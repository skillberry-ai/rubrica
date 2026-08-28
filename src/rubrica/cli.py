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

from rubrica import (
    brief,
    reconcile,
    refs,
    rounds,
    seal,
    skills,
    slices,
    summary,
    survey,
    target_brief,
    triage,
)
from rubrica.artifacts import ArtifactError, read_json
from rubrica.dedupe import candidate_pairs
from rubrica.emit import emit_run
from rubrica.errors import UsageError
from rubrica.findings import Finding, format_findings
from rubrica.intake import admit_from_triage, intake
from rubrica.manifest import decide, record_stage, set_limit
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
    ("survey", "inventory a corpus into a catalogue of candidates and mint a run"),
    ("intake", "register inputs and mint a run"),
    ("adopt-projection", "admit a manufactured projection into the catalogue, structurally"),
    ("triage-slices", "partition a catalogue into byte-bounded slices a dispatch can read"),
    ("triage-seal", "assemble the triage record from the staged parts"),
    ("validate", "schema-validate one stage's output"),
    ("check-refs", "cross-artifact and reachability checks"),
    ("reconcile-seal", "assemble the reconcile partials into one world model"),
    ("propose-batches", "partition a round's closable holes into byte-bounded batches"),
    ("propose-seal", "assemble the propose parts and score rulings into the scenario list"),
    ("score-seal", "compute the coverage matrices and compose the round's report"),
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
    ("gate-brief", "compose the existing reports into the human surface at one gate"),
    ("run-summary", "render one run as a single self-contained HTML page"),
    ("target-brief", "render one run's description of the target for its owners"),
    ("set-limit", "change a manifest limit, with the reason recorded in decisions.md"),
)


def _round_number(raw: str) -> int:
    """`--round`'s argparse type: a round is numbered from 1, and 0 is a usage error.

    Checked here rather than left to `RunPaths.batches`/`score_part`, which raise a
    bare `ValueError` for the same input. That `ValueError` is neither `UsageError`
    nor `ArtifactError`, so it falls through to main()'s catch-all and becomes an
    exit-1 `[internal]` finding -- a fabricated stage defect against a run that is
    fine, and the orchestrator spends its one repair attempt re-dispatching a
    prompt whose output was never read. A round number arrives from argv, so a bad
    one is a *usage* error: exit 2.

    The check is duplicated rather than moved, deliberately. RunPaths' bare
    `ValueError` matches its pre-existing `coverage_round`, and one round accessor
    raising a different class from the rest of them would be a worse defect than
    the same rule being stated in two layers -- the outer one for argv, the inner
    one for every caller that is not the CLI.

    argparse turns an ArgumentTypeError into its own usage error, which main()'s
    SystemExit handler already maps to exit 2 with the message on stderr, so this
    needs no branch of its own below.
    """
    try:
        value = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"a round number must be an integer, got {raw!r}"
        ) from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"rounds are numbered from 1, got {value}")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rubrica", description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    # One add_parser call per declared name, so SUBCOMMANDS is the roster and
    # this loop cannot omit or misspell one. Each subcommand's own arguments
    # are added below, keyed off the same dict, because they differ too much
    # (required vs. optional, choices, types) to fold into the tuple itself.
    parsers = {name: subparsers.add_parser(name, help=help_) for name, help_ in SUBCOMMANDS}

    p_survey = parsers["survey"]
    p_survey.add_argument("--corpus", action="append", required=True, metavar="PATH")
    p_survey.add_argument("--runs-dir", required=True)
    p_survey.add_argument("--target-name", required=True)
    p_survey.add_argument("--target-interface", required=True)
    p_survey.add_argument("--objective", required=True, choices=["breadth", "depth"])
    p_survey.add_argument("--objective-note", default=None)
    p_survey.add_argument("--scope-note", default=None)
    p_survey.add_argument("--exclude", action="append", default=[], metavar="GLOB")
    p_survey.add_argument("--max-rounds", type=int, default=2)
    p_survey.add_argument("--max-scenarios", type=int, default=128)
    p_survey.add_argument("--max-candidates", type=int, default=survey.DEFAULT_MAX_CANDIDATES)
    p_survey.add_argument(
        "--max-catalogue-bytes", type=int, default=survey.DEFAULT_MAX_CATALOGUE_BYTES
    )

    p_intake = parsers["intake"]
    # --input (register the files named on argv, minting a fresh manifest from
    # argv) and --run (admit whatever the triage record at an existing survey
    # run already ruled on, minting the manifest from the catalogue instead)
    # are two different ways to reach the same artifact, never both at once.
    p_intake_mode = p_intake.add_mutually_exclusive_group(required=True)
    p_intake_mode.add_argument("--input", action="append", metavar="PATH")
    p_intake_mode.add_argument("--run", metavar="PATH")
    # These five belong to --input only -- --run's equivalents live in the
    # catalogue that survey already wrote, and mixing the two is the shape
    # that produced findings against an unfixable artifact (manifest.json,
    # which no skill wrote and no repair prompt can fix). argparse cannot make
    # a flag conditionally required on which member of a mutually exclusive
    # group was chosen, so none of the five below carry required=True; main()
    # checks both directions explicitly once args.run is known.
    p_input_group = p_intake.add_argument_group("intake --input")
    p_input_group.add_argument("--runs-dir")
    p_input_group.add_argument("--target-name")
    p_input_group.add_argument("--target-interface")
    # A ceiling, not an estimate of the right suite size: the point past which
    # no human reviews the output (128 Harbor packages) and a run costs on the
    # order of $200 at the development run's ~$1.66/scenario across instantiate and
    # challenge. It was 8, which made refs.check_scenarios' guard bind in normal
    # operation and forced a hand-raise on the first real target.
    #
    # default=None rather than 2/128 here: main() needs to tell "the flag was
    # not on argv" apart from "the flag was given its old default value" so it
    # can refuse either one alongside --run, and only substitutes the 2/128
    # default itself, on the --input path, once that distinction is no longer
    # needed.
    p_input_group.add_argument("--max-rounds", type=int, default=None)
    p_input_group.add_argument("--max-scenarios", type=int, default=None)

    p_adopt = parsers["adopt-projection"]
    p_adopt.add_argument("--run", required=True)
    p_adopt.add_argument("--projection", required=True, metavar="ID")
    p_adopt.add_argument("--file", required=True, metavar="PATH")
    p_adopt.add_argument("--check-only", action="store_true")

    p_slices = parsers["triage-slices"]
    p_slices.add_argument("--run", required=True)

    p_triage_seal = parsers["triage-seal"]
    p_triage_seal.add_argument("--run", required=True)

    p_validate = parsers["validate"]
    p_validate.add_argument("--run", required=True)
    p_validate.add_argument("--stage", required=True, choices=list(STAGES))

    p_refs = parsers["check-refs"]
    p_refs.add_argument("--run", required=True)

    p_dedupe = parsers["dedupe-candidates"]
    p_dedupe.add_argument("--run", required=True)

    p_emit = parsers["emit"]
    p_emit.add_argument("--run", required=True)

    p_reconcile_seal = parsers["reconcile-seal"]
    p_reconcile_seal.add_argument("--run", required=True)
    # Passed rather than inferred: an amendment to the frozen goal list costs an
    # explicit orchestrator decision, and a seal that incremented a version it
    # found on disk would let the denominator move without one on the record.
    p_reconcile_seal.add_argument("--denominator-version", type=int, default=1)

    p_batches = parsers["propose-batches"]
    p_batches.add_argument("--run", required=True)
    # Passed rather than inferred, on reconcile-seal's --denominator-version
    # reasoning just above: a command that incremented a round it found on disk
    # would let the loop advance without a decision on the record, and
    # decisions.md is where a round is accounted for. _round_number rather than
    # int, so a round below 1 is exit 2 here instead of an exit-1 [internal]
    # finding out of RunPaths' bare ValueError.
    p_batches.add_argument("--round", type=_round_number, required=True)

    p_propose_seal = parsers["propose-seal"]
    # No --round: the seal is a pure function of every part in every round, so
    # there is no round for a caller to name. That is what lets it run twice per
    # round -- after propose and again after score -- with no way for the second
    # run to disagree with the first.
    p_propose_seal.add_argument("--run", required=True)

    p_score_seal = parsers["score-seal"]
    p_score_seal.add_argument("--run", required=True)
    p_score_seal.add_argument("--round", type=_round_number, required=True)

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

    p_brief = parsers["gate-brief"]
    p_brief.add_argument("--run", required=True)
    # brief.GATES, not a literal: gate_brief already refuses anything outside it,
    # and a second spelling of the gate set is a thing to forget. Gate 0 was added
    # after the other three, which is the update this would have missed.
    p_brief.add_argument("--gate", required=True, type=int, choices=brief.GATES)

    p_summary = parsers["run-summary"]
    p_summary.add_argument("--run", required=True)
    # Defaulted rather than required: the page's home is the run it describes,
    # and an operator rendering one run after another should not have to name a
    # path each time. -o is for the case where the run directory is read-only.
    p_summary.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="PATH",
        help="where to write the page (default: <run>/run-summary.html)",
    )

    p_target = parsers["target-brief"]
    p_target.add_argument("--run", required=True)
    # Defaulted for run-summary's reason -- the page's home is the run it
    # describes -- and `-o` matters more here than there: this page is the one
    # that gets attached to an email, so writing it somewhere an operator can
    # find is the normal case rather than the read-only-run exception.
    p_target.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="PATH",
        help="where to write the page (default: <run>/target-brief.html)",
    )

    p_set_limit = parsers["set-limit"]
    p_set_limit.add_argument("--run", required=True)
    p_set_limit.add_argument("--max-rounds", type=int, default=None)
    p_set_limit.add_argument("--max-scenarios", type=int, default=None)
    p_set_limit.add_argument("--max-scenario-part-bytes", type=int, default=None)
    p_set_limit.add_argument("--reason", required=True)
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

    if args.command == "survey":
        # Its own block and its own catch, exactly like intake's below: it
        # mints a run from arguments a human or orchestrator supplied and reads
        # a corpus, not a run artifact, so every failure here really is a
        # usage error or a misconfigured harness -- there is no stage to send
        # a finding back to.
        try:
            run = survey.survey(
                corpus_roots=[Path(p) for p in args.corpus],
                runs_dir=Path(args.runs_dir),
                target_name=args.target_name,
                target_interface=args.target_interface,
                objective=args.objective,
                objective_note=args.objective_note,
                scope_note=args.scope_note,
                operator_globs=args.exclude,
                max_rounds=args.max_rounds,
                max_scenarios=args.max_scenarios,
                max_candidates=args.max_candidates,
                max_catalogue_bytes=args.max_catalogue_bytes,
            )
        except (UsageError, ArtifactError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return USAGE
        print(run.root)
        return CLEAN

    if args.command == "intake":
        if args.run:
            # Minting a run from an ambiguous parameter set (a human's
            # --target-name alongside a catalogue that already carries one)
            # is refused rather than resolved by precedence -- this is the
            # one constraint argparse could not express, so it is checked
            # here, once, in main() itself. It is a usage error like any
            # other on this path, though, so it shares the same try/except
            # as the admit_from_triage call below rather than escaping
            # uncaught: an uncaught exception here would print nothing to
            # stdout and exit 1, which is indistinguishable from a stage
            # defect and would cost the orchestrator its one repair attempt
            # on a run that was never broken. admit_from_triage's own
            # findings (an inconsistent triage record) are a different
            # failure shape -- exit 1, printed on stdout -- and must not be
            # caught here.
            try:
                illegal = [
                    flag
                    for flag, value in (
                        ("--runs-dir", args.runs_dir),
                        ("--target-name", args.target_name),
                        ("--target-interface", args.target_interface),
                        ("--max-rounds", args.max_rounds),
                        ("--max-scenarios", args.max_scenarios),
                    )
                    if value is not None
                ]
                if illegal:
                    raise UsageError(
                        f"intake --run mints its manifest from the catalogue at {args.run}; "
                        f"{', '.join(illegal)} is illegal alongside --run"
                    )
                run = _run_dir(args.run)
                findings = admit_from_triage(run)
            except (UsageError, ArtifactError, OSError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return USAGE
            if findings:
                print(format_findings(findings))
                return FINDINGS
            print(run.root)
            return CLEAN

        # intake's own block, with its own catch. It reads paths the human
        # supplied rather than artifacts a stage wrote, so every failure here
        # really is a usage error or a misconfigured harness -- there is no
        # stage to send a finding back to. OSError covers the FileNotFoundError
        # for a missing input and the FileExistsError for a run id collision.
        try:
            missing = [
                flag
                for flag, value in (
                    ("--runs-dir", args.runs_dir),
                    ("--target-name", args.target_name),
                    ("--target-interface", args.target_interface),
                )
                if value is None
            ]
            if missing:
                raise UsageError(f"intake --input needs {', '.join(missing)}")
            run = intake(
                inputs=[Path(p) for p in args.input],
                runs_dir=Path(args.runs_dir),
                target_name=args.target_name,
                target_interface=args.target_interface,
                max_rounds=args.max_rounds if args.max_rounds is not None else 2,
                max_scenarios=args.max_scenarios if args.max_scenarios is not None else 128,
            )
        except (UsageError, ArtifactError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return USAGE
        print(run.root)
        return CLEAN

    if args.command == "adopt-projection":
        # Its own block, mirroring intake --run just above: adopt_projection
        # reads a human-supplied --file path as well as the run's own
        # artifacts, so a raised UsageError -- an unreadable file, an unknown
        # projection_id, a missing catalogue or triage record -- is a usage
        # error like intake --run's illegal-flag check, sharing its catch
        # rather than escaping uncaught. A non-empty return is the other
        # failure shape: check_acceptance's findings, repairable by
        # manufacturing the file again, so it is handled after the try like
        # admit_from_triage's findings are.
        try:
            run = _run_dir(args.run)
            findings = triage.adopt_projection(
                run,
                projection_id=args.projection,
                source=Path(args.file),
                check_only=args.check_only,
            )
        except (UsageError, ArtifactError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return USAGE
        if findings:
            print(format_findings(findings))
            return FINDINGS
        print(triage.ACCEPTANCE_PASS_MESSAGE)
        return CLEAN

    try:
        if args.command == "triage-slices":
            # Modeled on validate/check-refs just below, not on survey above:
            # this is a code stage over an existing run's artifact, not a
            # minter of one. write_slices reports no findings -- it either
            # produces a plan or it does not -- so this block has no _report
            # call and cannot exit FINDINGS. Its only two exits are CLEAN
            # here and USAGE via the shared except below: an unreadable
            # catalogue, no candidates, a candidate over cap, or -- guarded
            # inside write_slices itself, before any bare dict[...] read of
            # untrusted catalogue content -- a catalogue that is not a JSON
            # object, one missing run_id, request, policy, or excluded, an
            # excluded that is present but is not an array, or a candidate
            # that is not an object carrying a string candidate_id. Those
            # guards are load-bearing, not decorative: a bare KeyError
            # from any of those falls through to the generic `except
            # Exception` below this try block, which fabricates a `1`
            # blaming this stage for a defect that actually lives in the
            # catalogue -- exactly wrong, since a malformed catalogue cannot
            # be fixed by the one retry a `1` earns it, and this repository
            # has shipped both that failure shape and a `1` with empty
            # stdout before, from an exit path that assumed a case it did
            # not have.
            run = _run_dir(args.run)
            _, plan = slices.write_slices(run)
            for s in plan:
                size = run.slice_shard(s.id).stat().st_size
                print(f"{s.id}  {size}  {len(s.candidate_ids)}  {s.label}")
            return CLEAN

        if args.command == "triage-seal":
            # seal.seal raises nothing at all -- every failure mode, including
            # an unreadable run artifact, comes back as a Finding -- so this
            # block's only two exits are CLEAN/FINDINGS via _report below and
            # USAGE via the shared except, for the same reason triage-slices'
            # block above has none of its own: an unsafe run root or the like,
            # never a stage defect the seal itself could have reported.
            run = _run_dir(args.run)
            path, findings = seal.seal(run)
            if path is not None:
                print(path)
            return _report(findings)

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

        if args.command == "reconcile-seal":
            run = _run_dir(args.run)
            world, findings = reconcile.seal(run, denominator_version=args.denominator_version)
            if world is not None:
                print(world)
            return _report(findings)

        # The loop's three code steps. No catch of their own, on purpose: every
        # artifact they refuse to trust divides by WHO WROTE IT, and rounds.py
        # already draws that line for them. manifest.json, 01-world-model.json,
        # 02-scenarios.json and 03-coverage/round-N.json are code output, so a
        # malformed one raises the UsageError the shared except below maps to
        # exit 2 -- no re-dispatch of any prompt could repair it. The propose
        # parts and the score parts are model output, so a malformed one comes
        # back as a Finding naming that part: exit 1, one line each, repairable
        # by re-dispatching that one member. Catching anything here would
        # collapse the two.
        if args.command == "propose-batches":
            run = _run_dir(args.run)
            path = rounds.write_batches(run, round_n=args.round)
            if path is None:
                # Exit 0 with a message, not a finding: no closable hole is a
                # fact about the run, and the orchestrator branches on it to
                # stop the loop rather than to repair a stage. A finding here
                # would send it to re-dispatch a propose member that has
                # nothing wrong with it and no batch to read.
                print("no closable holes: there is no propose round to dispatch")
                return CLEAN
            print(path)
            return CLEAN

        if args.command == "propose-seal":
            run = _run_dir(args.run)
            path, findings = rounds.seal_scenarios(run)
            # `path is None` is two different states here and neither is an
            # error: findings were reported and nothing was written, or no
            # propose part exists yet at all. seal_scenarios' docstring keeps
            # them apart; this print just declines to name a file that was
            # never written.
            if path is not None:
                print(path)
            return _report(findings)

        if args.command == "score-seal":
            run = _run_dir(args.run)
            path, findings = rounds.seal_score(run, round_n=args.round)
            if path is not None:
                print(path)
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

        if args.command == "gate-brief":
            # Same ruling as claim-utilisation just above, for the same reason:
            # this composes existing reports rather than checking anything, so
            # it is never the thing that turns a readable run into exit 1.
            # --gate's argparse choices are brief.GATES, so anything outside the
            # set is already rejected before this line is reached, on the same
            # SystemExit(2) path every other bad argument takes.
            print(brief.gate_brief(_run_dir(args.run), args.gate))
            return CLEAN

        if args.command == "run-summary":
            # The same ruling as claim-utilisation and gate-brief above: this
            # composes what the run already contains, so it is never the thing
            # that turns a readable run into exit 1. Every artifact the page
            # reads is optional and an absent one renders as a stated absence,
            # so a run that stopped at extract is a page saying so, not a
            # finding -- which is why there is no _report call on this path.
            run = _run_dir(args.run)
            destination = Path(args.output) if args.output else run.root / "run-summary.html"
            # No local catch: an OSError from write_text -- a read-only
            # destination, a missing parent -- is the filesystem refusing, and
            # the shared handler below already maps that to USAGE. Catching it
            # here to return FINDINGS would be the 2-as-1 inversion this
            # module's docstring says it closed.
            destination.write_text(summary.run_summary(run), encoding="utf-8")
            # The path, not the page: the page is a file an operator opens, and
            # 300KB of markup on a terminal is not a report.
            print(destination)
            return CLEAN

        if args.command == "target-brief":
            # A report, the same ruling as claim-utilisation, gate-brief and
            # run-summary: it composes what the run already contains and is never
            # the thing that turns a readable run into exit 1. It goes further than
            # claim-utilisation and gate-brief, deliberately: an unreadable
            # 01-claims/ exits 2 out of both, because an empty utilisation table is
            # the one reading a human at gate 1 must never be handed. run-summary
            # already exits 0 here, measured, so it is not the foil this contrast
            # wants -- but this page has no number to be quietly wrong, so it
            # banners the missing citations and still exits 0.
            run = _run_dir(args.run)
            destination = Path(args.output) if args.output else run.root / "target-brief.html"
            # No local catch, for run-summary's reason: an OSError from write_text
            # is the filesystem refusing, and the shared handler below already
            # maps that to USAGE. Catching it here to return FINDINGS would be the
            # 2-as-1 inversion this module's docstring says it closed.
            destination.write_text(target_brief.page(run), encoding="utf-8")
            print(destination)
            return CLEAN

        if args.command == "set-limit":
            run = _run_dir(args.run)
            # Its own UsageError catch, matching decide and record-stage just
            # above: --max-rounds, --max-scenarios, --max-scenario-part-bytes and
            # --reason are the orchestrator's own arguments, not a stage's output,
            # so a bad one is a misconfigured harness rather than a repairable
            # stage defect.
            try:
                set_limit(
                    run,
                    max_rounds=args.max_rounds,
                    max_scenarios=args.max_scenarios,
                    max_scenario_part_bytes=args.max_scenario_part_bytes,
                    reason=args.reason,
                )
            except (UsageError, OSError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return USAGE
            print(run.manifest)
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
