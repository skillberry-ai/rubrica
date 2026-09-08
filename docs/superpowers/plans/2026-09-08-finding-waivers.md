# Finding Waivers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a human record that a `check-refs` finding is correct and its remedy lives elsewhere, so a correct-but-unfixable finding stops holding the run's gate open without disappearing from the output.

**Architecture:** A run-level, human-authored `waivers.json` names a `(check, subject)` pair, the stage where the remedy actually lives, and the finding text it was written against. A registry in a new `waivers.py` says which checks are waivable at all. `Finding` grows a `waived` flag; `_report` prints waived findings but excludes them from the exit code. `rubrica waive` is the only writer, and it refuses to waive a finding that is not currently raised.

**Tech Stack:** Python 3.13, `uv`, pytest, jsonschema (Draft 2020-12), ruff.

**Spec:** [`../specs/2026-09-08-finding-waivers-design.md`](../specs/2026-09-08-finding-waivers-design.md)

## Global Constraints

- Every commit signed **and** DCO'd: `git commit -S -s`. If signing fails, stop and report — never fall back to unsigned.
- Attribution trailer is `Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>`. Never `Co-Authored-By`.
- ruff: `line-length = 100`, `select = ["E","F","I","UP","B","SIM"]`. Run `make check` after editing `CLAUDE.md` or `README.md` (they are not ruff-excluded).
- The three gates must be green at every commit: `make test`, `make check`, `uv run rubrica check-skills` exiting 0.
- Exit codes are load-bearing: `0` clean, `1` findings one per line on stdout, `2` usage error or unreadable/misconfigured run. A stage defect must never surface as `2`. A `1` must never have empty stdout.
- Do not write a test count into any document.
- Comment density here is high and deliberate: comments explain *why*, usually citing a measurement. Match it.
- New behaviour predicates must be measured in **both** directions before they count as a guard: break the thing, confirm red; reword meaning-preservingly, confirm green.

---

### Task 1: The waivers artifact — schema, run path, loader, registry

**Files:**
- Create: `src/rubrica/schema/waivers-0.1.json`
- Create: `src/rubrica/waivers.py`
- Modify: `src/rubrica/paths.py:502` (add a `waivers` property beside `decisions`)
- Modify: `src/rubrica/validate.py:99-106` (add `waivers` to `ARTIFACT_SCHEMAS`)
- Test: `tests/unit/test_waivers.py`

**Interfaces:**
- Consumes: `RunPaths` from `rubrica.paths`; `read_json`, `write_json`, `ArtifactError` from `rubrica.artifacts`; `UsageError` from `rubrica.errors`; `STAGES` from `rubrica.paths`.
- Produces:
  - `WAIVABLE_CHECKS: dict[str, str]` — check name → what its `subject` names
  - `remedy_choices() -> tuple[str, ...]`
  - `load(run: RunPaths) -> list[dict]`
  - `waived_subjects(run: RunPaths, check: str) -> frozenset[str]`
  - `next_id(entries: list[dict]) -> str`
  - `RunPaths.waivers -> Path`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_waivers.py
import json

import pytest

from rubrica import waivers
from rubrica.artifacts import ArtifactError
from rubrica.paths import RunPaths


def _run(tmp_path) -> RunPaths:
    (tmp_path / "run-x").mkdir()
    return RunPaths(tmp_path / "run-x")


def test_an_absent_file_is_no_waivers(tmp_path):
    """The common case. Most runs never record one, and that is not a defect."""
    assert waivers.load(_run(tmp_path)) == []


def test_a_recorded_waiver_loads(tmp_path):
    run = _run(tmp_path)
    run.waivers.write_text(
        json.dumps(
            {
                "version": "0.1",
                "waivers": [
                    {
                        "id": "wv-0001",
                        "check": "claim-utilisation",
                        "subject": "llm-agent-py",
                        "remedy": "triage-rule",
                        "reason": "out of target domain",
                        "finding_text": "no world-model element cites any claim from llm-agent-py",
                        "recorded_at": "2026-09-08T04:12:33Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert waived_ids(run) == {"llm-agent-py"}


def waived_ids(run):
    return set(waivers.waived_subjects(run, "claim-utilisation"))


def test_a_waiver_for_another_check_does_not_leak(tmp_path):
    """The property that keeps a waiver narrow: subjects are per check."""
    run = _run(tmp_path)
    run.waivers.write_text(
        json.dumps(
            {
                "version": "0.1",
                "waivers": [
                    {
                        "id": "wv-0001",
                        "check": "some-other-check",
                        "subject": "llm-agent-py",
                        "remedy": "none",
                        "reason": "r",
                        "finding_text": "t",
                        "recorded_at": "2026-09-08T04:12:33Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert waived_ids(run) == set()


def test_a_malformed_document_raises_rather_than_failing_open(tmp_path):
    """Loud, not safe-by-accident. Failing open would hide a corrupted human
    record behind a gate that then looks correct."""
    run = _run(tmp_path)
    run.waivers.write_text("[]", encoding="utf-8")
    with pytest.raises(ArtifactError):
        waivers.load(run)


def test_a_non_object_entry_raises(tmp_path):
    run = _run(tmp_path)
    run.waivers.write_text(
        json.dumps({"version": "0.1", "waivers": ["nope"]}), encoding="utf-8"
    )
    with pytest.raises(ArtifactError):
        waivers.load(run)


def test_next_id_is_one_past_the_highest_even_with_a_gap(tmp_path):
    """A gap in the sequence must not remint an id already used, which is what
    len(entries) + 1 would do after a human deleted a middle entry."""
    entries = [{"id": "wv-0001"}, {"id": "wv-0007"}]
    assert waivers.next_id(entries) == "wv-0008"


def test_next_id_starts_at_one(tmp_path):
    assert waivers.next_id([]) == "wv-0001"


def test_every_stage_is_a_remedy_and_so_are_the_two_sentinels():
    """`none` has to exist or the ruling this exists for is inexpressible: a
    human who believes no artifact should change must not be made to name a
    remedy they do not believe in."""
    choices = waivers.remedy_choices()
    assert "reconcile-gaps" in choices
    assert "triage-rule" in choices
    assert "outside-the-run" in choices
    assert "none" in choices


def test_the_registry_names_what_a_subject_is():
    """A check absent from the registry is not waivable, and the value is what
    lets the CLI say what a subject means rather than just rejecting one."""
    assert waivers.WAIVABLE_CHECKS["claim-utilisation"] == "artifact_id"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_waivers.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'rubrica.waivers'`

- [ ] **Step 3: Add the `waivers` property to `RunPaths`**

In `src/rubrica/paths.py`, directly after the `decisions` property at line 502:

```python
    @property
    def waivers(self) -> Path:
        """A human's waivers for this run, or an absent file when there are none.

        Beside `manifest.json` and `decisions.md` rather than under a stage's
        numbered directory, because no stage writes it: it records a person's
        ruling about a finding, and the numbering belongs to the stages.
        """
        return self.root / "waivers.json"
```

- [ ] **Step 4: Write the schema**

Create `src/rubrica/schema/waivers-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "waivers-0.1.json",
  "title": "Waivers a human recorded for one run",
  "type": "object",
  "additionalProperties": false,
  "required": ["version", "waivers"],
  "properties": {
    "version": { "const": "0.1" },
    "waivers": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "id",
          "check",
          "subject",
          "remedy",
          "reason",
          "finding_text",
          "recorded_at"
        ],
        "properties": {
          "id": { "type": "string", "pattern": "^wv-[0-9]{4,}$" },
          "check": { "type": "string", "minLength": 1 },
          "subject": { "type": "string", "minLength": 1 },
          "remedy": { "type": "string", "minLength": 1 },
          "reason": { "type": "string", "minLength": 1 },
          "finding_text": { "type": "string", "minLength": 1 },
          "recorded_at": { "type": "string", "minLength": 1 }
        }
      }
    }
  }
}
```

`remedy` is a bare string here rather than an enum on purpose: the enum is
`paths.STAGES` plus two sentinels, and STAGES grows. A hard-coded schema enum
would need regeneration every time a stage is added, and `record_stage` already
sets the precedent of checking a stage name in Python (`if stage not in STAGES`)
while reading the *effort* enum out of the schema. `waive` enforces the choices.

- [ ] **Step 5: Register the kind**

In `src/rubrica/validate.py`, inside `ARTIFACT_SCHEMAS` immediately after the
`"gold": "gold-0.1.json",` line at 105:

```python
    # A fourth category, and deliberately in neither set below. Human-authored
    # like the config kinds, but it *does* live in a run directory, which is what
    # CONFIG_KINDS' "never joined into a run path" excludes. No stage produces it,
    # so it stays out of STAGE_ARTIFACTS and `validate --stage X` never hunts for
    # it. Registered here so `validate_artifact(path, "waivers")` can check a
    # hand-edited file. If a second kind ever lands in this category, give it a
    # named constant -- the comment above CONFIG_KINDS records what restating the
    # literal cost the last time.
    "waivers": "waivers-0.1.json",
```

- [ ] **Step 6: Write `waivers.py`**

Create `src/rubrica/waivers.py`:

```python
"""A human's record that a finding is correct and its remedy is not available here.

`refs.check_claim_utilisation` raises against `01-world-model.json`, which no
dispatchable stage declares in `writes`. When that finding is correct and
unfixable, the orchestrator's one repair attempt is not exhausted but
*unspendable*: every pass it could dispatch must refuse, because the finding
names a file that is not its output. A waiver is how a person records that,
so the gate stops being permanently dirty without the finding disappearing.

A waiver is not an assertion that the finding was wrong, and not a mute button:
the finding keeps printing, prefixed `[waived] `. Only its contribution to the
exit code goes away.

Only a human writes one. The gate-0 argument applies unchanged -- the party that
made a judgment must not also ratify it -- so neither the orchestrator (which
would diagnose and ratify in one move) nor the stage that declined (which would
vouch for its own refusal) may record one.
"""

from __future__ import annotations

from datetime import datetime

from rubrica.artifacts import ArtifactError, append_decision, read_json, write_json
from rubrica.errors import UsageError
from rubrica.paths import STAGES, RunPaths

# Which checks may be waived at all, and what a `subject` names for each. The
# value is documentation with a consumer: the CLI quotes it when it rejects a
# subject, so a person is told what kind of name the check expects rather than
# just that theirs did not match.
#
# A check absent from here is not waivable. That is deliberate -- a waiver
# nothing reads is the shape this project cuts, so a row lands here only
# alongside a check that consults it.
WAIVABLE_CHECKS: dict[str, str] = {
    "claim-utilisation": "artifact_id",
}

# `none` means "the finding is correct and no artifact should change" -- the
# ruling this module was built for, where seven reconcile passes each correctly
# declined an out-of-domain artifact. Without it a human would be forced to name
# a remedy they do not believe in. `outside-the-run` covers a corpus that should
# not have contained the input at all.
_SENTINEL_REMEDIES: tuple[str, ...] = ("outside-the-run", "none")


def remedy_choices() -> tuple[str, ...]:
    """Every stage name, plus the two sentinels. Derived, never restated."""
    return tuple(STAGES) + _SENTINEL_REMEDIES


def load(run: RunPaths) -> list[dict]:
    """Every waiver recorded for this run, `[]` when the file is absent.

    Absent is normal and silent: most runs record none. Malformed *raises*,
    which becomes an exit 2 through cli.py's handler, rather than being treated
    as "no waivers". Failing open would be safe in the narrow sense -- the
    finding would simply reappear -- and it would hide a corrupted human record
    behind a gate that then looks correct, which is the worse failure.
    """
    path = run.waivers
    if not path.exists():
        return []
    doc = read_json(path)
    if not isinstance(doc, dict):
        raise ArtifactError(f"{path}: a waivers document must be a JSON object")
    entries = doc.get("waivers")
    if not isinstance(entries, list):
        raise ArtifactError(f"{path}: a waivers document needs a `waivers` array")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ArtifactError(f"{path}: every waiver must be an object")
    return entries


def waived_subjects(run: RunPaths, check: str) -> frozenset[str]:
    """The subjects waived for `check`.

    Keyed on `(check, subject)` and never on the finding's message text. A text
    key would break on a reformat that changed nothing -- the failure this repo
    has already taken once, where a phrase pin broke on an innocuous rewording.
    `finding_text` is recorded as evidence, not used as a key.
    """
    return frozenset(
        entry["subject"]
        for entry in load(run)
        if entry.get("check") == check and isinstance(entry.get("subject"), str)
    )


def next_id(entries: list[dict]) -> str:
    """One past the highest `wv-` number present.

    Not `len(entries) + 1`, which would remint an id already used after somebody
    deleted a middle entry -- and deleting an entry is how a waiver is revoked,
    so the gap is an expected state rather than a corruption.
    """
    highest = 0
    for entry in entries:
        raw = entry.get("id")
        if isinstance(raw, str) and raw.startswith("wv-") and raw[3:].isdigit():
            highest = max(highest, int(raw[3:]))
    return f"wv-{highest + 1:04d}"
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_waivers.py -q`
Expected: PASS

- [ ] **Step 8: Confirm the schema is well-formed and the kind resolves**

Run:
```bash
uv run python -c "
from rubrica.validate import ARTIFACT_SCHEMAS, schema_dir
from rubrica.artifacts import read_json
print(read_json(schema_dir() / ARTIFACT_SCHEMAS['waivers'])['\$id'])
"
```
Expected: `waivers-0.1.json`

- [ ] **Step 9: Run the full gates**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run rubrica check-skills`
Expected: all green, `check-skills` exit 0. In particular `test_the_config_schemas_belong_to_no_stage` must still pass — it asserts `STAGE_ARTIFACTS` kinds are disjoint from `CONFIG_KINDS` and a subset of `ARTIFACT_SCHEMAS`, and adding a key to `ARTIFACT_SCHEMAS` alone satisfies both.

- [ ] **Step 10: Commit**

```bash
git add src/rubrica/waivers.py src/rubrica/schema/waivers-0.1.json \
        src/rubrica/paths.py src/rubrica/validate.py tests/unit/test_waivers.py
git commit -S -s -m "feat(waivers): add the waivers artifact, its schema and its registry

A human-authored waivers.json records that a finding is correct and its
remedy is not available in the stage the finding names. The registry says
which checks may be waived at all, so a waiver nothing reads cannot be
written.

Malformed raises rather than failing open: treating a corrupt human record
as 'no waivers' would hide it behind a gate that then looks correct.

Refs #35.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 2: `Finding.waived` and the `_report` split

**Files:**
- Modify: `src/rubrica/findings.py:60-73` (add the field, extend `__str__`)
- Modify: `src/rubrica/cli.py:379-383` (`_report`)
- Test: `tests/unit/test_findings_waived.py`

**Interfaces:**
- Consumes: `Finding` from Task 1's unchanged four fields.
- Produces: `Finding(artifact, layer, pointer, message, waived=False)`; `_report` returning `CLEAN` when every finding it was handed is waived.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_findings_waived.py
from pathlib import Path

from rubrica.cli import main
from rubrica.findings import Finding, format_findings


def test_a_finding_is_unwaived_by_default():
    """Additive: every existing construction passes four fields and must keep
    behaving exactly as it did."""
    f = Finding(Path("a.json"), "refs", "/", "boom")
    assert f.waived is False
    assert str(f) == "[refs] a.json#/: boom"


def test_a_waived_finding_says_so_on_its_line():
    """Prefixed rather than suffixed so a line-oriented reader can filter on it
    without parsing the message."""
    f = Finding(Path("a.json"), "refs", "/", "boom", waived=True)
    assert str(f) == "[waived] [refs] a.json#/: boom"


def test_format_findings_still_sorts_stably_with_a_mix():
    a = Finding(Path("a.json"), "refs", "/", "aaa", waived=True)
    b = Finding(Path("b.json"), "refs", "/", "bbb")
    assert format_findings([b, a]).splitlines() == [
        "[waived] [refs] a.json#/: aaa",
        "[refs] b.json#/: bbb",
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_findings_waived.py -q`
Expected: FAIL — `TypeError: Finding.__init__() got an unexpected keyword argument 'waived'`

- [ ] **Step 3: Add the field and extend `__str__`**

In `src/rubrica/findings.py`, replace the field block and `__str__` (lines 65-73):

```python
    artifact: Path
    layer: str
    pointer: str
    message: str
    # Last and defaulted, so every one of the existing constructions keeps
    # working unchanged. True only where a check consulted waivers.WAIVABLE_CHECKS
    # and found a human's waiver for this finding's (check, subject) pair.
    #
    # The finding is still reported. A waiver removes its contribution to the
    # exit code and nothing else -- see cli._report, which is the one place that
    # distinction is applied.
    waived: bool = False

    def __str__(self) -> str:
        where = f"{self.artifact}#{self.pointer}" if self.pointer else str(self.artifact)
        line = f"[{self.layer}] {where}: {self.message}"
        return f"[waived] {line}" if self.waived else line
```

- [ ] **Step 4: Split `_report`**

In `src/rubrica/cli.py`, replace `_report` (lines 379-383):

```python
def _report(findings) -> int:
    """Print every finding; let only the unwaived ones set the exit code.

    The split lives here rather than in the check-refs branch so it is uniform
    across every command that reports findings, and inert for every command whose
    checks never set the flag.

    Both invariants of the exit-code contract survive: a `1` still means unwaived
    findings, one per line on stdout, and still never has empty stdout. A run
    whose only findings are waived exits 0 *with those lines still printed* --
    which is the point, since a waived finding a reader can no longer see is a
    mute button rather than a record.
    """
    if not findings:
        return CLEAN
    print(format_findings(findings))
    return FINDINGS if any(not f.waived for f in findings) else CLEAN
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_findings_waived.py -q`
Expected: PASS

- [ ] **Step 6: Measure the guard in the other direction**

Temporarily change `_report`'s last line to `return FINDINGS`, run
`uv run pytest tests/unit/test_findings_waived.py -q` and confirm it still passes
(these tests do not cover `_report`), then run
`uv run pytest tests/unit/test_cli.py -q` and confirm it also still passes.
This proves the exit-code behaviour is **not yet guarded** — Task 3 is where the
guard for it lands. Revert the temporary change before continuing.

- [ ] **Step 7: Run the full gates**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run rubrica check-skills`
Expected: all green. Watch specifically for tests asserting empty stdout: every
such assertion in the suite guards an **exit-2** path, and `_report` is not
reached on those, so none should move.

- [ ] **Step 8: Commit**

```bash
git add src/rubrica/findings.py src/rubrica/cli.py tests/unit/test_findings_waived.py
git commit -S -s -m "feat(findings): let a waived finding print without setting the exit code

Finding grows a defaulted `waived`, and _report prints every finding while
letting only the unwaived ones decide the code. A run whose only findings
are waived exits 0 with those lines still on stdout -- a waived finding a
reader cannot see would be a mute button rather than a record.

Refs #35.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 3: Teach `check_claim_utilisation` about waivers

**Files:**
- Modify: `src/rubrica/refs.py:2878-2911` (`check_claim_utilisation`)
- Test: `tests/unit/test_refs_claim_utilisation_waivers.py`

**Interfaces:**
- Consumes: `waivers.waived_subjects` from Task 1; `Finding(..., waived=...)` from Task 2.
- Produces: no new names. `check_claim_utilisation` keeps its signature and returns findings whose `waived` reflects `waivers.json`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_refs_claim_utilisation_waivers.py
import json

from rubrica import refs
from rubrica.cli import main
from tests.toy import build_toy_run


def _waive(run, subject, check="claim-utilisation"):
    run.waivers.write_text(
        json.dumps(
            {
                "version": "0.1",
                "waivers": [
                    {
                        "id": "wv-0001",
                        "check": check,
                        "subject": subject,
                        "remedy": "triage-rule",
                        "reason": "out of the target's domain; every pass declined it",
                        "finding_text": "recorded verbatim by `rubrica waive`",
                        "recorded_at": "2026-09-08T04:12:33Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _uncited(run):
    """Give the run an input whose claims nothing in the world model cites."""
    claims = run.claims_dir / "orphan.json"
    claims.write_text(
        json.dumps(
            {
                "version": "0.1",
                "artifact_id": "orphan",
                "claims": [
                    {
                        "id": "clm-orphan-001",
                        "kind": "actor",
                        "text": "an actor no world-model element cites",
                        "confidence": "high",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_an_uncited_artifact_is_a_finding(tmp_path):
    """The behaviour that must not change: without a waiver this is still a
    finding, and still names the world model."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    found = refs.check_claim_utilisation(run)
    assert [f.message for f in found if "orphan" in f.message]
    assert all(not f.waived for f in found)


def test_a_waiver_marks_that_finding_waived(tmp_path):
    run = build_toy_run(tmp_path)
    _uncited(run)
    _waive(run, "orphan")
    found = [f for f in refs.check_claim_utilisation(run) if "orphan" in f.message]
    assert found and all(f.waived for f in found)


def test_a_waiver_for_a_different_subject_does_not_suppress(tmp_path):
    """The narrowness property. A waiver is for one subject, not for the check."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    _waive(run, "some-other-artifact")
    found = [f for f in refs.check_claim_utilisation(run) if "orphan" in f.message]
    assert found and all(not f.waived for f in found)


def test_check_refs_exits_zero_when_the_only_finding_is_waived(tmp_path, capsys):
    """The whole point: the gate stops being permanently dirty, and the finding
    is still on stdout so a reader still sees it."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    assert main(["check-refs", "--run", str(run.root)]) == 1
    _waive(run, "orphan")
    code = main(["check-refs", "--run", str(run.root)])
    out = capsys.readouterr().out
    assert code == 0
    assert "[waived]" in out and "orphan" in out


def test_check_refs_still_exits_one_with_an_unwaived_finding_beside_it(tmp_path):
    """A waiver must not clear the gate for anything but itself."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    run.world_model.write_text("{}", encoding="utf-8")
    _waive(run, "orphan")
    assert main(["check-refs", "--run", str(run.root)]) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_refs_claim_utilisation_waivers.py -q`
Expected: FAIL — the waived assertions fail because nothing sets the flag yet.

- [ ] **Step 3: Import the module and expose (subject, finding) pairs**

In `src/rubrica/refs.py`, add to the import block after line 37:

```python
from rubrica.waivers import waived_subjects
```

Split the check so the subject is returned *beside* the finding rather than
recoverable only by parsing the message. `waive` needs an exact subject match,
and `"orphan" in "...from orphan2 (1 claims)"` is True — substring matching would
waive the wrong artifact. Parsing the subject back out of the prose is the text
keying this design rejects, so the subject travels as data:

```python
def claim_utilisation_findings(run: RunPaths) -> list[tuple[str, Finding]]:
    """(subject, finding) pairs for the zero-citation check.

    The subject travels beside the finding rather than being recoverable from its
    message. `rubrica waive` needs to match a subject exactly, and a substring
    match over the message is wrong in a way that is easy to miss: an artifact id
    that is a prefix of another ("orphan" against "orphan2") would waive the wrong
    one. Parsing an id back out of prose is the text keying this design rejects.
    """
    out: list[tuple[str, Finding]] = []
    # Read once rather than per artifact: this raises on a malformed waivers.json,
    # and doing it before the loop means a corrupt human record surfaces as one
    # exit 2 rather than as a partial list of findings.
    waived = waived_subjects(run, "claim-utilisation")
    for entry in claim_utilisation(run)["artifacts"]:
        # `entry["total"]` guards a claims file with zero claims -- exactly the first
        # of the two causes named above ("rb-extract produced nothing usable"), which
        # `rb-extract` is explicitly allowed to produce for an input with nothing to
        # extract. Exempting it is not a hole: the report above still shows the
        # artifact at 0/0, so a human at gate 1 still sees it, it just is not a finding.
        if entry["total"] and entry["cited"] == 0:
            out.append(
                (
                    entry["artifact_id"],
                    Finding(
                        run.world_model,
                        "refs",
                        "/",
                        f"no world-model element cites any claim from "
                        f"{entry['artifact_id']} ({entry['total']} claims)",
                    # The third cause this check cannot distinguish from its two:
                    # rb-extract produced good claims and every reconcile pass
                    # correctly declined them as out of the target's domain. That
                    # is not a defect, and the finding names an artifact no
                    # dispatchable stage owns, so no repair can clear it. A human
                    # rules on it with `rubrica waive`.
                        waived=entry["artifact_id"] in waived,
                    ),
                )
            )
    return out


def check_claim_utilisation(run: RunPaths) -> list[Finding]:
    return [finding for _, finding in claim_utilisation_findings(run)]


# check name -> the accessor that yields its (subject, finding) pairs. Kept here
# rather than in waivers.py because that module must not import refs (refs imports
# it), and asserted equal to waivers.WAIVABLE_CHECKS by a test: the comment above
# validate.CONFIG_KINDS records what letting two such sets drift cost last time.
WAIVABLE_FINDING_SOURCES: dict[str, Callable[[RunPaths], list[tuple[str, Finding]]]] = {
    "claim-utilisation": claim_utilisation_findings,
}
```

`Callable` needs `from collections.abc import Callable` in `refs.py`'s imports if
it is not already there — check before adding, ruff's `F401` will flag a duplicate.

Also extend the docstring's closing paragraph with the third cause:

```python
    Two causes are named above and both are real defects. There is a third this
    check cannot distinguish from them: rb-extract produced good claims and every
    reconcile pass correctly declined them, because the artifact is outside the
    target's domain. Measured on a tau2-airline run where all seven passes dropped
    two admitted harness files, each recording its reason. That case is not
    repairable here -- the finding names 01-world-model.json, which no dispatchable
    stage declares in `writes` -- so a human waives it and the finding keeps
    printing without holding the gate open.
    """
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_refs_claim_utilisation_waivers.py -q`
Expected: PASS

- [ ] **Step 5: Check for an import cycle**

Run: `uv run python -c "import rubrica.refs; import rubrica.cli; print('ok')"`
Expected: `ok`. `refs` → `waivers` → `paths`/`artifacts`/`errors` only, so no
cycle. If a later change makes `waivers` import `manifest` at module level, that
becomes `refs → waivers → manifest → validate`, and the import must move inside
the function — the pattern `skills.py:318` already uses for the same reason.

- [ ] **Step 6: Measure the guard in both directions**

Delete the `waived=` argument, run the module's tests, confirm red. Restore it.
Then reword the finding message meaning-preservingly (e.g. `no world-model
element cites any claim from` → `no element of the world model cites a claim
from`), run the tests, confirm they stay **green** — which is the property the
`(check, subject)` key exists for, since a text key would have broken here.
Revert the wording.

- [ ] **Step 7: Test the unreadable-input paths**

Run:
```bash
uv run pytest tests/unit/test_refs_claim_utilisation_waivers.py -q
python3 - <<'PY'
# a malformed waivers.json must be an exit 2, not a 1 and not a crash
import json, subprocess, sys, tempfile, pathlib
PY
```
Then add to the test module:

```python
def test_a_malformed_waivers_file_is_exit_two_not_a_finding(tmp_path, capsys):
    """A misconfigured run, not a stage defect. A 1 here would spend the run's
    one repair attempt on a stage whose output was never the problem."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    run.waivers.write_text("{not json", encoding="utf-8")
    assert main(["check-refs", "--run", str(run.root)]) == 2
    assert capsys.readouterr().out.strip() == "", "an exit 2 must not print a finding line"


def test_an_unreadable_waivers_file_is_exit_two(tmp_path, capsys):
    run = build_toy_run(tmp_path)
    _uncited(run)
    run.waivers.write_text("{}", encoding="utf-8")
    run.waivers.chmod(0o000)
    try:
        assert main(["check-refs", "--run", str(run.root)]) == 2
        assert capsys.readouterr().out.strip() == ""
    finally:
        run.waivers.chmod(0o644)
```

Run: `uv run pytest tests/unit/test_refs_claim_utilisation_waivers.py -q`
Expected: PASS. If either returns 1 instead of 2, the `ArtifactError`/`OSError` is
being swallowed somewhere between `load` and `cli.main`'s outer handler — fix
that rather than relaxing the assertion.

- [ ] **Step 8: Run the full gates**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run rubrica check-skills`
Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add src/rubrica/refs.py tests/unit/test_refs_claim_utilisation_waivers.py
git commit -S -s -m "feat(refs): let a human's waiver clear the zero-citation finding

check_claim_utilisation names two causes and cannot distinguish a third:
rb-extract produced good claims and every reconcile pass correctly declined
them as out of the target's domain. Measured where all seven passes dropped
two admitted harness files, each recording its reason.

The finding names 01-world-model.json, which no dispatchable stage declares
in writes, so no repair clears it. It now carries the waived flag when a
human has ruled, and keeps printing either way.

Refs #35.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 4: `rubrica waive`

**Files:**
- Modify: `src/rubrica/waivers.py` (add `record`)
- Modify: `src/rubrica/cli.py:101-131` (`SUBCOMMANDS`), `:310-312` (parser), `:854-872` (handler)
- Test: `tests/unit/test_cli_waive.py`

**Interfaces:**
- Consumes: `load`, `next_id`, `remedy_choices`, `WAIVABLE_CHECKS` from Task 1; `refs.check_claim_utilisation` from Task 3.
- Produces: `waivers.record(run, *, check, subject, remedy, reason, finding_text, now=None) -> str` returning the new id; the `waive` subcommand.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_cli_waive.py
import json

from rubrica.artifacts import read_json
from rubrica.cli import main
from rubrica.validate import validate_artifact
from tests.toy import build_toy_run
from tests.unit.test_refs_claim_utilisation_waivers import _uncited


def _waive_argv(run, subject="orphan", remedy="triage-rule", check="claim-utilisation"):
    return [
        "waive", "--run", str(run.root), "--check", check, "--subject", subject,
        "--remedy", remedy, "--reason", "every reconcile pass declined it as out of domain",
    ]


def test_waiving_a_live_finding_records_it(tmp_path):
    run = build_toy_run(tmp_path)
    _uncited(run)
    assert main(_waive_argv(run)) == 0
    doc = read_json(run.waivers)
    assert doc["version"] == "0.1"
    (entry,) = doc["waivers"]
    assert entry["id"] == "wv-0001"
    assert entry["check"] == "claim-utilisation"
    assert entry["subject"] == "orphan"
    assert entry["remedy"] == "triage-rule"
    assert not validate_artifact(run.waivers, "waivers")


def test_the_finding_text_is_copied_from_the_finding_not_typed(tmp_path):
    """The integrity property: a human retyping a finding is a human who can
    paraphrase one, so there is no --finding-text flag at all."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    main(_waive_argv(run))
    entry = read_json(run.waivers)["waivers"][0]
    assert entry["finding_text"] == (
        "no world-model element cites any claim from orphan (1 claims)"
    )


def test_waiving_a_finding_that_is_not_raised_is_refused(tmp_path, capsys):
    """No pre-emptive waivers, and none left behind by a fixed defect."""
    run = build_toy_run(tmp_path)  # nothing uncited
    assert main(_waive_argv(run)) == 2
    assert not run.waivers.exists()
    assert "no such finding" in capsys.readouterr().err


def test_an_unregistered_check_is_refused(tmp_path, capsys):
    run = build_toy_run(tmp_path)
    _uncited(run)
    assert main(_waive_argv(run, check="not-a-check")) == 2
    assert not run.waivers.exists()


def test_a_remedy_outside_the_choices_is_refused(tmp_path):
    run = build_toy_run(tmp_path)
    _uncited(run)
    assert main(_waive_argv(run, remedy="nowhere")) == 2
    assert not run.waivers.exists()


def test_none_is_an_accepted_remedy(tmp_path):
    """The ruling this exists for must be expressible."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    assert main(_waive_argv(run, remedy="none")) == 0
    assert read_json(run.waivers)["waivers"][0]["remedy"] == "none"


def test_the_ruling_also_lands_in_decisions_md(tmp_path):
    run = build_toy_run(tmp_path)
    _uncited(run)
    main(_waive_argv(run))
    assert "waived claim-utilisation/orphan" in run.decisions.read_text(encoding="utf-8")


def test_a_reason_with_a_newline_is_refused(tmp_path):
    """decisions.md is one entry per line; an embedded newline corrupts the
    append-only format for every line written after it -- the guard `decide`
    already carries, for the same reason."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    argv = _waive_argv(run)
    argv[argv.index("--reason") + 1] = "line one\nline two"
    assert main(argv) == 2
    assert not run.waivers.exists()


def test_the_two_registries_cannot_drift():
    """waivers.WAIVABLE_CHECKS says what is waivable; refs.WAIVABLE_FINDING_SOURCES
    says how to find its findings. A row in one and not the other is either a check
    the CLI offers and cannot run, or an accessor nothing can reach."""
    from rubrica import refs, waivers

    assert set(refs.WAIVABLE_FINDING_SOURCES) == set(waivers.WAIVABLE_CHECKS)


def test_a_subject_that_is_a_prefix_of_another_is_not_confused(tmp_path):
    """Measured trap: a substring match would waive orphan2 when asked for
    orphan, because the id appears inside the other's message."""
    run = build_toy_run(tmp_path)
    _uncited(run)
    (run.claims_dir / "orphan2.json").write_text(
        json.dumps(
            {
                "version": "0.1",
                "artifact_id": "orphan2",
                "claims": [
                    {"id": "clm-orphan2-001", "kind": "actor",
                     "text": "another uncited actor", "confidence": "high"}
                ],
            }
        ),
        encoding="utf-8",
    )
    assert main(_waive_argv(run, subject="orphan")) == 0
    entry = read_json(run.waivers)["waivers"][0]
    assert entry["subject"] == "orphan"
    assert "orphan2" not in entry["finding_text"]


def test_a_second_waiver_appends_rather_than_replacing(tmp_path):
    run = build_toy_run(tmp_path)
    _uncited(run)
    main(_waive_argv(run))
    # a second uncited artifact, so a second finding exists to waive
    (run.claims_dir / "orphan2.json").write_text(
        json.dumps(
            {
                "version": "0.1",
                "artifact_id": "orphan2",
                "claims": [
                    {"id": "clm-orphan2-001", "kind": "actor",
                     "text": "another uncited actor", "confidence": "high"}
                ],
            }
        ),
        encoding="utf-8",
    )
    assert main(_waive_argv(run, subject="orphan2")) == 0
    ids = [e["id"] for e in read_json(run.waivers)["waivers"]]
    assert ids == ["wv-0001", "wv-0002"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_cli_waive.py -q`
Expected: FAIL — `invalid choice: 'waive'`

- [ ] **Step 3: Add `record` to `waivers.py`**

Append to `src/rubrica/waivers.py`:

```python
def record(
    run: RunPaths,
    *,
    check: str,
    subject: str,
    remedy: str,
    reason: str,
    finding_text: str,
    now: datetime | None = None,
) -> str:
    """Append one waiver and return its id.

    `finding_text` is the caller's copy of the finding this waiver answers, and
    the CLI takes it from the finding itself rather than from a flag -- a human
    retyping a finding is a human who can paraphrase one.
    """
    if check not in WAIVABLE_CHECKS:
        raise UsageError(
            f"unknown check {check!r}; waivable checks are "
            f"{', '.join(sorted(WAIVABLE_CHECKS))}"
        )
    choices = remedy_choices()
    if remedy not in choices:
        raise UsageError(f"unknown remedy {remedy!r}; expected one of {', '.join(choices)}")
    text = reason.strip()
    if not text:
        raise UsageError("a waiver reason cannot be empty")
    if "\n" in text:
        raise UsageError(
            "a waiver reason cannot contain a newline; decisions.md is one line per entry"
        )

    # Imported here rather than at module scope: refs.py imports this module, and
    # manifest.py imports validate.py, so a module-level import would build
    # refs -> waivers -> manifest -> validate at import time. skills.py:318 defers
    # an import for the same reason.
    from rubrica.manifest import utc_stamp

    entries = load(run)
    waiver_id = next_id(entries)
    entries.append(
        {
            "id": waiver_id,
            "check": check,
            "subject": subject,
            "remedy": remedy,
            "reason": text,
            "finding_text": finding_text,
            "recorded_at": utc_stamp(now),
        }
    )
    write_json(run.waivers, {"version": "0.1", "waivers": entries})
    append_decision(
        run.decisions,
        f"- {utc_stamp(now)} waived {check}/{subject}: remedy {remedy}; {text}",
    )
    return waiver_id
```

- [ ] **Step 4: Declare the subcommand**

In `src/rubrica/cli.py`, add to `SUBCOMMANDS` after the `decide` entry (line 125):

```python
    ("waive", "record a human's waiver of one finding whose remedy lives elsewhere"),
```

Add the parser after the `p_decide` block (line 312):

```python
    p_waive = parsers["waive"]
    p_waive.add_argument("--run", required=True)
    p_waive.add_argument("--check", required=True, choices=sorted(waivers.WAIVABLE_CHECKS))
    p_waive.add_argument("--subject", required=True)
    p_waive.add_argument("--remedy", required=True, choices=waivers.remedy_choices())
    p_waive.add_argument("--reason", required=True)
```

Add the import near the other `rubrica` imports at the top of `cli.py`:

```python
from rubrica import waivers
```

- [ ] **Step 5: Add the handler**

In `src/rubrica/cli.py`, after the `decide` handler's `return CLEAN` (line 872):

```python
        if args.command == "waive":
            run = _run_dir(args.run)
            # The finding must exist before it can be waived. Running the check
            # here is the whole integrity property: no pre-emptive waivers, none
            # left behind by a fixed defect, and `finding_text` is copied from
            # the finding rather than typed by a person who could paraphrase it.
            #
            # Dispatched through the registry rather than calling one check
            # directly: --check is a choice over waivers.WAIVABLE_CHECKS, so
            # hardcoding one accessor would silently run the wrong check the day a
            # second row lands.
            pairs = refs.WAIVABLE_FINDING_SOURCES[args.check](run)
            matched = next(
                (finding for subject, finding in pairs if subject == args.subject),
                None,
            )
            if matched is None:
                print(
                    f"error: no such finding to waive: {args.check} raises nothing for "
                    f"{waivers.WAIVABLE_CHECKS[args.check]} {args.subject!r}",
                    file=sys.stderr,
                )
                return USAGE
            # (UsageError, OSError), matching decide above: waivers.json being a
            # directory, or the run being read-only, raises a bare OSError that
            # would otherwise become a fabricated exit-1 "internal" finding.
            try:
                waiver_id = waivers.record(
                    run,
                    check=args.check,
                    subject=args.subject,
                    remedy=args.remedy,
                    reason=args.reason,
                    finding_text=matched.message,
                )
            except (UsageError, OSError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return USAGE
            print(waiver_id)
            return CLEAN
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli_waive.py -q`
Expected: PASS

- [ ] **Step 7: Confirm the docs gate now fails, then satisfy it in Task 6**

Run: `uv run pytest tests/unit/test_docs_accuracy.py -q`
Expected: FAIL — `docs/reference/cli.md has no `rubrica waive` section`. That
failure is the guard working; Task 6 fixes the document, not the assertion.

- [ ] **Step 8: Commit**

```bash
git add src/rubrica/waivers.py src/rubrica/cli.py tests/unit/test_cli_waive.py
git commit -S -s -m "feat(cli): add rubrica waive, which cannot waive an unraised finding

The subcommand runs the named check and refuses when nothing matches the
subject, so there are no pre-emptive waivers and none left behind by a fixed
defect. finding_text is copied from the matched finding rather than typed:
there is no --finding-text flag, because a human retyping a finding is a
human who can paraphrase one.

The ruling also lands in decisions.md, so the prose trail stays in the file
a human already reads at every gate.

Refs #35.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 5: `gate-brief` shows the active waivers

**Files:**
- Modify: `src/rubrica/brief.py` (add `_waiver_lines`, call it from `_gate_0`, `_gate_1`, `_gate_2`, `_gate_3`)
- Test: `tests/unit/test_brief_waivers.py`

**Interfaces:**
- Consumes: `waivers.load` from Task 1.
- Produces: `_waiver_lines(run: RunPaths) -> list[str]` — `[]` when there are none.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_brief_waivers.py
import json

import pytest

from rubrica.brief import GATES, gate_brief
from tests.toy import build_toy_run


def _waive(run, remedy="triage-rule"):
    run.waivers.write_text(
        json.dumps(
            {
                "version": "0.1",
                "waivers": [
                    {
                        "id": "wv-0001",
                        "check": "claim-utilisation",
                        "subject": "llm-agent-py",
                        "remedy": remedy,
                        "reason": "every reconcile pass declined it as out of domain",
                        "finding_text": "no world-model element cites any claim from llm-agent-py",
                        "recorded_at": "2026-09-08T04:12:33Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize("gate", GATES)
def test_a_waiver_appears_at_every_gate(gate, tmp_path):
    """A waived finding is re-read at each gate rather than forgotten after the
    one ruling that recorded it."""
    run = build_toy_run(tmp_path)
    _waive(run)
    text = gate_brief(run, gate)
    assert "wv-0001" in text
    assert "llm-agent-py" in text
    assert "triage-rule" in text


@pytest.mark.parametrize("gate", GATES)
def test_no_waiver_section_when_there_are_none(gate, tmp_path):
    """The common case must stay quiet -- an empty section at every gate is
    noise a reader learns to skip."""
    run = build_toy_run(tmp_path)
    assert "Waivers" not in gate_brief(run, gate)


def test_remedy_none_reads_as_accepted_rather_than_deferred(tmp_path):
    """`none` and a stage name say different things about whether anybody still
    owes work, so they must not render identically."""
    run = build_toy_run(tmp_path)
    _waive(run, remedy="none")
    text = gate_brief(run, 1)
    assert "accepted; no artifact should change" in text


def test_a_malformed_waivers_file_does_not_crash_the_brief(tmp_path):
    """gate-brief is a report and always exits clean on a readable run; a
    malformed artifact is check-refs' finding to raise, not this command's."""
    run = build_toy_run(tmp_path)
    run.waivers.write_text("{not json", encoding="utf-8")
    text = gate_brief(run, 1)
    assert "could not be read" in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_brief_waivers.py -q`
Expected: FAIL — no waiver text in any brief.

- [ ] **Step 3: Add `_waiver_lines`**

In `src/rubrica/brief.py`, after `_quietly` (line 197):

```python
def _waiver_lines(run: RunPaths) -> list[str]:
    """The waivers in force, or [] when there are none.

    Shown at every gate rather than only at the one where the waiver was
    written: a waived finding is a standing ruling, and a reader at gate 3 has
    as much reason to re-read it as the person who recorded it at gate 1.

    Read through _quietly's reasoning rather than waivers.load's: this is a
    report, and a malformed artifact is check-refs' finding to raise. Crashing
    here, or exiting non-zero, would make a report into a second gate.
    """
    doc = _quietly(run.waivers)
    if doc is None:
        return ["Waivers: waivers.json could not be read.", ""] if run.waivers.exists() else []
    entries = _dicts(_mapping(doc).get("waivers"))
    if not entries:
        return []
    lines = [f"Waivers in force: {len(entries)}"]
    for entry in entries:
        remedy = entry.get("remedy", "?")
        # `none` is the ruling that nothing should change, and it must not read
        # like a deferral to a stage that still owes work.
        gloss = "accepted; no artifact should change" if remedy == "none" else f"remedy {remedy}"
        lines.append(
            f"  {entry.get('id', '?')} {entry.get('check', '?')}/"
            f"{entry.get('subject', '?')} -- {gloss}"
        )
        lines.extend(_fold(str(entry.get("reason", "")), "    ", "    "))
    lines.append("")
    return lines
```

- [ ] **Step 4: Call it from every gate**

In each of `_gate_0`, `_gate_1`, `_gate_2` and `_gate_3`, immediately after the
`lines = [f"GATE N -- {run.root}", ""]` initialiser, add:

```python
    lines.extend(_waiver_lines(run))
```

For `_gate_2`, place it before the `coverage is None` early return, so a waiver
still shows on a run that has not reached coverage yet.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_brief_waivers.py -q`
Expected: PASS

- [ ] **Step 6: Confirm gate-brief still always exits clean**

Run: `uv run pytest tests/unit/ -k brief -q`
Expected: PASS. `gate-brief` is a report, not a gate: it must still exit 0 on
every readable run, including one carrying a waiver.

- [ ] **Step 7: Run the full gates**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run rubrica check-skills`
Expected: green except `test_docs_accuracy.py`'s `rubrica waive` section, which Task 6 closes.

- [ ] **Step 8: Commit**

```bash
git add src/rubrica/brief.py tests/unit/test_brief_waivers.py
git commit -S -s -m "feat(brief): show the waivers in force at every gate

A waived finding is a standing ruling, so a reader at gate 3 has as much
reason to re-read it as the person who recorded it at gate 1. remedy `none`
renders as an acceptance rather than as a deferral, because the two say
different things about whether anybody still owes work.

Read through _quietly rather than waivers.load: gate-brief is a report, and
a malformed artifact is check-refs' finding to raise.

Refs #35.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 6: Documents

**Files:**
- Modify: `docs/reference/cli.md` (a `rubrica waive` section)
- Modify: `docs/reference/artifacts.md` (the `waivers` kind)
- Modify: `docs/design/limitations.md` (point the two parked entries at the mechanism; record the third cause)
- Modify: `CLAUDE.md` (the deterministic-subcommands rulings)
- Test: `tests/unit/test_docs_accuracy.py` (existing; must go green)

**Interfaces:**
- Consumes: everything above. Produces no code.

- [ ] **Step 1: Run the docs gate to see exactly what it demands**

Run: `uv run pytest tests/unit/test_docs_accuracy.py -q`
Expected: FAIL naming the missing `rubrica waive` section in `docs/reference/cli.md`.

- [ ] **Step 2: Write the `cli.md` section**

Match the surrounding sections' shape. Cover: what it records, that only a human
runs it, that it refuses a finding that is not raised, that `finding_text` is
copied rather than typed, the `--remedy` choices including what `none` means, and
that a waived finding still prints while no longer setting the exit code.

- [ ] **Step 3: Write the `artifacts.md` entry**

Name the kind as `` `waivers` `` (backticked — the parametrized check is
backtick-delimited so `suite-expected` cannot satisfy a check for `expected`).
State that it is human-authored, lives at the run root, is written only by
`rubrica waive`, is append-only, and is in `ARTIFACT_SCHEMAS` but in neither
`STAGE_ARTIFACTS` nor `CONFIG_KINDS`, with the reason for each.

- [ ] **Step 4: Update `limitations.md`**

Three edits, and none of them deletes a record:

1. Under *"A re-seed whose remedy lies outside `rb-instantiate`'s `writes`
   cannot be repaired at all"* — add that the owed disposition now exists as
   `rubrica waive`, and that unparking this instance is a `WAIVABLE_CHECKS` row
   plus a subject key on the finding, not a second mechanism.
2. Under *"The rejection notice cannot express an escalated re-seed"* — same
   pointer, since the entry already says both are one missing concept.
3. A new entry recording the third cause `check_claim_utilisation` cannot
   distinguish, with the measurement: a tau2-airline run of 36 inputs where gate 0
   admitted two harness files on contract grounds and all seven reconcile passes
   declined them on domain grounds, each recording its reason, leaving a finding
   no repair could clear.

- [ ] **Step 5: Update `CLAUDE.md`**

Add `waive` to the deterministic-subcommands rulings, beside `decide` and
`set-limit`, stating the judgment rather than the list entry: a waiver is a
human's record that a finding is correct and its remedy is not available in the
stage the finding names; only a human writes one, because a stage or the
orchestrator ratifying its own judgment is what gate 0 exists to forbid; and a
waived finding still prints.

- [ ] **Step 6: Run `make check` — `CLAUDE.md` is not ruff-excluded**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: clean. `docs/` is ruff-excluded but `CLAUDE.md` is not, so a code block
edited there must be formatted.

- [ ] **Step 7: Run every gate**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run rubrica check-skills`
Expected: all green, `check-skills` exit 0.

- [ ] **Step 8: Commit**

```bash
git add docs/reference/cli.md docs/reference/artifacts.md docs/design/limitations.md CLAUDE.md
git commit -S -s -m "docs: Document rubrica waive and unpark what it now reaches

cli.md and artifacts.md gain the subcommand and the kind. limitations.md's
two parked entries point at the mechanism they said was owed, and a new
entry records the third cause check_claim_utilisation cannot distinguish
from its two, with the run it was measured on.

Refs #35.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```
