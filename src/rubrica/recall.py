"""compare-gold: recall and novelty against the authored bench tasks.

The question is whether the pipeline found the tests a
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

from rubrica.artifacts import ArtifactError, read_json, write_json
from rubrica.errors import UsageError
from rubrica.findings import Finding, format_findings
from rubrica.metrics import jaccard
from rubrica.paths import RunPaths
from rubrica.validate import validate_artifact

# Cell-overlap at or above this proposes a pair, once the goals already match.
# Half, because a generated scenario that reaches an authored task's goal through
# half the same capability cells is plausibly the same test asked differently --
# and the human confirmation step is what resolves the plausibly.
MATCH_JACCARD_FLOOR = 0.5


def load_gold(path: Path | str) -> dict[str, Any]:
    """Read and schema-validate the bench task list.

    UsageError, not findings: a person wrote this file, so there is no stage to
    hand a repair prompt to. Same treatment smoke.load_agents gives its roster,
    including the unreadable cases artifacts.read_json does not convert:
    --gold pointing at a directory, at a non-UTF-8 file, or at a file with mode
    000 raised out of here and became a finding at exit 1 blaming this run's
    artifacts for a misconfigured invocation. read_json is deliberately *not*
    widened, because an unreadable stage artifact must stay a finding.
    """
    try:
        findings = validate_artifact(Path(path), "gold")
        if findings:
            raise UsageError(f"unusable gold task list:\n{format_findings(findings)}")
        return read_json(path)
    except (OSError, UnicodeDecodeError, ArtifactError) as exc:
        raise UsageError(f"unusable gold task list: {path}: {exc}") from exc


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

    Raises ArtifactError when 02-scenarios.json cannot be read at all. It used to
    be swallowed into an empty mapping, which is a different claim: every emitted
    package then looked like a package whose scenario had vanished, and compare
    wrote a durable "Generated tasks that shipped: 0, Recall: 0.00" that blamed
    the gold list for an artifact this tool could not read.
    stability.comparability makes the same distinction for the same reason --
    absence must not read as agreement.
    """
    scenarios = _load_scenarios(run)
    return [scenarios[sid] for sid in run.scenario_ids_with_tasks() if sid in scenarios]


def _load_scenarios(run: RunPaths) -> dict[str, dict[str, Any]]:
    """The scenarios by id. Raises ArtifactError if 02-scenarios.json is unreadable."""
    document = read_json(run.scenarios)
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


# Ordered by how much a reader should care, and the order the checks run in. A
# scenario that reached a capability nobody authored is the most interesting
# result this tool can produce, and running the checks the other way round would
# file it under the blandest label that also happens to be true.
NOVELTY_KINDS = ("new_capability", "new_outcome_class", "new_hop_depth", "spurious")

_NOISE_CAVEAT = (
    "**Recall is a smoke signal, not a metric to optimize.** With a denominator of "
    "{denominator}, one task is {step:.0%}: {matched}/{denominator} against "
    "{next_up}/{denominator} is noise, not improvement. Every match below is a "
    "proposal for **human confirmation** -- matching is goal identity plus "
    "capability-cell overlap, and no similarity number can tell two phrasings of "
    "one test from two different tests."
)

_UNREADABLE_CAVEAT = (
    "**No recall is reported: {reason}.** The generated suite could not be read, so there is "
    'nothing to compare the authored tasks against. A recall of 0.00 here would read as "the '
    'pipeline found none of them" -- a claim about the pipeline, made from an artifact this '
    "tool could not read. Repair `02-scenarios.json` and re-run."
)

_NO_GOLD_CAVEAT = (
    "There are no gold tasks to compare against, so there is no recall to report. "
    "The novelty section below still stands on its own, and every entry in it is a "
    "proposal for **human confirmation**."
)


def classify_novelty(scenario: dict[str, Any], gold_tasks: list[dict[str, Any]]) -> tuple[str, str]:
    """Why one unmatched scenario is interesting. -> (kind, why).

    A goal gold never covers is folded into new_hop_depth rather than given a
    fifth category: it has no authored depths, so every depth it reaches is new,
    and the `why` string names the goal so the reason is not lost. That keeps the
    vocabulary this report is defined in terms of.
    """
    authored_capabilities = {
        ref["capability_id"] for task in gold_tasks for ref in task["capability_refs"]
    }
    authored_cells = (
        frozenset().union(*(cells(task["capability_refs"]) for task in gold_tasks))
        if gold_tasks
        else frozenset()
    )
    authored_depths = {(task["goal_id"], task["hop_depth"]) for task in gold_tasks}

    scenario_cells = cells(scenario["capability_refs"])
    new_capabilities = sorted(
        {capability for capability, _ in scenario_cells} - authored_capabilities
    )
    if new_capabilities:
        return "new_capability", (
            f"exercises {', '.join(new_capabilities)}, which no authored task touches"
        )
    new_cells = sorted(scenario_cells - authored_cells)
    if new_cells:
        return "new_outcome_class", (
            "reaches "
            + ", ".join(f"{capability}/{outcome}" for capability, outcome in new_cells)
            + ", an outcome class no authored task reaches for that capability"
        )
    pair = (scenario["goal_id"], scenario["hop_depth"])
    if pair not in authored_depths:
        covered = sorted(depth for goal, depth in authored_depths if goal == pair[0])
        return "new_hop_depth", (
            f"reaches goal {pair[0]} at hop depth {pair[1]}; authored depths for that goal "
            f"are {covered or 'none -- the goal itself is unauthored'}"
        )
    return "spurious", (
        "every capability cell and the (goal, hop depth) pair already appear in the authored "
        "tasks, so this adds no coverage axis and looks new only because no single authored "
        "task overlapped it enough to pair"
    )


def compare(run: RunPaths, gold: dict[str, Any]) -> dict[str, Any]:
    """The recall-and-novelty report for one run against one gold list.

    `recall` is None rather than 0.0 when no gold tasks were supplied: 0.0 reads as
    "the pipeline found none of them", which is a claim about the pipeline rather
    than about the missing input. It is None for the same reason when
    02-scenarios.json could not be read -- `unreadable` then carries why, and
    compare_run turns it into a finding naming the artifact.

    manifest.json is read first and indexed directly, the way smoke_run reads it:
    a directory without one is not a run, the ArtifactError becomes exit 2, and
    compare_run must not write measurement/recall.json into a directory that is
    not a run.
    """
    run_id = read_json(run.manifest)["run_id"]
    gold_tasks = gold.get("tasks", [])
    denominator = len(gold_tasks)
    # A format tag, not a schema_version: no JSON Schema gates this file,
    # because this project's own code writes it and unit tests gate it
    # instead. Claiming a schema_version would say otherwise.
    header = {
        "format": "rubrica-recall/1",
        # Which run this number is about. 07-report.json and review/sample.json
        # both carry it, and a recall.json copied out of its directory was the
        # one measurement output that could not say what it measured.
        "run_id": run_id,
        "target": gold.get("target"),
        "gold_denominator": denominator,
        "human_confirmation_required": True,
    }
    try:
        generated = generated_tasks(run)
    except ArtifactError as exc:
        return {
            **header,
            "generated_total": None,
            "matched": [],
            # Not every gold id: "nothing matched these" is a claim about the
            # suite, and there is no readable suite here to make it about.
            "unmatched_gold": [],
            "recall": None,
            "novel": [],
            "unreadable": str(exc),
        }
    matches, unmatched_gold, unmatched_generated = assign_matches(gold_tasks, generated)
    novel = []
    for scenario in unmatched_generated:
        kind, why = classify_novelty(scenario, gold_tasks)
        novel.append({"scenario_id": scenario["id"], "kind": kind, "why": why})
    return {
        **header,
        "generated_total": len(generated),
        "matched": matches,
        "unmatched_gold": unmatched_gold,
        "recall": round(len(matches) / denominator, 6) if denominator else None,
        "novel": novel,
        "unreadable": None,
    }


def caveat(report: dict[str, Any]) -> str:
    """The sentence that must sit beside every recall number."""
    if report.get("unreadable"):
        return _UNREADABLE_CAVEAT.format(reason=report["unreadable"])
    denominator = report["gold_denominator"]
    if not denominator:
        return _NO_GOLD_CAVEAT
    matched = len(report["matched"])
    return _NOISE_CAVEAT.format(
        denominator=denominator,
        step=1 / denominator,
        matched=matched,
        next_up=min(matched + 1, denominator),
    )


def render(report: dict[str, Any]) -> str:
    """The human-facing markdown. The caveat is not optional and not at the end."""
    lines = [
        "# Recall and novelty against the authored bench tasks",
        "",
        caveat(report),
        "",
        f"- **Authored tasks:** {report['gold_denominator']}",
        "- **Generated tasks that shipped:** "
        + ("not readable" if report["generated_total"] is None else str(report["generated_total"])),
        f"- **Matched:** {len(report['matched'])}",
        "- **Recall:** "
        + ("not applicable" if report["recall"] is None else f"{report['recall']:.2f}"),
        "",
        "## Proposed matches",
        "",
    ]
    if report["matched"]:
        lines += ["| Authored | Generated | Cell overlap |", "|---|---|---|"]
        lines += [
            f"| `{m['gold_id']}` | `{m['scenario_id']}` | {m['jaccard']:.2f} |"
            for m in report["matched"]
        ]
    else:
        lines.append("None.")
    lines += ["", "## Authored tasks nothing matched", ""]
    lines += (
        [f"- `{gold_id}`" for gold_id in report["unmatched_gold"]]
        if report["unmatched_gold"]
        else ["None."]
    )
    lines += ["", "## Generated tasks nothing authored", ""]
    lines += (
        [f"- `{n['scenario_id']}` — **{n['kind']}**: {n['why']}" for n in report["novel"]]
        if report["novel"]
        else ["None."]
    )
    lines.append("")
    return "\n".join(lines)


def compare_run(run: RunPaths, gold_path: Path | str) -> tuple[dict[str, Any], list[Finding]]:
    """Write measurement/recall.json and return (report, findings).

    Findings, not a bare report: a gold task nothing matched is worth the
    orchestrator's attention, and so is a `spurious` entry. Neither is a defect in
    an artifact, so both are reported once, aggregated, rather than one finding per
    row -- the point is the shape of the gap, not a list.
    """
    report = compare(run, load_gold(gold_path))
    write_json(run.recall, report)
    run.recall_md.write_text(render(report), encoding="utf-8")
    findings = []
    if report["unreadable"]:
        # Named, not silently folded into a recall of 0.00. The report already
        # says `recall: null` and why; this is the line the orchestrator branches
        # on, and it names the artifact to repair rather than the gold list.
        findings.append(
            Finding(
                run.scenarios,
                "recall",
                "",
                f"{report['unreadable']}; no recall could be measured for this run. Repair "
                "02-scenarios.json -- the number in measurement/recall.json is null rather "
                "than 0.00 because an unreadable suite is not a suite that matched nothing",
            )
        )
    if report["unmatched_gold"]:
        findings.append(
            Finding(
                run.recall,
                "recall",
                "/unmatched_gold",
                f"{len(report['unmatched_gold'])} authored task(s) have no generated "
                f"counterpart: {', '.join(report['unmatched_gold'])}. With a denominator of "
                f"{report['gold_denominator']} this is a smoke signal, not a score",
            )
        )
    spurious = [entry["scenario_id"] for entry in report["novel"] if entry["kind"] == "spurious"]
    if spurious:
        findings.append(
            Finding(
                run.recall,
                "recall",
                "/novel",
                f"{len(spurious)} generated task(s) add no coverage axis over the authored "
                f"set: {', '.join(spurious)}",
            )
        )
    return report, findings
