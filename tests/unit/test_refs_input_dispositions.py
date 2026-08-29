"""The read-coverage accounting, and the five ways a row can be wrong.

Issue #6: three reconcile passes were re-dispatched over a byte-identical run
directory and read 12/23, 10/23 and 9/23 of 01-claims/ the first time, 23/23,
13/23 and 3/23 the second. One improved to full coverage and one got materially
worse, which is what rules out a systematic cause. Both runs reported success
and both passed layer 1.

Every test here mutates one field of a clean toy run and asserts exactly its own
finding, because the five shapes are close enough that a mutation reaching two of
them is the likely bug.
"""

from __future__ import annotations

from rubrica import refs
from rubrica.artifacts import read_json, write_json
from tests.toy import build_toy_run


def _rows(run, attribute="outcomes_part"):
    """The outcomes part by default: it is the one whose toy rows are not all
    zero-drop, so a mutation there exercises the note path too."""
    path = getattr(run, attribute)
    return path, read_json(path)


def test_a_clean_run_reports_nothing(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    assert refs.check_input_dispositions(run) == []


def test_a_missing_row_for_a_manifest_input_is_reported(tmp_path):
    """The denominator is manifest.inputs, not the rows.

    This is the finding a pass that read three of twenty-three files hits
    first, and the reason the rows must be total: an accounting that only
    covers what it read cannot report what it did not.
    """
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    path, part = _rows(run)
    dropped_row = part["inputs_seen"].pop()
    write_json(path, part)
    findings = refs.check_input_dispositions(run)
    assert len(findings) == 1, [str(f) for f in findings]
    assert dropped_row["artifact_id"] in findings[0].message
    assert findings[0].artifact == path


def test_a_row_for_an_artifact_the_manifest_does_not_name_is_reported(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    path, part = _rows(run)
    part["inputs_seen"].append(
        {"artifact_id": "no-such-input", "own_kind_total": 0, "cited": 0, "dropped": 0}
    )
    write_json(path, part)
    findings = refs.check_input_dispositions(run)
    assert len(findings) == 1, [str(f) for f in findings]
    assert "no-such-input" in findings[0].message


def test_an_own_kind_total_that_disagrees_with_the_claims_file_is_reported(tmp_path):
    """Recomputed from 01-claims/, not taken on trust.

    A declared own_kind_total that disagrees with the claims file is a finding.
    That is a weaker property than it looks: a right count is not evidence of a
    read, and check_input_dispositions' docstring records the three routes to
    one without opening the file. What the test pins is the disagreement.
    """
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    path, part = _rows(run)
    row = next(r for r in part["inputs_seen"] if r["own_kind_total"])
    row["own_kind_total"] += 1
    row["dropped"] += 1
    row["note"] = "a number this pass did not measure"
    write_json(path, part)
    findings = refs.check_input_dispositions(run)
    assert len(findings) == 1, [str(f) for f in findings]
    assert "own_kind_total" in findings[0].message


def test_a_cited_count_that_disagrees_with_the_part_is_reported(tmp_path):
    """Recomputed from the part's own claims arrays, nested ones included."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    path, part = _rows(run)
    row = next(r for r in part["inputs_seen"] if r["cited"])
    row["cited"] -= 1
    row["dropped"] += 1
    row["note"] = "a flattering count in the other direction"
    write_json(path, part)
    findings = refs.check_input_dispositions(run)
    assert len(findings) == 1, [str(f) for f in findings]
    assert "cited" in findings[0].message


def test_arithmetic_that_does_not_close_is_reported(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    path, part = _rows(run)
    row = next(r for r in part["inputs_seen"] if r["own_kind_total"])
    row["dropped"] += 1
    row["note"] = "one more drop than there are claims to drop"
    write_json(path, part)
    findings = refs.check_input_dispositions(run)
    assert len(findings) == 1, [str(f) for f in findings]
    assert "cited + dropped" in findings[0].message


def test_a_non_integer_count_reports_rather_than_raising(tmp_path):
    """A malformed count is layer 1's finding, but layer 2 must survive reading it.

    check_all has no ordering guarantee that layer 1 rejected the document first.
    Measured before the arithmetic clause was guarded: `"cited": "2"` in
    01-outcomes.json raised `TypeError: can only concatenate str (not "int") to
    str`, which cli.py converts into exit 1 with one generic `[internal]` finding
    -- every other real finding in the run lost, and nothing naming the artifact
    to repair. The guard is on that clause alone, so the two recomputations above
    it still report: silence here would be the other half of the same defect.
    """
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    path, part = _rows(run)
    row = next(r for r in part["inputs_seen"] if r["cited"])
    row["cited"] = str(row["cited"])
    write_json(path, part)
    findings = refs.check_input_dispositions(run)
    assert [f.pointer for f in findings] == [f"/inputs_seen/{part['inputs_seen'].index(row)}/cited"]


def test_a_deleted_claims_file_is_not_this_checkers_finding(tmp_path):
    """A `1` must name the right artifact.

    check-refs over an unreadable 01-claims/ once produced four fabricated
    "no such claim" findings against a correct world model. A missing claims
    file counts as zero here and stays the finding of the checker that owns it,
    so this one reports the count disagreement it genuinely sees and nothing
    about the absence.
    """
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    (run.claims_dir / "trace-json.json").unlink()
    findings = refs.check_input_dispositions(run)
    # The exact set, not just "some finding and no forbidden one": the two
    # negatives below hold identically for a variant that emitted a *differently
    # worded* absence finding anchored on 01-claims/, which is the thing this test
    # names as forbidden. Measured: exactly two, both against the outcomes part,
    # because trace-json is the only input whose own-kind claims any pass cited.
    # The row's own arithmetic still closes (2 = 1 + 1), so the third clause is
    # silent -- a row can be internally consistent and still be about a file that
    # is gone, which is why the recomputation is the instrument and the
    # arithmetic is only bookkeeping on top of it.
    assert len(findings) == 2, [str(f) for f in findings]
    assert [(f.artifact, f.pointer) for f in findings] == [
        (run.outcomes_part, "/inputs_seen/2/own_kind_total"),
        (run.outcomes_part, "/inputs_seen/2/cited"),
    ], [str(f) for f in findings]
    assert all("no such claim" not in f.message for f in findings)
    assert all(f.artifact != run.claims_dir for f in findings)


def test_check_all_reaches_this_checker(tmp_path):
    """check_all runs every checker the run has inputs for, so a checker that is
    written but not wired in is invisible to `rubrica check-refs`."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    path, part = _rows(run)
    part["inputs_seen"].append(
        {"artifact_id": "input-invented-999", "own_kind_total": 0, "cited": 0, "dropped": 0}
    )
    write_json(path, part)
    assert any("input-invented-999" in f.message for f in refs.check_all(run))


def test_a_row_that_cited_nothing_is_not_a_finding_when_the_arithmetic_holds(tmp_path):
    """own_kind_total > 0 and cited == 0 is deliberately not a finding.

    The row already carries a required note, so the drop is on the record.
    Making it a finding would fail a repair round that cannot repair anything,
    and would put a coverage judgment behind an exit code -- the threshold
    check_claim_utilisation refuses on measurement: run-20260812-130056 had 130
    of 287 claims uncited and almost all of those drops were correct.

    So this moves api-json's outcome-class citations onto notes-md's claim and
    restates the row honestly. The pass has now cited nothing from api-json and
    said why, and that is a clean artifact.
    """
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    path, part = _rows(run)
    for record in part["outcomes"]:
        for outcome_class in record["outcome_classes"]:
            outcome_class["claims"] = ["clm-notes-004"]
    for row in part["inputs_seen"]:
        if row["artifact_id"] == "api-json":
            row.update(
                {
                    "cited": 0,
                    "dropped": row["own_kind_total"],
                    "note": "both restated by clm-notes-004, which is stated rather than "
                    "reverse_engineered",
                }
            )
        elif row["artifact_id"] == "notes-md":
            row.update({"cited": 1, "dropped": 0})
        elif row["artifact_id"] == "trace-json":
            row.update({"cited": 0, "dropped": 2, "note": "superseded by clm-notes-004"})
    write_json(path, part)
    assert refs.check_input_dispositions(run) == [], [
        str(f) for f in refs.check_input_dispositions(run)
    ]


def test_a_non_dict_partial_is_skipped_rather_than_raised_through(tmp_path):
    """The `part` read this branch added, guarded on the shape rather than on None.

    `_load` returns whatever the document holds, so a partial that is a list or a
    string reached `part.get` and raised AttributeError out of layer 2 -- measured
    at that line, for `["nope"]` in each of the four partials. `cli.py`'s catch-all
    takes that to exit 1 with one `[internal]` finding naming the run root instead
    of an artifact, which is the specificity half of the exit-code rule.

    `01-entities.json` and `01-goals.json` are the ones that matter, and they are
    asserted alongside the other pair rather than instead of them: no other
    layer-2 checker reads either, so before the guard this function was the sole
    raiser and there was nothing older to blame. `01-services.json` was the third
    such case and the deepest of them when this was written, because
    `reconcile-seal` does not read it either -- for the other two the seal would
    refuse a broken partial afterwards, and for this one nothing below did. It has
    readers on both sides now: `synthesise-interfaces` refuses a non-dict one by
    name, and `refs.check_services` guards the same read the same way, so this
    function is no longer its sole raiser. It stays asserted here regardless,
    since this checker still runs first and a raise here would still name the run
    root. `check_outcomes`
    runs earlier in `check_all` and still raises on
    a non-dict `01-capabilities.json` or `01-outcomes.json`, which is why the
    assertion here is against this checker rather than against `check_all` -- the
    register carries the ruling on the reads this branch did not add.
    """
    for attribute in (
        "entities_part",
        "goals_part",
        "services_part",
        "capabilities_part",
        "outcomes_part",
    ):
        run = build_toy_run(tmp_path / attribute, upto="reconcile-seal")
        getattr(run, attribute).write_text('["nope"]', encoding="utf-8")
        findings = refs.check_input_dispositions(run)
        # Every other pass still gets recomputed: skipping the unreadable partial
        # must not skip the loop. A guard that returned [] outright would satisfy
        # a bare "does not raise" assertion while deleting the instrument.
        assert all(f.artifact != getattr(run, attribute) for f in findings), findings
        assert findings == [], [str(f) for f in findings]

    # And the control, from the other direction: with the *rows* of one partial
    # made unreadable rather than the partial itself, the loop's other passes are
    # demonstrably still being checked, so the empty list above is a clean run
    # rather than a silenced one.
    run = build_toy_run(tmp_path / "control", upto="reconcile-seal")
    run.entities_part.write_text('["nope"]', encoding="utf-8")
    path, part = _rows(run)
    part["inputs_seen"][0]["own_kind_total"] = 99
    write_json(path, part)
    # Two findings, not one: bumping own_kind_total also stops the row's
    # arithmetic closing, so the third clause reports as well. Both name the
    # outcomes part, which is the point -- the unreadable entities part did not
    # stop the loop.
    assert [(f.artifact, f.pointer) for f in refs.check_input_dispositions(run)] == [
        (run.outcomes_part, "/inputs_seen/0/own_kind_total"),
        (run.outcomes_part, "/inputs_seen/0"),
    ]
