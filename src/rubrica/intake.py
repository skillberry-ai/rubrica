"""Stage 0: register the input artifacts and mint the run.

This module is the reason run ids and timestamps never come from a skill. A
model-invented timestamp would make two otherwise-identical runs diff, and a
model-invented run id could escape the runs directory.

Classification is a heuristic and is meant to be. It seeds the extract
stage's expectations; the extract skill reads the artifact itself and is free
to disagree in its claims.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

from rubrica.artifacts import ArtifactError, canonical_bytes, read_json, sha256_of, write_json
from rubrica.errors import UsageError
from rubrica.findings import Finding
from rubrica.manifest import utc_stamp
from rubrica.paths import RunPaths, is_safe_segment, safe_segment
from rubrica.refs import check_triage, resolve_pointer

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


def _unique_artifact_id(base: str, used: dict[str, int]) -> str:
    """One artifact id, suffixed on collision, `used` mutated to remember it.

    The single spelling of the collision rule -- `_unique_ids` (the --input
    path, keyed on a slugified filename) and `admit_from_triage` (the --run
    path, keyed on a candidate_id that is already a slug) both call this
    rather than each keeping their own counter. That matters downstream:
    refs.check_admitted_inputs reverses this exact rule to recover a
    candidate_id from a manifest artifact_id, and two independent spellings
    of "suffix on collision" would make that reversal ambiguous.
    """
    count = used.get(base, 0) + 1
    used[base] = count
    return base if count == 1 else f"{base}-{count}"


def _unique_ids(inputs: list[Path]) -> list[str]:
    """Artifact ids for the inputs, suffixed on collision, order preserved."""
    used: dict[str, int] = {}
    return [_unique_artifact_id(slug(path.name), used) for path in inputs]


def mint_run(runs_dir: Path, *, now: datetime | None = None) -> tuple[RunPaths, datetime]:
    """Create the run directory and return it with its resolved UTC stamp.

    Split out of intake() so `survey` can mint a run before anything is admitted.
    The manifest is still written by register(), which is what keeps
    manifest-0.1.json's inputs.minItems at 1: the manifest appears only when
    there are inputs to name.

    A naive datetime is refused rather than interpreted, for the reason intake()
    already refused it: .astimezone() assumes the host zone, so the same call on
    two machines would mint two different run ids.
    """
    if now is None:
        stamp = datetime.now(UTC)
    elif now.tzinfo is None:
        raise UsageError("intake needs a timezone-aware datetime, got a naive one")
    else:
        stamp = now.astimezone(UTC)
    run = RunPaths(Path(runs_dir) / f"run-{stamp:%Y%m%d-%H%M%S}")
    if run.root.exists():
        raise FileExistsError(f"run directory already exists: {run.root}")
    run.root.mkdir(parents=True)
    return run, stamp


def register(
    run: RunPaths,
    *,
    entries: list[dict],
    target_name: str,
    target_interface: str,
    max_rounds: int,
    max_scenarios: int,
    created: datetime,
) -> None:
    """Write manifest.json from already-built input entries."""
    write_json(
        run.manifest,
        {
            "schema_version": "0.1",
            "run_id": run.root.name,
            "created_utc": utc_stamp(created),
            "target": {"name": target_name, "interface": target_interface},
            "inputs": entries,
            "stages": {},
            "limits": {"max_rounds": max_rounds, "max_scenarios": max_scenarios},
        },
    )


def _container_path(candidate: dict, run: RunPaths) -> Path:
    """The on-disk location of the container a container_element was exploded from.

    Deliberately takes only `candidate` and `run`, not a `source_root`: the
    container being resolved here is a *different* catalogue candidate from
    the one materialise was called for, and that candidate carries its own
    `root_index` into 00-catalogue.json's `request.corpus_roots` -- which need
    not be the same root the caller resolved for the element being admitted.
    survey.py's own per-root walk_corpus loop is exactly why: a multi-root
    survey assigns root_index per root, so a container living under
    corpus_roots[1] must resolve correctly even when the admitted element's own
    materialise call was handed corpus_roots[0] as `source_root`. Joining
    `source_root` with the container's path (as if the two candidates always
    shared a root) would sometimes still resolve -- by accident, in the common
    single-root case -- and sometimes silently read the wrong file, or none at
    all. Resolving independently, against the catalogue's own record of the
    container's root, is what keeps that failure from being silent.

    check_catalogue already reports a container_element whose container
    candidate_id does not resolve, so this raises ArtifactError rather than
    duplicating that check with a second finding shape.
    """
    container_id = candidate["container"]["candidate_id"]
    try:
        catalogue = read_json(run.catalogue)
    except ArtifactError as exc:
        raise ArtifactError(f"cannot resolve container {container_id!r}: {exc}") from exc
    for entry in catalogue.get("candidates", []):
        if not isinstance(entry, dict) or entry.get("candidate_id") != container_id:
            continue
        path = entry.get("path")
        if not path:
            raise ArtifactError(
                f"candidate {container_id!r} in {run.catalogue} has no path to resolve"
            )
        if Path(path).is_absolute():
            return Path(path)
        roots = catalogue.get("request", {}).get("corpus_roots", [])
        root_index = entry.get("root_index")
        if (
            not isinstance(root_index, int)
            or isinstance(root_index, bool)
            or not (0 <= root_index < len(roots))
        ):
            raise ArtifactError(
                f"candidate {container_id!r} in {run.catalogue} has an invalid "
                f"root_index {root_index!r} for {len(roots)} corpus_roots"
            )
        return Path(roots[root_index]) / path
    raise ArtifactError(
        f"no such candidate {container_id!r} in {run.catalogue} to have been exploded from"
    )


def materialise(run: RunPaths, *, candidate: dict, source_root: Path, artifact_id: str) -> dict:
    """Put one admitted candidate into 00-inputs/ and describe it for the manifest.

    A corpus or projection candidate is copied byte for byte, from
    `source_root / candidate["path"]` unless that path is already absolute --
    a projection the human manufactured is not relative to anything survey
    walked, and `Path(source_root) / "/abs/path"` returning the absolute path
    unchanged is an accident of pathlib's `/` operator that this makes
    explicit rather than relying on.

    A container element is *written* from the container's parsed contents
    through canonical_bytes -- the same function survey hashed it with, so the
    sha256 recorded at survey time equals the digest refs.check_inputs will
    re-hash. Two spellings of "the canonical form" would make every exploded
    input report a mismatch.
    """
    origin = candidate.get("origin")
    if origin == "container_element":
        container_file = _container_path(candidate, run)
        payload = json.loads(container_file.read_text(encoding="utf-8"))
        element = resolve_pointer(payload, candidate["container"]["json_pointer"])
        body = canonical_bytes(element)
        # Same rule as the corpus/projection branch below: one definition of how
        # an input's on-disk filename is derived, not two. stored_name needs only
        # a suffix from its `source` argument, and a container element is always
        # written as JSON, so a synthetic path supplies exactly that -- there is
        # no real source file to point at.
        stored_as = stored_name(artifact_id, Path("container-element.json"))
        (run.inputs_dir / stored_as).write_bytes(body)
        return {
            "artifact_id": artifact_id,
            "source_path": f"{container_file}#{candidate['container']['json_pointer']}",
            "stored_as": stored_as,
            "sha256": hashlib.sha256(body).hexdigest(),
            "kind": candidate["kind"],
            "bytes": len(body),
            "provenance": {
                "container_sha256": sha256_of(container_file),
                "json_pointer": candidate["container"]["json_pointer"],
            },
        }

    raw_path = candidate["path"]
    source = Path(raw_path) if Path(raw_path).is_absolute() else Path(source_root) / raw_path
    stored_as = stored_name(artifact_id, source)
    shutil.copy2(source, run.inputs_dir / stored_as)
    entry = {
        "artifact_id": artifact_id,
        "source_path": str(source),
        "stored_as": stored_as,
        "sha256": sha256_of(source),
        "kind": candidate["kind"],
        "bytes": source.stat().st_size,
    }
    if origin == "projection":
        entry["provenance"] = dict(candidate["provenance"])
    return entry


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

    A caller of mint_run() and register(), so its behaviour cannot drift from
    theirs -- but every argument check below still runs *before* mint_run is
    called, exactly where it ran before the split: a bad --target-name or
    --max-rounds must mint nothing, not a run directory with no manifest.
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

    run, stamp = mint_run(runs_dir, now=now)
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

    register(
        run,
        entries=entries,
        target_name=target_name,
        target_interface=target_interface,
        max_rounds=max_rounds,
        max_scenarios=max_scenarios,
        created=stamp,
    )
    return run


def admit_from_triage(run: RunPaths) -> list[Finding]:
    """Register every admitted candidate and write the manifest.

    Returns findings and writes nothing when the triage record is internally
    inconsistent: that is a repairable stage defect at exit 1, fixed by
    re-dispatching triage. Only an unreadable or absent artifact is a
    UsageError, which cli.py maps to 2 -- the distinction the orchestrator
    branches on.
    """
    if not run.triage.is_file():
        raise UsageError(
            f"no triage record at {run.triage}; run the triage stage before intake --run"
        )
    if not run.catalogue.is_file():
        raise UsageError(f"no catalogue at {run.catalogue}; this run was not minted by survey")
    if run.manifest.exists():
        raise FileExistsError(
            f"manifest already exists: {run.manifest}; a re-run gets a new run id so the old "
            "artifacts stay diffable"
        )

    findings = check_triage(run)
    if findings:
        return findings

    catalogue = read_json(run.catalogue)
    triage = read_json(run.triage)
    candidates = {
        c["candidate_id"]: c
        for c in catalogue.get("candidates") or []
        if isinstance(c, dict) and isinstance(c.get("candidate_id"), str)
    }
    admits = sorted(
        (
            d
            for d in triage.get("dispositions") or []
            if isinstance(d, dict) and d.get("disposition") == "admit"
        ),
        key=lambda d: (d.get("priority", 1 << 30), d.get("candidate_id")),
    )
    if not admits:
        # check_triage already reports this (admits == 0 with a non-empty
        # dispositions list) whenever the schema-required minItems: 1 on
        # dispositions holds, so this is a defensive backstop rather than the
        # primary source of the finding -- kept because admit_from_triage does
        # not itself assume layer 1 has already run.
        return [Finding(run.triage, "refs", "/dispositions", "no candidate was admitted")]

    # check_triage's own "no such candidate" check is gated behind `if
    # candidates` (refs.py), so it is silent whenever the catalogue's own
    # candidates list is empty or carries no valid string ids -- a degenerate
    # catalogue can pass that gate with an admit disposition naming a
    # candidate that does not exist. admit_from_triage checks this itself,
    # unconditionally, for the same reason as the check above: an unresolved
    # candidate_id must come back as a finding against 00-triage.json, not
    # the KeyError that indexing `candidates` below would otherwise raise --
    # an uncaught exception here would escape every handler as an
    # empty-stdout exit 1, indistinguishable from a crashed harness rather
    # than a repairable stage defect.
    # key=repr rather than the bare default: a malformed disposition's
    # candidate_id need not even be a string on an unvalidated artifact (see
    # the "does not itself assume layer 1 has already run" comment above),
    # and sorted() over a set mixing None/int/str raises TypeError -- which
    # would reintroduce exactly the crash this check exists to prevent.
    unknown = sorted({d.get("candidate_id") for d in admits} - set(candidates), key=repr)
    if unknown:
        return [
            Finding(
                run.triage,
                "refs",
                "/dispositions",
                f"admitted candidate {cid!r} is not in the catalogue",
            )
            for cid in unknown
        ]

    admitted = [candidates[d["candidate_id"]] for d in admits]

    roots = catalogue["request"]["corpus_roots"]
    run.inputs_dir.mkdir(parents=True)
    entries = []
    used: dict[str, int] = {}
    for candidate in admitted:
        artifact_id = _unique_artifact_id(candidate["candidate_id"], used)
        # A multi-root survey assigns root_index per corpus root (survey.py's
        # own per-root walk_corpus loop), so each admitted candidate resolves
        # against *its own* root rather than corpus_roots[0] -- defaulting to
        # 0 only for a candidate that predates root_index (there are none in
        # this build, but the field is optional in the schema).
        source_root = Path(roots[candidate.get("root_index", 0)])
        entries.append(
            materialise(run, candidate=candidate, source_root=source_root, artifact_id=artifact_id)
        )

    request = catalogue["request"]
    register(
        run,
        entries=entries,
        target_name=request["target"]["name"],
        target_interface=request["target"]["interface"],
        max_rounds=request["limits"]["max_rounds"],
        max_scenarios=request["limits"]["max_scenarios"],
        created=datetime.strptime(catalogue["created_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        ),
    )
    return []
