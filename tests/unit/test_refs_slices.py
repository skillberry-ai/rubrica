"""refs.check_slices: 00-slices.json against 00-catalogue.json.

Six checks (plus a seventh added on top, cap_bytes -- see check_slices'
docstring), each proven with a mutation isolated to *only* that invariant:
the plan and the shard are edited together so every other check's inputs
stay internally consistent, and only the targeted defect is visible. This
is the same discipline test_refs_readable.py uses for check_readable, and
for the same reason -- a test that lets its own mutation trip a second,
unrelated check would prove only "some finding fires", not "this checker
names this defect". Every test below asserts both: the intended finding is
present, and it is the *only* one, so a future change that reintroduces a
second trip fails the test rather than passing quietly.
"""

from __future__ import annotations

from pathlib import Path

from rubrica import survey
from rubrica.artifacts import read_json, write_json
from rubrica.refs import check_slices
from rubrica.slices import row_bytes, write_slices


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
    # Dropping the id from candidate_ids alone leaves it sitting in the
    # shard, which would also trip check 6 (shard vs. candidate_ids). The
    # candidate has to be removed from *both*, and the slice's declared
    # bytes rolled back by exactly its row_bytes, so nothing but its
    # absence from every slice is left to notice.
    run = _sliced_run(tmp_path)
    plan = read_json(run.slices)
    sid = plan["slices"][0]["id"]
    dropped = plan["slices"][0]["candidate_ids"].pop()
    shard = read_json(run.slice_shard(sid))
    removed = next(c for c in shard["candidates"] if c["candidate_id"] == dropped)
    shard["candidates"].remove(removed)
    plan["slices"][0]["bytes"] -= row_bytes(removed)
    write_json(run.slices, plan)
    write_json(run.slice_shard(sid), shard)
    findings = check_slices(run)
    assert len(findings) == 1
    assert dropped in findings[0].message and "no slice" in findings[0].message


def test_a_candidate_in_two_slices_is_reported(tmp_path):
    # Appending the duplicate id to a second slice's candidate_ids alone
    # would leave that slice's shard disagreeing with its candidate_ids
    # (check 6) and, depending on which slice absorbs it, possibly over
    # cap_bytes (check 7). The duplicate has to land in the second slice's
    # shard too, with its bytes rolled forward to match -- and the target
    # slice has to be the one with enough headroom under the cap, which for
    # this fixture at cap=2500 is only the notes-md/trace-json pair
    # (1303 + 418 = 1721); api-json (2381) has no room for either.
    run = _sliced_run(tmp_path)
    plan = read_json(run.slices)
    by_bytes = sorted(plan["slices"], key=lambda s: s["bytes"])
    source = by_bytes[0]
    dupe = source["candidate_ids"][0]
    dupe_candidate = next(
        c
        for c in read_json(run.slice_shard(source["id"]))["candidates"]
        if c["candidate_id"] == dupe
    )
    target = next(
        s
        for s in plan["slices"]
        if s["id"] != source["id"] and s["bytes"] + row_bytes(dupe_candidate) <= plan["cap_bytes"]
    )
    for s in plan["slices"]:
        if s["id"] == target["id"]:
            s["candidate_ids"].append(dupe)
            s["bytes"] += row_bytes(dupe_candidate)
    shard = read_json(run.slice_shard(target["id"]))
    shard["candidates"].append(dupe_candidate)
    write_json(run.slices, plan)
    write_json(run.slice_shard(target["id"]), shard)
    findings = check_slices(run)
    assert len(findings) == 1
    assert dupe in findings[0].message and "is in slices" in findings[0].message


def test_a_slice_naming_an_unknown_candidate_is_reported(tmp_path):
    # Appending "ghost" to candidate_ids alone would also trip check 6
    # (shard vs. candidate_ids order) and, without rolling the extra bytes
    # forward, check 5 (bytes arithmetic) too. Extending the shard to match
    # and folding ghost's own row_bytes into the declared total leaves only
    # the one thing genuinely wrong: "ghost" does not resolve against the
    # catalogue.
    run = _sliced_run(tmp_path)
    plan = read_json(run.slices)
    sid = plan["slices"][0]["id"]
    plan["slices"][0]["candidate_ids"].append("ghost")
    ghost = {"candidate_id": "ghost"}
    shard = read_json(run.slice_shard(sid))
    shard["candidates"].append(ghost)
    plan["slices"][0]["bytes"] += row_bytes(ghost)
    write_json(run.slices, plan)
    write_json(run.slice_shard(sid), shard)
    findings = check_slices(run)
    assert len(findings) == 1
    assert "ghost" in findings[0].message and "no such candidate" in findings[0].message


def test_duplicate_slice_ids_are_reported(tmp_path):
    """The hardest of the six to isolate, because a collision *is* two plan
    entries resolving to one physical shard file -- there is only one path
    run.slice_shard(sid) can name, so making the two entries' candidate_ids
    differ (to dodge check 1's coverage count) leaves at least one of them
    disagreeing with that one shard (check 5/6), and making them agree with
    the shard means making them identical, which then reintroduces the
    coverage question for every candidate they share.

    The construction that resolves it: the toy fixture fits one slice at
    the default cap (measured), so duplicating that single entry -- id,
    candidate_ids, bytes, all of it -- gives both entries the *same*
    (already-correct) shard, bytes and candidate_ids, with nothing left
    to disagree about except the id collision itself. That still needed a
    real fix in check_slices, not just a clever fixture: coverage now
    counts *distinct* slice ids per candidate rather than raw occurrences
    (see the coverage-tracking comment there), so two entries correctly
    sharing one id do not also look like a check-1 double-coverage defect.
    """
    run = _toy_run(tmp_path)
    write_slices(run)  # default cap (65536): one slice holds the whole fixture
    plan = read_json(run.slices)
    assert len(plan["slices"]) == 1, "toy fixture must still fit one slice at the default cap"
    sid = plan["slices"][0]["id"]
    plan["slices"].append(dict(plan["slices"][0]))
    write_json(run.slices, plan)
    findings = check_slices(run)
    assert len(findings) == 1
    assert sid in findings[0].message and "more than one slice" in findings[0].message


def test_a_missing_shard_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    sid = read_json(run.slices)["slices"][0]["id"]
    run.slice_shard(sid).unlink()
    findings = check_slices(run)
    assert len(findings) == 1
    assert sid in findings[0].message and "no shard" in findings[0].message


def test_an_orphan_shard_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    (run.slices_dir / "s99.json").write_text("{}", encoding="utf-8")
    findings = check_slices(run)
    assert len(findings) == 1
    assert "s99" in findings[0].message


def test_a_slice_whose_recorded_bytes_are_wrong_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    plan = read_json(run.slices)
    plan["slices"][0]["bytes"] += 1
    write_json(run.slices, plan)
    findings = check_slices(run)
    assert len(findings) == 1
    assert "bytes" in findings[0].message


def test_a_shard_whose_candidates_disagree_with_the_plan_is_reported(tmp_path):
    """The plan and the shard can each be edited independently, so agreeing
    on the *set* of ids is not enough -- check 6 holds them to the same
    order, the property emit and every downstream member actually rely on.
    Reordering (not adding or removing) leaves the byte sum, the id set,
    and cap compliance all untouched, so only the order defect shows."""
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
    assert len(findings) == 1
    assert sid in findings[0].message and "do not match" in findings[0].message


def test_a_slice_over_the_cap_is_reported(tmp_path):
    """The seventh check: cap_bytes is the budget every slice was packed
    against, and nothing in the schema relates a slice's own bytes to it --
    that relationship is exactly the kind of cross-field arithmetic layer 1
    cannot state and layer 2 exists for. Inflating the declared bytes field
    alone would also trip check 5 (bytes-vs-shard mismatch); padding the
    shard's own candidate so the *recomputed* sum genuinely exceeds the cap,
    then declaring that same recomputed number, leaves only the cap
    violation visible."""
    run = _sliced_run(tmp_path)
    plan = read_json(run.slices)
    sid = plan["slices"][0]["id"]
    cap = plan["cap_bytes"]
    shard = read_json(run.slice_shard(sid))
    shard["candidates"][0]["_pad_for_cap_test"] = "x" * (cap + 1)
    recomputed = sum(row_bytes(c) for c in shard["candidates"])
    assert recomputed > cap, "padding must genuinely exceed the cap"
    plan["slices"][0]["bytes"] = recomputed
    write_json(run.slices, plan)
    write_json(run.slice_shard(sid), shard)
    findings = check_slices(run)
    assert len(findings) == 1
    assert sid in findings[0].message and "cap" in findings[0].message
