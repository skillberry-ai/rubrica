"""Prose predicates for the staged-triage prompt passes, each scoped to the
section that owns the rule -- the convention rb-triage's own test module
established, carried forward for the family Task 11 begins. That module went
with the monolithic skill in Task 14; every claim of its that no predicate here
already covered was carried into this file, each re-measured in both directions
against its new target pass. The rest were either already
covered by a predicate below or had been taken over by code -- `seal.py` and
`refs.py` now rule mechanically on the one-disposition-per-candidate
invariant its Invariants predicate used to pin in prose.

Roughly nineteen assertions in this repo were measured satisfiable by
unrelated content before that convention existed. Task 11's brief measured
each of these in both directions; a predicate nobody has watched fail is not
a guard.

**Window margin convention.** Every `_window_around`/`_window_after` call in
this module carries a `radius` sized to at least 2x the measured
anchor-to-token distance for whichever required token sits farthest from the
anchor (the nearer of an OR-group's alternatives, the farther of an
AND-group's requirements). A tighter window is a length pin in disguise: it
passes today against the real prose, but an honest, meaning-preserving
lengthening anywhere between the anchor and the token -- a clause added, a
sentence reworded longer -- pushes the token outside the window and fails
the test against a *correct* skill. Deletion-only probing (confirming the
predicate goes red when the claim is removed) cannot detect this, because a
tight-but-adequate window and a tight-and-fragile one both pass that probe
identically; only measuring the actual distance and comparing it to the
radius reveals the fragility. Three windows in this file were found below
the floor by that measurement alone, well after their own deletion probes
had already passed -- see this file's git history for the fix. When adding
a new windowed predicate, measure the anchor-to-token distance with the
same method (an ad hoc script against `skills.section_body`, not a guess)
and size the radius from it; do not pick a round number first and hope.
"""

from __future__ import annotations

import re

import pytest

from rubrica import digest, skills


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


def _audit() -> skills.Skill:
    return _skill("rb-triage-audit")


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


def _occurrences(body: str, token: str) -> list[int]:
    """Every index at which `token` occurs, not merely the first.

    `body.find(token)` anchors a co-occurrence claim on the *first* mention,
    which makes it fail when an unrelated, correct edit introduces an earlier
    one. Measured: adding a paragraph that names `authority` as one of the four
    required disposition keys moved that anchor off the sentence stating
    `authority: "triage"` and turned three predicates in this module red
    against prose that still carried every claim they test. That is the
    length-pin failure mode the module docstring describes, wearing a
    different hat -- the claim was never "the first mention of the token
    carries it", it was "the section states this somewhere as one statement".

    Returning every index lets a predicate assert exactly that, at the same
    radius, without admitting a wider window. It does not weaken the guard:
    deleting the claim still leaves no occurrence that satisfies it, which is
    the direction each caller below re-measured.
    """
    return [m.start() for m in re.finditer(re.escape(token), body)]


def test_the_objective_pass_declares_its_exact_contract():
    """The brief's contract, verbatim: the plan alone -- never the catalogue,
    the shards, or a per-slice dispositions part. The catalogue left this list
    when 00-slices.json started carrying the facts this pass needs: reading
    472,799 bytes for the ~21KB it used was the residual half of issue #3.

    That the block is bounded by how many candidates a run admitted rather than
    by how large they are is a **code** fact, readable in slices.py and needing
    no measurement: candidate_bytes is one integer per candidate id, excluded is
    capped at MAX_EXCLUDED_ENTRY_BYTES, and request and policy are fixed-size
    verbatim copies.

    What two runs of the same corpus **observed** is narrower and is a
    controlled comparison only because the candidate count was the same 443 in
    both. Against that fixed count the catalogue grew 472,799 -> 480,399 bytes,
    while the block's four components came out byte-identical (candidate_bytes
    18,204, excluded 1,062, policy 349, request 303 in each) and its in-file
    share moved 5 bytes, 22,134 -> 22,129. Without the count held fixed those
    two points would support "the candidate set did not change" exactly as well,
    which is why the count is named here and not left implied."""
    skill = _objective()
    assert skill.contract["stage"] == "triage-objective"
    assert skill.contract["reads"] == ["slices"]
    assert skill.contract["writes"] == ["objective"]
    assert skill.contract["schemas"] == ["objective"]
    assert skill.contract["invokes"] == ["validate"]


def test_the_objective_pass_forbids_reading_a_shard():
    """The pass's bounding constraint, on the artifact that now holds the digests.

    `00-slices.json` carries no candidate digest at all, so the old form of
    this predicate -- "digest" and a prohibition word both somewhere in the
    section -- no longer even has a subject. What can still make this pass
    unbounded is a shard: the shards hold every candidate's full digest between
    them and come to within a percent of the catalogue's own size -- seven
    shards, 470,455 bytes against 472,799, on the tau2 catalogue this design
    was measured against, and eight shards, 479,204 against 480,399, on a
    re-run of the same corpus later. The counts and the absolutes are
    checkout-specific; the near-equality is what both measurements say.

    Windowed rather than section-wide, because the unwindowed form of this
    predicate was measured vacuous: inverting the skill to grant the opposite
    permission left it green.

    Measured unbounded rather than clipped to the window: the section holds
    exactly three prohibition words, all of them `never`, and its four `shard`
    mentions sit 28, 123, 176 and 743 characters from the nearest one. The
    first three all resolve to the *same* `never` -- the one inside the
    prohibition sentence itself -- so this is an OR over mentions, and the
    "Window margin convention" in this module's own docstring sizes a radius
    from the nearer of an OR-group's alternatives (a line number would drift;
    the heading will not): the governing distance is 28, not 176. That is
    load-bearing rather than tidier bookkeeping, because reading 176 as
    governing would put the 2x floor at 352 and oblige *raising* the radius
    this predicate was actually measured at. The fourth mention ("firming up a
    surface judgment by opening a shard") is 743 away and outside the window on
    purpose -- it states the consequence, not the prohibition.

    **radius=300 is a value inside a measured band, not a tuned number, and the
    edge that can break is the upper one.** Swept in both directions: green on
    the shipped prose from radius 33 up, and green on the *inverted* prose --
    that is, vacuous -- from radius 748 up, where the fourth mention reaches
    the section's next `never`. The band is [33, 747]; 300 sits 9.1x above the
    lower edge and 2.5x below vacuity. **Do not widen it.** Every failure this
    predicate has had has been a ceiling failure: the unwindowed form was
    vacuous, and that fourth mention sat 220 away rather than 743 until the
    sentence above it was reworded from "never by how large they are" to
    "rather than by how large they are" -- at 220 the inversion probe passed
    for free at this very radius. The floor, by contrast, has never broken and
    for the surviving alternative barely can: `shard` and `never` are 28
    characters apart inside one sentence.

    **The vocabulary is matched on word boundaries, and that is load-bearing
    rather than fastidious.** `"never" in window` is also satisfied by
    "whe-never": an inversion reading "a shard under `00-slices/` is yours to
    open **whenever** you like" -- prose granting the exact permission this
    predicate exists to forbid -- put that substring 42 characters from the
    first mention and passed at radius=300. What that defeats is not the
    predicate directly but the *inversion probe*, which is the only evidence
    this predicate has: a probe that goes green against permission-granting
    prose measures nothing. So the measurement is three-directional, and
    direction 3 is an inversion whose only prohibition-looking token is a
    substring. Switching to `\\b...\\b` changed no distance and no band edge --
    28/123/176/743 and [33, 747] are the same under both matchers, because none
    of the three real hits was ever a substring artefact.
    """
    body = _norm(skills.section_body(_objective(), "1. Inputs"))
    indices = _occurrences(body, "shard")
    assert indices, "the Inputs section never names a shard"
    # Word-boundary rather than substring, for the reason direction 3 records:
    # `"never" in window` is also satisfied by "whenever", which is how
    # permission-granting prose passes a prohibition check.
    prohibition = re.compile(r"\b(?:never|not yours|do not)\b")
    near_prohibition = any(
        prohibition.search(_window_around(body, at, radius=300)) for at in indices
    )
    assert near_prohibition, "no `shard` mention sits near a prohibition"


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


def test_the_objective_pass_names_objective_reviews_three_required_keys():
    """`surfaces` was the sibling of issue #1's defect, in the same family.

    Found by the sweep that issue asked for -- each skill's prose against the
    keys its declared schemas `require`. `objective-0.1.json` requires
    `objective_review` to carry `declared_objective`, `supported` and
    `surfaces`; this pass names the first two and, before the fix, referred to
    the third only as prose ("the surfaces the corpus map shows", "group the
    map's groups into surfaces"). Nothing it reads carries the shape either:
    `00-slices.json` is now this pass's only input and holds no
    `objective_review` to copy from, so the key was one a member had to invent
    -- the same position the dispositions pass was in when three dispatches
    invented `verdict`.

    The reader/writer asymmetry is what makes this worth its own predicate:
    `rb-triage-rule` names ``00-objective.json``'s `surfaces` in key position
    because it *reads* the file, while the pass that *writes* it did not. A
    sweep over the family catches that; reading either skill alone does not.

    Anchored on the key-position mention of `surfaces` rather than on
    `objective_review`, because the anchor is the thing under test. radius=550
    against a measured 246-character distance to the farthest required token
    (`supported`, which precedes the anchor) -- margin ~2.2x, and symmetric
    because two of the three keys sit on either side of it.
    """
    body = _norm(skills.section_body(_objective(), "2. Output"))
    match = re.search(r'`surfaces`|`surfaces:|"surfaces"', body)
    assert match is not None, "the section never names the surfaces key in key position"
    window = _window_around(body, match.start(), radius=550)
    assert "declared_objective" in window
    assert "supported" in window


def test_the_objective_pass_states_which_bytes_weight_sums():
    """The ruling task 11's brief settles, restated onto the field that now
    carries the number: weight.bytes sums each evidence candidate's entry in
    the plan's `catalogue_facts.candidate_bytes` (the source file's size),
    never `slices[].bytes` or any other serialized row's size -- a saturating
    metric cannot express weight once the digest's 128-node skeleton clamp caps
    row size."""
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
    indices = _occurrences(body, "recommended_objective")
    assert indices, "the section never names recommended_objective"
    prohibition = ("may not", "must not", "never", "not permitted", "is not yours")
    assert any(p in _window_after(body, index) for index in indices for p in prohibition), (
        "no mention of recommended_objective is followed by a prohibition"
    )


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
    one path you could take") would still have passed the old assertion.

    radius=300 against a measured anchor-to-token distance of 142 chars to
    the nearest prohibition word ("never") -- margin ~2.1x, per this
    module's floor (see the module docstring)."""
    body = _norm(skills.section_body(_objective(), "4. Invariants"))
    index = body.find("recommended_objective")
    assert index != -1
    window = _window_after(body, index, radius=300)
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


def test_the_rule_pass_frames_all_three_truncation_flags_as_digest_facts():
    """Carried from rb-triage's own module (two predicates there, one here):
    naming the three flags is not the claim -- reading them as facts about the
    *digest* rather than about the candidate is. A pass that treats a missing
    `heuristics_fired` entry as evidence the candidate has no errors, or a
    capped key list as evidence the object is thin, declines exactly the
    candidates the flags exist to protect.

    Anchored on the framing phrase and requiring all three names inside one
    window, rather than each name near its own framing phrase. Measured
    reason: `fact about the digest` occurs three times in this section, and
    the first two are the per-flag paragraphs, each of which names only one or
    two of the three -- so a per-name check would pass on a coincidental
    neighbour while the summary claim that binds all three was gone. Only the
    summary window satisfies this, which is what makes it discriminating.

    radius=200 against a measured 71-character worst-case distance from the
    framing phrase to the farthest of the three names -- margin ~2.8x, per
    this module's floor (see the module docstring).

    `digest.TRACE_HEURISTICS` comes along from the same source module: the
    prose is only worth pinning while the code's list is non-empty, and
    enumerating its members in prose would pin digest.py's internals to a
    document.
    """
    assert digest.TRACE_HEURISTICS
    body = _norm(skills.section_body(_rule(), "1. Inputs"))
    names = ("heuristics_fired", "keys_truncated", "skeleton_nodes_truncated")
    framings = [m.start() for m in re.finditer(r"facts? about the digest", body)]
    assert framings, "the section never frames a flag as a fact about the digest"
    assert any(all(n in _window_around(body, at, radius=200) for n in names) for at in framings), (
        "no single digest-fact claim covers all three truncation flags"
    )


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
    clamped, not merely by assumption.

    The clamp/fact conjunct was measured vacuous: `fact` occurs nine times
    and `clamp` twice across this section, so a bare `"clamp" in body and
    "fact" in body` check still passed with the §10.1 sentence tying them
    together deleted -- both tokens survived via the unrelated
    `skeleton_nodes_truncated` paragraph a few lines below, which uses
    "fact" three times and "clamped" once of its own accord. Anchored on
    the claim's own wording ("in fact" / "comparable") and windowed forward
    to where "clamp" actually appears (374 characters away in the real
    prose) instead.

    radius=800 against that measured 374-character distance -- margin
    ~2.1x. The original radius=450 (margin ~1.2x) was demonstrated to break
    against a correct skill under an honest 87-character meaning-preserving
    lengthening of the intervening prose; widened here per this module's 2x
    floor (see the module docstring) once this task's own concurrent edits
    to this file were done."""
    body = _norm(skills.section_body(_rule(), "1. Inputs"))
    assert "cost" in body
    assert "comparable" in body
    anchor = _first_index(body, ("in fact", "comparable"))
    assert anchor != -1
    window = _window_after(body, anchor, radius=800)
    assert "clamp" in window


def test_the_rule_pass_names_the_repeated_signal_warning():
    """Measured on a real 130-element trace capture: error_markers fired once
    and resolved through the value already under status, so the two firing
    together is one fact stated twice. `status` and `error_markers` must
    co-occur with the "one fact" conclusion, not merely both appear somewhere
    in Inputs -- a reword that named the two fields without ever saying they
    can double-count would still satisfy a bag-of-tokens check.

    radius=650 against measured distances of 121 ("status") and 289 (the
    nearest of the "one fact" / "stated twice" / "twice" alternatives) --
    the controlling margin is ~2.2x on the 289-character token, per this
    module's floor (see the module docstring)."""
    body = _norm(skills.section_body(_rule(), "1. Inputs"))
    anchor = _first_index(body, ("error_markers",))
    assert anchor != -1
    window = _window_around(body, anchor, radius=650)
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
    indices = _occurrences(body, "authority")
    assert indices, "the section never names authority"
    assert any("triage" in _window_after(body, index, radius=200) for index in indices), (
        'no mention of authority is followed by the value "triage"'
    )


def test_the_rule_pass_names_the_disposition_key_itself():
    """The key holding `admit`/`decline` has to be *named*, not just described.

    Issue #1: the monolithic stage's prose named `candidate_id`, `authority`,
    `reason`, `reason_code` and `priority` and described this field at length
    while never once saying what to call it. Three consecutive dispatches at
    defaults invented `verdict` for it -- not a stale word copied out of the
    prose, an invention two dispatches arrived at independently. Every entry
    then failed layer 1, and because `brief.py:169,184` key off `disposition`,
    `gate-brief --gate 0` rendered zero admits and zero declines at exit 0: a
    human handed an empty selection presented as a clean one. The defect
    survived the split into this family, because the paragraph moved verbatim.

    **The bare word cannot be the predicate.** "Every disposition also carries
    `authority`" is prose *about* the field and satisfies any `"disposition" in
    body` check while leaving the key unnamed -- which is precisely the state
    that shipped. So this asserts a *key-position* mention: backticked alone,
    backticked with its colon, or quoted. `dispositions[]` and
    `00-dispositions/<slice_id>.json` do not satisfy it (both are the plural),
    and neither does any amount of discussion.

    Co-occurrence with both literal values is what makes it one statement
    rather than two: a section naming the key but only ever showing `admit`
    has not told a member what a decline looks like.

    radius=300 against a measured 131-character distance from the key-position
    anchor to the farther required token (`"decline"`) -- margin ~2.3x, per
    this module's floor (see the module docstring).
    """
    body = _norm(skills.section_body(_rule(), "2. Output"))
    match = re.search(r'`disposition`|`disposition:|"disposition"', body)
    assert match is not None, "the section never names the key in key position"
    window = _window_after(body, match.start(), radius=300)
    assert '"admit"' in window
    assert '"decline"' in window


def test_the_rule_pass_names_all_four_required_disposition_keys():
    """The schema's `required` list, stated in the section that writes it.

    `triage-0.1.json#/$defs/disposition` requires exactly `candidate_id`,
    `disposition`, `reason` and `authority`, and is `additionalProperties:
    false` -- so a synonym for any of the four is a hard validation failure,
    never a near miss the seal could repair. The sibling predicate above pins
    the one key that was missing; this one pins the set, so that the next key
    to go unnamed fails here rather than in a dispatch.

    Deliberately not a window: these four are a *set* the section must state,
    not a claim two tokens have to hold jointly, and the schema is the
    authority for the list rather than any phrasing of it.
    """
    body = _norm(skills.section_body(_rule(), "2. Output"))
    for key in ("candidate_id", "disposition", "reason", "authority"):
        assert re.search(rf"`{key}`|`{key}:|\"{key}\"", body), f"{key} is never named as a key"


def test_the_rule_pass_names_who_writes_the_human_authority():
    """Carried from rb-triage's own module (its `authority` and
    human-authority predicates, which this one predicate replaces). The
    sibling test above pins that this pass writes `authority: "triage"`; what
    that leaves unpinned is the other enum value. `triage-0.1.json` admits
    exactly two, and a pass that never learns where `"human"` comes from has
    no reason not to use it for a candidate it feels strongly about -- which
    would forge a gate-0 admission inside the record the gate reads.

    `adopt-projection` is the token that cannot be paraphrased away: it is a
    CLI subcommand name, and the only thing it does is append an admit to an
    existing record. A section naming it beside `authority` and `"human"` has
    necessarily identified a writer other than this pass.

    The gate is matched as `gate[ -]0` rather than as the phrase "gate-0
    override", after measuring that pin fail the mirror direction: the reword
    "what a person overriding you at gate 0 writes" carries the identical
    claim and turned the phrase pin red. The hyphen alternation is needed in
    both directions -- the live prose writes `gate-0`, an ordinary reword
    writes `gate 0`, and neither spelling is a substring of the other.

    radius=400 against a measured 161-character distance from `authority` to
    the farthest required token (`adopt-projection`) -- margin ~2.5x, per this
    module's floor (see the module docstring).
    """
    body = _norm(skills.section_body(_rule(), "2. Output"))
    indices = _occurrences(body, "authority")
    assert indices, "the section never names authority"

    def states_the_other_writer(index: int) -> bool:
        window = _window_after(body, index, radius=400)
        return (
            '"human"' in window
            and re.search(r"gate[ -]0", window) is not None
            and "adopt-projection" in window
        )

    assert any(states_the_other_writer(i) for i in indices), (
        "no mention of authority is followed by the other writer of the human value"
    )


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
    somewhere else in Method.

    radius=550 against a measured 235-character distance to "rb-reconcile"
    -- margin ~2.3x, per this module's floor (see the module docstring).
    `rb-reconcile-contradict` does not occur anywhere in this file, so
    widening this window carries no risk of the negative assertion below
    ever tripping."""
    body = _norm(skills.section_body(_rule(), "3. Method"))
    anchor = _first_index(body, ("conflict", "behavioural evidence"))
    assert anchor != -1
    window = _window_around(body, anchor, radius=550)
    assert "rb-reconcile" in window
    assert "rb-reconcile-contradict" not in window


def test_the_rule_pass_scopes_the_provenance_note_to_a_split_group():
    """New-to-this-pass item 2: where provenance shows a group was split
    across slices, the reason has to say so rather than imply a comparison
    against the whole group. `other_slices` (or "split") has to sit near the
    provenance/near_duplicate claim, not merely appear in the section.

    radius=650 against a measured 298-character distance to the nearer of
    "split" / "other_slices" -- margin ~2.2x, per this module's floor (see
    the module docstring)."""
    body = _norm(skills.section_body(_rule(), "3. Method"))
    anchor = _first_index(body, ("provenance",))
    assert anchor != -1
    window = _window_around(body, anchor, radius=650)
    assert "split" in window or "other_slices" in window


# --- rb-triage-audit --------------------------------------------------------
#
# Task 13's self-audit: the last of the staged-triage prompt passes, reading
# every rb-triage-rule part plus 00-objective.json and writing what the
# admitted set cannot cover -- deficiencies[] and projections[] in
# 00-audit.json. It never reads a candidate or a shard; the four tests below
# are the brief's own Step 1, verbatim in substance.


def test_the_audit_pass_declares_its_exact_contract():
    """The brief's contract, verbatim: the parts and the objective pass's
    ruling, never a shard, never the candidates, never 00-slices.json."""
    skill = _audit()
    assert skill.contract["stage"] == "triage-audit"
    assert skill.contract["reads"] == ["objective", "dispositions_dir"]
    assert skill.contract["writes"] == ["audit"]
    assert skill.contract["schemas"] == ["audit"]
    assert skill.contract["invokes"] == ["validate", "check-refs"]


def test_the_audit_pass_reads_the_parts_and_not_the_candidates():
    skill = _audit()
    assert skill.contract["reads"] == ["objective", "dispositions_dir"]


def test_the_audit_pass_asks_the_result_shape_question_directly():
    body = skills.section_body(_audit(), "3. Method").lower()
    assert "result shape" in body or "what it returns" in body
    assert "capabilit" in body


def test_the_audit_pass_writes_both_blocks_even_when_empty():
    body = skills.section_body(_audit(), "2. Output").lower()
    assert "empty" in body and "still" in body
    assert "is also a claim" in body or "is itself a claim" in body


def test_the_audit_pass_owns_the_members_obligations():
    body = skills.section_body(_audit(), "4. Invariants").lower()
    assert "digest_insufficient" in body and "needs_projection" in body


def test_the_audit_pass_explains_why_the_return_question_is_semantic():
    """The design spec's §4.2 reasoning, carried in force: code answering
    "does the admitted set declare what a capability returns" would be the
    coverage-denominator mistake rb-reconcile was already designed to avoid.
    Anchored on "semantic" itself and windowed forward, since the intro's
    surrounding prose is dense with unrelated words ("code", "record") that
    would satisfy a bag-of-tokens check without ever tying them to this
    specific claim.

    radius=500 against measured distances of 153 ("code") and 214 ("coverage
    denominator" -- the hyphenated spelling does not occur in this file at
    all) -- the controlling margin is ~2.3x on the 214-character token, per
    this module's floor (see the module docstring)."""
    body = _norm(_audit().body)
    anchor = _first_index(body, ("semantic",))
    assert anchor != -1
    window = _window_after(body, anchor, radius=500)
    assert "code" in window
    assert "coverage-denominator" in window or "coverage denominator" in window


def test_the_audit_pass_states_the_measured_failure_header():
    """The incident every pass in this family carries, restated here because
    this pass is the one whose whole existence is the fix for it: the
    deficiency that was never written down. Both halves -- the numbers and
    the reason the information was unrecoverable -- have to survive
    together, the same shape test_the_rule_pass_states_the_measured_failure_
    header already holds rb-triage-rule to."""
    body = _norm(_audit().body)
    assert "sixteen" in body and "thirteen" in body
    assert "deficienc" in body


def test_the_audit_pass_says_it_mints_the_deficiency_id_not_the_members():
    """A co-occurrence claim: `deficiency_notes` (the raw material) and
    `deficiency_id` (what only this pass mints) must sit together with a
    statement of who does the minting, not merely both be mentioned
    somewhere in Output -- a reword that dropped the division of labour
    while keeping both field names would still satisfy a bag-of-tokens
    check.

    radius=500 against measured distances of 190 ("deficiency_id") and 208
    (the nearer of "your job" / "nobody else") -- the controlling margin is
    ~2.4x on the 208-character token, per this module's floor (see the
    module docstring)."""
    body = _norm(skills.section_body(_audit(), "2. Output"))
    anchor = _first_index(body, ("deficiency_notes",))
    assert anchor != -1
    window = _window_after(body, anchor, radius=500)
    assert "deficiency_id" in window
    assert "your job" in window or "nobody else" in window


def test_the_audit_pass_lists_all_seven_projection_fields():
    """Each field has to appear as its own bulleted definition (`` - `field` ``),
    not merely as a bare token: `closes`, `sources`, `method` and `boundary`
    each recur once more in this section as an ordinary English word (a
    projection that "closes nothing", "two sources feed this block", an
    "extraction method", "the scope boundary" describing a *different*
    field) -- measured by deleting each field's actual bullet in a probe copy
    and finding the bare-token check still passed on that coincidental
    second mention. Anchoring on the markdown bullet syntax the list itself
    uses ties the check to the actual definition, not to the word."""
    body = skills.section_body(_audit(), "2. Output")
    for field in (
        "projection_id",
        "closes",
        "sources",
        "wanted",
        "method",
        "acceptance",
        "boundary",
    ):
        assert f"- `{field}`" in body


def test_the_audit_pass_says_where_a_source_digest_note_comes_from():
    """Carried from rb-triage's own module and strengthened, because the family
    changed what the field means.

    `triage-0.1.json` requires `digest_note` on every `projections[].sources`
    entry alongside `candidate_id`, and the predicate there was one token check
    over the whole Method section -- enough when the stage that wrote a projection
    was also the stage holding every digest. This pass holds none: its `reads` is
    the parts, never a candidate. So the prose owes two things, and a model given
    only the first would either omit a required key or invent a digest quote it
    never saw: the field exists, and its content comes from the member's own
    `reason` prose.

    Scoped to the `sources` bullet, forward only, at a radius measured rather than
    guessed: `candidate_id` sits +23 from the bullet and `digest_note` +44, but
    `reason` -- the token that carries the actual claim -- sits +238, so the floor
    is 476 and this uses 520 (2.2x). Nothing false can enter it: `reason`'s next
    occurrence in the section is +1817, and `candidate_id` occurs once in the
    section at all.
    """
    body = _norm(skills.section_body(_audit(), "2. Output"))
    index = body.find("- `sources`")
    assert index != -1, "the Output section has no `sources` bullet to read"
    window = _window_after(body, index, radius=520)
    assert "candidate_id" in window
    assert "digest_note" in window
    assert "`reason`" in window, (
        "the bullet never says where a pass that reads no digest gets the note from"
    )


def test_the_audit_pass_calls_unknown_confidence_honest():
    """A co-occurrence claim on `confidence`'s `unknown` value: the field
    name and the word "honest" have to sit close enough to be the same
    statement, not merely both appear somewhere in a section this dense with
    other prose."""
    body = _norm(skills.section_body(_audit(), "2. Output"))
    anchor = _first_index(body, ("confidence",))
    assert anchor != -1
    window = _window_after(body, anchor, radius=400)
    assert "unknown" in window and "honest" in window


def test_the_audit_pass_says_the_structural_fields_are_necessary_never_sufficient():
    """rb-triage's own acceptance-block ruling, carried forward: the four
    structural fields are checked mechanically, and `prose` is where
    *correct* actually gets defined. "necessary" and "sufficient" have to
    occur together with `prose`, not as two adjectives that happen to
    describe something else in the same section."""
    body = _norm(skills.section_body(_audit(), "2. Output"))
    anchor = _first_index(body, ("necessary",))
    assert anchor != -1
    window = _window_around(body, anchor, radius=300)
    assert "sufficient" in window
    assert "prose" in window


def test_the_audit_pass_routes_a_surface_shortfall_to_deficiencies_and_a_surplus_to_prose():
    """The design's §4.1 divergence, assigned to this pass by the brief: a
    lower observed count than predicted_surface_count is a loss and belongs
    in deficiencies[]; a higher one is not a loss, and audit-0.1.json has no
    field to hold it, so it is reported in prose instead. Both halves of the
    routing have to be anchored on the actual comparison, not merely present
    anywhere in Output -- a reword that kept "loss" and "prose" as
    unconnected asides would still pass a bag-of-tokens check.

    radius=2400 against measured distances of 390 ("loss") and 1097
    ("prose") -- the controlling margin is ~2.2x on the 1097-character
    token, per this module's floor (see the module docstring). The original
    radius=1200 (margin ~1.09x) was flagged in review as breaking against a
    correct skill under a plausible honest lengthening of the divergence
    paragraph; this widened window was re-verified in both directions --
    still red against a probe with the "prose" sentence's own claim
    removed, and still green against a ~150-character meaning-preserving
    insertion into the intervening prose."""
    body = _norm(skills.section_body(_audit(), "2. Output"))
    anchor = _first_index(body, ("predicted_surface_count",))
    assert anchor != -1
    window = _window_after(body, anchor, radius=2400)
    assert "loss" in window
    assert "prose" in window


def test_the_audit_pass_refuses_on_an_empty_dispositions_dir():
    body = _norm(skills.section_body(_audit(), "5. Refusal conditions"))
    anchor = _first_index(body, ("00-dispositions",))
    assert anchor != -1
    window = _window_after(body, anchor, radius=250)
    assert "missing" in window or "no parts" in window or "nothing" in window


def test_the_audit_pass_does_not_refuse_over_fan_out_completeness_it_cannot_see():
    """This pass's own honest limitation (its `reads` has no `slices` entry,
    so it cannot count how many parts should exist) has to be tied to an
    explicit "do not refuse" instruction, not merely mentioned as a fact --
    a reword that described the limitation without ever forbidding a refusal
    over it would leave a model free to refuse on exactly the case §5 exists
    to rule out.

    radius=500 against a measured 206-character distance to "check-refs"
    (the OR-alternative "slice" sits much closer, at 53, but the floor is
    sized off the tighter alternative rather than relying on the looser one
    to carry the margin) -- margin ~2.4x, per this module's floor (see the
    module docstring)."""
    body = _norm(skills.section_body(_audit(), "5. Refusal conditions"))
    assert "do not refuse" in body
    anchor = _first_index(body, ("do not refuse",))
    assert anchor != -1
    window = _window_after(body, anchor, radius=500)
    assert "slice" in window or "check-refs" in window


def test_the_audit_pass_does_not_refuse_when_the_absence_walk_finds_nothing():
    """A co-occurrence claim, not two independent mentions: `do not refuse`
    and `clean sweep` each appear in this section twice, from two different
    paragraphs -- the other `do not refuse` covers fan-out completeness, and
    the other `clean sweep` sits in the missing-`00-dispositions/` refusal,
    which is the opposite instruction (refuse there). An unwindowed
    `"do not refuse" in body and "clean sweep" in body` check is satisfied by
    that coincidence alone; anchoring on "turns up nothing," unique to the
    Step 4 sentence, ties both tokens to the one paragraph that actually
    states this rule.

    radius=350 against a measured 143-character distance to "clean sweep"
    (the closer of the two required tokens; "do not refuse" itself sits at
    38) -- margin ~2.4x, per this module's floor (see the module
    docstring)."""
    body = _norm(skills.section_body(_audit(), "5. Refusal conditions"))
    anchor = _first_index(body, ("turns up nothing",))
    assert anchor != -1
    window = _window_around(body, anchor, radius=350)
    assert "do not refuse" in window and "clean sweep" in window


# --- the whole family -------------------------------------------------------
#
# One rule that holds for all three passes rather than for any one of them.


@pytest.mark.parametrize(
    ("pass_name", "source"),
    [
        ("rb-triage-objective", "00-slices.json"),
        ("rb-triage-rule", "shard"),
        ("rb-triage-audit", "00-objective.json"),
    ],
)
def test_each_pass_states_its_schema_version_and_where_it_reads_run_id(pass_name, source):
    """Carried from rb-triage's own module, where it was one predicate over one
    Output section and is now three over three. Every part schema requires
    `schema_version` and `run_id` at the document root, so a pass that names
    neither writes a part that fails layer 1 on its first dispatch -- the
    primary output, not an edge case -- and one that invents a `run_id` writes
    a part the seal cannot match to the run it came from.

    Pinned through tokens that cannot be paraphrased: three field values a
    model has to write literally, and the artifact it has to read the id out
    of. The source predicate's own history is why the wording is not pinned --
    it began by also pinning `"never invent"`, and the meaning-preserving
    reword "do not make one up" turned it red. The co-occurrence of `run_id`
    with its source *is* the read-it-do-not-invent-it rule; there is no other
    reason for the two to appear together.

    radius=450 against a measured worst-case 53-character distance from
    `run_id` to its source token across the three passes -- margin ~8.5x,
    which is well over this module's floor (see the module docstring) and
    deliberately so. The mirror probe that set it: rewording all three
    sentences meaning-preservingly, moving the source to the end of the
    clause, pushed the worst distance to 172 and left only 1.45x at
    radius=250. Nothing false enters at the wider radius -- `shard`'s next
    occurrence in the rule pass is at +571 and `00-objective.json`'s in the
    audit pass at +5261, both outside it.
    """
    body = _norm(skills.section_body(_skill(pass_name), "2. Output"))
    assert "schema_version" in body
    assert '"0.1"' in body
    index = body.find("run_id")
    assert index != -1, "the Output section never names run_id"
    assert source in _window_after(body, index, radius=450)
