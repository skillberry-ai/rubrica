"""smoke_run end to end, against scripted agents rather than models.

The suite has to discriminate or none of the rest of this project means
anything, so these tests drive a real emitted package with a real verifier
subprocess and assert on the spread. The only fiction is the agent: three short
Python scripts standing in for a weak baseline, a competent agent, and an oracle.
"""

from __future__ import annotations

import sys

from testgen.artifacts import read_json
from testgen.smoke import ROLES, AgentSpec, smoke_run
from testgen.validate import validate_stage
from tests.unit.test_refs_states import build_state
from tests.unit.test_smoke_subprocess import COMPETENT, TOOLLESS

SID = "scn-001"

CRASHER = "import sys\nsys.exit(7)\n"

SLOW_BUT_CORRECT = COMPETENT + "import sys, time\nsys.stdout.flush()\ntime.sleep(30)\n"


def _spec(tmp_path, role, body, name=None, timeout_sec=60.0):
    script = tmp_path / (name or f"{role}.py")
    script.write_text(body, encoding="utf-8")
    return AgentSpec(
        role=role,
        model=f"model-{role}",
        command=(sys.executable, str(script)),
        timeout_sec=timeout_sec,
    )


def _roster(tmp_path, weak=TOOLLESS, under=COMPETENT, oracle=COMPETENT):
    return (
        _spec(tmp_path, "weak_baseline", weak),
        _spec(tmp_path, "under_test", under),
        _spec(tmp_path, "oracle", oracle),
    )


def _run(tmp_path):
    return build_state(tmp_path / "run", "emit")


def test_a_real_spread_produces_a_healthy_report(tmp_path):
    run = _run(tmp_path)
    report, findings = smoke_run(run, _roster(tmp_path))
    assert findings == [], findings
    assert report["verdict"] == "healthy"
    assert report["summary"]["mean_reward_by_role"] == {
        "weak_baseline": 0.0,
        "under_test": 1.0,
        "oracle": 1.0,
    }
    assert [task["scenario_id"] for task in report["tasks"]] == [SID]


def test_the_written_report_passes_layer_one(tmp_path):
    """The gate has to accept the artifact its own producer writes.

    A report smoke wrote that fails `validate --stage smoke` is a stage defect
    wearing a layer-1 error's clothes, and the orchestrator would retry the stage
    that is not at fault.
    """
    run = _run(tmp_path)
    smoke_run(run, _roster(tmp_path))
    assert validate_stage(run, "smoke") == []
    assert read_json(run.report)["run_id"] == read_json(run.manifest)["run_id"]


def test_the_report_lists_the_agents_in_role_order_with_their_models(tmp_path):
    run = _run(tmp_path)
    report, _ = smoke_run(run, _roster(tmp_path))
    assert [agent["role"] for agent in report["agents"]] == list(ROLES)
    assert [agent["model"] for agent in report["agents"]] == [f"model-{r}" for r in ROLES]


def test_a_trivial_suite_is_reported_as_a_finding_not_just_a_verdict(tmp_path):
    """smoke is a gate. Exit 0 on a degenerate suite would tell the orchestrator
    the suite is fit to trust."""
    run = _run(tmp_path)
    report, findings = smoke_run(run, _roster(tmp_path, weak=COMPETENT))
    assert report["verdict"] == "degenerate_trivial"
    assert len(findings) == 1
    assert findings[0].pointer == "/verdict"
    assert "weak baseline" in findings[0].message


def test_broken_labels_are_reported_against_the_labels_not_the_agent(tmp_path):
    run = _run(tmp_path)
    report, findings = smoke_run(run, _roster(tmp_path, oracle=TOOLLESS))
    assert report["verdict"] == "broken_labels"
    message = " ".join(f.message for f in findings)
    assert "gold labels or the verifier" in message


def test_a_crashing_agent_leaves_the_task_unscoreable_and_the_run_intact(tmp_path):
    """One broken role must not cost the other two their data."""
    run = _run(tmp_path)
    report, findings = smoke_run(run, _roster(tmp_path, under=CRASHER))
    results = {r["role"]: r for r in report["tasks"][0]["results"]}
    assert results["under_test"]["scored"] is False
    assert results["oracle"]["scored"] is True
    assert report["summary"]["unscoreable"] == 1
    assert report["verdict"] == "inconclusive"
    assert any("under_test" in f.message for f in findings)


def test_an_unscoreable_result_carries_no_reward_key_at_all(tmp_path):
    """Not reward: 0.0. The schema's `if scored then required` says the same
    thing, and a 0.0 here would be averaged as a real score by any later reader."""
    run = _run(tmp_path)
    report, _ = smoke_run(run, _roster(tmp_path, under=CRASHER))
    result = next(r for r in report["tasks"][0]["results"] if r["role"] == "under_test")
    assert "reward" not in result
    assert result["notes"]


def test_a_timed_out_agent_is_scored_on_the_partial_transcript_it_produced(tmp_path):
    """run_agent writes a hung agent's partial transcript out precisely so it can
    score. Discarding it drops the task from comparable() and shrinks the
    denominator for all three roles, not just the one that hung."""
    run = _run(tmp_path)
    specs = (
        _spec(tmp_path, "weak_baseline", TOOLLESS),
        _spec(tmp_path, "under_test", SLOW_BUT_CORRECT, timeout_sec=2.0),
        _spec(tmp_path, "oracle", COMPETENT),
    )
    report, findings = smoke_run(run, specs)
    result = next(r for r in report["tasks"][0]["results"] if r["role"] == "under_test")
    assert result["scored"] is True and result["reward"] == 1.0
    assert "timed out" in result["notes"]
    assert report["summary"]["unscoreable"] == 0
    assert report["summary"]["mean_reward_by_role"]["oracle"] == 1.0  # denominator intact
    assert report["verdict"] == "healthy"
    assert any("timed out" in f.message for f in findings)  # gate still speaks up


def test_a_timeout_with_no_reward_is_not_reported_as_having_scored_anyway(tmp_path):
    """A recorded note must never be false.

    The timeout finding says the role "scored anyway on its partial transcript:
    the reward is real, not padded". When the verifier produced no reward, the
    result at that very pointer carries no reward key at all -- so the sentence is
    not a harmless duplicate of the unscoreable finding, it is a false record of a
    score that does not exist. The timeout itself is still reported, in the
    unscoreable finding's note.
    """
    run = _run(tmp_path)
    (run.task_dir(SID) / "tests" / "verify.py").write_text("raise SystemExit(9)\n", "utf-8")
    specs = (
        _spec(tmp_path, "weak_baseline", TOOLLESS),
        _spec(tmp_path, "under_test", SLOW_BUT_CORRECT, timeout_sec=2.0),
        _spec(tmp_path, "oracle", COMPETENT),
    )
    report, findings = smoke_run(run, specs)
    results = report["tasks"][0]["results"]
    index = next(i for i, r in enumerate(results) if r["role"] == "under_test")
    assert results[index]["scored"] is False
    assert "reward" not in results[index]
    assert "timed out" in results[index]["notes"]

    pointer = f"/tasks/0/results/{index}"
    at_pointer = [f for f in findings if f.pointer == pointer]
    assert at_pointer, "the unscoreable result must still be reported"
    assert not any("the reward is real" in f.message for f in at_pointer), (
        "a result with no reward key must not be described as having scored anyway"
    )
    assert any("timed out" in f.message for f in at_pointer), "the timeout must still be recorded"


def test_a_role_whose_log_directory_cannot_be_cleared_is_unscoreable_not_timed_out(tmp_path):
    """A previous attempt's transcript must never be scored as this attempt's.

    run_agent clears the agent log directory of everything verify.py reads back,
    and fails closed when it cannot: the command is not launched and the result is
    unscoreable. A subdirectory named *.jsonl is the unremovable entry here -- the
    same shape verify.py's own _read_logs raises on. It must not be reported as a
    timeout, because nothing timed out.
    """
    run = _run(tmp_path)
    logs = run.smoke_dir("under_test", SID) / "agent"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "blocking.jsonl").mkdir()

    report, findings = smoke_run(run, _roster(tmp_path))
    results = {r["role"]: r for r in report["tasks"][0]["results"]}
    assert results["under_test"]["scored"] is False
    assert "reward" not in results["under_test"]
    assert "could not clear the agent log directory" in results["under_test"]["notes"]
    assert report["summary"]["unscoreable"] == 1
    assert not any("timed out" in f.message for f in findings), "nothing timed out"
    assert any("under_test" in f.message for f in findings)


def test_a_discarded_verifier_score_is_recorded_where_an_operator_would_find_it(tmp_path):
    """verify.py cannot see the crash, so a real reward.json sits next to the report.

    Without the note, an operator reading measurement/smoke/<role>/<sid>/verifier/
    would find a score the report says does not exist and nothing on disk
    explaining the mismatch.
    """
    run = _run(tmp_path)
    report, _ = smoke_run(run, _roster(tmp_path, under=CRASHER))
    result = next(r for r in report["tasks"][0]["results"] if r["role"] == "under_test")
    assert result["scored"] is False

    on_disk = read_json(run.smoke_dir("under_test", SID) / "verifier" / "reward.json")
    assert "discarded" in result["notes"]
    assert str(on_disk["reward"]) in result["notes"], "the note must name the score it discarded"
    assert "agent exited 7" in result["notes"], "and why it was discarded"


def test_a_roster_without_the_oracle_is_a_finding_and_still_reports(tmp_path):
    run = _run(tmp_path)
    specs = tuple(s for s in _roster(tmp_path) if s.role != "oracle")
    report, findings = smoke_run(run, specs)
    assert report is not None, "the data is still worth having"
    assert report["verdict"] == "inconclusive"
    assert any("oracle" in f.message for f in findings)


def test_a_suite_with_no_packages_writes_no_report(tmp_path):
    """report-0.1.json sets tasks minItems 1 on purpose.

    A report over no tasks with verdict healthy would validate clean and claim a
    successful smoke over a suite nobody ran, so there is nothing valid to write.
    """
    run = build_state(tmp_path / "run", "challenge")  # emit has not run
    report, findings = smoke_run(run, _roster(tmp_path))
    assert report is None
    assert not run.report.exists()
    assert len(findings) == 1
    assert "no emitted packages" in findings[0].message


def test_the_logs_land_where_the_layout_says(tmp_path):
    run = _run(tmp_path)
    smoke_run(run, _roster(tmp_path))
    base = run.smoke_dir("oracle", SID)
    assert (base / "agent" / "agent-stdout.jsonl").is_file()
    assert (base / "agent-stderr.txt").is_file()
    assert (base / "verifier" / "reward.json").is_file()
    assert (base / "verifier" / "reward.txt").is_file()
    assert (base / "verifier-stderr.txt").is_file()
    assert not list((base / "agent").glob("*.txt")), "stderr must never be transcript input"


def test_rerunning_smoke_overwrites_rather_than_accumulating(tmp_path):
    """Two runs of the same suite must produce one report, not a merged one."""
    run = _run(tmp_path)
    smoke_run(run, _roster(tmp_path))
    report, _ = smoke_run(run, _roster(tmp_path))
    assert len(report["tasks"]) == 1
    assert len(report["tasks"][0]["results"]) == len(ROLES)


def test_a_real_smoke_run_leaves_layer_two_clean(tmp_path):
    """The seam between the producer and the checker, proved rather than assumed.

    Both sides recompute the summary with the same functions, so this can only
    fail if smoke writes something summarize did not produce.
    """
    from testgen.refs import check_all

    run = _run(tmp_path)
    smoke_run(run, _roster(tmp_path))
    assert check_all(run) == []
