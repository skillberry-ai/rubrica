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


def test_inputs_rows_carry_every_manifest_field(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="intake")
    got = summary.inputs(run)
    assert got.rows, "intake registers the toy inputs"
    row = got.rows[0]
    assert row.artifact_id
    assert row.kind
    assert row.bytes_ > 0
    assert len(row.sha256) == 64
    assert row.stored_as


def test_inputs_rows_match_the_manifest_entry_field_for_field(tmp_path):
    """Every field of every row against the manifest, as whole-row equality.

    The test above reads five fields off `rows[0]` and asserts only that each is
    truthy, so a row that put `kind` in `stored_as`, or read every row out of
    `inputs[0]`, stays green -- the toy manifest's three entries all have a
    truthy value in all six fields. Building the expected rows from the document
    on disk is the lock, and it pins the order too: `inputs` renders the
    manifest's own sequence, which is the order intake registered them in.
    """
    from rubrica.artifacts import read_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    entries = read_json(run.manifest)["inputs"]
    assert len(entries) > 1, "one row cannot discriminate a per-row mapping"
    assert summary.inputs(run).rows == [
        summary.InputRow(
            artifact_id=entry["artifact_id"],
            kind=entry["kind"],
            bytes_=entry["bytes"],
            sha256=entry["sha256"],
            source_path=entry["source_path"],
            stored_as=entry["stored_as"],
        )
        for entry in entries
    ]


def test_inputs_totals_bytes_and_tallies_kinds(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="intake")
    got = summary.inputs(run)
    assert got.total_bytes == sum(r.bytes_ for r in got.rows)
    assert sum(got.kinds.values()) == len(got.rows)


def test_inputs_totals_the_manifests_own_bytes_and_counts_a_repeated_kind(tmp_path):
    """The two aggregates against the file, on a manifest with a duplicated kind.

    Both assertions in the test above are self-referential: `total_bytes ==
    sum(r.bytes_ ...)` holds for any total computed from the rows however wrong
    the rows are, and `sum(kinds.values()) == len(rows)` holds for a `kinds` that
    is a *set* of kinds rather than a tally, because the toy manifest's three
    inputs have three distinct kinds. So the total is compared to the document
    here, and one input's kind is rewritten to collide with another's -- which
    makes the expected tally `{"mcp_tool_schema": 1, "trace": 2}` and fails a set.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    manifest = read_json(run.manifest)
    manifest["inputs"][1]["kind"] = "trace"
    write_json(run.manifest, manifest)
    got = summary.inputs(run)
    assert got.total_bytes == sum(e["bytes"] for e in manifest["inputs"])
    assert got.kinds == {"mcp_tool_schema": 1, "trace": 2}


def test_inputs_without_a_manifest_is_absent(tmp_path):
    empty = tmp_path / "run-empty"
    empty.mkdir()
    assert isinstance(summary.inputs(RunPaths(empty)), summary.Absent)


def test_inputs_absent_names_the_artifact_it_looked_for(tmp_path):
    """`Absent("")` satisfies the isinstance check above; the page needs the name."""
    empty = tmp_path / "run-empty"
    empty.mkdir()
    assert summary.inputs(RunPaths(empty)).what == "manifest.json"


@pytest.mark.parametrize("bad", ["a lot", None, {"count": 3}, [], True])
def test_inputs_reads_a_non_integer_bytes_as_zero(tmp_path, bad):
    """`_as_int`, at every shape a hand-edited manifest reaches a summed column with.

    `bytes` feeds both a rendered cell and `total_bytes`, so a bare `int()` here
    takes the whole page down on one bad row -- `int("a lot")` raises ValueError
    and `int(None)` raises TypeError, and neither is caught anywhere between this
    and `main()`. Zero is the honest reading: the row still renders, and a byte
    count of 0 beside a real file is visibly wrong to a reader in a way an
    exception is not. `True` is in the list to record what `int()` does with it
    (1, not 0) rather than to endorse it -- the coercion is documented total, so
    every shape it accepts is measured.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    manifest = read_json(run.manifest)
    manifest["inputs"][0]["bytes"] = bad
    write_json(run.manifest, manifest)
    got = summary.inputs(run)
    expected = 1 if bad is True else 0
    assert got.rows[0].bytes_ == expected
    assert got.total_bytes == expected + sum(e["bytes"] for e in manifest["inputs"][1:])


def test_inputs_drops_a_non_dict_member_rather_than_raising(tmp_path):
    """`_dicts`' measured shape, on the one list this section reads.

    A string member reaches `.get` and raises `AttributeError` without the guard,
    on a run that is otherwise perfectly readable. The surviving row is asserted
    alongside the count so that "dropped everything" cannot pass.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    manifest = read_json(run.manifest)
    manifest["inputs"] = ["oops-a-string", manifest["inputs"][0]]
    write_json(run.manifest, manifest)
    got = summary.inputs(run)
    assert [r.artifact_id for r in got.rows] == ["api-json"]
    assert got.total_bytes == manifest["inputs"][1]["bytes"]


def test_inputs_on_a_manifest_whose_inputs_is_not_a_list_has_no_rows(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    manifest = read_json(run.manifest)
    manifest["inputs"] = "nope"
    write_json(run.manifest, manifest)
    got = summary.inputs(run)
    assert got.rows == []
    assert got.total_bytes == 0
    assert got.kinds == {}


def _objective_document(run_id: str) -> dict:
    """A schema-shaped `00-objective.json` payload, built rather than repeated.

    Every field name here is one `objective` reads, so the shape is pinned by
    objective-0.1.json in the one test that validates against it and reused by
    the rest.
    """
    return {
        "schema_version": "0.1",
        "run_id": run_id,
        "predicted_surface_count": 2,
        "objective_review": {
            "declared_objective": "breadth",
            "supported": True,
            "surfaces": [
                {
                    "name": "search",
                    "evidence": ["api-json"],
                    "weight": {"candidates": 1, "bytes": 40},
                },
                {
                    "name": "tickets",
                    "evidence": ["notes-md", "trace-json"],
                    "weight": {"candidates": 2, "bytes": 1216},
                },
            ],
        },
    }


def test_objective_reads_the_review_and_its_surfaces(tmp_path):
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    write_json(run.objective, _objective_document(run.root.name))
    got = summary.objective(run)
    assert got.declared == "breadth"
    assert got.supported is True
    assert got.predicted_count == 2
    assert got.surfaces[0].evidence == ["api-json"]
    assert got.surfaces[0].candidates == 1
    assert got.surfaces[0].bytes_ == 40


def test_objective_maps_each_surface_to_its_own_weight_in_order(tmp_path):
    """Both surfaces in full, which one surface cannot discriminate.

    A single-surface assertion is satisfied by an implementation that reads
    `surfaces[0]`'s weight for every row, or that reads `candidates` into
    `bytes_`. Two surfaces with pairwise distinct names, evidence lists and
    weights fail all of those, and whole-list equality pins the order the
    document declares -- surfaces are ranked by the pass that writes them, so
    re-sorting them here would relabel its ranking.

    The document is validated against objective-0.1.json first: this section
    reads six field names off it, and a fixture that drifted off-schema would let
    a wrong spelling pass here and read nothing at all on a real run.
    """
    from rubrica.artifacts import write_json
    from rubrica.validate import validate_artifact

    run = build_toy_run(tmp_path / "runs", upto="intake")
    write_json(run.objective, _objective_document(run.root.name))
    assert validate_artifact(run.objective, "objective") == [], (
        "the fixture must be the shape rb-triage-objective actually writes"
    )
    assert summary.objective(run).surfaces == [
        summary.Surface(name="search", evidence=["api-json"], candidates=1, bytes_=40),
        summary.Surface(
            name="tickets", evidence=["notes-md", "trace-json"], candidates=2, bytes_=1216
        ),
    ]


def test_objective_reads_the_objective_file_not_the_sealed_triage_copy(tmp_path):
    """Which of the two documents carrying `objective_review` this section reads.

    `triage-seal` copies `objective_review` into `00-triage.json` verbatim, so on
    a sealed run both files answer every assertion in the tests above and neither
    of them says which one was opened. `00-objective.json` is the answer, for two
    reasons: it is what the objective pass itself wrote, and it is the only one of
    the two carrying `predicted_surface_count` at all -- the field section 4.1's
    divergence check needs, which the seal does not copy. A run can also hold it
    while `triage-seal` has not run yet.

    The two documents are given contradictory verdicts here precisely so that
    reading the wrong one fails rather than coinciding.
    """
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    write_json(run.objective, _objective_document(run.root.name))
    write_json(
        run.triage,
        {
            "schema_version": "0.1",
            "run_id": run.root.name,
            "objective_review": {
                "declared_objective": "depth",
                "supported": False,
                "surfaces": [
                    {"name": "sealed", "evidence": ["x"], "weight": {"candidates": 9, "bytes": 9}}
                ],
            },
            "dispositions": [],
        },
    )
    got = summary.objective(run)
    assert got.declared == "breadth"
    assert got.supported is True
    assert [s.name for s in got.surfaces] == ["search", "tickets"]


def test_objective_absent_when_the_stage_has_not_run(tmp_path):
    """`upto="intake"` writes `manifest.json` and `00-inputs/` and nothing else,
    so there is no `00-objective.json` for this to find."""
    run = build_toy_run(tmp_path / "runs", upto="intake")
    assert not run.objective.exists(), "the fixture must not already carry the artifact"
    got = summary.objective(RunPaths(run.root))
    assert isinstance(got, summary.Absent)
    assert got.what == "00-objective.json"


def test_objective_survives_a_review_that_is_not_a_mapping(tmp_path):
    """`_mapping`'s measured shape: `"objective_review": "nope"` reached `.get`.

    The declared objective renders empty rather than the section vanishing --
    `predicted_surface_count` is still legible, and it is the half of the
    divergence check this document is the only source of.
    """
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    write_json(
        run.objective,
        {"schema_version": "0.1", "run_id": run.root.name, "objective_review": "nope"},
    )
    got = summary.objective(run)
    assert got.declared == ""
    assert got.surfaces == []
    assert got.supported is None


def _triage_document(run_id: str, dispositions: list) -> dict:
    return {"schema_version": "0.1", "run_id": run_id, "dispositions": dispositions}


def test_dispositions_counts_admits_and_groups_declines_by_reason(tmp_path):
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    write_json(
        run.triage,
        _triage_document(
            run.root.name,
            [
                {"candidate_id": "a", "disposition": "admit", "priority": 1, "reason": "keep"},
                {
                    "candidate_id": "b",
                    "disposition": "decline",
                    "reason_code": "near_duplicate",
                    "reason": "same as a",
                },
                {
                    "candidate_id": "c",
                    "disposition": "decline",
                    "reason_code": "near_duplicate",
                    "reason": "same as a too",
                },
                {
                    "candidate_id": "d",
                    "disposition": "decline",
                    "reason_code": "implementation_detail",
                    "reason": "build only",
                },
            ],
        ),
    )
    got = summary.dispositions(run)
    assert got.admit_count == 1
    assert got.decline_count == 3
    assert sorted(got.declines_by_reason) == ["implementation_detail", "near_duplicate"]
    assert len(got.declines_by_reason["near_duplicate"]) == 2


def test_dispositions_lists_admits_in_the_order_intake_will_materialise_them(tmp_path):
    """`intake.admit_sort_key`, measured: priority order, not document order.

    The counts asserted above are order-blind, so an unsorted `admits` passes
    every one of them. The order is the whole reason this reuses the pipeline's
    own key rather than spelling a sort here: the admits a human reads at gate 0
    are the sequence `admit_from_triage` will register, and the collision
    suffixes `_unique_artifact_id` hands out depend on it -- a page listing them
    in a different order would misdescribe which candidate became which
    `artifact_id`.
    """
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    write_json(
        run.triage,
        _triage_document(
            run.root.name,
            [
                {"candidate_id": "third", "disposition": "admit", "priority": 3, "reason": "r"},
                {"candidate_id": "first", "disposition": "admit", "priority": 1, "reason": "r"},
                {"candidate_id": "second", "disposition": "admit", "priority": 2, "reason": "r"},
            ],
        ),
    )
    got = summary.dispositions(run)
    assert [d["candidate_id"] for d in got.admits] == ["first", "second", "third"]


def test_dispositions_does_not_raise_on_a_priority_that_is_not_an_integer(tmp_path):
    """A string `priority` beside an integer one -- the shape `admit_sort_key`
    exists for, and the reason there is no `try` around that sort.

    Measured before that function existed: `sorted` raised `TypeError: '<' not
    supported between instances of 'int' and 'str'`, which nothing between here
    and `main()` catches. A non-integer priority sorts as if absent, so it lands
    after the integers rather than being dropped -- the candidate is still on the
    page, which is what a reader needs to see the malformation at all.
    """
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    write_json(
        run.triage,
        _triage_document(
            run.root.name,
            [
                {"candidate_id": "stringly", "disposition": "admit", "priority": "1"},
                {"candidate_id": "numeric", "disposition": "admit", "priority": 2},
            ],
        ),
    )
    got = summary.dispositions(run)
    assert [d["candidate_id"] for d in got.admits] == ["numeric", "stringly"]


def test_dispositions_orders_the_decline_groups_by_reason_code(tmp_path):
    """The group order, which `sorted(got.declines_by_reason)` above cannot see.

    Wrapping a comparison in `sorted()` makes it pass whatever order the mapping
    is in, so that assertion is satisfied by insertion order -- and insertion
    order is whatever the triage record happened to list, which two runs of the
    same pipeline need not share. This iterates the mapping itself. The three
    codes are inserted in reverse alphabetical order so file order and sorted
    order disagree.
    """
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    write_json(
        run.triage,
        _triage_document(
            run.root.name,
            [
                {"candidate_id": "a", "disposition": "admit", "priority": 1},
                {"candidate_id": "s", "disposition": "decline", "reason_code": "superseded"},
                {"candidate_id": "n", "disposition": "decline", "reason_code": "near_duplicate"},
                {"candidate_id": "i", "disposition": "decline", "reason_code": "generated"},
            ],
        ),
    )
    got = summary.dispositions(run)
    assert list(got.declines_by_reason) == ["generated", "near_duplicate", "superseded"]


def test_dispositions_groups_a_decline_with_no_reason_code_the_way_gate_0_does(tmp_path):
    """`reason_code` is optional in triage-0.1.json, so this shape is *valid*.

    Not a malformation: a decline is required to carry `reason` and `authority`
    and may carry no `reason_code` at all. `gate_brief`'s gate 0 renders that
    group as `?`, and this page reads the same field for the same human at the
    same gate, so it says the same thing -- an empty group label would read as a
    rendering bug rather than as a fact about the record.
    """
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    write_json(
        run.triage,
        _triage_document(
            run.root.name,
            [
                {"candidate_id": "a", "disposition": "admit", "priority": 1},
                {"candidate_id": "b", "disposition": "decline", "reason": "no code given"},
            ],
        ),
    )
    got = summary.dispositions(run)
    assert list(got.declines_by_reason) == ["?"]
    assert got.decline_count == 1


def test_dispositions_survives_a_non_dict_member(tmp_path):
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    write_json(
        run.triage,
        {
            "schema_version": "0.1",
            "run_id": run.root.name,
            "dispositions": ["oops-a-string", {"candidate_id": "a", "disposition": "admit"}],
        },
    )
    got = summary.dispositions(run)
    assert got.admit_count == 1, "the string member is dropped, not raised on"


def test_dispositions_without_a_triage_record_is_absent(tmp_path):
    empty = tmp_path / "run-empty"
    empty.mkdir()
    got = summary.dispositions(RunPaths(empty))
    assert isinstance(got, summary.Absent)
    assert got.what == "00-triage.json"


def _projection(projection_id: str, closes: list[str], statement: str) -> dict:
    """A schema-shaped projection, since triage-0.1.json requires seven fields.

    Only `projection_id`, `closes` and `wanted.statement` are read by
    `deficiencies`; the other four are required by the schema, and building them
    here is what lets one test validate the whole document rather than trusting a
    literal.
    """
    return {
        "projection_id": projection_id,
        "closes": closes,
        "sources": [{"candidate_id": "api-json", "digest_note": "the tool block"}],
        "wanted": {"kind": "mcp_tool_schema", "statement": statement, "why": "seeding needs it"},
        "method": {"confidence": "high", "steps": ["import the module"]},
        "acceptance": {"classifies_as": "mcp_tool_schema", "prose": "one document"},
        "boundary": "invents no result shape no trace exercises",
    }


def test_deficiencies_pairs_each_with_its_projection(tmp_path):
    """The pairing, on a document validated against triage-0.1.json.

    The schema names are `deficiency_id` on a deficiency and `closes` -- a list
    of deficiency ids -- on a projection, and both objects are
    `additionalProperties: false`, so a reading keyed on anything else finds
    nothing on a real run while passing happily against a hand-written literal.
    Validating the fixture is what makes this test a lock on the field names
    rather than on one spelling of them.
    """
    from rubrica.artifacts import write_json
    from rubrica.validate import validate_artifact

    run = build_toy_run(tmp_path / "runs", upto="intake")
    write_json(
        run.triage,
        {
            "schema_version": "0.1",
            "run_id": run.root.name,
            # Required by triage-0.1.json, and unread by `deficiencies`: the seal
            # writes all six top-level fields, so a fixture that validates has to
            # carry it even though this section never looks at it.
            "objective_review": _objective_document(run.root.name)["objective_review"],
            "dispositions": [
                {
                    "candidate_id": "api-json",
                    "disposition": "admit",
                    "priority": 1,
                    "reason": "the tool block",
                    "authority": "triage",
                }
            ],
            "deficiencies": [
                {"deficiency_id": "def-1", "subject": "errors", "statement": "no error path"}
            ],
            "projections": [_projection("prj-1", ["def-1"], "author one error trace")],
        },
    )
    assert validate_artifact(run.triage, "triage") == [], (
        "the fixture must be the shape triage-seal actually writes"
    )
    got = summary.deficiencies(run)
    assert [d.id_ for d in got] == ["def-1"]
    assert got[0].statement == "no error path"
    assert "author one error trace" in got[0].projection
    assert "prj-1" in got[0].projection, "the id is the argument adopt-projection takes"


def test_deficiencies_renders_the_empty_string_for_one_nothing_would_close(tmp_path):
    """A deficiency with no projection, which is the one worth reading.

    Asserted explicitly because it is the informative case: a projection is the
    plan for closing a deficiency, so a deficiency with none is the one gate 0
    has to rule on unaided. The second deficiency is paired, so "everything
    renders empty" cannot pass.
    """
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    write_json(
        run.triage,
        {
            "schema_version": "0.1",
            "run_id": run.root.name,
            "dispositions": [],
            "deficiencies": [
                {"deficiency_id": "def-1", "subject": "errors", "statement": "no error path"},
                {"deficiency_id": "def-2", "subject": "auth", "statement": "no auth model"},
            ],
            "projections": [_projection("prj-2", ["def-2"], "author an auth note")],
        },
    )
    got = {d.id_: d.projection for d in summary.deficiencies(run)}
    assert got["def-1"] == ""
    assert "author an auth note" in got["def-2"]


def test_deficiencies_reads_a_sealed_run_once_rather_than_twice(tmp_path):
    """The double-count a two-document union produces on every sealed run.

    `seal.seal` *copies* 00-audit.json's deficiencies and projections into
    00-triage.json (enriched with `closed_by` and `satisfied_by` from any
    adoption), so past `triage-seal` both files carry the same deficiency and
    reading both would list each one twice. That is the common case, not an edge:
    every run that reaches gate 0 has been sealed.

    The fixture is sealed by the real `seal.seal` over a patched audit part,
    rather than by two hand-written documents that merely resemble its output, so
    the duplication under test is the one the pipeline actually produces.
    """
    from rubrica.artifacts import read_json, write_json
    from rubrica.seal import seal

    run = build_toy_run(tmp_path / "runs", upto="triage-audit")
    audit = read_json(run.audit)
    audit["deficiencies"] = [
        {"deficiency_id": "def-1", "subject": "errors", "statement": "no error path"}
    ]
    audit["projections"] = [_projection("prj-1", ["def-1"], "author one error trace")]
    write_json(run.audit, audit)
    _, findings = seal(run)
    assert findings == [], "; ".join(f.message for f in findings)
    assert [d["deficiency_id"] for d in read_json(run.triage)["deficiencies"]] == ["def-1"], (
        "the seal must have copied the deficiency, or there is no duplication to avoid"
    )
    got = summary.deficiencies(run)
    assert [d.id_ for d in got] == ["def-1"]
    assert "author one error trace" in got[0].projection


def test_deficiencies_falls_back_to_the_audit_before_the_seal_has_run(tmp_path):
    """The audit part is the only source between `triage-audit` and `triage-seal`.

    Preferring the sealed record must not mean ignoring the part it is assembled
    from: a run stopped at the audit pass has deficiencies to read and no
    00-triage.json to read them out of, and the audit's `deficiencies` and
    `projections` are the same two schema objects under the same names.
    """
    from rubrica.artifacts import read_json, write_json
    from rubrica.validate import validate_artifact

    run = build_toy_run(tmp_path / "runs", upto="triage-audit")
    assert not run.triage.exists(), "the fixture must stop before the seal"
    audit = read_json(run.audit)
    audit["deficiencies"] = [
        {"deficiency_id": "def-1", "subject": "errors", "statement": "no error path"}
    ]
    audit["projections"] = [_projection("prj-1", ["def-1"], "author one error trace")]
    write_json(run.audit, audit)
    assert validate_artifact(run.audit, "audit") == []
    got = summary.deficiencies(run)
    assert [d.id_ for d in got] == ["def-1"]
    assert "author one error trace" in got[0].projection


def test_deficiencies_on_a_run_without_triage_is_empty(tmp_path):
    empty = tmp_path / "run-empty"
    empty.mkdir()
    assert summary.deficiencies(RunPaths(empty)) == []


def test_deficiencies_survives_a_projection_whose_closes_is_not_a_list_of_ids(tmp_path):
    """`_strings` on `closes`, at the two shapes that reach it.

    `closes` is a *list* of deficiency ids, so the pairing iterates it -- and a
    hand-edited `"closes": "def-1"` is a string whose characters would each be
    taken for a deficiency id, while a list member that is not a string cannot
    match an id that is and can be unhashable (`setdefault` raises TypeError on a
    list key). Both must leave the deficiency rendered and unpaired rather than
    raising, and the third projection is well-formed so that "paired nothing"
    cannot pass either.
    """
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    string_closes = _projection("prj-str", [], "unreachable by a string")
    string_closes["closes"] = "def-1"
    list_closes = _projection("prj-list", [], "unreachable by a list")
    list_closes["closes"] = [["def-1"]]
    write_json(
        run.triage,
        {
            "schema_version": "0.1",
            "run_id": run.root.name,
            "dispositions": [],
            "deficiencies": [
                {"deficiency_id": "def-1", "subject": "errors", "statement": "no error path"},
                {"deficiency_id": "def-2", "subject": "auth", "statement": "no auth model"},
            ],
            "projections": [
                string_closes,
                list_closes,
                _projection("prj-2", ["def-2"], "author an auth note"),
            ],
        },
    )
    got = {d.id_: d.projection for d in summary.deficiencies(run)}
    assert got["def-1"] == ""
    assert "author an auth note" in got["def-2"]


@pytest.mark.parametrize("token", ["Infinity", "-Infinity", "NaN"])
def test_inputs_reads_a_non_finite_bytes_as_zero(tmp_path, token):
    """The three bare tokens `json.loads` accepts, reached through a real manifest.

    Not a unit call on `_as_int`: the promise this measures is the module's, that
    nothing raises on a readable run's *content*, and only the artifact path
    proves it. `artifacts.read_json` calls `json.loads` with defaults, so
    `Infinity`, `-Infinity` and `NaN` are all accepted as bare tokens and arrive
    as floats -- and `int(inf)` raises **OverflowError**, which is in neither
    `TypeError` nor `ValueError`. Measured before the finite guard existed:
    `summary.inputs()` raised `OverflowError: cannot convert float infinity to
    integer` on a manifest that `validate --stage intake` is the right command to
    complain about. `NaN` is in the list because it is the sibling that already
    worked (`int(nan)` raises ValueError), so the parametrisation records which
    of the three the guard actually changed.

    The token is written into the file text rather than through `write_json`, and
    asserted present, because a test whose fixture quietly stored the string
    `"Infinity"` would measure `int()` on a string instead of on a float.
    """
    from rubrica.artifacts import read_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    manifest = read_json(run.manifest)
    manifest["inputs"][0]["bytes"] = "__TOKEN__"
    run.manifest.write_text(
        json.dumps(manifest, indent=2).replace('"__TOKEN__"', token), encoding="utf-8"
    )
    assert f": {token}" in run.manifest.read_text(encoding="utf-8"), (
        "the artifact must hold the bare token, not a quoted string"
    )
    got = summary.inputs(run)
    assert got.rows[0].bytes_ == 0
    assert got.total_bytes == sum(e["bytes"] for e in manifest["inputs"][1:])


def test_deficiencies_carries_the_closed_by_the_record_records(tmp_path):
    """`closed_by`, the field that separates a closed deficiency from an open one.

    Read because the page is otherwise unable to say the difference: `seal.seal`
    stamps `closed_by` onto a deficiency when a human adopts a projection that
    closes it, and gate 0's text brief renders exactly that distinction
    (`brief.py`, `OPEN` versus `closed by <projection_id>`). Without it an
    adopted-and-closed deficiency renders identically to one nothing has answered,
    which inverts what the section is read for.

    The empty string for an open deficiency, not `None`, matching the other three
    fields: absence is a rendered blank, and `str(...)` over a hand-edited
    non-string keeps the column total.

    The fixture is validated against triage-0.1.json -- all six required top-level
    fields, `dispositions` non-empty as its `minItems: 1` requires -- because the
    whole point of the field is its schema spelling.
    """
    from rubrica.artifacts import write_json
    from rubrica.validate import validate_artifact

    run = build_toy_run(tmp_path / "runs", upto="intake")
    closed = _projection("prj-1", ["def-1"], "author one error trace")
    closed["satisfied_by"] = "prj-1-json"
    write_json(
        run.triage,
        {
            "schema_version": "0.1",
            "run_id": run.root.name,
            "objective_review": _objective_document(run.root.name)["objective_review"],
            "dispositions": [
                {
                    "candidate_id": "api-json",
                    "disposition": "admit",
                    "priority": 1,
                    "reason": "the tool block",
                    "authority": "triage",
                }
            ],
            "deficiencies": [
                {
                    "deficiency_id": "def-1",
                    "subject": "errors",
                    "statement": "no error path",
                    "closed_by": "prj-1",
                },
                {"deficiency_id": "def-2", "subject": "auth", "statement": "no auth model"},
            ],
            "projections": [closed, _projection("prj-2", ["def-2"], "author an auth note")],
        },
    )
    assert validate_artifact(run.triage, "triage") == [], (
        "the fixture must be the shape triage-seal actually writes"
    )
    got = {d.id_: d for d in summary.deficiencies(run)}
    assert got["def-1"].closed_by == "prj-1"
    assert got["def-2"].closed_by == "", "an open deficiency renders a blank, not None"


def _sealed(run) -> dict:
    """The sealed world model as it sits on disk.

    Read rather than hand-written: every assertion below about a count or a
    collection compares against what the fixture actually sealed, and an
    expectation typed out here would only ever agree with itself.
    """
    return json.loads(run.world_model.read_text(encoding="utf-8"))


def test_world_model_counts_every_kind(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    got = summary.world_model(run)
    for kind in ("capabilities", "entities", "actors", "goals", "gaps", "contradictions"):
        assert kind in got.counts, f"{kind} is a world-model collection"
    assert got.counts["capabilities"] > 0


def test_world_model_counts_are_the_lengths_of_the_sealed_collections(tmp_path):
    """Every count against the fixture's own arrays, not one spot check.

    The presence test above passes on a `world_model` that returns 0 for five of
    the six collections -- measured: replacing the length with the literal 0
    leaves it green, because only `capabilities` is asserted non-empty there.

    The key set is derived from the sealed document rather than re-typed, so a
    collection added to world-model-0.1.json and not to
    `_WORLD_MODEL_COLLECTIONS` goes red here: the three non-collection keys are
    named, and everything else the document carries must be counted.

    `gaps` is asserted at exactly 0 because that is the fixture's own value -- it
    is what proves a zero count still renders as a row rather than being dropped
    with the key.
    """
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    sealed = _sealed(run)
    got = summary.world_model(run)
    assert set(got.counts) == set(sealed) - {"schema_version", "target", "denominator"}
    assert got.counts == {kind: len(sealed[kind]) for kind in got.counts}
    assert got.counts["gaps"] == 0
    assert sorted(kind for kind, n in got.counts.items() if n) == [
        "actors",
        "capabilities",
        "contradictions",
        "entities",
        "goals",
    ], "five of the six collections are non-empty in the toy world model"
    assert got.target == sealed["target"]
    assert got.denominator == sealed["denominator"]


@pytest.mark.parametrize(
    "collection", ["capabilities", "entities", "actors", "goals", "gaps", "contradictions"]
)
def test_world_model_counts_a_collection_that_is_not_a_list_as_zero(tmp_path, collection):
    """`_dicts` at each of the six keys, one parametrisation per key.

    `"actors": "nope"` is a four-character string, and `len()` on it counts four
    actors. Parametrised rather than asserted once because the six keys are a
    comprehension over a tuple -- the copy-paste slip this shape invites is a key
    spelled wrong, and only a case per key can see it. The other five counts are
    asserted unchanged, so a guard that swallowed the whole document would go red.
    """
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    sealed = _sealed(run)
    sealed[collection] = "nope"
    write_json(run.world_model, sealed)
    got = summary.world_model(run)
    assert got.counts[collection] == 0
    assert {kind: n for kind, n in got.counts.items() if kind != collection} == {
        kind: len(_sealed(run)[kind]) for kind in got.counts if kind != collection
    }


def test_world_model_survives_a_target_and_denominator_that_are_not_mappings(tmp_path):
    """Both are rendered key by key, so a truthy non-dict is the shape that raises.

    `brief._mapping`'s docstring records it measured at three gates: the
    `x.get("y") or {}` idiom substitutes only on a falsy value, so `"target":
    "nope"` reaches `.get` and raises AttributeError. The counts are asserted
    still populated, because the collections and these two fields are read off the
    same document and one malformation must not take the section with it.
    """
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    sealed = _sealed(run)
    sealed["target"] = "nope"
    sealed["denominator"] = ["also nope"]
    write_json(run.world_model, sealed)
    got = summary.world_model(run)
    assert got.target == {}
    assert got.denominator == {}
    assert got.counts["capabilities"] == len(sealed["capabilities"])


def test_world_model_before_the_seal_is_absent(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="extract")
    assert isinstance(summary.world_model(run), summary.Absent)


def test_world_model_absent_names_the_artifact_it_looked_for(tmp_path):
    """`Absent("")` satisfies an isinstance check; the page needs the name."""
    run = build_toy_run(tmp_path / "runs", upto="extract")
    assert summary.world_model(run).what == "01-world-model.json"


def test_world_model_survives_a_malformed_world_model(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    run.world_model.write_text("{not json", encoding="utf-8")
    assert isinstance(summary.world_model(run), summary.Absent)


def test_utilisation_totals_and_names_uncited_artifacts(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    got = summary.utilisation(run)
    assert got.total > 0
    assert got.cited <= got.total
    assert got.pct == pytest.approx(got.cited / got.total * 100)
    for artifact_id in got.uncited:
        matching = [a for a in got.per_artifact if a["artifact_id"] == artifact_id]
        assert matching and matching[0]["cited"] == 0


def test_utilisation_sums_the_report_rather_than_recomputing(tmp_path):
    """The numbers come from `claim_utilisation`, the one definition in this build.

    Asserted against that module's own output, because the page must not disagree
    with the `claim-utilisation` subcommand a reader runs beside it or with
    `refs.check_claim_utilisation`, which shares the arithmetic. The rows are
    asserted identical objects-in-order, so re-sorting or rebuilding them here
    goes red; the columns are asserted as its sums.

    The measured totals are pinned alongside: 9/9, 8/8 and 2/2 on the toy
    fixture, 19 of 19 overall. Derived sums alone would agree with a `utilisation`
    that summed the wrong column, since cited == total on this fixture.
    """
    from rubrica.utilisation import claim_utilisation

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    report = claim_utilisation(run)
    got = summary.utilisation(run)
    assert got.per_artifact == report["artifacts"]
    assert got.cited == sum(a["cited"] for a in report["artifacts"])
    assert got.total == sum(a["total"] for a in report["artifacts"])
    assert (got.cited, got.total) == (19, 19), "the toy world model cites all 19 claims"
    assert got.pct == pytest.approx(100.0)


def test_utilisation_names_an_artifact_the_world_model_cites_nothing_of(tmp_path):
    """`uncited`, which the toy fixture cannot reach unaltered.

    Measured: the sealed toy world model cites every claim of all three inputs
    (9/9, 8/8, 2/2), so the loop in
    test_utilisation_totals_and_names_uncited_artifacts has an empty body and the
    list ships unexercised -- and it is the entire input to the
    `uncited-artifacts` flag.

    trace-json is emptied of citations here. Its claims are cited in two places
    and both must go: a capability's `claims` array, and the sealed
    contradiction's `claim_b` -- `utilisation._cited_claim_ids` counts a
    contradiction's two sides as citations on purpose, and its comment says why,
    so dropping only the capability's reference would leave trace-json at 1 of 2
    rather than 0.

    The result is validated against world-model-0.1.json, since a fixture that
    could not exist would prove nothing about a real run.
    """
    from rubrica.artifacts import write_json
    from rubrica.validate import validate_artifact

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    sealed = _sealed(run)
    for group in ("capabilities", "entities", "actors", "goals"):
        for member in sealed[group]:
            member["claims"] = [c for c in member["claims"] if not c.startswith("clm-trace-")]
    sealed["contradictions"] = []
    write_json(run.world_model, sealed)
    assert validate_artifact(run.world_model, "world-model") == [], (
        "an uncited input must be produced by a world model that could really exist"
    )
    got = summary.utilisation(run)
    assert got.uncited == ["trace-json"]
    assert {a["artifact_id"]: a["cited"] for a in got.per_artifact}["trace-json"] == 0
    assert (got.cited, got.total) == (17, 19), "trace-json's two claims stopped being cited"
    assert got.pct == pytest.approx(17 / 19 * 100)


def test_utilisation_reports_no_percentage_when_no_claim_was_extracted(tmp_path):
    """The `if total else None` guard, at the one shape that reaches it.

    An empty `claims` array is schema-valid -- claims-0.1.json sets no minItems --
    and `claim_utilisation` reports such a file as a row with total 0. So a run
    whose claims files are all empty divides by zero here without the guard, and
    the fixture is asserted valid to show the shape needs no hand edit.

    `None` rather than 0.0 because 0% asserts every claim was dropped, which is a
    judgment about the reconcile passes, while "nothing was extracted to cite" is
    a different fact about the run.

    The 0-of-0 artifact is asserted **absent** from `uncited` while still present
    in `per_artifact`, which is the distinction `refs.check_claim_utilisation`
    already draws: its `entry["total"]` guard exempts a claims file with zero
    claims, because `rb-extract` is allowed to produce nothing for an input with
    nothing to extract, and the comment at that gate says the exemption is not a
    hole precisely because the artifact still shows in the report at 0/0. Naming it
    uncited here would make the `uncited-artifacts` flag fire on inputs the gate
    exempts.
    """
    from rubrica.artifacts import write_json
    from rubrica.paths import list_json
    from rubrica.validate import validate_artifact

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    for path in list_json(run.claims_dir):
        path.unlink()
    empty = run.claims_dir / "empty.json"
    write_json(empty, {"schema_version": "0.1", "artifact_id": "empty", "claims": []})
    assert validate_artifact(empty, "claims") == [], "an empty claims file is a valid one"
    got = summary.utilisation(run)
    assert (got.cited, got.total) == (0, 0)
    assert got.pct is None, "0.0 would assert every claim was dropped"
    assert got.uncited == [], "a 0-of-0 input is the case check_claim_utilisation exempts"
    assert [a["artifact_id"] for a in got.per_artifact] == ["empty"], (
        "exempt from the flag, still on the page"
    )


def test_utilisation_before_the_seal_is_absent(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="extract")
    assert isinstance(summary.utilisation(run), summary.Absent)


def test_utilisation_absent_says_the_seal_has_not_run(tmp_path):
    """The `what` distinguishes the two readings of an empty report.

    `claim_utilisation` returns no artifacts when there is no world model to
    resolve citations against, which means "the seal has not run" and not "no
    input was cited" -- so the absence has to say which, or the page states the
    second about a run in the first state.
    """
    run = build_toy_run(tmp_path / "runs", upto="extract")
    assert summary.utilisation(run).what == "claim utilisation (no world model yet)"


def test_gaps_carry_every_field_including_the_blocks_array(tmp_path):
    """Rewritten from the plan's version, whose fixture cannot reach its assertion.

    Measured: `build_toy_run(upto="reconcile-seal")` seals `"gaps": []`, so the
    plan's `assert got, "the toy world model carries a gap"` fails on the very
    fixture it names. Two gaps are written into the sealed model here instead, and
    the result is validated against world-model-0.1.json because the schema
    spelling is the point: `why_it_matters` is what a gap carries, and `why` is
    what the dataclass calls it -- reading `why` off the record yields the empty
    string on every real run, and no assertion over the fixture's own gaps would
    catch that if the fixture were hand-written to match the dataclass.

    The order is asserted as the document's, not sorted: `blocks` is what a reader
    scans, and re-ordering the rows would disagree with the world model a reader
    opens beside the page.
    """
    from rubrica.artifacts import write_json
    from rubrica.validate import validate_artifact

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    sealed = _sealed(run)
    sealed["gaps"] = [
        {
            "id": "gap-not-found",
            "subject": "get_ticket",
            "unknown": "what get_ticket returns for an id that does not exist",
            "why_it_matters": "no scenario on the missing branch has a stated gold answer",
            "blocks": ["propose", "score"],
        },
        {
            "id": "gap-auth",
            "subject": "authentication",
            "unknown": "whether any call requires a token",
            "why_it_matters": "an unauthenticated seed may be exercising a different target",
            "blocks": ["instantiate"],
        },
    ]
    write_json(run.world_model, sealed)
    assert validate_artifact(run.world_model, "world-model") == [], (
        "the fixture must be the shape reconcile-seal actually writes"
    )
    got = summary.gaps(run)
    assert [gap.id_ for gap in got] == ["gap-not-found", "gap-auth"], "the document's own order"
    assert got[0].subject == "get_ticket"
    assert got[0].unknown == "what get_ticket returns for an id that does not exist"
    assert got[0].why == sealed["gaps"][0]["why_it_matters"], "why reads why_it_matters"
    assert got[0].blocks == ["propose", "score"]
    assert got[1].blocks == ["instantiate"], "each gap keeps its own blocks, not the first's"


def test_gaps_without_a_world_model_is_empty(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="extract")
    assert summary.gaps(run) == []


def test_gaps_on_a_sealed_model_recording_none_is_empty(tmp_path):
    """The fixture's own state, asserted rather than assumed.

    `world_model` reports `gaps: 0` for this run and `Absent` for the run above,
    which is what makes an empty list an honest answer in both cases -- the
    section that says which of the two it is is a different section.
    """
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    assert _sealed(run)["gaps"] == []
    assert summary.gaps(run) == []


@pytest.mark.parametrize("bad", ["gap-1", {"gap-1": {}}, ["oops"], [None], 7])
def test_gaps_on_a_malformed_gaps_field_is_empty(tmp_path, bad):
    """`_dicts` at both depths: not-a-list, and a list of non-dicts.

    `"gaps": "gap-1"` iterates as five characters, and `"gaps": ["oops"]` reaches
    `.get` on a string -- the measured AttributeError `brief._dicts` exists for.
    """
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    sealed = _sealed(run)
    sealed["gaps"] = bad
    write_json(run.world_model, sealed)
    assert summary.gaps(run) == []


def test_contradictions_tallies_resolution_nested_inside_each_part(tmp_path):
    """The measured trap: resolution lives inside contradictions[], not at the
    top level of the part. Reading it at the top level tallies {"null": N}.

    The fixture's own six parts are cleared first -- measured:
    `build_toy_run(upto="reconcile-seal")` ships six parts holding one
    contradiction (`preferred_a`), so the counts asserted here would be 3 and 8
    against the untouched directory. The subject of this test is the nesting, not
    the fixture's parts, and
    test_contradictions_tallies_the_fixtures_own_parts_in_full covers those.
    """
    from rubrica.artifacts import write_json
    from rubrica.paths import list_json

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    run.contradictions_dir.mkdir(parents=True, exist_ok=True)
    for path in list_json(run.contradictions_dir):
        path.unlink()
    write_json(
        run.contradictions_dir / "subj-a.json",
        {
            "schema_version": "0.1",
            "subject_id": "subj-a",
            "contradictions": [
                {"id": "con-1", "resolution": "unresolved", "statement": "x"},
                {"id": "con-2", "resolution": "preferred_a", "statement": "y"},
            ],
        },
    )
    write_json(
        run.contradictions_dir / "subj-b.json",
        {"schema_version": "0.1", "subject_id": "subj-b", "contradictions": []},
    )
    got = summary.contradictions(run)
    assert got.total == 2
    assert got.parts_swept == 2
    assert got.by_resolution["unresolved"] == 1
    assert got.by_resolution["preferred_a"] == 1
    assert "null" not in got.by_resolution
    # The tally must hold nothing but what the two parts recorded, plus the
    # `unresolved` seed. A top-level read of `resolution` adds an
    # `(unrecorded)` group of 2 while leaving every assertion above green except
    # the two group counts, so the exact-dict form is what makes this a lock in
    # both directions.
    assert got.by_resolution == {"preferred_a": 1, "unresolved": 1}
    assert list(got.by_resolution) == sorted(got.by_resolution), "sorted, so the page is diffable"


def test_contradictions_tallies_the_fixtures_own_parts_in_full(tmp_path):
    """The unaltered fixture, exactly: 1 contradiction across 6 swept parts.

    Five of those parts record an empty `contradictions` array, which is a real
    record and not an absence -- contradictions-part-0.1.json says so where it
    declines to set `minItems`, and `parts_swept` is what separates "swept and
    clean" from "never swept". A `parts_swept` counting only the parts that found
    something would read 1 here and would be wrong about five subjects.
    """
    from rubrica.paths import list_json

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    assert len(list_json(run.contradictions_dir)) == 6, "the fixture ships six parts"
    got = summary.contradictions(run)
    assert got.total == 1
    assert got.parts_swept == 6
    assert got.by_resolution == {"preferred_a": 1, "unresolved": 0}


def test_contradictions_names_unresolved_at_zero(tmp_path):
    """brief.py's ruling: unresolved is named at zero whenever the tally renders
    at all, because a reader scanning for it must not have to infer absence."""
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    run.contradictions_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        run.contradictions_dir / "subj-a.json",
        {
            "schema_version": "0.1",
            "subject_id": "subj-a",
            "contradictions": [{"id": "con-1", "resolution": "both_possible"}],
        },
    )
    got = summary.contradictions(run)
    assert got.by_resolution["unresolved"] == 0


def test_contradictions_labels_a_member_whose_resolution_was_hand_removed(tmp_path):
    """The `or "(unrecorded)"` fallback, and the malformation one level deeper.

    `resolution` is required by contradictions-part-0.1.json, so a member without
    one is hand-edited -- and an empty group label on the page would read as a
    rendering bug rather than as a fact about the record, which is the ruling
    `dispositions` already makes for a decline carrying no reason code. The
    non-dict member and the non-list array are `_dicts`' two measured shapes: both
    are counted as nothing rather than raising, and the part is still swept.
    """
    from rubrica.artifacts import write_json
    from rubrica.paths import list_json

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    for path in list_json(run.contradictions_dir):
        path.unlink()
    write_json(
        run.contradictions_dir / "subj-a.json",
        {
            "schema_version": "0.1",
            "subject_id": "subj-a",
            "contradictions": [{"id": "con-1"}, {"id": "con-2", "resolution": ""}, "oops"],
        },
    )
    write_json(
        run.contradictions_dir / "subj-b.json",
        {"schema_version": "0.1", "subject_id": "subj-b", "contradictions": "nope"},
    )
    got = summary.contradictions(run)
    assert got.total == 2, "the string member is dropped, the two objects are counted"
    assert got.by_resolution == {"(unrecorded)": 2, "unresolved": 0}
    assert got.parts_swept == 2, "a part nothing could be read out of was still swept"


def test_contradictions_without_the_directory_is_absent(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="extract")
    assert not run.contradictions_dir.exists(), "the fixture level under test writes no parts"
    assert isinstance(summary.contradictions(run), summary.Absent)


def test_contradictions_absent_names_the_directory_it_looked_for(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="extract")
    assert summary.contradictions(run).what == "01-contradictions/"


def test_contradictions_on_an_empty_directory_is_absent(tmp_path):
    """A directory with no part in it, which is not the same as a swept run.

    `reconcile-contradict` writes one file per subject, so an empty directory has
    the same meaning for this section as no directory -- and a `Contradictions`
    reporting 0 of 0 would say the sweep happened and found nothing.
    """
    from rubrica.paths import list_json

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    for path in list_json(run.contradictions_dir):
        path.unlink()
    assert isinstance(summary.contradictions(run), summary.Absent)


def test_contradictions_on_an_unreadable_directory_is_absent(tmp_path):
    """The `except` around `list_json`, which raises `UsageError` -- not `OSError`.

    That is why this handler cannot be the `except OSError` the spine uses:
    `paths.list_json` catches the OSError itself and re-raises it as a
    `UsageError`, a ValueError subclass, so an unreadable directory would escape
    an OSError-only guard and take the whole page with it.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    run.contradictions_dir.chmod(0o000)
    try:
        got = summary.contradictions(run)
        assert isinstance(got, summary.Absent)
        assert got.what == "01-contradictions/", "both absence branches name the same directory"
    finally:
        run.contradictions_dir.chmod(0o755)


def test_contradictions_survives_a_part_that_is_not_readable(tmp_path):
    """One unreadable part degrades one part, not the tally.

    `_quietly` returns None for it and `_mapping` makes that an empty document, so
    the sweep count still includes the file -- the run did write it -- while its
    contradictions are simply not readable. The five other parts are still tallied,
    which is the control: without it this would pass on a `contradictions` that
    had stopped reading anything.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    from rubrica.paths import list_json

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    holding = run.contradictions_dir / "sub-cap-get-ticket.json"
    assert holding.is_file(), "the one fixture part that records a contradiction"
    holding.chmod(0o000)
    try:
        got = summary.contradictions(run)
        assert got.parts_swept == len(list_json(run.contradictions_dir))
        assert got.total == 0, "the only recorded contradiction lives in the unreadable part"
        assert got.by_resolution == {"unresolved": 0}
    finally:
        holding.chmod(0o644)


# The seven readable-run shapes measured escaping `claim_utilisation` as
# exceptions, each as a mutation of a fully sealed toy run. Driven end to end
# through `summary.utilisation()` rather than through `claim_utilisation` itself:
# the defect this closes is that a report which "never raises on a readable run's
# content" was calling a function that does, and only the composed call proves the
# guard is in the path the page actually takes. `id` is the parametrisation label
# and the escape it produced, so a red test names the shape it lost.
def _claims_member_is_a_string(run) -> None:
    from rubrica.artifacts import read_json, write_json
    from rubrica.paths import list_json

    path = list_json(run.claims_dir)[0]
    payload = read_json(path)
    payload["claims"] = ["oops"]
    write_json(path, payload)


def _claim_has_no_id(run) -> None:
    from rubrica.artifacts import read_json, write_json
    from rubrica.paths import list_json

    path = list_json(run.claims_dir)[0]
    payload = read_json(path)
    payload["claims"] = [{"statement": "a claim with no id"}]
    write_json(path, payload)


def _claims_is_not_a_list(run) -> None:
    from rubrica.artifacts import read_json, write_json
    from rubrica.paths import list_json

    path = list_json(run.claims_dir)[0]
    payload = read_json(path)
    payload["claims"] = 7
    write_json(path, payload)


def _group_member_is_a_string(run) -> None:
    from rubrica.artifacts import write_json

    sealed = _sealed(run)
    sealed["goals"] = ["oops"]
    write_json(run.world_model, sealed)


def _contradictions_member_is_a_string(run) -> None:
    from rubrica.artifacts import write_json

    sealed = _sealed(run)
    sealed["contradictions"] = ["oops"]
    write_json(run.world_model, sealed)


def _collection_is_not_a_list(run) -> None:
    from rubrica.artifacts import write_json

    sealed = _sealed(run)
    sealed["capabilities"] = "nope"
    write_json(run.world_model, sealed)


def _claims_dir_is_unreadable(run) -> None:
    run.claims_dir.chmod(0o000)


@pytest.mark.parametrize(
    "break_it",
    [
        pytest.param(_claims_member_is_a_string, id="TypeError-string-indices"),
        pytest.param(_claim_has_no_id, id="KeyError-id"),
        pytest.param(_claims_is_not_a_list, id="TypeError-int-not-iterable"),
        pytest.param(_group_member_is_a_string, id="AttributeError-group-member"),
        pytest.param(_contradictions_member_is_a_string, id="AttributeError-contradiction"),
        pytest.param(_collection_is_not_a_list, id="AttributeError-collection"),
        pytest.param(_claims_dir_is_unreadable, id="UsageError-unreadable-claims-dir"),
    ],
)
def test_utilisation_is_absent_rather_than_raising_on_a_readable_run(tmp_path, break_it):
    """The one hole measured in this module's never-raise promise, at all seven shapes.

    `claim_utilisation` is a report with its own contract and its own callers, and
    it is not total: `utilisation.py` indexes `claim["id"]` bare, `.get`s
    world-model group members bare, and calls `list_json(run.claims_dir)`, whose
    `UsageError` is a ValueError rather than an OSError. Every shape here is a
    *readable* run -- a hand-edited artifact, or a directory permission -- which is
    exactly the class this module promises to render rather than crash on, and one
    of them escaping takes the whole page down.

    Guarded in `summary.py`, not widened in `utilisation.py`: the gate and the
    subcommand share that module's arithmetic, and changing what it raises is a
    change to their contract.
    """
    if os.geteuid() == 0 and break_it is _claims_dir_is_unreadable:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    break_it(run)
    try:
        got = summary.utilisation(run)
        assert isinstance(got, summary.Absent)
        assert got.what == "claim utilisation (01-claims/ or 01-world-model.json unreadable)"
    finally:
        run.claims_dir.chmod(0o755)


def test_utilisation_absent_reads_differently_from_the_no_world_model_absence(tmp_path):
    """Two absences, two readings, so they must not share one string.

    "The seal has not run" is a fact about how far the run got; "something in the
    run could not be read" is a defect in an artifact. A page that rendered the
    same line for both would tell a reader with a broken claims file that their run
    simply had not reached reconcile-seal.
    """
    from rubrica.artifacts import read_json, write_json
    from rubrica.paths import list_json

    unsealed = build_toy_run(tmp_path / "runs", upto="extract")
    broken = build_toy_run(tmp_path / "runs2", upto="reconcile-seal")
    path = list_json(broken.claims_dir)[0]
    payload = read_json(path)
    payload["claims"] = ["oops"]
    write_json(path, payload)
    assert summary.utilisation(unsealed).what != summary.utilisation(broken).what


def test_utilisation_exempts_a_zero_of_zero_input_the_gate_exempts(tmp_path):
    """`uncited` is `check_claim_utilisation`'s predicate, `total and cited == 0`.

    One input is emptied of claims and another is left cited, so the two halves are
    separated: the 0-of-0 input must not be named, the 0-of-N input must be. Without
    the `total` guard `refs.py`'s gate reports one finding here while this page
    would name two inputs, and Task 7's `uncited-artifacts` flag would fire on an
    input `rb-extract` is explicitly allowed to have produced nothing for.
    """
    from rubrica.artifacts import read_json, write_json
    from rubrica.refs import check_claim_utilisation

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    emptied = run.claims_dir / "notes-md.json"
    payload = read_json(emptied)
    payload["claims"] = []
    write_json(emptied, payload)
    sealed = _sealed(run)
    for group in ("capabilities", "entities", "actors", "goals"):
        for member in sealed[group]:
            member["claims"] = [c for c in member["claims"] if not c.startswith("clm-trace-")]
    sealed["contradictions"] = []
    write_json(run.world_model, sealed)
    got = summary.utilisation(run)
    assert got.uncited == ["trace-json"], "0 of 2 is uncited; 0 of 0 is exempt"
    assert {a["artifact_id"] for a in got.per_artifact} == {"api-json", "notes-md", "trace-json"}
    assert [a for a in got.per_artifact if a["artifact_id"] == "notes-md"][0]["total"] == 0
    findings = check_claim_utilisation(run)
    assert [f.message for f in findings] == [
        "no world-model element cites any claim from trace-json (2 claims)"
    ], "the page names exactly what the gate reports"


def _round_doc(latest: dict, **fields) -> dict:
    """The toy's coverage document with `fields` replaced, deep-copied.

    Deep-copied through `json` rather than `dict(latest)`: every test below that
    writes more than one round document would otherwise be mutating the same
    nested `capability_matrix` the earlier write already put on disk, and the
    progression it means to assert about would be three references to one object.
    """
    doc = json.loads(json.dumps(latest))
    doc.update(fields)
    return doc


def test_coverage_reads_a_row_per_round_document(tmp_path):
    """One row per `round-N.json`, ordered by the round number and not by filename.

    The brief's version of this test wrote `run.coverage_round(1)` from `latest`,
    which the score fixture already writes -- so it overwrote a file rather than
    adding one, and a `coverage` that ignored the round documents entirely and
    rendered a single row off `latest` satisfied it. Three rounds are written here,
    and the third is round *10* deliberately: `list_json` sorts by name, where
    `round-10.json` sorts before `round-2.json`, so `[1, 2, 10]` is red for a
    builder that keeps `list_json`'s order and green only for one that sorts on the
    number.

    `latest` carries a fourth verdict, different from every round's, which is what
    separates the two facts this section reads: the rows are the progression, and
    `terminal_verdict` is the state the run ended in.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score")
    latest = read_json(run.coverage_latest)
    for n, verdict in ((1, "continue"), (2, "continue"), (10, "halted_round_cap")):
        write_json(run.coverage_round(n), _round_doc(latest, round=n, verdict=verdict))
    write_json(run.coverage_latest, _round_doc(latest, round=10, verdict="converged"))
    got = summary.coverage(run)
    assert [r.round_ for r in got.rounds] == [1, 2, 10]
    assert [r.verdict for r in got.rounds] == ["continue", "continue", "halted_round_cap"]
    assert got.terminal_verdict == "converged", "the terminal verdict is latest's, not a row's"


def test_coverage_row_reads_each_column_from_the_matrix_that_owns_it(tmp_path):
    """Seven columns, seven distinct numbers, so no swapped pair survives.

    `cells_covered`/`cells_total` come from `capability_matrix`, `goals_covered`/
    `goals_total` from `goal_matrix`, and `new_cells`/`rounds_without_progress`
    from `progress` -- three objects whose members are spelled `covered` and
    `total` twice over. A test using the fixture's own numbers cannot tell the two
    matrices apart, because the toy converges at 4-of-4 and 2-of-2 with the same
    `pct`.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score")
    latest = read_json(run.coverage_latest)
    holes = [
        {"ref": f"cell:cap-{n}/oc-x", "reason": "not_yet_attempted", "justification": "later"}
        for n in range(6)
    ]
    write_json(
        run.coverage_round(1),
        _round_doc(
            latest,
            round=1,
            verdict="continue",
            capability_matrix={"cells": [], "covered": 3, "total": 7, "pct": 0.42},
            goal_matrix={"rows": [], "covered": 1, "total": 5, "pct": 0.2},
            progress={"new_cells_this_round": 2, "rounds_without_progress": 4},
            holes=holes,
        ),
    )
    row = summary.coverage(run).rounds[0]
    assert (row.cells_covered, row.cells_total) == (3, 7)
    assert (row.goals_covered, row.goals_total) == (1, 5)
    assert row.pct == 0.42
    assert (row.new_cells, row.rounds_without_progress) == (2, 4)
    assert row.holes == 6, "the row's hole count is that round's, counted not read"


def test_coverage_renders_one_row_from_latest_when_no_round_document_exists(tmp_path):
    """`latest` is a round document too, so a run holding only it still has a row.

    Reachable without a hand edit: `score` writes `latest.json` and `round-N.json`
    together, and a run copied or archived by hand keeps whichever the copier took.
    The round number is moved off the fixture's 1 so that a row invented with a
    hard-coded round would be red.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score")
    latest = read_json(run.coverage_latest)
    write_json(run.coverage_latest, _round_doc(latest, round=4, verdict="halted_round_cap"))
    run.coverage_round(1).unlink()
    got = summary.coverage(run)
    assert [r.round_ for r in got.rounds] == [4]
    assert got.rounds[0].verdict == "halted_round_cap"
    assert got.terminal_verdict == "halted_round_cap"


def test_coverage_exposes_matrix_cells_with_their_scenarios(tmp_path):
    """The matrix is `latest`'s, cell for cell, and a round document's is a decoy.

    Compared field by field against the document rather than by count: the two id
    columns are both `$defs/id` strings, so a builder that read `outcome_class_id`
    into `capability_id` would satisfy every count-and-type assertion the brief's
    version made. The decoy in `round-1.json` is what makes "the matrix comes from
    the state the run ended in" a lock rather than a docstring.

    One cell is turned *uncovered* before the read, because the toy converges: with
    all four cells at `covered: true`, a builder hard-coding `covered=True` was
    measured surviving this test and every other one in the module. An uncovered
    cell in `latest` is also the state the page exists to show -- a converged run
    is the one reading a summary tells a human least about.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score")
    latest = read_json(run.coverage_latest)
    latest["capability_matrix"]["cells"][0]["covered"] = False
    write_json(run.coverage_latest, latest)
    decoy = {
        "capability_id": "cap-decoy",
        "outcome_class_id": "oc-decoy",
        "covered": False,
        "scenario_ids": [],
    }
    write_json(
        run.coverage_round(1),
        _round_doc(
            latest,
            capability_matrix={"cells": [decoy], "covered": 0, "total": 1, "pct": 0},
        ),
    )
    got = summary.coverage(run)
    assert [
        (c.capability_id, c.outcome_class_id, c.covered, c.scenario_ids) for c in got.cells
    ] == [
        (m["capability_id"], m["outcome_class_id"], m["covered"], m["scenario_ids"])
        for m in latest["capability_matrix"]["cells"]
    ]
    assert "cap-decoy" not in {c.capability_id for c in got.cells}
    assert [c for c in got.cells if c.covered], "covered cells render as covered"
    assert [c for c in got.cells if not c.covered], "and the uncovered one as uncovered"
    assert [c.scenario_ids for c in got.cells if c.scenario_ids], "and they name their scenarios"


def test_coverage_reads_holes_with_reason_and_justification(tmp_path):
    """Both fields, in document order -- the justification is the half a reader acts on.

    The brief's version asserted the reasons and the first `ref` and never looked
    at `justification`, which its own name promises: a builder leaving that field
    at `""` passed it. Order is asserted rather than a set, because the holes are
    rendered as a list and `score` writes them in the order it judged them.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score")
    doc = read_json(run.coverage_latest)
    doc["holes"] = [
        {"ref": "cell:cap-a/oc-x", "reason": "unreachable", "justification": "no mapping"},
        {"ref": "cell:cap-a/oc-y", "reason": "no_evidence", "justification": "nothing shows it"},
    ]
    write_json(run.coverage_latest, doc)
    got = summary.coverage(run)
    assert [(h.ref, h.reason, h.justification) for h in got.holes] == [
        ("cell:cap-a/oc-x", "unreachable", "no mapping"),
        ("cell:cap-a/oc-y", "no_evidence", "nothing shows it"),
    ]


def test_coverage_before_score_is_absent(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="propose")
    got = summary.coverage(run)
    assert isinstance(got, summary.Absent)
    assert got.what == "03-coverage/"


def test_coverage_passes_a_pct_that_is_not_a_number_through_uncoerced(tmp_path):
    """A `pct: "half"` is a score-stage defect for `validate` to name, and it renders.

    The brief's version of this test was vacuous twice over: it edited
    `latest.json`, whose `pct` no row reads while a `round-1.json` exists, and it
    asserted only that the section was not `Absent` -- which a `pct=_as_int(...)`
    rendering the string as `0` also satisfies. The mutation is moved onto the
    round document the row is built from, and the assertion onto the value, so
    coercing it is red.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score")
    doc = read_json(run.coverage_round(1))
    doc["capability_matrix"]["pct"] = "half"
    write_json(run.coverage_round(1), doc)
    got = summary.coverage(run)
    assert not isinstance(got, summary.Absent)
    assert got.rounds[0].pct == "half", "rendering what the file holds, not a zero"


def test_coverage_passes_a_round_number_that_is_not_a_number_through(tmp_path):
    """`round_` is `object`, and a non-numeric one sorts rather than raising.

    Two facts at once, because they are one line of implementation each: the value
    is rendered as the document holds it (a `_as_int`'d `round_` would print `0`
    beside a document that says `"two"`, which is a rendering that lies), and the
    *sort* reads it through `_as_int`, so the row still places instead of taking
    `sort` down with `TypeError: '<' not supported between 'str' and 'int'`.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score")
    latest = read_json(run.coverage_latest)
    write_json(run.coverage_round(2), _round_doc(latest, round="two", verdict="continue"))
    got = summary.coverage(run)
    assert [r.round_ for r in got.rounds] == ["two", 1], '"two" reads as 0 for the sort only'


def test_coverage_takes_the_implied_size_from_sizing_rather_than_recomputing(tmp_path):
    """Composed, not derived: the report's own dict, keys and all.

    `sizing.implied_size` is the one place this arithmetic lives -- `gate-brief`
    reports it at gates 1 and 2 -- and a second spelling here is how the page and
    the gate would come to disagree about the same run's implied size. Asserted as
    equality against a direct call plus the presence of `basis` and
    `ceiling_binding`, which a locally rebuilt number would not carry.
    """
    from rubrica.sizing import implied_size

    run = build_toy_run(tmp_path / "runs", upto="score")
    got = summary.coverage(run)
    assert got.implied == implied_size(run)
    assert got.implied["basis"] == "world_model+coverage"
    assert "ceiling_binding" in got.implied


@pytest.mark.parametrize("ceiling", ["eight", None, [8]], ids=["str", "null", "list"])
def test_coverage_implied_is_none_rather_than_raising_on_a_non_numeric_ceiling(tmp_path, ceiling):
    """The hole measured in `implied_size`, at all three shapes that reach it.

    `sizing.implied_size` wraps its reads in `except Exception` -- but
    `ceiling_binding` is computed in the `return` *below* that handler, so
    `implied > ceiling` raises `TypeError: '>' not supported between instances of
    'int' and 'str'` for a hand-edited `manifest.limits.max_scenarios`. That is
    the same class of hazard `claim_utilisation` turned out to be, and the same
    ruling applies: guarded here, not widened in `sizing.py`, which is a report
    with its own contract and its own callers.

    The `pytest.raises` is deliberate and is the measurement, not decoration: if
    `sizing.py` is ever made total this line goes red, and that redness is the
    notice that `summary.coverage`'s guard has become belt-and-braces rather than
    the only thing standing between a hand-edited manifest and a blank page.
    """
    from rubrica.artifacts import read_json, write_json
    from rubrica.sizing import implied_size

    run = build_toy_run(tmp_path / "runs", upto="score")
    manifest = read_json(run.manifest)
    manifest["limits"]["max_scenarios"] = ceiling
    write_json(run.manifest, manifest)
    with pytest.raises(TypeError):
        implied_size(run)
    got = summary.coverage(run)
    assert got.implied is None
    assert got.rounds and got.cells, "the rest of the section still renders"


def test_coverage_skips_a_round_document_it_cannot_read(tmp_path):
    """One malformed round document loses its row, not the section.

    `_quietly` returns None for it and the `if doc` guard drops it, so the rounds
    that *are* readable still render. A builder that appended a row per path
    regardless would render an all-zero row for a file it never read, which reads
    as a round that made no progress -- the opposite of "this file is broken".
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score")
    latest = read_json(run.coverage_latest)
    write_json(run.coverage_round(2), _round_doc(latest, round=2, verdict="converged"))
    run.coverage_round(1).write_text("{not json", encoding="utf-8")
    got = summary.coverage(run)
    assert [r.round_ for r in got.rounds] == [2]


def test_coverage_falls_back_to_latest_when_every_round_document_is_unreadable(tmp_path):
    """No readable round document is the same state as none at all.

    The fallback is on `rows`, not on `round_paths`, and that is the difference
    this test holds: a run whose only `round-1.json` is corrupt still has a
    `latest.json` saying where it ended, and dropping the row would report a scored
    run as having run no rounds.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score")
    write_json(run.coverage_latest, _round_doc(read_json(run.coverage_latest), round=3))
    run.coverage_round(1).write_text("nope", encoding="utf-8")
    got = summary.coverage(run)
    assert [r.round_ for r in got.rounds] == [3]


def test_coverage_on_an_unreadable_directory_is_absent(tmp_path):
    """`list_json` raises `UsageError`, a ValueError and *not* an OSError.

    The same shape measured against `contradictions`: an `except OSError` here
    would let it through, and `03-coverage/` unreadable is exactly the run a
    reader opens this page to understand.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path / "runs", upto="score")
    run.coverage_dir.chmod(0o000)
    try:
        got = summary.coverage(run)
        assert isinstance(got, summary.Absent)
        assert got.what == "03-coverage/"
    finally:
        run.coverage_dir.chmod(0o755)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("capability_matrix", "x"),
        ("goal_matrix", 7),
        ("progress", "nope"),
        ("holes", "nope"),
    ],
)
def test_coverage_survives_a_field_that_is_the_wrong_type(tmp_path, field, bad):
    """A truthy non-list, non-dict in either document renders as nothing found.

    `"capability_matrix": "x"` is the exact shape `brief._mapping`'s docstring
    records raising `AttributeError` at gate 2, and `"holes": "nope"` is `_dicts`':
    iterating the string would count four holes. Both documents are mutated,
    because the row reads one and the matrix reads the other.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score")
    for path in (run.coverage_latest, run.coverage_round(1)):
        doc = read_json(path)
        doc[field] = bad
        write_json(path, doc)
    got = summary.coverage(run)
    assert not isinstance(got, summary.Absent)
    row = got.rounds[0]
    if field == "capability_matrix":
        assert (row.cells_covered, row.cells_total, row.pct) == (0, 0, None)
        assert got.cells == []
    if field == "goal_matrix":
        assert (row.goals_covered, row.goals_total) == (0, 0)
    if field == "progress":
        assert (row.new_cells, row.rounds_without_progress) == (None, None)
    if field == "holes":
        assert row.holes == 0
        assert got.holes == []
