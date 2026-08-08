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
import math
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from testgen.artifacts import ArtifactError, read_json, write_json
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

    **Every way this file can be unreadable is a UsageError too, not just a schema
    failure.** artifacts.read_json turns only FileNotFoundError into an
    ArtifactError, so --agents pointing at a directory, at a non-UTF-8 file, or at
    a file with mode 000 raised IsADirectoryError / UnicodeDecodeError /
    PermissionError straight out of here -- and cli.py's catch-all reported it as
    "an artifact in this run is malformed" at exit 1, sending the orchestrator to
    spend its one repair attempt rewriting stage artifacts that were fine. The
    catch is here rather than in read_json on purpose: an unreadable *stage*
    artifact really is a repairable stage defect and must stay a finding.
    """
    try:
        findings = validate_artifact(Path(path), "agents")
        if findings:
            raise UsageError(f"unusable agent roster:\n{format_findings(findings)}")
        roster = read_json(path)
    except (OSError, UnicodeDecodeError, ArtifactError) as exc:
        raise UsageError(f"unusable agent roster: {path}: {exc}") from exc
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

    **The restriction this imposes: command[0] must be runnable as written, before
    substitution.** `substitute` fills placeholders in every argv element, this
    one included, but it runs per (role, task) inside the agent loop -- long after
    the roster has to be accepted or refused. So a roster whose executable is
    `{task_dir}/run-agent` is refused here, and the placeholders are usable only
    in the arguments after it. That is the deliberate resolution of the two
    docstrings' apparent disagreement, and it is the cheaper side of the trade: a
    non-runnable executable is a misconfigured roster, which owes the operator an
    exit 2 before anything runs, and letting one through would surface it as
    subprocess.run's FileNotFoundError per task -- reported as a repairable stage
    finding at exit 1 about an artifact that is fine. agents-0.1.json's `command`
    description states the same restriction where a roster author will read it.
    """
    resolved = []
    for spec in specs:
        found = shutil.which(spec.command[0])
        if found is None:
            raise UsageError(
                f"agent role {spec.role!r} names an executable that is not runnable: "
                f"{spec.command[0]!r}. The executable must resolve as written, before "
                f"{{task_dir}}/{{logs_dir}}/{{scenario_id}} are substituted; use a placeholder "
                "only in the arguments after it"
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


# The three names verify.py writes into out_dir: reward.json and
# reward-detail.json for a human or this module to read, reward.txt as the
# bare float Harbor's test.sh reads. verify_package unlinks exactly these
# three before running, and nothing else in out_dir -- see its docstring.
#
# One definition per file, not one for the clear and another at each read.
# These names are the scoring seam: verify_package reads _REWARD_JSON for the
# score and _refusal_note reads _REWARD_DETAIL_JSON for the verifier's own
# stated reason, and a rename that reached the unlink tuple but missed a read
# would clear a file this module then went looking for under its old name.
_REWARD_JSON = "reward.json"
_REWARD_TXT = "reward.txt"
_REWARD_DETAIL_JSON = "reward-detail.json"
_VERIFIER_OUTPUTS = (_REWARD_JSON, _REWARD_TXT, _REWARD_DETAIL_JSON)


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


# The glob patterns verify.py::_read_logs concatenates out of the agent log
# directory. run_agent clears exactly these before launching the agent, so a
# previous attempt's transcript cannot be scored as this one's -- the same
# staleness verify_package clears on the output side of the scoring seam.
#
# Defined here and pinned against verify.py's behaviour by
# test_the_transcript_globs_are_exactly_what_the_verifier_reads: if the verifier
# ever reads a third pattern, the clear would miss it and that test fails.
# verify.py is stdlib-only and imports nothing from testgen, so it cannot import
# this constant; the test is what keeps the two ends of the seam honest.
_TRANSCRIPT_GLOBS = ("*.jsonl", "*.txt")

# The note run_agent returns when it could not clear the agent log directory,
# and the prefix smoke_run recognises that outcome by.
#
# run_agent's returncode is None both here and on a timeout, and the two are
# opposite situations: a timeout leaves a real partial transcript that can carry
# an earned score, while this leaves no transcript from this attempt at all. One
# definition, read by the producer and the consumer, rather than the same
# sentence written twice on either side of the branch that depends on it.
_LOGS_NOT_CLEARED = "could not clear the agent log directory"


def _never_launched(note: str) -> bool:
    """Whether `note` is run_agent reporting that it never launched the command."""
    return note.startswith(_LOGS_NOT_CLEARED)


def _clear_transcripts(logs_dir: Path) -> str:
    """Remove every file verify.py would read from `logs_dir`. -> a note, or "".

    A glob-scoped unlink over _TRANSCRIPT_GLOBS, never shutil.rmtree: logs_dir is
    caller-supplied, and an rmtree over a wrong path would erase the emitted
    package or the whole run rather than merely leaving stale transcripts behind.
    verify_package's own clear is scoped the same way for the same reason.

    Fails closed. An OSError -- including the IsADirectoryError from a
    *subdirectory* named `*.jsonl`, which _read_logs would itself raise on -- is
    returned as a note rather than swallowed or raised: a transcript we could not
    clear is exactly the transcript we must not score, and raising would cost
    every other role its data on every remaining task.
    """
    for pattern in _TRANSCRIPT_GLOBS:
        for stale in sorted(logs_dir.glob(pattern)):
            try:
                stale.unlink()
            except OSError as exc:
                return f"{_LOGS_NOT_CLEARED} {logs_dir}: {exc}"
    return ""


def _decode(output: str | bytes | None) -> str:
    """Normalise a subprocess's captured stream to str, treating None as empty.

    Exists for TimeoutExpired.stdout/.stderr specifically: subprocess.run's
    text=True decodes a *successful* communicate() return, but a timeout raises
    from inside communicate() with the raw bytes it had collected so far, before
    that decoding step runs -- so the partial output on a timeout is bytes even
    though the call asked for text. None means the process was killed before it
    produced anything at all -- a hung-from-the-start agent, most often.

    utf-8 is hardcoded rather than left to locale.getencoding(): the agent's
    stdout is stream-json by definition, which is UTF-8, so there is no
    encoding to detect. errors="replace" keeps a stream cut mid-character by
    the kill readable instead of raising on it.
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

    **logs_dir is cleared of transcripts first.** run.smoke_dir(role, sid) is
    deterministic per (role, task), and overwriting agent-stdout.jsonl does not
    remove the `session-1.jsonl` a previous attempt's runner wrote for itself --
    which verify.py would concatenate, and whose `result` event would win, because
    parse_transcript takes the last one and "agent-stdout.jsonl" sorts first. A
    correct answer from attempt 1 would then be scored as attempt 2's. If the
    clear fails, the command is **not launched** and the returncode is None with
    _LOGS_NOT_CLEARED as the note: a directory we could not clear is one whose
    contents must not be scored as this attempt's.

    **stderr goes outside logs_dir on purpose.** verify.py globs *.txt in the
    agent log directory, so a diagnostic written inside it would be read back as
    transcript input -- and a warning line that happened to quote the reference
    answer would satisfy an answer_contains assertion the agent never earned.
    That is a property of the seam, not a convention the tests happen to
    follow, so it is enforced here rather than left to every future caller
    (stage 7's smoke_run does not exist yet) to remember on its own.

    A timeout writes out whatever the command had already produced. A partial
    transcript still scores, and killing the whole smoke run because one agent
    hung would discard every other role's data on every remaining task, which is
    the comparison the run exists to make.
    """
    if logs_dir == stderr_path.parent or logs_dir in stderr_path.parents:
        raise ValueError(
            f"stderr_path {stderr_path} is inside the agent log directory {logs_dir}; "
            "verify.py would read it back as transcript"
        )
    logs_dir.mkdir(parents=True, exist_ok=True)
    not_cleared = _clear_transcripts(logs_dir)
    if not_cleared:
        return None, not_cleared
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
    (reward.txt is the platform's contract -- Harbor reads that bare float, not
    reward.json. This function reads reward.json, reward.txt's richer sibling
    that carries the same number as a JSON object; verify.py writes both
    together, so "no reward.txt" and "no reward.json" are the same event here.)

    The three files verify.py writes (reward.json, reward.txt,
    reward-detail.json) are unlinked from out_dir before the verifier runs. It
    is per-(role, task) and nothing else in this module gives it a fresh name
    per attempt, so a verifier that exits 0 without writing anything -- a
    mangled copy that does nothing being exactly the case this task exists to
    catch -- would otherwise leave a previous run's reward.json in place to be
    read back as this run's score. The returncode/is_file guard below already
    catches a nonzero exit over a stale file; the unlink closes the zero-exit
    case that guard cannot see.

    This removes exactly those three names and nothing else -- not
    shutil.rmtree(out_dir), which would also erase out_dir if a caller ever
    passed task_dir or the run root by mistake, silently destroying the
    package or the whole run rather than merely writing reward files somewhere
    odd. If any of the three cannot be removed, that failure is not swallowed:
    a stale reward.json we could not clear is exactly the file we must not
    read, so verify_package returns unscoreable rather than proceeding, and
    the note names the file. That failure must not propagate, the same
    reasoning as treating an agent timeout as a result rather than an
    exception: one unremovable file must not cost every remaining role its
    data on every remaining task.
    """
    verify_py = task_dir / "tests" / "verify.py"
    if not verify_py.is_file():
        return None, None, "package has no tests/verify.py"
    if out_dir == agent_logs:
        raise ValueError(
            f"out_dir {out_dir} must not be agent_logs; the verifier would read its own output"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in _VERIFIER_OUTPUTS:
        try:
            (out_dir / name).unlink(missing_ok=True)
        except OSError as exc:
            return None, None, f"could not clear stale {name} from a previous run: {exc}"
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

    reward_path = out_dir / _REWARD_JSON
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
    detail = out_dir / _REWARD_DETAIL_JSON
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

    **The isfinite call is redundant, kept for legibility rather than for
    coverage.** The range test rejects every non-finite value on its own: NaN
    makes `0.0 <= value <= 1.0` False because every comparison with NaN is False,
    and +/-inf falls outside the range. Deleting `math.isfinite` changes no
    result. It is written out because "not finite" is the reason a reader needs
    for NaN, and deriving that reason from the range test is a step nobody should
    have to take at the scoring seam.
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
    timed_out: list[tuple[int, int, str]] = []
    for sid in sids:
        task_dir = run.task_dir(sid)
        results = []
        for spec in specs:
            base = run.smoke_dir(spec.role, sid)
            agent_logs = base / "agent"
            agent_code, agent_note = run_agent(
                spec,
                task_dir=task_dir,
                logs_dir=agent_logs,
                stderr_path=base / "agent-stderr.txt",
                scenario_id=sid,
            )
            _, verified_reward, verify_note = verify_package(
                task_dir,
                agent_logs=agent_logs,
                out_dir=base / "verifier",
                stderr_path=base / "verifier-stderr.txt",
            )
            # Only a nonzero exit is treated as unscoreable here. A crash leaves
            # an empty transcript, and verify.py cannot tell that apart from "the
            # agent legitimately answered nothing" -- it scores an empty
            # transcript as a real, low (often all-zero) reward rather than
            # refusing -- so this is the one place left with the agent's own
            # exit status to make that distinction. A timeout (agent_code is
            # None) is different: run_agent writes out whatever the command had
            # already produced before it was killed, and that partial transcript
            # can carry a real, earned score. Discarding it here would not just
            # blank one cell -- comparable() requires every role to have scored,
            # so one discarded timeout would silently void the other two roles'
            # scores on the same task too.
            crashed = agent_code not in (0, None)  # nonzero exit only; None means timed out
            # The third outcome: run_agent could not clear the agent log
            # directory, so it never launched the command. verify.py has just
            # scored whatever that directory still held, which belongs to a
            # previous attempt -- unscoreable, for the same reason a crash is.
            never_ran = _never_launched(agent_note)
            discarded_because = (
                f"agent exited {agent_code}, not 0"
                if crashed
                else "the agent was never launched"
                if never_ran
                else ""
            )
            reward = None if discarded_because else verified_reward
            notes = [agent_note, verify_note]
            if discarded_because and verified_reward is not None:
                # verify.py cannot see the crash, so it scored the empty transcript
                # anyway and wrote a real reward.json next to it -- without this,
                # an operator reading the verifier's own output would find a score
                # the report says does not exist, with nothing on disk explaining
                # the mismatch.
                notes.append(
                    f"verifier's score ({verified_reward.get('reward')}) was discarded: "
                    f"{discarded_because}"
                )
            results.append(_result_entry(spec.role, reward, notes))
            if agent_code is None and not never_ran:
                timed_out.append((len(tasks), len(results) - 1, spec.role))
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
            {
                "role": spec.role,
                "model": spec.model,
                **({"notes": spec.notes} if spec.notes else {}),
            }
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
    for i, j, role in timed_out:
        if not tasks[i]["results"][j]["scored"]:
            # A timeout whose verifier produced no reward is already reported by
            # the unscoreable loop above, with the timeout in its note. Saying
            # "scored anyway on its partial transcript: the reward is real" at the
            # same pointer as a result carrying no reward at all is not a
            # duplicate, it is a false record -- and a recorded note must never be
            # false.
            continue
        findings.append(
            Finding(
                run.report,
                "smoke",
                f"/tasks/{i}/results/{j}",
                f"{role} timed out on {tasks[i]['scenario_id']} but scored anyway on its "
                "partial transcript: the reward is real, not padded, but may understate "
                f"{role} -- check whether the timeout budget is the actual constraint "
                "before reading this number as a capability result",
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
