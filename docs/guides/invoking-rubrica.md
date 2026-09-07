# Invoking rubrica

`rubrica` is run from a shell, and there are two ways to run it. **Stage by
stage:** `uv run rubrica …` for the stages that are code, and
`./scripts/dispatch-stage.sh …` for the stages that are a prompt, one dispatch
at a time. **Or in one step:** hand an agent
`src/rubrica/skills/rb-orchestrate/SKILL.md` and a run directory, and it
dispatches the prompt stages from `extract` through `emit` itself, gating each
artifact before the next stage sees it and stopping at each human gate.

These runs dispatch a model. They cost money, they are not deterministic, and
they need credentials — which is why they live behind the `live` pytest marker
(`tests/conftest.py`) and `make live`, and are never part of `make test`.

This document is the reference for both, and it is about mechanics: the flags,
the environment variables, what a dispatch is handed and what it is denied.
Order appears below only where a mechanism depends on it — a repair that has to
precede the re-run it repairs, say — and never as the run's sequence:
[`docs/getting-started.md`](../getting-started.md) walks a run in order, and
`paths.STAGES` with [`docs/concepts/pipeline.md`](../concepts/pipeline.md) is
the ordering itself. Two readers were in mind: someone exercising a skill they
have just changed, and someone debugging a stage that misbehaved in a real run.
Both need it to work by copy-paste, not by paraphrase, so every command below
has been run against this repository's toy fixture before this file was
committed.

## 1. The two invocation types

Which one to use is not a matter of taste — it is what you are measuring. A
whole-pipeline `rb-orchestrate` run measures the pipeline; one stage dispatched
by itself measures that stage, and is the only way to give each fan-out member
its own read isolation, for the reason §6 gives. `rb-orchestrate` is also not
a stage: it declares no `stage` and no `schemas`, and it never runs `survey`,
never dispatches a pass of the triage family and never holds gate 0 — all three
are finished before it is handed a run at all.

Every stage is one or the other, and the split is in the code rather than
editorial: `skills.CODE_ONLY_STAGES` is exactly the set with no skill file for a
dispatch to point at. A `code` row is invoked with `uv run rubrica` (§3 has the
conventions); a `prompt` row with `./scripts/dispatch-stage.sh` (§4), or by
`rb-orchestrate` on your behalf where it dispatches that stage at all. `$RUN`
below is the run directory throughout, and `dispatch-stage.sh` is
`./scripts/dispatch-stage.sh`.

| Stage | Runs as | Invocation |
|---|---|---|
| `survey` | code | `rubrica survey --corpus … --runs-dir …` (mints the run) |
| `triage-slices` | code | `rubrica triage-slices --run "$RUN"` |
| `triage-objective` | prompt | `dispatch-stage.sh triage-objective "$RUN"` |
| `triage-rule` | prompt | `dispatch-stage.sh triage-rule "$RUN" <slice_id>` |
| `triage-audit` | prompt | `dispatch-stage.sh triage-audit "$RUN"` |
| `triage-seal` | code | `rubrica triage-seal --run "$RUN"` |
| `intake` | code | `rubrica intake --run "$RUN"`, or `--input …` to mint a run |
| `extract` | prompt | `dispatch-stage.sh extract "$RUN" <artifact_id>` |
| `reconcile-subjects` | prompt | `dispatch-stage.sh reconcile-subjects "$RUN"` |
| `reconcile-contradict` | prompt | `dispatch-stage.sh reconcile-contradict "$RUN" <subject_id>` |
| `reconcile-capabilities` | prompt | `dispatch-stage.sh reconcile-capabilities "$RUN"` |
| `reconcile-outcomes` | prompt | `dispatch-stage.sh reconcile-outcomes "$RUN"` |
| `reconcile-entities` | prompt | `dispatch-stage.sh reconcile-entities "$RUN"` |
| `reconcile-goals` | prompt | `dispatch-stage.sh reconcile-goals "$RUN"` |
| `reconcile-gaps` | prompt | `dispatch-stage.sh reconcile-gaps "$RUN"` |
| `reconcile-services` | prompt | `dispatch-stage.sh reconcile-services "$RUN"` |
| `synthesise-interfaces` | code | `rubrica synthesise-interfaces --run "$RUN"` |
| `reconcile-seal` | code | `rubrica reconcile-seal --run "$RUN"` |
| `propose-batches` | code | `rubrica propose-batches --run "$RUN" --round N` |
| `propose` | prompt | `dispatch-stage.sh propose "$RUN" <batch_id>` |
| `propose-seal` | code | `rubrica propose-seal --run "$RUN"` |
| `score` | prompt | `dispatch-stage.sh score "$RUN"` |
| `score-seal` | code | `rubrica score-seal --run "$RUN" --round N` |
| `instantiate` | prompt | `dispatch-stage.sh instantiate "$RUN" <scenario_id>` |
| `challenge` | prompt | `dispatch-stage.sh challenge "$RUN" <scenario_id>` |
| `emit` | prompt | `dispatch-stage.sh emit "$RUN"` |
| `smoke` | code | `rubrica smoke --run "$RUN" --agents <path>` |

An invocation ending in an id is a fan-out: one dispatch per id, and §4's
table says which file each id is read out of. The rows are `paths.STAGES` in
order, but what the table is *for* here is which invocation each stage takes,
and reading it as the run's sequence would mislead twice over: `survey` and the
`triage-*` family run before `intake` mints a manifest, and `02a` through `03b`
are a loop.

## 2. What both invocation types need first

**The venv has to be on `PATH`.** Every skill's Invariants section tells the stage
to run a bare `rubrica …`, and `README.md` says commands assume the venv is on
`PATH`. Measured without it: the stage reaches for `uv run rubrica`, which wants a
writable uv cache it does not have, and spends its entire budget thrashing on
that instead of on its artifact. The script exports it.

By hand the same choice is yours: with `.venv/bin` on `PATH` the commands in this
document read as `rubrica …`, and without it every one of them needs an explicit
`uv run` prefix (`uv run rubrica validate --run "$RUN" --stage extract`). The two
are interchangeable for a command you type; they are not for a stage you
dispatch, which is what the measurement above is about.

### The exit-code contract

Every subcommand exits one of three codes, and so does `dispatch-stage.sh`. The
code is the interface — `rb-orchestrate` branches on it — so route each one
rather than reading past it:

| Code | Meaning | What to do |
|---|---|---|
| `0` | clean | continue |
| `1` | findings, one per line on stdout | a repairable stage defect: worth one re-dispatch, carrying the gate's stdout verbatim (`RUBRICA_FINDINGS_FILE`, §4) |
| `2` | usage error, or an unreadable/misconfigured run | retrying cannot help; fix the run or the invocation |

Two invariants hold across that table, and both have been violated in this
repository before: **a stage defect must never surface as `2`**, and **a `1` must
never have empty stdout.** A third, learned the same way: a `1` must name the
right artifact. `dispatch-stage.sh` exits `2` for a missing `claude` or `jq` for
exactly this reason — a missing tool is the harness and not the stage, so the
one repair attempt an orchestrator has should not be spent re-running a stage
whose output was never the problem.

### The environment overrides the package reads

Four, each exercised by a test. Prefer them to editing repository files when you
are probing behaviour:

| Variable | Read by | What it moves |
|---|---|---|
| `RUBRICA_SCHEMA_DIR` | `validate.py` | the directory layer 1 loads its schemas from |
| `RUBRICA_SKILLS_DIR` | `skills.py` | the directory `discover()` and `check-skills` read skills from |
| `RUBRICA_SUITE_DIR` | `emit.py` | the suite template (`verify.py`, `test.sh`) `emit` compiles from |
| `RUBRICA_LIVE` | `tests/conftest.py` | whether the `live`-marked tests run (§8) |

Every other `RUBRICA_*` variable in this document belongs to
`scripts/dispatch-stage.sh` and is listed in §4; nothing inside the `rubrica`
package reads any of those.

## 3. `uv run rubrica …`, for a stage that is code

[`docs/reference/cli.md`](../reference/cli.md) is the per-subcommand reference —
every flag and an example each, held to `cli.SUBCOMMANDS` by
`tests/unit/test_docs_accuracy.py`. What is worth knowing before you open it is
the handful of conventions every subcommand shares:

- **`--run` is the run directory**, and everything takes it except the two forms
  that mint a run: `survey --corpus … --runs-dir …` and `intake --input …` both
  *print the new run directory on stdout*, which is why they are usually written
  `RUN=$(rubrica intake …)`. `intake --run "$RUN"` is the other form — the one
  that mints `manifest.json` for a run `survey` already created, after gate 0.
- **`--stage` is a stage name, never a path.** `validate --stage` and
  `record-stage --stage` both take a `paths.STAGES` entry, and the choices are
  built from that list, so a stage the pipeline does not have is a `2` from
  argument parsing rather than a confusing check failure later.
- **`--round` is the loop's round, 1-based.** `propose-batches --round N` and
  `score-seal --round N` are the two that need it; the round is part of the path
  they write (`02-batches/round-N.json`, `03-score/round-N.json`), so passing the
  wrong one writes a real artifact in the wrong place.
- **stdout is the interface, stderr is for humans.** A check's findings go to
  stdout one per line; the reports (`gate-brief --gate N`, `claim-utilisation`,
  `run-summary`, `target-brief`) print their whole document there and exit `0` on
  a readable run, because they are reports and not gates. Tracebacks and
  diagnostics go to stderr, where a machine parsing stdout is unaffected.
- **`record-stage` and `set-limit` write provenance, not artifacts.** Each is how
  a decision gets on the record — a stage's model, effort and skill digest, or a
  raised ceiling with its reason in `decisions.md` — so neither is optional
  bookkeeping you can do afterwards from memory.

## 4. `./scripts/dispatch-stage.sh …`, for a stage that is a prompt

§§7–8 are the manual runbook and stay the reference. `scripts/dispatch-stage.sh`
automates them, and adds the thing a hand dispatch cannot: it runs the stage in a
Claude Code instance that shares nothing with the developer's own setup.

### What it needs

It needs two tools the rest of this repository does not: the `claude` CLI and
`jq`. Both are checked before anything is dispatched, and a missing one exits `2`
naming it — the same code an unreadable run gets, since in both cases retrying
cannot help. `scripts/audit-reads.sh` needs `jq` too. Neither tool is a
dependency of the `rubrica` package, and `make setup` does not install either.

### Arguments

```
./scripts/dispatch-stage.sh <stage> <run-dir> [slice-id]
```

- **`<stage>`** is a `paths.STAGES` name with no `rb-` prefix; the script resolves
  it to `src/rubrica/skills/rb-<stage>/SKILL.md`. A stage with no skill file
  exits `2` and prints every stage that has one, `rb-orchestrate` excluded
  because it dispatches stages rather than being one.
- **`<run-dir>`** is resolved to an absolute path, and becomes the dispatch's
  *cwd* — the run directory, deliberately not the repository, so that
  `manifest.inputs[].source_path`, which is repo-relative, cannot resolve back to
  the original fixture file even by accident.
- **`[slice-id]`** is a fan-out member's own id and nothing else. Only a fan-out
  stage accepts one; any other stage exits `2` saying it is a single dispatch
  over everything.

### The slice id each fan-out stage takes, and where to read it from

| Stage | Address line | Where the ids come from |
|---|---|---|
| `extract` | `Your artifact_id:` | `jq -r '.inputs[].artifact_id' "$RUN"/manifest.json` |
| `triage-rule` | `Your slice_id:` | `jq -r '.slices[].id' "$RUN"/00-slices.json` |
| `reconcile-contradict` | `Your subject_id:` | `jq -r '.subjects[].id' "$RUN"/01-subjects.json` |
| `propose` | `Your batch_id:` | `jq -r '.batches[].id' "$RUN"/02-batches/round-N.json` |
| `instantiate`, `challenge` | `Your scenario_id:` | `jq -r '.scenarios[] \| select(.status=="active") \| .id' "$RUN"/02-scenarios.json` |

**The two columns disagree on purpose, and that is the trap.** The address line
handed to a member is always qualified — `Your subject_id:`, `Your batch_id:` —
while the field it is read out of is bare `id` everywhere except
`manifest.json`, whose inputs carry `artifact_id`. So
`jq -r '.subjects[].subject_id'` does not fail: it prints one `null` per subject,
which looks like a run with no ids rather than like a wrong query.
[`docs/design/limitations.md`](../design/limitations.md)'s entry "An id field is
bare where a thing is defined and qualified where it is referenced" carries the
ruling for why neither side is being renamed.

### Worked examples

```bash
# the checkpoint is still the stage *before* the one under test -- §7's table
RUN=$(PYTHONPATH=. uv run python /tmp/toy-run-to.py /tmp/rubrica-lab/runs intake)
./scripts/dispatch-stage.sh extract "$RUN" api-json     # fan-out: own slice id
./scripts/audit-reads.sh /tmp/rubrica-lab/transcripts/extract-api-json.jsonl

# the barrier takes no slice id, and needs a run built one checkpoint later
RUN=$(PYTHONPATH=. uv run python /tmp/toy-run-to.py /tmp/rubrica-lab/runs extract)
./scripts/dispatch-stage.sh reconcile-subjects "$RUN"

# the contradiction sweep is a fan-out over the cover that pass just wrote: one
# member per subject in 01-subjects.json, each given only its own subject_id.
# Read the ids out of that file: over the toy world the cover's subjects are
# sub-cap-find-tickets, sub-cap-get-ticket, sub-ent-ticket, sub-ent-comment,
# sub-actors-and-goals and sub-uncited, and sub-cap-get-ticket is the one whose
# claims actually disagree -- the interesting member to exercise first
./scripts/dispatch-stage.sh reconcile-contradict "$RUN" sub-cap-get-ticket

# triage-objective is also a barrier -- no slice id -- and every triage pass
# precedes intake, so the run comes from a real `rubrica survey` rather than the
# toy-run-to.py builder of §7
RUN=$(uv run rubrica survey --corpus <path> --runs-dir /tmp/rubrica-lab/runs \
  --target-name ticketq --target-interface mcp --objective breadth)
uv run rubrica triage-slices --run "$RUN"                    # code, not a dispatch
./scripts/dispatch-stage.sh triage-objective "$RUN"
uv run rubrica validate --run "$RUN" --stage triage-objective  # the gate: layer 1
uv run rubrica check-refs --run "$RUN"                         # then layer 2
```

### The environment it reads

| Variable | Default | What it does |
|---|---|---|
| `RUBRICA_LAB` | `${TMPDIR:-/tmp}/rubrica-lab` | scratch dir for the settings files, the composed prompt, the sandbox probe log and the transcripts |
| `RUBRICA_MODEL` | `sonnet` | the dispatch's model |
| `RUBRICA_EFFORT` | `medium` | the dispatch's effort |
| `RUBRICA_BUDGET` | unset — no ceiling at all | `--max-budget-usd`; see the cost part below for why it has no default |
| `RUBRICA_NO_SANDBOX` | unset | omit the sandbox block entirely (§6) |
| `RUBRICA_REQUIRE_SANDBOX` | unset | refuse the dispatch (exit `2`) rather than fall back when the sandbox probe fails (§6) |
| `RUBRICA_RESEED` | unset | carry a `re-seed` verdict's two fields into an `instantiate` re-dispatch (§9) |
| `RUBRICA_REJECT` | unset | space-separated scenario ids whose rejection is carried into a `score` re-dispatch, verbatim |
| `RUBRICA_FINDINGS_FILE` | unset | path to a file holding a gate's stdout, appended to a repair re-dispatch verbatim. A **file**, never a string |
| `RUBRICA_PRINT_SETTINGS` | unset | write both settings files and the prompt, print their three paths, dispatch nothing |
| `RUBRICA_PRINT_TRANSCRIPT` | unset | as above, then print the transcript path this dispatch would write, dispatch nothing |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | `64000` | Claude Code's own variable, not this project's, pinned here so a run's output ceiling is on the record |

**Why that last one is pinned rather than inherited.** Measured on Claude Code
2.1.247 against a local recorder that logs the request body and answers 400, so
nothing was generated and the sweep cost nothing: with the variable unset the
client's `max_tokens` is `64000` for the alias `RUBRICA_MODEL` defaults to and
`32000` for `aws/claude-sonnet-4-6` — the default moves with the model id, so
which ceiling a run got was being decided outside this repository. That `32000`
is what killed `propose` round 2 on `run-20260825-094033`. The same sweep closes
the obvious way the pin could be a fiction: a 643240-byte request body still went
out under `64000`, so the client does not shrink the ceiling to fit what is left
of the window. Values are sent verbatim up to the client's own clamp at `128000`.

`RUBRICA_MODEL` and `RUBRICA_EFFORT` set the dispatch's model and effort
(`sonnet`, `medium`); `RUBRICA_LAB` moves the scratch directory that holds the
generated settings and the transcripts. The model and effort you used are what
`record-stage --model/--effort` should then be given, per §8 — and for the `triage-objective` dispatch above, note them down:
that run has no manifest yet, so §8's `record-stage` for it cannot run until
`intake --run` has minted one after gate 0.

### Print modes: settings, prompt, transcript path

`RUBRICA_PRINT_SETTINGS=1` writes both settings files and exits before
dispatching, which is how `tests/unit/test_dispatch_harness.py` checks the deny
lists without spending a model call — and how to check them by hand:

```bash
RUBRICA_PRINT_SETTINGS=1 ./scripts/dispatch-stage.sh propose "$RUN" b01   # prints both paths
```

It prints three lines in a fixed order — the `--settings` file holding
`permissions`, the isolated user settings holding `sandbox`, and the composed
prompt — the third of which the comment above predates.

`RUBRICA_PRINT_TRANSCRIPT=1` stops one step later and prints one line, the
transcript path this dispatch would write. Both modes exist for the same reason:
every other way of checking these either costs a model call or greps the script's
source, and a test that greps the source passes when the rule is present and
unreachable.

### Transcripts, and the closing summary

The transcript is `$RUBRICA_LAB/transcripts/<stage>[-<slice-id>].jsonl`, written
by `tee` as the dispatch streams, so it exists whether the dispatch finishes or
not. **A prior attempt is never overwritten:** a second dispatch of the same
stage and slice becomes `-2`, then `-3`. Measured cost of the previous
behaviour — `propose` round 2's transcript overwrote round 1's on
`run-20260825-094033`, destroying the only per-attempt record of the failure that
motivated the bounded-batch change. The first attempt keeps the unsuffixed name,
because that is the path the closing summary prints and `audit-reads.sh` is
pointed at.

That summary is the script's last output and names five things: the
`transcript` path, the `cost` line below, whether the `sandbox` was `on` or
`off -- <reason>`, the two `gates` commands to run next (`rubrica validate
--stage <stage>` and `rubrica check-refs`), and the `read audit` invocation.
The audit is `./scripts/audit-reads.sh <transcript>`: it prints every file tool
call and every Bash line the dispatch made, for reading against the stage's
Contract `reads`. §6 is why that is the only instrument there is, rather than
housekeeping.

### What a dispatch cost

**`RUBRICA_BUDGET` has no default, and that is deliberate.** Set it and the
dispatch runs under `--max-budget-usd`; leave it unset, which is the normal case,
and no dollar ceiling is imposed at all. A ceiling does not slow a dispatch down,
it kills it where it stands, and both times one has been observed doing that here
it cost more than it saved: `summary.py`'s `orphaned_temp_files` docstring records
a ceiling killing a reconcile pass mid-write, leaving a `02-scenarios.json.tmp.*`
that had to be removed by hand, and the `reconcile-subjects` dispatch in issue #18
spent 38 turns and $3.72 of a $10 ceiling without writing an artifact. Neither is
visible in the run afterwards, because a killed dispatch and a refusing one leave
identical evidence: nothing.

What you get instead is the spend on every dispatch. The script's closing summary
carries a `cost` line naming the dollars, the turns and which ceiling was in force
— `none` unless you asked for one — read back out of the transcript's own `result`
line rather than counted here. Two shapes of transcript cannot answer it: one from
a dispatch killed mid-stream, and one whose result line carries no totals. Both
report `unread` and neither changes the script's exit code, which matters because
that code is what an orchestrator branches on.

This one *is* shipped, unlike §7's five-line toy-run builder, and the difference
is worth stating because the reasoning there was that a mapping table is cheaper
to retype than to maintain. This script is the opposite case: it is a hundred
lines of exact flags, two of which are load-bearing in a way nobody would
reconstruct from memory, and getting one wrong fails silently rather than loudly.

## 5. What a dispatch carries

[`docs/concepts/artifact-contract.md`](../concepts/artifact-contract.md) carries
this rule, in its first section, "The one architectural rule". The form worth
memorising:

> A dispatched subagent receives exactly three things: the run directory path,
> its stage name, and its skill. No conversational context is threaded
> through. That is what makes the contract real.

Nothing else may be passed — no summary of what an earlier stage concluded, no
excerpt from this repository's own documentation, no "by the way, the world
model says...". If the subagent needs a fact, it must get it by reading an
artifact its skill's Contract block lists under `reads`, because the artifact
contract is the only channel this system trusts. A dispatch that pastes in
"helpful" context has silently removed the fan-out isolation the design relies
on, and the resulting artifact will still validate — so this is a rule to
follow, not something `validate` will ever catch for you.

### The slice line, for a fan-out member

**The slice line is for the fan-out stages, and it is an address rather than
context.** A member of a fan-out has to be told which slice is its own or it
cannot find its work at all: `rb-triage-rule` needs `Your slice_id:`,
`rb-extract` needs `Your artifact_id:`, `rb-reconcile-contradict` needs
`Your subject_id:`, `rb-propose` needs `Your batch_id:`, and `rb-instantiate`
and `rb-challenge` each need `Your scenario_id:`. Omit the line entirely for `rb-triage-objective`,
`rb-triage-audit`, the other `rb-reconcile-*` passes, `rb-score` and `rb-emit`,
which are single
dispatches over everything. Give the member its own id and nothing about any
other slice — a sibling's id, or a hint about what a sibling found, is exactly
the context leak the rule above forbids. `rb-orchestrate`'s own §3 A1 states
the same rule from the dispatcher's side, and this line was missing from the
template while all four fan-out exercises run so far had to add it by hand.

### What may be appended to a *re*-dispatch

Nothing may be added to a first dispatch. A re-dispatch is the exception, and in
each case the payload is fixed by the skill that receives it rather than composed
by whoever dispatches:

| Append | Carried by | The payload, fixed |
|---|---|---|
| a gate's findings, for a repair | `RUBRICA_FINDINGS_FILE=<path>` | that gate's own stdout, read from a file |
| a `re-seed` objection | `RUBRICA_RESEED=1` | the verdict's `alternative_answers` and `notes`, `jq`'d out of `05-verdicts/<sid>.json` (§9) |
| a rejection, for a `score` re-dispatch | `RUBRICA_REJECT="<sid> …"` | each verdict's `uniquely_determined`, `derivable_without_guessing` and `notes` |

[`docs/concepts/artifact-contract.md`](../concepts/artifact-contract.md) names
the first two as the two an orchestrator may append. The rejection notice is a
third, and `rb-score`'s own Inputs section is what names it — "a whole kind of
dispatch rather than an edge case" — because `score`'s `reads` excludes
`05-verdicts/`, so quoted text is the only way a rejection reaches it. All three
are **verbatim machine text**: each is a file, or a `jq` projection of an
artifact, so a paraphrase is not something the harness declines to write, it is
something it cannot express. What is deliberately *not* in the rejection payload
is `rejected_reason` — that enum is `score`'s to choose from the quoted evidence,
and a notice that had already picked from it would be the conclusion-passing the
orchestrator's own rules forbid. An empty or missing `RUBRICA_FINDINGS_FILE` is
exit `2` rather than a silent no-append, because a repair dispatch carrying
nothing is indistinguishable from a first dispatch.

## 6. Isolation, and what only looks enforced

**Why isolation is not tidiness.** The falsifiable claim in this project is that
prompt-carried judgment survives a chain of artifact handoffs. A dispatch that
also carries a global `CLAUDE.md`, whatever plugins and hooks the developer runs,
and *this repository's* `CLAUDE.md`, `README.md` and `docs/` tree is measuring the
skill plus a briefing — and the briefing is the answer key. `docs/` describes
every stage's job, what it reads and what it writes; `tests/fixtures/toy/` is
described elsewhere in this repository as the model answer a skill imitates. A
stage that can read either is not being exercised.

Three mechanisms do it, all per-session, none of which changes anything on disk
outside the scratch directory:

| Mechanism | What it removes |
|---|---|
| `CLAUDE_CONFIG_DIR` | own history, transcripts, plugin set |
| `--safe-mode` | `CLAUDE.md`, plugins, hooks, custom agents and skills |
| `--settings` with `permissions.deny` | `docs/`, `tests/`, `CLAUDE.md`, `README.md`, sibling skills |
| `--settings` with a contract-derived `allow` | every path in `$RUN` that is not one of this stage's declared `writes` |

**The write grant is the stage's own contract, not the run directory.** It used to
be `Write(/$RUN/**)`, which stopped a dispatch escaping the run and permitted
anything inside it — and a dispatch used that too, writing a `compute_weights.py`
helper into the run root. `scripts/stage-write-scope.py` resolves the contract's
`writes` to concrete paths and the script grants exactly those, so an `extract`
member working on `api-json` gets:

```
Write(//$RUN/01-claims/api-json.json)
Edit(//$RUN/01-claims/api-json.json)
```

and nothing else — not a scratch file at the run root, and not a sibling's claims
file, which makes the grant an enforcement of the fan-out isolation rule as well
as of the artifact one. Read stays `Read(/$RUN/**)`: a stage reads widely by
design, and narrowing it would break `check-refs`, which reads artifacts the stage
itself does not.

Where an id cannot be pinned the resolver grants the artifact's own *directory*
rather than failing — a round-parameterised write on a run with no batch plan, or
a hand dispatch with no slice id. A grant that is too tight breaks the dispatch it
was meant to protect, and a denied write surfaces mid-turn as a model working
around it rather than as a clean error. The directory grant still refuses
everything else in the run, which is what the ruling asked for. A resolution that
collapsed to the run root is refused outright rather than granted.

`--safe-mode` does not remove the *built-in* skills, so the script also passes
`--disable-slash-commands`.

**One entry in that deny list is not about the answer key at all.** `WebSearch`
is denied because of the gateway, not the fixture: measured 2026-08-20, a tool
named exactly `WebSearch` in the request makes LiteLLM 1.85.5's
`websearch_interception` rewrite `stream=True` to `stream=False`, so the whole
response is generated before any byte is sent and envoy's ~300s idle timeout
kills the turn with zero bytes at 301.0s. Reconcile never completed until this
was removed. No stage uses `WebSearch`, and denying it here strips it from the
request's tools array (25 → 24, verified on the wire), which is what defeats the
name match — a permission-only block would still advertise the tool and still be
intercepted.

**The two settings scopes are not interchangeable, and this was measured.** On
Claude Code 2.1.227, a `sandbox` block in the file passed to `--settings`
silently stops that same file's `permissions.deny` `Read` rules from being
enforced: no warning, the reads simply succeed. Measured in both directions — the
identical deny list with the sandbox key deleted blocks, and with it added back
does not. So the script writes `permissions` into the `--settings` file and
`sandbox` into the isolated user settings. The two layers also disagree about
precedence, which is why the script builds two path lists from one intent:
`permissions.deny` beats `permissions.allow` unconditionally, so the skills root
cannot be denied wholesale with this stage's own directory re-allowed inside it,
while `sandbox.filesystem` resolves overlaps by the more specific path.

**What is enforced, and what only looks enforced.** The permissions layer is the
one doing the work, and by documented design it covers the file tools and the
file commands Claude Code parses out of a Bash line — *not* arbitrary
subprocesses. A `python -c "open(…)"` is outside it. The `sandbox` block is meant
to close exactly that gap at the OS level, and on the machine this was written on
it did not engage: with `bubblewrap` 0.9.0 and `socat` installed and
`bwrap --unshare-all` working standalone, a Python `open()` still read a
`denyRead` path. `failIfUnavailable` is set so a silent fall-through becomes loud;
`RUBRICA_NO_SANDBOX=1` drops the block.

**The script now probes that layer before configuring it.** It runs
`bwrap --unshare-all --dev-bind / / --proc /proc true`, and when that fails it drops
the sandbox block, says so on stderr, keeps the probe's output under
`$RUBRICA_LAB/sandbox-probe-<stage>.txt`, and records `sandbox off -- <reason>` in
the closing summary. `--proc` is the discriminating part: without it the same
command succeeds on a pod where the sandbox cannot work, which is how the fault
behind issue #18 stayed hidden through seven triage transcripts. The state being
avoided is the middle one — a sandbox configured that cannot engage, where every
Bash command dies including the `rubrica validate` and `check-refs` a stage is
ordered to run, and the dispatch still exits 0.

Set `RUBRICA_REQUIRE_SANDBOX=1` to refuse (exit 2) instead of falling back. Use it
for a measured run: dropping the layer changes what the recording is evidence of,
and the summary line is the only place that difference is written down.

It has since engaged once, and both observations are kept because neither
explains the other. At 2.1.231, against a *file* deny entry
(`$RUN/decisions.md`), a `python3 -c "open(...)"` got
`PermissionError: [Errno 13]` — while the same command against
`$RUN/01-world-model.json`, not denied, returned its contents in the same
configuration. That control matters: a sandbox failing every Bash file read looks
identical to one denying the right path. The 2.1.227 measurement above was against
a *directory* entry. Version or granularity — unknown which accounts for the
difference. So: check that layer on the machine you are using before relying on
it, and read the audit either way.

Which is the point of `scripts/audit-reads.sh`. §8's reading-a-failure part says an
out-of-contract read shows up nowhere on disk, and
[`docs/design/limitations.md`](../design/limitations.md)'s isolation entry
records that both read violations ever observed here surfaced only because a
subagent volunteered them in a report nobody obliged it to write. That is luck,
not an instrument. The transcript is the instrument: the audit prints every file
tool call and every Bash line, and those get read against the stage's Contract
`reads`.

**One thing this approach cannot do.** Subagents share their parent session's
permission and sandbox configuration, so a single instance running
`rb-orchestrate` cannot give each fan-out member a deny list naming only *that*
member's slice. Per-member read isolation needs one process per member, which is
what dispatching stage by stage with this script gives you. A whole-pipeline
orchestrate exercise remains the looser measurement it always was.

**The run directory holds three paths no skill's Contract lists under `reads`,
and the script denies exactly two of them.** `decisions.md`, `07-report.json`
and `measurement/` are each *about* the stages rather than merely outside their
scope — an orchestrator log, a smoke report, and the human review surface — so
granting `Read(<run>/**)` is right for artifacts and wrong for these three. But
the enforceable rule is narrower than "deny what the stage may not read." Four
skills' contracts oblige them to invoke `check-refs`, that subprocess runs
inside the same sandbox as the member, and a denied artifact is invisible to the
*checker* too — which surfaces as an exit `1` naming the wrong artifact, the
same class of defect an unreadable `01-claims/` once produced. So the rule the
script actually applies is **deny only what `check-refs` never reads**:
`decisions.md` and `measurement/` stay denied in both settings scopes, and
`07-report.json` came out, because `refs.py` appends it to the targets it
resolves. `tests/unit/test_dispatch_harness.py` derives that pair from
`refs._readable_targets` rather than trusting the script's own comment.

`decisions.md` is the one that bites. On 2026-08-13 a `propose` dispatch was given
a run whose `decisions.md` carried that stage's own pre-registered predictions,
written there minutes earlier so the reading could not be hindsight. The
transcript shows it running `ls -la` in the run directory: one `Read` from the
answer to its own exercise, and what stopped it was an unrelated premature kill.
So, two rules for scoring a stage by hand:

- **Predictions go where the dispatch cannot read them, never in the run.** On
  disk before the dispatch is the right instinct; inside the dispatch's read
  scope is the wrong destination. `docs/` and `tests/` are both denied in both
  settings scopes, so a note under either is out of reach. Most of `$RUN` is
  not — and the two paths under it that *are* denied are the wrong destination
  anyway, since a prediction filed in the orchestrator's log or the review
  surface is a prediction filed in an answer key.
- **The gate-1 human report is not an artifact either.** Anything you write while
  holding a gate is the orchestrator's, and a later stage reading it has been
  briefed.

None of this makes the deny list the instrument. It narrows the accident; the
audit is still what tells you what the stage read.

## 7. Exercising a stage against a checkpoint

### The dispatch prompt

Copy this verbatim, filling in the placeholders and nothing else:

```
You are the <stage> stage of the rubrica pipeline.

Run directory: <absolute path>
Your skill:    <absolute path to SKILL.md>
Your <slice>:  <id>            # fan-out members only -- see below

Read your skill and follow it exactly. Read only the artifacts your skill's
Contract block lists under `reads`. Write only what it lists under `writes`.
Do not read this pipeline's other stages, other scenarios, or any file the
contract does not name.

When you are done, report only: the paths you wrote, and any refusal
condition you hit.
```

`dispatch-stage.sh` composes exactly this text, with the placeholders filled and
— in the sanctioned cases of §5 — one block appended, and writes it to
`$RUBRICA_LAB/prompt-<stage>[-<slice-id>].txt` on every run rather than only in
print mode, because the prompt is the one dispatch input a transcript does not
let you reconstruct exactly.

### Building a toy run stopped before the stage under test

`tests/toy.py`'s `build_toy_run(runs_dir, upto=...)` mints a run with real
`intake` — or, for the `triage-*` checkpoints, real `survey` — and then writes
every hand-authored artifact up to and including the named checkpoint, never
past it. Handing `rb-reconcile-subjects` a run that already contains
`01-subjects.json` would test nothing, so the checkpoint you build to is always
the stage *before* the one you are exercising:

| Stage under test | `upto=` (the checkpoint just before it) | What the dispatched skill should write |
|---|---|---|
| `rb-triage-objective` | `"triage-slices"`   | `00-objective.json` |
| `rb-triage-rule`      | `"triage-objective"` | `00-dispositions/<slice-id>.json` for the one shard you pointed it at |
| `rb-triage-audit`     | `"triage-rule"`      | `00-audit.json` |
| `rb-extract`     | `"intake"`      | `01-claims/<artifact-id>.json` for the one input artifact you pointed it at |
| `rb-reconcile-subjects` | `"extract"` | `01-subjects.json` |
| any later `rb-reconcile-*` pass | `"extract"`, plus the partials that pass *reads* — see below | that pass's own partial, per [`../reference/artifacts.md`](../reference/artifacts.md). `rb-reconcile-contradict` is a fan-out: give it one `subject_id` |
| `rb-propose`     | `"reconcile-seal"`, then `rubrica propose-batches --round 1` | `02-scenarios/round-N/<batch-id>.json` for the one `batch_id` you pointed it at. The checkpoint stops before the batch plan, because `propose-batches` is code: run it yourself so the plan the member reads is the one the code would have written |
| `rb-score`       | `"propose-seal"` | `03-score/round-N.json` — the rulings, the holes and the verdict, and nothing it can compute |
| `rb-instantiate` | `"score-seal"`  | `04-instances/<sid>/{seed.json,expected.json,rationale.md}` |
| `rb-challenge`   | `"instantiate"` | `05-verdicts/<sid>.json` |
| `rb-emit`        | `"challenge"` (the default — see below) | `06-suite/` (via `rubrica emit`, which the skill invokes; the skill itself writes nothing) |

`rb-orchestrate` is not in this table: it is not a stage, it dispatches them.
Its live exercise is a whole-pipeline run starting from an `upto="intake"`
run, not a single-stage check against one checkpoint — see
`src/rubrica/skills/rb-orchestrate/exercise.md` for its pass criteria.

The `triage-*` family's checkpoints are the one part of the table that does not
go through `intake` at all: `paths.STAGES` puts every one of its passes
*before* it, so `build_toy_run` mints those runs with a real `survey()` over
`tests/fixtures/toy/` and returns before a manifest exists. Two consequences
worth knowing before you use them. The golden world is three files totalling
about four kilobytes of catalogue rows, so at the default slice cap it is a
**single slice** — pass `build_toy_run(runs_dir, upto="triage-objective",
slice_cap=4096)` to get more than one shard, which is what exercising
`rb-triage-rule` as a real fan-out (rather than as one member) requires. And
`triage-seal` is code, not a prompt: build to `upto="triage-audit"` and run
`uv run rubrica triage-seal` against the run directory.

A three-file corpus is also a thin exercise for a pass whose whole job is
scoping judgment. For a real one, mint a run with a real catalogue instead of a
toy one:

```bash
uv run rubrica survey --corpus <path> --runs-dir /tmp/rubrica-lab/runs \
  --target-name ticketq --target-interface mcp --objective breadth
```

This writes `00-catalogue.json` and prints the run directory on stdout — the
checkpoint `rubrica triage-slices` needs, and from there the family runs in
`paths.STAGES` order: `rb-triage-objective` over the slice map, one
`rb-triage-rule` dispatch per shard, `rb-triage-audit` once every member has
landed, then `rubrica triage-seal`.
`tests/fixtures/catalogue-unsupported-objective.json` and
`tests/fixtures/catalogue-all-declinable.json` are two committed catalogues that
should make a pass of it refuse; copying either one over a freshly-minted run's
`00-catalogue.json` exercises those refusals without a corpus at all.

**The reconcile family has a few checkpoints, not one per pass.**
`"reconcile-gaps"` is every partial the seal *requires* written with no world
model yet — so it is also the state that shows the seal omitting its optional
`services` key — `"reconcile-services"` adds `01-services.json` to that,
`"synthesise-interfaces"` adds the `01-interfaces/` documents the real code derives
from it, and
`"reconcile-seal"` is the assembled world model — the states the seal and the
later stages are tested against. None of them is the checkpoint a *middle* pass
needs, because each includes that pass's own output. So to exercise one middle
pass, build to `"extract"` and write only the partials it declares under `reads`,
taking them from `tests/toy.py`'s `split_world_model()`, which cuts the golden
world model into exactly those files:

```python
from rubrica.artifacts import write_json
from tests.toy import build_toy_run, split_world_model

run = build_toy_run(runs_dir, upto="extract")
parts = split_world_model()
write_json(run.subjects, parts["subjects"])            # what -contradict reads
write_json(run.capabilities_part, parts["capabilities"])  # what -outcomes reads
```

Writing a partial the pass under test is supposed to produce is the same
mistake as building one checkpoint too far: it tests nothing, and layer 1 will
pass either way.

`upto=None` (the default, i.e. omitting the keyword) writes everything the
fixture knows how to write, through `challenge` — exactly the checkpoint
`rb-emit` needs, since `build_toy_run`'s `_UPTO_STAGES` stops there (the
fixture writes nothing for `emit` or `smoke`: no suite package, no report). An
`upto` value outside `_UPTO_STAGES` — including a real `paths.STAGES` entry
this fixture does not model, such as `"emit"` — raises `ValueError` rather
than silently building the wrong thing.

The script, in full:

```python
# build a toy run stopped before the stage under test.
# Run as: PYTHONPATH=. uv run python /tmp/toy-run-to.py <runs-dir> <upto-or-None> [slice-cap]
#
# PYTHONPATH=. matters: tests/ is a package (tests/__init__.py) that pytest's
# rootdir insertion makes importable during a test run, but this script is not
# pytest, so it needs the repository root on sys.path explicitly.
import sys
from pathlib import Path

from tests.toy import build_toy_run

runs_dir = Path(sys.argv[1])
upto = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "None" else None
# The third argument is only accepted for a triage-* checkpoint: build_toy_run
# raises rather than silently ignoring a cap on a run that has no catalogue.
extra = {"slice_cap": int(sys.argv[3])} if len(sys.argv) > 3 else {}
run = build_toy_run(runs_dir, upto=upto, **extra)
print(run.root)
```

This is a throwaway script, not a shipped one (hence `/tmp`, not `scripts/`):
the mapping table above is the reusable part, and five lines are cheaper to
retype than to maintain as a committed CLI. Run it, then dispatch the prompt
template above with `<absolute path>` set to the printed run directory.

## 8. Verification, reading a failure, and the live suite

### The verification commands

After the subagent reports done, run these against `$RUN` (the run directory
from §7) for the stage you dispatched:

```bash
RUN=<the run directory from §7>
STAGE=<stage>  # e.g. triage-objective, extract, reconcile-subjects, propose, score, instantiate, challenge, emit
               # the loop's three code steps are not dispatched: run `rubrica
               # propose-batches`, `propose-seal` and `score-seal` yourself

uv run rubrica validate --run "$RUN" --stage "$STAGE"   # expect 0
uv run rubrica check-refs --run "$RUN"                  # expect 0
uv run rubrica record-stage --run "$RUN" --stage "$STAGE" \
  --model <model> --effort <effort> \
  --skill src/rubrica/skills/rb-"$STAGE"/SKILL.md
```

`--effort` is one of the values `manifest_stage_efforts()` reads out of the
manifest schema (currently `low`, `medium`, `high`, `xhigh`, `max`) — run
`uv run python -c "from rubrica.validate import manifest_stage_efforts as f; print(f())"`
if that enum ever moves and this line goes stale.

Both `validate` and `check-refs` will fail on the *unwritten* checkpoint you
built in §7 — that is expected, since the stage's artifact does not exist yet.
"Expect 0" applies only after the dispatched skill has actually written its
artifact.

**A fan-out stage is the second exception, and unlike the first it does not go
away once the artifact is written.** A dispatch carries exactly one slice id —
one `slice_id`, `artifact_id`, `subject_id`, `batch_id` or `scenario_id` — so
exercising a fan-out by hand dispatches *one* member and leaves the fan-out
incomplete by construction, and `check-refs` reports the members that never
landed: `refs.check_manifest`, `check_disposition_parts`,
`check_contradiction_parts`, `check_instances`, `check_verdicts` and
`check_scenario_parts` each report every slice with nothing on disk from the
moment their directory exists. That is the checker working, not a defect in the
skill under test. Read each finding's path and take as yours only the ones
naming *your* member's slice; a lab dispatch of a fan-out therefore expects 0
from `validate`, and from `check-refs` only the absent siblings.

**The `triage-*` passes are the ones whose `record-stage` runs late.**
`record-stage` merges into `manifest.json`, and on a run minted by `survey`
there *is* no manifest until `intake --run` writes it after gate 0 — so at the
moment you have just dispatched a triage pass, the command above raises
`ArtifactError` on the absent manifest at exit 2. Run `validate` and
`check-refs` for each pass when the brief above says to, then come back and
record the dispatched ones **retroactively, after gate 0**, once the manifest
exists:

```bash
# after `uv run rubrica intake --run "$RUN"` has minted manifest.json,
# once per dispatched pass -- triage-slices and triage-seal are code and have
# no skill file, so they take no record-stage entry at all
uv run rubrica record-stage --run "$RUN" --stage triage-objective \
  --model <the model you dispatched> --effort <the effort you used> \
  --skill src/rubrica/skills/rb-triage-objective/SKILL.md
```

The alternative — having the triage record carry its own provenance — was
considered and rejected: a model-invented skill digest is precisely what
`record-stage` exists to prevent, since the whole point of the hook is that the
recorded hash is of the file that was actually used. Recording retroactively
keeps the digest checkable, at the cost of the ordering. Write down which model
and effort you dispatched at the time; nothing on disk remembers them for you
until you run the command.

`survey` is *not* the other half of this. It is code, not a prompt: there is no
`rb-survey/SKILL.md` for `record-stage --skill` to hash, so `survey` never gets
a `manifest.stages` entry at all — the same as `intake` and `smoke`, and its
absence there is not a finding.

`record-stage --skill` needs a real file to hash and hard-fails
(`UsageError: skill file does not exist`) if it is not there. Every
`src/rubrica/skills/rb-<stage>/SKILL.md` above exists in this repository, so
each path resolves as written. `record-stage` hashes whatever file it is
given, so the recorded digest is only meaningful when it names the file that
was actually used.

### Reading a failure

The three checks above have three different owners. Route the failure to
whichever one actually needs to change:

- **A `validate` (schema) failure** usually means the skill's **Output**
  section is unclear — the model wrote something structurally different from
  what the schema requires. Fix the skill's prose, not the schema.
- **A `check-refs` failure** usually means the skill's **Invariants** section
  is missing a constraint — the artifact is well-formed JSON that satisfies
  the schema but breaks a cross-artifact rule (a dangling reference, a seed
  that does not conform to the world model, an unreachable scenario) the
  Invariants section should have told the model to maintain. **Route it there
  only if it names your own member's slice.** A finding naming a sibling you
  never dispatched is the single-member incompleteness described above, and no
  wording in the skill under test can remove it.
- **Nothing written, a refusal reported** may well be **correct**. Before
  treating it as a defect, check whether the refusal condition the subagent
  cited actually holds in the toy world: if it does, the skill did its job and
  the exercise passes (record which condition fired). If the condition does
  not hold, the skill's refusal conditions are over-broad and need narrowing.

One more failure mode, not raised by `validate` or `check-refs` at all: **the
subagent read an artifact outside its `reads` list.** Nothing on disk shows
this — the resulting artifact still validates — so it can only be caught by
reading the subagent's own report against the Contract block. This is the
isolation failure §5's rule exists to prevent, and it is graded as Important,
not Minor, if it happens.

### Running the live exercises as a suite

```bash
uv run pytest --markers | grep live      # confirm the marker is registered
uv run pytest -m live -q                 # skipped by default; run under RUBRICA_LIVE=1
                                          # (or `make live`). They assert against committed
                                          # recordings, so running them is free -- producing
                                          # a recording is what costs money.
RUBRICA_LIVE=1 uv run pytest -m live -q  # opt in. "", "0", "false", "no" (any
                                          # case, surrounding whitespace ignored)
                                          # do NOT opt in -- everything else does.
```

`tests/unit/test_live_marker.py` proves both directions of the skip mechanically,
including that those off-spellings stay off: a live test dispatches (and bills
for) a model, so `RUBRICA_LIVE=0` must not be the thing that turns it on.
The exercises above are run by hand, one skill at a time, following §5, §7 and §8 — they
are not `-m live` pytest tests themselves, because a live exercise's pass
criteria are read by a person, not asserted by an
`assert` statement.

## 9. Re-dispatching a `re-seed` by hand

`rb-challenge` can return `re-seed` for an instance, and `rubrica emit` refuses to
compile one — it reports a finding no further stage can clear. The repair is a
single re-dispatch of `rb-instantiate` for that scenario, carrying the adversary's
objection. That objection is one of exactly **two** things an orchestrator may
append to a dispatch, and the payload is fixed by two skills that agree on it:
`rb-orchestrate`'s named exception for a `re-seed` re-dispatch and
`rb-instantiate` §1 both say the verdict's **`alternative_answers` and its
`notes`** — not the verdict string, not `uniquely_determined`, not the flags.

```bash
RUBRICA_RESEED=1 ./scripts/dispatch-stage.sh instantiate "$RUN" scn-005
```

The block is extracted with `jq` straight from `05-verdicts/scn-005.json`, so a
paraphrase is not something the script declines to write — it is something the
script cannot express. That distinction is the point:
[`docs/concepts/artifact-contract.md`](../concepts/artifact-contract.md) calls a
paraphrased notice "the orchestrator's conclusion wearing a finding's clothes",
and the only structural defence is to make the appended text a copy rather than a
rendering. The flag refuses with exit 2 on a verdict that is not `re-seed`, on a
stage other than `instantiate`, and on a missing verdict file, because inventing an
objection is the same defect as paraphrasing one.

**Do not try to enforce that with a deny rule.** `rb-instantiate`'s §1 says the
directory is not in its `reads`, and the obvious move is to add `05-verdicts/` to
the harness deny list for that stage. It was tried, on 2026-08-13, and it broke the
member's own gate: `rb-instantiate`'s contract obliges it to invoke `check-refs`,
that subprocess runs inside the same sandbox, and a denied path is masked to a
character device — so `check-refs` saw no verdicts and reported ten fabricated
`instance scn-XXX has no verdict` findings while the identical command outside the
sandbox exited 0. Same failure this repository already records for an unreadable
`01-claims/`.

**The rule that came out of it:** never deny a run path `check-refs` reads. Most
skills invoke it (every `reconcile-*` pass, `instantiate`, `score`, `emit`), so in
practice the harness can only deny what `refs.py` never looks at — `decisions.md` and
`measurement/`. Whether a member *should* read `05-verdicts/` is a prompt-level
obligation, and the transcript audit is what checks it.

An empty `alternative_answers` is a *shape*, not a missing value: paired with
populated `notes` it means the defect was not ambiguity at all — an undeclared
call, or a disputed oracle — and the notes carry the whole reason. The script
passes the field through empty rather than omitting it, so the member can tell
which of the two shapes arrived.

After re-seeding, re-challenge that scenario and only then re-run `emit`. A second
`re-seed` verdict is not another repair: `rb-orchestrate`'s rule for a second
`re-seed` is to stop re-seeding and treat it as a rejection, because `emit`
refuses a `re-seed` no matter how many rounds produced it.

To inspect what a dispatch *would* send without spending anything:

```bash
RUBRICA_PRINT_SETTINGS=1 RUBRICA_RESEED=1 \
  ./scripts/dispatch-stage.sh instantiate "$RUN" scn-005   # prints 3 paths, dispatches nothing
```

The third path is the composed prompt. It is written on every run, not only in this
mode, because the prompt is the one dispatch input a transcript does not let you
reconstruct exactly — and a re-seed run is precisely when you want to prove what
was appended.
