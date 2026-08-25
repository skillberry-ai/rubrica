"""run-summary: one run directory as a single self-contained HTML page.

Partial runs are the primary case, not the edge case: measured across the 11 run
directories on disk when this was designed, 1 reached an emitted suite and 6 held
nothing past intake. Every test that builds a run short of `challenge` is
exercising the common path.
"""

from __future__ import annotations

import json
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


def test_header_reads_the_manifest_facts(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="intake", max_rounds=2, max_scenarios=8)
    head = summary.header(run)
    assert head.run_id == run.root.name
    assert head.max_rounds == 2
    assert head.max_scenarios == 8
    assert head.created_utc, "intake stamps created_utc"


def test_header_reports_this_runs_limits_and_not_the_fixture_default(tmp_path):
    """The same fields again, at values the toy fixture does not itself default to.

    `build_toy_run` defaults to `max_rounds=2, max_scenarios=8` -- the very pair
    the test above passes -- so that test cannot distinguish a header that read
    this manifest from one that read any manifest, or from a constant. 3 and 11
    are reachable (the manifest schema's floor is 1 for both) and appear nowhere
    in the fixture, and they are unequal to each other so a swapped pair of
    `limits` keys fails here too.
    """
    run = build_toy_run(tmp_path / "runs", upto="intake", max_rounds=3, max_scenarios=11)
    head = summary.header(run)
    assert head.max_rounds == 3
    assert head.max_scenarios == 11
    assert head.schema_version == "0.1"


def test_header_reports_the_manifests_run_id_not_the_directory_name(tmp_path):
    """Which of the two identical-looking sources the run id comes from.

    In every real run the manifest's `run_id` and the directory's name are the
    same string, so `head.run_id == run.root.name` is satisfied just as well by
    an implementation that never opened the manifest. Divorcing the two is the
    only way to say which one is being read, and the manifest is the answer the
    page owes: it is the run's own record of its identity, and a directory
    copied or renamed after the fact must not be able to relabel it.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    manifest = read_json(run.manifest)
    manifest["run_id"] = "renamed-on-disk"
    write_json(run.manifest, manifest)
    assert summary.header(run).run_id == "renamed-on-disk"


def test_header_lists_recorded_stages_sorted(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    manifest = read_json(run.manifest)
    manifest["stages"] = {
        "propose": {"model": "sonnet", "effort": "medium", "skill_sha256": "b" * 64},
        "extract": {"model": "opus", "effort": "high", "skill_sha256": "a" * 64},
    }
    write_json(run.manifest, manifest)
    head = summary.header(run)
    assert [s.stage for s in head.stages] == ["extract", "propose"]
    assert head.stages[0].model == "opus"
    assert head.stages[0].effort == "high"
    assert head.stages[0].skill_sha256 == "a" * 64


def test_header_sorts_stages_a_manifest_stores_out_of_order(tmp_path):
    """The ordering lock, on a manifest whose `stages` is not already sorted on disk.

    `artifacts.write_json` canonicalises with `sort_keys=True`, so a manifest
    written through it comes back with `extract` ahead of `propose` whatever order
    the caller built the dict in. That makes the ordering assertion in
    test_header_lists_recorded_stages_sorted satisfied by `json.load`'s
    file order alone -- measured: deleting `sorted()` from `header` leaves that
    test green and fails this one. So this manifest is written with a plain
    `json.dumps` and no `sort_keys`, which puts `propose` first in the file.

    Sorted rather than file order because a manifest is written key by key as the
    run progresses, and two runs of the same pipeline must render the same table
    -- a table ordered by whatever the last hand-edit did is not diffable.
    """
    from rubrica.artifacts import read_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    manifest = read_json(run.manifest)
    manifest["stages"] = {
        "propose": {"model": "sonnet", "effort": "medium", "skill_sha256": "b" * 64},
        "extract": {"model": "opus", "effort": "high", "skill_sha256": "a" * 64},
    }
    run.manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    assert list(read_json(run.manifest)["stages"]) == ["propose", "extract"], (
        "the file must hold the unsorted order for this test to discriminate"
    )
    assert [s.stage for s in summary.header(run).stages] == ["extract", "propose"]


def test_header_maps_every_recorded_field_of_every_recorded_stage(tmp_path):
    """Both records in full, as dataclass equality rather than field spot checks.

    The test above reads three fields off `stages[0]` and nothing at all off
    `stages[1]`, so a body-to-record mapping that dropped or crossed a field on
    any stage but the first stays green. Whole-list equality is the lock, and the
    six values are pairwise distinct so a `model`/`effort` cross, or a body read
    from a sibling stage's entry, fails rather than coinciding.

    This run stops at intake, so neither `extract` nor `propose` is a stage the
    spine marks produced -- and the records are rendered anyway. That is the
    documented ruling, not an oversight: the disagreement between a recorded
    stage and an absent artifact is a finding for `flags()` to raise, and a
    header that hid the record would hide the evidence for it.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    manifest = read_json(run.manifest)
    manifest["stages"] = {
        "propose": {"model": "sonnet", "effort": "medium", "skill_sha256": "b" * 64},
        "extract": {"model": "opus", "effort": "high", "skill_sha256": "a" * 64},
    }
    write_json(run.manifest, manifest)
    assert summary.header(run).stages == [
        summary.StageRecord(stage="extract", model="opus", effort="high", skill_sha256="a" * 64),
        summary.StageRecord(
            stage="propose", model="sonnet", effort="medium", skill_sha256="b" * 64
        ),
    ]


def test_header_without_a_manifest_is_absent(tmp_path):
    empty = tmp_path / "run-empty"
    empty.mkdir()
    assert isinstance(summary.header(RunPaths(empty)), summary.Absent)


def test_header_absent_names_the_artifact_it_looked_for(tmp_path):
    """`Absent` carries `what` so the page can say what is missing.

    An `isinstance` check alone is satisfied by `Absent("")`, and the whole
    reason absence is returned rather than raised is that the rendered page
    states which artifact it could not read.
    """
    empty = tmp_path / "run-empty"
    empty.mkdir()
    assert summary.header(RunPaths(empty)).what == "manifest.json"


def test_header_survives_a_malformed_manifest(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="intake")
    run.manifest.write_text("{not json", encoding="utf-8")
    assert isinstance(summary.header(RunPaths(run.root)), summary.Absent)


def test_header_survives_a_manifest_whose_stages_is_not_a_mapping(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    manifest = read_json(run.manifest)
    manifest["stages"] = "nope"
    write_json(run.manifest, manifest)
    head = summary.header(run)
    assert head.stages == []
    assert head.run_id == run.root.name, "the rest of the header still renders"


def test_header_survives_a_stage_whose_body_is_not_a_mapping(tmp_path):
    """The malformation one level deeper than the test above.

    `brief._dicts`' docstring records the measured shape: `_quietly` guards the
    *document*, and every loop below it then indexed into that document's
    *elements* with a bare `.get`. `"stages": {"extract": "nope"}` is that shape
    here -- a hand-edited manifest, which is what the gates invite -- and without
    a guard on the body it raises `AttributeError: 'str' object has no attribute
    'get'` on a run that is otherwise perfectly readable.

    The stage is still listed, with empty fields, rather than dropped: the name
    is the part that was legible, and a silently omitted row would read as "no
    stage record" -- a different fact about the run.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    manifest = read_json(run.manifest)
    manifest["stages"] = {"extract": "nope"}
    write_json(run.manifest, manifest)
    assert summary.header(run).stages == [
        summary.StageRecord(stage="extract", model="", effort="", skill_sha256="")
    ]
