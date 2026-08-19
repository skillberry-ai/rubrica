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
# The second capture: the same harness, model and target commit, run again after
# a pipeline run halted on gaps that only new traces could close. It re-captures
# p01-p10 and adds p11-p17, so it is the whole PROMPTS list where the first file
# is its first ten entries.
TRAJECTORIES2 = TRAJECTORIES_DIR / "trajectories2.json"
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


@pytest.fixture(scope="module")
def traces2() -> list:
    return json.loads(TRAJECTORIES2.read_text(encoding="utf-8"))


@pytest.fixture(scope="module", params=[TRAJECTORIES, TRAJECTORIES2], ids=["first", "second"])
def any_capture(request) -> list:
    """Each committed capture in turn, for the checks that must hold of both.

    Both files are surveyed as corpus inputs, so a structural property that
    matters for one matters identically for the other -- the `trace_id` mirror
    most of all, since without it `classify` returns `other` and every trace in
    the file loses its kind hint at once. Count and prompt-order checks stay
    per-file below, because those two differ by construction: the first capture
    predates `p11`.
    """
    return json.loads(Path(request.param).read_text(encoding="utf-8"))


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


def test_every_trace_carries_the_top_level_trace_id_mirror(any_capture):
    for trace in any_capture:
        assert trace["trace_id"] == trace["info"]["trace_id"]


def test_every_trace_has_at_least_one_span(any_capture):
    for trace in any_capture:
        assert trace["data"]["spans"]


@pytest.mark.parametrize("path", [TRAJECTORIES, TRAJECTORIES2], ids=["first", "second"])
def test_trajectories_classify_as_a_trace(path):
    """Guards the mirror's purpose rather than its presence: without the
    top-level trace_id this returns `other`."""
    assert classify(path) == "trace"


def test_every_trace_carries_the_user_turn(any_capture):
    """`info.request_preview` is what `digest.py`'s `request_text` heuristic
    reads, so a capture missing it hands `rb-triage` a corpus in which no user
    utterance is visible at all -- and triage then cannot judge whether the
    evidence covers the objective it was given.

    This is a measured failure, not a hypothetical. An earlier attempt at the
    second capture wrapped each graph invocation in its own MLflow span, which
    made MLflow name the trace after the wrapper and record no previews. Nothing
    else in this file or in the pipeline's own gates would have noticed.
    """
    for trace in any_capture:
        preview = trace["info"].get("request_preview")
        assert preview, "a trace with no request_preview hides its own user turn"
        assert json.loads(preview)["messages"][0]["content"]


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


def test_at_least_one_trace_observed_an_error_response(any_capture):
    """Four of the control run's five gaps are error-path questions. A fixture
    with no observed error cannot close any of them."""
    assert any(_error_payloads(trace) for trace in any_capture)


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


def _assert_prompt_order(prompts, traces) -> None:
    """Each trace carries the prompt that sits at its own index.

    Matches on the deterministic PROMPT TEXT the harness sent -- specifically,
    the longest literal chunk outside any `{placeholder}`, since p03, p05 and
    p12-p16 are filled from an observed id before being issued -- never on the
    model's own wording, so a legitimate re-capture with different LLM prose
    stays green.
    """
    for (pid, template), trace in zip(prompts, traces, strict=True):
        literal_chunks = [chunk.strip() for chunk in re.split(r"\{[^}]*\}", template)]
        distinctive = max(literal_chunks, key=len)
        content = json.loads(trace["info"]["request_preview"])["messages"][0]["content"]
        assert distinctive in content, f"{pid}: expected {distinctive!r} in {content!r}"


def test_first_capture_is_in_prompt_order(traces):
    """Guards the order the staging split depends on (README, "Staging for
    intake": split "in array order", named from `PROMPTS`'s ids by position).
    A reordering here would mislabel every split file with the wrong prompt.

    Held against the FIRST `len(traces)` prompts, because this file was captured
    before `p11` onwards existed. The slice is only meaningful because the check
    is by content: inserting a new prompt anywhere inside `p01`-`p10` rather
    than appending after them shifts every later trace against its template and
    fails here, which is exactly the drift worth catching.
    """
    _assert_prompt_order(_prompts()[: len(traces)], traces)


def test_second_capture_covers_every_prompt_in_order(traces2):
    """The second capture is the whole list, so this is the stronger form of the
    check above: one trace per prompt, in order, nothing skipped.

    It is also what keeps `PROMPTS` and this fixture honest about each other. Add
    a prompt without re-capturing and `strict=True` fails on the length; re-capture
    without adding and it fails the same way from the other side.
    """
    _assert_prompt_order(_prompts(), traces2)
