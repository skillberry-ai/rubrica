"""A human's record that a finding is correct and its remedy is not available here.

`refs.check_claim_utilisation` raises against `01-world-model.json`, which no
dispatchable stage declares in `writes`. When that finding is correct and
unfixable, the orchestrator's one repair attempt is not exhausted but
*unspendable*: every pass it could dispatch must refuse, because the finding
names a file that is not its output. A waiver is how a person records that,
so the gate stops being permanently dirty without the finding disappearing.

A waiver is not an assertion that the finding was wrong, and not a mute button:
the finding keeps printing, prefixed `[waived] `. Only its contribution to the
exit code goes away.

Only a human writes one. The gate-0 argument applies unchanged -- the party that
made a judgment must not also ratify it -- so neither the orchestrator (which
would diagnose and ratify in one move) nor the stage that declined (which would
vouch for its own refusal) may record one.
"""

from __future__ import annotations

import re
from datetime import datetime

from rubrica.artifacts import ArtifactError, append_decision, read_json, write_json
from rubrica.errors import UsageError
from rubrica.findings import format_findings
from rubrica.paths import STAGES, RunPaths
from rubrica.validate import validate_artifact

# Which checks may be waived at all, and what a `subject` names for each. The
# value is documentation with a consumer: the CLI quotes it when it rejects a
# subject, so a person is told what kind of name the check expects rather than
# just that theirs did not match.
#
# A check absent from here is not waivable. That is deliberate -- a waiver
# nothing reads is the shape this project cuts, so a row lands here only
# alongside a check that consults it.
WAIVABLE_CHECKS: dict[str, str] = {
    "claim-utilisation": "artifact_id",
}

# `none` means "the finding is correct and no artifact should change" -- the
# ruling this module was built for, where seven reconcile passes each correctly
# declined an out-of-domain artifact. Without it a human would be forced to name
# a remedy they do not believe in. `outside-the-run` covers a corpus that should
# not have contained the input at all.
_SENTINEL_REMEDIES: tuple[str, ...] = ("outside-the-run", "none")

# Mirrors waivers-0.1.json's `id` pattern rather than re-deriving it. The explicit
# [0-9] class is load-bearing for the reason paths.py's _ROUND_PART records as a
# ruling: `\d`, isdigit() and isdecimal() are all Unicode-wide, and int() folds
# `wv-١٢` to 12, so a laxer filter invents a number no ASCII reading of the id
# contains -- the same invented-round defect that comment was written for.
# Mirroring is coherent because `load` schema-validates: next_id only ever sees
# ids this pattern already accepted.
_WAIVER_ID = re.compile(r"\Awv-([0-9]{4,})\Z")


def remedy_choices() -> tuple[str, ...]:
    """Every stage name, plus the two sentinels. Derived, never restated."""
    return tuple(STAGES) + _SENTINEL_REMEDIES


def load(run: RunPaths) -> list[dict]:
    """Every waiver recorded for this run, `[]` when the file is absent.

    Absent is normal and silent: most runs record none. Malformed *raises*,
    which becomes an exit 2 through cli.py's handler, rather than being treated
    as "no waivers". Failing open would be safe in the narrow sense -- the
    finding would simply reappear -- and it would hide a corrupted human record
    behind a gate that then looks correct, which is the worse failure.

    **Schema-validated here, in the consumer, because nothing else in the run
    ever validates this artifact.** It is deliberately outside STAGE_ARTIFACTS,
    so no `validate --stage X` reaches it, and `rubrica waive`'s own checks are
    bypassed by exactly the hand-edit the design designates as the way to revoke
    a waiver. An invalid entry would otherwise suppress a finding silently and
    permanently, in the one mechanism whose whole purpose is auditability. This
    is the treatment smoke.load_agents and recall.load_gold already give their
    human-authored inputs, and the reason is theirs: a person wrote this file, so
    there is no stage to hand a repair prompt to, which makes it a UsageError
    (exit 2) rather than a finding.

    The three shape checks below run *first* and keep raising ArtifactError.
    Validation is an additional gate rather than a replacement: a document that
    is a JSON array, or whose entries are strings, must be refused by name here
    rather than reaching the validator and being described in schema vocabulary.
    """
    path = run.waivers
    if not path.exists():
        return []
    doc = read_json(path)
    if not isinstance(doc, dict):
        raise ArtifactError(f"{path}: a waivers document must be a JSON object")
    entries = doc.get("waivers")
    if not isinstance(entries, list):
        raise ArtifactError(f"{path}: a waivers document needs a `waivers` array")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ArtifactError(f"{path}: every waiver must be an object")
    findings = validate_artifact(path, "waivers")
    if findings:
        raise UsageError(f"unusable waivers: {path}:\n{format_findings(findings)}")
    return entries


def waived_subjects(run: RunPaths, check: str) -> frozenset[str]:
    """The subjects waived for `check`.

    Keyed on `(check, subject)` and never on the finding's message text. A text
    key would break on a reformat that changed nothing -- the failure this repo
    has already taken once, where a phrase pin broke on an innocuous rewording.
    `finding_text` is recorded as evidence, not used as a key.
    """
    return frozenset(
        entry["subject"]
        for entry in load(run)
        if entry.get("check") == check and isinstance(entry.get("subject"), str)
    )


def waived_subjects_quietly(run: RunPaths, check: str) -> frozenset[str]:
    """`waived_subjects`, but an unreadable file reads as no waivers at all.

    For a *report* rather than a gate, and the divergence is deliberate and
    narrow. `waived_subjects` raises, which cli.py turns into an exit 2 -- correct
    for `check-refs`, and wrong for `run-summary`, which exits 0 on a run it
    cannot read at all and must not gain a new way to fail on one it can. The
    malformed file is still somebody's exit 2: `check-refs` raises it on the same
    run, so failing quiet here loses no report of the defect.

    One spelling of the `(check, subject)` filter, delegated rather than copied:
    a second copy is how a report and the gate it mirrors come to disagree about
    which findings a human ruled on -- which is the disagreement the report grew
    in the first place.
    """
    try:
        return waived_subjects(run, check)
    except Exception:  # deliberate, matching brief._quietly's reasoning
        return frozenset()


def next_id(entries: list[dict]) -> str:
    """One past the highest `wv-` number present.

    Not `len(entries) + 1`, which would remint an id already used after somebody
    deleted a middle entry -- and deleting an entry is how a waiver is revoked,
    so the gap is an expected state rather than a corruption.
    """
    highest = 0
    for entry in entries:
        raw = entry.get("id")
        matched = _WAIVER_ID.match(raw) if isinstance(raw, str) else None
        if matched:
            highest = max(highest, int(matched.group(1)))
    return f"wv-{highest + 1:04d}"


def record(
    run: RunPaths,
    *,
    check: str,
    subject: str,
    remedy: str,
    reason: str,
    finding_text: str,
    now: datetime | None = None,
) -> str:
    """Append one waiver and return its id.

    `finding_text` is the caller's copy of the finding this waiver answers, and
    the CLI takes it from the finding itself rather than from a flag -- a human
    retyping a finding is a human who can paraphrase one.

    `check` is validated against WAIVABLE_CHECKS here because nothing else does:
    waivers-0.1.json deliberately keeps `check` a free string, so an entry naming
    a check no code consults is schema-valid and permanently inert. `remedy` is
    validated here for the mirror reason and *only* here -- `load` does not hold
    an existing file to remedy_choices(), since a stage renamed after a waiver was
    written must not turn the human record into an exit 2.

    A `(check, subject)` already waived is refused, and the message names the id
    of the waiver that holds it: two entries for one pair can carry contradictory
    remedies, and the hand-deletion that revokes a waiver would then leave the
    finding suppressed by the survivor.

    **One raise here does not mean nothing was written.** Every check runs before
    any filesystem mutation, so a UsageError from one of them leaves the run
    untouched -- but the append to decisions.md happens *after* waivers.json is
    written, and its failure is re-raised as a UsageError that says so and names
    the id. A caller must not read that one as "the waiver was not recorded".
    """
    if check not in WAIVABLE_CHECKS:
        raise UsageError(
            f"unknown check {check!r}; waivable checks are {', '.join(sorted(WAIVABLE_CHECKS))}"
        )
    choices = remedy_choices()
    if remedy not in choices:
        raise UsageError(f"unknown remedy {remedy!r}; expected one of {', '.join(choices)}")
    # Blank-string guards for the two fields the CLI cannot send blank but a
    # programmatic caller can. Both are minLength: 1 in waivers-0.1.json, so `""`
    # writes a document `load` then rejects -- and every later check-refs on that
    # run exits 2, leaving a run that poisoned itself and is recoverable only by a
    # hand edit, in the one mechanism whose purpose is auditability. decide sets
    # the precedent by refusing a blank note.
    #
    # Tested for blankness but stored unchanged, unlike `reason` below: `subject`
    # is the key waived_subjects compares against, and `finding_text` is a byte
    # copy of the finding's own message. Stripping either would make the record
    # differ from what the caller matched.
    if not subject.strip():
        raise UsageError("a waiver subject cannot be empty")
    text = reason.strip()
    if not text:
        raise UsageError("a waiver reason cannot be empty")
    if "\n" in text:
        raise UsageError(
            "a waiver reason cannot contain a newline; decisions.md is one line per entry"
        )
    if not finding_text.strip():
        raise UsageError("a waiver's finding text cannot be empty")

    # Deferred rather than imported at module scope, to keep manifest -- and
    # through it skills -- out of this module's import graph: refs.py imports
    # waivers at module scope, so every consumer of refs pays for whatever sits
    # there. Measured: this is not a cycle. manifest reaches artifacts, errors,
    # paths, skills and validate, none of which reaches refs or waivers, and this
    # module already imports validate at module scope. So the deferral buys
    # narrowness, not import-ability.
    from rubrica.manifest import utc_stamp

    stamp = utc_stamp(now)
    # Through `load`, so a file whose existing content is malformed is refused
    # before anything is appended to it: minting an id from entries that failed
    # validation would write a second entry into a document already unusable.
    entries = load(run)
    # One waiver per `(check, subject)`, which is the key `waived_subjects`
    # suppresses on. Measured before this guard existed: waiving the same pair
    # twice landed wv-0001 with `remedy: none` and wv-0002 with
    # `remedy: triage-rule` -- two contradictory rulings for one finding (`none`
    # says nothing should change, a stage name says somebody owes work), and
    # `gate-brief` printed `Waivers in force: 2` for it. The harm lands on
    # revocation, which is a hand-deletion: deleting the entry a reader found
    # leaves the finding suppressed by the survivor, in the one mechanism whose
    # whole purpose is auditability. The existing id is named so the person can
    # go to that entry instead of searching the file for it.
    #
    # Appending for a *different* subject under the same check stays correct: the
    # key is the pair, not the check.
    for existing in entries:
        if existing.get("check") == check and existing.get("subject") == subject:
            raise UsageError(
                f"{check}/{subject} is already waived by {existing['id']}; "
                f"amend or delete that entry in {run.waivers} rather than recording a second"
            )
    waiver_id = next_id(entries)
    entries.append(
        {
            "id": waiver_id,
            "check": check,
            "subject": subject,
            "remedy": remedy,
            "reason": text,
            "finding_text": finding_text,
            "recorded_at": stamp,
        }
    )
    write_json(run.waivers, {"schema_version": "0.1", "waivers": entries})
    # Also in decisions.md, so the prose trail sits in the file a human already
    # reads at every gate rather than only in a JSON document they would have to
    # know to open. One line, `decide`'s shape, which is why the newline above is
    # refused.
    try:
        append_decision(
            run.decisions,
            f"- {stamp} waived {check}/{subject}: remedy {remedy}; {text}",
        )
    except OSError as exc:
        # waivers.json is written first and stays written: it is the artifact the
        # gate reads, and appending the prose first would leave decisions.md
        # asserting a waiver that does not exist -- a false record that
        # accumulates on every retry. What was wrong here was never the order but
        # the silence: the waiver is live and already suppressing a finding, so
        # the failure names the id and both files rather than letting a caller
        # read the exit 2 as "nothing happened".
        raise UsageError(
            f"waiver {waiver_id} was recorded in {run.waivers} and is in effect, but "
            f"{run.decisions} could not be appended to: {exc}. The waiver stands; "
            f"remove it by hand to undo it."
        ) from exc
    return waiver_id
