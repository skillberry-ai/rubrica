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
    The layers: "schema" | "refs" | "invariant" | "emit" | "reconcile" |
    "internal" | "recall" | "review" | "skill" | "seal".

    "internal" is the layer cli.py uses when a checking layer raised instead of
    returning: the artifact is malformed in a way layer 1 must reject first, and
    the exit code still has to carry a line rather than a bare 1. "skill" is
    skills.check_contract's and check_all's layer: the artifact is a SKILL.md
    rather than a run artifact, and the check is against the code that owns
    each declared name rather than against a schema.

    "reconcile" is reconcile.seal's layer: the artifacts are the world-model partials
    and the failure is that they cannot be assembled at all -- a partial absent or
    unparseable, a declared capability with no outcome classes. Distinct from
    "refs" because refs checks a run someone may still be building, while this
    names the reason one command produced no output.

    "seal" is triage_seal's own layer: seal.py assembles rather than checks,
    but reports a narrow refusal class where assembly cannot faithfully
    represent what it was handed (see that module's docstring), and those
    findings need a layer name distinct from "refs" precisely because they
    fire *before* the record refs.check_triage would otherwise check exists
    at all.
    """

    artifact: Path
    layer: str
    pointer: str
    message: str

    def __str__(self) -> str:
        where = f"{self.artifact}#{self.pointer}" if self.pointer else str(self.artifact)
        return f"[{self.layer}] {where}: {self.message}"


def format_findings(items: list[Finding]) -> str:
    """Render findings one per line, sorted so output is stable across runs."""
    ordered = sorted(items, key=lambda f: (str(f.artifact), f.pointer, f.layer, f.message))
    return "\n".join(str(f) for f in ordered)
