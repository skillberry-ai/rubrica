"""rb-reconcile-services' contract and the four rules its prose must carry.

Every assertion here is scoped with skills.section_body. `skills.load()` sets
`body` to the entire file text and the five section headings are mandatory, so an
unscoped `"signal" in body` is satisfied by the frontmatter description and by the
contract block -- the structural reason roughly nineteen assertions in this repo
were measured satisfiable by unrelated content.

The family-wide properties of this pass -- that it reads all of `01-claims/`,
that it declares no world model, that it carries the `inputs_seen` prose every
owning pass carries -- are asserted in test_skills_reconcile_family.py, which
derives its parametrization from `paths.STAGES` and so picked this pass up the
moment the stage was declared. What is here is only what is particular to it.
"""

from __future__ import annotations

import re

import pytest

from rubrica import skills


@pytest.fixture
def skill():
    return skills.load(skills.skills_dir() / "rb-reconcile-services" / "SKILL.md")


def _flat(skill, heading: str) -> str:
    """One section, lowercased with runs of whitespace collapsed.

    The same normalisation test_skills_reconcile_family._flat applies, and for
    the same measured reason: a pure rewrap changes no words and must not flip a
    test -- rewrapping a paragraph at width 60 once split "becomes an entity"
    across a line boundary and turned an assertion red. Every token asserted
    below is therefore written lowercase.
    """
    return " ".join(skills.section_body(skill, heading).lower().split())


def _step_carrying(skill, heading: str, *keys: str) -> str:
    """The one numbered step in a section carrying any of `keys`, flattened.

    The Method sections in this family are numbered lists, and a rule lives in one
    step. Asserting over the whole section lets a token be satisfied by a sibling
    step -- measured here for `declared`, which step 2 uses for its own purpose --
    so a rule deleted from the step that owns it can stay green. Mirrors
    test_skills_reconcile_family._bullet_carrying, which does this for `- ` bullets;
    the exactly-one check is the same half of the instrument.
    """
    steps: list[str] = []
    for line in skills.section_body(skill, heading).splitlines():
        if re.match(r"\d+\. ", line):
            steps.append(line)
        elif steps:
            steps[-1] += " " + line
    flat = [" ".join(step.lower().split()) for step in steps]
    found = [step for step in flat if any(k in step for k in keys)]
    assert len(found) == 1, f"{keys} locates {len(found)} step(s) in {heading}, not one: {found}"
    return found[0]


def test_the_contract_binds_the_stage_and_reads_every_claims_file(skill):
    contract = skill.contract
    assert contract["stage"] == "reconcile-services"
    assert contract["writes"] == ["services_part"]
    assert contract["schemas"] == ["services-part"]
    # The barrier property: all of the claims, not one slice of them. The family is
    # split on *output*, so a pass reading one claims file would break the property
    # the single-dispatch stage had.
    assert "claims_dir" in contract["reads"]
    assert "manifest" in contract["reads"]


def test_no_containment_verdict_is_asked_for_anywhere_in_the_output_section(skill):
    """The one place the pipeline would assert a certainty it cannot support.

    A tool that looks self-contained but holds a hidden call produces a suite that
    passes in the lab and fails in production, so uncertainty must not read as
    contained. Asserted as an absence *and* a presence: the absence alone would be
    satisfied by a section that says nothing about containment at all.

    Three presence tokens rather than the two the absence needs a companion for,
    because two of them are measurably too weak on their own. `signal` and
    `absence of evidence` both survive deletion of the paragraph that carries the
    rule -- the first from the field list, the second from the
    `no_outward_evidence_found` bullet -- so `verdict` is the token that actually
    pins it: that word appears nowhere else in this section, and the rule cannot
    be stated without contrasting signals with one.
    """
    output = _flat(skill, "2. Output")
    assert "contained" not in output.replace("self-contained", "")
    assert "signal" in output
    assert "verdict" in output
    assert "absence of evidence" in output


def test_the_schema_claim_rule_names_the_disagreement_case(skill):
    """Two claims can describe one tool and disagree about its input schema.
    Synthesis is deterministic and cannot pick a winner, so the pick is this
    pass's recorded judgment -- and the Method section has to say which way.

    `declared` is the design's own word for the winning side, not a phrase this
    test invented: `world-model-0.1.json#/$defs/service_tool` describes the two
    pieces of evidence as "a tool declared in a tool-schema document and observed
    again in a trace".

    Scoped to the numbered step that owns the rule rather than to §3 as a whole,
    and the difference is measured rather than assumed: with the owning step
    deleted, `declared` is still satisfied by step 2's "a tool declared in one
    input and observed again in another", so over the whole section only
    `schema_claim` was carrying this test. Two of three tokens satisfiable by
    unrelated prose in the same section is the exact weakness this repository
    measured roughly nineteen times before section scoping became the convention;
    step scoping is that convention applied one level further down.
    """
    step = _step_carrying(skill, "3. Method", "schema_claim")
    assert "disagree" in step
    assert "declared" in step


def test_a_refusal_condition_covers_a_tool_name_that_cannot_be_preserved(skill):
    """Co-occurrence within the refusal section, not presence anywhere: a skill
    that mentions sanitisation in its Method section and refuses nothing would
    satisfy either half alone.
    """
    refusal = _flat(skill, "5. Refusal conditions")
    assert "renam" in refusal
    assert "record" in refusal or "report" in refusal
