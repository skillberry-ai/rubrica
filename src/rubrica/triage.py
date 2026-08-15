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

from rubrica import digest as digest_module
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


def _strings(value, report, label: str) -> list[str]:
    """The string members of `value`, reporting every other shape it carries.

    `value or []` is not a sufficient guard, for the reason
    `refs._as_list`'s docstring records: it substitutes only on a *falsy*
    value, so a truthy non-list (`"nope"`, an int) still reaches the `for`
    loop -- a string iterates character by character, silently checking the
    wrong thing, and an int raises TypeError. Both are the caller's criterion
    being quietly not-checked, which is worse here than anywhere else in this
    module: `check_acceptance` returning clean is what lets `adopt_projection`
    write to the catalogue.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        report(f"the acceptance contract's {label} is {value!r}, not a list of strings")
        return []
    out = []
    for member in value:
        if isinstance(member, str):
            out.append(member)
        else:
            report(f"the acceptance contract's {label} carries {member!r}, which is not a string")
    return out


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
    # `acceptance["classifies_as"]` was a bare index, one function away from the
    # guard at adopt_projection's own `acceptance` read that exists for exactly
    # this reason -- and measured with `"acceptance": {"prose": "p"}` it raised
    # KeyError straight out of main(): exit 1, empty stdout. The finding names
    # `path` like every other one here, because the whole point of this function
    # is that a projection's acceptance contract is judged against the
    # manufactured file; the *record*-level defect is reported by
    # adopt_projection, which owns the run.triage pointer.
    wanted_kind = acceptance.get("classifies_as")
    if not isinstance(wanted_kind, str):
        report(
            f"the projection's acceptance contract asks for classifies_as {wanted_kind!r}, "
            "which is not an artifact kind; structural acceptance cannot be judged against it"
        )
    elif actual_kind != wanted_kind:
        report(
            f"classifies as {actual_kind!r} (via intake.classify), but the projection's "
            f"acceptance contract asked for {wanted_kind!r}"
        )

    # `_strings` on all three lists below. `needle not in text` raises TypeError
    # for a non-string needle ("'in <string>' requires string as left operand"),
    # and `resolve_pointer` raises AttributeError on `pointer.startswith` for a
    # non-string pointer -- both measured escaping main(). A non-string entry is
    # itself the defect, so it is reported rather than skipped: silently
    # ignoring it would let a projection pass structural acceptance on a
    # criterion nobody checked.
    for needle in _strings(acceptance.get("must_contain"), report, "must_contain"):
        if needle not in text:
            report(f"must contain {needle!r}, which is not present")

    for needle in _strings(acceptance.get("must_not_contain"), report, "must_not_contain"):
        if needle in text:
            report(
                f"must not contain {needle!r}, which is present -- the boundary this "
                "projection was scoped to exclude"
            )

    pointers = _strings(acceptance.get("pointers_required"), report, "pointers_required")
    if pointers:
        try:
            document = json.loads(text)
        # RecursionError alongside JSONDecodeError, matching
        # digest.digest_for_path and intake._json_or_none: a manufactured
        # projection is a file a human wrote outside the run, so nothing has
        # vetted its nesting depth, and CPython's decoder raises RecursionError
        # rather than JSONDecodeError on a pathologically nested one.
        except (json.JSONDecodeError, RecursionError):
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

    Only a missing run artifact, an unreadable source file, a `projection_id`
    this run's triage record does not carry, or a `projection_id` already
    `satisfied_by` an earlier call is a UsageError -- nothing in the run is
    defective in any of those cases, the caller is either naming something
    that does not exist or repeating a completed action.
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
    # A *present but not a list* `projections` is a malformed record, which is
    # exit 1 with a finding -- not the "no projection X" UsageError below at
    # exit 2, which is where `"projections": "nope"` was measured to land it.
    # A stage defect must never surface as 2 (the orchestrator halts rather
    # than spending its one repair), and the distinction this preserves is
    # real: an *absent* or *empty* projections list with a `--projection` on
    # argv is the caller naming something that does not exist, which is a
    # usage error, while a string where an array belongs is 00-triage.json
    # being wrong.
    raw_projections = triage_record.get("projections")
    if raw_projections is not None and not isinstance(raw_projections, list):
        return [
            Finding(
                run.triage,
                "internal",
                "/projections",
                f"projections is {raw_projections!r}, not a list; adopt-projection cannot find "
                "the projection it was asked to adopt",
            )
        ]
    projections = raw_projections or []
    # enumerate rather than next() over a bare generator: a real index lets
    # the acceptance-missing finding below point at exactly the projection
    # that is malformed, not "somewhere in /projections".
    projection = None
    projection_index = None
    for index, candidate_projection in enumerate(projections):
        if (
            isinstance(candidate_projection, dict)
            and candidate_projection.get("projection_id") == projection_id
        ):
            projection = candidate_projection
            projection_index = index
            break
    if projection is None:
        raise UsageError(
            f"no projection {projection_id!r} in {run.triage}; nothing in the run is "
            "defective, the caller named something that does not exist"
        )

    # Idempotency: a second call for a projection already satisfied is not a
    # repeat of the same admission -- check_acceptance would still pass (the
    # file has not changed) and everything below would mint a *second*
    # candidate, append a *second* valid `admit` disposition, and overwrite
    # `satisfied_by`. Neither check_triage nor check_catalogue checks "at
    # most one admitted candidate per projection_id", so that duplication
    # passes check_all cleanly -- two real catalogue candidates from one
    # projection, silently feeding two identical inputs into extract. The
    # caller most likely to hit this is a human at gate 0 retrying a command
    # whose first outcome they were unsure about, so this is a UsageError
    # naming what already happened, not a finding: nothing in the run is
    # defective, the caller is repeating a completed action.
    already_satisfied_by = projection.get("satisfied_by")
    if already_satisfied_by:
        raise UsageError(
            f"projection {projection_id!r} is already satisfied by candidate "
            f"{already_satisfied_by!r}; adopt-projection does not re-admit an "
            "already-satisfied projection"
        )

    # projection["acceptance"] would raise KeyError on an unvalidated triage
    # record -- and because adopt-projection's cli.py dispatch block catches
    # only (UsageError, ArtifactError, OSError), an uncaught KeyError would
    # escape main() entirely as a traceback: an empty-stdout exit under a
    # code path the exit-code contract's "1 must never have empty stdout"
    # rule exists to forbid. A malformed triage record is a repairable stage
    # defect, and this function already returns findings, so it becomes one
    # naming the record -- never a run.catalogue or 05-verdicts pointer,
    # since 00-triage.json is where the defect actually lives.
    acceptance = projection.get("acceptance")
    if not isinstance(acceptance, dict):
        return [
            Finding(
                run.triage,
                "internal",
                f"/projections/{projection_index}/acceptance",
                f"projection {projection_id!r} has no acceptance object; adopt-projection "
                "cannot judge structural acceptance without it",
            )
        ]

    findings = check_acceptance(source, acceptance)
    if findings:
        return findings
    if check_only:
        return []

    catalogue = read_json(run.catalogue)
    # Both containers this function *appends to* are checked before it does,
    # and for a sharper reason than the read-only guards above: `"nope".append`
    # raises AttributeError, which escaped main() as exit 1 with empty stdout
    # (measured on both `candidates` and `dispositions`), and unlike a bad read
    # the failure lands halfway through a two-file write -- catalogue written,
    # triage record not, or the reverse. Refusing before the first write_json
    # is what keeps the pair consistent.
    raw_candidates = catalogue.get("candidates")
    if raw_candidates is not None and not isinstance(raw_candidates, list):
        return [
            Finding(
                run.catalogue,
                "internal",
                "/candidates",
                f"candidates is {raw_candidates!r}, not a list; adopt-projection cannot append "
                "the adopted candidate to it",
            )
        ]
    raw_dispositions = triage_record.get("dispositions")
    if raw_dispositions is not None and not isinstance(raw_dispositions, list):
        return [
            Finding(
                run.triage,
                "internal",
                "/dispositions",
                f"dispositions is {raw_dispositions!r}, not a list; adopt-projection cannot "
                "append the human's admit to it",
            )
        ]
    candidates = raw_candidates or []
    # `isinstance(..., str)` rather than the `"candidate_id" in c` this replaced:
    # a candidate_id that is not a string need not even be *hashable*, and a
    # list one raised `TypeError: unhashable type: 'list'` building this dict --
    # out of main(), again at exit 1 with empty stdout. A non-string id cannot
    # collide with `projection_id` (which _unique_artifact_id compares as a
    # string) so dropping it from the collision map loses nothing, and
    # check_catalogue already reports it as a finding of its own.
    used = {
        c["candidate_id"]: 1
        for c in candidates
        if isinstance(c, dict) and isinstance(c.get("candidate_id"), str)
    }
    candidate_id = _unique_artifact_id(projection_id, used)

    kind = classify(source)
    # digest.digest_for_path, the same call survey makes for every corpus
    # candidate -- one spelling of "how a candidate is digested", not a
    # second one for projections. body_chars comes from this catalogue's own
    # policy rather than survey.DEFAULT_DIGEST_BODY_CHARS: no import cycle
    # forces the choice (survey does not import this module), but reading it
    # from the catalogue keeps the adopted candidate's digest consistent with
    # every sibling *in this catalogue*, not with whatever today's global
    # default happens to be. An empty digest here would starve two readers: a
    # human at gate 0 (gate-brief renders it) and a re-dispatched rb-triage,
    # which would be obliged to decline the very file a human just admitted,
    # via its digest_insufficient refusal path.
    #
    # catalogue["policy"]["digest_body_chars"] would raise KeyError on an
    # unvalidated catalogue, for the same escapes-main()-as-a-traceback
    # reason the acceptance guard above exists -- so this is a Finding
    # against run.catalogue too, not a bare index.
    policy = catalogue.get("policy")
    digest_body_chars = policy.get("digest_body_chars") if isinstance(policy, dict) else None
    # bool excluded explicitly: isinstance(True, int) is True in Python, so
    # `"digest_body_chars": true` passed this guard and reached
    # digest_for_path as body_chars=1, truncating every digest body to a single
    # character with no error anywhere. JSON `true` is not an integer to the
    # catalogue schema either, so this is layer 1's rule held one step earlier
    # -- the same reason intake() and survey() exclude bool from their limits.
    if not isinstance(digest_body_chars, int) or isinstance(digest_body_chars, bool):
        return [
            Finding(
                run.catalogue,
                "internal",
                "/policy/digest_body_chars",
                "digest_body_chars is missing or not an integer; adopt-projection cannot "
                "digest the adopted candidate without it",
            )
        ]
    candidate_digest = digest_module.digest_for_path(source, kind, body_chars=digest_body_chars)
    raw_sources = projection.get("sources")
    # `or []` alone let a truthy non-list through -- `"sources": "nope"`
    # iterated character by character, and only `isinstance(s, dict)` filtering
    # every character out kept it from raising. It recorded an empty
    # `source_candidate_ids` on a projection that declared sources, which is
    # provenance silently lost rather than reported, so the shape is checked
    # instead of tolerated.
    if raw_sources is not None and not isinstance(raw_sources, list):
        return [
            Finding(
                run.triage,
                "internal",
                f"/projections/{projection_index}/sources",
                f"sources is {raw_sources!r}, not a list; the adopted candidate's provenance is "
                "minted from the candidate_ids it names",
            )
        ]
    source_candidate_ids = [
        s["candidate_id"]
        for s in raw_sources or []
        if isinstance(s, dict) and isinstance(s.get("candidate_id"), str)
    ]
    candidate = {
        "candidate_id": candidate_id,
        "origin": "projection",
        "path": str(source.resolve()),
        "bytes": source.stat().st_size,
        "sha256": sha256_of(source),
        "kind": kind,
        "admissible": True,
        "digest": candidate_digest,
        "provenance": {
            "projection_id": projection_id,
            "source_candidate_ids": source_candidate_ids,
        },
    }
    candidates.append(candidate)
    catalogue["candidates"] = candidates

    dispositions = raw_dispositions or []
    dispositions.append(
        {
            "candidate_id": candidate_id,
            "disposition": "admit",
            "reason": f"structural acceptance passed for projection {projection_id!r}",
            "authority": "human",
        }
    )
    triage_record["dispositions"] = dispositions

    # Only the *hashable* members, and only from a real list. `set(...)` over a
    # `closes` carrying a list raised `TypeError: unhashable type: 'list'` out
    # of main(); a truthy non-list `closes` (a string) would have built a set of
    # its characters and closed nothing. A deficiency_id that is not a string
    # cannot match one that is, so restricting to strings changes no correct
    # outcome, and check_triage already reports a `closes` entry that resolves
    # to no deficiency.
    raw_closes = projection.get("closes")
    closes = (
        {c for c in raw_closes if isinstance(c, str)} if isinstance(raw_closes, list) else set()
    )
    raw_deficiencies = triage_record.get("deficiencies")
    for deficiency in raw_deficiencies if isinstance(raw_deficiencies, list) else []:
        if isinstance(deficiency, dict) and deficiency.get("deficiency_id") in closes:
            deficiency["closed_by"] = projection_id
    projection["satisfied_by"] = candidate_id

    write_json(run.catalogue, catalogue)
    write_json(run.triage, triage_record)
    return []
