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
