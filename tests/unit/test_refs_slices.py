"""refs.check_slices: 00-slices.json against 00-catalogue.json.

Six checks, each mutating an otherwise-clean sliced run minimally so the
finding it names is the *only* one reported -- the same discipline
test_refs_readable.py uses for check_readable, and for the same reason: a
test that lets its own mutation trip a second, unrelated check would not
have proven the checker names the right defect.
"""

from __future__ import annotations

from pathlib import Path

from rubrica import survey
from rubrica.artifacts import read_json, write_json
from rubrica.refs import check_slices
from rubrica.slices import write_slices


def _toy_run(tmp_path):
    return survey.survey(
        corpus_roots=[Path("tests/fixtures/toy")],
        runs_dir=tmp_path / "runs",
        target_name="toy",
        target_interface="http",
        objective="breadth",
        max_rounds=2,
        max_scenarios=128,
    )


def _sliced_run(tmp_path, *, cap=2500):
    # cap=2500: the toy fixture's largest single candidate (api.json,
    # 2381B) fits, but the fixture's ~4.1KB total does not, so this is the
    # smallest cap that still splits it into more than one slice --
    # test_slices.py's own reasoning for the same number. At this cap every
    # one of the toy fixture's three candidates lands alone (measured), so
    # the one test needing a multi-candidate slice passes its own cap.
    run = _toy_run(tmp_path)
    write_slices(run, cap=cap)
    return run


def test_a_clean_sliced_run_reports_nothing(tmp_path):
    assert check_slices(_sliced_run(tmp_path)) == []


def test_an_absent_plan_reports_nothing_rather_than_crashing(tmp_path):
    """check_all runs every checker the run has inputs for, so a run before
    triage-slices must produce no findings here at all."""
    run = _toy_run(tmp_path)
    assert check_slices(run) == []


def test_an_unreadable_plan_is_one_finding_not_a_traceback(tmp_path):
    """The exact incident the module docstring records, replayed for this
    artifact: continuing past a plan that failed to parse would resolve
    candidate_ids that were never read, fabricating a finding per id against
    a catalogue that is fine."""
    run = _sliced_run(tmp_path)
    run.slices.write_text("{not json", encoding="utf-8")
    findings = check_slices(run)
    assert len(findings) == 1
    assert findings[0].artifact == run.slices


def test_a_candidate_no_slice_covers_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    plan = read_json(run.slices)
    dropped = plan["slices"][0]["candidate_ids"].pop()
    write_json(run.slices, plan)
    findings = check_slices(run)
    assert any(dropped in f.message and "no slice" in f.message for f in findings)


def test_a_candidate_in_two_slices_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    plan = read_json(run.slices)
    dupe = plan["slices"][0]["candidate_ids"][0]
    plan["slices"][1]["candidate_ids"].append(dupe)
    write_json(run.slices, plan)
    findings = check_slices(run)
    assert any(dupe in f.message and "is in slices" in f.message for f in findings)


def test_a_slice_naming_an_unknown_candidate_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    plan = read_json(run.slices)
    plan["slices"][0]["candidate_ids"].append("ghost")
    write_json(run.slices, plan)
    findings = check_slices(run)
    assert any("ghost" in f.message and "no such candidate" in f.message for f in findings)


def test_duplicate_slice_ids_are_reported(tmp_path):
    run = _sliced_run(tmp_path)
    plan = read_json(run.slices)
    assert len(plan["slices"]) > 1, "cap=2500 must split the toy fixture into >1 slice"
    plan["slices"][1]["id"] = plan["slices"][0]["id"]
    write_json(run.slices, plan)
    findings = check_slices(run)
    assert any(
        plan["slices"][0]["id"] in f.message and "more than one slice" in f.message
        for f in findings
    )


def test_a_missing_shard_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    sid = read_json(run.slices)["slices"][0]["id"]
    run.slice_shard(sid).unlink()
    findings = check_slices(run)
    assert any(sid in f.message and "no shard" in f.message for f in findings)


def test_an_orphan_shard_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    (run.slices_dir / "s99.json").write_text("{}", encoding="utf-8")
    findings = check_slices(run)
    assert any("s99" in f.message for f in findings)


def test_a_slice_whose_recorded_bytes_are_wrong_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    plan = read_json(run.slices)
    plan["slices"][0]["bytes"] += 1
    write_json(run.slices, plan)
    findings = check_slices(run)
    assert any("bytes" in f.message for f in findings)


def test_a_shard_whose_candidates_disagree_with_the_plan_is_reported(tmp_path):
    """The plan and the shard can each be edited independently, so agreeing
    on the *set* of ids is not enough -- check 6 holds them to the same
    order, the property emit and every downstream member actually rely on."""
    # cap=3500: api-json (2381B) and trace-json (418B) pack into one slice
    # together (measured), which notes-md (1303B) alone does not do with
    # any of the other two -- the smallest cap that gives a >1-candidate
    # slice to reorder.
    run = _sliced_run(tmp_path, cap=3500)
    plan = read_json(run.slices)
    multi = next(s for s in plan["slices"] if len(s["candidate_ids"]) > 1)
    sid = multi["id"]
    shard = read_json(run.slice_shard(sid))
    assert len(shard["candidates"]) > 1, "reordering needs at least two candidates"
    shard["candidates"] = list(reversed(shard["candidates"]))
    write_json(run.slice_shard(sid), shard)
    findings = check_slices(run)
    assert any(sid in f.message and "do not match" in f.message for f in findings)


def test_a_slice_over_the_cap_is_reported(tmp_path):
    """The seventh check: cap_bytes is the budget every slice was packed
    against, and nothing in the schema relates a slice's own bytes to it --
    that relationship is exactly the kind of cross-field arithmetic layer 1
    cannot state and layer 2 exists for."""
    run = _sliced_run(tmp_path)
    plan = read_json(run.slices)
    plan["slices"][0]["bytes"] = plan["cap_bytes"] + 1
    write_json(run.slices, plan)
    findings = check_slices(run)
    assert any("cap" in f.message for f in findings)
