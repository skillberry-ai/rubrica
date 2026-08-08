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
from pathlib import Path

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
