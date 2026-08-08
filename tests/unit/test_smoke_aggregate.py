"""The arithmetic and the verdict: stage 7's pure half.

Nothing here touches a subprocess. The thresholds are named constants because
refs.check_report recomputes every one of these numbers by calling these same
functions -- a second implementation of the arithmetic is the seam defect this
project keeps finding, so there is exactly one.
"""

from __future__ import annotations

import pytest

from testgen.smoke import (
    FAIL_CEILING,
    ORACLE_FLOOR,
    PASS_THRESHOLD,
    ROLES,
    WEAK_BASELINE_CEILING,
    comparable,
    components,
    mean_reward_by_role,
    summarize,
    task_flags,
    verdict_for,
)


def _result(role, reward=None):
    if reward is None:
        return {"role": role, "scored": False}
    return {
        "role": role,
        "scored": True,
        "reward": reward,
        "completion": 1.0,
        "assertions": reward,
        "trajectory": reward,
    }


def _task(sid, **by_role):
    return {"scenario_id": sid, "results": [_result(r, by_role.get(r)) for r in ROLES]}


def _spread(sid):
    return _task(sid, weak_baseline=0.0, under_test=0.8, oracle=1.0)


# -- comparable ---------------------------------------------------------------


def test_a_task_every_role_scored_is_comparable():
    assert comparable(_spread("s1"), ROLES) is True


def test_a_task_one_role_could_not_score_is_not_comparable():
    task = _task("s1", weak_baseline=0.0, under_test=0.8)  # oracle unscoreable
    assert comparable(task, ROLES) is False


# -- task_flags ---------------------------------------------------------------


def test_all_pass_fires_only_when_every_role_passes():
    assert task_flags(_task("s", weak_baseline=1.0, under_test=1.0, oracle=1.0), ROLES) == (
        True,
        False,
    )


def test_all_fail_fires_only_when_every_role_fails():
    assert task_flags(_task("s", weak_baseline=0.0, under_test=0.0, oracle=0.0), ROLES) == (
        False,
        True,
    )


def test_a_real_spread_is_neither():
    assert task_flags(_spread("s"), ROLES) == (False, False)


def test_an_unscoreable_task_is_neither_all_pass_nor_all_fail():
    """The ruling. Counting a missing score as a failure would report a task
    nobody managed to run as a hard one -- and a suite of them as well-designed."""
    task = _task("s", weak_baseline=0.0, under_test=0.0)  # oracle unscoreable
    assert task_flags(task, ROLES) == (False, False)


def test_a_task_with_no_declared_roles_is_neither_all_pass_nor_all_fail():
    """all([]) is True, so an empty reward list would claim both at once.

    Reachable through refs.check_report, which reads a report layer 1 has not
    gated: `agents: []` gives an empty `roles`, comparable() answers True
    vacuously, and without the guard the checker would report that every role
    both passed and failed the same task.
    """
    assert task_flags({"scenario_id": "s", "results": []}, ()) == (False, False)


def test_the_thresholds_absorb_float_slack_and_nothing_more():
    """0.8 * 1.0 + 0.2 * 1.0 is not exactly 1.0 for every weight pair."""
    assert task_flags(_task("s", **dict.fromkeys(ROLES, 0.9999)), ROLES) == (True, False)
    assert task_flags(_task("s", **dict.fromkeys(ROLES, 0.0001)), ROLES) == (False, True)
    assert task_flags(_task("s", **dict.fromkeys(ROLES, 0.99)), ROLES) == (False, False)
    assert PASS_THRESHOLD < 1.0 and FAIL_CEILING > 0.0


# -- mean_reward_by_role -----------------------------------------------------


def test_the_mean_is_taken_over_comparable_tasks_only():
    """The ragged-denominator ruling.

    Task s2 is unscoreable for the oracle. Averaging weak_baseline over both
    tasks and oracle over one compares a role's score on everything against
    another's on the subset it survived -- which flatters the role that failed.
    """
    tasks = [
        _task("s1", weak_baseline=0.0, under_test=0.5, oracle=1.0),
        _task("s2", weak_baseline=1.0, under_test=1.0),
    ]
    means = mean_reward_by_role(tasks, ROLES)
    assert means == {"weak_baseline": 0.0, "under_test": 0.5, "oracle": 1.0}


def test_a_role_with_no_comparable_task_is_omitted_not_zeroed():
    """0.0 would read as "scored zero" rather than "never measured"."""
    tasks = [_task("s1", weak_baseline=0.0, under_test=0.5)]
    assert mean_reward_by_role(tasks, ROLES) == {}


def test_a_role_absent_from_the_roster_is_not_invented():
    tasks = [
        {
            "scenario_id": "s1",
            "results": [_result("weak_baseline", 0.0), _result("under_test", 1.0)],
        }
    ]
    means = mean_reward_by_role(tasks, ("weak_baseline", "under_test"))
    assert set(means) == {"weak_baseline", "under_test"}


# -- summarize ---------------------------------------------------------------


def test_the_summary_counts_what_the_schema_requires():
    tasks = [_spread("s1"), _task("s2", weak_baseline=1.0, under_test=1.0, oracle=1.0)]
    summary = summarize(tasks, ROLES)
    assert summary["all_pass_tasks"] == 1
    assert summary["all_fail_tasks"] == 0
    assert summary["oracle_failures"] == 0
    assert summary["unscoreable"] == 0
    assert set(summary) == {
        "mean_reward_by_role",
        "all_pass_tasks",
        "all_fail_tasks",
        "oracle_failures",
        "unscoreable",
    }


def test_an_unscoreable_oracle_counts_as_an_oracle_failure():
    """A verifier that refused the contract is as much a signal that the suite is
    broken as an oracle that answered wrongly. Both indict the suite, not the
    agent, which is the only thing oracle_failures is for."""
    summary = summarize([_task("s1", weak_baseline=0.0, under_test=0.8)], ROLES)
    assert summary["oracle_failures"] == 1
    assert summary["unscoreable"] == 1


def test_a_low_scoring_oracle_counts_as_an_oracle_failure():
    summary = summarize([_task("s1", weak_baseline=0.0, under_test=0.8, oracle=0.5)], ROLES)
    assert summary["oracle_failures"] == 1


# -- verdict_for -------------------------------------------------------------


def _verdict(tasks, roles=ROLES):
    return verdict_for(tasks, summarize(tasks, roles), roles)


def test_a_real_spread_is_healthy():
    assert _verdict([_spread("s1")]) == "healthy"


def test_a_weak_baseline_that_passes_too_much_is_degenerate():
    assert _verdict([_task("s1", weak_baseline=1.0, under_test=1.0, oracle=1.0)]) == (
        "degenerate_trivial"
    )


def test_an_oracle_that_fails_too_much_indicts_the_labels():
    assert _verdict([_task("s1", weak_baseline=0.0, under_test=0.0, oracle=0.0)]) == (
        "broken_labels"
    )


def test_broken_labels_outranks_degenerate_trivial():
    """The precedence, and the reason for it.

    If the oracle cannot pass its own reference answers, nothing the weak
    baseline scored means anything yet -- the scoring path is what is broken.
    Reporting degenerate_trivial first would send someone to rewrite scenarios.
    """
    tasks = [_task("s1", weak_baseline=1.0, under_test=1.0, oracle=0.0)]
    assert _verdict(tasks) == "broken_labels"


def test_no_comparable_task_is_inconclusive():
    assert _verdict([_task("s1", weak_baseline=0.0, under_test=0.8)]) == "inconclusive"


def test_a_roster_without_the_oracle_cannot_be_healthy():
    """Even when every score looks perfect.

    The oracle is the test of the test suite. Without it there is nothing to rule
    out broken labels, so `healthy` would be a claim the run did not earn.
    """
    roles = ("weak_baseline", "under_test")
    tasks = [
        {
            "scenario_id": "s1",
            "results": [_result("weak_baseline", 0.0), _result("under_test", 1.0)],
        }
    ]
    assert verdict_for(tasks, summarize(tasks, roles), roles) == "inconclusive"


def test_the_thresholds_are_the_documented_ones():
    """Pins the numbers, so changing one is a deliberate edit with a failing test."""
    assert (WEAK_BASELINE_CEILING, ORACLE_FLOOR) == (0.30, 0.80)


# -- components --------------------------------------------------------------


@pytest.mark.parametrize(
    "reward",
    [
        {"reward": 1.5, "completion": 1.0, "assertions": 1.0, "trajectory": 1.0},
        {"reward": -0.1, "completion": 1.0, "assertions": 1.0, "trajectory": 1.0},
        {"reward": "1.0", "completion": 1.0, "assertions": 1.0, "trajectory": 1.0},
        {"reward": True, "completion": 1.0, "assertions": 1.0, "trajectory": 1.0},
        {"reward": float("nan"), "completion": 1.0, "assertions": 1.0, "trajectory": 1.0},
        {"reward": 1.0, "completion": 1.0, "assertions": 1.0},
    ],
)
def test_an_out_of_range_reward_is_rejected_rather_than_written(reward):
    """report-0.1.json bounds every one of these to [0, 1].

    Writing an out-of-range value would make `validate --stage smoke` fail on an
    artifact smoke itself produced -- a stage defect wearing a layer-1 error's
    clothes, and the orchestrator would retry the stage that is not at fault.
    """
    assert components(reward) is None


def test_a_well_formed_reward_is_accepted():
    assert components({"reward": 0.8, "completion": 1, "assertions": 1.0, "trajectory": 0.0}) == {
        "reward": 0.8,
        "completion": 1.0,
        "assertions": 1.0,
        "trajectory": 0.0,
    }
