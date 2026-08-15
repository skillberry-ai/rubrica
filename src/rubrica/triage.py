"""Gate 0's other half: adopting a manufactured projection back into a run.

`rb-triage` (the ninth skill) writes a projection when a candidate is valuable
but unusable as-is -- a work order for a file nothing in the run has yet. A
human (or, later, another dispatched member) manufactures that file outside
the run entirely. This module is how it comes back in: `check_acceptance`
runs the projection's `acceptance` contract's *mechanical* checks -- the ones
a machine can actually decide -- and `adopt_projection` appends a catalogue
candidate and an `admit` disposition once every one of them passes.

What this deliberately does not do: judge `acceptance.prose`. Whether a
tool's `result_shape` truly describes what a caller receives is semantic, and
layer 2's own rule -- check that a reference *resolves*, never that it
*supports* -- applies here just as it does to check-refs. `prose` stays a
human's call; `ACCEPTANCE_PASS_MESSAGE` says so on every clean pass, in words
chosen so a reader cannot mistake "structurally sound" for "accepted".
"""

from __future__ import annotations

import json
from pathlib import Path

from rubrica.artifacts import read_json, sha256_of, write_json
from rubrica.errors import UsageError
from rubrica.findings import Finding
from rubrica.intake import _unique_artifact_id, classify
from rubrica.paths import RunPaths
from rubrica.refs import UNSET, resolve_pointer

# The core semantic point of this module, said in the one place a human
# reading CLI output will actually see it: structural acceptance is
# necessary and never sufficient. "accepted" is deliberately absent -- a
# clean run of the four mechanical checks below is not a verdict on whether
# the file means what the projection asked for.
ACCEPTANCE_PASS_MESSAGE = (
    "structural acceptance passed; the prose criterion is still a human's to judge"
)


def check_acceptance(path: Path, acceptance: dict) -> list[Finding]:
    """Run one projection's acceptance contract's mechanical checks against `path`.

    Every finding names `path` -- the manufactured source file -- never a run
    artifact: nothing about `path` is part of the run yet, so a run-artifact
    pointer would name something that does not carry the defect. Four checks,
    each independent so a file failing more than one comes back as more than
    one finding -- the worker retrying against them, and later a human at gate
    1, both read the same list.

    `classifies_as` is checked through `intake.classify`, the same classifier
    intake itself will run once the candidate is admitted -- so adoption can
    never promise a kind that intake goes on to disagree with. `pointers_required`
    is resolved through `refs.resolve_pointer`, the same RFC 6901 walk check-refs
    uses elsewhere, so "does not resolve" means exactly one thing across this
    project. `must_contain` and `must_not_contain` are plain substring tests over
    the file's decoded text -- no parsing, no semantics, just what the brief's
    acceptance contract literally demanded or forbade.
    """
    path = Path(path)
    out: list[Finding] = []

    def report(message: str) -> None:
        out.append(Finding(path, "refs", "", message))

    # Read once, up front: a file that cannot be decoded as UTF-8 text is a
    # harness-level "unreadable file", which is this module's one usage
    # error, not a structural finding -- so it must be raised before any
    # check below has a chance to turn it into one instead.
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UsageError(f"cannot read projection source: {path} ({exc})") from exc

    actual_kind = classify(path)
    wanted_kind = acceptance["classifies_as"]
    if actual_kind != wanted_kind:
        report(
            f"classifies as {actual_kind!r} (via intake.classify), but the projection's "
            f"acceptance contract asked for {wanted_kind!r}"
        )

    for needle in acceptance.get("must_contain") or []:
        if needle not in text:
            report(f"must contain {needle!r}, which is not present")

    for needle in acceptance.get("must_not_contain") or []:
        if needle in text:
            report(
                f"must not contain {needle!r}, which is present -- the boundary this "
                "projection was scoped to exclude"
            )

    pointers = acceptance.get("pointers_required") or []
    if pointers:
        try:
            document = json.loads(text)
        except json.JSONDecodeError:
            document = None
        for pointer in pointers:
            if document is None:
                report(f"pointer {pointer!r} does not resolve: the file is not valid JSON")
                continue
            try:
                resolved = resolve_pointer(document, pointer)
            except ValueError as exc:
                report(f"pointer {pointer!r} is malformed: {exc}")
                continue
            if resolved is UNSET:
                report(f"pointer {pointer!r} does not resolve")

    return out


def adopt_projection(
    run: RunPaths, *, projection_id: str, source: Path, check_only: bool = False
) -> list[Finding]:
    """Bring one manufactured projection into the catalogue and close its deficiency.

    Copies nothing: unlike `intake.materialise`, the file stays exactly where
    the human left it. The catalogue gains a candidate whose `path` is the
    absolute source path (no `root_index` -- a projection is not relative to
    any corpus root survey walked). `00-triage.json` gains an `admit`
    disposition with `authority: "human"`, so a reader can always tell an
    admission the gate authored from one a human made at this later gate;
    every deficiency the projection's `closes` names gets `closed_by` set to
    the projection_id, and the projection itself gets `satisfied_by` set to
    the new candidate_id.

    Returns findings and writes nothing when `check_acceptance` finds anything
    to report -- the worker reads and retries against them, same as any other
    repairable stage defect. `check_only` short-circuits the same way on a
    clean pass: nothing is ever written when it is set, findings or not.

    Only a missing run artifact, an unreadable source file, or a
    `projection_id` this run's triage record does not carry is a UsageError --
    nothing in the run is defective in that last case, the caller named
    something that does not exist.
    """
    source = Path(source)
    if not source.is_file():
        raise UsageError(f"projection source is not a readable file: {source}")
    if not run.triage.is_file():
        raise UsageError(
            f"no triage record at {run.triage}; adopt-projection needs its projections"
        )
    if not run.catalogue.is_file():
        raise UsageError(f"no catalogue at {run.catalogue}; this run was not minted by survey")

    triage_record = read_json(run.triage)
    projections = triage_record.get("projections") or []
    projection = next(
        (p for p in projections if isinstance(p, dict) and p.get("projection_id") == projection_id),
        None,
    )
    if projection is None:
        raise UsageError(
            f"no projection {projection_id!r} in {run.triage}; nothing in the run is "
            "defective, the caller named something that does not exist"
        )

    findings = check_acceptance(source, projection["acceptance"])
    if findings:
        return findings
    if check_only:
        return []

    catalogue = read_json(run.catalogue)
    candidates = catalogue.get("candidates") or []
    used = {c["candidate_id"]: 1 for c in candidates if isinstance(c, dict) and "candidate_id" in c}
    candidate_id = _unique_artifact_id(projection_id, used)

    kind = classify(source)
    source_candidate_ids = [
        s["candidate_id"] for s in projection.get("sources") or [] if isinstance(s, dict)
    ]
    candidate = {
        "candidate_id": candidate_id,
        "origin": "projection",
        "path": str(source.resolve()),
        "bytes": source.stat().st_size,
        "sha256": sha256_of(source),
        "kind": kind,
        "admissible": True,
        "digest": {},
        "provenance": {
            "projection_id": projection_id,
            "source_candidate_ids": source_candidate_ids,
        },
    }
    candidates.append(candidate)
    catalogue["candidates"] = candidates

    dispositions = triage_record.get("dispositions") or []
    dispositions.append(
        {
            "candidate_id": candidate_id,
            "disposition": "admit",
            "reason": f"structural acceptance passed for projection {projection_id!r}",
            "authority": "human",
        }
    )
    triage_record["dispositions"] = dispositions

    closes = set(projection.get("closes") or [])
    for deficiency in triage_record.get("deficiencies") or []:
        if isinstance(deficiency, dict) and deficiency.get("deficiency_id") in closes:
            deficiency["closed_by"] = projection_id
    projection["satisfied_by"] = candidate_id

    write_json(run.catalogue, catalogue)
    write_json(run.triage, triage_record)
    return []
