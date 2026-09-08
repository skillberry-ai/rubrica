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

import re

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


def _bullets(stage: str, heading: str) -> list[str]:
    """One entry per top-level `- ` bullet in a section, each flattened like _flat.

    A continuation line joins the bullet above it, so a wrapped bullet is one
    entry rather than several. Anything before the first bullet -- a section's
    intro paragraph -- is deliberately dropped: this exists to scope an assertion
    to the condition that owns a rule, and an intro is owned by none of them.
    """
    out: list[str] = []
    for line in section_body(_skill(stage), heading).splitlines():
        if line.startswith("- "):
            out.append(line)
        elif out:
            out[-1] += " " + line
    return [" ".join(bullet.lower().split()) for bullet in out]


def _bullet_carrying(stage: str, heading: str, *keys: str) -> str:
    """The one bullet in a section carrying any of `keys`, flattened.

    Asserting inside one bullet rather than over a whole section is what makes a
    §5 assertion mean something: `assert "guess" in refusals` is satisfied by any
    of five sibling conditions, so a rule deleted from the one that owns it stays
    green. The exactly-one check is part of the instrument -- a key that matches
    two bullets is not a locator, and one that matches none means the rule is gone
    rather than that the test should quietly pass.
    """
    found = [bullet for bullet in _bullets(stage, heading) if any(k in bullet for k in keys)]
    assert len(found) == 1, (
        f"{keys} locates {len(found)} bullet(s) in {stage}'s {heading}, not one: {found}"
    )
    return found[0]


def _world_schema():
    return read_json(schema_dir() / ARTIFACT_SCHEMAS["world-model"])


def test_the_family_is_exactly_the_stages_between_extract_and_propose_batches():
    """Guards the derivation above, and the ordering the passes that have a real
    dependency depend on: outcomes quantifies over capabilities' output, entities
    and goals read the partials above them, gaps audits all of them, and the seal
    runs last. A reordering among those is a real change to what each pass can
    read, not a cosmetic one.

    `reconcile-services` is pinned here on a different footing, and this docstring
    must not be read as giving it a dependency it does not have *upward*: it reads
    no partial, and every claims file exists the moment `extract` finishes, so
    nothing above it constrains the slot. Its readers below do -- both
    `synthesise-interfaces` and the seal read the part it writes, the seal folding
    it into the world model's optional `services` field -- so it cannot sort after
    either. The comment beside it in `paths.STAGES` says exactly that, and the two
    must not disagree. What the position pins beyond that window is the
    *documentation*: STAGES is the on-disk numbering and both generated drawings
    render it in order, so moving it silently would redraw the family.

    `synthesise-interfaces` is in the slice and is **not** in `FAMILY`: it is code,
    it has no skill, and it merges nothing -- it derives one OpenAPI document per
    service from `01-services.json`. Its position is a dependency for the same
    reason, one step further: it reads the part the pass before it writes.
    """
    assert STAGES[STAGES.index("extract") + 1 : STAGES.index("propose-batches")] == (
        "reconcile-subjects",
        "reconcile-contradict",
        "reconcile-capabilities",
        "reconcile-outcomes",
        "reconcile-entities",
        "reconcile-goals",
        "reconcile-gaps",
        "reconcile-services",
        "synthesise-interfaces",
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


# The passes that own a claim kind and therefore carry an inputs_seen
# accounting. Derived from the schema rather than restated: a part schema that
# gains the field joins this parametrization without anyone editing a literal.
OWNING = tuple(
    stage
    for stage in FAMILY
    if "inputs_seen"
    in read_json(schema_dir() / ARTIFACT_SCHEMAS[STAGE_ARTIFACTS[stage][0]]).get("properties", {})
)


# The complement, derived so it cannot drift from OWNING: these passes have no
# field in which a partial read could be recorded, which is why the reading bound
# below says so to them and routes the others to their accounting.
UNACCOUNTED = tuple(stage for stage in FAMILY if stage not in OWNING)


def test_the_unaccounted_passes_are_the_complement_of_the_owning_ones():
    """A guard on the derivation, the mirror of the one below it. If a partial ever
    gains inputs_seen, this roster shrinks and the pass moves to the accounting
    branch of the reading bound rather than keeping prose that says its partial
    reads are invisible."""
    assert UNACCOUNTED == (
        "reconcile-subjects",
        "reconcile-contradict",
        "reconcile-gaps",
    ), UNACCOUNTED


@pytest.mark.parametrize("stage", FAMILY)
def test_the_method_bounds_how_the_claims_are_read(stage):
    """Every pass reads all of `01-claims/` and nothing bounded HOW.

    The band is linear in admitted-input count, and on tau2-retail it crossed the
    ceiling: `rb-reconcile-outcomes` died with `Prompt is too long` after 84 turns
    and 80 `Read` calls against a 22-input, 403 KB `01-claims/`. None of those 80
    calls passed `offset` or `limit`, and the same eight claim files were read three
    times each as the member ran out of room.

    `offset` and `limit` occur in **no** Method section in this family today --
    measured across all eight before this predicate was written -- so it cannot be
    satisfied by prose that predates the instruction.
    """
    method = _flat(stage, "3. Method")
    assert "offset" in method and "limit" in method, (
        f"{stage}'s Method names no bounded-read mechanism"
    )


@pytest.mark.parametrize("stage", FAMILY)
def test_the_reading_bound_carries_the_failure_that_justifies_it(stage):
    """Prose buys a probability, and an instruction whose cost is invisible is the
    first thing a member under pressure drops. The measured failure is what makes
    this one worth obeying, so the instruction and the death are asserted together.
    """
    method = _flat(stage, "3. Method")
    assert "prompt is too long" in method, f"{stage}'s Method does not name the failure"
    assert "re-read" in method or "reread" in method, (
        f"{stage}'s Method does not name re-reading as what caused it"
    )


@pytest.mark.parametrize("stage", UNACCOUNTED)
def test_a_pass_with_no_accounting_is_told_its_partial_reads_are_invisible(stage):
    """These three have no `inputs_seen`, so nothing downstream can tell that one of
    them read half the claims. That is an argument for the bound being tighter here,
    not looser, and the prose has to say which of the two situations the pass is in
    -- otherwise the instruction reads as though a note somewhere would cover it.
    """
    method = _flat(stage, "3. Method")
    assert "no field" in method or "nowhere" in method, (
        f"{stage} has no inputs_seen and its Method does not say a partial read is recorded nowhere"
    )


def test_the_owning_passes_are_exactly_the_ones_with_a_claim_kind():
    """A guard on the derivation above, not a restatement of it.

    If another partial gains inputs_seen, this fails and someone has to decide
    whether that pass really owns a claim kind -- rb-reconcile-gaps owns none,
    and giving it an accounting would assert a read coverage no output shape can
    force. The list is the same roster refs.PASS_OWN_KINDS carries, reached from
    the other side: this one reads the schemas, that one names the kinds, and a
    pass added to either without the other is what this catches.
    """
    assert OWNING == (
        "reconcile-capabilities",
        "reconcile-outcomes",
        "reconcile-entities",
        "reconcile-goals",
        "reconcile-services",
    ), OWNING


@pytest.mark.parametrize("stage", OWNING)
def test_the_output_section_states_the_accounting_is_total_over_the_manifest(stage):
    """Totality is the whole instrument, so the prose that describes it must say
    which set it is total over. A pass told only to "record what you read"
    records what it read, which is the artifact issue #6 already has.
    """
    output = _flat(stage, "2. Output")
    assert "inputs_seen" in output
    assert "manifest.inputs" in output
    assert "every input" in output


@pytest.mark.parametrize("stage", OWNING)
def test_the_method_says_to_record_the_row_as_each_file_is_finished(stage):
    """A row reconstructed at the end is a recollection of having read.

    That is the distinction the accounting exists to draw, so the instruction
    has to be about *when*, not only about *what*.

    "not" is in every Method section already, measured; "as you finish" and "at
    the end" are the two that carry the rule, and deleting the step turns both
    red.
    """
    method = _flat(stage, "3. Method")
    assert "as you finish" in method
    assert "not" in method and "at the end" in method


@pytest.mark.parametrize("stage", OWNING)
def test_the_invariants_say_the_counts_are_recomputed_rather_than_trusted(stage):
    """A pass that believes its numbers are taken on faith has no reason to
    measure them. Naming the checker is what makes the obligation legible.

    "check-refs" alone is satisfied by the run-both-commands paragraph that
    already closes every §4, measured -- so "recomputes" and "own_kind_total"
    are what this actually pins.
    """
    invariants = _flat(stage, "4. Invariants")
    assert "check-refs" in invariants
    assert "recomputes" in invariants
    assert "own_kind_total" in invariants


@pytest.mark.parametrize("stage", OWNING)
def test_a_claims_file_that_cannot_be_read_is_a_refusal_not_a_guessed_count(stage):
    """The one new refusal condition, and the one that can defeat the whole
    change: a pass that guesses four numbers to satisfy the schema has produced
    a clean artifact that means nothing.
    """
    refusals = _flat(stage, "5. Refusal conditions")
    assert "could not read" in refusals
    assert "guess" in refusals
    assert "refuse" in refusals


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


def test_outcomes_says_what_an_underspecified_class_cites():
    """`$defs/outcome_class` requires `claims` with `minItems: 1`, and
    `underspecified` is the kind written precisely where no claim states the
    behaviour -- so a pass told to write one, with nowhere named to point it,
    either fabricates an id (which `refs.check_world_model` catches only after
    the seal, at gate 1, against an artifact this pass finished long before) or
    refuses a class §3 tells it to write. The rule that closes the gap: cite the
    claims that establish the *operation* the class belongs to.

    "cite" and "underspecified" were both in this section already, measured, so
    "operation" is the token carrying the rule -- and Output is the section that
    owns it because Method uses all three words for other purposes.
    """
    output = _flat("reconcile-outcomes", "2. Output")
    assert "underspecified" in output
    assert "operation" in output
    assert "cite" in output


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
    and wrote everything. Passes later it is still true of this one, and only of
    this one: after it, nothing in the pipeline compares the world model against
    the evidence it came from. `rb-reconcile-services` is dispatched after it and
    reads the claims too, but it reads them to group tools rather than to check a
    model against them, which is why the claim survives as stated below.

    Scoped to the owning bullet and asserted as concepts, not as a sentence. This
    pinned the exact phrase "you are the last pass that reads the claims closely"
    until `reconcile-services` made that sentence false; the sentence was
    corrected, and an exact pin would then have gone red on the correction rather
    than on the defect -- the phrase-pin failure this repository has already had
    once. Locating the bullet by "confabulation" is what keeps the assertions off
    the four sibling conditions in the same section.
    """
    bullet = _bullet_carrying("reconcile-gaps", "5. Refusal conditions", "confabulation")
    assert "under-specification" in bullet
    # The last-ness, and what it is last *with respect to*. An OR over the three
    # natural formulations rather than one of them, because which noun carries it
    # is exactly the part a meaning-preserving reword changes.
    assert any(k in bullet for k in ("last pass", "last stage", "last to read")), bullet
    assert "claims" in bullet
    # And why the last-ness matters: nothing after this pass can tell an invention
    # from a fact. The verb is the rewordable part, so this is an OR too.
    assert any(k in bullet for k in ("catch", "detect", "notice")), bullet


def test_gaps_says_a_gap_cites_the_claims_that_make_the_absence_matter():
    """rb-reconcile-gaps gets no accounting -- it owns no claim kind -- so the
    gap's own claims array is the whole of what it gained. The distinction the
    prose has to carry: the claims are not evidence *for* the unknown, they are
    evidence the unknown matters.

    Both tokens are scoped tighter than the obvious ones: bare "claims" and
    "why_it_matters" were both already in this section before the array existed
    ("built from claims that actually leave things unstated", and the field
    list), so a predicate on either is green with the new paragraph deleted --
    measured, which is why it names the array and the word the distinction turns
    on instead.
    """
    output = _flat("reconcile-gaps", "2. Output")
    assert "`claims` array" in output
    assert "absence" in output


def _missing_input_refusal(stage: str) -> str:
    """The one §5 bullet in `stage` that owns the missing-input refusal.

    Located by "run directory"/"unreadable" rather than by "absent", and the
    choice is the instrument. Measured before the bullet was written: no §5
    bullet anywhere in the family carried "absent", "run directory" or
    "unreadable", so any of the three was a unique locator then -- but
    `reconcile-gaps` now deliberately carries a *second* bullet naming absence,
    the one routing it here, so "absent" would locate two bullets there and
    `_bullet_carrying`'s exactly-one check would fail against correct prose.
    The alternation is over the two ways the trigger names a file it cannot
    take, because which of them survives a meaning-preserving reword is exactly
    the part not worth pinning to one.
    """
    return _bullet_carrying(stage, "5. Refusal conditions", "run directory", "unreadable")


@pytest.mark.parametrize("stage", FAMILY)
def test_every_pass_refuses_a_missing_input_rather_than_modelling_around_it(stage):
    """Issue #36: three passes met the same absent partial and two answered one way.

    `reconcile-outcomes` and `reconcile-entities` refused, naming the missing
    `01-capabilities.json`; `reconcile-gaps` recorded the absence in its own
    artifact and halted the run. Nothing in any §5 picked between the two
    answers -- the five passes that own a claim kind carried "a claims file you
    could not read", which is narrower on both ends (a claims file, not a
    partial; a guessed `own_kind_total`, not a modelled-around hole), and
    `subjects`, `contradict` and `gaps` carried nothing at all. So the rule is
    asserted over the whole derived family rather than over a roster: a pass
    added to the band inherits the obligation without anyone editing a list.
    """
    bullet = _missing_input_refusal(stage)
    # The trigger. "absent" is the token, not the locator -- see the helper.
    assert "absent" in bullet, bullet
    # The action, both halves: a refusal that does not stop leaves the pass free
    # to write the artifact anyway, which is the failure being ruled out.
    #
    # Word-bounded and imperative-only, because a substring check is satisfied
    # here by the bullet's own closing measurement -- "the ones that refused cost
    # a re-dispatch each" and "Refusing is the cheap answer" both contain
    # "refus", so `"refuse" in bullet` stayed green with the instruction sentence
    # struck. Measured, and it is the substring-of-message trap one bullet down
    # from where the convention usually catches it. `\brefuse\b` matches neither
    # inflection.
    assert re.search(r"\b(?:refuse|decline)\b", bullet), bullet
    assert re.search(r"\bstop\b", bullet), bullet
    # And what it may not do instead. The verb is the rewordable part, so this is
    # an OR over the two formulations the bullet uses for one prohibition.
    assert any(k in bullet for k in ("do not model around", "do not infer")), bullet


@pytest.mark.parametrize("stage", FAMILY)
def test_the_missing_input_refusal_forbids_recording_the_absence_as_output(stage):
    """The half that reaches outside the refusing pass.

    Refusing and recording are not the same failure: a pass that writes the
    absence into its own artifact has produced a schema-valid statement about
    the *run* inside a document every later stage reads as a statement about the
    *target*, and neither check layer can tell them apart -- `check-refs` has
    nothing to compare the prose against. That is what halted
    `run-20260907-065440`, so the ground is asserted with the prohibition rather
    than left to the reader.
    """
    bullet = _missing_input_refusal(stage)
    # The prohibition, with the verb left free: which of record/write/report
    # carries it is the part a meaning-preserving reword changes, and the object
    # is what the rule is about.
    assert re.search(r"(?:do not|never) (?:record|write|report) the absence", bullet), bullet
    # The ground it rests on, without which the prohibition reads as a style note.
    assert any(k in bullet for k in ("fact about the run", "not about the target")), bullet


def test_the_missing_input_refusal_is_worded_identically_across_the_family():
    """Uniformity is the fix, not the wording. Issue #36's second suggestion asks
    for the rule to live in one place; there is no include mechanism for a
    SKILL.md, so byte-identity across the eight copies is the enforceable proxy.

    This is deliberately *not* a phrase pin: it is invariant under any reword
    applied to all eight and red only on drift in one, which is the state the
    issue reported -- three passes asked the same question, two answers.
    """
    worded = {stage: _missing_input_refusal(stage) for stage in FAMILY}
    assert len(set(worded.values())) == 1, sorted(worded)


def test_gaps_routes_an_absent_partial_to_refusal_and_a_wrong_one_to_a_gap():
    """The ruling issue #36 is really about, and it is a split rather than an
    addition: the audit's own §5 condition used to say "finds a defect ... record
    it as a gap", and absence is a defect by any reading. The pass obeyed it. So
    the two cases are now two bullets -- wrongness keeps the gap, absence routes
    to the refusal every sibling now carries.

    Located by the *trigger* -- the absent/wrong distinction -- and deliberately
    not by the ruling sentence: locating on "never about the run" made the
    ruling its own locator, so striking that sentence failed as "locates 0
    bullets" and the assertion below it was never independently exercised.
    Measured: each of "not a gap", "rather than wrong", "absent rather than",
    "never about the run" and "is about the target" locates exactly this bullet
    today, so the alternation is over trigger wordings only. Bare "absent"
    locates two bullets here by design -- this one and the shared refusal it
    routes to -- and "gap" locates five.
    """
    absent = _bullet_carrying(
        "reconcile-gaps", "5. Refusal conditions", "rather than wrong", "absent rather than"
    )
    assert "absent" in absent, absent
    assert "not a gap" in absent, absent
    # The ruling, stated as the rule rather than as this one case, so a later
    # reader does not have to re-derive it from the example.
    assert "`gaps` entry is about the target" in absent, absent
    # Why an absent partial cannot be one: a gap's subject names the target, and
    # a file nobody has written names nothing about it.
    assert any(k in absent for k in ("no target subject", "names nothing about")), absent
    # And the cost that makes it worse than an ordinary bad gap: it was true when
    # written and false by the time anyone could read it.
    assert "false when read" in absent, absent

    # The other half of the split, still a gap. Located by the prohibition that
    # keeps the record of which pass erred, which only this bullet carries.
    wrong = _bullet_carrying("reconcile-gaps", "5. Refusal conditions", "do not edit that artifact")
    assert "wrong" in wrong, wrong
    assert "record it as a gap" in wrong, wrong
