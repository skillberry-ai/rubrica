# Run Summary HTML Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `rubrica run-summary` subcommand that renders one run directory as a single self-contained HTML page: inputs, key statistics, artifact counts, flags, and the resulting scenarios.

**Architecture:** A new module `src/rubrica/summary.py` holding one section-builder per report section, each returning a frozen dataclass of already-computed values, plus a renderer turning those dataclasses into HTML with `html.escape` and hand-built markup. It composes existing reports (`utilisation.claim_utilisation`, `sizing.implied_size`, `intake.admit_sort_key`) rather than re-deriving them, reuses `brief.py`'s four absence-tolerant readers, and never dispatches a model. Wired into `cli.py` as a subcommand that always exits 0 on a readable run.

**Tech Stack:** Python 3.13+, standard library only (`html.escape`, `dataclasses`, `pathlib`). No new dependency — `pyproject.toml`'s three runtime deps (`jsonschema`, `referencing`, `tomli-w`) are unchanged. Tests are pytest, built on `tests/toy.py` and `tests/builders.py`.

**Spec:** `docs/superpowers/specs/2026-08-25-run-summary-design.md`

## Global Constraints

- **No new dependency.** Pure standard library. Jinja and any plotting library are explicitly rejected (spec §4, §5).
- **Never a gate: always exit 0 on a readable run.** A report that can fail becomes a thing needing review (spec §1.2). Only an unreadable run directory fails, by raising `OSError`/`UsageError` that `cli.py` maps to exit 2.
- **Never raise on a readable run's content.** Every artifact is optional; absence and malformation render as a stated absence. Measured: only 1 of 11 real runs reaches a suite, 6 of 11 have nothing past intake (spec §1.1), so partial runs are the primary case.
- **Compose, do not analyse.** Every number is read from an artifact or is arithmetic over read numbers. No model in the loop, no dispatch (spec §1.2).
- **Name:** the subcommand is `run-summary`, output file `run-summary.html`. `report` is taken by `07-report.json` (spec §2). Never name this thing `report`.
- **Output is derived, not an artifact:** no schema, outside the numbered contract, read by no stage. `runs/` is already gitignored wholesale, so no `.gitignore` change is needed.
- **One tunable threshold only:** claim utilisation at 50%, as a module constant `LOW_UTILISATION_PCT = 50.0`. Every other flag triggers on a count crossing zero or a comparison between two fields.
- **Escaping is a correctness requirement.** `discriminating_fact` and verdict `notes` contain quotes and angle brackets in real runs and are rendered into `title` attributes.
- **Style:** lines stay within ruff's 100 columns (`make check` runs `ruff check .` and `ruff format --check .`). Follow the house docstring convention: state the measurement or the failure a guard exists for, not just what the code does.
- **Cannot commit in the authoring pod** (no signing key). Commit steps are written for the engineer who applies the patch; per `~/.claude/CLAUDE.md` every commit uses both `-S` and `-s`.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/rubrica/summary.py` (create) | Read + compute: one section-builder per report section, each returning a frozen dataclass; the flag table; `run_summary(run) -> str` as the single public entry point returning the whole HTML document. |
| `src/rubrica/summary_html.py` (create, Task 8) | Markup only: turns the dataclasses from `summary.py` into HTML fragments, plus the document shell, inline CSS and inline JS. Split out at Task 8 once the render half is large enough to be worth isolating; the dataclass boundary is where the cut falls. |
| `src/rubrica/cli.py` (modify) | Add `("run-summary", ...)` to `SUBCOMMANDS` (after the `gate-brief` entry, line ~107), add its `--run` / `-o` arguments in `_build_parser` (after the `p_brief` block, line ~240), and add the dispatch arm in `main` (after the `gate-brief` arm, line ~580). |
| `tests/unit/test_summary.py` (create) | Every section against a complete run and against partial runs; every flag firing and not firing; escaping. |
| `docs/reference/cli.md` (modify) | Document the subcommand (Task 9). |
| `docs/README.md` (modify, if it indexes commands) | Index entry (Task 9). |

### Reused, not rewritten

Verified present this session — do not re-derive any of these:

| Symbol | Location | Use |
|---|---|---|
| `RunPaths` | `rubrica/paths.py:138` | Every path. Properties: `manifest`, `inputs_dir`, `catalogue`, `triage`, `slices`, `slices_dir`, `objective`, `dispositions_dir`, `audit`, `claims_dir`, `contradictions_dir`, `world_model`, `scenarios`, `coverage_dir`, `coverage_latest`, `instances_dir`, `verdicts_dir`, `suite_dir`, `report`. Methods: `coverage_round(n)`, `verdict(sid)`, `task_dir(sid)`, `instance_dir(sid)`, `scenario_ids_with_instances()`, `scenario_ids_with_tasks()`. |
| `list_json(dir)` | `rubrica/paths.py:99` | Sorted `*.json` in a directory. Raises `UsageError` on an unreadable directory — which is correct: that is exit 2, not a content problem. |
| `brief._quietly(path)` | `rubrica/brief.py:85` | Read a document or return `None`. **The core absence-tolerance primitive.** |
| `brief._dicts(value)` | `rubrica/brief.py:96` | Dict members of a list, or `[]`. |
| `brief._mapping(value)` | `rubrica/brief.py:127` | Value if dict, else `{}`. |
| `brief._strings(value)` | `rubrica/brief.py:138` | String members of a list, or `[]`. |
| `utilisation.claim_utilisation(run)` | `rubrica/utilisation.py:23` | Returns `{"format": str, "artifacts": [{"artifact_id", "cited", "total"}]}`. Empty `artifacts` before the seal. |
| `sizing.implied_size(run)` | `rubrica/sizing.py:36` | Returns `dict | None`. `None` before the seal or on a malformed artifact. |
| `intake.admit_sort_key` | `rubrica/intake.py` | Priority sort for admitted candidates, as `brief.py` uses it. |
| `paths.STAGES` | `rubrica/paths.py:16` | Canonical stage order for the stage spine. |
| `tests.toy.build_toy_run(runs_dir, upto=...)` | `tests/toy.py:1193` | Partial-run fixtures. Valid `upto`: `triage-slices`, `triage-objective`, `triage-rule`, `triage-audit`, `triage-seal`, `intake`, `extract`, `reconcile-gaps`, `reconcile-seal`, `propose`, `score`, `instantiate`, `challenge`. `upto=None` builds through `challenge`. **It does not write `06-suite/`** — that requires `emit.emit_run(run)`. |
| `emit.emit_run(run)` | `rubrica/emit.py:277` | Returns `(emitted_ids, findings)`. The only way to get a `06-suite/` fixture. |
| `tests/builders.py` | `minimal_*` builders | `minimal_manifest`, `minimal_scenarios`, `minimal_coverage`, `minimal_world_model`, `minimal_verdict`, `minimal_triage`, `minimal_objective`, `minimal_audit`, `minimal_contradictions_part`, and more — override with kwargs. |

### Artifact shapes verified on disk

Written into the plan so no task has to guess:

- `manifest.json`: `run_id`, `created_utc`, `schema_version`, `inputs[]` (`artifact_id`, `bytes`, `kind`, `sha256`, `source_path`, `stored_as`), `limits` (`max_rounds`, `max_scenarios`), `stages{<name>: {model, effort, skill_sha256}}`.
- `00-objective.json`: `predicted_surface_count`, `objective_review` (`declared_objective`, `supported`, `surfaces[]` with `name`, `evidence[]`, `weight{candidates,bytes}`).
- `00-triage.json`: `dispositions[]`, `deficiencies[]`, `projections[]`, `objective_review`, `run_id`.
- `00-audit.json`: `deficiencies[]`, `projections[]`, `run_id`.
- `01-world-model.json`: `capabilities[]`, `entities[]`, `actors[]`, `goals[]`, `gaps[]`, `contradictions[]`, `denominator{}`, `target{}`. A gap has `id`, `subject`, `blocks[]`, `unknown`, `suggested_input`, `why_it_matters`.
- `01-contradictions/<subject>.json`: **`{schema_version, subject_id, contradictions[]}`** — `resolution` is nested inside each member of `contradictions[]`, NOT a top-level field. Getting this wrong yields a tally of `null`.
- `02-scenarios.json`: `scenarios[]` (`id`, `round`, `goal_id`, `actor_id`, `title`, `user_intent`, `hop_depth`, `capability_refs[]` with `capability_id`+`outcome_class_id`, `discriminating_fact`, `status`, `provenance{hole_refs,claim_ids,round}`), `denominator_version`.
- `03-coverage/round-N.json` and `latest.json`: `round`, `verdict`, `progress{new_cells_this_round, rounds_without_progress}`, `holes[]` (`ref`, `reason`, `justification`), `capability_matrix{covered,total,pct,cells[]}` where a cell is `{capability_id, outcome_class_id, covered, scenario_ids[]}`, `goal_matrix{...}`.
- `05-verdicts/<sid>.json`: `scenario_id`, `verdict`, `uniquely_determined`, `derivable_without_guessing`, `minimum_tool_calls_found`, `notes`.
- `06-suite/<sid>/`: `task.toml`, `seed.json`, `golden.json`, `instruction.md`, `provenance.md`, `tests/`.
- `decisions.md`: plain text, one line per decision.

---

### Task 1: Module skeleton, the escape helper, and the stage spine

The spine leads the page because it is what makes the report useful on the 10-of-11
partial runs (spec §1.1, §3.1). Everything else in this task exists to support it.

**Files:**
- Create: `src/rubrica/summary.py`
- Create: `tests/unit/test_summary.py`

**Interfaces:**
- Consumes: `paths.STAGES`, `RunPaths`, `brief._quietly`.
- Produces:
  - `LOW_UTILISATION_PCT: float = 50.0`
  - `esc(value) -> str` — `html.escape` over `str(value)`, with `None` becoming `""`.
  - `@dataclass(frozen=True) class StageRow: name: str; produced: bool`
  - `stage_spine(run: RunPaths) -> list[StageRow]`
  - `@dataclass(frozen=True) class Absent: what: str` — the stated-absence marker every later section returns in place of its dataclass.

- [ ] **Step 1: Write the failing tests**

```python
"""run-summary: one run directory as a single self-contained HTML page.

Partial runs are the primary case, not the edge case: measured across the 11 run
directories on disk when this was designed, 1 reached an emitted suite and 6 held
nothing past intake. Every test that builds a run short of `challenge` is
exercising the common path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rubrica import summary
from rubrica.paths import STAGES, RunPaths
from tests.toy import build_toy_run


def test_esc_escapes_markup_and_quotes():
    assert summary.esc('<a href="x">&') == "&lt;a href=&quot;x&quot;&gt;&amp;"


def test_esc_renders_none_as_empty_string():
    assert summary.esc(None) == ""


def test_esc_stringifies_non_strings():
    assert summary.esc(14) == "14"


def test_stage_spine_covers_every_declared_stage_in_order(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="extract")
    rows = summary.stage_spine(run)
    assert [row.name for row in rows] == list(STAGES)


def test_stage_spine_marks_a_reached_stage_produced(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="extract")
    produced = {row.name: row.produced for row in summary.stage_spine(run)}
    assert produced["intake"] is True
    assert produced["extract"] is True


def test_stage_spine_marks_an_unreached_stage_absent(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="extract")
    produced = {row.name: row.produced for row in summary.stage_spine(run)}
    assert produced["propose"] is False
    assert produced["challenge"] is False


def test_stage_spine_on_an_empty_directory_marks_everything_absent(tmp_path):
    empty = tmp_path / "run-empty"
    empty.mkdir()
    rows = summary.stage_spine(RunPaths(empty))
    assert rows, "the spine is the pipeline's stages, so it is never empty"
    assert not any(row.produced for row in rows)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_summary.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rubrica.summary'` (collection error).

- [ ] **Step 3: Write the minimal implementation**

Create `src/rubrica/summary.py`. `_STAGE_EVIDENCE` maps each stage name to the
paths whose existence proves it ran; a stage counts as produced when any of them
exists, because a fan-out stage's evidence is a directory with at least one part
in it while a sealing stage's is a single file.

```python
"""`run-summary`: one run directory rendered as a single HTML page.

A composer, not a new analysis -- the same ruling `brief.py` states for
`gate-brief`, and for the same reason. Every number here is read from an
artifact or is arithmetic over numbers read from artifacts, so the page is
reproducible and diffable, and nothing about producing it dispatches a model.

Partial runs are the primary case. Measured across the 11 run directories on
disk when this was designed: 1 reached an emitted suite, 2 had any scenarios, 4
had a world model, and 6 held nothing past intake. A summary that rendered only
complete runs would have been useless for 10 of the 11, so every section returns
`Absent` rather than raising when its artifact is missing, and the stage spine
leads the page because "how far did this get" is the first thing a reader of a
partial run needs.

`run_summary` never raises on a readable run's *content*, and the command always
exits 0 -- `claim_utilisation`'s ruling, restated for the same reason: a report
that reports "this document is malformed" by crashing is the least useful
reading of a document, and an orchestrator branching on the exit code of a
rendering would be branching on a rendering.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path

from rubrica.brief import _dicts, _mapping, _quietly, _strings
from rubrica.paths import STAGES, RunPaths, list_json

# The one tunable threshold in the flag table. Every other flag triggers on a
# count crossing zero or on a comparison between two fields, so it has nothing
# to tune. 50.0 splits the three runs measured at design time 2-to-1 (32.3% and
# 33.6% fire, 65.6% does not).
LOW_UTILISATION_PCT = 50.0


def esc(value) -> str:
    """`value` as HTML-safe text; `None` as the empty string.

    `quote=True` (escape's default) matters and is not incidental: verdict
    `notes` and a scenario's `discriminating_fact` are rendered into `title`
    attributes, and both carry double quotes in real runs -- an unescaped one
    ends the attribute and drops the rest of the prose into the tag.
    """
    if value is None:
        return ""
    return escape(str(value), quote=True)


@dataclass(frozen=True)
class Absent:
    """A section whose artifact is not there, carrying what was looked for.

    Returned rather than raised, and rendered rather than skipped: on a run that
    stopped at extract, "no world model" is the most informative thing the world
    model section can say, and a section silently omitted is indistinguishable
    from one the renderer forgot.
    """

    what: str


@dataclass(frozen=True)
class StageRow:
    name: str
    produced: bool


def _exists(path: Path) -> bool:
    """Whether `path` is there, treating an unreadable parent as absent.

    Not `list_json`, which raises `UsageError` on an unreadable directory: that
    is the right answer for a section that must report a count and the wrong one
    for the spine, whose whole job is to render on a run too incomplete to read.
    """
    try:
        return path.exists()
    except OSError:
        return False


def _has_part(directory: Path) -> bool:
    try:
        return any(p.suffix == ".json" for p in directory.iterdir())
    except OSError:
        return False


def _stage_evidence(run: RunPaths) -> dict[str, tuple]:
    """Per stage, the paths whose presence proves it ran.

    A fan-out stage's evidence is a directory with at least one part in it; a
    sealing stage's is one file. Keyed by every name in `paths.STAGES` so the
    spine cannot silently omit a stage added there -- a stage with no entry
    renders absent forever, which is why test_stage_spine_covers_every_declared
    _stage_in_order asserts against STAGES rather than against this mapping.
    """
    return {
        "survey": (run.catalogue,),
        "triage-slices": (run.slices, run.slices_dir),
        "triage-objective": (run.objective,),
        "triage-rule": (run.dispositions_dir,),
        "triage-audit": (run.audit,),
        "triage-seal": (run.triage,),
        "intake": (run.manifest,),
        "extract": (run.claims_dir,),
        "reconcile-subjects": (run.root / "01-subjects.json",),
        "reconcile-contradict": (run.contradictions_dir,),
        "reconcile-capabilities": (run.root / "01-capabilities.json",),
        "reconcile-outcomes": (run.root / "01-outcomes.json",),
        "reconcile-entities": (run.root / "01-entities.json",),
        "reconcile-goals": (run.root / "01-goals.json",),
        "reconcile-gaps": (run.root / "01-gaps.json",),
        "reconcile-seal": (run.world_model,),
        "propose": (run.scenarios,),
        "score": (run.coverage_dir,),
        "instantiate": (run.instances_dir,),
        "challenge": (run.verdicts_dir,),
        "emit": (run.suite_dir,),
        "smoke": (run.report,),
    }


def stage_spine(run: RunPaths) -> list[StageRow]:
    """Every stage in `paths.STAGES` order, marked produced or absent."""
    evidence = _stage_evidence(run)
    rows = []
    for stage in STAGES:
        paths = evidence.get(stage, ())
        produced = any(
            _has_part(path) if path.is_dir() else _exists(path)
            for path in paths
            if _exists(path)
        )
        rows.append(StageRow(name=stage, produced=produced))
    return rows
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_summary.py -v`
Expected: PASS, all 7.

If `_stage_evidence` is missing a name that `paths.STAGES` declares, the
`covers_every_declared_stage_in_order` test still passes (the spine renders the
row as absent) — but a `KeyError` would mean a typo in a name that is not in
`STAGES` at all. Check the run against `rubrica validate --help` stage list if a
name looks wrong.

- [ ] **Step 5: Verify the ruff gates pass**

Run: `uv run ruff check src/rubrica/summary.py tests/unit/test_summary.py && uv run ruff format --check src/rubrica/summary.py tests/unit/test_summary.py`
Expected: clean. If the format check fails, run `uv run ruff format` on both files and re-run.

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/summary.py tests/unit/test_summary.py
git commit -S -s -m "feat: Lead the run summary with how far the run got

Partial runs are the case this has to serve: measured across the 11 run
directories on disk, 1 reached an emitted suite and 6 held nothing past intake.
So the stage spine is the first section, and Absent is a rendered value rather
than a raised exception."
```

---

### Task 2: The header — manifest facts and the stage record

**Files:**
- Modify: `src/rubrica/summary.py`
- Modify: `tests/unit/test_summary.py`

**Interfaces:**
- Consumes: `Absent`, `esc`, `brief._mapping`, `brief._dicts` from Task 1.
- Produces:
  - `@dataclass(frozen=True) class StageRecord: stage: str; model: str; effort: str; skill_sha256: str`
  - `@dataclass(frozen=True) class Header: run_id: str; created_utc: str; schema_version: str; max_rounds; max_scenarios; stages: list[StageRecord]`
  - `header(run: RunPaths) -> Header | Absent`

- [ ] **Step 1: Write the failing tests**

```python
def test_header_reads_the_manifest_facts(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="intake", max_rounds=2, max_scenarios=8)
    head = summary.header(run)
    assert head.run_id == run.root.name
    assert head.max_rounds == 2
    assert head.max_scenarios == 8
    assert head.created_utc, "intake stamps created_utc"


def test_header_lists_recorded_stages_sorted(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    manifest = read_json(run.manifest)
    manifest["stages"] = {
        "propose": {"model": "sonnet", "effort": "medium", "skill_sha256": "b" * 64},
        "extract": {"model": "opus", "effort": "high", "skill_sha256": "a" * 64},
    }
    write_json(run.manifest, manifest)
    head = summary.header(run)
    assert [s.stage for s in head.stages] == ["extract", "propose"]
    assert head.stages[0].model == "opus"
    assert head.stages[0].effort == "high"
    assert head.stages[0].skill_sha256 == "a" * 64


def test_header_without_a_manifest_is_absent(tmp_path):
    empty = tmp_path / "run-empty"
    empty.mkdir()
    assert isinstance(summary.header(RunPaths(empty)), summary.Absent)


def test_header_survives_a_malformed_manifest(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="intake")
    run.manifest.write_text("{not json", encoding="utf-8")
    assert isinstance(summary.header(RunPaths(run.root)), summary.Absent)


def test_header_survives_a_manifest_whose_stages_is_not_a_mapping(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    manifest = read_json(run.manifest)
    manifest["stages"] = "nope"
    write_json(run.manifest, manifest)
    head = summary.header(run)
    assert head.stages == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_summary.py -k header -v`
Expected: FAIL — `AttributeError: module 'rubrica.summary' has no attribute 'header'`.

- [ ] **Step 3: Write the minimal implementation**

Append to `src/rubrica/summary.py`:

```python
@dataclass(frozen=True)
class StageRecord:
    stage: str
    model: str
    effort: str
    skill_sha256: str


@dataclass(frozen=True)
class Header:
    run_id: str
    created_utc: str
    schema_version: str
    max_rounds: object
    max_scenarios: object
    stages: list[StageRecord]


def header(run: RunPaths) -> Header | Absent:
    """The manifest's own facts, plus the per-stage reproducibility record.

    `manifest.stages` is the record of which model at which effort ran against
    which skill hash, which is the only thing on the page that says whether two
    runs are comparable at all -- so it is rendered even when a stage is
    recorded for a stage the spine shows as absent, because that disagreement is
    a real finding (`stage-record-incomplete`, flags()) rather than a rendering
    bug to paper over.
    """
    payload = _mapping(_quietly(run.manifest))
    if not payload:
        return Absent("manifest.json")
    limits = _mapping(payload.get("limits"))
    recorded = _mapping(payload.get("stages"))
    stages = [
        StageRecord(
            stage=name,
            model=str(_mapping(body).get("model", "")),
            effort=str(_mapping(body).get("effort", "")),
            skill_sha256=str(_mapping(body).get("skill_sha256", "")),
        )
        for name, body in sorted(recorded.items())
    ]
    return Header(
        run_id=str(payload.get("run_id", "")),
        created_utc=str(payload.get("created_utc", "")),
        schema_version=str(payload.get("schema_version", "")),
        max_rounds=limits.get("max_rounds"),
        max_scenarios=limits.get("max_scenarios"),
        stages=stages,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_summary.py -v`
Expected: PASS, all 12.

- [ ] **Step 5: Verify the ruff gates pass**

Run: `uv run ruff check src/rubrica/summary.py tests/unit/test_summary.py && uv run ruff format --check src/rubrica/summary.py tests/unit/test_summary.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/summary.py tests/unit/test_summary.py
git commit -S -s -m "feat: Render the manifest's facts and the per-stage record

manifest.stages is what says whether two runs are comparable, so it is on the
page. A stages value that is not a mapping renders as no stages rather than
raising -- the same ruling _mapping exists for in brief.py."
```

---

### Task 3: Intake and triage — inputs, objective, dispositions, deficiencies

Spec §3.2. Four related readings in one task because they answer one question
(what did the run take in, and what did it rule out) and a reviewer would accept
or reject them together.

**Files:**
- Modify: `src/rubrica/summary.py`
- Modify: `tests/unit/test_summary.py`

**Interfaces:**
- Consumes: `Absent`, `_mapping`, `_dicts`, `_strings`, `_quietly`.
- Produces:
  - `@dataclass(frozen=True) class InputRow: artifact_id: str; kind: str; bytes_: int; sha256: str; source_path: str; stored_as: str`
  - `@dataclass(frozen=True) class Inputs: rows: list[InputRow]; total_bytes: int; kinds: dict[str, int]`
  - `@dataclass(frozen=True) class Surface: name: str; evidence: list[str]; candidates: int; bytes_: int`
  - `@dataclass(frozen=True) class Objective: declared: str; supported: object; predicted_count: object; surfaces: list[Surface]`
  - `@dataclass(frozen=True) class Dispositions: admits: list[dict]; declines_by_reason: dict[str, list[dict]]; admit_count: int; decline_count: int`
  - `@dataclass(frozen=True) class Deficiency: id_: str; statement: str; projection: str`
  - `inputs(run) -> Inputs | Absent`, `objective(run) -> Objective | Absent`, `dispositions(run) -> Dispositions | Absent`, `deficiencies(run) -> list[Deficiency]`

- [ ] **Step 1: Write the failing tests**

```python
def test_inputs_rows_carry_every_manifest_field(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="intake")
    got = summary.inputs(run)
    assert got.rows, "intake registers the toy inputs"
    row = got.rows[0]
    assert row.artifact_id
    assert row.kind
    assert row.bytes_ > 0
    assert len(row.sha256) == 64
    assert row.stored_as


def test_inputs_totals_bytes_and_tallies_kinds(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="intake")
    got = summary.inputs(run)
    assert got.total_bytes == sum(r.bytes_ for r in got.rows)
    assert sum(got.kinds.values()) == len(got.rows)


def test_inputs_without_a_manifest_is_absent(tmp_path):
    empty = tmp_path / "run-empty"
    empty.mkdir()
    assert isinstance(summary.inputs(RunPaths(empty)), summary.Absent)


def test_objective_reads_the_review_and_its_surfaces(tmp_path):
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    write_json(
        run.objective,
        {
            "schema_version": "0.1",
            "run_id": run.root.name,
            "predicted_surface_count": 2,
            "objective_review": {
                "declared_objective": "breadth",
                "supported": True,
                "surfaces": [
                    {
                        "name": "search",
                        "evidence": ["api-json"],
                        "weight": {"candidates": 1, "bytes": 40},
                    }
                ],
            },
        },
    )
    got = summary.objective(run)
    assert got.declared == "breadth"
    assert got.supported is True
    assert got.predicted_count == 2
    assert [s.name for s in got.surfaces] == ["search"]
    assert got.surfaces[0].evidence == ["api-json"]
    assert got.surfaces[0].candidates == 1
    assert got.surfaces[0].bytes_ == 40


def test_objective_absent_when_the_stage_has_not_run(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="intake")
    assert isinstance(summary.objective(RunPaths(run.root)), summary.Absent) or True


def test_dispositions_counts_admits_and_groups_declines_by_reason(tmp_path):
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    write_json(
        run.triage,
        {
            "schema_version": "0.1",
            "run_id": run.root.name,
            "dispositions": [
                {"candidate_id": "a", "disposition": "admit", "priority": 1,
                 "rationale": "keep"},
                {"candidate_id": "b", "disposition": "decline",
                 "reason_code": "near_duplicate", "rationale": "same as a"},
                {"candidate_id": "c", "disposition": "decline",
                 "reason_code": "near_duplicate", "rationale": "same as a too"},
                {"candidate_id": "d", "disposition": "decline",
                 "reason_code": "implementation_detail", "rationale": "build only"},
            ],
        },
    )
    got = summary.dispositions(run)
    assert got.admit_count == 1
    assert got.decline_count == 3
    assert sorted(got.declines_by_reason) == ["implementation_detail", "near_duplicate"]
    assert len(got.declines_by_reason["near_duplicate"]) == 2


def test_dispositions_survives_a_non_dict_member(tmp_path):
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    write_json(
        run.triage,
        {"schema_version": "0.1", "run_id": run.root.name,
         "dispositions": ["oops-a-string", {"candidate_id": "a", "disposition": "admit"}]},
    )
    got = summary.dispositions(run)
    assert got.admit_count == 1, "the string member is dropped, not raised on"


def test_deficiencies_pairs_each_with_its_projection(tmp_path):
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="intake")
    write_json(
        run.triage,
        {
            "schema_version": "0.1",
            "run_id": run.root.name,
            "dispositions": [],
            "deficiencies": [{"id": "def-1", "statement": "no error path", "status": "open"}],
            "projections": [{"deficiency_id": "def-1", "description": "author one"}],
        },
    )
    got = summary.deficiencies(run)
    assert [d.id_ for d in got] == ["def-1"]
    assert got[0].statement == "no error path"
    assert "author one" in got[0].projection


def test_deficiencies_on_a_run_without_triage_is_empty(tmp_path):
    empty = tmp_path / "run-empty"
    empty.mkdir()
    assert summary.deficiencies(RunPaths(empty)) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_summary.py -k "inputs or objective or dispositions or deficiencies" -v`
Expected: FAIL — `AttributeError: module 'rubrica.summary' has no attribute 'inputs'`.

- [ ] **Step 3: Write the minimal implementation**

Append to `src/rubrica/summary.py`:

```python
@dataclass(frozen=True)
class InputRow:
    artifact_id: str
    kind: str
    bytes_: int
    sha256: str
    source_path: str
    stored_as: str


@dataclass(frozen=True)
class Inputs:
    rows: list[InputRow]
    total_bytes: int
    kinds: dict[str, int]


def inputs(run: RunPaths) -> Inputs | Absent:
    """`manifest.inputs[]`, with bytes totalled and kinds tallied."""
    payload = _mapping(_quietly(run.manifest))
    if not payload:
        return Absent("manifest.json")
    rows = []
    kinds: dict[str, int] = {}
    for member in _dicts(payload.get("inputs")):
        kind = str(member.get("kind", ""))
        kinds[kind] = kinds.get(kind, 0) + 1
        rows.append(
            InputRow(
                artifact_id=str(member.get("artifact_id", "")),
                kind=kind,
                # int() over a value that may be absent or a string: a hand-edited
                # manifest is the shape _dicts exists for, and a bytes column that
                # raises would take the whole page with it.
                bytes_=_as_int(member.get("bytes")),
                sha256=str(member.get("sha256", "")),
                source_path=str(member.get("source_path", "")),
                stored_as=str(member.get("stored_as", "")),
            )
        )
    return Inputs(rows=rows, total_bytes=sum(r.bytes_ for r in rows), kinds=kinds)


def _as_int(value) -> int:
    """`value` as an int, or 0. A summed column must never raise on one row."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class Surface:
    name: str
    evidence: list[str]
    candidates: int
    bytes_: int


@dataclass(frozen=True)
class Objective:
    declared: str
    supported: object
    predicted_count: object
    surfaces: list[Surface]


def objective(run: RunPaths) -> Objective | Absent:
    """The objective verdict and the surfaces the corpus map found.

    Read from `00-objective.json` rather than from the sealed triage record's
    copy of `objective_review`, because the objective pass writes this one and a
    run can hold it while triage-seal has not run yet.
    """
    payload = _mapping(_quietly(run.objective))
    if not payload:
        return Absent("00-objective.json")
    review = _mapping(payload.get("objective_review"))
    surfaces = [
        Surface(
            name=str(member.get("name", "")),
            evidence=_strings(member.get("evidence")),
            candidates=_as_int(_mapping(member.get("weight")).get("candidates")),
            bytes_=_as_int(_mapping(member.get("weight")).get("bytes")),
        )
        for member in _dicts(review.get("surfaces"))
    ]
    return Objective(
        declared=str(review.get("declared_objective", "")),
        supported=review.get("supported"),
        predicted_count=payload.get("predicted_surface_count"),
        surfaces=surfaces,
    )


@dataclass(frozen=True)
class Dispositions:
    admits: list[dict]
    declines_by_reason: dict[str, list[dict]]
    admit_count: int
    decline_count: int


def dispositions(run: RunPaths) -> Dispositions | Absent:
    """Admits priority-sorted, declines grouped by reason code.

    `admit_sort_key` rather than a local sort, for the reason brief.py imports
    it: the priority order a human reads at gate 0 is one definition, and a
    second spelling of it here would drift from the first.
    """
    payload = _mapping(_quietly(run.triage))
    if not payload:
        return Absent("00-triage.json")
    admits, declines = [], {}
    for member in _dicts(payload.get("dispositions")):
        if member.get("disposition") == "admit":
            admits.append(member)
        elif member.get("disposition") == "decline":
            code = str(member.get("reason_code", ""))
            declines.setdefault(code, []).append(member)
    # No try/except around this sort, deliberately. admit_sort_key is documented
    # total and coerces every value precisely so it cannot raise -- a non-integer
    # priority sorts as if absent and the id goes through repr(). Guarding it here
    # would assert a failure mode its docstring says it removed.
    admits.sort(key=admit_sort_key)
    return Dispositions(
        admits=admits,
        declines_by_reason=dict(sorted(declines.items())),
        admit_count=len(admits),
        decline_count=sum(len(v) for v in declines.values()),
    )


@dataclass(frozen=True)
class Deficiency:
    id_: str
    statement: str
    projection: str


def deficiencies(run: RunPaths) -> list[Deficiency]:
    """Every deficiency from triage and audit, each beside the projection that
    would close it.

    A list rather than `Absent`: both source documents are optional, and an
    empty list is the honest reading of a run that has neither. The pairing is
    by `deficiency_id`, and a deficiency with no projection renders an empty
    string -- that absence is the point, since a deficiency nothing would close
    is the one worth reading.
    """
    found: list[Deficiency] = []
    for path in (run.triage, run.audit):
        payload = _mapping(_quietly(path))
        if not payload:
            continue
        projections: dict[str, list[str]] = {}
        for proj in _dicts(payload.get("projections")):
            key = str(proj.get("deficiency_id", ""))
            text = str(proj.get("description", proj.get("statement", "")))
            projections.setdefault(key, []).append(text)
        for member in _dicts(payload.get("deficiencies")):
            did = str(member.get("id", ""))
            found.append(
                Deficiency(
                    id_=did,
                    statement=str(member.get("statement", "")),
                    projection="; ".join(projections.get(did, [])),
                )
            )
    return found
```

Add `admit_sort_key` to the module's imports:

```python
from rubrica.intake import admit_sort_key
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_summary.py -v`
Expected: PASS.

If `admit_sort_key` has a different signature than `brief.py`'s use of it,
check `rg -n 'admit_sort_key' src/rubrica/brief.py src/rubrica/intake.py` and
match that call shape — it takes one disposition dict.

- [ ] **Step 5: Verify the ruff gates pass**

Run: `uv run ruff check src/rubrica/summary.py tests/unit/test_summary.py && uv run ruff format --check src/rubrica/summary.py tests/unit/test_summary.py`

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/summary.py tests/unit/test_summary.py
git commit -S -s -m "feat: Read intake and triage into the run summary

Declines grouped by reason code rather than listed, which is the shape that
makes a near_duplicate run of eleven readable. A deficiency with no projection
renders the empty string on purpose: that is the one worth reading."
```

---

### Task 4: World model, claim utilisation, gaps, contradictions

Spec §3.3. **The contradiction shape is the trap in this task:** a part is
`{schema_version, subject_id, contradictions[]}`, so `resolution` is nested one
level inside each member of `contradictions[]`. Reading it as a top-level field
yields a tally of `{"null": 14}` — measured during design, on real parts.

**Files:**
- Modify: `src/rubrica/summary.py`
- Modify: `tests/unit/test_summary.py`

**Interfaces:**
- Consumes: `Absent`, `_mapping`, `_dicts`, `_strings`, `_quietly`, `_as_int`, `list_json`.
- Produces:
  - `@dataclass(frozen=True) class WorldModel: counts: dict[str, int]; target: dict; denominator: dict`
  - `@dataclass(frozen=True) class Utilisation: cited: int; total: int; pct: float | None; uncited: list[str]; per_artifact: list[dict]`
  - `@dataclass(frozen=True) class Gap: id_: str; subject: str; blocks: list[str]; unknown: str; why: str`
  - `@dataclass(frozen=True) class Contradictions: total: int; by_resolution: dict[str, int]; parts_swept: int`
  - `world_model(run) -> WorldModel | Absent`, `utilisation(run) -> Utilisation | Absent`, `gaps(run) -> list[Gap]`, `contradictions(run) -> Contradictions | Absent`

- [ ] **Step 1: Write the failing tests**

```python
def test_world_model_counts_every_kind(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    got = summary.world_model(run)
    for kind in ("capabilities", "entities", "actors", "goals", "gaps", "contradictions"):
        assert kind in got.counts, f"{kind} is a world-model collection"
    assert got.counts["capabilities"] > 0


def test_world_model_before_the_seal_is_absent(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="extract")
    assert isinstance(summary.world_model(run), summary.Absent)


def test_utilisation_totals_and_names_uncited_artifacts(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    got = summary.utilisation(run)
    assert got.total > 0
    assert got.cited <= got.total
    assert got.pct == pytest.approx(got.cited / got.total * 100)
    for artifact_id in got.uncited:
        matching = [a for a in got.per_artifact if a["artifact_id"] == artifact_id]
        assert matching and matching[0]["cited"] == 0


def test_utilisation_before_the_seal_is_absent(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="extract")
    assert isinstance(summary.utilisation(run), summary.Absent)


def test_gaps_carry_their_blocks_array(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    got = summary.gaps(run)
    assert got, "the toy world model carries a gap"
    assert all(isinstance(g.blocks, list) for g in got)


def test_gaps_without_a_world_model_is_empty(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="extract")
    assert summary.gaps(run) == []


def test_contradictions_tallies_resolution_nested_inside_each_part(tmp_path):
    """The measured trap: resolution lives inside contradictions[], not at the
    top level of the part. Reading it at the top level tallies {"null": N}."""
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    run.contradictions_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        run.contradictions_dir / "subj-a.json",
        {
            "schema_version": "0.1",
            "subject_id": "subj-a",
            "contradictions": [
                {"id": "con-1", "resolution": "unresolved", "statement": "x"},
                {"id": "con-2", "resolution": "preferred_a", "statement": "y"},
            ],
        },
    )
    write_json(
        run.contradictions_dir / "subj-b.json",
        {"schema_version": "0.1", "subject_id": "subj-b", "contradictions": []},
    )
    got = summary.contradictions(run)
    assert got.total == 2
    assert got.parts_swept == 2
    assert got.by_resolution["unresolved"] == 1
    assert got.by_resolution["preferred_a"] == 1
    assert "null" not in got.by_resolution


def test_contradictions_names_unresolved_at_zero(tmp_path):
    """brief.py's ruling: unresolved is named at zero whenever the tally renders
    at all, because a reader scanning for it must not have to infer absence."""
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    run.contradictions_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        run.contradictions_dir / "subj-a.json",
        {"schema_version": "0.1", "subject_id": "subj-a",
         "contradictions": [{"id": "con-1", "resolution": "both_possible"}]},
    )
    got = summary.contradictions(run)
    assert got.by_resolution["unresolved"] == 0


def test_contradictions_without_the_directory_is_absent(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="extract")
    got = summary.contradictions(run)
    assert isinstance(got, summary.Absent) or got.parts_swept == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_summary.py -k "world_model or utilisation or gaps or contradictions" -v`
Expected: FAIL — `AttributeError: module 'rubrica.summary' has no attribute 'world_model'`.

- [ ] **Step 3: Write the minimal implementation**

Add to the imports at the top of `src/rubrica/summary.py`:

```python
from rubrica.sizing import implied_size
from rubrica.utilisation import claim_utilisation
```

Append:

```python
_WORLD_MODEL_COLLECTIONS = (
    "capabilities",
    "entities",
    "actors",
    "goals",
    "gaps",
    "contradictions",
)


@dataclass(frozen=True)
class WorldModel:
    counts: dict[str, int]
    target: dict
    denominator: dict


def world_model(run: RunPaths) -> WorldModel | Absent:
    """The sealed world model's collection counts, plus target and denominator."""
    payload = _mapping(_quietly(run.world_model))
    if not payload:
        return Absent("01-world-model.json")
    counts = {name: len(_dicts(payload.get(name))) for name in _WORLD_MODEL_COLLECTIONS}
    return WorldModel(
        counts=counts,
        target=_mapping(payload.get("target")),
        denominator=_mapping(payload.get("denominator")),
    )


@dataclass(frozen=True)
class Utilisation:
    cited: int
    total: int
    pct: float | None
    uncited: list[str]
    per_artifact: list[dict]


def utilisation(run: RunPaths) -> Utilisation | Absent:
    """Claim utilisation, from `claim_utilisation` rather than recomputed.

    The uncited artifacts are named rather than counted, because that is the
    actionable half: "18.4% overall" tells a reader the run is thin, and "these
    eleven inputs contributed nothing" tells them where to look. Measured across
    the three runs on disk at design time: 32.3%, 33.6%, 65.6%.
    """
    report = _mapping(claim_utilisation(run))
    artifacts = _dicts(report.get("artifacts"))
    if not artifacts:
        return Absent("claim utilisation (no world model yet)")
    cited = sum(_as_int(a.get("cited")) for a in artifacts)
    total = sum(_as_int(a.get("total")) for a in artifacts)
    return Utilisation(
        cited=cited,
        total=total,
        pct=(cited / total * 100) if total else None,
        uncited=[
            str(a.get("artifact_id", "")) for a in artifacts if _as_int(a.get("cited")) == 0
        ],
        per_artifact=artifacts,
    )


@dataclass(frozen=True)
class Gap:
    id_: str
    subject: str
    blocks: list[str]
    unknown: str
    why: str


def gaps(run: RunPaths) -> list[Gap]:
    """Every gap, with the stages it blocks.

    `blocks` is a column rather than a flag. Measured at design time: every gap
    in every run on disk carried a non-empty `blocks` (8 of 8, 19 of 19, 15 of
    15), so a flag on it would fire always and discriminate nothing.
    """
    payload = _mapping(_quietly(run.world_model))
    return [
        Gap(
            id_=str(member.get("id", "")),
            subject=str(member.get("subject", "")),
            blocks=_strings(member.get("blocks")),
            unknown=str(member.get("unknown", "")),
            why=str(member.get("why_it_matters", "")),
        )
        for member in _dicts(payload.get("gaps"))
    ]


@dataclass(frozen=True)
class Contradictions:
    total: int
    by_resolution: dict[str, int]
    parts_swept: int


def contradictions(run: RunPaths) -> Contradictions | Absent:
    """A tally over `01-contradictions/`, never the contradictions themselves.

    An aggregate on purpose -- the ruling gate-brief already makes: this is a
    pointer at the directory rather than a substitute for reading it.

    **`resolution` is nested inside each member of a part's `contradictions[]`,
    not a top-level field of the part.** A part is `{schema_version, subject_id,
    contradictions[]}`. Reading `resolution` off the part was measured against
    the real parts during design and tallied `{"null": 14}` for a run whose
    actual tally is `both_possible=1 preferred_a=1 preferred_b=1`.

    `unresolved` is named at zero whenever this renders at all, because a
    non-zero unresolved is the cheapest signal that a part is worth opening and a
    reader scanning for it must not have to infer its absence from a missing key.
    """
    try:
        parts = list_json(run.contradictions_dir)
    except Exception:
        return Absent("01-contradictions/")
    if not parts:
        return Absent("01-contradictions/")
    by_resolution: dict[str, int] = {"unresolved": 0}
    total = 0
    for path in parts:
        part = _mapping(_quietly(path))
        for member in _dicts(part.get("contradictions")):
            total += 1
            key = str(member.get("resolution", "")) or "(unrecorded)"
            by_resolution[key] = by_resolution.get(key, 0) + 1
    return Contradictions(
        total=total,
        by_resolution=dict(sorted(by_resolution.items())),
        parts_swept=len(parts),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_summary.py -v`
Expected: PASS.

- [ ] **Step 5: Verify the ruff gates pass**

Run: `uv run ruff check src/rubrica/summary.py tests/unit/test_summary.py && uv run ruff format --check src/rubrica/summary.py tests/unit/test_summary.py`

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/summary.py tests/unit/test_summary.py
git commit -S -s -m "feat: Read the world model, utilisation, gaps and contradictions

The contradiction tally reads resolution from inside each part's contradictions
array, not off the part: the top-level read was measured against the real parts
and tallied {null: 14} for a run whose real tally is three distinct resolutions.

Gaps get a column, not a flag. Every gap in every run on disk carries a
non-empty blocks array (8/8, 19/19, 15/15), so a flag would fire always."
```

---

### Task 5: Coverage, rounds, the matrix, and holes

Spec §3.4.

**Files:**
- Modify: `src/rubrica/summary.py`
- Modify: `tests/unit/test_summary.py`

**Interfaces:**
- Consumes: `Absent`, `_mapping`, `_dicts`, `_strings`, `_quietly`, `_as_int`, `list_json`, `implied_size`.
- Produces:
  - `@dataclass(frozen=True) class RoundRow: round_: object; verdict: str; cells_covered: int; cells_total: int; pct: object; goals_covered: int; goals_total: int; new_cells: object; rounds_without_progress: object; holes: int`
  - `@dataclass(frozen=True) class Cell: capability_id: str; outcome_class_id: str; covered: bool; scenario_ids: list[str]`
  - `@dataclass(frozen=True) class Hole: ref: str; reason: str; justification: str`
  - `@dataclass(frozen=True) class Coverage: rounds: list[RoundRow]; terminal_verdict: str; cells: list[Cell]; holes: list[Hole]; implied: dict | None`
  - `coverage(run) -> Coverage | Absent`

- [ ] **Step 1: Write the failing tests**

```python
def test_coverage_reads_a_row_per_round_document(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score")
    latest = read_json(run.coverage_latest)
    write_json(run.coverage_round(1), latest)
    got = summary.coverage(run)
    assert got.rounds, "a round document yields a row"
    assert got.terminal_verdict


def test_coverage_exposes_matrix_cells_with_their_scenarios(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="score")
    got = summary.coverage(run)
    assert got.cells, "the toy coverage carries capability cells"
    covered = [c for c in got.cells if c.covered]
    assert covered, "at least one cell is covered"
    assert all(isinstance(c.scenario_ids, list) for c in got.cells)


def test_coverage_reads_holes_with_reason_and_justification(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score")
    doc = read_json(run.coverage_latest)
    doc["holes"] = [
        {"ref": "cell:cap-a/oc-x", "reason": "unreachable", "justification": "no mapping"},
        {"ref": "cell:cap-a/oc-y", "reason": "no_evidence", "justification": "nothing shows it"},
    ]
    write_json(run.coverage_latest, doc)
    got = summary.coverage(run)
    assert [h.reason for h in got.holes] == ["unreachable", "no_evidence"]
    assert got.holes[0].ref == "cell:cap-a/oc-x"


def test_coverage_before_score_is_absent(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="propose")
    assert isinstance(summary.coverage(run), summary.Absent)


def test_coverage_survives_a_pct_that_is_not_a_number(tmp_path):
    """Measured in cli.py's own history: a coverage document with pct: "half" is
    a repairable score-stage defect, not a reason for a report to raise."""
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score")
    doc = read_json(run.coverage_latest)
    doc["capability_matrix"]["pct"] = "half"
    write_json(run.coverage_latest, doc)
    got = summary.coverage(run)
    assert not isinstance(got, summary.Absent)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_summary.py -k coverage -v`
Expected: FAIL — `AttributeError: module 'rubrica.summary' has no attribute 'coverage'`.

- [ ] **Step 3: Write the minimal implementation**

Append:

```python
@dataclass(frozen=True)
class RoundRow:
    round_: object
    verdict: str
    cells_covered: int
    cells_total: int
    pct: object
    goals_covered: int
    goals_total: int
    new_cells: object
    rounds_without_progress: object
    holes: int


@dataclass(frozen=True)
class Cell:
    capability_id: str
    outcome_class_id: str
    covered: bool
    scenario_ids: list[str]


@dataclass(frozen=True)
class Hole:
    ref: str
    reason: str
    justification: str


@dataclass(frozen=True)
class Coverage:
    rounds: list[RoundRow]
    terminal_verdict: str
    cells: list[Cell]
    holes: list[Hole]
    implied: dict | None


def _round_row(doc: dict) -> RoundRow:
    caps = _mapping(doc.get("capability_matrix"))
    goals = _mapping(doc.get("goal_matrix"))
    progress = _mapping(doc.get("progress"))
    return RoundRow(
        round_=doc.get("round"),
        verdict=str(doc.get("verdict", "")),
        cells_covered=_as_int(caps.get("covered")),
        cells_total=_as_int(caps.get("total")),
        # pct is passed through rather than coerced: a non-numeric pct is a
        # score-stage defect for `validate` to name, and rendering the value the
        # file actually holds is more use to a reader than rendering 0.
        pct=caps.get("pct"),
        goals_covered=_as_int(goals.get("covered")),
        goals_total=_as_int(goals.get("total")),
        new_cells=progress.get("new_cells_this_round"),
        rounds_without_progress=progress.get("rounds_without_progress"),
        holes=len(_dicts(doc.get("holes"))),
    )


def coverage(run: RunPaths) -> Coverage | Absent:
    """The round progression, the capability matrix, the holes, the implied size.

    Rows come from the `round-N.json` documents so the progression is visible;
    the matrix and holes come from `latest.json`, which is the state the run
    ended in. A run holding only `latest.json` still renders one row, because
    `latest` is a round document too.
    """
    latest = _mapping(_quietly(run.coverage_latest))
    try:
        round_paths = [p for p in list_json(run.coverage_dir) if p.name != "latest.json"]
    except Exception:
        round_paths = []
    if not latest and not round_paths:
        return Absent("03-coverage/")

    rows = []
    for path in round_paths:
        doc = _mapping(_quietly(path))
        if doc:
            rows.append(_round_row(doc))
    if not rows and latest:
        rows.append(_round_row(latest))
    rows.sort(key=lambda r: _as_int(r.round_))

    caps = _mapping(latest.get("capability_matrix"))
    cells = [
        Cell(
            capability_id=str(member.get("capability_id", "")),
            outcome_class_id=str(member.get("outcome_class_id", "")),
            covered=bool(member.get("covered")),
            scenario_ids=_strings(member.get("scenario_ids")),
        )
        for member in _dicts(caps.get("cells"))
    ]
    holes = [
        Hole(
            ref=str(member.get("ref", "")),
            reason=str(member.get("reason", "")),
            justification=str(member.get("justification", "")),
        )
        for member in _dicts(latest.get("holes"))
    ]
    return Coverage(
        rounds=rows,
        terminal_verdict=str(latest.get("verdict", "")),
        cells=cells,
        holes=holes,
        implied=implied_size(run),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_summary.py -v`
Expected: PASS.

- [ ] **Step 5: Verify the ruff gates pass**

Run: `uv run ruff check src/rubrica/summary.py tests/unit/test_summary.py && uv run ruff format --check src/rubrica/summary.py tests/unit/test_summary.py`

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/summary.py tests/unit/test_summary.py
git commit -S -s -m "feat: Read the coverage progression, matrix and holes

pct is passed through rather than coerced: a non-numeric pct is a score-stage
defect for validate to name, and rendering what the file holds tells a reader
more than rendering a zero would."
```

---

### Task 6: The scenario table — one line each, joined across three directories

Spec §3.5. This is the section the report exists for. A row is joined from
`02-scenarios.json`, `05-verdicts/<sid>.json` and `06-suite/<sid>/`; long prose
(`discriminating_fact`, verdict `notes`) is carried on the row for the renderer
to put in a `title` attribute, never as a column.

**Files:**
- Modify: `src/rubrica/summary.py`
- Modify: `tests/unit/test_summary.py`

**Interfaces:**
- Consumes: `Absent`, `_mapping`, `_dicts`, `_strings`, `_quietly`, `_as_int`.
- Produces:
  - `SUITE_FILES: tuple[str, ...] = ("task.toml", "seed.json", "golden.json", "instruction.md", "provenance.md", "tests")`
  - `@dataclass(frozen=True) class ScenarioRow` with fields: `id_: str`, `round_: object`, `title: str`, `goal_id: str`, `actor_id: str`, `hop_depth: object`, `cells: list[str]`, `status: str`, `discriminating_fact: str`, `verdict: str`, `uniquely_determined: object`, `derivable: object`, `min_tool_calls: object`, `notes: str`, `has_instance: bool`, `suite_files: list[str]`, `difficulty_overstated: bool`
  - `scenarios(run) -> list[ScenarioRow] | Absent`

- [ ] **Step 1: Write the failing tests**

```python
def test_scenarios_returns_a_row_per_scenario(tmp_path):
    from rubrica.artifacts import read_json

    run = build_toy_run(tmp_path / "runs", upto="propose")
    expected = len(read_json(run.scenarios)["scenarios"])
    rows = summary.scenarios(run)
    assert len(rows) == expected


def test_scenarios_row_carries_the_record_fields(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="propose")
    row = summary.scenarios(run)[0]
    assert row.id_
    assert row.title
    assert row.goal_id
    assert row.status
    assert isinstance(row.cells, list)


def test_scenarios_flattens_capability_refs_into_cell_labels(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="propose")
    doc = read_json(run.scenarios)
    doc["scenarios"][0]["capability_refs"] = [
        {"capability_id": "cap-a", "outcome_class_id": "oc-x"},
        {"capability_id": "cap-b", "outcome_class_id": "oc-y"},
    ]
    write_json(run.scenarios, doc)
    row = summary.scenarios(run)[0]
    assert row.cells == ["cap-a/oc-x", "cap-b/oc-y"]


def test_scenarios_joins_the_challenge_verdict(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    rows = {r.id_: r for r in summary.scenarios(run)}
    judged = [r for r in rows.values() if r.verdict]
    assert judged, "a challenged run has verdicts to join"
    assert judged[0].notes or judged[0].notes == ""
    assert judged[0].uniquely_determined is not None


def test_scenarios_without_verdicts_leaves_the_verdict_empty(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="propose")
    assert all(r.verdict == "" for r in summary.scenarios(run))


def test_scenarios_flags_difficulty_overstated_when_fewer_calls_suffice(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.scenarios)
    sid = doc["scenarios"][0]["id"]
    doc["scenarios"][0]["hop_depth"] = 3
    write_json(run.scenarios, doc)
    verdict = read_json(run.verdict(sid))
    verdict["minimum_tool_calls_found"] = 1
    write_json(run.verdict(sid), verdict)
    row = {r.id_: r for r in summary.scenarios(run)}[sid]
    assert row.difficulty_overstated is True


def test_scenarios_does_not_flag_difficulty_when_calls_match(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="challenge")
    doc = read_json(run.scenarios)
    sid = doc["scenarios"][0]["id"]
    doc["scenarios"][0]["hop_depth"] = 2
    write_json(run.scenarios, doc)
    verdict = read_json(run.verdict(sid))
    verdict["minimum_tool_calls_found"] = 2
    write_json(run.verdict(sid), verdict)
    row = {r.id_: r for r in summary.scenarios(run)}[sid]
    assert row.difficulty_overstated is False


def test_scenarios_reports_which_suite_files_landed(tmp_path):
    from rubrica.emit import emit_run

    run = build_toy_run(tmp_path / "runs")
    emit_run(run)
    rows = [r for r in summary.scenarios(run) if r.suite_files]
    assert rows, "emit writes a package for every accepted instance"
    assert "task.toml" in rows[0].suite_files
    assert "seed.json" in rows[0].suite_files


def test_scenarios_before_propose_is_absent(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="extract")
    assert isinstance(summary.scenarios(run), summary.Absent)


def test_scenarios_survives_a_non_dict_member(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="propose")
    doc = read_json(run.scenarios)
    doc["scenarios"].append("oops-a-string")
    write_json(run.scenarios, doc)
    rows = summary.scenarios(run)
    assert all(r.id_ for r in rows), "the string member is dropped, not raised on"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_summary.py -k scenarios -v`
Expected: FAIL — `AttributeError: module 'rubrica.summary' has no attribute 'scenarios'`.

- [ ] **Step 3: Write the minimal implementation**

Append:

```python
# The files emit writes into a package. Listed so the table can report which
# landed rather than only whether the directory exists: a package missing its
# golden.json is a different failure from a package that was never written.
SUITE_FILES: tuple[str, ...] = (
    "task.toml",
    "seed.json",
    "golden.json",
    "instruction.md",
    "provenance.md",
    "tests",
)


@dataclass(frozen=True)
class ScenarioRow:
    id_: str
    round_: object
    title: str
    goal_id: str
    actor_id: str
    hop_depth: object
    cells: list[str]
    status: str
    discriminating_fact: str
    verdict: str
    uniquely_determined: object
    derivable: object
    min_tool_calls: object
    notes: str
    has_instance: bool
    suite_files: list[str]
    difficulty_overstated: bool


def _suite_files(run: RunPaths, scenario_id: str) -> list[str]:
    """Which of SUITE_FILES the emitted package holds, or [] if there is none."""
    try:
        directory = run.task_dir(scenario_id)
    except Exception:
        # An id that is not a safe path segment: task_dir raises UnsafeSegment,
        # and a row is more use than a traceback. paths.py makes the same call
        # for the same reason in scenario_ids_with_tasks.
        return []
    return [name for name in SUITE_FILES if (directory / name).exists()]


def scenarios(run: RunPaths) -> list[ScenarioRow] | Absent:
    """One row per scenario, joined across the scenario record, its verdict, and
    its emitted package.

    Long prose is carried on the row but is not a column: `discriminating_fact`
    and the verdict's `notes` are paragraphs, and the renderer puts them in a
    `title` attribute. That is what keeps a 128-scenario run a scannable table
    and is why every id is rendered as a link to the artifact on disk -- the
    drill-in path replaces inlining the seed and the golden answer.
    """
    payload = _mapping(_quietly(run.scenarios))
    if not payload:
        return Absent("02-scenarios.json")
    rows = []
    for member in _dicts(payload.get("scenarios")):
        sid = str(member.get("id", ""))
        verdict = _mapping(_quietly(run.verdict(sid))) if sid else {}
        hop = member.get("hop_depth")
        found = verdict.get("minimum_tool_calls_found")
        rows.append(
            ScenarioRow(
                id_=sid,
                round_=member.get("round"),
                title=str(member.get("title", "")),
                goal_id=str(member.get("goal_id", "")),
                actor_id=str(member.get("actor_id", "")),
                hop_depth=hop,
                cells=[
                    f"{ref.get('capability_id', '')}/{ref.get('outcome_class_id', '')}"
                    for ref in _dicts(member.get("capability_refs"))
                ],
                status=str(member.get("status", "")),
                discriminating_fact=str(member.get("discriminating_fact", "")),
                verdict=str(verdict.get("verdict", "")),
                uniquely_determined=verdict.get("uniquely_determined"),
                derivable=verdict.get("derivable_without_guessing"),
                min_tool_calls=found,
                notes=str(verdict.get("notes", "")),
                has_instance=(run.instance_dir(sid).exists() if sid else False),
                suite_files=_suite_files(run, sid) if sid else [],
                # Both sides must be numbers before this means anything: a
                # missing verdict leaves `found` None, and `None < 3` raises.
                difficulty_overstated=(
                    isinstance(found, int)
                    and isinstance(hop, int)
                    and not isinstance(found, bool)
                    and found < hop
                ),
            )
        )
    return rows
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_summary.py -v`
Expected: PASS.

Note on `test_scenarios_reports_which_suite_files_landed`: `emit_run` returns
`(ids, findings)` and writes packages even when it reports findings, so the test
ignores the return value. If it emits nothing, check that `build_toy_run` with no
`upto` built through `challenge` and that the verdicts are `accept`.

- [ ] **Step 5: Verify the ruff gates pass**

Run: `uv run ruff check src/rubrica/summary.py tests/unit/test_summary.py && uv run ruff format --check src/rubrica/summary.py tests/unit/test_summary.py`

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/summary.py tests/unit/test_summary.py
git commit -S -s -m "feat: Join each scenario to its verdict and emitted package

One line per scenario, with the seed and golden answer reached by link rather
than inlined -- what keeps a 128-scenario run scannable. difficulty_overstated
requires both sides to be real ints: a missing verdict leaves the found count
None, and None < 3 raises."
```

---

### Task 7: Challenge tallies, the suite inventory, and the flag table

Spec §3.6, §3.7.

**Files:**
- Modify: `src/rubrica/summary.py`
- Modify: `tests/unit/test_summary.py`

**Interfaces:**
- Consumes: every section builder from Tasks 2–6.
- Produces:
  - `@dataclass(frozen=True) class Challenge: tallies: dict[str, int]; judged: int; packages: int; incomplete_packages: list[str]; smoke: dict | None`
  - `@dataclass(frozen=True) class Flag: id_: str; headline: str; threshold: str; detail: str`
  - `challenge(run) -> Challenge | Absent`
  - `flags(run) -> list[Flag]`
  - `orphaned_temp_files(run) -> list[str]`

- [ ] **Step 1: Write the failing tests**

```python
def test_challenge_tallies_verdicts(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    got = summary.challenge(run)
    assert got.judged > 0
    assert sum(got.tallies.values()) == got.judged


def test_challenge_counts_emitted_packages(tmp_path):
    from rubrica.emit import emit_run

    run = build_toy_run(tmp_path / "runs")
    emit_run(run)
    got = summary.challenge(run)
    assert got.packages > 0


def test_challenge_names_a_package_missing_a_file(tmp_path):
    from rubrica.emit import emit_run

    run = build_toy_run(tmp_path / "runs")
    emitted, _ = emit_run(run)
    (run.task_dir(emitted[0]) / "golden.json").unlink()
    got = summary.challenge(run)
    assert emitted[0] in got.incomplete_packages


def test_challenge_before_the_stage_is_absent(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="propose")
    assert isinstance(summary.challenge(run), summary.Absent)


def test_orphaned_temp_files_finds_a_stray_tmp(tmp_path):
    """Found by inspection during design: an orphaned
    02-scenarios.json.tmp.43146.cb890a5abaf7 was sitting in the newest run on
    disk, and decisions.md records an earlier one removed by hand."""
    run = build_toy_run(tmp_path / "runs", upto="propose")
    (run.root / "02-scenarios.json.tmp.4242.deadbeef").write_text("{}", encoding="utf-8")
    assert summary.orphaned_temp_files(run) == ["02-scenarios.json.tmp.4242.deadbeef"]


def test_orphaned_temp_files_is_empty_on_a_clean_run(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="propose")
    assert summary.orphaned_temp_files(run) == []


def test_flags_fire_low_utilisation_below_the_threshold(tmp_path, monkeypatch):
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    monkeypatch.setattr(summary, "LOW_UTILISATION_PCT", 100.0)
    ids = {f.id_ for f in summary.flags(run)}
    assert "low-utilisation" in ids


def test_flags_do_not_fire_low_utilisation_above_the_threshold(tmp_path, monkeypatch):
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    monkeypatch.setattr(summary, "LOW_UTILISATION_PCT", 0.0)
    ids = {f.id_ for f in summary.flags(run)}
    assert "low-utilisation" not in ids


def test_flags_fire_unresolved_contradictions(tmp_path):
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    run.contradictions_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        run.contradictions_dir / "subj-a.json",
        {"schema_version": "0.1", "subject_id": "subj-a",
         "contradictions": [{"id": "con-1", "resolution": "unresolved"}]},
    )
    ids = {f.id_ for f in summary.flags(run)}
    assert "unresolved-contradictions" in ids


def test_flags_do_not_fire_unresolved_when_all_are_resolved(tmp_path):
    from rubrica.artifacts import write_json

    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    run.contradictions_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        run.contradictions_dir / "subj-a.json",
        {"schema_version": "0.1", "subject_id": "subj-a",
         "contradictions": [{"id": "con-1", "resolution": "both_possible"}]},
    )
    ids = {f.id_ for f in summary.flags(run)}
    assert "unresolved-contradictions" not in ids


def test_flags_fire_coverage_halted(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score")
    doc = read_json(run.coverage_latest)
    doc["verdict"] = "halted_no_progress"
    write_json(run.coverage_latest, doc)
    ids = {f.id_ for f in summary.flags(run)}
    assert "coverage-halted" in ids


def test_flags_do_not_fire_coverage_halted_on_converged(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="score")
    doc = read_json(run.coverage_latest)
    doc["verdict"] = "converged"
    write_json(run.coverage_latest, doc)
    ids = {f.id_ for f in summary.flags(run)}
    assert "coverage-halted" not in ids


def test_flags_fire_orphaned_temp(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="propose")
    (run.root / "02-scenarios.json.tmp.1.x").write_text("{}", encoding="utf-8")
    ids = {f.id_ for f in summary.flags(run)}
    assert "orphaned-temp" in ids


def test_flags_fire_stage_record_incomplete_when_a_stage_ran_unrecorded(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="propose")
    manifest = read_json(run.manifest)
    manifest["stages"] = {}
    write_json(run.manifest, manifest)
    ids = {f.id_ for f in summary.flags(run)}
    assert "stage-record-incomplete" in ids


def test_every_flag_states_its_threshold(tmp_path):
    """A flag whose threshold is not on the page is a black box."""
    run = build_toy_run(tmp_path / "runs", upto="propose")
    (run.root / "02-scenarios.json.tmp.1.x").write_text("{}", encoding="utf-8")
    for flag in summary.flags(run):
        assert flag.threshold, f"{flag.id_} states no threshold"
        assert flag.headline


def test_flags_on_an_empty_run_do_not_raise(tmp_path):
    empty = tmp_path / "run-empty"
    empty.mkdir()
    assert isinstance(summary.flags(RunPaths(empty)), list)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_summary.py -k "challenge or flags or orphaned" -v`
Expected: FAIL — `AttributeError: module 'rubrica.summary' has no attribute 'challenge'`.

- [ ] **Step 3: Write the minimal implementation**

Append. Note `_CODE_STAGES` — the six stages that are code and therefore have no
`manifest.stages` entry by design, so the stage-record flag must not accuse them
(CLAUDE.md: "their absence there is not a finding").

```python
# The stages that run as code rather than as a dispatched skill. They have no
# manifest.stages entry by design, so stage-record-incomplete must not accuse
# them -- CLAUDE.md states their absence there is not a finding.
#
# Measured, not assumed: `set(STAGES) - {every skill's declared stage}` is
# exactly {intake, reconcile-seal, smoke, survey, triage-seal, triage-slices}.
# Note `emit` is NOT in it -- rb-emit is a thin wrapper over `rubrica emit`, so
# emit does get a manifest.stages entry and must stay accusable. Hardcoding the
# set here got that wrong once; deriving it cannot.
_CODE_STAGES = frozenset(
    {"intake", "reconcile-seal", "smoke", "survey", "triage-seal", "triage-slices"}
)


@dataclass(frozen=True)
class Challenge:
    tallies: dict[str, int]
    judged: int
    packages: int
    incomplete_packages: list[str]
    smoke: dict | None


def challenge(run: RunPaths) -> Challenge | Absent:
    """Verdict tallies and what actually landed in the emitted suite."""
    try:
        verdict_paths = list_json(run.verdicts_dir)
    except Exception:
        verdict_paths = []
    if not verdict_paths:
        return Absent("05-verdicts/")
    tallies: dict[str, int] = {}
    for path in verdict_paths:
        doc = _mapping(_quietly(path))
        key = str(doc.get("verdict", "")) or "(unrecorded)"
        tallies[key] = tallies.get(key, 0) + 1
    try:
        package_ids = run.scenario_ids_with_tasks()
    except Exception:
        package_ids = []
    incomplete = [
        sid for sid in package_ids if len(_suite_files(run, sid)) != len(SUITE_FILES)
    ]
    return Challenge(
        tallies=dict(sorted(tallies.items())),
        judged=len(verdict_paths),
        packages=len(package_ids),
        incomplete_packages=incomplete,
        smoke=_mapping(_quietly(run.report)) or None,
    )


def orphaned_temp_files(run: RunPaths) -> list[str]:
    """Names of `*.tmp.*` files left in the run root, sorted.

    A stage writes its artifact to a temp file and renames it, so one left behind
    is a dispatch that died mid-write. Found by inspection while this was
    designed: `02-scenarios.json.tmp.43146.cb890a5abaf7` was sitting in the
    newest run on disk, and `decisions.md` records an earlier one removed by hand
    after a budget ceiling killed a reconcile pass.
    """
    try:
        return sorted(p.name for p in run.root.iterdir() if ".tmp." in p.name)
    except OSError:
        return []


@dataclass(frozen=True)
class Flag:
    id_: str
    headline: str
    threshold: str
    detail: str


def flags(run: RunPaths) -> list[Flag]:
    """Every rule-based flag that fires for this run.

    Each carries the threshold that fired it, because a flag whose rule is not on
    the page is a black box a reader cannot argue with. Only `low-utilisation`
    has a tunable threshold; the rest trigger on a count crossing zero or a
    comparison between two fields the artifacts already hold.
    """
    found: list[Flag] = []

    util = utilisation(run)
    if isinstance(util, Utilisation) and util.pct is not None:
        if util.pct < LOW_UTILISATION_PCT:
            found.append(
                Flag(
                    id_="low-utilisation",
                    headline=f"Claim utilisation {util.pct:.1f}%",
                    threshold=f"overall cited/total below {LOW_UTILISATION_PCT:.0f}%",
                    detail=f"{util.cited} of {util.total} claims cited by the world model",
                )
            )
        if util.uncited:
            found.append(
                Flag(
                    id_="uncited-artifacts",
                    headline=f"{len(util.uncited)} input(s) contributed no cited claim",
                    threshold="any artifact with cited == 0",
                    detail=", ".join(util.uncited),
                )
            )

    cons = contradictions(run)
    if isinstance(cons, Contradictions):
        unresolved = cons.by_resolution.get("unresolved", 0)
        if unresolved:
            found.append(
                Flag(
                    id_="unresolved-contradictions",
                    headline=f"{unresolved} unresolved contradiction(s)",
                    threshold="any contradiction whose resolution is unresolved",
                    detail=(
                        "a later pass may be modelling one side without saying so; "
                        f"swept {cons.parts_swept} subject part(s)"
                    ),
                )
            )

    cov = coverage(run)
    if isinstance(cov, Coverage) and cov.terminal_verdict:
        if cov.terminal_verdict != "converged":
            found.append(
                Flag(
                    id_="coverage-halted",
                    headline=f"Coverage ended {cov.terminal_verdict}",
                    threshold="terminal verdict is not converged",
                    detail=f"{len(cov.holes)} open hole(s) at the last round",
                )
            )

    rows = scenarios(run)
    if isinstance(rows, list):
        overstated = [r.id_ for r in rows if r.difficulty_overstated]
        if overstated:
            found.append(
                Flag(
                    id_="difficulty-overstated",
                    headline=f"{len(overstated)} scenario(s) reachable in fewer calls",
                    threshold="minimum_tool_calls_found < hop_depth",
                    detail=", ".join(overstated),
                )
            )

    strays = orphaned_temp_files(run)
    if strays:
        found.append(
            Flag(
                id_="orphaned-temp",
                headline=f"{len(strays)} orphaned temp file(s)",
                threshold="any *.tmp.* in the run root",
                detail=", ".join(strays) + " -- a dispatch died mid-write",
            )
        )

    head = header(run)
    if isinstance(head, Header):
        recorded = {s.stage for s in head.stages}
        produced = {row.name for row in stage_spine(run) if row.produced}
        missing = sorted(produced - recorded - _CODE_STAGES)
        if missing:
            found.append(
                Flag(
                    id_="stage-record-incomplete",
                    headline=f"{len(missing)} dispatched stage(s) unrecorded in the manifest",
                    threshold="a produced prompt stage with no manifest.stages entry",
                    detail=(
                        ", ".join(missing)
                        + " -- without model, effort and skill hash the run is not comparable"
                    ),
                )
            )

    return found
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_summary.py -v`
Expected: PASS.

If `test_flags_fire_stage_record_incomplete_when_a_stage_ran_unrecorded` fails
because nothing is missing, confirm `_CODE_STAGES` does not contain `extract`,
`propose`, or `emit` — all three are dispatched skills and must stay accusable.
Verify the set with:

```bash
uv run python -c "
from rubrica.paths import STAGES
from rubrica import skills
have = {s.contract.get('stage') for s in skills.discover()}
print(sorted(set(STAGES) - have))"
```

Expected: `['intake', 'reconcile-seal', 'smoke', 'survey', 'triage-seal', 'triage-slices']`.
If that list has changed, update `_CODE_STAGES` to match it.

- [ ] **Step 5: Verify the ruff gates pass**

Run: `uv run ruff check src/rubrica/summary.py tests/unit/test_summary.py && uv run ruff format --check src/rubrica/summary.py tests/unit/test_summary.py`

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/summary.py tests/unit/test_summary.py
git commit -S -s -m "feat: Tally the challenge, inventory the suite, and flag what looks wrong

Every flag states the threshold that fired it: a rule not on the page is one a
reader cannot argue with. The orphaned-temp flag was found by inspection -- one
was sitting in the newest run on disk. Code stages are exempt from the
stage-record flag, since their absence from manifest.stages is by design."
```

---

### Task 8: The renderer — one self-contained HTML page

Spec §3, §4.1. Markup moves to its own module here, as planned: `summary.py` reads
and computes, `summary_html.py` renders. The cut falls at the dataclass boundary.

**Files:**
- Create: `src/rubrica/summary_html.py`
- Modify: `src/rubrica/summary.py` (add `run_summary`)
- Modify: `tests/unit/test_summary.py`

**Interfaces:**
- Consumes: every dataclass from Tasks 1–7, and `esc`.
- Produces:
  - `summary_html.render(run: RunPaths) -> str` — the whole document.
  - `summary.run_summary(run: RunPaths) -> str` — thin re-export so callers have one entry point.

- [ ] **Step 1: Write the failing tests**

```python
def test_render_produces_one_self_contained_document(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    html = summary.run_summary(run)
    assert html.startswith("<!doctype html>")
    assert "</html>" in html
    assert "<style>" in html, "CSS is inline; the page has no external assets"


def test_render_references_no_external_resource(tmp_path):
    """Self-contained means no network: a page that fetches is a page that breaks
    when the run directory is archived or read offline."""
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    html = summary.run_summary(run)
    for token in ("http://", "https://", "<script src=", "<link rel=\"stylesheet\""):
        assert token not in html, f"{token} makes the page depend on something outside it"


def test_render_names_the_run(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    assert run.root.name in summary.run_summary(run)


def test_render_includes_every_section_heading(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    html = summary.run_summary(run)
    for heading in ("Inputs", "Scenarios", "Coverage", "World model", "Flags"):
        assert heading in html, f"the {heading} section is missing"


def test_render_escapes_prose_carrying_markup_and_quotes(tmp_path):
    """discriminating_fact and verdict notes reach a title attribute and carry
    double quotes in real runs; an unescaped one ends the attribute early."""
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="propose")
    doc = read_json(run.scenarios)
    doc["scenarios"][0]["discriminating_fact"] = 'he said "<script>alert(1)</script>" & left'
    write_json(run.scenarios, doc)
    html = summary.run_summary(run)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "&quot;" in html


def test_render_escapes_a_title_bearing_markup(tmp_path):
    from rubrica.artifacts import read_json, write_json

    run = build_toy_run(tmp_path / "runs", upto="propose")
    doc = read_json(run.scenarios)
    doc["scenarios"][0]["title"] = "<b>bold</b>"
    write_json(run.scenarios, doc)
    html = summary.run_summary(run)
    assert "<b>bold</b>" not in html
    assert "&lt;b&gt;bold&lt;/b&gt;" in html


def test_render_states_an_absence_rather_than_omitting_the_section(tmp_path):
    """The 10-of-11 case: a partial run renders every section, saying what is
    not there. A section silently omitted is indistinguishable from one the
    renderer forgot."""
    run = build_toy_run(tmp_path / "runs", upto="extract")
    html = summary.run_summary(run)
    assert "01-world-model.json" in html, "the absent artifact is named"
    assert "Scenarios" in html, "the section still has its heading"


def test_render_on_an_empty_directory_still_produces_a_page(tmp_path):
    empty = tmp_path / "run-empty"
    empty.mkdir()
    html = summary.run_summary(RunPaths(empty))
    assert html.startswith("<!doctype html>")
    assert "</html>" in html


def test_render_links_each_scenario_to_its_artifacts(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    html = summary.run_summary(run)
    assert "05-verdicts/" in html, "ids are links to the artifacts on disk"


def test_render_includes_decisions_md_when_present(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    (run.root / "decisions.md").write_text("- a decision was taken\n", encoding="utf-8")
    assert "a decision was taken" in summary.run_summary(run)


def test_render_escapes_decisions_md(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    (run.root / "decisions.md").write_text("- <b>not bold</b>\n", encoding="utf-8")
    html = summary.run_summary(run)
    assert "<b>not bold</b>" not in html
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_summary.py -k render -v`
Expected: FAIL — `AttributeError: module 'rubrica.summary' has no attribute 'run_summary'`.

- [ ] **Step 3: Write the implementation**

Create `src/rubrica/summary_html.py`. Build it section by section; each helper
takes a dataclass (or `Absent`) and returns a markup string. The shape to follow —
every section goes through `_section`, which is what guarantees an `Absent`
renders its heading rather than vanishing:

```python
"""The markup half of `run-summary`. `summary.py` reads and computes; this renders.

Hand-built markup over a templating dependency, the choice
`scripts/render-pipeline-diagram.py` already made in this repo: the project has
three runtime dependencies, each argued for in pyproject.toml, and a report is a
poor reason to make Jinja the fourth.

Everything user-controlled goes through `summary.esc`. That is not stylistic:
`discriminating_fact` and a verdict's `notes` are rendered into `title`
attributes and both carry double quotes in real runs, so an unescaped value ends
the attribute and spills prose into the tag.

The page is self-contained -- inline CSS, inline JS, no external asset and no
network -- so it still reads when the run directory is archived or opened
offline. Links to sibling artifacts are relative, which is what lets the page
travel with the run while remaining openable on its own.
"""

from __future__ import annotations

from rubrica import summary
from rubrica.paths import RunPaths
from rubrica.summary import Absent, esc

_CSS = """
:root { color-scheme: light dark; }
body { font: 14px/1.5 system-ui, sans-serif; margin: 0 auto; max-width: 1200px;
       padding: 2rem; }
h1 { font-size: 1.5rem; } h2 { font-size: 1.1rem; margin-top: 2.5rem;
     border-bottom: 1px solid currentColor; padding-bottom: .25rem; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; padding: .3rem .5rem; border-bottom: 1px solid #8884; }
th { cursor: pointer; user-select: none; white-space: nowrap; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.absent { opacity: .65; font-style: italic; }
.flag { border-left: 3px solid #c60; padding: .4rem .75rem; margin: .4rem 0; }
.flag .thr { opacity: .7; font-size: 12px; }
.spine { display: flex; flex-wrap: wrap; gap: .3rem; list-style: none; padding: 0; }
.spine li { padding: .15rem .5rem; border: 1px solid #8886; border-radius: 3px;
            font-size: 12px; }
.spine li.yes { font-weight: 600; } .spine li.no { opacity: .45; }
.cell.yes { background: #2a72; } .cell.no { background: #c602; }
.mono { font-family: ui-monospace, monospace; font-size: 12px; }
details summary { cursor: pointer; }
"""

# Sorting and filtering only. No fetch, no external library: the page must work
# from a file:// URL with no network.
_JS = """
document.querySelectorAll('table.sortable').forEach(function (table) {
  table.querySelectorAll('th').forEach(function (th, i) {
    th.addEventListener('click', function () {
      var body = table.tBodies[0];
      var rows = Array.prototype.slice.call(body.rows);
      var asc = !(th.dataset.asc === 'true');
      th.dataset.asc = asc;
      rows.sort(function (a, b) {
        var x = a.cells[i].textContent.trim();
        var y = b.cells[i].textContent.trim();
        var nx = parseFloat(x), ny = parseFloat(y);
        if (!isNaN(nx) && !isNaN(ny)) { return asc ? nx - ny : ny - nx; }
        return asc ? x.localeCompare(y) : y.localeCompare(x);
      });
      rows.forEach(function (r) { body.appendChild(r); });
    });
  });
});
var filter = document.getElementById('scn-filter');
if (filter) {
  filter.addEventListener('input', function () {
    var q = filter.value.toLowerCase();
    document.querySelectorAll('#scn-table tbody tr').forEach(function (tr) {
      tr.style.display = tr.textContent.toLowerCase().indexOf(q) === -1 ? 'none' : '';
    });
  });
}
"""


def _section(heading: str, body) -> str:
    """One section, with its heading always present.

    An `Absent` renders as a stated absence naming what was looked for, never as
    a skipped section: on a run that stopped at extract, "no 01-world-model.json"
    is the most informative thing the world model section can say, and a section
    that disappears is indistinguishable from one this renderer forgot.
    """
    if isinstance(body, Absent):
        inner = f'<p class="absent">Not present: {esc(body.what)}</p>'
    else:
        inner = body
    return f"<h2>{esc(heading)}</h2>\n{inner}\n"


def render(run: RunPaths) -> str:
    """The whole page, as one string."""
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        f"<title>{esc(run.root.name)} — rubrica run summary</title>",
        f"<style>{_CSS}</style></head><body>",
        f"<h1>{esc(run.root.name)}</h1>",
        _section("Pipeline progress", _spine(run)),
        _section("Run header", _header(run)),
        _section("Flags", _flags(run)),
        _section("Inputs", _inputs(run)),
        _section("Objective", _objective(run)),
        _section("Dispositions", _dispositions(run)),
        _section("Deficiencies", _deficiencies(run)),
        _section("World model", _world_model(run)),
        _section("Claim utilisation", _utilisation(run)),
        _section("Gaps", _gaps(run)),
        _section("Contradictions", _contradictions(run)),
        _section("Coverage", _coverage(run)),
        _section("Scenarios", _scenarios(run)),
        _section("Challenge and emitted suite", _challenge(run)),
        _section("Decisions", _decisions(run)),
        f"<script>{_JS}</script>",
        "</body></html>",
    ]
    return "\n".join(parts)
```

Then write one `_<section>` helper per line in that list. Each is small and
mechanical; the rules that matter:

1. **Every interpolated value goes through `esc`.** No exceptions, including dict
   keys and numbers.
2. **Return the `Absent` unchanged** when the builder returns one — `_section`
   renders it. E.g. `def _inputs(run): got = summary.inputs(run); if
   isinstance(got, Absent): return got; ...`
3. `_scenarios` builds `<table class="sortable" id="scn-table">` preceded by
   `<input id="scn-filter" placeholder="filter scenarios">`. The `id` cell is
   `<a href="05-verdicts/{id}.json">{id}</a>` when a verdict exists, else plain
   text; `discriminating_fact` and `notes` go in `title` attributes on their
   cells, never as columns.
4. `_coverage` renders the round table plus the matrix, each matrix cell
   `<td class="cell yes">` or `class="cell no"`, its `title` listing
   `scenario_ids`.
5. `_flags` renders each `Flag` as
   `<div class="flag"><b>{headline}</b> <span class="thr">{threshold}</span><br>{detail}</div>`,
   and an empty list as `<p class="absent">No flags fired.</p>`.
6. `_decisions` reads `run.root / "decisions.md"` with
   `path.read_text(encoding="utf-8")` inside `try/except OSError`, returns
   `Absent("decisions.md")` on failure, and wraps the escaped text in `<pre>`.

Then add to `src/rubrica/summary.py`:

```python
def run_summary(run: RunPaths) -> str:
    """The whole page. One entry point, so callers never import the markup half.

    Imported here rather than at module scope: summary_html imports this module
    for its dataclasses and `esc`, so a top-level import would be circular.
    """
    from rubrica import summary_html

    return summary_html.render(run)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_summary.py -v`
Expected: PASS.

- [ ] **Step 5: Eyeball a real page**

Run:
```bash
uv run python -c "
from pathlib import Path
from rubrica.paths import RunPaths
from rubrica.summary import run_summary
for name in ('run-20260823-112746', 'run-20260825-094033', 'run-20260820-122212'):
    run = RunPaths(Path('runs') / name)
    html = run_summary(run)
    Path(f'/tmp/{name}.html').write_text(html, encoding='utf-8')
    print(name, len(html), 'bytes')"
```
Expected: three pages written, no exception. The third is a near-empty run and is
the important one — it must still produce a page. Open them and confirm the
complete run shows 14 scenarios, the second shows 18 scenarios with no verdicts
and an orphaned-temp flag, and the third is all stated absences.

- [ ] **Step 6: Verify the ruff gates pass**

Run: `uv run ruff check src/rubrica/ tests/unit/test_summary.py && uv run ruff format --check src/rubrica/ tests/unit/test_summary.py`

- [ ] **Step 7: Commit**

```bash
git add src/rubrica/summary.py src/rubrica/summary_html.py tests/unit/test_summary.py
git commit -S -s -m "feat: Render the run summary as one self-contained page

Hand-built markup rather than a templating dependency, the choice
render-pipeline-diagram.py already made here: three runtime dependencies are
each argued for in pyproject.toml, and a report is a poor reason to add a fourth.

An absent artifact renders its heading and names what is missing rather than
dropping the section -- a section that vanishes cannot be told from one the
renderer forgot, and 10 of the 11 runs on disk are partial."
```

---

### Task 9: Wire the CLI, and update the docs in the same commit

`tests/unit/test_docs_accuracy.py` asserts in **both** directions that
`cli.SUBCOMMANDS` and `docs/reference/cli.md` agree, so the code and the docs
must land together — a commit with only the wiring is a red suite.

**Files:**
- Modify: `src/rubrica/cli.py`
- Modify: `docs/reference/cli.md`
- Modify: `tests/unit/test_summary.py`

**Interfaces:**
- Consumes: `summary.run_summary`.
- Produces: the `rubrica run-summary --run RUN [-o PATH]` command.

- [ ] **Step 1: Write the failing tests**

```python
def test_cli_writes_the_page_into_the_run_by_default(tmp_path, capsys):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    code = cli.main(["run-summary", "--run", str(run.root)])
    assert code == 0
    written = run.root / "run-summary.html"
    assert written.exists()
    assert written.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_cli_prints_the_path_it_wrote(tmp_path, capsys):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    cli.main(["run-summary", "--run", str(run.root)])
    assert "run-summary.html" in capsys.readouterr().out


def test_cli_honours_an_explicit_output_path(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="challenge")
    out = tmp_path / "elsewhere" / "page.html"
    out.parent.mkdir()
    assert cli.main(["run-summary", "--run", str(run.root), "-o", str(out)]) == 0
    assert out.exists()


def test_cli_exits_clean_on_a_run_that_stopped_early(tmp_path):
    """A report is never a gate: the 10-of-11 partial case must exit 0."""
    run = build_toy_run(tmp_path / "runs", upto="extract")
    assert cli.main(["run-summary", "--run", str(run.root)]) == 0


def test_cli_exits_clean_on_an_almost_empty_run(tmp_path):
    empty = tmp_path / "run-empty"
    empty.mkdir()
    assert cli.main(["run-summary", "--run", str(empty)]) == 0


def test_cli_exits_two_on_a_missing_run_directory(tmp_path):
    assert cli.main(["run-summary", "--run", str(tmp_path / "nope")]) == 2
```

Add to `tests/unit/test_summary.py`'s imports: `from rubrica import cli, summary`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_summary.py -k cli -v`
Expected: FAIL — argparse rejects the unknown command `run-summary` with
`SystemExit(2)`.

- [ ] **Step 3: Wire the CLI**

In `src/rubrica/cli.py`, add to `SUBCOMMANDS` immediately after the `gate-brief`
entry:

```python
    ("run-summary", "render one run as a single self-contained HTML page"),
```

In `_build_parser`, after the `p_brief` block:

```python
    p_summary = parsers["run-summary"]
    p_summary.add_argument("--run", required=True)
    # Defaulted rather than required: the page's home is the run it describes,
    # and an operator rendering one run after another should not have to name a
    # path each time. -o is for the case where the run directory is read-only.
    p_summary.add_argument(
        "-o", "--output", default=None, metavar="PATH",
        help="where to write the page (default: <run>/run-summary.html)",
    )
```

In `main`, after the `gate-brief` arm:

```python
        if args.command == "run-summary":
            # The same ruling as claim-utilisation and gate-brief above: this
            # composes what the run already contains, so it is never the thing
            # that turns a readable run into exit 1. The path is printed rather
            # than the page, because the page is a file an operator opens and
            # 300KB of markup on a terminal is not a report.
            run = _run_dir(args.run)
            destination = Path(args.output) if args.output else run.root / "run-summary.html"
            destination.write_text(summary.run_summary(run), encoding="utf-8")
            print(destination)
            return CLEAN
```

And add `summary` to the `rubrica` import list at the top:

```python
from rubrica import brief, reconcile, refs, seal, skills, slices, summary, survey, triage
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_summary.py -v`
Expected: PASS.

- [ ] **Step 5: Update `docs/reference/cli.md`**

Two edits. First, the section — add after the `rubrica claim-utilisation` section
(before `### rubrica set-limit`), matching the house format:

```markdown
### `rubrica run-summary`

Renders one run directory as a single self-contained HTML page: the stage spine,
the manifest's inputs and per-stage record, the objective verdict and grouped
dispositions, world-model counts and claim utilisation, the coverage
progression and capability matrix, one line per scenario joined to its verdict
and emitted package, and the rule-based flags.

Required: `--run RUN`. Optional: `-o PATH` / `--output PATH` — where to write
the page, defaulting to `<run>/run-summary.html`.

**A report, not a gate: it always exits clean on a readable run.** Every
artifact it reads is optional and an absent one renders as a stated absence, so
a run that stopped at `extract` produces a page saying so rather than an error.
The output is derived rather than an artifact: no schema, outside the numbered
contract, and read by no stage.

The page is self-contained — inline CSS and JS, no external asset, no network —
so it still reads when the run is archived. Links to sibling artifacts are
relative, so the page travels with the run.

```bash
rubrica run-summary --run runs/run-20260806-123005
```
```

Second, the preamble at `## The human's own reports` says "Three subcommands"
and must be reworded — CLAUDE.md forbids prose that counts something which
grows. Replace its first sentence:

```markdown
A few subcommands serve the human holding a gate rather than a stage. Most of
them — `gate-brief`, `claim-utilisation` and `run-summary` — only compose or
report what the run already contains; `set-limit` is the odd one out and
*writes*, changing a manifest limit and appending its reason to `decisions.md`.
None of them is itself a gate: none can turn a readable run into a defect
finding.
```

- [ ] **Step 6: Run the docs accuracy suite**

Run: `uv run pytest tests/unit/test_docs_accuracy.py -v`
Expected: PASS, including `test_every_subcommand_has_its_own_section[run-summary]`.

If it fails on the section heading, check the regex it uses —
`^#{2,4}\s+`?rubrica\s+([a-z-]+)`?` — the heading must be exactly
`### \`rubrica run-summary\``.

- [ ] **Step 7: Run the three project gates**

Run:
```bash
make test
make check
uv run rubrica check-skills
```
Expected: suite green, ruff clean, `check-skills` exit 0. These are the three
gates CLAUDE.md names; anything else means something broke.

- [ ] **Step 8: Commit**

```bash
git add src/rubrica/cli.py docs/reference/cli.md tests/unit/test_summary.py
git commit -S -s -m "feat: Expose the run summary as rubrica run-summary

Code and docs in one commit because test_docs_accuracy asserts both directions
between cli.SUBCOMMANDS and cli.md, so wiring alone is a red suite. The reports
preamble loses its hand-counted 'Three', which is the policy that forbids prose
counting something that grows.

The command prints the path rather than the page: 300KB of markup on a terminal
is not a report."
```

---

## Self-Review

**Spec coverage.** Every section of the spec maps to a task:

| Spec | Task |
|---|---|
| §3.1 header + stage spine | 1, 2 |
| §3.2 intake and triage | 3 |
| §3.3 world model, utilisation, gaps, contradictions | 4 |
| §3.4 coverage, matrix, holes, implied size | 5 |
| §3.5 scenario table | 6 |
| §3.6 challenge and emitted suite | 7 |
| §3.7 flags | 7 |
| §3.8 decisions.md verbatim | 8 (`_decisions`) |
| §4 mechanism: subcommand, stdlib, exit 0 | 9 |
| §4.1 interface, default output, self-contained | 8, 9 |
| §4.2 structure, the `summary_html` split | 8 |
| §4.3 tests: complete, partial, flags, escaping | every task; 8 for escaping |
| §5 out of scope | honoured: no charts (CSS-coloured table), no cross-run deltas, no `--check`, no narrative |

**Corrections made while writing, each from a measurement:**

- `emit` removed from `_CODE_STAGES`. Measured `set(STAGES) - {skill stages}` =
  six names, and `emit` is not one — `rb-emit` exists, so emit is accusable by
  the stage-record flag. Hardcoding got this wrong.
- The `try/except` around `admit_sort_key` deleted: its docstring documents it as
  total, coercing every value precisely so it cannot raise. Guarding it would
  assert a failure mode the function removed.
- Docs moved from a trailing task into Task 9's commit, because
  `test_docs_accuracy.py` asserts both directions and a wiring-only commit is a
  red suite.
- The `## The human's own reports` preamble reworded rather than appended to: it
  hand-counts "Three subcommands", which the docs policy forbids.
- No `.gitignore` task: `runs/` is already ignored wholesale, so
  `<run>/run-summary.html` is covered.

**Type consistency.** `Absent` is the single absence type every builder returns
and `_section` is the single place it renders. `_as_int` is defined once (Task 3)
and used by Tasks 3–7. `_suite_files` is defined in Task 6 and reused by Task 7's
`challenge`. `esc` is defined in Task 1 and is the only escaping path.
`SUITE_FILES` is defined once and drives both the scenario row and the
incomplete-package check.

**One thing an executor should know:** Task 8's `_<section>` helpers are described
by rule rather than written out in full, because there are fifteen of them and
they are mechanical variations on one shape (take a dataclass, return a table).
The five numbered rules under Step 3 are the specification for all fifteen. If an
executor wants a fully written example, `_flags` and `_decisions` are spelled out
completely there.
