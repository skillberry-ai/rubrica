"""verify.py refuses a contract it cannot read, and rules on a log it cannot.

Both paths are about the same distinction: a bypassed authoring gate must not
reach the platform as a real zero, and a malformed agent log must not reach it as
an inflated score.
"""

from __future__ import annotations

import json

from testgen.suite.verify import main, parse_transcript, read_contract
from tests.builders import minimal_suite_expected


def _package(tmp_path, contract_text):
    expected = tmp_path / "expected.json"
    expected.write_text(contract_text, encoding="utf-8")
    logs = tmp_path / "agent"
    logs.mkdir()
    (logs / "t.jsonl").write_text("", encoding="utf-8")
    out = tmp_path / "verifier"
    return ["--expected", str(expected), "--agent-logs", str(logs), "--out", str(out)], out


# -- an unreadable contract ---------------------------------------------------


def test_a_truncated_contract_is_refused_rather_than_crashing(tmp_path):
    argv, out = _package(tmp_path, '{"contract": "testgen/v1", "assert')
    assert main(argv) == 2
    assert not (out / "reward.txt").exists(), "a refusal must not look like a real zero"
    detail = json.loads((out / "reward-detail.json").read_text())
    assert "not parseable JSON" in detail["error"]


def test_a_contract_that_is_not_an_object_is_refused(tmp_path):
    """json.loads("[]") parses fine and then every .get() call would raise."""
    argv, out = _package(tmp_path, "[]")
    assert main(argv) == 2
    assert not (out / "reward.txt").exists()
    assert "not an object" in json.loads((out / "reward-detail.json").read_text())["error"]


def test_an_absent_contract_is_refused(tmp_path):
    out = tmp_path / "verifier"
    assert main(["--expected", str(tmp_path / "nope.json"), "--out", str(out)]) == 2
    assert "could not be read" in json.loads((out / "reward-detail.json").read_text())["error"]


def test_a_well_formed_contract_still_scores(tmp_path):
    """The refusal path must not have swallowed the ordinary one."""
    argv, out = _package(tmp_path, json.dumps(minimal_suite_expected()))
    assert main(argv) == 0
    assert (out / "reward.txt").read_text() == "0.0"


def test_read_contract_returns_the_document_when_it_is_fine(tmp_path):
    path = tmp_path / "c.json"
    path.write_text('{"contract": "testgen/v1"}', encoding="utf-8")
    contract, problems = read_contract(path)
    assert problems == []
    assert contract == {"contract": "testgen/v1"}


# -- a non-string result ------------------------------------------------------


def _result_line(payload):
    return json.dumps({"type": "result", "subtype": "success", "result": payload})


def test_a_non_string_result_scores_as_no_answer():
    """The ruling: no answer, not str(payload).

    str({"text": "90420"}) contains "90420", so coercing would satisfy an
    answer_contains assertion against a dict the agent never said in prose --
    inflation at the scoring seam, which compute_reward's docstring forbids.
    """
    calls, answer, ok, notes = parse_transcript(_result_line({"text": "90420"}))
    assert answer == ""
    assert ok is True, "the run itself succeeded; it is the answer that is unreadable"
    assert any("rather than a string" in note for note in notes)
    assert "dict" in " ".join(notes)


def test_a_null_result_scores_as_no_answer_without_a_note():
    """None is an ordinary empty answer, not a malformed one."""
    _, answer, _, notes = parse_transcript(_result_line(None))
    assert answer == ""
    assert notes == []


def test_a_non_object_event_is_skipped_and_counted():
    _, answer, _, notes = parse_transcript('{"type": "result", "result": "ok"}\n[1, 2, 3]')
    assert answer == "ok"
    assert any("skipped 1" in note for note in notes)


def test_an_assistant_event_with_a_non_object_message_is_skipped():
    calls, _, _, notes = parse_transcript(json.dumps({"type": "assistant", "message": "oops"}))
    assert calls == []
    assert any("message was not an object" in note for note in notes)


def test_an_assistant_event_with_non_list_content_is_skipped_and_noted():
    event = {"type": "assistant", "message": {"content": {"not": "a list"}}}
    calls, _, _, notes = parse_transcript(json.dumps(event))
    assert calls == []
    assert any("message.content was not a list" in note for note in notes)


def test_a_tool_use_block_with_non_dict_input_is_recorded_with_no_args_and_noted():
    """input: ["a"] must not be dropped silently -- the call still happened."""
    event = {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": "query_aap2", "input": ["a"]}]},
    }
    calls, _, _, notes = parse_transcript(json.dumps(event))
    assert calls == [("query_aap2", {})]
    assert any("input was not an object" in note for note in notes)


def test_a_tool_use_block_with_a_non_string_name_is_recorded_as_is_and_noted():
    """The name is recorded rather than coerced: call_matches compares it
    against a contract `tool`, which is always a string, so a non-string name
    simply never matches -- the same fail-closed outcome as elsewhere here.
    """
    event = {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": 123, "input": {}}]},
    }
    calls, _, _, notes = parse_transcript(json.dumps(event))
    assert calls == [(123, {})]
    assert any("name was a int rather than a string" in note for note in notes)


def test_a_non_string_result_followed_by_a_healthy_one_leaves_no_stale_note():
    """The note tracks whichever result event actually becomes `answer`.

    A partial transcript plus a terminal error event can yield two result
    events; the last one wins. A note pinned to the first, discarded, event
    would tell a human reading reward-detail.json that no answer was read
    when the run was in fact scored with one.
    """
    text = "\n".join([_result_line({"text": "90420"}), _result_line("Job 90420 failed.")])
    _, answer, _, notes = parse_transcript(text)
    assert answer == "Job 90420 failed."
    assert notes == []


def test_a_healthy_result_followed_by_a_non_string_one_leaves_the_note():
    """The reverse order: the malformed event is the one that wins."""
    text = "\n".join([_result_line("Job 90420 failed."), _result_line({"text": "90420"})])
    _, answer, _, notes = parse_transcript(text)
    assert answer == ""
    assert any("rather than a string" in note for note in notes)


def test_the_notes_reach_reward_detail(tmp_path):
    """A concession invisible in the output is a silent one."""
    argv, out = _package(tmp_path, json.dumps(minimal_suite_expected()))
    logs = tmp_path / "agent"
    (logs / "t.jsonl").write_text(_result_line({"text": "90420"}), encoding="utf-8")
    assert main(argv) == 0
    detail = json.loads((out / "reward-detail.json").read_text())
    assert any("rather than a string" in note for note in detail["transcript_notes"])
    assert json.loads((out / "reward.txt").read_text()) == 0.0
