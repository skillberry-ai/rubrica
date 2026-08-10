"""tg-emit's contract: a thin entry point that writes nothing itself."""

from __future__ import annotations

from testgen.skills import SECTIONS, load, skills_dir
from testgen.validate import STAGE_ARTIFACTS

SKILL = skills_dir() / "tg-emit" / "SKILL.md"


def test_the_contract_matches_the_stage_gate():
    skill = load(SKILL)
    assert skill.contract["stage"] == "emit"
    assert set(skill.contract["schemas"]) == set(STAGE_ARTIFACTS["emit"])


def test_it_invokes_the_emit_subcommand_rather_than_describing_how_to_emit():
    """The whole reason this skill is thin. A prompt that explained how to build
    a Harbor package would reintroduce the nondeterminism emit-as-code removed.
    """
    assert "emit" in load(SKILL).contract["invokes"]


def test_it_has_the_five_sections():
    assert all(section in load(SKILL).headings for section in SECTIONS)


def test_it_states_why_emit_is_code_rather_than_a_prompt():
    body = load(SKILL).body.lower()
    assert "reproducib" in body


def test_it_states_that_a_pruned_package_is_information_not_an_error():
    body = load(SKILL).body.lower()
    assert "prune" in body
    assert "rejected" in body
