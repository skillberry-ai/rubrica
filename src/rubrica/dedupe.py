"""Proposing candidate duplicate scenario pairs.

The deterministic half of stage 3's dedupe. Two scenarios are candidates when
they serve the same goal and claim at least one coverage cell in common --
cheap to compute and a good filter. It never decides: recognising that "find
the oldest failing job on prod0" and "which prod0 job failed longest ago" are
the same test needs judgment, and tg-score makes that call with every
scenario already in context.

Scenarios already marked `duplicate` or `rejected` are excluded, so a pair whose
fold has been *carried out* is not raised again -- re-proposing a resolved fold
is how a loop fails to converge.

**That is narrower than "settled", and the difference is load-bearing for the
stage reading this output.** The filter is on status, and a pair that tg-score
deliberately kept *both* `active` on -- its first refusal condition, for a pair
that is arguably one test and arguably two -- is a settled pair whose members are
both still open, so it is raised again in every later round. A scorer told that
this command "excludes pairs already settled" could read the re-raise as evidence
the pair was never settled and fold it, deleting a cell for the whole run, which
that refusal condition ranks as the strictly worse error. So the guarantee here
is only this: **a candidate is a pair worth a judgment call, and one that has
already been judged can appear again.** Whether an earlier round decided it is
not something this command knows.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any

from rubrica.refs import OPEN_STATUSES, cell_ref


@dataclass(frozen=True)
class Candidate:
    """A pair worth a judgment call, with the evidence that raised it."""

    a: str
    b: str
    shared_cells: tuple[str, ...]
    identical_cells: bool


def _cells(scenario: dict[str, Any]) -> frozenset[str]:
    return frozenset(
        cell_ref(ref["capability_id"], ref["outcome_class_id"])
        for ref in scenario.get("capability_refs", [])
    )


def candidate_pairs(scenarios: list[dict[str, Any]]) -> list[Candidate]:
    """Candidate duplicate pairs, ordered by scenario id for stable output."""
    open_scenarios = sorted(
        (s for s in scenarios if s.get("status") in OPEN_STATUSES),
        key=lambda s: s["id"],
    )
    out: list[Candidate] = []
    for first, second in combinations(open_scenarios, 2):
        if first.get("goal_id") != second.get("goal_id"):
            continue
        cells_a, cells_b = _cells(first), _cells(second)
        shared = cells_a & cells_b
        if not shared:
            continue
        out.append(
            Candidate(
                a=first["id"],
                b=second["id"],
                shared_cells=tuple(sorted(shared)),
                identical_cells=cells_a == cells_b,
            )
        )
    return out
