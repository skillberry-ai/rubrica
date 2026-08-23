"""`gate-brief`: the human surface at all four human gates.

A composer, not a new analysis -- it renders reports
that already exist (`utilisation.claim_utilisation`, coverage, verdicts) plus
`sizing.implied_size`, in the shape each gate's human decision actually needs:

- **Gate 0** is this build's new one, and it is what decides whether gate 0 is
  holdable at all. It leads with the objective verdict -- supported or not --
  because that is the single fact most likely to make a tired reader overturn
  the whole triage record, and a reader who stops after ten lines must have
  seen it. The predicted-vs-observed surface divergence follows immediately,
  because it is the one available measure of how well the corpus map the
  objective pass ruled from actually described the corpus. Admits by priority,
  declines grouped by reason code, and every open deficiency beside the
  projection that would close it come next. The slice table and the summary of
  every group split across more than one slice close the brief: they are the
  mechanics of *how* the fan-out read the corpus rather than *what* it ruled,
  so a reader who only wants the ruling never has to scroll past them, and a
  reader weighing a `near_duplicate` decline has the split that produced the
  residue on the same page.
- **Gate 1** puts the world model's gaps next to the triage record's open
  deficiencies -- a pairing that is deliberately *not* a
  mechanical check (matching gap prose to decline prose is semantic, the same
  hole `check-refs` leaves for a claim's support). Both sides of that pairing are
  listed, each gap and each open deficiency by its id and its prose statement,
  so for that one call this rendering really is the whole instrument. Claim
  utilisation and the implied suite size are reported alongside it, and the
  reconcile sweep comes first: how many subjects cover how many claims, how
  many subjects were swept for contradictions, how many contradictions were
  recorded, and -- only when that count is non-zero -- the tally by
  `resolution`, which names `unresolved` at
  zero whenever that branch renders at all. The sweep is an **aggregate**, and
  saying so matters: it renders counts, never the contradictions themselves, so
  it is a pointer at `01-contradictions/` rather than a substitute for reading
  it. That is still worth leading with, because cross-pass incoherence -- a
  later pass quietly modelling what `rb-reconcile-contradict` recorded
  `unresolved` -- is not something layer 2 can see, and a non-zero `unresolved`
  in the tally is the cheapest signal that there is a part worth opening.
- **Gates 2 and 3** render what already exists: the coverage verdict, and the
  challenge stage's verdict tallies.

`gate_brief` never raises on a readable run's *content* -- every artifact it
reads is optional, and its absence renders as a stated absence rather than an
exception, on the same ruling that already governs `claim_utilisation`: a
report is never a gate, so it always exits 0. A run directory that cannot be
read at all is a different failure (the harness pointed at something broken),
and is left to raise -- `cli.py`'s shared catch maps that to exit 2 like every
other subcommand's.
"""

from __future__ import annotations

from rubrica.artifacts import read_json
from rubrica.errors import UsageError
from rubrica.intake import admit_sort_key
from rubrica.paths import RunPaths, list_json

# Imported rather than re-spelled, private name and all: `_as_list` is the one
# definition of "a list or nothing" in this build, and its docstring carries the
# measurement (`value or []` lets a truthy non-list reach a bare `for` and raise
# TypeError). A local copy beside `_dicts` and `_mapping` would be a second
# spelling of that guard, and half-a-module's-worth of inconsistent isinstance
# checks is the defect `_dicts` exists to have fixed.
from rubrica.refs import _as_list
from rubrica.sizing import implied_size
from rubrica.utilisation import claim_utilisation

GATES = (0, 1, 2, 3)

# Gate 0's three staged-triage section headers, named once. Each is the anchor a
# reader -- and a test -- scopes to, so a rewording that only lands in one of
# two places would silently unscope an assertion to the whole document.
DIVERGENCE_HEADER = "Surface divergence (predicted vs observed)"
SLICES_HEADER = "Slices the triage family read"
SPLIT_HEADER = "Groups split across more than one slice"


def gate_brief(run: RunPaths, gate: int) -> str:
    """Plain text (a human reads this, not a machine), never JSON."""
    if gate not in GATES:
        raise UsageError(f"unknown gate {gate!r}; expected one of {GATES}")
    return {0: _gate_0, 1: _gate_1, 2: _gate_2, 3: _gate_3}[gate](run)


def _quietly(path):
    """The document at `path`, or None. A malformed or absent artifact is some
    other command's finding to report (validate's, check-refs'); duplicating
    that here would double-count the same defect and, worse, would make a
    report crash instead of stating what it could not read."""
    try:
        return read_json(path)
    except Exception:  # deliberate, matching utilisation._quietly's reasoning
        return None


def _dicts(value) -> list[dict]:
    """The dict members of `value`, or `[]` if it is not a list at all.

    `_quietly` above only guards the document; every loop below then indexed
    into that document's *elements* with a bare `.get`, and half of them had an
    `isinstance` guard while their siblings in the same function did not. A
    triage record carrying `"deficiencies": ["oops-a-string"]` -- which is
    precisely the shape a human hand-editing the document gate 0 invites them
    to hand-edit produces -- raised `AttributeError: 'str' object has no
    attribute 'get'` and turned this command into a fabricated `[internal]`
    finding at exit 1.

    That is two promises at once: this module's docstring says `gate_brief`
    never raises on a readable run's *content*, and the exit-code contract's
    ruling for a report (claim-utilisation's, restated at cli.py's gate-brief
    arm) is that it always exits 0 on a readable run, so an orchestrator
    reading its code cannot mistake data for a defect. A report that reports
    "this document is malformed" by crashing is the least useful reading of a
    document, and gate 0 is not holdable without it.

    Silently dropping the malformed element is deliberate and is the *only*
    thing this can do: raising breaks the promise above, and inventing a
    finding is `validate`'s job -- run `rubrica validate --stage triage` and
    the schema names it precisely. Each caller states the count it rendered, so
    a dropped element shows up as a number that disagrees with the file.
    """
    if not isinstance(value, list):
        return []
    return [member for member in value if isinstance(member, dict)]


def _mapping(value) -> dict:
    """`value` if it is a dict, else `{}`.

    The `x.get("y") or {}` idiom this replaces substitutes only on a *falsy*
    value, so a truthy non-dict -- `"objective_review": "nope"`,
    `"capability_matrix": "x"` -- reached `.get` and raised AttributeError.
    Measured at gates 0, 1 and 2, all three at exit 1.
    """
    return value if isinstance(value, dict) else {}


def _strings(value) -> list[str]:
    """The string members of `value`, or `[]` if it is not a list at all.

    `_dicts`' sibling, for the fields whose elements are ids rather than
    objects -- `candidate_ids`, `other_slices`, a surface's `evidence`. The
    same measured failure applies: a hand-edited `"other_slices": "s02"` is a
    string, iterating it yields characters, and every one of them would be
    counted as a slice holding the group.
    """
    if not isinstance(value, list):
        return []
    return [member for member in value if isinstance(member, str)]


def _disposition_parts(run: RunPaths) -> tuple[list[dict], list[str]]:
    """Every readable `00-dispositions/<slice>.json`, and the slice ids whose
    part is present but could not be read.

    The parts are the only place the surfaces the fan-out *observed* exist:
    `triage-seal` copies `objective_review` from `00-objective.json` and the
    deficiencies from `00-audit.json`, and carries neither
    `predicted_surface_count` nor any part's `observed_surfaces` into the
    sealed record. So section 4.1's divergence can only be rendered by reading
    back what the members wrote, which is why gate 0's brief reads a staged
    artifact at all.

    The *directory* listing is deliberately not guarded: `list_json` raises
    `UsageError` on an unreadable directory and `cli.py` maps that to exit 2,
    which is this module's docstring's own line between "a readable run's
    content" (always exit 0, absence stated) and "a run directory that cannot
    be read at all". `claim_utilisation` over `01-claims/` and `_gate_3` over
    `05-verdicts/` are the two existing reports doing exactly this, and a third
    spelling of the same decision is how one of them would eventually get it
    wrong. An individual unreadable part *file* is the tolerated case, and it
    is the one a real run produces.
    """
    unreadable: list[str] = []
    parts: list[dict] = []
    for path in list_json(run.dispositions_dir):
        document = _quietly(path)
        if isinstance(document, dict):
            parts.append(document)
        else:
            unreadable.append(path.stem)
    return parts, unreadable


def _divergence_lines(run: RunPaths) -> list[str]:
    """Section 4.1's predicted-vs-observed surface divergence.

    The observed total is computed the way `rb-triage-audit`'s Method computes
    it -- every predicted surface with at least one admitted candidate anywhere
    in the parts, plus every distinct `observed_surfaces` entry any part
    reported. Deliberately not a simpler count: a human reading a shortfall
    here and then reading the audit's deficiencies must see the same
    arithmetic, and two definitions of "observed" in one gate's reading surface
    would make the brief and the record it summarises disagree about a number
    that is supposed to be the same number.
    """
    lines = [DIVERGENCE_HEADER]
    objective = _mapping(_quietly(run.objective))
    parts, unreadable_parts = _disposition_parts(run)

    admitted: set[str] = set()
    for part in parts:
        for entry in _dicts(part.get("dispositions")):
            candidate_id = entry.get("candidate_id")
            if entry.get("disposition") == "admit" and isinstance(candidate_id, str):
                admitted.add(candidate_id)

    # A surface's name is what a human reads it by, so an unnamed one renders
    # as "?" rather than being dropped: dropping it would silently lower the
    # predicted total the reader is asked to compare against.
    predicted_names: list[str] = []
    confirmed: list[str] = []
    unconfirmed: list[str] = []
    for surface in _dicts(_mapping(objective.get("objective_review")).get("surfaces")):
        name = surface.get("name")
        name = name if isinstance(name, str) else "?"
        predicted_names.append(name)
        evidence = _strings(surface.get("evidence"))
        (confirmed if any(cid in admitted for cid in evidence) else unconfirmed).append(name)

    # Names already predicted are not counted twice. `observed_surfaces` is
    # specified as what a member saw that the prediction did *not* name, but a
    # member that restates a predicted surface is schema-legal, and counting it
    # would manufacture a surplus out of agreement.
    seen = set(predicted_names)
    surplus: list[str] = []
    for part in parts:
        for surface in _dicts(part.get("observed_surfaces")):
            name = surface.get("name")
            name = name if isinstance(name, str) else "?"
            if name not in seen:
                seen.add(name)
                surplus.append(name)

    predicted_count = objective.get("predicted_surface_count")
    # The document's own number, not len(predicted_names): they are supposed to
    # agree, `refs.check_objective` is what says so, and rendering the recorded
    # value is what lets a human see them disagree.
    shown = predicted_count if isinstance(predicted_count, int) else "?"
    observed = len(confirmed) + len(surplus)
    lines.append(f"  predicted by the objective pass from the corpus map: {shown}")
    lines.append(
        f"  observed by the fan-out across {len(parts)} disposition "
        f"part{'s' if len(parts) != 1 else ''}: {observed}"
    )
    lines.append(
        f"  predicted, but confirmed by no admitted candidate in any part ({len(unconfirmed)}): "
        + (", ".join(unconfirmed) if unconfirmed else "(none)")
    )
    lines.append(
        f"  observed in a slice and never predicted ({len(surplus)}): "
        + (", ".join(surplus) if surplus else "(none)")
    )
    lines.append(
        "  A shortfall is a loss -- a surface the map expected that nothing any slice ruled "
        "on confirmed -- and `rb-triage-audit` records it as a deficiency. A surplus is not: "
        "`predicted_surface_count` was a prediction against exactly this comparison, never a "
        "target the fan-out was meant to hit, so a surplus reads as how well the map described "
        "the corpus."
    )
    if not run.objective.is_file():
        lines.append(
            "  (00-objective.json is absent -- `triage-objective` has not run for this run, "
            "so there is no prediction to compare against)"
        )
    elif not objective:
        lines.append(
            "  (00-objective.json is present but could not be read -- "
            "`rubrica validate --stage triage-objective` names the defect)"
        )
    if not parts and not unreadable_parts:
        lines.append(
            "  (no disposition parts on disk -- `triage-rule` has not run, or the parts have "
            "been cleared away since; the observed total above is over nothing)"
        )
    if unreadable_parts:
        lines.append(
            "  (could not read the disposition part for: "
            + ", ".join(unreadable_parts)
            + " -- their surfaces and admits are missing from the totals above)"
        )
    return lines


def _slice_lines(run: RunPaths) -> list[str]:
    """The slice table and the split-group summary, from `00-slices.json`.

    One reader for both because they are one document, and reading it twice
    would let the two sections disagree about it.
    """
    document = _mapping(_quietly(run.slices))
    entries = _dicts(document.get("slices"))

    cap = document.get("cap_bytes")
    cap_note = f", cap {cap} bytes each" if isinstance(cap, int) else ""
    table = [f"{SLICES_HEADER} ({len(entries)}{cap_note})"]
    for entry in entries:
        slice_id = entry.get("id")
        slice_id = slice_id if isinstance(slice_id, str) else "?"
        candidate_count = len(_strings(entry.get("candidate_ids")))
        table.append(
            f"  {slice_id}: {candidate_count} candidate"
            f"{'s' if candidate_count != 1 else ''}, {entry.get('bytes', '?')} bytes"
            f" -- {entry.get('label', '')}"
        )
    if not run.slices.is_file():
        table.append(
            "  (00-slices.json is absent -- `triage-slices` has not run for this run, or the "
            "slice plan has been cleared away since)"
        )
    elif not entries:
        table.append(
            "  (00-slices.json is present but could not be read, or lists no slices -- "
            "`rubrica validate --stage triage-slices` names the defect)"
        )

    # Every group with a member outside the slice being read, and every slice
    # that holds part of it. Accumulated across the whole plan rather than
    # reported per slice: "held by 4 slices" is the fact a human acts on, and
    # a per-slice rendering would state it four times, once from each side.
    holders: dict[str, set[str]] = {}
    totals: dict[str, object] = {}
    for entry in entries:
        slice_id = entry.get("id")
        for provenance in _dicts(entry.get("provenance")):
            others = _strings(provenance.get("other_slices"))
            if not others:
                continue
            group = provenance.get("group")
            # str() on the key for the reason gate 0's reason_code key is
            # coerced: this is grouped on and then sorted, and a non-string one
            # both risks being unhashable and makes the sort compare str to int.
            group = str(group) if group else "?"
            held = holders.setdefault(group, set())
            if isinstance(slice_id, str):
                held.add(slice_id)
            held.update(others)
            totals.setdefault(group, provenance.get("in_group_total"))

    split = [f"{SPLIT_HEADER} ({len(holders)})"]
    if holders:
        for group in sorted(holders):
            slice_ids = sorted(holders[group])
            split.append(
                f"  {group}: {totals.get(group, '?')} candidates across {len(slice_ids)} "
                f"slices ({', '.join(slice_ids)})"
            )
        split.append(
            "  No member of a split group saw the whole group, so a near-duplicate spanning "
            "the split could be admitted twice or declined against a sibling that is not "
            "there. Gate 0 is the only place that residue can be acted on -- nothing "
            "downstream of `intake` reads the corpus again."
        )
    elif entries:
        split.append("  (none -- every group the slicer found fits inside one slice)")
    else:
        # Not "(none)": with no readable slice plan this section knows nothing
        # about how the groups were partitioned, and "every group fits inside
        # one slice" would be an announcement of absence made because the input
        # could not be read -- the exact shape `paths.list_dir` exists to stop
        # `check-refs` and `validate` doing, stated as a fact to the one human
        # who can act on a split.
        split.append(
            "  (unknown -- see the note above for why 00-slices.json was not read; without "
            "a slice plan, whether any group was split across slices is not established "
            "either way)"
        )
    return table + [""] + split


def _gate_0(run: RunPaths) -> str:
    if not run.triage.is_file():
        # A ruling held by the report as well as by
        # the check: a run minted through `intake --input` never had a triage
        # step, and that absence is not a finding.
        #
        # Branched on the catalogue rather than stated unconditionally, because
        # a missing triage record has two causes and this used to name only
        # one. On a run `survey` minted, the catalogue is right there and triage
        # simply has not run yet -- so telling that reader "this run was minted
        # through `intake --input`, which has no catalogue and no triage step at
        # all" was false, and false at precisely the moment they are waiting for
        # triage and asking this command whether it has landed.
        if run.catalogue.is_file():
            return (
                f"GATE 0 -- {run.root}\n\n"
                "No triage record for this run yet (00-triage.json is absent), but "
                "00-catalogue.json is present: this run was minted by `survey` and the "
                "triage family has not run, or has not reached `triage-seal`. Run the "
                "family through to `triage-seal` and read this brief again -- there is "
                "nothing to review at gate 0 until it lands.\n"
            )
        return (
            f"GATE 0 -- {run.root}\n\n"
            "No triage record for this run (00-triage.json is absent), and no "
            "00-catalogue.json either. This run was minted through `intake --input`, "
            "which has no catalogue and no triage step at all -- nothing to review "
            "at gate 0.\n"
        )

    triage = _mapping(_quietly(run.triage))
    catalogue = _mapping(_quietly(run.catalogue))
    candidates = {
        c["candidate_id"]: c
        for c in _dicts(catalogue.get("candidates"))
        # isinstance rather than `"candidate_id" in c`: an unhashable id (a
        # list) raises TypeError building this dict, the same shape
        # adopt_projection's own `used` map was measured raising.
        if isinstance(c.get("candidate_id"), str)
    }

    review = _mapping(triage.get("objective_review"))
    lines = [f"GATE 0 -- {run.root}", "", "Objective verdict"]
    lines.append(f"  declared objective: {review.get('declared_objective', '?')}")
    lines.append(
        "  supported by the surfaces found: " + ("yes" if review.get("supported") else "no")
    )
    if review.get("notes"):
        lines.append(f"  notes: {review['notes']}")
    recommended = _mapping(review.get("recommended_objective"))
    if recommended:
        lines.append(
            f"  recommended objective instead: {recommended.get('objective')} -- "
            f"{recommended.get('reason')}"
        )
    lines.append("")

    # Immediately after the verdict, because it is the only measure of the
    # corpus map that verdict was ruled from -- see section 4.1.
    lines.extend(_divergence_lines(run))
    lines.append("")

    dispositions = _dicts(triage.get("dispositions"))
    # intake.admit_sort_key, not a third spelling of the same sort. The lambda
    # this replaces (`d.get("priority", 10**9)`) shared the measured TypeError
    # of the two it is now unified with -- a string `priority` alongside an
    # integer one raised out of `sorted`, at exit 1 from a command whose whole
    # ruling is that it exits 0. Using the *pipeline's* order here has a second
    # benefit beyond not raising: the admits a human reads at gate 0 are listed
    # in the order intake will actually materialise them.
    admits = sorted(
        (d for d in dispositions if d.get("disposition") == "admit"),
        key=admit_sort_key,
    )
    lines.append(f"Admits, by priority ({len(admits)})")
    if admits:
        for d in admits:
            priority = d.get("priority")
            marker = f"[{priority}]" if priority is not None else "-"
            lines.append(f"  {marker} {d.get('candidate_id', '?')}: {d.get('reason', '')}")
    else:
        lines.append("  (none)")
    lines.append("")

    declines_by_code: dict[str, list[dict]] = {}
    for d in dispositions:
        if d.get("disposition") == "decline":
            code = d.get("reason_code")
            # str() on the key, not the bare value: `reason_code` is grouped on
            # and then sorted, and a non-string one both risks being unhashable
            # and makes `sorted(declines_by_code)` compare str to int.
            declines_by_code.setdefault(str(code) if code else "?", []).append(d)
    total_declines = sum(len(v) for v in declines_by_code.values())
    lines.append(f"Declines, by reason code ({total_declines})")
    if declines_by_code:
        for code in sorted(declines_by_code):
            entries = declines_by_code[code]
            lines.append(f"  {code} ({len(entries)}):")
            for d in entries:
                bytes_note = ""
                # `candidates.get(...)` raises TypeError on an unhashable
                # candidate_id, so the lookup is gated on the key being the
                # string the schema requires; a non-string one simply renders
                # without its byte count.
                cid = d.get("candidate_id")
                candidate = candidates.get(cid) if isinstance(cid, str) else None
                if candidate is not None:
                    bytes_note = f", {candidate.get('bytes', '?')} bytes"
                lines.append(
                    f"    - {d.get('candidate_id', '?')}{bytes_note}: {d.get('reason', '')}"
                )
    else:
        lines.append("  (none)")
    lines.append("")

    deficiencies = _dicts(triage.get("deficiencies"))
    projections_by_closes: dict[str, list[dict]] = {}
    for projection in _dicts(triage.get("projections")):
        raw_closes = projection.get("closes")
        # Strings only, from a real list. A non-string `closes` entry can be
        # unhashable (`setdefault` raises TypeError on a list), and one that is
        # not a string cannot match a `deficiency_id` that is, so nothing
        # renderable is lost by skipping it.
        for closes in raw_closes if isinstance(raw_closes, list) else []:
            if isinstance(closes, str):
                projections_by_closes.setdefault(closes, []).append(projection)

    lines.append(f"Open deficiencies and their projections ({len(deficiencies)})")
    if deficiencies:
        for deficiency in deficiencies:
            deficiency_id = deficiency.get("deficiency_id", "?")
            closed_by = deficiency.get("closed_by")
            status = f"closed by {closed_by}" if closed_by else "OPEN"
            lines.append(f"  {deficiency_id} [{status}]: {deficiency.get('statement', '')}")
            for projection in projections_by_closes.get(deficiency_id, []):
                projection_id = projection.get("projection_id", "?")
                confidence = _mapping(projection.get("method")).get("confidence", "?")
                satisfied_by = projection.get("satisfied_by")
                satisfied_note = f", satisfied by {satisfied_by}" if satisfied_by else ""
                wanted = _mapping(projection.get("wanted")).get("statement", "")
                lines.append(
                    f"      -> {projection_id} (confidence: {confidence}{satisfied_note}): {wanted}"
                )
    else:
        lines.append("  (none)")
    lines.append("")

    # Last: how the fan-out read the corpus, rather than what it ruled.
    lines.extend(_slice_lines(run))

    return "\n".join(lines) + "\n"


def _gate_1(run: RunPaths) -> str:
    lines = [f"GATE 1 -- {run.root}", ""]

    # The reconcile sweep, read before anything derived from it. Cross-pass
    # incoherence -- a later pass modelling what rb-reconcile-contradict recorded
    # `unresolved` -- has no mechanical check and must not be given a fake one:
    # whether a claim *supports* an element is semantic, which is the hole layer 2
    # is forbidden to paper over. What follows is an aggregate: counts and a
    # resolution tally, not the contradictions themselves. It goes first because a
    # non-zero `unresolved` is what should send a reader into 01-contradictions/
    # before reading the world model built on top of it -- this report points at
    # the parts, it does not reproduce them.
    cover = _mapping(_quietly(run.subjects))
    subjects = _dicts(cover.get("subjects"))
    covered = {
        cid
        for subject in subjects
        # isinstance rather than a truthiness check, and for the same reason gate
        # 0's candidate map above carries one: this builds a *set*, so an
        # unhashable member -- `"claims": [["c-1"]]`, `[{"id": "c-1"}]`, both
        # readable JSON and both what a hand-edit at this gate produces -- raises
        # `TypeError: unhashable type` out of the comprehension. Measured at exit
        # 1 with a fabricated `[internal]` finding, which is the third instance in
        # this module of the shape adopt_projection's `used` map was measured
        # raising. `_as_list` guards the container; only this guards the members,
        # and a truthy element can still be a dict.
        for cid in _as_list(subject.get("claims"))
        if isinstance(cid, str)
    }
    lines.append("Reconcile sweep")
    if subjects:
        lines.append(f"  {len(subjects)} subjects over {len(covered)} claims")
    else:
        lines.append("  (no subject cover yet; nothing to report)")

    swept, found = 0, []
    for path in list_json(run.contradictions_dir):
        part = _mapping(_quietly(path))
        swept += 1
        found.extend(_dicts(part.get("contradictions")))
    # Both numbers, always. "12 subjects swept, 0 contradictions" is a strong
    # claim about the corpus and has to be legible as one -- a brief that printed
    # only a non-empty list would render a sweep that found nothing anywhere as
    # silence, which is the reading this stage most needs a human to question.
    lines.append(f"  {swept} subjects swept, {len(found)} contradictions recorded")
    if found:
        tally: dict[str, int] = {}
        for contradiction in found:
            resolution = contradiction.get("resolution")
            key = resolution if isinstance(resolution, str) else "(no resolution)"
            tally[key] = tally.get(key, 0) + 1
        # unresolved first, and shown as a zero whenever this branch renders at
        # all: it is the value under the most pressure to be dropped by a pass
        # that wants to look decisive, so a sweep that recorded contradictions and
        # resolved every one should be visibly odd rather than merely unremarked.
        # Scoped to the branch on purpose -- a run with *no* contradictions at all
        # never reaches here, and its reading is the "0 contradictions recorded"
        # line above, which is the stronger claim of the two anyway.
        ordered = ["unresolved", *sorted(k for k in tally if k != "unresolved")]
        lines.append("  " + ", ".join(f"{key}: {tally.get(key, 0)}" for key in ordered))
    lines.append("")

    lines.append("Claim utilisation, per input")
    utilisation = claim_utilisation(run)
    if utilisation["artifacts"]:
        for entry in utilisation["artifacts"]:
            lines.append(
                f"  {entry['artifact_id']}: {entry['cited']}/{entry['total']} claims cited "
                f"({entry['percent']}%)"
            )
    else:
        lines.append("  (no world model yet; nothing to report)")
    lines.append("")

    lines.append("Implied suite size")
    size = implied_size(run)
    if size is None:
        # None means either "no world model yet" or "one exists but could not
        # be read" (sizing.implied_size's own guard) -- this report cannot
        # tell those apart without re-reading what implied_size already
        # decided not to raise on, so it says both rather than picking one
        # and being wrong half the time.
        lines.append("  (implied size unavailable -- no world model yet, or it could not be read)")
    else:
        binding_note = (
            " -- ABOVE the ceiling; this target may want splitting across runs"
            if size["ceiling_binding"]
            else ""
        )
        # blocked_note makes the arithmetic on this line actually add up when
        # coverage has narrowed the denominator: capability_cells + hop_slots
        # alone is the *pre-deduction* total, and printing "= denominator"
        # right after it without showing the subtraction reads as broken math
        # to the human this line exists for.
        blocked_note = f" - {size['blocked_cells']} blocked" if size["blocked_cells"] else ""
        lines.append(
            f"  {size['capability_cells']} capability cells + {size['hop_slots']} hop-depth "
            f"slots{blocked_note} ({size['basis']}) = {size['denominator']} -> "
            f"implied {size['implied']}, ceiling {size['ceiling']}{binding_note}"
        )
    lines.append("")

    world = _mapping(_quietly(run.world_model))
    gaps = _dicts(world.get("gaps"))
    lines.append(f"World-model gaps ({len(gaps)})")
    if gaps:
        for gap in gaps:
            lines.append(f"  {gap.get('id', '?')}: {gap.get('unknown', '')}")
    else:
        lines.append("  (none)")
    lines.append("")

    triage = _quietly(run.triage)
    lines.append(
        "Triage's open deficiencies -- read against the gaps above. This pairing is "
        "semantic, so it is a human's call and this rendering is the "
        "whole instrument for making it, not a check"
    )
    if triage is None:
        lines.append("  (no triage record for this run)")
    else:
        open_deficiencies = [
            d for d in _dicts(_mapping(triage).get("deficiencies")) if not d.get("closed_by")
        ]
        if open_deficiencies:
            for deficiency in open_deficiencies:
                lines.append(
                    f"  {deficiency.get('deficiency_id', '?')}: {deficiency.get('statement', '')}"
                )
        else:
            lines.append("  (none open)")

    return "\n".join(lines) + "\n"


def _gate_2(run: RunPaths) -> str:
    lines = [f"GATE 2 -- {run.root}", ""]
    coverage = _quietly(run.coverage_latest)
    if coverage is None:
        lines.append("No coverage report yet (03-coverage/latest.json is absent).")
        return "\n".join(lines) + "\n"

    coverage = _mapping(coverage)
    lines.append(f"Coverage verdict: {coverage.get('verdict', '?')}")
    capability_matrix = _mapping(coverage.get("capability_matrix"))
    goal_matrix = _mapping(coverage.get("goal_matrix"))
    lines.append(
        f"  capability cells: {capability_matrix.get('covered', '?')}/"
        f"{capability_matrix.get('total', '?')}"
    )
    lines.append(f"  goals: {goal_matrix.get('covered', '?')}/{goal_matrix.get('total', '?')}")
    progress = _mapping(coverage.get("progress"))
    lines.append(
        f"  round {coverage.get('round', '?')}: {progress.get('new_cells_this_round', '?')} new "
        f"cells this round, {progress.get('rounds_without_progress', '?')} rounds without progress"
    )
    # len() over the raw value would count a string's characters as holes, so
    # the count is of a real list or nothing.
    raw_holes = coverage.get("holes")
    lines.append(f"  open holes: {len(raw_holes) if isinstance(raw_holes, list) else 0}")

    size = implied_size(run)
    if size is not None:
        binding_note = ", BINDING" if size["ceiling_binding"] else ""
        lines.append(
            f"  implied suite size: {size['implied']} (ceiling {size['ceiling']}{binding_note})"
        )

    return "\n".join(lines) + "\n"


def _gate_3(run: RunPaths) -> str:
    lines = [f"GATE 3 -- {run.root}", ""]
    tallies: dict[str, int] = {}
    for path in list_json(run.verdicts_dir):
        payload = _quietly(path)
        if isinstance(payload, dict):
            # str() on the key: `tallies` is grouped on and then `sorted`, so a
            # non-string verdict would either be unhashable or make the sort
            # compare str to int -- the same reason gate 0's reason_code key is
            # coerced.
            verdict = payload.get("verdict")
            verdict = str(verdict) if verdict else "?"
            tallies[verdict] = tallies.get(verdict, 0) + 1

    total = sum(tallies.values())
    lines.append(f"Verdict tallies ({total} instance{'s' if total != 1 else ''} challenged)")
    if tallies:
        for verdict in sorted(tallies):
            lines.append(f"  {verdict}: {tallies[verdict]}")
    else:
        lines.append("  (none)")

    return "\n".join(lines) + "\n"
