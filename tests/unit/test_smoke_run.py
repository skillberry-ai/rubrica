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


def _spec(tmp_path, role, body, name=None):
    script = tmp_path / (name or f"{role}.py")
    script.write_text(body, encoding="utf-8")
    return AgentSpec(
        role=role, model=f"model-{role}", command=(sys.executable, str(script)), timeout_sec=60.0
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
