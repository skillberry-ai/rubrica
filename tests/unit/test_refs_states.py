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

**When you add a stage, add its state here.** Append a (name, builder) pair
in pipeline order; the parametrization picks it up and the failure message
names the state that broke.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from testgen.artifacts import write_json
from testgen.paths import RunPaths
from testgen.refs import check_all
from tests.builders import (
    minimal_claims,
    minimal_coverage,
    minimal_expected,
    minimal_manifest,
    minimal_scenarios,
    minimal_seed,
    minimal_verdict,
    minimal_world_model,
)

SID = "scn-001"


def _intake(run: RunPaths) -> None:
    write_json(run.manifest, minimal_manifest())


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
    assert run.claims("aap2-api").is_file()
    assert run.world_model.is_file()
    assert run.scenarios.is_file()
    assert run.coverage_latest.is_file()
    assert run.seed(SID).is_file()
    assert run.expected(SID).is_file()
    assert run.verdict(SID).is_file()


def test_the_state_before_challenge_has_instances_but_no_verdicts(tmp_path):
    """Pins the shape of the state that regressed, not just its cleanliness."""
    run = build_state(tmp_path, "instantiate")
    assert run.scenario_ids_with_instances() == [SID]
    assert not run.verdicts_dir.exists()
