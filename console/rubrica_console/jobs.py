"""Running steps: subprocesses, logs, status, the dispatch cap, and the ledger.

Everything that changes a run goes through a subprocess -- the `rubrica` CLI for
code stages, gates and records, `scripts/dispatch-stage.sh` for prompt stages --
so this module never writes a run artifact itself and every write keeps the
checks its own command already has. What it does write is its own bookkeeping,
under `<lab>/console/<run name>/`, outside the run: job records, logs, findings
files for a repair, and the ledger `pipeline.Ledger` reads.

Rules carried over from `rb-orchestrate`, each enforced here rather than hoped for:

- At most `max_parallel` model dispatches at once, across every run this server
  drives (B3/B6: the shared gateway degrades past three).
- One job at a time per run: a seal starting while a fan-out is still writing
  parts would assemble a document from half of them.
- Exit 1 from a gate is findings: the step fails, its findings are kept verbatim
  in a file, and one repair is offered. Exit 2 is a halt with no repair.
- A finding a human accepted stays accepted: later gates that print the same line
  do not fail on it again, and it still shows in the log, prefixed `[accepted]`.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from rubrica import skills
from rubrica.paths import RunPaths
from rubrica_console import credentials as credentials_mod
from rubrica_console import dispatch, pipeline

CLEAN, FINDINGS, USAGE = 0, 1, 2
# How many dispatches of one fan-out must all fail, spending nothing, before the
# rest are cancelled. Three is the dispatch cap: one full wave.
_FAIL_FAST_AFTER = 3

QUEUED, RUNNING, SUCCEEDED, FAILED, HALTED, CANCELLED, INTERRUPTED = (
    "queued",
    "running",
    "succeeded",
    "findings",
    "halted",
    "cancelled",
    "interrupted",
)
_ACTIVE = (QUEUED, RUNNING)


class ConsoleError(Exception):
    """A request the console refuses: shown to the human, never a crash."""


class _Stop(Exception):
    """Internal: a recipe op ended the job (findings, halt, or cancel)."""

    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class Member:
    id: str
    status: str = QUEUED
    log: str = ""
    cost: float | None = None
    turns: int = 0
    last: str = ""
    exit: int | None = None
    error: str = ""


@dataclass
class Entry:
    label: str
    status: str = RUNNING
    exit: int | None = None
    log: str = ""


@dataclass
class Job:
    id: str
    run: str
    step: str
    title: str
    kind: str
    status: str = QUEUED
    created: float = field(default_factory=time.time)
    started: float | None = None
    ended: float | None = None
    model: str = ""
    effort: str = ""
    repair: bool = False
    chain: bool = False
    message: str = ""
    entries: list[Entry] = field(default_factory=list)
    members: dict[str, Member] = field(default_factory=dict)
    findings_file: str = ""

    @property
    def cost(self) -> float:
        return round(sum(m.cost or 0.0 for m in self.members.values()), 4)

    def as_dict(self) -> dict:
        data = asdict(self)
        data["cost"] = self.cost
        # The open findings themselves, so the page shows them without a log
        # click. Capped: a check-refs run can print thousands of lines.
        data["findings"] = []
        if self.findings_file:
            try:
                lines = Path(self.findings_file).read_text(encoding="utf-8").splitlines()
            except OSError:
                lines = []
            data["findings"] = lines[:200]
            data["findings_total"] = len(lines)
        data["members"] = list(data["members"].values())
        return data

    @classmethod
    def from_dict(cls, data: dict) -> Job:
        data = dict(data)
        for key in ("cost", "findings", "findings_total"):
            data.pop(key, None)
        entries = [Entry(**e) for e in data.pop("entries", [])]
        members = {m["id"]: Member(**m) for m in data.pop("members", [])}
        return cls(**data, entries=entries, members=members)


@dataclass
class Options:
    model: str
    effort: str
    budget: str | None = None
    agents: str | None = None


class _RunState:
    """The ledger and job records of one run, persisted under the lab directory."""

    def __init__(self, home: Path):
        self.home = home
        self.jobs_dir = home / "jobs"
        self.logs_dir = home / "logs"
        self.ledger_path = home / "ledger.json"
        for d in (self.jobs_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.data = {
            "reseeded": [],
            "failed": {},
            "accepted": [],
            "accepted_findings": [],
            "attempts": {},
            "used": {},
        }
        try:
            loaded = json.loads(self.ledger_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self.data.update({k: v for k, v in loaded.items() if k in self.data})
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        # Callers hold Console._lock, so one writer at a time.
        tmp = self.ledger_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.ledger_path)

    def ledger(self) -> pipeline.Ledger:
        return pipeline.Ledger(
            reseeded=set(self.data["reseeded"]),
            failed=set(self.data["failed"]),
            accepted=set(self.data["accepted"]),
        )


class Console:
    def __init__(
        self,
        runs_dir: Path,
        lab: Path,
        *,
        dispatch_script: Path | None = None,
        max_parallel: int = 3,
        model: str = "sonnet",
        effort: str = "medium",
        rubrica_argv: list[str] | None = None,
        credentials: credentials_mod.Store | None = None,
    ):
        self.runs_dir = runs_dir.resolve()
        self.credentials = credentials or credentials_mod.Store()
        self.lab = lab.resolve()
        self.lab.mkdir(parents=True, exist_ok=True)
        self.dispatch_script = (dispatch_script or dispatch.default_script()).resolve()
        self.max_parallel = max_parallel
        self.defaults = Options(model=model, effort=effort)
        self.rubrica_argv = rubrica_argv or [sys.executable, "-m", "rubrica.cli"]
        self.bash = dispatch.find_bash()
        self._sem = threading.BoundedSemaphore(max_parallel)
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}
        self._procs: dict[str, set[subprocess.Popen]] = {}
        self._cancel: set[str] = set()
        self._failfast: dict[str, str] = {}
        self._states: dict[str, _RunState] = {}
        self._skills_checked = False
        self._load_jobs()

    # -- runs ----------------------------------------------------------------

    def run_paths(self, name: str) -> RunPaths:
        if not name or "/" in name or name.startswith("."):
            raise ConsoleError(f"not a run name: {name!r}")
        root = self.runs_dir / name
        if not root.is_dir():
            raise ConsoleError(f"no run named {name} in {self.runs_dir}")
        return RunPaths(root)

    def list_runs(self) -> list[str]:
        try:
            children = sorted(self.runs_dir.iterdir(), reverse=True)
        except OSError:
            return []
        return [
            p.name
            for p in children
            if p.is_dir() and ((p / "manifest.json").exists() or (p / "00-catalogue.json").exists())
        ]

    def _state(self, name: str) -> _RunState:
        with self._lock:
            if name not in self._states:
                self._states[name] = _RunState(self.lab / "console" / name)
            return self._states[name]

    def steps(self, name: str) -> list[pipeline.Step]:
        run = self.run_paths(name)
        with self._lock:
            ledger = self._state(name).ledger()
        all_steps = pipeline.steps(run, ledger)
        active = self.active_job(name)
        if active is not None:
            for step in all_steps:
                if step.id == active.step:
                    step.status = "running"
        if not self.prompt_ready():
            for step in all_steps:
                if step.calls_model and step.status == pipeline.READY:
                    step.reason = self.prompt_unavailable_reason()
        return all_steps

    def _creds(self) -> credentials_mod.Credentials:
        try:
            return self.credentials.load()
        except credentials_mod.CredentialError:
            return credentials_mod.Credentials()

    def prompt_ready(self) -> bool:
        return self.dispatch_script.is_file() and self.bash is not None and self._creds().configured

    def prompt_unavailable_reason(self) -> str:
        if not self.dispatch_script.is_file():
            return f"Needs a repository checkout: {self.dispatch_script} does not exist"
        if self.bash is None:
            return "Needs bash 4 or newer (macOS: brew install bash)"
        return "Set up model access in Settings first: the console uses its own credentials"

    def ledger_view(self, name: str) -> dict:
        with self._lock:
            data = json.loads(json.dumps(self._state(name).data))
        return data

    # -- jobs ----------------------------------------------------------------

    def _load_jobs(self) -> None:
        for path in sorted((self.lab / "console").glob("*/jobs/*.json")):
            try:
                job = Job.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError):
                continue
            if job.status in _ACTIVE:
                # The server that ran it is gone. The disk state is what a resume
                # reads, so marking it is all that is needed.
                job.status = INTERRUPTED
                job.message = "the console stopped while this job was running"
                job.ended = job.ended or time.time()
                for member in job.members.values():
                    if member.status in _ACTIVE:
                        member.status = INTERRUPTED
            self._jobs[job.id] = job
            self._persist(job)

    def _persist(self, job: Job) -> None:
        # Under the lock: fan-out members finish on their own threads, and two of
        # them saving one record at once raced on the shared temp file (measured:
        # FileNotFoundError on the second replace), besides serialising a members
        # dict another thread was still adding to.
        state = self._state(job.run)
        path = state.jobs_dir / f"{job.id}.json"
        with self._lock:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(job.as_dict(), indent=2), encoding="utf-8")
            tmp.replace(path)

    def jobs(self, name: str | None = None) -> list[Job]:
        with self._lock:
            out = [j for j in self._jobs.values() if name is None or j.run == name]
        return sorted(out, key=lambda j: j.created, reverse=True)

    def job(self, job_id: str) -> Job:
        with self._lock:
            if job_id not in self._jobs:
                raise ConsoleError(f"no job {job_id}")
            return self._jobs[job_id]

    def active_job(self, name: str) -> Job | None:
        with self._lock:
            return next(
                (j for j in self._jobs.values() if j.run == name and j.status in _ACTIVE),
                None,
            )

    def run_cost(self, name: str) -> float:
        return round(sum(j.cost for j in self.jobs(name)), 4)

    def cancel(self, job_id: str) -> Job:
        job = self.job(job_id)
        with self._lock:
            self._cancel.add(job_id)
            procs = list(self._procs.get(job_id, ()))
        for proc in procs:
            # Already gone is fine: the job is ending either way.
            with contextlib.suppress(OSError):
                os.killpg(proc.pid, signal.SIGTERM)
        return job

    def shutdown(self) -> None:
        for job in self.jobs():
            if job.status in _ACTIVE:
                self.cancel(job.id)

    def wait(self, job_id: str, timeout: float = 60.0) -> Job:
        """Block until a job ends. For tests and for the chain runner."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = self.job(job_id)
            if job.status not in _ACTIVE:
                return job
            time.sleep(0.02)
        raise TimeoutError(job_id)

    # -- starting work -------------------------------------------------------

    def _new_job(self, name: str, step: pipeline.Step, opts: Options, **extra) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:12],
            run=name,
            step=step.id,
            title=step.title,
            kind=step.kind,
            model=opts.model,
            effort=opts.effort,
            **extra,
        )
        with self._lock:
            if self.active_job(name) is not None:
                raise ConsoleError("this run already has a job running; wait or cancel it")
            self._jobs[job.id] = job
        self._persist(job)
        return job

    def run_step(self, name: str, step_id: str, opts: Options, *, repair: bool = False) -> Job:
        all_steps = self.steps(name)
        step = pipeline.find(all_steps, step_id)
        if step is None:
            raise ConsoleError(f"no step {step_id} in this run")
        self._check_runnable(name, step, opts, repair=repair)
        job = self._new_job(name, step, opts, repair=repair)
        threading.Thread(
            target=self._execute, args=(job, step, opts), daemon=True, name=f"job-{job.id}"
        ).start()
        return job

    def _check_runnable(self, name: str, step: pipeline.Step, opts: Options, *, repair: bool):
        if self.active_job(name) is not None:
            raise ConsoleError("this run already has a job running; wait or cancel it")
        if step.kind == pipeline.GATE:
            raise ConsoleError("a gate is held by a human: use Approve, with a note")
        if step.status not in (pipeline.READY, pipeline.FAILED, pipeline.DONE):
            raise ConsoleError(f"{step.title} is not ready: an earlier step is not done")
        if step.calls_model and not self.prompt_ready():
            raise ConsoleError(self.prompt_unavailable_reason())
        if step.id == "smoke" and not opts.agents:
            raise ConsoleError("smoke needs an agents roster file; the console never invents one")
        state = self._state(name)
        if repair:
            if step.id not in state.data["failed"]:
                raise ConsoleError("there is nothing to repair: the step has no open findings")
            if not step.calls_model:
                raise ConsoleError(
                    "a code step's findings name an upstream artifact; repair that stage, "
                    "or accept the findings"
                )
            if state.data["attempts"].get(step.id, 0) >= 2:
                raise ConsoleError(
                    "this step already failed its repair; rb-orchestrate would halt here. "
                    "Accept the findings, or run it again from scratch"
                )

    def run_to_gate(self, name: str, opts: Options) -> Job:
        """Chain steps until a gate, a failure, or the end of the pipeline."""
        all_steps = self.steps(name)
        first = pipeline.next_step(all_steps)
        if first is None:
            raise ConsoleError("every step of this run is done")
        if first.kind == pipeline.GATE:
            raise ConsoleError(f"{first.title} is waiting for you")
        if first.status == pipeline.FAILED:
            raise ConsoleError(f"{first.title} has open findings: repair or accept them first")
        self._check_runnable(name, first, opts, repair=False)
        chain = pipeline.Step("chain", "Run to next gate", pipeline.FOLLOWUP)
        job = self._new_job(name, chain, opts, chain=True)
        threading.Thread(
            target=self._execute_chain, args=(job, opts), daemon=True, name=f"chain-{job.id}"
        ).start()
        return job

    def preview_to_gate(self, name: str) -> list[pipeline.Step]:
        """The steps a chain would run, as far as can be known before running them.

        A round's later steps depend on what the round before it produced, so the
        preview stops where the disk stops knowing; it never under-states the
        first dispatches the human is about to pay for.
        """
        out = []
        started = False
        for step in self.steps(name):
            if step.status in (pipeline.READY, pipeline.FAILED):
                started = True
            if not started or step.status == pipeline.DONE:
                continue
            if step.kind == pipeline.GATE:
                break
            out.append(step)
        return out

    # -- execution -----------------------------------------------------------

    def _execute_chain(self, job: Job, opts: Options) -> None:
        job.status, job.started = RUNNING, time.time()
        self._persist(job)
        try:
            ran = 0
            while True:
                if job.id in self._cancel:
                    raise _Stop(CANCELLED, "cancelled")
                all_steps = pipeline.steps(self.run_paths(job.run), self._state(job.run).ledger())
                step = pipeline.next_step(all_steps)
                if step is None:
                    job.message = f"ran {ran} step(s); the pipeline is complete"
                    break
                if step.kind == pipeline.GATE:
                    job.message = f"ran {ran} step(s); stopped at {step.title}"
                    break
                if step.status == pipeline.FAILED:
                    raise _Stop(FAILED, f"stopped: {step.title} has open findings")
                if step.id == "smoke" and not opts.agents:
                    job.message = f"ran {ran} step(s); smoke needs an agents roster file"
                    break
                marker = Entry(f"step: {step.title}", status=RUNNING)
                job.entries.append(marker)
                self._persist(job)
                status = self._run_recipe(job, step, opts)
                # The marker, not entries[-1]: the recipe appended its own entries.
                marker.status = status
                if status != SUCCEEDED:
                    raise _Stop(status, f"stopped: {step.title} ended {status}")
                ran += 1
            job.status = SUCCEEDED
        except _Stop as stop:
            job.status, job.message = stop.status, stop.message
        except Exception as exc:  # a console bug must not leave a job "running"
            job.status, job.message = HALTED, f"console error: {type(exc).__name__}: {exc}"
        finally:
            job.ended = time.time()
            with self._lock:
                self._cancel.discard(job.id)
            self._persist(job)

    def _execute(self, job: Job, step: pipeline.Step, opts: Options) -> None:
        job.status, job.started = RUNNING, time.time()
        self._persist(job)
        try:
            job.status = self._run_recipe(job, step, opts, repair=job.repair)
        except Exception as exc:
            job.status, job.message = HALTED, f"console error: {type(exc).__name__}: {exc}"
        finally:
            job.ended = time.time()
            with self._lock:
                self._cancel.discard(job.id)
            self._persist(job)

    def _run_recipe(
        self, job: Job, step: pipeline.Step, opts: Options, *, repair: bool = False
    ) -> str:
        """Run one step's recipe; return the job status it ends in."""
        state = self._state(job.run)
        run = self.run_paths(job.run)
        with self._lock:
            attempts = state.data["attempts"]
            attempts[step.id] = attempts.get(step.id, 0) + 1 if repair else 1
            findings_from = state.data["failed"].get(step.id) if repair else None
            state.save()
        try:
            if step.calls_model:
                self._preflight(job)
            for op in step.recipe:
                if job.id in self._cancel:
                    raise _Stop(CANCELLED, "cancelled")
                self._op(job, run, step, op, opts, findings_from)
        except _Stop as stop:
            job.message = stop.message
            if stop.status == FAILED:
                with self._lock:
                    state.data["failed"][step.id] = job.findings_file
                    if state.data["attempts"].get(step.id, 0) >= 2:
                        stop = _Stop(HALTED, stop.message + " (after its one repair)")
                    state.save()
                job.message = stop.message
            return stop.status
        with self._lock:
            state.data["failed"].pop(step.id, None)
            if step.stage:
                state.data["used"][step.stage] = {"model": opts.model, "effort": opts.effort}
            state.save()
        return SUCCEEDED

    def _preflight(self, job: Job) -> None:
        """B0, once per server: a broken skill contract halts before any dispatch."""
        if self._skills_checked:
            return
        code, out = self._cli(job, ["check-skills"], "check-skills")
        if code != CLEAN:
            raise _Stop(HALTED, "check-skills reported problems; no stage can be dispatched")
        self._skills_checked = True

    # -- ops -----------------------------------------------------------------

    def _op(self, job, run, step, op, opts, findings_from) -> None:
        kind = op["op"]
        rid = ["--run", str(run.root)]
        if kind == "dispatch":
            findings = Path(findings_from) if findings_from else None
            self._dispatch_members(job, run, op["stage"], [None], opts, findings=findings)
        elif kind == "fanout":
            ids = op["ids"]
            per_member: dict[str, Path] = {}
            if findings_from:
                ids, per_member = self._split_findings(job, Path(findings_from), step)
            self._dispatch_members(job, run, op["stage"], ids, opts, per_member=per_member)
        elif kind == "cli":
            self._gate(job, [*op["args"], *rid], op["args"][0])
        elif kind == "validate":
            self._gate(job, ["validate", "--stage", op["stage"], *rid], f"validate {op['stage']}")
        elif kind == "check-refs":
            self._gate(job, ["check-refs", *rid], "check-refs")
        elif kind == "record":
            skill = skills.skills_dir() / f"rb-{op['stage']}" / "SKILL.md"
            self._gate(
                job,
                [
                    "record-stage",
                    *rid,
                    "--stage",
                    op["stage"],
                    "--model",
                    opts.model,
                    "--effort",
                    opts.effort,
                    "--skill",
                    str(skill),
                ],
                f"record-stage {op['stage']}",
            )
        elif kind == "synthesise-interfaces":
            out = self._gate(job, ["synthesise-interfaces", *rid], "synthesise-interfaces")
            # B3: nothing printed means no service was declared; validating would
            # accuse a stage that behaved correctly.
            if out.strip():
                self._gate(
                    job,
                    ["validate", "--stage", "synthesise-interfaces", *rid],
                    "validate synthesise-interfaces",
                )
            else:
                self._decide(
                    job,
                    run,
                    "synthesise-interfaces: no service declared, nothing to derive (console)",
                )
            self._gate(job, ["check-refs", *rid], "check-refs")
        elif kind == "propose-batches":
            r = str(op["round"])
            out = self._gate(job, ["propose-batches", *rid, "--round", r], f"propose-batches {r}")
            if out.strip().startswith("no closable holes"):
                # B6.1: no round to run. Not validated -- that would accuse a stage
                # that behaved correctly -- and recorded, which ends the loop.
                self._decide(job, run, f"round {r}: no closable holes; the loop ends (console)")
            else:
                self._gate(
                    job,
                    ["validate", "--stage", "propose-batches", *rid],
                    "validate propose-batches",
                )
        elif kind == "score-seal":
            r = str(op["round"])
            self._gate(job, ["score-seal", *rid, "--round", r], f"score-seal {r}")
            self._gate(job, ["validate", "--stage", "score-seal", *rid], "validate score-seal")
            self._gate(job, ["check-refs", *rid], "check-refs")
            verdict = pipeline._verdict_of(run, int(r)) or "unreadable"
            # B6.7: recorded before anything branches on it.
            self._decide(job, run, f"round {r}: {verdict} (console)")
        elif kind == "followup":
            self._followup(job, run, op, opts)
        elif kind == "smoke":
            self._gate(
                job, ["smoke", *rid, "--agents", str(opts.agents)], "smoke", repairable=False
            )
        else:
            raise _Stop(HALTED, f"unknown recipe op {kind!r}")

    def _followup(self, job, run, op, opts) -> None:
        """B9: re-seed once (re-instantiate, then re-challenge); rejects via score."""
        rid = ["--run", str(run.root)]
        reseed = list(op.get("reseed") or [])
        if reseed:
            self._dispatch_members(job, run, "instantiate", reseed, opts, reseed=True)
            with self._lock:
                state = self._state(job.run)
                state.data["reseeded"] = sorted(set(state.data["reseeded"]) | set(reseed))
                state.save()
            self._dispatch_members(job, run, "challenge", reseed, opts)
            self._gate(job, ["validate", "--stage", "challenge", *rid], "validate challenge")
        # Recomputed after the re-seeds: a second `re-seed` is now a rejection.
        steps_now = pipeline.steps(run, self._state(job.run).ledger())
        follow = pipeline.find(steps_now, "followup")
        reject = list(follow.recipe[0].get("reject") or []) if follow else []
        if reject:
            r = str(op.get("round") or 1)
            self._dispatch_members(job, run, "score", [None], opts, reject=reject)
            self._gate(job, ["validate", "--stage", "score", *rid], "validate score")
            self._gate(job, ["propose-seal", *rid], "propose-seal")
            self._gate(job, ["validate", "--stage", "propose-seal", *rid], "validate propose-seal")
            self._gate(job, ["score-seal", *rid, "--round", r], f"score-seal {r}")
            self._gate(job, ["validate", "--stage", "score-seal", *rid], "validate score-seal")
        self._gate(job, ["check-refs", *rid], "check-refs")

    def _split_findings(self, job, findings: Path, step) -> tuple[list[str], dict[str, Path]]:
        """A fan-out repair goes to the members its findings name, each with its own lines.

        A member is named by a finding line that contains its id. Lines that name no
        member cannot be routed to one, and the repair says so rather than guessing.
        """
        try:
            lines = findings.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise _Stop(HALTED, f"cannot read the findings to repair from: {exc}") from exc
        members = step.members_done + step.members_todo
        # Longest first, so an id that is a prefix of another (orphan / orphan2)
        # does not claim its sibling's lines.
        ordered = sorted(members, key=len, reverse=True)
        routed: dict[str, list[str]] = {}
        for line in lines:
            owner = next((m for m in ordered if m in line), None)
            if owner:
                routed.setdefault(owner, []).append(line)
        if not routed:
            raise _Stop(
                FAILED,
                "the findings name no member of this fan-out, so no member can be "
                "repaired with them; accept them or fix the upstream artifact",
            )
        out: dict[str, Path] = {}
        repair_dir = self._state(job.run).home / "repair" / job.id
        repair_dir.mkdir(parents=True, exist_ok=True)
        for member, member_lines in routed.items():
            path = repair_dir / f"{member}.txt"
            path.write_text("\n".join(member_lines) + "\n", encoding="utf-8")
            out[member] = path
        return sorted(out), out

    def _decide(self, job, run, note: str) -> None:
        self._gate(job, ["decide", "--run", str(run.root), "--note", note], "decide")

    def _cli(self, job: Job, args: list[str], label: str) -> tuple[int, str]:
        state = self._state(job.run)
        log = state.logs_dir / job.id / f"{len(job.entries):03d}-{label.replace(' ', '_')}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        entry = Entry(label, log=str(log))
        job.entries.append(entry)
        self._persist(job)
        proc = subprocess.Popen(
            [*self.rubrica_argv, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        self._track(job, proc)
        try:
            out, err = proc.communicate()
        finally:
            self._untrack(job, proc)
        log.write_text(f"$ rubrica {' '.join(args)}\n{out}{err}", encoding="utf-8")
        entry.exit = proc.returncode
        # A default _gate refines; a bare _cli caller (the check-skills preflight)
        # would otherwise leave the entry reading "running" forever.
        entry.status = {CLEAN: SUCCEEDED, FINDINGS: FAILED}.get(proc.returncode, HALTED)
        return proc.returncode, out

    def _gate(self, job: Job, args: list[str], label: str, *, repairable: bool = True) -> str:
        """Run one CLI command; turn its exit code into continue / findings / halt."""
        code, out = self._cli(job, args, label)
        entry = job.entries[-1]
        if job.id in self._cancel:
            entry.status = CANCELLED
            raise _Stop(CANCELLED, "cancelled")
        if code == CLEAN:
            entry.status = SUCCEEDED
            self._persist(job)
            return out
        if code == FINDINGS:
            lines = [ln for ln in out.splitlines() if ln.strip()]
            accepted = set(self._state(job.run).data["accepted_findings"])
            open_lines = [
                ln for ln in lines if ln not in accepted and not ln.startswith("[waived] ")
            ]
            if not open_lines:
                # Every finding is one a human already accepted (or waived): the gate
                # is as clean as the human ruled it, and the log still shows them.
                entry.status = SUCCEEDED
                self._persist(job)
                return out
            findings = Path(entry.log).with_suffix(".findings.txt")
            findings.write_text("\n".join(open_lines) + "\n", encoding="utf-8")
            job.findings_file = str(findings)
            entry.status = FAILED
            self._persist(job)
            tail = "" if repairable else " (a report, not repairable by re-dispatch)"
            raise _Stop(FAILED, f"{label} reported {len(open_lines)} finding(s){tail}")
        entry.status = HALTED
        self._persist(job)
        raise _Stop(
            HALTED,
            f"{label} exited {code}: the run or harness needs a human, "
            "and a re-dispatch cannot help",
        )

    def _dispatch_members(
        self,
        job: Job,
        run: RunPaths,
        stage: str,
        ids: list[str | None],
        opts: Options,
        *,
        findings: Path | None = None,
        per_member: dict[str, Path] | None = None,
        reseed: bool = False,
        reject: list[str] | None = None,
    ) -> None:
        if not ids:
            return
        state = self._state(job.run)
        # Read once per fan-out, so a fan-out's members all use one set; a change in
        # Settings applies from the next step.
        creds_env = self._creds().env()
        threads = []
        for member_id in ids:
            key = f"{stage}:{member_id}" if member_id else stage
            log = state.logs_dir / job.id / f"{key.replace(':', '-')}.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            member = Member(id=key, log=str(log))
            with self._lock:
                job.members[key] = member
            env = dispatch.env_for(
                credentials=creds_env,
                lab=self.lab,
                model=opts.model,
                effort=opts.effort,
                budget=opts.budget,
                findings_file=(per_member or {}).get(member_id) or findings,
                reseed=reseed,
                reject=reject,
            )
            argv = [self.bash or "bash", str(self.dispatch_script), stage, str(run.root)]
            if member_id:
                argv.append(member_id)
            t = threading.Thread(target=self._member, args=(job, member, argv, env), daemon=True)
            threads.append(t)
        self._persist(job)
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if job.id in self._failfast:
            raise _Stop(HALTED, self._failfast.pop(job.id))
        if job.id in self._cancel:
            raise _Stop(CANCELLED, "cancelled")
        failed = [m for m in job.members.values() if m.id.startswith(stage) and m.status == HALTED]
        if any(m.exit == USAGE for m in failed):
            raise _Stop(HALTED, f"{stage}: the dispatch script refused (exit 2); see its log")
        if failed:
            # A member that did not finish leaves its slice missing; the gates below
            # will name it, and running the step again resumes only the missing ones.
            job.message = f"{len(failed)} {stage} dispatch(es) did not finish"
        self._persist(job)

    def _member(self, job: Job, member: Member, argv: list[str], env: dict) -> None:
        with self._sem:
            if job.id in self._cancel:
                member.status = CANCELLED
                return
            member.status = RUNNING
            self._persist(job)
            with open(member.log, "w", encoding="utf-8") as fh:
                proc = subprocess.Popen(
                    argv,
                    stdout=fh,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    cwd=str(dispatch.repo_root()),
                    env=env,
                    start_new_session=True,
                )
                self._track(job, proc)
                try:
                    while proc.poll() is None:
                        self._refresh(member)
                        time.sleep(0.5)
                finally:
                    self._untrack(job, proc)
            member.exit = proc.returncode
            self._refresh(member)
            if job.id in self._cancel:
                member.status = CANCELLED
            else:
                member.status = SUCCEEDED if proc.returncode == 0 else HALTED
            self._persist(job)
            self._maybe_fail_fast(job)

    def _maybe_fail_fast(self, job: Job) -> None:
        """Stop a fan-out whose first dispatches all failed without spending anything.

        Measured: with the gateway refusing every call, a 114-member extract ran 102
        failures at three minutes of retries each before the job ended. Failures
        that cost nothing are failures to *reach* the model -- credentials, gateway,
        model id -- and every remaining member would fail the same way. A member
        that spent money and then failed is a different case and does not count.
        """
        with self._lock:
            if job.id in self._cancel:
                return
            ended = [m for m in job.members.values() if m.status in (SUCCEEDED, HALTED)]
            if len(ended) < _FAIL_FAST_AFTER or any(m.status == SUCCEEDED for m in ended):
                return
            if any((m.cost or 0) > 0 for m in ended):
                return
            reason = next((m.error for m in ended if m.error), "") or "see a member's log"
            self._failfast[job.id] = (
                f"stopped after the first {len(ended)} dispatches all failed before reaching "
                f"the model: {reason}"
            )
        self.cancel(job.id)

    def _refresh(self, member: Member) -> None:
        progress = dispatch.read_progress(Path(member.log))
        member.turns, member.last = progress.turns, progress.last
        if progress.error:
            member.error = progress.error
        if progress.cost is not None:
            member.cost = progress.cost

    def _track(self, job: Job, proc: subprocess.Popen) -> None:
        with self._lock:
            self._procs.setdefault(job.id, set()).add(proc)

    def _untrack(self, job: Job, proc: subprocess.Popen) -> None:
        with self._lock:
            self._procs.get(job.id, set()).discard(proc)

    # -- human actions -------------------------------------------------------

    def _human_job(self, name: str, title: str) -> Job:
        step = pipeline.Step("human", title, pipeline.GATE)
        job = self._new_job(name, step, self.defaults)
        job.status, job.started = RUNNING, time.time()
        return job

    def _finish(self, job: Job, status: str, message: str = "") -> Job:
        job.status, job.message, job.ended = status, message, time.time()
        self._persist(job)
        return job

    def _human(self, name: str, title: str, commands: list[list[str]]) -> Job:
        """Run a human's action synchronously: a few quick CLI calls, no model."""
        job = self._human_job(name, title)
        try:
            for args in commands:
                self._gate(job, args, args[0], repairable=False)
        except _Stop as stop:
            return self._finish(job, stop.status, stop.message)
        return self._finish(job, SUCCEEDED, title)

    @staticmethod
    def _note(note: str) -> str:
        text = " ".join((note or "").split())
        if not text:
            raise ConsoleError("a note is required: it is what decisions.md records")
        return text

    def approve_gate(self, name: str, gate: int, note: str) -> Job:
        text = self._note(note)
        all_steps = self.steps(name)
        step = pipeline.find(all_steps, f"gate-{gate}")
        if step is None:
            raise ConsoleError(f"this run has no gate {gate}")
        if step.status != pipeline.READY:
            raise ConsoleError(f"gate {gate} is not the next thing to do in this run")
        run = self.run_paths(name)
        rid = ["--run", str(run.root)]
        commands: list[list[str]] = []
        if gate == 0:
            # Gate 0's approval is what admits the inputs: intake reads the sealed
            # triage record and mints the manifest. Then the triage passes, which
            # could not be recorded before a manifest existed, are recorded.
            commands.append(["intake", *rid])
            used = self._state(name).data["used"]
            for stage in ("triage-objective", "triage-rule", "triage-audit"):
                if stage in used:
                    skill = skills.skills_dir() / f"rb-{stage}" / "SKILL.md"
                    commands.append(
                        [
                            "record-stage",
                            *rid,
                            "--stage",
                            stage,
                            "--model",
                            used[stage]["model"],
                            "--effort",
                            used[stage]["effort"],
                            "--skill",
                            str(skill),
                        ]
                    )
        commands.append(["decide", *rid, "--note", f"human gate {gate} (console): {text}"])
        return self._human(name, f"Approve gate {gate}", commands)

    def gate_feedback(self, name: str, gate: int, note: str) -> Job:
        """Record a human's comments on a gate without approving it.

        Worded so `pipeline._GATE_LINE` cannot read it as the approval: that
        pattern wants `gate N` straight after the timestamp, and this line starts
        with `console:`. No stage reads decisions.md, so this reaches the record
        and the next human, never a dispatch -- the one channel between stages is
        an artifact, and a reviewer's prose is not one.
        """
        text = self._note(note)
        if gate not in (0, 1, 2, 3):
            raise ConsoleError("a gate is 0, 1, 2 or 3")
        run = self.run_paths(name)
        return self._human(
            name,
            f"Feedback on gate {gate}",
            [
                [
                    "decide",
                    "--run",
                    str(run.root),
                    "--note",
                    f"console: feedback on gate {gate}, not approved: {text}",
                ]
            ],
        )

    def gate_history(self, name: str, gate: int) -> list[str]:
        """Every decisions.md line about this gate: approvals and feedback alike."""
        run = self.run_paths(name)
        try:
            lines = run.decisions.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        pattern = re.compile(rf"\bgate {gate}\b", re.IGNORECASE)
        return [ln[2:] if ln.startswith("- ") else ln for ln in lines if pattern.search(ln)]

    def accept(self, name: str, step_id: str, note: str) -> Job:
        text = self._note(note)
        step = pipeline.find(self.steps(name), step_id)
        if step is None:
            raise ConsoleError(f"no step {step_id} in this run")
        state = self._state(name)
        lines: list[str] = []
        findings = state.data["failed"].get(step_id)
        if findings:
            try:
                lines = Path(findings).read_text(encoding="utf-8").splitlines()
            except OSError:
                lines = []
        elif step.done_on_disk:
            raise ConsoleError("this step is done and has no open findings to accept")
        run = self.run_paths(name)
        what = (
            f"{len(lines)} finding(s)"
            if lines
            else f"{len(step.members_todo)} unfinished member(s)"
        )
        job = self._human(
            name,
            f"Accept {step.title} as it stands",
            [
                [
                    "decide",
                    "--run",
                    str(run.root),
                    "--note",
                    f"console: accepted {step_id} with {what} and continued: {text}",
                ]
            ],
        )
        if job.status == SUCCEEDED:
            with self._lock:
                state.data["failed"].pop(step_id, None)
                state.data["accepted_findings"] = sorted(
                    set(state.data["accepted_findings"]) | {ln for ln in lines if ln.strip()}
                )
                if not step.done_on_disk:
                    state.data["accepted"] = sorted(set(state.data["accepted"]) | {step_id})
                state.save()
        return job

    def stop_rounds(self, name: str, note: str) -> Job:
        text = self._note(note)
        all_steps = self.steps(name)
        rounds = [
            s.round
            for s in all_steps
            if s.round and s.id.endswith("/score-seal") and s.status == pipeline.DONE
        ]
        if not rounds:
            raise ConsoleError("no round has finished yet, so there is no round to stop after")
        run = self.run_paths(name)
        return self._human(
            name,
            "Stop the round loop",
            [
                [
                    "decide",
                    "--run",
                    str(run.root),
                    "--note",
                    f"round loop stopped after round {max(rounds)} (console): {text}",
                ]
            ],
        )

    def decide(self, name: str, note: str) -> Job:
        run = self.run_paths(name)
        return self._human(
            name,
            "Record a decision",
            [["decide", "--run", str(run.root), "--note", self._note(note)]],
        )

    def waive(self, name: str, check: str, subject: str, remedy: str, reason: str) -> Job:
        run = self.run_paths(name)
        return self._human(
            name,
            "Waive a finding",
            [
                [
                    "waive",
                    "--run",
                    str(run.root),
                    "--check",
                    check,
                    "--subject",
                    subject,
                    "--remedy",
                    remedy,
                    "--reason",
                    self._note(reason),
                ]
            ],
        )

    def set_limit(self, name: str, limits: dict[str, int], reason: str) -> Job:
        run = self.run_paths(name)
        args = ["set-limit", "--run", str(run.root), "--reason", self._note(reason)]
        flags = {
            "max_rounds": "--max-rounds",
            "max_scenarios": "--max-scenarios",
            "max_scenario_part_bytes": "--max-scenario-part-bytes",
        }
        for key, value in limits.items():
            if key not in flags:
                raise ConsoleError(f"unknown limit {key}")
            args += [flags[key], str(int(value))]
        if len(args) == 6:
            raise ConsoleError("no limit given")
        return self._human(name, "Change a limit", [args])

    def delete_run(self, name: str, confirm: str) -> None:
        """Remove a run's directory and what this console kept about it.

        Not undoable, and a run holds model output that cost money, so the caller
        must send the run's name back as `confirm` -- a stray POST, or a click on
        the wrong card, deletes nothing. A run with a job still going is refused
        rather than cancelled: deleting the files under a live dispatch would leave
        it writing into a directory that no longer exists.
        """
        run = self.run_paths(name)
        if confirm != name:
            raise ConsoleError("type the run's name to confirm deleting it")
        # run_paths refuses `/` and dot-names; this also refuses a symlinked run,
        # whose rmtree would follow it to wherever it points.
        root = Path(os.path.abspath(run.root))
        if root.is_symlink() or root.parent != self.runs_dir:
            raise ConsoleError(f"{name} is not a run directory inside {self.runs_dir}")
        with self._lock:
            if self.active_job(name) is not None:
                raise ConsoleError("a job is still running on this run; cancel it first")
            shutil.rmtree(root)
            # The console's own records go too, or a new run that reused the name
            # would inherit this one's ledger, failures and spend.
            shutil.rmtree(self.lab / "console" / name, ignore_errors=True)
            self._states.pop(name, None)
            for job_id in [j for j, job in self._jobs.items() if job.run == name]:
                del self._jobs[job_id]

    def create_run(self, spec: dict) -> tuple[str | None, Job | None, str]:
        """Mint a run with `survey` or `intake --input`. Returns (run name, job, output)."""
        mode = spec.get("mode")
        target = (spec.get("target_name") or "").strip()
        interface = (spec.get("target_interface") or "").strip()
        if not target or not interface:
            raise ConsoleError("a target name and interface are required")
        args: list[str]
        if mode == "survey":
            corpus = [c for c in spec.get("corpus") or [] if c]
            if not corpus:
                raise ConsoleError("pick at least one corpus folder")
            objective = spec.get("objective") or "breadth"
            args = [
                "survey",
                "--runs-dir",
                str(self.runs_dir),
                "--target-name",
                target,
                "--target-interface",
                interface,
                "--objective",
                objective,
            ]
            for c in corpus:
                args += ["--corpus", c]
            for g in spec.get("exclude") or []:
                if g:
                    args += ["--exclude", g]
            for key in ("objective_note", "scope_note"):
                if spec.get(key):
                    args += [f"--{key.replace('_', '-')}", spec[key]]
        elif mode == "intake":
            inputs = [i for i in spec.get("inputs") or [] if i]
            if not inputs:
                raise ConsoleError("pick at least one input file")
            secret = self.credentials.path.expanduser().resolve()
            if any(Path(i).expanduser().resolve() == secret for i in inputs):
                raise ConsoleError("the console's credentials file cannot be a run input")
            args = [
                "intake",
                "--runs-dir",
                str(self.runs_dir),
                "--target-name",
                target,
                "--target-interface",
                interface,
            ]
            for i in inputs:
                args += ["--input", i]
        else:
            raise ConsoleError("mode must be 'survey' or 'intake'")
        for key in ("max_rounds", "max_scenarios"):
            if spec.get(key):
                args += [f"--{key.replace('_', '-')}", str(int(spec[key]))]
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run([*self.rubrica_argv, *args], capture_output=True, text=True)
        output = proc.stdout + proc.stderr
        if proc.returncode != CLEAN:
            raise ConsoleError(f"{mode} exited {proc.returncode}: {output.strip()}")
        printed = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        name = Path(printed[-1]).name if printed else None
        if name:
            # Kept beside the run's console records, so the same inputs can be run
            # again later without picking them again. Outside the run, like every
            # console record: the run's own contract says nothing of the console.
            keep = {k: v for k, v in spec.items() if k != "selection"}
            keep["selection"] = spec.get("selection")
            state = self._state(name)
            (state.home / "spec.json").write_text(json.dumps(keep, indent=2), encoding="utf-8")
        return name, None, output

    def run_spec(self, name: str) -> dict:
        """What a run was made from, so a new run can start from the same inputs.

        The console's own record when it created the run -- which keeps the picker
        selection exactly, exclusions included. Otherwise it is read back from the
        run: a survey run's catalogue names its corpus roots and exclusion globs,
        and a hand-picked run's manifest names each input's source path. That
        derived form has no picker selection, only what the command was given.
        """
        run = self.run_paths(name)
        stored = self._state(name).home / "spec.json"
        try:
            spec = json.loads(stored.read_text(encoding="utf-8"))
            if isinstance(spec, dict):
                spec["source"] = "console"
                return spec
        except (OSError, ValueError):
            pass
        spec: dict = {"source": "derived"}
        catalogue = pipeline._quietly(run.catalogue)
        manifest = pipeline._quietly(run.manifest)
        if isinstance(catalogue, dict):
            request = catalogue.get("request") or {}
            policy = catalogue.get("policy") or {}
            target = request.get("target") or {}
            spec.update(
                mode="survey",
                corpus=[str(p) for p in request.get("corpus_roots") or []],
                exclude=[str(g) for g in policy.get("operator_globs") or []],
                objective=request.get("objective") or "breadth",
                target_name=target.get("name", ""),
                target_interface=target.get("interface", ""),
                **{k: request.get(k) for k in ("objective_note", "scope_note") if request.get(k)},
                **(request.get("limits") or {}),
            )
        elif isinstance(manifest, dict):
            target = manifest.get("target") or {}
            spec.update(
                mode="intake",
                inputs=[
                    str(i["source_path"])
                    for i in manifest.get("inputs") or []
                    if isinstance(i, dict) and i.get("source_path")
                ],
                target_name=target.get("name", ""),
                target_interface=target.get("interface", ""),
                **(manifest.get("limits") or {}),
            )
        else:
            raise ConsoleError("this run records neither a catalogue nor a manifest")
        return spec
