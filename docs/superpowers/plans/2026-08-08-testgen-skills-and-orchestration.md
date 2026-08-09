# Skills and Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the six stage skills, the orchestrator skill, and the thin `tg-emit` entry point that turn the existing deterministic spine into a pipeline a model can actually run — plus the mechanical grip on prompts that keeps them from drifting away from the artifact contract.

**Architecture:** Every skill is a `SKILL.md` under `src/testgen/skills/tg-<name>/`, carrying a machine-readable `## Contract` block that declares which `RunPaths` names it reads and writes, which artifact kinds it produces, and which `testgen` subcommands it invokes. A new `skills.py` parses that block and a new `testgen check-skills` cross-checks every declaration against `paths.RunPaths`, `validate.STAGE_ARTIFACTS`, and the CLI's own subparser names — so a prompt that names a path or a stage that does not exist fails in CI rather than at run time. Two small CLI additions (`record-stage`, `decide`) give the orchestrator the two writers the contract declares but nobody implements. A hand-authored two-capability toy world runs the whole chain in CI with no model at all, and each skill is additionally exercised once, for real, against that world.

**Tech Stack:** Python 3.13, uv, jsonschema (Draft202012Validator), tomllib (stdlib — the contract block is TOML, so no new dependency), tomli-w, pytest, ruff.

## Global Constraints

Every task's requirements implicitly include this section. Values are verbatim.

- **Python 3.13**, managed with `uv`. `make setup` / `make test` / `make check` are the only entry points; `make check` must be clean (`ruff check .` and `ruff format --check .`).
- **ruff**: `line-length = 100`, `target-version = "py313"`, `select = ["E", "F", "I", "UP", "B", "SIM"]`. `docs/` is excluded from ruff; `README.md` is **not**.
- **No new runtime dependencies.** The contract block is TOML so `tomllib` (stdlib) parses it. Do not add PyYAML, and do not hand-roll a YAML parser.
- **Exit codes are the orchestrator's contract** (`cli.py` docstring): `0` clean, `1` findings printed one per line on stdout, `2` usage error or an unreadable run directory. **A stage defect must never surface as `2`**, and **a `1` must never have empty stdout**. A malformed *human-authored* file (a `--skills-dir` that is not a directory, a `SKILL.md` whose contract block is not TOML) is `2`: there is no stage to hand a repair prompt to. This is the same ruling `--agents` and `--gold` already carry.
- **Never restate a constant or a rule across a seam — import it.** This build adds a fourth consumer of the closed assertion vocabulary, so Task 2 consolidates it. No task may write a second copy of a stage list, a status set, an artifact-kind name, or an assertion kind.
- **Layer-2 precondition:** `refs.py` and `emit.py` index schema-required keys directly and may raise. `skills.py` has no such gate in front of it, so it must return findings rather than raise for anything a human could get wrong in a `SKILL.md`, and raise `UsageError` only for a file it cannot read at all.
- **Determinism:** no `random`, no builtin `hash()` (salted per process), no wall-clock in any artifact a diff compares. Timestamps and run ids come from code, never from a skill (design spec §4). `decide`'s timestamp is minted by `decide`, not written by the orchestrator prompt.
- **Artifacts are the only channel between stages.** A dispatched subagent receives exactly three things: the run directory path, its stage name, and its skill. No conversational context is threaded through. Every `SKILL.md` must be written so that this is sufficient.
- **Test hygiene.** Every new check needs (a) deletion-mutation evidence — deleting the check must make a *named* test fail — and (b) its dual: the pipeline state in which the check must stay *silent*, added to `tests/unit/test_refs_states.py` if it is a layer-2 check. Mutation harnesses must set `PYTHONDONTWRITEBYTECODE=1` or sweep `__pycache__` between mutate and restore, or a byte-length-preserving mutate-then-restore inside one second leaves CPython's mutated `.pyc` live and the evidence is a lie.
- **The three test-weakness shapes** (design spec §8, item 4) are a required self-check on every test written in this plan. Before claiming a task done, name for each new test which shape it could be, and why it is not:
  1. *Substring-of-message* — the assertion searches for a literal that some other finding's message also contains, so deleting the check leaves the test green.
  2. *Fixture-cannot-reach* — the fixture has one of everything, so it cannot distinguish "filtered correctly" from "never filtered at all". It has nothing left over for the check to have missed.
  3. *Holds-identically-before-and-after* (hash luck) — the expected answer coincides with the mechanism under test, so the test cannot detect its substitution.
- **Every filesystem call in a module whose failures are all exit-2 must map `OSError` to `UsageError`, and the catch tuples across sibling handlers must match.** This build hit the shape three times: `decide` catching only `UsageError` while its sibling `record-stage` caught `(UsageError, OSError)`; `skills.discover`/`check_all` guarding a *nonexistent* directory but leaving `iterdir()` on an unreadable one unwrapped; and, before this plan, `smoke.load_agents`, whose docstring records the first occurrence. In every case the symptom is identical and is the worst one available: a filesystem or configuration problem that **no stage wrote and no repair prompt can fix** surfaces as exit 1 with a fabricated finding telling the orchestrator to spend its one bounded repair attempt on an artifact that is fine. When adding or reviewing a handler, diff its catch tuple against its siblings' — an asymmetry between two handlers in the same file is the tell.
- **At every fix, ask what the same mistake is one scope narrower.** Added mid-build, after this plan hit it twice in its first two tasks. Task 1 closed "the contract block is found anywhere in the file" and the identical defect survived *inside* the Contract section. Task 2 closed "the declared value is the wrong container type" and the identical defect survived at the *element* type. Both narrower cases were reachable, and in both cases the fix's own new tests missed them — because a test written to cover the case you just understood does not reach the case one level in. This is not deletion-mutation and not the three shapes below; it is a question to ask out loud in every fix round, and the answer goes in the report even when it is "none."
- **A verified claim beats a plausible one, and a rationale is a claim.** Also added mid-build: this plan asserted twice, in successive rounds, that a particular test was weak, and both rationales were false — each survived until someone ran a mutation. When a report says a test is weak, redundant, or load-bearing, that statement must come with the mutation that established it, not the reasoning that suggested it.
- **A skill is text, so text-level tests must assert structure, not vibes.** A test on a `SKILL.md` must assert a *structural* property — a required heading is present, heading A precedes heading B, a declared set equals a set imported from code — never a bare free-text substring, unless the substring is a value imported from code and the test says so. A free-text substring assertion on prose is shape 1 by construction.
- **DCO and signing are mandatory on every commit:** `git commit -S -s`. Never commit without `-S`. If signing fails, stop and report it — do not fall back to an unsigned commit and do not work around signing. Use `Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>`; never `Co-Authored-By`, `Made-with`, or any trailer GitHub parses as co-authorship.

---

## Spec reconciliation

Seven places where this plan departs from, or resolves an ambiguity in, `docs/superpowers/specs/2026-08-06-skill-based-test-generator-design.md`. Each is a decision the implementer must not re-litigate; each is written back into the spec by Task 15.

**1. Skills live at `src/testgen/skills/`, not repo-root `skills/`.** §5 writes the path as `skills/tg-{...}/SKILL.md`. That path cannot be package data: `[tool.setuptools.packages.find] where = ["src"]`, so a repo-root directory ships in no wheel. An installed copy that can validate and emit but cannot find its own skills is exactly the hole the "ship the schemas as package data" fix closed (commit `7d719b9`), and §5's own path list already deviated once on packaging grounds ("Shipped as one console script with subcommands … only the packaging differs"). So skills go to `src/testgen/skills/tg-<name>/SKILL.md`, added to `[tool.setuptools.package-data]`, discovered by `skills.skills_dir()` mirroring `validate.schema_dir()` exactly — package data beside the module, overridable via `TESTGEN_SKILLS_DIR` so a candidate skill set can be checked without reinstalling. §5's *names* and *responsibilities* are unchanged.

**2. Skills are dispatched by file path, not by Claude Code skill discovery.** §4 says a dispatched subagent receives exactly three things: the run directory, its stage name, and its skill. Handing it a path satisfies that literally. Putting these eight skills under `.claude/skills/` would additionally make them auto-visible in every unrelated session in this repository, which is a side effect the contract does not ask for. Explicit non-goal.

**3. Plan 4 does not execute the aap2 slice-1 run.** §8's first slice includes a real run with all stages present and measurement; §11 asks for a plan covering it. This plan builds every component that run needs and exercises each skill once against the toy world, but the aap2 run itself is Plan 5. Reasons: it needs API budget, it needs the three human gates of §5 (or a documented `--no-gate` decision), and it produces measurement outputs that are experiment results rather than build artifacts. Deferring it keeps the review gate on this plan about whether the prompts and the contract are right, which is answerable, rather than about whether the aap2 world came out well, which is not.

**4. §9's "one golden end-to-end fixture" is additive to `tests/builders.py`, which stays.** A partial precursor already exists: `tests/builders.py` plus `tests/unit/test_refs_states.py` assemble a synthetic run through every state. Those payloads are deliberately *minimal* — one capability, one outcome-class pair, one scenario, no `machine:` invariant, no distractors, no `answer_excludes`, no `not_found` class, no contradiction — because their job is to be mutation fodder where one changed key is the whole test. The toy world is the opposite artifact: a world small enough to read but complete enough to be *reviewable*, run end to end from real input files through real `intake`. Both stay. Task 4 states this in the module docstring so the next reader does not "consolidate" them.

**5. `manifest.stages` has no writer, and this plan gives it one.** §4's reproducibility hook says the manifest records per stage: model, effort, and a content hash of the `SKILL.md` used. `intake` writes `"stages": {}` and nothing has ever written into it; `stability.stage_config` reads it and `diff_runs` gates comparability on it, so today two runs are trivially "comparable" because neither records anything. `testgen record-stage` closes it (Task 3). This is not a new feature — it is the absence of a declared one, the same shape as the unenforced `manifest.limits` the measurement build closed.

**6. `decisions.md` has no writer either.** `artifacts.append_decision` exists and no caller invokes it. §5's loop says "append decision to decisions.md" and §4 calls it the run's append-only lab notebook. `testgen decide` closes it (Task 3), and the timestamp comes from `decide` rather than from the orchestrator's prompt because §4's rule is that a skill that invents a timestamp makes two otherwise-identical runs diff.

**7. Each skill gets one real single-stage execution, run by the controller — not by the implementer.** §8's own note on Plan 4 is unambiguous: "a prompt's failure mode is behavioral, so an execution trace is the only artifact that will show it, and reading a `SKILL.md` tells you what it asked for, not what a model did with it." So every skill task ends with a **live exercise**: a fresh subagent given exactly the three things §4 permits, followed by `testgen validate --stage <s>` and `testgen check-refs`. The implementer must not run it, because the implementer's context holds the skill it just wrote and the brief that specified it — which is precisely the isolation the exercise exists to test. The controller runs it after the task review passes, against `tests/fixtures/toy/`. Each skill task therefore ships an `exercise.md` stating what the exercise must produce and what would count as a failure, and the controller's result is recorded in the SDD ledger.

---

## The skill contract

Every `SKILL.md` in this build has this shape. The five numbered sections are §5's uniform skill shape, unchanged. The `## Contract` block is new: it is the machine-readable declaration `check-skills` verifies, and it is the **only** place a path or an artifact kind is named, so the prose can never drift from it.

````markdown
---
name: tg-extract
description: Read one registered input artifact and record every statement it makes about the target as a claim.
---

# tg-extract

<One paragraph: what this stage is for and why it is a separate stage.>

## Contract

```toml
stage = "extract"
reads = ["manifest", "input_file"]
writes = ["claims"]
schemas = ["claims"]
invokes = ["validate"]
```

## 1. Inputs

<Prose. What it reads, and — load-bearing — what it must not read.>

## 2. Output

<Prose. The single artifact it writes and what "done" means.>

## 3. Method

<The judgment. The only section that differs meaningfully between skills.>

## 4. Invariants

<What must hold beyond the schema, stated so the skill self-checks before writing.>

## 5. Refusal conditions

<When to record a gap or halt instead of guessing. §5: the most important
prompt-level decision in the system.>
````

**Contract keys, and what `check-skills` does with each:**

| Key | Meaning | Checked against |
|---|---|---|
| `stage` | The `paths.STAGES` entry this skill implements. Absent for `tg-orchestrate`, which is not a stage. | `paths.STAGES` |
| `reads` | `RunPaths` attribute or method names, never literal paths. | `hasattr(RunPaths, name)` |
| `writes` | Same, for what it produces. | `hasattr(RunPaths, name)` |
| `schemas` | The artifact kinds its output must validate against. | `validate.STAGE_ARTIFACTS[stage]`, as a set equality |
| `invokes` | `testgen` subcommand names the skill tells the model to run. | the CLI's own subparser names |

`schemas` is a **set equality**, not a subset: a skill that forgets it must also write `expected.json` alongside `seed.json` is exactly the drift this check exists to catch, and a subset check would pass it.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/testgen/skills.py` | **Create.** Discover skills, parse the `## Contract` block, hash a `SKILL.md`, and check every declaration against the code that owns it. The only module that reads skill text. |
| `src/testgen/skills/tg-extract/SKILL.md` | **Create.** Stage 1a: one input artifact → claims. Fan-out. |
| `src/testgen/skills/tg-reconcile/SKILL.md` | **Create.** Stage 1b: all claims → the world model, contradictions, gaps, and the frozen denominator. Barrier. |
| `src/testgen/skills/tg-propose/SKILL.md` | **Create.** Stage 2: coverage holes → scenarios, each carrying a `discriminating_fact`. |
| `src/testgen/skills/tg-score/SKILL.md` | **Create.** Stage 3: compute both matrices, rule on dedupe candidates, justify every hole, compute the verdict. |
| `src/testgen/skills/tg-instantiate/SKILL.md` | **Create.** Stage 4: co-design a seed world and its oracle for one scenario. §6's six numbered steps. |
| `src/testgen/skills/tg-challenge/SKILL.md` | **Create.** Stage 5: adversarially verify one instance, reading `expected.json` last. |
| `src/testgen/skills/tg-emit/SKILL.md` | **Create.** Thin human-facing entry point over `testgen emit`. Writes nothing itself. |
| `src/testgen/skills/tg-orchestrate/SKILL.md` | **Create.** The loop: dispatch, validate, one bounded repair, human gates, `record-stage`, `decide`. |
| `src/testgen/skills/tg-*/exercise.md` | **Create,** one per skill. The live exercise's pass criteria and the properties to look for. Documentation, not a test: `check-skills` ignores it and no schema gates it. |
| `src/testgen/manifest.py` | **Create.** `record_stage`, `decide`, and the one spelling of the artifact timestamp format. Separate from `intake.py` because these are written *between* stages, not at stage 0. |
| `src/testgen/cli.py` | **Modify.** Add `check-skills`, `record-stage`, `decide`. Expose `subcommand_names()`. |
| `src/testgen/validate.py` | **Modify.** Add `manifest_stage_efforts()`, reading the effort enum out of the manifest schema so `record-stage` does not restate it. |
| `src/testgen/suite/verify.py` | **Modify.** Promote `_ANSWER_KINDS`/`_TOOL_KINDS` to public `DATA_KINDS`/`TRAJECTORY_KINDS`/`ASSERTION_KINDS`. |
| `src/testgen/emit.py`, `src/testgen/refs.py` | **Modify.** Import those instead of holding private copies. |
| `src/testgen/findings.py` | **Modify.** Add `"skill"` to the layer list in the docstring. |
| `src/testgen/paths.py` | **Modify.** Nothing structural — `skills.py` reads `RunPaths` by name. Touched only if a skill needs a name that does not exist yet. |
| `tests/fixtures/toy/` | **Create.** `api.json`, `notes.md`, `trace.json` — the three real input files the toy world is built from. |
| `tests/fixtures/toy-contradiction/`, `tests/fixtures/toy-gap/` | **Create.** §9's negative refusal fixtures. |
| `tests/toy.py` | **Create.** Builders for every hand-authored stage artifact of the toy world, mirroring `tests/builders.py`. |
| `tests/unit/test_skills_contract.py` | **Create.** The parametrized contract check over every discovered skill. |
| `tests/unit/test_skills_parse.py` | **Create.** Parsing and hashing, including every malformed-`SKILL.md` shape. |
| `tests/unit/test_skills_<stage>.py` | **Create,** one per skill: the structural properties that matter for *that* prompt. |
| `tests/unit/test_manifest_stages.py` | **Create.** `record-stage` and `decide`. |
| `tests/unit/test_toy_fixture.py` | **Create.** The toy world's own gate: its artifacts validate and are mutually consistent, checked before anything runs them. |
| `tests/unit/test_toy_end_to_end.py` | **Create.** §9's golden fixture: real `intake`, every stage validated, `check_all` clean, `emit`, `smoke`. |
| `tests/unit/test_refusal_fixtures.py` | **Create.** What can be asserted about the negative fixtures without a model. |
| `tests/unit/test_refusals_live.py` | **Create.** The refusals themselves, against a committed recording. `live`-marked. |
| `tests/unit/test_live_marker.py` | **Create.** That the marker is registered, skips by default, runs with the opt-in, and says how. |
| `tests/conftest.py` | **Create.** The `live` marker and its skip logic. |
| `docs/running-a-stage-by-hand.md` | **Create.** The runbook every live exercise follows: the dispatch prompt, the verification commands, and how to read a failure. |
| `Makefile` | **Modify.** A `live` target. |
| `pyproject.toml` | **Modify.** `skills/**/*.md` as package data; the `live` marker registered. |
| `README.md` | **Modify.** The skills table, the two new subcommands, how to run a stage by hand. |
| `docs/superpowers/specs/2026-08-06-skill-based-test-generator-design.md` | **Modify.** The seven reconciliations above, and what this build parked. |

---

## Task 1: Parse and hash a SKILL.md

**Files:**
- Create: `src/testgen/skills.py`
- Test: `tests/unit/test_skills_parse.py`
- Modify: `pyproject.toml` (package data)

**Interfaces:**
- Consumes: `testgen.artifacts.sha256_of`, `testgen.artifacts.ArtifactError`, `testgen.errors.UsageError`, `testgen.paths.STAGES`.
- Produces, for Tasks 2–13:
  - `SKILL_FILENAME = "SKILL.md"`
  - `CODE_ONLY_STAGES: frozenset[str]` — stages with no skill.
  - `ORCHESTRATOR = "tg-orchestrate"`
  - `SECTIONS: tuple[str, ...]` — the five section headings, in order.
  - `CONTRACT_HEADING = "Contract"` — deliberately **not** a member of `SECTIONS`, which is the five numbered sections. One definition of the heading name.
  - `class Skill` — frozen dataclass: `name: str`, `path: Path`, `contract: dict[str, Any]`, `headings: tuple[str, ...]`, `body: str`, plus a `declared(key) -> list[str]` helper that returns `[]` for an absent or non-list key (tolerant on purpose: an absent key is Task 2's finding to report by name, and raising here would make it exit 2).
  - `skills_dir() -> Path`
  - `discover(root: Path | None = None) -> list[Skill]`
  - `load(path: Path) -> Skill`
  - `section_body(skill: Skill, heading: str) -> str` — the text under one `## ` heading, up to the next one **or end of file**. Public, with three callers: Task 2's refusal-emptiness check, Task 12's Method-ordering slice, and `load` itself.
  - `skill_sha256(path: Path) -> str`
  - `expected_skill_names() -> tuple[str, ...]`

**The parsing must be section-aware and fence-aware, and both halves are load-bearing.** Find the contract block **inside the `## Contract` section only**, not anywhere in the file: a stray valid-TOML fence in the prose above it that happens to supply plausible values for every key would otherwise be parsed as the contract, silently. And skip fenced regions when detecting headings: a `## ` line inside a code block would otherwise land in `headings`, which Task 12's ordering check depends on being right. Do the fence tracking with a legible line-by-line loop that toggles a flag on ```` ``` ```` lines — not with a regex. A regex that tracks fence state is unreadable, and this codebase prefers a commented loop. A file with no `## Contract` heading at all is a `UsageError` naming the file, the same class as a missing block.

**The Contract section must hold exactly one ` ```toml ` fence, and any other count is refused.** Slicing to the section is necessary but not sufficient: a decoy inside it — a "deprecated example" or a before/after pair, both plausible authoring patterns — wins on a plain `search()`, silently. Count with `finditer` and raise `UsageError` naming the file and the count. **Refuse; do not choose.** Taking the first or the last is a guess, and this project's rule everywhere else is that an ambiguous input is reported rather than resolved in the reader's favour. Do **not** make the TOML regex itself fence-aware to disambiguate — counting matches in one already-sliced section is enough, and growing this into a markdown parser would be its own defect.

**Map a decode failure to `UsageError` too.** `path.read_text(encoding="utf-8")` raises `UnicodeDecodeError`, which is a subclass of `ValueError` and **not** of `OSError` — so `except OSError` alone lets it propagate. That is not a cosmetic gap: `cli.py`'s outer catch deliberately excludes `ValueError`, so once Task 2 wires this into `check-skills` an unhandled decode error becomes **exit 1 with an `[internal]` finding blaming a run directory**, telling the orchestrator to spend its one bounded repair attempt re-running a stage over a mis-encoded prompt file no stage wrote. Catch `(OSError, UnicodeDecodeError)`.

**`section_body` must handle EOF.** Section 5 is last in every real skill, so an implementation that required a following `## ` heading would read every refusal section as empty — and Task 2's emptiness check would then fire on every correct skill.

**Design notes the brief must carry verbatim:**

- `skills_dir()` mirrors `validate.schema_dir()` exactly: `TESTGEN_SKILLS_DIR` if set, else `Path(__file__).resolve().parent / "skills"`.
- `CODE_ONLY_STAGES = frozenset({"intake", "smoke"})`. Every other member of `paths.STAGES` must have a skill, and `expected_skill_names()` derives the list — `tuple(f"tg-{s}" for s in STAGES if s not in CODE_ONLY_STAGES) + (ORCHESTRATOR,)`. Do **not** write the eight names out; adding a stage to `STAGES` must immediately demand a skill.
- The contract block is the first fenced ` ```toml ` block in the file, parsed with `tomllib.loads`. Anything else about the markdown is not this module's business.
- `headings` is every `## ` heading in document order, stripped. Ordering checks in later tasks depend on the order being preserved, so it is a tuple, not a set.
- `skill_sha256` is `artifacts.sha256_of` — do not reimplement hashing. It hashes the **whole file**, contract block and prose together, because §4's hook is a content hash of the skill that was used.
- Failure mapping is the exit-code contract: a `SKILL.md` that does not exist, or whose contract block is absent or is not valid TOML, raises `UsageError` (→ exit 2, a human-authored file nothing can repair by re-prompting). A contract block that parses but declares something wrong is **not** this module's error — it is a Task 2 finding.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_skills_parse.py`:

```python
"""Parsing one SKILL.md, and the failures that are exit 2 rather than findings.

A malformed SKILL.md is a human-authored file: no stage produces it, so no
repair prompt fixes it. That is the same ruling --agents and --gold carry, and
it is why the assertions below expect UsageError rather than a Finding.
"""

from __future__ import annotations

import hashlib

import pytest

from testgen.errors import UsageError
from testgen.paths import STAGES
from testgen.skills import (
    CODE_ONLY_STAGES,
    ORCHESTRATOR,
    SECTIONS,
    SKILL_FILENAME,
    Skill,
    discover,
    expected_skill_names,
    load,
    skill_sha256,
    skills_dir,
)

CONTRACT = """\
```toml
stage = "extract"
reads = ["manifest", "input_file"]
writes = ["claims"]
schemas = ["claims"]
invokes = ["validate"]
```
"""


def write_skill(root, name, contract=CONTRACT, headings=SECTIONS, extra=""):
    """A minimal well-formed SKILL.md, with knobs for the negative cases."""
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        f"name: {name}",
        "description: A skill, for testing.",
        "---",
        "",
        f"# {name}",
        "",
        "Purpose paragraph.",
        "",
        "## Contract",
        "",
        contract,
    ]
    for heading in headings:
        lines += ["", f"## {heading}", "", "Body text."]
    if extra:
        lines += ["", extra]
    path = directory / SKILL_FILENAME
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_load_returns_the_contract_and_the_headings_in_order(tmp_path):
    path = write_skill(tmp_path, "tg-extract")
    skill = load(path)
    assert isinstance(skill, Skill)
    assert skill.name == "tg-extract"
    assert skill.path == path
    assert skill.contract == {
        "stage": "extract",
        "reads": ["manifest", "input_file"],
        "writes": ["claims"],
        "schemas": ["claims"],
        "invokes": ["validate"],
    }
    # "Contract" first, then the five sections, in document order. The tuple
    # order is load-bearing: tg-challenge's ordering test reads it.
    assert skill.headings == ("Contract", *SECTIONS)


def test_the_headings_tuple_preserves_document_order_not_sorted_order(tmp_path):
    """Pins order specifically, because ("Contract", *SECTIONS) happens to be
    close to sorted order and a set() would satisfy the test above.
    """
    reversed_sections = tuple(reversed(SECTIONS))
    path = write_skill(tmp_path, "tg-extract", headings=reversed_sections)
    assert load(path).headings == ("Contract", *reversed_sections)


def test_skill_sha256_is_the_digest_of_the_whole_file(tmp_path):
    """The manifest's reproducibility hook hashes the skill that was used.

    Whole-file equality against an independently computed digest, and that is
    deliberately the *only* assertion here. Because it pins the digest to the
    true hash of the bytes, any implementation satisfying it must also change
    output whenever the file changes -- prose included. So a changed Method
    section changes the recorded hash, which is what makes the hook meaningful,
    and a separate "editing the prose changes the digest" test would be
    subsumed rather than additive. See the plan's self-check note: that pair
    was mandated on a rationale that turned out to be false twice.
    """
    path = write_skill(tmp_path, "tg-extract")
    assert skill_sha256(path) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_discover_finds_every_skill_directory_sorted(tmp_path):
    write_skill(tmp_path, "tg-reconcile")
    write_skill(tmp_path, "tg-extract")
    (tmp_path / "not-a-skill").mkdir()
    assert [s.name for s in discover(tmp_path)] == ["tg-extract", "tg-reconcile"]


def test_a_directory_without_a_skill_file_is_not_discovered(tmp_path):
    """A stray directory is skipped, not an error: check-skills reports the
    *missing* skill by name (Task 2), which is a better message than a parse
    failure on a directory nobody claimed was a skill.
    """
    write_skill(tmp_path, "tg-extract")
    (tmp_path / "tg-propose").mkdir()
    assert [s.name for s in discover(tmp_path)] == ["tg-extract"]


def test_discover_on_a_missing_directory_is_a_usage_error(tmp_path):
    with pytest.raises(UsageError):
        discover(tmp_path / "nope")


def test_a_missing_skill_file_is_a_usage_error(tmp_path):
    with pytest.raises(UsageError):
        load(tmp_path / "tg-extract" / SKILL_FILENAME)


def test_a_skill_with_no_contract_block_is_a_usage_error(tmp_path):
    path = write_skill(tmp_path, "tg-extract", contract="Just prose, no block.")
    with pytest.raises(UsageError):
        load(path)


def test_a_contract_block_that_is_not_toml_is_a_usage_error(tmp_path):
    path = write_skill(tmp_path, "tg-extract", contract="```toml\nstage = [unclosed\n```\n")
    with pytest.raises(UsageError):
        load(path)


def test_a_non_toml_fenced_block_is_not_mistaken_for_the_contract(tmp_path):
    """The block is found by its `toml` info string, not by being first. A
    SKILL.md whose Method section opens with a ```json example must still parse.
    """
    path = write_skill(
        tmp_path,
        "tg-extract",
        contract='```json\n{"stage": "wrong"}\n```\n\n' + CONTRACT,
    )
    assert load(path).contract["stage"] == "extract"


def test_expected_skill_names_are_derived_from_STAGES(tmp_path):
    """Derived, never enumerated: adding a stage must demand a skill without
    anyone remembering to edit a list. Deleting the derivation and writing the
    eight names out passes an equality test against a literal -- so the
    assertion is against STAGES itself.
    """
    names = expected_skill_names()
    assert names[-1] == ORCHESTRATOR
    assert set(names[:-1]) == {f"tg-{s}" for s in STAGES if s not in CODE_ONLY_STAGES}
    assert "tg-intake" not in names and "tg-smoke" not in names


def test_skills_dir_resolves_beside_the_module_and_honours_the_override(tmp_path, monkeypatch):
    """Where an *installed* copy looks for its skills.

    This is the assertion that pins item 1 of the plan's Spec reconciliation:
    the skills are package data beside the module, not a repo-root directory
    that ships in no wheel. It reads like a restatement of the implementation
    and is kept anyway, because the thing being pinned is a packaging decision
    that no other test can fail on.
    """
    from testgen import skills as skills_module

    assert skills_dir() == Path(skills_module.__file__).resolve().parent / "skills"
    monkeypatch.setenv("TESTGEN_SKILLS_DIR", str(tmp_path))
    assert skills_dir() == tmp_path
```

> **Implementer note.** `Path` must be imported at the top of the test file.
> Do **not** add a test asserting that the real `skills_dir()` holds every name
> `expected_skill_names()` returns — it would be red from here until Task 13
> ships the last skill, and a suite that is red for eleven tasks stops being a
> signal. Task 13 adds that test, once it can pass.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_skills_parse.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'testgen.skills'`.

- [ ] **Step 3: Write `src/testgen/skills.py`**

```python
"""Reading the skill files, and hashing the one a stage was run with.

The pipeline's producers are prompts, so the drift hazard is different in kind
from the one the schemas close: a SKILL.md can name an artifact path that does
not exist, a stage that was renamed, or a CLI subcommand spelled with an
underscore, and nothing downstream notices until a model has already been paid
to follow it. This module gives that text one machine-readable declaration --
the `## Contract` block -- and check_contract, which arrives here in Task 2, is
what holds it to the code that owns each name.

**A malformed SKILL.md is exit 2, not a finding.** It is human-authored, like
--agents and --gold: no stage produces it, so no repair prompt fixes it. A
contract that *parses* but declares something wrong is the opposite -- an
ordinary finding, because it names exactly what to edit.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from testgen.artifacts import sha256_of
from testgen.errors import UsageError
from testgen.paths import STAGES

SKILL_FILENAME = "SKILL.md"

# Stages implemented entirely in code. intake mints run ids and timestamps,
# which the design spec forbids a skill from inventing; smoke executes the
# suite. Every other stage in STAGES has a skill, and expected_skill_names
# derives the list rather than restating it -- so adding a stage demands a
# skill without anyone remembering to edit a constant.
CODE_ONLY_STAGES: frozenset[str] = frozenset({"intake", "smoke"})

# Not a stage: it dispatches them. It has no `stage` key and no `schemas`.
ORCHESTRATOR = "tg-orchestrate"

# The uniform five-section skill shape (design spec section 5), in order.
# Section 5 is the one that matters most: skills default to helpfulness, and
# confabulation under under-specification is the characteristic failure of a
# prompt pipeline.
SECTIONS: tuple[str, ...] = (
    "1. Inputs",
    "2. Output",
    "3. Method",
    "4. Invariants",
    "5. Refusal conditions",
)

_HEADING = re.compile(r"^##[ \t]+(?P<title>.+?)[ \t]*$", re.MULTILINE)
_TOML_BLOCK = re.compile(r"^```toml[ \t]*\n(?P<body>.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)


@dataclass(frozen=True)
class Skill:
    """One parsed SKILL.md: its declaration, its structure, and its text."""

    name: str
    path: Path
    contract: dict[str, Any]
    headings: tuple[str, ...]
    body: str

    def declared(self, key: str) -> list[str]:
        """A list-valued contract key, or [] if absent.

        Tolerant on purpose: an absent key is check_contract's finding to
        report by name, and raising here would turn it into exit 2.
        """
        value = self.contract.get(key, [])
        return value if isinstance(value, list) else []


def skills_dir() -> Path:
    """Directory holding the skill files.

    Package data beside this module rather than at the repository root, so an
    installed (non-editable) copy can find its own skills -- the same reason
    the schemas moved. Overridable via TESTGEN_SKILLS_DIR so a candidate skill
    set can be checked without reinstalling.
    """
    override = os.environ.get("TESTGEN_SKILLS_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "skills"


def expected_skill_names() -> tuple[str, ...]:
    """Every skill this build must ship, derived from STAGES."""
    return tuple(f"tg-{stage}" for stage in STAGES if stage not in CODE_ONLY_STAGES) + (
        ORCHESTRATOR,
    )


def skill_sha256(path: Path | str) -> str:
    """Digest of a whole SKILL.md, for manifest.stages[].skill_sha256.

    The whole file, prose included: a changed Method section changes what the
    run did, so a hash over the contract block alone would call two different
    runs comparable.
    """
    return sha256_of(path)


def load(path: Path | str) -> Skill:
    """Parse one SKILL.md, raising UsageError on anything unreadable."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UsageError(f"unreadable skill file: {path} ({exc})") from exc

    match = _TOML_BLOCK.search(text)
    if match is None:
        raise UsageError(f"{path} has no ```toml contract block")
    try:
        contract = tomllib.loads(match.group("body"))
    except tomllib.TOMLDecodeError as exc:
        raise UsageError(f"{path} has a contract block that is not valid TOML: {exc}") from exc

    headings = tuple(m.group("title") for m in _HEADING.finditer(text))
    return Skill(
        name=path.parent.name, path=path, contract=contract, headings=headings, body=text
    )


def discover(root: Path | str | None = None) -> list[Skill]:
    """Every skill under `root` (default skills_dir()), sorted by name.

    A subdirectory with no SKILL.md is skipped rather than reported: the
    missing skill is named by check_contract, which knows which names are
    required, and "tg-propose has no SKILL.md" is a better message than a
    parse failure on a directory nobody claimed was a skill.
    """
    root = Path(root) if root is not None else skills_dir()
    if not root.is_dir():
        raise UsageError(f"skills directory does not exist: {root}")
    # iterdir() on a directory that exists but cannot be read raises
    # PermissionError -- an OSError, which would escape to cli.py's generic
    # catch and become exit 1 with a finding advising a repair against a run
    # directory, for a permission problem on a prompt directory no stage wrote.
    # Every failure in this module is exit 2, so the mapping belongs here.
    try:
        children = sorted(root.iterdir())
    except OSError as exc:
        raise UsageError(f"cannot read skills directory {root}: {exc}") from exc
    return [
        load(child / SKILL_FILENAME) for child in children if (child / SKILL_FILENAME).is_file()
    ]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_skills_parse.py -q`
Expected: PASS. Then `uv run pytest -q` — the whole suite must stay green.

- [ ] **Step 5: Ship the skills as package data**

In `pyproject.toml`, extend the existing block. The comment matters — it is the
same reasoning the schemas carry, and the next reader should find it here too:

```toml
# The schemas are the contract, so they ship with the package: without this a
# wheel installs code that cannot validate anything. The skills are the
# pipeline's producers, and for the same reason: an installed copy that can
# validate and emit but cannot find its own skills is a copy that cannot run.
[tool.setuptools.package-data]
testgen = ["schema/*.json", "suite/*.py", "suite/*.sh", "skills/*/SKILL.md"]
```

- [ ] **Step 6: Verify the package data glob actually matches**

Create `src/testgen/skills/.gitkeep` so the directory exists, then run:

```bash
uv run python -c "
from testgen.skills import skills_dir
print(skills_dir(), skills_dir().is_dir())
"
```

Expected: the path under `src/testgen/skills` and `True`.

- [ ] **Step 7: `make check` and commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
git add src/testgen/skills.py src/testgen/skills/.gitkeep tests/unit/test_skills_parse.py pyproject.toml
git commit -S -s -m "feat: Parse and hash a SKILL.md's machine-readable contract

The pipeline's producers become prompts in this build, so the drift hazard
changes shape: a SKILL.md can name an artifact path, a stage, or a CLI
subcommand that does not exist, and nothing notices until a model has been
paid to follow it. The contract block is the one declaration the next task
holds against the code that owns each name.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

**Self-check before reporting DONE.** For each test above, name which of the
three weakness shapes it could be and why it is not, and **verify the claim
rather than reasoning about it** — a claim about a test has to be true the same
way the test does. The way to verify a shape-3 claim is to mutate the mechanism
and run the single test in isolation.

Worked example, because this plan got it wrong twice in a row and the second
attempt is more instructive than the first.

**First wrong answer.** It is tempting to say
`test_skill_sha256_is_the_digest_of_the_whole_file` is shape 3 on its own — that
a digest-equality assertion holds identically whether the hash covers the whole
file or only the contract block. **Check it.** Mutate `skill_sha256` to hash the
extracted block and run that one test: it fails, because the fixture's contract
block is about 117 of 384 bytes and the two digests are nothing alike. The claim
is false.

**Second wrong answer**, which is the one worth learning from: having been
corrected, this plan then kept a companion test
(`test_editing_only_the_prose_changes_the_hash`) on the revised rationale that
it "pins sensitivity to any edit." Also false. Under the same block-only
mutation *both* tests fail — and more fundamentally, a test asserting exact
equality with `hashlib.sha256(path.read_bytes())` mathematically subsumes any
"changing the bytes changes the digest" claim, because that is what a
cryptographic hash is. There is no mutation that passes the first and fails the
second. So the companion test was deleted and its intent moved into the
survivor's docstring.

The lesson generalizes past this one test: **a rationale for keeping a test is a
claim, and a claim has to be checked the same way the test does.** Two plausible
English justifications in a row were both wrong here, and each survived until
someone ran a mutation. Report the mutation you ran and its result — not the
reasoning that led you to expect it.

`test_expected_skill_names_are_derived_from_STAGES` would be shape 1 against a
literal list of eight names, which is why it asserts against `STAGES` itself.

---

## Task 2: Hold every contract declaration to the code that owns it

**Files:**
- Modify: `src/testgen/skills.py` (add `check_contract`, `check_all`)
- Modify: `src/testgen/suite/verify.py` (promote the assertion vocabulary to public)
- Modify: `src/testgen/emit.py`, `src/testgen/refs.py` (import it instead of copying it)
- Modify: `src/testgen/cli.py` (add `check-skills`, expose `subcommand_names()`)
- Modify: `src/testgen/findings.py` (docstring: add the `"skill"` layer)
- Test: `tests/unit/test_skills_contract.py`
- Test: `tests/unit/test_cli.py` (extend)

**Interfaces:**
- Consumes: everything Task 1 produced, plus `paths.RunPaths`, `paths.STAGES`, `validate.STAGE_ARTIFACTS`, `validate.ARTIFACT_SCHEMAS`, `findings.Finding`.
- Produces:
  - `verify.DATA_KINDS`, `verify.TRAJECTORY_KINDS`, `verify.ASSERTION_KINDS` (public; `ASSERTION_KINDS = DATA_KINDS + TRAJECTORY_KINDS`)
  - `skills.check_contract(skill: Skill) -> list[Finding]`
  - `skills.check_all(root: Path | None = None) -> list[Finding]`
  - `cli.subcommand_names() -> tuple[str, ...]`

**The five checks, and the exact finding each produces.** Layer is `"skill"`, artifact is the `SKILL.md` path, pointer is a JSON-Pointer-shaped path into the contract block (`/stage`, `/reads/0`, …) so the finding reads like every other one in the system.

1. **`stage`** — present and in `paths.STAGES`, unless the skill is `ORCHESTRATOR`, where it must be *absent*. Message for a wrong value: `f"declares stage {value!r}, which is not one of: {', '.join(STAGES)}"`. Message for the orchestrator declaring one: `"tg-orchestrate is not a stage: it dispatches them, so it must not declare a stage"`.
2. **`stage` matches the directory name** — `skill.name == f"tg-{stage}"`. A `SKILL.md` in `tg-propose/` declaring `stage = "score"` would be dispatched for propose and validated as score.
3. **`reads` and `writes`** — every entry is an attribute of `paths.RunPaths`. Use `hasattr(RunPaths, name)`, which covers both properties and methods and needs no instance — **and reject a name starting with `_`**, because a skill declares artifacts through the public layout API and `hasattr(RunPaths, "_instance_dir_names")` is `True`. Message: `f"names {name!r}, which is not a RunPaths attribute; declare artifacts by their RunPaths name, never as a literal path"`.

3a. **Every list-valued key is present-and-a-list *with string elements*, or reported.** `Skill.declared()` returns `[]` for a key that is present but not a list, and that tolerance is deliberate — it is what keeps `load()` from raising on something a human can edit, so the problem stays a finding at exit 1 instead of becoming a misconfigured harness at exit 2. But it means `reads = "manifest"` (a bare TOML string rather than an array) produces **zero findings**, which is the worst failure this module can have: silence from the one component whose entire job is catching declaration mistakes, on a mistake a person will actually make — TOML makes `x = "a"` and `x = ["a"]` look equally reasonable. So **check the type in `check_contract`, where findings belong, and leave `declared()` alone.** For each of `reads`, `writes`, `invokes`, `schemas`: a key present but not a list is one finding naming the key, what was found, and that an array is required, at pointer `/<key>`. Same for `stage` present but not a string. **Skip the per-element loop and the `schemas` set comparison when the type check has already fired** — one finding about the type, not a type finding plus a cascade contradicting it. The cascade is not merely noisy: with the `schemas` type check disabled, `set("claims")` iterates *characters*, so a bare string produces seven findings, six of them claiming a schema kind named `c`, `l`, `a`… An orchestrator parsing those lines would attempt a repair against nonsense, which is worse than silence.

**And check the element type, not only the container type.** `schemas = [{kind = "claims"}]` — an array of tables, a natural TOML idiom someone reaches for wanting more structure — clears `isinstance(..., list)` and then raises `TypeError: unhashable type: 'dict'` on the `set()` call. Through the CLI that reaches `cli.py`'s generic `except Exception` and surfaces as exit 1 with `[internal] .: check-skills raised TypeError`, advising the reader to run `testgen validate` and repair an artifact in a run directory — wrong tool, wrong path, for a mistake that lives in a `SKILL.md`. Validate each element is a string **before** the `set()` and report the offending element and its type. Do not wrap the `set()` in `try/except TypeError`: catching the symptom makes the finding describe a Python error instead of the contract mistake, and naming the line to edit is this module's whole job. `reads`/`writes` are already safe here because they short-circuit on `isinstance(name, str)` per element; `invokes` is safe because `in` over a tuple needs no hashability and yields an ordinary finding.

**A pattern worth carrying to every later task, because this build has now hit it twice.** Task 1 closed "the contract block is found anywhere in the file" and the identical defect survived one scope narrower, *inside* the Contract section. Task 2 closed the container type and the identical defect survived one scope narrower, at the *element* type. Both narrower cases were reachable, and neither was caught by the fix's own tests. So at every fix, ask: **what is the same mistake one scope narrower than the one I just closed?**
4. **`schemas`** — `set(schemas) == set(STAGE_ARTIFACTS[stage])`, and every entry is a key of `ARTIFACT_SCHEMAS`. Absent for the orchestrator. Two messages, so a reader knows which direction is wrong: omitted kinds → `f"omits artifact kind(s) {...}, which stage {stage!r} is gated on"`; invented kinds → `f"declares artifact kind(s) {...}, which stage {stage!r} is not gated on"`.
5. **`invokes`** — every entry is in `cli.subcommand_names()`. Message: `f"invokes {name!r}, which is not a testgen subcommand; the subcommands are: {', '.join(subcommand_names())}"`.

Plus two structural checks that are about the file rather than the contract:

6. **The five sections are present, in order.** `SECTIONS` must appear as a subsequence of `skill.headings` — a subsequence, not a prefix or an equality, so a skill may add its own extra `##` headings. A missing or out-of-order section is a finding naming which one.
7. **Section 5 is not empty.** The text between the `## 5. Refusal conditions` heading and the next `## ` heading (or EOF) must contain at least one non-blank line. §5 calls refusal conditions the most important prompt-level decision in the system; a heading with nothing under it is how that decision silently is not made.

And `check_all` adds the one check no single skill can make: **every name in `expected_skill_names()` has a skill**, and no directory under the skills root is an unrecognised skill name. Missing → a finding against `skills_dir()`; extra → a finding against the stray directory. This is the check that fires when someone adds a stage to `STAGES` and forgets the prompt.

**Import the vocabulary rather than adding a fourth copy.** `_DATA_KINDS`/`_TRAJECTORY_KINDS` are currently written out three times: `suite/verify.py:226-227`, `emit.py:38-39`, `refs.py:799-800`. `verify.py`'s copy is the authority (it is the scorer, and it is copied standalone into the container, so it may not import from the package). `emit.py` already imports `CONTRACT` and `DEFAULT_WEIGHTS` from it, so importing the kinds is free. Do this consolidation in this task, because `check_contract` becomes the fourth consumer and four copies is where they drift.

- [ ] **Step 1: Promote the vocabulary in `suite/verify.py`**

Replace lines 222–227's private names, keeping the existing comment and extending it:

```python
# The closed assertion vocabulary, split by the field each kind scores against:
# an answer kind reads `value`, a tool kind reads `tool` and `args`. Stated once
# here because _contract_problems types those fields per kind, and a second copy
# of the vocabulary is how the gate and the scorer drift apart.
#
# Public, and imported by emit.py, refs.py and skills.py rather than copied:
# this file is the scorer, so it is the authority on what can be scored. It
# cannot import *from* the package -- it is copied standalone into the task
# container and must stay stdlib-only -- so the dependency runs one way only.
DATA_KINDS = ("answer_contains", "answer_excludes", "value_equals")
TRAJECTORY_KINDS = ("tool_called", "tool_not_called")
ASSERTION_KINDS = DATA_KINDS + TRAJECTORY_KINDS
```

Then update this file's own uses: `_ANSWER_KINDS` → `DATA_KINDS`, `_TOOL_KINDS` → `TRAJECTORY_KINDS`. Grep for both names first — `verify.py` uses them in `_assertion_satisfied` and `_contract_problems`.

In `emit.py`, delete lines 38–39 and extend the existing import:

```python
from testgen.suite.verify import CONTRACT, DATA_KINDS, DEFAULT_WEIGHTS, TRAJECTORY_KINDS
```

In `refs.py`, delete lines 799–800 and add the same import at the top of the file (`refs.py` does not import from `suite.verify` today, so this is a new import line — put it with the other `testgen.` imports, and let ruff's `I` rule order it).

Both modules use the private spellings `_DATA_KINDS` / `_TRAJECTORY_KINDS` internally; rename the uses, do not alias the imports. An alias would leave the private name in the file and the next reader would not know which one is authoritative.

- [ ] **Step 2: Verify the consolidation changed no behaviour**

Run: `uv run pytest -q`
Expected: PASS, same count as before the edit (832 at the start of this plan). A tuple's contents and order are unchanged, so nothing should move. If anything fails, the two copies had already drifted — report that as a finding before continuing, because it means a live defect just surfaced.

Then prove the copies are gone:

```bash
grep -rn "_DATA_KINDS\|_TRAJECTORY_KINDS\|_ANSWER_KINDS\|_TOOL_KINDS" --include=*.py src tests | grep -v __pycache__
```

Expected: no output.

- [ ] **Step 3: Write the failing contract tests**

`tests/unit/test_skills_contract.py`:

```python
"""Every contract declaration, against the code that owns the name.

The checks here are the only mechanical grip this project has on a prompt. A
schema gates an artifact a stage wrote; nothing gates the text that told the
stage what to write, so a SKILL.md naming `world-model` (the schema kind) where
it means `world_model` (the RunPaths attribute) would be discovered by a model
at run time, after the dispatch was paid for.

Each test below mutates one key of an otherwise-valid contract, which is the
deletion-mutation dual: the fixture is valid, so a finding can only come from
the mutated key.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from testgen.cli import subcommand_names
from testgen.paths import STAGES, RunPaths
from testgen.skills import (
    ORCHESTRATOR,
    SECTIONS,
    SKILL_FILENAME,
    check_all,
    check_contract,
    expected_skill_names,
    load,
)
from testgen.validate import ARTIFACT_SCHEMAS, STAGE_ARTIFACTS

CONTRACTS: dict[str, dict[str, object]] = {
    "tg-extract": {
        "stage": "extract",
        "reads": ["manifest", "input_file"],
        "writes": ["claims"],
        "schemas": ["claims"],
        "invokes": ["validate"],
    },
    ORCHESTRATOR: {
        "reads": ["manifest"],
        "writes": ["decisions"],
        "invokes": ["validate", "check-refs"],
    },
}


def _toml(contract: dict[str, object]) -> str:
    lines = []
    for key, value in contract.items():
        if isinstance(value, str):
            lines.append(f'{key} = "{value}"')
        else:
            inner = ", ".join(f'"{v}"' for v in value)
            lines.append(f"{key} = [{inner}]")
    return "```toml\n" + "\n".join(lines) + "\n```\n"


def write_skill(root: Path, name: str, contract=None, headings=SECTIONS, refusals="Refuse.")-> Path:
    """A valid SKILL.md for `name`, with knobs for each negative case."""
    contract = CONTRACTS[name] if contract is None else contract
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"name: {name}", "description: d.", "---", "", f"# {name}", "",
             "Purpose.", "", "## Contract", "", _toml(contract)]
    for heading in headings:
        body = refusals if heading == SECTIONS[-1] else "Body."
        lines += ["", f"## {heading}", "", body]
    path = directory / SKILL_FILENAME
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def messages(findings) -> str:
    return " | ".join(f.message for f in findings)


def test_a_valid_contract_produces_no_findings(tmp_path):
    """The baseline every mutation below is measured against."""
    assert check_contract(load(write_skill(tmp_path, "tg-extract"))) == []


def test_the_orchestrator_contract_is_valid_without_a_stage(tmp_path):
    assert check_contract(load(write_skill(tmp_path, ORCHESTRATOR))) == []


def test_an_unknown_stage_is_reported(tmp_path):
    """The fixture is `tg-bogus/` declaring stage="bogus" for a specific reason.

    An unknown stage value that nevertheless satisfies `name == f"tg-{stage}"`,
    so the stage-mismatch arm of the elif chain cannot fire as a substitute.
    The obvious fixture -- tg-extract declaring stage="extraction" -- does not
    discriminate: deleting the "not in STAGES" check leaves it green, because
    "tg-extract" != "tg-extraction" and the next arm reports instead, with a
    message containing the same word this assertion searches for. That is the
    substring-of-message shape, and it survived a full mutation pass.

    The count assertion is what makes the fallthrough visible; a pointer-only
    assertion would pass against either arm.
    """
    contract = dict(CONTRACTS["tg-extract"], stage="bogus", schemas=["claims"])
    findings = check_contract(load(write_skill(tmp_path, "tg-bogus", contract)))
    assert len(findings) == 1
    assert findings[0].pointer == "/stage"
    assert "bogus" in messages(findings)


def test_a_stage_that_disagrees_with_the_directory_name_is_reported(tmp_path):
    """A SKILL.md in tg-propose/ declaring stage="score" would be dispatched for
    propose and validated as score -- the two halves of one run disagreeing about
    which stage just ran.
    """
    contract = dict(CONTRACTS["tg-extract"], stage="score", schemas=["coverage"])
    findings = check_contract(load(write_skill(tmp_path, "tg-extract", contract)))
    assert "/stage" in [f.pointer for f in findings]
    assert "tg-extract" in messages(findings) and "score" in messages(findings)


def test_the_orchestrator_may_not_declare_a_stage(tmp_path):
    contract = dict(CONTRACTS[ORCHESTRATOR], stage="reconcile")
    findings = check_contract(load(write_skill(tmp_path, ORCHESTRATOR, contract)))
    assert [f.pointer for f in findings] == ["/stage"]


@pytest.mark.parametrize("key", ["reads", "writes"])
def test_a_path_that_is_not_a_RunPaths_attribute_is_reported(tmp_path, key):
    """The schema kind is `world-model`; the RunPaths attribute is `world_model`.
    A skill that declares the former names nothing the code can resolve.
    """
    contract = dict(CONTRACTS["tg-extract"])
    contract[key] = ["world-model"]
    findings = check_contract(load(write_skill(tmp_path, "tg-extract", contract)))
    assert [f.pointer for f in findings] == [f"/{key}/0"]
    assert "world-model" in messages(findings)


@pytest.mark.parametrize("key", ["reads", "writes"])
def test_every_declared_name_is_checked_not_only_the_first(tmp_path, key):
    """Otherwise a loop that returns on its first finding would pass the test
    above while leaving every later entry unchecked.
    """
    contract = dict(CONTRACTS["tg-extract"])
    contract[key] = ["manifest", "world-model", "nope"]
    findings = check_contract(load(write_skill(tmp_path, "tg-extract", contract)))
    assert [f.pointer for f in findings] == [f"/{key}/1", f"/{key}/2"]


def test_an_omitted_artifact_kind_is_reported(tmp_path):
    """instantiate is gated on both seed and expected. A skill that names only
    the seed is the drift a subset check would wave through -- and an oracle
    nobody wrote is a scenario that emits no test.
    """
    contract = {
        "stage": "instantiate",
        "reads": ["world_model", "scenarios"],
        "writes": ["seed", "expected", "rationale"],
        "schemas": ["seed"],
        "invokes": ["validate"],
    }
    findings = check_contract(load(write_skill(tmp_path, "tg-instantiate", contract)))
    assert [f.pointer for f in findings] == ["/schemas"]
    assert "expected" in messages(findings)


def test_an_invented_artifact_kind_is_reported(tmp_path):
    contract = dict(CONTRACTS["tg-extract"], schemas=["claims", "report"])
    findings = check_contract(load(write_skill(tmp_path, "tg-extract", contract)))
    assert [f.pointer for f in findings] == ["/schemas"]
    assert "report" in messages(findings)


def test_an_omission_and_an_invention_are_reported_separately(tmp_path):
    """Two messages, not one: "omits X" and "declares Y" tell the editor which
    direction is wrong, and a single symmetric-difference message does not.
    """
    contract = dict(CONTRACTS["tg-extract"], schemas=["report"])
    findings = check_contract(load(write_skill(tmp_path, "tg-extract", contract)))
    assert len(findings) == 2
    assert {"claims", "report"} <= set(messages(findings).replace("'", " ").split())


def test_an_unknown_subcommand_is_reported(tmp_path):
    """`check_refs` with an underscore is the plausible typo: it is how the
    Python function is spelled and it is not what argparse accepts.
    """
    contract = dict(CONTRACTS["tg-extract"], invokes=["validate", "check_refs"])
    findings = check_contract(load(write_skill(tmp_path, "tg-extract", contract)))
    assert [f.pointer for f in findings] == ["/invokes/1"]
    assert "check_refs" in messages(findings)


def test_every_real_subcommand_is_accepted(tmp_path):
    """Pins the check against the CLI rather than a hand-kept list: if a
    subcommand is added and subcommand_names() does not see it, this fails.
    """
    contract = dict(CONTRACTS["tg-extract"], invokes=list(subcommand_names()))
    assert check_contract(load(write_skill(tmp_path, "tg-extract", contract))) == []


def test_a_missing_section_is_reported(tmp_path):
    without_refusals = SECTIONS[:-1]
    findings = check_contract(load(write_skill(tmp_path, "tg-extract", headings=without_refusals)))
    assert SECTIONS[-1] in messages(findings)


def test_sections_out_of_order_are_reported(tmp_path):
    """Method before Inputs reads as a skill that acts before it reads."""
    scrambled = (SECTIONS[2], SECTIONS[0], SECTIONS[1], SECTIONS[3], SECTIONS[4])
    findings = check_contract(load(write_skill(tmp_path, "tg-extract", headings=scrambled)))
    assert findings, "an out-of-order section list must be reported"


def test_extra_headings_between_the_sections_are_allowed(tmp_path):
    """A subsequence, not an equality: a skill may add its own headings."""
    with_extras = (SECTIONS[0], SECTIONS[1], "Worked example", SECTIONS[2],
                   SECTIONS[3], SECTIONS[4])
    assert check_contract(load(write_skill(tmp_path, "tg-extract", headings=with_extras))) == []


def test_an_empty_refusal_section_is_reported(tmp_path):
    """Section 5 is the most important prompt-level decision in the system. A
    heading with nothing under it is how that decision silently is not made.
    """
    findings = check_contract(load(write_skill(tmp_path, "tg-extract", refusals="")))
    assert findings, "an empty refusal-conditions section must be reported"
    assert SECTIONS[-1] in messages(findings)


def test_a_refusal_section_at_end_of_file_is_read_correctly(tmp_path):
    """The section-body slice must handle EOF, not only the next `## ` heading.
    Section 5 is last in every real skill, so an implementation that looks for a
    following heading would find every refusal section empty -- and the test
    above would pass for the wrong reason.
    """
    assert check_contract(load(write_skill(tmp_path, "tg-extract"))) == []
    path = write_skill(tmp_path, "tg-extract")
    assert path.read_text(encoding="utf-8").rstrip().endswith("Refuse.")


def test_check_all_reports_a_skill_STAGES_demands_but_the_directory_lacks(tmp_path):
    write_skill(tmp_path, "tg-extract")
    findings = check_all(tmp_path)
    missing = messages(findings)
    for name in expected_skill_names():
        if name != "tg-extract":
            assert name in missing, f"{name} must be reported missing"


def test_check_all_reports_a_directory_that_is_not_a_known_skill(tmp_path):
    for name in expected_skill_names():
        contract = CONTRACTS.get(name)
        if contract is None:
            continue
        write_skill(tmp_path, name)
    write_skill(tmp_path, "tg-extract")
    (tmp_path / "tg-extractt" / "SKILL.md").parent.mkdir()
    (tmp_path / "tg-extractt" / "SKILL.md").write_text("stray\n", encoding="utf-8")
    assert "tg-extractt" in messages(check_all(tmp_path))


def test_the_RunPaths_names_the_real_skills_use_all_exist():
    """Guards the check itself against the attribute API moving under it.

    If paths.RunPaths ever renames `coverage_latest`, this fails here rather
    than in the middle of a dispatched score stage.
    """
    for name in ("manifest", "input_file", "claims", "world_model", "scenarios",
                 "coverage_round", "coverage_latest", "seed", "expected", "rationale",
                 "verdict", "task_dir", "report", "decisions"):
        assert hasattr(RunPaths, name), name


def test_every_stage_in_STAGES_has_a_schema_entry():
    """The precondition check 4 rests on. STAGE_ARTIFACTS must be total over
    STAGES, or `STAGE_ARTIFACTS[stage]` raises KeyError inside check_contract
    and a repairable declaration becomes an exit-2 traceback.
    """
    for stage in STAGES:
        assert stage in STAGE_ARTIFACTS
        for kind in STAGE_ARTIFACTS[stage]:
            assert kind in ARTIFACT_SCHEMAS
```

- [ ] **Step 4: Run to verify they fail**

Run: `uv run pytest tests/unit/test_skills_contract.py -q`
Expected: collection error — `cannot import name 'check_contract' from 'testgen.skills'` and `cannot import name 'subcommand_names' from 'testgen.cli'`.

- [ ] **Step 5: Expose the subcommand names from `cli.py`**

**One declared source, read by both the parser and the check.** Add a module-level tuple of `(name, help)` pairs that `_build_parser` *iterates over* to create each subparser, and have `subcommand_names()` return the names from it. Then no private argparse attribute is touched and the parser and the check cannot disagree — which is the property that matters, because a second hand-kept list goes stale the first time a subcommand is added.

```python
# Every subcommand, declared once. _build_parser iterates this to create each
# subparser and subcommand_names() reads it, so a skill's `invokes` list is
# validated against the same source argparse accepts -- a SKILL.md telling a
# model to run `testgen check_refs` fails in CI rather than at run time. Walking
# parser._subparsers._group_actions would work and is a private argparse API;
# a second hand-kept list would drift. This is neither.
SUBCOMMANDS: tuple[tuple[str, str], ...] = (
    ("intake", "register inputs and mint a run"),
    ("validate", "schema-validate one stage's output"),
    ("check-refs", "cross-artifact and reachability checks"),
    ("check-skills", "check every skill's contract against the code it names"),
    ("dedupe-candidates", "propose candidate duplicate scenario pairs as JSON"),
    ("emit", "compile accepted instances into Harbor packages"),
    ("smoke", "run the emitted suite against the agent roster"),
    ("compare-gold", "recall and novelty against the authored bench tasks"),
    ("diff-runs", "per-stage stability across two runs"),
    ("sample-for-review", "write a stratified review packet for the emitted suite"),
    ("record-stage", "record a stage's model, effort, and skill hash in the manifest"),
    ("decide", "append one orchestrator decision to the run's decisions.md"),
)


def subcommand_names() -> tuple[str, ...]:
    """Every `testgen` subcommand, as argparse accepts it."""
    return tuple(name for name, _ in SUBCOMMANDS)
```

`record-stage` and `decide` are listed here even though Task 3 adds them, so the tuple is written once. If you are implementing Task 2 before Task 3, include them in `SUBCOMMANDS` and let `_build_parser` create their subparsers with the arguments Task 3 specifies — or add the two entries in Task 3 and leave them out here. Either is fine; **say which you did**, because a `SUBCOMMANDS` entry with no arguments attached would make `testgen record-stage --run X` a usage error rather than an unknown command, and the two failure modes read differently to an orchestrator.

> **Implementer note.** `_build_parser` currently configures each subparser with different arguments, so iterating a flat `(name, help)` tuple gets you the parser objects but not their arguments. The arrangement that keeps one source without contorting the code: iterate `SUBCOMMANDS` to create the subparsers into a dict keyed by name, then add each one's arguments from that dict. If you find a cleaner shape, take it and explain the choice — the requirement is one source of truth for the *names*, not a particular loop.

- [ ] **Step 6: Add the checks to `skills.py`**

```python
def _is_subsequence(needles: tuple[str, ...], haystack: tuple[str, ...]) -> bool:
    iterator = iter(haystack)
    return all(any(item == needle for item in iterator) for needle in needles)


def check_contract(skill: Skill) -> list[Finding]:
    """One skill's declaration against the code that owns each name.

    Findings, never raises: every problem here names a line a human can edit,
    which is exit 1's contract. An unreadable file is load()'s UsageError and
    exit 2, because there is nothing to name.
    """
    # Imported here rather than at module scope: cli imports skills for the
    # check-skills subcommand, so a top-level import would be circular. Same
    # pattern refs.check_report uses for smoke.
    from testgen.cli import subcommand_names
    from testgen.validate import ARTIFACT_SCHEMAS, STAGE_ARTIFACTS

    out: list[Finding] = []

    def report(pointer: str, message: str) -> None:
        out.append(Finding(skill.path, "skill", pointer, message))

    stage = skill.contract.get("stage")
    if skill.name == ORCHESTRATOR:
        if stage is not None:
            report(
                "/stage",
                f"{ORCHESTRATOR} is not a stage: it dispatches them, so it must not "
                "declare a stage",
            )
    elif stage not in STAGES:
        report("/stage", f"declares stage {stage!r}, which is not one of: {', '.join(STAGES)}")
    elif skill.name != f"tg-{stage}":
        report(
            "/stage",
            f"lives in {skill.name}/ but declares stage {stage!r}; the orchestrator "
            f"dispatches it as {skill.name} and validates it as {stage!r}",
        )

    for key in ("reads", "writes"):
        for i, name in enumerate(skill.declared(key)):
            if not isinstance(name, str) or not hasattr(RunPaths, name):
                report(
                    f"/{key}/{i}",
                    f"names {name!r}, which is not a RunPaths attribute; declare artifacts "
                    "by their RunPaths name, never as a literal path",
                )

    if skill.name != ORCHESTRATOR and stage in STAGES:
        declared = set(skill.declared("schemas"))
        required = set(STAGE_ARTIFACTS[stage])
        for kind in sorted(declared - required):
            if kind not in ARTIFACT_SCHEMAS:
                report("/schemas", f"declares artifact kind {kind!r}, which has no schema")
            else:
                report(
                    "/schemas",
                    f"declares artifact kind {kind!r}, which stage {stage!r} is not gated on",
                )
        omitted = sorted(required - declared)
        if omitted:
            report(
                "/schemas",
                f"omits artifact kind(s) {', '.join(repr(k) for k in omitted)}, which stage "
                f"{stage!r} is gated on",
            )

    known = subcommand_names()
    for i, name in enumerate(skill.declared("invokes")):
        if name not in known:
            report(
                f"/invokes/{i}",
                f"invokes {name!r}, which is not a testgen subcommand; the subcommands are: "
                f"{', '.join(known)}",
            )

    for heading in SECTIONS:
        if heading not in skill.headings:
            report("", f"has no '## {heading}' section")
    if not _is_subsequence(tuple(h for h in SECTIONS if h in skill.headings), skill.headings):
        report("", f"sections are out of order; the required order is: {', '.join(SECTIONS)}")

    refusals = SECTIONS[-1]
    # section_body is Task 1's, fence-aware and EOF-aware. Do not re-implement
    # the slice here: section 5 is last in every real skill, so a second
    # implementation that required a following heading would read every refusal
    # section as empty and this check would fire on every correct skill.
    if refusals in skill.headings and not section_body(skill, refusals).strip():
        report(
            "",
            f"'## {refusals}' is empty; a skill with no stated refusal conditions "
            "confabulates under under-specification rather than recording a gap",
        )
    return out


def check_all(root: Path | str | None = None) -> list[Finding]:
    """Every skill's contract, plus the roster check no single skill can make.

    **Recognise the directory name before loading it.** `discover()` calls
    `load()` on every directory holding a SKILL.md, and `load()` raises
    UsageError on one it cannot parse -- so calling discover() unconditionally
    means a stray directory with unparseable content aborts the whole check.
    Worse than aborting: cli.py's `check-skills` handler catches UsageError and
    returns exit 2, so a stray directory that should be an ordinary finding
    ("this is not a skill this pipeline dispatches") silently becomes a
    misconfigured harness, and every real finding in the run is discarded with
    it. A name we do not recognise is reported without being parsed.
    """
    root = Path(root) if root is not None else skills_dir()
    if not root.is_dir():
        raise UsageError(f"skills directory does not exist: {root}")
    out: list[Finding] = []
    expected = set(expected_skill_names())

    # Partition by directory name first, parse second. See the docstring:
    # load() raises on a file it cannot parse, and an unrecognised directory
    # name has nothing worth parsing -- its finding is about the name.
    present = sorted(
        child.name for child in root.iterdir() if (child / SKILL_FILENAME).is_file()
    )
    for name in present:
        if name not in expected:
            out.append(
                Finding(
                    root / name / SKILL_FILENAME,
                    "skill",
                    "",
                    f"{name} is not a skill this pipeline dispatches; the skills are: "
                    f"{', '.join(sorted(expected))}",
                )
            )
    found = [load(root / name / SKILL_FILENAME) for name in present if name in expected]
    by_name = {skill.name: skill for skill in found}
    for name in sorted(expected - set(by_name)):
        out.append(
            Finding(root, "skill", "", f"no skill named {name}, which paths.STAGES demands")
        )
    for name in sorted(set(by_name) - expected):
        out.append(
            Finding(
                by_name[name].path,
                "skill",
                "",
                f"{name} is not a skill this pipeline dispatches; the skills are: "
                f"{', '.join(sorted(expected))}",
            )
        )
    for skill in found:
        out.extend(check_contract(skill))
    return out
```

Add the imports `skills.py` now needs: `from testgen.findings import Finding` and `from testgen.paths import STAGES, RunPaths`.

- [ ] **Step 7: Add the `check-skills` subcommand**

In `_build_parser()`:

```python
    p_skills = subparsers.add_parser(
        "check-skills", help="check every skill's contract against the code it names"
    )
    p_skills.add_argument("--skills-dir", default=None, metavar="PATH")
```

In `main()`, inside the outer `try`, alongside the other handlers:

```python
        if args.command == "check-skills":
            # Its own UsageError catch, for the same reason smoke and
            # sample-for-review have one: UsageError is a ValueError and the
            # outer narrow catch deliberately excludes ValueError. A SKILL.md
            # that cannot be parsed at all is human-authored and unrepairable
            # by re-prompting, so it is exit 2.
            try:
                findings = skills.check_all(args.skills_dir)
            except UsageError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return USAGE
            return _report(findings)
```

Add `from testgen import skills` to the imports. Note the catch-all handler's
`getattr(args, "run", None) or getattr(args, "a", ".")` already covers this
subcommand, which has neither — it falls through to `"."`, which is correct: a
skill defect is not in any run directory.

- [ ] **Step 8: Extend `tests/unit/test_cli.py`**

```python
def test_check_skills_is_clean_on_the_shipped_skills():
    """The real skills directory, exercised through the CLI's exit codes.

    This is the test that fails the moment a stage is added to STAGES without a
    prompt, and it is the reason check-skills exists as a subcommand and not
    only as a pytest: the orchestrator runs it before a run.
    """
    assert main(["check-skills"]) == 0


def test_check_skills_reports_findings_at_exit_1_with_lines_on_stdout(tmp_path, capsys):
    """The exit-code contract: a 1 must never mean "no information"."""
    (tmp_path / "tg-extract").mkdir()
    (tmp_path / "tg-extract" / "SKILL.md").write_text(
        '---\nname: tg-extract\n---\n\n## Contract\n\n```toml\nstage = "nope"\n```\n',
        encoding="utf-8",
    )
    assert main(["check-skills", "--skills-dir", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert out.strip(), "exit 1 with an empty stdout is the failure mode the CLI closed"
    assert "[skill]" in out


def test_check_skills_on_a_missing_directory_is_exit_2(tmp_path, capsys):
    """A human-authored path nothing can repair by re-prompting."""
    assert main(["check-skills", "--skills-dir", str(tmp_path / "nope")]) == 2
    assert capsys.readouterr().err.startswith("error: ")


def test_check_skills_on_an_unparseable_skill_is_exit_2(tmp_path, capsys):
    """A SKILL.md with no contract block at all: same ruling as a malformed
    --agents roster. Contrast with the exit-1 test above, where the block parses
    and declares something wrong -- that names a line to edit, so it is a finding.
    """
    (tmp_path / "tg-extract").mkdir()
    (tmp_path / "tg-extract" / "SKILL.md").write_text("# no contract\n", encoding="utf-8")
    assert main(["check-skills", "--skills-dir", str(tmp_path)]) == 2
    assert capsys.readouterr().err.startswith("error: ")
```

> **Implementer note.** `test_check_skills_is_clean_on_the_shipped_skills` will
> fail until Task 13 ships the last skill, because `check_all` reports every
> missing name. **Write it in Task 13, not here.** In this task, write only the
> three `tmp_path` tests above, which are green immediately.

- [ ] **Step 9: Update `findings.py`'s layer list**

One line, in the `Finding` docstring's comment:

```python
    layer: str  # "schema" | "refs" | "invariant" | "emit" | "internal" | "recall" | "review" | "skill"
```

Check the line length: that comment will exceed 100 characters, so wrap it —
move the list into the docstring body rather than the inline comment if needed.
`make check` is the arbiter.

- [ ] **Step 10: Run everything and commit**

```bash
uv run pytest -q && uv run ruff check . && uv run ruff format --check .
git add -A
git commit -S -s -m "feat: Check every skill contract against the code that owns the name

A schema gates an artifact a stage wrote; nothing gated the text that told the
stage what to write. check-skills holds each SKILL.md's declaration to
paths.RunPaths, validate.STAGE_ARTIFACTS and the CLI's own subparser names, so
a prompt naming an artifact or a subcommand that does not exist fails in CI
rather than after a dispatch was paid for.

Also consolidates the closed assertion vocabulary onto suite/verify.py, which
had three copies before this check became the fourth consumer.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

**Self-check before reporting DONE.** Beyond the three shapes: for the section-order
check, state what input distinguishes "is a subsequence" from "is a prefix" and
confirm a test covers it. For the `schemas` check, confirm a test would fail if
the equality were relaxed to a subset — `test_an_omitted_artifact_kind_is_reported`
is that test, and if it passes with `<=` substituted for `==`, say so rather than
assuming.

---

## Task 3: The two writers the contract declares and nobody implements

**Files:**
- Modify: `src/testgen/cli.py` (add `record-stage` and `decide`)
- Modify: `src/testgen/validate.py` (add `manifest_stage_efforts()`)
- Test: `tests/unit/test_manifest_stages.py`
- Test: `tests/unit/test_validate.py` (extend, one test)

**Interfaces:**
- Consumes: `skills.skill_sha256`, `artifacts.read_json`, `artifacts.write_json`, `artifacts.append_decision`, `validate.schema_dir`, `validate.ARTIFACT_SCHEMAS`.
- Produces: `validate.manifest_stage_efforts() -> tuple[str, ...]`; two subcommands.

**Why this task exists.** §4's reproducibility hook says `manifest.json` records, per stage, model, effort, and a content hash of the `SKILL.md` used, and that "two runs are comparable only if those match". `intake` writes `"stages": {}`. Nothing has ever written into it. `stability.stage_config` reads it and `stability.comparability` gates `diff-runs`' headline verdict on it — so today two runs are called comparable because *neither* records anything, which is the strongest possible false positive: the check passes precisely because the data is absent. Same shape for `decisions.md`: `artifacts.append_decision` exists with no caller, while §5's loop says "append decision to decisions.md" and §4 calls it the run's append-only lab notebook.

**Design notes the brief must carry verbatim:**

- `record-stage` **merges** into `manifest["stages"]`, it does not replace the map. A stage re-dispatched after a repair overwrites its own entry and leaves its siblings alone.
- The effort choices come from the manifest schema, read at parser-build time, so there is no second copy of the enum. `validate.manifest_stage_efforts()` returns `tuple(schema["properties"]["stages"]["additionalProperties"]["properties"]["effort"]["enum"])`.
- `record-stage` writes through `artifacts.write_json`, so the write is atomic and the canonical form is preserved. A stage entry appended with a hand-rolled `json.dump` would reformat the whole manifest and `diff-runs` would report formatting as variance.
- `record-stage` takes `--skill PATH` and hashes it with `skills.skill_sha256`. It must **not** take a `--skill-sha256` string: a caller that can pass the digest can pass the wrong digest, and the whole point is that the recorded hash is of the file that was actually used.
- Both subcommands are exit 2 on a bad argument (a missing manifest, an unknown stage, a `--skill` that does not exist), because they are driven by the orchestrator's own arguments rather than by a stage's output. Both are exit 0 on success and print nothing except the path they wrote — matching `intake`, which prints the run root. **"Every failure is exit 2" means the catch tuples must match**: both handlers catch `(UsageError, OSError)`. A handler catching only `UsageError` lets a `decisions.md` that is a directory, or a read-only run directory, exit 1 with a fabricated finding about a repairable stage defect — a misconfigured harness masquerading as something worth the orchestrator's one repair attempt. `smoke.load_agents`' docstring records this same lesson; treat a narrower catch on either as a Critical.
- **Reject an empty or whitespace-only `--model` in `record_stage`.** The manifest schema already requires `minLength: 1`, so accepting one means exit 0 now and an exit-1 schema finding against `manifest.json` three steps later — a bad orchestrator argument reported as a malformed artifact. Enforce it where the mistake is made. `effort` needs no equivalent because argparse `choices` already bounds it; confirm that rather than assuming it.
- `decide`'s entry format is `- <YYYY-MM-DDTHH:MM:SSZ> <note>`, with the timestamp minted here. Reuse `intake`'s exact `strftime` format string so the two agree; if that means lifting it to a shared constant, lift it — do not write the format string twice.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_manifest_stages.py`:

```python
"""record-stage and decide: the manifest's stage map and the run's notebook.

Both were declared by the design spec and implemented by nobody. The manifest
one matters most: stability.comparability gates diff-runs' headline verdict on
the stage map matching, so with the map永 empty two unrelated runs compare as
comparable -- a check that passes because the data is absent.
"""

from __future__ import annotations

import re

from testgen.artifacts import read_json, write_json
from testgen.cli import main
from testgen.paths import RunPaths
from testgen.skills import skill_sha256
from testgen.stability import comparability, stage_config
from testgen.validate import manifest_stage_efforts, validate_artifact
from tests.builders import minimal_manifest


def _run(tmp_path, stages=None):
    run = RunPaths(tmp_path / "run-20260808-120000")
    manifest = minimal_manifest()
    manifest["stages"] = {} if stages is None else stages
    write_json(run.manifest, manifest)
    return run


def _skill(tmp_path, text="# tg-extract\n"):
    path = tmp_path / "SKILL.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_record_stage_writes_model_effort_and_the_skill_digest(tmp_path):
    run = _run(tmp_path)
    skill = _skill(tmp_path)
    assert main(["record-stage", "--run", str(run.root), "--stage", "extract",
                 "--model", "claude-sonnet-5", "--effort", "high",
                 "--skill", str(skill)]) == 0
    assert read_json(run.manifest)["stages"] == {
        "extract": {
            "model": "claude-sonnet-5",
            "effort": "high",
            "skill_sha256": skill_sha256(skill),
        }
    }


def test_the_recorded_digest_is_of_the_file_that_was_passed(tmp_path):
    """Not a caller-supplied string, and not a fixed placeholder. Editing the
    skill and re-recording must change the digest, or the hook records nothing
    that could ever make two runs incomparable.
    """
    run = _run(tmp_path)
    skill = _skill(tmp_path)
    argv = ["record-stage", "--run", str(run.root), "--stage", "extract",
            "--model", "m", "--effort", "high", "--skill", str(skill)]
    assert main(argv) == 0
    before = read_json(run.manifest)["stages"]["extract"]["skill_sha256"]
    skill.write_text("# tg-extract\n\nA changed Method section.\n", encoding="utf-8")
    assert main(argv) == 0
    assert read_json(run.manifest)["stages"]["extract"]["skill_sha256"] != before


def test_record_stage_merges_rather_than_replacing_the_map(tmp_path):
    """A stage re-dispatched after a repair must not erase its siblings."""
    run = _run(tmp_path, stages={
        "reconcile": {"model": "m", "effort": "high", "skill_sha256": "b" * 64}
    })
    assert main(["record-stage", "--run", str(run.root), "--stage", "extract",
                 "--model", "m", "--effort", "low", "--skill", str(_skill(tmp_path))]) == 0
    assert set(read_json(run.manifest)["stages"]) == {"reconcile", "extract"}


def test_recording_the_same_stage_twice_overwrites_only_that_entry(tmp_path):
    run = _run(tmp_path, stages={
        "reconcile": {"model": "keep-me", "effort": "high", "skill_sha256": "b" * 64}
    })
    skill = _skill(tmp_path)
    for effort in ("low", "max"):
        assert main(["record-stage", "--run", str(run.root), "--stage", "reconcile",
                     "--model", "changed", "--effort", effort, "--skill", str(skill)]) == 0
    stages = read_json(run.manifest)["stages"]
    assert stages["reconcile"] == {
        "model": "changed", "effort": "max", "skill_sha256": skill_sha256(skill)
    }


def test_the_manifest_still_validates_after_recording(tmp_path):
    """The map is schema-gated, so a writer that got the shape wrong would be
    caught by `validate --stage intake` -- but only if someone ran it. This is
    that someone.
    """
    run = _run(tmp_path)
    assert main(["record-stage", "--run", str(run.root), "--stage", "emit",
                 "--model", "claude-sonnet-5", "--effort", "medium",
                 "--skill", str(_skill(tmp_path))]) == 0
    assert validate_artifact(run.manifest, "manifest") == []


def test_recording_does_not_reformat_the_rest_of_the_manifest(tmp_path):
    """Byte stability is the reproducibility premise: diff-runs must not report
    formatting as variance. A hand-rolled json.dump would rewrite every line.
    """
    run = _run(tmp_path)
    before = run.manifest.read_text(encoding="utf-8")
    assert main(["record-stage", "--run", str(run.root), "--stage", "extract",
                 "--model", "m", "--effort", "high", "--skill", str(_skill(tmp_path))]) == 0
    after = run.manifest.read_text(encoding="utf-8")
    # Every line of the original survives except the one-line empty stages map.
    unchanged = [line for line in before.splitlines() if line.strip() != '"stages": {},']
    for line in unchanged:
        assert line in after.splitlines(), line


def test_two_runs_recording_different_skills_are_not_comparable(tmp_path):
    """The check that was passing on absent data. Before this task both runs
    had `stages: {}`, so comparability found nothing to disagree about.
    """
    a, b = _run(tmp_path / "a"), _run(tmp_path / "b")
    for run, text in ((a, "# v1\n"), (b, "# v2\n")):
        skill = run.root / "SKILL.md"
        skill.write_text(text, encoding="utf-8")
        assert main(["record-stage", "--run", str(run.root), "--stage", "extract",
                     "--model", "m", "--effort", "high", "--skill", str(skill)]) == 0
    assert stage_config(a) != stage_config(b)
    # comparability returns list[str] -- the reasons, empty when comparable.
    # Not an (ok, reasons) pair: read the signature rather than assuming, which
    # is how this assertion was written wrong the first time.
    reasons = comparability(a, b)
    assert reasons
    assert any("skill_sha256" in reason for reason in reasons)


def test_an_unknown_stage_is_exit_2(tmp_path, capsys):
    run = _run(tmp_path)
    assert main(["record-stage", "--run", str(run.root), "--stage", "extraction",
                 "--model", "m", "--effort", "high", "--skill", str(_skill(tmp_path))]) == 2


def test_a_missing_skill_file_is_exit_2(tmp_path, capsys):
    run = _run(tmp_path)
    assert main(["record-stage", "--run", str(run.root), "--stage", "extract",
                 "--model", "m", "--effort", "high",
                 "--skill", str(tmp_path / "nope.md")]) == 2
    assert capsys.readouterr().err.startswith("error: ")


def test_an_unknown_effort_is_exit_2(tmp_path):
    """argparse's choices come from the schema, so this cannot drift from it."""
    run = _run(tmp_path)
    assert main(["record-stage", "--run", str(run.root), "--stage", "extract",
                 "--model", "m", "--effort", "extreme",
                 "--skill", str(_skill(tmp_path))]) == 2


def test_the_effort_choices_are_read_from_the_schema():
    """Not a second copy of the enum. If the schema gains an effort level, the
    CLI accepts it with no code change -- and if someone adds one to the CLI
    only, the manifest fails layer 1 and this test fails first.
    """
    assert manifest_stage_efforts() == ("low", "medium", "high", "xhigh", "max")


def test_decide_appends_a_timestamped_line(tmp_path):
    run = _run(tmp_path)
    assert main(["decide", "--run", str(run.root),
                 "--note", "round 1: continue, 2 of 4 cells covered"]) == 0
    text = run.decisions.read_text(encoding="utf-8")
    assert re.fullmatch(
        r"- \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z round 1: continue, 2 of 4 cells covered\n",
        text,
    ), text


def test_decide_appends_rather_than_rewriting(tmp_path):
    """The notebook is append-only: it is the record of what the orchestrator
    decided, and a rewrite would erase the reason a run went the way it did.
    """
    run = _run(tmp_path)
    for note in ("round 1: continue", "round 2: converged"):
        assert main(["decide", "--run", str(run.root), "--note", note]) == 0
    lines = run.decisions.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0].endswith("round 1: continue")
    assert lines[1].endswith("round 2: converged")


def test_decide_on_a_missing_run_directory_is_exit_2(tmp_path):
    assert main(["decide", "--run", str(tmp_path / "nope"), "--note", "x"]) == 2


def test_decide_refuses_an_empty_note(tmp_path, capsys):
    """A blank entry in the notebook is worse than no entry: it records that a
    decision was made and not what it was.
    """
    run = _run(tmp_path)
    assert main(["decide", "--run", str(run.root), "--note", "   "]) == 2
    assert capsys.readouterr().err.startswith("error: ")
    assert not run.decisions.exists()
```

> **Implementer note.** There is a stray non-ASCII character in the module
> docstring above (`map永 empty`). Fix it to `map empty` — it is a typo in the
> plan, not a test of your attention.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_manifest_stages.py -q`
Expected: import error on `manifest_stage_efforts`, then exit-2 results from
`main` for the unknown `record-stage` subcommand once that import is satisfied.

- [ ] **Step 3: Add `manifest_stage_efforts()` to `validate.py`**

```python
@functools.cache
def _stage_efforts_for(schema_root: Path) -> tuple[str, ...]:
    schema = read_json(schema_root / ARTIFACT_SCHEMAS["manifest"])
    stage = schema["properties"]["stages"]["additionalProperties"]
    return tuple(stage["properties"]["effort"]["enum"])


def manifest_stage_efforts() -> tuple[str, ...]:
    """The effort levels manifest.stages accepts, read out of the schema.

    `record-stage` uses this as its argparse choices, so the CLI cannot accept
    an effort the manifest schema will reject -- and there is no second copy of
    the enum to keep in step.

    The cache is keyed on the schema directory, exactly as _validator_for above
    is and for the same reason: overriding TESTGEN_SCHEMA_DIR must not return a
    value built from the old one. Keyed this way, a caller trying a candidate
    schema gets the candidate's enum with no cache_clear() ceremony -- and a
    test that needed teardown discipline to be meaningful is a test that was
    documenting its own scaffolding rather than the code's guarantee.
    """
    return _stage_efforts_for(schema_dir())
```

Note `functools` is already imported in `validate.py`. **Follow `_validator_for`'s
shape rather than inventing one** — it sits a few lines above, takes
`schema_root` as a cache-key parameter, and its docstring already explains why.
An unkeyed cache here would make the `TESTGEN_SCHEMA_DIR` override a lie.

Add one test to `tests/unit/test_validate.py`:

```python
def test_manifest_stage_efforts_tracks_a_schema_override(tmp_path, monkeypatch):
    """Reads the *active* schema directory, so TESTGEN_SCHEMA_DIR moves it.

    No cache_clear() anywhere in this test, and that absence is the point: the
    cache is keyed on the schema directory the way _validator_for's is, so the
    override works on its own. A version of this test that needed teardown
    discipline to pass would have been documenting its own scaffolding rather
    than a guarantee the code makes to any caller.
    """
    from testgen.validate import ARTIFACT_SCHEMAS, manifest_stage_efforts, schema_dir

    original = read_json(schema_dir() / ARTIFACT_SCHEMAS["manifest"])
    original["properties"]["stages"]["additionalProperties"]["properties"]["effort"]["enum"] = [
        "low", "ludicrous"
    ]
    write_json(tmp_path / ARTIFACT_SCHEMAS["manifest"], original)
    monkeypatch.setenv("TESTGEN_SCHEMA_DIR", str(tmp_path))
    assert manifest_stage_efforts() == ("low", "ludicrous")


def test_the_shipped_efforts_are_still_read_after_an_override_is_removed(tmp_path, monkeypatch):
    """The other half, which the override test cannot make on its own.

    A keyed cache must return the *shipped* enum again once the override is
    gone. Without this, an implementation that keyed correctly but leaked the
    last-seen value would satisfy the test above and quietly pin every later
    caller in the process to a candidate schema.
    """
    from testgen.validate import manifest_stage_efforts

    monkeypatch.setenv("TESTGEN_SCHEMA_DIR", str(tmp_path))
    monkeypatch.delenv("TESTGEN_SCHEMA_DIR")
    assert manifest_stage_efforts() == ("low", "medium", "high", "xhigh", "max")
```

- [ ] **Step 4: Add the two subcommands**

In `_build_parser()`:

```python
    p_record = subparsers.add_parser(
        "record-stage", help="record a stage's model, effort, and skill hash in the manifest"
    )
    p_record.add_argument("--run", required=True)
    p_record.add_argument("--stage", required=True, choices=list(STAGES))
    p_record.add_argument("--model", required=True)
    p_record.add_argument("--effort", required=True, choices=list(manifest_stage_efforts()))
    p_record.add_argument("--skill", required=True, metavar="PATH")

    p_decide = subparsers.add_parser(
        "decide", help="append one orchestrator decision to the run's decisions.md"
    )
    p_decide.add_argument("--run", required=True)
    p_decide.add_argument("--note", required=True)
```

In `main()`, inside the outer `try`:

```python
        if args.command == "record-stage":
            run = _run_dir(args.run)
            # Its own UsageError catch: these arguments come from the
            # orchestrator's own invocation, not from a stage's output, so a bad
            # one is a misconfigured harness and no repair prompt helps.
            try:
                record_stage(
                    run,
                    stage=args.stage,
                    model=args.model,
                    effort=args.effort,
                    skill=Path(args.skill),
                )
            except (UsageError, OSError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return USAGE
            print(run.manifest)
            return CLEAN

        if args.command == "decide":
            run = _run_dir(args.run)
            # (UsageError, OSError), matching record-stage above. Catching only
            # UsageError makes a decisions.md that is a directory, or a
            # read-only run directory, exit 1 with a fabricated finding about a
            # repairable stage defect -- a misconfigured harness masquerading as
            # something the orchestrator should spend its one repair attempt on.
            # Both subcommands are driven by the orchestrator's own arguments,
            # so every failure in either is exit 2. smoke.load_agents' docstring
            # records this same lesson; this is the second time.
            try:
                decide(run, args.note)
            except (UsageError, OSError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return USAGE
            print(run.decisions)
            return CLEAN
```

- [ ] **Step 5: Implement the two writers**

These are logic, not CLI plumbing, so they do not belong in `cli.py`'s handler
bodies. Put them in `src/testgen/manifest.py` — a new module, because
`intake.py` is stage 0 and would be the wrong home for something the
orchestrator calls between every stage:

```python
"""Writing into a run after intake minted it: the stage map and the notebook.

Both are declared by the design spec (section 4's reproducibility hook, and
decisions.md as the run's append-only lab notebook) and had no writer. The
consequence for the stage map was not cosmetic: stability.comparability gates
diff-runs' headline verdict on the two manifests' stage maps matching, so an
always-empty map made every pair of runs comparable -- a check passing because
its input was absent.

Timestamps are minted here rather than passed in, for the reason section 4
gives: a skill that invents a timestamp makes two otherwise-identical runs diff.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from testgen.artifacts import append_decision, read_json, write_json
from testgen.errors import UsageError
from testgen.paths import STAGES, RunPaths
from testgen.skills import skill_sha256

# The one spelling of the artifact timestamp format. intake writes
# manifest.created_utc with it and decide stamps each notebook line with it;
# two copies would let a reader's parser work on one and not the other.
UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc_stamp(now: datetime | None = None) -> str:
    """Now, or a supplied aware datetime, in the artifact timestamp format."""
    if now is None:
        return datetime.now(UTC).strftime(UTC_FORMAT)
    if now.tzinfo is None:
        raise UsageError("a naive datetime cannot be stamped; pass an aware one")
    return now.astimezone(UTC).strftime(UTC_FORMAT)


def record_stage(run: RunPaths, *, stage: str, model: str, effort: str, skill: Path) -> None:
    """Merge one stage's model, effort, and skill digest into the manifest.

    Merges rather than replaces: a stage re-dispatched after a repair overwrites
    its own entry and must leave its siblings alone. Written through
    write_json, so the manifest keeps its canonical byte form -- a hand-rolled
    dump would reformat every line and diff-runs would report that as variance.

    The digest is computed from `skill` here rather than accepted as a string:
    a caller that can pass a digest can pass the wrong one, and the point of
    the hook is that the recorded hash is of the file that was actually used.
    """
    if stage not in STAGES:
        raise UsageError(f"unknown stage {stage!r}; expected one of {', '.join(STAGES)}")
    if not Path(skill).is_file():
        raise UsageError(f"skill file does not exist: {skill}")
    manifest = read_json(run.manifest)
    stages = dict(manifest.get("stages") or {})
    stages[stage] = {
        "model": model,
        "effort": effort,
        "skill_sha256": skill_sha256(skill),
    }
    manifest["stages"] = stages
    write_json(run.manifest, manifest)


def decide(run: RunPaths, note: str, *, now: datetime | None = None) -> None:
    """Append one timestamped decision to the run's decisions.md.

    An empty note is refused rather than written: a blank entry records that a
    decision was made and not what it was, which is worse than no entry.
    """
    text = note.strip()
    if not text:
        raise UsageError("a decision note cannot be empty")
    append_decision(run.decisions, f"- {utc_stamp(now)} {text}")
```

Then in `intake.py`, replace the inline `stamp.strftime("%Y-%m-%dT%H:%M:%SZ")`
with `utc_stamp(stamp)` imported from `manifest.py`, so the format string
exists once. Check for an import cycle first: `manifest.py` imports
`testgen.skills`, and `skills.py` imports `testgen.cli` *inside a function*
only, so `intake → manifest → skills` is acyclic. If ruff or the test run
disagrees, move `UTC_FORMAT`/`utc_stamp` to `artifacts.py` instead, which
neither imports.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_manifest_stages.py tests/unit/test_validate.py tests/unit/test_intake.py -q`
Expected: PASS. Then the whole suite: `uv run pytest -q`.

- [ ] **Step 7: Exercise both from the installed copy**

The CLI is the contract, so check it as a caller does, not only through `main()`:

```bash
uv pip install -e '.[dev]' >/dev/null
RUN=$(testgen intake --input tests/builders.py --runs-dir /tmp/tg-t3 \
  --target-name toy --target-interface mcp)
testgen record-stage --run "$RUN" --stage extract --model claude-sonnet-5 \
  --effort high --skill src/testgen/skills/.gitkeep
testgen validate --run "$RUN" --stage intake && echo "manifest still valid"
testgen decide --run "$RUN" --note "recorded extract by hand"
cat "$RUN/decisions.md"
rm -rf /tmp/tg-t3
```

Expected: `record-stage` prints the manifest path and exits 0; `validate` exits
0; `decide` prints the decisions path; the `cat` shows one `- <timestamp>` line.

- [ ] **Step 8: `make check` and commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
git add -A
git commit -S -s -m "feat: Record each stage's model, effort and skill hash, and the decisions log

manifest.stages and decisions.md were both declared by the design spec and
written by nobody. The stage map mattered more than it looked: comparability
gates diff-runs' headline verdict on the two maps matching, so an always-empty
map made every pair of runs comparable -- a check passing because its input
was absent.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

**Self-check before reporting DONE.** Name which of the three shapes
`test_the_recorded_digest_is_of_the_file_that_was_passed` closes and which test
it is closing it for. State explicitly whether
`test_recording_does_not_reformat_the_rest_of_the_manifest` can actually fail —
if `write_json` makes it impossible to fail, say so; a test that cannot fail is
worth keeping only if you say why, and the reason here is that it pins the
*choice* to route through `write_json` rather than the behaviour of `write_json`.

---

## Task 4: The toy world — three real inputs and a reviewable artifact set

**Files:**
- Create: `tests/fixtures/toy/api.json`, `tests/fixtures/toy/notes.md`, `tests/fixtures/toy/trace.json`
- Create: `tests/toy.py`
- Test: `tests/unit/test_toy_fixture.py`

**Interfaces:**
- Consumes: nothing but the schemas.
- Produces, for Tasks 5–14: `tests/toy.py` exporting `TOY_DIR`, `INPUT_FILES`, `ARTIFACT_IDS`, `SIDS`, and one builder per artifact — `toy_claims(artifact_id)`, `toy_world_model()`, `toy_scenarios()`, `toy_coverage()`, `toy_seed(sid)`, `toy_expected(sid)`, `toy_rationale(sid)`, `toy_verdict(sid)`, plus `build_toy_run(runs_dir) -> RunPaths` which runs **real `intake`** and then writes every hand-authored artifact.

**What this fixture is for, and what it is not.** §9 asks for "one golden end-to-end fixture: a two-capability toy world small enough to review by hand, run in CI." `tests/builders.py` is *not* that and must not be merged with it: its payloads are deliberately minimal — one capability, one scenario, no `machine:` invariant, no distractors, no `answer_excludes`, no `not_found` outcome class, no contradiction — because their job is to be mutation fodder where one changed key is the whole test. The toy world is the opposite artifact: complete enough that a human reading it can judge whether the pipeline's output would be *fair*, and run from real files through real `intake` so the digest and `stored_as` chain is exercised rather than asserted. Both stay. Say so in `tests/toy.py`'s docstring.

**What the toy world deliberately exercises** that `builders.py` does not:

| Feature | Where | Why it is here |
|---|---|---|
| Real `intake` from real files | `build_toy_run` | `manifest.inputs[].sha256`/`stored_as` and `refs.check_inputs` are exercised, not hand-written to agree |
| Three input artifacts | `tests/fixtures/toy/` | a fan-out with more than one member, so `tg-extract` runs three times and claim-id collisions are possible |
| Two capabilities × two outcome classes | `toy_world_model` | four cells, so a partially-covered matrix is expressible |
| A `not_found` outcome class | `cap-get-ticket/oc-missing` | the absence-shaped scenario, which is where `answer_excludes` is the only expressible assertion |
| Two `machine:` invariants (`count`, `unique`) | `ent-ticket` | `invariants.py` has four forms and `builders.py` uses none |
| A resolved contradiction | `toy_world_model` | `check_world_model`'s contradiction claim refs, and a world model that records rather than silently resolves |
| A distractor set per seed | `toy_seed` | §6 step 2: the step a naive generator skips, and the reason a suite all-passes |
| `value_equals` and `answer_excludes` | `toy_expected` | two of the five vocabulary kinds that no fixture in the tree currently uses |
| Two goals at different hop depths | `toy_world_model` | a goal matrix with more than one row, so `hop_depths_present` is derived from something |
| A resolved near-duplicate scenario | `scn-open-dup` | `dedupe.candidate_pairs` returns **nothing** on a fixture whose scenarios claim disjoint cells, so without this the toy world can never exercise a dedupe judgment. Verified: in the pre-score state (everything `proposed`) it yields exactly `scn-open ↔ scn-open-dup` with `identical_cells=True`; in the resolved state it yields `[]`, because `candidate_pairs` filters to `OPEN_STATUSES` and re-proposing a settled pair is how a loop fails to converge |
| **No gaps** | `toy_world_model` | a blocking gap halts the pipeline (§5), so the golden fixture must have none. The gap fixture is Task 14 |

**The duplicate is not instantiated.** `SIDS` names the four scenarios with an instance directory; `scn-open-dup` has none, because a folded scenario is never instantiated and never emitted. It is still counted correctly everywhere it matters: it does not appear in either coverage matrix (a folded scenario's credit belongs to the scenario it was folded into), it does not count against `max_scenarios` (only `proposed` and `active` do), and `refs.check_instances` never looks at it because it has no directory. All of this was verified against the real checkers: `validate --stage propose`, `validate --stage score`, `check_all`, and `emit` are all clean with it present, and `emit` produces the same four packages.

- [ ] **Step 1: Write the three input files**

`tests/fixtures/toy/api.json` — classified `mcp_tool_schema` (the filename is
`api.json` and the payload has a `tools` key, either of which is sufficient):

```json
{
  "tools": [
    {
      "name": "query_tickets",
      "description": "Read-only access to the support ticket queues.",
      "input_schema": {
        "type": "object",
        "required": ["action"],
        "properties": {
          "action": { "type": "string", "enum": ["find_tickets", "get_ticket"] },
          "queue": { "type": "string", "enum": ["billing", "shipping"] },
          "status": { "type": "string", "enum": ["open", "blocked", "closed"] },
          "ticket_id": { "type": "integer" }
        }
      },
      "returns": {
        "find_tickets": "A list of tickets matching the queue and status filters, possibly empty.",
        "get_ticket": "One ticket with its comments, ordered by position. Errors if no ticket has that id."
      }
    }
  ],
  "entities": {
    "Ticket": {
      "collection": "tickets",
      "fields": {
        "ticket_id": "integer",
        "queue": "string",
        "status": "string",
        "summary": "string",
        "comment_count": "integer"
      }
    },
    "Comment": {
      "collection": "comments",
      "fields": {
        "comment_id": "integer",
        "ticket_id": "integer",
        "position": "integer",
        "body": "string"
      }
    }
  }
}
```

`tests/fixtures/toy/notes.md` — classified `design_doc`:

```markdown
# ticketq — operator notes

`ticketq` fronts two support queues, `billing` and `shipping`. Support
engineers use it to find the ticket they need to act on and to explain why a
ticket is stuck.

## Invariants the store maintains

- `comment_count` on a ticket is always the number of comment records
  attached to it. The field is recomputed on read, so a stored value that
  disagrees is overwritten.
- `ticket_id` is unique across every queue.

## Error behaviour

`get_ticket` with an id no ticket has is an **error**, not an empty result.
Callers must handle it as a not-found condition rather than treating the
absence of fields as a ticket in an unknown state.

## What engineers actually ask

Two things, in practice. "Which ticket in this queue still needs me?" — one
lookup. And "why is this one stuck?" — find the ticket, then read its
comments, which is where the blocker is named.
```

`tests/fixtures/toy/trace.json` — classified `trace` (it carries `trace_id`):

```json
{
  "trace_id": "toy-0001",
  "spans": [
    {
      "name": "query_tickets",
      "input": { "action": "find_tickets", "queue": "shipping", "status": "open" },
      "output": []
    },
    {
      "name": "query_tickets",
      "input": { "action": "get_ticket", "ticket_id": 9999 },
      "output": {}
    }
  ]
}
```

The second span is the contradiction the world model records: `notes.md` states
that an unknown id is an error, and this trace shows an empty object coming
back. It is deliberate — do not "fix" the trace.

- [ ] **Step 2: Write the failing fixture test**

`tests/unit/test_toy_fixture.py`:

```python
"""The toy world's artifacts are valid, mutually consistent, and reviewable.

This file checks the fixture itself. The end-to-end run through the real code
is test_toy_end_to_end.py (Task 5); if the fixture is wrong, that file's
failures would blame the pipeline for a bad fixture, so the fixture gets its
own gate first.
"""

from __future__ import annotations

from testgen.invariants import evaluate
from testgen.validate import validate_artifact
from tests.toy import (
    ARTIFACT_IDS,
    INPUT_FILES,
    SIDS,
    TOY_DIR,
    toy_claims,
    toy_coverage,
    toy_expected,
    toy_scenarios,
    toy_seed,
    toy_verdict,
    toy_world_model,
)


def test_the_three_input_files_exist_and_are_distinct_kinds():
    from testgen.intake import classify

    assert sorted(p.name for p in INPUT_FILES) == ["api.json", "notes.md", "trace.json"]
    kinds = {p.name: classify(p) for p in INPUT_FILES}
    assert kinds == {
        "api.json": "mcp_tool_schema",
        "notes.md": "design_doc",
        "trace.json": "trace",
    }


def test_every_toy_artifact_validates_against_its_schema(tmp_path):
    from testgen.artifacts import write_json

    def valid(payload, kind):
        path = tmp_path / f"{kind}.json"
        write_json(path, payload)
        return validate_artifact(path, kind)

    for artifact_id in ARTIFACT_IDS:
        assert valid(toy_claims(artifact_id), "claims") == [], artifact_id
    assert valid(toy_world_model(), "world-model") == []
    assert valid(toy_scenarios(), "scenarios") == []
    assert valid(toy_coverage(), "coverage") == []
    for sid in SIDS:
        assert valid(toy_seed(sid), "seed") == [], sid
        assert valid(toy_expected(sid), "expected") == [], sid
        assert valid(toy_verdict(sid), "verdict") == [], sid


def test_the_world_model_has_four_cells_and_two_goals():
    """The shape the coverage matrices are built against. Pinned here so a later
    edit that adds an outcome class fails the fixture test rather than silently
    making the matrices wrong.
    """
    world = toy_world_model()
    cells = [
        (cap["id"], oc["id"])
        for cap in world["capabilities"]
        for oc in cap["outcome_classes"]
    ]
    assert len(cells) == 4
    assert world["denominator"] == {"version": 1, "capability_cells": 4, "goals": 2}
    assert [g["id"] for g in world["goals"]] == ["goal-locate", "goal-explain"]


def test_the_world_model_records_the_contradiction_rather_than_resolving_it_silently():
    """notes.md says an unknown id is an error; the trace shows an empty object.
    A world model that picked one and moved on is the failure the extract/
    reconcile split exists to prevent.
    """
    world = toy_world_model()
    assert len(world["contradictions"]) == 1
    contradiction = world["contradictions"][0]
    claims = {claim["id"] for aid in ARTIFACT_IDS for claim in toy_claims(aid)["claims"]}
    assert contradiction["claim_a"] in claims
    assert contradiction["claim_b"] in claims
    assert contradiction["resolution"] == "preferred_a"


def test_the_world_model_has_no_gaps():
    """A gap blocks a downstream stage and the orchestrator halts. The golden
    fixture must run to completion, so it has none by construction; the gap
    fixture is tests/fixtures/toy-gap/.
    """
    assert toy_world_model()["gaps"] == []


def test_every_claim_id_is_unique_across_the_three_claims_files():
    """check_manifest reports a claim id defined twice, because every
    world-model reference to it would resolve ambiguously. Three claims files
    is the smallest fixture in which that can happen at all.
    """
    ids = [claim["id"] for aid in ARTIFACT_IDS for claim in toy_claims(aid)["claims"]]
    assert len(ids) == len(set(ids))


def test_every_world_model_claim_reference_resolves():
    known = {claim["id"] for aid in ARTIFACT_IDS for claim in toy_claims(aid)["claims"]}
    world = toy_world_model()
    for group in ("capabilities", "entities", "actors", "goals"):
        for item in world[group]:
            for claim_id in item["claims"]:
                assert claim_id in known, f"{group}: {claim_id}"


def test_the_machine_invariants_hold_over_every_seed():
    """Two forms, `count` and `unique`, over four seeds. builders.py uses no
    machine invariant at all, so this is the first fixture that exercises
    invariants.py through refs at all.
    """
    world = toy_world_model()
    machines = [
        inv["machine"]
        for entity in world["entities"]
        for inv in entity.get("invariants", [])
        if "machine" in inv
    ]
    assert len(machines) == 2, "the fixture must carry both forms"
    for sid in SIDS:
        collections = toy_seed(sid)["collections"]
        for machine in machines:
            assert evaluate(machine, collections) == [], f"{sid}: {machine['form']}"


def test_every_machine_form_is_proven_capable_of_failing(tmp_path):
    """The dual of the test above, and it must cover **every** form.

    The test above proves the invariants hold; it does not prove they *can*
    fail. An invariant whose `collection` is mistyped returns [] from
    invariants._records() and reports nothing, so the holds-test passes
    vacuously -- verified: changing the `unique` form's collection to
    "tickets_typo" left all eighteen fixture tests green.

    Structured as a corruption per form, keyed on the form name, so adding a
    third `machine:` form without an inversion case is a visible KeyError
    rather than silent non-coverage. A per-form list is what the first version
    of this test lacked: it inverted only the `count` form, and the `unique`
    form was asserted to hold while never being shown able to fail.
    """
    world = toy_world_model()
    machines = {
        inv["machine"]["form"]: inv["machine"]
        for entity in world["entities"]
        for inv in entity.get("invariants", [])
        if "machine" in inv
    }

    def corrupt_count(collections):
        collections["tickets"][0]["comment_count"] += 1

    def corrupt_unique(collections):
        collections["tickets"][1]["ticket_id"] = collections["tickets"][0]["ticket_id"]

    corruptions = {"count": corrupt_count, "unique": corrupt_unique}
    assert set(corruptions) == set(machines), (
        "every machine form in the fixture needs a corruption proving it can fail"
    )
    for form, machine in machines.items():
        collections = toy_seed("scn-blocked")["collections"]
        assert evaluate(machine, collections) == [], f"{form} must hold before corruption"
        corruptions[form](collections)
        assert evaluate(machine, collections) != [], f"{form} did not fire on a broken seed"


def test_the_coverage_report_covers_every_cell_and_both_goals():
    coverage = toy_coverage()
    assert coverage["capability_matrix"]["total"] == 4
    assert coverage["capability_matrix"]["covered"] == 4
    assert coverage["goal_matrix"]["total"] == 2
    assert coverage["goal_matrix"]["covered"] == 2
    assert coverage["holes"] == [], "a fully covered report has nothing to justify"
    assert coverage["verdict"] == "converged"


def test_the_expected_oracles_use_the_two_vocabulary_kinds_nothing_else_does():
    """value_equals and answer_excludes. The reason this fixture exists rather
    than another minimal_expected(): two of the five kinds in the closed
    vocabulary had no fixture exercising them end to end.
    """
    from testgen.suite.verify import ASSERTION_KINDS

    used = {
        assertion["kind"]
        for sid in SIDS
        for assertion in toy_expected(sid)["assertions"]
    }
    assert {"value_equals", "answer_excludes"} <= used
    assert used <= set(ASSERTION_KINDS), "the vocabulary is closed"


def test_each_oracle_copies_its_scenario_discriminating_fact_verbatim():
    """refs.check_instances compares the two strings, because a paraphrase is
    indistinguishable from substituting an easier fact.
    """
    facts = {s["id"]: s["discriminating_fact"] for s in toy_scenarios()["scenarios"]}
    for sid in SIDS:
        assert toy_expected(sid)["discriminating_fact"] == facts[sid]


def test_every_seed_carries_at_least_one_distractor():
    """Section 6 step 2: a world containing exactly one candidate makes the test
    passable by any agent that calls the API once and reads back the only row.
    The distractor set, not hop_depth, is what sets difficulty.
    """
    for sid in SIDS:
        tickets = toy_seed(sid)["collections"]["tickets"]
        assert len(tickets) >= 2, f"{sid} has no near-miss to rule out"


def test_the_folded_scenario_is_not_instantiated():
    """SIDS is the instantiated set; ALL_SCENARIO_IDS includes the duplicate.
    Conflating them would instantiate a folded scenario, which
    refs.check_instances reports -- only a judged scenario should have an
    instance directory.
    """
    from tests.toy import ALL_SCENARIO_IDS

    assert set(SIDS) < set(ALL_SCENARIO_IDS)
    folded = set(ALL_SCENARIO_IDS) - set(SIDS)
    assert folded == {"scn-open-dup"}
    by_id = {s["id"]: s for s in toy_scenarios()["scenarios"]}
    assert by_id["scn-open-dup"]["status"] == "duplicate"
    assert by_id["scn-open-dup"]["duplicate_of"] == "scn-open"


def test_the_duplicate_pair_is_a_dedupe_candidate_before_score_rules_on_it():
    """The reason scn-open-dup exists. candidate_pairs needs a shared goal AND a
    shared cell, and the other four scenarios' cells are disjoint -- so without
    this pair the toy world yields an empty candidate list and the deterministic
    half of stage 3 is exercised against nothing.

    Measured, not predicted: exactly one pair, with identical_cells True.
    """
    from testgen.dedupe import candidate_pairs

    pre_score = []
    for scenario in toy_scenarios()["scenarios"]:
        scenario = dict(scenario)
        scenario["status"] = "proposed"
        scenario.pop("duplicate_of", None)
        pre_score.append(scenario)
    candidates = candidate_pairs(pre_score)
    assert [(c.a, c.b) for c in candidates] == [("scn-open", "scn-open-dup")]
    assert candidates[0].identical_cells is True
    assert candidates[0].shared_cells == ("cell:cap-find-tickets/oc-found",)


def test_the_resolved_pair_is_no_longer_a_candidate():
    """The other direction, and the one that matters for convergence:
    candidate_pairs filters to OPEN_STATUSES, so a settled pair is not
    re-proposed in a later round. Without this test the fixture would prove only
    that a candidate can be found, not that resolving it stops the loop
    rediscovering it.
    """
    from testgen.dedupe import candidate_pairs

    assert candidate_pairs(toy_scenarios()["scenarios"]) == []


def test_the_folded_scenario_is_credited_in_neither_matrix():
    """A folded scenario's credit belongs to the scenario it was folded into. If
    it appeared in a cell's scenario_ids, refs.check_coverage's live-credit rule
    would still pass -- scn-open is live -- so nothing would catch it, and the
    matrix would imply two tests cover a cell that ships one.
    """
    coverage = toy_coverage()
    credited = {
        sid
        for cell in coverage["capability_matrix"]["cells"]
        for sid in cell["scenario_ids"]
    } | {
        sid for row in coverage["goal_matrix"]["rows"] for sid in row["scenario_ids"]
    }
    assert "scn-open-dup" not in credited


def test_the_open_scenario_count_stays_within_the_manifest_cap():
    """max_scenarios counts proposed and active only, so adding the duplicate
    must not consume cap. build_toy_run passes max_scenarios=8 and there are
    four live scenarios; this pins that the duplicate is genuinely free.
    """
    from testgen.refs import OPEN_STATUSES

    live = [s for s in toy_scenarios()["scenarios"] if s["status"] in OPEN_STATUSES]
    assert len(live) == 4
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/unit/test_toy_fixture.py -q`
Expected: `ModuleNotFoundError: No module named 'tests.toy'`.

- [ ] **Step 4: Write `tests/toy.py`**

```python
"""The golden toy world: two capabilities, four cells, four scenarios.

Section 9 asks for "one golden end-to-end fixture: a two-capability toy world
small enough to review by hand, run in CI". This is it, and it is deliberately
*not* a consolidation of tests/builders.py. Those payloads are minimal so that
one changed key is the whole test -- mutation fodder. This world is the opposite
artifact: complete enough that a person reading it can judge whether the
pipeline's output would be fair, and built from real files through real intake
so the digest and stored_as chain is exercised rather than hand-written to
agree. Keep both.

The world it describes: `ticketq`, two support queues, one read-only tool with
two actions. Every seed below carries near-misses on purpose -- a ticket that
is open in the wrong queue, a ticket with a confusingly similar summary --
because a world with exactly one candidate row is passable by any agent that
calls the API once, which is how an all-pass suite happens.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from testgen.artifacts import write_json
from testgen.intake import intake
from testgen.paths import RunPaths

TOY_DIR = Path(__file__).resolve().parent / "fixtures" / "toy"

# In the order intake registers them, which fixes the artifact ids below.
INPUT_FILES: tuple[Path, ...] = (
    TOY_DIR / "api.json",
    TOY_DIR / "notes.md",
    TOY_DIR / "trace.json",
)

# What intake.slug makes of each filename. Asserted in test_toy_end_to_end
# against the manifest intake actually wrote, rather than trusted here.
ARTIFACT_IDS: tuple[str, ...] = ("api-json", "notes-md", "trace-json")

# The scenarios with an instance directory. Deliberately narrower than
# ALL_SCENARIO_IDS below, which also holds the folded scn-open-dup: a duplicate
# is never instantiated, so iterating this set is what keeps seeds and oracles
# off it.
SIDS: tuple[str, ...] = ("scn-open", "scn-empty", "scn-blocked", "scn-missing")


def _claim(cid, kind, statement, artifact_id, locator, confidence, derivation, quote=None):
    evidence: dict[str, Any] = {"artifact_id": artifact_id, "locator": locator}
    if quote is not None:
        evidence["quote"] = quote
    return {
        "id": cid,
        "kind": kind,
        "statement": statement,
        "evidence": [evidence],
        "confidence": confidence,
        "derivation": derivation,
    }


_CLAIMS: dict[str, list[dict[str, Any]]] = {
    "api-json": [
        _claim("clm-api-001", "capability", "query_tickets supports action=find_tickets",
               "api-json", "#/tools/0/input_schema/properties/action/enum/0", "high", "stated"),
        _claim("clm-api-002", "capability", "query_tickets supports action=get_ticket",
               "api-json", "#/tools/0/input_schema/properties/action/enum/1", "high", "stated"),
        _claim("clm-api-003", "entity",
               "A ticket carries ticket_id, queue, status, summary and comment_count",
               "api-json", "#/entities/Ticket/fields", "high", "stated"),
        _claim("clm-api-004", "entity",
               "A comment carries comment_id, ticket_id, position and body",
               "api-json", "#/entities/Comment/fields", "high", "stated"),
        _claim("clm-api-005", "outcome_class",
               "find_tickets returns a possibly-empty list of matching tickets",
               "api-json", "#/tools/0/returns/find_tickets", "high", "stated"),
    ],
    "notes-md": [
        _claim("clm-notes-001", "actor", "Support engineers triage the two queues",
               "notes-md", "#operator-notes", "medium", "inferred"),
        _claim("clm-notes-002", "goal",
               "An engineer locates the ticket that needs action, or establishes it does not exist",
               "notes-md", "#what-engineers-actually-ask", "medium", "inferred"),
        _claim("clm-notes-003", "goal", "An engineer explains why a ticket is stuck",
               "notes-md", "#what-engineers-actually-ask", "medium", "inferred"),
        _claim("clm-notes-004", "outcome_class",
               "get_ticket with an id no ticket has is an error, not an empty result",
               "notes-md", "#error-behaviour", "high", "stated",
               quote="`get_ticket` with an id no ticket has is an **error**, not an empty result."),
        _claim("clm-notes-005", "invariant",
               "comment_count equals the number of comment records on the ticket",
               "notes-md", "#invariants-the-store-maintains", "high", "stated"),
        _claim("clm-notes-006", "invariant", "ticket_id is unique across every queue",
               "notes-md", "#invariants-the-store-maintains", "high", "stated"),
    ],
    "trace-json": [
        _claim("clm-trace-001", "outcome_class",
               "find_tickets returned an empty list for a queue with no matching tickets",
               "trace-json", "#/spans/0/output", "high", "reverse_engineered"),
        _claim("clm-trace-002", "outcome_class",
               "get_ticket on an unknown id returned an empty object rather than an error",
               "trace-json", "#/spans/1/output", "medium", "reverse_engineered"),
    ],
}


def toy_claims(artifact_id: str, **over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "artifact_id": artifact_id,
        "claims": [dict(claim) for claim in _CLAIMS[artifact_id]],
    }
    payload.update(over)
    return payload


def toy_world_model(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "target": {"name": "ticketq", "interface": "mcp"},
        "capabilities": [
            {
                "id": "cap-find-tickets",
                "operation": "query_tickets.find_tickets",
                "binding": {"tool": "query_tickets", "fixed_args": {"action": "find_tickets"}},
                "params": [
                    {"name": "queue", "type": "string", "required": True},
                    {"name": "status", "type": "string", "required": False},
                ],
                "outcome_classes": [
                    {"id": "oc-found", "kind": "success",
                     "description": "one or more tickets match the filters"},
                    {"id": "oc-none", "kind": "empty",
                     "description": "no ticket matches the filters"},
                ],
                "claims": ["clm-api-001", "clm-api-005", "clm-trace-001"],
                "confidence": "high",
            },
            {
                "id": "cap-get-ticket",
                "operation": "query_tickets.get_ticket",
                "binding": {"tool": "query_tickets", "fixed_args": {"action": "get_ticket"}},
                "params": [{"name": "ticket_id", "type": "integer", "required": True}],
                "outcome_classes": [
                    {"id": "oc-detail", "kind": "success",
                     "description": "the ticket and its comments, ordered by position"},
                    {"id": "oc-missing", "kind": "not_found",
                     "description": "no ticket has that id, which is an error"},
                ],
                "claims": ["clm-api-002", "clm-notes-004"],
                "confidence": "high",
            },
        ],
        "entities": [
            {
                "id": "ent-ticket",
                "name": "Ticket",
                "collection": "tickets",
                "fields": [
                    {"name": "ticket_id", "type": "integer"},
                    {"name": "queue", "type": "string"},
                    {"name": "status", "type": "string"},
                    {"name": "summary", "type": "string"},
                    {"name": "comment_count", "type": "integer"},
                ],
                "relations": [
                    {"name": "comments", "target_entity_id": "ent-comment",
                     "cardinality": "many"}
                ],
                "invariants": [
                    {
                        "id": "inv-comment-count",
                        "statement": "comment_count is the number of comments on the ticket",
                        "machine": {
                            "form": "count",
                            "collection": "tickets",
                            "field": "comment_count",
                            "of": "comments",
                            "local_key": "ticket_id",
                            "foreign_key": "ticket_id",
                        },
                    },
                    {
                        "id": "inv-ticket-id-unique",
                        "statement": "ticket_id is unique across every queue",
                        "machine": {
                            "form": "unique",
                            "collection": "tickets",
                            "field": "ticket_id",
                        },
                    },
                ],
                "claims": ["clm-api-003", "clm-notes-005", "clm-notes-006"],
            },
            {
                "id": "ent-comment",
                "name": "Comment",
                "collection": "comments",
                "fields": [
                    {"name": "comment_id", "type": "integer"},
                    {"name": "ticket_id", "type": "integer"},
                    {"name": "position", "type": "integer"},
                    {"name": "body", "type": "string"},
                ],
                "claims": ["clm-api-004"],
            },
        ],
        "actors": [
            {"id": "act-support", "name": "Support engineer", "claims": ["clm-notes-001"]}
        ],
        "goals": [
            {
                "id": "goal-locate",
                "actor_id": "act-support",
                "statement": "Locate the ticket that needs action, or establish that it does not exist",
                "expected_hop_depths": [1],
                "claims": ["clm-notes-002"],
            },
            {
                "id": "goal-explain",
                "actor_id": "act-support",
                "statement": "Explain why a ticket is stuck",
                "expected_hop_depths": [2],
                "claims": ["clm-notes-003"],
            },
        ],
        "contradictions": [
            {
                "id": "con-missing-semantics",
                "claim_a": "clm-notes-004",
                "claim_b": "clm-trace-002",
                "nature": (
                    "the operator notes state that get_ticket on an unknown id is an error; "
                    "the captured trace shows an empty object returned instead"
                ),
                "resolution": "preferred_a",
                "rationale": (
                    "the notes describe the current contract and the trace is one captured "
                    "call that predates it, so oc-missing is modelled as an error; recorded "
                    "rather than dropped because a scenario built on the trace's behaviour "
                    "would be labelled against a world the target no longer has"
                ),
            }
        ],
        "gaps": [],
        "denominator": {"version": 1, "capability_cells": 4, "goals": 2},
    }
    payload.update(over)
    return payload
```

> **Implementer note.** The `goal-locate` statement line above is 101 characters
> and will fail ruff. Wrap it with implicit string concatenation, matching the
> style used for `nature` and `rationale` just below it.

- [ ] **Step 5: Add the scenarios, coverage, seeds, oracles and verdicts**

Continuing `tests/toy.py`. The four scenarios and the coverage report that
summarizes them:

```python
_SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "scn-open",
        "round": 1,
        "goal_id": "goal-locate",
        "actor_id": "act-support",
        "title": "Find the open billing ticket",
        "user_intent": "Which ticket in the billing queue is still open?",
        "hop_depth": 1,
        "capability_refs": [
            {"capability_id": "cap-find-tickets", "outcome_class_id": "oc-found"}
        ],
        "discriminating_fact": "exactly one billing ticket has status open",
        "status": "active",
        "provenance": {
            "hole_refs": ["cell:cap-find-tickets/oc-found"],
            "claim_ids": ["clm-api-001", "clm-api-005"],
            "round": 1,
        },
    },
    {
        "id": "scn-empty",
        "round": 1,
        "goal_id": "goal-locate",
        "actor_id": "act-support",
        "title": "Report that the shipping queue is quiet",
        "user_intent": "Is anything blocked in the shipping queue right now?",
        "hop_depth": 1,
        "capability_refs": [
            {"capability_id": "cap-find-tickets", "outcome_class_id": "oc-none"}
        ],
        "discriminating_fact": "no shipping ticket has status blocked",
        "status": "active",
        "provenance": {
            "hole_refs": ["cell:cap-find-tickets/oc-none"],
            "claim_ids": ["clm-trace-001"],
            "round": 1,
        },
    },
    {
        "id": "scn-blocked",
        "round": 1,
        "goal_id": "goal-explain",
        "actor_id": "act-support",
        "title": "Explain what the blocked billing ticket is waiting on",
        "user_intent": "One billing ticket is blocked. Which one, and what is it waiting on?",
        "hop_depth": 2,
        "capability_refs": [
            {"capability_id": "cap-find-tickets", "outcome_class_id": "oc-found"},
            {"capability_id": "cap-get-ticket", "outcome_class_id": "oc-detail"},
        ],
        "discriminating_fact": (
            "exactly one billing ticket is blocked, and only its last comment names the blocker"
        ),
        "status": "active",
        "provenance": {
            "hole_refs": ["cell:cap-get-ticket/oc-detail", "goal:goal-explain"],
            "claim_ids": ["clm-api-002", "clm-api-004"],
            "round": 1,
        },
    },
    {
        "id": "scn-missing",
        "round": 1,
        "goal_id": "goal-locate",
        "actor_id": "act-support",
        "title": "Establish that a ticket does not exist",
        "user_intent": "What is the status of ticket 4109?",
        "hop_depth": 1,
        "capability_refs": [
            {"capability_id": "cap-get-ticket", "outcome_class_id": "oc-missing"}
        ],
        "discriminating_fact": "no ticket with id 4109 exists in either queue",
        "status": "active",
        "provenance": {
            "hole_refs": ["cell:cap-get-ticket/oc-missing"],
            "claim_ids": ["clm-notes-004"],
            "round": 1,
        },
    },
    # Folded into scn-open by the score stage: same goal, the same single cell,
    # and the same discriminating fact behind different wording. Present because
    # dedupe.candidate_pairs returns nothing at all on a scenario set whose
    # cells are disjoint -- without this pair the toy world could not exercise a
    # dedupe judgment, and the deterministic half of stage 3 would be untested
    # against any real input. It is never instantiated and never emitted, which
    # is what `duplicate` means.
    {
        "id": "scn-open-dup",
        "round": 1,
        "goal_id": "goal-locate",
        "actor_id": "act-support",
        "title": "Which billing ticket still needs attention",
        "user_intent": "Is there a billing ticket nobody has closed yet?",
        "hop_depth": 1,
        "capability_refs": [
            {"capability_id": "cap-find-tickets", "outcome_class_id": "oc-found"}
        ],
        "discriminating_fact": "exactly one billing ticket has status open",
        "status": "duplicate",
        "duplicate_of": "scn-open",
        "provenance": {
            "hole_refs": ["cell:cap-find-tickets/oc-found"],
            "claim_ids": ["clm-api-001"],
            "round": 1,
        },
    },
]

# Every scenario in 02-scenarios.json, including the folded one. SIDS above is
# the narrower set -- the scenarios with an instance directory -- and the two
# must not be conflated: iterating ALL_SCENARIO_IDS to build seeds would
# instantiate a duplicate, which refs.check_instances reports.
ALL_SCENARIO_IDS: tuple[str, ...] = tuple(s["id"] for s in _SCENARIOS)


def toy_scenarios(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "denominator_version": 1,
        "scenarios": [dict(s) for s in _SCENARIOS],
    }
    payload.update(over)
    return payload


def toy_coverage(**over: Any) -> dict[str, Any]:
    """Full coverage of four cells and two goals, so holes is empty.

    A hole here would have to name a covered row, which refs.check_coverage
    reports in both directions -- so "fully covered" and "no holes" are one
    statement, not two.
    """
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "round": 1,
        "denominator_version": 1,
        "capability_matrix": {
            "cells": [
                {"capability_id": "cap-find-tickets", "outcome_class_id": "oc-found",
                 "scenario_ids": ["scn-open", "scn-blocked"], "covered": True},
                {"capability_id": "cap-find-tickets", "outcome_class_id": "oc-none",
                 "scenario_ids": ["scn-empty"], "covered": True},
                {"capability_id": "cap-get-ticket", "outcome_class_id": "oc-detail",
                 "scenario_ids": ["scn-blocked"], "covered": True},
                {"capability_id": "cap-get-ticket", "outcome_class_id": "oc-missing",
                 "scenario_ids": ["scn-missing"], "covered": True},
            ],
            "covered": 4,
            "total": 4,
            "pct": 1.0,
        },
        "goal_matrix": {
            "rows": [
                {"goal_id": "goal-locate",
                 "scenario_ids": ["scn-open", "scn-empty", "scn-missing"],
                 "hop_depths_present": [1], "hop_depths_expected": [1], "covered": True},
                {"goal_id": "goal-explain", "scenario_ids": ["scn-blocked"],
                 "hop_depths_present": [2], "hop_depths_expected": [2], "covered": True},
            ],
            "covered": 2,
            "total": 2,
            "pct": 1.0,
        },
        "holes": [],
        "progress": {"new_cells_this_round": 4, "rounds_without_progress": 0},
        "verdict": "converged",
    }
    payload.update(over)
    return payload
```

- [ ] **Step 6: Add the four seeds**

Each seed's `comment_count` values satisfy `inv-comment-count` and each
`ticket_id` is unique, by construction. Every seed carries at least one
near-miss.

```python
_SEEDS: dict[str, dict[str, Any]] = {
    # One open billing ticket. Distractors: a closed billing ticket, and an
    # open ticket in the wrong queue -- so "the open one" is not answerable by
    # reading back the only row.
    "scn-open": {
        "tickets": [
            {"ticket_id": 4101, "queue": "billing", "status": "closed",
             "summary": "Duplicate invoice raised twice", "comment_count": 0},
            {"ticket_id": 4102, "queue": "billing", "status": "open",
             "summary": "Invoice export fails for EU accounts", "comment_count": 1},
            {"ticket_id": 4103, "queue": "shipping", "status": "open",
             "summary": "Label printer offline in DC2", "comment_count": 0},
        ],
        "comments": [
            {"comment_id": 1, "ticket_id": 4102, "position": 1,
             "body": "Reproduced on staging with an EU billing address."},
        ],
    },
    # Nothing blocked in shipping. Distractors: a *billing* ticket that is
    # blocked, and a shipping ticket that is open -- both near-misses on one
    # filter each, so an agent that drops either filter answers wrongly.
    "scn-empty": {
        "tickets": [
            {"ticket_id": 4102, "queue": "billing", "status": "blocked",
             "summary": "Invoice export fails for EU accounts", "comment_count": 1},
            {"ticket_id": 4103, "queue": "shipping", "status": "open",
             "summary": "Label printer offline in DC2", "comment_count": 0},
        ],
        "comments": [
            {"comment_id": 1, "ticket_id": 4102, "position": 1,
             "body": "Waiting on the payments team."},
        ],
    },
    # One blocked billing ticket whose blocker is named only in its *last*
    # comment. Distractors: a billing ticket with a near-identical summary that
    # is not blocked, and a blocked ticket in the wrong queue.
    "scn-blocked": {
        "tickets": [
            {"ticket_id": 4102, "queue": "billing", "status": "blocked",
             "summary": "Invoice export fails for EU accounts", "comment_count": 2},
            {"ticket_id": 4103, "queue": "billing", "status": "open",
             "summary": "Invoice export slow for EU accounts", "comment_count": 0},
            {"ticket_id": 4104, "queue": "shipping", "status": "blocked",
             "summary": "Label printer offline in DC2", "comment_count": 1},
        ],
        "comments": [
            {"comment_id": 1, "ticket_id": 4102, "position": 1,
             "body": "Reproduced on staging with an EU billing address."},
            {"comment_id": 2, "ticket_id": 4102, "position": 2,
             "body": "Blocked on PAY-77 until the payments team ships the fix."},
            {"comment_id": 3, "ticket_id": 4104, "position": 1,
             "body": "Replacement printer ordered."},
        ],
    },
    # No ticket 4109 anywhere. Distractors: two tickets whose ids bracket it,
    # so an agent that fabricates rather than reports absence has something
    # plausible to fabricate from.
    "scn-missing": {
        "tickets": [
            {"ticket_id": 4102, "queue": "billing", "status": "open",
             "summary": "Invoice export fails for EU accounts", "comment_count": 0},
            {"ticket_id": 4110, "queue": "billing", "status": "closed",
             "summary": "Invoice export fixed for EU accounts", "comment_count": 0},
        ],
        "comments": [],
    },
}


def toy_seed(scenario_id: str, **over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "collections": {
            name: [dict(record) for record in records]
            for name, records in _SEEDS[scenario_id].items()
        },
    }
    payload.update(over)
    return payload
```

- [ ] **Step 7: Add the four oracles, the rationales and the verdicts**

**The `answer_excludes` grounding rule is the subtle part and the brief must
state it.** `refs._check_reachability` requires an `answer_excludes` pointer to
resolve to *nothing*: the seed must not contain what the assertion says it
lacks. So an exclusion can never name a value that is present — excluding a
distractor that exists is not expressible this way, and is expressed instead by
`value_equals`, which requires the answer to carry the right token. The
exclusions below therefore ground in the *absence of a further record*, which is
exactly the `log-does-not-say` shape §4 says this field exists for. Each
`rationale` says so in words, because a reviewer reading the packet has to be
able to tell a deliberate absence from a broken pointer.

```python
_ORACLES: dict[str, dict[str, Any]] = {
    "scn-open": {
        "answer_reference": "Ticket 4102 is the one open billing ticket.",
        "assertions": [
            {"kind": "value_equals", "target": "answer", "value": "4102",
             "rationale": "the open billing ticket's id, as a standalone token: an answer "
                          "naming 41020 or 14102 has not identified this ticket",
             "grounded_in": {"seed_pointer": "/collections/tickets/1/ticket_id"}},
            {"kind": "tool_called", "target": "query_tickets.find_tickets",
             "value": "at least once",
             "rationale": "the queue must be queried rather than guessed at",
             "capability_id": "cap-find-tickets"},
        ],
        "trajectory": {"match": "subset", "operations": [
            {"capability_id": "cap-find-tickets", "args": {"queue": "billing"}}
        ]},
    },
    "scn-empty": {
        "answer_reference": "Nothing in the shipping queue is blocked.",
        "assertions": [
            {"kind": "answer_excludes", "target": "answer",
             "value": "Label printer offline in DC2",
             "rationale": "the shipping queue holds exactly one ticket and it is open, so "
                          "there is no blocked shipping ticket to describe; the pointer "
                          "resolves to nothing because the seed has no second shipping "
                          "record, and naming this ticket's summary is fabrication",
             "grounded_in": {"seed_pointer": "/collections/tickets/2"}},
            {"kind": "tool_called", "target": "query_tickets.find_tickets",
             "value": "at least once",
             "rationale": "an empty result must be established by querying, not assumed",
             "capability_id": "cap-find-tickets"},
        ],
        "trajectory": {"match": "subset", "operations": [
            {"capability_id": "cap-find-tickets",
             "args": {"queue": "shipping", "status": "blocked"}}
        ]},
    },
    "scn-blocked": {
        "answer_reference": "Ticket 4102 is blocked on PAY-77.",
        "assertions": [
            {"kind": "value_equals", "target": "answer", "value": "4102",
             "rationale": "the blocked ticket's id, and not 4103's, which differs only in "
                          "its summary wording",
             "grounded_in": {"seed_pointer": "/collections/tickets/0/ticket_id"}},
            {"kind": "answer_contains", "target": "answer", "value": "PAY-77",
             "rationale": "the blocker is named only in the ticket's last comment, so an "
                          "answer carrying it proves the comments were read",
             "grounded_in": {"seed_pointer": "/collections/comments/1/body"}},
            {"kind": "tool_called", "target": "query_tickets.get_ticket",
             "value": "at least once",
             "rationale": "the blocker is not in the find_tickets result, so the detail "
                          "call is the second hop this scenario claims",
             "capability_id": "cap-get-ticket"},
        ],
        "trajectory": {"match": "subset", "operations": [
            {"capability_id": "cap-find-tickets",
             "args": {"queue": "billing", "status": "blocked"}},
            {"capability_id": "cap-get-ticket", "args": {"ticket_id": 4102}},
        ]},
    },
    "scn-missing": {
        "answer_reference": "There is no ticket 4109.",
        "assertions": [
            {"kind": "answer_excludes", "target": "answer",
             "value": "Invoice export fails for EU accounts",
             "rationale": "the seed holds two tickets, 4102 and 4110, and neither is 4109; "
                          "the pointer resolves to nothing because there is no third "
                          "record, so attributing a neighbouring ticket's summary to 4109 "
                          "is the fabrication this test exists to catch",
             "grounded_in": {"seed_pointer": "/collections/tickets/2"}},
            {"kind": "tool_called", "target": "query_tickets.get_ticket",
             "value": "at least once",
             "rationale": "absence must be established by looking, not by assuming",
             "capability_id": "cap-get-ticket"},
        ],
        "trajectory": {"match": "subset", "operations": [
            {"capability_id": "cap-get-ticket", "args": {"ticket_id": 4109}}
        ]},
    },
}

_RATIONALES: dict[str, str] = {
    "scn-open": "Distractors: 4101 is billing but closed; 4103 is open but in shipping. "
                "An agent must apply both filters.",
    "scn-empty": "Distractors: 4102 is blocked but in billing; 4103 is in shipping but "
                 "open. Dropping either filter yields a non-empty answer.",
    "scn-blocked": "Distractors: 4103's summary differs from 4102's by one word and it is "
                   "not blocked; 4104 is blocked but in shipping. The blocker is in the "
                   "second comment only, so an agent that reads the first stops short.",
    "scn-missing": "Distractors: 4102 and 4110 bracket the requested 4109, and 4110's "
                   "summary reads as a resolution of 4102's, so a fabricated answer has "
                   "plausible material to draw on.",
}


def toy_expected(scenario_id: str, **over: Any) -> dict[str, Any]:
    """The oracle, with the scenario's discriminating_fact copied verbatim.

    Verbatim because refs.check_instances compares the two strings: a paraphrase
    is indistinguishable from substituting an easier fact, which is the exact
    move the field exists to prevent.
    """
    scenario = next(s for s in _SCENARIOS if s["id"] == scenario_id)
    oracle = _ORACLES[scenario_id]
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "scenario_id": scenario_id,
        "discriminating_fact": scenario["discriminating_fact"],
        "answer_reference": oracle["answer_reference"],
        "assertions": [dict(a) for a in oracle["assertions"]],
        "trajectory": dict(oracle["trajectory"]),
        "completion": {"status": "ok", "nonempty_answer": True},
    }
    payload.update(over)
    return payload


def toy_rationale(scenario_id: str) -> str:
    """The reviewer-facing note section 6 step 6 requires.

    Its whole job is to let a reviewer judge fairness without reverse-
    engineering the seed, so it names the distractors and why each is a
    near-miss.
    """
    scenario = next(s for s in _SCENARIOS if s["id"] == scenario_id)
    return (
        f"# {scenario['title']}\n\n"
        f"**Discriminating fact:** {scenario['discriminating_fact']}\n\n"
        f"**Distractor set.** {_RATIONALES[scenario_id]}\n"
    )


def toy_verdict(scenario_id: str, **over: Any) -> dict[str, Any]:
    """An accepting adversary whose call count matches the claimed hop depth.

    Matching rather than lower: refs.check_verdicts requires the
    difficulty_overstated flag when the adversary beats the claim, and a golden
    fixture that needed the flag would be asserting a defect is tolerated
    rather than that a clean run is clean.
    """
    scenario = next(s for s in _SCENARIOS if s["id"] == scenario_id)
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "scenario_id": scenario_id,
        "uniquely_determined": True,
        "derivable_without_guessing": True,
        "minimum_tool_calls_found": scenario["hop_depth"],
        "verdict": "accept",
        "notes": (
            "answered independently from the seed and matched the oracle; the distractors "
            "rule out every second reading I could construct"
        ),
    }
    payload.update(over)
    return payload


def build_toy_run(runs_dir: Path, **intake_kwargs: Any) -> RunPaths:
    """Mint a run with real intake, then write every hand-authored artifact.

    intake is real rather than simulated so the manifest's sha256, stored_as and
    the 00-inputs/ copies are produced by the code that produces them in a real
    run -- refs.check_inputs re-hashes those bytes, and a hand-written digest
    would only ever satisfy a check that was not looking.
    """
    run = intake(
        inputs=list(INPUT_FILES),
        runs_dir=Path(runs_dir),
        target_name="ticketq",
        target_interface="mcp",
        max_rounds=intake_kwargs.pop("max_rounds", 2),
        max_scenarios=intake_kwargs.pop("max_scenarios", 8),
        **intake_kwargs,
    )
    for artifact_id in ARTIFACT_IDS:
        write_json(run.claims(artifact_id), toy_claims(artifact_id))
    write_json(run.world_model, toy_world_model())
    write_json(run.scenarios, toy_scenarios())
    write_json(run.coverage_round(1), toy_coverage())
    write_json(run.coverage_latest, toy_coverage())
    for sid in SIDS:
        write_json(run.seed(sid), toy_seed(sid))
        write_json(run.expected(sid), toy_expected(sid))
        run.rationale(sid).write_text(toy_rationale(sid), encoding="utf-8")
        write_json(run.verdict(sid), toy_verdict(sid))
    return run
```

- [ ] **Step 8: Run the fixture tests**

Run: `uv run pytest tests/unit/test_toy_fixture.py -q`
Expected: PASS. Every failure here is a fixture defect — read the finding, fix
the fixture, do not relax the test. In particular:
- a `seed` schema failure means a collection name or a field type is wrong;
- an `expected` schema failure on an assertion usually means a data kind carries
  `capability_id` or a tool kind carries `grounded_in`, which the schema forbids
  per kind;
- `test_the_machine_invariants_hold_over_every_seed` failing means a
  `comment_count` does not match the comment records — recount, do not change
  the invariant.

- [ ] **Step 9: `make check` and commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
git add tests/fixtures/toy tests/toy.py tests/unit/test_toy_fixture.py
git commit -S -s -m "test: Add the golden toy world -- three real inputs, four reviewable tasks

Section 9's two-capability toy world, built from real files through real intake
so the digest and stored_as chain is exercised rather than hand-written to
agree. Deliberately not a merge with tests/builders.py: those payloads are
minimal so one changed key is the whole test, and this one is complete enough
that a person can judge whether the output would be fair.

Exercises what no fixture in the tree did: two machine invariant forms, a
not_found outcome class, value_equals and answer_excludes, a recorded
contradiction, and a distractor set in every seed.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

**Self-check before reporting DONE.** Three specific things to state in your
report.

First: `test_the_machine_invariants_hold_over_every_seed` is shape 2 on its own
— an invariant over a collection no seed declares returns `[]` and the test
passes vacuously — so say which test closes it, and confirm you ran the
inversion **for every form, not just one.** The first version of this plan
inverted only `count`, and mistyping the `unique` form's collection to
`"tickets_typo"` left all eighteen fixture tests green. A holds-test plus a
one-form inversion reads as coverage of both and is coverage of one.

Second: **which keys of a `machine:` form fail loudly and which fail silently.**
`collection` and `of` are validated by `refs.check_world_model` against the
world model's declared collections, so a typo there is a layer-2 finding. The
others — `field`, `local_key`, `foreign_key`, `order_by`, `within` — are not,
and `invariants.py` reports a *violation* for a missing field rather than
staying silent, which is loud. Work out which of these actually go quiet when
wrong and report the list; the ones that go quiet are the ones a fixture test
has to cover, because nothing else will.

Third: the `answer_excludes` pointers all resolve to a *missing array index*.
Confirm by reading `refs._is_empty` and `refs.resolve_pointer` that this is the
intended shape rather than an accident of how the pointer resolver reports
failure, and if you conclude it is an accident, say so and stop — that would be
a finding about the contract, not something to work around in the fixture.

---

## Task 5: The golden end-to-end run, through emit and smoke

**Files:**
- Create: `tests/unit/test_toy_end_to_end.py`
- Modify: `tests/unit/test_refs_states.py` (add the toy world as a second states table? **No** — see below)

**Interfaces:**
- Consumes: `tests.toy.build_toy_run`, `emit.emit_run`, `smoke.AgentSpec`/`smoke_run`, `validate.validate_stage`, `refs.check_all`.
- Produces: `tests/toy.py` gains `ORACLE_SCRIPT`, `WEAK_SCRIPT`, `UNDER_TEST_SCRIPT` and `toy_roster(tmp_path) -> tuple[AgentSpec, ...]`.

**Do not extend `test_refs_states.py`.** That file's contract is one cumulative table over the *minimal* builders, and its value comes from every state being reachable by one more builder call. A second world in it would double every parametrized case for no new coverage of `check_all`, which is what it exists to test. The toy world's job is different: a single complete run, checked at every layer. Keep them apart and say so in the new file's docstring.

**These numbers are already verified.** The toy world was run against the real code while this plan was written: all seven layer-1 stages clean, `check_all` clean, `emit` producing four packages, and `smoke` returning `healthy` with zero findings. The expected values below are transcribed from that run, not predicted. If your run disagrees, something in Task 4's fixture drifted — find that, do not adjust these numbers.

| Measurement | Value |
|---|---|
| Artifact ids | `api-json`, `notes-md`, `trace-json` |
| `stored_as` | `api-json.json`, `notes-md.md`, `trace-json.json` |
| Classified kinds | `mcp_tool_schema`, `design_doc`, `trace` |
| Packages emitted | `scn-blocked`, `scn-empty`, `scn-missing`, `scn-open` (sorted) |
| `mean_reward_by_role` | `weak_baseline` 0.2, `under_test` 0.766667, `oracle` 1.0 |
| Verdict | `healthy` |
| `all_pass_tasks` / `all_fail_tasks` / `oracle_failures` / `unscoreable` | 0 / 0 / 0 / 0 |

**One finding this run surfaced, and it changes a later task.** The weak baseline scores **0.4 on `scn-empty` and `scn-missing`** — the two absence-shaped scenarios — while scoring 0.0 on the other two. The cause is in `verify.score_assertions`' own docstring: *"An exclusion satisfied by absence scores a point rather than avoiding a penalty."* So an agent that answers "I do not have enough information to say" satisfies every `answer_excludes` assertion in the task, for free. A scenario built **only** of exclusions is therefore substantially passable by a refusal, and the weak-baseline signal §7 relies on ("if it passes much, the tests are trivial") is weakened exactly where the `log-does-not-say` class of test lives.

The toy world stays under the ceiling (0.2 against `WEAK_BASELINE_CEILING` 0.30) because each absence scenario also carries a `tool_called` assertion the refusing agent fails. **That is the general rule, and it becomes an invariant in `tg-instantiate` (Task 11): an absence-shaped scenario must carry at least one assertion a refusal cannot satisfy — a `tool_called`, or a positive `answer_contains` on something the seed does contain.** Do not "fix" it in the verifier: scoring an exclusion positively is the deliberate ruling that lets a pure-absence scenario score at all. Record it as a fixture property and constrain the authoring stage.

- [ ] **Step 1: Write the failing end-to-end test**

`tests/unit/test_toy_end_to_end.py`:

```python
"""The golden fixture, run through every layer with no model involved.

Section 9's "one golden end-to-end fixture ... run in CI". Deliberately *not*
folded into test_refs_states.py: that file's contract is one cumulative table
over the minimal builders, where each state is reachable by one more builder
call and the thing under test is check_all's silence. This file is the other
shape -- one complete run, checked at every layer, from real input files.

Every expected number here was measured against the real code, not predicted.
"""

from __future__ import annotations

import json
import sys

import pytest

from testgen.emit import emit_run
from testgen.refs import check_all
from testgen.smoke import ORACLE_FLOOR, WEAK_BASELINE_CEILING, smoke_run
from testgen.validate import validate_stage
from tests.toy import ARTIFACT_IDS, SIDS, build_toy_run, toy_roster

# Stages with a real artifact to gate at the point the fixture reaches. emit and
# smoke are checked after they run, further down.
AUTHORED_STAGES = (
    "intake", "extract", "reconcile", "propose", "score", "instantiate", "challenge",
)


@pytest.fixture
def toy_run(tmp_path):
    return build_toy_run(tmp_path / "runs")


def test_intake_registered_the_three_inputs_with_digests_it_computed(toy_run):
    """Real intake, so the digest and stored_as chain is produced rather than
    asserted. A hand-written digest could only ever satisfy a check that was
    not looking -- refs.check_inputs re-hashes these bytes.
    """
    manifest = json.loads(toy_run.manifest.read_text(encoding="utf-8"))
    assert [e["artifact_id"] for e in manifest["inputs"]] == list(ARTIFACT_IDS)
    assert [e["stored_as"] for e in manifest["inputs"]] == [
        "api-json.json", "notes-md.md", "trace-json.json"
    ]
    assert [e["kind"] for e in manifest["inputs"]] == [
        "mcp_tool_schema", "design_doc", "trace"
    ]
    for entry in manifest["inputs"]:
        assert toy_run.input_file(entry["stored_as"]).is_file()


@pytest.mark.parametrize("stage", AUTHORED_STAGES)
def test_layer_1_is_clean_for_every_authored_stage(toy_run, stage):
    assert validate_stage(toy_run, stage) == []


def test_layer_2_is_clean_over_the_whole_run(toy_run):
    """Including the reachability gate over four seeds, both machine invariant
    forms, the discriminating_fact comparison, and the coverage/hole
    reconciliation in both directions.
    """
    assert check_all(toy_run) == []


def test_emit_produces_one_complete_package_per_scenario(toy_run):
    emitted, findings = emit_run(toy_run)
    assert (emitted, findings) == (sorted(SIDS), [])
    assert validate_stage(toy_run, "emit") == []
    assert check_all(toy_run) == []
    for sid in SIDS:
        for name in ("task.toml", "instruction.md", "seed.json", "golden.json",
                     "provenance.md", "tests/expected.json", "tests/verify.py",
                     "tests/test.sh"):
            assert (toy_run.task_dir(sid) / name).is_file(), f"{sid}/{name}"


def test_the_emitted_contract_never_carries_a_kind_outside_the_vocabulary(toy_run):
    """The closed vocabulary, checked on the artifact that reaches the scorer.
    A kind the verifier does not implement scores as failed, silently, and the
    schema does not catch it because the *shape* is fine.
    """
    from testgen.suite.verify import ASSERTION_KINDS

    emit_run(toy_run)
    for sid in SIDS:
        contract = json.loads(
            (toy_run.task_dir(sid) / "tests" / "expected.json").read_text(encoding="utf-8")
        )
        for assertion in contract["assertions"]:
            assert assertion["kind"] in ASSERTION_KINDS


def test_smoke_scores_the_suite_with_a_non_degenerate_spread(toy_run, tmp_path):
    """Success criterion #1: the suite executes and yields a spread.

    The three means below were measured, not predicted. The oracle at 1.0 is the
    test of the test suite -- if it drops, the labels or the verifier are broken,
    not the agent.
    """
    emit_run(toy_run)
    report, findings = smoke_run(toy_run, toy_roster(tmp_path))
    assert findings == []
    means = report["summary"]["mean_reward_by_role"]
    assert means == {"weak_baseline": 0.2, "under_test": 0.766667, "oracle": 1.0}
    assert report["verdict"] == "healthy"
    assert report["summary"]["unscoreable"] == 0
    assert report["summary"]["oracle_failures"] == 0
    assert validate_stage(toy_run, "smoke") == []
    assert check_all(toy_run) == []


def test_the_spread_clears_both_thresholds_it_is_measured_against(toy_run, tmp_path):
    """States *why* the verdict is healthy, against the constants rather than
    the literals. If a threshold moves, this fails with the reason attached
    instead of the previous test failing on a number nobody can interpret.

    The final assertion is the strict ordering. An earlier draft wrote it as
    `a < b < c or (b <= c)`, which is satisfied by any run at all -- a
    tautology that reads as coverage. If a compound assertion in a test has an
    `or` in it, work out what input makes it false before keeping it.
    """
    emit_run(toy_run)
    report, _ = smoke_run(toy_run, toy_roster(tmp_path))
    means = report["summary"]["mean_reward_by_role"]
    assert means["weak_baseline"] <= WEAK_BASELINE_CEILING
    assert means["oracle"] >= ORACLE_FLOOR
    assert means["weak_baseline"] < means["under_test"] <= means["oracle"]


def test_each_package_carries_its_own_scenarios_oracle(toy_run):
    """Each emitted package was compiled from *its own* scenario's oracle.

    Necessary because no reward number can establish it: all three roles score
    identically on the two absence-shaped tasks (0.4 / 1.0 / 1.0), so a
    mislabeling between them moves nothing. And layer 2 only catches half of
    it -- refs.check_instances compares expected.json's scenario_id against its
    directory, so a *directory* swap is reported, but swapping which oracle
    content attaches to which id, with the capability wiring and seed pointers
    left correctly matched, passes check_all and every reward assertion in this
    file. Verified by performing that swap.

    Both sides derive from toy_expected(sid) rather than hardcoded strings, so
    the check keeps working when the fixture's wording changes -- and so that
    under a swap the fixture still returns the right content while the package
    holds the wrong one, which is what makes the assertion fire.
    """
    from tests.toy import toy_expected

    emit_run(toy_run)
    for sid in SIDS:
        contract = json.loads(
            (toy_run.task_dir(sid) / "tests" / "expected.json").read_text(encoding="utf-8")
        )
        assert contract["scenario_id"] == sid
        oracle = toy_expected(sid)
        emitted = {(a.get("target"), a["value"]) for a in contract["assertions"]}
        expected = {(a.get("target"), a["value"]) for a in oracle["assertions"]}
        assert emitted == expected, f"{sid}'s package carries another scenario's assertions"
        golden = json.loads(
            (toy_run.task_dir(sid) / "golden.json").read_text(encoding="utf-8")
        )
        assert golden["answer"] == oracle["answer_reference"]


def test_the_weak_baseline_scores_only_on_the_absence_shaped_tasks(toy_run, tmp_path):
    """Pins the finding this fixture surfaced, so it cannot regress silently.

    verify.score_assertions scores an exclusion satisfied by absence as a point,
    by design -- so a refusing agent collects every answer_excludes assertion
    for free. The two absence-shaped scenarios are therefore partly passable by
    saying nothing, and what keeps them honest is the tool_called assertion each
    also carries. That is why tg-instantiate's invariants require one.

    Without this test, an edit that dropped the tool_called assertion from an
    absence scenario would raise the weak baseline toward its ceiling and only
    the aggregate mean would move -- a number no reader can attribute.
    """
    emit_run(toy_run)
    report, _ = smoke_run(toy_run, toy_roster(tmp_path))
    by_task = {
        task["scenario_id"]: {r["role"]: r["reward"] for r in task["results"]}
        for task in report["tasks"]
    }
    assert by_task["scn-open"]["weak_baseline"] == 0.0
    assert by_task["scn-blocked"]["weak_baseline"] == 0.0
    assert by_task["scn-empty"]["weak_baseline"] == 0.4
    assert by_task["scn-missing"]["weak_baseline"] == 0.4


def test_every_absence_shaped_scenario_carries_an_assertion_a_refusal_fails(toy_run):
    """The fixture-level statement of the invariant tg-instantiate must enforce.

    A scenario whose assertions are *all* exclusions is substantially passable
    by an agent that answers nothing, which removes exactly the signal the weak
    baseline exists to provide.
    """
    from testgen.suite.verify import DATA_KINDS, TRAJECTORY_KINDS
    from tests.toy import toy_expected

    for sid in SIDS:
        assertions = toy_expected(sid)["assertions"]
        exclusions = [a for a in assertions if a["kind"] == "answer_excludes"]
        if not exclusions:
            continue
        refusal_proof = [
            a for a in assertions
            if a["kind"] in TRAJECTORY_KINDS
            or (a["kind"] in DATA_KINDS and a["kind"] != "answer_excludes")
        ]
        assert refusal_proof, f"{sid} is passable by a refusal"


def test_the_verifier_that_scores_is_the_copied_one_under_a_bare_import_surface(toy_run, tmp_path):
    """smoke runs the package's own verify.py under `python -S` with a scrubbed
    environment, so the stdlib-only constraint is enforced by execution rather
    than declared. Pinned here because the golden run is the only place all four
    packages are scored at once.
    """
    emit_run(toy_run)
    smoke_run(toy_run, toy_roster(tmp_path))
    for sid in SIDS:
        verifier_out = toy_run.smoke_dir("oracle", sid) / "verifier"
        assert (verifier_out / "reward.txt").is_file(), sid
        assert float((verifier_out / "reward.txt").read_text()) == 1.0
```

- [ ] **Step 2: Add the three agent scripts and the roster to `tests/toy.py`**

```python
# Scripted agents for the golden smoke run. Real subprocesses printing real
# JSONL, never mocks: the properties that matter are all about the other end of
# the pipe, and smoke's contract with an agent is a transcript on stdout.
#
# The oracle reads golden.json, which is what the design spec means by "an
# oracle agent handed the reference answer". It is a test of the test suite: if
# it does not pass nearly everything, the labels or the verifier are broken.
ORACLE_SCRIPT = """\
import json, pathlib
golden = json.loads(pathlib.Path("golden.json").read_text())
for call in golden["tool_calls"]:
    print(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": call["tool"], "input": call["args"]}]}}))
print(json.dumps({"type": "result", "subtype": "success", "result": golden["answer"]}))
"""

# No tools, no answer. Scores 0 on the two positive-assertion tasks and 0.4 on
# the two absence-shaped ones, because an exclusion satisfied by absence scores
# a point by design -- which is exactly why each absence task also carries a
# tool_called assertion this agent fails.
WEAK_SCRIPT = """\
import json
print(json.dumps({"type": "result", "subtype": "success",
                  "result": "I do not have enough information to say."}))
"""

# Makes every call and then paraphrases without the tokens the oracle asserts:
# full trajectory credit, partial assertion credit. A middling agent rather
# than a broken one, which is the spread that matters.
UNDER_TEST_SCRIPT = """\
import json, pathlib
golden = json.loads(pathlib.Path("golden.json").read_text())
for call in golden["tool_calls"]:
    print(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": call["tool"], "input": call["args"]}]}}))
print(json.dumps({"type": "result", "subtype": "success",
                  "result": "I looked at the queue and found the relevant ticket."}))
"""

_SCRIPTS = {
    "weak_baseline": WEAK_SCRIPT,
    "under_test": UNDER_TEST_SCRIPT,
    "oracle": ORACLE_SCRIPT,
}


def toy_roster(tmp_path: Path) -> tuple[Any, ...]:
    """AgentSpecs for the three roles, backed by scripts written under tmp_path.

    sys.executable rather than a shebang: the interpreter running the tests is
    the one that must run the scripts, and a shebang would depend on the
    executable bit and on `python` resolving to 3.13 on PATH.
    """
    from testgen.smoke import AgentSpec

    specs = []
    for role, body in _SCRIPTS.items():
        script = Path(tmp_path) / f"{role}.py"
        script.write_text(body, encoding="utf-8")
        specs.append(
            AgentSpec(
                role=role,
                model=f"scripted-{role}",
                command=(sys.executable, str(script)),
                timeout_sec=60.0,
            )
        )
    return tuple(specs)
```

Add `import sys` to `tests/toy.py`.

- [ ] **Step 3: Run it**

Run: `uv run pytest tests/unit/test_toy_end_to_end.py -q`
Expected: PASS, every test. This run takes longer than the rest of the suite —
twelve subprocesses for the agents plus twelve for the verifiers. If it exceeds
about 30 seconds, report that rather than adding a `slow` marker; the numbers
above came from a run of a few seconds.

- [ ] **Step 4: Confirm the whole suite and commit**

```bash
uv run pytest -q && uv run ruff check . && uv run ruff format --check .
git add tests/toy.py tests/unit/test_toy_end_to_end.py
git commit -S -s -m "test: Run the toy world end to end, through emit and smoke

Section 9's golden fixture, with no model involved: real intake, layer 1 on
every authored stage, layer 2 over the whole run, four emitted packages, and a
scored smoke run with three scripted agents. weak_baseline 0.2, under_test
0.767, oracle 1.0, verdict healthy -- a real spread rather than a suite that
all-passes.

Records the property that run surfaced: an exclusion satisfied by absence
scores a point by design, so an absence-shaped scenario made only of exclusions
is substantially passable by a refusal. Each of the toy world's two carries a
tool_called assertion that a refusal fails, and tg-instantiate will require it.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

**Self-check before reporting DONE.** `test_the_spread_clears_both_thresholds_it_is_measured_against` has a compound final assertion with an `or` that makes it weak — say whether it can fail at all, and if it cannot, replace it with the strict ordering (`weak < under_test <= oracle`) and report that you did. A test whose assertion is a tautology is worse than no test, because it reads as coverage.

---

## Task 6: The live-exercise harness

**Files:**
- Create: `tests/conftest.py`
- Create: `docs/running-a-stage-by-hand.md`
- Modify: `pyproject.toml` (register the `live` marker)
- Modify: `Makefile` (a `live` target)
- Test: `tests/unit/test_live_marker.py`

**Why this exists.** §8's note on this build: *"a prompt's failure mode is behavioral, so an execution trace is the only artifact that will show it, and reading a `SKILL.md` tells you what it asked for, not what a model did with it."* Every skill task from here on ends with a real single-stage run. That run cannot be part of `make test` — it costs money, it is nondeterministic, and it needs a model — so it needs a marker, a default skip, and a documented way to invoke it. What it must **not** be is optional in practice: a marker nobody runs is a suite that does not exist, so the marker's skip message names the exact command that runs it and Task 15's README does too.

- [ ] **Step 1: Write the marker test**

`tests/unit/test_live_marker.py`:

```python
"""The live marker exists, is registered, and is skipped by default.

A live test is one that dispatches a model. It cannot run in CI, and a marker
nobody can find is a suite that does not exist -- so this file pins that the
marker is registered (an unregistered marker is a ruff/pytest warning, not an
error, and would silently do nothing) and that the skip message names the
command that runs it.
"""

from __future__ import annotations

import subprocess
import sys


def test_the_live_marker_is_registered():
    """An unregistered marker still applies but warns, and `--strict-markers`
    would then fail the whole run. Registered means both work.
    """
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--markers"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "@pytest.mark.live" in out


LIVE_TEST = '''\
import pytest


@pytest.mark.live
def test_marked_live():
    assert True
'''


def _run_pytest(tmp_path, env_extra):
    """Run pytest over a generated test file, with the repo's conftest in scope.

    A subprocess rather than pytester: this project has no pytester dependency,
    and the property under test is the default *collection* behaviour, which is
    exactly what an in-process run would not reproduce faithfully.

    rootdir is the repository, so tests/conftest.py applies -- the file under
    test is written into the repo's own tests/ tree under a tmp-derived name and
    removed afterwards.
    """
    import os
    from pathlib import Path

    target = Path("tests") / f"test_generated_{tmp_path.name}.py"
    target.write_text(LIVE_TEST, encoding="utf-8")
    try:
        return subprocess.run(
            [sys.executable, "-m", "pytest", str(target), "-q", "-p", "no:cacheprovider"],
            capture_output=True, text=True, env={**os.environ, **env_extra},
        ).stdout
    finally:
        target.unlink(missing_ok=True)


def test_a_live_test_is_skipped_without_the_opt_in(tmp_path):
    out = _run_pytest(tmp_path, {"TESTGEN_LIVE": ""})
    assert "1 skipped" in out, out
    assert "1 passed" not in out, out


def test_the_same_test_runs_with_the_opt_in(tmp_path):
    """The other direction, and the one that makes the first meaningful: without
    it, a marker that skipped unconditionally would satisfy the test above --
    and a live suite nothing can ever run is ornamental.
    """
    out = _run_pytest(tmp_path, {"TESTGEN_LIVE": "1"})
    assert "1 passed" in out, out


def test_the_skip_reason_names_the_command_that_runs_it(tmp_path):
    """A marker nobody can find is a suite that does not exist. `-rs` prints the
    skip reasons, so the reason string is checkable rather than aspirational.
    """
    import os
    from pathlib import Path

    from tests.conftest import LIVE_ENV

    target = Path("tests") / f"test_generated_reason_{tmp_path.name}.py"
    target.write_text(LIVE_TEST, encoding="utf-8")
    try:
        out = subprocess.run(
            [sys.executable, "-m", "pytest", str(target), "-rs", "-q",
             "-p", "no:cacheprovider"],
            capture_output=True, text=True,
            env={**os.environ, "TESTGEN_LIVE": ""},
        ).stdout
    finally:
        target.unlink(missing_ok=True)
    assert LIVE_ENV in out, out
    assert "make live" in out, out
```

> **Implementer note.** The opt-in is an **environment variable**, not a pytest
> flag: a controller dispatching a subagent cannot easily add a flag to a command
> it does not construct, and an env var composes with `make live`. Note that
> `_run_pytest` writes its generated file into the repo's `tests/` tree so the
> project's `conftest.py` is in scope, and removes it in a `finally`. If that
> offends you, the alternative is copying `conftest.py` into `tmp_path` — which
> tests a copy of the marker logic rather than the real one. Prefer the real one.

- [ ] **Step 2: Write `tests/conftest.py`**

```python
"""Shared pytest configuration: the live marker and its default skip.

A live test dispatches a model. It costs money, it is not deterministic, and it
needs credentials, so it is skipped unless TESTGEN_LIVE is set. The skip
message names the command that runs it, because a marker nobody can find is a
suite that does not exist.
"""

from __future__ import annotations

import os

import pytest

LIVE_ENV = "TESTGEN_LIVE"
LIVE_SKIP_REASON = (
    f"live test: dispatches a model. Run with `{LIVE_ENV}=1 make live`, or "
    f"`{LIVE_ENV}=1 uv run pytest -m live`."
)


def pytest_collection_modifyitems(config, items):
    if os.environ.get(LIVE_ENV):
        return
    skip = pytest.mark.skip(reason=LIVE_SKIP_REASON)
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
```

In `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "live: dispatches a model; skipped unless TESTGEN_LIVE is set (see tests/conftest.py)",
]
```

In the `Makefile`, after `test`:

```make
live: ## Run the live stage exercises (dispatches a model; costs money)
	TESTGEN_LIVE=1 uv run pytest -m live -q
```

- [ ] **Step 3: Write the runbook**

`docs/running-a-stage-by-hand.md`. This is the document the controller follows
for every live exercise and the one a human follows to debug a stage, so it must
be executable as written. It contains:

1. **The three things a dispatched stage receives**, quoted from §4, and the
   statement that nothing else may be passed — no conversational context, no
   summary of what earlier stages concluded.
2. **The dispatch prompt template**, verbatim and copy-pasteable:

   ```
   You are the <stage> stage of the testgen pipeline.

   Run directory: <absolute path>
   Your skill:    <absolute path to SKILL.md>

   Read your skill and follow it exactly. Read only the artifacts your skill's
   Contract block lists under `reads`. Write only what it lists under `writes`.
   Do not read this pipeline's other stages, other scenarios, or any file the
   contract does not name.

   When you are done, report only: the paths you wrote, and any refusal
   condition you hit.
   ```

3. **The verification commands**, per stage:

   ```bash
   testgen validate --run "$RUN" --stage <stage>   # expect 0
   testgen check-refs --run "$RUN"                 # expect 0
   testgen record-stage --run "$RUN" --stage <stage> \
     --model <model> --effort <effort> \
     --skill src/testgen/skills/tg-<stage>/SKILL.md
   ```

4. **How to build the toy run to exercise a stage against**, including how to
   get a run directory populated up to the stage under test but *not* past it —
   `tests/toy.py`'s builders are importable, so a five-line script does it. Give
   that script in full:

   ```python
   # scripts/toy-run-to.py <stage> <runs-dir>  -- not shipped, written inline
   import sys
   from pathlib import Path
   from testgen.artifacts import write_json
   from tests.toy import (ARTIFACT_IDS, SIDS, build_toy_run, toy_claims,
                          toy_coverage, toy_scenarios, toy_world_model)
   # build_toy_run writes everything; for a partial run, call intake yourself
   # and stop before the stage under test. The runbook spells out which builder
   # corresponds to which stage.
   ```

   > **Implementer note.** `build_toy_run` writes *every* artifact, which is
   > wrong for exercising a stage: handing `tg-reconcile` a run that already
   > contains `01-world-model.json` tests nothing. So add
   > `build_toy_run(runs_dir, upto="extract")` — a keyword that stops after the
   > named stage, defaulting to the full run. Implement it in this task, extend
   > `tests/toy.py`, and test the two ends (`upto="intake"` writes only the
   > manifest and inputs; the default writes everything). The runbook then shows
   > one command per stage.

5. **What to do when the exercise fails**, split three ways, because the three
   have different owners: a *schema* failure is usually the skill's Output
   section being unclear; a *check-refs* failure is usually the Invariants
   section missing a constraint; and a stage that produced nothing and reported
   a refusal may well be **correct** — check whether the refusal condition it
   cites actually holds in the toy world before treating it as a defect.

- [ ] **Step 4: Verify the marker works in both directions**

```bash
uv run pytest --markers | grep live
uv run pytest -m live -q                 # expect: no tests ran / all skipped
TESTGEN_LIVE=1 uv run pytest -m live -q  # expect: same, until Task 7 adds one
uv run pytest -q                         # expect: unchanged count, nothing skipped
```

The last line matters: a `conftest.py` that skips too broadly would silently
shrink the suite. Compare the count against the previous task's.

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
git add tests/conftest.py tests/unit/test_live_marker.py docs/running-a-stage-by-hand.md pyproject.toml Makefile tests/toy.py
git commit -S -s -m "test: Add the live-exercise harness and the stage runbook

Every skill from here is exercised once for real, because a prompt's failure
mode is behavioral: reading a SKILL.md tells you what it asked for, not what a
model did with it. Those runs cannot be part of make test, so they get a marker
skipped by default -- with a skip message naming the command that runs it,
since a marker nobody can find is a suite that does not exist.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Tasks 7–13: the skills — how these tasks differ from the ones above

**The plan gives requirements; the implementer writes the prose.** Every earlier task in this plan supplies its code verbatim, because transcription is the cheapest way to get deterministic code right. For a `SKILL.md` that would be actively wrong, and the reason is in the spec (§8, closing note): *"when a plan supplies both the code and its tests, the tests cannot be trusted to bound the code, because both came from the same understanding."* For a prompt it is worse — if the plan writes the prompt, the implementer contributes nothing but copying, the reviewer compares the prose against the brief that produced it, and the only real check left is the live exercise.

So each skill task below gives, exactly and completely:

- **the contract block**, verbatim (it is mechanical, and `check-skills` fails on any deviation);
- **the Method steps**, enumerated, each with its spec citation — the *what*, not the wording;
- **the Invariants**, enumerated as checkable statements;
- **the Refusal conditions**, enumerated as trigger → required action;
- **the test file**, verbatim;
- **the live exercise**, with its pass criteria.

The implementer writes sections 1–5's prose from that list. A section that omits a listed item is a failed spec review. A section that adds an item is fine and expected — these lists are floors.

**Every skill task follows the same seven steps**, so they are not repeated in each:

1. Write the test file for this skill (`tests/unit/test_skills_<stage>.py`). Run it; it fails because the `SKILL.md` does not exist.
2. Write `src/testgen/skills/tg-<stage>/SKILL.md` with the contract block verbatim and sections 1–5 covering every listed item.
3. Write `src/testgen/skills/tg-<stage>/exercise.md` — the live exercise's pass criteria, from this task's list. It is documentation, not a test; `check-skills` ignores it.
4. `uv run pytest tests/unit/test_skills_<stage>.py -q` → PASS.
5. `uv run python -c "from testgen.skills import check_all, load, skills_dir; import sys; f=[x for x in check_all(skills_dir()) if 'tg-<stage>' in str(x.artifact)]; print(f or 'CLEAN'); sys.exit(1 if f else 0)"` → CLEAN. (`testgen check-skills` itself still exits 1 until Task 13, because the other skills are missing; this filters to the one you wrote.)
6. `uv run pytest -q && uv run ruff check . && uv run ruff format --check .`
7. Commit with `git commit -S -s`, `Assisted-By:` trailer, no `Co-Authored-By`.

**Every skill task also carries these three requirements in every section 1:** it reads only the artifacts its contract's `reads` names; it receives no conversational context, so anything it needs must come from an artifact; and it must never read another scenario's slice (§5's fan-out isolation rule) where the stage is a fan-out.

**And every section 4 ends with the same self-check instruction:** run `testgen validate --stage <stage>` and, where the contract lists it, `testgen check-refs`, before reporting done — and if either reports a finding, repair the artifact rather than reporting success.

### The live exercise, run by the controller

After each skill task's review passes, the **controller** — not the implementer — dispatches a fresh subagent with exactly the three things §4 permits (run directory, stage name, skill path), following `docs/running-a-stage-by-hand.md`. The implementer must not run it: its context holds the skill it just wrote and the brief that specified it, which is precisely the isolation the exercise tests. Record the outcome in the SDD ledger as `Task <N>: exercise <clean|findings: …>`.

A failed exercise is **not** automatically a failed task. Adjudicate it:

| Exercise outcome | Reading |
|---|---|
| Artifact written, `validate` and `check-refs` clean | Pass. |
| Artifact written, layer 1 finding | The skill's **Output** section is unclear. Fix the skill. |
| Artifact written, layer 2 finding | The skill's **Invariants** section is missing a constraint. Fix the skill. |
| Nothing written, a refusal reported | Check whether the cited refusal condition actually holds in the toy world. If it does, the skill is **correct** and the exercise passes — record which condition fired. If it does not, the refusal conditions are over-broad. |
| Subagent read an artifact outside `reads` | The **Inputs** section is not forbidding clearly enough. This is the isolation failure the fan-out design exists to prevent, so treat it as Important, not Minor. |

---

## Task 7: `tg-extract`

**Files:** create `src/testgen/skills/tg-extract/SKILL.md`, `.../exercise.md`; test `tests/unit/test_skills_extract.py`.

**Contract block, verbatim:**

```toml
stage = "extract"
reads = ["manifest", "input_file"]
writes = ["claims"]
schemas = ["claims"]
invokes = ["validate"]
```

**Method steps** (§3's "extract is a fan-out … one subagent each, none seeing the others' conclusions"):

1. Read `manifest.json` and find **your** input entry — the one whose `artifact_id` matches the id you were dispatched for. Read that one file via its `stored_as` name under `00-inputs/`.
2. Enumerate every statement the artifact makes about the target, one claim per statement. A claim is the atom of this stage: there are no bare assertions (§4).
3. For each claim, choose its `kind` from the schema's enum, and record `evidence` with a `locator` precise enough that a reader can find the statement again — a JSON pointer for a JSON input, a heading anchor or line reference for prose.
4. Set `derivation` honestly: `stated` when the artifact says it, `inferred` when you concluded it from what the artifact says, `reverse_engineered` when you read it off an observed behaviour such as a trace. §4: this is what makes gap reporting honest — "the OpenAPI spec states this" and "I guessed from one trace" must not be indistinguishable downstream.
5. Set `confidence` independently of `derivation`. A `stated` claim from a document that contradicts itself is not high confidence.
6. Prefix every claim id with your artifact id (`clm-<artifact-id>-NNN`), because claim ids must be unique across every claims file — `refs.check_manifest` reports a claim id defined twice, since every world-model reference to it would resolve ambiguously.

**Invariants:**

1. `artifact_id` equals the filename stem of the file you write, and is registered in `manifest.inputs`.
2. Every `evidence[].artifact_id` names a registered input — normally your own.
3. Every claim has at least one evidence entry. The schema requires it; state it anyway, because a claim without evidence is the failure this stage exists to prevent.
4. You claim nothing about capabilities or entities the artifact does not mention. Another artifact may mention them, and you must not know that.

**Refusal conditions:**

| Trigger | Required action |
|---|---|
| Your input file is unreadable or empty | Write a claims file with an empty `claims` array and report it. Do not guess at contents from the filename. |
| The artifact describes behaviour you cannot classify into any `kind` | Record it as the closest kind with `confidence: low` and say so in the `statement`. Do not invent a kind — the enum is closed. |
| The artifact contradicts *itself* | Record both claims separately with `confidence: low`. Reconciling them is `tg-reconcile`'s job and you must not do it here — §3: keeping them separate is what makes a contradiction a *recorded* one rather than something silently resolved. |
| You are tempted to record a capability's error semantics the artifact does not state | Do not. Record only what is there; a missing error class becomes a gap at `tg-reconcile` and a hole at `tg-score`. §5: skills default to helpfulness, and this must be written against. |

**Test file** — `tests/unit/test_skills_extract.py`:

```python
"""tg-extract's contract and the structural properties its prompt must have.

Structural, not free-text: an assertion that some sentence appears in the prose
is shape 1 by construction, because another sentence may contain the same words.
What is asserted here is either a declaration in the contract block or a set
compared against a set imported from the code.
"""

from __future__ import annotations

from testgen.skills import SECTIONS, load, skills_dir
from testgen.validate import STAGE_ARTIFACTS

SKILL = skills_dir() / "tg-extract" / "SKILL.md"


def test_the_contract_is_exactly_what_the_stage_is_gated_on():
    skill = load(SKILL)
    assert skill.contract["stage"] == "extract"
    assert set(skill.contract["schemas"]) == set(STAGE_ARTIFACTS["extract"])


def test_it_declares_only_the_two_artifacts_a_fan_out_member_may_read():
    """The isolation rule: an extract subagent sees the manifest and its own
    input file. Declaring claims_dir would let it read a sibling's conclusions,
    which is exactly what the fan-out was chosen to prevent.
    """
    assert load(SKILL).contract["reads"] == ["manifest", "input_file"]


def test_it_has_the_five_sections(): 
    assert all(section in load(SKILL).headings for section in SECTIONS)


def test_the_derivation_values_it_names_are_the_schema_s_enum():
    """A skill that names two of the three values would let the third go
    unwritten, and derivation is what makes gap reporting honest. Compared
    against the schema rather than a literal list.
    """
    from testgen.artifacts import read_json
    from testgen.validate import ARTIFACT_SCHEMAS, schema_dir

    schema = read_json(schema_dir() / ARTIFACT_SCHEMAS["claims"])
    enum = schema["$defs"]["claim"]["properties"]["derivation"]["enum"]
    body = load(SKILL).body
    for value in enum:
        assert value in body, f"the skill never mentions derivation={value!r}"


def test_the_claim_kinds_it_names_are_the_schema_s_enum():
    from testgen.artifacts import read_json
    from testgen.validate import ARTIFACT_SCHEMAS, schema_dir

    schema = read_json(schema_dir() / ARTIFACT_SCHEMAS["claims"])
    enum = schema["$defs"]["claim"]["properties"]["kind"]["enum"]
    body = load(SKILL).body
    missing = [kind for kind in enum if kind not in body]
    assert not missing, f"the skill never mentions claim kind(s) {missing}"


def test_the_refusal_section_names_a_response_for_an_unreadable_input():
    """One of the four refusal conditions, checked structurally: the section
    must be long enough to carry four distinct triggers. A length floor is a
    weak check and is here only to catch a section reduced to one line -- the
    live exercise is what tests whether the conditions actually fire.
    """
    from testgen.skills import SECTIONS as S

    skill = load(SKILL)
    index = skill.headings.index(S[-1])
    assert index == len(skill.headings) - 1, "refusal conditions must be the last section"
    body = skill.body.split(f"## {S[-1]}", 1)[1]
    assert len(body.strip().splitlines()) >= 4, "four refusal conditions are required"
```

> **Implementer note.** `test_the_refusal_section_names_a_response_for_an_unreadable_input`
> is a weak test and its docstring says so. Keep it, and in your report name it
> as the one test in this file whose failure mode is shape 1 — then say what the
> live exercise checks that it cannot.

**Live exercise** (`exercise.md` records this; the controller runs it):

- Build a toy run stopped after `intake`: `build_toy_run(runs_dir, upto="intake")`.
- Dispatch once per input artifact — three dispatches, each told only its own `artifact_id`.
- **Pass criteria:** three files under `01-claims/`, named `api-json.json`, `notes-md.json`, `trace-json.json`. Note the second one: the claims filename is `<artifact_id>.json` regardless of the input's suffix, because `paths.claims` builds it that way — the input was registered as `notes-md.md`, and a skill that mirrors `stored_as` would write `notes-md.md.json` or `notes-md.md`, either of which `refs.check_manifest` reports as a filename that disagrees with its own `artifact_id`. `testgen validate --stage extract` exits 0. `testgen check-refs` exits 0. No claim id appears in two files.
- **The property to look for that no test can check:** does the subagent dispatched for `trace-json` record `clm-trace-002`-shaped content — that an unknown id returned an empty object — *without* also asserting the documented error behaviour it never read? If it imports the notes' error semantics, the fan-out isolation is not holding and the Inputs section needs to forbid more clearly.

---

## Task 8: `tg-reconcile`

**Files:** create `src/testgen/skills/tg-reconcile/SKILL.md`, `.../exercise.md`; test `tests/unit/test_skills_reconcile.py`.

**Contract block, verbatim:**

```toml
stage = "reconcile"
reads = ["manifest", "claims_dir"]
writes = ["world_model"]
schemas = ["world-model"]
invokes = ["validate", "check-refs"]
```

**Method steps** (§3: reconcile is the barrier; §4: the denominator is computed here, once):

1. Read every file under `01-claims/`. This is the one stage that sees all of them — that is what makes it the barrier.
2. Group claims into capabilities, entities, actors and goals. Every element you create cites the claim ids it rests on; an element with no claim is not admissible (`refs.check_world_model` resolves every `claims[]` reference).
3. **For every capability, enumerate its outcome classes.** Not only the success path: `success`, `empty`, `not_found`, `error`, `underspecified` are the vocabulary, and the coverage denominator is capability × outcome class. A capability with one outcome class shrinks the denominator, which is how a run reaches high coverage without testing anything hard.
4. Give each capability a `binding` — the tool name a transcript will show, plus the `fixed_args` that distinguish this capability from a sibling sharing the tool. `emit` reports a finding for an accepted scenario whose capability has none, so a missing binding costs a test.
5. **Record every contradiction you find, rather than resolving it silently** (§3). Set `resolution` to one of the four values and give a `rationale` that says why. `unresolved` is a legitimate answer and is better than a guess.
6. **Record every gap** — knowledge about the target that no input contains and that reasoning cannot supply. Each gap names the stages it `blocks`. §5: halting on a blocking gap is the payoff for first-class gaps; if this never fires on a real run, gap detection is not working.
7. Enumerate goals from the actors' perspective, each with the `expected_hop_depths` it supports. The goal list is **frozen** here: stage 2 designs against it and may only request an amendment, which costs an orchestrator decision and a `denominator_version` bump (§4).
8. Compute `denominator`: `version: 1`, `capability_cells` = the total number of capability × outcome-class pairs, `goals` = the number of goals. `refs.check_world_model` recomputes both and reports a mismatch.
9. Add `machine:` invariants where an entity invariant fits one of the four forms — `compare`, `count`, `join`, `unique` — and `prose:` where it does not. §6 step 3: a seed violating a recomputed field is not merely unrealistic; the simulation recomputes it, so the authored content silently changes and the gold label is now wrong about a world that no longer exists.

**Invariants:**

1. Every `claims[]` reference in every element resolves to a claim id that exists in `01-claims/`.
2. `denominator.capability_cells` equals the number of capability × outcome-class pairs you wrote; `denominator.goals` equals the number of goals.
3. Every `goal.actor_id` names an actor you declared; every `relation.target_entity_id` names an entity you declared.
4. Every `machine:` invariant's `collection` and `of` name a collection some entity declares.
5. An invariant carries `machine:` **or** `prose:`, never both (the schema's `oneOf`).
6. A contradiction's `claim_a` and `claim_b` both resolve.

**Refusal conditions:**

| Trigger | Required action |
|---|---|
| Two claims disagree and you cannot tell which is right | Record the contradiction with `resolution: unresolved`. Do not pick one to keep the world model tidy. |
| A capability's error or empty behaviour is described nowhere | Record a **gap**, not an invented outcome class. If the missing semantics would stop stage 2 from proposing a meaningful scenario, the gap `blocks: ["propose"]`. |
| An entity's invariants are implied but not stated | Record them as `prose:` with the inference visible in the `statement`, or record a gap. Do not promote a guess to `machine:` — a wrong `machine:` invariant fails every seed that is actually correct. |
| You cannot identify any actor | Record a gap blocking `propose`. A goal list with no actor is a denominator you invented. |
| You are tempted to add a capability no claim supports because the target "obviously" has it | Do not. §5: confabulation under under-specification is the characteristic failure of a prompt pipeline. |

**Test file** — `tests/unit/test_skills_reconcile.py`:

```python
"""tg-reconcile's contract and the enumerations its prompt must be complete over.

The two set-completeness tests below are the ones that matter. This stage
computes the coverage denominator, so a skill that names three of the five
outcome-class kinds produces a denominator that is quietly smaller than the
target's real surface -- and every later percentage is measured against it.
"""

from __future__ import annotations

from testgen.artifacts import read_json
from testgen.skills import SECTIONS, load, skills_dir
from testgen.validate import ARTIFACT_SCHEMAS, STAGE_ARTIFACTS, schema_dir

SKILL = skills_dir() / "tg-reconcile" / "SKILL.md"


def _world_schema():
    return read_json(schema_dir() / ARTIFACT_SCHEMAS["world-model"])


def test_the_contract_matches_the_stage_gate():
    skill = load(SKILL)
    assert skill.contract["stage"] == "reconcile"
    assert set(skill.contract["schemas"]) == set(STAGE_ARTIFACTS["reconcile"])


def test_it_reads_the_whole_claims_directory_because_it_is_the_barrier():
    """The one stage that sees every artifact's conclusions. A contract that
    declared a single claims file would make it a fan-out member and there
    would be nothing left to merge.
    """
    assert "claims_dir" in load(SKILL).contract["reads"]


def test_it_has_the_five_sections():
    assert all(section in load(SKILL).headings for section in SECTIONS)


def test_it_names_every_outcome_class_kind():
    """The denominator is capability x outcome class. A skill that omits
    `underspecified` produces a denominator missing that column for every
    capability, and coverage is then measured against a surface smaller than
    the target's.
    """
    enum = _world_schema()["$defs"]["capability"]["properties"]["outcome_classes"]["items"][
        "properties"
    ]["kind"]["enum"]
    body = load(SKILL).body
    missing = [kind for kind in enum if kind not in body]
    assert not missing, f"the skill never mentions outcome class kind(s) {missing}"


def test_it_names_every_contradiction_resolution_value():
    """Including `unresolved`, which is the one a skill under pressure to be
    helpful will omit -- and it is the only honest answer for a real
    disagreement the inputs do not settle.
    """
    enum = _world_schema()["$defs"]["contradiction"]["properties"]["resolution"]["enum"]
    body = load(SKILL).body
    missing = [value for value in enum if value not in body]
    assert not missing, f"the skill never mentions resolution(s) {missing}"


def test_it_names_every_machine_invariant_form_the_code_implements():
    """Imported from invariants.py, not from the schema and not from a literal:
    the forms the code can evaluate are the forms a skill may write, and a
    skill naming a fifth would produce an invariant refs reports as
    unimplemented.
    """
    from testgen.invariants import _HANDLERS

    body = load(SKILL).body
    missing = [form for form in _HANDLERS if form not in body]
    assert not missing, f"the skill never mentions machine form(s) {missing}"


def test_it_names_every_stage_a_gap_may_block():
    """A gap's `blocks` list is what makes the orchestrator halt. A skill that
    names only `propose` cannot express a gap that blocks instantiate.
    """
    enum = _world_schema()["$defs"]["gap"]["properties"]["blocks"]["items"]["enum"]
    body = load(SKILL).body
    missing = [stage for stage in enum if stage not in body]
    assert not missing, f"the skill never mentions blockable stage(s) {missing}"


def test_it_states_that_the_denominator_is_computed_here_and_frozen():
    """Structural: the Method section must contain the denominator's three
    field names, which is the smallest check that the computation is specified
    rather than gestured at.
    """
    body = load(SKILL).body
    for field in ("capability_cells", "goals", "version"):
        assert field in body, field
```

> **Implementer note.** `test_it_names_every_machine_invariant_form_the_code_implements`
> imports `invariants._HANDLERS`, a private name. That is deliberate: it is the
> authoritative set, and the alternative is a literal list that goes stale the
> first time a form is added. If ruff objects, add the narrowest possible `noqa`
> with a comment saying why — do not switch to a literal.

**Live exercise:**

- Build a toy run stopped after `extract`: `build_toy_run(runs_dir, upto="extract")`.
- One dispatch.
- **Pass criteria:** `01-world-model.json` exists; `testgen validate --stage reconcile` exits 0; `testgen check-refs` exits 0. Then read it by hand against three questions:
  1. **Did it record the contradiction?** `notes.md` says an unknown id is an error; `trace.json` shows an empty object. A world model with zero contradictions here has silently resolved a real disagreement, and that is the failure §3's extract/reconcile split exists to prevent. This is the single most important thing the exercise measures.
  2. **Did it enumerate more than the success outcome class per capability?** Two capabilities with one class each is a denominator of 2 where the toy world has 4.
  3. **Did it write both `machine:` invariants?** `notes.md` states the comment count rule and the uniqueness rule explicitly, both fit implemented forms, and both are `stated`. A world model that files them as `prose:` has left the reachability gate with nothing to check.
- **Record which of the three it got**, in the ledger, whether or not the task passes. This is the first real measurement of whether prompt-carried judgment survives a handoff, which is the hypothesis the whole project exists to test.

---

## Task 9: `tg-propose`

**Files:** create `src/testgen/skills/tg-propose/SKILL.md`, `.../exercise.md`; test `tests/unit/test_skills_propose.py`.

**Contract block, verbatim:**

```toml
stage = "propose"
reads = ["world_model", "scenarios", "coverage_latest"]
writes = ["scenarios"]
schemas = ["scenarios"]
invokes = ["validate"]
```

`scenarios` appears in both `reads` and `writes` because `02-scenarios.json` is **append-only across rounds** (§4): round 2 reads what round 1 proposed and adds to it. `coverage_latest` is read to find the holes to target and legitimately does not exist in round 1 — `reads` is a declaration of what a skill may open, not a list of files that must be present.

**Method steps:**

1. Read the world model. Read `03-coverage/latest.json` if it exists; in round 1 it does not, and every cell is a hole by default.
2. Read the existing `02-scenarios.json` if present. **Append; never rewrite or renumber.** An existing scenario's `status` is not yours to change — `tg-score` owns that transition.
3. Pick the holes to target. A hole whose `reason` is `blocked_by_gap`, `unreachable` or `out_of_scope` is **not** closable — do not propose against it (§3: the two never substitute for one another).
4. For each targeted hole, design a scenario a real actor would actually want: `goal_id` and `actor_id` from the frozen lists, a `user_intent` phrased as the person would phrase it, and `capability_refs` naming exactly the cells the scenario claims to cover.
5. **Declare the `discriminating_fact`** — the single fact the test hinges on, stated so that stage 4 can build a world in which it is *uniquely* determined. §4: this is what stops stage 4 from facing a blank page and inventing a trivial world. A fact of the form "the query returns some rows" is not discriminating.
6. Set `hop_depth` to the number of tool calls the scenario genuinely requires, and make it consistent with `capability_refs`: a depth of 2 with one capability ref needs an explanation, because `tg-challenge` independently measures the minimum and flags `difficulty_overstated` when the claim is inflated.
7. Set `status: "proposed"` on everything you write. **Only `tg-score` may set `active`, `duplicate` or `rejected`.**
8. Fill `provenance`: the `hole_refs` you targeted, the `claim_ids` the scenario rests on, and the round.

**Invariants:**

1. Every `capability_refs[]` pair is a real capability × outcome-class cell in the world model.
2. Every `provenance.hole_refs[]` names a real cell or goal (`cell:<cap>/<oc>` or `goal:<id>`).
3. `denominator_version` equals the world model's `denominator.version`. If you believe the denominator is wrong, that is a refusal condition, not an edit.
4. Every scenario id is unique across the whole file, including rounds you did not write.
5. `round` and `provenance.round` are both the current round, and neither exceeds `manifest.limits.max_rounds` — `refs.check_limits` reports both.
6. The count of `proposed` plus `active` scenarios in the file does not exceed `manifest.limits.max_scenarios`. Duplicates and rejects do not count against it.
7. Every scenario you write has `status: "proposed"`.

**Refusal conditions:**

| Trigger | Required action |
|---|---|
| A hole's `reason` is `blocked_by_gap` | Do not propose against it. Say which gap, and stop. Proposing anyway produces a scenario stage 4 cannot seed. |
| Closing a hole would require a capability or outcome class the world model does not declare | Do not propose. Report that the world model needs an amendment — which costs an orchestrator decision and a `denominator_version` bump, and is not yours to make. |
| The goal list has no goal your scenario would serve | Do not invent one. §4: a goal-based denominator that stage 2 also invents can reach 100% by not imagining more goals. Report it. |
| You cannot state a `discriminating_fact` that is uniquely determined | Do not propose the scenario. A scenario whose fact is vague produces a world stage 4 builds arbitrarily and a label nobody can defend. |
| `max_scenarios` is already reached | Stop, and report how many holes remain unaddressed. Do not propose past the cap and leave `check-refs` to catch it. |

**Test file** — `tests/unit/test_skills_propose.py`:

```python
"""tg-propose's contract, and the two status boundaries it must not cross.

The status boundary is the one that matters here: propose writes `proposed`,
and score owns every other transition. A skill that writes `active` closes the
loop's judgment step by fiat, and refs would not notice -- `active` is a
perfectly valid status for a scenario to have.
"""

from __future__ import annotations

from testgen.artifacts import read_json
from testgen.refs import JUDGED_STATUSES, OPEN_STATUSES
from testgen.skills import SECTIONS, load, skills_dir
from testgen.validate import ARTIFACT_SCHEMAS, STAGE_ARTIFACTS, schema_dir

SKILL = skills_dir() / "tg-propose" / "SKILL.md"


def test_the_contract_matches_the_stage_gate():
    skill = load(SKILL)
    assert skill.contract["stage"] == "propose"
    assert set(skill.contract["schemas"]) == set(STAGE_ARTIFACTS["propose"])


def test_it_both_reads_and_writes_the_scenarios_file():
    """Append-only across rounds: round 2 reads what round 1 proposed. A
    contract that only wrote it would license a rewrite, and a rewritten
    02-scenarios.json loses round 1's provenance.
    """
    contract = load(SKILL).contract
    assert "scenarios" in contract["reads"]
    assert "scenarios" in contract["writes"]


def test_it_has_the_five_sections():
    assert all(section in load(SKILL).headings for section in SECTIONS)


def test_it_names_every_hole_reason_so_it_can_tell_closable_from_not():
    """A hole whose reason is blocked_by_gap is not closable by proposing. A
    skill that does not know the vocabulary cannot make that distinction and
    will propose against a gap.
    """
    schema = read_json(schema_dir() / ARTIFACT_SCHEMAS["coverage"])
    enum = schema["$defs"]["hole"]["properties"]["reason"]["enum"]
    body = load(SKILL).body
    missing = [reason for reason in enum if reason not in body]
    assert not missing, f"the skill never mentions hole reason(s) {missing}"


def test_it_states_that_it_writes_only_the_proposed_status():
    """The boundary, checked against refs' own status sets rather than literals.

    Every status in OPEN_STATUSES | JUDGED_STATUSES other than `proposed` is a
    transition score owns, and the skill must say so. This is deliberately a
    membership check over an imported set: adding a status to refs.py without
    revisiting this prompt should fail here.
    """
    body = load(SKILL).body
    assert "proposed" in body
    score_owned = (OPEN_STATUSES | JUDGED_STATUSES) - {"proposed"}
    assert score_owned, "the set this test is about must not be empty"
    # The skill must name each status it may not write, so a reader of the
    # prompt knows the boundary rather than inferring it.
    for status in sorted(score_owned):
        assert status in body, f"the skill never says it must not write {status!r}"


def test_it_names_the_two_manifest_limits_it_must_respect():
    """check_limits reports a round above max_rounds and an open-scenario count
    above max_scenarios. A skill that does not know the caps exist will hit them
    and spend the orchestrator's one repair attempt.
    """
    body = load(SKILL).body
    for limit in ("max_rounds", "max_scenarios"):
        assert limit in body, limit


def test_it_names_the_discriminating_fact_field():
    assert "discriminating_fact" in load(SKILL).body
```

**Live exercise:**

- Build a toy run stopped after `reconcile` (`upto="reconcile"`), so `02-scenarios.json` and `03-coverage/` do not exist — round 1 from a blank page.
- One dispatch.
- **Pass criteria:** `02-scenarios.json` exists; `testgen validate --stage propose` exits 0; `testgen check-refs` exits 0; **every** scenario has `status: "proposed"`.
- **The properties to look for:** (a) does it propose against the `not_found` cell, or only the success cells? Absence-shaped scenarios are the ones a helpful generator skips. (b) Are the `discriminating_fact` values actually discriminating, or are they restatements of the `user_intent`? (c) Does it stay at or under `max_scenarios` (8)?

---

## Task 10: `tg-score`

**Files:** create `src/testgen/skills/tg-score/SKILL.md`, `.../exercise.md`; test `tests/unit/test_skills_score.py`.

**Contract block, verbatim:**

```toml
stage = "score"
reads = ["world_model", "scenarios"]
writes = ["scenarios", "coverage_round", "coverage_latest"]
schemas = ["coverage"]
invokes = ["dedupe-candidates", "validate", "check-refs"]
```

**Method steps** (§5: dedupe folds into stage 3 because the candidate pairs are cheap to compute and the judgment is not):

1. Run `testgen dedupe-candidates --run <run>` and read the JSON it prints. Each candidate is a pair sharing a goal and at least one cell — a pair worth a judgment call, never a decision.
2. For each candidate pair, decide whether they are the **same test**. "Find the oldest failing job on prod0" and "which prod0 job failed longest ago" are one test; two scenarios differing only in outcome class are not. Mark the folded one `status: "duplicate"` with `duplicate_of` naming the survivor.
3. Promote every scenario you are keeping from `proposed` to `active`. A scenario left `proposed` is not instantiated, and `refs.check_instances` reports one that was.
4. Build `capability_matrix`: one cell per capability × outcome-class pair in the world model — **every** pair, none omitted and none invented. `scenario_ids` lists the scenarios claiming it; `covered` is true iff at least one of them is `proposed` or `active`.
5. Build `goal_matrix`: one row per goal. `hop_depths_expected` is copied from the goal's `expected_hop_depths`; `hop_depths_present` is derived from the `hop_depth` of the scenarios in `scenario_ids`; `covered` is true iff the row has a live scenario **and** every expected depth is present. A goal exercised at one depth of two is a partial row, and calling it covered is how the goal denominator reaches 100% without testing the hard half.
6. Compute `covered`, `total` and `pct` for both matrices from the rows themselves. `refs._check_matrix_arithmetic` recomputes all three.
7. **Justify every uncovered row with a hole**, and give no hole for a covered row. `refs.check_coverage` checks both directions: without both, a report could show 60% and explain none of the missing 40%. A hole whose cause is a world-model gap gets `reason: "blocked_by_gap"` and `gap_id`.
8. Fill `progress`: `new_cells_this_round` and `rounds_without_progress`.
9. Compute `verdict`. It is *computed here* and *acted on by the orchestrator* — scoring does not decide to iterate (§4). `converged` when no closable hole remains; `halted_no_progress` when a round added no new cell; `halted_round_cap` at `max_rounds`; `continue` otherwise.
10. Write the same document to `03-coverage/round-<N>.json` **and** `03-coverage/latest.json`. `validate --stage score` requires `latest.json` by name: a score stage that wrote the round file and forgot the pointer used to pass both gates with every coverage check bypassed.

**Invariants:**

1. The capability matrix has exactly one cell per world-model capability × outcome-class pair.
2. The goal matrix has exactly one row per world-model goal.
3. `covered`, `total` and `pct` agree with the rows in both matrices.
4. Every `scenario_ids[]` entry names a scenario in `02-scenarios.json`.
5. A row marked `covered` is credited to at least one scenario that is still `proposed` or `active`. A rejection reopens the row (§5), so a row credited only to rejected or duplicate scenarios must be recomputed as a hole.
6. Every uncovered row has exactly one hole; no covered row has one.
7. `denominator_version` equals the world model's.
8. `round` does not exceed `manifest.limits.max_rounds`.
9. Every scenario you mark `duplicate` has `duplicate_of` naming a scenario that is not itself a duplicate.
10. `latest.json` and `round-<N>.json` have identical content.

**Refusal conditions:**

| Trigger | Required action |
|---|---|
| A candidate pair is genuinely ambiguous — arguably the same test, arguably not | Keep both `active` and say why in the round file's hole justifications or the orchestrator's decision. Folding a distinct test loses a cell; keeping a duplicate costs one wasted instantiate. Prefer the cheaper error and record the call. |
| A cell cannot be covered because the world model has a gap | Write the hole with `reason: "blocked_by_gap"` and `gap_id`. Never `not_yet_attempted` — that says another round could close it, and no round can. |
| The scenario list claims a cell the world model does not have | Do not invent the cell to make the matrix balance. Report it: layer 2 will name it, and the propose stage produced a scenario against a cell that does not exist. |
| Your computed `pct` disagrees with the matrix you just wrote | Recompute rather than adjusting the number. A hand-adjusted total is the one defect that makes every downstream percentage meaningless. |

**Test file** — `tests/unit/test_skills_score.py`:

```python
"""tg-score's contract, and the vocabularies it must be complete over.

This stage writes the numbers every later judgment is measured against, so the
completeness checks here are about vocabulary coverage: a verdict it cannot
name is a loop state it cannot report, and a hole reason it cannot name is an
uncovered cell it will mislabel as closable.
"""

from __future__ import annotations

from testgen.artifacts import read_json
from testgen.cli import subcommand_names
from testgen.skills import SECTIONS, load, skills_dir
from testgen.validate import ARTIFACT_SCHEMAS, STAGE_ARTIFACTS, schema_dir

SKILL = skills_dir() / "tg-score" / "SKILL.md"


def _coverage_schema():
    return read_json(schema_dir() / ARTIFACT_SCHEMAS["coverage"])


def test_the_contract_matches_the_stage_gate():
    skill = load(SKILL)
    assert skill.contract["stage"] == "score"
    assert set(skill.contract["schemas"]) == set(STAGE_ARTIFACTS["score"])


def test_it_writes_both_the_round_file_and_the_latest_pointer():
    """validate --stage score requires latest.json by name. A score stage that
    wrote only the round file passed both gates with every coverage check
    bypassed, because check_limits and check_coverage both return [] when
    latest.json is absent.
    """
    writes = load(SKILL).contract["writes"]
    assert "coverage_round" in writes
    assert "coverage_latest" in writes


def test_it_writes_the_scenarios_file_because_it_owns_the_status_transitions():
    assert "scenarios" in load(SKILL).contract["writes"]


def test_it_invokes_dedupe_candidates():
    """The deterministic half of dedupe. A skill that eyeballs the scenario list
    instead is doing by judgment what code already did, and inconsistently.
    """
    assert "dedupe-candidates" in load(SKILL).contract["invokes"]
    assert "dedupe-candidates" in subcommand_names()


def test_it_has_the_five_sections():
    assert all(section in load(SKILL).headings for section in SECTIONS)


def test_it_names_every_coverage_verdict():
    """The verdict the orchestrator branches on. A skill that cannot name
    halted_no_progress cannot report a fixpoint, and the loop runs to the cap
    every time.
    """
    enum = _coverage_schema()["properties"]["verdict"]["enum"]
    body = load(SKILL).body
    missing = [verdict for verdict in enum if verdict not in body]
    assert not missing, f"the skill never mentions verdict(s) {missing}"


def test_it_names_every_hole_reason():
    enum = _coverage_schema()["$defs"]["hole"]["properties"]["reason"]["enum"]
    body = load(SKILL).body
    missing = [reason for reason in enum if reason not in body]
    assert not missing, f"the skill never mentions hole reason(s) {missing}"


def test_it_names_both_matrices_and_the_three_summary_fields():
    body = load(SKILL).body
    for name in ("capability_matrix", "goal_matrix", "hop_depths_present",
                 "hop_depths_expected", "covered", "total", "pct"):
        assert name in body, name


def test_it_states_the_status_values_it_may_set():
    """score owns every transition out of `proposed`. The three it may write are
    checked against refs' sets rather than a literal list.
    """
    from testgen.refs import JUDGED_STATUSES

    body = load(SKILL).body
    assert "duplicate" in body and "duplicate_of" in body
    for status in sorted(JUDGED_STATUSES):
        assert status in body, f"the skill never mentions {status!r}"


def test_it_states_that_a_rejection_reopens_a_row():
    """The state test_refs_states.py's post-rejection case exists for. A skill
    that does not know a rejected scenario loses its credit leaves latest.json
    reporting a cell covered by a scenario the adversary threw out -- coverage
    confidently wrong with both gates green.
    """
    body = load(SKILL).body
    assert "rejected" in body
    assert "recompute" in body.lower()
```

**Live exercise:**

- Build a toy run stopped after `propose` (`upto="propose"`), with the toy scenarios' statuses reset to `proposed` so the promotion is real work rather than already done. **Add `upto="propose"` support for this: `build_toy_run` must write `02-scenarios.json` with every status `proposed` when it stops there**, because a fixture handed to score with everything already `active` cannot show whether score promoted anything.
- One dispatch.
- **Pass criteria:** `03-coverage/round-1.json` and `03-coverage/latest.json` both exist and are byte-identical; `testgen validate --stage score` exits 0; `testgen check-refs` exits 0; every kept scenario is now `active`.
- **The properties to look for:** (a) is the matrix complete — 4 cells and 2 rows — or did it write only the cells some scenario claims? (b) With full coverage there are no holes; does it correctly write `holes: []` rather than inventing a hole to look thorough? (c) Is the verdict `converged`, and does the prompt's reasoning for it appear in the round file rather than only in the subagent's reply? (d) **The dedupe judgment, which is the point of this exercise.** In the pre-score state `dedupe-candidates` returns exactly one pair — `scn-open ↔ scn-open-dup`, with `identical_cells: true` — verified against the real code. The two are the same test behind different wording: same goal, same single cell, same `discriminating_fact`. So the skill should fold one, mark it `duplicate` with `duplicate_of` naming the survivor, and leave the survivor `active`. Three failure modes to watch for, in descending order of seriousness: keeping both `active` (the loop then pays for two instantiate fan-outs and the matrix implies two tests cover one cell); marking *both* `duplicate` (a cell with no live credit, which `check_coverage` reports); and skipping `dedupe-candidates` altogether because the scenario list is short enough to eyeball — a skill that skips it when the list is short will skip it when the list is long, and this is the only run where you can see it happen cheaply.

---

## Task 11: `tg-instantiate`

**Files:** create `src/testgen/skills/tg-instantiate/SKILL.md`, `.../exercise.md`; test `tests/unit/test_skills_instantiate.py`.

This and Task 12 are the two that determine whether the suite is worth running. §6: everything before them is bookkeeping by comparison.

**Contract block, verbatim:**

```toml
stage = "instantiate"
reads = ["world_model", "scenarios"]
writes = ["seed", "expected", "rationale"]
schemas = ["seed", "expected"]
invokes = ["validate", "check-refs"]
```

**Method steps — §6's six numbered steps, and the order *is* the method.** The skill must present them in this order and say that the order matters:

1. **Restate the discriminating fact as a decision problem.** What must the agent determine that it could plausibly get wrong?
2. **Design the distractor set.** The step a naive generator skips, and skipping it is how an all-pass suite happens. A world containing exactly one failing job makes "find the failing job" passable by any agent that calls the API once and reads back the only row. The seed needs near-misses: a record that matches on every dimension but one, one that matches outside the window, one with a superficially similar description. **The distractor set — not `hop_depth` — is what actually sets difficulty.**
3. **Seed the world, respecting the world model's invariants.** A seed violating a `machine:` invariant is not merely unrealistic — a simulation backend *recomputes* those fields, so authored content silently changes and the label is now wrong about a world that no longer exists.
4. **Derive the reference answer from the seed.** Read the answer out of the world you just built. Never write the answer first and hope the world agrees.
5. **Write the assertions with `grounded_in` pointers**, negatives included.
6. **Record the rationale** in `rationale.md` — which distractors exist and why — so a reviewer can judge fairness without reverse-engineering the seed.

**The assertion vocabulary is closed** and the skill must list it: `answer_contains`, `answer_excludes`, `tool_called`, `tool_not_called`, `value_equals`. §7: a skill cannot invent a new assertion kind; adding one is a human change to the verifier. Otherwise skills emit assertions nothing can evaluate, and the schema does not catch it because the *shape* is fine.

**Grounding differs by kind, and the skill must state all three rules:**

- A data kind (`answer_contains`, `answer_excludes`, `value_equals`) carries `grounded_in.seed_pointer` and **no** `capability_id`.
- A trajectory kind (`tool_called`, `tool_not_called`) carries `capability_id` and **no** `grounded_in` — a JSON pointer into seed data would be meaningless for it.
- **`answer_excludes` inverts the check:** the pointer must resolve to *nothing*. The seed must not contain what the assertion says it lacks. This is the rule that makes a `log-does-not-say` test both expressible and verifiable, and it has a consequence the skill must spell out: **an exclusion can never name a value the seed contains.** Ruling out a distractor that *does* exist is not expressible as an exclusion — use `value_equals`, which requires the answer to carry the right token delimited, so a near-miss id does not satisfy it.

**Invariants:**

1. `expected.discriminating_fact` is the scenario's, **copied verbatim**. `refs.check_instances` compares the two strings, because a paraphrase is indistinguishable from substituting an easier fact.
2. Every seed collection is a collection some world-model entity declares; every record carries every declared field and no undeclared field, with declared types.
3. Every `machine:` invariant holds over the seed.
4. Every data assertion's `seed_pointer` resolves within **this scenario's own** seed. It can never reach another scenario's world — that is what the fan-out isolation buys and what layer 2 enforces.
5. Every `answer_excludes` pointer resolves to nothing.
6. Every `tool_called` and every `trajectory.operations[]` capability is one the scenario declared in `capability_refs`. Coverage credits the scenario for the cells it declared, so an instance exercising an undeclared capability makes coverage confidently wrong. `tool_not_called` is exempt — forbidding a call to an unclaimed capability is exactly what the kind is for.
7. **An absence-shaped scenario must carry at least one assertion a refusal cannot satisfy** — a `tool_called`, or a positive `answer_contains` on something the seed does contain. This is not a style preference: `verify.score_assertions` scores an exclusion satisfied by absence as a *point*, so an agent answering "I don't have enough information" collects every `answer_excludes` in the task for free. Measured on the toy world: the weak baseline scores 0.4 on each absence-shaped task and 0.0 on the others, and what keeps it under `WEAK_BASELINE_CEILING` is precisely the `tool_called` assertion each absence task also carries. Without this invariant the weak-baseline signal §7 depends on is silently removed for exactly the class of test that most needs it.
8. `answer_reference` is a sentence a person could check against the seed.

**Refusal conditions:**

| Trigger | Required action |
|---|---|
| The `discriminating_fact` cannot be made *uniquely* determined in any seed you can build | Do not write a seed. Report it — the scenario needs re-proposing, and a world where the fact is ambiguous produces a label the adversary will reject anyway. |
| A world-model invariant makes the seed you need impossible | Do not violate the invariant to get the seed you want. Report the conflict: either the invariant is wrong (a `tg-reconcile` defect) or the scenario is (a `tg-propose` defect), and both are above your pay grade. |
| The assertion you need is not in the closed vocabulary | Do not invent a kind. Report what you would need to express. Adding a kind is a human change to `verify.py`. |
| You cannot ground an assertion in the seed | Drop the assertion and say so. An ungrounded assertion is one the reachability gate will reject, and writing it anyway spends the orchestrator's one repair attempt. |
| The scenario needs an entity or field the world model does not declare | Do not add it to the seed. Report it — seed conformance will reject an undeclared field, and a simulation backend would drop or recompute it, so a label relying on it would break at run time. |
| You are tempted to write the answer first and then build a world that fits it | Do not. This is step 4's whole point, and it is the most common way a generated benchmark acquires a label that is true of nothing. |

**Test file** — `tests/unit/test_skills_instantiate.py`:

```python
"""tg-instantiate's contract, and the rules its prompt must state completely.

The vocabulary and grounding checks are the important ones. This stage writes
the artifact that reaches the scorer, and every rule it does not know is a rule
layer 2 will report *after* a fan-out has been paid for.
"""

from __future__ import annotations

from testgen.skills import SECTIONS, load, skills_dir
from testgen.suite.verify import ASSERTION_KINDS, DATA_KINDS, TRAJECTORY_KINDS
from testgen.validate import STAGE_ARTIFACTS

SKILL = skills_dir() / "tg-instantiate" / "SKILL.md"


def test_the_contract_matches_the_stage_gate():
    skill = load(SKILL)
    assert skill.contract["stage"] == "instantiate"
    assert set(skill.contract["schemas"]) == set(STAGE_ARTIFACTS["instantiate"])


def test_it_writes_the_rationale_as_well_as_the_two_gated_artifacts():
    """Section 6 step 6: the rationale is what lets a reviewer judge fairness
    without reverse-engineering the seed. No schema gates it, so nothing but
    this would require it to exist.
    """
    writes = load(SKILL).contract["writes"]
    assert set(writes) == {"seed", "expected", "rationale"}


def test_it_has_the_five_sections():
    assert all(section in load(SKILL).headings for section in SECTIONS)


def test_it_names_every_kind_in_the_closed_vocabulary():
    """Imported from the scorer. A kind the skill does not know is a kind it
    cannot use; a kind it invents scores as failed and the schema does not
    catch it, because the shape is fine.
    """
    body = load(SKILL).body
    missing = [kind for kind in ASSERTION_KINDS if kind not in body]
    assert not missing, f"the skill never mentions assertion kind(s) {missing}"


def test_it_states_that_the_vocabulary_is_closed():
    body = load(SKILL).body.lower()
    assert "closed" in body, "the skill must say the vocabulary cannot be extended"


def test_it_states_the_grounding_rule_for_both_families():
    """Two rules, and getting them backwards is a schema failure per assertion:
    the expected schema forbids capability_id on a data kind and grounded_in on
    a tool kind.
    """
    body = load(SKILL).body
    assert "seed_pointer" in body
    assert "grounded_in" in body
    assert "capability_id" in body
    # Both families named, so the reader can tell which rule applies to which.
    for kind in DATA_KINDS:
        assert kind in body, kind
    for kind in TRAJECTORY_KINDS:
        assert kind in body, kind


def test_it_states_that_an_exclusion_must_resolve_to_nothing():
    """The inverted check. A skill that grounds answer_excludes the way it
    grounds answer_contains produces an assertion the reachability gate rejects
    with "the seed does contain what the assertion claims it lacks".
    """
    body = load(SKILL).body
    assert "answer_excludes" in body
    assert "resolve" in body.lower()


def test_it_requires_an_absence_scenario_to_carry_a_non_exclusion_assertion():
    """The invariant the toy world's smoke run produced.

    verify.score_assertions scores an exclusion satisfied by absence as a point,
    so a task made only of exclusions is substantially passable by an agent that
    answers nothing -- removing the weak-baseline signal exactly where the
    absence-shaped class of test lives. The skill must say so.
    """
    body = load(SKILL).body
    assert "refusal" in body.lower() or "answers nothing" in body.lower()
    assert "answer_excludes" in body
    assert "tool_called" in body


def test_it_states_the_six_method_steps_in_order():
    """Section 6: "order of operations is the method". The distractor step
    before the seed step, and the answer derived *after* the seed exists -- a
    skill that seeds first and derives the answer later has no reachability
    guarantee, and one that writes the answer first has a label that may be
    true of nothing.

    Checked as an ordering of the step markers rather than of prose, so it is a
    structural assertion and not a substring search.
    """
    body = load(SKILL).body
    markers = ["1.", "2.", "3.", "4.", "5.", "6."]
    positions = [body.find(marker) for marker in markers]
    assert all(p >= 0 for p in positions), "the six numbered steps must be present"
    assert positions == sorted(positions), "the numbered steps must appear in order"


def test_it_names_the_distractor_step_as_the_difficulty_lever():
    """Section 6 step 2 is explicit that the distractor set, not hop_depth, is
    what sets difficulty. A skill that treats hop_depth as the lever produces
    deep-but-trivial tasks.
    """
    body = load(SKILL).body.lower()
    assert "distractor" in body
    assert "hop_depth" in load(SKILL).body


def test_it_requires_the_discriminating_fact_to_be_copied_verbatim():
    body = load(SKILL).body
    assert "discriminating_fact" in body
    assert "verbatim" in body.lower()
```

**Live exercise:**

- Build a toy run stopped after `score` (`upto="score"`), then **delete `04-instances/` entirely** so the stage has real work.
- Dispatch **once per active scenario** — four dispatches, each told only its own `scenario_id`. This is the fan-out, and running it as one dispatch over all four would test something the design forbids.
- **Pass criteria:** four instance directories each holding `seed.json`, `expected.json`, `rationale.md`; `testgen validate --stage instantiate` exits 0; `testgen check-refs` exits 0 — which means the reachability gate passed, seed conformance passed, and both `machine:` invariants hold on all four seeds.
- **The properties to look for, in order of what they tell you:**
  1. **Did every seed get distractors?** Count the records. A seed with one ticket for `scn-open` is the all-pass failure mode arriving in the very first real run, and it is the single most informative thing this exercise measures.
  2. **Did `scn-missing` get an assertion a refusal cannot satisfy?** If it is all exclusions, invariant 7 was not followed and the prompt needs to state it harder.
  3. **Did any `comment_count` disagree with the comment records?** That is a `machine:` invariant violation and `check-refs` will name it — note whether the subagent caught it itself before writing, which is what section 4's self-check asks for.
  4. **Did the fan-out hold?** Check each `seed_pointer` resolves in its own seed, and check whether any `rationale.md` mentions another scenario. Cross-contamination is what the fan-out was chosen to prevent, and it is invisible unless you look.

---

## Task 12: `tg-challenge`

**Files:** create `src/testgen/skills/tg-challenge/SKILL.md`, `.../exercise.md`; test `tests/unit/test_skills_challenge.py`.

**Contract block, verbatim:**

```toml
stage = "challenge"
reads = ["scenarios", "seed", "expected"]
writes = ["verdict"]
schemas = ["verdict"]
invokes = ["validate"]
```

`expected` is in `reads` because the skill does read it — **last**, at step 4. The contract cannot express "in this order", so the ordering lives in the Method section and is checked structurally by the test below. §6: an adversary that sees the oracle first anchors on it and confirms almost anything, and pre-registration cannot be obtained from a skill whose context already holds the answer.

**Method steps — the ordering is the whole point (§6):**

1. **Answer the question independently from the seed.** Your input at this step is `seed.json` and the scenario's `user_intent`, and **deliberately not `expected.json`**. Record the answer you reached and the minimum number of tool calls actually needed to reach it.
2. **Search for a second world-consistent answer.** Is the question ambiguous given this world? Look for a distractor that a reasonable reading would select instead.
3. **Check derivability.** Can this be answered from the available capabilities at all, or does it require knowledge the world does not contain?
4. **Only then read `expected.json`** and compare.

**The verdict table, from §6, which the skill must reproduce:**

| Adversary result | Verdict |
|---|---|
| Matches expected, unique, derivable | `accept` |
| Found a second consistent answer | `re-seed` — add distractors or tighten the intent. Once only. |
| Not derivable from the available capabilities | `reject` — the test is unfair |
| Disagrees with expected, and you are right | `reject` or `re-seed` |
| `minimum_tool_calls_found` < the claimed `hop_depth` | `accept`, flagged `difficulty_overstated` |

Row 4 is the highest-value catch in the pipeline: it is how a wrong gold label is found before it becomes a benchmark that punishes correct agents. Row 5 is how the hop-depth distribution gets audited by something other than the stage that claimed it.

**Invariants:**

1. `scenario_id` matches the directory the instance lives in.
2. `uniquely_determined: false` requires at least one `alternative_answers` entry, each with the `world_consistent_reason` that makes it consistent. The schema enforces the count; the *quality* is yours.
3. `verdict: "accept"` is incompatible with `uniquely_determined: false` and with `derivable_without_guessing: false`. `refs.check_verdicts` reports either combination.
4. `minimum_tool_calls_found` is what **you** needed, not what the scenario claimed. If it is below the claimed `hop_depth`, the `difficulty_overstated` flag is **required** — layer 2 reports its absence.
5. `notes` says what you actually did: the answer you reached, and what you ruled out.

**Refusal conditions:**

| Trigger | Required action |
|---|---|
| You cannot answer from the seed at all | Verdict `reject`, `derivable_without_guessing: false`. Do not read `expected.json` first to work out what you were supposed to find — that is the anchoring this stage exists to avoid. |
| You find a second consistent answer | `re-seed`, and record the alternative with its reason. Do not resolve the ambiguity in the label's favour. |
| Your answer disagrees with `expected.json` and you believe you are right | `reject` or `re-seed`, and say plainly in `notes` that the oracle looks wrong. This is row 4, and a skill that defers to the oracle here deletes the pipeline's highest-value catch. |
| You realise at step 4 that you read `expected.json` earlier than step 4 | Say so in `notes` and mark the verdict `re-seed`. A verdict from an anchored adversary is not evidence, and recording that is more useful than a confident `accept` nobody can trust. |
| The seed violates a world-model invariant | Verdict `reject`. The label is about a world the backend would recompute into a different one. |

**Test file** — `tests/unit/test_skills_challenge.py`:

```python
"""tg-challenge's contract, and the ordering that makes it independent.

The ordering test is the one that matters and it is genuinely structural: the
Method section must mention expected.json strictly *after* it mentions
answering from the seed. An adversary that reads the oracle first confirms
almost anything, and no schema can catch that -- the artifact looks identical.
"""

from __future__ import annotations

from testgen.artifacts import read_json
from testgen.skills import SECTIONS, load, skills_dir
from testgen.validate import ARTIFACT_SCHEMAS, STAGE_ARTIFACTS, schema_dir

SKILL = skills_dir() / "tg-challenge" / "SKILL.md"


def _method_body() -> str:
    """The Method section alone, so the ordering below is about that section.

    Uses skills.section_body rather than splitting on "\\n## " by hand: that
    naive split is not fence-aware, and this skill's Method section contains a
    fenced block. A hand-rolled slice would cut at a `## ` line inside it and
    the ordering assertion would then be about a fragment.
    """
    from testgen.skills import section_body

    skill = load(SKILL)
    assert SECTIONS[2] in skill.headings, "the Method section must exist"
    return section_body(skill, SECTIONS[2])


def test_the_contract_matches_the_stage_gate():
    skill = load(SKILL)
    assert skill.contract["stage"] == "challenge"
    assert set(skill.contract["schemas"]) == set(STAGE_ARTIFACTS["challenge"])


def test_it_has_the_five_sections():
    assert all(section in load(SKILL).headings for section in SECTIONS)


def test_the_method_mentions_the_seed_before_it_mentions_the_oracle():
    """The independence, as a position comparison inside one section.

    This is the only mechanical grip there is on the ordering: the verdict
    artifact produced by an anchored adversary is byte-identical to one produced
    by an independent adversary, so nothing downstream can tell them apart. The
    live exercise is the real check; this stops the ordering being *removed*
    from the prompt.
    """
    method = _method_body()
    seed_at = method.find("seed.json")
    oracle_at = method.find("expected.json")
    assert seed_at >= 0, "the Method must name seed.json"
    assert oracle_at >= 0, "the Method must name expected.json"
    assert seed_at < oracle_at, "the Method must reach the seed before the oracle"


def test_the_method_says_the_oracle_is_read_last():
    method = _method_body().lower()
    assert "last" in method or "only then" in method


def test_it_names_every_verdict_value():
    schema = read_json(schema_dir() / ARTIFACT_SCHEMAS["verdict"])
    enum = schema["properties"]["verdict"]["enum"]
    body = load(SKILL).body
    missing = [verdict for verdict in enum if verdict not in body]
    assert not missing, f"the skill never mentions verdict(s) {missing}"


def test_it_names_every_flag_the_schema_allows():
    """difficulty_overstated is the only one today, and it is required when the
    adversary beats the claimed hop_depth -- refs.check_verdicts reports its
    absence, so a skill that does not know it exists produces a finding on a
    verdict that is otherwise correct.
    """
    schema = read_json(schema_dir() / ARTIFACT_SCHEMAS["verdict"])
    enum = schema["properties"]["flags"]["items"]["enum"]
    body = load(SKILL).body
    missing = [flag for flag in enum if flag not in body]
    assert not missing, f"the skill never mentions flag(s) {missing}"


def test_it_names_the_three_boolean_judgments_and_the_call_count():
    body = load(SKILL).body
    for field in ("uniquely_determined", "derivable_without_guessing",
                  "minimum_tool_calls_found", "alternative_answers"):
        assert field in body, field


def test_it_states_that_accept_is_incompatible_with_the_two_negatives():
    """check_verdicts reports accept alongside either false. A skill that does
    not know produces a self-contradictory verdict and spends the repair attempt.
    """
    body = load(SKILL).body
    assert "accept" in body
    assert body.count("uniquely_determined") >= 2, (
        "the field must be named where the judgment is made and where the "
        "incompatibility with accept is stated"
    )


def test_it_tells_the_adversary_to_report_the_oracle_wrong_when_it_is():
    """Row 4 of the verdict table: the highest-value catch in the pipeline, and
    the one a helpful model will not make unless told to.
    """
    body = load(SKILL).body.lower()
    assert "disagree" in body
```

> **Implementer note.** `test_it_states_that_accept_is_incompatible_with_the_two_negatives`
> uses a *count* of a field name as a proxy for "stated in two places". That is
> a weak assertion and you should say so in your report — it is shape 1 with a
> counter attached. If you find a genuinely structural alternative (for example,
> requiring the Invariants section specifically to name both fields, checked by
> slicing that section the way `_method_body` slices Method), prefer it and
> report the change.

**Live exercise:**

- Build a full toy run (`build_toy_run`), then **delete `05-verdicts/` entirely**.
- Dispatch **once per instance** — four dispatches, each told only its own `scenario_id`. The dispatch prompt must **not** name `expected.json`; the skill's own Method decides when it is read.
- **Pass criteria:** four verdict files; `testgen validate --stage challenge` exits 0; `testgen check-refs` exits 0.
- **The properties to look for:**
  1. **Did any adversary reach the oracle's answer independently?** For `scn-blocked` the answer is in the *second* comment, so an adversary that stops at the first comment will reach a different answer — and if it then reports `accept` anyway, it read the oracle first. This is the sharpest single signal the exercise can give.
  2. **What did it report for `minimum_tool_calls_found`?** `scn-blocked` claims `hop_depth: 2` and genuinely needs two calls; `scn-missing` claims 1 and needs 1. An adversary reporting 1 for `scn-blocked` without the `difficulty_overstated` flag produces a layer-2 finding, and reporting 2 for `scn-missing` means it did not actually try.
  3. **Did it find a second consistent answer for `scn-empty`?** It should not — the seed has exactly one shipping ticket and it is open. A `re-seed` here is a false positive worth understanding.
  4. **Note any `notes` field that reads as a summary of `expected.json` rather than of an independent attempt.** That is the anchoring failure, and prose is the only place it shows.

---

## Task 13: `tg-emit` and `tg-orchestrate`

**Files:** create `src/testgen/skills/tg-emit/SKILL.md`, `src/testgen/skills/tg-orchestrate/SKILL.md`, both `exercise.md`; tests `tests/unit/test_skills_emit.py`, `tests/unit/test_skills_orchestrate.py`; extend `tests/unit/test_skills_parse.py` and `tests/unit/test_cli.py` with the two roster tests deferred from Tasks 1 and 2.

Two skills in one task because neither is a judgment stage: `tg-emit` is a thin wrapper over code, and the orchestrator's correctness is almost entirely about the control flow the CLI already implements. Splitting them would put a reviewer gate between two halves of the same "wire the deterministic parts together" job.

### 13a. `tg-emit`

**Contract block, verbatim:**

```toml
stage = "emit"
reads = ["expected", "world_model"]
writes = ["task_dir"]
schemas = ["suite-expected"]
invokes = ["emit", "validate", "check-refs"]
```

**Why it is thin, and the skill must say so** (§7): emit is code because of the reproducibility criterion — if emit were a prompt, two runs with identical stage-4 and stage-5 artifacts could still produce different suites, and variance could no longer be attributed to a stage. This skill exists purely as the human-facing entry point. Its Method is four steps: run `testgen emit --run <run>`; read the paths it printed and the findings it reported; run `testgen validate --stage emit` and `testgen check-refs`; report what was emitted and what was pruned, **and why** — `emit` prunes a package for a scenario that no longer qualifies, and a pruned package is information, not an error.

**Invariants:** it writes nothing itself; every artifact under `06-suite/` comes from `testgen emit`. If it is ever tempted to hand-edit a package, that is a refusal condition, not a fix.

**Refusal conditions:**

| Trigger | Required action |
|---|---|
| `testgen emit` reports findings | Report them verbatim. Do not repair a package by hand — the finding names an upstream artifact, and editing the package leaves the artifact wrong and the suite unreproducible. |
| `emit` pruned a package you expected | Report which scenario and its status. A `rejected` scenario's package is *supposed* to be pruned. |
| `testgen emit` exits 2 | Report it as a harness problem. Exit 2 means the run directory or an artifact could not be read at all, and no repair prompt fixes it. |

**Test file** — `tests/unit/test_skills_emit.py`:

```python
"""tg-emit's contract: a thin entry point that writes nothing itself."""

from __future__ import annotations

from testgen.skills import SECTIONS, load, skills_dir
from testgen.validate import STAGE_ARTIFACTS

SKILL = skills_dir() / "tg-emit" / "SKILL.md"


def test_the_contract_matches_the_stage_gate():
    skill = load(SKILL)
    assert skill.contract["stage"] == "emit"
    assert set(skill.contract["schemas"]) == set(STAGE_ARTIFACTS["emit"])


def test_it_invokes_the_emit_subcommand_rather_than_describing_how_to_emit():
    """The whole reason this skill is thin. A prompt that explained how to build
    a Harbor package would reintroduce the nondeterminism emit-as-code removed.
    """
    assert "emit" in load(SKILL).contract["invokes"]


def test_it_has_the_five_sections():
    assert all(section in load(SKILL).headings for section in SECTIONS)


def test_it_states_why_emit_is_code_rather_than_a_prompt():
    body = load(SKILL).body.lower()
    assert "reproducib" in body


def test_it_states_that_a_pruned_package_is_information_not_an_error():
    body = load(SKILL).body.lower()
    assert "prune" in body
    assert "rejected" in body
```

### 13b. `tg-orchestrate`

**Contract block, verbatim.** No `stage` and no `schemas` — it is not a stage, it dispatches them:

```toml
reads = ["manifest", "world_model", "scenarios", "coverage_latest"]
writes = ["decisions"]
invokes = [
  "check-skills", "validate", "check-refs", "record-stage", "decide",
  "dedupe-candidates", "emit", "smoke",
]
```

**Method — §5's loop, verbatim in structure:**

```
testgen check-skills                        # before anything: a bad skill is not a stage defect
bin/intake                                  # already run by the operator; verify the manifest
fan-out tg-extract per artifact         → validate each
tg-reconcile                            → validate → check-refs
if any gap blocks a downstream stage    → HALT, report, request the missing artifact
loop (round = 1..K):                        # K = manifest.limits.max_rounds
    fan-out tg-propose per hole cluster            → validate
    dedupe-candidates → tg-score                   → validate → check-refs
    on latest.json.verdict: continue → round++ | converged|halted_* → break
    testgen decide --note "round N: <verdict>, <cells covered>/<total>"
fan-out tg-instantiate per active scenario  → validate → check-refs   ← reachability gate
fan-out tg-challenge per instantiated one   → validate
    re-seed → re-dispatch tg-instantiate ONCE, the adversary's alternatives appended
    reject  → mark rejected in 02, recompute coverage
tg-emit → 06-suite/ ; testgen smoke → 07-report.json
```

**The rules the skill must state, each with its reason:**

1. **A dispatched subagent receives exactly three things** (§4): the run directory path, its stage name, and its skill path. No conversational context, no summary of what an earlier stage concluded. That is what makes the artifact contract real, and a helpful orchestrator that pastes the world model into the instantiate dispatch has silently removed the fan-out isolation.
2. **One bounded repair, then halt** (§4, layer 1). On a validation failure, re-dispatch the *same* stage once with the validator's findings appended to the prompt. If it fails again, halt and report. Not a retry spiral.
3. **Exit codes are the branch** (`cli.py`): `0` continue; `1` findings on stdout — a repairable stage defect, worth the one repair attempt; `2` a misconfigured harness — halt, because repeating the stage cannot help. **A `2` is never a stage's fault and must never consume the repair attempt.**
4. **Halt on a blocking gap** (§5): if the world model records a gap whose `blocks` names a stage still to come, stop, report it, and request the missing input artifact. This is the payoff for first-class gaps, and if it never fires on a real run, gap detection is not working.
5. **`record-stage` after every stage**, with the model, the effort, and the skill path. §4's reproducibility hook: two runs are comparable only if those match, and an unrecorded stage makes two unrelated runs compare as comparable.
6. **`decide` at every branch** — each loop round's verdict, every amendment, every repair, every halt. It is the run's append-only lab notebook and it is what makes a run readable afterwards.
7. **Three human gates** (§5), each skippable via `--no-gate`: after 1b (confirm the world model, resolve contradictions, rule on gaps — the highest-leverage review in the pipeline, and the one artifact small enough to read carefully); after the loop (review scenarios and coverage *before* paying for the per-scenario fan-out — this is the cost gate); after 05 (skim rejects and re-seeds, mostly informational). The skill must state that `--no-gate` is what makes the reproducibility criterion possible at all: five identical pipelines cannot be run if a human intervenes in each.
8. **A `re-seed` verdict re-dispatches `tg-instantiate` once**, with the adversary's alternatives appended. A `reject` marks the scenario `rejected` in 02 and recomputes coverage — it does **not** loop back to propose. §5: looping after instantiation makes run cost unbounded, and "87%, 3 cells lost to rejected scenarios" is more informative than a 100% that hides how it got there.
9. **The denominator can move but never silently** (§4): a stage-2 amendment request costs an explicit orchestrator decision, bumps `denominator_version`, and is recorded in `decisions.md`.

**Refusal conditions:**

| Trigger | Required action |
|---|---|
| `check-skills` reports findings | Halt before dispatching anything. A skill whose contract is wrong will produce an artifact in the wrong place, and that is not a stage defect any repair prompt can fix. |
| A stage fails validation twice | Halt and report both findings sets. Do not dispatch a third time. |
| Any subcommand exits 2 | Halt. Do not spend the repair attempt: exit 2 means the harness is misconfigured. |
| A gap blocks a downstream stage | Halt and name the gap and the input artifact that would close it. |
| A human gate is reached and `--no-gate` was not passed | Stop and present the artifact for review. Do not proceed on the assumption the human would have approved. |
| `smoke` reports `broken_labels` | Report it as a suite defect, not an agent result. §7: if the oracle cannot pass its own reference answer, the gold labels or the verifier are broken. |
| You are tempted to pass an earlier stage's conclusion into a later dispatch to save it re-reading | Do not. That is the whole contract. |

**Test file** — `tests/unit/test_skills_orchestrate.py`:

```python
"""tg-orchestrate's contract, and the control-flow rules it must state.

The orchestrator is the one skill whose defects are silent in a *successful*
run: an orchestrator that passes extra context into a dispatch, or retries three
times, or treats an exit 2 as repairable, produces artifacts that all validate.
So these checks are about the rules being present in the prompt, and the live
exercise is a whole-pipeline run.
"""

from __future__ import annotations

from testgen.cli import subcommand_names
from testgen.paths import STAGES
from testgen.skills import CODE_ONLY_STAGES, ORCHESTRATOR, SECTIONS, load, skills_dir

SKILL = skills_dir() / ORCHESTRATOR / "SKILL.md"


def test_it_declares_no_stage_because_it_dispatches_them():
    contract = load(SKILL).contract
    assert "stage" not in contract
    assert "schemas" not in contract


def test_it_writes_the_decisions_log():
    assert load(SKILL).contract["writes"] == ["decisions"]


def test_it_has_the_five_sections():
    assert all(section in load(SKILL).headings for section in SECTIONS)


def test_it_invokes_every_subcommand_the_loop_needs():
    """Not every subcommand -- compare-gold, diff-runs and sample-for-review are
    measurement tools the orchestrator does not run. But every one it does
    declare must be real, which check_contract already enforces; this pins the
    ones the loop cannot work without.
    """
    invokes = set(load(SKILL).contract["invokes"])
    required = {"check-skills", "validate", "check-refs", "record-stage", "decide",
                "dedupe-candidates", "emit", "smoke"}
    assert required <= invokes, f"missing: {sorted(required - invokes)}"
    assert invokes <= set(subcommand_names())


def test_it_names_every_stage_it_dispatches():
    """Derived from STAGES, so adding a stage fails here until the loop mentions
    it. The two code-only stages are named as well: intake mints the run and
    smoke scores it, and an orchestrator that does not know they exist skips them.
    """
    body = load(SKILL).body
    for stage in STAGES:
        if stage in CODE_ONLY_STAGES:
            assert stage in body, f"the loop never mentions the code stage {stage!r}"
        else:
            assert f"tg-{stage}" in body, f"the loop never dispatches tg-{stage}"


def test_it_states_all_three_exit_codes_and_what_each_means():
    """The branch. An orchestrator that treats 2 as repairable spends its one
    repair attempt on a misconfigured harness and then halts anyway, with the
    real cause buried.
    """
    body = load(SKILL).body
    for code in ("0", "1", "2"):
        assert code in body
    lowered = body.lower()
    assert "exit" in lowered
    assert "misconfigur" in lowered, "exit 2's meaning must be stated"


def test_it_states_the_repair_is_bounded_to_one_attempt():
    body = load(SKILL).body.lower()
    assert "once" in body or "one repair" in body
    assert "halt" in body


def test_it_states_the_three_things_a_dispatch_receives():
    """The contract. An orchestrator that threads context through has removed
    the isolation the fan-out design was chosen for, and every artifact still
    validates.
    """
    body = load(SKILL).body.lower()
    assert "run directory" in body
    assert "stage name" in body or "its stage" in body
    assert "skill" in body


def test_it_names_the_three_human_gates_and_the_no_gate_flag():
    body = load(SKILL).body
    assert "--no-gate" in body
    lowered = body.lower()
    assert lowered.count("gate") >= 4, "three gates and the flag must each be described"


def test_it_states_that_a_rejection_does_not_loop_back_to_propose():
    """Deferred on purpose: looping after instantiation makes run cost unbounded.
    An orchestrator that loops instead of reporting an honest hole turns a
    bounded run into an open-ended one.
    """
    body = load(SKILL).body.lower()
    assert "reject" in body
    assert "hole" in body


def test_it_records_each_stage_and_each_decision():
    body = load(SKILL).body
    assert "record-stage" in body
    assert "skill_sha256" in body or "skill hash" in body.lower()
    assert "decide" in body
```

### 13c. The two deferred roster tests

Add to `tests/unit/test_skills_parse.py`:

```python
def test_the_shipped_skills_are_exactly_the_ones_STAGES_demands():
    """Deferred from Task 1 until the last skill landed. Red for eleven tasks
    would have made the suite stop being a signal; red now means a skill is
    genuinely missing.
    """
    assert sorted(s.name for s in discover()) == sorted(expected_skill_names())
```

Add to `tests/unit/test_cli.py`:

```python
def test_check_skills_is_clean_on_the_shipped_skills():
    """The whole point of check-skills existing as a subcommand: the
    orchestrator runs it before a run. This is also the test that fails the
    moment a stage is added to paths.STAGES without a prompt.
    """
    assert main(["check-skills"]) == 0
```

- [ ] **Step 1–7:** the seven shared steps, twice (once per skill), then 13c, then commit.

```bash
uv run pytest -q && uv run ruff check . && uv run ruff format --check .
testgen check-skills && echo "every skill contract clean"
git add -A
git commit -S -s -m "feat: Add tg-emit and tg-orchestrate, completing the skill roster

tg-emit is deliberately thin: emit is code because two runs with identical
stage-4 and stage-5 artifacts must produce identical suites, or variance can no
longer be attributed to a stage. tg-orchestrate carries the loop, the three
human gates, the one bounded repair, and the rule that a dispatched subagent
receives exactly three things -- the orchestrator defect class that is silent in
a successful run.

check-skills is now clean, so the roster test STAGES demands can finally be
asserted rather than deferred.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

**Live exercise — the whole pipeline, once.** This is the only exercise that runs the orchestrator, and it is the first end-to-end behavioural evidence the project has.

- Start from an empty runs directory. Run `testgen intake` on `tests/fixtures/toy/`'s three files by hand, then dispatch `tg-orchestrate` with the run directory and `--no-gate`.
- **Pass criteria:** the run reaches `07-report.json`; `testgen check-refs` exits 0; `manifest.stages` records an entry per dispatched stage; `decisions.md` has at least one line per loop round.
- **The properties to look for, and record all of them in the ledger whatever the outcome:**
  1. **Did it pass anything into a dispatch beyond the three permitted things?** The single most important question in this exercise, and the artifacts cannot answer it — you have to read the dispatch prompts.
  2. **Did it halt or recover correctly on the first validation failure?** If nothing failed, note that too: an unexercised repair path is untested, and it is worth deliberately corrupting one artifact and re-running just that stage to see the branch taken.
  3. **Did it `record-stage` every stage, or only the ones it remembered?**
  4. **Is the report's verdict `healthy`, and if not, is the reason in the labels or the agents?** The toy world with scripted agents gives `healthy`; a real agent roster will not, and the interesting question is whether the orchestrator reports the difference correctly.

---

## Task 14: The negative refusal fixtures

**Files:**
- Create: `tests/fixtures/toy-contradiction/{api.json,notes.md,trace.json}`
- Create: `tests/fixtures/toy-gap/{api.json,notes.md}`
- Create: `tests/unit/test_refusal_fixtures.py`
- Create: `tests/unit/test_refusals_live.py`
- Modify: `tests/toy.py` (fixture directory constants)

**Why these are §9's most valuable tests, quoted:** *"The valuable tests are negative fixtures proving the refusal conditions fire: a deliberately self-contradictory input pair **must** produce a `contradictions` entry; an input with error semantics removed **must** produce a `gap` that blocks stage 2. If those do not fail loudly, §5's refusal conditions are decorative."*

**And why they are hard to test honestly.** The assertion that matters — "the skill refused" — needs a model, so it lives behind the `live` marker. That leaves a trap §8 names directly: the *fixture-cannot-reach* shape, where "a fixture with one of everything cannot distinguish 'the skill refused correctly' from 'the skill never checked'". So each fixture gets **two** layers:

1. **A CI test that the fixture still contains the defect it was built around.** A fixture that lost its contradiction in an edit would let the live test pass for the wrong reason forever, and nobody would know. This is checkable without a model: read both files and assert they disagree on the specific documented point.
2. **A live test that the refusal fires.** Marked `live`, skipped by default.

### 14a. The contradiction fixture

`tests/fixtures/toy-contradiction/` is the toy world with the disagreement made **unresolvable**: `notes.md` states that `get_ticket` on an unknown id returns an error *and* that the store never errors on a read, while `trace.json` shows an empty object. Unlike the golden fixture — where the notes are newer and the trace is older, so `preferred_a` is defensible — here nothing in either artifact settles which is right, so the only honest resolution is `unresolved`.

Design it so the disagreement is:
- **stated in both artifacts**, not inferred from one;
- **about the same capability and outcome class**, so it lands in one contradiction rather than two unrelated claims;
- **undecidable from the artifacts**, with no timestamp, version, or precedence hint that would let a model reasonably prefer one.

### 14b. The gap fixture

`tests/fixtures/toy-gap/` is the toy world with **all error and empty semantics removed**: `api.json` declares the two actions and the entities but says nothing about what happens when a queue has no tickets or an id does not exist, and `notes.md` describes only the happy path. There is no `trace.json` — a trace would leak the behaviour back in.

The correct `tg-reconcile` output is a world model with a **gap** whose `blocks` includes `propose`, because a capability with only a success outcome class cannot support a meaningful `empty` or `not_found` scenario. The incorrect output — and the one §5 says a helpful model will produce — is a world model that invents the error semantics, at which point every downstream stage treats them as fact.

- [ ] **Step 1: Write the CI test**

`tests/unit/test_refusal_fixtures.py`:

```python
"""The negative fixtures still contain the defects they were built around.

Not a test of any skill -- a test of the fixtures. A contradiction fixture that
lost its contradiction in an edit would let the live refusal test pass forever
for the wrong reason, and nothing would report it. That is the
fixture-cannot-reach shape, and this file is what closes it.
"""

from __future__ import annotations

import json

from testgen.intake import classify
from tests.toy import CONTRADICTION_DIR, GAP_DIR


def test_the_contradiction_fixture_has_three_readable_inputs():
    names = sorted(p.name for p in CONTRADICTION_DIR.iterdir())
    assert names == ["api.json", "notes.md", "trace.json"]
    for path in CONTRADICTION_DIR.iterdir():
        assert classify(path) in {"mcp_tool_schema", "design_doc", "trace"}


def test_the_notes_and_the_trace_disagree_about_the_unknown_id_case():
    """The defect the fixture exists to carry. Asserted on the artifacts, so an
    edit that reconciles them by accident fails here rather than silently
    turning the live test into a tautology.
    """
    notes = (CONTRADICTION_DIR / "notes.md").read_text(encoding="utf-8").lower()
    trace = json.loads((CONTRADICTION_DIR / "trace.json").read_text(encoding="utf-8"))
    # The notes assert an error; the trace shows a non-error response.
    assert "error" in notes
    unknown = [
        span for span in trace["spans"]
        if span["input"].get("action") == "get_ticket"
    ]
    assert unknown, "the trace must exercise the unknown-id case"
    assert unknown[-1]["output"] == {}, "the trace must show a non-error response"


def test_the_contradiction_fixture_offers_no_way_to_prefer_one_side():
    """The property that makes `unresolved` the only honest resolution. If the
    notes carried a date or a version and the trace did not, `preferred_a` would
    be defensible and the fixture would be testing the golden world's case again.
    """
    notes = (CONTRADICTION_DIR / "notes.md").read_text(encoding="utf-8").lower()
    for hint in ("deprecated", "as of", "version", "supersede", "replaces", "since"):
        assert hint not in notes, f"the notes hint at precedence with {hint!r}"


def test_the_gap_fixture_has_no_trace_and_no_error_semantics():
    """A trace would leak the behaviour back in, and any mention of an error or
    an empty result would give a model something true to record instead of a gap.
    """
    names = sorted(p.name for p in GAP_DIR.iterdir())
    assert names == ["api.json", "notes.md"]
    text = " ".join(
        (GAP_DIR / name).read_text(encoding="utf-8").lower() for name in names
    )
    for leak in ("error", "not found", "not_found", "empty", "missing", "404"):
        assert leak not in text, f"the gap fixture leaks {leak!r}"


def test_the_gap_fixture_still_describes_the_two_capabilities():
    """The gap must be about outcome semantics only. A fixture that also lost
    the capabilities would produce a world model with nothing in it, and the
    refusal would fire for the wrong reason.
    """
    api = json.loads((GAP_DIR / "api.json").read_text(encoding="utf-8"))
    actions = api["tools"][0]["input_schema"]["properties"]["action"]["enum"]
    assert sorted(actions) == ["find_tickets", "get_ticket"]
```

> **Implementer note.** `test_the_gap_fixture_has_no_trace_and_no_error_semantics`
> forbids six substrings across both files, and writing prose that describes a
> ticket system without ever using the word "missing" is genuinely fiddly. Do
> not relax the list to make writing easier — the list *is* the fixture's
> specification. If a word is truly unavoidable, remove it from the list and say
> in your report which one and why, so the weakening is visible.

- [ ] **Step 2: Write the fixtures**

Build both from `tests/fixtures/toy/`'s files by subtraction, so they differ from the golden world only in the intended way. Add to `tests/toy.py`:

```python
CONTRADICTION_DIR = Path(__file__).resolve().parent / "fixtures" / "toy-contradiction"
GAP_DIR = Path(__file__).resolve().parent / "fixtures" / "toy-gap"
```

- [ ] **Step 3: Write the live refusal tests**

`tests/unit/test_refusals_live.py`. These cannot assert on a model's output from inside pytest — the dispatch happens outside — so they take the shape the project can actually support: **they read a recorded outcome.** Each live test:

1. mints a run from the fixture with real `intake`;
2. asserts the run is ready for `tg-reconcile` (claims present for every input);
3. **skips with an explicit message** if no recorded reconcile output is present, naming the runbook command that produces one;
4. when one *is* present, asserts the refusal fired: a `contradictions` entry with `resolution: "unresolved"` for 14a, and a `gaps` entry whose `blocks` contains `propose` for 14b.

```python
"""The refusal conditions, asserted against a recorded live dispatch.

Marked live because the assertion needs a model's output, and pytest cannot
dispatch a subagent. So the controller runs the dispatch per
docs/running-a-stage-by-hand.md and commits the resulting world model under
tests/fixtures/<name>/recorded/01-world-model.json.

**The recording is committed on purpose.** A refusal observed once and never
again is exactly the decorative refusal condition section 9 warns about; a
committed recording makes it a regression test instead. The cost is that a
recording is evidence of what the skill did *at one commit* -- so changing a
skill obliges re-recording, and that re-recording is a reviewable diff rather
than a silent drift.
"""

from __future__ import annotations

import pytest

from testgen.artifacts import read_json
from tests.toy import CONTRADICTION_DIR, GAP_DIR

pytestmark = pytest.mark.live

RECORDED = "recorded/01-world-model.json"
RERECORD = (
    "no recorded reconcile output. Produce one with the dispatch in "
    "docs/running-a-stage-by-hand.md against {fixture}, then commit it to {path}."
)


def _recorded(fixture):
    path = fixture / RECORDED
    if not path.is_file():
        pytest.skip(RERECORD.format(fixture=fixture, path=path))
    return read_json(path)


def test_a_self_contradictory_input_pair_produces_an_unresolved_contradiction():
    """Section 9's first negative: the pair must produce a contradictions entry.

    `unresolved` specifically, because this fixture offers nothing that would
    let either side be preferred -- test_the_contradiction_fixture_offers_no_way
    _to_prefer_one_side is what keeps that true. A world model that picked a side
    has silently resolved a real disagreement, which is the failure the
    extract/reconcile split exists to prevent.
    """
    world = _recorded(CONTRADICTION_DIR)
    contradictions = world.get("contradictions", [])
    assert contradictions, "tg-reconcile recorded no contradiction for a contradictory pair"
    resolutions = {entry["resolution"] for entry in contradictions}
    assert "unresolved" in resolutions, (
        f"the contradiction was resolved as {sorted(resolutions)}, but nothing in the "
        "fixture licenses preferring either side"
    )


def test_an_input_with_error_semantics_removed_produces_a_gap_blocking_propose():
    """Section 9's second negative, and the one a helpful model fails: with no
    error semantics stated anywhere, the tempting output is a world model that
    invents them -- after which every downstream stage treats them as fact.
    """
    world = _recorded(GAP_DIR)
    gaps = world.get("gaps", [])
    assert gaps, "tg-reconcile recorded no gap for inputs with no error semantics"
    blocking = [gap for gap in gaps if "propose" in gap.get("blocks", [])]
    assert blocking, (
        f"{len(gaps)} gap(s) recorded but none blocks propose; a capability whose "
        "error and empty behaviour is undocumented cannot support a meaningful "
        "scenario for those outcome classes"
    )


def test_the_gap_fixture_did_not_acquire_invented_outcome_classes():
    """The other half of the test above, and the one that actually catches
    confabulation. A world model can record a gap *and* invent the semantics
    anyway -- at which point the gap is decoration and stage 2 proceeds on
    fiction. So the outcome classes are counted too: with only the happy path
    documented, a capability should carry one success class, not four.
    """
    world = _recorded(GAP_DIR)
    for capability in world.get("capabilities", []):
        kinds = [oc["kind"] for oc in capability["outcome_classes"]]
        invented = [kind for kind in kinds if kind in {"error", "not_found", "empty"}]
        assert not invented, (
            f"{capability['id']} declares outcome class kind(s) {invented}, which no "
            "input artifact describes"
        )
```

> **Implementer note.** `test_the_gap_fixture_did_not_acquire_invented_outcome_classes`
> is the test that earns this file. The gap assertion alone is satisfiable by a
> model that records the gap *and* invents the semantics anyway — a shape-2
> weakness, where the fixture cannot distinguish "refused" from "hedged". If you
> find the two tests disagree on a real recording — a gap recorded *and* an
> invented `not_found` class — that is a finding about `tg-reconcile`'s refusal
> conditions, not a test to relax.

- [ ] **Step 4: Run the exercises and record the outputs**

The controller dispatches `tg-reconcile` against each fixture per the runbook,
then commits the two recorded world models. **Both outcomes are informative and
both get recorded in the ledger:**

- The refusal fires → §5's refusal conditions are working, and there is now a regression test.
- The refusal does **not** fire — the model invents error semantics, or resolves the contradiction silently — → this is the single most important finding the whole plan can produce, because it is the hypothesis under test failing. Do not fix it by weakening the fixture. Strengthen `tg-reconcile`'s section 5, re-record, and **note both attempts in the ledger**, because "the prompt needed strengthening before refusal fired" is the result, not an embarrassment.

- [ ] **Step 5: Commit**

```bash
uv run pytest -q && uv run ruff check . && uv run ruff format --check .
git add -A
git commit -S -s -m "test: Add the negative refusal fixtures and their recorded outcomes

Section 9's most valuable tests: a self-contradictory input pair must produce a
contradictions entry, and an input with error semantics removed must produce a
gap that blocks propose. If those do not fire, the refusal conditions are
decorative.

Each fixture gets two layers, because the assertion that matters needs a model
and would otherwise be untestable in CI: a live test that the refusal fires,
and a CI test that the fixture still contains the defect it was built around --
without the second, a fixture that lost its contradiction would let the first
pass forever for the wrong reason.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 15: README and the spec

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-06-skill-based-test-generator-design.md`

**README.** The "What is here so far" section currently ends with "No skills and no LLM calls yet — those arrive in later plans." That sentence is now wrong and is the first thing to fix. Add:

- the skills table (eight rows: seven stage skills plus the orchestrator, one line each on what judgment it carries);
- `skills.py` and `manifest.py` in the components table;
- the three new subcommands in the Usage section, with a worked `record-stage` and `decide`;
- a short **Running the pipeline** section pointing at `tg-orchestrate` and `docs/running-a-stage-by-hand.md`;
- a note that `make live` exists, what it costs, and that it is not part of `make test`.

`README.md` is **not** ruff-excluded, so any Python in it is formatted — check `make check` after editing.

**Spec.** Write back, in the sections that own each:

1. **§5** — the skills path is `src/testgen/skills/tg-<name>/SKILL.md`, package data, for the same reason the schemas are; the names and responsibilities are unchanged. Note the `## Contract` block and that `check-skills` holds it to `paths.RunPaths`, `validate.STAGE_ARTIFACTS` and the CLI's subparser names. Note that dispatch is by file path rather than Claude Code skill discovery, and why.
2. **§4** — `manifest.stages` now has a writer (`record-stage`), and `decisions.md` now has one (`decide`). Record that before this build the empty stage map made every pair of runs compare as comparable — a check passing because its input was absent.
3. **§7** — the ruling this build measured: `verify.score_assertions` scores an exclusion satisfied by absence as a point, so an absence-shaped scenario made only of exclusions is substantially passable by a refusal. `tg-instantiate` therefore requires at least one assertion a refusal cannot satisfy. Give the measured numbers (weak baseline 0.4 on each absence task, 0.0 elsewhere, 0.2 overall against a 0.30 ceiling).
4. **§8** — mark what this build closed and add a **"Parked from the skills build"** subsection for what it did not. Update the "first slice" status: every component now exists; the aap2 run is Plan 5.
5. **§8's process-changes list** — add what this build learned about testing prompts, and be specific rather than restating the prediction §8 already makes. At minimum: which of the three test-weakness shapes actually recurred in text-level tests; whether "assert structure, not substrings" held up or produced tests too weak to matter; and what the live exercises found that no test could. If a counter turned out not to transfer, say so — the prediction in §8 that fixture reachability "transfers and matters more" is a hypothesis this build is the first to test.
6. **§9** — the golden fixture and the two refusal fixtures now exist; record where they live and the recorded-output convention.
7. **§11** — replace "Produce an implementation plan covering the first slice" with the current next step: run the slice.

- [ ] **Step 1: Update the README, run `make check`**
- [ ] **Step 2: Update the spec's seven sections**
- [ ] **Step 3: Verify every claim in both documents**

For each factual claim you wrote, name the file or command that backs it. A spec
that says `check-skills` cross-checks three things must be right about all
three. Run the commands in the README's Usage section verbatim — a README whose
commands do not run is worse than no README, because a reader trusts it.

- [ ] **Step 4: Commit**

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
git add README.md docs/superpowers/specs/2026-08-06-skill-based-test-generator-design.md
git commit -S -s -m "docs: Record the skills layer in the README and the design spec

Seven reconciliations from this build, each written back into the section that
owns it: the skills' package-data path, the two writers the contract declared
and nobody implemented, the absence-scenario scoring ruling and the invariant it
forced on tg-instantiate, and what testing prompts actually taught us versus
what section 8 predicted it would.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Self-Review

Run against the spec with fresh eyes after the plan was complete. §8's process change #2 says to index by **artifact × layer**, not by spec element × task — because a table keyed on "which task implements this" makes structural gaps invisible. This build's artifacts are prompts, so the index is **skill × contract element × what checks it**.

### 1. Skill × contract element × what checks it

| Skill | `stage` | `reads`/`writes` | `schemas` | `invokes` | 5 sections | Refusals non-empty | Vocabulary completeness | Live exercise |
|---|---|---|---|---|---|---|---|---|
| `tg-extract` | T2 | T2 + T7 (isolation) | T2 | T2 | T2 + T7 | T2 + T7 | T7: `kind`, `derivation` enums | T7 ×3 (fan-out) |
| `tg-reconcile` | T2 | T2 + T8 (barrier) | T2 | T2 | T2 + T8 | T2 | T8: outcome kinds, resolutions, machine forms, blockable stages | T8 ×1 |
| `tg-propose` | T2 | T2 + T9 (append) | T2 | T2 | T2 + T9 | T2 | T9: hole reasons, statuses, limits | T9 ×1 |
| `tg-score` | T2 | T2 + T10 (both coverage paths) | T2 | T2 + T10 (`dedupe-candidates`) | T2 + T10 | T2 | T10: verdicts, hole reasons, statuses | T10 ×1 |
| `tg-instantiate` | T2 | T2 + T11 (`rationale`) | T2 (set equality: seed **and** expected) | T2 | T2 + T11 | T2 | T11: `ASSERTION_KINDS`, both grounding rules, six steps in order | T11 ×4 (fan-out) |
| `tg-challenge` | T2 | T2 | T2 | T2 | T2 + T12 | T2 | T12: verdicts, flags, ordering | T12 ×4 (fan-out) |
| `tg-emit` | T2 | T2 | T2 | T2 + T13 | T2 + T13 | T2 | — (writes nothing) | T13 (whole pipeline) |
| `tg-orchestrate` | T2 (must be **absent**) | T2 + T13 | T2 (must be absent) | T2 + T13 (8 required) | T2 + T13 | T2 | T13: every stage, exit codes, gates | T13 (whole pipeline) |
| *the roster itself* | T2 `check_all` (missing/extra) | — | — | — | — | — | T1: derived from `STAGES` | T13 (`check-skills` clean) |

Two things this table made visible that a task-keyed one did not:

- **Every column has a CI check and a live check, except `invokes` and the roster.** Those two are purely mechanical, which is correct — there is no behaviour to observe in "the subcommand name is spelled right."
- **`tg-emit` has no vocabulary column and no exercise of its own.** That is right for a skill that writes nothing, but it means `tg-emit`'s only real test is the whole-pipeline run in Task 13. Stated rather than hidden.

### 2. Spec coverage

| Spec element | Where |
|---|---|
| §3's six stage skills | T7–T12 |
| §3's `tg-emit` thin skill | T13a |
| §4's `manifest.stages` reproducibility hook | T3 (`record-stage`) |
| §4's `decisions.md` notebook | T3 (`decide`) |
| §4's "run ids and timestamps never come from a skill" | T3 (`manifest.utc_stamp`, one format string) |
| §5's uniform five-section shape | T2 (checks 6, 7) |
| §5's "section 5 is the most important prompt-level decision" | T2 check 7 (non-empty) + a refusal table in every skill task |
| §5's fan-out isolation rule | T7, T11, T12 contracts + each exercise's isolation question |
| §5's orchestrator loop | T13b |
| §5's three human gates and `--no-gate` | T13b |
| §5's dedupe folding into stage 3 | T10 (`invokes` includes `dedupe-candidates`) |
| §6's six instantiate steps, in order | T11 (ordering test) |
| §6's adversary ordering | T12 (position test + exercise question 1) |
| §6's verdict table incl. rows 4 and 5 | T12 |
| §7's closed assertion vocabulary | T2 (consolidation) + T11 (completeness) |
| §9's code-component unit tests | already shipped (832 tests) |
| §9's fixture-based stage tests asserting invariants | T4/T5 fixture + every exercise's `validate` + `check-refs` gate — see the note below |
| §9's negative refusal fixtures | T14 |
| §9's one golden end-to-end fixture | T4 + T5 |
| §10's confabulation risk | refusal tables + T14 |
| §10's silent schema drift risk | T2 (`check-skills`) |
| §10's trivial-suite risk | T11 invariant 7, measured in T5 |
| §10's nondeterminism risk | T3 (`record-stage`) |

**On §9's "fixture-based stage tests asserting invariants, not outputs":** §9 gives three examples — output validates, every claim carries evidence, no capability exists without a claim. All three are already enforced, by layer 1 (`evidence` has `minItems: 1`) and layer 2 (`check_world_model` resolves every `claims[]` reference). So the stage test §9 asks for *is* running `validate` and `check-refs` over a live dispatch's output, which is exactly each exercise's pass criteria. No separate mechanism is needed and none is built. Stated here because "we did not build a thing the spec names" needs to be visible as a decision rather than found as a gap.

**One thing §5 says that this plan implements as a prompt rather than a flag:** `--no-gate`. It is an argument to the *orchestrator skill's invocation*, not a `testgen` subcommand flag, because the gates live in the orchestrator's prompt and no code enforces them. That is a real weakness — a prompt-level flag can be forgotten in a way a CLI flag cannot — and it is the right cost for this slice, since building gate enforcement in code would mean the orchestrator stops being a skill. **Recorded as a parked finding for Task 15 to write into §8.**

### 3. Placeholder scan

Searched for every pattern the writing-plans skill forbids. Two initially failed and both are now fixed: Task 6's skip-behaviour test and Task 14's live refusal tests were described in comments rather than written, which is "write tests for the above" with better manners. Both are now complete code.

What remains, deliberately, and is not a placeholder:

- **Tasks 7–13 do not contain the `SKILL.md` prose.** They contain the contract verbatim, every Method step, every invariant, and every refusal condition as trigger → action. This is the plan's one structural departure from "the plan supplies the code", and the reason is §8's own closing note: when a plan supplies both the artifact and its tests, the tests cannot bound the artifact, because both came from the same understanding. For a prompt that collapses entirely — the implementer would contribute only copying. The lists are floors, and a section omitting a listed item is a failed spec review.
- **Several "Implementer note" blocks direct a choice rather than making it** (the `functools.cache` question in T3, `subcommand_names()`'s implementation in T2, the weak assertions flagged in T7 and T12). Each names which option to take and what to report. These are decisions that need a live test run to settle, not gaps.

### 4. Type and interface consistency

Checked every name the plan uses across tasks:

- `skills.py`'s exports are used with the same signatures in T2, T3 (`skill_sha256`), and T7–T13 (`load`, `skills_dir`, `SECTIONS`).
- `RunPaths` attribute names in every contract block exist today: verified by `test_the_RunPaths_names_the_real_skills_use_all_exist` in T2, and by reading `paths.py` — `manifest`, `input_file`, `claims`, `claims_dir`, `world_model`, `scenarios`, `coverage_round`, `coverage_latest`, `seed`, `expected`, `rationale`, `verdict`, `task_dir`, `decisions`. **No new `RunPaths` member is needed by any skill**, which is a good sign about the layout.
- Every `schemas` list matches `STAGE_ARTIFACTS` for its stage: `extract`→`claims`, `reconcile`→`world-model`, `propose`→`scenarios`, `score`→`coverage`, `instantiate`→`seed`+`expected`, `challenge`→`verdict`, `emit`→`suite-expected`.
- Every `invokes` entry is a real subcommand, including the three T3 adds.
- `DATA_KINDS`/`TRAJECTORY_KINDS`/`ASSERTION_KINDS` are introduced in T2 and imported in T4, T5, and T11's tests.
- `tests/toy.py`'s exports are consistent across T4, T5, T6 (`upto=`), T10 (proposed-status variant), T11, T12, T14 (`CONTRADICTION_DIR`, `GAP_DIR`).

One inconsistency found and fixed while reviewing: T4 originally exported only `SIDS`, which T5 and T11 use for the four instantiated scenarios — but adding `scn-open-dup` made `SIDS` ambiguous between "every scenario" and "every instantiated scenario". Now `SIDS` is the instantiated set and `ALL_SCENARIO_IDS` is the full one, with a test pinning that the folded scenario is in the second and not the first.

### 5. What was verified against running code while writing this plan

Not predicted — executed. This is §8 process item 7 applied to the plan itself, and it caught two things.

| Claim | Verified how |
|---|---|
| `answer_excludes` grounded at a missing array index passes the reachability gate | Read `refs.resolve_pointer` (returns `UNSET` for an out-of-range index) and `refs._is_empty` (`UNSET` is empty) |
| The toy world's artifact ids, `stored_as` names and classified kinds | Real `intake` over the three fixture files |
| All seven authored stages clean at layer 1 | `validate_stage` per stage |
| Both `machine:` invariant forms hold over all four seeds | `invariants.evaluate` per (seed, form) |
| `check_all` clean over the complete run | `refs.check_all` |
| `emit` produces four complete packages, `check_all` still clean | `emit.emit_run` |
| `smoke` returns `healthy` with the exact means in T5's table | `smoke.smoke_run` with three scripted agents |
| The duplicate scenario is a candidate pre-score and not post-score | `dedupe.candidate_pairs` on both states |
| Adding the duplicate keeps `validate --stage propose`, `--stage score`, `check_all` and `emit` clean | all four, with it present |

**The two findings that came out of running it:**

1. **`dedupe.candidate_pairs` returned `[]` on the toy world as first designed** — the four scenarios share goals but no cells, and a candidate needs both. So stage 3's deterministic half would have been exercised against nothing, and Task 10's exercise would have measured a skill's dedupe judgment on an empty list. Fixed by adding `scn-open-dup`, verified to yield exactly one pair with `identical_cells: True` before score rules on it and `[]` after.
2. **The weak baseline scores 0.4 on each absence-shaped task**, not 0.0, because `verify.score_assertions` scores an exclusion satisfied by absence as a *point* — so an agent that answers "I don't have enough information" collects every `answer_excludes` in the task for free. This is a real property of the scoring contract, not a fixture accident, and it means **an absence-shaped scenario built only of exclusions is substantially passable by a refusal** — removing the weak-baseline signal §7 depends on for precisely the `log-does-not-say` class of test. It became `tg-instantiate` invariant 7, a fixture-level test in T5, and a §7 spec amendment in T15.

Neither was findable by reading. The first needed `candidate_pairs` run on the actual scenario set; the second needed a scored smoke run.

### 6. What this plan cannot check, and knows it

Stated so the review gate is calibrated rather than surprised:

- **A prompt's structural tests are weak by construction.** "This heading exists", "these enum values appear", "A precedes B" is the whole toolkit. Deletion-mutation has no meaning here — §8 predicted this and it holds. Three tests are flagged in the plan as shape-1 with a counter attached (T7's refusal-length floor, T12's field-count proxy, T11's numbered-step ordering); each names what the live exercise checks that it cannot.
- **A skill's real test is the exercise, and one exercise is one sample.** A prompt that works once may not work twice, and nothing in this plan measures variance. `diff-runs` exists for exactly that and §8 already defers running it to a later slice.
- **The isolation rule cannot be checked from artifacts at all.** An instantiate subagent that read another scenario's seed produces a byte-identical artifact to one that did not, unless the leak happens to show in a value. Every fan-out exercise therefore asks the controller to read the dispatch prompts and the prose, and that is a human check with no mechanical backstop. Named in T11 and T13 as the property to look for; it is the weakest link in this build and should be the first thing a later slice hardens.
