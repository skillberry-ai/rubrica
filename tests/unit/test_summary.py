"""run-summary: one run directory as a single self-contained HTML page.

Partial runs are the primary case, not the edge case: measured across the 11 run
directories on disk when this was designed, 1 reached an emitted suite and 6 held
nothing past intake. Every test that builds a run short of `challenge` is
exercising the common path.
"""

from __future__ import annotations

import json
import os
import re

import pytest

from rubrica import cli, summary
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
    "propose-batches",
    "propose",
    "propose-seal",
    "score",
    "score-seal",
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


def test_header_surfaces_the_part_budget_a_run_actually_set(tmp_path):
    """The third limit, and the only optional one.

    Two runs whose scenario counts differ only because one partitioned its holes
    more finely were otherwise indistinguishable on this page, so a header that
    read `max_rounds` and `max_scenarios` alone left the dial that explains the
    difference invisible. Asserted at a value nothing in the fixture defaults to,
    for the reason the test above gives about 3 and 11: `build_toy_run` sets no
    part budget at all, so a constant or a default would satisfy a check against
    the default.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    doc = read_json(run.manifest)
    doc["limits"]["max_scenario_part_bytes"] = 9000
    write_json(run.manifest, doc)
    assert summary.header(run).max_scenario_part_bytes == 9000


def test_header_leaves_an_unset_part_budget_as_none_rather_than_the_default(tmp_path):
    """Absent means `rounds.DEFAULT_SCENARIO_PART_BYTES`, and this page must not
    say so by printing that number.

    `manifest-0.1.json` does not require the key, so a run that never set it and a
    run that set it to the default are different facts about the run -- and only
    the first is what almost every manifest on disk carries. `_val` renders the
    None as an explicit absence marker, which is the honest reading; substituting
    the constant here would make the page claim a limit the manifest never
    recorded.
    """
    run = build_toy_run(tmp_path / "runs", upto="intake")
    assert summary.header(run).max_scenario_part_bytes is None


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
    """`Malformed`, not `Absent`: the manifest is right there, and the spine says so.

    The spine marks `intake` produced from the file existing, so an `Absent` here
    would put "3 of 22 stages produced an artifact" on the same page as "Not
    present: manifest.json" -- two tests of one artifact, rendered as a
    contradiction the page never reconciles.
    """
    run = build_toy_run(tmp_path / "runs", upto="intake")
    run.manifest.write_text("{not json", encoding="utf-8")
    got = summary.header(RunPaths(run.root))
    assert isinstance(got, summary.Malformed)
    assert not isinstance(got, summary.Absent), "the two markers are siblings, not a subclass"
    assert got.what == "manifest.json"
    assert got.why, "a malformation says why, or the reader cannot tell it from an absence"


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


def _one_admit() -> list[dict]:
    """A `dispositions` array that satisfies triage-0.1.json's `minItems: 1`.

    Three fixtures in this file carried `"dispositions": []`, which the schema
    forbids -- a triage record with no disposition is not one triage-seal can
    write. None of the three reads `dispositions` at all, so the empty array cost
    nothing where it stood and everything when it was copied: CLAUDE.md names the
    copyable-invalid-fixture hazard, and a fixture nobody validates is exactly how
    a stage gets taught the wrong shape.
    """
    return [
        {
            "candidate_id": "api-json",
            "disposition": "admit",
            "priority": 1,
            "reason": "the tool block",
            "authority": "triage",
        }
    ]


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
    from rubrica.validate import validate_artifact

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
            "dispositions": _one_admit(),
            "deficiencies": [],
            "projections": [],
        },
    )
    assert validate_artifact(run.triage, "triage") == [], (
        "the sealed fixture must be the shape triage-seal actually writes"
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
    from rubrica.validate import validate_artifact

    run = build_toy_run(tmp_path / "runs", upto="intake")
    write_json(
        run.triage,
        {
            "schema_version": "0.1",
            "run_id": run.root.name,
            "objective_review": _objective_document(run.root.name)["objective_review"],
            "dispositions": _one_admit(),
            "deficiencies": [
                {"deficiency_id": "def-1", "subject": "errors", "statement": "no error path"},
                {"deficiency_id": "def-2", "subject": "auth", "statement": "no auth model"},
            ],
            "projections": [_projection("prj-2", ["def-2"], "author an auth note")],
        },
    )
    assert validate_artifact(run.triage, "triage") == [], (
        "the fixture must be the shape triage-seal actually writes"
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

    This is the one fixture here that triage-0.1.json rejects, and only in the
    field under test: `closes` is `{"type": "array", "minItems": 1}`, so a string
    or a nested list is exactly the hand edit being modelled. Every *incidental*
    invalidity is gone -- `objective_review` and a real disposition are present --
    so nothing else about the document is a shape the seal could not write.
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
            "objective_review": _objective_document(run.root.name)["objective_review"],
            "dispositions": _one_admit(),
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


def _uncite_trace(sealed: dict) -> None:
    """Drop every clm-trace-* citation from `sealed`, in place, at every site.

    Every site, not just the four top-level groups: since issue #6 the golden
    fixture cites clm-trace-001 on cap-find-tickets' `oc-none` outcome class,
    where the evidence for an observed empty return belongs. A stripper that
    walked only the parent arrays left it there, so `trace-json` stayed at 1 of 2
    and the `uncited` list this exercises came back empty -- the same
    fixture-cannot-reach shape the docstrings below already name.

    Contradictions are cleared by the callers rather than here, because that is
    the *other* half of what makes trace-json uncited and each caller says so.
    """
    for group in ("capabilities", "entities", "actors", "goals"):
        for member in sealed[group]:
            member["claims"] = [c for c in member["claims"] if not c.startswith("clm-trace-")]
    for capability in sealed["capabilities"]:
        for outcome_class in capability.get("outcome_classes", []):
            outcome_class["claims"] = [
                c for c in outcome_class["claims"] if not c.startswith("clm-trace-")
            ]
    for entity in sealed["entities"]:
        for invariant in entity.get("invariants", []):
            invariant["claims"] = [c for c in invariant["claims"] if not c.startswith("clm-trace-")]
    for gap in sealed.get("gaps", []):
        gap["claims"] = [c for c in gap["claims"] if not c.startswith("clm-trace-")]


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
    """Present and unreadable, which is not the pre-seal absence above."""
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    run.world_model.write_text("{not json", encoding="utf-8")
    got = summary.world_model(run)
    assert isinstance(got, summary.Malformed)
    assert got.what == "01-world-model.json"


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

    The measured totals are pinned alongside: 9/10, 8/8 and 2/2 on the toy
    fixture, 19 of 20 overall. They were pinned when the two columns were equal at
    19/19, where derived sums alone could not tell a `utilisation` that summed the
    wrong column from one that summed the right one. api-json's denominator has
    since gained `clm-api-010`, the run's one `tool` claim, which nothing cites
    yet, so cited != total and the pair now discriminates that on its own.
    """
    from rubrica.utilisation import claim_utilisation

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    report = claim_utilisation(run)
    got = summary.utilisation(run)
    assert got.per_artifact == report["artifacts"]
    assert got.cited == sum(a["cited"] for a in report["artifacts"])
    assert got.total == sum(a["total"] for a in report["artifacts"])
    assert (got.cited, got.total) == (19, 20), (
        "the toy world model cites 19 of 20 claims -- every one but the tool claim"
    )
    assert got.pct == pytest.approx(95.0)


def test_utilisation_names_an_artifact_the_world_model_cites_nothing_of(tmp_path):
    """`uncited`, which the toy fixture cannot reach unaltered.

    Measured: the sealed toy world model cites every claim of notes-md and
    trace-json and all but one of api-json's (9/10, 8/8, 2/2), so no input is at
    zero, the loop in test_utilisation_totals_and_names_uncited_artifacts has an
    empty body and the list ships unexercised -- and it is the entire input to the
    `uncited-artifacts` flag. `uncited` is per *input*, not per claim, which is
    why api-json's own uncited `tool` claim does not put it on the list.

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
    _uncite_trace(sealed)
    sealed["contradictions"] = []
    write_json(run.world_model, sealed)
    assert validate_artifact(run.world_model, "world-model") == [], (
        "an uncited input must be produced by a world model that could really exist"
    )
    got = summary.utilisation(run)
    assert got.uncited == ["trace-json"]
    assert {a["artifact_id"]: a["cited"] for a in got.per_artifact}["trace-json"] == 0
    assert (got.cited, got.total) == (17, 20), "trace-json's two claims stopped being cited"
    assert got.pct == pytest.approx(17 / 20 * 100)


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
    got = summary.utilisation(run)
    # `what` names the report and `why` the reading, which is the split every
    # marker now takes: ten of the twelve absences were bare paths and two were
    # sentences, and nothing said which a reader should expect.
    assert (got.what, got.why) == ("claim utilisation", "no world model yet")
    assert isinstance(got, summary.Absent), "not reaching the seal is not a malformation"


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
            # A gap's `claims` cite the evidence that the absence *matters*, which
            # is what $defs/gap has required since issue #6: clm-notes-004 is the
            # claim that a missing id is an error at all, so a run with no stated
            # gold answer for that branch is a hole rather than a non-question.
            "claims": ["clm-notes-004"],
        },
        {
            "id": "gap-auth",
            "subject": "authentication",
            "unknown": "whether any call requires a token",
            "why_it_matters": "an unauthenticated seed may be exercising a different target",
            "blocks": ["instantiate"],
            # clm-api-001 is the claim that the tool has a callable action at all --
            # the fact whose silence about authentication is the gap.
            "claims": ["clm-api-001"],
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


def test_contradictions_on_an_unreadable_directory_is_malformed_not_absent(tmp_path):
    """The `except` around `list_json`, which raises `UsageError` -- not `OSError`.

    That is why this handler cannot be the `except OSError` the spine uses:
    `paths.list_json` catches the OSError itself and re-raises it as a
    `UsageError`, a ValueError subclass, so an unreadable directory would escape
    an OSError-only guard and take the whole page with it.

    `Malformed` rather than `Absent`, and the empty-directory test above is the
    other half: `list_json` answers `[]` for a directory that is not there and
    *raises* for one it cannot list, so the two branches are two facts. Both name
    the same directory; only the malformation says the parts are on disk and
    unreadable.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    run.contradictions_dir.chmod(0o000)
    try:
        got = summary.contradictions(run)
        assert isinstance(got, summary.Malformed)
        assert got.what == "01-contradictions/", "both branches name the same directory"
        assert got.why
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


# The readable-run shapes measured escaping `claim_utilisation` as exceptions,
# each as a mutation of a fully sealed toy run. Driven end to end through
# `summary.utilisation()` rather than through `claim_utilisation` itself: the
# defect this closes is that a report which "never raises on a readable run's
# content" was calling a function that does, and only the composed call proves the
# guard is in the path the page actually takes. `id` is the parametrisation label
# and the escape it produced, so a red test names the shape it lost.
#
# They split into two sets now, and the split is the ruling issue #6 changed. The
# `01-claims/` shapes still raise and are still caught in summary.py. The
# world-model *container* shapes below no longer raise at all: `claim-utilisation`
# and `gate-brief` are reports, and a report has no findings channel through which
# to say "this document is malformed", so `utilisation._cited_claim_ids` was
# widened to skip a container it cannot walk --
# `test_utilisation_renders_over_a_world_model_container_it_could_not_walk` is
# where they are pinned now.
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
        pytest.param(_claims_dir_is_unreadable, id="UsageError-unreadable-claims-dir"),
    ],
)
def test_utilisation_is_a_marker_rather_than_raising_on_a_readable_run(tmp_path, break_it):
    """The hole measured in this module's never-raise promise, at the shapes that
    still reach it as exceptions.

    `claim_utilisation` is a report with its own contract and its own callers, and
    it is not total: `utilisation.py` indexes `claim["id"]` bare over an
    `01-claims/` document, and calls `list_json(run.claims_dir)`, whose
    `UsageError` is a ValueError rather than an OSError. Every shape here is a
    *readable* run -- a hand-edited artifact, or a directory permission -- which is
    exactly the class this module promises to render rather than crash on, and one
    of them escaping takes the whole page down.

    These are guarded in `summary.py` rather than widened in `utilisation.py`,
    which was the ruling for all of the measured shapes until issue #6 overturned
    half of it: the three world-model *container* shapes were widened there,
    because `claim-utilisation` and `gate-brief` are reports and a raise on a
    readable run breaks the exit-code contract outright -- a report has no findings
    channel to report a malformed document through, where a layer-2 checker at
    least degrades to an `internal` finding.

    **That reasoning reaches the three hand-edited-document shapes left here too**,
    and saying otherwise would make this docstring the weaker of two records of one
    ruling: each of them also takes both reports to exit 1 on a readable run, and
    `utilisation.py` states that hole plainly beside the unguarded line. What keeps
    them here is scope and authorisation -- issue #6 widened the world-model walk
    and never touched the `01-claims/` path, the overturned ruling was written
    specifically about these shapes with this page's marker attached, and only the
    world-model half was ruled in. So for those three this test pins current
    behaviour on a known-wrong thing rather than a settled one, and the ruling that
    parks it belongs in `docs/design/limitations.md` rather than in this docstring.

    `_claims_dir_is_unreadable` is here for a **different reason, and is not part of
    that hole**: an unreadable directory is a filesystem problem, `list_json` raises
    `UsageError`, and `cli.py` maps that to **exit 2** -- measured -- which is the
    exit-code contract's own ruling for one. Guarding it in `utilisation.py` would
    turn it into an exit 0 reporting empty utilisation over claims nobody could
    read, so this param is not a candidate for the same fix; it is caught here
    purely so the page renders a marker rather than crashing.
    """
    if os.geteuid() == 0 and break_it is _claims_dir_is_unreadable:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    break_it(run)
    try:
        got = summary.utilisation(run)
        # `Malformed`: every shape here is an artifact that is *there* and could not
        # be read, which is a defect `validate` will name -- not a stage that has
        # not run, which is what the absence one test above reports.
        assert isinstance(got, summary.Malformed)
        assert got.what == "claim utilisation"
        assert got.why == "01-claims/ or 01-world-model.json unreadable"
    finally:
        run.claims_dir.chmod(0o755)


@pytest.mark.parametrize(
    "break_it",
    [
        pytest.param(_group_member_is_a_string, id="group-member-a-string"),
        pytest.param(_contradictions_member_is_a_string, id="contradiction-a-string"),
        pytest.param(_collection_is_not_a_list, id="collection-not-a-list"),
    ],
)
def test_utilisation_renders_over_a_world_model_container_it_could_not_walk(tmp_path, break_it):
    """The three shapes that were `Malformed` markers here until issue #6.

    Each was measured raising `AttributeError: 'str' object has no attribute 'get'`
    out of `_cited_claim_ids`' walk over the world model's element groups, at exit
    1 from `claim-utilisation` and from `gate-brief --gate 1` -- both reports, and
    both ruled to exit clean on a readable run. So the walk skips a container it
    cannot read, and this page renders the numbers it could compute rather than a
    "present but unreadable" marker.

    Which is a loss of signal on this page, and it is the one this project already
    ruled on twice: naming a malformed document is `validate`'s job, layer 1 names
    it precisely (`rubrica validate --stage reconcile-seal`), and a report that
    says "malformed" by crashing is the least useful reading of a document. The
    citations the unwalkable container held are simply not counted, so the loss
    shows up as a number that disagrees with the file -- which is `brief._dicts`'
    ruling, stated there.
    """
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    break_it(run)

    got = summary.utilisation(run)

    assert not isinstance(got, summary.Marker), f"a readable run still reports: {got}"
    # And it reports over every input, so the page does not quietly shrink.
    assert {a["artifact_id"] for a in got.per_artifact} == {"api-json", "notes-md", "trace-json"}
    # A non-zero total citation count is what separates "skipped the one container
    # it could not walk" from "skipped the world model entirely": each mutator here
    # breaks exactly one container, and the assertions above all read `01-claims/`,
    # so a guard that returned nothing for every container would satisfy them while
    # rendering this page at 0% utilised.
    assert got.cited > 0, f"the other containers' citations still count: {got}"


def test_utilisation_absent_reads_differently_from_the_no_world_model_absence(tmp_path):
    """Two markers, two readings, so they must not render as one line.

    "The seal has not run" is a fact about how far the run got; "something in the
    run could not be read" is a defect in an artifact. A page that rendered the
    same line for both would tell a reader with a broken claims file that their run
    simply had not reached reconcile-seal. The marker *type* differs now as well as
    the words, and both halves are asserted: sharing `what` while differing in type
    is a distinction the page can still draw, and sharing both is not.
    """
    from rubrica.artifacts import read_json, write_json
    from rubrica.paths import list_json

    unsealed = build_toy_run(tmp_path / "runs", upto="extract")
    broken = build_toy_run(tmp_path / "runs2", upto="reconcile-seal")
    path = list_json(broken.claims_dir)[0]
    payload = read_json(path)
    payload["claims"] = ["oops"]
    write_json(path, payload)
    one, other = summary.utilisation(unsealed), summary.utilisation(broken)
    assert type(one) is not type(other), "one is an absence, the other a malformation"
    assert (one.what, one.why) != (other.what, other.why)


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
    _uncite_trace(sealed)
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

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
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

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
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

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
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

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
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


def test_coverage_exposes_goal_rows_with_their_depths_and_scenarios(tmp_path):
    """The goal matrix is `latest`'s, row for row, and a round document's is a decoy.

    Field by field against the document rather than by count, for the reason the
    cell test above gives: `hop_depths_present` and `hop_depths_expected` are the
    same `$defs/hop_depths` type, so a builder that read one into the other would
    satisfy every count-and-type assertion. Swapping them is the defect that
    matters most here -- it would turn every open depth into a covered one, which
    is the exact reading the matrix exists to prevent.

    The toy converges with both goals covered at their only expected depth, so one
    row is edited before the read: with the fixture untouched, a builder hard-coding
    `covered=True` and `present=expected` was measured surviving this test.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
    latest = read_json(run.coverage_latest)
    open_row = latest["goal_matrix"]["rows"][1]
    open_row["covered"] = False
    open_row["hop_depths_present"] = []
    open_row["hop_depths_expected"] = [2, 3]
    write_json(run.coverage_latest, latest)
    decoy = {
        "goal_id": "goal-decoy",
        "scenario_ids": [],
        "hop_depths_present": [],
        "hop_depths_expected": [1],
        "covered": False,
    }
    write_json(
        run.coverage_round(1),
        _round_doc(latest, goal_matrix={"rows": [decoy], "covered": 0, "total": 1, "pct": 0}),
    )
    got = summary.coverage(run)
    assert [(g.goal_id, g.scenario_ids, g.present, g.expected, g.covered) for g in got.goals] == [
        (
            m["goal_id"],
            m["scenario_ids"],
            m["hop_depths_present"],
            m["hop_depths_expected"],
            m["covered"],
        )
        for m in latest["goal_matrix"]["rows"]
    ]
    assert "goal-decoy" not in {g.goal_id for g in got.goals}
    assert [g for g in got.goals if g.covered], "covered goals read as covered"
    assert [g for g in got.goals if not g.covered], "and the open one as open"
    assert [g for g in got.goals if g.expected != g.present], "and a missing depth is visible"


def test_coverage_keeps_a_hop_depth_present_that_the_goal_does_not_expect(tmp_path):
    """A scenario landing at an unexpected depth survives into the row.

    Measured on `run-20260825-094033`: `goal-slack-draft` carries `present: [1]`
    against `expected: [2, 3]`, so a scenario reached it three hops shallower than
    anything asked for. `covered` is false and no hole says why, which makes the
    two depth lists the only record of it -- an implementation that intersected
    `present` with `expected`, which reads like tidying, would erase the one signal
    this row has.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
    latest = read_json(run.coverage_latest)
    latest["goal_matrix"]["rows"][0]["hop_depths_present"] = [1, 4]
    write_json(run.coverage_latest, latest)
    assert summary.coverage(run).goals[0].present == [1, 4]


@pytest.mark.parametrize("bad", ["two", 2, None, {"1": 1}])
def test_coverage_reads_a_hop_depth_list_that_is_not_a_list_as_empty(tmp_path, bad):
    """A non-list where a depth array belongs contributes no depth.

    The same shape `_strings` and `_dicts` exist for, one level further in: a
    hand-edited `"hop_depths_present": "two"` is iterable, and iterating it would
    yield the *characters* `t`, `w`, `o` as three hop depths of a 22-goal matrix.
    A bare `2` and a `None` are not iterable at all and would raise instead.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
    latest = read_json(run.coverage_latest)
    latest["goal_matrix"]["rows"][0]["hop_depths_present"] = bad
    write_json(run.coverage_latest, latest)
    got = summary.coverage(run)
    assert got.goals[0].present == []
    assert got.goals[0].expected == [1], "the sibling list is untouched"


def test_coverage_does_not_read_a_boolean_as_a_hop_depth(tmp_path):
    """`True` is an `int` in Python, and a hop depth column must not print it.

    `isinstance(True, int)` is true, so the obvious member test admits a
    hand-edited `[true, 2]` and renders a column headed `hop True`. Excluded
    explicitly rather than by a numeric range, because the depth a column is
    headed with is the value read here and `bool` is the one int subclass that
    formats as a word.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
    latest = read_json(run.coverage_latest)
    latest["goal_matrix"]["rows"][0]["hop_depths_expected"] = [True, 2, False]
    write_json(run.coverage_latest, latest)
    assert summary.coverage(run).goals[0].expected == [2]


def test_coverage_reads_holes_with_reason_and_justification(tmp_path):
    """Both fields, in document order -- the justification is the half a reader acts on.

    The brief's version asserted the reasons and the first `ref` and never looked
    at `justification`, which its own name promises: a builder leaving that field
    at `""` passed it. Order is asserted rather than a set, because the holes are
    rendered as a list and `score` writes them in the order it judged them.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
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
    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
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

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
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

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
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

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
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

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
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

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
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

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
    write_json(run.coverage_latest, _round_doc(read_json(run.coverage_latest), round=3))
    run.coverage_round(1).write_text("nope", encoding="utf-8")
    got = summary.coverage(run)
    assert [r.round_ for r in got.rounds] == [3]


def test_coverage_on_an_unreadable_directory_is_malformed_not_absent(tmp_path):
    """`list_json` raises `UsageError`, a ValueError and *not* an OSError.

    The same shape measured against `contradictions`: an `except OSError` here
    would let it through, and `03-coverage/` unreadable is exactly the run a
    reader opens this page to understand.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path / "runs", upto="score-seal")
    run.coverage_dir.chmod(0o000)
    try:
        got = summary.coverage(run)
        assert isinstance(got, summary.Malformed)
        assert got.what == "03-coverage/"
    finally:
        run.coverage_dir.chmod(0o755)


def test_coverage_with_no_readable_round_document_is_malformed_not_absent(tmp_path):
    """The measured I5 shape: the spine bolds `score` while the section denies it.

    A `03-coverage/` holding only a garbage `latest.json` is the run this
    distinction was found on. The directory exists, so the spine marks `score`
    produced; nothing in it parses, so this section has no body. Reported as an
    absence, the one page said both "score produced an artifact" and "03-coverage/
    is not present".
    """
    run = build_toy_run(tmp_path / "runs", upto="score-seal")
    for path in run.coverage_dir.iterdir():
        path.unlink()
    run.coverage_latest.write_text("{not json", encoding="utf-8")
    got = summary.coverage(run)
    assert isinstance(got, summary.Malformed)
    assert got.what == "03-coverage/"
    produced = {row.name: row.produced for row in summary.stage_spine(run)}
    assert produced["score"] is True, "the spine counts the directory, so the page must agree"


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

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
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
        assert got.goals == []
    if field == "progress":
        assert (row.new_cells, row.rounds_without_progress) == (None, None)
    if field == "holes":
        assert row.holes == 0
        assert got.holes == []


# -- the scenario table (spec 3.5) -------------------------------------------
# The section the report exists for, and the only one joined across three
# directories: `02-scenarios.json`, `05-verdicts/<sid>.json` and
# `06-suite/<sid>/`. Two properties of the toy fixture shape every test below and
# are worth stating once rather than re-measuring in each docstring.
#
# **The fixture is uniform in six of the seventeen row fields.** All five
# scenarios carry `round` 1 and `actor_id` "act-support"; all four verdicts carry
# the same `notes` prose, `verdict` "accept", `uniquely_determined` true and
# `derivable_without_guessing` true. A test over an unmutated toy run therefore
# cannot tell a field that is *read* from one that is *hardcoded* -- the same
# fixture-uniformity trap that let a `covered=True` mutation survive the coverage
# sweep. Every assertion over one of those fields below runs against a run whose
# document has been edited to make the value distinct.
#
# **The fixture does vary in the rest, and those variations are used as-is:**
# `hop_depth` (1 and 2), `goal_id` (goal-locate and goal-explain), `title`,
# `discriminating_fact`, `cells` (one ref and two), `min_tool_calls` (1 and 2) and
# -- because `scn-open-dup` is the folded duplicate -- `has_instance`,
# `suite_files` and the whole verdict join, which are present for four rows and
# absent for the fifth. `status` is the one field whose variation depends on the
# fixture *level*: uniform "proposed" at `propose`, and active-against-duplicate
# only from `score` on, which is where it is locked.


def test_scenarios_returns_a_row_per_scenario(tmp_path):
    from rubrica.artifacts import read_json

    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    expected = len(read_json(run.scenarios)["scenarios"])
    rows = summary.scenarios(run)
    assert len(rows) == expected


def test_scenarios_reads_every_id_in_document_order(tmp_path):
    """The ids, in the document's order, as an exact list.

    The count test above is satisfied by five rows carrying anything at all, and
    the order matters to a reader: `propose` appends, so position carries the round
    a scenario was proposed in as much as the `round` column does. The folded
    duplicate is last, which is what makes it the row every "absent join" assertion
    below indexes.
    """
    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    assert [r.id_ for r in summary.scenarios(run)] == [
        "scn-open",
        "scn-empty",
        "scn-blocked",
        "scn-missing",
        "scn-open-dup",
    ]


def test_scenarios_row_carries_the_record_fields(tmp_path):
    """Each record column, by value, against the fixture's first scenario.

    Written as exact values rather than as the brief's truthiness checks, which
    were measured satisfiable by a wrong implementation: `assert row.title and
    row.goal_id` stays green when the two are swapped, and every column here is a
    `str(member.get(...))` one line from its neighbour, which is exactly where a
    copy-paste slip lands. `round_` and `actor_id` are asserted in
    test_scenarios_reads_the_round_and_actor_from_the_record instead -- the fixture
    is uniform in both, so a value read from this run could not distinguish them
    from a constant.
    """
    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    row = summary.scenarios(run)[0]
    assert row.id_ == "scn-open"
    assert row.title == "Find the open billing ticket"
    assert row.goal_id == "goal-locate"
    assert row.hop_depth == 1
    assert row.cells == ["cap-find-tickets/oc-found"]
    assert row.discriminating_fact == "exactly one billing ticket has status open"
    # A second row, because four of these columns are uniform *within* the first one
    # and only differ between scenarios: `scn-blocked` is the fixture's only
    # two-hop, two-cell, goal-explain scenario, and without it a hardcoded
    # `goal_id="goal-locate"` passes -- measured as a surviving mutation before this
    # half was added.
    deeper = summary.scenarios(run)[2]
    assert deeper.id_ == "scn-blocked"
    assert deeper.goal_id == "goal-explain"
    assert deeper.hop_depth == 2
    assert deeper.cells == ["cap-find-tickets/oc-found", "cap-get-ticket/oc-detail"]
    # "proposed", not "active": `propose` writes every scenario proposed and `score`
    # is what promotes or folds it. Measured, because the natural guess is wrong and
    # the same field reads differently two stages later -- which is also why the
    # status column is locked at a level where it varies, in the test below.
    assert row.status == "proposed"


def test_scenarios_reads_the_status_where_the_statuses_differ(tmp_path):
    """Every status on a scored run, as an exact mapping.

    `status` is uniform at `propose` ("proposed" for all five) and varies only once
    `score` has folded the duplicate, so the level matters: a test at `propose`
    cannot tell a read status from a constant, and a hardcoded `"active"` would be
    the plausible wrong answer, since four of the five rows carry it.
    """
    run = build_toy_run(tmp_path / "runs", upto="score-seal")
    assert {r.id_: r.status for r in summary.scenarios(run)} == {
        "scn-open": "active",
        "scn-empty": "active",
        "scn-blocked": "active",
        "scn-missing": "active",
        "scn-open-dup": "duplicate",
    }


def test_scenarios_reads_the_round_and_actor_from_the_record(tmp_path):
    """`round_` and `actor_id`, on a run edited to stop them being uniform.

    The toy fixture proposes every scenario in round 1 and gives every one
    `act-support`, so a hardcoded `round_=1` or `actor_id="act-support"` passes
    every other test in this file. One row is edited to differ; the untouched
    sibling is the control, without which a hardcode of the *new* values would pass.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    doc = read_json(run.scenarios)
    doc["scenarios"][1]["round"] = 2
    doc["scenarios"][1]["actor_id"] = "act-admin"
    write_json(run.scenarios, doc)
    rows = summary.scenarios(run)
    assert (rows[1].round_, rows[1].actor_id) == (2, "act-admin")
    assert (rows[0].round_, rows[0].actor_id) == (1, "act-support")


def test_scenarios_carries_long_prose_in_full_rather_than_truncated(tmp_path):
    """`discriminating_fact` and `notes` are carried whole, not summarised.

    They are the two paragraph-shaped fields on the row and the reason the row
    carries them at all: the renderer puts each in a `title` attribute rather than
    a column, which is what keeps a 128-scenario run a scannable table. Truncating
    here would make the attribute a summary of a judgment, and the judgment is the
    half a human at gate 3 acts on. The fixture's longest `discriminating_fact` is
    used, since a short one is equal to its own first clause.
    """
    from rubrica.artifacts import read_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    record = {m["id"]: m for m in read_json(run.scenarios)["scenarios"]}["scn-blocked"]
    row = {r.id_: r for r in summary.scenarios(run)}["scn-blocked"]
    assert row.discriminating_fact == record["discriminating_fact"]
    assert len(row.discriminating_fact) > 60, "the fixture's multi-clause fact, not a short one"
    assert row.notes == read_json(run.verdict("scn-blocked"))["notes"]


def test_scenarios_flattens_capability_refs_into_cell_labels(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    doc = read_json(run.scenarios)
    doc["scenarios"][0]["capability_refs"] = [
        {"capability_id": "cap-a", "outcome_class_id": "oc-x"},
        {"capability_id": "cap-b", "outcome_class_id": "oc-y"},
    ]
    write_json(run.scenarios, doc)
    row = summary.scenarios(run)[0]
    assert row.cells == ["cap-a/oc-x", "cap-b/oc-y"]


def test_scenarios_joins_the_challenge_verdict(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    rows = {r.id_: r for r in summary.scenarios(run)}
    judged = [r for r in rows.values() if r.verdict]
    assert judged, "a challenged run has verdicts to join"
    # The brief wrote `judged[0].notes or judged[0].notes == ""` here, which is
    # tautological for a `str` -- a string is either truthy or equal to "" -- so it
    # held for a `notes` that was never read at all, and
    # `uniquely_determined is not None` held for a hardcoded `True`. Both fields are
    # locked by value in test_scenarios_reads_each_verdict_field_from_the_field_that_owns_it
    # instead; what this test still owns is that the join happens for every judged
    # scenario and for no other.
    assert len(judged) == 4, "four of the five toy scenarios were challenged"
    assert rows["scn-open-dup"].verdict == "", "the folded duplicate was never challenged"


def test_scenarios_reads_each_verdict_field_from_the_field_that_owns_it(tmp_path):
    """Four verdict columns, each given a distinct value in one document.

    The toy fixture accepts every challenged scenario with the same notes and the
    same two booleans, so `verdict == "accept"`, `uniquely_determined is True` and
    `derivable is True` are all satisfied by constants -- and `derivable` reads
    `derivable_without_guessing`, a rename no assertion over a uniform fixture can
    catch pointing at the wrong key. The values are chosen to be mutually
    distinguishable: `False` against `True` so a swap of the two booleans is
    visible, and a `min_tool_calls` that is neither of the fixture's 1 and 2.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.verdict("scn-open"))
    doc.update(
        verdict="reject",
        uniquely_determined=False,
        derivable_without_guessing=True,
        minimum_tool_calls_found=7,
        notes="two answers fit the seed equally well",
    )
    write_json(run.verdict("scn-open"), doc)
    row = {r.id_: r for r in summary.scenarios(run)}["scn-open"]
    assert row.verdict == "reject"
    assert row.uniquely_determined is False
    assert row.derivable is True
    assert row.min_tool_calls == 7
    assert row.notes == "two answers fit the seed equally well"


def test_scenarios_without_verdicts_leaves_the_verdict_empty(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    assert all(r.verdict == "" for r in summary.scenarios(run))


def test_scenarios_reports_the_instance_directory_per_row(tmp_path):
    """`has_instance` both ways, from the fixture's own variation.

    `instantiate` writes a directory for each active scenario and none for the
    folded duplicate, so a challenged toy run distinguishes a read `has_instance`
    from a hardcoded `True` without any editing -- the one boolean on this row for
    which that is true. Asserted as an exact set, because "four rows have one"
    would hold if the wrong four did.
    """
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    rows = summary.scenarios(run)
    assert {r.id_ for r in rows if r.has_instance} == {
        "scn-open",
        "scn-empty",
        "scn-blocked",
        "scn-missing",
    }
    assert {r.id_: r.status for r in rows if not r.has_instance} == {"scn-open-dup": "duplicate"}


def test_scenarios_flags_difficulty_overstated_when_fewer_calls_suffice(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.scenarios)
    sid = doc["scenarios"][0]["id"]
    doc["scenarios"][0]["hop_depth"] = 3
    write_json(run.scenarios, doc)
    verdict = read_json(run.verdict(sid))
    verdict["minimum_tool_calls_found"] = 1
    write_json(run.verdict(sid), verdict)
    rows = summary.scenarios(run)
    row = {r.id_: r for r in rows}[sid]
    assert row.difficulty_overstated is True
    # The control the brief's pair lacks: every other row is judged against its own
    # hop_depth, so a flag that had become unconditional would still pass above.
    assert not [r for r in rows if r.id_ != sid and r.difficulty_overstated]


def test_scenarios_does_not_flag_difficulty_when_calls_match(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.scenarios)
    sid = doc["scenarios"][0]["id"]
    doc["scenarios"][0]["hop_depth"] = 2
    write_json(run.scenarios, doc)
    verdict = read_json(run.verdict(sid))
    verdict["minimum_tool_calls_found"] = 2
    write_json(run.verdict(sid), verdict)
    row = {r.id_: r for r in summary.scenarios(run)}[sid]
    assert row.difficulty_overstated is False


def test_scenarios_does_not_flag_difficulty_without_a_verdict(tmp_path):
    """A missing verdict leaves the found count `None`, and `None < 1` raises.

    The folded duplicate is the shape: `hop_depth` 1 with no `05-verdicts/` entry,
    so dropping the `isinstance(found, int)` test from the flag turns rendering a
    challenged toy run into a `TypeError` -- breaking this module's one absolute
    promise, that it never raises on a readable run's content. Reachable without
    editing the fixture, which is why it is a test rather than a comment.
    """
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    row = {r.id_: r for r in summary.scenarios(run)}["scn-open-dup"]
    assert row.min_tool_calls is None
    assert row.difficulty_overstated is False


def test_scenarios_does_not_flag_difficulty_for_a_boolean_call_count(tmp_path):
    """`True < 3` is legal Python and is a nonsense comparison.

    `bool` is an `int` subclass, so an `isinstance(found, int)` test alone accepts a
    hand-edited `"minimum_tool_calls_found": true` and reports the scenario's
    difficulty as overstated on the strength of it -- a claim about the run made
    from a malformed document. The `not isinstance(found, bool)` guard is what this
    locks, and `_as_int`'s docstring records the opposite ruling for a count that is
    merely rendered: there, `True` reading as 1 is preferable to a crash.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.scenarios)
    doc["scenarios"][0]["hop_depth"] = 3
    write_json(run.scenarios, doc)
    verdict = read_json(run.verdict("scn-open"))
    verdict["minimum_tool_calls_found"] = True
    write_json(run.verdict("scn-open"), verdict)
    row = {r.id_: r for r in summary.scenarios(run)}["scn-open"]
    assert row.min_tool_calls is True, "rendered as the document holds it"
    assert row.difficulty_overstated is False

    # And the mirror, on the other side of the comparison: a `"hop_depth": true`
    # against a found count of 0 is `0 < True`, which is `True`. Without this the
    # `not isinstance(hop, bool)` half of the guard is unreachable by any test --
    # measured, and the reason the guard is written symmetrically rather than only
    # around the count.
    doc["scenarios"][0]["hop_depth"] = True
    write_json(run.scenarios, doc)
    verdict["minimum_tool_calls_found"] = 0
    write_json(run.verdict("scn-open"), verdict)
    row = {r.id_: r for r in summary.scenarios(run)}["scn-open"]
    assert row.hop_depth is True, "rendered as the document holds it"
    assert row.difficulty_overstated is False


@pytest.mark.parametrize("bad", ["two", None, [2], 2.5])
def test_scenarios_does_not_flag_difficulty_for_a_hop_depth_that_is_not_an_int(tmp_path, bad):
    """A non-int `hop_depth` renders uncoerced and flags nothing.

    `2.5` is in the list because a float is an ordinary comparison partner --
    `1 < 2.5` is `True` -- so it is the one shape an `isinstance(found, int)`-only
    guard would flag rather than raise on, and a fractional hop depth is a
    malformed document rather than an overstated difficulty. Passed through rather
    than `_as_int`'d, for `_round_row`'s ruling on `round`: a `0` beside a readable
    file reads as a rendering bug rather than as the propose-stage defect it is.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.scenarios)
    doc["scenarios"][0]["hop_depth"] = bad
    write_json(run.scenarios, doc)
    row = {r.id_: r for r in summary.scenarios(run)}["scn-open"]
    assert row.hop_depth == bad
    assert row.difficulty_overstated is False


def test_scenarios_reports_which_suite_files_landed(tmp_path):
    from rubrica.emit import emit_run

    run = build_toy_run(tmp_path / "runs")
    emit_run(run)
    rows = [r for r in summary.scenarios(run) if r.suite_files]
    assert rows, "emit writes a package for every accepted instance"
    assert "task.toml" in rows[0].suite_files
    assert "seed.json" in rows[0].suite_files


def test_scenarios_reports_a_full_package_as_every_suite_file(tmp_path):
    """The whole of `SUITE_FILES` for a complete package, `tests` included.

    `tests` is a *directory* and the other five are files, so a presence check
    written as `is_file()` reports five of six for a package emit wrote correctly --
    measured: emit writes all six for each of the four accepted toy scenarios. The
    folded duplicate is the negative half: no package at all is `[]`, which is what
    Task 7's challenge section distinguishes from a partial one.
    """
    from rubrica.emit import emit_run

    run = build_toy_run(tmp_path / "runs")
    emit_run(run)
    rows = {r.id_: r for r in summary.scenarios(run)}
    assert rows["scn-open"].suite_files == list(summary.SUITE_FILES)
    assert "tests" in rows["scn-open"].suite_files, "a directory, not a file"
    assert rows["scn-open-dup"].suite_files == []


def test_scenarios_reports_a_package_missing_a_file_as_the_subset(tmp_path):
    """A package missing its golden answer is not a package that was never written.

    That is the distinction `SUITE_FILES` exists for and the one a boolean "package
    emitted" column cannot draw. Without this test, a `suite_files` returning
    `list(SUITE_FILES)` whenever the directory exists passes every other suite
    assertion in this file, because emit writes all six for every toy package --
    the fixture is uniform in package *contents* even though it varies in package
    presence.
    """
    from rubrica.emit import emit_run

    run = build_toy_run(tmp_path / "runs")
    emit_run(run)
    (run.task_dir("scn-open") / "golden.json").unlink()
    row = {r.id_: r for r in summary.scenarios(run)}["scn-open"]
    assert "golden.json" not in row.suite_files
    assert row.suite_files == [n for n in summary.SUITE_FILES if n != "golden.json"]


def test_scenarios_before_propose_is_absent(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="extract")
    got = summary.scenarios(run)
    assert isinstance(got, summary.Absent)
    assert got.what == "02-scenarios.json"


def test_scenarios_survives_a_non_dict_member(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    doc = read_json(run.scenarios)
    before = len(doc["scenarios"])
    doc["scenarios"].append("oops-a-string")
    write_json(run.scenarios, doc)
    rows = summary.scenarios(run)
    assert all(r.id_ for r in rows), "the string member is dropped, not raised on"
    # The count is the control the brief's assertion lacked: `all(...)` over an empty
    # list is `True`, so dropping every member -- not only the malformed one -- passed
    # it.
    assert len(rows) == before


def test_scenarios_survives_an_id_that_is_not_a_safe_path_segment(tmp_path):
    """An unsafe id yields a row with an empty join, never a traceback.

    `run.verdict`, `run.instance_dir` and `run.task_dir` all call `safe_segment`,
    which raises `UnsafeSegment` -- a `ValueError`, so neither an `except OSError`
    nor `_quietly`'s guard around the *read* catches it: the raise happens while
    building the path argument, before the read is attempted. `"../../etc"` is the
    shape `safe_segment`'s docstring names as a plausible thing for a confused stage
    to emit, and `paths.scenario_ids_with_tasks` filters for exactly this reason.
    All three joins are asserted, because guarding one and not its neighbours is
    what a `_suite_files`-only guard looks like from the outside.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.scenarios)
    doc["scenarios"].append(dict(doc["scenarios"][0], id="../../etc"))
    write_json(run.scenarios, doc)
    row = summary.scenarios(run)[-1]
    assert row.id_ == "../../etc"
    assert row.verdict == ""
    assert row.has_instance is False
    assert row.suite_files == []
    assert row.difficulty_overstated is False


def test_scenarios_survives_a_member_with_no_id_at_all(tmp_path):
    """A record missing `id` renders a row, and joins nothing.

    `is_safe_segment("")` is `False`, so the empty id takes the same branch the
    unsafe one does -- one predicate for both, rather than a `bool(sid)` test beside
    an `is_safe_segment(sid)` test that could disagree. Without this, an
    implementation that joined on `""` would probe `05-verdicts/.json` and
    `06-suite/`, and `06-suite/` itself holding a `task.toml` would report the whole
    suite directory as this scenario's package.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.scenarios)
    member = dict(doc["scenarios"][0])
    member.pop("id")
    doc["scenarios"].append(member)
    write_json(run.scenarios, doc)
    row = summary.scenarios(run)[-1]
    assert row.id_ == ""
    assert row.verdict == ""
    assert row.has_instance is False
    assert row.suite_files == []


def test_scenarios_survives_an_unreadable_verdicts_directory(tmp_path):
    """A `05-verdicts/` at mode 000 empties the join rather than raising.

    `read_json` on a file under an untraversable directory raises
    `PermissionError`, which `_quietly` catches -- so this tests the
    *composition*, and its value is that it is the shape a run copied out of a
    container under a different uid actually has. The record columns must still
    render: the run's scenarios are readable, and "the verdicts cannot be read" is
    a statement about one directory.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    run.verdicts_dir.chmod(0o000)
    try:
        rows = summary.scenarios(run)
        assert all(r.verdict == "" for r in rows)
        assert rows[0].title == "Find the open billing ticket", "the record still renders"
    finally:
        run.verdicts_dir.chmod(0o755)


def test_scenarios_survives_an_unreadable_suite_directory(tmp_path):
    """A `06-suite/` at mode 000 reports no package rather than raising.

    `Path.exists()` swallows ENOENT and ENOTDIR but *not* EACCES, so a probe for
    `06-suite/<sid>/task.toml` under an untraversable parent raises rather than
    returning False -- which is why `_suite_files` probes through `_exists`, the
    helper the stage spine already needed for the same reason. `has_instance` is the
    control: `04-instances/` is untouched, so a guard that had swallowed the whole
    join rather than this one probe would show up here.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    from rubrica.emit import emit_run

    run = build_toy_run(tmp_path / "runs")
    emit_run(run)
    run.suite_dir.chmod(0o000)
    try:
        rows = summary.scenarios(run)
        assert all(r.suite_files == [] for r in rows)
        assert rows[0].has_instance is True, "the instances directory is still readable"
    finally:
        run.suite_dir.chmod(0o755)


def test_suite_files_is_empty_when_no_package_was_written(tmp_path):
    """`_suite_files`' contract, asserted directly because Task 7 consumes it.

    The challenge section reads it to tell an accepted scenario whose package
    landed from one whose did not, so `[]` for "there is no package" is part of the
    interface rather than an implementation detail of this table.
    """
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    assert not run.suite_dir.exists(), "a challenged run has not emitted yet"
    assert summary._suite_files(run, "scn-open") == []
    assert summary._suite_files(run, "../../etc") == []


@pytest.mark.parametrize(
    "field,bad",
    [
        ("capability_refs", "nope"),
        ("capability_refs", ["oops-a-string"]),
        ("capability_refs", 7),
    ],
)
def test_scenarios_survives_a_capability_refs_that_is_not_a_list_of_dicts(tmp_path, field, bad):
    """The one nested collection on the record, guarded by `_dicts`.

    `"capability_refs": "nope"` is `_mapping`'s measured shape one level down --
    iterating the string yields characters, and each `.get` on one raises
    `AttributeError` -- and `["oops-a-string"]` is `_dicts`' own: the list is a list,
    so a bare `or []` passes it straight through to the same raise. The row still
    renders, with no cells, because "this scenario's refs are malformed" is
    `validate`'s finding to report and not a reason for the page to fail.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    doc = read_json(run.scenarios)
    doc["scenarios"][0][field] = bad
    write_json(run.scenarios, doc)
    rows = summary.scenarios(run)
    assert rows[0].cells == []
    assert rows[0].id_ == "scn-open", "the rest of the row is unaffected"
    assert len(rows) == 5, "and so are its siblings"


def test_scenarios_on_a_document_that_is_not_a_mapping_is_malformed(tmp_path):
    """A `02-scenarios.json` holding a list is the artifact present and unreadable.

    `_mapping`'s reason, at the top of the section rather than inside a row: a
    truthy non-dict reaches `.get` and raises `AttributeError`, and a document that
    is a JSON array is not a scenarios artifact at all. `Malformed` is the honest
    answer -- the file is on disk, the spine counts it, and there is nothing to
    tabulate -- and `validate --stage propose` is what names the defect.
    """
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    write_json(run.scenarios, ["scn-open"])
    got = summary.scenarios(run)
    assert isinstance(got, summary.Malformed)
    assert got.what == "02-scenarios.json"
    produced = {row.name: row.produced for row in summary.stage_spine(run)}
    assert produced["propose"] is True, "the spine counts the file, so the page must agree"


# --- 3.6 the challenge tallies and the emitted-suite inventory ----------------


def test_challenge_tallies_verdicts_by_value(tmp_path):
    """The tally is keyed by the verdict each part actually holds.

    The toy fixture is *uniform* here -- all four verdicts are `accept` -- so a
    test that only asserted `sum(tallies.values()) == judged` would pass an
    implementation that keyed every part under one invented label, or under the
    filename. One verdict is flipped to `re-seed` so the dict has two keys to get
    wrong, which is the fixture-uniformity trap this plan has already lost two
    mutations to.

    `scn-blocked` is the one flipped, and which part it is matters: `list_json`
    sorts by filename, so flipping the *first* part makes the first-seen key order
    `re-seed, accept` while the sorted order is `accept, re-seed`. Dict equality
    ignores order, so without the `list(...)` assertion the sort that makes the
    page diffable is unlocked -- and flipping `scn-empty` instead leaves the two
    orders identical, which is a fixture that cannot see the difference.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.verdict("scn-blocked"))
    assert doc["verdict"] == "accept", "the fixture must start uniform for the flip to vary it"
    doc["verdict"] = "re-seed"
    write_json(run.verdict("scn-blocked"), doc)
    got = summary.challenge(run)
    assert got.tallies == {"accept": 3, "re-seed": 1}
    assert list(got.tallies) == ["accept", "re-seed"], "sorted, not in first-seen order"
    assert got.judged == 4
    assert sum(got.tallies.values()) == got.judged


def test_challenge_tallies_a_verdict_with_no_value_as_unrecorded(tmp_path):
    """`dispositions`' ruling on a blank label, applied to the verdict column.

    A verdict part whose `verdict` is missing or empty is a hand-edited record;
    grouping it under `""` would render as a blank row that reads like a rendering
    bug rather than as a fact about the part.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.verdict("scn-empty"))
    doc["verdict"] = ""
    write_json(run.verdict("scn-empty"), doc)
    got = summary.challenge(run)
    assert got.tallies == {"(unrecorded)": 1, "accept": 3}
    assert list(got.tallies) == ["(unrecorded)", "accept"], "sorted, not in first-seen order"


def test_challenge_counts_emitted_packages_apart_from_the_verdicts(tmp_path):
    """`packages` counts `06-suite/`, not `05-verdicts/`.

    On an unedited toy run the two counts are both 4, so asserting `packages > 0`
    is satisfied by an implementation returning `len(verdict_paths)`. One package
    directory is removed so the two numbers differ, which is the only shape that
    tells them apart.
    """
    import shutil

    from rubrica.emit import emit_run

    run = build_toy_run(tmp_path / "runs")
    emitted, _ = emit_run(run)
    shutil.rmtree(run.task_dir(emitted[0]))
    got = summary.challenge(run)
    assert got.packages == len(emitted) - 1
    assert got.judged == len(emitted), "the verdict count is untouched"
    assert got.incomplete_packages == [], "a package that is gone is absent, not incomplete"


def test_challenge_names_a_package_missing_a_file(tmp_path):
    """A package missing one of `SUITE_FILES` is named, and only that one.

    The exact-list assertion is the lock: `incomplete_packages` returning every
    emitted id would satisfy a membership test while telling a reader nothing.
    """
    from rubrica.emit import emit_run

    run = build_toy_run(tmp_path / "runs")
    emitted, _ = emit_run(run)
    (run.task_dir(emitted[0]) / "golden.json").unlink()
    got = summary.challenge(run)
    assert got.incomplete_packages == [emitted[0]]
    assert got.packages == len(emitted), "the package is still there, just short a file"


def test_challenge_reports_no_package_before_emit(tmp_path):
    """A judged run that never emitted: verdicts tallied, inventory empty."""
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    got = summary.challenge(run)
    assert got.judged == 4
    assert got.packages == 0
    assert got.incomplete_packages == []


def test_challenge_before_the_stage_is_absent(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    got = summary.challenge(run)
    assert isinstance(got, summary.Absent)
    assert got.what == "05-verdicts/"


def test_challenge_carries_the_smoke_report_when_one_was_written(tmp_path):
    """`smoke` is the report document, or None -- not a boolean.

    `build_toy_run` never writes `07-report.json` even at its last checkpoint, so
    both halves are asserted here: None before smoke ran, and the document's own
    fields after, since a `bool(path.exists())` would satisfy the second half
    alone.
    """
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    assert summary.challenge(run).smoke is None
    write_json(run.report, {"schema_version": "0.1", "checked": 4, "failures": []})
    assert summary.challenge(run).smoke == {
        "schema_version": "0.1",
        "checked": 4,
        "failures": [],
    }


def test_challenge_on_an_unreadable_verdicts_dir_is_malformed_not_absent(tmp_path):
    """`list_json` raises `UsageError`, which is a ValueError and not an OSError.

    The same shape `contradictions` documents: the guard has to catch the class,
    not `OSError`, or the one absolute promise of this module is broken by a
    `chmod` on one directory.

    And the marker has to be `Malformed`: this section's absence means "no verdicts
    yet", which is every run short of `challenge`, and a run whose verdicts are all
    on disk and unlistable is the opposite fact. The pre-stage test above is the
    control, so "everything is a malformation" cannot pass either.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    run.verdicts_dir.chmod(0o000)
    try:
        got = summary.challenge(run)
        assert isinstance(got, summary.Malformed)
        assert got.what == "05-verdicts/"
    finally:
        run.verdicts_dir.chmod(0o755)


def test_challenge_on_an_unreadable_suite_dir_still_tallies(tmp_path):
    """`scenario_ids_with_tasks` raises `UsageError` too, and only the inventory dies.

    The tally is the control: an unreadable `06-suite/` must cost the package
    count and nothing else, because the verdicts are perfectly readable and "how
    did the adversary judge this run" is the half a reader came for.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    from rubrica.emit import emit_run

    run = build_toy_run(tmp_path / "runs")
    emit_run(run)
    run.suite_dir.chmod(0o000)
    try:
        got = summary.challenge(run)
        assert got.packages == 0
        assert got.tallies == {"accept": 4}, "the verdicts still tally"
    finally:
        run.suite_dir.chmod(0o755)


# --- the orphaned temp-file scan ---------------------------------------------


def test_orphaned_temp_files_finds_a_stray_tmp(tmp_path):
    """Found by inspection during design: an orphaned
    02-scenarios.json.tmp.43146.cb890a5abaf7 was sitting in the newest run on
    disk, and decisions.md records an earlier one removed by hand."""
    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    (run.root / "02-scenarios.json.tmp.4242.deadbeef").write_text("{}", encoding="utf-8")
    assert summary.orphaned_temp_files(run) == ["02-scenarios.json.tmp.4242.deadbeef"]


def test_orphaned_temp_files_sorts_more_than_one(tmp_path):
    """Sorted, for the reason every other collection on this page is: two runs
    over the same directory must render the same list, and `iterdir` order is the
    filesystem's."""
    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    for name in ("02-scenarios.json.tmp.9.zz", "01-goals.json.tmp.1.aa"):
        (run.root / name).write_text("{}", encoding="utf-8")
    assert summary.orphaned_temp_files(run) == [
        "01-goals.json.tmp.1.aa",
        "02-scenarios.json.tmp.9.zz",
    ]


def test_orphaned_temp_files_is_empty_on_a_clean_run(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    assert summary.orphaned_temp_files(run) == []


def test_orphaned_temp_files_scans_only_the_run_root(tmp_path):
    """The scan is one directory deep, and that is the scope, not an oversight.

    A stray under `01-claims/` is already invisible to every reader of that
    directory -- `list_json` keeps only a `.json` suffix -- so naming it here would
    put a file on the page that nothing else in the run reacts to. The run root is
    where the sealed artifacts live and where an interrupted seal leaves its temp.
    """
    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    (run.claims_dir / "api-json.json.tmp.7.bb").write_text("{}", encoding="utf-8")
    assert summary.orphaned_temp_files(run) == []


def test_orphaned_temp_files_on_an_unreadable_run_root_is_empty(tmp_path):
    """`except OSError` around `iterdir`, at the shape that reaches it.

    A run root at mode 000 is the shape a run copied out of a container under a
    different uid has, and the scan reporting "no strays" is the honest answer:
    there is nothing it can see.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    run.root.chmod(0o000)
    try:
        assert summary.orphaned_temp_files(run) == []
    finally:
        run.root.chmod(0o755)


# --- 3.7 the flag table ------------------------------------------------------


def test_code_stages_is_exactly_the_stages_that_run_as_code():
    """`_CODE_STAGES` re-derived, because a hardcoded set got `emit` wrong once.

    CLAUDE.md: the code stages have no `manifest.stages` entry by design and
    "their absence there is not a finding", so `stage-record-incomplete` must
    exempt exactly them. `emit` is deliberately *not* exempt -- `rb-emit` is a
    thin wrapper over `rubrica emit`, so `emit` does get a record and must stay
    accusable -- and that is the half a hardcoded set loses first.

    Derived from `skills.discover()` rather than compared against a second
    hand-written list, so converting a stage from code to a skill (or the other
    way) fails here instead of quietly exempting it forever.
    """
    from rubrica import skills

    declared = {s.contract.get("stage") for s in skills.discover()}
    assert set(STAGES) - declared == summary._CODE_STAGES
    assert "emit" not in summary._CODE_STAGES, "rb-emit exists, so emit must stay accusable"


def test_flags_fire_low_utilisation_below_the_threshold(tmp_path, monkeypatch):
    """The threshold is patched *above* the fixture's own pct, which is nearly 100.

    Measured: the toy run's claim utilisation is 95.0% (api-json 9/10, notes-md
    8/8, trace-json 2/2) -- the one uncited claim is `clm-api-010`, the run's
    `tool` claim, which nothing consumes yet. The predicate is a strict `<`, so
    patching the threshold to the fixture's own pct -- as this test was first
    written, when that pct was 100.0 -- leaves `95.0 < 95.0` False and the flag
    silently not firing while the test claims to have observed it. 95.1 is the
    smallest round value that makes the predicate observable, and the pct is
    asserted first so a fixture change moves this test rather than hiding in it.
    """
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    assert summary.utilisation(run).pct == 95.0, "the fixture this threshold is chosen against"
    monkeypatch.setattr(summary, "LOW_UTILISATION_PCT", 95.1)
    fired = {f.id_: f for f in summary.flags(run)}
    assert "low-utilisation" in fired
    assert "95.0%" in fired["low-utilisation"].headline


def test_flags_do_not_fire_low_utilisation_above_the_threshold(tmp_path, monkeypatch):
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    monkeypatch.setattr(summary, "LOW_UTILISATION_PCT", 0.0)
    ids = {f.id_ for f in summary.flags(run)}
    assert "low-utilisation" not in ids


def test_flags_do_not_fire_low_utilisation_exactly_at_the_threshold(tmp_path, monkeypatch):
    """`below`, not `at or below` -- the boundary the threshold text promises.

    Without this the pair above is satisfied by `<=` just as well as by `<`, and
    the threshold string on the page says "below". A flag whose stated rule and
    whose predicate disagree at the boundary is worse than no flag.

    95.0 is the fixture's own measured pct -- see the firing test above for where
    that number comes from -- so this sits exactly on the boundary rather than
    merely near it.
    """
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    monkeypatch.setattr(summary, "LOW_UTILISATION_PCT", 95.0)
    ids = {f.id_ for f in summary.flags(run)}
    assert "low-utilisation" not in ids


def test_flags_do_not_fire_low_utilisation_before_the_seal(tmp_path, monkeypatch):
    """`Absent` utilisation is not 0%, so the flag must stay silent.

    A threshold of 100.1 fires on any readable pct at all; a run with no world
    model has no pct, and reporting "0% cited" there would be a judgment about
    reconcile passes that have not run.
    """
    run = build_toy_run(tmp_path / "runs", upto="reconcile-gaps")
    monkeypatch.setattr(summary, "LOW_UTILISATION_PCT", 100.1)
    assert isinstance(summary.utilisation(run), summary.Absent)
    ids = {f.id_ for f in summary.flags(run)}
    assert "low-utilisation" not in ids


def test_flags_do_not_raise_when_nothing_was_extracted(tmp_path, monkeypatch):
    """`util.pct is not None` is load-bearing, and this is the shape that reaches it.

    A claims file with an empty `claims` array is schema-valid -- claims-0.1.json
    sets no `minItems` -- so a run whose extract pass found nothing yields a
    `Utilisation` with real artifact rows, `total == 0` and `pct is None`. That is
    the one state where the section is present and the number is not: without the
    `is not None` guard, `None < LOW_UTILISATION_PCT` raises `TypeError` on a
    perfectly readable run, which is this module's one absolute promise broken.

    Not `Absent` and not 0%, which is `utilisation`'s own ruling: 0% asserts every
    claim was dropped, and "there were no claims to cite" is a different fact.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    for path in sorted(run.claims_dir.iterdir()):
        doc = read_json(path)
        doc["claims"] = []
        write_json(path, doc)
    util = summary.utilisation(run)
    assert util.pct is None and util.total == 0, "the shape under test"
    monkeypatch.setattr(summary, "LOW_UTILISATION_PCT", 100.1)
    ids = {f.id_ for f in summary.flags(run)}
    assert "low-utilisation" not in ids
    assert "uncited-artifacts" not in ids, "a 0-of-0 input is what the gate exempts"


def test_flags_fire_uncited_artifacts_and_name_them(tmp_path):
    """The toy fixture has *nothing* uncited, so the fixture has to be varied.

    An extra claims artifact nothing in the world model cites is the shape
    `refs.check_claim_utilisation` fires on, and naming it is the actionable half:
    "one input contributed nothing" is not useful without which one.
    """
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    assert summary.utilisation(run).uncited == [], "the fixture starts fully cited"
    write_json(run.claims_dir / "stray-md.json", _stray_claims_doc())
    fired = {f.id_: f for f in summary.flags(run)}
    assert "uncited-artifacts" in fired
    assert "stray-md" in fired["uncited-artifacts"].detail


def test_flags_do_not_fire_uncited_artifacts_on_a_fully_cited_run(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    ids = {f.id_ for f in summary.flags(run)}
    assert "uncited-artifacts" not in ids


def test_flags_fire_unresolved_contradictions(tmp_path):
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    run.contradictions_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        run.contradiction_part("subj-a"),
        {
            "schema_version": "0.1",
            "subject_id": "subj-a",
            "contradictions": [{"id": "con-1", "resolution": "unresolved"}],
        },
    )
    fired = {f.id_: f for f in summary.flags(run)}
    assert "unresolved-contradictions" in fired
    assert fired["unresolved-contradictions"].headline.startswith("1 ")


def test_flags_do_not_fire_unresolved_when_all_are_resolved(tmp_path):
    """The negative half, and a lock on *which* number the flag reads.

    The toy fixture already records one `preferred_a` contradiction, so a flag
    reading `cons.total` instead of `by_resolution["unresolved"]` fires here --
    which is exactly the misread `contradictions`' own docstring records against
    the top-level `resolution` field.
    """
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    run.contradictions_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        run.contradiction_part("subj-a"),
        {
            "schema_version": "0.1",
            "subject_id": "subj-a",
            "contradictions": [{"id": "con-1", "resolution": "both_possible"}],
        },
    )
    assert summary.contradictions(run).total == 2, "the fixture's own contradiction is still there"
    ids = {f.id_ for f in summary.flags(run)}
    assert "unresolved-contradictions" not in ids


def test_flags_fire_coverage_halted(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
    doc = read_json(run.coverage_latest)
    doc["verdict"] = "halted_no_progress"
    write_json(run.coverage_latest, doc)
    fired = {f.id_: f for f in summary.flags(run)}
    assert "coverage-halted" in fired
    assert "halted_no_progress" in fired["coverage-halted"].headline


def test_flags_do_not_fire_coverage_halted_on_converged(tmp_path):
    from rubrica.artifacts import read_json

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
    assert read_json(run.coverage_latest)["verdict"] == "converged"
    ids = {f.id_ for f in summary.flags(run)}
    assert "coverage-halted" not in ids


def test_flags_do_not_fire_coverage_halted_before_score(tmp_path):
    """An `Absent` coverage section is not a halt.

    `coverage` returns `Absent` before `score` runs, and a `Coverage` whose
    `terminal_verdict` is the empty string for a run whose `latest.json` records
    none -- neither is a run that stopped making progress, and flagging either
    would put a halt on the page of every run that has not scored yet.
    """
    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    assert isinstance(summary.coverage(run), summary.Absent)
    ids = {f.id_ for f in summary.flags(run)}
    assert "coverage-halted" not in ids


def test_flags_do_not_fire_coverage_halted_on_an_unrecorded_verdict(tmp_path):
    """A `latest.json` with no `verdict` is a score-stage defect, not a halt.

    `terminal_verdict` is `""` there, and `"" != "converged"` -- so a flag that
    tested only inequality would render "Coverage ended" with nothing after it,
    which is the blank-label shape `dispositions` and the verdict tally both rule
    against.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
    doc = read_json(run.coverage_latest)
    del doc["verdict"]
    write_json(run.coverage_latest, doc)
    assert summary.coverage(run).terminal_verdict == ""
    ids = {f.id_ for f in summary.flags(run)}
    assert "coverage-halted" not in ids


def test_flags_fire_difficulty_overstated_and_name_the_scenario(tmp_path):
    """`difficulty_overstated` is uniformly False on the toy run, so vary it.

    `scn-blocked` is proposed at `hop_depth: 2` and its verdict finds the same 2
    calls; dropping the found count to 1 is the one edit that makes the column
    non-uniform, and without it the flag's predicate is unobservable.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    assert not any(r.difficulty_overstated for r in summary.scenarios(run))
    doc = read_json(run.verdict("scn-blocked"))
    doc["minimum_tool_calls_found"] = 1
    write_json(run.verdict("scn-blocked"), doc)
    fired = {f.id_: f for f in summary.flags(run)}
    assert "difficulty-overstated" in fired
    assert fired["difficulty-overstated"].detail == "scn-blocked"


def test_flags_do_not_fire_difficulty_overstated_on_an_unedited_run(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    ids = {f.id_ for f in summary.flags(run)}
    assert "difficulty-overstated" not in ids


def test_flags_fire_orphaned_temp(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    (run.root / "02-scenarios.json.tmp.1.x").write_text("{}", encoding="utf-8")
    fired = {f.id_: f for f in summary.flags(run)}
    assert "orphaned-temp" in fired
    assert "02-scenarios.json.tmp.1.x" in fired["orphaned-temp"].detail


def test_flags_do_not_fire_orphaned_temp_on_a_clean_run(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    ids = {f.id_ for f in summary.flags(run)}
    assert "orphaned-temp" not in ids


def test_flags_fire_stage_record_incomplete_and_exempt_the_code_stages(tmp_path):
    """The fixture already has an empty `manifest.stages`, so the *detail* is the test.

    Measured: `build_toy_run` mints a manifest whose `stages` is `{}` at every
    checkpoint, so this flag fires on an unedited toy run and a test that "emptied
    stages" first would be asserting against a no-op mutation. What is worth
    locking is which stages get accused: the dispatched ones, and not `intake` or
    `reconcile-seal`, whose absence from `manifest.stages` CLAUDE.md states is not
    a finding.
    """
    from rubrica.artifacts import read_json

    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    assert read_json(run.manifest)["stages"] == {}, "the fixture records no stage"
    fired = {f.id_: f for f in summary.flags(run)}
    assert "stage-record-incomplete" in fired
    named = set(fired["stage-record-incomplete"].detail.split(" -- ")[0].split(", "))
    assert {"extract", "propose", "reconcile-goals"} <= named
    assert named.isdisjoint(summary._CODE_STAGES), "a code stage must never be accused"


def test_flags_do_not_fire_stage_record_incomplete_when_every_stage_is_recorded(tmp_path):
    """The negative half: a complete record silences the flag.

    Every produced stage that is not a code stage is given a record, so nothing is
    owed and the flag must not fire. What that locks is the `- recorded` term:
    dropping it leaves the flag firing on a fully recorded run, which is the one
    mutation only this test kills.

    **It cannot catch an over-broad `_CODE_STAGES`, and an earlier version of this
    docstring claimed it could.** Measured both halves of that claim wrong: the
    fixture here is built from `produced - summary._CODE_STAGES`, so it grows with
    the exemption and the flag stays silent however broad the set gets; and the
    positive test above does catch it, via `{"extract", "propose",
    "reconcile-goals"} <= named`, as does
    test_code_stages_is_exactly_the_stages_that_run_as_code. Recorded rather than
    quietly deleted because this repo's comments cite measurements, and a miscited
    one is worse than none.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    produced = {row.name for row in summary.stage_spine(run) if row.produced}
    manifest = read_json(run.manifest)
    manifest["stages"] = {
        name: {"model": "m", "effort": "high", "skill_sha256": "0" * 64}
        for name in sorted(produced - summary._CODE_STAGES)
    }
    assert manifest["stages"], "the mutation must actually record something"
    write_json(run.manifest, manifest)
    ids = {f.id_ for f in summary.flags(run)}
    assert "stage-record-incomplete" not in ids


def test_flags_do_not_fire_stage_record_incomplete_for_a_stage_that_never_ran(tmp_path):
    """A record is owed only for a stage the spine shows as *produced*.

    A propose-level run never dispatched `score`, `instantiate`, `challenge` or
    `emit`, so accusing them of an unrecorded dispatch would put four findings on
    the page of every partial run -- and partial runs are the primary case.
    """
    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    fired = {f.id_: f for f in summary.flags(run)}
    named = set(fired["stage-record-incomplete"].detail.split(" -- ")[0].split(", "))
    assert named.isdisjoint({"score", "instantiate", "challenge", "emit"})


def _stray_claims_doc() -> dict:
    """A claims artifact the toy world model cites nothing from.

    Beside the flag tests rather than in `tests/toy.py`: it is not a checkpoint of
    the golden world, it is the one addition to it that makes `uncited-artifacts`
    observable, and putting it in the fixture module would give every other test's
    run an uncited input.
    """
    return {
        "schema_version": "0.1",
        "artifact_id": "stray-md",
        "claims": [
            {
                "id": "clm-stray-001",
                "kind": "capability",
                "statement": "nothing in the world model cites this",
                "confidence": "low",
                "derivation": "stated",
                "evidence": [{"artifact_id": "stray-md", "locator": "#/never"}],
            }
        ],
    }


def _run_with_every_flag(tmp_path, monkeypatch) -> RunPaths:
    """A run engineered so every flag in the table fires at once.

    One fixture rather than seven, because the property under test is about the
    table as a whole: that no flag can reach the page without stating the rule
    that put it there. Each edit below is the same one the single-flag test above
    it makes, so a flag that stops firing here fails there too and the diagnosis
    is not ambiguous.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    # low-utilisation and uncited-artifacts: one claims artifact nothing cites
    # drops the pct off the fixture's own 95.0 and gives the uncited list a
    # member. The threshold is patched to 100.0 below, which is above the pct
    # either way -- what this arranges is the uncited list, not the crossing.
    write_json(run.claims_dir / "stray-md.json", _stray_claims_doc())
    monkeypatch.setattr(summary, "LOW_UTILISATION_PCT", 100.0)
    write_json(
        run.contradiction_part("subj-stray"),
        {
            "schema_version": "0.1",
            "subject_id": "subj-stray",
            "contradictions": [{"id": "con-stray", "resolution": "unresolved"}],
        },
    )
    latest = read_json(run.coverage_latest)
    latest["verdict"] = "halted_round_cap"
    write_json(run.coverage_latest, latest)
    verdict = read_json(run.verdict("scn-blocked"))
    verdict["minimum_tool_calls_found"] = 1
    write_json(run.verdict("scn-blocked"), verdict)
    (run.root / "01-goals.json.tmp.5.abc").write_text("{}", encoding="utf-8")
    # stage-record-incomplete needs no edit: build_toy_run mints an empty
    # manifest.stages.
    return run


def test_every_flag_states_its_threshold(tmp_path, monkeypatch):
    """A flag whose threshold is not on the page is a black box.

    Asserted over a run where *every* flag fires, not over the two that happen to
    fire on a propose-level run with a stray temp file: the property is that no
    flag can reach the page without its rule, and a loop over two of seven checks
    it for two. The id set is pinned in the same assertion, so a flag added
    without a threshold cannot slip in behind a `for` loop that never sees it.
    """
    run = _run_with_every_flag(tmp_path, monkeypatch)
    fired = summary.flags(run)
    assert {f.id_ for f in fired} == {
        "low-utilisation",
        "uncited-artifacts",
        "unresolved-contradictions",
        "coverage-halted",
        "difficulty-overstated",
        "orphaned-temp",
        "stage-record-incomplete",
    }
    for flag in fired:
        assert flag.threshold, f"{flag.id_} states no threshold"
        assert flag.headline, f"{flag.id_} states no headline"
        assert flag.detail, f"{flag.id_} states no detail"


def test_flags_are_unique_and_ordered_stably(tmp_path, monkeypatch):
    """One row per rule, in a fixed order, so two renderings of a run diff cleanly.

    The order is pinned against a **literal** sequence, not against a second call
    to `flags` on the same run. Measured: comparing the call to itself --
    `ids == [f.id_ for f in summary.flags(run)]`, which is what this test asserted
    first -- is satisfied by every deterministic implementation, and `return
    found[::-1]` survived all 194 tests in this module. So did `return
    sorted(found, key=lambda f: f.id_)`. The uniqueness half was already real
    (`found + found[:1]` was killed); the order half was a predicate nobody had
    watched fail.

    The literal is the declaration order in `flags`, and that is deliberately the
    thing under test rather than an alphabetical or a severity order: what a reader
    diffing two renderings of the same run depends on is that the table does not
    reshuffle, and the only way to state that independently of the implementation
    is to write the sequence down.
    """
    run = _run_with_every_flag(tmp_path, monkeypatch)
    ids = [f.id_ for f in summary.flags(run)]
    assert len(ids) == len(set(ids))
    assert ids == [
        "low-utilisation",
        "uncited-artifacts",
        "unresolved-contradictions",
        "coverage-halted",
        "difficulty-overstated",
        "orphaned-temp",
        "stage-record-incomplete",
    ]


def test_flags_keep_their_relative_order_on_a_partial_run(tmp_path):
    """The same fixed order over a subset, because partial runs are the primary case.

    A propose-level run with a stray temp file fires two of the seven flags, and
    they must come out in the order they hold in the full table. Asserted
    separately from the all-seven test above: a table whose order is fixed only
    when every rule fires is not a fixed order, and 10 of the 11 runs measured at
    design time would have rendered a subset.
    """
    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    (run.root / "02-scenarios.json.tmp.1.x").write_text("{}", encoding="utf-8")
    assert [f.id_ for f in summary.flags(run)] == ["orphaned-temp", "stage-record-incomplete"]


def test_flags_on_an_empty_run_do_not_raise(tmp_path):
    empty = tmp_path / "run-empty"
    empty.mkdir()
    assert summary.flags(RunPaths(empty)) == []


def test_flags_on_an_unreadable_run_root_do_not_raise(tmp_path):
    """The module's one absolute promise, at the flag table.

    `flags` calls six other builders and each can return `Absent`, which is why
    every one of them is `isinstance`-checked before it is indexed. A run root at
    mode 000 makes all six absent at once, which is the cheapest way to find a
    missing check.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path / "runs")
    run.root.chmod(0o000)
    try:
        assert summary.flags(run) == []
    finally:
        run.root.chmod(0o755)


# --------------------------------------------------------------- the renderer ---
# Every assertion below is on a rendered *value*, not on a heading. Measured: a
# renderer that emits `<h2>Inputs</h2>` and nothing under it satisfies
# `"Inputs" in html`, so a heading-only test is satisfied by a page that renders
# no data at all -- the substring-of-message shape CLAUDE.md names, at the one
# place in this module where every number a reader came for is interpolated.


def test_render_produces_one_self_contained_document(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    html = summary.run_summary(run)
    assert html.startswith("<!doctype html>")
    assert "</html>" in html
    assert "<style>" in html, "CSS is inline; the page has no external assets"


def test_render_references_no_external_resource(tmp_path):
    """Self-contained means no network: a page that fetches is a page that breaks
    when the run directory is archived or read offline."""
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    html = summary.run_summary(run)
    for token in ("http://", "https://", "<script src=", '<link rel="stylesheet"'):
        assert token not in html, f"{token} makes the page depend on something outside it"


def test_render_names_the_run(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    html = summary.run_summary(run)
    assert run.root.name in html
    # The bare-substring form above was measured satisfiable with the run name
    # dropped from *both* the `<h1>` and the `<title>`: the manifest's `run_id` is
    # the directory name on every run this code mints, so the Run header section
    # satisfied it on its own. The heading is pinned in the shape it renders in.
    assert f"<h1>{run.root.name}</h1>" in html
    assert f"<title>{run.root.name} " in html


def test_render_includes_every_section_heading(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    html = summary.run_summary(run)
    for heading in ("Inputs", "Scenarios", "Coverage", "World model", "Flags"):
        assert heading in html, f"the {heading} section is missing"
        # As an `<h2>`, not merely somewhere on the page: measured, renaming the
        # Coverage heading left the bare-substring loop green, because the section's
        # own prose says "Coverage ended halted_no_progress". A heading test that
        # any sentence can satisfy is not a heading test.
        assert f"<h2>{heading}</h2>" in html, f"the {heading} heading is not a heading"


def test_render_escapes_prose_carrying_markup_and_quotes(tmp_path):
    """discriminating_fact and verdict notes reach a title attribute and carry
    double quotes in real runs; an unescaped one ends the attribute early."""
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    doc = read_json(run.scenarios)
    doc["scenarios"][0]["discriminating_fact"] = 'he said "<script>alert(1)</script>" & left'
    write_json(run.scenarios, doc)
    html = summary.run_summary(run)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "&quot;" in html


def test_render_escapes_a_title_bearing_markup(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="propose-seal")
    doc = read_json(run.scenarios)
    doc["scenarios"][0]["title"] = "<b>bold</b>"
    write_json(run.scenarios, doc)
    html = summary.run_summary(run)
    assert "<b>bold</b>" not in html
    assert "&lt;b&gt;bold&lt;/b&gt;" in html


def test_render_states_an_absence_rather_than_omitting_the_section(tmp_path):
    """The 10-of-11 case: a partial run renders every section, saying what is
    not there. A section silently omitted is indistinguishable from one the
    renderer forgot.
    """
    run = build_toy_run(tmp_path / "runs", upto="extract")
    html = summary.run_summary(run)
    assert "01-world-model.json" in html, "the absent artifact is named"
    assert "Scenarios" in html, "the section still has its heading"
    # The heading half of the assertion above is satisfied by a page that renders
    # the heading and nothing else, so the absence under it is pinned too: the
    # section's whole content on this run is the stated absence.
    assert "Not present: 02-scenarios.json" in html


def test_render_on_an_empty_directory_still_produces_a_page(tmp_path):
    empty = tmp_path / "run-empty"
    empty.mkdir()
    html = summary.run_summary(RunPaths(empty))
    assert html.startswith("<!doctype html>")
    assert "</html>" in html
    # Not just well-formed: the page is *useful*, which for a directory holding
    # nothing means it names what it looked for. Every one of these is a section
    # that would have vanished had `_section` skipped an Absent.
    for what in (
        "Not present: manifest.json",
        "Not present: 00-objective.json",
        "Not present: 00-triage.json",
        "Not present: 01-world-model.json",
        "Not present: 01-contradictions/",
        "Not present: 03-coverage/",
        "Not present: 02-scenarios.json",
        "Not present: 05-verdicts/",
        "Not present: decisions.md",
    ):
        assert what in html, f"{what} is not stated on the page"


def test_render_links_each_scenario_to_its_artifacts(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    html = summary.run_summary(run)
    assert "05-verdicts/" in html, "ids are links to the artifacts on disk"
    assert '<a href="05-verdicts/scn-open.json">scn-open</a>' in html


def test_render_includes_decisions_md_when_present(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    (run.root / "decisions.md").write_text("- a decision was taken\n", encoding="utf-8")
    assert "a decision was taken" in summary.run_summary(run)


def test_render_escapes_decisions_md(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    (run.root / "decisions.md").write_text("- <b>not bold</b>\n", encoding="utf-8")
    html = summary.run_summary(run)
    assert "<b>not bold</b>" not in html
    assert "&lt;b&gt;not bold&lt;/b&gt;" in html


def test_render_marks_the_spine_produced_and_absent_per_stage(tmp_path):
    """The first thing a reader of a partial run needs, and it must distinguish.

    Both classes are asserted, because a spine that marks every stage `yes` reads
    as a complete run and a spine that marks every stage `no` reads as a run that
    never started -- and either is satisfied by a test that only looks for the
    stage names.
    """
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    html = summary.run_summary(run)
    assert '<li class="yes">challenge</li>' in html
    assert '<li class="no">emit</li>' in html
    assert '<li class="no">survey</li>' in html
    for stage in STAGES:
        assert f">{stage}</li>" in html, f"{stage} is missing from the spine"


def test_render_shows_a_recorded_limit_as_its_value(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge", max_rounds=2, max_scenarios=8)
    html = summary.run_summary(run)
    assert "<tr><td>max_rounds</td><td>2</td></tr>" in html
    assert "<tr><td>max_scenarios</td><td>8</td></tr>" in html


def test_render_shows_the_part_budget_row_whether_or_not_it_is_set(tmp_path):
    """Both states, because the row is the point: a reader comparing two runs has
    to be able to see that one set a finer part budget and the other took the
    default, and a row rendered only when the key is present hides half of that.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    html = summary.run_summary(run)
    assert (
        '<tr><td>max_scenario_part_bytes</td><td><span class="absent">not recorded</span></td></tr>'
    ) in html

    doc = read_json(run.manifest)
    doc["limits"]["max_scenario_part_bytes"] = 9000
    write_json(run.manifest, doc)
    html = summary.run_summary(run)
    assert "<tr><td>max_scenario_part_bytes</td><td>9000</td></tr>" in html


def test_render_marks_a_missing_limit_rather_than_blanking_the_cell(tmp_path):
    """`esc(None)` is the empty string, so a missing limit would render blank.

    Measured in Task 2: a manifest with no `limits` gave `max_rounds` an empty
    `<td>`, and a blank cell reads as a ceiling of nothing rather than as a field
    the manifest never carried.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.manifest)
    del doc["limits"]
    write_json(run.manifest, doc)
    html = summary.run_summary(run)
    assert '<tr><td>max_rounds</td><td><span class="absent">not recorded</span></td></tr>' in html
    assert "<tr><td>max_rounds</td><td></td></tr>" not in html


def test_render_names_every_input_with_its_bytes_and_the_total(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    html = summary.run_summary(run)
    got = summary.inputs(run)
    for row in got.rows:
        # The row prefix, not the id on its own: Task 4's claim-utilisation table
        # renders the same `artifact_id` values, so `row.artifact_id in html` held
        # whether or not the *inputs* table rendered it -- measured, replacing the
        # inputs id cell with a literal left the assertion green. The two cells that
        # follow are what scope it to this table.
        assert (
            f'<td class="mono">{row.artifact_id}</td>'
            f"<td>{row.kind}</td>"
            f'<td class="num">{row.bytes_}</td>' in html
        )
        assert f'<a href="00-inputs/{row.stored_as}">' in html
    assert f"{got.total_bytes} bytes" in html


def test_render_shows_a_supported_verdict_that_is_not_a_boolean(tmp_path):
    """`Objective.supported` is typed `object` on purpose; the page must not
    coerce it. A hand-edited `"supported": "partly"` renders as "partly", because
    rendering False there would invent a gate-0 verdict the pass never gave.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="triage-seal")
    doc = read_json(run.objective)
    doc["objective_review"]["supported"] = "partly"
    write_json(run.objective, doc)
    html = summary.run_summary(run)
    assert "Supported:</b> partly" in html


def test_render_reports_the_predicted_against_the_observed_surface_count(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="triage-seal")
    got = summary.objective(run)
    html = summary.run_summary(run)
    assert f"predicted surfaces:</b> {got.predicted_count}" in html
    assert f"observed surfaces:</b> {len(got.surfaces)}" in html
    for surface in got.surfaces:
        assert surface.name in html
        assert f'<td class="num">{surface.bytes_}</td>' in html


def test_render_lists_the_admitted_candidates_in_priority_order(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="triage-seal")
    got = summary.dispositions(run)
    html = summary.run_summary(run)
    assert f"{got.admit_count} admitted" in html
    # Indexed inside the admits table, not over the whole page. Measured:
    # `html.index(candidate_id)` over the whole page found the id in the Objective
    # section's surface-evidence titles, which render *above* this table and in a
    # different order -- so `_disposition_rows(got.admits[::-1])` survived.
    start = html.index("Admitted, in priority order")
    table = html[start : html.index("</table>", start)]
    positions = [table.index(str(member["candidate_id"])) for member in got.admits]
    assert positions == sorted(positions), "the admits table reshuffled the priority order"


def test_render_distinguishes_a_closed_deficiency_from_an_open_one(tmp_path):
    """`closed_by` is the only thing separating a deficiency a human answered
    from one nothing has, and `brief.py` renders that distinction at gate 0.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="triage-seal")
    doc = read_json(run.triage)
    doc["deficiencies"] = [
        {"deficiency_id": "def-open", "statement": "nothing answers this"},
        {
            "deficiency_id": "def-shut",
            "statement": "a human answered this",
            "closed_by": "proj-1",
        },
    ]
    doc["projections"] = [
        {
            "projection_id": "proj-1",
            "closes": ["def-shut"],
            "wanted": {"statement": "a digest of the missing surface"},
        }
    ]
    write_json(run.triage, doc)
    html = summary.run_summary(run)
    assert "closed by proj-1" in html
    assert "<b>OPEN</b>" in html
    assert "proj-1: a digest of the missing surface" in html


def test_render_tabulates_the_world_model_counts_and_denominator(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    got = summary.world_model(run)
    html = summary.run_summary(run)
    for kind, count in got.counts.items():
        assert f'<tr><td>{kind}</td><td class="num">{count}</td></tr>' in html
    for key, value in got.denominator.items():
        assert f"<tr><td>{key}</td><td>{value}</td></tr>" in html


def test_render_reports_the_utilisation_percentage_and_both_columns(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    got = summary.utilisation(run)
    html = summary.run_summary(run)
    assert f"{got.cited} of {got.total} claims cited" in html
    assert f"{got.pct:.1f}%" in html
    for row in got.per_artifact:
        # Three cells as one string, not the `cited` cell alone: `cited == total`
        # for two of this fixture's three rows (notes-md 8/8, trace-json 2/2), so
        # the adjacent `total` column satisfied a lone `cited` assertion --
        # measured green with the cited cell mutated to `_val(-1)`. api-json is
        # 9/10 since the `tool` claim nothing cites yet, so it alone would now
        # catch that; the other two still would not, which is why the three-cell
        # form stays. The same adjacent-identical-column trap
        # test_render_names_every_round_with_its_verdict_and_cells already records.
        assert (
            f'<td class="mono">{row["artifact_id"]}</td>'
            f'<td class="num">{row["cited"]}</td>'
            f'<td class="num">{row["total"]}</td>' in html
        )


def test_render_prints_the_pre_seal_utilisation_absence_verbatim(tmp_path):
    """`Utilisation` is `Absent` for two distinct reasons, and the page prints
    `Absent.what` rather than one fixed line: "the seal has not run" and
    "something in the run could not be read" are different facts.
    """
    run = build_toy_run(tmp_path / "runs", upto="extract")
    assert "Not present: claim utilisation (no world model yet)" in summary.run_summary(run)


def test_render_states_the_unreadable_utilisation_as_a_malformation(tmp_path):
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    # `"claims": 7` is one of the hand-edited `01-claims/` shapes measured escaping
    # `claim_utilisation` as an exception -- TypeError, not an OSError.
    write_json(run.claims_dir / "broken.json", {"schema_version": "0.1", "claims": 7})
    html = summary.run_summary(run)
    # "Present but unreadable", not "Not present": `01-claims/` is on disk and the
    # spine says `extract` produced it, so an absence line here is the page
    # contradicting its own first section.
    assert (
        "Present but unreadable: claim utilisation "
        "(01-claims/ or 01-world-model.json unreadable)" in html
    )
    assert "Not present: claim utilisation" not in html


def test_render_reports_each_gap_with_the_stages_it_blocks(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.world_model)
    doc["gaps"] = [
        {
            "id": "gap-1",
            "subject": "the refund path",
            "blocks": ["propose", "instantiate"],
            "unknown": "which queue a refund lands in",
            "why_it_matters": "no scenario can assert the queue",
        }
    ]
    write_json(run.world_model, doc)
    html = summary.run_summary(run)
    assert "gap-1" in html
    assert "propose, instantiate" in html
    assert "which queue a refund lands in" in html


def test_render_tallies_the_contradictions_by_resolution(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    got = summary.contradictions(run)
    html = summary.run_summary(run)
    assert f"{got.total} contradiction(s)" in html
    assert f"{got.parts_swept} subject part(s)" in html
    for key, count in got.by_resolution.items():
        assert f'<tr><td>{key}</td><td class="num">{count}</td></tr>' in html


def test_render_marks_each_matrix_cell_covered_or_not(tmp_path):
    """Both classes, because a matrix drawn all-yes reads as a converged run.

    The toy fixture covers all four cells, so one is turned off here: a test over
    the unedited fixture cannot tell a renderer that emits `cell yes`
    unconditionally from one that reads `covered`.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    latest = read_json(run.coverage_latest)
    latest["capability_matrix"]["cells"][1]["covered"] = False
    latest["capability_matrix"]["cells"][1]["scenario_ids"] = []
    write_json(run.coverage_latest, latest)
    html = summary.run_summary(run)
    assert 'class="cell yes"' in html
    assert 'class="cell no"' in html
    # Sorted, and carrying the folded claimant: rounds.capability_matrix lists
    # every scenario claiming the cell and leaves the live/dead distinction to
    # `covered` alone, per rb-score's Method step 4.
    assert 'title="scn-blocked, scn-open, scn-open-dup"' in html


def _goal_states(run):
    """The toy's goal matrix rewritten to hold all four cell states, and the page.

    Every state has to be manufactured, because the fixture cannot reach them: the
    toy converges with two goals each covered at their single expected depth, so an
    unedited run draws one `yes` per row and nothing else -- a renderer emitting
    `cell yes` unconditionally passes over it. Written once and shared, because the
    three tests below assert on the same four states from different angles and
    three copies of this setup would be three chances for them to drift apart.

    The resulting union of depths is `{1, 2, 3}`:

    | goal | 1 | 2 | 3 |
    |---|---|---|---|
    | `goal-locate` | covered | not expected | not expected |
    | `goal-explain` | not expected | expected, unreached | reached, unexpected |
    """
    from rubrica.artifacts import read_json, write_json

    latest = read_json(run.coverage_latest)
    rows = latest["goal_matrix"]["rows"]
    rows[1]["covered"] = False
    rows[1]["hop_depths_expected"] = [2]
    rows[1]["hop_depths_present"] = [3]
    write_json(run.coverage_latest, latest)
    return summary.run_summary(run)


def test_render_draws_a_goal_matrix_column_per_hop_depth_in_either_list(tmp_path):
    """The columns are the union of expected and present, not just expected.

    A depth reached but not expected is the one state that has no column if the
    header is built from `hop_depths_expected` alone -- and it is the state the
    matrix is most worth drawing for, so the union is the property asserted rather
    than the column count. Depth 3 below appears in no `hop_depths_expected` on the
    page.

    Sorted ascending, which `test_render_is_byte_identical_across_two_calls` needs
    a *stable* order for and a reader needs an *ascending* one for: hop depth is a
    magnitude, and `hop 3` left of `hop 1` reads as a rendering bug.
    """
    html = _goal_states(build_toy_run(tmp_path / "runs", upto="challenge"))
    # Read off the header rather than substring-matched, so the assertion is over
    # the columns and their order and not over the `class` the heading carries: a
    # pinned attribute here would break on a styling change that draws exactly the
    # same three columns.
    head = re.search(r"<thead><tr><th>goal</th>(.*?)</tr></thead>", html)
    assert head, "the goal matrix draws a header row"
    assert re.findall(r">hop (\d+)<", head.group(1)) == ["1", "2", "3"]
    assert "Goal matrix (2 goals" in html


def test_render_draws_the_four_goal_cell_states_apart(tmp_path):
    """Covered, open, unexpected and not-applicable are four renderings, not two.

    The capability matrix has two states because a cell either is or is not
    covered. A goal-by-depth grid has two more, and collapsing either of them
    loses a fact: an unexpected depth folded into `covered` claims a goal was
    reached as designed, and folded into `not covered` it disappears entirely,
    while a depth the goal never expected is not an open slot and must not be
    counted by eye as one.
    """
    html = _goal_states(build_toy_run(tmp_path / "runs", upto="challenge"))
    for state in ("yes", "no", "off", "na"):
        assert f'class="gcell {state}"' in html, f"the {state} state is drawn"


def test_render_states_each_goal_cell_in_words_not_colour_alone(tmp_path):
    """Every state says what it is in text, per the page's existing colour rule.

    The rule is `_CSS`' own, written at `.hole-reason`: weight and a rule carry a
    distinction, never colour alone. A four-state grid is where that is easiest to
    break, because four tints are cheaper to emit than four titles -- so each cell
    carries its meaning on the title and the legend spells the marks out. Asserted
    against the *titles*, since a legend alone leaves a reader counting cells
    against a key.
    """
    html = _goal_states(build_toy_run(tmp_path / "runs", upto="challenge"))
    for phrase in (
        "covered at hop depth 1",
        "expected at hop depth 2, no scenario reached it",
        "a scenario reached hop depth 3, which this goal does not expect",
        "not expected at hop depth 2",
    ):
        assert f'title="{phrase}"' in html, phrase


def test_render_names_the_scenarios_covering_a_goal(tmp_path):
    """The first column carries the goal and its scenarios, as the cell matrix does.

    `goal_matrix` records `scenario_ids` per *goal*, never per depth -- which is
    why they belong to the row rather than to a cell, and why no cell title may
    claim a particular scenario reached a particular depth. The document does not
    say that.
    """
    html = _goal_states(build_toy_run(tmp_path / "runs", upto="challenge"))
    # Sorted by rounds.goal_matrix, which fixes an order the document itself does
    # not specify so two runs with identical parts produce identical bytes.
    assert 'title="scn-empty, scn-missing, scn-open"' in html


def test_render_says_so_when_latest_carries_no_goal_row(tmp_path):
    """An empty `rows` renders a sentence, not an empty table.

    The sibling of the capability matrix's absence line, and the state a run whose
    world model has no goal at all ends in. A bare `<table>` with a header and no
    body reads as a rendering failure rather than as a run with nothing to draw.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    latest = read_json(run.coverage_latest)
    latest["goal_matrix"]["rows"] = []
    write_json(run.coverage_latest, latest)
    html = summary.run_summary(run)
    assert "latest.json carries no goal row" in html
    assert "Goal matrix (0 goals" in html


def test_render_labels_the_round_hole_count_apart_from_the_terminal_holes(tmp_path):
    """`RoundRow.holes` and `Coverage.holes` come from different documents by
    design and can differ without either being wrong, so the page must not let a
    reader take the difference for an arithmetic error.
    """
    html = summary.run_summary(build_toy_run(tmp_path / "runs", upto="challenge"))
    # Pinned as the column header, not as a substring: the note under the table
    # explains the same distinction in prose, so a bare `"holes that round" in
    # html` survives the column itself being relabelled "holes".
    assert '<th class="num">holes that round</th>' in html
    assert "Open holes at the last round" in html


def test_render_reports_the_implied_suite_size(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    got = summary.coverage(run)
    html = summary.run_summary(run)
    assert f"implies {got.implied['implied']} scenario(s)" in html
    assert f"ceiling {got.implied['ceiling']}" in html
    assert got.implied["basis"] in html


def test_render_says_the_implied_size_was_not_computed_when_it_could_not_be(tmp_path):
    """`implied is None` merges three facts, so the page states one honest line
    rather than guessing which of the three it was.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.manifest)
    # The measured shape: `implied > ceiling` raises TypeError on a non-numeric
    # ceiling, below sizing.py's own handler.
    doc["limits"]["max_scenarios"] = "eight"
    write_json(run.manifest, doc)
    html = summary.run_summary(run)
    assert "Implied suite size not computed" in html
    assert "implies" not in html.split("Implied suite size not computed")[1]


def test_render_names_every_round_with_its_verdict_and_cells(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    got = summary.coverage(run)
    html = summary.run_summary(run)
    assert f"Coverage ended <b>{got.terminal_verdict}</b>" in html
    for row in got.rounds:
        # The two cells asserted as an adjacent pair, not one at a time. Measured:
        # the toy run has covered == total == 4, so dropping the numeric class from
        # the covered cell left a lone `<td class="num">4</td>` assertion green
        # against the *total* cell -- the fixture-cannot-reach shape.
        assert (
            f'<td class="num">{row.cells_covered}</td><td class="num">{row.cells_total}</td>'
            in html
        )


def test_render_names_every_scenario_with_its_verdict_and_package_state(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    html = summary.run_summary(run)
    rows = summary.scenarios(run)
    assert len(rows) == 5
    for row in rows:
        assert row.title in html
        assert row.id_ in html
    # The folded duplicate has no verdict and no instance, and the row still
    # renders: a table that dropped it would hide the one scenario score folded.
    assert "scn-open-dup" in html
    assert '<span class="absent">no package</span>' in html


def test_render_puts_the_discriminating_fact_in_a_title_and_not_a_column(tmp_path):
    """Long prose on a title attribute is what keeps a 128-row table scannable."""
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    rows = summary.scenarios(run)
    fact = next(r.discriminating_fact for r in rows if r.discriminating_fact)
    html = summary.run_summary(run)
    assert f'title="{fact}"' in html
    assert f">{fact}<" not in html, "the fact became a column and widened every row"


def test_render_shows_an_uncoerced_hop_depth_verbatim(tmp_path):
    """`ScenarioRow.hop_depth` is `object`: a hand-edited `"two"` renders as
    "two", because a `0` beside a readable file reads as a rendering bug rather
    than as the propose-stage defect it is.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.scenarios)
    doc["scenarios"][0]["hop_depth"] = "two"
    write_json(run.scenarios, doc)
    html = summary.run_summary(run)
    assert ">two</td>" in html


def test_render_marks_an_overstated_difficulty_on_the_row(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    verdict = read_json(run.verdict("scn-blocked"))
    verdict["minimum_tool_calls_found"] = 1
    write_json(run.verdict("scn-blocked"), verdict)
    html = summary.run_summary(run)
    assert "1 (overstated)" in html


def test_render_tallies_the_verdicts_and_counts_the_packages(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    got = summary.challenge(run)
    html = summary.run_summary(run)
    assert f"{got.judged} scenario(s) judged" in html
    assert f"{got.packages} package(s)" in html
    for key, count in got.tallies.items():
        assert f'<tr><td>{key}</td><td class="num">{count}</td></tr>' in html


def test_render_states_the_challenge_absence_as_the_stage_not_having_run(tmp_path):
    """A run short of `challenge` has no verdicts, which is an absence and not a defect.

    The unreadable-directory half is `test_challenge_on_an_unreadable_verdicts_dir
    _is_malformed_not_absent`; this is the control that keeps the two apart on the
    page, since "05-verdicts/ could not be listed" about a run that never reached
    the stage would invent a defect.
    """
    run = build_toy_run(tmp_path / "runs", upto="score-seal")
    html = summary.run_summary(run)
    assert "Not present: 05-verdicts/" in html
    assert "Present but unreadable: 05-verdicts/" not in html
    assert "scenario(s) judged" not in html


def test_render_states_every_flag_with_its_threshold(tmp_path, monkeypatch):
    """A flag whose rule is not on the page is a black box a reader cannot argue
    with. Task 7's review measured that a renderer dropping the threshold column
    would still pass every test in Task 7, so the assertion lives here.
    """
    run = _run_with_every_flag(tmp_path, monkeypatch)
    html = summary.run_summary(run)
    fired = summary.flags(run)
    assert len(fired) == 7
    for flag in fired:
        # Through `esc`, not raw: `difficulty-overstated`'s threshold is
        # "minimum_tool_calls_found < hop_depth", so the page carries it with the
        # `<` escaped -- and a test comparing the raw string would push a
        # renderer towards *not* escaping the one flag whose rule contains markup.
        assert summary.esc(flag.headline) in html, f"{flag.id_} has no headline on the page"
        assert summary.esc(flag.threshold) in html, f"{flag.id_} reached the page without its rule"
        assert summary.esc(flag.detail) in html, f"{flag.id_} has no detail on the page"


def test_render_says_no_flags_fired_rather_than_leaving_the_section_empty(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.manifest)
    # stage-record-incomplete is the one flag an unedited toy run fires, because
    # build_toy_run mints an empty manifest.stages.
    doc["stages"] = {
        name: {"model": "m", "effort": "high", "skill_sha256": "0" * 64}
        for name in (
            "extract",
            "reconcile-subjects",
            "reconcile-contradict",
            "reconcile-capabilities",
            "reconcile-outcomes",
            "reconcile-entities",
            "reconcile-goals",
            "reconcile-gaps",
            "propose",
            "score",
            "instantiate",
            "challenge",
        )
    }
    write_json(run.manifest, doc)
    assert summary.flags(run) == []
    assert "No flags fired." in summary.run_summary(run)


def test_render_escapes_a_verdict_note_reaching_a_title_attribute(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    verdict = read_json(run.verdict("scn-open"))
    verdict["notes"] = 'the agent said "no" & stopped'
    write_json(run.verdict("scn-open"), verdict)
    html = summary.run_summary(run)
    assert 'title="the agent said &quot;no&quot; &amp; stopped"' in html


def test_render_escapes_an_unsafe_scenario_id(tmp_path):
    """A scenario id is a value like any other and goes through `esc`.

    The id cell, not the `href`, and that is a measured limit rather than a
    weaker claim than intended: an id carrying a `"` fails `is_safe_segment`, so
    `summary.scenarios` joins no verdict for it, so it renders unlinked and the
    `href` branch is unreachable for every shape that could break an attribute.
    Asserting on the href here would have been the fixture-cannot-reach shape --
    measured, an unescaped `href` survived it. The `esc` in the href stays as
    defence in depth against a future id grammar, unpinned and said so.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.scenarios)
    doc["scenarios"][0]["id"] = 'x" onmouseover="alert(1)'
    write_json(run.scenarios, doc)
    html = summary.run_summary(run)
    assert 'x" onmouseover="alert(1)' not in html
    assert "onmouseover=&quot;alert(1)" in html


def test_render_does_not_raise_on_an_unreadable_run_root(tmp_path):
    """The module's one absolute promise, at the renderer."""
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path / "runs")
    run.root.chmod(0o000)
    try:
        html = summary.run_summary(run)
    finally:
        run.root.chmod(0o755)
    assert html.startswith("<!doctype html>")
    assert "Not present: manifest.json" in html


def test_render_is_byte_identical_across_two_calls(tmp_path):
    """A page a reader diffs against yesterday's must not reshuffle on its own.

    `dict` iteration and `list_json`'s sort are the two places an unstable order
    would come from, and both are settled in `summary.py` -- this is the lock at
    the rendering boundary.
    """
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    assert summary.run_summary(run) == summary.run_summary(run)


# --------------------------------------------- fix round 1: four render items ---


def test_render_formats_a_float_pct_without_the_float_noise(tmp_path):
    """A float pct is formatted for display, which is not coercion.

    Measured on run-20260825-094033: 19 of 148 cells rendered as
    `0.12837837837837837`, seventeen digits in a cell nobody reads past the
    second. Three places, not one, because the field is a fraction in every
    coverage document on disk -- `:.1f` would render 11-of-20 cells as `0.6`.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.coverage_round(1))
    doc["capability_matrix"]["pct"] = 0.12837837837837837
    write_json(run.coverage_round(1), doc)
    html = summary.run_summary(run)
    assert '<td class="num">0.128</td>' in html
    assert "0.12837837837837837" not in html


def test_render_renders_a_non_float_pct_verbatim(tmp_path):
    """The other direction, and the one Task 5's ruling protects: a pct that is
    not a float is a score-stage defect for `validate` to name, and rendering
    `0.0` in its place would hide it.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.coverage_round(1))
    doc["capability_matrix"]["pct"] = "half"
    write_json(run.coverage_round(1), doc)
    html = summary.run_summary(run)
    assert '<td class="num">half</td>' in html


def _run_with_two_hole_kinds(tmp_path):
    """A run whose terminal holes carry one closed reason and two open ones.

    The toy world converges with no hole at all, so the distinction under test is
    unreachable on the unedited fixture -- and a test that cannot reach the
    condition it names is the fixture-cannot-reach shape this module has already
    been bitten by once.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    latest = read_json(run.coverage_latest)
    latest["holes"] = [
        {
            "ref": "cell:cap-find-tickets/oc-none",
            "reason": "unreachable",
            "justification": "the tool cannot return an empty set for this capability",
        },
        {
            "ref": "cell:cap-get-ticket/oc-detail",
            "reason": "blocked_by_gap",
            "justification": "no claim says what the tool returns for a missing ticket",
        },
        {
            "ref": "cell:cap-get-ticket/oc-missing",
            "reason": "not_yet_attempted",
            "justification": "round 1 proposed nothing for this cell",
        },
    ]
    write_json(run.coverage_latest, latest)
    return run


def test_render_distinguishes_an_unreachable_hole_from_an_open_one(tmp_path):
    """Spec 3.4: an `unreachable` hole is a closed question, the others open ones.

    Both halves are asserted, because a renderer that marked every hole closed --
    or every hole open -- would satisfy a test looking for one class alone, and
    the whole point is that a reader counting open holes does not count the closed
    ones with them.
    """
    html = summary.run_summary(_run_with_two_hole_kinds(tmp_path))
    assert '<td class="hole-reason closed">unreachable ' in html
    assert '<td class="hole-reason open">blocked_by_gap ' in html
    assert '<td class="hole-reason open">not_yet_attempted ' in html
    # In words as well as in a class: a distinction carried only by a colour is
    # one a colour-blind reader, a printed page and a text dump all lose.
    assert html.count("(closed question)") == 1
    assert html.count("(open question)") == 2


def test_render_marks_a_clipped_gap_rationale(tmp_path):
    """A sentence cut at 120 characters reads as a complete one unless it is marked.

    The full text stays on the cell's `title`; the ellipsis is what tells a reader
    there is more to hover for.
    """
    from rubrica.artifacts import read_json, write_json

    long_why = "the queue a refund lands in is unrecorded, " + "and " * 40 + "nobody knows"
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.world_model)
    doc["gaps"] = [
        {
            "id": "gap-long",
            "subject": "refunds",
            "blocks": ["propose"],
            "unknown": "the queue",
            "why_it_matters": long_why,
        }
    ]
    write_json(run.world_model, doc)
    html = summary.run_summary(run)
    assert "&hellip;" in html, "the clipped cell carries no mark"
    assert long_why[:100] in html
    assert f'title="{long_why}"' in html, "the full text is still one hover away"


def test_render_does_not_mark_a_gap_rationale_that_fits(tmp_path):
    """The other direction: nothing shorter than the clip width gains an ellipsis.

    Measured against the whole page rather than the one cell, which is what makes
    it a lock: `_clipped` is used by exactly two columns, and on this run one of
    them is absent, so a mark anywhere means an unclipped value was marked.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.world_model)
    doc["gaps"] = [
        {
            "id": "gap-short",
            "subject": "refunds",
            "blocks": ["propose"],
            "unknown": "the queue",
            "why_it_matters": "no scenario can assert the queue",
        }
    ]
    write_json(run.world_model, doc)
    html = summary.run_summary(run)
    assert "no scenario can assert the queue" in html
    assert "&hellip;" not in html


def test_render_marks_a_clipped_disposition_reason(tmp_path):
    """The second of the two columns that clip, pinned separately.

    One test over one call site cannot tell a renderer that marks both from one
    that marks the column the test happened to pick -- and a disposition's
    `reason` is a paragraph in every real run, so this is the site a reader meets
    first.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="triage-seal")
    doc = read_json(run.triage)
    long_reason = "admitted because " + "it carries the golden world's shape and " * 6
    doc["dispositions"][0]["reason"] = long_reason
    write_json(run.triage, doc)
    html = summary.run_summary(run)
    assert "&hellip;" in html
    assert f'title="{summary.esc(long_reason)}"' in html


def test_summary_html_reads_exactly_one_artifact_and_names_it():
    """`decisions.md` is the module's one read, and the docstring says so.

    A structural guard rather than a phrase pin: it counts the reads in the source
    and requires the docstring to name the artifact. The module docstring claimed
    "nothing here reads an artifact" while `_decisions` read one, and a comment
    that has drifted from the code is worse than no comment -- so the sentence and
    the count are asserted together, and a second read added here fails the suite
    rather than quietly making the prose wrong.
    """
    from pathlib import Path

    from rubrica import summary_html

    source = Path(summary_html.__file__).read_text(encoding="utf-8")
    reads = [
        line.strip()
        for line in source.splitlines()
        if ".read_text(" in line or "read_json(" in line or "list_json(" in line
    ]
    assert reads == ['text = run.decisions.read_text(encoding="utf-8")'], reads
    assert "decisions.md" in summary_html.__doc__


# The six CLI tests below are strengthened past the shapes that were *measured*
# satisfiable by a wrong wiring. Each mutation and its result:
#
#   deleting `destination.write_text(...)`  -- the command writes nothing, still
#     exits 0 and still prints a path -- left the two "exits clean" tests green,
#     because a bare `code == 0` says nothing about a file. Both now read the
#     page back.
#   `print("run-summary.html")` instead of the destination left the path test
#     green, because the substring is present whether or not the printed path is
#     the one written. It now pins the exact line.
#   writing to *both* the explicit `-o` path and the default left the -o test
#     green, because `out.exists()` cannot see the extra file. It now pins the
#     default's absence.
#   and the exit-2 test passed before `run-summary` was a subcommand at all, on
#     argparse's SystemExit(2) path. It now pins the message `_run_dir` produces.


def test_cli_writes_the_page_into_the_run_by_default(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    code = cli.main(["run-summary", "--run", str(run.root)])
    assert code == 0
    written = run.root / "run-summary.html"
    assert written.exists()
    text = written.read_text(encoding="utf-8")
    assert text.startswith("<!doctype html>")
    # The whole page and nothing else: run_summary is a pure function of the run
    # directory, so equality here catches a wiring that renders a stub, truncates
    # the write, or hands the renderer some other path.
    assert text == summary.run_summary(run)


def test_cli_prints_the_path_it_wrote(tmp_path, capsys):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    capsys.readouterr()  # drop whatever the fixture build wrote
    cli.main(["run-summary", "--run", str(run.root)])
    assert capsys.readouterr().out == f"{run.root / 'run-summary.html'}\n"


def test_cli_honours_an_explicit_output_path(tmp_path, capsys):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    out = tmp_path / "elsewhere" / "page.html"
    out.parent.mkdir()
    capsys.readouterr()  # drop whatever the fixture build wrote
    assert cli.main(["run-summary", "--run", str(run.root), "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")
    # The printed path follows -o. Pinned here as well as in the default case,
    # because printing the default unconditionally is invisible to every other
    # assertion: printing a path creates no file for them to see.
    assert capsys.readouterr().out == f"{out}\n"
    # -o redirects rather than adds. The flag exists for a read-only run
    # directory, so writing there anyway would defeat its only purpose.
    assert not (run.root / "run-summary.html").exists()


def test_cli_exits_clean_on_a_run_that_stopped_early(tmp_path):
    """A report is never a gate: the 10-of-11 partial case must exit 0.

    And it must exit 0 having written a page that *states* the absences, which is
    the behaviour cli.md promises for this case -- not merely an exit code.
    """
    run = build_toy_run(tmp_path / "runs", upto="extract")
    assert cli.main(["run-summary", "--run", str(run.root)]) == 0
    page = (run.root / "run-summary.html").read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>")
    assert page.endswith("</body></html>")
    assert "Not present: 01-world-model.json" in page


def test_cli_exits_clean_on_an_almost_empty_run(tmp_path):
    empty = tmp_path / "run-empty"
    empty.mkdir()
    assert cli.main(["run-summary", "--run", str(empty)]) == 0
    page = (empty / "run-summary.html").read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>")
    assert page.endswith("</body></html>")
    # Not even a manifest, and still a whole page: every section is present and
    # says what it looked for.
    assert "Not present: manifest.json" in page


def test_cli_exits_two_on_a_missing_run_directory(tmp_path, capsys):
    missing = tmp_path / "nope"
    assert cli.main(["run-summary", "--run", str(missing)]) == 2
    # The 2 has to come from _run_dir's check rather than from argparse rejecting
    # an unknown subcommand: measured, this assertion on the exit code alone
    # passed before `run-summary` was wired at all.
    assert f"run directory does not exist: {missing}" in capsys.readouterr().err


# ------------------------------------ fix round 2: the text-encoding hazards ---
#
# Every hazard the nine tasks hardened was a JSON *shape* -- `Infinity`, `"nope"`,
# `../../etc`, `chmod 000` -- and not one was a text *encoding*. That is why C1 and
# C2 survived nine scoped reviews: `grep -E 'UnicodeDecode|UnicodeEncode|surrogate'`
# over this file returned nothing across 4,306 lines, and every fixture wrote its
# artifacts with `encoding="utf-8"`, which is the one input that cannot reproduce
# either defect. The fixtures below write **bytes**.
#
# Both defects made a *report* exit 1, which is the contract violation rather than
# the crash: CLAUDE.md's exit-code table reserves 1 for a repairable stage defect
# with a finding per line, and the `[internal]` finding both produced advised
# `rubrica validate --stage <stage>` -- unactionable for `decisions.md`, which has
# no schema, and misleading for the surrogate, since the page had already rendered
# completely and correctly. So each is driven end to end through `cli.main` and the
# assertion is on the exit code, not merely on nothing being raised.


def test_cli_exits_clean_on_a_decisions_md_that_is_not_utf_8(tmp_path, capsys):
    """C1: `UnicodeDecodeError` is a `ValueError`, so `except OSError` never saw it.

    Measured before the fix: exit **1**, a traceback on stderr, and
    `[internal] <run>: run-summary raised UnicodeDecodeError ... run `rubrica
    validate --stage <stage>`` on stdout. After: exit 0, and the section says the
    file is there and unreadable rather than absent.
    """
    run = build_toy_run(tmp_path / "runs", upto="intake")
    # A lone continuation byte: latin-1 prose is how a real `decisions.md` acquires
    # one, since `decide` appends whatever a human or an orchestrator hands it.
    run.decisions.write_bytes(b"Some prose with a latin-1 byte: \xe9tape\n")
    capsys.readouterr()
    assert cli.main(["run-summary", "--run", str(run.root)]) == 0
    assert capsys.readouterr().out == f"{run.root / 'run-summary.html'}\n"
    page = (run.root / "run-summary.html").read_text(encoding="utf-8")
    assert "Present but unreadable: decisions.md" in page
    assert "not UTF-8 text" in page
    # Not the absence line: the file is on disk, and saying it is not there is the
    # spine-versus-section contradiction `Malformed` exists to prevent.
    assert "Not present: decisions.md" not in page


def test_decisions_that_is_not_utf_8_is_malformed_rather_than_absent(tmp_path):
    """The builder half of the test above, at the marker rather than the page."""
    from rubrica import summary_html

    run = build_toy_run(tmp_path / "runs", upto="intake")
    run.decisions.write_bytes(b"\xff\xfe not text at all\n")
    got = summary_html._decisions(run)
    assert isinstance(got, summary.Malformed)
    assert got.what == "decisions.md"


def test_cli_exits_clean_on_a_lone_surrogate_in_an_artifact(tmp_path, capsys):
    """C2(a): the reachable source, and the one that must have a test.

    `json.loads('"\\udcff"')` returns the lone surrogate `'\\udcff'` -- accepted by
    default exactly as `Infinity` is, which is the token class this module already
    guards against in `_as_int`. It flows manifest -> `inputs` -> `InputRow
    .stored_as` -> the `stored as` cell. `html.escape` does not touch surrogates
    and `write_text(encoding="utf-8")` cannot encode one, so before the fix this
    was exit **1** with a `UnicodeEncodeError` -- *after* the page had rendered
    completely and correctly, which is why nothing inside the rendering module
    could see it.
    """
    run = build_toy_run(tmp_path / "runs", upto="intake")
    manifest = json.loads(run.manifest.read_text(encoding="utf-8"))
    manifest["inputs"][0]["stored_as"] = json.loads('"\\udcff"')
    assert len(manifest["inputs"][0]["stored_as"]) == 1, "one code point, not six characters"
    # `surrogatepass`, because writing this document is exactly what a plain UTF-8
    # write cannot do -- which is the defect, one layer up.
    run.manifest.write_bytes(json.dumps(manifest).encode("utf-8", "surrogatepass"))
    capsys.readouterr()
    assert cli.main(["run-summary", "--run", str(run.root)]) == 0
    page = (run.root / "run-summary.html").read_text(encoding="utf-8")
    # Rendered as the escape `os.fsdecode` would have produced, not dropped and not
    # turned into a `?`: which byte it was is the only actionable thing about it.
    assert r"\udcff" in page


def test_cli_exits_clean_on_a_stray_temp_file_whose_name_is_not_utf_8(tmp_path):
    """C2(b): `run.root.iterdir()` surrogate-escapes a non-UTF-8 filename.

    The name reaches the page through the `orphaned-temp` flag's `detail`, so this
    is a second, independent route to the same `UnicodeEncodeError` -- and the
    reason the fix is one decision in `esc` rather than three at three sources.
    """
    run = build_toy_run(tmp_path / "runs", upto="intake")
    (run.root / os.fsdecode(b"x.json.tmp.1.\xff\xfe")).write_bytes(b"{}")
    assert cli.main(["run-summary", "--run", str(run.root)]) == 0
    page = (run.root / "run-summary.html").read_text(encoding="utf-8")
    assert "orphaned temp file(s)" in page, "the flag is what carries the name onto the page"


def test_cli_exits_clean_on_a_run_directory_whose_name_is_not_utf_8(tmp_path):
    """C2(c): `run.root.name` is interpolated into the `<title>` and the `<h1>`.

    An *otherwise empty* directory, which is what makes this the third independent
    source: no artifact, no stray file, and the page still could not be written.
    """
    root = tmp_path / os.fsdecode(b"run-\xff\xfe")
    root.mkdir()
    assert cli.main(["run-summary", "--run", str(root)]) == 0
    page = (root / "run-summary.html").read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>")
    assert page.endswith("</body></html>")


def test_esc_turns_a_lone_surrogate_into_text_and_leaves_real_text_alone(tmp_path):
    """The single decision, at the one function that makes it.

    Both directions: the surrogate becomes six characters a reader can recognise,
    and text that was already text is untouched -- including the non-ASCII prose
    and the markup characters `esc` exists to escape, which an over-broad
    sanitiser would have mangled.
    """
    assert summary.esc("\udcff") == r"\udcff"
    assert summary.esc("x\udcffy") == r"x\udcffy"
    assert summary.esc("émile — ok") == "émile — ok"
    assert summary.esc('<b>"a"</b>') == "&lt;b&gt;&quot;a&quot;&lt;/b&gt;"
    # The whole point: whatever comes back can be written as UTF-8.
    summary.esc("\udcff").encode("utf-8")


# ---------------------------------- fix round 2: malformed content exits clean ---
#
# Measured by Task 9's reviewer and never committed. Each is a *readable* run whose
# manifest cannot be read as an artifact, which is the class this module promises to
# render rather than raise on -- and the class the exit-code contract reserves 1 for
# only when a stage produced it and a repair could fix it.


def test_cli_exits_clean_on_a_garbage_json_manifest(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="intake")
    run.manifest.write_text("{not json", encoding="utf-8")
    assert cli.main(["run-summary", "--run", str(run.root)]) == 0
    page = (run.root / "run-summary.html").read_text(encoding="utf-8")
    assert "Present but unreadable: manifest.json" in page


def test_cli_exits_clean_on_a_manifest_that_is_a_json_list(tmp_path):
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    write_json(run.manifest, ["not", "a", "manifest"])
    assert cli.main(["run-summary", "--run", str(run.root)]) == 0
    page = (run.root / "run-summary.html").read_text(encoding="utf-8")
    assert "Present but unreadable: manifest.json" in page


def test_cli_exits_clean_on_an_unreadable_manifest_in_a_readable_run(tmp_path):
    """`chmod 000` on the manifest alone -- the run root, and every other artifact,
    stays readable. An OSError on one artifact inside a readable run is not the
    harness pointed at something it cannot read, so it is not exit 2 either.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path / "runs", upto="intake")
    run.manifest.chmod(0o000)
    try:
        assert cli.main(["run-summary", "--run", str(run.root)]) == 0
        page = (run.root / "run-summary.html").read_text(encoding="utf-8")
        assert "Present but unreadable: manifest.json" in page
    finally:
        run.manifest.chmod(0o644)


# ------------------------------- fix round 2: the rest of the review's findings ---


def test_render_agrees_with_its_own_spine_about_a_present_unreadable_artifact(tmp_path):
    """I5, on the run the disagreement was measured on.

    A valid manifest, `02-scenarios.json` holding `[]`, and a garbage
    `latest.json`: the spine bolds `propose` and `score` because both artifacts
    exist, while both sections found nothing to read. Rendered as absences, the one
    page said "3 of 22 stages produced an artifact" *and* that neither artifact was
    present -- the spine testing existence, the sections testing parseability, and
    nothing reconciling them.
    """
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
    write_json(run.scenarios, [])
    for path in run.coverage_dir.iterdir():
        path.unlink()
    run.coverage_latest.write_text("{not json", encoding="utf-8")
    html = summary.run_summary(run)
    assert '<li class="yes">propose</li>' in html
    assert '<li class="yes">score</li>' in html
    assert "Present but unreadable: 02-scenarios.json" in html
    assert "Present but unreadable: 03-coverage/" in html
    assert "Not present: 02-scenarios.json" not in html
    assert "Not present: 03-coverage/" not in html
    # And the spine says which test it made, so a reader does not take the two for
    # a contradiction.
    assert "Produced means the stage's artifact exists" in html


def test_render_spells_a_json_boolean_as_yes_or_no(tmp_path):
    """M10: 35 cells read `True` and one read `False` -- Python's spelling, on a page
    about a run rather than about the program reading it, and one column away from
    the scenario table's `instance` cell, which already read `yes`.

    Both spellings are asserted gone and both replacements asserted present, since
    a `_val` that mapped every boolean to `yes` would satisfy half of this.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    html = summary.run_summary(run)
    # The verdict columns are where the 35 `True` cells were: every verdict on this
    # fixture carries `uniquely_determined` and `derivable_without_guessing`.
    assert "<td>yes</td>" in html
    assert ">True<" not in html
    assert ">False<" not in html
    # The other direction, so a `_val` mapping every boolean to `yes` cannot pass.
    doc = read_json(run.verdict("scn-open"))
    doc["uniquely_determined"] = False
    write_json(run.verdict("scn-open"), doc)
    flipped = summary.run_summary(run)
    assert "<td>no</td>" in flipped
    assert ">False<" not in flipped
    # And the one boolean rendered outside a table cell, on a run that has an
    # objective verdict to render: `Supported:</b> True` was the reading before.
    triaged = build_toy_run(tmp_path / "runs2", upto="triage-seal")
    assert "<b>Supported:</b> yes" in summary.run_summary(triaged)


def test_render_heads_the_holes_column_ref_because_a_hole_can_name_a_goal(tmp_path):
    """I4: 22 of 151 holes on `run-20260825-094033` were `goal:goal-...` refs.

    Headed `cell` beside a `Capability matrix (148 cells)` heading, `151 holes`
    read as an arithmetic error -- and the caveat the page already carried is about
    a different discrepancy (per-round holes against `latest.json`'s), so it
    misdirected the reader who checked. The header was wrong; the numbers were not.
    """
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score-seal")
    doc = read_json(run.coverage_latest)
    doc["holes"] = [
        {"ref": "cell:cap-a/oc-x", "reason": "unreachable", "justification": "no mapping"},
        {"ref": "goal:goal-refund", "reason": "no_evidence", "justification": "no trace"},
    ]
    write_json(run.coverage_latest, doc)
    html = summary.run_summary(run)
    assert "<th>ref (cell or goal)</th>" in html
    assert "<th>cell</th>" not in html
    assert "goal:goal-refund" in html
    # The heading count and the matrix count are over different sets, and the page
    # has to say so where a reader compares them.
    assert "over different sets and need not agree" in html


def test_render_labels_which_denominator_the_coverage_prose_means(tmp_path):
    """M11: one word, two numbers, on one page -- measured 127 in the coverage prose
    against `capability_cells 148, goals 22` in the world-model table, and neither
    saying which sense it meant.
    """
    run = build_toy_run(tmp_path / "runs", upto="score-seal")
    html = summary.run_summary(run)
    # The comma and the trailing space pin the *prose* line rather than the note
    # below it, which necessarily uses the same two words: measured, `assert
    # "sizing denominator" in html` stayed green with the prose reverted, because
    # the note alone satisfied it.
    assert ", sizing denominator " in html
    assert "expected hop-depth slots, less blocked cells" in html
    # The world model's own record is still rendered under its own name, so the two
    # senses are distinguishable rather than merged.
    assert "<h3>Denominator</h3>" in html


def test_render_says_the_artifact_links_are_relative_to_the_run(tmp_path):
    """M12: all 23 relative hrefs are dead when `-o` points outside the run, and
    `-o` is exactly the flag an operator uses for a read-only run directory. The
    behaviour is correct and documented; the page carried no note.
    """
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    html = summary.run_summary(run)
    assert "Artifact links are relative to the run directory" in html
    assert "-o" in html.split("Artifact links are relative")[1][:400]


def test_render_links_a_scenario_to_its_instance_and_its_package(tmp_path):
    """R28, and spec 3.5: three hrefs per row, of which only `05-verdicts/` existed.

    Both new links are asserted, and both negatives with them: the plain-text
    `yes` and the plain-text file list are what this replaces, so a renderer that
    linked one column and not the other cannot pass.
    """
    from rubrica.emit import emit_run

    run = build_toy_run(tmp_path / "runs")
    emit_run(run)
    html = summary.run_summary(run)
    assert '<a href="04-instances/scn-open/">yes</a>' in html
    assert '<a href="06-suite/scn-open/">' in html
    rows = summary.scenarios(run)
    # One link per row that has the thing, and no more: the folded duplicate has
    # neither, so a renderer that linked every row cannot pass.
    assert html.count('<a href="04-instances/') == len([r for r in rows if r.has_instance])
    assert html.count('<a href="06-suite/') == len([r for r in rows if r.suite_files])
    assert '<span class="absent">no package</span>' in html


def test_clipped_marks_one_character_past_the_boundary_and_not_the_boundary(tmp_path):
    """The `<=` in `_clipped`, which nothing pinned.

    Measured: mutating `<= _CLIP_AT` to `< _CLIP_AT` -- which marks an uncut
    120-character cell as clipped -- left every test in this file green, because
    both existing tests sit far from the boundary. Asserted at the two adjacent
    widths, on `_clipped` itself rather than through a page, because no artifact
    field can be pinned to an exact length without the fixture asserting it.
    """
    from rubrica import summary_html

    exact = "x" * summary_html._CLIP_AT
    over = "x" * (summary_html._CLIP_AT + 1)
    assert "&hellip;" not in summary_html._clipped(exact), "a cell that fits is not clipped"
    assert summary_html._clipped(exact) == exact
    assert "&hellip;" in summary_html._clipped(over)
