"""refs.check_slices: 00-slices.json against 00-catalogue.json.

Every check that module numbers -- the partition, the shards, the byte
arithmetic, the cap, and the catalogue_facts block's two derived fields (see
check_slices itself for what each number means; a count written here went
stale the first time a check was added) -- is proven here with a mutation
isolated to *only* that invariant:
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


def _mutate_facts(run, mutate):
    """Edit only 00-slices.json's catalogue_facts, leaving the partition alone.

    The module's discipline: a mutation must be visible to exactly one check.
    catalogue_facts is read by nothing else in check_slices, so editing it
    cannot trip the partition, shard or cap checks -- which is why every test
    below can assert its finding is the only one.
    """
    plan = read_json(run.slices)
    mutate(plan["catalogue_facts"])
    write_json(run.slices, plan)


def test_a_clean_run_reports_no_catalogue_facts_findings(tmp_path):
    run = _sliced_run(tmp_path)
    assert check_slices(run) == []


def test_a_candidate_bytes_value_disagreeing_with_the_catalogue_is_reported(tmp_path):
    """The check that makes the whole block safe to read.

    rb-triage-objective sums weight.bytes from candidate_bytes while
    check_objective recomputes it from the catalogue. Without this check a
    drifted block would surface the objective pass's *correct* arithmetic as a
    finding against 00-objective.json -- a 1 naming the wrong artifact.
    """
    run = _sliced_run(tmp_path)
    catalogue = read_json(run.catalogue)
    victim = catalogue["candidates"][0]["candidate_id"]
    real = catalogue["candidates"][0]["bytes"]

    def bump(facts):
        facts["candidate_bytes"][victim] = real + 1

    _mutate_facts(run, bump)
    findings = check_slices(run)
    assert len(findings) == 1
    assert findings[0].pointer == f"/catalogue_facts/candidate_bytes/{victim}"
    assert str(real) in findings[0].message
    # Finding's field is `artifact`, not `path`. Which artifact a finding names
    # is the exit-code contract's third rule, so this assertion is the point of
    # the test as much as the pointer is.
    assert str(run.slices) == str(findings[0].artifact), "the plan is at fault, not the catalogue"


def test_a_candidate_missing_from_candidate_bytes_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    victim = read_json(run.catalogue)["candidates"][0]["candidate_id"]
    _mutate_facts(run, lambda facts: facts["candidate_bytes"].pop(victim))
    findings = check_slices(run)
    assert len(findings) == 1
    assert findings[0].pointer == f"/catalogue_facts/candidate_bytes/{victim}"
    assert "no candidate_bytes entry" in findings[0].message


def test_candidate_bytes_naming_a_candidate_the_catalogue_does_not_have_is_reported(tmp_path):
    """An extra id is drift too: a plan minted before the catalogue shrank."""
    run = _sliced_run(tmp_path)
    _mutate_facts(run, lambda facts: facts["candidate_bytes"].update({"ghost-1": 10}))
    findings = check_slices(run)
    assert len(findings) == 1
    assert findings[0].pointer == "/catalogue_facts/candidate_bytes/ghost-1"
    assert "not a catalogue candidate" in findings[0].message


def test_an_exclusion_total_disagreeing_with_the_catalogue_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    _mutate_facts(run, lambda facts: facts["excluded"].update({"total": 7}))
    findings = check_slices(run)
    assert len(findings) == 1
    assert findings[0].pointer == "/catalogue_facts/excluded/total"


def test_an_exclusion_tally_disagreeing_with_the_catalogue_is_reported(tmp_path):
    run = _sliced_run(tmp_path)
    _mutate_facts(run, lambda facts: facts["excluded"].update({"by_reason": {"binary": 3}}))
    findings = check_slices(run)
    assert len(findings) == 1
    assert findings[0].pointer == "/catalogue_facts/excluded/by_reason"


def test_an_unreadable_catalogue_reports_no_catalogue_facts_findings(tmp_path):
    """Silence, not one finding per candidate against a plan that is fine.

    This is the 01-claims/ incident: check-refs over an unreadable directory
    once reported four fabricated `no such claim` findings against a correct
    world model. An unreadable catalogue is check_readable's finding, and
    resolving candidate_bytes against candidates that were never parsed would
    blame the plan for the catalogue being broken.
    """
    run = _sliced_run(tmp_path)
    run.catalogue.write_text("{not json", encoding="utf-8")
    findings = check_slices(run)
    assert [f for f in findings if "catalogue_facts" in f.pointer] == []


def test_a_catalogue_whose_candidates_are_not_an_array_reports_no_bytes_findings(tmp_path):
    """The same skip, through the branch that already sets known_ids to None."""
    run = _sliced_run(tmp_path)
    catalogue = read_json(run.catalogue)
    catalogue["candidates"] = "not an array"
    write_json(run.catalogue, catalogue)
    findings = check_slices(run)
    assert [f for f in findings if "candidate_bytes" in f.pointer] == []
