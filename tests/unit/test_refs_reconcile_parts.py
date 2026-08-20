"""Layer 2 over the reconcile partials.

Each checker is measured in both directions: red on the defect it names, and green
on a clean run. A predicate nobody has watched fail is not yet a guard.
"""

from __future__ import annotations

import os

import pytest

from rubrica import refs
from rubrica.artifacts import read_json, write_json
from rubrica.cli import main
from tests.toy import build_toy_run, split_world_model


def _seeded(tmp_path):
    run = build_toy_run(tmp_path, upto="extract")
    parts = split_world_model()
    write_json(run.subjects, parts["subjects"])
    write_json(run.capabilities_part, parts["capabilities"])
    write_json(run.outcomes_part, parts["outcomes"])
    for subject_id, part in parts["contradictions"].items():
        write_json(run.contradiction_part(subject_id), part)
    return run, parts


def test_a_complete_cover_is_clean(tmp_path):
    run, _ = _seeded(tmp_path)
    assert refs.check_subjects(run) == []


def test_an_absent_cover_is_not_a_finding(tmp_path):
    """A pass that has not run yet is validate_stage's finding, not this one's --
    the rule every checker in this module follows."""
    run = build_toy_run(tmp_path, upto="extract")
    assert refs.check_subjects(run) == []


def test_absent_partials_are_not_findings(tmp_path):
    """The same rule for the other two checkers, and for each half of the pair
    check_outcomes needs. check_all runs over a run at whatever stage it has
    reached, so a checker that reported absence would be permanently dirty from
    extract onward and no repair could clear it.
    """
    run = build_toy_run(tmp_path, upto="extract")
    assert refs.check_contradiction_parts(run) == []
    assert refs.check_outcomes(run) == []

    parts = split_world_model()
    # A cover with no parts directory yet: the contradict fan-out has not been
    # dispatched at all. Reporting every subject as unvisited here would spend the
    # orchestrator's single repair attempt on a phantom -- check_verdicts' reason
    # for guarding on is_dir(), and the reason this guard is is_dir() too rather
    # than a count. Once the directory exists the window is *not* tolerated, which
    # is what test_a_subject_with_no_part_is_reported measures.
    write_json(run.subjects, parts["subjects"])
    assert refs.check_contradiction_parts(run) == []
    # And one half of the capabilities/outcomes pair without the other: the passes
    # are separate dispatches, so between them exactly this state is on disk.
    write_json(run.capabilities_part, parts["capabilities"])
    assert refs.check_outcomes(run) == []


def test_a_claim_no_subject_covers_is_reported(tmp_path):
    run, parts = _seeded(tmp_path)
    dropped = parts["subjects"]["subjects"][0]["claims"].pop()
    write_json(run.subjects, parts["subjects"])

    findings = refs.check_subjects(run)

    assert any(dropped in f.message for f in findings), (
        "totality is the property that makes the cover acceptable where a pair filter was not"
    )


def test_a_subject_citing_an_unextracted_claim_is_reported(tmp_path):
    run, parts = _seeded(tmp_path)
    parts["subjects"]["subjects"][0]["claims"].append("clm-invented-999")
    write_json(run.subjects, parts["subjects"])
    assert any("clm-invented-999" in f.message for f in refs.check_subjects(run))


def test_a_duplicate_subject_id_is_reported(tmp_path):
    run, parts = _seeded(tmp_path)
    parts["subjects"]["subjects"].append(dict(parts["subjects"]["subjects"][0]))
    write_json(run.subjects, parts["subjects"])
    assert any("duplicate" in f.message for f in refs.check_subjects(run))


def test_every_subject_visited_is_clean(tmp_path):
    run, _ = _seeded(tmp_path)
    assert refs.check_contradiction_parts(run) == []


def test_a_subject_with_no_part_is_reported(tmp_path):
    run, parts = _seeded(tmp_path)
    subject_id = next(iter(parts["contradictions"]))
    run.contradiction_part(subject_id).unlink()
    assert any(subject_id in f.message for f in refs.check_contradiction_parts(run))


def test_a_part_for_an_undeclared_subject_is_reported(tmp_path):
    run, _ = _seeded(tmp_path)
    write_json(
        run.contradiction_part("sub-invented"),
        {"schema_version": "0.1", "subject_id": "sub-invented", "contradictions": []},
    )
    assert any("sub-invented" in f.message for f in refs.check_contradiction_parts(run))


def test_a_part_whose_subject_id_disagrees_with_its_filename_is_reported(tmp_path):
    """The filename is what the fan-out was dispatched with; the field is what the
    member believed it was working on. A mismatch means one member wrote another's
    slice, which is the failure the fourth dispatch argument exists to prevent."""
    run, parts = _seeded(tmp_path)
    subject_id = next(iter(parts["contradictions"]))
    part = read_json(run.contradiction_part(subject_id))
    part["subject_id"] = "sub-somebody-else"
    write_json(run.contradiction_part(subject_id), part)
    assert any("sub-somebody-else" in f.message for f in refs.check_contradiction_parts(run))


def test_a_contradiction_naming_an_unextracted_claim_is_reported(tmp_path):
    run, parts = _seeded(tmp_path)
    subject_id, part = next(
        (sid, p) for sid, p in parts["contradictions"].items() if p["contradictions"]
    )
    part["contradictions"][0]["claim_a"] = "clm-invented-999"
    write_json(run.contradiction_part(subject_id), part)
    assert any("clm-invented-999" in f.message for f in refs.check_contradiction_parts(run))


def test_matched_capabilities_and_outcomes_are_clean(tmp_path):
    run, _ = _seeded(tmp_path)
    assert refs.check_outcomes(run) == []


def test_a_capability_with_no_outcome_record_is_reported(tmp_path):
    run, parts = _seeded(tmp_path)
    parts["outcomes"]["outcomes"] = parts["outcomes"]["outcomes"][:1]
    write_json(run.outcomes_part, parts["outcomes"])
    findings = refs.check_outcomes(run)
    assert findings, "an unswept capability shrinks the denominator silently"


def test_an_outcome_record_for_an_unknown_capability_is_reported(tmp_path):
    run, parts = _seeded(tmp_path)
    parts["outcomes"]["outcomes"].append(
        {
            "capability_id": "cap-invented",
            "outcome_classes": [{"id": "oc-x", "kind": "success", "description": "x"}],
        }
    )
    write_json(run.outcomes_part, parts["outcomes"])
    assert any("cap-invented" in f.message for f in refs.check_outcomes(run))


def test_check_all_reaches_the_new_checkers(tmp_path):
    """check_all runs every checker the run has inputs for, so a checker that is
    written but not wired in is invisible to `rubrica check-refs`."""
    run, parts = _seeded(tmp_path)
    parts["subjects"]["subjects"][0]["claims"].append("clm-invented-999")
    write_json(run.subjects, parts["subjects"])
    assert any("clm-invented-999" in f.message for f in refs.check_all(run))


def test_an_unparseable_partial_short_circuits_everything_below_it(tmp_path):
    """check_readable must name the broken partial and stop. Continuing produces
    findings that blame artifacts which are fine -- and the orchestrator's single
    repair attempt then rewrites the wrong file."""
    run, _ = _seeded(tmp_path)
    run.subjects.write_text("{not json", encoding="utf-8")
    findings = refs.check_all(run)
    assert len(findings) == 1
    assert "01-subjects.json" in str(findings[0].artifact)


def test_a_malformed_contradictions_part_is_named_and_short_circuits(tmp_path):
    """The fan-out directory's own entry in _readable_targets, measured.

    Nothing else reports this. check_contradiction_parts' _load treats an
    unparseable part as absent, while its filename still counts as on disk, so
    with 01-contradictions/ missing from the target list check_all comes back
    *clean* over a part it could not read -- measured, by deleting that line. A
    check announcing "nothing wrong" because its input was unreadable is the
    incident the whole list exists to prevent.
    """
    run, parts = _seeded(tmp_path)
    subject_id = next(iter(parts["contradictions"]))
    path = run.contradiction_part(subject_id)
    path.write_text('{"schema_version": "0.1", "subject', encoding="utf-8")

    findings = refs.check_all(run)

    assert len(findings) == 1, [str(f) for f in findings]
    assert findings[0].artifact == path


# -- the additions to the brief's list -------------------------------------
#
# Three properties the brief's cases do not reach: a part filename that is not a
# usable subject id, and the two unreadable-input shapes the exit-code contract
# turns on. All three are shapes this repo has been burned by before, which is
# why they are measured here rather than assumed.


def test_a_badly_named_part_is_an_ordinary_finding(tmp_path):
    """A part filename that cannot be a subject id is exit 1, not exit 2.

    paths.subject_part_ids() drops it from the listing and
    unsafe_contradiction_part_names() hands it here, mirroring
    scenario_ids_with_instances / unsafe_instance_dir_names. Without that pairing
    the name reaches contradiction_part(), raises UnsafeSegment, and cli.py maps
    it to exit 2 -- misreporting a repairable stage defect as a misconfigured
    harness and discarding every other finding in the run.
    """
    run, _ = _seeded(tmp_path)
    (run.contradictions_dir / "subject 1.json").write_text(
        '{"schema_version": "0.1", "subject_id": "sub-x", "contradictions": []}',
        encoding="utf-8",
    )

    findings = refs.check_contradiction_parts(run)

    # Reported *as* a name problem, not as a subject the cover forgot: the
    # message has to send a repair at the filename.
    assert any("subject 1" in f.message and "subject id" in f.message for f in findings), [
        f.message for f in findings
    ]
    # Exactly one, which pins the is_safe_segment guard on the filename/field
    # comparison. Without it the same file also draws "declares subject_id
    # 'sub-x' but is the part for 'subject 1'" -- a second finding that restates
    # the first and does it with a false clause, since an unusable stem is not
    # the subject any file belongs to.
    assert len(findings) == 1, [f.message for f in findings]


@pytest.mark.parametrize(
    "attribute",
    ["subjects", "capabilities_part", "outcomes_part", "entities_part", "goals_part", "gaps_part"],
)
def test_every_partial_added_to_the_readable_list_is_named(tmp_path, attribute):
    """The list is only as good as its enumeration, so break each entry in turn.

    Three of these -- entities, goals, gaps -- have no layer-2 checker reading
    them at all; their entry is what makes a truncated one a named finding
    instead of silence that reconcile-seal walks into later.

    tests/unit/test_refs_readable.py owns this completeness loop for every other
    artifact kind, but its loop reads each target *before* breaking it, so it
    cannot hold a partial until build_toy_run writes one. Held here meanwhile.
    """
    run, parts = _seeded(tmp_path)
    write_json(run.entities_part, parts["entities"])
    write_json(run.goals_part, parts["goals"])
    write_json(run.gaps_part, parts["gaps"])
    path = getattr(run, attribute)
    path.write_text("{", encoding="utf-8")
    assert [f.artifact for f in refs.check_readable(run)] == [path]


@pytest.mark.skipif(
    os.geteuid() == 0, reason="chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)"
)
@pytest.mark.parametrize("mode", [0o000, 0o444])
def test_an_unreadable_contradictions_dir_is_exit_2_not_a_finding(tmp_path, capsys, mode):
    """A run directory the harness cannot read is a misconfiguration, not a defect.

    Both modes, because they are different code paths: at 0o000 the listing
    itself fails, at 0o444 the listing succeeds and stat'ing a child fails. The
    shape matters because `Path.glob` swallows EACCES -- an unreadable
    01-claims/ once made check-refs report four `no such claim` findings against
    a correct world model, and the same hole here would have
    check_contradiction_parts report every subject as unvisited.
    """
    run, _ = _seeded(tmp_path)
    run.contradictions_dir.chmod(mode)
    try:
        code = main(["check-refs", "--run", str(run.root)])
    finally:
        run.contradictions_dir.chmod(0o755)
    captured = capsys.readouterr()
    assert code == 2, captured.out
    assert captured.out.strip() == "", "a filesystem problem must not print a finding line"
    assert captured.err.startswith("error: ")


@pytest.mark.skipif(
    os.geteuid() == 0, reason="chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)"
)
def test_an_unreadable_partial_file_is_exit_2_not_a_finding(tmp_path, capsys):
    """The file exists and is well-formed; the process may not read it.

    read_json raises PermissionError rather than ArtifactError there, so this is
    not the malformed-JSON path above: it lands on cli.py's OSError arm, which is
    exit 2. Asserted because the alternative -- _load swallowing it as absence --
    is the incident the whole readable-targets list exists to prevent, and adding
    a partial to that list is only useful if the unreadable case still reaches it.
    """
    run, _ = _seeded(tmp_path)
    run.subjects.chmod(0o000)
    try:
        code = main(["check-refs", "--run", str(run.root)])
    finally:
        run.subjects.chmod(0o644)
    captured = capsys.readouterr()
    assert code == 2, captured.out
    assert captured.out.strip() == "", "a filesystem problem must not print a finding line"
    assert captured.err.startswith("error: ")
