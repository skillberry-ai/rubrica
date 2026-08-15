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
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ArtifactError(f"malformed JSON in {path}: {exc}") from exc


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

    decisions.md is the run's append-only lab notebook (design spec section
    4); it is never rewritten, so this is a plain append rather than an
    atomic replace.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(entry.rstrip("\n") + "\n")
