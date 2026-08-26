# Bounded propose/score loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every prompt-written response in the propose/score loop bounded in size, so a run whose world model has a large denominator can complete a second round instead of dying at the harness output cap having written nothing.

**Architecture:** `propose` becomes a fan-out over byte-budgeted batches of closable holes, each member writing only its own batch's scenarios into `02-scenarios/round-N/<batch>.json`; code seals those into `02-scenarios.json`. `score` keeps its barrier but writes only judgments — rulings, holes, verdict — into `03-score/round-N.json`, while code computes both coverage matrices and composes `03-coverage/round-N.json`. New code lives in one module, `src/rubrica/rounds.py`, because the loop's determinism is one concern.

**Tech Stack:** Python 3.13, `uv`, `pytest`, `ruff` (line-length 100, `select = ["E","F","I","UP","B","SIM"]`), JSON Schema draft 2020-12.

**Spec:** `docs/superpowers/specs/2026-08-26-propose-score-output-cap-design.md` — read it before Task 1. Sections 5.1, 5.2 and 6 are the design; section 2 is why the obvious smaller fix was rejected and is worth reading before proposing one.

## Global Constraints

- **Every commit signed and DCO'd: `git commit -S -s`.** Both flags. If signing fails, **stop and report it** — never fall back to unsigned, never work around it.
- Attribution trailer is exactly `Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>`. **Never** `Co-Authored-By` or `Made-with`.
- The three gates, all of which must pass before any commit: `make test` green, `make check` clean, `uv run rubrica check-skills` exit 0.
- **Never write a test count into any document.** No heading may count something that grows (stages, skills, subcommands, gates).
- Exit-code contract, load-bearing: `0` clean, `1` findings **one per line on stdout**, `2` usage error or unreadable/misconfigured run. A stage defect must never surface as `2`; a `1` must never have empty stdout; a `1` must name the *right* artifact. When touching `cli.py`, `validate.py`, `refs.py` or `paths.py`, test the unreadable-input paths (`chmod 000`, `chmod 0444`, a bad `RUBRICA_SCHEMA_DIR`), not just the happy path.
- Artifacts on disk are the only channel between stages. A fan-out member gets its own slice id and never a sibling's, never a slice's contents.
- Comment density in this repo is high and deliberate: comments explain *why*, usually citing a measurement. Match it; do not strip existing comments.
- `docs/` is excluded from ruff, so its code blocks are laid out for reading. `README.md` and `CLAUDE.md` are **not** excluded — run `make check` after editing either.
- Measured constants that this plan hard-codes, all from `runs/run-20260825-094033` on 2026-08-26: mean 1,162 bytes/scenario, max 1,579; 148 capability cells + 22 goals = 170 denominator rows; 86 `not_yet_attempted` holes of 151.

---
## File Structure

**Created:**

| Path | Responsibility |
|---|---|
| `src/rubrica/rounds.py` | The propose/score loop's code steps: hole enumeration, batch partition, scenarios assembly, matrix computation, coverage composition. One module because two runs with identical parts must produce byte-identical output, and that guarantee is one concern. |
| `src/rubrica/schema/batches-0.1.json` | `propose-batches`' output: hole refs assigned to byte-budgeted batches. |
| `src/rubrica/schema/scenarios-part-0.1.json` | One propose member's own batch of new scenarios. |
| `src/rubrica/schema/score-part-0.1.json` | One score dispatch's judgments: rulings, holes, verdict. |
| `src/rubrica/skills/rb-propose/SUPERSEDED.md` | Why the existing `exercise.md` records a stage shape that no longer exists. |
| `src/rubrica/skills/rb-score/SUPERSEDED.md` | Same, for score. |
| `tests/unit/test_rounds.py` | Every pure function in `rounds.py`. |
| `tests/unit/test_rounds_cli.py` | The three new subcommands, including the unreadable-input paths. |

**Modified:** `src/rubrica/paths.py` (accessors, `STAGES`), `src/rubrica/validate.py` (`ARTIFACT_SCHEMAS`, `STAGE_ARTIFACTS`), `src/rubrica/refs.py` (three checkers plus `check_all`), `src/rubrica/cli.py` (`SUBCOMMANDS`, parsers, handlers), `src/rubrica/schema/manifest-0.1.json` (`max_scenario_part_bytes`), `src/rubrica/skills/rb-propose/SKILL.md`, `src/rubrica/skills/rb-score/SKILL.md`, `src/rubrica/skills/rb-orchestrate/SKILL.md`, `scripts/dispatch-stage.sh`, `scripts/render-pipeline-diagram.py`, `scripts/render-readme-diagram.py`, `tests/toy.py`, `docs/concepts/pipeline.md`, `docs/reference/cli.md`, `docs/reference/artifacts.md`, `docs/design/limitations.md`, `CLAUDE.md`.

**Why `rounds.py` and not an extension of an existing module:** `slices.py` owns the triage partition, `seal.py` the triage seal, `reconcile.py` the reconcile seal. A fourth module for the loop's own code steps follows that grain. Do not add these functions to `refs.py` — that module checks, and `check_coverage` must keep reporting against whatever it is handed, including a coverage document this seal never composed.

---

### Task 1: Path accessors for the new artifacts

No behaviour yet — just the paths, so every later task has one place to get them. `paths.STAGES` is **not** touched here; it moves in Task 8 with the docs and the fixture that must move with it.

**Files:**
- Modify: `src/rubrica/paths.py`
- Test: `tests/unit/test_paths.py`

**Interfaces:**
- Consumes: nothing.
- Produces: on `RunPaths` — `batches: Path`, `scenario_parts_dir: Path`, `scenario_round_dir(round_n: int) -> Path`, `scenario_part(round_n: int, batch_id: str) -> Path`, `score_parts_dir: Path`, `score_part(round_n: int) -> Path`, `score_part_rounds() -> list[int]`, `scenario_part_rounds() -> list[int]`, `scenario_part_batch_ids(round_n: int) -> list[str]`, `unsafe_scenario_part_names(round_n: int) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_paths.py`:

```python
def test_new_round_artifact_paths(tmp_path):
    run = RunPaths(tmp_path)
    assert run.batches == tmp_path / "02-batches.json"
    assert run.scenario_parts_dir == tmp_path / "02-scenarios"
    assert run.scenario_round_dir(1) == tmp_path / "02-scenarios" / "round-1"
    assert run.scenario_part(2, "b01") == tmp_path / "02-scenarios" / "round-2" / "b01.json"
    assert run.score_parts_dir == tmp_path / "03-score"
    assert run.score_part(3) == tmp_path / "03-score" / "round-3.json"


def test_score_part_rounds_reads_what_is_on_disk(tmp_path):
    run = RunPaths(tmp_path)
    run.score_parts_dir.mkdir()
    for name in ("round-1.json", "round-10.json", "round-2.json", "notes.json"):
        (run.score_parts_dir / name).write_text("{}", encoding="utf-8")
    # Numeric, so round-10 does not sort between round-1 and round-2, and a file
    # that is not a round is ignored rather than crashing the seal.
    assert run.score_part_rounds() == [1, 2, 10]


def test_round_numbers_must_be_positive(tmp_path):
    run = RunPaths(tmp_path)
    # Mirrors coverage_round's guard: a round of 0 or -1 is a caller bug, and a
    # path built from one would silently address a directory nobody writes.
    for bad in (0, -1):
        with pytest.raises(ValueError):
            run.scenario_round_dir(bad)
        with pytest.raises(ValueError):
            run.score_part(bad)


def test_scenario_part_rejects_an_unsafe_batch_id(tmp_path):
    run = RunPaths(tmp_path)
    # Batch ids are code-minted, but this joins the same way disposition_part
    # does and the guard is what stops an artifact-sourced id escaping the run.
    with pytest.raises(UnsafeSegment):
        run.scenario_part(1, "../../etc/passwd")


def test_part_listings_are_empty_when_nothing_exists(tmp_path):
    run = RunPaths(tmp_path)
    assert run.scenario_part_rounds() == []
    assert run.scenario_part_batch_ids(1) == []


def test_part_listings_read_what_is_on_disk(tmp_path):
    run = RunPaths(tmp_path)
    for round_n, batch in ((1, "b01"), (1, "b02"), (2, "b01")):
        part = run.scenario_part(round_n, batch)
        part.parent.mkdir(parents=True, exist_ok=True)
        part.write_text("{}", encoding="utf-8")
    assert run.scenario_part_rounds() == [1, 2]
    assert run.scenario_part_batch_ids(1) == ["b01", "b02"]
    assert run.scenario_part_batch_ids(2) == ["b01"]


def test_unsafe_scenario_part_names_are_listed_not_raised(tmp_path):
    run = RunPaths(tmp_path)
    # Same split unsafe_contradiction_part_names exists for: the id-listing
    # accessor must not raise, because returning an unsafe id made the later
    # scenario_part() call raise at a call site that cannot handle it.
    d = run.scenario_round_dir(1)
    d.mkdir(parents=True)
    (d / "b01.json").write_text("{}", encoding="utf-8")
    (d / "..bad.json").write_text("{}", encoding="utf-8")
    assert run.scenario_part_batch_ids(1) == ["b01"]
    assert run.unsafe_scenario_part_names(1) == ["..bad"]
```

Check the imports already at the top of that module and add `UnsafeSegment` / `pytest` only if absent.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_paths.py -k "round_artifact or round_numbers or scenario_part or part_listings or unsafe_scenario" -v`
Expected: FAIL, `AttributeError: 'RunPaths' object has no attribute 'batches'`.

- [ ] **Step 3: Implement the accessors**

In `src/rubrica/paths.py`, immediately after the existing `scenarios` property, add:

```python
    @property
    def batches(self) -> Path:
        return self.root / "02-batches.json"

    @property
    def scenario_parts_dir(self) -> Path:
        return self.root / "02-scenarios"

    def scenario_round_dir(self, round_n: int) -> Path:
        if round_n < 1:
            raise ValueError(f"round must be >= 1, got {round_n}")
        return self.scenario_parts_dir / f"round-{round_n}"

    def scenario_part(self, round_n: int, batch_id: str) -> Path:
        return self.scenario_round_dir(round_n) / f"{safe_segment(batch_id)}.json"

    def scenario_part_rounds(self) -> list[int]:
        """Every round number that has a part directory, ascending.

        Sorted numerically rather than lexically: round-10 must not sort between
        round-1 and round-2, which is exactly what sorted() on the stem does.
        """
        rounds: list[int] = []
        for entry in list_dir(self.scenario_parts_dir):
            if not entry.is_dir() or not entry.name.startswith("round-"):
                continue
            suffix = entry.name[len("round-") :]
            if suffix.isdigit():
                rounds.append(int(suffix))
        return sorted(rounds)

    def _scenario_part_stems(self, round_n: int) -> list[str]:
        return [p.stem for p in list_json(self.scenario_round_dir(round_n))]

    def scenario_part_batch_ids(self, round_n: int) -> list[str]:
        """The safe batch ids with a part in this round, sorted."""
        return sorted(s for s in self._scenario_part_stems(round_n) if is_safe_segment(s))

    def unsafe_scenario_part_names(self, round_n: int) -> list[str]:
        """Part stems this package refuses to join into a path.

        Split from scenario_part_batch_ids for the reason
        unsafe_contradiction_part_names is split from subject_part_ids: an
        id-listing accessor that raised made the failure surface at a call site
        with no way to report it, and these belong in a finding instead.
        """
        return sorted(s for s in self._scenario_part_stems(round_n) if not is_safe_segment(s))

    @property
    def score_parts_dir(self) -> Path:
        return self.root / "03-score"

    def score_part(self, round_n: int) -> Path:
        if round_n < 1:
            raise ValueError(f"round must be >= 1, got {round_n}")
        return self.score_parts_dir / f"round-{round_n}.json"

    def score_part_rounds(self) -> list[int]:
        """Every round number that has a score part, ascending.

        Sorted numerically for the reason scenario_part_rounds is, and a file
        whose stem is not round-<digits> is ignored rather than raising: this is
        the accessor the seal iterates, and a stray file in the directory must
        not be able to stop a round from being assembled.
        """
        rounds: list[int] = []
        for path in list_json(self.score_parts_dir):
            stem = path.stem
            if stem.startswith("round-") and stem[len("round-") :].isdigit():
                rounds.append(int(stem[len("round-") :]))
        return sorted(rounds)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_paths.py -v`
Expected: PASS. Then `make test` and `make check` — both must be green before the commit.

- [ ] **Step 5: Commit**

```bash
git add src/rubrica/paths.py tests/unit/test_paths.py
git commit -S -s -m "feat: Add path accessors for the round parts and batches

Paths only, no behaviour and no STAGES change: the stage list moves with the
docs and the toy fixture that must move with it, so this lands first and alone.

scenario_part_rounds sorts numerically because round-10 sorts between round-1
and round-2 lexically, and the unsafe-name listing is split from the id listing
for the reason unsafe_contradiction_part_names already is -- an accessor that
raises surfaces the failure where nothing can report it.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---
### Task 2: The three schemas, the artifact kinds, and the byte-budget limit

**Files:**
- Create: `src/rubrica/schema/batches-0.1.json`, `src/rubrica/schema/scenarios-part-0.1.json`, `src/rubrica/schema/score-part-0.1.json`
- Modify: `src/rubrica/validate.py` (`ARTIFACT_SCHEMAS` only — `STAGE_ARTIFACTS` waits for Task 8), `src/rubrica/schema/manifest-0.1.json`, `src/rubrica/manifest.py`, `src/rubrica/cli.py` (the `set-limit` flag), `docs/reference/artifacts.md`
- Test: `tests/unit/test_validate.py`, `tests/unit/test_manifest.py`

**Interfaces:**
- Consumes: nothing.
- Produces: artifact kinds `batches`, `scenarios-part`, `score-part` resolvable through `validate.ARTIFACT_SCHEMAS`; `manifest.set_limit(..., max_scenario_part_bytes: int | None = None, ...)`; optional manifest key `limits.max_scenario_part_bytes`.

**Deliberate deviation from the spec, recorded here rather than silently taken:** spec section 7 lists `refs.check_limits` as gaining `max_scenario_part_bytes`. It does not, and should not. `check_limits` exists to catch a run that *exceeded* a bound — a scenario tagged past `max_rounds`, more open scenarios than `max_scenarios`. This limit is not a bound on the run's content but a budget the partition packs against, and whether the partition honoured it is exactly what `check_batches` recomputes in Task 7 (`test_check_batches_reports_a_batch_over_its_own_cap`). Putting it in both places would be two checkers for one property, and `check_limits` would have nothing of its own to compare against.

**Why the limit is optional rather than required:** `limits` is `additionalProperties: false` with `max_rounds` and `max_scenarios` required. Making a third key required would make every manifest already on disk under `runs/` schema-invalid, and `diff-runs`, `run-summary` and `gate-brief` all read those. Optional, with `rounds.DEFAULT_SCENARIO_PART_BYTES` applied when absent, keeps old runs readable while still letting `set-limit` put a change on the record.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_validate.py`:

```python
@pytest.mark.parametrize("kind", ["batches", "scenarios-part", "score-part"])
def test_the_new_round_kinds_resolve_to_a_shipped_schema(kind):
    assert kind in ARTIFACT_SCHEMAS
    assert (schema_dir() / ARTIFACT_SCHEMAS[kind]).is_file()


def test_a_batches_document_validates(tmp_path):
    doc = {
        "schema_version": "0.1",
        "round": 1,
        "cap_bytes": 28000,
        "bytes_per_scenario": 1600,
        "batches": [
            {"id": "b01", "hole_refs": ["cell:cap-a/oc-success"], "projected_bytes": 1600},
        ],
    }
    assert validate_doc(doc, "batches") == []


def test_a_batches_document_with_no_batches_is_refused():
    # Zero batches means nothing to dispatch. propose-batches writes no
    # document at all when there are no closable holes, so a batches file that
    # exists and is empty is a partition defect rather than a quiet round.
    doc = {
        "schema_version": "0.1", "round": 1, "cap_bytes": 28000,
        "bytes_per_scenario": 1600, "batches": [],
    }
    assert validate_doc(doc, "batches") != []


def test_a_scenarios_part_validates_and_carries_its_own_batch_id(tmp_path):
    doc = {
        "schema_version": "0.1",
        "round": 1,
        "batch_id": "b01",
        "scenarios": [],
    }
    # An empty array is a real record: this member swept its batch and closed
    # nothing, the same reading contradictions-part-0.1.json gives its own.
    assert validate_doc(doc, "scenarios-part") == []


def test_a_score_part_validates(tmp_path):
    doc = {
        "schema_version": "0.1",
        "round": 1,
        "rulings": [{"scenario_id": "sc-b01-001", "status": "active"}],
        "holes": [],
        "verdict": "converged",
    }
    assert validate_doc(doc, "score-part") == []


def test_a_fold_ruling_must_name_its_survivor():
    doc = {
        "schema_version": "0.1", "round": 1, "holes": [], "verdict": "converged",
        "rulings": [{"scenario_id": "sc-b01-002", "status": "duplicate"}],
    }
    assert validate_doc(doc, "score-part") != []


def test_a_rejection_ruling_must_name_a_reason():
    doc = {
        "schema_version": "0.1", "round": 1, "holes": [], "verdict": "converged",
        "rulings": [{"scenario_id": "sc-b01-002", "status": "rejected"}],
    }
    assert validate_doc(doc, "score-part") != []
```

Use whatever helper this module already uses to validate a document against a kind; if it validates through a file, write `doc` to `tmp_path` first and pass the path. Add `ARTIFACT_SCHEMAS` / `schema_dir` to the imports if absent.

Append to `tests/unit/test_manifest.py`:

```python
def test_set_limit_records_the_part_byte_budget(tmp_path):
    run = build_toy_run(tmp_path, upto="intake")
    set_limit(run, max_scenario_part_bytes=12000, reason="probe run, small batches")
    manifest = read_json(run.manifest)
    assert manifest["limits"]["max_scenario_part_bytes"] == 12000
    assert "12000" in run.decisions.read_text(encoding="utf-8")


def test_set_limit_still_refuses_a_call_with_no_limit(tmp_path):
    run = build_toy_run(tmp_path, upto="intake")
    with pytest.raises(UsageError):
        set_limit(run, reason="nothing to change")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_validate.py -k "round_kinds or batches_document or scenarios_part or score_part or fold_ruling or rejection_ruling" tests/unit/test_manifest.py -k part_byte -v`
Expected: FAIL — `KeyError: 'batches'` and `TypeError: set_limit() got an unexpected keyword argument`.

- [ ] **Step 3: Write the three schemas**

`src/rubrica/schema/batches-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "batches-0.1.json",
  "title": "One round's propose batches",
  "description": "propose-batches' (code) output: the closable holes of this round, partitioned into batches whose projected output keeps one rb-propose dispatch inside the harness output cap. A batch is a writing unit, not a decision unit -- every closable hole reaches a member, and which holes are closable is rb-score's ruling, not this partition's. Measured on run-20260825-094033: 86 closable holes at a 1,162-byte mean scenario would have been ~124KB in one response against a 32,000-token cap.",
  "type": "object",
  "required": ["schema_version", "round", "cap_bytes", "bytes_per_scenario", "batches"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {"const": "0.1"},
    "round": {"type": "integer", "minimum": 1},
    "cap_bytes": {
      "type": "integer",
      "minimum": 1,
      "description": "The per-member output budget every batch was packed against. Echoed here, as slices-0.1.json echoes its own cap, so a reader auditing one batch's projection against the budget need not open the manifest."
    },
    "bytes_per_scenario": {
      "type": "integer",
      "minimum": 1,
      "description": "The estimate the projection used: rounds.DEFAULT_BYTES_PER_SCENARIO until a sealed 02-scenarios.json exists, and the mean over that file thereafter. Recorded because it is the term that makes the partition self-calibrating, and a reader comparing two rounds' batch sizes needs it to tell a changed estimate from a changed hole count."
    },
    "batches": {
      "type": "array",
      "minItems": 1,
      "description": "At least one: propose-batches writes no document at all when no hole is closable, so an empty array here is a partition defect rather than a round with nothing to do.",
      "items": {
        "type": "object",
        "required": ["id", "hole_refs", "projected_bytes"],
        "additionalProperties": false,
        "properties": {
          "id": {
            "$ref": "world-model-0.1.json#/$defs/id",
            "description": "Code-minted (b01, b02, ...), short and stable, because it is a path segment: 02-scenarios/round-N/<id>.json joins it through safe_segment, and it prefixes the scenario ids the member mints so two members cannot collide."
          },
          "hole_refs": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "coverage-0.1.json#/$defs/hole_ref"},
            "description": "The holes this batch owns, in the same cell:/goal: vocabulary the coverage report uses. A batch with none would give its member nothing to close, so this floor mirrors the outer array's."
          },
          "projected_bytes": {
            "type": "integer",
            "minimum": 0,
            "description": "hole_refs length times bytes_per_scenario. refs.check_batches recomputes it, so a batch cannot drift from its own header."
          }
        }
      }
    }
  }
}
```

`src/rubrica/schema/scenarios-part-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "scenarios-part-0.1.json",
  "title": "One propose member's batch of new scenarios",
  "description": "What one rb-propose fan-out member wrote for its own batch, and nothing else. An empty scenarios array is a real record -- it says this member read its batch and could close none of it, which is what refusal conditions exist to produce -- so the array has no minItems, and refs.check_scenario_parts requires a file per batch rather than a non-empty one. The member never re-emits a sibling's scenarios or an earlier round's: propose-seal assembles 02-scenarios.json from every part, which is why this part is bounded while that document is not.",
  "type": "object",
  "required": ["schema_version", "round", "batch_id", "scenarios"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {"const": "0.1"},
    "round": {"type": "integer", "minimum": 1},
    "batch_id": {"$ref": "world-model-0.1.json#/$defs/id"},
    "scenarios": {
      "type": "array",
      "items": {"$ref": "scenarios-0.1.json#/$defs/scenario"}
    }
  }
}
```

`src/rubrica/schema/score-part-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "score-part-0.1.json",
  "title": "One score dispatch's judgments",
  "description": "Everything rb-score decides and nothing it can compute. The coverage matrices are absent on purpose: rb-score's own Method specifies both as pure functions of the world model and the scenario list, and refs.py already recomputes them in checker form, so score-seal computes them and this part carries only the folds, the rejections, the hole reasons and the verdict. Measured on run-20260825-094033: this replaces a 24,613-byte scenarios re-emit and a 61,342-byte coverage document written twice.",
  "type": "object",
  "required": ["schema_version", "round", "rulings", "holes", "verdict"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {"const": "0.1"},
    "round": {"type": "integer", "minimum": 1},
    "rulings": {
      "type": "array",
      "description": "One entry per scenario whose status changes in this round. A scenario absent from every round's rulings keeps the status its propose member gave it, which is `proposed`. An empty array is a real record: it says score promoted nothing and folded nothing.",
      "items": {
        "type": "object",
        "required": ["scenario_id", "status"],
        "additionalProperties": false,
        "properties": {
          "scenario_id": {"$ref": "world-model-0.1.json#/$defs/id"},
          "status": {"enum": ["active", "duplicate", "rejected"]},
          "duplicate_of": {"$ref": "world-model-0.1.json#/$defs/id"},
          "rejected_reason": {
            "enum": ["ambiguous", "not_derivable", "wrong_label", "out_of_scope", "blocked_by_gap"]
          }
        },
        "allOf": [
          {
            "if": {"properties": {"status": {"const": "duplicate"}}, "required": ["status"]},
            "then": {"required": ["duplicate_of"]}
          },
          {
            "if": {"properties": {"status": {"const": "rejected"}}, "required": ["status"]},
            "then": {"required": ["rejected_reason"]}
          }
        ]
      }
    },
    "holes": {
      "type": "array",
      "items": {"$ref": "coverage-0.1.json#/$defs/hole"},
      "description": "One entry per uncovered row, carrying the reason and justification that are judgment and cannot be computed. score-seal refuses to compose a coverage document if an uncovered row has no hole here, or a hole here names a row the computed matrices show as covered -- the both-directions check refs.check_coverage already makes after the fact."
    },
    "verdict": {"$ref": "coverage-0.1.json#/properties/verdict"}
  }
}
```

`status` deliberately omits `proposed`: a ruling exists to change a status, and `proposed` is what a scenario already carries out of its propose member, so a ruling naming it would be a no-op that still had to be honoured. `scenarios-0.1.json` already exposes the scenario object as `$defs/scenario` (verified 2026-08-26 — its `$defs` are `id`, `hole_ref`, `scenario`, and `properties/scenarios/items` is already a `$ref` to it), so `scenarios-part` `$ref`s it with no change to that file. Do not copy the scenario object: a second definition is how a field drifts between the part and the sealed document.

- [ ] **Step 4: Register the kinds and the limit**

In `src/rubrica/validate.py`, add to `ARTIFACT_SCHEMAS` after the reconcile partials block:

```python
    # The propose/score loop's part kinds. Each is one dispatch's slice of a
    # document that used to be emitted whole by a model, and every one of them
    # $refs scenarios-0.1.json's or coverage-0.1.json's $defs rather than
    # restating a scenario, a ruling or a hole.
    "batches": "batches-0.1.json",
    "scenarios-part": "scenarios-part-0.1.json",
    "score-part": "score-part-0.1.json",
```

In `src/rubrica/schema/manifest-0.1.json`, add to `limits.properties` (leaving `required` untouched):

```json
    "max_scenario_part_bytes": {
      "type": "integer",
      "minimum": 1,
      "description": "Per-member output budget propose-batches packs against. Optional rather than required: making a third limit required would invalidate every manifest already on disk, which diff-runs, run-summary and gate-brief all read. Absent means rounds.DEFAULT_SCENARIO_PART_BYTES."
    }
```

In `src/rubrica/manifest.py`, add the parameter to `set_limit` — a third `max_scenario_part_bytes: int | None = None` keyword, folded into the existing no-op guard and the existing decisions.md line so all three limits are handled by one code path:

```python
    if max_rounds is None and max_scenarios is None and max_scenario_part_bytes is None:
        raise UsageError(
            "set_limit needs at least one of max_rounds, max_scenarios "
            "or max_scenario_part_bytes"
        )
```

Follow the function's existing shape for applying and recording each limit; add the third alongside the two, rather than special-casing it.

In `src/rubrica/cli.py`, beside the existing two flags:

```python
    p_set_limit.add_argument("--max-scenario-part-bytes", type=int, default=None)
```

and pass `max_scenario_part_bytes=args.max_scenario_part_bytes` through the existing `set_limit(...)` call.

- [ ] **Step 5: Document the kinds**

`docs/reference/artifacts.md` must name each new kind as `batches`, `scenarios-part` and `score-part` — `tests/unit/test_docs_accuracy.py` fails until it does. Give each a short entry saying what writes it, what reads it, and the one-line reason it exists: the part kinds exist so no prompt writes a document that grows with the world model's denominator.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_validate.py tests/unit/test_manifest.py tests/unit/test_docs_accuracy.py -v`
Expected: PASS. Then `make test` and `make check`.

- [ ] **Step 7: Commit**

```bash
git add src/rubrica/schema/ src/rubrica/validate.py src/rubrica/manifest.py src/rubrica/cli.py \
        docs/reference/artifacts.md tests/unit/test_validate.py tests/unit/test_manifest.py
git commit -S -s -m "feat: Add the batches, scenarios-part and score-part kinds

Three part kinds for the propose/score loop, each \$refing scenarios-0.1.json's
or coverage-0.1.json's \$defs rather than restating a scenario, a ruling or a
hole, as the triage and reconcile part schemas already do.

score-part carries no matrices: rb-score's Method already specifies both as
pure functions of the world model and the scenario list, and refs.py recomputes
them in checker form, so the part holds only what is judgment.

max_scenario_part_bytes is optional, not required -- a third required limit
would invalidate every manifest already under runs/, which diff-runs,
run-summary and gate-brief all read.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---
### Task 3: `rounds.py` — closable holes and the batch partition

**Files:**
- Create: `src/rubrica/rounds.py`
- Test: `tests/unit/test_rounds.py`

**Interfaces:**
- Consumes: `RunPaths` accessors from Task 1; artifact kinds from Task 2.
- Produces: `DEFAULT_BYTES_PER_SCENARIO: int`, `DEFAULT_SCENARIO_PART_BYTES: int`, `closable_holes(run: RunPaths) -> list[str]`, `bytes_per_scenario(run: RunPaths) -> int`, `partition(refs: list[str], *, cap_bytes: int, per_scenario: int) -> list[list[str]]`, `write_batches(run: RunPaths, *, round_n: int) -> Path | None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_rounds.py`:

```python
"""The propose/score loop's code steps.

Every number asserted here that is not obviously arithmetic came off
runs/run-20260825-094033 on 2026-08-26: 148 capability cells plus 22 goals,
86 closable holes of 151, mean 1,162 bytes per scenario and max 1,579.
"""

from __future__ import annotations

import json

import pytest

from rubrica import rounds
from rubrica.artifacts import read_json, write_json
from rubrica.errors import UsageError
from rubrica.paths import RunPaths


def _world(caps: int = 2, ocs: int = 2, goals: int = 1) -> dict:
    return {
        "schema_version": "0.1",
        "denominator": {"capability_cells": caps * ocs, "goals": goals, "version": 1},
        "capabilities": [
            {
                "id": f"cap-{c}",
                "outcome_classes": [{"id": f"cap-{c}-oc-{o}"} for o in range(ocs)],
            }
            for c in range(caps)
        ],
        "goals": [
            {"id": f"goal-{g}", "expected_hop_depths": [1]} for g in range(goals)
        ],
    }


def _run_with_world(tmp_path, world: dict) -> RunPaths:
    run = RunPaths(tmp_path)
    write_json(run.world_model, world)
    return run


def test_round_one_treats_every_cell_and_goal_as_open(tmp_path):
    # No coverage report exists in round 1, which is the normal shape rather
    # than a missing file: rb-propose's own Inputs section says to treat every
    # cell and goal as open, and the partition has to build the same worklist.
    run = _run_with_world(tmp_path, _world(caps=2, ocs=2, goals=1))
    assert rounds.closable_holes(run) == [
        "cell:cap-0/cap-0-oc-0",
        "cell:cap-0/cap-0-oc-1",
        "cell:cap-1/cap-1-oc-0",
        "cell:cap-1/cap-1-oc-1",
        "goal:goal-0",
    ]


def test_later_rounds_take_only_the_not_yet_attempted_holes(tmp_path):
    # The other three reasons are not closable by proposing, whatever the
    # scenario: unreachable and out_of_scope are outside the suite's surface,
    # and blocked_by_gap needs an earlier stage's gap resolved first.
    run = _run_with_world(tmp_path, _world())
    write_json(
        run.coverage_latest,
        {
            "schema_version": "0.1", "round": 1, "denominator_version": 1,
            "capability_matrix": {"cells": [], "covered": 0, "total": 0, "pct": 0.0},
            "goal_matrix": {"rows": [], "covered": 0, "total": 0, "pct": 0.0},
            "progress": {"new_cells_this_round": 0, "rounds_without_progress": 0},
            "verdict": "continue",
            "holes": [
                {"ref": "cell:cap-0/cap-0-oc-0", "reason": "not_yet_attempted", "justification": "x"},
                {"ref": "goal:goal-0", "reason": "not_yet_attempted", "justification": "x"},
                {"ref": "cell:cap-1/cap-1-oc-0", "reason": "unreachable", "justification": "x"},
                {"ref": "cell:cap-1/cap-1-oc-1", "reason": "out_of_scope", "justification": "x"},
                {"ref": "cell:cap-0/cap-0-oc-1", "reason": "blocked_by_gap",
                 "gap_id": "gap-1", "justification": "x"},
            ],
        },
    )
    assert rounds.closable_holes(run) == ["cell:cap-0/cap-0-oc-0", "goal:goal-0"]


def test_the_scenario_byte_estimate_falls_back_before_any_round_lands(tmp_path):
    run = _run_with_world(tmp_path, _world())
    assert rounds.bytes_per_scenario(run) == rounds.DEFAULT_BYTES_PER_SCENARIO


def test_the_scenario_byte_estimate_self_calibrates_from_the_sealed_file(tmp_path):
    run = _run_with_world(tmp_path, _world())
    small = {"id": "sc-b01-001", "round": 1, "title": "a"}
    write_json(run.scenarios, {"schema_version": "0.1", "denominator_version": 1,
                               "scenarios": [small, small]})
    expected = len(json.dumps(small, sort_keys=True))
    assert rounds.bytes_per_scenario(run) == expected


def test_an_empty_sealed_file_falls_back_rather_than_dividing_by_zero(tmp_path):
    run = _run_with_world(tmp_path, _world())
    write_json(run.scenarios, {"schema_version": "0.1", "denominator_version": 1,
                               "scenarios": []})
    assert rounds.bytes_per_scenario(run) == rounds.DEFAULT_BYTES_PER_SCENARIO


def test_the_partition_keeps_every_batch_inside_the_budget():
    refs = [f"cell:cap-{i}/oc" for i in range(86)]
    batches = rounds.partition(refs, cap_bytes=28000, per_scenario=1600)
    # 28000 // 1600 == 17 holes per batch, so 86 holes become 6 batches -- the
    # measured case from run-20260825-094033.
    assert len(batches) == 6
    assert [len(b) for b in batches] == [17, 17, 17, 17, 17, 1]
    for batch in batches:
        assert len(batch) * 1600 <= 28000
    # No hole is dropped and none is duplicated: the partition is a partition.
    assert [ref for batch in batches for ref in batch] == refs


def test_the_partition_of_nothing_is_nothing():
    assert rounds.partition([], cap_bytes=28000, per_scenario=1600) == []


def test_a_budget_smaller_than_one_scenario_is_a_usage_error():
    # max(1, cap // per) would silently produce a batch that cannot fit, which
    # is the silent cap this whole change exists to remove. Refuse instead.
    with pytest.raises(UsageError):
        rounds.partition(["cell:a/b"], cap_bytes=100, per_scenario=1600)


def test_write_batches_writes_a_schema_valid_document(tmp_path):
    run = _run_with_world(tmp_path, _world(caps=2, ocs=2, goals=1))
    path = rounds.write_batches(run, round_n=1)
    assert path == run.batches
    doc = read_json(path)
    assert doc["round"] == 1
    assert doc["cap_bytes"] == rounds.DEFAULT_SCENARIO_PART_BYTES
    assert doc["bytes_per_scenario"] == rounds.DEFAULT_BYTES_PER_SCENARIO
    assert [b["id"] for b in doc["batches"]] == ["b01"]
    assert doc["batches"][0]["hole_refs"] == rounds.closable_holes(run)
    assert doc["batches"][0]["projected_bytes"] == 5 * rounds.DEFAULT_BYTES_PER_SCENARIO


def test_write_batches_honours_the_manifest_budget(tmp_path):
    run = _run_with_world(tmp_path, _world(caps=4, ocs=4, goals=4))
    write_json(run.manifest, {"limits": {"max_rounds": 2, "max_scenarios": 128,
                                         "max_scenario_part_bytes": 3200}})
    doc = read_json(rounds.write_batches(run, round_n=1))
    assert doc["cap_bytes"] == 3200
    # 3200 // 1600 == 2 holes per batch over 20 holes -> 10 batches, zero-padded
    # ids so b10 sorts after b09 as a path segment and in any listing.
    assert [b["id"] for b in doc["batches"]] == [f"b{i:02d}" for i in range(1, 11)]


def test_write_batches_writes_nothing_when_no_hole_is_closable(tmp_path):
    # Distinct from an empty batches array, which the schema refuses: no
    # document at all is how the orchestrator learns there is no round to run.
    run = _run_with_world(tmp_path, {"schema_version": "0.1", "capabilities": [],
                                     "goals": [],
                                     "denominator": {"capability_cells": 0, "goals": 0,
                                                     "version": 1}})
    assert rounds.write_batches(run, round_n=1) is None
    assert not run.batches.exists()


def test_write_batches_reports_an_unreadable_world_model(tmp_path):
    run = RunPaths(tmp_path)
    with pytest.raises(Exception):
        rounds.write_batches(run, round_n=1)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_rounds.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'rubrica.rounds'`.

- [ ] **Step 3: Write the module**

Create `src/rubrica/rounds.py`:

```python
"""The propose/score loop's code steps.

Code rather than a prompt for the reason emit and both existing seals are code:
two runs with identical parts must produce a byte-identical result, or variance
stops being attributable to the stage that caused it. There is a second reason
specific to this loop, and it is the defect this module exists to close.

MEASURED, run-20260825-094033 (executive-agent, 5 files, sonnet/medium): round
1 proposed 18 scenarios into a 24,613-byte 02-scenarios.json and rb-score
returned verdict `continue`. Round 2 then had to emit round 1's scenarios
verbatim plus one new scenario per closable hole, of which the coverage report
listed 86. At the file's own 1,162-byte mean that is ~124,545 bytes in one
response against a 32,000-output-token cap: the dispatch spent $3.57 over 31
minutes and wrote nothing at all.

The term that binds is NOT the accumulated re-emit, which was 24,613 of those
bytes -- 20%. It is the round's own batch, sized by the closable-hole count,
which is why this module partitions holes rather than merely dropping the
re-emit. The comparison run 20260823-112746 cleared round 2 with 4 closable
holes and a round-1 file only 1.4x smaller; the hole counts differ by 21.5x.

So a batch is a *writing* unit, exactly as a triage slice is a *reading* unit,
and the same thing makes it acceptable: nothing here decides anything. Every
closable hole reaches a member, which holes are closable is rb-score's ruling
and not this partition's, and a human at gate 2 still sees the whole coverage
matrix. What this bounds is how much one response has to contain.
"""

from __future__ import annotations

import json

from rubrica.artifacts import read_json, write_json
from rubrica.errors import UsageError
from rubrica.paths import RunPaths

# The measured maximum scenario on run-20260825-094033 was 1,579 serialized
# bytes against a 1,162 mean. The estimate rounds up to the max rather than the
# mean, because a projection that under-estimates produces exactly the failure
# this module exists to prevent, and one that over-estimates only produces one
# more batch than strictly needed.
DEFAULT_BYTES_PER_SCENARIO = 1600

# Per-member output budget, ~8k output tokens at ~3.5 bytes/token. Chosen well
# under the 32,000 that killed round 2 rather than just under it: the cap counts
# thinking tokens too, and a member also emits its report back to the
# orchestrator, so the write is not the whole response. At this budget the
# measured 86 closable holes become 6 batches.
DEFAULT_SCENARIO_PART_BYTES = 28000


def _live_statuses() -> tuple[str, ...]:
    """Statuses that still count toward coverage: a test may yet ship for them."""
    return ("proposed", "active")


def closable_holes(run: RunPaths) -> list[str]:
    """The hole refs a new scenario could close this round, sorted.

    Round 1 has no coverage report, and that is the normal shape rather than a
    missing file -- rb-propose's Inputs section says so outright -- so every
    capability x outcome-class cell and every goal is open by default and the
    worklist is enumerated from the world model.

    From round 2 the report's holes are the worklist, filtered to
    `not_yet_attempted`. The other three reasons are not closable by proposing,
    however good the scenario: `unreachable` and `out_of_scope` are cells the
    suite is not trying to cover, and `blocked_by_gap` means the world model
    does not yet support a scenario there, so proposing anyway produces one
    rb-instantiate cannot honestly seed.
    """
    world = read_json(run.world_model)
    if not run.coverage_latest.exists():
        refs = [
            f"cell:{cap['id']}/{oc['id']}"
            for cap in world.get("capabilities", [])
            for oc in cap.get("outcome_classes", [])
        ]
        refs += [f"goal:{goal['id']}" for goal in world.get("goals", [])]
        return sorted(refs)
    coverage = read_json(run.coverage_latest)
    return sorted(
        hole["ref"]
        for hole in coverage.get("holes", [])
        if hole.get("reason") == "not_yet_attempted"
    )


def bytes_per_scenario(run: RunPaths) -> int:
    """Mean serialized bytes of the scenarios already sealed, else the default.

    Self-calibrating on purpose: the estimate is the one term in the projection
    that depends on the target rather than on the partition, and a run whose
    scenarios are wordier than the fixture's would otherwise be under-estimated
    every round. Falls back on a missing or empty file rather than dividing by
    zero -- round 1 has neither.
    """
    if not run.scenarios.exists():
        return DEFAULT_BYTES_PER_SCENARIO
    scenarios = read_json(run.scenarios).get("scenarios", [])
    if not scenarios:
        return DEFAULT_BYTES_PER_SCENARIO
    total = sum(len(json.dumps(s, sort_keys=True)) for s in scenarios)
    return max(1, total // len(scenarios))


def partition(refs: list[str], *, cap_bytes: int, per_scenario: int) -> list[list[str]]:
    """Chunk hole refs so each batch's projected output stays inside cap_bytes.

    Adjacent chunks in the order given, not a size-packing: every hole projects
    to the same estimate, so there is nothing for a packer to optimise, and the
    sorted order keeps a capability's cells together where a packer would
    scatter them.

    A budget smaller than one scenario is refused rather than clamped. Clamping
    to one hole per batch would emit a batch that cannot fit its own projection
    -- a cap that does not bind, silently, which is the whole defect class this
    module closes.
    """
    if cap_bytes < per_scenario:
        raise UsageError(
            f"max_scenario_part_bytes={cap_bytes} is below the {per_scenario}-byte "
            "estimate for a single scenario, so no batch could fit one"
        )
    per_batch = cap_bytes // per_scenario
    return [refs[i : i + per_batch] for i in range(0, len(refs), per_batch)]


def _cap_bytes(run: RunPaths) -> int:
    """The manifest's per-member budget, or the default when it carries none.

    Absent rather than required in manifest-0.1.json: a third required limit
    would invalidate every manifest already on disk under runs/.
    """
    if not run.manifest.exists():
        return DEFAULT_SCENARIO_PART_BYTES
    limits = read_json(run.manifest).get("limits", {})
    return limits.get("max_scenario_part_bytes", DEFAULT_SCENARIO_PART_BYTES)


def write_batches(run: RunPaths, *, round_n: int) -> Path | None:
    """Partition this round's closable holes into 02-batches.json.

    Returns None and writes nothing when no hole is closable. That is different
    from writing an empty batches array, which batches-0.1.json refuses: no
    document at all is how the orchestrator learns there is no round to run,
    whereas an empty array would be a partition that lost its own worklist.
    """
    refs = closable_holes(run)
    if not refs:
        return None
    per_scenario = bytes_per_scenario(run)
    cap = _cap_bytes(run)
    batches = partition(refs, cap_bytes=cap, per_scenario=per_scenario)
    write_json(
        run.batches,
        {
            "schema_version": "0.1",
            "round": round_n,
            "cap_bytes": cap,
            "bytes_per_scenario": per_scenario,
            # Zero-padded so b10 sorts after b09 both as a path segment and in
            # any listing -- the same reason triage's slice ids are s01, not s1.
            "batches": [
                {
                    "id": f"b{i:02d}",
                    "hole_refs": batch,
                    "projected_bytes": len(batch) * per_scenario,
                }
                for i, batch in enumerate(batches, start=1)
            ],
        },
    )
    return run.batches
```

Add `from pathlib import Path` to the imports — `write_batches` annotates `Path | None`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_rounds.py -v`
Expected: PASS. Then `make test` and `make check`.

- [ ] **Step 5: Commit**

```bash
git add src/rubrica/rounds.py tests/unit/test_rounds.py
git commit -S -s -m "feat: Partition a round's closable holes into byte-bounded batches

The term that killed round 2 on run-20260825-094033 was not the accumulated
re-emit -- that was 24,613 of ~124,545 projected bytes, 20% -- but the round's
own batch, sized by the 86 closable holes the coverage report listed. So this
partitions holes rather than merely dropping the re-emit.

A batch is a writing unit the way a triage slice is a reading unit, and the
same thing makes it acceptable: nothing here decides anything. Every closable
hole reaches a member.

A budget below one scenario's estimate is refused rather than clamped: clamping
would emit a batch that cannot fit its own projection, which is a cap that does
not bind, silently.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---
### Task 4: `rounds.py` — assembling `02-scenarios.json` from the parts

The document that used to be emitted whole by a model becomes a pure function of the parts. It never reads its own output, so it is idempotent and byte-stable, which is what lets it run twice per round (once after propose, once after score) without the second run being able to disagree with the first.

**Files:**
- Modify: `src/rubrica/rounds.py`, `src/rubrica/findings.py` (one layer name)
- Test: `tests/unit/test_rounds.py`

**Interfaces:**
- Consumes: `RunPaths.scenario_part_rounds()`, `scenario_part_batch_ids()`, `unsafe_scenario_part_names()`, `score_part()` from Task 1.
- Produces: `seal_scenarios(run: RunPaths) -> tuple[Path | None, list[Finding]]`, `collect_scenarios(run: RunPaths) -> tuple[list[dict], list[Finding]]`. Findings carry `layer="rounds"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_rounds.py`:

```python
def _part(run, round_n, batch, scenarios):
    write_json(
        run.scenario_part(round_n, batch),
        {"schema_version": "0.1", "round": round_n, "batch_id": batch,
         "scenarios": scenarios},
    )


def _scenario(sid, *, round_n=1, goal="goal-0", status="proposed", refs=None, depth=1):
    return {
        "id": sid, "round": round_n, "goal_id": goal, "actor_id": "actor-0",
        "title": f"title {sid}", "user_intent": f"intent {sid}", "hop_depth": depth,
        "capability_refs": refs if refs is not None else [
            {"capability_id": "cap-0", "outcome_class_id": "cap-0-oc-0"}
        ],
        "discriminating_fact": f"fact {sid}", "status": status,
        "provenance": {"round": round_n},
    }


def test_the_seal_assembles_every_round_in_order(tmp_path):
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b02", [_scenario("sc-b02-001")])
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    _part(run, 2, "b01", [_scenario("sc-b01-002", round_n=2)])
    path, findings = rounds.seal_scenarios(run)
    assert findings == []
    assert path == run.scenarios
    doc = read_json(path)
    # Ordered by (round, batch id, position in part): deterministic, and it is
    # the order a reader scanning rounds expects.
    assert [s["id"] for s in doc["scenarios"]] == [
        "sc-b01-001", "sc-b02-001", "sc-b01-002",
    ]
    assert doc["denominator_version"] == 1


def test_the_seal_is_byte_identical_across_two_runs(tmp_path):
    # The property emit and both existing seals exist to hold: identical parts
    # must produce identical bytes, or variance stops being attributable.
    first = _run_with_world(tmp_path / "a", _world())
    second = _run_with_world(tmp_path / "b", _world())
    for run in (first, second):
        _part(run, 1, "b01", [_scenario("sc-b01-001"), _scenario("sc-b01-002")])
        _part(run, 1, "b02", [_scenario("sc-b02-001")])
        rounds.seal_scenarios(run)
    assert first.scenarios.read_bytes() == second.scenarios.read_bytes()


def test_the_seal_is_idempotent(tmp_path):
    # It runs twice per round -- after propose and after score -- so a second
    # run must not be able to disagree with the first. It reads only parts,
    # never its own output, which is what makes that true by construction.
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    rounds.seal_scenarios(run)
    once = run.scenarios.read_bytes()
    rounds.seal_scenarios(run)
    assert run.scenarios.read_bytes() == once


def test_the_seal_applies_a_rounds_rulings(tmp_path):
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001"), _scenario("sc-b01-002")])
    write_json(run.score_part(1), {
        "schema_version": "0.1", "round": 1, "holes": [], "verdict": "converged",
        "rulings": [
            {"scenario_id": "sc-b01-001", "status": "active"},
            {"scenario_id": "sc-b01-002", "status": "duplicate",
             "duplicate_of": "sc-b01-001"},
        ],
    })
    _, findings = rounds.seal_scenarios(run)
    assert findings == []
    by_id = {s["id"]: s for s in read_json(run.scenarios)["scenarios"]}
    assert by_id["sc-b01-001"]["status"] == "active"
    assert by_id["sc-b01-002"]["status"] == "duplicate"
    assert by_id["sc-b01-002"]["duplicate_of"] == "sc-b01-001"


def test_a_scenario_with_no_ruling_keeps_the_status_its_member_gave_it(tmp_path):
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    write_json(run.score_part(1), {
        "schema_version": "0.1", "round": 1, "holes": [], "verdict": "continue",
        "rulings": [],
    })
    rounds.seal_scenarios(run)
    assert read_json(run.scenarios)["scenarios"][0]["status"] == "proposed"


def test_a_later_round_may_overturn_an_earlier_ruling(tmp_path):
    # rb-score's Output section: "do not re-open a ruling that nothing new bears
    # on", never "statuses are frozen after the round that set them". A
    # rejection notice carried into a re-dispatch is exactly the case.
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    write_json(run.score_part(1), {
        "schema_version": "0.1", "round": 1, "holes": [], "verdict": "continue",
        "rulings": [{"scenario_id": "sc-b01-001", "status": "active"}],
    })
    write_json(run.score_part(2), {
        "schema_version": "0.1", "round": 2, "holes": [], "verdict": "converged",
        "rulings": [{"scenario_id": "sc-b01-001", "status": "rejected",
                     "rejected_reason": "ambiguous"}],
    })
    rounds.seal_scenarios(run)
    only = read_json(run.scenarios)["scenarios"][0]
    assert only["status"] == "rejected"
    assert only["rejected_reason"] == "ambiguous"


def test_the_seal_refuses_two_parts_claiming_one_scenario_id(tmp_path):
    # Members mint their own ids, so a collision is possible in a way it never
    # was for a single dispatch. It has to be caught here: the merged array
    # would simply carry the id twice, and check_scenarios indexes that array,
    # so it would agree with whatever it was handed.
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-001")])
    _part(run, 1, "b02", [_scenario("sc-001")])
    path, findings = rounds.seal_scenarios(run)
    assert path is None
    assert not run.scenarios.exists()
    assert any("sc-001" in f.message for f in findings)


def test_the_seal_refuses_a_ruling_for_a_scenario_no_part_wrote(tmp_path):
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    write_json(run.score_part(1), {
        "schema_version": "0.1", "round": 1, "holes": [], "verdict": "continue",
        "rulings": [{"scenario_id": "sc-nope", "status": "active"}],
    })
    path, findings = rounds.seal_scenarios(run)
    assert path is None
    assert any("sc-nope" in f.message for f in findings)


def test_the_seal_refuses_an_unparseable_part(tmp_path):
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    run.scenario_part(1, "b02").write_text("{not json", encoding="utf-8")
    path, findings = rounds.seal_scenarios(run)
    assert path is None
    assert any("b02" in str(f.path) or "b02" in f.message for f in findings)


def test_the_seal_refuses_a_part_whose_name_is_not_a_safe_segment(tmp_path):
    run = _run_with_world(tmp_path, _world())
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    (run.scenario_round_dir(1) / "..bad.json").write_text("{}", encoding="utf-8")
    path, findings = rounds.seal_scenarios(run)
    assert path is None
    assert any("..bad" in f.message for f in findings)


def test_the_seal_writes_nothing_when_no_part_exists(tmp_path):
    # Not a refusal: a run that has not dispatched propose yet simply has no
    # scenarios, and reporting a finding would make the orchestrator retry a
    # stage that has not run.
    run = _run_with_world(tmp_path, _world())
    path, findings = rounds.seal_scenarios(run)
    assert path is None
    assert findings == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_rounds.py -k seal -v`
Expected: FAIL, `AttributeError: module 'rubrica.rounds' has no attribute 'seal_scenarios'`.

- [ ] **Step 3: Add the "rounds" finding layer**

In `src/rubrica/findings.py`, extend the layer list in the `Finding` docstring and add the paragraph explaining the new one, in the style of the existing "reconcile" and "seal" paragraphs:

```
    "rounds" is rounds.py's layer: the artifacts are the propose parts and the
    score parts, and the failure is that they cannot be assembled at all -- two
    parts claiming one scenario id, a ruling for a scenario no part wrote, a
    part that does not parse. Distinct from "refs" for the reason "reconcile"
    is: refs checks a run someone may still be building, while this names the
    reason one command produced no output. Distinct from "seal" and "reconcile"
    because a reader triaging a failed round needs to know which assembler
    refused without reading the message.
```

- [ ] **Step 4: Write the assembly**

Append to `src/rubrica/rounds.py`:

```python
def collect_scenarios(run: RunPaths) -> tuple[list[dict], list[Finding]]:
    """Every part's scenarios, ordered by (round, batch id, position in part).

    Deterministic ordering is the whole point: this list becomes
    02-scenarios.json, and two runs with identical parts must produce identical
    bytes. Round and batch id are both sorted rather than taken in directory
    order, because a filesystem's order is not a promise.
    """
    scenarios: list[dict] = []
    findings: list[Finding] = []
    seen: dict[str, str] = {}
    for round_n in run.scenario_part_rounds():
        for name in run.unsafe_scenario_part_names(round_n):
            findings.append(
                Finding(
                    run.scenario_round_dir(round_n),
                    "rounds",
                    "",
                    f"part name {name!r} in round {round_n} is not a safe path segment, "
                    "so this seal will not join it into a path",
                )
            )
        for batch_id in run.scenario_part_batch_ids(round_n):
            path = run.scenario_part(round_n, batch_id)
            try:
                part = read_json(path)
            except ArtifactError as exc:
                findings.append(Finding(path, "rounds", "", str(exc)))
                continue
            if not isinstance(part, dict) or not isinstance(part.get("scenarios"), list):
                findings.append(
                    Finding(path, "rounds", "", "part is not an object carrying a scenarios array")
                )
                continue
            for i, scenario in enumerate(part["scenarios"]):
                if not isinstance(scenario, dict) or not isinstance(scenario.get("id"), str):
                    findings.append(
                        Finding(path, "rounds", f"/scenarios/{i}", "scenario has no string id")
                    )
                    continue
                sid = scenario["id"]
                where = f"round {round_n} batch {batch_id}"
                if sid in seen:
                    findings.append(
                        Finding(
                            path,
                            "rounds",
                            f"/scenarios/{i}/id",
                            f"scenario id {sid} is already claimed by {seen[sid]}; members "
                            "mint their own ids, so a collision has to be caught here -- the "
                            "merged array would simply carry it twice",
                        )
                    )
                    continue
                seen[sid] = where
                scenarios.append(scenario)
    return scenarios, findings


def _apply_rulings(run: RunPaths, scenarios: list[dict]) -> list[Finding]:
    """Fold every round's score rulings into the assembled scenarios, in place.

    Rounds are applied in ascending order so a later round may overturn an
    earlier ruling. rb-score's Output section asks for "do not re-open a ruling
    that nothing new bears on", never "statuses are frozen after the round that
    set them" -- a rejection notice carried into a re-dispatch is exactly the
    case where changing one is the point.
    """
    findings: list[Finding] = []
    by_id = {s["id"]: s for s in scenarios}
    for round_n in run.score_part_rounds():
        path = run.score_part(round_n)
        try:
            part = read_json(path)
        except ArtifactError as exc:
            findings.append(Finding(path, "rounds", "", str(exc)))
            continue
        if not isinstance(part, dict) or not isinstance(part.get("rulings"), list):
            findings.append(
                Finding(path, "rounds", "", "score part is not an object carrying a rulings array")
            )
            continue
        for i, ruling in enumerate(part["rulings"]):
            sid = ruling.get("scenario_id") if isinstance(ruling, dict) else None
            if not isinstance(sid, str):
                findings.append(
                    Finding(path, "rounds", f"/rulings/{i}", "ruling has no string scenario_id")
                )
                continue
            target = by_id.get(sid)
            if target is None:
                findings.append(
                    Finding(
                        path,
                        "rounds",
                        f"/rulings/{i}/scenario_id",
                        f"ruling names {sid}, which no propose part wrote",
                    )
                )
                continue
            target["status"] = ruling["status"]
            # Set only what the new status requires, and clear the other, so a
            # scenario rejected after having been folded does not keep a stale
            # duplicate_of that check_scenarios would then resolve happily.
            for field, keep in (("duplicate_of", "duplicate"), ("rejected_reason", "rejected")):
                if ruling["status"] == keep:
                    target[field] = ruling[field]
                else:
                    target.pop(field, None)
    return findings


def seal_scenarios(run: RunPaths) -> tuple[Path | None, list[Finding]]:
    """Assemble 02-scenarios.json from every propose part and every score ruling.

    A pure function of those parts: it never reads its own output, which is what
    makes it idempotent and lets it run twice per round -- after propose, so
    score has a document to read, and after score, so instantiate sees the
    statuses -- with no way for the second run to disagree with the first.

    Writes nothing when any finding is reported, for the reason seal.py gives:
    a half-assembled document would clear layer 1 for the fields it did manage
    to fill and read as a complete scenario list to a human at gate 2.
    """
    scenarios, findings = collect_scenarios(run)
    if not scenarios and not findings:
        # Propose has not run. Not a refusal: reporting one would make the
        # orchestrator retry a stage that was never dispatched.
        return None, []
    findings += _apply_rulings(run, scenarios)
    if findings:
        return None, findings
    world = read_json(run.world_model)
    write_json(
        run.scenarios,
        {
            "schema_version": "0.1",
            "denominator_version": world.get("denominator", {}).get("version", 1),
            "scenarios": scenarios,
        },
    )
    return run.scenarios, findings
```

Extend the module's imports: `from rubrica.artifacts import ArtifactError, read_json, write_json`, `from rubrica.findings import Finding`. `list_json` is **not** imported here — round discovery belongs to `RunPaths` (`scenario_part_rounds`, `score_part_rounds` from Task 1), so this module never parses a filename itself and the two seals cannot disagree about what a round directory is.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_rounds.py -v`
Expected: PASS. Then `make test` and `make check`.

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/rounds.py src/rubrica/findings.py tests/unit/test_rounds.py
git commit -S -s -m "feat: Assemble 02-scenarios.json from the propose and score parts

The document a model used to emit whole becomes a pure function of the parts:
never reads its own output, so it is idempotent and byte-stable, which is what
lets it run twice per round without the second run disagreeing with the first.

Refuses rather than half-assembling, on seal.py's reasoning -- a partial
document would clear layer 1 for the fields it filled and read as complete at
gate 2. The collision check is new work rather than a port: members mint their
own ids now, so two parts can claim one id, and the merged array would simply
carry it twice with check_scenarios agreeing with whatever it was handed.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---
### Task 5: `rounds.py` — the matrices, progress, and composing the coverage document

**Read before starting:** `rb-score/SKILL.md` Method steps 4, 5, 6 and 8. Those steps *are* the specification for the functions below — every rule is already stated there as a pure function of the world model and the scenario list, which is why this moves to code and why nothing here is a new judgment. Do not improve on them.

**Files:**
- Modify: `src/rubrica/rounds.py`
- Test: `tests/unit/test_rounds.py`

**Interfaces:**
- Consumes: `seal_scenarios` from Task 4.
- Produces: `capability_matrix(world: dict, scenarios: list[dict]) -> dict`, `goal_matrix(world: dict, scenarios: list[dict]) -> dict`, `progress(run: RunPaths, round_n: int, cap_matrix: dict) -> dict`, `seal_score(run: RunPaths, *, round_n: int) -> tuple[Path | None, list[Finding]]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_rounds.py`:

```python
def test_a_capability_cell_lists_every_claimant_but_is_covered_only_by_a_live_one(tmp_path):
    # Asymmetric on purpose, and rb-score's Method step 4 is where it comes
    # from: scenario_ids lists the scenarios *claiming* the cell, covered is
    # true only if one of them is proposed or active. A cell claimed only by
    # folded or rejected scenarios is a hole again, because no test will ship.
    world = _world(caps=1, ocs=1, goals=0)
    refs = [{"capability_id": "cap-0", "outcome_class_id": "cap-0-oc-0"}]
    scenarios = [
        _scenario("sc-001", status="duplicate", refs=refs),
        _scenario("sc-002", status="rejected", refs=refs),
    ]
    matrix = rounds.capability_matrix(world, scenarios)
    assert matrix["cells"][0]["scenario_ids"] == ["sc-001", "sc-002"]
    assert matrix["cells"][0]["covered"] is False
    assert matrix == {"cells": matrix["cells"], "covered": 0, "total": 1, "pct": 0.0}

    scenarios.append(_scenario("sc-003", status="active", refs=refs))
    matrix = rounds.capability_matrix(world, scenarios)
    assert matrix["cells"][0]["covered"] is True
    assert matrix["covered"] == 1 and matrix["pct"] == 1.0


def test_every_declared_cell_appears_even_with_no_scenarios(tmp_path):
    # The dangerous direction, per Method step 4: a matrix holding only the
    # cells some scenario happens to claim reports 100% of a denominator it
    # shrank to fit. Enumerate from the world model, never from the scenarios.
    matrix = rounds.capability_matrix(_world(caps=2, ocs=2, goals=0), [])
    assert matrix["total"] == 4
    assert matrix["covered"] == 0
    assert matrix["pct"] == 0.0
    assert [c["capability_id"] for c in matrix["cells"]] == [
        "cap-0", "cap-0", "cap-1", "cap-1",
    ]


def test_a_goal_row_carries_only_live_scenarios(tmp_path):
    # Method step 5: leaving a duplicate in a goal row credits the goal with a
    # depth no shipped test reaches.
    world = _world(caps=1, ocs=1, goals=1)
    world["goals"][0]["expected_hop_depths"] = [1, 2]
    scenarios = [
        _scenario("sc-001", status="active", depth=1),
        _scenario("sc-002", status="duplicate", depth=2),
    ]
    row = rounds.goal_matrix(world, scenarios)["rows"][0]
    assert row["scenario_ids"] == ["sc-001"]
    assert row["hop_depths_present"] == [1]
    assert row["hop_depths_expected"] == [1, 2]
    # A goal exercised at one depth of two is a partial row, not a covered one.
    assert row["covered"] is False


def test_a_goal_is_covered_only_when_every_expected_depth_is_present(tmp_path):
    world = _world(caps=1, ocs=1, goals=1)
    world["goals"][0]["expected_hop_depths"] = [1, 2]
    scenarios = [
        _scenario("sc-001", status="active", depth=1),
        _scenario("sc-002", status="active", depth=2),
    ]
    row = rounds.goal_matrix(world, scenarios)["rows"][0]
    assert row["hop_depths_present"] == [1, 2]
    assert row["covered"] is True


def test_expected_hop_depths_are_copied_not_trimmed(tmp_path):
    # Method step 5 says copied, not re-derived and not trimmed to what the
    # scenarios reached -- trimming is how a partial row looks complete.
    world = _world(caps=1, ocs=1, goals=1)
    world["goals"][0]["expected_hop_depths"] = [3, 1]
    row = rounds.goal_matrix(world, [])["rows"][0]
    assert row["hop_depths_expected"] == [1, 3]
    assert row["covered"] is False


def test_an_empty_denominator_gives_pct_zero_not_a_zero_division(tmp_path):
    empty = {"schema_version": "0.1", "capabilities": [], "goals": [],
             "denominator": {"capability_cells": 0, "goals": 0, "version": 1}}
    assert rounds.capability_matrix(empty, [])["pct"] == 0.0
    assert rounds.goal_matrix(empty, [])["pct"] == 0.0


def test_round_one_progress_counts_the_cells_it_covered(tmp_path):
    run = _run_with_world(tmp_path, _world(caps=1, ocs=2, goals=0))
    matrix = rounds.capability_matrix(read_json(run.world_model), [
        _scenario("sc-001", status="active",
                  refs=[{"capability_id": "cap-0", "outcome_class_id": "cap-0-oc-0"}]),
    ])
    assert rounds.progress(run, 1, matrix) == {
        "new_cells_this_round": 1, "rounds_without_progress": 0,
    }


def test_round_one_that_covered_nothing_starts_the_no_progress_count(tmp_path):
    run = _run_with_world(tmp_path, _world(caps=1, ocs=2, goals=0))
    matrix = rounds.capability_matrix(read_json(run.world_model), [])
    assert rounds.progress(run, 1, matrix) == {
        "new_cells_this_round": 0, "rounds_without_progress": 1,
    }


def test_new_cells_is_a_set_difference_not_a_count_difference(tmp_path):
    # Method step 8: "covered now and were *not* covered before". A count
    # difference reports zero when one cell is gained and another lost, which
    # is real progress the loop would then halt on.
    run = _run_with_world(tmp_path, _world(caps=1, ocs=2, goals=0))
    write_json(run.coverage_round(1), {
        "schema_version": "0.1", "round": 1, "denominator_version": 1,
        "capability_matrix": {
            "cells": [
                {"capability_id": "cap-0", "outcome_class_id": "cap-0-oc-0",
                 "scenario_ids": ["sc-001"], "covered": True},
                {"capability_id": "cap-0", "outcome_class_id": "cap-0-oc-1",
                 "scenario_ids": [], "covered": False},
            ],
            "covered": 1, "total": 2, "pct": 0.5,
        },
        "goal_matrix": {"rows": [], "covered": 0, "total": 0, "pct": 0.0},
        "holes": [], "verdict": "continue",
        "progress": {"new_cells_this_round": 1, "rounds_without_progress": 0},
    })
    now = rounds.capability_matrix(read_json(run.world_model), [
        _scenario("sc-002", status="active", round_n=2,
                  refs=[{"capability_id": "cap-0", "outcome_class_id": "cap-0-oc-1"}]),
    ])
    assert now["covered"] == 1  # same count as round 1
    assert rounds.progress(run, 2, now)["new_cells_this_round"] == 1
    assert rounds.progress(run, 2, now)["rounds_without_progress"] == 0


def test_a_round_with_no_new_cell_increments_the_prior_no_progress_count(tmp_path):
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=0))
    write_json(run.coverage_round(1), {
        "schema_version": "0.1", "round": 1, "denominator_version": 1,
        "capability_matrix": {"cells": [], "covered": 0, "total": 0, "pct": 0.0},
        "goal_matrix": {"rows": [], "covered": 0, "total": 0, "pct": 0.0},
        "holes": [], "verdict": "continue",
        "progress": {"new_cells_this_round": 0, "rounds_without_progress": 1},
    })
    matrix = rounds.capability_matrix(read_json(run.world_model), [])
    assert rounds.progress(run, 2, matrix)["rounds_without_progress"] == 2


def _score_part(run, round_n, *, holes, verdict="continue", rulings=None):
    write_json(run.score_part(round_n), {
        "schema_version": "0.1", "round": round_n,
        "rulings": rulings or [], "holes": holes, "verdict": verdict,
    })


def test_seal_score_composes_a_schema_valid_coverage_document(tmp_path):
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=1))
    _part(run, 1, "b01", [_scenario("sc-b01-001")])
    _score_part(run, 1, holes=[
        {"ref": "goal:goal-0", "reason": "not_yet_attempted", "justification": "nobody yet"},
    ], verdict="continue", rulings=[{"scenario_id": "sc-b01-001", "status": "active"}])
    rounds.seal_scenarios(run)
    path, findings = rounds.seal_score(run, round_n=1)
    assert findings == []
    assert path == run.coverage_round(1)
    doc = read_json(path)
    assert doc["round"] == 1
    assert doc["verdict"] == "continue"
    assert doc["capability_matrix"]["covered"] == 1
    assert doc["goal_matrix"]["covered"] == 0
    assert doc["holes"] == [
        {"ref": "goal:goal-0", "reason": "not_yet_attempted", "justification": "nobody yet"},
    ]
    # latest.json is a code-written copy, so it cannot drift from round-N.json
    # the way two model writes of "identical content" can.
    assert run.coverage_latest.read_bytes() == path.read_bytes()


def test_seal_score_refuses_an_uncovered_row_with_no_hole(tmp_path):
    # refs.check_coverage checks both directions after the fact; the seal
    # refuses before the write, because a coverage document missing a hole is
    # otherwise perfectly assemblable and reads as complete at gate 2.
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=1))
    _part(run, 1, "b01", [])
    _score_part(run, 1, holes=[])
    rounds.seal_scenarios(run)
    path, findings = rounds.seal_score(run, round_n=1)
    assert path is None
    assert not run.coverage_round(1).exists()
    refs_named = " ".join(f.message for f in findings)
    assert "cell:cap-0/cap-0-oc-0" in refs_named
    assert "goal:goal-0" in refs_named


def test_seal_score_refuses_a_hole_naming_a_covered_row(tmp_path):
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=0))
    _part(run, 1, "b01", [_scenario("sc-b01-001", status="active")])
    _score_part(run, 1, holes=[
        {"ref": "cell:cap-0/cap-0-oc-0", "reason": "not_yet_attempted", "justification": "x"},
    ], verdict="converged")
    rounds.seal_scenarios(run)
    path, findings = rounds.seal_score(run, round_n=1)
    assert path is None
    assert any("cell:cap-0/cap-0-oc-0" in f.message for f in findings)


def test_seal_score_refuses_a_hole_naming_a_row_the_world_model_does_not_have(tmp_path):
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=0))
    _part(run, 1, "b01", [_scenario("sc-b01-001", status="active")])
    _score_part(run, 1, holes=[
        {"ref": "cell:cap-9/nope", "reason": "unreachable", "justification": "x"},
    ], verdict="converged")
    rounds.seal_scenarios(run)
    path, findings = rounds.seal_score(run, round_n=1)
    assert path is None
    assert any("cap-9" in f.message for f in findings)


def test_seal_score_refuses_a_missing_score_part(tmp_path):
    run = _run_with_world(tmp_path, _world(caps=1, ocs=1, goals=0))
    _part(run, 1, "b01", [_scenario("sc-b01-001", status="active")])
    rounds.seal_scenarios(run)
    path, findings = rounds.seal_score(run, round_n=1)
    assert path is None
    assert findings != []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_rounds.py -k "matrix or progress or seal_score or hop_depths or denominator_gives" -v`
Expected: FAIL, `AttributeError: module 'rubrica.rounds' has no attribute 'capability_matrix'`.

- [ ] **Step 3: Write the matrices, progress, and the composition**

Append to `src/rubrica/rounds.py`:

```python
def capability_matrix(world: dict, scenarios: list[dict]) -> dict:
    """One cell per capability x outcome-class pair the world model declares.

    Transcribed from rb-score's Method step 4, which already specifies it as a
    pure function -- nothing here is a judgment this module took over. Two rules
    from that step are easy to get subtly wrong and both are load-bearing:

    * Enumerate from the world model, never from the scenario list. A matrix
      holding only the cells some scenario happens to claim reports 100% of a
      denominator it shrank to fit.
    * `scenario_ids` lists every scenario *claiming* the cell, including the
      folded and the rejected, while `covered` is true only if one of them is
      still live. The asymmetry is deliberate: a cell claimed only by scenarios
      that will never ship is a hole again.
    """
    live = {s["id"] for s in scenarios if s.get("status") in _live_statuses()}
    cells = []
    for cap in world.get("capabilities", []):
        for oc in cap.get("outcome_classes", []):
            claimants = sorted(
                s["id"]
                for s in scenarios
                if any(
                    ref.get("capability_id") == cap["id"]
                    and ref.get("outcome_class_id") == oc["id"]
                    for ref in s.get("capability_refs", [])
                )
            )
            cells.append(
                {
                    "capability_id": cap["id"],
                    "outcome_class_id": oc["id"],
                    "scenario_ids": claimants,
                    "covered": any(sid in live for sid in claimants),
                }
            )
    return _summarise(cells, "cells")


def goal_matrix(world: dict, scenarios: list[dict]) -> dict:
    """One row per goal the world model declares.

    Transcribed from rb-score's Method step 5. Unlike a capability cell, a goal
    row's `scenario_ids` carries only the live scenarios: leaving a folded one in
    credits the goal with a hop depth no shipped test reaches.

    `hop_depths_expected` is copied from the goal, not trimmed to what the
    scenarios reached. Trimming is how a goal exercised at one depth of two
    reaches 100% without ever testing the multi-hop half the suite exists to
    probe.
    """
    rows = []
    for goal in world.get("goals", []):
        mine = [
            s
            for s in scenarios
            if s.get("status") in _live_statuses() and s.get("goal_id") == goal["id"]
        ]
        expected = sorted(set(goal["expected_hop_depths"]))
        present = sorted({s["hop_depth"] for s in mine})
        rows.append(
            {
                "goal_id": goal["id"],
                "scenario_ids": sorted(s["id"] for s in mine),
                "hop_depths_present": present,
                "hop_depths_expected": expected,
                "covered": bool(mine) and set(expected) <= set(present),
            }
        )
    return _summarise(rows, "rows")


def _summarise(rows: list[dict], key: str) -> dict:
    """covered/total/pct from the rows themselves, per Method step 6.

    pct is 0.0 rather than a ZeroDivisionError on an empty denominator: a world
    model with no capabilities is a real (if useless) run, and
    refs._check_matrix_arithmetic already expects that convention.
    """
    covered = sum(1 for row in rows if row["covered"])
    return {
        key: rows,
        "covered": covered,
        "total": len(rows),
        "pct": (covered / len(rows)) if rows else 0.0,
    }


def _covered_cell_keys(matrix: dict) -> set[tuple[str, str]]:
    return {
        (c["capability_id"], c["outcome_class_id"]) for c in matrix["cells"] if c["covered"]
    }


def progress(run: RunPaths, round_n: int, cap_matrix: dict) -> dict:
    """new_cells_this_round and rounds_without_progress, per Method step 8.

    `new_cells_this_round` is a *set* difference, not a difference of counts:
    "covered now and were not covered before this round". A count difference
    reports zero when one cell is gained and another lost, and the loop would
    then halt on progress it actually made.
    """
    now = _covered_cell_keys(cap_matrix)
    previous = run.coverage_round(round_n - 1) if round_n > 1 else None
    if previous is None or not previous.exists():
        new_cells = len(now)
        return {
            "new_cells_this_round": new_cells,
            "rounds_without_progress": 0 if new_cells else 1,
        }
    prior = read_json(previous)
    was = _covered_cell_keys(prior["capability_matrix"])
    new_cells = len(now - was)
    carried = prior.get("progress", {}).get("rounds_without_progress", 0)
    return {
        "new_cells_this_round": new_cells,
        "rounds_without_progress": 0 if new_cells else carried + 1,
    }


def seal_score(run: RunPaths, *, round_n: int) -> tuple[Path | None, list[Finding]]:
    """Compose 03-coverage/round-N.json, and publish it as latest.json.

    The matrices are computed here rather than read from the score part, so a
    percentage cannot disagree with the matrix beneath it -- the failure rb-score's
    own Output section warns about. What score decides (the holes' reasons and
    justifications, the verdict) is copied through untouched.

    latest.json is a byte copy rather than a second composition, which removes
    the "written twice with identical content" instruction that could only ever
    drift.

    Refuses before writing on the class where assembly cannot faithfully
    represent what it was handed. Items 2 and 3 below overlap
    refs.check_coverage deliberately, for the reason seal.py gives for its own
    overlaps: check_coverage reports after the fact over any coverage document,
    including one this seal never composed, while a missing hole is otherwise
    perfectly assemblable and would reach gate 2 looking complete.
    """
    findings: list[Finding] = []
    path = run.score_part(round_n)
    try:
        part = read_json(path)
    except ArtifactError as exc:
        return None, [Finding(path, "rounds", "", str(exc))]
    for key, kind in (("holes", list), ("verdict", str)):
        if not isinstance(part.get(key), kind):
            findings.append(Finding(path, "rounds", f"/{key}", f"score part has no {key}"))
    if findings:
        return None, findings

    world = read_json(run.world_model)
    scenarios = read_json(run.scenarios).get("scenarios", []) if run.scenarios.exists() else []
    cap = capability_matrix(world, scenarios)
    goals = goal_matrix(world, scenarios)

    uncovered = {f"cell:{c['capability_id']}/{c['outcome_class_id']}"
                 for c in cap["cells"] if not c["covered"]}
    uncovered |= {f"goal:{r['goal_id']}" for r in goals["rows"] if not r["covered"]}
    every_row = {f"cell:{c['capability_id']}/{c['outcome_class_id']}" for c in cap["cells"]}
    every_row |= {f"goal:{r['goal_id']}" for r in goals["rows"]}

    holed = {hole["ref"] for hole in part["holes"]}
    for ref in sorted(holed - every_row):
        findings.append(
            Finding(path, "rounds", "/holes",
                    f"hole names {ref}, which the world model does not declare")
        )
    for ref in sorted(holed & every_row - uncovered):
        findings.append(
            Finding(path, "rounds", "/holes",
                    f"hole names {ref}, which the computed matrices show as covered")
        )
    for ref in sorted(uncovered - holed):
        findings.append(
            Finding(path, "rounds", "/holes",
                    f"{ref} is uncovered and no hole justifies it")
        )
    if findings:
        return None, findings

    document = {
        "schema_version": "0.1",
        "round": round_n,
        "denominator_version": world.get("denominator", {}).get("version", 1),
        "capability_matrix": cap,
        "goal_matrix": goals,
        "holes": part["holes"],
        "progress": progress(run, round_n, cap),
        "verdict": part["verdict"],
    }
    write_json(run.coverage_round(round_n), document)
    write_json(run.coverage_latest, document)
    return run.coverage_round(round_n), findings
```

`write_json` is canonical (sorted keys, fixed indent), so writing the same `document` object to both paths produces identical bytes — that is what the `latest.json` byte-equality test asserts.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_rounds.py -v`
Expected: PASS. Then `make test` and `make check`.

- [ ] **Step 5: Commit**

```bash
git add src/rubrica/rounds.py tests/unit/test_rounds.py
git commit -S -s -m "feat: Compute the coverage matrices in code and compose the report

rb-score's Method steps 4, 5 and 6 already specify both matrices as pure
functions of the world model and the scenario list, and refs.py already
recomputes them in checker form. So this deletes a transcription step a checker
exists to police, and removes the failure that section warns about: a
percentage that disagrees with the matrix beneath it.

Two rules are easy to get subtly wrong and both are kept: enumerate cells from
the world model rather than the scenario list, and let a capability cell list
every claimant while only a live one covers it. new_cells_this_round is a set
difference, not a count difference -- a count reports zero when one cell is
gained and another lost, and the loop would halt on real progress.

latest.json becomes a byte copy, which retires the 'written twice with
identical content' instruction that could only ever drift.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---
### Task 6: The three subcommands

**Files:**
- Modify: `src/rubrica/cli.py`, `docs/reference/cli.md`
- Test: `tests/unit/test_rounds_cli.py`

**Interfaces:**
- Consumes: `rounds.write_batches`, `rounds.seal_scenarios`, `rounds.seal_score`.
- Produces: `rubrica propose-batches --run PATH --round N`, `rubrica propose-seal --run PATH`, `rubrica score-seal --run PATH --round N`.

**Why `--round` is passed rather than inferred:** the same reason `reconcile-seal` takes `--denominator-version`. A command that incremented a round it found on disk would let the loop advance without an orchestrator decision on the record, and `decisions.md` is where a round is accounted for.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_rounds_cli.py`:

```python
"""The loop's three code subcommands, including the paths that must exit 2.

The exit-code contract is load-bearing: 0 clean, 1 findings one per line on
stdout, 2 usage error or unreadable run. A stage defect must never surface as 2,
a 1 must never have empty stdout, and a 1 must name the right artifact -- the
class that once produced four fabricated "no such claim" findings against a
correct world model.
"""

from __future__ import annotations

import json

import pytest

from rubrica.artifacts import read_json, write_json
from rubrica.cli import main
from rubrica.paths import RunPaths

pytestmark = pytest.mark.usefixtures()


def _minimal(tmp_path):
    run = RunPaths(tmp_path)
    write_json(run.world_model, {
        "schema_version": "0.1",
        "denominator": {"capability_cells": 1, "goals": 1, "version": 1},
        "capabilities": [{"id": "cap-0", "outcome_classes": [{"id": "cap-0-oc-0"}]}],
        "goals": [{"id": "goal-0", "expected_hop_depths": [1]}],
    })
    return run


def test_propose_batches_exits_clean_and_prints_the_path(tmp_path, capsys):
    run = _minimal(tmp_path)
    assert main(["propose-batches", "--run", str(tmp_path), "--round", "1"]) == 0
    assert str(run.batches) in capsys.readouterr().out


def test_propose_batches_says_so_when_there_is_nothing_to_dispatch(tmp_path, capsys):
    run = _minimal(tmp_path)
    write_json(run.world_model, {"schema_version": "0.1", "capabilities": [], "goals": [],
                                 "denominator": {"capability_cells": 0, "goals": 0,
                                                 "version": 1}})
    # Exit 0, not 1: no closable hole is a fact about the run, not a defect in
    # it, and the orchestrator branches on the message rather than on a finding.
    assert main(["propose-batches", "--run", str(tmp_path), "--round", "1"]) == 0
    assert "no closable holes" in capsys.readouterr().out
    assert not run.batches.exists()


def test_propose_batches_exits_two_on_an_unreadable_world_model(tmp_path, capsys):
    run = _minimal(tmp_path)
    run.world_model.chmod(0o000)
    try:
        assert main(["propose-batches", "--run", str(tmp_path), "--round", "1"]) == 2
    finally:
        run.world_model.chmod(0o644)
    assert capsys.readouterr().err.strip() != ""


def test_propose_batches_exits_two_on_a_missing_run(tmp_path):
    assert main(["propose-batches", "--run", str(tmp_path / "nope"), "--round", "1"]) == 2


def test_propose_batches_exits_two_on_a_budget_below_one_scenario(tmp_path, capsys):
    run = _minimal(tmp_path)
    write_json(run.manifest, {"limits": {"max_rounds": 2, "max_scenarios": 128,
                                         "max_scenario_part_bytes": 10}})
    # A misconfigured budget is a usage error, not a stage defect: no
    # re-dispatch of any prompt can fix it.
    assert main(["propose-batches", "--run", str(tmp_path), "--round", "1"]) == 2
    assert "max_scenario_part_bytes" in capsys.readouterr().err


def test_propose_seal_exits_one_with_a_line_per_finding(tmp_path, capsys):
    run = _minimal(tmp_path)
    for batch in ("b01", "b02"):
        write_json(run.scenario_part(1, batch), {
            "schema_version": "0.1", "round": 1, "batch_id": batch,
            "scenarios": [{"id": "sc-001", "round": 1, "goal_id": "goal-0",
                           "actor_id": "a", "title": "t", "user_intent": "u",
                           "hop_depth": 1, "capability_refs": [],
                           "discriminating_fact": "f", "status": "proposed",
                           "provenance": {"round": 1}}],
        })
    assert main(["propose-seal", "--run", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    # A 1 must never have empty stdout, and every finding is one line.
    assert out.strip() != ""
    assert all(line.strip() for line in out.strip().splitlines())
    assert "sc-001" in out


def test_score_seal_exits_one_and_names_the_score_part_not_the_coverage_file(tmp_path, capsys):
    # The right-artifact rule: the defect is in the part a prompt wrote, and a
    # finding against 03-coverage/round-1.json would name a file that does not
    # exist and that no re-dispatch could repair.
    run = _minimal(tmp_path)
    write_json(run.scenario_part(1, "b01"), {
        "schema_version": "0.1", "round": 1, "batch_id": "b01", "scenarios": [],
    })
    write_json(run.score_part(1), {
        "schema_version": "0.1", "round": 1, "rulings": [], "holes": [],
        "verdict": "converged",
    })
    assert main(["propose-seal", "--run", str(tmp_path)]) == 0
    assert main(["score-seal", "--run", str(tmp_path), "--round", "1"]) == 1
    out = capsys.readouterr().out
    assert "03-score" in out
    assert not run.coverage_round(1).exists()


def test_score_seal_exits_clean_and_publishes_latest(tmp_path, capsys):
    run = _minimal(tmp_path)
    write_json(run.scenario_part(1, "b01"), {
        "schema_version": "0.1", "round": 1, "batch_id": "b01", "scenarios": [],
    })
    write_json(run.score_part(1), {
        "schema_version": "0.1", "round": 1, "rulings": [], "verdict": "continue",
        "holes": [
            {"ref": "cell:cap-0/cap-0-oc-0", "reason": "not_yet_attempted",
             "justification": "nobody yet"},
            {"ref": "goal:goal-0", "reason": "not_yet_attempted",
             "justification": "nobody yet"},
        ],
    })
    assert main(["propose-seal", "--run", str(tmp_path)]) == 0
    assert main(["score-seal", "--run", str(tmp_path), "--round", "1"]) == 0
    assert run.coverage_latest.read_bytes() == run.coverage_round(1).read_bytes()
    assert str(run.coverage_round(1)) in capsys.readouterr().out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_rounds_cli.py -v`
Expected: FAIL, `argparse` exits 2 with "invalid choice: 'propose-batches'".

- [ ] **Step 3: Register the subcommands**

In `src/rubrica/cli.py`, add to `SUBCOMMANDS` immediately after `("reconcile-seal", ...)` so the roster reads in pipeline order:

```python
    ("propose-batches", "partition a round's closable holes into byte-bounded batches"),
    ("propose-seal", "assemble the propose parts and score rulings into the scenario list"),
    ("score-seal", "compute the coverage matrices and compose the round's report"),
```

Add the parsers beside `p_reconcile_seal`:

```python
    p_batches = parsers["propose-batches"]
    p_batches.add_argument("--run", required=True)
    # Passed rather than inferred, on reconcile-seal's --denominator-version
    # reasoning: a command that incremented a round it found on disk would let
    # the loop advance without a decision on the record.
    p_batches.add_argument("--round", type=int, required=True)

    p_propose_seal = parsers["propose-seal"]
    p_propose_seal.add_argument("--run", required=True)

    p_score_seal = parsers["score-seal"]
    p_score_seal.add_argument("--run", required=True)
    p_score_seal.add_argument("--round", type=int, required=True)
```

Add the handlers inside the same `try:` block that holds `triage-slices` and `reconcile-seal`, so the shared `except (UsageError, ArtifactError, OSError)` maps every unreadable-input path to exit 2:

```python
        if args.command == "propose-batches":
            run = _run_dir(args.run)
            path = rounds.write_batches(run, round_n=args.round)
            if path is None:
                # Exit 0 with a message, not a finding: no closable hole is a
                # fact about the run, and the orchestrator branches on it to
                # stop the loop rather than to repair a stage.
                print("no closable holes: there is no propose round to dispatch")
                return CLEAN
            print(path)
            return CLEAN

        if args.command == "propose-seal":
            run = _run_dir(args.run)
            path, findings = rounds.seal_scenarios(run)
            if path is not None:
                print(path)
            return _report(findings)

        if args.command == "score-seal":
            run = _run_dir(args.run)
            path, findings = rounds.seal_score(run, round_n=args.round)
            if path is not None:
                print(path)
            return _report(findings)
```

Add `from rubrica import rounds` to the imports.

- [ ] **Step 4: Document them**

Add a `rubrica propose-batches`, `rubrica propose-seal` and `rubrica score-seal` section to `docs/reference/cli.md` — `tests/unit/test_docs_accuracy.py` asserts a section per `SUBCOMMANDS` name and fails until each exists. For each: what it reads, what it writes, its exit codes, and the one-line reason it is code rather than a prompt. For `propose-batches` also record that exit 0 with "no closable holes" and no artifact is the normal end of the loop, not an error.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_rounds_cli.py tests/unit/test_docs_accuracy.py -v`
Expected: PASS. Then `make test` and `make check`.

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/cli.py docs/reference/cli.md tests/unit/test_rounds_cli.py
git commit -S -s -m "feat: Add propose-batches, propose-seal and score-seal

--round is passed rather than inferred, on reconcile-seal's
--denominator-version reasoning: a command that incremented a round it found on
disk would let the loop advance without a decision on the record.

propose-batches exits 0 with a message and no artifact when no hole is closable.
That is the normal end of the loop rather than a defect, and a finding there
would make the orchestrator repair a stage that has nothing wrong with it.

Tests cover the exit-2 paths -- unreadable world model, missing run,
misconfigured budget -- and assert that a 1 carries a line per finding naming
the score part rather than the coverage file it declined to write.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 7: Layer 2 checkers for the new parts

**Files:**
- Modify: `src/rubrica/refs.py`
- Test: `tests/unit/test_refs.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `check_batches(run) -> list[Finding]`, `check_scenario_parts(run) -> list[Finding]`, `check_score_parts(run) -> list[Finding]`, all three called from `check_all`.

**The check that makes the partition enforceable:** a scenario in part `<batch>` must target a hole assigned to that batch. Without it the partition is instruction only, and a member that wandered into a sibling's holes would produce a document byte-identical to one that did not. This mirrors the triage seal's existing refusal on "a disposition naming a candidate outside the slice its own part rules on", and it is the one thing here that overlaps no other layer.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_refs.py`:

```python
def test_check_batches_recomputes_projected_bytes(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(run.batches, {
        "schema_version": "0.1", "round": 1, "cap_bytes": 28000,
        "bytes_per_scenario": 1600,
        "batches": [{"id": "b01", "hole_refs": ["cell:cap-0/cap-0-oc-0"],
                     "projected_bytes": 99}],
    })
    findings = refs.check_batches(run)
    assert any("projected_bytes" in f.message for f in findings)


def test_check_batches_reports_a_batch_over_its_own_cap(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(run.batches, {
        "schema_version": "0.1", "round": 1, "cap_bytes": 1600,
        "bytes_per_scenario": 1600,
        "batches": [{"id": "b01",
                     "hole_refs": ["cell:cap-0/cap-0-oc-0", "goal:goal-0"],
                     "projected_bytes": 3200}],
    })
    assert any("cap_bytes" in f.message for f in refs.check_batches(run))


def test_check_batches_reports_a_hole_ref_the_world_model_does_not_declare(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(run.batches, {
        "schema_version": "0.1", "round": 1, "cap_bytes": 28000,
        "bytes_per_scenario": 1600,
        "batches": [{"id": "b01", "hole_refs": ["cell:cap-9/nope"],
                     "projected_bytes": 1600}],
    })
    assert any("cap-9" in f.message for f in refs.check_batches(run))


def test_check_batches_reports_a_hole_assigned_to_two_batches(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(run.batches, {
        "schema_version": "0.1", "round": 1, "cap_bytes": 28000,
        "bytes_per_scenario": 1600,
        "batches": [
            {"id": "b01", "hole_refs": ["goal:goal-0"], "projected_bytes": 1600},
            {"id": "b02", "hole_refs": ["goal:goal-0"], "projected_bytes": 1600},
        ],
    })
    # A partition, not a covering: two members proposing against one hole is a
    # guaranteed duplicate that score then has to fold.
    assert any("goal:goal-0" in f.message for f in refs.check_batches(run))


def test_check_scenario_parts_wants_a_file_per_batch(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(run.batches, {
        "schema_version": "0.1", "round": 1, "cap_bytes": 28000,
        "bytes_per_scenario": 1600,
        "batches": [
            {"id": "b01", "hole_refs": ["goal:goal-0"], "projected_bytes": 1600},
            {"id": "b02", "hole_refs": ["cell:cap-0/cap-0-oc-0"], "projected_bytes": 1600},
        ],
    })
    write_json(run.scenario_part(1, "b01"), {
        "schema_version": "0.1", "round": 1, "batch_id": "b01", "scenarios": [],
    })
    # Reports every missing batch from the moment the directory exists, which is
    # why the orchestrator runs this only once the fan-out has finished -- the
    # property check_verdicts and check_contradiction_parts already have.
    assert any("b02" in f.message for f in refs.check_scenario_parts(run))


def test_check_scenario_parts_reports_a_scenario_outside_its_own_batch(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(run.batches, {
        "schema_version": "0.1", "round": 1, "cap_bytes": 28000,
        "bytes_per_scenario": 1600,
        "batches": [
            {"id": "b01", "hole_refs": ["goal:goal-0"], "projected_bytes": 1600},
            {"id": "b02", "hole_refs": ["cell:cap-0/cap-0-oc-0"], "projected_bytes": 1600},
        ],
    })
    write_json(run.scenario_part(1, "b01"), {
        "schema_version": "0.1", "round": 1, "batch_id": "b01",
        # goal-1 is b01's, but this cell belongs to b02.
        "scenarios": [{"id": "sc-b01-001", "round": 1, "goal_id": "goal-0",
                       "actor_id": "a", "title": "t", "user_intent": "u",
                       "hop_depth": 1,
                       "capability_refs": [{"capability_id": "cap-0",
                                            "outcome_class_id": "cap-0-oc-0"}],
                       "discriminating_fact": "f", "status": "proposed",
                       "provenance": {"round": 1}}],
    })
    write_json(run.scenario_part(1, "b02"), {
        "schema_version": "0.1", "round": 1, "batch_id": "b02", "scenarios": [],
    })
    findings = refs.check_scenario_parts(run)
    assert any("b02" in f.message and "sc-b01-001" in f.message for f in findings)


def test_check_scenario_parts_reports_a_mismatched_batch_id_header(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(run.batches, {
        "schema_version": "0.1", "round": 1, "cap_bytes": 28000,
        "bytes_per_scenario": 1600,
        "batches": [{"id": "b01", "hole_refs": ["goal:goal-0"], "projected_bytes": 1600}],
    })
    write_json(run.scenario_part(1, "b01"), {
        "schema_version": "0.1", "round": 1, "batch_id": "b99", "scenarios": [],
    })
    assert any("b99" in f.message for f in refs.check_scenario_parts(run))


def test_check_score_parts_reports_a_ruling_for_an_unknown_scenario(tmp_path):
    run = _run_with_world_for_refs(tmp_path)
    write_json(run.scenarios, {"schema_version": "0.1", "denominator_version": 1,
                               "scenarios": []})
    write_json(run.score_part(1), {
        "schema_version": "0.1", "round": 1, "holes": [], "verdict": "converged",
        "rulings": [{"scenario_id": "sc-ghost", "status": "active"}],
    })
    assert any("sc-ghost" in f.message for f in refs.check_score_parts(run))


def test_check_score_parts_reports_a_fold_onto_a_scenario_that_is_itself_a_duplicate(tmp_path):
    # A fold chain leaves no shipped test for either cell, and check_scenarios'
    # equivalent guard is on the sealed document -- this one names the part a
    # re-dispatch can actually repair.
    run = _run_with_world_for_refs(tmp_path)
    write_json(run.scenarios, {
        "schema_version": "0.1", "denominator_version": 1,
        "scenarios": [
            {"id": "sc-001", "round": 1, "goal_id": "goal-0", "actor_id": "a",
             "title": "t", "user_intent": "u", "hop_depth": 1,
             "capability_refs": [], "discriminating_fact": "f",
             "status": "duplicate", "duplicate_of": "sc-002",
             "provenance": {"round": 1}},
        ],
    })
    write_json(run.score_part(1), {
        "schema_version": "0.1", "round": 1, "holes": [], "verdict": "converged",
        "rulings": [{"scenario_id": "sc-001", "status": "duplicate",
                     "duplicate_of": "sc-001"}],
    })
    assert refs.check_score_parts(run) != []


def test_check_all_runs_the_new_checkers(tmp_path):
    # check_all runs every checker the run has inputs for -- there is no such
    # thing as a stage-scoped check-refs -- so a checker not wired in is a
    # checker that never runs on a real run.
    run = _run_with_world_for_refs(tmp_path)
    write_json(run.batches, {
        "schema_version": "0.1", "round": 1, "cap_bytes": 28000,
        "bytes_per_scenario": 1600,
        "batches": [{"id": "b01", "hole_refs": ["cell:cap-9/nope"],
                     "projected_bytes": 1600}],
    })
    assert any("cap-9" in f.message for f in refs.check_all(run))
```

Add a `_run_with_world_for_refs(tmp_path)` helper to that module if one does not already exist, writing the same minimal world model `tests/unit/test_rounds_cli.py::_minimal` writes; if the module already has an equivalent, reuse it rather than adding a second.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_refs.py -k "check_batches or scenario_parts or score_parts or check_all_runs_the_new" -v`
Expected: FAIL, `AttributeError: module 'rubrica.refs' has no attribute 'check_batches'`.

- [ ] **Step 3: Implement the three checkers**

Add to `src/rubrica/refs.py`, following the shape every checker in that module already uses (`_load` for the artifact, an inner `report(pointer, message)` closure that anchors findings on the right path, and an early `return []` when an input is absent so a run someone is still building reports nothing):

- `check_batches(run)` — over `run.batches`: recompute each batch's `projected_bytes` as `len(hole_refs) * bytes_per_scenario` and report a mismatch; report `projected_bytes > cap_bytes`; report a `hole_refs` entry that does not name a cell or goal the world model declares, resolving `cell:<cap>/<oc>` against `_cells(world)` and `goal:<id>` against the goal ids; report a ref appearing in more than one batch, and a duplicate ref within one batch. Anchor every finding on `run.batches`.
- `check_scenario_parts(run)` — for each round in `run.scenario_part_rounds()`, read `run.batches` for the batch roster and report a batch with no part file, a part whose `batch_id` disagrees with its filename, a part name that is not a safe segment, and — the check that makes the partition enforceable — any scenario whose `goal_id` or `capability_refs` resolve to a hole ref assigned to a *different* batch. Report the offending scenario id and the batch that owns the ref, so the message names both. Anchor findings on the part path, never on `run.scenarios`.
- `check_score_parts(run)` — for each `03-score/round-N.json`: report a ruling naming a scenario absent from `run.scenarios`, and a `duplicate_of` that names a scenario which is itself `duplicate` or `rejected` in the sealed document, or that names the ruling's own `scenario_id`. Anchor findings on the score part path.

Then add all three to `check_all` in pipeline order — after `check_world_model` and before `check_scenarios` — so a run that has batches gets them checked. `check_all` runs every checker the run has inputs for, so a checker left out of it is a checker that never runs on a real run.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_refs.py -v`
Expected: PASS. Then `make test` and `make check`.

- [ ] **Step 5: Commit**

```bash
git add src/rubrica/refs.py tests/unit/test_refs.py
git commit -S -s -m "feat: Check the batches and the round parts at layer 2

The own-batch-only check is the one here that overlaps no other layer, and it is
what makes the partition enforceable rather than merely instructed: a member
that wandered into a sibling's holes produces a document byte-identical to one
that did not, so no schema and no digest can see it. Mirrors the triage seal's
refusal on a disposition naming a candidate outside its own slice.

check_scenario_parts and check_score_parts report every missing slice from the
moment their directory exists, so they run only once the fan-out has finished --
the property check_verdicts and check_contradiction_parts already have.

Wired into check_all, because a checker left out of it never runs on a real run.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---
### Task 8: Cutover — the stage list, the fixture, and every document that describes the pipeline

This is the one task that cannot be split: `paths.STAGES` is simultaneously the ordering, the on-disk numbering, and the input to both generated diagrams and three documents, and `validate.STAGE_ARTIFACTS` changing `propose` from `scenarios` to `scenarios-part` breaks `tests/toy.py` the moment it lands. Everything that reads `STAGES` moves in one commit, and the suite is the proof it moved consistently.

**Files:**
- Modify: `src/rubrica/paths.py`, `src/rubrica/validate.py`, `tests/toy.py`, `scripts/render-pipeline-diagram.py`, `scripts/render-readme-diagram.py`, `docs/concepts/pipeline.md`, `CLAUDE.md`
- Regenerate: `docs/concepts/pipeline-diagram.html`, `docs/assets/how-it-works.svg`, `docs/assets/how-it-works-dark.svg`

**Interfaces:**
- Consumes: everything from Tasks 1–7.
- Produces: stages `propose-batches`, `propose`, `propose-seal`, `score`, `score-seal`; `STAGE_ARTIFACTS` entries for each; `build_toy_run(..., upto=...)` accepting the new checkpoints.

- [ ] **Step 1: Extend `paths.STAGES`**

Replace the `"propose", "score",` lines with the five, and carry a comment in the register's own idiom explaining the ordering, as the triage and reconcile families already do:

```python
    # The propose/score loop, engineered as substeps for the reason the triage
    # and reconcile families are. propose-batches and both seals are code, so
    # they carry no skill and no manifest.stages entry, and their absence there
    # is not a finding.
    #
    # The two seals sort after the passes they seal, and propose-seal sorts
    # before score because score reads 02-scenarios.json: this tuple is the
    # documentation of that ordering, and placing either seal earlier would draw
    # both generated diagrams with a seal running before its own inputs.
    #
    # Stages 02a through 03b are a loop bounded by max_rounds, and the whole
    # loop repeats -- not just propose and score. score-seal computes the
    # coverage verdict's document; only the orchestrator acts on the verdict.
    "propose-batches",
    "propose",
    "propose-seal",
    "score",
    "score-seal",
```

- [ ] **Step 2: Extend `validate.STAGE_ARTIFACTS`**

```python
    "propose-batches": ("batches",),
    # propose now writes only its own batch's part. The stage that produces the
    # accumulating 02-scenarios.json is propose-seal, which is code.
    "propose": ("scenarios-part",),
    "propose-seal": ("scenarios",),
    # score writes only what it decides; the matrices and the report around them
    # are score-seal's, which is why the "coverage" kind moved off this row.
    "score": ("score-part",),
    "score-seal": ("coverage",),
```

Check how `validate` resolves a per-slice artifact kind for the existing fan-out stages (`extract` → `claims`, `reconcile-contradict` → `contradictions-part`) and make `scenarios-part` and `score-part` resolve the same way; those two are per-round as well as per-slice, so if the existing mechanism assumes a single directory, extend it to take the round rather than special-casing these stages.

- [ ] **Step 3: Run the suite to see exactly what the cutover breaks**

Run: `make test`
Expected: FAIL. The failures are the guard working, and they are the worklist for the rest of this task. Expect them in `tests/unit/test_docs_accuracy.py` (pipeline.md ordering, both diagram renders, the CLAUDE.md stage table), and in every test that builds a toy run through `propose` or `score`.

- [ ] **Step 4: Move the toy fixture**

In `tests/toy.py`, `build_toy_run` must now write the propose parts and the score part rather than `02-scenarios.json` and `03-coverage/*` directly, and then reach the sealed documents by calling `rounds.seal_scenarios` and `rounds.seal_score` — not by hand-writing them. Hand-writing the sealed documents would make the fixture able to disagree with the seal, and the fixture is the model answer a skill imitates.

Add to `_UPTO_STAGES`, replacing `"propose", "score",`:

```python
    # Four checkpoints across the loop rather than five: "propose" is every part
    # written with nothing sealed -- the state check_scenario_parts and the
    # part schemas are tested against -- and "propose-seal" is the assembled
    # scenario list score reads. "score" is the judgments with no report yet,
    # and "score-seal" is the coverage document every later stage and gate 2
    # read. "propose-batches" gets no checkpoint: nothing stops there, and a
    # checkpoint nobody stops at is a helper this module already has too many
    # requests for.
    "propose",
    "propose-seal",
    "score",
    "score-seal",
```

Keep `SIDS` and `ALL_SCENARIO_IDS` meaning exactly what they mean today — `SIDS` the four instantiated scenarios, `ALL_SCENARIO_IDS` including the folded duplicate. The fold now arrives as a ruling in the score part rather than as a status written into the scenario, and the sealed document must come out identical to what it is today. **Assert that**: before changing the fixture, capture the current `02-scenarios.json` and `03-coverage/latest.json` bytes from a toy run into `/tmp`, and after the change confirm the sealed files are byte-identical. If they differ, the fixture changed the golden world rather than the route to it, and that is a defect in this task, not an improvement.

- [ ] **Step 5: Update both diagram tables and re-render**

`scripts/render-pipeline-diagram.py`: add a `ROWS` entry per new stage, with the dir column reading `02a`, `02b`, `02c`, `03a`, `03b`. Then:

```bash
uv run python scripts/render-pipeline-diagram.py
uv run python scripts/render-readme-diagram.py
```

`scripts/render-readme-diagram.py`: `PHASES` must partition `paths.STAGES` in order, so add all five names to the phase that already holds `propose` and `score`. Which phase a stage belongs to is editorial and no test can rule on it — the two seals and the batcher belong with the loop they serve, not in a new phase, because the README diagram's whole job is the newcomer's altitude and a batcher is not a concept a newcomer needs.

Never hand-edit either output: both are byte-compared against a fresh render.

- [ ] **Step 6: Update the three documents**

- `docs/concepts/pipeline.md`: every stage named in `STAGES` order, with the loop's five stages described as one logical step. Say which are code and which carry a skill.
- `CLAUDE.md`: the stage table gains five rows (`02a`–`03b`); the "one architectural rule" fan-out paragraph gains `batch_id` as a third slice-id kind alongside `artifact_id`, `subject_id` and `scenario_id`; the list of code stages (`intake`, `smoke`, `survey`, `triage-slices`, `triage-seal`, `reconcile-seal`) gains `propose-batches`, `propose-seal` and `score-seal`; and the sentence "Stages 02 and 03 are a loop bounded by `max_rounds`. Score *computes* the coverage verdict" needs the verdict clause kept and the stage numbers updated — score still computes the verdict, and `score-seal` composes the document that carries it.
- `CLAUDE.md` is **not** ruff-excluded, so run `make check` after editing it.

- [ ] **Step 7: Run everything**

Run: `make test && make check && uv run rubrica check-skills`
Expected: all green, exit 0. `check-skills` will still pass here because the skills' contracts are untouched until Task 9 — if it fails now, a contract already names something this task renamed, and that is the signal to bring Task 9's contract edit forward rather than to weaken the check.

- [ ] **Step 8: Commit**

```bash
git add src/rubrica/paths.py src/rubrica/validate.py tests/toy.py scripts/ docs/ CLAUDE.md
git commit -S -s -m "feat: Cut the pipeline over to the five-stage propose/score loop

One commit because paths.STAGES is simultaneously the ordering, the on-disk
numbering, the input to both generated diagrams and the subject of three
documents, and STAGE_ARTIFACTS moving propose to scenarios-part breaks the toy
fixture the moment it lands. The suite is the proof it all moved together.

The toy fixture now writes parts and reaches the sealed documents through
rounds.seal_scenarios and rounds.seal_score rather than hand-writing them: a
fixture that hand-writes a sealed document can disagree with the seal, and this
fixture is the model answer a skill imitates. Its sealed bytes are unchanged --
the route to the golden world moved, the golden world did not.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 9: The skills

**Read first:** `CLAUDE.md`'s "Testing prompts: the traps that actually recur here". `skills.load()` sets `body` to the entire file text and all five section headings are mandatory, so `"refusal" in body.lower()` is vacuous for every conforming skill. Scope every assertion with `skills.section_body(skill, "<heading>")` and assert co-occurrence *within* that section.

**Files:**
- Modify: `src/rubrica/skills/rb-propose/SKILL.md`, `src/rubrica/skills/rb-score/SKILL.md`, `src/rubrica/skills/rb-orchestrate/SKILL.md`
- Create: `src/rubrica/skills/rb-propose/SUPERSEDED.md`, `src/rubrica/skills/rb-score/SUPERSEDED.md`
- Test: `tests/unit/test_skills_prose.py` (or whichever module already holds the prose predicates)

- [ ] **Step 1: Rewrite `rb-propose`'s contract and all five sections**

```toml
stage = "propose"
reads = ["manifest", "world_model", "batches", "coverage_latest"]
writes = ["scenario_part"]
schemas = ["scenarios-part"]
invokes = ["validate"]
```

The prose changes, section by section:

1. **Inputs** — the member is dispatched with a `batch_id`. It reads `02-batches.json`, finds its own batch, and takes that batch's `hole_refs` as its entire worklist. It reads `coverage_latest` for each hole's `reason` and context, and the world model for the frozen id lists. **It no longer reads `02-scenarios.json` at all**, and the section must say why rather than merely omitting it: a `not_yet_attempted` hole is by definition one no scenario covers, and `rb-score` folds anything that slips, so a member needs neither to read nor to write the accumulating document. Say plainly that another batch's holes are not this member's work, naming the sibling-blindness the way `rb-reconcile-contradict`'s Inputs does.
2. **Output** — one `scenarios-part-0.1.json`-shaped document at `02-scenarios/round-N/<batch_id>.json`, carrying only the scenarios this member wrote. Every scenario id must be prefixed `sc-<batch_id>-` so two members cannot collide; `propose-seal` refuses a collision, so a member that ignores this costs the whole round. Every scenario still starts `status: "proposed"` and nothing else.
3. **Method** — keep every judgment step verbatim where it survives: the four hole reasons and which one is closable, the absence-and-error-shaped-outcome paragraph, the `discriminating_fact` uniqueness requirement, and the "start from an actual open cell, never from what a good test suite generally has" warning. The step that changes is the old step 3 (read the existing scenarios and append, never rewrite) — it becomes "write only your own batch, and never a file outside `02-scenarios/round-N/`". Keep step 4's instruction to take **every** closable hole in the batch: it is now safe, because the batch is bounded, and it is the instruction that stops a member cherry-picking the easy `success` cells.
4. **Invariants** — the `max_scenarios` and `max_rounds` invariants stay. Add: every scenario's `capability_refs` and `goal_id` resolve to a hole ref in **this** batch (`refs.check_scenario_parts` enforces it), and the `batch_id` in the document matches the member's own.
5. **Refusal conditions** — keep all four. Each must still name a trigger the member can detect from what it reads and an action it can take; a hole it cannot state a unique `discriminating_fact` for is still refusal condition 4, and the member now records that by writing a part with fewer scenarios than its batch has holes, which is a real record rather than a silent gap.

- [ ] **Step 2: Rewrite `rb-score`'s contract and sections**

```toml
stage = "score"
reads = ["manifest", "world_model", "scenarios"]
writes = ["score_part"]
schemas = ["score-part"]
invokes = ["dedupe-candidates", "validate"]
```

`check-refs` leaves `invokes`: a score part alone cannot be checked against a coverage document that `score-seal` has not composed yet, and a member invoking a checker that reports on artifacts it has not produced is the shape that generated fabricated findings before. The prose changes:

- **Output** — one `score-part-0.1.json` document. Delete the "written twice ... with identical content" paragraph and the `mkdir` warning attached to it: `score-seal` creates `03-coverage/` in code. Delete the matrix-construction requirement from Output and **keep Method steps 4, 5 and 6 as a statement of what `score-seal` will compute**, reframed so score knows which rows will come out uncovered and can therefore justify them — it still has to do the reasoning, it just no longer transcribes the result. Say why in one sentence, because a stage told to stop writing something it used to write will otherwise read as a demotion: the arithmetic was never judgment, `refs._check_matrix_arithmetic` already recomputed it, and what is left in this part is judgment only.
- **Invariants** — the both-directions hole rule becomes load-bearing here, since `score-seal` refuses on it: every row the matrices will show uncovered has exactly one hole, and no hole names a row they will show covered.
- **Refusal conditions** — unchanged in substance.

- [ ] **Step 3: Update `rb-orchestrate`**

Its `reads` gains `batches`; its `invokes` gains `propose-batches`, `propose-seal` and `score-seal`. Its loop step becomes: run `propose-batches`; if it reports no closable holes, the loop is over; otherwise dispatch one `propose` member per batch id, **at most three concurrently** (the shared LiteLLM gateway degrades on concurrent streaming requests that each generate substantial output — measured clean at 1–3, 60–90s mid-stream stalls at 5, envoy 503 at 6+); run `check-refs` only once every member has landed; run `propose-seal`; dispatch `score`; run `score-seal`; then act on the verdict. The two sanctioned appends are unchanged, and a batch id is an address, not context — never pass a member a sibling's batch id or any batch's contents.

- [ ] **Step 4: Write the two `SUPERSEDED.md` files**

Follow `src/rubrica/skills/rb-reconcile/SUPERSEDED.md` exactly in intent. Each says: which stage shape the neighbouring `exercise.md` recorded, that the shape no longer exists, that the record was deliberately **not** relocated or rewritten because doing so would assert that a dispatch of the new shape did what the old one actually did, and that the new shape therefore has no behavioural evidence yet. Name the run and the figures for `rb-propose`: `run-20260825-094033`, round 1 succeeded at 18 scenarios / $2.69 / 23 minutes, round 2 failed at the output cap having written nothing for $3.57.

- [ ] **Step 5: Write the prose predicates, and measure each in both directions**

Add tests asserting, scoped with `skills.section_body`:

```python
def test_propose_says_why_it_no_longer_reads_the_scenario_list():
    section = section_body(load_skill("rb-propose"), "1. Inputs")
    lowered = section.lower()
    assert "02-scenarios.json" in section
    assert "not_yet_attempted" in lowered
    # Co-occurrence within the section that owns the rule, never presence
    # anywhere in the file: the frontmatter description and the contract block
    # both satisfy a naive substring check.
    assert "fold" in lowered or "duplicate" in lowered


def test_score_says_the_matrices_are_computed_rather_than_written():
    section = section_body(load_skill("rb-score"), "2. Output")
    lowered = section.lower()
    assert "score-seal" in lowered
    assert "capability_matrix" in section and "goal_matrix" in section
    assert "written twice" not in lowered


def test_propose_requires_the_batch_prefixed_scenario_id():
    section = section_body(load_skill("rb-propose"), "2. Output")
    assert "sc-<batch_id>-" in section
```

**For each predicate, measure both directions before committing it** — this is not optional, and roughly nineteen assertions in this repo were measured satisfiable by unrelated content:

```bash
cp -r src/rubrica/skills /tmp/skills-probe
# Blank the prose the predicate claims to check, then confirm the test goes RED:
RUBRICA_SKILLS_DIR=/tmp/skills-probe uv run pytest tests/unit/test_skills_prose.py -k <name> -v
# Reword that prose meaning-preservingly, then confirm it stays GREEN:
RUBRICA_SKILLS_DIR=/tmp/skills-probe uv run pytest tests/unit/test_skills_prose.py -k <name> -v
```

A predicate that stays green when the prose is blanked is not a guard; a predicate that goes red on an innocuous reword is a phrase pin, which has already broken this repo once on a reformat. Delete or rewrite either.

- [ ] **Step 6: Run the gates**

Run: `uv run rubrica check-skills && make test && make check`
Expected: `check-skills` exit 0 — it holds every contract to `paths.RunPaths` attribute names, `validate.STAGE_ARTIFACTS` and `cli.SUBCOMMANDS`, so `reads = [... "batches"]` and `writes = ["scenario_part"]` only pass because Tasks 1, 2 and 6 named them. Remember what it does *not* check: whether the `reads` set is *right*. Read the two rewritten skills once more for that.

- [ ] **Step 7: Commit**

```bash
git add src/rubrica/skills/ tests/unit/test_skills_prose.py
git commit -S -s -m "feat: Rewrite rb-propose as a batch member and rb-score as judgments only

rb-propose loses scenarios from both sides of its contract. The Inputs section
says why rather than merely omitting it: a not_yet_attempted hole is one no
scenario covers, and score folds what slips, so a member needs neither to read
nor to write the accumulating document. Scenario ids are batch-prefixed because
members mint their own and propose-seal refuses a collision.

rb-score keeps Method steps 4-6 as what score-seal will compute, so it still
does the reasoning that tells it which rows are uncovered -- it just stops
transcribing the result. check-refs leaves its invokes: a score part cannot be
checked against a coverage document that does not exist yet, and a stage
invoking a checker over artifacts it has not produced is what generated
fabricated findings before.

Both exercise.md files stay where they are with a SUPERSEDED.md beside them,
per the rb-reconcile precedent: relocating one would assert that a dispatch of
the new shape did what the old one actually did.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---
### Task 10: The harness — declare the output cap, stop destroying transcripts

**Files:**
- Modify: `scripts/dispatch-stage.sh`
- Test: `tests/unit/test_dispatch_harness.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `CLAUDE_CODE_MAX_OUTPUT_TOKENS` exported by the dispatch script; transcripts that never overwrite a prior attempt.

**The measurement this task owes, before a number is written:** `CLAUDE_CODE_MAX_OUTPUT_TOKENS` appears nowhere in this repository and is unset in the environment (verified 2026-08-26), so the 32,000 that killed round 2 is Claude Code's own default for the process this script spawns. The effective cap is presumably `min(env var, model max)` and **neither term is established here**. Do not carry the API documentation's 128K sonnet figure into the script as though it had been observed through Claude Code.

- [ ] **Step 1: Measure the ceiling**

Pick any run directory and a stage whose write is large, set the var high, and see what the harness actually enforces:

```bash
RUBRICA_LAB=/tmp/cap-probe CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000 \
  RUBRICA_PRINT_SETTINGS=1 ./scripts/dispatch-stage.sh propose "$RUN"
```

`RUBRICA_PRINT_SETTINGS=1` writes the settings and the prompt and dispatches nothing, so this first call costs nothing and confirms the plumbing. Then one real dispatch at that value against a corpus whose round would exceed 32,000, and read the result: either it completes, which establishes the value is honoured, or it fails at a number, which establishes the real ceiling. **Record whichever happened in `decisions.md` with the value used**, then write that number into the script. One dispatch, one fact.

- [ ] **Step 2: Write the failing tests**

Append to `tests/unit/test_dispatch_harness.py`:

```python
def test_the_dispatch_declares_the_output_token_cap():
    # The round loop's viability depended on a default belonging to another
    # tool: unset in the environment and absent from this repository, so the
    # value a run actually ran under was not recoverable afterwards.
    script = (REPO_ROOT / "scripts" / "dispatch-stage.sh").read_text(encoding="utf-8")
    assert "CLAUDE_CODE_MAX_OUTPUT_TOKENS" in script
    assert "export CLAUDE_CODE_MAX_OUTPUT_TOKENS" in script


def test_the_output_token_cap_is_overridable_from_the_environment():
    # Same shape as RUBRICA_MODEL and RUBRICA_BUDGET: a default in the script,
    # overridable per dispatch, so a probe does not need the file edited.
    script = (REPO_ROOT / "scripts" / "dispatch-stage.sh").read_text(encoding="utf-8")
    assert "${CLAUDE_CODE_MAX_OUTPUT_TOKENS:-" in script


def test_a_re_dispatch_does_not_overwrite_the_earlier_transcript(tmp_path):
    # MEASURED consequence, not a hypothetical: transcripts are named by stage,
    # so propose round 2 overwrote round 1's and destroyed the only per-attempt
    # evidence for the failure that motivated this whole change.
    lab = tmp_path / "lab"
    (lab / "transcripts").mkdir(parents=True)
    existing = lab / "transcripts" / "propose.jsonl"
    existing.write_text("round one\n", encoding="utf-8")
    # Drive the script's own naming logic rather than reimplementing it here.
    chosen = _transcript_path_for(lab, stage="propose", slice_id="")
    assert chosen != existing
    assert existing.read_text(encoding="utf-8") == "round one\n"
```

`_transcript_path_for` must exercise the script rather than restate its rule — a test that restates the rule passes when the rule is present and unreachable. Add a `RUBRICA_PRINT_TRANSCRIPT=1` mode to the script that prints the transcript path it would use and dispatches nothing, in the exact style of the existing `RUBRICA_PRINT_SETTINGS=1` block and for the same stated reason, then have the helper shell out to it.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_dispatch_harness.py -k "output_token or earlier_transcript" -v`
Expected: FAIL — the string is absent and the collision helper does not exist.

- [ ] **Step 4: Edit the script**

Beside the existing `PATH` export, with a comment in the file's own measured idiom recording the number from Step 1, where it came from, and that the value is a Claude Code default this project now pins rather than a model limit:

```bash
export CLAUDE_CODE_MAX_OUTPUT_TOKENS="${CLAUDE_CODE_MAX_OUTPUT_TOKENS:-<measured value>}"
```

Replace the transcript line so a second attempt never lands on the first's path:

```bash
TRANSCRIPT="$LAB/transcripts/$STAGE${SLICE:+-$SLICE}.jsonl"
# Never overwrite a prior attempt. MEASURED cost of the previous behaviour:
# propose round 2's transcript overwrote round 1's on run-20260825-094033,
# destroying the only per-attempt record of the failure that motivated the
# bounded-batch change -- and for propose the round is exactly what a reader
# needs to tell two attempts apart. The script does not know the round and does
# not need to: "do not destroy the prior attempt" is the whole requirement.
if [ -e "$TRANSCRIPT" ]; then
  n=2
  while [ -e "$LAB/transcripts/$STAGE${SLICE:+-$SLICE}-$n.jsonl" ]; do
    n=$((n + 1))
  done
  TRANSCRIPT="$LAB/transcripts/$STAGE${SLICE:+-$SLICE}-$n.jsonl"
fi
```

Add the `RUBRICA_PRINT_TRANSCRIPT` block and document both new variables in the script's `# Environment:` header, where every other one is already listed.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_dispatch_harness.py -v`
Expected: PASS. Then `make test` and `make check`.

- [ ] **Step 6: Commit**

```bash
git add scripts/dispatch-stage.sh tests/unit/test_dispatch_harness.py
git commit -S -s -m "fix: Declare the output token cap and stop overwriting transcripts

CLAUDE_CODE_MAX_OUTPUT_TOKENS appeared nowhere in this repository and was unset
in the environment, so the 32,000 that killed propose round 2 was Claude Code's
own default for the process this script spawns -- an undeclared dependency of
the round loop, and the value a run ran under was not recoverable afterwards.
The number written here was measured through the harness rather than taken from
the API's model ceiling, which is a different number in a different layer.

The transcript fix is the smaller finding from the same failure: naming
transcripts by stage meant propose round 2 overwrote round 1's and destroyed the
only per-attempt evidence for the defect that motivated this change.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 11: The limitations entry, and the end-to-end check

**Files:**
- Modify: `docs/design/limitations.md`
- Test: the three gates, plus one real dispatch if a corpus is available.

- [ ] **Step 1: Write the register entry**

Add an entry in the register's own idiom — what is wrong, the measured figures, and the ruling that parked it. It must record all four of these, because each is a thing the next person would otherwise re-derive:

1. **What was fixed and what the binding term actually was.** Round 2 on `run-20260825-094033` projected ~124,545 bytes (~35,600 tokens) against a 32,000 cap; the accumulated re-emit was 24,613 of those bytes, 20%, and the round's own batch was the rest. The comparison run `20260823-112746` cleared round 2 with 4 closable holes against 86, its round-1 file only 1.4× smaller. Anyone reaching for "just append incrementally" is reaching for the 20%.
2. **What is still unbounded.** `rb-score`'s hole justifications: one per uncovered row, measured 35,773 bytes (~10k tokens) at 170 denominator rows, down from the ~147 KB a score dispatch emitted before. Still linear in the denominator. A target roughly 3× this one re-approaches the cap. **The ruling:** left linear deliberately — a hole's `reason` and `justification` are judgment and cannot move to code, and bounding them would mean sharding score, which would break the barrier property that lets it fold duplicates at all.
3. **That the harness cap is now declared but was a default.** With the measured value from Task 10 and the note that the effective ceiling is `min(env var, model max)`.
4. **That neither `rb-propose` nor `rb-score` has behavioural evidence for its new shape.** Both `exercise.md` files record the superseded shape and carry a `SUPERSEDED.md` saying so. This joins the `reconcile-*` and `triage-*` families in the same condition, and the register already names those — say that this now covers the propose/score loop too, so the count of stages without behavioural evidence is not something a reader has to assemble from three places.

Do not write a test count anywhere in the entry, and do not give it a heading that counts something that grows.

- [ ] **Step 2: Run the three gates**

```bash
make test && make check && uv run rubrica check-skills
```

Expected: green, clean, exit 0.

- [ ] **Step 3: Re-verify both generated drawings**

```bash
uv run python scripts/render-pipeline-diagram.py --check
uv run python scripts/render-readme-diagram.py --check
```

Expected: no diff. A failure here means a committed drawing was hand-edited or a stage was added without a row.

- [ ] **Step 4: Exercise the exit-code contract deliberately**

For each of `propose-batches`, `propose-seal` and `score-seal`, confirm by hand that the unreadable-input paths exit `2` and never `1`, and that no exit `1` produces empty stdout:

```bash
RUN=$(mktemp -d)
uv run rubrica propose-seal --run "$RUN"; echo "exit $?"        # 2: no run
chmod 000 "$RUN"; uv run rubrica propose-seal --run "$RUN"; echo "exit $?"  # 2
chmod 755 "$RUN"
RUBRICA_SCHEMA_DIR=/nonexistent uv run rubrica validate --stage propose --run "$RUN"; echo "exit $?"  # 2
```

- [ ] **Step 5: If a corpus is available, run one real round**

The toy fixture cannot reach this defect class — re-emitting its scenario set was always cheap — so the only end-to-end evidence is a real corpus whose denominator produces more closable holes than one response can hold. `run-20260825-094033`'s world model is on disk and has 170 denominator rows and 86 closable holes, which is exactly the failing case. Running `propose-batches` against it costs nothing and should produce 6 batches; that alone verifies the partition against the measurement without dispatching anything.

**`runs/` is gitignored, so it does not exist in a worktree** — verified when this plan's own worktree came up with `tests/unit/test_sizing.py:64` newly skipped for exactly that reason. Reach the run by absolute path in the main checkout instead of a relative one:

```bash
RUN=/home/bnayahu/work/kaegis/rubrica/runs/run-20260825-094033
uv run rubrica propose-batches --run "$RUN" --round 2
python3 -c "
import json, os
d = json.load(open(os.environ['RUN'] + '/02-batches.json'))
print(len(d['batches']), 'batches', [len(b['hole_refs']) for b in d['batches']])
print('max projection', max(b['projected_bytes'] for b in d['batches']), 'cap', d['cap_bytes'])"
```

Expected: 6 batches, none projecting over `cap_bytes`.

Two cautions. This **writes** `02-batches.json` into a historical run whose artifacts are the evidence behind this whole change, so copy the run to a scratch directory first and probe the copy — the numbers are identical and the original stays untouched. And **do not commit any run directory**: `runs/` is gitignored for this reason.

If that run is not on the machine, the partition is still covered by `test_the_partition_keeps_every_batch_inside_the_budget` in Task 3, which asserts the same 86-holes-to-6-batches case from the measurement. Say which of the two was actually run — a synthetic test passing is not evidence about the real world model, and the sizing test's own skip message makes exactly that distinction.

- [ ] **Step 6: Commit**

```bash
git add docs/design/limitations.md
git commit -S -s -m "docs: Register what the bounded loop fixed and what stays linear

Records the binding term, because the issue got it wrong and the next reader
would too: round 2's re-emit was 20% of its projected output and the round's own
batch was the rest, which is why appending incrementally was not the fix.

Records the residual honestly. Score's hole justifications stay linear in the
denominator -- 35,773 bytes at 170 rows, down from ~147KB per dispatch -- and a
target roughly 3x this one re-approaches the cap. Left linear deliberately: a
hole's reason is judgment, and bounding it would mean sharding score and
breaking the barrier that lets it fold duplicates.

Also records that neither rb-propose nor rb-score has behavioural evidence for
its new shape, which puts the propose/score loop in the same condition the
register already names for the reconcile and triage families.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Notes for whoever executes this

**The three things most likely to go wrong, in order:**

1. **Task 8 is where a partial job hides.** `paths.STAGES` feeds two generated drawings, three documents and `STAGE_ARTIFACTS`; the suite catches every one of those, so trust the failures as the worklist and do not weaken an assertion to get past it. The one thing the suite cannot catch is the toy fixture changing the golden world rather than the route to it — that is what the byte-comparison in Step 4 is for, and skipping it is how a defect gets taught to a skill.
2. **The `reads` sets in Task 9 are not checked by anything.** `check-skills` validates the *names*, never whether the set is *right*. A `reads` list can be complete, over-broad, or missing something the prose needs, and only reading catches it. Before raising a finding against either rewritten skill's output later, check what its `reads` actually gives it: a finding that requires knowledge outside the contract is a finding against the contract or the fixture, never against the prompt.
3. **Do not re-litigate the design mid-implementation.** `docs/design/limitations.md` is the register of what is known wrong, and re-litigating a parked ruling has cost this project two fix rounds. The spec's section 9 lists what was already considered and rejected here, with the measurement for each.

**On the gateway:** when the propose fan-out is dispatched for real, cap it at three concurrent members. Measured on this shared LiteLLM gateway: clean at 1–3, 60–90s mid-stream stalls at 5, envoy `503 upstream connect error` at 6+. The symptom to recognise is retries logged with **no HTTP status** (`error_status: null`) rather than `429` — that is a stalled stream, not a rate limit, and raising the retry budget hides it instead of fixing it.
