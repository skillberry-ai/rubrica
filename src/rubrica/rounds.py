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

import copy
import json
from pathlib import Path

from rubrica.artifacts import ArtifactError, read_json, write_json
from rubrica.errors import UsageError
from rubrica.findings import Finding
from rubrica.paths import RunPaths

# `_cells` is private and reached from here deliberately, named in the import line
# rather than through the module so the coupling is visible where a reader looks
# for it: seal_score needs BOTH halves of refs' cell split -- the wide set to know
# which cells the world model DECLARES, and the narrow one to know which of them a
# scenario could be driven through.
from rubrica.refs import OPEN_STATUSES, _cells, drivable_cells

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


def _declared_cells(run: RunPaths, world: dict) -> list[tuple[str, str]]:
    """Every (capability_id, outcome_class_id) the world model declares, in its order.

    Two callers want different halves of this. `closable_holes` wants the
    enumeration, to mint one hole ref per cell on round 1. `seal_score` wants the
    *refusal*: `capability_matrix` is a pure function of a dict, so it has no path
    to name and no way to refuse, which puts the door at the read instead.

    `outcome_classes` is required rather than defaulted, and world-model-0.1.json
    lists it in capability.required with minItems 1. Measured before this door
    existed -- a capability without it contributed zero cells in silence, and a
    world model of only such capabilities made write_batches return None,
    manufacturing the loop's normal terminal state out of a malformed artifact.
    The same silence shrinks a coverage denominator to fit, which is the failure
    rb-score's own refusal conditions rank above every other.
    01-world-model.json is reconcile-seal's own code output, so a finding against
    it is unrepairable by re-dispatch -- the argument _cap_bytes makes for
    manifest.json, and the reason this raises rather than reporting.
    """
    cells: list[tuple[str, str]] = []
    for cap in _rows_with_string_id(run.world_model, "capabilities", world["capabilities"]):
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
        cells.extend((cap["id"], oc["id"]) for oc in classes)
    return cells


def closable_holes(run: RunPaths) -> list[str]:
    """The hole refs a new scenario could close this round, sorted.

    Round 1 has no coverage report, and that is the normal shape rather than a
    missing file -- rb-propose's Inputs section says so outright -- so every
    DRIVABLE capability x outcome-class cell and every goal is open by default and
    the worklist is enumerated from the world model. Drivable, not declared: a
    capability with no binding.tool cannot be closed by proposing at all, so
    offering the cell spends a round producing a scenario rb-instantiate cannot
    seed and emit drops.

    From round 2 the report's holes are the worklist, filtered to
    `not_yet_attempted` and then with the declared-but-undrivable refs SUBTRACTED.
    Subtracted, not narrowed to the drivable set, and
    test_a_round_two_hole_ref_no_capability_declares_is_still_offered pins the
    difference: a `cell:` ref no capability declares at all is left in the worklist
    rather than swallowed, because a hole ref resolving to nothing is a
    coverage-document defect and check-refs is the layer that reports it. The other
    three reasons are not closable by proposing, however good the scenario:
    `unreachable` and `out_of_scope` are cells the suite is not trying to cover, and
    `blocked_by_gap` means the world model does not yet support a scenario there, so
    proposing anyway produces one rb-instantiate cannot honestly seed.

    Both filters are needed on that branch and neither subsumes the other. The
    reason filter catches score's own `unreachable` and `out_of_scope` holes on an
    undrivable cell; it does not catch a `not_yet_attempted` one, and score can
    write those -- the prompt the measured documents were scored by (5cd2358) stated
    the wide rule in BOTH Method step 4 and Invariant 1, with the string `binding`
    nowhere in the file, and seal_score's injection defers to a hole score wrote for
    the same cell by design. The Method since d6786a4 names the undrivable case and
    calls `not_yet_attempted` the one wrong reason there, but no dispatch has
    measured that it obeys, so the drivability filter is what closes that path
    either way -- an undrivable cell is closable in no round rather than in every
    round but the first.

    `capabilities`, `goals` and `holes` are required rather than defaulted, and
    that matches layer 1 exactly -- world-model-0.1.json and coverage-0.1.json
    each list them in `required` -- so a document reaching here without one is a
    hand-edit, and refusing it names the artifact that carries the defect.
    """
    world = _object_or_refuse(
        run.world_model, read_json(run.world_model), ("capabilities", "goals")
    )
    # Hoisted above the branch because BOTH branches drop the undrivable cells, and
    # filtering one of them only is what made round 2 reinstate what round 1 had
    # closed: score may hole an undrivable cell `not_yet_attempted`, which the reason
    # filter below passes, so the cell came back into the worklist one round after
    # being kept out of it.
    #
    # _declared_cells is called unfiltered on purpose: it is the door that refuses a
    # capability with no outcome_classes, and an UNBOUND capability missing them is
    # exactly as malformed as a bound one. Filter the enumeration afterwards, so
    # narrowing the worklist cannot narrow the check.
    #
    # And called BEFORE drivable_cells, which is why it is bound to a name here
    # rather than left inline as the comprehension's iterable: this door turns a
    # malformed `capabilities` or `outcome_classes` into a UsageError naming the
    # world model, while drivable_cells is a bare comprehension over the same
    # keys. Measured with the two the other way round -- `"capabilities": 7` came
    # back as a TypeError out of drivable_cells instead of the "is not an array"
    # refusal, which from a code step names the run root and not the artifact
    # carrying the defect.
    #
    # Hoisting therefore also means the round-2 branch refuses a malformed
    # `capabilities` or `outcome_classes` that it previously walked straight past,
    # never having enumerated the world model at all. That is a widening and it is
    # deliberate: 01-world-model.json does not become well-formed because a coverage
    # document exists beside it, and the silent-zero-cells failure _declared_cells
    # documents is worth the same door on every round, not only the first.
    declared = _declared_cells(run, world)
    drivable = drivable_cells(world)
    if not run.coverage_latest.exists():
        refs: list[str] = [
            f"cell:{cap_id}/{oc_id}"
            for cap_id, oc_id in declared
            # An undrivable cell is not closable by proposing: rb-instantiate could
            # not seed it and emit would drop the test, so offering it spends a
            # round to produce nothing. This is the same judgment the coverage
            # branch below already makes for `unreachable`.
            if (cap_id, oc_id) in drivable
        ]
        refs.extend(
            f"goal:{goal['id']}"
            for goal in _rows_with_string_id(run.world_model, "goals", world["goals"])
        )
        # Deduped for the reason the coverage branch below is: two capabilities
        # sharing an id, or one carrying the same outcome class twice, would
        # otherwise cost two dispatched writes for one cell.
        return sorted(set(refs))
    coverage = _object_or_refuse(run.coverage_latest, read_json(run.coverage_latest), ("holes",))
    # BOTH keys, mirroring progress()' pass over a prior matrix's cells, and
    # `reason` is here for exactly the reason `ref` is: this function READS it, so
    # a malformed one has to refuse rather than filter itself out of the worklist.
    #
    # Measured before this door covered it, on round 2 against a latest.json
    # carrying one otherwise well-formed hole: with `reason` absent, and again
    # with `reason: 7`, the filter below matched neither, closable_holes returned
    # [], write_batches returned None, and `rubrica propose-batches` printed "no
    # closable holes" and exited 0 having written nothing -- the loop's normal
    # TERMINAL STATE manufactured out of a malformed coverage document, which the
    # orchestrator then branches on to stop the loop. The same hole with
    # `reason: "not_yet_attempted"` wrote its plan, so nothing in the run's shape
    # distinguished the two outcomes.
    #
    # That is the third instance of this class in this loop: _declared_cells'
    # outcome_classes door and bytes_per_scenario's `scenarios` door were both
    # closed for the same reason, that a malformed artifact must never produce a
    # plausible-looking normal outcome. UsageError and not a Finding by the
    # who-wrote-it rule -- 03-coverage/latest.json is seal_score's own code
    # output, so no re-dispatch of any prompt could repair it. coverage-0.1.json
    # requires both keys on a hole, which is what keeps this a fix rather than an
    # emergency; a hole can still reach here unvalidated, which is why the read
    # refuses rather than trusting that layer.
    holes = coverage["holes"]
    for key in ("ref", "reason"):
        holes = _rows_with_string_id(run.coverage_latest, "holes", holes, key)
    # The refs form of what this branch excludes, spelled the way seal_score spells
    # its own `undrivable_refs` so the two cannot drift: the cells the world model
    # declares and the target cannot drive. Computed here rather than beside
    # `drivable` above because only this branch needs it -- round 1 has the pairs
    # themselves and tests membership positively.
    #
    # Subtracted rather than intersected, and the difference is load-bearing: this
    # drops exactly the declared-but-undrivable refs, leaving a `cell:` ref no
    # capability declares at all alone. Keeping only the drivable refs would swallow
    # that one too, and a hole ref resolving to nothing is a coverage-document defect
    # check-refs is the layer to report -- the same division of labour the round-1
    # branch draws.
    undrivable_refs = {f"cell:{cap_id}/{oc_id}" for cap_id, oc_id in set(declared) - drivable}
    # Deduped, and the duplicate is not this module's defect: coverage-0.1.json
    # puts no `uniqueItems` on `holes`, so two identical not_yet_attempted refs
    # are a score-stage defect arriving from upstream. The COST is here, though
    # -- one hole would take two batch slots, so a member writes two scenarios
    # for the same cell and rb-instantiate seeds both -- and this is the last
    # code that can drop it before it is paid for in dispatches. A `set` rather
    # than a refusal because a duplicate has an unambiguous correct reading,
    # unlike the malformed shapes above; sorted() was already collapsing order.
    return sorted(
        {
            hole["ref"]
            for hole in holes
            if hole["reason"] == "not_yet_attempted"
            # An undrivable cell is not closable by proposing in ANY round, and the
            # reason filter beside this does not reach it: score writes the hole
            # itself as `not_yet_attempted` -- rb-score as of 5cd2358, which is the
            # prompt the documents behind this clause were scored by, described its
            # capability rows as one per declared pair in Method step 4 AND in
            # Invariant 1, and the string `binding` appeared nowhere in that file
            # (`git show 5cd2358:src/rubrica/skills/rb-score/SKILL.md | grep -c
            # binding` is 0).
            # The Method since d6786a4 names the undrivable case and calls
            # `not_yet_attempted` the one wrong reason there, but no dispatch has
            # measured that it obeys, so this clause stays whatever the prompt says
            # -- and seal_score's injection defers to score's hole for the same cell
            # on purpose, so the mechanical `unreachable` never replaces it. Without
            # this clause round 2 handed rb-propose back precisely the cells round 1
            # had kept from it, at the cost the design cites as the whole price of
            # the defect: a scenario rb-instantiate cannot seed and emit drops.
            #
            # This does omit the hole from the worklist while the coverage document
            # still shows it `not_yet_attempted`, so the worklist alone does not say
            # why nobody worked the cell. The hole itself stays in the document a
            # human reads at gate 2, and that is what accounts for it.
            #
            # `check-refs` deliberately does not also report it, and that was tried
            # and reverted rather than never considered: exit 1 tells rb-orchestrate
            # "a repairable stage defect, spend the one repair attempt", and an
            # unbound capability is repairable by no re-dispatch at all --
            # rb-reconcile-capabilities' section 5 tells the pass to leave `binding`
            # off rather than guess a tool name, so the pass did the right thing and
            # nothing downstream can add one. `check-refs` runs after reconcile-seal
            # and *before* HUMAN GATE 1, so a finding there WOULD HAVE halted the run
            # ahead of the gate it was meant to be read at -- rb-orchestrate's A3
            # reads an exit 1 as a repairable stage defect and A4 spends one
            # re-dispatch and then halts, which makes that unavoidable rather than
            # likely. Derived, not observed: what was measured on
            # run-20260827-070444 is check-refs standalone at exit 1 with 20 stdout
            # lines, 19 of 24 capabilities named plus the stale capability_cells
            # line. No orchestrated run was dispatched against such a world model,
            # so nobody has watched A4 halt on one. An earlier signal belongs on the
            # layer CLAUDE.md keeps for exactly this, the reports that always exit
            # clean on a readable run: gate-brief, not check-refs.
            and hole["ref"] not in undrivable_refs
        }
    )


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
    holes projecting 258 bytes against a projected write of ~99,932 -- 387x
    under, and exactly the cap that does not bind, silently, that this module
    exists to close. scenarios-0.1.json lists `scenarios` in `required` and every scenario
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
    in this repo, present at triage.py:456 (`digest_body_chars`), manifest.py:176
    (`set_limit`'s requested limits), intake.py:247 (`root_index`) and seal.py:311
    (a disposition's `priority`) -- each of those the guard clause itself, not the
    comment above it.
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
            #
            # Round-scoped, and that half is load-bearing rather than cosmetic.
            # rb-propose has each member mint scenario ids beginning
            # `sc-<batch_id>-`, numbering from its own batch's position, and its
            # invariant 4 states the prefix is the whole of what stops two members
            # choosing the same id. Without the round term that was true within a
            # round and false across rounds: every round's first batch was `b01`,
            # so a round-2 member numbering from position minted `sc-b01-01` again
            # and seal_scenarios correctly refused the round. Measured on
            # run-20260906-102327 round 2. The round belongs in the id rather than
            # in a second field the prompt has to read because this way the
            # namespace is distinct in CODE -- the member needs to know nothing
            # about round 1 to avoid it, which also closes the contract gap that
            # sent two round-2 members reading files their `reads` forbids in
            # search of the ids already taken.
            "batches": [
                {
                    "id": f"r{round_n}-b{i:02d}",
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

# coverage-0.1.json's own `verdict` enum and its hole `reason` enum, whitelisted
# here for exactly the reason _RULING_STATUSES is: seal_score copies both onto the
# coverage document and its latest.json copy untouched, and both are CODE output,
# so a value outside either enum makes an artifact no re-dispatch can repair fail
# its own schema. Measured before these two guards existed, each on an otherwise
# clean round-1 part: `verdict: "keep_going"` and a hole `reason` of
# `because_i_said_so` each let `rubrica score-seal` exit 0 and WRITE both
# documents, after which `validate --stage score-seal` reported findings against
# them. Mitigated rather than unreachable -- `validate --stage score` sees the part
# first -- which is why the sibling comment above must not be read as covering
# these two: it argues the who-wrote-it rule, and that rule applies identically
# here. Restated rather than read out of the schema, matching _RULING_STATUSES;
# test_rounds.py pins each against the schema enum it mirrors.
_VERDICTS = frozenset({"continue", "converged", "halted_no_progress", "halted_round_cap"})
_HOLE_REASONS = frozenset({"not_yet_attempted", "unreachable", "out_of_scope", "blocked_by_gap"})

# (the field a status requires, the status that requires it) -- score-part-0.1.json
# spells the same pair as two if/then clauses, and scenarios-0.1.json repeats them
# on the sealed scenario, so the fold and the rejection each carry exactly one.
_STATUS_FIELDS: tuple[tuple[str, str], ...] = (
    ("duplicate_of", "duplicate"),
    ("rejected_reason", "rejected"),
)

# WHO WROTE THE ARTIFACT is what decides the exit code for a malformed one, and
# that is the exit-code contract rather than a style choice. Do NOT tidy the two
# shapes below back into one -- they answer different questions.
#
#   manifest.json (intake), 01-world-model.json (reconcile-seal) and
#   02-scenarios.json (this module) are CODE output. No re-dispatch of any prompt
#   can repair them, so reporting a repairable stage defect against one would be a
#   lie to the orchestrator: it would spend its one retry rewriting an artifact no
#   model wrote. These go through `_object_or_refuse`/`_rows_with_string_id`, which
#   raise the UsageError cli.py maps to exit 2 -- what closable_holes,
#   bytes_per_scenario and _cap_bytes already do.
#
#   The propose parts (02-scenarios/round-N/bNN.json) and the score parts
#   (03-score/round-N.json) are MODEL output. A malformed one is exactly a
#   repairable stage defect and the orchestrator has to be able to re-dispatch
#   that one member, so it is a Finding at exit 1 NAMING THE PART -- never a
#   UsageError, because "a stage defect must never surface as 2".
#
# Both shapes exist for the same underlying reason: indexing a key bare out of a
# code step raises KeyError or TypeError, which cli.py's catch-all reports as an
# exit-1 `[internal]` finding anchored on the run root -- the wrong artifact,
# every time, and at the wrong exit code half the time.


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
            # Split rather than one combined guard, and the split is the POINTER:
            # `/scenarios` does not resolve in a part that is not an object at
            # all, so the two conditions cannot honestly share one. `_object_or_refuse`
            # already draws this line for the artifacts it guards, and refs.py
            # points at an absent member the same way (catalogue_facts'
            # candidate_bytes entry, refs.py's check_catalogue_facts).
            if not isinstance(part, dict):
                findings.append(Finding(path, "rounds", "", "part is not a JSON object"))
                continue
            if not isinstance(part.get("scenarios"), list):
                findings.append(
                    Finding(path, "rounds", "/scenarios", "part carries no scenarios array")
                )
                continue
            for i, scenario in enumerate(part["scenarios"]):
                if not isinstance(scenario, dict):
                    findings.append(
                        Finding(path, "rounds", f"/scenarios/{i}", "scenario is not a JSON object")
                    )
                    continue
                if not isinstance(scenario.get("id"), str):
                    findings.append(
                        Finding(path, "rounds", f"/scenarios/{i}/id", "scenario has no string id")
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
                # Copied, not aliased, and this is NOT redundant with read_json
                # re-parsing: _apply_rulings folds statuses in PLACE, and
                # seal_scenarios runs twice per round (after propose so score has
                # a document, again after score so instantiate sees the statuses).
                # Any caller that collects once and reads the list either side of
                # a fold -- which is the shape Task 5's matrices want -- would
                # otherwise watch its own rows change under it. A deepcopy per row
                # is nothing against the byte-identity guarantee this seal exists
                # to hold; measured green in both directions today only because
                # nothing yet caches a part document, which a cache added here
                # later would silently undo.
                scenarios.append(copy.deepcopy(scenario))
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
        if not isinstance(part, dict):
            findings.append(Finding(path, "rounds", "", "score part is not a JSON object"))
            continue
        if not isinstance(part.get("rulings"), list):
            findings.append(
                Finding(path, "rounds", "/rulings", "score part carries no rulings array")
            )
            continue
        # Reset for EVERY part, never hoisted out of this loop, and that scoping
        # is the whole ruling. Two rulings for one scenario in ONE part are a
        # single dispatch contradicting itself, which is a defect. The same pair
        # across TWO parts is a later round overturning an earlier ruling, which
        # rb-score's Output section sanctions outright -- it asks for "do not
        # re-open a ruling that nothing new bears on", never "statuses are frozen
        # after the round that set them" -- so a global register would refuse the
        # supported case along with the defect.
        #
        # Measured before this guard existed, on rulings [{sc-1, rejected,
        # out_of_scope}, {sc-1, active}] in one part: `validate --stage` against
        # score-part-0.1.json returned NO findings, because that schema puts no
        # uniqueness constraint on `rulings`; seal_scenarios returned (path, [])
        # and sealed status `active` with the rejection and its rejected_reason
        # gone. This is the scenario-id collision hole in the other artifact --
        # the merged document agrees with whatever it was handed, and
        # check_scenarios indexes that merged document, so it agrees too. The
        # seal is the only place it can be caught.
        ruled: dict[str, int] = {}
        for i, ruling in enumerate(part["rulings"]):
            # Split from the scenario_id check for the reason the part-container
            # guard above is split: `/rulings/N/scenario_id` does not resolve in a
            # ruling that is not an object at all.
            if not isinstance(ruling, dict):
                findings.append(
                    Finding(path, "rounds", f"/rulings/{i}", "ruling is not a JSON object")
                )
                continue
            sid = ruling.get("scenario_id")
            if not isinstance(sid, str):
                findings.append(
                    Finding(
                        path,
                        "rounds",
                        f"/rulings/{i}/scenario_id",
                        "ruling has no string scenario_id",
                    )
                )
                continue
            # Registered on the id claim alone, before the shape guards below, so
            # a part naming one scenario twice is reported once for the duplicate
            # whether or not either ruling is otherwise well formed.
            if sid in ruled:
                findings.append(
                    Finding(
                        path,
                        "rounds",
                        f"/rulings/{i}/scenario_id",
                        f"this part already ruled on {sid} at /rulings/{ruled[sid]}; one score "
                        "dispatch contradicting itself is a defect, and the sealed document "
                        "would carry only the last of the two",
                    )
                )
                continue
            ruled[sid] = i
            status = ruling.get("status")
            # The `isinstance` is the same door _hole_refs puts in front of a hole's
            # reason, and for the same measured reason rather than for symmetry: a
            # `frozenset` membership test hashes its operand, so `status: []` or
            # `status: {}` raised TypeError here and surfaced as an exit-1
            # `[internal]` finding on the RUN ROOT instead of a finding naming
            # `/rulings/N/status`. Pre-existing rather than introduced with the
            # whitelist, and closed alongside its sibling because the two are one
            # line apart in kind.
            if not isinstance(status, str) or status not in _RULING_STATUSES:
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
                        f"/rulings/{i}/{missing[0]}",
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


def _any_part_exists(run: RunPaths) -> bool:
    """Whether any propose member wrote a part at all, in any round.

    The discriminator between the loop's two DIFFERENT terminal signals, which a
    scenario count of zero collapses into one:

      * no part file anywhere -- propose was never dispatched, and seal_scenarios
        writes nothing;
      * a part per batch, every one carrying `scenarios: []` -- every member read
        its batch and could close none of it, which is a real outcome the refusal
        conditions exist to produce, and seal_scenarios seals an EMPTY document.

    Sealing the second is what keeps an honest total refusal distinguishable from
    a stage that never ran: rb-score needs a document to read, and score
    computing its verdict over zero scenarios is how the loop learns it made no
    progress. scenarios-0.1.json puts no `minItems` on `scenarios`, so the empty
    document is schema-valid.

    A third signal is `write_batches` returning None -- no closable hole, so
    there was no round to run. Do not collapse it into either of the two above:
    that one says the worklist was empty before any member was dispatched, while
    the empty seal says members ran and declined.

    Batch ids rather than `scenario_part_rounds()` alone, because the question is
    whether a PART exists: a round directory that exists and holds no part file
    is still the never-dispatched case.
    """
    return any(run.scenario_part_batch_ids(round_n) for round_n in run.scenario_part_rounds())


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
    if not _any_part_exists(run):
        # Propose has not run. Not a refusal: reporting one would make the
        # orchestrator retry a stage that was never dispatched. Note that this
        # is NOT `if not scenarios` -- see _any_part_exists for the second,
        # different terminal signal that test would have swallowed.
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


def _live_statuses() -> frozenset[str]:
    """Statuses that still count toward coverage: a test may yet ship for them.

    refs.OPEN_STATUSES, not a second spelling of it, and the two are the same
    object rather than merely equal today. refs.check_coverage computes its own
    `live_ids` from that set and reports every row this seal marks covered whose
    every credit is dead, so a divergence would not be a style difference -- it
    would be this code writing a coverage document that check-refs then refuses,
    with the disagreement invisible in either file. dedupe.py and stability.py
    already import it for the reason its own comment gives ("Shared with
    dedupe.py, which must exclude the same set").

    Named here anyway, rather than used inline, because this is where the reason
    coverage cares about the set gets written down: `duplicate` and `rejected`
    are dead for coverage because no test ships for them, which is a different
    question from refs.JUDGED_STATUSES' "may appear under 04/05/06".
    """
    return OPEN_STATUSES


def capability_matrix(world: dict, scenarios: list[dict]) -> dict:
    """One cell per capability x outcome-class pair the target can be driven on.

    Not every pair the world model *declares* -- that was the rule before the
    undrivable denominator (docs/design/findings.md) was closed, and the fourth
    bullet below is the narrowing that replaced it. This line is worth its own
    correction because it went on saying "declares" after the body below stopped
    meaning it, so a reader grepping for the change that IS that narrowing met the
    superseded rule first and its replacement twelve lines later.

    Transcribed from rb-score's Method step 4, which already specifies it as a
    pure function of the world model and the scenario list -- so this takes over
    an arithmetic step, not a judgment. What score still decides is everything
    this cannot compute: which pairs are one test, which scenarios to turn down,
    and why an uncovered row is uncovered.

    The rules from that step that are easy to get subtly wrong, every one of
    them load-bearing (unnumbered on purpose: the count was "two" while three
    bullets stood beneath it, which is the same defect this repo bans in a
    heading that counts something that grows):

    * Enumerate from the world model, never from the scenario list. A matrix
      holding only the cells some scenario happens to claim reports 100% of a
      denominator it shrank to fit.
    * `scenario_ids` lists every scenario *claiming* the cell, including the
      folded and the rejected, while `covered` is true only if one of them is
      still live. The asymmetry is deliberate: a cell claimed only by scenarios
      that will never ship is a hole again.
    * Enumerate the DRIVABLE cells, not every declared one. A capability with no
      binding.tool cannot be driven through the target -- emit.bindings drops it --
      so a row for it is a scored target no emitted test could hit, and pct would
      divide by a number the denominator does not hold. seal_score records those
      cells as `unreachable` holes instead, so the report still accounts for all of
      them. Measured on run-20260827-070444: 37 of 56 rows were undrivable.

    Pure, so it cannot refuse a malformed world model -- it has no path to name.
    `_declared_cells` is that door, and `seal_score` calls it first.
    """
    live_statuses = _live_statuses()
    live = {s["id"] for s in scenarios if s.get("status") in live_statuses}
    # Computed once outside the loop rather than re-derived per cell: it is a set
    # comprehension over the whole capability list, and the membership test below
    # is what the narrowing is.
    drivable = drivable_cells(world)
    cells = []
    for cap in world.get("capabilities", []):
        for oc in cap.get("outcome_classes", []):
            if (cap["id"], oc["id"]) not in drivable:
                continue
            claimants = sorted(
                s["id"]
                for s in scenarios
                if any(
                    ref.get("capability_id") == cap["id"]
                    and ref.get("outcome_class_id") == oc["id"]
                    for ref in s.get("capability_refs", [])
                )
            )
            cells.append(
                {
                    "capability_id": cap["id"],
                    "outcome_class_id": oc["id"],
                    "scenario_ids": claimants,
                    "covered": any(sid in live for sid in claimants),
                }
            )
    return _summarise(cells, "cells")


def goal_matrix(world: dict, scenarios: list[dict]) -> dict:
    """One row per goal the world model declares.

    Transcribed from rb-score's Method step 5. Unlike a capability cell, a goal
    row's `scenario_ids` carries only the live scenarios, and that asymmetry is
    the step's own: `hop_depths_present` is derived from this row's membership,
    so leaving a folded scenario in credits the goal with a hop depth no shipped
    test reaches -- and refs.check_coverage recomputes the depths from whatever
    ids it finds there, so the two have to agree about which ids belong.

    `hop_depths_expected` is copied from the goal, not trimmed to what the
    scenarios reached. Trimming is how a goal exercised at one depth of two
    reaches 100% without ever testing the multi-hop half the suite exists to
    probe. Sorted rather than echoed in the goal's own order because two runs
    with identical parts must produce byte-identical output; check_coverage
    compares the two as sets, so the order is this seal's to fix.
    """
    live_statuses = _live_statuses()
    rows = []
    for goal in world.get("goals", []):
        mine = [
            s
            for s in scenarios
            if s.get("status") in live_statuses and s.get("goal_id") == goal["id"]
        ]
        expected = sorted(set(goal["expected_hop_depths"]))
        present = sorted({s["hop_depth"] for s in mine})
        rows.append(
            {
                "goal_id": goal["id"],
                "scenario_ids": sorted(s["id"] for s in mine),
                "hop_depths_present": present,
                "hop_depths_expected": expected,
                "covered": bool(mine) and set(expected) <= set(present),
            }
        )
    return _summarise(rows, "rows")


def _summarise(rows: list[dict], key: str) -> dict:
    """covered/total/pct from the rows themselves, per Method step 6.

    pct is 0.0 rather than a ZeroDivisionError on an empty denominator: a world
    model with no capabilities is a real (if useless) run, and
    refs._check_matrix_arithmetic already computes `(covered / total) if total
    else 0.0`, so any other convention here would be a finding against a
    document this code just wrote.
    """
    covered = sum(1 for row in rows if row["covered"])
    return {
        key: rows,
        "covered": covered,
        "total": len(rows),
        "pct": (covered / len(rows)) if rows else 0.0,
    }


def _covered_cell_keys(matrix: dict) -> set[tuple[str, str]]:
    return {(c["capability_id"], c["outcome_class_id"]) for c in matrix["cells"] if c["covered"]}


def progress(run: RunPaths, round_n: int, cap_matrix: dict) -> dict:
    """new_cells_this_round and rounds_without_progress, per Method step 8.

    `new_cells_this_round` is a *set* difference, not a difference of counts:
    "covered now and were not covered before this round". A count difference
    reports zero when one cell is gained and another lost, and the loop would
    then halt on progress it actually made.

    The prior round's coverage document is the baseline, and it is read rather
    than re-derived from the scenarios' round tags.

    WHICH CLAUSE OF METHOD STEP 8 THIS IMPLEMENTS: the primary clause, "covered
    now and were *not* covered before this round", as a set difference against the
    prior round's document. The skill agrees with it, and this paragraph records
    that it once did not, because the divergence is worth remembering and the
    reasoning is what stops it coming back.

    The step used to restate the primary clause in round-tag terms -- "no live
    scenario from an earlier round credits them" -- and that restatement, never
    implemented here, diverged from the clause above in exactly the states this
    loop exists to handle: fold round 1's scenario into a round-2 one claiming the
    same cell, and the restatement calls that cell new because no *live* earlier
    scenario credits it any more, which is the inflation the step's own hazard
    sentence names ("inflated by counting cells an earlier round already covered is
    how a loop that has stopped making progress runs to the round cap anyway"). So
    the restatement contradicted the hazard written beside it and the primary
    clause did not.

    The skill now states the evaluation point the restatement left unstated:
    liveness is read as the dispatch *found* it, before its own rulings. With that
    point named the round-tag reading and this function's baseline agree on the
    fold case and on the rejection case both -- only rb-score changes a status, so
    nothing can move between the previous seal and the current dispatch except the
    current dispatch's own rulings, which is what the evaluation point excludes.
    rb-score derives the reading for its `halted_no_progress` verdict; it writes
    neither number, and this function writes both.

    Reading round-(N-1).json rather than latest.json is what keeps the step's
    other warning satisfied: latest.json is rewritten by every re-score, so it
    can answer for a round that was scored and then re-proposed against, while
    the numbered file is that round's own history.
    """
    now = _covered_cell_keys(cap_matrix)
    if round_n <= 1:
        # Round 1's absent prior document is the LEGITIMATE case, and it must not
        # be collapsed with the absence refused just below. There is no earlier
        # round that could have covered anything, so every covered cell is new by
        # definition, and no round can have passed without progress yet. rb-score's
        # progress step states both round-1 values, and the rule rather than its
        # wording is what is cited here: the previous version of this comment
        # quoted a sentence the skill has since reworded, and quoted the
        # rounds_without_progress half of it to justify the new_cells line.
        new_cells = len(now)
        return {
            "new_cells_this_round": new_cells,
            "rounds_without_progress": 0 if new_cells else 1,
        }
    previous = run.coverage_round(round_n - 1)
    if not previous.exists():
        # REFUSED, never defaulted to the round-1 branch above, and do not
        # "simplify" it back. Measured before this refusal existed: round 5 with
        # round-4's document absent returned every covered cell as new and
        # rounds_without_progress as 0, erasing four rounds of accumulated
        # history -- so `halted_no_progress` could never fire from it and the loop
        # would run to the round cap. That is the failure Method step 8 warns
        # about in its own words, arriving through the bound rather than through
        # the count.
        #
        # It is also not a state any repair reaches. seal_score writes nothing
        # when it refuses, so the orchestrator's path is: seal_score(N) refuses ->
        # repair score -> seal_score(N) again -> the document exists. Reaching
        # here means a round's seal was skipped outright, which is an inconsistent
        # run rather than a legitimate one. UsageError and not a Finding for the
        # who-wrote-it reason: 03-coverage/round-N.json is seal_score's own code
        # output, so no re-dispatch of any prompt can produce the missing file.
        raise UsageError(
            f"missing artifact: {previous} -- round {round_n} has no round "
            f"{round_n - 1} coverage document to measure progress against, so "
            "rounds_without_progress cannot be carried; a round's seal was skipped"
        )
    # 03-coverage/round-N.json is THIS function's sibling output -- seal_score
    # writes it -- so a malformed one is a hand-edit no re-dispatch could repair,
    # which is why these are UsageErrors rather than findings. Guarded rather
    # than indexed bare for the reason the module comment above collect_scenarios
    # gives: `prior["capability_matrix"]` on a document that is not an object
    # raises TypeError out of a code step, and cli.py's catch-all reports that as
    # an exit-1 `[internal]` finding against the RUN ROOT.
    prior = _object_or_refuse(previous, read_json(previous), ("capability_matrix", "progress"))
    matrix = _object_or_refuse(
        previous, prior["capability_matrix"], ("cells",), " capability_matrix"
    )
    # Both keys, because _covered_cell_keys builds a tuple of the two and
    # _rows_with_string_id checks one per call. A cell missing either would make
    # the baseline silently disagree with `now` -- the same key on both sides is
    # the whole comparison.
    for key in ("capability_id", "outcome_class_id"):
        _rows_with_string_id(previous, "capability_matrix.cells", matrix["cells"], key)
    # `covered` too, and separately because it is a BOOL: _rows_with_string_id
    # asks for a non-empty string and cannot ask for this one. _covered_cell_keys
    # indexes it bare, so a cell without it raises KeyError out of a code step --
    # the exit-1-`[internal]`-against-the-run-root breach _object_or_refuse's
    # docstring records, on a document seal_score itself wrote. Measured before
    # this door: a prior-round cell carrying both ids and no `covered` raised
    # KeyError('covered') from progress(). Fourth site of the class
    # closable_holes' `reason` door closed as the third.
    for i, cell in enumerate(matrix["cells"]):
        _object_or_refuse(previous, cell, ("covered",), f" capability_matrix.cells[{i}]")
    carried = _object_or_refuse(
        previous, prior["progress"], ("rounds_without_progress",), " progress"
    )["rounds_without_progress"]
    if not isinstance(carried, int) or isinstance(carried, bool) or carried < 0:
        # coverage-0.1.json constrains it to `integer, minimum: 0`, and this is
        # that constraint for a document that reached here without layer 1. Typed
        # rather than merely present -- unlike seal_scenarios' denominator.version,
        # which is only read and echoed -- because this value is ARITHMETIC:
        # `carried + 1` on a string raises TypeError, and `True + 1` would count
        # a bool as 1 and carry it into a schema-valid integer.
        raise UsageError(
            f"{previous} progress.rounds_without_progress must be an integer >= 0: "
            f"found {carried!r}"
        )
    was = _covered_cell_keys(matrix)
    new_cells = len(now - was)
    return {
        "new_cells_this_round": new_cells,
        "rounds_without_progress": 0 if new_cells else carried + 1,
    }


def _hole_refs(path: Path, holes: list) -> tuple[set[str], list[Finding]]:
    """The holes' refs as a set, or a finding per hole with no ref or a bad reason.

    A Finding rather than a UsageError, and that is the exit-code contract rather
    than a preference: 03-score/round-N.json is MODEL output, so a malformed one
    is exactly a repairable stage defect and the orchestrator has to be able to
    re-dispatch score alone. `_rows_with_string_id` answers the same question for
    the code-written artifacts and raises instead, which is why this is spelled
    out here rather than delegated to it.

    Split into the container check and the ref check for the reason
    _apply_rulings splits its own: `/holes/N/ref` does not resolve in a hole that
    is not an object at all, so the two cannot honestly share one pointer.
    """
    refs: set[str] = set()
    findings: list[Finding] = []
    for i, hole in enumerate(holes):
        if not isinstance(hole, dict):
            findings.append(Finding(path, "rounds", f"/holes/{i}", "hole is not a JSON object"))
            continue
        ref = hole.get("ref")
        if not isinstance(ref, str) or not ref:
            # Empty refused alongside the non-strings because "" matches neither
            # branch of coverage-0.1.json's hole_ref pattern, so a hole carrying
            # it reconciles against no row at all and reads as a hole for
            # nothing -- while every uncovered row it should have named stays
            # unjustified.
            findings.append(Finding(path, "rounds", f"/holes/{i}/ref", "hole has no string ref"))
            continue
        reason = hole.get("reason")
        # `isinstance` FIRST, and it is not redundant with the membership test:
        # `x in frozenset(...)` HASHES x, so an unhashable JSON value raises
        # TypeError out of a code step instead of answering False. Measured
        # before this door: `reason: []` and `reason: {}` each produced an exit-1
        # `[internal]` finding anchored on the RUN ROOT -- the same breach every
        # other guard in this module exists to close, and against a MODEL-written
        # part whose defect has to name `/holes/N/reason` so a re-dispatch of
        # score can repair it. `[]` and `{}` are the whole of the reachable set,
        # since they are the only unhashable values JSON can carry.
        if not isinstance(reason, str) or reason not in _HOLE_REASONS:
            # Whitelisted, not merely type-checked: seal_score copies this value
            # onto the coverage document it writes, so see _HOLE_REASONS for the
            # who-wrote-it argument and the measurement.
            findings.append(
                Finding(
                    path,
                    "rounds",
                    f"/holes/{i}/reason",
                    f"hole for {ref} carries reason {reason!r}, which is not one of "
                    f"{sorted(_HOLE_REASONS)}",
                )
            )
            continue
        refs.add(ref)
    return refs, findings


def seal_score(run: RunPaths, *, round_n: int) -> tuple[Path | None, list[Finding]]:
    """Compose 03-coverage/round-N.json, and publish it as latest.json.

    The matrices are computed here rather than read from the score part, so a
    percentage cannot disagree with the matrix beneath it -- the failure
    rb-score's own Output section warns about, and one no gate could catch from
    the document alone. What score decides is copied through untouched: each
    hole's reason and justification, and the verdict.

    The document's holes are score's plus one computed `unreachable` entry per
    declared cell no scenario could be driven through -- see the comment on
    `undrivable` below. "Copied through untouched" still holds of every hole
    score wrote: the computed ones are deduped against score's refs, and score
    wins the collision.

    latest.json is a byte copy rather than a second composition, which retires
    the "written twice with identical content" instruction that could only ever
    drift. `write_json` is canonical, so one `document` object written to both
    paths produces identical bytes by construction rather than by care.

    Writes nothing when it reports any finding, for the reason seal.py gives: a
    half-composed coverage document clears layer 1 for the fields it filled and
    reads as complete to a human at gate 2.

    The three hole reconciliations below overlap refs.check_coverage
    deliberately, for the reason seal.py gives for its own overlaps:
    check_coverage reports after the fact over any coverage document, including
    one this seal never composed, while a missing hole is otherwise perfectly
    assemblable.
    """
    findings: list[Finding] = []
    path = run.score_part(round_n)
    try:
        part = read_json(path)
    except ArtifactError as exc:
        return None, [Finding(path, "rounds", "", str(exc))]
    # Split from the field checks below, and the split is the POINTER: `/holes`
    # does not resolve in a part that is not an object at all. _apply_rulings
    # draws the same line in front of the same file.
    if not isinstance(part, dict):
        return None, [Finding(path, "rounds", "", "score part is not a JSON object")]
    for key, kind in (("holes", list), ("verdict", str)):
        if not isinstance(part.get(key), kind):
            findings.append(Finding(path, "rounds", f"/{key}", f"score part has no {key}"))
    if findings:
        return None, findings
    if part["verdict"] not in _VERDICTS:
        # Whitelisted for the same reason a ruling's status is, and against the
        # same document class: see _VERDICTS.
        return None, [
            Finding(
                path,
                "rounds",
                "/verdict",
                f"score part carries verdict {part['verdict']!r}, which is not one of "
                f"{sorted(_VERDICTS)}",
            )
        ]
    holed, findings = _hole_refs(path, part["holes"])
    if findings:
        return None, findings

    world = _object_or_refuse(
        run.world_model, read_json(run.world_model), ("capabilities", "goals", "denominator")
    )
    # Called for the refusal, not the return value: capability_matrix is pure and
    # cannot name the artifact it was handed. See _declared_cells for the
    # measurement -- a capability with no outcome classes shrinks the denominator
    # in silence, which is the one arithmetic error rb-score's refusal conditions
    # rank above every other.
    _declared_cells(run, world)
    _rows_with_string_id(run.world_model, "goals", world["goals"])
    # Echoed, never defaulted to 1, and this is the one place a default would be
    # silently wrong rather than loudly: refs.check_coverage compares this field
    # to world["denominator"]["version"] for EQUALITY, so a fallback against a
    # world model at 2 is a check-refs finding against a document this code just
    # wrote. Invariant 7 says the same thing to the prompt -- a version you
    # believe wrong is something to report, not to replace with another number.
    denominator = _object_or_refuse(
        run.world_model, world["denominator"], ("version",), " denominator"
    )
    # Absent is legitimate rather than a defect: seal_scenarios writes nothing
    # when no propose part exists, and score scoring a run with no scenarios is
    # how the loop learns it made no progress. Guarded when present for the
    # reason bytes_per_scenario is -- 02-scenarios.json is this module's own code
    # output, and a `scenarios` of the wrong type there produced a plausible
    # wrong number rather than an error.
    scenarios: list[dict] = []
    if run.scenarios.exists():
        sealed = _object_or_refuse(run.scenarios, read_json(run.scenarios), ("scenarios",))
        scenarios = _rows_with_string_id(run.scenarios, "scenarios", sealed["scenarios"])
    cap = capability_matrix(world, scenarios)
    goals = goal_matrix(world, scenarios)

    # Every declared cell no scenario could be driven through against this target.
    # rb-score's Method defines `unreachable` as "no scenario could exercise this
    # row against this target at all", and a capability with no binding.tool is
    # exactly that: emit.call_spec reads binding["tool"] unguarded, so no emitted
    # test could ever hit the cell. Computed here rather than asked of the prompt
    # because binding absence is a fact on disk and not a judgment -- and
    # score-seal already owns the matrices for the same reason.
    #
    # Together with the matrix these holes account for every declared cell: the
    # drivable ones are scored, the rest are justified here. That pairing is what
    # keeps the narrowed denominator an honest denominator rather than a silent
    # cap. Measured on run-20260827-070444: 37 of 56 cells, all undrivable.
    undrivable = sorted(_cells(world) - drivable_cells(world))
    undrivable_refs = {f"cell:{cap_id}/{oc_id}" for cap_id, oc_id in undrivable}
    injected = [
        {
            "ref": f"cell:{cap_id}/{oc_id}",
            "reason": "unreachable",
            "justification": (
                f"capability {cap_id!r} declares no binding.tool, so emit cannot turn it into a "
                "tool call and no scenario could exercise this row against the target"
            ),
        }
        for cap_id, oc_id in undrivable
        # Deduped against what score wrote, and score wins: seal_score's contract
        # is that every hole's reason and justification is copied through
        # untouched, and out_of_scope is a defensible reading a prompt may prefer
        # for the same cell. `holed` is the score part's refs, not the merged
        # document's, so this is the only place the two can collide.
        if f"cell:{cap_id}/{oc_id}" not in holed
    ]

    # Split out from `every_row` below, because the three checks that follow ask
    # two different questions and the answers stopped coinciding: `scored_rows` is
    # what the matrices score, `every_row` is what the world model DECLARES, and
    # once the matrix carries drivable rows only the second is strictly larger.
    scored_rows = {f"cell:{c['capability_id']}/{c['outcome_class_id']}" for c in cap["cells"]}
    scored_rows |= {f"goal:{r['goal_id']}" for r in goals["rows"]}
    uncovered = {
        f"cell:{c['capability_id']}/{c['outcome_class_id']}"
        for c in cap["cells"]
        if not c["covered"]
    }
    uncovered |= {f"goal:{r['goal_id']}" for r in goals["rows"] if not r["covered"]}
    # The undrivable cells count as declared, because this set backs the "which
    # the world model does not declare" finding below and the world model DOES
    # declare them -- they are simply not scored rows. Without this, the moment the
    # matrix stops scoring an undrivable cell a score-authored hole on it is
    # refused with a message that is false, and a correct document never gets
    # written; measured under exactly that narrowing before it landed, and the test
    # that pins it is
    # test_seal_score_does_not_call_a_score_hole_on_an_undrivable_cell_undeclared,
    # which the narrowing armed -- its docstring records both the measurement and
    # the round it spent unable to fail.
    #
    # `uncovered` deliberately does NOT grow the same way: only a drivable row has
    # to be justified by a hole of score's, and the undrivable ones are justified
    # by the injection above.
    every_row = scored_rows | undrivable_refs

    for ref in sorted(holed - every_row):
        findings.append(
            Finding(
                path,
                "rounds",
                "/holes",
                f"hole names {ref}, which the world model does not declare",
            )
        )
    # Parenthesised rather than relying on `-` binding tighter than `&`, which it
    # does: the unbracketed form reads as the wrong grouping to everyone who has
    # to go and check the table.
    #
    # `scored_rows`, not `every_row`, and the two differ by exactly the undrivable
    # cells: this finding says a MATRIX shows the row covered, so only a row some
    # matrix actually scores can earn it. Written with `every_row`, every ref the
    # check above now accepts as declared comes straight back out of this one as
    # "covered" -- measured, and it is why every_row could not simply be widened
    # in place. No `- undrivable_refs` term beside it: the matrix scores drivable
    # rows only, so the two sets are disjoint and the term would be dead. It would
    # also have been wrong to add while the matrix was still wide, where it would
    # have suppressed a finding that was true -- measured on run-20260827-070444
    # with the wide matrix in place, a live scenario crediting
    # cell:cap-a2a-http-server/oc-a2a-server-error earned this finding against
    # score's own `unreachable` hole on the same cell, because the wide matrix
    # really did mark it covered. Narrowing the matrix is what ended that.
    for ref in sorted(holed & (scored_rows - uncovered)):
        findings.append(
            Finding(
                path,
                "rounds",
                "/holes",
                f"hole names {ref}, which the computed matrices show as covered",
            )
        )
    # `- undrivable_refs` as well as `- holed`, because the document's holes are
    # score's plus the injected ones and every undrivable cell is in one or the
    # other by construction. Only a DRIVABLE uncovered row is still score's to
    # justify, which is the sense in which this set does not grow.
    for ref in sorted(uncovered - holed - undrivable_refs):
        findings.append(
            Finding(path, "rounds", "/holes", f"{ref} is uncovered and no hole justifies it")
        )
    if findings:
        return None, findings

    document = {
        "schema_version": "0.1",
        "round": round_n,
        "denominator_version": denominator["version"],
        "capability_matrix": cap,
        "goal_matrix": goals,
        # score's own holes first and in their order, then the computed ones, so a
        # reader at gate 2 sees what the prompt decided before what code added.
        "holes": [*part["holes"], *injected],
        "progress": progress(run, round_n, cap),
        "verdict": part["verdict"],
    }
    write_json(run.coverage_round(round_n), document)
    write_json(run.coverage_latest, document)
    return run.coverage_round(round_n), findings
