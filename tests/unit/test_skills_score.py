"""rb-score's contract, and the vocabularies it must be complete over.

This stage writes the numbers every later judgment is measured against, so the
completeness checks here are about vocabulary coverage: a verdict it cannot
name is a loop state it cannot report, and a hole reason it cannot name is an
uncovered cell it will mislabel as closable.
"""

from __future__ import annotations

import re

from rubrica.artifacts import read_json
from rubrica.cli import subcommand_names
from rubrica.skills import SECTIONS, load, section_body, skills_dir
from rubrica.validate import ARTIFACT_SCHEMAS, STAGE_ARTIFACTS, schema_dir

SKILL = skills_dir() / "rb-score" / "SKILL.md"

OUTPUT, METHOD, INVARIANTS = SECTIONS[1], SECTIONS[2], SECTIONS[3]


def _coverage_schema():
    return read_json(schema_dir() / ARTIFACT_SCHEMAS["coverage"])


def blocks(heading: str) -> list[str]:
    """Blank-line-separated blocks of one section, via the parser's own slicer.

    Two tests below need a *co-occurrence* rather than a mention: a vocabulary
    has to be enumerated in one place to be choosable from, and a rule has to
    state its own remedy to be followable. `load(...).body` is the whole
    document, so a whole-body substring check for either is satisfied by text
    belonging to some other rule -- which is exactly how both went vacuous.
    """
    return [chunk for chunk in section_body(load(SKILL), heading).split("\n\n") if chunk.strip()]


def method_step(number: int) -> str:
    """One numbered Method step, whitespace-normalised, paragraphs included.

    `blocks(METHOD)` splits on blank lines, which is the right unit for a rule
    that lives in one paragraph and the wrong one for a step that spans several:
    step 8 states the quantity in its first paragraph and the evaluation point it
    is read at in its second, so a paragraph-scoped check for the pair can never
    hold no matter how correct the prose is. Same shape as
    `test_skills_orchestrate.py`'s `step_body`, and normalised for the reason
    that module and both family modules normalise (399dba5: two phrase pins
    broke on an innocuous reformat).
    """
    section = section_body(load(SKILL), METHOD)
    start = section.index(f"\n{number}. **")
    try:
        end = section.index(f"\n{number + 1}. **", start)
    except ValueError:
        end = len(section)
    return re.sub(r"\s+", " ", section[start:end])


def test_the_contract_matches_the_stage_gate():
    skill = load(SKILL)
    assert skill.contract["stage"] == "score"
    assert set(skill.contract["schemas"]) == set(STAGE_ARTIFACTS["score"])


def test_it_writes_only_its_own_part_and_neither_coverage_file():
    """The coverage documents are `score-seal`'s output, not score's.

    Score still OWNS the status transitions and the hole justifications -- they
    are what its part carries -- but it no longer transcribes the matrices or
    publishes the pointer, because neither was ever judgment:
    `refs._check_matrix_arithmetic` already recomputed both from the rows, and a
    percentage that disagrees with the matrix under it is a failure no gate could
    catch from the document alone.

    An exact list rather than a membership check, because the interesting defect
    is an ADDITION: a contract that kept `coverage_round` beside `score_part`
    would satisfy any presence check of the new name while still claiming an
    artifact only the seal writes.
    """
    writes = load(SKILL).contract["writes"]
    assert writes == ["score_part"], writes


def test_it_invokes_dedupe_candidates():
    """The deterministic half of dedupe. A skill that eyeballs the scenario list
    instead is doing by judgment what code already did, and inconsistently.
    """
    assert "dedupe-candidates" in load(SKILL).contract["invokes"]
    assert "dedupe-candidates" in subcommand_names()


def test_it_has_the_five_sections():
    assert all(section in load(SKILL).headings for section in SECTIONS)


def test_it_names_every_coverage_verdict():
    """The verdict the orchestrator branches on. A skill that cannot name
    halted_no_progress cannot report a fixpoint, and the loop runs to the cap
    every time.
    """
    enum = _coverage_schema()["properties"]["verdict"]["enum"]
    body = load(SKILL).body
    missing = [verdict for verdict in enum if verdict not in body]
    assert not missing, f"the skill never mentions verdict(s) {missing}"


def test_it_enumerates_every_hole_reason_in_one_place():
    """Choosing a reason is a judgment `rb-propose` then reads as a worklist, so
    the four values have to be presented *together* with what each one means.

    **Strengthened: the whole-body version was vacuous.** Deleting Method step
    7's entire four-reason enumeration left all ten tests in this file green,
    because every one of the four leaks from somewhere else -- `blocked_by_gap`
    and `out_of_scope` from section 2's `rejected_reason` list, `blocked_by_gap`
    and `not_yet_attempted` from a refusal condition, `unreachable` from step 7's
    surrounding prose. The document mentioned the vocabulary in four places and
    defined it in none.

    Checked as a co-occurrence in one block of the Method section, which is the
    property and not the phrasing: the four may be reordered, reworded, or moved
    to another Method paragraph, and only splitting the enumeration up fails.
    Contrast `test_skills_propose.py`'s identically shaped check, which is a real
    guard against the same mutation purely because *that* document names the
    vocabulary once.
    """
    enum = _coverage_schema()["$defs"]["hole"]["properties"]["reason"]["enum"]
    owning = [block for block in blocks(METHOD) if all(reason in block for reason in enum)]
    assert owning, (
        f"no single Method block enumerates all four hole reasons {enum} together, so the "
        "skill mentions the vocabulary without ever defining it"
    )


def test_it_names_both_matrices_and_the_three_summary_fields():
    body = load(SKILL).body
    for name in (
        "capability_matrix",
        "goal_matrix",
        "hop_depths_present",
        "hop_depths_expected",
        "covered",
        "total",
        "pct",
    ):
        assert name in body, name


def test_it_states_the_status_values_it_may_set():
    """score owns every transition out of `proposed`. The three it may write are
    checked against refs' sets rather than a literal list.
    """
    from rubrica.refs import JUDGED_STATUSES

    body = load(SKILL).body
    assert "duplicate" in body and "duplicate_of" in body
    for status in sorted(JUDGED_STATUSES):
        assert status in body, f"the skill never mentions {status!r}"


def test_it_states_that_a_rejection_reopens_a_row():
    """The state test_refs_states.py's post-rejection case exists for. A skill
    that does not know a rejected scenario loses its credit leaves latest.json
    reporting a cell covered by a scenario the adversary threw out -- coverage
    confidently wrong with both gates green.

    **Strengthened: the whole-body version was vacuous.** `"rejected" in body`
    and `"recompute" in body.lower()` both hold from unrelated text -- `rejected`
    is a scenario status this document names a dozen times, and the recompute
    language appears in the arithmetic rules -- so deleting Invariant 5's rule
    body left all ten tests green with the invariant gone.

    Checked as a co-occurrence in one block of the Invariants section, because
    the rule is a conditional: the *credit being live* and the *recompute it
    obliges* are only actionable stated together, and each half read alone is
    satisfied by a document that has lost the other.
    """
    owning = [
        block
        for block in blocks(INVARIANTS)
        if "covered" in block and "rejected" in block and "duplicate" in block
    ]
    assert owning, (
        "no single Invariants block ties a covered row to a live credit and names both "
        "statuses that lose it"
    )
    assert any("recompute" in block.lower() and "hole" in block.lower() for block in owning), (
        "that invariant must state the remedy: recompute the row as uncovered and justify a hole"
    )


def test_output_says_the_matrices_are_computed_rather_than_written():
    """The prose half of `test_it_writes_only_its_own_part_and_neither_coverage_file`.
    The contract can say `writes = ["score_part"]` while the Output section still
    instructs a dispatched model to write both matrices and both coverage files,
    which is exactly the state this task closed -- `check_contract` validates
    names, so all three gates stayed green through it.

    Scoped to the block that names both matrices, and it must name `score-seal`
    in the same breath: a section that lists the matrices without saying who
    computes them reads as an instruction to write them.

    The negative pin is on `written twice`, the superseded instruction's own
    phrase. It is a *forbidden* substring rather than a required one, so the
    usual phrase-pin failure mode is inverted: rewording the rule cannot break
    it, and only reintroducing the double write can.
    """
    section = section_body(load(SKILL), OUTPUT)
    owning = [
        block for block in blocks(OUTPUT) if "capability_matrix" in block and "goal_matrix" in block
    ]
    assert owning, "the Output section never names the two matrices together"
    assert any("score-seal" in block for block in owning), (
        "the block naming both matrices must name score-seal as what computes them, or it "
        "reads as an instruction to write them here"
    )
    assert "written twice" not in section.lower(), (
        "the superseded double-write instruction is back in the Output section"
    )
    assert "score-part-0.1.json" in section, (
        "the Output section must name the shape of the one document this stage writes"
    )


def test_method_states_the_evaluation_point_a_new_cell_is_judged_from():
    """Method step 8 used to contradict itself, and `rounds.progress`' docstring
    recorded the contradiction rather than resolving it, because resolving a
    prompt's specification is not a code task's to do.

    The step stated a primary clause -- "covered now and were *not* covered
    before this round" -- and then restated it as "no live scenario from an
    earlier round credits them". The two diverge in the case the loop exists to
    handle: fold an earlier round's scenario into one of this round's claiming
    the same cell and no *live* earlier-round scenario credits it, so the
    restatement calls the cell new, which is the inflation the step's own hazard
    sentence warns about in the next breath.

    Resolved by naming the evaluation point the restatement left unstated:
    liveness is read as the dispatch *found* it, before its own rulings. So the
    property is that the block owning `new_cells_this_round` states that
    evaluation point, and the alternation is over three ways to say it rather
    than one phrase -- the requirement is the evaluation point, not its wording.
    """
    step = method_step(8)
    assert "new_cells_this_round" in step, (
        "Method step 8 is not the step that owns new_cells_this_round any more; this "
        "predicate is scoped to the wrong step"
    )
    assert re.search(
        r"as you found (them|it)|as you read it|before your own rulings", step, re.I
    ), (
        "the step must say which point in this dispatch a credit's liveness is read at; "
        "without it the round-tag derivation and the seal's baseline disagree on a fold"
    )
    assert re.search(r"\bfold\b", step, re.I), (
        "the step must name the case the two readings diverge in, or the evaluation point "
        "reads as a detail rather than as the rule"
    )
    method = section_body(load(SKILL), METHOD)
    assert "no live scenario from an earlier round credits them" not in method, (
        "the restatement that contradicts this step's own hazard sentence is back"
    )


def test_output_says_a_re_dispatch_must_restate_the_rulings_it_replaces():
    """The one way this stage can silently lose work it already did, and it
    arrived with the split rather than existing before it.

    `03-score/round-<N>.json` is one document per round and `_apply_rulings`
    folds the score parts onto scenarios whose parts all say `proposed`, so the
    sealed statuses come from the score parts and from nothing else. A
    re-dispatch after an `rb-challenge` rejection scores the same round -- the
    round it derives is the highest round tag among the scenarios, which no new
    proposal has moved -- so its part *replaces* the first dispatch's. Carrying
    only the new rejection reverts every promotion that round made to
    `proposed`, and a `proposed` scenario is not instantiated, not emitted and
    not counted: `refs.check_instances` would only ever report it after gate 3.

    Scoped to the block that states the replacement, and required to state the
    remedy in the same block: the hazard without the restatement rule is a
    warning a dispatched model cannot act on, which is this project's own test
    for a decorative rule.
    """
    owning = [
        block
        for block in blocks(OUTPUT)
        if re.search(r"re-dispatch", block, re.I) and re.search(r"rewrite|replace", block, re.I)
    ]
    assert owning, "the Output section never says a re-dispatch replaces this round's part"
    assert any(
        re.search(r"restate", block, re.I) and re.search(r"still in force|already", block, re.I)
        for block in owning
    ), (
        "that block must say the replacement part has to restate the rulings still in force, "
        "or the hazard is stated with no action a dispatched model can take"
    )
