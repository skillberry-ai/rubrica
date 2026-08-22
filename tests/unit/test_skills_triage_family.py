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


def _first_index(body: str, tokens: tuple[str, ...]) -> int:
    """The lowest index at which any of `tokens` occurs, or -1 if none do."""
    indices = [body.find(t) for t in tokens]
    indices = [i for i in indices if i != -1]
    return min(indices) if indices else -1


def _window_around(body: str, index: int, radius: int = 250) -> str:
    """The text around `index`, sized like the window
    test_the_objective_pass_reads_request_before_the_corpus_map already
    uses below. A claim is two things holding *together* -- an ordering word
    next to a fan-out word -- not two tokens each satisfied somewhere in a
    section that never actually joins them."""
    return body[max(0, index - radius) : index + radius]


def _window_after(body: str, index: int, radius: int = 250) -> str:
    """The text starting at `index`, forward only.

    A symmetric window around `recommended_objective` inside a numbered
    Invariants list reached backward into the *previous* item's own
    "never" -- item 2's "never over a slice's ... serialized size" -- and
    passed a probe that had actually deleted item 3's prohibition. In both
    places this predicate reads, the field name is stated first and the
    prohibition follows it in the same sentence or the next one, so a
    forward-only window states the claim this test actually means: a
    prohibition that follows naming the field, not a prohibition word
    floating anywhere nearby.
    """
    return body[index : index + radius]


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
    """A prohibition claim: `recommended_objective` and a prohibition word
    must occur *together*, not as two tokens each satisfiable anywhere in
    the section. A phrase pin on the exact wording ("may not act on") once
    sat here and failed a good-faith reword ("acting on that recommendation
    yourself is not permitted") that keeps the same meaning in different
    words -- the reword was the honest one; the pin was what was wrong, and
    fixing it means widening the accepted prohibition vocabulary and
    checking proximity instead of an exact phrase."""
    body = _norm(skills.section_body(_objective(), "2. Output"))
    index = body.find("recommended_objective")
    assert index != -1
    window = _window_after(body, index)
    prohibition = ("may not", "must not", "never", "not permitted", "is not yours")
    assert any(p in window for p in prohibition)


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
    """An ordering claim, not a mention: refusal has to land *before* the
    fan-out is dispatched, so an ordering word must co-occur with a
    fan-out/dispatch word. Mentioning the fan-out alone would also be
    satisfied by prose that describes the fan-out re-checking this later --
    the opposite ordering -- which is why a bare presence check used to pass
    here without ever reading which way the sentence pointed."""
    body = _norm(skills.section_body(_objective(), "5. Refusal conditions"))
    anchor = _first_index(body, ("fan-out", "fan out", "dispatch", "members"))
    assert anchor != -1, "no mention of the fan-out or its dispatch at all"
    window = _window_around(body, anchor)
    assert any(o in window for o in ("before", "ahead of", "prior to"))


def test_the_objective_pass_forbids_acting_on_a_recommended_objective_in_invariants():
    """A prohibition claim, same shape as the Output-section one above:
    `recommended_objective` and a prohibition word have to sit together.
    Checking only that both words appear anywhere in Invariants is close to
    tautological, since the field's own name contains "recommend" -- a
    reword keeping the field name while dropping the prohibition ("reflects
    one path you could take") would still have passed the old assertion."""
    body = _norm(skills.section_body(_objective(), "4. Invariants"))
    index = body.find("recommended_objective")
    assert index != -1
    window = _window_after(body, index)
    prohibition = ("may not", "must not", "never", "not permitted", "is not yours")
    assert any(p in window for p in prohibition)


def test_the_objective_pass_names_the_audit_pass_in_inputs():
    """rb-triage's `excluded` instruction, carried into Inputs: a mechanical
    exclusion you believe was wrong is a fact worth recording. This pass
    writes no deficiencies[] (not a field objective-0.1.json has), so it
    names rb-triage-audit as the pass that turns the concern into a real
    one. Scoped to Inputs, not the whole file, so a reword that dropped this
    from Inputs specifically -- while the Method section still carried its
    own mention -- would still be caught here rather than passing on the
    other section's coincidental survival."""
    body = _norm(skills.section_body(_objective(), "1. Inputs"))
    assert "excluded" in body
    assert "rb-triage-audit" in body


def test_the_objective_pass_names_the_audit_pass_in_method():
    """The same instruction restated as Method's own step: name
    rb-triage-audit as the pass that turns a real gap into a recorded
    deficiency, once the slices have reported what they actually saw --
    never a decision this pass makes in its place. Scoped to Method for the
    same reason the Inputs test above is scoped to Inputs."""
    body = _norm(skills.section_body(_objective(), "3. Method"))
    assert "excluded" in body
    assert "rb-triage-audit" in body
