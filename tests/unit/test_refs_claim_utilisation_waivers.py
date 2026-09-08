"""The zero-citation finding, and the human waiver that clears its exit code.

The finding names `01-world-model.json`, which no dispatchable stage declares in
`writes`, so the orchestrator's one repair attempt is unspendable on it. A human's
waiver is how that ruling gets recorded: the finding keeps printing, prefixed
`[waived] `, and only its contribution to the exit code goes away.
"""

from __future__ import annotations

import json

from rubrica import refs
from rubrica.cli import main
from tests.toy import build_toy_run
from tests.unit.test_utilisation import _blank_world_model_claim_refs

# The toy input `_uncited` makes uncited, and therefore the `subject` most waivers
# here name. api-json specifically: measured, it is the only one of the toy's three
# inputs that stripping the world model's citation sites leaves at zero, because
# notes-md and trace-json are also cited through `contradictions`, which
# utilisation._cited_claim_ids counts.
SUBJECT = "api-json"


def _waive(run, subject, check="claim-utilisation"):
    run.waivers.write_text(
        json.dumps(
            {
                # `schema_version`, not `version`: waivers.load schema-validates and
                # raises UsageError on a violation, so a fixture keyed the old way
                # would exercise the exit-2 path rather than the behaviour under test.
                "schema_version": "0.1",
                "waivers": [
                    {
                        "id": "wv-0001",
                        "check": check,
                        "subject": subject,
                        "remedy": "triage-rule",
                        "reason": "out of the target's domain; every pass declined it",
                        "finding_text": "recorded verbatim by `rubrica waive`",
                        "recorded_at": "2026-09-08T04:12:33Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _uncited(run):
    """Give the run a registered input whose claims nothing in the world model cites.

    A registered input stripped of its citations rather than a new claims file: an
    unregistered claims file is a *second* finding of its own (check_manifest's
    "not registered in the manifest"), which no waiver here covers, so the exit-0
    assertion below could not hold for a reason that has nothing to do with waivers.
    """
    _blank_world_model_claim_refs(run, SUBJECT)


def _orphan(run, artifact_id):
    """A well-formed claims file nothing cites, for a *second* uncited subject.

    Well-formed matters: refs.check_manifest indexes `claim["evidence"]` directly,
    so a claim without it raises KeyError before claim_utilisation is reached at
    all. Its evidence cites a registered artifact, so beside the zero-citation
    finding these tests are about it adds exactly two more, both measured:
    check_manifest's "artifact_id 'orphan' is not registered in the manifest" and
    check_subjects' "no subject covers claim clm-orphan-001". Both are unwaived and
    unwaivable, which is what the one test using this helper needs.
    """
    (run.claims_dir / f"{artifact_id}.json").write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "artifact_id": artifact_id,
                "claims": [
                    {
                        "id": f"clm-{artifact_id}-001",
                        "kind": "actor",
                        "confidence": "high",
                        "derivation": "stated",
                        "statement": "an actor no world-model element cites",
                        "evidence": [{"artifact_id": SUBJECT, "locator": "#/tools/0"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _by_subject(run):
    """The pairs as a mapping, so a test never has to match a subject in prose."""
    return dict(refs.claim_utilisation_findings(run))


def test_an_uncited_artifact_is_a_finding(tmp_path):
    """The behaviour that must not change: without a waiver this is still a
    finding, and still names the world model."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    found = refs.check_claim_utilisation(run)
    assert len(found) == 1, found
    assert set(_by_subject(run)) == {SUBJECT}
    assert all(not f.waived for f in found)
    assert all(f.artifact == run.world_model for f in found)


def test_a_waiver_marks_that_finding_waived(tmp_path):
    run = build_toy_run(tmp_path)
    _uncited(run)
    _waive(run, SUBJECT)
    found = _by_subject(run)
    assert found[SUBJECT].waived


def test_a_waiver_for_a_different_subject_does_not_suppress(tmp_path):
    """The narrowness property. A waiver is for one subject, not for the check."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    _waive(run, "some-other-artifact")
    found = _by_subject(run)
    assert not found[SUBJECT].waived


def test_a_waiver_for_a_different_check_does_not_suppress(tmp_path):
    """The other half of the `(check, subject)` key: the right subject recorded
    under a check name nothing here reads is inert."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    _waive(run, SUBJECT, check="check-manifest")
    found = _by_subject(run)
    assert not found[SUBJECT].waived


def test_a_waiver_does_not_reach_a_subject_it_is_only_a_prefix_of(tmp_path):
    """Why the subject travels beside the finding instead of being read back out
    of its message: `"api-json" in "...any claim from api-json2 (1 claims)"` is
    True, so a substring match over the prose would waive the wrong artifact."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    _orphan(run, f"{SUBJECT}2")
    _waive(run, SUBJECT)
    found = _by_subject(run)
    assert found[SUBJECT].waived
    assert not found[f"{SUBJECT}2"].waived


def test_the_subject_travels_beside_the_finding(tmp_path):
    """The accessor's contract: one pair per finding, keyed on the artifact id
    `rubrica waive` will be given, not on anything parsed from the message."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    pairs = refs.claim_utilisation_findings(run)
    assert [subject for subject, _ in pairs] == [SUBJECT]
    assert [f for _, f in pairs] == refs.check_claim_utilisation(run)


def test_the_registry_names_this_accessor():
    """The wiring `rubrica waive` will read: the key is the string
    waivers.WAIVABLE_CHECKS uses, and the value is the pair accessor."""
    from rubrica.waivers import WAIVABLE_CHECKS

    assert set(refs.WAIVABLE_FINDING_SOURCES) == set(WAIVABLE_CHECKS)
    assert refs.WAIVABLE_FINDING_SOURCES["claim-utilisation"] is refs.claim_utilisation_findings


def test_check_refs_exits_zero_when_the_only_finding_is_waived(tmp_path, capsys):
    """The whole point: the gate stops being permanently dirty, and the finding
    is still on stdout so a reader still sees it."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    assert main(["check-refs", "--run", str(run.root)]) == 1
    # Drained so the assertions below read the waived run's own output rather than
    # a buffer that also holds the unwaived run's line.
    capsys.readouterr()
    _waive(run, SUBJECT)
    code = main(["check-refs", "--run", str(run.root)])
    out = capsys.readouterr().out
    assert code == 0
    assert "[waived]" in out and SUBJECT in out


def test_check_refs_still_exits_one_with_an_unwaived_finding_beside_it(tmp_path):
    """A waiver must not clear the gate for anything but itself."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    _orphan(run, "orphan")
    _waive(run, SUBJECT)
    assert main(["check-refs", "--run", str(run.root)]) == 1


def test_a_malformed_waivers_file_is_exit_two_not_a_finding(tmp_path, capsys):
    """A misconfigured run, not a stage defect. A 1 here would spend the run's
    one repair attempt on a stage whose output was never the problem."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    run.waivers.write_text("{not json", encoding="utf-8")
    assert main(["check-refs", "--run", str(run.root)]) == 2
    assert capsys.readouterr().out.strip() == "", "an exit 2 must not print a finding line"


def test_a_schema_invalid_waivers_file_is_exit_two(tmp_path, capsys):
    """Parseable and wrong is the same class of problem as unparseable: a person
    wrote it, so there is no stage to hand a repair prompt to."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    run.waivers.write_text(
        json.dumps({"schema_version": "0.1", "waivers": [{"check": "claim-utilisation"}]}),
        encoding="utf-8",
    )
    assert main(["check-refs", "--run", str(run.root)]) == 2
    assert capsys.readouterr().out.strip() == ""


def test_an_unreadable_waivers_file_is_exit_two(tmp_path, capsys):
    run = build_toy_run(tmp_path)
    _uncited(run)
    run.waivers.write_text("{}", encoding="utf-8")
    run.waivers.chmod(0o000)
    try:
        assert main(["check-refs", "--run", str(run.root)]) == 2
        assert capsys.readouterr().out.strip() == ""
    finally:
        run.waivers.chmod(0o644)
