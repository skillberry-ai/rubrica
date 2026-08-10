"""tg-instantiate's contract, and the rules its prompt must state completely.

The vocabulary and grounding checks are the important ones. This stage writes
the artifact that reaches the scorer, and every rule it does not know is a rule
layer 2 will report *after* a fan-out has been paid for.
"""

from __future__ import annotations

from testgen.skills import SECTIONS, load, section_body, skills_dir
from testgen.suite.verify import ASSERTION_KINDS, DATA_KINDS, TRAJECTORY_KINDS
from testgen.validate import STAGE_ARTIFACTS

SKILL = skills_dir() / "tg-instantiate" / "SKILL.md"

# The section that owns the rules this file checks. Four tests below scope to
# it rather than to the whole file: `load(...).body` is the entire document,
# frontmatter and mandatory headings included, so a whole-body substring check
# is satisfied by text that has nothing to do with the property it names.
METHOD = SECTIONS[2]


def method_body() -> str:
    """The Method section's text, via the parser's own fence-aware slicer."""
    return section_body(load(SKILL), METHOD)


def paragraphs(text: str) -> list[str]:
    """Blank-line-separated paragraphs.

    Used where a property is really a *co-occurrence*: a rule and the remedy
    it prescribes have to be stated together to be followed, and two mentions
    in unrelated paragraphs are what made the whole-body versions of these
    checks vacuous.
    """
    return [chunk for chunk in text.split("\n\n") if chunk.strip()]


def test_the_contract_matches_the_stage_gate():
    skill = load(SKILL)
    assert skill.contract["stage"] == "instantiate"
    assert set(skill.contract["schemas"]) == set(STAGE_ARTIFACTS["instantiate"])


def test_it_writes_the_rationale_as_well_as_the_two_gated_artifacts():
    """Section 6 step 6: the rationale is what lets a reviewer judge fairness
    without reverse-engineering the seed. No schema gates it, so nothing but
    this would require it to exist.
    """
    writes = load(SKILL).contract["writes"]
    assert set(writes) == {"seed", "expected", "rationale"}


def test_it_has_the_five_sections():
    assert all(section in load(SKILL).headings for section in SECTIONS)


def test_it_names_every_kind_in_the_closed_vocabulary():
    """Imported from the scorer. A kind the skill does not know is a kind it
    cannot use; a kind it invents scores as failed and the schema does not
    catch it, because the shape is fine.
    """
    body = load(SKILL).body
    missing = [kind for kind in ASSERTION_KINDS if kind not in body]
    assert not missing, f"the skill never mentions assertion kind(s) {missing}"


def test_it_states_that_the_vocabulary_is_closed():
    """Where the five kinds are listed, that listing must be declared closed.

    **Strengthened from the plan's version under a Task 11 ruling.** The
    original was `"closed" in load(SKILL).body.lower()`, which this skill
    satisfies twice over with "closed objects" and "a closed object" -- both
    about JSON `additionalProperties`, neither about the assertion vocabulary.
    Deleting the sentence that says the vocabulary cannot be extended left it
    passing, so it bounded nothing.

    Checked as a co-occurrence in one paragraph: the paragraph that enumerates
    the vocabulary is the paragraph that has to say it is closed, since a
    reader who has just been handed five kinds is exactly the reader who needs
    to be told there is no sixth.
    """
    owning = [
        para for para in paragraphs(method_body()) if all(kind in para for kind in ASSERTION_KINDS)
    ]
    assert owning, "no single Method paragraph enumerates the whole assertion vocabulary"
    assert any("closed" in para.lower() for para in owning), (
        "the paragraph enumerating the vocabulary must say it is closed; a kind the skill "
        "invents scores as failed and no schema catches it"
    )


def test_it_states_the_grounding_rule_for_both_families():
    """Two rules, and getting them backwards is a schema failure per assertion:
    the expected schema forbids capability_id on a data kind and grounded_in on
    a tool kind.
    """
    body = load(SKILL).body
    assert "seed_pointer" in body
    assert "grounded_in" in body
    assert "capability_id" in body
    # Both families named, so the reader can tell which rule applies to which.
    for kind in DATA_KINDS:
        assert kind in body, kind
    for kind in TRAJECTORY_KINDS:
        assert kind in body, kind


def test_it_states_that_an_exclusion_must_resolve_to_nothing():
    """The inverted check. A skill that grounds answer_excludes the way it
    grounds answer_contains produces an assertion the reachability gate rejects
    with "the seed does contain what the assertion claims it lacks".
    """
    body = load(SKILL).body
    assert "answer_excludes" in body
    assert "resolve" in body.lower()


def test_it_requires_an_absence_scenario_to_carry_a_non_exclusion_assertion():
    """The invariant the toy world's smoke run produced.

    verify.score_assertions scores an exclusion satisfied by absence as a point,
    so a task made only of exclusions is substantially passable by an agent that
    answers nothing -- removing the weak-baseline signal exactly where the
    absence-shaped class of test lives. The skill must say so.

    **Strengthened from the plan's version under a Task 11 ruling.** The
    original's `"refusal" in body.lower()` was satisfied by the mandatory
    `## 5. Refusal conditions` heading itself -- `SECTIONS` requires that
    heading and `load` sets `body` to the whole file, so it held for every
    conforming skill in this build, permanently and regardless of content.
    Its other two clauses were whole-body too, and this skill names both kinds
    in its grounding rules, so all three passed without the absence rule
    existing anywhere.

    Checked as a co-occurrence in one Method paragraph, because the property
    is a pairing: the kind that is free to a do-nothing agent and the kind
    that has to accompany it are only actionable stated together.
    """
    owning = [
        para
        for para in paragraphs(method_body())
        if "answer_excludes" in para and "tool_called" in para
    ]
    assert owning, (
        "no single Method paragraph pairs answer_excludes with the tool_called that has to "
        "accompany it in an absence-shaped oracle"
    )
    assert any("refusal" in para.lower() or "answers nothing" in para.lower() for para in owning), (
        "that paragraph must say what the pairing is for: an agent that refuses collects the "
        "exclusion for free"
    )


def test_it_states_the_six_method_steps_in_order():
    """Section 6: "order of operations is the method". The distractor step
    before the seed step, and the answer derived *after* the seed exists -- a
    skill that seeds first and derives the answer later has no reachability
    guarantee, and one that writes the answer first has a label that may be
    true of nothing.

    Checked as an ordering of the step markers rather than of prose, so it is a
    structural assertion and not a substring search.

    **Scoped to the Method section under a Task 11 ruling.** Against the whole
    body, `"1."`, `"2."` and `"3."` resolved to the mandatory section headings
    `## 1. Inputs`, `## 2. Output` and `## 3. Method` -- so only 4 -> 5 -> 6
    was ever constrained, and the two orderings this docstring names first
    were not: Method steps 1-3 could be permuted freely, distractors-after-seed
    included. Slicing the section first makes all six markers the steps
    themselves.
    """
    method = method_body()
    markers = ["1.", "2.", "3.", "4.", "5.", "6."]
    positions = [method.find(marker) for marker in markers]
    assert all(p >= 0 for p in positions), "the six numbered steps must be present"
    assert positions == sorted(positions), "the numbered steps must appear in order"
    # Named separately, because these two are the orderings with consequences
    # and a bare sorted() failure would not say which one broke.
    assert positions[1] < positions[2], (
        "the distractor step must come before the seed step; a seed written first has whatever "
        "near-misses happen to fall out of it"
    )
    assert positions[2] < positions[3], (
        "the answer must be derived after the seed exists; written first, it is a label that "
        "may be true of nothing"
    )


def test_it_names_the_distractor_step_as_the_difficulty_lever():
    """Section 6 step 2 is explicit that the distractor set, not hop_depth, is
    what sets difficulty. A skill that treats hop_depth as the lever produces
    deep-but-trivial tasks.

    **Strengthened from the plan's version under a Task 11 ruling.** The
    original's two whole-body clauses were satisfied by the frontmatter
    description (which mentions distractors) and by section 1's list of the
    scenario fields this stage reads (which includes `hop_depth`). Method
    step 2 could have been deleted outright and it would still have passed.

    Checked as a co-occurrence in one Method paragraph, because the claim is a
    comparison between the two: naming them in separate places says nothing
    about which one is the lever.
    """
    contrasting = [
        para for para in paragraphs(method_body()) if "hop_depth" in para and "distractor" in para
    ]
    assert contrasting, (
        "no single Method paragraph contrasts the distractor set with hop_depth; the skill has "
        "to say which of the two actually sets difficulty"
    )


def test_it_requires_the_discriminating_fact_to_be_copied_verbatim():
    body = load(SKILL).body
    assert "discriminating_fact" in body
    assert "verbatim" in body.lower()
