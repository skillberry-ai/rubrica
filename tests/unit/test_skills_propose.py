"""rb-propose's contract, and the two status boundaries it must not cross.

The status boundary is the one that matters here: propose writes `proposed`,
and score owns every other transition. A skill that writes `active` closes the
loop's judgment step by fiat, and refs would not notice -- `active` is a
perfectly valid status for a scenario to have.
"""

from __future__ import annotations

import re

from rubrica.artifacts import read_json
from rubrica.skills import SECTIONS, load, section_body, skills_dir
from rubrica.validate import ARTIFACT_SCHEMAS, STAGE_ARTIFACTS, schema_dir

SKILL = skills_dir() / "rb-propose" / "SKILL.md"

INPUTS, OUTPUT, INVARIANTS = SECTIONS[0], SECTIONS[1], SECTIONS[3]


def blocks(heading: str) -> list[str]:
    """Blank-line-separated blocks of one section, via the parser's own slicer.

    The same helper `test_skills_score.py` defines, for the same measured
    reason: `load(...).body` is the whole document, so a whole-body substring
    check for any rule below is satisfied by the frontmatter `description:`
    line, by the mandatory contract block, or by prose belonging to a different
    rule. Every predicate here is a *co-occurrence inside the block that owns
    the rule*, never a presence anywhere in the file.
    """
    return [chunk for chunk in section_body(load(SKILL), heading).split("\n\n") if chunk.strip()]


def test_the_contract_matches_the_stage_gate():
    skill = load(SKILL)
    assert skill.contract["stage"] == "propose"
    assert set(skill.contract["schemas"]) == set(STAGE_ARTIFACTS["propose"])


def test_it_reads_its_batch_plan_and_writes_only_its_own_part():
    """The scenario list is on neither side of this contract any more, and both
    absences are the point rather than an omission.

    It does not READ it because the worklist is now the batch plan: a
    `not_yet_attempted` hole is by definition one no scenario covers, and score
    folds anything that slips, so nothing a member needs is in the accumulating
    document. It does not WRITE it because `propose-seal` does -- an append that
    every member performed on one shared file is exactly the re-emit the round
    cap was blowing on, and a member that rewrote it would lose a sibling's
    provenance rather than its own.

    Both directions are asserted: a contract that quietly kept `scenarios` on
    either side would pass a presence-only check of the two names that replaced
    it.
    """
    contract = load(SKILL).contract
    assert "batches" in contract["reads"]
    assert "scenario_part" in contract["writes"]
    assert "scenarios" not in contract["reads"]
    assert "scenarios" not in contract["writes"]


def test_it_has_the_five_sections():
    assert all(section in load(SKILL).headings for section in SECTIONS)


def test_it_names_every_hole_reason_so_it_can_tell_closable_from_not():
    """A hole whose reason is blocked_by_gap is not closable by proposing. A
    skill that does not know the vocabulary cannot make that distinction and
    will propose against a gap.
    """
    schema = read_json(schema_dir() / ARTIFACT_SCHEMAS["coverage"])
    enum = schema["$defs"]["hole"]["properties"]["reason"]["enum"]
    body = load(SKILL).body
    missing = [reason for reason in enum if reason not in body]
    assert not missing, f"the skill never mentions hole reason(s) {missing}"


def test_it_states_that_it_writes_only_the_proposed_status():
    """The boundary, checked against the scenarios schema's own status enum.

    The authority for which statuses exist is the schema, not refs.py's two
    subsets. `OPEN_STATUSES | JUDGED_STATUSES` is {proposed, active, rejected}
    and omits `duplicate` entirely -- no refs check needs to name it -- so a
    test built on those sets passes against a skill whose prose never mentions
    `duplicate`. That is the likeliest omission of the four, because
    `duplicate` is set by score's dedupe ruling rather than by an obvious
    judgement verb, and Method step 7 names it explicitly. Deriving from the
    enum also gives the property the docstring used to claim falsely: a fifth
    status added to the schema fails here.
    """
    schema = read_json(schema_dir() / ARTIFACT_SCHEMAS["scenarios"])
    enum = schema["$defs"]["scenario"]["properties"]["status"]["enum"]
    assert "proposed" in enum, "the status this skill writes must exist"
    body = load(SKILL).body
    assert "proposed" in body
    score_owned = [status for status in enum if status != "proposed"]
    assert score_owned, "the set this test is about must not be empty"
    # The skill must name each status it may not write, so a reader of the
    # prompt knows the boundary rather than inferring it.
    missing = [status for status in score_owned if status not in body]
    assert not missing, f"the skill never says it must not write {missing}"


def test_it_names_the_two_manifest_limits_it_must_respect():
    """check_limits reports a round above max_rounds and an open-scenario count
    above max_scenarios. A skill that does not know the caps exist will hit them
    and spend the orchestrator's one repair attempt.
    """
    body = load(SKILL).body
    for limit in ("max_rounds", "max_scenarios"):
        assert limit in body, limit


def test_it_names_the_discriminating_fact_field():
    assert "discriminating_fact" in load(SKILL).body


def test_inputs_says_why_the_scenario_list_is_on_neither_side_of_the_contract():
    """The contract test above pins that `scenarios` is gone from `reads` and
    `writes`. This pins that the prose *says why*, which is the half a model
    dispatched with the file actually reads.

    Both halves have to be there, and they have different reasons. It does not
    read the document because a hole reaches a member only as
    `not_yet_attempted` -- by definition a row no scenario covers -- and score
    folds any duplicate that slips, so nothing a member needs is in there. It
    does not write it because `propose-seal` does.

    Scoped to the block that names the file rather than to the section, because
    `02-scenarios.json` appears in the Method and Invariants sections too (the
    seal's own document, and the artifact `check_limits` reports an overflow
    against), and a section-wide check would let the justification be deleted
    while some other rule's mention kept it green.
    """
    owning = [block for block in blocks(INPUTS) if "02-scenarios.json" in block]
    assert owning, "the Inputs section never names the document it no longer reads"
    assert any(
        "not_yet_attempted" in block and re.search(r"fold|duplicate", block, re.I)
        for block in owning
    ), (
        "no block naming 02-scenarios.json says why reading it is unnecessary: the hole "
        "reason that makes it redundant, and score folding what slips"
    )
    assert any("propose-seal" in block for block in owning), (
        "no block naming 02-scenarios.json names propose-seal as what writes it instead"
    )


def test_output_requires_the_batch_prefixed_scenario_id():
    """Members mint their own ids and no member can see a sibling's part, so the
    batch prefix is the whole of what stops two members choosing one id.
    `rounds.collect_scenarios` refuses a collision and `seal_scenarios` then
    writes nothing at all, so one member ignoring this costs the round's seal
    rather than its own part -- which is why the cost has to be stated here and
    not only the rule.

    `batch[_ ]id` rather than the literal `batch_id`: "your batch id as its
    prefix" preserves the rule exactly, and pinning the underscore would have
    made an innocuous reword red. The prefix template itself is a format and has
    no paraphrase, so `sc-` is safe to pin.
    """
    owning = [
        block
        for block in blocks(OUTPUT)
        if "sc-" in block and re.search(r"batch[_ ]id", block, re.I)
    ]
    assert owning, "no Output block ties the scenario id it must mint to its own batch id"
    assert any(re.search(r"collision|collide", block, re.I) for block in owning), (
        "that block must say what the prefix prevents and what ignoring it costs"
    )


def test_invariants_hold_every_hole_ref_to_the_members_own_batch():
    """The one rule that makes the partition enforceable rather than merely
    instructed, and the one no other layer can see: a member that wandered into
    a sibling's holes writes a part byte-identical to one that did not, so only
    `refs.check_scenario_parts` -- resolving `provenance.hole_refs` against the
    plan -- can report it.

    The field matters and is asserted: resolving `goal_id` and `capability_refs`
    instead was measured to report 19 of 22 *correct* scenarios (Ruling R21),
    because the ids a scenario names are not the holes it targets.
    `provenance.hole_refs` is the member's own declaration of what it targeted,
    which is why that is the field the checker reads and the field this
    invariant has to name.
    """
    owning = [
        block
        for block in blocks(INVARIANTS)
        if "hole_refs" in block and "check_scenario_parts" in block
    ]
    assert owning, "no Invariants block ties provenance.hole_refs to the checker that resolves it"
    assert any(re.search(r"\bown batch\b", block) for block in owning), (
        "that invariant must say the refs have to be the member's OWN batch's, which is the "
        "half no schema and no other layer can see"
    )
