"""The waivers in force, read at every human gate.

A waiver is a standing ruling rather than a one-off note: it was recorded once,
by a person holding one gate, and it goes on suppressing a finding's exit code
for the rest of the run. So a reader at gate 3 has as much reason to see it as
the reader who wrote it at gate 1, and every gate renders it.

`gate-brief` is a report, so none of this may turn a readable run into a
non-zero exit: the malformed case below is the assertion that holds that line.
"""

from __future__ import annotations

import json

import pytest

from rubrica import cli
from rubrica.brief import GATES, WAIVERS_HEADER, WAIVERS_UNREADABLE, gate_brief
from rubrica.waivers import remedy_choices
from tests.toy import build_toy_catalogue_and_triage, build_toy_run

# The waivable subject the toy run actually has. Imported rather than respelled:
# tests/unit/test_refs_claim_utilisation_waivers.py measured that api-json is the
# one toy input whose citations can be stripped to zero, and a second spelling
# here would be a literal to forget the day the fixture changes.
from tests.unit.test_refs_claim_utilisation_waivers import SUBJECT


def _waive(run, remedy="triage-rule", subject=SUBJECT):
    """One recorded waiver, written the way `rubrica waive` writes one.

    `schema_version`, not `version`: `waivers.load` schema-validates, so a
    document keyed the old way is rejected outright -- and while `_waiver_lines`
    deliberately does not go through `load`, a fixture that only this reader
    accepts would be testing a shape no other consumer in the run can read.
    """
    run.waivers.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "waivers": [
                    {
                        "id": "wv-0001",
                        "check": "claim-utilisation",
                        "subject": subject,
                        "remedy": remedy,
                        "reason": "every reconcile pass declined it as out of domain",
                        "finding_text": f"no world-model element cites any claim from {subject}",
                        "recorded_at": "2026-09-08T04:12:33Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize("gate", GATES)
def test_a_waiver_appears_at_every_gate(gate, tmp_path):
    """A waived finding is re-read at each gate rather than forgotten after the
    one ruling that recorded it."""
    run = build_toy_run(tmp_path)
    _waive(run)
    text = gate_brief(run, gate)
    assert "wv-0001" in text
    assert SUBJECT in text
    assert "triage-rule" in text


@pytest.mark.parametrize("gate", GATES)
def test_no_waiver_section_when_there_are_none(gate, tmp_path):
    """The common case must stay quiet -- an empty section at every gate is
    noise a reader learns to skip."""
    run = build_toy_run(tmp_path)
    assert "Waivers" not in gate_brief(run, gate)


@pytest.mark.parametrize("gate", GATES)
def test_the_count_is_the_number_of_entries(gate, tmp_path):
    """The header states how many, so a reader can tell a one-waiver run from a
    run somebody waived their way through."""
    run = build_toy_run(tmp_path)
    _waive(run)
    assert f"{WAIVERS_HEADER}: 1" in gate_brief(run, gate)


def test_the_reason_is_rendered_beside_the_waiver(tmp_path):
    """Without the reason the section is a list of ids: the whole point of a
    waiver being on the record is that the next reader can weigh the argument."""
    run = build_toy_run(tmp_path)
    _waive(run)
    assert "declined it as out of domain" in gate_brief(run, 1)


def test_remedy_none_reads_as_accepted_rather_than_deferred(tmp_path):
    """`none` and a stage name say different things about whether anybody still
    owes work, so they must not render identically."""
    run = build_toy_run(tmp_path)
    _waive(run, remedy="none")
    text = gate_brief(run, 1)
    assert "accepted; no artifact should change" in text


def test_a_stage_remedy_does_not_read_as_an_acceptance(tmp_path):
    """The other direction of the branch above: a remedy naming a stage still
    says somebody owes work there."""
    run = build_toy_run(tmp_path)
    _waive(run, remedy="triage-rule")
    text = gate_brief(run, 1)
    assert "remedy triage-rule" in text
    assert "accepted; no artifact should change" not in text


@pytest.mark.parametrize("remedy", ["outside-the-run", "extract", "emit"])
def test_a_known_remedy_carries_no_unknown_marker(remedy, tmp_path):
    """Every value `rubrica waive --remedy` accepts renders plainly. Parametrised
    over three shapes of the choice set -- a sentinel and two stage names -- since
    the marker below is only useful if it never fires on a legitimate value."""
    assert remedy in remedy_choices()
    run = build_toy_run(tmp_path)
    _waive(run, remedy=remedy)
    assert "not a known stage" not in gate_brief(run, 1)


def test_an_unknown_remedy_is_marked_as_one(tmp_path):
    """A stage renamed after a waiver was written leaves a `remedy` naming
    nothing. `load` deliberately does not reject it -- that would turn cosmetic
    staleness into an exit 2 on every later check -- so this report is where a
    reader is told the pointer is stale.
    """
    run = build_toy_run(tmp_path)
    _waive(run, remedy="banana")
    text = gate_brief(run, 1)
    assert "remedy banana (not a known stage)" in text


def test_a_malformed_waivers_file_does_not_crash_the_brief(tmp_path):
    """gate-brief is a report and always exits clean on a readable run; a
    malformed artifact is check-refs' finding to raise, not this command's."""
    run = build_toy_run(tmp_path)
    run.waivers.write_text("{not json", encoding="utf-8")
    text = gate_brief(run, 1)
    # Against the constant brief.py renders, not against its prose: pinning the
    # sentence was measured to fail on the meaning-preserving reword "could not be
    # read" -> "is unreadable", which is this repository's own phrase-pin defect.
    # The negative half is what makes it discriminating -- rendering nothing at all
    # was measured to pass a bare `"waivers.json" in text`.
    assert WAIVERS_UNREADABLE in text
    assert WAIVERS_HEADER not in text


@pytest.mark.parametrize("gate", GATES)
def test_the_command_still_exits_clean_with_a_waiver(gate, tmp_path):
    """Through the CLI rather than through gate_brief, because the promise is
    about the exit code an orchestrator reads: a report is never a gate."""
    run = build_toy_run(tmp_path)
    _waive(run)
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", str(gate)]) == 0


@pytest.mark.parametrize("gate", GATES)
def test_the_command_still_exits_clean_on_a_malformed_waivers_file(gate, tmp_path):
    """The same promise where it is most likely to break: the one artifact in a
    run a human is invited to hand-edit, edited wrong."""
    run = build_toy_run(tmp_path)
    run.waivers.write_text("{not json", encoding="utf-8")
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", str(gate)]) == 0


def test_a_waivers_document_of_the_wrong_shape_renders_as_none_rather_than_raising(tmp_path):
    """Readable JSON whose `waivers` is not a list of objects. `_dicts` drops the
    members it cannot read, which is this module's standing ruling for a
    hand-edited document -- so the section is absent, not a traceback, and
    `rubrica validate` is what names the shape."""
    run = build_toy_run(tmp_path)
    run.waivers.write_text(
        json.dumps({"schema_version": "0.1", "waivers": ["oops-a-string"]}), encoding="utf-8"
    )
    assert WAIVERS_HEADER not in gate_brief(run, 1)
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "1"]) == 0


def test_gate_zero_shows_the_waiver_on_a_run_that_has_a_triage_record(tmp_path):
    """Gate 0 has three exits -- two absent-triage messages and the real brief --
    and every toy run the tests above build takes an absent-triage one, because
    `build_toy_run` mints through `intake --input` and never writes 00-triage.json.

    Measured: deleting the waiver block from gate 0's *real* body left every other
    assertion in this module green, so this is the one that reaches it.
    """
    run = build_toy_run(tmp_path)
    build_toy_catalogue_and_triage(run)
    _waive(run)
    text = gate_brief(run, 0)
    assert "wv-0001" in text
    assert f"{WAIVERS_HEADER}: 1" in text


def test_gate_zero_still_leads_with_the_objective_verdict(tmp_path):
    """Gate 0's stated ruling -- a tired reader who stops after ten lines must
    have seen the verdict -- survives the waiver block being added above it.

    Asserted on a run that has a triage record, since that is the only run whose
    gate 0 renders a verdict at all.
    """
    run = build_toy_run(tmp_path)
    build_toy_catalogue_and_triage(run)
    _waive(run)
    lines = gate_brief(run, 0).splitlines()
    assert "Objective verdict" in lines[:10], lines[:10]
