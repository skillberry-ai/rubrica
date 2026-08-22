"""Prose predicates for the staged-triage prompt passes, each scoped to the
section that owns the rule -- rb-triage.md's convention (see
test_skills_triage.py), carried forward for the family Task 11 begins.

Roughly nineteen assertions in this repo were measured satisfiable by
unrelated content before that convention existed. Task 11's brief measured
each of these in both directions; a predicate nobody has watched fail is not
a guard.
"""

from __future__ import annotations

import re

from rubrica import skills


def _skill(name: str) -> skills.Skill:
    # skills_dir() re-read on every call, not cached at import time, so a test
    # run under RUBRICA_SKILLS_DIR=/tmp/skills-probe (the both-direction
    # measurement this task's brief requires) reads that copy rather than the
    # installed one.
    return skills.load(skills.skills_dir() / name / "SKILL.md")


def _objective() -> skills.Skill:
    return _skill("rb-triage-objective")


def _norm(text: str) -> str:
    """Whitespace-normalised, so a reflow does not break a phrase pin.

    399dba5 fixed exactly this for rb-triage's own tests: two phrase pins
    broke on an innocuous reformat.
    """
    return re.sub(r"\s+", " ", text.lower())


def test_the_objective_pass_declares_its_exact_contract():
    """The brief's contract, verbatim: slices and catalogue, never the
    shards or a per-slice dispositions part."""
    skill = _objective()
    assert skill.contract["stage"] == "triage-objective"
    assert skill.contract["reads"] == ["slices", "catalogue"]
    assert skill.contract["writes"] == ["objective"]
    assert skill.contract["schemas"] == ["objective"]
    assert skill.contract["invokes"] == ["validate"]


def test_the_objective_pass_forbids_reading_candidate_digests():
    body = _norm(skills.section_body(_objective(), "1. Inputs"))
    assert "digest" in body and ("not" in body or "never" in body)


def test_the_objective_pass_admits_that_a_map_is_thinner_than_the_digests():
    """Spec section 12 item 3's honest limitation: `supported` is ruled from
    labels and counts, not from a reading of what those counts summarize."""
    body = _norm(skills.section_body(_objective(), "1. Inputs"))
    assert "supported" in body and ("thinner" in body or "wrong" in body)


def test_the_objective_pass_reads_request_before_the_corpus_map():
    """rb-triage's Step 1, carried in force: a reading that starts from the
    candidates and arrives at a scope rationalises the objective to fit it."""
    body = _norm(skills.section_body(_objective(), "3. Method"))
    assert "step 1" in body
    start = body.index("step 1")
    window = body[start : start + 400]
    assert "request" in window and "first" in window


def test_the_objective_pass_states_which_bytes_weight_sums():
    """The ruling task 11's brief settles: weight.bytes sums each evidence
    candidate's own catalogue `bytes` field (source file size), never a
    slice's or a serialized row's size -- a saturating metric cannot express
    weight once triage-slices' 128-node skeleton clamp caps row size."""
    body = _norm(skills.section_body(_objective(), "2. Output"))
    assert "weight.bytes" in body or "weight" in body
    assert "bytes" in body
    assert "row" in body or "serialized" in body
    assert "saturat" in body


def test_the_objective_pass_states_that_it_may_not_act_on_its_recommendation():
    body = _norm(skills.section_body(_objective(), "2. Output"))
    assert "recommended_objective" in body
    assert "may not act" in body or "not act on" in body


def test_the_objective_pass_explains_predicted_surface_count_is_a_prediction():
    """New in this pass, and the reason it runs separately from the members
    that read digests: a divergence is a fact about the map's adequacy, not
    an error either reading made."""
    body = _norm(skills.section_body(_objective(), "2. Output"))
    assert "predicted_surface_count" in body
    assert "prediction" in body
    assert "not" in body and "error" in body


def test_the_objective_pass_refuses_on_an_absent_objective_and_not_on_an_unsupported_one():
    body = _norm(skills.section_body(_objective(), "5. Refusal conditions"))
    assert "absent" in body and "scope_note" in body
    assert "do not refuse" in body and "unsupported" in body


def test_the_objective_pass_refuses_before_the_fanout_is_dispatched():
    """Refusing here is the point of running first -- the same authority the
    monolithic rb-triage had, narrowed to this pass's own slice of it."""
    body = _norm(skills.section_body(_objective(), "5. Refusal conditions"))
    assert "fan-out" in body or "fan out" in body


def test_the_objective_pass_forbids_acting_on_a_recommended_objective_in_invariants():
    body = _norm(skills.section_body(_objective(), "4. Invariants"))
    assert "recommended_objective" in body
    assert "recommendation" in body


def test_the_objective_pass_names_the_audit_pass_for_a_mechanical_exclusion_concern():
    """rb-triage's `excluded` instruction, carried: a mechanical exclusion you
    believe was wrong is a fact worth recording. This pass writes no
    deficiencies[] (not a field objective-0.1.json has), so it names
    rb-triage-audit as the pass that turns the concern into a real one."""
    body = _norm(_objective().body)
    assert "excluded" in body
    assert "rb-triage-audit" in body
