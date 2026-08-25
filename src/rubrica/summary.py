"""`run-summary`: one run directory rendered as a single HTML page.

A composer, not a new analysis -- the same ruling `brief.py` states for
`gate-brief`, and for the same reason. Every number here is read from an
artifact or is arithmetic over numbers read from artifacts, so the page is
reproducible and diffable, and nothing about producing it dispatches a model.

Partial runs are the primary case. Measured across the 11 run directories on
disk when this was designed: 1 reached an emitted suite, 2 had any scenarios, 4
had a world model, and 6 held nothing past intake. A summary that rendered only
complete runs would have been useless for 10 of the 11, so every section returns
`Absent` rather than raising when its artifact is missing, and the stage spine
leads the page because "how far did this get" is the first thing a reader of a
partial run needs.

`run_summary` never raises on a readable run's *content*, and the command always
exits 0 -- `claim_utilisation`'s ruling, restated for the same reason: a report
that reports "this document is malformed" by crashing is the least useful
reading of a document, and an orchestrator branching on the exit code of a
rendering would be branching on a rendering.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path

from rubrica.paths import STAGES, RunPaths

# The one tunable threshold in the flag table. Every other flag triggers on a
# count crossing zero or on a comparison between two fields, so it has nothing
# to tune. 50.0 splits the three runs measured at design time 2-to-1 (32.3% and
# 33.6% fire, 65.6% does not).
LOW_UTILISATION_PCT = 50.0


def esc(value) -> str:
    """`value` as HTML-safe text; `None` as the empty string.

    `quote=True` (escape's default) matters and is not incidental: verdict
    `notes` and a scenario's `discriminating_fact` are rendered into `title`
    attributes, and both carry double quotes in real runs -- an unescaped one
    ends the attribute and drops the rest of the prose into the tag.
    """
    if value is None:
        return ""
    return escape(str(value), quote=True)


@dataclass(frozen=True)
class Absent:
    """A section whose artifact is not there, carrying what was looked for.

    Returned rather than raised, and rendered rather than skipped: on a run that
    stopped at extract, "no world model" is the most informative thing the world
    model section can say, and a section silently omitted is indistinguishable
    from one the renderer forgot.
    """

    what: str


@dataclass(frozen=True)
class StageRow:
    name: str
    produced: bool


def _exists(path: Path) -> bool:
    """Whether `path` is there, treating an unreadable parent as absent.

    Not `list_json`, which raises `UsageError` on an unreadable directory: that
    is the right answer for a section that must report a count and the wrong one
    for the spine, whose whole job is to render on a run too incomplete to read.
    """
    try:
        return path.exists()
    except OSError:
        return False


def _has_part(directory: Path) -> bool:
    """Whether `directory` holds at least one thing a fan-out stage would write.

    A subdirectory counts, not only a `*.json` file, and that is not defensive
    breadth -- it is a measured fix. Two of the four fan-out stages write
    directories rather than files: `instantiate` writes
    `04-instances/<scenario_id>/seed.json` and `emit` writes
    `06-suite/<scenario_id>/task.toml`, so *no* `.json` file is ever a direct
    child of either. Counting only `.json` suffixes marked `instantiate` absent
    on a fully built toy run that had four instance directories, and would have
    done the same to `emit` on the one run of the eleven that reached a suite --
    the spine reporting "never ran" about the two stages a complete run is most
    read for.

    An unreadable directory is absence here for `_exists`'s reason: the spine's
    whole job is to render on a run too incomplete to read.
    """
    try:
        return any(p.suffix == ".json" or p.is_dir() for p in directory.iterdir())
    except OSError:
        return False


def _stage_evidence(run: RunPaths) -> dict[str, tuple]:
    """Per stage, the paths whose presence proves it ran.

    A fan-out stage's evidence is a directory with at least one part in it; a
    sealing stage's is one file. Keyed by every name in `paths.STAGES` so the
    spine cannot silently omit a stage added there -- a stage with no entry
    renders absent forever, which is why test_stage_spine_covers_every_declared
    _stage_in_order asserts against STAGES rather than against this mapping.

    Every path here comes from a `RunPaths` property, the six reconcile partials
    included, rather than being joined from a filename in this table: `paths.py`
    is the one home for every artifact path in this repo, so a rename there
    cannot leave a stale spelling behind here.
    """
    return {
        "survey": (run.catalogue,),
        "triage-slices": (run.slices, run.slices_dir),
        "triage-objective": (run.objective,),
        "triage-rule": (run.dispositions_dir,),
        "triage-audit": (run.audit,),
        "triage-seal": (run.triage,),
        "intake": (run.manifest,),
        "extract": (run.claims_dir,),
        "reconcile-subjects": (run.subjects,),
        "reconcile-contradict": (run.contradictions_dir,),
        "reconcile-capabilities": (run.capabilities_part,),
        "reconcile-outcomes": (run.outcomes_part,),
        "reconcile-entities": (run.entities_part,),
        "reconcile-goals": (run.goals_part,),
        "reconcile-gaps": (run.gaps_part,),
        "reconcile-seal": (run.world_model,),
        "propose": (run.scenarios,),
        "score": (run.coverage_dir,),
        "instantiate": (run.instances_dir,),
        "challenge": (run.verdicts_dir,),
        "emit": (run.suite_dir,),
        "smoke": (run.report,),
    }


def stage_spine(run: RunPaths) -> list[StageRow]:
    """Every stage in `paths.STAGES` order, marked produced or absent."""
    evidence = _stage_evidence(run)
    rows = []
    for stage in STAGES:
        paths = evidence.get(stage, ())
        produced = any(
            _has_part(path) if path.is_dir() else _exists(path) for path in paths if _exists(path)
        )
        rows.append(StageRow(name=stage, produced=produced))
    return rows
