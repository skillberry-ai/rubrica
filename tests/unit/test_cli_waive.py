"""`rubrica waive`: the only writer of waivers.json, and the refusal that guards it.

A waiver suppresses a finding's exit code, so the one thing this subcommand must
never do is record a waiver for a finding nobody is raising. It therefore runs the
named check itself and matches the subject against the pairs that check yields --
which is also where `finding_text` comes from, since a human retyping a finding is
a human who can paraphrase one.

Nothing here pins the finding's prose. Matching is on `(check, subject)` precisely
so a meaning-preserving reword of the message changes nothing, and a test that
pinned the sentence would be the text keying this design rejects.
"""

from __future__ import annotations

import pytest

from rubrica import refs, waivers
from rubrica.artifacts import read_json
from rubrica.cli import main
from rubrica.errors import UsageError
from rubrica.validate import validate_artifact
from tests.toy import build_toy_run
from tests.unit.test_refs_claim_utilisation_waivers import (
    SUBJECT,
    _by_subject,
    _orphan,
    _uncited,
)

_REASON = "out of the target's domain; every reconcile pass declined it"


def _waive_argv(run, subject=SUBJECT, remedy="triage-rule", check="claim-utilisation"):
    return [
        "waive",
        "--run",
        str(run.root),
        "--check",
        check,
        "--subject",
        subject,
        "--remedy",
        remedy,
        "--reason",
        _REASON,
    ]


def test_waiving_a_live_finding_records_it(tmp_path, capsys):
    run = build_toy_run(tmp_path)
    _uncited(run)
    assert main(_waive_argv(run)) == 0
    assert capsys.readouterr().out.strip() == "wv-0001", "the minted id is what a caller reads"
    doc = read_json(run.waivers)
    # `schema_version`, the house key: waivers-0.1.json requires it, and a document
    # keyed `version` is one waivers.load rejects outright.
    assert doc["schema_version"] == "0.1"
    (entry,) = doc["waivers"]
    assert entry["id"] == "wv-0001"
    assert entry["check"] == "claim-utilisation"
    assert entry["subject"] == SUBJECT
    assert entry["remedy"] == "triage-rule"
    assert entry["reason"] == _REASON
    assert not validate_artifact(run.waivers, "waivers")


def test_the_finding_text_is_copied_from_the_finding_not_typed(tmp_path):
    """The integrity property: a human retyping a finding is a human who can
    paraphrase one, so there is no --finding-text flag at all.

    Asserted against the live finding's own message rather than against a pinned
    sentence -- the message is prose a reword may change, and the property under
    test is that the recorded copy came from the finding, not what it says.
    """
    run = build_toy_run(tmp_path)
    _uncited(run)
    main(_waive_argv(run))
    entry = read_json(run.waivers)["waivers"][0]
    assert entry["finding_text"] == _by_subject(run)[SUBJECT].message


def test_waiving_a_finding_that_is_not_raised_is_refused(tmp_path, capsys):
    """No pre-emptive waivers, and none left behind by a fixed defect."""
    run = build_toy_run(tmp_path)  # nothing uncited
    assert main(_waive_argv(run)) == 2
    assert not run.waivers.exists()
    captured = capsys.readouterr()
    assert "no such finding" in captured.err
    assert captured.out.strip() == "", "an exit 2 must not print a finding line"


def test_an_unregistered_check_is_refused(tmp_path):
    """--check is a choice over waivers.WAIVABLE_CHECKS, so argparse refuses this
    before the handler runs; main turns its SystemExit(2) into the usage code."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    assert main(_waive_argv(run, check="not-a-check")) == 2
    assert not run.waivers.exists()


def test_a_remedy_outside_the_choices_is_refused(tmp_path):
    run = build_toy_run(tmp_path)
    _uncited(run)
    assert main(_waive_argv(run, remedy="nowhere")) == 2
    assert not run.waivers.exists()


def test_none_is_an_accepted_remedy(tmp_path):
    """The ruling this exists for must be expressible."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    assert main(_waive_argv(run, remedy="none")) == 0
    assert read_json(run.waivers)["waivers"][0]["remedy"] == "none"


def test_the_ruling_also_lands_in_decisions_md(tmp_path):
    run = build_toy_run(tmp_path)
    _uncited(run)
    main(_waive_argv(run))
    assert f"waived claim-utilisation/{SUBJECT}" in run.decisions.read_text(encoding="utf-8")


def test_a_reason_with_a_newline_is_refused(tmp_path):
    """decisions.md is one entry per line; an embedded newline corrupts the
    append-only format for every line written after it -- the guard `decide`
    already carries, for the same reason."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    argv = _waive_argv(run)
    argv[argv.index("--reason") + 1] = "line one\nline two"
    assert main(argv) == 2
    assert not run.waivers.exists()


def test_every_offered_check_can_actually_be_run():
    """The CLI's own dependency between the two registries.

    --check's choices come from waivers.WAIVABLE_CHECKS and the handler dispatches
    through refs.WAIVABLE_FINDING_SOURCES, so a key in the first and not the second
    is a check the CLI offers and then KeyErrors on -- an exception escaping into
    the catch-all as a fabricated exit-1 finding.
    """
    assert set(waivers.WAIVABLE_CHECKS) <= set(refs.WAIVABLE_FINDING_SOURCES)


def test_a_subject_that_is_a_prefix_of_another_is_not_confused(tmp_path, capsys):
    """Measured trap: `"api-json" in "...any claim from api-json2 (1 claims)"` is
    True, so an implementation matching the subject against the finding's message
    would record a waiver for api-json off api-json2's finding.

    Only api-json2 is uncited here, so the trap is measured without depending on
    the order the pairs happen to arrive in: the right answer is a refusal.
    """
    run = build_toy_run(tmp_path)
    _orphan(run, f"{SUBJECT}2")
    assert main(_waive_argv(run, subject=SUBJECT)) == 2
    assert not run.waivers.exists()
    assert "no such finding" in capsys.readouterr().err


def test_a_second_waiver_appends_rather_than_replacing(tmp_path):
    run = build_toy_run(tmp_path)
    _uncited(run)
    main(_waive_argv(run))
    # A second uncited artifact, so a second finding exists to waive. Built the way
    # the helper builds one: a claims file without `evidence` raises KeyError in
    # check_manifest before claim_utilisation is reached at all.
    _orphan(run, f"{SUBJECT}2")
    assert main(_waive_argv(run, subject=f"{SUBJECT}2")) == 0
    ids = [e["id"] for e in read_json(run.waivers)["waivers"]]
    assert ids == ["wv-0001", "wv-0002"]


# -- record's own guards, which argparse's choices make unreachable from the CLI --
#
# waivers-0.1.json keeps `check` a free string on purpose, so `record`'s check
# against WAIVABLE_CHECKS is the only thing standing between a typo and a waiver
# nothing will ever read. Exercised directly because the subcommand's `choices`
# refuse those arguments one layer earlier.


def test_record_refuses_an_unregistered_check(tmp_path):
    run = build_toy_run(tmp_path)
    with pytest.raises(UsageError, match="unknown check"):
        waivers.record(
            run,
            check="not-a-check",
            subject=SUBJECT,
            remedy="none",
            reason=_REASON,
            finding_text="whatever the finding said",
        )
    assert not run.waivers.exists()


def test_record_refuses_a_remedy_outside_the_choices(tmp_path):
    run = build_toy_run(tmp_path)
    with pytest.raises(UsageError, match="unknown remedy"):
        waivers.record(
            run,
            check="claim-utilisation",
            subject=SUBJECT,
            remedy="nowhere",
            reason=_REASON,
            finding_text="whatever the finding said",
        )
    assert not run.waivers.exists()


def test_record_refuses_a_blank_reason(tmp_path):
    """Whitespace-only, not just empty: a waiver records *why*, and " " records
    that somebody waived a finding and not what they ruled -- the treatment
    manifest.decide already gives a blank note."""
    run = build_toy_run(tmp_path)
    with pytest.raises(UsageError, match="cannot be empty"):
        waivers.record(
            run,
            check="claim-utilisation",
            subject=SUBJECT,
            remedy="none",
            reason="   ",
            finding_text="whatever the finding said",
        )
    assert not run.waivers.exists()
