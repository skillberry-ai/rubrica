# Contract Closure and Emit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the nine layer-2 gaps the contract spine shipped with, then build the first consumer of the closed contract — `emit`, which compiles accepted instances into runnable Harbor task packages scored by one generic hand-written verifier.

**Architecture:** Two halves, in this order for a reason. Tasks 1–6 finish layer 2 and the schemas, because `emit` is the first component that joins ids read from artifacts into filesystem paths and into a scoring contract — every unchecked reference becomes a silently wrong score the moment it does. Tasks 7–11 then add `src/testgen/suite/verify.py` (stdlib-only, runs inside a bare container, the sole implementation of scoring semantics) and `src/testgen/emit.py` (the only Harbor-aware component). No LLM calls anywhere in this plan; every task is unit-testable.

**Tech Stack:** Python 3.13, uv, jsonschema (Draft202012Validator), tomli-w, pytest, ruff.

## Global Constraints

- **Python 3.13**, dependencies limited to `jsonschema>=4.23` and `tomli-w>=1.1`. **Do not add a runtime dependency in this plan.** Every check here is reachable with the stdlib.
- **`src/testgen/suite/verify.py` and `src/testgen/suite/test.sh` must be stdlib-only.** They are copied verbatim into a task package and executed inside `registry.access.redhat.com/ubi9/ubi:latest` with no third-party packages and no network. `verify.py` must never import `testgen`.
- **Canonical JSON for every artifact:** written only through `testgen.artifacts.write_json`, which uses `indent=2, sort_keys=True, ensure_ascii=False` plus a trailing newline. Two runs with the same content must produce byte-identical files.
- **Findings are returned, never raised.** Layer-2 checks return `list[Finding]`; the orchestrator needs the whole list for its one bounded repair attempt.
- **Exit codes are the orchestrator's contract:** `0` clean, `1` findings on stdout, `2` usage error or unreadable run. A stage defect must never surface as `2`.
- **`check_all` must stay clean on every valid partial run.** `tests/unit/test_refs_states.py` enumerates the pipeline states; a new check that fires where nothing is wrong costs the orchestrator its repair attempt on a phantom.
- **Layer-2 checks may assume layer 1 ran.** Indexing a required key directly is correct; do not add defensive `.get()` chains for shapes the schema already guarantees.
- **ruff:** `line-length = 100`, `select = ["E", "F", "I", "UP", "B", "SIM"]`. Run `make check` before every commit.
- **Commits:** `git commit -S -s` (both flags, always). Add `Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>`. Never `Co-Authored-By`.

## File Structure

| File | Responsibility |
|---|---|
| `src/testgen/refs.py` (modify) | Gains `check_manifest`, `check_limits`, `OPEN_STATUSES`, `check_suite`; `check_coverage` and `check_instances` grow. Stays the single home of layer 2. |
| `src/testgen/paths.py` (modify) | Gains `scenario_ids_with_tasks()`. Stays the single source of truth for layout. |
| `src/testgen/validate.py` (modify) | Registers the two new schemas and gives `emit` and `smoke` real layer-1 gates. |
| `src/testgen/schema/*.json` (modify) | Anchor and `created_utc` fixes; capability `binding`. |
| `src/testgen/schema/suite-expected-0.1.json` (create) | The scoring contract `verify.py` consumes. |
| `src/testgen/schema/report-0.1.json` (create) | The smoke report's contract, written before its producer exists. |
| `src/testgen/suite/__init__.py` (create) | Marks the template directory a package so tests import the tracked original. |
| `src/testgen/suite/verify.py` (create) | The sole implementation of scoring semantics. Stdlib-only. |
| `src/testgen/suite/test.sh` (create) | Harbor verifier entrypoint. Copied verbatim. |
| `src/testgen/emit.py` (create) | Translation and package writing. The only Harbor-aware module. |
| `src/testgen/cli.py` (modify) | Adds the `emit` subcommand. |
| `tests/builders.py` (modify) | Payloads stay mutually consistent as checks tighten. |

---

### Task 1: Manifest referential integrity

Layer 2 never reads `manifest.json` today, so the chain `manifest.inputs[].artifact_id` → `01-claims/<aid>.json` filename → that file's own `artifact_id` → `claims[].evidence[].artifact_id` is entirely unchecked. `_claim_ids` also unions ids into a set, so two claims files defining the same claim id merge silently — every world-model reference to that id then resolves to an ambiguity that reads as clean.

**Files:**
- Modify: `src/testgen/refs.py` (add `_claim_index`, rewrite `_claim_ids`, add `check_manifest`, register it in `check_all`)
- Test: `tests/unit/test_refs_manifest.py` (create)

**Interfaces:**
- Consumes: `testgen.artifacts.read_json`, `testgen.findings.Finding`, `testgen.paths.RunPaths`, the existing `_load` helper.
- Produces: `refs.check_manifest(run: RunPaths) -> list[Finding]`; `refs._claim_index(run: RunPaths) -> dict[str, list[Path]]` mapping each claim id to one entry per definition site.

**Direction matters.** Check claims → manifest, never manifest → claims. During the extract fan-out most inputs have no claims file yet, and that absence is `validate_stage`'s business, not this module's. A check in the other direction would fire on every valid partial state.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_refs_manifest.py`:

```python
"""check_manifest: the manifest against 01-claims, and evidence against the manifest."""

from __future__ import annotations

from testgen.artifacts import write_json
from testgen.paths import RunPaths
from testgen.refs import check_manifest
from tests.builders import minimal_claims, minimal_manifest


def _run(tmp_path, manifest=None, claims=None) -> RunPaths:
    """A run holding a manifest and zero or more claims files keyed by artifact id."""
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    write_json(run.manifest, manifest if manifest is not None else minimal_manifest())
    for artifact_id, payload in (claims or {}).items():
        write_json(run.claims(artifact_id), payload)
    return run


def _messages(findings) -> str:
    return " || ".join(f.message for f in findings)


def test_a_consistent_manifest_and_claims_file_is_clean(tmp_path):
    run = _run(tmp_path, claims={"aap2-api": minimal_claims()})
    assert check_manifest(run) == []


def test_no_manifest_is_not_a_finding(tmp_path):
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    assert check_manifest(run) == []


def test_a_registered_input_with_no_claims_file_is_not_a_finding(tmp_path):
    """The normal state during the extract fan-out; firing here is a phantom."""
    run = _run(tmp_path)
    assert check_manifest(run) == []


def test_a_claims_file_naming_an_unregistered_artifact_is_reported(tmp_path):
    run = _run(tmp_path, claims={"ghost": minimal_claims(artifact_id="ghost")})
    findings = check_manifest(run)
    assert len(findings) == 1
    assert "not registered in the manifest" in findings[0].message


def test_a_claims_filename_that_disagrees_with_its_artifact_id_is_reported(tmp_path):
    run = _run(tmp_path, claims={"aap2-api": minimal_claims(artifact_id="something-else")})
    messages = _messages(check_manifest(run))
    assert "is named aap2-api.json" in messages


def test_evidence_citing_an_unregistered_artifact_is_reported(tmp_path):
    claims = minimal_claims()
    claims["claims"][0]["evidence"][0]["artifact_id"] = "never-registered"
    run = _run(tmp_path, claims={"aap2-api": claims})
    findings = check_manifest(run)
    assert len(findings) == 1
    assert findings[0].pointer == "/claims/0/evidence/0/artifact_id"
    assert "never-registered" in findings[0].message


def test_the_same_claim_id_in_two_files_is_reported(tmp_path):
    """The reconciliation hazard: a set would merge these and read as clean."""
    manifest = minimal_manifest()
    manifest["inputs"].append(
        {
            "artifact_id": "aap2-schema",
            "source_path": "harness-skills/parsec-aap2/schema.json",
            "sha256": "c" * 64,
            "kind": "entity_schema",
            "bytes": 2048,
        }
    )
    second = minimal_claims(artifact_id="aap2-schema")
    second["claims"][0]["evidence"][0]["artifact_id"] = "aap2-schema"
    run = _run(
        tmp_path,
        manifest=manifest,
        claims={"aap2-api": minimal_claims(), "aap2-schema": second},
    )
    messages = _messages(check_manifest(run))
    assert "'clm-001' is defined more than once" in messages
    assert "aap2-api.json, aap2-schema.json" in messages


def test_the_same_claim_id_twice_in_one_file_is_reported(tmp_path):
    claims = minimal_claims()
    claims["claims"].append(dict(claims["claims"][0]))
    run = _run(tmp_path, claims={"aap2-api": claims})
    messages = _messages(check_manifest(run))
    assert "'clm-001' is defined more than once" in messages


def test_a_duplicate_registered_artifact_id_is_reported(tmp_path):
    manifest = minimal_manifest()
    manifest["inputs"].append(dict(manifest["inputs"][0]))
    run = _run(tmp_path, manifest=manifest)
    messages = _messages(check_manifest(run))
    assert "already registered at /inputs/0" in messages


def test_an_unparseable_created_utc_is_reported(tmp_path):
    """The schema's pattern catches shape; only a parse catches month 13."""
    run = _run(tmp_path, manifest=minimal_manifest(created_utc="2026-13-45T99:99:99Z"))
    findings = check_manifest(run)
    assert len(findings) == 1
    assert findings[0].pointer == "/created_utc"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_refs_manifest.py -q`
Expected: FAIL — `ImportError: cannot import name 'check_manifest' from 'testgen.refs'`

- [ ] **Step 3: Add the claim index and rewrite `_claim_ids`**

In `src/testgen/refs.py`, add `from datetime import datetime` and `from pathlib import Path` to the imports, then replace the existing `_claim_ids` function with both of these:

```python
def _claim_index(run: RunPaths) -> dict[str, list[Path]]:
    """Claim id -> every claims file defining it, one entry per definition.

    A list rather than a set: two definitions of one id in the *same* file is
    as much of a reconciliation hazard as two across files, and a set would
    hide it. check_manifest reports any id with more than one entry.
    """
    index: dict[str, list[Path]] = {}
    if not run.claims_dir.is_dir():
        return index
    for path in sorted(run.claims_dir.glob("*.json")):
        payload = _load(path)
        if not isinstance(payload, dict):
            continue
        for claim in payload.get("claims", []):
            if "id" in claim:
                index.setdefault(claim["id"], []).append(path)
    return index


def _claim_ids(run: RunPaths) -> set[str]:
    """Every claim id across every 01-claims file."""
    return set(_claim_index(run))
```

- [ ] **Step 4: Add `check_manifest`**

Insert into `src/testgen/refs.py` immediately before `check_world_model`:

```python
def check_manifest(run: RunPaths) -> list[Finding]:
    """The manifest against 01-claims, and each claim's evidence against the manifest.

    Checked in one direction only: every claims file must name a registered
    input, never the reverse. A registered input with no claims file yet is the
    normal state during the extract fan-out, and reporting it there would fire
    on a run in which nothing is wrong.
    """
    manifest = _load(run.manifest)
    if manifest is None:
        return []
    out: list[Finding] = []

    def report(pointer: str, message: str) -> None:
        out.append(Finding(run.manifest, "refs", pointer, message))

    # The schema constrains created_utc's shape; only a parse rejects month 13
    # or hour 99. Layer 1 cannot express that and jsonschema's date-time format
    # is a no-op without rfc3339-validator, which this project does not depend on.
    created = manifest.get("created_utc")
    try:
        datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        report(
            "/created_utc",
            f"{created!r} is not a real UTC timestamp of the form YYYY-MM-DDTHH:MM:SSZ",
        )

    registered: dict[str, int] = {}
    for i, entry in enumerate(manifest.get("inputs", [])):
        artifact_id = entry["artifact_id"]
        if artifact_id in registered:
            report(
                f"/inputs/{i}/artifact_id",
                f"artifact_id {artifact_id!r} is already registered at "
                f"/inputs/{registered[artifact_id]}",
            )
            continue
        registered[artifact_id] = i

    for claim_id, paths in sorted(_claim_index(run).items()):
        if len(paths) > 1:
            names = ", ".join(sorted(p.name for p in paths))
            out.append(
                Finding(
                    run.claims_dir,
                    "refs",
                    "",
                    f"claim id {claim_id!r} is defined more than once, in {names}; every "
                    "world-model reference to it would resolve ambiguously",
                )
            )

    if not run.claims_dir.is_dir():
        return out

    for path in sorted(run.claims_dir.glob("*.json")):
        payload = _load(path)
        if not isinstance(payload, dict):
            continue
        declared = payload.get("artifact_id")
        if declared != path.stem:
            out.append(
                Finding(
                    path,
                    "refs",
                    "/artifact_id",
                    f"file declares artifact_id {declared!r} but is named {path.name}; the "
                    "filename is how every other stage addresses it",
                )
            )
        elif declared not in registered:
            out.append(
                Finding(
                    path,
                    "refs",
                    "/artifact_id",
                    f"artifact_id {declared!r} is not registered in the manifest",
                )
            )
        for i, claim in enumerate(payload.get("claims", [])):
            for j, evidence in enumerate(claim.get("evidence", [])):
                if evidence["artifact_id"] not in registered:
                    out.append(
                        Finding(
                            path,
                            "refs",
                            f"/claims/{i}/evidence/{j}/artifact_id",
                            f"evidence cites unregistered artifact: {evidence['artifact_id']}",
                        )
                    )
    return out
```

Note the `elif` on the filename branch: when a file is both misnamed and unregistered, one finding naming the real problem beats two describing the same defect twice.

- [ ] **Step 5: Register it in `check_all`**

In `src/testgen/refs.py`, add `check_manifest` as the first entry of `check_all`:

```python
def check_all(run: RunPaths) -> list[Finding]:
    """Every layer-2 check that the run directory currently has inputs for."""
    findings: list[Finding] = []
    findings.extend(check_manifest(run))
    findings.extend(check_world_model(run))
    findings.extend(check_scenarios(run))
    findings.extend(check_coverage(run))
    findings.extend(check_instances(run))
    findings.extend(check_verdicts(run))
    return findings
```

- [ ] **Step 6: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS. `tests/unit/test_refs_states.py` must stay green — `minimal_manifest` registers `aap2-api` and `minimal_claims` declares it, so the states table is already consistent. If it fails, the builders disagree and the builders are what to fix.

- [ ] **Step 7: Lint and commit**

```bash
make check
git add src/testgen/refs.py tests/unit/test_refs_manifest.py
git commit -S -s -m "feat: Check the manifest-to-claims chain and claim id uniqueness

Layer 2 never read manifest.json, so the chain from a registered input
through a claims filename to each claim's evidence was unchecked, and
_claim_ids unioned ids into a set -- two files defining one claim id
merged silently and every world-model reference to it read as clean.

Checked in one direction only: a registered input with no claims file yet
is the normal state during the extract fan-out.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 2: Enforce the manifest's limits

`max_rounds` and `max_scenarios` are written by intake and read by nothing. A scenarios document tagged `round: 99` under `max_rounds: 2`, or 400 scenarios under a cap of 8, passes both layers today — so the loop bound that keeps run cost finite is documentation, not a constraint.

**Files:**
- Modify: `src/testgen/refs.py` (add `OPEN_STATUSES` and `check_limits`, register in `check_all`)
- Modify: `src/testgen/dedupe.py` (import the shared status set instead of defining its own)
- Test: `tests/unit/test_refs_limits.py` (create)

**Interfaces:**
- Consumes: `refs._load`, `testgen.findings.Finding`, `testgen.paths.RunPaths`.
- Produces: `refs.OPEN_STATUSES: frozenset[str]` = `{"proposed", "active"}`; `refs.check_limits(run: RunPaths) -> list[Finding]`.

**What the scenario cap counts.** Only `proposed` and `active` scenarios. A `duplicate` or `rejected` one costs no per-scenario fan-out, which is the cost the cap exists to bound, and counting them would make the cap tighten as the pipeline correctly discards work.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_refs_limits.py`:

```python
"""check_limits: the manifest's loop and suite bounds, enforced."""

from __future__ import annotations

from testgen.artifacts import write_json
from testgen.paths import RunPaths
from testgen.refs import check_limits
from tests.builders import minimal_coverage, minimal_manifest, minimal_scenarios


def _run(tmp_path, *, manifest=None, scenarios=None, coverage=None) -> RunPaths:
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    write_json(run.manifest, manifest if manifest is not None else minimal_manifest())
    if scenarios is not None:
        write_json(run.scenarios, scenarios)
    if coverage is not None:
        write_json(run.coverage_latest, coverage)
    return run


def _messages(findings) -> str:
    return " || ".join(f.message for f in findings)


def _scenario(sid: str, **over):
    base = dict(minimal_scenarios()["scenarios"][0])
    base["id"] = sid
    base.update(over)
    return base


def test_a_run_inside_its_limits_is_clean(tmp_path):
    run = _run(tmp_path, scenarios=minimal_scenarios(), coverage=minimal_coverage())
    assert check_limits(run) == []


def test_no_manifest_means_nothing_to_enforce(tmp_path):
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    write_json(run.scenarios, minimal_scenarios())
    assert check_limits(run) == []


def test_a_scenario_beyond_max_rounds_is_reported(tmp_path):
    scenarios = minimal_scenarios(scenarios=[_scenario("scn-001", round=99)])
    run = _run(tmp_path, scenarios=scenarios)
    messages = _messages(check_limits(run))
    assert "round 99" in messages
    assert "max_rounds=2" in messages


def test_a_provenance_round_beyond_max_rounds_is_reported(tmp_path):
    scenario = _scenario("scn-001")
    scenario["provenance"] = dict(scenario["provenance"], round=7)
    run = _run(tmp_path, scenarios=minimal_scenarios(scenarios=[scenario]))
    findings = check_limits(run)
    assert [f.pointer for f in findings] == ["/scenarios/0/provenance/round"]


def test_too_many_open_scenarios_is_reported(tmp_path):
    manifest = minimal_manifest(limits={"max_rounds": 2, "max_scenarios": 2})
    scenarios = minimal_scenarios(
        scenarios=[_scenario("scn-001"), _scenario("scn-002"), _scenario("scn-003")]
    )
    run = _run(tmp_path, manifest=manifest, scenarios=scenarios)
    messages = _messages(check_limits(run))
    assert "3 scenarios are proposed or active" in messages
    assert "max_scenarios=2" in messages


def test_duplicate_and_rejected_scenarios_do_not_count_against_the_cap(tmp_path):
    """The cap bounds per-scenario fan-out cost, which discarded work does not incur."""
    manifest = minimal_manifest(limits={"max_rounds": 2, "max_scenarios": 1})
    scenarios = minimal_scenarios(
        scenarios=[
            _scenario("scn-001"),
            _scenario("scn-002", status="duplicate", duplicate_of="scn-001"),
            _scenario("scn-003", status="rejected", rejected_reason="ambiguous"),
        ]
    )
    run = _run(tmp_path, manifest=manifest, scenarios=scenarios)
    assert check_limits(run) == []


def test_a_coverage_round_beyond_max_rounds_is_reported(tmp_path):
    run = _run(tmp_path, coverage=minimal_coverage(round=5))
    findings = check_limits(run)
    assert len(findings) == 1
    assert findings[0].artifact == run.coverage_latest
    assert findings[0].pointer == "/round"


def test_the_cap_is_a_ceiling_not_an_equality(tmp_path):
    manifest = minimal_manifest(limits={"max_rounds": 9, "max_scenarios": 9})
    run = _run(tmp_path, manifest=manifest, scenarios=minimal_scenarios())
    assert check_limits(run) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_refs_limits.py -q`
Expected: FAIL — `ImportError: cannot import name 'check_limits' from 'testgen.refs'`

- [ ] **Step 3: Add `OPEN_STATUSES` and `check_limits`**

In `src/testgen/refs.py`, add the constant just below the `_GOAL_RE` definition:

```python
# A scenario that still counts: one the pipeline has not discarded. Shared with
# dedupe.py, which must exclude the same set -- re-proposing a pair resolved in
# an earlier round is how the enrichment loop fails to converge.
OPEN_STATUSES = frozenset({"proposed", "active"})
```

Then insert `check_limits` immediately after `check_manifest`:

```python
def check_limits(run: RunPaths) -> list[Finding]:
    """The manifest's loop and suite bounds against what the run actually holds.

    intake writes these and, until now, nothing read them. They are the reason
    run cost is finite, so an unenforced cap is not a documentation gap: it is
    the absence of the bound.
    """
    manifest = _load(run.manifest)
    if manifest is None:
        return []
    limits = manifest.get("limits", {})
    max_rounds = limits.get("max_rounds")
    max_scenarios = limits.get("max_scenarios")
    out: list[Finding] = []

    scenarios_doc = _load(run.scenarios)
    if scenarios_doc is not None:
        scenarios = scenarios_doc.get("scenarios", [])

        def report(pointer: str, message: str) -> None:
            out.append(Finding(run.scenarios, "refs", pointer, message))

        if isinstance(max_rounds, int):
            for i, scenario in enumerate(scenarios):
                if scenario["round"] > max_rounds:
                    report(
                        f"/scenarios/{i}/round",
                        f"scenario is tagged round {scenario['round']} but the manifest caps "
                        f"the enrichment loop at max_rounds={max_rounds}",
                    )
                provenance_round = scenario.get("provenance", {}).get("round")
                if isinstance(provenance_round, int) and provenance_round > max_rounds:
                    report(
                        f"/scenarios/{i}/provenance/round",
                        f"provenance records round {provenance_round} but the manifest caps "
                        f"the enrichment loop at max_rounds={max_rounds}",
                    )
        if isinstance(max_scenarios, int):
            open_count = sum(1 for s in scenarios if s.get("status") in OPEN_STATUSES)
            if open_count > max_scenarios:
                report(
                    "/scenarios",
                    f"{open_count} scenarios are proposed or active but the manifest caps the "
                    f"suite at max_scenarios={max_scenarios}; duplicate and rejected scenarios "
                    "do not count against it",
                )

    coverage = _load(run.coverage_latest)
    if coverage is not None and isinstance(max_rounds, int) and coverage["round"] > max_rounds:
        out.append(
            Finding(
                run.coverage_latest,
                "refs",
                "/round",
                f"coverage is reported for round {coverage['round']} but the manifest caps the "
                f"enrichment loop at max_rounds={max_rounds}",
            )
        )
    return out
```

- [ ] **Step 4: Register it in `check_all`**

Add `findings.extend(check_limits(run))` immediately after the `check_manifest` line in `check_all`.

- [ ] **Step 5: Point `dedupe` at the shared set**

In `src/testgen/dedupe.py`, change the import line and delete the local constant:

```python
from testgen.refs import OPEN_STATUSES, cell_ref
```

Delete the `_OPEN_STATUSES = frozenset({"proposed", "active"})` line, and in `candidate_pairs` change the filter to `if s.get("status") in OPEN_STATUSES`. `dedupe` already imports from `refs`, so this adds no new dependency direction — it removes a second definition of one concept that had a live chance to drift.

- [ ] **Step 6: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 7: Lint and commit**

```bash
make check
git add src/testgen/refs.py src/testgen/dedupe.py tests/unit/test_refs_limits.py
git commit -S -s -m "feat: Enforce the manifest's round and scenario limits

max_rounds and max_scenarios were written by intake and read by nothing,
so the bound that keeps run cost finite was documentation. A scenarios
document tagged round 99 under a cap of 2 passed both layers.

The scenario cap counts only proposed and active scenarios, since the
cost it bounds is per-scenario fan-out and discarded work incurs none.
dedupe.py now imports that status set rather than defining its own.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 3: Scope the oracle to what its scenario claimed

Two gaps, one loop, so one task. §4 makes `discriminating_fact` the mechanism that stops instantiate inventing an easier world than the one proposed, but nothing compares the two strings — the field is decorative. And `trajectory.operations[].capability_id` is checked against the world model but not against the scenario's own `capability_refs`, so an instance can exercise capabilities the scenario never declared while coverage credits the scenario for cells it does not test. Coverage becomes confidently wrong with no finding.

**Files:**
- Modify: `src/testgen/refs.py` (`_check_reachability` gains a parameter; `check_instances` compares the fact)
- Test: `tests/unit/test_refs_instance.py` (extend)

**Interfaces:**
- Consumes: everything Task 1 and 2 added.
- Produces: `refs._check_reachability(report, world, seed, expected, scenario_caps: set[str]) -> None` — one added positional parameter. No other caller exists.

**`tool_not_called` is deliberately exempt.** "Must not call the delete capability" is a legitimate assertion about a capability the scenario never claimed — that is the whole point of a forbidden-call check. So `tool_called` and `trajectory.operations` are constrained to the scenario's refs; `tool_not_called` needs only to name a real capability.

**Equality, not similarity, for `discriminating_fact`.** The scenario declares it; instantiate's job is to *realize* it in a seed, not to rewrite it. A paraphrase is indistinguishable from a quiet substitution of an easier fact, and the check that cannot tell them apart is worth nothing. The finding text tells the stage to copy it verbatim.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_refs_instance.py`. Read the file first for its existing fixture helpers and reuse them; if it has no helper that writes a full instance, use this shape:

```python
def test_an_expected_whose_discriminating_fact_differs_is_reported(tmp_path):
    """The field is the contract stage 4 builds to; a paraphrase hides a substitution."""
    run = _instantiated_run(tmp_path)
    expected = minimal_expected(discriminating_fact="some prod0 job failed at some point")
    write_json(run.expected("scn-001"), expected)
    messages = " || ".join(f.message for f in check_instances(run))
    assert "discriminating_fact" in messages
    assert "verbatim" in messages


def test_a_matching_discriminating_fact_is_clean(tmp_path):
    run = _instantiated_run(tmp_path)
    scenario_fact = minimal_scenarios()["scenarios"][0]["discriminating_fact"]
    write_json(run.expected("scn-001"), minimal_expected(discriminating_fact=scenario_fact))
    assert check_instances(run) == []


def test_a_trajectory_operation_outside_the_scenarios_capability_refs_is_reported(tmp_path):
    """Coverage credits the scenario for cells the instance never exercises."""
    run = _instantiated_run(tmp_path)
    world = minimal_world_model()
    world["capabilities"].append(
        {
            "id": "cap-get-log",
            "operation": "query_aap2.get_job_log",
            "params": [{"name": "job_id", "type": "integer", "required": True}],
            "outcome_classes": [
                {"id": "oc-success", "kind": "success", "description": "log returned"}
            ],
            "claims": ["clm-001"],
            "confidence": "high",
        }
    )
    world["denominator"] = {"version": 1, "capability_cells": 3, "goals": 1}
    write_json(run.world_model, world)
    expected = minimal_expected(
        discriminating_fact=minimal_scenarios()["scenarios"][0]["discriminating_fact"],
        trajectory={
            "match": "subset",
            "operations": [{"capability_id": "cap-get-log", "args": {"job_id": 90420}}],
        },
    )
    write_json(run.expected("scn-001"), expected)
    findings = check_instances(run)
    assert [f.pointer for f in findings] == ["/trajectory/operations/0/capability_id"]
    assert "the scenario does not claim" in findings[0].message


def test_a_tool_called_assertion_outside_the_capability_refs_is_reported(tmp_path):
    run = _instantiated_run(tmp_path)
    expected = minimal_expected(
        discriminating_fact=minimal_scenarios()["scenarios"][0]["discriminating_fact"]
    )
    expected["assertions"][1]["capability_id"] = "cap-nowhere"
    write_json(run.expected("scn-001"), expected)
    messages = " || ".join(f.message for f in check_instances(run))
    assert "no such capability: cap-nowhere" in messages


def test_a_tool_not_called_assertion_may_name_a_capability_outside_the_refs(tmp_path):
    """A forbidden-call check about an unclaimed capability is the point of the kind."""
    run = _instantiated_run(tmp_path)
    world = minimal_world_model()
    world["capabilities"].append(
        {
            "id": "cap-delete-job",
            "operation": "query_aap2.delete_job",
            "params": [{"name": "job_id", "type": "integer", "required": True}],
            "outcome_classes": [
                {"id": "oc-success", "kind": "success", "description": "deleted"}
            ],
            "claims": ["clm-001"],
            "confidence": "high",
        }
    )
    world["denominator"] = {"version": 1, "capability_cells": 3, "goals": 1}
    write_json(run.world_model, world)
    expected = minimal_expected(
        discriminating_fact=minimal_scenarios()["scenarios"][0]["discriminating_fact"]
    )
    expected["assertions"].append(
        {
            "kind": "tool_not_called",
            "target": "query_aap2.delete_job",
            "value": "never",
            "rationale": "a read-only triage task must not mutate state",
            "capability_id": "cap-delete-job",
        }
    )
    write_json(run.expected("scn-001"), expected)
    assert check_instances(run) == []
```

If `tests/unit/test_refs_instance.py` has no `_instantiated_run` helper, add one that writes `minimal_world_model`, `minimal_scenarios`, `minimal_seed`, and `minimal_expected` into a `RunPaths(tmp_path)` for scenario `scn-001`. **`minimal_expected`'s `discriminating_fact` currently differs from `minimal_scenarios`'s** — that is why several tests above pass it explicitly. Task 4 aligns the builders; until then, do not "fix" it here.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_refs_instance.py -q`
Expected: FAIL — the new tests find no `discriminating_fact` finding and no scope finding.

- [ ] **Step 3: Give `_check_reachability` the scenario's capability set**

In `src/testgen/refs.py`, change the signature and the two capability branches:

```python
def _check_reachability(report, world: dict, seed: dict, expected: dict, scenario_caps: set) -> None:
    """Every assertion is grounded in this scenario's own seed.

    Resolution happens against `seed` and nothing else, so an assertion can
    never reach another scenario's world.

    `scenario_caps` is the scenario's own declared capability_refs. A positive
    trajectory claim must stay inside it: coverage credits the scenario for the
    cells it declared, so an instance exercising a capability the scenario never
    claimed makes coverage confidently wrong. tool_not_called is exempt --
    forbidding a call to an unclaimed capability is exactly what the kind is for.
    """
    capability_ids = {cap["id"] for cap in world.get("capabilities", [])}
    for i, assertion in enumerate(expected.get("assertions", [])):
        kind = assertion["kind"]
        pointer = f"/assertions/{i}"
        if kind in _TRAJECTORY_KINDS:
            capability_id = assertion.get("capability_id")
            if capability_id not in capability_ids:
                report(f"{pointer}/capability_id", f"no such capability: {capability_id}")
            elif kind == "tool_called" and capability_id not in scenario_caps:
                report(
                    f"{pointer}/capability_id",
                    f"asserts a call to {capability_id}, which the scenario does not claim in "
                    "capability_refs; coverage would credit cells this test does not exercise",
                )
            continue
```

Leave the rest of the assertion loop unchanged, and change the trajectory loop at the end of the function to:

```python
    for i, operation in enumerate(expected.get("trajectory", {}).get("operations", [])):
        capability_id = operation["capability_id"]
        if capability_id not in capability_ids:
            report(
                f"/trajectory/operations/{i}/capability_id",
                f"no such capability: {capability_id}",
            )
        elif capability_id not in scenario_caps:
            report(
                f"/trajectory/operations/{i}/capability_id",
                f"the trajectory uses {capability_id}, which the scenario does not claim in "
                "capability_refs; coverage would credit cells this test does not exercise",
            )
```

- [ ] **Step 4: Compare the discriminating fact and pass the set through**

In `check_instances`, replace the `_check_reachability(out_exp, world, seed, expected)` call and the block above it with:

```python
        _check_seed_conformance(out_seed, world, seed)
        _check_invariants(out_inv, world, seed)
        if expected.get("scenario_id") != sid:
            out_exp(
                "/scenario_id",
                f"expected.json names scenario {expected.get('scenario_id')} but lives in the "
                f"instance directory for {sid}",
            )
        scenario_fact = scenario.get("discriminating_fact")
        if expected.get("discriminating_fact") != scenario_fact:
            out_exp(
                "/discriminating_fact",
                f"the oracle's discriminating_fact is {expected.get('discriminating_fact')!r} but "
                f"the scenario declared {scenario_fact!r}; copy the scenario's verbatim -- a "
                "paraphrase is indistinguishable from substituting an easier fact",
            )
        scenario_caps = {ref["capability_id"] for ref in scenario.get("capability_refs", [])}
        _check_reachability(out_exp, world, seed, expected, scenario_caps)
```

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -q`
Expected: FAIL in `tests/unit/test_refs_states.py` and possibly other files, because `minimal_expected`'s `discriminating_fact` does not match `minimal_scenarios`'s. That is a real inconsistency in the builders that the new check just exposed. Fix it now: in `tests/builders.py`, change `minimal_expected`'s `discriminating_fact` to exactly `"exactly one prod0 job failed inside the window"`, matching `minimal_scenarios`.

- [ ] **Step 6: Re-run the whole suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 7: Lint and commit**

```bash
make check
git add src/testgen/refs.py tests/unit/test_refs_instance.py tests/builders.py
git commit -S -s -m "feat: Scope the oracle to the fact and capabilities its scenario claimed

Two decorative fields made real. Nothing compared discriminating_fact
between scenario and oracle, so the mechanism that stops instantiate
inventing an easier world than the one proposed did nothing. And
trajectory operations were checked against the world model but not
against the scenario's own capability_refs, so an instance could
exercise capabilities the scenario never declared while coverage
credited it -- confidently wrong, with no finding.

tool_not_called stays exempt: forbidding a call to an unclaimed
capability is what the kind exists for.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 4: Relate holes to the matrices, and bring the goal matrix up to the capability matrix's rigour

Two coverage gaps, one function, so one task. Hole refs are checked for existence but never related to the matrices, so a coverage report can declare zero holes while cells are `covered: false` — the "every uncovered cell is justified" discipline that makes the hole vocabulary worth having is unenforced. And the goal matrix is checked far more loosely than the capability matrix: `hop_depths_expected` is never compared to the world model's `goals[].expected_hop_depths`, `hop_depths_present` is never derived from the scenarios it lists, and there is no goal-row counterpart to the covered-with-no-scenarios check.

**Files:**
- Modify: `src/testgen/refs.py` (`check_coverage`)
- Modify: `tests/builders.py` (`minimal_coverage` gains the goal hole the new check requires)
- Test: `tests/unit/test_refs_planning.py` (extend)

**Interfaces:**
- Consumes: `refs.cell_ref`, `refs.goal_ref`, `refs.parse_hole_ref`, `refs._load`.
- Produces: no new public name; `check_coverage` returns more findings.

**The definition of a covered goal row, now enforced:** a row is covered iff it lists at least one scenario **and** `hop_depths_present` covers every depth in `hop_depths_expected`. A goal exercised only at one hop depth when the world model expects two is not covered, and the existing builder payload already encodes exactly that case.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_refs_planning.py`. Reuse its existing helper for writing a world model plus scenarios plus coverage; the tests below assume one named `_scored_run(tmp_path, coverage=...)` that writes `minimal_world_model`, `minimal_scenarios`, and the given coverage. Add it if absent.

```python
def test_an_uncovered_cell_with_no_hole_is_reported(tmp_path):
    """Without this, a report can claim zero holes while cells sit uncovered."""
    coverage = minimal_coverage(holes=[])
    run = _scored_run(tmp_path, coverage=coverage)
    messages = " || ".join(f.message for f in check_coverage(run))
    assert "cell:cap-find-jobs/oc-empty is uncovered but no hole justifies it" in messages
    assert "goal:goal-triage is uncovered but no hole justifies it" in messages


def test_a_hole_naming_a_covered_row_is_reported(tmp_path):
    coverage = minimal_coverage()
    coverage["holes"].append(
        {
            "ref": "cell:cap-find-jobs/oc-success",
            "reason": "not_yet_attempted",
            "justification": "claims a hole in a cell the same report marks covered",
        }
    )
    run = _scored_run(tmp_path, coverage=coverage)
    messages = " || ".join(f.message for f in check_coverage(run))
    assert "cell:cap-find-jobs/oc-success" in messages
    assert "the matrix marks covered" in messages


def test_hop_depths_expected_must_match_the_world_model(tmp_path):
    coverage = minimal_coverage()
    coverage["goal_matrix"]["rows"][0]["hop_depths_expected"] = [1]
    run = _scored_run(tmp_path, coverage=coverage)
    findings = [f for f in check_coverage(run) if "hop_depths_expected" in f.pointer]
    assert len(findings) == 1
    assert "[1, 2]" in findings[0].message


def test_hop_depths_present_must_be_derived_from_the_listed_scenarios(tmp_path):
    coverage = minimal_coverage()
    coverage["goal_matrix"]["rows"][0]["hop_depths_present"] = [1, 2]
    run = _scored_run(tmp_path, coverage=coverage)
    findings = [f for f in check_coverage(run) if "hop_depths_present" in f.pointer]
    assert len(findings) == 1
    assert "scn-001" in findings[0].message or "[2]" in findings[0].message


def test_a_goal_row_marked_covered_without_scenarios_is_reported(tmp_path):
    coverage = minimal_coverage()
    row = coverage["goal_matrix"]["rows"][0]
    row["scenario_ids"] = []
    row["hop_depths_present"] = []
    row["covered"] = True
    coverage["goal_matrix"]["covered"] = 1
    coverage["goal_matrix"]["pct"] = 1.0
    run = _scored_run(tmp_path, coverage=coverage)
    findings = [f for f in check_coverage(run) if f.pointer.endswith("/covered")]
    assert len(findings) == 1
    assert "lists no scenarios" in findings[0].message


def test_a_goal_row_covered_at_only_some_expected_hop_depths_is_not_covered(tmp_path):
    """The builder payload is exactly this case: expected [1, 2], present [2]."""
    coverage = minimal_coverage()
    row = coverage["goal_matrix"]["rows"][0]
    row["covered"] = True
    coverage["goal_matrix"]["covered"] = 1
    coverage["goal_matrix"]["pct"] = 1.0
    run = _scored_run(tmp_path, coverage=coverage)
    messages = " || ".join(f.message for f in check_coverage(run))
    assert "hop depth" in messages


def test_the_builder_coverage_payload_is_clean(tmp_path):
    """Guards the builders: every later state test depends on this staying true."""
    run = _scored_run(tmp_path, coverage=minimal_coverage())
    assert check_coverage(run) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_refs_planning.py -q`
Expected: FAIL. `test_the_builder_coverage_payload_is_clean` fails too, because `minimal_coverage` has an uncovered goal row and no hole for it — Step 4 fixes the builder.

- [ ] **Step 3: Relate holes to the matrices and tighten the goal rows**

In `src/testgen/refs.py`, replace the goal-matrix block and the holes loop at the end of `check_coverage`. The capability-matrix block above them is unchanged. Insert this in place of everything from `goal_matrix = coverage.get("goal_matrix", {})` to the end of the function:

```python
    goal_matrix = coverage.get("goal_matrix", {})
    rows = goal_matrix.get("rows", [])
    seen_goals = {r["goal_id"] for r in rows}
    for missing_goal in sorted(goal_ids - seen_goals):
        report("/goal_matrix/rows", f"matrix omits goal {missing_goal}")
    for invented_goal in sorted(seen_goals - goal_ids):
        report("/goal_matrix/rows", f"matrix invents goal {invented_goal}")

    goals_by_id = {g["id"]: g for g in world.get("goals", [])}
    hop_by_scenario = {
        s["id"]: s.get("hop_depth") for s in scenarios_doc.get("scenarios", [])
    }
    for i, row in enumerate(rows):
        for j, sid in enumerate(row.get("scenario_ids", [])):
            if sid not in scenario_ids:
                report(f"/goal_matrix/rows/{i}/scenario_ids/{j}", f"no such scenario: {sid}")
        goal = goals_by_id.get(row["goal_id"])
        expected_depths: set[int] = set()
        if goal is not None:
            expected_depths = set(goal.get("expected_hop_depths", []))
            if set(row.get("hop_depths_expected", [])) != expected_depths:
                report(
                    f"/goal_matrix/rows/{i}/hop_depths_expected",
                    f"row expects hop depths {sorted(row.get('hop_depths_expected', []))} but the "
                    f"world model declares {sorted(expected_depths)} for {row['goal_id']}",
                )
        present = {
            hop_by_scenario[sid]
            for sid in row.get("scenario_ids", [])
            if isinstance(hop_by_scenario.get(sid), int)
        }
        if set(row.get("hop_depths_present", [])) != present:
            report(
                f"/goal_matrix/rows/{i}/hop_depths_present",
                f"row reports hop depths {sorted(row.get('hop_depths_present', []))} but its "
                f"scenarios have {sorted(present)}",
            )
        # A goal row is covered iff it has a scenario and every expected hop
        # depth is present. A goal exercised at one depth when two are expected
        # is a partial row, and calling it covered is how a goal denominator
        # reaches 100% without testing the hard half of the goal.
        if not row.get("scenario_ids"):
            if row.get("covered"):
                report(
                    f"/goal_matrix/rows/{i}/covered",
                    f"goal {row['goal_id']} is marked covered but lists no scenarios",
                )
        elif bool(row.get("covered")) != (expected_depths <= present):
            report(
                f"/goal_matrix/rows/{i}/covered",
                f"goal {row['goal_id']} is marked covered={row.get('covered')} but its scenarios "
                f"reach hop depths {sorted(present)} against an expected {sorted(expected_depths)}",
            )
    _check_matrix_arithmetic(
        report, "/goal_matrix", [bool(r.get("covered")) for r in rows], goal_matrix
    )

    hole_refs: set[str] = set()
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
        hole_refs.add(hole["ref"])
        gap_id = hole.get("gap_id")
        if gap_id is not None and gap_id not in gap_ids:
            report(f"/holes/{i}/gap_id", f"no such gap: {gap_id}")

    # Every uncovered row must be justified, and no justified row may be
    # covered. Without both directions the hole vocabulary is decorative: a
    # report could show 60% and explain none of the missing 40%.
    uncovered = {
        cell_ref(c["capability_id"], c["outcome_class_id"])
        for c in matrix_cells
        if not c.get("covered")
    } | {goal_ref(r["goal_id"]) for r in rows if not r.get("covered")}
    covered = {
        cell_ref(c["capability_id"], c["outcome_class_id"])
        for c in matrix_cells
        if c.get("covered")
    } | {goal_ref(r["goal_id"]) for r in rows if r.get("covered")}
    for ref in sorted(uncovered - hole_refs):
        report("/holes", f"{ref} is uncovered but no hole justifies it")
    for ref in sorted(hole_refs & covered):
        report("/holes", f"hole {ref} names a row the matrix marks covered")
    return out
```

- [ ] **Step 4: Give the builder payload its goal hole**

In `tests/builders.py`, `minimal_coverage`'s goal row is uncovered — expected depths `[1, 2]`, present `[2]` — so it now needs a hole. Replace the `"holes"` value with:

```python
        "holes": [
            {
                "ref": "cell:cap-find-jobs/oc-empty",
                "reason": "not_yet_attempted",
                "justification": "no scenario has exercised the empty-result path yet",
            },
            {
                "ref": "goal:goal-triage",
                "reason": "not_yet_attempted",
                "justification": "only the 2-hop path is covered; hop depth 1 has no scenario",
            },
        ],
```

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS. If `tests/unit/test_schemas_planning.py` asserts a hole count, update it — a second hole is now the consistent payload.

- [ ] **Step 6: Lint and commit**

```bash
make check
git add src/testgen/refs.py tests/builders.py tests/unit/test_refs_planning.py
git commit -S -s -m "feat: Tie coverage holes to the matrices and tighten the goal rows

A coverage report could declare zero holes while cells sat uncovered,
so the every-uncovered-cell-is-justified discipline that makes the hole
vocabulary worth having was unenforced in both directions.

The goal matrix now matches the capability matrix's rigour:
hop_depths_expected is compared to the world model, hop_depths_present
is derived from the scenarios the row lists, and a row is covered only
when it has a scenario and reaches every expected hop depth -- otherwise
a goal denominator reaches 100% without testing the hard half.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 5: Anchor the schema id patterns and constrain `created_utc`

Python's `re` lets `$` match immediately before a trailing newline, so `"scn-001\n"` satisfies every `^…$` id pattern in the schemas while `paths.safe_segment` — which uses `\Z` — refuses it. Today that is unreachable. It goes live in Task 10, when `emit` calls `run.task_dir(sid)` with an id read from `02-scenarios.json`: the id would clear layer 1 and then raise `UnsafeSegment`, which `cli.py` maps to exit 2, telling the orchestrator the harness is misconfigured when the truth is a repairable stage defect.

`created_utc` is the same class of problem stated differently: the schema declares `"format": "date-time"` and the validator is built with no `format_checker`, so `"not-a-timestamp"` validates clean. Adding a checker would not help — `date-time` is not among `Draft202012Validator.FORMAT_CHECKER.checkers` unless `rfc3339-validator` is installed, and this plan adds no dependency. A `pattern` enforces the shape with the stdlib and is *stricter* than RFC 3339: it rejects `2026-08-06T12:00:00+05:30`, and a non-UTC stamp would make two runs' timestamps incomparable and the derived run id wrong.

**Files:**
- Modify: all eight of `src/testgen/schema/*.json`
- Modify: `src/testgen/validate.py` (docstring note on the deviation)
- Test: `tests/unit/test_schemas_planning.py` or `tests/unit/test_schemas_instance.py` (extend, one test per schema group)

**Interfaces:**
- Consumes: nothing new.
- Produces: no new name. Every `pattern` in the schema directory is anchored `\A…\Z`; `manifest.created_utc` gains a pattern.

**The twelve pattern sites**, all found with `grep -n 'pattern' src/testgen/schema/*.json`:

| File | Pattern to change |
|---|---|
| `claims-0.1.json` | `$defs.id` |
| `world-model-0.1.json` | `$defs.id` |
| `scenarios-0.1.json` | `$defs.id`, `$defs.hole_ref` |
| `coverage-0.1.json` | `$defs.id`, `$defs.hole_ref` |
| `seed-0.1.json` | `collections.propertyNames.pattern` |
| `expected-0.1.json` | `$defs.id`, `grounded_in.seed_pointer` (`^/` → `\A/`) |
| `verdict-0.1.json` | `$defs.id` |
| `manifest-0.1.json` | `$defs.id`, `$defs.sha256`, plus the new `created_utc` |

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_schemas_instance.py`:

```python
import pytest

from testgen.validate import ARTIFACT_SCHEMAS, validate_artifact
from testgen.artifacts import write_json


@pytest.mark.parametrize("kind", sorted(ARTIFACT_SCHEMAS))
def test_no_schema_pattern_uses_a_caret_dollar_anchor(kind, tmp_path):
    """Python's re lets $ match before a trailing newline; \\Z does not.

    paths.safe_segment uses \\Z, so an id ending in a newline clears layer 1
    and then raises UnsafeSegment, which the CLI maps to exit 2 -- a repairable
    stage defect misreported as a broken harness.
    """
    import json

    from testgen.validate import schema_dir

    text = (schema_dir() / ARTIFACT_SCHEMAS[kind]).read_text(encoding="utf-8")
    schema = json.loads(text)

    def patterns(node):
        """Every string value of a "pattern" key, at any depth."""
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "pattern" and isinstance(value, str):
                    yield value
                else:
                    yield from patterns(value)
        elif isinstance(node, list):
            for item in node:
                yield from patterns(item)

    found = list(patterns(schema))
    assert found, f"{kind} declares no patterns; the table in the plan says it should"
    for pattern in found:
        assert not pattern.startswith("^"), f"{kind}: {pattern!r} still uses ^"
        assert not pattern.endswith("$"), f"{kind}: {pattern!r} still uses $"
        assert pattern.startswith("\\A"), f"{kind}: {pattern!r} is not anchored with \\A"


def test_a_scenario_id_ending_in_a_newline_is_rejected(tmp_path):
    from tests.builders import minimal_scenarios

    payload = minimal_scenarios()
    payload["scenarios"][0]["id"] = "scn-001\n"
    path = tmp_path / "02-scenarios.json"
    write_json(path, payload)
    assert validate_artifact(path, "scenarios") != []


def test_a_seed_pointer_not_starting_with_a_slash_is_rejected(tmp_path):
    from tests.builders import minimal_expected

    payload = minimal_expected()
    payload["assertions"][0]["grounded_in"]["seed_pointer"] = "collections/jobs/0"
    path = tmp_path / "expected.json"
    write_json(path, payload)
    assert validate_artifact(path, "expected") != []


@pytest.mark.parametrize(
    "created_utc",
    ["not-a-timestamp", "2026-08-06T12:00:00+05:30", "2026-08-06 12:00:00Z", "2026-08-06T12:00:00Z\n"],
)
def test_a_created_utc_that_is_not_a_utc_stamp_is_rejected(tmp_path, created_utc):
    from tests.builders import minimal_manifest

    path = tmp_path / "manifest.json"
    write_json(path, minimal_manifest(created_utc=created_utc))
    assert validate_artifact(path, "manifest") != []


def test_the_canonical_created_utc_is_accepted(tmp_path):
    from tests.builders import minimal_manifest

    path = tmp_path / "manifest.json"
    write_json(path, minimal_manifest(created_utc="2026-08-06T12:00:00Z"))
    assert validate_artifact(path, "manifest") == []
```

The three assertions per pattern are deliberately redundant: `startswith("\\A")` is the requirement, and the two negative checks name the specific defect so a failure message says which anchor came back rather than only that something is off. `seed_pointer`'s `\A/` has no trailing anchor and passes — a pointer's tail is unconstrained.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_schemas_instance.py -q`
Expected: FAIL — every schema still uses `^…$`, and every `created_utc` value validates.

- [ ] **Step 3: Re-anchor every pattern**

In each of the eight schema files, rewrite each `pattern` value: replace a leading `^` with `\\A` and a trailing `$` with `\\Z` (in JSON source that is the two characters `\A`, written `"\\A"` inside the JSON string — i.e. the file contains `"\\A[A-Za-z0-9]..."`). The id def becomes:

```json
    "id": {
      "type": "string",
      "pattern": "\\A[A-Za-z0-9][A-Za-z0-9._-]*\\Z",
      "maxLength": 128
    }
```

The hole ref def in both `scenarios-0.1.json` and `coverage-0.1.json` becomes:

```json
    "hole_ref": {
      "type": "string",
      "pattern": "\\A(cell:[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*|goal:[A-Za-z0-9][A-Za-z0-9._-]*)\\Z"
    }
```

In `seed-0.1.json`: `"propertyNames": { "pattern": "\\A[A-Za-z0-9][A-Za-z0-9._-]*\\Z" }`.
In `expected-0.1.json`: `"seed_pointer": { "type": "string", "pattern": "\\A/" }` — no trailing anchor, since a pointer's tail is unconstrained.
In `manifest-0.1.json`: `"sha256": { "type": "string", "pattern": "\\A[0-9a-f]{64}\\Z" }`.

Verify with `grep -c '\^' src/testgen/schema/*.json` — every count must be 0.

- [ ] **Step 4: Constrain `created_utc`**

In `src/testgen/schema/manifest-0.1.json`, replace the `created_utc` property with:

```json
    "created_utc": {
      "type": "string",
      "format": "date-time",
      "pattern": "\\A\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z\\Z"
    },
```

`format` stays as documentation of intent; `pattern` is what actually holds. The pattern is deliberately narrower than RFC 3339 — it admits only the `Z` form `intake` writes, because a stamp carrying an offset would make two runs' timestamps incomparable and the run id derived from it wrong.

- [ ] **Step 5: Record the deviation**

Append to the module docstring of `src/testgen/validate.py`:

```
**The schemas anchor patterns with `\A` and `\Z`, not `^` and `$`.** JSON
Schema specifies ECMA-262 regexes, where those escapes are not defined, so
these schemas are portable only to a Python validator. That is a deliberate
trade: Python's `re` lets `$` match immediately before a trailing newline, so
`"scn-001\n"` would satisfy every id pattern and then raise UnsafeSegment when
joined into a path -- surfacing a repairable stage defect as exit 2, a
misconfigured harness. Nothing outside this package validates these artifacts.
```

- [ ] **Step 6: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 7: Lint and commit**

```bash
make check
git add src/testgen/schema src/testgen/validate.py tests/unit/test_schemas_instance.py
git commit -S -s -m "fix: Anchor schema patterns with \\A..\\Z and constrain created_utc

Python's re lets \$ match before a trailing newline, so \"scn-001\\n\"
cleared every id pattern and then raised UnsafeSegment when joined into
a path -- exit 2, telling the orchestrator the harness was broken when
the truth was a repairable stage defect. Unreachable until emit joins an
id read from 02-scenarios.json, which is two tasks away.

created_utc declared format: date-time and had no constraint at all:
date-time is not a registered checker without rfc3339-validator. A
pattern enforces it with the stdlib and is stricter, admitting only the
UTC Z form intake writes.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 6: Give capabilities a tool binding

`emit` must turn a `capability_id` into a concrete tool call — Harbor scores `{"name": "query_aap2", "args": {"action": "get_job_log", "job_id": 91010}}`. The world model's `operation` is a free string like `"query_aap2.find_jobs"`, and splitting it on a dot to recover the tool name plus an `action` argument would bake one target's MCP calling convention into the emitter. `emit` must be Harbor-aware, not target-aware.

So the binding becomes a declared, evidence-backed part of the world model rather than a guess in the emitter. A capability with no binding cannot be emitted, and `emit` says so as a finding.

**Files:**
- Modify: `src/testgen/schema/world-model-0.1.json` (optional `binding` on a capability)
- Modify: `tests/builders.py` (`minimal_world_model` declares one)
- Test: `tests/unit/test_schemas_planning.py` (extend)

**Interfaces:**
- Consumes: nothing new.
- Produces: the world-model capability shape gains an **optional** `binding: {tool: str, fixed_args: object}`. Optional, so every artifact that validated before still validates — no schema version bump. Tasks 9 and 10 read it as `capability.get("binding")`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_schemas_planning.py`:

```python
def test_a_capability_may_declare_a_tool_binding(tmp_path):
    from testgen.artifacts import write_json
    from testgen.validate import validate_artifact
    from tests.builders import minimal_world_model

    path = tmp_path / "01-world-model.json"
    write_json(path, minimal_world_model())
    assert validate_artifact(path, "world-model") == []
    assert minimal_world_model()["capabilities"][0]["binding"] == {
        "tool": "query_aap2",
        "fixed_args": {"action": "find_jobs"},
    }


def test_a_capability_without_a_binding_still_validates(tmp_path):
    """Optional, so no artifact that validated before this change stops validating."""
    from testgen.artifacts import write_json
    from testgen.validate import validate_artifact
    from tests.builders import minimal_world_model

    world = minimal_world_model()
    del world["capabilities"][0]["binding"]
    path = tmp_path / "01-world-model.json"
    write_json(path, world)
    assert validate_artifact(path, "world-model") == []


def test_a_binding_missing_its_tool_is_rejected(tmp_path):
    from testgen.artifacts import write_json
    from testgen.validate import validate_artifact
    from tests.builders import minimal_world_model

    world = minimal_world_model()
    world["capabilities"][0]["binding"] = {"fixed_args": {}}
    path = tmp_path / "01-world-model.json"
    write_json(path, world)
    assert validate_artifact(path, "world-model") != []


def test_a_binding_with_an_unknown_key_is_rejected(tmp_path):
    from testgen.artifacts import write_json
    from testgen.validate import validate_artifact
    from tests.builders import minimal_world_model

    world = minimal_world_model()
    world["capabilities"][0]["binding"] = {
        "tool": "query_aap2",
        "fixed_args": {},
        "endpoint": "https://example.invalid",
    }
    path = tmp_path / "01-world-model.json"
    write_json(path, world)
    assert validate_artifact(path, "world-model") != []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_schemas_planning.py -q`
Expected: FAIL — `minimal_world_model` has no `binding`, and the schema's `additionalProperties: false` on a capability rejects one.

- [ ] **Step 3: Add `binding` to the capability schema**

In `src/testgen/schema/world-model-0.1.json`, inside `$defs.capability.properties` (leaving `required` untouched), add:

```json
        "binding": {
          "type": "object",
          "description": "How this capability is invoked on the target: the tool name a transcript will show, plus the arguments that identify this capability rather than a sibling sharing the tool. Optional in the schema and required by emit, which reports a finding for an accepted scenario whose capability has none.",
          "required": ["tool", "fixed_args"],
          "additionalProperties": false,
          "properties": {
            "tool": { "type": "string", "minLength": 1 },
            "fixed_args": { "type": "object" }
          }
        },
```

- [ ] **Step 4: Declare one in the builder**

In `tests/builders.py`, add to `minimal_world_model`'s single capability, after `"operation"`:

```python
                "binding": {"tool": "query_aap2", "fixed_args": {"action": "find_jobs"}},
```

- [ ] **Step 5: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Lint and commit**

```bash
make check
git add src/testgen/schema/world-model-0.1.json tests/builders.py tests/unit/test_schemas_planning.py
git commit -S -s -m "feat: Let a capability declare how it is invoked

emit must turn a capability_id into a concrete tool call, and the only
information available was a free-form operation string. Splitting it on
a dot to recover a tool name plus an action argument would bake one
target's MCP calling convention into the emitter, which must be
Harbor-aware but not target-aware.

Optional in the schema, so nothing that validated before stops
validating; required by emit, which reports a finding instead.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 7: The generic verifier — transcript parsing and assertion scoring

`verify.py` is the one place a bug silently inflates every score, so it is hand-written once and copied verbatim into every package rather than generated per task. That is what forces the assertion vocabulary closed: a skill cannot invent a kind, because adding one is a human edit to this file.

The tracked original lives inside the package and is what the tests exercise, so the tested file and the executed file cannot differ.

**Files:**
- Create: `src/testgen/suite/__init__.py`
- Create: `src/testgen/suite/verify.py` (partial — assertion half; Task 8 finishes it)
- Modify: `pyproject.toml` (ship the templates as package data)
- Test: `tests/unit/test_verify_assertions.py` (create)

**Interfaces:**
- Consumes: the stdlib only. **`verify.py` must not import `testgen`** — it executes inside a bare ubi9 container where the package is absent.
- Produces:
  - `CONTRACT = "testgen/v1"`, `DEFAULT_WEIGHTS = {"assertions": 0.8, "trajectory": 0.2}`
  - `parse_transcript(text: str) -> tuple[list[tuple[str, dict]], str, bool]` → `(calls, answer, ok)`
  - `values_equal(want, got) -> bool`
  - `call_matches(spec: dict, call: tuple[str, dict]) -> bool` — spec is `{"tool": str, "args": dict}`
  - `score_assertions(answer: str, calls: list, assertions: list[dict]) -> tuple[float, dict]`

**The five kinds and exactly what each means.** This table is the contract; the docstrings must say the same thing.

| kind | satisfied when | notes |
|---|---|---|
| `answer_contains` | `value` occurs in the answer, case-insensitively | |
| `answer_excludes` | `value` does **not** occur, case-insensitively | satisfied by absence, scored as a point |
| `value_equals` | `value` occurs delimited — not flanked by an alphanumeric | so `"3"` is not satisfied by `"13"` |
| `tool_called` | some actual call matches `{tool, args}` | args match on subset |
| `tool_not_called` | no actual call matches | satisfied by absence, scored as a point |

Absence is scored as a point, not a penalty. That makes a fabrication trap a positively-scored item and lets a pure-absence scenario — "which job caused the outage?" when none did — consist entirely of exclusions and still score coherently. This decision, and the numeric-string equality below, are carried over from a sibling project's verifier that earned them on live runs.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_verify_assertions.py`:

```python
"""The generic verifier's transcript parsing and assertion scoring.

Imports the tracked original that emit copies verbatim, so the tested file and
the executed file cannot differ.
"""

from __future__ import annotations

import json

import pytest

from testgen.suite.verify import (
    call_matches,
    parse_transcript,
    score_assertions,
    values_equal,
)


def _transcript(*events) -> str:
    return "\n".join(json.dumps(e) for e in events)


def _tool_use(name, args):
    return {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": name, "input": args}]},
    }


def _result(text, *, subtype="success", is_error=False):
    return {"type": "result", "subtype": subtype, "is_error": is_error, "result": text}


# -- parse_transcript --------------------------------------------------------


def test_a_transcript_yields_its_calls_answer_and_success_flag():
    text = _transcript(
        _tool_use("query_aap2", {"action": "find_jobs", "controller": "prod0"}),
        _result("Job 90420 failed."),
    )
    calls, answer, ok = parse_transcript(text)
    assert calls == [("query_aap2", {"action": "find_jobs", "controller": "prod0"})]
    assert answer == "Job 90420 failed."
    assert ok is True


def test_a_malformed_line_is_skipped_rather_than_fatal():
    """A truncated transcript must still score; crashing would report a broken agent."""
    text = "not json\n{\n" + _transcript(_result("done"))
    calls, answer, ok = parse_transcript(text)
    assert calls == []
    assert answer == "done"


def test_an_error_result_is_not_ok():
    _, _, ok = parse_transcript(_transcript(_result("boom", subtype="error", is_error=True)))
    assert ok is False


def test_the_last_result_event_wins():
    text = _transcript(_result("first"), _result("second"))
    _, answer, _ = parse_transcript(text)
    assert answer == "second"


def test_a_tool_use_with_no_input_yields_empty_args():
    text = _transcript({
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": "query_aap2"}]},
    })
    calls, _, _ = parse_transcript(text)
    assert calls == [("query_aap2", {})]


def test_an_empty_transcript_yields_no_answer_and_not_ok():
    calls, answer, ok = parse_transcript("")
    assert (calls, answer, ok) == ([], "", False)


# -- values_equal and call_matches ------------------------------------------


@pytest.mark.parametrize(
    ("want", "got", "expected"),
    [
        (90420, 90420, True),
        (90420, "90420", True),
        ("90420", 90420, True),
        (90420.0, 90420, True),
        (True, 1, False),
        (1, True, False),
        (True, True, True),
        ("prod0", "prod0", True),
        ("prod0", "prod1", False),
    ],
)
def test_values_equal_compares_numbers_numerically_and_bools_strictly(want, got, expected):
    """An agent serialising job_id as a string still chose the right job; but
    failed_only=true and failed_only=1 are different intents."""
    assert values_equal(want, got) is expected


def test_a_call_matches_on_an_argument_subset():
    call = ("query_aap2", {"action": "find_jobs", "controller": "prod0", "max_results": 50})
    assert call_matches({"tool": "query_aap2", "args": {"action": "find_jobs"}}, call)


def test_a_call_with_a_missing_required_argument_does_not_match():
    call = ("query_aap2", {"action": "find_jobs"})
    assert not call_matches({"tool": "query_aap2", "args": {"controller": "prod0"}}, call)


def test_a_call_with_the_wrong_tool_name_does_not_match():
    assert not call_matches({"tool": "other", "args": {}}, ("query_aap2", {}))


def test_a_spec_with_no_args_matches_any_call_to_that_tool():
    assert call_matches({"tool": "query_aap2"}, ("query_aap2", {"action": "anything"}))


# -- score_assertions -------------------------------------------------------


def _assertion(kind, **over):
    base = {"id": "a0", "kind": kind, "value": "90420", "rationale": "because"}
    base.update(over)
    return base


def test_every_assertion_satisfied_scores_one():
    calls = [("query_aap2", {"action": "find_jobs"})]
    assertions = [
        _assertion("answer_contains", value="90420"),
        _assertion("answer_excludes", id="a1", value="DNS"),
        _assertion("value_equals", id="a2", value="90420", target="job_id"),
        _assertion("tool_called", id="a3", tool="query_aap2", args={"action": "find_jobs"}),
        _assertion("tool_not_called", id="a4", tool="query_aap2", args={"action": "delete_job"}),
    ]
    score, detail = score_assertions("Job 90420 failed on prod0.", calls, assertions)
    assert score == 1.0
    assert detail["failed"] == []
    assert detail["total"] == 5


def test_answer_contains_is_case_insensitive():
    score, _ = score_assertions("job 90420 FAILED", [], [_assertion("answer_contains", value="failed")])
    assert score == 1.0


def test_answer_excludes_is_violated_by_a_case_variant():
    """Case-insensitivity makes an exclusion stricter, which is the right direction."""
    score, detail = score_assertions("caused by dns", [], [_assertion("answer_excludes", value="DNS")])
    assert score == 0.0
    assert [f["id"] for f in detail["failed"]] == ["a0"]


def test_value_equals_is_not_satisfied_by_a_longer_number():
    score, _ = score_assertions("job 13 failed", [], [_assertion("value_equals", value="3")])
    assert score == 0.0


def test_value_equals_is_satisfied_at_a_punctuation_boundary():
    score, _ = score_assertions("the count was 3.", [], [_assertion("value_equals", value="3")])
    assert score == 1.0


def test_value_equals_is_satisfied_at_the_end_of_the_answer():
    score, _ = score_assertions("the count was 3", [], [_assertion("value_equals", value="3")])
    assert score == 1.0


def test_tool_not_called_fails_when_the_call_was_made():
    calls = [("query_aap2", {"action": "delete_job", "job_id": 1})]
    assertion = _assertion("tool_not_called", tool="query_aap2", args={"action": "delete_job"})
    score, detail = score_assertions("done", calls, [assertion])
    assert score == 0.0
    assert detail["failed"][0]["kind"] == "tool_not_called"


def test_a_partially_satisfied_set_scores_the_fraction():
    assertions = [
        _assertion("answer_contains", value="90420"),
        _assertion("answer_contains", id="a1", value="never-present"),
    ]
    score, detail = score_assertions("Job 90420.", [], assertions)
    assert score == 0.5
    assert [f["id"] for f in detail["failed"]] == ["a1"]


def test_an_unknown_kind_is_reported_as_failed_rather_than_awarded():
    """The vocabulary is closed. An unknown kind means a bypassed gate, and
    awarding a point for one would hide it."""
    score, detail = score_assertions("anything", [], [_assertion("answer_matches_regex")])
    assert score == 0.0
    assert "unknown assertion kind" in json.dumps(detail)


def test_an_empty_assertion_list_scores_one():
    score, detail = score_assertions("anything", [], [])
    assert score == 1.0
    assert detail["total"] == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_verify_assertions.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'testgen.suite'`

- [ ] **Step 3: Create the package marker**

Create `src/testgen/suite/__init__.py`:

```python
"""Files copied verbatim into every emitted task package.

verify.py and test.sh execute inside the task container -- a bare ubi9 image
with no third-party packages and no network -- so they are stdlib-only and must
never import testgen. They live inside the package so the tests exercise the
same bytes emit copies, which is the only way the tested file and the executed
file cannot drift apart.
"""
```

- [ ] **Step 4: Write the assertion half of `verify.py`**

Create `src/testgen/suite/verify.py`:

```python
#!/usr/bin/env python3
"""Generic verifier for a testgen-emitted task (contract "testgen/v1").

Stdlib-only: this runs inside the task container, a bare ubi9 image with no
third-party packages and no network. It must never import testgen.

This file is the SOLE implementation of testgen's scoring semantics, and it is
hand-written rather than generated per task on purpose. A generated verifier is
untrustworthy code sitting directly in the scoring path -- the one place a bug
silently inflates every score. Keeping it fixed is also what forces the
assertion vocabulary closed: no skill can invent a kind, because adding one is a
human edit to this file.

emit copies this file verbatim into every package. The tracked original at
src/testgen/suite/verify.py is what the tests exercise, so the tested file and
the executed file cannot differ.
"""

import argparse
import json
import sys
from pathlib import Path

CONTRACT = "testgen/v1"

# The answer carries the discriminating fact, so it carries most of the weight.
# A trajectory is largely obvious once the task is understood, and weighting it
# heavily would let a well-shaped-but-wrong run out-score a correct one.
DEFAULT_WEIGHTS = {"assertions": 0.8, "trajectory": 0.2}


def parse_transcript(text):
    """Read a stream-json transcript into (calls, answer, ok).

    Each call is (tool_name, args). Malformed lines are skipped so a truncated
    transcript still scores rather than crashing -- a crash would be reported as
    a broken agent when the truth is a broken log.
    """
    calls, answer, ok = [], "", False
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    args = block.get("input")
                    calls.append(
                        (block.get("name", ""), args if isinstance(args, dict) else {})
                    )
        elif event.get("type") == "result":
            # Last result event wins: exactly one is written per run, but a
            # partial transcript plus a terminal error event can yield two.
            answer = event.get("result", "") or ""
            ok = event.get("subtype") == "success" and not event.get("is_error", False)
    return calls, answer, ok


def _as_number(value):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def values_equal(want, got):
    """Compare two JSON scalars as tool arguments.

    Numbers compare numerically and a numeric string equals a number: an agent
    that serialises job_id as "90420" still chose the right job, so penalising
    it would measure serialisation style rather than tool use. Booleans are
    never equal to numbers, because failed_only=true and failed_only=1 are
    different intents.
    """
    if isinstance(want, bool) or isinstance(got, bool):
        return isinstance(want, bool) and isinstance(got, bool) and want == got
    want_number, got_number = _as_number(want), _as_number(got)
    if want_number is not None and got_number is not None:
        return want_number == got_number
    return want == got


def call_matches(spec, call):
    """Subset match: tool names must be equal and every listed arg must agree.

    Arguments the spec omits are ignored, so an incidental max_results or
    controller does not break an otherwise correct call.
    """
    name, args = call
    if spec.get("tool", "") != name:
        return False
    for key, want in (spec.get("args") or {}).items():
        if key not in args or not values_equal(want, args[key]):
            return False
    return True


def _contains(answer, value):
    return value.lower() in answer.lower()


def _delimited(answer, value):
    """Whether `value` occurs in `answer` not flanked by an alphanumeric.

    This is what separates value_equals from answer_contains: an answer of
    "job 13 failed" must not satisfy an asserted count of "3".
    """
    haystack, needle = answer.lower(), value.lower()
    if not needle:
        return False
    start = 0
    while True:
        index = haystack.find(needle, start)
        if index < 0:
            return False
        before = haystack[index - 1] if index > 0 else ""
        after_index = index + len(needle)
        after = haystack[after_index] if after_index < len(haystack) else ""
        if not before.isalnum() and not after.isalnum():
            return True
        start = index + 1


def _assertion_satisfied(answer, calls, assertion):
    """-> True, False, or None when the kind is not in the closed vocabulary."""
    kind = assertion.get("kind")
    value = assertion.get("value", "")
    if kind == "answer_contains":
        return _contains(answer, value)
    if kind == "answer_excludes":
        return not _contains(answer, value)
    if kind == "value_equals":
        return _delimited(answer, value)
    if kind in ("tool_called", "tool_not_called"):
        hit = any(call_matches(assertion, call) for call in calls)
        return hit if kind == "tool_called" else not hit
    return None


def score_assertions(answer, calls, assertions):
    """-> (score, detail) over one denominator of every assertion.

    An exclusion satisfied by absence scores a point rather than avoiding a
    penalty. That makes a fabrication trap a positively-scored item, and lets a
    pure-absence scenario consist entirely of exclusions and still score.

    An unrecognised kind counts as failed, never as satisfied: the vocabulary is
    closed, so one can only arrive here through a bypassed authoring gate, and
    awarding a point would hide that.
    """
    satisfied_ids, failed, unknown = [], [], []
    for assertion in assertions:
        result = _assertion_satisfied(answer, calls, assertion)
        if result is None:
            entry = dict(assertion)
            entry["error"] = f"unknown assertion kind {assertion.get('kind')!r}"
            unknown.append(entry)
            failed.append(entry)
        elif result:
            satisfied_ids.append(assertion.get("id"))
        else:
            failed.append(dict(assertion))

    total = len(assertions)
    detail = {
        "total": total,
        "satisfied": satisfied_ids,
        "failed": failed,
        "unknown_kinds": unknown,
    }
    if total == 0:
        return 1.0, detail
    return (total - len(failed)) / total, detail
```

`failed` holds full copies of the failing assertions, not just their ids: the whole point of `reward-detail.json` is that a reader can see *which* check failed and why without opening the run directory.

- [ ] **Step 5: Ship the templates as package data**

In `pyproject.toml`, extend the package-data entry:

```toml
[tool.setuptools.package-data]
testgen = ["schema/*.json", "suite/*.py", "suite/*.sh"]
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/unit/test_verify_assertions.py -q`
Expected: PASS.

- [ ] **Step 7: Prove the verifier is importable with no testgen on the path**

The container constraint is real, so check it rather than trusting it:

```bash
uv run python -c "
import ast, pathlib
tree = ast.parse(pathlib.Path('src/testgen/suite/verify.py').read_text())
bad = [
    n for n in ast.walk(tree)
    if (isinstance(n, ast.Import) and any(a.name.startswith('testgen') for a in n.names))
    or (isinstance(n, ast.ImportFrom) and (n.module or '').startswith('testgen'))
]
assert not bad, 'verify.py imports testgen; it runs where testgen does not exist'
print('verify.py is testgen-free')
"
```

Expected: `verify.py is testgen-free`. Task 8 turns this into a permanent test.

- [ ] **Step 8: Lint and commit**

```bash
make check
git add src/testgen/suite pyproject.toml tests/unit/test_verify_assertions.py
git commit -S -s -m "feat: Add the generic verifier's parsing and assertion scoring

Hand-written once and copied verbatim rather than generated per task:
the scoring path is the one place a bug silently inflates every score.
Keeping it fixed is also what forces the assertion vocabulary closed --
no skill can invent a kind, because adding one is a human edit here.

Absence scores a point rather than avoiding a penalty, so a fabrication
trap is a positively-scored item and a pure-absence scenario can consist
entirely of exclusions. An unrecognised kind counts as failed: the
vocabulary is closed, so one can only arrive through a bypassed gate.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 8: The generic verifier — trajectory scoring, reward, and entrypoint

Harbor's universal contract is a bare float in `/logs/verifier/reward.txt` — that is what its adapter validator requires and the only file the platform is guaranteed to read. `reward.json` and `reward-detail.json` are for humans, and the detail file is not optional in practice: a bare 0.625 with no way to see which check failed costs real debugging time.

**Files:**
- Modify: `src/testgen/suite/verify.py` (trajectory scoring, `compute_reward`, `main`)
- Create: `src/testgen/suite/test.sh`
- Test: `tests/unit/test_verify_reward.py` (create)

**Interfaces:**
- Consumes: everything Task 7 produced.
- Produces:
  - `score_trajectory(calls: list, trajectory: dict) -> tuple[float, dict]`
  - `compute_reward(contract: dict, calls: list, answer: str, ok: bool) -> tuple[dict, dict]` → `(reward, detail)` where reward holds `reward`, `completion`, `assertions`, `trajectory`
  - `main(argv=None) -> int` — `0` scored, `2` refused to score

**Three match modes, from `expected.json`'s `trajectory.match`:**

| mode | score |
|---|---|
| `subset` | fraction of expected operations matched; each actual call satisfies at most one expected operation |
| `exact-set` | 1.0 only if every expected operation matched **and** the run made no extra calls |
| `exact-sequence` | 1.0 only if the call list is pairwise equal in order and the same length |

**A contract this verifier cannot read is refused, not scored 0.** Writing a 0 would report a bypassed authoring gate as a bad agent run, inverting the conclusion. So on a contract mismatch it writes `reward-detail.json` with the error, writes **no** `reward.txt`, and exits 2 — Harbor then sees a missing reward rather than a real one.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_verify_reward.py`:

```python
"""Trajectory scoring, the reward computation, and the verifier entrypoint."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from testgen.suite.verify import CONTRACT, compute_reward, main, score_trajectory


def _calls(*pairs):
    return list(pairs)


def _op(tool="query_aap2", **args):
    return {"tool": tool, "args": args}


# -- score_trajectory -------------------------------------------------------


def test_subset_scores_the_matched_fraction():
    calls = _calls(("query_aap2", {"action": "find_jobs"}))
    trajectory = {"match": "subset", "operations": [_op(action="find_jobs"), _op(action="get_job_log")]}
    score, detail = score_trajectory(calls, trajectory)
    assert score == 0.5
    assert detail["unmatched"] == [_op(action="get_job_log")]


def test_subset_ignores_extra_calls():
    calls = _calls(("query_aap2", {"action": "find_jobs"}), ("query_aap2", {"action": "whatever"}))
    score, _ = score_trajectory(calls, {"match": "subset", "operations": [_op(action="find_jobs")]})
    assert score == 1.0


def test_subset_does_not_let_one_call_satisfy_two_operations():
    """Otherwise a single call scores a two-hop trajectory, erasing hop depth."""
    calls = _calls(("query_aap2", {"action": "find_jobs"}))
    trajectory = {"match": "subset", "operations": [_op(action="find_jobs"), _op(action="find_jobs")]}
    score, _ = score_trajectory(calls, trajectory)
    assert score == 0.5


def test_subset_is_order_independent():
    calls = _calls(("query_aap2", {"action": "get_job_log"}), ("query_aap2", {"action": "find_jobs"}))
    trajectory = {"match": "subset", "operations": [_op(action="find_jobs"), _op(action="get_job_log")]}
    score, _ = score_trajectory(calls, trajectory)
    assert score == 1.0


def test_exact_set_rejects_an_extra_call():
    calls = _calls(("query_aap2", {"action": "find_jobs"}), ("query_aap2", {"action": "extra"}))
    score, _ = score_trajectory(calls, {"match": "exact-set", "operations": [_op(action="find_jobs")]})
    assert score == 0.0


def test_exact_set_accepts_the_same_calls_in_any_order():
    calls = _calls(("query_aap2", {"action": "get_job_log"}), ("query_aap2", {"action": "find_jobs"}))
    trajectory = {"match": "exact-set", "operations": [_op(action="find_jobs"), _op(action="get_job_log")]}
    score, _ = score_trajectory(calls, trajectory)
    assert score == 1.0


def test_exact_sequence_rejects_the_wrong_order():
    calls = _calls(("query_aap2", {"action": "get_job_log"}), ("query_aap2", {"action": "find_jobs"}))
    trajectory = {
        "match": "exact-sequence",
        "operations": [_op(action="find_jobs"), _op(action="get_job_log")],
    }
    score, _ = score_trajectory(calls, trajectory)
    assert score == 0.0


def test_exact_sequence_accepts_the_right_order():
    calls = _calls(("query_aap2", {"action": "find_jobs"}), ("query_aap2", {"action": "get_job_log"}))
    trajectory = {
        "match": "exact-sequence",
        "operations": [_op(action="find_jobs"), _op(action="get_job_log")],
    }
    score, _ = score_trajectory(calls, trajectory)
    assert score == 1.0


def test_no_expected_operations_scores_one():
    score, _ = score_trajectory([], {"match": "subset", "operations": []})
    assert score == 1.0


# -- compute_reward ---------------------------------------------------------


def _contract(**over):
    payload = {
        "contract": CONTRACT,
        "scenario_id": "scn-001",
        "completion": {"status": "ok", "nonempty_answer": True},
        "assertions": [
            {"id": "a0", "kind": "answer_contains", "value": "90420", "rationale": "the job id"}
        ],
        "trajectory": {"match": "subset", "operations": [_op(action="find_jobs")]},
        "weights": {"assertions": 0.8, "trajectory": 0.2},
    }
    payload.update(over)
    return payload


def test_a_fully_correct_run_scores_one():
    calls = _calls(("query_aap2", {"action": "find_jobs"}))
    reward, _ = compute_reward(_contract(), calls, "Job 90420 failed.", True)
    assert reward["reward"] == 1.0
    assert reward["completion"] == 1.0


def test_the_weights_are_applied():
    """Answer right, trajectory absent -> the assertions weight alone."""
    reward, _ = compute_reward(_contract(), [], "Job 90420 failed.", True)
    assert reward["reward"] == pytest.approx(0.8)


def test_a_failed_completion_gates_the_reward_to_zero():
    calls = _calls(("query_aap2", {"action": "find_jobs"}))
    reward, detail = compute_reward(_contract(), calls, "Job 90420 failed.", False)
    assert reward["reward"] == 0.0
    assert detail["gate"] == 0.0
    assert reward["assertions"] == 1.0, "the components stay visible under the gate"


def test_an_empty_answer_gates_the_reward_to_zero():
    reward, _ = compute_reward(_contract(), [], "   ", True)
    assert reward["reward"] == 0.0


def test_an_expected_error_completion_is_not_gated_by_a_failed_run():
    contract = _contract(completion={"status": "error", "nonempty_answer": False})
    reward, _ = compute_reward(contract, [], "", False)
    assert reward["completion"] == 1.0


def test_missing_weights_fall_back_to_the_documented_defaults():
    contract = _contract()
    del contract["weights"]
    reward, detail = compute_reward(contract, [], "Job 90420 failed.", True)
    assert detail["weights"] == {"assertions": 0.8, "trajectory": 0.2}
    assert reward["reward"] == pytest.approx(0.8)


# -- main -------------------------------------------------------------------


def _write_run(tmp_path, contract, transcript):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "expected.json").write_text(json.dumps(contract))
    logs = tmp_path / "logs" / "agent"
    logs.mkdir(parents=True)
    (logs / "transcript.jsonl").write_text(transcript)
    return tmp_path / "tests" / "expected.json", logs, tmp_path / "out"


def test_main_writes_the_three_reward_files(tmp_path):
    transcript = "\n".join(
        [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "query_aap2",
                                "input": {"action": "find_jobs"},
                            }
                        ]
                    },
                }
            ),
            json.dumps(
                {"type": "result", "subtype": "success", "is_error": False, "result": "Job 90420."}
            ),
        ]
    )
    expected, logs, out = _write_run(tmp_path, _contract(), transcript)
    code = main(["--expected", str(expected), "--agent-logs", str(logs), "--out", str(out)])
    assert code == 0
    assert json.loads((out / "reward.json").read_text())["reward"] == 1.0
    assert (out / "reward.txt").read_text() == "1.0"
    assert "weights" in json.loads((out / "reward-detail.json").read_text())


def test_main_refuses_an_unreadable_contract_rather_than_scoring_zero(tmp_path):
    """A zero would report a bypassed authoring gate as a bad agent run."""
    expected, logs, out = _write_run(tmp_path, _contract(contract="bench/v2"), "")
    code = main(["--expected", str(expected), "--agent-logs", str(logs), "--out", str(out)])
    assert code == 2
    assert not (out / "reward.txt").exists()
    assert "bench/v2" in json.loads((out / "reward-detail.json").read_text())["error"]


def test_main_reads_both_jsonl_and_txt_logs(tmp_path):
    expected, logs, out = _write_run(tmp_path, _contract(), "")
    (logs / "extra.txt").write_text(
        json.dumps(
            {"type": "result", "subtype": "success", "is_error": False, "result": "Job 90420."}
        )
    )
    assert main(["--expected", str(expected), "--agent-logs", str(logs), "--out", str(out)]) == 0
    assert json.loads((out / "reward.json").read_text())["assertions"] == 1.0


# -- the container constraint ----------------------------------------------


def test_verify_py_never_imports_testgen():
    """It executes in a bare ubi9 container where the package does not exist."""
    source = Path("src/testgen/suite/verify.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders = [
        node
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Import)
            and any(alias.name.startswith("testgen") for alias in node.names)
        )
        or (isinstance(node, ast.ImportFrom) and (node.module or "").startswith("testgen"))
    ]
    assert offenders == []


def test_test_sh_invokes_the_verifier_and_propagates_its_exit_code():
    script = Path("src/testgen/suite/test.sh").read_text(encoding="utf-8")
    assert "/tests/verify.py" in script
    assert "/logs/verifier" in script
    assert "exit $?" in script
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_verify_reward.py -q`
Expected: FAIL — `ImportError: cannot import name 'score_trajectory'`

- [ ] **Step 3: Add trajectory scoring**

Append to `src/testgen/suite/verify.py`:

```python
def _match_unordered(operations, calls):
    """-> the set of expected-operation indices satisfied, greedily.

    Each actual call is consumed by at most one expected operation. Without
    that, a single call would satisfy a two-operation trajectory and hop depth
    -- the whole difficulty signal -- would stop being measured.
    """
    used, matched = set(), set()
    for i, operation in enumerate(operations):
        for j, call in enumerate(calls):
            if j in used or not call_matches(operation, call):
                continue
            used.add(j)
            matched.add(i)
            break
    return matched


def score_trajectory(calls, trajectory):
    """-> (score, detail) for one of the three declared match modes."""
    operations = trajectory.get("operations") or []
    match = trajectory.get("match", "subset")

    if match == "exact-sequence":
        pairwise = len(operations) == len(calls) and all(
            call_matches(operation, call) for operation, call in zip(operations, calls)
        )
        matched = set(range(len(operations))) if pairwise else set()
        score = 1.0 if pairwise else 0.0
    else:
        matched = _match_unordered(operations, calls)
        complete = len(matched) == len(operations)
        if match == "exact-set":
            score = 1.0 if complete and len(calls) == len(operations) else 0.0
        else:
            score = 1.0 if not operations else len(matched) / len(operations)

    detail = {
        "match": match,
        "actual": [{"tool": name, "args": args} for name, args in calls],
        "unmatched": [op for i, op in enumerate(operations) if i not in matched],
        "extra_calls": max(0, len(calls) - len(operations)),
    }
    return score, detail
```

- [ ] **Step 4: Add `compute_reward` and `main`**

Append to `src/testgen/suite/verify.py`:

```python
def compute_reward(contract, calls, answer, ok):
    """-> (reward, detail).

    `reward` holds only scalars. Everything a human needs to understand the
    number goes in `detail`, written alongside as reward-detail.json: a bare
    0.625 with no way to see which check failed costs real debugging time.

    The completion gate multiplies rather than contributes. A run that crashed
    or answered nothing has not earned partial credit for calling the right
    tools, but the components stay visible in `reward` so the gate is
    distinguishable from a genuinely wrong answer.
    """
    completion = contract.get("completion") or {}
    gate = 1.0
    if completion.get("status", "ok") == "ok" and not ok:
        gate = 0.0
    if completion.get("nonempty_answer", True) and not answer.strip():
        gate = 0.0

    assertion_score, assertion_detail = score_assertions(
        answer, calls, contract.get("assertions") or []
    )
    trajectory_score, trajectory_detail = score_trajectory(
        calls, contract.get("trajectory") or {}
    )

    weights = contract.get("weights") or {}
    weight_assertions = float(weights.get("assertions", DEFAULT_WEIGHTS["assertions"]))
    weight_trajectory = float(weights.get("trajectory", DEFAULT_WEIGHTS["trajectory"]))
    combined = weight_assertions * assertion_score + weight_trajectory * trajectory_score

    reward = {
        "reward": round(gate * combined, 6),
        "completion": gate,
        "assertions": round(assertion_score, 6),
        "trajectory": round(trajectory_score, 6),
    }
    detail = {
        "scenario_id": contract.get("scenario_id"),
        "gate": gate,
        "weights": {"assertions": weight_assertions, "trajectory": weight_trajectory},
        "assertions": assertion_detail,
        "trajectory": trajectory_detail,
    }
    return reward, detail


def _read_logs(agent_logs):
    """Concatenate every transcript file in the agent log directory.

    Globs *.jsonl and *.txt, so --out must not point at --agent-logs: a second
    run would otherwise read its own reward.txt back as transcript input.
    """
    parts = []
    for pattern in ("*.jsonl", "*.txt"):
        for path in sorted(Path(agent_logs).glob(pattern)):
            parts.append(path.read_text(errors="replace"))
    return "\n".join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", default="/tests/expected.json")
    parser.add_argument("--agent-logs", default="/logs/agent")
    parser.add_argument("--out", default="/logs/verifier")
    args = parser.parse_args(argv)

    contract = json.loads(Path(args.expected).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    declared = contract.get("contract")
    if declared != CONTRACT:
        # Refuse rather than write a misleading 0. A contract this verifier
        # cannot read is a bypassed authoring gate, not a bad agent run, and
        # reporting it as 0 would invert that conclusion. No reward.txt is
        # written, so the platform sees a missing reward instead of a real one.
        message = f"expected contract {CONTRACT!r}, got {declared!r}"
        (out / "reward-detail.json").write_text(json.dumps({"error": message}, indent=2))
        print(f"verify.py: {message}", file=sys.stderr)
        return 2

    calls, answer, ok = parse_transcript(_read_logs(args.agent_logs))
    reward, detail = compute_reward(contract, calls, answer, ok)

    (out / "reward.json").write_text(json.dumps(reward, indent=2, sort_keys=True))
    (out / "reward.txt").write_text(str(reward["reward"]))
    (out / "reward-detail.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True, default=str)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Create the Harbor entrypoint**

Create `src/testgen/suite/test.sh`:

```bash
#!/bin/bash
# Harbor verifier entrypoint for a testgen-emitted task.
#
# Harbor's contract is a bare float in /logs/verifier/reward.txt; reward.json
# and reward-detail.json are written alongside for humans. verify.py writes no
# reward.txt when it refuses to score, so an unreadable contract reaches the
# platform as a missing reward rather than as a real zero.
#
# emit copies this file verbatim into every package; the tracked original is
# src/testgen/suite/test.sh.
set -o pipefail
mkdir -p /logs/verifier
python3 /tests/verify.py \
  --expected /tests/expected.json \
  --agent-logs /logs/agent \
  --out /logs/verifier
exit $?
```

Make it executable: `chmod +x src/testgen/suite/test.sh`

- [ ] **Step 6: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 7: Lint and commit**

```bash
make check
git add src/testgen/suite tests/unit/test_verify_reward.py
git commit -S -s -m "feat: Finish the generic verifier with trajectory scoring and reward

Three match modes, with subset consuming each actual call at most once:
otherwise a single call satisfies a two-operation trajectory and hop
depth, the whole difficulty signal, stops being measured.

An unreadable contract is refused, not scored zero -- a zero would
report a bypassed authoring gate as a bad agent run and invert the
conclusion. No reward.txt is written in that case, so the platform sees
a missing reward rather than a real one.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 9: Translate an oracle into the scoring contract

`emit` is the only Harbor-aware component, and this is the half that does the translating: an `expected.json` written against the world model becomes a `tests/expected.json` written against tool names a transcript will actually show. Everything upstream stays platform-neutral, so retargeting a second evaluation platform means a second emitter, not a re-run.

Translation is where a capability id becomes a tool call, so it is where a missing `binding` surfaces.

**Files:**
- Create: `src/testgen/emit.py` (translation half; Task 10 adds package writing)
- Test: `tests/unit/test_emit_contract.py` (create)

**Interfaces:**
- Consumes: `testgen.suite.verify.CONTRACT` and `DEFAULT_WEIGHTS` (the single definition of both — `emit` must not restate the string), `testgen.findings.Finding`.
- Produces:
  - `emit.bindings(world: dict) -> dict[str, dict]` — capability id to its binding, omitting capabilities that declare none
  - `emit.call_spec(binding: dict, args: dict) -> dict` — `{"tool": str, "args": dict}` with `fixed_args` merged under the operation's own args
  - `emit.to_contract(world: dict, scenario: dict, expected: dict) -> tuple[dict | None, list[tuple[str, str]]]` — the contract, or `None` when problems block it; problems are `(pointer, message)` pairs that Task 10 turns into `Finding`s

**Assertion ids are `a<source index>`.** The index into `expected.json`'s own `assertions` array, so a failure in `reward-detail.json` traces back to a specific assertion in the run directory with no lookup table.

**`fixed_args` merge order.** `{**binding["fixed_args"], **operation_args}` — the operation's own arguments win. `fixed_args` identifies *which* capability is being invoked; a collision means the oracle is overriding the identity of the call it named, and letting the operation win makes that visible in the emitted contract rather than silently discarding it.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_emit_contract.py`:

```python
"""Translating an oracle into the scoring contract verify.py consumes."""

from __future__ import annotations

import pytest

from testgen.emit import bindings, call_spec, to_contract
from testgen.suite.verify import CONTRACT
from tests.builders import minimal_expected, minimal_scenarios, minimal_world_model


def _parts(**over):
    world = over.get("world", minimal_world_model())
    scenario = over.get("scenario", minimal_scenarios()["scenarios"][0])
    expected = over.get("expected", minimal_expected())
    return world, scenario, expected


def test_bindings_are_indexed_by_capability_id():
    assert bindings(minimal_world_model()) == {
        "cap-find-jobs": {"tool": "query_aap2", "fixed_args": {"action": "find_jobs"}}
    }


def test_a_capability_without_a_binding_is_absent_from_the_index():
    world = minimal_world_model()
    del world["capabilities"][0]["binding"]
    assert bindings(world) == {}


def test_call_spec_merges_fixed_args_under_the_operations_own_args():
    spec = call_spec(
        {"tool": "query_aap2", "fixed_args": {"action": "find_jobs"}},
        {"controller": "prod0"},
    )
    assert spec == {"tool": "query_aap2", "args": {"action": "find_jobs", "controller": "prod0"}}


def test_an_operation_arg_overrides_a_fixed_arg():
    """A collision means the oracle is overriding the call's identity; make it visible."""
    spec = call_spec({"tool": "t", "fixed_args": {"action": "a"}}, {"action": "b"})
    assert spec["args"]["action"] == "b"


def test_a_clean_oracle_translates_with_no_problems():
    contract, problems = to_contract(*_parts())
    assert problems == []
    assert contract["contract"] == CONTRACT
    assert contract["scenario_id"] == "scn-001"
    assert contract["completion"] == {"status": "ok", "nonempty_answer": True}
    assert contract["weights"] == {"assertions": 0.8, "trajectory": 0.2}


def test_a_data_assertion_keeps_its_kind_value_and_rationale_and_drops_its_grounding():
    """seed_pointer grounds the label at authoring time; the container cannot use it."""
    contract, _ = to_contract(*_parts())
    first = contract["assertions"][0]
    assert first == {
        "id": "a0",
        "kind": "answer_contains",
        "target": "answer",
        "value": "90420",
        "rationale": "the failing job id must appear in the answer",
    }


def test_a_trajectory_assertion_becomes_a_tool_and_args_pair():
    contract, _ = to_contract(*_parts())
    second = contract["assertions"][1]
    assert second["id"] == "a1"
    assert second["kind"] == "tool_called"
    assert second["tool"] == "query_aap2"
    assert second["args"] == {"action": "find_jobs"}
    assert "capability_id" not in second


def test_the_trajectory_operations_are_translated_and_the_match_mode_kept():
    contract, _ = to_contract(*_parts())
    assert contract["trajectory"]["match"] == "subset"
    assert contract["trajectory"]["operations"] == [
        {"tool": "query_aap2", "args": {"action": "find_jobs", "controller": "prod0"}}
    ]


def test_assertion_ids_follow_the_source_index():
    expected = minimal_expected()
    expected["assertions"].append(
        {
            "kind": "answer_excludes",
            "target": "answer",
            "value": "DNS",
            "rationale": "nothing in the seed supports a network cause",
            "grounded_in": {"seed_pointer": "/collections/jobs/0/dns_error"},
        }
    )
    contract, _ = to_contract(*_parts(expected=expected))
    assert [a["id"] for a in contract["assertions"]] == ["a0", "a1", "a2"]


def test_an_unbound_capability_in_an_assertion_is_a_problem_and_blocks_the_contract():
    world = minimal_world_model()
    del world["capabilities"][0]["binding"]
    contract, problems = to_contract(*_parts(world=world))
    assert contract is None
    pointers = [p for p, _ in problems]
    assert "/assertions/1/capability_id" in pointers
    assert any("declares no binding" in message for _, message in problems)


def test_an_unbound_capability_in_the_trajectory_is_a_problem():
    world = minimal_world_model()
    del world["capabilities"][0]["binding"]
    _, problems = to_contract(*_parts(world=world))
    assert "/trajectory/operations/0/capability_id" in [p for p, _ in problems]


def test_every_problem_is_reported_not_just_the_first():
    """emit gets one bounded repair attempt, so it must report the whole list."""
    world = minimal_world_model()
    del world["capabilities"][0]["binding"]
    _, problems = to_contract(*_parts(world=world))
    assert len(problems) >= 2


@pytest.mark.parametrize("match", ["subset", "exact-set", "exact-sequence"])
def test_each_match_mode_survives_translation(match):
    expected = minimal_expected()
    expected["trajectory"] = dict(expected["trajectory"], match=match)
    contract, problems = to_contract(*_parts(expected=expected))
    assert problems == []
    assert contract["trajectory"]["match"] == match
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_emit_contract.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'testgen.emit'`

- [ ] **Step 3: Write the translation half of `emit.py`**

Create `src/testgen/emit.py`:

```python
"""Compiling accepted instances into Harbor task packages: stage 6.

This is the only Harbor-aware module in the project. Everything upstream is
platform-neutral, so retargeting a second evaluation platform means writing a
second emitter, not re-running the pipeline.

It is code rather than a skill because of the reproducibility criterion: if emit
were a prompt, two runs with identical stage-4 and stage-5 artifacts could still
produce different suites, and variance could no longer be attributed to a stage.
A thin tg-emit skill exists purely as the human-facing entry point.
"""

from __future__ import annotations

from typing import Any

from testgen.suite.verify import CONTRACT, DEFAULT_WEIGHTS

_DATA_KINDS = ("answer_contains", "answer_excludes", "value_equals")
_TRAJECTORY_KINDS = ("tool_called", "tool_not_called")


def bindings(world: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Capability id -> its tool binding, omitting capabilities that declare none.

    Absence is the caller's problem to report, not this function's to paper
    over: a guessed binding is a wrong tool name in the scoring path.
    """
    return {
        cap["id"]: cap["binding"] for cap in world.get("capabilities", []) if cap.get("binding")
    }


def call_spec(binding: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """A {tool, args} pair for verify.py, with fixed_args merged underneath.

    The operation's own arguments win. fixed_args identifies *which* capability
    a shared tool is invoking, so a collision means the oracle is overriding the
    identity of the call it named -- better visible in the emitted contract than
    silently discarded.
    """
    return {"tool": binding["tool"], "args": {**binding.get("fixed_args", {}), **args}}


def to_contract(
    world: dict[str, Any], scenario: dict[str, Any], expected: dict[str, Any]
) -> tuple[dict[str, Any] | None, list[tuple[str, str]]]:
    """Translate one oracle into the contract verify.py consumes.

    Returns (contract, problems). A non-empty problems list means the contract
    could not be built faithfully and None is returned rather than a package
    that scores against a guess. Problems are (pointer, message) pairs; the
    whole list is returned rather than the first, because emit gets one bounded
    repair attempt and needs every reason.

    grounded_in.seed_pointer is deliberately dropped. It is the authoring-time
    proof that a label is reachable in its own seed, enforced by check-refs; the
    container has no seed to resolve it against and carrying it would suggest
    the verifier checks something it cannot.
    """
    bound = bindings(world)
    problems: list[tuple[str, str]] = []

    def unbound(pointer: str, capability_id: str) -> None:
        problems.append(
            (
                pointer,
                f"capability {capability_id!r} declares no binding, so it cannot be turned into "
                "a tool call; add binding.tool and binding.fixed_args in the world model",
            )
        )

    assertions: list[dict[str, Any]] = []
    for i, assertion in enumerate(expected.get("assertions", [])):
        kind = assertion["kind"]
        entry: dict[str, Any] = {
            "id": f"a{i}",
            "kind": kind,
            "value": assertion["value"],
            "rationale": assertion["rationale"],
        }
        if "target" in assertion:
            entry["target"] = assertion["target"]
        if kind in _DATA_KINDS:
            assertions.append(entry)
            continue
        if kind in _TRAJECTORY_KINDS:
            capability_id = assertion["capability_id"]
            binding = bound.get(capability_id)
            if binding is None:
                unbound(f"/assertions/{i}/capability_id", capability_id)
                continue
            entry.update(call_spec(binding, {}))
            assertions.append(entry)
            continue
        problems.append(
            (
                f"/assertions/{i}/kind",
                f"unknown assertion kind {kind!r}; the vocabulary is closed and verify.py "
                "cannot score this",
            )
        )

    trajectory_in = expected.get("trajectory", {})
    operations: list[dict[str, Any]] = []
    for i, operation in enumerate(trajectory_in.get("operations", [])):
        capability_id = operation["capability_id"]
        binding = bound.get(capability_id)
        if binding is None:
            unbound(f"/trajectory/operations/{i}/capability_id", capability_id)
            continue
        operations.append(call_spec(binding, operation.get("args", {})))

    if problems:
        return None, problems

    contract = {
        "contract": CONTRACT,
        "scenario_id": scenario["id"],
        "completion": dict(expected["completion"]),
        "assertions": assertions,
        "trajectory": {"match": trajectory_in["match"], "operations": operations},
        "weights": dict(DEFAULT_WEIGHTS),
    }
    return contract, []
```

**On the weights.** They are the fixed default for now. Choosing them per scenario is a judgment call about where a given test's discriminating power sits, which belongs to a skill and to evidence from a real score spread — neither of which exists yet. A constant here is honest; a per-scenario guess would look like calibration.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_emit_contract.py -q`
Expected: PASS.

- [ ] **Step 5: Run the whole suite, lint, and commit**

```bash
uv run pytest -q
make check
git add src/testgen/emit.py tests/unit/test_emit_contract.py
git commit -S -s -m "feat: Translate an oracle into the scoring contract

The Harbor-aware half of emit: an expected.json written against the
world model becomes a contract written against tool names a transcript
will actually show. Assertion ids follow the source index, so a failure
in reward-detail.json traces back to a specific assertion with no lookup.

grounded_in.seed_pointer is dropped deliberately -- it is the
authoring-time reachability proof, enforced by check-refs, and the
container has no seed to resolve it against.

An unbound capability blocks the contract rather than being guessed at:
a guessed binding is a wrong tool name in the scoring path.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 10: Write the task packages

The other half of `emit`: select the instances that earned a place in the suite, and write each as a self-contained Harbor package.

**Files:**
- Modify: `src/testgen/emit.py` (`suite_template_dir`, `emit_run`, and the file writers)
- Modify: `src/testgen/cli.py` (the `emit` subcommand)
- Test: `tests/unit/test_emit_packages.py` (create)

**Interfaces:**
- Consumes: everything Task 9 produced, `testgen.artifacts.write_json`, `testgen.paths.RunPaths`, `testgen.findings.Finding`.
- Produces:
  - `emit.HARBOR_SCHEMA_VERSION = "1.3"`, `emit.DOCKER_IMAGE = "registry.access.redhat.com/ubi9/ubi:latest"`
  - `emit.suite_template_dir() -> Path` — where `verify.py` and `test.sh` are read from, overridable via `TESTGEN_SUITE_DIR`, mirroring `validate.schema_dir()`
  - `emit.emit_run(run: RunPaths) -> tuple[list[str], list[Finding]]` → `(emitted_scenario_ids, findings)`
  - CLI: `testgen emit --run DIR`, printing one emitted task directory per line

**What gets emitted.** A scenario whose status is `active` *and* whose verdict is `accept`. A `reject` verdict is a scenario correctly thrown out and is skipped silently — the coverage report already accounts for the cell it lost. Two states *are* findings, because `emit` runs as stage 6 and both mean the pipeline did not finish:

- an instance with **no verdict** — `challenge` never judged it. (Note this differs from `refs.check_verdicts`, which tolerates the same state because it runs after *every* stage and would otherwise fire between instantiate and challenge. `emit` runs only once, after challenge, so here the absence is real.)
- a verdict of **`re-seed`** — the adversary asked for one re-instantiation and it never happened.

**The eight files per package:**

| File | Content |
|---|---|
| `task.toml` | Harbor task metadata |
| `instruction.md` | `scenario["user_intent"]` |
| `seed.json` | verbatim copy of the instance seed — the simulated backend loads it |
| `golden.json` | `{"answer": expected["answer_reference"], "tool_calls": [...]}` for the oracle agent |
| `provenance.md` | how this task came to exist, from the scenario and the verdict |
| `tests/expected.json` | Task 9's contract |
| `tests/verify.py` | verbatim copy of the template |
| `tests/test.sh` | verbatim copy of the template |

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_emit_packages.py`:

```python
"""Writing an accepted instance out as a Harbor task package."""

from __future__ import annotations

import json
import tomllib

from testgen.artifacts import write_json
from testgen.emit import emit_run, suite_template_dir
from testgen.paths import RunPaths
from tests.builders import (
    minimal_expected,
    minimal_manifest,
    minimal_scenarios,
    minimal_seed,
    minimal_verdict,
    minimal_world_model,
)

SID = "scn-001"


def _run(tmp_path, *, verdict=..., scenarios=None, world=None, expected=None) -> RunPaths:
    """A run populated through challenge, ready for emit."""
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    write_json(run.manifest, minimal_manifest())
    write_json(run.world_model, world if world is not None else minimal_world_model())
    write_json(run.scenarios, scenarios if scenarios is not None else minimal_scenarios())
    write_json(run.seed(SID), minimal_seed())
    write_json(run.expected(SID), expected if expected is not None else minimal_expected())
    if verdict is not ...:
        if verdict is not None:
            write_json(run.verdict(SID), verdict)
    else:
        write_json(run.verdict(SID), minimal_verdict())
    return run


def test_an_accepted_instance_produces_all_eight_files(tmp_path):
    run = _run(tmp_path)
    emitted, findings = emit_run(run)
    assert findings == []
    assert emitted == [SID]
    task = run.task_dir(SID)
    for name in ("task.toml", "instruction.md", "seed.json", "golden.json", "provenance.md"):
        assert (task / name).is_file(), name
    for name in ("expected.json", "verify.py", "test.sh"):
        assert (task / "tests" / name).is_file(), name


def test_the_task_toml_is_parseable_and_names_the_target(tmp_path):
    run = _run(tmp_path)
    emit_run(run)
    payload = tomllib.loads((run.task_dir(SID) / "task.toml").read_text())
    assert payload["schema_version"] == "1.3"
    assert payload["task"]["name"].endswith(SID)
    assert payload["metadata"]["agent_type"] == "aap2"
    assert payload["environment"]["mcp_servers"][0]["url"] == "${BACKEND_MCP_URL}"
    assert payload["verifier"]["timeout_sec"] > 0
    assert payload["agent"]["timeout_sec"] > 0


def test_the_instruction_is_the_scenarios_user_intent(tmp_path):
    run = _run(tmp_path)
    emit_run(run)
    text = (run.task_dir(SID) / "instruction.md").read_text()
    assert text.strip() == minimal_scenarios()["scenarios"][0]["user_intent"]


def test_the_seed_is_copied_verbatim(tmp_path):
    run = _run(tmp_path)
    emit_run(run)
    assert (run.task_dir(SID) / "seed.json").read_text() == run.seed(SID).read_text()


def test_the_verifier_and_entrypoint_are_copied_verbatim(tmp_path):
    """The tested file and the executed file must not differ."""
    run = _run(tmp_path)
    emit_run(run)
    for name in ("verify.py", "test.sh"):
        assert (run.task_dir(SID) / "tests" / name).read_bytes() == (
            suite_template_dir() / name
        ).read_bytes()


def test_the_golden_holds_the_reference_answer_and_the_expected_calls(tmp_path):
    run = _run(tmp_path)
    emit_run(run)
    golden = json.loads((run.task_dir(SID) / "golden.json").read_text())
    assert golden["answer"] == minimal_expected()["answer_reference"]
    assert golden["tool_calls"] == [
        {"tool": "query_aap2", "args": {"action": "find_jobs", "controller": "prod0"}}
    ]


def test_the_provenance_records_the_discriminating_fact_and_the_adversarys_finding(tmp_path):
    run = _run(tmp_path)
    emit_run(run)
    text = (run.task_dir(SID) / "provenance.md").read_text()
    assert "exactly one prod0 job failed inside the window" in text
    assert "cell:cap-find-jobs/oc-success" in text
    assert "minimum_tool_calls_found" in text


def test_the_emitted_contract_validates_against_verify_pys_expectations(tmp_path):
    from testgen.suite.verify import CONTRACT, compute_reward

    run = _run(tmp_path)
    emit_run(run)
    contract = json.loads((run.task_dir(SID) / "tests" / "expected.json").read_text())
    assert contract["contract"] == CONTRACT
    reward, _ = compute_reward(
        contract, [("query_aap2", {"action": "find_jobs", "controller": "prod0"})], "Job 90420.", True
    )
    assert reward["reward"] == 1.0


def test_a_rejected_scenario_is_skipped_without_a_finding(tmp_path):
    """The coverage report already accounts for the cell it lost."""
    scenarios = minimal_scenarios()
    scenarios["scenarios"][0]["status"] = "rejected"
    scenarios["scenarios"][0]["rejected_reason"] = "ambiguous"
    run = _run(tmp_path, scenarios=scenarios, verdict=minimal_verdict(verdict="reject"))
    emitted, findings = emit_run(run)
    assert emitted == []
    assert findings == []
    assert not run.task_dir(SID).exists()


def test_an_instance_with_no_verdict_is_a_finding(tmp_path):
    """emit runs once, after challenge, so here the absence is real."""
    run = _run(tmp_path, verdict=None)
    emitted, findings = emit_run(run)
    assert emitted == []
    assert len(findings) == 1
    assert "has no verdict" in findings[0].message


def test_a_re_seed_verdict_is_a_finding(tmp_path):
    run = _run(tmp_path, verdict=minimal_verdict(verdict="re-seed"))
    emitted, findings = emit_run(run)
    assert emitted == []
    assert any("re-seed" in f.message for f in findings)


def test_an_unbound_capability_becomes_a_finding_and_writes_no_package(tmp_path):
    world = minimal_world_model()
    del world["capabilities"][0]["binding"]
    run = _run(tmp_path, world=world)
    emitted, findings = emit_run(run)
    assert emitted == []
    assert findings
    assert all(f.layer == "emit" for f in findings)
    assert not run.task_dir(SID).exists(), "a package must not be half-written"


def test_a_missing_world_model_is_a_finding_not_a_crash(tmp_path):
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    emitted, findings = emit_run(run)
    assert emitted == []
    assert len(findings) == 1


def test_re_emitting_replaces_a_stale_package(tmp_path):
    run = _run(tmp_path)
    emit_run(run)
    stale = run.task_dir(SID) / "stale.txt"
    stale.write_text("left over from an earlier emit")
    emit_run(run)
    assert not stale.exists()


def test_emit_is_byte_stable_across_runs(tmp_path):
    """Two emits of one run directory must produce identical bytes."""
    run = _run(tmp_path)
    emit_run(run)
    first = {
        p.relative_to(run.suite_dir): p.read_bytes()
        for p in sorted(run.suite_dir.rglob("*"))
        if p.is_file()
    }
    emit_run(run)
    second = {
        p.relative_to(run.suite_dir): p.read_bytes()
        for p in sorted(run.suite_dir.rglob("*"))
        if p.is_file()
    }
    assert first == second
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_emit_packages.py -q`
Expected: FAIL — `ImportError: cannot import name 'emit_run' from 'testgen.emit'`

- [ ] **Step 3: Add the constants and the template locator**

Add to the imports of `src/testgen/emit.py`:

```python
import os
import shutil
from pathlib import Path

import tomli_w

from testgen.artifacts import ArtifactError, read_json, write_json
from testgen.findings import Finding
from testgen.paths import RunPaths
```

and, below the kind tuples:

```python
# Harbor task metadata. Pinned rather than discovered: a suite emitted against
# one Harbor task schema and scored against another is a silent mismatch.
HARBOR_SCHEMA_VERSION = "1.3"
DOCKER_IMAGE = "registry.access.redhat.com/ubi9/ubi:latest"
VERIFIER_TIMEOUT_SEC = 120.0
AGENT_TIMEOUT_SEC = 600.0
SUITE_NAME = "testgen"


def suite_template_dir() -> Path:
    """Directory holding verify.py and test.sh.

    Mirrors validate.schema_dir(): package data beside the module so an
    installed copy can emit, overridable via TESTGEN_SUITE_DIR so a candidate
    verifier can be emitted without reinstalling.
    """
    override = os.environ.get("TESTGEN_SUITE_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "suite"
```

- [ ] **Step 4: Add the per-file writers**

Append to `src/testgen/emit.py`:

```python
def _task_toml(scenario: dict[str, Any], world: dict[str, Any]) -> str:
    target = world.get("target", {})
    payload = {
        "schema_version": HARBOR_SCHEMA_VERSION,
        "task": {
            "name": f"{SUITE_NAME}/{scenario['id']}",
            "description": scenario["title"],
        },
        "metadata": {
            "agent_type": target.get("name", "unknown"),
            "suite": SUITE_NAME,
            "goal_id": scenario["goal_id"],
            "actor_id": scenario["actor_id"],
            "hop_depth": scenario["hop_depth"],
        },
        "environment": {
            "docker_image": DOCKER_IMAGE,
            "workdir": "/",
            "mcp_servers": [{"name": "backend", "url": "${BACKEND_MCP_URL}"}],
        },
        "verifier": {"timeout_sec": VERIFIER_TIMEOUT_SEC},
        "agent": {"timeout_sec": AGENT_TIMEOUT_SEC},
    }
    return tomli_w.dumps(payload)


def _golden(expected: dict[str, Any], operations: list[dict[str, Any]]) -> dict[str, Any]:
    """The reference answer plus the calls that reach it.

    No tool *results*: nothing upstream records what the simulated backend would
    return, and inventing them would put fabricated data in the file the oracle
    agent is handed. The seed is the source of truth for results.
    """
    return {"answer": expected["answer_reference"], "tool_calls": operations}


def _provenance(scenario: dict[str, Any], expected: dict[str, Any], verdict: dict[str, Any]) -> str:
    provenance = scenario.get("provenance", {})
    alternatives = verdict.get("alternative_answers") or []
    cells = [
        f"{ref['capability_id']}/{ref['outcome_class_id']}"
        for ref in scenario.get("capability_refs", [])
    ]
    lines = [
        "# Provenance",
        "",
        "**Status:** generated by testgen. Every line below is copied from the run",
        "directory, never restated by hand.",
        "",
        f"- **Scenario:** `{scenario['id']}` — {scenario['title']}",
        f"- **Goal:** `{scenario['goal_id']}` for actor `{scenario['actor_id']}`",
        f"- **Declared hop depth:** {scenario['hop_depth']}",
        f"- **Discriminating fact:** {scenario['discriminating_fact']}",
        f"- **Coverage holes targeted:** {', '.join(provenance.get('hole_refs', [])) or 'none'}",
        f"- **Capability cells claimed:** {', '.join(cells) or 'none'}",
        f"- **Claims behind it:** {', '.join(provenance.get('claim_ids', [])) or 'none'}",
        f"- **Proposed in round:** {provenance.get('round', scenario['round'])}",
        "",
        "## Adversarial review",
        "",
        f"- **Verdict:** {verdict.get('verdict')}",
        f"- **Uniquely determined:** {verdict.get('uniquely_determined')}",
        f"- **Derivable without guessing:** {verdict.get('derivable_without_guessing')}",
        f"- **`minimum_tool_calls_found`:** {verdict.get('minimum_tool_calls_found')} "
        f"(against a declared hop depth of {scenario['hop_depth']})",
        f"- **Notes:** {verdict.get('notes', '')}",
    ]
    if alternatives:
        lines += ["", "### Alternative answers the adversary found world-consistent", ""]
        lines += [
            f"- {alt.get('answer')} — {alt.get('world_consistent_reason')}" for alt in alternatives
        ]
    lines += [
        "",
        "## Reference answer",
        "",
        expected["answer_reference"],
        "",
    ]
    return "\n".join(lines)
```

- [ ] **Step 5: Add `emit_run`**

Append to `src/testgen/emit.py`:

```python
def _load(path) -> Any | None:
    try:
        return read_json(path)
    except ArtifactError:
        return None


def emit_run(run: RunPaths) -> tuple[list[str], list[Finding]]:
    """Write a Harbor package for every accepted instance.

    Returns (emitted scenario ids, findings). A findings list means the suite is
    incomplete and the caller exits 1; packages for the instances that did
    translate are still written, so a single unbound capability does not cost
    the whole suite.
    """
    world = _load(run.world_model)
    if world is None:
        return [], [
            Finding(run.root, "emit", "", "no world model: emit needs 01-world-model.json")
        ]
    scenarios_doc = _load(run.scenarios) or {"scenarios": []}
    by_id = {s["id"]: s for s in scenarios_doc.get("scenarios", [])}

    emitted: list[str] = []
    findings: list[Finding] = []

    for sid in run.scenario_ids_with_instances():
        scenario = by_id.get(sid)
        if scenario is None or scenario.get("status") != "active":
            continue

        verdict = _load(run.verdict(sid))
        if verdict is None:
            findings.append(
                Finding(
                    run.instance_dir(sid),
                    "emit",
                    "",
                    f"instance {sid} has no verdict; challenge must judge every instance before "
                    "emit runs",
                )
            )
            continue
        if verdict.get("verdict") == "re-seed":
            findings.append(
                Finding(
                    run.verdict(sid),
                    "emit",
                    "/verdict",
                    f"instance {sid} is marked re-seed; the adversary asked for one "
                    "re-instantiation and it has not happened",
                )
            )
            continue
        if verdict.get("verdict") != "accept":
            continue

        expected = _load(run.expected(sid))
        seed = _load(run.seed(sid))
        if expected is None or seed is None:
            findings.append(
                Finding(
                    run.instance_dir(sid),
                    "emit",
                    "",
                    f"instance {sid} is missing seed.json or expected.json",
                )
            )
            continue

        contract, problems = to_contract(world, scenario, expected)
        if contract is None:
            findings.extend(
                Finding(run.expected(sid), "emit", pointer, message)
                for pointer, message in problems
            )
            continue

        task = run.task_dir(sid)
        # Replace rather than merge. A re-emit after a fix must not leave a
        # stale file behind, and the path is under 06-suite with a segment that
        # safe_segment has already vetted, so the tree being removed is one this
        # module wrote.
        if task.exists():
            shutil.rmtree(task)
        (task / "tests").mkdir(parents=True)

        (task / "task.toml").write_text(_task_toml(scenario, world), encoding="utf-8")
        (task / "instruction.md").write_text(
            scenario["user_intent"].rstrip("\n") + "\n", encoding="utf-8"
        )
        write_json(task / "seed.json", seed)
        write_json(task / "golden.json", _golden(expected, contract["trajectory"]["operations"]))
        (task / "provenance.md").write_text(
            _provenance(scenario, expected, verdict), encoding="utf-8"
        )
        write_json(task / "tests" / "expected.json", contract)
        for name in ("verify.py", "test.sh"):
            shutil.copyfile(suite_template_dir() / name, task / "tests" / name)
        (task / "tests" / "test.sh").chmod(0o755)
        emitted.append(sid)

    return emitted, findings
```

- [ ] **Step 6: Wire the CLI**

In `src/testgen/cli.py`, add the subparser after `p_dedupe`:

```python
    p_emit = subparsers.add_parser("emit", help="compile accepted instances into Harbor packages")
    p_emit.add_argument("--run", required=True)
```

add the import `from testgen.emit import emit_run`, and add the branch after the `dedupe-candidates` branch:

```python
        if args.command == "emit":
            run = _run_dir(args.run)
            emitted, findings = emit_run(run)
            for sid in emitted:
                print(run.task_dir(sid))
            return _report(findings)
```

`_report` prints findings to stdout and returns 1, so the emitted paths precede them. That ordering matters: a partially-successful emit must still tell the caller what it produced.

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/unit/test_emit_packages.py -q`
Expected: PASS. `test_emit_is_byte_stable_across_runs` is the one to watch — if it fails, something in the package is nondeterministic and that breaks `diff-runs` in Plan 3 before it is written.

- [ ] **Step 8: Smoke the CLI by hand**

```bash
uv run testgen emit --run /tmp/does-not-exist ; echo "exit=$?"
```

Expected: `error: run directory does not exist: /tmp/does-not-exist` on stderr and `exit=2`.

- [ ] **Step 9: Run the whole suite, lint, and commit**

```bash
uv run pytest -q
make check
git add src/testgen/emit.py src/testgen/cli.py tests/unit/test_emit_packages.py
git commit -S -s -m "feat: Write accepted instances out as Harbor task packages

Eight files per package, with verify.py and test.sh copied verbatim from
the tracked templates so the tested file and the executed file cannot
differ.

An instance with no verdict, or one still marked re-seed, is a finding
here even though refs.check_verdicts tolerates the first: check-refs
runs after every stage and would fire between instantiate and challenge,
while emit runs once, after challenge, so the absence is real.

golden.json carries no tool results. Nothing upstream records what the
backend would return and inventing them would hand the oracle agent
fabricated data.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 11: Give emit and smoke real gates

`STAGE_ARTIFACTS` maps both `emit` and `smoke` to `()`, so `validate --stage emit` returns exit 0 unconditionally — even when emit produced nothing at all. That was a defensible placeholder while neither stage existed. It is wrong as a merged contract now that one of them does: an orchestrator reads 0 as success and dispatches the next stage against an empty suite.

The smoke report's schema is written here too, before its producer exists in Plan 3. That is the right order for this project — the artifact contract is the architecture, and a stage whose output shape is undecided is a stage whose consumers cannot be written.

**Files:**
- Create: `src/testgen/schema/suite-expected-0.1.json`, `src/testgen/schema/report-0.1.json`
- Modify: `src/testgen/paths.py` (`scenario_ids_with_tasks`), `src/testgen/validate.py` (register both, real `STAGE_ARTIFACTS`), `src/testgen/refs.py` (`check_suite`)
- Modify: `tests/builders.py` (`minimal_suite_expected`, `minimal_report`)
- Test: `tests/unit/test_validate.py` (extend), `tests/unit/test_refs_suite.py` (create), `tests/unit/test_refs_states.py` (extend)

**Interfaces:**
- Consumes: `emit.emit_run` (the states table builds its emit state by running the real emitter rather than approximating its output by hand).
- Produces:
  - `RunPaths.scenario_ids_with_tasks() -> list[str]`
  - `refs.check_suite(run: RunPaths) -> list[Finding]`
  - `ARTIFACT_SCHEMAS` gains `"suite-expected"` and `"report"`; `STAGE_ARTIFACTS["emit"] = ("suite-expected",)` and `STAGE_ARTIFACTS["smoke"] = ("report",)`
  - `tests.builders.minimal_suite_expected(**over)`, `tests.builders.minimal_report(**over)`

**This task changes an existing behaviour on purpose.** `validate --stage smoke` will now report a finding on any run that has not produced `07-report.json`. Existing tests asserting that `emit` and `smoke` validate trivially must be updated to assert the new contract — do not weaken the gate to keep them green.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_refs_suite.py`:

```python
"""check_suite: an emitted package is complete and addresses a real scenario."""

from __future__ import annotations

from testgen.artifacts import write_json
from testgen.emit import emit_run
from testgen.paths import RunPaths
from testgen.refs import check_suite
from tests.builders import (
    minimal_expected,
    minimal_manifest,
    minimal_scenarios,
    minimal_seed,
    minimal_verdict,
    minimal_world_model,
)

SID = "scn-001"

PACKAGE_FILES = (
    "task.toml",
    "instruction.md",
    "seed.json",
    "golden.json",
    "provenance.md",
    "tests/expected.json",
    "tests/verify.py",
    "tests/test.sh",
)


def _emitted_run(tmp_path) -> RunPaths:
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    write_json(run.manifest, minimal_manifest())
    write_json(run.world_model, minimal_world_model())
    write_json(run.scenarios, minimal_scenarios())
    write_json(run.seed(SID), minimal_seed())
    write_json(run.expected(SID), minimal_expected())
    write_json(run.verdict(SID), minimal_verdict())
    emitted, findings = emit_run(run)
    assert (emitted, findings) == ([SID], [])
    return run


def test_a_freshly_emitted_suite_is_clean(tmp_path):
    assert check_suite(_emitted_run(tmp_path)) == []


def test_no_suite_directory_is_not_a_finding(tmp_path):
    """The normal state before emit runs."""
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    assert check_suite(run) == []


def test_each_missing_package_file_is_reported(tmp_path):
    for name in PACKAGE_FILES:
        run = _emitted_run(tmp_path / name.replace("/", "_"))
        (run.task_dir(SID) / name).unlink()
        findings = check_suite(run)
        assert len(findings) == 1, f"{name}: {findings}"
        assert name in findings[0].message


def test_a_contract_naming_the_wrong_scenario_is_reported(tmp_path):
    run = _emitted_run(tmp_path)
    path = run.task_dir(SID) / "tests" / "expected.json"
    from testgen.artifacts import read_json

    write_json(path, read_json(path) | {"scenario_id": "scn-999"})
    findings = check_suite(run)
    assert len(findings) == 1
    assert "scn-999" in findings[0].message


def test_a_package_for_a_scenario_that_was_never_proposed_is_reported(tmp_path):
    run = _emitted_run(tmp_path)
    write_json(run.scenarios, minimal_scenarios(scenarios=[]))
    messages = " || ".join(f.message for f in check_suite(run))
    assert "was proposed" in messages


def test_a_package_for_a_non_active_scenario_is_reported(tmp_path):
    run = _emitted_run(tmp_path)
    scenarios = minimal_scenarios()
    scenarios["scenarios"][0]["status"] = "rejected"
    scenarios["scenarios"][0]["rejected_reason"] = "ambiguous"
    write_json(run.scenarios, scenarios)
    messages = " || ".join(f.message for f in check_suite(run))
    assert "rejected" in messages
```

Append to `tests/unit/test_validate.py`:

```python
def test_the_emit_stage_reports_a_run_that_produced_no_package(tmp_path):
    """Exit 0 here would tell the orchestrator an empty suite was a success."""
    from testgen.paths import RunPaths
    from testgen.validate import validate_stage

    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    findings = validate_stage(run, "emit")
    assert len(findings) == 1
    assert "produced no suite-expected artifact" in findings[0].message


def test_the_smoke_stage_reports_a_run_with_no_report(tmp_path):
    from testgen.paths import RunPaths
    from testgen.validate import validate_stage

    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    findings = validate_stage(run, "smoke")
    assert len(findings) == 1
    assert "produced no report artifact" in findings[0].message


def test_an_emitted_contract_validates(tmp_path):
    from testgen.artifacts import write_json
    from testgen.validate import validate_artifact
    from tests.builders import minimal_suite_expected

    path = tmp_path / "expected.json"
    write_json(path, minimal_suite_expected())
    assert validate_artifact(path, "suite-expected") == []


def test_a_contract_with_the_wrong_contract_string_is_rejected(tmp_path):
    from testgen.artifacts import write_json
    from testgen.validate import validate_artifact
    from tests.builders import minimal_suite_expected

    path = tmp_path / "expected.json"
    write_json(path, minimal_suite_expected(contract="bench/v2"))
    assert validate_artifact(path, "suite-expected") != []


def test_a_data_assertion_carrying_a_tool_is_rejected(tmp_path):
    """The two assertion shapes must stay distinguishable in the emitted file."""
    from testgen.artifacts import write_json
    from testgen.validate import validate_artifact
    from tests.builders import minimal_suite_expected

    payload = minimal_suite_expected()
    payload["assertions"][0]["tool"] = "query_aap2"
    path = tmp_path / "expected.json"
    write_json(path, payload)
    assert validate_artifact(path, "suite-expected") != []


def test_a_trajectory_assertion_without_a_tool_is_rejected(tmp_path):
    from testgen.artifacts import write_json
    from testgen.validate import validate_artifact
    from tests.builders import minimal_suite_expected

    payload = minimal_suite_expected()
    del payload["assertions"][1]["tool"]
    path = tmp_path / "expected.json"
    write_json(path, payload)
    assert validate_artifact(path, "suite-expected") != []


def test_a_minimal_report_validates(tmp_path):
    from testgen.artifacts import write_json
    from testgen.validate import validate_artifact
    from tests.builders import minimal_report

    path = tmp_path / "07-report.json"
    write_json(path, minimal_report())
    assert validate_artifact(path, "report") == []


def test_an_unscored_result_need_not_carry_a_reward(tmp_path):
    """Unscoreable is not zero: verify.py refuses rather than reporting 0.0."""
    from testgen.artifacts import write_json
    from testgen.validate import validate_artifact
    from tests.builders import minimal_report

    payload = minimal_report()
    payload["tasks"][0]["results"][0] = {"role": "oracle", "scored": False}
    path = tmp_path / "07-report.json"
    write_json(path, payload)
    assert validate_artifact(path, "report") == []


def test_a_scored_result_must_carry_a_reward(tmp_path):
    from testgen.artifacts import write_json
    from testgen.validate import validate_artifact
    from tests.builders import minimal_report

    payload = minimal_report()
    payload["tasks"][0]["results"][0] = {"role": "oracle", "scored": True}
    path = tmp_path / "07-report.json"
    write_json(path, payload)
    assert validate_artifact(path, "report") != []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_refs_suite.py tests/unit/test_validate.py -q`
Expected: FAIL — `cannot import name 'check_suite'`, and the two stage-gate tests find zero findings.

- [ ] **Step 3: Write the suite contract schema**

Create `src/testgen/schema/suite-expected-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "suite-expected-0.1.json",
  "title": "Scoring contract for one emitted task",
  "description": "What suite/verify.py consumes inside the task container. A projection of 04-instances/<sid>/expected.json onto tool names a transcript will show; grounded_in is deliberately absent, since the container has no seed to resolve a pointer against.",
  "type": "object",
  "required": ["contract", "scenario_id", "completion", "assertions", "trajectory", "weights"],
  "additionalProperties": false,
  "properties": {
    "contract": { "const": "testgen/v1" },
    "scenario_id": { "$ref": "#/$defs/id" },
    "completion": {
      "type": "object",
      "required": ["status", "nonempty_answer"],
      "additionalProperties": false,
      "properties": {
        "status": { "enum": ["ok", "error"] },
        "nonempty_answer": { "type": "boolean" }
      }
    },
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
        "operations": { "type": "array", "items": { "$ref": "#/$defs/call" } }
      }
    },
    "weights": {
      "type": "object",
      "required": ["assertions", "trajectory"],
      "additionalProperties": false,
      "properties": {
        "assertions": { "$ref": "#/$defs/fraction" },
        "trajectory": { "$ref": "#/$defs/fraction" }
      }
    }
  },
  "$defs": {
    "id": {
      "type": "string",
      "pattern": "\\A[A-Za-z0-9][A-Za-z0-9._-]*\\Z",
      "maxLength": 128
    },
    "fraction": { "type": "number", "minimum": 0, "maximum": 1 },
    "call": {
      "type": "object",
      "required": ["tool", "args"],
      "additionalProperties": false,
      "properties": {
        "tool": { "type": "string", "minLength": 1 },
        "args": { "type": "object" }
      }
    },
    "assertion": {
      "type": "object",
      "required": ["id", "kind", "value", "rationale"],
      "properties": {
        "id": { "$ref": "#/$defs/id" },
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
        "tool": { "type": "string", "minLength": 1 },
        "args": { "type": "object" }
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
            "additionalProperties": false,
            "properties": {
              "id": true, "kind": true, "target": true, "value": true, "rationale": true
            }
          }
        },
        {
          "if": {
            "properties": { "kind": { "enum": ["tool_called", "tool_not_called"] } },
            "required": ["kind"]
          },
          "then": {
            "required": ["tool", "args"],
            "additionalProperties": false,
            "properties": {
              "id": true, "kind": true, "target": true, "value": true,
              "rationale": true, "tool": true, "args": true
            }
          }
        }
      ]
    }
  }
}
```

- [ ] **Step 4: Write the smoke report schema**

Create `src/testgen/schema/report-0.1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "report-0.1.json",
  "title": "Smoke report",
  "description": "Stage 7. Three agent roles run the emitted suite: a weak baseline that should fail nearly everything, the agent under test, and an oracle handed the reference answer that should pass nearly everything. The third run is a test of the test suite -- if the oracle fails, the gold labels or the verifier are broken, not the agent.",
  "type": "object",
  "required": ["schema_version", "run_id", "agents", "tasks", "summary", "verdict"],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "0.1" },
    "run_id": { "$ref": "#/$defs/id" },
    "agents": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["role", "model"],
        "additionalProperties": false,
        "properties": {
          "role": { "$ref": "#/$defs/role" },
          "model": { "type": "string", "minLength": 1 },
          "notes": { "type": "string" }
        }
      }
    },
    "tasks": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["scenario_id", "results", "all_pass", "all_fail"],
        "additionalProperties": false,
        "properties": {
          "scenario_id": { "$ref": "#/$defs/id" },
          "results": {
            "type": "array",
            "minItems": 1,
            "items": { "$ref": "#/$defs/result" }
          },
          "all_pass": { "type": "boolean" },
          "all_fail": { "type": "boolean" }
        }
      }
    },
    "summary": {
      "type": "object",
      "required": [
        "mean_reward_by_role", "all_pass_tasks", "all_fail_tasks",
        "oracle_failures", "unscoreable"
      ],
      "additionalProperties": false,
      "properties": {
        "mean_reward_by_role": {
          "type": "object",
          "propertyNames": { "$ref": "#/$defs/role" },
          "additionalProperties": { "$ref": "#/$defs/fraction" }
        },
        "all_pass_tasks": { "type": "integer", "minimum": 0 },
        "all_fail_tasks": { "type": "integer", "minimum": 0 },
        "oracle_failures": { "type": "integer", "minimum": 0 },
        "unscoreable": { "type": "integer", "minimum": 0 }
      }
    },
    "verdict": {
      "description": "healthy: a real spread. degenerate_trivial: the weak baseline passes too much, so the suite is not testing anything. broken_labels: the oracle fails too much, which indicts the labels or the verifier rather than the agent. inconclusive: too few scoreable tasks to say.",
      "enum": ["healthy", "degenerate_trivial", "broken_labels", "inconclusive"]
    }
  },
  "$defs": {
    "id": {
      "type": "string",
      "pattern": "\\A[A-Za-z0-9][A-Za-z0-9._-]*\\Z",
      "maxLength": 128
    },
    "fraction": { "type": "number", "minimum": 0, "maximum": 1 },
    "role": { "enum": ["weak_baseline", "under_test", "oracle"] },
    "result": {
      "type": "object",
      "required": ["role", "scored"],
      "additionalProperties": false,
      "properties": {
        "role": { "$ref": "#/$defs/role" },
        "scored": { "type": "boolean" },
        "reward": { "$ref": "#/$defs/fraction" },
        "completion": { "$ref": "#/$defs/fraction" },
        "assertions": { "$ref": "#/$defs/fraction" },
        "trajectory": { "$ref": "#/$defs/fraction" },
        "notes": { "type": "string" }
      },
      "if": { "properties": { "scored": { "const": true } }, "required": ["scored"] },
      "then": { "required": ["reward", "completion", "assertions", "trajectory"] }
    }
  }
}
```

`scored: false` with no reward is the schema-level expression of the unscoreable-is-not-zero rule: `verify.py` refuses to score an unreadable contract rather than writing a 0, and a report that recorded that refusal as 0.0 would invert the conclusion.

- [ ] **Step 5: Add the task listing**

In `src/testgen/paths.py`, add after `scenario_ids_with_instances`:

```python
    def scenario_ids_with_tasks(self) -> list[str]:
        """Scenario ids that have an emitted task directory, sorted.

        Names that are not safe path segments are excluded, for the same reason
        scenario_ids_with_instances excludes them: returning one makes every
        later task_dir() call raise UnsafeSegment, which the CLI maps to exit 2.
        Unlike the instances directory this one is written only by emit, which
        derives every name from an id safe_segment already vetted -- so an
        unsafe name here means someone edited the run directory by hand, and
        skipping it is the honest response.
        """
        if not self.suite_dir.is_dir():
            return []
        return sorted(
            p.name for p in self.suite_dir.iterdir() if p.is_dir() and is_safe_segment(p.name)
        )
```

- [ ] **Step 6: Register the schemas and the gates**

In `src/testgen/validate.py`, add to `ARTIFACT_SCHEMAS`:

```python
    "suite-expected": "suite-expected-0.1.json",
    "report": "report-0.1.json",
```

change the last two entries of `STAGE_ARTIFACTS`:

```python
    "emit": ("suite-expected",),
    "smoke": ("report",),
```

and add the two branches to `_artifact_paths`, before the final `raise`:

```python
    if kind == "suite-expected":
        return [run.task_dir(sid) / "tests" / "expected.json" for sid in run.scenario_ids_with_tasks()]
    if kind == "report":
        return [run.report] if run.report.is_file() else []
```

Also update the comment above `STAGE_ARTIFACTS`, which currently explains the empty tuples — every stage now has a gate, so the comment should say so rather than describe a state that no longer exists.

- [ ] **Step 7: Add `check_suite`**

Insert into `src/testgen/refs.py` before `check_all`:

```python
_PACKAGE_FILES = (
    "task.toml",
    "instruction.md",
    "seed.json",
    "golden.json",
    "provenance.md",
    "tests/expected.json",
    "tests/verify.py",
    "tests/test.sh",
)


def check_suite(run: RunPaths) -> list[Finding]:
    """Each emitted package is complete and addresses an active scenario.

    A package missing its verifier or its contract is worse than no package: it
    reaches the platform, fails to score, and reads as an agent failure.
    """
    scenarios_doc = _load(run.scenarios) or {"scenarios": []}
    by_id = {s["id"]: s for s in scenarios_doc.get("scenarios", [])}
    out: list[Finding] = []

    for sid in run.scenario_ids_with_tasks():
        task = run.task_dir(sid)
        for name in _PACKAGE_FILES:
            if not (task / name).is_file():
                out.append(
                    Finding(task, "refs", "", f"emitted package is missing {name}")
                )

        scenario = by_id.get(sid)
        if scenario is None:
            out.append(Finding(task, "refs", "", f"no scenario named {sid} was proposed"))
        elif scenario.get("status") != "active":
            out.append(
                Finding(
                    task,
                    "refs",
                    "",
                    f"scenario {sid} has status {scenario.get('status')!r} but only an active "
                    "scenario should have been emitted",
                )
            )

        contract = _load(task / "tests" / "expected.json")
        if contract is not None and contract.get("scenario_id") != sid:
            out.append(
                Finding(
                    task / "tests" / "expected.json",
                    "refs",
                    "/scenario_id",
                    f"contract names scenario {contract.get('scenario_id')} but lives in the "
                    f"task directory for {sid}",
                )
            )
    return out
```

Add `findings.extend(check_suite(run))` to `check_all`, after `check_verdicts`.

- [ ] **Step 8: Add the two builders**

Append to `tests/builders.py`:

```python
def minimal_suite_expected(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract": "testgen/v1",
        "scenario_id": "scn-001",
        "completion": {"status": "ok", "nonempty_answer": True},
        "assertions": [
            {
                "id": "a0",
                "kind": "answer_contains",
                "target": "answer",
                "value": "90420",
                "rationale": "the failing job id must appear in the answer",
            },
            {
                "id": "a1",
                "kind": "tool_called",
                "target": "query_aap2.find_jobs",
                "value": "at least once",
                "rationale": "the agent must query rather than guess",
                "tool": "query_aap2",
                "args": {"action": "find_jobs"},
            },
        ],
        "trajectory": {
            "match": "subset",
            "operations": [
                {"tool": "query_aap2", "args": {"action": "find_jobs", "controller": "prod0"}}
            ],
        },
        "weights": {"assertions": 0.8, "trajectory": 0.2},
    }
    payload.update(over)
    return payload


def minimal_report(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "run_id": "run-20260806-120000",
        "agents": [
            {"role": "weak_baseline", "model": "claude-haiku-4-5-20251001", "notes": "no tools"},
            {"role": "under_test", "model": "claude-sonnet-5"},
            {"role": "oracle", "model": "claude-sonnet-5", "notes": "handed golden.json"},
        ],
        "tasks": [
            {
                "scenario_id": "scn-001",
                "results": [
                    {
                        "role": "weak_baseline",
                        "scored": True,
                        "reward": 0.0,
                        "completion": 1.0,
                        "assertions": 0.0,
                        "trajectory": 0.0,
                    },
                    {
                        "role": "under_test",
                        "scored": True,
                        "reward": 0.8,
                        "completion": 1.0,
                        "assertions": 1.0,
                        "trajectory": 0.0,
                    },
                    {
                        "role": "oracle",
                        "scored": True,
                        "reward": 1.0,
                        "completion": 1.0,
                        "assertions": 1.0,
                        "trajectory": 1.0,
                    },
                ],
                "all_pass": False,
                "all_fail": False,
            }
        ],
        "summary": {
            "mean_reward_by_role": {"weak_baseline": 0.0, "under_test": 0.8, "oracle": 1.0},
            "all_pass_tasks": 0,
            "all_fail_tasks": 0,
            "oracle_failures": 0,
            "unscoreable": 0,
        },
        "verdict": "healthy",
    }
    payload.update(over)
    return payload
```

Note `minimal_suite_expected` has **no** `schema_version` — the emitted contract carries `contract: "testgen/v1"` instead, because it is versioned by the verifier that reads it rather than by testgen's artifact set.

- [ ] **Step 9: Extend the pipeline states table**

In `tests/unit/test_refs_states.py`, add two states. The emit state runs the **real** emitter rather than hand-building a package, so the table cannot drift from what emit actually writes:

```python
def _emit(run: RunPaths) -> None:
    emitted, findings = emit_run(run)
    assert (emitted, findings) == ([SID], []), f"emit failed in the states table: {findings}"


def _smoke(run: RunPaths) -> None:
    write_json(run.report, minimal_report())
```

Add `from testgen.emit import emit_run` and `minimal_report` to the imports, append `("emit", _emit)` and `("smoke", _smoke)` to `STATES`, and extend `test_the_states_are_cumulative_so_the_last_one_is_a_complete_run` with:

```python
    assert (run.task_dir(SID) / "tests" / "expected.json").is_file()
    assert run.report.is_file()
```

- [ ] **Step 10: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS, after updating any existing test in `tests/unit/test_validate.py` that asserted `emit` or `smoke` validate trivially. Those assertions encoded the placeholder, and the placeholder is what this task removes — update them to the new contract rather than relaxing the gate.

- [ ] **Step 11: Verify the gate end to end by hand**

```bash
rm -rf /tmp/tg-p2 && mkdir -p /tmp/tg-p2
uv run testgen intake --input src/testgen/schema/manifest-0.1.json \
  --runs-dir /tmp/tg-p2 --target-name aap2 --target-interface mcp
RUN=$(ls -d /tmp/tg-p2/run-*)
uv run testgen validate --run "$RUN" --stage emit ; echo "emit gate exit=$?"
uv run testgen validate --run "$RUN" --stage smoke ; echo "smoke gate exit=$?"
uv run testgen check-refs --run "$RUN" ; echo "check-refs exit=$?"
rm -rf /tmp/tg-p2
```

Expected: both gates print a finding and exit 1 — a run with no suite and no report is not a success. `check-refs` exits 0, because layer 2 correctly tolerates a run that has only been through intake.

- [ ] **Step 12: Lint and commit**

```bash
make check
git add src/testgen tests
git commit -S -s -m "feat: Give emit and smoke real layer-1 gates

STAGE_ARTIFACTS mapped both to (), so validate --stage emit returned 0
unconditionally even when emit produced nothing -- and an orchestrator
reads 0 as success, then dispatches the next stage against an empty
suite. Defensible while neither stage existed; wrong now that one does.

The smoke report's schema lands before its producer, which is the right
order here: a stage whose output shape is undecided is a stage whose
consumers cannot be written. scored: false with no reward is the
schema-level form of the unscoreable-is-not-zero rule.

The states table now builds its emit state by running the real emitter,
so it cannot drift from what emit actually writes.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Self-Review

Indexed by **artifact × layer**, per the process change §8 of the spec asks for. A table keyed on "which task implements this requirement" made both of the contract spine's structural gaps invisible; this one makes an unchecked artifact obvious.

| Artifact | Layer 1 (schema) | Layer 2 (refs) | Consumed by |
|---|---|---|---|
| `manifest.json` | ✅ + `created_utc` pattern (T5) | ✅ **new** `check_manifest` (T1), `check_limits` (T2) | `check_limits` |
| `01-claims/<aid>.json` | ✅ | ✅ **new** filename/id/evidence chain, duplicate ids (T1) | `check_world_model` |
| `01-world-model.json` | ✅ + `binding` (T6) | ✅ existing | `emit` (T9) |
| `02-scenarios.json` | ✅ | ✅ + round/count caps (T2) | `emit` (T10) |
| `03-coverage/*.json` | ✅ | ✅ + holes↔matrices, goal rigour (T4) | — |
| `04-instances/<sid>/seed.json` | ✅ | ✅ existing | `emit` (T10) |
| `04-instances/<sid>/expected.json` | ✅ | ✅ + fact equality, capability scoping (T3) | `emit` (T9) |
| `05-verdicts/<sid>.json` | ✅ | ✅ existing | `emit` (T10) |
| `06-suite/<sid>/tests/expected.json` | ✅ **new** (T11) | ✅ **new** `check_suite` (T11) | `verify.py` (T7–8) |
| `06-suite/<sid>/` other seven files | n/a (not JSON) | ✅ **new** presence check (T11) | Harbor |
| `07-report.json` | ✅ **new** (T11) | none — Plan 3 adds one with its producer | Plan 3 |

**Spec coverage.** Nine of the ten items carried forward in §8 are covered: manifest chain (T1), `manifest.limits` (T2), `discriminating_fact` (T3), `capability_refs` scoping (T3), holes↔matrices (T4), `goal_matrix` rigour (T4), `\A…\Z` anchors (T5), `created_utc` (T5), emit/smoke gates (T11). The tenth — **re-verifying input digests** — is deliberately left to Plan 3, where `diff-runs` is its natural home, exactly as §8 states. From §7: `verify.py` (T7–8) and `bin/emit` (T9–10) are here; `smoke`, `compare-gold`, `diff-runs`, and `sample-for-review` are Plan 3.

**Type consistency.** `call_spec` and `_call_matches`/`call_matches` both use the key `tool`, not `name` — deliberately different from the sibling project's `name`, and consistent between `emit.py`, `verify.py`, and `suite-expected-0.1.json`. `CONTRACT` and `DEFAULT_WEIGHTS` are defined once in `verify.py` and imported by `emit.py`, so the contract string cannot drift. `bindings()` returns capability→binding; `to_contract` returns `(dict | None, list[tuple[str, str]])` and `emit_run` returns `(list[str], list[Finding])` — the pointer/message pairs become `Finding`s only at the boundary, in T10.

**Two things a reviewer should attack.**

1. **`discriminating_fact` exact equality (T3)** is the highest-risk decision in this plan. It is right in principle — a paraphrase is indistinguishable from a substitution — but it puts a verbatim-copy obligation on a language model, and if `tg-instantiate` cannot reliably meet it, this check burns the orchestrator's single repair attempt on well-behaved runs. It cannot be evaluated until Plan 4 exists. If it proves too brittle there, the fallback is to keep the field and compare it only when the oracle *changed* it in a way that weakens the seed — a much harder check, deferred on purpose.

2. **The plan supplies both the code and its tests**, so the tests cannot bound the code. Three of the contract spine's defects were exactly that. Each task's reviewer should be asked to **name one input class this task's tests do not reach** and to check that class by hand. Likely candidates: a seed whose collection is empty (T4's hop-depth derivation), an assertion whose `value` is a single character (T7's `_delimited`), and a run where two scenarios share a capability but only one is accepted (T10's selection).

