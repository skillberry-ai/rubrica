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

from rubrica.artifacts import dict_members, read_json_or_none, str_members
from rubrica.paths import RunPaths, list_json

FORMAT = "rubrica-utilisation/1"


def claim_utilisation(run: RunPaths) -> dict:
    """Per-artifact cited/total counts, or an empty report before the seal.

    An absent or unreadable world model yields no artifacts rather than every
    claim counted as uncited: `check-refs` runs at every stage gate, and a run
    stopped at extract legitimately has claims and no world model.

    A claims file that is listed but does not read as a JSON object -- broken
    JSON, a top-level array, a file the process may not open -- is named under
    `unreadable` rather than skipped. Skipping it was silent: gate 1 lost the
    input's row and nothing else changed, while `validate --stage extract` named
    the defect. The key is present only when something was unreadable, so the
    report over a fully readable run is byte-for-byte what it was before.
    """
    artifacts: list[dict] = []
    unreadable: list[str] = []
    cited = _cited_claim_ids(run)
    if cited is None:
        return {"format": FORMAT, "artifacts": artifacts}

    for path in list_json(run.claims_dir):
        payload = _quietly(path)
        if not isinstance(payload, dict):
            # The file name, not a guessed artifact id: there is no readable
            # `artifact_id` to take, and the name is what a reader opens next.
            unreadable.append(path.name)
            continue
        # Deliberately *not* guarded, unlike the world-model reads in
        # `_cited_claim_ids` below. A malformed `01-claims/` member raises here --
        # `claim["id"]` on a string is `TypeError: string indices must be
        # integers`, a claim dict with no `id` is `KeyError: 'id'`, `"claims": 7`
        # is `TypeError: 'int' object is not iterable` -- and `summary.utilisation`
        # catches them there to render "present but unreadable" on the run-summary
        # page. That guard is in summary.py by ruling
        # (`test_utilisation_is_a_marker_rather_than_raising_on_a_readable_run`
        # records it), so widening it here would delete a measured signal from
        # another surface rather than add one.
        #
        # The exit-0 contract argument that widened the world-model reads below
        # reaches these reads just as far: they are the same breach, two reports at
        # exit 1 on a readable run. What keeps them unguarded is scope, not the
        # contract -- closing the read-coverage variance (docs/design/findings.md)
        # widened the world-model walk and never touched this path, and only that
        # half was ruled in -- so this is a live hole, and the ruling that parks it
        # belongs in docs/design/limitations.md rather than only in a comment here.
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
    report: dict = {"format": FORMAT, "artifacts": artifacts}
    if unreadable:
        report["unreadable"] = unreadable
    return report


def _cited_claim_ids(run: RunPaths) -> set[str] | None:
    """Every claim id the world model rests on, or None if there is no world model."""
    world = _quietly(run.world_model)
    if not isinstance(world, dict):
        return None
    cited: set[str] = set()
    for group in ("capabilities", "entities", "actors", "goals"):
        for item in dict_members(world.get(group)):
            cited.update(str_members(item.get("claims")))
    # The three nested sites. `$defs/invariant`, `$defs/outcome_class` and
    # `$defs/gap` carried no `claims` array at all until the read-coverage variance
    # was closed, so an invariant's provenance had to go on its entity or into
    # `description` prose. Measured on run-20260823-112746 while that was still
    # true: `invariant` claims were cited 0 of 55 times and `outcome_class` 7 of
    # 62, with 24 more appearing only inside prose -- 117 of 434 claims, 27% of the
    # corpus, that this function could not see. Walking the children is what makes
    # those citations structural rather than prose.
    for capability in dict_members(world.get("capabilities")):
        for outcome_class in dict_members(capability.get("outcome_classes")):
            cited.update(str_members(outcome_class.get("claims")))
    for entity in dict_members(world.get("entities")):
        for invariant in dict_members(entity.get("invariants")):
            cited.update(str_members(invariant.get("claims")))
    for gap in dict_members(world.get("gaps")):
        cited.update(str_members(gap.get("claims")))
    # `refs.check_world_model` (refs.py:1920-1923, its `/contradictions/` loop)
    # already resolves contradictions[].claim_a
    # and claim_b as claim references -- it reports one as a finding if it does not
    # resolve. A definition of "cited" that excludes them would disagree with that
    # checker in the same module family, and would tell an input whose only surviving
    # contribution is a recorded contradiction that nothing cites it, which is false.
    for contradiction in dict_members(world.get("contradictions")):
        for side in ("claim_a", "claim_b"):
            claim_id = contradiction.get(side)
            # isinstance rather than `is not None`, for `artifacts.str_members`' reason:
            # `set.add` raises on an unhashable side exactly as `set.update` did
            # on an unhashable member, and both sides are one hand-edit apart
            # from the arrays above.
            if isinstance(claim_id, str):
                cited.add(claim_id)
    return cited


def _quietly(path):
    """The document, or None. An unreadable artifact is `check_readable`'s
    finding to report, and duplicating it here would double-count one defect."""
    return read_json_or_none(path, quiet=True)
