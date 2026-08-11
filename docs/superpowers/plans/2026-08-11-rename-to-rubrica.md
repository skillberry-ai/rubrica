# Rename to Rubrica Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `test-generator` / `testgen` identity with **Rubrica** across the distribution, the CLI, the package, the skill directories, the environment overrides, the emitted Harbor packages and the living documentation — changing no stage's judgment, schema, gate or exit-code behaviour.

**Architecture:** Six tasks, ordered so that each one ends with a green suite and a commit. The deliberate wire-format break goes **first**, in isolation, so that the emitted-byte change is a reviewed decision with its own determinism proof rather than a side effect of a later sweep. The package move goes second, because it is the change that breaks every import at once and cannot be done incrementally. Environment variables, skill directories and documentation follow, each independently rejectable. The final task is a whole-repo residual sweep plus the four-part verification gate.

**Tech Stack:** Python 3.13, `uv`, pytest, ruff, setuptools. No new dependencies. Design spec: `docs/superpowers/specs/2026-08-11-rename-to-rubrica-design.md`.

## Global Constraints

Every task's requirements implicitly include all of these.

- **Every commit is signed and DCO'd: `git commit -S -s`.** If signing fails, **stop and report it** — never fall back to an unsigned commit, never work around it.
- Attribution trailer is exactly `Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>`. **Never** `Co-Authored-By` or `Made-with`.
- The test baseline is **1126 passed, 4 skipped**. Any other number means something broke — investigate, do not adjust the number.
- `make check` must be clean (ruff check + ruff format --check, no changes). `line-length = 100`, `select = ["E","F","I","UP","B","SIM"]`. `docs/` is excluded from ruff; `README.md` is **not**.
- `uv run rubrica check-skills` must exit 0 from Task 4 onward (`uv run testgen check-skills` before that).
- **No back-compatibility aliases.** No `TESTGEN_*` environment fallbacks, no `testgen` console-script shim, no deprecation period. Adding one is a plan violation.
- **Do not touch dated design records.** `docs/superpowers/specs/2026-08-06-*.md` and everything in `docs/superpowers/plans/` except this file stay byte-identical, apart from the single rename note added in Task 5. `git diff --stat` on those paths must show only that one file.
- Comment density in this repo is high and deliberate — comments explain *why*, usually citing a measurement. When you edit a comment, preserve its reasoning; when the rename makes a comment's example stale, update the example and keep the argument.
- Never weaken the exit-code contract: `0` clean, `1` findings one per line on stdout, `2` usage error or unreadable run. A stage defect must never surface as `2`, and a `1` must never have empty stdout.

## File Structure

No files gain or lose responsibilities. The rename moves one directory tree and edits identifiers in place.

| Path | What changes |
|---|---|
| `src/testgen/` → `src/rubrica/` | Whole package moves via `git mv`. 22 modules, plus `schema/`, `skills/`, `suite/`. |
| `src/rubrica/suite/verify.py:25` | `CONTRACT` string. The scoring wire format. |
| `src/rubrica/suite/test.sh:2,10` | Header comments; copied verbatim into every emitted package, so its bytes ship. |
| `src/rubrica/emit.py:44,51,54,211` | `SUITE_NAME`, the `RUBRICA_SUITE_DIR` override, the provenance line. |
| `src/rubrica/skills.py:41,146,149,157,306` | `ORCHESTRATOR`, the skills-dir override, and the two places that build a skill directory name from a stage. Gains one constant, `SKILL_PREFIX`. |
| `src/rubrica/validate.py:87,90,103,121,132` · `cli.py:45,206` | `RUBRICA_SCHEMA_DIR`. |
| `src/rubrica/skills/tg-*/` → `rb-*/` | Eight directories, each holding `SKILL.md` and `exercise.md`. |
| `pyproject.toml:2,15,29,46` | Distribution name, console script, package-data key, pytest marker help. |
| `Makefile:14` | `RUBRICA_LIVE`. |
| `tests/conftest.py:4,15,23,30` | `LIVE_ENV`. |
| `tests/builders.py:250` | The contract string every built package carries. |
| `tests/unit/test_verify_reward.py:727-744` | The stdlib-only guard: its name, its prefix strings, two hardcoded paths. |
| 51 test files | `from testgen …` → `from rubrica …`, plus the fixture names named in Task 4. |
| `README.md` · `CLAUDE.md` · `docs/running-a-stage-by-hand.md` | Rewritten. |
| `docs/superpowers/specs/2026-08-06-…-design.md` | One rename note at the top. Nothing else. |

---

### Task 1: The wire-format break, in isolation

Do this first and alone. It changes the bytes of every emitted Harbor package, and it must be a reviewed decision with its own determinism proof rather than collateral damage from a later `sed`.

**Files:**
- Modify: `src/testgen/suite/verify.py:25`
- Modify: `src/testgen/suite/test.sh:2`
- Modify: `src/testgen/emit.py:44`, `src/testgen/emit.py:211`
- Modify: `tests/builders.py:250`
- Modify: `tests/unit/test_verify_contract_refusal.py:30`, `:60`, `:63`
- Test: `tests/unit/test_verify_contract_refusal.py`, `tests/unit/test_emit_packages.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `verify.CONTRACT == "rubrica/v1"` and `emit.SUITE_NAME == "rubrica"`. Task 2 moves both modules but does not change these values again.

- [ ] **Step 1: Confirm the baseline before touching anything**

```bash
uv run pytest -q 2>&1 | tail -3
```
Expected: `1126 passed, 4 skipped`. If it is anything else, stop — you are not starting from the documented baseline.

- [ ] **Step 2: Prove the current emitter is deterministic, so the check means something later**

```bash
uv run python - <<'PY'
import shutil, tempfile, subprocess, sys, filecmp, pathlib
sys.path.insert(0, "tests")
from toy import build_toy_run
out = []
for i in (0, 1):
    d = pathlib.Path(tempfile.mkdtemp())
    run = build_toy_run(d, upto="challenge")
    subprocess.run([sys.executable, "-m", "testgen.cli", "emit", "--run", str(run.root)], check=True)
    out.append(run.suite_dir)
cmp = filecmp.dircmp(*out)
print("differing:", cmp.diff_files, "left_only:", cmp.left_only, "right_only:", cmp.right_only)
PY
```
Expected: `differing: [] left_only: [] right_only: []`.

If `build_toy_run`'s signature or the `upto` value differs from this, read `tests/toy.py` — `_UPTO_STAGES` lists the legal checkpoints — and use the checkpoint that produces stages 4 and 5. Do not add a new helper; CLAUDE.md records that nearly every request for a new checkpoint during the original build turned out to be for one that already existed.

- [ ] **Step 3: Change the scoring contract**

In `src/testgen/suite/verify.py:25`:

```python
CONTRACT = "rubrica/v1"
```

- [ ] **Step 4: Change the suite name and the provenance line**

In `src/testgen/emit.py:44`:

```python
SUITE_NAME = "rubrica"
```

In `src/testgen/emit.py:211`, inside the `lines` list:

```python
        "**Status:** generated by rubrica. Every line below is copied from the run",
```

- [ ] **Step 5: Change the shipped verifier entrypoint's branding line only**

In `src/testgen/suite/test.sh:2` — change *only* line 2. Line 10 names the tracked source path and is corrected in Task 2, after the path actually exists:

```bash
# Harbor verifier entrypoint for a rubrica-emitted task.
```

- [ ] **Step 6: Update the tests that pin the contract string**

In `tests/builders.py:250`:

```python
        "contract": "rubrica/v1",
```

In `tests/unit/test_verify_contract_refusal.py`, three occurrences — `:30`, `:60`, `:63`:

```python
    argv, out = _package(tmp_path, '{"contract": "rubrica/v1", "assert')
```
```python
    path.write_text('{"contract": "rubrica/v1"}', encoding="utf-8")
```
```python
    assert contract == {"contract": "rubrica/v1"}
```

- [ ] **Step 7: Run the tests**

```bash
uv run pytest -q 2>&1 | tail -3
```
Expected: `1126 passed, 4 skipped`.

If a test fails asserting on a task name like `testgen/scn-empty`, that is a pin this plan did not find. Update it to `rubrica/scn-empty` and note it in the commit body — do not delete the assertion.

- [ ] **Step 8: Prove a mismatched contract is still refused, not scored zero**

```bash
uv run pytest tests/unit/test_verify_contract_refusal.py -v 2>&1 | tail -15
```
Expected: all pass. This is the behaviour that makes the break safe: an old package meeting the new verifier gets `reward-detail.json` plus exit 2 and **no** `reward.txt`, so Harbor reports a missing reward rather than a real zero.

- [ ] **Step 9: Re-prove determinism with the new bytes**

Re-run the Step 2 command verbatim. Expected: `differing: [] left_only: [] right_only: []`.

This is the guarantee that lets run-to-run variance be attributed to a stage, and Step 4 changed the bytes it applies to.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -S -s -m "feat!: Rename the scoring contract and suite to rubrica

verify.CONTRACT becomes rubrica/v1 and emit.SUITE_NAME becomes rubrica,
so emitted task ids are rubrica/<scenario_id>.

BREAKING: a package emitted before this commit is refused by a verifier
from after it -- reward-detail.json with the error, no reward.txt, exit
2, which is the designed contract-mismatch path rather than a scored
zero. Every previously emitted suite must be re-emitted.

Determinism re-proved rather than assumed: two emits from identical
stage-4 and stage-5 artifacts remain byte-identical, which is the
property that lets variance be attributed to a stage.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 2: Move the package

The change that breaks every import at once, so it is one commit rather than several. Nothing here is optional or incremental.

**Files:**
- Move: `src/testgen/` → `src/rubrica/`
- Modify: `pyproject.toml:2`, `:15`, `:29`
- Modify: `src/rubrica/suite/test.sh:10`
- Modify: `tests/unit/test_verify_reward.py:727`, `:729`, `:736`, `:738`, `:744`
- Modify: all 51 test files importing `testgen`, and every intra-package import

**Interfaces:**
- Consumes: `verify.CONTRACT`, `emit.SUITE_NAME` from Task 1 — unchanged in value here.
- Produces: importable package `rubrica`, console script `rubrica`, distribution `rubrica`. Tasks 3–6 assume all three.

- [ ] **Step 1: Move the tree with git, so history follows**

```bash
git mv src/testgen src/rubrica
find src -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null; true
```

The `find` removes stale bytecode: `git mv` moves tracked files only, and a leftover `src/testgen/__pycache__` will shadow imports confusingly.

- [ ] **Step 2: Rewrite every import**

`sed` is safe here specifically because it is case-sensitive: lowercase `testgen` cannot match the uppercase `TESTGEN_*` environment variables, which Task 3 owns. Task 1 already handled the string literals that would otherwise be caught here.

```bash
git ls-files -z '*.py' | xargs -0 sed -i 's/\btestgen\b/rubrica/g'
git diff --stat | tail -3
```
Expected: roughly 60–75 files changed. Then read the diff for anything that is not an import or a dotted reference:

```bash
git diff -U0 -- '*.py' | grep '^+' | grep -v 'rubrica' | head
```
Expected: no output. Any line here is a `sed` casualty — inspect it.

- [ ] **Step 3: Fix the package metadata**

In `pyproject.toml`, three lines:

```toml
name = "rubrica"
```
```toml
[project.scripts]
rubrica = "rubrica.cli:main"
```
```toml
[tool.setuptools.package-data]
rubrica = ["schema/*.json", "suite/*.py", "suite/*.sh", "skills/*/SKILL.md"]
```

Leave the comment above `[tool.setuptools.package-data]` intact — it explains *why* the schemas and skills ship, which the rename does not change.

- [ ] **Step 4: Fix the shipped entrypoint's source-path comment**

In `src/rubrica/suite/test.sh:10` — the path now exists, so this is the moment it becomes true:

```bash
# src/rubrica/suite/test.sh.
```

- [ ] **Step 5: Repair the stdlib-only guard, which `sed` has just silently defanged**

This is the most dangerous edit in the whole rename. `tests/unit/test_verify_reward.py` walks `verify.py`'s AST and asserts no import starts with the package name — that is what keeps the verifier runnable inside a bare container. Step 2 rewrote the prefix strings for you, which is correct, but the **test's own name** still says `testgen` and reads as a stale claim. Rename it:

```python
def test_verify_py_never_imports_rubrica():
```

Then confirm the prefix strings at `:736` and `:738` now read `"rubrica"`, and the two hardcoded paths at `:729` and `:744` now read `src/rubrica/suite/verify.py` and `src/rubrica/suite/test.sh`.

- [ ] **Step 6: Prove the guard still guards — it must fail when violated**

A predicate nobody has watched fail is not yet a guard. Temporarily add a real violation:

```bash
cp src/rubrica/suite/verify.py /tmp/verify.py.bak
sed -i '0,/^import /s/^import /from rubrica.errors import UsageError  # TEMP\nimport /' src/rubrica/suite/verify.py
uv run pytest tests/unit/test_verify_reward.py::test_verify_py_never_imports_rubrica -q 2>&1 | tail -5
```
Expected: **FAIL**. If it passes, the guard is dead and the rename broke it — stop and fix before continuing.

Then restore:

```bash
cp /tmp/verify.py.bak src/rubrica/suite/verify.py
git diff --stat src/rubrica/suite/verify.py
```
Expected: no output from `git diff --stat` — the file is back to its committed state.

- [ ] **Step 7: Reinstall, so the console script is regenerated under its new name**

```bash
uv pip uninstall test-generator
uv pip install -e '.[dev]'
uv run rubrica --help 2>&1 | head -5
```
Expected: the subcommand help. Then confirm the old name is gone:

```bash
uv run testgen --help 2>&1 | tail -2
```
Expected: a "command not found" style failure. A working `testgen` means the old script survived and the no-aliases constraint is violated.

- [ ] **Step 8: Run the tests**

```bash
uv run pytest -q 2>&1 | tail -3
uv run testgen check-skills; echo "check-skills exit: $?"
```

Note: `check-skills` is still invoked as `testgen` in your muscle memory but the script is now `rubrica`:

```bash
uv run rubrica check-skills; echo "exit: $?"
```
Expected: `1126 passed, 4 skipped`, and `exit: 0`.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -S -s -m "refactor!: Move the package from testgen to rubrica

git mv src/testgen src/rubrica, rewrite every import, and rename the
distribution and console script. No back-compatibility shim: the project
is at 0.1.0, no external user exists, and no sibling repository in
~/work/kaegis/ references it.

Repairs the stdlib-only guard in test_verify_reward.py rather than
letting the sweep defang it. That test asserts verify.py imports nothing
from the package, which is what keeps it runnable inside a bare
container; a renamed package with the old prefix string would pass
unconditionally forever while appearing to hold. Observed failing
against a deliberate violation before being restored.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 3: Rename the environment overrides

**Files:**
- Modify: `src/rubrica/validate.py:87`, `:90`, `:103`, `:121`, `:132`
- Modify: `src/rubrica/skills.py:146`, `:149`
- Modify: `src/rubrica/emit.py:51`, `:54`
- Modify: `src/rubrica/cli.py:45`, `:206`
- Modify: `tests/conftest.py:4`, `:15`, `:23`, `:30`
- Modify: `Makefile:14`, `pyproject.toml:46`
- Modify: `tests/unit/test_validate.py:67`, `:534`, `:557`; `tests/unit/test_cli.py:750`, `:757`; `tests/unit/test_skills_parse.py:229`; `tests/unit/test_live_marker.py:69`, `:79`, `:86`, `:91`, `:101`, `:121`

**Interfaces:**
- Consumes: package `rubrica` from Task 2.
- Produces: `RUBRICA_SCHEMA_DIR`, `RUBRICA_SKILLS_DIR`, `RUBRICA_SUITE_DIR`, `RUBRICA_LIVE`. Task 4 uses `RUBRICA_SKILLS_DIR` to probe candidate skill sets.

- [ ] **Step 1: Rewrite all four names, code and prose together**

The names appear in string literals, in comments explaining why the override exists, and in a pytest marker's help text. All four must move together — a comment naming a variable that no longer exists is worse than no comment.

```bash
git ls-files -z '*.py' 'Makefile' 'pyproject.toml' | xargs -0 sed -i \
  -e 's/TESTGEN_SCHEMA_DIR/RUBRICA_SCHEMA_DIR/g' \
  -e 's/TESTGEN_SKILLS_DIR/RUBRICA_SKILLS_DIR/g' \
  -e 's/TESTGEN_SUITE_DIR/RUBRICA_SUITE_DIR/g' \
  -e 's/TESTGEN_LIVE/RUBRICA_LIVE/g'
git diff --stat | tail -3
```

- [ ] **Step 2: Confirm no old name survives outside the dated records**

```bash
grep -rn "TESTGEN_" --exclude-dir=.git --exclude-dir=docs --exclude-dir=.venv . | grep -v "^./docs/"
```
Expected: no output.

- [ ] **Step 3: Run the tests**

```bash
uv run pytest -q 2>&1 | tail -3
```
Expected: `1126 passed, 4 skipped`.

- [ ] **Step 4: Prove the live gate still refuses to be opted into by accident**

`RUBRICA_LIVE=0`, typed by someone who means "off", must not dispatch a model and spend money. `_LIVE_OFF_SPELLINGS` in `tests/conftest.py` is the guard; confirm the rename did not orphan it:

```bash
uv run pytest tests/unit/test_live_marker.py -v 2>&1 | tail -12
RUBRICA_LIVE=0 uv run pytest -m live -q 2>&1 | tail -3
```
Expected: the `test_live_marker.py` tests pass, and the second command **skips** the live tests rather than running them. A skip message naming `RUBRICA_LIVE=1 make live` is the correct output.

- [ ] **Step 5: Confirm `make live`'s own wiring**

```bash
grep -n "RUBRICA_LIVE" Makefile pyproject.toml
```
Expected: `Makefile:14` sets `RUBRICA_LIVE=1`, and `pyproject.toml:46`'s marker help names `RUBRICA_LIVE`. The skip message must name a command that exists, because a marker nobody can find is a suite that does not exist.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -S -s -m "refactor!: Rename the four environment overrides to RUBRICA_*

TESTGEN_{SCHEMA_DIR,SKILLS_DIR,SUITE_DIR,LIVE} become RUBRICA_*, in the
string literals, in the comments that explain why each override exists,
and in the pytest marker help that tells a reader how to run the live
suite.

BREAKING: no fallback to the old names. Anyone with TESTGEN_SCHEMA_DIR
exported will silently get the packaged schemas instead of theirs, which
is the correct failure for a 0.1.0 project with no external users.

Verified that RUBRICA_LIVE=0 still means off: the off-spellings guard
survives the rename, so nobody opts into paid model dispatch by typing
the value that means no.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 4: Rename the skill directories, and give the prefix one home

**Files:**
- Move: `src/rubrica/skills/tg-{extract,reconcile,propose,score,instantiate,challenge,emit,orchestrate}/` → `rb-*/`
- Modify: `src/rubrica/skills.py:41`, `:157`, `:306` (and add `SKILL_PREFIX`)
- Modify: all 8 `src/rubrica/skills/rb-*/SKILL.md` and all 8 `exercise.md`
- Modify: `tests/unit/test_skills_contract.py:138`, `:139`, `:150`, `:454`, `:455`, `:456`
- Modify: `tests/unit/test_skills_parse.py:206`
- Test: `tests/unit/test_skills_contract.py`, `tests/unit/test_skills_parse.py`, `tests/unit/test_refusal_fixtures.py`

**Interfaces:**
- Consumes: package `rubrica` (Task 2), `RUBRICA_SKILLS_DIR` (Task 3).
- Produces: `skills.SKILL_PREFIX = "rb-"`, and `skills.expected_skill_names()` returning `("rb-extract", "rb-reconcile", "rb-propose", "rb-score", "rb-instantiate", "rb-challenge", "rb-emit", "rb-orchestrate")` — order follows `paths.STAGES` with `CODE_ONLY_STAGES` removed, then the orchestrator appended.

- [ ] **Step 1: Record what the three negative guards say now, before you change them**

These three tests exist to prove `check-skills` rejects a misspelling, an unknown stage, and the two code-only stages. After the rename they must fail for the **same reason** — the same message, with only the prefix differing. Capture the current messages first, so the comparison is against evidence rather than memory:

```bash
uv run pytest -q \
  "tests/unit/test_skills_contract.py::test_an_unknown_stage_is_reported" \
  "tests/unit/test_skills_contract.py::test_check_all_reports_a_directory_that_is_not_a_known_skill" \
  "tests/unit/test_skills_parse.py::test_expected_skill_names_are_derived_from_STAGES" \
  -v 2>&1 | tail -8
```
Expected: 3 passed. Now capture the messages they assert on:

```bash
uv run python -c "
import sys; sys.path.insert(0,'tests')
from rubrica.skills import load, check_contract, check_all
print('expected names:', __import__('rubrica.skills',fromlist=['x']).expected_skill_names())
" 2>&1 | tail -3
```
Write the printed tuple down. Step 7 compares against it.

- [ ] **Step 2: Move the eight directories**

```bash
for s in extract reconcile propose score instantiate challenge emit orchestrate; do
  git mv "src/rubrica/skills/tg-$s" "src/rubrica/skills/rb-$s"
done
ls src/rubrica/skills/
```
Expected: eight `rb-*` directories, no `tg-*`.

- [ ] **Step 3: Give the prefix a single home in `skills.py`**

The prefix currently lives in three places — a literal in `ORCHESTRATOR`, an f-string at `:157`, and another f-string at `:306`. That is the duplication this module already argues against one comment earlier ("derives the list rather than restating it -- so adding a stage demands a skill without anyone remembering to edit a constant"). Introduce the constant, immediately above `ORCHESTRATOR`:

```python
# One home for the skill-directory prefix. It appeared in three places
# before the Rubrica rename -- ORCHESTRATOR, expected_skill_names, and the
# directory/stage agreement check -- and a rename that updates two of three
# leaves check_contract rejecting every correctly named skill. Same reasoning
# as CODE_ONLY_STAGES above: derive, do not restate.
SKILL_PREFIX = "rb-"

# Not a stage: it dispatches them. It has no `stage` key and no `schemas`.
ORCHESTRATOR = f"{SKILL_PREFIX}orchestrate"
```

At `:157`, inside `expected_skill_names`:

```python
    return tuple(
        f"{SKILL_PREFIX}{stage}" for stage in STAGES if stage not in CODE_ONLY_STAGES
    ) + (ORCHESTRATOR,)
```

At `:306`, in the directory/stage agreement arm:

```python
    elif skill.name != f"{SKILL_PREFIX}{stage}":
```

- [ ] **Step 4: Rewrite the skill names inside every skill file and every test**

The eight `SKILL.md` files cross-reference each other by directory name, and `exercise.md` files name the skill they exercised.

```bash
git ls-files -z 'src/rubrica/skills/' '*.py' 'Makefile' | xargs -0 sed -i \
  -e 's/\btg-extract\b/rb-extract/g' \
  -e 's/\btg-extractt\b/rb-extractt/g' \
  -e 's/\btg-reconcile\b/rb-reconcile/g' \
  -e 's/\btg-propose\b/rb-propose/g' \
  -e 's/\btg-score\b/rb-score/g' \
  -e 's/\btg-instantiate\b/rb-instantiate/g' \
  -e 's/\btg-challenge\b/rb-challenge/g' \
  -e 's/\btg-emit\b/rb-emit/g' \
  -e 's/\btg-orchestrate\b/rb-orchestrate/g' \
  -e 's/\btg-bogus\b/rb-bogus/g' \
  -e 's/\btg-smoke\b/rb-smoke/g' \
  -e 's/\btg-intake\b/rb-intake/g'
```

`tg-extractt` is listed **before** `tg-extract` would otherwise match it, and each pattern is `\b`-anchored, because `tg-extract` is a prefix of `tg-extractt` and a careless order turns the deliberate misspelling into `rb-extractt` inconsistently. Verify:

```bash
grep -rn "rb-extractt" tests/ | head
grep -rn "\btg-" --exclude-dir=.git --exclude-dir=docs --exclude-dir=.venv . | grep -v "^./docs/"
```
Expected: `rb-extractt` present at the two lines it belongs on, and no surviving `tg-` outside `docs/`.

- [ ] **Step 5: Rewrite the CLI name inside the skill prose**

The `SKILL.md` files instruct a dispatched model to run gates by name — 58 occurrences across the eight files, e.g. "Before you report done, run `testgen validate --stage extract`". A skill telling a model to run a command that does not exist is a skill whose refusal conditions cannot fire.

```bash
git ls-files -z 'src/rubrica/skills/' | xargs -0 sed -i 's/\btestgen\b/rubrica/g'
grep -rn "testgen" src/rubrica/skills/ | head
```
Expected: no output from the `grep`.

In `exercise.md` files, **only the invocation lines change.** Every measured number, verdict and quoted model output stays exactly as recorded — a rename changes no measurement, and a reasoned number presented as an observed one corrupts the evidence. Review the diff on those eight files specifically:

```bash
git diff -- 'src/rubrica/skills/*/exercise.md' | grep '^[-+]' | grep -v '^[-+][-+]' | head -40
```
Expected: every changed line is a command or a skill-directory reference. If a line containing a count, a score or a reward changed, revert that line.

- [ ] **Step 6: Run the full suite**

```bash
uv run pytest -q 2>&1 | tail -3
uv run rubrica check-skills; echo "exit: $?"
```
Expected: `1126 passed, 4 skipped`, and `exit: 0`.

- [ ] **Step 7: Prove each negative guard still fails for its original reason**

Re-run the three from Step 1 and confirm they pass — passing here means each still *detects* its defect:

```bash
uv run pytest -q \
  "tests/unit/test_skills_contract.py::test_an_unknown_stage_is_reported" \
  "tests/unit/test_skills_contract.py::test_check_all_reports_a_directory_that_is_not_a_known_skill" \
  "tests/unit/test_skills_parse.py::test_expected_skill_names_are_derived_from_STAGES" \
  -v 2>&1 | tail -8
```
Expected: 3 passed, and `expected_skill_names()` now prints the `rb-*` tuple from this task's **Interfaces** block.

Then measure the guard in the other direction — a real skill set with a real defect, under `RUBRICA_SKILLS_DIR`, so nothing in the repo is touched:

```bash
rm -rf /tmp/skills-probe && cp -r src/rubrica/skills /tmp/skills-probe
mv /tmp/skills-probe/rb-propose /tmp/skills-probe/rb-proposee
RUBRICA_SKILLS_DIR=/tmp/skills-probe uv run rubrica check-skills; echo "exit: $?"
```
Expected: **exit 1**, with findings on stdout naming `rb-proposee` and the missing `rb-propose`. Exit 0 means the prefix constant is not actually being consulted. Exit 2 means a stage defect surfaced as a usage error, which violates the exit-code contract — stop and fix.

```bash
rm -rf /tmp/skills-probe
```

- [ ] **Step 8: Confirm the refusal fixtures did not silently lose anything**

```bash
uv run pytest tests/unit/test_refusal_fixtures.py -v 2>&1 | tail -8
```
Expected: all pass. These guard that `toy-contradiction/` and `toy-gap/` still carry their defect *and* have not lost anything else — an over-subtraction once destroyed a capability fact while passing every forbidden-substring check.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -S -s -m "refactor!: Rename the skill directories from tg-* to rb-*

Moves the eight skill directories, rewrites their cross-references and
the CLI name in their prose, and updates the deliberately invalid names
the check-skills negative tests rely on -- rb-extractt, rb-bogus,
rb-smoke, rb-intake -- so each still fails for its original reason
rather than as an unrecognised prefix.

Collapses the prefix into one SKILL_PREFIX constant. It lived in three
places, and a rename updating two of them leaves check_contract
rejecting every correctly named skill; this is the same argument the
module already makes for deriving the skill list from STAGES.

exercise.md invocation lines move; every measured number stays as
recorded, because a rename changes no measurement.

Measured in both directions: a candidate skill set with a misspelled
directory, supplied via RUBRICA_SKILLS_DIR, exits 1 with findings naming
it -- not 0, and not 2.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 5: Documentation

**Files:**
- Modify: `README.md` (30 occurrences), `CLAUDE.md` (16), `docs/running-a-stage-by-hand.md` (22)
- Modify: `docs/superpowers/specs/2026-08-06-skill-based-test-generator-design.md` — **one note at the top, nothing else**
- Do not modify: anything else under `docs/superpowers/`

**Interfaces:**
- Consumes: every name established in Tasks 1–4.
- Produces: nothing code depends on.

- [ ] **Step 1: Rewrite the three living documents**

```bash
sed -i -e 's/\btestgen\b/rubrica/g' -e 's/\btest-generator\b/rubrica/g' \
  -e 's/\btg-/rb-/g' -e 's/TESTGEN_/RUBRICA_/g' \
  README.md CLAUDE.md docs/running-a-stage-by-hand.md
```

Then read all three. `sed` gets the identifiers; it does not get the prose. Fix by hand:

- The `# test-generator` heading in both `README.md` and `CLAUDE.md` becomes `# Rubrica`.
- `pyproject.toml`'s `description` is quoted in neither, but the phrase "test suite generator" appears in prose — leave descriptive prose describing what the tool *does*; only proper-noun uses of the old name change.
- `README.md`'s path references (`src/rubrica/skills/rb-<name>/SKILL.md`) and its markdown link targets must both be updated, and a link whose text and target disagree is a broken link.
- `CLAUDE.md`'s "Nine stages, eight skills" table, its `paths.STAGES` reference, and its `Two env overrides exist` sentence (which names two of the four — leave that count as it is unless it was already wrong).

- [ ] **Step 2: Add the constant to CLAUDE.md's skill-contract section**

Task 4 introduced `skills.SKILL_PREFIX`, and CLAUDE.md is the document that tells a future contributor which code owns which name. In the `## The skill contract` section, after the sentence naming `paths.RunPaths`, `validate.STAGE_ARTIFACTS` and `cli.SUBCOMMANDS`, add:

```markdown
The `rb-` prefix itself lives in `skills.SKILL_PREFIX` — one home, because it
was three before the rename and a partial update makes `check-skills` reject
every correctly named skill.
```

- [ ] **Step 3: Note the rename at the top of the dated design record, and change nothing else in it**

Insert immediately below that document's title, then leave the entire rest of the file byte-identical:

```markdown
> **Renamed 2026-08-11.** This record describes the project when it was called
> `test-generator`, with a `testgen` CLI and `tg-*` skills. It is left as
> written: a record of what was decided on 2026-08-06 should not describe a past
> that did not happen. For the current names see
> [`2026-08-11-rename-to-rubrica-design.md`](2026-08-11-rename-to-rubrica-design.md).
```

- [ ] **Step 4: Prove the dated records are otherwise untouched**

```bash
git diff --stat -- docs/superpowers/
```
Expected: exactly two files — `specs/2026-08-06-skill-based-test-generator-design.md` with a small insertion, and `plans/2026-08-11-rename-to-rubrica.md` if you have been ticking checkboxes. **No other file under `docs/superpowers/plans/` may appear.** If one does, revert it: `git checkout -- <path>`.

- [ ] **Step 5: Lint, because README.md is not excluded from ruff**

```bash
uv run ruff check . && uv run ruff format --check .
```
Expected: both clean, no changes. `docs/` is excluded by `extend-exclude`, but `README.md` is not, and ruff formats Python code blocks inside Markdown.

- [ ] **Step 6: Run the tests**

```bash
uv run pytest -q 2>&1 | tail -3
```
Expected: `1126 passed, 4 skipped`. Documentation is not test-free here — `README.md` and `CLAUDE.md` are read by no test, but `docs/running-a-stage-by-hand.md` is referenced by CLAUDE.md, and a stale command in it is a defect a reader hits.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -S -s -m "docs: Rename the living documents to Rubrica

README.md, CLAUDE.md and docs/running-a-stage-by-hand.md rewritten. The
last is a procedure, so leaving the old command name would tell a reader
to run something that no longer exists.

The dated design record and the plans stay verbatim, with one note at
the top of the 2026-08-06 spec pointing here: a record of what was
decided that day should not describe a past that did not happen. This is
the same reasoning that already excludes docs/ from ruff.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 6: Residual sweep and the four-part gate

Nothing new is renamed here. This task exists because a rename's characteristic failure is the occurrence nobody grepped for.

**Files:**
- Modify: only whatever the sweep finds.

**Interfaces:**
- Consumes: everything.
- Produces: a verified repository.

- [ ] **Step 1: Sweep for every residual, excluding only the dated records**

```bash
grep -rn "testgen\|test-generator\|TESTGEN_\|\btg-" \
  --exclude-dir=.git --exclude-dir=.venv --exclude-dir=__pycache__ . \
  | grep -v "^./docs/superpowers/plans/2026-08-0" \
  | grep -v "^./docs/superpowers/specs/2026-08-06" \
  | grep -v "^./docs/superpowers/specs/2026-08-11" \
  | grep -v "^./docs/superpowers/plans/2026-08-11"
```
Expected: **no output.** Every line is a residual. Fix each, then re-run until clean.

The two 2026-08-11 files are excluded because this plan and its spec legitimately discuss the old names.

- [ ] **Step 2: Confirm the git history followed the move**

```bash
git log --follow --oneline -3 -- src/rubrica/skills.py | cat
```
Expected: commits predating this rename. If only the rename commit appears, the move was not done with `git mv` and blame is lost — worth knowing before this merges.

- [ ] **Step 3: Gate 1 of 4 — the suite**

```bash
uv run pytest -q 2>&1 | tail -3
```
Expected: `1126 passed, 4 skipped`.

- [ ] **Step 4: Gate 2 of 4 — lint and format**

```bash
uv run ruff check . && uv run ruff format --check . && echo "CHECK CLEAN"
```
Expected: `CHECK CLEAN`.

- [ ] **Step 5: Gate 3 of 4 — the skill contracts**

```bash
uv run rubrica check-skills; echo "exit: $?"
```
Expected: `exit: 0`. This proves the eight renamed contracts still hold to `paths.RunPaths` attribute names, `validate.STAGE_ARTIFACTS` and `cli.SUBCOMMANDS`.

- [ ] **Step 6: Gate 4 of 4 — byte-stable emission**

```bash
uv run python - <<'PY'
import tempfile, subprocess, sys, filecmp, pathlib
sys.path.insert(0, "tests")
from toy import build_toy_run
out = []
for i in (0, 1):
    d = pathlib.Path(tempfile.mkdtemp())
    run = build_toy_run(d, upto="challenge")
    subprocess.run([sys.executable, "-m", "rubrica.cli", "emit", "--run", str(run.root)], check=True)
    out.append(run.suite_dir)
cmp = filecmp.dircmp(*out)
print("differing:", cmp.diff_files, "left_only:", cmp.left_only, "right_only:", cmp.right_only)
PY
```
Expected: `differing: [] left_only: [] right_only: []`.

Then confirm the new identity actually reached the artifacts:

```bash
uv run python - <<'PY'
import tempfile, subprocess, sys, pathlib
sys.path.insert(0, "tests")
from toy import build_toy_run
d = pathlib.Path(tempfile.mkdtemp())
run = build_toy_run(d, upto="challenge")
subprocess.run([sys.executable, "-m", "rubrica.cli", "emit", "--run", str(run.root)], check=True)
for p in sorted(run.suite_dir.rglob("task.toml"))[:1]:
    print(p.read_text()[:400])
PY
```
Expected: `name = "rubrica/<scenario_id>"` and `suite = "rubrica"`.

- [ ] **Step 7: Commit anything the sweep fixed**

If Step 1 found nothing, there is nothing to commit and this task ends here. Otherwise:

```bash
git add -A
git commit -S -s -m "fix: Clear the residual testgen references the sweep found

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

- [ ] **Step 8: Report the hand-off items — these are not yours to do**

Print this list for the user and stop:

1. Rename the working directory `~/work/kaegis/test-generator` → `~/work/kaegis/rubrica`, and the GitHub repository.
2. Register `rubrica` on PyPI. Verified unclaimed on PyPI, npm and RubyGems as of 2026-08-11.
3. Check `rubrica` on crates.io by hand — the automated check returned HTTP 403 rather than a real answer.
4. Confirm nothing is currently registered in Harbor from this generator. If anything is, it must be re-emitted: Task 1 broke the scoring contract deliberately, so an old package meeting the new verifier is refused with exit 2 and no `reward.txt`.

---

## Self-Review

**Spec coverage** — every section of `2026-08-11-rename-to-rubrica-design.md` maps to a task:

| Spec section | Task |
|---|---|
| §1 The decision · §3 Identity mapping | Tasks 1–5 collectively; the mapping table is realised across all of them |
| §2 Why this name | No task — rationale, already recorded |
| §4 Measured scope | Task 6 Step 1 verifies the sweep was complete |
| §5.1 `skills.py` prefix in three places | Task 4 Step 3 |
| §5.2 `check-skills` negative fixtures | Task 4 Steps 1, 4, 7 |
| §5.3 `emit.py` `SUITE_NAME` + provenance | Task 1 Steps 4 |
| §5.4 `suite/test.sh` shipped verbatim | Task 1 Step 5 (branding), Task 2 Step 4 (path) |
| §5.5 the stdlib-only guard | Task 2 Steps 5–6 |
| §6 Wire-format break | Task 1, whole task |
| §7 Documentation policy | Task 5, including the exercise.md rule at Task 4 Step 5 |
| §8 Verification gate, all four parts | Task 6 Steps 3–6 |
| §9 Out of scope | Task 6 Step 8 |
| §10 No aliases, no re-recording | Global Constraints; no task re-records a fixture |

**Placeholder scan** — no TBD, no "add error handling", no "similar to Task N". Every code step shows the actual replacement text; every verification step shows the command and its expected output.

**Type consistency** — `SKILL_PREFIX` is introduced in Task 4 Step 3 and used at three call sites in that same step; `expected_skill_names()` keeps its signature and return type (`tuple[str, ...]`), only its values change, and those values are written out in Task 4's Interfaces block. `verify.CONTRACT` and `emit.SUITE_NAME` keep their types (`str`) and are set once, in Task 1, then never re-set. `build_toy_run(runs_dir, upto=...)` is used identically in Task 1 Step 2 and Task 6 Step 6.

**One known ordering hazard, stated deliberately:** Task 2's `sed` over `*.py` is safe only because Task 1 has already converted the string literals `"testgen/v1"` and `SUITE_NAME = "testgen"` to their Rubrica values. Running Task 2 before Task 1 would rewrite emitted bytes silently, without the determinism proof. **Do not reorder Tasks 1 and 2.**
