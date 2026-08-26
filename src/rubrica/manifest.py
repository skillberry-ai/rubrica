"""Writing into a run after intake minted it: the stage map and the notebook.

Both belong to the run's on-disk contract -- the reproducibility hook that
hashes each stage's skill, and decisions.md as the run's append-only lab
notebook -- and had no writer. The
consequence for the stage map was not cosmetic: stability.comparability gates
diff-runs' headline verdict on the two manifests' stage maps matching, so an
always-empty map made every pair of runs comparable -- a check passing because
its input was absent.

Timestamps are minted here rather than passed in, for the reproducibility
reason: a skill that invents a timestamp makes two otherwise-identical runs
diff.
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


def set_limit(
    run: RunPaths,
    *,
    max_rounds: int | None = None,
    max_scenarios: int | None = None,
    max_scenario_part_bytes: int | None = None,
    reason: str,
    now: datetime | None = None,
) -> None:
    """Lower (or raise) a manifest limit, with the reason recorded in decisions.md.

    This function replaces a specific failure: a run's
    `max_scenarios` had been hand-edited with no trace of who did it or why,
    and it was read as an unexplained discrepancy because every mechanism was
    checked before the person. A limits change made through this function
    instead always leaves a decisions.md line naming both the old and the new
    value and the reason, so the next reader does not have to reconstruct it.

    `reason` is required and refused blank, on `decide`'s own reasoning: an
    unexplained change is worse than no change. At least one of `max_rounds`,
    `max_scenarios` or `max_scenario_part_bytes` must be given -- calling this
    with none of them is a no-op that would still cost a decisions.md line about
    nothing, so it is a usage error instead, matching the same class of guard
    `decide` and `record_stage` apply to their own arguments.

    `max_scenario_part_bytes` is the propose/score loop's per-member output
    budget, and it is the one limit that may be absent from a manifest: making a
    third `limits` key required would have made every manifest already under
    `runs/` schema-invalid, and `diff-runs`, `run-summary` and `gate-brief` all
    read those. Absent means `rounds.DEFAULT_SCENARIO_PART_BYTES`, so setting it
    here is how a smaller budget gets onto the record rather than into an
    argument nobody kept.

    This does not itself set `implied_size`'s number here or anywhere else --
    `sizing.implied_size` is a diagnostic nothing acts on (see its module
    docstring); this exists for the opposite direction, lowering the ceiling
    on a cheap probe run, with the reason on record instead of a silent edit.
    """
    # One ordered roster of (key, requested value), read by all three loops below
    # -- the no-op guard, the range check, and the apply-and-record pass. A third
    # limit handled on its own branch would have to be added to each of them
    # separately, and the first one forgotten would either accept a call that
    # changes nothing, write an out-of-range budget, or apply a value with no
    # decisions.md line: the exact failure this function exists to prevent.
    requested: tuple[tuple[str, int | None], ...] = (
        ("max_rounds", max_rounds),
        ("max_scenarios", max_scenarios),
        ("max_scenario_part_bytes", max_scenario_part_bytes),
    )
    if all(value is None for _, value in requested):
        names = ", ".join(label for label, _ in requested[:-1])
        raise UsageError(f"set_limit needs at least one of {names} or {requested[-1][0]}")
    # The integers, refused here rather than left for the manifest schema --
    # exactly what `record_stage` above does for `--model` and `--effort`, and
    # `intake()` for these same two limits, with the same reasoning and the same
    # measured consequence. `set-limit --max-scenarios 0 --max-rounds -3` exited
    # 0, wrote both values, and appended a decisions.md line announcing the
    # change; the defect surfaced only the next time somebody happened to run
    # `validate`, as two findings against manifest.json -- an artifact no skill
    # wrote and no repair prompt can fix, so a bad orchestrator argument was
    # misattributed to the run. manifest-0.1.json puts `minimum: 1` on both, and
    # nothing between argparse's `type=int` and the schema was checking it.
    #
    # isinstance-checked, not just `< 1`, because set_limit is a library
    # function a direct caller reaches with 2.5 or "2" -- which would write a
    # manifest the schema rejects for its *type* rather than its value, the same
    # class of defect one step further out. bool is excluded because
    # isinstance(True, int) is True and `max_rounds=True` would write JSON
    # `true`, which is not an integer to the schema either.
    for label, value in requested:
        if value is None:
            continue
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise UsageError(f"set_limit needs {label} to be an integer >= 1, got {value!r}")
    text = reason.strip()
    if not text:
        raise UsageError("set_limit's reason cannot be empty")
    if "\n" in text:
        raise UsageError(
            "set_limit's reason cannot contain a newline; decisions.md is one line per entry"
        )

    manifest = read_json(run.manifest)
    raw_limits = manifest.get("limits")
    # The same guard `record_stage` applies to `manifest.stages`, for the same
    # reason: a hand-edited or corrupt `limits` that is present but not a mapping
    # makes `dict(raw_limits or {})` either raise ValueError -- which cli.py's
    # set-limit handler does not catch, so it fell through to the internal-error
    # branch and became exit 1, a fabricated stage finding for a corrupt
    # manifest -- or, for something falsy like `[]`, silently discard it in
    # favour of an empty map and lose the limit it was asked to leave alone.
    # This is the harness pointed at a manifest it cannot act on, which is exit 2.
    if raw_limits is not None and not isinstance(raw_limits, dict):
        raise UsageError(
            f"manifest.limits is a {type(raw_limits).__name__}, not an object; "
            f"the manifest at {run.manifest} is corrupt"
        )
    limits = dict(raw_limits or {})
    changes = []
    for label, value in requested:
        if value is None:
            continue
        # '?' for the old value covers max_scenario_part_bytes' ordinary case: it
        # is optional, so the first time it is set there is nothing to report as
        # the previous value, and a fabricated default here would read as a change
        # from a number the manifest never carried.
        changes.append(f"{label} {limits.get(label, '?')} -> {value}")
        limits[label] = value
    manifest["limits"] = limits
    # Two writes, and they are not transactional: nothing here makes the manifest
    # and decisions.md succeed or fail together, so a failure between them leaves
    # one written and the other not. Manifest first is the deliberate choice, and
    # the ordering is the whole mitigation.
    #
    # This way round, the survivable outcome is a limit that changed with no
    # decisions.md line -- bad, and precisely the failure this function exists
    # to prevent (a hand-edited max_scenarios with no trace of who did it or why),
    # but recoverable: the manifest still carries the new value, `diff-runs`
    # still sees it, and a human can append the missing note.
    #
    # The other way round would leave a decisions.md line asserting a change that
    # did not happen, and decisions.md is append-only -- the run's lab notebook
    # would carry a false entry that nothing can retract, and the next reader
    # would trust it over the manifest. A record that lies is worse than a record
    # that is missing, which is the same ruling `decide` makes in refusing to
    # write a blank note.
    write_json(run.manifest, manifest)

    append_decision(run.decisions, f"- {utc_stamp(now)} set-limit: {'; '.join(changes)} -- {text}")


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
