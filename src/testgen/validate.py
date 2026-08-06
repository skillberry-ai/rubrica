"""JSON Schema validation of run artifacts: layer 1 of three.

Layer 1 checks shape only. Cross-artifact references, seed-pointer
reachability, and world-model invariants are layer 2 and live in refs.py;
layer 3 is the smoke gate. A stage's output must clear layer 1 before the
orchestrator dispatches the next stage (design spec section 5).

Findings are returned, never raised: the orchestrator's contract is one
bounded repair attempt with the findings appended to the stage prompt, which
needs the full list rather than the first failure.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path

from jsonschema import Draft202012Validator

from testgen.artifacts import ArtifactError, read_json
from testgen.findings import Finding
from testgen.paths import STAGES, RunPaths

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
}

# Which artifact kinds each stage must produce. Stages that emit no JSON
# artifact of their own map to an empty tuple and pass layer 1 trivially;
# they are gated by check-refs and by the smoke report instead.
STAGE_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "intake": ("manifest",),
    "extract": ("claims",),
    "reconcile": ("world-model",),
    "propose": ("scenarios",),
    "score": ("coverage",),
    "instantiate": ("seed", "expected"),
    "challenge": ("verdict",),
    "emit": (),
    "smoke": (),
}


class UnknownStage(ValueError):
    """Raised for a stage name that is not in paths.STAGES."""


def schema_dir() -> Path:
    """Directory holding the artifact schemas.

    Overridable via TESTGEN_SCHEMA_DIR so a caller can validate against a
    candidate schema set without reinstalling the package.
    """
    override = os.environ.get("TESTGEN_SCHEMA_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "schema"


@functools.cache
def _validator_for(kind: str, schema_root: Path) -> Draft202012Validator:
    """Compiled validator, cached on (kind, schema_root).

    schema_root is part of the key rather than read inside, so overriding
    TESTGEN_SCHEMA_DIR does not return a validator built from the old one.
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
    if kind == "manifest":
        return [run.manifest] if run.manifest.is_file() else []
    if kind == "world-model":
        return [run.world_model] if run.world_model.is_file() else []
    if kind == "scenarios":
        return [run.scenarios] if run.scenarios.is_file() else []
    if kind == "claims":
        return sorted(run.claims_dir.glob("*.json")) if run.claims_dir.is_dir() else []
    if kind == "coverage":
        return sorted(run.coverage_dir.glob("*.json")) if run.coverage_dir.is_dir() else []
    if kind == "verdict":
        return sorted(run.verdicts_dir.glob("*.json")) if run.verdicts_dir.is_dir() else []
    if kind == "seed":
        return [run.seed(sid) for sid in run.scenario_ids_with_instances()]
    if kind == "expected":
        return [run.expected(sid) for sid in run.scenario_ids_with_instances()]
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
