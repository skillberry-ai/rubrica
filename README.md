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
No skills and no LLM calls yet — those arrive in later plans.

| Component | Job |
|---|---|
| `paths.py` | Run-directory layout, the single source of truth for artifact paths |
| `artifacts.py` | Atomic, byte-stable canonical JSON I/O |
| `validate.py` | Layer 1: JSON Schema validation per stage |
| `invariants.py` | Evaluates world-model `machine:` invariants over a seed |
| `refs.py` | Layer 2: cross-artifact references, seed conformance, the reachability gate |
| `intake.py` | Stage 0: register + hash + classify inputs, mint the run |
| `dedupe.py` | Candidate duplicate scenario pairs (proposes; never decides) |
| `schema/` | One JSON Schema per artifact kind, shipped as package data |

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

### Exit codes

| Code | Meaning |
|---|---|
| `0` | clean |
| `1` | findings, one per line on stdout |
| `2` | usage error, or an unreadable run directory |

`1` means a stage produced a bad artifact and is worth one repair attempt.
`2` means the harness is misconfigured and repeating the stage cannot help.

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
