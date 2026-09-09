"""`run-summary` must not report a waived finding as an open problem.

`summary.utilisation` recomputes `refs.check_claim_utilisation`'s predicate --
deliberately, and `summary.py`'s module docstring says why a second spelling of
that arithmetic is tolerated where a third would not be. What it did not do was
read the *ruling*: measured on a run where `check-refs` exits 0 with the
`[waived] ` line printed, the page still flagged "1 input(s) contributed no cited
claim" with nothing marking it as ruled on, which is the page and the gate
disagreeing about one run in judgment rather than in arithmetic.

`run-summary` must not become a gate to fix that. It exits 0 on a run it cannot
read at all, so the waivers are read tolerantly through
`waivers.waived_subjects_quietly`; the last test here is the assertion that holds
that line.
"""

from __future__ import annotations

import re

from rubrica import summary, summary_html
from rubrica.cli import main
from tests.toy import build_toy_run
from tests.unit.test_refs_claim_utilisation_waivers import SUBJECT, _orphan, _uncited, _waive

_FLAG = "uncited-artifacts"


def _flag(run):
    """The `uncited-artifacts` flag, or None. Selected by id rather than by
    position: the flag table grows, and an index would silently start asserting
    against a neighbour."""
    return next((f for f in summary.flags(run) if f.id_ == _FLAG), None)


def test_a_waived_input_is_not_an_open_flag(tmp_path):
    """The defect this fixes, asserted beside the gate's own verdict on the same
    run: `check-refs` exits 0, so the page must not carry an open problem."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    assert _flag(run) is not None, "without a waiver this is an open problem"
    _waive(run, SUBJECT)
    assert main(["check-refs", "--run", str(run.root)]) == 0
    assert _flag(run) is None
    got = summary.utilisation(run)
    assert got.uncited == []
    assert got.waived == [SUBJECT]


def test_the_waived_input_is_still_named_on_the_page(tmp_path):
    """Marked, not muted. `check-refs` keeps printing the finding prefixed
    `[waived] `, so a page that dropped the input entirely would be the mute
    button the waiver design refuses -- the ruling is what changes, not the fact.

    Asserted on the rendered page rather than on the dataclass, because the
    dataclass field could hold the id while no renderer showed it.

    Scoped to the paragraph that names the input, and the scoping is measured
    rather than stylistic: a plain `"waived" in page.lower()` was green against a
    build that ignored the waiver entirely, because the flag table's threshold
    string carries the word too. Measured on the fixed build, exactly one `<p>`
    of ten names the subject, so the scope is not a way of hiding a second one.
    """
    run = build_toy_run(tmp_path)
    _uncited(run)
    _waive(run, SUBJECT)
    page = summary_html.render(run)
    marked = [para for para in re.findall(r"<p>.*?</p>", page, re.S) if SUBJECT in para]
    assert marked, "the waived input is named nowhere on the page"
    assert all("waived" in para for para in marked), marked
    # The all-clear sentence must not stand on a run that has one: nothing was
    # cited from this input, and a human ruling on it did not change that.
    assert "Every input with claims contributed at least one cited claim" not in page


def test_an_unwaived_input_beside_a_waived_one_still_flags(tmp_path):
    """A waiver clears its own subject and nothing else -- `waived_subjects`'
    narrowness property, seen from the page.

    The headline counts only what is still open, so a reader acts on a number
    that matches the unwaived findings `check-refs` prints; the waived one is
    named in the detail so the count cannot read as the whole story.
    """
    run = build_toy_run(tmp_path)
    _uncited(run)
    _orphan(run, "orphan")
    _waive(run, SUBJECT)
    got = summary.utilisation(run)
    assert (got.uncited, got.waived) == (["orphan"], [SUBJECT])
    flag = _flag(run)
    assert flag is not None
    assert flag.headline.startswith("1 input(s)")
    assert "orphan" in flag.detail
    assert SUBJECT in flag.detail


def test_a_malformed_waivers_file_leaves_the_report_at_exit_zero(tmp_path, capsys):
    """A report is never a gate. `waivers.load` raises on this file and
    `check-refs` exits 2 on the same run, which is where that defect is reported;
    here it must read as no ruling at all, so nothing is suppressed and the page
    still renders.
    """
    run = build_toy_run(tmp_path)
    _uncited(run)
    _waive(run, SUBJECT)
    run.waivers.write_text("{not json", encoding="utf-8")
    assert main(["run-summary", "--run", str(run.root), "--output", str(tmp_path / "p.html")]) == 0
    capsys.readouterr()
    got = summary.utilisation(run)
    assert got.waived == [], "an unreadable ruling suppresses nothing"
    assert got.uncited == [SUBJECT]
    assert main(["check-refs", "--run", str(run.root)]) == 2
