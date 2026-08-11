"""Stage 0: register the input artifacts and mint the run.

This module is the reason run ids and timestamps never come from a skill. A
model-invented timestamp would make two otherwise-identical runs diff, and a
model-invented run id could escape the runs directory.

Classification is a heuristic and is meant to be. It seeds the extract
stage's expectations; the extract skill reads the artifact itself and is free
to disagree in its claims.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

from rubrica.artifacts import sha256_of, write_json
from rubrica.errors import UsageError
from rubrica.manifest import utc_stamp
from rubrica.paths import RunPaths, is_safe_segment, safe_segment

_SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".go", ".rs", ".java", ".rb"}
_DOC_SUFFIXES = {".md", ".rst", ".txt", ".adoc"}


def slug(value: str) -> str:
    """Turn an arbitrary path or name into a safe artifact id.

    Step 1 collapses every run of non-alphanumerics to a single "-", so after
    step 2 strips leading and trailing dashes nothing but an alphanumeric can
    be first or last. safe_segment is the check that this held.
    """
    lowered = re.sub(r"[^A-Za-z0-9]+", "-", str(value).lower())
    trimmed = lowered.strip("-")[:96]
    return safe_segment(trimmed) if trimmed else "input"


def stored_name(artifact_id: str, source: Path) -> str:
    """The filename an input is registered under inside 00-inputs/.

    The suffix is cosmetic and the artifact id is the identity, so a suffix that
    would make the name an unsafe path segment is dropped rather than sanitised
    into something unrecognisable or raised on. Raising would turn a perfectly
    registrable input into a misconfigured-harness exit 2; keeping it would put
    a name in manifest.stored_as that paths.input_file refuses to join.
    """
    candidate = f"{artifact_id}{Path(source).suffix.lower()}"
    return candidate if is_safe_segment(candidate) else artifact_id


def _json_or_none(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def classify(path: Path) -> str:
    """Best-effort artifact kind, from the filename and then the content."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in _DOC_SUFFIXES:
        return "design_doc"
    if suffix in _SOURCE_SUFFIXES:
        return "source_code"

    payload = _json_or_none(path)
    if isinstance(payload, dict):
        if "openapi" in payload or "swagger" in payload:
            return "openapi"
        if "spans" in payload or "trace_id" in payload:
            return "trace"
        if path.name == "api.json" or "tools" in payload:
            return "mcp_tool_schema"
        if path.name == "schema.json":
            return "entity_schema"
    if (
        isinstance(payload, list)
        and payload
        and isinstance(payload[0], dict)
        and ("spans" in payload[0] or "trace_id" in payload[0])
    ):
        return "trace"
    return "other"


def _unique_ids(inputs: list[Path]) -> list[str]:
    """Artifact ids for the inputs, suffixed on collision, order preserved."""
    used: dict[str, int] = {}
    ids: list[str] = []
    for path in inputs:
        base = slug(path.name)
        count = used.get(base, 0) + 1
        used[base] = count
        ids.append(base if count == 1 else f"{base}-{count}")
    return ids


def intake(
    *,
    inputs: list[Path],
    runs_dir: Path,
    target_name: str,
    target_interface: str,
    max_rounds: int,
    max_scenarios: int,
    now: datetime | None = None,
) -> RunPaths:
    """Create a run directory, register the inputs, and write the manifest.

    Returns the RunPaths for the new run. Refuses to touch an existing run
    directory: a re-run gets a new id so the old artifacts stay diffable.
    """
    if not inputs:
        raise UsageError("intake needs at least one input artifact")
    # Refused here rather than left for the manifest schema, exactly as
    # manifest.record_stage refuses a blank --model and an unknown --effort. All
    # four of these come from the person or orchestrator invoking intake, and
    # all four have a constraint in manifest-0.1.json: minLength 1 on both
    # target strings, minimum 1 on both limits. Minting the run anyway exited 0
    # and printed a run directory, and the defect surfaced steps later as three
    # findings against manifest.json -- an artifact no repair prompt can ever
    # fix, because intake is code and no skill wrote it. Stricter than the
    # schema on the strings, for record_stage's reason: "   " satisfies
    # minLength: 1 but names no target anyone could act on.
    for label, value in (("--target-name", target_name), ("--target-interface", target_interface)):
        if not isinstance(value, str) or not value.strip():
            raise UsageError(f"intake needs a non-empty {label}, got {value!r}")
    for label, value in (("--max-rounds", max_rounds), ("--max-scenarios", max_scenarios)):
        # isinstance-checked because intake is a library function too: argparse's
        # type=int protects the CLI, but a direct caller passing 2.5 or "2" would
        # otherwise write a manifest the schema rejects for its *type* rather
        # than its value, which is the same class of defect one step further out.
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise UsageError(f"intake needs {label} to be an integer >= 1, got {value!r}")
    inputs = [Path(p) for p in inputs]
    for path in inputs:
        if not path.is_file():
            raise FileNotFoundError(f"input artifact does not exist: {path}")

    # A naive datetime is refused rather than interpreted: .astimezone() would
    # assume the system local zone, so the same call on two hosts would mint
    # two different run ids and created_utc values. Those are the two fields
    # the design says must never come from a skill precisely because they must
    # be stable, so guessing at the zone is worse than failing loudly.
    if now is None:
        stamp = datetime.now(UTC)
    elif now.tzinfo is None:
        raise UsageError("intake needs a timezone-aware datetime, got a naive one")
    else:
        stamp = now.astimezone(UTC)

    run = RunPaths(Path(runs_dir) / f"run-{stamp:%Y%m%d-%H%M%S}")
    if run.root.exists():
        raise FileExistsError(f"run directory already exists: {run.root}")

    run.inputs_dir.mkdir(parents=True)
    entries = []
    for path, artifact_id in zip(inputs, _unique_ids(inputs), strict=True):
        stored_as = stored_name(artifact_id, path)
        destination = run.inputs_dir / stored_as
        shutil.copy2(path, destination)
        entries.append(
            {
                "artifact_id": artifact_id,
                "source_path": str(path),
                "stored_as": stored_as,
                "sha256": sha256_of(path),
                "kind": classify(path),
                "bytes": path.stat().st_size,
            }
        )

    write_json(
        run.manifest,
        {
            "schema_version": "0.1",
            "run_id": run.root.name,
            "created_utc": utc_stamp(stamp),
            "target": {"name": target_name, "interface": target_interface},
            "inputs": entries,
            "stages": {},
            "limits": {"max_rounds": max_rounds, "max_scenarios": max_scenarios},
        },
    )
    return run
