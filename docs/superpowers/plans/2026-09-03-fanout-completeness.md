# Fan-out Completeness Checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a fan-out member that writes no slice a layer-2 finding against its own
directory, for the two fan-outs that lack the check — `extract` and `instantiate`.

**Architecture:** Two clauses, each added to the `refs.py` checker that already owns the
*other* direction of its relation, behind an `is_dir()` guard. This mirrors
`check_contradiction_parts` and `_scenario_round_findings`, which both keep the
declared-minus-on-disk and on-disk-minus-declared directions in one checker. No new
checker, no new module, no change to layer 1.

**Tech Stack:** Python 3.13, `uv`, pytest, ruff. No new dependencies.

**Spec:** GitHub issue #19 plus the design approved in conversation, restated in full in
"Background" below. There is no separate spec file — this was a bounded change.

## Background (the whole argument, for a reader with no context)

A fan-out member that refuses, dies, or is killed writes no slice while its siblings write
theirs. Measured on `main` at `ce02bc5`, in that state **both check layers exit 0 with zero
findings** and the run proceeds to build a world model from an incomplete corpus.

Two fan-outs have this hole. Four do not:

| Fan-out | Declared population | Completeness check today |
|---|---|---|
| `triage-rule` -> `00-dispositions/` | `00-slices.json` | yes — `check_disposition_parts` |
| `extract` -> `01-claims/` | `manifest.inputs` | **no — Task 1 adds it** |
| `reconcile-contradict` -> `01-contradictions/` | `01-subjects.json` | yes — `check_contradiction_parts` |
| `propose` -> `02-scenarios/round-N/` | `02-batches/round-N.json` | yes — `_scenario_round_findings` |
| `instantiate` -> `04-instances/` | `02-scenarios.json` (`active`) | **no — Task 2 adds it** |
| `challenge` -> `05-verdicts/` | `04-instances/` on disk | yes — `check_verdicts` |

Left to run on, the extract hole surfaces 15 `check-refs` findings blaming the reconcile
partials, whose only fault is citing a claim nobody extracted. `CLAUDE.md` records that
class — *"a `1` must name the right artifact"* — as having cost this project a fix round.

**Why `rb-extract` has no exempt case.** Its refusal condition for an unreadable or empty
input is *"write a claims file with an empty `claims` array and report that plainly."* So
every registered input must have a claims file, even a vacuous one. The finding's wording
must say so, or a reader repairs it by deleting the input instead of re-dispatching.

**Why layer 2 and not layer 1.** The issue points at `validate._artifact_paths` enumerating
the claims files that exist rather than the ones that should. True, but completeness needs
the manifest, and layer 1 is one-schema-per-artifact by architecture (`CLAUDE.md`, "Two
check layers"). Do not touch `validate.py`.

**Why code and not the orchestrator.** `rb-orchestrate` knows the member count and could
compare it. Four sibling fan-outs enforce this in code; putting the guarantee in a prompt is
the trade this project decides the other way.

**Why the reports are untouched.** `utilisation.claim_utilisation` iterates
`list_json(run.claims_dir)`, so a missing input vanishes from gate 1's table rather than
showing 0/0. That is real, but `check-refs` now exits 1 before gate 1 is reached, and
`CLAUDE.md` puts this arithmetic's finding in `check-refs` and nowhere else. Do not touch
`utilisation.py`, `brief.py`, or `summary.py`.

## Global Constraints

- **Every commit signed and DCO'd: `git commit -S -s`.** Both flags. If signing fails, STOP
  and report it; never fall back to unsigned, never work around it.
- Attribution trailer is exactly `Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>`.
  Never `Co-Authored-By` or `Made-with`.
- ruff: `line-length = 100`, `select = ["E","F","I","UP","B","SIM"]`. Run `make check` after
  editing `CLAUDE.md` or `README.md` — they are **not** in `extend-exclude`; all of `docs/` is.
- Comment density in this repo is high and deliberate: comments explain *why*, usually citing
  a measurement. Match it. Do not strip existing comments.
- The exit-code contract is load-bearing: `0` clean, `1` findings one per line on stdout,
  `2` usage error. **A stage defect must never surface as `2`**, and a `1` must never have
  empty stdout. Both new clauses produce ordinary `Finding`s, i.e. exit 1.
- Three gates must be green before any task is considered done: `make test`, `make check`,
  and `uv run rubrica check-skills` exiting 0.
- **Never write a test count into any file.** `CLAUDE.md` forbids it.
- Docstrings in `refs.py` carry the *ruling*, not just a description. When a ruling is
  overturned, rewrite the docstring rather than appending to it.

---

### Task 1: extract — a registered input with no claims file

**Files:**
- Modify: `src/rubrica/refs.py` — `check_manifest`, docstring at 1222-1231 and a new clause
  before the `_claim_index` loop at ~1264
- Test: `tests/unit/test_refs_manifest.py`

**Interfaces:**
- Consumes: `RunPaths.claims_dir`, `RunPaths.claims(artifact_id)`, `refs.Finding`,
  `artifacts.list_json` — all already imported in `refs.py`.
- Produces: nothing new. No new public name; `check_manifest`'s signature is unchanged, so
  `check_all` needs no edit.

**Context an implementer needs.** `check_manifest` already builds
`registered: dict[str, int]` mapping `artifact_id` -> its index in `manifest["inputs"]`. It
already reports the *reverse* direction — a claims file naming an unregistered input. Its
docstring currently states the ruling this task overturns:

```
    Checked in one direction only: every claims file must name a registered
    input, never the reverse. A registered input with no claims file yet is the
    normal state during the extract fan-out, and reporting it there would fire
    on a run in which nothing is wrong.
```

`manifest-0.1.json` pins `artifact_id` to `\A[A-Za-z0-9][A-Za-z0-9._-]*\Z`, so an unsafe
artifact id is a layer-1 failure and this clause needs no `is_safe_segment` handling — unlike
`check_contradiction_parts`, which does. Do not add any.

- [ ] **Step 1: Write the two failing tests**

In `tests/unit/test_refs_manifest.py`. The existing `_run(tmp_path, manifest=None, claims=None)`
helper writes the manifest and a claims file per key of `claims`; passing no `claims` leaves
`01-claims/` **absent**, which is why the guard test below passes for a different reason than
the finding test.

```python
def test_a_registered_input_with_no_claims_file_is_reported_once_the_directory_exists(tmp_path):
    """A sibling landed, so the fan-out ran; this input's member wrote nothing."""
    manifest = minimal_manifest()
    manifest["inputs"].append(
        {
            "artifact_id": "aap2-notes",
            "source_path": "harness-skills/parsec-aap2/notes.md",
            "stored_as": "notes.md",
            "sha256": "c" * 64,
            "kind": "design_doc",
            "bytes": 12,
        }
    )
    run = _run(tmp_path, manifest=manifest, claims={"aap2-api": minimal_claims()})
    findings = check_manifest(run)
    assert len(findings) == 1
    assert findings[0].artifact == run.claims_dir
    assert "aap2-notes" in findings[0].message
    assert "has no claims file on disk" in findings[0].message
```

Then **replace** the existing `test_a_registered_input_with_no_claims_file_is_not_a_finding`
(currently at line 37, docstring `"""The normal state during the extract fan-out; firing here
is a phantom."""`) with the guard test it actually is. Its old name and docstring assert the
ruling this task overturns, so leaving them would leave the repo stating both rulings at once:

```python
def test_a_registered_input_is_not_reported_before_the_claims_directory_exists(tmp_path):
    """The guard: with no 01-claims/ at all the run has not reached the extract fan-out,
    and reporting every input there would spend the orchestrator's one repair attempt on a
    phantom. Once the directory exists the tolerance ends -- see the test above."""
    run = _run(tmp_path)
    assert not run.claims_dir.exists()
    assert check_manifest(run) == []
```

- [ ] **Step 2: Run the tests and verify the first fails and the second passes**

Run: `uv run pytest tests/unit/test_refs_manifest.py -v`
Expected: `..._is_reported_once_the_directory_exists` FAILS with `assert 0 == 1`;
`..._before_the_claims_directory_exists` PASSES already (the guard is the directory's absence).

- [ ] **Step 3: Rewrite the docstring ruling**

In `src/rubrica/refs.py`, replace the four-line paragraph quoted above (inside
`check_manifest`'s docstring, keeping the summary line `"""The manifest against 01-claims,
and each claim's evidence against the manifest.` intact) with:

```
    Both directions: every claims file must name a registered input, and every
    registered input must have a claims file. The second was one-directional
    until issue #19, on the argument that a registered input with no claims file
    is the normal state *during* the extract fan-out -- true, but not a state
    check-refs observes. There is no stage-scoped check-refs; check_all runs
    every checker the run has inputs for, and the orchestrator dispatches it
    after a fan-out completes. That is the argument check_disposition_parts,
    check_contradiction_parts and _scenario_round_findings all make, and until
    #19 the extract fan-out was the one of the four making it differently: a
    member that refused, died or was killed passed both layers at zero findings,
    then surfaced stages later as findings against the reconcile partials that
    had cited its absent claims.
```

- [ ] **Step 4: Write the clause**

Insert immediately **before** the `for claim_id, paths in sorted(_claim_index(run).items()):`
loop (~line 1264), after the `registered` loop completes:

```python
    # The guard is `is_dir()`, not a count, exactly as the three sibling fan-out
    # checkers guard theirs: with no 01-claims/ at all the run has not reached
    # extract, and reporting every input there would spend the orchestrator's
    # single repair attempt on a phantom. Once the directory exists the
    # mid-fan-out window is deliberately *not* tolerated -- check-refs is
    # dispatched after every member has finished, so a missing file is real.
    if run.claims_dir.is_dir():
        extracted = {path.stem for path in list_json(run.claims_dir)}
        for artifact_id in sorted(set(registered) - extracted):
            out.append(
                Finding(
                    run.claims_dir,
                    "refs",
                    "",
                    f"input {artifact_id} has no claims file on disk; every registered input "
                    "needs one, even one recording that nothing could be extracted from it",
                )
            )
```

The second clause of the message is load-bearing, not padding: `rb-extract`'s refusal
condition for an unreadable or empty input is to write a claims file with an empty `claims`
array, so a reader must repair this by re-dispatching the member, never by deleting the input.

- [ ] **Step 5: Run the tests and verify both pass**

Run: `uv run pytest tests/unit/test_refs_manifest.py -v`
Expected: all PASS.

- [ ] **Step 6: Fix the one collateral assertion**

`test_a_claims_file_naming_an_unregistered_artifact_is_reported` builds a run with a ghost
claims file and **no** claims file for the registered `aap2-api` — two real defects, so it
now gets 2 findings and asserts 1. Isolate the property it names by completing its fixture
rather than by loosening the count:

```python
def test_a_claims_file_naming_an_unregistered_artifact_is_reported(tmp_path):
    run = _run(
        tmp_path,
        claims={"aap2-api": minimal_claims(), "ghost": minimal_claims(artifact_id="ghost")},
    )
    findings = check_manifest(run)
    assert len(findings) == 1
    assert "not registered in the manifest" in findings[0].message
```

- [ ] **Step 7: Verify the whole suite and both directions of the new predicate**

Run: `uv run pytest -q` — expect all pass, no failures.
Then measure the guard in both directions by hand, which `CLAUDE.md` requires of any new
predicate before it counts as a guard. Run each line separately:

```
rm -rf /tmp/t1
uv run python -c "import sys; sys.path.insert(0, 'tests'); from pathlib import Path; import toy; print(toy.build_toy_run(Path('/tmp/t1/runs'), upto='extract').root)"
uv run rubrica check-refs --run /tmp/t1/runs/run-*        # expect 0
mv /tmp/t1/runs/run-*/01-claims/notes-md.json /tmp/away.json
uv run rubrica check-refs --run /tmp/t1/runs/run-*        # expect 1, one finding naming 01-claims and notes-md
mv /tmp/away.json /tmp/t1/runs/run-*/01-claims/notes-md.json
uv run rubrica check-refs --run /tmp/t1/runs/run-*        # expect 0 again
```

- [ ] **Step 8: Commit**

Stage exactly `src/rubrica/refs.py` and `tests/unit/test_refs_manifest.py`, then commit with
`git commit -S -s` (both flags mandatory) and this message:

```
fix: Report a registered input whose extract member wrote no claims file

An rb-extract member that refuses, dies or is killed left both check layers at
zero findings, and the loss surfaced stages later as findings against the
reconcile partials that had cited its absent claims. check_manifest now checks
the manifest-to-claims relation in both directions, guarded on 01-claims/
existing exactly as the three sibling fan-out checkers guard theirs.

Refs #19

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
```

---

### Task 2: instantiate — an active scenario with no instance directory

**Files:**
- Modify: `src/rubrica/refs.py` — `check_instances`, docstring at 3728 and a new clause after
  the `unsafe_instance_dir_names` loop (~3752)
- Test: `tests/unit/test_refs_instance.py`

**Interfaces:**
- Consumes: `RunPaths.instances_dir`, `RunPaths.scenario_ids_with_instances()`, `refs.Finding`
  — all already available in `refs.py`.
- Produces: nothing new. `check_instances`'s signature is unchanged, so `check_all` needs no edit.

**Context an implementer needs.** This is the same shape as Task 1 and was found by
measurement while verifying issue #19's scope, not reported in it. On a toy run built to
`instantiate`, removing `04-instances/scn-blocked/` (a scenario whose status is `active`)
leaves `validate --stage instantiate` at 0 and `check-refs` at 0. It compounds:
`check_verdicts` derives its population from `run.scenario_ids_with_instances()` and
`check_suite` from `run.scenario_ids_with_tasks()`, both on-disk, so a dropped active
scenario propagates unremarked to a suite that is one test short.

`check_instances` already reports the reverse direction, inside its
`for sid in run.scenario_ids_with_instances():` loop — an instance directory whose scenario
has a status outside `JUDGED_STATUSES` (`{"active", "rejected"}`). Do **not** duplicate it.

The declared population here is `status == "active"` only, not `JUDGED_STATUSES`. `rejected`
is excluded deliberately: challenge marks a scenario `rejected` *after* it was instantiated,
so a rejected scenario legitimately has an instance directory, and requiring one would fire
on a run whose reject path worked. `duplicate` and `proposed` are excluded because
`rb-instantiate` is dispatched one member per **active** scenario.

`check_instances` opens with `world = _load(run.world_model)` and returns `[]` when the world
model is absent. Keep that. It has **no** `instances_dir.is_dir()` guard today, because every
loop it runs is over `scenario_ids_with_instances()`, which is empty when the directory is
absent. The new clause is the first one that does not iterate the directory, so it needs the
guard explicitly — without it, a run sitting at stage 03 with scenarios sealed and no
instances yet would report every active scenario as missing.

The clause reads `by_id`, which `check_instances` already builds a few lines above as
`{s["id"]: s for s in scenarios_doc.get("scenarios", [])}`. Do not re-read the scenarios file.

- [ ] **Step 1: Write the two failing tests**

In `tests/unit/test_refs_instance.py`. The existing `_run` helper writes claims, world model,
`minimal_scenarios()` (one scenario, `scn-001`, status `active`) and a seed and expected under
`run.seed(sid)`, which creates `04-instances/scn-001/`.

```python
def test_an_active_scenario_with_no_instance_directory_is_reported(tmp_path):
    """The instantiate fan-out's missing member: a sibling landed, this one wrote nothing."""
    scenarios = minimal_scenarios()
    second = dict(scenarios["scenarios"][0])
    second["id"] = "scn-002"
    scenarios["scenarios"].append(second)
    run = _run(tmp_path)
    write_json(run.scenarios, scenarios)
    findings = check_instances(run)
    assert len(findings) == 1
    assert findings[0].artifact == run.instances_dir
    assert "scn-002" in findings[0].message
    assert "has no instance directory on disk" in findings[0].message


def test_an_active_scenario_is_not_reported_before_the_instances_directory_exists(tmp_path):
    """The guard: with no 04-instances/ at all the run has not reached instantiate, and
    reporting every active scenario there would spend the orchestrator's one repair attempt
    on a phantom."""
    run = RunPaths(tmp_path)
    write_json(run.claims("aap2-api"), minimal_claims())
    write_json(run.world_model, minimal_world_model())
    write_json(run.scenarios, minimal_scenarios())
    assert not run.instances_dir.exists()
    assert check_instances(run) == []
```

- [ ] **Step 2: Run the tests and verify the first fails**

Run: `uv run pytest tests/unit/test_refs_instance.py -v`
Expected: `..._with_no_instance_directory_is_reported` FAILS with `assert 0 == 1`;
`..._before_the_instances_directory_exists` PASSES already.

- [ ] **Step 3: Extend the docstring**

`check_instances`'s docstring is the one-liner
`"""Seed conformance, machine invariants, and the reachability gate."""`. Replace it with:

```
    """Completeness, seed conformance, machine invariants, and the reachability gate.

    Completeness is checked in both directions. The loop below reports an
    instance directory whose scenario was never judged; the clause above it
    reports an `active` scenario with no instance directory, which until issue
    #19 nothing reported at all -- and the silence compounded, because
    check_verdicts and check_suite both derive their populations from what is on
    disk, so a dropped active scenario reached an emitted suite one test short
    with no finding anywhere.

    `rejected` is excluded from the population that must have a directory, and
    the asymmetry is deliberate: challenge marks a scenario `rejected` *after* it
    was instantiated, so a rejected scenario legitimately has a directory, and
    requiring one would fire on a run whose reject path worked exactly as
    prescribed.
    """
```

- [ ] **Step 4: Write the clause**

Insert immediately **after** the `for name in run.unsafe_instance_dir_names():` loop and
**before** `for sid in run.scenario_ids_with_instances():`:

```python
    # The guard is `is_dir()`, not a count, for the reason the three sibling
    # fan-out checkers give: with no 04-instances/ at all the run has not
    # reached instantiate, and reporting every active scenario there would
    # spend the orchestrator's single repair attempt on a phantom. Every other
    # loop in this checker iterates the directory and is empty-safe without a
    # guard, which is why this is the first clause to need one.
    if run.instances_dir.is_dir():
        instantiated = set(run.scenario_ids_with_instances())
        for sid, scenario in sorted(by_id.items()):
            if scenario.get("status") == "active" and sid not in instantiated:
                out.append(
                    Finding(
                        run.instances_dir,
                        "refs",
                        "",
                        f"active scenario {sid} has no instance directory on disk; every "
                        "scenario score left active is one instantiate was dispatched for",
                    )
                )
```

- [ ] **Step 5: Run the tests and verify both pass**

Run: `uv run pytest tests/unit/test_refs_instance.py -v`
Expected: all PASS.

- [ ] **Step 6: Run the whole suite and fix any collateral assertion**

Run: `uv run pytest -q`

Any failure here is a fixture that builds a run with active scenarios and a partially
populated `04-instances/`. Fix it the way Task 1 Step 6 does — complete the fixture, or, if
the test's subject genuinely is a partial run, assert on the message rather than loosening a
count. Do **not** weaken the new clause to accommodate a fixture. If a failing test's
docstring asserts that a missing instance directory is tolerated, that docstring is the
ruling being overturned: rewrite it, and say so in the commit body.

- [ ] **Step 7: Verify both directions by hand**

Run each line separately:

```
rm -rf /tmp/t2
uv run python -c "import sys; sys.path.insert(0, 'tests'); from pathlib import Path; import toy; print(toy.build_toy_run(Path('/tmp/t2/runs'), upto='instantiate').root)"
uv run rubrica check-refs --run /tmp/t2/runs/run-*        # expect 0
mv /tmp/t2/runs/run-*/04-instances/scn-blocked /tmp/inst-away
uv run rubrica check-refs --run /tmp/t2/runs/run-*        # expect 1, naming 04-instances and scn-blocked
mv /tmp/inst-away /tmp/t2/runs/run-*/04-instances/scn-blocked
uv run rubrica check-refs --run /tmp/t2/runs/run-*        # expect 0 again
```

- [ ] **Step 8: Commit**

Stage exactly `src/rubrica/refs.py` and `tests/unit/test_refs_instance.py`, then commit with
`git commit -S -s` (both flags mandatory) and this message:

```
fix: Report an active scenario whose instantiate member wrote no directory

The same shape as the extract hole, found by measurement while verifying #19's
scope: removing one active scenario's instance directory left both check layers
at zero findings. It compounded, because check_verdicts and check_suite both
derive their populations from what is on disk, so the loss reached an emitted
suite one test short with no finding anywhere. rejected stays out of the
population that must have a directory, since challenge marks a scenario rejected
after it was instantiated.

Refs #19

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
```

---

### Task 3: extract's gate gains check-refs

**Files:**
- Modify: `scripts/render-pipeline-diagram.py` — the `01a` / `extract` row's `gates=` at ~139
- Modify: `docs/concepts/pipeline-diagram.html` — **by re-render only, never by hand**
- Modify: `CLAUDE.md` — the `01a` row of the stage table
- Modify: `docs/concepts/pipeline.md` — extract's gate
- Modify: `src/rubrica/skills/rb-orchestrate/SKILL.md` — step B2 (~498-500) and the summary
  table line (~226)

**Interfaces:**
- Consumes: nothing from Tasks 1-2 in code. Depends on Task 1 only for the *reason* the gate
  is worth running: before Task 1, `check-refs` after extract had no extract-specific
  clause to report.
- Produces: nothing consumed by later tasks.

**Why this task exists.** Without it the new Task 1 finding first surfaces at
`reconcile-subjects`' gate, which is the next stage whose gate runs `check-refs`. The finding
still names `01-claims/` correctly, so blame is right either way — but by then
`reconcile-subjects` has already built a subjects partial from an incomplete corpus, so the
repair costs two stages instead of one.

**Verified before planning:** `check-refs` is already clean at 0 findings on an intact toy run
stopped at `extract`, so this gate change does not turn a green run amber.

- [ ] **Step 1: Edit the diagram's content model**

In `scripts/render-pipeline-diagram.py`, the `01a` row currently reads `gates=["validate"]`.
Change it to `gates=["validate", "check-refs"]`. Change nothing else in that file — every
coordinate is computed from `ROWS`.

- [ ] **Step 2: Verify the committed page is now stale, then re-render**

```
uv run python scripts/render-pipeline-diagram.py --check    # expect non-zero
uv run python scripts/render-pipeline-diagram.py
uv run python scripts/render-pipeline-diagram.py --check    # expect 0
```

Never hand-edit `docs/concepts/pipeline-diagram.html`. `tests/unit/test_docs_accuracy.py`
re-renders and compares byte-for-byte.

- [ ] **Step 3: Update the stage table in `CLAUDE.md`**

Find the `01a` / extract row, whose last cell is `validate`, and change it to
`validate · check-refs`. Copy the `·` separator from the `01b` row rather than typing a
middle dot, so the character matches exactly.

- [ ] **Step 4: Update `docs/concepts/pipeline.md`**

Locate extract's gate statement (`grep -n extract docs/concepts/pipeline.md`) and add
`check-refs` alongside `validate`, matching whatever form that document uses for a stage with
two gates — read the `reconcile-subjects` entry and follow it exactly rather than inventing a
form.

- [ ] **Step 5: Update `rb-orchestrate`'s SKILL.md in both places**

Step B2 currently reads, at ~498: *"Then `rubrica validate --stage extract --run <run>` once,
after all members are done."* Add the `check-refs` call after it, and say why it is one call
after every member rather than one per member — that is the same caveat the skill already
carries for the later fan-outs, so match their wording rather than inventing new prose. Also
update the summary table line at ~226, `fan out rb-extract, one per input artifact   ->
validate --stage extract`, to name both commands, keeping the column alignment of the
surrounding lines intact.

Then confirm the contract block is untouched and still passes:

```
uv run rubrica check-skills    # expect 0
```

- [ ] **Step 6: Run the docs-accuracy suite and the three gates**

```
uv run pytest tests/unit/test_docs_accuracy.py -q
uv run pytest -q
make check
uv run rubrica check-skills
```

`make check` matters here specifically because `CLAUDE.md` is **not** in ruff's
`extend-exclude` while all of `docs/` is.

- [ ] **Step 7: Commit**

Stage `scripts/render-pipeline-diagram.py`, `docs/concepts/pipeline-diagram.html`,
`docs/concepts/pipeline.md`, `CLAUDE.md` and
`src/rubrica/skills/rb-orchestrate/SKILL.md`, then commit with `git commit -S -s` and this
message:

```
docs: Run check-refs at extract's gate, where the missing member is caught

Before this, the missing-claims-file finding first surfaced at reconcile-subjects'
gate -- correctly named, but only after that pass had already built a subjects
partial from an incomplete corpus, so the repair cost two stages instead of one.
check-refs was measured clean at 0 findings on an intact run stopped at extract,
so the added gate does not turn a green run amber.

Refs #19

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
```

---

## Verification before the branch is considered done

```
uv run pytest -q                                             # all pass
make check                                                   # ruff check + format --check, clean
uv run rubrica check-skills                                  # 0
uv run python scripts/render-pipeline-diagram.py --check      # 0
```

Plus the four by-hand measurements in Task 1 Step 7 and Task 2 Step 7, which are the only
evidence that either predicate has been watched failing. A predicate nobody has watched fail
is not yet a guard.
