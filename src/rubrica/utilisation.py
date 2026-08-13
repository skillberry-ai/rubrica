"""Per-artifact claim utilisation: how much of each input reached the world model.

One function in its own module, for `metrics.py`'s stated reason -- the gate in
`refs.py` and the `claim-utilisation` subcommand must never come to disagree
about what utilisation means, and duplicating the arithmetic is how they would.

Utilisation rate is a fact about the *input*, not about rb-reconcile's diligence.
Measured on run-20260812-130056: the ten trajectory slices ran 64-92% while
agent-server-py ran 8% (2 of 25), and the 23 dropped claims were A2A plumbing
rb-reconcile was right to discard. So this module reports and never judges;
exactly one case is a finding, and `refs.check_claim_utilisation` owns it.
"""

from __future__ import annotations

from rubrica.artifacts import read_json
from rubrica.paths import RunPaths, list_json

FORMAT = "rubrica-utilisation/1"


def claim_utilisation(run: RunPaths) -> dict:
    """Per-artifact cited/total counts, or an empty report before reconcile.

    An absent or unreadable world model yields no artifacts rather than every
    claim counted as uncited: `check-refs` runs at every stage gate, and a run
    stopped at extract legitimately has claims and no world model.
    """
    artifacts: list[dict] = []
    cited = _cited_claim_ids(run)
    if cited is None:
        return {"format": FORMAT, "artifacts": artifacts}

    for path in list_json(run.claims_dir):
        payload = _quietly(path)
        if not isinstance(payload, dict):
            continue
        ids = [claim["id"] for claim in payload.get("claims", [])]
        used = sum(1 for claim_id in ids if claim_id in cited)
        artifacts.append(
            {
                "artifact_id": payload.get("artifact_id", path.stem),
                "cited": used,
                "total": len(ids),
                # Integer, not a float: this number is read by a human at gate 1
                # and printed into a report, and a float would make two runs over
                # the same data diff on formatting alone.
                "percent": (100 * used // len(ids)) if ids else 0,
            }
        )
    return {"format": FORMAT, "artifacts": artifacts}


def _cited_claim_ids(run: RunPaths) -> set[str] | None:
    """Every claim id the world model rests on, or None if there is no world model."""
    world = _quietly(run.world_model)
    if not isinstance(world, dict):
        return None
    cited: set[str] = set()
    for group in ("capabilities", "entities", "actors", "goals"):
        for item in world.get(group, []):
            cited.update(item.get("claims", []) or [])
    # `refs.check_world_model` (refs.py:464-467) already resolves contradictions[].claim_a
    # and claim_b as claim references -- it reports one as a finding if it does not
    # resolve. A definition of "cited" that excludes them would disagree with that
    # checker in the same module family, and would tell an input whose only surviving
    # contribution is a recorded contradiction that nothing cites it, which is false.
    for contradiction in world.get("contradictions", []):
        for side in ("claim_a", "claim_b"):
            claim_id = contradiction.get(side)
            if claim_id is not None:
                cited.add(claim_id)
    return cited


def _quietly(path):
    """The document, or None. An unreadable artifact is `check_readable`'s
    finding to report, and duplicating it here would double-count one defect."""
    try:
        return read_json(path)
    except Exception:  # deliberate: an unreadable artifact is check_readable's finding
        return None
