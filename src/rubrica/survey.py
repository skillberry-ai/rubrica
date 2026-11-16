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

import contextlib
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

# Same nine strings as catalogue-0.1.json's exclusion_reason enum. Kept here
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
    "symlink_outside_root",
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


def _is_vcs_name(part: str) -> bool:
    """Whether one path part names a version-control folder, ignoring case.

    Case-blind on purpose: on a case-insensitive volume -- the macOS default --
    `.GIT` *is* the `.git` folder, so an exact match let it through the walk and
    the seed check alike. `casefold` rather than `lower` so the comparison is the
    one Python documents for caseless matching.
    """
    return part.casefold() in _VCS_DIRS


def _vcs_part_of(path: Path) -> str | None:
    """The first VCS folder name in `path` or the path it resolves to, if any.

    Both spellings are checked: the path as given catches `repo/.git` named
    directly, and the resolved one catches a symlink or `..` that lands inside a
    VCS folder while its own spelling does not mention one.
    """
    candidates = [Path(path).absolute()]
    # A resolve failure (a symlink loop) leaves the spelled path to judge;
    # whether the seed is readable at all is decided by the caller.
    with contextlib.suppress(OSError, RuntimeError):
        candidates.append(Path(path).resolve())
    for candidate in candidates:
        for part in candidate.parts:
            if _is_vcs_name(part):
                return part
    return None


def _gitignore_patterns(root: Path) -> list[str]:
    """Patterns from `root/.gitignore`, one level only, as written.

    Deliberately not a full gitignore implementation: nested ignore files are
    a library's job, and getting them subtly wrong would drop evidence
    *silently*, which is the one failure this module exists to prevent. What
    it does catch is the common case -- a top-level ignore listing generated
    and secret files -- and anything it misses stays in the catalogue where
    triage and a human can see it.

    Lines come back in file order, a `!` line with its `!` still on, because
    order is what a `!` line means: `_gitignored` lets the last matching line
    decide. Before that, every `!` line was skipped while the broad line it
    narrowed still applied, so the common "ignore everything, keep a few"
    file (`*`, `!*/`, `!*.py`, ...) dropped every file git keeps -- a bug
    scout's corpus came out empty, the exact failure this module exists to
    prevent.

    These shapes are honoured (see `_gitignored` for how each matches):

    - plain, `x` or `*.log` -- a file, or a folder on the file's path, with
      that name at any depth, so `secrets` drops `a/secrets/k.txt`;
    - anchored, `/x` -- only the path from the root, never a same-named file
      or folder deeper down;
    - folder, `x/` -- every file under a folder matching `x` at any depth, or
      under the one folder at that path when the pattern also starts with `/`
      or has another `/` in it;
    - `**` as a whole segment -- any number of folder levels, as in
      `**/.env`, `logs/**` and `a/**/b`.

    Before the anchored and folder shapes were honoured, `/.env` and
    `secrets/` -- two of the commonest top-level lines -- excluded nothing, and
    a `.env` and a `secrets/key.txt` were catalogued as evidence. When they
    first were, `**` shrank to a single `*` and `secrets` without its slash
    still excluded nothing inside the folder, so a nested `a/b/.env` and
    `secrets/key.txt` were catalogued again.
    """
    ignore = root / ".gitignore"
    # `utf-8-sig` drops one leading byte-order mark, as git does. Read as plain
    # `utf-8`, a file saved with one (Windows Notepad, some editors) kept the
    # mark on its first pattern -- `str.strip()` does not remove U+FEFF -- so
    # `\ufeff.env` matched nothing and a `.env` git ignores was catalogued.
    try:
        text = ignore.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return []
    patterns = []
    for raw in text.splitlines():
        line = raw.strip()
        # A line that is only slashes names no file; kept, it would strip to an
        # empty pattern, which matches nothing useful at best and everything
        # under the root at worst. The same holds after a `!`, so a bare `!`
        # or `!/` is skipped too.
        if line.startswith("#") or not line.removeprefix("!").strip("/"):
            continue
        patterns.append(line)
    return patterns


def _segments_match(segments: Sequence[str], pattern: Sequence[str]) -> bool:
    """`segments` match `pattern` one folder level per segment, `**` aside.

    Segment by segment rather than one fnmatch over the joined path, because
    fnmatch's `*` crosses `/`: `/*.env` over the whole path would also drop
    `sub/x.env`, which an anchored pattern exists precisely not to do.

    A segment that is exactly `**` stands for any number of folder levels, as
    in git: zero or more at the start or in the middle (`**/.env` drops `.env`
    and `a/b/.env`; `a/**/b` drops `a/b/f`), one or more at the end (`logs/**`
    drops everything inside `logs` but not a file called `logs`). Before this,
    `**` was a single `*`, and a nested `a/b/.env` was catalogued as evidence.

    A table rather than recursion: a hostile `.gitignore` full of `**` lines
    would make naive backtracking exponential in the path depth, and this runs
    once per file in the corpus. The table is len(segments) x len(pattern).
    """
    n, m = len(segments), len(pattern)
    # reach[j] -- whether the first i segments match the first j pattern parts.
    reach = [False] * (m + 1)
    reach[0] = True
    for j in range(1, m + 1):
        # A `**` that is not the last part may match zero segments.
        reach[j] = reach[j - 1] and pattern[j - 1] == "**" and j < m
    for i in range(1, n + 1):
        nxt = [False] * (m + 1)
        for j in range(1, m + 1):
            part = pattern[j - 1]
            if part == "**":
                # Take this segment into the `**` (staying on it, or entering
                # it from before), or -- unless last -- let it match nothing.
                nxt[j] = reach[j] or reach[j - 1] or (j < m and nxt[j - 1])
            else:
                nxt[j] = reach[j - 1] and fnmatch.fnmatch(segments[i - 1], part)
        reach = nxt
    return reach[m]


def _gitignored(relative: str, patterns: Sequence[str]) -> bool:
    """Whether `relative` (a corpus-relative POSIX path) is matched by `patterns`.

    What is honoured, each as git does it:

    - a pattern matches the file itself, or any folder on the file's path --
      so `secrets` and `/creds` drop every file inside a folder of that name,
      and `x/` matches folders only, never a file called `x`;
    - a pattern with no `/` but a trailing one matches at any depth; a leading
      `/`, or a `/` anywhere but the end, ties it to the root (`/creds` drops
      `creds/t.txt`, not `sub/creds/t.txt`);
    - `*`, `?` and `[...]` stay within one folder level; `**` as a whole
      segment spans any number of them (see `_segments_match`).

    - a line starting with `!` re-includes what it matches, and the last line
      that matches decides, so `docs/*` then `!docs/api.md` keeps `api.md`
      while `!x` then `x` still drops `x`.

    One git rule is deliberately not honoured: git cannot re-include a file
    whose parent folder is excluded, so under `*` then `!*/` it still drops
    `docs/other.txt` (the file itself matches `*`), where this keeps it
    because `!*/` was the last line to match something on its path. Leaving
    that rule out only ever errs toward *keeping* a file, which is this
    module's safe side: a file kept by mistake is seen at gate 0, a file
    dropped by mistake is gone. Nested `.gitignore` files are not honoured.
    """
    parts = [part for part in relative.split("/") if part]
    ignored = False
    for line in patterns:
        negate = line.startswith("!")
        pattern = line[1:] if negate else line
        folder_only = pattern.endswith("/")
        body = pattern.strip("/")
        # As in git: a leading `/`, or a `/` anywhere but the end, ties the
        # pattern to the root instead of letting it match at any depth.
        anchored = pattern.startswith("/") or "/" in body
        segments = [segment for segment in body.split("/") if segment]
        if not segments:
            continue
        if not anchored:
            # An unanchored name is an anchored one under any number of folders.
            segments = ["**", *segments]
        # Each folder on the path, as its path from the root; then the file
        # itself, unless the pattern names folders only. A file is ignored when
        # it, or any folder it sits in, is.
        last = len(parts) - 1 if folder_only else len(parts)
        if any(_segments_match(parts[:k], segments) for k in range(1, last + 1)):
            # Last match wins, as in git; with no `!` lines this is "any line
            # matches", exactly the rule before negation was honoured.
            ignored = not negate
    return ignored


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
    only: Sequence[Path] | None = None,
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

    `only` is the files a human named one by one, all under the single root
    passed with it, and replaces the walk of that root. A named file skips the
    filters that judge a file by *where* it sits -- version control, vendored
    folders, the root's .gitignore, `--exclude` -- because the human pointed at
    it on purpose and those filters exist to drop what nobody chose. It keeps
    the ones that judge *what* it is (lockfile, binary, unreadable, duplicate),
    each still recorded, so a named file that cannot be a candidate is visible
    as declined rather than missing. A named file inside a version-control
    folder never reaches here from survey(): `_seed_roots` refuses it first.
    """
    kept: list[Path] = []
    excluded: list[dict] = []
    if seen is None:
        seen = {}

    if only is not None:
        if len(roots) != 1:
            raise UsageError("walk_corpus takes `only` with exactly one root")
        root = Path(roots[0])
        for path in sorted(Path(p) for p in only):
            _keep_or_drop(path, path.relative_to(root).as_posix(), kept, excluded, seen)
        return kept, excluded

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
            walked, unlistable = _walk_files(root)
        except OSError as exc:
            # An unreadable *root* is the harness pointed at something it cannot
            # read, which is exit 2 -- the same call paths.list_dir makes, and
            # for the same reason: a swallowed EACCES here would report an empty
            # corpus rather than an unreadable one.
            raise UsageError(f"cannot read corpus root: {root} ({exc})") from exc

        ignore_patterns = _gitignore_patterns(root)
        resolved_root = _resolve_or_none(root)

        # A folder below the root that could not be listed is recorded rather
        # than skipped: rglob used to swallow its PermissionError, so every
        # file inside was in neither `kept` nor `excluded` -- measured on
        # `c/locked/spec.md` under a `chmod 000 c/locked`, which came back as
        # ([a.md], []). Its path is the folder's, since its files cannot be
        # named, and a folder inside version control or a vendored tree keeps
        # the reason its files would have got, so the tally does not change
        # meaning when a mode bit does.
        for folder in unlistable:
            folder_parts = set(folder.relative_to(root).parts)
            if any(_is_vcs_name(part) for part in folder_parts):
                reason = "vcs_metadata"
            elif folder_parts & _VENDOR_DIRS:
                reason = "vendored"
            else:
                reason = "unreadable"
            excluded.append({"path": folder.relative_to(root).as_posix(), "reason": reason})

        for path in walked:
            relative = path.relative_to(root).as_posix()
            parts = set(path.relative_to(root).parts)

            def drop(reason: str, rel: str = relative) -> None:
                excluded.append({"path": rel, "reason": reason})

            # rglob does not descend into a symlinked folder, but is_file()
            # follows a symlinked *file*, so a link in the corpus pointing at
            # ~/.ssh/id_rsa or a credentials file was read, hashed and
            # catalogued as evidence. A link whose target lands outside this
            # root is declined before anything opens it -- recorded, not
            # dropped silently, because the corpus owner may have meant it.
            # A link to a file inside the root is kept, but judged by where its
            # target sits as well as by its own spelling, so `notes -> .git/config`
            # is still `vcs_metadata` and `notes.md -> .env` is still `gitignored`
            # when `.env` is.
            if path.is_symlink():
                target = _resolve_or_none(path)
                if (
                    target is None
                    or resolved_root is None
                    or not target.is_relative_to(resolved_root)
                ):
                    drop("symlink_outside_root")
                    continue
                target_relative = target.relative_to(resolved_root)
                parts |= set(target_relative.parts)
                # The name-and-path checks below must see the target too, not
                # only the link's own spelling: before this, `notes.md -> .env`
                # catalogued a gitignored `.env`'s contents as `notes.md`, and
                # `alias.txt -> real.md` got past `--exclude real.md`. The
                # reason recorded is still the one an ordinary file would get.
                spellings = [relative, target_relative.as_posix()]
            else:
                spellings = [relative]

            if any(_is_vcs_name(part) for part in parts):
                drop("vcs_metadata")
                continue
            if parts & _VENDOR_DIRS:
                drop("vendored")
                continue
            if any(Path(rel).name in _LOCKFILES for rel in spellings):
                drop("lockfile")
                continue
            if operator_globs and any(_matches_any(rel, operator_globs) for rel in spellings):
                drop("operator_excluded")
                continue
            if ignore_patterns and any(_gitignored(rel, ignore_patterns) for rel in spellings):
                drop("gitignored")
                continue
            _keep_or_drop(path, relative, kept, excluded, seen, lockfile_checked=True)

    return kept, excluded


def _walk_files(root: Path) -> tuple[list[Path], list[Path]]:
    """Every file under `root`, sorted, and every folder below it that could not be listed.

    os.walk rather than rglob because rglob gives no way to learn that it
    skipped a folder it could not list. `followlinks=False` keeps rglob's rule
    that a symlinked folder is never descended into; a symlinked *file* still
    appears and is_file() still follows it, so the symlink checks the caller
    makes see exactly what they saw before. The sort is over the same Path
    objects rglob produced, so the order -- and so which of two identical
    files is the `duplicate` -- is unchanged.
    """
    unlistable: list[Path] = []

    def note(exc: OSError) -> None:
        if exc.filename is not None:
            unlistable.append(Path(exc.filename))

    files: list[Path] = []
    for folder, _dirnames, filenames in root.walk(on_error=note, follow_symlinks=False):
        # A symlinked folder is listed without being entered; rglob yielded it
        # too and is_file() rejected it, so the filter below drops it the same way.
        files.extend(folder / name for name in filenames)
    walked = sorted(p for p in files if p.is_file())
    # The root's own listing failure is the caller's exit 2, raised by its
    # forced iterdir() before this runs; anything left here is below it.
    return walked, sorted(p for p in unlistable if p != root)


def _resolve_or_none(path: Path) -> Path | None:
    """`path` with every symlink followed, or None when that cannot be done.

    None (a loop, a vanished target) is treated by the caller as a target it
    cannot place inside the root, which is the safe side to fail on.
    """
    try:
        return Path(path).resolve(strict=True)
    except (OSError, RuntimeError):
        return None


def _keep_or_drop(
    path: Path,
    relative: str,
    kept: list[Path],
    excluded: list[dict],
    seen: dict[str, Path],
    *,
    lockfile_checked: bool = False,
) -> None:
    """The checks on what a file *is*, shared by the walk and by a named file."""
    if not lockfile_checked and path.name in _LOCKFILES:
        excluded.append({"path": relative, "reason": "lockfile"})
        return
    try:
        if _looks_binary(path):
            excluded.append({"path": relative, "reason": "binary"})
            return
        digest = sha256_of(path)
    except OSError:
        # One bad mode in a user tree must not abort the inventory. The
        # file is recorded as declined, so it is visible rather than
        # absent -- which is the whole rule this module is built on.
        excluded.append({"path": relative, "reason": "unreadable"})
        return
    if digest in seen:
        excluded.append({"path": relative, "reason": "duplicate"})
        return
    seen[digest] = path
    kept.append(path)


def _seed_roots(seeds: Sequence[Path]) -> list[tuple[Path, list[Path] | None]]:
    """Each `--corpus` path as a (root, named files) pair, in the order given.

    A folder is a root walked whole (`None`). Files are grouped under their
    parent folder, which becomes a root walked over exactly those files, so
    `request.corpus_roots` stays a list of folders and every reader that joins
    `roots[root_index] / path` -- intake above all -- resolves a named file
    unchanged. A path that is neither, or a file that cannot be opened, is the
    harness pointed at something it cannot read: exit 2 before any run exists,
    like an unreadable folder root.

    A seed that is, or sits inside, a version-control folder is refused the
    same way. A named file skips the walk's VCS filter on purpose, and a folder
    seed is filtered only on the parts *below* it, so without this check
    `--corpus repo/.git` catalogued `config`, `HEAD` and the hooks as evidence --
    and `.git/config` is where remote credentials live. Refusing rather than
    recording a decline because the seed is the whole request: there is no
    run worth minting from a VCS folder, and exit 2 is what an unreadable root
    already gets. The name match ignores case, as the walk's does.
    """
    out: list[tuple[Path, list[Path] | None]] = []
    by_parent: dict[Path, list[Path]] = {}
    for seed in seeds:
        # Absolute once, here, before anything is grouped or recorded: the
        # catalogue outlives the folder survey ran from, and intake joins
        # `corpus_roots[i] / path` against its *own* cwd. A relative root --
        # `.` for a bare `--corpus notes.md` -- then failed with a bare
        # FileNotFoundError, or read a different same-named file. `absolute()`
        # rather than `resolve()` so a symlinked folder root is recorded as
        # spelled; a symlinked named file is still resolved below.
        seed = Path(seed).absolute()
        vcs = _vcs_part_of(seed)
        if vcs is not None:
            raise UsageError(
                f"corpus path is or sits inside a version-control folder ({vcs}): {seed}"
            )
        if seed.is_dir():
            out.append((seed, None))
            continue
        if not seed.is_file():
            raise UsageError(f"corpus path is neither a file nor a directory: {seed}")
        if seed.is_symlink():
            target = _resolve_or_none(seed)
            if target is None:
                raise UsageError(f"cannot resolve corpus file symlink: {seed}")
            seed = target
        try:
            with seed.open("rb"):
                pass
        except OSError as exc:
            raise UsageError(f"cannot read corpus file: {seed} ({exc})") from exc
        parent = seed.parent
        if parent not in by_parent:
            by_parent[parent] = []
            out.append((parent, by_parent[parent]))
        if seed not in by_parent[parent]:
            by_parent[parent].append(seed)
    return out


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
    roots = _seed_roots(corpus_roots)
    for root_index, (root, named) in enumerate(roots):
        kept, root_excluded = walk_corpus(
            [root], operator_globs=operator_globs, seen=seen, only=named
        )
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
                #
                # A conversation is exempt, and the parse happens here rather
                # than inside the `explode` call so this check can see what was
                # parsed. A trajectory is one episode whose records are turns,
                # not a container of independent records -- message 7 is
                # unreadable without 1 through 6, the same shape the OpenAPI
                # ruling keeps whole. Exploding one is doubly wrong: the file
                # candidate, the only row carrying the behavioural digest
                # `_trace_digest_from_messages` produces, gets `admissible:
                # False` because a container may not be admitted, and each
                # message is admitted instead as its own candidate, which
                # `classify_payload` calls `other` and digests to a one-turn
                # skeleton with no tool name, no request text and no sibling
                # context.
                #
                # Measured on the four metadata-rich airline result files under
                # tau2-bench's `data/tau2/results/final`, and scoped to them by
                # name because the per-file totals vary -- an unqualified
                # file-dependent figure is unfalsifiable. Invariant across all
                # four: the per-episode key intersection is exactly 4 on all 200
                # episodes, all 200 carry at least 3 messages, and so 200 of 200
                # satisfy `EXPLODE_MIN_COMMON_KEYS` in every one of them. Only
                # the size of the wreckage varies -- 4,374 to 5,800 message rows,
                # so 4,574 to 6,000 candidates against a DEFAULT_MAX_CANDIDATES
                # of 500, an order of magnitude past the cap in all four.
                #
                # Gated on `is_message_list` and deliberately never on
                # `kind == "trace"`: a parsec-shaped list of `{spans, trace_id}`
                # records classifies `trace` too and must keep exploding.
                # Measured on this repository's three exploding JSON fixtures
                # (corpus-toy/capture.json and both reservation-trajectories
                # files): `is_message_list` is False for all three, so this gate
                # changes no corpus already surveyed here.
                try:
                    parsed = json.loads(path.read_text(encoding="utf-8"))
                    if not digest_module.is_message_list(parsed):
                        exploded = explode(parsed)
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
        "corpus_roots": [str(root) for root, _ in roots],
        "limits": {"max_rounds": max_rounds, "max_scenarios": max_scenarios},
    }
    # What a human named file by file, so a root that is only a named file's
    # folder does not read as "this whole folder was surveyed".
    seed_files = [str(path) for _, named in roots for path in named or []]
    if seed_files:
        request["seed_files"] = seed_files
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
