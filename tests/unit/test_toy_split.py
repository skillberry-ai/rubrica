"""The split is derived from the golden world model, and it is total.

Totality is the property with teeth: the subject cover must name every claim in
the run, because refs.check_subjects holds a real run to exactly that and a
fixture that could not satisfy its own gate would be a fixture-cannot-reach
weakness rather than a test.
"""

from __future__ import annotations

from rubrica import validate
from tests.toy import ARTIFACT_IDS, split_world_model, toy_claims, toy_world_model

_KIND_FOR_KEY = {
    "subjects": "subjects",
    "capabilities": "capabilities-part",
    "outcomes": "outcomes-part",
    "entities": "entities-part",
    "goals": "goals-part",
    "gaps": "gaps-part",
    "services": "services-part",
}


def _all_claim_ids() -> set[str]:
    return {
        claim["id"] for artifact_id in ARTIFACT_IDS for claim in toy_claims(artifact_id)["claims"]
    }


def test_every_partial_validates_against_its_own_schema(tmp_path):
    import json

    parts = split_world_model()
    for key, kind in _KIND_FOR_KEY.items():
        doc = tmp_path / f"{key}.json"
        doc.write_text(json.dumps(parts[key]), encoding="utf-8")
        assert validate.validate_artifact(doc, kind) == [], f"{key} does not match {kind}"
    for subject_id, part in parts["contradictions"].items():
        doc = tmp_path / f"contradiction-{subject_id}.json"
        doc.write_text(json.dumps(part), encoding="utf-8")
        assert validate.validate_artifact(doc, "contradictions-part") == []


def test_the_subject_cover_names_every_claim_in_the_run():
    covered = {
        claim_id
        for subject in split_world_model()["subjects"]["subjects"]
        for claim_id in subject["claims"]
    }
    assert covered == _all_claim_ids(), (
        "the cover must be total: refs.check_subjects reports any claim it omits"
    )


def test_no_subject_names_the_same_claim_twice():
    """The cover over-assigns across subjects, never within one.

    A cover may put one claim under several subjects -- that is what
    rb-reconcile-subjects is instructed to do when a claim bears on more than one
    -- but a repeat inside a single subject's array says nothing a member could
    act on. Reachable since issue #6 moved the fixture's outcome_class-kind
    citations onto the outcome classes: clm-api-005 is on both of
    cap-find-tickets' outcome classes, deliberately, and the capability's subject
    covers what its outcome classes cite, so it arrives at that subject twice.
    """
    for subject in split_world_model()["subjects"]["subjects"]:
        claims = subject["claims"]
        assert len(claims) == len(set(claims)), f"{subject['id']} repeats a claim id: {claims}"


def test_every_subject_has_a_contradictions_part():
    """Even an empty one. The file's existence is the record that the sweep
    visited that subject, which is the check the single-turn stage never had."""
    parts = split_world_model()
    subject_ids = {subject["id"] for subject in parts["subjects"]["subjects"]}
    assert set(parts["contradictions"]) == subject_ids


def test_the_split_carries_every_contradiction_the_world_model_declares():
    """A split that dropped one would make the round-trip in
    tests/unit/test_reconcile_seal.py pass against a world model missing it."""
    split_ids = {
        c["id"]
        for part in split_world_model()["contradictions"].values()
        for c in part["contradictions"]
    }
    assert split_ids == {c["id"] for c in toy_world_model()["contradictions"]}


def test_outcomes_covers_every_declared_capability():
    parts = split_world_model()
    assert {o["capability_id"] for o in parts["outcomes"]["outcomes"]} == {
        c["id"] for c in parts["capabilities"]["capabilities"]
    }


def test_each_contradiction_lands_in_a_subject_that_names_both_its_sides():
    """rb-reconcile-contradict's invariant 3, held against the model answer.

    Measured before split_world_model widened the owning subject:
    sub-cap-get-ticket held clm-notes-004 but not clm-trace-002 and carried
    con-missing-semantics anyway, and refs.check_contradiction_parts was clean
    over it because it resolved both ids against the whole run. A fixture that
    breaks a skill's own invariant teaches the skill to break it -- this is the
    model answer a member imitates.
    """
    parts = split_world_model()
    covered_by = {s["id"]: set(s["claims"]) for s in parts["subjects"]["subjects"]}
    for subject_id, part in parts["contradictions"].items():
        for contradiction in part["contradictions"]:
            for side in ("claim_a", "claim_b"):
                assert contradiction[side] in covered_by[subject_id], (
                    f"{contradiction['id']}'s {side} reaches outside {subject_id}, which is a "
                    "claim a sibling member's subject covers, not this one's to sweep"
                )


def test_a_cross_artifact_contradiction_is_findable_inside_one_subject():
    """The branch's central claim, demonstrated rather than asserted in prose.

    Splitting reconcile is only sound if a disagreement *between two inputs* is
    still visible to the single fan-out member that records it. The golden world's
    one contradiction pits the operator notes against the captured trace, so this
    checks that both of those claims live in the same subject -- the only way a
    single member's own subject names both sides, which recording it requires.
    """
    parts = split_world_model()
    origin = {
        claim["id"]: artifact_id
        for artifact_id in ARTIFACT_IDS
        for claim in toy_claims(artifact_id)["claims"]
    }
    found = [
        (subject_id, c)
        for subject_id, part in parts["contradictions"].items()
        for c in part["contradictions"]
        if origin[c["claim_a"]] != origin[c["claim_b"]]
    ]
    assert found, "the golden world must carry a contradiction spanning two inputs"
    covered_by = {s["id"]: set(s["claims"]) for s in parts["subjects"]["subjects"]}
    for subject_id, contradiction in found:
        assert {contradiction["claim_a"], contradiction["claim_b"]} <= covered_by[subject_id]


# own_kind_total / cited / dropped for every (pass, artifact) pair in the golden
# corpus, read off the fixture by hand and typed out here.
_EXPECTED_INPUTS_SEEN: dict[str, dict[str, tuple[int, int, int]]] = {
    "capabilities": {"api-json": (5, 5, 0), "notes-md": (0, 0, 0), "trace-json": (0, 0, 0)},
    "entities": {"api-json": (2, 2, 0), "notes-md": (2, 2, 0), "trace-json": (0, 0, 0)},
    "outcomes": {"api-json": (2, 2, 0), "notes-md": (1, 1, 0), "trace-json": (2, 1, 1)},
    "goals": {"api-json": (0, 0, 0), "notes-md": (5, 5, 0), "trace-json": (0, 0, 0)},
    # Read off tests/fixtures/toy/ the same way every row above it was: the corpus
    # holds exactly one claim of kind `tool` -- clm-api-010 on api-json, whose
    # payload is api.json's tools[0].input_schema copied verbatim -- and neither
    # notes.md nor trace.json declares a tool at all. svc-tickets cites that one
    # claim, so nothing is dropped and no row here carries a note.
    "services": {"api-json": (1, 1, 0), "notes-md": (0, 0, 0), "trace-json": (0, 0, 0)},
}


def test_the_derived_rows_match_a_hand_written_table():
    """A literal, where every other expectation in this module is derived.

    Deliberate, and the only expectation in the repository that neither walk can
    satisfy by agreeing with itself. tests.toy._inputs_seen and
    refs._claim_refs_in are line-for-line the same walk, so every test that
    builds its expectation by mutating what the fixture produced would still
    pass with a mirrored bug in both -- two identical algorithms agreeing is not
    evidence. This table was read off tests/fixtures/toy/ by hand, so it fails
    if either walk drifts, and it fails if the fixture's claim kinds change
    without someone noticing. Issue #6, where read coverage varied 3/23 to 23/23
    across byte-identical dispatches, is exactly the class of defect that a
    self-confirming measurement cannot see.

    trace-json's outcomes row is the one non-zero drop, so it is also the one
    row required to carry a note.
    """
    parts = split_world_model()
    for key, expected in _EXPECTED_INPUTS_SEEN.items():
        rows = {row["artifact_id"]: row for row in parts[key]["inputs_seen"]}
        assert set(rows) == set(expected), key
        for artifact_id, (own_kind_total, cited, dropped) in expected.items():
            row = rows[artifact_id]
            assert (row["own_kind_total"], row["cited"], row["dropped"]) == (
                own_kind_total,
                cited,
                dropped,
            ), f"{key} / {artifact_id}"
            assert ("note" in row) is bool(dropped), f"{key} / {artifact_id}"
