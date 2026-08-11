"""Writing into a run after intake minted it: the stage map and the notebook.

Both are declared by the design spec (section 4's reproducibility hook, and
decisions.md as the run's append-only lab notebook) and had no writer. The
consequence for the stage map was not cosmetic: stability.comparability gates
diff-runs' headline verdict on the two manifests' stage maps matching, so an
always-empty map made every pair of runs comparable -- a check passing because
its input was absent.

Timestamps are minted here rather than passed in, for the reason section 4
gives: a skill that invents a timestamp makes two otherwise-identical runs diff.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from rubrica.artifacts import append_decision, read_json, write_json
from rubrica.errors import UsageError
from rubrica.paths import STAGES, RunPaths
from rubrica.skills import skill_sha256
from rubrica.validate import manifest_stage_efforts

# The one spelling of the artifact timestamp format. intake writes
# manifest.created_utc with it and decide stamps each notebook line with it;
# two copies would let a reader's parser work on one and not the other.
UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc_stamp(now: datetime | None = None) -> str:
    """Now, or a supplied aware datetime, in the artifact timestamp format."""
    if now is None:
        return datetime.now(UTC).strftime(UTC_FORMAT)
    if now.tzinfo is None:
        raise UsageError("a naive datetime cannot be stamped; pass an aware one")
    return now.astimezone(UTC).strftime(UTC_FORMAT)


def record_stage(run: RunPaths, *, stage: str, model: str, effort: str, skill: Path) -> None:
    """Merge one stage's model, effort, and skill digest into the manifest.

    Merges rather than replaces: a stage re-dispatched after a repair overwrites
    its own entry and must leave its siblings alone. Written through
    write_json, so the manifest keeps its canonical byte form -- a hand-rolled
    dump would reformat every line and diff-runs would report that as variance.

    The digest is computed from `skill` here rather than accepted as a string:
    a caller that can pass a digest can pass the wrong one, and the point of
    the hook is that the recorded hash is of the file that was actually used.
    """
    if stage not in STAGES:
        raise UsageError(f"unknown stage {stage!r}; expected one of {', '.join(STAGES)}")
    # Rejected here rather than left for the manifest schema's minLength: 1 to
    # catch three steps downstream. A blank model would still write at exit 0
    # and only surface as an exit-1 finding the next time someone happens to
    # run `validate` -- misattributing a bad orchestrator argument to the
    # manifest, the same misdirection the missing OSError catch above causes
    # for a filesystem problem. Stricter than the schema on purpose: "   "
    # satisfies minLength: 1 but records nothing anyone could use as a model
    # name, so it is refused the same way decide refuses a whitespace-only note.
    if not model.strip():
        raise UsageError("a stage's model cannot be empty")
    # Same shape, for the same reason: effort's argparse `choices` protects the
    # CLI, but record_stage is a library function a caller can invoke directly
    # (this module's own tests do), and nothing before this line stopped an
    # empty or invented effort from being written and only rejected later by
    # the manifest schema's enum.
    if effort not in manifest_stage_efforts():
        raise UsageError(
            f"unknown effort {effort!r}; expected one of {', '.join(manifest_stage_efforts())}"
        )
    if not Path(skill).is_file():
        raise UsageError(f"skill file does not exist: {skill}")
    manifest = read_json(run.manifest)
    raw_stages = manifest.get("stages")
    # A hand-edited or corrupt manifest.stages that is present but not a
    # mapping (a list, a string) would make `dict(raw_stages or {})` either
    # raise a bare TypeError -- which cli.py's record-stage handler does not
    # catch, so it would fall through to the internal-error branch and become
    # exit 1 -- or, for something falsy like `[]` or `""`, silently discard it
    # in favour of an empty map. Both are wrong: this is the harness pointed at
    # a manifest it cannot act on, which is exit 2, not a repairable finding.
    # A per-stage *entry* that is not a dict needs no such guard here, because
    # the assignment below replaces that entry wholesale rather than merging
    # into it -- so a malformed sibling entry is left untouched, not read.
    if raw_stages is not None and not isinstance(raw_stages, dict):
        raise UsageError(
            f"manifest.stages is a {type(raw_stages).__name__}, not an object; "
            f"the manifest at {run.manifest} is corrupt"
        )
    stages = dict(raw_stages or {})
    stages[stage] = {
        "model": model,
        "effort": effort,
        "skill_sha256": skill_sha256(skill),
    }
    manifest["stages"] = stages
    write_json(run.manifest, manifest)


def decide(run: RunPaths, note: str, *, now: datetime | None = None) -> None:
    """Append one timestamped decision to the run's decisions.md.

    An empty note is refused rather than written: a blank entry records that a
    decision was made and not what it was, which is worse than no entry.

    A note containing a newline is refused too. decisions.md is one entry per
    line (every reader, including this module's own tests, parses it that
    way), and append_decision only strips a *trailing* newline -- an embedded
    one would split the entry across two physical lines, one of which has no
    leading `- <timestamp>` and silently corrupts the append-only format for
    every line written after it.
    """
    text = note.strip()
    if not text:
        raise UsageError("a decision note cannot be empty")
    if "\n" in text:
        raise UsageError(
            "a decision note cannot contain a newline; decisions.md is one line per entry"
        )
    append_decision(run.decisions, f"- {utc_stamp(now)} {text}")
