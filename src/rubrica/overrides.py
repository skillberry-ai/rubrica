"""`rubrica overrule`: a human's gate-0 ruling on one candidate, recorded where the seal reads it.

Gate 0 is the one gate whose mistakes nothing downstream can recover -- a
candidate triage declines is gone as completely as if the corpus never held it
-- and the design has always said a human there may overrule triage one
candidate at a time. Until this module there was no way to: a hand-edit of
00-triage.json is erased by the next `triage-seal`, and a second disposition
for the same candidate in 00-adoptions.json makes the seal refuse.

So an override is written to the same human-authored file adoptions live in,
under its own `overrides` list, and `triage-seal` applies it in place of the
part's disposition. Three properties follow, and each is the reason for a
choice below:

- **The parts are never touched.** What triage decided stays on disk in
  00-dispositions/, so the human's ruling and the model's can always be set
  side by side -- the observability this experiment depends on.
- **Nothing here seals.** Like `adopt-projection`, this writes the human's
  record and leaves assembly to `triage-seal`, so there is one code path that
  builds 00-triage.json.
- **Refused once intake has run.** The manifest's inputs are materialised from
  the sealed admits, and `refs.check_admitted_inputs` holds the two to each
  other; changing an admit after that would make the run disagree with itself.
  A ruling that late belongs in a new run.

A malformed 00-adoptions.json is a `UsageError` (exit 2), for the reason
`waivers.load` gives: a person wrote it, so there is no stage to hand a repair
prompt to.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from rubrica.artifacts import ArtifactError, append_decision, read_json, write_json
from rubrica.errors import UsageError
from rubrica.findings import format_findings
from rubrica.paths import RunPaths
from rubrica.seal import HUMAN_DECLINE_CODES
from rubrica.validate import validate_artifact

ACTIONS = ("admit", "decline")


def _read_object(path: Path, what: str) -> dict:
    try:
        document = read_json(path)
    except ArtifactError as exc:
        raise UsageError(f"cannot read {what}: {exc}") from exc
    if not isinstance(document, dict):
        raise UsageError(f"{path}: {what} must be a JSON object")
    return document


def load_adoptions(run: RunPaths) -> dict:
    """00-adoptions.json, schema-validated, or a fresh empty document when absent."""
    if not run.adoptions.is_file():
        return {"adoptions": []}
    document = _read_object(run.adoptions, "the adoptions file")
    findings = validate_artifact(run.adoptions, "adoptions")
    if findings:
        raise UsageError(f"unusable adoptions file: {run.adoptions}:\n{format_findings(findings)}")
    return document


def triage_decisions(run: RunPaths) -> dict[str, str]:
    """Each candidate's disposition as triage's own parts state it -- never the sealed record.

    The sealed record already carries any override, so reading it would make an
    override look like triage's own judgment the second time a human looked.
    """
    decisions: dict[str, str] = {}
    for slice_id in run.slice_ids_with_parts():
        path = run.disposition_part(slice_id)
        part = _read_object(path, f"the dispositions part for slice {slice_id!r}")
        entries = part.get("dispositions")
        if not isinstance(entries, list):
            raise UsageError(f"{path}: has no dispositions array")
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("candidate_id"), str):
                decisions[entry["candidate_id"]] = str(entry.get("disposition"))
    return decisions


def _admissible(run: RunPaths) -> dict[str, bool]:
    catalogue = _read_object(run.catalogue, "the catalogue")
    candidates = catalogue.get("candidates")
    return {
        c["candidate_id"]: c.get("admissible") is not False
        for c in (candidates if isinstance(candidates, list) else [])
        if isinstance(c, dict) and isinstance(c.get("candidate_id"), str)
    }


def _clean_reason(reason: str) -> str:
    text = reason.strip()
    if not text:
        raise UsageError("a reason is required: it is what the override and decisions.md record")
    if "\n" in text or "\r" in text:
        raise UsageError("the reason must be one line: decisions.md holds one ruling per line")
    return text


def overrule(
    run: RunPaths,
    candidates: list[str],
    *,
    action: str | None,
    reason: str,
    reason_code: str | None = None,
    clear: bool = False,
    now: datetime | None = None,
) -> list[str]:
    """Record (or, with `clear`, remove) a human ruling on each candidate; return one line each.

    All-or-nothing: every candidate is checked before anything is written, so a
    refusal for the third of five leaves the file exactly as it was.
    """
    # Imported here, as waivers.record does, so manifest stays out of this
    # module's import graph for callers that only read.
    from rubrica.manifest import utc_stamp

    text = _clean_reason(reason)
    if run.manifest.exists():
        raise UsageError(
            "gate 0 has already been approved: intake has minted manifest.json from the "
            "sealed triage record, so an override now would make the run disagree with "
            "itself. Start a new run from the same corpus to rule differently."
        )
    if not candidates:
        raise UsageError("name at least one --candidate")
    if clear:
        if action is not None or reason_code is not None:
            raise UsageError("--clear takes no --admit/--decline and no --reason-code")
    else:
        if action not in ACTIONS:
            raise UsageError("choose --admit or --decline (or --clear to undo an override)")
        if action == "decline" and reason_code not in HUMAN_DECLINE_CODES:
            raise UsageError(
                f"a decline needs --reason-code, one of {', '.join(HUMAN_DECLINE_CODES)}"
            )
        if action == "admit" and reason_code is not None:
            raise UsageError("an admit takes no --reason-code")

    document = load_adoptions(run)
    triage = triage_decisions(run)
    admissible = _admissible(run)
    adopted = {a.get("candidate_id") for a in document.get("adoptions", [])}
    overrides = list(document.get("overrides", []))
    by_candidate = {o["candidate_id"]: o for o in overrides}

    seen: set[str] = set()
    for cid in candidates:
        if cid in seen:
            raise UsageError(f"candidate {cid!r} is named twice")
        seen.add(cid)
        if cid in adopted:
            raise UsageError(
                f"{cid!r} was admitted by adopting a projection, which is already a human "
                "ruling; there is no triage decision to overrule"
            )
        if cid not in triage:
            raise UsageError(f"no triage part rules on {cid!r}, so there is nothing to overrule")
        if clear:
            if cid not in by_candidate:
                raise UsageError(f"{cid!r} has no override to clear")
            continue
        if triage[cid] == action:
            raise UsageError(
                f"triage already decided {action} for {cid!r}; use --clear to undo an override"
            )
        if cid in by_candidate:
            raise UsageError(f"{cid!r} is already overridden to {action}")
        if action == "admit" and not admissible.get(cid, True):
            raise UsageError(
                f"{cid!r} is marked inadmissible in the catalogue, so it cannot be admitted"
            )

    stamp = utc_stamp(now)
    lines: list[str] = []
    if clear:
        overrides = [o for o in overrides if o["candidate_id"] not in seen]
        for cid in candidates:
            lines.append(f"{cid}: override cleared, back to triage's {triage[cid]}")
    else:
        for cid in candidates:
            disposition = {
                "candidate_id": cid,
                "disposition": action,
                "reason": text,
                "authority": "human",
            }
            if reason_code is not None:
                disposition["reason_code"] = reason_code
            overrides.append(
                {
                    "candidate_id": cid,
                    "disposition": disposition,
                    "replaces": triage[cid],
                    "recorded_at": stamp,
                }
            )
            code = f" ({reason_code})" if reason_code else ""
            lines.append(f"{cid}: {triage[cid]} -> {action}{code}")
    overrides.sort(key=lambda o: o["candidate_id"])

    if "schema_version" not in document:
        document["schema_version"] = "0.1"
    if "run_id" not in document:
        catalogue = _read_object(run.catalogue, "the catalogue")
        document["run_id"] = catalogue.get("run_id")
    document.setdefault("adoptions", [])
    if overrides:
        document["overrides"] = overrides
    else:
        document.pop("overrides", None)

    # The override first, then the log line -- waivers.record's order, and its
    # reason: a ruling that exists without its log line is recoverable by reading
    # the file; a log line for a ruling that was never written is a false record.
    write_json(run.adoptions, document)
    verb = "cleared override" if clear else "overrule"
    for line in lines:
        try:
            append_decision(run.decisions, f"- {stamp} {verb} at gate 0: {line} -- {text}")
        except OSError as exc:
            raise UsageError(
                f"the override is written to {run.adoptions.name} but decisions.md could not "
                f"be appended ({exc}); re-record it with `rubrica decide`"
            ) from exc
    return lines
