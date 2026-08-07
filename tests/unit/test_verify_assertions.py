"""The generic verifier's transcript parsing and assertion scoring.

Imports the tracked original that emit copies verbatim, so the tested file and
the executed file cannot differ.
"""

from __future__ import annotations

import json

import pytest

from testgen.suite.verify import (
    call_matches,
    parse_transcript,
    score_assertions,
    values_equal,
)


def _transcript(*events) -> str:
    return "\n".join(json.dumps(e) for e in events)


def _tool_use(name, args):
    return {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": name, "input": args}]},
    }


def _result(text, *, subtype="success", is_error=False):
    return {"type": "result", "subtype": subtype, "is_error": is_error, "result": text}


# -- parse_transcript --------------------------------------------------------


def test_a_transcript_yields_its_calls_answer_and_success_flag():
    text = _transcript(
        _tool_use("query_aap2", {"action": "find_jobs", "controller": "prod0"}),
        _result("Job 90420 failed."),
    )
    calls, answer, ok = parse_transcript(text)
    assert calls == [("query_aap2", {"action": "find_jobs", "controller": "prod0"})]
    assert answer == "Job 90420 failed."
    assert ok is True


def test_a_malformed_line_is_skipped_rather_than_fatal():
    """A truncated transcript must still score; crashing would report a broken agent."""
    text = "not json\n{\n" + _transcript(_result("done"))
    calls, answer, ok = parse_transcript(text)
    assert calls == []
    assert answer == "done"


def test_an_error_result_is_not_ok():
    _, _, ok = parse_transcript(_transcript(_result("boom", subtype="error", is_error=True)))
    assert ok is False


def test_the_last_result_event_wins():
    text = _transcript(_result("first"), _result("second"))
    _, answer, _ = parse_transcript(text)
    assert answer == "second"


def test_a_tool_use_with_no_input_yields_empty_args():
    text = _transcript(
        {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "name": "query_aap2"}]},
        }
    )
    calls, _, _ = parse_transcript(text)
    assert calls == [("query_aap2", {})]


def test_an_empty_transcript_yields_no_answer_and_not_ok():
    calls, answer, ok = parse_transcript("")
    assert (calls, answer, ok) == ([], "", False)


# -- values_equal and call_matches ------------------------------------------


@pytest.mark.parametrize(
    ("want", "got", "expected"),
    [
        (90420, 90420, True),
        (90420, "90420", True),
        ("90420", 90420, True),
        (90420.0, 90420, True),
        (True, 1, False),
        (1, True, False),
        (True, True, True),
        ("prod0", "prod0", True),
        ("prod0", "prod1", False),
    ],
)
def test_values_equal_compares_numbers_numerically_and_bools_strictly(want, got, expected):
    """An agent serialising job_id as a string still chose the right job; but
    failed_only=true and failed_only=1 are different intents."""
    assert values_equal(want, got) is expected


def test_a_call_matches_on_an_argument_subset():
    call = ("query_aap2", {"action": "find_jobs", "controller": "prod0", "max_results": 50})
    assert call_matches({"tool": "query_aap2", "args": {"action": "find_jobs"}}, call)


def test_a_call_with_a_missing_required_argument_does_not_match():
    call = ("query_aap2", {"action": "find_jobs"})
    assert not call_matches({"tool": "query_aap2", "args": {"controller": "prod0"}}, call)


def test_a_call_with_the_wrong_tool_name_does_not_match():
    assert not call_matches({"tool": "other", "args": {}}, ("query_aap2", {}))


def test_a_spec_with_no_args_matches_any_call_to_that_tool():
    assert call_matches({"tool": "query_aap2"}, ("query_aap2", {"action": "anything"}))


# -- score_assertions -------------------------------------------------------


def _assertion(kind, **over):
    base = {"id": "a0", "kind": kind, "value": "90420", "rationale": "because"}
    base.update(over)
    return base


def test_every_assertion_satisfied_scores_one():
    calls = [("query_aap2", {"action": "find_jobs"})]
    assertions = [
        _assertion("answer_contains", value="90420"),
        _assertion("answer_excludes", id="a1", value="DNS"),
        _assertion("value_equals", id="a2", value="90420", target="job_id"),
        _assertion("tool_called", id="a3", tool="query_aap2", args={"action": "find_jobs"}),
        _assertion("tool_not_called", id="a4", tool="query_aap2", args={"action": "delete_job"}),
    ]
    score, detail = score_assertions("Job 90420 failed on prod0.", calls, assertions)
    assert score == 1.0
    assert detail["failed"] == []
    assert detail["total"] == 5


def test_answer_contains_is_case_insensitive():
    assertions = [_assertion("answer_contains", value="failed")]
    score, _ = score_assertions("job 90420 FAILED", [], assertions)
    assert score == 1.0


def test_answer_excludes_is_violated_by_a_case_variant():
    """Case-insensitivity makes an exclusion stricter, which is the right direction."""
    assertions = [_assertion("answer_excludes", value="DNS")]
    score, detail = score_assertions("caused by dns", [], assertions)
    assert score == 0.0
    assert [f["id"] for f in detail["failed"]] == ["a0"]


def test_value_equals_is_not_satisfied_by_a_longer_number():
    score, _ = score_assertions("job 13 failed", [], [_assertion("value_equals", value="3")])
    assert score == 0.0


def test_value_equals_is_satisfied_at_a_punctuation_boundary():
    score, _ = score_assertions("the count was 3.", [], [_assertion("value_equals", value="3")])
    assert score == 1.0


def test_value_equals_is_satisfied_at_the_end_of_the_answer():
    score, _ = score_assertions("the count was 3", [], [_assertion("value_equals", value="3")])
    assert score == 1.0


def test_tool_not_called_fails_when_the_call_was_made():
    calls = [("query_aap2", {"action": "delete_job", "job_id": 1})]
    assertion = _assertion("tool_not_called", tool="query_aap2", args={"action": "delete_job"})
    score, detail = score_assertions("done", calls, [assertion])
    assert score == 0.0
    assert detail["failed"][0]["kind"] == "tool_not_called"


def test_a_partially_satisfied_set_scores_the_fraction():
    assertions = [
        _assertion("answer_contains", value="90420"),
        _assertion("answer_contains", id="a1", value="never-present"),
    ]
    score, detail = score_assertions("Job 90420.", [], assertions)
    assert score == 0.5
    assert [f["id"] for f in detail["failed"]] == ["a1"]


def test_an_unknown_kind_is_reported_as_failed_rather_than_awarded():
    """The vocabulary is closed. An unknown kind means a bypassed gate, and
    awarding a point for one would hide it."""
    score, detail = score_assertions("anything", [], [_assertion("answer_matches_regex")])
    assert score == 0.0
    assert "unknown assertion kind" in json.dumps(detail)


def test_an_empty_assertion_list_scores_one():
    score, detail = score_assertions("anything", [], [])
    assert score == 1.0
    assert detail["total"] == 0
