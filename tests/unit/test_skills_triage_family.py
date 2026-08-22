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


def _rule() -> skills.Skill:
    return _skill("rb-triage-rule")


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


# --- rb-triage-rule --------------------------------------------------------
#
# Task 12's fan-out member: one per slice, the pass that actually declines
# things. Most of the superseded monolithic rb-triage's material lands here,
# so these predicates are the closest kin to test_skills_triage.py's own.


def test_the_rule_pass_declares_its_exact_contract():
    """The brief's contract, verbatim: a member reads its own shard and the
    objective pass's ruling, never the catalogue or the plan directly -- the
    shard already carries `request` and `policy`."""
    skill = _rule()
    assert skill.contract["stage"] == "triage-rule"
    assert skill.contract["reads"] == ["slice_shard", "objective"]
    assert skill.contract["writes"] == ["disposition_part"]
    assert skill.contract["schemas"] == ["dispositions-part"]
    assert skill.contract["invokes"] == ["validate"]


def test_the_rule_pass_reads_only_its_own_shard():
    skill = _rule()
    assert skill.contract["reads"] == ["slice_shard", "objective"]
    inputs = skills.section_body(skill, "1. Inputs").lower()
    assert "sibling" in inputs or "another member" in inputs


def test_the_rule_pass_inverts_the_decline_everything_refusal():
    body = skills.section_body(_rule(), "5. Refusal conditions").lower()
    assert "write the part" in body
    assert "seal" in body  # names who owns the union judgment


def test_the_rule_pass_ties_provenance_to_the_near_duplicate_judgment():
    """A co-occurrence claim, not two independent mentions: both tokens
    appearing anywhere in Method, unlinked, would also be satisfied by two
    unrelated sentences that never actually tie provenance to the
    near_duplicate judgment -- measured true on this file's own second,
    unrelated `provenance` mention in Step 4."""
    body = _norm(skills.section_body(_rule(), "3. Method"))
    anchor = _first_index(body, ("provenance",))
    assert anchor != -1
    window = _window_after(body, anchor, radius=300)
    assert "near_duplicate" in window


def test_the_rule_pass_keeps_the_failing_trace_rule():
    body = skills.section_body(_rule(), "3. Method").lower()
    assert "failing trace" in body and "near-duplicate" in body


def test_the_rule_pass_names_all_three_digest_truncation_facts():
    body = skills.section_body(_rule(), "1. Inputs")
    for field in ("heuristics_fired", "keys_truncated", "skeleton_nodes_truncated"):
        assert field in body


def test_the_rule_pass_says_priority_is_within_the_slice():
    """A co-occurrence claim: the within-slice scoping language has to sit
    near `priority` itself, not merely appear somewhere in Output --
    `near_duplicate`'s own unrelated *in this slice* wording, in the
    reason_code table, would otherwise satisfy this with zero mention of
    priority's own scope."""
    body = _norm(skills.section_body(_rule(), "2. Output"))
    anchor = _first_index(body, ("priority",))
    assert anchor != -1
    window = _window_after(body, anchor, radius=300)
    assert "within" in window or "in this slice" in window or "in your slice" in window


def test_the_rule_pass_states_the_measured_failure_header():
    """The incident this whole family exists to prevent, and the reason this
    particular pass carries it in full: it is the one that does the
    declining. The numbers and the vanished-conversation detail have to
    survive together -- a reword that kept the numbers but dropped what was
    lost would still leave a reader with no idea why every candidate needs a
    reason, so this checks both halves of the same story rather than either
    alone."""
    body = _norm(_rule().body)
    assert "sixteen" in body and "thirteen" in body
    assert "conversation" in body and ("no longer exists" in body or "vanished" in body)


def test_the_rule_pass_gives_both_arguments_against_opening_a_candidate():
    """rb-triage's §1 carried forward: cost and comparability, both, plus the
    new point that the widths are comparable *in fact* now that the digest is
    clamped, not merely by assumption."""
    body = _norm(skills.section_body(_rule(), "1. Inputs"))
    assert "cost" in body
    assert "comparable" in body
    assert "clamp" in body and "fact" in body


def test_the_rule_pass_names_the_repeated_signal_warning():
    """Measured on a real 130-element trace capture: error_markers fired once
    and resolved through the value already under status, so the two firing
    together is one fact stated twice. `status` and `error_markers` must
    co-occur with the "one fact" conclusion, not merely both appear somewhere
    in Inputs -- a reword that named the two fields without ever saying they
    can double-count would still satisfy a bag-of-tokens check."""
    body = _norm(skills.section_body(_rule(), "1. Inputs"))
    anchor = _first_index(body, ("error_markers",))
    assert anchor != -1
    window = _window_around(body, anchor, radius=400)
    assert "status" in window
    assert "one fact" in window or "stated twice" in window or "twice" in window


def test_the_rule_pass_lists_all_eight_reason_codes():
    body = skills.section_body(_rule(), "2. Output")
    for code in (
        "off_objective",
        "out_of_scope",
        "near_duplicate",
        "superseded",
        "implementation_detail",
        "no_evidence_value",
        "digest_insufficient",
        "needs_projection",
    ):
        assert code in body


def test_the_rule_pass_states_authority_is_triage_on_every_disposition():
    """A co-occurrence claim: `authority` and the literal value `"triage"`
    have to sit close enough together to be the same statement, not just both
    be present somewhere in Output."""
    body = skills.section_body(_rule(), "2. Output")
    index = body.find("authority")
    assert index != -1
    window = _window_after(body, index, radius=200)
    assert "triage" in window


def test_the_rule_pass_keeps_the_digest_insufficient_refusal_rule():
    """§5 unchanged in force: a candidate you cannot judge is a decline, not a
    refusal, and the deficiency it obliges is rb-triage-audit's to write from
    this pass's own deficiency_notes."""
    body = _norm(skills.section_body(_rule(), "5. Refusal conditions"))
    assert "digest_insufficient" in body
    assert "rb-triage-audit" in body
    assert "deficiency_notes" in body
    assert "check-refs" in body and "reject" in body


def test_the_rule_pass_admits_conflicts_rather_than_resolving_them():
    """§3 Step 4's judgment rule: a trace/spec conflict is worth admitting,
    not resolving -- rb-reconcile is better placed to (the real stage on
    this branch; the sibling staged-reconcile branch's rb-reconcile-contradict
    does not exist here). The anchor here is the conflict language itself,
    and the resolution-naming text has to follow it, not merely appear
    somewhere else in Method."""
    body = _norm(skills.section_body(_rule(), "3. Method"))
    anchor = _first_index(body, ("conflict", "behavioural evidence"))
    assert anchor != -1
    window = _window_around(body, anchor, radius=400)
    assert "rb-reconcile" in window
    assert "rb-reconcile-contradict" not in window


def test_the_rule_pass_scopes_the_provenance_note_to_a_split_group():
    """New-to-this-pass item 2: where provenance shows a group was split
    across slices, the reason has to say so rather than imply a comparison
    against the whole group. `other_slices` (or "split") has to sit near the
    provenance/near_duplicate claim, not merely appear in the section."""
    body = _norm(skills.section_body(_rule(), "3. Method"))
    anchor = _first_index(body, ("provenance",))
    assert anchor != -1
    window = _window_around(body, anchor, radius=500)
    assert "split" in window or "other_slices" in window
