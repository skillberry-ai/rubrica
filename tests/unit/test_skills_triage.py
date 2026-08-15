"""Prose predicates for rb-triage, each scoped to the section that owns the rule.

Roughly nineteen assertions in this repo were measured satisfiable by unrelated
content before this convention existed. Task 11's brief measured each of these
in both directions; a predicate nobody has watched fail is not a guard.
"""

from __future__ import annotations

import re

from rubrica import digest, skills


def _skill():
    # skills_dir() re-read on every call, not cached at import time, so a
    # test run under RUBRICA_SKILLS_DIR=/tmp/skills-probe (the both-direction
    # measurement in the task) reads that copy rather than the installed one.
    return skills.load(skills.skills_dir() / "rb-triage" / "SKILL.md")


def _norm(text):
    """Whitespace-normalised, so a reflow does not break a phrase pin.

    399dba5 fixed exactly this: two phrase pins broke on an innocuous reformat.
    """
    return re.sub(r"\s+", " ", text.lower())


def test_the_inputs_section_forbids_opening_a_candidate_file():
    """The catalogue-only rule is the design's cost bound and its comparability
    guarantee. It has to be stated where a reader looking for what to read looks.

    The first assertion is weakened from a bare "not the corpus" pin after
    measuring it break on the meaning-preserving reword "you never open the
    corpus itself" -- accepted as an alternative rather than deleting the
    concept check. The second assertion is weakened the same way, after the
    same batch reword also replaced "Opening one is out of contract." with
    "Doing so falls outside your contract." -- "outside your contract"
    carries the identical claim and is accepted alongside the original."""
    body = _norm(skills.section_body(_skill(), "1. Inputs"))
    assert "00-catalogue.json" in body
    assert "not the corpus" in body or "never open the corpus" in body
    assert "out of contract" in body or "outside your contract" in body


def test_the_inputs_section_names_heuristics_fired_as_a_fact_about_the_digest():
    """A heuristic that did not fire is a fact about the digest, not the
    candidate -- the mitigation for the module's blindness only works if the
    skill reads the field that way.

    Review of this task found the second assertion satisfiable by a different
    paragraph than the one it names: correction 2's skeleton-truncation prose
    also contains the literal phrase "about the digest", roughly 520 chars
    after this mention, so a section-wide search could pass even if the
    heuristics_fired sentence itself dropped the phrase entirely. Bounded to
    a 300-char window right after the heuristics_fired mention -- long enough
    to survive a reword of that one sentence, short enough to stay well clear
    of the second occurrence -- so this predicate is scoped to the sentence
    it is meant to guard, not to the section that happens to contain it."""
    body = _norm(skills.section_body(_skill(), "1. Inputs"))
    assert "heuristics_fired" in body
    start = body.index("heuristics_fired")
    window = body[start : start + 300]
    assert "about the digest" in window


def test_the_inputs_section_names_trace_heuristics_reachably():
    """digest.TRACE_HEURISTICS is the code's list; heuristics_fired is the
    field the skill has to know carries it. Enumerating each heuristic name in
    prose would pin digest.py's internals to a document, which 2f93726 warns
    against, so this only checks that the code's list is non-empty and the
    skill names the field."""
    body = _norm(_skill().body)
    assert digest.TRACE_HEURISTICS
    assert "heuristics_fired" in body


def test_the_inputs_section_marks_a_truncated_skeleton_as_a_digest_fact():
    """A JSON candidate's skeleton is width-bounded at 32 children; without
    this the skill would read an incomplete skeleton as a complete one."""
    body = _norm(skills.section_body(_skill(), "1. Inputs"))
    assert "keys_truncated" in body
    assert "fact about the digest" in body


def test_the_inputs_section_warns_status_and_error_markers_are_not_independent():
    """Measured on the real 130-element parsec capture: after narrowing,
    error_markers fires on exactly one element and every firing resolves
    through status, so the two names can be one fact reported twice.

    The second assertion is weakened from a bare "one fact" pin after
    measuring it break on the meaning-preserving reword "a single observation
    ... stated twice" -- "stated twice" is the part of the sentence that
    survived that reword, so it replaces "one fact" as the anchor."""
    body = _norm(skills.section_body(_skill(), "1. Inputs"))
    assert "error_markers" in body and "status" in body
    assert "one fact" in body or "stated twice" in body


def test_the_output_section_names_the_authority_field():
    """triage-0.1.json:62 requires authority on every disposition (enum
    ["triage", "human"], schema line 70). Finding 1 of this task's review:
    the skill never named it, so a live dispatch's first `rubrica validate`
    would report a missing-required-property finding on every disposition it
    wrote -- the primary output artifact, not an edge case."""
    body = _norm(skills.section_body(_skill(), "2. Output"))
    assert "authority" in body
    assert "gate-0 override" in body or "gate 0 override" in body


def test_the_method_section_names_all_seven_projection_fields():
    """triage-0.1.json's projections[] requires all seven of projection_id,
    closes, sources, wanted, method, acceptance, and boundary -- a projection
    missing either of the two the brief's text omitted fails layer 1, which
    would be discovered at a live dispatch rather than in tests."""
    body = _norm(skills.section_body(_skill(), "3. Method"))
    for field in (
        "projection_id",
        "closes",
        "sources",
        "wanted",
        "method",
        "acceptance",
        "boundary",
    ):
        assert field in body


def test_the_method_section_names_the_projection_sources_digest_note():
    """triage-0.1.json:107 requires digest_note on every projections[].sources
    entry alongside candidate_id. Finding 3 of this task's review: every other
    leaf field in this paragraph was named at the key level (wanted.kind/
    statement/why, method.steps/confidence, all five acceptance keys) but
    sources was described only in prose, without its literal required key."""
    body = _norm(skills.section_body(_skill(), "3. Method"))
    assert "digest_note" in body


def test_the_method_section_requires_the_absence_check():
    """Step 5 is the block that would have predicted six parsec refusals.

    The first assertion accepts a couple of synonyms for "result shape"
    after measuring the bare phrase break on the reword "returned structure"
    -- not widened to the bare word "shape", which step 4's near-duplicate
    prose ("distinct shape") would satisfy regardless of what step 5 says."""
    body = _norm(skills.section_body(_skill(), "3. Method"))
    assert "result shape" in body or "returned structure" in body or "return shape" in body
    assert "deficien" in body


def test_the_method_section_protects_a_failing_trace_from_near_duplicate_folding():
    """The one ERROR trace in 130 was the parsec run's only evidence of failure
    behaviour, and near_duplicate is exactly how it would have been lost."""
    body = _norm(skills.section_body(_skill(), "3. Method"))
    assert "failing trace" in body
    assert "near-duplicate" in body


def test_the_method_section_admits_unknown_as_a_method_confidence():
    body = _norm(skills.section_body(_skill(), "3. Method"))
    assert "unknown" in body and "honest" in body


def test_the_method_section_says_structural_acceptance_is_not_sufficient():
    """Weakened from a single phrase pin ("never sufficient" / "not
    sufficient") after measuring it break on a meaning-preserving reword:
    "necessary but insufficient on their own" says the same thing and failed
    both alternatives.

    A bare "insufficient" alternative was tried and then dropped before it ever
    shipped: it does survive that rewording, but `digest_insufficient` is a
    schema enum value discussed elsewhere in this same skill for an unrelated
    reason (section 5's refusal condition about one bad digest), and nothing
    stops Method prose from someday naming it too. A latent phrase-pin
    collision -- not one that fires today, but one where a future, unrelated
    edit to this section would make the assertion pass for the wrong reason,
    vacuously, with nobody noticing. Kept to the two phrasings actually
    measured to carry the claim."""
    body = _norm(skills.section_body(_skill(), "3. Method"))
    assert "never sufficient" in body or "not sufficient" in body


def test_the_invariants_section_requires_one_disposition_per_candidate():
    body = _norm(skills.section_body(_skill(), "4. Invariants"))
    assert "exactly one disposition" in body
    assert "not fewer" in body


def test_the_invariants_section_forbids_acting_on_a_recommended_objective():
    """A re-scope the stage performs itself is invisible, and produces a
    selection that looks coherent and answers a question nobody asked."""
    body = _norm(skills.section_body(_skill(), "4. Invariants"))
    assert "recommended_objective" in body
    assert "recommendation" in body


def test_the_refusal_section_refuses_a_missing_objective_and_an_empty_admit_set():
    """The second assertion's first half is weakened from a bare "every
    candidate" pin after measuring it break on the meaning-preserving reword
    "an admitted set with nothing in it" -- "zero admits" alone, which that
    reword still left standing one sentence later, carries the same claim."""
    body = _norm(skills.section_body(_skill(), "5. Refusal conditions"))
    assert "objective" in body and "absent" in body
    assert ("every candidate" in body or "nothing in it" in body) and "zero admits" in body


def test_the_refusal_section_forbids_refusing_on_an_unsupported_objective():
    """Refusing there leaves the human nothing to rule on, which is the opposite
    of the help gate 0 needs."""
    body = _norm(skills.section_body(_skill(), "5. Refusal conditions"))
    assert "do not refuse" in body
    assert "unsupported" in body


def test_the_refusal_section_forbids_refusing_over_one_bad_digest():
    body = _norm(skills.section_body(_skill(), "5. Refusal conditions"))
    assert "digest_insufficient" in body
    assert "three hundred" in body or "not a reason to abandon" in body


def test_the_output_section_names_schema_version_and_the_run_id_it_reads():
    """Every other stage skill states its `schema_version` (rb-extract,
    rb-reconcile, rb-propose, rb-score, rb-challenge, rb-instantiate); rb-triage
    named neither it nor `run_id`, and `triage-0.1.json` requires both at the
    document root. Nothing pinned it, which is the same defect the task review
    caught one level up for `authority`.

    Scoped to section 2, which owns the output's shape -- `"schema_version" in
    body` over the whole file is vacuous for every skill in this repo, since
    `skills.load()` sets `body` to the entire file text. `0.1` is asserted
    alongside the field name because naming the field without its value tells a
    model nothing it can write.
    """
    body = _norm(skills.section_body(_skill(), "2. Output"))
    assert "schema_version" in body
    assert '"0.1"' in body
    assert "run_id" in body
    # And where to read it from: an invented run_id is exactly what
    # intake.py's module docstring says must never come from a skill.
    assert "00-catalogue.json" in body and "never invent" in body


def test_the_output_section_says_an_empty_block_is_still_written():
    """`triage-0.1.json` requires `deficiencies` and `projections` at the root,
    so a record with nothing to report in either still carries `[]`. Omitting a
    block because it would be empty fails layer 1 and spends a repair round on a
    record whose judgment was fine.

    The `[]` spellings are pinned because that is the actionable half: prose
    saying "required" without showing the empty value leaves a model to guess
    between `[]`, `null`, and omission.
    """
    body = _norm(skills.section_body(_skill(), "2. Output"))
    assert '"deficiencies": []' in body
    assert '"projections": []' in body
    assert "required" in body
    assert "empty" in body


def test_the_output_section_places_a_human_authority_in_this_runs_record():
    """It said `authority: "human"` was reserved for a gate-0 override "that
    lands in a later run's record" -- wrong in both directions. Both a gate-0
    override and `adopt-projection` edit *this* run's 00-triage.json, and
    `triage.adopt_projection` appends its admit with `authority: "human"` to the
    very file this skill produced.
    """
    body = _norm(skills.section_body(_skill(), "2. Output"))
    assert "adopt-projection" in body
    assert "this same record" in body
    # The negative half, and the only wording it can safely pin: the wrong claim
    # was that a human authority "lands in a later run's record". The corrected
    # prose still says "a new run's" while negating it, so pinning "later run"
    # absent would forbid stating the correction -- `lands in` is the phrase that
    # belonged only to the wrong version.
    assert "lands in" not in body, "the claim this replaced must be gone, not merely balanced"
