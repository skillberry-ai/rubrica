"""Command-line surface for the deterministic pipeline components.

Exit codes are part of the contract the orchestrator skill branches on:

    0  clean
    1  findings, printed one per line on stdout
    2  usage error, or a run directory that could not be read

The distinction between 1 and 2 matters. A 1 means the stage produced a bad
artifact and is worth one repair attempt; a 2 means the harness itself is
misconfigured and repeating the stage cannot help.

Two failure modes of that contract are closed here.

**A stage defect must never surface as 2.** The catch below is deliberately
narrow. It used to include a bare `ValueError`, which existed for intake's own
argument checks but swallowed every `ValueError` raised anywhere downstream --
a coverage document with `pct: "half"` was reported as a misconfigured harness
when it is a repairable score-stage defect, and `UnsafeSegment` (a `ValueError`
subclass) could become a 2 from any call site that had not been individually
hardened. intake raises `UsageError` for its own usage problems instead.

**A 1 must never mean "no information".** An unexpected exception from a
checking layer is a layer-1 precondition violation (refs.py and emit.py both
document it): a malformed artifact indexed directly. That is a repairable stage
defect, so it exits 1 -- but an exception printed nowhere left stdout empty, and
an orchestrator branching on 1 then retried blind with no findings to act on. It
is turned into a finding-shaped line instead. The traceback goes to stderr,
where a human can read it and a machine parsing stdout is unaffected.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import traceback
from pathlib import Path

from testgen import refs
from testgen.artifacts import ArtifactError, read_json
from testgen.dedupe import candidate_pairs
from testgen.emit import emit_run
from testgen.errors import UsageError
from testgen.findings import Finding, format_findings
from testgen.intake import intake
from testgen.paths import STAGES, RunPaths
from testgen.smoke import load_agents, preflight, smoke_run
from testgen.validate import UnknownStage, validate_stage

CLEAN, FINDINGS, USAGE = 0, 1, 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="testgen", description=__doc__)
    subparsers = parser.add_subparsers(dest="command")

    p_intake = subparsers.add_parser("intake", help="register inputs and mint a run")
    p_intake.add_argument("--input", action="append", required=True, metavar="PATH")
    p_intake.add_argument("--runs-dir", required=True)
    p_intake.add_argument("--target-name", required=True)
    p_intake.add_argument("--target-interface", required=True)
    p_intake.add_argument("--max-rounds", type=int, default=2)
    p_intake.add_argument("--max-scenarios", type=int, default=8)

    p_validate = subparsers.add_parser("validate", help="schema-validate one stage's output")
    p_validate.add_argument("--run", required=True)
    p_validate.add_argument("--stage", required=True, choices=list(STAGES))

    p_refs = subparsers.add_parser("check-refs", help="cross-artifact and reachability checks")
    p_refs.add_argument("--run", required=True)

    p_dedupe = subparsers.add_parser(
        "dedupe-candidates", help="propose candidate duplicate scenario pairs as JSON"
    )
    p_dedupe.add_argument("--run", required=True)

    p_emit = subparsers.add_parser("emit", help="compile accepted instances into Harbor packages")
    p_emit.add_argument("--run", required=True)

    p_smoke = subparsers.add_parser("smoke", help="run the emitted suite against the agent roster")
    p_smoke.add_argument("--run", required=True)
    p_smoke.add_argument("--agents", required=True, metavar="PATH")
    return parser


def _run_dir(raw: str) -> RunPaths:
    root = Path(raw)
    if not root.is_dir():
        raise FileNotFoundError(f"run directory does not exist: {root}")
    return RunPaths(root)


def _report(findings) -> int:
    if not findings:
        return CLEAN
    print(format_findings(findings))
    return FINDINGS


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    # parse_known_args rather than parse_args so an unknown subcommand becomes
    # our exit code 2 instead of argparse's SystemExit(2) escaping the caller.
    try:
        args, extra = parser.parse_known_args(argv)
    except SystemExit as exc:
        # argparse raises SystemExit(0) after printing --help and SystemExit(2)
        # for a usage error. Collapsing both to USAGE told the orchestrator the
        # harness was misconfigured every time someone asked for help. The
        # comparison is deliberately `== 0` rather than an int cast: exc.code
        # can in principle be None or a string, neither of which argparse ever
        # uses for a successful --help, and both compare False without raising.
        return CLEAN if exc.code == 0 else USAGE
    if args.command is None or extra:
        parser.print_usage(sys.stderr)
        return USAGE

    if args.command == "intake":
        # intake's own block, with its own catch. It reads paths the human
        # supplied rather than artifacts a stage wrote, so every failure here
        # really is a usage error or a misconfigured harness -- there is no
        # stage to send a finding back to. OSError covers the FileNotFoundError
        # for a missing input and the FileExistsError for a run id collision.
        try:
            run = intake(
                inputs=[Path(p) for p in args.input],
                runs_dir=Path(args.runs_dir),
                target_name=args.target_name,
                target_interface=args.target_interface,
                max_rounds=args.max_rounds,
                max_scenarios=args.max_scenarios,
            )
        except (UsageError, ArtifactError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return USAGE
        print(run.root)
        return CLEAN

    try:
        if args.command == "validate":
            return _report(validate_stage(_run_dir(args.run), args.stage))

        if args.command == "check-refs":
            return _report(refs.check_all(_run_dir(args.run)))

        if args.command == "dedupe-candidates":
            run = _run_dir(args.run)
            scenarios = read_json(run.scenarios).get("scenarios", [])
            print(
                json.dumps(
                    [dataclasses.asdict(c) for c in candidate_pairs(scenarios)],
                    indent=2,
                    sort_keys=True,
                )
            )
            return CLEAN

        if args.command == "emit":
            run = _run_dir(args.run)
            emitted, findings = emit_run(run)
            for sid in emitted:
                print(run.task_dir(sid))
            return _report(findings)

        if args.command == "smoke":
            run = _run_dir(args.run)
            # An inner catch, because UsageError is a ValueError and the outer
            # narrow catch deliberately does not include ValueError -- without
            # this a typo'd roster path would reach `except Exception` and be
            # reported as a malformed artifact at exit 1.
            try:
                specs = preflight(load_agents(Path(args.agents)))
            except UsageError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return USAGE
            report, findings = smoke_run(run, specs)
            if report is not None:
                print(run.report)
            return _report(findings)
    except (FileNotFoundError, ArtifactError, UnknownStage) as exc:
        # A run directory that cannot be read, an artifact that is absent or is
        # not JSON at all, an unknown stage name: the harness was pointed at
        # something it cannot work with, and repeating the stage cannot help.
        print(f"error: {exc}", file=sys.stderr)
        return USAGE
    except Exception as exc:
        # Anything else is a malformed artifact indexed directly by a checking
        # layer, in violation of the layer-1 precondition both refs.py and
        # emit.py document -- a repairable stage defect. Exit 1, with a
        # finding-shaped line so the orchestrator has something to act on
        # instead of a bare 1 and an empty stdout.
        traceback.print_exc(file=sys.stderr)
        return _report(
            [
                Finding(
                    Path(args.run),
                    "internal",
                    "",
                    f"{args.command} raised {type(exc).__name__}: {exc}. An artifact in this run "
                    "is malformed in a way layer 1 must reject first; run `testgen validate "
                    "--stage <stage>` for the stages this run has reached and repair the "
                    "artifact it names",
                )
            ]
        )

    parser.print_usage(sys.stderr)
    return USAGE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
