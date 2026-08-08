# test-generator

Builds a test suite for an agentic system from whatever artifacts describe it —
specifications, captured trajectories, source code — by running a pipeline of
AI skills over a schema-validated on-disk artifact contract.

**This is an experiment.** The question it exists to answer is whether
prompt-carried judgment survives a chain of artifact handoffs well enough to
produce a suite worth running. Design:
[`docs/superpowers/specs/2026-08-06-skill-based-test-generator-design.md`](docs/superpowers/specs/2026-08-06-skill-based-test-generator-design.md).

## What is here so far

The **contract spine**: the deterministic components every stage depends on.
No skills and no LLM calls yet — those arrive in later plans. Also here: a
**measurement layer** built on top of the spine — four tools that score,
compare, and sample a suite once `emit` has produced one.

| Component | Job |
|---|---|
| `paths.py` | Run-directory layout, the single source of truth for artifact paths |
| `artifacts.py` | Atomic, byte-stable canonical JSON I/O |
| `validate.py` | Layer 1: JSON Schema validation per stage |
| `invariants.py` | Evaluates world-model `machine:` invariants over a seed |
| `refs.py` | Layer 2: cross-artifact references, seed conformance, the reachability gate, and — since this build — cross-checking `07-report.json` against `06-suite/` and the manifest |
| `intake.py` | Stage 0: register + hash + classify inputs, mint the run |
| `dedupe.py` | Candidate duplicate scenario pairs (proposes; never decides) |
| `smoke.py` | `testgen smoke`: runs the emitted suite against three agent roles, scores with the package's own copied verifier, and gates on the verdict |
| `recall.py` | `testgen compare-gold`: recall and novelty against hand-authored gold tasks |
| `stability.py` | `testgen diff-runs`: per-stage Jaccard stability between two runs |
| `review.py` | `testgen sample-for-review`: a stratified human-review packet |
| `metrics.py` | The one `jaccard` set-similarity function `recall.py` and `stability.py` both use |
| `errors.py` | `UsageError`, the exception a malformed human-authored config raises so it maps to exit 2 |
| `schema/` | One JSON Schema per artifact kind, plus `agents-0.1.json` and `gold-0.1.json` for the two human-authored config files, shipped as package data |

## Setup

Requires Python 3.13+ and [`uv`](https://docs.astral.sh/uv/).

```bash
make setup     # create the venv, install runtime + dev deps
make test      # run the suite
make check     # ruff lint + format check, no changes
```

## Usage

```bash
# Stage 0: register inputs and mint a run
testgen intake \
  --input path/to/api.json \
  --input path/to/schema.json \
  --runs-dir runs \
  --target-name aap2 \
  --target-interface mcp \
  --max-rounds 2 \
  --max-scenarios 8
# --max-rounds and --max-scenarios are optional; those are their defaults.
# prints the new run directory, e.g. runs/run-20260806-123005

# After each stage: shape, then references
testgen validate --run runs/run-20260806-123005 --stage reconcile
testgen check-refs --run runs/run-20260806-123005

# Feed candidate duplicate pairs to the scoring stage
testgen dedupe-candidates --run runs/run-20260806-123005
```

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
testgen smoke --run runs/run-20260806-123005 --agents agents.json
# runs/run-20260806-123005/07-report.json

# Compare what was generated against the hand-authored gold tasks
testgen compare-gold --run runs/run-20260806-123005 --gold gold.json
# writes measurement/recall.json + measurement/recall.md and prints the
# rendered markdown; exits 1 if any gold task went unmatched:
#
# **Recall is a smoke signal, not a metric to optimize.** With a denominator
# of 2, one task is 50%: 1/2 against 2/2 is noise, not improvement. ...
# - **Recall:** 0.50
# ## Authored tasks nothing matched
# - `bench-002`

# Write a stratified human-review packet
testgen sample-for-review --run runs/run-20260806-123005
# runs/run-20260806-123005/measurement/review/packet.md

# Stability between two otherwise-identical runs
testgen diff-runs --a runs/run-A --b runs/run-B
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
| `2` | usage error, an unreadable run directory, or a malformed `--agents`/`--gold` config |

`1` means a stage produced a bad artifact and is worth one repair attempt.
`2` means the harness is misconfigured and repeating the stage cannot help —
a human-authored config that fails its schema is exit 2 for the same reason:
there is no stage to hand a repair prompt to.

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
