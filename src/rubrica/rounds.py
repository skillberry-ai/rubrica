"""The propose/score loop's code steps.

Code rather than a prompt for the reason emit and both existing seals are code:
two runs with identical parts must produce a byte-identical result, or variance
stops being attributable to the stage that caused it. There is a second reason
specific to this loop, and it is the defect this module exists to close.

MEASURED, run-20260825-094033 (executive-agent, 5 files, sonnet/medium): round
1 proposed 18 scenarios into a 24,613-byte 02-scenarios.json and rb-score
returned verdict `continue`. Round 2 then had to emit round 1's scenarios
verbatim plus one new scenario per closable hole, of which the coverage report
listed 86. At the file's own 1,162-byte mean that is ~124,545 bytes in one
response against a 32,000-output-token cap: the dispatch spent $3.57 over 31
minutes and wrote nothing at all.

The term that binds is NOT the accumulated re-emit, which was 24,613 of those
bytes -- 20%. It is the round's own batch, sized by the closable-hole count,
which is why this module partitions holes rather than merely dropping the
re-emit. The comparison run 20260823-112746 cleared round 2 with 4 closable
holes and a round-1 file only 1.4x smaller; the hole counts differ by 21.5x.

So a batch is a *writing* unit, exactly as a triage slice is a *reading* unit,
and the same thing makes it acceptable: nothing here decides anything. Every
closable hole reaches a member, which holes are closable is rb-score's ruling
and not this partition's, and a human at gate 2 still sees the whole coverage
matrix. What this bounds is how much one response has to contain.
"""

from __future__ import annotations

import json
from pathlib import Path

from rubrica.artifacts import read_json, write_json
from rubrica.errors import UsageError
from rubrica.paths import RunPaths

# The measured maximum scenario on run-20260825-094033 was 1,579 serialized
# bytes against a 1,162 mean. The estimate rounds up to the max rather than the
# mean, because a projection that under-estimates produces exactly the failure
# this module exists to prevent, and one that over-estimates only produces one
# more batch than strictly needed.
DEFAULT_BYTES_PER_SCENARIO = 1600

# Per-member output budget, ~8k output tokens at ~3.5 bytes/token. Chosen well
# under the 32,000 that killed round 2 rather than just under it: the cap counts
# thinking tokens too, and a member also emits its report back to the
# orchestrator, so the write is not the whole response. At this budget the
# measured 86 closable holes become 6 batches.
DEFAULT_SCENARIO_PART_BYTES = 28000


def closable_holes(run: RunPaths) -> list[str]:
    """The hole refs a new scenario could close this round, sorted.

    Round 1 has no coverage report, and that is the normal shape rather than a
    missing file -- rb-propose's Inputs section says so outright -- so every
    capability x outcome-class cell and every goal is open by default and the
    worklist is enumerated from the world model.

    From round 2 the report's holes are the worklist, filtered to
    `not_yet_attempted`. The other three reasons are not closable by proposing,
    however good the scenario: `unreachable` and `out_of_scope` are cells the
    suite is not trying to cover, and `blocked_by_gap` means the world model
    does not yet support a scenario there, so proposing anyway produces one
    rb-instantiate cannot honestly seed.
    """
    world = read_json(run.world_model)
    if not run.coverage_latest.exists():
        refs = [
            f"cell:{cap['id']}/{oc['id']}"
            for cap in world.get("capabilities", [])
            for oc in cap.get("outcome_classes", [])
        ]
        refs += [f"goal:{goal['id']}" for goal in world.get("goals", [])]
        return sorted(refs)
    coverage = read_json(run.coverage_latest)
    return sorted(
        hole["ref"]
        for hole in coverage.get("holes", [])
        if hole.get("reason") == "not_yet_attempted"
    )


def bytes_per_scenario(run: RunPaths) -> int:
    """Mean serialized bytes of the scenarios already sealed, else the default.

    Self-calibrating on purpose: the estimate is the one term in the projection
    that depends on the target rather than on the partition, and a run whose
    scenarios are wordier than the fixture's would otherwise be under-estimated
    every round. Falls back on a missing or empty file rather than dividing by
    zero -- round 1 has neither.
    """
    if not run.scenarios.exists():
        return DEFAULT_BYTES_PER_SCENARIO
    scenarios = read_json(run.scenarios).get("scenarios", [])
    if not scenarios:
        return DEFAULT_BYTES_PER_SCENARIO
    total = sum(len(json.dumps(s, sort_keys=True)) for s in scenarios)
    return max(1, total // len(scenarios))


def partition(refs: list[str], *, cap_bytes: int, per_scenario: int) -> list[list[str]]:
    """Chunk hole refs so each batch's projected output stays inside cap_bytes.

    Adjacent chunks in the order given, not a size-packing: every hole projects
    to the same estimate, so there is nothing for a packer to optimise, and the
    sorted order keeps a capability's cells together where a packer would
    scatter them.

    A budget smaller than one scenario is refused rather than clamped. Clamping
    to one hole per batch would emit a batch that cannot fit its own projection
    -- a cap that does not bind, silently, which is the whole defect class this
    module closes.
    """
    if cap_bytes < per_scenario:
        raise UsageError(
            f"max_scenario_part_bytes={cap_bytes} is below the {per_scenario}-byte "
            "estimate for a single scenario, so no batch could fit one"
        )
    per_batch = cap_bytes // per_scenario
    return [refs[i : i + per_batch] for i in range(0, len(refs), per_batch)]


def _cap_bytes(run: RunPaths) -> int:
    """The manifest's per-member budget, or the default when it carries none.

    Absent rather than required in manifest-0.1.json: a third required limit
    would invalidate every manifest already on disk under runs/.
    """
    if not run.manifest.exists():
        return DEFAULT_SCENARIO_PART_BYTES
    limits = read_json(run.manifest).get("limits", {})
    return limits.get("max_scenario_part_bytes", DEFAULT_SCENARIO_PART_BYTES)


def write_batches(run: RunPaths, *, round_n: int) -> Path | None:
    """Partition this round's closable holes into 02-batches.json.

    Returns None and writes nothing when no hole is closable. That is different
    from writing an empty batches array, which batches-0.1.json refuses: no
    document at all is how the orchestrator learns there is no round to run,
    whereas an empty array would be a partition that lost its own worklist.
    """
    refs = closable_holes(run)
    if not refs:
        return None
    per_scenario = bytes_per_scenario(run)
    cap = _cap_bytes(run)
    batches = partition(refs, cap_bytes=cap, per_scenario=per_scenario)
    write_json(
        run.batches(round_n),
        {
            "schema_version": "0.1",
            "round": round_n,
            "cap_bytes": cap,
            "bytes_per_scenario": per_scenario,
            # Zero-padded so b10 sorts after b09 both as a path segment and in
            # any listing -- the same reason triage's slice ids are s01, not s1.
            "batches": [
                {
                    "id": f"b{i:02d}",
                    "hole_refs": batch,
                    "projected_bytes": len(batch) * per_scenario,
                }
                for i, batch in enumerate(batches, start=1)
            ],
        },
    )
    return run.batches(round_n)
