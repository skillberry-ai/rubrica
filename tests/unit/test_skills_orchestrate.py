"""rb-orchestrate's contract, and the control-flow rules it must state.

The orchestrator is the one skill whose defects are silent in a *successful*
run: an orchestrator that passes extra context into a dispatch, or retries three
times, or treats an exit 2 as repairable, produces artifacts that all validate.
So these checks are about the rules being present in the prompt, and the live
exercise is a whole-pipeline run.
"""

from __future__ import annotations

import re

from rubrica.cli import subcommand_names
from rubrica.paths import STAGES
from rubrica.skills import (
    CODE_ONLY_STAGES,
    ORCHESTRATOR,
    SECTIONS,
    load,
    section_body,
    skills_dir,
)

SKILL = skills_dir() / ORCHESTRATOR / "SKILL.md"
METHOD = "3. Method"


def _norm(text: str) -> str:
    """Whitespace-normalised, so a reflow does not break a phrase pin.

    399dba5 fixed exactly this in the extract/reconcile prose tests; the same
    risk applies here, so the two Task 20 predicates below use it too.
    """
    return re.sub(r"\s+", " ", text.lower())


def method_body() -> str:
    """The `## 3. Method` section only.

    Six of the assertions below scope to this rather than to `skill.body`,
    which `load()` sets to the *entire file* -- frontmatter and mandatory
    contract block included. Measured during Task 13's fix round: the
    frontmatter `description:` line alone satisfied the three-things test, and
    the contract block's own `invokes` list alone satisfied two thirds of the
    record-stage test. Section 3 is where the rules the docstrings name have to
    live, so it is what they are asserted against.
    """
    return section_body(load(SKILL), METHOD)


def gate_step(method: str, number: str) -> str:
    """The text of one human-gate step: its label up to the next step marker.

    Scoped to the step rather than to a fixed-width window after the label, so
    the assertion below cannot be satisfied by an artifact named in the
    *following* step -- which is what a lookahead window admits as soon as a
    stubbed gate carries a line or two of filler prose.
    """
    hit = re.search(rf"Human gate {number}", method)
    if hit is None:
        return ""
    rest = method[hit.end() :]
    stop = re.search(r"\n\n\*\*[AB]\d", rest)
    return rest[: stop.start()] if stop else rest


def test_it_declares_no_stage_because_it_dispatches_them():
    contract = load(SKILL).contract
    assert "stage" not in contract
    assert "schemas" not in contract


def test_it_writes_the_decisions_log():
    assert load(SKILL).contract["writes"] == ["decisions"]


def test_it_declares_every_artifact_its_branches_read():
    """Pinned by set equality under a Task 13 ruling: `verdict` was added to
    `reads` because rule 8's three-way branch *is* the verdict value and no
    gate surfaces it in time (`validate` only schema-checks those files,
    `check-refs` never compares the value to anything, and `emit` reports a
    `re-seed` only at stage 6 and a `reject` not at all).

    Set equality rather than `<=`: `check_contract` only verifies each entry is
    a public `RunPaths` attribute, so both dropping `verdict` again and quietly
    widening this list to an artifact no requirement needs would otherwise pass
    every check in the build. `report` is deliberately absent -- smoke's
    non-healthy verdict arrives as an exit-1 finding, so the gate covers it.
    """
    assert set(load(SKILL).contract["reads"]) == {
        "manifest",
        "world_model",
        "scenarios",
        "coverage_latest",
        "verdict",
    }


def test_it_has_the_five_sections():
    assert all(section in load(SKILL).headings for section in SECTIONS)


def test_it_invokes_every_subcommand_the_loop_needs():
    """Not every subcommand -- compare-gold, diff-runs and sample-for-review are
    measurement tools the orchestrator does not run. But every one it does
    declare must be real, which check_contract already enforces; this pins the
    ones the loop cannot work without.
    """
    invokes = set(load(SKILL).contract["invokes"])
    required = {
        "check-skills",
        "validate",
        "check-refs",
        "record-stage",
        "decide",
        "dedupe-candidates",
        "emit",
        "smoke",
    }
    assert required <= invokes, f"missing: {sorted(required - invokes)}"
    assert invokes <= set(subcommand_names())


def test_it_names_every_stage_it_dispatches():
    """Derived from STAGES, so adding a stage fails here until the loop mentions
    it. The two code-only stages are named as well: intake mints the run and
    smoke scores it, and an orchestrator that does not know they exist skips them.

    Strengthened during Task 13's fix round: scoped to the Method section,
    because against the whole body the `smoke` half was satisfied by the
    mandatory contract block's own `invokes` list -- deleting every prose
    mention of smoke left it green. Same two-sides-from-one-source shape as the
    record-stage test below. `intake` and the seven `rb-*` names did require
    real prose even before the scoping.
    """
    method = method_body()
    for stage in STAGES:
        if stage in CODE_ONLY_STAGES:
            assert stage in method, f"the loop never mentions the code stage {stage!r}"
        else:
            assert f"rb-{stage}" in method, f"the loop never dispatches rb-{stage}"


def test_the_orchestrator_dispatches_survey_triage_and_holds_gate_zero():
    """`survey` and `triage` both precede intake, and gate 0 precedes the
    orchestrator's own dispatch entirely -- the orchestrator never runs
    `rubrica survey`, never dispatches `rb-triage`, and never holds gate 0
    itself. But a reader of this file needs the whole pipeline in view, not
    just the seven stages this skill dispatches, so the Method section must
    say where its own walk picks up."""
    body = _norm(method_body())
    assert "survey" in body and "triage" in body
    assert "gate 0" in body


def test_the_orchestrator_knows_gate_zero_decides_what_the_run_can_know():
    """The reason this gate is different in kind from 1-3: a model that both
    selects the inputs and ratifies the selection makes triage unfalsifiable.

    Scoped to the whole file rather than the Method section, because the
    explanation of *why* gate 0 differs is framing for the reader, not a step
    in the walk -- it can live anywhere the prose puts it.
    """
    body = _norm(load(SKILL).body)
    assert "what the run can" in body


def test_it_states_all_three_exit_codes_and_what_each_means():
    """The branch. An orchestrator that treats 2 as repairable spends its one
    repair attempt on a misconfigured harness and then halts anyway, with the
    real cause buried.

    Strengthened during Task 13's fix round. The original was
    `all(c in body for c in "012")` plus `"exit" in body` and
    `"misconfigur" in body`: measured, "0"/"1"/"2" occur 34/46/36 times in a
    conforming file (section numbers, `0.1`, `02-scenarios.json`) and "exit" 21
    times, so deleting the entire exit-code statement left all eleven tests
    green on the surviving "misconfigured" in refusal condition 3.

    Each code must now be named *as an exit code* beside its own meaning. The
    first form shipped anchored on the bold `| **0** |` table cell, which bound
    the property and then over-coupled to the markup: reformatting the table
    into flowing prose -- an edit that fully preserves the rule -- broke a
    still-conforming file. Measured in fix round 2, the `exits? N` anchor is
    better on both axes at once: it cuts the Method-section search space from
    26 and 18 bare digit occurrences for codes 1 and 2 down to 6 and 6, it goes
    False for **all three** codes when A3 is deleted, and it stays True through
    a prose rewrite of the same rule.

    `stdout` rather than `findings` for exit 1, deliberately: the branch table's
    own "exits 1 | Re-dispatch that stage once, findings appended" row would
    otherwise satisfy this code on its own, and one leaking code in a
    three-code assertion is one code with no gate on it.
    """
    method = method_body()
    for code, meaning in (("0", "clean"), ("1", "stdout"), ("2", "misconfigur")):
        assert re.search(rf"exits?[- ]{code}\b.{{0,140}}{meaning}", method, re.I | re.S), (
            f"exit {code}'s meaning is not stated in the Method section"
        )


def test_it_states_the_repair_is_bounded_to_one_attempt():
    """Strengthened during Task 13's fix round. The original was
    `("once" in body or "one repair" in body) and "halt" in body`: measured,
    "once" occurs 13 times in unrelated prose ("get this right once", "two
    members appending at once"), "halt" 43 times, and "one repair" is in the
    frontmatter `description:` line -- so deleting the whole bounded-repair
    rule left all eleven tests green.

    What has to be stated is the bound itself: the *same* stage, re-dispatched
    *once*, and no third attempt.
    """
    method = method_body()
    assert re.search(r"(same stage|re-dispatch).{0,80}once", method, re.I | re.S), (
        "the Method must say the same stage is re-dispatched once"
    )
    assert "third" in method.lower(), "the Method must rule out a third dispatch"


def test_it_states_the_three_things_a_dispatch_receives():
    """The contract. An orchestrator that threads context through has removed
    the isolation the fan-out design was chosen for, and every artifact still
    validates.

    Strengthened during Task 13's fix round, and this was the worst of the
    seven: the original three substring checks were **all satisfied by the
    frontmatter `description:` line alone**, because `load()` sets `body` to the
    whole file. It constrained no prose at all, and deleting every statement of
    the rule left all eleven tests green.

    The three now have to be named together, in one Method passage, in order.
    """
    assert re.search(r"run directory.{0,120}stage name.{0,120}skill", method_body(), re.I | re.S), (
        "the Method must name the run directory, the stage name and the skill together"
    )


def test_it_names_the_three_human_gates_and_the_no_gate_flag():
    """Strengthened during Task 13's fix round. The original was
    `"--no-gate" in body and body.lower().count("gate") >= 4`: measured,
    "gate" occurs 69 times in a conforming file because it is this project's
    word for validate and check-refs ("gate with", "the reachability gate",
    "both gates"), and the frontmatter contributes two on its own. Deleting all
    three human gates and A7 entirely left all eleven tests green on one
    surviving `--no-gate` mention.

    Strengthened again in fix round 2. The first version required only that
    three distinct "Human gate N" labels exist, which is an improvement on a
    "gate" count and still not the property: measured, a file reducing B5, B7
    and B10 to bare `**B5. Human gate 1.**` stubs passed it, so zero gates
    could be *described*. Each label must now sit in a step that names what is
    reviewed there -- an artifact of the run.

    What this does and does not bound, stated so the docstring does not outrun
    the predicate: it requires each gate to name the artifact presented, and it
    does **not** check that the step explains the judgment to be made there
    (gate 1's "resolve contradictions, rule on gaps"). That much rests on spec
    review and the live exercise. The artifact reference is scoped to the gate's
    own step, so a stub cannot borrow the next step's.
    """
    method = method_body()
    assert "--no-gate" in method
    for number in ("1", "2", "3"):
        step = gate_step(method, number)
        assert step, f"human gate {number} is not identified in the Method section"
        assert re.search(r"`[^`\n]+\.json`|verdicts", step), (
            f"human gate {number} does not name what is reviewed there"
        )


def test_it_states_that_a_rejection_does_not_loop_back_to_propose():
    """Deferred on purpose: looping after instantiation makes run cost unbounded.
    An orchestrator that loops instead of reporting an honest hole turns a
    bounded run into an open-ended one.

    Strengthened during Task 13's fix round. The original was
    `"reject" in body and "hole" in body`: measured, "reject" occurs 27 times
    and "hole" 18 in ordinary coverage vocabulary, the predicate never
    mentioned `propose` at all, and deleting both the reject branch and the
    whole no-loop-back rule left all eleven tests green.

    The deferral and its consequence must be stated together: no return to
    propose, and an honest hole instead.
    """
    assert re.search(
        r"(does not|never).{0,60}(loop back|return).{0,40}propose.{0,300}hole",
        method_body(),
        re.I | re.S,
    ), "the Method must say a rejection does not go back to propose, and leaves a hole"


def test_it_records_each_stage_and_each_decision():
    """Strengthened during Task 13's fix round. Two of the original three
    predicates were satisfied by the **mandatory contract block**: `invokes`
    declares both `record-stage` and `decide`, and `check_contract` requires
    that block to exist -- so deleting both steps entirely left all eleven
    tests green on §2's lone `skill_sha256` mention. Two-sides-from-one-source
    inside a single prompt, where one side is a structure the plan itself
    mandates.

    Both commands must now be *invoked* in the Method, with the flags a caller
    actually needs, and the digest named where the recording step is. Note the
    fix that made the third assertion satisfiable at all: `skill_sha256` was
    moved into the `record-stage` step, rather than the predicate being scoped
    around its absence.
    """
    method = method_body()
    assert "record-stage --run" in method, "the Method must invoke record-stage"
    assert "decide --run" in method, "the Method must invoke decide"
    assert "skill_sha256" in method, "the recording step must name the digest it writes"
