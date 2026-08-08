"""compare-gold: recall and novelty against the authored bench tasks.

Design spec section 7. The question is whether the pipeline found the tests a
human already wrote, and what it found that they did not -- and the answer is a
smoke signal, never a metric to optimize. With a denominator of ten, one task is
ten percentage points: 7/10 against 8/10 is noise. The rendered report says so
inline, derived from the actual denominator, because a number without that
sentence beside it will be optimized.

Every match is a **proposal for human confirmation.** Matching is goal identity
plus capability-cell overlap, and no similarity number can tell two phrasings of
one test from two genuinely different tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from testgen.artifacts import ArtifactError, read_json
from testgen.errors import UsageError
from testgen.findings import format_findings
from testgen.metrics import jaccard
from testgen.paths import RunPaths
from testgen.validate import validate_artifact

# Cell-overlap at or above this proposes a pair, once the goals already match.
# Half, because a generated scenario that reaches an authored task's goal through
# half the same capability cells is plausibly the same test asked differently --
# and the human confirmation step is what resolves the plausibly.
MATCH_JACCARD_FLOOR = 0.5


def load_gold(path: Path | str) -> dict[str, Any]:
    """Read and schema-validate the bench task list.

    UsageError, not findings: a person wrote this file, so there is no stage to
    hand a repair prompt to. Same treatment smoke.load_agents gives its roster.
    """
    findings = validate_artifact(Path(path), "gold")
    if findings:
        raise UsageError(f"unusable gold task list:\n{format_findings(findings)}")
    return read_json(path)


def cells(capability_refs: list[dict[str, Any]]) -> frozenset[tuple[str, str]]:
    """The set of (capability, outcome class) pairs a task exercises."""
    return frozenset((ref["capability_id"], ref["outcome_class_id"]) for ref in capability_refs)


def generated_tasks(run: RunPaths) -> list[dict[str, Any]]:
    """The scenarios that actually shipped, in id order.

    Emitted packages joined back to their scenarios -- not every scenario in
    02-scenarios.json. Recall is about the suite that shipped: crediting the
    pipeline with a scenario the adversary rejected would count a test it did not
    deliver. A package whose scenario has vanished from 02 is skipped rather than
    guessed at; refs.check_suite reports that separately.
    """
    scenarios = _load_scenarios(run)
    return [scenarios[sid] for sid in run.scenario_ids_with_tasks() if sid in scenarios]


def _load_scenarios(run: RunPaths) -> dict[str, dict[str, Any]]:
    try:
        document = read_json(run.scenarios)
    except ArtifactError:
        return {}
    return {s["id"]: s for s in document.get("scenarios", [])}


def _pair_score(gold_task: dict[str, Any], scenario: dict[str, Any]) -> float | None:
    """Cell overlap for a candidate pair, or None if they cannot pair at all.

    Goal identity is a precondition rather than a term in the score: two tasks
    over different goals are different tests even when every capability cell
    matches, because the goal is what the test is about.
    """
    if gold_task["goal_id"] != scenario["goal_id"]:
        return None
    score = jaccard(cells(gold_task["capability_refs"]), cells(scenario["capability_refs"]))
    return score if score >= MATCH_JACCARD_FLOOR else None


def assign_matches(
    gold_tasks: list[dict[str, Any]], generated: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    """One-to-one assignment. -> (matches, unmatched gold ids, unmatched scenarios).

    One gold task claims at most one scenario and vice versa. Without that, eight
    paraphrases of one test would each be credited against the same bench task and
    recall would exceed what the suite covers.

    Greedy on descending overlap, with ties broken by (gold id, scenario id) so
    the assignment is a function of the inputs alone. A non-deterministic
    assignment would make recall appear to move between two runs of the same data,
    which is the one thing this number must not do.
    """
    candidates = []
    for gold_task in gold_tasks:
        for scenario in generated:
            score = _pair_score(gold_task, scenario)
            if score is not None:
                candidates.append((score, gold_task["id"], scenario["id"]))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))

    matches: list[dict[str, Any]] = []
    taken_gold: set[str] = set()
    taken_scenarios: set[str] = set()
    for score, gold_id, scenario_id in candidates:
        if gold_id in taken_gold or scenario_id in taken_scenarios:
            continue
        taken_gold.add(gold_id)
        taken_scenarios.add(scenario_id)
        matches.append({"gold_id": gold_id, "scenario_id": scenario_id, "jaccard": score})
    matches.sort(key=lambda match: match["gold_id"])
    return (
        matches,
        sorted(task["id"] for task in gold_tasks if task["id"] not in taken_gold),
        sorted(
            (s for s in generated if s["id"] not in taken_scenarios),
            key=lambda s: s["id"],
        ),
    )
