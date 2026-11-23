"""Reading and writing run artifacts.

Artifacts are the only channel between pipeline stages, so their on-disk form
has to be stable: two runs that produce the same content must produce
byte-identical files, or diff-runs reports formatting as variance. Hence
sort_keys and a fixed indent.

Writes are atomic because a stage that dies mid-write must not leave a
half-written artifact that the next stage would read as valid JSON.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


class ArtifactError(Exception):
    """Raised when an artifact is missing or is not readable JSON."""


def read_json(path: Path | str) -> Any:
    """Read one artifact, raising ArtifactError with the path on any failure."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ArtifactError(f"missing artifact: {path}") from exc
    except UnicodeDecodeError as exc:
        # Bytes that are not UTF-8 at all are malformed content, exactly like
        # JSON that does not parse, and belong in the same ArtifactError so the
        # finding names *this* path. Measured before this line existed:
        # `validate --stage triage-slices` over a 00-slices.json holding
        # b"\xff\xfe\x00bogus" exited 1 with an [internal] finding anchored on
        # the run root, whose advice was to "run `rubrica validate --stage
        # <stage>` ... and repair the artifact it names" -- circular, since that
        # was the command being run, and the one path it needed to name was
        # already in hand here. UnicodeDecodeError is a ValueError, not an
        # OSError, so it reached cli.py's catch-all rather than either handler
        # that knows a path.
        raise ArtifactError(f"not UTF-8 text: {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ArtifactError(f"malformed JSON in {path}: {exc}") from exc


def read_json_or_none(path: Path | str, *, quiet: bool = False) -> Any | None:
    """Read one artifact, or None when it cannot be read -- in one of two senses.

    Default (`quiet=False`), for the checkers and code stages (refs, emit,
    review, stability): only ArtifactError becomes None -- absent, not UTF-8, or
    malformed JSON, which is "that stage has not run yet" or some other check's
    finding. Anything else, PermissionError above all, still propagates, so
    cli.py maps an unreadable run to exit 2 rather than a check quietly treating
    a chmod-000 file as absent and reporting fabricated findings against the
    wrong artifact.

    `quiet=True`, for the reports (brief, utilisation, the console): *any*
    exception becomes None. A report is never a gate; an unreadable artifact is
    validate's or check-refs' finding to report, and repeating it here would
    double-count one defect and, worse, make a report crash instead of stating
    what it could not read.
    """
    if quiet:
        try:
            return read_json(path)
        except Exception:  # deliberate: see the docstring
            return None
    try:
        return read_json(path)
    except ArtifactError:
        return None


def sha256_of(path: Path | str) -> str:
    """Hex digest of a file's bytes, streamed so a large trace is fine."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(payload: Any) -> bytes:
    """The canonical on-disk form of an artifact, as bytes.

    Separate from write_json because survey needs the *digest* of a container
    element before any file exists, and intake materialises that same element
    later. Two spellings of "the canonical form" would make every exploded
    input's sha256 mismatch after materialisation.
    """
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def write_json(path: Path | str, payload: Any) -> None:
    """Write `payload` atomically in the canonical artifact format.

    Serialization happens before any filesystem mutation, so an unserializable
    payload leaves the previous content and the directory untouched.
    """
    path = Path(path)
    body = canonical_bytes(payload).decode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def append_decision(path: Path | str, entry: str) -> None:
    """Append one orchestrator decision to decisions.md.

    decisions.md is the run's append-only lab notebook; it is never rewritten,
    so this is a plain append rather than an atomic replace.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # A person hand-editing decisions.md can save it without a final newline, and a
    # plain append then glues the new entry onto their last line -- the console's
    # gate reader needs each entry to start its own line with `- `, so an Approve
    # written that way left the gate open. Only the last byte is read, in binary:
    # decoding the whole file would make one non-UTF-8 byte a human typed (T-81)
    # fail every later append.
    lead = "" if _ends_cleanly(path) else "\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(lead + entry.rstrip("\n") + "\n")


def _ends_cleanly(path: Path) -> bool:
    """True when appending to `path` needs no leading newline.

    That is: the file is missing, empty, or already ends with "\\n". A file that
    cannot be read (write-only, say) is treated as clean, so this check never
    turns an append that would have succeeded into a failure; the open for append
    that follows still reports a real permission problem as before.
    """
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            if fh.tell() == 0:
                return True
            fh.seek(-1, os.SEEK_END)
            return fh.read(1) == b"\n"
    except OSError:
        return True


# The two type guards every reader of an artifact's *elements* needs. They live
# here because `brief`, `utilisation` and `refs` all import this module and it
# imports none of them back: `refs` imports `claim_utilisation`, so a guard kept
# in `refs` cannot be imported by `utilisation` without a circular import, and
# three local copies of one guard is how half a module's isinstance checks came
# to disagree with the other half.


def dict_members(value: Any) -> list[dict]:
    """The dict members of `value`, or `[]` if it is not a list at all.

    `read_json_or_none` only guards the document; a reader that then indexes into
    that document's *elements* with a bare `.get` needs this too. Measured in
    `brief.py`: a triage record carrying `"deficiencies": ["oops-a-string"]` --
    which is precisely the shape a human hand-editing the document gate 0 invites
    them to hand-edit produces -- raised `AttributeError: 'str' object has no
    attribute 'get'` and turned `gate-brief` into a fabricated `[internal]`
    finding at exit 1.

    Measured again in `utilisation.py`, one level up: on a readable world model,
    every one of `capabilities`, `entities`, `actors`, `goals`, `gaps`,
    `contradictions`, `capabilities[].outcome_classes` and
    `entities[].invariants` set to `"nope"` or `["nope"]` raised
    `AttributeError: 'str' object has no attribute 'get'` -- a bare string is the
    shape that does not fail loudly, since iterating it yields characters that
    then reach `.get` -- and an integer raised `TypeError: 'int' object is not
    iterable`. Both `claim-utilisation` and `gate-brief` exited 1 with one
    fabricated `[internal]` finding. Three of those eight containers -- `gaps`,
    `outcome_classes` and `invariants` -- are walks added when the read-coverage
    variance was closed, so those crashes were through a path that build created
    rather than one it inherited.

    That is two promises at once: `gate_brief` never raises on a readable run's
    *content*, and the exit-code contract's ruling for a report (claim-
    utilisation's, restated at cli.py's gate-brief arm) is that it always exits 0
    on a readable run, so an orchestrator reading its code cannot mistake data
    for a defect. A layer-2 checker that raises degrades to an `internal` finding
    at exit 1, which is bad but is still a finding, while a **report** has no
    findings channel at all -- so a raise there is a violation of the exit-code
    contract rather than a strict reading of a malformed document.

    Silently dropping the malformed element is deliberate and is the *only* thing
    this can do: raising breaks the promise above, and inventing a finding is
    `validate`'s job -- run `rubrica validate --stage triage` and the schema
    names it precisely. Each caller states the count it rendered, so a dropped
    element shows up as a number that disagrees with the file.
    """
    if not isinstance(value, list):
        return []
    return [member for member in value if isinstance(member, dict)]


def str_members(value: Any) -> list[str]:
    """The string members of `value`, or `[]` if it is not a list at all.

    `dict_members`' sibling, for the fields whose elements are ids rather than
    objects -- `candidate_ids`, `other_slices`, a surface's `evidence`, a
    `claims` array. The same measured failure applies: a hand-edited
    `"other_slices": "s02"` is a string, iterating it yields characters, and
    every one of them would be counted as a slice holding the group.

    Measured on a readable toy run carrying `"claims": [{"a": 1}]` on a gap --
    JSON that parses, and precisely what a hand-edit at gate 1 produces from a
    list of ids: `set.update` raised `TypeError: unhashable type: 'dict'` in
    `utilisation.py`, and cli.py turned that into exit 1 with one fabricated
    `[internal]` finding for `claim-utilisation` and for `gate-brief --gate 1`,
    which reads that report. Both are reports, and a report always exits 0 on a
    readable run -- so that was a violation of the exit-code contract, not a
    strictness question. Closing the read-coverage variance widened the exposure
    from four citation sites to seven and `gaps[].claims` is the newest of them,
    but the shape was always reachable.

    A non-list is dropped whole for `refs._as_list`'s measured reason, and a bare
    string is the sharper case of it: `set.update("clm-api-001")` does not raise
    at all, it iterates the string and adds each character, so a guard on
    truthiness alone would have counted one hand-typed id as nine citations of
    nothing.

    Dropping the malformed member is the only thing this can do, on
    `dict_members`' ruling: raising breaks the promise above, and inventing a
    finding is layer 1's job -- `claim_refs` is an array of ids in
    world-model-0.1.json, so `rubrica validate --stage reconcile-seal` names it
    precisely. The dropped member shows up as a claim that resolves against
    nothing, which is what it is.
    """
    if not isinstance(value, list):
        return []
    return [member for member in value if isinstance(member, str)]
