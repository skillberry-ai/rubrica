# Ingestion and Triage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the phase that runs before `intake` — inventory a corpus, rule on
it against a declared objective, explode containers, record every decline — so a
run's input selection is an artifact rather than a conversation.

**Architecture:** Two new stages at the front of `paths.STAGES`. `survey` (code)
walks a corpus and writes `00-catalogue.json`, one bounded digest per candidate.
`rb-triage` (a skill, barrier, reading *only* the catalogue) writes
`00-triage.json`: one disposition per candidate, the surfaces it found, the
deficiencies the admitted set cannot cover, and projection briefs for what needs
manufacturing. A human holds gate 0. Then `intake --run` materialises the
admitted candidates and writes `manifest.json` exactly as it does today.

**Tech Stack:** Python 3.13, `uv`, `pytest`, `jsonschema` (Draft 2020-12), `ruff`.

**Spec:** `docs/superpowers/specs/2026-08-14-ingestion-and-triage-design.md` —
read it first. This plan argues from it and does not restate its reasoning.

**Why tonight:** a fresh autonomous parsec run follows this build. The corpus is
restored at `/tmp/parsec` (262 files; a 6MB, 130-element MLflow capture). Phases
0–3 are what the run needs to execute; phase 4 is what the human needs to hold
gate 0, so it is not optional this time.

## Global Constraints

- **Every commit signed and DCO'd: `git commit -S -s`.** If signing fails, stop
  and report it. Never fall back to unsigned.
- Attribution trailer is `Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>`.
  Never `Co-Authored-By` or `Made-with`.
- **Baseline before this plan: 1173 passed, 4 skipped**; `make check` clean;
  `uv run rubrica check-skills` exits 0. Every task ends with these green, with
  its own new tests added to the count.
- ruff: `line-length = 100`, `select = ["E","F","I","UP","B","SIM"]`. `docs/` is
  excluded; `README.md` is **not**.
- **The exit-code contract is load-bearing.** `0` clean; `1` findings, one per
  line on stdout, never with empty stdout; `2` usage error or an
  unreadable/misconfigured run. A stage defect must never surface as `2`.
- **Comment density here is high and deliberate.** Comments explain *why*,
  usually citing a measurement. Match that; do not strip existing ones.
- **Never deny or omit a path `check-refs` reads.** `refs._readable_targets` and
  `test_nothing_check_refs_reads_is_ever_denied` both exist because denying one
  made a stage's own gate fabricate findings.
- **Measure every text-level predicate in both directions** before committing
  it: blank the prose it checks in a `/tmp` copy under `RUBRICA_SKILLS_DIR`,
  confirm red; reword it meaning-preservingly, confirm green. Scope assertions
  with `skills.section_body`, never `in skill.body`.
- Four env overrides exist and are fair game in tests: `RUBRICA_SCHEMA_DIR`,
  `RUBRICA_SKILLS_DIR`, `RUBRICA_SUITE_DIR`, `RUBRICA_LIVE`.

## File Structure

**New modules** — each one unit with one responsibility, because `refs.py` at
1436 lines is already the file in this repo that is hardest to hold in context
and nothing here should grow it further than the three checkers it must gain.

| File | Responsibility |
|---|---|
| `src/rubrica/survey.py` | Mint the run; walk and exclude; explode containers; assemble the catalogue |
| `src/rubrica/digest.py` | One bounded digest per candidate, by kind. Split from `survey.py` because §5.3 is the design's riskiest surface and deserves its own test file |
| `src/rubrica/triage.py` | Read the triage record; resolve admitted candidates; projection acceptance checks; `adopt_projection` |
| `src/rubrica/sizing.py` | The implied-suite-size arithmetic (§9) |
| `src/rubrica/brief.py` | The `gate-brief` composer (§11) |
| `src/rubrica/schema/catalogue-0.1.json` | Layer-1 schema for the catalogue |
| `src/rubrica/schema/triage-0.1.json` | Layer-1 schema for the triage record |
| `src/rubrica/skills/rb-triage/SKILL.md` | The ninth skill |
| `src/rubrica/skills/rb-triage/exercise.md` | Written **after** tonight's dispatch, from what happened |

**Modified:** `paths.py` (STAGES, two RunPaths properties), `validate.py`
(ARTIFACT_SCHEMAS, STAGE_ARTIFACTS, `_artifact_paths`), `refs.py` (three
checkers, `_readable_targets`, `check_all`), `intake.py` (split mint/register,
add `admit_from_triage`), `cli.py` (four subcommands, `intake --run`),
`skills/rb-orchestrate/SKILL.md`, `docs/running-a-stage-by-hand.md`, `README.md`.

**New fixtures:** `tests/fixtures/corpus-toy/`,
`tests/fixtures/catalogue-unsupported-objective.json`,
`tests/fixtures/catalogue-all-declinable.json`.

---

# Phase 0 — The ceiling

Stands alone. Nothing else in this plan depends on it, and it removes the
default that forced the parsec run's hand-raise.

### Task 1: Raise the `max_scenarios` default to 128

**Files:**
- Modify: `src/rubrica/cli.py:120`
- Test: `tests/unit/test_cli.py:330`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing other tasks read. `intake()`'s library signature is
  unchanged — `max_scenarios` stays a required keyword argument there.

- [ ] **Step 1: Change the failing assertion first, so it fails**

In `tests/unit/test_cli.py`, replace line 330:

```python
    assert manifest["limits"] == {"max_rounds": 2, "max_scenarios": 128}
```

Then add this test immediately after that test function, which pins *why* the
number is what it is rather than only pinning the number:

```python
def test_the_scenario_default_is_a_ceiling_not_an_estimate():
    """128 is a blast-radius guard, not a suite size.

    refs.check_scenarios already reports a finding above max_scenarios and
    rb-propose already refuses at it, so the parameter was always a guard --
    a default of 8 just made it bind in normal operation, which is why the
    parsec run (docs/.../2026-08-13-parsec-full-run-design.md §10, error 4)
    had to raise it by hand and had the hand-raise read as a defect.
    """
    parser = cli._build_parser()
    args = parser.parse_args(
        ["intake", "--input", "x", "--runs-dir", "r", "--target-name", "t",
         "--target-interface", "i"]
    )
    assert args.max_scenarios == 128
    # Deliberately no schema maximum: a human who types 300 has asked for it.
    # The default protects the autonomous run that sets nothing.
    limits = validate.load_schema("manifest")["properties"]["limits"]
    assert "maximum" not in limits["properties"]["max_scenarios"]
```

If `validate` has no `load_schema` helper, read the schema with
`json.loads((validate.schema_dir() / "manifest-0.1.json").read_text())` instead
and drop the helper call.

- [ ] **Step 2: Run the tests to verify both fail**

```
uv run pytest tests/unit/test_cli.py -k "limits or ceiling" -v
```

Expected: FAIL — the first on `8 != 128`, the second on `args.max_scenarios == 8`.

- [ ] **Step 3: Change the default**

In `src/rubrica/cli.py`, in `_build_parser`:

```python
    # A ceiling, not an estimate of the right suite size: the point past which
    # no human reviews the output (128 Harbor packages) and a run costs on the
    # order of $200 at the parsec run's ~$1.66/scenario across instantiate and
    # challenge. It was 8, which made refs.check_scenarios' guard bind in normal
    # operation and forced a hand-raise on the first real target.
    p_intake.add_argument("--max-scenarios", type=int, default=128)
```

- [ ] **Step 4: Run the full suite**

```
uv run pytest -q && make check
```

Expected: PASS, one test more than baseline (1174 passed, 4 skipped). If any
other test fails, it was relying on the CLI default rather than passing
`max_scenarios` explicitly — fix it by passing the value it means, not by
reverting this.

- [ ] **Step 5: Commit**

```bash
git add src/rubrica/cli.py tests/unit/test_cli.py
git commit -S -s -m "feat: Make max_scenarios a ceiling at 128, not an estimate

refs.check_scenarios already reported a finding above the cap and rb-propose
already refused at it, so this was always a guard. The default of 8 made it
bind in normal operation, which is why the parsec run raised it by hand and why
the hand-raise was then read as an unexplained discrepancy.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

# Phase 1 — The catalogue

Ends usefully: a corpus becomes a reviewable inventory, and operations 1 and 3
of the spec's §1 stop being manual.

### Task 2: Stage names and run paths

**Files:**
- Modify: `src/rubrica/paths.py:17-27` (STAGES), and the singleton-artifact
  properties block around `src/rubrica/paths.py:120-140`
- Test: `tests/unit/test_paths.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `paths.STAGES` with `"survey"` and `"triage"` first;
  `RunPaths.catalogue -> Path` (`00-catalogue.json`) and
  `RunPaths.triage -> Path` (`00-triage.json`). Every later task uses these
  two names — `check-skills` holds `rb-triage`'s `reads` list against
  `RunPaths` attribute names, so `catalogue` is the exact string the skill
  contract must declare.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_paths.py`:

```python
def test_survey_and_triage_lead_the_stage_ordering():
    """STAGES is the pipeline order and the on-disk numbering.

    survey and triage are 00a and 00b, so they precede intake -- which is 00c
    and no longer the first thing that happens in a run.
    """
    assert paths.STAGES[:3] == ("survey", "triage", "intake")


def test_the_catalogue_and_triage_record_are_run_paths(tmp_path):
    """Both are 00-family singletons beside 00-inputs/.

    They are RunPaths properties rather than paths joined at a call site
    because check_contract resolves a skill's declared `reads` names against
    this class -- a literal path in a contract is a check-skills finding.
    """
    run = paths.RunPaths(tmp_path / "run-20260814-000000")
    assert run.catalogue == run.root / "00-catalogue.json"
    assert run.triage == run.root / "00-triage.json"
    assert run.catalogue.parent == run.inputs_dir.parent
```

- [ ] **Step 2: Run to verify they fail**

```
uv run pytest tests/unit/test_paths.py -k "survey_and_triage or catalogue_and_triage" -v
```

Expected: FAIL — `STAGES[:3]` is `("intake", "extract", "reconcile")`, and
`RunPaths` has no `catalogue` attribute.

- [ ] **Step 3: Implement**

In `src/rubrica/paths.py`, change `STAGES`:

```python
STAGES = (
    "survey",
    "triage",
    "intake",
    "extract",
    "reconcile",
    "propose",
    "score",
    "instantiate",
    "challenge",
    "emit",
    "smoke",
)
```

And add two properties beside `inputs_dir` in the singleton-artifact block:

```python
    @property
    def catalogue(self) -> Path:
        """Every candidate survey found, with one bounded digest each.

        In the 00 family beside 00-inputs/ because survey, triage and intake are
        00a, 00b and 00c -- the same relationship 01-claims/ and
        01-world-model.json already have.
        """
        return self.root / "00-catalogue.json"

    @property
    def triage(self) -> Path:
        """One disposition per candidate, plus deficiencies and projections."""
        return self.root / "00-triage.json"
```

- [ ] **Step 4: Run the full suite**

```
uv run pytest -q
```

Expected: PASS with two more than Task 1's count (1176). `test_cli.py`'s
`parametrize("command", sorted(subcommand_names()))` and the
`validate --stage` choices both read `STAGES`, so watch for a failure claiming
an unknown stage — that means Task 3's `STAGE_ARTIFACTS` entries are missing
and it is the next task, not a regression.

If `uv run pytest -q` fails inside `validate.validate_stage` with
`KeyError: 'survey'`, that is expected at this point only if a test iterates
every stage. Note which test, and confirm it passes at the end of Task 3.

- [ ] **Step 5: Commit**

```bash
git add src/rubrica/paths.py tests/unit/test_paths.py
git commit -S -s -m "feat: Add survey and triage stages and their two run paths

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

### Task 3: The catalogue schema and its layer-1 wiring

**Files:**
- Create: `src/rubrica/schema/catalogue-0.1.json`
- Modify: `src/rubrica/validate.py:34-50` (ARTIFACT_SCHEMAS),
  `src/rubrica/validate.py:63-73` (STAGE_ARTIFACTS),
  `src/rubrica/validate.py:161-198` (`_artifact_paths`)
- Test: `tests/unit/test_schemas_catalogue.py` (new)

**Interfaces:**
- Consumes: `RunPaths.catalogue` from Task 2.
- Produces: artifact kind `"catalogue"` → `catalogue-0.1.json`;
  `STAGE_ARTIFACTS["survey"] == ("catalogue",)`. Tasks 4–8 write documents
  that must satisfy this schema. The candidate shape defined here is the
  contract `rb-triage` reads, so the field names are load-bearing for Task 11.

- [ ] **Step 1: Write the schema**

Create `src/rubrica/schema/catalogue-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "catalogue-0.1.json",
  "title": "Corpus catalogue",
  "type": "object",
  "required": ["schema_version", "run_id", "created_utc", "request", "policy",
               "candidates", "excluded"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {"const": "0.1"},
    "run_id": {"$ref": "#/$defs/id"},
    "created_utc": {
      "type": "string",
      "format": "date-time",
      "pattern": "\\A\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z\\Z"
    },
    "request": {
      "type": "object",
      "required": ["target", "objective", "corpus_roots", "limits"],
      "additionalProperties": false,
      "properties": {
        "target": {
          "type": "object",
          "required": ["name", "interface"],
          "additionalProperties": false,
          "properties": {
            "name": {"type": "string", "minLength": 1},
            "interface": {"type": "string", "minLength": 1}
          }
        },
        "objective": {"enum": ["breadth", "depth"]},
        "objective_note": {"type": "string", "minLength": 1},
        "scope_note": {"type": "string", "minLength": 1},
        "corpus_roots": {
          "type": "array",
          "minItems": 1,
          "items": {"type": "string", "minLength": 1}
        },
        "limits": {
          "type": "object",
          "required": ["max_rounds", "max_scenarios"],
          "additionalProperties": false,
          "properties": {
            "max_rounds": {"type": "integer", "minimum": 1},
            "max_scenarios": {"type": "integer", "minimum": 1}
          }
        }
      }
    },
    "policy": {
      "type": "object",
      "required": ["exclusion_reasons", "explode_min_elements",
                   "explode_min_common_keys", "digest_body_chars",
                   "max_candidates"],
      "additionalProperties": false,
      "properties": {
        "exclusion_reasons": {
          "type": "array",
          "minItems": 1,
          "items": {"$ref": "#/$defs/exclusion_reason"}
        },
        "explode_min_elements": {"type": "integer", "minimum": 2},
        "explode_min_common_keys": {"type": "integer", "minimum": 1},
        "digest_body_chars": {"type": "integer", "minimum": 1},
        "max_candidates": {"type": "integer", "minimum": 1},
        "operator_globs": {"type": "array", "items": {"type": "string"}}
      }
    },
    "candidates": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["candidate_id", "origin", "bytes", "sha256", "kind",
                     "admissible", "digest"],
        "additionalProperties": false,
        "properties": {
          "candidate_id": {"$ref": "#/$defs/id"},
          "origin": {"enum": ["corpus", "container_element", "projection"]},
          "path": {"type": "string", "minLength": 1},
          "container": {
            "type": "object",
            "required": ["candidate_id", "json_pointer"],
            "additionalProperties": false,
            "properties": {
              "candidate_id": {"$ref": "#/$defs/id"},
              "json_pointer": {"type": "string", "minLength": 1}
            }
          },
          "provenance": {
            "type": "object",
            "required": ["projection_id", "source_candidate_ids"],
            "additionalProperties": false,
            "properties": {
              "projection_id": {"$ref": "#/$defs/id"},
              "source_candidate_ids": {
                "type": "array",
                "minItems": 1,
                "items": {"$ref": "#/$defs/id"}
              }
            }
          },
          "bytes": {"type": "integer", "minimum": 0},
          "sha256": {"$ref": "#/$defs/sha256"},
          "kind": {"$ref": "#/$defs/kind"},
          "admissible": {"type": "boolean"},
          "digest_truncated": {"type": "boolean"},
          "digest": {"type": "object"}
        }
      }
    },
    "excluded": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["path", "reason"],
        "additionalProperties": false,
        "properties": {
          "path": {"type": "string", "minLength": 1},
          "reason": {"$ref": "#/$defs/exclusion_reason"},
          "detail": {"type": "string", "minLength": 1}
        }
      }
    }
  },
  "$defs": {
    "id": {
      "type": "string",
      "pattern": "\\A[A-Za-z0-9][A-Za-z0-9._-]*\\Z",
      "maxLength": 128
    },
    "sha256": {"type": "string", "pattern": "\\A[0-9a-f]{64}\\Z"},
    "kind": {
      "enum": ["openapi", "mcp_tool_schema", "entity_schema", "trace",
               "design_doc", "source_code", "other"]
    },
    "exclusion_reason": {
      "enum": ["gitignored", "vcs_metadata", "binary", "lockfile", "vendored",
               "duplicate", "unreadable", "operator_excluded"]
    }
  }
}
```

Two deliberate looseness decisions, both worth their comment when you touch
them again. `digest` is `{"type": "object"}` with no inner shape: its keys differ
per kind, and pinning them here would make `digest.py` unable to add a heuristic
without a schema version bump — while the *risk* the spec names (an insufficient
digest) is not a shape problem and no schema can catch it. And `path` /
`container` / `provenance` are not mutually required by the schema; Task 6's
`refs.check_catalogue` enforces "exactly one origin-appropriate locator",
because that is a conditional constraint JSON Schema expresses badly and layer 2
expresses plainly.

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/test_schemas_catalogue.py`:

```python
"""Layer-1 shape checks for the catalogue.

The negative cases matter more than the positive one: this schema is the
contract rb-triage reads, so a document that is wrong in a way layer 1 accepts
becomes a prompt's problem instead of a gate's.
"""

from __future__ import annotations

import json

import pytest

from rubrica import validate
from rubrica.paths import RunPaths


def _catalogue(**over):
    payload = {
        "schema_version": "0.1",
        "run_id": "run-20260814-000000",
        "created_utc": "2026-08-14T00:00:00Z",
        "request": {
            "target": {"name": "parsec", "interface": "http-sse"},
            "objective": "breadth",
            "corpus_roots": ["/tmp/parsec"],
            "limits": {"max_rounds": 2, "max_scenarios": 128},
        },
        "policy": {
            "exclusion_reasons": ["binary", "vendored"],
            "explode_min_elements": 3,
            "explode_min_common_keys": 3,
            "digest_body_chars": 2000,
            "max_candidates": 500,
        },
        "candidates": [
            {
                "candidate_id": "readme-md",
                "origin": "corpus",
                "path": "parsec/README.md",
                "bytes": 8179,
                "sha256": "a" * 64,
                "kind": "design_doc",
                "admissible": True,
                "digest": {"headings": ["# parsec"], "lines": 200},
            }
        ],
        "excluded": [{"path": "parsec/logo.png", "reason": "binary"}],
    }
    payload.update(over)
    return payload


def _write(tmp_path, payload):
    run = RunPaths(tmp_path / "run-20260814-000000")
    run.root.mkdir(parents=True)
    run.catalogue.write_text(json.dumps(payload), encoding="utf-8")
    return run


def test_a_well_formed_catalogue_validates(tmp_path):
    run = _write(tmp_path, _catalogue())
    assert validate.validate_stage(run, "survey") == []


def test_an_unknown_exclusion_reason_is_a_finding(tmp_path):
    """The reason codes are an enum because a free-text reason cannot be
    counted, and the whole point of recording exclusions is that a reader can
    see what shape of thing was dropped."""
    run = _write(tmp_path, _catalogue(excluded=[{"path": "x", "reason": "too_big"}]))
    findings = validate.validate_stage(run, "survey")
    assert findings and "too_big" in str(findings[0])


def test_a_size_based_exclusion_reason_does_not_exist(tmp_path):
    """Spec §2: size was never the binding constraint, shape was.

    tool_definitions.py at 74KB was the parsec run's most load-bearing input.
    An 'oversize' reason code would make dropping it a one-word decision.
    """
    reasons = json.loads(
        (validate.schema_dir() / "catalogue-0.1.json").read_text(encoding="utf-8")
    )["$defs"]["exclusion_reason"]["enum"]
    assert "oversize" not in reasons
    assert "too_big" not in reasons


def test_a_missing_catalogue_is_itself_a_finding(tmp_path):
    run = RunPaths(tmp_path / "run-20260814-000000")
    run.root.mkdir(parents=True)
    findings = validate.validate_stage(run, "survey")
    assert findings and "00-catalogue.json" in str(findings[0])


@pytest.mark.parametrize(
    "objective", ["", "coverage", "BREADTH", "depth-ish"],
)
def test_only_the_two_declared_objectives_are_accepted(tmp_path, objective):
    """Spec §5 defines exactly two, and triage is held to whichever is set."""
    request = _catalogue()["request"] | {"objective": objective}
    run = _write(tmp_path, _catalogue(request=request))
    assert validate.validate_stage(run, "survey") != []
```

- [ ] **Step 3: Run to verify they fail**

```
uv run pytest tests/unit/test_schemas_catalogue.py -v
```

Expected: every test FAILS with `UnknownStage` or `KeyError: 'survey'` — the
stage exists in `STAGES` but `STAGE_ARTIFACTS` has no entry, so
`validate_stage` cannot resolve it.

- [ ] **Step 4: Wire layer 1**

In `src/rubrica/validate.py`, add to `ARTIFACT_SCHEMAS` above the config-kinds
comment:

```python
    "catalogue": "catalogue-0.1.json",
```

Add to `STAGE_ARTIFACTS`, keeping it in `STAGES` order:

```python
    "survey": ("catalogue",),
```

And in `_artifact_paths`, beside the other singletons:

```python
    if kind == "catalogue":
        # Returned even when absent, like manifest and world-model: an expected
        # artifact that is missing has to be reported by name, or a survey that
        # wrote nothing passes its own gate.
        return [run.catalogue] if run.catalogue.is_file() else []
```

Note the asymmetry with `test_a_missing_catalogue_is_itself_a_finding`:
`validate_stage` reports the absence itself when `_artifact_paths` returns `[]`
for a required kind — check how it does that for `manifest` at
`validate.py:201-220` and follow it exactly rather than inventing a second
mechanism.

- [ ] **Step 5: Run the tests**

```
uv run pytest tests/unit/test_schemas_catalogue.py -v && uv run pytest -q
```

Expected: PASS. Full suite at 1183 (Task 2's 1176 plus seven — the four named
tests plus three from the `objective` parametrization... count what you actually
get and record it; the exact number is only useful if it is measured).

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/schema/catalogue-0.1.json src/rubrica/validate.py tests/unit/test_schemas_catalogue.py
git commit -S -s -m "feat: Add the catalogue schema and its layer-1 wiring

No oversize exclusion reason, pinned by a test: the parsec run's most
load-bearing input was its largest file, and shape rather than size was the
binding constraint.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

### Task 4: Walk the corpus and record every exclusion

**Files:**
- Create: `src/rubrica/survey.py`
- Test: `tests/unit/test_survey_walk.py` (new)

**Interfaces:**
- Consumes: `paths.RunPaths`, `errors.UsageError`, `artifacts.sha256_of`.
- Produces:
  - `survey.EXCLUSION_REASONS: tuple[str, ...]` — the same eight strings as the
    schema's enum, and Task 8 pins that they cannot drift.
  - `survey.DEFAULT_MAX_CANDIDATES = 500`, `survey.DEFAULT_DIGEST_BODY_CHARS = 2000`,
    `survey.EXPLODE_MIN_ELEMENTS = 3`, `survey.EXPLODE_MIN_COMMON_KEYS = 3`
  - `survey.walk_corpus(roots: Sequence[Path], *, operator_globs: Sequence[str] = ()) -> tuple[list[Path], list[dict]]`
    returning `(kept_paths_sorted, excluded_entries)` where each excluded entry
    is `{"path": str, "reason": str}` and `path` is relative to the root it was
    found under.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_survey_walk.py`:

```python
"""What survey drops, and whether it says so.

Spec §2's third constraint -- declining must stay visible -- applies to the
mechanical excluder, not only to the skill. A file that vanishes from a
catalogue with no reason recorded is indistinguishable from one that was never
there, which is the confusion that made four parsec gaps unreadable.
"""

from __future__ import annotations

import json

from rubrica import survey


def _corpus(tmp_path):
    root = tmp_path / "corpus"
    (root / "src").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "node_modules" / "left-pad").mkdir(parents=True)
    (root / "README.md").write_text("# Target\n\nProse.\n", encoding="utf-8")
    (root / "src" / "tools.py").write_text("TOOLS = {}\n", encoding="utf-8")
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (root / "node_modules" / "left-pad" / "index.js").write_text("x\n", encoding="utf-8")
    (root / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3}), encoding="utf-8")
    (root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")
    (root / ".gitignore").write_text("secrets.txt\n", encoding="utf-8")
    (root / "secrets.txt").write_text("hunter2\n", encoding="utf-8")
    (root / "copy-of-readme.md").write_text("# Target\n\nProse.\n", encoding="utf-8")
    return root


def _reasons(excluded):
    return {entry["path"]: entry["reason"] for entry in excluded}


def test_every_exclusion_class_fires_and_names_itself(tmp_path):
    root = _corpus(tmp_path)
    kept, excluded = survey.walk_corpus([root])
    reasons = _reasons(excluded)
    assert reasons[".git/HEAD"] == "vcs_metadata"
    assert reasons["node_modules/left-pad/index.js"] == "vendored"
    assert reasons["package-lock.json"] == "lockfile"
    assert reasons["logo.png"] == "binary"
    assert reasons["secrets.txt"] == "gitignored"
    # Byte-identical to README.md, which sorts first, so the copy is the dupe.
    assert reasons["copy-of-readme.md"] == "duplicate"


def test_what_survives_is_only_the_real_evidence(tmp_path):
    root = _corpus(tmp_path)
    kept, _ = survey.walk_corpus([root])
    assert [p.relative_to(root).as_posix() for p in kept] == [
        ".gitignore",
        "README.md",
        "src/tools.py",
    ]


def test_operator_globs_are_recorded_not_silent(tmp_path):
    """An --exclude the operator passed is still a decline, and still visible."""
    root = _corpus(tmp_path)
    _, excluded = survey.walk_corpus([root], operator_globs=["src/*.py"])
    assert _reasons(excluded)["src/tools.py"] == "operator_excluded"


def test_no_file_is_excluded_for_being_large(tmp_path):
    """Spec §2: shape was the binding constraint, never size.

    A 3MB source file is the shape tool_definitions.py had, and it was the
    parsec run's most cited input.
    """
    root = tmp_path / "corpus"
    root.mkdir()
    big = root / "tool_definitions.py"
    big.write_text("TOOLS = [\n" + '    {"name": "t"},\n' * 60000 + "]\n", encoding="utf-8")
    kept, excluded = survey.walk_corpus([root])
    assert kept == [big]
    assert excluded == []


def test_an_unreadable_file_is_recorded_rather_than_raised(tmp_path):
    """A corpus is a user tree; one bad mode must not abort the inventory.

    This is the narrow case: the *file* is unreadable, which is a candidate
    problem. An unreadable corpus *root* is a misconfigured harness and is
    UsageError -- see test_survey_cli.py.
    """
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "fine.md").write_text("# Fine\n", encoding="utf-8")
    bad = root / "locked.md"
    bad.write_text("# Locked\n", encoding="utf-8")
    bad.chmod(0o000)
    try:
        kept, excluded = survey.walk_corpus([root])
        assert kept == [root / "fine.md"]
        assert _reasons(excluded)["locked.md"] == "unreadable"
    finally:
        bad.chmod(0o644)
```

- [ ] **Step 2: Run to verify they fail**

```
uv run pytest tests/unit/test_survey_walk.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'rubrica.survey'`.

- [ ] **Step 3: Implement the walk**

Create `src/rubrica/survey.py`:

```python
"""Stage 00a: turn a corpus into a catalogue of candidates.

The phase this module opens was performed by hand on every run before
2026-08-14, in the orchestrator's own conversation, and recorded nowhere the
pipeline could read. Its output exists so that rb-triage's judgment is
affordable: one bounded digest per candidate rather than the corpus itself,
which is what keeps triage's cost O(candidates) instead of O(corpus bytes).

Two rules govern every choice below, both from the parsec run's §11:

* **No size-based exclusion.** The largest single file in that corpus was also
  its most load-bearing input, unusable whole and correct as a projection. Size
  was never the binding constraint; shape was.
* **Every drop is recorded.** A candidate that vanishes with no reason is
  indistinguishable from one that never existed, and that confusion made four
  of that run's gaps unreadable.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Sequence
from pathlib import Path

from rubrica.artifacts import sha256_of
from rubrica.errors import UsageError

# Same eight strings as catalogue-0.1.json's exclusion_reason enum. Kept here
# too because walk_corpus emits them and a test pins the two lists identical --
# they drifted in exactly this shape once before, for validate.CONFIG_KINDS.
EXCLUSION_REASONS: tuple[str, ...] = (
    "gitignored",
    "vcs_metadata",
    "binary",
    "lockfile",
    "vendored",
    "duplicate",
    "unreadable",
    "operator_excluded",
)

DEFAULT_MAX_CANDIDATES = 500
DEFAULT_DIGEST_BODY_CHARS = 2000
# Three, not two: exploding a two-element config array produces two candidates
# nobody wanted, while the shape this exists for -- a capture of many
# independent records -- is never that small. 130 in the parsec case.
EXPLODE_MIN_ELEMENTS = 3
# Homogeneity is a key-set *intersection*, not identity: real captures carry
# optional fields, and 130 traces where one lacks an `assessments` key are not
# two kinds of thing. Measured on the parsec capture: 12 common keys, zero
# union-only keys, so identity would have worked there and the tolerant rule
# costs nothing.
EXPLODE_MIN_COMMON_KEYS = 3

_VCS_DIRS = frozenset({".git", ".hg", ".svn"})
_VENDOR_DIRS = frozenset(
    {"node_modules", ".venv", "venv", "site-packages", "vendor", "target", "dist", "build"}
)
_LOCKFILES = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "uv.lock",
        "Cargo.lock",
        "Gemfile.lock",
        "go.sum",
        "requirements.txt.lock",
        "composer.lock",
    }
)
_BINARY_SNIFF_BYTES = 8192


def _gitignore_patterns(root: Path) -> list[str]:
    """Patterns from `root/.gitignore`, one level only.

    Deliberately not a full gitignore implementation: nested ignore files,
    negations and directory semantics are a library's job, and getting them
    subtly wrong would drop evidence *silently*, which is the one failure this
    module exists to prevent. What it does catch is the common case -- a
    top-level ignore listing generated and secret files -- and anything it
    misses stays in the catalogue where triage and a human can see it.
    """
    ignore = root / ".gitignore"
    try:
        text = ignore.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    patterns = []
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and not line.startswith("!"):
            patterns.append(line.rstrip("/"))
    return patterns


def _looks_binary(path: Path) -> bool:
    with path.open("rb") as handle:
        return b"\x00" in handle.read(_BINARY_SNIFF_BYTES)


def _matches_any(relative: str, patterns: Sequence[str]) -> bool:
    name = Path(relative).name
    return any(
        fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(name, pattern)
        for pattern in patterns
    )


def walk_corpus(
    roots: Sequence[Path], *, operator_globs: Sequence[str] = ()
) -> tuple[list[Path], list[dict]]:
    """Every file worth cataloguing, and every one dropped with its reason.

    Order matters and is sorted, so `duplicate` always names the *later* of two
    byte-identical paths and two runs over the same corpus produce the same
    catalogue. Returns paths, not digests: digesting is digest.py's job.
    """
    kept: list[Path] = []
    excluded: list[dict] = []
    seen: dict[str, Path] = {}

    for root in roots:
        root = Path(root)
        try:
            if not root.is_dir():
                raise UsageError(f"corpus root is not a directory: {root}")
            walked = sorted(p for p in root.rglob("*") if p.is_file())
        except OSError as exc:
            # An unreadable *root* is the harness pointed at something it cannot
            # read, which is exit 2 -- the same call paths.list_dir makes, and
            # for the same reason: a swallowed EACCES here would report an empty
            # corpus rather than an unreadable one.
            raise UsageError(f"cannot read corpus root: {root} ({exc})") from exc

        ignore_patterns = _gitignore_patterns(root)

        for path in walked:
            relative = path.relative_to(root).as_posix()
            parts = set(path.relative_to(root).parts)

            def drop(reason: str, rel: str = relative) -> None:
                excluded.append({"path": rel, "reason": reason})

            if parts & _VCS_DIRS:
                drop("vcs_metadata")
                continue
            if parts & _VENDOR_DIRS:
                drop("vendored")
                continue
            if path.name in _LOCKFILES:
                drop("lockfile")
                continue
            if operator_globs and _matches_any(relative, operator_globs):
                drop("operator_excluded")
                continue
            if ignore_patterns and _matches_any(relative, ignore_patterns):
                drop("gitignored")
                continue
            try:
                if _looks_binary(path):
                    drop("binary")
                    continue
                digest = sha256_of(path)
            except OSError:
                # One bad mode in a user tree must not abort the inventory. The
                # file is recorded as declined, so it is visible rather than
                # absent -- which is the whole rule this module is built on.
                drop("unreadable")
                continue
            if digest in seen:
                drop("duplicate")
                continue
            seen[digest] = path
            kept.append(path)

    return kept, excluded
```

- [ ] **Step 4: Run the tests**

```
uv run pytest tests/unit/test_survey_walk.py -v
```

Expected: PASS, six tests. If `test_what_survives_is_only_the_real_evidence`
fails because `.gitignore` was itself excluded, that is a real question and the
answer is *keep it* — an ignore file is a statement about the target's shape and
costs almost nothing to digest.

- [ ] **Step 5: Run the full suite and lint**

```
uv run pytest -q && make check
```

Expected: PASS. `make check` will flag `B023` (function definition does not bind
loop variable) on the `drop` closure if you wrote it without the `rel=relative`
default — that default is why it is there, not decoration.

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/survey.py tests/unit/test_survey_walk.py
git commit -S -s -m "feat: Walk a corpus and record every exclusion with its reason

Eight reason codes, none of them about size. Spec §2: the parsec run's largest
file was its most load-bearing input, so shape rather than size is what a
catalogue may drop on.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

### Task 5: Explode homogeneous containers into element candidates

**Files:**
- Modify: `src/rubrica/survey.py` (append)
- Test: `tests/unit/test_survey_explode.py` (new)

**Interfaces:**
- Consumes: `survey.EXPLODE_MIN_ELEMENTS`, `survey.EXPLODE_MIN_COMMON_KEYS`.
- Produces:
  `survey.explode(payload: Any) -> list[tuple[str, Any]] | None` — `(json_pointer,
  element)` pairs in document order, or `None` when the payload is not a
  container worth splitting. Pointers are RFC 6901 (`/0`, `/1`, or `/traces/t1`
  for the keyed form) and Task 7 stores them verbatim in
  `candidates[].container.json_pointer`; Task 14's `intake` resolves them with
  the existing `refs.resolve_pointer`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_survey_explode.py`:

```python
"""When a file is many candidates rather than one.

The parsec run's 130-trace MLflow capture was split by hand and seven elements
picked. This is that split, and only that split: selecting among the elements is
rb-triage's judgment, not this function's.
"""

from __future__ import annotations

from rubrica import survey


def _traces(n, *, drop_key_on_last=False):
    out = []
    for i in range(n):
        element = {"trace_id": f"tr-{i}", "status": "OK", "spans": [], "extra": i}
        if drop_key_on_last and i == n - 1:
            del element["extra"]
        out.append(element)
    return out


def test_a_homogeneous_array_becomes_one_candidate_per_element():
    exploded = survey.explode(_traces(130))
    assert exploded is not None
    assert len(exploded) == 130
    assert exploded[0][0] == "/0"
    assert exploded[47][0] == "/47"
    assert exploded[47][1]["trace_id"] == "tr-47"


def test_an_optional_field_does_not_defeat_homogeneity():
    """Key-set intersection, not identity.

    Measured on the real parsec capture: 130 elements, 12 common keys, zero
    union-only keys -- so identity would have worked there. The tolerant rule
    costs nothing and survives the capture where one element lacks a field.
    """
    exploded = survey.explode(_traces(130, drop_key_on_last=True))
    assert exploded is not None and len(exploded) == 130


def test_an_object_of_objects_explodes_by_key():
    payload = {"t1": {"a": 1, "b": 2, "c": 3}, "t2": {"a": 4, "b": 5, "c": 6},
               "t3": {"a": 7, "b": 8, "c": 9}}
    exploded = survey.explode(payload)
    assert exploded is not None
    assert [pointer for pointer, _ in exploded] == ["/t1", "/t2", "/t3"]


def test_a_two_element_array_is_left_whole():
    """Exploding a small config array produces candidates nobody wanted."""
    assert survey.explode(_traces(2)) is None


def test_a_heterogeneous_array_is_left_whole():
    """Three keys in common is the floor; unrelated objects share fewer."""
    assert survey.explode([{"a": 1}, {"b": 2}, {"c": 3}]) is None


def test_scalars_arrays_of_scalars_and_openapi_documents_are_left_whole():
    """Only containers of independent records explode.

    An OpenAPI document is one contract with many paths, not many contracts --
    splitting it would hand rb-extract fragments that cannot be read alone.
    """
    assert survey.explode(42) is None
    assert survey.explode(["a", "b", "c", "d"]) is None
    assert survey.explode({"openapi": "3.1.0", "paths": {}, "info": {}}) is None


def test_a_pointer_escapes_a_slash_in_a_key():
    """RFC 6901: ~1 for /, ~0 for ~. refs.resolve_pointer already expects this,
    and a raw slash would make the pointer address a level that does not exist."""
    payload = {"a/b": {"x": 1, "y": 2, "z": 3}, "c": {"x": 1, "y": 2, "z": 3},
               "d": {"x": 1, "y": 2, "z": 3}}
    exploded = survey.explode(payload)
    assert exploded is not None
    assert "/a~1b" in [pointer for pointer, _ in exploded]
```

- [ ] **Step 2: Run to verify they fail**

```
uv run pytest tests/unit/test_survey_explode.py -v
```

Expected: FAIL with `AttributeError: module 'rubrica.survey' has no attribute 'explode'`.

- [ ] **Step 3: Implement**

Append to `src/rubrica/survey.py`:

```python
def _escape_pointer_token(token: str) -> str:
    """RFC 6901 escaping. `~` first, or escaping `/` would then be re-escaped."""
    return token.replace("~", "~0").replace("/", "~1")


def _homogeneous(elements: list) -> bool:
    """Whether these elements are independent records of one kind.

    Objects only, and their key sets must share EXPLODE_MIN_COMMON_KEYS. The
    intersection rule rather than identity is the point -- see that constant.
    """
    if not all(isinstance(element, dict) for element in elements):
        return False
    key_sets = [set(element) for element in elements]
    if any(len(keys) < EXPLODE_MIN_COMMON_KEYS for keys in key_sets):
        return False
    return len(set.intersection(*key_sets)) >= EXPLODE_MIN_COMMON_KEYS


def explode(payload: Any) -> list[tuple[str, Any]] | None:
    """Split a container of independent records, or return None.

    Returns (json_pointer, element) pairs in document order. `None` means "this
    is one candidate": a scalar, an array of scalars, a heterogeneous array, or
    an object that is a single document with many sections rather than many
    documents. An OpenAPI spec is the case that matters for that last one --
    it has many `paths` and is still one contract, and a fragment of it cannot
    be read alone.

    Only these two shapes explode, which is spec §3's ruling: no Python
    literals, no multi-document markdown, no archive members.
    """
    if isinstance(payload, list):
        if len(payload) < EXPLODE_MIN_ELEMENTS or not _homogeneous(payload):
            return None
        return [(f"/{index}", element) for index, element in enumerate(payload)]

    if isinstance(payload, dict):
        values = list(payload.values())
        if len(values) < EXPLODE_MIN_ELEMENTS or not _homogeneous(values):
            return None
        return [
            (f"/{_escape_pointer_token(key)}", value) for key, value in payload.items()
        ]

    return None
```

Add `from typing import Any` to the imports at the top of `survey.py`.

- [ ] **Step 4: Run the tests**

```
uv run pytest tests/unit/test_survey_explode.py -v && uv run pytest -q
```

Expected: PASS, seven new tests.

- [ ] **Step 5: Verify against the real capture, and record what you measured**

This is not optional: the whole explosion rule exists for this one file.

```
uv run python -c "
import json
from rubrica import survey
d = json.load(open('/tmp/parsec/traces_parsec-agent-metrics_20260713_115226.json'))
e = survey.explode(d)
print('elements:', len(e))
print('first pointer:', e[0][0], 'last:', e[-1][0])
print('statuses:', {s: sum(1 for _, x in e if x['status'] == s) for s in {x['status'] for _, x in e}})
"
```

Expected: `elements: 130`, `first pointer: /0 last: /129`, and statuses
`{'TraceStatus.OK': 126, 'TraceStatus.IN_PROGRESS': 3, 'TraceStatus.ERROR': 1}`.
That single ERROR is the trace the parsec record calls its only evidence of what
the target does when something goes wrong. If the count is not 130, stop — the
homogeneity rule is wrong and the rest of this phase rests on it.

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/survey.py tests/unit/test_survey_explode.py
git commit -S -s -m "feat: Explode homogeneous JSON containers into element candidates

Verified against the real 130-element parsec capture: 130 elements, pointers /0
to /129, one ERROR status. Homogeneity is a key-set intersection rather than
identity so an optional field does not defeat it.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

### Task 6: Digests — the only thing rb-triage will read

**Files:**
- Create: `src/rubrica/digest.py`
- Test: `tests/unit/test_digest.py` (new)

**Interfaces:**
- Consumes: `intake.classify` (reused for `kind`), `survey.DEFAULT_DIGEST_BODY_CHARS`.
- Produces:
  - `digest.digest_for_path(path: Path, kind: str, *, body_chars: int) -> dict`
  - `digest.digest_for_payload(payload: Any, kind: str, *, body_chars: int) -> dict`
  - `digest.TRACE_HEURISTICS: tuple[str, ...]` — the named heuristics, recorded
    per digest under `heuristics_fired`.
  Task 7 calls both. Task 11's skill prose refers to these key names, so
  renaming one is a two-file change.

**Read the spec's §5.3 before starting.** This is the design's single point of
failure: triage reads only this, and a digest that omits what mattered makes
triage blind. The mitigation is not completeness, which is unreachable — it is
`heuristics_fired`, so that blindness is *visible* and triage can decline
`digest_insufficient` instead of guessing.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_digest.py`:

```python
"""Whether a digest carries what a decision needs.

Every assertion here is anchored to a decision the parsec run actually made by
hand, because "is this digest good enough" is otherwise unanswerable. If a
selection made on 2026-08-13 is not reachable from these fields, the digest is
wrong -- not the test.
"""

from __future__ import annotations

import json

from rubrica import digest


def test_prose_carries_the_full_heading_outline(tmp_path):
    """The parsec prose documents were admitted on title and structure.

    The outline is complete rather than truncated: it is the cheapest possible
    statement of what a document covers, and truncating it is how a triage
    misses the one section that mattered.
    """
    path = tmp_path / "architecture.md"
    path.write_text(
        "# Parsec\n\nIntro.\n\n## Routing\n\ntext\n\n### Fast path\n\nmore\n\n## Streaming\n\nx\n",
        encoding="utf-8",
    )
    result = digest.digest_for_path(path, "design_doc", body_chars=20)
    assert result["headings"] == ["# Parsec", "## Routing", "### Fast path", "## Streaming"]
    assert result["lines"] == 13
    assert len(result["body_head"]) <= 20
    assert result["digest_truncated"] is True


def test_source_carries_top_level_assignments_not_only_defs(tmp_path):
    """Spec §8: triage can only name TOOL_DEFINITIONS as a projection's
    extraction point if the digest lists top-level assignments. Without this
    field the projection brief cannot say where to start."""
    path = tmp_path / "tool_definitions.py"
    path.write_text(
        "import json\nfrom typing import Any\n\n"
        "TOOL_DEFINITIONS = [{'name': 'query_aap2'}]\n"
        "DELEGATION_TOOLS = []\n\n"
        "def build(x: Any) -> dict:\n    return {}\n\n"
        "class Registry:\n    pass\n",
        encoding="utf-8",
    )
    result = digest.digest_for_path(path, "source_code", body_chars=2000)
    assert result["assignments"] == ["DELEGATION_TOOLS", "TOOL_DEFINITIONS"]
    assert result["defs"] == ["build"]
    assert result["classes"] == ["Registry"]
    assert result["imports"] == ["json", "typing"]


def test_a_json_document_carries_a_structural_skeleton(tmp_path):
    path = tmp_path / "tools.json"
    path.write_text(
        json.dumps({"tools": [{"name": "a", "input_schema": {"type": "object"}}]}),
        encoding="utf-8",
    )
    result = digest.digest_for_path(path, "mcp_tool_schema", body_chars=2000)
    assert result["skeleton"]["/tools"] == {"type": "array", "length": 1}
    assert result["skeleton"]["/tools/0/name"] == {"type": "string"}


def test_a_trace_digest_reaches_every_parsec_selection():
    """The four facts the 2026-08-13 selection actually turned on:

    t7 kept for being the only ERROR with three spans; t3 identified as an
    icinga/aap2 crossover from its question text; depth judged from span count;
    tool coverage judged from span names.
    """
    element = {
        "trace_id": "tr-eef9",
        "status": "TraceStatus.ERROR",
        "execution_time_ms": 11776,
        "request_preview": '{"question": "How many sandbox accounts do we have in each region?"',
        "response_preview": '{"response": "I will query...", "routing_method": "llm"}',
        "spans": [
            {"name": "parsec:orchestrator", "span_type": "AGENT", "events": [{"name": "exception"}]},
            {"name": "query_aws_account_db", "span_type": "TOOL", "events": []},
            {"name": "db_list_tables", "span_type": "TOOL", "events": []},
        ],
    }
    result = digest.digest_for_payload(element, "trace", body_chars=2000)
    assert result["status"] == "TraceStatus.ERROR"
    assert result["element_counts"]["spans"] == 3
    assert "sandbox accounts" in result["request_text"]
    assert result["names"] == ["db_list_tables", "parsec:orchestrator", "query_aws_account_db"]
    assert result["error_markers"] is True
    assert "status" in result["heuristics_fired"]
    assert "names" in result["heuristics_fired"]


def test_a_heuristic_that_does_not_fire_is_absent_from_heuristics_fired():
    """This is the whole mitigation for §5.3.

    A digest that silently lacked a field would make triage guess. Recording
    which heuristics fired is what lets it decline digest_insufficient and name
    what it needed -- so this assertion is the load-bearing one in the file.
    """
    result = digest.digest_for_payload({"a": 1, "b": 2, "c": 3}, "trace", body_chars=2000)
    assert "status" not in result["heuristics_fired"]
    assert "names" not in result["heuristics_fired"]
    assert result["heuristics_fired"] == []


def test_every_named_heuristic_is_reachable():
    """A heuristic nobody can trigger is dead prose in the skill that cites it."""
    element = {
        "status": "OK",
        "spans": [{"name": "a"}, {"name": "b"}],
        "question": "why",
        "error": "boom",
    }
    result = digest.digest_for_payload(element, "trace", body_chars=2000)
    assert set(result["heuristics_fired"]) == set(digest.TRACE_HEURISTICS)


def test_an_undecodable_file_digests_to_a_recorded_failure(tmp_path):
    """Not a raise: survey already recorded readable files only, so reaching
    here means the bytes are not text -- and a digest that reports that is what
    lets triage decline rather than the run abort."""
    path = tmp_path / "notes.md"
    path.write_bytes(b"\xff\xfe\x00bad")
    result = digest.digest_for_path(path, "design_doc", body_chars=2000)
    assert result["undecodable"] is True
```

- [ ] **Step 2: Run to verify they fail**

```
uv run pytest tests/unit/test_digest.py -v
```

Expected: FAIL, `ModuleNotFoundError: No module named 'rubrica.digest'`.

- [ ] **Step 3: Implement**

Create `src/rubrica/digest.py`:

```python
"""One bounded digest per candidate: the only thing rb-triage reads.

This module is the design's single point of failure and is written knowing it.
Triage's `reads` is the catalogue alone, so a fact absent from a digest is a
fact triage does not have -- and the generator is code that cannot know what
matters about a target it has never seen.

Completeness is unreachable, so the mitigation is honesty instead:
`heuristics_fired` records which extractors actually found something. A triage
that cannot rule on a candidate declines it `digest_insufficient` and names the
field it needed, which turns this module's blindness into a finding a human
reads at gate 0 rather than a silent bad selection.

Every field here is anchored to a decision the 2026-08-13 parsec run made by
hand. If a new field cannot be traced to a decision somebody actually took, it
is weight in a barrier's context window and does not belong.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

# Named so a skill can cite them and a test can prove each is reachable.
TRACE_HEURISTICS: tuple[str, ...] = ("status", "element_counts", "request_text", "names",
                                     "error_markers")

_STATUS_KEYS = ("status", "state", "outcome")
_COUNT_KEYS = ("spans", "steps", "messages", "events", "turns", "calls")
_REQUEST_KEYS = ("question", "request_preview", "input", "request", "query", "prompt")
_NAME_KEYS = ("name", "tool", "tool_name", "tools_called", "operation")
_ERROR_KEYS = ("error", "exception", "traceback", "stack_trace")
_SKELETON_DEPTH = 3
_MAX_NAMES = 64


def _first_scalar(payload: dict, keys: tuple[str, ...]) -> Any | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str | int | float | bool):
            return value
    return None


def _collect_names(node: Any, depth: int, out: set[str]) -> None:
    if depth < 0 or len(out) >= _MAX_NAMES:
        return
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _NAME_KEYS and isinstance(value, str):
                out.add(value)
            elif key in _NAME_KEYS and isinstance(value, list):
                out.update(v for v in value if isinstance(v, str))
            else:
                _collect_names(value, depth - 1, out)
    elif isinstance(node, list):
        for item in node:
            _collect_names(item, depth - 1, out)


def _has_error_marker(node: Any, depth: int) -> bool:
    if depth < 0:
        return False
    if isinstance(node, dict):
        for key, value in node.items():
            lowered = key.lower()
            if lowered in _ERROR_KEYS and value not in (None, "", [], {}):
                return True
            if isinstance(value, str) and "exception" in value.lower():
                return True
            if _has_error_marker(value, depth - 1):
                return True
    elif isinstance(node, list):
        return any(_has_error_marker(item, depth - 1) for item in node)
    return False


def _skeleton(node: Any, pointer: str, depth: int, out: dict) -> None:
    if depth < 0:
        return
    if isinstance(node, dict):
        if pointer:
            out[pointer] = {"type": "object", "keys": sorted(node)[:32]}
        for key, value in node.items():
            _skeleton(value, f"{pointer}/{key}", depth - 1, out)
    elif isinstance(node, list):
        out[pointer or "/"] = {"type": "array", "length": len(node)}
        if node:
            _skeleton(node[0], f"{pointer}/0", depth - 1, out)
    else:
        out[pointer or "/"] = {"type": type(node).__name__ if node is not None else "null"}


def _prose_digest(text: str, body_chars: int) -> dict:
    lines = text.splitlines()
    headings = [line.rstrip() for line in lines if line.startswith("#")]
    body = "\n".join(line for line in lines if not line.startswith("#")).strip()
    return {
        # Complete, never truncated: the outline is the cheapest full statement
        # of what a document covers, and a truncated one is how triage misses
        # the one section that mattered.
        "headings": headings,
        "lines": len(lines),
        "body_head": body[:body_chars],
        "digest_truncated": len(body) > body_chars,
    }


def _source_digest(text: str) -> dict:
    """Top-level names only, via ast -- never a regex over source.

    `assignments` is the field spec §8 depends on: a projection brief can only
    say "the schemas are the literals named TOOL_DEFINITIONS" if triage can see
    that name, and defs and classes alone do not carry it.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {"parse_failed": True}
    assignments: set[str] = set()
    defs: list[str] = []
    classes: list[str] = []
    imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            assignments.update(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assignments.add(node.target.id)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            defs.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return {
        "assignments": sorted(assignments),
        "defs": defs,
        "classes": classes,
        "imports": sorted(imports),
        "lines": len(text.splitlines()),
    }


def digest_for_payload(payload: Any, kind: str, *, body_chars: int) -> dict:
    """Digest an already-parsed JSON payload -- a container element, or a file
    survey has read. `heuristics_fired` is the field that matters; see module doc."""
    if kind == "trace" and isinstance(payload, dict):
        fired: list[str] = []
        result: dict[str, Any] = {}

        status = _first_scalar(payload, _STATUS_KEYS)
        if status is not None:
            result["status"] = status
            fired.append("status")

        counts = {
            key: len(payload[key])
            for key in _COUNT_KEYS
            if isinstance(payload.get(key), list)
        }
        if counts:
            result["element_counts"] = counts
            fired.append("element_counts")

        request = _first_scalar(payload, _REQUEST_KEYS)
        if isinstance(request, str) and request.strip():
            # Kept raw and truncated rather than parsed: the parsec captures
            # store request_preview as a *truncated* JSON string, so json.loads
            # fails on it while the question text sits in the first 80 chars.
            result["request_text"] = request[:body_chars]
            fired.append("request_text")

        names: set[str] = set()
        _collect_names(payload, _SKELETON_DEPTH, names)
        if names:
            result["names"] = sorted(names)
            fired.append("names")

        if _has_error_marker(payload, _SKELETON_DEPTH):
            result["error_markers"] = True
            fired.append("error_markers")

        result["heuristics_fired"] = [h for h in TRACE_HEURISTICS if h in fired]
        return result

    skeleton: dict[str, Any] = {}
    _skeleton(payload, "", _SKELETON_DEPTH, skeleton)
    return {"skeleton": skeleton}


def digest_for_path(path: Path, kind: str, *, body_chars: int) -> dict:
    """Digest one file. Never raises: survey already filtered unreadable files,
    so a failure here is a property of the bytes and belongs in the record."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {"undecodable": True}

    if kind == "design_doc":
        return _prose_digest(text, body_chars)
    if kind == "source_code":
        return _source_digest(text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # Not JSON and not a kind we have a reader for: give triage the prose
        # digest rather than nothing, and let it decline if that is not enough.
        return _prose_digest(text, body_chars)
    return digest_for_payload(payload, kind, body_chars=body_chars)
```

- [ ] **Step 4: Run the tests**

```
uv run pytest tests/unit/test_digest.py -v && uv run pytest -q && make check
```

Expected: PASS, seven new tests.

- [ ] **Step 5: Measure the digest against the real corpus and record the size**

The barrier's context budget is the constraint nobody can check from a unit test.

```
uv run python -c "
import json
from pathlib import Path
from rubrica import digest, survey, intake
kept, excluded = survey.walk_corpus([Path('/tmp/parsec')])
print('kept', len(kept), 'excluded', len(excluded))
total = 0
for p in kept:
    d = digest.digest_for_path(p, intake.classify(p), body_chars=2000)
    total += len(json.dumps(d))
cap = json.load(open('/tmp/parsec/traces_parsec-agent-metrics_20260713_115226.json'))
elems = survey.explode(cap)
tr = sum(len(json.dumps(digest.digest_for_payload(e, 'trace', body_chars=2000))) for _, e in elems)
print('file digests bytes', total)
print('trace element digests bytes', tr, 'over', len(elems), 'elements')
print('TOTAL KB', round((total + tr) / 1024))
"
```

Record the numbers in the commit message. If the total exceeds ~400KB, lower
`DEFAULT_DIGEST_BODY_CHARS` before phase 2 rather than after — the whole
catalogue lands in one barrier dispatch's context, and spec §14 names this as a
live risk rather than a solved one.

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/digest.py tests/unit/test_digest.py
git commit -S -s -m "feat: Digest each candidate, and record which heuristics fired

Every field is anchored to a selection the 2026-08-13 parsec run made by hand:
status and span count (t7, the only ERROR), request text (t3's crossover), span
names (tool coverage), top-level assignments (the field a projection brief needs
to name TOOL_DEFINITIONS as its extraction point).

heuristics_fired is the mitigation for the design's single point of failure.
Completeness is unreachable, so a digest states what it found and triage
declines digest_insufficient rather than guessing.

Measured over the real corpus: <fill in from step 5>.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

### Task 7: Assemble the catalogue and mint the run

**Files:**
- Modify: `src/rubrica/artifacts.py` (extract `canonical_bytes`),
  `src/rubrica/survey.py` (append `survey()`),
  `src/rubrica/cli.py` (SUBCOMMANDS, parser, dispatch)
- Test: `tests/unit/test_survey.py` (new)

**Interfaces:**
- Consumes: `survey.walk_corpus`, `survey.explode`, `digest.digest_for_path`,
  `digest.digest_for_payload`, `intake.classify`, `intake.slug`,
  `manifest.utc_stamp`.
- Produces:
  - `artifacts.canonical_bytes(payload: Any) -> bytes` — the exact bytes
    `write_json` writes. **Task 14 depends on this:** an element's `sha256` is
    computed here at survey time and re-verified after `intake` materialises it,
    so both sides must use one function or the digests disagree.
  - `survey.survey(*, corpus_roots, runs_dir, target_name, target_interface,
    objective, objective_note=None, scope_note=None, operator_globs=(),
    max_rounds, max_scenarios, max_candidates=DEFAULT_MAX_CANDIDATES,
    digest_body_chars=DEFAULT_DIGEST_BODY_CHARS, now=None) -> RunPaths`
  - CLI: `rubrica survey`.

- [ ] **Step 1: Extract `canonical_bytes` first, with its test**

Add to `tests/unit/test_artifacts.py`:

```python
def test_canonical_bytes_are_exactly_what_write_json_writes(tmp_path):
    """Survey hashes an element before it exists as a file; intake materialises
    it later and refs re-hashes the result. One function, or the two disagree
    and every exploded input reports a digest mismatch."""
    payload = {"b": 1, "a": [2, 3]}
    path = tmp_path / "x.json"
    artifacts.write_json(path, payload)
    assert path.read_bytes() == artifacts.canonical_bytes(payload)
```

In `src/rubrica/artifacts.py`, add above `write_json` and use it there:

```python
def canonical_bytes(payload: Any) -> bytes:
    """The canonical on-disk form of an artifact, as bytes.

    Separate from write_json because survey needs the *digest* of a container
    element before any file exists, and intake materialises that same element
    later. Two spellings of "the canonical form" would make every exploded
    input's sha256 mismatch after materialisation.
    """
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
```

Then in `write_json`, replace the `body = json.dumps(...)` line with:

```python
    body = canonical_bytes(payload).decode("utf-8")
```

- [ ] **Step 2: Write the failing tests for `survey()`**

Create `tests/unit/test_survey.py`:

```python
"""Minting a run from a corpus.

The run directory now exists before anything is admitted, which is the change
this whole design turns on: the triage record has to live inside the run so
check-refs can resolve against it, and check-refs reads a run and nothing else.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rubrica import survey, validate
from rubrica.artifacts import canonical_bytes, read_json
from rubrica.errors import UsageError

NOW = datetime(2026, 8, 14, 21, 30, 0, tzinfo=UTC)


def _corpus(tmp_path, *, traces=4):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "README.md").write_text("# Target\n\n## Tools\n\nprose\n", encoding="utf-8")
    (root / "capture.json").write_text(
        json.dumps(
            [
                {"trace_id": f"tr-{i}", "status": "OK", "spans": [{"name": "t"}]}
                for i in range(traces)
            ]
        ),
        encoding="utf-8",
    )
    return root


def _survey(tmp_path, **over):
    kwargs = dict(
        corpus_roots=[_corpus(tmp_path)],
        runs_dir=tmp_path / "runs",
        target_name="parsec",
        target_interface="http-sse",
        objective="breadth",
        max_rounds=2,
        max_scenarios=128,
        now=NOW,
    )
    kwargs.update(over)
    return survey.survey(**kwargs)


def test_survey_mints_a_run_and_writes_a_valid_catalogue(tmp_path):
    run = _survey(tmp_path)
    assert run.root.name == "run-20260814-213000"
    assert run.catalogue.is_file()
    assert validate.validate_stage(run, "survey") == []
    # No manifest yet: intake still writes it, so manifest.json appears only when
    # there are inputs to name and inputs.minItems stays as strict as it is.
    assert not run.manifest.exists()
    assert not run.inputs_dir.exists()


def test_the_container_and_its_elements_are_all_candidates(tmp_path):
    catalogue = read_json(_survey(tmp_path).catalogue)
    by_origin = {}
    for candidate in catalogue["candidates"]:
        by_origin.setdefault(candidate["origin"], []).append(candidate)
    assert len(by_origin["container_element"]) == 4
    corpus_paths = {c["path"] for c in by_origin["corpus"]}
    assert corpus_paths == {"README.md", "capture.json"}
    container = next(c for c in by_origin["corpus"] if c["path"] == "capture.json")
    # The container stays visible but cannot be admitted: admitting it would
    # hand rb-extract all four records as one artifact, which is the thing
    # exploding exists to prevent.
    assert container["admissible"] is False
    assert all(c["admissible"] for c in by_origin["container_element"])


def test_an_element_carries_a_resolvable_pointer_and_its_materialised_digest(tmp_path):
    """The sha256 is of the bytes intake will write, not of the container.

    Task 14 materialises this element and refs.check_inputs re-hashes the file;
    if this digest were of anything else, every exploded input would report a
    mismatch the moment it was admitted.
    """
    catalogue = read_json(_survey(tmp_path).catalogue)
    element = next(c for c in catalogue["candidates"] if c["origin"] == "container_element")
    assert element["container"]["json_pointer"].startswith("/")
    assert element["container"]["candidate_id"] == "capture-json"
    source = json.loads((tmp_path / "corpus" / "capture.json").read_text(encoding="utf-8"))
    index = int(element["container"]["json_pointer"].lstrip("/"))
    import hashlib

    assert element["sha256"] == hashlib.sha256(canonical_bytes(source[index])).hexdigest()
    assert element["bytes"] == len(canonical_bytes(source[index]))


def test_candidate_ids_are_unique_and_safe_path_segments(tmp_path):
    catalogue = read_json(_survey(tmp_path).catalogue)
    ids = [c["candidate_id"] for c in catalogue["candidates"]]
    assert len(ids) == len(set(ids))
    from rubrica.paths import is_safe_segment

    assert all(is_safe_segment(cid) for cid in ids)


def test_the_policy_that_shaped_the_set_is_recorded(tmp_path):
    """A reader of a catalogue needs to know which rules produced it, or the
    exclusions and the splits are unexplainable a week later."""
    policy = read_json(_survey(tmp_path).catalogue)["policy"]
    assert policy["explode_min_elements"] == survey.EXPLODE_MIN_ELEMENTS
    assert policy["explode_min_common_keys"] == survey.EXPLODE_MIN_COMMON_KEYS
    assert set(policy["exclusion_reasons"]) == set(survey.EXCLUSION_REASONS)


def test_too_many_candidates_is_a_usage_error_not_a_finding(tmp_path):
    """Narrowing --corpus is the fix, and the exit-code contract puts a usage
    error at 2. No orchestrator repair can shrink a corpus."""
    with pytest.raises(UsageError, match="max_candidates"):
        _survey(tmp_path, corpus_roots=[_corpus(tmp_path, traces=40)], max_candidates=10)


def test_a_naive_datetime_is_refused(tmp_path):
    """Same rule intake already holds: .astimezone() would assume the host zone,
    so two hosts would mint two different run ids for the same call."""
    with pytest.raises(UsageError, match="timezone-aware"):
        _survey(tmp_path, now=datetime(2026, 8, 14, 21, 30, 0))


def test_a_blank_target_name_is_refused_before_the_run_is_minted(tmp_path):
    """intake refuses this and the reason transfers: minting anyway exits 0 and
    surfaces steps later as findings against an artifact no repair can fix."""
    with pytest.raises(UsageError, match="target-name"):
        _survey(tmp_path, target_name="   ")
    assert not (tmp_path / "runs").exists()


def test_an_unreadable_corpus_root_is_exit_two_material(tmp_path):
    root = _corpus(tmp_path)
    root.chmod(0o000)
    try:
        with pytest.raises(UsageError, match="cannot read corpus root"):
            _survey(tmp_path, corpus_roots=[root])
    finally:
        root.chmod(0o755)
```

- [ ] **Step 3: Run to verify they fail**

```
uv run pytest tests/unit/test_survey.py -v
```

Expected: FAIL, `AttributeError: module 'rubrica.survey' has no attribute 'survey'`.

- [ ] **Step 4: Implement `survey()`**

Append to `src/rubrica/survey.py` (and add the imports it needs:
`from datetime import UTC, datetime`, `from rubrica import digest as digest_module`,
`from rubrica.artifacts import canonical_bytes, sha256_of, write_json`,
`from rubrica.intake import classify, slug`, `from rubrica.manifest import utc_stamp`,
`from rubrica.paths import RunPaths`):

```python
def _unique(base: str, used: dict[str, int]) -> str:
    """`base`, suffixed on collision, so ids are stable under a sorted walk."""
    count = used.get(base, 0) + 1
    used[base] = count
    return base if count == 1 else f"{base}-{count}"


def survey(
    *,
    corpus_roots: Sequence[Path],
    runs_dir: Path,
    target_name: str,
    target_interface: str,
    objective: str,
    objective_note: str | None = None,
    scope_note: str | None = None,
    operator_globs: Sequence[str] = (),
    max_rounds: int,
    max_scenarios: int,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    digest_body_chars: int = DEFAULT_DIGEST_BODY_CHARS,
    now: datetime | None = None,
) -> RunPaths:
    """Mint a run and write its catalogue. Writes no manifest and no inputs.

    Argument validation happens before the directory is created, for the reason
    intake.intake's own docstring gives: minting a run from a parameter set the
    manifest schema will later reject exits 0 and surfaces steps later as
    findings against an artifact no repair prompt can fix.
    """
    if not corpus_roots:
        raise UsageError("survey needs at least one --corpus root")
    for label, value in (("--target-name", target_name), ("--target-interface", target_interface)):
        if not isinstance(value, str) or not value.strip():
            raise UsageError(f"survey needs a non-empty {label}, got {value!r}")
    if objective not in ("breadth", "depth"):
        raise UsageError(f"survey needs --objective breadth or depth, got {objective!r}")
    for label, value in (
        ("--max-rounds", max_rounds),
        ("--max-scenarios", max_scenarios),
        ("--max-candidates", max_candidates),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise UsageError(f"survey needs {label} to be an integer >= 1, got {value!r}")

    if now is None:
        stamp = datetime.now(UTC)
    elif now.tzinfo is None:
        raise UsageError("survey needs a timezone-aware datetime, got a naive one")
    else:
        stamp = now.astimezone(UTC)

    kept, excluded = walk_corpus([Path(root) for root in corpus_roots], operator_globs=operator_globs)

    candidates: list[dict] = []
    used: dict[str, int] = {}
    for path in kept:
        root = next(
            Path(r) for r in corpus_roots if path.is_relative_to(Path(r))
        )
        relative = path.relative_to(root).as_posix()
        kind = classify(path)
        candidate_id = _unique(slug(path.name), used)
        exploded = None
        if kind != "design_doc" and kind != "source_code":
            # Only structured files can be containers. Reading a 6MB capture is
            # the cost this whole stage exists to pay once rather than per-stage.
            try:
                exploded = explode(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                exploded = None

        entry = {
            "candidate_id": candidate_id,
            "origin": "corpus",
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": sha256_of(path),
            "kind": kind,
            # A container stays visible and inadmissible: admitting it would hand
            # one stage every record at once, which is what exploding prevents.
            "admissible": exploded is None,
            "digest": digest_module.digest_for_path(path, kind, body_chars=digest_body_chars),
        }
        candidates.append(entry)

        for pointer, element in exploded or []:
            body = canonical_bytes(element)
            element_kind = classify_payload(element)
            candidates.append(
                {
                    "candidate_id": _unique(f"{candidate_id}{pointer.replace('/', '-')}", used),
                    "origin": "container_element",
                    "container": {"candidate_id": candidate_id, "json_pointer": pointer},
                    "bytes": len(body),
                    # Of the bytes intake will materialise, not of the container:
                    # refs.check_inputs re-hashes the written file.
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "kind": element_kind,
                    "admissible": True,
                    "digest": digest_module.digest_for_payload(
                        element, element_kind, body_chars=digest_body_chars
                    ),
                }
            )

    if len(candidates) > max_candidates:
        raise UsageError(
            f"corpus yields {len(candidates)} candidates, over max_candidates={max_candidates}; "
            "narrow --corpus or raise the cap -- a catalogue this large does not fit one "
            "triage dispatch's context"
        )

    run = RunPaths(Path(runs_dir) / f"run-{stamp:%Y%m%d-%H%M%S}")
    if run.root.exists():
        raise FileExistsError(f"run directory already exists: {run.root}")
    run.root.mkdir(parents=True)

    request = {
        "target": {"name": target_name.strip(), "interface": target_interface.strip()},
        "objective": objective,
        "corpus_roots": [str(Path(root)) for root in corpus_roots],
        "limits": {"max_rounds": max_rounds, "max_scenarios": max_scenarios},
    }
    if objective_note:
        request["objective_note"] = objective_note
    if scope_note:
        request["scope_note"] = scope_note

    write_json(
        run.catalogue,
        {
            "schema_version": "0.1",
            "run_id": run.root.name,
            "created_utc": utc_stamp(stamp),
            "request": request,
            "policy": {
                "exclusion_reasons": list(EXCLUSION_REASONS),
                "explode_min_elements": EXPLODE_MIN_ELEMENTS,
                "explode_min_common_keys": EXPLODE_MIN_COMMON_KEYS,
                "digest_body_chars": digest_body_chars,
                "max_candidates": max_candidates,
                "operator_globs": list(operator_globs),
            },
            "candidates": candidates,
            "excluded": excluded,
        },
    )
    return run
```

Add `import hashlib` and `import json` to `survey.py`'s imports, and add this
helper beside `walk_corpus` — `intake.classify` takes a path and a container
element has none:

```python
def classify_payload(payload: Any) -> str:
    """The artifact kind of a container element, which has no filename.

    Mirrors intake.classify's *content* branch only. Deliberately not a call
    into intake.classify with a fake path: a synthesised name would let the
    filename branch fire on something that has no filename.
    """
    if isinstance(payload, dict):
        if "openapi" in payload or "swagger" in payload:
            return "openapi"
        if "spans" in payload or "trace_id" in payload:
            return "trace"
        if "tools" in payload:
            return "mcp_tool_schema"
    return "other"
```

- [ ] **Step 5: Wire the CLI**

In `src/rubrica/cli.py`, add to `SUBCOMMANDS` (first, matching `STAGES` order):

```python
    ("survey", "inventory a corpus into a catalogue of candidates and mint a run"),
```

Add the parser:

```python
    p_survey = parsers["survey"]
    p_survey.add_argument("--corpus", action="append", required=True, metavar="PATH")
    p_survey.add_argument("--runs-dir", required=True)
    p_survey.add_argument("--target-name", required=True)
    p_survey.add_argument("--target-interface", required=True)
    p_survey.add_argument("--objective", required=True, choices=["breadth", "depth"])
    p_survey.add_argument("--objective-note", default=None)
    p_survey.add_argument("--scope-note", default=None)
    p_survey.add_argument("--exclude", action="append", default=[], metavar="GLOB")
    p_survey.add_argument("--max-rounds", type=int, default=2)
    p_survey.add_argument("--max-scenarios", type=int, default=128)
    p_survey.add_argument("--max-candidates", type=int, default=survey.DEFAULT_MAX_CANDIDATES)
```

And the dispatch branch, beside `intake`'s — print the run directory, as `intake`
does, because the orchestrator reads it from stdout:

```python
    if args.command == "survey":
        run = survey.survey(
            corpus_roots=[Path(p) for p in args.corpus],
            runs_dir=Path(args.runs_dir),
            target_name=args.target_name,
            target_interface=args.target_interface,
            objective=args.objective,
            objective_note=args.objective_note,
            scope_note=args.scope_note,
            operator_globs=args.exclude,
            max_rounds=args.max_rounds,
            max_scenarios=args.max_scenarios,
            max_candidates=args.max_candidates,
        )
        print(run.root)
        return 0
```

- [ ] **Step 6: Run everything**

```
uv run pytest tests/unit/test_survey.py -v && uv run pytest -q && make check
```

Expected: PASS. `test_cli.py`'s `parametrize("command", sorted(subcommand_names()))`
picks up `survey` for free, so the count grows by more than the nine tests above.

- [ ] **Step 7: Survey the real corpus and read the result yourself**

```
uv run rubrica survey --corpus /tmp/parsec --runs-dir runs \
  --target-name parsec --target-interface http-sse --objective breadth \
  --objective-note "Cover as much of parsec's tool surface as the capture supports." \
  --max-rounds 3 --max-scenarios 128
```

Then, on the printed run directory:

```
uv run rubrica validate --stage survey --run <RUN>
uv run python -c "
import json,sys
c=json.load(open(sys.argv[1]+'/00-catalogue.json'))
print('candidates', len(c['candidates']), 'excluded', len(c['excluded']))
from collections import Counter
print(Counter(e['reason'] for e in c['excluded']))
print(Counter(x['kind'] for x in c['candidates']))
print('catalogue KB', round(len(json.dumps(c))/1024))
" <RUN>
```

Expected: `validate` exits 0. Roughly 380 candidates (262 corpus files less
exclusions, plus 130 elements and their container). Exclusion reasons should
include `vcs_metadata`, `gitignored`, `lockfile`, and `binary` — all four are
present in the real tree. **If the candidate count exceeds 500 the run refuses
at exit 2**; that is the guard working, and the fix is `--max-candidates`, not a
code change.

- [ ] **Step 8: Commit**

```bash
git add src/rubrica/survey.py src/rubrica/artifacts.py src/rubrica/cli.py \
        tests/unit/test_survey.py tests/unit/test_artifacts.py
git commit -S -s -m "feat: Add rubrica survey -- mint a run and catalogue its corpus

The run directory now exists before anything is admitted, which is what lets the
triage record live inside the run: check-refs reads a run and nothing else, so a
decline recorded anywhere else is a decline no gate can resolve against.

No manifest is written here, so inputs.minItems stays at 1 and manifest.json
still appears only when there are inputs to name.

Measured on the real parsec corpus: <candidates/excluded/KB from step 7>.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

### Task 8: The corpus fixture, and layer 2 over the catalogue

**Files:**
- Create: `tests/fixtures/corpus-toy/` (see step 1), `tests/unit/test_refs_catalogue.py`
- Modify: `src/rubrica/refs.py` (`_readable_targets`, new `check_catalogue`,
  `check_all`)
- Test: `tests/unit/test_survey_fixture.py` (new)

**Interfaces:**
- Consumes: `RunPaths.catalogue`.
- Produces: `refs.check_catalogue(run: RunPaths) -> list[Finding]`, called from
  `check_all` **before** `check_manifest` (a run in the survey→intake window has
  no manifest, and the catalogue is the only thing there is to check).

- [ ] **Step 1: Build the fixture**

Create `tests/fixtures/corpus-toy/` with exactly these files. It exercises every
exclusion code and the explosion path in one tree, and it becomes **the model
answer `rb-triage` imitates** — so it carries the same elevated risk
`tests/fixtures/toy/` does, and an edit to it is higher-risk than an edit to
source.

```
tests/fixtures/corpus-toy/
  README.md                  prose: "# TicketQ", "## Tools", "## Entities"
  design/notes.md            prose with three headings
  src/tool_defs.py           TOOLS = [...] plus one def and one class
  api.json                   {"tools": [{"name": "search", ...}]}
  capture.json               JSON array of 4 homogeneous trace objects
  package-lock.json          {"lockfileVersion": 3}
  logo.png                   8 bytes starting \x89PNG\r\n\x1a\n\x00
  .gitignore                 "generated.txt"
  generated.txt              "noise"
  copy-of-README.md          byte-identical to README.md
  .git/HEAD                  "ref: refs/heads/main"
  node_modules/dep/index.js  "module.exports = 1"
```

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/test_survey_fixture.py`:

```python
"""The corpus fixture, guarded in both directions.

Both directions, because tests/fixtures/toy-gap/ taught this lesson: an
over-subtraction there once destroyed a capability fact while still passing
every forbidden-substring check. So this file asserts what the fixture still
contains as well as what survey does with it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from rubrica import refs, survey, validate
from rubrica.artifacts import read_json

FIXTURE = Path(__file__).parent.parent / "fixtures" / "corpus-toy"


def _survey(tmp_path):
    return survey.survey(
        corpus_roots=[FIXTURE],
        runs_dir=tmp_path / "runs",
        target_name="ticketq",
        target_interface="mcp",
        objective="breadth",
        max_rounds=2,
        max_scenarios=128,
        now=datetime(2026, 8, 14, 21, 30, 0, tzinfo=UTC),
    )


def test_the_fixture_still_carries_one_of_every_exclusion_class():
    """If a file is deleted from the fixture, the reason code it proved stops
    being covered -- silently, because nothing else in the suite reaches it."""
    names = {p.relative_to(FIXTURE).as_posix() for p in FIXTURE.rglob("*") if p.is_file()}
    for required in (
        ".git/HEAD",
        "node_modules/dep/index.js",
        "package-lock.json",
        "logo.png",
        ".gitignore",
        "generated.txt",
        "copy-of-README.md",
        "capture.json",
        "src/tool_defs.py",
    ):
        assert required in names, f"corpus-toy lost {required}"


def test_surveying_the_fixture_clears_both_gates(tmp_path):
    run = _survey(tmp_path)
    assert validate.validate_stage(run, "survey") == []
    assert refs.check_catalogue(run) == []


def test_the_fixture_produces_every_exclusion_reason_but_operator_excluded(tmp_path):
    """operator_excluded needs an --exclude flag, so it is the one reason a
    corpus alone cannot produce; test_survey_walk covers it."""
    catalogue = read_json(_survey(tmp_path).catalogue)
    produced = {entry["reason"] for entry in catalogue["excluded"]}
    assert produced == set(survey.EXCLUSION_REASONS) - {"operator_excluded"}


def test_the_exclusion_reasons_in_code_and_schema_cannot_drift(tmp_path):
    """validate.CONFIG_KINDS exists because {"agents", "gold"} drifted out of
    sync with a literal restated in tests. Same shape, same pin."""
    import json

    enum = json.loads(
        (validate.schema_dir() / "catalogue-0.1.json").read_text(encoding="utf-8")
    )["$defs"]["exclusion_reason"]["enum"]
    assert sorted(enum) == sorted(survey.EXCLUSION_REASONS)
```

Create `tests/unit/test_refs_catalogue.py`:

```python
"""Layer 2 over the catalogue: the conditional constraints the schema cannot say.

Spec §3 (Task 3): `path` / `container` / `provenance` are not mutually required
in JSON Schema because the constraint is conditional on `origin`, which Schema
expresses badly and layer 2 expresses plainly.
"""

from __future__ import annotations

from rubrica import refs
from rubrica.artifacts import read_json, write_json
from rubrica.paths import RunPaths


def _run_with(tmp_path, mutate):
    run = RunPaths(tmp_path / "run-20260814-213000")
    run.root.mkdir(parents=True)
    catalogue = {
        "schema_version": "0.1",
        "run_id": "run-20260814-213000",
        "created_utc": "2026-08-14T21:30:00Z",
        "request": {
            "target": {"name": "t", "interface": "i"},
            "objective": "breadth",
            "corpus_roots": ["/tmp/c"],
            "limits": {"max_rounds": 2, "max_scenarios": 128},
        },
        "policy": {
            "exclusion_reasons": ["binary"],
            "explode_min_elements": 3,
            "explode_min_common_keys": 3,
            "digest_body_chars": 2000,
            "max_candidates": 500,
        },
        "candidates": [
            {"candidate_id": "cap-json", "origin": "corpus", "path": "cap.json",
             "bytes": 10, "sha256": "a" * 64, "kind": "trace", "admissible": False,
             "digest": {}},
            {"candidate_id": "cap-json-0", "origin": "container_element",
             "container": {"candidate_id": "cap-json", "json_pointer": "/0"},
             "bytes": 5, "sha256": "b" * 64, "kind": "trace", "admissible": True,
             "digest": {}},
        ],
        "excluded": [],
    }
    mutate(catalogue)
    write_json(run.catalogue, catalogue)
    return run


def test_a_clean_catalogue_has_no_findings(tmp_path):
    assert refs.check_catalogue(_run_with(tmp_path, lambda c: None)) == []


def test_a_corpus_candidate_without_a_path_is_a_finding(tmp_path):
    def mutate(c):
        del c["candidates"][0]["path"]

    findings = refs.check_catalogue(_run_with(tmp_path, mutate))
    assert findings and "path" in str(findings[0])


def test_an_element_whose_container_does_not_resolve_is_a_finding(tmp_path):
    def mutate(c):
        c["candidates"][1]["container"]["candidate_id"] = "nope"

    findings = refs.check_catalogue(_run_with(tmp_path, mutate))
    assert findings and "nope" in str(findings[0])


def test_a_duplicate_candidate_id_is_a_finding(tmp_path):
    def mutate(c):
        c["candidates"][1]["candidate_id"] = "cap-json"

    findings = refs.check_catalogue(_run_with(tmp_path, mutate))
    assert findings and "cap-json" in str(findings[0])


def test_an_absent_catalogue_is_not_a_finding(tmp_path):
    """A run built through `intake --input` never had one, and spec §7.1 rules
    that its absence is not a finding -- the same ruling that makes intake's and
    smoke's absence from manifest.stages not a finding."""
    run = RunPaths(tmp_path / "run-20260814-213000")
    run.root.mkdir(parents=True)
    assert refs.check_catalogue(run) == []
```

- [ ] **Step 3: Run to verify they fail**

```
uv run pytest tests/unit/test_refs_catalogue.py tests/unit/test_survey_fixture.py -v
```

Expected: FAIL — `refs` has no `check_catalogue`, and the fixture does not exist.

- [ ] **Step 4: Implement `check_catalogue`**

In `src/rubrica/refs.py`, add beside `check_manifest`:

```python
def check_catalogue(run: RunPaths) -> list[Finding]:
    """Conditional constraints over 00-catalogue.json that layer 1 cannot state.

    An absent catalogue is not a finding: a run minted through `intake --input`
    never had one, and treating that as a defect would report every pre-triage
    run as broken. Same ruling as intake's and smoke's absence from
    manifest.stages.
    """
    catalogue = _load(run.catalogue)
    if not isinstance(catalogue, dict):
        return []
    out: list[Finding] = []

    def report(pointer: str, message: str) -> None:
        out.append(Finding(run.catalogue, "refs", pointer, message))

    candidates = catalogue.get("candidates")
    if not isinstance(candidates, list):
        return []

    ids = [c.get("candidate_id") for c in candidates if isinstance(c, dict)]
    for duplicate in _dupes([i for i in ids if isinstance(i, str)]):
        report("/candidates", f"duplicate candidate_id {duplicate!r}")
    known = {i for i in ids if isinstance(i, str)}

    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            continue
        origin = candidate.get("origin")
        pointer = f"/candidates/{index}"
        if origin == "corpus" and not candidate.get("path"):
            report(f"{pointer}/path", "a corpus candidate must carry the path it was read from")
        if origin == "container_element":
            container = candidate.get("container")
            if not isinstance(container, dict):
                report(f"{pointer}/container", "a container element must name its container")
                continue
            parent = container.get("candidate_id")
            if parent not in known:
                report(
                    f"{pointer}/container/candidate_id",
                    f"no such candidate {parent!r} to have been exploded from",
                )
        if origin == "projection" and not isinstance(candidate.get("provenance"), dict):
            report(
                f"{pointer}/provenance",
                "an adopted projection must record the projection_id it satisfies",
            )
    return out
```

Add `run.catalogue` and `run.triage` to `_readable_targets`, and
`findings.extend(check_catalogue(run))` as the **first** entry in `check_all`'s
list — before `check_manifest`, because a run between survey and intake has a
catalogue and no manifest.

- [ ] **Step 5: Run everything**

```
uv run pytest -q && make check && uv run rubrica check-skills
```

Expected: PASS, `check-skills` exits 0.

- [ ] **Step 6: Confirm the readable-targets rule still holds**

```
uv run pytest tests/unit/test_dispatch_harness.py -v
```

Expected: PASS. If `test_nothing_check_refs_reads_is_ever_denied` fails, the
dispatch script denies one of the two new paths — **fix the deny list, never the
test.** Denying a path `check-refs` reads is measured to make a stage's own gate
fabricate findings.

- [ ] **Step 7: Commit**

```bash
git add tests/fixtures/corpus-toy src/rubrica/refs.py tests/unit/test_refs_catalogue.py \
        tests/unit/test_survey_fixture.py
git commit -S -s -m "feat: Add the corpus fixture and layer 2 over the catalogue

check_catalogue holds the conditional constraints layer 1 cannot state: a
corpus candidate carries a path, an element's container resolves, an adopted
projection records its provenance. An absent catalogue is not a finding, per
spec §7.1 -- a run minted through intake --input never had one.

The fixture is guarded in both directions. tests/fixtures/toy-gap/ taught that
lesson: an over-subtraction there destroyed a capability fact while passing
every forbidden-substring check.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

# Phase 2 — The skill

Ends usefully: operation 2 of the spec's §1 — the judgment call that chose one
parsec surface out of six — becomes a stage with a contract, a schema and a gate.

### Task 9: The triage schema, including projections

**Files:**
- Create: `src/rubrica/schema/triage-0.1.json`
- Modify: `src/rubrica/validate.py` (ARTIFACT_SCHEMAS, STAGE_ARTIFACTS, `_artifact_paths`)
- Test: `tests/unit/test_schemas_triage.py` (new)

**Interfaces:**
- Consumes: `RunPaths.triage`.
- Produces: artifact kind `"triage"`; `STAGE_ARTIFACTS["triage"] == ("triage",)`.
  The `dispositions[]`, `deficiencies[]` and `projections[]` field names are the
  contract Task 11's prose, Task 10's checks, Task 15's `admit_from_triage` and
  Task 17's `adopt_projection` all key off.

- [ ] **Step 1: Write the schema**

Create `src/rubrica/schema/triage-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "triage-0.1.json",
  "title": "Triage record",
  "type": "object",
  "required": ["schema_version", "run_id", "objective_review", "dispositions",
               "deficiencies", "projections"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {"const": "0.1"},
    "run_id": {"$ref": "#/$defs/id"},
    "objective_review": {
      "type": "object",
      "required": ["declared_objective", "supported", "surfaces"],
      "additionalProperties": false,
      "properties": {
        "declared_objective": {"enum": ["breadth", "depth"]},
        "supported": {"type": "boolean"},
        "notes": {"type": "string", "minLength": 1},
        "recommended_objective": {
          "type": "object",
          "required": ["objective", "reason"],
          "additionalProperties": false,
          "properties": {
            "objective": {"enum": ["breadth", "depth"]},
            "reason": {"type": "string", "minLength": 1}
          }
        },
        "surfaces": {
          "type": "array",
          "minItems": 1,
          "items": {
            "type": "object",
            "required": ["name", "evidence", "weight"],
            "additionalProperties": false,
            "properties": {
              "name": {"type": "string", "minLength": 1},
              "evidence": {
                "type": "array",
                "minItems": 1,
                "items": {"$ref": "#/$defs/id"}
              },
              "weight": {
                "type": "object",
                "required": ["candidates", "bytes"],
                "additionalProperties": false,
                "properties": {
                  "candidates": {"type": "integer", "minimum": 1},
                  "bytes": {"type": "integer", "minimum": 0}
                }
              }
            }
          }
        }
      }
    },
    "dispositions": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["candidate_id", "disposition", "reason", "authority"],
        "additionalProperties": false,
        "properties": {
          "candidate_id": {"$ref": "#/$defs/id"},
          "disposition": {"enum": ["admit", "decline"]},
          "reason_code": {"$ref": "#/$defs/decline_reason"},
          "reason": {"type": "string", "minLength": 1},
          "priority": {"type": "integer", "minimum": 1},
          "authority": {"enum": ["triage", "human"]}
        }
      }
    },
    "deficiencies": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["deficiency_id", "subject", "statement"],
        "additionalProperties": false,
        "properties": {
          "deficiency_id": {"$ref": "#/$defs/id"},
          "subject": {"type": "string", "minLength": 1},
          "statement": {"type": "string", "minLength": 1},
          "closed_by": {"$ref": "#/$defs/id"}
        }
      }
    },
    "projections": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["projection_id", "closes", "sources", "wanted", "method",
                     "acceptance", "boundary"],
        "additionalProperties": false,
        "properties": {
          "projection_id": {"$ref": "#/$defs/id"},
          "closes": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/$defs/id"}
          },
          "sources": {
            "type": "array",
            "minItems": 1,
            "items": {
              "type": "object",
              "required": ["candidate_id", "digest_note"],
              "additionalProperties": false,
              "properties": {
                "candidate_id": {"$ref": "#/$defs/id"},
                "path": {"type": "string", "minLength": 1},
                "digest_note": {"type": "string", "minLength": 1}
              }
            }
          },
          "wanted": {
            "type": "object",
            "required": ["kind", "statement", "why"],
            "additionalProperties": false,
            "properties": {
              "kind": {"$ref": "#/$defs/kind"},
              "statement": {"type": "string", "minLength": 1},
              "why": {"type": "string", "minLength": 1}
            }
          },
          "method": {
            "type": "object",
            "required": ["confidence", "steps"],
            "additionalProperties": false,
            "properties": {
              "confidence": {"enum": ["high", "medium", "unknown"]},
              "steps": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "minLength": 1}
              }
            }
          },
          "acceptance": {
            "type": "object",
            "required": ["classifies_as", "prose"],
            "additionalProperties": false,
            "properties": {
              "classifies_as": {"$ref": "#/$defs/kind"},
              "pointers_required": {"type": "array", "items": {"type": "string", "minLength": 1}},
              "must_contain": {"type": "array", "items": {"type": "string", "minLength": 1}},
              "must_not_contain": {"type": "array", "items": {"type": "string", "minLength": 1}},
              "prose": {"type": "string", "minLength": 1}
            }
          },
          "boundary": {"type": "string", "minLength": 1},
          "satisfied_by": {"type": "string", "minLength": 1}
        }
      }
    }
  },
  "$defs": {
    "id": {"type": "string", "pattern": "\\A[A-Za-z0-9][A-Za-z0-9._-]*\\Z", "maxLength": 128},
    "kind": {
      "enum": ["openapi", "mcp_tool_schema", "entity_schema", "trace",
               "design_doc", "source_code", "other"]
    },
    "decline_reason": {
      "enum": ["off_objective", "out_of_scope", "near_duplicate", "superseded",
               "implementation_detail", "no_evidence_value", "digest_insufficient",
               "needs_projection"]
    }
  }
}
```

`acceptance.prose` is required while every structural key is optional, and that
ordering is the point: the structural checks are necessary and not sufficient, so
a projection brief with only mechanical criteria and no statement of what
"correct" means is incomplete. `surfaces` has `minItems: 1` because a triage that
enumerated no surfaces has not done the job spec §6.1 gives it.

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/test_schemas_triage.py`. Build a `_triage()` helper the way
`test_schemas_catalogue.py` builds `_catalogue()`, then assert:

```python
def test_a_well_formed_triage_record_validates(tmp_path):
    run = _write(tmp_path, _triage())
    assert validate.validate_stage(run, "triage") == []


def test_a_triage_with_no_surfaces_is_a_finding(tmp_path):
    """Spec §6.1: enumerating the surfaces is the job, not a courtesy. It is
    what would have made parsec's excluded-surface problem visible at gate 0."""
    review = _triage()["objective_review"] | {"surfaces": []}
    assert validate.validate_stage(_write(tmp_path, _triage(objective_review=review)), "triage")


def test_a_free_text_decline_reason_code_is_a_finding(tmp_path):
    """The codes are an enum so declines can be counted by shape. A free-text
    code makes 'what did this run drop' unanswerable."""
    dispositions = [_triage()["dispositions"][0] | {"reason_code": "seemed_irrelevant"}]
    assert validate.validate_stage(_write(tmp_path, _triage(dispositions=dispositions)), "triage")


def test_every_decline_reason_code_the_spec_names_is_accepted(tmp_path):
    """A code the schema rejects is a code the skill cannot use, which turns a
    declared decline into a schema failure at the gate."""
    import json

    enum = json.loads(
        (validate.schema_dir() / "triage-0.1.json").read_text(encoding="utf-8")
    )["$defs"]["decline_reason"]["enum"]
    assert set(enum) == {
        "off_objective", "out_of_scope", "near_duplicate", "superseded",
        "implementation_detail", "no_evidence_value", "digest_insufficient",
        "needs_projection",
    }


def test_a_projection_without_acceptance_prose_is_a_finding(tmp_path):
    """Structural acceptance is necessary, not sufficient. A brief with only
    mechanical criteria has not said what correct means, and the same rule
    forbids inventing a mechanical check for support in layer 2."""
    projection = _triage()["projections"][0]
    del projection["acceptance"]["prose"]
    assert validate.validate_stage(_write(tmp_path, _triage(projections=[projection])), "triage")
```

- [ ] **Step 3: Run to verify they fail**

```
uv run pytest tests/unit/test_schemas_triage.py -v
```

Expected: FAIL with `KeyError: 'triage'` from `STAGE_ARTIFACTS`.

- [ ] **Step 4: Wire layer 1**

`ARTIFACT_SCHEMAS`: `"triage": "triage-0.1.json"`. `STAGE_ARTIFACTS`:
`"triage": ("triage",)`. `_artifact_paths`:

```python
    if kind == "triage":
        return [run.triage] if run.triage.is_file() else []
```

- [ ] **Step 5: Run and commit**

```
uv run pytest -q && make check
git add src/rubrica/schema/triage-0.1.json src/rubrica/validate.py tests/unit/test_schemas_triage.py
git commit -S -s -m "feat: Add the triage schema -- dispositions, deficiencies, projections

surfaces has minItems 1 because enumerating them is the job spec §6.1 gives
triage, and acceptance.prose is required while every structural key is optional:
mechanical criteria are necessary and never sufficient.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

### Task 10: Layer 2 over the triage record

**Files:**
- Modify: `src/rubrica/refs.py` (new `check_triage`, wire into `check_all`)
- Test: `tests/unit/test_refs_triage.py` (new)

**Interfaces:**
- Consumes: `RunPaths.catalogue`, `RunPaths.triage`.
- Produces: `refs.check_triage(run: RunPaths) -> list[Finding]`, called from
  `check_all` immediately after `check_catalogue`.

**These are the checks that make declining visible.** Read spec §6.1 and §10.
Every one is reference resolution; none of them is semantic, and the one §11 asks
for that *would* be semantic is deliberately absent — it becomes a gate report in
Task 19 instead.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_refs_triage.py` with a `_run_with(tmp_path, mutate)`
helper writing both a catalogue (two candidates, `cap-json` and `readme-md`) and
a triage record, then:

```python
def test_a_clean_record_has_no_findings(tmp_path):
    assert refs.check_triage(_run_with(tmp_path, lambda t, c: None)) == []


def test_a_candidate_with_no_disposition_is_a_finding(tmp_path):
    """The coverage requirement is the whole mechanism.

    Without it, 'declined' and 'never considered' are the same absence -- which
    is exactly the confusion that left four parsec gaps indistinguishable from
    gaps nothing could close.
    """
    def mutate(triage, catalogue):
        triage["dispositions"] = [d for d in triage["dispositions"]
                                  if d["candidate_id"] != "readme-md"]

    findings = refs.check_triage(_run_with(tmp_path, mutate))
    assert findings and "readme-md" in str(findings[0])


def test_a_disposition_for_an_unknown_candidate_is_a_finding(tmp_path):
    """Triage cannot invent a candidate; a candidate it wishes existed is a
    deficiency."""
    def mutate(triage, catalogue):
        triage["dispositions"].append(
            {"candidate_id": "invented", "disposition": "admit", "reason": "x",
             "authority": "triage"}
        )

    findings = refs.check_triage(_run_with(tmp_path, mutate))
    assert findings and "invented" in str(findings[0])


def test_two_dispositions_for_one_candidate_is_a_finding(tmp_path):
    def mutate(triage, catalogue):
        triage["dispositions"].append(dict(triage["dispositions"][0]))

    assert refs.check_triage(_run_with(tmp_path, mutate)) != []


def test_a_decline_without_a_reason_code_is_a_finding(tmp_path):
    """Required on declines and forbidden on admits: a conditional constraint,
    so it lives here rather than in an if/then the schema expresses badly."""
    def mutate(triage, catalogue):
        for d in triage["dispositions"]:
            if d["disposition"] == "decline":
                d.pop("reason_code", None)

    assert refs.check_triage(_run_with(tmp_path, mutate)) != []


def test_an_admit_carrying_a_decline_reason_code_is_a_finding(tmp_path):
    def mutate(triage, catalogue):
        for d in triage["dispositions"]:
            if d["disposition"] == "admit":
                d["reason_code"] = "off_objective"

    assert refs.check_triage(_run_with(tmp_path, mutate)) != []


def test_a_digest_insufficient_decline_unreferenced_by_a_deficiency_is_a_finding(tmp_path):
    """Spec §6.1: the two codes whose purpose is to make a loss visible would
    otherwise be the quietest way to lose something. A decline nothing points at
    reads exactly like a decline that was fine."""
    def mutate(triage, catalogue):
        triage["deficiencies"] = []

    findings = refs.check_triage(_run_with(tmp_path, mutate, decline_code="digest_insufficient"))
    assert findings and "digest_insufficient" in str(findings[0])


def test_a_needs_projection_decline_unreferenced_by_a_projection_is_a_finding(tmp_path):
    def mutate(triage, catalogue):
        triage["projections"] = []

    assert refs.check_triage(_run_with(tmp_path, mutate, decline_code="needs_projection")) != []


def test_a_projection_closing_an_unknown_deficiency_is_a_finding(tmp_path):
    def mutate(triage, catalogue):
        triage["projections"][0]["closes"] = ["def-nope"]

    findings = refs.check_triage(_run_with(tmp_path, mutate))
    assert findings and "def-nope" in str(findings[0])


def test_a_projection_source_that_is_not_a_candidate_is_a_finding(tmp_path):
    def mutate(triage, catalogue):
        triage["projections"][0]["sources"][0]["candidate_id"] = "ghost"

    assert refs.check_triage(_run_with(tmp_path, mutate)) != []


def test_an_admitted_inadmissible_candidate_is_a_finding(tmp_path):
    """A container is in the catalogue so a reader can see where elements came
    from. Admitting it hands one stage every record at once."""
    def mutate(triage, catalogue):
        for d in triage["dispositions"]:
            if d["candidate_id"] == "cap-json":
                d["disposition"] = "admit"
                d.pop("reason_code", None)

    findings = refs.check_triage(_run_with(tmp_path, mutate))
    assert findings and "admissible" in str(findings[0])


def test_zero_admits_is_a_finding_naming_the_triage_record(tmp_path):
    """An empty admitted set is a scoping failure, not a triage result -- and it
    is exit 1 against 00-triage.json, repairable by re-dispatching, never exit 2."""
    def mutate(triage, catalogue):
        for d in triage["dispositions"]:
            d["disposition"] = "decline"
            d["reason_code"] = "off_objective"

    findings = refs.check_triage(_run_with(tmp_path, mutate))
    assert findings and "00-triage.json" in str(findings[0].artifact)


def test_an_absent_triage_record_is_not_a_finding(tmp_path):
    """Spec §7.1 again: a run built through intake --input never had one."""
    run = RunPaths(tmp_path / "run-20260814-213000")
    run.root.mkdir(parents=True)
    assert refs.check_triage(run) == []
```

- [ ] **Step 2: Run to verify they fail**

```
uv run pytest tests/unit/test_refs_triage.py -v
```

Expected: FAIL, `refs` has no `check_triage`.

- [ ] **Step 3: Implement**

In `src/rubrica/refs.py`, after `check_catalogue`:

```python
def check_triage(run: RunPaths) -> list[Finding]:
    """Reference checks over 00-triage.json. Nothing here is semantic.

    The finding spec §11 actually asks for -- a world-model gap whose closing
    evidence was declined at triage -- is deliberately NOT here. Matching gap
    prose to decline prose is semantic, and layer 2 checks that an element
    *references* a resolvable thing and never that the thing *supports* it. That
    pairing is a human's call at gate 1, surfaced by `rubrica gate-brief`.
    """
    triage = _load(run.triage)
    if not isinstance(triage, dict):
        return []
    catalogue = _load(run.catalogue)
    out: list[Finding] = []

    def report(pointer: str, message: str) -> None:
        out.append(Finding(run.triage, "refs", pointer, message))

    dispositions = triage.get("dispositions") or []
    deficiency_ids = {
        d.get("deficiency_id")
        for d in (triage.get("deficiencies") or [])
        if isinstance(d, dict)
    }
    projections = triage.get("projections") or []
    projection_ids = {
        p.get("projection_id") for p in projections if isinstance(p, dict)
    }

    candidates = {}
    if isinstance(catalogue, dict):
        candidates = {
            c["candidate_id"]: c
            for c in (catalogue.get("candidates") or [])
            if isinstance(c, dict) and isinstance(c.get("candidate_id"), str)
        }

    seen: set[str] = set()
    admits = 0
    for index, entry in enumerate(dispositions):
        if not isinstance(entry, dict):
            continue
        pointer = f"/dispositions/{index}"
        cid = entry.get("candidate_id")
        if candidates and cid not in candidates:
            report(f"{pointer}/candidate_id", f"no such candidate {cid!r} in the catalogue")
        if cid in seen:
            report(f"{pointer}/candidate_id", f"candidate {cid!r} already has a disposition")
        seen.add(cid)

        code = entry.get("reason_code")
        if entry.get("disposition") == "decline":
            if not code:
                report(f"{pointer}/reason_code", "a decline must carry a reason_code")
            elif code == "digest_insufficient" and not deficiency_ids:
                report(
                    f"{pointer}/reason_code",
                    "a digest_insufficient decline must be referenced by a deficiency, or the "
                    "loss it records is invisible",
                )
            elif code == "needs_projection" and not projection_ids:
                report(
                    f"{pointer}/reason_code",
                    "a needs_projection decline must be referenced by a projection, or its "
                    "remedy is unstated",
                )
        else:
            admits += 1
            if code:
                report(f"{pointer}/reason_code", "reason_code names a decline; an admit has none")
            if cid in candidates and candidates[cid].get("admissible") is False:
                report(
                    f"{pointer}/disposition",
                    f"candidate {cid!r} is not admissible -- it is a container whose elements "
                    "are the candidates",
                )

    for cid in sorted(set(candidates) - seen):
        report("/dispositions", f"candidate {cid!r} has no disposition; every one must be ruled on")

    if dispositions and admits == 0:
        report(
            "/dispositions",
            "no candidate was admitted; an empty admitted set is a scoping failure rather than "
            "a triage result",
        )

    for index, projection in enumerate(projections):
        if not isinstance(projection, dict):
            continue
        pointer = f"/projections/{index}"
        for closes in projection.get("closes") or []:
            if closes not in deficiency_ids:
                report(f"{pointer}/closes", f"no such deficiency {closes!r}")
        for position, source in enumerate(projection.get("sources") or []):
            if isinstance(source, dict) and candidates and source.get("candidate_id") not in candidates:
                report(
                    f"{pointer}/sources/{position}/candidate_id",
                    f"no such candidate {source.get('candidate_id')!r} to project from",
                )
    return out
```

Wire `findings.extend(check_triage(run))` into `check_all` right after
`check_catalogue`.

- [ ] **Step 4: Run and commit**

```
uv run pytest -q && make check
git add src/rubrica/refs.py tests/unit/test_refs_triage.py
git commit -S -s -m "feat: Check the triage record's references, and nothing semantic

Every candidate gets exactly one disposition, and a digest_insufficient or
needs_projection decline must be referenced by a deficiency or a projection --
the two codes whose purpose is making a loss visible would otherwise be the
quietest way to lose something.

The finding §11 asks for is deliberately absent: matching gap prose to decline
prose is semantic, and layer 2 resolves references rather than judging support.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

### Task 11: `rb-triage`

**Files:**
- Create: `src/rubrica/skills/rb-triage/SKILL.md`
- Test: `tests/unit/test_skills_triage.py` (new)

**Interfaces:**
- Consumes: the catalogue field names from Task 3, the triage field names from
  Task 9, `digest.TRACE_HEURISTICS`.
- Produces: a ninth skill that `skills.check_all` accepts. `reads = ["catalogue"]`
  is a single entry, and `check_contract` resolves it against `RunPaths` — so
  Task 2's property name is what makes this contract legal.

**Read `src/rubrica/skills/rb-extract/SKILL.md` first** for the house voice: it
addresses the dispatched member directly, explains *why* each boundary exists,
and names the failure the boundary prevents.

- [ ] **Step 1: Write the skill**

Create `src/rubrica/skills/rb-triage/SKILL.md`:

````markdown
---
name: rb-triage
description: Rule on every candidate in a run's catalogue against the declared objective -- admit, or decline with a reason -- and state what the admitted set cannot cover.
---

# rb-triage

You decide what this run will be able to know.

Every candidate you decline is a fact about the target that no later stage can
recover, because nothing downstream reads the corpus -- `rb-extract` reads only
what `intake` admitted, and `intake` admits only what you marked `admit`. There
is no stage after you that can notice you were wrong. That is why your output
records a reason for every single candidate rather than a list of the ones you
kept: a human holds a gate on this record, and they can only overturn a decision
they can see.

The failure this stage exists to prevent has been measured. On 2026-08-13 a run
selected sixteen inputs by hand and excluded, among other things, the files that
declared what each of the target's thirteen tools returns. Six scenarios later
died because no artifact carried those shapes, and the world model recorded the
absence as four gaps that looked identical to gaps nothing could ever close. The
information that would have distinguished them -- *this was declined, and here is
why* -- existed only in a conversation that no longer exists.

## Contract

```toml
stage = "triage"
reads = ["catalogue"]
writes = ["triage"]
schemas = ["triage"]
invokes = ["validate"]
```

## 1. Inputs

You read exactly one file: `00-catalogue.json`.

Not the corpus. The catalogue's candidates name paths on disk, and some of those
paths exist and are readable right now. **Opening one is out of contract.** The
prohibition is on opening the file, not on what you would have taken from it,
for two reasons that are worth stating because the temptation is real and
constant.

The first is cost. The catalogue exists so that your judgment costs one bounded
digest per candidate instead of the whole corpus. A corpus can be gigabytes; a
catalogue is a few hundred kilobytes. Opening candidates one by one to "check"
them is how a stage that was designed to be affordable becomes the most
expensive one in the pipeline.

The second matters more. The digests are the same width for every candidate, so
your reasons are comparable — "declined, no tool schema in the digest" means the
same thing said about candidate 3 and candidate 300. Once you have read some
candidates in full and others only as digests, your record no longer says what
it appears to say, and nobody reading it can tell which decisions were made on
which basis.

What you get for each candidate: its `candidate_id`, `kind`, `bytes`, `sha256`,
`origin`, its `path` or the `container` it was exploded out of, and its `digest`.
What the digest contains depends on the kind, and it is described in §2 of
`policy` and in the digest itself. **The field that matters most is
`heuristics_fired`**, on trace digests: it lists which extractors found
something. A heuristic missing from that list found nothing, which is a fact
about the digest and not about the candidate.

`request` carries what you are being asked for: the target's name and
interface, the `objective` (`breadth` or `depth`), and optionally an
`objective_note` and a `scope_note`. `policy` carries the rules that shaped the
set — which exclusion reasons were in force, the explosion thresholds, the
digest caps. `excluded` lists what `survey` dropped mechanically and why; read
it, because a mechanical exclusion you believe was wrong is a `deficiencies[]`
entry, not something to stay quiet about.

You are dispatched with no memory of any conversation before you, and nothing
you write carries forward as memory. What you need is in this document or in
that one file.

## 2. Output

One file: `00-triage.json`, validating against `triage-0.1.json`.

**`objective_review`** — the surfaces you found, and whether the objective you
were given is supported by them.

A *surface* is a coherent region of the target's behaviour that a suite could
be built about: a persona, an API area, a workflow, a subsystem. You are not
guessing at the target's internal structure; you are grouping the evidence in
front of you by what it is evidence *about*. For each one: a `name`, the
`evidence` candidate ids, and a `weight` of `{candidates, bytes}` — both
arithmetic over the catalogue, so a reader can check them.

`declared_objective` echoes `request.objective`. `supported` is your judgment on
whether the evidence can carry it: `depth` on a surface with one candidate is
not supported, and neither is `breadth` when eleven of twelve surfaces have no
behavioural evidence at all. If you would have chosen differently, say so in
`recommended_objective` with a reason. **You may not act on that
recommendation.** Select against the objective you were given, and let the human
at the gate decide whether to change it — a re-scope you perform yourself is
invisible, and it produces a selection that looks coherent and answers a
question nobody asked.

Enumerating the surfaces is not a courtesy. It is the part of this record that
lets a human see that the objective they declared excludes something they wanted.

**`dispositions[]`** — **one entry for every candidate in the catalogue, exactly
once, including the ones you decline and the ones marked
`admissible: false`.** A container is inadmissible because its elements are the
real candidates; decline it, and say that is why.

An `admit` carries `reason` (prose) and a `priority` — an integer rank, 1 for
the most valuable, expressing where you would spend the extraction budget first.
No code acts on `priority`; it orders the human's reading.

A `decline` carries `reason` (prose) and a `reason_code` from this list:

| Code | Use it when |
|---|---|
| `off_objective` | Real evidence about the target, but not about what this run is for |
| `out_of_scope` | Belongs to a surface `scope_note` excludes |
| `near_duplicate` | An admitted candidate carries the same shape; name it in `reason` |
| `superseded` | Something more authoritative says the same thing; name it |
| `implementation_detail` | Describes how, where the objective needs what |
| `no_evidence_value` | Carries no statement about the target at all |
| `digest_insufficient` | You cannot rule on it from its digest |
| `needs_projection` | Valuable, not usable as-is; write the projection |

`digest_insufficient` and `needs_projection` each oblige you to write something
else — a `deficiencies[]` entry for the first, a `projections[]` entry for the
second — and `check-refs` will reject the record if you don't. Those two codes
exist to make a loss visible, so a decline nothing else points at is worse than
no code at all.

**`deficiencies[]`** — what the admitted set cannot cover that the objective
needs. Each has a `deficiency_id`, a `subject` naming the thing that is missing,
and a `statement` saying what will not be answerable without it.

This is the block that would have prevented the failure in the header. Ask it
directly, every time: *for each capability the admitted set implies, does
anything in the admitted set declare what it returns?* If not, that is a
deficiency, and writing it costs one paragraph now instead of six dead scenarios
later.

**`projections[]`** — a brief for something that has to be manufactured. See §3
step 6.

## 3. Method

**Step 1 — read `request` first, before any candidate.** The objective decides
every subsequent call, and a reading that starts from the candidates arrives at
a scope and then rationalises the objective to fit it.

**Step 2 — group every candidate into a surface.** Work from `path`, `kind`, and
the digest's own contents: a prose document's headings, a trace's `request_text`
and `names`, a source file's `assignments` and `defs`. Every candidate belongs
to exactly one surface for the purpose of this pass, including ones you will
decline — a surface with nothing but declines is exactly what a human needs to
see.

**Step 3 — weigh each surface and rule on the objective.** Count candidates and
bytes per surface. Then answer: can the declared objective be met from this?
Write `supported`, and `recommended_objective` if you disagree.

**Step 4 — rule on every candidate.** Prefer behavioural evidence over prose
about behaviour: a trace records what the target *did*, prose records what
someone intended. Both are legitimate, and when they conflict that conflict is
itself worth admitting rather than resolving — `rb-reconcile` records
contradictions and is better placed to.

For near-duplicates, admit the one with the most distinct shape rather than the
largest or the newest. On the 2026-08-13 corpus, seven traces of 130 were kept
for distinct shape — one aggregation, two triages, two multi-hop debugs, one
identity lookup, and one failure — and that last one was the run's only evidence
of what the target does when something goes wrong. **A failing trace is almost
never a near-duplicate of a successful one**, however similar its request looks.

**Step 5 — check for absence, not just presence.** Walk the capabilities the
admitted set implies and ask what each one's result shape is declared in. Walk
the surfaces and ask which have no behavioural evidence. Each answer that comes
back empty is a `deficiencies[]` entry.

**Step 6 — write a projection for anything valuable that is not usable as-is.**

A projection is a work order someone else executes — a human tonight, possibly a
subagent later — so it has to be complete without you. It needs: `sources` (the
candidate ids and what their digests told you), `wanted` (the `kind`, a
`statement` of the artifact, and `why` it matters), `method` (`steps`, and a
`confidence` of `high`, `medium` or `unknown` — **`unknown` is an honest value**;
you usually cannot know an extraction method from a digest, and a confident-
sounding wrong method is worse than an admitted gap), `acceptance`, and a
`boundary` saying what must not be included.

`acceptance` is how the worker knows they are done: `classifies_as`,
`pointers_required`, `must_contain` (the exact strings that must appear),
`must_not_contain` (the scope boundary, as strings), and `prose`. The four
structural fields are checked mechanically by `rubrica adopt-projection`. They
are necessary and never sufficient — `prose` is where you say what *correct*
means, and a brief without it has not specified anything.

**Step 7 — run your gate.** `rubrica validate --stage triage --run <RUN>`. Fix
what it reports and run it again. Then `rubrica check-refs --run <RUN>`, which
will tell you if any candidate went unruled or any code went unreferenced.

## 4. Invariants

1. **Exactly one disposition per catalogue candidate.** Not fewer: an unruled
   candidate is indistinguishable from one nobody saw. Not more.
2. **Nothing in `dispositions[]` that is not in `candidates[]`.** A candidate you
   wish existed is a `deficiencies[]` entry.
3. **At least one admit.** An empty admitted set is a scoping failure; see §5.
4. **Never admit a candidate whose `admissible` is `false`.**
5. **Every `digest_insufficient` decline is referenced by a deficiency, and every
   `needs_projection` decline by a projection.**
6. **`weight` is arithmetic over the catalogue**, not an impression. A reader
   recomputes it.
7. **You read `00-catalogue.json` and nothing else.** No candidate file, no
   `decisions.md`, no artifact from another run.
8. **`recommended_objective` is a recommendation.** Your selection is against
   `request.objective` as written.

## 5. Refusal conditions

Each of these means: write no `00-triage.json`, and report what you found and
why you stopped. A partial record is worse than none, because it passes layer 1
and the gate reads it as complete.

**Refuse if `request.objective` is absent, or contradicts `scope_note`.** A
triage held to no objective cannot be held to anything, and this stage exists
because that judgment was previously unwritten. If the objective says `breadth`
and `scope_note` confines the run to one surface, those are two different runs;
say so and stop.

**Refuse if you would decline every candidate.** Zero admits is not a result you
can report by writing it down — it means the corpus, the objective, or the scope
is wrong, and all three are outside your authority to change. Report which one
you believe it is.

**Refuse if the catalogue has no candidates at all**, or if it is not readable as
the schema describes. That is a `survey` defect or a broken run, and producing a
record against it would attribute a scoping decision to a stage that never ran.

**Do not refuse when the declared objective is unsupported.** Write the record,
set `objective_review.supported` to `false`, state why, and let the gate rule.
Refusing here would leave the human with nothing to rule *on*, which is the
opposite of the help they need.

**Do not refuse for a candidate you cannot judge.** Decline it
`digest_insufficient`, name the field you needed in `reason`, and write the
matching deficiency. One unreadable digest is not a reason to abandon three
hundred good decisions.
````

- [ ] **Step 2: Verify the contract mechanically**

```
uv run rubrica check-skills
```

Expected: exit 0. If it reports that `catalogue` is not a `RunPaths` attribute,
Task 2 was not completed. If it reports sections out of order, the five headings
must be exactly `1. Inputs`, `2. Output`, `3. Method`, `4. Invariants`,
`5. Refusal conditions` in that order.

- [ ] **Step 3: Write the prose tests**

Create `tests/unit/test_skills_triage.py`. **Every predicate must be scoped with
`skills.section_body`** — `"refusal" in skill.body.lower()` is vacuous for every
conforming skill, because `body` is the whole file and the five headings are
mandatory.

```python
"""Prose predicates for rb-triage, each scoped to the section that owns the rule.

Roughly nineteen assertions in this repo were measured satisfiable by unrelated
content before this convention existed. Step 4 of this task measures each of
these in both directions; a predicate nobody has watched fail is not a guard.
"""

from __future__ import annotations

import re

from rubrica import digest, skills


def _skill():
    return next(s for s in skills.load_all() if s.name == "rb-triage")


def _norm(text):
    """Whitespace-normalised, so a reflow does not break a phrase pin.

    399dba5 fixed exactly this: two phrase pins broke on an innocuous reformat.
    """
    return re.sub(r"\s+", " ", text.lower())


def test_the_inputs_section_forbids_opening_a_candidate_file():
    """The catalogue-only rule is the design's cost bound and its comparability
    guarantee. It has to be stated where a reader looking for what to read looks."""
    body = _norm(skills.section_body(_skill(), "1. Inputs"))
    assert "00-catalogue.json" in body
    assert "not the corpus" in body
    assert "out of contract" in body


def test_the_inputs_section_names_heuristics_fired_as_a_fact_about_the_digest():
    """Spec §5.3's mitigation only works if the skill knows what the field means:
    a heuristic that did not fire is a fact about the digest, not the candidate."""
    body = _norm(skills.section_body(_skill(), "1. Inputs"))
    assert "heuristics_fired" in body
    assert "about the digest" in body


def test_every_named_trace_heuristic_is_reachable_from_the_skill_or_the_code():
    """A heuristic the code emits and the skill never mentions is invisible to
    the judgment that depends on it."""
    body = _norm(_skill().body)
    assert all(h in body or h == "element_counts" for h in digest.TRACE_HEURISTICS) or True
    # The real assertion: the code's list is non-empty and the skill names the
    # field that carries it. Enumerating each heuristic in prose would pin
    # digest.py's internals to a document, which 2f93726 warns against.
    assert digest.TRACE_HEURISTICS
    assert "heuristics_fired" in body


def test_the_method_section_requires_the_absence_check():
    """Step 5 is the block that would have predicted six parsec refusals."""
    body = _norm(skills.section_body(_skill(), "3. Method"))
    assert "result shape" in body
    assert "deficien" in body


def test_the_method_section_protects_a_failing_trace_from_near_duplicate_folding():
    """The one ERROR trace in 130 was the parsec run's only evidence of failure
    behaviour, and near_duplicate is exactly how it would have been lost."""
    body = _norm(skills.section_body(_skill(), "3. Method"))
    assert "failing trace" in body
    assert "near-duplicate" in body


def test_the_method_section_admits_unknown_as_a_method_confidence():
    body = _norm(skills.section_body(_skill(), "3. Method"))
    assert "unknown" in body and "honest" in body


def test_the_method_section_says_structural_acceptance_is_not_sufficient():
    body = _norm(skills.section_body(_skill(), "3. Method"))
    assert "never sufficient" in body or "not sufficient" in body


def test_the_invariants_section_requires_one_disposition_per_candidate():
    body = _norm(skills.section_body(_skill(), "4. Invariants"))
    assert "exactly one disposition" in body
    assert "not fewer" in body


def test_the_invariants_section_forbids_acting_on_a_recommended_objective():
    """A re-scope the stage performs itself is invisible, and produces a
    selection that looks coherent and answers a question nobody asked."""
    body = _norm(skills.section_body(_skill(), "4. Invariants"))
    assert "recommended_objective" in body
    assert "recommendation" in body


def test_the_refusal_section_refuses_a_missing_objective_and_an_empty_admit_set():
    body = _norm(skills.section_body(_skill(), "5. Refusal conditions"))
    assert "objective" in body and "absent" in body
    assert "every candidate" in body and "zero admits" in body


def test_the_refusal_section_forbids_refusing_on_an_unsupported_objective():
    """Refusing there leaves the human nothing to rule on, which is the opposite
    of the help gate 0 needs."""
    body = _norm(skills.section_body(_skill(), "5. Refusal conditions"))
    assert "do not refuse" in body
    assert "unsupported" in body


def test_the_refusal_section_forbids_refusing_over_one_bad_digest():
    body = _norm(skills.section_body(_skill(), "5. Refusal conditions"))
    assert "digest_insufficient" in body
    assert "three hundred" in body or "not a reason to abandon" in body
```

Delete the third test's `or True` line and its confused first assertion — write
only the two real assertions. It is written above the way it should *not* be, as
a warning: an assertion ending in `or True` cannot fail, and that shape has
shipped in this repo before.

- [ ] **Step 4: Measure every predicate in both directions**

Not optional, and not skippable under time pressure — this is the step that
turns predicates into guards.

```bash
cp -r src/rubrica/skills /tmp/skills-probe
for heading in "1. Inputs" "3. Method" "4. Invariants" "5. Refusal conditions"; do
  echo "=== blanking $heading ==="
  # Blank that section's body in /tmp/skills-probe/rb-triage/SKILL.md by hand,
  # then:
  RUBRICA_SKILLS_DIR=/tmp/skills-probe uv run pytest tests/unit/test_skills_triage.py -q
  # Expected: RED for every predicate scoped to that section, GREEN for others.
  # Restore the section before the next iteration.
done
```

Then the mirror direction: reword each pinned phrase meaning-preservingly in the
`/tmp` copy and confirm the tests **stay green**. A pin that breaks on an
innocuous rewording is the failure `399dba5` fixed, and `_norm` exists for it.
If a predicate cannot survive a rewording, weaken the pin to the concept rather
than deleting the test.

Record, in the commit message, which predicates you watched go red.

- [ ] **Step 5: Run everything and commit**

```
uv run pytest -q && make check && uv run rubrica check-skills
```

```bash
git add src/rubrica/skills/rb-triage/SKILL.md tests/unit/test_skills_triage.py
git commit -S -s -m "feat: Add rb-triage, the ninth skill

reads = ['catalogue'] -- one entry, so check_skills enforces the catalogue-only
rule through the same check it already applies to every other stage.

Its header states the measured failure it exists to prevent: six parsec
scenarios died for tool result shapes nothing declared, and the world model
recorded four gaps indistinguishable from gaps nothing could close, because the
information that would have separated them lived in a conversation.

All <N> prose predicates measured in both directions under RUBRICA_SKILLS_DIR:
<list which went red on which section>.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

### Task 12: Refusal fixtures, dispatch, and the runbook

**Files:**
- Create: `tests/fixtures/catalogue-unsupported-objective.json`,
  `tests/fixtures/catalogue-all-declinable.json`,
  `tests/unit/test_triage_refusal_fixtures.py`
- Modify: `docs/running-a-stage-by-hand.md`, `tests/unit/test_dispatch_harness.py`

**Interfaces:**
- Consumes: the catalogue schema; `survey.EXPLODE_MIN_ELEMENTS`.
- Produces: two committed catalogues that fire refusal conditions 1 and 2, for
  the live exercise to run against.

**These fixtures are catalogue JSON files, not corpora** — triage reads only the
catalogue, so a negative fixture is one small file rather than a whole tree. That
is the one place this phase is cheaper than the existing refusal fixtures.

- [ ] **Step 1: Write the two fixtures**

`tests/fixtures/catalogue-unsupported-objective.json` — a valid catalogue whose
`request.objective` is `depth` while exactly one candidate carries any
behavioural evidence. It must validate against `catalogue-0.1.json`: the defect
is semantic, and a fixture that fails layer 1 tests the schema instead of the
prompt.

`tests/fixtures/catalogue-all-declinable.json` — a valid catalogue whose
`request.scope_note` confines the run to a surface no candidate touches, so every
candidate is `out_of_scope`.

- [ ] **Step 2: Write the fixture guards**

Create `tests/unit/test_triage_refusal_fixtures.py`:

```python
"""Both directions on the two negative catalogues.

tests/unit/test_refusal_fixtures.py guards the existing pair this way for a
measured reason: an over-subtraction once destroyed a capability fact while
passing every forbidden-substring check. So each fixture is checked for still
carrying its defect AND for not having lost anything else.
"""

from __future__ import annotations

import json
from pathlib import Path

from rubrica import validate
from rubrica.paths import RunPaths

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _staged(tmp_path, name):
    run = RunPaths(tmp_path / "run-20260814-213000")
    run.root.mkdir(parents=True)
    run.catalogue.write_text((FIXTURES / name).read_text(encoding="utf-8"), encoding="utf-8")
    return run


def test_both_fixtures_clear_layer_one(tmp_path):
    """The defect is semantic. A fixture that fails validate tests the schema."""
    for name in ("catalogue-unsupported-objective.json", "catalogue-all-declinable.json"):
        assert validate.validate_stage(_staged(tmp_path, name), "survey") == [], name


def test_the_unsupported_objective_fixture_still_declares_depth():
    catalogue = json.loads(
        (FIXTURES / "catalogue-unsupported-objective.json").read_text(encoding="utf-8")
    )
    assert catalogue["request"]["objective"] == "depth"


def test_the_unsupported_objective_fixture_still_has_only_one_behavioural_candidate():
    """This is the subtraction. If a second trace creeps in, depth becomes
    arguably supportable and the fixture stops firing refusal condition 3."""
    catalogue = json.loads(
        (FIXTURES / "catalogue-unsupported-objective.json").read_text(encoding="utf-8")
    )
    traces = [c for c in catalogue["candidates"] if c["kind"] == "trace" and c["admissible"]]
    assert len(traces) == 1


def test_the_unsupported_objective_fixture_has_not_lost_its_other_candidates():
    """Over-subtraction check: it still has enough prose to make a real triage
    pass possible, so the refusal is about the objective and not about emptiness."""
    catalogue = json.loads(
        (FIXTURES / "catalogue-unsupported-objective.json").read_text(encoding="utf-8")
    )
    assert len([c for c in catalogue["candidates"] if c["kind"] == "design_doc"]) >= 3


def test_the_all_declinable_fixture_scope_note_names_nothing_in_the_set():
    catalogue = json.loads(
        (FIXTURES / "catalogue-all-declinable.json").read_text(encoding="utf-8")
    )
    scope = catalogue["request"]["scope_note"].lower()
    assert catalogue["candidates"]
    for candidate in catalogue["candidates"]:
        assert candidate.get("path", "").lower() not in scope
```

- [ ] **Step 3: Extend the dispatch-harness tests**

In `tests/unit/test_dispatch_harness.py`, add `triage` to whatever parametrization
enumerates dispatchable stages, and add:

```python
def test_the_triage_dispatch_denies_the_decisions_log():
    """Every stage's dispatch denies decisions.md: a propose dispatch was
    measured one Read from the run's answer key on 2026-08-13."""
    settings = _settings_for("triage")
    assert any("decisions.md" in rule for rule in _deny_rules(settings))


def test_the_triage_dispatch_does_not_deny_the_catalogue_it_must_read():
    """The mirror of the rule that cost two wrong denies: 2f93726 measured that
    denying a path check-refs reads makes a stage's own gate fabricate findings.
    The catalogue is both triage's only input and a path check_catalogue reads."""
    settings = _settings_for("triage")
    assert not any("00-catalogue.json" in rule for rule in _deny_rules(settings))
```

Follow the existing helpers in that file rather than inventing `_settings_for` and
`_deny_rules` if they already exist under other names. These tests **skip** rather
than fail on a machine without `claude` or `jq` on `PATH`, so a green run there is
not evidence — check how the existing tests do that and match it.

- [ ] **Step 4: Add the runbook entry**

In `docs/running-a-stage-by-hand.md`, add `triage` to the stage table and a
worked dispatch:

```
scripts/dispatch-stage.sh triage "$RUN"
```

with a note that triage takes no slice id (it is a barrier) and that its gate is
`rubrica validate --stage triage --run "$RUN"` followed by
`rubrica check-refs --run "$RUN"`.

- [ ] **Step 5: Run everything and commit**

```
uv run pytest -q && make check && uv run rubrica check-skills
```

```bash
git add tests/fixtures/catalogue-*.json tests/unit/test_triage_refusal_fixtures.py \
        tests/unit/test_dispatch_harness.py docs/running-a-stage-by-hand.md
git commit -S -s -m "test: Add the two triage refusal fixtures and dispatch coverage

Negative fixtures here are catalogue files rather than corpora, because triage
reads only the catalogue -- so each is one small document with exactly one thing
subtracted, guarded in both directions.

The dispatch tests pin both halves of the deny rule: decisions.md is denied, and
00-catalogue.json is not, because denying a path check-refs reads was measured to
make a stage's own gate fabricate findings.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

# Phase 3 — Admission

Ends usefully: the pipeline runs end to end from a corpus, and operation 5 of the
spec's §1 stops being manual.

### Task 13: Split `intake`, and materialise a container element

**Files:**
- Modify: `src/rubrica/intake.py`, `src/rubrica/schema/manifest-0.1.json`
- Test: `tests/unit/test_intake_split.py` (new), `tests/unit/test_schemas_planning.py`

**Interfaces:**
- Consumes: `artifacts.canonical_bytes` (Task 7), `refs.resolve_pointer`.
- Produces:
  - `intake.mint_run(runs_dir: Path, *, now: datetime | None = None) -> tuple[RunPaths, datetime]`
    — creates the directory, returns it and the resolved UTC stamp.
  - `intake.register(run: RunPaths, *, entries: list[dict], target_name: str,
    target_interface: str, max_rounds: int, max_scenarios: int, created: datetime) -> None`
    — writes `manifest.json` from already-built input entries.
  - `intake.materialise(run: RunPaths, *, candidate: dict, source_root: Path,
    artifact_id: str) -> dict` — copies or writes one input into `00-inputs/` and
    returns its `manifest.inputs[]` entry, including `provenance` when the
    candidate came from a container or a projection.
  - `manifest-0.1.json` gains optional `inputs[].provenance`.
  - **`intake.intake()`'s signature and behaviour are unchanged.** All twenty
    existing call sites and `tests/toy.py` must keep passing untouched.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_intake_split.py`:

```python
"""The split, and the invariant that survives it.

intake() keeps its exact signature because twenty call sites and
tests/toy.py's build_toy_run depend on it. What changes is that survey can now
mint a run without writing a manifest, and admit can write a manifest into a
run it did not mint.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rubrica import intake, refs, validate
from rubrica.artifacts import canonical_bytes, read_json

NOW = datetime(2026, 8, 14, 21, 30, 0, tzinfo=UTC)


def test_mint_run_creates_a_directory_and_no_manifest(tmp_path):
    run, stamp = intake.mint_run(tmp_path / "runs", now=NOW)
    assert run.root.is_dir()
    assert run.root.name == "run-20260814-213000"
    assert stamp == NOW
    assert not run.manifest.exists()


def test_mint_run_refuses_an_existing_run_directory(tmp_path):
    intake.mint_run(tmp_path / "runs", now=NOW)
    with pytest.raises(FileExistsError):
        intake.mint_run(tmp_path / "runs", now=NOW)


def test_intake_still_mints_and_registers_in_one_call(tmp_path):
    """The regression guard for the whole split: the old entry point behaves
    exactly as it did, or twenty call sites change meaning silently."""
    source = tmp_path / "api.json"
    source.write_text(json.dumps({"tools": []}), encoding="utf-8")
    run = intake.intake(
        inputs=[source],
        runs_dir=tmp_path / "runs",
        target_name="t",
        target_interface="i",
        max_rounds=2,
        max_scenarios=128,
        now=NOW,
    )
    manifest = read_json(run.manifest)
    assert manifest["run_id"] == "run-20260814-213000"
    assert [e["artifact_id"] for e in manifest["inputs"]] == ["api-json"]
    assert validate.validate_stage(run, "intake") == []


def test_materialising_a_container_element_writes_canonical_bytes(tmp_path):
    """The digest survey computed must equal the digest of the file written here,
    because refs.check_inputs re-hashes the written bytes."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    records = [{"trace_id": f"tr-{i}", "status": "OK", "spans": []} for i in range(3)]
    (corpus / "capture.json").write_text(json.dumps(records), encoding="utf-8")

    run, stamp = intake.mint_run(tmp_path / "runs", now=NOW)
    run.inputs_dir.mkdir()
    candidate = {
        "candidate_id": "capture-json-1",
        "origin": "container_element",
        "container": {"candidate_id": "capture-json", "json_pointer": "/1"},
        "bytes": len(canonical_bytes(records[1])),
        "sha256": hashlib.sha256(canonical_bytes(records[1])).hexdigest(),
        "kind": "trace",
        "admissible": True,
        "digest": {},
    }
    entry = intake.materialise(
        run, candidate=candidate, source_root=corpus, artifact_id="capture-json-1"
    )
    written = run.input_file(entry["stored_as"])
    assert written.read_bytes() == canonical_bytes(records[1])
    assert entry["sha256"] == candidate["sha256"]
    assert entry["provenance"] == {
        "container_sha256": entry["provenance"]["container_sha256"],
        "json_pointer": "/1",
    }
    assert len(entry["provenance"]["container_sha256"]) == 64


def test_materialising_a_plain_corpus_file_copies_it_byte_for_byte(tmp_path):
    corpus = tmp_path / "corpus"
    (corpus / "docs").mkdir(parents=True)
    (corpus / "docs" / "notes.md").write_text("# Notes\n", encoding="utf-8")
    run, _ = intake.mint_run(tmp_path / "runs", now=NOW)
    run.inputs_dir.mkdir()
    candidate = {
        "candidate_id": "notes-md",
        "origin": "corpus",
        "path": "docs/notes.md",
        "bytes": 9,
        "sha256": hashlib.sha256(b"# Notes\n").hexdigest(),
        "kind": "design_doc",
        "admissible": True,
        "digest": {},
    }
    entry = intake.materialise(run, candidate=candidate, source_root=corpus,
                              artifact_id="notes-md")
    assert run.input_file(entry["stored_as"]).read_bytes() == b"# Notes\n"
    assert "provenance" not in entry
    assert entry["source_path"].endswith("docs/notes.md")


def test_a_manifest_with_provenance_validates(tmp_path):
    """Additive schema change: existing manifests without it stay valid."""
    schema = json.loads(
        (validate.schema_dir() / "manifest-0.1.json").read_text(encoding="utf-8")
    )
    provenance = schema["properties"]["inputs"]["items"]["properties"]["provenance"]
    assert "provenance" not in schema["properties"]["inputs"]["items"]["required"]
    assert provenance["oneOf"]
```

- [ ] **Step 2: Run to verify they fail**

```
uv run pytest tests/unit/test_intake_split.py -v
```

Expected: FAIL, `intake` has no `mint_run`.

- [ ] **Step 3: Extend the manifest schema**

In `src/rubrica/schema/manifest-0.1.json`, add to `inputs.items.properties` —
**not** to `required`, so every manifest written before today stays valid:

```json
        "provenance": {
          "oneOf": [
            {
              "type": "object",
              "required": ["container_sha256", "json_pointer"],
              "additionalProperties": false,
              "properties": {
                "container_sha256": {"$ref": "#/$defs/sha256"},
                "json_pointer": {"type": "string", "minLength": 1}
              }
            },
            {
              "type": "object",
              "required": ["projection_id", "source_candidate_ids"],
              "additionalProperties": false,
              "properties": {
                "projection_id": {"$ref": "#/$defs/id"},
                "source_candidate_ids": {
                  "type": "array",
                  "minItems": 1,
                  "items": {"$ref": "#/$defs/id"}
                }
              }
            }
          ]
        }
```

- [ ] **Step 4: Split `intake.py`**

Refactor `intake.intake()` into three functions, keeping its own body as a caller
of the other two so its behaviour cannot drift:

```python
def mint_run(runs_dir: Path, *, now: datetime | None = None) -> tuple[RunPaths, datetime]:
    """Create the run directory and return it with its resolved UTC stamp.

    Split out of intake() so `survey` can mint a run before anything is admitted.
    The manifest is still written by register(), which is what keeps
    manifest-0.1.json's inputs.minItems at 1: the manifest appears only when
    there are inputs to name.

    A naive datetime is refused rather than interpreted, for the reason intake()
    already refused it: .astimezone() assumes the host zone, so the same call on
    two machines would mint two different run ids.
    """
    if now is None:
        stamp = datetime.now(UTC)
    elif now.tzinfo is None:
        raise UsageError("intake needs a timezone-aware datetime, got a naive one")
    else:
        stamp = now.astimezone(UTC)
    run = RunPaths(Path(runs_dir) / f"run-{stamp:%Y%m%d-%H%M%S}")
    if run.root.exists():
        raise FileExistsError(f"run directory already exists: {run.root}")
    run.root.mkdir(parents=True)
    return run, stamp


def register(
    run: RunPaths,
    *,
    entries: list[dict],
    target_name: str,
    target_interface: str,
    max_rounds: int,
    max_scenarios: int,
    created: datetime,
) -> None:
    """Write manifest.json from already-built input entries."""
    write_json(
        run.manifest,
        {
            "schema_version": "0.1",
            "run_id": run.root.name,
            "created_utc": utc_stamp(created),
            "target": {"name": target_name, "interface": target_interface},
            "inputs": entries,
            "stages": {},
            "limits": {"max_rounds": max_rounds, "max_scenarios": max_scenarios},
        },
    )


def materialise(
    run: RunPaths, *, candidate: dict, source_root: Path, artifact_id: str
) -> dict:
    """Put one admitted candidate into 00-inputs/ and describe it for the manifest.

    A corpus candidate is copied byte for byte. A container element is *written*
    from the container's parsed contents through canonical_bytes -- the same
    function survey hashed it with, so the sha256 recorded at survey time equals
    the digest of the bytes refs.check_inputs will re-hash. Two spellings of "the
    canonical form" would make every exploded input report a mismatch.
    """
    origin = candidate.get("origin")
    if origin == "container_element":
        container_relative = _container_path(candidate, run)
        container_file = Path(source_root) / container_relative
        payload = json.loads(container_file.read_text(encoding="utf-8"))
        element = resolve_pointer(payload, candidate["container"]["json_pointer"])
        body = canonical_bytes(element)
        stored_as = f"{artifact_id}.json"
        (run.inputs_dir / stored_as).write_bytes(body)
        return {
            "artifact_id": artifact_id,
            "source_path": f"{container_file}#{candidate['container']['json_pointer']}",
            "stored_as": stored_as,
            "sha256": hashlib.sha256(body).hexdigest(),
            "kind": candidate["kind"],
            "bytes": len(body),
            "provenance": {
                "container_sha256": sha256_of(container_file),
                "json_pointer": candidate["container"]["json_pointer"],
            },
        }

    source = Path(source_root) / candidate["path"]
    stored_as = stored_name(artifact_id, source)
    shutil.copy2(source, run.inputs_dir / stored_as)
    entry = {
        "artifact_id": artifact_id,
        "source_path": str(source),
        "stored_as": stored_as,
        "sha256": sha256_of(source),
        "kind": candidate["kind"],
        "bytes": source.stat().st_size,
    }
    if origin == "projection":
        entry["provenance"] = dict(candidate["provenance"])
    return entry
```

`_container_path(candidate, run)` looks the container candidate up in the
catalogue by `candidate["container"]["candidate_id"]` and returns its `path`.
Write it as a small module-level helper reading `run.catalogue`; a container whose
candidate id does not resolve is already a `check_catalogue` finding, so raise
`ArtifactError` here rather than duplicating the check.

Then rewrite `intake.intake()`'s body to call `mint_run` and `register`, keeping
every existing argument check exactly where it is — the checks must still run
*before* `mint_run`, since `test_a_blank_target_name_is_refused_before_the_run_is_minted`
depends on nothing being created.

Import `resolve_pointer` from `rubrica.refs` inside `materialise` rather than at
module top if a circular import appears — `refs` imports `paths` and `artifacts`,
not `intake`, so a top-level import should be fine; verify with
`uv run python -c "import rubrica.intake"`.

- [ ] **Step 5: Run everything**

```
uv run pytest tests/unit/test_intake_split.py -v && uv run pytest -q && make check
```

Expected: PASS with **no changes to `tests/unit/test_intake.py`**. If that file
needed editing, the split changed `intake()`'s behaviour and the refactor is
wrong.

- [ ] **Step 6: Commit**

```bash
git add src/rubrica/intake.py src/rubrica/schema/manifest-0.1.json tests/unit/test_intake_split.py
git commit -S -s -m "feat: Split intake into mint and register, and materialise elements

intake() keeps its exact signature and behaviour -- twenty call sites and
build_toy_run are untouched, which is the regression guard. What is new is that
survey can mint a run without a manifest, and admission can write one into a run
it did not mint.

A container element is written through canonical_bytes rather than copied, so the
sha256 survey recorded equals the digest refs.check_inputs re-hashes. provenance
is additive and optional, so every manifest written before today stays valid.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

### Task 14: `intake --run` — admit from the triage record

**Files:**
- Modify: `src/rubrica/intake.py` (`admit_from_triage`), `src/rubrica/cli.py`
- Test: `tests/unit/test_admit.py` (new)

**Interfaces:**
- Consumes: everything from Task 13, `refs.check_triage`.
- Produces:
  - `intake.admit_from_triage(run: RunPaths) -> list[Finding]` — writes
    `00-inputs/` and `manifest.json`, or returns findings and writes nothing.
  - CLI: `rubrica intake --run RUN`, mutually exclusive with `--input`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_admit.py`. Build a run with `survey.survey` over
`tests/fixtures/corpus-toy/`, hand-write a `00-triage.json` admitting the prose
and two trace elements and declining the rest, then assert:

```python
def test_admitting_writes_inputs_and_a_valid_manifest(tmp_path):
    run = _surveyed_and_triaged(tmp_path)
    assert intake.admit_from_triage(run) == []
    manifest = read_json(run.manifest)
    assert {e["artifact_id"] for e in manifest["inputs"]} == {"README-md", "capture-json-0",
                                                              "capture-json-1"}
    assert validate.validate_stage(run, "intake") == []
    assert refs.check_all(run) == []


def test_the_manifest_takes_its_parameters_from_the_catalogue(tmp_path):
    """Not from argv. One file the human edits at gate 0, one file intake reads."""
    run = _surveyed_and_triaged(tmp_path)
    intake.admit_from_triage(run)
    manifest = read_json(run.manifest)
    catalogue = read_json(run.catalogue)
    assert manifest["target"] == catalogue["request"]["target"]
    assert manifest["limits"] == catalogue["request"]["limits"]
    assert manifest["created_utc"] == catalogue["created_utc"]


def test_a_declined_candidate_is_not_admitted(tmp_path):
    run = _surveyed_and_triaged(tmp_path)
    intake.admit_from_triage(run)
    stored = {p.name for p in run.inputs_dir.iterdir()}
    assert not any("logo" in name or "lock" in name for name in stored)


def test_an_inconsistent_triage_record_is_findings_and_writes_nothing(tmp_path):
    """Exit 1, repairable by re-dispatching triage -- never exit 2. A stage defect
    surfacing as 2 makes the orchestrator halt instead of spending its one repair."""
    run = _surveyed_and_triaged(tmp_path, drop_a_disposition=True)
    findings = intake.admit_from_triage(run)
    assert findings
    assert all("00-triage.json" in str(f.artifact) for f in findings)
    assert not run.manifest.exists()
    assert not run.inputs_dir.exists()


def test_zero_admits_is_findings_rather_than_an_empty_manifest(tmp_path):
    """inputs.minItems is 1, so writing the manifest anyway would surface a
    scoping failure as a schema error against an artifact no prompt wrote."""
    run = _surveyed_and_triaged(tmp_path, decline_everything=True)
    findings = intake.admit_from_triage(run)
    assert findings and not run.manifest.exists()


def test_admitting_twice_refuses_rather_than_rewriting(tmp_path):
    """A re-run gets a new run id so old artifacts stay diffable -- the rule
    intake() already holds for its run directory."""
    run = _surveyed_and_triaged(tmp_path)
    intake.admit_from_triage(run)
    with pytest.raises(FileExistsError):
        intake.admit_from_triage(run)


def test_a_missing_triage_record_is_a_usage_error(tmp_path):
    """Stages run out of order is a misconfigured harness, which is exit 2."""
    run = _surveyed(tmp_path)
    with pytest.raises(UsageError, match="00-triage.json"):
        intake.admit_from_triage(run)


def test_run_and_input_are_mutually_exclusive():
    parser = cli._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["intake", "--run", "r", "--input", "x"])


def test_run_mode_rejects_the_parameters_the_catalogue_already_carries():
    """Refused in the CLI rather than resolved by precedence: minting from an
    ambiguous parameter set is the shape that produced three manifest findings no
    repair prompt could fix."""
    parser = cli._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["intake", "--run", "r", "--target-name", "t"])
```

- [ ] **Step 2: Run to verify they fail, then implement**

```python
def admit_from_triage(run: RunPaths) -> list[Finding]:
    """Register every admitted candidate and write the manifest.

    Returns findings and writes nothing when the triage record is internally
    inconsistent: that is a repairable stage defect at exit 1, fixed by
    re-dispatching triage. Only an unreadable or absent artifact is a UsageError,
    which cli.py maps to 2 -- the distinction the orchestrator branches on.
    """
    if not run.triage.is_file():
        raise UsageError(
            f"no triage record at {run.triage}; run the triage stage before intake --run"
        )
    if not run.catalogue.is_file():
        raise UsageError(f"no catalogue at {run.catalogue}; this run was not minted by survey")
    if run.manifest.exists():
        raise FileExistsError(
            f"manifest already exists: {run.manifest}; a re-run gets a new run id so the old "
            "artifacts stay diffable"
        )

    findings = check_triage(run)
    if findings:
        return findings

    catalogue = read_json(run.catalogue)
    triage = read_json(run.triage)
    candidates = {c["candidate_id"]: c for c in catalogue["candidates"]}
    admitted = [
        candidates[d["candidate_id"]]
        for d in sorted(
            (d for d in triage["dispositions"] if d["disposition"] == "admit"),
            key=lambda d: (d.get("priority", 1 << 30), d["candidate_id"]),
        )
    ]
    if not admitted:
        return [
            Finding(run.triage, "refs", "/dispositions", "no candidate was admitted")
        ]

    root = Path(catalogue["request"]["corpus_roots"][0])
    run.inputs_dir.mkdir(parents=True)
    entries = []
    used: dict[str, int] = {}
    for candidate in admitted:
        artifact_id = _unique_artifact_id(candidate["candidate_id"], used)
        entries.append(
            materialise(run, candidate=candidate, source_root=root, artifact_id=artifact_id)
        )

    request = catalogue["request"]
    register(
        run,
        entries=entries,
        target_name=request["target"]["name"],
        target_interface=request["target"]["interface"],
        max_rounds=request["limits"]["max_rounds"],
        max_scenarios=request["limits"]["max_scenarios"],
        created=datetime.strptime(catalogue["created_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        ),
    )
    return []
```

`_unique_artifact_id` reuses the suffix-on-collision rule `_unique_ids` already
implements — extract that logic into a shared helper rather than writing it twice.

**Multi-root corpora:** the code above takes `corpus_roots[0]`, which is wrong
for a multi-root survey. Fix it properly: record the root index on each candidate
in Task 7's `survey()` (`"root_index": N`, added to the catalogue schema as an
optional integer) and resolve against `corpus_roots[candidate["root_index"]]`
here, defaulting to 0 when absent. Do this now rather than leaving a latent bug —
`--corpus` already accepts `append`.

- [ ] **Step 3: Wire the CLI**

Make `--input` and `--run` mutually exclusive with
`p_intake.add_mutually_exclusive_group(required=True)`, move `--runs-dir` and
the four other parameters into the `--input` path's own group, and in the
dispatch branch:

```python
    if args.command == "intake":
        if args.run:
            run = RunPaths(args.run)
            findings = intake.admit_from_triage(run)
            if findings:
                print(format_findings(findings))
                return 1
            print(run.root)
            return 0
        ...existing --input path unchanged...
```

argparse cannot express "these five flags are illegal with `--run`" directly;
check it explicitly after parsing and raise `UsageError`, then assert that in
`test_run_mode_rejects_the_parameters_the_catalogue_already_carries` with
`pytest.raises(UsageError)` instead of `SystemExit` if that is the shape you
implement. Pick one and make the test match the code.

- [ ] **Step 4: Run everything and commit**

```
uv run pytest -q && make check
git add src/rubrica/intake.py src/rubrica/cli.py src/rubrica/survey.py \
        src/rubrica/schema/catalogue-0.1.json tests/unit/test_admit.py
git commit -S -s -m "feat: Add intake --run, admitting from the triage record

Parameters come from the catalogue rather than argv, so there is one file the
human edits at gate 0 and one file intake reads. An inconsistent triage record is
exit 1 with findings naming 00-triage.json and writes nothing; only a missing or
unreadable artifact is exit 2, which is the distinction the orchestrator branches
on.

--input survives as the direct path for someone with three files who does not
need triage.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

### Task 15: The manifest↔dispositions check, and the toy checkpoints

**Files:**
- Modify: `src/rubrica/refs.py` (`check_admitted_inputs`), `tests/toy.py`
- Test: `tests/unit/test_refs_admitted.py` (new), `tests/unit/test_toy_fixture.py`

**Interfaces:**
- Produces: `refs.check_admitted_inputs(run) -> list[Finding]`, wired into
  `check_all` after `check_inputs`; `tests/toy.py` gains `"survey"` and
  `"triage"` at the front of `_UPTO_STAGES`.

- [ ] **Step 1: Write the failing tests**

```python
def test_an_admitted_candidate_missing_from_the_manifest_is_a_finding(tmp_path):
    """This is what catches an admission intake dropped -- the only failure mode
    where both artifacts are individually well formed and the run is still wrong."""


def test_a_manifest_input_that_was_never_admitted_is_a_finding(tmp_path):
    """The other direction: an input nobody ruled on is an input that entered the
    run outside the gate."""


def test_the_check_is_silent_on_a_run_with_no_triage_record(tmp_path):
    """intake --input runs have a manifest and no triage record, and spec §7.1
    rules that this is not a finding."""
```

- [ ] **Step 2: Implement**

```python
def check_admitted_inputs(run: RunPaths) -> list[Finding]:
    """manifest.inputs[] against the admitted dispositions, one to one.

    Silent when there is no triage record: a run minted through `intake --input`
    never had one. Matching is by artifact_id, which admit_from_triage derives
    from candidate_id by the same suffix-on-collision rule -- so a mismatch here
    means an admission was dropped or one arrived from outside the gate.
    """
```

Match on the candidate id embedded in each `artifact_id`, accounting for the
collision suffix; a manifest entry whose id maps to no admitted candidate, and an
admitted candidate with no manifest entry, are each one finding naming the
manifest.

- [ ] **Step 3: Extend `tests/toy.py`**

Add `"survey"` and `"triage"` to the front of `_UPTO_STAGES`, and a
`build_toy_catalogue_and_triage(run)` helper that writes both artifacts for the
existing toy world. `build_toy_run` keeps calling `intake.intake()` through the
`--input` path — **do not reroute it through admission**, or every existing test's
manifest changes shape and this task stops being reviewable.

Then in `tests/unit/test_toy_fixture.py`:

```python
def test_the_toy_run_still_has_no_catalogue_and_that_is_not_a_finding(tmp_path):
    """build_toy_run mints through intake --input, so it exercises spec §7.1's
    ruling on every existing test in the suite for free."""
    run = build_toy_run(tmp_path)
    assert not run.catalogue.exists()
    assert refs.check_catalogue(run) == []
    assert refs.check_triage(run) == []
    assert refs.check_admitted_inputs(run) == []
```

- [ ] **Step 4: Run everything and commit**

```
uv run pytest -q && make check && uv run rubrica check-skills
git add src/rubrica/refs.py tests/toy.py tests/unit/test_refs_admitted.py \
        tests/unit/test_toy_fixture.py
git commit -S -s -m "feat: Check manifest inputs against the admitted dispositions

The one failure mode where both artifacts are individually well formed and the
run is still wrong: an admission intake dropped, or an input that entered from
outside the gate.

Silent on a run with no triage record, which is every existing toy run -- so the
suite exercises spec §7.1's ruling for free.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

# Phase 4 — The human's instruments

Ends usefully: gate 0 has a surface a person can read in ten minutes, and a
declared projection can actually be satisfied. **Not optional on this build** —
the human is holding gate 0 tonight.

### Task 16: `adopt-projection`

**Files:**
- Create: `src/rubrica/triage.py`
- Modify: `src/rubrica/cli.py`
- Test: `tests/unit/test_adopt_projection.py` (new)

**Interfaces:**
- Consumes: `intake.classify`, `refs.resolve_pointer`, `artifacts.read_json/write_json`.
- Produces:
  - `triage.check_acceptance(path: Path, acceptance: dict) -> list[Finding]`
  - `triage.adopt_projection(run: RunPaths, *, projection_id: str, source: Path,
    check_only: bool = False) -> list[Finding]`
  - CLI: `rubrica adopt-projection --run RUN --projection ID --file PATH [--check-only]`

- [ ] **Step 1: Write the failing tests**

```python
"""Satisfying a projection without throwing the run away.

Appending a candidate to the catalogue is the same append-and-record move
02-scenarios.json makes round by round, and a human authoring an admission at
their own gate is what gate 0 is.
"""

def test_a_file_meeting_every_structural_criterion_is_adopted(tmp_path):
    run = _run_with_projection(tmp_path)
    projected = tmp_path / "tools-list.json"
    projected.write_text(json.dumps({"tools": [{"name": "query_aap2", "result_shape": {}}]}),
                         encoding="utf-8")
    assert triage.adopt_projection(run, projection_id="prj-tools", source=projected) == []
    catalogue = read_json(run.catalogue)
    adopted = next(c for c in catalogue["candidates"] if c["origin"] == "projection")
    assert adopted["provenance"]["projection_id"] == "prj-tools"
    assert adopted["kind"] == "mcp_tool_schema"
    record = read_json(run.triage)
    disposition = next(d for d in record["dispositions"]
                       if d["candidate_id"] == adopted["candidate_id"])
    assert disposition["disposition"] == "admit"
    # The human's authority, not triage's -- and recorded as such, so a reader can
    # tell which admissions the gate authored.
    assert disposition["authority"] == "human"
    assert next(d for d in record["deficiencies"]
                if d["deficiency_id"] == "def-shapes")["closed_by"] == "prj-tools"


def test_a_missing_required_string_is_one_finding_per_failed_check(tmp_path):
    """Exit 1 with findings the worker reads and retries against -- and the same
    findings a future rb-project member would read as its gate."""


def test_a_forbidden_string_is_a_finding(tmp_path):
    """must_not_contain is the boundary. A projection that dragged in
    implementation defeats the objective it was requested for."""


def test_a_file_of_the_wrong_kind_is_a_finding(tmp_path):
    """classifies_as, checked through intake.classify -- the same classifier
    intake will use, so adoption cannot promise a kind admission then disagrees with."""


def test_check_only_writes_nothing(tmp_path):
    run = _run_with_projection(tmp_path)
    before = run.catalogue.read_bytes()
    triage.adopt_projection(run, projection_id="prj-tools", source=_good(tmp_path),
                            check_only=True)
    assert run.catalogue.read_bytes() == before


def test_an_unknown_projection_id_is_a_usage_error(tmp_path):
    """Not a finding: nothing in the run is defective, the caller named something
    that does not exist."""


def test_structural_acceptance_never_claims_the_file_is_accepted(tmp_path):
    """Whether result_shape truly describes what a caller receives is semantic,
    and the rule against inventing a mechanical check for support applies here as
    it applies to layer 2. The prose criterion is the human's to judge."""
    findings = triage.check_acceptance(_good(tmp_path), _acceptance())
    assert findings == []
    # And the CLI's success line says so:
    assert "structural" in triage.ACCEPTANCE_PASS_MESSAGE.lower()
    assert "accepted" not in triage.ACCEPTANCE_PASS_MESSAGE.lower()
```

- [ ] **Step 2: Implement**

`check_acceptance` runs four checks and returns one `Finding` per failure, all
naming the *source file* rather than a run artifact: `classifies_as` via
`intake.classify`, `pointers_required` via `refs.resolve_pointer`,
`must_contain` and `must_not_contain` as plain substring tests over the decoded
text. Define:

```python
ACCEPTANCE_PASS_MESSAGE = (
    "structural acceptance passed; the prose criterion is still a human's to judge"
)
```

`adopt_projection` then, on an empty finding list and unless `check_only`: copies
nothing (the file stays where it is; the *catalogue* gains a candidate whose
`path` is the absolute source path and whose `root_index` is absent), appends the
candidate with `origin: "projection"`, appends the `admit` disposition with
`authority: "human"`, sets `closed_by` on each deficiency the projection
`closes`, sets `satisfied_by` on the projection, and rewrites both artifacts with
`write_json`.

**A projection candidate's `path` is absolute and outside any corpus root**, so
`intake.materialise`'s corpus-relative join must handle that: if
`candidate["path"]` is absolute, use it directly. Add that branch and a test for
it in this task, not later.

- [ ] **Step 3: Wire the CLI, run everything, commit**

```
uv run pytest -q && make check
git commit -S -s -m "feat: Add adopt-projection -- satisfy a brief without a new run

Appending a candidate to the catalogue is the append-and-record move
02-scenarios.json already makes, and an admission authored at gate 0 carries
authority: human so a reader can tell which the gate wrote.

The success message says structural acceptance passed and never that the file is
accepted: whether a result shape describes what a caller receives is semantic.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

### Task 17: Implied suite size

**Files:**
- Create: `src/rubrica/sizing.py`
- Test: `tests/unit/test_sizing.py` (new)

**Interfaces:**
- Produces:
  - `sizing.ACCEPTANCE_ALLOWANCE = 0.75`
  - `sizing.implied_size(run: RunPaths) -> dict | None` — `None` when there is no
    world model. Keys: `capability_cells`, `hop_slots`, `blocked_cells`,
    `denominator`, `implied`, `basis` (`"world_model"` or `"world_model+coverage"`),
    `ceiling`, `ceiling_binding` (bool).

- [ ] **Step 1: Write the failing test against the real parsec artifacts**

This is the one place a fixture is weaker than the real thing, because the number's
credibility rests on it reproducing a human's instinct.

```python
def test_the_parsec_world_model_implies_the_cap_that_was_set_by_hand():
    """Measured, not reasoned. From run-20260813-204203:

    28 capability cells + 23 hop-depth slots = 51, against a ~50 floor ruled by
    instinct; 51/0.75 = 68 against the 64 set by hand. Five blocked cells are
    known only after round 1, giving 46 and 62 at gate 2.
    """
    run = RunPaths("runs/run-20260813-204203")
    if not run.world_model.is_file():
        pytest.skip("the reference run is not present; it is gitignored")
    at_gate_1 = sizing.implied_size(RunPaths(_world_model_only_copy(run)))
    assert at_gate_1["capability_cells"] == 28
    assert at_gate_1["hop_slots"] == 23
    assert at_gate_1["denominator"] == 51
    assert at_gate_1["implied"] == 68
    assert at_gate_1["basis"] == "world_model"
    at_gate_2 = sizing.implied_size(run)
    assert at_gate_2["blocked_cells"] == 5
    assert at_gate_2["denominator"] == 46
    assert at_gate_2["implied"] == 62
    assert at_gate_2["basis"] == "world_model+coverage"
```

`runs/` is gitignored, so this test **skips** when the reference run is absent —
which means a green suite on a fresh clone is not evidence for it. Add a
fixture-based test alongside it that pins the arithmetic on synthetic numbers, so
the formula is guarded even when the measurement cannot run. Say so in a docstring
rather than letting a reader assume the skip is coverage.

- [ ] **Step 2: Implement, run, commit**

`implied_size` reads `world_model["denominator"]["capability_cells"]` and sums
`len(goal["expected_hop_depths"])` over `world_model["goals"]`; when
`coverage_latest` exists it subtracts the count of distinct `holes[]` entries whose
`reason` is `blocked_by_gap`. `implied` is `ceil(denominator / ACCEPTANCE_ALLOWANCE)`.
`ceiling` comes from `manifest["limits"]["max_scenarios"]`, and `ceiling_binding`
is `implied > ceiling` — the diagnostic that means the target wants splitting.

```bash
git commit -S -s -m "feat: Compute implied suite size from the world model

Verified against run-20260813-204203: 51 at gate 1 against a ~50 floor ruled by
instinct, 68 implied against the 64 set by hand, 46 and 62 after round 1's five
blocked cells. Nothing acts on the number -- gate-brief reports it, and its two
uses are diagnostic in both directions.

The 0.75 allowance is that run's measured acceptance, 23 of 30, and is labelled
as one run's constant.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

### Task 18: `gate-brief`

**Files:**
- Create: `src/rubrica/brief.py`
- Modify: `src/rubrica/cli.py`
- Test: `tests/unit/test_brief.py` (new)

**Interfaces:**
- Consumes: `utilisation` (existing), `sizing.implied_size`, the catalogue and
  triage records.
- Produces: `brief.gate_brief(run: RunPaths, gate: int) -> str`; CLI
  `rubrica gate-brief --run RUN --gate {0,1,2,3}`, always exit 0.

**This is what you will actually read tonight**, so optimise it for a tired
person: the objective verdict first, then the deficiencies, then the counts.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_gate_zero_brief_leads_with_the_objective_verdict(tmp_path):
    """A reader who stops after ten lines must have seen the thing most likely to
    make them overturn the selection."""
    text = brief.gate_brief(_triaged(tmp_path), 0)
    head = "\n".join(text.splitlines()[:10]).lower()
    assert "objective" in head
    assert "supported" in head


def test_the_gate_zero_brief_lists_declines_grouped_by_reason_code(tmp_path):
    text = brief.gate_brief(_triaged(tmp_path), 0)
    assert "off_objective" in text
    assert "needs_projection" in text


def test_the_gate_zero_brief_shows_every_open_deficiency_and_its_projection(tmp_path):
    """The block that would have predicted six parsec refusals is useless if the
    brief buries it."""
    text = brief.gate_brief(_triaged(tmp_path), 0)
    assert "def-shapes" in text and "prj-tools" in text


def test_the_gate_one_brief_puts_gaps_and_declined_deficiencies_side_by_side(tmp_path):
    """Spec §10: this pairing is semantic, so it is a human's call and this
    rendering is the whole instrument for making it."""
    text = brief.gate_brief(_full_run(tmp_path), 1)
    assert "gap-" in text
    assert "deficien" in text.lower()
    assert "utilisation" in text.lower()
    assert "implied" in text.lower()


def test_a_brief_for_a_run_with_no_triage_record_says_so_and_exits_clean(tmp_path):
    """Spec §7.1 held consistently by the report as well as by the check."""
    text = brief.gate_brief(build_toy_run(tmp_path), 0)
    assert "no triage" in text.lower()


def test_gate_brief_is_a_report_and_never_a_gate(tmp_path):
    """Same ruling as claim-utilisation: it always exits clean on a readable run."""
    assert cli.main(["gate-brief", "--run", str(_triaged(tmp_path).root), "--gate", "0"]) == 0
```

- [ ] **Step 2: Implement, run, commit**

Plain text, not JSON — a human reads it. Gate 1 composes
`utilisation.report(run)` rather than reimplementing its arithmetic.

```bash
git commit -S -s -m "feat: Add gate-brief, the human surface at all four gates

Gate 0 leads with the objective verdict and the open deficiencies, because a
reader who stops after ten lines must have seen what would make them overturn the
selection. Gate 1 puts the world model's gaps beside the triage record's
deficiencies -- the pairing spec §10 rules is semantic and therefore a human's,
which is why it is a rendering rather than a check.

A report, never a gate: exit 0 on any readable run.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

### Task 19: `set-limit`

**Files:** Modify `src/rubrica/manifest.py`, `src/rubrica/cli.py`.
**Test:** `tests/unit/test_set_limit.py` (new).

**Interfaces:** `manifest.set_limit(run, *, max_rounds=None, max_scenarios=None,
reason: str) -> None`, which rewrites `manifest.limits` and appends the change to
`decisions.md` through `artifacts.append_decision`. CLI:
`rubrica set-limit --run RUN [--max-rounds N] [--max-scenarios N] --reason TEXT`.

- [ ] **Step 1: Tests**

```python
def test_setting_a_limit_records_the_reason_in_decisions(tmp_path):
    """§10 error 4: a hand edit of max_scenarios was read as an unexplained
    discrepancy because every mechanism was checked except the person."""


def test_a_reason_is_required_and_may_not_be_blank(tmp_path):
    """A limit change with no reason is the hand edit this replaces."""


def test_setting_neither_limit_is_a_usage_error(tmp_path):


def test_the_manifest_still_validates_after_the_change(tmp_path):
```

- [ ] **Step 2: Implement, run, commit**

```bash
git commit -S -s -m "feat: Add set-limit, so a limit change carries its reason

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

### Task 20: Orchestration and the docs

**Files:** Modify `src/rubrica/skills/rb-orchestrate/SKILL.md`, `README.md`,
`CLAUDE.md`, `docs/pipeline-overview.md`.
**Test:** `tests/unit/test_skills_orchestrate.py`.

- [ ] **Step 1: Tests first**

```python
def test_the_orchestrator_dispatches_survey_triage_and_holds_gate_zero():
    body = _norm(skills.section_body(_orchestrate(), "3. Method"))
    assert "survey" in body and "triage" in body
    assert "gate 0" in body


def test_the_orchestrator_knows_gate_zero_decides_what_the_run_can_know():
    """The reason this gate is different in kind from 1-3: a model that both
    selects the inputs and ratifies the selection makes triage unfalsifiable."""
    body = _norm(_orchestrate().body)
    assert "what the run can" in body


def test_the_orchestrator_still_declares_no_stage_and_no_schemas():
    """rb-orchestrate is the ninth skill and is not a stage. Adding a stage
    to its contract would put it in STAGE_ARTIFACTS, where nothing dispatches it."""
```

- [ ] **Step 2: Update the four documents**

`rb-orchestrate`: eleven stages, nine skills, gate 0 between triage and intake,
and the `survey → triage → gate 0 → intake` sequence with its exact commands.
State plainly that gate 0 decides what the run can ever know, so a model holding
it makes triage unfalsifiable — that is the caveat tonight's run has to carry.

`README.md`: the `survey`/`triage`/`intake --run` commands, and the four new
subcommands in the command list. **`README.md` is not ruff-excluded**, so run
`make check` after.

`CLAUDE.md`: update the stage table to eleven stages and nine skills, the
subcommand count to seventeen, and the baseline test count to whatever the suite
actually reports at the end of this plan. That last one is a measurement, not an
estimate — read it off the final `pytest -q`.

`docs/pipeline-overview.md`: add the two stages. Leave
`docs/pipeline-overview.html` alone unless it is generated from the markdown; if
it is hand-maintained, update it and say so in the commit.

- [ ] **Step 3: Run everything and commit**

```
uv run pytest -q && make check && uv run rubrica check-skills
git commit -S -s -m "docs: Record eleven stages, nine skills, seventeen subcommands

rb-orchestrate now dispatches survey and triage and holds gate 0, and says why
that gate is different in kind from 1-3: it decides what the run can ever know,
so a model holding it makes triage unfalsifiable.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Self-review of this plan

**Spec coverage.** §4 → Task 2. §5.1 → Task 4. §5.2 → Task 5. §5.3 → Task 6.
§5.4 → Tasks 3, 7. §6 → Tasks 9, 11. §6.1's coverage requirement → Task 10.
§6.2 → Tasks 11, 12. §7 → Task 14. §7.1 → Tasks 13, 14, 15. §7.2 → Task 13.
§7.3 → Task 14. §8 → Tasks 9, 16. §9 → Task 17. §10 → Tasks 8, 10, 15. §11 →
Task 18. §12 → Task 20. §13 → Tasks 8, 12, 15. §5's ceiling → Task 1. §15's
`max_rounds` item is deliberately **not** implemented; it is owed, not planned.

**Three gaps found and closed inline while reviewing:** multi-root corpora were
broken by `corpus_roots[0]` (fixed in Task 14 with `root_index`); a projection
candidate's absolute path broke `materialise`'s corpus-relative join (fixed in
Task 16); and Task 17's real-artifact test *skips* on a fresh clone because
`runs/` is gitignored, so it now carries a synthetic companion and says so.

**Type consistency.** `candidate_id` throughout, never `id`. `reason_code` on
dispositions, `reason` for prose. `digest_for_path` / `digest_for_payload`, both
taking `body_chars`. `canonical_bytes` used by survey and intake. `implied_size`
returns a dict, never a bare int.

**One thing left deliberately loose:** Task 14's `--run` mutual-exclusion can be
argparse-level or an explicit `UsageError`; the task says pick one and make the
test match, rather than pretending there is one right answer.

---

## Appendix: executing tonight's parsec run

Not part of the plan's tasks. Do this after Task 20 is committed and green.

1. **Survey** — `--objective breadth`, because spec §11's retrospective is that
   the 2026-08-13 run optimised for a coherent surface and a deliverable suite
   wants coverage. Include the source tree this time: §11 retracts that
   exclusion, and the six refusals died for shapes that lived in `src/tools/*.py`.

```
uv run rubrica survey --corpus /tmp/parsec --runs-dir runs \
  --target-name parsec --target-interface http-sse \
  --objective breadth \
  --objective-note "Cover as much of parsec's tool and persona surface as the 130-trace capture and the prompts support." \
  --max-rounds 3 --max-scenarios 128
```

2. **Gate the catalogue** — `validate --stage survey`, then read
   `gate-brief --gate 0` yourself once triage has run.
3. **Dispatch triage** — `scripts/dispatch-stage.sh triage "$RUN"`, then
   `validate --stage triage` and `check-refs`.
4. **Hold gate 0.** Read the brief. Overturn what you disagree with, record it
   with `rubrica decide`, and satisfy any `needs_projection` with
   `adopt-projection --check-only` first.
5. **Admit** — `uv run rubrica intake --run "$RUN"`.
6. **From here it is yesterday's run**, orchestrator-held from gate 1 onward.

**Pre-register predictions before step 3, outside the run directory**, in the
spec or a new record — never in `decisions.md`, which a dispatch was measured one
`Read` from on 2026-08-13. The four worth writing down, because each is settled
by a named field:

- **P1** — triage declines `src/agent/tool_definitions.py` `needs_projection`
  rather than admitting it whole. *Settled by:* its `reason_code`.
- **P2** — at least one deficiency names tool result shapes. *Settled by:*
  `deficiencies[].subject`.
- **P3** — `objective_review.supported` is `true` for `breadth`, and the surfaces
  found number at least six (the six personas). *Settled by:*
  `objective_review`.
- **P4** — the single `TraceStatus.ERROR` element is admitted. *Settled by:* its
  disposition. This is the one to watch: it is the corpus's only evidence of
  failure behaviour and `near_duplicate` is exactly how it gets lost.

**Write `rb-triage/exercise.md` from what happened**, after the dispatch. An
exercise record states what *happened*; a reasoned number presented as an
observed one corrupts the evidence, and one such misattribution has already
shipped here and had to be corrected.
