"""Task 17: the suite size a world model implies.

`sizing.implied_size` has two witnesses.
`test_the_parsec_world_model_implies_the_cap_that_was_set_by_hand` is the real
one -- it is the whole reason to believe the formula, because its numbers were
measured on a real target and agreed with a human's instinct before this
module existed. It **skips** on a fresh clone, because `runs/` is gitignored:
that skip is not evidence the formula holds, only evidence nobody has yet
proven it doesn't. `test_the_formula_is_pinned_on_synthetic_numbers` is the
fixture-based companion the brief asks for precisely because the real test
cannot run everywhere -- it guards the arithmetic even when the measurement
can't.
"""

from __future__ import annotations

import math
import shutil
import tempfile
from pathlib import Path

import pytest

from rubrica import sizing
from rubrica.artifacts import read_json, write_json
from rubrica.paths import RunPaths
from tests.toy import build_toy_run

REAL_RUN = RunPaths("runs/run-20260813-204203")


def _world_model_only_copy(run: RunPaths) -> Path:
    """A fresh directory holding only `run`'s manifest and world model.

    No `tmp_path` parameter, deliberately -- this helper mirrors the brief's
    own call shape, `RunPaths(_world_model_only_copy(run))`, so it mints its
    own scratch directory rather than depending on a fixture the brief's
    snippet does not thread through. The manifest is copied alongside the
    world model because `implied_size` reads `limits.max_scenarios` off it
    for `ceiling`; without it, this would be testing a different function.
    Coverage is deliberately absent: this is gate 1's state, before score's
    round 1 exists to say which cells are blocked_by_gap.
    """
    root = Path(tempfile.mkdtemp(prefix="rubrica-sizing-gate1-"))
    copy = RunPaths(root)
    shutil.copy(run.manifest, copy.manifest)
    shutil.copy(run.world_model, copy.world_model)
    return root


def test_the_parsec_world_model_implies_the_cap_that_was_set_by_hand():
    """Measured, not reasoned. From run-20260813-204203:

    28 capability cells + 23 hop-depth slots = 51, against a ~50 floor ruled by
    instinct; 51/0.75 = 68 against the 64 set by hand. Five blocked cells are
    known only after round 1, giving 46 and 62 at gate 2.

    Skips when the reference run is absent (`runs/` is gitignored, so a fresh
    clone never has it) -- a green suite here is then not evidence for the
    claim above; see test_the_formula_is_pinned_on_synthetic_numbers for the
    arithmetic guard that still runs.
    """
    if not REAL_RUN.world_model.is_file():
        pytest.skip(
            "runs/run-20260813-204203 is not present on this machine (runs/ is "
            "gitignored); a green suite without it is not evidence this formula "
            "reproduces the parsec measurement -- only the synthetic companion "
            "test guards the arithmetic here"
        )

    at_gate_1 = sizing.implied_size(RunPaths(_world_model_only_copy(REAL_RUN)))
    assert at_gate_1["capability_cells"] == 28
    assert at_gate_1["hop_slots"] == 23
    assert at_gate_1["denominator"] == 51
    assert at_gate_1["implied"] == 68
    assert at_gate_1["basis"] == "world_model"

    at_gate_2 = sizing.implied_size(REAL_RUN)
    assert at_gate_2["blocked_cells"] == 5
    assert at_gate_2["denominator"] == 46
    assert at_gate_2["implied"] == 62
    assert at_gate_2["basis"] == "world_model+coverage"


def test_the_formula_is_pinned_on_synthetic_numbers(tmp_path):
    """Guards ceil((capability_cells + hop_slots [- blocked_cells]) / 0.75) on
    numbers this test controls, so the formula stays checked even where the
    real run above cannot reach.

    10 capability cells + 3 hop-depth slots (two goals, [1, 2] and [1]) = 13;
    ceil(13 / 0.75) = 18, above a 16-scenario ceiling -- ceiling_binding true,
    the "target wants splitting" diagnostic. Two distinct blocked_by_gap refs
    (a duplicate ref in holes[] must count once) drop the denominator to 11;
    ceil(11 / 0.75) = 15, now under the same ceiling -- ceiling_binding false,
    exercising both directions of that flag from one fixture.
    """
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal", max_scenarios=16)
    world = {
        "schema_version": "0.1",
        "target": {"name": "synthetic", "interface": "mcp"},
        "capabilities": [],
        "entities": [],
        "actors": [],
        "goals": [
            {
                "id": "goal-a",
                "actor_id": "act-a",
                "statement": "a",
                "expected_hop_depths": [1, 2],
                "claims": [],
            },
            {
                "id": "goal-b",
                "actor_id": "act-a",
                "statement": "b",
                "expected_hop_depths": [1],
                "claims": [],
            },
        ],
        "contradictions": [],
        "gaps": [],
        "denominator": {"version": 1, "capability_cells": 10, "goals": 2},
    }
    write_json(run.world_model, world)

    at_gate_1 = sizing.implied_size(run)
    assert at_gate_1["capability_cells"] == 10
    assert at_gate_1["hop_slots"] == 3
    assert at_gate_1["denominator"] == 13
    assert at_gate_1["implied"] == math.ceil(13 / 0.75) == 18
    assert at_gate_1["basis"] == "world_model"
    assert at_gate_1["ceiling"] == 16
    assert at_gate_1["ceiling_binding"] is True

    coverage = {
        "schema_version": "0.1",
        "round": 1,
        "denominator_version": 1,
        "capability_matrix": {"cells": [], "covered": 0, "total": 10, "pct": 0.0},
        "goal_matrix": {"rows": [], "covered": 0, "total": 2, "pct": 0.0},
        "holes": [
            {
                "ref": "cell:cap-a/oc-a",
                "reason": "blocked_by_gap",
                "justification": "no admitted input describes this outcome",
                "gap_id": "gap-a",
            },
            {
                # Same ref twice: a repeated report of the same blocked cell
                # must not be double-counted.
                "ref": "cell:cap-a/oc-a",
                "reason": "blocked_by_gap",
                "justification": "no admitted input describes this outcome",
                "gap_id": "gap-a",
            },
            {
                "ref": "cell:cap-b/oc-b",
                "reason": "blocked_by_gap",
                "justification": "no admitted input describes this outcome",
                "gap_id": "gap-b",
            },
            {
                "ref": "cell:cap-c/oc-c",
                "reason": "not_yet_attempted",
                "justification": "no scenario has targeted this cell yet",
            },
        ],
        "progress": {"new_cells_this_round": 0, "rounds_without_progress": 1},
        "verdict": "continue",
    }
    write_json(run.coverage_latest, coverage)

    at_gate_2 = sizing.implied_size(run)
    assert at_gate_2["blocked_cells"] == 2
    assert at_gate_2["denominator"] == 11
    assert at_gate_2["implied"] == math.ceil(11 / 0.75) == 15
    assert at_gate_2["basis"] == "world_model+coverage"
    assert at_gate_2["ceiling"] == 16
    assert at_gate_2["ceiling_binding"] is False


def test_implied_size_does_not_subtract_unreachable_holes(tmp_path):
    """The one arithmetic trap the narrowed denominator opens. `implied_size`
    subtracts `blocked_by_gap` holes from the denominator, and score-seal now
    writes an `unreachable` hole for every undrivable cell -- but those cells are
    ALREADY outside `denominator.capability_cells`, so subtracting them here too
    would under-report the implied size twice over.

    Pinned on numbers this test controls, the way
    test_the_formula_is_pinned_on_synthetic_numbers above is, and built the same
    way rather than through a second builder.
    """
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal", max_scenarios=16)
    write_json(
        run.world_model,
        {
            "schema_version": "0.1",
            "target": {"name": "synthetic", "interface": "mcp"},
            "capabilities": [],
            "entities": [],
            "actors": [],
            "goals": [
                {
                    "id": "goal-a",
                    "actor_id": "act-a",
                    "statement": "a",
                    "expected_hop_depths": [1, 2],
                    "claims": [],
                },
            ],
            "contradictions": [],
            "gaps": [],
            # Already narrowed to the drivable cells by the seal, which is exactly
            # why the unreachable hole below must not be subtracted again.
            "denominator": {"version": 1, "capability_cells": 10, "goals": 1},
        },
    )
    write_json(
        run.coverage_latest,
        {
            "schema_version": "0.1",
            "round": 1,
            "denominator_version": 1,
            "capability_matrix": {"cells": [], "covered": 0, "total": 10, "pct": 0.0},
            "goal_matrix": {"rows": [], "covered": 0, "total": 1, "pct": 0.0},
            "holes": [
                {
                    "ref": "cell:cap-unbound/oc-ok",
                    "reason": "unreachable",
                    "justification": "no binding.tool",
                },
                {
                    "ref": "cell:cap-bound/oc-gap",
                    "reason": "blocked_by_gap",
                    "justification": "world model lacks it",
                    "gap_id": "gap-1",
                },
            ],
            "progress": {"new_cells_this_round": 0, "rounds_without_progress": 1},
            "verdict": "continue",
        },
    )

    size = sizing.implied_size(run)

    # One blocked cell subtracted, the unreachable one ignored: 10 + 2 - 1 = 11.
    assert size["blocked_cells"] == 1
    assert size["denominator"] == 11


def test_implied_size_is_none_before_a_world_model_exists(tmp_path):
    """A run stopped at extract legitimately has no world model yet; this is
    the same absence-is-not-a-defect ruling claim_utilisation already makes,
    and `gate-brief` depends on this returning cleanly rather than raising."""
    run = build_toy_run(tmp_path / "runs", upto="extract")
    assert sizing.implied_size(run) is None


def test_implied_size_is_none_on_a_present_but_malformed_world_model(tmp_path):
    """A world model that exists but is not valid JSON is a repairable stage
    defect (validate's finding to raise, not this diagnostic's) -- guards the
    review finding that `read_json`'s ArtifactError reached gate-brief
    unguarded and turned a report into exit 2."""
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    run.world_model.write_text("{not valid json", encoding="utf-8")
    assert sizing.implied_size(run) is None


def test_implied_size_is_none_when_denominator_is_missing(tmp_path):
    """A schema-shaped document with no `denominator` key at all raises
    KeyError out of `world["denominator"]["capability_cells"]` -- a malformed
    artifact, not this function's to surface as an exception."""
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    world = read_json(run.world_model)
    del world["denominator"]
    write_json(run.world_model, world)
    assert sizing.implied_size(run) is None
