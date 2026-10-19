"""Gate 1's human rulings: `rubrica rule`, and the functions that apply them.

Gate 1 reviews the world model, and until this module the only way to correct it
was to hand-edit a reconcile pass's partial -- which overwrites the model's value
with nothing left to show what it was, and is erased the next time that pass
runs. A ruling is written instead to `01-rulings.json`, a file only a human
writes, and applied by code:

- `reconcile-seal` applies contradiction resolutions, capability bindings, gap
  `blocks` and service regroupings to `01-world-model.json`;
- `synthesise-interfaces` and `check-refs` read the regrouped services through
  `effective_services`, so the interface documents follow the human's grouping;
- the six passes that model contradictions read the file when they are re-run,
  because a resolution only changes the world model if the passes that modelled
  the old one model the new one.

The partials are never edited, so what a pass decided and what the human decided
both stay on disk -- the property gate 0's overrides keep for the same reason.

The `apply_*` functions are pure: they take a pass's records and the rulings and
return the effective records plus a finding for every ruling they cannot apply,
reported against `01-rulings.json` (exit 1, the triage seal's precedent for an
override it cannot apply). `rule` and `clear` are the writers, and refuse a bad
request at exit 2 before anything is written.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime

from rubrica.artifacts import ArtifactError, append_decision, read_json, write_json
from rubrica.errors import UsageError
from rubrica.findings import Finding, format_findings
from rubrica.paths import RunPaths, list_json
from rubrica.validate import validate_artifact

RESOLUTIONS = ("unresolved", "preferred_a", "preferred_b", "both_possible")
BLOCKABLE = ("propose", "score", "instantiate", "challenge", "emit", "smoke")
KINDS = ("contradictions", "gaps", "capabilities", "services")

# The passes whose prompts model a contradiction's resolution, in dispatch order.
# A contradiction ruling reaches the world model only once these have re-run.
CONTRADICTION_READERS = (
    "reconcile-capabilities",
    "reconcile-outcomes",
    "reconcile-entities",
    "reconcile-goals",
    "reconcile-gaps",
    "reconcile-services",
)


# -- reading ---------------------------------------------------------------


def load(run: RunPaths) -> dict:
    """The rulings, tolerantly: `{}` when absent or unreadable. For reports, never gates."""
    try:
        document = read_json(run.rulings) if run.rulings.is_file() else {}
    except (ArtifactError, OSError):
        return {}
    return document if isinstance(document, dict) else {}


def load_strict(run: RunPaths) -> dict:
    """The rulings, schema-validated, or an empty document when absent.

    A malformed file is a `UsageError` (exit 2): a person wrote it, so there is no
    stage to hand a repair prompt to -- `waivers.load`'s reason.
    """
    if not run.rulings.is_file():
        return {"schema_version": "0.1"}
    try:
        document = read_json(run.rulings)
    except ArtifactError as exc:
        raise UsageError(f"cannot read the rulings file: {exc}") from exc
    if not isinstance(document, dict):
        raise UsageError(f"{run.rulings}: the rulings file must be a JSON object")
    findings = validate_artifact(run.rulings, "rulings")
    if findings:
        raise UsageError(f"unusable rulings file: {run.rulings}:\n{format_findings(findings)}")
    return document


def _entries(rulings: dict, kind: str) -> list[dict]:
    value = rulings.get(kind)
    return [e for e in value if isinstance(e, dict)] if isinstance(value, list) else []


def accepted_gaps(rulings: dict) -> set[str]:
    """Gap ids a human ruled do not stop the run."""
    return {
        e["id"]
        for e in _entries(rulings, "gaps")
        if e.get("ruling") == "accept" and isinstance(e.get("id"), str)
    }


def blocking_gaps(gaps: list[dict], rulings: dict) -> list[dict]:
    """The gaps that still stop a stage once the human's accepts are taken out."""
    accepted = accepted_gaps(rulings)
    return [g for g in gaps if g.get("blocks") and g.get("id") not in accepted]


# -- applying --------------------------------------------------------------


def _finding(run: RunPaths, pointer: str, message: str) -> Finding:
    return Finding(run.rulings, "rulings", pointer, message)


def apply_contradictions(
    run: RunPaths, contradictions: list[dict], rulings: dict
) -> tuple[list[dict], list[Finding]]:
    """Each contradiction with a human's resolution in place of the pass's."""
    out = [dict(c) for c in contradictions]
    by_id = {c.get("id"): c for c in out}
    findings = []
    for index, entry in enumerate(_entries(rulings, "contradictions")):
        target = by_id.get(entry.get("id"))
        if target is None:
            findings.append(
                _finding(
                    run,
                    f"/contradictions/{index}",
                    f"ruling names contradiction {entry.get('id')!r}, which no part records",
                )
            )
            continue
        target["resolution"] = entry.get("resolution")
    return out, findings


def apply_gaps(run: RunPaths, gaps: list[dict], rulings: dict) -> tuple[list[dict], list[Finding]]:
    """Each gap with a human's `blocks` in place of the pass's. An accept changes nothing here.

    `blocks` keeps `minItems: 1` in the world model's schema, so "this gap does not
    stop the run" cannot be written into the gap itself; it is read from the
    rulings file through `accepted_gaps`.
    """
    out = [dict(g) for g in gaps]
    by_id = {g.get("id"): g for g in out}
    findings = []
    for index, entry in enumerate(_entries(rulings, "gaps")):
        target = by_id.get(entry.get("id"))
        if target is None:
            findings.append(
                _finding(
                    run,
                    f"/gaps/{index}",
                    f"ruling names gap {entry.get('id')!r}, which no part records",
                )
            )
            continue
        if entry.get("ruling") == "blocks":
            target["blocks"] = list(entry.get("blocks") or [])
    return out, findings


def apply_capabilities(
    run: RunPaths, capabilities: list[dict], rulings: dict, tools: set[str] | None
) -> tuple[list[dict], list[Finding]]:
    """Each capability with a human's binding in place of the pass's.

    `tools` is the declared tool set (the effective services' tool names), or None
    when the run declares none -- a binding to a tool nothing declares would be a
    test against a call the target does not offer.
    """
    out = [dict(c) for c in capabilities]
    by_id = {c.get("id"): c for c in out}
    findings = []
    for index, entry in enumerate(_entries(rulings, "capabilities")):
        pointer = f"/capabilities/{index}"
        target = by_id.get(entry.get("id"))
        if target is None:
            findings.append(
                _finding(
                    run,
                    pointer,
                    f"ruling names capability {entry.get('id')!r}, which no part records",
                )
            )
            continue
        if entry.get("ruling") != "bind":
            continue
        binding = entry.get("binding") or {}
        tool = binding.get("tool")
        if tools is None or tool not in tools:
            findings.append(
                _finding(
                    run,
                    pointer,
                    f"capability {entry.get('id')!r} is bound to tool {tool!r}, which no service "
                    "in this run declares",
                )
            )
            continue
        target["binding"] = {"tool": tool, "fixed_args": dict(binding.get("fixed_args") or {})}
    return out, findings


def effective_services(
    run: RunPaths, services: list[dict] | None, rulings: dict
) -> tuple[list[dict] | None, list[Finding]]:
    """The pass's service grouping with the human's regrouping operations applied in order.

    None stays None: a run whose services pass never ran has no grouping to
    regroup, and a regrouping ruling then names services nothing declares.
    """
    entries = _entries(rulings, "services")
    if services is None:
        findings = [
            _finding(run, f"/services/{i}", "a service ruling, but this run has no services part")
            for i, _ in enumerate(entries)
        ]
        return None, findings
    if not entries:
        # The pass's list exactly as written, malformed members included: a
        # regrouping that filtered them would hide the "not an object" finding
        # synthesise-interfaces and check_services owe the pass.
        return services, []
    out = copy.deepcopy(services)
    findings: list[Finding] = []

    def find(service_id):
        return next((s for s in out if isinstance(s, dict) and s.get("id") == service_id), None)

    for index, entry in enumerate(entries):
        pointer = f"/services/{index}"
        op = entry.get("op")
        if op == "move_tool":
            source = next(
                (
                    s
                    for s in out
                    if isinstance(s, dict)
                    and any(
                        isinstance(t, dict) and t.get("name") == entry.get("tool")
                        for t in s.get("tools", [])
                    )
                ),
                None,
            )
            target = find(entry.get("to"))
            if source is None or target is None:
                findings.append(
                    _finding(
                        run,
                        pointer,
                        f"cannot move tool {entry.get('tool')!r} to {entry.get('to')!r}: "
                        "no service declares that tool, or no service has that id",
                    )
                )
                continue
            if source is target:
                continue
            tool = next(t for t in source["tools"] if t.get("name") == entry.get("tool"))
            source["tools"] = [t for t in source["tools"] if t is not tool]
            target["tools"] = [*target.get("tools", []), tool]
            if not source["tools"]:
                out = [s for s in out if s is not source]
        elif op == "merge":
            source, target = find(entry.get("service")), find(entry.get("into"))
            if source is None or target is None or source is target:
                findings.append(
                    _finding(
                        run,
                        pointer,
                        f"cannot merge {entry.get('service')!r} into "
                        f"{entry.get('into')!r}: both must be different, existing services",
                    )
                )
                continue
            target["tools"] = [*target.get("tools", []), *source.get("tools", [])]
            target["signals"] = [*target.get("signals", []), *source.get("signals", [])]
            out = [s for s in out if s is not source]
        elif op == "split":
            source = find(entry.get("service"))
            names = set(entry.get("tools") or [])
            moving = [t for t in (source or {}).get("tools", []) if t.get("name") in names]
            if (
                source is None
                or len(moving) != len(names)
                or len(moving) == len(source.get("tools", []))
            ):
                findings.append(
                    _finding(
                        run,
                        pointer,
                        f"cannot split {entry.get('service')!r}: every named tool must "
                        "be one of its tools, and at least one tool must stay",
                    )
                )
                continue
            if find(entry.get("new_id")) is not None:
                findings.append(
                    _finding(run, pointer, f"service id {entry.get('new_id')!r} already exists")
                )
                continue
            source["tools"] = [t for t in source["tools"] if t.get("name") not in names]
            out.append(
                {
                    "id": entry.get("new_id"),
                    "statement": entry.get("statement"),
                    "tools": moving,
                    # The source's signals are what made these tools a service at
                    # all; the human's split says they are a different one, not
                    # that the evidence for a backend vanished.
                    "signals": list(source.get("signals", [])),
                }
            )
    return out, findings


def declared_tools(services: list[dict] | None) -> set[str] | None:
    if services is None:
        return None
    return {
        t["name"] for s in services for t in s.get("tools", []) if isinstance(t.get("name"), str)
    }


# -- the parts a ruling is checked against ------------------------------------


def _part_list(path, key: str) -> list[dict]:
    try:
        document = read_json(path)
    except ArtifactError as exc:
        raise UsageError(f"cannot read {path.name}: {exc}") from exc
    value = document.get(key) if isinstance(document, dict) else None
    if not isinstance(value, list):
        raise UsageError(f"{path}: has no {key} array to rule on")
    return [v for v in value if isinstance(v, dict)]


def _contradictions(run: RunPaths) -> list[dict]:
    out: list[dict] = []
    for path in list_json(run.contradictions_dir):
        out.extend(_part_list(path, "contradictions"))
    return out


def _services(run: RunPaths) -> list[dict] | None:
    return _part_list(run.services_part, "services") if run.services_part.is_file() else None


# -- writing ---------------------------------------------------------------


def _clean_reason(reason: str) -> str:
    text = (reason or "").strip()
    if not text:
        raise UsageError("a reason is required: it is what the ruling and decisions.md record")
    if "\n" in text or "\r" in text:
        raise UsageError("the reason must be one line: decisions.md holds one ruling per line")
    return text


def _refuse_if_closed(run: RunPaths) -> None:
    if run.batches_dir.exists():
        raise UsageError(
            "gate 1 is past: propose has already read the world model (02-batches/ exists), "
            "so a ruling now would leave the coverage built on it describing a different "
            "model. Start a new run to rule differently."
        )


def rule(
    run: RunPaths,
    *,
    kind: str,
    entry: dict,
    reason: str,
    now: datetime | None = None,
) -> str:
    """Record one ruling of `kind`; return the line logged to decisions.md.

    `entry` carries the ruling's own fields (id plus resolution, ruling, blocks,
    binding, or a service op). Checked against the parts -- never the sealed world
    model, which already carries earlier rulings -- before anything is written.
    """
    from rubrica.manifest import utc_stamp

    if kind not in KINDS:
        raise UsageError(f"unknown ruling kind {kind!r}")
    text = _clean_reason(reason)
    _refuse_if_closed(run)
    document = load_strict(run)
    rulings = _entries(document, kind)
    stamp = utc_stamp(now)
    ruling = {**entry, "reason": text, "recorded_at": stamp}

    if kind == "contradictions":
        current = {c.get("id"): c for c in _contradictions(run)}
        cid = entry["id"]
        if cid not in current:
            raise UsageError(f"no contradiction part records {cid!r}")
        if entry["resolution"] not in RESOLUTIONS:
            raise UsageError(f"resolution must be one of {', '.join(RESOLUTIONS)}")
        was = current[cid].get("resolution")
        if was == entry["resolution"]:
            raise UsageError(
                f"the pass already resolved {cid!r} as {was}; use --clear to undo a ruling"
            )
        ruling["replaces"] = was
        summary = f"contradiction {cid}: {was} -> {entry['resolution']}"
    elif kind == "gaps":
        current = {g.get("id"): g for g in _part_list(run.gaps_part, "gaps")}
        gid = entry["id"]
        if gid not in current:
            raise UsageError(f"01-gaps.json records no gap {gid!r}")
        was = list(current[gid].get("blocks") or [])
        if entry["ruling"] == "blocks":
            blocks = list(dict.fromkeys(entry.get("blocks") or []))
            if not blocks or any(b not in BLOCKABLE for b in blocks):
                raise UsageError(f"--blocks takes one or more of {', '.join(BLOCKABLE)}")
            if blocks == was:
                raise UsageError(f"gap {gid!r} already blocks {', '.join(was)}")
            ruling["blocks"] = blocks
            summary = f"gap {gid}: blocks {', '.join(was) or 'nothing'} -> {', '.join(blocks)}"
        else:
            ruling.pop("blocks", None)
            blocked = ", ".join(was) or "nothing"
            summary = f"gap {gid}: accepted, does not stop the run (blocked {blocked})"
        ruling["replaces"] = was
    elif kind == "capabilities":
        current = {c.get("id"): c for c in _part_list(run.capabilities_part, "capabilities")}
        cap = entry["id"]
        if cap not in current:
            raise UsageError(f"01-capabilities.json records no capability {cap!r}")
        bound = (current[cap].get("binding") or {}).get("tool")
        if entry["ruling"] == "accept_unbound" and bound:
            raise UsageError(f"{cap!r} is already bound to {bound!r}; there is nothing to accept")
        if (
            entry["ruling"] == "bind"
            and entry["binding"]["tool"] == bound
            and (entry["binding"].get("fixed_args") or {})
            == (current[cap].get("binding") or {}).get("fixed_args", {})
        ):
            raise UsageError(f"{cap!r} is already bound to {bound!r} with those arguments")
        if entry["ruling"] == "bind":
            services, _ = effective_services(run, _services(run), document)
            tools = declared_tools(services)
            tool = entry["binding"]["tool"]
            if tools is None:
                raise UsageError("this run declares no services, so there is no tool to bind to")
            if tool not in tools:
                raise UsageError(
                    f"no service declares tool {tool!r}; declared: {', '.join(sorted(tools))}"
                )
            summary = f"capability {cap}: bound to {tool}"
        else:
            ruling.pop("binding", None)
            summary = f"capability {cap}: accepted as not drivable"
    else:  # services
        trial = {**document, "services": [*rulings, ruling]}
        if not run.services_part.is_file():
            raise UsageError("this run has no 01-services.json, so there is no grouping to change")
        _, problems = effective_services(run, _services(run), trial)
        if problems:
            raise UsageError(problems[-1].message)
        op = entry["op"]
        summary = {
            "move_tool": lambda: f"service: moved tool {entry['tool']} to {entry['to']}",
            "merge": lambda: f"service: merged {entry['service']} into {entry['into']}",
            "split": lambda: (
                f"service: split {', '.join(entry['tools'])} out of {entry['service']} "
                f"as {entry['new_id']}"
            ),
        }[op]()

    if kind != "services":
        if any(r.get("id") == entry["id"] for r in rulings):
            raise UsageError(
                f"{entry['id']!r} already has a ruling; use --clear first to change it"
            )
        rulings = sorted([*rulings, ruling], key=lambda r: r["id"])
    else:
        rulings = [*rulings, ruling]
    document[kind] = rulings
    write_json(run.rulings, document)
    return _log(run, stamp, summary, text)


def clear(run: RunPaths, *, kind: str, ref: str, reason: str, now: datetime | None = None) -> str:
    """Remove one ruling: by id, or for services by its position in the list."""
    from rubrica.manifest import utc_stamp

    text = _clean_reason(reason)
    _refuse_if_closed(run)
    document = load_strict(run)
    rulings = _entries(document, kind)
    if kind == "services":
        if not ref.isdigit() or int(ref) >= len(rulings):
            raise UsageError(f"there is no service ruling number {ref}")
        kept = [r for i, r in enumerate(rulings) if i != int(ref)]
        trial = {**document, "services": kept}
        _, problems = effective_services(run, _services(run), trial)
        if problems:
            raise UsageError(
                f"clearing it would leave the later rulings unappliable: {problems[0].message}"
            )
    else:
        kept = [r for r in rulings if r.get("id") != ref]
        if len(kept) == len(rulings):
            raise UsageError(f"{ref!r} has no ruling to clear")
    if kept:
        document[kind] = kept
    else:
        document.pop(kind, None)
    write_json(run.rulings, document)
    return _log(run, utc_stamp(now), f"cleared the {kind} ruling on {ref}", text)


def _log(run: RunPaths, stamp: str, summary: str, reason: str) -> str:
    # The ruling first, then the log line -- waivers.record's order. Worded so it
    # never reads as the gate's approval line (`- <stamp> gate N` / `human gate N`).
    line = f"- {stamp} ruling at gate 1: {summary} -- {reason}"
    try:
        append_decision(run.decisions, line)
    except OSError as exc:
        raise UsageError(
            f"the ruling is written to {run.rulings.name} but decisions.md could not be "
            f"appended ({exc}); re-record it with `rubrica decide`"
        ) from exc
    return summary


def parse_fixed_args(raw: str | None) -> dict:
    if raw is None:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UsageError(f"--fixed-args is not JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise UsageError("--fixed-args must be a JSON object")
    return value
