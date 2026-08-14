"""Whether a digest carries what a decision needs.

Every assertion here is anchored to a decision the parsec run actually made by
hand, because "is this digest good enough" is otherwise unanswerable. If a
selection made on 2026-08-13 is not reachable from these fields, the digest is
wrong -- not the test.
"""

from __future__ import annotations

import json

from rubrica import digest


def test_prose_carries_the_full_heading_outline(tmp_path):
    """The parsec prose documents were admitted on title and structure.

    The outline is complete rather than truncated: it is the cheapest possible
    statement of what a document covers, and truncating it is how a triage
    misses the one section that mattered.
    """
    path = tmp_path / "architecture.md"
    path.write_text(
        "# Parsec\n\nIntro.\n\n## Routing\n\ntext\n\n### Fast path\n\nmore\n\n## Streaming\n\nx\n",
        encoding="utf-8",
    )
    result = digest.digest_for_path(path, "design_doc", body_chars=20)
    assert result["headings"] == ["# Parsec", "## Routing", "### Fast path", "## Streaming"]
    assert result["lines"] == 15
    assert len(result["body_head"]) <= 20
    assert result["digest_truncated"] is True


def test_source_carries_top_level_assignments_not_only_defs(tmp_path):
    """Spec §8: triage can only name TOOL_DEFINITIONS as a projection's
    extraction point if the digest lists top-level assignments. Without this
    field the projection brief cannot say where to start."""
    path = tmp_path / "tool_definitions.py"
    path.write_text(
        "import json\nfrom typing import Any\n\n"
        "TOOL_DEFINITIONS = [{'name': 'query_aap2'}]\n"
        "DELEGATION_TOOLS = []\n\n"
        "def build(x: Any) -> dict:\n    return {}\n\n"
        "class Registry:\n    pass\n",
        encoding="utf-8",
    )
    result = digest.digest_for_path(path, "source_code", body_chars=2000)
    assert result["assignments"] == ["DELEGATION_TOOLS", "TOOL_DEFINITIONS"]
    assert result["defs"] == ["build"]
    assert result["classes"] == ["Registry"]
    assert result["imports"] == ["json", "typing"]


def test_a_json_document_carries_a_structural_skeleton(tmp_path):
    path = tmp_path / "tools.json"
    path.write_text(
        json.dumps({"tools": [{"name": "a", "input_schema": {"type": "object"}}]}),
        encoding="utf-8",
    )
    result = digest.digest_for_path(path, "mcp_tool_schema", body_chars=2000)
    assert result["skeleton"]["/tools"] == {"type": "array", "length": 1}
    assert result["skeleton"]["/tools/0/name"] == {"type": "string"}


def test_a_trace_digest_reaches_every_parsec_selection():
    """The four facts the 2026-08-13 selection actually turned on:

    t7 kept for being the only ERROR with three spans; t3 identified as an
    icinga/aap2 crossover from its question text; depth judged from span count;
    tool coverage judged from span names.
    """
    element = {
        "trace_id": "tr-eef9",
        "status": "TraceStatus.ERROR",
        "execution_time_ms": 11776,
        "request_preview": '{"question": "How many sandbox accounts do we have in each region?"',
        "response_preview": '{"response": "I will query...", "routing_method": "llm"}',
        "spans": [
            {
                "name": "parsec:orchestrator",
                "span_type": "AGENT",
                "events": [{"name": "exception"}],
            },
            {"name": "query_aws_account_db", "span_type": "TOOL", "events": []},
            {"name": "db_list_tables", "span_type": "TOOL", "events": []},
        ],
    }
    result = digest.digest_for_payload(element, "trace", body_chars=2000)
    assert result["status"] == "TraceStatus.ERROR"
    assert result["element_counts"]["spans"] == 3
    assert "sandbox accounts" in result["request_text"]
    assert result["names"] == ["db_list_tables", "parsec:orchestrator", "query_aws_account_db"]
    assert result["error_markers"] is True
    assert "status" in result["heuristics_fired"]
    assert "names" in result["heuristics_fired"]


def test_a_heuristic_that_does_not_fire_is_absent_from_heuristics_fired():
    """This is the whole mitigation for §5.3.

    A digest that silently lacked a field would make triage guess. Recording
    which heuristics fired is what lets it decline digest_insufficient and name
    what it needed -- so this assertion is the load-bearing one in the file.
    """
    result = digest.digest_for_payload({"a": 1, "b": 2, "c": 3}, "trace", body_chars=2000)
    assert "status" not in result["heuristics_fired"]
    assert "names" not in result["heuristics_fired"]
    assert result["heuristics_fired"] == []


def test_every_named_heuristic_is_reachable():
    """A heuristic nobody can trigger is dead prose in the skill that cites it."""
    element = {
        "status": "OK",
        "spans": [{"name": "a"}, {"name": "b"}],
        "question": "why",
        "error": "boom",
    }
    result = digest.digest_for_payload(element, "trace", body_chars=2000)
    assert set(result["heuristics_fired"]) == set(digest.TRACE_HEURISTICS)


def test_an_undecodable_file_digests_to_a_recorded_failure(tmp_path):
    """Not a raise: survey already recorded readable files only, so reaching
    here means the bytes are not text -- and a digest that reports that is what
    lets triage decline rather than the run abort."""
    path = tmp_path / "notes.md"
    path.write_bytes(b"\xff\xfe\x00bad")
    result = digest.digest_for_path(path, "design_doc", body_chars=2000)
    assert result["undecodable"] is True
