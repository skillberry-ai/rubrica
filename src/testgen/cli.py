"""Command-line surface for the deterministic pipeline components.

Exit codes are part of the contract the orchestrator skill branches on:

    0  clean
    1  findings, printed one per line on stdout
    2  usage error, or a run directory that could not be read

The distinction between 1 and 2 matters. A 1 means the stage produced a bad
artifact and is worth one repair attempt; a 2 means the harness itself is
misconfigured and repeating the stage cannot help.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from testgen import refs
from testgen.artifacts import ArtifactError, read_json
from testgen.dedupe import candidate_pairs
from testgen.findings import format_findings
from testgen.intake import intake
from testgen.paths import STAGES, RunPaths
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

    try:
        if args.command == "intake":
            run = intake(
                inputs=[Path(p) for p in args.input],
                runs_dir=Path(args.runs_dir),
                target_name=args.target_name,
                target_interface=args.target_interface,
                max_rounds=args.max_rounds,
                max_scenarios=args.max_scenarios,
            )
            print(run.root)
            return CLEAN

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
    except (FileNotFoundError, FileExistsError, ArtifactError, UnknownStage, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return USAGE

    parser.print_usage(sys.stderr)
    return USAGE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
