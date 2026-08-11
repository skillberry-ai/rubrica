"""refs.check_report: the report against the suite it claims to have run.

check_all had no report checker, so a report could list a scenario whose
emit had pruned and both gates stayed green. The hard part is that the *same*
shape on disk is legitimate when the scenario was rejected after smoke ran --
which is a state the design spec's reject path prescribes, and the record the
honest-hole report is built from. Status is the distinguisher.
"""

from __future__ import annotations

import pytest

from rubrica.artifacts import read_json, write_json
from rubrica.refs import check_all, check_report
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
    # Pinned on the pointer, not just the message: with the `scenario is None`
    # branch deleted, this used to still fail -- via an AttributeError at the
    # following elif, which also indexes `scenario`. That crash proved the
    # mutation was detected, not that this test asserts on the branch's own
    # finding. This pointer is unique to this branch for a ghost id.
    assert any(f.pointer == "/tasks/0/scenario_id" for f in check_report(run))


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
    # Pinned on the pointer, not just the message: the seam-recomputation
    # findings (/summary/mean_reward_by_role, /verdict) also incidentally
    # contain the substring "oracle" once its result is stripped -- the former
    # because it repr's the stale declared dict, which still has an "oracle"
    # key. Only this loop emits /tasks/0/results.
    findings = check_report(run)
    assert any(f.pointer == "/tasks/0/results" and "oracle" in f.message for f in findings)


def test_a_roster_without_a_required_role_is_reported(tmp_path):
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    payload["agents"] = [a for a in payload["agents"] if a["role"] != "weak_baseline"]
    for task in payload["tasks"]:
        task["results"] = [r for r in task["results"] if r["role"] != "weak_baseline"]
    write_json(run.report, payload)
    # Pinned on the pointer, not just the message: /summary/mean_reward_by_role
    # also repr's the stale declared dict, which still has a "weak_baseline"
    # key, and /verdict fires too (smoke.verdict_for has its own REQUIRED_ROLES
    # gate). Only this loop emits /agents.
    findings = check_report(run)
    assert any(f.pointer == "/agents" and "weak_baseline" in f.message for f in findings)


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


def test_a_task_with_no_results_is_reported_without_crashing(tmp_path):
    """The precondition check_report disclaims: nothing orders `validate
    --stage smoke` before check-refs, so a report missing a schema-required
    key can legitimately arrive. smoke.comparable indexes `task["results"]`
    directly and would raise KeyError; the guard before the seam turns that
    into a finding naming the one task instead of a traceback naming none."""
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    del payload["tasks"][0]["results"]
    write_json(run.report, payload)
    findings = check_report(run)  # must not raise
    assert any(f.pointer == "/tasks/0/results" for f in findings)


def test_a_result_with_no_role_is_reported_without_crashing(tmp_path):
    """smoke.summarize indexes `result["role"]` for every result, scored or
    not, before it even checks whether the result was scored."""
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    del payload["tasks"][0]["results"][0]["role"]
    write_json(run.report, payload)
    findings = check_report(run)  # must not raise
    assert any(f.pointer == "/tasks/0/results" for f in findings)


def test_a_scored_result_with_no_reward_is_reported_without_crashing(tmp_path):
    """smoke.task_flags and smoke.summarize both index `result["reward"]`
    directly once a result is scored."""
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    del payload["tasks"][0]["results"][0]["reward"]
    write_json(run.report, payload)
    findings = check_report(run)  # must not raise
    assert any(f.pointer == "/tasks/0/results" for f in findings)


def test_a_task_with_no_scenario_id_does_not_crash_the_duplicate_check(tmp_path):
    """`named` can hold None; sorting the raw set used to raise TypeError
    (str vs NoneType) before the ghost-scenario finding for this task could
    even be produced."""
    run = _smoked(tmp_path)
    payload = read_json(run.report)
    second = dict(payload["tasks"][0])
    del second["scenario_id"]
    payload["tasks"].append(second)
    write_json(run.report, payload)
    findings = check_report(run)  # must not raise
    assert any(f.pointer == "/tasks/1/scenario_id" for f in findings)


def test_a_present_report_that_is_not_an_object_is_reported(tmp_path):
    """The tolerance is applied at depth 0 (absent -- see
    test_no_report_is_not_a_finding) and must not be abandoned at depth 2
    (present, but not even an object): both are ungated arrivals, and only the
    first is legitimate."""
    run = _smoked(tmp_path)
    write_json(run.report, ["not", "an", "object"])
    findings = check_report(run)
    assert len(findings) == 1
    assert findings[0].pointer == ""


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
    from rubrica import smoke

    run = _smoked(tmp_path)
    original = smoke.PASS_THRESHOLD
    try:
        smoke.PASS_THRESHOLD = 0.5  # under_test scored 0.8 -> now an all_pass task
        assert check_report(run) != []
    finally:
        smoke.PASS_THRESHOLD = original
    assert check_report(run) == []
