"""Stage 00a: turn a corpus into a catalogue of candidates.

The phase this module opens was performed by hand on every run before
2026-08-14, in the orchestrator's own conversation, and recorded nowhere the
pipeline could read. Its output exists so that triage's judgment is
affordable: one bounded digest per candidate rather than the corpus itself,
which is what keeps triage's cost O(candidates) instead of O(corpus bytes).

Two rules govern every choice below, both learned from the 2026-08-13
development run -- a full-pipeline run over a large real-world corpus, called
"the development corpus" throughout this module:

* **No size-based exclusion.** The largest single file in that corpus was also
  its most load-bearing input, unusable whole and correct as a projection. Size
  was never the binding constraint; shape was.
* **Every drop is recorded.** A candidate that vanishes with no reason is
  indistinguishable from one that never existed, and that confusion made four
  of that run's gaps unreadable.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rubrica import digest as digest_module
from rubrica import slices as slices_module
from rubrica.artifacts import canonical_bytes, sha256_of, write_json
from rubrica.errors import UsageError
from rubrica.intake import _unique_artifact_id, classify, slug
from rubrica.manifest import utc_stamp
from rubrica.paths import RunPaths

# Same eight strings as catalogue-0.1.json's exclusion_reason enum. Kept here
# too because walk_corpus emits them and a test pins the two lists identical --
# they drifted in exactly this shape once before, for validate.CONFIG_KINDS.
EXCLUSION_REASONS: tuple[str, ...] = (
    "gitignored",
    "vcs_metadata",
    "binary",
    "lockfile",
    "vendored",
    "duplicate",
    "unreadable",
    "operator_excluded",
)

DEFAULT_MAX_CANDIDATES = 500
# 1MiB, chosen with headroom above the 476KB the development corpus's catalogue
# measured at (351 candidates, well under DEFAULT_MAX_CANDIDATES) -- not to
# bind on the corpus we have, but because --max-candidates is a count guard
# and bytes are what actually fill a dispatched model's context window.
DEFAULT_MAX_CATALOGUE_BYTES = 1_048_576
DEFAULT_DIGEST_BODY_CHARS = 2000
# Three, not two: exploding a two-element config array produces two candidates
# nobody wanted, while the shape this exists for -- a capture of many
# independent records -- is never that small. 130 in the development corpus.
EXPLODE_MIN_ELEMENTS = 3
# Homogeneity is a key-set *intersection*, not identity: real captures carry
# optional fields, and 130 traces where one lacks an `assessments` key are not
# two kinds of thing. Measured on that capture: 12 common keys, zero
# union-only keys, so identity would have worked there and the tolerant rule
# costs nothing.
EXPLODE_MIN_COMMON_KEYS = 3

_VCS_DIRS = frozenset({".git", ".hg", ".svn"})
_VENDOR_DIRS = frozenset(
    {"node_modules", ".venv", "venv", "site-packages", "vendor", "target", "dist", "build"}
)
_LOCKFILES = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "uv.lock",
        "Cargo.lock",
        "Gemfile.lock",
        "go.sum",
        "requirements.txt.lock",
        "composer.lock",
    }
)
_BINARY_SNIFF_BYTES = 8192


def _gitignore_patterns(root: Path) -> list[str]:
    """Patterns from `root/.gitignore`, one level only.

    Deliberately not a full gitignore implementation: nested ignore files,
    negations and directory semantics are a library's job, and getting them
    subtly wrong would drop evidence *silently*, which is the one failure this
    module exists to prevent. What it does catch is the common case -- a
    top-level ignore listing generated and secret files -- and anything it
    misses stays in the catalogue where triage and a human can see it.
    """
    ignore = root / ".gitignore"
    try:
        text = ignore.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    patterns = []
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and not line.startswith("!"):
            patterns.append(line.rstrip("/"))
    return patterns


def _looks_binary(path: Path) -> bool:
    with path.open("rb") as handle:
        return b"\x00" in handle.read(_BINARY_SNIFF_BYTES)


def _matches_any(relative: str, patterns: Sequence[str]) -> bool:
    name = Path(relative).name
    return any(
        fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(name, pattern) for pattern in patterns
    )


def walk_corpus(
    roots: Sequence[Path],
    *,
    operator_globs: Sequence[str] = (),
    seen: dict[str, Path] | None = None,
) -> tuple[list[Path], list[dict]]:
    """Every file worth cataloguing, and every one dropped with its reason.

    Order matters and is sorted, so `duplicate` always names the *later* of two
    byte-identical paths and two runs over the same corpus produce the same
    catalogue. Returns paths, not digests: digesting is digest.py's job.

    `seen` is digest -> the path that already claimed it, and defaults to a
    fresh dict private to this call -- the behaviour every existing caller and
    test already depends on. survey() passes one dict across its per-root
    calls instead, so a file byte-identical across two `--corpus` roots is
    still caught as `duplicate` even though each root gets its own call (for
    `root_index`); without a shared dict, each call started from empty and a
    cross-root duplicate was admitted twice with no finding anywhere.
    """
    kept: list[Path] = []
    excluded: list[dict] = []
    if seen is None:
        seen = {}

    for root in roots:
        root = Path(root)
        try:
            if not root.is_dir():
                raise UsageError(f"corpus root is not a directory: {root}")
            # rglob silently swallows a PermissionError raised while listing the
            # *root* itself -- measured, not assumed: an EACCES root returns an
            # empty generator rather than raising, so the `except OSError` below
            # never fired and an unreadable root reported as an empty corpus,
            # which is exactly the swallowed-EACCES hazard this function's own
            # comment already warned about. Forcing one iterdir() first makes
            # that failure visible before rglob can hide it.
            list(root.iterdir())
            walked = sorted(p for p in root.rglob("*") if p.is_file())
        except OSError as exc:
            # An unreadable *root* is the harness pointed at something it cannot
            # read, which is exit 2 -- the same call paths.list_dir makes, and
            # for the same reason: a swallowed EACCES here would report an empty
            # corpus rather than an unreadable one.
            raise UsageError(f"cannot read corpus root: {root} ({exc})") from exc

        ignore_patterns = _gitignore_patterns(root)

        for path in walked:
            relative = path.relative_to(root).as_posix()
            parts = set(path.relative_to(root).parts)

            def drop(reason: str, rel: str = relative) -> None:
                excluded.append({"path": rel, "reason": reason})

            if parts & _VCS_DIRS:
                drop("vcs_metadata")
                continue
            if parts & _VENDOR_DIRS:
                drop("vendored")
                continue
            if path.name in _LOCKFILES:
                drop("lockfile")
                continue
            if operator_globs and _matches_any(relative, operator_globs):
                drop("operator_excluded")
                continue
            if ignore_patterns and _matches_any(relative, ignore_patterns):
                drop("gitignored")
                continue
            try:
                if _looks_binary(path):
                    drop("binary")
                    continue
                digest = sha256_of(path)
            except OSError:
                # One bad mode in a user tree must not abort the inventory. The
                # file is recorded as declined, so it is visible rather than
                # absent -- which is the whole rule this module is built on.
                drop("unreadable")
                continue
            if digest in seen:
                drop("duplicate")
                continue
            seen[digest] = path
            kept.append(path)

    return kept, excluded


def classify_payload(payload: Any) -> str:
    """The artifact kind of a container element, which has no filename.

    Mirrors intake.classify's *content* branch only. Deliberately not a call
    into intake.classify with a fake path: a synthesised name would let the
    filename branch fire on something that has no filename.
    """
    if isinstance(payload, dict):
        if "openapi" in payload or "swagger" in payload:
            return "openapi"
        if "spans" in payload or "trace_id" in payload:
            return "trace"
        if "tools" in payload:
            return "mcp_tool_schema"
    return "other"


def _escape_pointer_token(token: str) -> str:
    """RFC 6901 escaping. `~` first, or escaping `/` would then be re-escaped."""
    return token.replace("~", "~0").replace("/", "~1")


# catalogue-0.1.json's `id` definition: `\A[A-Za-z0-9][A-Za-z0-9._-]*\Z`, with
# maxLength 128. Named here because _element_candidate_id has to *budget*
# against it, not merely hope.
_MAX_CANDIDATE_ID = 128
# Reserved for `_unique_artifact_id`'s collision suffix, which is appended
# *after* this function returns and so cannot be accounted for inside it. Eight
# characters carries "-9999999" -- far past the point DEFAULT_MAX_CANDIDATES
# (500) allows a single base id to collide.
_COLLISION_SUFFIX_ROOM = 8


def _element_candidate_id(container_id: str, pointer: str) -> str:
    """The candidate_id for one element exploded out of `container_id`.

    This was `f"{container_id}{pointer.replace('/', '-')}"`, which slugged the
    container half and left the pointer-derived half raw -- and
    `_escape_pointer_token` had just introduced `~0`/`~1` into it. Measured on
    `{"trace one/a": ..., "trace two~b": ..., "Trace Three": ...}`: `survey`
    exited 0 and `validate --stage survey` then reported three schema findings,
    so the command minted a catalogue that fails its own layer-1 gate. Id-keyed
    containers are first-class here and real ids carry `:`, `/` and
    spaces, so this is the ordinary case rather than a hostile one.

    The pointer goes through `slug`, the same function every other id in this
    pipeline is built with -- one spelling of "make this a safe id", not a
    second. For an *array* container the result is byte-identical to what this
    replaced (`slug("/0")` is `"0"`, so `capture-json` + `-0` is still
    `capture-json-0`), which matters: those ids are written into committed
    fixtures and a triage record names them.

    maxLength 128 is budgeted rather than assumed, because a long container name
    plus a long key can exceed it on its own. The *prefix* is what gets
    truncated, never the suffix: every element of one container shares the
    prefix, so trimming it identically keeps them distinguishable, while
    trimming the suffix would collapse them all onto one base id and leave
    `_unique_artifact_id` to tell them apart by collision counter alone.
    """
    suffix = slug(pointer)
    budget = _MAX_CANDIDATE_ID - _COLLISION_SUFFIX_ROOM
    room_for_prefix = budget - len(suffix) - 1
    # rstrip so a truncation landing mid-separator does not leave a trailing
    # "-" or "." doubled against the one this joins with. The id pattern would
    # tolerate it; a reader would not.
    prefix = container_id[:room_for_prefix].rstrip("-._") if room_for_prefix > 0 else ""
    if not prefix:
        # A container id long enough to leave no room is pathological, and the
        # suffix alone is still a valid id (slug guarantees that) and still
        # unique per element within this container.
        return suffix
    return f"{prefix}-{suffix}"


def _homogeneous(elements: list) -> bool:
    """Whether these elements are independent records of one kind.

    Objects only, and their key sets must share EXPLODE_MIN_COMMON_KEYS. The
    intersection rule rather than identity is the point -- see that constant.
    """
    if not all(isinstance(element, dict) for element in elements):
        return False
    key_sets = [set(element) for element in elements]
    if any(len(keys) < EXPLODE_MIN_COMMON_KEYS for keys in key_sets):
        return False
    return len(set.intersection(*key_sets)) >= EXPLODE_MIN_COMMON_KEYS


def explode(payload: Any) -> list[tuple[str, Any]] | None:
    """Split a container of independent records, or return None.

    Returns (json_pointer, element) pairs in document order. `None` means "this
    is one candidate": a scalar, an array of scalars, a heterogeneous array, or
    an object that is a single document with many sections rather than many
    documents. An OpenAPI spec is the case that matters for that last one --
    it has many `paths` and is still one contract, and a fragment of it cannot
    be read alone.

    Only these two shapes explode, by ruling: no Python
    literals, no multi-document markdown, no archive members.
    """
    if isinstance(payload, list):
        if len(payload) < EXPLODE_MIN_ELEMENTS or not _homogeneous(payload):
            return None
        return [(f"/{index}", element) for index, element in enumerate(payload)]

    if isinstance(payload, dict):
        values = list(payload.values())
        if len(values) < EXPLODE_MIN_ELEMENTS or not _homogeneous(values):
            return None
        return [(f"/{_escape_pointer_token(key)}", value) for key, value in payload.items()]

    return None


def survey(
    *,
    corpus_roots: Sequence[Path],
    runs_dir: Path,
    target_name: str,
    target_interface: str,
    objective: str,
    objective_note: str | None = None,
    scope_note: str | None = None,
    operator_globs: Sequence[str] = (),
    max_rounds: int,
    max_scenarios: int,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    max_catalogue_bytes: int = DEFAULT_MAX_CATALOGUE_BYTES,
    digest_body_chars: int = DEFAULT_DIGEST_BODY_CHARS,
    now: datetime | None = None,
) -> RunPaths:
    """Mint a run and write its catalogue. Writes no manifest and no inputs.

    Argument validation happens before the directory is created, for the reason
    intake.intake's own docstring gives: minting a run from a parameter set the
    manifest schema will later reject exits 0 and surfaces steps later as
    findings against an artifact no repair prompt can fix. The catalogue's
    serialised byte size is measured and checked against max_catalogue_bytes
    for the same reason, and before the same mkdir: a catalogue too large for
    one triage dispatch's context is exactly as unrepairable as too many
    candidates, so it gets the same exit-2 treatment at the same point.
    """
    if not corpus_roots:
        raise UsageError("survey needs at least one --corpus root")
    for label, value in (("--target-name", target_name), ("--target-interface", target_interface)):
        if not isinstance(value, str) or not value.strip():
            raise UsageError(f"survey needs a non-empty {label}, got {value!r}")
    if objective not in ("breadth", "depth"):
        raise UsageError(f"survey needs --objective breadth or depth, got {objective!r}")
    for label, value in (
        ("--max-rounds", max_rounds),
        ("--max-scenarios", max_scenarios),
        ("--max-candidates", max_candidates),
        ("--max-catalogue-bytes", max_catalogue_bytes),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise UsageError(f"survey needs {label} to be an integer >= 1, got {value!r}")

    if now is None:
        stamp = datetime.now(UTC)
    elif now.tzinfo is None:
        raise UsageError("survey needs a timezone-aware datetime, got a naive one")
    else:
        stamp = now.astimezone(UTC)

    candidates: list[dict] = []
    excluded: list[dict] = []
    used: dict[str, int] = {}
    # One walk_corpus call per root, rather than one call over the whole list,
    # so root_index is the loop variable and no path needs to be re-matched
    # against corpus_roots afterwards -- see this task's brief for why
    # re-matching is wrong for nested roots. `seen` is created once here and
    # passed into every call so a file byte-identical across two roots is
    # still caught as `duplicate`, naming the copy under the *later* root --
    # the per-root loop must not reopen the cross-root dedup gap a bare
    # `walk_corpus([Path(root)], ...)` call (a fresh, private `seen` each
    # time) would silently admit twice.
    seen: dict[str, Path] = {}
    for root_index, root in enumerate(corpus_roots):
        kept, root_excluded = walk_corpus([Path(root)], operator_globs=operator_globs, seen=seen)
        excluded.extend(root_excluded)

        for path in kept:
            relative = path.relative_to(Path(root)).as_posix()
            kind = classify(path)
            candidate_id = _unique_artifact_id(slug(path.name), used)
            exploded = None
            if kind != "design_doc" and kind != "source_code":
                # Only structured files can be containers. Reading a 6MB capture
                # is the cost this whole stage exists to pay once rather than
                # per-stage.
                # RecursionError alongside the three obvious ones, matching
                # digest.digest_for_path's and intake._json_or_none's catches
                # and for the reason this module's own header states: with no
                # size-based exclusion, a pathologically nested file (a
                # 200,000-deep `[[[...]]]`) in an arbitrary user tree reaches
                # this line, and CPython's json decoder raises RecursionError
                # rather than JSONDecodeError for that shape. cli.py's survey
                # block catches only (UsageError, ArtifactError, OSError), so
                # it escaped main() as a traceback -- one hostile file in the
                # corpus took down the whole inventory. Not exploding it is the
                # right outcome anyway: a file this decoder cannot read is one
                # candidate, and the digest heuristics record that.
                try:
                    exploded = explode(json.loads(path.read_text(encoding="utf-8")))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError):
                    exploded = None

            entry = {
                "candidate_id": candidate_id,
                "origin": "corpus",
                "path": relative,
                "root_index": root_index,
                "bytes": path.stat().st_size,
                "sha256": sha256_of(path),
                "kind": kind,
                # A container stays visible and inadmissible: admitting it would
                # hand one stage every record at once, which is what exploding
                # prevents.
                "admissible": exploded is None,
                "digest": digest_module.digest_for_path(path, kind, body_chars=digest_body_chars),
            }
            candidates.append(entry)

            for pointer, element in exploded or []:
                body = canonical_bytes(element)
                element_kind = classify_payload(element)
                candidates.append(
                    {
                        "candidate_id": _unique_artifact_id(
                            _element_candidate_id(candidate_id, pointer), used
                        ),
                        "origin": "container_element",
                        "container": {"candidate_id": candidate_id, "json_pointer": pointer},
                        "bytes": len(body),
                        # Of the bytes intake will materialise, not of the
                        # container: refs.check_inputs re-hashes the written
                        # file.
                        "sha256": hashlib.sha256(body).hexdigest(),
                        "kind": element_kind,
                        "admissible": True,
                        "digest": digest_module.digest_for_payload(
                            element, element_kind, body_chars=digest_body_chars
                        ),
                    }
                )

    if len(candidates) > max_candidates:
        raise UsageError(
            f"corpus yields {len(candidates)} candidates, over max_candidates={max_candidates}; "
            "narrow --corpus or raise the cap -- a catalogue this large does not fit one "
            "triage dispatch's context"
        )

    # Before the byte cap, because this one is not about the catalogue's total:
    # a candidate row larger than one slice cannot be partitioned at all, and
    # no repair prompt can shrink it. `triage-slices` would have to either
    # exceed its cap or drop the candidate, and dropping one silently is the
    # failure this whole stage exists to prevent.
    oversized = slices_module.oversized_rows(candidates)
    if oversized:
        named = ", ".join(f"{cid} at {size} bytes" for cid, size in oversized[:5])
        raise UsageError(
            f"{len(oversized)} candidate row(s) exceed one slice of "
            f"{slices_module.DEFAULT_SLICE_BYTES} bytes: {named}; narrow --corpus or "
            "--exclude these files -- a row this large cannot be sliced, so triage "
            "could never be dispatched over it"
        )

    run_id = f"run-{stamp:%Y%m%d-%H%M%S}"

    request = {
        "target": {"name": target_name.strip(), "interface": target_interface.strip()},
        "objective": objective,
        "corpus_roots": [str(Path(root)) for root in corpus_roots],
        "limits": {"max_rounds": max_rounds, "max_scenarios": max_scenarios},
    }
    if objective_note:
        request["objective_note"] = objective_note
    if scope_note:
        request["scope_note"] = scope_note

    payload = {
        "schema_version": "0.1",
        "run_id": run_id,
        "created_utc": utc_stamp(stamp),
        "request": request,
        "policy": {
            "exclusion_reasons": list(EXCLUSION_REASONS),
            "explode_min_elements": EXPLODE_MIN_ELEMENTS,
            "explode_min_common_keys": EXPLODE_MIN_COMMON_KEYS,
            "digest_body_chars": digest_body_chars,
            "max_candidates": max_candidates,
            "max_catalogue_bytes": max_catalogue_bytes,
            "operator_globs": list(operator_globs),
        },
        "candidates": candidates,
        "excluded": excluded,
    }

    # Measured before mkdir, same ordering as the max_candidates check above:
    # a catalogue this large does not fit one triage dispatch's context, and
    # narrowing --corpus/--exclude is the only fix -- no repair prompt can
    # shrink a corpus, so a rejected run must leave no directory behind for a
    # human or orchestrator to puzzle over.
    measured = len(canonical_bytes(payload))
    if measured > max_catalogue_bytes:
        raise UsageError(
            f"catalogue would be {measured} bytes, over max_catalogue_bytes={max_catalogue_bytes}; "
            "narrow --corpus or raise the cap -- a catalogue this large does not fit one "
            "triage dispatch's context"
        )

    run = RunPaths(Path(runs_dir) / run_id)
    if run.root.exists():
        raise FileExistsError(f"run directory already exists: {run.root}")
    run.root.mkdir(parents=True)

    write_json(run.catalogue, payload)
    return run
