import json
import sys
from pathlib import Path

from testgen.artifacts import write_json
from testgen.cli import main
from testgen.paths import RunPaths
from tests.builders import (
    minimal_claims,
    minimal_gold,
    minimal_manifest,
    minimal_scenarios,
    minimal_world_model,
)
from tests.unit.test_refs_states import build_state
from tests.unit.test_smoke_subprocess import COMPETENT, TOOLLESS


def _seeded_run(tmp_path):
    run = RunPaths(tmp_path / "runs" / "run-1")
    write_json(run.claims("aap2-api"), minimal_claims())
    write_json(run.world_model, minimal_world_model())
    return run


def test_no_subcommand_is_a_usage_error(capsys):
    assert main([]) == 2


def test_unknown_subcommand_is_a_usage_error():
    assert main(["frobnicate"]) == 2


def test_top_level_help_exits_clean(capsys):
    """--help is not a misconfigured harness.

    argparse raises SystemExit(0) here and SystemExit(2) for a real usage
    error; the orchestrator branches on the difference.
    """
    assert main(["--help"]) == 0
    assert "usage: testgen" in capsys.readouterr().out


def test_subcommand_help_exits_clean(capsys):
    assert main(["validate", "--help"]) == 0
    assert "--stage" in capsys.readouterr().out


def test_bad_stage_choice_is_still_a_usage_error(tmp_path):
    """The SystemExit(2) path argparse takes for an invalid --choice."""
    run = _seeded_run(tmp_path)
    assert main(["validate", "--run", str(run.root), "--stage", "not-a-stage"]) == 2


def test_a_missing_required_argument_is_still_a_usage_error():
    assert main(["validate"]) == 2


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


def test_an_unsafe_instance_directory_exits_one_not_two(tmp_path, capsys):
    """A badly-named directory is a repairable stage defect, not a bad harness.

    Exit 1 buys the orchestrator its one repair attempt with the finding in
    hand; exit 2 would tell it to halt.
    """
    run = _seeded_run(tmp_path)
    write_json(run.scenarios, minimal_scenarios())
    (run.instances_dir / "scn 001").mkdir(parents=True, exist_ok=True)
    assert main(["check-refs", "--run", str(run.root)]) == 1
    assert "scn 001" in capsys.readouterr().out


def test_a_non_numeric_coverage_pct_exits_one_not_two(tmp_path, capsys):
    """A repairable score-stage defect must never be reported as a bad harness.

    `float("half")` raised ValueError out of _check_matrix_arithmetic, and the
    bare ValueError in cli.py's catch tuple -- there for intake's own usage
    checks -- turned it into exit 2, telling the orchestrator to halt when one
    repair would have cleared it.
    """
    from tests.builders import minimal_coverage

    run = _seeded_run(tmp_path)
    write_json(run.scenarios, minimal_scenarios())
    coverage = minimal_coverage()
    coverage["capability_matrix"]["pct"] = "half"
    write_json(run.coverage_latest, coverage)

    assert main(["check-refs", "--run", str(run.root)]) == 1
    out = capsys.readouterr().out
    assert "/capability_matrix/pct" in out
    assert "'half'" in out


def test_an_unexpected_exception_exits_one_with_a_finding_on_stdout(tmp_path, capsys):
    """A 1 with an empty stdout makes the orchestrator retry blind.

    refs.py and emit.py both document the layer-1 precondition that makes these
    unreachable in the happy path. When a caller runs check-refs without
    validate, the KeyError must still arrive as a line naming the run and the
    exception rather than a bare exit code.
    """
    run = _seeded_run(tmp_path)
    manifest = minimal_manifest()
    del manifest["limits"]
    write_json(run.manifest, manifest)

    assert main(["check-refs", "--run", str(run.root)]) == 1
    captured = capsys.readouterr()
    assert "[internal]" in captured.out
    assert "KeyError" in captured.out
    assert "validate" in captured.out, "the line must say what to run next"
    assert str(run.root) in captured.out
    assert "Traceback" not in captured.out, "the traceback belongs on stderr"
    assert "Traceback" in captured.err


def test_an_emit_over_a_malformed_oracle_exits_one_with_a_finding(tmp_path, capsys):
    """The same, through emit, which holds the most direct indexing in the project."""
    from tests.builders import minimal_expected, minimal_seed, minimal_verdict, minimal_world_model

    run = _seeded_run(tmp_path)
    write_json(run.world_model, minimal_world_model())
    write_json(run.scenarios, minimal_scenarios())
    write_json(run.seed("scn-001"), minimal_seed())
    expected = minimal_expected()
    del expected["completion"]
    write_json(run.expected("scn-001"), expected)
    write_json(run.verdict("scn-001"), minimal_verdict())

    assert main(["emit", "--run", str(run.root)]) == 1
    out = capsys.readouterr().out
    assert "[internal]" in out
    assert "KeyError" in out


def test_an_escaping_unsafe_segment_exits_one_not_two(tmp_path, capsys, monkeypatch):
    """UnsafeSegment is a ValueError subclass, so the bare catch tuple hid it too.

    Every id-joining call site in the project now derives its ids from a
    safe-segment-filtered listing, so no artifact can currently drive
    UnsafeSegment out to the CLI -- writing a run directory that provokes one
    would be a test whose values never reach the behaviour its name claims. The
    check is that cli.py's *mapping* is right, so the exception is raised where
    a future unhardened call site would raise it: exit 1 with a line, not the
    exit 2 that tells the orchestrator the harness is broken.
    """
    from testgen import refs
    from testgen.paths import UnsafeSegment

    run = _seeded_run(tmp_path)

    def explode(_run):
        raise UnsafeSegment("unsafe path segment: '../escape'")

    monkeypatch.setattr(refs, "check_all", explode)

    assert main(["check-refs", "--run", str(run.root)]) == 1
    out = capsys.readouterr().out
    assert "[internal]" in out
    assert "UnsafeSegment" in out
    assert "../escape" in out, "exit 1 must never mean 'no information'"


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


def _write_roster(tmp_path, weak_is_competent=False):
    """An agents.json whose three commands are scripted stand-ins, not models.

    weak_is_competent hands the weak baseline the same script as the oracle, so
    a degenerate suite (a tool-less agent is not required to pass it) can be
    provoked on demand.
    """
    weak_script = tmp_path / "weak.py"
    weak_script.write_text(COMPETENT if weak_is_competent else TOOLLESS, encoding="utf-8")
    under_script = tmp_path / "under.py"
    under_script.write_text(COMPETENT, encoding="utf-8")
    oracle_script = tmp_path / "oracle.py"
    oracle_script.write_text(COMPETENT, encoding="utf-8")

    roster = tmp_path / "agents.json"
    write_json(
        roster,
        {
            "schema_version": "0.1",
            "agents": [
                {
                    "role": "weak_baseline",
                    "model": "model-weak",
                    "command": [sys.executable, str(weak_script)],
                },
                {
                    "role": "under_test",
                    "model": "model-under",
                    "command": [sys.executable, str(under_script)],
                },
                {
                    "role": "oracle",
                    "model": "model-oracle",
                    "command": [sys.executable, str(oracle_script)],
                },
            ],
        },
    )
    return roster


def test_smoke_exits_zero_on_a_healthy_suite(tmp_path, capsys):
    run = build_state(tmp_path / "run", "emit")
    roster = _write_roster(tmp_path)
    code = main(["smoke", "--run", str(run.root), "--agents", str(roster)])
    assert code == 0
    assert str(run.report) in capsys.readouterr().out


def test_smoke_exits_two_on_an_unusable_roster(tmp_path, capsys):
    run = build_state(tmp_path / "run", "emit")
    assert main(["smoke", "--run", str(run.root), "--agents", str(tmp_path / "nope.json")]) == 2
    assert "unusable agent roster" in capsys.readouterr().err


def test_smoke_exits_one_with_findings_on_a_degenerate_suite(tmp_path, capsys):
    run = build_state(tmp_path / "run", "emit")
    roster = _write_roster(tmp_path, weak_is_competent=True)
    assert main(["smoke", "--run", str(run.root), "--agents", str(roster)]) == 1
    out = capsys.readouterr().out
    assert "[smoke]" in out and "not testing anything" in out


def test_smoke_exits_two_when_the_directory_has_no_manifest(tmp_path, capsys):
    """A directory without a manifest is not a run, and no stage repair makes one."""
    run = build_state(tmp_path / "run", "emit")
    run.manifest.unlink()
    roster = _write_roster(tmp_path)
    assert main(["smoke", "--run", str(run.root), "--agents", str(roster)]) == 2


def _write_gold(tmp_path, payload=None):
    path = tmp_path / "gold.json"
    write_json(path, payload if payload is not None else minimal_gold())
    return path


def test_compare_gold_exits_zero_on_a_full_match(tmp_path, capsys):
    run = build_state(tmp_path / "run", "emit")
    gold = _write_gold(tmp_path)
    assert main(["compare-gold", "--run", str(run.root), "--gold", str(gold)]) == 0
    out = capsys.readouterr().out
    assert "Recall and novelty" in out
    assert (run.measurement_dir / "recall.json").is_file()


def test_compare_gold_exits_one_on_an_unmatched_gold_task(tmp_path, capsys):
    run = build_state(tmp_path / "run", "emit")
    payload = minimal_gold()
    payload["tasks"][0]["goal_id"] = "goal-elsewhere"
    gold = _write_gold(tmp_path, payload)
    assert main(["compare-gold", "--run", str(run.root), "--gold", str(gold)]) == 1
    out = capsys.readouterr().out
    assert "[recall]" in out
    assert "bench-001" in out


def test_compare_gold_exits_two_on_a_malformed_gold_file(tmp_path, capsys):
    run = build_state(tmp_path / "run", "emit")
    payload = minimal_gold()
    payload["tasks"][0]["hop_depth"] = 99
    gold = _write_gold(tmp_path, payload)
    assert main(["compare-gold", "--run", str(run.root), "--gold", str(gold)]) == 2
    assert "unusable gold" in capsys.readouterr().err


def test_diff_runs_emits_json_on_stdout_for_two_identical_runs(tmp_path, capsys):
    run_a = build_state(tmp_path / "a", "emit")
    run_b = build_state(tmp_path / "b", "emit")
    assert main(["diff-runs", "--a", str(run_a.root), "--b", str(run_b.root)]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["comparable"] is True
    assert captured.err == ""


def test_diff_runs_warns_on_stderr_when_the_runs_read_different_inputs(tmp_path, capsys):
    run_a = build_state(tmp_path / "a", "emit")
    run_b = build_state(tmp_path / "b", "emit")
    manifest = json.loads(run_b.manifest.read_text(encoding="utf-8"))
    manifest["inputs"][0]["sha256"] = "f" * 64
    write_json(run_b.manifest, manifest)

    code = main(["diff-runs", "--a", str(run_a.root), "--b", str(run_b.root)])
    captured = capsys.readouterr()
    assert code == 0
    report = json.loads(captured.out)
    assert report["comparable"] is False
    assert "different input" in captured.err


def test_diff_runs_exits_two_on_a_nonexistent_b_directory(tmp_path):
    run_a = build_state(tmp_path / "a", "emit")
    assert main(["diff-runs", "--a", str(run_a.root), "--b", str(tmp_path / "absent")]) == 2
