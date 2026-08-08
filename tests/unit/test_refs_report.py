"""refs.check_report: the report against the suite it claims to have run.

check_all had no report checker, so a report could list a scenario whose
emit had pruned and both gates stayed green. The hard part is that the *same*
shape on disk is legitimate when the scenario was rejected after smoke ran --
which is a state the design spec's reject path prescribes, and the record the
honest-hole report is built from. Status is the distinguisher.
"""

from __future__ import annotations

import pytest

from testgen.artifacts import read_json, write_json
from testgen.refs import check_all, check_report
from tests.builders import minimal_scenarios
from tests.unit.test_refs_states import build_state

SID = "scn-001"


def _smoked(tmp_path):
    """A run through smoke: one emitted package and a report over it."""
    return build_state(tmp_path, "smoke")


def _report(run, **over):
    payload = read_json(run.report)
    payload.update(over)
    write_json(run.report, payload)
    return payload


def test_a_consistent_report_is_clean(tmp_path):
    assert check_report(_smoked(tmp_path)) == []


def test_no_report_is_not_a_finding(tmp_path):
    """Every state before smoke. check_all runs in all of them."""
    assert check_report(build_state(tmp_path, "emit")) == []


def test_a_report_naming_a_scenario_that_was_never_proposed_is_reported(tmp_path):
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    payload["tasks"][0]["scenario_id"] = "scn-ghost"
    write_json(run.report, payload)
    assert any("scn-ghost" in f.message for f in check_report(run))


def test_an_active_scenario_with_no_package_is_reported(tmp_path):
    """The carried-forward defect. A report over a suite nobody emitted."""
    import shutil

    run = _smoked(tmp_path)
    shutil.rmtree(run.task_dir(SID))
    findings = check_report(run)
    assert len(findings) == 1
    assert "has no emitted package" in findings[0].message


def test_a_rejected_scenario_with_no_package_is_tolerated(tmp_path):
    """The legitimate half of the same shape.

    challenge marks a scenario rejected after smoke has run and emit prunes its
    package. Reporting that would make check-refs permanently dirty in a state
    the spec prescribes, and would push someone to delete the rejection record
    the honest-hole report is built from.
    """
    import shutil

    run = _smoked(tmp_path)
    scenarios = minimal_scenarios()
    scenarios["scenarios"][0]["status"] = "rejected"
    scenarios["scenarios"][0]["rejected_reason"] = "ambiguous"
    write_json(run.scenarios, scenarios)
    shutil.rmtree(run.task_dir(SID))
    assert check_report(run) == []


def test_a_proposed_scenario_in_the_report_is_reported(tmp_path):
    """`proposed` is not judged. A suite emitted from an unscored scenario
    bypassed the gate that decides what is worth instantiating."""
    run = _smoked(tmp_path)
    scenarios = minimal_scenarios()
    scenarios["scenarios"][0]["status"] = "proposed"
    write_json(run.scenarios, scenarios)
    assert any("proposed" in f.message for f in check_report(run))


def test_an_emitted_package_the_report_never_ran_is_reported(tmp_path):
    """The other direction, and it is never legitimate.

    A package in 06-suite/ that no report entry mentions has not been smoked, so
    the suite ships a task nothing has ever executed.
    """
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    payload["tasks"] = []
    write_json(run.report, payload)
    assert any("was never run" in f.message for f in check_report(run))


def test_a_duplicated_task_entry_is_reported(tmp_path):
    """Two entries for one scenario double its weight in every mean."""
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    payload["tasks"].append(dict(payload["tasks"][0]))
    write_json(run.report, payload)
    assert any("more than once" in f.message for f in check_report(run))


def test_a_run_id_that_does_not_match_the_manifest_is_reported(tmp_path):
    """A report filed against the wrong run is worse than no report."""
    run = _smoked(tmp_path)
    _report(run, run_id="run-19990101-000000")
    assert any("run_id" in f.pointer for f in check_report(run))


def test_a_declared_role_missing_from_a_task_is_reported(tmp_path):
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    payload["tasks"][0]["results"] = [
        r for r in payload["tasks"][0]["results"] if r["role"] != "oracle"
    ]
    write_json(run.report, payload)
    assert any("oracle" in f.message for f in check_report(run))


def test_a_roster_without_a_required_role_is_reported(tmp_path):
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    payload["agents"] = [a for a in payload["agents"] if a["role"] != "weak_baseline"]
    for task in payload["tasks"]:
        task["results"] = [r for r in task["results"] if r["role"] != "weak_baseline"]
    write_json(run.report, payload)
    assert any("weak_baseline" in f.message for f in check_report(run))


@pytest.mark.parametrize(
    "field,value",
    [
        ("all_pass_tasks", 3),
        ("all_fail_tasks", 3),
        ("oracle_failures", 3),
        ("unscoreable", 3),
    ],
)
def test_a_summary_count_that_does_not_match_the_results_is_reported(tmp_path, field, value):
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    payload["summary"][field] = value
    write_json(run.report, payload)
    findings = check_report(run)
    assert any(field in f.pointer for f in findings), [f.pointer for f in findings]


def test_a_mean_that_does_not_match_the_results_is_reported(tmp_path):
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    payload["summary"]["mean_reward_by_role"]["under_test"] = 0.99
    write_json(run.report, payload)
    assert any("mean_reward_by_role" in f.pointer for f in check_report(run))


def test_a_task_flag_that_does_not_match_its_results_is_reported(tmp_path):
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    payload["tasks"][0]["all_pass"] = True
    write_json(run.report, payload)
    assert any("all_pass" in f.pointer for f in check_report(run))


def test_a_verdict_that_does_not_match_the_data_is_reported(tmp_path):
    """The headline is the number a human reads first, so it is recomputed.

    A report claiming `healthy` over data that says `broken_labels` is the single
    most expensive thing this file can let through.
    """
    run = _smoked(tmp_path)
    _report(run, verdict="broken_labels")
    findings = check_report(run)
    assert any(f.pointer == "/verdict" for f in findings)
    assert any("healthy" in f.message for f in findings)


def test_check_all_runs_the_report_check(tmp_path):
    run = _smoked(tmp_path)
    _report(run, verdict="degenerate_trivial")
    assert any(f.pointer == "/verdict" for f in check_all(run))


def test_the_recomputation_uses_the_producers_own_functions(tmp_path):
    """Guards the seam, not the arithmetic.

    A second implementation of summarize in refs would pass every test above and
    drift the first time a threshold moved. This asserts the checker is reading
    the same constants the writer used.
    """
    from testgen import smoke

    run = _smoked(tmp_path)
    original = smoke.PASS_THRESHOLD
    try:
        smoke.PASS_THRESHOLD = 0.5  # under_test scored 0.8 -> now an all_pass task
        assert check_report(run) != []
    finally:
        smoke.PASS_THRESHOLD = original
    assert check_report(run) == []
