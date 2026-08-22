"""The seal: assemble 00-triage.json from the staged parts.

Code rather than a prompt, for the reason emit is code: two runs with
identical parts must produce a byte-identical triage record, or variance
stops being attributable to the pass that caused it. There is a second
reason here, the same one `reconcile.seal` (the sibling seal for stage 1)
names: a code step streams nothing, so it cannot be killed by the gateway's
idle reset, however large the assembled record gets.

This module assembles; it does not check. Cross-artifact checking is layer 2
and lives in refs.py (`check_triage`, which runs over the sealed record after
this writes it, on any run -- including one this seal never sealed). What
this *does* report is the narrow class where assembly cannot faithfully
represent what it was handed, and the list is exactly five items long:

1. a part absent, unparseable, or not a JSON object carrying its declared
   payload keys -- 00-objective.json, 00-slices.json (not a staged *part* of
   triage itself, but still an input this seal cannot assemble without, read
   through the identical door), every 00-dispositions/<slice>.json part, and
   00-audit.json. 00-adoptions.json is exempt: it is required and may be
   empty, and adoptions-0.1.json's own description says its absence is not a
   defect -- no human has necessarily adopted anything -- so a missing file
   there is folded in as `{"adoptions": []}` rather than reported;
2. a candidate with no disposition anywhere across every part and every
   adoption, or with more than one (triage-0.1.json's own invariant -- one
   disposition per candidate -- now checked across parts rather than within
   one document);
3. a disposition naming a candidate outside the slice its own part rules on;
4. no `admit` anywhere across every part and every adoption (spec section
   10.2's inversion: a member may legitimately decline its whole slice -- a
   tests/ or docs/ subtree with nothing worth admitting -- and that member
   still writes its part; only the *union* across every part having zero
   admits is a scoping failure, so this belongs to the seal and never to any
   one member);
5. a `digest_insufficient` decline with no deficiency anywhere in
   00-audit.json, or a `needs_projection` decline with no projection there
   sourcing it -- the two reference sets `check_triage` already checks
   against, now read from a different artifact because the sealed record
   does not exist yet.

It writes nothing at all when it reports any of them. A half-assembled
record would be worse than none: it would clear layer 1 for the fields it did
manage to fill, and read as a complete triage decision to a human at gate 0.

Items 2, 4 and 5 overlap `refs.check_triage` deliberately, for the reason
`reconcile.seal`'s own docstring gives for its analogous overlaps:
`check_triage` reports *after* the fact, over any triage record including one
this seal never sealed, while the branches here refuse *before the write*,
because assembly is otherwise perfectly possible in every one of these
cases -- a dropped or duplicated candidate simply does not appear (or appears
twice) in the merged dispositions list, an empty admitted set is still a
valid-looking array, and an unreferenced decline reason is still a valid
enum value. The record then reaches gate 1 looking coherent to a human and to
`check_triage`, which indexes the very list this seal just built and so
agrees with whatever it was handed. A pipeline more likely to produce output
at the cost of an unobservable drop is a loss, not a win.

Item 3 overlaps nothing in any layer, and for a sharper reason than "this one
runs first": `check_triage` has no concept of slices at all -- by the time it
runs, a wrong-slice disposition already looks like any other disposition in
the merged list, with nothing left in the sealed record to tell it apart from
one that was scoped correctly. The seal is the only place either half of that
defect is ever checked against the plan that scoped it.

Presence, parseability and payload-key presence are the whole of what item 1
checks -- not the *type* of what a payload key holds, exactly as
`reconcile.seal`'s own docstring states and for the identical reason: layer 1
(one schema per staged artifact, all already shipped) is the rejection point
for a wrong-typed value, and duplicating that here would put the same rule in
two places with two messages. The code below indexes nested fields
(`candidate_id`, `disposition`, `sources[].candidate_id`, ...) directly, the
same way `reconcile.seal` indexes `entry["capability_id"]` -- a wrongly-typed
nested field still raises out of it, by design.
"""

from __future__ import annotations

from pathlib import Path

from rubrica.artifacts import ArtifactError, read_json, write_json
from rubrica.findings import Finding
from rubrica.paths import RunPaths

# Every singleton input this seal reads through the same door, in the order a
# repair should start from: the objective pass ran first, the slice plan
# predates triage entirely, and the audit pass consolidates every part's
# deficiency_notes last. (RunPaths attribute, the payload keys this module
# actually reads from it) -- the keys are checked, not merely documented, by
# _payload_keys below, mirroring reconcile._SINGLETON_PARTS exactly.
_SINGLETON_PARTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("objective", ("run_id", "objective_review")),
    ("slices", ("slices",)),
    ("audit", ("deficiencies", "projections")),
)

# The read-failure sentinel, and specifically *not* None -- `null` is a
# legitimate JSON document and read_json returns None for it, which would
# make `document is not None` mean two different things at once. Measured on
# the sibling reconcile seal: a `null` part skipped the payload-key check
# below and reached a bare dict index, raising a KeyError that cli.py's
# catch-all then reported against the run root rather than the broken
# artifact. An object() cannot be read off disk.
_UNREADABLE = object()

# The lowest rank a disposition without a member-assigned `priority` sorts
# at, within its own surface group -- mirroring intake._NO_PRIORITY, but not
# imported from there: that constant orders *already-sealed* admits for
# materialisation, one stage downstream of this one, and folding the two
# into a single import would couple this module's own composition to a
# private constant of a caller that does not exist yet when this runs.
_NO_MEMBER_PRIORITY = 1 << 30


def _read_part(path: Path, out: list[Finding]) -> object:
    """One part's parsed JSON, or _UNREADABLE with a finding naming *that* part.

    Naming the right artifact is the exit-code contract's third rule, learned
    the hard way in this repo: check-refs over an unreadable 01-claims/ once
    reported four fabricated findings against a world model that was fine.
    """
    try:
        return read_json(path)
    except ArtifactError as exc:
        out.append(Finding(path, "seal", "", str(exc)))
        return _UNREADABLE


# JSON's own type names, because the finding sits next to the JSON file it
# names: "found null" and "found array" describe what is on disk, not Python.
_JSON_TYPES: dict[type, str] = {
    type(None): "null",
    bool: "boolean",
    int: "number",
    float: "number",
    str: "string",
    list: "array",
}


def _json_type(document: object) -> str:
    return _JSON_TYPES.get(type(document), type(document).__name__)


def _payload_keys(path: Path, keys: tuple[str, ...], document: object, out: list[Finding]) -> bool:
    """Whether `document` is an object carrying every key declared for it.

    Mirrors reconcile._payload_keys precisely, including the isinstance guard
    doing double duty: a document that is not a dict has no payload key
    either, and two of the wrong shapes (a list, a string) would otherwise
    answer `key not in document` correctly while the other two (`None`, an
    int) raise TypeError trying -- the guard is what turns all four into one
    finding instead of one finding and three tracebacks.
    """
    if not isinstance(document, dict):
        out.append(
            Finding(
                path,
                "seal",
                "",
                f"expected a JSON object with {' and '.join(sorted(keys))}, found "
                f"{_json_type(document)}",
            )
        )
        return False
    missing = [key for key in keys if key not in document]
    for key in missing:
        out.append(
            Finding(
                path,
                "seal",
                "",
                f"no {key!r} key; whatever wrote this artifact did not record its "
                "payload, so there is nothing to assemble from it",
            )
        )
    return not missing


def _read_checked(path: Path, keys: tuple[str, ...], out: list[Finding]) -> dict | None:
    """One artifact that is readable *and* carries its payload keys, else None.

    The one door every artifact this seal reads comes through, so a read
    failure and a document missing a payload key are different findings but
    the same outcome for the caller -- exactly the shape a `null` part
    exploited before this existed.
    """
    document = _read_part(path, out)
    if document is _UNREADABLE:
        return None
    return document if _payload_keys(path, keys, document, out) else None


def _member_priority(entry: dict) -> int:
    """`entry["priority"]` if it is a real int, else the lowest-rank sentinel.

    A member ranks only the candidates it admits (spec section 8); a decline
    ordinarily carries no `priority` at all, and this sentinel is what lets
    it sort after every admit in its surface group without treating "absent"
    as a crash. `bool` is excluded because `isinstance(True, int)` is `True`
    in Python and a stray `"priority": true` would otherwise rank as 1.
    """
    priority = entry.get("priority")
    if isinstance(priority, int) and not isinstance(priority, bool):
        return priority
    return _NO_MEMBER_PRIORITY


def seal(run: RunPaths) -> tuple[Path | None, list[Finding]]:
    """Assemble 00-triage.json from the staged parts, or report why it cannot be.

    Returns `(run.triage, [])` on a clean assembly and `(None, findings)`
    otherwise -- never both a path and findings, and never a write when
    findings are non-empty. Re-running this over an already-sealed run
    re-derives the identical record from the same parts (spec 8.1): sealing
    is idempotent because nothing it reads is itself the sealed record.
    """
    findings: list[Finding] = []

    documents: dict[str, dict] = {}
    for attribute, keys in _SINGLETON_PARTS:
        document = _read_checked(getattr(run, attribute), keys, findings)
        if document is not None:
            documents[attribute] = document

    # 00-adoptions.json is the one part exempt from item 1's "absent is a
    # defect" rule -- see the module docstring and adoptions-0.1.json's own
    # description. A file that exists but is broken is still reported through
    # the identical door as every other part; only its *absence* is silent.
    if run.adoptions.is_file():
        adoptions_document = _read_checked(run.adoptions, ("adoptions",), findings)
    else:
        adoptions_document = {"adoptions": []}
    if adoptions_document is not None:
        documents["adoptions"] = adoptions_document

    # One dispositions part per slice that has written one -- slice_ids_with_parts
    # already excludes anything list_json's own listing-failure guards would
    # have turned into a UsageError, so this loop only has parseability and
    # payload-key presence left to check, exactly like every other part above.
    parts: dict[str, dict] = {}
    for slice_id in run.slice_ids_with_parts():
        part = _read_checked(run.disposition_part(slice_id), ("dispositions",), findings)
        if part is not None:
            parts[slice_id] = part

    if findings:
        return None, findings

    # -- item 3: a disposition naming a candidate outside its own slice -----
    # Keyed by the plan's own slice ids, not by whatever a part's own
    # slice_id field claims: parts are read by filename
    # (run.disposition_part(slice_id)), the same way check_slices resolves a
    # shard by the plan's id rather than by content, so a part cannot lie
    # about which slice it is scoped to simply by writing a different value
    # inside itself.
    slice_candidates: dict[str, set[str]] = {
        s["id"]: set(s["candidate_ids"]) for s in documents["slices"]["slices"]
    }
    for slice_id, part in parts.items():
        allowed = slice_candidates.get(slice_id, set())
        for entry in part["dispositions"]:
            cid = entry["candidate_id"]
            if cid not in allowed:
                findings.append(
                    Finding(
                        run.disposition_part(slice_id),
                        "seal",
                        "",
                        f"candidate {cid!r} is not in slice {slice_id!r}, which this part rules on",
                    )
                )

    # -- item 2: every candidate ruled on exactly once, across every part and
    # every adoption. adoptions bypass slicing entirely (spec 8.1: an adopted
    # candidate needs no slice member to rule on it since a human already
    # did), so the population this totals against is the union of every
    # slice's own candidate_ids and every adoption's candidate_id, not the
    # catalogue -- reading the catalogue here would be a sixth artifact this
    # seal does not otherwise need, for a set check_slices' own coverage
    # check already guarantees agrees with the catalogue whenever it is run.
    rulings: dict[str, list[tuple[Path, dict]]] = {}
    for slice_id, part in parts.items():
        for entry in part["dispositions"]:
            rulings.setdefault(entry["candidate_id"], []).append(
                (run.disposition_part(slice_id), entry)
            )
    for adoption in documents["adoptions"]["adoptions"]:
        disposition = adoption["disposition"]
        rulings.setdefault(disposition["candidate_id"], []).append((run.adoptions, disposition))

    population = {cid for candidates in slice_candidates.values() for cid in candidates}
    population |= {a["candidate_id"] for a in documents["adoptions"]["adoptions"]}

    for cid in sorted(population - set(rulings)):
        findings.append(
            Finding(
                run.dispositions_dir,
                "seal",
                "",
                f"candidate {cid!r} has no disposition in any staged part or adoption",
            )
        )
    for cid in sorted(cid for cid, entries in rulings.items() if len(entries) > 1):
        findings.append(
            Finding(
                rulings[cid][0][0],
                "seal",
                "",
                f"candidate {cid!r} has more than one disposition across the staged parts",
            )
        )

    # -- item 5: a digest_insufficient/needs_projection decline referencing
    # nothing 00-audit.json actually carries. Mirrors check_triage's own
    # weak/strong split exactly (see that function's comments for why
    # digest_insufficient stays weak), reading from the audit part instead of
    # the not-yet-assembled record because that is where the two lists live
    # before this seal runs.
    deficiency_ids = {d["deficiency_id"] for d in documents["audit"]["deficiencies"]}
    projected_candidate_ids = {
        source["candidate_id"]
        for projection in documents["audit"]["projections"]
        for source in projection["sources"]
    }
    for cid, entries in rulings.items():
        if len(entries) != 1:
            continue  # already reported above; do not compound it here
        path, entry = entries[0]
        if entry.get("disposition") == "admit":
            continue
        code = entry.get("reason_code")
        if code == "digest_insufficient" and not deficiency_ids:
            findings.append(
                Finding(
                    path,
                    "seal",
                    "",
                    f"a digest_insufficient decline for {cid!r} has no deficiency in "
                    f"{run.audit.name} to reference",
                )
            )
        elif code == "needs_projection" and cid not in projected_candidate_ids:
            findings.append(
                Finding(
                    path,
                    "seal",
                    "",
                    f"a needs_projection decline for {cid!r} has no projection in "
                    f"{run.audit.name} sourcing it",
                )
            )

    # -- item 4: spec 10.2's inversion. A single part may legitimately admit
    # nothing at all; only the union across every part and every adoption
    # having zero admits is a scoping failure.
    if not any(
        entry.get("disposition") == "admit" for entries in rulings.values() for _, entry in entries
    ):
        findings.append(
            Finding(
                run.dispositions_dir,
                "seal",
                "",
                "no admit anywhere across every staged part or adoption; an empty admitted "
                "set is a scoping failure rather than a triage result",
            )
        )

    if findings:
        return None, findings

    # -- assembly: every candidate below has exactly one ruling (item 2's
    # dupe/missing checks already returned otherwise), so entries[0] is safe.
    surfaces = documents["objective"]["objective_review"]["surfaces"]
    # First-seen wins: a candidate named in more than one surface's evidence
    # (schema-legal -- evidence carries no cross-surface uniqueItems) ranks by
    # whichever surface the objective pass listed first, matching how a
    # reader scans the array top to bottom.
    surface_rank: dict[str, int] = {}
    for index, surface in enumerate(surfaces):
        for cid in surface["evidence"]:
            surface_rank.setdefault(cid, index)
    # A candidate no surface's evidence names at all -- most often one this
    # seal is folding in from an adoption, minted after the objective pass
    # ran and so never eligible to appear in any surface's evidence -- sorts
    # after every ranked surface, not before or interleaved with one.
    unranked = len(surfaces)

    def sort_key(item: tuple[str, tuple[Path, dict]]) -> tuple[int, int, str]:
        cid, (_, entry) = item
        return (surface_rank.get(cid, unranked), _member_priority(entry), cid)

    ordered = sorted(((cid, entries[0]) for cid, entries in rulings.items()), key=sort_key)

    dispositions: list[dict] = []
    admit_rank = 0
    for _cid, (_, entry) in ordered:
        entry = dict(entry)
        if entry.get("disposition") == "admit":
            admit_rank += 1
            entry["priority"] = admit_rank
        dispositions.append(entry)

    # Deficiencies and projections are copied from 00-audit.json, then folded
    # against 00-adoptions.json: adoptions-0.1.json's own description says
    # this seal is what sets satisfied_by/closed_by at fold-in time, never
    # adopt_projection itself, since adopt_projection no longer writes the
    # record those fields live in.
    deficiencies = [dict(d) for d in documents["audit"]["deficiencies"]]
    projections = [dict(p) for p in documents["audit"]["projections"]]
    for adoption in documents["adoptions"]["adoptions"]:
        for projection in projections:
            if projection["projection_id"] == adoption["projection_id"]:
                projection["satisfied_by"] = adoption["candidate_id"]
        for deficiency in deficiencies:
            if deficiency["deficiency_id"] in adoption["closed_deficiency_ids"]:
                deficiency["closed_by"] = adoption["projection_id"]

    triage_record = {
        "schema_version": "0.1",
        "run_id": documents["objective"]["run_id"],
        "objective_review": documents["objective"]["objective_review"],
        "dispositions": dispositions,
        "deficiencies": deficiencies,
        "projections": projections,
    }
    write_json(run.triage, triage_record)
    return run.triage, []
