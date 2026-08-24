"""rb-extract's contract and the structural properties its prompt must have.

Structural, not free-text: an assertion that some sentence appears in the prose
is shape 1 by construction, because another sentence may contain the same
words. What is asserted here is either a declaration in the contract block or
a set compared against a set imported from the code.
"""

from __future__ import annotations

from rubrica.skills import SECTIONS, load, section_body, skills_dir
from rubrica.validate import STAGE_ARTIFACTS

SKILL = skills_dir() / "rb-extract" / "SKILL.md"


def paragraphs(text: str) -> list[str]:
    """Blank-line-separated paragraphs.

    Used where a property is really a *co-occurrence*: a rule and the thing it
    is about have to be stated together to be followable, and two mentions in
    unrelated paragraphs are what makes a whole-body substring check vacuous.
    """
    return [chunk for chunk in text.split("\n\n") if chunk.strip()]


def test_the_contract_is_exactly_what_the_stage_is_gated_on():
    skill = load(SKILL)
    assert skill.contract["stage"] == "extract"
    assert set(skill.contract["schemas"]) == set(STAGE_ARTIFACTS["extract"])


def test_it_declares_only_the_two_artifacts_a_fan_out_member_may_read():
    """The isolation rule: an extract subagent sees the manifest and its own
    input file. Declaring claims_dir would let it read a sibling's conclusions,
    which is exactly what the fan-out was chosen to prevent.
    """
    assert load(SKILL).contract["reads"] == ["manifest", "input_file"]


def test_the_inputs_section_forbids_a_sibling_read_whatever_the_purpose():
    """Added under a ruling from Task 13's whole-pipeline exercise.

    The extract subagent dispatched for `notes-md` in that run self-reported
    reading both sibling input files while checking locator-format
    conventions. Its claims were clean and both gates passed; nothing in the
    system could have seen it. The loophole is that the section's original
    prohibition explained itself entirely in terms of content bleeding across
    -- so a reader whose motive is *format* rather than content can conclude
    the stated reason does not apply to them, which is the shape of failure
    hardest to write against because the motive is genuinely helpful.

    Scoped to section 1 with `section_body` and asserted as a co-occurrence
    inside one paragraph, not as a substring of the whole file: `body`
    includes every other section, and "locator" alone occurs twice in Method
    step 3, which owns the format this paragraph points at -- so a whole-body
    search for the word could not fail. Two assertions, because the fix has
    two halves and either one alone leaves the gap open: the prohibition must
    be purpose-independent, and the model must be told where the convention
    legitimately comes from -- removing the motive, not only the permission.
    """
    paras = paragraphs(section_body(load(SKILL), SECTIONS[0]))

    forbidding = [
        para
        for para in paras
        if "locator" in para
        and ("api.json" in para or "trace.json" in para or "sibling" in para)
        and ("motive" in para or "why you opened" in para)
    ]
    assert forbidding, (
        "no Inputs paragraph forbids opening a sibling input file for a non-content purpose "
        "such as checking how a locator is formatted; a prohibition justified only by content "
        "contamination reads as inapplicable to a subagent that wants the house format, and "
        "that read is what Task 13's run actually produced"
    )

    assert any("evidence.locator" in para and "Method step 3" in para for para in paras), (
        "no Inputs paragraph says where the locator convention does come from -- the claims "
        "schema's evidence.locator field and this skill's Method step 3. Forbidding the "
        "sibling read without naming the legitimate route leaves the motive intact"
    )


def test_it_has_the_five_sections():
    assert all(section in load(SKILL).headings for section in SECTIONS)


def test_the_derivation_values_it_names_are_the_schema_s_enum():
    """A skill that names two of the three values would let the third go
    unwritten, and derivation is what makes gap reporting honest. Compared
    against the schema rather than a literal list.
    """
    from rubrica.artifacts import read_json
    from rubrica.validate import ARTIFACT_SCHEMAS, schema_dir

    schema = read_json(schema_dir() / ARTIFACT_SCHEMAS["claims"])
    enum = schema["$defs"]["claim"]["properties"]["derivation"]["enum"]
    body = load(SKILL).body
    for value in enum:
        assert value in body, f"the skill never mentions derivation={value!r}"


def test_the_claim_kinds_it_names_are_the_schema_s_enum():
    from rubrica.artifacts import read_json
    from rubrica.validate import ARTIFACT_SCHEMAS, schema_dir

    schema = read_json(schema_dir() / ARTIFACT_SCHEMAS["claims"])
    enum = schema["$defs"]["claim"]["properties"]["kind"]["enum"]
    body = load(SKILL).body
    missing = [kind for kind in enum if kind not in body]
    assert not missing, f"the skill never mentions claim kind(s) {missing}"


def test_the_refusal_section_names_a_response_for_an_unreadable_input():
    """One of the refusal conditions, and the only one with a prescribed *output*.

    **The body now checks what the name says.** It used to assert only that
    section 5 is last and has at least four lines, so replacing all four
    conditions with "Write whatever seems most helpful" left every test in this
    file green -- a length floor over a section whose emptiness `check_contract`
    already reports, and a name promising a content check that nothing performed.

    Making the body match the name rather than the reverse, because this
    condition is the one that can be checked for content without pinning a
    phrase: an unreadable input has a *specific* prescribed response -- a claims
    file with an empty `claims` array -- and a stage that instead guesses from
    the filename or the manifest `kind` writes confabulated claims that are
    byte-indistinguishable from extracted ones. Renaming the test would have left
    that unguarded and added nothing. The structural checks are kept: they cost
    nothing and the ordering one is real.
    """
    skill = load(SKILL)
    refusals = SECTIONS[-1]
    index = skill.headings.index(refusals)
    assert index == len(skill.headings) - 1, "refusal conditions must be the last section"
    body = section_body(skill, refusals)
    assert len(body.strip().splitlines()) >= 4, "four refusal conditions are required"

    owning = [
        para
        for para in paragraphs(body)
        if ("unreadable" in para.lower() or "cannot be read" in para.lower()) and "claims" in para
    ]
    assert owning, (
        "no refusal condition says what to do with an input that cannot be read, so the "
        "stage's only guidance is to be helpful"
    )
    assert any("empty" in para.lower() for para in owning), (
        "that condition must prescribe the output -- a claims file with an empty claims "
        "array -- not merely acknowledge the situation"
    )
    assert any("guess" in para.lower() or "do not" in para.lower() for para in owning), (
        "and it must forbid the tempting alternative: reconstructing the content from the "
        "filename, the manifest kind, or a sibling artifact"
    )


def test_it_requires_every_prose_heading_to_be_cited_or_explained():
    """rb-extract already said "every statement it makes about the target" and
    still skipped an entire section: the claims from agent-notes-md carry
    locators L51...L55 then jump to L84, and L57-L80 is the whole Usage Examples
    section -- five canonical user asks plus res_12345 -- while the Apache licence
    at L187 got a claim.

    Universal quantification works when the set is small, closed and already
    written down. "Every statement in a document" is unbounded; "every `##`
    heading" is not.

    Whitespace-normalised before matching: measured that rewrapping the
    paragraph at width 60, changing no words, split "every `##` heading"
    across a line boundary and flipped this test red -- collapsing runs of
    whitespace to single spaces tests the words, not where an editor happened
    to wrap the line.
    """
    method = " ".join(section_body(load(SKILL), "3. Method").lower().split())
    assert "every `##` heading" in method
    assert "carries nothing about the target" in method


def test_the_method_ties_a_state_observation_to_its_capture_instant():
    """A trace claim that omits when it was observed is unresolvable downstream.

    Measured on run-20260816-172810: `trajectories2-json-3` and
    `trajectories2-json-10` both list jane@example.com's reservations, either
    side of the cancellation in `trajectories2-json-4`, and produced claims
    reading "returned a list containing exactly one reservation" against
    "returned `[]`". `rb-reconcile` recorded that as `both_possible` on the
    stated grounds that "no input carries a timestamp or sequence relating
    them" -- while all three input files carried `info.request_time`, inside the
    one artifact each fan-out member is allowed to read.

    Asserted as a co-occurrence inside section 3 rather than as presence
    anywhere in the file: `skills.load()` sets `body` to the entire file text,
    so a bare substring check here would also be satisfied by the frontmatter
    description or the Contract block.

    Whitespace-normalised for the same reason the heading test above is -- the
    words are the rule, not where a reflow put the line break.
    """
    method = " ".join(section_body(load(SKILL), "3. Method").lower().split())
    assert "observed state" in method
    assert "capture instant" in method
    assert "request_time" in method
    # The scoping half of the rule: it must NOT be attached to contract claims,
    # or every claim in a trace acquires a timestamp and the signal is noise.
    assert "declared contract" in method


def test_the_method_says_why_only_extract_can_carry_the_instant():
    """The rule is load-bearing because of where it sits in the pipeline, and a
    reader who does not know that will treat it as bookkeeping and drop it.

    rb-reconcile's `reads` is claims_dir and manifest: it never sees a trace, so
    an instant extract leaves out is unrecoverable rather than merely absent.
    """
    method = " ".join(section_body(load(SKILL), "3. Method").lower().split())
    assert "only stage that reads this artifact" in method
    assert "no later stage can recover" in method


def test_the_method_allows_a_prose_instant_where_no_field_carries_one():
    """Measured on tau2-bench's 200 chat trajectories: zero carry any
    time-shaped key, while the instant is stated in the opening message's prose
    ("The current time is 2024-05-15 15:00:00 EST."). Without this clause the
    rule's worked example points at a field the artifact does not have, and a
    member reading it literally records no instant at all.

    Scoped to section 3 with section_body for the reason the two predicates above
    are: skills.load() sets body to the whole file text, so a bare substring
    check would also be satisfied by the frontmatter or the Contract block.
    """
    method = " ".join(section_body(load(SKILL), "3. Method").lower().split())
    assert "in prose" in method
    assert "locator of that message" in method
