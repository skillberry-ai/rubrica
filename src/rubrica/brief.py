"""`gate-brief`: the human surface at all four human gates.

Design spec section 11. A composer, not a new analysis -- it renders reports
that already exist (`utilisation.claim_utilisation`, coverage, verdicts) plus
`sizing.implied_size`, in the shape each gate's human decision actually needs:

- **Gate 0** is this build's new one, and it is what decides whether gate 0 is
  holdable at all. It leads with the objective verdict -- supported or not --
  because that is the single fact most likely to make a tired reader overturn
  the whole triage record, and a reader who stops after ten lines must have
  seen it. Admits by priority, declines grouped by reason code, and every open
  deficiency beside the projection that would close it follow.
- **Gate 1** puts the world model's gaps next to the triage record's open
  deficiencies -- section 10's pairing, which is deliberately *not* a
  mechanical check (matching gap prose to decline prose is semantic, the same
  hole `check-refs` leaves for a claim's support), so this rendering is the
  whole instrument for a human making that call. Claim utilisation and the
  implied suite size are reported alongside it.
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
from rubrica.paths import RunPaths, list_json
from rubrica.sizing import implied_size
from rubrica.utilisation import claim_utilisation

GATES = (0, 1, 2, 3)


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


def _gate_0(run: RunPaths) -> str:
    if not run.triage.is_file():
        # Design spec section 7.1's ruling, held by the report as well as by
        # the check: a run minted through `intake --input` never had a triage
        # step, and that absence is not a finding.
        return (
            f"GATE 0 -- {run.root}\n\n"
            "No triage record for this run (00-triage.json is absent). This run "
            "was minted through `intake --input`, which has no catalogue and no "
            "triage step at all -- nothing to review at gate 0.\n"
        )

    triage = _quietly(run.triage) or {}
    catalogue = _quietly(run.catalogue) or {}
    candidates = {
        c["candidate_id"]: c
        for c in catalogue.get("candidates", [])
        if isinstance(c, dict) and "candidate_id" in c
    }

    review = triage.get("objective_review") or {}
    lines = [f"GATE 0 -- {run.root}", "", "Objective verdict"]
    lines.append(f"  declared objective: {review.get('declared_objective', '?')}")
    lines.append(
        "  supported by the surfaces found: " + ("yes" if review.get("supported") else "no")
    )
    if review.get("notes"):
        lines.append(f"  notes: {review['notes']}")
    recommended = review.get("recommended_objective")
    if recommended:
        lines.append(
            f"  recommended objective instead: {recommended.get('objective')} -- "
            f"{recommended.get('reason')}"
        )
    lines.append("")

    dispositions = triage.get("dispositions") or []
    admits = sorted(
        (d for d in dispositions if isinstance(d, dict) and d.get("disposition") == "admit"),
        key=lambda d: d.get("priority", 10**9),
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
        if isinstance(d, dict) and d.get("disposition") == "decline":
            declines_by_code.setdefault(d.get("reason_code") or "?", []).append(d)
    total_declines = sum(len(v) for v in declines_by_code.values())
    lines.append(f"Declines, by reason code ({total_declines})")
    if declines_by_code:
        for code in sorted(declines_by_code):
            entries = declines_by_code[code]
            lines.append(f"  {code} ({len(entries)}):")
            for d in entries:
                bytes_note = ""
                candidate = candidates.get(d.get("candidate_id"))
                if candidate is not None:
                    bytes_note = f", {candidate.get('bytes', '?')} bytes"
                lines.append(
                    f"    - {d.get('candidate_id', '?')}{bytes_note}: {d.get('reason', '')}"
                )
    else:
        lines.append("  (none)")
    lines.append("")

    deficiencies = triage.get("deficiencies") or []
    projections_by_closes: dict[str, list[dict]] = {}
    for projection in triage.get("projections") or []:
        if not isinstance(projection, dict):
            continue
        for closes in projection.get("closes") or []:
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
                confidence = (projection.get("method") or {}).get("confidence", "?")
                satisfied_by = projection.get("satisfied_by")
                satisfied_note = f", satisfied by {satisfied_by}" if satisfied_by else ""
                wanted = (projection.get("wanted") or {}).get("statement", "")
                lines.append(
                    f"      -> {projection_id} (confidence: {confidence}{satisfied_note}): {wanted}"
                )
    else:
        lines.append("  (none)")

    return "\n".join(lines) + "\n"


def _gate_1(run: RunPaths) -> str:
    lines = [f"GATE 1 -- {run.root}", "", "Claim utilisation, per input"]
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

    world = _quietly(run.world_model) or {}
    gaps = world.get("gaps") or []
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
        "semantic (spec section 10), so it is a human's call and this rendering is the "
        "whole instrument for making it, not a check"
    )
    if triage is None:
        lines.append("  (no triage record for this run)")
    else:
        open_deficiencies = [
            d for d in (triage.get("deficiencies") or []) if not d.get("closed_by")
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

    lines.append(f"Coverage verdict: {coverage.get('verdict', '?')}")
    capability_matrix = coverage.get("capability_matrix") or {}
    goal_matrix = coverage.get("goal_matrix") or {}
    lines.append(
        f"  capability cells: {capability_matrix.get('covered', '?')}/"
        f"{capability_matrix.get('total', '?')}"
    )
    lines.append(f"  goals: {goal_matrix.get('covered', '?')}/{goal_matrix.get('total', '?')}")
    progress = coverage.get("progress") or {}
    lines.append(
        f"  round {coverage.get('round', '?')}: {progress.get('new_cells_this_round', '?')} new "
        f"cells this round, {progress.get('rounds_without_progress', '?')} rounds without progress"
    )
    lines.append(f"  open holes: {len(coverage.get('holes') or [])}")

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
            verdict = payload.get("verdict") or "?"
            tallies[verdict] = tallies.get(verdict, 0) + 1

    total = sum(tallies.values())
    lines.append(f"Verdict tallies ({total} instance{'s' if total != 1 else ''} challenged)")
    if tallies:
        for verdict in sorted(tallies):
            lines.append(f"  {verdict}: {tallies[verdict]}")
    else:
        lines.append("  (none)")

    return "\n".join(lines) + "\n"
