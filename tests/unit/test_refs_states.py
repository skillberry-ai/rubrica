"""check_all must be clean on every internally-consistent partial run.

refs.check_all runs after *every* stage, so it sees the run directory in each
of the states the pipeline passes through. An artifact a later stage has not
written yet is not a finding -- that absence is validate.validate_stage's
business. A finding raised in a state where nothing is wrong costs the
orchestrator its one bounded repair attempt on a phantom, which is exactly
the defect this file exists to prevent from returning.

Each state below is cumulative: STATES[n] applies every builder up to and
including index n, so the run directory grows the way a real run does. Every
state is assembled from tests/builders.py, whose payloads are mutually
consistent, so no finding is legitimately warranted in any of them.

Not every state adds a file. The last one, `post-rejection`, *rewrites*
02-scenarios.json and 03-coverage/latest.json to the state the design spec's
reject path prescribes, and emit prunes a package rather than writing one. A
state is any run directory the pipeline legitimately passes through, not only a
growing one.

**When you add a stage, add its state here.** Append a (name, builder) pair
in pipeline order; the parametrization picks it up and the failure message
names the state that broke.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from testgen.artifacts import read_json, write_json
from testgen.emit import emit_run
from testgen.paths import RunPaths
from testgen.refs import check_all
from tests.builders import (
    MINIMAL_INPUT_BYTES,
    MINIMAL_INPUT_NAME,
    minimal_claims,
    minimal_coverage,
    minimal_expected,
    minimal_manifest,
    minimal_report,
    minimal_scenarios,
    minimal_seed,
    minimal_verdict,
    minimal_world_model,
)

SID = "scn-001"


def _intake(run: RunPaths) -> None:
    """The manifest plus the registered copy whose digest it records.

    Writing the manifest alone was a fiction: intake copies every input into
    00-inputs/ and hashes it, and refs.check_inputs re-verifies that. The
    builder's sha256 is the digest of MINIMAL_INPUT_BYTES, so this state
    satisfies the check by construction -- if it needed a tolerance in
    check_inputs to pass, the check would not be worth having.
    """
    write_json(run.manifest, minimal_manifest())
    run.inputs_dir.mkdir(parents=True, exist_ok=True)
    run.input_file(MINIMAL_INPUT_NAME).write_bytes(MINIMAL_INPUT_BYTES)


def _extract(run: RunPaths) -> None:
    write_json(run.claims("aap2-api"), minimal_claims())


def _reconcile(run: RunPaths) -> None:
    write_json(run.world_model, minimal_world_model())


def _propose(run: RunPaths) -> None:
    write_json(run.scenarios, minimal_scenarios())


def _score(run: RunPaths) -> None:
    write_json(run.coverage_latest, minimal_coverage())


def _instantiate(run: RunPaths) -> None:
    write_json(run.seed(SID), minimal_seed())
    write_json(run.expected(SID), minimal_expected())


def _challenge(run: RunPaths) -> None:
    write_json(run.verdict(SID), minimal_verdict())


def _emit(run: RunPaths) -> None:
    emitted, findings = emit_run(run)
    assert (emitted, findings) == ([SID], []), f"emit failed in the states table: {findings}"


def _smoke(run: RunPaths) -> None:
    write_json(run.report, minimal_report())


# The reopened cell, justified as an honest hole. `not_yet_attempted` is the
# schema's vocabulary for "no accepted scenario exercises this"; the
# justification names the rejection, which is the record §362's report is
# built from.
REOPENED_HOLE = {
    "ref": "cell:cap-find-jobs/oc-success",
    "reason": "not_yet_attempted",
    "justification": (
        "scn-001 claimed this cell and challenge rejected it as ambiguous, so no accepted "
        "scenario exercises it; the cell is uncovered again"
    ),
}


def _post_rejection(run: RunPaths) -> None:
    """challenge rejected scn-001 after it was instantiated, judged, and emitted.

    The design spec's reject path: mark the scenario `rejected` in
    02-scenarios.json, recompute coverage so the cell it claimed is uncovered
    again and carries an honest hole, and re-run emit. The instance, the verdict
    and the coverage record all stay -- they are what the report's "87%, 3 cells
    lost to rejected scenarios" is built from.

    check_all must be clean here. It was not: check_instances and check_suite
    both required `active`, so check-refs went permanently dirty in a state the
    pipeline prescribes and no repair the orchestrator dispatched could clear it.
    And emit only replaced the package it was about to rewrite, so the package
    for the rejected scenario stayed under 06-suite/ and would have shipped to
    Harbor and been scored.
    """
    scenarios = minimal_scenarios()
    scenarios["scenarios"][0]["status"] = "rejected"
    scenarios["scenarios"][0]["rejected_reason"] = "ambiguous"
    write_json(run.scenarios, scenarios)

    coverage = minimal_coverage()
    cell = coverage["capability_matrix"]["cells"][0]
    cell["scenario_ids"] = []
    cell["covered"] = False
    coverage["capability_matrix"]["covered"] = 0
    coverage["capability_matrix"]["pct"] = 0.0
    row = coverage["goal_matrix"]["rows"][0]
    row["scenario_ids"] = []
    row["hop_depths_present"] = []
    coverage["holes"].insert(0, dict(REOPENED_HOLE))
    coverage["progress"] = {"new_cells_this_round": 0, "rounds_without_progress": 1}
    write_json(run.coverage_latest, coverage)

    emitted, findings = emit_run(run)
    assert (emitted, findings) == ([], []), f"emit after a rejection: {findings}"
    assert not run.task_dir(SID).exists(), "emit must prune the rejected scenario's package"


# Pipeline order. Cumulative: each state is every builder up to and including
# its own. "empty" carries no builder -- a run directory that exists and
# holds nothing is the state check_all sees before intake writes anything.
STATES: list[tuple[str, Callable[[RunPaths], None] | None]] = [
    ("empty", None),
    ("intake", _intake),
    ("extract", _extract),
    ("reconcile", _reconcile),
    ("propose", _propose),
    ("score", _score),
    ("instantiate", _instantiate),
    ("challenge", _challenge),
    ("emit", _emit),
    ("smoke", _smoke),
    ("post-rejection", _post_rejection),
]

STATE_NAMES = [name for name, _ in STATES]


def build_state(root: Path, name: str) -> RunPaths:
    """Populate `root` up to and including the named pipeline state."""
    run = RunPaths(root)
    run.root.mkdir(parents=True, exist_ok=True)
    for state_name, builder in STATES:
        if builder is not None:
            builder(run)
        if state_name == name:
            return run
    raise AssertionError(f"no such pipeline state: {name!r}")


@pytest.mark.parametrize("state", STATE_NAMES)
def test_check_all_is_clean_in_every_valid_partial_state(tmp_path, state):
    run = build_state(tmp_path, state)
    assert check_all(run) == []


def test_the_states_are_cumulative_so_the_last_one_is_a_complete_run(tmp_path):
    """Guards the table itself: the final state must really hold every artifact.

    Without this, dropping a builder from STATES would silently narrow every
    test above into a check of a smaller run than it claims to cover.
    """
    run = build_state(tmp_path, STATE_NAMES[-1])
    assert run.manifest.is_file()
    assert run.input_file(MINIMAL_INPUT_NAME).is_file()
    assert run.claims("aap2-api").is_file()
    assert run.world_model.is_file()
    assert run.scenarios.is_file()
    assert run.coverage_latest.is_file()
    assert run.seed(SID).is_file()
    assert run.expected(SID).is_file()
    assert run.verdict(SID).is_file()
    assert run.report.is_file()
    # 06-suite/<sid> is deliberately *absent* in the last state: it rejects
    # scn-001, and emit prunes the package for a scenario that no longer
    # qualifies. test_the_emit_state_really_wrote_a_package below is what
    # guarantees there was a package to prune.
    assert not run.task_dir(SID).exists()
    # The rejection is recorded rather than erased. That record is what the
    # honest-hole report ("87%, 3 cells lost to rejected scenarios") is built
    # from, and it is the reason layer 2 admits `rejected` under 04/05/06.
    scenario = read_json(run.scenarios)["scenarios"][0]
    assert scenario["status"] == "rejected"
    assert scenario["rejected_reason"]
    holes = read_json(run.coverage_latest)["holes"]
    assert any(hole["ref"] == REOPENED_HOLE["ref"] for hole in holes)


def test_the_emit_state_really_wrote_a_package(tmp_path):
    """The other half of the prune assertion above.

    Without this, the last state's `not task_dir().exists()` would pass just as
    happily over a package emit never wrote at all.
    """
    run = build_state(tmp_path, "emit")
    assert (run.task_dir(SID) / "tests" / "expected.json").is_file()


def test_the_post_rejection_state_still_holds_the_instance_and_the_verdict(tmp_path):
    """Pins the shape of the state, not just its cleanliness.

    A "fix" that swept 04-instances/ and 05-verdicts/ clean on rejection would
    also make check_all clean here, and would destroy the artifact record the
    report is built from.
    """
    run = build_state(tmp_path, "post-rejection")
    assert run.scenario_ids_with_instances() == [SID]
    assert run.verdict(SID).is_file()
    assert run.scenario_ids_with_tasks() == []


def test_the_non_recomputed_post_rejection_state_is_reported(tmp_path):
    """Pins the *incorrect* variant of the state above -- the one nothing pinned.

    _post_rejection recomputes coverage by hand, so the table proves only the
    correct variant clean; every value it writes into 03-coverage/latest.json
    could have reached no behaviour at all and the suite would look identical.
    This is the same state with §361's "recompute coverage" skipped: the scenario
    is marked rejected in 02 and latest.json is left alone. check_all returned
    zero findings there, and so did `validate --stage score`, while latest.json
    reported pct 0.5 with the cell covered by the scenario the adversary threw
    out -- coverage credited to a discarded scenario with both gates green.

    Exactly one finding, so the assertion also proves nothing *else* fires: the
    instance, the verdict and the package all legitimately survive a rejection.
    """
    run = build_state(tmp_path, "smoke")
    assert check_all(run) == [], "the baseline this state is measured against"

    scenarios = minimal_scenarios()
    scenarios["scenarios"][0]["status"] = "rejected"
    scenarios["scenarios"][0]["rejected_reason"] = "ambiguous"
    write_json(run.scenarios, scenarios)

    findings = check_all(run)
    assert [f.pointer for f in findings] == ["/capability_matrix/cells/0"]
    assert "recompute coverage" in findings[0].message, "the finding must say what to do"
    assert findings[0].artifact == run.coverage_latest


def test_the_state_before_challenge_has_instances_but_no_verdicts(tmp_path):
    """Pins the shape of the state that regressed, not just its cleanliness."""
    run = build_state(tmp_path, "instantiate")
    assert run.scenario_ids_with_instances() == [SID]
    assert not run.verdicts_dir.exists()
