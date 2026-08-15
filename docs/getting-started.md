# Getting started

Rubrica builds an agent test suite for a target system out of whatever
artifacts describe it — specs, captured trajectories, source — by chaining AI
skills over a schema-validated contract on disk. This page gets a first-time
reader from a clone of this repository to a minted run they can inspect.
Every command below was run against this repository before this page was
committed; where the output is long, it is shown truncated and said so.

## Install

Prerequisites: Python 3.13+ and [`uv`](https://docs.astral.sh/uv/).

```bash
make setup
```

This runs `uv venv --python 3.13` followed by `uv pip install -e '.[dev]'`,
producing a `.venv` with the `rubrica` console script and the dev
dependencies (`pytest`, `ruff`). Everything else on this page assumes that
venv is on `PATH`; if it is not, prefix every command with `uv run` instead
(`uv run rubrica --help`, `uv run pytest -q`, and so on).

## The two ways to start a run

Every run lives in one directory (`docs/concepts/artifact-contract.md`
describes what goes in it), and there are two ways to mint one:

- **`rubrica survey --corpus …`** walks a corpus of files, digests each
  candidate, and writes `00-catalogue.json`. Nothing is admitted yet — the
  `rb-triage` skill rules on the catalogue next, admitting or declining each
  candidate against the survey's stated objective, and a human holds a gate
  over that ruling before anything downstream ever sees the corpus again.
  This is the path for "here is a pile of files, tell me what's usable."
- **`rubrica intake --input …`** mints a run directly from files you name
  yourself. There is no corpus, no catalogue, no triage record, and no gate
  over the selection — you already decided which files matter, so nothing
  reviews that decision.

**`intake --input` still works exactly as it always has.** The survey/triage
path was added alongside it, not in place of it; if you already know which
few files carry the target's behavior, hand-picking them and skipping straight
to `intake --input` is the right call, not a shortcut around anything. The
rest of this page walks the survey path first, because it is the one with
more steps to show, and then shows the hand-picked path at the end.

## Path A, walked end to end

This section works against `tests/fixtures/corpus-toy`, a small fixture
describing a fictional ticket-queue tool (TicketQ: `search_tickets`,
`get_ticket`, `escalate_ticket`) mixed in with files a real survey should
exclude or decline — a `.gitignore`d file, a duplicate README, a binary logo,
a `node_modules/` entry, a lockfile, and one file that exists only to
demonstrate an unrelated permission test.

### 1. Survey the corpus

```bash
export RUNS=runs   # or any directory you want runs written under
rubrica survey --corpus tests/fixtures/corpus-toy --runs-dir "$RUNS" \
  --target-name toy --target-interface mcp --objective breadth
```

Prints the new run directory:

```
runs/run-20260815-201344
```

```bash
export RUN=$(ls -d "$RUNS"/run-*)   # runs/run-20260815-201344, in this run
rubrica validate --run "$RUN" --stage survey
echo "exit=$?"
```

```
exit=0
```

`00-catalogue.json` now holds one entry per candidate, each with a bounded
digest rather than a copy of its bytes:

```bash
cat "$RUN"/00-catalogue.json | head -40
```

```json
{
  "candidates": [
    {
      "admissible": true,
      "bytes": 14,
      "candidate_id": "gitignore",
      "digest": {
        "body_head": "generated.txt",
        "digest_truncated": false,
        "headings": [],
        "lines": 1
      },
      "kind": "other",
      "origin": "corpus",
      "path": ".gitignore",
      "root_index": 0,
      "sha256": "2f52b96d746e0d0b6732f083fe7276ef6e90ff6b80317e29e6d4be46988e3314"
    },
    {
      "admissible": true,
      "bytes": 474,
      "candidate_id": "readme-md",
      "digest": {
        "body_head": "TicketQ is a small support-ticket queue. An agent searches tickets, reads one,\nand can escalate it to a human when the customer is upset.\n\n\n- `search_tickets(query)` finds tickets by free-text query.\n- `get_ticket(ticket_id)` reads one ticket in full.\n- `escalate_ticket(ticket_id, reason)` flags a ticket for a human.\n\n\n- A **ticket** has an id, a subject, a body, a status, and a priority.\n- A **customer** has an id, a name, and an email.",
        "digest_truncated": false,
        "headings": [
          "# TicketQ",
          "## Tools",
          "## Entities"
        ],
        "lines": 15
      },
      "kind": "design_doc",
      "origin": "corpus",
      "path": "README.md",
      "root_index": 0,
      "sha256": "385d8d6f8a1f13a95fc58f839742f184b66aa5fc85e9fa41db5adb109e8bcd38"
    },
    {
      "admissible": true,
```

(cut off at line 40 by `head`; 11 candidates in all, plus an `excluded` list
naming six paths and why each was left out: `.hg/branch` (`vcs_metadata`),
`copy-of-README.md` (`duplicate`), `generated.txt` (`gitignored`),
`logo.png` (`binary`), `node_modules/dep/index.js` (`vendored`), and
`package-lock.json` (`lockfile`).) One candidate, `capture.json`, is a
container of four captured tool calls; the survey exploded it into four
individually admissible candidates (`capture-json-0` … `capture-json-3`) and
marked the container itself non-admissible, since triage rules on the
elements, not the container.

### 2. Triage rules on every candidate

`rb-triage` is a prompt, not code — the one thing on this page that does not
run as a `rubrica` subcommand. It reads `00-catalogue.json` only, rules
`admit` or `decline` on every candidate against the declared objective, and
states what the admitted set still cannot cover. Dispatching it is described
in [`docs/guides/running-a-stage-by-hand.md`](guides/running-a-stage-by-hand.md);
this page does not repeat that runbook, because a dispatch is not a command
this repository ships.

**This is gate 0, and it is different from every other gate in the
pipeline.** Nothing downstream of `intake` ever reads the corpus again, so a
candidate `rb-triage` declines is gone as completely as if the corpus never
contained it. A human reviews the ruling before anything is minted — that
review is what the rest of this section is building toward.

### 3. Check what triage wrote

Once `rb-triage` has written `00-triage.json`, the same two check layers that
gate every other stage apply here too:

```bash
rubrica validate --run "$RUN" --stage triage
echo "exit=$?"
```

```
exit=0
```

```bash
rubrica check-refs --run "$RUN"
echo "exit=$?"
```

```
exit=0
```

A clean `validate` means the triage record is shaped correctly — every
candidate ruled on, every decline carrying a reason. A clean `check-refs`
means those rulings actually resolve against the catalogue — no disposition
naming a candidate that does not exist, no `needs_projection` decline left
without a projection that sources it.

### 4. Read the gate 0 brief

```bash
rubrica gate-brief --run "$RUN" --gate 0
echo "exit=$?"
```

```
GATE 0 -- runs/run-20260815-201344

Objective verdict
  declared objective: breadth
  supported by the surfaces found: yes
  notes: Every tool TicketQ exposes -- search_tickets, get_ticket, escalate_ticket -- has at least one admitted trace and is named in both the README and the tool schema, so a breadth objective is reachable from what was admitted.

Admits, by priority (8)
  [1] api-json: the one MCP tool schema in the corpus.
  [1] notes-md: the only source for escalate_ticket's undecided reason-length rule and the closed-ticket coverage gap.
  [1] readme-md: states the three tools and the two entities in one page.
  [2] capture-json-0: one successful search_tickets call.
  [2] capture-json-1: one successful get_ticket call.
  [2] capture-json-2: the one captured error path, for escalate_ticket.
  [2] tool-defs-py: source for the three tool entry points and the TicketNotFound error path.
  [3] capture-json-3: a second search_tickets call, distinct query.

Declines, by reason code (3)
  no_evidence_value (1):
    - gitignore, 14 bytes: one line, no statement about the target system.
  out_of_scope (1):
    - locked-md, 423 bytes: documents this fixture's own permission-testing setup, not the TicketQ target.
  superseded (1):
    - capture-json, 319 bytes: the container; each of its four elements was exploded and admitted individually above.

Open deficiencies and their projections (0)
  (none)

exit=0
```

This is the whole reading surface for gate 0: the objective verdict up top
(the thing most likely to make a reviewer overturn the selection), then every
admit and every decline grouped by reason. A human reads this, decides the
selection is sound (or asks for a re-triage first), and only then does the
run get minted.

### 5. Mint the run

```bash
rubrica intake --run "$RUN"
```

```
runs/run-20260815-201344
```

This is the same run directory — `intake --run` mints `manifest.json` and
`00-inputs/` in place from the catalogue and the triage record, rather than
starting a new one. `manifest.json` now lists the eight admitted candidates,
each with its stored path under `00-inputs/`:

```bash
cat "$RUN"/manifest.json | head -20
```

```json
{
  "created_utc": "2026-08-15T20:13:44Z",
  "inputs": [
    {
      "artifact_id": "api-json",
      "bytes": 186,
      "kind": "mcp_tool_schema",
      "sha256": "8aca0fc985c185ec8c8ce35ada693ff3b3929e227e6f38e774917177178d29ae",
      "source_path": "tests/fixtures/corpus-toy/api.json",
      "stored_as": "api-json.json"
    },
    {
      "artifact_id": "notes-md",
      "bytes": 652,
      "kind": "design_doc",
      "sha256": "67b1d4b2cd69a8e82bf86a8642111ce70bcb9c19392585bcb48c3bfc6601d1a4",
      "source_path": "tests/fixtures/corpus-toy/design/notes.md",
      "stored_as": "notes-md.md"
    },
    {
```

(cut off at line 20; the rest is the same shape, one entry per admitted
candidate, for all eight of them — plus the `limits`, `run_id`,
`schema_version`, `stages` (empty until a stage is dispatched and recorded),
and `target` that round out the file.)

From here the run is in the same state an `intake --input` run reaches
directly: a manifest, a populated `00-inputs/`, and nothing written past
that. The rest of the pipeline — `extract` through `emit` — is what
`docs/concepts/pipeline.md` describes, and what runs it is the next section.

### The other path, briefly

`intake --input` reaches the same starting state with no corpus step at all,
for a hand-picked set of files:

```bash
rubrica intake \
  --input tests/fixtures/toy/api.json \
  --input tests/fixtures/toy/notes.md \
  --input tests/fixtures/toy/trace.json \
  --runs-dir "$RUNS" \
  --target-name toy --target-interface mcp \
  --max-rounds 2 --max-scenarios 128
```

```
runs/run-20260815-201620
```

No catalogue, no triage record, no gate — `manifest.json` is written
straight from the three `--input` files named on the command line.

## What runs the prompt stages

No command in this repository dispatches a model. `survey`, `intake`,
`validate`, `check-refs`, and every other subcommand above are code — the
dispatch of `rb-triage`, and of the seven stages from `extract` through
`emit`, happens by pointing an agent at a skill file and a run directory.

`rb-orchestrate` — `src/rubrica/skills/rb-orchestrate/SKILL.md` — is the skill
that drives a whole run once a manifest exists. Point an agent at it with a
run directory and it dispatches one subagent per stage from `extract`
through `emit`, gates every artifact before the next stage sees it, holds the
round loop between propose and score, holds the three human gates after
reconcile, score, and challenge, spends at most one repair attempt per stage
failure, and records what it did — the model, the skill's hash, and every
branch it took — so the run explains itself afterward. It never runs
`survey`, never dispatches `rb-triage`, and never holds gate 0: all three are
finished, by the time it is ever handed a run, per the walkthrough above.

`rb-triage` itself is dispatched the same way, on its own, before a manifest
exists at all — see
[`docs/guides/running-a-stage-by-hand.md`](guides/running-a-stage-by-hand.md)
for the exact dispatch prompt and the settings that keep a dispatched
subagent from reading anything its skill does not list.

## What each dispatch carries

Every dispatch — whether `rb-orchestrate` sending out one stage, or a stage
being run by hand — hands a subagent exactly three things: the run directory,
the stage's name, and the path to its skill file. Nothing else. No summary of
what an earlier stage concluded, no excerpt of this page or the design spec,
no "by the way" context. If a stage needs a fact, it reads it from an
artifact its skill's contract lists, or it does not have it.

The three fan-out stages — `extract`, `instantiate`, `challenge` — get a
fourth thing: the id of their own slice (an `artifact_id` or `scenario_id`).
That id is an address, never a hint about what a sibling found, and never a
sibling's own id.

[`docs/concepts/artifact-contract.md`](concepts/artifact-contract.md) covers
the rest of this rule — including the two things an orchestrator may append
to a *re*-dispatch, and why both must be verbatim machine text rather than a
paraphrase.

## Where to go next

- [`docs/concepts/pipeline.md`](concepts/pipeline.md) — every stage, what it
  reads and writes, and the loop between propose and score.
- [`docs/reference/cli.md`](reference/cli.md) — every subcommand, its flags,
  and its own example.
- [`docs/reference/artifacts.md`](reference/artifacts.md) — every artifact
  kind, its schema, and what is worth knowing before you open one.
- [`docs/concepts/glossary.md`](concepts/glossary.md) — terms used across the
  schemas and the CLI, defined from what actually produces or consumes them.
- [`docs/guides/running-a-stage-by-hand.md`](guides/running-a-stage-by-hand.md)
  — dispatch one stage by itself and check what it wrote, whether you are
  exercising a skill you just changed or debugging one that misbehaved.
- [`docs/design/rationale.md`](design/rationale.md) — why the pipeline is
  shaped this way: the one architectural rule, the two check layers, the
  human gates.
- [`docs/design/limitations.md`](design/limitations.md) — what is known not
  to work yet, and why it was parked rather than fixed.
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — the three checks a change has to
  clear, and the commit conventions this repository holds to.
