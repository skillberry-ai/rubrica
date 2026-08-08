"""The two seams onto the outside world, exercised against real subprocesses.

No mocking. A mocked subprocess proves the call was formed, not that the thing on
the other end behaves -- and the properties that matter here are all about the
other end: that a timeout leaves a partial transcript, that stderr never reaches
the transcript reader, and that the verifier that runs is the copied one under an
import surface it would have in the container.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

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


def test_a_timeout_before_any_output_still_writes_an_empty_transcript(tmp_path):
    """exc.stdout is None, not bytes, when the agent produced no output before the kill.

    _decode's None branch is a separate code path from its bytes branch, and this
    is the only test that exercises it: a hung-from-the-start agent must not raise
    out of run_agent and discard every remaining role's data on every remaining
    task.
    """
    run = _emitted(tmp_path)
    logs, _, base = _paths(run)
    code, note = run_agent(
        _spec(
            _script(tmp_path, "silent_slow.py", "import time\ntime.sleep(30)\n"), timeout_sec=1.5
        ),
        task_dir=run.task_dir(SID),
        logs_dir=logs,
        stderr_path=base / "agent-stderr.txt",
        scenario_id=SID,
    )
    assert code is None
    assert "timed out" in note
    assert (logs / "agent-stdout.jsonl").read_text() == ""


def test_run_agent_refuses_a_stderr_path_inside_the_agent_log_directory(tmp_path):
    """The seam enforces this itself; it must not depend on every caller's discipline.

    Stage 7's smoke_run is the real caller and does not exist yet. If it ever
    passed logs_dir / "agent-stderr.txt", every test in this file that pins the
    stderr-outside-logs_dir property would stay green while the hazard the
    property exists to prevent came back.
    """
    run = _emitted(tmp_path)
    logs, _, _base = _paths(run)
    with pytest.raises(ValueError):
        run_agent(
            _spec(_script(tmp_path, "z.py", COMPETENT)),
            task_dir=run.task_dir(SID),
            logs_dir=logs,
            stderr_path=logs / "agent-stderr.txt",
            scenario_id=SID,
        )


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


def test_a_stale_reward_is_not_reused_when_the_verifier_exits_nonzero(tmp_path):
    """out_dir is per-(role, task); without a clear, a re-run would see the last score."""
    run = _emitted(tmp_path)
    logs, out, base = _paths(run)
    run_agent(
        _spec(_script(tmp_path, "good7.py", COMPETENT)),
        task_dir=run.task_dir(SID),
        logs_dir=logs,
        stderr_path=base / "agent-stderr.txt",
        scenario_id=SID,
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / "reward.json").write_text('{"reward": 1.0}', encoding="utf-8")  # a previous run's score
    (run.task_dir(SID) / "tests" / "verify.py").write_text("raise SystemExit(9)\n", "utf-8")
    code, reward, _ = verify_package(
        run.task_dir(SID),
        agent_logs=logs,
        out_dir=out,
        stderr_path=base / "verifier-stderr.txt",
    )
    assert code == 9
    assert reward is None, f"a stale reward.json was reported as this run's score: {reward}"


_EXITS_ZERO_WITHOUT_WRITING_VERIFIER = "import sys\nsys.exit(0)\n"


def test_a_stale_reward_is_cleared_before_a_verifier_that_exits_zero_and_writes_nothing(tmp_path):
    """The scenario the out_dir clear exists for -- the layer-3 scenario this task is named for.

    test_a_stale_reward_is_not_reused_when_the_verifier_exits_nonzero (above) pins
    the returncode half of the guard: its mangled verifier exits 9, which the
    `completed.returncode != 0` check catches on its own, whether or not out_dir
    was ever cleared. This test pins the half that check cannot see: a mangled
    verify.py that exits 0 without writing anything -- emit shipping a broken copy
    into the package, exactly the failure this module exists to catch -- with a
    previous attempt's reward.json still sitting in out_dir. Without the unlink in
    verify_package, that stale {"reward": 1.0} would pass both halves of the guard
    (returncode == 0, reward.json.is_file()) and be reported as this run's score.
    """
    run = _emitted(tmp_path)
    logs, out, base = _paths(run)
    run_agent(
        _spec(_script(tmp_path, "good12.py", COMPETENT)),
        task_dir=run.task_dir(SID),
        logs_dir=logs,
        stderr_path=base / "agent-stderr.txt",
        scenario_id=SID,
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / "reward.json").write_text('{"reward": 1.0}', encoding="utf-8")  # a previous run's score
    (run.task_dir(SID) / "tests" / "verify.py").write_text(
        _EXITS_ZERO_WITHOUT_WRITING_VERIFIER, encoding="utf-8"
    )
    code, reward, note = verify_package(
        run.task_dir(SID),
        agent_logs=logs,
        out_dir=out,
        stderr_path=base / "verifier-stderr.txt",
    )
    assert code == 0
    assert reward is None, f"a stale reward.json was reported as this run's score: {reward}"
    assert "diagnostic" in note, note


@pytest.mark.skipif(
    os.geteuid() == 0, reason="chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)"
)
def test_an_unremovable_stale_output_makes_the_task_unscoreable_without_raising(tmp_path):
    """Fail closed: an unlink failure must not let verify_package proceed or raise.

    A read-only out_dir reproduces a real failure mode -- a read-only mount, a
    permissions mismatch -- rather than mocking Path.unlink: this module's seams
    are tested against real subprocesses and real filesystem behaviour, and an
    unlink failure is exactly the kind of "the thing on the other end behaves
    differently than hoped" case a mock would paper over rather than exercise.
    """
    run = _emitted(tmp_path)
    logs, out, base = _paths(run)
    run_agent(
        _spec(_script(tmp_path, "good13.py", COMPETENT)),
        task_dir=run.task_dir(SID),
        logs_dir=logs,
        stderr_path=base / "agent-stderr.txt",
        scenario_id=SID,
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / "reward.json").write_text('{"reward": 1.0}', encoding="utf-8")
    out.chmod(0o555)  # read-only dir: removing an entry needs write permission on the parent
    try:
        code, reward, note = verify_package(
            run.task_dir(SID),
            agent_logs=logs,
            out_dir=out,
            stderr_path=base / "verifier-stderr.txt",
        )
    finally:
        out.chmod(0o755)  # restore so tmp_path's own cleanup can remove the directory
    assert code is None
    assert reward is None, f"an unremovable stale reward.json was reported as a score: {reward}"
    assert "reward.json" in note, note


_FRESH_REWARD_THEN_ERROR_VERIFIER = """\
import argparse, json, pathlib, sys

parser = argparse.ArgumentParser()
parser.add_argument("--expected")
parser.add_argument("--agent-logs")
parser.add_argument("--out")
args = parser.parse_args()
out = pathlib.Path(args.out)
out.mkdir(parents=True, exist_ok=True)
(out / "reward.json").write_text(json.dumps({"reward": 1.0}))
sys.exit(1)
"""


def test_a_freshly_written_reward_is_not_trusted_if_the_verifier_still_exits_nonzero(tmp_path):
    """The returncode half of the guard, independent of staleness.

    out_dir is cleared before the verifier runs (see verify_package's
    docstring), so a *stale* reward.json from a previous attempt cannot cause
    this. This is the other half: even a reward.json the verifier just wrote
    on *this* attempt must not be trusted if the process that wrote it did not
    exit 0 -- a verifier that scores and then crashes on some unrelated
    cleanup step is not a run whose score should reach the report.
    """
    run = _emitted(tmp_path)
    logs, out, base = _paths(run)
    run_agent(
        _spec(_script(tmp_path, "good7b.py", COMPETENT)),
        task_dir=run.task_dir(SID),
        logs_dir=logs,
        stderr_path=base / "agent-stderr.txt",
        scenario_id=SID,
    )
    (run.task_dir(SID) / "tests" / "verify.py").write_text(
        _FRESH_REWARD_THEN_ERROR_VERIFIER, encoding="utf-8"
    )
    code, reward, note = verify_package(
        run.task_dir(SID),
        agent_logs=logs,
        out_dir=out,
        stderr_path=base / "verifier-stderr.txt",
    )
    assert code == 1
    assert reward is None, f"a reward.json from a nonzero exit was reported as a score: {reward}"


def test_verify_package_refuses_out_dir_equal_to_agent_logs(tmp_path):
    """verify.py's own docstring names this hazard: a run reading its own reward.txt back."""
    run = _emitted(tmp_path)
    logs, _out, base = _paths(run)
    with pytest.raises(ValueError):
        verify_package(
            run.task_dir(SID),
            agent_logs=logs,
            out_dir=logs,
            stderr_path=base / "verifier-stderr.txt",
        )


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


_STDLIB_PROBE_VERIFIER = """\
import argparse, json, math, pathlib, sys

parser = argparse.ArgumentParser()
parser.add_argument("--expected")
parser.add_argument("--agent-logs")
parser.add_argument("--out")
args = parser.parse_args()
out = pathlib.Path(args.out)
out.mkdir(parents=True, exist_ok=True)
(out / "reward.json").write_text(json.dumps({"reward": math.floor(1.0)}))
sys.exit(0)
"""


def test_the_stdlib_is_still_reachable_under_the_scrub(tmp_path):
    """The scrub, as a whole, must not starve the verifier of the stdlib it needs.

    This is not a test of -S alone: -S only skips importing site, and was never
    going to remove argparse/json/math/pathlib/sys, which are stdlib rather than
    site-packages -- so the test cannot fail for that reason. What it actually
    guards is scrubbed_env()'s emptied PYTHONPATH and minimal PATH *together
    with* -S: the real verify.py imports exactly those five modules among
    others, and this stand-in imports that same set and nothing else, producing
    its reward only by using all five. If a future tightening of scrubbed_env()
    or an added interpreter flag broke one of them, this test would catch it
    here -- as a nonzero exit and reward is None -- rather than at every real
    task, where it would look like a broken suite instead of a broken harness.
    """
    run = _emitted(tmp_path)
    logs, out, base = _paths(run)
    run_agent(
        _spec(_script(tmp_path, "good4.py", COMPETENT)),
        task_dir=run.task_dir(SID),
        logs_dir=logs,
        stderr_path=base / "agent-stderr.txt",
        scenario_id=SID,
    )
    (run.task_dir(SID) / "tests" / "verify.py").write_text(_STDLIB_PROBE_VERIFIER, encoding="utf-8")
    code, reward, note = verify_package(
        run.task_dir(SID),
        agent_logs=logs,
        out_dir=out,
        stderr_path=base / "verifier-stderr.txt",
    )
    assert reward == {"reward": 1}, note
    assert code == 0
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
    stated = json.loads((_paths(run)[1] / "reward-detail.json").read_text())["error"]
    assert note == stated, "the note must be the verifier's own stated reason, not its stderr tail"


def test_a_package_with_no_verifier_is_unscoreable(tmp_path):
    run = _emitted(tmp_path)
    (run.task_dir(SID) / "tests" / "verify.py").unlink()
    _, reward, note = _score(run, COMPETENT, tmp_path, "good6.py")
    assert reward is None
    assert "no tests/verify.py" in note


def test_a_verifier_that_times_out_is_unscoreable(tmp_path):
    """Distinct from run_agent's timeout: this is the verifier itself hanging."""
    run = _emitted(tmp_path)
    logs, out, base = _paths(run)
    run_agent(
        _spec(_script(tmp_path, "good8.py", COMPETENT)),
        task_dir=run.task_dir(SID),
        logs_dir=logs,
        stderr_path=base / "agent-stderr.txt",
        scenario_id=SID,
    )
    (run.task_dir(SID) / "tests" / "verify.py").write_text(
        "import time\ntime.sleep(30)\n", encoding="utf-8"
    )
    code, reward, note = verify_package(
        run.task_dir(SID),
        agent_logs=logs,
        out_dir=out,
        stderr_path=base / "verifier-stderr.txt",
        timeout_sec=1.0,
    )
    assert (code, reward, note) == (None, None, "verifier timed out after 1.0 s")


_UNREADABLE_JSON_VERIFIER = """\
import argparse, pathlib, sys

parser = argparse.ArgumentParser()
parser.add_argument("--expected")
parser.add_argument("--agent-logs")
parser.add_argument("--out")
args = parser.parse_args()
out = pathlib.Path(args.out)
out.mkdir(parents=True, exist_ok=True)
(out / "reward.json").write_text("not json at all")
sys.exit(0)
"""


def test_a_verifier_that_writes_unreadable_json_is_unscoreable(tmp_path):
    """emit could ship a copy that gets this far and still corrupts its own output."""
    run = _emitted(tmp_path)
    logs, out, base = _paths(run)
    run_agent(
        _spec(_script(tmp_path, "good9.py", COMPETENT)),
        task_dir=run.task_dir(SID),
        logs_dir=logs,
        stderr_path=base / "agent-stderr.txt",
        scenario_id=SID,
    )
    (run.task_dir(SID) / "tests" / "verify.py").write_text(
        _UNREADABLE_JSON_VERIFIER, encoding="utf-8"
    )
    code, reward, note = verify_package(
        run.task_dir(SID),
        agent_logs=logs,
        out_dir=out,
        stderr_path=base / "verifier-stderr.txt",
    )
    assert code == 0
    assert reward is None
    assert "unreadable reward.json" in note


def test_a_verifier_that_writes_a_non_object_reward_is_unscoreable(tmp_path):
    """A valid-JSON, wrong-shape reward.json must not be handed to the report as a score."""
    run = _emitted(tmp_path)
    logs, out, base = _paths(run)
    run_agent(
        _spec(_script(tmp_path, "good10.py", COMPETENT)),
        task_dir=run.task_dir(SID),
        logs_dir=logs,
        stderr_path=base / "agent-stderr.txt",
        scenario_id=SID,
    )
    (run.task_dir(SID) / "tests" / "verify.py").write_text(
        _UNREADABLE_JSON_VERIFIER.replace('"not json at all"', '"[1.0]"'), encoding="utf-8"
    )
    code, reward, note = verify_package(
        run.task_dir(SID),
        agent_logs=logs,
        out_dir=out,
        stderr_path=base / "verifier-stderr.txt",
    )
    assert code == 0
    assert reward is None
    assert "not an object" in note


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
