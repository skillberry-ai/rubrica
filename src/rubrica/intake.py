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
    # RecursionError alongside the three obvious ones, matching
    # digest.digest_for_path's own catch and for the same measured reason:
    # survey.py's "no size-based exclusion" rule means a pathologically nested
    # file (a 200,000-deep `[[[...]]]`) reaches classify() uncaught by anything
    # upstream, and CPython's json decoder raises RecursionError rather than
    # JSONDecodeError for that shape. classify is on the hot path of both new
    # commands -- `survey --corpus DIR` walks an arbitrary user tree, and
    # `adopt-projection` reaches it through triage.check_acceptance -- and
    # neither cli.py dispatch block catches RecursionError, so it escaped
    # main() as a traceback: exit 1 with empty stdout, the shape the exit-code
    # contract forbids.
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError):
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


# The lowest priority a disposition without one sorts at -- admits run in
# priority order and one that declares none goes last.
_NO_PRIORITY = 1 << 30


def admit_sort_key(disposition: dict) -> tuple[int, str]:
    """The order admitted candidates are materialised in, as one function.

    Two callers need the *identical* order, not merely a compatible one:
    admit_from_triage materialises in this order and `_unique_artifact_id`'s
    collision suffixes therefore depend on it, and
    refs.check_admitted_inputs replays the same sort to recover which
    artifact_id each admitted candidate_id became. Two spellings of "sorted by
    priority then id" would make that replay silently disagree the first time
    they drifted, so there is one.

    Total-ordering is the whole reason this is a named function rather than a
    lambda. `(d.get("priority", _NO_PRIORITY), d.get("candidate_id"))` was
    measured to raise TypeError on two shapes an *unvalidated* triage record
    reaches it with -- a string `priority` alongside an integer one
    ("'<' not supported between instances of 'int' and 'str'") and a null
    `candidate_id` alongside a string one -- and neither cli.py's `intake
    --run` block nor its `check-refs` block catches TypeError, so it escaped
    main() as a traceback: exit 1 with empty stdout. admit_from_triage does
    not assume layer 1 has already run (its own module comments say so twice),
    so every value is coerced to a comparable one here instead: a non-integer
    priority sorts as if absent, and the id goes through repr() -- the same
    device the `unknown` sort in admit_from_triage already uses, and
    order-preserving for the ids the schema actually permits, since
    `\\A[A-Za-z0-9][A-Za-z0-9._-]*\\Z` contains nothing repr escapes and every
    result gains the same leading quote. A malformed id is reported as a
    finding moments later; all this has to do is get there without raising.
    """
    priority = disposition.get("priority")
    if not isinstance(priority, int) or isinstance(priority, bool):
        priority = _NO_PRIORITY
    return (priority, repr(disposition.get("candidate_id")))


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


def _resolvable_root_index(root_index, roots) -> bool:
    """Whether `root_index` is a usable index into `roots`.

    One spelling, read by `_container_path` (for the container a
    container_element was exploded from) and by `admit_from_triage` (for each
    admitted corpus candidate). Both were indexing `request.corpus_roots` with
    a number the catalogue supplied and neither layer checks against the list's
    actual length; `_container_path` had this test inline and the admit loop had
    none at all, which is how a hand-edited `root_index` reached `roots[5]` and
    raised IndexError out of main().

    `isinstance(root_index, bool)` is excluded explicitly because
    `isinstance(True, int)` is True in Python, and `roots[True]` silently reads
    the *second* corpus root rather than raising -- the wrong file, with no
    error anywhere, which is the failure mode `_container_path`'s docstring
    already says resolving independently exists to prevent.
    """
    return (
        isinstance(root_index, int)
        and not isinstance(root_index, bool)
        and 0 <= root_index < len(roots)
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
        if not _resolvable_root_index(root_index, roots):
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


def _registration_from_catalogue(run: RunPaths, catalogue: dict) -> tuple[dict, list[Finding]]:
    """register()'s five arguments, read out of the catalogue, or findings.

    Every read below was a bare index -- `catalogue["request"]["target"]["name"]`,
    `["limits"]["max_rounds"]`, `datetime.strptime(catalogue["created_utc"], ...)`
    -- and every one of them ran *after* the 00-inputs/ materialise loop and
    *outside* the try whose except cleans it up. Deleting `request.target` from
    a surveyed catalogue, which is exactly the hand-edit gate 0 authorises, was
    measured to breach the exit-code contract three ways at once: the KeyError
    escaped cli.py's `(UsageError, ArtifactError, OSError)` catch and left
    main() with exit 1 and empty stdout; 00-inputs/ stayed behind fully
    populated; and every retry after repairing the catalogue then died on
    `[Errno 17] File exists` at exit 2, so the run was permanently unusable
    rather than repairable.

    So this runs *before* the mkdir, alongside the corpus_roots check that was
    already there -- a malformed catalogue leaves no directory behind at all --
    and returns findings against 00-catalogue.json, where the defect lives,
    with a pointer at the key that is wrong. Stricter than the manifest schema
    on the two target strings and on both limits, for the reason intake()'s own
    argument checks give: "   " satisfies minLength: 1 but names no target
    anyone could act on, and a manifest written from a limit the schema rejects
    surfaces steps later as a finding against an artifact no repair prompt can
    fix.
    """
    out: list[Finding] = []

    def report(pointer: str, message: str) -> None:
        out.append(Finding(run.catalogue, "internal", pointer, message))

    request = catalogue.get("request")
    if not isinstance(request, dict):
        report(
            "/request",
            "request is missing or not an object; intake --run mints the manifest from it and "
            "has nothing to read",
        )
        return {}, out

    target = request.get("target")
    values: dict[str, object] = {}
    if not isinstance(target, dict):
        report(
            "/request/target",
            "target is missing or not an object; the manifest's target block is minted from it",
        )
    else:
        for key in ("name", "interface"):
            value = target.get(key)
            if not isinstance(value, str) or not value.strip():
                report(
                    f"/request/target/{key}",
                    f"target.{key} is missing or blank; manifest.target.{key} is minted from it "
                    "and cannot be empty",
                )
            else:
                values[f"target_{key}"] = value

    limits = request.get("limits")
    if not isinstance(limits, dict):
        report(
            "/request/limits",
            "limits is missing or not an object; the manifest's limits block is minted from it",
        )
    else:
        for key in ("max_rounds", "max_scenarios"):
            value = limits.get(key)
            # isinstance(True, int) is True, so bool is excluded explicitly --
            # the same guard intake() and survey() apply to the same two
            # limits, because JSON `true` is not an integer to the manifest
            # schema either.
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                report(
                    f"/request/limits/{key}",
                    f"limits.{key} is {value!r}, not an integer >= 1; manifest.limits.{key} is "
                    "minted from it and the manifest schema requires one",
                )
            else:
                values[key] = value

    created = catalogue.get("created_utc")
    try:
        # TypeError as well as ValueError: strptime raises TypeError, not
        # ValueError, when created_utc is absent (None) or is a number rather
        # than a string, and both escaped main() identically before this guard.
        values["created"] = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except (TypeError, ValueError):
        report(
            "/created_utc",
            f"created_utc is {created!r}, not a UTC stamp in manifest.UTC_FORMAT "
            "('%Y-%m-%dT%H:%M:%SZ'); manifest.created_utc is minted from it",
        )

    return values, out


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
        key=admit_sort_key,
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

    # catalogue["request"]["corpus_roots"] would raise KeyError on an
    # unvalidated catalogue -- the same "does not itself assume layer 1 has
    # already run" reasoning as the unknown-candidate check above, and for
    # the same consequence: an uncaught KeyError here would escape main()'s
    # narrow (UsageError, ArtifactError, OSError) catch as a traceback,
    # exactly the empty-stdout-exit-1 shape the exit-code contract forbids.
    # A malformed catalogue is a repairable stage defect, and this function
    # already returns findings for one (see above), so this becomes one
    # too -- against run.catalogue, where the defect actually lives.
    request = catalogue.get("request")
    roots = request.get("corpus_roots") if isinstance(request, dict) else None
    if not isinstance(roots, list) or not roots:
        return [
            Finding(
                run.catalogue,
                "internal",
                "/request/corpus_roots",
                "corpus_roots is missing, empty, or not a list; intake --run cannot resolve "
                "which corpus root each admitted candidate came from",
            )
        ]
    # `roots[candidate.get("root_index", 0)]` in the loop below is an index into
    # a list whose length nothing has checked against the value the catalogue
    # supplies. `_container_path` already guards its own copy of exactly this
    # lookup, with exactly this reasoning, for the container it resolves; a
    # *corpus* candidate's root_index had no such guard, and a hand-edited
    # root_index of 5 against one corpus root was measured to raise IndexError
    # (a string one, TypeError) straight out of main() -- the cleanup below
    # fired, so the run stayed retryable, but the exit was still 1 with empty
    # stdout. Checked here rather than in the loop so a malformed catalogue
    # leaves no directory behind at all, and reported per candidate so a human
    # repairing 00-catalogue.json is told which one is wrong.
    root_findings = [
        Finding(
            run.catalogue,
            "internal",
            "/candidates",
            f"admitted candidate {candidate.get('candidate_id')!r} has an invalid root_index "
            f"{candidate.get('root_index')!r} for {len(roots)} corpus_roots",
        )
        for candidate in admitted
        if not _resolvable_root_index(candidate.get("root_index", 0), roots)
    ]
    if root_findings:
        return root_findings

    # Before the mkdir, exactly like the corpus_roots check just above and for
    # the same reason: a catalogue this function cannot mint a manifest from
    # must leave no half-created run behind. Reading these five values here
    # rather than at the register() call below is the fix for the measured
    # breach _registration_from_catalogue's docstring records.
    registration, findings = _registration_from_catalogue(run, catalogue)
    if findings:
        return findings

    run.inputs_dir.mkdir(parents=True)
    try:
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
                materialise(
                    run, candidate=candidate, source_root=source_root, artifact_id=artifact_id
                )
            )
        # Inside the try, not after it. The five arguments are already read and
        # checked (above, before the mkdir), so nothing here can raise the
        # KeyError this used to -- but register() itself can still fail, on a
        # read-only run directory or a full disk, and a failure there outside
        # this try left 00-inputs/ populated with no manifest and every retry
        # dead on FileExistsError. Whatever the reason a run does not get its
        # manifest, it comes back to its pre-admission state and the same call
        # can simply be made again.
        register(
            run,
            entries=entries,
            target_name=registration["target_name"],
            target_interface=registration["target_interface"],
            max_rounds=registration["max_rounds"],
            max_scenarios=registration["max_scenarios"],
            created=registration["created"],
        )
    except Exception:
        # A source file can vanish between survey and intake -- deleted,
        # moved, permissions changed -- and materialise raises partway
        # through the loop, having already copied some candidates in. Left
        # alone, that leaves 00-inputs/ half-populated with no manifest, and
        # a retry's mkdir above hits FileExistsError forever: the run is
        # stuck, not repairable. Removing what this call created returns the
        # run to its pre-admission state, so the same call can simply be
        # made again once the missing file is back.
        #
        # register() is inside this try too, so this branch covers it as well.
        # It needs no cleanup of its *own* partial output -- per
        # artifacts.write_json's tempfile-then-replace, it either writes a
        # complete manifest or writes nothing -- but it does need the
        # 00-inputs/ removal below, because a register() that fails on a
        # read-only run directory or a full disk would otherwise leave exactly
        # the populated-inputs-no-manifest state that strands the run.
        shutil.rmtree(run.inputs_dir, ignore_errors=True)
        raise

    return []
