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
    calls, _, _, _ = parse_transcript(json.dumps({"type": "assistant", "message": "oops"}))
    assert calls == []


def test_the_notes_reach_reward_detail(tmp_path):
    """A concession invisible in the output is a silent one."""
    argv, out = _package(tmp_path, json.dumps(minimal_suite_expected()))
    logs = tmp_path / "agent"
    (logs / "t.jsonl").write_text(_result_line({"text": "90420"}), encoding="utf-8")
    assert main(argv) == 0
    detail = json.loads((out / "reward-detail.json").read_text())
    assert any("rather than a string" in note for note in detail["transcript_notes"])
    assert json.loads((out / "reward.txt").read_text()) == 0.0
