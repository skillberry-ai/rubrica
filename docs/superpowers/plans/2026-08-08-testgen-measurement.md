# Testgen Measurement Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the four measurement tools of design spec §7 — `smoke`, `compare-gold`, `diff-runs`, `sample-for-review` — so a generated suite can be judged degenerate, trivial, or broken-labelled before anyone trusts a number from it.

**Architecture:** Every tool reads a completed run directory and writes under a new `measurement/` subtree; the numbered prefixes stay reserved for pipeline stages, so `STAGES` and `STAGE_ARTIFACTS` are untouched. `smoke` is the only tool that touches the outside world, and it does so through exactly two subprocess seams — an agent command per role, and the emitted package's *own* `tests/verify.py`. Everything else is pure functions over JSON, so the aggregation, the thresholds, the matching, and the sampling are all unit-testable without a container, a network, or an LLM call.

**Tech Stack:** Python 3.13, uv, jsonschema (Draft202012Validator), tomli-w, pytest, ruff. No new runtime dependencies.

## Scope Check

This plan covers four tools plus five contract fixes carried forward from earlier builds. That is close to the size of the closure-and-emit build (11 tasks), and the four tools are only loosely coupled — each is one module plus its tests. They are kept in one plan rather than four because they share the run-directory layout, the `measurement/` subtree, the CLI surface, and one metric (`jaccard`), and because splitting a 1-to-3-task tool into its own plan would cost more in duplicated groundwork than it buys in isolation. Each task still ends at an independently testable deliverable, so a reviewer can reject any one of them without touching its neighbours.

## Global Constraints

Every task's requirements implicitly include this section.

- **Python 3.13**, managed by `uv`. Runtime dependencies stay exactly `jsonschema>=4.23` and `tomli-w>=1.1`. Dev stays `pytest>=8.3`, `ruff>=0.8`. **Adding a runtime dependency is out of scope for this plan.**
- **ruff** with `line-length = 100`, `select = ["E", "F", "I", "UP", "B", "SIM"]`. `make check` must be clean — `ruff check .` and `ruff format --check .` both.
- **`make test` must be green at the end of every task.** Not just the new tests.
- **Commits:** `git commit -S -s` — both flags, every time. Cryptographic signature *and* DCO sign-off. Add `Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>`. **Never** `Co-Authored-By`, `Made-with`, or any trailer GitHub parses as co-authorship. If signing fails, stop and report it; do not fall back to an unsigned commit.
- **Exit codes are the orchestrator's contract:** `0` clean, `1` findings printed one per line on stdout, `2` usage error or an unreadable run directory. Two failure modes stay closed: **a stage defect must never surface as `2`**, and **a `1` must never have empty stdout**.
- **A malformed human-supplied config file is a `2`, not a `1`.** `--agents` and `--gold` name files a person wrote. There is no stage to send a repair prompt to, so a schema failure there is a usage error, reported on stderr, exactly as `intake` already treats the paths it is handed. This is the one place in the project where a schema finding does not become exit `1`.
- **`src/testgen/suite/verify.py` stays stdlib-only and never imports `testgen`.** It executes inside a bare `ubi9` container. Zero `# noqa`.
- **Never restate a constant or a rule across a seam — import it.** If `refs` recomputes what `smoke` declared, it calls `smoke`'s own function rather than re-deriving the arithmetic. A constant duplicated across two modules (or into a schema) is one of the per-seam defect classes §8 of the spec names, and it is the shape that produced the last build's Critical.
- **Schemas gate artifacts the code did not write.** Model-authored stage outputs and human-authored config files get a JSON Schema. Measurement outputs, which this project's own code writes, are gated by unit tests instead — a schema over them would only restate the writer. `07-report.json` keeps its schema because `validate --stage smoke` is a real gate an orchestrator branches on.
- **Determinism.** No `random`, no builtin `hash()` (it is salted per process), and no wall-clock value in any written output. Sampling ties break on `hashlib.sha256`. Run ids and timestamps come from `intake` and nowhere else.
- **The layer-2 precondition is unchanged.** `refs.py` and `emit.py` index schema-required keys directly and raise on a malformed document rather than returning a finding, because layer 1 gates the artifact first. New code in those modules follows the same rule. New modules that read *emitted packages* or *human config* use `.get()`, because nothing orders `validate` before them — and each such site says which of the two it is.
- **Every new check needs two things:** deletion-mutation evidence (delete the check, and a **named** test fails — quote the name) **and** the pipeline state it must stay *silent* in, added to `tests/unit/test_refs_states.py`. The first is a per-check counter; the second is its per-seam dual. The last build's Critical was invisible to the first and obvious to the second.
- **Mutation harnesses set `PYTHONDONTWRITEBYTECODE=1`** or sweep `__pycache__` between mutate and restore. A byte-length-preserving mutate-then-restore inside one second leaves CPython's mutated `.pyc` live, because `.pyc` validation checks source size and mtime-to-the-second only. Mutation evidence gathered without this is worthless.
- **Any subprocess that executes an emitted package's `verify.py` scrubs the environment:** `PYTHONPATH=""` and a minimal `PATH`. An accidental `import testgen` must fail the way it would in the container, not silently succeed from the dev tree.
- **The CLI is `testgen <subcommand>`, not `bin/<script>`.** The spec writes `bin/smoke`; the contract-spine build chose a single console script with subcommands and shipped it. Continue that. Do not create a `bin/` directory.

---

## Spec reconciliation

Scanned against the design spec, not only against itself — that was the last build's most expensive lesson: its pre-flight scan checked task-versus-task, found nothing, and the arbiter between two contradictory tasks turned out to be a clause in a spec section the scan never opened. Four places where this plan and the spec need reconciling, resolved here rather than left for an implementer to guess at:

**1. `diff-runs` takes two runs, not N.** §512 says "across N identical ungated runs"; §296 says `bin/diff-runs A B`. Pairwise is the primitive and N runs are N−1 (or N choose 2) invocations of it, so the CLI takes `--a` and `--b`. Aggregating N is deferred with the *execution* of `diff-runs`, which §8's deferral table already puts in slice 2 — building an N-way aggregator for a tool nobody has run yet is the wrong order.

**2. `diff-runs` compares three stage products, not "artifact by artifact".** §296 says artifact by artifact; §512 names exactly three comparisons — capability sets after 1b, goal×cell claims after 2, final task ids after 6. §512 is the requirement and §296 is its rationale ("so variance can be attributed to a stage"). Three named comparisons satisfy the rationale; comparing every artifact byte-wise would report canonical-JSON formatting as variance and attribute nothing.

**3. A smoke run without all three agents.** §493 describes three agents and gives each a job. It does not say what happens when a roster names two. This plan rules: the run proceeds, a finding names the missing role, and the verdict is `inconclusive` — because dropping the oracle is a cost decision a human is entitled to make, the remaining data is real, and `healthy` would be a claim about a spread nobody measured. Recorded in §7 by Task 13, so the ruling lives in the spec rather than only in the code.

**4. The post-rejection state, again.** §346's loop puts `reject → mark rejected in 02, recompute coverage` *before* emit and smoke, and §280 admits `rejected` under `04/05/06`. A rejection discovered after smoke has already run is therefore a reachable state in which `07-report.json` names a scenario with no package — and it is the state a naive report checker would report as a defect. Task 8 resolves it on status and adds it to the states table. This is the same question that produced the last build's Critical; the answer is the same and it is now enforced in a fourth place.

## The measurement layout

New on disk. Nothing here is a pipeline stage, so the numbered prefixes are left alone.

```
runs/<run-id>/
  manifest.json  00-inputs/ … 06-suite/  07-report.json      (unchanged)
  measurement/
    smoke/<role>/<sid>/agent/           transcript: the agent writes here, and
                                        smoke adds the command's stdout as
                                        agent-stdout.jsonl
    smoke/<role>/<sid>/agent-stderr.txt outside agent/ on purpose — verify.py
                                        globs *.jsonl and *.txt in the agent log
                                        directory, so stderr placed inside it
                                        would be read back as transcript input
    smoke/<role>/<sid>/verifier/        reward.json reward.txt reward-detail.json
    smoke/<role>/<sid>/verifier-stderr.txt
    recall.json                         compare-gold
    review/packet.md                    sample-for-review
    review/sample.json
  decisions.md                                                (unchanged)
```

`smoke/<role>/<sid>/agent/` and `.../verifier/` deliberately mirror Harbor's `/logs/agent` and `/logs/verifier`. That is the whole point: the verifier that runs here is invoked with the same three arguments `test.sh` passes it in the container, so a package that scores locally scores there.

`diff-runs` writes nothing. It spans two runs and belongs to neither, so its report goes to stdout like `dedupe-candidates` already does.

## File Structure

| File | Responsibility |
|---|---|
| `src/testgen/errors.py` | **Create.** `UsageError`, moved out of `intake.py` so `smoke` can raise it without importing the intake stage. |
| `src/testgen/metrics.py` | **Create.** `jaccard`. One function, but it is where the 0/0 ruling lives, and both `recall` and `stability` need it. |
| `src/testgen/smoke.py` | **Create.** Stage 7: run each role over each package, score with the package's own verifier, aggregate into `07-report.json`. The two subprocess seams live here and nowhere else. |
| `src/testgen/recall.py` | **Create.** `compare-gold`: recall and novelty against a human-authored bench list. |
| `src/testgen/stability.py` | **Create.** `diff-runs`: per-stage Jaccard plus the comparability precondition. |
| `src/testgen/review.py` | **Create.** `sample-for-review`: deterministic stratified sampling and the review packet. |
| `src/testgen/schema/agents-0.1.json` | **Create.** Human-authored: the three agent roles and their commands. |
| `src/testgen/schema/gold-0.1.json` | **Create.** Human-authored: the ~10 authored bench tasks. |
| `src/testgen/schema/manifest-0.1.json` | **Modify.** Add required `inputs[].stored_as`. |
| `src/testgen/paths.py` | **Modify.** `input_file`, `measurement_dir`, `smoke_dir`, `recall`, `review_dir`, `review_packet`, `review_sample`. |
| `src/testgen/refs.py` | **Modify.** `check_readable` (and `check_all`'s short-circuit), `check_inputs`, `check_report`. |
| `src/testgen/intake.py` | **Modify.** Record `stored_as`; import `UsageError` from `errors`. |
| `src/testgen/validate.py` | **Modify.** Register the `agents` and `gold` schema kinds. |
| `src/testgen/suite/verify.py` | **Modify.** Refuse an unreadable or non-object contract; rule on a non-string `result`. |
| `src/testgen/emit.py` | **Modify.** One docstring correction. |
| `src/testgen/cli.py` | **Modify.** Four subcommands; import `UsageError` from `errors`. |
| `tests/builders.py` | **Modify.** `stored_as` and the input bytes it hashes; `minimal_agents`, `minimal_gold`. |
| `tests/unit/test_refs_inputs.py` | **Create.** The digest re-verification. |
| `tests/unit/test_refs_readable.py` | **Create.** `check_readable` and the short-circuit. |
| `tests/unit/test_verify_contract_refusal.py` | **Create.** The two `verify.py` hardening rulings. |
| `tests/unit/test_smoke_config.py` | **Create.** Agent config loading, substitution, preflight. |
| `tests/unit/test_smoke_subprocess.py` | **Create.** The two seams, against real subprocesses. |
| `tests/unit/test_smoke_aggregate.py` | **Create.** Flags, summary, verdict, and the ragged-set rule. |
| `tests/unit/test_smoke_run.py` | **Create.** End to end with a scripted fake agent. |
| `tests/unit/test_refs_report.py` | **Create.** The report↔suite cross-check. |
| `tests/unit/test_metrics.py` | **Create.** `jaccard`, including 0/0. |
| `tests/unit/test_recall.py` | **Create.** Matching, novelty precedence, the noise caveat. |
| `tests/unit/test_stability.py` | **Create.** Per-stage Jaccard and comparability. |
| `tests/unit/test_review.py` | **Create.** Determinism, band preference, packet contents. |
| `tests/unit/test_refs_states.py` | **Modify.** Add the `measurement` state. |
| `tests/unit/test_cli.py` | **Modify.** Four subcommands' exit codes. |
| `tests/unit/test_schemas_planning.py` | **Modify.** The two new schemas compile and the registry is consistent. |
| `README.md`, spec §4 and §8 | **Modify.** The `measurement/` layout, the new subcommands, the status of the carried-forward lists. |

---

## Task 1: Re-verify input digests

The last item owed from the contract-spine build's carried-forward list. Nothing confirms the bytes in `00-inputs/` are the bytes whose hash the manifest records, so the reproducibility claim rests on an unchecked assumption. Closing it needs one schema addition first: the manifest records a digest but not the *filename* the copy was written under, so a checker would have to re-derive `intake`'s naming rule — a second definition that drifts from the first. `stored_as` makes the manifest self-describing instead.

**Files:**
- Modify: `src/testgen/schema/manifest-0.1.json`
- Modify: `src/testgen/artifacts.py` (receive `sha256_of`)
- Modify: `src/testgen/intake.py` (`stored_name`, record `stored_as`)
- Modify: `src/testgen/paths.py` (`input_file`)
- Modify: `src/testgen/refs.py` (`check_inputs`, wire into `check_all`)
- Modify: `tests/builders.py`
- Modify: `tests/unit/test_refs_states.py` (`_intake` writes the registered copy)
- Test: `tests/unit/test_refs_inputs.py` (create)
- Test: `tests/unit/test_intake.py`, `tests/unit/test_paths.py`, `tests/unit/test_schemas_planning.py` (extend)

**Interfaces:**
- Produces: `paths.RunPaths.input_file(stored_as: str) -> Path`; `intake.stored_name(artifact_id: str, source: Path) -> str`; `artifacts.sha256_of(path: Path) -> str`; `refs.check_inputs(run: RunPaths) -> list[Finding]`.
- Consumes: nothing from later tasks. `artifacts.sha256_of` is the moved-in `intake.sha256_of`; `intake` re-imports it so `intake.sha256_of` keeps resolving and existing tests that reference it still pass.

- [ ] **Step 1: Move `sha256_of` into `artifacts.py`**

Cut the function out of `intake.py` verbatim and paste it into `artifacts.py` after `read_json`. It reads a file's bytes, which is that module's job, and `refs` needs it without importing the intake *stage*.

```python
def sha256_of(path: Path | str) -> str:
    """Hex digest of a file's bytes, streamed so a large trace is fine."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()
```

Add `import hashlib` to `artifacts.py`. In `intake.py`, delete the function and its now-unused `import hashlib`, and add `sha256_of` to the existing `from testgen.artifacts import write_json` line.

- [ ] **Step 2: Run the tests to confirm the move broke nothing**

Run: `uv run pytest -q`
Expected: PASS, unchanged count. `intake.sha256_of` still resolves through the import.

- [ ] **Step 3: Write the failing test for `paths.input_file`**

Add to `tests/unit/test_paths.py`:

```python
def test_input_file_resolves_under_the_inputs_directory():
    run = RunPaths("/runs/run-1")
    assert run.input_file("aap2-api.json") == Path("/runs/run-1/00-inputs/aap2-api.json")


def test_input_file_refuses_an_unsafe_stored_name():
    run = RunPaths("/runs/run-1")
    with pytest.raises(UnsafeSegment):
        run.input_file("../../etc/passwd")
```

- [ ] **Step 4: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_paths.py -q -k input_file`
Expected: FAIL with `AttributeError: 'RunPaths' object has no attribute 'input_file'`

- [ ] **Step 5: Implement `paths.input_file`**

Add to `RunPaths`, in the `-- per-id artifacts --` block beside `claims`:

```python
    def input_file(self, stored_as: str) -> Path:
        """The registered copy of one input artifact, by its manifest name.

        `stored_as` comes from manifest.inputs[].stored_as, which intake writes.
        That is what makes the manifest self-describing: a reader re-verifying a
        digest does not have to re-derive intake's naming rule, and there is only
        one definition of that rule to keep correct.
        """
        return self.inputs_dir / safe_segment(stored_as)
```

- [ ] **Step 6: Run them to verify they pass**

Run: `uv run pytest tests/unit/test_paths.py -q -k input_file`
Expected: PASS

- [ ] **Step 7: Write the failing tests for `intake`'s `stored_as`**

Add to `tests/unit/test_intake.py`:

```python
def test_the_manifest_records_the_name_each_input_was_stored_under(tmp_path):
    source = tmp_path / "api.json"
    source.write_text('{"tools": []}', encoding="utf-8")
    run = intake(
        inputs=[source],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
    )
    entry = read_json(run.manifest)["inputs"][0]
    assert entry["stored_as"] == "api.json"
    assert run.input_file(entry["stored_as"]).is_file()
    assert sha256_of(run.input_file(entry["stored_as"])) == entry["sha256"]


def test_a_suffix_that_would_make_an_unsafe_name_is_dropped(tmp_path):
    """The extension is cosmetic; the artifact id is the identity.

    A source named `weird.js on` would otherwise be stored as `weird-js on`,
    which manifest.stored_as cannot safely reference and paths.input_file would
    raise on -- turning a registrable input into an exit 2.
    """
    source = tmp_path / "weird.js on"
    source.write_text("{}", encoding="utf-8")
    run = intake(
        inputs=[source],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
    )
    entry = read_json(run.manifest)["inputs"][0]
    assert entry["stored_as"] == "weird-js-on"
    assert run.input_file("weird-js-on").is_file()
```

Import `sha256_of` from `testgen.artifacts` and `read_json` in that test module if they are not already imported.

- [ ] **Step 8: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_intake.py -q -k stored`
Expected: FAIL with `KeyError: 'stored_as'` on the first, and `assert 'weird-js on' == 'weird-js-on'` on the second.

- [ ] **Step 9: Implement `stored_name` and record it**

In `intake.py`, add after `slug`:

```python
def stored_name(artifact_id: str, source: Path) -> str:
    """The filename an input is registered under inside 00-inputs/.

    The suffix is cosmetic and the artifact id is the identity, so a suffix that
    would make the name an unsafe path segment is dropped rather than sanitised
    into something unrecognisable or raised on. Raising would turn a perfectly
    registrable input into a misconfigured-harness exit 2; keeping it would put
    a name in manifest.stored_as that paths.input_file refuses to join.
    """
    candidate = f"{artifact_id}{Path(source).suffix.lower()}"
    return candidate if is_safe_segment(candidate) else artifact_id
```

Import `is_safe_segment` alongside `safe_segment` from `testgen.paths`. Then in `intake`'s loop, replace the two lines that build `destination` and append the entry:

```python
    for path, artifact_id in zip(inputs, _unique_ids(inputs), strict=True):
        stored_as = stored_name(artifact_id, path)
        destination = run.inputs_dir / stored_as
        shutil.copy2(path, destination)
        entries.append(
            {
                "artifact_id": artifact_id,
                "source_path": str(path),
                "stored_as": stored_as,
                "sha256": sha256_of(path),
                "kind": classify(path),
                "bytes": path.stat().st_size,
            }
        )
```

- [ ] **Step 10: Add `stored_as` to the manifest schema**

In `src/testgen/schema/manifest-0.1.json`, inside `properties.inputs.items`: add `"stored_as"` to `required` (between `source_path` and `sha256`) and add the property:

```json
          "stored_as": { "$ref": "#/$defs/id" },
```

`$defs/id` already permits dots, so `aap2-api.json` matches, and it already forbids `/` and a leading dot, which is what makes the name safe to join.

- [ ] **Step 11: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_intake.py -q -k stored`
Expected: PASS

- [ ] **Step 12: Give the builders an input the manifest's digest actually describes**

In `tests/builders.py`, add `import hashlib` and two module constants above `minimal_claims`:

```python
# The registered input copy that minimal_manifest describes. The manifest's
# sha256 is the real digest of these bytes, so any state builder that writes
# them satisfies refs.check_inputs by construction rather than by tolerance --
# the previous "a" * 64 placeholder could only ever have passed a check that
# was not looking.
MINIMAL_INPUT_NAME = "aap2-api.json"
MINIMAL_INPUT_BYTES = b'{"tools": [{"name": "query_aap2"}]}\n'
```

Then rewrite `minimal_manifest`'s single input entry:

```python
        "inputs": [
            {
                "artifact_id": "aap2-api",
                "source_path": "harness-skills/parsec-aap2/api.json",
                "stored_as": MINIMAL_INPUT_NAME,
                "sha256": hashlib.sha256(MINIMAL_INPUT_BYTES).hexdigest(),
                "kind": "mcp_tool_schema",
                "bytes": len(MINIMAL_INPUT_BYTES),
            }
        ],
```

Then run `uv run pytest -q` and fix every test that asserted on the old `"a" * 64` or on `"bytes": 4096`. Do not weaken an assertion to make it pass: if a test needed a specific digest, it should now use `hashlib.sha256(MINIMAL_INPUT_BYTES).hexdigest()` or the builder constants.

- [ ] **Step 13: Write the failing tests for `check_inputs`**

Create `tests/unit/test_refs_inputs.py`:

```python
"""refs.check_inputs: the bytes in 00-inputs/ against the manifest's digests.

Nothing checked this before, and the reproducibility claim rests on it. A run
whose registered copy has been edited since intake makes every claim derived
from that input unattributable, while validate, check-refs and emit all stay
green -- the numbers are simply confidently wrong.
"""

from __future__ import annotations

import hashlib

import pytest

from testgen.artifacts import write_json
from testgen.paths import RunPaths
from testgen.refs import check_inputs
from tests.builders import MINIMAL_INPUT_BYTES, MINIMAL_INPUT_NAME, minimal_manifest


def _run(tmp_path, *, manifest=None, body=MINIMAL_INPUT_BYTES, name=MINIMAL_INPUT_NAME):
    run = RunPaths(tmp_path)
    write_json(run.manifest, manifest if manifest is not None else minimal_manifest())
    if body is not None:
        run.inputs_dir.mkdir(parents=True, exist_ok=True)
        (run.inputs_dir / name).write_bytes(body)
    return run


def test_a_registered_input_whose_stored_bytes_match_is_clean(tmp_path):
    assert check_inputs(_run(tmp_path)) == []


def test_no_manifest_is_not_a_finding(tmp_path):
    """The state before intake. check_all runs in it and must stay silent."""
    assert check_inputs(RunPaths(tmp_path)) == []


def test_a_registered_input_with_no_stored_copy_is_reported(tmp_path):
    findings = check_inputs(_run(tmp_path, body=None))
    assert len(findings) == 1
    assert findings[0].pointer == "/inputs/0/stored_as"
    assert "no stored copy" in findings[0].message


def test_an_edited_stored_input_is_reported(tmp_path):
    run = _run(tmp_path, body=b'{"tools": [{"name": "tampered"}]}\n')
    findings = check_inputs(run)
    assert len(findings) == 1
    assert findings[0].artifact == run.input_file(MINIMAL_INPUT_NAME)
    assert "has been edited since intake" in findings[0].message
    assert hashlib.sha256(MINIMAL_INPUT_BYTES).hexdigest() in findings[0].message


def test_a_stored_copy_whose_recorded_size_is_wrong_is_reported(tmp_path):
    """Reachable only by hand-editing the manifest, and still worth a finding.

    A digest match all but guarantees a size match, so this fires on a manifest
    someone edited `bytes` in -- which is the manifest field a reader skims
    instead of hashing.
    """
    manifest = minimal_manifest()
    manifest["inputs"][0]["bytes"] = 999999
    findings = check_inputs(_run(tmp_path, manifest=manifest))
    assert len(findings) == 1
    assert "999999" in findings[0].message


def test_an_unsafe_stored_as_is_reported_rather_than_raised(tmp_path):
    """paths.input_file raises UnsafeSegment, which cli.py would map to exit 2.

    A manifest is a stage output, so a bad value in it is a repairable defect and
    must arrive as a finding. Returning it raw would report a repairable defect
    as a misconfigured harness and discard every other finding in the run.
    """
    manifest = minimal_manifest()
    manifest["inputs"][0]["stored_as"] = "../../etc/passwd"
    findings = check_inputs(_run(tmp_path, manifest=manifest))
    assert len(findings) == 1
    assert "not a safe path segment" in findings[0].message


def test_two_bad_inputs_are_both_reported(tmp_path):
    """The orchestrator gets one bounded repair attempt, so it needs every reason."""
    manifest = minimal_manifest()
    manifest["inputs"].append(
        {
            "artifact_id": "aap2-schema",
            "source_path": "harness-skills/parsec-aap2/schema.json",
            "stored_as": "aap2-schema.json",
            "sha256": "b" * 64,
            "kind": "entity_schema",
            "bytes": 2,
        }
    )
    run = _run(tmp_path, manifest=manifest)
    (run.inputs_dir / "aap2-schema.json").write_bytes(b"{}")
    assert len(check_inputs(run)) == 1  # only the second: digest mismatch
    (run.inputs_dir / MINIMAL_INPUT_NAME).write_bytes(b"edited\n")
    assert len(check_inputs(run)) == 2
```

Note the `pytest` import is used by nothing above; drop it rather than leave an `F401` for ruff to flag.

- [ ] **Step 14: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_refs_inputs.py -q`
Expected: FAIL with `ImportError: cannot import name 'check_inputs' from 'testgen.refs'`

- [ ] **Step 15: Implement `check_inputs`**

In `refs.py`, add `sha256_of` to the `testgen.artifacts` import and `is_safe_segment` to the `testgen.paths` import, then add after `check_manifest`:

```python
def check_inputs(run: RunPaths) -> list[Finding]:
    """The bytes in 00-inputs/ against the digests the manifest records.

    The reproducibility claim rests on this and nothing checked it. Two runs are
    comparable only if they read the same inputs, and manifest.inputs[].sha256 is
    the only record of what those were; a registered copy edited after intake
    makes every claim derived from it unattributable while every other gate in
    the project stays green.

    This re-hashes on every check-refs call, which is once per stage. Slice 1
    registers an api.json, a schema.json and a handful of traces, so the cost is
    milliseconds. If a large source tree is ever registered, the fix is a
    size-and-mtime shortcut here, not skipping the check.

    `stored_as` is validated rather than joined blindly: paths.input_file raises
    UnsafeSegment, which cli.py maps to exit 2, and a bad value in a stage output
    is a repairable defect that must arrive as a finding instead.
    """
    manifest = _load(run.manifest)
    if manifest is None:
        return []
    out: list[Finding] = []
    for i, entry in enumerate(manifest["inputs"]):
        artifact_id = entry["artifact_id"]
        stored_as = entry["stored_as"]
        if not is_safe_segment(stored_as):
            out.append(
                Finding(
                    run.manifest,
                    "refs",
                    f"/inputs/{i}/stored_as",
                    f"{stored_as!r} is not a safe path segment, so the registered copy of "
                    f"{artifact_id!r} cannot be located",
                )
            )
            continue
        path = run.input_file(stored_as)
        if not path.is_file():
            out.append(
                Finding(
                    run.manifest,
                    "refs",
                    f"/inputs/{i}/stored_as",
                    f"registered input {artifact_id!r} has no stored copy at {path}",
                )
            )
            continue
        actual = sha256_of(path)
        if actual != entry["sha256"]:
            out.append(
                Finding(
                    path,
                    "refs",
                    "",
                    f"stored bytes hash to {actual} but the manifest records {entry['sha256']} "
                    f"for {artifact_id!r}; the registered copy has been edited since intake, so "
                    "nothing derived from it is attributable to these inputs",
                )
            )
            continue
        size = path.stat().st_size
        if size != entry["bytes"]:
            out.append(
                Finding(
                    path,
                    "refs",
                    "",
                    f"stored copy is {size} bytes but the manifest records {entry['bytes']} for "
                    f"{artifact_id!r}",
                )
            )
    return out
```

Then add it to `check_all`, immediately after `check_manifest`:

```python
    findings.extend(check_inputs(run))
```

- [ ] **Step 16: Run them to verify they pass**

Run: `uv run pytest tests/unit/test_refs_inputs.py -q`
Expected: PASS, 7 tests.

- [ ] **Step 17: Make the `intake` state in the states table write the registered copy**

`check_inputs` now runs in every state, and `_intake` wrote only the manifest — a fiction, since real intake copies and hashes every input. Fixing the fiction is what gives the new check a real silent state. In `tests/unit/test_refs_states.py`:

```python
def _intake(run: RunPaths) -> None:
    """The manifest plus the registered copy whose digest it records.

    Writing the manifest alone was a fiction: intake copies every input into
    00-inputs/ and hashes it, and refs.check_inputs re-verifies that. The
    builder's sha256 is the digest of MINIMAL_INPUT_BYTES, so this state
    satisfies the check by construction -- if it needed a tolerance in
    check_inputs to pass, the check would not be worth having.
    """
    write_json(run.manifest, minimal_manifest())
    run.inputs_dir.mkdir(parents=True, exist_ok=True)
    run.input_file(MINIMAL_INPUT_NAME).write_bytes(MINIMAL_INPUT_BYTES)
```

Import `MINIMAL_INPUT_BYTES` and `MINIMAL_INPUT_NAME` from `tests.builders`. Add to `test_the_states_are_cumulative_so_the_last_one_is_a_complete_run`:

```python
    assert run.input_file(MINIMAL_INPUT_NAME).is_file()
```

- [ ] **Step 18: Run the whole suite**

Run: `uv run pytest -q` then `uv run ruff check . && uv run ruff format --check .`
Expected: all green. Every state in the table must be clean — if any state reports a `check_inputs` finding, the state builder is wrong, not the check.

- [ ] **Step 19: Gather deletion-mutation evidence**

For each of the four checks in `check_inputs`, delete it, run the suite, and record which **named** test fails. Set `PYTHONDONTWRITEBYTECODE=1` for every run, or the mutated `.pyc` outlives the restore.

```bash
export PYTHONDONTWRITEBYTECODE=1
# for each check: comment out its `if`/`out.append` block, then
uv run pytest -q 2>&1 | tail -20
# restore, and confirm green again before the next mutation
```

Expected mapping — every one of these must fail, by name:

| Deleted check | Named test that must fail |
|---|---|
| unsafe `stored_as` | `test_an_unsafe_stored_as_is_reported_rather_than_raised` |
| absent stored copy | `test_a_registered_input_with_no_stored_copy_is_reported` |
| digest mismatch | `test_an_edited_stored_input_is_reported` |
| recorded size mismatch | `test_a_stored_copy_whose_recorded_size_is_wrong_is_reported` |

Also delete the `check_inputs(run)` line from `check_all` and confirm a named test fails — if none does, the check is unreachable through the CLI. Add one to `tests/unit/test_refs_inputs.py` if needed:

```python
def test_check_all_runs_the_input_digest_check(tmp_path):
    run = _run(tmp_path, body=b"edited\n")
    assert any("edited since intake" in f.message for f in check_all(run))
```

Record the table in the task report.

- [ ] **Step 20: Commit**

```bash
git add -A
git commit -S -s -m "feat: Re-verify that the stored inputs are the bytes the manifest hashed

The last item owed from the contract-spine build's carried-forward list. The
manifest now records stored_as, so a reader confirming a digest does not
re-derive intake's naming rule, and refs.check_inputs re-hashes each registered
copy on every check-refs call.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 2: Name the artifact that is actually broken

An unparseable `02-scenarios.json` currently produces four findings blaming `03-coverage/latest.json` and `04-instances/`, and never names the broken file — so a repair prompt rewrites the wrong artifact. Every checker's `_load` returns `None` on an unreadable document, each draws its own conclusion from the absence, and the file that caused all of it is never mentioned. `emit._unreadable_instance` fixed this shape in the smaller instance; this is the larger one. Plan 3 adds a sixth `_load` caller, so fixing it now stops the defect compounding.

**Files:**
- Modify: `src/testgen/refs.py` (`_readable_targets`, `check_readable`, `check_all`)
- Modify: `src/testgen/emit.py` (one docstring)
- Test: `tests/unit/test_refs_readable.py` (create)

**Interfaces:**
- Produces: `refs.check_readable(run: RunPaths) -> list[Finding]`. `check_all` returns *only* its findings when it returns any.
- Consumes: nothing.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_refs_readable.py`:

```python
"""refs.check_readable: name the artifact that is broken, not its neighbours.

Every checker in refs treats an unreadable document as an absent one, because
_load swallows ArtifactError. That is right for absence -- a stage that has not
run yet is not a finding -- and wrong for a truncated file: four checkers each
concluded something from the silence, none of them named the file, and the
repair prompt rewrote an artifact that was fine.
"""

from __future__ import annotations

from testgen.paths import RunPaths
from testgen.refs import check_all, check_readable
from tests.unit.test_refs_states import build_state


def test_a_complete_run_has_nothing_unreadable(tmp_path):
    assert check_readable(build_state(tmp_path, "smoke")) == []


def test_an_empty_run_has_nothing_unreadable(tmp_path):
    """Absence is not unreadability. Reporting it would fire before intake."""
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    assert check_readable(run) == []


def test_a_truncated_scenarios_file_is_named(tmp_path):
    run = build_state(tmp_path, "smoke")
    run.scenarios.write_text('{"schema_version": "0.1", "scen', encoding="utf-8")
    findings = check_readable(run)
    assert [f.artifact for f in findings] == [run.scenarios]
    assert "malformed JSON" in findings[0].message


def test_check_all_names_only_the_broken_file(tmp_path):
    """The defect this check exists to remove.

    Before it, check_all returned four findings against 03-coverage/latest.json
    and 04-instances/ and never mentioned 02-scenarios.json at all.
    """
    run = build_state(tmp_path, "smoke")
    assert check_all(run) == [], "the baseline this state is measured against"
    run.scenarios.write_text("not json at all", encoding="utf-8")

    findings = check_all(run)
    assert [f.artifact for f in findings] == [run.scenarios]


def test_every_artifact_kind_layer_two_reads_is_covered(tmp_path):
    """Guards the target list itself.

    A check that names the broken file is only as good as its enumeration: an
    artifact missing from _readable_targets is one whose truncation still
    misdirects the repair. Breaking each in turn is the only way to prove the
    list is complete.
    """
    run = build_state(tmp_path, "smoke")
    task = run.task_dir("scn-001")
    for path in (
        run.manifest,
        run.claims("aap2-api"),
        run.world_model,
        run.scenarios,
        run.coverage_latest,
        run.seed("scn-001"),
        run.expected("scn-001"),
        run.verdict("scn-001"),
        task / "seed.json",
        task / "golden.json",
        task / "tests" / "expected.json",
        run.report,
    ):
        original = path.read_text(encoding="utf-8")
        path.write_text("{", encoding="utf-8")
        assert [f.artifact for f in check_readable(run)] == [path], f"not covered: {path}"
        path.write_text(original, encoding="utf-8")
    assert check_readable(run) == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_refs_readable.py -q`
Expected: FAIL with `ImportError: cannot import name 'check_readable' from 'testgen.refs'`

- [ ] **Step 3: Implement `_readable_targets` and `check_readable`**

Add to `refs.py`, immediately after `_load`:

```python
def _readable_targets(run: RunPaths) -> list[Path]:
    """Every JSON document in the run that a layer-2 check goes on to read.

    Pipeline order, so the first finding names the earliest broken artifact --
    the one a repair should start from. tests/unit/test_refs_readable.py breaks
    each of these in turn, which is what keeps the list complete: an artifact
    missing here is one whose truncation still misdirects the repair.
    """
    targets = [run.manifest]
    if run.claims_dir.is_dir():
        targets += sorted(run.claims_dir.glob("*.json"))
    targets += [run.world_model, run.scenarios]
    if run.coverage_dir.is_dir():
        targets += sorted(run.coverage_dir.glob("*.json"))
    for sid in run.scenario_ids_with_instances():
        targets += [run.seed(sid), run.expected(sid)]
    if run.verdicts_dir.is_dir():
        targets += sorted(run.verdicts_dir.glob("*.json"))
    for sid in run.scenario_ids_with_tasks():
        task = run.task_dir(sid)
        targets += [
            task / "seed.json",
            task / "golden.json",
            task / "tests" / "expected.json",
        ]
    targets.append(run.report)
    return targets


def check_readable(run: RunPaths) -> list[Finding]:
    """Every artifact that is present but is not parseable JSON, named.

    Absence is deliberately not reported: a stage that has not run yet is
    validate_stage's finding, and reporting it here would fire in states where
    nothing is wrong.
    """
    out: list[Finding] = []
    for path in _readable_targets(run):
        if not path.is_file():
            continue
        try:
            read_json(path)
        except ArtifactError as exc:
            out.append(Finding(path, "refs", "", str(exc)))
    return out
```

- [ ] **Step 4: Short-circuit `check_all`**

```python
def check_all(run: RunPaths) -> list[Finding]:
    """Every layer-2 check that the run directory currently has inputs for.

    An unparseable artifact short-circuits everything below it. Every checker
    treats an unreadable document as an absent one, so continuing produces
    findings that blame artifacts which are fine and never names the one that is
    broken -- and the orchestrator's single bounded repair attempt then rewrites
    the wrong file.
    """
    unreadable = check_readable(run)
    if unreadable:
        return unreadable
    findings: list[Finding] = []
    findings.extend(check_manifest(run))
    # the remaining eight check_* calls stay exactly as they are
```

Only the docstring and the two new lines at the top change; do not reorder or edit the existing `findings.extend(...)` calls.

- [ ] **Step 5: Run them to verify they pass**

Run: `uv run pytest tests/unit/test_refs_readable.py -q`
Expected: PASS, 5 tests.

- [ ] **Step 6: Correct `emit_run`'s docstring about pruning**

`emit_run`'s docstring draws the line at "a missing *input*", which does not describe what the code does to a per-instance defect: a truncated oracle or an unbound capability prunes that scenario's package. The behaviour is defensible; the docstring is wrong about it. Add this paragraph after the existing "Pruning runs only after the emit loop actually ran" paragraph:

```python
    A *per-instance* defect -- no verdict, an unbound capability, an oracle that
    no longer parses -- prunes that scenario's package rather than sparing it,
    and that is not the early-return case above. The package on disk was built
    from an oracle nobody can now read, so leaving it in place would ship a test
    whose gold label cannot be checked against anything. emit is deterministic,
    so repairing the oracle and re-emitting restores the package byte for byte:
    the cost is bounded to one re-run, which is the right trade against shipping
    a test that looks accepted and is not.
```

- [ ] **Step 7: Run the whole suite**

Run: `uv run pytest -q` and `uv run ruff check . && uv run ruff format --check .`
Expected: all green, including every state in `test_refs_states.py` — `check_readable` must be silent in all of them.

- [ ] **Step 8: Gather deletion-mutation evidence**

```bash
export PYTHONDONTWRITEBYTECODE=1
```

| Deleted | Named test that must fail |
|---|---|
| the `try`/`except ArtifactError` body in `check_readable` | `test_a_truncated_scenarios_file_is_named` |
| the short-circuit in `check_all` | `test_check_all_names_only_the_broken_file` |
| any single entry from `_readable_targets` | `test_every_artifact_kind_layer_two_reads_is_covered` (naming the path) |

Record it. If deleting `run.report` from `_readable_targets` does **not** fail a named test, the coverage loop is not reaching it — fix the test, not the list.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -S -s -m "fix: Name the unparseable artifact instead of blaming its neighbours

Every layer-2 checker treats an unreadable document as an absent one, so a
truncated 02-scenarios.json produced four findings against files that were fine
and never named the broken one. check_readable runs first and short-circuits.

Also corrects emit_run's docstring, which drew the pruning line at a missing
input and did not describe what the code does to a truncated oracle.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 3: Make the verifier refuse what it cannot read

Two carried-forward items in `suite/verify.py`, both of which `smoke` is about to make reachable by feeding it real transcripts and real packages.

A syntactically invalid `expected.json` exits 1 with a traceback from `json.loads` *before* `_contract_problems` runs, so the refusal path that exists to stop an authoring failure being scored as a zero never engages. And a transcript whose `result` is not a string crashes `compute_reward` at `answer.strip()`. The second needs a ruling, not a guard, because it changes what a malformed agent log scores.

**The ruling: a non-string `result` scores as no answer, and says so in the detail.** Coercing with `str()` is the tempting alternative and it is score inflation: `str({"text": "90420"})` contains `90420`, so an `answer_contains: "90420"` assertion would pass against a dict the agent never uttered in prose. `compute_reward`'s own docstring forbids exactly that — "Read none of the four as tolerance at the scoring seam. Tolerance there is score inflation." No answer means the `nonempty_answer` gate fires and the run scores 0, which is the honest outcome for a log this verifier cannot read, and the note in `reward-detail.json` is what distinguishes it from a genuinely empty answer.

**Files:**
- Modify: `src/testgen/suite/verify.py`
- Modify: `tests/unit/test_verify_assertions.py` (7 `parse_transcript` call sites)
- Test: `tests/unit/test_verify_contract_refusal.py` (create)

**Interfaces:**
- Produces: `parse_transcript(text) -> (calls, answer, ok, notes)` — a **4-tuple now**; `notes` is a `list[str]`. `read_contract(path) -> (contract | None, problems)`. `main` writes `detail["transcript_notes"]` when notes is non-empty.
- Consumes: nothing. `compute_reward`'s signature is unchanged.
- Constraint: this file stays stdlib-only, never imports `testgen`, and carries zero `# noqa`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_verify_contract_refusal.py`:

```python
"""verify.py refuses a contract it cannot read, and rules on a log it cannot.

Both paths are about the same distinction: a bypassed authoring gate must not
reach the platform as a real zero, and a malformed agent log must not reach it as
an inflated score.
"""

from __future__ import annotations

import json

from testgen.suite.verify import main, parse_transcript, read_contract
from tests.builders import minimal_suite_expected


def _package(tmp_path, contract_text):
    expected = tmp_path / "expected.json"
    expected.write_text(contract_text, encoding="utf-8")
    logs = tmp_path / "agent"
    logs.mkdir()
    (logs / "t.jsonl").write_text("", encoding="utf-8")
    out = tmp_path / "verifier"
    return ["--expected", str(expected), "--agent-logs", str(logs), "--out", str(out)], out


# -- an unreadable contract ---------------------------------------------------


def test_a_truncated_contract_is_refused_rather_than_crashing(tmp_path):
    argv, out = _package(tmp_path, '{"contract": "testgen/v1", "assert')
    assert main(argv) == 2
    assert not (out / "reward.txt").exists(), "a refusal must not look like a real zero"
    detail = json.loads((out / "reward-detail.json").read_text())
    assert "not parseable JSON" in detail["error"]


def test_a_contract_that_is_not_an_object_is_refused(tmp_path):
    """json.loads("[]") parses fine and then every .get() call would raise."""
    argv, out = _package(tmp_path, "[]")
    assert main(argv) == 2
    assert not (out / "reward.txt").exists()
    assert "not an object" in json.loads((out / "reward-detail.json").read_text())["error"]


def test_an_absent_contract_is_refused(tmp_path):
    out = tmp_path / "verifier"
    assert main(["--expected", str(tmp_path / "nope.json"), "--out", str(out)]) == 2
    assert "could not be read" in json.loads((out / "reward-detail.json").read_text())["error"]


def test_a_well_formed_contract_still_scores(tmp_path):
    """The refusal path must not have swallowed the ordinary one."""
    argv, out = _package(tmp_path, json.dumps(minimal_suite_expected()))
    assert main(argv) == 0
    assert (out / "reward.txt").read_text() == "0.0"


def test_read_contract_returns_the_document_when_it_is_fine(tmp_path):
    path = tmp_path / "c.json"
    path.write_text('{"contract": "testgen/v1"}', encoding="utf-8")
    contract, problems = read_contract(path)
    assert problems == []
    assert contract == {"contract": "testgen/v1"}


# -- a non-string result ------------------------------------------------------


def _result_line(payload):
    return json.dumps({"type": "result", "subtype": "success", "result": payload})


def test_a_non_string_result_scores_as_no_answer(tmp_path):
    """The ruling: no answer, not str(payload).

    str({"text": "90420"}) contains "90420", so coercing would satisfy an
    answer_contains assertion against a dict the agent never said in prose --
    inflation at the scoring seam, which compute_reward's docstring forbids.
    """
    calls, answer, ok, notes = parse_transcript(_result_line({"text": "90420"}))
    assert answer == ""
    assert ok is True, "the run itself succeeded; it is the answer that is unreadable"
    assert any("rather than a string" in note for note in notes)
    assert "dict" in " ".join(notes)


def test_a_null_result_scores_as_no_answer_without_a_note(tmp_path):
    """None is an ordinary empty answer, not a malformed one."""
    _, answer, _, notes = parse_transcript(_result_line(None))
    assert answer == ""
    assert notes == []


def test_a_non_object_event_is_skipped_and_counted(tmp_path):
    _, answer, _, notes = parse_transcript('{"type": "result", "result": "ok"}\n[1, 2, 3]')
    assert answer == "ok"
    assert any("skipped 1" in note for note in notes)


def test_an_assistant_event_with_a_non_object_message_is_skipped(tmp_path):
    calls, _, _, _ = parse_transcript(json.dumps({"type": "assistant", "message": "oops"}))
    assert calls == []


def test_the_notes_reach_reward_detail(tmp_path):
    """A concession invisible in the output is a silent one."""
    argv, out = _package(tmp_path, json.dumps(minimal_suite_expected()))
    logs = tmp_path / "agent"
    (logs / "t.jsonl").write_text(_result_line({"text": "90420"}), encoding="utf-8")
    assert main(argv) == 0
    detail = json.loads((out / "reward-detail.json").read_text())
    assert any("rather than a string" in note for note in detail["transcript_notes"])
    assert json.loads((out / "reward.txt").read_text()) == 0.0
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_verify_contract_refusal.py -q`
Expected: FAIL — `ImportError` for `read_contract`, and `ValueError: too many values to unpack` on the `parse_transcript` tests.

- [ ] **Step 3: Rewrite `parse_transcript`**

```python
def parse_transcript(text):
    """Read a stream-json transcript into (calls, answer, ok, notes).

    Each call is (tool_name, args). Malformed lines are skipped so a truncated
    transcript still scores rather than crashing -- a crash would be reported as
    a broken agent when the truth is a broken log.

    `notes` is what keeps those concessions honest. A skipped line or a coerced
    field changes the score, so it is carried out to reward-detail.json rather
    than applied silently. Distinct notes are recorded once each, so a wholly
    corrupt log cannot flood the detail file.

    A `result` that is not a string scores as **no answer**, deliberately not as
    `str(value)`: str({"text": "90420"}) contains "90420", so coercion would
    satisfy an answer_contains assertion against a dict the agent never uttered.
    compute_reward's docstring rules that out -- tolerance at the scoring seam is
    score inflation. No answer means the nonempty_answer gate fires, which is the
    honest reading of a log this verifier cannot understand.
    """
    calls, answer, ok = [], "", False
    notes, skipped = [], 0

    def note(message):
        if message not in notes:
            notes.append(message)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            skipped += 1
            continue
        if not isinstance(event, dict):
            skipped += 1
            continue
        if event.get("type") == "assistant":
            message = event.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    args = block.get("input")
                    calls.append((block.get("name", ""), args if isinstance(args, dict) else {}))
        elif event.get("type") == "result":
            # Last result event wins: exactly one is written per run, but a
            # partial transcript plus a terminal error event can yield two.
            value = event.get("result", "")
            if value is None:
                value = ""
            elif not isinstance(value, str):
                note(
                    f"a result event carried a {type(value).__name__} rather than a string; "
                    "scored as no answer"
                )
                value = ""
            answer = value
            ok = event.get("subtype") == "success" and not event.get("is_error", False)
    if skipped:
        notes.append(f"skipped {skipped} line(s) that were not parseable JSON objects")
    return calls, answer, ok, notes
```

- [ ] **Step 4: Add `read_contract` and rewire `main`**

```python
def read_contract(path):
    """-> (contract, problems). A file that could not be read is itself a problem.

    main() used to call json.loads directly, so a truncated expected.json raised
    out of the verifier before _contract_problems ran: the refusal path that
    exists to keep an authoring failure from being scored as a zero never
    engaged, and the platform saw a crashed verifier rather than a stated
    refusal. A gate cannot defend a file it did not manage to parse.
    """
    try:
        text = Path(path).read_text()
    except OSError as exc:
        return None, [f"contract at {path} could not be read: {exc}"]
    try:
        contract = json.loads(text)
    except ValueError as exc:
        return None, [f"contract at {path} is not parseable JSON: {exc}"]
    if not isinstance(contract, dict):
        return None, [
            f"contract at {path} is a {type(contract).__name__}, not an object; every field "
            "this verifier reads would be absent"
        ]
    return contract, []
```

Then `main`'s body, from the argument parse down:

```python
    args = parser.parse_args(argv)

    # out is created before the contract is read: a refusal has to be able to
    # write reward-detail.json, and an absent contract is one of the refusals.
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    contract, problems = read_contract(args.expected)
    if not problems:
        problems = _contract_problems(contract)
    if problems:
        # Refuse rather than write a misleading 0 -- or, for a weights
        # problem, an inflated reward that looks like a normal score. A
        # contract this verifier cannot read is a bypassed authoring gate, not
        # a bad agent run, and scoring it would invert that conclusion. No
        # reward.txt is written, so the platform sees a missing reward
        # instead of a real one.
        message = "; ".join(problems)
        (out / "reward-detail.json").write_text(json.dumps({"error": message}, indent=2))
        print(f"verify.py: {message}", file=sys.stderr)
        return 2

    calls, answer, ok, notes = parse_transcript(_read_logs(args.agent_logs))
    reward, detail = compute_reward(contract, calls, answer, ok)
    if notes:
        detail["transcript_notes"] = notes

    (out / "reward.json").write_text(json.dumps(reward, indent=2, sort_keys=True))
    (out / "reward.txt").write_text(str(reward["reward"]))
    (out / "reward-detail.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True, default=str)
    )
    return 0
```

- [ ] **Step 5: Update the existing `parse_transcript` call sites**

`tests/unit/test_verify_assertions.py` unpacks a 3-tuple in 7 places. Change each to the 4-tuple, using `_` for `notes` where the test does not care. Do **not** change what any of them asserts.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_verify_contract_refusal.py tests/unit/test_verify_assertions.py tests/unit/test_verify_reward.py -q`
Expected: PASS

- [ ] **Step 7: Confirm the file is still container-safe**

Run:
```bash
grep -n "import" src/testgen/suite/verify.py
grep -c "noqa" src/testgen/suite/verify.py || true
PYTHONPATH="" python3 -c "import ast,sys; ast.parse(open('src/testgen/suite/verify.py').read())"
```
Expected: imports are exactly `argparse json math sys pathlib.Path`; zero `noqa`; parses under a bare interpreter. No `testgen` import anywhere.

- [ ] **Step 8: Run the whole suite and gather mutation evidence**

Run: `uv run pytest -q` and `uv run ruff check . && uv run ruff format --check .`

```bash
export PYTHONDONTWRITEBYTECODE=1
```

| Deleted | Named test that must fail |
|---|---|
| the `except ValueError` branch of `read_contract` | `test_a_truncated_contract_is_refused_rather_than_crashing` |
| the `isinstance(contract, dict)` branch | `test_a_contract_that_is_not_an_object_is_refused` |
| the `except OSError` branch | `test_an_absent_contract_is_refused` |
| the `not isinstance(value, str)` branch | `test_a_non_string_result_scores_as_no_answer` |
| the `isinstance(message, dict)` guard | `test_an_assistant_event_with_a_non_object_message_is_skipped` |
| the `if notes:` line in `main` | `test_the_notes_reach_reward_detail` |

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -S -s -m "fix: Refuse a contract the verifier cannot parse, and rule on a non-string result

An invalid expected.json crashed json.loads before _contract_problems ran, so
the refusal path that keeps an authoring failure from being scored as a zero
never engaged. A non-string result crashed compute_reward at answer.strip().

The ruling on the second is no answer rather than str(value): coercion would let
str({\"text\": \"90420\"}) satisfy answer_contains \"90420\" against a dict the
agent never uttered. Every concession the parser makes is now carried out to
reward-detail.json rather than applied silently.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 4: The agent roster

`smoke` needs three agents, and the only honest way to get them is to let a human name the commands. This task builds that boundary: a schema'd roster file, the dataclass it loads into, the placeholder substitution that fills in per-task paths, and the preflight that refuses a roster with a command that cannot run — before any agent is invoked.

**Files:**
- Create: `src/testgen/errors.py`
- Create: `src/testgen/schema/agents-0.1.json`
- Create: `src/testgen/smoke.py`
- Modify: `src/testgen/intake.py`, `src/testgen/cli.py` (import `UsageError` from `errors`)
- Modify: `src/testgen/validate.py` (register `agents`)
- Modify: `tests/builders.py` (`minimal_agents`)
- Test: `tests/unit/test_smoke_config.py` (create), `tests/unit/test_schemas_planning.py` (extend)

**Interfaces:**
- Produces: `errors.UsageError`; `smoke.ROLES`, `smoke.REQUIRED_ROLES`, `smoke.AgentSpec`, `smoke.load_agents(path) -> tuple[AgentSpec, ...]`, `smoke.substitute(command, *, task_dir, logs_dir, scenario_id) -> tuple[str, ...]`, `smoke.preflight(specs) -> tuple[AgentSpec, ...]` (returns specs with `command[0]` resolved to an absolute path).
- Consumes: `validate.validate_artifact`, `findings.format_findings`, `artifacts.read_json`, and `emit.AGENT_TIMEOUT_SEC` — imported, never restated. `task.toml` declares that timeout to Harbor, so a locally-used different value would mean a package that times out here does not time out there.
- `AgentSpec` is `@dataclass(frozen=True)` with fields `role: str`, `model: str`, `command: tuple[str, ...]`, `timeout_sec: float = AGENT_TIMEOUT_SEC`, `notes: str = ""`.

- [ ] **Step 1: Move `UsageError` into its own module**

Create `src/testgen/errors.py`:

```python
"""Errors that change a CLI exit code.

UsageError lives here rather than in intake.py because it is not about intake.
It means "the harness was handed something it cannot act on", which cli.py maps
to exit 2 -- and smoke needs to raise it for a malformed agent roster without
importing the intake stage to get at the exception type.
"""

from __future__ import annotations


class UsageError(ValueError):
    """Raised when a component was called with arguments it cannot act on.

    Named rather than a bare ValueError so cli.py can map *these* to exit 2
    without also mapping every ValueError raised anywhere downstream. A coverage
    document with a non-numeric `pct` is a repairable score-stage defect, and
    reporting it as a misconfigured harness told the orchestrator to halt when
    one repair would have cleared it.
    """
```

In `intake.py`, delete the class and add `from testgen.errors import UsageError`. Leave the name importable from `intake` — `cli.py` and the existing tests reference `testgen.intake.UsageError` and must keep working. In `cli.py`, change the import to `from testgen.errors import UsageError` and drop `UsageError` from the `testgen.intake` import line.

- [ ] **Step 2: Run the suite to confirm the move broke nothing**

Run: `uv run pytest -q`
Expected: PASS, unchanged count.

- [ ] **Step 3: Write the agents schema**

Create `src/testgen/schema/agents-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "agents-0.1.json",
  "title": "Agent roster for a smoke run",
  "description": "Human-authored, not a stage output. The three roles of design spec section 7: a weak baseline that should fail nearly everything, the agent under test, and an oracle handed the reference answer that should pass nearly everything. Each command is an argv list; smoke substitutes {task_dir}, {logs_dir} and {scenario_id} into each element and expects the command to write a stream-json transcript into {logs_dir} or to stdout. Because a person wrote this file, a schema failure here is a usage error (exit 2) rather than a finding -- there is no stage to send a repair prompt to.",
  "type": "object",
  "required": ["schema_version", "agents"],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "0.1" },
    "agents": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["role", "model", "command"],
        "additionalProperties": false,
        "properties": {
          "role": { "enum": ["weak_baseline", "under_test", "oracle"] },
          "model": { "type": "string", "minLength": 1 },
          "command": {
            "description": "argv. prefixItems bounds only the executable, which must be a non-empty string; later elements may legitimately be empty.",
            "type": "array",
            "minItems": 1,
            "prefixItems": [{ "type": "string", "minLength": 1 }],
            "items": { "type": "string" }
          },
          "timeout_sec": { "type": "number", "exclusiveMinimum": 0 },
          "notes": { "type": "string" }
        }
      }
    }
  }
}
```

- [ ] **Step 4: Register the kind and add the builder**

In `validate.py`, add to `ARTIFACT_SCHEMAS`:

```python
    # Config kinds. Human-authored inputs, not stage outputs, so they are
    # deliberately absent from STAGE_ARTIFACTS: no stage produces them and
    # `validate --stage X` must never look for them.
    "agents": "agents-0.1.json",
```

In `tests/builders.py`:

```python
def minimal_agents(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "agents": [
            {
                "role": "weak_baseline",
                "model": "claude-haiku-4-5-20251001",
                "command": ["true"],
                "notes": "no tools",
            },
            {"role": "under_test", "model": "claude-sonnet-5", "command": ["true"]},
            {
                "role": "oracle",
                "model": "claude-sonnet-5",
                "command": ["true"],
                "notes": "handed golden.json",
            },
        ],
    }
    payload.update(over)
    return payload
```

Add to `tests/unit/test_schemas_planning.py`:

```python
def test_the_config_schemas_belong_to_no_stage():
    """A config kind in STAGE_ARTIFACTS would make validate --stage hunt for it.

    agents.json and gold.json are handed to a subcommand by a person; they never
    live in a run directory, and _artifact_paths has no branch for them -- so a
    stage claiming to produce one would raise KeyError inside layer 1.
    """
    produced = {kind for kinds in STAGE_ARTIFACTS.values() for kind in kinds}
    assert produced.isdisjoint({"agents", "gold"})
    assert produced <= set(ARTIFACT_SCHEMAS)


def test_every_registered_schema_compiles():
    for kind in ARTIFACT_SCHEMAS:
        assert _validator_for(kind, schema_dir()) is not None
```

Adapt the second to whatever the existing file already does for schema compilation — if it already loops over `ARTIFACT_SCHEMAS`, the new entries are covered and only the first test is new.

- [ ] **Step 5: Write the failing tests for roster loading**

Create `tests/unit/test_smoke_config.py`:

```python
"""The agent roster boundary: loading, substitution, and the preflight.

Everything about smoke that does not touch a subprocess. A malformed roster is a
usage error rather than a finding, which is the one place in the project where a
schema failure does not become exit 1: a person wrote this file, so there is no
stage to send a repair prompt to.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from testgen.errors import UsageError
from testgen.smoke import REQUIRED_ROLES, ROLES, AgentSpec, load_agents, preflight, substitute
from tests.builders import minimal_agents


def _roster(tmp_path, payload=None):
    path = tmp_path / "agents.json"
    path.write_text(json.dumps(payload if payload is not None else minimal_agents()), "utf-8")
    return path


# -- load_agents --------------------------------------------------------------


def test_a_valid_roster_loads_all_three_roles(tmp_path):
    specs = load_agents(_roster(tmp_path))
    assert [s.role for s in specs] == list(ROLES)
    assert specs[0].command == ("true",)
    assert specs[0].notes == "no tools"


def test_the_agent_timeout_defaults_to_the_one_the_package_declares(tmp_path):
    """emit writes AGENT_TIMEOUT_SEC into task.toml for Harbor.

    Using a different default here would mean a package that times out locally
    does not time out on the platform, or the reverse -- the same suite scoring
    two ways depending on who ran it.
    """
    from testgen.emit import AGENT_TIMEOUT_SEC

    assert load_agents(_roster(tmp_path))[0].timeout_sec == AGENT_TIMEOUT_SEC


def test_an_explicit_timeout_wins(tmp_path):
    payload = minimal_agents()
    payload["agents"][0]["timeout_sec"] = 12.5
    assert load_agents(_roster(tmp_path, payload))[0].timeout_sec == 12.5


def test_an_absent_roster_is_a_usage_error(tmp_path):
    with pytest.raises(UsageError, match="unusable agent roster"):
        load_agents(tmp_path / "nope.json")


def test_a_roster_that_fails_the_schema_is_a_usage_error(tmp_path):
    payload = minimal_agents()
    payload["agents"][0]["role"] = "sidekick"
    with pytest.raises(UsageError, match="sidekick"):
        load_agents(_roster(tmp_path, payload))


def test_a_roster_with_an_empty_executable_is_a_usage_error(tmp_path):
    payload = minimal_agents()
    payload["agents"][0]["command"] = ["", "--flag"]
    with pytest.raises(UsageError):
        load_agents(_roster(tmp_path, payload))


def test_a_duplicated_role_is_a_usage_error(tmp_path):
    """Two under_test agents make mean_reward_by_role ambiguous.

    The schema cannot express it: uniqueItems compares whole objects, and two
    entries differing only by model are distinct objects.
    """
    payload = minimal_agents()
    payload["agents"].append({"role": "under_test", "model": "other", "command": ["true"]})
    with pytest.raises(UsageError, match="under_test"):
        load_agents(_roster(tmp_path, payload))


def test_a_roster_missing_a_required_role_still_loads(tmp_path):
    """Deliberately not a usage error.

    Dropping the oracle is a cost decision a person is allowed to make, and the
    run still produces real data. smoke reports it as a finding and refuses to
    call the result healthy -- exit 1 with the data, not exit 2 with nothing.
    """
    payload = minimal_agents()
    payload["agents"] = [a for a in payload["agents"] if a["role"] != "oracle"]
    specs = load_agents(_roster(tmp_path, payload))
    assert "oracle" not in {s.role for s in specs}
    assert "oracle" in REQUIRED_ROLES


# -- substitute ---------------------------------------------------------------


def test_every_placeholder_is_filled():
    argv = substitute(
        ("run", "--task", "{task_dir}", "--logs", "{logs_dir}", "--id", "{scenario_id}"),
        task_dir=Path("/runs/r/06-suite/scn-001"),
        logs_dir=Path("/runs/r/measurement/smoke/oracle/scn-001/agent"),
        scenario_id="scn-001",
    )
    assert argv == (
        "run",
        "--task",
        "/runs/r/06-suite/scn-001",
        "--logs",
        "/runs/r/measurement/smoke/oracle/scn-001/agent",
        "--id",
        "scn-001",
    )


def test_a_literal_brace_survives():
    """str.replace, not str.format.

    A JSON snippet passed as a flag value is an ordinary thing to put in an argv,
    and str.format raises KeyError or ValueError on it. A roster that works from a
    shell must not break because one argument held a brace.
    """
    argv = substitute(
        ("run", '--extra={"temperature": 0}', "{scenario_id}"),
        task_dir=Path("/t"),
        logs_dir=Path("/l"),
        scenario_id="scn-001",
    )
    assert argv == ("run", '--extra={"temperature": 0}', "scn-001")


def test_an_unknown_placeholder_is_left_alone():
    """It may mean something to the command itself; guessing would corrupt it."""
    assert substitute(
        ("run", "{model}"), task_dir=Path("/t"), logs_dir=Path("/l"), scenario_id="s"
    ) == ("run", "{model}")


def test_a_placeholder_appearing_twice_is_filled_twice():
    assert substitute(
        ("{scenario_id}", "{scenario_id}-out"),
        task_dir=Path("/t"),
        logs_dir=Path("/l"),
        scenario_id="s",
    ) == ("s", "s-out")


# -- preflight ----------------------------------------------------------------


def test_preflight_resolves_the_executable_to_an_absolute_path():
    """run_agent sets cwd to the task directory.

    A relative command that resolved from the repository root would not exist by
    the time it ran, so the resolved path is substituted back into command[0].
    """
    spec = AgentSpec(role="under_test", model="m", command=("true", "--x"))
    resolved = preflight((spec,))[0]
    assert Path(resolved.command[0]).is_absolute()
    assert Path(resolved.command[0]).resolve() == Path(shutil.which("true")).resolve()
    assert resolved.command[1:] == ("--x",)


def test_preflight_refuses_a_command_that_cannot_run():
    """Before anything runs, not on task 5 of 8.

    Discovering the typo mid-run wastes every agent invocation before it and
    leaves a half-populated report on disk.
    """
    spec = AgentSpec(role="oracle", model="m", command=("definitely-not-a-real-binary-xyz",))
    with pytest.raises(UsageError, match="not runnable"):
        preflight((spec,))


def test_preflight_names_the_role_that_is_broken():
    specs = (
        AgentSpec(role="weak_baseline", model="m", command=("true",)),
        AgentSpec(role="oracle", model="m", command=("nope-xyz",)),
    )
    with pytest.raises(UsageError, match="oracle"):
        preflight(specs)
```

- [ ] **Step 6: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_smoke_config.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'testgen.smoke'`

- [ ] **Step 7: Write `smoke.py`'s config half**

Create `src/testgen/smoke.py`:

```python
"""Stage 7: run the emitted suite against three agents and report the spread.

Design spec section 7. The suite is scored three ways -- by a weak baseline that
should fail nearly everything, by the agent under test, and by an oracle handed
the reference answer that should pass nearly everything -- because a single
average hides every way a suite can be worthless. A weak baseline that scores
well means the tests are trivial. An oracle that scores badly means the gold
labels or the verifier are broken, **not** the agent. That third run is a test of
the test suite, and it is the cheapest one here.

This module has exactly two seams onto the outside world, and nothing else in the
project has any: an agent command per role, and the emitted package's *own*
tests/verify.py. Everything between them is pure functions over JSON, which is
what makes the thresholds, the flags and the verdict testable without a
container, a network, or an LLM call.

**Precondition: emit must have run.** This module reads emitted packages, which
nothing orders `validate --stage emit` before, so it uses `.get()` on their
contents rather than indexing directly -- the same exception refs.check_suite
documents. It indexes `manifest.json` directly, because that is a gated stage
output.
"""

from __future__ import annotations

import dataclasses
import math
import shutil
from dataclasses import dataclass
from pathlib import Path

from testgen.artifacts import read_json
from testgen.emit import AGENT_TIMEOUT_SEC, VERIFIER_TIMEOUT_SEC
from testgen.errors import UsageError
from testgen.findings import Finding, format_findings
from testgen.paths import RunPaths
from testgen.validate import validate_artifact

# Pipeline order, and the order the report lists agents in.
ROLES = ("weak_baseline", "under_test", "oracle")

# A roster missing either of these cannot be judged healthy. The weak baseline is
# what detects a trivial suite and the oracle is what detects broken labels, so
# without them the run measures a spread against nothing.
REQUIRED_ROLES = ("weak_baseline", "oracle")

_PLACEHOLDERS = ("task_dir", "logs_dir", "scenario_id")


@dataclass(frozen=True)
class AgentSpec:
    """One role's agent, as the roster declares it."""

    role: str
    model: str
    command: tuple[str, ...]
    timeout_sec: float = AGENT_TIMEOUT_SEC
    notes: str = ""


def load_agents(path: Path | str) -> tuple[AgentSpec, ...]:
    """Read and schema-validate the roster. -> the specs in ROLES order.

    A malformed roster raises UsageError, which cli.py maps to exit 2. That is
    deliberate and it is the one place in the project where a schema failure does
    not become exit 1: a person wrote this file, so there is no stage to hand a
    repair prompt to, and telling an orchestrator to re-run a stage would not fix
    a typo in a path.

    A missing REQUIRED_ROLE is *not* checked here. Dropping the oracle is a cost
    decision a human is allowed to make, and the run still produces real data --
    so smoke_run reports it as a finding and refuses to call the result healthy,
    rather than refusing to run.
    """
    findings = validate_artifact(Path(path), "agents")
    if findings:
        raise UsageError(f"unusable agent roster:\n{format_findings(findings)}")
    roster = read_json(path)
    specs = [
        AgentSpec(
            role=entry["role"],
            model=entry["model"],
            command=tuple(entry["command"]),
            timeout_sec=float(entry.get("timeout_sec", AGENT_TIMEOUT_SEC)),
            notes=entry.get("notes", ""),
        )
        for entry in roster["agents"]
    ]
    roles = [spec.role for spec in specs]
    duplicates = sorted({role for role in roles if roles.count(role) > 1})
    if duplicates:
        # The schema cannot express this: uniqueItems compares whole objects, and
        # two entries differing only by model are distinct objects. Two agents in
        # one role make mean_reward_by_role ambiguous.
        raise UsageError(
            f"agent roster declares {', '.join(duplicates)} more than once; one agent per role"
        )
    return tuple(sorted(specs, key=lambda spec: ROLES.index(spec.role)))


def substitute(
    command: tuple[str, ...], *, task_dir: Path, logs_dir: Path, scenario_id: str
) -> tuple[str, ...]:
    """Fill {task_dir}, {logs_dir} and {scenario_id} in every argv element.

    str.replace rather than str.format. An argv element may legitimately contain a
    literal brace -- a JSON snippet passed as a flag value is the obvious case --
    and str.format raises KeyError or ValueError on it, so a roster that works
    from a shell would break because one argument held a `{`.

    An unrecognised placeholder is left as written rather than emptied: it may
    mean something to the command itself, and substituting a guess would corrupt
    an argument that was correct.
    """
    values = {
        "task_dir": str(task_dir),
        "logs_dir": str(logs_dir),
        "scenario_id": scenario_id,
    }
    filled = []
    for element in command:
        for name in _PLACEHOLDERS:
            element = element.replace("{" + name + "}", values[name])
        filled.append(element)
    return tuple(filled)


def preflight(specs: tuple[AgentSpec, ...]) -> tuple[AgentSpec, ...]:
    """Resolve each role's executable to an absolute path, or refuse the roster.

    Two jobs, both load-bearing.

    Resolving: run_agent sets cwd to the task directory, so a relative
    `./my-agent` that resolved from the repository root would not exist by the
    time it ran. The resolved absolute path goes back into command[0], so cwd
    cannot change which binary runs.

    Refusing early: discovering a typo'd command on task 5 of 8 wastes the twelve
    agent invocations before it and leaves a half-populated report on disk.
    shutil.which handles both a bare name on PATH and a name with a directory
    component, and requires the executable bit either way.
    """
    resolved = []
    for spec in specs:
        found = shutil.which(spec.command[0])
        if found is None:
            raise UsageError(
                f"agent role {spec.role!r} names an executable that is not runnable: "
                f"{spec.command[0]!r}"
            )
        resolved.append(
            dataclasses.replace(spec, command=(str(Path(found).resolve()), *spec.command[1:]))
        )
    return tuple(resolved)
```

`math` is imported for Task 6 and will be flagged as unused by ruff until then — add it in Task 6 instead, not here.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_smoke_config.py tests/unit/test_schemas_planning.py -q`
Expected: PASS

- [ ] **Step 9: Run the whole suite and gather mutation evidence**

Run: `uv run pytest -q` and `uv run ruff check . && uv run ruff format --check .`

```bash
export PYTHONDONTWRITEBYTECODE=1
```

| Deleted | Named test that must fail |
|---|---|
| the `if findings: raise` in `load_agents` | `test_a_roster_that_fails_the_schema_is_a_usage_error` |
| the duplicate-role check | `test_a_duplicated_role_is_a_usage_error` |
| `prefixItems` from the schema's `command` | `test_a_roster_with_an_empty_executable_is_a_usage_error` |
| the `sorted(..., key=ROLES.index)` on the return | `test_a_valid_roster_loads_all_three_roles` (reorder the builder's agents to confirm) |
| the `dataclasses.replace` in `preflight` | `test_preflight_resolves_the_executable_to_an_absolute_path` |
| the `if found is None: raise` | `test_preflight_refuses_a_command_that_cannot_run` |

If the fourth does not fail, the builder already lists the roles in `ROLES` order and the sort is untested — reorder `minimal_agents` so `oracle` comes first and keep it that way.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -S -s -m "feat: Add the smoke agent roster, its schema, and the preflight

The human-authored boundary for stage 7: three roles, an argv command each, and
placeholder substitution by str.replace rather than str.format so a literal brace
in an argument cannot break a roster that works from a shell.

A malformed roster is exit 2, not exit 1 -- a person wrote it, so there is no
stage to hand a repair prompt to. A roster missing the oracle still loads: that
is a cost decision, and the run still produces data worth reporting.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 5: The two subprocess seams

Everything in this project that touches the outside world is in this task. `run_agent` invokes one role's command for one package; `verify_package` scores the result by executing **the package's own copied `tests/verify.py`**, not by importing the library.

That distinction is the whole of layer 3. The question stage 7 answers is *does the emitted suite actually execute* — so a `verify.py` that `emit` mangled on the way into the package has to fail here. Importing the tested original would answer a different, easier question. The verifier runs under `python -S` with a scrubbed environment, which gives it exactly the stdlib and nothing else: an accidental `import testgen` fails the way it would in a bare `ubi9` image instead of resolving out of the dev tree.

**Files:**
- Modify: `src/testgen/smoke.py`
- Test: `tests/unit/test_smoke_subprocess.py` (create)

**Interfaces:**
- Produces: `smoke.run_agent(spec, *, task_dir, logs_dir, stderr_path, scenario_id) -> tuple[int | None, str]`; `smoke.verify_package(task_dir, *, agent_logs, out_dir, stderr_path, timeout_sec=VERIFIER_TIMEOUT_SEC) -> tuple[int | None, dict | None, str]`; `smoke.verifier_argv(...)`; `smoke.scrubbed_env() -> dict[str, str]`.
- Consumes: `AgentSpec` and `substitute` from Task 4; `VERIFIER_TIMEOUT_SEC` from `emit`.
- Contract: a returncode of `None` means "timed out". A `reward` of `None` means "not scoreable", which the report records as `scored: false` — **never as `0.0`**.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_smoke_subprocess.py`:

```python
"""The two seams onto the outside world, exercised against real subprocesses.

No mocking. A mocked subprocess proves the call was formed, not that the thing on
the other end behaves -- and the properties that matter here are all about the
other end: that a timeout leaves a partial transcript, that stderr never reaches
the transcript reader, and that the verifier that runs is the copied one under an
import surface it would have in the container.
"""

from __future__ import annotations

import json
import sys

from testgen.emit import emit_run
from testgen.smoke import AgentSpec, run_agent, scrubbed_env, verify_package
from tests.unit.test_refs_states import build_state

SID = "scn-001"

COMPETENT = """\
import json, sys
print(json.dumps({"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "query_aap2",
     "input": {"action": "find_jobs", "controller": "prod0"}}]}}))
print(json.dumps({"type": "result", "subtype": "success",
                  "result": "Job 90420 failed on prod0."}))
"""

TOOLLESS = """\
import json
print(json.dumps({"type": "result", "subtype": "success", "result": "I am not sure."}))
"""


def _script(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def _spec(script, role="under_test", timeout_sec=60.0):
    return AgentSpec(
        role=role, model="m", command=(sys.executable, str(script)), timeout_sec=timeout_sec
    )


def _emitted(tmp_path):
    run = build_state(tmp_path / "run", "challenge")
    emitted, findings = emit_run(run)
    assert (emitted, findings) == ([SID], []), findings
    return run


def _paths(run, role="under_test"):
    base = run.smoke_dir(role, SID)
    return base / "agent", base / "verifier", base


# -- run_agent ---------------------------------------------------------------


def test_the_commands_stdout_lands_in_the_agent_log_directory(tmp_path):
    """A runner that streams stream-json to stdout needs no wrapper."""
    run = _emitted(tmp_path)
    logs, _, base = _paths(run)
    code, note = run_agent(
        _spec(_script(tmp_path, "a.py", COMPETENT)),
        task_dir=run.task_dir(SID),
        logs_dir=logs,
        stderr_path=base / "agent-stderr.txt",
        scenario_id=SID,
    )
    assert (code, note) == (0, "")
    events = [json.loads(line) for line in (logs / "agent-stdout.jsonl").read_text().splitlines()]
    assert [e["type"] for e in events] == ["assistant", "result"]


def test_stderr_lands_outside_the_agent_log_directory(tmp_path):
    """verify.py globs *.jsonl and *.txt in the agent log directory.

    A warning line written inside it would be read back as transcript input -- and
    a diagnostic that happened to quote the reference answer would then satisfy an
    answer_contains assertion the agent never earned.
    """
    run = _emitted(tmp_path)
    logs, _, base = _paths(run)
    noisy = _script(tmp_path, "n.py", 'import sys\nsys.stderr.write("Job 90420 failed\\n")\n')
    run_agent(
        _spec(noisy),
        task_dir=run.task_dir(SID),
        logs_dir=logs,
        stderr_path=base / "agent-stderr.txt",
        scenario_id=SID,
    )
    assert "90420" in (base / "agent-stderr.txt").read_text()
    assert not list(logs.glob("*.txt"))
    assert "90420" not in (logs / "agent-stdout.jsonl").read_text()


def test_a_nonzero_exit_is_reported_but_the_transcript_is_kept(tmp_path):
    run = _emitted(tmp_path)
    logs, _, base = _paths(run)
    body = COMPETENT + "raise SystemExit(3)\n"
    code, note = run_agent(
        _spec(_script(tmp_path, "e.py", body)),
        task_dir=run.task_dir(SID),
        logs_dir=logs,
        stderr_path=base / "agent-stderr.txt",
        scenario_id=SID,
    )
    assert code == 3
    assert "exited 3" in note
    assert "90420" in (logs / "agent-stdout.jsonl").read_text()


def test_a_timeout_keeps_whatever_the_agent_had_already_written(tmp_path):
    """A timeout is a result, not an error.

    Killing the whole smoke run because one agent hung would discard the other
    roles' data on every remaining task -- the comparison the run exists to make.
    And a partial transcript still scores, so it is written out.
    """
    run = _emitted(tmp_path)
    logs, _, base = _paths(run)
    body = COMPETENT + "import sys, time\nsys.stdout.flush()\ntime.sleep(30)\n"
    code, note = run_agent(
        _spec(_script(tmp_path, "slow.py", body), timeout_sec=1.5),
        task_dir=run.task_dir(SID),
        logs_dir=logs,
        stderr_path=base / "agent-stderr.txt",
        scenario_id=SID,
    )
    assert code is None
    assert "timed out" in note
    assert "90420" in (logs / "agent-stdout.jsonl").read_text()


def test_the_agent_runs_with_the_task_directory_as_its_cwd(tmp_path):
    run = _emitted(tmp_path)
    logs, _, base = _paths(run)
    body = 'import os, json\nprint(json.dumps({"type": "result", "result": os.getcwd()}))\n'
    run_agent(
        _spec(_script(tmp_path, "cwd.py", body)),
        task_dir=run.task_dir(SID),
        logs_dir=logs,
        stderr_path=base / "agent-stderr.txt",
        scenario_id=SID,
    )
    written = json.loads((logs / "agent-stdout.jsonl").read_text())["result"]
    assert written == str(run.task_dir(SID).resolve())


# -- verify_package ----------------------------------------------------------


def _score(run, agent_body, tmp_path, name):
    logs, out, base = _paths(run)
    run_agent(
        _spec(_script(tmp_path, name, agent_body)),
        task_dir=run.task_dir(SID),
        logs_dir=logs,
        stderr_path=base / "agent-stderr.txt",
        scenario_id=SID,
    )
    return verify_package(
        run.task_dir(SID),
        agent_logs=logs,
        out_dir=out,
        stderr_path=base / "verifier-stderr.txt",
    )


def test_a_competent_run_scores_one(tmp_path):
    run = _emitted(tmp_path)
    code, reward, note = _score(run, COMPETENT, tmp_path, "good.py")
    assert (code, note) == (0, "")
    assert reward["reward"] == 1.0


def test_a_toolless_run_scores_zero(tmp_path):
    """The suite has to discriminate, or none of the rest of this means anything."""
    run = _emitted(tmp_path)
    _, reward, _ = _score(run, TOOLLESS, tmp_path, "weak.py")
    assert reward["reward"] == 0.0
    assert reward["completion"] == 1.0, "it answered; the answer was wrong"


def test_the_verifier_that_runs_is_the_copied_one(tmp_path):
    """Layer 3's actual question.

    Importing testgen.suite.verify would answer whether the *tested* verifier
    works. Mangling the copy has to be visible, or emit could ship a broken
    verifier into every package and the smoke gate would pass.
    """
    run = _emitted(tmp_path)
    (run.task_dir(SID) / "tests" / "verify.py").write_text("raise SystemExit(9)\n", "utf-8")
    code, reward, note = _score(run, COMPETENT, tmp_path, "good2.py")
    assert reward is None, "an unrunnable verifier must not produce a score"
    assert code == 9


def test_a_verifier_that_imports_testgen_fails_as_it_would_in_the_container(tmp_path):
    """The scrub is what makes the stdlib-only constraint enforced by something.

    Under the dev interpreter testgen is importable, so without -S and a cleared
    PYTHONPATH a verifier that quietly grew a testgen import would pass here and
    fail in a bare ubi9 image -- discovered on the platform, not in CI.
    """
    run = _emitted(tmp_path)
    verify_py = run.task_dir(SID) / "tests" / "verify.py"
    verify_py.write_text("import testgen\n" + verify_py.read_text(), encoding="utf-8")
    _, reward, _ = _score(run, COMPETENT, tmp_path, "good3.py")
    assert reward is None


def test_the_stdlib_is_still_reachable_under_the_scrub(tmp_path):
    """The other half: the scrub must not be so aggressive it breaks the verifier.

    verify.py imports argparse, json, math, sys and pathlib. If -S removed any of
    those, every task would be unscoreable and the suite would read as broken.
    """
    run = _emitted(tmp_path)
    _, reward, _ = _score(run, COMPETENT, tmp_path, "good4.py")
    assert reward is not None
    assert "PYTHONPATH" in scrubbed_env()
    assert scrubbed_env()["PYTHONPATH"] == ""


def test_a_refused_contract_is_unscoreable_and_not_a_zero(tmp_path):
    """verify.py exits 2 and writes no reward.txt.

    Recording that as 0.0 would turn a bypassed authoring gate into a bad agent
    run, which inverts the conclusion the whole three-role design exists to
    support.
    """
    run = _emitted(tmp_path)
    (run.task_dir(SID) / "tests" / "expected.json").write_text('{"contract": "nope"}', "utf-8")
    code, reward, note = _score(run, COMPETENT, tmp_path, "good5.py")
    assert code == 2
    assert reward is None
    assert "contract" in note
    assert not (_paths(run)[1] / "reward.txt").exists()


def test_a_package_with_no_verifier_is_unscoreable(tmp_path):
    run = _emitted(tmp_path)
    (run.task_dir(SID) / "tests" / "verify.py").unlink()
    _, reward, note = _score(run, COMPETENT, tmp_path, "good6.py")
    assert reward is None
    assert "no tests/verify.py" in note


def test_the_verifier_is_invoked_the_way_test_sh_invokes_it(tmp_path):
    """Same three arguments, so a package that scores here scores on the platform."""
    from testgen.smoke import verifier_argv

    run = _emitted(tmp_path)
    argv = verifier_argv(run.task_dir(SID), agent_logs=Path("/logs/agent"), out_dir=Path("/logs/v"))
    assert argv[1] == "-S"
    assert "--expected" in argv and "--agent-logs" in argv and "--out" in argv
    shell = (run.task_dir(SID) / "tests" / "test.sh").read_text()
    for flag in ("--expected", "--agent-logs", "--out"):
        assert flag in shell
```

Add `from pathlib import Path` to the imports.

- [ ] **Step 2: Add `smoke_dir` to `paths.py`**

```python
    @property
    def measurement_dir(self) -> Path:
        """Outputs of the measurement tools, which are not pipeline stages.

        Kept out of the numbered prefixes on purpose: those are the stage
        contract, and STAGES/STAGE_ARTIFACTS must not grow an entry for a tool
        that no orchestrator dispatches.
        """
        return self.root / "measurement"

    def smoke_dir(self, role: str, scenario_id: str) -> Path:
        """Where one (role, task) execution's logs go.

        The `agent/` and `verifier/` children below this mirror Harbor's
        /logs/agent and /logs/verifier, so the verifier is handed the same paths
        it is handed in the container.
        """
        return (
            self.measurement_dir
            / "smoke"
            / safe_segment(role)
            / safe_segment(scenario_id)
        )
```

Add a test to `tests/unit/test_paths.py` that `smoke_dir` refuses an unsafe role and an unsafe scenario id.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_smoke_subprocess.py -q`
Expected: FAIL with `ImportError: cannot import name 'run_agent' from 'testgen.smoke'`

- [ ] **Step 4: Implement the two seams**

Add to `smoke.py` (and add `import json`, `import subprocess`, `import sys` to its imports):

```python
def scrubbed_env() -> dict[str, str]:
    """The environment an emitted verifier runs in.

    PYTHONPATH is emptied and PATH is minimal so that an emitted verifier which
    quietly grew a third-party or testgen import fails here rather than on the
    platform. The interpreter is additionally invoked with -S (see
    verifier_argv), which is what actually removes site-packages: under the dev
    interpreter testgen is installed editable, so clearing PYTHONPATH alone
    leaves it importable and the stdlib-only constraint enforced by nothing.

    PYTHONDONTWRITEBYTECODE keeps __pycache__ out of the emitted package, which
    would otherwise appear in 06-suite/ and be shipped.
    """
    return {"PATH": "/usr/bin:/bin", "PYTHONPATH": "", "PYTHONDONTWRITEBYTECODE": "1"}


def verifier_argv(task_dir: Path, *, agent_logs: Path, out_dir: Path) -> list[str]:
    """The verifier invocation, matching the three arguments test.sh passes.

    Kept in one function so the local invocation and the container's cannot
    drift: a package that scores here has to score there, and the only way to
    keep that true is for the argument list to have one definition.
    """
    return [
        sys.executable,
        "-S",
        str(task_dir / "tests" / "verify.py"),
        "--expected",
        str(task_dir / "tests" / "expected.json"),
        "--agent-logs",
        str(agent_logs),
        "--out",
        str(out_dir),
    ]


def run_agent(
    spec: AgentSpec,
    *,
    task_dir: Path,
    logs_dir: Path,
    stderr_path: Path,
    scenario_id: str,
) -> tuple[int | None, str]:
    """Execute one role's command for one task. -> (returncode, note).

    A returncode of None means the command timed out. The note is empty on a
    clean run and otherwise says what happened, in one clause, for the report.

    The command's own stdout is captured into logs_dir as agent-stdout.jsonl, so
    a runner that streams stream-json to stdout needs no wrapper; a runner that
    writes its own transcript files into logs_dir works too, because verify.py
    concatenates every *.jsonl and *.txt it finds there.

    **stderr goes outside logs_dir on purpose.** verify.py globs *.txt in the
    agent log directory, so a diagnostic written inside it would be read back as
    transcript input -- and a warning line that happened to quote the reference
    answer would satisfy an answer_contains assertion the agent never earned.

    A timeout writes out whatever the command had already produced. A partial
    transcript still scores, and killing the whole smoke run because one agent
    hung would discard every other role's data on every remaining task, which is
    the comparison the run exists to make.
    """
    logs_dir.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    argv = substitute(
        spec.command, task_dir=task_dir, logs_dir=logs_dir, scenario_id=scenario_id
    )
    stdout_path = logs_dir / "agent-stdout.jsonl"
    try:
        completed = subprocess.run(  # noqa: S603 - argv comes from a human-authored roster
            list(argv),
            cwd=task_dir,
            capture_output=True,
            text=True,
            timeout=spec.timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        return None, f"agent timed out after {spec.timeout_sec} s"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        return completed.returncode, f"agent exited {completed.returncode}"
    return 0, ""


def verify_package(
    task_dir: Path,
    *,
    agent_logs: Path,
    out_dir: Path,
    stderr_path: Path,
    timeout_sec: float = VERIFIER_TIMEOUT_SEC,
) -> tuple[int | None, dict | None, str]:
    """Score one task with the package's own verifier. -> (code, reward, note).

    **The copied verify.py, not the library import.** Layer 3 asks whether the
    emitted suite executes, so a verifier that emit mangled on the way into the
    package has to fail here; importing the tested original would answer an
    easier question and let a broken suite through the gate.

    A reward of None means the task is not scoreable for this role, which the
    report records as `scored: false`. It is **never** recorded as 0.0. The
    verifier exits 2 and writes no reward.txt when it refuses a contract it
    cannot read, because that is a bypassed authoring gate rather than a bad
    agent run -- and scoring it zero would invert exactly that conclusion.
    """
    verify_py = task_dir / "tests" / "verify.py"
    if not verify_py.is_file():
        return None, None, "package has no tests/verify.py"
    out_dir.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(  # noqa: S603 - argv is built by verifier_argv
            verifier_argv(task_dir, agent_logs=agent_logs, out_dir=out_dir),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=scrubbed_env(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, None, f"verifier timed out after {timeout_sec} s"
    stderr_path.write_text(completed.stderr, encoding="utf-8")

    reward_path = out_dir / "reward.json"
    if completed.returncode != 0 or not reward_path.is_file():
        return completed.returncode, None, _refusal_note(out_dir, completed)
    try:
        reward = json.loads(reward_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return completed.returncode, None, f"verifier wrote an unreadable reward.json: {exc}"
    if not isinstance(reward, dict):
        return completed.returncode, None, "verifier wrote a reward.json that is not an object"
    return completed.returncode, reward, ""


def _refusal_note(out_dir: Path, completed: subprocess.CompletedProcess) -> str:
    """Why the verifier produced no score, preferring its own stated reason.

    verify.py writes reward-detail.json with an `error` key when it refuses, and
    that message names the contract field that is wrong. Falling back to stderr
    first would report a Python traceback where a one-line diagnosis exists.
    """
    detail = out_dir / "reward-detail.json"
    if detail.is_file():
        try:
            payload = json.loads(detail.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = None
        if isinstance(payload, dict) and payload.get("error"):
            return str(payload["error"])
    tail = (completed.stderr or "").strip().splitlines()
    if tail:
        return f"verifier exited {completed.returncode}: {tail[-1][:200]}"
    return f"verifier exited {completed.returncode} with no diagnostic"
```

Note: the two `# noqa: S603` comments are only needed if the project's ruff config selects `S`. It does not (`select = ["E", "F", "I", "UP", "B", "SIM"]`), so **drop both `noqa` comments** — an unnecessary `noqa` is itself lint debt. Keep the explanatory half of each as an ordinary comment above the call if it reads usefully.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_smoke_subprocess.py -q`
Expected: PASS, 13 tests. If `test_a_verifier_that_imports_testgen_fails_as_it_would_in_the_container` fails, `-S` is not doing its job on this interpreter — investigate rather than deleting the test; it is the only thing enforcing the stdlib-only constraint at runtime.

- [ ] **Step 6: Run the whole suite and gather mutation evidence**

Run: `uv run pytest -q` and `uv run ruff check . && uv run ruff format --check .`

```bash
export PYTHONDONTWRITEBYTECODE=1
```

| Deleted / changed | Named test that must fail |
|---|---|
| the `except TimeoutExpired` stdout write | `test_a_timeout_keeps_whatever_the_agent_had_already_written` |
| `cwd=task_dir` | `test_the_agent_runs_with_the_task_directory_as_its_cwd` |
| move `stderr_path` inside `logs_dir` | `test_stderr_lands_outside_the_agent_log_directory` |
| `env=scrubbed_env()` and `-S` | `test_a_verifier_that_imports_testgen_fails_as_it_would_in_the_container` |
| the `verify_py.is_file()` guard | `test_a_package_with_no_verifier_is_unscoreable` |
| the `returncode != 0` guard in `verify_package` | `test_the_verifier_that_runs_is_the_copied_one` |
| `_refusal_note`'s `reward-detail.json` branch | `test_a_refused_contract_is_unscoreable_and_not_a_zero` |
| replace the copied verifier with a library import | `test_the_verifier_that_runs_is_the_copied_one` |

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -S -s -m "feat: Add smoke's two subprocess seams

run_agent invokes one role's command per package; verify_package scores it by
executing the package's own copied tests/verify.py under python -S with a
scrubbed environment, so an accidental testgen import fails the way it would in
a bare ubi9 image rather than resolving out of the dev tree.

A timeout writes out the partial transcript and reports the role unscoreable for
that task rather than aborting the run. A refused contract stays unscoreable and
never becomes a 0.0: that would report a bypassed authoring gate as a bad agent
run.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 6: Flags, summary, verdict

The pure half of stage 7, and the part that decides whether anyone should believe the numbers. All of it is functions over the report's own `tasks` list, so `refs.check_report` can recompute the whole summary by calling these rather than re-deriving the arithmetic — which is what stops the two sides of that seam from disagreeing.

Two rulings this task encodes, both of the shape §8 warns about (a default silently standing in for a real value):

- **Means are computed over *comparable* tasks only** — the tasks where every declared role produced a score. A role that crashed on the two hardest tasks would otherwise have its mean taken over the six easy ones and compared against another role's mean over all eight. The ragged denominator flatters exactly the role that failed most.
- **An unscoreable task is neither `all_pass` nor `all_fail`.** Counting a missing score as a failure would report a task nobody managed to run as a hard one.

**Files:**
- Modify: `src/testgen/smoke.py`
- Test: `tests/unit/test_smoke_aggregate.py` (create)

**Interfaces:**
- Produces: `PASS_THRESHOLD`, `FAIL_CEILING`, `WEAK_BASELINE_CEILING`, `ORACLE_FLOOR`, `MIN_COMPARABLE_TASKS`; `comparable(task, roles) -> bool`; `task_flags(task, roles) -> tuple[bool, bool]`; `mean_reward_by_role(tasks, roles) -> dict[str, float]`; `summarize(tasks, roles) -> dict`; `verdict_for(tasks, summary, roles) -> str`; `components(reward) -> dict[str, float] | None`.
- Consumes: nothing new. `refs.check_report` (Task 8) calls `task_flags`, `summarize` and `verdict_for` directly.
- A `task` here is a dict with `results: list[dict]`; `roles` is a tuple of role names in `ROLES` order.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_smoke_aggregate.py`:

```python
"""The arithmetic and the verdict: stage 7's pure half.

Nothing here touches a subprocess. The thresholds are named constants because
refs.check_report recomputes every one of these numbers by calling these same
functions -- a second implementation of the arithmetic is the seam defect this
project keeps finding, so there is exactly one.
"""

from __future__ import annotations

import pytest

from testgen.smoke import (
    FAIL_CEILING,
    ORACLE_FLOOR,
    PASS_THRESHOLD,
    ROLES,
    WEAK_BASELINE_CEILING,
    comparable,
    components,
    mean_reward_by_role,
    summarize,
    task_flags,
    verdict_for,
)


def _result(role, reward=None):
    if reward is None:
        return {"role": role, "scored": False}
    return {
        "role": role,
        "scored": True,
        "reward": reward,
        "completion": 1.0,
        "assertions": reward,
        "trajectory": reward,
    }


def _task(sid, **by_role):
    return {"scenario_id": sid, "results": [_result(r, by_role.get(r)) for r in ROLES]}


def _spread(sid):
    return _task(sid, weak_baseline=0.0, under_test=0.8, oracle=1.0)


# -- comparable ---------------------------------------------------------------


def test_a_task_every_role_scored_is_comparable():
    assert comparable(_spread("s1"), ROLES) is True


def test_a_task_one_role_could_not_score_is_not_comparable():
    task = _task("s1", weak_baseline=0.0, under_test=0.8)  # oracle unscoreable
    assert comparable(task, ROLES) is False


# -- task_flags ---------------------------------------------------------------


def test_all_pass_fires_only_when_every_role_passes():
    assert task_flags(_task("s", weak_baseline=1.0, under_test=1.0, oracle=1.0), ROLES) == (
        True,
        False,
    )


def test_all_fail_fires_only_when_every_role_fails():
    assert task_flags(_task("s", weak_baseline=0.0, under_test=0.0, oracle=0.0), ROLES) == (
        False,
        True,
    )


def test_a_real_spread_is_neither():
    assert task_flags(_spread("s"), ROLES) == (False, False)


def test_an_unscoreable_task_is_neither_all_pass_nor_all_fail():
    """The ruling. Counting a missing score as a failure would report a task
    nobody managed to run as a hard one -- and a suite of them as well-designed."""
    task = _task("s", weak_baseline=0.0, under_test=0.0)  # oracle unscoreable
    assert task_flags(task, ROLES) == (False, False)


def test_a_task_with_no_declared_roles_is_neither_all_pass_nor_all_fail():
    """all([]) is True, so an empty reward list would claim both at once.

    Reachable through refs.check_report, which reads a report layer 1 has not
    gated: `agents: []` gives an empty `roles`, comparable() answers True
    vacuously, and without the guard the checker would report that every role
    both passed and failed the same task.
    """
    assert task_flags({"scenario_id": "s", "results": []}, ()) == (False, False)


def test_the_thresholds_absorb_float_slack_and_nothing_more():
    """0.8 * 1.0 + 0.2 * 1.0 is not exactly 1.0 for every weight pair."""
    assert task_flags(_task("s", **dict.fromkeys(ROLES, 0.9999)), ROLES) == (True, False)
    assert task_flags(_task("s", **dict.fromkeys(ROLES, 0.0001)), ROLES) == (False, True)
    assert task_flags(_task("s", **dict.fromkeys(ROLES, 0.99)), ROLES) == (False, False)
    assert PASS_THRESHOLD < 1.0 and FAIL_CEILING > 0.0


# -- mean_reward_by_role -----------------------------------------------------


def test_the_mean_is_taken_over_comparable_tasks_only():
    """The ragged-denominator ruling.

    Task s2 is unscoreable for the oracle. Averaging weak_baseline over both
    tasks and oracle over one compares a role's score on everything against
    another's on the subset it survived -- which flatters the role that failed.
    """
    tasks = [
        _task("s1", weak_baseline=0.0, under_test=0.5, oracle=1.0),
        _task("s2", weak_baseline=1.0, under_test=1.0),
    ]
    means = mean_reward_by_role(tasks, ROLES)
    assert means == {"weak_baseline": 0.0, "under_test": 0.5, "oracle": 1.0}


def test_a_role_with_no_comparable_task_is_omitted_not_zeroed():
    """0.0 would read as "scored zero" rather than "never measured"."""
    tasks = [_task("s1", weak_baseline=0.0, under_test=0.5)]
    assert mean_reward_by_role(tasks, ROLES) == {}


def test_a_role_absent_from_the_roster_is_not_invented():
    tasks = [
        {
            "scenario_id": "s1",
            "results": [_result("weak_baseline", 0.0), _result("under_test", 1.0)],
        }
    ]
    means = mean_reward_by_role(tasks, ("weak_baseline", "under_test"))
    assert set(means) == {"weak_baseline", "under_test"}


# -- summarize ---------------------------------------------------------------


def test_the_summary_counts_what_the_schema_requires():
    tasks = [_spread("s1"), _task("s2", weak_baseline=1.0, under_test=1.0, oracle=1.0)]
    summary = summarize(tasks, ROLES)
    assert summary["all_pass_tasks"] == 1
    assert summary["all_fail_tasks"] == 0
    assert summary["oracle_failures"] == 0
    assert summary["unscoreable"] == 0
    assert set(summary) == {
        "mean_reward_by_role",
        "all_pass_tasks",
        "all_fail_tasks",
        "oracle_failures",
        "unscoreable",
    }


def test_an_unscoreable_oracle_counts_as_an_oracle_failure():
    """A verifier that refused the contract is as much a signal that the suite is
    broken as an oracle that answered wrongly. Both indict the suite, not the
    agent, which is the only thing oracle_failures is for."""
    summary = summarize([_task("s1", weak_baseline=0.0, under_test=0.8)], ROLES)
    assert summary["oracle_failures"] == 1
    assert summary["unscoreable"] == 1


def test_a_low_scoring_oracle_counts_as_an_oracle_failure():
    summary = summarize([_task("s1", weak_baseline=0.0, under_test=0.8, oracle=0.5)], ROLES)
    assert summary["oracle_failures"] == 1


# -- verdict_for -------------------------------------------------------------


def _verdict(tasks, roles=ROLES):
    return verdict_for(tasks, summarize(tasks, roles), roles)


def test_a_real_spread_is_healthy():
    assert _verdict([_spread("s1")]) == "healthy"


def test_a_weak_baseline_that_passes_too_much_is_degenerate():
    assert _verdict([_task("s1", weak_baseline=1.0, under_test=1.0, oracle=1.0)]) == (
        "degenerate_trivial"
    )


def test_an_oracle_that_fails_too_much_indicts_the_labels():
    assert _verdict([_task("s1", weak_baseline=0.0, under_test=0.0, oracle=0.0)]) == (
        "broken_labels"
    )


def test_broken_labels_outranks_degenerate_trivial():
    """The precedence, and the reason for it.

    If the oracle cannot pass its own reference answers, nothing the weak
    baseline scored means anything yet -- the scoring path is what is broken.
    Reporting degenerate_trivial first would send someone to rewrite scenarios.
    """
    tasks = [_task("s1", weak_baseline=1.0, under_test=1.0, oracle=0.0)]
    assert _verdict(tasks) == "broken_labels"


def test_no_comparable_task_is_inconclusive():
    assert _verdict([_task("s1", weak_baseline=0.0, under_test=0.8)]) == "inconclusive"


def test_a_roster_without_the_oracle_cannot_be_healthy():
    """Even when every score looks perfect.

    The oracle is the test of the test suite. Without it there is nothing to rule
    out broken labels, so `healthy` would be a claim the run did not earn.
    """
    roles = ("weak_baseline", "under_test")
    tasks = [
        {
            "scenario_id": "s1",
            "results": [_result("weak_baseline", 0.0), _result("under_test", 1.0)],
        }
    ]
    assert verdict_for(tasks, summarize(tasks, roles), roles) == "inconclusive"


def test_the_thresholds_are_the_documented_ones():
    """Pins the numbers, so changing one is a deliberate edit with a failing test."""
    assert (WEAK_BASELINE_CEILING, ORACLE_FLOOR) == (0.30, 0.80)


# -- components --------------------------------------------------------------


@pytest.mark.parametrize(
    "reward",
    [
        {"reward": 1.5, "completion": 1.0, "assertions": 1.0, "trajectory": 1.0},
        {"reward": -0.1, "completion": 1.0, "assertions": 1.0, "trajectory": 1.0},
        {"reward": "1.0", "completion": 1.0, "assertions": 1.0, "trajectory": 1.0},
        {"reward": True, "completion": 1.0, "assertions": 1.0, "trajectory": 1.0},
        {"reward": float("nan"), "completion": 1.0, "assertions": 1.0, "trajectory": 1.0},
        {"reward": 1.0, "completion": 1.0, "assertions": 1.0},
    ],
)
def test_an_out_of_range_reward_is_rejected_rather_than_written(reward):
    """report-0.1.json bounds every one of these to [0, 1].

    Writing an out-of-range value would make `validate --stage smoke` fail on an
    artifact smoke itself produced -- a stage defect wearing a layer-1 error's
    clothes, and the orchestrator would retry the stage that is not at fault.
    """
    assert components(reward) is None


def test_a_well_formed_reward_is_accepted():
    assert components(
        {"reward": 0.8, "completion": 1, "assertions": 1.0, "trajectory": 0.0}
    ) == {"reward": 0.8, "completion": 1.0, "assertions": 1.0, "trajectory": 0.0}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_smoke_aggregate.py -q`
Expected: FAIL with `ImportError: cannot import name 'comparable' from 'testgen.smoke'`

- [ ] **Step 3: Implement the constants and the pure functions**

Add `import math` to `smoke.py`, then:

```python
# A task "passes" for a role at or above PASS_THRESHOLD and "fails" at or below
# FAIL_CEILING. Both absorb float slack and nothing more: a weight pair summing
# to 1.0 in exact arithmetic does not always sum to 1.0 in IEEE 754, so a
# perfectly correct run can score 0.9999999999999999.
PASS_THRESHOLD = 0.999
FAIL_CEILING = 0.001

# Above this, the weak baseline is passing too much and the suite is not testing
# anything. Below the floor, the oracle cannot pass its own reference answers and
# the labels or the verifier are broken -- not the agent.
WEAK_BASELINE_CEILING = 0.30
ORACLE_FLOOR = 0.80

# Fewer comparable tasks than this and the verdict is inconclusive. One, not a
# larger number: the first slice caps the suite at ~8 scenarios, so any larger
# floor would make a slice-1 run inconclusive by construction and the degenerate
# flags would never get a chance to fire. The flags do the real work; this only
# stops a verdict being pronounced over nothing.
MIN_COMPARABLE_TASKS = 1

_COMPONENTS = ("reward", "completion", "assertions", "trajectory")


def components(reward: dict) -> dict[str, float] | None:
    """The four fractions from a verifier's reward.json, or None if unusable.

    report-0.1.json bounds every one of these to [0, 1], so an out-of-range value
    cannot go into the report: writing it would make `validate --stage smoke`
    fail on an artifact smoke itself produced, and the orchestrator would retry
    the stage that is not at fault.

    Booleans are excluded because True is not a reward, and non-finite values
    because json.loads accepts NaN and Infinity as bare tokens. verify.py's
    _contract_problems normally prevents all of this; this is the check that the
    *copied* verifier still honoured it.
    """
    values: dict[str, float] = {}
    for key in _COMPONENTS:
        value = reward.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            return None
        values[key] = float(value)
    return values


def _scored(result: dict) -> bool:
    return bool(result.get("scored"))


def comparable(task: dict, roles: tuple[str, ...]) -> bool:
    """Whether every declared role produced a score for this task.

    Means and flags are computed over comparable tasks only. A role that failed
    to run on the two hardest tasks would otherwise have its mean taken over the
    six easy ones and compared against another role's mean over all eight -- the
    ragged-denominator mistake, which flatters exactly the role that crashed most.
    """
    scored = {result["role"] for result in task["results"] if _scored(result)}
    return set(roles) <= scored


def task_flags(task: dict, roles: tuple[str, ...]) -> tuple[bool, bool]:
    """(all_pass, all_fail) for one task.

    Both are False for a task that is not comparable. Counting an unscoreable
    result as a failure would report a task nobody managed to run as a hard one,
    and a suite full of them as well-designed -- the same "default silently
    substituting for a real value" shape that produced every plan defect in the
    previous build.
    """
    if not comparable(task, roles):
        return False, False
    rewards = [r["reward"] for r in task["results"] if r["role"] in set(roles) and _scored(r)]
    if not rewards:
        # `all([])` is True, so an empty reward list would report both flags at
        # once -- "every role passed" and "every role failed" about the same task.
        # Reachable through check_report, which reads reports layer 1 has not
        # gated: a report with `agents: []` gives an empty `roles`, comparable()
        # answers True vacuously, and this is what stops the vacuum from becoming
        # two contradictory claims. It is the same empty-means-full-marks trap
        # compute_reward's docstring names at the scoring seam.
        return False, False
    return (
        all(value >= PASS_THRESHOLD for value in rewards),
        all(value <= FAIL_CEILING for value in rewards),
    )


def mean_reward_by_role(tasks: list[dict], roles: tuple[str, ...]) -> dict[str, float]:
    """Mean reward per role, over comparable tasks only.

    A role with no comparable task is omitted rather than reported as 0.0, which
    would read as "scored zero" instead of "never measured". report-0.1.json
    permits the omission for exactly that reason.
    """
    usable = [task for task in tasks if comparable(task, roles)]
    means: dict[str, float] = {}
    for role in roles:
        rewards = [
            result["reward"]
            for task in usable
            for result in task["results"]
            if result["role"] == role and _scored(result)
        ]
        if rewards:
            means[role] = round(sum(rewards) / len(rewards), 6)
    return means


def summarize(tasks: list[dict], roles: tuple[str, ...]) -> dict:
    """The report's summary block, recomputed from nothing but `tasks`.

    refs.check_report calls this rather than re-deriving the arithmetic, so the
    producer and the checker cannot disagree about what the numbers mean.

    An *unscoreable* oracle counts as an oracle failure alongside a low-scoring
    one. Both say the suite is broken rather than the agent, which is the only
    thing oracle_failures is for: a verifier that refused the contract is as much
    a broken-labels signal as an oracle that answered wrongly.
    """
    flags = [task_flags(task, roles) for task in tasks]
    oracle_failures = 0
    unscoreable = 0
    for task in tasks:
        for result in task["results"]:
            if not _scored(result):
                unscoreable += 1
            if result["role"] == "oracle" and (
                not _scored(result) or result["reward"] < PASS_THRESHOLD
            ):
                oracle_failures += 1
    return {
        "mean_reward_by_role": mean_reward_by_role(tasks, roles),
        "all_pass_tasks": sum(1 for all_pass, _ in flags if all_pass),
        "all_fail_tasks": sum(1 for _, all_fail in flags if all_fail),
        "oracle_failures": oracle_failures,
        "unscoreable": unscoreable,
    }


def verdict_for(tasks: list[dict], summary: dict, roles: tuple[str, ...]) -> str:
    """The report's headline, in a fixed precedence.

    The order is the point. `broken_labels` outranks `degenerate_trivial`,
    because if the oracle cannot pass its own reference answers then neither the
    labels nor the verifier can be trusted and nothing the weak baseline scored
    means anything yet. Reporting degenerate_trivial first would send someone to
    rewrite scenarios when the scoring path is what is broken.

    A roster missing a REQUIRED_ROLE is inconclusive even when every score looks
    perfect: `healthy` would be a claim about a spread the run did not measure.
    """
    if set(REQUIRED_ROLES) - set(roles):
        return "inconclusive"
    if sum(1 for task in tasks if comparable(task, roles)) < MIN_COMPARABLE_TASKS:
        return "inconclusive"
    means = summary["mean_reward_by_role"]
    if means.get("oracle", 0.0) < ORACLE_FLOOR:
        return "broken_labels"
    if means.get("weak_baseline", 0.0) > WEAK_BASELINE_CEILING:
        return "degenerate_trivial"
    return "healthy"
```

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest tests/unit/test_smoke_aggregate.py -q`
Expected: PASS

- [ ] **Step 5: Run the whole suite and gather mutation evidence**

Run: `uv run pytest -q` and `uv run ruff check . && uv run ruff format --check .`

```bash
export PYTHONDONTWRITEBYTECODE=1
```

| Deleted / changed | Named test that must fail |
|---|---|
| the `if not comparable` guard in `task_flags` | `test_an_unscoreable_task_is_neither_all_pass_nor_all_fail` |
| the `if not rewards` guard in `task_flags` | `test_a_task_with_no_declared_roles_is_neither_all_pass_nor_all_fail` |
| the `usable` filter in `mean_reward_by_role` | `test_the_mean_is_taken_over_comparable_tasks_only` |
| the `if rewards:` guard (report 0.0 instead) | `test_a_role_with_no_comparable_task_is_omitted_not_zeroed` |
| the `not _scored(result) or` clause in `oracle_failures` | `test_an_unscoreable_oracle_counts_as_an_oracle_failure` |
| swap the `broken_labels` and `degenerate_trivial` branches | `test_broken_labels_outranks_degenerate_trivial` |
| the `REQUIRED_ROLES` branch in `verdict_for` | `test_a_roster_without_the_oracle_cannot_be_healthy` |
| the `MIN_COMPARABLE_TASKS` branch | `test_no_comparable_task_is_inconclusive` |
| the range check in `components` | `test_an_out_of_range_reward_is_rejected_rather_than_written[reward0]` |
| the `isinstance(value, bool)` clause | `test_an_out_of_range_reward_is_rejected_rather_than_written[reward3]` |
| the `math.isfinite` clause | `test_an_out_of_range_reward_is_rejected_rather_than_written[reward4]` |

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -S -s -m "feat: Add smoke's flags, summary and verdict

Two rulings, both of the shape a default silently standing in for a real value.
Means are taken over comparable tasks only, because a ragged denominator flatters
the role that crashed most. An unscoreable task is neither all_pass nor all_fail,
because counting a missing score as a failure reports a task nobody ran as a hard
one.

broken_labels outranks degenerate_trivial: if the oracle cannot pass its own
reference answers, nothing the weak baseline scored means anything yet.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 7: `smoke_run` and the CLI

Wire the three halves together, write `07-report.json`, and expose the subcommand. `smoke` is a gate, not just a reporter: a verdict other than `healthy` is a finding, so exit 1 tells the orchestrator the suite is not fit to trust yet. That is what makes it the third of the three real code gates §8 requires.

**Files:**
- Modify: `src/testgen/smoke.py`
- Modify: `src/testgen/cli.py`
- Test: `tests/unit/test_smoke_run.py` (create), `tests/unit/test_cli.py` (extend)

**Interfaces:**
- Produces: `smoke.smoke_run(run: RunPaths, specs: tuple[AgentSpec, ...]) -> tuple[dict | None, list[Finding]]`.
- Consumes: everything from Tasks 4-6.
- CLI: `testgen smoke --run DIR --agents PATH`. Prints the report path on stdout when a report was written, then any findings. `UsageError` from `load_agents`/`preflight` → exit 2. An absent `manifest.json` → `ArtifactError` → exit 2, because a directory without a manifest is not a run.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_smoke_run.py`:

```python
"""smoke_run end to end, against scripted agents rather than models.

The suite has to discriminate or none of the rest of this project means
anything, so these tests drive a real emitted package with a real verifier
subprocess and assert on the spread. The only fiction is the agent: three short
Python scripts standing in for a weak baseline, a competent agent, and an oracle.
"""

from __future__ import annotations

import sys

from testgen.artifacts import read_json
from testgen.smoke import AgentSpec, ROLES, smoke_run
from testgen.validate import validate_stage
from tests.unit.test_refs_states import build_state
from tests.unit.test_smoke_subprocess import COMPETENT, TOOLLESS

SID = "scn-001"

CRASHER = "import sys\nsys.exit(7)\n"


def _spec(tmp_path, role, body, name=None):
    script = tmp_path / (name or f"{role}.py")
    script.write_text(body, encoding="utf-8")
    return AgentSpec(
        role=role, model=f"model-{role}", command=(sys.executable, str(script)), timeout_sec=60.0
    )


def _roster(tmp_path, weak=TOOLLESS, under=COMPETENT, oracle=COMPETENT):
    return (
        _spec(tmp_path, "weak_baseline", weak),
        _spec(tmp_path, "under_test", under),
        _spec(tmp_path, "oracle", oracle),
    )


def _run(tmp_path):
    return build_state(tmp_path / "run", "emit")


def test_a_real_spread_produces_a_healthy_report(tmp_path):
    run = _run(tmp_path)
    report, findings = smoke_run(run, _roster(tmp_path))
    assert findings == [], findings
    assert report["verdict"] == "healthy"
    assert report["summary"]["mean_reward_by_role"] == {
        "weak_baseline": 0.0,
        "under_test": 1.0,
        "oracle": 1.0,
    }
    assert [task["scenario_id"] for task in report["tasks"]] == [SID]


def test_the_written_report_passes_layer_one(tmp_path):
    """The gate has to accept the artifact its own producer writes.

    A report smoke wrote that fails `validate --stage smoke` is a stage defect
    wearing a layer-1 error's clothes, and the orchestrator would retry the stage
    that is not at fault.
    """
    run = _run(tmp_path)
    smoke_run(run, _roster(tmp_path))
    assert validate_stage(run, "smoke") == []
    assert read_json(run.report)["run_id"] == read_json(run.manifest)["run_id"]


def test_the_report_lists_the_agents_in_role_order_with_their_models(tmp_path):
    run = _run(tmp_path)
    report, _ = smoke_run(run, _roster(tmp_path))
    assert [agent["role"] for agent in report["agents"]] == list(ROLES)
    assert [agent["model"] for agent in report["agents"]] == [f"model-{r}" for r in ROLES]


def test_a_trivial_suite_is_reported_as_a_finding_not_just_a_verdict(tmp_path):
    """smoke is a gate. Exit 0 on a degenerate suite would tell the orchestrator
    the suite is fit to trust."""
    run = _run(tmp_path)
    report, findings = smoke_run(run, _roster(tmp_path, weak=COMPETENT))
    assert report["verdict"] == "degenerate_trivial"
    assert len(findings) == 1
    assert findings[0].pointer == "/verdict"
    assert "weak baseline" in findings[0].message


def test_broken_labels_are_reported_against_the_labels_not_the_agent(tmp_path):
    run = _run(tmp_path)
    report, findings = smoke_run(run, _roster(tmp_path, oracle=TOOLLESS))
    assert report["verdict"] == "broken_labels"
    message = " ".join(f.message for f in findings)
    assert "gold labels or the verifier" in message


def test_a_crashing_agent_leaves_the_task_unscoreable_and_the_run_intact(tmp_path):
    """One broken role must not cost the other two their data."""
    run = _run(tmp_path)
    report, findings = smoke_run(run, _roster(tmp_path, under=CRASHER))
    results = {r["role"]: r for r in report["tasks"][0]["results"]}
    assert results["under_test"]["scored"] is False
    assert results["oracle"]["scored"] is True
    assert report["summary"]["unscoreable"] == 1
    assert report["verdict"] == "inconclusive"
    assert any("under_test" in f.message for f in findings)


def test_an_unscoreable_result_carries_no_reward_key_at_all(tmp_path):
    """Not reward: 0.0. The schema's `if scored then required` says the same
    thing, and a 0.0 here would be averaged as a real score by any later reader."""
    run = _run(tmp_path)
    report, _ = smoke_run(run, _roster(tmp_path, under=CRASHER))
    result = next(r for r in report["tasks"][0]["results"] if r["role"] == "under_test")
    assert "reward" not in result
    assert result["notes"]


def test_a_roster_without_the_oracle_is_a_finding_and_still_reports(tmp_path):
    run = _run(tmp_path)
    specs = tuple(s for s in _roster(tmp_path) if s.role != "oracle")
    report, findings = smoke_run(run, specs)
    assert report is not None, "the data is still worth having"
    assert report["verdict"] == "inconclusive"
    assert any("oracle" in f.message for f in findings)


def test_a_suite_with_no_packages_writes_no_report(tmp_path):
    """report-0.1.json sets tasks minItems 1 on purpose.

    A report over no tasks with verdict healthy would validate clean and claim a
    successful smoke over a suite nobody ran, so there is nothing valid to write.
    """
    run = build_state(tmp_path / "run", "challenge")  # emit has not run
    report, findings = smoke_run(run, _roster(tmp_path))
    assert report is None
    assert not run.report.exists()
    assert len(findings) == 1
    assert "no emitted packages" in findings[0].message


def test_the_logs_land_where_the_layout_says(tmp_path):
    run = _run(tmp_path)
    smoke_run(run, _roster(tmp_path))
    base = run.smoke_dir("oracle", SID)
    assert (base / "agent" / "agent-stdout.jsonl").is_file()
    assert (base / "agent-stderr.txt").is_file()
    assert (base / "verifier" / "reward.json").is_file()
    assert (base / "verifier" / "reward.txt").is_file()
    assert (base / "verifier-stderr.txt").is_file()
    assert not list((base / "agent").glob("*.txt")), "stderr must never be transcript input"


def test_rerunning_smoke_overwrites_rather_than_accumulating(tmp_path):
    """Two runs of the same suite must produce one report, not a merged one."""
    run = _run(tmp_path)
    smoke_run(run, _roster(tmp_path))
    report, _ = smoke_run(run, _roster(tmp_path))
    assert len(report["tasks"]) == 1
    assert len(report["tasks"][0]["results"]) == len(ROLES)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_smoke_run.py -q`
Expected: FAIL with `ImportError: cannot import name 'smoke_run' from 'testgen.smoke'`

- [ ] **Step 3: Implement `smoke_run`**

Add to `smoke.py` (and add `write_json` to the `testgen.artifacts` import):

```python
_VERDICT_MESSAGES = {
    "degenerate_trivial": (
        "the weak baseline mean reward is above {ceiling}, so the suite is not testing "
        "anything: a tool-less agent passes it. Redesign distractors and raise hop depth "
        "rather than trusting the under_test number"
    ),
    "broken_labels": (
        "the oracle mean reward is below {floor}. An agent handed the reference answer "
        "cannot pass these tasks, which indicts the gold labels or the verifier -- not the "
        "agent. Fix the labels before reading any other number in this report"
    ),
    "inconclusive": (
        "too little comparable data to judge the suite: fewer than {minimum} task(s) were "
        "scored by every declared role, or the roster is missing a role that "
        "degenerate-suite detection needs"
    ),
}


def _result_entry(role: str, reward: dict | None, notes: list[str]) -> dict:
    """One report result. An unscoreable role gets no reward key at all.

    Not `reward: 0.0`. report-0.1.json requires the four components only when
    `scored` is true, and a 0.0 here would be averaged as a real score by every
    later reader -- turning "we could not measure this" into "this failed".
    """
    usable = components(reward) if isinstance(reward, dict) else None
    if usable is None and isinstance(reward, dict):
        notes = [*notes, "verifier returned a reward outside [0, 1] or of the wrong type"]
    entry: dict = {"role": role, "scored": usable is not None}
    if usable is not None:
        entry.update(usable)
    note = "; ".join(n for n in notes if n)
    if note:
        entry["notes"] = note
    return entry


def smoke_run(run: RunPaths, specs: tuple[AgentSpec, ...]) -> tuple[dict | None, list[Finding]]:
    """Run every role over every emitted package and write 07-report.json.

    Returns (report, findings). The report is None only when there is nothing to
    run: report-0.1.json sets `tasks` minItems 1 deliberately, because a report
    over no tasks with verdict `healthy` would validate clean and claim a
    successful smoke over a suite nobody ran.

    **smoke is a gate, not only a reporter.** A verdict other than `healthy` comes
    back as a finding, so the caller exits 1 and the orchestrator learns the suite
    is not fit to trust. Exiting 0 with `broken_labels` printed inside a JSON file
    is how a broken suite gets shipped.

    A crashing or hanging agent costs that (role, task) its score and nothing
    else. The remaining roles still run, because the comparison across roles is
    the entire product.
    """
    # Read before anything runs. This raises ArtifactError on a directory with no
    # manifest, which cli.py maps to exit 2 -- and reading it after the agent loop
    # would burn every agent invocation in the run before discovering that the
    # thing it was pointed at is not a run.
    run_id = read_json(run.manifest)["run_id"]

    findings: list[Finding] = []
    sids = run.scenario_ids_with_tasks()
    if not sids:
        return None, [
            Finding(
                run.suite_dir,
                "smoke",
                "",
                "no emitted packages to run; emit must produce at least one package before "
                "smoke, and a report over no tasks cannot be written",
            )
        ]

    roles = tuple(spec.role for spec in specs)
    for role in REQUIRED_ROLES:
        if role not in roles:
            findings.append(
                Finding(
                    run.report,
                    "smoke",
                    "/agents",
                    f"the roster declares no {role!r} agent. Design spec section 7 makes it "
                    "load-bearing for degenerate-suite detection, so this run cannot be judged "
                    "healthy however good the scores look",
                )
            )

    tasks: list[dict] = []
    for sid in sids:
        task_dir = run.task_dir(sid)
        results = []
        for spec in specs:
            base = run.smoke_dir(spec.role, sid)
            agent_logs = base / "agent"
            _, agent_note = run_agent(
                spec,
                task_dir=task_dir,
                logs_dir=agent_logs,
                stderr_path=base / "agent-stderr.txt",
                scenario_id=sid,
            )
            _, reward, verify_note = verify_package(
                task_dir,
                agent_logs=agent_logs,
                out_dir=base / "verifier",
                stderr_path=base / "verifier-stderr.txt",
            )
            results.append(_result_entry(spec.role, reward, [agent_note, verify_note]))
        task = {"scenario_id": sid, "results": results}
        all_pass, all_fail = task_flags(task, roles)
        tasks.append({**task, "all_pass": all_pass, "all_fail": all_fail})

    summary = summarize(tasks, roles)
    verdict = verdict_for(tasks, summary, roles)
    report = {
        "schema_version": "0.1",
        # Indexed directly: manifest.json is a gated stage output, and a directory
        # without one is not a run. The ArtifactError becomes exit 2, which is the
        # honest answer -- no repair to a stage would produce a manifest.
        "run_id": run_id,
        "agents": [
            {"role": spec.role, "model": spec.model, **({"notes": spec.notes} if spec.notes else {})}
            for spec in specs
        ],
        "tasks": tasks,
        "summary": summary,
        "verdict": verdict,
    }
    write_json(run.report, report)

    for i, task in enumerate(tasks):
        for j, result in enumerate(task["results"]):
            if not result["scored"]:
                findings.append(
                    Finding(
                        run.report,
                        "smoke",
                        f"/tasks/{i}/results/{j}",
                        f"{result['role']} produced no score for {task['scenario_id']}: "
                        f"{result.get('notes', 'no diagnostic')}",
                    )
                )
    if verdict != "healthy":
        findings.append(
            Finding(
                run.report,
                "smoke",
                "/verdict",
                _VERDICT_MESSAGES[verdict].format(
                    ceiling=WEAK_BASELINE_CEILING,
                    floor=ORACLE_FLOOR,
                    minimum=MIN_COMPARABLE_TASKS,
                ),
            )
        )
    return report, findings
```

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest tests/unit/test_smoke_run.py -q`
Expected: PASS, 11 tests.

- [ ] **Step 5: Add the `smoke` subcommand**

In `cli.py`'s `_build_parser`:

```python
    p_smoke = subparsers.add_parser("smoke", help="run the emitted suite against the agent roster")
    p_smoke.add_argument("--run", required=True)
    p_smoke.add_argument("--agents", required=True, metavar="PATH")
```

Add `from testgen.smoke import load_agents, preflight, smoke_run` to the imports, and inside the main `try`, after the `emit` branch:

```python
        if args.command == "smoke":
            run = _run_dir(args.run)
            # An inner catch, because UsageError is a ValueError and the outer
            # narrow catch deliberately does not include ValueError -- without
            # this a typo'd roster path would reach `except Exception` and be
            # reported as a malformed artifact at exit 1.
            try:
                specs = preflight(load_agents(Path(args.agents)))
            except UsageError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return USAGE
            report, findings = smoke_run(run, specs)
            if report is not None:
                print(run.report)
            return _report(findings)
```

- [ ] **Step 6: Add the CLI tests**

In `tests/unit/test_cli.py`:

```python
def test_smoke_exits_zero_on_a_healthy_suite(tmp_path, capsys):
    run = build_state(tmp_path / "run", "emit")
    roster = _write_roster(tmp_path)
    code = main(["smoke", "--run", str(run.root), "--agents", str(roster)])
    assert code == 0
    assert str(run.report) in capsys.readouterr().out


def test_smoke_exits_two_on_an_unusable_roster(tmp_path, capsys):
    run = build_state(tmp_path / "run", "emit")
    assert main(["smoke", "--run", str(run.root), "--agents", str(tmp_path / "nope.json")]) == 2
    assert "unusable agent roster" in capsys.readouterr().err


def test_smoke_exits_one_with_findings_on_a_degenerate_suite(tmp_path, capsys):
    run = build_state(tmp_path / "run", "emit")
    roster = _write_roster(tmp_path, weak_is_competent=True)
    assert main(["smoke", "--run", str(run.root), "--agents", str(roster)]) == 1
    out = capsys.readouterr().out
    assert "[smoke]" in out and "not testing anything" in out


def test_smoke_exits_two_when_the_directory_has_no_manifest(tmp_path, capsys):
    """A directory without a manifest is not a run, and no stage repair makes one."""
    run = build_state(tmp_path / "run", "emit")
    run.manifest.unlink()
    roster = _write_roster(tmp_path)
    assert main(["smoke", "--run", str(run.root), "--agents", str(roster)]) == 2
```

`_write_roster` is a local helper writing an `agents.json` whose three commands are `[sys.executable, <script>]`, reusing `COMPETENT` and `TOOLLESS` from `tests/unit/test_smoke_subprocess.py`.

- [ ] **Step 7: Run the whole suite**

Run: `uv run pytest -q` and `uv run ruff check . && uv run ruff format --check .`
Expected: all green.

- [ ] **Step 8: Prove the end-to-end property by hand, outside pytest**

The suite must discriminate, and one manual run against a real emitted package is worth recording in the report:

```bash
uv run python - <<'PY'
from pathlib import Path
import json, subprocess, sys, tempfile
PY
```

If a heredoc is refused by the sandbox, write the script to a scratch file with the Write tool and run `uv run python /tmp/tg-smoke-probe.py` instead. The script must: build a run to the `emit` state, write a roster with a tool-less weak baseline and a competent oracle, call `smoke_run`, and print `07-report.json`'s `summary` and `verdict`. Paste the printed summary into the task report — it is the evidence that the emitted package, the copied verifier, and the aggregation agree.

- [ ] **Step 9: Gather mutation evidence**

```bash
export PYTHONDONTWRITEBYTECODE=1
```

| Deleted / changed | Named test that must fail |
|---|---|
| the `if not sids` early return | `test_a_suite_with_no_packages_writes_no_report` |
| the `REQUIRED_ROLES` loop | `test_a_roster_without_the_oracle_is_a_finding_and_still_reports` |
| the `if verdict != "healthy"` finding | `test_a_trivial_suite_is_reported_as_a_finding_not_just_a_verdict` |
| the unscoreable-result findings loop | `test_a_crashing_agent_leaves_the_task_unscoreable_and_the_run_intact` |
| `components(reward)` → `reward` in `_result_entry` | `test_an_out_of_range_reward_is_rejected_rather_than_written` (Task 6) and `test_the_written_report_passes_layer_one` |
| set `entry["reward"] = 0.0` when unscoreable | `test_an_unscoreable_result_carries_no_reward_key_at_all` |
| the inner `except UsageError` in `cli.py` | `test_smoke_exits_two_on_an_unusable_roster` |

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -S -s -m "feat: Add smoke_run and the smoke subcommand

Stage 7 end to end: every role over every emitted package, scored by the
package's own verifier, aggregated into 07-report.json.

smoke is a gate rather than only a reporter -- a verdict other than healthy comes
back as a finding, because exiting 0 with broken_labels printed inside a JSON
file is how a broken suite gets shipped. A crashing agent costs that one
(role, task) its score and nothing else.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 8: Cross-check the report against the suite

`check_all` has no report checker at all, so a report can list a scenario whose package `emit` has pruned and `validate --stage smoke` stays clean. It became reachable *because* emit now prunes, and it belongs with the smoke producer that owns the artifact.

The seam that needs care is the post-rejection state. Two situations look identical on disk and are opposite in meaning:

- A report naming a scenario with no package because **challenge rejected it after smoke ran**. Legitimate, prescribed by the spec's reject path, and it is the record the honest-hole report ("87%, 3 cells lost to rejected scenarios") is built from. Reporting it would make `check-refs` permanently dirty in a state the pipeline prescribes.
- A report naming a scenario that is still `active`, or one absent from `02-scenarios.json` entirely. That is a report over a suite nobody emitted.

The scenario's **status** is the distinguisher, and `JUDGED_STATUSES` already exists for exactly this. Every recomputed number comes from calling `smoke`'s own functions rather than re-deriving the arithmetic — a second implementation of `summarize` is the seam defect this project keeps finding.

**Files:**
- Modify: `src/testgen/refs.py`
- Modify: `tests/unit/test_refs_states.py` (add the `measurement` state)
- Test: `tests/unit/test_refs_report.py` (create)

**Interfaces:**
- Produces: `refs.check_report(run: RunPaths) -> list[Finding]`, called last in `check_all`.
- Consumes: `smoke.ROLES`, `smoke.REQUIRED_ROLES`, `smoke.task_flags`, `smoke.summarize`, `smoke.verdict_for`. `refs` imports `smoke`; `smoke` must never import `refs`.
- The report is read with `.get()` throughout: nothing orders `validate --stage smoke` before `check-refs`, so an ungated document can legitimately arrive — the same exception `check_suite` documents.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_refs_report.py`:

```python
"""refs.check_report: the report against the suite it claims to have run.

check_all had no report checker, so a report could list a scenario whose package
emit had pruned and both gates stayed green. The hard part is that the *same*
shape on disk is legitimate when the scenario was rejected after smoke ran --
which is a state the design spec's reject path prescribes, and the record the
honest-hole report is built from. Status is the distinguisher.
"""

from __future__ import annotations

import pytest

from testgen.artifacts import read_json, write_json
from testgen.refs import check_all, check_report
from tests.builders import minimal_report, minimal_scenarios
from tests.unit.test_refs_states import build_state

SID = "scn-001"


def _smoked(tmp_path):
    """A run through smoke: one emitted package and a report over it."""
    return build_state(tmp_path, "smoke")


def _report(run, **over):
    payload = read_json(run.report)
    payload.update(over)
    write_json(run.report, payload)
    return payload


def test_a_consistent_report_is_clean(tmp_path):
    assert check_report(_smoked(tmp_path)) == []


def test_no_report_is_not_a_finding(tmp_path):
    """Every state before smoke. check_all runs in all of them."""
    assert check_report(build_state(tmp_path, "emit")) == []


def test_a_report_naming_a_scenario_that_was_never_proposed_is_reported(tmp_path):
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    payload["tasks"][0]["scenario_id"] = "scn-ghost"
    write_json(run.report, payload)
    assert any("scn-ghost" in f.message for f in check_report(run))


def test_an_active_scenario_with_no_package_is_reported(tmp_path):
    """The carried-forward defect. A report over a suite nobody emitted."""
    import shutil

    run = _smoked(tmp_path)
    shutil.rmtree(run.task_dir(SID))
    findings = check_report(run)
    assert len(findings) == 1
    assert "has no emitted package" in findings[0].message


def test_a_rejected_scenario_with_no_package_is_tolerated(tmp_path):
    """The legitimate half of the same shape.

    challenge marks a scenario rejected after smoke has run and emit prunes its
    package. Reporting that would make check-refs permanently dirty in a state
    the spec prescribes, and would push someone to delete the rejection record
    the honest-hole report is built from.
    """
    import shutil

    run = _smoked(tmp_path)
    scenarios = minimal_scenarios()
    scenarios["scenarios"][0]["status"] = "rejected"
    scenarios["scenarios"][0]["rejected_reason"] = "ambiguous"
    write_json(run.scenarios, scenarios)
    shutil.rmtree(run.task_dir(SID))
    assert check_report(run) == []


def test_a_proposed_scenario_in_the_report_is_reported(tmp_path):
    """`proposed` is not judged. A suite emitted from an unscored scenario
    bypassed the gate that decides what is worth instantiating."""
    run = _smoked(tmp_path)
    scenarios = minimal_scenarios()
    scenarios["scenarios"][0]["status"] = "proposed"
    write_json(run.scenarios, scenarios)
    assert any("proposed" in f.message for f in check_report(run))


def test_an_emitted_package_the_report_never_ran_is_reported(tmp_path):
    """The other direction, and it is never legitimate.

    A package in 06-suite/ that no report entry mentions has not been smoked, so
    the suite ships a task nothing has ever executed.
    """
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    payload["tasks"][0]["scenario_id"] = payload["tasks"][0]["scenario_id"]
    payload["tasks"] = []
    write_json(run.report, payload)
    assert any("was never run" in f.message for f in check_report(run))


def test_a_duplicated_task_entry_is_reported(tmp_path):
    """Two entries for one scenario double its weight in every mean."""
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    payload["tasks"].append(dict(payload["tasks"][0]))
    write_json(run.report, payload)
    assert any("more than once" in f.message for f in check_report(run))


def test_a_run_id_that_does_not_match_the_manifest_is_reported(tmp_path):
    """A report filed against the wrong run is worse than no report."""
    run = _smoked(tmp_path)
    _report(run, run_id="run-19990101-000000")
    assert any("run_id" in f.pointer for f in check_report(run))


def test_a_declared_role_missing_from_a_task_is_reported(tmp_path):
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    payload["tasks"][0]["results"] = [
        r for r in payload["tasks"][0]["results"] if r["role"] != "oracle"
    ]
    write_json(run.report, payload)
    assert any("oracle" in f.message for f in check_report(run))


def test_a_roster_without_a_required_role_is_reported(tmp_path):
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    payload["agents"] = [a for a in payload["agents"] if a["role"] != "weak_baseline"]
    for task in payload["tasks"]:
        task["results"] = [r for r in task["results"] if r["role"] != "weak_baseline"]
    write_json(run.report, payload)
    assert any("weak_baseline" in f.message for f in check_report(run))


@pytest.mark.parametrize(
    "field,value",
    [
        ("all_pass_tasks", 3),
        ("all_fail_tasks", 3),
        ("oracle_failures", 3),
        ("unscoreable", 3),
    ],
)
def test_a_summary_count_that_does_not_match_the_results_is_reported(tmp_path, field, value):
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    payload["summary"][field] = value
    write_json(run.report, payload)
    findings = check_report(run)
    assert any(field in f.pointer for f in findings), [f.pointer for f in findings]


def test_a_mean_that_does_not_match_the_results_is_reported(tmp_path):
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    payload["summary"]["mean_reward_by_role"]["under_test"] = 0.99
    write_json(run.report, payload)
    assert any("mean_reward_by_role" in f.pointer for f in check_report(run))


def test_a_task_flag_that_does_not_match_its_results_is_reported(tmp_path):
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    payload["tasks"][0]["all_pass"] = True
    write_json(run.report, payload)
    assert any("all_pass" in f.pointer for f in check_report(run))


def test_a_verdict_that_does_not_match_the_data_is_reported(tmp_path):
    """The headline is the number a human reads first, so it is recomputed.

    A report claiming `healthy` over data that says `broken_labels` is the single
    most expensive thing this file can let through.
    """
    run = _smoked(tmp_path)
    _report(run, verdict="broken_labels")
    findings = check_report(run)
    assert any(f.pointer == "/verdict" for f in findings)
    assert any("healthy" in f.message for f in findings)


def test_check_all_runs_the_report_check(tmp_path):
    run = _smoked(tmp_path)
    _report(run, verdict="degenerate_trivial")
    assert any(f.pointer == "/verdict" for f in check_all(run))


def test_the_recomputation_uses_the_producers_own_functions(tmp_path):
    """Guards the seam, not the arithmetic.

    A second implementation of summarize in refs would pass every test above and
    drift the first time a threshold moved. This asserts the checker is reading
    the same constants the writer used.
    """
    from testgen import smoke

    run = _smoked(tmp_path)
    original = smoke.PASS_THRESHOLD
    try:
        smoke.PASS_THRESHOLD = 0.5  # under_test scored 0.8 -> now an all_pass task
        assert check_report(run) != []
    finally:
        smoke.PASS_THRESHOLD = original
    assert check_report(run) == []
```

The last test is deliberately a monkeypatch on the module attribute; if `refs` had copied the constant into its own module namespace it would not see the change. Use `pytest`'s `monkeypatch.setattr` if it reads more cleanly, but keep the property.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_refs_report.py -q`
Expected: FAIL with `ImportError: cannot import name 'check_report' from 'testgen.refs'`

- [ ] **Step 3: Implement `check_report`**

Add to `refs.py`, after `check_suite`. Import `smoke` **inside the function**, not at module scope: `smoke` imports `emit`, `emit` is a heavier module, and a module-level import here makes `refs` — which every other checker imports — pull in the emitter. A local import keeps the dependency where it is used and documents why.

```python
def check_report(run: RunPaths) -> list[Finding]:
    """07-report.json against 06-suite/, and its own arithmetic against its results.

    check_all had no report checker, so a report could list a scenario whose
    package emit had pruned and `validate --stage smoke` stayed clean. That became
    reachable when emit started pruning.

    **Status is the distinguisher for the hard case.** A report naming a scenario
    with no package is legitimate when the scenario is `rejected`: challenge marks
    it rejected *after* smoke ran, emit prunes the package, and that record is
    what the honest-hole report ("87%, 3 cells lost to rejected scenarios") is
    built from. Reporting it would make check-refs permanently dirty in a state the
    design spec prescribes, and the only way to clear it would be to delete the
    evidence. An `active` scenario with no package, or an id absent from
    02-scenarios.json, is the real defect: a report over a suite nobody emitted.

    Every recomputed number comes from calling smoke's own functions. A second
    implementation of the arithmetic here would agree today and drift the first
    time a threshold moved -- the per-seam defect class that produced the previous
    build's Critical.

    `.get()` throughout: nothing orders `validate --stage smoke` before
    check-refs, so an ungated report can legitimately arrive. Same exception
    check_suite documents, same reason.
    """
    from testgen import smoke

    report = _load(run.report)
    if not isinstance(report, dict):
        return []
    out: list[Finding] = []

    def report_finding(pointer: str, message: str) -> None:
        out.append(Finding(run.report, "refs", pointer, message))

    manifest = _load(run.manifest)
    if isinstance(manifest, dict) and report.get("run_id") != manifest.get("run_id"):
        report_finding(
            "/run_id",
            f"report is filed against run {report.get('run_id')!r} but this run is "
            f"{manifest.get('run_id')!r}",
        )

    agents = report.get("agents") or []
    roles = tuple(
        role
        for role in smoke.ROLES
        if role in {agent.get("role") for agent in agents if isinstance(agent, dict)}
    )
    for role in smoke.REQUIRED_ROLES:
        if role not in roles:
            report_finding(
                "/agents",
                f"no {role!r} agent ran, so the suite cannot be judged: it is what detects "
                + ("a trivial suite" if role == "weak_baseline" else "broken gold labels"),
            )

    scenarios_doc = _load(run.scenarios) or {"scenarios": []}
    by_id = {s["id"]: s for s in scenarios_doc.get("scenarios", [])}
    emitted = set(run.scenario_ids_with_tasks())

    tasks = [task for task in report.get("tasks") or [] if isinstance(task, dict)]
    named: list[str] = []
    for i, task in enumerate(tasks):
        sid = task.get("scenario_id")
        named.append(sid)
        scenario = by_id.get(sid)
        if scenario is None:
            report_finding(
                f"/tasks/{i}/scenario_id",
                f"the report ran {sid!r}, which no scenario in 02-scenarios.json proposes",
            )
        elif scenario.get("status") not in JUDGED_STATUSES:
            report_finding(
                f"/tasks/{i}/scenario_id",
                f"the report ran {sid!r}, whose status is {scenario.get('status')!r}; only a "
                "judged scenario (active, or rejected after the fact) should have been emitted",
            )
        elif sid not in emitted and scenario.get("status") != "rejected":
            report_finding(
                f"/tasks/{i}/scenario_id",
                f"the report ran {sid!r} but it has no emitted package; a report over a suite "
                "that was never emitted describes nothing",
            )

        declared = {r.get("role") for r in task.get("results") or [] if isinstance(r, dict)}
        for role in roles:
            if role not in declared:
                report_finding(
                    f"/tasks/{i}/results",
                    f"{role} is declared in /agents but produced no result for {sid!r}, so its "
                    "mean is taken over a different task set than the other roles",
                )
        expected_pass, expected_fail = smoke.task_flags(task, roles)
        for key, value in (("all_pass", expected_pass), ("all_fail", expected_fail)):
            if task.get(key) is not value:
                report_finding(
                    f"/tasks/{i}/{key}",
                    f"declared {task.get(key)!r} but the results say {value!r}",
                )

    for sid in sorted(set(named)):
        if named.count(sid) > 1:
            report_finding(
                "/tasks",
                f"scenario {sid!r} appears more than once, which doubles its weight in every "
                "mean the summary reports",
            )
    for sid in sorted(emitted - set(named)):
        report_finding(
            "/tasks",
            f"the emitted package for {sid!r} was never run: the suite ships a task nothing "
            "has executed",
        )

    expected_summary = smoke.summarize(tasks, roles)
    declared_summary = report.get("summary") or {}
    for key, value in expected_summary.items():
        if declared_summary.get(key) != value:
            report_finding(
                f"/summary/{key}",
                f"declared {declared_summary.get(key)!r} but the results give {value!r}",
            )

    expected_verdict = smoke.verdict_for(tasks, expected_summary, roles)
    if report.get("verdict") != expected_verdict:
        report_finding(
            "/verdict",
            f"declared {report.get('verdict')!r} but the results give {expected_verdict!r}; the "
            "verdict is the number a human reads first",
        )
    return out
```

Note the `mean_reward_by_role` comparison goes through the generic summary loop, so a float mismatch is caught by dict inequality. `mean_reward_by_role` rounds to 6 places in `smoke`, and `smoke_run` writes exactly what `summarize` returned, so an exact comparison is right here — a tolerance would let a hand-edited mean through.

Add to `check_all`, after `check_suite`:

```python
    findings.extend(check_report(run))
```

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest tests/unit/test_refs_report.py -q`
Expected: PASS. If `test_a_consistent_report_is_clean` fails, `tests/builders.py`'s `minimal_report` is arithmetically inconsistent with its own `results` — fix the builder, not the check.

- [ ] **Step 5: Add the `measurement` state to the states table**

`measurement/` is new on disk and `check_all` must be silent about it. In `tests/unit/test_refs_states.py`, add a builder and insert it between `smoke` and `post-rejection`:

```python
def _measurement(run: RunPaths) -> None:
    """The measurement tools' outputs, which are not stage artifacts.

    They live under measurement/ rather than a numbered prefix, and no layer-2
    check reads them. This state exists so that stays true: a checker that
    started globbing the run directory rather than naming its artifacts would
    find these and report them.
    """
    write_json(run.recall, {"schema_version": "0.1", "denominator": 0, "matched": [], "novel": []})
    run.review_dir.mkdir(parents=True, exist_ok=True)
    run.review_packet.write_text("# Review packet\n", encoding="utf-8")
```

```python
STATES: list[tuple[str, Callable[[RunPaths], None] | None]] = [
    ("empty", None),
    ("intake", _intake),
    ("extract", _extract),
    ("reconcile", _reconcile),
    ("propose", _propose),
    ("score", _score),
    ("instantiate", _instantiate),
    ("challenge", _challenge),
    ("emit", _emit),
    ("smoke", _smoke),
    ("measurement", _measurement),      # new
    ("post-rejection", _post_rejection),
]
```

The `recall` payload above is a placeholder shape; Task 10 replaces it with `recall.compare`'s real output once that exists, and Task 12 replaces the packet stub. Leave a `# Task 10 replaces this` comment so it is not mistaken for a contract. Extend `test_the_states_are_cumulative_so_the_last_one_is_a_complete_run` with `assert run.recall.is_file()` and `assert run.review_packet.is_file()`.

Add the `paths.py` properties this needs now, so the state builder compiles:

```python
    @property
    def recall(self) -> Path:
        return self.measurement_dir / "recall.json"

    @property
    def review_dir(self) -> Path:
        return self.measurement_dir / "review"

    @property
    def review_packet(self) -> Path:
        return self.review_dir / "packet.md"

    @property
    def review_sample(self) -> Path:
        return self.review_dir / "sample.json"
```

- [ ] **Step 6: Confirm the post-rejection state is still clean**

Run: `uv run pytest tests/unit/test_refs_states.py -q -v`
Expected: every state passes, including `post-rejection` — where the report names `scn-001`, its status is `rejected`, and its package has been pruned. That is the exact state the tolerance in `check_report` exists for. If it fails, the tolerance is missing or wrong; do not fix it by weakening a different check.

- [ ] **Step 7: Add the end-to-end cleanliness assertion**

Now that `check_report` exists, add to `tests/unit/test_smoke_run.py`:

```python
def test_a_real_smoke_run_leaves_layer_two_clean(tmp_path):
    """The seam between the producer and the checker, proved rather than assumed.

    Both sides recompute the summary with the same functions, so this can only
    fail if smoke writes something summarize did not produce.
    """
    from testgen.refs import check_all

    run = _run(tmp_path)
    smoke_run(run, _roster(tmp_path))
    assert check_all(run) == []
```

- [ ] **Step 8: Run the whole suite and gather mutation evidence**

Run: `uv run pytest -q` and `uv run ruff check . && uv run ruff format --check .`

```bash
export PYTHONDONTWRITEBYTECODE=1
```

| Deleted / changed | Named test that must fail |
|---|---|
| the `run_id` comparison | `test_a_run_id_that_does_not_match_the_manifest_is_reported` |
| the `REQUIRED_ROLES` loop | `test_a_roster_without_a_required_role_is_reported` |
| the `scenario is None` branch | `test_a_report_naming_a_scenario_that_was_never_proposed_is_reported` |
| the `JUDGED_STATUSES` branch | `test_a_proposed_scenario_in_the_report_is_reported` |
| the `sid not in emitted` branch | `test_an_active_scenario_with_no_package_is_reported` |
| its `and status != "rejected"` clause | `test_a_rejected_scenario_with_no_package_is_tolerated` **must start failing** |
| the missing-role-per-task loop | `test_a_declared_role_missing_from_a_task_is_reported` |
| the `task_flags` comparison | `test_a_task_flag_that_does_not_match_its_results_is_reported` |
| the duplicate-task loop | `test_a_duplicated_task_entry_is_reported` |
| the `emitted - named` loop | `test_an_emitted_package_the_report_never_ran_is_reported` |
| the summary comparison loop | every `test_a_summary_count_that_does_not_match_the_results_is_reported[...]` |
| the verdict comparison | `test_a_verdict_that_does_not_match_the_data_is_reported` |
| `check_report(run)` in `check_all` | `test_check_all_runs_the_report_check` |

The sixth row is the per-seam dual, and it is the one that matters most: deleting the tolerance must make a **tolerance** test fail, not only a defect test. Record both directions.

**Silent states:** `emit` (no report yet), `smoke`, `measurement`, and `post-rejection` — all four in the states table.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -S -s -m "fix: Cross-check the smoke report against the suite it claims to have run

check_all had no report checker, so a report could list a scenario whose package
emit had pruned and validate --stage smoke stayed clean -- newly reachable
because emit prunes.

Status is the distinguisher: a rejected scenario with no package is the record
the honest-hole report is built from and is tolerated; an active one is a report
over a suite nobody emitted. Every recomputed number calls smoke's own functions,
so the producer and the checker cannot drift.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 9: `jaccard` and gold matching

`compare-gold` answers "did the pipeline find the tests a human already authored, and what did it find that they did not". This task builds the input schema, the one metric two tools share, and the matching half.

**The matching rule: goal identity is required, cell overlap is scored.** Two tasks over different goals are different tests even when they touch the same capability cell — the goal is what a test is *about*, and scoring it would let a `find-the-failing-job` scenario partially match a `check-inventory-freshness` bench task because both call `query_aap2`. Cell overlap above `MATCH_JACCARD_FLOOR` is then what proposes the pair, and **the proposal is for a human to confirm**: no similarity number can tell two phrasings of one test from two different tests.

**Files:**
- Create: `src/testgen/metrics.py`, `src/testgen/schema/gold-0.1.json`, `src/testgen/recall.py`
- Modify: `src/testgen/validate.py` (register `gold`)
- Modify: `tests/builders.py` (`minimal_gold`)
- Test: `tests/unit/test_metrics.py`, `tests/unit/test_recall.py` (create)

**Interfaces:**
- Produces: `metrics.jaccard(a: frozenset, b: frozenset) -> float`; `recall.MATCH_JACCARD_FLOOR`, `recall.cells(capability_refs) -> frozenset[tuple[str, str]]`, `recall.generated_tasks(run) -> list[dict]`, `recall.load_gold(path) -> dict`, `recall.assign_matches(gold_tasks, generated) -> tuple[list[dict], list[str], list[dict]]` returning (matches, unmatched gold ids, unmatched generated scenarios).
- Consumes: `errors.UsageError`, `validate.validate_artifact`.

- [ ] **Step 1: Write `metrics.py` and its tests**

Create `tests/unit/test_metrics.py`:

```python
"""jaccard, and the 0/0 ruling it exists to hold in one place."""

from __future__ import annotations

from testgen.metrics import jaccard


def test_identical_sets_score_one():
    assert jaccard(frozenset("ab"), frozenset("ab")) == 1.0


def test_disjoint_sets_score_zero():
    assert jaccard(frozenset("ab"), frozenset("cd")) == 0.0


def test_partial_overlap_is_the_intersection_over_the_union():
    assert jaccard(frozenset("abc"), frozenset("bcd")) == 0.5


def test_two_empty_sets_score_one():
    """The ruling, and the trap.

    0/0 has no arithmetic answer. Returning 0.0 would report two runs that both
    produced nothing as maximally *different*, which is false. 1.0 is correct --
    the sets are identical -- and it is why every caller is required to report the
    set sizes alongside the number: a 1.0 over two empty sets is true and useless,
    and only the sizes make that visible.
    """
    assert jaccard(frozenset(), frozenset()) == 1.0


def test_one_empty_set_scores_zero():
    assert jaccard(frozenset("a"), frozenset()) == 0.0
    assert jaccard(frozenset(), frozenset("a")) == 0.0


def test_the_result_is_rounded_so_two_runs_produce_byte_identical_output():
    assert jaccard(frozenset(range(3)), frozenset(range(7))) == 0.428571
```

Create `src/testgen/metrics.py`:

```python
"""Set-similarity metrics shared by the measurement tools.

One function, in its own module, because the 0/0 answer is a ruling rather than
arithmetic and duplicating it across recall.py and stability.py is how the two
tools would come to disagree about what "no data" means.
"""

from __future__ import annotations


def jaccard(a: frozenset, b: frozenset) -> float:
    """|a and b| / |a or b|, with two empty sets defined as 1.0.

    Two empty sets are identical, so 1.0 is the correct reading -- but it is also
    the least informative number this function can return, so **every caller must
    report the set sizes alongside it.** A stability report saying "jaccard 1.0"
    over two runs that emitted nothing is true and reads as success.

    Rounded to six places so two runs over the same data produce byte-identical
    output and diff-runs does not report float formatting as variance.
    """
    if not a and not b:
        return 1.0
    return round(len(a & b) / len(a | b), 6)
```

Run: `uv run pytest tests/unit/test_metrics.py -q` → PASS.

- [ ] **Step 2: Write the gold schema**

Create `src/testgen/schema/gold-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "gold-0.1.json",
  "title": "Authored bench tasks to compare a generated suite against",
  "description": "Human-authored. The ~10 hand-written aap2 bench tasks compare-gold measures recall and novelty against. Ids here are world-model ids: goal_id and capability_refs must name the same goals, capabilities and outcome classes the run's 01-world-model.json declares, or nothing can match. A schema failure here is a usage error (exit 2), not a finding: a person wrote this file.",
  "type": "object",
  "required": ["schema_version", "target", "tasks"],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "0.1" },
    "target": { "type": "string", "minLength": 1 },
    "tasks": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "goal_id", "hop_depth", "capability_refs"],
        "additionalProperties": false,
        "properties": {
          "id": { "$ref": "#/$defs/id" },
          "goal_id": { "$ref": "#/$defs/id" },
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
          "notes": { "type": "string" }
        }
      }
    }
  },
  "$defs": {
    "id": {
      "type": "string",
      "pattern": "\\A[A-Za-z0-9][A-Za-z0-9._-]*\\Z",
      "maxLength": 128
    }
  }
}
```

`tasks` deliberately has **no** `minItems`: an empty gold list is a legitimate "we have no bench tasks yet", and `compare` reports a denominator of zero rather than refusing. Register `"gold": "gold-0.1.json"` in `validate.ARTIFACT_SCHEMAS` beside `agents`.

- [ ] **Step 3: Add the builder**

```python
def minimal_gold(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "target": "aap2",
        "tasks": [
            {
                "id": "bench-001",
                "goal_id": "goal-triage",
                "hop_depth": 2,
                "capability_refs": [
                    {"capability_id": "cap-find-jobs", "outcome_class_id": "oc-success"}
                ],
                "notes": "the hand-authored triage task scn-001 should match",
            }
        ],
    }
    payload.update(over)
    return payload
```

- [ ] **Step 4: Write the failing matching tests**

Create `tests/unit/test_recall.py` with the matching half (novelty and rendering arrive in Task 10):

```python
"""compare-gold: matching a generated suite against authored bench tasks.

Recall here is a smoke signal. The tests below pin the *rules* -- goal identity
required, cell overlap scored, one gold task to at most one scenario -- because
those are what make the number mean anything, not the number itself.
"""

from __future__ import annotations

import json

import pytest

from testgen.errors import UsageError
from testgen.recall import (
    MATCH_JACCARD_FLOOR,
    assign_matches,
    cells,
    generated_tasks,
    load_gold,
)
from tests.builders import minimal_gold, minimal_scenarios
from tests.unit.test_refs_states import build_state


def _gold_file(tmp_path, payload=None):
    path = tmp_path / "gold.json"
    path.write_text(json.dumps(payload if payload is not None else minimal_gold()), "utf-8")
    return path


def _generated(sid, goal_id="goal-triage", hop_depth=2, refs=(("cap-find-jobs", "oc-success"),)):
    return {
        "id": sid,
        "goal_id": goal_id,
        "hop_depth": hop_depth,
        "capability_refs": [
            {"capability_id": c, "outcome_class_id": o} for c, o in refs
        ],
    }


def _gold(gid, goal_id="goal-triage", hop_depth=2, refs=(("cap-find-jobs", "oc-success"),)):
    return {**_generated(gid, goal_id, hop_depth, refs), "id": gid}


# -- load_gold ---------------------------------------------------------------


def test_a_valid_gold_file_loads(tmp_path):
    assert load_gold(_gold_file(tmp_path))["tasks"][0]["id"] == "bench-001"


def test_an_absent_gold_file_is_a_usage_error(tmp_path):
    with pytest.raises(UsageError, match="unusable gold"):
        load_gold(tmp_path / "nope.json")


def test_a_gold_file_that_fails_the_schema_is_a_usage_error(tmp_path):
    payload = minimal_gold()
    payload["tasks"][0]["hop_depth"] = 99
    with pytest.raises(UsageError):
        load_gold(_gold_file(tmp_path, payload))


def test_an_empty_gold_list_is_allowed(tmp_path):
    """"We have no bench tasks yet" is a real state, and refusing it would make
    compare-gold unusable on a second target before anyone authored one."""
    assert load_gold(_gold_file(tmp_path, minimal_gold(tasks=[])))["tasks"] == []


# -- generated_tasks ---------------------------------------------------------


def test_only_emitted_scenarios_count_as_generated(tmp_path):
    """Recall is about the suite that shipped.

    A scenario the adversary rejected produced no package, so counting it would
    credit the pipeline with finding a test it did not deliver.
    """
    run = build_state(tmp_path, "emit")
    assert [task["id"] for task in generated_tasks(run)] == ["scn-001"]


def test_a_package_whose_scenario_vanished_is_skipped(tmp_path):
    from testgen.artifacts import write_json

    run = build_state(tmp_path, "emit")
    write_json(run.scenarios, minimal_scenarios(scenarios=[]))
    assert generated_tasks(run) == []


# -- cells -------------------------------------------------------------------


def test_cells_is_the_set_of_capability_outcome_pairs():
    assert cells(_generated("s")["capability_refs"]) == frozenset(
        {("cap-find-jobs", "oc-success")}
    )


def test_a_repeated_ref_collapses():
    refs = (("cap-a", "oc-1"), ("cap-a", "oc-1"))
    assert len(cells(_generated("s", refs=refs)["capability_refs"])) == 1


# -- assign_matches ----------------------------------------------------------


def test_an_exact_pair_matches():
    matches, unmatched_gold, unmatched_generated = assign_matches(
        [_gold("bench-001")], [_generated("scn-001")]
    )
    assert [(m["gold_id"], m["scenario_id"], m["jaccard"]) for m in matches] == [
        ("bench-001", "scn-001", 1.0)
    ]
    assert (unmatched_gold, unmatched_generated) == ([], [])


def test_a_different_goal_never_matches_however_similar_the_cells():
    """Goal identity is required, not scored.

    The two tasks below share every capability cell. They are still different
    tests: the goal is what a test is *about*, and scoring it would let a
    find-the-failing-job scenario partially match a check-inventory bench task
    because both happen to call query_aap2.
    """
    matches, unmatched_gold, unmatched_generated = assign_matches(
        [_gold("bench-001", goal_id="goal-triage")],
        [_generated("scn-001", goal_id="goal-inventory")],
    )
    assert matches == []
    assert unmatched_gold == ["bench-001"]
    assert [s["id"] for s in unmatched_generated] == ["scn-001"]


def test_overlap_below_the_floor_does_not_match():
    gold = _gold("bench-001", refs=(("cap-a", "oc-1"), ("cap-b", "oc-1"), ("cap-c", "oc-1")))
    generated = _generated("scn-001", refs=(("cap-a", "oc-1"), ("cap-x", "oc-1"), ("cap-y", "oc-1")))
    assert assign_matches([gold], [generated])[0] == []
    assert MATCH_JACCARD_FLOOR > 0.2


def test_overlap_at_the_floor_matches():
    gold = _gold("bench-001", refs=(("cap-a", "oc-1"), ("cap-b", "oc-1")))
    generated = _generated("scn-001", refs=(("cap-a", "oc-1"), ("cap-b", "oc-1"), ("cap-c", "oc-1")))
    matches, _, _ = assign_matches([gold], [generated])
    assert len(matches) == 1
    assert matches[0]["jaccard"] == pytest.approx(2 / 3)


def test_one_gold_task_matches_at_most_one_scenario():
    """Otherwise recall inflates: eight paraphrases of one test would each be
    credited against the same bench task."""
    gold = [_gold("bench-001")]
    matches, _, unmatched_generated = assign_matches(
        gold, [_generated("scn-001"), _generated("scn-002")]
    )
    assert len(matches) == 1
    assert len(unmatched_generated) == 1


def test_one_scenario_matches_at_most_one_gold_task():
    matches, unmatched_gold, _ = assign_matches(
        [_gold("bench-001"), _gold("bench-002")], [_generated("scn-001")]
    )
    assert len(matches) == 1
    assert len(unmatched_gold) == 1


def test_the_best_available_pair_wins_and_the_assignment_is_deterministic():
    """Greedy on descending overlap, ties broken by id.

    Without a total order the same inputs could produce two different match sets
    across runs, and recall would look like it moved when nothing did.
    """
    gold = [_gold("bench-001", refs=(("cap-a", "oc-1"), ("cap-b", "oc-1")))]
    close = _generated("scn-close", refs=(("cap-a", "oc-1"), ("cap-b", "oc-1")))
    loose = _generated("scn-loose", refs=(("cap-a", "oc-1"), ("cap-b", "oc-1"), ("cap-c", "oc-1")))
    for order in ([close, loose], [loose, close]):
        matches, _, _ = assign_matches(gold, order)
        assert [m["scenario_id"] for m in matches] == ["scn-close"]
```

- [ ] **Step 5: Run them to verify they fail, then implement**

Run: `uv run pytest tests/unit/test_recall.py -q` → FAIL (`ModuleNotFoundError: testgen.recall`).

Create `src/testgen/recall.py`:

```python
"""compare-gold: recall and novelty against the authored bench tasks.

Design spec section 7. The question is whether the pipeline found the tests a
human already wrote, and what it found that they did not -- and the answer is a
smoke signal, never a metric to optimize. With a denominator of ten, one task is
ten percentage points: 7/10 against 8/10 is noise. The rendered report says so
inline, derived from the actual denominator, because a number without that
sentence beside it will be optimized.

Every match is a **proposal for human confirmation.** Matching is goal identity
plus capability-cell overlap, and no similarity number can tell two phrasings of
one test from two genuinely different tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from testgen.artifacts import read_json
from testgen.errors import UsageError
from testgen.findings import format_findings
from testgen.metrics import jaccard
from testgen.paths import RunPaths
from testgen.validate import validate_artifact

# Cell-overlap at or above this proposes a pair, once the goals already match.
# Half, because a generated scenario that reaches an authored task's goal through
# half the same capability cells is plausibly the same test asked differently --
# and the human confirmation step is what resolves the plausibly.
MATCH_JACCARD_FLOOR = 0.5


def load_gold(path: Path | str) -> dict[str, Any]:
    """Read and schema-validate the bench task list.

    UsageError, not findings: a person wrote this file, so there is no stage to
    hand a repair prompt to. Same treatment smoke.load_agents gives its roster.
    """
    findings = validate_artifact(Path(path), "gold")
    if findings:
        raise UsageError(f"unusable gold task list:\n{format_findings(findings)}")
    return read_json(path)


def cells(capability_refs: list[dict[str, Any]]) -> frozenset[tuple[str, str]]:
    """The set of (capability, outcome class) pairs a task exercises."""
    return frozenset(
        (ref["capability_id"], ref["outcome_class_id"]) for ref in capability_refs
    )


def generated_tasks(run: RunPaths) -> list[dict[str, Any]]:
    """The scenarios that actually shipped, in id order.

    Emitted packages joined back to their scenarios -- not every scenario in
    02-scenarios.json. Recall is about the suite that shipped: crediting the
    pipeline with a scenario the adversary rejected would count a test it did not
    deliver. A package whose scenario has vanished from 02 is skipped rather than
    guessed at; refs.check_suite reports that separately.
    """
    scenarios = _load_scenarios(run)
    return [scenarios[sid] for sid in run.scenario_ids_with_tasks() if sid in scenarios]


def _load_scenarios(run: RunPaths) -> dict[str, dict[str, Any]]:
    try:
        document = read_json(run.scenarios)
    except Exception:  # noqa: BLE001 - see below
        return {}
    return {s["id"]: s for s in document.get("scenarios", [])}


def _pair_score(gold_task: dict[str, Any], scenario: dict[str, Any]) -> float | None:
    """Cell overlap for a candidate pair, or None if they cannot pair at all.

    Goal identity is a precondition rather than a term in the score: two tasks
    over different goals are different tests even when every capability cell
    matches, because the goal is what the test is about.
    """
    if gold_task["goal_id"] != scenario["goal_id"]:
        return None
    score = jaccard(cells(gold_task["capability_refs"]), cells(scenario["capability_refs"]))
    return score if score >= MATCH_JACCARD_FLOOR else None


def assign_matches(
    gold_tasks: list[dict[str, Any]], generated: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    """One-to-one assignment. -> (matches, unmatched gold ids, unmatched scenarios).

    One gold task claims at most one scenario and vice versa. Without that, eight
    paraphrases of one test would each be credited against the same bench task and
    recall would exceed what the suite covers.

    Greedy on descending overlap, with ties broken by (gold id, scenario id) so
    the assignment is a function of the inputs alone. A non-deterministic
    assignment would make recall appear to move between two runs of the same data,
    which is the one thing this number must not do.
    """
    candidates = []
    for gold_task in gold_tasks:
        for scenario in generated:
            score = _pair_score(gold_task, scenario)
            if score is not None:
                candidates.append((score, gold_task["id"], scenario["id"]))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))

    matches: list[dict[str, Any]] = []
    taken_gold: set[str] = set()
    taken_scenarios: set[str] = set()
    for score, gold_id, scenario_id in candidates:
        if gold_id in taken_gold or scenario_id in taken_scenarios:
            continue
        taken_gold.add(gold_id)
        taken_scenarios.add(scenario_id)
        matches.append({"gold_id": gold_id, "scenario_id": scenario_id, "jaccard": score})
    matches.sort(key=lambda match: match["gold_id"])
    return (
        matches,
        sorted(task["id"] for task in gold_tasks if task["id"] not in taken_gold),
        sorted(
            (s for s in generated if s["id"] not in taken_scenarios),
            key=lambda s: s["id"],
        ),
    )
```

Replace the bare `except Exception` in `_load_scenarios` with `except ArtifactError` and import it — a blind except would swallow a real bug, and the `noqa` in the sketch above is a marker that the sketch is wrong, not a licence. `refs.check_readable` already names an unparseable `02-scenarios.json`, so returning `{}` here is the right degradation.

- [ ] **Step 6: Run them to verify they pass**

Run: `uv run pytest tests/unit/test_recall.py tests/unit/test_metrics.py -q`
Expected: PASS

- [ ] **Step 7: Run the whole suite and gather mutation evidence**

Run: `uv run pytest -q` and `uv run ruff check . && uv run ruff format --check .`

```bash
export PYTHONDONTWRITEBYTECODE=1
```

| Deleted / changed | Named test that must fail |
|---|---|
| the `not a and not b` branch of `jaccard` | `test_two_empty_sets_score_one` |
| the `round(...)` in `jaccard` | `test_the_result_is_rounded_so_two_runs_produce_byte_identical_output` |
| the `goal_id` precondition in `_pair_score` | `test_a_different_goal_never_matches_however_similar_the_cells` |
| the `>= MATCH_JACCARD_FLOOR` clause | `test_overlap_below_the_floor_does_not_match` |
| the `taken_gold` guard | `test_one_scenario_matches_at_most_one_gold_task` |
| the `taken_scenarios` guard | `test_one_gold_task_matches_at_most_one_scenario` |
| the tie-break terms in `candidates.sort` | `test_the_best_available_pair_wins_and_the_assignment_is_deterministic` |
| `scenario_ids_with_tasks()` → every scenario in 02 | `test_only_emitted_scenarios_count_as_generated` |
| the `if findings: raise` in `load_gold` | `test_a_gold_file_that_fails_the_schema_is_a_usage_error` |

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -S -s -m "feat: Add jaccard and gold-task matching for compare-gold

Goal identity is a precondition rather than a term in the score: two tasks over
different goals are different tests even when every capability cell matches.
Assignment is one-to-one and deterministic, so eight paraphrases of one test
cannot each be credited against the same bench task and recall cannot appear to
move between two runs of the same data.

jaccard lives in its own module because 0/0 is a ruling rather than arithmetic,
and duplicating it is how two tools come to disagree about what no data means.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 10: Novelty, the noise caveat, and the `compare-gold` subcommand

Recall alone is half the signal. The other half is what the pipeline found that nobody authored, categorized so it can be judged rather than counted: **new capability / new outcome class / new hop depth / spurious**, in that precedence.

The precedence is the design. A scenario that reaches a capability gold never touches is the most interesting thing `compare-gold` can report, and it would be filed under the blandest available label if the checks ran in the other order. `spurious` is last and it is a real category: a scenario whose every cell and whose (goal, hop depth) pair already appear in gold is not novel by any axis — it looks new only because the matcher could not pair it.

**Files:**
- Modify: `src/testgen/recall.py`, `src/testgen/cli.py`
- Modify: `tests/unit/test_refs_states.py` (replace the `measurement` stub with the real output)
- Test: `tests/unit/test_recall.py` (extend), `tests/unit/test_cli.py` (extend)

**Interfaces:**
- Produces: `recall.NOVELTY_KINDS`, `recall.classify_novelty(scenario, gold_tasks) -> tuple[str, str]` returning `(kind, why)`, `recall.compare(run, gold) -> dict`, `recall.render(report) -> str`, `recall.compare_run(run, gold_path) -> tuple[dict, list[Finding]]`.
- CLI: `testgen compare-gold --run DIR --gold PATH`. Writes `measurement/recall.json`, prints the rendered markdown to stdout, exits 0. A malformed gold file is exit 2.
- The report carries `"format": "testgen-recall/1"` and **no `schema_version`** — per the global constraint, measurement outputs the code writes are gated by unit tests, and a `schema_version` on a file with no schema is a claim there is one.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_recall.py`:

```python
# -- classify_novelty --------------------------------------------------------

from testgen.recall import NOVELTY_KINDS, classify_novelty, compare, render  # noqa: E402


def _kind(scenario, gold=None):
    return classify_novelty(scenario, gold if gold is not None else [_gold("bench-001")])[0]


def test_a_capability_gold_never_touches_is_the_headline():
    assert _kind(_generated("scn-9", refs=(("cap-unknown", "oc-success"),))) == "new_capability"


def test_a_known_capability_in_an_unknown_outcome_class_is_a_new_outcome_class():
    assert _kind(_generated("scn-9", refs=(("cap-find-jobs", "oc-empty"),))) == "new_outcome_class"


def test_a_known_cell_at_an_unauthored_hop_depth_is_a_new_hop_depth():
    assert _kind(_generated("scn-9", hop_depth=4)) == "new_hop_depth"


def test_a_goal_gold_never_covers_is_a_new_hop_depth_too():
    """A goal absent from gold has no authored depths, so every depth is new.

    Folding it in here rather than adding a fifth category keeps the vocabulary
    the spec fixed, and the `why` string names the goal so the reason is not lost.
    """
    kind, why = classify_novelty(
        _generated("scn-9", goal_id="goal-unseen"), [_gold("bench-001")]
    )
    assert kind == "new_hop_depth"
    assert "goal-unseen" in why


def test_a_recombination_of_authored_coverage_is_spurious():
    """Last in the precedence, and a real category.

    Every cell and the (goal, hop depth) pair already appear in gold -- spread
    across two authored tasks -- so this adds no coverage axis. It looks new only
    because no single gold task overlapped it enough to pair.
    """
    gold = [
        _gold("bench-001", refs=(("cap-a", "oc-1"),) * 1),
        _gold("bench-002", refs=(("cap-b", "oc-1"),) * 1),
    ]
    scenario = _generated(
        "scn-9", refs=(("cap-a", "oc-1"), ("cap-b", "oc-1"), ("cap-a", "oc-1"))
    )
    kind, why = classify_novelty(scenario, gold)
    assert kind == "spurious"
    assert why


def test_the_precedence_is_capability_then_class_then_depth():
    """A scenario that is new on every axis at once must report the strongest.

    Reporting new_hop_depth for a scenario that reached a capability nobody
    authored buries the most interesting result compare-gold can produce.
    """
    scenario = _generated("scn-9", refs=(("cap-unknown", "oc-unknown"),), hop_depth=5)
    assert _kind(scenario) == "new_capability"
    assert NOVELTY_KINDS[0] == "new_capability"


def test_every_scenario_gets_exactly_one_kind_from_the_closed_vocabulary():
    for scenario in (
        _generated("a"),
        _generated("b", refs=(("cap-x", "oc-1"),)),
        _generated("c", hop_depth=1),
        _generated("d", goal_id="goal-other"),
    ):
        assert _kind(scenario) in NOVELTY_KINDS


# -- compare -----------------------------------------------------------------


def test_compare_reports_recall_over_the_gold_denominator(tmp_path):
    run = build_state(tmp_path, "emit")
    report = compare(run, minimal_gold())
    assert report["gold_denominator"] == 1
    assert report["recall"] == 1.0
    assert report["matched"][0]["scenario_id"] == "scn-001"
    assert report["unmatched_gold"] == []
    assert report["novel"] == []
    assert report["human_confirmation_required"] is True
    assert "schema_version" not in report


def test_compare_categorizes_what_matched_nothing(tmp_path):
    run = build_state(tmp_path, "emit")
    gold = minimal_gold(tasks=[_gold("bench-001", goal_id="goal-elsewhere")])
    report = compare(run, gold)
    assert report["recall"] == 0.0
    assert report["unmatched_gold"] == ["bench-001"]
    assert [entry["kind"] for entry in report["novel"]] == ["new_hop_depth"]
    assert report["novel"][0]["scenario_id"] == "scn-001"


def test_an_empty_gold_list_reports_no_recall_rather_than_a_zero(tmp_path):
    """0.0 would read as "the pipeline found none of them"."""
    run = build_state(tmp_path, "emit")
    report = compare(run, minimal_gold(tasks=[]))
    assert report["gold_denominator"] == 0
    assert report["recall"] is None


def test_compare_is_deterministic(tmp_path):
    run = build_state(tmp_path, "emit")
    assert compare(run, minimal_gold()) == compare(run, minimal_gold())


# -- render ------------------------------------------------------------------


def test_the_rendered_report_states_the_noise_caveat_with_the_real_denominator(tmp_path):
    """Mandated by design spec section 7, and derived rather than boilerplate.

    A recall number without this sentence beside it will be optimized, and with a
    denominator of ten it is ten points per task.
    """
    run = build_state(tmp_path, "emit")
    text = render(compare(run, minimal_gold(tasks=[_gold(f"bench-{i:03d}") for i in range(10)])))
    assert "denominator of 10" in text
    assert "noise" in text
    assert "not a metric to optimize" in text


def test_the_caveat_changes_with_the_denominator(tmp_path):
    run = build_state(tmp_path, "emit")
    text = render(compare(run, minimal_gold()))
    assert "denominator of 1" in text
    assert "denominator of 10" not in text


def test_an_empty_gold_list_renders_a_different_sentence(tmp_path):
    run = build_state(tmp_path, "emit")
    text = render(compare(run, minimal_gold(tasks=[])))
    assert "no gold tasks" in text
    assert "noise" not in text


def test_the_rendered_report_says_matches_need_human_confirmation(tmp_path):
    run = build_state(tmp_path, "emit")
    assert "human confirmation" in render(compare(run, minimal_gold()))


def test_every_novel_scenario_appears_in_the_rendering(tmp_path):
    run = build_state(tmp_path, "emit")
    gold = minimal_gold(tasks=[_gold("bench-001", goal_id="goal-elsewhere")])
    text = render(compare(run, gold))
    assert "scn-001" in text
    assert "new_hop_depth" in text
```

Move the mid-file import to the module's import block rather than leaving the `noqa: E402`.

- [ ] **Step 2: Implement novelty, `compare`, `render`, `compare_run`**

Append to `recall.py`:

```python
# Ordered by how much a reader should care, and the order the checks run in. A
# scenario that reached a capability nobody authored is the most interesting
# result this tool can produce, and running the checks the other way round would
# file it under the blandest label that also happens to be true.
NOVELTY_KINDS = ("new_capability", "new_outcome_class", "new_hop_depth", "spurious")

_NOISE_CAVEAT = (
    "**Recall is a smoke signal, not a metric to optimize.** With a denominator of "
    "{denominator}, one task is {step:.0%}: {matched}/{denominator} against "
    "{next_up}/{denominator} is noise, not improvement. Every match below is a "
    "proposal for **human confirmation** -- matching is goal identity plus "
    "capability-cell overlap, and no similarity number can tell two phrasings of "
    "one test from two different tests."
)

_NO_GOLD_CAVEAT = (
    "No gold tasks were supplied, so there is no recall to report. The novelty "
    "section below still stands on its own, and every entry in it is a proposal "
    "for **human confirmation**."
)


def classify_novelty(
    scenario: dict[str, Any], gold_tasks: list[dict[str, Any]]
) -> tuple[str, str]:
    """Why one unmatched scenario is interesting. -> (kind, why).

    A goal gold never covers is folded into new_hop_depth rather than given a
    fifth category: it has no authored depths, so every depth it reaches is new,
    and the `why` string names the goal so the reason is not lost. That keeps the
    vocabulary the design spec fixed.
    """
    authored_capabilities = {
        ref["capability_id"] for task in gold_tasks for ref in task["capability_refs"]
    }
    authored_cells = frozenset().union(
        *(cells(task["capability_refs"]) for task in gold_tasks)
    ) if gold_tasks else frozenset()
    authored_depths = {
        (task["goal_id"], task["hop_depth"]) for task in gold_tasks
    }

    scenario_cells = cells(scenario["capability_refs"])
    new_capabilities = sorted(
        {capability for capability, _ in scenario_cells} - authored_capabilities
    )
    if new_capabilities:
        return "new_capability", (
            f"exercises {', '.join(new_capabilities)}, which no authored task touches"
        )
    new_cells = sorted(scenario_cells - authored_cells)
    if new_cells:
        return "new_outcome_class", (
            "reaches "
            + ", ".join(f"{capability}/{outcome}" for capability, outcome in new_cells)
            + ", an outcome class no authored task reaches for that capability"
        )
    pair = (scenario["goal_id"], scenario["hop_depth"])
    if pair not in authored_depths:
        covered = sorted(depth for goal, depth in authored_depths if goal == pair[0])
        return "new_hop_depth", (
            f"reaches goal {pair[0]} at hop depth {pair[1]}; authored depths for that goal "
            f"are {covered or 'none -- the goal itself is unauthored'}"
        )
    return "spurious", (
        "every capability cell and the (goal, hop depth) pair already appear in the authored "
        "tasks, spread across more than one of them, so this adds no coverage axis and looks "
        "new only because no single authored task overlapped it enough to pair"
    )


def compare(run: RunPaths, gold: dict[str, Any]) -> dict[str, Any]:
    """The recall-and-novelty report for one run against one gold list.

    `recall` is None rather than 0.0 when no gold tasks were supplied: 0.0 reads as
    "the pipeline found none of them", which is a claim about the pipeline rather
    than about the missing input.
    """
    gold_tasks = gold.get("tasks", [])
    generated = generated_tasks(run)
    matches, unmatched_gold, unmatched_generated = assign_matches(gold_tasks, generated)
    novel = []
    for scenario in unmatched_generated:
        kind, why = classify_novelty(scenario, gold_tasks)
        novel.append({"scenario_id": scenario["id"], "kind": kind, "why": why})
    denominator = len(gold_tasks)
    return {
        # A format tag, not a schema_version: no JSON Schema gates this file,
        # because this project's own code writes it and unit tests gate it
        # instead. Claiming a schema_version would say otherwise.
        "format": "testgen-recall/1",
        "target": gold.get("target"),
        "gold_denominator": denominator,
        "generated_total": len(generated),
        "matched": matches,
        "unmatched_gold": unmatched_gold,
        "recall": round(len(matches) / denominator, 6) if denominator else None,
        "novel": novel,
        "human_confirmation_required": True,
    }


def caveat(report: dict[str, Any]) -> str:
    """The sentence design spec section 7 requires beside every recall number."""
    denominator = report["gold_denominator"]
    if not denominator:
        return _NO_GOLD_CAVEAT
    matched = len(report["matched"])
    return _NOISE_CAVEAT.format(
        denominator=denominator,
        step=1 / denominator,
        matched=matched,
        next_up=min(matched + 1, denominator),
    )


def render(report: dict[str, Any]) -> str:
    """The human-facing markdown. The caveat is not optional and not at the end."""
    lines = [
        "# Recall and novelty against the authored bench tasks",
        "",
        caveat(report),
        "",
        f"- **Authored tasks:** {report['gold_denominator']}",
        f"- **Generated tasks that shipped:** {report['generated_total']}",
        f"- **Matched:** {len(report['matched'])}",
        f"- **Recall:** "
        + ("not applicable" if report["recall"] is None else f"{report['recall']:.2f}"),
        "",
        "## Proposed matches",
        "",
    ]
    if report["matched"]:
        lines += ["| Authored | Generated | Cell overlap |", "|---|---|---|"]
        lines += [
            f"| `{m['gold_id']}` | `{m['scenario_id']}` | {m['jaccard']:.2f} |"
            for m in report["matched"]
        ]
    else:
        lines.append("None.")
    lines += ["", "## Authored tasks nothing matched", ""]
    lines += (
        [f"- `{gold_id}`" for gold_id in report["unmatched_gold"]]
        if report["unmatched_gold"]
        else ["None."]
    )
    lines += ["", "## Generated tasks nothing authored", ""]
    lines += (
        [f"- `{n['scenario_id']}` — **{n['kind']}**: {n['why']}" for n in report["novel"]]
        if report["novel"]
        else ["None."]
    )
    lines.append("")
    return "\n".join(lines)


def compare_run(run: RunPaths, gold_path: Path | str) -> tuple[dict[str, Any], list[Finding]]:
    """Write measurement/recall.json and return (report, findings).

    Findings, not a bare report: a gold task nothing matched is worth the
    orchestrator's attention, and so is a `spurious` entry. Neither is a defect in
    an artifact, so both are reported once, aggregated, rather than one finding per
    row -- the point is the shape of the gap, not a list.
    """
    report = compare(run, load_gold(gold_path))
    write_json(run.recall, report)
    (run.measurement_dir / "recall.md").write_text(render(report), encoding="utf-8")
    findings = []
    if report["unmatched_gold"]:
        findings.append(
            Finding(
                run.recall,
                "recall",
                "/unmatched_gold",
                f"{len(report['unmatched_gold'])} authored task(s) have no generated "
                f"counterpart: {', '.join(report['unmatched_gold'])}. With a denominator of "
                f"{report['gold_denominator']} this is a smoke signal, not a score",
            )
        )
    spurious = [entry["scenario_id"] for entry in report["novel"] if entry["kind"] == "spurious"]
    if spurious:
        findings.append(
            Finding(
                run.recall,
                "recall",
                "/novel",
                f"{len(spurious)} generated task(s) add no coverage axis over the authored "
                f"set: {', '.join(spurious)}",
            )
        )
    return report, findings
```

Add `write_json` to the `testgen.artifacts` import and `Finding` to the `testgen.findings` import. Add `"recall"` to the `layer` comment in `findings.py`'s docstring.

- [ ] **Step 3: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_recall.py -q`
Expected: PASS

- [ ] **Step 4: Add the `compare-gold` subcommand**

```python
    p_gold = subparsers.add_parser(
        "compare-gold", help="recall and novelty against the authored bench tasks"
    )
    p_gold.add_argument("--run", required=True)
    p_gold.add_argument("--gold", required=True, metavar="PATH")
```

```python
        if args.command == "compare-gold":
            run = _run_dir(args.run)
            try:
                report, findings = compare_run(run, Path(args.gold))
            except UsageError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return USAGE
            print(render(report))
            return _report(findings)
```

Mixing the rendered markdown and finding lines on stdout is deliberate and matches `emit`, which prints task directories before its findings: a human reads the report, and a machine parsing findings reads the `[recall] ...` lines. Add CLI tests for exit 0 on a full match, exit 1 on an unmatched gold task, and exit 2 on a malformed gold file.

- [ ] **Step 5: Replace the states-table stub with the real output**

Task 8 wrote a hand-shaped placeholder into `_measurement`. Replace it with a call to the real tool, so the state cannot drift from what `compare-gold` actually writes — the same technique `_emit` already uses:

```python
def _measurement(run: RunPaths) -> None:
    """The measurement tools' real outputs, written by the tools themselves.

    Hand-shaping these would let the state drift from what the tools write, which
    is how a state stops proving anything. compare_run and sample_run are called
    for the same reason _emit calls emit_run.
    """
    report, findings = compare_run(run, _gold_path(run))
    assert findings == [], f"compare-gold in the states table: {findings}"
```

`_gold_path(run)` writes `minimal_gold()` to `run.root / "gold.json"` and returns it. That path is deliberately *not* under `measurement/` — the gold list is an input a person supplies, not an output — and nothing in the project globs the run root, so no checker sees it. It sits inside the run directory only because the state builder receives nothing but `run`; writing to `run.root.parent` would land in pytest's shared tmp base and collide across tests.

Task 12 appends the `sample_run` call.

- [ ] **Step 6: Run the whole suite and gather mutation evidence**

Run: `uv run pytest -q` and `uv run ruff check . && uv run ruff format --check .`

```bash
export PYTHONDONTWRITEBYTECODE=1
```

| Deleted / changed | Named test that must fail |
|---|---|
| the `new_capabilities` branch | `test_a_capability_gold_never_touches_is_the_headline` |
| the `new_cells` branch | `test_a_known_capability_in_an_unknown_outcome_class_is_a_new_outcome_class` |
| the `authored_depths` branch | `test_a_known_cell_at_an_unauthored_hop_depth_is_a_new_hop_depth` |
| reorder the branches (depth first) | `test_the_precedence_is_capability_then_class_then_depth` |
| the `if denominator else None` clause | `test_an_empty_gold_list_reports_no_recall_rather_than_a_zero` |
| the `caveat(report)` line in `render` | `test_the_rendered_report_states_the_noise_caveat_with_the_real_denominator` |
| hard-code `denominator=10` in the caveat | `test_the_caveat_changes_with_the_denominator` |
| the `_NO_GOLD_CAVEAT` branch | `test_an_empty_gold_list_renders_a_different_sentence` |
| the `unmatched_gold` finding | the new CLI exit-1 test |

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -S -s -m "feat: Add novelty categorization, the noise caveat, and compare-gold

The precedence is the design: a scenario that reached a capability nobody authored
is the most interesting result this tool can produce, and checking hop depth first
would file it under the blandest label that also happens to be true.

The noise caveat is derived from the actual denominator rather than boilerplate,
because a recall number without that sentence beside it will be optimized -- and
with a denominator of ten it is ten points per task.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 11: `diff-runs`

Design spec §291: a per-stage stability number, so variance can be *attributed* — the difference between "the pipeline is nondeterministic" and "stage 2 is nondeterministic and everything downstream is stable given a fixed 02". Three Jaccards, on capability ids after 1b, on goal×cell claims after 2, and on emitted task ids after 6.

Two things make it more than three numbers.

**Comparability is a precondition, not a caveat.** §291 says two runs are comparable only if the manifest's per-stage model, effort and skill hash match — and, now that Task 1 exists, only if they read the same input bytes. Comparing runs that read different inputs produces a stability number that measures the inputs.

**Every Jaccard is reported with its set sizes and its difference.** A bare `1.0` over two runs that emitted nothing reads as perfect stability; a bare `0.4` tells nobody *which* capability moved. `only_a` and `only_b` are what make the number actionable, which is the entire point of attributing variance per stage.

`diff-runs` spans two runs and belongs to neither, so it writes nothing: the report goes to stdout as JSON and the exit code is 0, exactly like `dedupe-candidates`. Incomparability is *data inside that JSON* plus a warning on stderr — not a finding, because exit 1 means finding lines on stdout and mixing them with a JSON document would break the orchestrator's line parser.

**Files:**
- Create: `src/testgen/stability.py`
- Modify: `src/testgen/cli.py`
- Test: `tests/unit/test_stability.py` (create), `tests/unit/test_cli.py` (extend)

**Interfaces:**
- Produces: `stability.input_digests(run)`, `stability.stage_config(run)`, `stability.capability_ids(run)`, `stability.goal_cell_claims(run)`, `stability.emitted_task_ids(run)`, `stability.comparability(a, b) -> list[str]`, `stability.diff_runs(a, b) -> dict`.
- CLI: `testgen diff-runs --a DIR --b DIR`. JSON on stdout, exit 0; a stderr warning when the runs are not comparable; exit 2 if either directory is unreadable.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_stability.py`:

```python
"""diff-runs: attributing variance to a stage rather than to "the pipeline".

The numbers are Jaccards, which is the easy part. What these tests pin is the
part that makes them mean something: that two runs which read different inputs
are declared incomparable rather than scored, and that every number arrives with
its set sizes and its difference attached.
"""

from __future__ import annotations

from testgen.artifacts import read_json, write_json
from testgen.stability import (
    capability_ids,
    comparability,
    diff_runs,
    emitted_task_ids,
    goal_cell_claims,
    input_digests,
    stage_config,
)
from tests.builders import minimal_manifest, minimal_scenarios, minimal_world_model
from tests.unit.test_refs_states import build_state


def _pair(tmp_path, state="emit"):
    return build_state(tmp_path / "a", state), build_state(tmp_path / "b", state)


# -- the per-stage sets ------------------------------------------------------


def test_capability_ids_come_from_the_world_model(tmp_path):
    run = build_state(tmp_path, "reconcile")
    assert capability_ids(run) == frozenset({"cap-find-jobs"})


def test_goal_cell_claims_are_goal_capability_outcome_triples(tmp_path):
    run = build_state(tmp_path, "propose")
    assert goal_cell_claims(run) == frozenset(
        {("goal-triage", "cap-find-jobs", "oc-success")}
    )


def test_a_discarded_scenario_makes_no_claim(tmp_path):
    """Stability is about what the run produced, and a duplicate produced nothing."""
    run = build_state(tmp_path, "propose")
    scenarios = minimal_scenarios()
    scenarios["scenarios"][0]["status"] = "duplicate"
    scenarios["scenarios"][0]["duplicate_of"] = "scn-000"
    write_json(run.scenarios, scenarios)
    assert goal_cell_claims(run) == frozenset()


def test_emitted_task_ids_come_from_the_suite_directory(tmp_path):
    run = build_state(tmp_path, "emit")
    assert emitted_task_ids(run) == frozenset({"scn-001"})


def test_an_absent_artifact_gives_an_empty_set_rather_than_raising(tmp_path):
    """diff-runs must be usable on a run that halted early.

    Comparing a complete run against one that stopped after propose is exactly the
    comparison that localizes where it stopped being reproducible.
    """
    from testgen.paths import RunPaths

    run = RunPaths(tmp_path / "nothing")
    run.root.mkdir(parents=True)
    assert capability_ids(run) == frozenset()
    assert goal_cell_claims(run) == frozenset()
    assert emitted_task_ids(run) == frozenset()


# -- comparability -----------------------------------------------------------


def test_two_identical_runs_are_comparable(tmp_path):
    a, b = _pair(tmp_path)
    assert comparability(a, b) == []


def test_different_input_bytes_make_the_runs_incomparable(tmp_path):
    """A stability number over different inputs measures the inputs."""
    a, b = _pair(tmp_path)
    manifest = read_json(b.manifest)
    manifest["inputs"][0]["sha256"] = "f" * 64
    write_json(b.manifest, manifest)
    reasons = comparability(a, b)
    assert len(reasons) == 1
    assert "different input" in reasons[0]


def test_a_stage_run_under_a_different_model_makes_the_runs_incomparable(tmp_path):
    """Design spec section 291: two runs are comparable only if these match."""
    a, b = _pair(tmp_path)
    manifest = read_json(b.manifest)
    manifest["stages"]["reconcile"]["model"] = "claude-sonnet-5"
    write_json(b.manifest, manifest)
    assert any("reconcile" in reason and "model" in reason for reason in comparability(a, b))


def test_a_stage_run_under_a_different_effort_or_skill_hash_is_caught(tmp_path):
    a, b = _pair(tmp_path)
    manifest = read_json(b.manifest)
    manifest["stages"]["reconcile"]["effort"] = "low"
    manifest["stages"]["reconcile"]["skill_sha256"] = "c" * 64
    write_json(b.manifest, manifest)
    reasons = " ".join(comparability(a, b))
    assert "effort" in reasons and "skill_sha256" in reasons


def test_a_stage_recorded_in_only_one_run_is_reported(tmp_path):
    a, b = _pair(tmp_path)
    manifest = read_json(b.manifest)
    manifest["stages"]["propose"] = {
        "model": "claude-opus-5",
        "effort": "high",
        "skill_sha256": "d" * 64,
    }
    write_json(b.manifest, manifest)
    assert any("propose" in reason for reason in comparability(a, b))


def test_an_unreadable_manifest_makes_the_runs_incomparable_rather_than_equal(tmp_path):
    """Absence must not read as agreement.

    Two runs whose manifests cannot be read would otherwise both yield empty
    digest sets, and jaccard(empty, empty) is 1.0 -- the runs would be declared
    perfectly comparable *because* nothing could be checked.
    """
    a, b = _pair(tmp_path)
    b.manifest.unlink()
    assert comparability(a, b) != []


# -- diff_runs ---------------------------------------------------------------


def test_two_identical_runs_are_stable_everywhere(tmp_path):
    a, b = _pair(tmp_path)
    report = diff_runs(a, b)
    assert report["comparable"] is True
    assert report["incomparable_reasons"] == []
    for stage in ("1b_capabilities", "2_goal_cell_claims", "6_task_ids"):
        assert report["stages"][stage]["jaccard"] == 1.0
        assert report["stages"][stage]["only_a"] == []
        assert report["stages"][stage]["only_b"] == []


def test_every_number_arrives_with_its_set_sizes(tmp_path):
    """A jaccard of 1.0 over two empty sets is true and reads as success.

    Only the sizes make that visible, which is why the metric's own docstring
    requires every caller to report them.
    """
    from testgen.paths import RunPaths

    a, b = RunPaths(tmp_path / "x"), RunPaths(tmp_path / "y")
    a.root.mkdir(parents=True)
    b.root.mkdir(parents=True)
    stage = diff_runs(a, b)["stages"]["6_task_ids"]
    assert stage["jaccard"] == 1.0
    assert (stage["a_size"], stage["b_size"]) == (0, 0)


def test_a_capability_only_one_run_found_is_named(tmp_path):
    """A bare 0.5 tells nobody which capability moved."""
    a, b = _pair(tmp_path)
    world = minimal_world_model()
    world["capabilities"][0]["id"] = "cap-renamed"
    write_json(b.world_model, world)
    stage = diff_runs(a, b)["stages"]["1b_capabilities"]
    assert stage["only_a"] == ["cap-find-jobs"]
    assert stage["only_b"] == ["cap-renamed"]
    assert stage["jaccard"] == 0.0


def test_a_goal_cell_claim_difference_is_rendered_as_a_readable_triple(tmp_path):
    a, b = _pair(tmp_path)
    write_json(b.scenarios, minimal_scenarios(scenarios=[]))
    stage = diff_runs(a, b)["stages"]["2_goal_cell_claims"]
    assert stage["only_a"] == ["goal-triage/cap-find-jobs/oc-success"]
    assert stage["only_b"] == []


def test_the_stage_variance_is_still_reported_when_the_runs_are_incomparable(tmp_path):
    """Refusing to report would hide the localization that is the whole point.

    An incomparable pair is often the interesting one -- the report says so and
    reports the numbers anyway, so a reader can see that stage 2 diverged *and*
    that the inputs differed.
    """
    a, b = _pair(tmp_path)
    manifest = read_json(b.manifest)
    manifest["inputs"][0]["sha256"] = "f" * 64
    write_json(b.manifest, manifest)
    report = diff_runs(a, b)
    assert report["comparable"] is False
    assert report["stages"]["1b_capabilities"]["jaccard"] == 1.0


def test_the_report_names_both_runs_and_is_deterministic(tmp_path):
    a, b = _pair(tmp_path)
    report = diff_runs(a, b)
    assert report["a"] == str(a.root)
    assert report["b"] == str(b.root)
    assert report == diff_runs(a, b)
    assert "format" in report


def test_stage_config_and_input_digests_read_what_the_manifest_records(tmp_path):
    run = build_state(tmp_path, "intake")
    manifest = minimal_manifest()
    assert stage_config(run) == manifest["stages"]
    assert input_digests(run) == frozenset(
        {(manifest["inputs"][0]["artifact_id"], manifest["inputs"][0]["sha256"])}
    )
```

- [ ] **Step 2: Run them to verify they fail, then implement**

Create `src/testgen/stability.py`:

```python
"""diff-runs: attribute variance to a stage instead of to "the pipeline".

Design spec section 291. Three Jaccards -- capability ids after 1b, goal-by-cell
claims after 2, emitted task ids after 6 -- so a reader can tell "stage 2 is
nondeterministic and everything downstream is stable given a fixed 02" from "the
whole thing is unstable". That distinction is the only reason to measure it.

Two disciplines, both load-bearing.

**Comparability is a precondition.** Two runs are comparable only if they read the
same input bytes and ran each stage under the same model, effort and skill hash. A
stability number over different inputs measures the inputs.

**Every number is reported with its set sizes and its difference.** jaccard's own
docstring requires it: a bare 1.0 over two runs that emitted nothing reads as
perfect stability, and a bare 0.4 tells nobody which capability moved.

This tool writes nothing. It spans two runs and belongs to neither, so its report
goes to stdout as JSON and its exit code is 0 -- like dedupe-candidates.
Incomparability is data inside that JSON plus a warning on stderr, not a finding:
exit 1 means finding lines on stdout, and a JSON document mixed with them would
break the orchestrator's line parser.
"""

from __future__ import annotations

from typing import Any

from testgen.artifacts import ArtifactError, read_json
from testgen.metrics import jaccard
from testgen.paths import RunPaths
from testgen.refs import OPEN_STATUSES

_STAGE_FIELDS = ("model", "effort", "skill_sha256")


def _load(path) -> Any | None:
    """None for absent or unparseable, so diff-runs works on a run that halted.

    Comparing a complete run against one that stopped after propose is exactly the
    comparison that localizes where reproducibility broke, so an absent artifact
    is data rather than an error. `comparability` treats an unreadable *manifest*
    separately, because there absence must not read as agreement.
    """
    try:
        return read_json(path)
    except ArtifactError:
        return None


def input_digests(run: RunPaths) -> frozenset[tuple[str, str]]:
    """(artifact_id, sha256) for every registered input."""
    manifest = _load(run.manifest)
    if not isinstance(manifest, dict):
        return frozenset()
    return frozenset(
        (entry["artifact_id"], entry["sha256"]) for entry in manifest.get("inputs", [])
    )


def stage_config(run: RunPaths) -> dict[str, dict[str, Any]]:
    """The manifest's per-stage model, effort and skill hash."""
    manifest = _load(run.manifest)
    if not isinstance(manifest, dict):
        return {}
    return manifest.get("stages", {})


def capability_ids(run: RunPaths) -> frozenset[str]:
    """Stage 1b's product: what the reconciled world model says the target can do."""
    world = _load(run.world_model)
    if not isinstance(world, dict):
        return frozenset()
    return frozenset(
        capability["id"] for capability in world.get("capabilities", []) if "id" in capability
    )


def goal_cell_claims(run: RunPaths) -> frozenset[tuple[str, str, str]]:
    """Stage 2's product: (goal, capability, outcome class) triples the run claims.

    Only scenarios the pipeline has not discarded. A `duplicate` or `rejected`
    scenario produced no test, so counting its claims would report stability in
    coverage the run did not deliver.
    """
    document = _load(run.scenarios)
    if not isinstance(document, dict):
        return frozenset()
    return frozenset(
        (scenario["goal_id"], ref["capability_id"], ref["outcome_class_id"])
        for scenario in document.get("scenarios", [])
        if scenario.get("status") in OPEN_STATUSES
        for ref in scenario.get("capability_refs", [])
    )


def emitted_task_ids(run: RunPaths) -> frozenset[str]:
    """Stage 6's product: the packages that shipped."""
    return frozenset(run.scenario_ids_with_tasks())


def comparability(a: RunPaths, b: RunPaths) -> list[str]:
    """Why these two runs cannot be compared. Empty means they can.

    An unreadable manifest is its own reason rather than an empty digest set:
    jaccard(empty, empty) is 1.0, so two runs whose manifests could not be read
    would otherwise be declared perfectly comparable *because* nothing was checked.
    """
    reasons: list[str] = []
    for run, label in ((a, "a"), (b, "b")):
        if not isinstance(_load(run.manifest), dict):
            reasons.append(f"run {label} has no readable manifest.json, so nothing can be pinned")
    if reasons:
        return reasons

    digests_a, digests_b = input_digests(a), input_digests(b)
    if digests_a != digests_b:
        reasons.append(
            "the two runs read different input bytes, so any stability number below measures "
            "the inputs rather than the pipeline"
        )

    stages_a, stages_b = stage_config(a), stage_config(b)
    for stage in sorted(set(stages_a) | set(stages_b)):
        if stage not in stages_a or stage not in stages_b:
            present = "a" if stage in stages_a else "b"
            reasons.append(f"stage {stage!r} is recorded only in run {present}")
            continue
        for field in _STAGE_FIELDS:
            if stages_a[stage].get(field) != stages_b[stage].get(field):
                reasons.append(
                    f"stage {stage!r} ran with a different {field}: "
                    f"{stages_a[stage].get(field)!r} against {stages_b[stage].get(field)!r}"
                )
    return reasons


def _render_member(member: Any) -> str:
    return "/".join(str(part) for part in member) if isinstance(member, tuple) else str(member)


def _stage_diff(set_a: frozenset, set_b: frozenset) -> dict[str, Any]:
    return {
        "jaccard": jaccard(set_a, set_b),
        "a_size": len(set_a),
        "b_size": len(set_b),
        "only_a": sorted(_render_member(member) for member in set_a - set_b),
        "only_b": sorted(_render_member(member) for member in set_b - set_a),
    }


def diff_runs(a: RunPaths, b: RunPaths) -> dict[str, Any]:
    """The per-stage stability report for two runs.

    The stage numbers are reported even when the runs are incomparable. An
    incomparable pair is often the interesting one, and refusing to report would
    hide exactly the localization this tool exists for -- a reader needs to see
    that stage 2 diverged *and* that the inputs differed.
    """
    reasons = comparability(a, b)
    return {
        "format": "testgen-stability/1",
        "a": str(a.root),
        "b": str(b.root),
        "comparable": not reasons,
        "incomparable_reasons": reasons,
        "stages": {
            "1b_capabilities": _stage_diff(capability_ids(a), capability_ids(b)),
            "2_goal_cell_claims": _stage_diff(goal_cell_claims(a), goal_cell_claims(b)),
            "6_task_ids": _stage_diff(emitted_task_ids(a), emitted_task_ids(b)),
        },
    }
```

Run: `uv run pytest tests/unit/test_stability.py -q` → PASS.

- [ ] **Step 3: Add the `diff-runs` subcommand**

```python
    p_diff = subparsers.add_parser("diff-runs", help="per-stage stability across two runs")
    p_diff.add_argument("--a", required=True)
    p_diff.add_argument("--b", required=True)
```

```python
        if args.command == "diff-runs":
            report = diff_runs(_run_dir(args.a), _run_dir(args.b))
            print(json.dumps(report, indent=2, sort_keys=True))
            if not report["comparable"]:
                # stderr, not a finding. Exit 1 means finding lines on stdout, and
                # a JSON document mixed with them would break the orchestrator's
                # line parser -- so incomparability is data in the JSON plus a
                # warning a human sees.
                for reason in report["incomparable_reasons"]:
                    print(f"warning: {reason}", file=sys.stderr)
            return CLEAN
```

CLI tests: exit 0 with parseable JSON on stdout for two identical runs; exit 0 with a stderr warning for two runs with different input digests; exit 2 for a nonexistent `--b`.

- [ ] **Step 4: Run the whole suite and gather mutation evidence**

Run: `uv run pytest -q` and `uv run ruff check . && uv run ruff format --check .`

```bash
export PYTHONDONTWRITEBYTECODE=1
```

| Deleted / changed | Named test that must fail |
|---|---|
| the digest comparison in `comparability` | `test_different_input_bytes_make_the_runs_incomparable` |
| the `_STAGE_FIELDS` loop | `test_a_stage_run_under_a_different_model_makes_the_runs_incomparable` |
| the stage-present-in-one branch | `test_a_stage_recorded_in_only_one_run_is_reported` |
| the unreadable-manifest early return | `test_an_unreadable_manifest_makes_the_runs_incomparable_rather_than_equal` |
| the `OPEN_STATUSES` filter | `test_a_discarded_scenario_makes_no_claim` |
| `only_a`/`only_b` from `_stage_diff` | `test_a_capability_only_one_run_found_is_named` |
| `a_size`/`b_size` from `_stage_diff` | `test_every_number_arrives_with_its_set_sizes` |
| return early when incomparable | `test_the_stage_variance_is_still_reported_when_the_runs_are_incomparable` |

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -S -s -m "feat: Add diff-runs, per-stage stability across two runs

Three Jaccards so variance can be attributed to a stage rather than to the
pipeline, each reported with its set sizes and its difference -- a bare 1.0 over
two runs that emitted nothing reads as perfect stability, and a bare 0.4 names no
capability.

Comparability is a precondition rather than a caveat: runs that read different
input bytes, or ran a stage under a different model, effort or skill hash, are
declared incomparable. An unreadable manifest is its own reason, because an empty
digest set would otherwise make two unpinnable runs look identical.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 12: `sample-for-review`

Design spec §7: a stratified review packet — instruction, seed digest, expected, rationale, adversary notes — with a fixed rubric, appended to the run so review becomes a trend line rather than an anecdote. And one instruction that decides the design: **sample preferentially from high-confidence `accept` verdicts**, because that is precisely where a correlated labeler/adversary blind spot hides. A sample drawn from the cases the adversary flagged would find only what the adversary already found.

Sampling must be deterministic — no `random`, no builtin `hash()` (salted per process), no timestamp. Ties break on `sha256` of the scenario id, which is stable across runs and machines.

The packet carries a **seed digest, not the seed.** §7 says digest, and it is right: a reviewer needs to confirm *which* world the label was authored against, and pasting a whole simulated backend into a review document buries the four questions they are there to answer.

**Files:**
- Create: `src/testgen/review.py`
- Modify: `src/testgen/cli.py`
- Modify: `tests/unit/test_refs_states.py` (extend `_measurement`)
- Test: `tests/unit/test_review.py` (create), `tests/unit/test_cli.py` (extend)

**Interfaces:**
- Produces: `review.RUBRIC`, `review.DEFAULT_SAMPLE_SIZE`, `review.confidence_band(verdict) -> str`, `review.candidates(run) -> list[dict]`, `review.stratified(entries, size) -> list[dict]`, `review.packet(run, entries) -> str`, `review.sample_run(run, size) -> tuple[list[dict], list[Finding]]`.
- CLI: `testgen sample-for-review --run DIR [--size N]`. Writes `measurement/review/packet.md` and `measurement/review/sample.json`, prints the packet path, exits 0 (or 1 with findings if there is nothing to sample).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_review.py`:

```python
"""sample-for-review: a stratified packet, drawn where the blind spot hides.

The sampling rule is the design. Drawing from the cases the adversary flagged
would find only what the adversary already found; drawing from high-confidence
accepts is what can find a correlated labeler/adversary blind spot, which is the
one failure mode design spec section 10 says the pipeline cannot fix itself.
"""

from __future__ import annotations

import json

from testgen.artifacts import read_json, write_json
from testgen.review import (
    DEFAULT_SAMPLE_SIZE,
    RUBRIC,
    candidates,
    confidence_band,
    packet,
    sample_run,
    stratified,
)
from tests.builders import minimal_scenarios, minimal_verdict
from tests.unit.test_refs_states import build_state

SID = "scn-001"


def _entry(sid, band="high", hop_depth=2):
    return {"scenario_id": sid, "band": band, "hop_depth": hop_depth}


# -- confidence_band ---------------------------------------------------------


def test_an_unqualified_accept_is_high_confidence():
    assert confidence_band(minimal_verdict()) == "high"


def test_an_accept_the_adversary_qualified_is_low_confidence():
    for key in ("uniquely_determined", "derivable_without_guessing"):
        assert confidence_band(minimal_verdict(**{key: False, "alternative_answers": [
            {"answer": "other", "world_consistent_reason": "also consistent"}
        ]})) == "low"


def test_a_non_accept_verdict_is_low_confidence():
    assert confidence_band(minimal_verdict(verdict="re-seed")) == "low"


# -- candidates --------------------------------------------------------------


def test_only_emitted_scenarios_are_reviewable(tmp_path):
    """A reviewer can only act on a task that shipped."""
    run = build_state(tmp_path, "emit")
    assert [entry["scenario_id"] for entry in candidates(run)] == [SID]
    assert candidates(run)[0]["band"] == "high"
    assert candidates(run)[0]["hop_depth"] == 2


def test_a_scenario_with_no_verdict_is_low_confidence_not_excluded(tmp_path):
    """Excluding it would hide exactly the package that most needs a human."""
    run = build_state(tmp_path, "emit")
    run.verdict(SID).unlink()
    assert candidates(run)[0]["band"] == "low"


# -- stratified --------------------------------------------------------------


def test_high_confidence_entries_come_first():
    entries = [_entry("a", band="low"), _entry("b", band="high")]
    assert [e["scenario_id"] for e in stratified(entries, 1)] == ["b"]


def test_the_sample_spreads_across_hop_depths_before_going_deep():
    """Stratified, not just top-ranked.

    Three samples all at hop depth 1 would tell a reviewer nothing about whether
    the deep scenarios are fair.
    """
    entries = [
        _entry("a1", hop_depth=1),
        _entry("a2", hop_depth=1),
        _entry("a3", hop_depth=1),
        _entry("b1", hop_depth=3),
    ]
    sampled = stratified(entries, 2)
    assert sorted(e["hop_depth"] for e in sampled) == [1, 3]


def test_the_sample_is_deterministic():
    """No random, no builtin hash (salted per process), no timestamp.

    A sample that moved between runs would make the review trend line meaningless
    -- a change in the scores could not be told from a change in the sample.
    """
    entries = [_entry(f"scn-{i:03d}", hop_depth=(i % 3) + 1) for i in range(20)]
    first = [e["scenario_id"] for e in stratified(entries, 5)]
    assert first == [e["scenario_id"] for e in stratified(list(reversed(entries)), 5)]


def test_asking_for_more_than_exists_returns_everything():
    entries = [_entry("a"), _entry("b")]
    assert len(stratified(entries, 10)) == 2


def test_asking_for_none_returns_nothing():
    assert stratified([_entry("a")], 0) == []


def test_a_low_band_entry_is_included_once_the_high_band_runs_out():
    """The preference is a preference, not an exclusion.

    A suite where the adversary qualified everything would otherwise produce an
    empty packet -- the run most in need of review producing the least of it.
    """
    entries = [_entry("a", band="high"), _entry("b", band="low")]
    assert len(stratified(entries, 2)) == 2


# -- packet ------------------------------------------------------------------


def test_the_packet_carries_the_five_things_the_spec_names(tmp_path):
    run = build_state(tmp_path, "emit")
    text = packet(run, candidates(run))
    assert "A job failed on prod0" in text, "instruction"
    assert "sha256" in text.lower(), "seed digest"
    assert "90420" in text, "expected"
    assert "answered independently from the seed" in text, "adversary notes"
    for item in RUBRIC:
        assert item.replace("_", " ") in text.replace("_", " ")


def test_the_packet_carries_the_seed_digest_and_not_the_seed(tmp_path):
    """Section 7 says digest.

    A reviewer needs to confirm which world the label was authored against; the
    whole simulated backend pasted inline buries the four questions they are there
    to answer.
    """
    from testgen.artifacts import sha256_of

    run = build_state(tmp_path, "emit")
    text = packet(run, candidates(run))
    assert sha256_of(run.seed(SID))[:16] in text
    assert '"controller": "prod0"' not in text


def test_the_packet_states_why_the_sample_is_drawn_where_it_is(tmp_path):
    """Without the reason, a reader will 'fix' the sampling to be uniform."""
    run = build_state(tmp_path, "emit")
    text = packet(run, candidates(run))
    assert "blind spot" in text
    assert "high-confidence" in text


def test_the_packet_marks_each_sampled_band(tmp_path):
    run = build_state(tmp_path, "emit")
    assert "high" in packet(run, candidates(run))


def test_a_rationale_is_included_when_the_instantiate_stage_wrote_one(tmp_path):
    run = build_state(tmp_path, "emit")
    run.rationale(SID).write_text("Chose 90420 because it is the only prod0 failure.", "utf-8")
    assert "only prod0 failure" in packet(run, candidates(run))


# -- sample_run --------------------------------------------------------------


def test_sample_run_writes_the_packet_and_the_machine_readable_record(tmp_path):
    run = build_state(tmp_path, "emit")
    sampled, findings = sample_run(run, DEFAULT_SAMPLE_SIZE)
    assert findings == []
    assert run.review_packet.is_file()
    record = read_json(run.review_sample)
    assert record["run_id"] == read_json(run.manifest)["run_id"]
    assert [s["scenario_id"] for s in record["sampled"]] == [SID]
    assert record["rubric"] == list(RUBRIC)
    assert "created" not in json.dumps(record), "no timestamp: the record must be diffable"


def test_sample_run_reports_a_suite_with_nothing_to_review(tmp_path):
    run = build_state(tmp_path, "challenge")  # emit has not run
    sampled, findings = sample_run(run, DEFAULT_SAMPLE_SIZE)
    assert sampled == []
    assert len(findings) == 1
    assert "no emitted packages" in findings[0].message


def test_sample_run_reports_when_no_high_confidence_accept_exists(tmp_path):
    """The signal, not a failure.

    A suite in which the adversary qualified every accept is a suite whose review
    cannot look where the blind spot hides -- which is worth saying out loud.
    """
    run = build_state(tmp_path, "emit")
    write_json(run.verdict(SID), minimal_verdict(verdict="reject", notes="ambiguous"))
    scenarios = minimal_scenarios()
    scenarios["scenarios"][0]["status"] = "rejected"
    scenarios["scenarios"][0]["rejected_reason"] = "ambiguous"
    write_json(run.scenarios, scenarios)
    _, findings = sample_run(run, DEFAULT_SAMPLE_SIZE)
    assert any("high-confidence" in f.message for f in findings)


def test_sample_run_is_idempotent(tmp_path):
    run = build_state(tmp_path, "emit")
    sample_run(run, DEFAULT_SAMPLE_SIZE)
    first = run.review_packet.read_text()
    sample_run(run, DEFAULT_SAMPLE_SIZE)
    assert run.review_packet.read_text() == first
```

- [ ] **Step 2: Implement `review.py`**

```python
"""sample-for-review: a stratified review packet, with a fixed rubric.

Design spec section 7, and one instruction in it decides the whole design:
**sample preferentially from high-confidence `accept` verdicts.** That is where a
correlated labeler/adversary blind spot hides. A sample drawn from the cases the
adversary flagged would surface only what the adversary already found, which is
the one risk in section 10 the pipeline cannot mitigate from inside itself.

Everything here is deterministic. No `random`, no builtin `hash()` -- which is
salted per process -- and no timestamp anywhere in the output. A sample that moved
between two runs of the same suite would make the review trend line worthless,
because a change in the scores could not be told from a change in the sample.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from testgen.artifacts import ArtifactError, read_json, sha256_of, write_json
from testgen.findings import Finding
from testgen.paths import RunPaths

# Fixed, so review is a trend line rather than a fresh opinion each time.
RUBRIC = ("fair", "unambiguous", "correctly_labeled", "non_trivial")

DEFAULT_SAMPLE_SIZE = 3

_WHY_HERE = (
    "Sampled preferentially from **high-confidence `accept` verdicts** and spread across hop "
    "depths. That is deliberate: the adversary already reported what it doubted, so reviewing "
    "its doubts finds only what it found. A correlated labeler/adversary blind spot can only "
    "show up in the cases both of them were confident about, and this packet is drawn from "
    "exactly those. Do not make this sample uniform."
)


def confidence_band(verdict: dict[str, Any] | None) -> str:
    """"high" only for an accept the adversary qualified in no way.

    An absent verdict is "low" rather than excluded: a package with no adversarial
    judgement at all is the one that most needs a human, and dropping it from the
    candidate pool would hide it.
    """
    if not isinstance(verdict, dict):
        return "low"
    unqualified = (
        verdict.get("verdict") == "accept"
        and verdict.get("uniquely_determined") is True
        and verdict.get("derivable_without_guessing") is True
        and not verdict.get("flags")
    )
    return "high" if unqualified else "low"


def _load(path) -> Any | None:
    try:
        return read_json(path)
    except ArtifactError:
        return None


def candidates(run: RunPaths) -> list[dict[str, Any]]:
    """Every emitted package, with its band and its hop depth, in id order.

    Emitted packages only. A reviewer can act on a task that shipped; a scenario
    the pipeline discarded is not something to ask four questions about.
    """
    document = _load(run.scenarios) or {"scenarios": []}
    scenarios = {s["id"]: s for s in document.get("scenarios", [])}
    entries = []
    for sid in run.scenario_ids_with_tasks():
        scenario = scenarios.get(sid, {})
        entries.append(
            {
                "scenario_id": sid,
                "band": confidence_band(_load(run.verdict(sid))),
                "hop_depth": scenario.get("hop_depth", 0),
            }
        )
    return entries


def _order_key(entry: dict[str, Any]) -> tuple[int, str]:
    """Band first, then a stable digest of the id.

    sha256 rather than hash(): the builtin is salted per process, so the same
    suite would sample differently on every invocation and the trend line would
    measure the salt.
    """
    band_rank = 0 if entry["band"] == "high" else 1
    return band_rank, hashlib.sha256(entry["scenario_id"].encode("utf-8")).hexdigest()


def stratified(entries: list[dict[str, Any]], size: int) -> list[dict[str, Any]]:
    """Round-robin across hop depths, preferring the high band. Deterministic.

    Stratified rather than top-ranked: three samples all at hop depth 1 tell a
    reviewer nothing about whether the deep scenarios are fair.

    The band preference is a preference, not an exclusion. A suite in which the
    adversary qualified every accept would otherwise produce an empty packet --
    the run most in need of review producing the least of it.
    """
    if size <= 0:
        return []
    strata: dict[int, list[dict[str, Any]]] = {}
    for entry in sorted(entries, key=_order_key):
        strata.setdefault(entry["hop_depth"], []).append(entry)
    picked: list[dict[str, Any]] = []
    while len(picked) < size and any(strata.values()):
        for depth in sorted(strata):
            if len(picked) >= size:
                break
            if strata[depth]:
                picked.append(strata[depth].pop(0))
    return sorted(picked, key=_order_key)


def _section(run: RunPaths, entry: dict[str, Any]) -> list[str]:
    sid = entry["scenario_id"]
    task = run.task_dir(sid)
    verdict = _load(run.verdict(sid)) or {}
    expected = _load(run.expected(sid)) or {}
    instruction = (
        (task / "instruction.md").read_text(encoding="utf-8").strip()
        if (task / "instruction.md").is_file()
        else "(no instruction.md in the emitted package)"
    )
    digest = sha256_of(run.seed(sid)) if run.seed(sid).is_file() else "(no seed.json)"
    lines = [
        f"## `{sid}` — confidence band: **{entry['band']}**, hop depth {entry['hop_depth']}",
        "",
        "### Instruction the agent receives",
        "",
        instruction,
        "",
        f"### Seed digest\n\n`sha256:{digest}`\n",
        "The seed itself is deliberately not inlined: the digest is what confirms which world",
        "this label was authored against, and the whole simulated backend would bury the four",
        "questions below.",
        "",
        "### Reference answer and assertions",
        "",
        "```json",
        json.dumps(
            {
                "answer_reference": expected.get("answer_reference"),
                "discriminating_fact": expected.get("discriminating_fact"),
                "assertions": expected.get("assertions"),
            },
            indent=2,
            sort_keys=True,
        ),
        "```",
        "",
    ]
    if run.rationale(sid).is_file():
        lines += [
            "### Why the instantiate stage chose this world",
            "",
            run.rationale(sid).read_text(encoding="utf-8").strip(),
            "",
        ]
    lines += [
        "### Adversary notes",
        "",
        f"- **Verdict:** {verdict.get('verdict')}",
        f"- **Uniquely determined:** {verdict.get('uniquely_determined')}",
        f"- **Derivable without guessing:** {verdict.get('derivable_without_guessing')}",
        f"- **`minimum_tool_calls_found`:** {verdict.get('minimum_tool_calls_found')}",
        f"- **Notes:** {verdict.get('notes', '')}",
        "",
        "### Rubric",
        "",
    ]
    lines += [f"- [ ] **{item.replace('_', ' ')}**" for item in RUBRIC]
    lines.append("")
    return lines


def packet(run: RunPaths, entries: list[dict[str, Any]]) -> str:
    """The review packet: one section per sampled task, one fixed rubric each."""
    lines = [
        "# Review packet",
        "",
        _WHY_HERE,
        "",
        f"- **Tasks in this packet:** {len(entries)}",
        f"- **Rubric:** {', '.join(item.replace('_', ' ') for item in RUBRIC)}",
        "",
    ]
    for entry in entries:
        lines += _section(run, entry)
    return "\n".join(lines)


def sample_run(run: RunPaths, size: int = DEFAULT_SAMPLE_SIZE) -> tuple[list[dict], list[Finding]]:
    """Write the packet and the machine-readable record. -> (sampled, findings).

    sample.json carries no timestamp, so two runs of the same suite produce
    byte-identical records and a diff shows only what actually changed.
    """
    pool = candidates(run)
    if not pool:
        return [], [
            Finding(
                run.suite_dir,
                "review",
                "",
                "no emitted packages to review; emit must run before sample-for-review",
            )
        ]
    sampled = stratified(pool, size)
    findings: list[Finding] = []
    if not any(entry["band"] == "high" for entry in pool):
        findings.append(
            Finding(
                run.review_sample,
                "review",
                "",
                "no high-confidence accept exists in this suite, so the packet cannot look "
                "where a correlated labeler/adversary blind spot would hide; every accept was "
                "qualified by the adversary",
            )
        )
    run.review_dir.mkdir(parents=True, exist_ok=True)
    run.review_packet.write_text(packet(run, sampled), encoding="utf-8")
    write_json(
        run.review_sample,
        {
            "format": "testgen-review/1",
            "run_id": read_json(run.manifest)["run_id"],
            "size_requested": size,
            "sampled": sampled,
            "rubric": list(RUBRIC),
        },
    )
    return sampled, findings
```

- [ ] **Step 3: Run the tests, add the subcommand**

Run: `uv run pytest tests/unit/test_review.py -q` → PASS.

```python
    p_review = subparsers.add_parser(
        "sample-for-review", help="write a stratified review packet for the emitted suite"
    )
    p_review.add_argument("--run", required=True)
    p_review.add_argument("--size", type=int, default=DEFAULT_SAMPLE_SIZE)
```

```python
        if args.command == "sample-for-review":
            run = _run_dir(args.run)
            sampled, findings = sample_run(run, args.size)
            if sampled:
                print(run.review_packet)
            return _report(findings)
```

CLI tests: exit 0 printing the packet path; exit 1 with a finding when `emit` has not run.

- [ ] **Step 4: Extend the `measurement` state to call the real tool**

```python
def _measurement(run: RunPaths) -> None:
    report, findings = compare_run(run, _gold_path(run))
    assert findings == [], f"compare-gold in the states table: {findings}"
    sampled, findings = sample_run(run)
    assert (len(sampled), findings) == (1, []), f"sample-for-review in the states table: {findings}"
```

Extend `test_the_states_are_cumulative_so_the_last_one_is_a_complete_run` with `assert run.review_sample.is_file()`.

- [ ] **Step 5: Run the whole suite and gather mutation evidence**

Run: `uv run pytest -q` and `uv run ruff check . && uv run ruff format --check .`

```bash
export PYTHONDONTWRITEBYTECODE=1
```

| Deleted / changed | Named test that must fail |
|---|---|
| the `uniquely_determined` clause in `confidence_band` | `test_an_accept_the_adversary_qualified_is_low_confidence` |
| the `verdict == "accept"` clause | `test_a_non_accept_verdict_is_low_confidence` |
| the `isinstance(verdict, dict)` guard | `test_a_scenario_with_no_verdict_is_low_confidence_not_excluded` |
| the `band_rank` term in `_order_key` | `test_high_confidence_entries_come_first` |
| `sha256` → builtin `hash()` in `_order_key` | `test_the_sample_is_deterministic` (across processes; run pytest twice with `-p no:randomly` if needed) |
| the round-robin over `sorted(strata)` | `test_the_sample_spreads_across_hop_depths_before_going_deep` |
| filter the pool to the high band only | `test_a_low_band_entry_is_included_once_the_high_band_runs_out` |
| the digest line in `_section` | `test_the_packet_carries_the_seed_digest_and_not_the_seed` |
| inline the seed instead of its digest | the same test's second assertion |
| `_WHY_HERE` from `packet` | `test_the_packet_states_why_the_sample_is_drawn_where_it_is` |
| the no-high-band finding | `test_sample_run_reports_when_no_high_confidence_accept_exists` |
| add a timestamp to `sample.json` | `test_sample_run_writes_the_packet_and_the_machine_readable_record` |

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -S -s -m "feat: Add sample-for-review, drawn where the blind spot hides

The sampling rule is the design: preferentially from high-confidence accept
verdicts, because the adversary already reported what it doubted and reviewing its
doubts finds only what it found. A correlated labeler/adversary blind spot can
only show up in the cases both were confident about.

Deterministic throughout -- sha256 rather than the salted builtin hash, and no
timestamp in the record -- because a sample that moved between runs would make a
change in the scores indistinguishable from a change in the sample. The packet
carries the seed digest, not the seed.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 13: Documentation and the spec's own record

The spec's run-directory sketch in §4 is a *commitment*, not an illustration — the closure-and-emit build's most expensive lesson was that a plan reviewed only against itself misses exactly these. This plan added a `measurement/` subtree, a manifest field, and four subcommands. All three belong in the spec and the README before the branch closes.

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-06-skill-based-test-generator-design.md` (§4 run directory, §4 schemas, §5 note, §7, §8)

**Interfaces:** none. Documentation only.

- [ ] **Step 1: Update the spec's run-directory block (§4)**

Add `measurement/` to the block at spec line ~146, with the three sub-paths and the one-line reason the numbered prefixes were left alone:

```
  07-report.json
  measurement/            outputs of the measurement tools, which are not stages
    smoke/<role>/<sid>/    agent/ (transcript) + verifier/ (reward.json, reward.txt)
    recall.json recall.md  compare-gold
    review/                packet.md, sample.json
  decisions.md            append-only orchestrator log
```

Below the block, add: *"`measurement/` is outside the numbered prefixes on purpose. Those name pipeline stages the orchestrator dispatches, and `STAGES`/`STAGE_ARTIFACTS` must not grow an entry for a tool nothing dispatches. `diff-runs` writes nothing at all: it spans two runs and belongs to neither."*

- [ ] **Step 2: Record `stored_as` and the two config schemas (§4)**

In §4's schema list, note that the manifest's input entries carry `stored_as` — the filename inside `00-inputs/` — and why: *"so a reader re-verifying a digest does not have to re-derive intake's naming rule. Two definitions of that rule is how they drift."*

Add a sentence that two **human-authored** config files are schema'd alongside the stage artifacts — `agents-0.1.json` and `gold-0.1.json` — and state the principle: *"A schema gates artifacts the code did not write. Measurement outputs, which this project's own code writes, are gated by unit tests instead; a schema over them would only restate the writer. A failure in a human-authored config is exit 2, not exit 1: there is no stage to hand a repair prompt to."*

- [ ] **Step 3: Note the CLI shape (§5)**

Beside the `bin/{intake,validate,...}` listing, add: *"Shipped as one console script with subcommands — `testgen intake`, `testgen validate`, … — rather than a `bin/` directory of separate files. The names and the responsibilities are as listed; only the packaging differs."*

- [ ] **Step 4: Record the measurement rulings (§7)**

Under "Measurement harness", add the decisions this build made that the spec did not specify, one line each. At minimum:

- The three thresholds and their names (`WEAK_BASELINE_CEILING`, `ORACLE_FLOOR`, `PASS_THRESHOLD`/`FAIL_CEILING`) and that `broken_labels` outranks `degenerate_trivial`, with the reason.
- Means are taken over **comparable** tasks only, and an unscoreable task is neither `all_pass` nor `all_fail`.
- `smoke` scores by executing the package's **own copied** `verify.py` under `python -S` with a scrubbed environment. That is what makes the stdlib-only constraint enforced by something that runs, and it is what makes the smoke gate answer "does the emitted suite execute" rather than "does the tested verifier work".
- A non-string `result` in a transcript scores as **no answer**, not `str(value)`, and the coercion is recorded in `reward-detail.json`.
- `compare-gold` requires goal identity and scores cell overlap; matches are one-to-one and are **proposals for human confirmation**.
- `diff-runs` reports the per-stage numbers even when the runs are incomparable, and every Jaccard carries its set sizes and its difference.
- `sample-for-review` is deterministic on `sha256` and carries the seed **digest**.

- [ ] **Step 5: Update §8's carried-forward tables**

The contract-spine list is now **fully closed** — say so, and mark *re-verify input digests* as shipped in this build with `refs.check_inputs` and `manifest.stored_as`.

For the closure-and-emit list, mark the five items this build closed:

| Item | Where |
|---|---|
| Cross-check `07-report.json` against `06-suite/` | `refs.check_report`, with status as the distinguisher for the post-rejection state |
| `parse_transcript` on a non-string `result` | ruled: no answer, recorded in the detail |
| A syntactically invalid `expected.json` in a package | `verify.read_contract` refuses before `_contract_problems` |
| `emit` prunes on a repairable upstream defect | docstring corrected to describe what the code does |
| `refs._load` swallows `ArtifactError` | `check_readable`, short-circuiting `check_all` |

Leave the remaining four parked with their rulings intact: the unsafe directory name under `06-suite/`, `cli.py`'s `except Exception` blaming the artifact, `intake` sitting outside the exception net, and re-verifying digests *across* runs (now partly addressed by `diff-runs`' comparability precondition — say which part remains).

- [ ] **Step 6: Write §8's process changes for the next plan**

Replace "Three process changes for the next plan" with what is true after this build. Keep the three that still hold, and **add whatever this build actually learned** — written from the fix rounds and the whole-branch review, not from this plan's expectations. If the deletion-mutation-plus-silent-state pair worked, say what it caught and what it still missed. If a per-seam defect got through it, that is the most valuable paragraph in the document.

Plan 4 (the skills) is the first plan where prompts, not code, produce the artifacts — so note explicitly which of these process changes still apply when the producer is a model and which do not. A deletion-mutation counter has no meaning for a prompt.

- [ ] **Step 7: Update the README**

- Extend the "What is here so far" table with `smoke.py`, `recall.py`, `stability.py`, `review.py`, `metrics.py`, `errors.py`, and update the `refs.py` row.
- Add a **Measurement** section to Usage with a worked example of each of the four subcommands, including a complete `agents.json` and a two-task `gold.json` inline. A subcommand with a `--agents` flag and no example of the file is a placeholder.
- Add a short "What smoke actually tells you" block: the three verdicts, what each one indicts, and the sentence that `broken_labels` indicts the labels or the verifier rather than the agent.
- Add the recall noise caveat to the `compare-gold` example, so nobody meets the number without it.
- Update the exit-code table with the one exception: a malformed `--agents` or `--gold` file is `2`.

- [ ] **Step 8: Verify the docs against the code**

Run every command in the README against a real run directory and confirm the output matches what the README claims. A README example that does not run is worse than none.

```bash
uv run testgen --help
uv run testgen smoke --help
uv run testgen compare-gold --help
uv run testgen diff-runs --help
uv run testgen sample-for-review --help
```

Then run `make test` and `make check` one final time.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -S -s -m "docs: Record the measurement layer in the spec and the README

The spec's run-directory block is a commitment rather than an illustration -- the
last build's most expensive lesson was that a plan reviewed only against itself
misses exactly these -- so measurement/, manifest.stored_as and the four
subcommands go into section 4 alongside the schema-gating principle they follow.

Section 8's contract-spine carried-forward list is now fully closed; five of the
nine closure-and-emit items shipped in this build and four stay parked with their
rulings.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Self-Review

Indexed by **artifact × layer**, per spec §8's second process change: a table keyed on "which task implements this requirement" cannot see a structural gap, and one keyed on "which layer checks this artifact" makes it obvious.

### Artifact × layer

| Artifact | Layer 1 (schema) | Layer 2 (refs) | Layer 3 (smoke) | Written by |
|---|---|---|---|---|
| `manifest.json` | `manifest-0.1.json`, now with `stored_as` (T1) | `check_manifest`; **`check_inputs` re-hashes the stored bytes (T1)**; `check_readable` (T2) | — | `intake` |
| `00-inputs/*` | not JSON in general — no schema | `check_inputs` (T1) is the only gate, and it is the reproducibility claim's foundation | — | `intake` |
| `01-claims/*.json` | `claims-0.1.json` | `check_manifest`, `check_readable` (T2) | — | extract |
| `01-world-model.json` | `world-model-0.1.json` | `check_world_model`, `check_readable` (T2) | read by `stability.capability_ids` (T11) | reconcile |
| `02-scenarios.json` | `scenarios-0.1.json` | `check_scenarios`, `check_readable` (T2) | read by `recall`, `stability`, `review` (T9-12) | propose |
| `03-coverage/*` | `coverage-0.1.json` | `check_coverage`, `check_limits`, `check_readable` (T2) | — | score |
| `04-instances/<sid>/*` | `seed-0.1.json`, `expected-0.1.json` | `check_instances`, `check_readable` (T2) | seed digest + expected in the review packet (T12) | instantiate |
| `05-verdicts/<sid>.json` | `verdict-0.1.json` | `check_verdicts`, `check_readable` (T2) | `review.confidence_band` (T12) | challenge |
| `06-suite/<sid>/` | `suite-expected-0.1.json` | `check_suite`; `check_readable` covers `seed.json`, `golden.json`, `tests/expected.json` (T2) | **`verify_package` executes the copied `verify.py` (T5)** | `emit` |
| `07-report.json` | `report-0.1.json` | **`check_report` (T8)** — the gap that existed at the start of this plan | `smoke_run` writes it and gates on its verdict (T7) | `smoke` |
| `agents.json` (input) | `agents-0.1.json` (T4) → **exit 2** | n/a — not a run artifact | — | a human |
| `gold.json` (input) | `gold-0.1.json` (T9) → **exit 2** | n/a — not a run artifact | — | a human |
| `measurement/recall.json`, `recall.md` | none, by the stated principle | none — the `measurement` state (T8/T10) proves layer 2 stays silent | — | `compare-gold` |
| `measurement/review/*` | none, by the stated principle | none — same state | — | `sample-for-review` |
| `measurement/smoke/**` | none — logs, not artifacts | none | it *is* layer 3's working area | `smoke` |
| `diff-runs` output | none — stdout, spans two runs | n/a | — | `diff-runs` |

**Gaps this table makes visible, and the decision on each:**

- `00-inputs/*` has no layer-1 gate and cannot have one (arbitrary bytes). `check_inputs` is the *only* thing standing between a tampered input and a run that looks clean. That is why T1 checks the digest, the size, and the segment safety of `stored_as` rather than just the digest.
- The three `measurement/` artifacts have no schema **by design**, and the risk is that a future checker starts globbing the run directory and reports them. The `measurement` state in the states table (T8, filled in by T10 and T12 with the real tool output) is the counter.
- `decisions.md` is checked by nothing at any layer. Unchanged from the previous two builds, and out of scope: it is a human-readable lab notebook with no consumer in code. Noted rather than fixed.
- `measurement/smoke/**` transcripts are unvalidated by design — they are an agent's output, and `parse_transcript` is deliberately tolerant of a broken one (T3 makes every concession visible instead of silent).

### Spec coverage

| §7 requirement | Task |
|---|---|
| `smoke` runs the suite against a weak baseline, the agent under test, and an oracle | T4-T7 |
| Per-task all-pass / all-fail flags for degenerate-suite detection | T6 |
| "If the oracle does not pass, the gold labels or the verifier are broken, not the agent" | T6 (`ORACLE_FLOOR`, `broken_labels`), T7 (the finding's wording) |
| `compare-gold` matches on `capability_refs` + goal overlap, human-confirmed | T9 |
| Novelty categorized as new outcome class / new capability / new hop-depth / spurious | T10 |
| "The report must state inline that with a denominator of 10, 7/10 vs 8/10 is noise" | T10 (`caveat`, derived from the real denominator) |
| `diff-runs` reports per-stage stability — Jaccard on capability sets after 1b, goal×cell claims after 2, task ids after 6 | T11 |
| `sample-for-review` emits instruction, seed digest, expected, rationale, adversary notes, with a fixed rubric | T12 |
| "Sample preferentially from high-confidence `accept` verdicts" | T12 |
| Re-verify input digests (§8, the last contract-spine item) | T1 |
| Cross-check `07-report.json` against `06-suite/` (§8) | T8 |
| `parse_transcript` on a non-string `result` (§8) | T3 |
| Invalid `expected.json` in a package (§8) | T3 |
| `refs._load` swallows `ArtifactError` (§8) | T2 |
| `emit` prunes on a repairable upstream defect (§8) | T2 (docstring) |
| §4's run directory records the layout | T13 |

**Deliberately out of scope, and why:**

- **Executing** `diff-runs` and `sample-for-review` against real runs. §8's deferral table says build the tool in slice 1 and run it in slice 2 — the first needs 5× run cost, the second needs human time.
- The four remaining closure-and-emit items (unsafe directory name under `06-suite/`, `cli.py`'s `except Exception`, `intake` outside the exception net, cross-run digest re-verification beyond `diff-runs`' precondition). Each needs a hand-tampered artifact; each stays parked with its ruling. T13 records that they are still open.
- Plan 4's territory: the six stage skills, the orchestrator, `tg-emit`, negative refusal fixtures, and the golden end-to-end toy fixture (§9).

### Type and name consistency

Checked across tasks, since a name defined in one and used in another is exactly where these plans have gone wrong before:

- `AgentSpec` fields (`role`, `model`, `command: tuple[str, ...]`, `timeout_sec: float`, `notes: str`) are defined in T4 and used unchanged in T5 and T7.
- `parse_transcript` becomes a **4-tuple** in T3. Its seven existing call sites are named in T3 Step 5; nothing in T4-T13 calls it.
- `run_agent` returns `(int | None, str)` and `verify_package` returns `(int | None, dict | None, str)`. T7 unpacks both with `_` for the returncodes it does not use.
- `task_flags`, `summarize` and `verdict_for` take `(…, roles: tuple[str, ...])` in T6 and are called with the same signature by T7 and by T8's `check_report`.
- `refs` imports `smoke` **inside** `check_report` (T8), not at module scope. `smoke` imports `emit`; nothing imports `refs` from `smoke`, `recall`, `stability` or `review` except `stability`'s use of `OPEN_STATUSES`. No cycle.
- `paths` additions land across three tasks: `input_file` (T1), `measurement_dir` and `smoke_dir` (T5), `recall`, `review_dir`, `review_packet`, `review_sample` (T8, because the `measurement` state builder needs them to compile).
- `sha256_of` moves from `intake` to `artifacts` in T1 and is used from there by `refs` (T1) and `review` (T12). `intake.sha256_of` keeps resolving through the import.
- `UsageError` moves from `intake` to `errors` in T4 and is raised by `smoke.load_agents`, `smoke.preflight` (T4) and `recall.load_gold` (T9).
- `Finding.layer` gains three values: `"smoke"` (T7), `"recall"` (T10), `"review"` (T12). T10 Step 2 updates the docstring in `findings.py` that enumerates them — **all three**, not only `recall`.
- Measurement outputs carry `"format": "testgen-<tool>/1"` and never `schema_version`. T8's `measurement` state builder writes a stub with `schema_version`; **T10 Step 5 replaces it with the real `compare_run` output**, which is what removes the inconsistency. If T10 is implemented before T8's stub is replaced, the stub is the only place in the tree claiming a schema that does not exist.

