"""tg-challenge's contract, and the ordering that makes it independent.

The ordering test is the one that matters and it is genuinely structural: the
Method section must mention expected.json strictly *after* it mentions
answering from the seed. An adversary that reads the oracle first confirms
almost anything, and no schema can catch that -- the artifact looks identical.
"""

from __future__ import annotations

from rubrica.artifacts import read_json
from rubrica.skills import SECTIONS, load, section_body, skills_dir
from rubrica.validate import ARTIFACT_SCHEMAS, STAGE_ARTIFACTS, schema_dir

SKILL = skills_dir() / "tg-challenge" / "SKILL.md"


def paragraphs(text: str) -> list[str]:
    """Blank-line-separated paragraphs.

    Used where a property is really a *co-occurrence*: a rule and the names it
    is about have to be stated together to be followed at all, and two mentions
    in unrelated sections are what makes a whole-body check vacuous.
    """
    return [chunk for chunk in text.split("\n\n") if chunk.strip()]


def _method_body() -> str:
    """The Method section alone, so the ordering below is about that section.

    Uses skills.section_body rather than splitting on "\\n## " by hand: that
    naive split is not fence-aware, and this skill's Method section contains a
    fenced block. A hand-rolled slice would cut at a `## ` line inside it and
    the ordering assertion would then be about a fragment.
    """
    skill = load(SKILL)
    assert SECTIONS[2] in skill.headings, "the Method section must exist"
    return section_body(skill, SECTIONS[2])


def test_the_contract_matches_the_stage_gate():
    skill = load(SKILL)
    assert skill.contract["stage"] == "challenge"
    assert set(skill.contract["schemas"]) == set(STAGE_ARTIFACTS["challenge"])
    # `reads` is pinned exactly, and this clause is load-bearing rather than
    # decorative. check_contract only requires each entry to be a public
    # RunPaths attribute, so `world_model` -- or any other artifact -- could be
    # added to this adversary's context and every other test in this file would
    # still pass. It was ruled deliberately withheld: refs._check_invariants
    # already evaluates every `machine:` invariant over every seed and the
    # orchestrator runs check-refs, so declaring the world model would buy no
    # coverage and add anchoring surface to the one stage whose entire value is
    # not being anchored. Widening this set is a plan-level decision.
    assert set(skill.contract["reads"]) == {"scenarios", "seed", "expected"}, (
        "tg-challenge reads exactly the scenario list, its own seed and its own oracle; "
        "any further read widens the context of the stage that exists to be un-anchored"
    )


def test_it_has_the_five_sections():
    assert all(section in load(SKILL).headings for section in SECTIONS)


def test_the_method_mentions_the_seed_before_it_mentions_the_oracle():
    """The independence, as a position comparison inside one section.

    This is the only mechanical grip there is on the ordering: the verdict
    artifact produced by an anchored adversary is byte-identical to one produced
    by an independent adversary, so nothing downstream can tell them apart. The
    live exercise is the real check; this stops the ordering being *removed*
    from the prompt.
    """
    method = _method_body()
    seed_at = method.find("seed.json")
    oracle_at = method.find("expected.json")
    assert seed_at >= 0, "the Method must name seed.json"
    assert oracle_at >= 0, "the Method must name expected.json"
    assert seed_at < oracle_at, "the Method must reach the seed before the oracle"


def test_the_method_says_the_oracle_is_read_last():
    """The ordering word has to sit in the paragraph that first names the oracle.

    **Strengthened from the plan's version under a fix-round-1 ruling.** The
    original was `"last" in method or "only then" in method` over the whole
    Method section. Measured against the delivered skill and confirmed by the
    reviewer: `"last"` occurred nowhere in Method, so the assertion rested
    entirely on `"only then"` in step 4's heading -- and the `"last"` disjunct
    is satisfiable by content that has nothing to do with the ordering. This
    fixture's own `scn-blocked` discriminating fact is "only its *last* comment
    names the blocker", so any future edit quoting it inside Method would
    satisfy the test permanently with the ordering sentence deleted. This is
    the only automated guard on this skill's central property, so a floor that
    can be satisfied by an unrelated word is not good enough.

    Checked as a co-occurrence in the Method paragraph that *first* names
    `expected.json`, because that is the paragraph a reader meets before any
    step tells them anything: whatever it says about the oracle is what a model
    reading in order acts on.
    """
    first_oracle = next(
        (para for para in paragraphs(_method_body()) if "expected.json" in para), None
    )
    assert first_oracle is not None, "the Method must name expected.json"
    lowered = first_oracle.lower()
    assert "last" in lowered or "only then" in lowered, (
        "the first Method paragraph to name expected.json must say when it is read; naming "
        "the oracle without the ordering is where an anchored adversary comes from:\n"
        f"{first_oracle}"
    )


def test_it_names_every_verdict_value():
    schema = read_json(schema_dir() / ARTIFACT_SCHEMAS["verdict"])
    enum = schema["properties"]["verdict"]["enum"]
    body = load(SKILL).body
    missing = [verdict for verdict in enum if verdict not in body]
    assert not missing, f"the skill never mentions verdict(s) {missing}"


def test_it_names_every_flag_the_schema_allows():
    """difficulty_overstated is the only one today, and it is required when the
    adversary beats the claimed hop_depth -- refs.check_verdicts reports its
    absence, so a skill that does not know it exists produces a finding on a
    verdict that is otherwise correct.
    """
    schema = read_json(schema_dir() / ARTIFACT_SCHEMAS["verdict"])
    enum = schema["properties"]["flags"]["items"]["enum"]
    body = load(SKILL).body
    missing = [flag for flag in enum if flag not in body]
    assert not missing, f"the skill never mentions flag(s) {missing}"


def test_it_names_the_four_judgment_fields_the_verdict_carries():
    """Renamed: the old name said "the three boolean judgments and the call
    count", and the four fields are two booleans, an integer and an array --
    `alternative_answers` has never been a boolean and `minimum_tool_calls_found`
    is the count the old name already accounted for separately, so the name
    described a five-field verdict that does not exist.

    Derived from the schema rather than listed, so the name cannot drift from the
    fields again: every property of `verdict-0.1.json` that carries a *judgment*
    (as opposed to identity or the rendered verdict itself) must be named.
    """
    schema = read_json(schema_dir() / ARTIFACT_SCHEMAS["verdict"])
    identity = {"schema_version", "scenario_id", "verdict", "flags", "notes"}
    judgments = sorted(set(schema["properties"]) - identity)
    body = load(SKILL).body
    missing = [field for field in judgments if field not in body]
    assert not missing, f"the skill never mentions judgment field(s) {missing}"


def test_it_states_that_accept_is_incompatible_with_the_two_negatives():
    """check_verdicts reports accept alongside either false. A skill that does
    not know produces a self-contradictory verdict and spends the repair attempt.

    **Strengthened from the plan's version, which its own implementer note
    invited replacing.** The original was
    `load(SKILL).body.count("uniquely_determined") >= 2` -- shape 1 with a
    counter attached. It bounded nothing about the incompatibility: this skill
    names `uniquely_determined` in section 2's field list, in Method step 2
    where the judgment is made, and in the verdict-table prose, so deleting the
    Invariants entry that states the incompatibility outright still left three
    occurrences and the count passing.

    Checked instead as a co-occurrence inside the Invariants section, because
    the property is a *pairing of three names*: `accept` and both negatives
    have to appear together for the rule to be readable at all, and the section
    that owns a rule of this kind is the one the reader consults before filing
    a verdict.
    """
    invariants = section_body(load(SKILL), SECTIONS[3])
    owning = [
        para
        for para in paragraphs(invariants)
        if "accept" in para
        and "uniquely_determined" in para
        and "derivable_without_guessing" in para
    ]
    assert owning, (
        "no single Invariants paragraph states that accept is incompatible with both "
        "uniquely_determined: false and derivable_without_guessing: false; check_verdicts "
        "reports either combination, and a skill that does not know spends the repair attempt"
    )


def test_it_tells_the_adversary_to_report_the_oracle_wrong_when_it_is():
    """Row 4 of the verdict table: the highest-value catch in the pipeline, and
    the one a helpful model will not make unless told to.

    **Strengthened from the plan's version under a fix-round-1 ruling.** The
    original was `"disagree" in load(SKILL).body.lower()`. `"disagree"` occurs
    six times in the delivered skill and two of them have nothing to do with
    this property -- "a denormalised count that disagrees with the records it
    counts" in Method step 3, and a `scenario_id` that "disagrees with the name
    it is filed under" in Invariant 1. So both the section-5 condition *and*
    the brief-supplied verdict-table row could be deleted with the test still
    green, on the row the plan calls the pipeline's highest-value catch.

    Checked as a co-occurrence in the section-5 paragraph that owns the
    instruction: the trigger (a disagreement with `expected.json`) and the
    required action (say in `notes` that the oracle looks wrong) are only
    actionable stated together, and a helpful model needs the action spelled
    out or it defers to the label.
    """
    owning = [
        para
        for para in paragraphs(section_body(load(SKILL), SECTIONS[4]))
        if "expected.json" in para and "oracle looks wrong" in para.lower()
    ]
    assert owning, (
        "no Refusal-conditions paragraph pairs a disagreement with expected.json with the "
        "instruction to say in notes that the oracle looks wrong; a skill that leaves this "
        "out deletes the pipeline's highest-value catch, and a helpful model defers"
    )
    assert any("disagree" in para.lower() for para in owning), (
        "that paragraph must state the trigger as a disagreement, so the reader knows when "
        "the instruction applies"
    )
