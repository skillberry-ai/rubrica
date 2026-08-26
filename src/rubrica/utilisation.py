"""Per-artifact claim utilisation: how much of each input reached the world model.

One function in its own module, for `metrics.py`'s stated reason -- the gate in
`refs.py` and the `claim-utilisation` subcommand must never come to disagree
about what utilisation means, and duplicating the arithmetic is how they would.

Utilisation rate is a fact about the *input*, not about the diligence of the
reconcile passes that cite it.
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
    """Per-artifact cited/total counts, or an empty report before the seal.

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
            cited.update(_claim_ids(item.get("claims")))
    # The three nested sites. `$defs/invariant`, `$defs/outcome_class` and
    # `$defs/gap` carried no `claims` array at all until issue #6, so an
    # invariant's provenance had to go on its entity or into `description`
    # prose. Measured on run-20260823-112746 while that was still true:
    # `invariant` claims were cited 0 of 55 times and `outcome_class` 7 of 62,
    # with 24 more appearing only inside prose -- 117 of 434 claims, 27% of
    # the corpus, that this function could not see. Walking the children is
    # what makes those citations structural rather than prose.
    for capability in world.get("capabilities", []):
        for outcome_class in capability.get("outcome_classes", []) or []:
            cited.update(_claim_ids(outcome_class.get("claims")))
    for entity in world.get("entities", []):
        for invariant in entity.get("invariants", []) or []:
            cited.update(_claim_ids(invariant.get("claims")))
    for gap in world.get("gaps", []) or []:
        cited.update(_claim_ids(gap.get("claims")))
    # `refs.check_world_model` (refs.py:464-467) already resolves contradictions[].claim_a
    # and claim_b as claim references -- it reports one as a finding if it does not
    # resolve. A definition of "cited" that excludes them would disagree with that
    # checker in the same module family, and would tell an input whose only surviving
    # contribution is a recorded contradiction that nothing cites it, which is false.
    for contradiction in world.get("contradictions", []):
        for side in ("claim_a", "claim_b"):
            claim_id = contradiction.get(side)
            # isinstance rather than `is not None`, for _claim_ids' reason below:
            # `set.add` raises on an unhashable side exactly as `set.update` did
            # on an unhashable member, and both sides are one hand-edit apart
            # from the arrays above.
            if isinstance(claim_id, str):
                cited.add(claim_id)
    return cited


def _claim_ids(value) -> list[str]:
    """The string members of a `claims` array, or `[]` for anything else.

    Measured on a readable toy run carrying `"claims": [{"a": 1}]` on a gap --
    JSON that parses, and precisely what a hand-edit at gate 1 produces from a
    list of ids: `set.update` raised `TypeError: unhashable type: 'dict'`, and
    cli.py turned that into exit 1 with one fabricated `[internal]` finding for
    `claim-utilisation` and for `gate-brief --gate 1`, which reads this report.
    Both are reports, and a report always exits 0 on a readable run -- so that
    was a violation of the exit-code contract, not a strictness question. Issue
    #6 widened the exposure from four citation sites to seven and `gaps[].claims`
    is the newest of them, but the shape was always reachable.

    A non-list `claims` is dropped whole for `refs._as_list`'s measured reason,
    and a bare string is the sharper case of it: `set.update("clm-api-001")` does
    not raise at all, it iterates the string and adds each character, so a guard
    on truthiness alone would have counted one hand-typed id as nine citations of
    nothing.

    Dropping the malformed member is the only thing this can do, on
    `brief._dicts`' ruling: raising breaks the promise above, and inventing a
    finding is layer 1's job -- `claim_refs` is an array of ids in
    world-model-0.1.json, so `rubrica validate --stage reconcile-seal` names it
    precisely. The dropped member shows up as a claim that resolves against
    nothing, which is what it is.
    """
    if not isinstance(value, list):
        return []
    return [member for member in value if isinstance(member, str)]


def _quietly(path):
    """The document, or None. An unreadable artifact is `check_readable`'s
    finding to report, and duplicating it here would double-count one defect."""
    try:
        return read_json(path)
    except Exception:  # deliberate: an unreadable artifact is check_readable's finding
        return None
