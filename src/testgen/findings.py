"""A single validation finding, shared by every checking layer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    """One problem found in one artifact.

    `pointer` is a JSON Pointer into the artifact, or "" for the document
    root. `layer` names the checking layer that produced it, so a reader can
    tell a shape error from a reference error without parsing the message.

    "internal" is the layer cli.py uses when a checking layer raised instead of
    returning: the artifact is malformed in a way layer 1 must reject first, and
    the exit code still has to carry a line rather than a bare 1.
    """

    artifact: Path
    layer: str  # "schema" | "refs" | "invariant" | "emit" | "internal" | "recall" | "review"
    pointer: str
    message: str

    def __str__(self) -> str:
        where = f"{self.artifact}#{self.pointer}" if self.pointer else str(self.artifact)
        return f"[{self.layer}] {where}: {self.message}"


def format_findings(items: list[Finding]) -> str:
    """Render findings one per line, sorted so output is stable across runs."""
    ordered = sorted(items, key=lambda f: (str(f.artifact), f.pointer, f.layer, f.message))
    return "\n".join(str(f) for f in ordered)
