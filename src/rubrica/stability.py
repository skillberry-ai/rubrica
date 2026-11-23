"""diff-runs: attribute variance to a stage instead of to "the pipeline".

Three Jaccards -- capability ids after 1b, goal-by-cell
claims after 2, emitted task ids after 6 -- so a reader can tell "stage 2 is
nondeterministic and everything downstream is stable given a fixed 02" from "the
whole thing is unstable". That distinction is the only reason to measure it.

Two disciplines, both load-bearing.

**Comparability is a precondition.** Two runs are comparable only if they read the
same input bytes and ran each stage under the same model, effort and skill hash. A
stability number over different inputs measures the inputs.

**Every number is reported with its set sizes and its difference.** jaccard's own
docstring requires it: a bare 1.0 over two runs that emitted nothing reads as
perfect stability, and a bare 0.4 tells nobody which capability moved.

This tool writes nothing. It spans two runs and belongs to neither, so its report
goes to stdout as JSON and its exit code is 0 -- like dedupe-candidates.
Incomparability is data inside that JSON plus a warning on stderr, not a finding:
exit 1 means finding lines on stdout, and a JSON document mixed with them would
break the orchestrator's line parser.
"""

from __future__ import annotations

from typing import Any

from rubrica.artifacts import read_json_or_none
from rubrica.metrics import jaccard
from rubrica.paths import RunPaths
from rubrica.refs import OPEN_STATUSES

_STAGE_FIELDS = ("model", "effort", "skill_sha256")


# None for absent or unparseable, so diff-runs works on a run that halted.
#
# Comparing a complete run against one that stopped after propose is exactly the
# comparison that localizes where reproducibility broke, so an absent artifact
# is data rather than an error. `comparability` treats an unreadable *manifest*
# separately, because there absence must not read as agreement.
_load = read_json_or_none


def _input_entries(run: RunPaths) -> list[Any]:
    """The manifest's `inputs` list as written, or empty when it is not a list."""
    manifest = _load(run.manifest)
    if not isinstance(manifest, dict):
        return []
    inputs = manifest.get("inputs", [])
    return inputs if isinstance(inputs, list) else []


def _is_input_digest(entry: Any) -> bool:
    # Both values must be strings, not merely present: an unhashable `sha256`
    # (a hand-edited list, say) would raise TypeError building the frozenset.
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("artifact_id"), str)
        and isinstance(entry.get("sha256"), str)
    )


def input_digests(run: RunPaths) -> frozenset[tuple[str, str]]:
    """(artifact_id, sha256) for every registered input that records both.

    An entry that is not an object, or lacks either string, is skipped rather
    than indexed: indexing it raised KeyError or AttributeError, which cli.py's
    catch-all turned into an `[internal]` line at exit 1 -- a finding-shaped
    answer from a command whose exit code is 0. Skipping alone would let two
    runs with the same broken entry agree *because* nothing was read, so
    `comparability` counts the skipped entries and names each side that has one.
    """
    return frozenset(
        (entry["artifact_id"], entry["sha256"])
        for entry in _input_entries(run)
        if _is_input_digest(entry)
    )


def _unpinned_inputs(run: RunPaths) -> int:
    """How many of the manifest's inputs `input_digests` had to skip."""
    return sum(1 for entry in _input_entries(run) if not _is_input_digest(entry))


def stage_config(run: RunPaths) -> dict[str, dict[str, Any]]:
    """The manifest's per-stage model, effort and skill hash.

    A `stages` key that is present but not a mapping is read as no stages at
    all, rather than returned raw: `comparability` would index a list by stage
    name and raise TypeError, which cli.py reports as a malformed artifact at
    exit 1. Reading it as absent routes it through the empty-map check instead,
    which makes the pair incomparable -- and absence never reading as agreement
    is the whole point of that check.
    """
    manifest = _load(run.manifest)
    if not isinstance(manifest, dict):
        return {}
    stages = manifest.get("stages", {})
    return stages if isinstance(stages, dict) else {}


def _entries(document: Any, key: str) -> list[dict[str, Any]]:
    """The object entries of `document[key]`, skipping anything else.

    The stage sets below are data, not a precondition, so a malformed entry is
    skipped rather than raised on: an AttributeError or KeyError here escaped to
    cli.py's catch-all as an `[internal]` exit 1, where diff-runs promises a JSON
    report at exit 0. A skipped entry cannot read as agreement: it is missing
    from that run's set, so a run whose twin kept it shows it under `only_a` or
    `only_b`, and the set sizes say how much each side contributed.
    """
    if not isinstance(document, dict):
        return []
    entries = document.get(key, [])
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def capability_ids(run: RunPaths) -> frozenset[str]:
    """The reconcile family's product: what the world model says the target can do."""
    return frozenset(
        capability["id"]
        for capability in _entries(_load(run.world_model), "capabilities")
        if isinstance(capability.get("id"), str)
    )


def goal_cell_claims(run: RunPaths) -> frozenset[tuple[str, str, str]]:
    """Stage 2's product: (goal, capability, outcome class) triples the run claims.

    Only scenarios the pipeline has not discarded. A `duplicate` or `rejected`
    scenario produced no test, so counting its claims would report stability in
    coverage the run did not deliver. A scenario or ref that is not an object, or
    whose ids are not strings, is skipped for the reason `_entries` gives -- and a
    non-string `status` is never tested against OPEN_STATUSES, since an
    unhashable one raises TypeError on a frozenset membership test.
    """
    claims: set[tuple[str, str, str]] = set()
    for scenario in _entries(_load(run.scenarios), "scenarios"):
        status, goal = scenario.get("status"), scenario.get("goal_id")
        if not isinstance(status, str) or status not in OPEN_STATUSES:
            continue
        if not isinstance(goal, str):
            continue
        for ref in _entries(scenario, "capability_refs"):
            capability, outcome = ref.get("capability_id"), ref.get("outcome_class_id")
            if isinstance(capability, str) and isinstance(outcome, str):
                claims.add((goal, capability, outcome))
    return frozenset(claims)


def emitted_task_ids(run: RunPaths) -> frozenset[str]:
    """Stage 6's product: the packages that shipped."""
    return frozenset(run.scenario_ids_with_tasks())


def comparability(a: RunPaths, b: RunPaths) -> list[str]:
    """Why these two runs cannot be compared. Empty means they can.

    One principle, applied at three depths: **absence must not read as
    agreement.** An unreadable manifest is its own reason rather than an empty
    digest set, because jaccard(empty, empty) is 1.0, so two runs whose manifests
    could not be read would otherwise be declared perfectly comparable *because*
    nothing was checked. An empty `stages` map is its own reason for the same
    reason one level in: the per-stage loop below takes zero iterations over it
    and appends nothing. And a `stages` value that is not a mapping at all is
    normalised to empty by stage_config so it reaches that check.
    """
    reasons: list[str] = []
    for run, label in ((a, "a"), (b, "b")):
        if not isinstance(_load(run.manifest), dict):
            reasons.append(f"run {label} has no readable manifest.json, so nothing can be pinned")
    if reasons:
        # Kept deliberately, and it does not change `comparable`: with either
        # manifest unreadable the run is incomparable either way. What it guards
        # is the *reasons list a human reads to localize the break*. When only one
        # manifest is unreadable, that side's digests and stage config are empty
        # while the other side's are real, so falling through would append "the
        # two runs read different input bytes" and one "stage X is recorded only
        # in run a" per stage -- every one of them derived from the absence rather
        # than from a difference, burying the single fact that explains them all.
        return reasons

    digests_a, digests_b = input_digests(a), input_digests(b)
    if digests_a != digests_b:
        reasons.append(
            "the two runs read different input bytes, so any stability number below measures "
            "the inputs rather than the pipeline"
        )
    # Absence must not read as agreement, at the depth of one input entry:
    # input_digests skips an entry it cannot pin, so two runs carrying the same
    # broken entry would otherwise compare equal on what is left.
    for run, label in ((a, "a"), (b, "b")):
        unpinned = _unpinned_inputs(run)
        if unpinned:
            reasons.append(
                f"run {label} has {unpinned} input entr{'y' if unpinned == 1 else 'ies'} in "
                "manifest.json without a string artifact_id and sha256, so its input bytes "
                "cannot be pinned"
            )

    stages_a, stages_b = stage_config(a), stage_config(b)
    # The same principle the manifest check above implements, one artifact
    # deeper: absence must not read as agreement. An empty `stages` map takes
    # the loop below zero times and appends no reason, so two runs that recorded
    # nothing were declared perfectly comparable *because* nothing was checked
    # -- exactly the reading jaccard(empty, empty) == 1.0 gets wrong. That is
    # not a hypothetical state: it is every intake-only run, and any run where
    # the orchestrator never called `record-stage`. Reported per side, because
    # which side recorded nothing is the fact a reader needs.
    for stages, label in ((stages_a, "a"), (stages_b, "b")):
        if not stages:
            reasons.append(
                f"run {label} records no stages in manifest.json, so no model, effort or skill "
                "hash can be pinned"
            )
    for stage in sorted(set(stages_a) | set(stages_b)):
        if stage not in stages_a or stage not in stages_b:
            present = "a" if stage in stages_a else "b"
            reasons.append(f"stage {stage!r} is recorded only in run {present}")
            continue
        # A stage entry that is not an object (a hand-edited `"extract": "oops"`)
        # has no model, effort or skill hash to read; calling .get on it raised
        # AttributeError and surfaced as an `[internal]` exit 1. Named per side
        # rather than compared, because two identical broken entries are equal
        # strings and comparing them would read absence as agreement.
        malformed = [
            label
            for stages, label in ((stages_a, "a"), (stages_b, "b"))
            if not isinstance(stages[stage], dict)
        ]
        for label in malformed:
            reasons.append(
                f"stage {stage!r} in run {label} is not an object in manifest.json, so no "
                "model, effort or skill hash can be pinned"
            )
        if malformed:
            continue
        for field in _STAGE_FIELDS:
            if stages_a[stage].get(field) != stages_b[stage].get(field):
                reasons.append(
                    f"stage {stage!r} ran with a different {field}: "
                    f"{stages_a[stage].get(field)!r} against {stages_b[stage].get(field)!r}"
                )
    return reasons


def _render_member(member: Any) -> str:
    return "/".join(str(part) for part in member) if isinstance(member, tuple) else str(member)


def _stage_diff(set_a: frozenset, set_b: frozenset) -> dict[str, Any]:
    return {
        "jaccard": jaccard(set_a, set_b),
        "a_size": len(set_a),
        "b_size": len(set_b),
        "only_a": sorted(_render_member(member) for member in set_a - set_b),
        "only_b": sorted(_render_member(member) for member in set_b - set_a),
    }


def diff_runs(a: RunPaths, b: RunPaths) -> dict[str, Any]:
    """The per-stage stability report for two runs.

    The stage numbers are reported even when the runs are incomparable. An
    incomparable pair is often the interesting one, and refusing to report would
    hide exactly the localization this tool exists for -- a reader needs to see
    that stage 2 diverged *and* that the inputs differed.
    """
    reasons = comparability(a, b)
    return {
        "format": "rubrica-stability/1",
        "a": str(a.root),
        "b": str(b.root),
        "comparable": not reasons,
        "incomparable_reasons": reasons,
        "stages": {
            "1b_capabilities": _stage_diff(capability_ids(a), capability_ids(b)),
            "2_goal_cell_claims": _stage_diff(goal_cell_claims(a), goal_cell_claims(b)),
            "6_task_ids": _stage_diff(emitted_task_ids(a), emitted_task_ids(b)),
        },
    }
