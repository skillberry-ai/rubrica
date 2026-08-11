import json
import os
import sys
from pathlib import Path

import pytest

import rubrica.validate
from rubrica.artifacts import read_json, write_json
from rubrica.cli import main, subcommand_names
from rubrica.paths import RunPaths
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
    assert "usage: rubrica" in capsys.readouterr().out


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
    from rubrica import refs
    from rubrica.paths import UnsafeSegment

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


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--target-name", ""),
        ("--target-interface", "   "),
        ("--max-rounds", "0"),
        ("--max-scenarios", "0"),
    ],
)
def test_intake_refuses_to_mint_a_run_the_intake_gate_would_fail(tmp_path, capsys, flag, value):
    """Exit 2 and an empty runs directory, where it used to be exit 0 and a run.

    Each of these violates manifest-0.1.json (minLength 1 on the target strings,
    minimum 1 on the limits), so the run intake minted failed `validate --stage
    intake` immediately -- a finding against an artifact intake wrote itself, so
    no repair prompt could ever clear it. Checked at the CLI as well as in
    intake() because this is the surface a person actually mistypes.
    """
    source = tmp_path / "api.json"
    source.write_text('{"tools": []}', encoding="utf-8")
    arguments = {
        "--input": str(source),
        "--runs-dir": str(tmp_path / "runs"),
        "--target-name": "aap2",
        "--target-interface": "mcp",
        flag: value,
    }
    argv = ["intake"]
    for name, argument in arguments.items():
        argv += [name, argument]
    code = main(argv)
    captured = capsys.readouterr()
    assert code == 2, captured.out
    assert captured.out.strip() == "", "a refused intake must not print a run directory"
    assert captured.err.startswith("error: ")
    assert not (tmp_path / "runs").exists(), "a refused intake must mint nothing"


def test_intake_defaults_the_first_slice_limits(tmp_path, capsys):
    from rubrica.artifacts import read_json

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


def test_compare_gold_prints_only_the_path_it_wrote_on_stdout(tmp_path, capsys):
    """stdout is the findings channel, so prose must not share it.

    Exit 1 means finding lines on stdout, one per line. A 25-line markdown
    document printed to the same stream ahead of them is indistinguishable from
    findings to the orchestrator's line parser -- the hazard diff-runs names and
    avoids. smoke prints the path to the report it wrote; so does this. The
    rendering still reaches a human, on stderr.
    """
    run = build_state(tmp_path / "run", "emit")
    gold = _write_gold(tmp_path)
    assert main(["compare-gold", "--run", str(run.root), "--gold", str(gold)]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == str(run.recall_md)
    assert "Recall and novelty" not in captured.out
    assert "Recall and novelty" in captured.err
    assert run.recall.is_file()
    assert run.recall_md.is_file()


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


def test_sample_for_review_exits_zero_and_prints_the_packet_path(tmp_path, capsys):
    run = build_state(tmp_path / "run", "emit")
    assert main(["sample-for-review", "--run", str(run.root)]) == 0
    out = capsys.readouterr().out
    assert out.strip() == str(run.review_packet)
    assert run.review_sample.is_file()


def test_sample_for_review_exits_one_when_emit_has_not_run(tmp_path, capsys):
    run = build_state(tmp_path / "run", "challenge")
    assert main(["sample-for-review", "--run", str(run.root)]) == 1
    out = capsys.readouterr().out
    assert "[review]" in out
    assert "no emitted packages" in out


def test_sample_for_review_exits_two_on_a_nonexistent_run_directory(tmp_path):
    assert main(["sample-for-review", "--run", str(tmp_path / "absent")]) == 2


def test_sample_for_review_with_a_size_of_zero_is_a_usage_error_and_writes_nothing(
    tmp_path, capsys
):
    """An empty packet at exit 0 is indistinguishable from success.

    --size 0 used to overwrite an existing packet with a packet of no tasks and
    exit clean, which reads as "reviewed, nothing to say". intake validates its
    own numeric arguments as a usage error; so does this.
    """
    run = build_state(tmp_path / "run", "emit")
    assert main(["sample-for-review", "--run", str(run.root)]) == 0
    capsys.readouterr()
    first = run.review_packet.read_text()
    sample_before = run.review_sample.read_text()

    assert main(["sample-for-review", "--run", str(run.root), "--size", "0"]) == 2
    captured = capsys.readouterr()
    assert "size" in captured.err
    assert captured.out.strip() == "", "a usage error must not print a path or a finding"
    assert run.review_packet.read_text() == first, "the existing packet must be untouched"
    assert run.review_sample.read_text() == sample_before


# -- the 1-vs-2 contract, across every subcommand ----------------------------


def _argv_for(command, run, tmp_path):
    """A well-formed invocation of `command` against `run`."""
    if command == "diff-runs":
        return ["diff-runs", "--a", str(run.root), "--b", str(run.root)]
    argv = [command, "--run", str(run.root)]
    if command == "validate":
        argv += ["--stage", "reconcile"]
    if command == "smoke":
        argv += ["--agents", str(_write_roster(tmp_path))]
    if command == "compare-gold":
        argv += ["--gold", str(_write_gold(tmp_path))]
    return argv


# The call each subcommand makes after its arguments are resolved, as
# (module path, attribute), so a test can force an exception out of it.
_EXPLODE_TARGETS = {
    "validate": ("rubrica.cli", "validate_stage"),
    "check-refs": ("rubrica.refs", "check_all"),
    "dedupe-candidates": ("rubrica.cli", "candidate_pairs"),
    "emit": ("rubrica.cli", "emit_run"),
    "smoke": ("rubrica.cli", "smoke_run"),
    "compare-gold": ("rubrica.cli", "compare_run"),
    "sample-for-review": ("rubrica.cli", "sample_run"),
    "diff-runs": ("rubrica.cli", "diff_runs"),
}


@pytest.mark.parametrize("command", sorted(_EXPLODE_TARGETS))
def test_every_subcommand_turns_an_unexpected_exception_into_a_finding(
    tmp_path, capsys, monkeypatch, command
):
    """main() is total, and exit 1 always carries information -- for every subcommand.

    The catch-all handler built its finding from `args.run`, and diff-runs is the
    only subcommand without one: it raised AttributeError *inside the handler*,
    giving exit 1 with zero stdout lines -- verbatim the failure mode cli.py's
    docstring says it closed -- and main() stopped returning an int at all. A
    single-subcommand test could not have caught that, so this is parametrized
    over every subcommand that routes through the handler.

    intake is excluded deliberately: it has its own block with its own catch and
    returns before this one, because it reads paths a person supplied rather than
    artifacts a stage wrote, so its failures are usage errors with no stage to
    send a finding to.
    """
    module_name, attribute = _EXPLODE_TARGETS[command]
    module = __import__(module_name, fromlist=[attribute])

    def explode(*_args, **_kwargs):
        raise RuntimeError("forced through the handler")

    monkeypatch.setattr(module, attribute, explode)

    run = build_state(tmp_path / "run", "emit")
    code = main(_argv_for(command, run, tmp_path))
    captured = capsys.readouterr()
    assert isinstance(code, int), "main must return an int, never raise"
    assert code == 1
    assert [line for line in captured.out.splitlines() if line.strip()], (
        "exit 1 must never mean 'no information'"
    )
    assert "[internal]" in captured.out
    assert "RuntimeError" in captured.out
    assert "forced through the handler" in captured.out
    assert "Traceback" in captured.err


def test_diff_runs_over_a_malformed_scenario_reports_a_finding_not_an_empty_exit_one(
    tmp_path, capsys
):
    """The reproduction, without monkeypatching anything.

    A scenario missing goal_id is a repairable propose-stage defect, and
    stability.goal_cell_claims indexes it directly -- the layer-1 precondition
    refs.py and emit.py both document. It must arrive as a finding line.
    """
    run = build_state(tmp_path / "run", "emit")
    scenarios = read_json(run.scenarios)
    del scenarios["scenarios"][0]["goal_id"]
    write_json(run.scenarios, scenarios)

    code = main(["diff-runs", "--a", str(run.root), "--b", str(run.root)])
    captured = capsys.readouterr()
    assert code == 1
    assert "[internal]" in captured.out
    assert "KeyError" in captured.out
    assert str(run.root) in captured.out, "the line must name the run it is about"


@pytest.mark.parametrize("command", ["smoke", "compare-gold", "sample-for-review"])
def test_a_directory_that_is_not_a_run_is_a_usage_error_and_nothing_is_written(
    tmp_path, capsys, command
):
    """One empty directory, one answer from every tool that writes into a run.

    These three used to disagree: smoke read the manifest first and exited 2,
    while compare-gold and sample-for-review exited 1 -- and compare-gold left a
    measurement/recall.json behind in a directory that is not a run. No stage
    repair produces a manifest, so 2 is the honest answer and nothing belongs on
    disk.

    diff-runs is deliberately not here. It spans two runs and belongs to neither,
    so it writes nothing, reports incomparability as data in its JSON plus a
    stderr warning, and exits 0 -- comparability() already names an unreadable
    manifest as the reason.
    """
    empty = tmp_path / "not-a-run"
    empty.mkdir()
    run = RunPaths(empty)
    assert main(_argv_for(command, run, tmp_path)) == 2, capsys.readouterr().out
    assert list(empty.iterdir()) == [], "nothing may be written into a non-run"


# -- a misconfigured invocation is never a finding about the run -------------


@pytest.mark.parametrize("breakage", ["directory", "non-utf8", "mode-000"])
@pytest.mark.parametrize("flag", ["--agents", "--gold"])
def test_an_unreadable_config_file_is_a_usage_error_not_a_finding(tmp_path, capsys, flag, breakage):
    """A person wrote these files, so there is no stage to send a repair prompt to.

    read_json converts only FileNotFoundError, so a config path pointing at a
    directory, at a non-UTF-8 file, or at a file with mode 000 raised
    IsADirectoryError / UnicodeDecodeError / PermissionError out to cli.py's
    catch-all and was reported as "an artifact in this run is malformed" at exit
    1 -- sending the orchestrator to spend its one repair attempt rewriting stage
    artifacts that were fine.
    """
    if breakage == "mode-000" and os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_state(tmp_path / "run", "emit")
    path = tmp_path / "config-input"
    if breakage == "directory":
        path.mkdir()
    elif breakage == "non-utf8":
        path.write_bytes(b"\xff\xfe\x00\x00{}")
    else:
        path.write_text("{}", encoding="utf-8")
        path.chmod(0o000)

    command = "smoke" if flag == "--agents" else "compare-gold"
    try:
        code = main([command, "--run", str(run.root), flag, str(path)])
    finally:
        if breakage == "mode-000":
            path.chmod(0o644)
    captured = capsys.readouterr()
    assert code == 2, captured.out
    assert captured.out.strip() == "", "a misconfigured harness must not print findings"
    assert "unusable" in captured.err


# -- an unreadable run directory is a filesystem problem, not a stage defect -


# (directory attribute on RunPaths, argv for a subcommand that lists it).
_UNREADABLE_LISTINGS = {
    "instances-validate": ("instances_dir", ["validate", "--stage", "instantiate"]),
    "instances-emit": ("instances_dir", ["emit"]),
    "instances-check-refs": ("instances_dir", ["check-refs"]),
    "claims-validate": ("claims_dir", ["validate", "--stage", "extract"]),
    "claims-check-refs": ("claims_dir", ["check-refs"]),
    "coverage-validate": ("coverage_dir", ["validate", "--stage", "score"]),
    "verdicts-validate": ("verdicts_dir", ["validate", "--stage", "challenge"]),
    "suite-validate": ("suite_dir", ["validate", "--stage", "emit"]),
    "root-validate": ("root", ["validate", "--stage", "intake"]),
    "root-check-refs": ("root", ["check-refs"]),
}


@pytest.mark.parametrize("mode", [0o000, 0o444])
@pytest.mark.parametrize("case", sorted(_UNREADABLE_LISTINGS))
def test_an_unreadable_run_directory_is_exit_2_not_a_finding(tmp_path, capsys, case, mode):
    """The last member of a family: a filesystem problem dressed as a stage defect.

    Two shapes, one cause. `Path.iterdir` and `Path.is_dir`/`is_file` raise
    PermissionError, which was not in cli.py's catch tuple, so `chmod 000` on
    04-instances produced an exit-1 `[internal]` finding advising a repair of an
    artifact that was fine. `Path.glob` does the opposite and *swallows* EACCES,
    so an unreadable 01-claims made `validate --stage extract` announce "produced
    no claims artifact" and made `check-refs` report "no such claim" against a
    correct world model -- a check reporting absence, and naming the wrong
    artifact, because its input was unreadable rather than missing.

    Both modes are exercised because they are different code paths: 0o000 fails
    the listing itself, while 0o444 lists fine and fails on stat'ing a child.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    attribute, command = _UNREADABLE_LISTINGS[case]
    run = build_state(tmp_path / "run", "emit")
    target = getattr(run, attribute)
    target.chmod(mode)
    try:
        code = main([command[0], "--run", str(run.root), *command[1:]])
    finally:
        target.chmod(0o755)
    captured = capsys.readouterr()
    assert code == 2, captured.out
    assert captured.out.strip() == "", "a filesystem problem must not print a finding line"
    assert captured.err.startswith("error: ")


# -- the parser itself reads the schema, and that read can fail --------------


@pytest.mark.parametrize("command", sorted(subcommand_names()))
@pytest.mark.parametrize("breakage", ["missing-dir", "moved-enum"])
def test_an_unbuildable_parser_is_exit_2_on_every_subcommand(
    tmp_path, capsys, monkeypatch, command, breakage
):
    """A schema the parser cannot read is a misconfigured harness, not a finding.

    _build_parser reads the manifest schema for record-stage's --effort choices,
    which happens on *every* invocation and before argv is parsed. The call sat
    outside main's try blocks, so an ArtifactError (schema directory absent) or a
    KeyError (the effort enum moved) escaped main entirely: exit 1 with zero
    stdout lines -- both halves of the exit-code contract broken at once -- and
    main not returning an int at all. Parametrized over every subcommand because
    the failure precedes dispatch: intake, which has its own catch and never
    reaches the shared one, was affected too.
    """
    if breakage == "missing-dir":
        monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(tmp_path / "definitely-not-here"))
    else:
        schema_dir = tmp_path / "schema"
        schema_dir.mkdir()
        schema = read_json(Path(rubrica.validate.__file__).parent / "schema" / "manifest-0.1.json")
        del schema["properties"]["stages"]["additionalProperties"]["properties"]["effort"]
        write_json(schema_dir / "manifest-0.1.json", schema)
        monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(schema_dir))

    run = build_state(tmp_path / "run", "emit")
    argv = _argv_for(command, run, tmp_path) if command in _EXPLODE_TARGETS else [command]
    code = main(argv)
    captured = capsys.readouterr()
    assert isinstance(code, int), "main must return an int, never raise"
    assert code == 2, captured.out
    assert captured.out.strip() == "", "a misconfigured harness must not print a finding line"
    assert captured.err.startswith("error: ")


def test_check_skills_is_clean_on_the_shipped_skills():
    """The whole point of check-skills existing as a subcommand: the
    orchestrator runs it before a run. This is also the test that fails the
    moment a stage is added to paths.STAGES without a prompt.
    """
    assert main(["check-skills"]) == 0


def test_check_skills_reports_findings_at_exit_1_with_lines_on_stdout(tmp_path, capsys):
    """The exit-code contract: a 1 must never mean "no information"."""
    (tmp_path / "rb-extract").mkdir()
    (tmp_path / "rb-extract" / "SKILL.md").write_text(
        '---\nname: rb-extract\n---\n\n## Contract\n\n```toml\nstage = "nope"\n```\n',
        encoding="utf-8",
    )
    assert main(["check-skills", "--skills-dir", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert out.strip(), "exit 1 with an empty stdout is the failure mode the CLI closed"
    assert "[skill]" in out


def test_check_skills_on_a_missing_directory_is_exit_2(tmp_path, capsys):
    """A human-authored path nothing can repair by re-prompting."""
    assert main(["check-skills", "--skills-dir", str(tmp_path / "nope")]) == 2
    assert capsys.readouterr().err.startswith("error: ")


def test_check_skills_on_an_unparseable_skill_is_exit_2(tmp_path, capsys):
    """A SKILL.md with no contract block at all: same ruling as a malformed
    --agents roster. Contrast with the exit-1 test above, where the block parses
    and declares something wrong -- that names a line to edit, so it is a finding.
    """
    (tmp_path / "rb-extract").mkdir()
    (tmp_path / "rb-extract" / "SKILL.md").write_text("# no contract\n", encoding="utf-8")
    assert main(["check-skills", "--skills-dir", str(tmp_path)]) == 2
    assert capsys.readouterr().err.startswith("error: ")
