"""tg-reconcile's contract and the enumerations its prompt must be complete over.

The two set-completeness tests below are the ones that matter. This stage
computes the coverage denominator, so a skill that names three of the five
outcome-class kinds produces a denominator that is quietly smaller than the
target's real surface -- and every later percentage is measured against it.
"""

from __future__ import annotations

import re

from rubrica.artifacts import read_json
from rubrica.skills import SECTIONS, load, skills_dir
from rubrica.validate import ARTIFACT_SCHEMAS, STAGE_ARTIFACTS, schema_dir

SKILL = skills_dir() / "tg-reconcile" / "SKILL.md"


def _world_schema():
    return read_json(schema_dir() / ARTIFACT_SCHEMAS["world-model"])


def test_the_contract_matches_the_stage_gate():
    skill = load(SKILL)
    assert skill.contract["stage"] == "reconcile"
    assert set(skill.contract["schemas"]) == set(STAGE_ARTIFACTS["reconcile"])


def test_it_reads_the_whole_claims_directory_because_it_is_the_barrier():
    """The one stage that sees every artifact's conclusions. A contract that
    declared a single claims file would make it a fan-out member and there
    would be nothing left to merge.
    """
    assert "claims_dir" in load(SKILL).contract["reads"]


def test_it_has_the_five_sections():
    assert all(section in load(SKILL).headings for section in SECTIONS)


def test_it_names_every_outcome_class_kind():
    """The denominator is capability x outcome class. A skill that omits
    `underspecified` produces a denominator missing that column for every
    capability, and coverage is then measured against a surface smaller than
    the target's.
    """
    enum = _world_schema()["$defs"]["capability"]["properties"]["outcome_classes"]["items"][
        "properties"
    ]["kind"]["enum"]
    body = load(SKILL).body
    missing = [kind for kind in enum if kind not in body]
    assert not missing, f"the skill never mentions outcome class kind(s) {missing}"


def test_it_names_every_contradiction_resolution_value():
    """Including `unresolved`, which is the one a skill under pressure to be
    helpful will omit -- and it is the only honest answer for a real
    disagreement the inputs do not settle.
    """
    enum = _world_schema()["$defs"]["contradiction"]["properties"]["resolution"]["enum"]
    body = load(SKILL).body
    missing = [value for value in enum if value not in body]
    assert not missing, f"the skill never mentions resolution(s) {missing}"


def test_it_names_every_machine_invariant_form_the_code_implements():
    """Imported from invariants.py, not from the schema and not from a literal:
    the forms the code can evaluate are the forms a skill may write, and a
    skill naming a fifth would produce an invariant refs reports as
    unimplemented.
    """
    from rubrica.invariants import _HANDLERS

    body = load(SKILL).body
    missing = [form for form in _HANDLERS if form not in body]
    assert not missing, f"the skill never mentions machine form(s) {missing}"


def test_it_names_every_stage_a_gap_may_block():
    """A gap's `blocks` list is what makes the orchestrator halt. A skill that
    names only `propose` cannot express a gap that blocks instantiate.
    """
    enum = _world_schema()["$defs"]["gap"]["properties"]["blocks"]["items"]["enum"]
    body = load(SKILL).body
    missing = [stage for stage in enum if stage not in body]
    assert not missing, f"the skill never mentions blockable stage(s) {missing}"


def test_it_states_that_the_denominator_is_computed_here_and_frozen():
    """Structural: the prose must name the denominator's three field names,
    which is the smallest check that the computation is specified rather than
    gestured at.

    `version` is matched on a word boundary, not as a bare substring, and that
    detail is the whole test. As a substring it is satisfied by `schema_version`
    and `denominator_version` elsewhere in the prose, so deleting the actual
    `version: 1` statement from the denominator step left this test green --
    mutation-confirmed. Scoping the search to the Method section does *not* fix
    it either: `denominator_version` legitimately appears there too, in the
    amendment-cost sentence. `\\b` works because underscore is a word character,
    so neither compound matches, and there is exactly one standalone `version`.

    `goals` and `capability_cells` stay bare substrings deliberately. `goals` is
    recurring domain vocabulary throughout this document and a word-boundary
    match would not make the check meaningfully stronger; `capability_cells`
    occurs only in denominator contexts. Both are honestly weaker than the
    `version` check, and this docstring is where that is recorded rather than
    left for the next reader to discover by mutation.
    """
    body = load(SKILL).body
    for field in ("capability_cells", "goals"):
        assert field in body, field
    assert re.search(r"\bversion\b", body), "the prose never names the denominator's `version`"
