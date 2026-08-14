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
hardened. intake raises `UsageError` for its own usage problems instead, and
that named subclass -- not `ValueError` -- is what the catch names.

**And the mirror of it: a filesystem problem must never surface as 1.** The
same catch names `OSError`, not just its `FileNotFoundError` subclass. A run
directory that cannot be *read* is the harness pointed at something it cannot
work with, exactly like one that does not exist; reporting it as a stage defect
sent the orchestrator to spend its one repair attempt re-running a stage whose
output was fine. Malformed content still reaches the handler at the bottom and
still exits 1: content errors are `ArtifactError`, `KeyError`, `UnsafeSegment`,
never `OSError`.

**A 1 must never mean "no information".** An unexpected exception from a
checking layer is a layer-1 precondition violation (refs.py and emit.py both
document it): a malformed artifact indexed directly. That is a repairable stage
defect, so it exits 1 -- but an exception printed nowhere left stdout empty, and
an orchestrator branching on 1 then retried blind with no findings to act on. It
is turned into a finding-shaped line instead. The traceback goes to stderr,
where a human can read it and a machine parsing stdout is unaffected.

**Both invariants also have to hold before any subcommand runs.** Building the
parser is not free: `record-stage`'s `--effort` choices are read out of the
active manifest schema so the CLI cannot accept an effort the schema rejects.
That read happens for *every* invocation, `intake` included, and it happens
before argv has even been parsed -- so a typo'd `RUBRICA_SCHEMA_DIR`, a
non-editable install missing its package data, or a schema edit that moves
`properties.stages.additionalProperties.properties.effort.enum` used to let an
`ArtifactError` or a `KeyError` escape `main` entirely: exit 1, empty stdout,
and `main` not returning an int at all. Nothing about parser construction reads
a run artifact, so no failure of it can be a stage defect: it is exit 2 on the
same stderr channel as every other usage error.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import traceback
from pathlib import Path

from rubrica import refs, skills
from rubrica.artifacts import ArtifactError, read_json
from rubrica.dedupe import candidate_pairs
from rubrica.emit import emit_run
from rubrica.errors import UsageError
from rubrica.findings import Finding, format_findings
from rubrica.intake import intake
from rubrica.manifest import decide, record_stage
from rubrica.paths import STAGES, RunPaths
from rubrica.recall import compare_run, render
from rubrica.review import DEFAULT_SAMPLE_SIZE, sample_run
from rubrica.smoke import load_agents, preflight, smoke_run
from rubrica.stability import diff_runs
from rubrica.utilisation import claim_utilisation
from rubrica.validate import UnknownStage, manifest_stage_efforts, validate_stage

CLEAN, FINDINGS, USAGE = 0, 1, 2

# Every `rubrica` subcommand, as (name, help). The one declared source both
# _build_parser and subcommand_names() read: _build_parser iterates this to
# create each subparser (then adds that subcommand's own arguments to the
# result), and subcommand_names() just reads off the names. A hand-kept
# second list here is exactly how skills.check_contract's validation of a
# SKILL.md's `invokes` list against the real CLI would go stale the first
# time a subcommand was added.
SUBCOMMANDS: tuple[tuple[str, str], ...] = (
    ("intake", "register inputs and mint a run"),
    ("validate", "schema-validate one stage's output"),
    ("check-refs", "cross-artifact and reachability checks"),
    ("dedupe-candidates", "propose candidate duplicate scenario pairs as JSON"),
    ("emit", "compile accepted instances into Harbor packages"),
    ("smoke", "run the emitted suite against the agent roster"),
    ("compare-gold", "recall and novelty against the authored bench tasks"),
    ("diff-runs", "per-stage stability across two runs"),
    ("sample-for-review", "write a stratified review packet for the emitted suite"),
    ("check-skills", "check every skill's contract against the code it names"),
    ("record-stage", "record a stage's model, effort, and skill hash in the manifest"),
    ("decide", "append one orchestrator decision to the run's decisions.md"),
    ("claim-utilisation", "per-artifact share of claims the world model cites"),
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rubrica", description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    # One add_parser call per declared name, so SUBCOMMANDS is the roster and
    # this loop cannot omit or misspell one. Each subcommand's own arguments
    # are added below, keyed off the same dict, because they differ too much
    # (required vs. optional, choices, types) to fold into the tuple itself.
    parsers = {name: subparsers.add_parser(name, help=help_) for name, help_ in SUBCOMMANDS}

    p_intake = parsers["intake"]
    p_intake.add_argument("--input", action="append", required=True, metavar="PATH")
    p_intake.add_argument("--runs-dir", required=True)
    p_intake.add_argument("--target-name", required=True)
    p_intake.add_argument("--target-interface", required=True)
    p_intake.add_argument("--max-rounds", type=int, default=2)
    # A ceiling, not an estimate of the right suite size: the point past which
    # no human reviews the output (128 Harbor packages) and a run costs on the
    # order of $200 at the parsec run's ~$1.66/scenario across instantiate and
    # challenge. It was 8, which made refs.check_scenarios' guard bind in normal
    # operation and forced a hand-raise on the first real target.
    p_intake.add_argument("--max-scenarios", type=int, default=128)

    p_validate = parsers["validate"]
    p_validate.add_argument("--run", required=True)
    p_validate.add_argument("--stage", required=True, choices=list(STAGES))

    p_refs = parsers["check-refs"]
    p_refs.add_argument("--run", required=True)

    p_dedupe = parsers["dedupe-candidates"]
    p_dedupe.add_argument("--run", required=True)

    p_emit = parsers["emit"]
    p_emit.add_argument("--run", required=True)

    p_smoke = parsers["smoke"]
    p_smoke.add_argument("--run", required=True)
    p_smoke.add_argument("--agents", required=True, metavar="PATH")

    p_gold = parsers["compare-gold"]
    p_gold.add_argument("--run", required=True)
    p_gold.add_argument("--gold", required=True, metavar="PATH")

    p_diff = parsers["diff-runs"]
    p_diff.add_argument("--a", required=True)
    p_diff.add_argument("--b", required=True)

    p_review = parsers["sample-for-review"]
    p_review.add_argument("--run", required=True)
    p_review.add_argument("--size", type=int, default=DEFAULT_SAMPLE_SIZE)

    p_skills = parsers["check-skills"]
    p_skills.add_argument("--skills-dir", default=None, metavar="PATH")

    p_record = parsers["record-stage"]
    p_record.add_argument("--run", required=True)
    p_record.add_argument("--stage", required=True, choices=list(STAGES))
    p_record.add_argument("--model", required=True)
    p_record.add_argument("--effort", required=True, choices=list(manifest_stage_efforts()))
    p_record.add_argument("--skill", required=True, metavar="PATH")

    p_decide = parsers["decide"]
    p_decide.add_argument("--run", required=True)
    p_decide.add_argument("--note", required=True)

    p_utilisation = parsers["claim-utilisation"]
    p_utilisation.add_argument("--run", required=True)
    return parser


def subcommand_names() -> tuple[str, ...]:
    """Every `rubrica` subcommand, as argparse accepts it.

    skills.check_contract validates each skill's `invokes` list against this,
    so a SKILL.md telling a model to run `rubrica check_refs` fails in CI
    rather than at run time. Reads SUBCOMMANDS -- the same tuple _build_parser
    iterates over -- rather than a second list, so the parser and this check
    cannot disagree.
    """
    return tuple(name for name, _ in SUBCOMMANDS)


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
    # Inside a try, because _build_parser reads the active manifest schema off
    # disk for record-stage's --effort choices. The catch is wider than the one
    # around the subcommand bodies below on purpose, and it is still narrow in
    # the way that matters: no run artifact is read here, so nothing this can
    # catch is a repairable stage defect. ArtifactError is the schema file
    # missing or not being JSON; KeyError and TypeError are a schema whose
    # effort enum has moved or is no longer a list of strings; OSError is the
    # file being unreadable rather than absent.
    try:
        parser = _build_parser()
    except (ArtifactError, OSError, KeyError, TypeError) as exc:
        print(
            f"error: cannot build the command-line parser: {type(exc).__name__}: {exc}. "
            "record-stage's --effort choices are read from the manifest schema, so every "
            "subcommand needs it; check RUBRICA_SCHEMA_DIR and that the package's schema/ "
            "data is installed",
            file=sys.stderr,
        )
        return USAGE
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
            # An inner catch so the failure is handled next to the call that
            # can produce it. The shared catch below now also maps UsageError to
            # exit 2, so this is a localisation rather than the only thing
            # standing between a typo'd roster path and a fabricated exit-1
            # finding -- which is what it was when that catch excluded every
            # ValueError, UsageError included.
            try:
                specs = preflight(load_agents(Path(args.agents)))
            except UsageError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return USAGE
            report, findings = smoke_run(run, specs)
            if report is not None:
                print(run.report)
            return _report(findings)

        if args.command == "compare-gold":
            run = _run_dir(args.run)
            try:
                report, findings = compare_run(run, Path(args.gold))
            except UsageError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return USAGE
            # The path, not the document. Exit 1 means finding lines on stdout,
            # and a 25-line markdown report printed to the same stream ahead of
            # them leaves an orchestrator parsing stdout with prose it must
            # somehow tell from findings -- the hazard diff-runs names and avoids.
            # compare_run has already written the rendering to measurement/,
            # so `smoke`'s discipline applies: print where it is. The prose goes
            # to stderr, where a human still sees it and no parser is affected.
            print(run.recall_md)
            print(render(report), file=sys.stderr)
            return _report(findings)

        if args.command == "sample-for-review":
            run = _run_dir(args.run)
            # Same shape as smoke's inner catch above, and the same reason:
            # --size 0 is a usage error, handled beside the call that raises it.
            # The shared catch below is the backstop.
            try:
                sampled, findings = sample_run(run, args.size)
            except UsageError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return USAGE
            if sampled:
                print(run.review_packet)
            return _report(findings)

        if args.command == "claim-utilisation":
            # A report, not a gate: always CLEAN on a readable run. The finding
            # half lives in check-refs, so this command never returns 1 and an
            # orchestrator reading its exit code cannot mistake data for a defect.
            print(json.dumps(claim_utilisation(_run_dir(args.run)), indent=2, sort_keys=True))
            return CLEAN

        if args.command == "diff-runs":
            report = diff_runs(_run_dir(args.a), _run_dir(args.b))
            print(json.dumps(report, indent=2, sort_keys=True))
            if not report["comparable"]:
                # stderr, not a finding. Exit 1 means finding lines on stdout, and
                # a JSON document mixed with them would break the orchestrator's
                # line parser -- so incomparability is data in the JSON plus a
                # warning a human sees.
                for reason in report["incomparable_reasons"]:
                    print(f"warning: {reason}", file=sys.stderr)
            return CLEAN

        if args.command == "check-skills":
            # Its own UsageError catch, for the same reason smoke and
            # sample-for-review have one. A SKILL.md that cannot be parsed at
            # all is human-authored and unrepairable by re-prompting, so it is
            # exit 2 -- and unlike the other two, this one is not about a run
            # directory at all, so keeping it local is what documents that.
            try:
                findings = skills.check_all(args.skills_dir)
            except UsageError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return USAGE
            return _report(findings)

        if args.command == "record-stage":
            run = _run_dir(args.run)
            # Its own UsageError catch: these arguments come from the
            # orchestrator's own invocation, not from a stage's output, so a bad
            # one is a misconfigured harness and no repair prompt helps.
            try:
                record_stage(
                    run,
                    stage=args.stage,
                    model=args.model,
                    effort=args.effort,
                    skill=Path(args.skill),
                )
            except (UsageError, OSError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return USAGE
            print(run.manifest)
            return CLEAN

        if args.command == "decide":
            run = _run_dir(args.run)
            # (UsageError, OSError), matching record-stage above -- not just
            # UsageError. decisions.md being a directory, or the run directory
            # being read-only with no decisions.md yet, raises a bare OSError
            # out of append_decision's open(); without OSError here that falls
            # through to the catch-all below and becomes exit 1 with a
            # fabricated "internal" finding, the same misreading
            # smoke.load_agents' docstring already names for --agents: a
            # harness-level filesystem problem told the orchestrator a stage
            # was broken and sent it to spend its one repair attempt re-running
            # a stage that was fine.
            try:
                decide(run, args.note)
            except (UsageError, OSError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return USAGE
            print(run.decisions)
            return CLEAN
    except (OSError, UsageError, ArtifactError, UnknownStage) as exc:
        # A run directory that cannot be read, an artifact that is absent or is
        # not JSON at all, an unknown stage name: the harness was pointed at
        # something it cannot work with, and repeating the stage cannot help.
        #
        # OSError rather than just its FileNotFoundError subclass, and UsageError
        # alongside it, close the last member of a family this build kept
        # rediscovering: a *filesystem* problem on the run directory reported as
        # a repairable stage defect. `chmod 000` on 04-instances raised
        # PermissionError out of paths.scenario_ids_with_instances and became an
        # exit-1 [internal] finding telling the orchestrator to repair an
        # artifact that was fine. paths.list_dir now converts the listing shapes
        # into UsageError with the directory named (following skills._skill_dirs),
        # and OSError here is the backstop for the rest: `run.manifest.is_file()`
        # on a run root with mode 000 raises PermissionError from a plain stat,
        # and there are dozens of such stats no per-call-site wrapper would ever
        # cover. Nothing about this widens the 1-vs-2 line in the wrong
        # direction: a stage defect is malformed *content* -- ArtifactError,
        # KeyError, UnsafeSegment -- and reaches the handler below. An OSError is
        # the filesystem refusing, which no repair prompt can fix.
        print(f"error: {exc}", file=sys.stderr)
        return USAGE
    except Exception as exc:
        # Anything else is a malformed artifact indexed directly by a checking
        # layer, in violation of the layer-1 precondition both refs.py and
        # emit.py document -- a repairable stage defect. Exit 1, with a
        # finding-shaped line so the orchestrator has something to act on
        # instead of a bare 1 and an empty stdout.
        traceback.print_exc(file=sys.stderr)
        # `args.run` is not universal: diff-runs is the only subcommand without
        # it, and `Path(args.run)` raised AttributeError *inside this handler* --
        # exit 1 with an empty stdout, verbatim the failure mode this module's
        # docstring says it closed, and main() stopped returning an int at all.
        # diff-runs' run-shaped argument is --a, and "." is the last resort so
        # this line can never be the thing that fails.
        return _report(
            [
                Finding(
                    Path(getattr(args, "run", None) or getattr(args, "a", ".")),
                    "internal",
                    "",
                    f"{args.command} raised {type(exc).__name__}: {exc}. An artifact in this run "
                    "is malformed in a way layer 1 must reject first; run `rubrica validate "
                    "--stage <stage>` for the stages this run has reached and repair the "
                    "artifact it names",
                )
            ]
        )

    parser.print_usage(sys.stderr)
    return USAGE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
