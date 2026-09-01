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


def _sentences(text: str) -> list[str]:
    """Whitespace-normalised text split into sentences.

    A sentence, not a fixed-width character window, for the reason
    `gate_step` below gives: a window admits whatever the *next* sentence
    happens to say, and this file's prose is long enough that a 300-character
    radius reaches two paragraphs. The boundary is a period followed by
    whitespace, optionally through a closing `**` -- so a bolded lead-in ends
    a sentence -- which leaves `00-catalogue.json` and `manifest.json` intact
    because the character after their period is a letter.
    """
    return [s for s in re.split(r"\.(?:\*\*)?\s", text) if s.strip()]


# Ways English forbids something, for the interface-gate predicate below. A set
# rather than three literals inline, because the predicate's brittleness was
# measured: "and running `validate --stage synthesise-interfaces` is forbidden to
# you" is meaning-preserving and reded the earlier {must not, do not, never}
# spelling, which is the same reword-brittleness CLAUDE.md warns about.
#
# Widened, but not to bare "not", and the ceiling is measured rather than guessed.
# The prose this guards is B3's, not B4's -- B4 halts on a blocking gap and has
# nothing to do with synthesis, and a maintainer who blanks it, sees green and
# concludes the guard is vacuous has measured the wrong band. With B3's prohibition
# paragraph blanked (1132 characters) exactly one prose sentence still carries the
# command -- "when it printed at least one path, gate it with `rubrica validate
# --stage synthesise-interfaces --run <run>`, then `rubrica check-refs --run
# <run>`" -- and it already satisfies the empty-case half through "printed". So the
# prohibition half is the only thing discriminating there, and every token below is
# absent from that sentence deliberately: none of "gate", "then", "when", "path" or
# "run" may ever join this set, however natural it reads.
PROHIBITIONS: frozenset[str] = frozenset(
    {
        "must not",
        "do not",
        "never",
        "not run",
        "forbidden",
        "forbids",
        "prohibited",
        "refuse",
        "skip",
        "avoid",
    }
)


def prose_sentences(text: str) -> list[str]:
    """`text`'s sentences with every fenced code block removed first.

    The Method section opens with the whole-run block, which is fenced, ~2,900
    characters long, and contains almost no `. ` -- so `_sentences` returns the
    entire block as **one** pseudo-sentence. Any co-occurrence predicate over
    sentences is therefore satisfiable by that block alone, which is not a check of
    the prose at all.

    Measured, and it is not hypothetical: the interface-gate predicate below was
    green with its own paragraph deleted the moment the block's synthesis row was
    annotated with `if it printed nothing`, because the block then carried the
    command, `never yours`, and `printed` inside that one pseudo-sentence. Reading
    prose only is what makes the predicate about the prose.

    Not folded into `method_body`, deliberately, and the example is measured rather
    than assumed: folding it in reds
    `test_it_records_each_stage_and_each_decision`, whose `record-stage --run` needle
    exists exactly once in the whole section, at `SKILL.md:402`, inside a fence --
    *the Method must invoke record-stage*. That predicate is satisfied **by** the
    block, so stripping the block there would make it vacuous in the other
    direction.

    Not the stage roster, which is what an earlier draft of this docstring claimed:
    zero of its needles are block-only. Every `rb-*` name and every
    `CODE_ONLY_STAGES` name also appears in the prose bands, so
    `test_it_names_every_stage_it_dispatches` is unaffected by stripping. Measured
    by folding the strip into `method_body` and running the module: two tests red,
    that one not among them.
    """
    return _sentences(re.sub(r"```.*?```", " ", text, flags=re.DOTALL))


def whole_run_block() -> str:
    """The fenced whole-run block that opens the Method section.

    Its own reader, because the block and the prose are two audiences of one
    instruction and each can drift from the other: the block is framed as "every
    `rubrica` command shown is one you actually run", so a command shown there
    unconditionally *is* an instruction to run it, whatever a later band says.
    prose_sentences above exists to read everything except this; this reads only it.
    """
    match = re.search(r"```\n(.*?)```", method_body(), re.DOTALL)
    assert match, "the Method section no longer opens with a fenced whole-run block"
    return match.group(1)


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


def step_body(method: str, label: str) -> str:
    """One numbered Method step's text, from its `**BN.` marker to the next one.

    Same reasoning as `gate_step` above, for the walk's steps rather than its
    gates, and measured rather than assumed. Every reconcile rule below lives in
    B3, and **two** of the four tests stay green with their own B3 paragraph
    deleted if they are asserted against the whole Method section instead: the
    concurrency cap, satisfied by the one-block walk's own `at most 3 members
    concurrently` marker, and the denominator flag, satisfied by B6's amendment
    rule. Both are real prose about a different place in the run, which is
    exactly the borrowing a scoped slice prevents.

    The count is two rather than three, corrected after measuring each test
    whole instead of only its regex half: the check-refs timing test *would*
    leak on its `after every member` clause, which B9 states verbatim for
    `rb-challenge`, but it also requires the literal `check_contradiction_parts`
    and that identifier appears exactly once in the file -- in the paragraph
    being deleted. So that one goes red either way, and the scoping is
    belt-and-braces for it rather than load-bearing. Recorded rather than
    trimmed to the two that need it, because the next rule added to B3 has no
    guarantee of carrying its own unique identifier.
    """
    hit = re.search(rf"\*\*{label}\.", method)
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

    `batches` joined it for the same shape of reason once `propose` became a
    fan-out: the roster of that fan-out is the batch ids `propose-batches` mints
    in code and writes to `02-batches/round-N.json`, a member cannot be
    dispatched without being told which one is its own, and nothing else
    surfaces those ids. What the orchestrator may take from that document is
    still only the ids -- a batch's `hole_refs` are the member's to read out of
    the same file -- but the read itself is a requirement, not a convenience.

    Set equality rather than `<=`: `check_contract` only verifies each entry is
    a public `RunPaths` attribute, so both dropping `verdict` again and quietly
    widening this list to an artifact no requirement needs would otherwise pass
    every check in the build. `report` is deliberately absent -- smoke's
    non-healthy verdict arrives as an exit-1 finding, so the gate covers it.
    """
    assert set(load(SKILL).contract["reads"]) == {
        "manifest",
        "world_model",
        "batches",
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
        # The loop's three code steps. Without propose-batches there is no
        # fan-out roster, without propose-seal no scenario list for score to
        # read, and without score-seal no coverage document to branch on -- so
        # an orchestrator that does not know they exist cannot run a round at
        # all, which is exactly what this set is for.
        "propose-batches",
        "propose-seal",
        "score-seal",
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


def test_the_whole_run_block_shows_the_interface_gate_as_conditional():
    """The block must not instruct the command its own prose forbids.

    `validate --stage synthesise-interfaces` accuses a run whose target declares no
    tool (see the predicate above and
    test_the_interface_gate_over_a_run_with_no_services_names_the_run_root), so B3
    forbids it there. The block is framed as "every `rubrica` command shown is one
    you actually run" and nothing in it says the bands override it -- so a row
    showing that gate unconditionally contradicts the prose, and an orchestrator
    that reads the block and skims the band still spends its one repair attempt on
    a correct run. This is the shape `propose-batches` avoids by carrying no
    `validate` row at all, only `# no closable holes -> leave the loop`.

    Asserted over the block alone rather than the section: the prose predicate above
    deliberately strips fenced blocks, so without this nothing checks the block at
    all -- and the block is where this contradiction was introduced.
    """
    lines = [
        line for line in whole_run_block().splitlines() if "validate --stage synthesise" in line
    ]
    assert len(lines) == 1, f"expected one gate row for synthesis, found {lines}"
    assert lines[0].lstrip().lower().startswith("if "), (
        "the block shows `validate --stage synthesise-interfaces` unconditionally: "
        f"{lines[0]!r}. Every command in this block is one the orchestrator runs, so "
        "the condition has to be visible here and not only in B3"
    )
    skips = [
        line
        for line in whole_run_block().splitlines()
        if ("printed nothing" in line or "no path" in line or "no service" in line)
        and ("skip" in line or "not" in line)
    ]
    assert skips, "the block never shows what to do when synthesis printed no path"


def test_the_orchestrator_disclaims_survey_triage_and_gate_zero():
    """`survey` and the triage family both precede intake, and gate 0 precedes
    the orchestrator's own dispatch entirely -- it never runs `rubrica survey`,
    never dispatches any triage pass, and never holds gate 0 itself. A reader
    of this file needs the whole pipeline in view, not just the stages this
    skill dispatches, so the Method section must say where its own walk picks
    up *and* that none of what precedes it is the orchestrator's.

    Scoped to one sentence, and not by accident. Task 14 removed the
    monolithic `triage` stage, which made the predecessor's `"triage" in body`
    vacuous overnight: `triage` is a substring of all five `triage-*` names,
    and the roster test above already requires every one of them somewhere in
    this section, so the token could no longer be attributed to the
    disclaimer. Requiring the disclaiming *sentence* to carry it restores the
    attribution. Deliberately tolerant of how the family is spelled there --
    five names, or one "the triage family" -- because that is editorial, while
    the disclaimer itself is not.
    """
    sentences = _sentences(_norm(method_body()))
    disclaimers = [s for s in sentences if "never" in s or "not yours" in s]
    assert disclaimers, "the Method section disclaims nothing at all"
    assert any("rubrica survey" in s and "triage" in s and "gate 0" in s for s in disclaimers), (
        "no single sentence disclaims survey, the triage family and gate 0 together"
    )


def test_it_forbids_the_interface_gate_when_synthesis_printed_no_path():
    """The gate that accuses a correct run, and the one instruction that closes it.

    `01-interfaces/` holds one document per service, so a target whose corpus
    declares no tool produces none -- `rb-reconcile-services` is instructed to write
    `services: []` for one, and synthesis then exits 0 having printed nothing.
    `validate --stage synthesise-interfaces` over that run exits 1 against the run
    root ("produced no interface artifact"), which would send this skill to spend
    its single repair attempt on a pass that would honestly write `services: []`
    again. Measured before this prose existed, on a run with every `tool` claim
    removed: synthesis 0 with empty stdout, `validate --stage reconcile-services` 0,
    `check-refs` 0, this gate 1.

    Scoped to one sentence of the Method section, and required to carry the
    prohibition together with the command it prohibits: `synthesise-interfaces`
    appears in that section several times by necessity (the dispatch table, the
    exit-code paragraph), so an unscoped check would be satisfied by prose that
    never states the condition. Tolerant of how the empty case is spelled --
    "printed nothing", "no path", `services: []` -- and, since the fix round that
    measured it, equally tolerant of how the prohibition is spelled: PROHIBITIONS
    above holds the vocabulary, and its comment records both why it was widened
    ("is forbidden to you" reded the earlier three-token spelling) and the ceiling
    on widening it further (with B3's prohibition paragraph blanked, one prose
    sentence still carries the command *and* satisfies the empty-case half, so the
    prohibition half is the whole discriminator there).

    The band is **B3**, where synthesis is run, and every citation here says so.
    Measured, because the four that used to say B4 were citing a measurement:
    blanking all 2,130 characters of B4 leaves this test and the block test green,
    while removing B3's synthesis prose fails this one.

    The rule is B6 step 1's, one band earlier, and that step's own version is pinned
    by test_the_batches_gate_over_a_run_with_no_plan_names_the_run_root in
    tests/unit/test_validate.py rather than here.
    """
    sentences = prose_sentences(_norm(method_body()))
    assert any(
        "validate --stage synthesise-interfaces" in s
        and any(prohibition in s for prohibition in PROHIBITIONS)
        and ("print" in s or "no path" in s or "services: []" in s)
        for s in sentences
    ), (
        "no single sentence of the Method section's prose forbids "
        "`validate --stage synthesise-interfaces` AND says which run it applies to"
    )
    # Both halves in one sentence, and over prose rather than the whole section:
    # two vacuities were measured here, one after the other. Splitting this into
    # two assertions let the fenced block satisfy the command-plus-prohibition half
    # alone (`-- not yours`, `never yours`); and once the block's synthesis row was
    # annotated `if it printed nothing`, the block satisfied all three tokens at
    # once and the predicate passed with its own paragraph deleted. prose_sentences
    # is the fix for the second, one co-occurrence for the first.


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
    "once" and "halt" both occur many times over in unrelated prose -- "once"
    carries the dispatch protocol's own advice and the re-seed budget, and "halt"
    is what five different rules do -- and "one repair" is in the frontmatter
    `description:` line, so deleting the whole bounded-repair rule left all
    eleven tests green.

    The two phrases this paragraph used to quote, and the count beside them, were
    dropped when the propose fan-out landed. One of them lived in the paragraph
    arguing that propose could not be a fan-out, which is gone, so the count was
    no longer true and the quotation sent a reader looking for text that is not
    there -- and the other is hard-wrapped in the skill, so grepping for it fails
    even though the sentence is still on the page. Neither was load-bearing: the
    measurement's point is that the tokens are common, not how common.

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


def test_b3_caps_the_contradict_fan_out_at_three_concurrent_members():
    """The widest fan-out in the run, against a shared gateway. Envoy returns
    `upstream connect error ... reset reason: connection timeout` intermittently
    at five or more concurrently streaming dispatches, and one to three was
    measured clean, so the cap is a mitigation the orchestrator has to carry --
    nothing in the artifacts records that it was dropped.

    Scoped to B3 and stated as an alternation rather than one phrase: the
    property is that the step names a bound of three on concurrent members, not
    that it spells the bound "at most three", so a meaning-preserving reword
    ("no more than 3 at a time") must stay green while deleting the rule goes
    red.
    """
    b3 = step_body(method_body(), "B3")
    assert b3, "B3 is not a labelled step in the Method section"
    assert re.search(
        # The bound, however it is spelled, then a word for simultaneity within a
        # sentence of it. The first draft of this pattern listed "never more than"
        # as one fixed phrase and went red on the reword "Never dispatch more than
        # 3 ... in parallel", which preserves the rule exactly -- the negation and
        # the comparative can have words between them, so the pattern allows that
        # rather than enumerating the ways an author might separate them.
        r"(?:at most|(?:no|not|never)\b[^.]{0,40}\bmore than|limit\w*[^.]{0,30}\bto|"
        r"cap\w*[^.]{0,30}\b(?:at|to))\s*(?:three|3)\b"
        r".{0,120}(?:at a time|concurrent|at once|in parallel|side by side)",
        b3,
        re.I | re.S,
    ), "B3 must bound the rb-reconcile-contradict fan-out to three concurrent members"


def test_b3_separates_the_concurrency_cap_from_the_reset_the_split_addresses():
    """Two different gateway failures, and the whole risk is a later reader
    "fixing" one by reasoning about the other: capping concurrency does not
    shorten a dispatch, and shortening a dispatch does not make the gateway
    tolerate more of them at once. So B3 has to say they are different, not just
    happen to describe both.
    """
    b3 = step_body(method_body(), "B3")
    assert re.search(r"different failure|not the same failure|unrelated to", b3, re.I), (
        "B3 must say the concurrency cap and the idle reset are different failures"
    )
    assert re.search(r"idle reset|zero bytes|zero-byte", b3, re.I), (
        "B3 must name the reset the pass split addresses, or the distinction has no second half"
    )


def test_b3_defers_the_contradict_check_refs_until_every_member_has_finished():
    """Exactly B9's rule, for the run's other fan-out with a run-global checker:
    `refs.check_contradiction_parts` reports every subject with no part from the
    moment `01-contradictions/` exists, so mid-fan-out findings are about members
    still in flight. Pinned on the checker's own function name, which is a code
    identifier rather than a phrase, plus the timing rule -- either alone would be
    satisfiable by prose that named the mechanism without stating when to run it.
    """
    b3 = step_body(method_body(), "B3")
    assert "check_contradiction_parts" in b3, "B3 must name the checker whose timing this is"
    assert re.search(
        r"check-refs\b.{0,120}(only )?(after|once) (every|all) member",
        b3,
        re.I | re.S,
    ), "B3 must defer check-refs until every contradict member has finished"


def test_b3_invokes_the_seal_as_code_and_reserves_the_denominator_flag():
    """`reconcile-seal` is code, not a dispatch, and it takes the number rather
    than inferring it precisely so the denominator cannot move without a decision
    behind it. An orchestrator that passes `--denominator-version` by habit hands
    back the silent bump B6's rule exists to prevent, so the flag's condition has
    to be stated where the seal is invoked, not only where the amendment rule
    lives.
    """
    b3 = step_body(method_body(), "B3")
    assert "rubrica reconcile-seal --run <run>" in b3, "B3 must invoke the seal as code"
    assert re.search(
        # Either order. Proximity is the property -- the flag named beside the
        # decision it costs -- and which clause an author puts first is not.
        r"--denominator-version.{0,400}decisions\.md|decisions\.md.{0,400}--denominator-version",
        b3,
        re.I | re.S,
    ), "B3 must tie --denominator-version to a decision recorded in decisions.md"
