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

import os
import shutil
from pathlib import Path
from typing import Any

import tomli_w

from testgen.artifacts import ArtifactError, read_json, write_json
from testgen.findings import Finding
from testgen.paths import RunPaths
from testgen.suite.verify import CONTRACT, DEFAULT_WEIGHTS

_DATA_KINDS = ("answer_contains", "answer_excludes", "value_equals")
_TRAJECTORY_KINDS = ("tool_called", "tool_not_called")

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
        return [], [Finding(run.root, "emit", "", "no world model: emit needs 01-world-model.json")]
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
