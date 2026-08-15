# MVP Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Rubrica shareable — Apache-2.0 licensed, accurately documented for a
reader with no build context, and guarded so the documentation cannot silently go
stale again.

**Architecture:** Four user-facing documents become fifteen, each owning one
subject, so a fact has an obvious destination. `docs/superpowers/` stays tracked
in full but is demoted from authority to recorded history; two fresh documents
(`docs/design/rationale.md`, `docs/design/limitations.md`) take over as the source
of truth. A new test module asserts the docs still name what the code owns, using
only sets the code already exports — never a phrase.

**Tech Stack:** Python 3.13, `uv`, pytest, ruff, setuptools. No new dependencies.
GitHub Actions for CI.

**Spec:** [`docs/superpowers/specs/2026-08-15-mvp-readiness-design.md`](../specs/2026-08-15-mvp-readiness-design.md)

## Global Constraints

Every task's requirements implicitly include this section.

- **Every commit is signed and DCO signed-off: `git commit -S -s`.** Both flags.
  If signing fails, **stop and report it** — never fall back to an unsigned
  commit, never work around it.
- Attribution trailer is `Assisted-By: Claude (Anthropic AI)
  <noreply@anthropic.com>`. **Never** `Co-Authored-By` or `Made-with`.
- **No change to any stage, skill, schema, check layer, or exit code.** If a task
  appears to require one, that is a finding against the spec: stop the task and
  report it. The only files under `src/` this plan touches are
  `pyproject.toml`-adjacent metadata — none under `src/rubrica/`.
- **No edit to any existing file under `docs/superpowers/`.** The only addition
  there is `docs/superpowers/README.md` (Task 13). Verified in Task 16.
- **No re-recording of any live fixture.** No skill changes, so nothing obliges
  one.
- **No per-file license headers.** `LICENSE` + `NOTICE` + the pyproject SPDX
  field is the whole licensing surface.
- Package version stays `0.1.0`.
- ruff: `line-length = 100`, `select = ["E","F","I","UP","B","SIM"]`, `docs/`
  excluded. Run `make check` before every commit that touches Python.
- **Test counts appear in no user-facing document.** Not corrected — absent.
  Task 15 makes this mechanical.
- CI never runs `make live`: it needs credentials and costs money.
- After every task: `make test` green, `make check` clean, `uv run rubrica
  check-skills` exit 0. A task that leaves any of the three red is not done.

### The user-facing set

Used throughout. `README.md`, `CONTRIBUTING.md`, `CLAUDE.md`, and `docs/**/*.md`
**excluding** `docs/superpowers/**`. Recorded history is not in the set: its
counts are correct records of what was true on their own date, and predicates
that ban counts must not fire on them.

---

## File Structure

**Created:**

| Path | Responsibility |
|---|---|
| `LICENSE` | Apache-2.0, verbatim |
| `NOTICE` | Copyright attribution |
| `CONTRIBUTING.md` | How to work in this repository: setup, gates, commit rules |
| `.github/workflows/ci.yml` | The three gates, on push and pull request |
| `docs/README.md` | Index; the one file permitted to link recorded history |
| `docs/getting-started.md` | One worked run, install to emitted suite |
| `docs/concepts/pipeline.md` | Stages, skills, gates, the round loop, fan-out |
| `docs/concepts/artifact-contract.md` | The one architectural rule, run layout, both check layers, exit codes |
| `docs/concepts/glossary.md` | Every term the schemas and `--help` use, Harbor included |
| `docs/reference/cli.md` | One section per subcommand |
| `docs/reference/artifacts.md` | One entry per artifact kind |
| `docs/design/rationale.md` | The falsifiable question and why the design is shaped this way |
| `docs/design/limitations.md` | Every parked ruling, with the reasoning that parked it |
| `docs/superpowers/README.md` | Preamble marking the tree as dated history |
| `scripts/capture-reservation-trajectories.py` | The capture harness, moved out of `tests/` |
| `tests/unit/test_docs_accuracy.py` | The staleness guard |

**Modified:** `README.md` (rewritten), `CLAUDE.md` (rewritten), `pyproject.toml`,
`.gitignore`, `tests/unit/test_trajectory_fixtures.py:27`,
`tests/fixtures/reservation-trajectories/README.md`.

**Moved:** `docs/running-a-stage-by-hand.md` →
`docs/guides/running-a-stage-by-hand.md`;
`tests/fixtures/reservation-trajectories/capture_harness.py` →
`scripts/capture-reservation-trajectories.py`.

**Deleted:** `docs/pipeline-overview.md`, `docs/pipeline-overview.html`.

### Why the tasks are in this order

The guard predicates are red until the document they check exists, and a task
must not end with a red suite. So each predicate lands in the same task as its
document, and the three policy predicates (no test counts, no counts in
headings, no history citations) land last — in Task 15, after `CLAUDE.md` is
rewritten, because `CLAUDE.md` currently violates all three.

`pipeline-overview.md` is deleted in Task 14, not when its content is copied out
in Tasks 4–6. Two documents carrying the same facts for a few commits is
harmless; deleting the source before its content has a home is not.

**One constraint the policy predicates impose on every earlier task:** no heading
in a new document may count stages, skills, subcommands, or gates. That is why
Task 4 writes `### The human gates` rather than `### The four human gates` — the
gate count already grew from three to four once, which is exactly what the
predicate exists to catch. Prose may state the count freely; only headings are
constrained.

---

## Task 1: Licensing and packaging metadata

**Files:**
- Create: `LICENSE`, `NOTICE`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: nothing.
- Produces: `LICENSE` and `NOTICE` at the repository root, referenced by
  `pyproject.toml`'s `license-files`. Task 2's `CONTRIBUTING.md` links `LICENSE`.

- [ ] **Step 1: Write the Apache-2.0 text to `LICENSE`**

Fetch the canonical text rather than typing it — a hand-transcribed license is a
legal defect:

```bash
curl -fsSL https://www.apache.org/licenses/LICENSE-2.0.txt -o LICENSE
wc -l LICENSE    # expect 202
grep -c "APPENDIX: How to apply the Apache License" LICENSE   # expect 1
```

If the machine has no network, copy the text from another Apache-2.0 repository
on disk and verify the same two checks.

- [ ] **Step 2: Write `NOTICE`**

```
Rubrica
Copyright IBM Corp.

This product includes software developed at IBM Corp.
```

- [ ] **Step 3: Add the metadata to `pyproject.toml`**

Replace the `[project]` block's opening (currently lines 1–9) with:

```toml
[project]
name = "rubrica"
version = "0.1.0"
description = "Skill-based test suite generator for agentic systems"
readme = "README.md"
requires-python = ">=3.13"
license = "Apache-2.0"
license-files = ["LICENSE", "NOTICE"]
authors = [{name = "Jonathan Bnayahu", email = "bnayahu@il.ibm.com"}]
keywords = ["agents", "testing", "test-generation", "llm", "evaluation"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: Apache Software License",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Testing",
]
dependencies = [
    "jsonschema>=4.23",
    "tomli-w>=1.1",
]
```

- [ ] **Step 4: Bump the build backend**

`license = "Apache-2.0"` as a bare SPDX string is PEP 639, which setuptools
implements from 77.0. Below that the field is read as legacy free text and
`license-files` is ignored. In `[build-system]`:

```toml
requires = ["setuptools>=77"]
```

- [ ] **Step 5: Correct the ruff-exclusion comment**

`pyproject.toml` currently justifies excluding `docs/` on the grounds that
"committed design records must not be reformatted". That reason expires when
`docs/` becomes documentation. The exclusion stays; the reason changes. Replace
the comment above `extend-exclude`:

```toml
# Ruff formats Python code blocks inside Markdown. Everything under docs/ is
# prose -- documentation whose code blocks are laid out for reading, and dated
# build records under docs/superpowers/ that are history and must stay verbatim.
# A formatter must not rewrite either. The code that matters is in src/ and
# tests/, where ruff does apply.
extend-exclude = ["docs"]
```

- [ ] **Step 6: Verify the metadata is real, not just present**

```bash
uv pip install -e '.[dev]'
uv run python -c "
from importlib.metadata import metadata
m = metadata('rubrica')
print('License-Expression:', m.get('License-Expression'))
print('Author-email:', m.get('Author-email'))
assert m.get('License-Expression') == 'Apache-2.0', m.get('License-Expression')
print('OK')
"
```

Expected: `License-Expression: Apache-2.0` and `OK`. If it prints `None`, the
setuptools bump did not take effect — check the installed setuptools version with
`uv run python -c "import setuptools; print(setuptools.__version__)"`; it must be
≥ 77.

- [ ] **Step 7: Confirm nothing else broke**

```bash
make check && make test && uv run rubrica check-skills
```

Expected: ruff clean, suite green, exit 0.

- [ ] **Step 8: Commit**

```bash
git add LICENSE NOTICE pyproject.toml
git commit -S -s -m "chore: License under Apache-2.0 and fill in package metadata

Copyright IBM Corp. LICENSE plus NOTICE plus the pyproject SPDX field is the
whole licensing surface -- no per-file headers, so no churn across ~90 source
and test files.

The build backend moves to setuptools>=77 because the bare-string license
field is PEP 639, which setuptools implements from 77.0; below that the field
is read as legacy free text and license-files is ignored. Verified through
importlib.metadata rather than by reading the file back.

The ruff-exclusion comment justified excluding docs/ as 'committed design
records must not be reformatted'. docs/ is becoming documentation, so the
reason is rewritten while the exclusion stays.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 2: CONTRIBUTING.md, CI, and the gitignore

**Files:**
- Create: `CONTRIBUTING.md`, `.github/workflows/ci.yml`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `LICENSE` from Task 1.
- Produces: the phrase "three gates" as `make check` → `make test` → `rubrica
  check-skills`, in that order, in both `CONTRIBUTING.md` and `ci.yml`. Task 15
  verifies the two agree.

This task exists before the documentation tasks because two documents already
claim CI exists (`docs/pipeline-overview.md:32`, `:221`). Making the claim true
is cheaper than deleting it, and every later document may then refer to CI
honestly.

- [ ] **Step 1: Write `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.13"

      - name: Install
        run: uv pip install --system -e '.[dev]'

      # The three gates, in the order CONTRIBUTING.md names them. `make live` is
      # deliberately absent: it dispatches a model, so it needs credentials and
      # costs money on every push.
      - name: Lint and format
        run: |
          uv run ruff check .
          uv run ruff format --check .

      - name: Tests
        run: uv run pytest -q

      - name: Skill contracts
        run: uv run rubrica check-skills
```

The gates are spelled out rather than invoked through `make setup`, because
`make setup` creates a venv the workflow does not need — `--system` installs into
the runner's interpreter directly.

- [ ] **Step 2: Write `CONTRIBUTING.md`**

Required content, in this order. Every item is a rule this repository already
follows; none is invented here.

1. **Setup** — `make setup`, Python 3.13+, `uv`. Note that `README.md`'s commands
   assume the venv is on `PATH` and otherwise need `uv run`.
2. **The three gates** — `make check`, `make test`, `uv run rubrica check-skills`.
   State that CI runs exactly these three and that a red gate is not mergeable.
3. **`make live` is not one of them** — it dispatches a model behind
   `RUBRICA_LIVE` and the `live` marker. Running it against committed recordings
   is free; *producing* a recording costs money. Never in CI.
4. **Commits** — `git commit -S -s`, both flags, `-s` for the `Signed-off-by`
   DCO trailer and `-S` for the cryptographic signature. If signing fails, stop
   and report it; never fall back to unsigned, never disable it. PRs without DCO
   fail CI checks. Retroactive fix: `git rebase --exec 'git commit --amend
   --no-edit -S -s' main`.
5. **AI attribution** — `Assisted-By: Claude (Anthropic AI)
   <noreply@anthropic.com>`. Never `Co-Authored-By` or `Made-with`, because
   GitHub parses those as co-authorship and inflates contributor stats.
6. **Comment density** — high and deliberate. Comments explain *why* a choice was
   made, usually citing a measurement. Match it; do not strip them.
7. **Adding or changing a test predicate** — measure it in both directions before
   committing. Delete or blank the thing it claims to check and confirm it goes
   red; then reword that thing meaning-preservingly and confirm it stays green. A
   predicate nobody has watched fail is not yet a guard. For prose predicates,
   use `RUBRICA_SKILLS_DIR` with a `/tmp` copy rather than editing repo files.
8. **Adding a stage or a skill** — `paths.STAGES` is the ordering and the on-disk
   numbering; `validate.STAGE_ARTIFACTS` maps stage to artifact kinds;
   `cli.SUBCOMMANDS` owns subcommand names; every `SKILL.md` carries a `##
   Contract` block held to those names by `rubrica check-skills`. Adding any of
   them means `docs/reference/cli.md`, `docs/concepts/pipeline.md`, or
   `docs/reference/artifacts.md` must name the new entry —
   `tests/unit/test_docs_accuracy.py` will fail until it does. That failure is
   the guard working.
9. **Where documentation lives** — link `docs/README.md`. State the rule
   plainly: **`docs/superpowers/` is recorded history, not documentation. Do not
   cite it as current, and do not edit anything in it.**
10. **License** — Apache-2.0, link `LICENSE`. Contributions are accepted under it
    via the DCO sign-off.

- [ ] **Step 3: Add the gitignore entry**

Append to `.gitignore`, under the existing agent-harness stanza:

```
.claude/.cc-writes/
```

- [ ] **Step 4: Verify the workflow is valid YAML and the gates match**

```bash
uv run python -c "
import re, pathlib
ci = pathlib.Path('.github/workflows/ci.yml').read_text(encoding='utf-8')
for gate in ['ruff check .', 'ruff format --check .', 'pytest -q', 'rubrica check-skills']:
    assert gate in ci, gate
assert 'make live' not in ci and 'RUBRICA_LIVE' not in ci, 'CI must never run the live tests'
c = pathlib.Path('CONTRIBUTING.md').read_text(encoding='utf-8')
for gate in ['make check', 'make test', 'check-skills']:
    assert gate in c, gate
assert '-S -s' in c, 'CONTRIBUTING.md must name both commit flags'
assert 'Co-Authored-By' in c, 'CONTRIBUTING.md must name the forbidden trailer to forbid it'
print('OK')
"
```

Expected: `OK`.

- [ ] **Step 5: Confirm the suite is still green**

```bash
make check && make test && uv run rubrica check-skills
```

- [ ] **Step 6: Commit**

```bash
git add CONTRIBUTING.md .github/workflows/ci.yml .gitignore
git commit -S -s -m "ci: Add CONTRIBUTING and the CI two documents already claimed

pipeline-overview.md asserted check-skills 'fails in CI' and the toy world
'runs end to end in CI'. Neither was true -- there was no .github/ at all.
Making the claim true is cheaper than deleting it, and lets every later
document refer to CI honestly.

The workflow runs exactly three gates -- ruff, pytest, check-skills -- in the
order CONTRIBUTING.md names them. make live is deliberately absent: it
dispatches a model, so it needs credentials and costs money per push.

CONTRIBUTING.md moves the commit conventions out of CLAUDE.md, where a human
contributor would not look for them.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 3: Move the capture harness out of `tests/`

**Files:**
- Move: `tests/fixtures/reservation-trajectories/capture_harness.py` →
  `scripts/capture-reservation-trajectories.py`
- Modify: `tests/unit/test_trajectory_fixtures.py:27`,
  `tests/fixtures/reservation-trajectories/README.md`

**Interfaces:**
- Consumes: nothing.
- Produces: `scripts/capture-reservation-trajectories.py`, still containing a
  `PROMPTS: list[tuple[str, str]] = [` assignment. Nothing later depends on this
  task.

**Read this before starting.** `tests/unit/test_trajectory_fixtures.py` reads the
harness and `ast.literal_eval`s its `PROMPTS` list to derive the expected trace
ids and their order. It parses the file as *text* — it does not import it — so the
kebab-case filename is fine, and the move costs exactly one constant. Do not
"helpfully" rewrite the `PROMPTS` assignment onto one line: the parser slices from
the marker string `PROMPTS: list[tuple[str, str]] = [` to the next `]`, and that
marker must survive verbatim.

- [ ] **Step 1: Confirm the guards are green before the move**

```bash
uv run pytest tests/unit/test_trajectory_fixtures.py -q
```

Expected: 8 passed. This is the baseline the move must preserve.

- [ ] **Step 2: Move the file**

```bash
git mv tests/fixtures/reservation-trajectories/capture_harness.py \
       scripts/capture-reservation-trajectories.py
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
uv run pytest tests/unit/test_trajectory_fixtures.py -q
```

Expected: FAIL. The module-level `CAPTURE_HARNESS` path no longer exists, so
every test that reads `PROMPTS` errors — `FileNotFoundError` at collection or in
`_prompts()`. This is the failing state the fix resolves.

- [ ] **Step 4: Point the constant at the new location**

In `tests/unit/test_trajectory_fixtures.py`, replace line 27:

```python
CAPTURE_HARNESS = TRAJECTORIES_DIR / "capture_harness.py"
```

with:

```python
# The harness lives in scripts/, not beside the fixture: it is a capture tool
# whose absolute paths only resolve on the machine that ran it, not a test.
# Still read from here, because PROMPTS is the fixture's own record of which
# trace is which -- derived from the source rather than copied into a literal,
# so a re-capture that changes the prompts changes what these tests expect.
CAPTURE_HARNESS = (
    Path(__file__).resolve().parents[2] / "scripts" / "capture-reservation-trajectories.py"
)
```

Add `from pathlib import Path` to the imports if it is not already there — check
first; `ast`, `json`, and `re` are imported at the top of that module and `Path`
may not be.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
uv run pytest tests/unit/test_trajectory_fixtures.py -q
```

Expected: 8 passed, matching Step 1's baseline exactly.

- [ ] **Step 6: Update the fixture README**

In `tests/fixtures/reservation-trajectories/README.md`:

1. Change every `$FIX/capture_harness.py` invocation to
   `$REPO/scripts/capture-reservation-trajectories.py`, and define `REPO` beside
   the existing `FIX` definition.
2. Reword the line 4 spec citation so it reads as provenance rather than
   authority — for example, "captured under the plan recorded at
   `docs/superpowers/specs/2026-08-12-…`", with a clause noting that
   `docs/superpowers/` is dated history and `docs/design/` is current.
3. Add this paragraph, which records a deliberate decision rather than an
   oversight:

```markdown
## The absolute paths are deliberate

`capture-reservation-trajectories.py` hardcodes the source checkout it captured
from, and `trajectories.json` embeds that same path ten times in MLflow
`mlflow.source.name` fields. Neither is sanitised. `trajectories.json` is a
committed recording, and a recording is evidence of what happened — editing one
to look tidier corrupts the evidence it exists to carry. The harness is kept for
the same reason: it records how this fixture was produced. Re-capturing on
another machine means editing those constants, and that edit is the reviewable
part.
```

- [ ] **Step 7: Confirm the whole suite and lint**

```bash
make check && make test && uv run rubrica check-skills
```

Expected: all green. `scripts/` is not ruff-excluded, so the moved file is linted
where it stands — it was linted under `tests/` too, so this should pass without
edits. If ruff now reports findings, fix them without touching the `PROMPTS`
assignment's formatting and re-run Step 5.

- [ ] **Step 8: Commit**

```bash
git add -A tests/unit/test_trajectory_fixtures.py \
  tests/fixtures/reservation-trajectories/README.md \
  scripts/capture-reservation-trajectories.py
git commit -S -s -m "refactor: Move the trajectory capture harness to scripts/

It is a capture tool, not a test, and its two hardcoded constants only
resolve on the machine that captured the fixture -- which made tests/ the
wrong home for it.

test_trajectory_fixtures.py still reads it: PROMPTS is the fixture's own
record of which trace is which, parsed with ast.literal_eval from the source
rather than copied into a literal, so the move costs one constant and the
eight guards keep working. Verified red between the move and the fix.

The absolute paths stay, and the fixture README now says why: trajectories.json
is a recording, and editing a recording to look tidier corrupts the evidence.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 4: `docs/concepts/pipeline.md` and the guard module

**Files:**
- Create: `docs/concepts/pipeline.md`, `tests/unit/test_docs_accuracy.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `tests/unit/test_docs_accuracy.py` with module-level constants
  `REPO_ROOT`, `DOCS`, `PIPELINE`, `CLI_REF`, `ARTIFACTS_REF` and the helper
  `_user_facing() -> list[Path]`. Tasks 7, 8, and 15 append predicates to this
  module and reuse those names exactly — do not rename them.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_docs_accuracy.py`:

```python
"""The user-facing documents still name what the code owns.

Not a test of any behaviour -- a test of the documentation, in the shape of
test_refusal_fixtures.py. Every predicate asserts on a set the code already
exports (`cli.subcommand_names`, `paths.STAGES`, `skills.expected_skill_names`,
`validate.STAGE_ARTIFACTS`), never on a phrase. That is deliberate: a phrase pin
breaks on an innocuous reformat, which has already happened once in this
repository's skill tests, so pinning prose would trade one staleness problem for
a noisier one.

Why this module exists, measured rather than supposed: four hand-maintained
counts were stale simultaneously -- twelve subcommands against seventeen, 1126
tests against 1677, eight skills against nine, three human gates against four --
and CLAUDE.md's own reconciliation of the test count, roughly 800 words updated
commit by commit, was still wrong by 299.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rubrica import paths, skills

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"

PIPELINE = DOCS / "concepts" / "pipeline.md"
CLI_REF = DOCS / "reference" / "cli.md"
ARTIFACTS_REF = DOCS / "reference" / "artifacts.md"


def _user_facing() -> list[Path]:
    """Every document a reader with no build context is expected to read.

    docs/superpowers/ is excluded on purpose. It is recorded history: its counts
    are correct records of what was true on their own date, so a predicate that
    bans a count must not fire on them.
    """
    fixed = [REPO_ROOT / "README.md", REPO_ROOT / "CONTRIBUTING.md", REPO_ROOT / "CLAUDE.md"]
    under_docs = [
        path
        for path in sorted(DOCS.rglob("*.md"))
        if "superpowers" not in path.relative_to(DOCS).parts
    ]
    return [path for path in fixed if path.is_file()] + under_docs


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_the_pipeline_document_names_every_stage_in_contract_order():
    """paths.STAGES is the ordering and the on-disk numbering, so a document
    that lists the stages out of order is describing a different pipeline.

    Order, not just presence: every stage name is an ordinary English word
    (`emit`, `score`, `propose`), so presence alone is nearly satisfiable by
    accident in any prose about a pipeline. Position is not.
    """
    text = _read(PIPELINE)
    positions = []
    for stage in paths.STAGES:
        token = f"`{stage}`"
        assert token in text, f"pipeline.md never names the {stage} stage as {token}"
        positions.append(text.index(token))
    assert positions == sorted(positions), (
        "pipeline.md first names the stages in an order other than paths.STAGES: "
        f"{list(zip(paths.STAGES, positions, strict=True))}"
    )


@pytest.mark.parametrize("skill", sorted(skills.expected_skill_names()))
def test_every_skill_is_named_in_the_pipeline_document(skill):
    """skills.expected_skill_names() derives from STAGES minus the code-only
    stages, plus the orchestrator -- so this cannot drift from the code even if
    someone adds a stage and forgets the skill directory."""
    assert skill in _read(PIPELINE), f"pipeline.md never names {skill}"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/unit/test_docs_accuracy.py -q
```

Expected: FAIL — 10 failures, all `FileNotFoundError` on
`docs/concepts/pipeline.md`. That is the point: the document does not exist yet.

- [ ] **Step 3: Write `docs/concepts/pipeline.md`**

Draw content from `docs/pipeline-overview.md:36-92` and `:94-109`. Do **not**
delete `pipeline-overview.md` — Task 14 does that.

Required content:

1. **The stage table**, all eleven rows, columns `Dir` / `Stage` / `Runs as` /
   `Reads` / `Writes` / `Gate`. Copy the existing table at
   `pipeline-overview.md:41-53` and **add the `rb-triage` row that is missing
   from the skill table below it**. Every stage name appears as a backtick code
   span, in `paths.STAGES` order — the test asserts both.
2. **Why `survey` and `triage` carry no `0N` prefix** — they write
   `00-catalogue.json` and `00-triage.json` ahead of the `manifest.json` and
   `00-inputs/` that `intake` mints once gate 0 has passed, so the numbering
   stays intake's: intake is what fixes the run's identity.
3. **The human gates**, as a `### The human gates` section replacing the current
   `### Three human gates`. The heading carries no count — Task 15's predicate
   rejects one, because this count already grew from three to four. The prose
   below it may say there are four:
   - **Gate 0, after triage** — decides what the run can ever know.
   - **Gate 1, after reconcile** — highest leverage; every downstream stage
     inherits an error here, and it is the one artifact small enough to read
     carefully.
   - **Gate 2, after the coverage loop** — the cost gate, before per-scenario
     fan-out is paid for.
   - **Gate 3, after challenge** — skim rejects and re-seeds; mostly
     informational.
4. **Gate 0 is different in kind**, and why triage cannot hold its own gate:
   gates 1–3 review a judgment made from evidence already in the run, so
   overturning one corrects an inference about the target. Gate 0 decides what
   the run can ever know — nothing downstream of `intake` reads the corpus
   again, so a candidate `rb-triage` declines is gone as completely as if the
   corpus never contained it. The same party selecting the inputs and ratifying
   the selection would make the run unfalsifiable.
5. **Gates 1–3 are skippable with `--no-gate`** and gate 0 is not the
   orchestrator's to skip. State that `--no-gate` is an argument to the
   *orchestrator skill's invocation*, not a `rubrica` flag: the gates live in the
   prompt and no code enforces them. A prompt-level flag can be forgotten in a
   way a CLI flag cannot; that is a known cost, accepted because enforcing the
   gates in code would mean the orchestrator stops being a skill, which is the
   thing being tested.
6. **The 02↔03 loop** — propose targets the holes coverage names; score
   recomputes coverage and returns `continue` / `converged` /
   `halted_no_progress` / `halted_round_cap`. Score *computes* the verdict; only
   the orchestrator acts on it. Bounded by `max_rounds` in the manifest.
7. **Fan-out means isolation, not just parallelism** — from
   `pipeline-overview.md:70-75`, verbatim in substance. An extract subagent sees
   one input file so it cannot smuggle a sibling's conclusion into its claims;
   that is what makes a contradiction between two inputs something the pipeline
   *records* rather than something one reader silently resolves.
8. **The skill table**, one row per skill, `rb-triage` included and
   `rb-orchestrate` last with an explicit note that it is not a stage: it
   declares no `stage` and no `schemas`, dispatches `extract` through `emit`,
   holds gates 1–3, and writes `decisions.md`. It never runs `survey`, never
   dispatches `rb-triage`, and never holds gate 0.
9. **`intake`, `smoke`, and `survey` are code**, so they have no skill and no
   `manifest.stages` entry. Their absence there is not a defect.

Must **not** appear: any "For team review" banner, any build-status table, any
test count, any count of stages/skills/subcommands/gates in a heading, and any
reference to `docs/superpowers`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run pytest tests/unit/test_docs_accuracy.py -q
```

Expected: 10 passed.

- [ ] **Step 5: Measure both predicates in the failure direction**

A predicate nobody has watched fail is not yet a guard. Both edits below are
reverted immediately — `git checkout` is the last command of each.

```bash
# Order predicate: swap two stage names so presence still holds but order breaks.
uv run python - <<'PY'
import pathlib
p = pathlib.Path("docs/concepts/pipeline.md")
t = p.read_text(encoding="utf-8")
t = t.replace("`survey`", "@@TMP@@", 1).replace("`smoke`", "`survey`", 1)
p.write_text(t.replace("@@TMP@@", "`smoke`", 1), encoding="utf-8")
PY
uv run pytest tests/unit/test_docs_accuracy.py -q -k order
# Expected: FAIL, naming the out-of-order positions
git checkout -- docs/concepts/pipeline.md

# Skill predicate: remove one skill name.
sed -i 's/`rb-triage`/`rb-tri4ge`/g' docs/concepts/pipeline.md
uv run pytest tests/unit/test_docs_accuracy.py -q -k skill
# Expected: FAIL on rb-triage only, 8 passed
git checkout -- docs/concepts/pipeline.md
```

- [ ] **Step 6: Measure both predicates in the reword direction**

A guard that breaks on innocuous editing is as bad as no guard.

```bash
# Reflow the whole document's prose without changing meaning: collapse every
# run of spaces and re-wrap. If a predicate depends on layout it dies here.
uv run python - <<'PY'
import pathlib, re
p = pathlib.Path("docs/concepts/pipeline.md")
t = p.read_text(encoding="utf-8")
# only touch prose paragraphs, never table rows or fenced blocks
out, fence = [], False
for line in t.splitlines():
    if line.startswith("```"):
        fence = not fence
    if fence or line.startswith(("|", "#", "-", "  ")) or not line.strip():
        out.append(line)
    else:
        out.append(re.sub(r"\s+", " ", line).strip())
p.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
uv run pytest tests/unit/test_docs_accuracy.py -q
# Expected: 10 passed -- still green
git checkout -- docs/concepts/pipeline.md
```

If either predicate went red here, it is pinning layout rather than content:
rewrite it to search the whole text, not a line.

- [ ] **Step 7: Confirm the whole suite and lint**

```bash
make check && make test && uv run rubrica check-skills
```

- [ ] **Step 8: Commit**

```bash
git add docs/concepts/pipeline.md tests/unit/test_docs_accuracy.py
git commit -S -s -m "docs: Add concepts/pipeline.md, guarded against stage and skill drift

The overview document it draws from was missing rb-triage from its skill
table entirely, titled its gate section 'Three human gates' when there are
four, and gave twelve of seventeen subcommands. Two predicates make the first
two of those impossible to reintroduce.

The stage predicate asserts contract *order*, not presence: every stage name
is an ordinary English word, so presence alone is nearly satisfiable by
accident in any prose about a pipeline. Position is not. The skill predicate
reads skills.expected_skill_names(), which derives from STAGES, so it cannot
drift even if a stage is added and its skill directory forgotten.

Both measured in both directions: red on a swapped stage order and on a
removed skill name, green after reflowing every prose paragraph in the file.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 5: `docs/concepts/artifact-contract.md`

**Files:**
- Create: `docs/concepts/artifact-contract.md`

**Interfaces:**
- Consumes: `docs/concepts/pipeline.md` from Task 4 (links to it).
- Produces: the document `README.md` (Task 14) and `CLAUDE.md` (Task 15) both
  link for the exit-code contract. Nothing imports it.

No new predicate: the exit-code contract is already held by parametrized tests in
`tests/unit/test_cli.py`, and per the spec's own rule a requirement a
deterministic gate already enforces does not also become a doc predicate.

- [ ] **Step 1: Write the document**

Draw from `docs/pipeline-overview.md:16-34` and `:164-192`, and from
`README.md:106-129` and `:360-428`.

Required content:

1. **The one architectural rule** — artifacts on disk are the only channel
   between stages. A stage is dispatched with exactly three things: the run
   directory, the stage name, and its skill file path. No conversational context
   is threaded through. If a stage needs a fact it reads it from an artifact, or
   it does not have it. Fan-out members get a fourth thing: the id of their own
   slice, which is an address rather than context — never a sibling's.
2. **What the orchestrator may append to a re-dispatch** — exactly two things,
   both verbatim machine text, never paraphrased: a repair's gate findings, and
   a re-seed's verdict fields. A paraphrase is the orchestrator's conclusion
   wearing a finding's clothes.
3. **Why the rule is a rule and not a check** — a dispatch that pastes in
   "helpful" context removes the fan-out isolation the design was chosen for, and
   the resulting artifact still validates. Link
   `docs/guides/running-a-stage-by-hand.md` for the isolated-dispatch tooling and
   `docs/design/limitations.md` for why this is the weakest link.
4. **A run on disk** — the directory tree from `pipeline-overview.md:169-192`,
   **with `00-catalogue.json` and `00-triage.json` added**, both above
   `manifest.json`, each with a one-line comment. State that one directory per
   run is the whole state of the system: there is nowhere else state hides.
5. **Two check layers** — keep the heading `## Two check layers` exactly. Layer 1
   is `rubrica validate --stage X`: JSON Schema, one per artifact kind, schemas
   in `src/rubrica/schema/*.json` shipped as package data, `STAGE_ARTIFACTS`
   mapping stage to kind. Layer 2 is `rubrica check-refs`: cross-artifact
   references, seed conformance, reachability, invariant evaluation.
6. **What layer 2 does not do** — it checks that an element *references* a
   resolvable claim, never that the claim *supports* it. Support is semantic; do
   not invent a mechanical check for it. Two real defects lived under that hole
   in the golden fixture itself.
7. **The exit-code contract**, as a table: `0` clean, `1` findings one per line
   on stdout, `2` usage error or an unreadable/misconfigured run. Then the two
   invariants, both of which this repository has violated before: a stage defect
   must never surface as `2`, and a `1` must never have empty stdout. Then the
   third rule, learned the hard way: a `1` must name the *right* artifact —
   `check-refs` over an unreadable `01-claims/` once reported four fabricated
   `no such claim` findings against a correct world model.
8. **Why the split matters to a caller** — a `1` is a repairable stage defect
   worth one retry; a `2` means retrying cannot help.
9. **The mirror rule** — a filesystem problem never surfaces as `1`. `Path.glob`
   swallows `EACCES` and yields nothing, so a check over an unreadable directory
   announced *absence* when its input was merely unreadable. Every run-directory
   listing goes through `paths.list_dir`/`list_json`, which raise `UsageError`.
10. **The two checks worth understanding** — the reachability gate (every data
    assertion in a gold label carries a JSON Pointer into its *own* scenario's
    seed; positive assertions must resolve with the value present,
    `answer_excludes` must resolve to nothing, so a label cannot reach another
    scenario's seed at all) and the denominator check
    (`denominator.capability_cells` must equal the real number of capability ×
    outcome-class pairs; a miscount corrupts every coverage percentage downstream
    and nothing else would notice).
11. **The skill contract** — every `SKILL.md` carries a `## Contract` block (TOML,
    exactly one fence) with `stage`, `reads`, `writes`, `schemas`, `invokes`, and
    five mandatory sections in order: Inputs, Output, Method, Invariants, Refusal
    conditions. `rubrica check-skills` holds each contract to `paths.RunPaths`
    attribute names, `validate.STAGE_ARTIFACTS`, and `cli.SUBCOMMANDS` — it
    validates the *names*, never whether the set is *right*.

Must **not** appear: a test count, a count of stages/skills/subcommands/gates in
a heading, or any reference to `docs/superpowers`.

- [ ] **Step 2: Verify the run tree gained the two files the old one lacked**

```bash
uv run python -c "
import pathlib
t = pathlib.Path('docs/concepts/artifact-contract.md').read_text(encoding='utf-8')
for name in ['00-catalogue.json', '00-triage.json', 'manifest.json', 'decisions.md',
             '01-world-model.json', '03-coverage', '05-verdicts', '06-suite', '07-report.json']:
    assert name in t, name
assert '## Two check layers' in t
print('OK')
"
```

Expected: `OK`.

- [ ] **Step 3: Confirm the suite is green**

```bash
make check && make test && uv run rubrica check-skills
```

- [ ] **Step 4: Commit**

```bash
git add docs/concepts/artifact-contract.md
git commit -S -s -m "docs: Add concepts/artifact-contract.md

The one architectural rule, the run directory, both check layers, the
exit-code contract and its three hard-won rules, the reachability and
denominator checks, and the skill contract -- collected from README.md and
pipeline-overview.md, where they were split across two documents and four
non-adjacent sections.

The run tree gains 00-catalogue.json and 00-triage.json, which the overview's
version never listed even after survey and triage shipped.

No new doc predicate: the exit-code contract is already held by parametrized
tests in test_cli.py, and a requirement a deterministic gate enforces does not
also become a documentation predicate.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 6: `docs/concepts/glossary.md`

**Files:**
- Create: `docs/concepts/glossary.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the definition of `Harbor` that `docs/reference/cli.md` (Task 7)
  links from its `emit` section.

**Why this document is load-bearing rather than filler.** `Harbor` is the format
`rubrica emit` targets. It ships in `rubrica --help` (`cli.py:95`, "compile
accepted instances into Harbor packages"), in `emit.py`'s pinned
`HARBOR_SCHEMA_VERSION = "1.3"`, in `paths.py:255`, and in `suite/test.sh`'s
`/logs/verifier/reward.txt` contract. Every definition of it lives in
`docs/superpowers/`. Under the spec's §4 rule, that makes the term undefined in
everything authoritative: a reader who runs `--help` has nothing to look up.

- [ ] **Step 1: Read the sources before writing a definition**

Do not paraphrase from memory. Read, in this order:

```bash
sed -n '1,60p' src/rubrica/emit.py
sed -n '245,275p' src/rubrica/paths.py
cat src/rubrica/suite/test.sh
sed -n '195,215p;405,420p' src/rubrica/smoke.py
```

- [ ] **Step 2: Write the document**

One `## <term>` section per entry, alphabetical, each two to five sentences.
Required entries:

- **Harbor** — the external task-package format stage 6 targets, pinned at
  `HARBOR_SCHEMA_VERSION = "1.3"` because a suite emitted against one schema and
  scored against another is a silent mismatch. Its verifier contract is a bare
  float in `/logs/verifier/reward.txt`. `emit.py` is the only Harbor-aware module
  in the project; everything upstream of it is format-agnostic. Describe the
  emitted `06-suite/<sid>/` layout with its `agent/` and `verifier/` children.
- **claim** — one atomic, evidence-backed statement about the target, extracted
  from exactly one input artifact, carrying a locator.
- **derivation** — a claim's honesty grade: `stated`, `inferred`, or
  `reverse_engineered`. The point is that "the spec says this" and "I guessed
  from one trace" never look alike downstream.
- **world model** — the single reconciled picture of the target: capabilities,
  entities, goals, invariants, recorded contradictions, recorded gaps, and the
  frozen coverage denominator.
- **contradiction** — two claims that cannot both hold, *recorded* rather than
  resolved, with a `resolution` field.
- **gap** — something no input says anything about, recorded with what it
  `blocks`. A gap naming `propose` halts the round loop.
- **denominator** — the coverage denominator, computed once by reconcile and
  frozen. `denominator.capability_cells` is the count of capability ×
  outcome-class pairs.
- **hole** — an uncovered cell in a coverage matrix, each justified with a reason;
  `blocked_by_gap` carries the gap id, and is not the same as
  `not_yet_attempted`, which implies another round could close it.
- **scenario** — a proposed test, appended by a round of `propose` and never
  renumbered by a later one.
- **seed** — the concrete world one scenario's test runs against, including
  distractors. Every seed value is synthetic by construction; see
  `docs/design/limitations.md` for why.
- **distractor** — a near-miss record placed in the seed so no agent can pass by
  reading back the only matching row. Designed *first*, before the oracle.
- **oracle** — the reference answer, derived *from* the seed rather than the seed
  being built to fit it.
- **verdict** — `rb-challenge`'s ruling on one instance: `accept`, `re-seed`, or
  `reject`.
- **projection** — a manufactured artifact standing in for something the corpus
  lacks, admitted structurally by `rubrica adopt-projection` without touching the
  corpus or the run's identity.
- **objective** — the survey's stated aim (for example `breadth`), recorded in the
  catalogue and read by triage.
- **candidate** — one catalogued file from the corpus, with a bounded digest and
  never its own bytes, ruled on by triage as `admit` / `decline` /
  `needs_projection`.
- **run** — one directory holding the entire state of one pipeline execution.

- [ ] **Step 3: Verify every term the code actually ships is defined**

```bash
uv run python -c "
import pathlib
g = pathlib.Path('docs/concepts/glossary.md').read_text(encoding='utf-8').lower()
for term in ['harbor', 'claim', 'derivation', 'world model', 'contradiction', 'gap',
             'denominator', 'hole', 'scenario', 'seed', 'distractor', 'oracle',
             'verdict', 'projection', 'objective', 'candidate', 'run']:
    assert f'## {term}' in g, term
assert 'reward.txt' in g, 'the Harbor verifier contract must be stated'
assert '1.3' in g, 'the pinned Harbor schema version must be stated'
print('OK')
"
```

Expected: `OK`.

- [ ] **Step 4: Confirm the suite is green, then commit**

```bash
make check && make test && uv run rubrica check-skills
git add docs/concepts/glossary.md
git commit -S -s -m "docs: Define the vocabulary, Harbor first

Harbor ships in rubrica --help, in emit.py's pinned schema version, in
paths.py, and in suite/test.sh's reward.txt contract -- and every definition
of it lived in docs/superpowers/. Demoting that tree to history left the
format the tool's primary output targets undefined in everything
authoritative: a reader who runs --help had nothing to look up.

Written from the source rather than paraphrased -- emit.py, paths.py,
test.sh, smoke.py -- because a glossary that guesses is worse than none.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 7: `docs/reference/cli.md` and the subcommand predicates

**Files:**
- Create: `docs/reference/cli.md`
- Modify: `tests/unit/test_docs_accuracy.py`

**Interfaces:**
- Consumes: `REPO_ROOT`, `CLI_REF`, `_read`, `_user_facing` from Task 4.
- Produces: the heading format `### \`rubrica <name>\`` — one per subcommand. The
  predicate parses that format, so later edits must keep it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_docs_accuracy.py`. Add `import re` to the stdlib
imports and `from rubrica.cli import subcommand_names` to the rubrica imports —
keep them in ruff's import order (`I` is in the select list, so `make check`
catches a misplacement).

```python
# Every subcommand gets its own section, headed `rubrica <name>`. Parsed rather
# than substring-matched because most subcommand names are ordinary words that
# appear in prose anyway -- `validate`, `decide`, `emit`, `smoke` -- so a bare
# `in text` check would pass on a document that merely mentions them.
_CLI_SECTION = re.compile(r"^#{2,4}\s+`?rubrica\s+([a-z-]+)`?", re.MULTILINE)


def _documented_subcommands() -> set[str]:
    return set(_CLI_SECTION.findall(_read(CLI_REF)))


@pytest.mark.parametrize("name", sorted(subcommand_names()))
def test_every_subcommand_has_its_own_section(name):
    assert name in _documented_subcommands(), (
        f"docs/reference/cli.md has no `rubrica {name}` section"
    )


def test_no_section_documents_a_subcommand_that_does_not_exist():
    """The other direction: a section for a command that was renamed or removed
    is a worse defect than a missing one, because it reads as current."""
    stale = _documented_subcommands() - set(subcommand_names())
    assert not stale, f"cli.md documents commands cli.SUBCOMMANDS does not define: {sorted(stale)}"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/unit/test_docs_accuracy.py -q -k subcommand
```

Expected: FAIL — 18 errors, `FileNotFoundError` on `docs/reference/cli.md`.

- [ ] **Step 3: Get the authoritative command list**

```bash
uv run python -c "
from rubrica.cli import SUBCOMMANDS
for name, help_text in SUBCOMMANDS:
    print(f'{name}: {help_text}')
"
for c in $(uv run python -c "
from rubrica.cli import subcommand_names
print(' '.join(subcommand_names()))
"); do echo "=== $c ==="; uv run rubrica "$c" --help; done
```

Write the document from that output, not from memory. `--help` is the contract.

- [ ] **Step 4: Write `docs/reference/cli.md`**

Structure: a short preamble, then one `### \`rubrica <name>\`` section per
subcommand, grouped under `## ` headings by role. Draw worked examples from
`README.md:131-335`, which already has correct ones for eleven of the seventeen.

Preamble content: commands assume the venv is on `PATH` (`make setup` creates
it), otherwise prefix `uv run`; link `docs/concepts/artifact-contract.md` for the
exit-code contract rather than restating it.

Groups and members:

- **`## Minting a run`** — `survey`, `intake`, `adopt-projection`
- **`## Checking`** — `validate`, `check-refs`, `check-skills`
- **`## Feeding a stage`** — `dedupe-candidates`
- **`## The orchestrator's writers`** — `record-stage`, `decide`
- **`## The human's own reports`** — `gate-brief`, `claim-utilisation`,
  `set-limit`
- **`## Emitting and measuring`** — `emit`, `smoke`, `compare-gold`,
  `diff-runs`, `sample-for-review`

Each section carries: a one-line statement of what it does, its required and
optional flags, what it writes, and a worked example with the expected output
shape. Facts that must appear and are absent from today's README:

- `claim-utilisation` — appears in no user-facing document today. It is a
  **report, not a gate**: it always exits clean on a readable run, surfacing each
  input's cited/total claim count for a human to read at gate 1. The
  zero-utilisation *finding* it shares its arithmetic with lives in `check-refs`,
  never here.
- `gate-brief` — same ruling, always exits clean on a readable run. Composes what
  already exists into the reading surface at each of the four gates: the
  objective verdict and grouped declines at 0, utilisation and implied size at 1,
  the coverage matrix at 2, the verdict tally at 3.
- `set-limit` — changes a manifest limit (`max_scenarios` most often) with the
  reason recorded in `decisions.md`, so raising a ceiling is a decision on the
  record rather than a silent hand-edit.
- `survey` — `intake`'s counterpart for the corpus path: walks a corpus, digests
  each candidate, mints the run, writes `00-catalogue.json` rather than a
  manifest, because nothing has been admitted yet.
- `adopt-projection` — admits a manufactured artifact into the catalogue
  structurally, without touching the corpus or the run's identity.
- `record-stage` — computes the digest from `--skill` rather than accepting a
  string: a caller that can pass a digest can pass the wrong one. It hashes the
  whole file, prose included, so a `skill_sha256` that no longer matches the file
  on disk is the hook working, not a defect.
- `decide` — refuses a note that is empty, whitespace-only, or contains a
  newline, at exit 2. A blank entry records that a decision was made and not what
  it was; an embedded newline corrupts a format every reader parses one line per
  entry.
- `emit` — code rather than a prompt, because two runs with identical stage-4 and
  stage-5 artifacts must produce byte-identical suites; otherwise variance can no
  longer be attributed to a stage. Link `docs/concepts/glossary.md#harbor` for
  the output format.
- `dedupe-candidates` — proposes pairs and never decides.
- `smoke` — its three verdicts, from `README.md:337-358`: `healthy`,
  `degenerate_trivial` (indicts the *suite*, not the agent under test),
  `broken_labels` (indicts the gold labels or the verifier — an agent handed the
  reference answer that still cannot pass proves the scoring path is wrong).
  `broken_labels` outranks `degenerate_trivial`. Plus `inconclusive`, which is a
  statement about the run rather than the suite.
- `compare-gold` — writes `measurement/recall.json` and `.md`, prints only the
  path on stdout because stdout is the findings channel, renders the markdown to
  stderr, and exits 1 if any gold task went unmatched. Recall is a smoke signal,
  not a metric to optimize.
- The `--agents` and `--gold` config shapes, copied from `README.md:249-306`.

Must **not** appear: a test count, a count in a heading, or any reference to
`docs/superpowers`.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
uv run pytest tests/unit/test_docs_accuracy.py -q
```

Expected: 28 passed (10 from Task 4, 18 here).

- [ ] **Step 6: Measure both predicates in the failure direction**

```bash
# Missing section: rename one heading so the command is documented nowhere.
sed -i 's/^### `rubrica claim-utilisation`/### `rubrica claim-utilization`/' docs/reference/cli.md
uv run pytest tests/unit/test_docs_accuracy.py -q -k subcommand
# Expected: TWO failures -- the missing-section test for claim-utilisation, AND
# test_no_section_documents_a_subcommand_that_does_not_exist, which now sees a
# section for a command that does not exist. Both directions from one edit.
git checkout -- docs/reference/cli.md

# Reword direction: change every section's prose without touching its heading.
uv run python - <<'PY'
import pathlib
p = pathlib.Path("docs/reference/cli.md")
lines = p.read_text(encoding="utf-8").splitlines()
p.write_text(
    "\n".join(line if line.startswith(("#", "|", "```", " ")) else line.upper() for line in lines)
    + "\n",
    encoding="utf-8",
)
PY
uv run pytest tests/unit/test_docs_accuracy.py -q -k subcommand
# Expected: 18 passed -- the predicate reads headings, not prose
git checkout -- docs/reference/cli.md
```

- [ ] **Step 7: Confirm the whole suite and lint, then commit**

```bash
make check && make test && uv run rubrica check-skills
git add docs/reference/cli.md tests/unit/test_docs_accuracy.py
git commit -S -s -m "docs: Add reference/cli.md, one section per subcommand, guarded

The overview document listed twelve of seventeen subcommands, and
claim-utilisation appeared in no user-facing document at all. Written from
each command's own --help output rather than from memory, because --help is
the contract.

Two predicates, in both directions: every name in cli.SUBCOMMANDS has a
section, and no section documents a command SUBCOMMANDS does not define. The
second matters more than it looks -- a section for a renamed command reads as
current, which is worse than an absent one.

Headings are parsed rather than substring-matched: most subcommand names are
ordinary words that appear in prose anyway (validate, decide, emit, smoke), so
a bare containment check would pass on a document that merely mentions them.
Measured green after upper-casing every non-heading line in the file.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 8: `docs/reference/artifacts.md` and the artifact-kind predicate

**Files:**
- Create: `docs/reference/artifacts.md`
- Modify: `tests/unit/test_docs_accuracy.py`

**Interfaces:**
- Consumes: `ARTIFACTS_REF`, `_read` from Task 4.
- Produces: every artifact kind named as a backtick code span in
  `docs/reference/artifacts.md`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_docs_accuracy.py`, adding `validate` to the existing
`from rubrica import paths, skills` line so it reads
`from rubrica import paths, skills, validate`:

```python
def _artifact_kinds() -> set[str]:
    return {kind for kinds in validate.STAGE_ARTIFACTS.values() for kind in kinds}


@pytest.mark.parametrize("kind", sorted(_artifact_kinds()))
def test_every_artifact_kind_is_documented(kind):
    """Backtick-delimited on purpose: a bare `expected in text` check is
    satisfied by the string `suite-expected`, so two distinct artifact kinds
    would collapse into one and the missing one would never be noticed."""
    assert f"`{kind}`" in _read(ARTIFACTS_REF), (
        f"docs/reference/artifacts.md never names the {kind} artifact as `{kind}`"
    )
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
uv run pytest tests/unit/test_docs_accuracy.py -q -k artifact
```

Expected: FAIL — 12 errors, `FileNotFoundError` on
`docs/reference/artifacts.md`.

- [ ] **Step 3: Get the authoritative kind list and their schemas**

```bash
uv run python -c "
from rubrica import validate
for stage, kinds in validate.STAGE_ARTIFACTS.items():
    print(stage, '->', kinds)
"
ls src/rubrica/schema/
```

- [ ] **Step 4: Write `docs/reference/artifacts.md`**

One `## \`<kind>\`` section per artifact kind, twelve in all: `catalogue`,
`claims`, `coverage`, `expected`, `manifest`, `report`, `scenarios`, `seed`,
`suite-expected`, `triage`, `verdict`, `world-model`. Each carries:

- its schema file under `src/rubrica/schema/`,
- the stage that writes it and the stages that read it,
- its on-disk path within a run, from `paths.py`,
- what it is for, in two or three sentences,
- the fields worth knowing before reading one.

Then two sections for the human-authored configs that no stage produces —
`agents-0.1.json` and `gold-0.1.json` — noting that a config failing its schema
is exit 2, not exit 1, because there is no stage to hand a repair prompt to.

State the two schema-level facts that bite:

- The world model has **no representation for a field's value domain**:
  `capability.params` and `entity.fields` carry only name/type(/required), with
  `additionalProperties: false`. Link `docs/design/limitations.md`.
- **Seed conformance is one-directional** (seed→world only). Link the same.

Must **not** appear: a test count, a count in a heading, or any reference to
`docs/superpowers`.

- [ ] **Step 5: Run the test to verify it passes**

```bash
uv run pytest tests/unit/test_docs_accuracy.py -q
```

Expected: 40 passed (28 + 12).

- [ ] **Step 6: Measure the predicate in both directions**

```bash
# Failure direction, and specifically the collision this predicate exists to
# catch: delete the `expected` section but leave `suite-expected` alone.
sed -i 's/^## `expected`/## the oracle document/' docs/reference/artifacts.md
uv run pytest tests/unit/test_docs_accuracy.py -q -k artifact
# Expected: exactly one failure, for `expected`. If it passes, the predicate is
# matching inside `suite-expected` and the backticks are not doing their job.
git checkout -- docs/reference/artifacts.md

# Reword direction.
uv run python - <<'PY'
import pathlib
p = pathlib.Path("docs/reference/artifacts.md")
lines = p.read_text(encoding="utf-8").splitlines()
p.write_text(
    "\n".join(line if line.startswith(("#", "|", "```")) else line.upper() for line in lines)
    + "\n",
    encoding="utf-8",
)
PY
uv run pytest tests/unit/test_docs_accuracy.py -q -k artifact
# Expected: 12 passed
git checkout -- docs/reference/artifacts.md
```

- [ ] **Step 7: Confirm the whole suite and lint, then commit**

```bash
make check && make test && uv run rubrica check-skills
git add docs/reference/artifacts.md tests/unit/test_docs_accuracy.py
git commit -S -s -m "docs: Add reference/artifacts.md, one entry per schema kind

Twelve artifact kinds, each with its schema, its writing stage, its readers,
its on-disk path, and the fields worth knowing -- plus the two human-authored
configs no stage produces, and why a bad one is exit 2 rather than exit 1.

The predicate matches backtick-delimited names, which is the whole point:
a bare containment check for `expected` is satisfied by `suite-expected`, so
two distinct kinds would collapse into one and the missing one would never be
noticed. Measured by deleting only the `expected` section and confirming
exactly one failure.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 9: Move and de-internalise the hand-dispatch runbook

**Files:**
- Move: `docs/running-a-stage-by-hand.md` →
  `docs/guides/running-a-stage-by-hand.md`
- Modify: the moved file; `scripts/dispatch-stage.sh:6`, `:370`;
  `tests/unit/test_refusals_live.py:5`, `:30`; `tests/unit/test_toy_fixture.py:295`

**Interfaces:**
- Consumes: nothing.
- Produces: the path `docs/guides/running-a-stage-by-hand.md`, which
  `docs/concepts/artifact-contract.md` (Task 5), `README.md` (Task 14), and
  `CLAUDE.md` (Task 15) all link.

- [ ] **Step 1: Move the file**

```bash
mkdir -p docs/guides
git mv docs/running-a-stage-by-hand.md docs/guides/running-a-stage-by-hand.md
```

- [ ] **Step 2: Find every reference to the old path**

```bash
grep -rn "docs/running-a-stage-by-hand" --binary-files=text . \
  --exclude-dir=.git --exclude-dir=.venv --exclude-dir=docs/superpowers
```

Expected: five hits — `scripts/dispatch-stage.sh:6` and `:370`,
`tests/unit/test_refusals_live.py:5` and `:30`,
`tests/unit/test_toy_fixture.py:295`. `README.md` and `CLAUDE.md` also reference
it; leave those to Tasks 14 and 15, which rewrite both files wholesale. Any hit
under `docs/superpowers/` is **left alone** — a dated record is not edited to
track a later rename.

- [ ] **Step 3: Update the five references**

In each, change `docs/running-a-stage-by-hand.md` to
`docs/guides/running-a-stage-by-hand.md`. At
`tests/unit/test_toy_fixture.py:295`, also drop the plan-task framing — the
comment currently reads "…Tasks 7-13 depends on, per
docs/running-a-stage-by-hand.md's table". Rewrite it to name what actually
depends on the checkpoint (the per-stage exercise) rather than a task number no
reader can resolve.

- [ ] **Step 4: Remove the internal framing from the runbook**

Four edits, each replacing text that only parses for someone holding a plan
document. Exact current text on the left.

| At | Replace | With |
|---|---|---|
| `:5-7` | "It is followed by two readers — the controller, after each of Tasks 7–13's skill implementations passes review, and a human debugging a stage that misbehaved in a real run." | "It has two readers: someone exercising a skill they have just changed, and someone debugging a stage that misbehaved in a real run." |
| `:83-84` | "see Task 13's `exercise.md` for its pass criteria." | "see `src/rubrica/skills/rb-orchestrate/exercise.md` for its pass criteria." |
| `:189-191` | "Every `src/rubrica/skills/rb-<stage>/SKILL.md` above exists starting with the task that writes it (Tasks 7–13); until then, this command's shape can be proven against any throwaway file:" | "Every `src/rubrica/skills/rb-<stage>/SKILL.md` above exists in this repository, so each path resolves as written." — then delete the throwaway-file fallback that followed it, which no longer applies. |
| `:248` | "criteria are read by a person (or the controller), not asserted by an" | "criteria are read by a person, not asserted by an" |

- [ ] **Step 5: Fix the two false claims about the live marker**

`:235-237` currently says `uv run pytest -m live -q` is "today: deselected, exit 5
-- no test is live-marked yet (Task 14 adds the first). once one exists: skipped
by default." Live-marked tests exist now. Verify before writing the replacement:

```bash
uv run pytest -m live -q 2>&1 | tail -3
```

Expected: skipped, not exit 5. Then replace those three comment lines with a
single accurate one: the tests are skipped by default and run under
`RUBRICA_LIVE=1` (or `make live`), and they assert against committed recordings
so running them is free — producing a recording is what costs money.

- [ ] **Step 6: Verify nothing still points at the old path**

```bash
grep -rn "docs/running-a-stage-by-hand" --binary-files=text . \
  --exclude-dir=.git --exclude-dir=.venv \
  | grep -v "^./docs/superpowers/" | grep -v "^./README.md" | grep -v "^./CLAUDE.md"
```

Expected: no output. Use `--binary-files=text` as written — this repository has
already had a stale name survive six tasks of sweeps because an `&nbsp;` split
it, so the sweep runs against raw bytes.

- [ ] **Step 7: Verify no task number or "the controller" survives**

```bash
grep -nEi "task[s]? [0-9]|the controller" docs/guides/running-a-stage-by-hand.md
```

Expected: no output.

- [ ] **Step 8: Confirm the suite and lint, then commit**

```bash
make check && make test && uv run rubrica check-skills
git add -A docs/guides scripts/dispatch-stage.sh tests/unit/test_refusals_live.py \
  tests/unit/test_toy_fixture.py
git commit -S -s -m "docs: Move the hand-dispatch runbook into guides/ and de-internalise it

It told its reader it was 'followed by two readers -- the controller, after
each of Tasks 7-13's skill implementations passes review', and cited Task 13's
exercise.md and Task 14 by number. Nobody outside the build can resolve any of
that.

Two claims in it were also false, both found while planning: it said no test
is live-marked yet (four are, and make test reports them skipped), and it
hedged that each SKILL.md exists only 'starting with the task that writes it',
with a throwaway-file fallback for before then. All nine exist.

References under docs/superpowers/ are deliberately not updated: a dated
record is not edited to track a later rename.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 10: `docs/getting-started.md`

**Files:**
- Create: `docs/getting-started.md`

**Interfaces:**
- Consumes: `docs/reference/cli.md` (Task 7), `docs/concepts/pipeline.md`
  (Task 4).
- Produces: the document `README.md` (Task 14) links as its next step.

**Every command in this file must be executed before the file is committed.** A
getting-started guide that was never run is the single most expensive kind of
stale documentation, because it fails for a reader on their first contact with
the project.

- [ ] **Step 1: Do the run yourself, capturing real output**

Work in a scratch directory so nothing lands in the repository:

```bash
export SCRATCH=$(mktemp -d)
uv run rubrica survey --corpus tests/fixtures/corpus-toy --runs-dir "$SCRATCH" \
  --target-name toy --target-interface mcp --objective breadth
# capture the printed run directory
export RUN=$(ls -d "$SCRATCH"/run-*)
uv run rubrica validate --run "$RUN" --stage survey; echo "exit=$?"
cat "$RUN"/00-catalogue.json | head -40
```

Record what each command actually printed. Then walk the rest of the path,
consulting `docs/guides/running-a-stage-by-hand.md` for the triage dispatch, and
`rubrica gate-brief --gate 0`, `rubrica intake --run "$RUN"`.

- [ ] **Step 2: Write the document from that transcript**

Required sections, in order:

1. **Install** — `make setup`; Python 3.13+ and `uv` as prerequisites; the note
   that commands assume the venv is on `PATH`, otherwise prefix `uv run`.
2. **The two ways to start a run** — `survey` (corpus, catalogue, triage, gate 0)
   and `intake --input` (hand-picked, no corpus, no catalogue, no triage record,
   no gate 0). State plainly that `intake --input` still works unchanged.
3. **Path A, walked end to end** against `tests/fixtures/corpus-toy`, with the
   real output of each command. Cover: `survey` → `validate --stage survey` →
   dispatch `rb-triage` → `validate --stage triage` + `check-refs` →
   `gate-brief --gate 0` → `intake --run`.
4. **What runs the prompt stages** — no command in this repository does.
   `rb-orchestrate` does: point an agent at
   `src/rubrica/skills/rb-orchestrate/SKILL.md` with a run directory. It
   dispatches one subagent per stage, gates every artifact before the next stage
   sees it, holds the round loop and gates 1–3, spends at most one repair attempt
   per failure, and records each stage and each branch.
5. **What each dispatch carries** — exactly three things, plus a slice id for the
   three fan-out stages. Link `docs/concepts/artifact-contract.md`.
6. **Where to go next** — `docs/concepts/pipeline.md` for the stages,
   `docs/reference/cli.md` for the commands,
   `docs/guides/running-a-stage-by-hand.md` for exercising one stage,
   `docs/design/rationale.md` for why it is shaped this way.

Must **not** appear: a test count, a count in a heading, or any reference to
`docs/superpowers`.

- [ ] **Step 3: Re-run every command block from the finished document**

Copy each fenced `bash` block out of the file and run it in a fresh scratch
directory. Any command that errors, or prints something the document does not
show, is a defect in the document — fix the document, not the transcript.

```bash
rm -rf "$SCRATCH"; export SCRATCH=$(mktemp -d)
# then re-run each block in order
```

- [ ] **Step 4: Confirm the suite and lint, then commit**

```bash
make check && make test && uv run rubrica check-skills
git add docs/getting-started.md
git commit -S -s -m "docs: Add getting-started.md, every command executed first

Both entry paths -- survey/triage/gate 0, and intake --input for a hand-picked
set -- walked end to end against tests/fixtures/corpus-toy, with the real
output of each command rather than a plausible transcript.

Every fenced block was re-run from the finished file in a fresh scratch
directory before this commit. A getting-started guide nobody executed is the
most expensive kind of stale documentation: it fails a reader on their first
contact with the project.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 11: `docs/design/rationale.md`

**Files:**
- Create: `docs/design/rationale.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the document `CLAUDE.md:13` retargets to in Task 15, replacing its
  pointer at `docs/superpowers/specs/2026-08-06-…`.

This is where the experiment goes. It is referenced prominently from `README.md`
and from `CLAUDE.md`, and it is not the front page.

- [ ] **Step 1: Read the source material**

```bash
sed -n '1,120p' docs/superpowers/specs/2026-08-06-skill-based-test-generator-design.md
sed -n '12,34p;70,92p' docs/pipeline-overview.md
```

Read, then write in your own words for a reader with no build context. Do not
transcribe the spec: it is a design record written for people who were in the
conversation.

- [ ] **Step 2: Write the document**

Required content:

1. **The falsifiable question** — does prompt-carried judgment survive a chain of
   artifact handoffs well enough to produce a suite worth running? State that it
   is falsifiable and what would falsify it.
2. **The yardstick that follows from it** — a change that makes the pipeline more
   likely to produce output while making a stage's judgment less observable is a
   loss, not a win. This sentence is why the document exists: `CLAUDE.md` cites
   it as the test for whether a change is an improvement.
3. **Why artifacts on disk are the only channel** — what it buys (every handoff is
   a file you can open, schema-check, and diff between runs) and what it costs
   (no stage can be told anything; if it needs a fact it must read it).
4. **Why fan-out is about isolation, not parallelism** — an extract member sees
   one input, so a contradiction between two inputs is something the pipeline
   *records* rather than something one reader silently resolves.
5. **Why `emit` is code and not a prompt** — two runs with identical stage-4 and
   stage-5 artifacts must produce byte-identical suites, or variance can no longer
   be attributed to a stage.
6. **Why gate 0 cannot be triage's own gate** — the same party selecting the
   inputs and ratifying the selection would make the whole run unfalsifiable.
   Contrast with gates 1–3, which review a judgment made from evidence already in
   the run.
7. **Why refusal conditions are the most important prompt-level decision** — and
   what makes one decorative: a trigger with no stated action, an action a model
   cannot take, or a condition a model cannot detect from what it can read.
8. **What has actually been observed** — one short paragraph: the pipeline has run
   end to end with a model at every stage against the two-capability toy world,
   and both refusal fixtures produced declines rather than guesses, with the
   outputs committed under `tests/fixtures/<name>/recorded/`. **No numbers**, and
   no build-status table. Point at
   `tests/unit/test_refusal_fixtures.py` and `tests/unit/test_refusals_live.py`
   as the assertions, and at each skill's `exercise.md` for the measured record of
   one dispatch.
9. **What is not yet known** — one paragraph pointing at
   `docs/design/limitations.md`, and the honest statement that one exercise is one
   sample: a prompt that works once may not work twice, and `diff-runs` exists to
   measure exactly that.

Must **not** appear: a test count, a build-status done/pending table, a count in a
heading, or a reference to `docs/superpowers` (the source material is read, not
cited).

- [ ] **Step 3: Verify the yardstick sentence and the absence of numbers**

```bash
uv run python -c "
import pathlib, re
t = pathlib.Path('docs/design/rationale.md').read_text(encoding='utf-8')
assert 'less observable' in t, 'the yardstick sentence must appear -- CLAUDE.md cites it'
assert 'falsifi' in t
assert not re.search(r'\b\d{3,4}\s+(tests?|passed)\b', t), 'no test counts'
assert 'docs/superpowers' not in t
print('OK')
"
```

Expected: `OK`.

- [ ] **Step 4: Confirm the suite and lint, then commit**

```bash
make check && make test && uv run rubrica check-skills
git add docs/design/rationale.md
git commit -S -s -m "docs: Add design/rationale.md -- the experiment, moved off the front page

The falsifiable question stays load-bearing: the sentence CLAUDE.md cites as
its yardstick for judging changes lives here now, in a document written for a
reader with no build context rather than for people who were in the
conversation.

Carries why artifacts are the only channel, why fan-out is isolation rather
than parallelism, why emit is code, why gate 0 cannot be triage's own, and
what makes a refusal condition decorative.

What has been observed is one paragraph with no numbers, pointing at the tests
and exercise records that hold the evidence -- prose that recites measurements
goes stale, and an assertion does not.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 12: `docs/design/limitations.md`

**Files:**
- Create: `docs/design/limitations.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the document `CLAUDE.md:15-17` retargets to in Task 15, replacing
  "Read §8's **Parked from the skills build** table before proposing a fix".

**This is the largest writing task in the plan, and the one where under-delivering
is a real regression rather than a cosmetic one.** `CLAUDE.md` currently sends
every contributor to §8 to stop them re-reporting known issues. If the
replacement gestures at the rulings instead of carrying them, contributors
re-report the bugs and two wasted fix rounds — which this project has already
paid for once — become likely again.

**Three traps specific to this task, all verified:**

1. **§8 is six subsections, not one table.** "Deferred to later slices",
   "Carried forward from the contract-spine build", "Carried forward from the
   closure-and-emit build" (which has both a *closed* and a *still parked*
   table), "Parked from the measurement build", "Parked from the skills build",
   and whatever the ingestion-and-triage build added. `CLAUDE.md` names only the
   last, but a contributor's "bug I just found" may sit in any of them.
2. **Many entries name skills by their pre-rename `tg-` prefix** —
   `tg-orchestrate`, `tg-extract`, `tg-reconcile`, `tg-score`, `tg-instantiate`,
   `tg-challenge`. Those files are `rb-*` today. Copying an entry verbatim would
   put a dead name in current documentation, which is exactly the class of defect
   this plan exists to remove. Translate every one.
3. **Some entries are closed, not parked.** "`bin/diff-runs` execution" is
   deferred-to-slice-2 language for a tool that now ships; the closure-and-emit
   subsection has an explicit *Closed this build* table. A limitations document
   that lists closed items as open is as misleading as one that omits open ones.

- [ ] **Step 1: Enumerate every row, and record the count before triaging**

```bash
SPEC=docs/superpowers/specs/2026-08-06-skill-based-test-generator-design.md
awk '/^## 8\./,/^## 9\./' "$SPEC" > /tmp/section8.md
grep -c "^| " /tmp/section8.md           # total table rows including headers
grep -n "^### " /tmp/section8.md         # every subsection
```

Write down the subsection list and the row count. The verification step in this
task checks that every row was accounted for — carried, or explicitly dismissed
with a reason.

- [ ] **Step 2: Triage each row into one of three buckets**

Build the triage as a scratch list first (not committed):

- **Live** — still true of the code today. Verify each against the source rather
  than trusting the record; several entries are three builds old. Example check
  for the `source_field` entry: `grep -n "source_field" src/rubrica/invariants.py
  src/rubrica/refs.py`.
- **Closed** — fixed since. Do not carry it; do not mention it. The historical
  table remains in the record for anyone who wants the archaeology.
- **Superseded** — the reasoning was overtaken by a later decision (for example a
  deferral to "slice 2" for a tool that now ships).

Cross-check the triage against two other sources, because §8 is not the only
place a ruling lives:

```bash
sed -n '/^## Known limitations/,$p' CLAUDE.md
sed -n '237,266p' docs/pipeline-overview.md
```

Any item in either that is not in your Live bucket is either a genuine addition
or a triage error — resolve it before writing.

- [ ] **Step 3: Write the document**

Structure: a preamble, then one `## ` section per live limitation, grouped by
what a reader would be about to do.

Preamble content, stated plainly: this document exists so a contributor does not
spend a round re-reporting something already ruled on. Each entry states what is
wrong, why it matters, and **why it is parked** — the reasoning, not just the
verdict, because a ruling without its reasoning cannot be re-opened responsibly
when circumstances change.

The three that most often look like new bugs go first, in this order:

1. **The isolation rule is enforceable on artifacts inside a run and
   unenforceable on everything else a subagent can reach.** A member that read a
   sibling's seed produces a byte-identical artifact to one that did not. Both
   observed violations surfaced *only* because a subagent volunteered them in a
   report nobody obliged it to write — one extract member self-reported reading
   both sibling input files, one reconcile member volunteered consulting a
   different fixture outside its declared `reads`. Both outputs were correct and
   independently verified. No schema, no `check-refs`, no digest can catch this;
   the only instrument is a transcript audit at dispatch time. **This is the
   weakest link in the design.** Name `scripts/audit-reads.sh` as the instrument
   that exists.
2. **The world model has no representation for a field's value domain.**
   `capability.params` and `entity.fields` carry only name/type(/required), with
   `additionalProperties: false`. So every seed value is synthetic by
   construction, and a concrete value anywhere downstream of reconcile is a
   *prescription* to `rb-instantiate`, never an assertion about the target. **Do
   not raise findings that require a stage to ground a value against claims** —
   no artifact carries the domains.
3. **Seed conformance is one-directional** (seed→world only), so a seed can drop
   a declared collection, or declare all of them empty, and pass both layers with
   zero findings. Whether *partial* seeds are legal is an open design question:
   it needs a ruling, not a patch.

Then the rest of the Live bucket. At minimum, and each only if Step 2 confirmed
it still holds:

- **Layer 2 checks that an element *references* a resolvable claim, never that
  the claim *supports* it.** Support is semantic; do not invent a mechanical
  check for it. Two real defects lived under that hole in the golden fixture
  itself.
- **`--no-gate` is a prompt-level flag, not a CLI flag.** A prompt-level flag can
  be forgotten in a way a CLI flag cannot. Accepted because enforcing the gates
  in code would mean the orchestrator stops being a skill, which is the thing
  being tested.
- **The orchestrator has no lever for `effort`.** It records the field, but the
  dispatch mechanism cannot supply the value, so every `effort` in a manifest is a
  characterization rather than a setting. `model` and `skill_sha256` carry the
  reproducibility claim.
- **`refs.py` never checks a `machine:` invariant's field names against the
  entity's declared fields.** The invariant loop iterates exactly
  `("collection", "of")`; `field`, `local_key`, `foreign_key`, `order_by` and
  `source_field` are checked by nobody, so a typo in any of the five is caught
  only coincidentally. `invariants.py` reads `source_field` with a `""` default
  rather than the `MISSING` sentinel every other key uses, which is the one typo
  that produces no message at all. Record both, and that the wider missing check
  is the one that would remove the class.
- **`cli.py`'s catch-all names the wrong run for `diff-runs`**, which takes `--a`
  and `--b`. A defect in run *b* surfaces as a malformed artifact in run *a*.
  Still a parseable exit-1 finding, which is strictly better than the empty
  exit 1 it replaced.
- **`dedupe-candidates` maps a stage defect to exit 2** where five other
  subcommands return exit 1 for the same unparseable file. A single-subcommand
  inconsistency in a class otherwise closed.
- **`intake` sits outside the exception net** — its own `try` returns before the
  outer handler.
- **`emit` and `smoke` have no real layer-1 gate**: `STAGE_ARTIFACTS` maps both to
  `()`, so `validate --stage emit` returns 0 unconditionally.
- **`golden scn-empty`'s `answer_excludes` marks a correct, more-informative
  answer wrong** (assertions 0.5, reward 0.6 against the oracle's 1.0), parked
  because the reward it feeds is pinned in three places.
- **One exercise is one sample.** A prompt that works once may not work twice, and
  nothing has yet measured variance. `diff-runs` exists for exactly that.
- **`max_scenarios` has no sizing heuristic yet.** Record what is known — the
  floor for a real target is well above the toy world's — and that the heuristic
  is still owed rather than chosen.

Must **not** appear: a `tg-` prefixed skill name, a test count, a count in a
heading, or a reference to `docs/superpowers` (the source is read, not cited).

- [ ] **Step 4: Verify the translation and the coverage**

```bash
uv run python -c "
import pathlib, re
t = pathlib.Path('docs/design/limitations.md').read_text(encoding='utf-8')
assert 'tg-' not in t, 'a pre-rename skill name survived the distillation'
assert not re.search(r'\b\d{3,4}\s+(tests?|passed)\b', t), 'no test counts'
assert 'docs/superpowers' not in t
for must in ['isolation', 'value domain', 'one-directional', 'references', 'effort',
             'source_field', 'answer_excludes', 'max_scenarios']:
    assert must in t, must
print('OK')
"
```

Expected: `OK`.

- [ ] **Step 5: Verify every §8 row was accounted for**

Walk your Step 2 triage list against the document. Every Live row must have a
section; every Closed and Superseded row must have a one-line note in your
scratch list saying why it was dropped. Paste that scratch list into the commit
message body — it is the evidence that nothing was silently lost, and it is the
only record of the triage.

- [ ] **Step 6: Confirm the suite and lint, then commit**

```bash
make check && make test && uv run rubrica check-skills
git add docs/design/limitations.md
git commit -S -s -m "docs: Add design/limitations.md, carrying every live ruling

CLAUDE.md sends every contributor to the spec's section 8 before they propose
a fix, so that most 'bugs you just found' meet a ruling instead of a fix
round. That pointer now goes here, which means this file has to carry the
rulings rather than gesture at them: a contributor who cannot find the ruling
re-reports the bug, and this project has already paid two wasted fix rounds
for exactly that.

Distilled rather than copied, for three measured reasons: section 8 is six
subsections and CLAUDE.md named only one of them; many entries still use the
pre-rename tg- skill names, which would put dead names in current
documentation; and some entries are closed rather than parked, including a
deferral for a tool that now ships.

Each entry states what is wrong, why it matters, and why it is parked -- the
reasoning, not just the verdict, because a ruling without its reasoning cannot
be re-opened responsibly when circumstances change.

Triage of every section 8 row follows.

<paste the Step 5 scratch list here>

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 13: The history preamble and the docs index

**Files:**
- Create: `docs/superpowers/README.md`, `docs/README.md`

**Interfaces:**
- Consumes: every document from Tasks 4–12 (the index links them all).
- Produces: `docs/README.md` — the **only** file in the user-facing set permitted
  to mention `docs/superpowers`. Task 15's predicate asserts exactly that.

**This is the one permitted addition under `docs/superpowers/`.** Do not touch any
other file in that tree; Task 16 verifies it.

- [ ] **Step 1: Write `docs/superpowers/README.md`**

Short — well under a page. Required content:

1. **What this tree is** — dated design records and implementation plans, written
   during the build, each accurate as of its own date.
2. **What it is not** — documentation. It is not maintained, its counts and
   statuses are snapshots, and some of it names skills by a prefix (`tg-`) that
   was renamed.
3. **Do not cite it as current.** The current documentation is `docs/`; link
   `docs/README.md`, `docs/design/rationale.md` for why the system is shaped this
   way, and `docs/design/limitations.md` for what does not work yet and the
   ruling that parked each item.
4. **Do not edit anything here.** A dated record is not updated to track a later
   rename — that is what makes it a record.
5. **Why it is kept** — the reasoning behind a decision is often only in the
   record that made it, and a fixture or a test may legitimately cite one as
   provenance.

- [ ] **Step 2: Write `docs/README.md`**

An index, grouped, one line per document saying what question it answers:

- **Start here** — `getting-started.md`
- **Concepts** — `concepts/pipeline.md`, `concepts/artifact-contract.md`,
  `concepts/glossary.md`
- **Reference** — `reference/cli.md`, `reference/artifacts.md`
- **Guides** — `guides/running-a-stage-by-hand.md`
- **Design** — `design/rationale.md`, `design/limitations.md`
- **History** — `superpowers/`, with the one-line framing: dated build records,
  superseded by the documents above, kept for provenance and **not to be cited as
  current**.

- [ ] **Step 3: Verify the index links resolve and the history rule reads right**

```bash
uv run python -c "
import pathlib, re
docs = pathlib.Path('docs')
index = (docs / 'README.md').read_text(encoding='utf-8')
missing = [
    target for target in re.findall(r'\]\(([^)#]+)', index)
    if not target.startswith(('http', 'mailto'))
    and not (docs / target.lstrip('./')).exists()
]
assert not missing, f'docs/README.md links nothing: {missing}'
assert 'superpowers' in index, 'the index is the one file that must link history'
print('OK')
"
```

Expected: `OK`.

- [ ] **Step 4: Confirm the suite and lint, then commit**

```bash
make check && make test && uv run rubrica check-skills
git add docs/README.md docs/superpowers/README.md
git commit -S -s -m "docs: Add the docs index, and mark superpowers/ as history

docs/superpowers/ stays tracked in full -- every byte -- but it is recorded
history rather than documentation, and a newcomer meeting a 5,622-line plan
beside a 1,358-line spec would reasonably mistake it for the latter. The
preamble says which it is, that its counts are snapshots, that some of it
names skills by a prefix that was renamed, and that nothing in it should be
edited to track a later rename.

docs/README.md is the index, and the only file in the user-facing set
permitted to mention that tree. Task 15's predicate holds that.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 14: Rewrite `README.md` and delete the overview documents

**Files:**
- Modify: `README.md` (rewritten)
- Delete: `docs/pipeline-overview.md`, `docs/pipeline-overview.html`

**Interfaces:**
- Consumes: every document from Tasks 4–13.
- Produces: a `README.md` under 120 lines that links out rather than explaining.

Today's `README.md` is 432 lines doing eight jobs, and it is where several of the
spec's §2a defects live: "Two more, neither one a gate itself" followed by three
commands, a code table omitting nine modules and `suite/`, and no mention of
`claim-utilisation` at all. It is not edited into shape — it is replaced, because
the sections that were wrong are the sections that now belong elsewhere.

- [ ] **Step 1: Write the new `README.md`**

Target: **under 120 lines.** Required sections, in order, and nothing else:

1. **Title and one paragraph** — what Rubrica does: builds a test suite for an
   agentic system from whatever artifacts describe it (specs, captured
   trajectories, source) by running a pipeline of AI skills over a
   schema-validated on-disk artifact contract. Lead with the tool, not the
   experiment.
2. **A three-sentence "how it works"** — eleven stages, each dispatched with only
   a run directory, a stage name, and a skill file; every handoff is a file on
   disk you can open, schema-check, and diff. Link
   `docs/concepts/artifact-contract.md`.
3. **Status** — an honest one-paragraph statement: early, working against a toy
   world end to end with a model at every stage, not yet hardened against a real
   target. Link `docs/design/limitations.md` and `docs/design/rationale.md`. **No
   numbers, no done/pending table.**
4. **Install** — Python 3.13+ and [`uv`](https://docs.astral.sh/uv/), then
   `make setup`. List `make test`, `make check`, `make lint`, `make format`,
   `make help` with one-line descriptions, and `make live` with its caveat: it is
   deliberately not part of `make test`, it sits behind the `live` marker and
   `RUBRICA_LIVE`, it asserts against committed recordings so running it is free,
   and *producing* a recording is the part that dispatches a model and costs
   money.
5. **Quickstart** — five to eight lines, the shortest path that produces
   something, then "the full walkthrough is `docs/getting-started.md`".
6. **Documentation** — a short link list mirroring `docs/README.md`'s groups.
   This is the section that replaces everything cut.
7. **Contributing** — one line, linking `CONTRIBUTING.md`.
8. **License** — Apache-2.0, © IBM Corp., linking `LICENSE`.

Must **not** appear: a test count, a count of stages/skills/subcommands/gates in
a heading, a reference to `docs/superpowers`, a build-status table, "What is here
so far", "until this build", or a per-module code table. The code table is not
moved anywhere: `docs/reference/cli.md` documents the commands and
`docs/reference/artifacts.md` the artifacts, which is what a reader needs. A
module-by-module list is a maintenance burden with no reader.

- [ ] **Step 2: Verify the content has a home, then delete the overviews**

Verify before deleting, not after:

```bash
grep -c "fan-out\|isolation" docs/concepts/pipeline.md
grep -c "reachability\|denominator" docs/concepts/artifact-contract.md
```

Expected: at least 1 from each. Then:

```bash
git rm docs/pipeline-overview.md docs/pipeline-overview.html
```

- [ ] **Step 3: Find every reference to the deleted paths**

```bash
grep -rn "pipeline-overview" --binary-files=text . \
  --exclude-dir=.git --exclude-dir=.venv | grep -v "^./docs/superpowers/"
```

Expected: no output. Hits under `docs/superpowers/` are left alone — a dated
record is not edited to track a later deletion, and Task 16 records that as
broken-by-history rather than as a defect.

- [ ] **Step 4: Verify the README's own links resolve and it stayed short**

```bash
uv run python -c "
import pathlib, re
t = pathlib.Path('README.md').read_text(encoding='utf-8')
lines = t.count(chr(10))
assert lines < 120, f'README.md is {lines} lines; the target is under 120'
missing = [
    target for target in re.findall(r'\]\(([^)#]+)', t)
    if not target.startswith(('http', 'mailto')) and not pathlib.Path(target).exists()
]
assert not missing, f'README.md links nothing: {missing}'
for banned in ['docs/superpowers', 'What is here so far', 'until this build', 'pipeline-overview']:
    assert banned not in t, banned
assert not re.search(r'\b\d{3,4}\s+(tests?|passed)\b', t), 'no test counts'
print(f'OK -- {lines} lines')
"
```

Expected: `OK` and a line count under 120.

- [ ] **Step 5: Confirm the suite and lint**

```bash
make check && make test && uv run rubrica check-skills
```

`make check` matters here: `README.md` is **not** ruff-excluded, so its fenced
Python blocks are format-checked.

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -S -s -m "docs: Rewrite README.md as a front door and delete the overview

432 lines doing eight jobs, and where several measured defects lived: 'Two
more, neither one a gate itself' followed by three commands, a code table
omitting nine modules and suite/, and no mention of claim-utilisation at all.
Replaced rather than edited -- the sections that were wrong are the sections
that now belong elsewhere.

pipeline-overview.md and its 642-line hand-styled HTML twin are deleted. The
twin carried a second copy of every number in the markdown, which is a drift
class rather than an instance; concepts/pipeline.md and
concepts/artifact-contract.md own that content now.

The per-module code table is not moved anywhere. reference/cli.md documents
the commands and reference/artifacts.md the artifacts, which is what a reader
needs; a module-by-module list is a maintenance burden with no reader.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 15: Rewrite `CLAUDE.md` and add the three policy predicates

**Files:**
- Modify: `CLAUDE.md` (rewritten), `tests/unit/test_docs_accuracy.py`

**Interfaces:**
- Consumes: `docs/design/rationale.md` (Task 11), `docs/design/limitations.md`
  (Task 12), `docs/README.md` (Task 13), `REPO_ROOT`/`_read`/`_user_facing` from
  Task 4, and the `import re` Task 7 added to the guard module.
- Produces: nothing later depends on.

`CLAUDE.md` is agent-facing instructions, read at the start of every session in
this repository. The rewrite must **preserve every rule** while dropping the
build-log accretion. What goes is the genre, not the guidance.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_docs_accuracy.py`:

```python
# Policy predicates. Unlike the four above, these do not check that a document
# names something the code owns -- they enforce a decision about what a document
# may contain. Both were motivated by measurement, recorded here because a future
# author will feel them as friction and deserves the reason: four hand-maintained
# counts were stale simultaneously, and the ~800-word parenthetical in CLAUDE.md
# that existed purely to keep the test count honest was itself wrong by 299.

_TEST_COUNT = re.compile(r"\b\d{3,4}\s+(?:tests?|passed)\b")

_NUMBER = (
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)"
)
# Only sets that grow. `## Two check layers` stays: there are exactly two by
# architecture, and a third would be a design change rather than an increment.
_GROWING = r"(?:stages?|skills?|subcommands?|gates?)"
_COUNTED_HEADING = re.compile(
    rf"^#+\s+.*\b{_NUMBER}\s+(?:\w+\s+)?{_GROWING}\b", re.IGNORECASE | re.MULTILINE
)


def _doc_id(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


@pytest.mark.parametrize("doc", _user_facing(), ids=_doc_id)
def test_no_user_facing_document_carries_a_hand_typed_test_count(doc):
    """The count grows with every capability, so a number typed into prose is
    wrong shortly after it is written. `make test` reports the real one."""
    hits = _TEST_COUNT.findall(_read(doc))
    assert not hits, f"{_doc_id(doc)} states a test count ({hits}); run make test instead"


@pytest.mark.parametrize("doc", _user_facing(), ids=_doc_id)
def test_no_heading_counts_something_that_grows(doc):
    hits = _COUNTED_HEADING.findall(_read(doc))
    assert not hits, (
        f"{_doc_id(doc)} has a heading counting stages/skills/subcommands/gates: {hits}"
    )


def test_claude_md_does_not_cite_recorded_history():
    """The instruction every agent in this repository follows must point at
    current documentation. It used to point into a dated build record."""
    assert "docs/superpowers" not in _read(REPO_ROOT / "CLAUDE.md")


def test_only_the_docs_index_cites_recorded_history():
    citing = [_doc_id(doc) for doc in _user_facing() if "docs/superpowers" in _read(doc)]
    assert citing == ["docs/README.md"], (
        "docs/README.md is the one user-facing file that may link recorded history; "
        f"these do: {citing}"
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
uv run pytest tests/unit/test_docs_accuracy.py -q -k "count or heading or history"
```

Expected: FAIL — at least four failures, all against `CLAUDE.md`: its `1378
passed` baseline, its `## Eleven stages, nine skills` and `## Seventeen
deterministic subcommands` headings, and its two `docs/superpowers` references.
If any *other* document fails here, that document carries a defect an earlier task
introduced — fix it there before continuing.

- [ ] **Step 3: Rewrite `CLAUDE.md`**

Keep every item below, rewritten for concision but not weakened. These are rules,
not description.

1. **What Rubrica is**, in three sentences, plus the yardstick: a change that
   makes the pipeline more likely to produce output while making a stage's
   judgment less observable is a loss, not a win. Link
   `docs/design/rationale.md` and `docs/design/limitations.md`, and say plainly
   that most "bugs you just found" are in the second, with a ruling.
2. **Setup and commands** — the make targets. **Delete the entire baseline
   parenthetical** (currently `:30-70`). Replace with one sentence: `make test`
   green, `make check` clean, and `uv run rubrica check-skills` exit 0 are the
   three gates; anything else means something broke. Keep the four env overrides
   (`RUBRICA_SCHEMA_DIR`, `RUBRICA_SKILLS_DIR`, `RUBRICA_SUITE_DIR`,
   `RUBRICA_LIVE`) and the instruction to prefer them over editing repo files.
3. **The one architectural rule** — verbatim in substance, including the fan-out
   fourth thing and the two verbatim appends the orchestrator may make.
4. **The stage and skill table** — heading without a count. Keep the gate column,
   the note that `survey`/`intake`/`smoke` are code so their absence from
   `manifest.stages` is not a finding, and the paragraph on why gate 0 is
   different in kind.
5. **The exit-code contract** — the table, both invariants, the right-artifact
   rule, and the instruction to test unreadable-input paths (`chmod 000`,
   `chmod 0444`, a bad `RUBRICA_SCHEMA_DIR`) when touching `cli.py`,
   `validate.py`, `refs.py` or `paths.py`.
6. **Two check layers** — keep the heading `## Two check layers` exactly. The
   predicate permits it and Step 1's comment says why.
7. **The skill contract** — the `## Contract` block, the five mandatory sections
   in order, what `check-skills` validates and what it does not, `SKILL_PREFIX`'s
   single home, and the test for a decorative refusal condition.
8. **The deterministic subcommands** — heading without a count. Keep the rulings
   that are judgments rather than list entries: `emit` is code so two runs give
   byte-identical suites, `dedupe-candidates` proposes and never decides,
   `record-stage` hashes the file so a mismatch is the hook working,
   `claim-utilisation` and `gate-brief` are reports that always exit clean on a
   readable run, `set-limit` puts a raised ceiling on the record.
9. **Testing prompts: the traps that recur** — `skills.load()` sets `body` to the
   entire file text, so `"refusal" in body.lower()` is vacuous for every
   conforming skill; use `skills.section_body`; assert co-occurrence within the
   owning section; measure every predicate in both directions; the two weakness
   shapes that recur here (*substring-of-message*, *fixture-cannot-reach*) and
   that *holds-identically* has no prompt analogue.
10. **Fixtures** — the golden toy world is the model answer a skill imitates, so
    an edit there is higher-risk than an edit to source; `tests/toy.py` and
    `build_toy_run`; both negative fixtures and why both directions are needed;
    the gap fixture's forbidden-substring list **is its specification**; recorded
    live output and the re-recording obligation.
11. **Live tests and exercises** — `make live`, the `RUBRICA_LIVE` gate that treats
    `0`/`false`/`no`/empty as off, and the two rules for an exercise record: it
    states what **happened**, and results belong in `exercise.md` rather than only
    in a ledger elsewhere.
12. **Conventions** — `git commit -S -s` with the stop-and-report rule, the
    `Assisted-By` trailer and the forbidden ones, ruff's settings, and the
    comment-density rule. Link `CONTRIBUTING.md` rather than duplicating it.
13. **Before raising a finding against a skill's output** — check what the stage's
    `reads` actually gives it; a finding requiring knowledge outside the contract
    is a finding against the contract or the fixture, never the prompt. And the
    mirror, for a proposed `reads` addition: does a deterministic gate already
    enforce the property?
14. **New section — where documentation lives.** `docs/` is current;
    `docs/superpowers/` is recorded history and **must not be cited**, which is
    why this file no longer names it. State that adding a stage, skill,
    subcommand, or artifact kind means updating `docs/concepts/pipeline.md`,
    `docs/reference/cli.md`, or `docs/reference/artifacts.md`, and that
    `tests/unit/test_docs_accuracy.py` fails until it does — that failure is the
    guard working.

Drop: the baseline parenthetical, every count in a heading, both
`docs/superpowers` references, and the old `docs/running-a-stage-by-hand.md` path
(now under `docs/guides/`).

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run pytest tests/unit/test_docs_accuracy.py -q
```

Expected: all green. The two parametrized predicates run once per user-facing
document, so the total grows with the document set — do not write that number
down anywhere.

- [ ] **Step 5: Measure the three policy predicates in the failure direction**

```bash
printf '\n1677 tests passing.\n' >> CLAUDE.md
uv run pytest tests/unit/test_docs_accuracy.py -q -k count      # expect FAIL
git checkout -- CLAUDE.md

printf '\n## Eleven stages, nine skills\n' >> CLAUDE.md
uv run pytest tests/unit/test_docs_accuracy.py -q -k heading    # expect FAIL
git checkout -- CLAUDE.md

printf '\n## 17 deterministic subcommands\n' >> CLAUDE.md
uv run pytest tests/unit/test_docs_accuracy.py -q -k heading    # expect FAIL
git checkout -- CLAUDE.md

printf '\nSee docs/superpowers/specs/ for the design.\n' >> CLAUDE.md
uv run pytest tests/unit/test_docs_accuracy.py -q -k history
# Expected: TWO failures -- the CLAUDE.md-specific predicate and the index-only one
git checkout -- CLAUDE.md
```

- [ ] **Step 6: Measure the heading predicate in the false-positive direction**

It must not fire on a count of something closed by design, or on an ordinary
stage heading:

```bash
grep -n "^## Two check layers" CLAUDE.md      # must be present
printf '\n## Stage 04: instantiate\n' >> CLAUDE.md
uv run pytest tests/unit/test_docs_accuracy.py -q -k heading
# Expected: PASS. If this fails the predicate is over-broad -- narrow _GROWING,
# never delete the heading to satisfy it.
git checkout -- CLAUDE.md
```

- [ ] **Step 7: Confirm the whole suite and lint, then commit**

```bash
make check && make test && uv run rubrica check-skills
git add CLAUDE.md tests/unit/test_docs_accuracy.py
git commit -S -s -m "docs: Rewrite CLAUDE.md, and make the stale counts unrepeatable

Every rule is preserved; what goes is the genre. The largest single deletion is
the ~800-word parenthetical that existed purely to keep a test-count baseline
honest commit by commit -- the most conscientious prose in the repository, and
still wrong by 299, which is the argument for deleting the genre rather than
correcting the number.

Its two pointers into docs/superpowers/ now go to docs/design/rationale.md and
docs/design/limitations.md. The second is the instruction every agent here
follows before proposing a fix, and it was sending them into a dated build
record.

Three policy predicates: no hand-typed test count in the user-facing set, no
heading counting stages/skills/subcommands/gates, and only docs/README.md may
cite recorded history. All measured in the failure direction, and the heading
predicate in the false-positive direction too -- '## Two check layers' must
survive, because that set is closed by design rather than growing.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 16: Whole-tree verification

**Files:** none, unless a check fails.

**Interfaces:**
- Consumes: everything.
- Produces: the evidence that the plan is done. This task writes no new content;
  when a check fails, fix it in the task that owns the file and re-run this task
  from Step 1.

- [ ] **Step 1: The three gates**

```bash
make check && make test && uv run rubrica check-skills; echo "exit=$?"
```

Expected: ruff clean, suite green, `exit=0`.

- [ ] **Step 2: Every relative link in every tracked markdown resolves**

```bash
uv run python - <<'PY'
import pathlib, re, subprocess
tracked = subprocess.run(
    ["git", "ls-files", "*.md"], capture_output=True, text=True, check=True
).stdout.split()
broken = []
for name in tracked:
    path = pathlib.Path(name)
    for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
        target = target.split("#")[0].strip()
        if not target or target.startswith(("http", "mailto", "<")):
            continue
        if not (path.parent / target).resolve().exists():
            broken.append((name, target))
history = [item for item in broken if item[0].startswith("docs/superpowers/")]
current = [item for item in broken if not item[0].startswith("docs/superpowers/")]
print("broken links in current documentation:", len(current))
for item in current:
    print("  ", item)
print("broken links inside recorded history (accepted):", len(history))
PY
```

Expected: **zero** in current documentation. A non-zero count inside recorded
history is expected and accepted — `pipeline-overview.md` was deleted in Task 14
and a dated record is not edited to track that. Report the history number in the
final summary; do not fix it.

- [ ] **Step 3: The byte-level rename sweep**

`--binary-files=text` is not optional: this repository has already had a stale
name survive six tasks of sweeps because an `&nbsp;` split it.

```bash
for name in pipeline-overview docs/running-a-stage-by-hand capture_harness; do
  echo "=== $name ==="
  grep -rn --binary-files=text "$name" . \
    --exclude-dir=.git --exclude-dir=.venv --exclude-dir=.pytest_cache \
    --exclude-dir=.ruff_cache \
    | grep -v "^./docs/superpowers/" \
    | grep -v "^./runs/" || echo "  clean"
done
```

Expected: `clean` for the first two. For `capture_harness` the only permitted hits
are inside `tests/fixtures/reservation-trajectories/trajectories.json` — captured
MLflow provenance in a committed recording, deliberately not sanitised — and the
prose in that fixture's README explaining exactly that.

- [ ] **Step 4: The history tree lost nothing**

```bash
git diff --stat 6390df0 -- docs/superpowers/
```

Expected: three files, **all additions** —
`specs/2026-08-15-mvp-readiness-design.md`, `plans/2026-08-15-mvp-readiness.md`,
and `README.md`. **Any modification line against a pre-existing file violates the
plan's global constraints.** If one appears, revert it:
`git checkout 6390df0 -- <path>`.

- [ ] **Step 5: The CI claim is true, and its gates match CONTRIBUTING.md**

```bash
test -f .github/workflows/ci.yml && echo "workflow present"
grep -n "ruff check\|pytest -q\|check-skills" .github/workflows/ci.yml
grep -n "make check\|make test\|check-skills" CONTRIBUTING.md
grep -c "make live\|RUBRICA_LIVE" .github/workflows/ci.yml    # expect 0
```

- [ ] **Step 6: The fresh-clone walkthrough**

Clone to a scratch directory and follow the documented setup exactly as written —
not from the working tree, which holds state a new reader does not have.

```bash
CLONE=$(mktemp -d)
git clone --quiet . "$CLONE/rubrica"
cd "$CLONE/rubrica"
make setup
make test
uv run rubrica check-skills; echo "exit=$?"
```

Then execute, in order, every fenced `bash` block in `README.md` and in
`docs/getting-started.md`, against a scratch runs directory. Any command that
errors, or prints something the document does not show, is a defect in that
document.

- [ ] **Step 7: The packaging metadata survived every later edit**

```bash
cd /home/bnayahu/work/kaegis/rubrica
uv run python -c "
from importlib.metadata import metadata
m = metadata('rubrica')
assert m.get('License-Expression') == 'Apache-2.0', m.get('License-Expression')
assert m.get('Summary')
print('OK')
"
uv build 2>&1 | tail -3
```

Expected: `OK`, and a wheel plus sdist built without error.

- [ ] **Step 8: Commit whatever the walkthrough caught**

If Steps 1–7 found nothing, there is nothing to commit and the plan is complete.
If they found something, commit the fix with a message naming the step that caught
it — a check that catches a real defect is worth recording as having worked.

```bash
git commit -S -s -m "docs: Fix what the fresh-clone walkthrough caught

<name the step, the document, and what was wrong>

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Definition of done

- `make check` clean, `make test` green, `uv run rubrica check-skills` exit 0.
- `LICENSE`, `NOTICE`, `CONTRIBUTING.md`, and `.github/workflows/ci.yml` exist,
  and the two documents that claimed CI no longer claim anything untrue.
- Every document in the target set exists, and every relative link in current
  documentation resolves.
- No user-facing document states a test count, counts a growing set in a heading,
  or cites `docs/superpowers` — except `docs/README.md`, which links it as
  history.
- `git diff --stat 6390df0 -- docs/superpowers/` shows additions only.
- `docs/getting-started.md`'s commands have been executed from a fresh clone.
- Every predicate in `tests/unit/test_docs_accuracy.py` has been watched to fail.
