"""rb-propose's contract, and the two status boundaries it must not cross.

The status boundary is the one that matters here: propose writes `proposed`,
and score owns every other transition. A skill that writes `active` closes the
loop's judgment step by fiat, and refs would not notice -- `active` is a
perfectly valid status for a scenario to have.
"""

from __future__ import annotations

from rubrica.artifacts import read_json
from rubrica.skills import SECTIONS, load, skills_dir
from rubrica.validate import ARTIFACT_SCHEMAS, STAGE_ARTIFACTS, schema_dir

SKILL = skills_dir() / "rb-propose" / "SKILL.md"


def test_the_contract_matches_the_stage_gate():
    skill = load(SKILL)
    assert skill.contract["stage"] == "propose"
    assert set(skill.contract["schemas"]) == set(STAGE_ARTIFACTS["propose"])


def test_it_both_reads_and_writes_the_scenarios_file():
    """Append-only across rounds: round 2 reads what round 1 proposed. A
    contract that only wrote it would license a rewrite, and a rewritten
    02-scenarios.json loses round 1's provenance.
    """
    contract = load(SKILL).contract
    assert "scenarios" in contract["reads"]
    assert "scenarios" in contract["writes"]


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
