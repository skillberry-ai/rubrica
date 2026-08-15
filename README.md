# Rubrica

Builds a test suite for an agentic system from whatever artifacts describe it —
specifications, captured trajectories, source code — by running a pipeline of
AI skills over a schema-validated on-disk artifact contract.

**This is an experiment.** The question it exists to answer is whether
prompt-carried judgment survives a chain of artifact handoffs well enough to
produce a suite worth running. Design:
[`docs/superpowers/specs/2026-08-06-skill-based-test-generator-design.md`](docs/superpowers/specs/2026-08-06-skill-based-test-generator-design.md).

## What is here so far

Three layers, all of them present. The **contract spine**: the deterministic
components every stage depends on. A **measurement layer** on top of it — four
tools that score, compare, and sample a suite once `emit` has produced one. And
the **nine skills** that carry the pipeline's judgment, across eleven stages
(two of the eleven, `survey` and `intake`, are code, alongside `smoke`). The
whole pipeline has run end to end with a model at every stage, from three
input files to a scored suite whose tasks discriminate between agent roles.

### The skills

Eight stage skills plus the orchestrator, at
`src/rubrica/skills/rb-<name>/SKILL.md`. Each carries one judgment and reads
only what its `## Contract` block declares.

| Skill | The judgment it carries |
|---|---|
| `rb-triage` | Decides what the run can ever know: rules on every catalogued candidate `admit` / `decline` / `needs_projection`, with a reason for every one — not just the ones it kept — and states what the admitted set still cannot cover |
| `rb-extract` | Turns one input artifact into evidence-backed claims, in isolation from every sibling artifact — and grades each claim `stated` / `inferred` / `reverse_engineered` instead of flattening the difference |
| `rb-reconcile` | Merges every extract's claims into one world model, *recording* contradictions and gaps rather than resolving them, and computes the coverage denominator once |
| `rb-propose` | Appends scenarios targeting holes that proposing can actually close — never rewriting or renumbering what an earlier round proposed |
| `rb-score` | Folds the scenario pairs that are one test, computes both coverage matrices, justifies every uncovered row with a hole, and computes the verdict the orchestrator acts on |
| `rb-instantiate` | Designs the distractor set *first*, seeds a world respecting the model's invariants, then derives the oracle from that seed — never the reverse |
| `rb-challenge` | Answers the question from the seed alone before the oracle is ever opened, hunts for a second world-consistent answer, and rules `accept` / `re-seed` / `reject` |
| `rb-emit` | The thin human-facing entry point over `rubrica emit`: runs it, gates what it produced, reports what was pruned. Writes nothing itself |
| `rb-orchestrate` | Not a stage — it dispatches them: what runs next, whether an artifact is good enough to build on, the round loop, the three human gates, at most one repair attempt per failure |

### The code

| Component | Job |
|---|---|
| `paths.py` | Run-directory layout, the single source of truth for artifact paths |
| `artifacts.py` | Atomic, byte-stable canonical JSON I/O |
| `validate.py` | Layer 1: JSON Schema validation per stage |
| `invariants.py` | Evaluates world-model `machine:` invariants over a seed |
| `refs.py` | Layer 2: cross-artifact references, seed conformance, the reachability gate, and cross-checking `07-report.json` against `06-suite/` and the manifest |
| `intake.py` | Stage 0: register + hash + classify inputs, mint the run |
| `dedupe.py` | Candidate duplicate scenario pairs (proposes; never decides) |
| `smoke.py` | `rubrica smoke`: runs the emitted suite against three agent roles, scores with the package's own copied verifier, and gates on the verdict |
| `recall.py` | `rubrica compare-gold`: recall and novelty against hand-authored gold tasks |
| `stability.py` | `rubrica diff-runs`: per-stage Jaccard stability between two runs |
| `review.py` | `rubrica sample-for-review`: a stratified human-review packet |
| `skills.py` | Parses each `SKILL.md`'s `## Contract` block, holds it to the code that owns each name (`rubrica check-skills`), and hashes the file a stage was actually run with |
| `manifest.py` | `rubrica record-stage` and `rubrica decide`: the two writers `manifest.stages` and `decisions.md` were declared without |
| `metrics.py` | The one `jaccard` set-similarity function `recall.py` and `stability.py` both use |
| `errors.py` | `UsageError`, the exception a malformed human-authored config raises so it maps to exit 2 |
| `schema/` | One JSON Schema per artifact kind, plus `agents-0.1.json` and `gold-0.1.json` for the two human-authored config files, shipped as package data |

## Setup

Requires Python 3.13+ and [`uv`](https://docs.astral.sh/uv/).

```bash
make setup     # create the venv, install runtime + dev deps
make test      # run the suite
make check     # ruff lint + format check, no changes
make lint      # ruff check --fix
make format    # ruff format
make help      # every target, with its one-line description
```

There is one more target, `make live`, and it is deliberately not part of
`make test`: it runs the tests whose assertions need a model's output, behind
the `live` pytest marker and the `RUBRICA_LIVE` opt-in (`tests/conftest.py`).
As they stand today those tests assert against **committed recordings** of a live
dispatch (`tests/fixtures/<name>/recorded/`), so running them costs nothing;
producing or re-producing a recording is the part that dispatches a subagent and
costs money. `make test` skips them with a reason naming the command that runs
them, so they are never silently absent.

## Running the pipeline

Before any of that, a run has to exist and its inputs have to be admitted.
`rubrica survey --corpus …` walks a corpus and mints the run, writing
`00-catalogue.json` — one bounded digest per candidate file, never the
candidate's own bytes. `rb-triage` reads only that catalogue and rules on
every candidate, writing `00-triage.json`. **Human gate 0** holds on that
record — reviewed with `rubrica gate-brief --gate 0` — before
`rubrica intake --run <run>` materialises the admitted candidates into
`manifest.json`. This gate is different in kind from the three the
orchestrator holds below: it decides what the run can ever know, since
nothing after `intake` reads the corpus again — `rb-extract` sees only what
was admitted. `intake --input` still works unchanged as the direct path for a
hand-picked input set with no survey or triage step at all.

The stages from there on are prompts, so no command in this repository runs
them. `rb-orchestrate` does: point an agent at
[`src/rubrica/skills/rb-orchestrate/SKILL.md`](src/rubrica/skills/rb-orchestrate/SKILL.md)
with a run directory, and it dispatches one subagent per stage, gates every
artifact before the next stage sees it, holds the round loop and the three human
gates, spends at most one repair attempt per failure, and records each stage and
each branch.

Every dispatch carries exactly three things — the run directory, the stage name,
and the path to that stage's `SKILL.md` — plus, for the three fan-out stages, the
id of its own slice, which is an address rather than context. Nothing else: no
summary of what an earlier stage concluded, no excerpt of the world model. That
is what makes the artifact contract real, and it is a rule to follow rather than
something `validate` can catch — a dispatch that pastes in "helpful" context
removes the fan-out isolation the design was chosen for, and the resulting
artifact still validates.

To run one stage by hand — the way every skill here was exercised —
follow [`docs/running-a-stage-by-hand.md`](docs/running-a-stage-by-hand.md),
which carries the dispatch prompt verbatim plus the per-stage setup and gate
commands.

`scripts/dispatch-stage.sh` automates that runbook and adds the one thing a hand
dispatch cannot: it runs the stage in a Claude Code instance carrying none of the
developer's own configuration, and none of *this* repository's either. That
matters because `docs/` holds the design spec and `tests/fixtures/toy/` is the
model answer a skill imitates — a stage that can read them is being measured
against the answer key. `scripts/audit-reads.sh` then prints every file the
dispatch actually opened, which is the only way an out-of-contract read is ever
visible: it leaves nothing on disk, because a fan-out member that read a
sibling's slice writes a byte-identical artifact to one that did not. §7 of the
runbook covers what each layer does and does not enforce.

## Usage

Commands below assume the venv is on your `PATH` (`make setup` creates it);
otherwise prefix each with `uv run`.

```bash
# Stage 0, path A: hand-pick the inputs yourself and mint a run directly.
# No corpus, no catalogue, no triage record, no gate 0.
rubrica intake \
  --input path/to/api.json \
  --input path/to/schema.json \
  --runs-dir runs \
  --target-name aap2 \
  --target-interface mcp \
  --max-rounds 2 \
  --max-scenarios 128
# --max-rounds and --max-scenarios are optional; those are their defaults.
# prints the new run directory, e.g. runs/run-20260806-123005

# Stage 0, path B: point at a whole corpus instead and let triage decide.
rubrica survey \
  --corpus path/to/corpus \
  --runs-dir runs \
  --target-name aap2 \
  --target-interface mcp \
  --objective breadth
# mints the run and prints its directory, same as intake above, but writes
# 00-catalogue.json rather than a manifest -- there is nothing to extract from
# yet, because nothing has been admitted

# rb-triage is dispatched against that catalogue (see "Running the pipeline"
# above); once its 00-triage.json exists and human gate 0 has held --
# rubrica gate-brief --run runs/run-20260806-123005 --gate 0 -- admission
# finally mints the manifest:
rubrica intake --run runs/run-20260806-123005
# prints the same run directory; --run and --input are mutually exclusive

# After each stage: shape, then references
rubrica validate --run runs/run-20260806-123005 --stage reconcile
rubrica check-refs --run runs/run-20260806-123005

# Feed candidate duplicate pairs to the scoring stage
rubrica dedupe-candidates --run runs/run-20260806-123005

# Every skill's Contract block against the code that owns each name
rubrica check-skills
```

### The human's own subcommands

Two more, neither one a gate itself: `gate-brief` composes what already
exists into the reading surface at any of the four gates, and `set-limit`
changes a manifest limit deliberately, with the reason on record rather than
as a silent hand-edit.

```bash
# The reading surface at gate 0, 1, 2 or 3 -- utilisation and implied size at
# 1, the coverage matrices at 2, the verdict tallies at 3
rubrica gate-brief --run runs/run-20260806-123005 --gate 1

# Raise a ceiling deliberately, with the reason recorded in decisions.md
rubrica set-limit --run runs/run-20260806-123005 --max-scenarios 200 \
  --reason "breadth objective under-covered the tool surface at 128"

# Bring a manufactured projection back into the catalogue, structurally
rubrica adopt-projection --run runs/run-20260806-123005 \
  --projection proj-001 --file path/to/manufactured-tool-schema.json
```

### The two writers the orchestrator uses

`manifest.stages` and `decisions.md` are declared by the design and had no
writer until this build. These are the two subcommands that fill them, and
`rb-orchestrate` is their only caller in a real run.

```bash
# What a stage was run with, merged into manifest.stages
rubrica record-stage --run runs/run-20260806-123005 \
  --stage extract \
  --model claude-opus-5 \
  --effort medium \
  --skill src/rubrica/skills/rb-extract/SKILL.md
# prints the manifest path, and adds:
#   "extract": {"model": "claude-opus-5", "effort": "medium",
#               "skill_sha256": "<sha256 of that SKILL.md>"}
```

The digest is computed here from `--skill` rather than accepted as a string: a
caller that can pass a digest can pass the wrong one, and the hook is only worth
having if the recorded hash is of the file the run actually used. It hashes the
whole file, prose included — a changed Method section changes what the run did.
So a `skill_sha256` that no longer matches the file on disk is the hook working,
not a defect: the skill was edited after that stage ran.

```bash
# One line in the run's append-only notebook, timestamped by the code
rubrica decide --run runs/run-20260806-123005 \
  --note "human gate 1: gap-bad-argument-behavior ruled non-blocking for propose as a whole"
# prints the decisions.md path, and appends:
#   - 2026-08-10T21:58:07Z human gate 1: gap-bad-argument-behavior ruled ...
```

A note that is empty, whitespace-only, or contains a newline is refused at exit
2: a blank entry records that a decision was made and not what it was, and an
embedded newline silently corrupts a format every reader parses one line per
entry.

### Measurement

The four measurement tools take a run that already has a `06-suite/` (and, for
`smoke`, a `07-report.json`) and write nothing into the numbered stage
directories — their outputs live under `measurement/`, outside the pipeline's
own contract, because nothing dispatches them.

`smoke` and `compare-gold` need a human-authored config the pipeline itself
never produces: an agent roster, and a gold benchmark. Here is a complete
three-role roster —

```json
{
  "schema_version": "0.1",
  "agents": [
    {
      "role": "weak_baseline",
      "model": "no-tools-stub",
      "command": ["/path/to/agents/weak_baseline.sh"],
      "notes": "no tools"
    },
    {
      "role": "under_test",
      "model": "claude-sonnet-5",
      "command": ["/path/to/agents/under_test.sh"]
    },
    {
      "role": "oracle",
      "model": "claude-sonnet-5",
      "command": ["/path/to/agents/oracle.sh"],
      "notes": "handed the reference answer"
    }
  ]
}
```

— and a two-task gold benchmark:

```json
{
  "schema_version": "0.1",
  "target": "aap2",
  "tasks": [
    {
      "id": "bench-001",
      "goal_id": "goal-triage",
      "hop_depth": 2,
      "capability_refs": [
        {"capability_id": "cap-find-jobs", "outcome_class_id": "oc-success"}
      ],
      "notes": "the hand-authored triage task scn-001 should match"
    },
    {
      "id": "bench-002",
      "goal_id": "goal-triage",
      "hop_depth": 1,
      "capability_refs": [
        {"capability_id": "cap-find-jobs", "outcome_class_id": "oc-empty"}
      ],
      "notes": "an empty-result triage task the generated suite never produced"
    }
  ]
}
```

Each `command` is a script that reads the task on stdin (or its own arguments)
and writes a stream-json transcript — the same shape `suite/verify.py`
already parses.

```bash
# Run the suite against all three roles, score with the package's own
# verifier, and write measurement/smoke/<role>/<sid>/ plus 07-report.json
rubrica smoke --run runs/run-20260806-123005 --agents agents.json
# runs/run-20260806-123005/07-report.json

# Compare what was generated against the hand-authored gold tasks
rubrica compare-gold --run runs/run-20260806-123005 --gold gold.json
# writes measurement/recall.json + measurement/recall.md and prints only the
# path on stdout, because stdout is the findings channel; the rendered
# markdown goes to stderr. Exits 1 if any gold task went unmatched:
# runs/run-20260806-123005/measurement/recall.md
# [recall] .../measurement/recall.json#/unmatched_gold: 1 authored task(s) ...
#
# ...and on stderr, for a human:
# **Recall is a smoke signal, not a metric to optimize.** With a denominator
# of 2, one task is 50%: 1/2 against 2/2 is noise, not improvement. ...
# - **Recall:** 0.50
# ## Authored tasks nothing matched
# - `bench-002`

# Write a stratified human-review packet
rubrica sample-for-review --run runs/run-20260806-123005
# runs/run-20260806-123005/measurement/review/packet.md

# Stability between two otherwise-identical runs
rubrica diff-runs --a runs/run-A --b runs/run-B
# {"comparable": true, "incomparable_reasons": [], "stages": {...}}
```

### What `smoke` actually tells you

Three verdicts, from the same report:

- **`healthy`** — the spread looks like a real test: the weak baseline
  mostly fails, the oracle mostly passes, the agent under test lands
  somewhere between.
- **`degenerate_trivial`** — the weak baseline's mean is above
  `WEAK_BASELINE_CEILING`. The tests are too easy to discriminate anything;
  this indicts the *suite*, not the agent under test.
- **`broken_labels`** — the oracle's mean is below `ORACLE_FLOOR`. **This
  indicts the gold labels or the verifier, not the agent** — an agent handed
  the reference answer that still cannot pass is proof the scoring path is
  wrong, checked before anyone starts arguing about the agent under test.
  `broken_labels` outranks `degenerate_trivial` when a report could earn
  either: a suite that cannot even pass its own oracle is not trustworthy
  evidence about triviality either.

(A fourth outcome, `inconclusive`, means there was not enough comparable data
to render a verdict at all — a required role never scored, or too few tasks
had every role score together — and is a statement about the run, not the
suite.)

### Exit codes

| Code | Meaning |
|---|---|
| `0` | clean |
| `1` | findings, one per line on stdout |
| `2` | usage error, a run directory that cannot be read (absent *or* unreadable), a schema set the CLI cannot load, a malformed `--agents`/`--gold` config, or a `SKILL.md` that cannot be parsed |

`1` means a stage produced a bad artifact and is worth one repair attempt.
`2` means the harness is misconfigured and repeating the stage cannot help —
a human-authored config that fails its schema is exit 2 for the same reason:
there is no stage to hand a repair prompt to. A `SKILL.md` is in that class too:
no stage produces one, so no repair prompt fixes it. A `SKILL.md` that *parses*
but declares something wrong is the opposite — an ordinary exit-1 finding from
`check-skills`, because it names exactly what to edit.

Two invariants follow, and both are enforced in parametrized tests:

- **A stage defect never surfaces as `2`.** The exception catch names
  `UsageError` and `OSError`, never a bare `ValueError` — a coverage document
  with `pct: "half"` is a repairable score-stage defect, not a broken harness.
- **A `1` never has an empty stdout.** An orchestrator that branches on `1` and
  finds nothing to read retries blind. An unexpected exception becomes an
  `[internal]` finding line on stdout with its traceback on stderr.

The two are parametrized over different sets, and the difference is worth knowing
before trusting either. `test_an_unbuildable_parser_is_exit_2_on_every_subcommand`
runs over `cli.subcommand_names()` — genuinely every subcommand, because the
manifest schema is read while the parser is *built*, ahead of argv.
`test_every_subcommand_turns_an_unexpected_exception_into_a_finding` runs over the
eight that route through the shared catch-all; `intake` is excluded by design
(its own block catches first, because it reads paths a person supplied rather
than artifacts a stage wrote), and `check-skills`, `record-stage` and `decide`
are covered by their own targeted tests instead.

The mirror of the first invariant is the one this project kept rediscovering:
**a filesystem problem never surfaces as `1`.** `chmod 000` on a run's
`04-instances/` used to produce an exit-1 finding telling the orchestrator to
repair an artifact that was perfectly fine, and an unreadable `01-claims/` used
to report `stage 'extract' produced no claims artifact` — because `Path.glob`
swallows `EACCES` and yields nothing, so the check announced *absence* when its
input was merely unreadable. Every run-directory listing goes through
`paths.list_dir`/`list_json`, which raise `UsageError`, and `OSError` maps to
exit 2 for the stats no listing helper covers.

Reading a schema is in the same class. `record-stage`'s `--effort` choices come
from `manifest-0.1.json`, so *building the parser* touches the disk on every
invocation — a typo'd `RUBRICA_SCHEMA_DIR` or a non-editable install missing its
package data is exit 2 for every subcommand, `intake` included.

`intake` refuses an empty `--target-name`/`--target-interface` and a
`--max-rounds`/`--max-scenarios` below 1 at exit 2 rather than minting the run:
`manifest-0.1.json` rejects all four, so the run it used to mint at exit 0
failed `validate --stage intake` on the spot — and since `intake` is code rather
than a skill, no repair prompt could ever have cleared that finding.

## The two checks worth understanding

**The reachability gate.** Every data assertion in a gold label carries a JSON
Pointer into its *own* scenario's seed. Positive assertions must resolve with
the value present; `answer_excludes` must resolve to nothing. A label can
therefore only assert things that exist in the world it was authored against,
and cannot reach another scenario's seed at all.

**The denominator check.** `denominator.capability_cells` must equal the real
number of capability × outcome-class pairs. A miscount corrupts every coverage
percentage downstream, and nothing else would notice — the numbers would simply
be confidently wrong.

## Conventions

Commits are cryptographically signed and DCO signed-off (`git commit -S -s`).
AI assistance is credited with an `Assisted-By` trailer, never `Co-Authored-By`.
