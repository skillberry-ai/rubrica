"""The trajectory fixture still carries what the experiment depends on.

Not a test of any skill -- a test of the fixture, in the shape of
test_refusal_fixtures.py. Two things would silently invalidate the trajectory
run if they drifted: the top-level `trace_id` mirror (without it `classify`
returns `other` and the extract member loses its kind hint), and the opaque
`outputSchema` (the run's whole premise is that /tools/list says nothing about
outputs). Neither shows up as a failure anywhere else.

Assertions are on structure and on `classify`'s verdict, never on captured
prose, so a legitimate re-capture with different LLM wording stays green.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from rubrica.intake import classify
from tests.toy import TRAJECTORIES_DIR

TOOLS_LIST = TRAJECTORIES_DIR / "tools-list.json"
TRAJECTORIES = TRAJECTORIES_DIR / "trajectories.json"
# The harness lives in scripts/, not beside the fixture: it is a capture tool
# whose absolute paths only resolve on the machine that ran it, not a test.
# Still read from here, because PROMPTS is the fixture's own record of which
# trace is which -- derived from the source rather than copied into a literal,
# so a re-capture that changes the prompts changes what these tests expect.
CAPTURE_HARNESS = (
    Path(__file__).resolve().parents[2] / "scripts" / "capture-reservation-trajectories.py"
)

FIVE_TOOLS = frozenset(
    {
        "search_restaurants",
        "check_availability",
        "place_reservation",
        "cancel_reservation",
        "list_reservations",
    }
)


@pytest.fixture(scope="module")
def tools_doc() -> dict:
    return json.loads(TOOLS_LIST.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def traces() -> list:
    return json.loads(TRAJECTORIES.read_text(encoding="utf-8"))


def test_tools_list_has_the_five_capabilities(tools_doc):
    assert {t["name"] for t in tools_doc["tools"]} == FIVE_TOOLS


def test_every_tool_specifies_its_inputs(tools_doc):
    for tool in tools_doc["tools"]:
        assert tool["inputSchema"]["properties"], tool["name"]


def test_no_tool_specifies_its_outputs(tools_doc):
    """The premise of the run: outputs are opaque, so trajectories are the only
    source of output knowledge. If a tool's declared `outputSchema.properties.result`
    goes narrower than an opaque string, the spec needs revising, not the
    assertion. An `outputSchema` that is *absent entirely* is also acceptable --
    it is strictly more opaque than a declared opaque string, so `.get(..., "string")`
    defaults it to the value that already passes rather than failing the one
    direction that strengthens this test's own premise."""
    for tool in tools_doc["tools"]:
        result = tool.get("outputSchema", {}).get("properties", {}).get("result", {})
        assert result.get("type", "string") == "string", tool["name"]


def test_tools_list_classifies_as_an_mcp_tool_schema():
    assert classify(TOOLS_LIST) == "mcp_tool_schema"


def test_every_trace_carries_the_top_level_trace_id_mirror(traces):
    for trace in traces:
        assert trace["trace_id"] == trace["info"]["trace_id"]


def test_every_trace_has_at_least_one_span(traces):
    for trace in traces:
        assert trace["data"]["spans"]


def test_trajectories_classify_as_a_trace():
    """Guards the mirror's purpose rather than its presence: without the
    top-level trace_id this returns `other`."""
    assert classify(TRAJECTORIES) == "trace"


def _error_payloads(obj) -> list[dict]:
    """Every `{"error": ...}` object reachable in a trace, JSON-in-string included.

    A tool error comes back as `json.dumps({"error": str(e)})` -- a JSON *string*
    that MLflow then stores inside a span attribute, so the payload is
    double-encoded and has to be parsed rather than matched. Measured: with the
    three traces carrying genuine tool errors excluded, `"error" in
    json.dumps(trace)` still returns True, because every tool's description says
    it "will return an appropriate error message". Matching the substring tests
    the schema's prose, not the observation.
    """
    found: list[dict] = []
    if isinstance(obj, dict):
        if "error" in obj:
            found.append(obj)
        for value in obj.values():
            found += _error_payloads(value)
    elif isinstance(obj, list):
        for value in obj:
            found += _error_payloads(value)
    elif isinstance(obj, str):
        try:
            parsed = json.loads(obj)
        except (json.JSONDecodeError, TypeError):
            return found
        found += _error_payloads(parsed)
    return found


def test_at_least_one_trace_observed_an_error_response(traces):
    """Four of the control run's five gaps are error-path questions. A fixture
    with no observed error cannot close any of them."""
    assert any(_error_payloads(trace) for trace in traces)


def _prompts() -> list[tuple[str, str]]:
    """The `(id, prompt_text)` pairs from `capture-reservation-trajectories.py`'s
    own `PROMPTS` list, in order.

    Parsed with `ast.literal_eval` rather than a regex over the whole file.
    Measured: `re.findall(r'\\("(p\\d\\d-[a-z-]+)"', text)` finds only 6 of the
    10 ids here, because `ruff format` reflowed several `PROMPTS` entries onto
    their own line, putting a newline between the tuple's opening `(` and its
    id string -- the anchor the naive regex depends on. `ast.literal_eval`
    doesn't care how the source is line-wrapped (that is what makes it a
    parser and not a pattern match), so the `PROMPTS` assignment is sliced out
    by its own brackets and evaluated as a list literal instead.
    """
    text = CAPTURE_HARNESS.read_text(encoding="utf-8")
    marker = "PROMPTS: list[tuple[str, str]] = ["
    start = text.index(marker) + len(marker) - 1  # position of the assignment's own "["
    end = text.index("]", start) + 1
    return ast.literal_eval(text[start:end])


def test_ten_traces_committed(traces):
    """The fixture README's staging contract splits `trajectories.json` into
    one file per trace "in array order" and names each from `PROMPTS`'s ids.
    Both the count and the order (below) are load-bearing for that split, and
    nothing else in this file or in `intake`/`check-refs` would notice a
    re-capture that silently dropped one."""
    assert len(traces) == 10


def test_traces_are_in_prompt_order(traces):
    """Guards the order the staging split depends on (README, "Staging for
    intake": split "in array order", named from `PROMPTS`'s ids by position).
    A reordering here would mislabel every split file with the wrong prompt.

    Matches on the deterministic PROMPT TEXT the harness sent -- specifically,
    the longest literal chunk outside any `{placeholder}`, since p03 and p05
    are filled from an observed id before being issued -- never on the model's
    own wording, so a legitimate re-capture with different LLM prose stays
    green.
    """
    prompts = _prompts()
    assert len(prompts) == len(traces)
    for (pid, template), trace in zip(prompts, traces, strict=True):
        literal_chunks = [chunk.strip() for chunk in re.split(r"\{[^}]*\}", template)]
        distinctive = max(literal_chunks, key=len)
        content = json.loads(trace["info"]["request_preview"])["messages"][0]["content"]
        assert distinctive in content, f"{pid}: expected {distinctive!r} in {content!r}"
