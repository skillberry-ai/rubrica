"""The refusal conditions, asserted against a recorded live dispatch.

Marked live because the assertion needs a model's output, and pytest cannot
dispatch a subagent. So the controller runs the dispatch per
docs/running-a-stage-by-hand.md and commits the resulting world model under
tests/fixtures/<name>/recorded/01-world-model.json.

**The recording is committed on purpose.** A refusal observed once and never
again is exactly the decorative refusal condition section 9 warns about; a
committed recording makes it a regression test instead. The cost is that a
recording is evidence of what the skill did *at one commit* -- so changing a
skill obliges re-recording, and that re-recording is a reviewable diff rather
than a silent drift.
"""

from __future__ import annotations

import pytest

from testgen.artifacts import read_json
from tests.toy import CONTRADICTION_DIR, GAP_DIR

pytestmark = pytest.mark.live

RECORDED = "recorded/01-world-model.json"
RERECORD = (
    "no recorded reconcile output. Produce one with the dispatch in "
    "docs/running-a-stage-by-hand.md against {fixture}, then commit it to {path}."
)


def _recorded(fixture):
    path = fixture / RECORDED
    if not path.is_file():
        pytest.skip(RERECORD.format(fixture=fixture, path=path))
    return read_json(path)


def test_a_self_contradictory_input_pair_produces_an_unresolved_contradiction():
    """Section 9's first negative: the pair must produce a contradictions entry.

    `unresolved` specifically, because this fixture offers nothing that would
    let either side be preferred -- test_the_contradiction_fixture_offers_no_way
    _to_prefer_one_side is what keeps that true. A world model that picked a side
    has silently resolved a real disagreement, which is the failure the
    extract/reconcile split exists to prevent.
    """
    world = _recorded(CONTRADICTION_DIR)
    contradictions = world.get("contradictions", [])
    assert contradictions, "tg-reconcile recorded no contradiction for a contradictory pair"
    resolutions = {entry["resolution"] for entry in contradictions}
    assert "unresolved" in resolutions, (
        f"the contradiction was resolved as {sorted(resolutions)}, but nothing in the "
        "fixture licenses preferring either side"
    )


def test_an_input_with_error_semantics_removed_produces_a_gap_blocking_propose():
    """Section 9's second negative, and the one a helpful model fails: with no
    error semantics stated anywhere, the tempting output is a world model that
    invents them -- after which every downstream stage treats them as fact.
    """
    world = _recorded(GAP_DIR)
    gaps = world.get("gaps", [])
    assert gaps, "tg-reconcile recorded no gap for inputs with no error semantics"
    blocking = [gap for gap in gaps if "propose" in gap.get("blocks", [])]
    assert blocking, (
        f"{len(gaps)} gap(s) recorded but none blocks propose; a capability whose "
        "error and empty behaviour is undocumented cannot support a meaningful "
        "scenario for those outcome classes"
    )


def test_the_gap_fixture_did_not_acquire_invented_outcome_classes():
    """The other half of the test above, and the one that actually catches
    confabulation. A world model can record a gap *and* invent the semantics
    anyway -- at which point the gap is decoration and stage 2 proceeds on
    fiction. So the outcome classes are counted too: with only the happy path
    documented, a capability should carry one success class, not four.
    """
    world = _recorded(GAP_DIR)
    for capability in world.get("capabilities", []):
        kinds = [oc["kind"] for oc in capability["outcome_classes"]]
        invented = [kind for kind in kinds if kind in {"error", "not_found", "empty"}]
        assert not invented, (
            f"{capability['id']} declares outcome class kind(s) {invented}, which no "
            "input artifact describes"
        )
