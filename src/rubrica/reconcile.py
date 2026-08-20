"""The seal: assemble the reconcile partials into one world model.

Code rather than a prompt, for the reason emit is code: two runs with identical
partials must produce a byte-identical world model, or variance stops being
attributable to the pass that caused it. There is a second reason here, specific
to this pipeline's gateway: a code step streams nothing, so it cannot be killed
by the ~300s idle reset that splitting reconcile exists to avoid, however large
the assembled model gets.

This module assembles; it does not check. Cross-artifact checking is layer 2 and
lives in refs.py. What it *does* report is the narrow class that makes assembly
impossible -- a partial that is absent or unparseable, a declared capability with
no outcome classes, an outcome record naming a capability nobody declared -- and
it writes nothing at all when it reports any of them. A half-assembled world
model would be worse than none: it would clear layer 1 for the collections it did
manage to fill.
"""

from __future__ import annotations

from pathlib import Path

from rubrica.artifacts import ArtifactError, read_json, write_json
from rubrica.findings import Finding
from rubrica.paths import RunPaths, list_json

# (RunPaths attribute, the key inside that partial) in the order the passes run,
# so a run missing several partials names the earliest pass first -- the one a
# repair should start from, the same ordering _readable_targets uses.
_SINGLETON_PARTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("capabilities_part", ("capabilities",)),
    ("outcomes_part", ("outcomes",)),
    ("entities_part", ("entities",)),
    ("goals_part", ("actors", "goals")),
    ("gaps_part", ("gaps",)),
)


def _read_part(path: Path, out: list[Finding]) -> dict | None:
    """One partial, or None with a finding naming *that* partial.

    Naming the right artifact is the third rule of the exit-code contract, learned
    the hard way here: check-refs over an unreadable 01-claims/ once reported four
    fabricated `no such claim` findings against a world model that was correct.
    """
    try:
        return read_json(path)
    except ArtifactError as exc:
        out.append(Finding(path, "reconcile", "", str(exc)))
        return None


def seal(run: RunPaths, *, denominator_version: int = 1) -> tuple[Path | None, list[Finding]]:
    """Assemble 01-world-model.json from the partials, or report why it cannot be.

    `denominator_version` is passed in rather than inferred: an amendment costs an
    explicit orchestrator decision recorded in decisions.md, and a seal that
    incremented a version it found on disk would let the number move without one.
    """
    findings: list[Finding] = []

    # The manifest, not a partial, is where `target` comes from. The single-turn
    # stage wrote it itself and nothing ever checked it against the manifest, so
    # sourcing it here removes an unchecked restatement rather than moving one.
    manifest = _read_part(run.manifest, findings)

    parts: dict[str, dict] = {}
    for attribute, _keys in _SINGLETON_PARTS:
        document = _read_part(getattr(run, attribute), findings)
        if document is not None:
            parts[attribute] = document

    contradictions: list[dict] = []
    for path in list_json(run.contradictions_dir):
        part = _read_part(path, findings)
        if part is not None:
            contradictions.extend(part.get("contradictions", []))

    if findings:
        return None, findings

    capabilities = [dict(item) for item in parts["capabilities_part"]["capabilities"]]
    outcomes = {
        entry["capability_id"]: entry["outcome_classes"]
        for entry in parts["outcomes_part"]["outcomes"]
    }
    declared = {capability["id"] for capability in capabilities}

    for capability_id in sorted(set(outcomes) - declared):
        findings.append(
            Finding(
                run.outcomes_part,
                "reconcile",
                "/outcomes",
                f"outcome classes for {capability_id}, which no capability in "
                f"{run.capabilities_part.name} declares",
            )
        )
    for capability in capabilities:
        if capability["id"] not in outcomes:
            findings.append(
                Finding(
                    run.outcomes_part,
                    "reconcile",
                    "/outcomes",
                    f"capability {capability['id']} has no outcome classes; every declared "
                    "capability needs its capability x outcome-class cells, which is what the "
                    "coverage denominator counts",
                )
            )
        else:
            capability["outcome_classes"] = outcomes[capability["id"]]

    if findings:
        return None, findings

    world = {
        "schema_version": "0.1",
        "target": manifest["target"],
        "capabilities": capabilities,
        "entities": parts["entities_part"]["entities"],
        "actors": parts["goals_part"]["actors"],
        "goals": parts["goals_part"]["goals"],
        "contradictions": contradictions,
        "gaps": parts["gaps_part"]["gaps"],
        "denominator": {
            "version": denominator_version,
            # *Distinct* (capability_id, outcome_class_id) pairs, counted off the
            # joined capabilities so the number cannot disagree with the cells it
            # describes. A set, not a sum of per-capability outcome-class counts,
            # because refs.check_world_model recomputes this field as
            # len(refs._cells(world)) and refs._cells is a set comprehension. That
            # recomputation makes the field an identity: whatever is written here
            # has to be what the check derives, or check-refs reports a finding
            # against a world model this seal had just produced. The two spellings
            # agree until a capability id or an outcome-class id repeats, at which
            # point a sum is simply the wrong number -- so do not "simplify" this
            # back to sum(len(c["outcome_classes"]) for c in capabilities).
            "capability_cells": len(
                {
                    (capability["id"], outcome_class["id"])
                    for capability in capabilities
                    for outcome_class in capability["outcome_classes"]
                }
            ),
            "goals": len(parts["goals_part"]["goals"]),
        },
    }
    write_json(run.world_model, world)
    return run.world_model, []
