"""sample-for-review: a stratified review packet, with a fixed rubric.

Design spec section 7, and one instruction in it decides the whole design:
**sample preferentially from high-confidence `accept` verdicts.** That is where a
correlated labeler/adversary blind spot hides. A sample drawn from the cases the
adversary flagged would surface only what the adversary already found, which is
the one risk in section 10 the pipeline cannot mitigate from inside itself.

Everything here is deterministic. No `random`, no builtin `hash()` -- which is
salted per process -- and no timestamp anywhere in the output. A sample that moved
between two runs of the same suite would make the review trend line worthless,
because a change in the scores could not be told from a change in the sample.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from rubrica.artifacts import ArtifactError, read_json, sha256_of, write_json
from rubrica.errors import UsageError
from rubrica.findings import Finding
from rubrica.paths import RunPaths

# Fixed, so review is a trend line rather than a fresh opinion each time.
RUBRIC = ("fair", "unambiguous", "correctly_labeled", "non_trivial")

DEFAULT_SAMPLE_SIZE = 3

_WHY_HERE = (
    "Sampled preferentially from **high-confidence `accept` verdicts** and spread across hop "
    "depths. That is deliberate: the adversary already reported what it doubted, so reviewing "
    "its doubts finds only what it found. A correlated labeler/adversary blind spot can only "
    "show up in the cases both of them were confident about, and this packet is drawn from "
    "exactly those. Do not make this sample uniform."
)


def confidence_band(verdict: dict[str, Any] | None) -> str:
    """ "high" only for an accept the adversary qualified in no way.

    An absent verdict is "low" rather than excluded: a package with no adversarial
    judgement at all is the one that most needs a human, and dropping it from the
    candidate pool would hide it.
    """
    if not isinstance(verdict, dict):
        return "low"
    unqualified = (
        verdict.get("verdict") == "accept"
        and verdict.get("uniquely_determined") is True
        and verdict.get("derivable_without_guessing") is True
        and not verdict.get("flags")
    )
    return "high" if unqualified else "low"


def _load(path) -> Any | None:
    try:
        return read_json(path)
    except ArtifactError:
        return None


def candidates(run: RunPaths) -> list[dict[str, Any]]:
    """Every emitted package, with its band and its hop depth, in id order.

    Emitted packages only. A reviewer can act on a task that shipped; a scenario
    the pipeline discarded is not something to ask four questions about.

    Raises ArtifactError when 02-scenarios.json cannot be read. Defaulting it to
    an empty document gave every candidate `hop_depth: 0`, which collapses the
    stratification this tool exists for -- a packet of three tasks all at one
    depth, written at exit 0 with no finding, looking exactly like a suite that
    really is flat. recall.generated_tasks makes the same distinction.
    """
    document = read_json(run.scenarios)
    scenarios = {s["id"]: s for s in document.get("scenarios", [])}
    entries = []
    for sid in run.scenario_ids_with_tasks():
        scenario = scenarios.get(sid, {})
        entries.append(
            {
                "scenario_id": sid,
                "band": confidence_band(_load(run.verdict(sid))),
                "hop_depth": scenario.get("hop_depth", 0),
            }
        )
    return entries


def _order_key(entry: dict[str, Any]) -> tuple[int, str]:
    """Band first, then a stable digest of the id.

    sha256 rather than hash(): the builtin is salted per process, so the same
    suite would sample differently on every invocation and the trend line would
    measure the salt.
    """
    band_rank = 0 if entry["band"] == "high" else 1
    return band_rank, hashlib.sha256(entry["scenario_id"].encode("utf-8")).hexdigest()


def stratified(entries: list[dict[str, Any]], size: int) -> list[dict[str, Any]]:
    """Round-robin across hop depths, preferring the high band. Deterministic.

    Stratified rather than top-ranked: three samples all at hop depth 1 tell a
    reviewer nothing about whether the deep scenarios are fair.

    The band preference is a preference, not an exclusion. A suite in which the
    adversary qualified every accept would otherwise produce an empty packet --
    the run most in need of review producing the least of it.
    """
    if size <= 0:
        # sample_run refuses a non-positive size as a UsageError before it gets
        # here, so this only keeps the pure function total for a direct caller.
        return []
    strata: dict[int, list[dict[str, Any]]] = {}
    for entry in sorted(entries, key=_order_key):
        strata.setdefault(entry["hop_depth"], []).append(entry)
    picked: list[dict[str, Any]] = []
    while len(picked) < size and any(strata.values()):
        for depth in sorted(strata):
            if len(picked) >= size:
                break
            if strata[depth]:
                picked.append(strata[depth].pop(0))
    return sorted(picked, key=_order_key)


def _section(run: RunPaths, entry: dict[str, Any]) -> list[str]:
    sid = entry["scenario_id"]
    task = run.task_dir(sid)
    verdict = _load(run.verdict(sid)) or {}
    expected = _load(run.expected(sid)) or {}
    instruction = (
        (task / "instruction.md").read_text(encoding="utf-8").strip()
        if (task / "instruction.md").is_file()
        else "(no instruction.md in the emitted package)"
    )
    digest = sha256_of(run.seed(sid)) if run.seed(sid).is_file() else "(no seed.json)"
    lines = [
        f"## `{sid}` — confidence band: **{entry['band']}**, hop depth {entry['hop_depth']}",
        "",
        "### Instruction the agent receives",
        "",
        instruction,
        "",
        f"### Seed digest\n\n`sha256:{digest}`\n",
        "The seed itself is deliberately not inlined: the digest is what confirms which world",
        "this label was authored against, and the whole simulated backend would bury the four",
        "questions below.",
        "",
        "### Reference answer and assertions",
        "",
        "```json",
        json.dumps(
            {
                "answer_reference": expected.get("answer_reference"),
                "discriminating_fact": expected.get("discriminating_fact"),
                "assertions": expected.get("assertions"),
            },
            indent=2,
            sort_keys=True,
        ),
        "```",
        "",
    ]
    if run.rationale(sid).is_file():
        lines += [
            "### Why the instantiate stage chose this world",
            "",
            run.rationale(sid).read_text(encoding="utf-8").strip(),
            "",
        ]
    lines += [
        "### Adversary notes",
        "",
        f"- **Verdict:** {verdict.get('verdict')}",
        f"- **Uniquely determined:** {verdict.get('uniquely_determined')}",
        f"- **Derivable without guessing:** {verdict.get('derivable_without_guessing')}",
        f"- **`minimum_tool_calls_found`:** {verdict.get('minimum_tool_calls_found')}",
        f"- **Notes:** {verdict.get('notes', '')}",
        "",
        "### Rubric",
        "",
    ]
    lines += [f"- [ ] **{item.replace('_', ' ')}**" for item in RUBRIC]
    lines.append("")
    return lines


def packet(run: RunPaths, entries: list[dict[str, Any]]) -> str:
    """The review packet: one section per sampled task, one fixed rubric each."""
    lines = [
        "# Review packet",
        "",
        _WHY_HERE,
        "",
        f"- **Tasks in this packet:** {len(entries)}",
        f"- **Rubric:** {', '.join(item.replace('_', ' ') for item in RUBRIC)}",
        "",
    ]
    for entry in entries:
        lines += _section(run, entry)
    return "\n".join(lines)


def sample_run(run: RunPaths, size: int = DEFAULT_SAMPLE_SIZE) -> tuple[list[dict], list[Finding]]:
    """Write the packet and the machine-readable record. -> (sampled, findings).

    sample.json carries no timestamp, so two runs of the same suite produce
    byte-identical records and a diff shows only what actually changed.

    Two refusals happen before anything is written.

    A `size` of zero or less is a UsageError, which cli.py maps to exit 2. It used
    to overwrite an existing packet with an empty one and exit 0, which is
    indistinguishable from success -- and a review packet nobody can tell is empty
    on purpose is worse than no packet. intake validates its own numeric arguments
    the same way.

    manifest.json is read first, the way smoke_run reads it, so a directory that
    is not a run exits 2 rather than having a measurement/review/ tree written
    into it. It used to be read last, after the packet was already on disk.
    """
    if size <= 0:
        raise UsageError(
            f"--size must be at least 1, got {size}; a packet of no tasks cannot be told "
            "apart from a review that found nothing to say"
        )
    run_id = read_json(run.manifest)["run_id"]
    try:
        pool = candidates(run)
    except ArtifactError as exc:
        return [], [
            Finding(
                run.scenarios,
                "review",
                "",
                f"{exc}; the review packet cannot be stratified by hop depth without it, and "
                "a packet built from a default depth of 0 would collapse the stratification "
                "this tool exists for. Nothing was written",
            )
        ]
    if not pool:
        return [], [
            Finding(
                run.suite_dir,
                "review",
                "",
                "no emitted packages to review; emit must run before sample-for-review",
            )
        ]
    sampled = stratified(pool, size)
    findings: list[Finding] = []
    if not any(entry["band"] == "high" for entry in pool):
        findings.append(
            Finding(
                run.review_sample,
                "review",
                "",
                "no high-confidence accept exists in this suite, so the packet cannot look "
                "where a correlated labeler/adversary blind spot would hide; every accept was "
                "qualified by the adversary",
            )
        )
    run.review_dir.mkdir(parents=True, exist_ok=True)
    run.review_packet.write_text(packet(run, sampled), encoding="utf-8")
    write_json(
        run.review_sample,
        {
            "format": "rubrica-review/1",
            "run_id": run_id,
            "size_requested": size,
            "sampled": sampled,
            "rubric": list(RUBRIC),
        },
    )
    return sampled, findings
