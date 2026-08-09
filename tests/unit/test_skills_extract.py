"""tg-extract's contract and the structural properties its prompt must have.

Structural, not free-text: an assertion that some sentence appears in the prose
is shape 1 by construction, because another sentence may contain the same
words. What is asserted here is either a declaration in the contract block or
a set compared against a set imported from the code.
"""

from __future__ import annotations

from testgen.skills import SECTIONS, load, skills_dir
from testgen.validate import STAGE_ARTIFACTS

SKILL = skills_dir() / "tg-extract" / "SKILL.md"


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
