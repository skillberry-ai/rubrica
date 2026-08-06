import json
from pathlib import Path

from testgen.artifacts import write_json
from testgen.cli import main
from testgen.paths import RunPaths
from tests.builders import minimal_claims, minimal_scenarios, minimal_world_model


def _seeded_run(tmp_path):
    run = RunPaths(tmp_path / "runs" / "run-1")
    write_json(run.claims("aap2-api"), minimal_claims())
    write_json(run.world_model, minimal_world_model())
    return run


def test_no_subcommand_is_a_usage_error(capsys):
    assert main([]) == 2


def test_unknown_subcommand_is_a_usage_error():
    assert main(["frobnicate"]) == 2


def test_validate_a_clean_stage_exits_zero(tmp_path, capsys):
    run = _seeded_run(tmp_path)
    assert main(["validate", "--run", str(run.root), "--stage", "reconcile"]) == 0
    assert capsys.readouterr().out.strip() == ""


def test_validate_a_failing_stage_exits_one_and_prints_findings(tmp_path, capsys):
    run = _seeded_run(tmp_path)
    write_json(run.world_model, minimal_world_model(schema_version="0.9"))
    assert main(["validate", "--run", str(run.root), "--stage", "reconcile"]) == 1
    assert "[schema]" in capsys.readouterr().out


def test_validate_an_unknown_stage_is_a_usage_error(tmp_path):
    run = _seeded_run(tmp_path)
    assert main(["validate", "--run", str(run.root), "--stage", "reconsile"]) == 2


def test_validate_a_missing_run_directory_is_a_usage_error(tmp_path):
    assert main(["validate", "--run", str(tmp_path / "absent"), "--stage", "reconcile"]) == 2


def test_check_refs_on_a_clean_run_exits_zero(tmp_path, capsys):
    run = _seeded_run(tmp_path)
    assert main(["check-refs", "--run", str(run.root)]) == 0
    assert capsys.readouterr().out.strip() == ""


def test_check_refs_prints_findings_and_exits_one(tmp_path, capsys):
    run = _seeded_run(tmp_path)
    world = minimal_world_model()
    world["denominator"]["goals"] = 7
    write_json(run.world_model, world)
    assert main(["check-refs", "--run", str(run.root)]) == 1
    assert "[refs]" in capsys.readouterr().out


def test_dedupe_candidates_emits_json_on_stdout(tmp_path, capsys):
    run = _seeded_run(tmp_path)
    payload = minimal_scenarios()
    second = dict(payload["scenarios"][0])
    second["id"] = "scn-002"
    payload["scenarios"].append(second)
    write_json(run.scenarios, payload)
    assert main(["dedupe-candidates", "--run", str(run.root)]) == 0
    emitted = json.loads(capsys.readouterr().out)
    assert emitted == [
        {
            "a": "scn-001",
            "b": "scn-002",
            "shared_cells": ["cell:cap-find-jobs/oc-success"],
            "identical_cells": True,
        }
    ]


def test_dedupe_candidates_without_scenarios_is_a_usage_error(tmp_path):
    run = _seeded_run(tmp_path)
    assert main(["dedupe-candidates", "--run", str(run.root)]) == 2


def test_intake_creates_a_run_and_prints_its_path(tmp_path, capsys):
    source = tmp_path / "api.json"
    source.write_text('{"tools": []}', encoding="utf-8")
    code = main(
        [
            "intake",
            "--input",
            str(source),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--target-name",
            "aap2",
            "--target-interface",
            "mcp",
            "--max-rounds",
            "2",
            "--max-scenarios",
            "8",
        ]
    )
    assert code == 0
    printed = capsys.readouterr().out.strip()
    assert (tmp_path / "runs") == Path(printed).parent
    assert (Path(printed) / "manifest.json").is_file()


def test_intake_with_a_missing_input_is_a_usage_error(tmp_path):
    code = main(
        [
            "intake",
            "--input",
            str(tmp_path / "absent.json"),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--target-name",
            "aap2",
            "--target-interface",
            "mcp",
        ]
    )
    assert code == 2


def test_intake_defaults_the_first_slice_limits(tmp_path, capsys):
    from testgen.artifacts import read_json

    source = tmp_path / "api.json"
    source.write_text('{"tools": []}', encoding="utf-8")
    main(
        [
            "intake",
            "--input",
            str(source),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--target-name",
            "aap2",
            "--target-interface",
            "mcp",
        ]
    )
    printed = capsys.readouterr().out.strip()
    manifest = read_json(Path(printed) / "manifest.json")
    assert manifest["limits"] == {"max_rounds": 2, "max_scenarios": 8}
