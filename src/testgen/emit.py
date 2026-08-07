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
