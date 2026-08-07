"""Proposing candidate duplicate scenario pairs.

The deterministic half of stage 3's dedupe. Two scenarios are candidates when
they serve the same goal and claim at least one coverage cell in common --
cheap to compute and a good filter. It never decides: recognising that "find
the oldest failing job on prod0" and "which prod0 job failed longest ago" are
the same test needs judgment, and tg-score makes that call with every
scenario already in context.

Scenarios already marked duplicate or rejected are excluded; re-proposing a
pair that was resolved in an earlier round is how a loop fails to converge.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any

from testgen.refs import OPEN_STATUSES, cell_ref


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
