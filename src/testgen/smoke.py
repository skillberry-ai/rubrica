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
import shutil
from dataclasses import dataclass
from pathlib import Path

from testgen.artifacts import read_json
from testgen.emit import AGENT_TIMEOUT_SEC
from testgen.errors import UsageError
from testgen.findings import format_findings
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
