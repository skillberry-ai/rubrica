"""tg-instantiate's contract, and the rules its prompt must state completely.

The vocabulary and grounding checks are the important ones. This stage writes
the artifact that reaches the scorer, and every rule it does not know is a rule
layer 2 will report *after* a fan-out has been paid for.
"""

from __future__ import annotations

from testgen.skills import SECTIONS, load, skills_dir
from testgen.suite.verify import ASSERTION_KINDS, DATA_KINDS, TRAJECTORY_KINDS
from testgen.validate import STAGE_ARTIFACTS

SKILL = skills_dir() / "tg-instantiate" / "SKILL.md"


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
    body = load(SKILL).body.lower()
    assert "closed" in body, "the skill must say the vocabulary cannot be extended"


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
    """
    body = load(SKILL).body
    assert "refusal" in body.lower() or "answers nothing" in body.lower()
    assert "answer_excludes" in body
    assert "tool_called" in body


def test_it_states_the_six_method_steps_in_order():
    """Section 6: "order of operations is the method". The distractor step
    before the seed step, and the answer derived *after* the seed exists -- a
    skill that seeds first and derives the answer later has no reachability
    guarantee, and one that writes the answer first has a label that may be
    true of nothing.

    Checked as an ordering of the step markers rather than of prose, so it is a
    structural assertion and not a substring search.
    """
    body = load(SKILL).body
    markers = ["1.", "2.", "3.", "4.", "5.", "6."]
    positions = [body.find(marker) for marker in markers]
    assert all(p >= 0 for p in positions), "the six numbered steps must be present"
    assert positions == sorted(positions), "the numbered steps must appear in order"


def test_it_names_the_distractor_step_as_the_difficulty_lever():
    """Section 6 step 2 is explicit that the distractor set, not hop_depth, is
    what sets difficulty. A skill that treats hop_depth as the lever produces
    deep-but-trivial tasks.
    """
    body = load(SKILL).body.lower()
    assert "distractor" in body
    assert "hop_depth" in load(SKILL).body


def test_it_requires_the_discriminating_fact_to_be_copied_verbatim():
    body = load(SKILL).body
    assert "discriminating_fact" in body
    assert "verbatim" in body.lower()
