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
from rubrica.invariants import InvariantForm
from rubrica.invariants import evaluate as evaluate_invariant
from rubrica.paths import RunPaths, is_safe_segment, list_json
from rubrica.slices import row_bytes
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
    """
    targets = [run.catalogue, run.triage, run.manifest]
    targets += list_json(run.claims_dir)
    targets += [run.world_model, run.scenarios]
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


def _cells(world: dict) -> set[tuple[str, str]]:
    """Every (capability_id, outcome_class_id) pair the world model declares."""
    return {
        (cap["id"], oc["id"])
        for cap in world.get("capabilities", [])
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

    Only ever called on candidate coverage overlaps, which are rare enough
    (a hand-edited plan, not a normal `write_slices` output) that this exists
    purely so the message reads as English rather than "a, b" for the common
    two-item case.
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
    if run.adoptions.is_file():
        try:
            adoptions_doc = read_json(run.adoptions)
        except ArtifactError as exc:
            out.append(Finding(run.adoptions, "refs", "", str(exc)))
            adoptions_doc = None
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

    Checked in one direction only: every claims file must name a registered
    input, never the reverse. A registered input with no claims file yet is the
    normal state during the extract fan-out, and reporting it there would fire
    on a run in which nothing is wrong.
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
    actual_cells = len(_cells(world))
    if denominator.get("capability_cells") != actual_cells:
        report(
            "/denominator/capability_cells",
            f"declared capability_cells={denominator.get('capability_cells')} but the world "
            f"model declares {actual_cells} capability x outcome-class cells",
        )
    actual_goals = len(world.get("goals", []))
    if denominator.get("goals") != actual_goals:
        report(
            "/denominator/goals",
            f"declared goals={denominator.get('goals')} but the world model declares "
            f"{actual_goals}",
        )
    return out


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
    rb-extract produced nothing usable from it or rb-reconcile ignored a whole
    artifact.
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
    for missing in sorted(cells - seen):
        report("/capability_matrix/cells", f"matrix omits cell {cell_ref(*missing)}")
    for invented in sorted(seen - cells):
        report("/capability_matrix/cells", f"matrix invents cell {cell_ref(*invented)}")
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
    """Seed conformance, machine invariants, and the reachability gate."""
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
    findings.extend(check_world_model(run))
    findings.extend(check_claim_utilisation(run))
    findings.extend(check_scenarios(run))
    findings.extend(check_coverage(run))
    findings.extend(check_instances(run))
    findings.extend(check_verdicts(run))
    findings.extend(check_suite(run))
    findings.extend(check_report(run))
    return findings
