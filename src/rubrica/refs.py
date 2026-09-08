"""Referential integrity across run artifacts: layer 2 of three.

Layer 1 (validate.py) checks that each artifact has the right shape. This
module checks what a schema cannot see: whether ids resolve across artifact
boundaries, whether declared arithmetic matches the data it summarizes, and
(Task 8) whether every assertion is reachable in its own seed.

check_all tolerates a partially-populated run directory. It runs after every
stage, so when reconcile finishes there is no 02-scenarios.json yet and that
absence is normal. A stage that should have produced an artifact and did not
is validate.validate_stage's finding, not this module's. The enumeration of
those valid partial states is executable, in tests/unit/test_refs_states.py.

**Precondition: layer 1 must have run first.** This module assumes every
artifact present is already schema-valid -- _check_reachability and
_check_seed_conformance index required keys directly and would raise KeyError
on a malformed document rather than return a finding. check_all is publicly
callable and the CLI exposes check-refs with no way to require that validate
ran, so a caller running them out of order gets a traceback, not a finding.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from rubrica.artifacts import ArtifactError, read_json, sha256_of
from rubrica.findings import Finding
from rubrica.interfaces import TOOL_NAME
from rubrica.invariants import InvariantForm
from rubrica.invariants import evaluate as evaluate_invariant
from rubrica.paths import RunPaths, is_safe_segment, list_json
from rubrica.slices import candidate_bytes_index, excluded_summary, row_bytes
from rubrica.suite.verify import DATA_KINDS, TRAJECTORY_KINDS
from rubrica.utilisation import claim_utilisation

_CELL_RE = re.compile(r"\Acell:([A-Za-z0-9][A-Za-z0-9._-]*)/([A-Za-z0-9][A-Za-z0-9._-]*)\Z")
_GOAL_RE = re.compile(r"\Agoal:([A-Za-z0-9][A-Za-z0-9._-]*)\Z")

# A scenario that still counts: one the pipeline has not discarded. Shared with
# dedupe.py, which must exclude the same set -- re-proposing a pair resolved in
# an earlier round is how the enrichment loop fails to converge.
OPEN_STATUSES = frozenset({"proposed", "active"})

# A scenario the pipeline has *ruled on*: fit to instantiate when it was ruled
# on, or thrown out afterwards. This is the status set that may legitimately
# appear under 04/05/06.
#
# An earlier enumeration of this check said `active`, which contradicts the
# challenge loop it was written beside: a rejected scenario is marked
# `rejected` in 02-scenarios.json *after* it has been instantiated and judged,
# so requiring `active` made check-refs permanently dirty in a state the reject
# path prescribes, with no repair able to clear it. The reasoned commitment
# wins over the one-clause enumeration -- the
# artifact record of the rejection is what makes the honest-hole report ("87%,
# 3 cells lost to rejected scenarios") possible, so that record must survive.
#
# `proposed` and `duplicate` stay out on purpose. A `proposed` scenario
# instantiated before score ruled on it is a real defect, and so is an
# instance for a scenario dedupe folded into another.
JUDGED_STATUSES = frozenset({"active", "rejected"})


def cell_ref(capability_id: str, outcome_class_id: str) -> str:
    """Canonical hole reference for one capability x outcome-class cell."""
    return f"cell:{capability_id}/{outcome_class_id}"


def goal_ref(goal_id: str) -> str:
    """Canonical hole reference for one goal row."""
    return f"goal:{goal_id}"


def parse_hole_ref(ref: str) -> tuple[str, tuple[str, ...]]:
    """Parse a hole reference into ("cell", (cap, oc)) or ("goal", (goal,))."""
    match = _CELL_RE.match(ref or "")
    if match:
        return "cell", (match.group(1), match.group(2))
    match = _GOAL_RE.match(ref or "")
    if match:
        return "goal", (match.group(1),)
    raise ValueError(f"malformed hole reference: {ref!r}")


def _load(path) -> Any | None:
    """Read an artifact, or None when it does not exist yet."""
    try:
        return read_json(path)
    except ArtifactError:
        return None


def _readable_targets(run: RunPaths) -> list[Path]:
    """Every JSON document in the run that a layer-2 check goes on to read.

    Pipeline order, so the first finding names the earliest broken artifact --
    the one a repair should start from. tests/unit/test_refs_readable.py breaks
    each of these in turn, which is what keeps the list complete: an artifact
    missing here is one whose truncation still misdirects the repair.

    The gaps partial is listed although no layer-2 check reads it, so this is
    slightly wider than its first line: it is an input to reconcile-seal, and
    listing it names a truncated one at check-refs time instead of leaving it to
    the seal's own dispatch. The services partial needs no such argument at all --
    it has two layer-2 readers of its own, check_input_dispositions for its
    accounting and check_services for the grouping itself, and the seal reads it
    too when it exists, folding it into the world model's optional `services`
    field. So unlike the gaps partial it is named here for the ordinary reason,
    and this listing is the earliest of three guards rather than the only one.
    The entities, goals and services partials are read as well as listed --
    check_input_dispositions recomputes each pass's accounting out of them. Being
    named here is not the only guard, and measurably not: the seal refuses a
    broken partial itself, exit 1 with the artifact named. And
    check_readable covers only JSON that will not parse, so a partial that parses
    to a non-object passes here; layer 1 and the seal each reject that shape by
    name. tests/unit/test_refs_reconcile_parts.py breaks each of the partials in
    turn.
    """
    targets = [run.catalogue, run.triage, run.manifest]
    targets += list_json(run.claims_dir)
    targets += [run.subjects]
    targets += list_json(run.contradictions_dir)
    targets += [
        run.capabilities_part,
        run.outcomes_part,
        run.entities_part,
        run.goals_part,
        run.gaps_part,
        run.services_part,
    ]
    # The synthesised documents, after the part they are derived from: a truncated
    # one is named here rather than left to whichever later reader hands it to the
    # harness, and check_interfaces is the reader that would otherwise treat it as
    # absent and report a missing document against the part instead. Iterated,
    # because there is one per service and none at all in a run whose target
    # declares no tools.
    targets += list_json(run.interfaces_dir)
    targets.append(run.world_model)
    # The loop's per-round documents, in the order one round writes them:
    # propose-batches' plan, every propose part, the sealed scenario list the
    # parts assemble into, then score's own part. check_batches,
    # check_scenario_parts and check_score_parts each read their own, and
    # check_scenario_parts reads the *plan* beside the parts as well -- so a
    # truncated plan left unnamed here is a checker reporting a missing batch for
    # every correct part in the round while naming the wrong artifact.
    for round_n in run.batches_rounds():
        targets.append(run.batches(round_n))
    for round_n in run.scenario_part_rounds():
        targets += [run.scenario_part(round_n, b) for b in run.scenario_part_batch_ids(round_n)]
    targets.append(run.scenarios)
    for round_n in run.score_part_rounds():
        targets.append(run.score_part(round_n))
    targets += list_json(run.coverage_dir)
    for sid in run.scenario_ids_with_instances():
        targets += [run.seed(sid), run.expected(sid)]
    targets += list_json(run.verdicts_dir)
    for sid in run.scenario_ids_with_tasks():
        task = run.task_dir(sid)
        targets += [
            task / "seed.json",
            task / "golden.json",
            task / "tests" / "expected.json",
        ]
    targets.append(run.report)
    return targets


def check_readable(run: RunPaths) -> list[Finding]:
    """Every artifact that is present but is not parseable JSON, named.

    Absence is deliberately not reported: a stage that has not run yet is
    validate_stage's finding, and reporting it here would fire in states where
    nothing is wrong.
    """
    out: list[Finding] = []
    for path in _readable_targets(run):
        if not path.is_file():
            continue
        try:
            read_json(path)
        except ArtifactError as exc:
            out.append(Finding(path, "refs", "", str(exc)))
    return out


def _claim_index(run: RunPaths) -> dict[str, list[Path]]:
    """Claim id -> every claims file defining it, one entry per definition.

    A list rather than a set: two definitions of one id in the *same* file is
    as much of a reconciliation hazard as two across files, and a set would
    hide it. check_manifest reports any id with more than one entry.
    """
    index: dict[str, list[Path]] = {}
    for path in list_json(run.claims_dir):
        payload = _load(path)
        if not isinstance(payload, dict):
            continue
        for claim in payload["claims"]:
            index.setdefault(claim["id"], []).append(path)
    return index


def _claim_ids(run: RunPaths) -> set[str]:
    """Every claim id across every 01-claims file."""
    return set(_claim_index(run))


def _claims_by_artifact(run: RunPaths) -> dict[str, list[dict]]:
    """artifact_id -> its claim records, from 01-claims/ itself.

    Keyed on the payload's own `artifact_id` rather than the filename, because
    that is the field every other checker resolves against and a mismatch
    between the two is check_manifest's finding, not this reader's. Not silently,
    though: a claims file whose payload names an artifact the manifest does not
    register lands under a key no accounting row can name, so
    check_input_dispositions reports a consequential own_kind_total disagreement
    against the partial as well, and one defect ends up naming two artifacts.
    check_manifest's is the finding to repair from.
    """
    out: dict[str, list[dict]] = {}
    for path in list_json(run.claims_dir):
        payload = _load(path)
        if not isinstance(payload, dict):
            continue
        artifact_id = payload.get("artifact_id")
        if not isinstance(artifact_id, str):
            continue
        out.setdefault(artifact_id, []).extend(
            claim for claim in _as_list(payload.get("claims")) if isinstance(claim, dict)
        )
    return out


def _claim_refs_in(node: Any) -> list[str]:
    """Every id in every `claims` array anywhere in a document.

    A walk rather than a per-part list of paths: the reconcile partials each nest
    their citations differently -- an entity carries them on itself and on each
    invariant, the outcomes part two levels down inside an `outcomes` record --
    and a path list would need revising by whoever nests a new element, which is
    the drift this module's "$ref, do not restate" rule refuses elsewhere. An
    inputs_seen row has no `claims` key, so the accounting cannot count itself.
    """
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "claims":
                found.extend(v for v in _as_list(value) if isinstance(v, str))
            else:
                found.extend(_claim_refs_in(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_claim_refs_in(item))
    return found


def _cells(world: dict) -> set[tuple[str, str]]:
    """Every (capability_id, outcome_class_id) pair the world model declares."""
    return {
        (cap["id"], oc["id"])
        for cap in world.get("capabilities", [])
        for oc in cap.get("outcome_classes", [])
    }


def drivable_cells(world: dict) -> set[tuple[str, str]]:
    """The cells a scenario could actually be driven through the target on.

    `_cells` above and this are deliberately two functions, and collapsing them
    is the mistake this split exists to prevent. `_cells` answers "does this
    reference resolve" -- it backs hole refs, scenario capability_refs and batch
    hole_refs -- so it must stay wide, or a scenario on an undrivable cell reads
    as naming a cell the world model does not declare. This one answers "is this
    cell in the denominator", which is a narrower question with a different right
    answer.

    Keyed on `binding.tool`, one notch tighter than `emit.bindings`' truthiness
    test on the binding object (emit.py:67, the `if cap.get("binding")` clause of
    its comprehension) because `emit.call_spec` then reads `binding["tool"]`
    unguarded (emit.py:79) -- so the denominator equals what the
    pipeline can actually ship, not merely what it retains. The two predicates
    disagree on exactly one shape, a binding present with no `tool`, and do not
    "align" them: that shape crashes call_spec, so it belongs outside the
    denominator rather than inside the suite.
    Measured on run-20260827-070444: 24 capabilities, 5 bound, 37 of 56 cells
    counted against a suite that could never contain them, with both gate layers
    exiting 0.

    The proxy is lossy and knowingly so: of the 37 excluded cells on that run, 29
    were correctly excluded (dependency declarations from pyproject.toml, and real
    surfaces on another interface) and 8 were real agent-level behaviour that
    `binding`'s tool shape cannot express at all -- see docs/design/limitations.md
    on why that is recorded rather than fixed here.

    `(cap.get("binding") or {})` rather than `cap.get("binding", {})`: an explicit
    `binding: null` is what a hand-edit at gate 1 produces, and the second
    spelling returns None and raises AttributeError on the chained `.get`.

    A set of distinct pairs, for _cells' reason: the seal writes len() of this and
    check_world_model recomputes it, so a sum of per-capability counts would
    diverge the moment an id repeated.
    """
    return {
        (cap["id"], oc["id"])
        for cap in world.get("capabilities", [])
        if (cap.get("binding") or {}).get("tool")
        for oc in cap.get("outcome_classes", [])
    }


def _dupes(values: list[str]) -> list[str]:
    return sorted({v for v in values if values.count(v) > 1})


def _as_list(value: Any) -> list:
    """`value` if it is a list, else `[]`.

    Every list-typed field check_triage iterates is schema-required to be an
    array, but check_all has no ordering guarantee that layer 1 has rejected a
    malformed document before layer 2 reads it. `value or []` is not a
    sufficient guard on its own: it only substitutes on a *falsy* value, and a
    truthy non-list (an int, a non-empty string) still reaches a bare `for`
    loop and raises TypeError rather than being skipped -- measured directly
    below, where `"sources": "not-a-list"` used to do exactly that.
    """
    return value if isinstance(value, list) else []


def _str_or_none(value: Any) -> str | None:
    """`value` if it is a string, else `None`.

    Every id check_triage resolves against a dict or set key is
    schema-required to be a string, but the same ordering gap means one can
    arrive as a list or a dict instead -- and `x in some_dict` or
    `some_set.add(x)` raises TypeError on an unhashable `x` rather than
    producing a finding. Routing every id through this before it touches a
    dict or set keeps the lookup on a guaranteed-hashable value; the
    mismatched value itself stays visible in the message, which is why call
    sites keep reporting the original (`cid!r`), not this function's result.
    """
    return value if isinstance(value, str) else None


def check_catalogue(run: RunPaths) -> list[Finding]:
    """Conditional constraints over 00-catalogue.json that layer 1 cannot state.

    An absent catalogue is not a finding: a run minted through `intake --input`
    never had one, and treating that as a defect would report every pre-triage
    run as broken. Same ruling as intake's and smoke's absence from
    manifest.stages.
    """
    catalogue = _load(run.catalogue)
    if not isinstance(catalogue, dict):
        return []
    out: list[Finding] = []

    def report(pointer: str, message: str) -> None:
        out.append(Finding(run.catalogue, "refs", pointer, message))

    candidates = catalogue.get("candidates")
    if not isinstance(candidates, list):
        return []

    ids = [c.get("candidate_id") for c in candidates if isinstance(c, dict)]
    for duplicate in _dupes([i for i in ids if isinstance(i, str)]):
        report("/candidates", f"duplicate candidate_id {duplicate!r}")
    known = {i for i in ids if isinstance(i, str)}

    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            continue
        origin = candidate.get("origin")
        pointer = f"/candidates/{index}"
        if origin == "corpus" and not candidate.get("path"):
            report(f"{pointer}/path", "a corpus candidate must carry the path it was read from")
        if origin == "container_element":
            container = candidate.get("container")
            if not isinstance(container, dict):
                report(f"{pointer}/container", "a container element must name its container")
                continue
            parent = container.get("candidate_id")
            if parent not in known:
                report(
                    f"{pointer}/container/candidate_id",
                    f"no such candidate {parent!r} to have been exploded from",
                )
        if origin == "projection" and not isinstance(candidate.get("provenance"), dict):
            report(
                f"{pointer}/provenance",
                "an adopted projection must record the projection_id it satisfies",
            )
    return out


def _and_join(items: list[str]) -> str:
    """ "a and b" for two items, "a, b, and c" for more -- never a bare comma list.

    Called on candidate coverage overlaps and on a hole ref assigned to more than
    one batch. Both are rare enough (a hand-edited plan, not a normal
    `write_slices` or `write_batches` output) that this exists purely so the
    message reads as English rather than "a, b" for the common two-item case.
    """
    if len(items) <= 1:
        return ", ".join(items)
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def check_slices(run: RunPaths) -> list[Finding]:
    """00-slices.json against 00-catalogue.json: same partition, or a finding.

    Absent is not a finding: a run before `triage-slices` has run has nothing
    to check here, same ruling as check_catalogue's for a run minted through
    `intake --input` -- check_all runs every checker the run has inputs for,
    so a pre-slicing run must report nothing.

    A *present* plan that is not parseable JSON is exactly one finding naming
    00-slices.json, returned immediately. This is the module docstring's
    `01-claims/` incident again: continuing past an unreadable plan to resolve
    candidate_ids that were never actually parsed would fabricate a `no such
    candidate` finding for every id the read failed on, blaming a catalogue
    that is fine for a plan that is broken.

    `_readable_targets` does not cover 00-slices.json or its shards -- the
    plan is minted well after the artifacts that list enumerates -- so
    `check_readable`'s short-circuit never fires for this artifact and this
    checker must guard the unreadable case for itself.
    """
    if not run.slices.is_file():
        return []
    try:
        plan = read_json(run.slices)
    except ArtifactError as exc:
        return [Finding(run.slices, "refs", "", str(exc))]
    if not isinstance(plan, dict):
        return []
    slice_entries = plan.get("slices")
    if not isinstance(slice_entries, list):
        return []

    out: list[Finding] = []

    def report(pointer: str, message: str) -> None:
        out.append(Finding(run.slices, "refs", pointer, message))

    cap_bytes = plan.get("cap_bytes")

    # Check 3: slice ids unique. Duplicate ids are reported once here rather
    # than left to corrupt every check below that addresses a shard by id --
    # two entries sharing one id would otherwise both resolve to the same
    # shard file and their shard/bytes findings would look like agreement.
    raw_ids = [s.get("id") for s in slice_entries if isinstance(s, dict)]
    for dup in _dupes([i for i in raw_ids if isinstance(i, str)]):
        report("/slices", f"slice id {dup!r} is used by more than one slice")

    # Checks 1 & 2 resolve candidate_ids against the catalogue's own ids. A
    # catalogue that is absent, unreadable, or missing a candidates array
    # cannot support that resolution -- reported already by check_catalogue,
    # or not yet a defect if triage has not run -- so known_ids is None and
    # this checker skips 1 & 2 rather than treating every id as unresolvable.
    catalogue = _load(run.catalogue)
    catalogue_candidates = catalogue.get("candidates") if isinstance(catalogue, dict) else None
    known_ids: set[str] | None
    if isinstance(catalogue_candidates, list):
        known_ids = {
            cid
            for c in catalogue_candidates
            if isinstance(c, dict) and isinstance(cid := c.get("candidate_id"), str)
        }
    else:
        known_ids = None

    # A set, not a list: what check 1 below asks is "how many *distinct*
    # slice ids cover this candidate", not "how many entries do". A slice id
    # duplicated across two entries (check 3's own defect) would otherwise
    # make every candidate the duplicate shares look doubly-covered even
    # when both entries name the same slice -- an artifact of counting
    # entries, not of the candidate actually crossing a slice boundary.
    coverage: dict[str, set[str]] = {}

    for index, entry in enumerate(slice_entries):
        if not isinstance(entry, dict):
            continue
        pointer = f"/slices/{index}"
        sid = _str_or_none(entry.get("id"))
        candidate_ids = [c for c in _as_list(entry.get("candidate_ids")) if isinstance(c, str)]

        if known_ids is not None:
            for j, cid in enumerate(candidate_ids):
                if cid not in known_ids:
                    report(f"{pointer}/candidate_ids/{j}", f"no such candidate {cid!r}")
                elif sid is not None:
                    coverage.setdefault(cid, set()).add(sid)

        declared_bytes = entry.get("bytes")
        # Check 7: no slice is over cap_bytes, the budget every slice in this
        # plan was packed against. Numbered because the checks below cite it as
        # a landmark -- it went unlabelled when it was added on top of 1-6, and
        # a stale pointer to it outlived that in two docstrings.
        if (
            isinstance(cap_bytes, int)
            and isinstance(declared_bytes, int)
            and declared_bytes > cap_bytes
        ):
            report(
                f"{pointer}/bytes",
                f"slice {sid!r} is {declared_bytes} bytes, over the {cap_bytes}-byte cap "
                "this plan was packed against",
            )

        if sid is None:
            continue  # nothing safe to join into a shard path

        # Check 4 (missing half): a shard this slice claims must exist on
        # disk. Named at slices_dir, not the nonexistent shard path, mirroring
        # check_verdicts' Finding(run.instance_dir(sid), ...) for a missing
        # verdict -- point at the thing that does exist and should hold it.
        shard_path = run.slice_shard(sid)
        if not shard_path.is_file():
            out.append(Finding(run.slices_dir, "refs", "", f"slice {sid} has no shard on disk"))
            continue
        try:
            shard = read_json(shard_path)
        except ArtifactError as exc:
            out.append(Finding(shard_path, "refs", "", str(exc)))
            continue
        if not isinstance(shard, dict):
            continue

        shard_candidates = [c for c in _as_list(shard.get("candidates")) if isinstance(c, dict)]

        # Check 6: shard candidates match candidate_ids, in order -- the same
        # ids in the same sequence, not merely the same set.
        shard_ids = [c.get("candidate_id") for c in shard_candidates]
        if shard_ids != candidate_ids:
            out.append(
                Finding(
                    shard_path,
                    "refs",
                    "/candidates",
                    f"shard candidates do not match slice {sid}'s candidate_ids, in order",
                )
            )

        # Check 5: bytes is arithmetic, not testimony -- recomputed from the
        # shard's own candidates via slices.row_bytes, the same function
        # write_slices used to produce the number in the first place.
        recomputed = sum(row_bytes(c) for c in shard_candidates)
        if isinstance(declared_bytes, int) and declared_bytes != recomputed:
            out.append(
                Finding(
                    run.slices,
                    "refs",
                    f"{pointer}/bytes",
                    f"slice {sid} declares bytes={declared_bytes} but its shard's candidates "
                    f"sum to {recomputed}",
                )
            )

    # Check 1: every catalogue candidate lands in exactly one slice.
    if known_ids is not None:
        for cid in sorted(known_ids):
            covering = coverage.get(cid, set())
            if not covering:
                report("", f"no slice covers {cid!r}")
            elif len(covering) > 1:
                report("", f"{cid!r} is in slices {_and_join(sorted(covering))}")

    # Check 4 (orphan half): every shard on disk is named by the plan.
    # Mirrors check_verdicts' orphan-verdict scan just as directly as the
    # missing-shard branch above mirrors its missing-verdict one.
    plan_shard_ids = {i for i in raw_ids if isinstance(i, str)}
    for shard_path in list_json(run.slices_dir):
        if shard_path.stem not in plan_shard_ids:
            out.append(
                Finding(
                    shard_path,
                    "refs",
                    "",
                    f"{shard_path.name} is a shard on disk that no slice in the plan names",
                )
            )

    # Checks 8 and 9: the catalogue_facts block's *derived* fields, recomputed
    # from the catalogue through the same functions write_slices used to
    # produce them -- check 5's discipline, for check 5's reason. What this
    # catches is drift between the plan and the catalogue, the realistic case
    # being a plan minted before a human adopted a projection at gate 0,
    # rather than arithmetic this module could get wrong twice identically.
    #
    # Two criteria put a field in, and each field below carries its own. The
    # first is the wrong-artifact hazard: check_objective recomputes
    # weight.bytes from the catalogue's own candidates[], and
    # rb-triage-objective's reads are 00-slices.json alone, so it takes those
    # same numbers from candidate_bytes -- undetected drift here would surface
    # that pass's *correct* arithmetic as a finding against 00-objective.json.
    # Checking the plan is what keeps the 1 on the artifact actually at fault --
    # the exit-code contract's third rule, and what four fabricated `no such
    # claim` findings against a correct world model once cost.
    #
    # The second is a reader's rather than a recomputation's, and the tally is
    # in on it: `total` and `by_reason` are the only account of what survey
    # dropped that the objective pass can see, and a drifted tally is a lie no
    # artifact it reads can correct.
    #
    # `request` and `policy` stay unchecked because they are verbatim copies,
    # and nothing verifies the shards' own copies of either. `excluded.entries`
    # stays unchecked for a different reason, and *not* because it is a copy --
    # its selection is derived twice, filtered to DISPUTABLE_EXCLUSION_REASONS
    # and then cut to a prefix that fits the byte budget, with only each
    # retained element verbatim. It is out because a mismatch message would
    # inline up to MAX_EXCLUDED_ENTRY_BYTES twice on one line, against a
    # contract that wants one *readable* finding per line. Its truncation flag
    # is checked below on the same reader's grounds as the tally, and scoped the
    # same way: that is one boolean, and a stale `false` tells the objective
    # pass the disputable list is complete when it is not. Not a gate-0 human --
    # `entries_truncated` is never rendered by brief.py, so the only party it
    # misleads directly is the pass that reads the plan and nothing else; a
    # human inherits the error only through that pass's notes.
    facts = plan.get("catalogue_facts")
    if isinstance(facts, dict) and isinstance(catalogue, dict):
        # Both halves skip on an unreadable or wrong-shaped catalogue rather
        # than reporting every entry, reusing the same reasoning that leaves
        # known_ids None above.
        if isinstance(catalogue_candidates, list):
            expected_bytes = candidate_bytes_index(catalogue_candidates)
            declared = facts.get("candidate_bytes")
            declared = declared if isinstance(declared, dict) else {}
            for cid in sorted(expected_bytes):
                pointer = f"/catalogue_facts/candidate_bytes/{cid}"
                if cid not in declared:
                    report(pointer, f"catalogue_facts has no candidate_bytes entry for {cid!r}")
                elif declared[cid] != expected_bytes[cid]:
                    report(
                        pointer,
                        f"catalogue_facts records {cid!r} at {declared[cid]!r} bytes but "
                        f"the catalogue says {expected_bytes[cid]}",
                    )
            for cid in sorted(set(declared) - set(expected_bytes)):
                report(
                    f"/catalogue_facts/candidate_bytes/{cid}",
                    f"catalogue_facts records candidate_bytes for {cid!r}, which is not "
                    "a catalogue candidate",
                )
        catalogue_excluded = catalogue.get("excluded")
        if isinstance(catalogue_excluded, list):
            expected_excluded = excluded_summary(catalogue_excluded)
            declared_excluded = facts.get("excluded")
            declared_excluded = declared_excluded if isinstance(declared_excluded, dict) else {}
            for key in ("total", "by_reason", "entries_truncated"):
                if declared_excluded.get(key) != expected_excluded[key]:
                    report(
                        f"/catalogue_facts/excluded/{key}",
                        f"catalogue_facts records excluded.{key}={declared_excluded.get(key)!r} "
                        f"but the catalogue's exclusions give {expected_excluded[key]!r}",
                    )
    return out


def check_disposition_parts(run: RunPaths) -> list[Finding]:
    """One part per slice, and the union of parts and adoptions covers the catalogue.

    Returns nothing until 00-dispositions/ exists: with no dispositions
    directory at all the run has not reached the dispositions fan-out, and
    reporting every slice as unruled there would spend the orchestrator's
    single repair attempt on a phantom.

    Note what that does *not* tolerate. Once the directory exists -- i.e. once
    the first part has landed -- every slice without one is reported. The
    dispositions fan-out window, where some members have finished and others
    are still in flight, is therefore *not* tolerated; the guard is `is_dir()`,
    not a count. That is deliberate: check-refs is dispatched after the
    fan-out completes, so a missing part at that point is real -- there is no
    such thing as a stage-scoped check-refs.

    Nothing here is semantic: every check below is "does this reference
    resolve", never "does this disposition make sense for this candidate".

    `_readable_targets` does not cover 00-slices.json, any disposition part,
    or 00-adoptions.json -- all three are minted well after the artifacts
    that list enumerates -- so this checker self-guards each of them exactly
    as check_slices does for the plan.
    """
    if not run.dispositions_dir.is_dir():
        return []
    if not run.slices.is_file():
        return []
    try:
        plan = read_json(run.slices)
    except ArtifactError as exc:
        return [Finding(run.slices, "refs", "", str(exc))]
    if not isinstance(plan, dict):
        return []
    slice_entries = plan.get("slices")
    if not isinstance(slice_entries, list):
        return []

    # Slice id -> the candidate_ids the plan says belong to it, the same
    # population check_slices already holds every plan entry to -- reading
    # it here rather than importing that check's own tables keeps this
    # checker independent of check_slices' internal shape.
    slice_candidates: dict[str, set[str]] = {}
    for entry in slice_entries:
        if not isinstance(entry, dict):
            continue
        sid = _str_or_none(entry.get("id"))
        if sid is not None:
            slice_candidates[sid] = {
                c for c in _as_list(entry.get("candidate_ids")) if isinstance(c, str)
            }

    have_parts = set(run.slice_ids_with_parts())
    out: list[Finding] = []

    # Clause 1: every slice the plan declares has a part written for it.
    missing_slices = sorted(set(slice_candidates) - have_parts)
    for sid in missing_slices:
        out.append(
            Finding(
                run.dispositions_dir,
                "refs",
                "",
                f"slice {sid} has no disposition part on disk",
            )
        )

    # Every present part is read exactly once, here, and an unreadable one is
    # its own finding excluded from every check below -- continuing past a
    # parse failure would fabricate findings against candidates the failed
    # part never actually let this checker see, the module docstring's
    # `01-claims/` incident again.
    parts: dict[str, dict] = {}
    readable_sids: set[str] = set()
    for sid in sorted(have_parts):
        path = run.disposition_part(sid)
        try:
            doc = read_json(path)
        except ArtifactError as exc:
            out.append(Finding(path, "refs", "", str(exc)))
            continue
        if not isinstance(doc, dict):
            continue
        readable_sids.add(sid)
        parts[sid] = doc

    # Clause 2: every disposition names a candidate that belongs to the slice
    # its own part rules on -- the same defect seal.py's item 3 refuses
    # before the write, reported here after the fact over any run's staged
    # parts, including one the seal never sealed.
    rulings: dict[str, list[tuple[Path, dict]]] = {}
    for sid, doc in parts.items():
        allowed = slice_candidates.get(sid, set())
        path = run.disposition_part(sid)
        for index, entry in enumerate(_as_list(doc.get("dispositions"))):
            if not isinstance(entry, dict):
                continue
            cid = _str_or_none(entry.get("candidate_id"))
            if cid is None:
                continue
            if cid not in allowed:
                out.append(
                    Finding(
                        path,
                        "refs",
                        f"/dispositions/{index}/candidate_id",
                        f"candidate {entry.get('candidate_id')!r} is not in slice {sid!r}, "
                        "which this part rules on",
                    )
                )
            rulings.setdefault(cid, []).append((path, entry))

    # Adoptions bypass slicing entirely (spec 8.1: an adopted candidate needs
    # no slice member to rule on it since a human already did), so they fold
    # into the same rulings map. Required-and-may-be-empty per
    # adoptions-0.1.json's own description: absence is not a defect, but a
    # present-and-broken file is, same self-guard as every other part above.
    adoptions_unreadable = False
    if run.adoptions.is_file():
        try:
            adoptions_doc = read_json(run.adoptions)
        except ArtifactError as exc:
            out.append(Finding(run.adoptions, "refs", "", str(exc)))
            adoptions_doc = None
            adoptions_unreadable = True
        if isinstance(adoptions_doc, dict):
            for adoption in _as_list(adoptions_doc.get("adoptions")):
                if not isinstance(adoption, dict):
                    continue
                cid = _str_or_none(adoption.get("candidate_id"))
                if cid is not None:
                    rulings.setdefault(cid, []).append((run.adoptions, adoption))

    # Clause 3: no candidate ruled twice across parts and adoptions.
    for cid in sorted(cid for cid, entries in rulings.items() if len(entries) > 1):
        out.append(
            Finding(
                rulings[cid][0][0],
                "refs",
                "",
                f"candidate {cid!r} has more than one disposition across the staged parts",
            )
        )

    # Clause 4: the union of parts and adoptions covers the catalogue --
    # scoped to exclude candidates whose owning slice was already reported
    # missing or unreadable above, so one broken slice does not also report
    # every one of its own candidates as separately uncovered.
    catalogue = _load(run.catalogue)
    if isinstance(catalogue, dict):
        catalogue_ids = {
            cid
            for c in _as_list(catalogue.get("candidates"))
            if isinstance(c, dict) and isinstance(cid := c.get("candidate_id"), str)
        }
        uncheckable: set[str] = set()
        for sid in missing_slices:
            uncheckable |= slice_candidates.get(sid, set())
        for sid in have_parts - readable_sids:
            uncheckable |= slice_candidates.get(sid, set())
        if adoptions_unreadable:
            # The content of a broken 00-adoptions.json is unknowable, so
            # its actual scope cannot be folded in the way a broken part's
            # can (that scope comes from the plan, not from the part
            # itself). What *can* be bounded is which candidates an
            # adoption could ever have been responsible for: adoptions
            # bypass slicing entirely (spec 8.1), so every candidate no
            # slice covers is exactly that population, and is excluded
            # rather than guessed at. A slice-covered candidate stays
            # checkable -- a broken adoptions file cannot explain away a
            # candidate that was never adoption-eligible to begin with.
            slice_covered = {cid for ids in slice_candidates.values() for cid in ids}
            uncheckable |= catalogue_ids - slice_covered
        checkable = catalogue_ids - uncheckable
        for cid in sorted(checkable - set(rulings)):
            out.append(
                Finding(
                    run.dispositions_dir,
                    "refs",
                    "",
                    f"candidate {cid!r} has no disposition in any staged part or adoption",
                )
            )

    return out


def check_objective(run: RunPaths) -> list[Finding]:
    """Reference checks over 00-objective.json. Nothing here is semantic.

    Unlike check_disposition_parts, this reads one file written whole by one
    pass -- there is no fan-out window where "some surfaces resolved, some
    have not landed yet" is a normal, in-progress state to tolerate. A
    present-but-broken 00-objective.json is a defect from the moment it
    exists, so this carries no check_verdicts-style caveat.

    `_readable_targets` does not cover 00-objective.json -- it is minted well
    after the artifacts that list enumerates -- so this checker self-guards
    its own read exactly as check_slices does for the plan.
    """
    if not run.objective.is_file():
        return []
    try:
        objective = read_json(run.objective)
    except ArtifactError as exc:
        return [Finding(run.objective, "refs", "", str(exc))]
    if not isinstance(objective, dict):
        return []

    # The catalogue is already covered by check_readable/_readable_targets,
    # so an unreadable one is check_readable's finding, not this checker's to
    # repeat -- reading it through _load, silently None on failure, matches
    # check_triage's identical treatment of the same artifact.
    catalogue = _load(run.catalogue)
    candidates_by_id: dict[str, dict] = {}
    if isinstance(catalogue, dict):
        candidates_by_id = {
            cid: c
            for c in _as_list(catalogue.get("candidates"))
            if isinstance(c, dict) and isinstance(cid := c.get("candidate_id"), str)
        }

    review = objective.get("objective_review")
    if not isinstance(review, dict):
        return []
    surfaces = _as_list(review.get("surfaces"))
    out: list[Finding] = []

    for index, surface in enumerate(surfaces):
        if not isinstance(surface, dict):
            continue
        pointer = f"/objective_review/surfaces/{index}"
        evidence = [e for e in _as_list(surface.get("evidence")) if isinstance(e, str)]

        # Clause 1: every evidence id resolves to a real catalogue candidate.
        # Skipped (like check_slices' known_ids is None branch) when the
        # catalogue itself could not be read, rather than treating every id
        # as unresolvable.
        unresolved = False
        if candidates_by_id:
            for position, cid in enumerate(evidence):
                if cid not in candidates_by_id:
                    out.append(
                        Finding(
                            run.objective,
                            "refs",
                            f"{pointer}/evidence/{position}",
                            f"no such candidate {cid!r}",
                        )
                    )
                    unresolved = True

        # Clause 2: weight is arithmetic over the catalogue, recomputed from
        # evidence rather than compared against itself -- a surface cannot
        # certify its own count (lesson from earlier tasks: "weight is
        # arithmetic a reader recomputes"). Distinct evidence ids, not raw
        # count: evidence carries no uniqueItems constraint, and a candidate
        # named twice in one surface is still one physical candidate.
        # Skipped when evidence did not fully resolve above, or the
        # catalogue could not be read -- the weight of a broken evidence list
        # is not a second, independent defect to report.
        if unresolved or not candidates_by_id:
            continue
        weight = surface.get("weight")
        if not isinstance(weight, dict):
            continue
        distinct = set(evidence)
        recomputed_candidates = len(distinct)
        # bytes sums each candidate's own catalogue `bytes` field (the
        # source file's size), never row_bytes' serialized-row size. digest.py
        # clamps the digest skeleton at 128 nodes, so a 2.7MB source and
        # a 20KB one can serialize to nearly the same row -- a metric that
        # saturates under that cap is not a weight metric, it stops
        # discriminating between candidates of very different evidential
        # size right where this pass needs it to.
        recomputed_bytes = sum(
            b for cid in distinct if isinstance(b := candidates_by_id[cid].get("bytes"), int)
        )
        declared_candidates = weight.get("candidates")
        declared_bytes = weight.get("bytes")
        if declared_candidates != recomputed_candidates:
            out.append(
                Finding(
                    run.objective,
                    "refs",
                    f"{pointer}/weight/candidates",
                    f"declares weight.candidates={declared_candidates!r} but its evidence "
                    f"names {recomputed_candidates} distinct candidate(s)",
                )
            )
        if declared_bytes != recomputed_bytes:
            out.append(
                Finding(
                    run.objective,
                    "refs",
                    f"{pointer}/weight/bytes",
                    f"declares weight.bytes={declared_bytes!r} but its evidence candidates "
                    f"sum to {recomputed_bytes}",
                )
            )
    return out


def check_audit(run: RunPaths) -> list[Finding]:
    """Reference checks over 00-audit.json against the staged dispositions.

    00-audit.json is written once, by the pass that runs last among the
    staged-triage prompts precisely because it consolidates every disposition
    part's deficiency_notes -- rb-triage-audit cannot even start until every
    dispositions fan-out member has finished, the same barrier reconcile and
    score hold for their own fan-outs. So unlike check_disposition_parts, this
    checker never has to tolerate a mid-fan-out 00-dispositions/: by the time
    00-audit.json exists to be checked at all, the barrier it was written
    behind has already closed, and it carries no check_verdicts-style caveat.
    Nothing here is semantic.

    `_readable_targets` does not cover 00-audit.json or any disposition part
    -- both are minted well after the artifacts that list enumerates -- so
    this checker self-guards each of them exactly as check_slices does for
    the plan.
    """
    if not run.audit.is_file():
        return []
    try:
        audit = read_json(run.audit)
    except ArtifactError as exc:
        return [Finding(run.audit, "refs", "", str(exc))]
    if not isinstance(audit, dict):
        return []

    out: list[Finding] = []
    deficiency_ids = {
        _str_or_none(d.get("deficiency_id"))
        for d in _as_list(audit.get("deficiencies"))
        if isinstance(d, dict)
    } - {None}
    projections = _as_list(audit.get("projections"))
    # Strong, exactly like check_triage's own needs_projection check:
    # projections[].sources[] does name a candidate, so this checks the
    # decline's own candidate is sourced, not merely that some projection
    # exists for something else.
    projected_candidate_ids = {
        _str_or_none(source.get("candidate_id"))
        for projection in projections
        if isinstance(projection, dict)
        for source in _as_list(projection.get("sources"))
        if isinstance(source, dict)
    } - {None}

    # Clause 3: every projection's closes names a real deficiency.
    for index, projection in enumerate(projections):
        if not isinstance(projection, dict):
            continue
        pointer = f"/projections/{index}/closes"
        for position, closes in enumerate(_as_list(projection.get("closes"))):
            if _str_or_none(closes) not in deficiency_ids:
                out.append(
                    Finding(
                        run.audit,
                        "refs",
                        f"{pointer}/{position}",
                        f"no such deficiency {closes!r}",
                    )
                )

    # Clauses 1 & 2 read every staged part's own declines. An absent
    # dispositions_dir here means a hand-assembled or manufactured audit
    # artifact rather than a mid-fan-out one (see the docstring for why that
    # distinction holds), so it is skipped rather than guessed at.
    if not run.dispositions_dir.is_dir():
        return out

    for slice_id in run.slice_ids_with_parts():
        part_path = run.disposition_part(slice_id)
        try:
            part = read_json(part_path)
        except ArtifactError as exc:
            out.append(Finding(part_path, "refs", "", str(exc)))
            continue
        if not isinstance(part, dict):
            continue

        # Strong for digest_insufficient too, unlike check_triage/seal's weak
        # form: those read the *consolidated* triage record, where
        # deficiencies[] carries no candidate-reference field to key a
        # stronger check on. One level upstream, before consolidation,
        # deficiency_notes[].candidate_id is exactly that field -- this is
        # not re-implementing rb-triage-audit's consolidation (which dedupes
        # notes across slices and mints deficiency_id), only checking whether
        # the consolidation the pass already performed covers what this part
        # flagged before it ran.
        noted_candidate_ids = {
            _str_or_none(note.get("candidate_id"))
            for note in _as_list(part.get("deficiency_notes"))
            if isinstance(note, dict)
        } - {None}

        for index, entry in enumerate(_as_list(part.get("dispositions"))):
            if not isinstance(entry, dict):
                continue
            if entry.get("disposition") != "decline":
                continue
            cid = _str_or_none(entry.get("candidate_id"))
            code = entry.get("reason_code")
            pointer = f"/dispositions/{index}/reason_code"
            if code == "digest_insufficient" and cid not in noted_candidate_ids:
                out.append(
                    Finding(
                        part_path,
                        "refs",
                        pointer,
                        f"a digest_insufficient decline for {entry.get('candidate_id')!r} is "
                        "not referenced by any deficiency_notes entry in this part",
                    )
                )
            elif code == "needs_projection" and cid not in projected_candidate_ids:
                out.append(
                    Finding(
                        part_path,
                        "refs",
                        pointer,
                        f"a needs_projection decline for {entry.get('candidate_id')!r} has no "
                        f"projection in {run.audit.name} sourcing it",
                    )
                )
    return out


def check_triage(run: RunPaths) -> list[Finding]:
    """Reference checks over 00-triage.json. Nothing here is semantic.

    The finding this check might seem to ask for -- a world-model gap whose closing
    evidence was declined at triage -- is deliberately NOT here. Matching gap
    prose to decline prose is semantic, and layer 2 checks that an element
    *references* a resolvable thing and never that the thing *supports* it. That
    pairing is a human's call at gate 1, surfaced by `rubrica gate-brief`.
    """
    triage = _load(run.triage)
    if not isinstance(triage, dict):
        return []
    catalogue = _load(run.catalogue)
    out: list[Finding] = []

    def report(pointer: str, message: str) -> None:
        out.append(Finding(run.triage, "refs", pointer, message))

    # Every list read below goes through _as_list, and every id that will
    # touch a dict or set goes through _str_or_none, because none of this is
    # schema-validated yet -- check_all has no ordering guarantee that layer 1
    # has already rejected the document check_triage is reading.
    dispositions = _as_list(triage.get("dispositions"))
    deficiency_ids = {
        _str_or_none(d.get("deficiency_id"))
        for d in _as_list(triage.get("deficiencies"))
        if isinstance(d, dict)
    } - {None}
    projections = _as_list(triage.get("projections"))
    # Strong form, for needs_projection only: the candidate a decline names must
    # actually be sourced by some projection, not merely coexist with an
    # unrelated one. digest_insufficient stays weak (see the comment at its
    # check below) because deficiencies[] carries no candidate-reference field
    # to check against -- projections[].sources[] does, so this one can be tight.
    projected_candidate_ids = {
        _str_or_none(source.get("candidate_id"))
        for projection in projections
        if isinstance(projection, dict)
        for source in _as_list(projection.get("sources"))
        if isinstance(source, dict)
    } - {None}

    candidates = {}
    if isinstance(catalogue, dict):
        candidates = {
            c["candidate_id"]: c
            for c in _as_list(catalogue.get("candidates"))
            if isinstance(c, dict) and isinstance(c.get("candidate_id"), str)
        }

    seen: set[str | None] = set()
    admits = 0
    for index, entry in enumerate(dispositions):
        if not isinstance(entry, dict):
            continue
        pointer = f"/dispositions/{index}"
        cid = entry.get("candidate_id")
        cid_str = _str_or_none(cid)
        if candidates and cid_str not in candidates:
            report(f"{pointer}/candidate_id", f"no such candidate {cid!r} in the catalogue")
        if cid_str in seen:
            report(f"{pointer}/candidate_id", f"candidate {cid!r} already has a disposition")
        seen.add(cid_str)

        code = entry.get("reason_code")
        if entry.get("disposition") == "decline":
            if not code:
                report(f"{pointer}/reason_code", "a decline must carry a reason_code")
            elif code == "digest_insufficient" and not deficiency_ids:
                # Weak by necessity: triage-0.1.json's deficiencies[] has no
                # candidate-reference field (deficiency_id, subject, statement,
                # optional closed_by -- none of them name a candidate_id), so
                # the strongest check layer 2 can mechanically make here is
                # "at least one deficiency exists at all". Anything stronger
                # would mean matching decline prose to deficiency prose, which
                # is semantic and out of bounds for this layer.
                report(
                    f"{pointer}/reason_code",
                    "a digest_insufficient decline must be referenced by a deficiency, or the "
                    "loss it records is invisible",
                )
            elif code == "needs_projection" and cid_str not in projected_candidate_ids:
                # Strong: projections[].sources[].candidate_id does name a
                # candidate, so this checks the decline's own candidate is
                # actually sourced by some projection -- not merely that the
                # triage record contains a projection for something else.
                report(
                    f"{pointer}/reason_code",
                    "a needs_projection decline must be sourced by a projection naming this "
                    "candidate, or its remedy is unstated",
                )
        else:
            admits += 1
            if code:
                report(f"{pointer}/reason_code", "reason_code names a decline; an admit has none")
            if cid_str in candidates and candidates[cid_str].get("admissible") is False:
                report(
                    f"{pointer}/disposition",
                    f"candidate {cid!r} is not admissible -- it is a container whose elements "
                    "are the candidates",
                )

    for cid in sorted(set(candidates) - seen):
        report("/dispositions", f"candidate {cid!r} has no disposition; every one must be ruled on")

    if dispositions and admits == 0:
        report(
            "/dispositions",
            "no candidate was admitted; an empty admitted set is a scoping failure rather than "
            "a triage result",
        )

    for index, projection in enumerate(projections):
        if not isinstance(projection, dict):
            continue
        pointer = f"/projections/{index}"
        for closes in _as_list(projection.get("closes")):
            if _str_or_none(closes) not in deficiency_ids:
                report(f"{pointer}/closes", f"no such deficiency {closes!r}")
        for position, source in enumerate(_as_list(projection.get("sources"))):
            if not isinstance(source, dict):
                continue
            source_cid = source.get("candidate_id")
            if candidates and _str_or_none(source_cid) not in candidates:
                report(
                    f"{pointer}/sources/{position}/candidate_id",
                    f"no such candidate {source_cid!r} to project from",
                )
    return out


def check_manifest(run: RunPaths) -> list[Finding]:
    """The manifest against 01-claims, and each claim's evidence against the manifest.

    Both directions: every claims file must name a registered input, and every
    registered input must have a claims file. The relation was one-directional
    until issue #19, on the argument that a registered input with no claims file
    is the normal state *during* the extract fan-out -- true, but not a state
    check-refs observes. There is no stage-scoped check-refs; check_all runs
    every checker the run has inputs for, and the orchestrator dispatches it
    after a fan-out completes. That is the argument check_disposition_parts,
    check_contradiction_parts, check_instances, check_verdicts and
    _scenario_round_findings all make, and until #19 the extract and instantiate
    fan-outs were the ones making it differently: a member that refused, died or
    was killed passed both layers at zero findings, then surfaced stages later --
    here as findings against the reconcile partials that had cited its absent
    claims, and for instantiate as an emitted suite one test short, which
    check_instances records.
    """
    manifest = _load(run.manifest)
    if manifest is None:
        return []
    out: list[Finding] = []

    def report(pointer: str, message: str) -> None:
        out.append(Finding(run.manifest, "refs", pointer, message))

    # A JSON Schema `format` keyword cannot express calendar validity: the
    # schema declares created_utc's format as date-time, but jsonschema's
    # date-time format is a no-op without rfc3339-validator, which this
    # project does not depend on -- so month 13 and hour 99 pass layer 1
    # unchallenged. This strptime call is what actually rejects them, which
    # makes it a genuine layer-2 check, not defensive tolerance of a run that
    # skipped validate; the try/except is only converting strptime's
    # documented raise into a finding instead of a traceback.
    created = manifest["created_utc"]
    try:
        datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        report(
            "/created_utc",
            f"{created!r} is not a real UTC timestamp of the form YYYY-MM-DDTHH:MM:SSZ",
        )

    registered: dict[str, int] = {}
    for i, entry in enumerate(manifest["inputs"]):
        artifact_id = entry["artifact_id"]
        if artifact_id in registered:
            report(
                f"/inputs/{i}/artifact_id",
                f"artifact_id {artifact_id!r} is already registered at "
                f"/inputs/{registered[artifact_id]}",
            )
            continue
        registered[artifact_id] = i

    # The guard is `is_dir()`, not a count, exactly as the sibling fan-out
    # checkers guard theirs: with no 01-claims/ at all the run has not reached
    # extract, and reporting every input there would spend the orchestrator's
    # single repair attempt on a phantom. Once the directory exists the
    # mid-fan-out window is deliberately *not* tolerated -- check-refs is
    # dispatched after every member has finished, so a missing file is real.
    if run.claims_dir.is_dir():
        extracted = {path.stem for path in list_json(run.claims_dir)}
        for artifact_id in sorted(set(registered) - extracted):
            out.append(
                Finding(
                    run.claims_dir,
                    "refs",
                    "",
                    f"input {artifact_id} has no claims file on disk; every registered input "
                    "needs one, even one recording that nothing could be extracted from it",
                )
            )

    for claim_id, paths in sorted(_claim_index(run).items()):
        if len(paths) > 1:
            names = ", ".join(sorted(p.name for p in paths))
            out.append(
                Finding(
                    run.claims_dir,
                    "refs",
                    "",
                    f"claim id {claim_id!r} is defined more than once, in {names}; every "
                    "world-model reference to it would resolve ambiguously",
                )
            )

    for path in list_json(run.claims_dir):
        payload = _load(path)
        if not isinstance(payload, dict):
            continue
        declared = payload["artifact_id"]
        if declared != path.stem:
            out.append(
                Finding(
                    path,
                    "refs",
                    "/artifact_id",
                    f"file declares artifact_id {declared!r} but is named {path.name}; the "
                    "filename is how every other stage addresses it",
                )
            )
        elif declared not in registered:
            out.append(
                Finding(
                    path,
                    "refs",
                    "/artifact_id",
                    f"artifact_id {declared!r} is not registered in the manifest",
                )
            )
        for i, claim in enumerate(payload["claims"]):
            for j, evidence in enumerate(claim["evidence"]):
                if evidence["artifact_id"] not in registered:
                    out.append(
                        Finding(
                            path,
                            "refs",
                            f"/claims/{i}/evidence/{j}/artifact_id",
                            f"evidence cites unregistered artifact: {evidence['artifact_id']}",
                        )
                    )
    return out


def check_inputs(run: RunPaths) -> list[Finding]:
    """The bytes in 00-inputs/ against the digests the manifest records.

    The reproducibility claim rests on this and nothing checked it. Two runs are
    comparable only if they read the same inputs, and manifest.inputs[].sha256 is
    the only record of what those were; a registered copy edited after intake
    makes every claim derived from it unattributable while every other gate in
    the project stays green.

    This re-hashes on every check-refs call, which is once per stage. Slice 1
    registers an api.json, a schema.json and a handful of traces, so the cost is
    milliseconds. If a large source tree is ever registered, the fix is a
    size-and-mtime shortcut here, not skipping the check.

    `stored_as` is validated rather than joined blindly: paths.input_file raises
    UnsafeSegment, which cli.py maps to exit 2, and a bad value in a stage output
    is a repairable defect that must arrive as a finding instead.
    """
    manifest = _load(run.manifest)
    if manifest is None:
        return []
    out: list[Finding] = []
    for i, entry in enumerate(manifest["inputs"]):
        artifact_id = entry["artifact_id"]
        stored_as = entry["stored_as"]
        if not is_safe_segment(stored_as):
            out.append(
                Finding(
                    run.manifest,
                    "refs",
                    f"/inputs/{i}/stored_as",
                    f"{stored_as!r} is not a safe path segment, so the registered copy of "
                    f"{artifact_id!r} cannot be located",
                )
            )
            continue
        path = run.input_file(stored_as)
        if not path.is_file():
            out.append(
                Finding(
                    run.manifest,
                    "refs",
                    f"/inputs/{i}/stored_as",
                    f"registered input {artifact_id!r} has no stored copy at {path}",
                )
            )
            continue
        actual = sha256_of(path)
        if actual != entry["sha256"]:
            out.append(
                Finding(
                    path,
                    "refs",
                    "",
                    f"stored bytes hash to {actual} but the manifest records {entry['sha256']} "
                    f"for {artifact_id!r}; the registered copy has been edited since intake, so "
                    "nothing derived from it is attributable to these inputs",
                )
            )
            continue
        size = path.stat().st_size
        if size != entry["bytes"]:
            out.append(
                Finding(
                    path,
                    "refs",
                    "",
                    f"stored copy is {size} bytes but the manifest records {entry['bytes']} for "
                    f"{artifact_id!r}",
                )
            )
    return out


def check_admitted_inputs(run: RunPaths) -> list[Finding]:
    """manifest.inputs[] against the admitted dispositions, one to one.

    Silent when there is no triage record: a run minted through `intake --input`
    never had one. Matching is by artifact_id, which admit_from_triage derives
    from candidate_id by the same suffix-on-collision rule -- so a mismatch here
    means an admission was dropped or one arrived from outside the gate.

    What this cannot catch: it replays admit_from_triage's own derivation
    (same sort, same _unique_artifact_id) rather than re-deriving the rule
    independently, so a bug in that shared computation, or in its sort order,
    is invisible here -- both sides would compute the identical wrong answer.
    """
    triage = _load(run.triage)
    if not isinstance(triage, dict):
        return []
    manifest = _load(run.manifest)
    if not isinstance(manifest, dict):
        return []

    # A local import, not a top-level one: intake.py already imports
    # check_triage from this module, so importing intake at module scope here
    # would be a load-time cycle. Reusing _unique_artifact_id -- rather than
    # writing a second spelling of "suffix on collision" in this module --
    # matters because the reverse direction is genuinely ambiguous:
    # "cap-json-2" could name either a real collision suffix or a candidate
    # literally called that. Replaying the same forward computation
    # admit_from_triage used, in the same sorted order, has no such ambiguity.
    from rubrica.intake import _unique_artifact_id, admit_sort_key

    admits = [
        entry
        for entry in _as_list(triage.get("dispositions"))
        if isinstance(entry, dict)
        and entry.get("disposition") == "admit"
        and isinstance(entry.get("candidate_id"), str)
    ]
    # intake.admit_sort_key, imported rather than respelled here, for the
    # reason its own docstring gives: this replay must produce the *identical*
    # order admit_from_triage materialised in, because `_unique_artifact_id`'s
    # collision suffixes depend on it. The local lambda it replaces also
    # shared that function's measured TypeError -- a string `priority`
    # alongside an integer one raised out of `sort`, and check-refs turned a
    # malformed triage record into a fabricated `[internal]` finding naming the
    # run directory instead of the record that carries the defect.
    admits.sort(key=admit_sort_key)
    used: dict[str, int] = {}
    expected = {_unique_artifact_id(d["candidate_id"], used): d["candidate_id"] for d in admits}

    registered = {
        entry["artifact_id"]
        for entry in _as_list(manifest.get("inputs"))
        if isinstance(entry, dict) and isinstance(entry.get("artifact_id"), str)
    }

    out: list[Finding] = []
    for artifact_id, candidate_id in sorted(expected.items()):
        if artifact_id not in registered:
            out.append(
                Finding(
                    run.manifest,
                    "refs",
                    "/inputs",
                    f"candidate {candidate_id!r} was admitted at triage but has no entry in the "
                    "manifest -- an admission intake dropped",
                )
            )
    for artifact_id in sorted(registered - set(expected)):
        out.append(
            Finding(
                run.manifest,
                "refs",
                "/inputs",
                f"input {artifact_id!r} is registered but was never admitted at triage -- it "
                "entered the run from outside the gate",
            )
        )
    return out


def check_limits(run: RunPaths) -> list[Finding]:
    """The manifest's loop and suite bounds against what the run actually holds.

    intake writes these and, until now, nothing read them. They are the reason
    run cost is finite, so an unenforced cap is not a documentation gap: it is
    the absence of the bound.

    `limits`, `max_rounds`, `max_scenarios`, and every key indexed below are
    `required` by their schemas, so on a schema-valid document they are always
    present -- but not guaranteed to be a Python `int`: jsonschema's `type:
    integer` accepts any float with a zero fractional part, so a schema-valid
    manifest can carry max_rounds as 2.0. No isinstance guard is added here
    for that, because `>` compares int and float transparently and needs no
    help. A guard would be actively wrong: the brief this function was
    transcribed from wrapped the entire round-check loop in `if
    isinstance(max_rounds, int):`, which would make a float bound silently
    turn the check into a no-op instead of enforcing it -- the exact
    unenforced-cap defect this task exists to close, not a safer version of
    it. A malformed document (e.g. a non-numeric bound) raises on the `>`
    comparison, per this module's documented precondition that layer 1 ran
    first.
    """
    manifest = _load(run.manifest)
    if manifest is None:
        return []
    limits = manifest["limits"]
    max_rounds = limits["max_rounds"]
    max_scenarios = limits["max_scenarios"]
    out: list[Finding] = []

    scenarios_doc = _load(run.scenarios)
    if scenarios_doc is not None:
        scenarios = scenarios_doc["scenarios"]

        def report(pointer: str, message: str) -> None:
            out.append(Finding(run.scenarios, "refs", pointer, message))

        for i, scenario in enumerate(scenarios):
            if scenario["round"] > max_rounds:
                report(
                    f"/scenarios/{i}/round",
                    f"scenario is tagged round {scenario['round']} but the manifest caps "
                    f"the enrichment loop at max_rounds={max_rounds}",
                )
            provenance_round = scenario["provenance"]["round"]
            if provenance_round > max_rounds:
                report(
                    f"/scenarios/{i}/provenance/round",
                    f"provenance records round {provenance_round} but the manifest caps "
                    f"the enrichment loop at max_rounds={max_rounds}",
                )
        open_count = sum(1 for s in scenarios if s["status"] in OPEN_STATUSES)
        if open_count > max_scenarios:
            report(
                "/scenarios",
                f"{open_count} scenarios are proposed or active but the manifest caps the "
                f"suite at max_scenarios={max_scenarios}; duplicate and rejected scenarios "
                "do not count against it",
            )

    coverage = _load(run.coverage_latest)
    if coverage is not None and coverage["round"] > max_rounds:
        out.append(
            Finding(
                run.coverage_latest,
                "refs",
                "/round",
                f"coverage is reported for round {coverage['round']} but the manifest caps the "
                f"enrichment loop at max_rounds={max_rounds}",
            )
        )
    return out


def check_subjects(run: RunPaths) -> list[Finding]:
    """The claim subject cover, and its totality.

    Totality is the whole reason a subject cover is acceptable where a
    code-proposed pair filter was not. A filter drops one of ~n^2/2 pairs that
    appear nowhere on disk, so nothing can report the omission and no human can
    overrule it; a cover names every claim, so a claim it misses is a finding
    here. That difference is why the cover exists in this shape, and this checker
    is the half of it that is mechanical.

    The design's other clause for this checker -- every subject has at least one
    claim -- is not here because layer 1 already has it: subjects-0.1.json
    reaches world-model-0.1.json#/$defs/claim_refs, which carries minItems 1. A
    property a deterministic gate already enforces belongs to that gate.
    """
    cover = _load(run.subjects)
    if cover is None:
        return []
    out: list[Finding] = []

    def report(pointer: str, message: str) -> None:
        out.append(Finding(run.subjects, "refs", pointer, message))

    subjects = _as_list(cover.get("subjects"))
    for dupe in _dupes([s["id"] for s in subjects if isinstance(s, dict)]):
        report("/subjects", f"duplicate subject id {dupe!r}")

    known = _claim_ids(run)
    covered: set[str] = set()
    for i, subject in enumerate(subjects):
        if not isinstance(subject, dict):
            continue
        for j, claim_id in enumerate(_as_list(subject.get("claims"))):
            covered.add(claim_id)
            if claim_id not in known:
                report(f"/subjects/{i}/claims/{j}", f"no such claim: {claim_id}")

    for claim_id in sorted(known - covered):
        report(
            "/subjects",
            f"no subject covers claim {claim_id}; the cover must be total, or the "
            "contradiction sweep never compares that claim against anything",
        )
    return out


def check_contradiction_parts(run: RunPaths) -> list[Finding]:
    """One contradictions part per subject in the cover, and its references.

    **Meaningful only once every fan-out member has finished.** This reports every
    subject without a part from the moment 01-contradictions/ exists, so mid-
    fan-out most of them are missing by construction -- exactly the caveat
    check_verdicts carries, and for the same reason. There is no stage-scoped
    check-refs: check_all runs every checker the run has inputs for.

    The subject_id *field* is checked against the *filename* because they answer
    different questions: the filename is the slice the member was dispatched with,
    the field is the slice it believed it was working on. A mismatch means one
    member wrote a sibling's slice, which is the failure the fourth dispatch
    argument exists to prevent and which no schema can see.

    Both sides of every recorded contradiction must also be claims the part's own
    subject names -- rb-reconcile-contradict's invariant 3, and until this clause
    existed nothing enforced it: the two claim ids were resolved against the whole
    run, so a member reaching outside its slice was clean. A claim outside a
    member's own subject is a sibling member's to sweep, so recording it here
    would double-count what that sibling already covers, and the finding belongs
    on the part. This stays a **reference** check, in layer 2's remit: does this
    id appear in that subject's claim list. Whether the two claims genuinely
    contradict is semantic, and nothing here judges it.
    """
    cover = _load(run.subjects)
    if cover is None or not run.contradictions_dir.is_dir():
        return []
    out: list[Finding] = []
    declared = {
        s["id"] for s in _as_list(cover.get("subjects")) if isinstance(s, dict) and "id" in s
    }
    on_disk = set(run.subject_part_ids())

    # A part filename that is not a safe path segment cannot be a subject id, so
    # it is not in on_disk and contradiction_part() cannot be asked for it. Same
    # treatment as check_instances gives an unsafe instance directory name: a
    # repairable defect in the pass that wrote it, so an ordinary finding at exit
    # 1 rather than an UnsafeSegment reaching cli.py as exit 2 and taking every
    # other finding in the run with it.
    for name in run.unsafe_contradiction_part_names():
        out.append(
            Finding(
                run.contradictions_dir,
                "refs",
                "",
                f"contradictions part {name!r} is not a usable subject id: a subject id must "
                "start with a letter or digit and contain only letters, digits, dots, dashes, "
                "and underscores",
            )
        )

    for subject_id in sorted(declared - on_disk):
        out.append(
            Finding(
                run.contradictions_dir,
                "refs",
                "",
                f"no contradictions part for subject {subject_id}; every subject needs one, "
                "even one recording that no disagreement was found there",
            )
        )
    for subject_id in sorted(on_disk - declared):
        out.append(
            Finding(
                run.contradiction_part(subject_id),
                "refs",
                "",
                f"contradictions part for subject {subject_id}, which 01-subjects.json does "
                "not declare",
            )
        )

    # Keyed only on string ids, so an id-less or non-string-id subject simply has
    # no entry and the own-subject clause below skips its part rather than
    # resolving against a claim list it cannot address.
    covered_by = {
        s["id"]: {c for c in _as_list(s.get("claims")) if isinstance(c, str)}
        for s in _as_list(cover.get("subjects"))
        if isinstance(s, dict) and isinstance(s.get("id"), str)
    }

    known = _claim_ids(run)
    seen: list[str] = []
    for path in list_json(run.contradictions_dir):
        part = _load(path)
        if part is None:
            continue
        field = _str_or_none(part.get("subject_id"))
        # The filename/field comparison is skipped for an unsafe stem, already
        # reported above. Its message would otherwise read "is the part for
        # 'subject 1'", asserting that an unusable stem is the subject this file
        # belongs to -- a second finding restating the first, and doing it with a
        # false clause. The contents are still checked below: nothing here joins
        # a path, so an unsafe name is no hazard once list_json has handed it over.
        if field is not None and field != path.stem and is_safe_segment(path.stem):
            out.append(
                Finding(
                    path,
                    "refs",
                    "/subject_id",
                    f"declares subject_id {field!r} but is the part for {path.stem!r}",
                )
            )
        # The claim list of the subject this file *is* the part for, or None when
        # the cover does not declare that subject at all -- already reported above
        # as an undeclared part, so the clause below stays quiet rather than adding
        # a second finding derived from the same absence.
        own = covered_by.get(path.stem)
        for i, contradiction in enumerate(_as_list(part.get("contradictions"))):
            if not isinstance(contradiction, dict):
                continue
            # _str_or_none, not str(): str(None) produced the literal id 'None',
            # so an id-less contradiction in two parts drew "duplicate
            # contradiction id 'None' across parts" and sent the one bounded
            # repair after an id that exists nowhere. The real defect -- a missing
            # required `id` -- is contradictions-part-0.1.json's, at layer 1.
            contradiction_id = _str_or_none(contradiction.get("id"))
            if contradiction_id is not None:
                seen.append(contradiction_id)
            for side in ("claim_a", "claim_b"):
                claim_id = contradiction.get(side)
                if claim_id not in known:
                    out.append(
                        Finding(
                            path,
                            "refs",
                            f"/contradictions/{i}/{side}",
                            f"no such claim: {claim_id}",
                        )
                    )
                elif own is not None and claim_id not in own:
                    # Reached only after `claim_id in known` succeeded, so the
                    # value is hashable here and this set membership cannot raise
                    # TypeError on a list- or dict-valued side.
                    out.append(
                        Finding(
                            path,
                            "refs",
                            f"/contradictions/{i}/{side}",
                            f"claim {claim_id} is not one subject {path.stem!r} names; both "
                            "sides of a contradiction must be claims this subject covers, "
                            "since a claim outside this subject is a sibling member's to "
                            "sweep, not this one's",
                        )
                    )
    for dupe in _dupes(seen):
        out.append(
            Finding(
                run.contradictions_dir,
                "refs",
                "",
                f"duplicate contradiction id {dupe!r} across parts",
            )
        )
    return out


def check_outcomes(run: RunPaths) -> list[Finding]:
    """Every declared capability has outcome classes, and no others do.

    The completeness half is what splitting the outcomes pass out bought: an
    unswept capability shrinks the coverage denominator, and a run can reach high
    coverage that way without ever testing anything hard. Nothing checked it while
    both lived in one turn.

    Both clauses overlap a branch of reconcile.seal's refusal, deliberately: the
    layers fire at different times. The seal refuses before writing a world model;
    this reports on a run at any stage, including one that is never sealed. What
    neither clause can see is *two outcome records for one capability*: the
    `recorded` set comprehension below collapses them to one member, so neither
    direction of its comparison reports anything and the seal stays the only place
    a duplicate outcomes record is ever caught.
    """
    capabilities = _load(run.capabilities_part)
    outcomes = _load(run.outcomes_part)
    if capabilities is None or outcomes is None:
        return []
    out: list[Finding] = []
    declared = [
        c["id"]
        for c in _as_list(capabilities.get("capabilities"))
        if isinstance(c, dict) and "id" in c
    ]
    recorded = {
        e["capability_id"]
        for e in _as_list(outcomes.get("outcomes"))
        if isinstance(e, dict) and "capability_id" in e
    }
    for capability_id in sorted(set(declared) - recorded):
        out.append(
            Finding(
                run.outcomes_part,
                "refs",
                "/outcomes",
                # Same correction as reconcile.py's twin of this refusal: "a
                # capability left unswept shrinks the surface every later percentage
                # is measured against" was true of every capability while the
                # denominator counted every cell, and is true of a bound one only
                # now that it counts the drivable ones. The finding does not change
                # -- an unswept capability names no cells, so nothing accounts for
                # it in either direction.
                f"no outcome classes for declared capability {capability_id}; a capability "
                "with no outcome classes names no cells at all, so a bound one left unswept "
                "shrinks the surface every later percentage is measured against, and an "
                "unbound one leaves the seal's unreachable holes nothing to account for",
            )
        )
    for capability_id in sorted(recorded - set(declared)):
        out.append(
            Finding(
                run.outcomes_part,
                "refs",
                "/outcomes",
                f"outcome classes for {capability_id}, which 01-capabilities.json does not declare",
            )
        )
    return out


def check_world_model(run: RunPaths) -> list[Finding]:
    """Internal consistency of the world model, including the denominator."""
    world = _load(run.world_model)
    if world is None:
        return []
    out: list[Finding] = []
    path = run.world_model

    def report(pointer: str, message: str) -> None:
        out.append(Finding(path, "refs", pointer, message))

    known_claims = _claim_ids(run)
    entity_ids = {e["id"] for e in world.get("entities", [])}
    actor_ids = {a["id"] for a in world.get("actors", [])}
    collections = {e["collection"] for e in world.get("entities", [])}

    for group in ("capabilities", "entities", "actors", "goals"):
        ids = [item["id"] for item in world.get(group, [])]
        for dupe in _dupes(ids):
            report(f"/{group}", f"duplicate id {dupe!r}")
        for i, item in enumerate(world.get(group, [])):
            for j, claim_id in enumerate(item.get("claims", [])):
                if claim_id not in known_claims:
                    report(f"/{group}/{i}/claims/{j}", f"no such claim: {claim_id}")

    # The three nested citation sites $defs/invariant, $defs/outcome_class and
    # $defs/gap gained in issue #6, resolved on the same one-directional rule as
    # every other reference in this module: that the id exists, never that the
    # claim supports the element. Support is semantic and belongs to gate 1.
    #
    # Without these loops the requirement would be satisfiable with an invented
    # id: `utilisation._cited_claim_ids` counts a child element's claims, so a
    # fabricated one would raise an input's utilisation without any checker ever
    # resolving it.
    #
    # `_as_list` at every level, `isinstance` on each element, and `isinstance` on
    # each claim entry, because these loops reach shapes nothing reached before.
    # `gaps` in particular was iterated by no loop in this function, so every
    # malformed spelling of it was clean here and an unguarded loop makes it raise
    # instead. (check_coverage does read `world.get("gaps", [])`, for its hole refs.)
    # Three measurements, each of a real defect an earlier draft of this block had:
    #
    #   - `"gaps": null` and `"gaps": "x"` raised AttributeError out of a layer-2
    #     gate. Exit 1, not 2, and the distinction is the same one the third
    #     bullet draws: cli.py's named handler maps only (OSError, UsageError,
    #     ArtifactError, UnknownStage) to 2, and `except Exception` takes an
    #     AttributeError to exit 1 with a generic `internal` finding -- measured,
    #     by raising one out of this very checker. So it is the specificity half
    #     of the rule that it breaks, never the exit-code half: a repairable
    #     stage defect reported against nothing in particular.
    #   - `outcome_class["claims"] = "nope"` reported four `no such claim` findings,
    #     one per character: the wrong-artifact class this module has shipped once.
    #   - `claims: [{"a": 1}]` at any of the three sites raised `TypeError:
    #     unhashable type: 'dict'` from the `not in known_claims` test below.
    #     `cli.py` converts that to exit 1 with a generic `internal` finding, so it
    #     is not an exit-2 violation -- but every other real finding in that world
    #     model is suppressed and replaced by a message naming nothing, which is the
    #     specificity half of the same rule.
    #
    # A non-string claim entry is therefore skipped silently rather than reported,
    # and that is deliberate: `claim_refs` items `$ref` `#/$defs/id`, a patterned
    # string, so a non-string there is already a layer-1 failure -- and a property a
    # deterministic gate enforces belongs to that gate, not to a second one.
    for i, capability in enumerate(_as_list(world.get("capabilities"))):
        if not isinstance(capability, dict):
            continue
        for j, outcome_class in enumerate(_as_list(capability.get("outcome_classes"))):
            if not isinstance(outcome_class, dict):
                continue
            for k, claim_id in enumerate(_as_list(outcome_class.get("claims"))):
                if not isinstance(claim_id, str):
                    continue
                if claim_id not in known_claims:
                    report(
                        f"/capabilities/{i}/outcome_classes/{j}/claims/{k}",
                        f"no such claim: {claim_id}",
                    )
    for i, entity in enumerate(_as_list(world.get("entities"))):
        if not isinstance(entity, dict):
            continue
        for j, invariant in enumerate(_as_list(entity.get("invariants"))):
            if not isinstance(invariant, dict):
                continue
            for k, claim_id in enumerate(_as_list(invariant.get("claims"))):
                if not isinstance(claim_id, str):
                    continue
                if claim_id not in known_claims:
                    report(
                        f"/entities/{i}/invariants/{j}/claims/{k}",
                        f"no such claim: {claim_id}",
                    )
    for i, gap in enumerate(_as_list(world.get("gaps"))):
        if not isinstance(gap, dict):
            continue
        for k, claim_id in enumerate(_as_list(gap.get("claims"))):
            if not isinstance(claim_id, str):
                continue
            if claim_id not in known_claims:
                report(f"/gaps/{i}/claims/{k}", f"no such claim: {claim_id}")

    for i, entity in enumerate(world.get("entities", [])):
        for j, relation in enumerate(entity.get("relations", [])):
            if relation["target_entity_id"] not in entity_ids:
                report(
                    f"/entities/{i}/relations/{j}/target_entity_id",
                    f"no such entity: {relation['target_entity_id']}",
                )
        for j, invariant in enumerate(entity.get("invariants", [])):
            machine = invariant.get("machine")
            if not machine:
                continue
            for key in ("collection", "of"):
                name = machine.get(key)
                if name is not None and name not in collections:
                    report(
                        f"/entities/{i}/invariants/{j}/machine/{key}",
                        f"invariant references undeclared collection: {name}",
                    )

    for i, goal in enumerate(world.get("goals", [])):
        if goal["actor_id"] not in actor_ids:
            report(f"/goals/{i}/actor_id", f"no such actor: {goal['actor_id']}")

    for i, contradiction in enumerate(world.get("contradictions", [])):
        for side in ("claim_a", "claim_b"):
            if contradiction[side] not in known_claims:
                report(f"/contradictions/{i}/{side}", f"no such claim: {contradiction[side]}")

    denominator = world.get("denominator", {})
    # drivable_cells, not _cells: the denominator counts what the suite can be
    # scored against, while _cells stays wide because it resolves references. The
    # seal writes len() of this same function, which is what keeps the field an
    # identity rather than two spellings that can drift.
    actual_cells = len(drivable_cells(world))
    if denominator.get("capability_cells") != actual_cells:
        report(
            "/denominator/capability_cells",
            f"declared capability_cells={denominator.get('capability_cells')} but the world "
            f"model declares {actual_cells} drivable capability x outcome-class cells",
        )
    actual_goals = len(world.get("goals", []))
    if denominator.get("goals") != actual_goals:
        report(
            "/denominator/goals",
            f"declared goals={denominator.get('goals')} but the world model declares "
            f"{actual_goals}",
        )
    return out


# Which claim kinds each reconcile pass is accountable for. Every kind in
# claims-0.1.json's enum now has an owner among the passes below -- `tool` was
# the one that did not, and reconcile-services took it in the commit that added
# the pass -- so the partition is whole rather than pending. Nothing compares
# this table to the schema's enum, deliberately: a pass's own-kind number is well
# defined whether or not every kind has an owner, so a checker demanding total
# coverage would have had to invent an owner for a kind whose pass did not exist
# yet, and would demand one again of the next kind added ahead of its pass.
#
# What makes a per-pass number possible is the *partition* -- no kind having two
# owners -- and not one kind per pass: entities_part owns two and goals_part owns
# two, and both numbers are still per-pass because no other pass is accountable
# for those kinds. Measured on run-20260823-112746, per-kind citation ran
# capability 110/135 (the pass that read 23/23 files) and goal 2/38 (the pass
# that read 3/23), while the run's one aggregate utilisation figure was 33.6% --
# the average that hid both. reconcile-gaps owns no kind, and reconcile-subjects
# and reconcile-contradict need no accounting because check_subjects already
# makes the cover total.
PASS_OWN_KINDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("capabilities_part", ("capability",)),
    ("entities_part", ("entity", "invariant")),
    ("outcomes_part", ("outcome_class",)),
    ("goals_part", ("actor", "goal")),
    ("services_part", ("tool",)),
)


def check_input_dispositions(run: RunPaths) -> list[Finding]:
    """Each reconcile pass's accounting of the inputs it read, recomputed.

    Issue #6 measured a pass's read coverage of 01-claims/ varying 3/23 to 23/23
    across byte-identical dispatches, with claims in files it never opened cited
    at exactly 0/167. Neither check layer could see it: a skimmed read produces a
    well-formed partial, and utilisation is a lagging aggregate that averages a
    diligent pass with a skimming one.

    So every number a row declares is recomputed here -- `own_kind_total` from
    the claims file, `cited` from the part's own citations -- which makes a wrong
    number a finding rather than making a right one evidence of a read.
    `own_kind_total` is **recomputable, not unforgeable**: it is legitimately zero
    wherever the input holds no claim of `own_kinds`, the finding message below
    states the recomputed count back to the pass inside its own dispatch, and a
    mechanical count over `01-claims/` yields it without reading a claim.
    `docs/design/limitations.md` records that leak beside the `rb-reconcile-gaps`
    entry, with what this accounting does deliver instead.

    What this deliberately does *not* report: a row whose own_kind_total is
    positive and whose cited is zero. Such a row already carries a required note,
    so the drop is on the record and belongs to the human at gate 1. Making it a
    finding would fail a repair round that cannot repair anything, and would put
    a coverage judgment behind an exit code -- the threshold
    check_claim_utilisation refuses for a reason its own docstring measures.
    """
    manifest = _load(run.manifest)
    if manifest is None:
        return []
    declared = [
        entry["artifact_id"]
        for entry in _as_list(manifest.get("inputs"))
        if isinstance(entry, dict) and isinstance(entry.get("artifact_id"), str)
    ]
    by_artifact = _claims_by_artifact(run)

    out: list[Finding] = []
    for attribute, own_kinds in PASS_OWN_KINDS:
        path = getattr(run, attribute)
        part = _load(path)
        if not isinstance(part, dict):
            # An absent or unreadable partial is reconcile.seal's finding and
            # layer 1's; reporting it again here would double-count one defect
            # and name a second artifact for it.
            #
            # `isinstance` rather than `is None`, and the difference is reachable:
            # `_load` returns whatever the document holds, so a partial that is a
            # list or a string reached `part.get` and raised AttributeError out of
            # layer 2 -- measured, `["nope"]` in each of the four partials that
            # then existed. For `01-entities.json` and `01-goals.json` this is the
            # *only* layer-2 reader, so nothing older raised first and the guard
            # closes the whole instance for them rather than moving it.
            # `01-services.json` was the third such case and the deepest of them
            # when the guard was written, since reconcile-seal did not read it then
            # either; it now has readers on every side -- `synthesise-interfaces`
            # refuses a non-dict one by name (interfaces.synthesise), the seal
            # refuses one through its own read door, and `check_services` below
            # guards the same read the same way -- so the guard here no longer
            # closes that instance alone. It stays because this checker still runs
            # first and must not raise past any of them.
            # `01-capabilities.json` and `01-outcomes.json` still raise out of
            # `check_outcomes`, which runs earlier in check_all and is not this
            # branch's read. A non-dict document is the same class as an
            # unreadable one -- layer 1 rejects it, and every partial's schema is
            # `"type": "object"` -- so it takes the same branch rather than a
            # finding of its own.
            continue

        # `path=path` binds the loop variable deliberately: ruff's B023 fires
        # otherwise, and it would be a real bug -- every finding in the run would
        # be reported against the last partial this loop reached.
        def report(pointer: str, message: str, path: Path = path) -> None:
            out.append(Finding(path, "refs", pointer, message))

        rows = [row for row in _as_list(part.get("inputs_seen")) if isinstance(row, dict)]
        cited_ids = set(_claim_refs_in(part))
        seen: set[str] = set()

        for i, row in enumerate(rows):
            artifact_id = row.get("artifact_id")
            if not isinstance(artifact_id, str):
                continue
            seen.add(artifact_id)
            if artifact_id not in declared:
                report(
                    f"/inputs_seen/{i}/artifact_id",
                    f"no such input: {artifact_id}; the accounting must be over "
                    "manifest.inputs, and a row for an artifact the manifest does not "
                    "name is a row about nothing",
                )
                continue
            # A claims file that is absent or unreadable contributes no claims, so
            # this counts 0 for it and reports only the count disagreement it
            # genuinely sees against the partial.
            #
            # An *unreadable* claims file is check_readable's finding, by name. An
            # *absent* one is deliberately nobody's: check_manifest checks the
            # claims-to-manifest direction only, because "a registered input with
            # no claims file yet is the normal state during the extract fan-out",
            # and this checker must not become the place it is reported for the
            # same reason -- the reconcile partials do not exist during that
            # fan-out, so a row's disagreement is the only signal here, and it is
            # a true one: a row declaring counts for a file that is gone is wrong
            # whatever became of the file. Inferring the absence *from* the
            # disagreement is what this must not do. check-refs over an unreadable
            # claims directory once produced four fabricated `no such claim`
            # findings against a correct world model, and naming the wrong
            # artifact is what sends the orchestrator's one bounded repair at a
            # file that is fine.
            own = [
                claim
                for claim in by_artifact.get(artifact_id, [])
                if claim.get("kind") in own_kinds
            ]
            actual_cited = sum(1 for claim in own if claim.get("id") in cited_ids)
            if row.get("own_kind_total") != len(own):
                report(
                    f"/inputs_seen/{i}/own_kind_total",
                    f"declared own_kind_total={row.get('own_kind_total')} for "
                    f"{artifact_id} but 01-claims/ holds {len(own)} claim(s) of "
                    f"{', '.join(own_kinds)}",
                )
            if row.get("cited") != actual_cited:
                report(
                    f"/inputs_seen/{i}/cited",
                    f"declared cited={row.get('cited')} for {artifact_id} but this "
                    f"artifact's claims appear {actual_cited} time(s) in this part",
                )
            # Only this clause is guarded on the reads being integers, and that
            # asymmetry is the point: the two comparisons above are `!=` against a
            # recomputed int, which a string or a None fails cleanly and reports,
            # so a malformed row still produces findings rather than falling
            # silent. Addition does not fail cleanly. Measured on a real toy run,
            # `"cited": "2"` in 01-outcomes.json raised `TypeError: can only
            # concatenate str (not "int") to str` out of this line; cli.py turns
            # that into exit 1 with one generic `[internal]` finding, so every
            # other real finding in the run is lost -- the specificity failure
            # check_world_model's guard block above records the same measurement
            # for. check_all has no ordering guarantee that layer 1 rejected the
            # document first (_as_list's docstring states the rule), and
            # check_verdicts' declared-vs-found comparison guards both sides this
            # same way.
            #
            # One behaviour change comes with the guard, and it is deliberate: a
            # row *missing* `dropped` outright now fails the isinstance and this
            # clause does not fire, where the `.get(key, 0)` default it replaced
            # read the absence as 0 and could report the arithmetic. The two
            # comparisons above are untouched and still report. Layer 1 owns the
            # absence -- `dropped` is required and `"type": "integer"` in
            # inputs-seen-0.1.json -- and a property a deterministic gate already
            # enforces belongs to that gate, not to a second reading of it here
            # that would report the same defect against a different pointer.
            counts = [row.get(key) for key in ("cited", "dropped", "own_kind_total")]
            if all(isinstance(value, int) for value in counts) and (
                counts[0] + counts[1] != counts[2]
            ):
                report(
                    f"/inputs_seen/{i}",
                    f"cited + dropped does not equal own_kind_total for {artifact_id}",
                )

        for artifact_id in [a for a in declared if a not in seen]:
            report(
                "/inputs_seen",
                f"no row for input {artifact_id}; the accounting must be total over "
                "manifest.inputs, or a pass that never opened a claims file is "
                "indistinguishable from one that opened it and cited nothing",
            )
    return out


def _stored_input_paths(run: RunPaths) -> dict[str, Path]:
    """artifact_id -> the registered copy of that input under 00-inputs/.

    The same resolution check_inputs performs -- manifest entry, `stored_as`,
    paths.input_file -- and it has to stay the same one: a payload compared
    against some other reading of the input would answer a question nobody asked.

    `stored_as` is asked is_safe_segment first for the reason check_inputs asks
    it: paths.input_file raises UnsafeSegment, which cli.py maps to exit 2, and a
    bad value in a stage's output is a repairable defect that must arrive as a
    finding instead. Here it owes silence rather than a second finding -- it is
    reported already, against the manifest it lives in.
    """
    manifest = _load(run.manifest)
    if not isinstance(manifest, dict):
        return {}
    out: dict[str, Path] = {}
    for entry in _as_list(manifest.get("inputs")):
        if not isinstance(entry, dict):
            continue
        artifact_id = _str_or_none(entry.get("artifact_id"))
        stored_as = _str_or_none(entry.get("stored_as"))
        if artifact_id is None or stored_as is None or not is_safe_segment(stored_as):
            continue
        out[artifact_id] = run.input_file(stored_as)
    return out


def _payload_findings(
    claim_id: str,
    claim: dict,
    claims_file: Path | None,
    claim_index: int,
    stored: dict[str, Path],
) -> list[Finding]:
    """One `schema_claim`'s payload against the input region its evidence names.

    This is what makes a prompt's byte-for-byte transcription of an input schema
    falsifiable. Synthesis does not read 00-inputs/ -- the stage that reads inputs
    is extract -- so the payload reaches the OpenAPI document through a claim or
    not at all, and nothing else in the pipeline can tell a transcribed schema
    from an invented one.

    Structural identity, not support. Whether a claim *supports* an element is
    semantic and layer 2 is forbidden to invent a mechanical check for it; whether
    a payload equals the document region its own locator names is decidable, and
    is exactly the class layer 2 exists for. Decoded values, never bytes: the
    payload and the input are each parsed first, so a reformatted schema whose
    parsed value is unchanged is not a fidelity defect and must not read as one.

    Everything that is merely *not comparable* returns nothing, because a
    structural non-comparison is not evidence of a defect:

    - no payload -- interfaces.synthesise refuses a `schema_claim` carrying none,
      by name and against the services part, so a second report here would name a
      second artifact for one defect;
    - an input this checker cannot resolve to a path, or whose registered copy is
      absent, not UTF-8 or not JSON: check_manifest, check_inputs and
      check_readable each own one of those, and a markdown input reaches the last
      of them every time a prose claim is named as a schema claim;
    - a locator that is not a JSON pointer. Locators come in three shapes across
      this project's corpora, and only the first is comparable:
      `#/tools/0/input_schema`, a bare pointer into a JSON input;
      `#operator-notes`, a markdown heading anchor for prose; and
      `api.json#/tools/0`, the URI-with-path form tests/builders.py carries.
      claims-0.1.json constrains `locator` to a non-empty string and nothing
      further, so layer 1 admits all three and any fourth. resolve_pointer
      *raises* on the last two rather than returning UNSET, and an exception
      escaping here is exit 1 with one `[internal]` finding naming the run root --
      the class cli.py's catch-all and findings.py exist to prevent.

    A pointer that resolves to *nothing* is a finding, and deliberately so: a
    fabricated payload behind a fabricated locator is precisely what silence there
    would let through, and that is the property this check exists to observe.

    A pointer that resolves to a JSON *string* is the one further abstention, and
    unlike the three above it is about the resolved value rather than the locator's
    shape. `payload` is `{"type": "object"}` in claims-0.1.json, so a string target
    makes the comparison below unequal by construction and the finding a certain
    false positive. See the guard for the measurement that found it.
    """
    payload = claim.get("payload")
    if not isinstance(payload, dict) or claims_file is None:
        return []
    evidence = _as_list(claim.get("evidence"))
    first = evidence[0] if evidence and isinstance(evidence[0], dict) else None
    if first is None:
        # minItems 1 of evidence objects is layer 1's requirement; a claim with
        # neither names no region for this to read.
        return []
    artifact_id = _str_or_none(first.get("artifact_id"))
    locator = _str_or_none(first.get("locator"))
    if artifact_id is None or locator is None:
        return []
    document_path = stored.get(artifact_id)
    if document_path is None:
        return []
    document = _load(document_path)
    if document is None:
        return []
    pointer = locator[1:] if locator.startswith("#") else locator
    if not pointer.startswith("/"):
        return []
    value = resolve_pointer(document, pointer)
    if value is UNSET:
        return [
            Finding(
                claims_file,
                "refs",
                f"/claims/{claim_index}/evidence/0/locator",
                f"{claim_id} records locator {locator} in {artifact_id}, which resolves to "
                f"nothing in {document_path.name}, so the payload every simulator of this "
                "tool is built from cannot be checked against the input it claims to copy",
            )
        ]
    if isinstance(value, str):
        # A pointer that lands on a JSON *string* is not comparable, and reporting
        # drift for it is a guaranteed false positive: claims-0.1.json declares
        # `payload` as `{"type": "object"}`, so layer 1 has already rejected any
        # payload that could equal a string, and the `!=` below can therefore only
        # ever fire. Measured on run-20260830-101018, an MLflow trace corpus: every
        # one of twelve rb-extract dispatches found the target's tool declarations
        # stored inside JSON-*encoded string* attributes, so no pointer over the
        # document reaches a schema object at all. One of the twelve pointed its
        # locator at the enclosing attribute -- an honest pointer, a verbatim
        # payload -- and this comparison called it drift that "makes the synthesised
        # interface describe a tool the target does not have". That accuses the
        # claims file of a defect it does not have, which is the "a 1 must name the
        # right artifact" rule read from the other side.
        #
        # Abstaining loses no real check for the reason above, and it is deliberately
        # narrower than the fix it stands in for: teaching resolve_pointer to decode a
        # string target and keep descending would make these payloads genuinely
        # checkable. That is a capability rather than a workaround -- MLflow traces
        # are a real input kind -- and docs/design/limitations.md carries the ruling
        # that parked it.
        return []
    if value != payload:
        return [
            Finding(
                claims_file,
                "refs",
                f"/claims/{claim_index}/payload",
                f"{claim_id}'s payload is not what {document_path.name} holds at {locator}; "
                "the tool's input schema has to be transcribed verbatim, and a payload that "
                "has drifted from it makes the synthesised interface describe a tool the "
                "target does not have",
            )
        ]
    return []


def _duplicate_service_ids(part: dict) -> set[str]:
    """Every `services[].id` the part declares more than once.

    One home, two readers: check_services reports it, and check_interfaces stays
    silent about the documents such a pair collapses onto. Two computations of the
    same set would be two answers free to drift, and the second reader's silence is
    only correct while it is silent about exactly the ids the first reports.

    Non-string ids are dropped rather than counted: an unhashable one would raise
    out of the set, and layer 1 owns the shape.
    """
    ids = [
        service.get("id") for service in _as_list(part.get("services")) if isinstance(service, dict)
    ]
    declared = [service_id for service_id in ids if isinstance(service_id, str)]
    return {service_id for service_id in declared if declared.count(service_id) > 1}


def check_services(run: RunPaths) -> list[Finding]:
    """The tool grouping in 01-services.json, against the claims it cites.

    Five clauses, reported in the order below so a repair reads resolution before
    the grouping the resolution feeds: every id in a tool's `claims` resolves to a
    `tool` claim, every `schema_claim` is one of its own tool's ids, no two
    services share a tool claim and no two share an id, every tool name survives
    the harness's sanitisation unchanged, and every `schema_claim`'s payload equals
    the input region its evidence names.

    A tool claim in two services is two simulators serving one tool name, which is
    one database the agent under test sees two conflicting views of. Two services
    with one id is the same hazard arriving by a different route, and it is worth
    its own clause because of where the alternative surfaces: `interfaces.synthesise`
    accepts the part and writes one document, last grouping wins, and
    check_interfaces then reports both directions of the difference against
    `01-interfaces/<id>.json` -- a 1 naming a derived file that is byte-for-byte
    what synthesis wrote, for a defect living in the part, unclearable by
    re-dispatching either stage. Nothing else reports it: services-part-0.1.json
    carries no uniqueness constraint and synthesis has no opinion.

    The orphan side of the partition is deliberately absent; see the comment on
    the clause itself.

    Silent on an absent or non-dict part, and silent on the whole run when any
    claims file is unreadable: see the guards inline. Nothing here reports a
    defect in an *input* to itself -- check_readable, check_manifest and
    check_inputs each own one of those, and check-refs over an unreadable
    01-claims/ once produced four fabricated `no such claim` findings against a
    correct world model.
    """
    part = _load(run.services_part)
    if not isinstance(part, dict):
        # Absent is the ordinary state before reconcile-services. isinstance
        # rather than `is None` for the reason check_input_dispositions guards the
        # same read that way: `null` and a list are legitimate JSON that reach
        # `.get` and raise AttributeError out of layer 2.
        return []

    # Every claims file has to be whole before one id is resolved. A file that is
    # unreadable, not an object, or an object with no `claims` array leaves the
    # index short of the claims it should have held, so each "no such claim" below
    # would be a guess against a part that may be perfectly correct -- the
    # fabricated-finding class this module has paid for once. This says nothing at
    # all instead: check_readable names the first shape and layer 1 the other two,
    # `claims` being required in claims-0.1.json. The third is worth its own
    # clause because it is neither of the first two and measurably reachable --
    # `{"schema_version": "0.1"}` in place of a claims file made this checker
    # report `no claim in 01-claims/ has id clm-api-010` against a correct
    # services part, and takes _claim_index down a KeyError.
    #
    # An empty or absent 01-claims/ takes the same branch: a services part with
    # nothing to resolve against means extract has not run, which is
    # validate_stage's finding.
    #
    # Two reads of each claims file, deliberately. _claims_by_artifact already
    # carries the member guards this checker needs and skips a broken file
    # silently, so the alternative is a third walker of 01-claims/ restating those
    # guards -- and check_inputs re-hashing every registered input on every call
    # is the cost precedent for a re-read here.
    claim_files = list_json(run.claims_dir)
    if not claim_files or any(
        not isinstance(document, dict) or not isinstance(document.get("claims"), list)
        for document in (_load(path) for path in claim_files)
    ):
        return []

    # Claim id -> the record, the file it came from, and its index in that file.
    # From _claims_by_artifact rather than _claim_index: that index carries only
    # defining *paths*, which is neither the `kind` clause 1 needs nor the
    # `payload` clause 5 does, and it reaches `payload["claims"]` and `claim["id"]`
    # unguarded besides -- so a claims file that is a dict with no `claims` key
    # raises KeyError out of it, a third shape check_readable cannot see.
    claims: dict[str, dict] = {}
    defined_in: dict[str, tuple[Path | None, int]] = {}
    for artifact_id, records in _claims_by_artifact(run).items():
        # A declared artifact_id that is not a safe segment cannot be turned into
        # a path to name in a finding, and the disagreement between the declared
        # id and the filename is check_manifest's. The claims stay in the index
        # either way: dropping them would make every service citing one look as
        # though it cited nothing, which is the fabricated-finding class again.
        # Two files declaring one artifact_id is check_manifest's finding too, and
        # is the one case where the index below is that of the merged list rather
        # than of the file.
        path = run.claims(artifact_id) if is_safe_segment(artifact_id) else None
        for index, claim in enumerate(records):
            claim_id = _str_or_none(claim.get("id"))
            if claim_id is None or claim_id in claims:
                # A duplicate id is check_manifest's finding, and it reports every
                # definition; keeping the first is enough to resolve against here
                # and adds no second report of the same defect.
                continue
            claims[claim_id] = claim
            defined_in[claim_id] = (path, index)

    out: list[Finding] = []

    def report(pointer: str, message: str) -> None:
        out.append(Finding(run.services_part, "refs", pointer, message))

    # Clauses 3, 4 and 5 are collected during the one walk and emitted after it,
    # so each arrives as a group rather than interleaved per tool. Clauses 1 and 2
    # emit inline, because a tool's own resolution findings belong beside each
    # other -- so the order is *by clause from 3 onwards*, and across tools a tool
    # B clause-1 finding can still follow a tool A clause-2 one. What the grouping
    # buys is that a repair reads every unresolvable id before the grouping and
    # payload consequences of those ids.
    references: dict[str, list[str]] = {}
    names: list[tuple[str, Any]] = []
    schema_claims: list[str] = []

    for i, service in enumerate(_as_list(part.get("services"))):
        if not isinstance(service, dict):
            # Layer 1 rejects it and interfaces.synthesise refuses it by name;
            # a third report would name a third pointer for one defect.
            continue
        service_id = _str_or_none(service.get("id"))
        # The label a partition finding names. A service with no usable id is
        # synthesise's finding, so this falls back to the pointer rather than
        # reporting the id again.
        label = service_id if service_id is not None else f"/services/{i}"
        cited_here: set[str] = set()
        for j, tool in enumerate(_as_list(service.get("tools"))):
            if not isinstance(tool, dict):
                continue
            pointer = f"/services/{i}/tools/{j}"
            declared = _as_list(tool.get("claims"))
            own_ids = {c for c in declared if isinstance(c, str)}
            for k, claim_id in enumerate(declared):
                if not isinstance(claim_id, str):
                    # Layer 1 owns a non-string id, and a set built from unguarded
                    # members raises TypeError: unhashable type instead.
                    continue
                cited_here.add(claim_id)
                claim = claims.get(claim_id)
                if claim is None:
                    report(
                        f"{pointer}/claims/{k}",
                        f"no claim in 01-claims/ has id {claim_id}, so this tool cites nothing "
                        "a simulator could be built from",
                    )
                elif claim.get("kind") != "tool":
                    report(
                        f"{pointer}/claims/{k}",
                        f"{claim_id} is a {claim.get('kind')!r} claim, not a tool claim: it "
                        "records no tool contract for this service to preserve",
                    )
            schema_claim = tool.get("schema_claim")
            if isinstance(schema_claim, str):
                if schema_claim not in own_ids:
                    report(
                        f"{pointer}/schema_claim",
                        f"{schema_claim} is not among this tool's own claims, so the request "
                        "body it names has no recorded evidence of belonging to this tool",
                    )
                schema_claims.append(schema_claim)
            names.append((f"{pointer}/name", tool.get("name")))
        for claim_id in sorted(cited_here):
            # Once per service, not once per citation: two tools of one service
            # sharing a schema claim are one simulator with one database, which is
            # not the hazard the duplicate clause reports.
            references.setdefault(claim_id, []).append(label)

    for service_id in sorted(_duplicate_service_ids(part)):
        # Named here and *only* here: run.interface() derives one path from the id,
        # so two services with one id collapse onto one file, and the difference
        # would otherwise be reported against a derived document that faithfully
        # carries the last grouping -- a 1 naming a file with no defect in it.
        # check_interfaces skips these services for that reason, so this is the one
        # line a repair can act on.
        report(
            "/services",
            f"more than one service is named {service_id}: they share the one document "
            f"01-interfaces/{service_id}.json, so the groupings after the first are lost and "
            "the tools in them have no simulator",
        )

    # The duplicate side of the claim-level partition only. The orphan side -- a `tool` claim
    # no service references -- is deliberately NOT reported here, because
    # check_input_dispositions already enforces it by identity: PASS_OWN_KINDS
    # binds services_part to ("tool",), that checker recomputes `own_kind_total`
    # from 01-claims/ and `cited` from the part's own citations rather than
    # trusting either, and reports both disagreements plus
    # `cited + dropped != own_kind_total`. So on a run where it is clean, the
    # number of unreferenced tool claims per input already equals the declared
    # `dropped` -- and inputs-seen-0.1.json requires a `note` on any row with
    # `dropped >= 1`, which makes the reason a layer-1 property. A property a
    # deterministic gate already enforces belongs to that gate, not to a second
    # reading of it here against a different pointer; reporting it twice would
    # also make a documented drop permanently dirty, a 1 no re-dispatch can clear.
    #
    # The asymmetry is why the duplicate side stays. It has no counterpart in that
    # accounting at all: `cited` counts a claim referenced *at all*, so a claim in
    # two services counts once and the arithmetic still balances. And the two
    # counters coincide only because every citation in the services part sits
    # inside a service's tool -- a field carrying claim ids somewhere else in the
    # part would silently pull them apart, and that is the change that would owe
    # this clause's orphan half back.
    #
    # The residual case neither side covers: a tool claim in a claims file whose
    # `artifact_id` the manifest does not register has no accounting row to be
    # counted in. That is check_manifest's finding, plus the `no row for input`
    # clause beside the arithmetic.
    for claim_id, claim in sorted(claims.items()):
        if claim.get("kind") != "tool":
            continue
        where = references.get(claim_id, [])
        if len(set(where)) > 1:
            report(
                "/services",
                f"{claim_id} is referenced by more than one service ({', '.join(where)}): two "
                "simulators serving one tool name give the agent two conflicting views of one "
                "database",
            )

    for pointer, name in names:
        if not isinstance(name, str) or not TOOL_NAME.match(name):
            # Checked here as well as in interfaces.synthesise, and not
            # redundantly: a document hand-corrected at gate 1 reaches check-refs
            # without passing through synthesis again, so the property has to hold
            # at check time and not only at write time. TOOL_NAME is imported from
            # the module that owns it rather than restated -- a second copy of the
            # pattern is exactly the drift its one home exists to prevent, and it
            # is already one restatement away from the harness's own rule.
            report(
                pointer,
                f"tool name {name!r} would not survive the harness's sanitisation unchanged, "
                "so the agent would call a name the simulator does not serve",
            )

    stored = _stored_input_paths(run)
    # set, because `schema_claims` is appended per tool: two tools of one service
    # naming one drifted schema claim produced two byte-identical findings -- same
    # artifact, same pointer, same message -- which is two stdout lines for one
    # defect and one of them a repair cannot act on separately. sorted, so the
    # emission order is the claim id's rather than the walk's.
    for claim_id in sorted(set(schema_claims)):
        claim = claims.get(claim_id)
        if claim is None:
            # Already reported above, through the tool's own `claims` array.
            continue
        path, index = defined_in[claim_id]
        out.extend(_payload_findings(claim_id, claim, path, index, stored))
    return out


def _operation_ids(document: dict) -> set[str]:
    """Every `operationId` a document declares, across every path and method.

    A walk rather than the fixed `/paths/<tool>/post` this project's synthesis
    writes. The check below exists for a document a human corrected at gate 1, and
    reading only `post` would report an operation moved to another method as
    missing -- a finding naming a defect that is not the one there. A non-string
    operationId is skipped and then surfaces as a tool name with no operation,
    which names the same file either way.
    """
    found: set[str] = set()
    paths = document.get("paths")
    if not isinstance(paths, dict):
        return found
    for item in paths.values():
        if not isinstance(item, dict):
            continue
        for operation in item.values():
            if isinstance(operation, dict):
                name = _str_or_none(operation.get("operationId"))
                if name is not None:
                    found.add(name)
    return found


def check_interfaces(run: RunPaths) -> list[Finding]:
    """One synthesised document per service, each preserving its tool names.

    Three clauses: a service with no document, a document no service asked for,
    and a document whose set of `operationId`s differs from its service's set of
    tool names -- the difference named in both directions, because a rename is two
    defects and a human shown one half would rename the wrong side back.

    Silent about a service whose id another service also declares. Those collapse
    onto one document, so every clause here would report the collapse against a
    file that is byte-for-byte what synthesis wrote, for a defect living in the
    part -- and check_services names that defect once, where a repair can act on
    it. The path is still counted as expected, or the document they share would come
    back as one no service asked for.

    The third is the check the rest of the lab design rests on. `operationId` is
    what the harness turns back into an MCP tool name, so the substitution the
    whole measurement depends on is invisible to the agent's reasoning only if the
    name it calls is the name the simulator serves.

    Returns nothing until 01-interfaces/ exists, for the reason check_verdicts
    returns nothing until 05-verdicts/ does: before synthesis has run there is no
    document to be missing, and reporting one per service would make
    reconcile-services' own check-refs gate exit 1 on a correct run, spending the
    orchestrator's single repair attempt re-dispatching a pass whose output was
    never the problem. interfaces.synthesise mkdirs the directory even for a run
    whose target declares no tool, so its existence is what distinguishes
    "synthesis has not run" from "synthesis ran and wrote nothing". Once it
    exists every missing document is reported: synthesis is all-or-nothing, so
    there is no partially-written window to tolerate -- the guard is `is_dir()`,
    not a count.
    """
    if not run.interfaces_dir.is_dir():
        return []
    part = _load(run.services_part)
    if not isinstance(part, dict):
        # With no readable grouping there is no expectation to hold the directory
        # to; an absent part is validate_stage's finding and an unreadable one is
        # check_readable's.
        return []

    missing: list[Finding] = []
    mismatched: list[Finding] = []
    expected: set[Path] = set()
    duplicated = _duplicate_service_ids(part)
    for i, service in enumerate(_as_list(part.get("services"))):
        if not isinstance(service, dict):
            continue
        service_id = _str_or_none(service.get("id"))
        if service_id is None or not is_safe_segment(service_id):
            # An id that cannot be a filename is interfaces.synthesise's finding
            # against the part, and there is no path to expect for it.
            continue
        path = run.interface(service_id)
        expected.add(path)
        if service_id in duplicated:
            continue
        if not path.is_file():
            missing.append(
                Finding(
                    run.services_part,
                    "refs",
                    f"/services/{i}/id",
                    f"service {service_id} has no synthesised document at {path}: nothing "
                    "downstream can stand a simulator up for it",
                )
            )
            continue
        document = _load(path)
        if not isinstance(document, dict):
            # Present but unreadable, or parsing to something other than an
            # object. check_readable names the first and layer 1 the second;
            # reporting a *missing* document for it would send the repair at the
            # grouping instead of at the file that will not parse.
            continue
        declared = {
            name
            for name in (
                _str_or_none(tool.get("name"))
                for tool in _as_list(service.get("tools"))
                if isinstance(tool, dict)
            )
            if name is not None
        }
        served = _operation_ids(document)
        for name in sorted(declared - served):
            mismatched.append(
                Finding(
                    path,
                    "refs",
                    "/paths",
                    f"service {service_id} declares tool {name!r} and this document serves no "
                    "operation with that operationId, so the agent would call a name the "
                    "simulator does not answer",
                )
            )
        for name in sorted(served - declared):
            mismatched.append(
                Finding(
                    path,
                    "refs",
                    "/paths",
                    f"this document serves operationId {name!r}, which is not a tool of "
                    f"service {service_id}: the simulator would answer a name the agent under "
                    "test was never given",
                )
            )

    extra = [
        Finding(
            path,
            "refs",
            "",
            f"no service in 01-services.json is named {path.stem}, so this document describes "
            "a simulator nothing asked for; synthesis owns this directory and removes what a "
            "superseded grouping left behind",
        )
        for path in list_json(run.interfaces_dir)
        if path not in expected
    ]
    return missing + extra + mismatched


def check_claim_utilisation(run: RunPaths) -> list[Finding]:
    """An input whose claims the world model cites *none* of.

    The mirror of check_world_model's claim check, which reports a world model
    citing an id that does not exist; this reports a claims file no world model
    cites. Same pair, opposite directions -- the shape the parked-decisions record
    already has four rows of.

    Zero, not a percentage. Measured on run-20260812-130056: 130 of 287 claims
    were uncited and almost all of those drops were correct, so a threshold would
    have failed a run whose rb-reconcile was behaving. Zero is indefensible under
    every reading -- a human registered that input through intake, so either
    rb-extract produced nothing usable from it or the reconcile passes ignored a
    whole artifact.
    """
    out: list[Finding] = []
    for entry in claim_utilisation(run)["artifacts"]:
        # `entry["total"]` guards a claims file with zero claims -- exactly the first
        # of the two causes named above ("rb-extract produced nothing usable"), which
        # `rb-extract` is explicitly allowed to produce for an input with nothing to
        # extract. Exempting it is not a hole: the report above still shows the
        # artifact at 0/0, so a human at gate 1 still sees it, it just is not a finding.
        if entry["total"] and entry["cited"] == 0:
            out.append(
                Finding(
                    run.world_model,
                    "refs",
                    "/",
                    f"no world-model element cites any claim from "
                    f"{entry['artifact_id']} ({entry['total']} claims)",
                )
            )
    return out


# Exactly the two statuses scenarios-0.1.json's enum carries that OPEN_STATUSES
# does not, spelled out rather than derived as a complement: a status this module
# has never seen (a hand-edit, a schema that grew) must not be silently counted
# as discarded, which `not in OPEN_STATUSES` would do.
_DISCARDED_STATUSES = frozenset({"duplicate", "rejected"})


def _batch_plan_findings(
    path: Path,
    plan: dict,
    round_n: int,
    cells: set[tuple[str, str]] | None,
    goal_ids: set[str] | None,
) -> list[Finding]:
    """One round's batch plan, checked.

    Split out of check_batches so the per-round `report` closure does not capture
    a loop variable, and so every finding is anchored on this round's own file.
    """
    out: list[Finding] = []

    def report(pointer: str, message: str) -> None:
        out.append(Finding(path, "refs", pointer, message))

    declared_round = plan.get("round")
    if declared_round != round_n:
        report(
            "/round",
            f"declares round {declared_round!r} but is the plan for round {round_n}; the round "
            "in the filename is the one the parts beside it were dispatched for",
        )

    # Both factors of the projection, and both guarded against a bool: `True` is
    # an `int` in Python, so a bare isinstance would multiply by it and report a
    # projection of 0 as if the plan had declared one.
    per_scenario = plan.get("bytes_per_scenario")
    have_per_scenario = isinstance(per_scenario, int) and not isinstance(per_scenario, bool)
    cap = plan.get("cap_bytes")
    have_cap = isinstance(cap, int) and not isinstance(cap, bool)

    # ref -> every batch id that claimed it, one entry per occurrence. A list
    # rather than a set for the reason _claim_index keeps one: the same ref twice
    # in ONE batch costs a second dispatched write exactly as it does across two,
    # and a set would hide it.
    owners: dict[str, list[str]] = {}
    batch_ids: list[str] = []
    for i, batch in enumerate(_as_list(plan.get("batches"))):
        if not isinstance(batch, dict):
            continue
        bid = _str_or_none(batch.get("id"))
        if bid is not None:
            batch_ids.append(bid)
        # A batch with no usable id is still checked for its own arithmetic --
        # the missing id is layer 1's finding -- so the message falls back to the
        # pointer rather than printing `None` as if that were the batch's name.
        label = f"batch {bid}" if bid is not None else f"the batch at /batches/{i}"
        refs = _as_list(batch.get("hole_refs"))
        projected = batch.get("projected_bytes")
        if have_per_scenario:
            expected = len(refs) * per_scenario
            if projected != expected:
                report(
                    f"/batches/{i}/projected_bytes",
                    f"{label} declares projected_bytes={projected!r} but {len(refs)} hole_refs "
                    f"at bytes_per_scenario={per_scenario} is {expected}",
                )
        if (
            have_cap
            and isinstance(projected, int)
            and not isinstance(projected, bool)
            and projected > cap
        ):
            # Anchored on hole_refs, not on projected_bytes, and the split is the
            # repair: a batch over budget holds too many holes, where a drifted
            # projection holds the wrong number. Two findings sharing one pointer
            # would leave a test unable to tell which one fired.
            report(
                f"/batches/{i}/hole_refs",
                f"{label} projects {projected} bytes, over the cap_bytes={cap} budget it was "
                "packed against, so one member's output would not fit the harness",
            )
        for j, ref in enumerate(refs):
            pointer = f"/batches/{i}/hole_refs/{j}"
            if not isinstance(ref, str):
                report(pointer, f"hole reference is not a string: {ref!r}")
                continue
            if bid is not None:
                owners.setdefault(ref, []).append(bid)
            try:
                kind, parts = parse_hole_ref(ref)
            except ValueError as exc:
                report(pointer, str(exc))
                continue
            # Resolved only when a world model was readable. An absent one is not
            # this checker's finding -- validate_stage owns that -- and an
            # unreadable one is check_readable's, which check_all short-circuits
            # on before reaching here.
            if kind == "cell" and cells is not None and parts not in cells:
                report(pointer, f"hole reference names no real cell: {ref}")
            if kind == "goal" and goal_ids is not None and parts[0] not in goal_ids:
                report(pointer, f"hole reference names no real goal: {ref}")

    for dupe in _dupes(batch_ids):
        report(
            "/batches",
            f"duplicate batch id {dupe!r}; a batch id is a part filename "
            "(02-scenarios/round-N/<id>.json), so two batches sharing one share a part",
        )

    for ref in sorted(owners):
        holders = owners[ref]
        distinct = sorted(set(holders))
        if len(distinct) > 1:
            report(
                "/batches",
                f"hole ref {ref!r} is assigned to {_and_join(distinct)}; this is a partition, "
                "not a covering, so two members proposing against one hole is a guaranteed "
                "duplicate that score then has to fold",
            )
        elif len(holders) > 1:
            report(
                "/batches",
                f"hole ref {ref!r} appears {len(holders)} times in batch {distinct[0]}, so that "
                "batch spends two of its own slots on one hole",
            )
    return out


def check_batches(run: RunPaths) -> list[Finding]:
    """Every round's batch plan: its arithmetic, its budget, and its hole refs.

    Walks `run.batches_rounds()` rather than one file, and anchors every finding
    on the round's own `02-batches/round-N.json`, so a defect in round 2's
    partition never names round 1's plan.

    An absent 02-batches/ is not a finding: a run that has not reached propose has
    no plan to check, and reporting one there would spend the orchestrator's
    single repair attempt on a phantom. An *unreadable* plan is a finding naming
    that plan, never a silent skip -- a checker that returns nothing because it
    could not read its input is the `01-claims/` incident in the module docstring
    wearing a checker's clothes.

    Nothing here is semantic. Whether the partition is a *good* one -- whether
    these holes belong together in one dispatch -- is not a question layer 2 can
    ask; whether each ref resolves and each projection recomputes is.
    """
    rounds = run.batches_rounds()
    if not rounds:
        return []
    world = _load(run.world_model)
    cells = _cells(world) if isinstance(world, dict) else None
    goal_ids = (
        {g["id"] for g in _as_list(world.get("goals")) if isinstance(g, dict) and "id" in g}
        if isinstance(world, dict)
        else None
    )
    out: list[Finding] = []
    for round_n in rounds:
        path = run.batches(round_n)
        try:
            plan = read_json(path)
        except ArtifactError as exc:
            out.append(Finding(path, "refs", "", str(exc)))
            continue
        if not isinstance(plan, dict):
            out.append(Finding(path, "refs", "", "batch plan is not a JSON object"))
            continue
        out.extend(_batch_plan_findings(path, plan, round_n, cells, goal_ids))
    return out


def _scenario_part_findings(
    path: Path, batch_id: str, round_n: int, owners: dict[str, str]
) -> list[Finding]:
    """One propose part, checked against the batch it was dispatched with.

    Split out of check_scenario_parts for the reason _batch_plan_findings is: the
    `report` closure must not capture a loop variable, and every finding here
    belongs on this part rather than on 02-scenarios.json, which no member wrote.
    """
    try:
        part = read_json(path)
    except ArtifactError as exc:
        return [Finding(path, "refs", "", str(exc))]
    if not isinstance(part, dict):
        return [Finding(path, "refs", "", "propose part is not a JSON object")]
    out: list[Finding] = []

    def report(pointer: str, message: str) -> None:
        out.append(Finding(path, "refs", pointer, message))

    # The field against the filename, for the reason check_contradiction_parts
    # compares subject_id against its own stem: the filename is the batch the
    # member was dispatched with, the field is the batch it believed it was
    # working on, and a mismatch means one member wrote a sibling's slice. No
    # schema can see it, because both documents are individually valid.
    field = _str_or_none(part.get("batch_id"))
    if field is not None and field != batch_id:
        report("/batch_id", f"declares batch_id {field!r} but is the part for {batch_id!r}")
    declared_round = part.get("round")
    if declared_round != round_n:
        report(
            "/round",
            f"declares round {declared_round!r} but sits in round {round_n}'s part directory",
        )

    for i, scenario in enumerate(_as_list(part.get("scenarios"))):
        if not isinstance(scenario, dict):
            continue
        sid = _str_or_none(scenario.get("id"))
        named = sid if sid is not None else f"the scenario at /scenarios/{i}"
        # `provenance.hole_refs` and nothing else, because that is where the member
        # DECLARES which holes it wrote this scenario to close (rb-propose Method
        # step 9), and scenarios-0.1.json requires it with minItems 1. It is the
        # faithful analogue of the triage precedent: a dispositions part names a
        # `candidate_id` and the seal refuses one outside the slice it rules on,
        # because the candidate IS that fan-out's work unit. Here the work unit is
        # a hole.
        #
        # `goal_id` and `capability_refs` are the ids a scenario NAMES, which is a
        # different thing from the holes it TARGETS, and resolving them here was
        # measured unsatisfiable rather than merely wrong (Ruling R21). A scenario
        # closing one cell still has to carry a `goal_id` -- required, drawn from
        # the world model's frozen list -- and that goal is not a hole assignment
        # at all. `partition` chunks a sorted ref list and `cell:` sorts before
        # `goal:`, so a cell-only batch is the normal shape: on a real
        # write_batches partition of 20 cells and 2 goals (first batch = 17 cells,
        # second = 3 cells + 2 goals), resolving those two fields reported 19 of 22
        # CORRECT scenarios -- the first batch's 17 cell scenarios for naming the
        # goal the second owns, and the second's 2 goal scenarios for naming the
        # cell the first owns. Positionally rather than by id because the ids that
        # run actually carried were b01/b02, before the round term was added to
        # them; restating them in today's spelling would attribute the measurement
        # to a partition nobody ran. The same parts
        # against `provenance.hole_refs` report none.
        #
        # This stays a reference check, in layer 2's remit: does this ref name a
        # hole this batch was given. Whether the scenario actually CLOSES it is
        # semantic and nothing here judges it.
        provenance = scenario.get("provenance")
        declared = _as_list(provenance.get("hole_refs")) if isinstance(provenance, dict) else []
        for j, ref in enumerate(declared):
            pointer = f"/scenarios/{i}/provenance/hole_refs/{j}"
            if not isinstance(ref, str):
                report(pointer, f"hole reference is not a string: {ref!r}")
                continue
            owner = owners.get(ref)
            if owner is None:
                # A different defect from naming the wrong batch, and it needs its
                # own message: no member at all was dispatched to close this hole,
                # so the scenario is either closing something the round did not
                # consider closable or naming a hole that does not exist.
                report(
                    pointer,
                    f"scenario {named} targets {ref}, which round {round_n} assigns to no batch "
                    f"at all, so no member -- {batch_id} included -- was dispatched to close it",
                )
            elif owner != batch_id:
                report(
                    pointer,
                    f"scenario {named} targets {ref}, which round {round_n} assigns to batch "
                    f"{owner}, not to {batch_id} that wrote this part; a member that wandered "
                    "into a sibling's holes writes a part byte-identical to one that did not, "
                    "so this is the only layer that can see it",
                )
    return out


def _scenario_round_findings(run: RunPaths, round_n: int) -> list[Finding]:
    """One round's part directory against that round's own batch plan."""
    out: list[Finding] = []
    round_dir = run.scenario_round_dir(round_n)
    # An unsafe stem cannot be a batch id, so it is not in scenario_part_batch_ids
    # and scenario_part() cannot be asked for it. Reported as an ordinary finding
    # for the reason check_contradiction_parts gives: an UnsafeSegment reaching
    # cli.py would become exit 2 and take every other finding in the run with it.
    for name in run.unsafe_scenario_part_names(round_n):
        out.append(
            Finding(
                round_dir,
                "refs",
                "",
                f"propose part {name!r} is not a usable batch id: a batch id must start with a "
                "letter or digit and contain only letters, digits, dots, dashes, and underscores",
            )
        )
    plan_path = run.batches(round_n)
    try:
        plan = read_json(plan_path)
    except ArtifactError as exc:
        out.append(
            Finding(
                plan_path,
                "refs",
                "",
                f"{exc}; round {round_n} has propose parts, so the plan they were dispatched "
                "from must be beside them -- without it no part can be checked against the "
                "batch that owns its holes",
            )
        )
        return out
    if not isinstance(plan, dict):
        out.append(Finding(plan_path, "refs", "", "batch plan is not a JSON object"))
        return out

    roster: set[str] = set()
    # First declarer wins: a ref in two batches is check_batches' finding, and
    # restating it here as an own-batch violation would report one plan defect
    # twice and send the repair at a part instead of at the partition.
    owners: dict[str, str] = {}
    for batch in _as_list(plan.get("batches")):
        if not isinstance(batch, dict):
            continue
        bid = _str_or_none(batch.get("id"))
        if bid is None:
            continue
        roster.add(bid)
        for ref in _as_list(batch.get("hole_refs")):
            if isinstance(ref, str):
                owners.setdefault(ref, bid)

    on_disk = set(run.scenario_part_batch_ids(round_n))
    for bid in sorted(roster - on_disk):
        out.append(
            Finding(
                round_dir,
                "refs",
                "",
                f"batch {bid} of round {round_n} has no propose part on disk; every batch needs "
                "one, even one recording that its member could close nothing",
            )
        )
    for bid in sorted(on_disk - roster):
        out.append(
            Finding(
                run.scenario_part(round_n, bid),
                "refs",
                "",
                f"propose part for batch {bid}, which round {round_n}'s batch plan does not "
                "declare",
            )
        )
    for bid in sorted(on_disk):
        out.extend(_scenario_part_findings(run.scenario_part(round_n, bid), bid, round_n, owners))
    return out


def check_scenario_parts(run: RunPaths) -> list[Finding]:
    """One propose part per batch, and every scenario inside its own batch.

    **Meaningful only once every fan-out member has finished.** Every batch
    without a part is reported from the moment 02-scenarios/round-N/ exists, so
    mid-fan-out most of them are missing by construction -- exactly the caveat
    check_verdicts and check_contradiction_parts carry, and for the same reason.
    There is no stage-scoped check-refs: check_all runs every checker the run has
    inputs for.

    Each round's roster comes from that round's own `run.batches(round_n)`, never
    from one shared plan: a singleton overwritten by round 2 would have round 1's
    parts checked against round 2's assignment, reporting a missing batch for
    every correct part after the first and naming the wrong artifact while doing
    it.

    The own-batch clause is the one check here that overlaps no other layer. A
    member that proposed against a sibling's hole produces a part that satisfies
    scenarios-part-0.1.json, hashes like any other, and reads as ordinary output;
    only the plan beside it says whose hole that was. It mirrors
    check_disposition_parts' clause 2, "a disposition naming a candidate outside
    the slice its own part rules on", and it mirrors it in the field it reads as
    well as in the shape: that clause resolves the `candidate_id` a disposition
    names because the candidate is the triage fan-out's work unit, and this one
    resolves `provenance.hole_refs` because a hole is the propose fan-out's.
    """
    rounds = run.scenario_part_rounds()
    if not rounds:
        return []
    out: list[Finding] = []
    for round_n in rounds:
        out.extend(_scenario_round_findings(run, round_n))
    return out


def _score_part_findings(
    path: Path, round_n: int, status_of: dict[str, Any] | None
) -> list[Finding]:
    """One score part's rulings against the sealed scenario list."""
    try:
        part = read_json(path)
    except ArtifactError as exc:
        return [Finding(path, "refs", "", str(exc))]
    if not isinstance(part, dict):
        return [Finding(path, "refs", "", "score part is not a JSON object")]
    out: list[Finding] = []

    def report(pointer: str, message: str) -> None:
        out.append(Finding(path, "refs", pointer, message))

    declared_round = part.get("round")
    if declared_round != round_n:
        report("/round", f"declares round {declared_round!r} but is the part for round {round_n}")
    for i, ruling in enumerate(_as_list(part.get("rulings"))):
        if not isinstance(ruling, dict):
            continue
        sid = _str_or_none(ruling.get("scenario_id"))
        if sid is None:
            continue
        if status_of is not None and sid not in status_of:
            report(
                f"/rulings/{i}/scenario_id",
                f"rules on {sid}, which 02-scenarios.json does not carry",
            )
        target = _str_or_none(ruling.get("duplicate_of"))
        if target is None:
            continue
        if target == sid:
            # Reported and then skipped: once a ruling folds a scenario onto
            # itself, its target's status says nothing further, and a second
            # finding on the same pointer would leave a test unable to tell which
            # clause fired.
            report(
                f"/rulings/{i}/duplicate_of",
                f"folds {sid} onto itself, so nothing survives the fold",
            )
            continue
        if status_of is None:
            continue
        if target not in status_of:
            report(
                f"/rulings/{i}/duplicate_of",
                f"folds {sid} onto {target}, which 02-scenarios.json does not carry",
            )
        elif status_of.get(target) in _DISCARDED_STATUSES:
            report(
                f"/rulings/{i}/duplicate_of",
                f"folds {sid} onto {target}, which is itself {status_of[target]} in the sealed "
                "document, so neither ships and every cell the two claimed is a hole again",
            )
    return out


def check_score_parts(run: RunPaths) -> list[Finding]:
    """Every round's score rulings against the sealed scenario list.

    Reads the *sealed* 02-scenarios.json rather than the propose parts, because
    that is the document a ruling has to resolve against and the one score-seal
    folds it into. A fold chain -- a ruling folding A onto B while B is itself
    `duplicate` or `rejected` -- leaves no shipped test for either scenario's
    cells, and nothing else reports it: check_scenarios asks only whether
    `duplicate_of` resolves, never what the target's own status is.

    A finding names the part, not 02-scenarios.json, because the part is what a
    re-dispatch of that round's rb-score can actually repair -- the sealed
    document is code output.

    Statuses are read as of the seal, which is what makes the fold-chain clause
    honest across rounds: a later round may overturn an earlier ruling
    (rb-score's Output sanctions exactly that), and if it rejects the scenario an
    earlier fold pointed at, the earlier fold is *now* a chain with no shipped
    test at its end. Reporting it is the point, not a false positive.

    Reports nothing until 03-score/ holds a round part, and reads the sealed
    document only if it is there: a score part is written after the propose seal,
    so an absent 02-scenarios.json means the run is in a state no ruling can be
    resolved against, which is validate_stage's finding rather than this one's.
    """
    rounds = run.score_part_rounds()
    if not rounds:
        return []
    sealed = _load(run.scenarios)
    status_of: dict[str, Any] | None = None
    if isinstance(sealed, dict):
        status_of = {
            s["id"]: s.get("status")
            for s in _as_list(sealed.get("scenarios"))
            if isinstance(s, dict) and isinstance(s.get("id"), str)
        }
    out: list[Finding] = []
    for round_n in rounds:
        out.extend(_score_part_findings(run.score_part(round_n), round_n, status_of))
    return out


def check_scenarios(run: RunPaths) -> list[Finding]:
    """Scenario references into the world model, and internal consistency."""
    scenarios_doc = _load(run.scenarios)
    world = _load(run.world_model)
    if scenarios_doc is None or world is None:
        return []
    out: list[Finding] = []
    path = run.scenarios

    def report(pointer: str, message: str) -> None:
        out.append(Finding(path, "refs", pointer, message))

    cells = _cells(world)
    capability_ids = {cap["id"] for cap in world.get("capabilities", [])}
    goal_ids = {g["id"] for g in world.get("goals", [])}
    actor_ids = {a["id"] for a in world.get("actors", [])}
    scenarios = scenarios_doc.get("scenarios", [])
    scenario_ids = {s["id"] for s in scenarios}

    declared_version = scenarios_doc.get("denominator_version")
    world_version = world.get("denominator", {}).get("version")
    if declared_version != world_version:
        report(
            "/denominator_version",
            f"scenarios were proposed against denominator_version={declared_version} but the "
            f"world model is at {world_version}",
        )

    for dupe in _dupes([s["id"] for s in scenarios]):
        report("/scenarios", f"duplicate scenario id {dupe!r}")

    for i, scenario in enumerate(scenarios):
        if scenario["goal_id"] not in goal_ids:
            report(f"/scenarios/{i}/goal_id", f"no such goal: {scenario['goal_id']}")
        if scenario["actor_id"] not in actor_ids:
            report(f"/scenarios/{i}/actor_id", f"no such actor: {scenario['actor_id']}")
        target = scenario.get("duplicate_of")
        if target is not None and target not in scenario_ids:
            report(f"/scenarios/{i}/duplicate_of", f"no such scenario: {target}")
        for j, ref in enumerate(scenario.get("capability_refs", [])):
            pair = (ref["capability_id"], ref["outcome_class_id"])
            if ref["capability_id"] not in capability_ids:
                report(
                    f"/scenarios/{i}/capability_refs/{j}/capability_id",
                    f"no such capability: {ref['capability_id']}",
                )
            elif pair not in cells:
                report(
                    f"/scenarios/{i}/capability_refs/{j}/outcome_class_id",
                    f"capability {ref['capability_id']} has no outcome class "
                    f"{ref['outcome_class_id']}",
                )
        for j, ref in enumerate(scenario.get("provenance", {}).get("hole_refs", [])):
            pointer = f"/scenarios/{i}/provenance/hole_refs/{j}"
            try:
                kind, parts = parse_hole_ref(ref)
            except ValueError as exc:
                report(pointer, str(exc))
                continue
            if kind == "cell" and parts not in cells:
                report(pointer, f"hole reference names no real cell: {ref}")
            if kind == "goal" and parts[0] not in goal_ids:
                report(pointer, f"hole reference names no real goal: {ref}")
    return out


def _check_matrix_arithmetic(
    report, pointer: str, covered_flags: list[bool], declared: dict
) -> None:
    """Covered/total/pct must agree with the rows they summarize.

    `pct` is converted rather than compared directly, because a schema-valid
    `number` can arrive as an int. The conversion is guarded: `float("half")`
    raises ValueError, and a coverage document carrying a non-numeric pct is a
    repairable score-stage defect, so it has to become an ordinary finding. Left
    unguarded it escaped to cli.py and was reported as exit 2 -- a misconfigured
    harness -- which is the one thing the exit-code contract forbids.
    """
    total = len(covered_flags)
    covered = sum(1 for flag in covered_flags if flag)
    if declared.get("total") != total:
        report(f"{pointer}/total", f"declared total={declared.get('total')} but found {total}")
    if declared.get("covered") != covered:
        report(
            f"{pointer}/covered",
            f"declared covered={declared.get('covered')} but {covered} rows are marked covered",
        )
    expected_pct = (covered / total) if total else 0.0
    declared_pct = declared.get("pct", -1)
    if isinstance(declared_pct, bool) or not isinstance(declared_pct, (int, float)):
        report(
            f"{pointer}/pct",
            f"declared pct={declared_pct!r} is not a number, so it cannot be checked against "
            f"covered/total, which is {expected_pct}",
        )
        return
    if abs(float(declared_pct) - expected_pct) > 1e-9:
        report(
            f"{pointer}/pct",
            f"declared pct={declared.get('pct')} but covered/total is {expected_pct}",
        )


def check_coverage(run: RunPaths) -> list[Finding]:
    """Coverage matrices against the world model and the scenario list."""
    coverage = _load(run.coverage_latest)
    world = _load(run.world_model)
    if coverage is None or world is None:
        return []
    out: list[Finding] = []
    path = run.coverage_latest

    def report(pointer: str, message: str) -> None:
        out.append(Finding(path, "refs", pointer, message))

    cells = _cells(world)
    goal_ids = {g["id"] for g in world.get("goals", [])}
    gap_ids = {g["id"] for g in world.get("gaps", [])}
    scenarios_doc = _load(run.scenarios) or {"scenarios": []}
    scenario_ids = {s["id"] for s in scenarios_doc.get("scenarios", [])}
    live_ids = {s["id"] for s in scenarios_doc.get("scenarios", []) if s["status"] in OPEN_STATUSES}

    def check_live_credit(pointer: str, label: str, ids: list[str]) -> None:
        """A row marked covered must be credited to a scenario that still counts.

        `covered` means an accepted scenario exercises the row. When challenge
        rejects that scenario, the reject path is "mark rejected in
        02, recompute coverage" -- because the cell is a hole again. Nothing
        enforced the recomputation: this function checked only that a cited
        scenario_id *existed*, so the post-rejection state with the recomputation
        skipped left both check-refs and `validate --stage score` green while
        latest.json still reported the cell covered by the scenario the adversary
        threw out as ambiguous. Coverage confidently wrong with no finding is the
        defect class this module exists to catch.

        `duplicate` counts as dead alongside `rejected`, which is why this reuses
        OPEN_STATUSES rather than naming one status: a folded scenario is never
        instantiated and never emitted (see JUDGED_STATUSES) and does not count
        against max_scenarios either, so no test ships for the row it claimed and
        the credit belongs to the scenario it was folded into. Both cases are
        repaired the same way, by recomputing.

        A row credited to a mix of live and dead scenarios stays covered: a live
        scenario still exercises it. Only a row whose every credit is dead has
        lost its coverage.
        """
        if ids and not (set(ids) & live_ids):
            report(
                pointer,
                f"{label} is marked covered but every scenario crediting it "
                f"({', '.join(sorted(ids))}) is rejected or a duplicate, so no accepted scenario "
                "exercises it; a rejection reopens the row, so the score stage must recompute "
                "coverage and justify the row as a hole",
            )

    world_version = world.get("denominator", {}).get("version")
    if coverage.get("denominator_version") != world_version:
        report(
            "/denominator_version",
            f"coverage was computed against denominator_version="
            f"{coverage.get('denominator_version')} but the world model is at {world_version}",
        )

    matrix = coverage.get("capability_matrix", {})
    matrix_cells = matrix.get("cells", [])
    seen = {(c["capability_id"], c["outcome_class_id"]) for c in matrix_cells}
    # drivable_cells here and `cells` (wide) for the hole refs below, which is the
    # whole point of the split. The matrix is the SCORED surface, so it enumerates
    # what a scenario could be driven on; a hole is an ACCOUNT of a cell, so its
    # ref only has to resolve. Compared against the wide set, a correctly narrowed
    # matrix reported one 'matrix omits cell' per undrivable cell -- 37 of them on
    # run-20260827-070444, every one of them fabricated.
    drivable = drivable_cells(world)
    for missing in sorted(drivable - seen):
        report("/capability_matrix/cells", f"matrix omits cell {cell_ref(*missing)}")
    # `seen - drivable` rather than `seen - cells`: a matrix row on an undrivable
    # cell is now also wrong, because that cell belongs in the holes instead. This
    # tightens the invented-cell direction rather than loosening it.
    #
    # Two messages, not one, because they are two different defects and only one
    # of them is an invention. A declared-but-undrivable cell is one the human at
    # gate 2 will find sitting in 01-world-model.json, so telling them the matrix
    # "invents" it reads as the checker being wrong rather than the document --
    # 37 rows' worth on run-20260827-070444 before the matrix itself narrowed.
    # `cells` is the wide set, so membership in it is exactly the partition:
    # inside, the world model declares the cell and the matrix scored a row it
    # should have left to the holes; outside, no capability declares the pair.
    for extra in sorted(seen - drivable):
        if extra in cells:
            report(
                "/capability_matrix/cells",
                f"matrix scores undrivable cell {cell_ref(*extra)}; it belongs in the holes",
            )
        else:
            report("/capability_matrix/cells", f"matrix invents cell {cell_ref(*extra)}")
    for i, cell in enumerate(matrix_cells):
        for j, sid in enumerate(cell.get("scenario_ids", [])):
            if sid not in scenario_ids:
                report(f"/capability_matrix/cells/{i}/scenario_ids/{j}", f"no such scenario: {sid}")
        if cell.get("covered") and not cell.get("scenario_ids"):
            report(
                f"/capability_matrix/cells/{i}",
                f"cell {cell_ref(cell['capability_id'], cell['outcome_class_id'])} is marked "
                "covered but lists no scenarios",
            )
        elif cell.get("covered"):
            check_live_credit(
                f"/capability_matrix/cells/{i}",
                f"cell {cell_ref(cell['capability_id'], cell['outcome_class_id'])}",
                cell.get("scenario_ids", []),
            )
    _check_matrix_arithmetic(
        report, "/capability_matrix", [bool(c.get("covered")) for c in matrix_cells], matrix
    )

    goal_matrix = coverage.get("goal_matrix", {})
    rows = goal_matrix.get("rows", [])
    seen_goals = {r["goal_id"] for r in rows}
    for missing_goal in sorted(goal_ids - seen_goals):
        report("/goal_matrix/rows", f"matrix omits goal {missing_goal}")
    for invented_goal in sorted(seen_goals - goal_ids):
        report("/goal_matrix/rows", f"matrix invents goal {invented_goal}")

    goals_by_id = {g["id"]: g for g in world["goals"]}
    hop_by_scenario = {s["id"]: s["hop_depth"] for s in scenarios_doc["scenarios"]}
    for i, row in enumerate(rows):
        for j, sid in enumerate(row["scenario_ids"]):
            if sid not in scenario_ids:
                report(f"/goal_matrix/rows/{i}/scenario_ids/{j}", f"no such scenario: {sid}")
        goal = goals_by_id.get(row["goal_id"])
        expected_depths: set[int] = set()
        if goal is not None:
            expected_depths = set(goal["expected_hop_depths"])
            if set(row["hop_depths_expected"]) != expected_depths:
                report(
                    f"/goal_matrix/rows/{i}/hop_depths_expected",
                    f"row expects hop depths {sorted(row['hop_depths_expected'])} but the "
                    f"world model declares {sorted(expected_depths)} for {row['goal_id']}",
                )
        present = {
            hop_by_scenario[sid]
            for sid in row["scenario_ids"]
            if isinstance(hop_by_scenario.get(sid), int)
        }
        if set(row["hop_depths_present"]) != present:
            report(
                f"/goal_matrix/rows/{i}/hop_depths_present",
                f"row reports hop depths {sorted(row['hop_depths_present'])} but its "
                f"scenarios have {sorted(present)}",
            )
        # A goal row is covered iff it has a *live* scenario and every expected
        # hop depth is present. A goal exercised at one depth when two are
        # expected is a partial row, and calling it covered is how a goal
        # denominator reaches 100% without testing the hard half of the goal. The
        # live-credit half is checked on both matrices, because both feed
        # _check_matrix_arithmetic and the hole reconciliation below: a one-sided
        # check would leave the goal denominator confidently wrong in exactly the
        # state the capability denominator now reports.
        if not row["scenario_ids"]:
            if row["covered"]:
                report(
                    f"/goal_matrix/rows/{i}/covered",
                    f"goal {row['goal_id']} is marked covered but lists no scenarios",
                )
        elif bool(row["covered"]) != (expected_depths <= present):
            report(
                f"/goal_matrix/rows/{i}/covered",
                f"goal {row['goal_id']} is marked covered={row['covered']} but its scenarios "
                f"reach hop depths {sorted(present)} against an expected {sorted(expected_depths)}",
            )
        if row["covered"]:
            check_live_credit(
                f"/goal_matrix/rows/{i}", f"goal {row['goal_id']}", row["scenario_ids"]
            )
    _check_matrix_arithmetic(
        report, "/goal_matrix", [bool(r.get("covered")) for r in rows], goal_matrix
    )

    hole_refs: set[str] = set()
    for i, hole in enumerate(coverage.get("holes", [])):
        try:
            kind, parts = parse_hole_ref(hole["ref"])
        except ValueError as exc:
            report(f"/holes/{i}/ref", str(exc))
            continue
        if kind == "cell" and parts not in cells:
            report(f"/holes/{i}/ref", f"hole names no real cell: {hole['ref']}")
        if kind == "goal" and parts[0] not in goal_ids:
            report(f"/holes/{i}/ref", f"hole names no real goal: {hole['ref']}")
        hole_refs.add(hole["ref"])
        gap_id = hole.get("gap_id")
        if gap_id is not None and gap_id not in gap_ids:
            report(f"/holes/{i}/gap_id", f"no such gap: {gap_id}")

    # Every uncovered row must be justified, and no justified row may be
    # covered. Without both directions the hole vocabulary is decorative: a
    # report could show 60% and explain none of the missing 40%.
    uncovered = {
        cell_ref(c["capability_id"], c["outcome_class_id"])
        for c in matrix_cells
        if not c["covered"]
    } | {goal_ref(r["goal_id"]) for r in rows if not r["covered"]}
    covered = {
        cell_ref(c["capability_id"], c["outcome_class_id"]) for c in matrix_cells if c["covered"]
    } | {goal_ref(r["goal_id"]) for r in rows if r["covered"]}
    for ref in sorted(uncovered - hole_refs):
        report("/holes", f"{ref} is uncovered but no hole justifies it")
    for ref in sorted(hole_refs & covered):
        report("/holes", f"hole {ref} names a row the matrix marks covered")
    return out


class _Unset:
    def __repr__(self) -> str:
        return "<unset>"


UNSET = _Unset()

# Declared field type -> the predicate a seed value must satisfy. `integer`
# excludes bool deliberately: bool is an int subclass in Python, and a seed
# writing `true` where an id belongs is a real defect, not a wide integer.
_TYPE_CHECKS: dict[str, Any] = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


def resolve_pointer(document: Any, pointer: str) -> Any:
    """Resolve an RFC 6901 JSON Pointer, returning UNSET if it does not exist.

    Written here rather than pulled from a library because the whole surface
    is fifteen lines and the reachability gate depends on its exact
    does-not-resolve semantics.
    """
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError(f"not a JSON pointer: {pointer!r}")
    current = document
    for raw in pointer.split("/")[1:]:
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                return UNSET
            current = current[token]
        elif isinstance(current, list):
            if not token.isdigit() or int(token) >= len(current):
                return UNSET
            current = current[int(token)]
        else:
            return UNSET
    return current


def _is_empty(value: Any) -> bool:
    return value is UNSET or value is None or value in ("", [], {})


def _check_seed_conformance(report, world: dict, seed: dict) -> None:
    """Seed collections, fields, and types against the world model's entities."""
    entities = {e["collection"]: e for e in world.get("entities", [])}
    collections = seed.get("collections", {})
    for name in sorted(set(collections) - set(entities)):
        report(
            f"/collections/{name}",
            f"seed declares collection {name!r}, which no world-model entity declares",
        )
    for name, records in sorted(collections.items()):
        entity = entities.get(name)
        if entity is None:
            continue
        declared = {f["name"]: f["type"] for f in entity.get("fields", [])}
        for i, record in enumerate(records):
            pointer = f"/collections/{name}/{i}"
            for missing in sorted(set(declared) - set(record)):
                report(pointer, f"record is missing declared field {missing!r}")
            for extra in sorted(set(record) - set(declared)):
                report(
                    pointer,
                    f"record carries undeclared field {extra!r}; a simulation backend will "
                    "drop or recompute it, so a label relying on it would break at run time",
                )
            for field, type_name in sorted(declared.items()):
                if field not in record:
                    continue
                check = _TYPE_CHECKS.get(type_name)
                if check is not None and not check(record[field]):
                    report(
                        f"{pointer}/{field}",
                        f"field {field!r} is declared {type_name} but holds {record[field]!r}",
                    )


def _check_invariants(report_invariant, world: dict, seed: dict) -> None:
    collections = seed.get("collections", {})
    for entity in world.get("entities", []):
        for invariant in entity.get("invariants", []):
            machine = invariant.get("machine")
            if not machine:
                continue
            try:
                violations = evaluate_invariant(machine, collections)
            except InvariantForm as exc:
                report_invariant("", f"invariant {invariant['id']}: {exc}")
                continue
            for violation in violations:
                report_invariant("", f"invariant {invariant['id']}: {violation}")


def _check_reachability(
    report, world: dict, seed: dict, expected: dict, scenario_caps: set[str]
) -> None:
    """Every assertion is grounded in this scenario's own seed.

    Resolution happens against `seed` and nothing else, so an assertion can
    never reach another scenario's world.

    `scenario_caps` is the scenario's own declared capability_refs. A positive
    trajectory claim must stay inside it: coverage credits the scenario for the
    cells it declared, so an instance exercising a capability the scenario never
    claimed makes coverage confidently wrong. tool_not_called is exempt --
    forbidding a call to an unclaimed capability is exactly what the kind is for.
    """
    capability_ids = {cap["id"] for cap in world.get("capabilities", [])}
    for i, assertion in enumerate(expected["assertions"]):
        kind = assertion["kind"]
        pointer = f"/assertions/{i}"
        if kind in TRAJECTORY_KINDS:
            capability_id = assertion.get("capability_id")
            if capability_id not in capability_ids:
                report(f"{pointer}/capability_id", f"no such capability: {capability_id}")
            elif kind == "tool_called" and capability_id not in scenario_caps:
                report(
                    f"{pointer}/capability_id",
                    f"asserts a call to {capability_id}, which the scenario does not claim in "
                    "capability_refs; coverage would credit cells this test does not exercise",
                )
            continue
        if kind not in DATA_KINDS:
            continue
        seed_pointer = assertion["grounded_in"]["seed_pointer"]
        resolved = resolve_pointer(seed, seed_pointer)
        if kind == "answer_excludes":
            if not _is_empty(resolved):
                report(
                    f"{pointer}/grounded_in/seed_pointer",
                    f"answer_excludes is grounded at {seed_pointer}, which resolves to a value "
                    f"({resolved!r}); the seed does contain what the assertion claims it lacks",
                )
            continue
        if resolved is UNSET:
            report(
                f"{pointer}/grounded_in/seed_pointer",
                f"{seed_pointer} does not resolve in this scenario's seed",
            )
            continue
        rendered = str(resolved)
        value = assertion["value"]
        if kind == "answer_contains" and value not in rendered:
            report(
                f"{pointer}/value",
                f"asserted value {value!r} is not present at {seed_pointer} (found {resolved!r})",
            )
        if kind == "value_equals" and rendered != value:
            report(
                f"{pointer}/value",
                f"asserted value {value!r} does not equal the seed value {resolved!r} at "
                f"{seed_pointer}",
            )

    for i, operation in enumerate(expected["trajectory"]["operations"]):
        capability_id = operation["capability_id"]
        if capability_id not in capability_ids:
            report(
                f"/trajectory/operations/{i}/capability_id",
                f"no such capability: {capability_id}",
            )
        elif capability_id not in scenario_caps:
            report(
                f"/trajectory/operations/{i}/capability_id",
                f"the trajectory uses {capability_id}, which the scenario does not claim in "
                "capability_refs; coverage would credit cells this test does not exercise",
            )


def check_instances(run: RunPaths) -> list[Finding]:
    """Completeness, seed conformance, machine invariants, and the reachability gate.

    Completeness is checked in both directions. The loop below reports an
    instance directory whose scenario was never judged; the clause above it
    reports an `active` scenario with no instance directory, which until issue
    #19 nothing reported at all -- and the silence compounded, because
    check_verdicts and check_suite both derive their populations from what is on
    disk, so a dropped active scenario reached an emitted suite one test short
    with no finding anywhere.

    `rejected` is excluded from the population that must have a directory, and
    the asymmetry is deliberate: challenge marks a scenario `rejected` *after* it
    was instantiated, so a rejected scenario legitimately has a directory, and
    requiring one would fire on a run whose reject path worked exactly as
    prescribed. Score can also rule a scenario `rejected` during the loop, in
    which case instantiate was never dispatched for it and it has no directory
    at all -- so both presence and absence are prescribed states for `rejected`,
    and neither is checkable here.
    """
    world = _load(run.world_model)
    if world is None:
        return []
    scenarios_doc = _load(run.scenarios) or {"scenarios": []}
    by_id = {s["id"]: s for s in scenarios_doc.get("scenarios", [])}
    out: list[Finding] = []

    # A directory name that is not a safe path segment cannot be a scenario id,
    # so no artifact under it can be read. That is a repairable defect in the
    # stage that wrote it, so it is an ordinary finding at exit 1 rather than
    # an UnsafeSegment escaping to cli.py as exit 2 and taking every other
    # finding in the run with it.
    for name in run.unsafe_instance_dir_names():
        out.append(
            Finding(
                run.instances_dir,
                "refs",
                "",
                f"instance directory {name!r} is not a usable scenario id: a scenario id must "
                "start with a letter or digit and contain only letters, digits, dots, dashes, "
                "and underscores",
            )
        )

    # The guard is `is_dir()`, not a count, for the reason the sibling fan-out
    # checkers give: with no 04-instances/ at all the run has not reached
    # instantiate, and reporting every active scenario there would spend the
    # orchestrator's single repair attempt on a phantom. Every other loop in
    # this checker iterates the directory and is empty-safe without a guard,
    # which is why this is the first clause to need one.
    if run.instances_dir.is_dir():
        instantiated = set(run.scenario_ids_with_instances())
        # `sorted(by_id)` rather than `sorted(by_id.items())`: sorting the items
        # sorts pairs whose second element is never compared, since the ids that
        # order them are unique keys -- so it reads as though the scenario dicts
        # were being ordered, buys nothing over sorting the keys, and diverges
        # from the idiom the sibling completeness clauses use. A duplicate id in
        # 02-scenarios.json is reported from the list rather than caught here;
        # this mapping is a comprehension, so two equal ids collapse into one
        # key long before anything sorts them.
        for sid in sorted(by_id):
            if by_id[sid].get("status") == "active" and sid not in instantiated:
                out.append(
                    Finding(
                        run.instances_dir,
                        "refs",
                        "",
                        f"active scenario {sid} has no instance directory on disk; every "
                        "scenario score left active is one instantiate was dispatched for",
                    )
                )

    for sid in run.scenario_ids_with_instances():
        scenario = by_id.get(sid)
        if scenario is None:
            out.append(
                Finding(run.instance_dir(sid), "refs", "", f"no scenario named {sid} was proposed")
            )
            continue
        # Every scenario_id under 04/05/06 must have been *judged* in 02:
        # `active`, or `rejected` after the fact by challenge. A `rejected`
        # scenario that was already instantiated is the state the reject path
        # prescribes, so it is not a finding; a `proposed`
        # one is, because score has not ruled on it yet, and so is a
        # `duplicate`, because dedupe folded it into another scenario.
        status = scenario.get("status")
        if status not in JUDGED_STATUSES:
            out.append(
                Finding(
                    run.instance_dir(sid),
                    "refs",
                    "",
                    f"scenario {sid} has status {status!r} but only a judged scenario (active, "
                    "or rejected after the fact) should have been instantiated",
                )
            )

        seed = _load(run.seed(sid))
        expected = _load(run.expected(sid))
        if seed is None or expected is None:
            continue

        seed_path, expected_path = run.seed(sid), run.expected(sid)

        def out_seed(pointer: str, message: str, path=seed_path) -> None:
            out.append(Finding(path, "refs", pointer, message))

        def out_inv(pointer: str, message: str, path=seed_path) -> None:
            out.append(Finding(path, "invariant", pointer, message))

        def out_exp(pointer: str, message: str, path=expected_path) -> None:
            out.append(Finding(path, "refs", pointer, message))

        _check_seed_conformance(out_seed, world, seed)
        _check_invariants(out_inv, world, seed)
        if expected["scenario_id"] != sid:
            out_exp(
                "/scenario_id",
                f"expected.json names scenario {expected['scenario_id']} but lives in the "
                f"instance directory for {sid}",
            )
        scenario_fact = scenario["discriminating_fact"]
        if expected["discriminating_fact"] != scenario_fact:
            out_exp(
                "/discriminating_fact",
                f"the oracle's discriminating_fact is {expected['discriminating_fact']!r} but "
                f"the scenario declared {scenario_fact!r}; copy the scenario's verbatim -- a "
                "paraphrase is indistinguishable from substituting an easier fact",
            )
        scenario_caps = {ref["capability_id"] for ref in scenario["capability_refs"]}
        _check_reachability(out_exp, world, seed, expected, scenario_caps)
    return out


def check_verdicts(run: RunPaths) -> list[Finding]:
    """One coherent verdict per instantiated scenario.

    Returns nothing until 05-verdicts/ exists: with no verdict directory at all
    the run has not reached challenge, and reporting every instance as
    unjudged there would spend the orchestrator's single repair attempt on a
    phantom.

    Note what that does *not* tolerate. Once the directory exists -- i.e. once
    the first verdict has landed -- every instance without one is reported. The
    challenge fan-out window, where some instances are judged and others are
    still in flight, is therefore *not* tolerated; the guard is `is_dir()`, not
    a count. That is deliberate: check-refs is dispatched after the fan-out
    completes, so a missing verdict at that point is real.
    """
    if not run.verdicts_dir.is_dir():
        return []
    scenarios_doc = _load(run.scenarios) or {"scenarios": []}
    hop_depths = {s["id"]: s.get("hop_depth") for s in scenarios_doc.get("scenarios", [])}
    instantiated = run.scenario_ids_with_instances()
    out: list[Finding] = []

    for sid in instantiated:
        path = run.verdict(sid)
        verdict = _load(path)
        if verdict is None:
            out.append(Finding(run.instance_dir(sid), "refs", "", f"instance {sid} has no verdict"))
            continue

        def report(pointer: str, message: str, path=path) -> None:
            out.append(Finding(path, "refs", pointer, message))

        if verdict.get("scenario_id") != sid:
            report(
                "/scenario_id",
                f"verdict names scenario {verdict.get('scenario_id')} but is filed under {sid}",
            )
        if verdict.get("verdict") == "accept":
            if not verdict.get("derivable_without_guessing", True):
                report(
                    "/verdict",
                    "verdict is accept but the test is reported as not derivable without "
                    "guessing; those cannot both be true",
                )
            if not verdict.get("uniquely_determined", True):
                report(
                    "/verdict",
                    "verdict is accept but the answer is reported as not uniquely determined; "
                    "those cannot both be true",
                )
        claimed = hop_depths.get(sid)
        found = verdict.get("minimum_tool_calls_found")
        if (
            isinstance(claimed, int)
            and isinstance(found, int)
            and found < claimed
            and "difficulty_overstated" not in verdict.get("flags", [])
        ):
            report(
                "/minimum_tool_calls_found",
                f"adversary solved this in {found} call(s) but the scenario claims hop_depth "
                f"{claimed}; the difficulty_overstated flag is required",
            )

    if run.verdicts_dir.is_dir():
        known = set(instantiated)
        for path in list_json(run.verdicts_dir):
            if path.stem not in known:
                out.append(
                    Finding(path, "refs", "", f"verdict for {path.stem}, which has no instance")
                )
    return out


_PACKAGE_FILES = (
    "task.toml",
    "instruction.md",
    "seed.json",
    "golden.json",
    "provenance.md",
    "tests/expected.json",
    "tests/verify.py",
    "tests/test.sh",
)


def check_suite(run: RunPaths) -> list[Finding]:
    """Each emitted package is complete and addresses a judged scenario.

    A package missing its verifier or its contract is worse than no package: it
    reaches the platform, fails to score, and reads as an agent failure.

    A `rejected` scenario is tolerated here, not reported. emit prunes the
    package for a scenario that stopped qualifying, but nothing orders emit and
    check-refs, so between challenge marking a scenario `rejected` and the next
    emit the package is legitimately still on disk. Reporting it would make
    check-refs dirty in a state the reject path prescribes, and no repair the
    orchestrator dispatched could clear it. See JUDGED_STATUSES.

    **The `.get()` calls below are deliberate, not an inconsistency with this
    module's layer-1 precondition.** Everywhere else this module indexes
    schema-required keys directly, because layer 1 gated the artifact first.
    Here the files being read live under 06-suite/, and nothing orders
    `validate --stage emit` before `check-refs` -- so this is the one place
    where an ungated document can legitimately arrive. Tolerating a missing key
    is what turns that into an ordinary finding instead of a traceback.
    """
    scenarios_doc = _load(run.scenarios) or {"scenarios": []}
    by_id = {s["id"]: s for s in scenarios_doc.get("scenarios", [])}
    out: list[Finding] = []

    for sid in run.scenario_ids_with_tasks():
        task = run.task_dir(sid)
        for name in _PACKAGE_FILES:
            if not (task / name).is_file():
                out.append(Finding(task, "refs", "", f"emitted package is missing {name}"))

        scenario = by_id.get(sid)
        if scenario is None:
            out.append(Finding(task, "refs", "", f"no scenario named {sid} was proposed"))
        elif scenario.get("status") not in JUDGED_STATUSES:
            out.append(
                Finding(
                    task,
                    "refs",
                    "",
                    f"scenario {sid} has status {scenario.get('status')!r} but only a judged "
                    "scenario (active, or rejected after the fact) should have been emitted",
                )
            )

        contract = _load(task / "tests" / "expected.json")
        if contract is not None and contract.get("scenario_id") != sid:
            out.append(
                Finding(
                    task / "tests" / "expected.json",
                    "refs",
                    "/scenario_id",
                    f"contract names scenario {contract.get('scenario_id')} but lives in the "
                    f"task directory for {sid}",
                )
            )
    return out


def _malformed_task_results(task: dict) -> str | None:
    """None if `task["results"]` is shaped well enough for smoke's own functions
    to index directly; otherwise a message naming what is missing.

    check_report's `.get()` tolerance stops at the top of each result: smoke's
    `comparable`, `task_flags`, and `summarize` all index `results`, `role`
    (unconditionally, for every result -- `summarize` checks `result["role"] ==
    "oracle"` before it looks at whether the result was even scored), and
    `reward` (for a scored result) directly, because layer 1 normally guarantees
    they are there. A report that arrives before `validate --stage smoke` has
    run can be missing any of them. This is what turns that into a finding
    naming one task instead of a traceback that names none.
    """
    results = task.get("results")
    if not isinstance(results, list):
        return "results is missing or not a list"
    for result in results:
        if not isinstance(result, dict):
            return "a result is not an object"
        if "role" not in result:
            return "a result has no role"
        if result.get("scored") and "reward" not in result:
            return "a scored result has no reward"
    return None


def check_report(run: RunPaths) -> list[Finding]:
    """07-report.json against 06-suite/, and its own arithmetic against its results.

    check_all had no report checker, so a report could list a scenario whose
    package emit had pruned and `validate --stage smoke` stayed clean. That became
    reachable when emit started pruning.

    **Status is the distinguisher for the hard case.** A report naming a scenario
    with no package is legitimate when the scenario is `rejected`: challenge marks
    it rejected *after* smoke ran, emit prunes the package, and that record is
    what the honest-hole report ("87%, 3 cells lost to rejected scenarios") is
    built from. Reporting it would make check-refs permanently dirty in a state the
    reject path prescribes, and the only way to clear it would be to delete the
    evidence. An `active` scenario with no package, or an id absent from
    02-scenarios.json, is the real defect: a report over a suite nobody emitted.

    Every recomputed number comes from calling smoke's own functions. A second
    implementation of the arithmetic here would agree today and drift the first
    time a threshold moved -- the per-seam defect class that produced the previous
    build's Critical.

    `.get()` throughout: nothing orders `validate --stage smoke` before
    check-refs, so an ungated report can legitimately arrive. Same exception
    check_suite documents, same reason. That tolerance has to hold all the way
    down to smoke's own functions, not just at this module's boundary: a task
    whose `results` don't have the shape smoke indexes directly is excluded from
    the flag comparison and from the summary/verdict recomputation, via
    `_malformed_task_results`, rather than handed to smoke to crash on. A
    present report that is not even an object gets one whole-document finding
    instead of being silently waved through the way an absent one is.
    """
    from rubrica import smoke

    report = _load(run.report)
    if report is None:
        return []
    if not isinstance(report, dict):
        return [
            Finding(
                run.report,
                "refs",
                "",
                "07-report.json is valid JSON but not an object, so none of its fields "
                "can be checked",
            )
        ]
    out: list[Finding] = []

    def report_finding(pointer: str, message: str) -> None:
        out.append(Finding(run.report, "refs", pointer, message))

    manifest = _load(run.manifest)
    if isinstance(manifest, dict) and report.get("run_id") != manifest.get("run_id"):
        report_finding(
            "/run_id",
            f"report is filed against run {report.get('run_id')!r} but this run is "
            f"{manifest.get('run_id')!r}",
        )

    agents = report.get("agents") or []
    roles = tuple(
        role
        for role in smoke.ROLES
        if role in {agent.get("role") for agent in agents if isinstance(agent, dict)}
    )
    for role in smoke.REQUIRED_ROLES:
        if role not in roles:
            report_finding(
                "/agents",
                f"no {role!r} agent ran, so the suite cannot be judged: it is what detects "
                + ("a trivial suite" if role == "weak_baseline" else "broken gold labels"),
            )

    scenarios_doc = _load(run.scenarios) or {"scenarios": []}
    by_id = {s["id"]: s for s in scenarios_doc.get("scenarios", [])}
    emitted = set(run.scenario_ids_with_tasks())

    tasks = [task for task in report.get("tasks") or [] if isinstance(task, dict)]
    named: list[str] = []
    well_formed_tasks: list[dict] = []
    for i, task in enumerate(tasks):
        sid = task.get("scenario_id")
        named.append(sid)
        scenario = by_id.get(sid)
        if scenario is None:
            report_finding(
                f"/tasks/{i}/scenario_id",
                f"the report ran {sid!r}, which no scenario in 02-scenarios.json proposes",
            )
        elif scenario.get("status") not in JUDGED_STATUSES:
            report_finding(
                f"/tasks/{i}/scenario_id",
                f"the report ran {sid!r}, whose status is {scenario.get('status')!r}; only a "
                "judged scenario (active, or rejected after the fact) should have been emitted",
            )
        elif sid not in emitted and scenario.get("status") != "rejected":
            report_finding(
                f"/tasks/{i}/scenario_id",
                f"the report ran {sid!r} but it has no emitted package; a report over a suite "
                "that was never emitted describes nothing",
            )

        declared = {r.get("role") for r in task.get("results") or [] if isinstance(r, dict)}
        for role in roles:
            if role not in declared:
                report_finding(
                    f"/tasks/{i}/results",
                    f"{role} is declared in /agents but produced no result for {sid!r}, so its "
                    "mean is taken over a different task set than the other roles",
                )
        malformed = _malformed_task_results(task)
        if malformed is not None:
            report_finding(
                f"/tasks/{i}/results",
                f"{malformed}, so this task cannot be checked against smoke's own "
                "arithmetic; excluded from the flag and summary recomputation below "
                "rather than crashing it",
            )
            continue
        well_formed_tasks.append(task)

        expected_pass, expected_fail = smoke.task_flags(task, roles)
        for key, value in (("all_pass", expected_pass), ("all_fail", expected_fail)):
            if task.get(key) is not value:
                report_finding(
                    f"/tasks/{i}/{key}",
                    f"declared {task.get(key)!r} but the results say {value!r}",
                )

    # key=str: `named` can hold None for a task with no scenario_id (already
    # reported above, via the ghost-scenario branch), and None does not compare
    # against str -- sorting the raw set would raise before that finding's
    # message could be read.
    for sid in sorted(set(named), key=str):
        if named.count(sid) > 1:
            report_finding(
                "/tasks",
                f"scenario {sid!r} appears more than once, which doubles its weight in every "
                "mean the summary reports",
            )
    for sid in sorted(emitted - set(named)):
        report_finding(
            "/tasks",
            f"the emitted package for {sid!r} was never run: the suite ships a task nothing "
            "has executed",
        )

    expected_summary = smoke.summarize(well_formed_tasks, roles)
    declared_summary = report.get("summary") or {}
    for key, value in expected_summary.items():
        if declared_summary.get(key) != value:
            report_finding(
                f"/summary/{key}",
                f"declared {declared_summary.get(key)!r} but the results give {value!r}",
            )

    expected_verdict = smoke.verdict_for(well_formed_tasks, expected_summary, roles)
    if report.get("verdict") != expected_verdict:
        report_finding(
            "/verdict",
            f"declared {report.get('verdict')!r} but the results give {expected_verdict!r}; the "
            "verdict is the number a human reads first",
        )
    return out


def check_all(run: RunPaths) -> list[Finding]:
    """Every layer-2 check that the run directory currently has inputs for.

    An unparseable artifact short-circuits everything below it. Every checker
    treats an unreadable document as an absent one, so continuing produces
    findings that blame artifacts which are fine and never names the one that is
    broken -- and the orchestrator's single bounded repair attempt then rewrites
    the wrong file.
    """
    unreadable = check_readable(run)
    if unreadable:
        return unreadable
    findings: list[Finding] = []
    findings.extend(check_catalogue(run))
    findings.extend(check_slices(run))
    findings.extend(check_disposition_parts(run))
    findings.extend(check_objective(run))
    findings.extend(check_audit(run))
    findings.extend(check_triage(run))
    findings.extend(check_manifest(run))
    findings.extend(check_inputs(run))
    findings.extend(check_admitted_inputs(run))
    findings.extend(check_limits(run))
    findings.extend(check_subjects(run))
    findings.extend(check_contradiction_parts(run))
    findings.extend(check_outcomes(run))
    # After the partials are readable, before anything reasons about the model
    # assembled from them: the accounting is a property of what each pass wrote,
    # so it is answerable while the parts are still separate documents.
    findings.extend(check_input_dispositions(run))
    # After each pass's accounting, before anything reasons about the assembled
    # model: these are properties of what reconcile-services and
    # synthesise-interfaces wrote, answerable while the parts are still separate
    # documents.
    findings.extend(check_services(run))
    findings.extend(check_interfaces(run))
    findings.extend(check_world_model(run))
    findings.extend(check_claim_utilisation(run))
    findings.extend(check_batches(run))
    findings.extend(check_scenario_parts(run))
    findings.extend(check_score_parts(run))
    findings.extend(check_scenarios(run))
    findings.extend(check_coverage(run))
    findings.extend(check_instances(run))
    findings.extend(check_verdicts(run))
    findings.extend(check_suite(run))
    findings.extend(check_report(run))
    return findings
