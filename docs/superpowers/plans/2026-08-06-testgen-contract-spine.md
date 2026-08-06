# Test Generator: Contract Spine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic on-disk artifact contract that every pipeline stage reads and writes — schemas, atomic artifact I/O, schema validation, referential-integrity and reachability checking, input intake, and dedupe candidate proposal.

**Architecture:** A Python package `testgen` under `src/`, exposing one CLI (`testgen <subcommand>`). All artifact paths resolve through a single `paths.RunPaths` class so the run-directory layout exists in exactly one place. Validation is layered: JSON Schema checks shape (`validate.py`), then a referential-integrity linter checks what schemas cannot express (`refs.py`) — cross-artifact id references, JSON-pointer reachability of every assertion into its own seed, and world-model invariants evaluated over each seed by a small safe expression evaluator (`invariants.py`).

**Tech Stack:** Python 3.13, uv, `jsonschema` (runtime), `pytest` + `ruff` (dev). No LLM calls anywhere in this plan — every component here is deterministic.

**Design spec:** `docs/superpowers/specs/2026-08-06-skill-based-test-generator-design.md`. Section references below (§3, §4, …) point at it.

## Global Constraints

- **Python 3.13+**, environment managed by `uv`. Use `uv pip install`, never bare `pip`, inside the venv.
- **Runtime dependencies are limited to `jsonschema` and `tomli-w`.** `tomli-w` is unused in this plan; it belongs to the emit layer and is declared here so the dependency set is fixed once.
- **Artifacts are the only channel between stages** (§4). No module in this plan may pass state between stages by any other means.
- **Canonical artifact JSON:** `indent=2`, `sort_keys=True`, trailing newline. Two runs producing the same content must produce byte-identical files, or `diff-runs` reports formatting as variance.
- **Every artifact carries `schema_version: "0.1"`** as a required `const`.
- **Run ids and timestamps are minted by `intake` (code), never by skills** (§4).
- **The assertion vocabulary is closed** (§7): `answer_contains`, `answer_excludes`, `tool_called`, `tool_not_called`, `value_equals`. Adding a kind is a human change to the verifier, so the schema pins it as an `enum`.
- **Ids from artifacts are model-generated and untrusted.** Any id joined into a filesystem path must pass `paths.safe_segment` first.
- **Terminology (§3), used exactly:** a **gap** is missing knowledge about the target, recorded in the world model, closable only by supplying another input artifact. A **hole** is an uncovered coverage cell, recorded in the coverage report, closable by proposing scenarios. Never use one word for the other.
- **Every commit is signed and DCO signed-off:** `git commit -S -s`. Use the trailer `Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>`. Never `Co-Authored-By`. If signing fails, stop and report — do not fall back to an unsigned commit.

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, dependency pins, CLI entry point, ruff and pytest config |
| `Makefile` | `setup` / `test` / `check` / `lint` / `format` targets |
| `src/testgen/paths.py` | Run-directory layout; the single source of truth for artifact paths. Path-segment safety. |
| `src/testgen/artifacts.py` | Atomic canonical JSON read/write; `decisions.md` append |
| `src/testgen/validate.py` | JSON Schema validation, stage → schema mapping |
| `src/testgen/invariants.py` | Safe expression evaluator for world-model `machine:` invariants |
| `src/testgen/refs.py` | Referential integrity, seed-pointer reachability, invariants over seeds |
| `src/testgen/intake.py` | Register + hash + classify inputs; mint run id and manifest |
| `src/testgen/dedupe.py` | Propose candidate duplicate scenario pairs |
| `src/testgen/cli.py` | `argparse` dispatch for every subcommand |
| `schema/*.json` | One JSON Schema per artifact kind |
| `tests/unit/*.py` | Unit tests, one module per source module |
| `tests/fixtures/` | Hand-authored valid and invalid artifacts |

---

### Task 1: Project scaffolding and the run-directory layout

Everything downstream resolves paths through `RunPaths`, so this lands first and carries the project setup with it.

**Files:**
- Create: `pyproject.toml`
- Create: `Makefile`
- Create: `src/testgen/__init__.py`
- Create: `src/testgen/paths.py`
- Test: `tests/unit/test_paths.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `paths.STAGES: tuple[str, ...]`; `paths.safe_segment(value: str) -> str`; `paths.UnsafeSegment(ValueError)`; `paths.RunPaths(root: Path)` with properties `manifest`, `inputs_dir`, `claims_dir`, `world_model`, `scenarios`, `coverage_dir`, `coverage_latest`, `instances_dir`, `verdicts_dir`, `suite_dir`, `report`, `decisions` (all `-> Path`) and methods `claims(artifact_id: str) -> Path`, `coverage_round(round_n: int) -> Path`, `instance_dir(scenario_id: str) -> Path`, `seed(scenario_id: str) -> Path`, `expected(scenario_id: str) -> Path`, `rationale(scenario_id: str) -> Path`, `verdict(scenario_id: str) -> Path`, `task_dir(scenario_id: str) -> Path`, `scenario_ids_with_instances() -> list[str]`.

- [ ] **Step 1: Create the package scaffolding**

`pyproject.toml`:

```toml
[project]
name = "test-generator"
version = "0.1.0"
description = "Skill-based test suite generator for agentic systems"
requires-python = ">=3.13"
dependencies = [
    "jsonschema>=4.23",
    "tomli-w>=1.1",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "ruff>=0.8"]

[project.scripts]
testgen = "testgen.cli:main"

[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`Makefile` (tabs, not spaces, for the recipe lines):

```make
.PHONY: help setup test check lint format

help: ## Show this help
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

setup: ## Create the venv and install runtime + dev deps
	uv venv --python 3.13
	uv pip install -e '.[dev]'

test: ## Run the test suite
	uv run pytest -q

check: ## Lint and verify formatting, making no changes
	uv run ruff check .
	uv run ruff format --check .

lint: ## Auto-fix lint findings
	uv run ruff check --fix .

format: ## Reformat the code
	uv run ruff format .
```

`src/testgen/__init__.py`:

```python
"""Skill-based test suite generator for agentic systems."""

__all__ = ["__version__"]

__version__ = "0.1.0"
```

- [ ] **Step 2: Install and confirm the environment works**

Run: `make setup && uv run python -c "import testgen; print(testgen.__version__)"`
Expected: prints `0.1.0`.

- [ ] **Step 3: Write the failing test**

`tests/unit/test_paths.py`:

```python
from pathlib import Path

import pytest

from testgen.paths import STAGES, RunPaths, UnsafeSegment, safe_segment


def test_stages_are_in_pipeline_order():
    assert STAGES == (
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


def test_safe_segment_accepts_ordinary_ids():
    assert safe_segment("scn-001") == "scn-001"
    assert safe_segment("aap2.api.json") == "aap2.api.json"


@pytest.mark.parametrize(
    "bad",
    [
        "../etc",
        "a/b",
        "..",
        "",
        ".hidden",
        "with space",
        "trailing/",
        "x\x00y",
    ],
)
def test_safe_segment_rejects_anything_that_could_escape(bad):
    with pytest.raises(UnsafeSegment):
        safe_segment(bad)


def test_singleton_artifact_paths():
    rp = RunPaths(Path("/runs/r1"))
    assert rp.manifest == Path("/runs/r1/manifest.json")
    assert rp.inputs_dir == Path("/runs/r1/00-inputs")
    assert rp.claims_dir == Path("/runs/r1/01-claims")
    assert rp.world_model == Path("/runs/r1/01-world-model.json")
    assert rp.scenarios == Path("/runs/r1/02-scenarios.json")
    assert rp.coverage_dir == Path("/runs/r1/03-coverage")
    assert rp.coverage_latest == Path("/runs/r1/03-coverage/latest.json")
    assert rp.instances_dir == Path("/runs/r1/04-instances")
    assert rp.verdicts_dir == Path("/runs/r1/05-verdicts")
    assert rp.suite_dir == Path("/runs/r1/06-suite")
    assert rp.report == Path("/runs/r1/07-report.json")
    assert rp.decisions == Path("/runs/r1/decisions.md")


def test_per_id_artifact_paths():
    rp = RunPaths(Path("/runs/r1"))
    assert rp.claims("aap2-api") == Path("/runs/r1/01-claims/aap2-api.json")
    assert rp.coverage_round(2) == Path("/runs/r1/03-coverage/round-2.json")
    assert rp.instance_dir("scn-001") == Path("/runs/r1/04-instances/scn-001")
    assert rp.seed("scn-001") == Path("/runs/r1/04-instances/scn-001/seed.json")
    assert rp.expected("scn-001") == Path("/runs/r1/04-instances/scn-001/expected.json")
    assert rp.rationale("scn-001") == Path("/runs/r1/04-instances/scn-001/rationale.md")
    assert rp.verdict("scn-001") == Path("/runs/r1/05-verdicts/scn-001.json")
    assert rp.task_dir("scn-001") == Path("/runs/r1/06-suite/scn-001")


def test_per_id_paths_refuse_unsafe_ids():
    rp = RunPaths(Path("/runs/r1"))
    for call in (rp.claims, rp.instance_dir, rp.seed, rp.expected, rp.verdict, rp.task_dir):
        with pytest.raises(UnsafeSegment):
            call("../../etc/passwd")


def test_coverage_round_must_be_positive():
    rp = RunPaths(Path("/runs/r1"))
    with pytest.raises(ValueError):
        rp.coverage_round(0)


def test_scenario_ids_with_instances_lists_sorted_dirs(tmp_path):
    rp = RunPaths(tmp_path)
    for sid in ("scn-002", "scn-001"):
        rp.instance_dir(sid).mkdir(parents=True)
    (rp.instances_dir / "stray-file.json").write_text("{}", encoding="utf-8")
    assert rp.scenario_ids_with_instances() == ["scn-001", "scn-002"]


def test_scenario_ids_with_instances_is_empty_when_stage_has_not_run(tmp_path):
    assert RunPaths(tmp_path).scenario_ids_with_instances() == []
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_paths.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'testgen.paths'`.

- [ ] **Step 5: Write the implementation**

`src/testgen/paths.py`:

```python
"""Run-directory layout: the single source of truth for artifact paths.

Every module reads and writes artifacts through this module, so the on-disk
contract (design spec section 4) is expressed in exactly one place.
"""

from __future__ import annotations

import re
from pathlib import Path

# Stage names in pipeline order. The validate and check-refs CLIs accept
# these, and the orchestrator names the stage it is dispatching with them.
STAGES = (
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

_SAFE_SEGMENT = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")


class UnsafeSegment(ValueError):
    """Raised when an id from an artifact would escape the run directory."""


def safe_segment(value: str) -> str:
    """Return `value` if it is safe to use as one path segment, else raise.

    Ids in artifacts are produced by language models and must never be joined
    into a path unchecked: "../../etc" is a plausible thing for a confused
    stage to emit, and the run directory is the only place we write.
    """
    if not isinstance(value, str) or not _SAFE_SEGMENT.match(value) or ".." in value:
        raise UnsafeSegment(f"unsafe path segment: {value!r}")
    return value


class RunPaths:
    """Resolves every artifact path for one run directory."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def __repr__(self) -> str:
        return f"RunPaths({str(self.root)!r})"

    # -- singleton artifacts ---------------------------------------------
    @property
    def manifest(self) -> Path:
        return self.root / "manifest.json"

    @property
    def inputs_dir(self) -> Path:
        return self.root / "00-inputs"

    @property
    def claims_dir(self) -> Path:
        return self.root / "01-claims"

    @property
    def world_model(self) -> Path:
        return self.root / "01-world-model.json"

    @property
    def scenarios(self) -> Path:
        return self.root / "02-scenarios.json"

    @property
    def coverage_dir(self) -> Path:
        return self.root / "03-coverage"

    @property
    def coverage_latest(self) -> Path:
        return self.coverage_dir / "latest.json"

    @property
    def instances_dir(self) -> Path:
        return self.root / "04-instances"

    @property
    def verdicts_dir(self) -> Path:
        return self.root / "05-verdicts"

    @property
    def suite_dir(self) -> Path:
        return self.root / "06-suite"

    @property
    def report(self) -> Path:
        return self.root / "07-report.json"

    @property
    def decisions(self) -> Path:
        return self.root / "decisions.md"

    # -- per-id artifacts ------------------------------------------------
    def claims(self, artifact_id: str) -> Path:
        return self.claims_dir / f"{safe_segment(artifact_id)}.json"

    def coverage_round(self, round_n: int) -> Path:
        if round_n < 1:
            raise ValueError(f"coverage round must be >= 1, got {round_n}")
        return self.coverage_dir / f"round-{round_n}.json"

    def instance_dir(self, scenario_id: str) -> Path:
        return self.instances_dir / safe_segment(scenario_id)

    def seed(self, scenario_id: str) -> Path:
        return self.instance_dir(scenario_id) / "seed.json"

    def expected(self, scenario_id: str) -> Path:
        return self.instance_dir(scenario_id) / "expected.json"

    def rationale(self, scenario_id: str) -> Path:
        return self.instance_dir(scenario_id) / "rationale.md"

    def verdict(self, scenario_id: str) -> Path:
        return self.verdicts_dir / f"{safe_segment(scenario_id)}.json"

    def task_dir(self, scenario_id: str) -> Path:
        return self.suite_dir / safe_segment(scenario_id)

    # -- listings --------------------------------------------------------
    def scenario_ids_with_instances(self) -> list[str]:
        """Scenario ids that have an instance directory, sorted.

        Stage 5 and stage 6 iterate over this rather than re-reading
        02-scenarios.json, so a scenario rejected after instantiation is
        still visible to them and can be reported rather than vanishing.
        """
        if not self.instances_dir.is_dir():
            return []
        return sorted(p.name for p in self.instances_dir.iterdir() if p.is_dir())
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_paths.py -q`
Expected: PASS, 9 tests.

- [ ] **Step 7: Verify lint and formatting are clean**

Run: `make check`
Expected: no findings.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml Makefile src/testgen/__init__.py src/testgen/paths.py tests/unit/test_paths.py
git commit -S -s -m "feat: Add package scaffolding and run-directory layout

RunPaths is the single source of truth for artifact paths, so the on-disk
stage contract lives in one place. safe_segment guards every id that reaches
the filesystem: artifact ids are model-generated and untrusted.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 2: Artifact I/O and the shared Finding type

Canonical byte-stable JSON, atomic writes, and the one type every checking layer reports in.

**Files:**
- Create: `src/testgen/artifacts.py`
- Create: `src/testgen/findings.py`
- Test: `tests/unit/test_artifacts.py`
- Test: `tests/unit/test_findings.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `artifacts.ArtifactError(Exception)`; `artifacts.read_json(path: Path) -> Any`; `artifacts.write_json(path: Path, payload: Any) -> None`; `artifacts.append_decision(path: Path, entry: str) -> None`; `findings.Finding` — a frozen dataclass with fields `artifact: Path`, `layer: str`, `pointer: str`, `message: str`; `findings.format_findings(items: list[Finding]) -> str`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_artifacts.py`:

```python
import json

import pytest

from testgen.artifacts import ArtifactError, append_decision, read_json, write_json


def test_round_trip(tmp_path):
    path = tmp_path / "nested" / "a.json"
    write_json(path, {"b": 1, "a": [1, 2]})
    assert read_json(path) == {"b": 1, "a": [1, 2]}


def test_output_is_canonical_and_key_order_independent(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_json(first, {"b": 1, "a": 2})
    write_json(second, {"a": 2, "b": 1})
    assert first.read_bytes() == second.read_bytes()
    assert first.read_text(encoding="utf-8") == '{\n  "a": 2,\n  "b": 1\n}\n'


def test_non_ascii_is_written_literally_not_escaped(tmp_path):
    path = tmp_path / "a.json"
    write_json(path, {"msg": "café"})
    assert "café" in path.read_text(encoding="utf-8")


def test_read_missing_artifact_names_the_path(tmp_path):
    with pytest.raises(ArtifactError, match="missing artifact"):
        read_json(tmp_path / "absent.json")


def test_read_malformed_artifact_names_the_path(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ArtifactError, match="malformed JSON"):
        read_json(path)


def test_failed_write_leaves_the_previous_content_intact(tmp_path):
    path = tmp_path / "a.json"
    write_json(path, {"keep": True})
    with pytest.raises(TypeError):
        write_json(path, {"bad": object()})
    assert read_json(path) == {"keep": True}


def test_failed_write_leaves_no_temp_files_behind(tmp_path):
    path = tmp_path / "a.json"
    write_json(path, {"keep": True})
    with pytest.raises(TypeError):
        write_json(path, {"bad": object()})
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.json"]


def test_write_overwrites_in_place(tmp_path):
    path = tmp_path / "a.json"
    write_json(path, {"v": 1})
    write_json(path, {"v": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {"v": 2}


def test_append_decision_creates_then_appends(tmp_path):
    path = tmp_path / "decisions.md"
    append_decision(path, "round 1: continue")
    append_decision(path, "round 2: converged\n")
    assert path.read_text(encoding="utf-8") == "round 1: continue\nround 2: converged\n"
```

`tests/unit/test_findings.py`:

```python
from pathlib import Path

from testgen.findings import Finding, format_findings


def test_str_includes_layer_path_and_pointer():
    f = Finding(Path("/r/01-world-model.json"), "schema", "/capabilities/0", "missing 'operation'")
    assert str(f) == "[schema] /r/01-world-model.json#/capabilities/0: missing 'operation'"


def test_str_omits_the_pointer_for_root_findings():
    f = Finding(Path("/r/a.json"), "refs", "", "unknown capability_id")
    assert str(f) == "[refs] /r/a.json: unknown capability_id"


def test_format_findings_is_sorted_for_stable_output():
    items = [
        Finding(Path("/r/b.json"), "refs", "", "second"),
        Finding(Path("/r/a.json"), "schema", "/x", "first"),
    ]
    assert format_findings(items) == (
        "[schema] /r/a.json#/x: first\n[refs] /r/b.json: second"
    )


def test_format_findings_of_nothing_is_empty():
    assert format_findings([]) == ""


def test_findings_are_hashable_so_callers_can_dedupe():
    a = Finding(Path("/r/a.json"), "refs", "", "dup")
    b = Finding(Path("/r/a.json"), "refs", "", "dup")
    assert len({a, b}) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_artifacts.py tests/unit/test_findings.py -q`
Expected: FAIL — `ModuleNotFoundError` for `testgen.artifacts` and `testgen.findings`.

- [ ] **Step 3: Write findings.py**

`src/testgen/findings.py`:

```python
"""A single validation finding, shared by every checking layer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    """One problem found in one artifact.

    `pointer` is a JSON Pointer into the artifact, or "" for the document
    root. `layer` names the checking layer that produced it, so a reader can
    tell a shape error from a reference error without parsing the message.
    """

    artifact: Path
    layer: str  # "schema" | "refs" | "invariant"
    pointer: str
    message: str

    def __str__(self) -> str:
        where = f"{self.artifact}#{self.pointer}" if self.pointer else str(self.artifact)
        return f"[{self.layer}] {where}: {self.message}"


def format_findings(items: list[Finding]) -> str:
    """Render findings one per line, sorted so output is stable across runs."""
    ordered = sorted(items, key=lambda f: (str(f.artifact), f.pointer, f.layer, f.message))
    return "\n".join(str(f) for f in ordered)
```

- [ ] **Step 4: Write artifacts.py**

`src/testgen/artifacts.py`:

```python
"""Reading and writing run artifacts.

Artifacts are the only channel between pipeline stages, so their on-disk form
has to be stable: two runs that produce the same content must produce
byte-identical files, or diff-runs reports formatting as variance. Hence
sort_keys and a fixed indent.

Writes are atomic because a stage that dies mid-write must not leave a
half-written artifact that the next stage would read as valid JSON.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class ArtifactError(Exception):
    """Raised when an artifact is missing or is not readable JSON."""


def read_json(path: Path | str) -> Any:
    """Read one artifact, raising ArtifactError with the path on any failure."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ArtifactError(f"missing artifact: {path}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ArtifactError(f"malformed JSON in {path}: {exc}") from exc


def write_json(path: Path | str, payload: Any) -> None:
    """Write `payload` atomically in the canonical artifact format.

    Serialization happens before any filesystem mutation, so an unserializable
    payload leaves the previous content and the directory untouched.
    """
    path = Path(path)
    body = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def append_decision(path: Path | str, entry: str) -> None:
    """Append one orchestrator decision to decisions.md.

    decisions.md is the run's append-only lab notebook (design spec section
    4); it is never rewritten, so this is a plain append rather than an
    atomic replace.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(entry.rstrip("\n") + "\n")
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_artifacts.py tests/unit/test_findings.py -q`
Expected: PASS, 14 tests.

- [ ] **Step 6: Verify lint and formatting are clean**

Run: `make check`
Expected: no findings.

- [ ] **Step 7: Commit**

```bash
git add src/testgen/artifacts.py src/testgen/findings.py tests/unit/test_artifacts.py tests/unit/test_findings.py
git commit -S -s -m "feat: Add canonical artifact I/O and the shared Finding type

Artifact JSON is written sort_keys + indent=2 so two runs with identical
content produce byte-identical files; without that, diff-runs would report
key ordering as pipeline variance. Writes serialize before touching the
filesystem and land via os.replace, so a stage dying mid-write cannot leave
a half-written artifact for the next stage to read.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 3: Schema validation, with the claims and world-model schemas

Layer 1 of the three checking layers. The two ingestion schemas land with the validation machinery so it has something real to validate; the remaining schemas follow in Tasks 4 and 5.

Note one deliberate overlap: the `id` pattern in every schema is the same expression `paths.safe_segment` enforces. Schema validation therefore rejects a traversal-shaped id before any code joins it to a path — defence in depth, since a stage's output is validated before anything else reads it.

**Files:**
- Create: `schema/claims-0.1.json`
- Create: `schema/world-model-0.1.json`
- Create: `src/testgen/validate.py`
- Create: `tests/builders.py`
- Test: `tests/unit/test_validate.py`

**Interfaces:**
- Consumes: `paths.STAGES`, `paths.RunPaths`; `artifacts.read_json`, `artifacts.ArtifactError`, `artifacts.write_json`; `findings.Finding`.
- Produces: `validate.ARTIFACT_SCHEMAS: dict[str, str]` (artifact kind → schema filename); `validate.STAGE_ARTIFACTS: dict[str, tuple[str, ...]]` (stage → the kinds it must produce); `validate.UnknownStage(ValueError)`; `validate.schema_dir() -> Path`; `validate.validate_artifact(path: Path, kind: str) -> list[Finding]`; `validate.validate_stage(run: RunPaths, stage: str) -> list[Finding]`. Also `tests/builders.py` with `minimal_claims(**over) -> dict` and `minimal_world_model(**over) -> dict`, each returning a schema-valid payload that later tasks mutate to build negative cases.

- [ ] **Step 1: Write the claims schema**

`schema/claims-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "claims-0.1.json",
  "title": "Claims extracted from one input artifact",
  "type": "object",
  "required": ["schema_version", "artifact_id", "claims"],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "0.1" },
    "artifact_id": { "$ref": "#/$defs/id" },
    "claims": { "type": "array", "items": { "$ref": "#/$defs/claim" } }
  },
  "$defs": {
    "id": {
      "type": "string",
      "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]*$",
      "maxLength": 128
    },
    "claim": {
      "type": "object",
      "required": ["id", "kind", "statement", "evidence", "confidence", "derivation"],
      "additionalProperties": false,
      "properties": {
        "id": { "$ref": "#/$defs/id" },
        "kind": {
          "enum": ["capability", "entity", "invariant", "actor", "goal", "outcome_class"]
        },
        "statement": { "type": "string", "minLength": 1 },
        "payload": { "type": "object" },
        "evidence": {
          "type": "array",
          "minItems": 1,
          "items": { "$ref": "#/$defs/evidence" }
        },
        "confidence": { "enum": ["high", "medium", "low"] },
        "derivation": { "enum": ["stated", "inferred", "reverse_engineered"] }
      }
    },
    "evidence": {
      "type": "object",
      "required": ["artifact_id", "locator"],
      "additionalProperties": false,
      "properties": {
        "artifact_id": { "$ref": "#/$defs/id" },
        "locator": { "type": "string", "minLength": 1 },
        "quote": { "type": "string" }
      }
    }
  }
}
```

`evidence` has `minItems: 1` on purpose: the design spec makes every claim carry provenance, and requiring it in the schema is what stops a stage from asserting an unsourced fact that later stages treat as established.

- [ ] **Step 2: Write the world-model schema**

`schema/world-model-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "world-model-0.1.json",
  "title": "Reconciled world model",
  "type": "object",
  "required": [
    "schema_version", "target", "capabilities", "entities",
    "actors", "goals", "contradictions", "gaps", "denominator"
  ],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "0.1" },
    "target": {
      "type": "object",
      "required": ["name", "interface"],
      "additionalProperties": false,
      "properties": {
        "name": { "type": "string", "minLength": 1 },
        "interface": { "type": "string", "minLength": 1 },
        "notes": { "type": "string" }
      }
    },
    "capabilities": { "type": "array", "items": { "$ref": "#/$defs/capability" } },
    "entities": { "type": "array", "items": { "$ref": "#/$defs/entity" } },
    "actors": { "type": "array", "items": { "$ref": "#/$defs/actor" } },
    "goals": { "type": "array", "items": { "$ref": "#/$defs/goal" } },
    "contradictions": { "type": "array", "items": { "$ref": "#/$defs/contradiction" } },
    "gaps": { "type": "array", "items": { "$ref": "#/$defs/gap" } },
    "denominator": {
      "type": "object",
      "required": ["version", "capability_cells", "goals"],
      "additionalProperties": false,
      "properties": {
        "version": { "type": "integer", "minimum": 1 },
        "capability_cells": { "type": "integer", "minimum": 0 },
        "goals": { "type": "integer", "minimum": 0 }
      }
    }
  },
  "$defs": {
    "id": {
      "type": "string",
      "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]*$",
      "maxLength": 128
    },
    "claim_refs": {
      "type": "array",
      "minItems": 1,
      "items": { "$ref": "#/$defs/id" }
    },
    "capability": {
      "type": "object",
      "required": ["id", "operation", "params", "outcome_classes", "claims", "confidence"],
      "additionalProperties": false,
      "properties": {
        "id": { "$ref": "#/$defs/id" },
        "operation": { "type": "string", "minLength": 1 },
        "params": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["name", "type", "required"],
            "additionalProperties": false,
            "properties": {
              "name": { "type": "string", "minLength": 1 },
              "type": { "type": "string", "minLength": 1 },
              "required": { "type": "boolean" }
            }
          }
        },
        "outcome_classes": {
          "type": "array",
          "minItems": 1,
          "items": {
            "type": "object",
            "required": ["id", "kind", "description"],
            "additionalProperties": false,
            "properties": {
              "id": { "$ref": "#/$defs/id" },
              "kind": {
                "enum": ["success", "empty", "not_found", "error", "underspecified"]
              },
              "description": { "type": "string", "minLength": 1 }
            }
          }
        },
        "claims": { "$ref": "#/$defs/claim_refs" },
        "confidence": { "enum": ["high", "medium", "low"] }
      }
    },
    "entity": {
      "type": "object",
      "required": ["id", "name", "collection", "fields", "claims"],
      "additionalProperties": false,
      "properties": {
        "id": { "$ref": "#/$defs/id" },
        "name": { "type": "string", "minLength": 1 },
        "collection": { "$ref": "#/$defs/id" },
        "fields": {
          "type": "array",
          "minItems": 1,
          "items": {
            "type": "object",
            "required": ["name", "type"],
            "additionalProperties": false,
            "properties": {
              "name": { "type": "string", "minLength": 1 },
              "type": {
                "enum": ["string", "integer", "number", "boolean", "array", "object"]
              }
            }
          }
        },
        "relations": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["name", "target_entity_id", "cardinality"],
            "additionalProperties": false,
            "properties": {
              "name": { "type": "string", "minLength": 1 },
              "target_entity_id": { "$ref": "#/$defs/id" },
              "cardinality": { "enum": ["one", "many"] }
            }
          }
        },
        "invariants": { "type": "array", "items": { "$ref": "#/$defs/invariant" } },
        "claims": { "$ref": "#/$defs/claim_refs" }
      }
    },
    "invariant": {
      "type": "object",
      "required": ["id", "statement"],
      "additionalProperties": false,
      "properties": {
        "id": { "$ref": "#/$defs/id" },
        "statement": { "type": "string", "minLength": 1 },
        "machine": { "$ref": "#/$defs/machine" },
        "prose": { "type": "string", "minLength": 1 }
      },
      "oneOf": [
        { "required": ["machine"], "not": { "required": ["prose"] } },
        { "required": ["prose"], "not": { "required": ["machine"] } }
      ]
    },
    "machine": {
      "type": "object",
      "required": ["form"],
      "oneOf": [
        {
          "type": "object",
          "required": ["form", "collection", "left", "op", "right"],
          "additionalProperties": false,
          "properties": {
            "form": { "const": "compare" },
            "collection": { "$ref": "#/$defs/id" },
            "left": { "type": "string", "minLength": 1 },
            "op": { "enum": ["==", "!=", "<", "<=", ">", ">="] },
            "right": {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "field": { "type": "string", "minLength": 1 },
                "literal": true
              },
              "oneOf": [{ "required": ["field"] }, { "required": ["literal"] }]
            }
          }
        },
        {
          "type": "object",
          "required": ["form", "collection", "field", "of", "local_key", "foreign_key"],
          "additionalProperties": false,
          "properties": {
            "form": { "const": "count" },
            "collection": { "$ref": "#/$defs/id" },
            "field": { "type": "string", "minLength": 1 },
            "of": { "$ref": "#/$defs/id" },
            "local_key": { "type": "string", "minLength": 1 },
            "foreign_key": { "type": "string", "minLength": 1 }
          }
        },
        {
          "type": "object",
          "required": [
            "form", "collection", "field", "of", "source_field",
            "separator", "order_by", "local_key", "foreign_key"
          ],
          "additionalProperties": false,
          "properties": {
            "form": { "const": "join" },
            "collection": { "$ref": "#/$defs/id" },
            "field": { "type": "string", "minLength": 1 },
            "of": { "$ref": "#/$defs/id" },
            "source_field": { "type": "string", "minLength": 1 },
            "separator": { "type": "string" },
            "order_by": { "type": "string", "minLength": 1 },
            "local_key": { "type": "string", "minLength": 1 },
            "foreign_key": { "type": "string", "minLength": 1 }
          }
        },
        {
          "type": "object",
          "required": ["form", "collection", "field"],
          "additionalProperties": false,
          "properties": {
            "form": { "const": "unique" },
            "collection": { "$ref": "#/$defs/id" },
            "field": { "type": "string", "minLength": 1 },
            "within": { "type": "string", "minLength": 1 },
            "increasing": { "type": "boolean" }
          }
        }
      ]
    },
    "actor": {
      "type": "object",
      "required": ["id", "name", "claims"],
      "additionalProperties": false,
      "properties": {
        "id": { "$ref": "#/$defs/id" },
        "name": { "type": "string", "minLength": 1 },
        "claims": { "$ref": "#/$defs/claim_refs" }
      }
    },
    "goal": {
      "type": "object",
      "required": ["id", "actor_id", "statement", "expected_hop_depths", "claims"],
      "additionalProperties": false,
      "properties": {
        "id": { "$ref": "#/$defs/id" },
        "actor_id": { "$ref": "#/$defs/id" },
        "statement": { "type": "string", "minLength": 1 },
        "expected_hop_depths": {
          "type": "array",
          "minItems": 1,
          "uniqueItems": true,
          "items": { "type": "integer", "minimum": 1, "maximum": 5 }
        },
        "claims": { "$ref": "#/$defs/claim_refs" }
      }
    },
    "contradiction": {
      "type": "object",
      "required": ["id", "claim_a", "claim_b", "nature", "resolution", "rationale"],
      "additionalProperties": false,
      "properties": {
        "id": { "$ref": "#/$defs/id" },
        "claim_a": { "$ref": "#/$defs/id" },
        "claim_b": { "$ref": "#/$defs/id" },
        "nature": { "type": "string", "minLength": 1 },
        "resolution": {
          "enum": ["unresolved", "preferred_a", "preferred_b", "both_possible"]
        },
        "rationale": { "type": "string", "minLength": 1 }
      }
    },
    "gap": {
      "type": "object",
      "required": ["id", "subject", "unknown", "why_it_matters", "blocks"],
      "additionalProperties": false,
      "properties": {
        "id": { "$ref": "#/$defs/id" },
        "subject": { "type": "string", "minLength": 1 },
        "unknown": { "type": "string", "minLength": 1 },
        "why_it_matters": { "type": "string", "minLength": 1 },
        "blocks": {
          "type": "array",
          "minItems": 1,
          "uniqueItems": true,
          "items": {
            "enum": ["propose", "score", "instantiate", "challenge", "emit", "smoke"]
          }
        },
        "suggested_input": { "type": "string" }
      }
    }
  }
}
```

Three choices worth understanding before you transcribe them:

- `entity.collection` names the top-level key this entity occupies in a seed file. `refs.py` (Task 7) needs it to walk a seed, and nothing else in the world model carries that mapping.
- `invariant` requires exactly one of `machine` or `prose` via `oneOf`. A reconcile stage that supplies both has not decided whether the invariant is checkable, and a checkable invariant that is also prose would be silently skipped by the evaluator.
- `machine` is a **structured directive**, not an expression string: an object with a `form` discriminator and one branch per form (`compare`, `count`, `join`, `unique`). There is therefore no expression parser and nothing to sandbox — a malformed directive is a schema error, not a runtime one. Task 6 implements the evaluator for exactly these four forms. Anything that does not fit them is recorded as `prose:`; the known example is arithmetic over timestamps (aap2's `duration_seconds == finished - started`).
- `contradiction.rationale` is required even when `resolution` is `unresolved`. Recording *why* something could not be resolved is the whole value of the field.

- [ ] **Step 3: Write the failing tests**

`tests/builders.py`:

```python
"""Minimal schema-valid artifact payloads, for mutation in tests.

Each builder returns the smallest payload its schema accepts. Tests override
one key to construct a negative case, which keeps each test's intent visible
instead of buried in fifty lines of valid boilerplate.
"""

from __future__ import annotations

from typing import Any


def minimal_claims(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "artifact_id": "aap2-api",
        "claims": [
            {
                "id": "clm-001",
                "kind": "capability",
                "statement": "query_aap2 supports action=find_jobs",
                "evidence": [{"artifact_id": "aap2-api", "locator": "api.json#/tools/0"}],
                "confidence": "high",
                "derivation": "stated",
            }
        ],
    }
    payload.update(over)
    return payload


def minimal_world_model(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "target": {"name": "aap2", "interface": "mcp"},
        "capabilities": [
            {
                "id": "cap-find-jobs",
                "operation": "query_aap2.find_jobs",
                "params": [{"name": "controller", "type": "string", "required": True}],
                "outcome_classes": [
                    {"id": "oc-success", "kind": "success", "description": "jobs returned"},
                    {"id": "oc-empty", "kind": "empty", "description": "no jobs match"},
                ],
                "claims": ["clm-001"],
                "confidence": "high",
            }
        ],
        "entities": [
            {
                "id": "ent-job",
                "name": "Job",
                "collection": "jobs",
                "fields": [
                    {"name": "job_id", "type": "integer"},
                    {"name": "status", "type": "string"},
                ],
                "claims": ["clm-001"],
            }
        ],
        "actors": [{"id": "act-sre", "name": "SRE", "claims": ["clm-001"]}],
        "goals": [
            {
                "id": "goal-triage",
                "actor_id": "act-sre",
                "statement": "Find out why a job failed",
                "expected_hop_depths": [1, 2],
                "claims": ["clm-001"],
            }
        ],
        "contradictions": [],
        "gaps": [],
        "denominator": {"version": 1, "capability_cells": 2, "goals": 1},
    }
    payload.update(over)
    return payload
```

`tests/unit/test_validate.py`:

```python
import pytest

from testgen.artifacts import write_json
from testgen.paths import RunPaths
from testgen.validate import (
    ARTIFACT_SCHEMAS,
    STAGE_ARTIFACTS,
    UnknownStage,
    schema_dir,
    validate_artifact,
    validate_stage,
)
from tests.builders import minimal_claims, minimal_world_model


def test_every_stage_has_an_artifact_mapping():
    from testgen.paths import STAGES

    assert set(STAGE_ARTIFACTS) == set(STAGES)


def test_every_mapped_kind_has_a_registered_schema():
    mapped = {k for kinds in STAGE_ARTIFACTS.values() for k in kinds}
    assert mapped <= set(ARTIFACT_SCHEMAS)


def test_registered_schemas_exist_on_disk():
    for filename in ARTIFACT_SCHEMAS.values():
        assert (schema_dir() / filename).is_file(), filename


def test_minimal_claims_is_valid(tmp_path):
    path = tmp_path / "c.json"
    write_json(path, minimal_claims())
    assert validate_artifact(path, "claims") == []


def test_minimal_world_model_is_valid(tmp_path):
    path = tmp_path / "wm.json"
    write_json(path, minimal_world_model())
    assert validate_artifact(path, "world-model") == []


def test_claim_without_evidence_is_rejected(tmp_path):
    payload = minimal_claims()
    payload["claims"][0]["evidence"] = []
    path = tmp_path / "c.json"
    write_json(path, payload)
    findings = validate_artifact(path, "claims")
    assert findings
    assert findings[0].layer == "schema"
    assert findings[0].pointer == "/claims/0/evidence"


def test_traversal_shaped_id_is_rejected_by_the_schema(tmp_path):
    payload = minimal_claims()
    payload["claims"][0]["id"] = "../../etc/passwd"
    path = tmp_path / "c.json"
    write_json(path, payload)
    assert any(f.pointer == "/claims/0/id" for f in validate_artifact(path, "claims"))


def test_wrong_schema_version_is_rejected(tmp_path):
    path = tmp_path / "c.json"
    write_json(path, minimal_claims(schema_version="0.2"))
    assert any(f.pointer == "/schema_version" for f in validate_artifact(path, "claims"))


def test_unknown_top_level_key_is_rejected(tmp_path):
    path = tmp_path / "c.json"
    write_json(path, minimal_claims(surprise=1))
    assert validate_artifact(path, "claims")


def test_structured_machine_invariant_is_valid(tmp_path):
    payload = minimal_world_model()
    payload["entities"][0]["invariants"] = [
        {
            "id": "inv-event-count",
            "statement": "event_count equals the number of matching job_events",
            "machine": {
                "form": "count",
                "collection": "jobs",
                "field": "event_count",
                "of": "job_events",
                "local_key": "job_id",
                "foreign_key": "job_id",
            },
        }
    ]
    path = tmp_path / "wm.json"
    write_json(path, payload)
    assert validate_artifact(path, "world-model") == []


def test_machine_invariant_with_an_unknown_form_is_rejected(tmp_path):
    payload = minimal_world_model()
    payload["entities"][0]["invariants"] = [
        {"id": "inv-1", "statement": "s", "machine": {"form": "regex", "pattern": ".*"}}
    ]
    path = tmp_path / "wm.json"
    write_json(path, payload)
    assert validate_artifact(path, "world-model")


def test_machine_compare_needs_exactly_one_of_field_or_literal(tmp_path):
    payload = minimal_world_model()
    payload["entities"][0]["invariants"] = [
        {
            "id": "inv-1",
            "statement": "s",
            "machine": {
                "form": "compare",
                "collection": "jobs",
                "left": "log_trimmed_size",
                "op": "<=",
                "right": {"field": "log_original_size", "literal": 0},
            },
        }
    ]
    path = tmp_path / "wm.json"
    write_json(path, payload)
    assert validate_artifact(path, "world-model")


def test_invariant_with_both_machine_and_prose_is_rejected(tmp_path):
    payload = minimal_world_model()
    payload["entities"][0]["invariants"] = [
        {
            "id": "inv-1",
            "statement": "both",
            "machine": {"form": "unique", "collection": "jobs", "field": "job_id"},
            "prose": "also prose",
        }
    ]
    path = tmp_path / "wm.json"
    write_json(path, payload)
    assert validate_artifact(path, "world-model")


def test_invariant_with_neither_machine_nor_prose_is_rejected(tmp_path):
    payload = minimal_world_model()
    payload["entities"][0]["invariants"] = [{"id": "inv-1", "statement": "neither"}]
    path = tmp_path / "wm.json"
    write_json(path, payload)
    assert validate_artifact(path, "world-model")


def test_gap_must_name_what_it_blocks(tmp_path):
    payload = minimal_world_model()
    payload["gaps"] = [
        {
            "id": "gap-1",
            "subject": "error semantics",
            "unknown": "what happens on an unknown controller",
            "why_it_matters": "cannot build not_found scenarios",
            "blocks": [],
        }
    ]
    path = tmp_path / "wm.json"
    write_json(path, payload)
    assert any(f.pointer == "/gaps/0/blocks" for f in validate_artifact(path, "world-model"))


def test_missing_artifact_is_reported_not_raised(tmp_path):
    findings = validate_artifact(tmp_path / "absent.json", "claims")
    assert len(findings) == 1
    assert "missing artifact" in findings[0].message


def test_malformed_artifact_is_reported_not_raised(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{oops", encoding="utf-8")
    findings = validate_artifact(path, "claims")
    assert len(findings) == 1
    assert "malformed JSON" in findings[0].message


def test_validate_stage_walks_every_claims_file(tmp_path):
    run = RunPaths(tmp_path)
    write_json(run.claims("good"), minimal_claims(artifact_id="good"))
    bad = minimal_claims(artifact_id="bad")
    bad["claims"][0]["confidence"] = "certain"
    write_json(run.claims("bad"), bad)
    findings = validate_stage(run, "extract")
    assert len(findings) == 1
    assert findings[0].artifact == run.claims("bad")


def test_validate_stage_reports_a_stage_that_produced_nothing(tmp_path):
    findings = validate_stage(RunPaths(tmp_path), "reconcile")
    assert len(findings) == 1
    assert "produced no world-model artifact" in findings[0].message


def test_validate_stage_rejects_an_unknown_stage(tmp_path):
    with pytest.raises(UnknownStage):
        validate_stage(RunPaths(tmp_path), "reconsile")


def test_stages_with_no_json_artifact_pass_trivially(tmp_path):
    assert validate_stage(RunPaths(tmp_path), "emit") == []
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_validate.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'testgen.validate'`.

- [ ] **Step 5: Write the implementation**

`src/testgen/validate.py`:

```python
"""JSON Schema validation of run artifacts: layer 1 of three.

Layer 1 checks shape only. Cross-artifact references, seed-pointer
reachability, and world-model invariants are layer 2 and live in refs.py;
layer 3 is the smoke gate. A stage's output must clear layer 1 before the
orchestrator dispatches the next stage (design spec section 5).

Findings are returned, never raised: the orchestrator's contract is one
bounded repair attempt with the findings appended to the stage prompt, which
needs the full list rather than the first failure.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path

from jsonschema import Draft202012Validator

from testgen.artifacts import ArtifactError, read_json
from testgen.findings import Finding
from testgen.paths import STAGES, RunPaths

# Artifact kind -> schema filename.
ARTIFACT_SCHEMAS: dict[str, str] = {
    "manifest": "manifest-0.1.json",
    "claims": "claims-0.1.json",
    "world-model": "world-model-0.1.json",
    "scenarios": "scenarios-0.1.json",
    "coverage": "coverage-0.1.json",
    "seed": "seed-0.1.json",
    "expected": "expected-0.1.json",
    "verdict": "verdict-0.1.json",
}

# Which artifact kinds each stage must produce. Stages that emit no JSON
# artifact of their own map to an empty tuple and pass layer 1 trivially;
# they are gated by check-refs and by the smoke report instead.
STAGE_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "intake": ("manifest",),
    "extract": ("claims",),
    "reconcile": ("world-model",),
    "propose": ("scenarios",),
    "score": ("coverage",),
    "instantiate": ("seed", "expected"),
    "challenge": ("verdict",),
    "emit": (),
    "smoke": (),
}


class UnknownStage(ValueError):
    """Raised for a stage name that is not in paths.STAGES."""


def schema_dir() -> Path:
    """Directory holding the artifact schemas.

    Overridable via TESTGEN_SCHEMA_DIR so a caller can validate against a
    candidate schema set without reinstalling the package.
    """
    override = os.environ.get("TESTGEN_SCHEMA_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "schema"


@functools.cache
def _validator_for(kind: str, schema_root: Path) -> Draft202012Validator:
    """Compiled validator, cached on (kind, schema_root).

    schema_root is part of the key rather than read inside, so overriding
    TESTGEN_SCHEMA_DIR does not return a validator built from the old one.
    """
    try:
        filename = ARTIFACT_SCHEMAS[kind]
    except KeyError as exc:
        raise KeyError(f"no schema registered for artifact kind {kind!r}") from exc
    schema = read_json(schema_root / filename)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _pointer(parts) -> str:
    return "".join(f"/{part}" for part in parts)


def validate_artifact(path: Path, kind: str) -> list[Finding]:
    """Validate one artifact file against the schema for `kind`."""
    path = Path(path)
    try:
        payload = read_json(path)
    except ArtifactError as exc:
        return [Finding(path, "schema", "", str(exc))]
    validator = _validator_for(kind, schema_dir())
    return [
        Finding(path, "schema", _pointer(error.absolute_path), error.message)
        for error in validator.iter_errors(payload)
    ]


def _artifact_paths(run: RunPaths, kind: str) -> list[Path]:
    """Every file of `kind` that should exist in this run."""
    if kind == "manifest":
        return [run.manifest]
    if kind == "world-model":
        return [run.world_model]
    if kind == "scenarios":
        return [run.scenarios]
    if kind == "claims":
        return sorted(run.claims_dir.glob("*.json")) if run.claims_dir.is_dir() else []
    if kind == "coverage":
        return sorted(run.coverage_dir.glob("*.json")) if run.coverage_dir.is_dir() else []
    if kind == "verdict":
        return sorted(run.verdicts_dir.glob("*.json")) if run.verdicts_dir.is_dir() else []
    if kind == "seed":
        return [run.seed(sid) for sid in run.scenario_ids_with_instances()]
    if kind == "expected":
        return [run.expected(sid) for sid in run.scenario_ids_with_instances()]
    raise KeyError(f"unknown artifact kind {kind!r}")


def validate_stage(run: RunPaths, stage: str) -> list[Finding]:
    """Validate every artifact the named stage is responsible for.

    An expected-but-absent artifact is itself a finding. A stage that
    produced nothing has failed, and passing silently would let the
    orchestrator dispatch the next stage against a missing input.
    """
    if stage not in STAGES:
        raise UnknownStage(f"unknown stage {stage!r}; expected one of {', '.join(STAGES)}")
    findings: list[Finding] = []
    for kind in STAGE_ARTIFACTS[stage]:
        paths = _artifact_paths(run, kind)
        if not paths:
            findings.append(
                Finding(run.root, "schema", "", f"stage {stage!r} produced no {kind} artifact")
            )
        for path in paths:
            findings.extend(validate_artifact(path, kind))
    return findings
```

- [ ] **Step 6: Make `tests/` importable as a package**

The tests import `tests.builders`, so `tests/` needs an `__init__.py`.

Run: `touch tests/__init__.py tests/unit/__init__.py`

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_validate.py -q`
Expected: PASS, 21 tests.

- [ ] **Step 8: Run the whole suite and the lint gate**

Run: `make test && make check`
Expected: all tests pass, no lint findings.

- [ ] **Step 9: Commit**

```bash
git add schema/claims-0.1.json schema/world-model-0.1.json src/testgen/validate.py \
        tests/builders.py tests/unit/test_validate.py tests/__init__.py tests/unit/__init__.py
git commit -S -s -m "feat: Add schema validation with the claims and world-model schemas

validate_artifact returns findings rather than raising: the orchestrator's
contract is one bounded repair attempt with the findings appended to the
stage prompt, so it needs the whole list, not the first failure.

Two shape rules are load-bearing rather than decorative. Claims require at
least one evidence entry, so no stage can assert an unsourced fact that later
stages then treat as established. And the id pattern matches what
paths.safe_segment enforces, so a traversal-shaped id is rejected at
validation time, before any code joins it to a path.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 4: The scenarios, coverage, and manifest schemas

Three schemas, no new code. They land together because they share the `hole_ref` string form and reviewing that form once is better than reviewing it twice.

**Refinement of the design spec.** §4 writes scenario status as `duplicate_of:<id>` and `rejected:<reason>` — compound strings. Encode them as a `status` enum plus separate `duplicate_of` and `rejected_reason` fields, made conditionally required with `if`/`then`. A compound string cannot be validated for a well-formed target id, and every consumer would have to re-parse it.

**Hole references** use a canonical string form: `cell:<capability_id>/<outcome_class_id>` or `goal:<goal_id>`. Greppable, sortable, and one field rather than a tagged union. The pattern is repeated in both schemas that use it rather than shared by `$ref` across files — each schema stays independently readable, at the cost of one duplicated regex.

**Files:**
- Create: `schema/scenarios-0.1.json`
- Create: `schema/coverage-0.1.json`
- Create: `schema/manifest-0.1.json`
- Modify: `tests/builders.py` (append three builders)
- Test: `tests/unit/test_schemas_planning.py`

**Interfaces:**
- Consumes: `validate.validate_artifact`; `artifacts.write_json`.
- Produces: `tests/builders.py` gains `minimal_scenarios(**over) -> dict`, `minimal_coverage(**over) -> dict`, `minimal_manifest(**over) -> dict`. Field names fixed here and relied on by Tasks 7 and 9: a scenario has `capability_refs: [{capability_id, outcome_class_id}]`, `provenance: {hole_refs, claim_ids, round}`, and `status` in `{proposed, active, duplicate, rejected}`; a coverage document has `capability_matrix.cells[]`, `goal_matrix.rows[]`, `holes[].ref`, `progress`, and `verdict`; a manifest has `inputs[]`, `stages{}`, and `limits.max_rounds` / `limits.max_scenarios`.

- [ ] **Step 1: Write the scenarios schema**

`schema/scenarios-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "scenarios-0.1.json",
  "title": "Proposed test scenarios",
  "type": "object",
  "required": ["schema_version", "denominator_version", "scenarios"],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "0.1" },
    "denominator_version": { "type": "integer", "minimum": 1 },
    "scenarios": { "type": "array", "items": { "$ref": "#/$defs/scenario" } }
  },
  "$defs": {
    "id": {
      "type": "string",
      "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]*$",
      "maxLength": 128
    },
    "hole_ref": {
      "type": "string",
      "pattern": "^(cell:[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*|goal:[A-Za-z0-9][A-Za-z0-9._-]*)$"
    },
    "scenario": {
      "type": "object",
      "required": [
        "id", "round", "goal_id", "actor_id", "title", "user_intent",
        "hop_depth", "capability_refs", "discriminating_fact", "status", "provenance"
      ],
      "additionalProperties": false,
      "properties": {
        "id": { "$ref": "#/$defs/id" },
        "round": { "type": "integer", "minimum": 1 },
        "goal_id": { "$ref": "#/$defs/id" },
        "actor_id": { "$ref": "#/$defs/id" },
        "title": { "type": "string", "minLength": 1 },
        "user_intent": { "type": "string", "minLength": 1 },
        "hop_depth": { "type": "integer", "minimum": 1, "maximum": 5 },
        "capability_refs": {
          "type": "array",
          "minItems": 1,
          "items": {
            "type": "object",
            "required": ["capability_id", "outcome_class_id"],
            "additionalProperties": false,
            "properties": {
              "capability_id": { "$ref": "#/$defs/id" },
              "outcome_class_id": { "$ref": "#/$defs/id" }
            }
          }
        },
        "discriminating_fact": { "type": "string", "minLength": 1 },
        "status": { "enum": ["proposed", "active", "duplicate", "rejected"] },
        "duplicate_of": { "$ref": "#/$defs/id" },
        "rejected_reason": {
          "enum": ["ambiguous", "not_derivable", "wrong_label", "out_of_scope", "blocked_by_gap"]
        },
        "provenance": {
          "type": "object",
          "required": ["hole_refs", "claim_ids", "round"],
          "additionalProperties": false,
          "properties": {
            "hole_refs": {
              "type": "array",
              "minItems": 1,
              "items": { "$ref": "#/$defs/hole_ref" }
            },
            "claim_ids": { "type": "array", "items": { "$ref": "#/$defs/id" } },
            "round": { "type": "integer", "minimum": 1 }
          }
        }
      },
      "allOf": [
        {
          "if": { "properties": { "status": { "const": "duplicate" } }, "required": ["status"] },
          "then": { "required": ["duplicate_of"] }
        },
        {
          "if": { "properties": { "status": { "const": "rejected" } }, "required": ["status"] },
          "then": { "required": ["rejected_reason"] }
        }
      ]
    }
  }
}
```

`provenance.hole_refs` has `minItems: 1`: a scenario that targets no hole is a scenario nobody asked for, and the enrichment loop's progress arithmetic depends on every scenario declaring what it was meant to close.

- [ ] **Step 2: Write the coverage schema**

`schema/coverage-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "coverage-0.1.json",
  "title": "Coverage report for one enrichment round",
  "type": "object",
  "required": [
    "schema_version", "round", "denominator_version",
    "capability_matrix", "goal_matrix", "holes", "progress", "verdict"
  ],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "0.1" },
    "round": { "type": "integer", "minimum": 1 },
    "denominator_version": { "type": "integer", "minimum": 1 },
    "capability_matrix": {
      "type": "object",
      "required": ["cells", "covered", "total", "pct"],
      "additionalProperties": false,
      "properties": {
        "cells": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["capability_id", "outcome_class_id", "scenario_ids", "covered"],
            "additionalProperties": false,
            "properties": {
              "capability_id": { "$ref": "#/$defs/id" },
              "outcome_class_id": { "$ref": "#/$defs/id" },
              "scenario_ids": { "type": "array", "items": { "$ref": "#/$defs/id" } },
              "covered": { "type": "boolean" }
            }
          }
        },
        "covered": { "type": "integer", "minimum": 0 },
        "total": { "type": "integer", "minimum": 0 },
        "pct": { "$ref": "#/$defs/fraction" }
      }
    },
    "goal_matrix": {
      "type": "object",
      "required": ["rows", "covered", "total", "pct"],
      "additionalProperties": false,
      "properties": {
        "rows": {
          "type": "array",
          "items": {
            "type": "object",
            "required": [
              "goal_id", "scenario_ids", "hop_depths_present",
              "hop_depths_expected", "covered"
            ],
            "additionalProperties": false,
            "properties": {
              "goal_id": { "$ref": "#/$defs/id" },
              "scenario_ids": { "type": "array", "items": { "$ref": "#/$defs/id" } },
              "hop_depths_present": { "$ref": "#/$defs/hop_depths" },
              "hop_depths_expected": { "$ref": "#/$defs/hop_depths" },
              "covered": { "type": "boolean" }
            }
          }
        },
        "covered": { "type": "integer", "minimum": 0 },
        "total": { "type": "integer", "minimum": 0 },
        "pct": { "$ref": "#/$defs/fraction" }
      }
    },
    "holes": { "type": "array", "items": { "$ref": "#/$defs/hole" } },
    "progress": {
      "type": "object",
      "required": ["new_cells_this_round", "rounds_without_progress"],
      "additionalProperties": false,
      "properties": {
        "new_cells_this_round": { "type": "integer", "minimum": 0 },
        "rounds_without_progress": { "type": "integer", "minimum": 0 }
      }
    },
    "verdict": {
      "enum": ["continue", "converged", "halted_no_progress", "halted_round_cap"]
    }
  },
  "$defs": {
    "id": {
      "type": "string",
      "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]*$",
      "maxLength": 128
    },
    "fraction": { "type": "number", "minimum": 0, "maximum": 1 },
    "hop_depths": {
      "type": "array",
      "uniqueItems": true,
      "items": { "type": "integer", "minimum": 1, "maximum": 5 }
    },
    "hole_ref": {
      "type": "string",
      "pattern": "^(cell:[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*|goal:[A-Za-z0-9][A-Za-z0-9._-]*)$"
    },
    "hole": {
      "type": "object",
      "required": ["ref", "reason", "justification"],
      "additionalProperties": false,
      "properties": {
        "ref": { "$ref": "#/$defs/hole_ref" },
        "reason": {
          "enum": ["not_yet_attempted", "unreachable", "out_of_scope", "blocked_by_gap"]
        },
        "justification": { "type": "string", "minLength": 1 },
        "gap_id": { "$ref": "#/$defs/id" }
      },
      "if": { "properties": { "reason": { "const": "blocked_by_gap" } }, "required": ["reason"] },
      "then": { "required": ["gap_id"] }
    }
  }
}
```

`justification` is required for every hole, including `not_yet_attempted` — that is what stops the loop from silently truncating coverage. `pct` is a fraction in `[0, 1]`, never a percentage; pick one and the reports stay comparable.

- [ ] **Step 3: Write the manifest schema**

`schema/manifest-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "manifest-0.1.json",
  "title": "Run manifest",
  "type": "object",
  "required": ["schema_version", "run_id", "created_utc", "target", "inputs", "stages", "limits"],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "0.1" },
    "run_id": { "$ref": "#/$defs/id" },
    "created_utc": { "type": "string", "format": "date-time" },
    "target": {
      "type": "object",
      "required": ["name", "interface"],
      "additionalProperties": false,
      "properties": {
        "name": { "type": "string", "minLength": 1 },
        "interface": { "type": "string", "minLength": 1 }
      }
    },
    "inputs": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["artifact_id", "source_path", "sha256", "kind", "bytes"],
        "additionalProperties": false,
        "properties": {
          "artifact_id": { "$ref": "#/$defs/id" },
          "source_path": { "type": "string", "minLength": 1 },
          "sha256": { "$ref": "#/$defs/sha256" },
          "kind": {
            "enum": [
              "openapi", "mcp_tool_schema", "entity_schema",
              "trace", "design_doc", "source_code", "other"
            ]
          },
          "bytes": { "type": "integer", "minimum": 0 }
        }
      }
    },
    "stages": {
      "type": "object",
      "propertyNames": {
        "enum": [
          "intake", "extract", "reconcile", "propose", "score",
          "instantiate", "challenge", "emit", "smoke"
        ]
      },
      "additionalProperties": {
        "type": "object",
        "required": ["model", "effort", "skill_sha256"],
        "additionalProperties": false,
        "properties": {
          "model": { "type": "string", "minLength": 1 },
          "effort": { "enum": ["low", "medium", "high", "xhigh", "max"] },
          "skill_sha256": { "$ref": "#/$defs/sha256" }
        }
      }
    },
    "limits": {
      "type": "object",
      "required": ["max_rounds", "max_scenarios"],
      "additionalProperties": false,
      "properties": {
        "max_rounds": { "type": "integer", "minimum": 1 },
        "max_scenarios": { "type": "integer", "minimum": 1 }
      }
    }
  },
  "$defs": {
    "id": {
      "type": "string",
      "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]*$",
      "maxLength": 128
    },
    "sha256": { "type": "string", "pattern": "^[0-9a-f]{64}$" }
  }
}
```

`stages` records model, effort, and the SKILL.md content hash per stage. That triple is what makes two runs comparable, so `diff-runs` can refuse to compare runs that used different prompts. `limits` is where the first slice's `max_rounds: 2` and `max_scenarios: 8` live.

- [ ] **Step 4: Write the failing tests**

Append to `tests/builders.py`:

```python
def minimal_scenarios(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "denominator_version": 1,
        "scenarios": [
            {
                "id": "scn-001",
                "round": 1,
                "goal_id": "goal-triage",
                "actor_id": "act-sre",
                "title": "Find the failing job on prod0",
                "user_intent": "A job failed on prod0. Which one, and why?",
                "hop_depth": 2,
                "capability_refs": [
                    {"capability_id": "cap-find-jobs", "outcome_class_id": "oc-success"}
                ],
                "discriminating_fact": "exactly one prod0 job failed inside the window",
                "status": "active",
                "provenance": {
                    "hole_refs": ["cell:cap-find-jobs/oc-success"],
                    "claim_ids": ["clm-001"],
                    "round": 1,
                },
            }
        ],
    }
    payload.update(over)
    return payload


def minimal_coverage(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "round": 1,
        "denominator_version": 1,
        "capability_matrix": {
            "cells": [
                {
                    "capability_id": "cap-find-jobs",
                    "outcome_class_id": "oc-success",
                    "scenario_ids": ["scn-001"],
                    "covered": True,
                },
                {
                    "capability_id": "cap-find-jobs",
                    "outcome_class_id": "oc-empty",
                    "scenario_ids": [],
                    "covered": False,
                },
            ],
            "covered": 1,
            "total": 2,
            "pct": 0.5,
        },
        "goal_matrix": {
            "rows": [
                {
                    "goal_id": "goal-triage",
                    "scenario_ids": ["scn-001"],
                    "hop_depths_present": [2],
                    "hop_depths_expected": [1, 2],
                    "covered": False,
                }
            ],
            "covered": 0,
            "total": 1,
            "pct": 0.0,
        },
        "holes": [
            {
                "ref": "cell:cap-find-jobs/oc-empty",
                "reason": "not_yet_attempted",
                "justification": "no scenario has exercised the empty-result path yet",
            }
        ],
        "progress": {"new_cells_this_round": 1, "rounds_without_progress": 0},
        "verdict": "continue",
    }
    payload.update(over)
    return payload


def minimal_manifest(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "run_id": "run-20260806-120000",
        "created_utc": "2026-08-06T12:00:00Z",
        "target": {"name": "aap2", "interface": "mcp"},
        "inputs": [
            {
                "artifact_id": "aap2-api",
                "source_path": "harness-skills/parsec-aap2/api.json",
                "sha256": "a" * 64,
                "kind": "mcp_tool_schema",
                "bytes": 4096,
            }
        ],
        "stages": {
            "reconcile": {"model": "claude-opus-5", "effort": "high", "skill_sha256": "b" * 64}
        },
        "limits": {"max_rounds": 2, "max_scenarios": 8},
    }
    payload.update(over)
    return payload
```

`tests/unit/test_schemas_planning.py`:

```python
from testgen.artifacts import write_json
from testgen.validate import validate_artifact
from tests.builders import minimal_coverage, minimal_manifest, minimal_scenarios


def _findings(tmp_path, kind, payload):
    path = tmp_path / f"{kind}.json"
    write_json(path, payload)
    return validate_artifact(path, kind)


def test_minimal_scenarios_is_valid(tmp_path):
    assert _findings(tmp_path, "scenarios", minimal_scenarios()) == []


def test_minimal_coverage_is_valid(tmp_path):
    assert _findings(tmp_path, "coverage", minimal_coverage()) == []


def test_minimal_manifest_is_valid(tmp_path):
    assert _findings(tmp_path, "manifest", minimal_manifest()) == []


def test_duplicate_status_requires_a_target(tmp_path):
    payload = minimal_scenarios()
    payload["scenarios"][0]["status"] = "duplicate"
    assert _findings(tmp_path, "scenarios", payload)


def test_duplicate_status_with_a_target_is_valid(tmp_path):
    payload = minimal_scenarios()
    payload["scenarios"][0]["status"] = "duplicate"
    payload["scenarios"][0]["duplicate_of"] = "scn-000"
    assert _findings(tmp_path, "scenarios", payload) == []


def test_rejected_status_requires_a_reason(tmp_path):
    payload = minimal_scenarios()
    payload["scenarios"][0]["status"] = "rejected"
    assert _findings(tmp_path, "scenarios", payload)


def test_rejected_reason_is_a_closed_set(tmp_path):
    payload = minimal_scenarios()
    payload["scenarios"][0]["status"] = "rejected"
    payload["scenarios"][0]["rejected_reason"] = "did not like it"
    assert _findings(tmp_path, "scenarios", payload)


def test_scenario_must_target_at_least_one_hole(tmp_path):
    payload = minimal_scenarios()
    payload["scenarios"][0]["provenance"]["hole_refs"] = []
    findings = _findings(tmp_path, "scenarios", payload)
    assert any(f.pointer == "/scenarios/0/provenance/hole_refs" for f in findings)


def test_malformed_hole_ref_is_rejected(tmp_path):
    payload = minimal_scenarios()
    payload["scenarios"][0]["provenance"]["hole_refs"] = ["cap-find-jobs"]
    assert _findings(tmp_path, "scenarios", payload)


def test_goal_hole_ref_is_accepted(tmp_path):
    payload = minimal_scenarios()
    payload["scenarios"][0]["provenance"]["hole_refs"] = ["goal:goal-triage"]
    assert _findings(tmp_path, "scenarios", payload) == []


def test_hop_depth_above_five_is_rejected(tmp_path):
    payload = minimal_scenarios()
    payload["scenarios"][0]["hop_depth"] = 6
    assert _findings(tmp_path, "scenarios", payload)


def test_every_hole_needs_a_justification(tmp_path):
    payload = minimal_coverage()
    del payload["holes"][0]["justification"]
    assert _findings(tmp_path, "coverage", payload)


def test_blocked_by_gap_hole_must_name_the_gap(tmp_path):
    payload = minimal_coverage()
    payload["holes"][0]["reason"] = "blocked_by_gap"
    assert _findings(tmp_path, "coverage", payload)


def test_blocked_by_gap_hole_with_a_gap_id_is_valid(tmp_path):
    payload = minimal_coverage()
    payload["holes"][0]["reason"] = "blocked_by_gap"
    payload["holes"][0]["gap_id"] = "gap-1"
    assert _findings(tmp_path, "coverage", payload) == []


def test_pct_is_a_fraction_not_a_percentage(tmp_path):
    payload = minimal_coverage()
    payload["capability_matrix"]["pct"] = 50
    assert _findings(tmp_path, "coverage", payload)


def test_coverage_verdict_is_a_closed_set(tmp_path):
    assert _findings(tmp_path, "coverage", minimal_coverage(verdict="keep_going"))


def test_manifest_requires_at_least_one_input(tmp_path):
    assert _findings(tmp_path, "manifest", minimal_manifest(inputs=[]))


def test_manifest_rejects_a_short_sha(tmp_path):
    payload = minimal_manifest()
    payload["inputs"][0]["sha256"] = "abc123"
    assert _findings(tmp_path, "manifest", payload)


def test_manifest_rejects_an_unknown_stage_name(tmp_path):
    payload = minimal_manifest()
    payload["stages"]["reconsile"] = payload["stages"].pop("reconcile")
    assert _findings(tmp_path, "manifest", payload)


def test_manifest_stage_entry_needs_the_full_comparability_triple(tmp_path):
    payload = minimal_manifest()
    del payload["stages"]["reconcile"]["skill_sha256"]
    assert _findings(tmp_path, "manifest", payload)
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_schemas_planning.py -q`
Expected: FAIL — the first three tests fail with a missing-schema `KeyError`, since `read_json` cannot find the new schema files.

- [ ] **Step 6: Confirm the schemas make the tests pass**

The schemas from Steps 1–3 are the implementation; there is no Python to write.

Run: `uv run pytest tests/unit/test_schemas_planning.py -q`
Expected: PASS, 20 tests.

- [ ] **Step 7: Run the whole suite and the lint gate**

Run: `make test && make check`
Expected: all tests pass, no lint findings.

- [ ] **Step 8: Commit**

```bash
git add schema/scenarios-0.1.json schema/coverage-0.1.json schema/manifest-0.1.json \
        tests/builders.py tests/unit/test_schemas_planning.py
git commit -S -s -m "feat: Add the scenarios, coverage, and manifest schemas

Scenario status is an enum plus separate duplicate_of and rejected_reason
fields, conditionally required, rather than the spec's compound
'duplicate_of:<id>' string: a compound string cannot be validated for a
well-formed target id and every consumer would re-parse it.

Two rules exist to stop silent truncation. Every hole requires a
justification, including not_yet_attempted, so an uncovered cell is always
accounted for. And every scenario must declare at least one hole it targets,
since the loop's progress arithmetic is computed from those declarations.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 5: The seed, expected, and verdict schemas

The three per-scenario artifacts. Two decisions here differ from the design spec and both need to land in the spec too, which is the last step of this task.

**The seed schema validates the envelope only.** A seed's real shape is dictated by the world model's entities, not by a fixed schema, so there is nothing generic to assert beyond "an object of named collections, each an array of objects." Semantic validity — do the collection names match the world model's entities, do the field names and types match, do the invariants hold — is layer 2, in Tasks 6 and 7. This is the concrete reason the invariant evaluator is worth building rather than optional: without it, a seed is almost entirely unchecked.

**`negative_expectations` is dropped.** The spec lists it alongside `assertions`, with "must not claim a root cause the data does not support" as the example — but that is exactly `answer_excludes`, which is already in the closed vocabulary. A second field expressing the same thing would either duplicate the verifier's logic or, worse, hold prose that nothing evaluates. Everything the field was for is expressible as `answer_excludes` and `tool_not_called`.

**Grounding differs by assertion kind.** Data assertions (`answer_contains`, `answer_excludes`, `value_equals`) require `grounded_in.seed_pointer` — a JSON Pointer into this scenario's own seed. Trajectory assertions (`tool_called`, `tool_not_called`) are grounded in the world model instead and carry `capability_id`; a JSON Pointer into seed data would be meaningless for them. The schema enforces exactly one of the two shapes per kind.

**Files:**
- Create: `schema/seed-0.1.json`
- Create: `schema/expected-0.1.json`
- Create: `schema/verdict-0.1.json`
- Modify: `tests/builders.py` (append three builders)
- Modify: `docs/superpowers/specs/2026-08-06-skill-based-test-generator-design.md` (§4 oracle schema)
- Test: `tests/unit/test_schemas_instance.py`

**Interfaces:**
- Consumes: `validate.validate_artifact`; `artifacts.write_json`.
- Produces: `tests/builders.py` gains `minimal_seed(**over) -> dict`, `minimal_expected(**over) -> dict`, `minimal_verdict(**over) -> dict`. Field names fixed here and relied on by Task 7 and by the emit layer: a seed is `{schema_version, collections: {<collection>: [ {...} ]}}`; an expected document has `assertions[].kind`, `assertions[].grounded_in.seed_pointer` (data kinds) or `assertions[].capability_id` (trajectory kinds), plus `trajectory.operations[].capability_id` and `completion`.

- [ ] **Step 1: Write the seed schema**

`schema/seed-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "seed-0.1.json",
  "title": "Seed world for one scenario (envelope only)",
  "description": "A seed's real shape comes from the world model's entities, so this schema constrains only the envelope. Collection names, field names and types, and invariants are checked by refs.py against the world model.",
  "type": "object",
  "required": ["schema_version", "collections"],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "0.1" },
    "collections": {
      "type": "object",
      "minProperties": 1,
      "propertyNames": { "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]*$" },
      "additionalProperties": {
        "type": "array",
        "items": { "type": "object" }
      }
    }
  }
}
```

- [ ] **Step 2: Write the expected schema**

`schema/expected-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "expected-0.1.json",
  "title": "Oracle for one scenario",
  "type": "object",
  "required": [
    "schema_version", "scenario_id", "discriminating_fact",
    "answer_reference", "assertions", "trajectory", "completion"
  ],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "0.1" },
    "scenario_id": { "$ref": "#/$defs/id" },
    "discriminating_fact": { "type": "string", "minLength": 1 },
    "answer_reference": { "type": "string", "minLength": 1 },
    "assertions": {
      "type": "array",
      "minItems": 1,
      "items": { "$ref": "#/$defs/assertion" }
    },
    "trajectory": {
      "type": "object",
      "required": ["match", "operations"],
      "additionalProperties": false,
      "properties": {
        "match": { "enum": ["subset", "exact-set", "exact-sequence"] },
        "operations": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["capability_id", "args"],
            "additionalProperties": false,
            "properties": {
              "capability_id": { "$ref": "#/$defs/id" },
              "args": { "type": "object" }
            }
          }
        }
      }
    },
    "completion": {
      "type": "object",
      "required": ["status", "nonempty_answer"],
      "additionalProperties": false,
      "properties": {
        "status": { "enum": ["ok", "error"] },
        "nonempty_answer": { "type": "boolean" }
      }
    }
  },
  "$defs": {
    "id": {
      "type": "string",
      "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]*$",
      "maxLength": 128
    },
    "assertion": {
      "type": "object",
      "required": ["kind", "value", "rationale"],
      "properties": {
        "kind": {
          "enum": [
            "answer_contains",
            "answer_excludes",
            "tool_called",
            "tool_not_called",
            "value_equals"
          ]
        },
        "target": { "type": "string", "minLength": 1 },
        "value": { "type": "string", "minLength": 1 },
        "rationale": { "type": "string", "minLength": 1 },
        "capability_id": { "$ref": "#/$defs/id" },
        "grounded_in": {
          "type": "object",
          "required": ["seed_pointer"],
          "additionalProperties": false,
          "properties": {
            "seed_pointer": { "type": "string", "pattern": "^/" }
          }
        }
      },
      "allOf": [
        {
          "if": {
            "properties": {
              "kind": { "enum": ["answer_contains", "answer_excludes", "value_equals"] }
            },
            "required": ["kind"]
          },
          "then": {
            "required": ["grounded_in"],
            "not": { "required": ["capability_id"] },
            "additionalProperties": false,
            "properties": {
              "kind": true,
              "target": true,
              "value": true,
              "rationale": true,
              "grounded_in": true
            }
          }
        },
        {
          "if": {
            "properties": { "kind": { "enum": ["tool_called", "tool_not_called"] } },
            "required": ["kind"]
          },
          "then": {
            "required": ["capability_id"],
            "not": { "required": ["grounded_in"] },
            "additionalProperties": false,
            "properties": {
              "kind": true,
              "target": true,
              "value": true,
              "rationale": true,
              "capability_id": true
            }
          }
        }
      ]
    }
  }
}
```

The `additionalProperties: false` sits inside each `then` branch rather than on the assertion object, because a single top-level `additionalProperties` cannot see keywords introduced by `allOf` branches and would reject every valid assertion. This is the one genuinely subtle piece of JSON Schema in the project — if you find yourself fighting it, the rule being expressed is: a data assertion has `grounded_in` and no `capability_id`; a trajectory assertion has `capability_id` and no `grounded_in`.

- [ ] **Step 3: Write the verdict schema**

`schema/verdict-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "verdict-0.1.json",
  "title": "Adversarial verdict for one instantiated scenario",
  "type": "object",
  "required": [
    "schema_version", "scenario_id", "uniquely_determined",
    "derivable_without_guessing", "minimum_tool_calls_found", "verdict", "notes"
  ],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "0.1" },
    "scenario_id": { "$ref": "#/$defs/id" },
    "uniquely_determined": { "type": "boolean" },
    "alternative_answers": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["answer", "world_consistent_reason"],
        "additionalProperties": false,
        "properties": {
          "answer": { "type": "string", "minLength": 1 },
          "world_consistent_reason": { "type": "string", "minLength": 1 }
        }
      }
    },
    "derivable_without_guessing": { "type": "boolean" },
    "minimum_tool_calls_found": { "type": "integer", "minimum": 0 },
    "verdict": { "enum": ["accept", "re-seed", "reject"] },
    "flags": {
      "type": "array",
      "uniqueItems": true,
      "items": { "enum": ["difficulty_overstated"] }
    },
    "notes": { "type": "string", "minLength": 1 }
  },
  "allOf": [
    {
      "if": {
        "properties": { "uniquely_determined": { "const": false } },
        "required": ["uniquely_determined"]
      },
      "then": {
        "required": ["alternative_answers"],
        "properties": { "alternative_answers": { "minItems": 1 } }
      }
    }
  ],
  "$defs": {
    "id": {
      "type": "string",
      "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]*$",
      "maxLength": 128
    }
  }
}
```

Claiming a scenario is not uniquely determined obliges the adversary to produce the second answer. Without that rule, "ambiguous" becomes a costless way out of hard reasoning, and the `re-seed` loop gets no information to work with.

- [ ] **Step 4: Write the failing tests**

Append to `tests/builders.py`:

```python
def minimal_seed(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "collections": {
            "jobs": [
                {"job_id": 90420, "status": "failed", "controller": "prod0"},
                {"job_id": 90421, "status": "successful", "controller": "prod0"},
            ]
        },
    }
    payload.update(over)
    return payload


def minimal_expected(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "scenario_id": "scn-001",
        "discriminating_fact": "exactly one prod0 job has status failed",
        "answer_reference": "Job 90420 failed on prod0.",
        "assertions": [
            {
                "kind": "answer_contains",
                "target": "answer",
                "value": "90420",
                "rationale": "the failing job id must appear in the answer",
                "grounded_in": {"seed_pointer": "/collections/jobs/0/job_id"},
            },
            {
                "kind": "tool_called",
                "target": "query_aap2.find_jobs",
                "value": "at least once",
                "rationale": "the agent must query rather than guess",
                "capability_id": "cap-find-jobs",
            },
        ],
        "trajectory": {
            "match": "subset",
            "operations": [{"capability_id": "cap-find-jobs", "args": {"controller": "prod0"}}],
        },
        "completion": {"status": "ok", "nonempty_answer": True},
    }
    payload.update(over)
    return payload


def minimal_verdict(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "scenario_id": "scn-001",
        "uniquely_determined": True,
        "derivable_without_guessing": True,
        "minimum_tool_calls_found": 2,
        "verdict": "accept",
        "notes": "answered independently from the seed and matched the oracle",
    }
    payload.update(over)
    return payload
```

`tests/unit/test_schemas_instance.py`:

```python
from testgen.artifacts import write_json
from testgen.validate import validate_artifact
from tests.builders import minimal_expected, minimal_seed, minimal_verdict


def _findings(tmp_path, kind, payload):
    path = tmp_path / f"{kind}.json"
    write_json(path, payload)
    return validate_artifact(path, kind)


def test_minimal_seed_is_valid(tmp_path):
    assert _findings(tmp_path, "seed", minimal_seed()) == []


def test_seed_must_have_at_least_one_collection(tmp_path):
    assert _findings(tmp_path, "seed", minimal_seed(collections={}))


def test_seed_collection_must_be_an_array_of_objects(tmp_path):
    assert _findings(tmp_path, "seed", minimal_seed(collections={"jobs": [1, 2]}))


def test_seed_permits_arbitrary_entity_fields(tmp_path):
    payload = minimal_seed(collections={"anything": [{"whatever": {"nested": True}}]})
    assert _findings(tmp_path, "seed", payload) == []


def test_minimal_expected_is_valid(tmp_path):
    assert _findings(tmp_path, "expected", minimal_expected()) == []


def test_data_assertion_without_grounding_is_rejected(tmp_path):
    payload = minimal_expected()
    del payload["assertions"][0]["grounded_in"]
    assert _findings(tmp_path, "expected", payload)


def test_data_assertion_may_not_carry_a_capability_id(tmp_path):
    payload = minimal_expected()
    payload["assertions"][0]["capability_id"] = "cap-find-jobs"
    assert _findings(tmp_path, "expected", payload)


def test_trajectory_assertion_without_a_capability_id_is_rejected(tmp_path):
    payload = minimal_expected()
    del payload["assertions"][1]["capability_id"]
    assert _findings(tmp_path, "expected", payload)


def test_trajectory_assertion_may_not_carry_grounding(tmp_path):
    payload = minimal_expected()
    payload["assertions"][1]["grounded_in"] = {"seed_pointer": "/collections/jobs/0"}
    assert _findings(tmp_path, "expected", payload)


def test_answer_excludes_is_grounded_like_other_data_assertions(tmp_path):
    payload = minimal_expected()
    payload["assertions"] = [
        {
            "kind": "answer_excludes",
            "target": "answer",
            "value": "root cause",
            "rationale": "the log does not support a root-cause claim",
            "grounded_in": {"seed_pointer": "/collections/jobs/0/error_msg"},
        }
    ]
    assert _findings(tmp_path, "expected", payload) == []


def test_assertion_kind_is_closed(tmp_path):
    payload = minimal_expected()
    payload["assertions"][0]["kind"] = "answer_matches_regex"
    assert _findings(tmp_path, "expected", payload)


def test_seed_pointer_must_be_a_json_pointer(tmp_path):
    payload = minimal_expected()
    payload["assertions"][0]["grounded_in"]["seed_pointer"] = "collections.jobs[0]"
    assert _findings(tmp_path, "expected", payload)


def test_expected_needs_at_least_one_assertion(tmp_path):
    assert _findings(tmp_path, "expected", minimal_expected(assertions=[]))


def test_negative_expectations_is_not_a_field(tmp_path):
    payload = minimal_expected()
    payload["negative_expectations"] = [{"statement": "no root cause claimed"}]
    assert _findings(tmp_path, "expected", payload)


def test_minimal_verdict_is_valid(tmp_path):
    assert _findings(tmp_path, "verdict", minimal_verdict()) == []


def test_ambiguity_claim_requires_the_second_answer(tmp_path):
    payload = minimal_verdict(uniquely_determined=False, verdict="re-seed")
    assert _findings(tmp_path, "verdict", payload)


def test_ambiguity_claim_with_an_alternative_is_valid(tmp_path):
    payload = minimal_verdict(
        uniquely_determined=False,
        verdict="re-seed",
        alternative_answers=[
            {"answer": "Job 90421 failed.", "world_consistent_reason": "also outside the window"}
        ],
    )
    assert _findings(tmp_path, "verdict", payload) == []


def test_verdict_notes_may_not_be_empty(tmp_path):
    assert _findings(tmp_path, "verdict", minimal_verdict(notes=""))


def test_difficulty_overstated_is_the_only_flag(tmp_path):
    assert _findings(tmp_path, "verdict", minimal_verdict(flags=["too_easy"]))
    assert _findings(tmp_path, "verdict", minimal_verdict(flags=["difficulty_overstated"])) == []
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_schemas_instance.py -q`
Expected: FAIL — missing-schema `KeyError` for the three new kinds.

- [ ] **Step 6: Run the tests to verify the schemas make them pass**

Run: `uv run pytest tests/unit/test_schemas_instance.py -q`
Expected: PASS, 19 tests.

- [ ] **Step 7: Amend the design spec to match**

Two decisions in this task diverge from the spec, so the spec has to move. In §4, replace the oracle schema sketch's assertion and `negative_expectations` lines:

Replace this block:

```
 assertions: [{kind: answer_contains|answer_excludes|tool_called|tool_not_called|value_equals,
               target, value, rationale,
               grounded_in: {seed_pointer}}],       ← JSON pointer into this scenario's seed.json
 trajectory: {match, operations}, completion: {status, nonempty_answer},
 negative_expectations: [...]}
```

with:

```
 assertions: [{kind: answer_contains|answer_excludes|value_equals,
               target, value, rationale,
               grounded_in: {seed_pointer}}          ← JSON pointer into this scenario's seed.json
              |{kind: tool_called|tool_not_called,
               target, value, rationale, capability_id}],  ← grounded in the world model instead
 trajectory: {match, operations}, completion: {status, nonempty_answer}}
```

Then add this paragraph immediately after that code block:

```
Grounding differs by assertion kind. Data assertions point into the seed;
trajectory assertions name a capability, because a JSON pointer into seed data
would be meaningless for them. There is no separate `negative_expectations`
field: everything it was for — "must not claim a root cause the data does not
support" — is `answer_excludes`, and a second field expressing the same thing
would either duplicate the verifier or hold prose nothing evaluates.
```

- [ ] **Step 8: Run the whole suite and the lint gate**

Run: `make test && make check`
Expected: all tests pass, no lint findings.

- [ ] **Step 9: Commit**

```bash
git add schema/seed-0.1.json schema/expected-0.1.json schema/verdict-0.1.json \
        tests/builders.py tests/unit/test_schemas_instance.py \
        docs/superpowers/specs/2026-08-06-skill-based-test-generator-design.md
git commit -S -s -m "feat: Add the seed, expected, and verdict schemas

The seed schema constrains the envelope only. A seed's real shape comes from
the world model's entities, so collection names, field types, and invariants
are layer 2 -- which is why the invariant evaluator is load-bearing rather
than optional: without it a seed is almost entirely unchecked.

Grounding now differs by assertion kind: data assertions carry a JSON pointer
into their own seed, trajectory assertions carry a capability_id, and the
schema permits exactly one shape per kind. Drops negative_expectations, which
duplicated answer_excludes and would otherwise have held prose that nothing
evaluates. Spec section 4 amended to match both changes.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 6: The machine-invariant evaluator

Evaluates a world-model `machine:` directive against a seed's collections. Pure functions over plain dicts, no I/O, no dependency on any other `testgen` module — which makes it the easiest component in the project to test exhaustively, and it should be.

This is the component that gives the seed schema's permissiveness a floor. Task 5 deliberately validates only a seed's envelope; everything else a seed can get wrong is caught here or in Task 7.

**Files:**
- Create: `src/testgen/invariants.py`
- Test: `tests/unit/test_invariants.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `invariants.OPS: dict[str, object]` (comparison operator table); `invariants.InvariantForm(ValueError)`; `invariants.evaluate(machine: dict, collections: dict) -> list[str]` — returns one human-readable message per violation, empty when the invariant holds. Task 7 calls this once per `machine:` invariant per seed and wraps each message in a `Finding` with layer `"invariant"`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_invariants.py`:

```python
import pytest

from testgen.invariants import InvariantForm, evaluate

JOBS = {
    "jobs": [
        {"job_id": 1, "event_count": 2, "log": "a\nb", "trimmed": 5, "original": 9},
        {"job_id": 2, "event_count": 0, "log": "", "trimmed": 0, "original": 0},
    ],
    "job_events": [
        {"job_id": 1, "counter": 1, "stdout": "a"},
        {"job_id": 1, "counter": 2, "stdout": "b"},
    ],
}


# -- compare ------------------------------------------------------------
def test_compare_field_to_field_holds():
    m = {
        "form": "compare",
        "collection": "jobs",
        "left": "trimmed",
        "op": "<=",
        "right": {"field": "original"},
    }
    assert evaluate(m, JOBS) == []


def test_compare_field_to_field_reports_the_offending_record():
    m = {
        "form": "compare",
        "collection": "jobs",
        "left": "original",
        "op": "<",
        "right": {"field": "trimmed"},
    }
    violations = evaluate(m, JOBS)
    assert len(violations) == 2
    assert "jobs[0]" in violations[0]


def test_compare_field_to_literal_holds():
    m = {
        "form": "compare",
        "collection": "jobs",
        "left": "trimmed",
        "op": ">=",
        "right": {"literal": 0},
    }
    assert evaluate(m, JOBS) == []


def test_compare_reports_a_missing_field_rather_than_passing():
    m = {
        "form": "compare",
        "collection": "jobs",
        "left": "absent",
        "op": "==",
        "right": {"literal": 1},
    }
    violations = evaluate(m, JOBS)
    assert len(violations) == 2
    assert "no field 'absent'" in violations[0]


def test_compare_reports_incomparable_types_rather_than_raising():
    m = {
        "form": "compare",
        "collection": "jobs",
        "left": "log",
        "op": "<",
        "right": {"literal": 5},
    }
    violations = evaluate(m, JOBS)
    assert len(violations) == 2
    assert "cannot compare" in violations[0]


# -- count --------------------------------------------------------------
COUNT = {
    "form": "count",
    "collection": "jobs",
    "field": "event_count",
    "of": "job_events",
    "local_key": "job_id",
    "foreign_key": "job_id",
}


def test_count_holds_for_a_consistent_seed():
    assert evaluate(COUNT, JOBS) == []


def test_count_reports_a_declared_value_that_disagrees_with_the_records():
    collections = {
        "jobs": [{"job_id": 1, "event_count": 7}],
        "job_events": [{"job_id": 1, "counter": 1}],
    }
    violations = evaluate(COUNT, collections)
    assert len(violations) == 1
    assert "event_count=7" in violations[0]
    assert "has 1" in violations[0]


def test_count_of_zero_related_records_holds():
    collections = {"jobs": [{"job_id": 9, "event_count": 0}], "job_events": []}
    assert evaluate(COUNT, collections) == []


# -- join ---------------------------------------------------------------
JOIN = {
    "form": "join",
    "collection": "jobs",
    "field": "log",
    "of": "job_events",
    "source_field": "stdout",
    "separator": "\n",
    "order_by": "counter",
    "local_key": "job_id",
    "foreign_key": "job_id",
}


def test_join_holds_when_the_field_is_the_ordered_concatenation():
    assert evaluate(JOIN, JOBS) == []


def test_join_respects_order_by_not_seed_order():
    collections = {
        "jobs": [{"job_id": 1, "log": "a\nb"}],
        "job_events": [
            {"job_id": 1, "counter": 2, "stdout": "b"},
            {"job_id": 1, "counter": 1, "stdout": "a"},
        ],
    }
    assert evaluate(JOIN, collections) == []


def test_join_reports_a_field_that_does_not_match():
    collections = {
        "jobs": [{"job_id": 1, "log": "wrong"}],
        "job_events": [{"job_id": 1, "counter": 1, "stdout": "a"}],
    }
    violations = evaluate(JOIN, collections)
    assert len(violations) == 1
    assert "ordered join" in violations[0]


def test_join_reports_related_records_missing_the_order_by_field():
    collections = {
        "jobs": [{"job_id": 1, "log": "a"}],
        "job_events": [{"job_id": 1, "stdout": "a"}],
    }
    violations = evaluate(JOIN, collections)
    assert len(violations) == 1
    assert "order_by" in violations[0]


# -- unique -------------------------------------------------------------
def test_unique_holds_for_distinct_values():
    m = {"form": "unique", "collection": "jobs", "field": "job_id"}
    assert evaluate(m, JOBS) == []


def test_unique_reports_duplicates():
    m = {"form": "unique", "collection": "jobs", "field": "job_id"}
    collections = {"jobs": [{"job_id": 1}, {"job_id": 1}]}
    violations = evaluate(m, collections)
    assert len(violations) == 1
    assert "duplicate" in violations[0]


def test_unique_within_a_group_permits_repeats_across_groups():
    m = {"form": "unique", "collection": "job_events", "field": "counter", "within": "job_id"}
    collections = {
        "job_events": [
            {"job_id": 1, "counter": 1},
            {"job_id": 2, "counter": 1},
        ]
    }
    assert evaluate(m, collections) == []


def test_unique_within_a_group_still_catches_repeats_inside_one_group():
    m = {"form": "unique", "collection": "job_events", "field": "counter", "within": "job_id"}
    collections = {
        "job_events": [
            {"job_id": 1, "counter": 1},
            {"job_id": 1, "counter": 1},
        ]
    }
    violations = evaluate(m, collections)
    assert len(violations) == 1
    assert "job_id" in violations[0]


def test_increasing_holds_for_an_ascending_sequence():
    m = {
        "form": "unique",
        "collection": "job_events",
        "field": "counter",
        "within": "job_id",
        "increasing": True,
    }
    assert evaluate(m, JOBS) == []


def test_increasing_reports_a_descending_sequence():
    m = {
        "form": "unique",
        "collection": "job_events",
        "field": "counter",
        "within": "job_id",
        "increasing": True,
    }
    collections = {
        "job_events": [
            {"job_id": 1, "counter": 2},
            {"job_id": 1, "counter": 1},
        ]
    }
    violations = evaluate(m, collections)
    assert len(violations) == 1
    assert "increasing" in violations[0]


# -- boundaries ---------------------------------------------------------
def test_an_absent_collection_yields_no_violations():
    """Collection presence is refs.py's job, not this module's.

    Reporting it here as well would double-count the same defect in the
    check-refs output.
    """
    m = {"form": "unique", "collection": "absent", "field": "x"}
    assert evaluate(m, JOBS) == []


def test_an_unimplemented_form_raises():
    with pytest.raises(InvariantForm, match="regex"):
        evaluate({"form": "regex", "collection": "jobs", "field": "log"}, JOBS)


def test_violation_messages_are_deterministic():
    m = {"form": "unique", "collection": "jobs", "field": "job_id"}
    collections = {"jobs": [{"job_id": 1}, {"job_id": 1}, {"job_id": 2}, {"job_id": 2}]}
    assert evaluate(m, collections) == evaluate(m, collections)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_invariants.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'testgen.invariants'`.

- [ ] **Step 3: Write the implementation**

`src/testgen/invariants.py`:

```python
"""Evaluating world-model `machine:` invariants against a seed.

Deliberately not an expression language. Each invariant is a structured
directive with a `form` discriminator, so there is nothing to parse and
nothing to sandbox: a malformed directive fails schema validation before it
ever reaches this module. Four forms cover the invariant classes observed in
the aap2 simulation skill; anything that does not fit is recorded as `prose:`
and left to the authoring stage's own self-check.

Known limit: arithmetic over timestamps (aap2's
`duration_seconds == finished - started`) is not expressible here and must be
prose. A `derive` form is the natural extension when a second target needs it.

Every function returns violation messages rather than raising, because a
seed with three problems should report three problems in one pass.
"""

from __future__ import annotations

import operator
from typing import Any, Callable

OPS: dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}


class InvariantForm(ValueError):
    """Raised when an invariant's form is not one this module implements."""


class _Missing:
    def __repr__(self) -> str:
        return "<missing>"


MISSING = _Missing()


def _records(collections: dict[str, Any], name: str) -> list[dict[str, Any]]:
    """Records in a collection, or empty if the seed has no such collection.

    An absent collection is refs.py's finding to report; duplicating it here
    would double-count one defect in the check-refs output.
    """
    value = collections.get(name)
    return value if isinstance(value, list) else []


def _field(record: dict[str, Any], name: str) -> Any:
    return record.get(name, MISSING)


def evaluate(machine: dict[str, Any], collections: dict[str, Any]) -> list[str]:
    """Check one invariant against a seed's collections.

    Returns one message per violation; an empty list means the invariant
    holds (or that there was nothing in the seed to check it against).
    """
    form = machine.get("form")
    handler = _HANDLERS.get(form)
    if handler is None:
        raise InvariantForm(f"unimplemented invariant form: {form!r}")
    return handler(machine, collections)


def _compare(m: dict[str, Any], collections: dict[str, Any]) -> list[str]:
    out: list[str] = []
    coll, left_name, op = m["collection"], m["left"], m["op"]
    for i, record in enumerate(_records(collections, coll)):
        left = _field(record, left_name)
        if left is MISSING:
            out.append(f"{coll}[{i}] has no field {left_name!r}")
            continue
        if "literal" in m["right"]:
            right = m["right"]["literal"]
            right_label = repr(right)
        else:
            right_name = m["right"]["field"]
            right = _field(record, right_name)
            if right is MISSING:
                out.append(f"{coll}[{i}] has no field {right_name!r}")
                continue
            right_label = f"{right_name}={right!r}"
        try:
            holds = OPS[op](left, right)
        except TypeError:
            out.append(f"{coll}[{i}]: cannot compare {left!r} {op} {right!r}")
            continue
        if not holds:
            out.append(f"{coll}[{i}]: {left_name}={left!r} {op} {right_label} is false")
    return out


def _related(m: dict[str, Any], collections: dict[str, Any], key: Any) -> list[dict[str, Any]]:
    return [r for r in _records(collections, m["of"]) if r.get(m["foreign_key"]) == key]


def _count(m: dict[str, Any], collections: dict[str, Any]) -> list[str]:
    out: list[str] = []
    coll, field, local_key = m["collection"], m["field"], m["local_key"]
    for i, record in enumerate(_records(collections, coll)):
        declared = _field(record, field)
        key = _field(record, local_key)
        if declared is MISSING:
            out.append(f"{coll}[{i}] has no field {field!r}")
            continue
        if key is MISSING:
            out.append(f"{coll}[{i}] has no field {local_key!r}")
            continue
        actual = len(_related(m, collections, key))
        if declared != actual:
            out.append(
                f"{coll}[{i}].{field}={declared} but {m['of']} has {actual} record(s) "
                f"with {m['foreign_key']}=={key!r}"
            )
    return out


def _join(m: dict[str, Any], collections: dict[str, Any]) -> list[str]:
    out: list[str] = []
    coll, field, local_key = m["collection"], m["field"], m["local_key"]
    order_by, source_field, sep = m["order_by"], m["source_field"], m["separator"]
    for i, record in enumerate(_records(collections, coll)):
        declared = _field(record, field)
        key = _field(record, local_key)
        if declared is MISSING:
            out.append(f"{coll}[{i}] has no field {field!r}")
            continue
        if key is MISSING:
            out.append(f"{coll}[{i}] has no field {local_key!r}")
            continue
        matches = _related(m, collections, key)
        if any(order_by not in r for r in matches):
            out.append(
                f"{m['of']} record(s) for {m['foreign_key']}=={key!r} are missing "
                f"order_by field {order_by!r}"
            )
            continue
        try:
            matches = sorted(matches, key=lambda r: r[order_by])
        except TypeError:
            out.append(f"{m['of']} order_by field {order_by!r} has incomparable values")
            continue
        expected = sep.join(str(r.get(source_field, "")) for r in matches)
        if declared != expected:
            out.append(
                f"{coll}[{i}].{field} is not the ordered join of "
                f"{m['of']}.{source_field} by {order_by}"
            )
    return out


def _unique(m: dict[str, Any], collections: dict[str, Any]) -> list[str]:
    out: list[str] = []
    coll, field = m["collection"], m["field"]
    within = m.get("within")
    groups: dict[Any, list[Any]] = {}
    for i, record in enumerate(_records(collections, coll)):
        value = _field(record, field)
        if value is MISSING:
            out.append(f"{coll}[{i}] has no field {field!r}")
            continue
        key: Any = None
        if within is not None:
            key = _field(record, within)
            if key is MISSING:
                out.append(f"{coll}[{i}] has no field {within!r}")
                continue
        groups.setdefault(key, []).append(value)

    # Groups are walked in a repr-sorted order so messages are identical
    # across runs; diff-runs would otherwise report ordering as variance.
    for key in sorted(groups, key=repr):
        values = groups[key]
        where = f" within {within}=={key!r}" if within is not None else ""
        duplicates = sorted({v for v in values if values.count(v) > 1}, key=repr)
        if duplicates:
            out.append(f"{coll}.{field} has duplicate value(s) {duplicates}{where}")
        if m.get("increasing"):
            try:
                ascending = all(a < b for a, b in zip(values, values[1:], strict=False))
            except TypeError:
                out.append(f"{coll}.{field} has incomparable values{where}")
                continue
            if not ascending:
                out.append(f"{coll}.{field} is not strictly increasing{where}")
    return out


_HANDLERS: dict[Any, Callable[[dict[str, Any], dict[str, Any]], list[str]]] = {
    "compare": _compare,
    "count": _count,
    "join": _join,
    "unique": _unique,
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_invariants.py -q`
Expected: PASS, 22 tests.

- [ ] **Step 5: Run the whole suite and the lint gate**

Run: `make test && make check`
Expected: all tests pass, no lint findings.

- [ ] **Step 6: Commit**

```bash
git add src/testgen/invariants.py tests/unit/test_invariants.py
git commit -S -s -m "feat: Add the machine-invariant evaluator

Four structured forms -- compare, count, join, unique -- cover the invariant
classes the aap2 simulation skill actually declares. Because invariants are
structured directives rather than expression strings, there is no parser and
nothing to sandbox: a malformed directive fails schema validation before it
reaches this module.

Everything returns messages rather than raising, so a seed with three
problems reports three problems in one pass. Group iteration is repr-sorted
so messages are byte-identical across runs; unsorted dict order would make
diff-runs report message ordering as pipeline variance.

An absent collection yields no violations here on purpose -- collection
presence is check-refs' finding, and reporting it in both places would
double-count one defect.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 7: Referential integrity for the world model, scenarios, and coverage

Layer 2, first half. Everything JSON Schema cannot express about the planning artifacts: do ids resolve, and does the arithmetic add up.

`check_all` must tolerate a partially-populated run directory. check-refs runs after *every* stage, so at the point reconcile finishes there is no `02-scenarios.json` yet, and that absence is normal rather than a finding. Absence of an artifact is validate's business (Task 3, which reports a stage that produced nothing); presence-but-inconsistent is this module's.

**The denominator check is the highest-value assertion in this task.** `denominator.capability_cells` must equal the actual number of (capability, outcome_class) pairs, and `denominator.goals` must equal the number of goals. A reconcile stage that miscounts corrupts every coverage percentage downstream, and nothing else in the pipeline would notice — the numbers would simply be confidently wrong.

**Files:**
- Create: `src/testgen/refs.py`
- Test: `tests/unit/test_refs_planning.py`

**Interfaces:**
- Consumes: `paths.RunPaths`; `artifacts.read_json`, `artifacts.ArtifactError`; `findings.Finding`.
- Produces: `refs.cell_ref(capability_id: str, outcome_class_id: str) -> str`; `refs.goal_ref(goal_id: str) -> str`; `refs.parse_hole_ref(ref: str) -> tuple[str, tuple[str, ...]]` returning `("cell", (cap, oc))` or `("goal", (goal,))` and raising `ValueError` on a malformed ref; `refs.check_world_model(run: RunPaths) -> list[Finding]`; `refs.check_scenarios(run: RunPaths) -> list[Finding]`; `refs.check_coverage(run: RunPaths) -> list[Finding]`; `refs.check_all(run: RunPaths) -> list[Finding]`. Task 8 adds `check_instances` and `check_verdicts` and extends `check_all`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_refs_planning.py`:

```python
import pytest

from testgen.artifacts import write_json
from testgen.paths import RunPaths
from testgen.refs import (
    cell_ref,
    check_all,
    check_coverage,
    check_scenarios,
    check_world_model,
    goal_ref,
    parse_hole_ref,
)
from tests.builders import minimal_claims, minimal_coverage, minimal_scenarios, minimal_world_model


def _run(tmp_path, *, claims=True, world=True, scenarios=False, coverage=False):
    run = RunPaths(tmp_path)
    if claims:
        write_json(run.claims("aap2-api"), minimal_claims())
    if world:
        write_json(run.world_model, minimal_world_model())
    if scenarios:
        write_json(run.scenarios, minimal_scenarios())
    if coverage:
        write_json(run.coverage_latest, minimal_coverage())
    return run


# -- hole refs ----------------------------------------------------------
def test_cell_and_goal_refs_round_trip():
    assert parse_hole_ref(cell_ref("cap-a", "oc-b")) == ("cell", ("cap-a", "oc-b"))
    assert parse_hole_ref(goal_ref("goal-x")) == ("goal", ("goal-x",))


def test_cell_ref_has_the_documented_string_form():
    assert cell_ref("cap-a", "oc-b") == "cell:cap-a/oc-b"
    assert goal_ref("goal-x") == "goal:goal-x"


@pytest.mark.parametrize("bad", ["cap-a", "cell:cap-a", "goal:", "cell:a/b/c", ""])
def test_malformed_hole_refs_raise(bad):
    with pytest.raises(ValueError):
        parse_hole_ref(bad)


# -- world model --------------------------------------------------------
def test_a_consistent_world_model_has_no_findings(tmp_path):
    assert check_world_model(_run(tmp_path)) == []


def test_a_claim_reference_with_no_matching_claim_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["capabilities"][0]["claims"] = ["clm-999"]
    write_json(run.world_model, world)
    findings = check_world_model(run)
    assert any("clm-999" in f.message for f in findings)
    assert all(f.layer == "refs" for f in findings)


def test_a_goal_pointing_at_an_unknown_actor_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["goals"][0]["actor_id"] = "act-ghost"
    write_json(run.world_model, world)
    assert any("act-ghost" in f.message for f in check_world_model(run))


def test_a_relation_pointing_at_an_unknown_entity_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["entities"][0]["relations"] = [
        {"name": "events", "target_entity_id": "ent-ghost", "cardinality": "many"}
    ]
    write_json(run.world_model, world)
    assert any("ent-ghost" in f.message for f in check_world_model(run))


def test_a_contradiction_citing_an_unknown_claim_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["contradictions"] = [
        {
            "id": "con-1",
            "claim_a": "clm-001",
            "claim_b": "clm-ghost",
            "nature": "return shape",
            "resolution": "unresolved",
            "rationale": "cannot tell which source is current",
        }
    ]
    write_json(run.world_model, world)
    assert any("clm-ghost" in f.message for f in check_world_model(run))


def test_an_invariant_over_an_undeclared_collection_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["entities"][0]["invariants"] = [
        {
            "id": "inv-1",
            "statement": "s",
            "machine": {"form": "unique", "collection": "widgets", "field": "x"},
        }
    ]
    write_json(run.world_model, world)
    assert any("widgets" in f.message for f in check_world_model(run))


def test_a_miscounted_capability_cell_denominator_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["denominator"]["capability_cells"] = 5
    write_json(run.world_model, world)
    findings = check_world_model(run)
    assert any("capability_cells" in f.message and "5" in f.message for f in findings)


def test_a_miscounted_goal_denominator_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["denominator"]["goals"] = 4
    write_json(run.world_model, world)
    assert any("goals" in f.message for f in check_world_model(run))


def test_duplicate_capability_ids_are_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["capabilities"].append(dict(world["capabilities"][0]))
    world["denominator"]["capability_cells"] = 4
    write_json(run.world_model, world)
    assert any("duplicate" in f.message for f in check_world_model(run))


# -- scenarios ----------------------------------------------------------
def test_consistent_scenarios_have_no_findings(tmp_path):
    assert check_scenarios(_run(tmp_path, scenarios=True)) == []


def test_a_capability_ref_to_an_unknown_capability_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    payload = minimal_scenarios()
    payload["scenarios"][0]["capability_refs"] = [
        {"capability_id": "cap-ghost", "outcome_class_id": "oc-success"}
    ]
    write_json(run.scenarios, payload)
    assert any("cap-ghost" in f.message for f in check_scenarios(run))


def test_a_capability_ref_to_a_wrong_outcome_class_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    payload = minimal_scenarios()
    payload["scenarios"][0]["capability_refs"] = [
        {"capability_id": "cap-find-jobs", "outcome_class_id": "oc-ghost"}
    ]
    write_json(run.scenarios, payload)
    assert any("oc-ghost" in f.message for f in check_scenarios(run))


def test_a_scenario_with_an_unknown_goal_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    payload = minimal_scenarios()
    payload["scenarios"][0]["goal_id"] = "goal-ghost"
    write_json(run.scenarios, payload)
    assert any("goal-ghost" in f.message for f in check_scenarios(run))


def test_a_duplicate_pointing_at_no_such_scenario_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    payload = minimal_scenarios()
    payload["scenarios"][0]["status"] = "duplicate"
    payload["scenarios"][0]["duplicate_of"] = "scn-ghost"
    write_json(run.scenarios, payload)
    assert any("scn-ghost" in f.message for f in check_scenarios(run))


def test_a_hole_ref_naming_no_real_cell_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    payload = minimal_scenarios()
    payload["scenarios"][0]["provenance"]["hole_refs"] = ["cell:cap-ghost/oc-success"]
    write_json(run.scenarios, payload)
    assert any("cap-ghost" in f.message for f in check_scenarios(run))


def test_a_stale_denominator_version_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    write_json(run.scenarios, minimal_scenarios(denominator_version=2))
    assert any("denominator_version" in f.message for f in check_scenarios(run))


def test_duplicate_scenario_ids_are_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    payload = minimal_scenarios()
    payload["scenarios"].append(dict(payload["scenarios"][0]))
    write_json(run.scenarios, payload)
    assert any("duplicate" in f.message for f in check_scenarios(run))


# -- coverage -----------------------------------------------------------
def test_consistent_coverage_has_no_findings(tmp_path):
    assert check_coverage(_run(tmp_path, scenarios=True, coverage=True)) == []


def test_a_coverage_matrix_missing_a_real_cell_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["capability_matrix"]["cells"] = payload["capability_matrix"]["cells"][:1]
    payload["capability_matrix"]["total"] = 1
    payload["capability_matrix"]["pct"] = 1.0
    write_json(run.coverage_latest, payload)
    assert any("oc-empty" in f.message for f in check_coverage(run))


def test_a_coverage_matrix_inventing_a_cell_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["capability_matrix"]["cells"].append(
        {
            "capability_id": "cap-ghost",
            "outcome_class_id": "oc-success",
            "scenario_ids": [],
            "covered": False,
        }
    )
    payload["capability_matrix"]["total"] = 3
    write_json(run.coverage_latest, payload)
    assert any("cap-ghost" in f.message for f in check_coverage(run))


def test_inconsistent_covered_arithmetic_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["capability_matrix"]["covered"] = 2
    write_json(run.coverage_latest, payload)
    assert any("covered" in f.message for f in check_coverage(run))


def test_a_pct_that_disagrees_with_the_counts_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["capability_matrix"]["pct"] = 0.9
    write_json(run.coverage_latest, payload)
    assert any("pct" in f.message for f in check_coverage(run))


def test_a_cell_citing_an_unknown_scenario_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["capability_matrix"]["cells"][0]["scenario_ids"] = ["scn-ghost"]
    write_json(run.coverage_latest, payload)
    assert any("scn-ghost" in f.message for f in check_coverage(run))


def test_a_cell_marked_covered_with_no_scenarios_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["capability_matrix"]["cells"][1]["covered"] = True
    payload["capability_matrix"]["covered"] = 2
    payload["capability_matrix"]["pct"] = 1.0
    write_json(run.coverage_latest, payload)
    assert any("no scenarios" in f.message for f in check_coverage(run))


def test_a_blocked_by_gap_hole_naming_no_real_gap_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["holes"][0]["reason"] = "blocked_by_gap"
    payload["holes"][0]["gap_id"] = "gap-ghost"
    write_json(run.coverage_latest, payload)
    assert any("gap-ghost" in f.message for f in check_coverage(run))


# -- check_all ----------------------------------------------------------
def test_check_all_tolerates_a_run_that_has_only_reached_reconcile(tmp_path):
    assert check_all(_run(tmp_path)) == []


def test_check_all_tolerates_an_empty_run_directory(tmp_path):
    assert check_all(RunPaths(tmp_path)) == []


def test_check_all_aggregates_findings_from_every_present_artifact(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    world = minimal_world_model()
    world["denominator"]["goals"] = 9
    write_json(run.world_model, world)
    payload = minimal_scenarios()
    payload["scenarios"][0]["goal_id"] = "goal-ghost"
    write_json(run.scenarios, payload)
    messages = " ".join(f.message for f in check_all(run))
    assert "goals" in messages
    assert "goal-ghost" in messages
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_refs_planning.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'testgen.refs'`.

- [ ] **Step 3: Write the implementation**

`src/testgen/refs.py`:

```python
"""Referential integrity across run artifacts: layer 2 of three.

Layer 1 (validate.py) checks that each artifact has the right shape. This
module checks what a schema cannot see: whether ids resolve across artifact
boundaries, whether declared arithmetic matches the data it summarizes, and
(Task 8) whether every assertion is reachable in its own seed.

check_all tolerates a partially-populated run directory. It runs after every
stage, so when reconcile finishes there is no 02-scenarios.json yet and that
absence is normal. A stage that should have produced an artifact and did not
is validate.validate_stage's finding, not this module's.
"""

from __future__ import annotations

import re
from typing import Any

from testgen.artifacts import ArtifactError, read_json
from testgen.findings import Finding
from testgen.paths import RunPaths

_CELL_RE = re.compile(r"\Acell:([A-Za-z0-9][A-Za-z0-9._-]*)/([A-Za-z0-9][A-Za-z0-9._-]*)\Z")
_GOAL_RE = re.compile(r"\Agoal:([A-Za-z0-9][A-Za-z0-9._-]*)\Z")


def cell_ref(capability_id: str, outcome_class_id: str) -> str:
    """Canonical hole reference for one capability x outcome-class cell."""
    return f"cell:{capability_id}/{outcome_class_id}"


def goal_ref(goal_id: str) -> str:
    """Canonical hole reference for one goal row."""
    return f"goal:{goal_id}"


def parse_hole_ref(ref: str) -> tuple[str, tuple[str, ...]]:
    """Parse a hole reference into ("cell", (cap, oc)) or ("goal", (goal,))."""
    match = _CELL_RE.match(ref or "")
    if match:
        return "cell", (match.group(1), match.group(2))
    match = _GOAL_RE.match(ref or "")
    if match:
        return "goal", (match.group(1),)
    raise ValueError(f"malformed hole reference: {ref!r}")


def _load(path) -> Any | None:
    """Read an artifact, or None when it does not exist yet."""
    try:
        return read_json(path)
    except ArtifactError:
        return None


def _claim_ids(run: RunPaths) -> set[str]:
    """Every claim id across every 01-claims file."""
    ids: set[str] = set()
    if not run.claims_dir.is_dir():
        return ids
    for path in sorted(run.claims_dir.glob("*.json")):
        payload = _load(path)
        if isinstance(payload, dict):
            ids.update(c["id"] for c in payload.get("claims", []) if "id" in c)
    return ids


def _cells(world: dict) -> set[tuple[str, str]]:
    """Every (capability_id, outcome_class_id) pair the world model declares."""
    return {
        (cap["id"], oc["id"])
        for cap in world.get("capabilities", [])
        for oc in cap.get("outcome_classes", [])
    }


def _dupes(values: list[str]) -> list[str]:
    return sorted({v for v in values if values.count(v) > 1})


def check_world_model(run: RunPaths) -> list[Finding]:
    """Internal consistency of the world model, including the denominator."""
    world = _load(run.world_model)
    if world is None:
        return []
    out: list[Finding] = []
    path = run.world_model

    def report(pointer: str, message: str) -> None:
        out.append(Finding(path, "refs", pointer, message))

    known_claims = _claim_ids(run)
    entity_ids = {e["id"] for e in world.get("entities", [])}
    actor_ids = {a["id"] for a in world.get("actors", [])}
    collections = {e["collection"] for e in world.get("entities", [])}

    for group in ("capabilities", "entities", "actors", "goals"):
        ids = [item["id"] for item in world.get(group, [])]
        for dupe in _dupes(ids):
            report(f"/{group}", f"duplicate id {dupe!r}")
        for i, item in enumerate(world.get(group, [])):
            for j, claim_id in enumerate(item.get("claims", [])):
                if claim_id not in known_claims:
                    report(f"/{group}/{i}/claims/{j}", f"no such claim: {claim_id}")

    for i, entity in enumerate(world.get("entities", [])):
        for j, relation in enumerate(entity.get("relations", [])):
            if relation["target_entity_id"] not in entity_ids:
                report(
                    f"/entities/{i}/relations/{j}/target_entity_id",
                    f"no such entity: {relation['target_entity_id']}",
                )
        for j, invariant in enumerate(entity.get("invariants", [])):
            machine = invariant.get("machine")
            if not machine:
                continue
            for key in ("collection", "of"):
                name = machine.get(key)
                if name is not None and name not in collections:
                    report(
                        f"/entities/{i}/invariants/{j}/machine/{key}",
                        f"invariant references undeclared collection: {name}",
                    )

    for i, goal in enumerate(world.get("goals", [])):
        if goal["actor_id"] not in actor_ids:
            report(f"/goals/{i}/actor_id", f"no such actor: {goal['actor_id']}")

    for i, contradiction in enumerate(world.get("contradictions", [])):
        for side in ("claim_a", "claim_b"):
            if contradiction[side] not in known_claims:
                report(f"/contradictions/{i}/{side}", f"no such claim: {contradiction[side]}")

    denominator = world.get("denominator", {})
    actual_cells = len(_cells(world))
    if denominator.get("capability_cells") != actual_cells:
        report(
            "/denominator/capability_cells",
            f"declared capability_cells={denominator.get('capability_cells')} but the world "
            f"model declares {actual_cells} capability x outcome-class cells",
        )
    actual_goals = len(world.get("goals", []))
    if denominator.get("goals") != actual_goals:
        report(
            "/denominator/goals",
            f"declared goals={denominator.get('goals')} but the world model declares "
            f"{actual_goals}",
        )
    return out


def check_scenarios(run: RunPaths) -> list[Finding]:
    """Scenario references into the world model, and internal consistency."""
    scenarios_doc = _load(run.scenarios)
    world = _load(run.world_model)
    if scenarios_doc is None or world is None:
        return []
    out: list[Finding] = []
    path = run.scenarios

    def report(pointer: str, message: str) -> None:
        out.append(Finding(path, "refs", pointer, message))

    cells = _cells(world)
    capability_ids = {cap["id"] for cap in world.get("capabilities", [])}
    goal_ids = {g["id"] for g in world.get("goals", [])}
    actor_ids = {a["id"] for a in world.get("actors", [])}
    scenarios = scenarios_doc.get("scenarios", [])
    scenario_ids = {s["id"] for s in scenarios}

    declared_version = scenarios_doc.get("denominator_version")
    world_version = world.get("denominator", {}).get("version")
    if declared_version != world_version:
        report(
            "/denominator_version",
            f"scenarios were proposed against denominator_version={declared_version} but the "
            f"world model is at {world_version}",
        )

    for dupe in _dupes([s["id"] for s in scenarios]):
        report("/scenarios", f"duplicate scenario id {dupe!r}")

    for i, scenario in enumerate(scenarios):
        if scenario["goal_id"] not in goal_ids:
            report(f"/scenarios/{i}/goal_id", f"no such goal: {scenario['goal_id']}")
        if scenario["actor_id"] not in actor_ids:
            report(f"/scenarios/{i}/actor_id", f"no such actor: {scenario['actor_id']}")
        target = scenario.get("duplicate_of")
        if target is not None and target not in scenario_ids:
            report(f"/scenarios/{i}/duplicate_of", f"no such scenario: {target}")
        for j, ref in enumerate(scenario.get("capability_refs", [])):
            pair = (ref["capability_id"], ref["outcome_class_id"])
            if ref["capability_id"] not in capability_ids:
                report(
                    f"/scenarios/{i}/capability_refs/{j}/capability_id",
                    f"no such capability: {ref['capability_id']}",
                )
            elif pair not in cells:
                report(
                    f"/scenarios/{i}/capability_refs/{j}/outcome_class_id",
                    f"capability {ref['capability_id']} has no outcome class "
                    f"{ref['outcome_class_id']}",
                )
        for j, ref in enumerate(scenario.get("provenance", {}).get("hole_refs", [])):
            pointer = f"/scenarios/{i}/provenance/hole_refs/{j}"
            try:
                kind, parts = parse_hole_ref(ref)
            except ValueError as exc:
                report(pointer, str(exc))
                continue
            if kind == "cell" and parts not in cells:
                report(pointer, f"hole reference names no real cell: {ref}")
            if kind == "goal" and parts[0] not in goal_ids:
                report(pointer, f"hole reference names no real goal: {ref}")
    return out


def _check_matrix_arithmetic(
    report, pointer: str, covered_flags: list[bool], declared: dict
) -> None:
    """Covered/total/pct must agree with the rows they summarize."""
    total = len(covered_flags)
    covered = sum(1 for flag in covered_flags if flag)
    if declared.get("total") != total:
        report(f"{pointer}/total", f"declared total={declared.get('total')} but found {total}")
    if declared.get("covered") != covered:
        report(
            f"{pointer}/covered",
            f"declared covered={declared.get('covered')} but {covered} rows are marked covered",
        )
    expected_pct = (covered / total) if total else 0.0
    if abs(float(declared.get("pct", -1)) - expected_pct) > 1e-9:
        report(
            f"{pointer}/pct",
            f"declared pct={declared.get('pct')} but covered/total is {expected_pct}",
        )


def check_coverage(run: RunPaths) -> list[Finding]:
    """Coverage matrices against the world model and the scenario list."""
    coverage = _load(run.coverage_latest)
    world = _load(run.world_model)
    if coverage is None or world is None:
        return []
    out: list[Finding] = []
    path = run.coverage_latest

    def report(pointer: str, message: str) -> None:
        out.append(Finding(path, "refs", pointer, message))

    cells = _cells(world)
    goal_ids = {g["id"] for g in world.get("goals", [])}
    gap_ids = {g["id"] for g in world.get("gaps", [])}
    scenarios_doc = _load(run.scenarios) or {"scenarios": []}
    scenario_ids = {s["id"] for s in scenarios_doc.get("scenarios", [])}

    world_version = world.get("denominator", {}).get("version")
    if coverage.get("denominator_version") != world_version:
        report(
            "/denominator_version",
            f"coverage was computed against denominator_version="
            f"{coverage.get('denominator_version')} but the world model is at {world_version}",
        )

    matrix = coverage.get("capability_matrix", {})
    matrix_cells = matrix.get("cells", [])
    seen = {(c["capability_id"], c["outcome_class_id"]) for c in matrix_cells}
    for missing in sorted(cells - seen):
        report("/capability_matrix/cells", f"matrix omits cell {cell_ref(*missing)}")
    for invented in sorted(seen - cells):
        report("/capability_matrix/cells", f"matrix invents cell {cell_ref(*invented)}")
    for i, cell in enumerate(matrix_cells):
        for j, sid in enumerate(cell.get("scenario_ids", [])):
            if sid not in scenario_ids:
                report(
                    f"/capability_matrix/cells/{i}/scenario_ids/{j}", f"no such scenario: {sid}"
                )
        if cell.get("covered") and not cell.get("scenario_ids"):
            report(
                f"/capability_matrix/cells/{i}",
                f"cell {cell_ref(cell['capability_id'], cell['outcome_class_id'])} is marked "
                "covered but lists no scenarios",
            )
    _check_matrix_arithmetic(
        report, "/capability_matrix", [bool(c.get("covered")) for c in matrix_cells], matrix
    )

    goal_matrix = coverage.get("goal_matrix", {})
    rows = goal_matrix.get("rows", [])
    seen_goals = {r["goal_id"] for r in rows}
    for missing_goal in sorted(goal_ids - seen_goals):
        report("/goal_matrix/rows", f"matrix omits goal {missing_goal}")
    for invented_goal in sorted(seen_goals - goal_ids):
        report("/goal_matrix/rows", f"matrix invents goal {invented_goal}")
    for i, row in enumerate(rows):
        for j, sid in enumerate(row.get("scenario_ids", [])):
            if sid not in scenario_ids:
                report(f"/goal_matrix/rows/{i}/scenario_ids/{j}", f"no such scenario: {sid}")
    _check_matrix_arithmetic(
        report, "/goal_matrix", [bool(r.get("covered")) for r in rows], goal_matrix
    )

    for i, hole in enumerate(coverage.get("holes", [])):
        try:
            kind, parts = parse_hole_ref(hole["ref"])
        except ValueError as exc:
            report(f"/holes/{i}/ref", str(exc))
            continue
        if kind == "cell" and parts not in cells:
            report(f"/holes/{i}/ref", f"hole names no real cell: {hole['ref']}")
        if kind == "goal" and parts[0] not in goal_ids:
            report(f"/holes/{i}/ref", f"hole names no real goal: {hole['ref']}")
        gap_id = hole.get("gap_id")
        if gap_id is not None and gap_id not in gap_ids:
            report(f"/holes/{i}/gap_id", f"no such gap: {gap_id}")
    return out


def check_all(run: RunPaths) -> list[Finding]:
    """Every layer-2 check that the run directory currently has inputs for."""
    findings: list[Finding] = []
    findings.extend(check_world_model(run))
    findings.extend(check_scenarios(run))
    findings.extend(check_coverage(run))
    return findings
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_refs_planning.py -q`
Expected: PASS, 31 tests.

- [ ] **Step 5: Run the whole suite and the lint gate**

Run: `make test && make check`
Expected: all tests pass, no lint findings.

- [ ] **Step 6: Commit**

```bash
git add src/testgen/refs.py tests/unit/test_refs_planning.py
git commit -S -s -m "feat: Add referential integrity for world model, scenarios, coverage

Checks what JSON Schema cannot see: whether ids resolve across artifact
boundaries and whether declared arithmetic matches the data it summarizes.

The denominator check is the highest-value assertion here. A reconcile stage
that miscounts capability cells or goals corrupts every coverage percentage
downstream, and nothing else in the pipeline would notice -- the numbers would
simply be confidently wrong. The same applies to a matrix that omits or
invents a cell, or marks one covered while listing no scenarios.

check_all tolerates a partially-populated run directory, since it runs after
every stage and a not-yet-reached artifact is normal. An artifact that should
exist and does not is validate_stage's finding, not this module's.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 8: Seed conformance, the reachability gate, and verdict pairing

Layer 2, second half — and the most important code in this plan. This is the gate that makes the design's central invariant structural rather than aspirational: **a gold label may only assert values present in its own scenario's seed.**

Three things happen here.

**Seed conformance.** A seed's collections must be exactly the collections the world model's entities declare, every record must carry every declared field with the declared type, and no record may carry an undeclared field. The last rule matters more than it looks: a simulation backend drops or recomputes fields it does not know about, so an invented field is a value the gold label may be relying on that will not exist at run time.

**The reachability gate.** Every data assertion's `seed_pointer` is resolved against *that scenario's own seed and nothing else* — cross-contamination between scenarios is impossible by construction, not by convention. The check inverts by kind: `answer_contains` and `value_equals` require the pointer to resolve and the value to be present; `answer_excludes` requires it to resolve to nothing, which is what makes a `log-does-not-say` test verifiable instead of merely plausible.

**Verdict pairing.** Beyond one-verdict-per-instance, two self-contradiction checks: an `accept` that simultaneously reports `derivable_without_guessing: false` or `uniquely_determined: false` is incoherent, and a `minimum_tool_calls_found` below the scenario's claimed `hop_depth` must carry the `difficulty_overstated` flag.

**Files:**
- Modify: `src/testgen/refs.py` (add the pointer resolver, `check_instances`, `check_verdicts`; extend `check_all`)
- Modify: `tests/builders.py` (`minimal_world_model` must declare the `controller` field its seed uses)
- Test: `tests/unit/test_refs_instance.py`

**Interfaces:**
- Consumes: everything Task 7 produced, plus `invariants.evaluate`, `invariants.InvariantForm`.
- Produces: `refs.UNSET` (sentinel returned when a pointer does not resolve); `refs.resolve_pointer(document: Any, pointer: str) -> Any`; `refs.check_instances(run: RunPaths) -> list[Finding]`; `refs.check_verdicts(run: RunPaths) -> list[Finding]`; `check_all` now includes both.

- [ ] **Step 1: Make the world-model builder declare the field its seed uses**

In `tests/builders.py`, `minimal_world_model`'s `ent-job` entity declares only `job_id` and `status`, while `minimal_seed` writes a `controller` field. Under the undeclared-field rule that is now a finding, so the builder must declare it. Replace the entity's `fields` list:

```python
                "fields": [
                    {"name": "job_id", "type": "integer"},
                    {"name": "status", "type": "string"},
                    {"name": "controller", "type": "string"},
                ],
```

- [ ] **Step 2: Write the failing tests**

`tests/unit/test_refs_instance.py`:

```python
import pytest

from testgen.artifacts import write_json
from testgen.paths import RunPaths
from testgen.refs import UNSET, check_all, check_instances, check_verdicts, resolve_pointer
from tests.builders import (
    minimal_claims,
    minimal_expected,
    minimal_scenarios,
    minimal_seed,
    minimal_verdict,
    minimal_world_model,
)


def _run(tmp_path, *, seed=None, expected=None, verdict=None, world=None, sid="scn-001"):
    run = RunPaths(tmp_path)
    write_json(run.claims("aap2-api"), minimal_claims())
    write_json(run.world_model, world if world is not None else minimal_world_model())
    write_json(run.scenarios, minimal_scenarios())
    write_json(run.seed(sid), seed if seed is not None else minimal_seed())
    write_json(run.expected(sid), expected if expected is not None else minimal_expected())
    if verdict is not None:
        write_json(run.verdict(sid), verdict)
    return run


# -- pointer resolver ---------------------------------------------------
def test_pointer_resolves_nested_objects_and_arrays():
    doc = {"collections": {"jobs": [{"job_id": 7}]}}
    assert resolve_pointer(doc, "/collections/jobs/0/job_id") == 7


def test_empty_pointer_is_the_whole_document():
    doc = {"a": 1}
    assert resolve_pointer(doc, "") == doc


def test_pointer_unescapes_rfc6901_sequences():
    assert resolve_pointer({"a/b": {"c~d": 1}}, "/a~1b/c~0d") == 1


@pytest.mark.parametrize(
    "pointer",
    ["/collections/absent", "/collections/jobs/9", "/collections/jobs/x", "/collections/jobs/0/x"],
)
def test_unresolvable_pointers_return_unset(pointer):
    doc = {"collections": {"jobs": [{"job_id": 7}]}}
    assert resolve_pointer(doc, pointer) is UNSET


def test_pointer_without_a_leading_slash_raises():
    with pytest.raises(ValueError):
        resolve_pointer({"a": 1}, "a")


# -- seed conformance ---------------------------------------------------
def test_a_conformant_instance_has_no_findings(tmp_path):
    assert check_instances(_run(tmp_path)) == []


def test_an_instance_for_no_such_scenario_is_reported(tmp_path):
    run = _run(tmp_path, sid="scn-ghost")
    assert any("scn-ghost" in f.message for f in check_instances(run))


def test_an_instance_for_a_scenario_marked_duplicate_is_reported(tmp_path):
    run = _run(tmp_path)
    payload = minimal_scenarios()
    payload["scenarios"][0]["status"] = "duplicate"
    payload["scenarios"][0]["duplicate_of"] = "scn-000"
    write_json(run.scenarios, payload)
    assert any("duplicate" in f.message for f in check_instances(run))


def test_a_seed_collection_the_world_model_does_not_declare_is_reported(tmp_path):
    seed = minimal_seed(collections={"widgets": [{"x": 1}]})
    assert any("widgets" in f.message for f in check_instances(_run(tmp_path, seed=seed)))


def test_a_record_missing_a_declared_field_is_reported(tmp_path):
    seed = minimal_seed(collections={"jobs": [{"job_id": 1, "status": "failed"}]})
    findings = check_instances(_run(tmp_path, seed=seed))
    assert any("controller" in f.message for f in findings)


def test_a_record_with_an_undeclared_field_is_reported(tmp_path):
    seed = minimal_seed(
        collections={
            "jobs": [{"job_id": 1, "status": "failed", "controller": "prod0", "invented": 1}]
        }
    )
    findings = check_instances(_run(tmp_path, seed=seed))
    assert any("invented" in f.message for f in findings)


def test_a_field_of_the_wrong_declared_type_is_reported(tmp_path):
    seed = minimal_seed(
        collections={"jobs": [{"job_id": "one", "status": "failed", "controller": "prod0"}]}
    )
    findings = check_instances(_run(tmp_path, seed=seed))
    assert any("job_id" in f.message and "integer" in f.message for f in findings)


def test_a_boolean_does_not_satisfy_an_integer_field(tmp_path):
    seed = minimal_seed(
        collections={"jobs": [{"job_id": True, "status": "failed", "controller": "prod0"}]}
    )
    assert any("job_id" in f.message for f in check_instances(_run(tmp_path, seed=seed)))


def test_a_violated_machine_invariant_is_reported_at_the_invariant_layer(tmp_path):
    world = minimal_world_model()
    world["entities"][0]["invariants"] = [
        {
            "id": "inv-unique-job",
            "statement": "job_id is unique",
            "machine": {"form": "unique", "collection": "jobs", "field": "job_id"},
        }
    ]
    seed = minimal_seed(
        collections={
            "jobs": [
                {"job_id": 1, "status": "failed", "controller": "prod0"},
                {"job_id": 1, "status": "failed", "controller": "prod0"},
            ]
        }
    )
    findings = check_instances(_run(tmp_path, seed=seed, world=world))
    assert any(f.layer == "invariant" and "duplicate" in f.message for f in findings)


# -- the reachability gate ----------------------------------------------
def test_an_unresolvable_seed_pointer_is_reported(tmp_path):
    expected = minimal_expected()
    expected["assertions"][0]["grounded_in"]["seed_pointer"] = "/collections/jobs/9/job_id"
    findings = check_instances(_run(tmp_path, expected=expected))
    assert any("does not resolve" in f.message for f in findings)


def test_an_asserted_value_absent_from_the_seed_is_reported(tmp_path):
    expected = minimal_expected()
    expected["assertions"][0]["value"] = "99999"
    findings = check_instances(_run(tmp_path, expected=expected))
    assert any("not present" in f.message for f in findings)


def test_value_equals_requires_an_exact_match(tmp_path):
    expected = minimal_expected()
    expected["assertions"][0] = {
        "kind": "value_equals",
        "target": "job_id",
        "value": "9042",
        "rationale": "prefix is not equality",
        "grounded_in": {"seed_pointer": "/collections/jobs/0/job_id"},
    }
    findings = check_instances(_run(tmp_path, expected=expected))
    assert any("does not equal" in f.message for f in findings)


def test_answer_excludes_holds_when_the_pointer_resolves_to_nothing(tmp_path):
    expected = minimal_expected()
    expected["assertions"] = [
        {
            "kind": "answer_excludes",
            "target": "answer",
            "value": "root cause",
            "rationale": "the seed carries no error_msg, so no root cause is derivable",
            "grounded_in": {"seed_pointer": "/collections/jobs/0/error_msg"},
        }
    ]
    assert check_instances(_run(tmp_path, expected=expected)) == []


def test_answer_excludes_is_reported_when_the_data_is_actually_there(tmp_path):
    world = minimal_world_model()
    world["entities"][0]["fields"].append({"name": "error_msg", "type": "string"})
    seed = minimal_seed(
        collections={
            "jobs": [
                {
                    "job_id": 90420,
                    "status": "failed",
                    "controller": "prod0",
                    "error_msg": "datastream file not found",
                }
            ]
        }
    )
    expected = minimal_expected()
    expected["assertions"] = [
        {
            "kind": "answer_excludes",
            "target": "answer",
            "value": "root cause",
            "rationale": "claims the data is silent",
            "grounded_in": {"seed_pointer": "/collections/jobs/0/error_msg"},
        }
    ]
    findings = check_instances(_run(tmp_path, seed=seed, expected=expected, world=world))
    assert any("resolves to a value" in f.message for f in findings)


def test_a_trajectory_assertion_naming_an_unknown_capability_is_reported(tmp_path):
    expected = minimal_expected()
    expected["assertions"][1]["capability_id"] = "cap-ghost"
    assert any("cap-ghost" in f.message for f in check_instances(_run(tmp_path, expected=expected)))


def test_a_trajectory_operation_naming_an_unknown_capability_is_reported(tmp_path):
    expected = minimal_expected()
    expected["trajectory"]["operations"][0]["capability_id"] = "cap-ghost"
    assert any("cap-ghost" in f.message for f in check_instances(_run(tmp_path, expected=expected)))


def test_an_expected_document_naming_a_different_scenario_is_reported(tmp_path):
    expected = minimal_expected(scenario_id="scn-002")
    findings = check_instances(_run(tmp_path, expected=expected))
    assert any("scn-002" in f.message for f in findings)


def test_a_pointer_cannot_reach_another_scenarios_seed(tmp_path):
    """Cross-contamination is impossible by construction, not by convention."""
    run = _run(tmp_path)
    write_json(run.seed("scn-002"), minimal_seed(collections={"jobs": []}))
    write_json(run.expected("scn-002"), minimal_expected(scenario_id="scn-002"))
    payload = minimal_scenarios()
    second = dict(payload["scenarios"][0])
    second["id"] = "scn-002"
    payload["scenarios"].append(second)
    write_json(run.scenarios, payload)
    findings = check_instances(run)
    assert any("scn-002" in str(f.artifact) and "does not resolve" in f.message for f in findings)


# -- verdicts -----------------------------------------------------------
def test_a_matching_verdict_has_no_findings(tmp_path):
    assert check_verdicts(_run(tmp_path, verdict=minimal_verdict())) == []


def test_an_instance_with_no_verdict_is_reported(tmp_path):
    assert any("no verdict" in f.message for f in check_verdicts(_run(tmp_path)))


def test_a_verdict_naming_a_different_scenario_is_reported(tmp_path):
    run = _run(tmp_path, verdict=minimal_verdict(scenario_id="scn-999"))
    assert any("scn-999" in f.message for f in check_verdicts(run))


def test_an_accept_that_admits_the_test_is_not_derivable_is_reported(tmp_path):
    verdict = minimal_verdict(derivable_without_guessing=False)
    findings = check_verdicts(_run(tmp_path, verdict=verdict))
    assert any("derivable" in f.message for f in findings)


def test_an_accept_that_admits_the_test_is_ambiguous_is_reported(tmp_path):
    verdict = minimal_verdict(
        uniquely_determined=False,
        alternative_answers=[{"answer": "other", "world_consistent_reason": "also fits"}],
    )
    findings = check_verdicts(_run(tmp_path, verdict=verdict))
    assert any("uniquely determined" in f.message for f in findings)


def test_an_easier_than_claimed_test_must_carry_the_flag(tmp_path):
    verdict = minimal_verdict(minimum_tool_calls_found=1)
    findings = check_verdicts(_run(tmp_path, verdict=verdict))
    assert any("difficulty_overstated" in f.message for f in findings)


def test_an_easier_than_claimed_test_with_the_flag_is_accepted(tmp_path):
    verdict = minimal_verdict(minimum_tool_calls_found=1, flags=["difficulty_overstated"])
    assert check_verdicts(_run(tmp_path, verdict=verdict)) == []


# -- aggregation --------------------------------------------------------
def test_check_all_now_includes_instance_and_verdict_findings(tmp_path):
    run = _run(tmp_path)
    assert any("no verdict" in f.message for f in check_all(run))
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_refs_instance.py -q`
Expected: FAIL — `ImportError: cannot import name 'UNSET' from 'testgen.refs'`.

- [ ] **Step 4: Add the pointer resolver and type table to refs.py**

Add these imports at the top of `src/testgen/refs.py`, alongside the existing ones:

```python
from testgen.invariants import InvariantForm
from testgen.invariants import evaluate as evaluate_invariant
```

Then append to `src/testgen/refs.py`, before `check_all`:

```python
class _Unset:
    def __repr__(self) -> str:
        return "<unset>"


UNSET = _Unset()

# Declared field type -> the predicate a seed value must satisfy. `integer`
# excludes bool deliberately: bool is an int subclass in Python, and a seed
# writing `true` where an id belongs is a real defect, not a wide integer.
_TYPE_CHECKS: dict[str, Any] = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}

_DATA_KINDS = ("answer_contains", "answer_excludes", "value_equals")
_TRAJECTORY_KINDS = ("tool_called", "tool_not_called")


def resolve_pointer(document: Any, pointer: str) -> Any:
    """Resolve an RFC 6901 JSON Pointer, returning UNSET if it does not exist.

    Written here rather than pulled from a library because the whole surface
    is fifteen lines and the reachability gate depends on its exact
    does-not-resolve semantics.
    """
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError(f"not a JSON pointer: {pointer!r}")
    current = document
    for raw in pointer.split("/")[1:]:
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                return UNSET
            current = current[token]
        elif isinstance(current, list):
            if not token.isdigit() or int(token) >= len(current):
                return UNSET
            current = current[int(token)]
        else:
            return UNSET
    return current


def _is_empty(value: Any) -> bool:
    return value is UNSET or value is None or value in ("", [], {})


def _check_seed_conformance(report, world: dict, seed: dict) -> None:
    """Seed collections, fields, and types against the world model's entities."""
    entities = {e["collection"]: e for e in world.get("entities", [])}
    collections = seed.get("collections", {})
    for name in sorted(set(collections) - set(entities)):
        report(
            f"/collections/{name}",
            f"seed declares collection {name!r}, which no world-model entity declares",
        )
    for name, records in sorted(collections.items()):
        entity = entities.get(name)
        if entity is None:
            continue
        declared = {f["name"]: f["type"] for f in entity.get("fields", [])}
        for i, record in enumerate(records):
            pointer = f"/collections/{name}/{i}"
            for missing in sorted(set(declared) - set(record)):
                report(pointer, f"record is missing declared field {missing!r}")
            for extra in sorted(set(record) - set(declared)):
                report(
                    pointer,
                    f"record carries undeclared field {extra!r}; a simulation backend will "
                    "drop or recompute it, so a label relying on it would break at run time",
                )
            for field, type_name in sorted(declared.items()):
                if field not in record:
                    continue
                check = _TYPE_CHECKS.get(type_name)
                if check is not None and not check(record[field]):
                    report(
                        f"{pointer}/{field}",
                        f"field {field!r} is declared {type_name} but holds "
                        f"{record[field]!r}",
                    )


def _check_invariants(report_invariant, world: dict, seed: dict) -> None:
    collections = seed.get("collections", {})
    for entity in world.get("entities", []):
        for invariant in entity.get("invariants", []):
            machine = invariant.get("machine")
            if not machine:
                continue
            try:
                violations = evaluate_invariant(machine, collections)
            except InvariantForm as exc:
                report_invariant("", f"invariant {invariant['id']}: {exc}")
                continue
            for violation in violations:
                report_invariant("", f"invariant {invariant['id']}: {violation}")


def _check_reachability(report, world: dict, seed: dict, expected: dict) -> None:
    """Every assertion is grounded in this scenario's own seed.

    Resolution happens against `seed` and nothing else, so an assertion can
    never reach another scenario's world.
    """
    capability_ids = {cap["id"] for cap in world.get("capabilities", [])}
    for i, assertion in enumerate(expected.get("assertions", [])):
        kind = assertion["kind"]
        pointer = f"/assertions/{i}"
        if kind in _TRAJECTORY_KINDS:
            if assertion.get("capability_id") not in capability_ids:
                report(
                    f"{pointer}/capability_id",
                    f"no such capability: {assertion.get('capability_id')}",
                )
            continue
        if kind not in _DATA_KINDS:
            continue
        seed_pointer = assertion["grounded_in"]["seed_pointer"]
        resolved = resolve_pointer(seed, seed_pointer)
        if kind == "answer_excludes":
            if not _is_empty(resolved):
                report(
                    f"{pointer}/grounded_in/seed_pointer",
                    f"answer_excludes is grounded at {seed_pointer}, which resolves to a value "
                    f"({resolved!r}); the seed does contain what the assertion claims it lacks",
                )
            continue
        if resolved is UNSET:
            report(
                f"{pointer}/grounded_in/seed_pointer",
                f"{seed_pointer} does not resolve in this scenario's seed",
            )
            continue
        rendered = str(resolved)
        value = assertion["value"]
        if kind == "answer_contains" and value not in rendered:
            report(
                f"{pointer}/value",
                f"asserted value {value!r} is not present at {seed_pointer} (found {resolved!r})",
            )
        if kind == "value_equals" and rendered != value:
            report(
                f"{pointer}/value",
                f"asserted value {value!r} does not equal the seed value {resolved!r} at "
                f"{seed_pointer}",
            )

    for i, operation in enumerate(expected.get("trajectory", {}).get("operations", [])):
        if operation["capability_id"] not in capability_ids:
            report(
                f"/trajectory/operations/{i}/capability_id",
                f"no such capability: {operation['capability_id']}",
            )


def check_instances(run: RunPaths) -> list[Finding]:
    """Seed conformance, machine invariants, and the reachability gate."""
    world = _load(run.world_model)
    if world is None:
        return []
    scenarios_doc = _load(run.scenarios) or {"scenarios": []}
    by_id = {s["id"]: s for s in scenarios_doc.get("scenarios", [])}
    out: list[Finding] = []

    for sid in run.scenario_ids_with_instances():
        scenario = by_id.get(sid)
        if scenario is None:
            out.append(
                Finding(run.instance_dir(sid), "refs", "", f"no scenario named {sid} was proposed")
            )
            continue
        if scenario.get("status") == "duplicate":
            out.append(
                Finding(
                    run.instance_dir(sid),
                    "refs",
                    "",
                    f"scenario {sid} is marked duplicate and should not have been instantiated",
                )
            )

        seed = _load(run.seed(sid))
        expected = _load(run.expected(sid))
        if seed is None or expected is None:
            continue

        seed_path, expected_path = run.seed(sid), run.expected(sid)
        out_seed = lambda p, m: out.append(Finding(seed_path, "refs", p, m))  # noqa: E731
        out_inv = lambda p, m: out.append(Finding(seed_path, "invariant", p, m))  # noqa: E731
        out_exp = lambda p, m: out.append(Finding(expected_path, "refs", p, m))  # noqa: E731

        _check_seed_conformance(out_seed, world, seed)
        _check_invariants(out_inv, world, seed)
        if expected.get("scenario_id") != sid:
            out_exp(
                "/scenario_id",
                f"expected.json names scenario {expected.get('scenario_id')} but lives in the "
                f"instance directory for {sid}",
            )
        _check_reachability(out_exp, world, seed, expected)
    return out


def check_verdicts(run: RunPaths) -> list[Finding]:
    """One coherent verdict per instantiated scenario."""
    scenarios_doc = _load(run.scenarios) or {"scenarios": []}
    hop_depths = {s["id"]: s.get("hop_depth") for s in scenarios_doc.get("scenarios", [])}
    instantiated = run.scenario_ids_with_instances()
    out: list[Finding] = []

    for sid in instantiated:
        path = run.verdict(sid)
        verdict = _load(path)
        if verdict is None:
            out.append(
                Finding(run.instance_dir(sid), "refs", "", f"instance {sid} has no verdict")
            )
            continue

        def report(pointer: str, message: str, path=path) -> None:
            out.append(Finding(path, "refs", pointer, message))

        if verdict.get("scenario_id") != sid:
            report(
                "/scenario_id",
                f"verdict names scenario {verdict.get('scenario_id')} but is filed under {sid}",
            )
        if verdict.get("verdict") == "accept":
            if not verdict.get("derivable_without_guessing", True):
                report(
                    "/verdict",
                    "verdict is accept but the test is reported as not derivable without "
                    "guessing; those cannot both be true",
                )
            if not verdict.get("uniquely_determined", True):
                report(
                    "/verdict",
                    "verdict is accept but the answer is reported as not uniquely determined; "
                    "those cannot both be true",
                )
        claimed = hop_depths.get(sid)
        found = verdict.get("minimum_tool_calls_found")
        if isinstance(claimed, int) and isinstance(found, int) and found < claimed:
            if "difficulty_overstated" not in verdict.get("flags", []):
                report(
                    "/minimum_tool_calls_found",
                    f"adversary solved this in {found} call(s) but the scenario claims hop_depth "
                    f"{claimed}; the difficulty_overstated flag is required",
                )

    if run.verdicts_dir.is_dir():
        known = set(instantiated)
        for path in sorted(run.verdicts_dir.glob("*.json")):
            if path.stem not in known:
                out.append(
                    Finding(path, "refs", "", f"verdict for {path.stem}, which has no instance")
                )
    return out
```

- [ ] **Step 5: Extend check_all**

Replace the body of `check_all` in `src/testgen/refs.py`:

```python
def check_all(run: RunPaths) -> list[Finding]:
    """Every layer-2 check that the run directory currently has inputs for."""
    findings: list[Finding] = []
    findings.extend(check_world_model(run))
    findings.extend(check_scenarios(run))
    findings.extend(check_coverage(run))
    findings.extend(check_instances(run))
    findings.extend(check_verdicts(run))
    return findings
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_refs_instance.py -q`
Expected: PASS, 29 tests.

- [ ] **Step 7: Run the whole suite and the lint gate**

Both `test_refs_planning.py` and `test_refs_instance.py` share `tests/builders.py`, and Step 1 changed a builder. Confirm the earlier tests still pass.

Run: `make test && make check`
Expected: all tests pass, no lint findings.

- [ ] **Step 8: Commit**

```bash
git add src/testgen/refs.py tests/builders.py tests/unit/test_refs_instance.py
git commit -S -s -m "feat: Add seed conformance, the reachability gate, and verdict pairing

This is the gate that makes the design's central invariant structural: a gold
label may only assert values present in its own scenario's seed. Pointers
resolve against that scenario's seed and nothing else, so cross-contamination
between scenarios is impossible by construction rather than by convention.

The check inverts by assertion kind. answer_contains and value_equals require
the pointer to resolve with the value present; answer_excludes requires it to
resolve to nothing, which is what makes a 'the log does not say' test
verifiable instead of merely plausible.

Undeclared seed fields are a finding because a simulation backend drops or
recomputes fields it does not know about, so an invented field is a value the
gold label may depend on that will not exist at run time.

Verdict pairing catches two self-contradictions an LLM produces readily: an
accept that simultaneously reports the test as not derivable or not uniquely
determined, and a solve cheaper than the claimed hop_depth without the
difficulty_overstated flag.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 9: Input intake

Stage 0. Registers the input artifacts, hashes them, classifies them, and mints the run id and manifest. This is where the global constraint "run ids and timestamps are minted by code, never by skills" is actually enforced.

`now` is an injectable parameter rather than a `datetime.now()` call buried inside, so the tests can assert an exact run id.

**Files:**
- Create: `src/testgen/intake.py`
- Test: `tests/unit/test_intake.py`

**Interfaces:**
- Consumes: `paths.RunPaths`, `paths.safe_segment`; `artifacts.write_json`, `artifacts.read_json`.
- Produces: `intake.slug(value: str) -> str`; `intake.classify(path: Path) -> str` returning one of the manifest's `kind` values; `intake.sha256_of(path: Path) -> str`; `intake.intake(*, inputs: list[Path], runs_dir: Path, target_name: str, target_interface: str, max_rounds: int, max_scenarios: int, now: datetime | None = None) -> RunPaths`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_intake.py`:

```python
import json
from datetime import UTC, datetime

import pytest

from testgen.artifacts import read_json
from testgen.intake import classify, intake, sha256_of, slug
from testgen.validate import validate_artifact

NOW = datetime(2026, 8, 6, 12, 30, 5, tzinfo=UTC)


def _write(tmp_path, name, payload):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("api.json", "api-json"),
        ("parsec-aap2/api.json", "parsec-aap2-api-json"),
        ("Weird Name!!.MD", "weird-name-md"),
        ("---leading", "leading"),
        ("", "input"),
    ],
)
def test_slug_produces_safe_path_segments(raw, expected):
    from testgen.paths import safe_segment

    result = slug(raw)
    assert result == expected
    assert safe_segment(result) == result


def test_classify_recognises_an_mcp_tool_schema(tmp_path):
    assert classify(_write(tmp_path, "api.json", {"tools": []})) == "mcp_tool_schema"


def test_classify_recognises_an_entity_schema(tmp_path):
    assert classify(_write(tmp_path, "schema.json", {"jobs": {}})) == "entity_schema"


def test_classify_recognises_openapi_by_content(tmp_path):
    assert classify(_write(tmp_path, "spec.json", {"openapi": "3.1.0"})) == "openapi"


def test_classify_recognises_a_trace_by_content(tmp_path):
    assert classify(_write(tmp_path, "run1.json", {"trace_id": "tr-1", "spans": []})) == "trace"


def test_classify_recognises_a_design_document(tmp_path):
    assert classify(_write(tmp_path, "notes.md", "# Design")) == "design_doc"


def test_classify_recognises_source_code(tmp_path):
    assert classify(_write(tmp_path, "agent.py", "def run(): ...")) == "source_code"


def test_classify_falls_back_to_other(tmp_path):
    assert classify(_write(tmp_path, "blob.bin", "\x00\x01")) == "other"


def test_sha256_matches_the_known_digest_of_empty_input(tmp_path):
    path = _write(tmp_path, "empty", "")
    assert sha256_of(path) == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_intake_mints_a_run_id_from_the_supplied_timestamp(tmp_path):
    run = intake(
        inputs=[_write(tmp_path / "src", "api.json", {"tools": []})],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
        now=NOW,
    )
    assert run.root.name == "run-20260806-123005"


def test_intake_writes_a_schema_valid_manifest(tmp_path):
    run = intake(
        inputs=[_write(tmp_path / "src", "api.json", {"tools": []})],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
        now=NOW,
    )
    assert validate_artifact(run.manifest, "manifest") == []


def test_intake_copies_inputs_and_records_hash_kind_and_size(tmp_path):
    source = _write(tmp_path / "src", "api.json", {"tools": []})
    run = intake(
        inputs=[source],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
        now=NOW,
    )
    entry = read_json(run.manifest)["inputs"][0]
    assert entry["artifact_id"] == "api-json"
    assert entry["kind"] == "mcp_tool_schema"
    assert entry["sha256"] == sha256_of(source)
    assert entry["bytes"] == source.stat().st_size
    copied = run.inputs_dir / "api-json.json"
    assert copied.read_bytes() == source.read_bytes()


def test_intake_disambiguates_colliding_artifact_ids(tmp_path):
    first = _write(tmp_path / "a", "api.json", {"tools": [1]})
    second = _write(tmp_path / "b", "api.json", {"tools": [2]})
    run = intake(
        inputs=[first, second],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
        now=NOW,
    )
    ids = [e["artifact_id"] for e in read_json(run.manifest)["inputs"]]
    assert ids == ["api-json", "api-json-2"]


def test_intake_records_the_limits_the_orchestrator_will_enforce(tmp_path):
    run = intake(
        inputs=[_write(tmp_path / "src", "api.json", {"tools": []})],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
        now=NOW,
    )
    assert read_json(run.manifest)["limits"] == {"max_rounds": 2, "max_scenarios": 8}


def test_intake_refuses_an_empty_input_set(tmp_path):
    with pytest.raises(ValueError, match="at least one input"):
        intake(
            inputs=[],
            runs_dir=tmp_path / "runs",
            target_name="aap2",
            target_interface="mcp",
            max_rounds=2,
            max_scenarios=8,
            now=NOW,
        )


def test_intake_refuses_a_missing_input(tmp_path):
    with pytest.raises(FileNotFoundError):
        intake(
            inputs=[tmp_path / "absent.json"],
            runs_dir=tmp_path / "runs",
            target_name="aap2",
            target_interface="mcp",
            max_rounds=2,
            max_scenarios=8,
            now=NOW,
        )


def test_intake_refuses_to_overwrite_an_existing_run(tmp_path):
    kwargs = dict(
        inputs=[_write(tmp_path / "src", "api.json", {"tools": []})],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
        now=NOW,
    )
    intake(**kwargs)
    with pytest.raises(FileExistsError):
        intake(**kwargs)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_intake.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'testgen.intake'`.

- [ ] **Step 3: Write the implementation**

`src/testgen/intake.py`:

```python
"""Stage 0: register the input artifacts and mint the run.

This module is the reason run ids and timestamps never come from a skill. A
model-invented timestamp would make two otherwise-identical runs diff, and a
model-invented run id could escape the runs directory.

Classification is a heuristic and is meant to be. It seeds the extract
stage's expectations; the extract skill reads the artifact itself and is free
to disagree in its claims.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

from testgen.artifacts import write_json
from testgen.paths import RunPaths, safe_segment

_SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".go", ".rs", ".java", ".rb"}
_DOC_SUFFIXES = {".md", ".rst", ".txt", ".adoc"}


def slug(value: str) -> str:
    """Turn an arbitrary path or name into a safe artifact id."""
    lowered = re.sub(r"[^A-Za-z0-9]+", "-", str(value).lower())
    trimmed = lowered.strip("-")
    trimmed = re.sub(r"^[^A-Za-z0-9]+", "", trimmed)[:96]
    return safe_segment(trimmed) if trimmed else "input"


def sha256_of(path: Path) -> str:
    """Hex digest of a file's bytes, streamed so a large trace is fine."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_or_none(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def classify(path: Path) -> str:
    """Best-effort artifact kind, from the filename and then the content."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in _DOC_SUFFIXES:
        return "design_doc"
    if suffix in _SOURCE_SUFFIXES:
        return "source_code"

    payload = _json_or_none(path)
    if isinstance(payload, dict):
        if "openapi" in payload or "swagger" in payload:
            return "openapi"
        if "spans" in payload or "trace_id" in payload:
            return "trace"
        if path.name == "api.json" or "tools" in payload:
            return "mcp_tool_schema"
        if path.name == "schema.json":
            return "entity_schema"
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        if "spans" in payload[0] or "trace_id" in payload[0]:
            return "trace"
    return "other"


def _unique_ids(inputs: list[Path]) -> list[str]:
    """Artifact ids for the inputs, suffixed on collision, order preserved."""
    used: dict[str, int] = {}
    ids: list[str] = []
    for path in inputs:
        base = slug(path.name)
        count = used.get(base, 0) + 1
        used[base] = count
        ids.append(base if count == 1 else f"{base}-{count}")
    return ids


def intake(
    *,
    inputs: list[Path],
    runs_dir: Path,
    target_name: str,
    target_interface: str,
    max_rounds: int,
    max_scenarios: int,
    now: datetime | None = None,
) -> RunPaths:
    """Create a run directory, register the inputs, and write the manifest.

    Returns the RunPaths for the new run. Refuses to touch an existing run
    directory: a re-run gets a new id so the old artifacts stay diffable.
    """
    if not inputs:
        raise ValueError("intake needs at least one input artifact")
    inputs = [Path(p) for p in inputs]
    for path in inputs:
        if not path.is_file():
            raise FileNotFoundError(f"input artifact does not exist: {path}")

    stamp = (now or datetime.now(UTC)).astimezone(UTC)
    run = RunPaths(Path(runs_dir) / f"run-{stamp:%Y%m%d-%H%M%S}")
    if run.root.exists():
        raise FileExistsError(f"run directory already exists: {run.root}")

    run.inputs_dir.mkdir(parents=True)
    entries = []
    for path, artifact_id in zip(inputs, _unique_ids(inputs), strict=True):
        destination = run.inputs_dir / f"{artifact_id}{path.suffix.lower()}"
        shutil.copy2(path, destination)
        entries.append(
            {
                "artifact_id": artifact_id,
                "source_path": str(path),
                "sha256": sha256_of(path),
                "kind": classify(path),
                "bytes": path.stat().st_size,
            }
        )

    write_json(
        run.manifest,
        {
            "schema_version": "0.1",
            "run_id": run.root.name,
            "created_utc": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "target": {"name": target_name, "interface": target_interface},
            "inputs": entries,
            "stages": {},
            "limits": {"max_rounds": max_rounds, "max_scenarios": max_scenarios},
        },
    )
    return run
```

Note on `_unique_ids`: ids come from the filename alone, not the parent directory, which is why two `api.json` inputs from different directories collide and get suffixed rather than being distinguished automatically. That is the intended behaviour — an operator feeding two same-named files should see `api-json` and `api-json-2` and can rename the sources if the distinction matters.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_intake.py -q`
Expected: PASS, 20 tests.

- [ ] **Step 5: Run the whole suite and the lint gate**

Run: `make test && make check`
Expected: all tests pass, no lint findings.

- [ ] **Step 6: Commit**

```bash
git add src/testgen/intake.py tests/unit/test_intake.py
git commit -S -s -m "feat: Add input intake

Mints the run id and timestamp in code, which is the point: a model-invented
timestamp makes two otherwise-identical runs diff, and a model-invented run id
could escape the runs directory. `now` is injected so tests can assert an
exact id.

Intake refuses to reuse an existing run directory. A re-run gets a fresh id so
the previous artifacts stay on disk and diffable, which is what the
reproducibility criterion needs.

Classification is deliberately heuristic. It seeds the extract stage's
expectations; that stage reads the artifact itself and may disagree in its
claims.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 10: Dedupe candidate proposal

The deterministic half of stage 3's dedupe. This proposes *candidate* pairs; it never decides. Recognising that "find the oldest failing job on prod0" and "which prod0 job failed longest ago" are the same test needs judgment, and that judgment belongs to `tg-score`, which already holds every scenario in context.

**Files:**
- Create: `src/testgen/dedupe.py`
- Test: `tests/unit/test_dedupe.py`

**Interfaces:**
- Consumes: `refs.cell_ref`.
- Produces: `dedupe.Candidate` — a frozen dataclass with fields `a: str`, `b: str`, `shared_cells: tuple[str, ...]`, `identical_cells: bool`; `dedupe.candidate_pairs(scenarios: list[dict]) -> list[Candidate]`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_dedupe.py`:

```python
from testgen.dedupe import Candidate, candidate_pairs


def _scn(sid, goal, cells, status="active"):
    return {
        "id": sid,
        "goal_id": goal,
        "status": status,
        "capability_refs": [{"capability_id": c, "outcome_class_id": o} for c, o in cells],
    }


def test_no_candidates_for_a_single_scenario():
    assert candidate_pairs([_scn("s1", "g1", [("cap-a", "oc-1")])]) == []


def test_same_goal_and_identical_cells_is_a_candidate():
    scenarios = [
        _scn("s1", "g1", [("cap-a", "oc-1")]),
        _scn("s2", "g1", [("cap-a", "oc-1")]),
    ]
    assert candidate_pairs(scenarios) == [
        Candidate(a="s1", b="s2", shared_cells=("cell:cap-a/oc-1",), identical_cells=True)
    ]


def test_same_goal_with_partial_overlap_is_a_candidate_but_not_identical():
    scenarios = [
        _scn("s1", "g1", [("cap-a", "oc-1"), ("cap-b", "oc-2")]),
        _scn("s2", "g1", [("cap-a", "oc-1")]),
    ]
    candidate = candidate_pairs(scenarios)[0]
    assert candidate.shared_cells == ("cell:cap-a/oc-1",)
    assert candidate.identical_cells is False


def test_different_goals_are_never_candidates():
    scenarios = [
        _scn("s1", "g1", [("cap-a", "oc-1")]),
        _scn("s2", "g2", [("cap-a", "oc-1")]),
    ]
    assert candidate_pairs(scenarios) == []


def test_same_goal_with_no_shared_cells_is_not_a_candidate():
    scenarios = [
        _scn("s1", "g1", [("cap-a", "oc-1")]),
        _scn("s2", "g1", [("cap-b", "oc-2")]),
    ]
    assert candidate_pairs(scenarios) == []


def test_already_resolved_scenarios_are_excluded():
    scenarios = [
        _scn("s1", "g1", [("cap-a", "oc-1")]),
        _scn("s2", "g1", [("cap-a", "oc-1")], status="duplicate"),
        _scn("s3", "g1", [("cap-a", "oc-1")], status="rejected"),
    ]
    assert candidate_pairs(scenarios) == []


def test_proposed_and_active_scenarios_are_both_considered():
    scenarios = [
        _scn("s1", "g1", [("cap-a", "oc-1")], status="proposed"),
        _scn("s2", "g1", [("cap-a", "oc-1")], status="active"),
    ]
    assert len(candidate_pairs(scenarios)) == 1


def test_pairs_are_ordered_and_each_appears_once():
    scenarios = [
        _scn("s3", "g1", [("cap-a", "oc-1")]),
        _scn("s1", "g1", [("cap-a", "oc-1")]),
        _scn("s2", "g1", [("cap-a", "oc-1")]),
    ]
    pairs = [(c.a, c.b) for c in candidate_pairs(scenarios)]
    assert pairs == [("s1", "s2"), ("s1", "s3"), ("s2", "s3")]


def test_shared_cells_are_sorted_for_stable_output():
    scenarios = [
        _scn("s1", "g1", [("cap-b", "oc-2"), ("cap-a", "oc-1")]),
        _scn("s2", "g1", [("cap-a", "oc-1"), ("cap-b", "oc-2")]),
    ]
    assert candidate_pairs(scenarios)[0].shared_cells == ("cell:cap-a/oc-1", "cell:cap-b/oc-2")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_dedupe.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'testgen.dedupe'`.

- [ ] **Step 3: Write the implementation**

`src/testgen/dedupe.py`:

```python
"""Proposing candidate duplicate scenario pairs.

The deterministic half of stage 3's dedupe. Two scenarios are candidates when
they serve the same goal and claim at least one coverage cell in common --
cheap to compute and a good filter. It never decides: recognising that "find
the oldest failing job on prod0" and "which prod0 job failed longest ago" are
the same test needs judgment, and tg-score makes that call with every
scenario already in context.

Scenarios already marked duplicate or rejected are excluded; re-proposing a
pair that was resolved in an earlier round is how a loop fails to converge.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any

from testgen.refs import cell_ref

_OPEN_STATUSES = frozenset({"proposed", "active"})


@dataclass(frozen=True)
class Candidate:
    """A pair worth a judgment call, with the evidence that raised it."""

    a: str
    b: str
    shared_cells: tuple[str, ...]
    identical_cells: bool


def _cells(scenario: dict[str, Any]) -> frozenset[str]:
    return frozenset(
        cell_ref(ref["capability_id"], ref["outcome_class_id"])
        for ref in scenario.get("capability_refs", [])
    )


def candidate_pairs(scenarios: list[dict[str, Any]]) -> list[Candidate]:
    """Candidate duplicate pairs, ordered by scenario id for stable output."""
    open_scenarios = sorted(
        (s for s in scenarios if s.get("status") in _OPEN_STATUSES),
        key=lambda s: s["id"],
    )
    out: list[Candidate] = []
    for first, second in combinations(open_scenarios, 2):
        if first.get("goal_id") != second.get("goal_id"):
            continue
        cells_a, cells_b = _cells(first), _cells(second)
        shared = cells_a & cells_b
        if not shared:
            continue
        out.append(
            Candidate(
                a=first["id"],
                b=second["id"],
                shared_cells=tuple(sorted(shared)),
                identical_cells=cells_a == cells_b,
            )
        )
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_dedupe.py -q`
Expected: PASS, 9 tests.

- [ ] **Step 5: Run the whole suite and the lint gate**

Run: `make test && make check`
Expected: all tests pass, no lint findings.

- [ ] **Step 6: Commit**

```bash
git add src/testgen/dedupe.py tests/unit/test_dedupe.py
git commit -S -s -m "feat: Add dedupe candidate proposal

Proposes candidate pairs -- same goal, at least one shared coverage cell --
and never decides. Semantic equivalence between two differently-worded
scenarios is a judgment call, and tg-score makes it with every scenario
already in context.

Scenarios already marked duplicate or rejected are excluded, because
re-proposing a pair resolved in an earlier round is exactly how an enrichment
loop fails to converge.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 11: The CLI and the README

The surface the orchestrator skill actually calls. **Exit codes are part of the contract, not a detail** — the orchestrator branches on them, so they need to distinguish "the artifact is bad" from "I could not run":

| Code | Meaning | Orchestrator's response |
|---|---|---|
| `0` | clean | dispatch the next stage |
| `1` | findings reported on stdout | one bounded repair attempt, then halt |
| `2` | usage error or unreadable run directory | halt; this is a bug in the harness, not in the stage output |

**Files:**
- Create: `src/testgen/cli.py`
- Create: `README.md`
- Test: `tests/unit/test_cli.py`

**Interfaces:**
- Consumes: everything from Tasks 1–10.
- Produces: `cli.main(argv: list[str] | None = None) -> int`, wired to the `testgen` console script declared in Task 1's `pyproject.toml`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_cli.py`:

```python
import json

from testgen.artifacts import write_json
from testgen.cli import main
from testgen.paths import RunPaths
from tests.builders import minimal_claims, minimal_scenarios, minimal_world_model


def _seeded_run(tmp_path):
    run = RunPaths(tmp_path / "runs" / "run-1")
    write_json(run.claims("aap2-api"), minimal_claims())
    write_json(run.world_model, minimal_world_model())
    return run


def test_no_subcommand_is_a_usage_error(capsys):
    assert main([]) == 2


def test_unknown_subcommand_is_a_usage_error():
    assert main(["frobnicate"]) == 2


def test_validate_a_clean_stage_exits_zero(tmp_path, capsys):
    run = _seeded_run(tmp_path)
    assert main(["validate", "--run", str(run.root), "--stage", "reconcile"]) == 0
    assert capsys.readouterr().out.strip() == ""


def test_validate_a_failing_stage_exits_one_and_prints_findings(tmp_path, capsys):
    run = _seeded_run(tmp_path)
    write_json(run.world_model, minimal_world_model(schema_version="0.9"))
    assert main(["validate", "--run", str(run.root), "--stage", "reconcile"]) == 1
    assert "[schema]" in capsys.readouterr().out


def test_validate_an_unknown_stage_is_a_usage_error(tmp_path):
    run = _seeded_run(tmp_path)
    assert main(["validate", "--run", str(run.root), "--stage", "reconsile"]) == 2


def test_validate_a_missing_run_directory_is_a_usage_error(tmp_path):
    assert main(["validate", "--run", str(tmp_path / "absent"), "--stage", "reconcile"]) == 2


def test_check_refs_on_a_clean_run_exits_zero(tmp_path, capsys):
    run = _seeded_run(tmp_path)
    assert main(["check-refs", "--run", str(run.root)]) == 0
    assert capsys.readouterr().out.strip() == ""


def test_check_refs_prints_findings_and_exits_one(tmp_path, capsys):
    run = _seeded_run(tmp_path)
    world = minimal_world_model()
    world["denominator"]["goals"] = 7
    write_json(run.world_model, world)
    assert main(["check-refs", "--run", str(run.root)]) == 1
    assert "[refs]" in capsys.readouterr().out


def test_dedupe_candidates_emits_json_on_stdout(tmp_path, capsys):
    run = _seeded_run(tmp_path)
    payload = minimal_scenarios()
    second = dict(payload["scenarios"][0])
    second["id"] = "scn-002"
    payload["scenarios"].append(second)
    write_json(run.scenarios, payload)
    assert main(["dedupe-candidates", "--run", str(run.root)]) == 0
    emitted = json.loads(capsys.readouterr().out)
    assert emitted == [
        {
            "a": "scn-001",
            "b": "scn-002",
            "shared_cells": ["cell:cap-find-jobs/oc-success"],
            "identical_cells": True,
        }
    ]


def test_dedupe_candidates_without_scenarios_is_a_usage_error(tmp_path):
    run = _seeded_run(tmp_path)
    assert main(["dedupe-candidates", "--run", str(run.root)]) == 2


def test_intake_creates_a_run_and_prints_its_path(tmp_path, capsys):
    source = tmp_path / "api.json"
    source.write_text('{"tools": []}', encoding="utf-8")
    code = main(
        [
            "intake",
            "--input", str(source),
            "--runs-dir", str(tmp_path / "runs"),
            "--target-name", "aap2",
            "--target-interface", "mcp",
            "--max-rounds", "2",
            "--max-scenarios", "8",
        ]
    )
    assert code == 0
    printed = capsys.readouterr().out.strip()
    assert (tmp_path / "runs") == __import__("pathlib").Path(printed).parent
    assert (__import__("pathlib").Path(printed) / "manifest.json").is_file()


def test_intake_with_a_missing_input_is_a_usage_error(tmp_path):
    code = main(
        [
            "intake",
            "--input", str(tmp_path / "absent.json"),
            "--runs-dir", str(tmp_path / "runs"),
            "--target-name", "aap2",
            "--target-interface", "mcp",
        ]
    )
    assert code == 2


def test_intake_defaults_the_first_slice_limits(tmp_path, capsys):
    from testgen.artifacts import read_json

    source = tmp_path / "api.json"
    source.write_text('{"tools": []}', encoding="utf-8")
    main(
        [
            "intake",
            "--input", str(source),
            "--runs-dir", str(tmp_path / "runs"),
            "--target-name", "aap2",
            "--target-interface", "mcp",
        ]
    )
    printed = capsys.readouterr().out.strip()
    manifest = read_json(__import__("pathlib").Path(printed) / "manifest.json")
    assert manifest["limits"] == {"max_rounds": 2, "max_scenarios": 8}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_cli.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'testgen.cli'`.

- [ ] **Step 3: Write the implementation**

`src/testgen/cli.py`:

```python
"""Command-line surface for the deterministic pipeline components.

Exit codes are part of the contract the orchestrator skill branches on:

    0  clean
    1  findings, printed one per line on stdout
    2  usage error, or a run directory that could not be read

The distinction between 1 and 2 matters. A 1 means the stage produced a bad
artifact and is worth one repair attempt; a 2 means the harness itself is
misconfigured and repeating the stage cannot help.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from testgen import refs
from testgen.artifacts import ArtifactError, read_json
from testgen.dedupe import candidate_pairs
from testgen.findings import format_findings
from testgen.intake import intake
from testgen.paths import STAGES, RunPaths
from testgen.validate import UnknownStage, validate_stage

CLEAN, FINDINGS, USAGE = 0, 1, 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="testgen", description=__doc__)
    subparsers = parser.add_subparsers(dest="command")

    p_intake = subparsers.add_parser("intake", help="register inputs and mint a run")
    p_intake.add_argument("--input", action="append", required=True, metavar="PATH")
    p_intake.add_argument("--runs-dir", required=True)
    p_intake.add_argument("--target-name", required=True)
    p_intake.add_argument("--target-interface", required=True)
    p_intake.add_argument("--max-rounds", type=int, default=2)
    p_intake.add_argument("--max-scenarios", type=int, default=8)

    p_validate = subparsers.add_parser("validate", help="schema-validate one stage's output")
    p_validate.add_argument("--run", required=True)
    p_validate.add_argument("--stage", required=True, choices=list(STAGES))

    p_refs = subparsers.add_parser("check-refs", help="cross-artifact and reachability checks")
    p_refs.add_argument("--run", required=True)

    p_dedupe = subparsers.add_parser(
        "dedupe-candidates", help="propose candidate duplicate scenario pairs as JSON"
    )
    p_dedupe.add_argument("--run", required=True)
    return parser


def _run_dir(raw: str) -> RunPaths:
    root = Path(raw)
    if not root.is_dir():
        raise FileNotFoundError(f"run directory does not exist: {root}")
    return RunPaths(root)


def _report(findings) -> int:
    if not findings:
        return CLEAN
    print(format_findings(findings))
    return FINDINGS


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    # parse_known_args rather than parse_args so an unknown subcommand becomes
    # our exit code 2 instead of argparse's SystemExit(2) escaping the caller.
    try:
        args, extra = parser.parse_known_args(argv)
    except SystemExit:
        return USAGE
    if args.command is None or extra:
        parser.print_usage(sys.stderr)
        return USAGE

    try:
        if args.command == "intake":
            run = intake(
                inputs=[Path(p) for p in args.input],
                runs_dir=Path(args.runs_dir),
                target_name=args.target_name,
                target_interface=args.target_interface,
                max_rounds=args.max_rounds,
                max_scenarios=args.max_scenarios,
            )
            print(run.root)
            return CLEAN

        if args.command == "validate":
            return _report(validate_stage(_run_dir(args.run), args.stage))

        if args.command == "check-refs":
            return _report(refs.check_all(_run_dir(args.run)))

        if args.command == "dedupe-candidates":
            run = _run_dir(args.run)
            scenarios = read_json(run.scenarios).get("scenarios", [])
            print(
                json.dumps(
                    [dataclasses.asdict(c) for c in candidate_pairs(scenarios)],
                    indent=2,
                    sort_keys=True,
                )
            )
            return CLEAN
    except (FileNotFoundError, FileExistsError, ArtifactError, UnknownStage, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return USAGE

    parser.print_usage(sys.stderr)
    return USAGE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

Note on `dataclasses.asdict`: `Candidate.shared_cells` is a tuple, and `asdict` leaves tuples as tuples, which `json.dumps` renders as an array. That is why the test expects a list.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli.py -q`
Expected: PASS, 14 tests.

- [ ] **Step 5: Write the README**

`README.md`:

```markdown
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
| `schema/` | One JSON Schema per artifact kind |

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
  --target-interface mcp
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
```

- [ ] **Step 6: Run the whole suite and the lint gate**

Run: `make test && make check`
Expected: all tests pass, no lint findings.

- [ ] **Step 7: Confirm the installed console script works end to end**

```bash
uv run testgen intake --input schema/claims-0.1.json --runs-dir /tmp/tg-runs \
  --target-name smoke --target-interface none
uv run testgen validate --run "$(ls -d /tmp/tg-runs/run-* | tail -1)" --stage intake
echo "validate exit: $?"
uv run testgen check-refs --run "$(ls -d /tmp/tg-runs/run-* | tail -1)"
echo "check-refs exit: $?"
rm -rf /tmp/tg-runs
```

Expected: intake prints a run path; `validate --stage intake` exits `0`; `check-refs` exits `0` (no world model yet, and that absence is not a finding).

- [ ] **Step 8: Commit**

```bash
git add src/testgen/cli.py README.md tests/unit/test_cli.py
git commit -S -s -m "feat: Add the CLI and README

Exit codes are contract, not detail: 0 clean, 1 findings on stdout, 2 usage or
unreadable run. The orchestrator branches on the difference -- a 1 means the
stage produced a bad artifact and earns one repair attempt, a 2 means the
harness is misconfigured and repeating the stage cannot help.

parse_known_args is used rather than parse_args so an unknown subcommand
returns our exit code 2 instead of letting argparse's SystemExit escape into
the caller.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Self-Review

Run against the spec after finishing all eleven tasks.

**Spec coverage for this plan's scope (§4 artifact contract, §8 code gates):**

| Spec element | Task |
|---|---|
| Run directory layout (§4) | 1 |
| Canonical byte-stable artifact JSON (§4) | 2 |
| Claim atom with evidence + derivation (§4) | 3 |
| World model: capabilities, entities, actors, goals, contradictions, gaps, denominator (§4) | 3 |
| `machine:` / `prose:` invariants (§4) | 3, 6 |
| Scenario with `capability_refs` + `discriminating_fact` (§4) | 4 |
| Coverage: two matrices, holes, progress, verdict (§4) | 4 |
| Manifest with per-stage model/effort/skill hash (§4) | 4 |
| Oracle with `grounded_in.seed_pointer` (§4) | 5 |
| Verdict with `minimum_tool_calls_found` (§4) | 5 |
| Validation layer 1: schema (§4) | 3 |
| Validation layer 2: referential integrity + reachability (§4) | 7, 8 |
| Frozen denominator, amendment bumps version (§4) | 3 (schema), 7 (check) |
| Reachability by construction (§3, §6) | 8 |
| Run ids and timestamps minted by code (§4) | 9 |
| Dedupe candidates before per-scenario fan-out (§3, §5) | 10 |
| Closed assertion vocabulary (§7) | 5 |

**Deliberately out of scope here** — these belong to Plan 2 (emit + measure) and Plan 3 (the skills), and are listed so a reviewer does not read their absence as a gap: the generic `verify.py`, `emit`, `smoke`, `compare-gold`, `diff-runs`, `sample-for-review`, all eight `SKILL.md` files, the negative refusal fixtures, and the golden end-to-end toy fixture.

**Two spec amendments this plan makes** (both applied in Task 5, Step 7):
1. Grounding differs by assertion kind — data assertions carry a seed pointer, trajectory assertions carry a `capability_id`.
2. `negative_expectations` is removed as redundant with `answer_excludes`.

**Type consistency check:** `Finding(artifact, layer, pointer, message)` is constructed identically in Tasks 3, 7, and 8. `RunPaths` method names used in `validate._artifact_paths`, `refs`, `intake`, and `cli` all come from Task 1's Interfaces block. `cell_ref` is defined in Task 7 and consumed by Task 10. `invariants.evaluate` is defined in Task 6 and imported in Task 8 under the alias `evaluate_invariant`.

**Ordering constraint:** Task 8 changes `minimal_world_model` in `tests/builders.py` (adding the `controller` field), which Task 7's tests also consume. Task 8's Step 7 re-runs the whole suite for exactly that reason. Tasks 1–11 must be executed in order; the only genuinely independent pair is 9 and 10.

**Test-count expectations** in each "verify it passes" step are the counts implied by the test code as written. If a count is off by one after transcription, check for a dropped `@pytest.mark.parametrize` case before assuming the implementation is wrong.
