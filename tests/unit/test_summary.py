"""run-summary: one run directory as a single self-contained HTML page.

Partial runs are the primary case, not the edge case: measured across the 11 run
directories on disk when this was designed, 1 reached an emitted suite and 6 held
nothing past intake. Every test that builds a run short of `challenge` is
exercising the common path.
"""

from __future__ import annotations

import os

import pytest

from rubrica import summary
from rubrica.paths import STAGES, RunPaths
from tests.toy import build_toy_run

# The stages each fixture level reaches, as *exact* sets rather than a handful of
# spot checks. Exact-set equality is what makes these locks: asserting only that
# `intake` is produced leaves the other 21 evidence paths free to point anywhere,
# and repointing `triage-audit`, `reconcile-goals` and `score` at artifacts that
# never exist in a run left all of the original 8 tests green. That is the
# substring-of-message shape CLAUDE.md names, and the six near-identical
# `reconcile-*` lines in `_stage_evidence` are where the next copy-paste slip
# lands. Compared as sets, not lists, because
# test_stage_spine_covers_every_declared_stage_in_order already owns the ordering.
_TRIAGE_FAMILY = {
    "survey",
    "triage-slices",
    "triage-objective",
    "triage-rule",
    "triage-audit",
    "triage-seal",
}
_INTAKE_THROUGH_CHALLENGE = {
    "intake",
    "extract",
    "reconcile-subjects",
    "reconcile-contradict",
    "reconcile-capabilities",
    "reconcile-outcomes",
    "reconcile-entities",
    "reconcile-goals",
    "reconcile-gaps",
    "reconcile-seal",
    "propose",
    "score",
    "instantiate",
    "challenge",
}


def test_esc_escapes_markup_and_quotes():
    assert summary.esc('<a href="x">&') == "&lt;a href=&quot;x&quot;&gt;&amp;"


def test_esc_renders_none_as_empty_string():
    assert summary.esc(None) == ""


def test_esc_stringifies_non_strings():
    assert summary.esc(14) == "14"


def test_stage_spine_covers_every_declared_stage_in_order(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="extract")
    rows = summary.stage_spine(run)
    assert [row.name for row in rows] == list(STAGES)


def test_stage_spine_marks_a_reached_stage_produced(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="extract")
    produced = {row.name: row.produced for row in summary.stage_spine(run)}
    assert produced["intake"] is True
    assert produced["extract"] is True


def test_stage_spine_marks_an_unreached_stage_absent(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="extract")
    produced = {row.name: row.produced for row in summary.stage_spine(run)}
    assert produced["propose"] is False
    assert produced["challenge"] is False


def test_stage_spine_on_an_empty_directory_marks_everything_absent(tmp_path):
    empty = tmp_path / "run-empty"
    empty.mkdir()
    rows = summary.stage_spine(RunPaths(empty))
    assert rows, "the spine is the pipeline's stages, so it is never empty"
    assert not any(row.produced for row in rows)


def test_stage_spine_marks_a_directory_writing_fan_out_stage_produced(tmp_path):
    """instantiate and emit write per-scenario *directories*, never a top-level file.

    Measured, not hypothetical: an evidence test that counted only `*.json` children
    of `04-instances/` marked `instantiate` absent on this very run, which has four
    instance directories. `emit` has the same shape (`06-suite/<sid>/task.toml`), so
    the spine was reporting "never ran" about the two stages a complete run is most
    read for.
    """
    run = build_toy_run(tmp_path / "runs")
    assert run.scenario_ids_with_instances(), "the fixture must actually have instances"
    produced = {row.name: row.produced for row in summary.stage_spine(run)}
    assert produced["instantiate"] is True


def _produced(run) -> set[str]:
    return {row.name for row in summary.stage_spine(run) if row.produced}


def test_stage_spine_marks_every_triage_family_stage_produced(tmp_path):
    """All six pre-intake stages at once, as an exact set.

    `build_toy_run(upto="triage-seal")` writes every one of them, so each of the
    six evidence entries is measured here rather than assumed. The set is exact
    in both directions: a repointed path drops a name, and an entry that matches
    something a triage run never wrote adds one.
    """
    run = build_toy_run(tmp_path / "runs", upto="triage-seal")
    assert _produced(run) == _TRIAGE_FAMILY


def test_stage_spine_marks_every_stage_from_intake_through_challenge_produced(tmp_path):
    """The other fourteen, same exact-set reasoning.

    Covers all six `reconcile-*` partial paths, which are six near-identical
    lines in `_stage_evidence` and so the likeliest place for a copy-paste slip
    that no earlier test could see.
    """
    run = build_toy_run(tmp_path / "runs")
    assert _produced(run) == _INTAKE_THROUGH_CHALLENGE


@pytest.mark.parametrize("mode", [0o000, 0o444])
def test_stage_spine_does_not_raise_on_an_unreadable_run_root(tmp_path, mode):
    """`_exists`'s `except OSError` is load-bearing on this interpreter, not defensive.

    Measured on Python 3.13: `Path.exists()` raises `PermissionError` when the
    parent directory denies traversal, so without that handler the spine -- whose
    entire job is to render on a run too broken to read -- would raise instead of
    reporting a run it cannot see as unreached. Both modes deny traversal to a
    *directory* (0o444 grants read but not the `x` a child stat needs), so both
    yield a fully absent spine; the pair is kept because they are two different
    refusals and only one of them would survive a `chmod` regression.

    The row count is asserted alongside, since "no exception and no rows" would
    satisfy a bare `not any(...)` while telling a reader nothing.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path / "runs")
    run.root.chmod(mode)
    try:
        rows = summary.stage_spine(run)
        assert len(rows) == len(STAGES)
        assert not any(row.produced for row in rows)
    finally:
        run.root.chmod(0o755)


def test_stage_spine_degrades_to_absent_on_a_listable_but_untraversable_fan_out_dir(tmp_path):
    """`_has_part`'s `except OSError`, at the one shape that reaches it.

    0o444 on a directory is the narrow case `paths.py` documents for
    `_instance_dir_names`: `iterdir()` succeeds because read is granted, and
    stat'ing a *child* is what raises, since traversal is not. `04-instances/`
    holds only subdirectories, so `_has_part` must call `p.is_dir()` on one to
    answer at all -- which makes this the only fan-out directory in the run that
    exercises the handler. Absent is the honest answer: the directory is there,
    but nothing about what it holds can be read.

    `challenge` is asserted still produced as the control. Without it this would
    pass on a spine that had stopped reporting anything at all, and the point is
    that one unreadable directory degrades exactly one row.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path / "runs")
    assert all(p.is_dir() for p in run.instances_dir.iterdir()), (
        "the shape under test needs a directory whose children are all subdirectories"
    )
    run.instances_dir.chmod(0o444)
    try:
        produced = {row.name: row.produced for row in summary.stage_spine(run)}
        assert produced["instantiate"] is False
        assert produced["challenge"] is True
    finally:
        run.instances_dir.chmod(0o755)
