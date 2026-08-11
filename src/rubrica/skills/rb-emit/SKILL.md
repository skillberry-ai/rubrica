---
name: rb-emit
description: Compile the accepted instances into Harbor task packages by running `rubrica emit`, gate the result, and report what was emitted and what was pruned -- a thin human-facing entry point over code that writes nothing itself.
---

# rb-emit

You are stage 6, and you are the thinnest skill in this pipeline. Every other
stage asks you for a judgment; this one asks you for four commands and an
honest report. **You do not write any file in the run directory.**
`rubrica emit` writes the suite; you run it, gate what it produced, and say
what happened.

That is not modesty about the stage's importance -- 06-suite/ is the thing
that ships -- it is the one design decision this skill exists to preserve.
**Emit is code because of the reproducibility criterion.** If emit were a
prompt, two runs with identical stage-4 and stage-5 artifacts could still
produce different suites: a different `task.toml` field order, a paraphrased
`instruction.md`, one assertion translated two ways. Variance in the finished
suite could then no longer be attributed to any stage, because the last step
would be adding variance of its own. `emit.py` is deterministic instead --
the same instances and the same world model compile to the same bytes, every
time -- and the entire value of that property is lost the moment somebody
writes a package by hand. So the rule below is absolute rather than
stylistic: if you are editing a file under `06-suite/`, the pipeline has
already lost the property this stage was written in code to protect.

## Contract

```toml
stage = "emit"
reads = ["scenarios", "verdict", "expected", "world_model"]
writes = ["task_dir"]
schemas = ["suite-expected"]
invokes = ["emit", "validate", "check-refs"]
```

## 1. Inputs

Four names under `reads`, in two pairs that do two different jobs.

**The pair the compilation is about.** `01-world-model.json` (`world_model`),
whose `capabilities[].binding` turns a capability id into the `{tool, args}`
pair the verifier can score, and each accepted instance's
`04-instances/<scenario_id>/expected.json` (`expected`), the oracle being
translated. These are what `rubrica emit` consumes to build a package, so they
are what a finding about a package will name.

**The pair the *report* is about.** `02-scenarios.json` (`scenarios`) and
`05-verdicts/<scenario_id>.json` (`verdict`). Method step 4 asks you to say why
a package is absent, and two of the reasons appear nowhere in emit's own
output: `emit` skips a scenario whose `status` is not `active` without printing
a word, and skips an instance whose verdict is `reject` without printing a
word. Those two facts live in these two files and nowhere else -- no gate
reports either of them, because `refs.check_suite` reports a package that is
*present* for a scenario nobody judged and says nothing at all about one that
is absent. They are in your `reads` because a requirement of this skill needs
them, which is the only reason anything is ever in a `reads` list.

`writes` names `task_dir` -- `06-suite/<scenario_id>/` -- because that is where
this stage's output lands, even though the process that puts it there is
`rubrica emit` and not you.

You read all four to *understand and report* what emit did, never to decide
anything. This stage has no judgment to make: every judgment that selects
what ships was already made and recorded -- `rb-score` promoted the scenario
to `active`, `rb-challenge` filed an `accept`, and `emit` reads both. You are
not a second opinion on either.

**So the boundary that matters here is not the one you are used to, and
inferring the usual one would be wrong.** Every fan-out skill in this pipeline
holds a hard line at its `reads` list because its value comes from judging one
slice without seeing another's. You are not a fan-out member and you produce
no judgment, so there is nothing here for a wider view to contaminate -- which
is why this contract can name the scenario list and the verdicts without cost.
What replaces that boundary is a narrower and stricter one, and it is the
whole of this skill's discipline: **you may read, and you may not write.**

Two specific forms of that, because reading these two files is exactly where
the temptation arrives. A `status` you may read is not a `status` you may
change -- that transition is `rb-score`'s alone. A `reject` you may read is
not a verdict you may weigh: the adversary ruled, and your job is to report
that the ruling is why a package is absent, never to decide it was harsh.

You are dispatched with no memory of any conversation that came before you.
Whatever you need is in this document, in the run directory, or in the output
of the commands below. In particular, nobody tells you which scenarios ought
to have been emitted, and you do not need telling: emit prints the ones it
wrote and the run directory holds the state that decided the rest.

## 2. Output

**Nothing, in the run directory.** Every file under `06-suite/` is written by
`rubrica emit`, which lays out one directory per emitted scenario holding
`task.toml`, `instruction.md`, `seed.json`, `golden.json`, `provenance.md`,
and `tests/` with `expected.json`, `verify.py` and `test.sh`. Your contract's
`schemas` names `suite-expected`, the schema for `tests/expected.json`: that
is the gate `validate --stage emit` applies to each package's scoring
contract. It is a gate you run, not a document you author.

What you produce is a **report**, addressed to the orchestrator, and it has
four parts:

1. **What was emitted** -- the task directory paths `rubrica emit` printed,
   one per package.
2. **What emit reported** -- every finding line, verbatim, or that there were
   none.
3. **What was pruned, and why** -- one line per instance directory that has no
   package, naming the scenario and the reason (Method step 4).
4. **What the two gates said** -- the exit code of `rubrica validate --stage
   emit` and of `rubrica check-refs`, and any finding either one named.

None of that is a file. `decisions.md` is the orchestrator's to append to via
`rubrica decide`, not yours, and a report you deliver as prose is exactly
what this stage is for.

## 3. Method

Four steps.

1. **Run `rubrica emit --run <run>`.**

   That is the whole of the compilation. Do not build a package by hand, do
   not "fix up" one emit wrote, and do not write the missing package for an
   instance emit skipped. There is nothing to gain by it: emit is
   deterministic, so once the upstream artifact is repaired, re-running emit
   restores the package byte for byte -- the cost of a real repair is one
   re-run, and the cost of a hand-written package is a suite nobody can
   reproduce.

2. **Read the paths it printed and the findings it reported.** Emit's stdout
   is one task directory path per emitted package, followed by finding lines
   if there are any. The exit code tells you which case you are in:

   - **0** -- every qualifying instance compiled. The printed paths are the
     whole suite.
   - **1** -- packages were still written for the instances that translated,
     *and* at least one finding is on stdout. A single unbound capability
     does not cost the whole suite, so this is a partial success with a named
     defect, not a failed stage. Report both halves.
   - **2** -- the run directory or an artifact could not be read at all.
     Nothing was compiled and no finding names anything to edit; report it as
     a harness problem (refusal condition 3).

   Emit's findings are always about an *upstream* artifact -- a capability
   with no `binding` in the world model, an oracle that no longer parses, an
   instance with no verdict, an instance still marked `re-seed`. Read each
   one for which artifact it names, because that is who has to change.

3. **Run `rubrica validate --stage emit`, then `rubrica check-refs`.** In
   that order: layer 1 schema-checks every emitted `tests/expected.json`
   against `suite-expected`, and layer 2 then checks each package is complete
   (all eight files present) and addresses a scenario that was actually
   judged.

   **You have no scoping problem here, and two sibling skills do**, so it is
   worth saying why yours differs rather than leaving a reader to wonder.
   `rb-instantiate` and `rb-challenge` each carry a paragraph telling their
   reader to ignore findings against a sibling's artifact, because those two
   run several subagents at once against a gate that is run-global. Emit is a
   single dispatch over the whole suite and nothing else is running, so every
   finding either command returns is about this run's state and reporting it
   is your job.

   The other four stages carry a different clause -- a finding against what
   you just wrote is your own defect to fix -- and **that one does not apply
   to you either**, for the opposite reason: you wrote nothing. A
   `check-refs` finding here is usually not yours to repair, because the
   artifact it names is upstream. Report it; do not edit it.

   One expected exception worth recognising rather than repairing: layer 2
   tolerates a package for a scenario marked `rejected`, because nothing
   orders `emit` and `check-refs`, and between a rejection and the next emit
   such a package is legitimately still on disk. If you have just run emit,
   that package is gone -- pruned -- which is the state described below.

4. **Report what was emitted and what was pruned, and why.** The pruning is
   not a footnote to the report, it is half of it. `06-suite/` is shipped to
   Harbor and scored as a whole, so emit makes it a function of the current
   run state and nothing else: every package directory it did not write this
   run is removed. That is deliberate, because the alternative is shipping a
   complete, well-formed, scoreable package for a test nobody accepted.

   So for every instance directory under `04-instances/` with no package
   under `06-suite/`, say which scenario and why. The reasons, and where each
   one comes from:

   | Why there is no package | Where you read it | Is it a defect? |
   |---|---|---|
   | The scenario's `status` is not `active` -- `duplicate`, `rejected`, or still `proposed` | `02-scenarios.json` | No. A `rejected` scenario's package is *supposed* to be pruned, and a `duplicate` never had a test of its own. |
   | Its verdict is `reject` | `05-verdicts/<sid>.json` | No, and it is the most informative line in your report: the adversary threw the test out, so the cell it claimed is a hole again. |
   | Its verdict is `re-seed` | emit's own finding | Yes -- the adversary asked for one re-instantiation and it has not happened. Report the finding; the orchestrator owns the re-dispatch. |
   | It has no verdict at all | emit's own finding | Yes. `rb-challenge` has not judged it. |
   | Its oracle or seed is missing or unparseable, or a capability it needs has no binding | emit's own finding | Yes, and the finding names the file. |

   A pruned package is **information, not an error**, and the first two rows
   are the whole reason this step exists: a run that emits three packages
   from four instances is not a run that lost one -- it is a run reporting
   that one test was thrown out, which is exactly what "87%, one cell lost to
   a rejected scenario" is made of. Say it in those terms. A report that
   lists three paths and says nothing about the fourth instance hides the one
   fact a reader most needs.

## 4. Invariants

1. **You write nothing.** Every artifact under `06-suite/` came from
   `rubrica emit`. If a package's content is wrong, the artifact it was
   compiled from is wrong; fixing the package leaves the artifact wrong and
   the suite unreproducible.

2. **The suite is exactly what emit wrote this run.** You do not restore a
   pruned package, and you do not delete a package emit kept.

3. **Every instance without a package is accounted for in your report**, with
   the scenario named and the reason given -- whether the reason is a defect
   or an ordinary rejection.

4. **Emit's findings are reported verbatim, and attributed upstream.** A
   finding names an artifact and a pointer; passing along that text is worth
   more than your summary of it, because the orchestrator routes the repair
   by the path in the finding.

5. **Nothing you report is invented.** The paths come from emit's stdout, the
   statuses from `02-scenarios.json`, the verdicts from `05-verdicts/`, and
   the gate results from the two commands' exit codes. If you find yourself
   asserting that a package "should" contain something, you have started
   reviewing the suite instead of reporting it -- that review is
   `sample-for-review`'s and `smoke`'s, and neither is yours to run.

Before you report done, run `rubrica validate --stage emit` and then
`rubrica check-refs`. Unlike every judgment stage in this pipeline, a finding
from either one is usually **not** your defect to fix, because you wrote
nothing: it belongs to the stage that produced the artifact the finding
names. What *is* yours is to run both, read them, and report them without
smoothing anything over. Report success only when `rubrica emit`,
`rubrica validate --stage emit` and `rubrica check-refs` all exited 0; on any
other combination, report the exit codes and the findings and let the
orchestrator decide.

## 5. Refusal conditions

Every condition below is one where the correct output is not a completed
suite. The pull on this stage is unlike the judgment stages': there is no
story to invent and no label to defer to, and the tempting error is *repair*
-- one missing field in one package, one path to fix, one small edit that
turns an exit 1 into an exit 0 and a partial suite into a complete one. That
edit is the single most damaging thing this skill can do, and it is
undetectable afterwards: a hand-finished package validates exactly like a
compiled one, and the run that shipped it can never be reproduced from its
own artifacts again.

- **`rubrica emit` reports findings.** Report them verbatim and stop. Do not
  repair a package by hand: the finding names an *upstream* artifact -- an
  oracle, a verdict, a capability's binding in the world model -- and editing
  the package leaves that artifact wrong while making the suite disagree with
  the run that produced it. The orchestrator's one bounded repair is a
  re-dispatch of the stage that owns the named artifact, followed by a
  re-emit, and you do not get to substitute an edit for it.

- **`emit` pruned a package you expected to see.** Report which scenario and
  its status, and do not treat the absence as a failure to investigate
  further. A `rejected` scenario's package is *supposed* to be pruned; so is
  a `duplicate`'s, and so is one whose verdict is `reject`. The honest report
  is "three packages emitted; `scn-x` pruned, verdict `reject`", not "three
  of four packages emitted" and not a fourth package written to make the
  count look right.

- **`rubrica emit` exits 2.** Report it as a harness problem. Exit 2 means
  the run directory or an artifact could not be read at all -- a mistyped
  path, an unreadable file -- so no repair prompt fixes it and re-running the
  stage cannot help. Do not retry it hoping for a different answer and do not
  fall back to writing anything by hand.

- **Emit exits 1 with an `[internal]` finding telling you to run
  `validate --stage <stage>`.** That is layer 1 having been skipped, not a
  defect in the suite: emit indexes schema-required keys directly and one of
  the artifacts it read is malformed in a way `validate` must reject first.
  Run `rubrica validate --stage instantiate` and `rubrica validate --stage
  challenge`, report what they name, and leave the repair to the stage that
  owns the artifact. Emitting again against the same malformed input produces
  the same finding.

- **You are about to edit, create, or delete a file under `06-suite/`.**
  Stop, whatever the reason -- a missing verifier, a package for a scenario
  that should not have shipped, a field you are sure is wrong. This is the
  refusal condition the whole skill is built around, and the reason it needs
  stating is that every instance of it looks locally helpful and leaves no
  trace. If the suite on disk is wrong, the artifact it was compiled from is
  wrong or emit is wrong; both are reports to make, and neither is repaired
  by a file you write here.
