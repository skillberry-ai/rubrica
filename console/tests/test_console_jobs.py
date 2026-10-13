"""The console's job runner, driven against real toy runs with a fake dispatcher.

The fake stands in for `scripts/dispatch-stage.sh` and nothing else: it copies
the artifact a stage would write out of a complete toy run, prints the closing
`cost` line the real script prints, and can be told to fail. Everything around
it is real -- the `rubrica` CLI for every gate, seal and record, the toy fixture
for every artifact -- so a step this suite calls clean is one the real gates
called clean.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import textwrap
import time
from pathlib import Path

import pytest
from rubrica_console import credentials, pipeline
from rubrica_console.jobs import (
    CANCELLED,
    FAILED,
    HALTED,
    INTERRUPTED,
    SUCCEEDED,
    Console,
    ConsoleError,
    Options,
)

from tests.toy import build_toy_run

# Where each stage's output lives, so the fake can copy it from the reference run.
_FAKE = textwrap.dedent(
    """\
    import json, os, shutil, sys, time
    from pathlib import Path

    stage, run = sys.argv[1], Path(sys.argv[2])
    member = sys.argv[3] if len(sys.argv) > 3 else None
    ref = Path(os.environ["FAKE_REF"])
    log = Path(os.environ["FAKE_LOG"])
    with log.open("a") as fh:
        fh.write(json.dumps({
            "stage": stage, "member": member, "start": time.time(),
            "findings": os.environ.get("RUBRICA_FINDINGS_FILE"),
            "findings_text": (Path(os.environ["RUBRICA_FINDINGS_FILE"]).read_text()
                              if os.environ.get("RUBRICA_FINDINGS_FILE") else None),
            "reseed": os.environ.get("RUBRICA_RESEED"),
            "reject": os.environ.get("RUBRICA_REJECT"),
            "model": os.environ.get("RUBRICA_MODEL"),
            "token": os.environ.get("ANTHROPIC_AUTH_TOKEN"),
            "api_key": os.environ.get("ANTHROPIC_API_KEY"),
            "base_url": os.environ.get("ANTHROPIC_BASE_URL"),
            "headers": os.environ.get("ANTHROPIC_CUSTOM_HEADERS"),
        }) + "\\n")
    time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
    key = f"{stage}:{member}" if member else stage
    if key in os.environ.get("FAKE_EXIT2", "").split():
        print("refusing", file=sys.stderr); sys.exit(2)
    if key in os.environ.get("FAKE_EXIT1_AFTER_SPEND", "").split():
        print(json.dumps({"type": "result", "is_error": True, "total_cost_usd": 0.4,
                          "result": "the model ran out of turns"}))
        print("cost        $0.40 over 9 turns, ceiling none")
        sys.exit(1)
    if key in os.environ.get("FAKE_FAIL", "").split():
        # The shape a refused call leaves: a result line with is_error, no spend.
        print(json.dumps({"type": "result", "is_error": True, "total_cost_usd": 0,
                          "result": "Failed to authenticate. API Error: 401"}))
        sys.exit(1)
    single = {
        "reconcile-subjects": "01-subjects.json",
        "reconcile-capabilities": "01-capabilities.json",
        "reconcile-outcomes": "01-outcomes.json",
        "reconcile-entities": "01-entities.json",
        "reconcile-goals": "01-goals.json",
        "reconcile-gaps": "01-gaps.json",
        "reconcile-services": "01-services.json",
        "triage-objective": "00-objective.json",
        "triage-audit": "00-audit.json",
    }
    fanned = {
        "extract": "01-claims/{}.json",
        "reconcile-contradict": "01-contradictions/{}.json",
        "triage-rule": "00-dispositions/{}.json",
        "challenge": "05-verdicts/{}.json",
    }
    rel = single.get(stage) or (fanned[stage].format(member) if stage in fanned else None)
    if stage == "propose":
        rel = next(str(p.relative_to(ref)) for p in ref.glob(f"02-scenarios/round-*/{member}.json"))
    if stage == "score":
        rel = sorted(str(p.relative_to(ref)) for p in ref.glob("03-score/round-*.json"))[-1]
    if stage == "instantiate":
        rel = f"04-instances/{member}"
    bad = key in os.environ.get("FAKE_BAD", "").split() and (
        not os.environ.get("RUBRICA_FINDINGS_FILE")
        or key in os.environ.get("FAKE_BAD_ON_REPAIR", "").split()
    )
    dst = run / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if bad:
        dst.write_text("{}")
    elif (ref / rel).is_dir():
        shutil.copytree(ref / rel, dst, dirs_exist_ok=True)
    else:
        shutil.copyfile(ref / rel, dst)
    use = {"type": "tool_use", "name": "Write", "input": {"file_path": str(dst)}}
    print(json.dumps({"type": "assistant", "message": {"content": [use]}}))
    print("transcript  /dev/null")
    print("cost        $0.25 over 3 turns, ceiling none")
    """
)


@pytest.fixture(scope="module")
def reference(tmp_path_factory) -> Path:
    """A complete toy run: the source of every artifact the fake writes."""
    return build_toy_run(tmp_path_factory.mktemp("ref")).root


@pytest.fixture
def fake(tmp_path, reference, monkeypatch) -> dict:
    script = tmp_path / "fake-dispatch.sh"
    py = tmp_path / "fake.py"
    py.write_text(_FAKE, encoding="utf-8")
    script.write_text(f'#!/usr/bin/env bash\nexec "{os.sys.executable}" "{py}" "$@"\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "fake.log"
    monkeypatch.setenv("FAKE_REF", str(reference))
    monkeypatch.setenv("FAKE_LOG", str(log))
    for var in (
        "FAKE_FAIL",
        "FAKE_BAD",
        "FAKE_BAD_ON_REPAIR",
        "FAKE_EXIT2",
        "FAKE_SLEEP",
        "FAKE_EXIT1_AFTER_SPEND",
    ):
        monkeypatch.delenv(var, raising=False)
    return {"script": script, "log": log}


def _calls(fake) -> list[dict]:
    try:
        return [json.loads(line) for line in fake["log"].read_text().splitlines()]
    except FileNotFoundError:
        return []


def _store(tmp_path) -> credentials.Store:
    store = credentials.Store(tmp_path / "creds" / "console-credentials.json")
    store.save(
        credentials.Credentials(
            base_url="https://gateway.example/anthropic",
            secret="console-token-1234",
            headers={"x-gateway-token": "hdr-5678"},
        )
    )
    return store


def _console(tmp_path, runs_dir, fake, **kw) -> Console:
    kw.setdefault("credentials", _store(tmp_path))
    return Console(runs_dir, tmp_path / "lab", dispatch_script=fake["script"], **kw)


OPTS = Options(model="test-model", effort="medium")


@pytest.fixture
def intake_run(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="intake")
    return run


def _status(console, name) -> dict[str, str]:
    return {s.id: s.status for s in console.steps(name)}


def test_run_to_gate_drives_the_world_model_band_and_stops_at_gate_1(tmp_path, fake, intake_run):
    console = _console(tmp_path, intake_run.root.parent, fake)
    name = intake_run.root.name
    job = console.wait(console.run_to_gate(name, OPTS).id, timeout=180)
    assert job.status == SUCCEEDED, (job.message, [(e.label, e.status) for e in job.entries])
    assert "Gate 1" in job.message
    status = _status(console, name)
    assert status["gate-1"] == pipeline.READY
    assert all(
        v == pipeline.DONE for k, v in status.items() if k != "gate-1" and not k.startswith("round")
    ), status
    # record-stage ran with the model the dispatch used.
    stages = json.loads(intake_run.manifest.read_text())["stages"]
    assert stages["extract"]["model"] == "test-model"
    assert stages["reconcile-services"]["effort"] == "medium"
    # Every fan-out member got its own id and nothing else.
    members = [c["member"] for c in _calls(fake) if c["stage"] == "extract"]
    inputs = [i["artifact_id"] for i in json.loads(intake_run.manifest.read_text())["inputs"]]
    assert sorted(members) == sorted(inputs)
    assert job.cost == pytest.approx(0.25 * len(_calls(fake)))


def test_a_fan_out_runs_only_its_missing_members(tmp_path, fake, intake_run, reference):
    first = json.loads(intake_run.manifest.read_text())["inputs"][0]["artifact_id"]
    intake_run.claims_dir.mkdir(exist_ok=True)
    shutil.copyfile(reference / "01-claims" / f"{first}.json", intake_run.claims(first))
    console = _console(tmp_path, intake_run.root.parent, fake)
    job = console.wait(console.run_step(intake_run.root.name, "extract", OPTS).id, timeout=60)
    assert job.status == SUCCEEDED, job.message
    assert first not in [c["member"] for c in _calls(fake)]


def test_no_more_than_max_parallel_dispatches_run_at_once(tmp_path, fake, intake_run, monkeypatch):
    monkeypatch.setenv("FAKE_SLEEP", "0.4")
    console = _console(tmp_path, intake_run.root.parent, fake, max_parallel=1)
    job = console.wait(console.run_step(intake_run.root.name, "extract", OPTS).id, timeout=60)
    assert job.status == SUCCEEDED, job.message
    starts = sorted(c["start"] for c in _calls(fake))
    assert len(starts) >= 2
    # With a cap of one, each dispatch starts after the previous one slept.
    assert all(b - a >= 0.35 for a, b in zip(starts, starts[1:], strict=False))


def test_findings_fail_the_step_and_repair_sends_each_member_its_own_lines(
    tmp_path, fake, intake_run, monkeypatch
):
    inputs = [i["artifact_id"] for i in json.loads(intake_run.manifest.read_text())["inputs"]]
    bad = inputs[0]
    monkeypatch.setenv("FAKE_BAD", f"extract:{bad}")
    console = _console(tmp_path, intake_run.root.parent, fake)
    name = intake_run.root.name
    job = console.wait(console.run_step(name, "extract", OPTS).id, timeout=60)
    assert job.status == FAILED
    assert "finding" in job.message
    # The page shows the findings themselves, verbatim, without a log click.
    shown = job.as_dict()["findings"]
    assert shown and all(bad in line for line in shown)
    assert _status(console, name)["extract"] == pipeline.FAILED
    # Run-to-gate refuses to walk past an open failure.
    with pytest.raises(ConsoleError):
        console.run_to_gate(name, OPTS)

    repaired = console.wait(console.run_step(name, "extract", OPTS, repair=True).id, timeout=60)
    assert repaired.status == SUCCEEDED, repaired.message
    repair_calls = [c for c in _calls(fake) if c["findings"]]
    assert [c["member"] for c in repair_calls] == [bad]
    # Its lines, verbatim from the gate, and only lines that name it.
    assert bad in repair_calls[0]["findings_text"]
    assert all(bad in ln for ln in repair_calls[0]["findings_text"].splitlines())
    assert _status(console, name)["extract"] == pipeline.DONE


def test_a_failed_repair_halts_and_offers_no_second_repair(tmp_path, fake, intake_run, monkeypatch):
    """rb-orchestrate A4: one repair, then halt."""
    console = _console(tmp_path, intake_run.root.parent, fake)
    name = intake_run.root.name
    console.wait(console.run_step(name, "extract", OPTS).id, timeout=60)
    monkeypatch.setenv("FAKE_BAD", "reconcile-subjects")
    monkeypatch.setenv("FAKE_BAD_ON_REPAIR", "reconcile-subjects")
    job = console.wait(console.run_step(name, "reconcile-subjects", OPTS).id, timeout=60)
    assert job.status == FAILED
    second = console.wait(console.run_step(name, "reconcile-subjects", OPTS, repair=True).id, 60)
    assert second.status == HALTED
    assert "after its one repair" in second.message
    with pytest.raises(ConsoleError, match="already failed its repair"):
        console.run_step(name, "reconcile-subjects", OPTS, repair=True)


def test_exit_2_from_the_dispatcher_halts_without_a_repair(tmp_path, fake, intake_run, monkeypatch):
    monkeypatch.setenv("FAKE_EXIT2", "reconcile-subjects")
    console = _console(tmp_path, intake_run.root.parent, fake)
    name = intake_run.root.name
    console.wait(console.run_step(name, "extract", OPTS).id, timeout=60)
    job = console.wait(console.run_step(name, "reconcile-subjects", OPTS).id, timeout=60)
    assert job.status == HALTED
    assert "exit 2" in job.message
    with pytest.raises(ConsoleError, match="nothing to repair"):
        console.run_step(name, "reconcile-subjects", OPTS, repair=True)


def test_accepted_findings_do_not_fail_later_gates(tmp_path, fake, intake_run, monkeypatch):
    inputs = [i["artifact_id"] for i in json.loads(intake_run.manifest.read_text())["inputs"]]
    monkeypatch.setenv("FAKE_BAD", f"extract:{inputs[0]}")
    console = _console(tmp_path, intake_run.root.parent, fake)
    name = intake_run.root.name
    console.wait(console.run_step(name, "extract", OPTS).id, timeout=60)
    accept = console.accept(name, "extract", "known bad input, ruled acceptable")
    assert accept.status == SUCCEEDED, accept.message
    assert "accepted extract" in intake_run.decisions.read_text()
    assert _status(console, name)["extract"] == pipeline.DONE
    # The first run stopped at validate, so check-refs had never run: on the
    # re-run, validate's accepted lines pass and check-refs' finding -- one nobody
    # has seen yet -- still stops the step. Accepting is per line, never blanket.
    again = console.wait(console.run_step(name, "extract", OPTS).id, timeout=60)
    assert again.status == FAILED
    assert "check-refs" in again.message
    console.accept(name, "extract", "same bad input, as seen by check-refs")
    third = console.wait(console.run_step(name, "extract", OPTS).id, timeout=60)
    assert third.status == SUCCEEDED, third.message
    # Still printed in the gate's log, never hidden.
    assert any("check-refs" in e.label for e in third.entries)


def test_accepting_needs_a_note(tmp_path, fake, intake_run):
    console = _console(tmp_path, intake_run.root.parent, fake)
    with pytest.raises(ConsoleError, match="note is required"):
        console.accept(intake_run.root.name, "extract", "   ")


def test_cancel_stops_running_dispatches(tmp_path, fake, intake_run, monkeypatch):
    monkeypatch.setenv("FAKE_SLEEP", "30")
    console = _console(tmp_path, intake_run.root.parent, fake)
    job = console.run_step(intake_run.root.name, "extract", OPTS)
    deadline = time.time() + 10
    while not _calls(fake) and time.time() < deadline:
        time.sleep(0.05)
    console.cancel(job.id)
    done = console.wait(job.id, timeout=20)
    assert done.status == CANCELLED


def test_deleting_a_run_removes_it_and_the_consoles_records(tmp_path, fake, intake_run):
    console = _console(tmp_path, intake_run.root.parent, fake)
    name = intake_run.root.name
    console.wait(console.run_step(name, "extract", OPTS).id, timeout=60)
    records = console.lab / "console" / name
    assert records.is_dir() and console.jobs(name)
    with pytest.raises(ConsoleError, match="type the run's name"):
        console.delete_run(name, "")
    assert intake_run.root.is_dir()
    console.delete_run(name, name)
    assert not intake_run.root.exists() and not records.exists()
    assert console.jobs(name) == [] and name not in console.list_runs()


def test_a_run_with_a_job_going_is_not_deleted(tmp_path, fake, intake_run, monkeypatch):
    monkeypatch.setenv("FAKE_SLEEP", "30")
    console = _console(tmp_path, intake_run.root.parent, fake)
    name = intake_run.root.name
    job = console.run_step(name, "extract", OPTS)
    with pytest.raises(ConsoleError, match="still running"):
        console.delete_run(name, name)
    assert intake_run.root.is_dir()
    console.cancel(job.id)
    console.wait(job.id, timeout=20)


def test_a_symlinked_run_is_not_deleted_through_the_link(tmp_path, fake, intake_run):
    elsewhere = tmp_path / "elsewhere"
    intake_run.root.rename(elsewhere)
    intake_run.root.symlink_to(elsewhere)
    console = _console(tmp_path, intake_run.root.parent, fake)
    with pytest.raises(ConsoleError, match="not a run directory"):
        console.delete_run(intake_run.root.name, intake_run.root.name)
    assert (elsewhere / "manifest.json").exists()


def test_a_restart_marks_running_jobs_interrupted(tmp_path, fake, intake_run, monkeypatch):
    monkeypatch.setenv("FAKE_SLEEP", "30")
    console = _console(tmp_path, intake_run.root.parent, fake)
    job = console.run_step(intake_run.root.name, "extract", OPTS)
    deadline = time.time() + 10
    while not _calls(fake) and time.time() < deadline:
        time.sleep(0.05)
    restarted = _console(tmp_path, intake_run.root.parent, fake)
    assert restarted.job(job.id).status == INTERRUPTED
    console.cancel(job.id)
    console.wait(job.id, timeout=20)


def test_one_job_at_a_time_per_run(tmp_path, fake, intake_run, monkeypatch):
    monkeypatch.setenv("FAKE_SLEEP", "2")
    console = _console(tmp_path, intake_run.root.parent, fake)
    job = console.run_step(intake_run.root.name, "extract", OPTS)
    with pytest.raises(ConsoleError, match="already has a job running"):
        console.run_step(intake_run.root.name, "extract", OPTS)
    console.cancel(job.id)
    console.wait(job.id, timeout=20)


def test_a_gate_cannot_be_run_only_approved_with_a_note(tmp_path, fake):
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    console = _console(tmp_path, run.root.parent, fake)
    name = run.root.name
    with pytest.raises(ConsoleError, match="held by a human"):
        console.run_step(name, "gate-1", OPTS)
    with pytest.raises(ConsoleError, match="note is required"):
        console.approve_gate(name, 1, "")
    job = console.approve_gate(name, 1, "world model reads right")
    assert job.status == SUCCEEDED, job.message
    assert "human gate 1 (console): world model reads right" in run.decisions.read_text()
    assert _status(console, name)["gate-1"] == pipeline.DONE


def test_gate_0_approval_admits_the_inputs_and_records_the_triage_passes(tmp_path, fake):
    run = build_toy_run(tmp_path / "runs", upto="triage-seal")
    console = _console(tmp_path, run.root.parent, fake)
    name = run.root.name
    console._state(name).data["used"]["triage-objective"] = {"model": "m1", "effort": "low"}
    job = console.approve_gate(name, 0, "admit what triage chose")
    assert job.status == SUCCEEDED, (job.message, [(e.label, e.exit) for e in job.entries])
    manifest = json.loads(run.manifest.read_text())
    assert manifest["stages"]["triage-objective"]["model"] == "m1"
    assert "human gate 0 (console)" in run.decisions.read_text()


def test_smoke_never_runs_without_a_roster(tmp_path, fake):
    run = build_toy_run(tmp_path / "runs")
    console = _console(tmp_path, run.root.parent, fake)
    with pytest.raises(ConsoleError):
        console.run_step(run.root.name, "smoke", OPTS)


def test_prompt_steps_are_refused_without_a_dispatch_script(tmp_path, intake_run):
    console = Console(
        intake_run.root.parent,
        tmp_path / "lab",
        dispatch_script=tmp_path / "missing.sh",
        credentials=_store(tmp_path),
    )
    with pytest.raises(ConsoleError, match="repository checkout"):
        console.run_step(intake_run.root.name, "extract", OPTS)
    extract = pipeline.find(console.steps(intake_run.root.name), "extract")
    assert "repository checkout" in extract.reason


def test_create_run_by_intake(tmp_path, fake):
    toy = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "toy"
    console = _console(tmp_path, tmp_path / "runs", fake)
    name, _, _ = console.create_run(
        {
            "mode": "intake",
            "target_name": "toy",
            "target_interface": "http",
            "inputs": [str(p) for p in sorted(toy.iterdir()) if p.is_file()],
        }
    )
    assert name in console.list_runs()
    assert pipeline.next_step(console.steps(name)).id == "extract"


def test_create_run_refuses_an_empty_spec(tmp_path, fake):
    console = _console(tmp_path, tmp_path / "runs", fake)
    with pytest.raises(ConsoleError):
        console.create_run({"mode": "survey", "target_name": "t", "target_interface": "mcp"})


def test_a_round_runs_end_to_end_and_records_its_verdict(tmp_path, fake):
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    console = _console(tmp_path, run.root.parent, fake)
    name = run.root.name
    console.approve_gate(name, 1, "looks right")
    job = console.wait(console.run_to_gate(name, OPTS).id, timeout=180)
    assert job.status == SUCCEEDED, (job.message, [(e.label, e.status) for e in job.entries])
    decisions = run.decisions.read_text()
    assert "round 1:" in decisions and "(console)" in decisions
    status = _status(console, name)
    assert status["round-1/score-seal"] == pipeline.DONE
    assert status["round-1/propose-seal-2"] == pipeline.DONE
    # Stopped at a gate, never past one.
    assert next(s for s in console.steps(name) if s.status == pipeline.READY).kind == pipeline.GATE


def test_followup_reseeds_once_and_carries_rejects_to_score(tmp_path, fake):
    run = build_toy_run(tmp_path / "runs")
    ids = run.scenario_ids_with_instances()
    reseed, reject = ids[0], ids[1]
    for sid, verdict in ((reseed, "re-seed"), (reject, "reject")):
        doc = json.loads(run.verdict(sid).read_text())
        doc["verdict"] = verdict
        run.verdict(sid).write_text(json.dumps(doc))
    console = _console(tmp_path, run.root.parent, fake)
    name = run.root.name
    step = pipeline.find(console.steps(name), "followup")
    assert step.status == pipeline.READY
    assert sorted(step.members_todo) == sorted([reseed, reject])
    job = console.wait(console.run_step(name, "followup", OPTS).id, timeout=120)
    calls = _calls(fake)
    inst = [c for c in calls if c["stage"] == "instantiate"]
    assert [(c["member"], c["reseed"]) for c in inst] == [(reseed, "1")]
    assert [c["member"] for c in calls if c["stage"] == "challenge"] == [reseed]
    score = [c for c in calls if c["stage"] == "score"]
    assert len(score) == 1 and reject in score[0]["reject"].split()
    # Once is the budget: the ledger remembers the re-seed.
    assert reseed in console.ledger_view(name)["reseeded"]
    assert job.status in (SUCCEEDED, FAILED)


# -- the console's own credentials ---------------------------------------------------


def test_dispatches_get_the_consoles_credentials_and_none_of_the_shells(
    tmp_path, fake, intake_run, monkeypatch
):
    """Measured: dispatches borrowed the shell's ANTHROPIC_* and failed 401 when the
    console was started outside Claude Code. They must get exactly the console's."""
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "shell-token-should-not-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "shell-key-should-not-leak")
    monkeypatch.setenv("ANTHROPIC_CUSTOM_HEADERS", "x-shell: leak")
    console = _console(tmp_path, intake_run.root.parent, fake)
    job = console.wait(console.run_step(intake_run.root.name, "extract", OPTS).id, timeout=60)
    assert job.status == SUCCEEDED, job.message
    calls = _calls(fake)
    assert calls
    for call in calls:
        assert call["token"] == "console-token-1234"
        assert call["api_key"] is None
        assert call["base_url"] == "https://gateway.example/anthropic"
        assert call["headers"] == "x-gateway-token: hdr-5678"


def test_without_credentials_no_prompt_step_runs(tmp_path, fake, intake_run):
    empty = credentials.Store(tmp_path / "none.json")
    console = _console(tmp_path, intake_run.root.parent, fake, credentials=empty)
    with pytest.raises(ConsoleError, match="Settings"):
        console.run_step(intake_run.root.name, "extract", OPTS)
    assert _calls(fake) == []


def test_a_fan_out_whose_first_dispatches_cannot_reach_the_model_stops_early(
    tmp_path, fake, intake_run, monkeypatch
):
    inputs = [i["artifact_id"] for i in json.loads(intake_run.manifest.read_text())["inputs"]]
    monkeypatch.setenv("FAKE_FAIL", " ".join(f"extract:{a}" for a in inputs))
    monkeypatch.setattr("rubrica_console.jobs._FAIL_FAST_AFTER", 1)
    console = _console(tmp_path, intake_run.root.parent, fake, max_parallel=1)
    job = console.wait(console.run_step(intake_run.root.name, "extract", OPTS).id, timeout=60)
    assert job.status == HALTED
    assert "Failed to authenticate" in job.message
    # One wave, not the whole fan-out.
    assert len(_calls(fake)) < len(inputs)
    member = next(m for m in job.members.values() if m.status == HALTED)
    assert "401" in member.error


def test_a_dispatch_that_spent_money_and_failed_does_not_stop_the_fan_out(
    tmp_path, fake, intake_run, monkeypatch
):
    """A failure after reaching the model is that member's problem, not everyone's."""
    inputs = [i["artifact_id"] for i in json.loads(intake_run.manifest.read_text())["inputs"]]
    monkeypatch.setattr("rubrica_console.jobs._FAIL_FAST_AFTER", 1)
    monkeypatch.setenv("FAKE_EXIT1_AFTER_SPEND", f"extract:{inputs[0]}")
    console = _console(tmp_path, intake_run.root.parent, fake, max_parallel=1)
    console.wait(console.run_step(intake_run.root.name, "extract", OPTS).id, timeout=60)
    assert len(_calls(fake)) == len(inputs)


# -- keeping a run's inputs for a re-run ----------------------------------------------


def test_a_console_made_run_keeps_its_selection(tmp_path, fake):
    toy = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "toy"
    console = _console(tmp_path, tmp_path / "runs", fake)
    selection = {
        "include": [str(toy)],
        "exclude": [str(toy / "trace.json")],
        "dirs": {str(toy): True},
    }
    name, _, _ = console.create_run(
        {
            "mode": "intake",
            "target_name": "toy",
            "target_interface": "http",
            "inputs": [str(toy / "api.json"), str(toy / "notes.md")],
            "selection": selection,
            "extra_exclude": [],
            "max_rounds": 3,
        }
    )
    spec = console.run_spec(name)
    assert spec["source"] == "console"
    assert spec["selection"] == selection
    assert spec["max_rounds"] == 3


def test_a_run_made_elsewhere_has_its_inputs_read_back(tmp_path, fake):
    run = build_toy_run(tmp_path / "runs", upto="intake")
    spec = _console(tmp_path, run.root.parent, fake).run_spec(run.root.name)
    assert spec["source"] == "derived" and spec["mode"] == "intake"
    sources = [i["source_path"] for i in json.loads(run.manifest.read_text())["inputs"]]
    assert spec["inputs"] == sources
    survey_run = build_toy_run(tmp_path / "s", upto="triage-seal")
    spec = _console(tmp_path, survey_run.root.parent, fake).run_spec(survey_run.root.name)
    assert spec["mode"] == "survey" and spec["corpus"]


def test_the_credentials_file_is_never_a_run_input(tmp_path, fake):
    console = _console(tmp_path, tmp_path / "runs", fake)
    with pytest.raises(ConsoleError, match="credentials"):
        console.create_run(
            {
                "mode": "intake",
                "target_name": "t",
                "target_interface": "x",
                "inputs": [str(console.credentials.path)],
            }
        )
