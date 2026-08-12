# Claim Utilisation and Observable Judgment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a stage that silently drops evidence visible, without punishing a
stage that correctly drops noise.

**Architecture:** One new module computes per-artifact claim utilisation; the
Layer-2 gate and the new reporting subcommand both call it, so they cannot come
to disagree. Two skills gain one quantified sentence each, guarded by
section-scoped prose tests measured in both directions. Four live recordings are
refreshed and one guard test retired, per a recorded human ruling.

**Tech Stack:** Python 3.13, `uv`, pytest, ruff; `scripts/dispatch-stage.sh` for
the re-records.

**Spec:** [`docs/superpowers/specs/2026-08-12-claim-utilisation-and-observable-judgment-design.md`](../specs/2026-08-12-claim-utilisation-and-observable-judgment-design.md)

## Global Constraints

- **Every commit signed and DCO'd: `git commit -S -s`.** Both flags. If signing
  fails, **stop and report it** — never fall back to unsigned, never work around.
- Attribution trailer exactly `Assisted-By: Claude (Anthropic AI)
  <noreply@anthropic.com>`. Never `Co-Authored-By` or `Made-with`.
- ruff: `line-length = 100`, `select = ["E","F","I","UP","B","SIM"]`. `docs/` is
  excluded and committed design records must not be reformatted; `tests/` and
  `src/` are **not** excluded.
- `make check` clean and `uv run rubrica check-skills` exit 0 at every commit.
- **Test baseline entering this plan: 1139 passed, 4 skipped** (measured
  2026-08-12 on `main` at `3d7bb2a`). Every task re-measures.
- The exit-code contract is load-bearing: `0` clean, `1` findings **one per line
  on stdout**, `2` usage error or an unreadable/misconfigured run. A stage defect
  must never surface as `2`; a `1` must never have empty stdout.
- Comment density is high and deliberate: comments explain *why*, citing a
  measurement. Match it.
- Assertions on skill prose must be scoped with `skills.section_body(skill,
  "3. Method")`, never `skill.body` — the frontmatter `description:` and the
  contract block satisfy naive substring checks, which is why roughly nineteen
  assertions here were once measured satisfiable by unrelated content.

### One deviation from the spec, deliberate

Spec §5 names the subcommand `claim-coverage`. **Use `claim-utilisation`
instead.** "Coverage" is already the stage-03 artifact vocabulary
(`03-coverage/`, `coverage.holes`, `capability_matrix`), and a subcommand called
`claim-coverage` would read as belonging to it. The spec's own prose says
"utilisation" throughout. Everything else in §5 stands.

---

## File Structure

**Created:**

| Path | Responsibility |
|---|---|
| `src/rubrica/utilisation.py` | Compute per-artifact claim utilisation. One function, its own module — the `metrics.py` precedent. |
| `tests/unit/test_utilisation.py` | Unit tests for that function and the new gate. |

**Modified:**

| Path | Change |
|---|---|
| `src/rubrica/refs.py` | Add `check_claim_utilisation`; register in `check_all` after `check_world_model`. |
| `src/rubrica/cli.py` | Add `claim-utilisation` to `SUBCOMMANDS` and wire the branch. |
| `src/rubrica/skills/rb-reconcile/SKILL.md` | One sentence after Method step 3. |
| `src/rubrica/skills/rb-extract/SKILL.md` | One sentence in Method. |
| `tests/unit/test_skills_reconcile.py` | One scoped prose test (8 tests today). |
| `tests/unit/test_skills_extract.py` | One scoped prose test (7 tests today). |
| `tests/unit/test_refusal_fixtures.py` | Delete `test_the_recorded_world_model_keeps_its_pre_rubrica_spelling` (line 259). |
| `CLAUDE.md` | "Twelve deterministic subcommands" → thirteen; add to the list; re-measure baseline. |
| `src/rubrica/skills/rb-{extract,reconcile}/exercise.md` | Re-recorded. |
| `tests/fixtures/toy-{gap,contradiction}/recorded/01-world-model.json` | Re-recorded. |

**Why the gate and the report share one function.** `metrics.py`'s docstring
states the rule: a computation duplicated across two tools "is how the two tools
would come to disagree." `refs.check_claim_utilisation` and the
`claim-utilisation` subcommand must never disagree about what utilisation means,
so both call `utilisation.claim_utilisation`.

**A refinement on the spec's stated limitation.** Spec §2 records that
`_claim_ids` unions ids into a set, so per-file attribution is ambiguous when two
files define one id. `refs._claim_index(run) -> dict[str, list[Path]]` already
carries that attribution and `check_manifest` already reports any id with more
than one entry. So the new code uses `_claim_index`, not `_claim_ids`, and
sidesteps the limitation rather than inheriting it. The spec's caution is
narrower in practice than it was written; note that in the Task 1 report.

---

## Task 1: The utilisation module, gate, and subcommand

**Files:**
- Create: `src/rubrica/utilisation.py`
- Create: `tests/unit/test_utilisation.py`
- Modify: `src/rubrica/refs.py` (add `check_claim_utilisation`; register in `check_all` at ~line 1392, after `check_world_model`)
- Modify: `src/rubrica/cli.py` (`SUBCOMMANDS` at line 87; branch beside `diff-runs` at ~line 324)
- Modify: `CLAUDE.md` ("Twelve deterministic subcommands" section; `Baseline:` line)

**Interfaces:**
- Consumes: `rubrica.paths.RunPaths`, `rubrica.paths.list_json`, `refs._claim_index(run) -> dict[str, list[Path]]`, `refs.Finding(path, checker, pointer, message)`.
- Produces: `utilisation.claim_utilisation(run: RunPaths) -> dict` and `refs.check_claim_utilisation(run: RunPaths) -> list[Finding]`. Task 2 does not use either; Task 3 runs the suite that covers them.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_utilisation.py`:

```python
"""Per-artifact claim utilisation, and the one case that is a finding.

The measurement this exists for: run-20260812-130056 extracted 287 claims and
its world model cited 157, so 130 were cited by nothing and neither gate said a
word. `refs.check_world_model` checks that a cited claim id resolves; nothing
checked the reverse.

Why the gate fires only on *zero* and not on a percentage: sampling the uncited
claims returned deployment facts -- LOG_LEVEL, PORT, "listening on 0.0.0.0:8000"
-- which rb-reconcile was right to drop. A cite-everything gate would emit ~130
findings to catch one real loss, and the cheapest way to satisfy it would be to
promote that trivia into the world model.
"""

from __future__ import annotations

import json

from rubrica.paths import RunPaths
from rubrica.refs import check_claim_utilisation
from rubrica.utilisation import claim_utilisation
from tests.toy import build_toy_run


def _blank_world_model_claim_refs(run: RunPaths, artifact_id: str) -> None:
    """Remove every reference to one artifact's claims from the world model.

    Simulates the exact defect: the claims file is present and well-formed, and
    nothing in the world model rests on it.
    """
    claims = json.loads((run.claims_dir / f"{artifact_id}.json").read_text(encoding="utf-8"))
    doomed = {c["id"] for c in claims["claims"]}
    world = json.loads(run.world_model.read_text(encoding="utf-8"))
    for group in ("capabilities", "entities", "actors", "goals"):
        for item in world.get(group, []):
            item["claims"] = [c for c in item.get("claims", []) if c not in doomed]
    run.world_model.write_text(json.dumps(world, indent=2) + "\n", encoding="utf-8")


def test_the_toy_run_utilises_every_input(tmp_path):
    run = build_toy_run(tmp_path / "runs")
    report = claim_utilisation(run)
    assert report["format"] == "rubrica-utilisation/1"
    assert report["artifacts"], "no artifacts reported for a run with claims"
    for entry in report["artifacts"]:
        assert entry["cited"] > 0, entry


def test_the_toy_run_has_no_utilisation_finding(tmp_path):
    run = build_toy_run(tmp_path / "runs")
    assert check_claim_utilisation(run) == []


def test_an_input_cited_by_nothing_is_one_finding_naming_it(tmp_path):
    """The red direction. Without it this predicate has never been watched fail,
    and a guard nobody has seen fail is not yet a guard."""
    run = build_toy_run(tmp_path / "runs")
    _blank_world_model_claim_refs(run, "api-json")
    findings = check_claim_utilisation(run)
    assert len(findings) == 1, findings
    assert "api-json" in findings[0].message


def test_it_does_not_fire_before_a_world_model_exists(tmp_path):
    """check-refs runs at every stage gate. A run stopped at extract has claims
    and no world model, and reporting all of them as uncited would make the
    extract gate unpassable."""
    run = build_toy_run(tmp_path / "runs", upto="extract")
    assert check_claim_utilisation(run) == []
    assert claim_utilisation(run)["artifacts"] == []


def test_partial_utilisation_is_reported_but_is_not_a_finding(tmp_path):
    """The whole design decision, pinned: 8% is data, 0% is a defect."""
    run = build_toy_run(tmp_path / "runs")
    claims = json.loads((run.claims_dir / "api-json.json").read_text(encoding="utf-8"))
    keep = claims["claims"][0]["id"]
    world = json.loads(run.world_model.read_text(encoding="utf-8"))
    doomed = {c["id"] for c in claims["claims"]} - {keep}
    for group in ("capabilities", "entities", "actors", "goals"):
        for item in world.get(group, []):
            item["claims"] = [c for c in item.get("claims", []) if c not in doomed]
    run.world_model.write_text(json.dumps(world, indent=2) + "\n", encoding="utf-8")

    entry = next(e for e in claim_utilisation(run)["artifacts"] if e["artifact_id"] == "api-json")
    assert entry["cited"] == 1
    assert entry["percent"] < 100
    assert check_claim_utilisation(run) == []
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd /home/bnayahu/work/kaegis/rubrica
uv run pytest tests/unit/test_utilisation.py -q 2>&1 | tail -5
```

Expected: collection error — `ModuleNotFoundError: No module named 'rubrica.utilisation'`.

- [ ] **Step 3: Write the module**

Create `src/rubrica/utilisation.py`:

```python
"""Per-artifact claim utilisation: how much of each input reached the world model.

One function in its own module, for `metrics.py`'s stated reason -- the gate in
`refs.py` and the `claim-utilisation` subcommand must never come to disagree
about what utilisation means, and duplicating the arithmetic is how they would.

Utilisation rate is a fact about the *input*, not about rb-reconcile's diligence.
Measured on run-20260812-130056: the ten trajectory slices ran 64-92% while
agent-server-py ran 8% (2 of 25), and the 23 dropped claims were A2A plumbing
rb-reconcile was right to discard. So this module reports and never judges;
exactly one case is a finding, and `refs.check_claim_utilisation` owns it.
"""

from __future__ import annotations

from rubrica.artifacts import read_json
from rubrica.paths import RunPaths, list_json

FORMAT = "rubrica-utilisation/1"


def claim_utilisation(run: RunPaths) -> dict:
    """Per-artifact cited/total counts, or an empty report before reconcile.

    An absent or unreadable world model yields no artifacts rather than every
    claim counted as uncited: `check-refs` runs at every stage gate, and a run
    stopped at extract legitimately has claims and no world model.
    """
    artifacts: list[dict] = []
    cited = _cited_claim_ids(run)
    if cited is None:
        return {"format": FORMAT, "artifacts": artifacts}

    for path in list_json(run.claims_dir):
        payload = _quietly(path)
        if not isinstance(payload, dict):
            continue
        ids = [claim["id"] for claim in payload.get("claims", [])]
        used = sum(1 for claim_id in ids if claim_id in cited)
        artifacts.append(
            {
                "artifact_id": payload.get("artifact_id", path.stem),
                "cited": used,
                "total": len(ids),
                # Integer, not a float: this number is read by a human at gate 1
                # and printed into a report, and a float would make two runs over
                # the same data diff on formatting alone.
                "percent": (100 * used // len(ids)) if ids else 0,
            }
        )
    return {"format": FORMAT, "artifacts": artifacts}


def _cited_claim_ids(run: RunPaths) -> set[str] | None:
    """Every claim id the world model rests on, or None if there is no world model."""
    world = _quietly(run.world_model)
    if not isinstance(world, dict):
        return None
    cited: set[str] = set()
    for group in ("capabilities", "entities", "actors", "goals"):
        for item in world.get(group, []):
            cited.update(item.get("claims", []) or [])
    return cited


def _quietly(path):
    """The document, or None. An unreadable artifact is `check_readable`'s
    finding to report, and duplicating it here would double-count one defect."""
    try:
        return read_json(path)
    except Exception:  # noqa: BLE001 -- see docstring: not this module's finding
        return None
```

Both helpers are confirmed present: `rubrica.artifacts.read_json` at
`artifacts.py:26` and `rubrica.paths.list_json` at `paths.py:67`. Write the
imports exactly as shown.

- [ ] **Step 4: Add the gate to `refs.py`**

Add after `check_world_model`, and register it in `check_all` immediately after
`findings.extend(check_world_model(run))`:

```python
def check_claim_utilisation(run: RunPaths) -> list[Finding]:
    """An input whose claims the world model cites *none* of.

    The mirror of check_world_model's claim check, which reports a world model
    citing an id that does not exist; this reports a claims file no world model
    cites. Same pair, opposite directions -- the shape the spec's parked table
    already has four rows of.

    Zero, not a percentage. Measured on run-20260812-130056: 130 of 287 claims
    were uncited and almost all of those drops were correct, so a threshold would
    have failed a run whose rb-reconcile was behaving. Zero is indefensible under
    every reading -- a human registered that input through intake, so either
    rb-extract produced nothing usable from it or rb-reconcile ignored a whole
    artifact.
    """
    out: list[Finding] = []
    for entry in claim_utilisation(run)["artifacts"]:
        if entry["total"] and entry["cited"] == 0:
            out.append(
                Finding(
                    run.world_model,
                    "refs",
                    "/",
                    f"no world-model element cites any claim from "
                    f"{entry['artifact_id']} ({entry['total']} claims)",
                )
            )
    return out
```

Add `from rubrica.utilisation import claim_utilisation` to `refs.py`'s imports.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
uv run pytest tests/unit/test_utilisation.py -q
```

Expected: 5 passed.

- [ ] **Step 6: Wire the subcommand**

In `cli.py`, add to `SUBCOMMANDS` (line 87) after the `decide` entry:

```python
    ("claim-utilisation", "per-artifact share of claims the world model cites"),
```

Add its parser argument beside the other `--run` subcommands, then add the
branch next to `diff-runs` (~line 324):

```python
        if args.command == "claim-utilisation":
            # A report, not a gate: always CLEAN on a readable run. The finding
            # half lives in check-refs, so this command never returns 1 and an
            # orchestrator reading its exit code cannot mistake data for a defect.
            print(json.dumps(claim_utilisation(_run_dir(args.run)), indent=2, sort_keys=True))
            return CLEAN
```

`_run_dir(args.run)` is the same helper `check-refs` uses at `cli.py:253`, so it
inherits that path's `UsageError` handling for an unreadable run — which is what
makes Step 7's middle case exit `2` rather than `1`. Add
`from rubrica.utilisation import claim_utilisation` to `cli.py`'s imports.

- [ ] **Step 7: Verify the exit-code contract in all three directions**

```bash
RUN=runs/run-20260812-130056
.venv/bin/rubrica claim-utilisation --run "$RUN" | head -12; echo "exit=$?"       # expect 0
.venv/bin/rubrica claim-utilisation --run /nonexistent; echo "exit=$?"            # expect 2
.venv/bin/rubrica check-refs --run "$RUN"; echo "exit=$?"                          # expect 0
```

The middle one matters most: a misconfigured run must be `2`, never `1`. If it
returns `1`, the branch is missing the `UsageError` handling its neighbours have.

Expect the first to show `agent-server-py` at 8% and the trajectory slices in the
60s–90s, reproducing the spec's §1 table against a real run.

- [ ] **Step 8: Update CLAUDE.md**

Two edits. In the "Twelve deterministic subcommands" section, change the heading
to thirteen, add `claim-utilisation` to the inline list, and extend the trailing
prose in its existing voice to say what it is for — a report surfaced at gate 1,
not a gate. Then re-measure and update the `Baseline:` line:

```bash
make test 2>&1 | tail -2
```

Put the observed numbers in, extending the parenthetical as the existing line
does. Do not invent a number you did not see.

- [ ] **Step 9: Verify and commit**

```bash
make check && uv run rubrica check-skills && echo "check-skills=0"
git add src/rubrica/utilisation.py src/rubrica/refs.py src/rubrica/cli.py \
        tests/unit/test_utilisation.py CLAUDE.md
git commit -S -s -m "feat: Report claim utilisation and gate the zero case

refs.check_world_model reports a world model citing a claim id that does not
exist; nothing reported a claims file no world model cites. Measured on
run-20260812-130056: 130 of 287 claims uncited, zero findings from either gate.

The gate fires only on zero utilisation of a whole registered input, because
sampling the uncited claims returned LOG_LEVEL, PORT and 'listening on
0.0.0.0:8000' -- drops rb-reconcile was right to make. A cite-everything gate
would emit ~130 findings to catch one real loss and would pay a stage to promote
deployment trivia into the world model.

Per-artifact rates go to claim-utilisation, a report that is always exit 0, so an
orchestrator cannot mistake data for a defect. Utilisation rate turns out to be a
fact about the input -- 8% for agent-server-py against 64-92% for the trajectory
slices -- which is why it belongs in a human's gate-1 decision rather than a gate.

Gate and report share one function, for metrics.py's stated reason.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 2: Both prompt edits, each guarded

**Files:**
- Modify: `src/rubrica/skills/rb-reconcile/SKILL.md` (Method, after step 3)
- Modify: `src/rubrica/skills/rb-extract/SKILL.md` (Method)
- Modify: `tests/unit/test_skills_reconcile.py` (8 tests today)
- Modify: `tests/unit/test_skills_extract.py` (7 tests today)

**Interfaces:**
- Consumes: `rubrica.skills.load`, `section_body`, `skills_dir` — all already imported by both test modules; read each file's existing imports rather than adding duplicates.
- Produces: nothing other tasks consume. Task 3 re-records the two skills this task edits, so its dispatches must run *after* this task commits.

- [ ] **Step 1: Write both failing tests**

Append to `tests/unit/test_skills_reconcile.py`:

```python
def test_it_requires_an_entity_for_a_capabilitys_described_response_shape():
    """Task 6 of the trajectory run dropped a claim that named all six fields of
    cancel_reservation's success payload -- confidence high, a JSON Pointer into
    an observed span, the refund_policy string quoted -- and produced four
    entities, none of them a cancellation receipt. Nothing in the prompt was
    violated: Method step 2 said "group claims", an unquantified verb.

    Scoped to Method and asserting co-occurrence, because the words "entity" and
    "capability" appear throughout this file and a presence check anywhere in
    `body` would pass with this rule deleted.
    """
    method = section_body(load(SKILL), "3. Method").lower()
    assert "for every capability you declare" in method
    assert "becomes an entity" in method
```

Append to `tests/unit/test_skills_extract.py`:

```python
def test_it_requires_every_prose_heading_to_be_cited_or_explained():
    """rb-extract already said "every statement it makes about the target" and
    still skipped an entire section: the claims from agent-notes-md carry
    locators L51...L55 then jump to L84, and L57-L80 is the whole Usage Examples
    section -- five canonical user asks plus res_12345 -- while the Apache licence
    at L187 got a claim.

    Universal quantification works when the set is small, closed and already
    written down. "Every statement in a document" is unbounded; "every `##`
    heading" is not.
    """
    method = section_body(load(SKILL), "3. Method").lower()
    assert "every `##` heading" in method
    assert "carries nothing about the target" in method
```

- [ ] **Step 2: Run both to verify they fail**

```bash
uv run pytest tests/unit/test_skills_reconcile.py tests/unit/test_skills_extract.py -q 2>&1 | tail -6
```

Expected: 2 failed on the new assertions. If either *passes*, stop and report —
the phrase already occurs somewhere in the Method section and the assertion is
not testing what it claims.

- [ ] **Step 3: Add the reconcile sentence**

In `src/rubrica/skills/rb-reconcile/SKILL.md`, immediately after Method step 3's
block, insert a new numbered step and renumber the steps that follow:

```
4. **For every capability you declare, if any claim describes the shape of
   what that capability returns, that shape becomes an entity.** A capability
   whose success payload a claim spells out field by field, with no entity
   modelling it, is a response nothing downstream can assert against -- and no
   gate reports it, because `refs.check_world_model` only checks that the
   claims you *did* cite resolve.

   Quantified over the capabilities you have just declared, deliberately, and
   not over claims. Measured: step 3's "for every capability" produced every
   outcome-class cell a real run needed, while an unquantified instruction to
   "group claims" dropped 45% of them. A stage can check itself against five
   capabilities it just wrote down; it cannot check itself against every
   statement in a document.
```

Renumbering matters: `check-skills` validates section *names*, not step numbers,
but a duplicate step number would mislead a reader. Verify with:

```bash
grep -n "^[0-9]\+\. \*\*" src/rubrica/skills/rb-reconcile/SKILL.md
```

- [ ] **Step 4: Add the extract sentence**

In `src/rubrica/skills/rb-extract/SKILL.md`, add to the Method section:

```
**Cover the whole artifact.** For a prose artifact, every `##` heading must be
cited by at least one claim's `evidence.locator`, or your report must say why
that section carries nothing about the target. Headings are a small, closed set
the artifact itself writes down, which is what makes this checkable where "every
statement" is not: a real dispatch that had been told "every statement it makes
about the target" filed a claim for a licence line and skipped a whole section of
usage examples -- the five requests a user actually makes of this target.
```

- [ ] **Step 5: Run both to verify they pass**

```bash
uv run pytest tests/unit/test_skills_reconcile.py tests/unit/test_skills_extract.py -q
uv run rubrica check-skills; echo "check-skills=$?"
```

Expected: all pass, `check-skills=0`.

- [ ] **Step 6: Measure both predicates in the other direction**

This is the step that turns each assertion into a guard. For **each** of the two
skills, in a `/tmp` copy under `RUBRICA_SKILLS_DIR`:

```bash
rm -rf /tmp/skills-probe && cp -r src/rubrica/skills /tmp/skills-probe
# delete the new paragraph from the /tmp copy, then:
RUBRICA_SKILLS_DIR=/tmp/skills-probe uv run pytest \
  tests/unit/test_skills_reconcile.py tests/unit/test_skills_extract.py -q 2>&1 | tail -4
```

Expected: the two new tests fail. Then **reword** the paragraph in the `/tmp`
copy meaning-preservingly — change the surrounding sentences while keeping the
two asserted phrases — and confirm the tests go green again. Both directions,
because a phrase pin has broken on an innocuous reformat in this repository
before, and a predicate nobody has watched fail is not yet a guard.

Report both results with real output. If the deletion leaves either test green,
**stop and report** — the assertion is matching something else.

- [ ] **Step 7: Verify and commit**

```bash
make test 2>&1 | tail -2   # expect +2 over Task 1's count
make check && uv run rubrica check-skills
git add src/rubrica/skills/rb-reconcile/SKILL.md src/rubrica/skills/rb-extract/SKILL.md \
        tests/unit/test_skills_reconcile.py tests/unit/test_skills_extract.py
git commit -S -s -m "fix: Quantify two instructions that silently dropped evidence

rb-reconcile read a claim naming all six fields of a capability's success
payload -- high confidence, JSON Pointer into an observed span -- and modelled no
entity for it. Nothing in the prompt was violated: Method said 'group claims'.
The fix is quantified over the capabilities the stage just declared, a closed
set it can check itself against, because that phrasing produced every
outcome-class cell a real run needed while the unquantified one dropped 45%.

rb-extract already said 'every statement it makes about the target' and skipped
a whole section anyway -- locators L51...L55 then L84, with L57-L80 the usage
examples -- while filing a claim for a licence line. So quantified prose is not
sufficient on its own; the set has to be small, closed and written down. Headings
are.

Both predicates measured in both directions: red with the prose deleted from a
RUBRICA_SKILLS_DIR copy, green again after a meaning-preserving reword.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 3: Re-record, and retire the guard test

**Files:**
- Modify: `src/rubrica/skills/rb-extract/exercise.md`
- Modify: `src/rubrica/skills/rb-reconcile/exercise.md`
- Modify: `tests/fixtures/toy-gap/recorded/01-world-model.json`
- Modify: `tests/fixtures/toy-contradiction/recorded/01-world-model.json`
- Modify: `tests/unit/test_refusal_fixtures.py` (delete the test at line 259)

**Interfaces:**
- Consumes: the two edited skills from Task 2. **This task must run after Task 2 commits**, or it re-records the old prompts.
- Produces: nothing consumed by later tasks.

**This task spends live model dispatches and is the only task that does.**

- [ ] **Step 1: Read the ruling before touching anything**

Read spec §6. It records a human ruling that resolves a live contradiction:
CLAUDE.md obliges re-recording `recorded/01-world-model.json` when a skill
changes, and `test_the_recorded_world_model_keeps_its_pre_rubrica_spelling`
forbids exactly that for these two files. **CLAUDE.md governs; the test is
retired as the losing side of a documented contradiction, not as an oversight.**

Do not skip this step. Without the ruling, deleting that test looks like
defeating a guard to make a change pass, which is what it would be otherwise.

- [ ] **Step 2: Re-record the two exercise.md files**

For each of `extract` and `reconcile`, build a toy run to the checkpoint *before*
the stage and dispatch it:

```bash
cat > /tmp/toy-run-to.py <<'PY'
import sys
from pathlib import Path
from tests.toy import build_toy_run
runs_dir = Path(sys.argv[1])
upto = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "None" else None
print(build_toy_run(runs_dir, upto=upto).root)
PY

RUN=$(PYTHONPATH=. uv run python /tmp/toy-run-to.py /tmp/rubrica-lab/runs intake)
RUBRICA_LAB=/tmp/rubrica-lab/rr-extract ./scripts/dispatch-stage.sh extract "$RUN" api-json
./scripts/audit-reads.sh /tmp/rubrica-lab/rr-extract/transcripts/extract-api-json.jsonl

RUN=$(PYTHONPATH=. uv run python /tmp/toy-run-to.py /tmp/rubrica-lab/runs extract)
RUBRICA_LAB=/tmp/rubrica-lab/rr-reconcile ./scripts/dispatch-stage.sh reconcile "$RUN"
./scripts/audit-reads.sh /tmp/rubrica-lab/rr-reconcile/transcripts/reconcile.jsonl
```

Then update each `exercise.md` to record **what happened**, including the gate
results and the read audit. Two rules from this repository's conventions: an
exercise record states what happened, and a reasoned number presented as an
observed one corrupts the evidence — one such misattribution shipped here and had
to be corrected. Keep the model and effort the dispatch actually used.

- [ ] **Step 3: Re-record the two refusal fixtures**

Each is `rb-reconcile` output over a negative fixture. Build a run from the
fixture, dispatch `reconcile`, then copy the produced world model over the
recording:

```bash
grep -n "CONTRADICTION_DIR\|GAP_DIR\|def build_toy_run" tests/toy.py | head
```

Read `build_toy_run`'s signature for how it takes a fixture directory — the
existing recordings were produced the same way, and `tests/toy.py` is documented
as the module to check before adding a helper, because nearly every request for a
new checkpoint turned out to be one that already existed. Use the existing path;
do not add a helper.

- [ ] **Step 4: Run the four live assertions — the stop condition**

```bash
RUBRICA_LIVE=1 uv run pytest -m live -q 2>&1 | tail -20
```

Four assertions in `tests/unit/test_refusals_live.py` must survive: the
contradiction still resolving `unresolved`; the gap still blocking `propose` with
action-named subjects; a malformed-calls gap alone not satisfying that test; and
the gap fixture acquiring no invented outcome classes, with
`cells == denominator.capability_cells`.

**If any of the four fails, STOP and report. Do not adjust the assertion, do not
re-record again, do not tune the fixture.** A failure there is ambiguous between
"Task 2's reconcile change broke refusal detection" and "model variance" — and
removing that ambiguity is the only reason a recording exists. At that point the
re-record has produced a finding, not a fixture, and it needs a human ruling.

- [ ] **Step 5: Retire the spelling guard**

Delete `test_the_recorded_world_model_keeps_its_pre_rubrica_spelling` from
`tests/unit/test_refusal_fixtures.py` (line 259, including its parametrize
decorator and its full docstring). Delete only that test; the rest of the module
guards properties unaffected by this change.

- [ ] **Step 6: Verify**

```bash
make test 2>&1 | tail -2      # expect -1 test from Step 5's deletion
make check && uv run rubrica check-skills
git diff --stat
```

Confirm the two recordings changed and that the diff is *reviewable* — that was
the stated reason for preferring a re-record to a silent rewrite, so a diff that
is unreadably large is itself worth reporting.

- [ ] **Step 7: Update CLAUDE.md's baseline and commit**

```bash
make test 2>&1 | tail -2
```

Update the `Baseline:` line with the observed numbers, then:

```bash
git add src/rubrica/skills/rb-extract/exercise.md src/rubrica/skills/rb-reconcile/exercise.md \
        tests/fixtures/toy-gap/recorded/01-world-model.json \
        tests/fixtures/toy-contradiction/recorded/01-world-model.json \
        tests/unit/test_refusal_fixtures.py CLAUDE.md
git commit -S -s -m "test: Re-record after the prompt changes, per a documented ruling

Changing rb-extract and rb-reconcile obliges re-recording under this repo's
convention. Both refusal recordings are rb-reconcile output, and a guard test
forbade re-recording them precisely to protect their pre-Rubrica tg-propose
spelling as dated evidence.

That is a live contradiction between CLAUDE.md and a test, and the design spec
records the human ruling that settles it: CLAUDE.md governs, and the guard is
retired as the losing side rather than as an oversight. Both costs were stated
before the ruling -- the tg-propose spelling was the only in-repo marker that
these recordings predate the rename, and four live assertions had to survive the
re-record with a failure being ambiguous rather than diagnostic.

The four live assertions pass against the new recordings.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage.** §1's measurement → Task 1's test docstrings, which carry the
numbers rather than restating them as prose. §2's zero-utilisation check → Task 1
Steps 3–4, with the `_claim_index` refinement recorded in the File Structure
notes. §3's reconcile sentence → Task 2 Steps 1, 3. §4's extract sentence → Task
2 Steps 1, 4. §5's subcommand → Task 1 Steps 6–7, with the `claim-coverage` →
`claim-utilisation` rename flagged in Global Constraints. §6's re-records and the
ruling → Task 3, whose Step 1 requires reading the ruling and whose Step 4 is the
stop condition. §7's both-directions protocol → Task 1 Step 1
(`test_an_input_cited_by_nothing...` is the red direction) and Task 2 Step 6.
§8's non-scope items appear in no task. No gap.

**Placeholders.** None. The two lookups this plan originally deferred are now
resolved inline: `read_json` at `artifacts.py:26`, `list_json` at `paths.py:67`,
and `_run_dir` as the `RunPaths` helper `check-refs` uses at `cli.py:253`. Task 3
Step 3 still points at `tests/toy.py` rather than quoting a signature, and that
is deliberate — that module is documented as the thing to check before adding a
helper, because nearly every request for a new checkpoint during the original
build turned out to be one that already existed.

**Type consistency.** `claim_utilisation(run: RunPaths) -> dict` is defined in
Task 1 Step 3 and called in Step 4 and Step 6 under that exact name.
`check_claim_utilisation(run: RunPaths) -> list[Finding]` is defined in Step 4 and
imported in Step 1's test under that name. `FORMAT = "rubrica-utilisation/1"` is
asserted in Step 1 and defined in Step 3. The report's keys — `artifact_id`,
`cited`, `total`, `percent` — are asserted in Step 1 and produced in Step 3, and
`format`/`artifacts` match between them. `SKILL` and `section_body` in Task 2 are
already defined in both existing test modules.
