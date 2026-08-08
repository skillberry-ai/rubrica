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
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from testgen.artifacts import read_json
from testgen.emit import AGENT_TIMEOUT_SEC, VERIFIER_TIMEOUT_SEC
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


def _decode(output: str | bytes | None) -> str:
    """Normalise a subprocess's captured stream to str, treating None as empty.

    Exists for TimeoutExpired.stdout/.stderr specifically: subprocess.run's
    text=True decodes a *successful* communicate() return, but a timeout raises
    from inside communicate() with the raw bytes it had collected so far, before
    that decoding step runs -- so the partial output on a timeout is bytes even
    though the call asked for text.
    """
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output


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
    argv = substitute(spec.command, task_dir=task_dir, logs_dir=logs_dir, scenario_id=scenario_id)
    stdout_path = logs_dir / "agent-stdout.jsonl"
    try:
        completed = subprocess.run(
            list(argv),
            cwd=task_dir,
            capture_output=True,
            text=True,
            timeout=spec.timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        # CPython quirk, not a text=True bug in this code: on a timeout with
        # partial output, TimeoutExpired.stdout/.stderr carry raw bytes even
        # though text=True was passed -- the newline/encoding translation that
        # normally runs happens only on communicate()'s *successful* return, a
        # path a timeout never reaches. Decode defensively rather than let a
        # hung agent's partial transcript raise TypeError instead of scoring.
        stdout_path.write_text(_decode(exc.stdout), encoding="utf-8")
        stderr_path.write_text(_decode(exc.stderr), encoding="utf-8")
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
        completed = subprocess.run(
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
