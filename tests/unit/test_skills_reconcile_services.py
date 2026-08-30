"""rb-reconcile-services' contract, and the rules its prose must carry.

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


def _paragraph_carrying(skill, heading: str, *keys: str) -> str:
    """The one blank-line-delimited paragraph in a section carrying any of `keys`.

    §3 ends with a prose paragraph rather than a numbered step, so _step_carrying
    cannot reach it -- it matched zero steps, measured. Paragraph scoping is the
    same instrument one shape over: flattened, so a rewrap cannot flip it, and
    exactly-one so a key that matches two paragraphs is not a locator.
    """
    paragraphs = skills.section_body(skill, heading).split("\n\n")
    flat = [" ".join(paragraph.lower().split()) for paragraph in paragraphs]
    found = [paragraph for paragraph in flat if any(k in paragraph for k in keys)]
    assert len(found) == 1, f"{keys} locates {len(found)} paragraph(s) in {heading}: {found}"
    return found[0]


def _bullets(skill, heading: str) -> list[str]:
    """One entry per top-level `- ` bullet in a section, each flattened like _flat.

    A continuation line joins the bullet above it, so a wrapped bullet is one entry.
    Mirrors test_skills_reconcile_family._bullets for the same measured reason: a
    §5 assertion over a whole section is satisfied by any of seven sibling
    conditions, so a rule deleted from the one that owns it stays green.
    """
    out: list[str] = []
    for line in skills.section_body(skill, heading).splitlines():
        if line.startswith("- "):
            out.append(line)
        elif out:
            out[-1] += " " + line
    return [" ".join(bullet.lower().split()) for bullet in out]


def _bullet_carrying(skill, heading: str, *keys: str) -> str:
    """The one bullet carrying any of `keys`. The exactly-one check is part of the
    instrument: a key matching two bullets is not a locator, and one matching none
    means the rule is gone rather than that the test should quietly pass.
    """
    found = [bullet for bullet in _bullets(skill, heading) if any(k in bullet for k in keys)]
    assert len(found) == 1, f"{keys} locates {len(found)} bullet(s), not one: {found}"
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


def test_a_refusal_condition_covers_a_finding_against_another_stages_artifact(skill):
    """The third move, for the one state that otherwise has no legal one.

    `check-refs` now compares every `schema_claim`'s payload against the input
    region its locator names and reports a mismatch against the claims file --
    `rb-extract`'s artifact. §4's verification paragraph says a finding naming
    another artifact is not this pass's to fix, and one sentence later says to
    report success only once `check-refs` exits clean: from a schema-valid run,
    obeying both is possible only by editing another stage's output or by claiming a
    success the exit code contradicts. Same class as the >64-character name, which
    had no legal record until a refusal gave it one.

    Scoped to the bullet that owns it, and asserted through several formulations
    where the wording is the part a meaning-preserving reword changes.
    """
    bullet = _bullet_carrying(skill, "5. Refusal conditions", "check-refs")
    assert "payload" in bullet
    # Stems and an OR over the natural formulations rather than phrase pins, which
    # is what the sibling at the top of this section does (`renam`, `record` or
    # `report`). Measured: `"do not edit"` reds on a meaning-preserving "Never edit
    # that file", and `"01-claims/"` on a bullet that says "the claims file" -- the
    # same class as this project's `rename` -> `renam` fix, and narrow fragility
    # rather than a broken guard, since a wholesale rewrite stays green either way.
    assert any(k in bullet for k in ("01-claims/", "claims file")), bullet
    # Both halves of the prohibition, plus the move that replaces them.
    # An OR over the three ways a prohibition on editing is actually written --
    # `do/must not edit`, `never edit`, and the passive `must not be edited` -- and
    # not the bare stem `edit`, which the mirror hazard satisfies: a bullet
    # *permitting* the edit would contain it too. Measured: the passive reworded
    # variant reds against ("not edit", "never edit") alone, which is how this set
    # got its third entry.
    assert any(k in bullet for k in ("not edit", "never edit", "not be edited")), bullet
    assert any(k in bullet for k in ("not report success", "not clean")), bullet
    assert "stop" in bullet


def test_the_verification_paragraph_points_at_that_condition(skill):
    """The other side of the pair: the paragraph that used to demand one of two
    forbidden moves has to name the third one, or a reader who stops at the
    verification instruction still has no legal move.
    """
    # §4, not §3: the verification paragraph closes the Invariants section, which
    # is where the arithmetic it re-runs is stated. Measured -- over §3 the locator
    # matched nothing.
    paragraph = _paragraph_carrying(skill, "4. Invariants", "report success")
    assert "refusal condition" in paragraph, paragraph


def test_the_unusable_payload_condition_routes_the_finding_it_produces(skill):
    """The bullet that *instructs* the state, carrying the move for the finding.

    Following this condition is not a defect, and after the fix round that measured
    it the finding synthesis raises names `01-claims/<artifact_id>.json` rather than
    this pass's part -- so the pass can be handed a finding about an artifact it did
    not write, for having done exactly what it was told. That is the same class as
    the `check-refs` bullet below it, and the same third move closes it. Without the
    move stated here, a reader of this bullet alone has two forbidden options: edit
    another stage's claims file, or report a success the exit code contradicts.

    Scoped to the one bullet that owns the case, and asserted through stems and
    alternations for the reason its sibling records: `01-claims/` reds on a
    meaning-preserving "the claims file", and "do not edit" on "never edit".
    """
    bullet = _bullet_carrying(skill, "5. Refusal conditions", "schema_claim")
    # The file the finding names -- the whole point of the routing, since the
    # tempting reading is that a finding about your own citation is yours to fix.
    assert any(k in bullet for k in ("01-claims/", "claims file")), bullet
    assert any(k in bullet for k in ("not yours", "rb-extract")), bullet
    # The third move, in the three parts that make it recoverable: report it, keep
    # your hands off the other stage's file, and stop rather than claim success.
    assert "stop" in bullet, bullet
    # A regex rather than the literal set its sibling uses, and both bounds are
    # measured. Tighter fails: the meaning-preserving "that claims file is never
    # yours to edit" reds every literal in that set and every adjacency window.
    # Looser fails too -- the bare stem `edit` is the mirror hazard, since a bullet
    # *permitting* the edit carries it just as well. So: a prohibition and the verb
    # inside one sentence, which a permission is not. The bullet also writes "must
    # not" with no emphasis inside it deliberately: `must **not** edit` reds this.
    assert re.search(r"(?:do not|must not|never)\b[^.]{0,40}?\bedit", bullet), bullet
    assert any(k in bullet for k in ("report the finding", "report it")), bullet


def test_the_unpreservable_name_condition_names_the_one_legal_way_out(skill):
    """A dead end with an escape the bullet used to leave unnamed.

    Recording the tool under its real name is what this condition requires, and
    `synthesise-interfaces` then refuses the service -- correctly, and against this
    pass's own part. Re-dispatched with that finding, a pass told only "record it
    and do not rename it" has no move at all, and the one it is likeliest to invent
    is the rename this bullet forbids. Invariant 1's accounting is the escape:
    `dropped` with a `note`. So the bullet has to name it, while still forbidding
    the rename -- both halves, in the bullet that owns them.
    """
    bullet = _bullet_carrying(skill, "5. Refusal conditions", "sanitis")
    assert "renam" in bullet, bullet
    assert "dropped" in bullet, bullet
    assert "note" in bullet, bullet
    # Named as the invariant rather than described loosely, because `dropped` and
    # `note` alone are also how section 2 describes a drop: what makes this the
    # *legal* way out is that Invariant 1 admits it.
    assert "invariant 1" in bullet, bullet
