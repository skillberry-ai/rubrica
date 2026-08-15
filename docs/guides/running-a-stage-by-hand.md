# Running a stage by hand

This is the runbook for exercising one skill for real: dispatching a fresh
subagent with a `SKILL.md` and a run directory, then checking what it did. It
has two readers: someone exercising a skill they have just changed, and
someone debugging a stage that misbehaved in a real run. Both need it to work
by copy-paste, not by paraphrase, so every command below has been run against
this repository's toy fixture before this file was committed.

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
run, not a single-stage check against one checkpoint — see
`src/rubrica/skills/rb-orchestrate/exercise.md` for its pass criteria.

`rb-triage` is not in this table either, for a different reason: `paths.STAGES`
puts it *before* `intake`, and `build_toy_run` mints its run via a real
`intake()` call — there is no toy checkpoint that stops short of it. To
exercise `rb-triage` by hand, mint a run with a real catalogue instead of a toy
one:

```bash
uv run rubrica survey --corpus <path> --runs-dir /tmp/rubrica-lab/runs \
  --target-name ticketq --target-interface mcp --objective breadth
```

This writes `00-catalogue.json` and prints the run directory on stdout — exactly
the checkpoint `rb-triage` needs, since the catalogue is its only input.
`tests/fixtures/catalogue-unsupported-objective.json` and
`tests/fixtures/catalogue-all-declinable.json` are two committed catalogues that
should make it refuse (conditions 1 and 2 of its §5); copying either one over a
freshly-minted run's `00-catalogue.json` exercises those refusals without a
corpus at all.

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
STAGE=<stage>  # e.g. triage, extract, reconcile, propose, score, instantiate, challenge, emit

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

**`survey` and `triage` are the two stages whose `record-stage` runs late.**
`record-stage` merges into `manifest.json`, and on a run minted by `survey`
there *is* no manifest until `intake --run` writes it after gate 0 — so at the
moment you have just dispatched `rb-triage`, the command above raises
`ArtifactError` on the absent manifest at exit 2. Run `validate` and
`check-refs` for those two stages when the brief above says to, then come back
and record them **retroactively, after gate 0**, once the manifest exists:

```bash
# after `uv run rubrica intake --run "$RUN"` has minted manifest.json
uv run rubrica record-stage --run "$RUN" --stage triage \
  --model <the model you dispatched> --effort <the effort you used> \
  --skill src/rubrica/skills/rb-triage/SKILL.md
```

The alternative — having the triage record carry its own provenance — was
considered and rejected: a model-invented skill digest is precisely what
`record-stage` exists to prevent, since the whole point of the hook is that the
recorded hash is of the file that was actually used. Recording retroactively
keeps the digest checkable, at the cost of the ordering. Write down which model
and effort you dispatched at the time; nothing on disk remembers them for you
until you run the command.

`record-stage --skill` needs a real file to hash and hard-fails
(`UsageError: skill file does not exist`) if it is not there. Every
`src/rubrica/skills/rb-<stage>/SKILL.md` above exists in this repository, so
each path resolves as written. `record-stage` hashes whatever file it is
given, so the recorded digest is only meaningful when it names the file that
was actually used.

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
The exercises above are run by hand, one skill at a time, following §§1–5 — they
are not `-m live` pytest tests themselves, because a live exercise's pass
criteria are read by a person, not asserted by an
`assert` statement.

## 7. Dispatching into an isolated instance

§§2–4 are the manual runbook and stay the reference. `scripts/dispatch-stage.sh`
automates them, and adds the thing a hand dispatch cannot: it runs the stage in a
Claude Code instance that shares nothing with the developer's own setup.

```bash
# the checkpoint is still the stage *before* the one under test -- §3's table
RUN=$(PYTHONPATH=. uv run python /tmp/toy-run-to.py /tmp/rubrica-lab/runs intake)
./scripts/dispatch-stage.sh extract "$RUN" api-json     # fan-out: own slice id
./scripts/audit-reads.sh /tmp/rubrica-lab/transcripts/extract-api-json.jsonl

# a barrier stage takes no slice id, and needs a run built one checkpoint later
RUN=$(PYTHONPATH=. uv run python /tmp/toy-run-to.py /tmp/rubrica-lab/runs extract)
./scripts/dispatch-stage.sh reconcile "$RUN"

# triage is also a barrier -- no slice id -- and precedes intake, so its run
# comes from a real `rubrica survey` rather than the toy-run-to.py builder above
RUN=$(uv run rubrica survey --corpus <path> --runs-dir /tmp/rubrica-lab/runs \
  --target-name ticketq --target-interface mcp --objective breadth)
./scripts/dispatch-stage.sh triage "$RUN"
uv run rubrica validate --run "$RUN" --stage triage   # the gate: layer 1
uv run rubrica check-refs --run "$RUN"                # then layer 2
```

`RUBRICA_MODEL`, `RUBRICA_EFFORT` and `RUBRICA_BUDGET` set the dispatch's model,
effort and hard dollar ceiling (`sonnet`, `medium`, `2`); `RUBRICA_LAB` moves the
scratch directory that holds the generated settings and the transcripts. The
model and effort you used are what `record-stage --model/--effort` should then be
given, per §4 — and for the `triage` dispatch above, note them down: that run has
no manifest yet, so §4's `record-stage` for it cannot run until `intake --run`
has minted one after gate 0.

This one *is* shipped, unlike §3's five-line toy-run builder, and the difference
is worth stating because the reasoning there was that a mapping table is cheaper
to retype than to maintain. This script is the opposite case: it is a hundred
lines of exact flags, two of which are load-bearing in a way nobody would
reconstruct from memory, and getting one wrong fails silently rather than loudly.

**Why isolation is not tidiness.** The falsifiable claim in this project is that
prompt-carried judgment survives a chain of artifact handoffs. A dispatch that
also carries a global `CLAUDE.md`, whatever plugins and hooks the developer runs,
and *this repository's* `CLAUDE.md`, `README.md` and design spec is measuring the
skill plus a briefing — and the briefing is the answer key. `docs/` holds the
spec; `tests/fixtures/toy/` is described elsewhere in this repository as the model
answer a skill imitates. A stage that can read either is not being exercised.

Three mechanisms do it, all per-session, none of which changes anything on disk
outside the scratch directory:

| Mechanism | What it removes |
|---|---|
| `CLAUDE_CONFIG_DIR` | own history, transcripts, plugin set |
| `--safe-mode` | `CLAUDE.md`, plugins, hooks, custom agents and skills |
| `--settings` with `permissions.deny` | `docs/`, `tests/`, `CLAUDE.md`, `README.md`, sibling skills |

`--safe-mode` does not remove the *built-in* skills, so the script also passes
`--disable-slash-commands`.

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

**The venv has to be on `PATH`.** Every skill's Invariants section tells the stage
to run a bare `rubrica …`, and `README.md` says commands assume the venv is on
`PATH`. Measured without it: the stage reaches for `uv run rubrica`, which wants a
writable uv cache it does not have, and spends its entire budget thrashing on
that instead of on its artifact. The script exports it.

**What is enforced, and what only looks enforced.** The permissions layer is the
one doing the work, and by documented design it covers the file tools and the
file commands Claude Code parses out of a Bash line — *not* arbitrary
subprocesses. A `python -c "open(…)"` is outside it. The `sandbox` block is meant
to close exactly that gap at the OS level, and on the machine this was written on
it did not engage: with `bubblewrap` 0.9.0 and `socat` installed and
`bwrap --unshare-all` working standalone, a Python `open()` still read a
`denyRead` path. `failIfUnavailable` is set so a silent fall-through becomes loud;
`RUBRICA_NO_SANDBOX=1` drops the block.

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

Which is the point of `scripts/audit-reads.sh`. §5's last paragraph says an
out-of-contract read shows up nowhere on disk, and §8 of the design spec records
that both isolation violations ever observed here surfaced only because a
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

**The run directory holds three paths the stage may not read, and one of them is
an answer key.** Granting `Read(<run>/**)` is right for artifacts and wrong for
`decisions.md`, `07-report.json` and `measurement/`: no skill's Contract lists any
of them under `reads`, and all three are *about* the stages rather than merely
outside their scope — an orchestrator log, a smoke report, and the human review
surface. The script denies all three, in both settings scopes.

`decisions.md` is the one that bites. On 2026-08-13 a `propose` dispatch was given
a run whose `decisions.md` carried that stage's own pre-registered predictions,
written there minutes earlier so the reading could not be hindsight. The
transcript shows it running `ls -la` in the run directory: one `Read` from the
answer to its own exercise, and what stopped it was an unrelated premature kill.
So, two rules for scoring a stage by hand:

- **Predictions go in the design spec, never in the run.** On disk before the
  dispatch is the right instinct; inside the dispatch's read scope is the wrong
  destination.
- **The gate-1 human report is not an artifact either.** Anything you write while
  holding a gate is the orchestrator's, and a later stage reading it has been
  briefed.

`RUBRICA_PRINT_SETTINGS=1` writes both settings files and exits before
dispatching, which is how `tests/unit/test_dispatch_harness.py` checks the deny
lists without spending a model call — and how to check them by hand:

```bash
RUBRICA_PRINT_SETTINGS=1 ./scripts/dispatch-stage.sh propose "$RUN"   # prints both paths
```

None of this makes the deny list the instrument. It narrows the accident; the
audit is still what tells you what the stage read.

## 8. Re-dispatching a `re-seed` by hand

`rb-challenge` can return `re-seed` for an instance, and `rubrica emit` refuses to
compile one — it reports a finding no further stage can clear. The repair is a
single re-dispatch of `rb-instantiate` for that scenario, carrying the adversary's
objection. That objection is one of exactly **two** things an orchestrator may
append to a dispatch, and the payload is fixed by two skills that agree on it:
`rb-orchestrate` step 227 and `rb-instantiate` §1 both say the verdict's
**`alternative_answers` and its `notes`** — not the verdict string, not
`uniquely_determined`, not the flags.

```bash
RUBRICA_RESEED=1 ./scripts/dispatch-stage.sh instantiate "$RUN" scn-005
```

The block is extracted with `jq` straight from `05-verdicts/scn-005.json`, so a
paraphrase is not something the script declines to write — it is something the
script cannot express. That distinction is the point: the design spec calls a
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

**The rule that came out of it:** never deny a run path `check-refs` reads. Four
skills invoke it (`reconcile`, `instantiate`, `score`, `emit`), so in practice the
harness can only deny what `refs.py` never looks at — `decisions.md` and
`measurement/`. Whether a member *should* read `05-verdicts/` is a prompt-level
obligation, and the transcript audit is what checks it.

An empty `alternative_answers` is a *shape*, not a missing value: paired with
populated `notes` it means the defect was not ambiguity at all — an undeclared
call, or a disputed oracle — and the notes carry the whole reason. The script
passes the field through empty rather than omitting it, so the member can tell
which of the two shapes arrived.

After re-seeding, re-challenge that scenario and only then re-run `emit`. A second
`re-seed` verdict is not another repair: `rb-orchestrate` §505 says treat it as a
rejection, because `emit` refuses a `re-seed` no matter how many rounds produced
it.

To inspect what a dispatch *would* send without spending anything:

```bash
RUBRICA_PRINT_SETTINGS=1 RUBRICA_RESEED=1 \
  ./scripts/dispatch-stage.sh instantiate "$RUN" scn-005   # prints 3 paths, dispatches nothing
```

The third path is the composed prompt. It is written on every run, not only in this
mode, because the prompt is the one dispatch input a transcript does not let you
reconstruct exactly — and a re-seed run is precisely when you want to prove what
was appended.
