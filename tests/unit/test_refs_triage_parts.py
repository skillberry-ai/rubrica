"""refs.check_disposition_parts, check_objective, check_audit: the three
layer-2 checkers over staged-triage's prompt-pass outputs, added alongside
check_slices (which already covers 00-slices.json against the catalogue).

Every mutation test edits exactly the artifact(s) its own defect lives in,
_staged_run's hand-written objective/parts/audit otherwise held fixed, so a
finding is attributable to the one thing that changed -- the same discipline
test_refs_slices.py and test_seal.py use.
"""

from __future__ import annotations

from rubrica import refs
from rubrica.artifacts import read_json, write_json
from tests.unit.test_seal import _staged_run

# ---------------------------------------------------------------------------
# check_disposition_parts
# ---------------------------------------------------------------------------


def _staged_run_with_correct_weights(tmp_path):
    """_staged_run's hand-written objective hardcodes weight.bytes against
    byte counts that do not match the toy fixture's actual candidates
    (measured here: notes-md=898, api-json=1231, trace-json=318, not the
    1303/2381/418 test_seal.py's own comment claims). seal.py never checks
    weight arithmetic -- it copies objective_review verbatim -- so that
    mismatch was invisible until check_objective existed to notice it.
    Corrected here, in this module, rather than in test_seal.py's own copy:
    Task 9's fixture and its tests are not mine to change, and this task's
    "clean run reports nothing" baseline needs a run that is actually clean
    by the arithmetic this checker recomputes.
    """
    run = _staged_run(tmp_path)
    catalogue = {c["candidate_id"]: c for c in read_json(run.catalogue)["candidates"]}
    doc = read_json(run.objective)
    for surface in doc["objective_review"]["surfaces"]:
        surface["weight"]["bytes"] = sum(catalogue[cid]["bytes"] for cid in surface["evidence"])
    write_json(run.objective, doc)
    return run


def test_a_clean_staged_run_reports_nothing_for_disposition_parts(tmp_path):
    assert refs.check_disposition_parts(_staged_run(tmp_path)) == []


def test_an_absent_dispositions_dir_reports_nothing(tmp_path):
    """A run before the dispositions fan-out has nothing to check here."""
    run = _staged_run(tmp_path)
    for part in run.dispositions_dir.iterdir():
        part.unlink()
    run.dispositions_dir.rmdir()
    assert refs.check_disposition_parts(run) == []


def test_an_unreadable_slices_plan_is_one_finding_not_a_traceback(tmp_path):
    run = _staged_run(tmp_path)
    run.slices.write_text("{not json", encoding="utf-8")
    findings = refs.check_disposition_parts(run)
    assert len(findings) == 1
    assert findings[0].artifact == run.slices


def test_disposition_parts_reports_every_missing_part_mid_fan_out(tmp_path):
    """The check_verdicts caveat, pinned rather than merely documented."""
    run = _staged_run(tmp_path)
    parts = sorted(run.dispositions_dir.iterdir())
    for p in parts[1:]:
        p.unlink()
    findings = refs.check_disposition_parts(run)
    assert len(findings) == len(parts) - 1


def test_an_unreadable_part_is_one_finding_naming_that_part(tmp_path):
    """Continuing past a parse failure would fabricate findings against
    candidates the failed part never let this checker actually see -- the
    module docstring's 01-claims/ incident, replayed for a disposition part.
    Isolated to a slice with no cross-slice/adoption entanglement (s01,
    notes-md) so nothing else this checker reads is disturbed."""
    run = _staged_run(tmp_path)
    run.disposition_part("s01").write_text("{not json", encoding="utf-8")
    findings = refs.check_disposition_parts(run)
    assert len(findings) == 1
    assert findings[0].artifact == run.disposition_part("s01")


def test_a_disposition_naming_a_candidate_outside_its_slice_is_reported(tmp_path):
    """Appends a rogue entry naming a candidate that belongs to no slice at
    all (never minted in the catalogue), rather than moving an existing
    entry -- moving one would also either duplicate an already-ruled
    candidate or strip the origin candidate's own coverage, tripping a
    second, unrelated check (the same entanglement seal.py's own analogous
    test tolerates with `any(...)` rather than `len(findings) == 1`)."""
    run = _staged_run(tmp_path)
    part = run.disposition_part("s01")
    doc = read_json(part)
    doc["dispositions"].append(
        {
            "candidate_id": "ghost",
            "disposition": "admit",
            "reason": "wrongly claimed by the wrong slice",
            "priority": 2,
            "authority": "triage",
        }
    )
    write_json(part, doc)
    findings = refs.check_disposition_parts(run)
    assert len(findings) == 1
    assert "ghost" in findings[0].message and "not in slice" in findings[0].message


def test_a_candidate_ruled_twice_within_one_part_is_reported(tmp_path):
    """Duplicated within the *same* part's own array, so the duplicate stays
    in-slice and cannot also trip the not-in-slice check above."""
    run = _staged_run(tmp_path)
    part = run.disposition_part("s01")
    doc = read_json(part)
    doc["dispositions"].append(dict(doc["dispositions"][0]))
    write_json(part, doc)
    findings = refs.check_disposition_parts(run)
    assert len(findings) == 1
    assert "notes-md" in findings[0].message and "more than one disposition" in findings[0].message


def test_an_uncovered_catalogue_candidate_is_reported(tmp_path):
    """A candidate minted into the catalogue after slicing (the shape
    adopt_projection produces) with no adoption naming it: no slice's
    candidate_ids ever claimed it, and nothing rules on it, so the union of
    parts and adoptions does not cover the catalogue."""
    run = _staged_run(tmp_path)
    catalogue = read_json(run.catalogue)
    catalogue["candidates"].append(
        {"candidate_id": "orphan-cand", "origin": "projection", "admissible": True}
    )
    write_json(run.catalogue, catalogue)
    findings = refs.check_disposition_parts(run)
    assert len(findings) == 1
    assert "orphan-cand" in findings[0].message and "no disposition" in findings[0].message


def test_an_adopted_orphan_candidate_is_not_reported(tmp_path):
    """The other half of the same rule: an adoption naming the same orphan
    candidate is what the union clause exists to accept."""
    run = _staged_run(tmp_path)
    catalogue = read_json(run.catalogue)
    catalogue["candidates"].append(
        {"candidate_id": "orphan-cand", "origin": "projection", "admissible": True}
    )
    write_json(run.catalogue, catalogue)
    write_json(
        run.adoptions,
        {
            "schema_version": "0.1",
            "run_id": catalogue["run_id"],
            "adoptions": [
                {
                    "candidate_id": "orphan-cand",
                    "disposition": {
                        "candidate_id": "orphan-cand",
                        "disposition": "admit",
                        "reason": "structural acceptance passed",
                        "authority": "human",
                    },
                    "projection_id": "prj-1",
                    "closed_deficiency_ids": ["def-1"],
                }
            ],
        },
    )
    assert refs.check_disposition_parts(run) == []


def test_an_unreadable_adoptions_file_is_one_finding(tmp_path):
    run = _staged_run(tmp_path)
    run.adoptions.write_text("{not json", encoding="utf-8")
    findings = refs.check_disposition_parts(run)
    assert len(findings) == 1
    assert findings[0].artifact == run.adoptions


# ---------------------------------------------------------------------------
# check_objective
# ---------------------------------------------------------------------------


def test_a_clean_staged_run_reports_nothing_for_objective(tmp_path):
    assert refs.check_objective(_staged_run_with_correct_weights(tmp_path)) == []


def test_an_absent_objective_reports_nothing(tmp_path):
    run = _staged_run(tmp_path)
    run.objective.unlink()
    assert refs.check_objective(run) == []


def test_an_unreadable_objective_is_one_finding_not_a_traceback(tmp_path):
    run = _staged_run(tmp_path)
    run.objective.write_text("{not json", encoding="utf-8")
    findings = refs.check_objective(run)
    assert len(findings) == 1
    assert findings[0].artifact == run.objective


def test_an_evidence_id_that_does_not_resolve_is_reported(tmp_path):
    """Weight is skipped once evidence fails to resolve (Lessons: isolate the
    mutation to one invariant) -- the weight of a broken evidence list is not
    a second, independent defect."""
    run = _staged_run_with_correct_weights(tmp_path)
    doc = read_json(run.objective)
    doc["objective_review"]["surfaces"][0]["evidence"] = ["ghost"]
    write_json(run.objective, doc)
    findings = refs.check_objective(run)
    assert len(findings) == 1
    assert "ghost" in findings[0].message and "no such candidate" in findings[0].message


def test_a_surface_weight_that_is_not_arithmetic_is_reported(tmp_path):
    run = _staged_run_with_correct_weights(tmp_path)
    doc = read_json(run.objective)
    doc["objective_review"]["surfaces"][0]["weight"]["candidates"] += 3
    write_json(run.objective, doc)
    findings = refs.check_objective(run)
    assert any("weight" in f.message for f in findings)
    assert len(findings) == 1, "candidates-only mutation must not also trip the bytes check"


def test_a_surface_bytes_that_are_not_arithmetic_is_reported(tmp_path):
    """The other half of clause 2 -- bytes mutated alone, candidates left
    correct, isolating the bytes arithmetic from the candidates arithmetic."""
    run = _staged_run_with_correct_weights(tmp_path)
    doc = read_json(run.objective)
    doc["objective_review"]["surfaces"][0]["weight"]["bytes"] += 100
    write_json(run.objective, doc)
    findings = refs.check_objective(run)
    assert len(findings) == 1
    assert "weight.bytes" in findings[0].message


# ---------------------------------------------------------------------------
# check_audit
# ---------------------------------------------------------------------------


def test_a_clean_staged_run_reports_nothing_for_audit(tmp_path):
    assert refs.check_audit(_staged_run(tmp_path)) == []


def test_an_absent_audit_reports_nothing(tmp_path):
    run = _staged_run(tmp_path)
    run.audit.unlink()
    assert refs.check_audit(run) == []


def test_an_unreadable_audit_is_one_finding_not_a_traceback(tmp_path):
    run = _staged_run(tmp_path)
    run.audit.write_text("{not json", encoding="utf-8")
    findings = refs.check_audit(run)
    assert len(findings) == 1
    assert findings[0].artifact == run.audit


def test_a_digest_insufficient_decline_with_no_deficiency_is_reported(tmp_path):
    run = _staged_run(tmp_path)
    part = sorted(run.dispositions_dir.iterdir())[0]
    doc = read_json(part)
    doc["dispositions"][0] |= {
        "disposition": "decline",
        "reason_code": "digest_insufficient",
        "reason": "no result shape in the digest",
    }
    doc["dispositions"][0].pop("priority", None)
    write_json(part, doc)
    findings = refs.check_audit(run)
    assert any("digest_insufficient" in f.message for f in findings)
    assert len(findings) == 1, "s01's own empty deficiency_notes is the only thing mutated"


def test_a_needs_projection_decline_with_no_projection_is_reported(tmp_path):
    """Isolated by re-pointing the fixture's one projection's one source away
    from trace-json -- projected_candidate_ids is built from exactly that
    field and nothing else, mirroring seal.py's own analogous test."""
    run = _staged_run(tmp_path)
    audit = read_json(run.audit)
    audit["projections"][0]["sources"][0]["candidate_id"] = "notes-md"
    write_json(run.audit, audit)
    findings = refs.check_audit(run)
    assert len(findings) == 1
    assert "needs_projection" in findings[0].message and "trace-json" in findings[0].message


def test_a_closes_naming_no_such_deficiency_is_reported(tmp_path):
    run = _staged_run(tmp_path)
    audit = read_json(run.audit)
    audit["projections"][0]["closes"] = ["ghost-def"]
    write_json(run.audit, audit)
    findings = refs.check_audit(run)
    assert len(findings) == 1
    assert "ghost-def" in findings[0].message and "no such deficiency" in findings[0].message


def test_an_unreadable_part_is_one_finding_when_checking_audit(tmp_path):
    run = _staged_run(tmp_path)
    run.disposition_part("s01").write_text("{not json", encoding="utf-8")
    findings = refs.check_audit(run)
    assert len(findings) == 1
    assert findings[0].artifact == run.disposition_part("s01")


def test_an_absent_dispositions_dir_skips_decline_checks_but_not_closes(tmp_path):
    """A hand-assembled audit with no staged parts behind it still gets its
    own closes clause checked; only the clauses that read the parts skip."""
    run = _staged_run(tmp_path)
    audit = read_json(run.audit)
    audit["projections"][0]["closes"] = ["ghost-def"]
    write_json(run.audit, audit)
    for part in run.dispositions_dir.iterdir():
        part.unlink()
    run.dispositions_dir.rmdir()
    findings = refs.check_audit(run)
    assert len(findings) == 1
    assert "no such deficiency" in findings[0].message
