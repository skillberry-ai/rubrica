import json

import pytest

from rubrica.artifacts import write_json
from rubrica.validate import ARTIFACT_SCHEMAS, CONFIG_KINDS, schema_dir, validate_artifact
from tests.builders import (
    minimal_expected,
    minimal_manifest,
    minimal_scenarios,
    minimal_seed,
    minimal_verdict,
)
from tests.toy import toy_world_model


def _findings(tmp_path, kind, payload):
    path = tmp_path / f"{kind}.json"
    write_json(path, payload)
    return validate_artifact(path, kind)


def test_minimal_seed_is_valid(tmp_path):
    assert _findings(tmp_path, "seed", minimal_seed()) == []


def test_seed_must_have_at_least_one_collection(tmp_path):
    assert _findings(tmp_path, "seed", minimal_seed(collections={}))


def test_seed_collection_must_be_an_array_of_objects(tmp_path):
    assert _findings(tmp_path, "seed", minimal_seed(collections={"jobs": [1, 2]}))


def test_seed_permits_arbitrary_entity_fields(tmp_path):
    payload = minimal_seed(collections={"anything": [{"whatever": {"nested": True}}]})
    assert _findings(tmp_path, "seed", payload) == []


def test_minimal_expected_is_valid(tmp_path):
    assert _findings(tmp_path, "expected", minimal_expected()) == []


def test_data_assertion_without_grounding_is_rejected(tmp_path):
    payload = minimal_expected()
    del payload["assertions"][0]["grounded_in"]
    assert _findings(tmp_path, "expected", payload)


def test_data_assertion_may_not_carry_a_capability_id(tmp_path):
    payload = minimal_expected()
    payload["assertions"][0]["capability_id"] = "cap-find-jobs"
    assert _findings(tmp_path, "expected", payload)


def test_trajectory_assertion_without_a_capability_id_is_rejected(tmp_path):
    payload = minimal_expected()
    del payload["assertions"][1]["capability_id"]
    assert _findings(tmp_path, "expected", payload)


def test_trajectory_assertion_may_not_carry_grounding(tmp_path):
    payload = minimal_expected()
    payload["assertions"][1]["grounded_in"] = {"seed_pointer": "/collections/jobs/0"}
    assert _findings(tmp_path, "expected", payload)


def test_answer_excludes_is_grounded_like_other_data_assertions(tmp_path):
    payload = minimal_expected()
    payload["assertions"] = [
        {
            "kind": "answer_excludes",
            "target": "answer",
            "value": "root cause",
            "rationale": "the log does not support a root-cause claim",
            "grounded_in": {"seed_pointer": "/collections/jobs/0/error_msg"},
        }
    ]
    assert _findings(tmp_path, "expected", payload) == []


def test_assertion_kind_is_closed(tmp_path):
    payload = minimal_expected()
    payload["assertions"][0]["kind"] = "answer_matches_regex"
    assert _findings(tmp_path, "expected", payload)


def test_seed_pointer_must_be_a_json_pointer(tmp_path):
    payload = minimal_expected()
    payload["assertions"][0]["grounded_in"]["seed_pointer"] = "collections.jobs[0]"
    assert _findings(tmp_path, "expected", payload)


def test_expected_needs_at_least_one_assertion(tmp_path):
    assert _findings(tmp_path, "expected", minimal_expected(assertions=[]))


def test_negative_expectations_is_not_a_field(tmp_path):
    payload = minimal_expected()
    payload["negative_expectations"] = [{"statement": "no root cause claimed"}]
    assert _findings(tmp_path, "expected", payload)


def test_minimal_verdict_is_valid(tmp_path):
    assert _findings(tmp_path, "verdict", minimal_verdict()) == []


def test_ambiguity_claim_requires_the_second_answer(tmp_path):
    payload = minimal_verdict(uniquely_determined=False, verdict="re-seed")
    assert _findings(tmp_path, "verdict", payload)


def test_ambiguity_claim_with_an_alternative_is_valid(tmp_path):
    payload = minimal_verdict(
        uniquely_determined=False,
        verdict="re-seed",
        alternative_answers=[
            {"answer": "Job 90421 failed.", "world_consistent_reason": "also outside the window"}
        ],
    )
    assert _findings(tmp_path, "verdict", payload) == []


def test_verdict_notes_may_not_be_empty(tmp_path):
    assert _findings(tmp_path, "verdict", minimal_verdict(notes=""))


def test_difficulty_overstated_is_the_only_flag(tmp_path):
    assert _findings(tmp_path, "verdict", minimal_verdict(flags=["too_easy"]))
    assert _findings(tmp_path, "verdict", minimal_verdict(flags=["difficulty_overstated"])) == []


# -- world model: claims on the three child element defs (issue #6) ------
def _world_with_a_gap() -> dict:
    """The golden world model plus one gap, so all three sites are reachable.

    `tests/fixtures/toy/` deliberately keeps `"gaps": []` -- the golden world
    has nothing missing from it, and inventing a gap there would change what
    the fixture teaches. So the gap is added here. Skipping the site instead
    would be the *fixture-cannot-reach* weakness this repo has measured, at
    exactly the def whose claims are the least obvious of the three.
    """
    world = toy_world_model()
    world["gaps"] = [
        {
            "id": "gap-empty-comment-list",
            "subject": "what get_ticket returns for a ticket with no comments",
            "unknown": "whether the comments array comes back empty or the key is absent",
            "why_it_matters": "an oracle over comments cannot be grounded either way",
            "blocks": ["instantiate"],
            # A gap's claims cite the evidence that the *absence matters*, not
            # evidence of the fact that is missing: clm-api-006 is what
            # promises the ticket together with its comments, which is what
            # makes the silence about the empty case a hole rather than a
            # non-question.
            "claims": ["clm-api-006"],
        }
    ]
    return world


def test_a_world_model_with_claims_on_every_child_element_is_valid(tmp_path):
    """The positive direction, and what stops the two below passing vacuously.

    Both of those assert that a *finding* appears. A helper that was invalid
    for some unrelated reason would satisfy them without the schema ever
    requiring anything, so the shape they mutate has to be known-good first.
    """
    assert _findings(tmp_path, "world-model", _world_with_a_gap()) == []


@pytest.mark.parametrize(
    "pointer",
    [
        ("capabilities", 0, "outcome_classes", 0),
        ("entities", 0, "invariants", 0),
        ("gaps", 0),
    ],
)
def test_a_child_element_without_claims_is_rejected(tmp_path, pointer):
    """The three defs that had no `claims` array until issue #6.

    `capability`, `entity`, `actor` and `goal` have always required one. These
    three did not, and `additionalProperties: false` meant a pass could not
    even record provenance voluntarily -- so an invariant's evidence went onto
    its entity, or into `description` prose no counter reads.
    """
    world = _world_with_a_gap()
    node = world
    for key in pointer[:-1]:
        node = node[key]
    del node[pointer[-1]]["claims"]
    assert _findings(tmp_path, "world-model", world), (
        f"a child element at {pointer} with no claims was accepted"
    )


@pytest.mark.parametrize(
    "pointer",
    [
        ("capabilities", 0, "outcome_classes", 0),
        ("entities", 0, "invariants", 0),
        ("gaps", 0),
    ],
)
def test_a_child_element_with_an_empty_claims_array_is_rejected(tmp_path, pointer):
    """minItems 1 comes from $defs/claim_refs, which these now $ref.

    Both directions matter: "the key is present" is not the property. An empty
    array is a pass declaring it has no evidence for an element it declared
    anyway, which is the confabulation every refusal-conditions section warns
    about.
    """
    world = _world_with_a_gap()
    node = world
    for key in pointer[:-1]:
        node = node[key]
    node[pointer[-1]]["claims"] = []
    assert _findings(tmp_path, "world-model", world), (
        f"an empty claims array at {pointer} was accepted"
    )


def test_every_registered_artifact_kind_now_has_a_schema_file():
    """Every kind registered in validate.ARTIFACT_SCHEMAS exists on disk.

    Task 3 could only assert this for the two schemas it created. With Tasks 4
    and 5 landed, the registry and the schema directory must agree completely.
    """
    from rubrica.validate import ARTIFACT_SCHEMAS, schema_dir

    for kind, filename in ARTIFACT_SCHEMAS.items():
        assert (schema_dir() / filename).is_file(), kind


# Config kinds (agents, gold, ...) are human-authored, never joined into a run
# path, and carry no id-shaped field -- role is a closed enum, not a segment --
# so there is nothing here for paths.safe_segment's \\A..\\Z convention to apply
# to. They are exempt from the pattern-anchoring check below.
@pytest.mark.parametrize("kind", sorted(set(ARTIFACT_SCHEMAS) - CONFIG_KINDS))
def test_no_schema_pattern_uses_a_caret_dollar_anchor(kind, tmp_path):
    """Python's re lets $ match before a trailing newline; \\Z does not.

    paths.safe_segment uses \\Z, so an id ending in a newline clears layer 1
    and then raises UnsafeSegment, which the CLI maps to exit 2 -- a repairable
    stage defect misreported as a broken harness.
    """
    text = (schema_dir() / ARTIFACT_SCHEMAS[kind]).read_text(encoding="utf-8")
    schema = json.loads(text)
    seen: set[tuple[str, str]] = set()

    def resolve(ref: str, home: str) -> tuple[dict, str]:
        """The subschema `ref` points at, plus the file it now lives in.

        Refs are followed rather than stopped at, because neither the reconcile
        partials nor the triage part schemas own a `pattern` of their own: their
        ids are `world-model-0.1.json#/$defs/id` and `triage-0.1.json#/$defs/id`,
        resolved at validation time through validate._schema_registry. Stopping
        at the ref would make `found` empty for every one of them, and the
        `assert found` guard below -- which is what stops this test passing
        vacuously -- would have to be dropped. This way it keeps its teeth, and
        gains some: a part that pointed at a
        definition anchored with ^ or $ is now caught here too.
        """
        filename, _, pointer = ref.partition("#")
        filename = filename or home
        node = json.loads((schema_dir() / filename).read_text(encoding="utf-8"))
        for part in pointer.lstrip("/").split("/"):
            if part:
                node = node[part.replace("~1", "/").replace("~0", "~")]
        return node, filename

    def patterns(node, home: str):
        """Every string value of a "pattern" key, at any depth, refs followed."""
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "pattern" and isinstance(value, str):
                    yield value
                elif key == "$ref" and isinstance(value, str):
                    if (home, value) in seen:
                        continue  # $defs/machine and friends are self-recursive.
                    seen.add((home, value))
                    target, target_home = resolve(value, home)
                    yield from patterns(target, target_home)
                else:
                    yield from patterns(value, home)
        elif isinstance(node, list):
            for item in node:
                yield from patterns(item, home)

    found = list(patterns(schema, ARTIFACT_SCHEMAS[kind]))
    assert found, f"{kind} declares no patterns; the table in the plan says it should"
    for pattern in found:
        assert not pattern.startswith("^"), f"{kind}: {pattern!r} still uses ^"
        assert not pattern.endswith("$"), f"{kind}: {pattern!r} still uses $"
        assert pattern.startswith("\\A"), f"{kind}: {pattern!r} is not anchored with \\A"


def test_a_scenario_id_ending_in_a_newline_is_rejected(tmp_path):
    payload = minimal_scenarios()
    payload["scenarios"][0]["id"] = "scn-001\n"
    path = tmp_path / "02-scenarios.json"
    write_json(path, payload)
    assert validate_artifact(path, "scenarios") != []


def test_a_seed_pointer_not_starting_with_a_slash_is_rejected(tmp_path):
    payload = minimal_expected()
    payload["assertions"][0]["grounded_in"]["seed_pointer"] = "collections/jobs/0"
    path = tmp_path / "expected.json"
    write_json(path, payload)
    assert validate_artifact(path, "expected") != []


@pytest.mark.parametrize(
    "created_utc",
    [
        "not-a-timestamp",
        "2026-08-06T12:00:00+05:30",
        "2026-08-06 12:00:00Z",
        "2026-08-06T12:00:00Z\n",
    ],
)
def test_a_created_utc_that_is_not_a_utc_stamp_is_rejected(tmp_path, created_utc):
    path = tmp_path / "manifest.json"
    write_json(path, minimal_manifest(created_utc=created_utc))
    assert validate_artifact(path, "manifest") != []


def test_the_canonical_created_utc_is_accepted(tmp_path):
    path = tmp_path / "manifest.json"
    write_json(path, minimal_manifest(created_utc="2026-08-06T12:00:00Z"))
    assert validate_artifact(path, "manifest") == []
