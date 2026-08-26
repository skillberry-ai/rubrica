"""The loop's three code subcommands, including the paths that must exit 2.

The exit-code contract is load-bearing: 0 clean, 1 findings one per line on
stdout, 2 usage error or unreadable run. A stage defect must never surface as 2,
a 1 must never have empty stdout, and a 1 must name the right artifact -- the
class that once produced four fabricated "no such claim" findings against a
correct world model.
"""

from __future__ import annotations

import os

import pytest

from rubrica.artifacts import write_json
from rubrica.cli import main
from rubrica.paths import RunPaths


def _minimal(tmp_path):
    run = RunPaths(tmp_path)
    write_json(
        run.world_model,
        {
            "schema_version": "0.1",
            "denominator": {"capability_cells": 1, "goals": 1, "version": 1},
            "capabilities": [{"id": "cap-0", "outcome_classes": [{"id": "cap-0-oc-0"}]}],
            "goals": [{"id": "goal-0", "expected_hop_depths": [1]}],
        },
    )
    return run


def test_propose_batches_exits_clean_and_prints_the_path(tmp_path, capsys):
    run = _minimal(tmp_path)
    assert main(["propose-batches", "--run", str(tmp_path), "--round", "1"]) == 0
    assert str(run.batches(1)) in capsys.readouterr().out


def test_propose_batches_says_so_when_there_is_nothing_to_dispatch(tmp_path, capsys):
    run = _minimal(tmp_path)
    write_json(
        run.world_model,
        {
            "schema_version": "0.1",
            "capabilities": [],
            "goals": [],
            "denominator": {"capability_cells": 0, "goals": 0, "version": 1},
        },
    )
    # Exit 0, not 1: no closable hole is a fact about the run, not a defect in
    # it, and the orchestrator branches on the message rather than on a finding.
    assert main(["propose-batches", "--run", str(tmp_path), "--round", "1"]) == 0
    assert "no closable holes" in capsys.readouterr().out
    assert not run.batches(1).exists()


@pytest.mark.skipif(
    os.geteuid() == 0, reason="chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)"
)
def test_propose_batches_exits_two_on_an_unreadable_world_model(tmp_path, capsys):
    run = _minimal(tmp_path)
    run.world_model.chmod(0o000)
    try:
        assert main(["propose-batches", "--run", str(tmp_path), "--round", "1"]) == 2
    finally:
        run.world_model.chmod(0o644)
    assert capsys.readouterr().err.strip() != ""


def test_propose_batches_exits_two_on_a_missing_run(tmp_path):
    assert main(["propose-batches", "--run", str(tmp_path / "nope"), "--round", "1"]) == 2


def test_propose_batches_exits_two_on_a_budget_below_one_scenario(tmp_path, capsys):
    run = _minimal(tmp_path)
    write_json(
        run.manifest,
        {"limits": {"max_rounds": 2, "max_scenarios": 128, "max_scenario_part_bytes": 10}},
    )
    # A misconfigured budget is a usage error, not a stage defect: no
    # re-dispatch of any prompt can fix it.
    assert main(["propose-batches", "--run", str(tmp_path), "--round", "1"]) == 2
    assert "max_scenario_part_bytes" in capsys.readouterr().err


def test_propose_seal_exits_one_with_a_line_per_finding(tmp_path, capsys):
    run = _minimal(tmp_path)
    for batch in ("b01", "b02"):
        write_json(
            run.scenario_part(1, batch),
            {
                "schema_version": "0.1",
                "round": 1,
                "batch_id": batch,
                "scenarios": [
                    {
                        "id": "sc-001",
                        "round": 1,
                        "goal_id": "goal-0",
                        "actor_id": "a",
                        "title": "t",
                        "user_intent": "u",
                        "hop_depth": 1,
                        "capability_refs": [],
                        "discriminating_fact": "f",
                        "status": "proposed",
                        "provenance": {"round": 1},
                    }
                ],
            },
        )
    assert main(["propose-seal", "--run", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    # A 1 must never have empty stdout, and every finding is one line.
    assert out.strip() != ""
    assert all(line.strip() for line in out.strip().splitlines())
    assert "sc-001" in out
    # The right artifact: the collision is in the part a member wrote, and
    # 02-scenarios.json -- this seal's own code output -- was never written.
    assert str(run.scenario_part(1, "b02")) in out
    assert not run.scenarios.exists()


def test_score_seal_exits_one_and_names_the_score_part_not_the_coverage_file(tmp_path, capsys):
    # The right-artifact rule: the defect is in the part a prompt wrote, and a
    # finding against 03-coverage/round-1.json would name a file that does not
    # exist and that no re-dispatch could repair.
    run = _minimal(tmp_path)
    write_json(
        run.scenario_part(1, "b01"),
        {"schema_version": "0.1", "round": 1, "batch_id": "b01", "scenarios": []},
    )
    write_json(
        run.score_part(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "rulings": [],
            "holes": [],
            "verdict": "converged",
        },
    )
    assert main(["propose-seal", "--run", str(tmp_path)]) == 0
    assert main(["score-seal", "--run", str(tmp_path), "--round", "1"]) == 1
    out = capsys.readouterr().out
    assert str(run.score_part(1)) in out
    assert not run.coverage_round(1).exists()


def test_score_seal_exits_clean_and_publishes_latest(tmp_path, capsys):
    run = _minimal(tmp_path)
    write_json(
        run.scenario_part(1, "b01"),
        {"schema_version": "0.1", "round": 1, "batch_id": "b01", "scenarios": []},
    )
    write_json(
        run.score_part(1),
        {
            "schema_version": "0.1",
            "round": 1,
            "rulings": [],
            "verdict": "continue",
            "holes": [
                {
                    "ref": "cell:cap-0/cap-0-oc-0",
                    "reason": "not_yet_attempted",
                    "justification": "nobody yet",
                },
                {
                    "ref": "goal:goal-0",
                    "reason": "not_yet_attempted",
                    "justification": "nobody yet",
                },
            ],
        },
    )
    assert main(["propose-seal", "--run", str(tmp_path)]) == 0
    assert main(["score-seal", "--run", str(tmp_path), "--round", "1"]) == 0
    assert run.coverage_latest.read_bytes() == run.coverage_round(1).read_bytes()
    assert str(run.coverage_round(1)) in capsys.readouterr().out


# A round number arrives on argv, so a bad one is a usage error and must be
# exit 2. Left to RunPaths it is a bare ValueError -- neither UsageError nor
# ArtifactError -- so it reaches cli.py's catch-all and becomes an exit-1
# `[internal]` finding: a fabricated stage defect against a run that is fine.
@pytest.mark.parametrize("command", ["propose-batches", "score-seal"])
@pytest.mark.parametrize("bad", ["0", "-1", "one"])
def test_a_round_number_outside_the_contract_is_a_usage_error(tmp_path, capsys, command, bad):
    _minimal(tmp_path)
    assert main([command, "--run", str(tmp_path), "--round", bad]) == 2
    captured = capsys.readouterr()
    assert "--round" in captured.err
    # stdout stays empty: a 2 is not a finding, and an orchestrator parsing
    # stdout for finding lines must see nothing to act on.
    assert captured.out == ""
