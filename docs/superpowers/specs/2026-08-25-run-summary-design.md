# A single-page HTML summary of one run

**Date:** 2026-08-25
**Status:** design, approved in conversation; no implementation yet

---

## 1. The problem, measured

Reading a run today means opening it file by file. A completed run holds 23
top-level paths across seven numbered stage families, and the questions an
operator actually asks — how far did this get, what came out, what looks wrong —
are each answered by a different file, several of them fan-out directories that
have to be aggregated before they say anything.

`gate-brief` already solves a neighbouring problem and is the direct precedent
for this one: it composes existing reports into the shape a human decision needs
at one of the four gates, and its docstring is explicit that it is "a composer,
not a new analysis". This design applies the same discipline to a different
question. A gate brief serves one decision at one moment; this serves the
after-the-fact read of a whole run, gates included.

### 1.1 Partial runs are the common case, not the edge case

Measured across all 11 run directories in `runs/` this session:

| | runs |
|---|---|
| reach an emitted suite (`06-suite/`) | **1 of 11** |
| have any scenarios (`02-scenarios.json`) | 2 of 11 |
| have a world model (`01-world-model.json`) | 4 of 11 |
| have nothing past intake | 6 of 11 |

So the dominant case is a run that stopped somewhere. This is the single fact
that most shapes the design: a summary that only renders complete runs would be
useless for 10 of 11 runs on disk. **Every artifact is optional, and its absence
renders as a stated absence rather than an exception** — the ruling
`claim_utilisation` and `implied_size` already make for the same reason, both
returning empty-or-`None` on a pre-seal run rather than raising.

The corollary is that the first thing on the page must be *how far the run got*.

### 1.2 What a report must not become

Two properties are load-bearing and constrain everything below:

- **It composes; it does not analyse.** Every number is read from an artifact or
  computed from read numbers by arithmetic. No dispatch, no model in the loop.
  This is what makes the page reproducible and diffable, and it is why this is
  not a skill: in this repo a `SKILL.md` is a dispatched model stage (all 17
  under `src/rubrica/skills/` are prompts), so building it that way would pay a
  dispatch to do arithmetic and make the output non-reproducible — losing the
  property that makes it trustworthy.
- **It is never a gate.** It exits 0 on any readable run. A report that can fail
  becomes a thing needing review, and an orchestrator branching on its exit code
  would be branching on a rendering.

## 2. Naming, and one collision

`report` is taken. `docs/reference/artifacts.md` §`report` defines it as the
smoke-run result at `07-report.json`, written by `smoke` and cross-checked by
`check-refs`. The subcommand is therefore **`run-summary`**, and its output is
**`run-summary.html`**.

The output is *derived*, not an artifact: it is written outside the numbered
contract, has no schema, is not read by any stage, and is gitignored alongside
`runs/`. Verified safe: `check-refs` reads named paths and calls `list_json` on
specific directories, never enumerating the run root for strays, so an added
HTML file cannot make it report a finding.

## 3. What the page contains

Ordered as the page is ordered. Every field named here was verified present in a
real run directory this session; where a run lacks it, the section renders the
absence.

### 3.1 Header — how far the run got

A **stage spine**: the pipeline's stages in `paths.STAGES` order, each marked
produced or absent from whether its path exists. This is the section that makes
the page useful on the 10-of-11 partial runs, so it leads.

Beside it, from `manifest.json`: `run_id`, `created_utc`, `limits.max_rounds`,
`limits.max_scenarios`, and the per-stage `model` / `effort` / `skill_sha256`
table from `manifest.stages` — the reproducibility record, already structured.

### 3.2 Intake and triage

- **Inputs** — `manifest.inputs[]`: `source_path`, `kind`, `bytes`, `sha256`
  (abbreviated, full in `title`), `stored_as`. Totals: count, total bytes, kinds
  tallied.
- **Objective** — `00-objective.json`: `declared_objective`, `supported`,
  `predicted_surface_count` against surfaces observed, each surface with its
  `evidence` artifact ids and `weight`.
- **Dispositions** — admit and decline counts from `00-triage.json`, declines
  grouped by reason code with counts. Admits as a priority-sorted table (reusing
  `intake.admit_sort_key`, as `brief.py` does), one row each, reason truncated
  with the full text in `title` — not the full prose paragraphs `gate-brief`
  prints.
- **Deficiencies** — from `00-triage.json` and `00-audit.json`, each beside the
  projection that would close it.

### 3.3 World model and claims

- **Counts** — from `01-world-model.json`: `capabilities`, `entities`, `actors`,
  `goals`, `gaps`, `contradictions`, plus `target` and `denominator`.
- **Claim utilisation** — via `utilisation.claim_utilisation`. The overall figure
  stated prominently and **uncited artifacts named**, that being the actionable
  half. Measured: 33.6% (1 of 23 artifacts uncited) for `run-20260823-112746`,
  65.6% (0 of 5) for `run-20260825-094033`, 32.3% (3 of 25) for
  `run-20260824-054040`.
- **Gaps** — `id`, `subject`, `blocks[]`, `unknown`, `why_it_matters`, with the
  blocked stages tallied. Not a flag: measured, **every gap in every run carries
  a non-empty `blocks[]`** (8/8, 19/19, 15/15), so a flag on it would fire
  always and discriminate nothing. It is a column and a count.
- **Contradictions** — read from the `01-contradictions/*.json` parts, each part
  being `{subject_id, contradictions[]}`, so `resolution` is nested one level
  inside the part and not a top-level field. Tallied by `resolution`, with
  `unresolved` named at zero whenever the tally renders at all. Counts and a
  pointer to the directory, never the contradictions themselves — the ruling
  `gate-brief` already makes.

### 3.4 Coverage and rounds

- **Round progression** — one row per `03-coverage/round-N.json`: round, cells
  covered of total, pct, goals, `progress.new_cells_this_round`,
  `progress.rounds_without_progress`, open holes. The terminal `verdict` called
  out.
- **Capability × outcome-class matrix** — from `capability_matrix.cells[]`, each
  cell carrying `capability_id`, `outcome_class_id`, `covered`, `scenario_ids`.
  Rendered as a table with background colour, no plotting dependency. Because
  covered cells name their scenarios, the matrix is the index *into* §3.5: a
  cell links to the scenarios covering it.
- **Holes** — `ref`, `reason`, `justification`, with `unreachable` visually
  distinguished from other reasons: an unreachable hole is a closed question and
  the others are open ones.
- **Implied suite size** against the ceiling, via `sizing.implied_size`.

### 3.5 Scenarios — one line each

One row per scenario in `02-scenarios.json`, joined across three directories:

| source | columns |
|---|---|
| `02-scenarios.json` | `id`, `round`, `title`, `goal_id`, `actor_id`, `hop_depth`, capability×outcome refs, `status` |
| `05-verdicts/<id>.json` | `verdict`, `uniquely_determined`, `derivable_without_guessing`, `minimum_tool_calls_found` |
| `06-suite/<id>/` | package present, and which of `task.toml`, `seed.json`, `golden.json`, `instruction.md`, `provenance.md`, `tests/` it holds |

Sortable, filterable by verdict / status / round. Every id links to the artifact
on disk by relative `file://` href — `04-instances/<id>/`,
`05-verdicts/<id>.json`, `06-suite/<id>/` — which is what lets the row stay one
line and keeps seed and golden JSON off the page entirely.

`discriminating_fact` and verdict `notes` are long prose; they live in `title`
attributes or an expand-on-click cell, not columns.

### 3.6 Challenge and emitted suite

Verdict tallies, which scenarios were re-seeded and why, repair attempts spent,
and the emitted inventory: package count and per-package file presence. When
`07-report.json` exists, the smoke summary joins here.

### 3.7 Flags

Computed in code, each with its threshold **named on the page** so a flag is
never a black box. Only one flag has a tunable threshold — claim utilisation,
set at 50%, which splits the three measured runs 2-to-1 and is a module constant
so moving it is a one-line change with a test. Every other flag triggers on a
count crossing zero, or on a comparison between two fields, and so has nothing
to tune. Measured against real runs, which is how two of them were demoted or
added:

| flag | trigger | measured |
|---|---|---|
| Low claim utilisation | overall pct < 50% | 32.3%–65.6% across 3 runs |
| Uncited artifacts | an input contributing no cited claim | 1/23, 0/5, 3/25 |
| Coverage halted | `verdict != complete` | `halted_no_progress`, `continue` |
| Unresolved contradictions | `resolution == "unresolved"` count > 0 | **6 in `run-20260825-094033`**; 0 in `run-20260823-112746` (`both_possible=1 preferred_a=1 preferred_b=1`) |
| Repair attempts spent | a scenario re-seeded | scn-009, once |
| Difficulty overstated | `minimum_tool_calls_found < hop_depth` | 0 of 14 |
| Orphaned temp file | a `*.tmp.*` under the run root | **`02-scenarios.json.tmp.43146.cb890a5abaf7`** in `run-20260825-094033` |
| Stage record incomplete | a produced stage with no `manifest.stages` entry | — |

Two of these earn their place on evidence rather than anticipation. The
unresolved-contradiction flag fires on the newest run on disk, which is exactly
the signal `brief.py` calls "the cheapest signal that there is a part worth
opening". The orphaned-temp flag was found by inspection during this design —
one is sitting in `run-20260825-094033` now, and `decisions.md` records a prior
one removed by hand.

### 3.8 `decisions.md`, verbatim

Rendered as-is at the bottom. It is the human record of the run's judgment calls,
already prose written for this reader; there is nothing to compose.

## 4. Mechanism

**A `rubrica run-summary` subcommand, pure standard library, in a new module
`src/rubrica/summary.py`.**

The repo has already voted for this shape twice. `gate-brief` is this tool at
plain-text scope and lives as a subcommand in `brief.py`. And
`scripts/render-pipeline-diagram.py` establishes that this repo generates real
HTML with `html.escape` and hand-built markup — there is no templating
dependency, and adding Jinja as the project's first new runtime dependency for
the sake of a *report* is a bad trade against three declared dependencies chosen
as carefully as `pyproject.toml`'s comments show.

Going through the CLI also inherits, for free: `cli.py`'s exit-code contract and
shared catch, `_run_dir`'s argument handling, `RunPaths` naming every path the
page reads, and `check-skills` keeping the contract honest.

Rejected: a script under `scripts/`, whose two non-doc members exist to drive a
real dispatch (`dispatch-stage.sh`, `audit-reads.sh`, both needing `jq`, one
needing `claude`) — a run-reading renderer is neither, and would be the only
thing there that reads a run directory.

### 4.1 Interface

```
rubrica run-summary --run <dir> [-o|--output PATH]
```

Default output `<run>/run-summary.html`. Exit 0 on any readable run; an
unreadable run directory raises `OSError` and `cli.py` maps it to 2, as for every
other subcommand.

Output is one self-contained file: inline CSS, inline JS for sort and filter, no
external assets, no network. Relative hrefs to sibling artifacts, so the page and
the run travel together and the page still opens standalone.

### 4.2 Structure

`summary.py` holds one section-builder per §3 section, each returning a small
dataclass of already-computed values, plus a `flags()` function holding the
threshold table of §3.7 and a renderer turning those into HTML. It reuses
`utilisation.claim_utilisation`, `sizing.implied_size`, and
`intake.admit_sort_key` rather than recomputing any of them.

If the render half outgrows comfort, it splits into `summary.py` (read and
compute) and `summary_html.py` (markup); the dataclass boundary is where that cut
already falls, so it is a move, not a redesign.

### 4.3 Tests

`tests/unit/test_summary.py`, test-first. The cases that matter:

- every section against a complete run (the `06-suite` shape);
- every section against a run stopped at `02-scenarios.json`, and one stopped
  before the world model — renders stated absences, exits 0, raises nothing.
  This is 10 of 11 real runs, so it is the primary case, not a degenerate one;
- each flag firing and not firing, against fixtures built for each;
- **HTML escaping of prose fields.** `discriminating_fact` and verdict `notes`
  contain quotes and angle brackets in real runs and are rendered into `title`
  attributes, so escaping is a correctness test rather than a nicety.

## 5. Out of scope, deliberately

- **No charts.** The matrix is a coloured table. No plotting dependency.
- **No cross-run deltas.** `diff-runs` and `compare-gold` own that comparison.
- **No `--check` mode.** `render-pipeline-diagram.py` has one because its output
  is committed and must not drift; this output is derived per run and never
  committed, so there is nothing to verify it against.
- **No model-written narrative.** §1.2.
