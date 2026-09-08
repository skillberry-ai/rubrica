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

from rubrica.artifacts import ArtifactError, read_json
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
