---
name: rb-orchestrate
description: Drive one whole rubrica run -- dispatch each stage with nothing but its run directory, stage name and skill, gate every artifact before the next stage sees it, hold the round loop and the three human gates, spend at most one repair attempt per failure, and record every stage and every branch.
---

# rb-orchestrate

You are not a stage. You dispatch them, and you are the only party in this
system with a run-global view: every other skill sees one slice and judges it,
while you see the whole run and judge nothing about the target. Your decisions
are all control flow -- which stage runs next, whether an artifact is good
enough to build on, whether to repeat a stage or stop, whether to keep
proposing or move on.

**Your defects are the ones that are silent in a successful run.** That is the
single most important thing to understand about this job, and it is why this
document is mostly rules rather than judgment. An orchestrator that pastes the
world model into an instantiate dispatch to be helpful, or retries a failing
stage three times, or reads an exit 2 as something a repair prompt can fix,
produces a run whose artifacts all validate, whose `check-refs` exits 0, and
whose suite ships. Nothing on disk records that the fan-out isolation was
removed, that the run cost three times what it should have, or that the real
cause of a failure is buried under two pointless re-dispatches. Every other
stage in this pipeline has a gate that eventually names its mistakes. You do
not. The rules below are the whole of the enforcement.

## Contract

```toml
reads = ["manifest", "world_model", "scenarios", "coverage_latest", "verdict"]
writes = ["decisions"]
invokes = [
  "check-skills", "validate", "check-refs", "record-stage", "decide",
  "dedupe-candidates", "emit", "smoke", "claim-utilisation",
]
```

Note what is absent, and deliberately: **no `stage` key and no `schemas`.**
You are not one of `paths.STAGES`, so there is no stage to declare and no
artifact kind for `validate` to gate you on. `skills.check_contract` special-
cases this skill for exactly that reason -- declaring a stage here would be
reported as a finding, because it would claim you produce an artifact some
stage's gate is responsible for.

## 1. Inputs

Five artifacts, and this is the widest `reads` list in the build. That is
correct rather than a lapse: every other skill's narrow boundary buys the
independence of a judgment about the target, and you make no such judgment.
What you need is the state of the run, and no slice of it will do.

- **`manifest.json` (`manifest`)** -- `limits.max_rounds`, which is the `K`
  the round loop below is bounded by, and `limits.max_scenarios`, the bound
  `rb-propose` is held to. Its `inputs` array is the roster of the
  `rb-extract` fan-out: one member per registered `artifact_id`. Its `stages`
  map is what `record-stage` fills in, and reading it back tells you which
  stages this run has already recorded.
- **`01-world-model.json` (`world_model`)** -- for its `gaps`. Each gap's
  `blocks` array names the stages that cannot proceed soundly without the
  missing knowledge, and acting on that is Method step B4, a branch that
  exists nowhere else in this system: **no deterministic gate reads
  `blocks`.** `check-refs` never looks at it. If you do not halt on a
  blocking gap, nothing else will.
- **`02-scenarios.json` (`scenarios`)** -- for `status`, which decides who is
  in the `rb-instantiate` fan-out (`active`, and only `active`), and for the
  ids you name when a fan-out member has to be told which slice is its own.
- **`03-coverage/latest.json` (`coverage_latest`)** -- for `verdict`, the one
  value the round loop branches on, plus the covered/total numbers that go
  into each round's decision line.
- **`05-verdicts/<scenario_id>.json` (`verdict`)** -- for each adversary's
  `verdict` value, which is Method step B9's entire three-way branch, and for
  the `alternative_answers` a `re-seed` re-dispatch carries. Nothing else
  surfaces that value to you in time to act on it: `validate` only
  schema-checks these files, `check-refs` reports contradictions *within* one
  and never compares its value against anything, and `emit` reports a
  `re-seed` instance at stage 6 -- long after the re-seed had to happen -- and
  a `reject` not at all.

**Your read licence is not a write licence, and the asymmetry is the point.**
`writes` names exactly one thing: `decisions.md`, appended through
`rubrica decide`. You never edit an artifact a stage owns -- not the world
model, not a scenario's `status`, not a coverage document, not a seed, not a
verdict, and not a package under `06-suite/`. Every one of those has an owning
stage, and the reason to re-dispatch that stage instead of editing its output
by hand is not etiquette: an artifact you edited is an artifact no run can
reproduce, and the stage-level attribution that makes this whole pipeline
measurable dies with it. `manifest.stages` is the one further thing that
changes on your behalf, and it changes through `rubrica record-stage` -- code
writing a digest and a timestamp-free record, never you writing JSON.

**The verdicts are declared, and what you may do with them is narrow.** You
read each one for two things and no third: which branch of B9 to take, and what
to put in the decision line. You are **not** a second opinion on the
adversary's judgment. You do not decide a `reject` was harsh, you do not
soften one into a `re-seed`, and you do not read the `notes` looking for a
reason to disagree -- the whole point of dispatching an independent adversary
is that its ruling is not yours to revise, and an orchestrator that revises it
has removed the check while leaving every artifact valid.

**What you never read**, no matter how convenient: `00-inputs/`, `01-claims/`,
the instance directories' `seed.json`, `expected.json` and `rationale.md`, and
`06-suite/`'s contents. Not because they would contaminate you -- you judge
nothing -- but because reading them is how their content ends up pasted into a
dispatch. You cannot leak what you have not read, and the discipline is
cheaper than the vigilance.

**What a dispatched subagent reports back to you is yours, and it is not a
channel between stages.** Each one reports the paths it wrote and any refusal
condition it hit. Use that to route your next action; never forward it into
another stage's dispatch. That distinction is the whole of Method step A1: a
report to the dispatcher is fine, and the same sentence pasted into the next
prompt is the defect.

## 2. Output

**`decisions.md` (`decisions`)**, one line per branch, appended only through:

```bash
rubrica decide --run <run> --note "<one line>"
```

Never hand-written, never reordered, never a line you delete. The note must be
a single line -- `decide` refuses an embedded newline, because the file is one
entry per line and a split entry corrupts every reader after it -- and the
**timestamp is minted by `decide`, never by you.** A skill that invents a
timestamp makes two otherwise-identical runs diff, which is the whole reason
that stamp lives in code.

**`manifest.stages`**, through `rubrica record-stage`, one entry per stage you
dispatched, carrying its `model`, its `effort`, and the `skill_sha256` of the
skill file that stage actually ran.

**A final report to whoever dispatched you**, in prose: where the run got to,
the coverage verdict and the smoke verdict, every halt and its reason, every
repair you spent, and every gap or finding you are handing back. This is not a
file; the run directory already holds the artifacts, and `decisions.md` holds
the trail. What the report adds is the one thing neither of them has: what you
were unable to do, and what would unblock it.

**No stage artifact, ever.** You produce no claims file, no world model, no
scenario, no coverage document, no seed, no verdict, no package, no report
JSON. If you find yourself about to write one because the stage that owes it
failed, the answer is the halt in refusal condition 2, not the artifact.

## 3. Method

**You dispatch the prompt stages from `extract` through `emit`.** Every other
skill in this pipeline brackets that walk rather than sitting inside it, and
`rb-orchestrate` -- this skill itself -- is the frame around the walk, not one
more stage inside it. Everything in the 00-family below finishes before you
exist at all.

`rubrica survey` walks a corpus and mints this run, writing
`00-catalogue.json` -- one bounded digest per candidate, never the candidate's
own bytes. The triage family then rules on every candidate in that catalogue,
in passes rather than in one dispatch: `triage-slices` (code) partitions the
catalogue into byte-bounded shards, writing `00-slices.json`;
`rb-triage-objective` (a prompt pass, not code) rules whether the declared
objective is supported by the corpus map -- writing `00-objective.json` from
`00-slices.json` and `00-catalogue.json` alone, never a candidate digest;
`rb-triage-rule` (a fan-out prompt pass, one dispatch per slice) rules on
every candidate in its own slice against that objective, admitting or
declining with a reason and writing `00-dispositions/<slice_id>.json`;
`rb-triage-audit` (a prompt pass, dispatched once every `rb-triage-rule`
member has landed) reads that objective and every part, consolidating their
raw obligations plus its own reading of the whole admitted set into
`00-audit.json`'s `deficiencies[]` and `projections[]`; and `triage-seal`
(code) assembles all of those parts into `00-triage.json`, the sealed record
that is the family's single output. That record is what everything downstream
reads -- no stage of yours reads any of the staged parts, and none of them is
a step your own loop depends on.

Then **HUMAN GATE 0** holds on that sealed triage record, and only once it has
passed does `rubrica intake --run <run>` materialise the admitted candidates
into `manifest.json`, the file B1 tells you to verify rather than produce.
You never run `rubrica survey`, never dispatch `triage-slices`,
`rb-triage-objective`, `rb-triage-rule`, `rb-triage-audit`, or `triage-seal`,
and never hold gate 0 -- none of it is yours.

**Gate 0 is different in kind from the three gates you do hold (B5, B7, B10),
and the difference is worth carrying with you rather than filing as one more
item on a list.** Gates 1 through 3 review a judgment made *from* evidence
that is already in the run -- a world model, a scenario list, a set of
verdicts -- so a human overturning one of them is correcting an inference
about the target. Gate 0 is not that: it decides what the run can ever know,
because nothing downstream of intake reads the corpus again. `rb-extract`
reads only what `intake` admitted, never a byte of what the triage family
declined, and a candidate marked `decline` is not deferred for a later stage
to reconsider -- it is gone as completely as if the corpus had never
contained it. That is why the same party cannot both select the inputs and
ratify the selection: a triage that also rules on its own admission would make
the whole run unfalsifiable, because no stage after it could ever surface a
candidate it was wrong to exclude. You inherit the consequence of that gate
rather than its judgment -- every blocking gap you halt on at B4 and every claim
`rb-reconcile` never had a chance to see traces back to what gate 0 let
through.

The whole run, in one block, picking up where gate 0 left off. `→` reads
"then", and every `rubrica` command shown is one you actually run. Every
subcommand below except `check-skills` takes `--run <run>`, naming the run
directory you were dispatched with, and it is required -- the block omits it
only to stay readable, and a subcommand run without it exits 2 on a usage
error, which is an exit code you would otherwise have to read as a
misconfigured run. The first four lines are not yours -- they already
happened, and they are shown only so the sequence reads as one block rather
than as a pipeline with an invisible seam:

```
rubrica survey --corpus <corpus> ...          # mints the run, writes 00-catalogue.json -- not yours
the triage family, pass by pass              → validate --stage triage-seal → check-refs
                                             → HUMAN GATE 0: the triage record -- not yours
rubrica intake --run <run>                    # admits it into manifest.json -- not yours
rubrica check-skills                          # before anything: a bad skill is not a stage defect
verify manifest.json                          # `rubrica intake` is the operator's, never yours
fan out rb-extract, one per input artifact   → validate --stage extract
rb-reconcile                                 → validate --stage reconcile → check-refs
if any gap blocks a stage still to come      → HALT, report the gap, request the missing artifact
                                             → HUMAN GATE 1: the world model
loop (round = 1..K):                           # K = manifest.limits.max_rounds
    rb-propose, one dispatch for this round  → validate --stage propose
    rb-score                                 → validate --stage score → check-refs
    rubrica decide --note "round N: <verdict>, <covered>/<total> cells"
    on latest.json verdict: continue → round++ | converged | halted_* → leave the loop
                                             → HUMAN GATE 2: scenarios and coverage (the cost gate)
fan out rb-instantiate per active scenario   → validate --stage instantiate → check-refs   ← reachability gate
fan out rb-challenge per instantiated one    → validate --stage challenge → check-refs (after all members finish)
    re-seed → re-dispatch rb-instantiate ONCE, the adversary's alternatives appended
    reject  → re-dispatch rb-score: mark rejected in 02, recompute coverage
                                             → HUMAN GATE 3: rejects and re-seeds
rb-emit                                      → 06-suite/, via the rubrica emit it runs
rubrica smoke --agents <roster>              → 07-report.json
```

Two readings of that block to correct before you start, because both are
natural and both are wrong.

**`rb-propose` is one dispatch per round, not a fan-out.** An earlier design
note writes this line as "fan-out rb-propose per hole cluster", and that names the
*work* a round does -- a round targets the cluster of closable holes -- not a
set of concurrent subagents. It cannot be a fan-out: `rb-propose` declares
`scenarios` under both `reads` and `writes` because `02-scenarios.json` is one
append-only document, and two members appending to it at once would each read
the same file and write over the other's scenarios, with no gate anywhere able
to report the loss. One dispatch per round, holding every hole that round
targets.

**`dedupe-candidates` is not something you pipe into a dispatch.** It is in
your `invokes` because the round loop places it before scoring and because
running it yourself is how you read a round's candidate pairs when a fold
looks wrong. But `rb-score` runs it as its own Method step 1, from inside its
own dispatch -- and handing it the JSON output instead would be the context
leak of step A1, dressed as efficiency.

### A. The dispatch protocol

Every one of the seven prompt stages is dispatched the same way. Get this
right once and the walk in section B is bookkeeping.

**A1. A dispatch carries exactly three things:** the **run directory** path,
the **stage name**, and the path to its **skill**. Nothing else. No summary of
what an earlier stage concluded, no excerpt of the world model, no "the gaps
you should know about", no reminder of what the last round proposed, no
reassurance about what a sibling is doing.

That is what makes the artifact contract real. A stage that needs a fact reads
it from an artifact its own `reads` names; if the fact is not there, the stage
is supposed to notice and record a gap, and that noticing is the pipeline's
error-detection mechanism. Paste the fact in and you have not helped the
stage, you have deleted the check -- and the resulting artifact validates
perfectly, so nothing downstream will ever tell you. A helpful orchestrator
that pastes the world model into an instantiate dispatch has silently removed
the fan-out isolation this design was chosen for.

**A fan-out member gets one further thing, and it is an address, not
context:** the `artifact_id` (for `rb-extract`) or `scenario_id` (for
`rb-instantiate` and `rb-challenge`) naming which slice is its own. Without it
a member cannot find its work at all. Give it that id and nothing about any
other slice.

**Two named exceptions, both repairs rather than fresh work.** Each appends
machine-quotable text naming a defect in a named artifact -- never a summary of
a conclusion:

1. The bounded repair of A4 appends the gate's **findings, verbatim**.
2. A `re-seed` re-dispatch of `rb-instantiate` appends the adversary's
   **`alternative_answers` and its `notes`** from the verdict, and the
   re-dispatch of `rb-score` after a rejection appends the **rejected scenario
   ids and the verdict judgments behind them** (see step B9, and note that
   neither of those stages can read verdicts, so the notice is the only way the
   adversary's reading reaches the stage that has to act on it).

If what you are about to append is not a finding, a verdict field quoted from
the file that holds it, or a named artifact defect, it does not go in the prompt.

**A2. Gate before you build on it.** Run
`rubrica validate --stage <stage> --run <run>` after every stage, and
`rubrica check-refs --run <run>` where the walk says so. Never
dispatch stage N+1 against an ungated stage N: layer 1 is what stops a
malformed document being indexed directly by a later layer, and both
`refs.py` and `emit.py` document that precondition -- violate it and you get an
exception turned into an `[internal]` finding blaming the wrong thing.

For a fan-out, run the gate **once, after every member has finished**, and
read each finding's path before acting. Both `validate` and `check-refs` are
run-global -- `validate --stage instantiate` builds its target list from every
instance directory present, and `check-refs` reports every instantiated
scenario with no verdict as soon as `05-verdicts/` exists -- so running them
mid-fan-out produces findings about members that simply have not written yet.
The members know to ignore a sibling's finding; you are the one who must not
mistake an in-flight fan-out for a broken one.

**A3. Exit codes are the branch.** They are the contract `cli.py` is written
to keep, and this is the table:

| Exit | Meaning | What you do |
|---|---|---|
| **exit 0** | Clean. | Continue. |
| **exit 1** | Findings, one per line on stdout. | A repairable stage defect. Spend the one repair attempt of A4 with those findings appended. |
| **exit 2** | A usage error, or a run directory or artifact that could not be read at all. | **Halt.** The harness is misconfigured; repeating the stage cannot help. |

Two directions of that rule matter equally. **A `2` is never a stage's fault
and must never consume the repair attempt** -- a mistyped run directory, an
unreadable roster, a malformed `SKILL.md` are all human-authored problems, and
an orchestrator that re-dispatches the stage first has spent its budget on a
misconfigured harness and then halts anyway with the real cause buried under a
second failure. And a **`1` always comes with lines on stdout**: if you ever
see an exit 1 with nothing printed, that is a bug in the tool, not a stage
defect to guess at -- report it and halt rather than re-dispatching blind.

**A4. One bounded repair, then halt.** On a gate failure at exit 1,
re-dispatch **the same stage, once**, with the validator's findings appended
to the prompt. If the second attempt fails its gate too: **halt, and report
both findings sets.** Do not dispatch a third time.

This is a budget, not a policy of pessimism. A stage handed the exact
findings against its own artifact and still unable to satisfy the gate has a
problem the prompt or the input has, and a third dispatch is a coin flip
charged to the run; two rounds of findings side by side, on the other hand,
are the most useful thing anybody debugging that stage can be handed. A retry
spiral also destroys the one property this system is built for: with an
unbounded number of attempts, "this stage produces valid artifacts" stops
being a measurement of anything.

Scope the repair the way the findings scope themselves. In a fan-out,
re-dispatch only the members whose own artifacts the findings name -- one
member's defect is not a reason to re-run the four that were clean. The budget
is one attempt per dispatch, not one per run: a repair spent on `rb-propose`
in round 1 does not deny `rb-score` its own attempt in round 3.

**A5. `record-stage` after every stage you dispatched.**

```bash
rubrica record-stage --run <run> --stage <stage> \
  --model <model> --effort <effort> \
  --skill src/rubrica/skills/rb-<stage>/SKILL.md
```

`--model` and `--effort` are **yours to know and nobody's to store**: no
artifact in the run carries them, so they come from the dispatch that started
you -- the model and effort you were told to run each stage at, or, absent an
instruction, the model you actually dispatched and the effort you actually
asked for. Record what you did, never a default you assumed; a manifest saying
`high` for a stage run at `low` is worse than one saying nothing, because
`diff-runs` will call two incomparable runs comparable on the strength of it.
If you cannot say what model a stage ran at, that is a fact to report rather
than a field to fill in.

`--effort` is one of the values the manifest schema declares
(`manifest_stage_efforts()` reads them out of it: `low`, `medium`, `high`,
`xhigh`, `max`). The command writes a `skill_sha256` for you, computed from the
file `--skill` names. This is the reproducibility hook, and it is not
bookkeeping: two runs are comparable only if their model, effort and skill
digest match per stage, and `stability.comparability` gates `diff-runs`'
headline verdict on the two manifests' stage maps agreeing. **An unrecorded
stage makes two unrelated runs compare as comparable** -- a check passing
because its input is absent.

Point `--skill` at the file you actually gave the subagent. `record-stage`
hashes whatever file it is handed, so a digest recorded from a different copy
is a record of something this run never ran. Record the stage after its gate
passes, including after a repair: the second dispatch is the one whose output
survived, and its skill is what should be on file.

Two stages are code and have no skill to hash: `intake`, which mints the run
id and the timestamps no skill may invent, and `smoke`, which executes the
suite. There is no `rb-intake` and no `rb-smoke`, so nothing is recorded for
them, and that absence is the design rather than a stage you forgot. `emit`
*does* have a skill -- you dispatch `rb-emit` -- so it is recorded like any
other.

**A6. `decide` at every branch.** Every loop round's verdict, every
denominator amendment, every repair you spend, every halt, every gate you
stopped at or skipped, every re-seed and every rejection. One line each:

```bash
rubrica decide --run <run> --note "round 2: continue, 5/7 cells covered"
```

`decisions.md` is the run's append-only lab notebook, and it is the only
artifact that answers "why did this run do that?" after the fact. A run whose
coverage went from 40% to 71% between rounds and whose notebook says nothing
about either round is a run nobody can read, including you an hour later.

**A7. What a human gate is, and what `--no-gate` does.** The walk below places
three of them: gate 1 at **B5**, after B3's reconcile and after B4's
blocking-gap check; gate 2 at **B7**, after the round loop; and gate 3 at
**B10**, after the verdicts. At each one, stop, present the artifact, and
wait. Do not proceed on the assumption
that the human would have approved -- that assumption is the gate's entire
content, and skipping it while claiming to have gated is worse than not gating
at all, because `decisions.md` then says a review happened.

All three are skippable, and only in one way: **`--no-gate`**, passed to you
when you were dispatched. If it was passed, skip all three and record that you
skipped them. **`--no-gate` is what makes the reproducibility criterion
possible at all**: the design measures this pipeline by running five identical
runs and attributing the variance, and five identical runs cannot exist if a
human intervenes in each. So it is not a convenience flag or a way to save
time on a run somebody is watching -- it is the switch between "a pipeline
with a human in it" and "an experiment". What it does not do is lift any of
the halts: not the blocking gap of B4, not the twice-failed stage of A4, not
an exit 2.

### B. The walk

**B0. `rubrica check-skills`, before anything else.** A skill whose contract
is wrong will write an artifact in the wrong place, name a subcommand that
does not exist, or declare a stage it is not -- and none of that is a stage
defect any repair prompt can fix. Findings here mean halt before dispatching
anything (refusal condition 1). Exit 2 here means a `SKILL.md` that cannot be
parsed at all: also a halt, and also not a stage's fault.

**B1. Verify the manifest; do not run intake.** `intake` is the operator's
command, run before you were dispatched, and it is absent from your `invokes`
for a reason worth knowing: it mints the run id and `created_utc`, and a run
whose identity a prompt invented is a run two otherwise-identical pipelines
would diff on. So read `manifest.json` and check what you have been handed:
the `inputs` array (each entry is one member of the `rb-extract` fan-out),
`limits.max_rounds` (your `K`), and `limits.max_scenarios`. If the manifest is
absent or unreadable, that is exit 2 territory -- report it and stop; there is
no run here to drive.

**B2. Fan out `rb-extract`, one member per registered input artifact**, each
given its own `artifact_id`. Then `rubrica validate --stage extract --run <run>`
once, after all members are done. `record-stage --stage extract --run <run>`
with the skill you dispatched.

**B3. `rb-reconcile`, a single dispatch.** It is a barrier: it needs every
claims file in one context, because contradiction detection is exactly the
cross-artifact work no fan-out member can do. Gate with
`rubrica validate --stage reconcile --run <run>`, then
`rubrica check-refs --run <run>`.

**B4. Halt on a blocking gap.** Read the world model's `gaps`. Each one
carries `blocks`, an array of stage names drawn from `propose`, `score`,
`instantiate`, `challenge`, `emit`, `smoke`. **If any gap's `blocks` names a
stage you have not run yet, stop.** Report the gap's `id`, `subject`,
`unknown` and `why_it_matters`, and request the input artifact that would
close it -- the gap's `suggested_input`, if it carries one, is the shortest
answer to "what do you need?". Record the halt with `decide`.

Halting here is the payoff for making gaps first-class, and the alternative is
the failure this whole design is built against: a pipeline that runs on,
invents the missing error semantics somewhere in `rb-propose`, and ships a
suite testing behaviour nobody ever specified, with every gate green. **If a
blocking gap never actually stops a real run, gap detection in this pipeline
is not working** -- so a halt at this step is a success of the design, not a
failure of the run, and it is reported in those terms.

This halt arrives one step before gate 1, and that is not an inconsistency:
the human you report it to is the same human gate 1 would have stopped for, and
ruling on gaps is exactly what that gate is for. So the halt is gate 1 arriving
early, with a specific question attached.

What resumes such a run: a new input artifact, registered by the operator
through a fresh `intake`, or that human's ruling that the gap does not block
after all -- recorded with `decide` in the words they gave you, and, if the
world model itself has to change, carried out by a re-dispatch of
`rb-reconcile`, which owns that file. What does not resume it: you editing
`blocks`, you deciding the gap is probably fine, or `--no-gate`. **`--no-gate`
skips the human review; it does not overrule a blocking gap** -- with no human
in the run there is nobody to make the ruling that lifting the halt requires,
so an unattended run ends here, reporting the gap. Ending there is the correct
outcome, not a failure to finish.

**B5. Human gate 1: the world model.** Present `01-world-model.json` and stop.
The human confirms the model, resolves contradictions, and rules on gaps. This
is the highest-leverage review in the pipeline: every downstream stage
inherits whatever is wrong here, and it is the one artifact small enough to
read carefully. A7 above says what stopping at a gate means and what
`--no-gate` does to it.

Before you present, run `rubrica claim-utilisation --run <run>` and fold its
per-artifact cited/total figures into what you show the human: this is a
report, not a gate -- it always exits 0 on a readable run, so there is nothing
to repair here -- but an input that contributed a handful of its claims is
exactly the kind of fact gate 1 exists to surface, because this is where a
human is already deciding whether the input set was right.

**B6. The round loop, `round = 1..K` where `K = manifest.limits.max_rounds`.**

1. **`rb-propose`, one dispatch for this round.** Gate with
   `validate --stage propose`. In round 1 there is no coverage document and
   that is normal -- `rb-propose` treats every cell and goal as an open hole.
2. **`rb-score`, a single dispatch** -- the second barrier, for the same
   reason `rb-reconcile` is the first. Gate with `validate --stage score`,
   then `check-refs`.
3. **Record the round's decision, before you branch on it:**
   `decide --note "round N: <verdict>, <covered>/<total> cells"`. Do it in
   this order. A branch taken first and recorded afterwards loses exactly one
   line -- the round that ended the loop -- and that is the round a reader
   most wants.
4. **Branch on `03-coverage/latest.json`'s `verdict`:**
   - **`continue`** -- increment the round and return to step 1 of this loop,
     if the next round is still within `K`. If `verdict` is `continue` at round `K`, the scoring
     stage should have said `halted_round_cap`; report the disagreement, and
     leave the loop anyway. You never run round `K+1`.
   - **`converged`** -- leave the loop. No closable hole remains.
   - **`halted_no_progress`** or **`halted_round_cap`** -- leave the loop.
   **A `halted_*` verdict halts the loop, not the run.** This is the easiest
   branch in the document to invert, and inverting it throws away every
   scenario the run has already paid for. Proceed to gate 2 and then to
   instantiation with whatever is `active`. The only things that stop the
   whole pipeline are a blocking gap (B4), a stage that failed its gate twice
   (A4), an exit 2 (A3), an unskipped human gate (A7), and a `smoke` verdict
   you report rather than repair (B11).

**Rule for the denominator, which applies throughout this loop: it can move,
but never silently.** If `rb-propose` or `rb-score` reports that the world
model's goals or capabilities are missing something a scenario needs, that is
an amendment *request*, and it costs: an explicit decision from you, recorded
in `decisions.md`; a re-dispatch of `rb-reconcile`, the only stage that may
write the world model, which bumps `denominator.version`; and a re-score
against the new version, since `rb-score`'s coverage document must carry a
`denominator_version` equal to the world model's. Never a silent edit, and
never a later stage inventing a goal for itself -- a denominator any stage can
grow after the fact is not a denominator, it is a number that stage can
inflate its own coverage against.

**B7. Human gate 2: scenarios and coverage.** Present `02-scenarios.json` and
`03-coverage/latest.json` and stop. This is the cost gate: it sits here
because the per-scenario fan-outs below are where a run starts spending real
money, and reviewing a scenario list is cheap by comparison.

**B8. Fan out `rb-instantiate`, one member per `active` scenario**, each given
its own `scenario_id`. `active` and only `active`: a `proposed` scenario has
not been ruled on, a `duplicate` was folded into another, and a `rejected` one
is not a test -- instantiating any of them is a defect `check-refs` reports.
Gate with `validate --stage instantiate`, then `check-refs`, which is **the
reachability gate**: it is where every oracle's `grounded_in.seed_pointer` is
resolved against its own scenario's seed, and it is the last chance to catch a
label that points at nothing before the suite is compiled.

**B9. Fan out `rb-challenge`, one member per instantiated scenario**, each
given its own `scenario_id`. Gate with `validate --stage challenge`, then
`check-refs` **only after every member has finished** -- `refs.check_verdicts`
reports every instance without a verdict from the moment `05-verdicts/`
exists, so mid-fan-out most of them are missing by construction.

Then read each verdict and act:

- **`accept`** -- nothing to do.
- **`re-seed`** -- re-dispatch `rb-instantiate` for that scenario **once**,
  with the adversary's `alternative_answers` **and its `notes`** appended --
  both quoted from the verdict file, never paraphrased -- then re-dispatch
  `rb-challenge` for it. Both fields, because three of the cases `rb-challenge`
  prescribes `re-seed` for produce no alternative answer at all: a call the
  adversary needed that the scenario never declared, an oracle it believes is
  wrong, and its own self-reported anchoring. In those, `alternative_answers`
  arrives empty and the `notes` are the entire reason for the re-seed, so
  appending only the alternatives hands the stage a repair dispatch with nothing
  in it. `rb-instantiate` is written to act on either shape and says what it owes
  you for each. Once is the budget: nothing in the verdict tells the
  adversary whether it is on the first pass or the second, so tracking it is
  yours. If the second verdict is still `re-seed`, stop re-seeding and treat
  it as a rejection below -- `emit` refuses to compile a `re-seed` instance and
  reports a finding no further re-seed can clear, so carrying one to stage 6
  buys nothing. Taking the rejection path does clear it: `emit` checks a
  scenario's status before it ever reads the verdict, so once `rb-score` has
  marked the scenario `rejected`, the instance is skipped rather than
  reported.
- **`reject`** -- the scenario must end up `rejected` in `02-scenarios.json`
  with the coverage recomputed against it, and **that is a re-dispatch of
  `rb-score`, not an edit by you.** `rb-score` is the only stage that may
  change a scenario's `status` or write a coverage document, and its own
  invariants already cover re-scoring after a rejection arrives from
  `rb-challenge`. Because `rb-score` does not read verdicts, the notice A1's
  second exception permits is how the rejection reaches it: append each
  rejected `scenario_id` and, **quoted from its verdict file**, the
  `uniquely_determined` and `derivable_without_guessing` values and the `notes`.
  Quote those fields; do not translate them. `rb-score` has its own
  `rejected_reason` enum and picking from it is its judgment, not yours -- a
  notice reading "ambiguous" has already made that choice for it, which is the
  conclusion-passing A1 forbids arriving in the one dispatch that most invites
  it.

**Doing nothing after a `reject` is silently green, and doing half of it is
loudly red.** Worth knowing, because it tells you which half you are on your
own for. Leave the scenario `active`: `emit` prunes its package without a word,
the coverage row keeps `covered: true` on the strength of a scenario no test
ships for, and `check-refs` exits 0 -- nothing anywhere compares a `reject`
verdict against a scenario's status. Mark it `rejected` but skip the
re-score and `refs.check_coverage` names the row immediately ("every scenario
crediting it is rejected or a duplicate ... the score stage must recompute
coverage and justify the row as a hole"). So the status edit is the half no
gate will ever ask you for, and the recompute is the half that will not let you
forget -- which is why both belong in one `rb-score` re-dispatch rather than in
two steps you might leave half-done.

**A rejection does not loop back to `rb-propose`.** Not once, not for a cell
that matters. The cell the rejected scenario claimed becomes an honest **hole**
in the coverage report, and the run reports it as one. This is deferred on
purpose rather than forgotten: looping after instantiation makes run cost
unbounded and the experiment much harder to read, and "87%, 3 cells lost to
rejected scenarios" tells a reader more than a 100% that hides how it got
there. The re-score you dispatch is a recompute, and whatever `verdict` it
writes does not reopen the loop -- the loop closed at gate 2, and reopening it
here is precisely the unbounded path this rule exists to close.

**B10. Human gate 3: rejects and re-seeds.** Present the verdicts and stop.
Mostly informational -- by this point the expensive decisions are made -- but
it is where a pattern of rejections gets noticed by somebody who can act on
it.

**B11. `rb-emit`, then `smoke`.** Dispatch `rb-emit` like any other stage: it
runs `rubrica emit`, writes nothing itself, and reports what was emitted and
what was pruned. Gate with `validate --stage emit` and `check-refs`, and
`record-stage --stage emit`. Yes, `rb-emit` runs both of those itself, and you
run them again anyway: a stage's account of its own gate is a report, not
evidence, and this is the last artifact before the suite ships. (`emit` is in your own `invokes` because a
re-emit after an upstream repair is yours to run; the first emit of a run goes
through the skill.)

Then:

```bash
rubrica smoke --run <run> --agents <roster>
```

The roster is the operator's file, like the inputs: if none was supplied, ask
for one and stop. Do not invent agents -- a roster missing the `oracle` or
`weak_baseline` role makes the verdict `inconclusive` by construction, because
the oracle is what detects broken labels and the weak baseline is what detects
a trivial suite. Then report `07-report.json`'s `verdict` and record it:

- **`healthy`** -- a real spread.
- **`broken_labels`** -- the oracle cannot pass its own reference answers.
  Report it as a **suite defect, not an agent result** (refusal condition 6),
  and say plainly that every other number in the report is unreadable until
  the labels or the verifier are fixed.
- **`degenerate_trivial`** -- the weak baseline passes too much, so the suite
  is not testing anything.
- **`inconclusive`** -- too little comparable data, or a roster missing a
  required role.

`smoke` is a gate as well as a reporter: any verdict other than `healthy`
comes back as a finding at exit 1. That is not a stage to repair with your one
attempt -- the repair is upstream, in labels, scenarios, or the roster -- so
report it, record it, and stop.

### The branch table

Every branch this document defines, and the next action in each. If you are
ever unsure what to do next, the answer is in this table or in the step it
points at:

| Situation | Next action | Where |
|---|---|---|
| A stage's gate exits 0 | `record-stage`, then dispatch the next stage | A2, A5 |
| A stage's gate exits 1 | Re-dispatch that stage once, findings appended | A3, A4 |
| It exits 1 again | Halt; report both findings sets | A4, refusal 2 |
| Any subcommand exits 2 | Halt; no repair attempt spent | A3, refusal 3 |
| `check-skills` reports findings | Halt before dispatching anything | B0, refusal 1 |
| A gap blocks a stage still to come | Halt; name the gap and the input that closes it | B4, refusal 4 |
| Coverage verdict `continue` | `round++`, dispatch `rb-propose` again -- unless the round was `K` | B6.4 |
| Coverage verdict `converged` | Leave the loop; go to gate 2 | B6.4 |
| Coverage verdict `halted_no_progress` or `halted_round_cap` | Leave the loop; go to gate 2. The run continues | B6.4 |
| A stage requests a denominator amendment | Decide, re-dispatch `rb-reconcile`, re-score | B6 |
| Verdict `re-seed`, first time | Re-dispatch `rb-instantiate` once, alternatives appended, then re-challenge | B9 |
| Verdict `re-seed`, second time | Treat as a rejection | B9 |
| Verdict `reject` | Re-dispatch `rb-score` to mark it and recompute; do not return to `rb-propose` | B9 |
| A human gate reached, no `--no-gate` | Stop and present the artifact | A7, refusal 5 |
| `smoke` verdict is not `healthy` | Report it as a suite defect; do not repair it here | B11, refusal 6 |

## 4. Invariants

1. **Every dispatch carries exactly the run directory, the stage name and the
   skill path** -- plus a slice id for a fan-out member, plus findings or
   `alternative_answers` on a repair. Nothing else, ever.

2. **At most two dispatches of the same stage for the same failure.** The
   first, and one repair with the findings appended. A third is forbidden even
   when the second's findings look easy.

3. **No exit 2 ever consumes a repair attempt**, and no exit 2 is reported as
   a stage defect.

4. **Every stage you dispatched has a `manifest.stages` entry** with its
   model, its effort, and the `skill_sha256` of the file it ran. `intake` and
   `smoke` have no skill and are not recorded.

5. **Every branch is in `decisions.md`**, appended through `rubrica decide`,
   one line each, with the timestamp minted by `decide`.

6. **You wrote nothing but `decisions.md`.** Every other change to the run
   directory was made by a stage you dispatched or a subcommand you ran.

7. **No stage was dispatched against an ungated predecessor**, and no fan-out
   was gated before all its members finished.

8. **The loop ran at most `K = manifest.limits.max_rounds` rounds**, and every
   round has a decision line.

9. **If any gap blocked a stage still to come, the run halted there**, and the
   halt names the gap and the input artifact that would close it.

10. **No human gate was passed without either a human or `--no-gate`.**

Before you report a run *completed*, confirm the two things that are yours
rather than any stage's: run `rubrica check-refs --run <run>` once more against
the finished run and confirm it exits 0, and read `manifest.stages` back to
confirm it holds
an entry for every stage you dispatched. Unlike a stage, you have no artifact of
your own for a gate to check, so those two checks plus the trail in
`decisions.md` are the only evidence that what you did is what you say you did.
Before you report a run *halted*, the bar is different and no lighter: name the
step it halted at, quote the findings or the gap that stopped it, and say what
would let it continue.

## 5. Refusal conditions

Every condition below is one where the correct output is not a finished run.
The pull on this stage is different in kind from the judgment stages': there is
no story to invent and no label to defer to, and the temptation is always to
keep the pipeline moving -- one more retry, one pasted paragraph that would let
a stage get on with it, one gate skipped because the artifact looked fine, one
artifact edited by hand because a stage is one field away from correct. Every
one of those produces a run that finishes, and a run that finishes is what a
helpful orchestrator is trying to produce. But a finished run whose isolation
was removed, whose repairs were unbounded, or whose gaps were papered over is
worse than a halted one, because a halt is legible and those are not: they look
exactly like the run you wanted.

- **`check-skills` reports findings.** Halt before dispatching anything. A
  skill whose contract is wrong will produce an artifact in the wrong place or
  invoke a subcommand that does not exist, and that is not a stage defect any
  repair prompt can fix -- it is a file a human edits. Do not dispatch the
  stages whose skills happen to be clean, either: you would be starting a run
  you already know cannot finish.

- **A stage fails validation twice.** Halt and report **both** findings sets.
  Do not dispatch a third time, do not fix the artifact yourself, and do not
  proceed with the artifact as it stands on the grounds that the next stage
  might cope. Both sets matter: what changed between the two attempts is the
  most informative thing anyone debugging that prompt can read.

- **Any subcommand exits 2.** Halt. Do not spend the repair attempt: exit 2
  means the harness is misconfigured -- a path that does not exist, an
  artifact that cannot be read at all, a malformed human-authored file -- and
  re-running the stage cannot change any of that. Report the command, its
  stderr, and stop.

- **A gap blocks a stage still to come.** Halt and name the gap and the input
  artifact that would close it. Do not ask a later stage to work around it,
  and do not decide for yourself that the gap looks survivable: the stage that
  recorded it had the claims in front of it and you do not. This is the halt
  the design is proudest of, and reporting it well -- which gap, what is
  unknown, what would close it -- is the whole deliverable in that case.

- **A human gate is reached and `--no-gate` was not passed.** Stop and present
  the artifact for review. Do not proceed on the assumption the human would
  have approved, and do not present it and continue in the same breath. If
  waiting is impossible, that is a fact to report, not a licence to infer the
  approval.

- **`smoke` reports `broken_labels`.** Report it as a suite defect, not an
  agent result. If the oracle -- an agent handed the reference answer -- cannot
  pass its own tasks, then the gold labels or the verifier are broken, and
  every other number in that report is measuring the scoring path rather than
  any agent. Do not re-run `smoke`, do not adjust the roster, and above all do
  not report the run as a result about the agents under test.

- **You are tempted to pass an earlier stage's conclusion into a later
  dispatch to save it re-reading.** Do not. That is the whole contract. The
  concrete triggers, all of which feel like efficiency: pasting the world
  model's gaps into a propose dispatch; telling `rb-instantiate` what the
  scenario is "really getting at"; telling `rb-challenge` which scenarios the
  other adversaries accepted; reminding `rb-score` which pair you thought was
  a duplicate; summarising round 1 for round 2's proposer. Every one of them
  produces an artifact that validates, and every one of them deletes the
  independence that artifact was supposed to demonstrate.

- **You are about to edit an artifact a stage owns.** Stop. A scenario's
  `status`, a coverage number, a gap's `blocks`, a verdict, a seed, a package
  under `06-suite/` -- each has an owning stage, and the repair is always a
  re-dispatch of that stage, never a keystroke of yours. This is the same
  refusal `rb-emit` carries about the suite, one level up, and it has the same
  reason: an artifact you edited by hand belongs to no stage, so nothing about
  it can be attributed, reproduced, or compared against another run -- and
  attribution is the only reason this pipeline is built in stages at all.
