"""tg-emit's contract: a thin entry point that writes nothing itself."""

from __future__ import annotations

import re

from testgen.skills import SECTIONS, load, section_body, skills_dir
from testgen.validate import STAGE_ARTIFACTS

SKILL = skills_dir() / "tg-emit" / "SKILL.md"


def test_the_contract_matches_the_stage_gate():
    """The `reads` pin arrived with a Task 13 ruling: `scenarios` and `verdict`
    were added because Method step 4 has to report *why* a package is absent,
    and the two silent-prune reasons live only in those files -- `emit` skips a
    non-`active` scenario and a `reject` verdict with no finding either time,
    and no gate covers either (`refs.check_suite` reports a package that is
    present for an unjudged scenario and nothing about one that is absent).

    Set equality, not `<=`: `check_contract` only checks that each name is a
    public `RunPaths` attribute, so a silent narrowing back to the two-name form
    would pass every other check in the build.
    """
    skill = load(SKILL)
    assert skill.contract["stage"] == "emit"
    assert set(skill.contract["schemas"]) == set(STAGE_ARTIFACTS["emit"])
    assert set(skill.contract["reads"]) == {"scenarios", "verdict", "expected", "world_model"}


def test_it_invokes_the_emit_subcommand_rather_than_describing_how_to_emit():
    """The whole reason this skill is thin. A prompt that explained how to build
    a Harbor package would reintroduce the nondeterminism emit-as-code removed.
    """
    assert "emit" in load(SKILL).contract["invokes"]


def test_it_has_the_five_sections():
    assert all(section in load(SKILL).headings for section in SECTIONS)


def test_it_states_why_emit_is_code_rather_than_a_prompt():
    """Strengthened during Task 13's fix round, and this one the implementer had
    wrongly judged sound. Measured: `"reproducib"` occurs exactly twice in the
    delivered file, and one of them is Invariant 1's *unreproducible* -- a
    consequence of hand-editing a package, not a reason emit is code. Deleting
    the whole preamble paragraph that states the reason left all five tests
    green on that one word. (The refusal conditions do not rescue it either:
    they say "reproduce"/"reproduced", which the substring never matches.)

    So the causal claim itself is what is asserted -- reproducibility named
    alongside the prompt alternative, and the two-identical-runs argument that
    makes it a reason rather than an adjective.
    """
    body = load(SKILL).body
    assert re.search(r"reproducib.{0,200}prompt|prompt.{0,200}reproducib", body, re.I | re.S), (
        "the reason emit is code rather than a prompt must be stated"
    )
    assert re.search(r"two runs.{0,120}identical", body, re.I | re.S), (
        "the two-identical-runs argument is what makes reproducibility the reason"
    )


def test_it_states_that_a_pruned_package_is_information_not_an_error():
    """Strengthened during Task 13's fix round, after the review refuted the
    original as vacuous on both sides. `"prune" in body` was satisfied by the
    frontmatter `description:` line, and `"rejected" in body` by an incidental
    mention of `check-refs`'s tolerance inside Method step 3 -- so deleting
    Method step 4 *and* refusal condition 2, every statement of the property,
    left all five tests green.

    Scoped to the Method section, where step 4 owns this, and requiring both
    halves of the claim: that a prune is information rather than a defect, and
    that a `rejected` scenario's package is supposed to be gone. A co-occurrence
    of "prune" and "rejected" would not do -- step 3's tolerance paragraph
    contains both within a few lines of each other, by itself.
    """
    method = section_body(load(SKILL), "3. Method")
    assert re.search(r"information,? not an error", method, re.I), (
        "step 4 must say a pruned package is information rather than an error"
    )
    assert re.search(r"rejected.{0,100}supposed.{0,4}to be pruned", method, re.I | re.S), (
        "step 4 must say a rejected scenario's package is supposed to be pruned"
    )
