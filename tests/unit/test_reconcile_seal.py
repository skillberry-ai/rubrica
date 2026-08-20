"""The seal, and the one property that makes the split safe.

The round trip is the whole point: if seal(split(w)) != w, then staging reconcile
changed what the pipeline produces, and every fixture and recording downstream of
01-world-model.json is describing a world the new passes cannot rebuild.
"""

from __future__ import annotations

import os

import pytest

from rubrica import reconcile, refs, validate
from rubrica.artifacts import read_json, write_json
from tests.toy import build_toy_run, split_world_model, toy_world_model


def _write_parts(run, parts: dict) -> None:
    write_json(run.capabilities_part, parts["capabilities"])
    write_json(run.outcomes_part, parts["outcomes"])
    write_json(run.entities_part, parts["entities"])
    write_json(run.goals_part, parts["goals"])
    write_json(run.gaps_part, parts["gaps"])
    write_json(run.subjects, parts["subjects"])
    for subject_id, part in parts["contradictions"].items():
        write_json(run.contradiction_part(subject_id), part)


def test_the_seal_rebuilds_the_golden_world_model_exactly(tmp_path):
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())

    path, findings = reconcile.seal(run)

    assert findings == []
    assert path == run.world_model
    assert read_json(run.world_model) == toy_world_model()


def test_the_sealed_world_model_passes_layer_one(tmp_path):
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    reconcile.seal(run)
    assert validate.validate_artifact(run.world_model, "world-model") == []


def test_the_denominator_is_computed_not_copied(tmp_path):
    """The arithmetic is the seal's job. A partial cannot assert it, and nothing
    in the partials carries a number for the seal to trust."""
    run = build_toy_run(tmp_path, upto="extract")
    parts = split_world_model()
    _write_parts(run, parts)
    reconcile.seal(run)

    world = read_json(run.world_model)
    expected_cells = sum(len(o["outcome_classes"]) for o in parts["outcomes"]["outcomes"])
    assert world["denominator"] == {
        "version": 1,
        "capability_cells": expected_cells,
        "goals": len(parts["goals"]["goals"]),
    }


def test_the_denominator_agrees_with_the_recomputation_that_checks_it(tmp_path):
    """refs.check_world_model recomputes capability_cells, which makes the field an
    identity rather than an independent claim: whatever the seal writes has to be
    what the check derives, or check-refs reports a finding against a world model
    the seal itself just produced.

    Asserted through check_world_model rather than by recomputing the count here,
    so the two sides are not both this test's own arithmetic."""
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    reconcile.seal(run)

    assert [f for f in refs.check_world_model(run) if f.pointer.startswith("/denominator")] == []


def test_the_denominator_counts_distinct_cells_not_a_sum_of_counts(tmp_path):
    """The case where set semantics and a sum diverge, which the toy world model
    cannot reach on its own: refs._cells is a *set* of (capability, outcome class)
    pairs, so a repeated outcome-class id inside one capability is one cell, not
    two. A seal that summed per-capability lengths would write 6 here and the
    check that recomputes the field would immediately contradict it.

    The repeat is schema-legal -- the world-model schema puts no uniqueItems on
    outcome_classes, and check_world_model's duplicate-id scan covers the four
    top-level groups, not the classes nested inside a capability -- so nothing
    else in the pipeline stands between a repeated cell and this count."""
    run = build_toy_run(tmp_path, upto="extract")
    parts = split_world_model()
    first = parts["outcomes"]["outcomes"][0]
    # Copied before mutating: split_world_model's entities/actors/goals/gaps are
    # references into the world dict it was handed, and its outcome_classes lists
    # come straight off the golden capabilities. Appending in place would edit
    # toy_world_model()'s own structures for anything sharing them.
    repeated = [*first["outcome_classes"], dict(first["outcome_classes"][0])]
    parts["outcomes"]["outcomes"] = [
        {"capability_id": first["capability_id"], "outcome_classes": repeated},
        *parts["outcomes"]["outcomes"][1:],
    ]
    _write_parts(run, parts)

    reconcile.seal(run)

    world = read_json(run.world_model)
    naive_sum = sum(len(o["outcome_classes"]) for o in parts["outcomes"]["outcomes"])
    distinct = len(
        {(c["id"], oc["id"]) for c in world["capabilities"] for oc in c["outcome_classes"]}
    )
    assert naive_sum != distinct, "the fixture must reach the case where the two differ"
    assert world["denominator"]["capability_cells"] == distinct
    assert [f for f in refs.check_world_model(run) if f.pointer.startswith("/denominator")] == []


def test_the_denominator_version_can_be_bumped_for_an_amendment(tmp_path):
    """An amendment costs an explicit orchestrator decision and a version bump.
    The seal takes the bumped number rather than inventing or incrementing one,
    so the record of why it moved stays in decisions.md."""
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    reconcile.seal(run, denominator_version=2)
    assert read_json(run.world_model)["denominator"]["version"] == 2


def test_the_target_comes_from_the_manifest(tmp_path):
    """No pass restates it. Today reconcile writes `target` itself and nothing
    checks it against the manifest, so this removes an unchecked restatement."""
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    reconcile.seal(run)
    assert read_json(run.world_model)["target"] == read_json(run.manifest)["target"]


@pytest.mark.parametrize(
    "attribute",
    ["capabilities_part", "outcomes_part", "entities_part", "goals_part", "gaps_part"],
)
def test_a_missing_partial_is_a_finding_and_writes_nothing(tmp_path, attribute):
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    getattr(run, attribute).unlink()

    path, findings = reconcile.seal(run)

    assert path is None
    assert findings, f"a missing {attribute} must be reported"
    assert not run.world_model.is_file(), "the seal must not write a partial world model"
    assert all(f.message for f in findings), "a finding with an empty message is an empty exit-1"


def test_several_missing_partials_name_the_earliest_pass_first(tmp_path):
    """Pass order, not filesystem order: the first finding names the pass a repair
    should start from, the same property _readable_targets holds for layer 2."""
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    run.gaps_part.unlink()
    run.outcomes_part.unlink()

    _, findings = reconcile.seal(run)

    assert [f.artifact for f in findings] == [run.outcomes_part, run.gaps_part]


def test_a_capability_with_no_outcome_record_is_a_finding(tmp_path):
    run = build_toy_run(tmp_path, upto="extract")
    parts = split_world_model()
    parts["outcomes"]["outcomes"] = parts["outcomes"]["outcomes"][:1]
    _write_parts(run, parts)

    path, findings = reconcile.seal(run)

    assert path is None
    assert any("no outcome classes" in f.message for f in findings)
    assert not run.world_model.is_file()


def test_an_outcome_record_for_an_unknown_capability_is_a_finding(tmp_path):
    run = build_toy_run(tmp_path, upto="extract")
    parts = split_world_model()
    parts["outcomes"]["outcomes"].append(
        {
            "capability_id": "cap-invented",
            "outcome_classes": [{"id": "oc-x", "kind": "success", "description": "invented"}],
        }
    )
    _write_parts(run, parts)

    path, findings = reconcile.seal(run)

    assert path is None
    assert any("cap-invented" in f.message for f in findings)


def test_the_cli_exits_clean_and_prints_the_world_model_path(tmp_path, capsys):
    from rubrica.cli import main

    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())

    assert main(["reconcile-seal", "--run", str(run.root)]) == 0
    assert capsys.readouterr().out.strip() == str(run.world_model)


def test_the_cli_exits_one_with_findings_on_stdout(tmp_path, capsys):
    """The exit-code contract: a stage defect is 1, one finding per line, on
    stdout -- never 2, and never an empty stdout."""
    from rubrica.cli import main

    run = build_toy_run(tmp_path, upto="extract")
    parts = split_world_model()
    _write_parts(run, parts)
    run.gaps_part.unlink()

    assert main(["reconcile-seal", "--run", str(run.root)]) == 1
    out = capsys.readouterr().out
    assert out.strip(), "exit 1 with empty stdout is the failure this forbids"
    # And it names the missing partial. Measured: with the finding swallowed
    # instead of reported, the KeyError that follows is still caught and still
    # exits 1 with a line on stdout -- but that line is `[internal]` against the
    # run root, so exit code and non-empty stdout alone cannot tell the seal
    # reporting a missing partial from the catch-all rescuing an exception.
    assert "01-gaps.json" in out


def test_a_missing_run_directory_is_a_usage_error(tmp_path, capsys):
    from rubrica.cli import main

    assert main(["reconcile-seal", "--run", str(tmp_path / "nope")]) == 2


@pytest.mark.parametrize("mode", [0o000, 0o444])
def test_an_unreadable_contradictions_directory_is_exit_2_not_a_finding(tmp_path, capsys, mode):
    """The other side of the split this task has to get right: a *missing* partial
    is a repairable stage defect (1), while a run directory the harness cannot read
    is a misconfiguration (2) and repeating the pass cannot help.

    Both modes, because they are different code paths: at 0o000 the listing itself
    fails, at 0o444 the listing succeeds and stat'ing a child fails. The shape
    matters here because `Path.glob` swallows EACCES -- an unreadable 01-claims/
    once made check-refs report four `no such claim` findings against a correct
    world model, and a glob here would have the seal silently assemble a world
    model with no contradictions at all."""
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    from rubrica.cli import main

    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    run.contradictions_dir.chmod(mode)
    try:
        code = main(["reconcile-seal", "--run", str(run.root)])
    finally:
        run.contradictions_dir.chmod(0o755)
    captured = capsys.readouterr()
    assert code == 2, captured.out
    assert captured.out.strip() == "", "a filesystem problem must not print a finding line"
    assert captured.err.startswith("error: ")
    assert not run.world_model.is_file()


def test_a_malformed_partial_is_a_finding_naming_that_partial(tmp_path, capsys):
    """Not exit 2, and not a finding against some other artifact. This repo has
    reported four fabricated `no such claim` findings against a correct world
    model because an unreadable input was blamed on the wrong file."""
    from rubrica.cli import main

    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    run.entities_part.write_text("{not json", encoding="utf-8")

    code = main(["reconcile-seal", "--run", str(run.root)])
    out = capsys.readouterr().out
    assert code == 1
    assert "01-entities.json" in out
