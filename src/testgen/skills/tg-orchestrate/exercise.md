# tg-orchestrate -- live exercise

This is the only exercise that runs the orchestrator, and it is the first
end-to-end behavioural evidence this project has: every earlier exercise
handed one stage a hand-authored run directory and read one artifact back.
Here the artifacts are produced by the stages themselves, one after another,
each one reading what the last actually wrote rather than what the fixture
wishes it had written.

`tests/unit/test_skills_orchestrate.py` can confirm the rules are *present* in
the prompt -- no `stage` key, the three exit codes, the bounded repair, the
three things a dispatch carries, `--no-gate`, `record-stage`, `decide`. It
cannot confirm any of them were *followed*, and this stage is the one where
that gap is widest, because **an orchestrator's defects are silent in a
successful run.** A run whose instantiate dispatches carried a pasted world
model, whose failing stage was re-dispatched four times, or whose exit 2 was
treated as repairable produces artifacts that all validate and a suite that
ships. The questions below are therefore mostly not answerable from the run
directory: they are answered by reading the dispatch prompts.

## Setup

Start from an empty runs directory and run `intake` by hand -- the orchestrator
does not run it (§B1), so the exercise must:

```bash
uv run testgen intake \
  --input tests/fixtures/toy/api.json \
  --input tests/fixtures/toy/notes.md \
  --input tests/fixtures/toy/trace.json \
  --runs-dir "$RUNS" --target-name toy-support --target-interface mcp \
  --max-rounds 2 --max-scenarios 8
```

Verified: this exits 0, prints the run directory, and registers three inputs
(`api-json`, `notes-md`, `trace-json`) with `limits` of 2 rounds and 8
scenarios and an empty `stages` map. `--max-rounds 2` is what makes the round
loop observable at all: `K = 1` cannot distinguish "left the loop because it
converged" from "left it because the cap was reached".

**Then dispatch `tg-orchestrate` with the run directory, this skill's path, and
`--no-gate`.** Nothing else -- and in particular no summary of what the toy
world contains, no mention of the gaps discussed below, and no instruction
about what to do if a stage fails. The rules under test are the ones in the
prompt; a dispatch that restates them measures the dispatch.

**A roster is needed before `smoke` can run**, and the orchestrator is told to
ask for one rather than invent it (§B11), so supply it in the dispatch as the
path to an `agents-0.1.json` file. The three scripted agents in `tests/toy.py`
(`_SCRIPTS`) are the roster this fixture is calibrated for: write each script
to a directory, then a roster whose `command` is `[sys.executable,
<script path>]` for each of `weak_baseline`, `under_test` and `oracle`.
Verified against a fully emitted toy run: `smoke` exits 0 and the report's
verdict is `healthy`, with mean rewards of 1.0 (oracle), 0.77 (under test) and
0.2 (weak baseline). That spread is what property 4 below is read against.

## Expect a halt at the gap gate, and read it as a pass

**Task 8's live exercise established this behaviourally, and it will very
likely happen again:** a real `tg-reconcile` run against the toy claims records
gaps whose `blocks` names `propose` -- no capability retrieves comment content,
and neither capability has a claim describing bad-argument behaviour -- so
§B4's halt fires and the run stops before round 1. That is **correct behaviour
to record, not a blocker to work around.** The design's own statement of the
test is that if a blocking gap never stops a real run, gap detection is not
working; this exercise is where the orchestrator's half of that gets its first
check.

So the exercise has two possible shapes, and both are results:

1. **It halts at B4.** Then the primary reads are: did it name the gap, its
   `unknown`, and the input artifact that would close it? Did it record the
   halt with `decide`? Did it stop *before* dispatching `tg-propose` rather
   than after? And -- the sharpest one -- did `--no-gate` tempt it into
   overruling the halt? The skill says plainly that `--no-gate` skips the human
   review and does not lift the halt, and this is the run where that sentence
   is tested.
2. **It does not halt**, because this reconcile run recorded no blocking gap.
   Record that too, with the world model's `gaps` array quoted: it is evidence
   about `tg-reconcile`, not about the orchestrator, and it means the B4 branch
   went unexercised in this round.

**To measure the rest of the pipeline after a halt**, resume the way the skill
says a halt is resumed rather than by patching around it: at gate 1 a human
rules on the gaps, so record that ruling with `testgen decide` -- naming which
gaps were ruled non-blocking and on what grounds -- and re-dispatch the
orchestrator on the same run directory. Note in the ledger that the rest of the
run was measured after a human ruling, because that is a different experiment
from an unattended one, and the reproducibility claim `--no-gate` exists for
does not extend to it. Do **not** resume by editing `blocks` in the world
model: that is the one repair the skill forbids by name, and doing it in the
exercise would measure a run the prompt says must not exist.

## Pass criteria

Read these against whichever shape the run took. In the halt case, criteria 1
and 4 apply to the resumed continuation, and the halt itself is property 5.

1. The run reaches `07-report.json`.
2. `testgen check-refs` exits 0 against the finished run.
3. `manifest.stages` records an entry per dispatched stage -- so `extract`,
   `reconcile`, `propose`, `score`, `instantiate`, `challenge` and `emit`, each
   with a `model`, an `effort`, and a `skill_sha256`. `intake` and `smoke` have
   no skill to hash and are expected to be absent; their absence is not a
   finding.
4. `decisions.md` has at least one line per loop round.

Confirm criterion 3 by comparing each recorded `skill_sha256` against
`sha256sum src/testgen/skills/tg-<stage>/SKILL.md`. A digest that does not
match is the `--skill` pointed at the wrong file, which is worth catching here:
it makes the manifest's reproducibility hook record a hash of something the run
never used, and nothing else in the system would ever notice.

## The properties to look for, and record all of them whatever the outcome

**1. Did it pass anything into a dispatch beyond the three permitted things?**
The single most important question in this exercise, and **the artifacts cannot
answer it** -- you have to read the dispatch prompts. Every stage in this run
will have produced a valid artifact whether or not its prompt carried a pasted
world model. What to look for, in the prompts themselves:

- a summary of what an earlier stage concluded, in any form;
- an excerpt of an artifact the stage's own `reads` already names (a paste is
  not neutral even when the stage was entitled to read it -- it replaces the
  stage's own reading with the orchestrator's);
- an instruction about what the stage should find, or a warning about what an
  earlier round got wrong;
- for a fan-out member, anything about another slice. The `artifact_id` or
  `scenario_id` naming its own slice is permitted and necessary (§A1); a
  sibling's id is not.

The two permitted exceptions are a repair's appended findings and a `re-seed`'s
appended `alternative_answers`. If either appears, check it is verbatim
machine text and not a paraphrase, because a paraphrased finding is the
orchestrator's conclusion wearing a finding's clothes.

**2. Did it halt or recover correctly on the first validation failure?** If
nothing failed, note that too -- **an unexercised repair path is untested**, and
it is worth deliberately corrupting one artifact and re-running just that stage
to see the branch taken. A cheap corruption with a determinate expected
outcome: delete a required field from `02-scenarios.json` after `tg-propose`
finishes, and check that the orchestrator re-dispatches `tg-propose` **once**
with the findings appended rather than editing the file itself or re-dispatching
twice. A second, sharper one: point a dispatch at a run directory that does not
exist, which is exit 2, and check that no repair attempt is spent on it.

**3. Did it `record-stage` every stage, or only the ones it remembered?** Read
`manifest.stages` against the stages that actually produced artifacts. The
likely failure is not a wholesale omission but a tail-off -- the early stages
recorded and the later ones forgotten as the run gets longer -- and the reason
it matters is that `stability.comparability` gates `diff-runs`' verdict on
these maps agreeing, so a missing entry makes two unrelated runs compare as
comparable.

**4. Is the report's verdict `healthy`, and if not, is the reason in the labels
or the agents?** The toy world with the scripted roster gives `healthy`
(measured: 1.0 / 0.77 / 0.2). A real agent roster will not, and the interesting
question is whether the orchestrator reports the difference correctly:
`broken_labels` as a suite defect rather than an agent result, and no attempt
to repair it with its own re-dispatch budget.

**5. Did the gap halt fire, and was it reported well?** See the section above.
Record the gaps' ids and their `blocks`, whether the halt named the input
artifact that would close each one, and whether `--no-gate` was correctly read
as not lifting it.

**6. Did the loop branch correctly on the coverage verdict?** Read
`03-coverage/latest.json`'s `verdict` for each round against what the
orchestrator did next. The branch worth watching is a `halted_no_progress` or
`halted_round_cap` at round 2: those halt the **loop**, not the run, and an
orchestrator that stops the pipeline there throws away every scenario the run
has already paid for. The other direction is a `continue` at round `K`, where
the correct action is to leave the loop anyway and report the disagreement.

## The deferral this exercise finally discharges

**`tg-reconcile` has never been exercised against real `tg-extract` output.**
Task 8's exercise ran it against `tests/toy.py`'s hand-authored claims, and
those claims file the unknown-id error correctly as an `outcome_class` -- so
that exercise could not test `tg-reconcile`'s Method step 3 instruction to
harvest outcome classes from claims of *any* kind. That instruction exists
because Task 7's real extract run filed the same fact as an `invariant` from
one slice (`notes-md`) and as an `outcome_class` from another (`api-json`), and
the consequence is specific: the coverage denominator is capability x outcome
class, so an error behaviour filed as an `invariant` does not feed the
enumeration and a column of the matrix goes missing with no schema, no
`check-refs` and no validation error naming it.

**This run is the first time reconcile reads real extract output, so read the
world model for it.** Concretely:

- Do the three claims files disagree about the kind of the unknown-id error,
  the way Task 7's run did? Record what each filed.
- Does `01-world-model.json`'s `capabilities[].outcome_classes` include an
  error class for `get_ticket` on an unknown id, and does its `denominator`
  count the cell? Task 8's fixture-based run enumerated **seven** capability
  cells (three for `find_tickets`, four for `get_ticket`); a real chained run
  producing fewer, with the unknown-id class absent, is the harvest failing.
- If the class is present, which claim does it cite? A class harvested from an
  `invariant`-kinded claim is the instruction working, and it is only visible
  in the citation.

**What a negative result looks like**, so it is not mistaken for success: the
run completes, every gate exits 0, the coverage report reads 100%, and the
denominator is missing the unknown-id cell entirely. Nothing anywhere reports
it -- a smaller denominator is a *cleaner-looking* run, which is what makes
this the failure worth going looking for. If that is what happened, the finding
is against `tg-reconcile`'s Method step 3 (or against the claims that fed it),
not against the orchestrator, and it belongs in the ledger under Task 8's
deferral rather than this one's.

## Recording the result

Record all six properties plus the deferral read in the exercise ledger,
whatever the outcome, and say which of the two shapes the run took. Property 1
is the one this exercise exists for and the one that needs the transcripts: it
is the only defect class in this build that is invisible in every artifact, on
every run, forever -- and unlike `tg-challenge`'s ordering, it cannot even be
made readable by asking for a pre-registration, because the orchestrator writes
no artifact that a prompt could be pre-registered in. The dispatch prompts are
the only evidence there will ever be, so they have to be read while they still
exist.

## Run record: round 1 of the live exercise

Two dispatches against one run: the first halted, a human ruled at gate 1, the
second resumed and completed. `intake` was run by hand, `--max-rounds 2` so the
loop was observable, and the roster was the three scripted agents written to
disk and validated against `agents-0.1.json`. Each dispatch carried only the run
directory, this skill's path, `--no-gate` and the roster path -- no summary of
the toy world, no mention of gaps, no instruction about stage failures.

### Part 1: the halt, which is the pass

It halted at B4 before dispatching `tg-propose`. A real `tg-reconcile` recorded
`gap-bad-argument-behavior`, whose `blocks` names `propose`, because none of the
three inputs says anything about `query_tickets`' invalid or missing-argument
behaviour. It named the gap, its `unknown`, and the input that would close it,
and recorded the halt with `decide`.

**The sharpest read passed: `--no-gate` did not tempt it into overruling the
halt.** Handed the flag, it reasoned that it skips the human review and does not
lift the halt "since it is not a human gate" -- the distinction the skill states
in one sentence, tested here for the first time.

### Part 2: the resumed run, after a human ruling

The human ruled the gap non-blocking for the stage as a whole and blocking for
its own cells only, recorded with `decide`, requiring those cells to come back
as `blocked_by_gap` holes and forbidding any edit to `blocks`. The run then
completed: propose (4 scenarios), score, instantiate (fan-out of 4), challenge
(fan-out of 4, all `accept`), emit (4 packages), smoke.

**All four pass criteria met, verified against the artifacts rather than the
report:**

1. `07-report.json` exists, `verdict: "healthy"`.
2. `check-refs` on the finished run exits 0.
3. `manifest.stages` holds all seven dispatched stages -- extract, reconcile,
   propose, score, instantiate, challenge, emit -- each with a `model`, an
   `effort` and a `skill_sha256`. `intake` and `smoke` are absent, as expected.
4. `decisions.md` carries twelve lines, well over one per loop round.

**The ruling was honoured exactly.** Coverage came back 4/6 capability cells
(66.7%) and 2/2 goals, verdict `converged` in round 1 of 2, with **two** holes --
`cell:cap-find-tickets/oc-find-bad-args` and `cell:cap-get-ticket/oc-get-bad-args`
-- both `reason: blocked_by_gap` carrying `gap_id: gap-bad-argument-behavior`,
neither `not_yet_attempted`. A stage told to leave an honest hole left one.

**The suite discriminates.** `mean_reward_by_role` was oracle 1.0, under_test
0.7, weak_baseline 0.2, with `oracle_failures: 0` -- so the labels are right, an
agent handed the reference answer passes everything. And `all_pass_tasks: 0`
with `all_fail_tasks: 0`: **no task was passed by every role or failed by every
role**, which is the property a generated suite exists to have and the one a
degenerate suite loses first. `unscoreable: 0`.

**An unplanned demonstration of the reproducibility hook.** `tg-extract`'s
`SKILL.md` was amended after this run's extract stage had already been recorded,
so its stored `skill_sha256` no longer matches the file on disk while the other
six still do. That is the hook working as designed: it records the digest of
what the run actually used, not of whatever the file later became, which is the
whole reason `record-stage` hashes rather than names.

### The deferral this run discharges

`tg-reconcile` has now been exercised against **real `tg-extract` output**, owed
since Task 8. The result is substantive rather than a formality: the real world
model's denominator is **6 capability cells**, against the hand-authored
fixture's 4. Real upstream artifacts produced a *larger* denominator, which is
the opposite of the failure this read was watching for -- a silently dropped
column, leaving a run that looks cleaner than it is. Both extra cells are
bad-argument outcome classes, one per capability, and both are correctly
reported as blocked holes rather than quietly omitted. So the honest report is
66.7% with two justified holes, where the feared one would have read 100%.

Reconcile also recorded `ctr-get-ticket-unknown-id` with resolution
`preferred_a`: `api.json` and `notes.md` independently state that `get_ticket`
on an unknown id errors, while `trace.json`'s single captured span shows it
returning `{}`. Two independent *stated* claims preferred over one
`reverse_engineered` observation, recorded as a resolution rather than silently
absorbed -- the extract/reconcile split paying off on real input.

**Both numbers are measurements, and the difference between them is the
finding.** The setup section above cites "seven capability cells (three for
`find_tickets`, four for `get_ticket`)" and attributes it, correctly, to Task
8's fixture-based run -- a measured result of a real `tg-reconcile` dispatch over
the hand-authored fixture claims, not a prediction. This run measured **6** over
real `tg-extract` claims for the same target. So the two figures are two
measurements of two different inputs: fixture claims give 7, real extract claims
give 6, and the hand-authored world model those fixture claims came with said 4.

That is **stage-level variance driven by upstream claim quality, in the one
artifact that freezes the coverage denominator for the entire run** -- every
later coverage percentage is a fraction of whichever number reconcile happened
to write, so the same target can honestly report a different denominator
depending only on how good its claims were.

An earlier version of this note read the pair as a prediction beaten by a
measurement, and called the seven a figure "written from reasoning rather than
from a run". That was a controller error -- the seven is at progress.md's Task 8
exercise entry as a measured enumeration -- and it is corrected here rather than
quietly deleted, because of what the error cost: it took the more interesting of
the two readings and discarded it.

**One limitation no prose fix closes.** The orchestrator has no lever for
`effort`. It recorded `model: sonnet, effort: medium` as the most neutral
characterization available and flagged the assumption rather than presenting it
as fact. Section A5 now says where model and effort come from; the dispatch
mechanism still cannot supply an effort level.
