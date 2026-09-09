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
    "internal" | "recall" | "review" | "skill" | "seal" | "rounds" |
    "interfaces".

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

    "rounds" is rounds.py's layer: the artifacts are the propose parts and the
    score parts, and the failure is that they cannot be assembled at all -- two
    parts claiming one scenario id, a ruling for a scenario no part wrote, a
    part that does not parse. Distinct from "refs" for the reason "reconcile"
    is: refs checks a run someone may still be building, while this names the
    reason one command produced no output. Distinct from "seal" and "reconcile"
    because a reader triaging a failed round needs to know which assembler
    refused without reading the message.

    "interfaces" is interfaces.synthesise's layer: the artifacts are
    01-services.json and the claims files it cites, and the failure is that no
    OpenAPI document can be derived at all -- a services part absent or
    unparseable, a service id that is not a usable filename, a tool name the
    harness would rewrite, a `schema_claim` no claim in 01-claims/ has an id for.
    A `schema_claim` naming a claim that exists and carries no usable payload is
    the one finding in this layer that names a *claims* file instead, because that
    payload is rb-extract's output and the part citing it may be correct.
    Distinct from "refs" for the reason "reconcile" and "rounds" are: refs checks
    a run someone may still be building, while this names the reason one command
    produced no output. Distinct from those two because synthesis is a
    *derivation* rather than an assembly of staged parts, so a reader triaging a
    failed 01 band needs to know it was the derivation that refused and not one of
    the seals.
    """

    artifact: Path
    layer: str
    pointer: str
    message: str
    # Last and defaulted, so every one of the existing constructions keeps
    # working unchanged. True only where a check consulted waivers.WAIVABLE_CHECKS
    # and found a human's waiver for this finding's (check, subject) pair.
    #
    # The finding is still reported. A waiver removes its contribution to the
    # exit code and nothing else -- see cli._report, which is the one place that
    # distinction is applied.
    waived: bool = False

    def __str__(self) -> str:
        where = f"{self.artifact}#{self.pointer}" if self.pointer else str(self.artifact)
        line = f"[{self.layer}] {where}: {self.message}"
        return f"[waived] {line}" if self.waived else line


def format_findings(items: list[Finding]) -> str:
    """Render findings one per line, sorted so output is stable across runs."""
    ordered = sorted(items, key=lambda f: (str(f.artifact), f.pointer, f.layer, f.message))
    return "\n".join(str(f) for f in ordered)
