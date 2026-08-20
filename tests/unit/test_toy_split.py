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
