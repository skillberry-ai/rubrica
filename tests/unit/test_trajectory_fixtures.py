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

import json

import pytest

from rubrica.intake import classify
from tests.toy import TRAJECTORIES_DIR

TOOLS_LIST = TRAJECTORIES_DIR / "tools-list.json"
TRAJECTORIES = TRAJECTORIES_DIR / "trajectories.json"

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
    source of output knowledge. If this goes red the spec needs revising, not
    the assertion."""
    for tool in tools_doc["tools"]:
        result = tool.get("outputSchema", {}).get("properties", {}).get("result", {})
        assert result.get("type") == "string", tool["name"]


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


def test_at_least_one_trace_observed_an_error_response(traces):
    """Four of the control run's five gaps are error-path questions. A fixture
    with no observed error cannot close any of them."""
    assert any("error" in json.dumps(trace) for trace in traces)
