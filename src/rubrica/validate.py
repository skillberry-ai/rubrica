"""JSON Schema validation of run artifacts: layer 1 of three.

Layer 1 checks shape only. Cross-artifact references, seed-pointer
reachability, and world-model invariants are layer 2 and live in refs.py;
layer 3 is the smoke gate. A stage's output must clear layer 1 before the
orchestrator dispatches the next stage (design spec section 5).

Findings are returned, never raised: the orchestrator's contract is one
bounded repair attempt with the findings appended to the stage prompt, which
needs the full list rather than the first failure.

**The schemas anchor patterns with `\\A` and `\\Z`, not `^` and `$`.** JSON
Schema specifies ECMA-262 regexes, where those escapes are not defined, so
these schemas are portable only to a Python validator. That is a deliberate
trade: Python's `re` lets `$` match immediately before a trailing newline, so
`"scn-001\\n"` would satisfy every id pattern and then raise UnsafeSegment when
joined into a path -- surfacing a repairable stage defect as exit 2, a
misconfigured harness. Nothing outside this package validates these artifacts.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path

from jsonschema import Draft202012Validator

from rubrica.artifacts import ArtifactError, read_json
from rubrica.findings import Finding
from rubrica.paths import STAGES, RunPaths, list_json

# Artifact kind -> schema filename.
ARTIFACT_SCHEMAS: dict[str, str] = {
    "manifest": "manifest-0.1.json",
    "claims": "claims-0.1.json",
    "world-model": "world-model-0.1.json",
    "scenarios": "scenarios-0.1.json",
    "coverage": "coverage-0.1.json",
    "seed": "seed-0.1.json",
    "expected": "expected-0.1.json",
    "verdict": "verdict-0.1.json",
    "suite-expected": "suite-expected-0.1.json",
    "report": "report-0.1.json",
    "catalogue": "catalogue-0.1.json",
    "triage": "triage-0.1.json",
    # Config kinds. Human-authored inputs, not stage outputs, so they are
    # deliberately absent from STAGE_ARTIFACTS: no stage produces them and
    # `validate --stage X` must never look for them.
    "agents": "agents-0.1.json",
    "gold": "gold-0.1.json",
}

# Config artifact kinds: human-authored, never joined into a run path, never
# produced by a stage. The one definition of this set -- tests that need to
# know which kinds are config rather than stage output import it rather than
# restating the literal, which is how {"agents", "gold"} drifted out of sync
# with ARTIFACT_SCHEMAS before this constant existed.
CONFIG_KINDS: frozenset[str] = frozenset({"agents", "gold"})

# Which artifact kinds each stage must produce. Every stage now has a real
# gate: a stage that produced none of its required kinds fails layer 1
# rather than passing trivially, so the orchestrator never dispatches the
# next stage against an empty or missing output.
STAGE_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "survey": ("catalogue",),
    "triage": ("triage",),
    "intake": ("manifest",),
    "extract": ("claims",),
    "reconcile": ("world-model",),
    "propose": ("scenarios",),
    "score": ("coverage",),
    "instantiate": ("seed", "expected"),
    "challenge": ("verdict",),
    "emit": ("suite-expected",),
    "smoke": ("report",),
}


class UnknownStage(ValueError):
    """Raised for a stage name that is not in paths.STAGES."""


def schema_dir() -> Path:
    """Directory holding the artifact schemas.

    The schemas ship as package data beside this module rather than at the
    repository root, so an installed (non-editable) copy can validate. Walking
    up to the repo root only ever worked for an editable install.

    Overridable via RUBRICA_SCHEMA_DIR so a caller can validate against a
    candidate schema set without reinstalling the package.
    """
    override = os.environ.get("RUBRICA_SCHEMA_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "schema"


@functools.cache
def _manifest_stage_efforts(schema_root: Path) -> tuple[str, ...]:
    """The cached half of manifest_stage_efforts, keyed on schema_root.

    Same reason _validator_for below takes schema_root as a cache key rather
    than reading schema_dir() inside: a plain zero-argument @functools.cache
    would return the first schema it ever saw for the life of the process, so
    a test overriding RUBRICA_SCHEMA_DIR after some earlier call (parser
    construction happens on every CLI invocation, so there always is an
    earlier call) would silently get the old effort list back -- correct only
    as long as every caller remembered to `.cache_clear()` first. Keying on
    the root makes that scaffolding unnecessary rather than merely documented.
    """
    schema = read_json(schema_root / ARTIFACT_SCHEMAS["manifest"])
    stage = schema["properties"]["stages"]["additionalProperties"]
    return tuple(stage["properties"]["effort"]["enum"])


def manifest_stage_efforts() -> tuple[str, ...]:
    """The effort levels manifest.stages accepts, read out of the active schema.

    `record-stage` uses this as its argparse choices, so the CLI cannot accept
    an effort the manifest schema will reject -- and there is no second copy of
    the enum to keep in step. Reads the *active* schema_dir() on every call
    (cheap: a small JSON file, cached per root by _manifest_stage_efforts), so
    a RUBRICA_SCHEMA_DIR override takes effect immediately with no cache to
    clear.
    """
    return _manifest_stage_efforts(schema_dir())


@functools.cache
def _validator_for(kind: str, schema_root: Path) -> Draft202012Validator:
    """Compiled validator, cached on (kind, schema_root).

    schema_root is part of the key rather than read inside, so overriding
    RUBRICA_SCHEMA_DIR does not return a validator built from the old one.
    """
    try:
        filename = ARTIFACT_SCHEMAS[kind]
    except KeyError as exc:
        raise KeyError(f"no schema registered for artifact kind {kind!r}") from exc
    schema = read_json(schema_root / filename)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _pointer(parts) -> str:
    return "".join(f"/{part}" for part in parts)


def validate_artifact(path: Path, kind: str) -> list[Finding]:
    """Validate one artifact file against the schema for `kind`."""
    path = Path(path)
    try:
        payload = read_json(path)
    except ArtifactError as exc:
        return [Finding(path, "schema", "", str(exc))]
    validator = _validator_for(kind, schema_dir())
    return [
        Finding(path, "schema", _pointer(error.absolute_path), error.message)
        for error in validator.iter_errors(payload)
    ]


def _artifact_paths(run: RunPaths, kind: str) -> list[Path]:
    """Every file of `kind` that should exist in this run."""
    if kind == "catalogue":
        # Returned even when absent, unlike manifest and world-model's plain
        # is_file() gate: read_json's ArtifactError names the path in its
        # message ("missing artifact: <path>"), so validate_artifact anchors
        # the finding on 00-catalogue.json itself rather than on the run root.
        # An expected artifact that is missing has to be reported by name, or
        # a survey that wrote nothing passes its own gate.
        return [run.catalogue]
    if kind == "triage":
        return [run.triage] if run.triage.is_file() else []
    if kind == "manifest":
        return [run.manifest] if run.manifest.is_file() else []
    if kind == "world-model":
        return [run.world_model] if run.world_model.is_file() else []
    if kind == "scenarios":
        return [run.scenarios] if run.scenarios.is_file() else []
    if kind == "claims":
        return list_json(run.claims_dir)
    if kind == "coverage":
        # latest.json is a singleton artifact that happens to live in a
        # directory of round files, so it is required the way manifest.json and
        # 02-scenarios.json are, not merely globbed. Globbing alone let
        # round-1.json satisfy the gate on its own -- and since refs.check_limits
        # and refs.check_coverage both read coverage_latest and return [] when it
        # is absent, a score stage that wrote the round file and forgot the
        # pointer passed *both* gates with every coverage check bypassed.
        # Returning the absent path makes validate_artifact report it by name.
        rounds = list_json(run.coverage_dir)
        if not rounds and not run.coverage_dir.is_dir():
            return []
        if run.coverage_latest.is_file():
            return rounds
        return [run.coverage_latest, *rounds]
    if kind == "verdict":
        return list_json(run.verdicts_dir)
    if kind == "seed":
        return [run.seed(sid) for sid in run.scenario_ids_with_instances()]
    if kind == "expected":
        return [run.expected(sid) for sid in run.scenario_ids_with_instances()]
    if kind == "suite-expected":
        return [
            run.task_dir(sid) / "tests" / "expected.json" for sid in run.scenario_ids_with_tasks()
        ]
    if kind == "report":
        return [run.report] if run.report.is_file() else []
    raise KeyError(f"unknown artifact kind {kind!r}")


def validate_stage(run: RunPaths, stage: str) -> list[Finding]:
    """Validate every artifact the named stage is responsible for.

    An expected-but-absent artifact is itself a finding. A stage that
    produced nothing has failed, and passing silently would let the
    orchestrator dispatch the next stage against a missing input.
    """
    if stage not in STAGES:
        raise UnknownStage(f"unknown stage {stage!r}; expected one of {', '.join(STAGES)}")
    findings: list[Finding] = []
    for kind in STAGE_ARTIFACTS[stage]:
        paths = _artifact_paths(run, kind)
        if not paths:
            findings.append(
                Finding(run.root, "schema", "", f"stage {stage!r} produced no {kind} artifact")
            )
        for path in paths:
            findings.extend(validate_artifact(path, kind))
    return findings
