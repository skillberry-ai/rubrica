# Running a stage by hand

This is the runbook for exercising one skill for real: dispatching a fresh
subagent with a `SKILL.md` and a run directory, then checking what it did. It
is followed by two readers — the controller, after each of Tasks 7–13's skill
implementations passes review, and a human debugging a stage that misbehaved
in a real run. Both need it to work by copy-paste, not by paraphrase, so every
command below has been run against this repository's toy fixture before this
file was committed.

These runs dispatch a model. They cost money, they are not deterministic, and
they need credentials — which is why they live behind the `live` pytest marker
(`tests/conftest.py`) and `make live`, and are never part of `make test`.

## 1. What a dispatched stage receives

The design spec (§4) is exact about this:

> A dispatched subagent receives exactly three things: the run directory path,
> its stage name, and its skill. No conversational context is threaded
> through. That is what makes the contract real.

Nothing else may be passed — no summary of what an earlier stage concluded, no
excerpt from the design spec, no "by the way, the world model says...". If the
subagent needs a fact, it must get it by reading an artifact its skill's
Contract block lists under `reads`, because the artifact contract is the only
channel this system trusts. A dispatch that pastes in "helpful" context has
silently removed the fan-out isolation the design relies on, and the resulting
artifact will still validate — so this is a rule to follow, not something
`validate` will ever catch for you.

## 2. The dispatch prompt

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

**The slice line is for the three fan-out stages, and it is an address rather
than context.** A member of a fan-out has to be told which slice is its own or
it cannot find its work at all: `rb-extract` needs `Your artifact_id:`, and
`rb-instantiate` and `rb-challenge` each need `Your scenario_id:`. Omit the
line entirely for `rb-reconcile`, `rb-score` and `rb-emit`, which are single
dispatches over everything. Give the member its own id and nothing about any
other slice — a sibling's id, or a hint about what a sibling found, is the
context leak §1 forbids. `rb-orchestrate`'s own §3 A1 states the same rule from
the dispatcher's side, and this line was missing from the template while all
four fan-out exercises run so far had to add it by hand.

## 3. Building a toy run stopped before the stage under test

`tests/toy.py`'s `build_toy_run(runs_dir, upto=...)` mints a run with real
`intake` and then writes every hand-authored artifact up to and including the
named checkpoint — never past it. Handing `rb-reconcile` a run that already
contains `01-world-model.json` would test nothing, so the checkpoint you build
to is always the stage *before* the one you are exercising:

| Stage under test | `upto=` (the checkpoint just before it) | What the dispatched skill should write |
|---|---|---|
| `rb-extract`     | `"intake"`      | `01-claims/<artifact-id>.json` for the one input artifact you pointed it at |
| `rb-reconcile`   | `"extract"`     | `01-world-model.json` |
| `rb-propose`     | `"reconcile"`   | `02-scenarios.json` (a new round) |
| `rb-score`       | `"propose"`     | `03-coverage/round-N.json` and `latest.json` |
| `rb-instantiate` | `"score"`       | `04-instances/<sid>/{seed.json,expected.json,rationale.md}` |
| `rb-challenge`   | `"instantiate"` | `05-verdicts/<sid>.json` |
| `rb-emit`        | `"challenge"` (the default — see below) | `06-suite/` (via `rubrica emit`, which the skill invokes; the skill itself writes nothing) |

`rb-orchestrate` is not in this table: it is not a stage, it dispatches them.
Its live exercise is a whole-pipeline run starting from an `upto="intake"`
run, not a single-stage check against one checkpoint — see Task 13's
`exercise.md` for its pass criteria.

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
# Run as: PYTHONPATH=. uv run python /tmp/toy-run-to.py <runs-dir> <upto-or-None>
#
# PYTHONPATH=. matters: tests/ is a package (tests/__init__.py) that pytest's
# rootdir insertion makes importable during a test run, but this script is not
# pytest, so it needs the repository root on sys.path explicitly.
import sys
from pathlib import Path

from tests.toy import build_toy_run

runs_dir = Path(sys.argv[1])
upto = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "None" else None
run = build_toy_run(runs_dir, upto=upto)
print(run.root)
```

This is a throwaway script, not a shipped one (hence `/tmp`, not `scripts/`):
the mapping table above is the reusable part, and five lines are cheaper to
retype than to maintain as a committed CLI. Run it, then dispatch the prompt
from §2 with `<absolute path>` set to the printed run directory.

## 4. The verification commands

After the subagent reports done, run these against `$RUN` (the run directory
from §3) for the stage you dispatched:

```bash
RUN=<the run directory from step 3>
STAGE=<stage>  # e.g. extract, reconcile, propose, score, instantiate, challenge, emit

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
built in §3 — that is expected, since the stage's artifact does not exist yet.
"Expect 0" applies only after the dispatched skill has actually written its
artifact.

`record-stage --skill` needs a real file to hash and hard-fails
(`UsageError: skill file does not exist`) if it is not there. Every
`src/rubrica/skills/rb-<stage>/SKILL.md` above exists starting with the task
that writes it (Tasks 7–13); until then, this command's shape can be proven
against any throwaway file:

```bash
printf '## Contract\n\n```toml\nstage = "extract"\n```\n' > /tmp/throwaway-SKILL.md
uv run rubrica record-stage --run "$RUN" --stage extract \
  --model claude-test --effort low --skill /tmp/throwaway-SKILL.md
```

This was run against the toy fixture while writing this file and exits 0,
merging a `stages.extract` entry into the manifest. Once a skill's real
`SKILL.md` exists, point `--skill` at it instead — `record-stage` hashes
whatever file it is given, so the recorded digest is only meaningful when it
names the file that was actually used.

## 5. Reading a failure

The three checks above have three different owners. Route the failure to
whichever one actually needs to change:

- **A `validate` (schema) failure** usually means the skill's **Output**
  section is unclear — the model wrote something structurally different from
  what the schema requires. Fix the skill's prose, not the schema.
- **A `check-refs` failure** usually means the skill's **Invariants** section
  is missing a constraint — the artifact is well-formed JSON that satisfies
  the schema but breaks a cross-artifact rule (a dangling reference, a seed
  that does not conform to the world model, an unreachable scenario) the
  Invariants section should have told the model to maintain.
- **Nothing written, a refusal reported** may well be **correct**. Before
  treating it as a defect, check whether the refusal condition the subagent
  cited actually holds in the toy world: if it does, the skill did its job and
  the exercise passes (record which condition fired). If the condition does
  not hold, the skill's refusal conditions are over-broad and need narrowing.

One more failure mode, not raised by `validate` or `check-refs` at all: **the
subagent read an artifact outside its `reads` list.** Nothing on disk shows
this — the resulting artifact still validates — so it can only be caught by
reading the subagent's own report against the Contract block. This is the
isolation failure §1's rule exists to prevent, and it is graded as Important,
not Minor, if it happens.

## 6. Running the live exercises as a suite

```bash
uv run pytest --markers | grep live      # confirm the marker is registered
uv run pytest -m live -q                 # today: deselected, exit 5 -- no test is
                                          # live-marked yet (Task 14 adds the first).
                                          # once one exists: skipped by default.
RUBRICA_LIVE=1 uv run pytest -m live -q  # opt in. "", "0", "false", "no" (any
                                          # case, surrounding whitespace ignored)
                                          # do NOT opt in -- everything else does.
```

`tests/unit/test_live_marker.py` proves both directions of the skip mechanically,
including that those off-spellings stay off: a live test dispatches (and bills
for) a model, so `RUBRICA_LIVE=0` must not be the thing that turns it on.
The exercises above are run by hand, one skill at a time, following §§1–5 — they
are not `-m live` pytest tests themselves, because a live exercise's pass
criteria are read by a person (or the controller), not asserted by an
`assert` statement.
