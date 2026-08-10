"""tg-extract's contract and the structural properties its prompt must have.

Structural, not free-text: an assertion that some sentence appears in the prose
is shape 1 by construction, because another sentence may contain the same
words. What is asserted here is either a declaration in the contract block or
a set compared against a set imported from the code.
"""

from __future__ import annotations

from testgen.skills import SECTIONS, load, section_body, skills_dir
from testgen.validate import STAGE_ARTIFACTS

SKILL = skills_dir() / "tg-extract" / "SKILL.md"


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
    from testgen.artifacts import read_json
    from testgen.validate import ARTIFACT_SCHEMAS, schema_dir

    schema = read_json(schema_dir() / ARTIFACT_SCHEMAS["claims"])
    enum = schema["$defs"]["claim"]["properties"]["derivation"]["enum"]
    body = load(SKILL).body
    for value in enum:
        assert value in body, f"the skill never mentions derivation={value!r}"


def test_the_claim_kinds_it_names_are_the_schema_s_enum():
    from testgen.artifacts import read_json
    from testgen.validate import ARTIFACT_SCHEMAS, schema_dir

    schema = read_json(schema_dir() / ARTIFACT_SCHEMAS["claims"])
    enum = schema["$defs"]["claim"]["properties"]["kind"]["enum"]
    body = load(SKILL).body
    missing = [kind for kind in enum if kind not in body]
    assert not missing, f"the skill never mentions claim kind(s) {missing}"


def test_the_refusal_section_names_a_response_for_an_unreadable_input():
    """One of the four refusal conditions, checked structurally: the section
    must be long enough to carry four distinct triggers. A length floor is a
    weak check and is here only to catch a section reduced to one line -- the
    live exercise is what tests whether the conditions actually fire.
    """
    from testgen.skills import SECTIONS as S

    skill = load(SKILL)
    index = skill.headings.index(S[-1])
    assert index == len(skill.headings) - 1, "refusal conditions must be the last section"
    body = skill.body.split(f"## {S[-1]}", 1)[1]
    assert len(body.strip().splitlines()) >= 4, "four refusal conditions are required"
