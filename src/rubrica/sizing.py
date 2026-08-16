"""Suite size implied by the world model's denominator -- a diagnostic, not a cap.

`max_scenarios` (paths.py, cli.py) is a safety ceiling: the point past which no
human reviews the output. It says nothing about whether *this* target's world
model wants twelve scenarios or sixty. This module derives a second
number from the world model itself -- capability cells plus expected hop-depth
slots, divided by one run's measured acceptance rate -- and nothing acts on it.
`gate-brief` reports it at gates 1 and 2 for a human deciding whether the suite
under construction is the right size, in both directions: implied size above
the ceiling means the target wants splitting across runs; a suite that halts
far below the implied size is the signal that score's stopping rule (F1) gave
up early.

Measured against run-20260813-204203 (see tests/unit/test_sizing.py, which
skips on a fresh clone because `runs/` is gitignored -- that skip is not
evidence the formula holds; the fixture-based test alongside it is): 28
capability cells + 23 hop-depth slots = 51 against a ~50 floor set by
instinct, 68 implied against the 64 ceiling set by hand. After round 1's five
`blocked_by_gap` cells, 46 and 62.
"""

from __future__ import annotations

import math

from rubrica.artifacts import read_json
from rubrica.paths import RunPaths

# The 2026-08-13 development run's measured acceptance rate: 23 of 30
# instantiated scenarios accepted at challenge. One run's constant, labelled as
# one rather than a law: it is a single sample from a single corpus, and nothing
# establishes that a different target accepts at the same rate.
ACCEPTANCE_ALLOWANCE = 0.75


def implied_size(run: RunPaths) -> dict | None:
    """The suite size this run's world model implies, or None if it cannot be computed.

    None rather than raising, in two different situations that share the same
    return value on purpose:

    - a run stopped before reconcile legitimately has no world model yet, and
      `gate-brief` (which calls this) must never fail on a readable run that
      simply has not reached that stage -- the same ruling `claim_utilisation`
      already makes for the same absence; and
    - a world model, coverage document, or manifest that is *present* but
      malformed -- bad JSON, or a schema-shaped document missing
      `denominator`/`capability_cells`/`limits.max_scenarios` -- which is some
      other command's finding to report (`validate`'s, `check-refs`'), not
      this function's to raise on. Duplicating that check here would
      double-report the same defect, and worse, would turn a report into an
      exception -- the failure `gate-brief`'s module docstring says every read
      it makes must not have. This mirrors `brief._quietly` and
      `utilisation`'s helper of the same name, both of which already catch
      broadly for exactly this reason; `implied_size` is a public function a
      caller can reach directly, so the guard belongs here rather than only
      in `gate-brief`'s call site.

    Reads `denominator.capability_cells` and sums `len(goal["expected_hop_depths"])`
    over every goal for the numerator. When coverage exists (gate 2 or later),
    also subtracts the count of *distinct* `holes[].ref` whose `reason` is
    `blocked_by_gap` -- which cells score's round 1 has judged unreachable
    without a projection is not knowable before that round runs, so the basis
    string ("world_model" vs "world_model+coverage") says which state this
    result reflects. `ceiling` is the safety cap already in force
    (`manifest.limits.max_scenarios`); `ceiling_binding` is whether the
    implied size exceeds it, which is the diagnostic that means the target
    wants splitting across more than one run.
    """
    if not run.world_model.is_file():
        return None

    try:
        world = read_json(run.world_model)
        capability_cells = world["denominator"]["capability_cells"]
        hop_slots = sum(len(goal.get("expected_hop_depths", [])) for goal in world.get("goals", []))
        denominator = capability_cells + hop_slots

        blocked_cells = 0
        basis = "world_model"
        if run.coverage_latest.is_file():
            coverage = read_json(run.coverage_latest)
            blocked_refs = {
                hole["ref"]
                for hole in coverage.get("holes", [])
                if hole.get("reason") == "blocked_by_gap"
            }
            blocked_cells = len(blocked_refs)
            denominator -= blocked_cells
            basis = "world_model+coverage"

        implied = math.ceil(denominator / ACCEPTANCE_ALLOWANCE)
        manifest = read_json(run.manifest)
        ceiling = manifest["limits"]["max_scenarios"]
    except Exception:  # deliberate, matching brief._quietly's reasoning
        return None

    return {
        "capability_cells": capability_cells,
        "hop_slots": hop_slots,
        "blocked_cells": blocked_cells,
        "denominator": denominator,
        "implied": implied,
        "basis": basis,
        "ceiling": ceiling,
        "ceiling_binding": implied > ceiling,
    }
