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
response: the dispatch spent $3.57 over 31 minutes and wrote nothing at all.

Those bytes are measured; the token figure they imply is not. At the ESTIMATED
BYTES_PER_TOKEN below, ~124,545 bytes is ~35,600 tokens, past the 32,000-token
OUTPUT_TOKEN_CEILING -- an inference from an estimate, kept out from under the
MEASURED header above so that header vouches only for what was observed.

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

from rubrica.artifacts import ArtifactError, read_json, write_json
from rubrica.errors import UsageError
from rubrica.findings import Finding
from rubrica.paths import RunPaths

# The measured maximum scenario on run-20260825-094033 was 1,579 serialized
# bytes against a 1,162 mean. The estimate rounds up to the max rather than the
# mean, because a projection that under-estimates produces exactly the failure
# this module exists to prevent, and one that over-estimates only produces one
# more batch than strictly needed.
DEFAULT_BYTES_PER_SCENARIO = 1600

# Claude Code's own default max output tokens for the process dispatch-stage.sh
# spawns. Observed once, by one route only: as the error that killed propose
# round 2 on run-20260825-094033. It is NOT a model limit, and NOT a value this
# repo sets anywhere today -- Task 10 pins it. Recorded here so the budget below
# can be related to it by a test rather than only by a comment, which is what
# test_the_default_member_budget_leaves_half_the_output_ceiling_free does.
OUTPUT_TOKEN_CEILING = 32000

# An ESTIMATE, not a measurement: no file from that run has been tokenized. It
# exists only to make a byte budget and a token ceiling comparable, which needs
# the right order of magnitude rather than a precise ratio.
BYTES_PER_TOKEN = 3.5

# Per-member output budget, in BYTES -- ~8k output tokens at BYTES_PER_TOKEN,
# a quarter of OUTPUT_TOKEN_CEILING. Deliberately a fraction of the ceiling
# rather than just under it: the ceiling counts thinking tokens too, and a
# member also emits its report back to the orchestrator, so the write is not the
# whole response. The units are the trap here -- the ceiling is tokens and this
# is bytes, so the two are comparable only through BYTES_PER_TOKEN. At this
# budget the measured 86 closable holes become 6 batches.
DEFAULT_SCENARIO_PART_BYTES = 28000


# The two spellings of "where the budget came from", so partition's refusal can
# name the lever the operator actually has: correct the manifest key, or set it.
DEFAULT_CAP_SOURCE = "the default per-member output budget (no manifest limit set)"
MANIFEST_CAP_SOURCE = "manifest.json's limits.max_scenario_part_bytes"


def _object_or_refuse(
    path: Path, payload: object, required: tuple[str, ...] = (), where: str = ""
) -> dict:
    """`payload` as a JSON object carrying every key in `required`, or a UsageError.

    The same container door slices.write_slices puts in front of the catalogue,
    and it is here for the same measured reason: this module's callers index keys
    bare, so a payload of the wrong top-level shape raises TypeError or KeyError
    out of a *code* step, which cli.py's catch-all reports as an exit-1
    `[internal]` finding anchored on the RUN ROOT -- the exit-code contract's
    third rule ("a 1 must name the right artifact") breached, and breached
    against an artifact no re-dispatch can repair, since manifest.json is
    intake's own code output. Of the four wrong top-level shapes, `[]` and `"hi"`
    answer `key not in payload` correctly and would reach the missing-field
    refusal, while `None` and `7` raise TypeError; this guard makes all four one
    refusal instead of two refusals and two tracebacks.
    """
    # `where` names the sub-location when the object is nested, because a
    # refusal reading "01-world-model.json is missing outcome_classes" leaves an
    # operator to find WHICH capability in a file with 148 cells in it.
    at = f"{path}{where}"
    if not isinstance(payload, dict):
        raise UsageError(f"{at} is not a JSON object: found {payload!r}")
    missing = [key for key in required if key not in payload]
    if missing:
        raise UsageError(f"{at} is missing required field(s): {missing}")
    return payload


def _rows_with_string_id(
    path: Path, field: str, rows: object, key: str = "id", *, min_rows: int = 0
) -> list[dict]:
    """`rows` as a list of objects each carrying a non-empty string `key`, else UsageError.

    Presence of the array is not enough, and slices.write_slices records both
    halves of why one level out: a row that is not an object raises TypeError
    from the indexing its caller does, and a `key` present but not a string
    reaches an f-string that interpolates it silently -- minting a plausible and
    wrong hole ref that check-refs would later report against the batch plan
    rather than against the artifact that actually carried the defect. Empty is
    refused alongside the non-strings because `cell:/oc` does not match
    coverage-0.1.json's hole_ref pattern, so the only place it could surface is
    layer 1 against this module's own output.
    """
    if not isinstance(rows, list):
        raise UsageError(f"{path}'s {field} is not an array: found {rows!r}")
    # `min_rows` is the schema's own minItems, and only outcome_classes carries
    # one. capabilities, goals and scenarios may all legitimately be empty -- a
    # world model with no capabilities is what write_batches returns None for --
    # so this stays opt-in rather than a blanket non-empty rule. Measured: with
    # the presence check alone, a capability whose outcome_classes was `[]`
    # contributed zero cells in the same silence the presence check just closed,
    # so requiring the key without its minItems left half the hole open.
    if len(rows) < min_rows:
        raise UsageError(
            f"{path}'s {field} has {len(rows)} entries, fewer than the {min_rows} "
            "its schema requires"
        )
    unshaped = [
        i
        for i, row in enumerate(rows)
        if not isinstance(row, dict) or not isinstance(row.get(key), str) or not row[key]
    ]
    if unshaped:
        raise UsageError(
            f"{path} has {field} entries that are not an object with a non-empty "
            f"string {key}, at index {unshaped}"
        )
    return rows


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

    `capabilities`, `goals` and `holes` are required rather than defaulted, and
    that matches layer 1 exactly -- world-model-0.1.json and coverage-0.1.json
    each list them in `required` -- so a document reaching here without one is a
    hand-edit, and refusing it names the artifact that carries the defect.
    """
    world = _object_or_refuse(
        run.world_model, read_json(run.world_model), ("capabilities", "goals")
    )
    if not run.coverage_latest.exists():
        refs: list[str] = []
        for cap in _rows_with_string_id(run.world_model, "capabilities", world["capabilities"]):
            # Required, not defaulted, for the reason capabilities and goals
            # are: world-model-0.1.json lists outcome_classes in
            # capability.required with minItems 1. Measured before this line
            # existed -- a capability without it contributed zero cells in
            # silence, and a world model of only such capabilities made
            # write_batches return None, manufacturing the loop's normal
            # terminal state out of a malformed artifact. 01-world-model.json
            # is reconcile-seal's own code output, so a finding against it is
            # unrepairable by re-dispatch -- the same argument _cap_bytes makes
            # for manifest.json.
            classes = _rows_with_string_id(
                run.world_model,
                f"capabilities[{cap['id']}].outcome_classes",
                _object_or_refuse(
                    run.world_model,
                    cap,
                    ("outcome_classes",),
                    f" capabilities[{cap['id']}]",
                )["outcome_classes"],
                min_rows=1,
            )
            refs.extend(f"cell:{cap['id']}/{oc['id']}" for oc in classes)
        refs.extend(
            f"goal:{goal['id']}"
            for goal in _rows_with_string_id(run.world_model, "goals", world["goals"])
        )
        # Deduped for the reason the coverage branch below is: two capabilities
        # sharing an id, or one carrying the same outcome class twice, would
        # otherwise cost two dispatched writes for one cell.
        return sorted(set(refs))
    coverage = _object_or_refuse(run.coverage_latest, read_json(run.coverage_latest), ("holes",))
    holes = _rows_with_string_id(run.coverage_latest, "holes", coverage["holes"], "ref")
    # Deduped, and the duplicate is not this module's defect: coverage-0.1.json
    # puts no `uniqueItems` on `holes`, so two identical not_yet_attempted refs
    # are a score-stage defect arriving from upstream. The COST is here, though
    # -- one hole would take two batch slots, so a member writes two scenarios
    # for the same cell and rb-instantiate seeds both -- and this is the last
    # code that can drop it before it is paid for in dispatches. A `set` rather
    # than a refusal because a duplicate has an unambiguous correct reading,
    # unlike the malformed shapes above; sorted() was already collapsing order.
    return sorted({hole["ref"] for hole in holes if hole.get("reason") == "not_yet_attempted"})


def bytes_per_scenario(run: RunPaths) -> int:
    """Mean serialized bytes of the scenarios already sealed, else the default.

    Self-calibrating on purpose: the estimate is the one term in the projection
    that depends on the target rather than on the partition, and a run whose
    scenarios are wordier than the fixture's would otherwise be under-estimated
    every round. Falls back on a missing or empty file rather than dividing by
    zero -- round 1 has neither.

    `scenarios` is required and its rows shape-checked, not defaulted, and this
    was the module's worst-shaped hole: every other malformed artifact here now
    produces a refusal, but a `scenarios` of the wrong type produced a
    PLAUSIBLE WRONG NUMBER. Measured -- `{"scenarios": 7}` raised TypeError from
    the sum (the exit-1-against-the-run-root class these guards close), and
    `{"scenarios": "eighteen scenarios"}` iterated the string's characters to a
    3-byte estimate, which on an 86-hole world model emitted ONE batch of all 86
    holes projecting 258 bytes against a real write of ~99,932 -- 387x under, and
    exactly the cap that does not bind, silently, that this module exists to
    close. scenarios-0.1.json lists `scenarios` in `required` and every scenario
    carries a required string `id`, so both checks match layer 1.

    Compact `json.dumps`, not artifacts.canonical_bytes, and the divergence from
    slices.row_bytes is deliberate: what this bounds is one *response*, and a
    model emitting a scenario does not pay for the seal's `indent=2`. row_bytes
    measures the opposite thing -- a shard's real size on disk, which is what a
    member's Read call pays for -- so the two answer different questions and must
    not be unified.
    """
    if not run.scenarios.exists():
        return DEFAULT_BYTES_PER_SCENARIO
    sealed = _object_or_refuse(run.scenarios, read_json(run.scenarios), ("scenarios",))
    scenarios = _rows_with_string_id(run.scenarios, "scenarios", sealed["scenarios"])
    if not scenarios:
        return DEFAULT_BYTES_PER_SCENARIO
    total = sum(len(json.dumps(s, sort_keys=True)) for s in scenarios)
    return max(1, total // len(scenarios))


def partition(
    refs: list[str],
    *,
    cap_bytes: int,
    per_scenario: int,
    cap_source: str = DEFAULT_CAP_SOURCE,
) -> list[list[str]]:
    """Chunk hole refs so each batch's projected output stays inside cap_bytes.

    Adjacent chunks in the order given, not a size-packing: every hole projects
    to the same estimate, so there is nothing for a packer to optimise, and the
    sorted order keeps a capability's cells together where a packer would
    scatter them.

    A budget smaller than one scenario is refused rather than clamped. Clamping
    to one hole per batch would emit a batch that cannot fit its own projection
    -- a cap that does not bind, silently, which is the whole defect class this
    module closes.

    `cap_source` names where the budget came from, because the refusal used to
    say `max_scenario_part_bytes=28000` on a run whose manifest carries no such
    key -- sending a reader to a field that does not exist, when the operator's
    actual lever there is to SET that key rather than to correct it.
    """
    if cap_bytes < per_scenario:
        raise UsageError(
            f"{cap_source} ({cap_bytes} bytes) is below the {per_scenario}-byte "
            "estimate for a single scenario, so no batch could fit one"
        )
    per_batch = cap_bytes // per_scenario
    return [refs[i : i + per_batch] for i in range(0, len(refs), per_batch)]


def _cap_bytes(run: RunPaths) -> tuple[int, str]:
    """The manifest's per-member budget, or the default when it carries none.

    Absent rather than required in manifest-0.1.json: a third required limit
    would invalidate every manifest already on disk under runs/.

    A present-but-malformed value is refused as a UsageError naming the manifest
    and the value, never left to surface downstream. Two reasons, and the second
    is specific to this file: a string reaches `partition`'s comparison and
    raises TypeError, which cli.py's catch-all turns into an exit-1 `[internal]`
    finding against the run root -- wrong code and wrong artifact at once; and
    manifest.json is written by intake in *code*, so a finding against it is
    unrepairable by any re-dispatch, which is the trap CLAUDE.md names for this
    exact file. The range check sits beside the type check because
    manifest-0.1.json constrains the field to `integer, minimum: 1`, and this is
    that same constraint for a manifest that reached here without layer 1.
    `isinstance(True, int)` is True in Python, so a `max_scenario_part_bytes:
    true` would otherwise cap every batch at one byte -- the standing bool guard
    in this repo, present at triage.py:450, manifest.py:149, intake.py:239 and
    seal.py:307.
    """
    if not run.manifest.exists():
        return DEFAULT_SCENARIO_PART_BYTES, DEFAULT_CAP_SOURCE
    manifest = _object_or_refuse(run.manifest, read_json(run.manifest))
    limits = manifest.get("limits", {})
    if not isinstance(limits, dict):
        raise UsageError(f"{run.manifest}'s limits is not a JSON object: found {limits!r}")
    if "max_scenario_part_bytes" not in limits:
        return DEFAULT_SCENARIO_PART_BYTES, DEFAULT_CAP_SOURCE
    cap = limits["max_scenario_part_bytes"]
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
        raise UsageError(
            f"{run.manifest}'s limits.max_scenario_part_bytes must be an integer >= 1: "
            f"found {cap!r}"
        )
    return cap, MANIFEST_CAP_SOURCE


def write_batches(run: RunPaths, *, round_n: int) -> Path | None:
    """Partition this round's closable holes into 02-batches/round-N.json.

    Returns None and writes nothing when no hole is closable. That is different
    from writing an empty batches array, which batches-0.1.json refuses: no
    document at all is how the orchestrator learns there is no round to run,
    whereas an empty array would be a partition that lost its own worklist.
    """
    refs = closable_holes(run)
    if not refs:
        return None
    per_scenario = bytes_per_scenario(run)
    cap, cap_source = _cap_bytes(run)
    batches = partition(refs, cap_bytes=cap, per_scenario=per_scenario, cap_source=cap_source)
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


# score-part-0.1.json's own `status` enum, and deliberately NOT
# scenarios-0.1.json's, which also admits `proposed`. A ruling exists to CHANGE
# a status, and `proposed` is what a scenario already carries out of its propose
# member, so a ruling naming it would be a no-op that still had to be honoured.
# A whitelist rather than isinstance(status, str) because _apply_rulings writes
# this value straight onto the scenario: an arbitrary string would make the
# assembled 02-scenarios.json fail its own schema, and that document is code
# output, so the finding would be unrepairable by any re-dispatch.
_RULING_STATUSES = frozenset({"active", "duplicate", "rejected"})

# (the field a status requires, the status that requires it) -- score-part-0.1.json
# spells the same pair as two if/then clauses, and scenarios-0.1.json repeats them
# on the sealed scenario, so the fold and the rejection each carry exactly one.
_STATUS_FIELDS: tuple[tuple[str, str], ...] = (
    ("duplicate_of", "duplicate"),
    ("rejected_reason", "rejected"),
)

# The reads in this module split by WHO WROTE the artifact, and the split is the
# exit-code contract rather than a style choice. The world model and the sealed
# scenario list are code output, so a malformed one is a misconfigured run and
# `_object_or_refuse`/`_rows_with_string_id` raise the UsageError that maps to
# exit 2 -- what closable_holes and bytes_per_scenario already do. The propose
# and score parts are MODEL output, so a malformed one is a repairable stage
# defect, and "a stage defect must never surface as 2" makes it a Finding on the
# functions below instead. Both shapes still exist for the same underlying
# reason: indexing a key bare out of a code step raises KeyError or TypeError,
# which cli.py's catch-all reports as an exit-1 `[internal]` finding anchored on
# the run root -- the wrong artifact, every time.


def collect_scenarios(run: RunPaths) -> tuple[list[dict], list[Finding]]:
    """Every part's scenarios, ordered by (round, batch id, position in part).

    Deterministic ordering is the whole point: this list becomes
    02-scenarios.json, and two runs with identical parts must produce identical
    bytes. Round and batch id are both sorted rather than taken in directory
    order, because a filesystem's order is not a promise -- and the sorting is
    RunPaths' (scenario_part_rounds, scenario_part_batch_ids), so this module
    never parses a round out of a filename and the two seals cannot disagree
    about what a round directory is.
    """
    scenarios: list[dict] = []
    findings: list[Finding] = []
    seen: dict[str, str] = {}
    for round_n in run.scenario_part_rounds():
        for name in run.unsafe_scenario_part_names(round_n):
            findings.append(
                Finding(
                    run.scenario_round_dir(round_n),
                    "rounds",
                    "",
                    f"part name {name!r} in round {round_n} is not a safe path segment, "
                    "so this seal will not join it into a path",
                )
            )
        for batch_id in run.scenario_part_batch_ids(round_n):
            path = run.scenario_part(round_n, batch_id)
            try:
                part = read_json(path)
            except ArtifactError as exc:
                findings.append(Finding(path, "rounds", "", str(exc)))
                continue
            if not isinstance(part, dict) or not isinstance(part.get("scenarios"), list):
                findings.append(
                    Finding(path, "rounds", "", "part is not an object carrying a scenarios array")
                )
                continue
            for i, scenario in enumerate(part["scenarios"]):
                if not isinstance(scenario, dict) or not isinstance(scenario.get("id"), str):
                    findings.append(
                        Finding(path, "rounds", f"/scenarios/{i}", "scenario has no string id")
                    )
                    continue
                sid = scenario["id"]
                where = f"round {round_n} batch {batch_id}"
                if sid in seen:
                    findings.append(
                        Finding(
                            path,
                            "rounds",
                            f"/scenarios/{i}/id",
                            f"scenario id {sid} is already claimed by {seen[sid]}; members "
                            "mint their own ids, so a collision has to be caught here -- the "
                            "merged array would simply carry it twice",
                        )
                    )
                    continue
                seen[sid] = where
                scenarios.append(scenario)
    return scenarios, findings


def _apply_rulings(run: RunPaths, scenarios: list[dict]) -> list[Finding]:
    """Fold every round's score rulings into the assembled scenarios, in place.

    Rounds are applied in ascending order so a later round may overturn an
    earlier ruling. rb-score's Output section asks for "do not re-open a ruling
    that nothing new bears on", never "statuses are frozen after the round that
    set them" -- a rejection notice carried into a re-dispatch is exactly the
    case where changing one is the point.

    Called only on a clean collect, never on one that reported a finding. A part
    that did not parse means every scenario it held is absent from `by_id`, so
    every ruling naming one would be reported here as "no propose part wrote it"
    -- a finding against 03-score for a defect in 02-scenarios, and this package
    has twice shipped a checker that named the wrong artifact.
    """
    findings: list[Finding] = []
    by_id = {s["id"]: s for s in scenarios}
    for round_n in run.score_part_rounds():
        path = run.score_part(round_n)
        try:
            part = read_json(path)
        except ArtifactError as exc:
            findings.append(Finding(path, "rounds", "", str(exc)))
            continue
        if not isinstance(part, dict) or not isinstance(part.get("rulings"), list):
            findings.append(
                Finding(path, "rounds", "", "score part is not an object carrying a rulings array")
            )
            continue
        for i, ruling in enumerate(part["rulings"]):
            sid = ruling.get("scenario_id") if isinstance(ruling, dict) else None
            if not isinstance(sid, str):
                findings.append(
                    Finding(path, "rounds", f"/rulings/{i}", "ruling has no string scenario_id")
                )
                continue
            status = ruling.get("status")
            if status not in _RULING_STATUSES:
                # Checked rather than indexed bare, and checked against the enum
                # rather than against `str`: see _RULING_STATUSES for both halves.
                findings.append(
                    Finding(
                        path,
                        "rounds",
                        f"/rulings/{i}/status",
                        f"ruling for {sid} carries status {status!r}, which is not one of "
                        f"{sorted(_RULING_STATUSES)}",
                    )
                )
                continue
            required = [field for field, keep in _STATUS_FIELDS if status == keep]
            missing = [field for field in required if not isinstance(ruling.get(field), str)]
            if missing:
                findings.append(
                    Finding(
                        path,
                        "rounds",
                        f"/rulings/{i}",
                        f"ruling for {sid} has status {status!r} but no string "
                        f"{missing[0]}, which that status requires",
                    )
                )
                continue
            target = by_id.get(sid)
            if target is None:
                findings.append(
                    Finding(
                        path,
                        "rounds",
                        f"/rulings/{i}/scenario_id",
                        f"ruling names {sid}, which no propose part wrote",
                    )
                )
                continue
            target["status"] = status
            # Set only what the new status requires, and clear the other, so a
            # scenario rejected after having been folded does not keep a stale
            # duplicate_of that check_scenarios would then resolve happily -- it
            # asks only whether the target exists, so nothing would report it.
            for field, keep in _STATUS_FIELDS:
                if status == keep:
                    target[field] = ruling[field]
                else:
                    target.pop(field, None)
    return findings


def seal_scenarios(run: RunPaths) -> tuple[Path | None, list[Finding]]:
    """Assemble 02-scenarios.json from every propose part and every score ruling.

    A pure function of those parts: it never reads its own output, which is what
    makes it idempotent and lets it run twice per round -- after propose, so
    score has a document to read, and after score, so instantiate sees the
    statuses -- with no way for the second run to disagree with the first.

    Writes nothing when any finding is reported, for the reason seal.py gives:
    a half-assembled document would clear layer 1 for the fields it did manage
    to fill and read as a complete scenario list to a human at gate 2.
    """
    scenarios, findings = collect_scenarios(run)
    if findings:
        # Before the ruling pass, not merged with it: _apply_rulings' docstring
        # records the misattributed cascade that ordering produces.
        return None, findings
    if not scenarios:
        # Propose has not run. Not a refusal: reporting one would make the
        # orchestrator retry a stage that was never dispatched.
        return None, []
    findings = _apply_rulings(run, scenarios)
    if findings:
        return None, findings
    world = _object_or_refuse(run.world_model, read_json(run.world_model), ("denominator",))
    # Echoed from the world model, never defaulted, and this is the one place a
    # default would be silently wrong rather than loudly: refs.check_scenarios
    # compares this field to world["denominator"]["version"] for EQUALITY, so a
    # fallback of 1 against a world model at 2 is a check-refs finding against a
    # document this code just wrote -- unrepairable by any re-dispatch. Presence
    # only, not an integer check, and the line between that and _cap_bytes' type
    # check is which layer already owns the field: world-model-0.1.json lists
    # denominator in `required` and constrains version to `integer, minimum: 1`,
    # while manifest-0.1.json does not require max_scenario_part_bytes at all, so
    # layer 1 covers this one and covers nothing there. Same ruling reconcile.seal
    # states for its own payload keys.
    denominator = _object_or_refuse(
        run.world_model, world["denominator"], ("version",), " denominator"
    )
    write_json(
        run.scenarios,
        {
            "schema_version": "0.1",
            "denominator_version": denominator["version"],
            "scenarios": scenarios,
        },
    )
    return run.scenarios, findings
