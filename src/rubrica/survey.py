"""Stage 00a: turn a corpus into a catalogue of candidates.

The phase this module opens was performed by hand on every run before
2026-08-14, in the orchestrator's own conversation, and recorded nowhere the
pipeline could read. Its output exists so that rb-triage's judgment is
affordable: one bounded digest per candidate rather than the corpus itself,
which is what keeps triage's cost O(candidates) instead of O(corpus bytes).

Two rules govern every choice below, both from the parsec run's §11:

* **No size-based exclusion.** The largest single file in that corpus was also
  its most load-bearing input, unusable whole and correct as a projection. Size
  was never the binding constraint; shape was.
* **Every drop is recorded.** A candidate that vanishes with no reason is
  indistinguishable from one that never existed, and that confusion made four
  of that run's gaps unreadable.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Sequence
from pathlib import Path

from rubrica.artifacts import sha256_of
from rubrica.errors import UsageError

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
DEFAULT_DIGEST_BODY_CHARS = 2000
# Three, not two: exploding a two-element config array produces two candidates
# nobody wanted, while the shape this exists for -- a capture of many
# independent records -- is never that small. 130 in the parsec case.
EXPLODE_MIN_ELEMENTS = 3
# Homogeneity is a key-set *intersection*, not identity: real captures carry
# optional fields, and 130 traces where one lacks an `assessments` key are not
# two kinds of thing. Measured on the parsec capture: 12 common keys, zero
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
    roots: Sequence[Path], *, operator_globs: Sequence[str] = ()
) -> tuple[list[Path], list[dict]]:
    """Every file worth cataloguing, and every one dropped with its reason.

    Order matters and is sorted, so `duplicate` always names the *later* of two
    byte-identical paths and two runs over the same corpus produce the same
    catalogue. Returns paths, not digests: digesting is digest.py's job.
    """
    kept: list[Path] = []
    excluded: list[dict] = []
    seen: dict[str, Path] = {}

    for root in roots:
        root = Path(root)
        try:
            if not root.is_dir():
                raise UsageError(f"corpus root is not a directory: {root}")
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
