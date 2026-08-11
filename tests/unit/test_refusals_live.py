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

import json

import pytest

from rubrica.artifacts import read_json
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


def _declared_actions(fixture) -> list[str]:
    """The capability names the fixture's own `api.json` declares.

    Read from the fixture rather than written as a literal, so a re-record that
    legitimately changes the input changes what these tests expect, and a
    recording that simply lost a capability does not.
    """
    api = json.loads((fixture / "api.json").read_text(encoding="utf-8"))
    return api["tools"][0]["input_schema"]["properties"]["action"]["enum"]


def _propose_blocking_subjects(world) -> list[str]:
    """The `subject` of every gap that blocks `propose`.

    `subject` rather than the whole entry, because it is the field that names
    *what* is unknown. `why_it_matters` mentions the downstream capabilities in
    every gap this skill writes -- including the schema-invalid-call gap, whose
    prose names both capabilities while the gap itself is about neither.
    """
    return [
        gap.get("subject", "")
        for gap in world.get("gaps", [])
        if "propose" in gap.get("blocks", [])
    ]


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
    assert contradictions, "rb-reconcile recorded no contradiction for a contradictory pair"
    resolutions = {entry["resolution"] for entry in contradictions}
    assert "unresolved" in resolutions, (
        f"the contradiction was resolved as {sorted(resolutions)}, but nothing in the "
        "fixture licenses preferring either side"
    )


def test_an_input_with_error_semantics_removed_produces_a_gap_blocking_propose():
    """Section 9's second negative, and the one a helpful model fails: with no
    error semantics stated anywhere, the tempting output is a world model that
    invents them -- after which every downstream stage treats them as fact.

    **Tied to the capabilities whose semantics were actually subtracted**, which
    is what makes this the test its name claims. "Some gap blocks propose" was
    satisfied by `gap-invalid-argument-behavior` -- a gap about *schema-invalid
    calls*, which has nothing to do with the removed prose and which the
    **contradiction** recording carries too, i.e. a fixture whose error semantics
    were never removed. A recording that recorded only that gap and invented the
    error and empty semantics outright would have passed. Both declared
    capabilities lost their non-success prose here (`get_ticket`'s "Errors if..."
    and `find_tickets`' "possibly empty"), so each must have its own gap, matched
    on the gap's `subject`.
    """
    world = _recorded(GAP_DIR)
    subjects = _propose_blocking_subjects(world)
    assert subjects, (
        f"{len(world.get('gaps', []))} gap(s) recorded but none blocks propose; a "
        "capability whose error and empty behaviour is undocumented cannot support a "
        "meaningful scenario for those outcome classes"
    )
    for action in _declared_actions(GAP_DIR):
        assert any(action in subject for subject in subjects), (
            f"no propose-blocking gap names {action!r} as its subject, though the fixture "
            f"removed its non-success semantics; the gaps recorded are about {subjects}"
        )


def test_a_gap_about_malformed_calls_alone_does_not_satisfy_that_test():
    """The negative direction of the test above, made permanent.

    Written as a synthetic world model rather than by editing a recording,
    because the recordings are evidence and must not be touched. The entry below
    is `gap-invalid-argument-behavior` as it appears verbatim in *both*
    recordings, and the point is that on its own it must not count: it is a real
    gap about a real unknown, and it is not the subtraction this fixture makes.

    **`why_it_matters` keeps the pre-Rubrica `tg-propose` spelling on purpose.**
    It is quoted model output, and the recordings it quotes were produced before
    the skills were renamed to `rb-*`; the Rubrica rename changed no measurement,
    so it did not rewrite them either. Updating this string to `rb-propose`
    without re-recording would make "verbatim" false. Nothing here reads the
    field -- `_propose_blocking_subjects` reads `subject` and `blocks` -- so the
    spelling costs the assertion nothing and buys it fidelity to the evidence.
    """
    world = {
        "gaps": [
            {
                "id": "gap-invalid-argument-behavior",
                "subject": "query_tickets' behavior on a schema-invalid call",
                "why_it_matters": (
                    "tg-propose cannot design a meaningful bad-argument scenario for either "
                    "find_tickets or get_ticket without knowing what the tool does"
                ),
                "blocks": ["propose"],
            }
        ]
    }
    subjects = _propose_blocking_subjects(world)
    assert subjects, "the fixture entry does block propose, which is why it was mistaken for one"
    assert not [
        action for action in _declared_actions(GAP_DIR) if any(action in s for s in subjects)
    ], "a gap about malformed calls must not be read as a gap about either capability"


def test_the_gap_fixture_did_not_acquire_invented_outcome_classes():
    """The other half of the test above, and the one that actually catches
    confabulation. A world model can record a gap *and* invent the semantics
    anyway -- at which point the gap is decoration and stage 2 proceeds on
    fiction. So the outcome classes are counted too: with only the happy path
    documented, a capability should carry one success class, not four.

    **The counts are pinned, because the loop was vacuous without them.** A
    recording with `capabilities: []` iterated zero times and passed while
    proving nothing -- and that recording is schema-valid, `capabilities` having
    no `minItems`, so no gate would have objected either. The expected number
    comes from the fixture's own `api.json` rather than from a literal, and the
    per-capability enumeration is checked against the recording's own
    `denominator.capability_cells`, which catches the other empty shape: a
    capability present with no outcome classes at all.
    """
    world = _recorded(GAP_DIR)
    capabilities = world.get("capabilities", [])
    actions = _declared_actions(GAP_DIR)
    assert len(capabilities) == len(actions), (
        f"the recording declares {len(capabilities)} capability(ies) for a fixture whose "
        f"api.json declares {len(actions)}: {actions}"
    )
    cells = 0
    for capability in capabilities:
        kinds = [oc["kind"] for oc in capability["outcome_classes"]]
        assert kinds, f"{capability['id']} enumerates no outcome class at all"
        cells += len(kinds)
        invented = [kind for kind in kinds if kind in {"error", "not_found", "empty"}]
        assert not invented, (
            f"{capability['id']} declares outcome class kind(s) {invented}, which no "
            "input artifact describes"
        )
    assert cells == world["denominator"]["capability_cells"], (
        f"the capabilities enumerate {cells} cells but the denominator claims "
        f"{world['denominator']['capability_cells']}"
    )
