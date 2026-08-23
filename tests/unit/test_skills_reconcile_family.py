"""The reconcile family's contracts, and the rules each pass now owns.

One module over the family rather than seven, because most of what is checked
here is a property of the *split*: every pass reads all of 01-claims/, no pass
reads 01-world-model.json, and the enumerations that used to be complete in one
prompt must still be complete in whichever pass inherited them.

Every prose assertion is scoped with `section_body`, and asserts co-occurrence
inside the section that owns the rule. `load()` sets `body` to the entire file
text and the five headings are mandatory, so a substring check against `body` is
satisfied by the frontmatter `description:` line, by the contract block, or by
any other section -- roughly nineteen assertions in this repository were
measured satisfiable that way before the convention changed.
"""

from __future__ import annotations

import pytest

from rubrica.artifacts import read_json
from rubrica.paths import STAGES
from rubrica.skills import SECTIONS, SKILL_PREFIX, load, section_body, skills_dir
from rubrica.validate import ARTIFACT_SCHEMAS, STAGE_ARTIFACTS, schema_dir

# Derived from STAGES, not restated: a pass added to the family joins this
# parametrization without anyone remembering to edit a list, which is the same
# reasoning skills.expected_skill_names() rests on. reconcile-seal is excluded
# because it is code -- it has no skill file to read.
FAMILY = tuple(s for s in STAGES if s.startswith("reconcile-") and s != "reconcile-seal")


def _skill(stage: str):
    return load(skills_dir() / f"{SKILL_PREFIX}{stage}" / "SKILL.md")


def _flat(stage: str, heading: str) -> str:
    """One section, lowercased with runs of whitespace collapsed.

    Normalised because a pure rewrap changes no words and must not flip a test:
    measured once that rewrapping a paragraph at width 60 split "becomes an
    entity" across a line boundary and turned an assertion red.
    """
    return " ".join(section_body(_skill(stage), heading).lower().split())


def _world_schema():
    return read_json(schema_dir() / ARTIFACT_SCHEMAS["world-model"])


def test_the_family_is_the_eight_stages_between_extract_and_propose():
    """Guards the derivation above, and the ordering the passes depend on:
    outcomes quantifies over capabilities' output, gaps audits all of them, and
    the seal runs last. A reordering here is a real change to what each pass can
    read, not a cosmetic one.
    """
    assert STAGES[STAGES.index("extract") + 1 : STAGES.index("propose")] == (
        "reconcile-subjects",
        "reconcile-contradict",
        "reconcile-capabilities",
        "reconcile-outcomes",
        "reconcile-entities",
        "reconcile-goals",
        "reconcile-gaps",
        "reconcile-seal",
    )


@pytest.mark.parametrize("stage", FAMILY)
def test_the_contract_matches_the_stage_gate(stage):
    skill = _skill(stage)
    assert skill.contract["stage"] == stage
    assert set(skill.contract["schemas"]) == set(STAGE_ARTIFACTS[stage])


@pytest.mark.parametrize("stage", FAMILY)
def test_it_has_the_five_sections(stage):
    assert all(section in _skill(stage).headings for section in SECTIONS)


@pytest.mark.parametrize("stage", FAMILY)
def test_every_pass_reads_the_whole_claims_directory(stage):
    """The barrier property, and the reason the split is safe. The family is cut
    on *output*: a pass declaring a single claims file would be a fan-out member
    over the evidence, and a contradiction spanning two inputs would then be
    invisible to every one of them.
    """
    assert "claims_dir" in _skill(stage).contract["reads"]


@pytest.mark.parametrize("stage", FAMILY)
def test_no_pass_declares_the_world_model_and_the_prose_says_so(stage):
    """The single-pass prohibition on rereading your own last answer, rewritten
    for a sequence. A later pass reading an earlier pass's partial *is* the
    design, so what survives is narrower: nobody reads the assembled answer, and
    a re-dispatched pass does not reread its own output instead of the claims.
    """
    reads = _skill(stage).contract["reads"]
    assert "world_model" not in reads
    inputs = _flat(stage, "1. Inputs")
    assert "no pass reads `01-world-model.json`" in inputs
    assert "does not read its own previous output" in inputs


# The passes that could settle a disagreement, and so must carry the rule that a
# resolution may rest only on what the claims establish. Not every pass in the
# family: subjects writes no resolution and has nowhere to put one, and goals and
# gaps are held to the narrower constraint that an unresolved contradiction is
# not theirs to settle.
RESOLVERS = (
    "reconcile-contradict",
    "reconcile-capabilities",
    "reconcile-outcomes",
    "reconcile-entities",
)


@pytest.mark.parametrize("stage", RESOLVERS)
def test_the_resolvers_forbid_convention_standing_in_for_evidence(stage):
    """The rule with the sharpest tell in the whole design: convention reasoning
    would have produced the same answer even if the losing claim had never been
    extracted, which is what distinguishes it from a resolution the claim set
    actually earned. Carried unchanged from the superseded single-pass stage,
    worked example included, into every pass that could settle a disagreement.
    """
    inputs = _flat(stage, "1. Inputs")
    assert 'a system "like this" usually does' in inputs
    assert "get_ticket" in inputs
    assert "even if `notes.md` had never been extracted at all" in inputs


def test_subjects_instructs_over_assignment_rather_than_a_guess():
    """The cover's one safe direction. A claim in no subject is compared against
    nothing and the omission appears nowhere on disk -- refs.check_subjects
    catches a claim missing from the cover, but nothing catches a disagreement
    split across two subjects, which is why the prompt has to instruct the safe
    direction rather than leave it to judgment.
    """
    refusals = _flat("reconcile-subjects", "5. Refusal conditions")
    assert "over-assign" in refusals
    assert "never compared against anything" in refusals


def test_contradict_is_dispatched_with_one_subject_id_and_sweeps_across_inputs():
    """Its two fan-out properties, which are in tension: the slice is one
    subject, and the reading inside that slice is every input. Getting the second
    wrong is what would silently un-do cross-artifact contradiction detection.
    """
    inputs = _flat("reconcile-contradict", "1. Inputs")
    assert "subject_id" in inputs
    assert "never a sibling's" in inputs
    assert "from every file they appear in" in inputs


def test_contradict_writes_its_part_even_when_it_found_nothing():
    """An empty array is the record that the subject was swept. A missing file is
    indistinguishable from a member that was never dispatched, which is why
    refs.check_contradiction_parts requires a file per subject rather than a
    non-empty one.
    """
    output = _flat("reconcile-contradict", "2. Output")
    assert "write the part even when you found nothing" in output
    assert "empty `contradictions` array" in output


def test_contradict_names_every_contradiction_resolution_value():
    """Including `unresolved`, which is the one a skill under pressure to look
    decisive will omit -- and it is the only honest answer for a real
    disagreement the claims do not settle.
    """
    enum = _world_schema()["$defs"]["contradiction"]["properties"]["resolution"]["enum"]
    method = _flat("reconcile-contradict", "3. Method")
    missing = [value for value in enum if value not in method]
    assert not missing, f"the Method section never mentions resolution(s) {missing}"


def test_capabilities_treats_the_recorded_contradictions_as_a_constraint():
    """The cross-pass incoherence this design is most exposed to: a later pass
    modelling what the sweep recorded `unresolved`. No mechanical check can catch
    it -- whether a claim *supports* an element is semantic -- so the prompt is
    the only instrument, beside a human at gate 1.
    """
    inputs = _flat("reconcile-capabilities", "1. Inputs")
    assert "unresolved" in inputs
    assert "constraint" in inputs


def test_capabilities_requires_a_binding_and_names_what_a_missing_one_costs():
    method = _flat("reconcile-capabilities", "3. Method")
    assert "`binding`" in method
    assert "fixed_args" in method
    assert "costs a shipped test" in method


def test_capabilities_may_not_write_outcome_classes():
    """The subtraction that defines the artifact, and the reason for it: making
    the capability list a file the next pass reads, rather than a memory of
    having just written one, is what lets that pass quantify over it.
    """
    output = _flat("reconcile-capabilities", "2. Output")
    assert "do not write `outcome_classes`" in output


def test_outcomes_names_every_outcome_class_kind():
    """The denominator is capability x outcome class. A pass that omits
    `underspecified` produces a denominator missing that column for every
    capability, and coverage is then measured against a surface smaller than the
    target's.
    """
    # $defs/outcome_class, not the shape inlined under $defs/capability: the
    # definition was extracted so the partial schemas could $ref it, and reading
    # it through capability's `items` now lands on a $ref and raises KeyError.
    enum = _world_schema()["$defs"]["outcome_class"]["properties"]["kind"]["enum"]
    method = _flat("reconcile-outcomes", "3. Method")
    missing = [kind for kind in enum if kind not in method]
    assert not missing, f"the Method section never mentions outcome class kind(s) {missing}"


def test_outcomes_quantifies_over_the_capability_list_on_disk():
    """The measured instruction. "For every capability" produced every
    outcome-class cell a real run needed; an unquantified "group claims" dropped
    45% of them. Quantifying over the *file* is what the split bought, so the
    assertion pins the file rather than just the phrase.
    """
    method = _flat("reconcile-outcomes", "3. Method")
    assert "for each capability in `01-capabilities.json`" in method
    assert "45%" in method


def test_outcomes_harvests_from_claims_of_every_kind():
    """The measurement behind it: one real run filed the same fact as
    `outcome_class` from one input and as `invariant`, twice, from another, and
    nothing in the claims schema forces the right label.
    """
    method = _flat("reconcile-outcomes", "3. Method")
    assert "not only the ones already tagged `outcome_class`" in method
    assert "twice" in method


def test_entities_requires_an_entity_for_a_capabilitys_described_response_shape():
    """Task 6 of the trajectory run dropped a claim that named all six fields of
    cancel_reservation's success payload -- confidence high, a JSON Pointer into
    an observed span, the refund_policy string quoted -- and produced four
    entities, none of them a cancellation receipt. Nothing in the prompt was
    violated: the old Method step 2 said "group claims", an unquantified verb.

    Asserting co-occurrence inside Method, because "entity" and "capability"
    appear throughout this file and a presence check anywhere in `body` would
    pass with this rule deleted.
    """
    method = _flat("reconcile-entities", "3. Method")
    assert "for every capability declared in `01-capabilities.json`" in method
    assert "becomes an entity" in method


def test_entities_names_every_machine_invariant_form_the_code_implements():
    """Imported from invariants.py, not from the schema and not from a literal:
    the forms the code can evaluate are the forms a skill may write, and a skill
    naming a fifth would produce an invariant refs reports as unimplemented.
    """
    from rubrica.invariants import _HANDLERS

    method = _flat("reconcile-entities", "3. Method")
    missing = [form for form in _HANDLERS if form not in method]
    assert not missing, f"the Method section never mentions machine form(s) {missing}"


def test_entities_states_both_directions_of_the_machine_prose_choice():
    """Both, because they fail differently and the costlier one is the
    safer-looking mistake. `prose:` where a form fits leaves the reachability
    gate nothing to check; `machine:` on an inference fails every seed that is
    actually correct, because check-refs evaluates it as ground truth.
    """
    method = _flat("reconcile-entities", "3. Method")
    assert "leaves the reachability gate with nothing mechanical to check" in method
    assert "fails every seed that is actually correct" in method


def test_goals_states_that_the_list_is_frozen_and_what_an_amendment_costs():
    """The half of the denominator a prompt still writes. A list a later, more
    permissive stage could add to is not a denominator -- it is a number that
    stage can inflate its own coverage against by discovering more of it after
    the fact. The arithmetic itself is reconcile-seal's and is pinned in
    tests/unit/test_reconcile_seal.py.
    """
    output = _flat("reconcile-goals", "2. Output")
    assert "frozen" in output
    assert "denominator_version" in output
    assert "request" in output


def test_goals_refuses_to_manufacture_an_actor():
    """Every goal needs a real actor_id to resolve, so a goal list written over
    an invented actor is a denominator whose shape was invented too."""
    refusals = _flat("reconcile-goals", "5. Refusal conditions")
    assert "you cannot identify any actor" in refusals
    assert "blocks `propose`" in refusals


def test_gaps_names_every_stage_a_gap_may_block():
    """A gap's `blocks` list is what makes the orchestrator halt. A pass that
    names only `propose` cannot express a gap that blocks instantiate.
    """
    enum = _world_schema()["$defs"]["gap"]["properties"]["blocks"]["items"]["enum"]
    method = _flat("reconcile-gaps", "3. Method")
    missing = [stage for stage in enum if stage not in method]
    assert not missing, f"the Method section never mentions blockable stage(s) {missing}"


def test_gaps_forbids_naming_blocks_narrowly_to_avoid_a_halt():
    """The refusal with a consequence outside the artifact: a blocking gap is the
    only mechanism this pipeline has for refusing to invent knowledge it does not
    have, and a gap detector that never stops a run is not doing its job.
    """
    refusals = _flat("reconcile-gaps", "5. Refusal conditions")
    assert "honestly rather than narrowly" in refusals
    assert "never leave it empty" in refusals


def test_gaps_audits_the_earlier_partials_and_may_not_edit_them():
    """The second half of this pass's method, which no other pass has and no gate
    can do: layer 2 checks that an element *references* a resolvable claim, never
    that the claim *supports* it, because support is semantic. Recording rather
    than editing is what keeps the record of which pass made the mistake.
    """
    method = _flat("reconcile-gaps", "3. Method")
    assert "audit every earlier partial" in method
    assert "never that the claim *supports* it" in method
    refusals = _flat("reconcile-gaps", "5. Refusal conditions")
    assert "do not edit that artifact" in refusals


def test_gaps_carries_the_confabulation_refusal_as_the_last_close_reader():
    """It was "you are the last stage that does" when one stage read every claim
    and wrote everything. Six passes later it is still true of this one, and only
    of this one: after it, nothing in the pipeline compares the world model
    against the evidence it came from.
    """
    refusals = _flat("reconcile-gaps", "5. Refusal conditions")
    assert "confabulation under under-specification" in refusals
    assert "you are the last pass that reads the claims closely" in refusals
