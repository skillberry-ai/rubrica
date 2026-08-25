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

import math
from dataclasses import dataclass
from html import escape
from pathlib import Path

# Imported rather than re-spelled, private names and all, for the reason
# `brief.py` gives where it imports `refs._as_list`: these four are the one
# definition each of "read it or return None", "a dict or nothing", "the dict
# members of a list" and "the string members of a list" in this build, and their
# docstrings carry the measurements that made them exist. A
# local copy would be a second spelling of a guard whose whole point is that
# there is one, and half a module's worth of inconsistent isinstance checks is
# the defect `_mapping` exists to have fixed.
from rubrica.brief import _dicts, _mapping, _quietly, _strings

# The one sort in this module that is not local to it. `dispositions` lists the
# admits in the order `admit_from_triage` will materialise them, and that order is
# `intake`'s to define: `_unique_artifact_id`'s collision suffixes depend on it and
# `refs.check_admitted_inputs` replays it, so a second spelling here would
# misdescribe which candidate became which `artifact_id` the first time the two
# drifted. It is also documented total, which is why nothing guards the call.
from rubrica.intake import admit_sort_key
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


@dataclass(frozen=True)
class StageRecord:
    stage: str
    model: str
    effort: str
    skill_sha256: str


@dataclass(frozen=True)
class Header:
    run_id: str
    created_utc: str
    schema_version: str
    # Deliberately not `int`: these come straight off a JSON document that may
    # have been hand-edited, and coercing a malformed limit would either raise
    # or invent a number. Whatever is there is rendered as what is there.
    max_rounds: object
    max_scenarios: object
    stages: list[StageRecord]


def header(run: RunPaths) -> Header | Absent:
    """The manifest's own facts, plus the per-stage reproducibility record.

    `manifest.stages` is the record of which model at which effort ran against
    which skill hash, which is the only thing on the page that says whether two
    runs are comparable at all -- so it is rendered even when a record exists for
    a stage the spine shows as absent, because that disagreement is a real
    finding (`stage-record-incomplete`, flags()) rather than a rendering bug to
    paper over.

    The run id comes from the manifest rather than from the directory name. The
    two agree in every run this code mints, and the manifest is still the right
    source: it is the run's own record of its identity, so a directory copied or
    renamed after the fact cannot relabel the page.
    """
    payload = _mapping(_quietly(run.manifest))
    if not payload:
        return Absent("manifest.json")
    limits = _mapping(payload.get("limits"))
    recorded = _mapping(payload.get("stages"))
    stages = []
    # `_mapping` twice over, at both depths a hand-edited manifest can break:
    # `"stages": "nope"` yields no records, and `"stages": {"extract": "nope"}`
    # yields a record whose fields are blank. Dropping the latter's row instead
    # would render as "no stage record", which is a different fact about the run
    # from "a stage record nothing could be read out of".
    for name, body in sorted(recorded.items()):
        entry = _mapping(body)
        stages.append(
            StageRecord(
                stage=name,
                model=str(entry.get("model", "")),
                effort=str(entry.get("effort", "")),
                skill_sha256=str(entry.get("skill_sha256", "")),
            )
        )
    return Header(
        run_id=str(payload.get("run_id", "")),
        created_utc=str(payload.get("created_utc", "")),
        schema_version=str(payload.get("schema_version", "")),
        max_rounds=limits.get("max_rounds"),
        max_scenarios=limits.get("max_scenarios"),
        stages=stages,
    )


def _as_int(value) -> int:
    """`value` as an int, or 0. A summed column must never raise on one row.

    Introduced here and reused by every later section that sums or sorts on a
    number read off a document, which is the reason it is one function: `bytes`,
    a coverage cell count and a round number all reach arithmetic, and `int()`
    raises ValueError on a non-numeric string and TypeError on None -- neither
    caught anywhere between a section builder and `main()`. Zero is the honest
    reading rather than a dropped row: the row still renders, and a byte count of
    0 beside a real file is visibly wrong to a reader in a way a traceback is
    not.

    **The `math.isfinite` guard is the third failure mode, and it is neither of
    those two exceptions.** `json.loads` accepts `Infinity`, `-Infinity` and
    `NaN` as bare tokens and `artifacts.read_json` calls it with defaults, so a
    non-finite float reaches here from any hand-edited artifact -- and
    `int(inf)` raises **OverflowError**, outside the tuple below. Measured
    end-to-end: a `manifest.json` carrying `"bytes": Infinity` made `inputs()`
    raise, breaking this module's promise never to raise on a readable run's
    content. `NaN` was already handled, since `int(nan)` raises ValueError; the
    explicit finite test is written out because "not finite" is the reason a
    reader needs for both, and this repo has ruled twice on exactly this token
    class in exactly this shape -- `smoke.components` and
    `suite.verify._is_number`, both of which reach for `math.isfinite` rather
    than for an exception.

    A float is the only shape that can be non-finite here, which is what makes
    one `isinstance` check enough rather than the precedents' fuller
    number-typing: every value reaching this function was produced by
    `json.loads`, and it turns a bare non-finite token into a `float` and
    nothing else. `bool` is not excluded, unlike in those two -- `True` is not a
    reward there, while here it is simply a malformed count that renders as 1
    rather than as a crash.
    """
    # Before int(), not after: OverflowError is not catchable by the tuple below
    # without claiming a fourth failure mode the caller cannot tell apart.
    if isinstance(value, float) and not math.isfinite(value):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class InputRow:
    artifact_id: str
    kind: str
    bytes_: int
    sha256: str
    source_path: str
    stored_as: str


@dataclass(frozen=True)
class Inputs:
    rows: list[InputRow]
    total_bytes: int
    kinds: dict[str, int]


def inputs(run: RunPaths) -> Inputs | Absent:
    """`manifest.inputs[]`, with bytes totalled and kinds tallied.

    In the manifest's own order, which is the order intake registered them in --
    `admit_from_triage` materialises by `admit_sort_key`, so on a run that came
    through triage the sequence here *is* the priority order, and re-sorting the
    rows would hide it.
    """
    payload = _mapping(_quietly(run.manifest))
    if not payload:
        return Absent("manifest.json")
    rows = []
    kinds: dict[str, int] = {}
    for member in _dicts(payload.get("inputs")):
        kind = str(member.get("kind", ""))
        kinds[kind] = kinds.get(kind, 0) + 1
        rows.append(
            InputRow(
                artifact_id=str(member.get("artifact_id", "")),
                kind=kind,
                # _as_int over a value that may be absent or a string: a
                # hand-edited manifest is the shape _dicts exists for, and a
                # bytes column that raises would take the whole page with it.
                bytes_=_as_int(member.get("bytes")),
                sha256=str(member.get("sha256", "")),
                source_path=str(member.get("source_path", "")),
                stored_as=str(member.get("stored_as", "")),
            )
        )
    return Inputs(rows=rows, total_bytes=sum(r.bytes_ for r in rows), kinds=kinds)


@dataclass(frozen=True)
class Surface:
    name: str
    evidence: list[str]
    candidates: int
    bytes_: int


@dataclass(frozen=True)
class Objective:
    declared: str
    # Deliberately not `bool` and not `int`, for `Header.max_rounds`' reason: both
    # come straight off a document that may have been hand-edited, and `supported`
    # is the field the whole gate-0 verdict turns on -- coercing a malformed one to
    # False would invent a verdict the pass never gave.
    supported: object
    predicted_count: object
    surfaces: list[Surface]


def objective(run: RunPaths) -> Objective | Absent:
    """The objective verdict and the surfaces the corpus map found.

    Read from `00-objective.json` rather than from the sealed triage record's copy
    of `objective_review`, for two reasons. The objective pass writes this one, so
    a run can hold it while `triage-seal` has not run yet -- six of the eleven runs
    measured at design time held nothing past intake. And the seal copies
    `objective_review` but *not* `predicted_surface_count`, so the sealed record
    cannot answer the divergence question this section exists to set up.
    """
    payload = _mapping(_quietly(run.objective))
    if not payload:
        return Absent("00-objective.json")
    review = _mapping(payload.get("objective_review"))
    surfaces = [
        Surface(
            name=str(member.get("name", "")),
            evidence=_strings(member.get("evidence")),
            candidates=_as_int(_mapping(member.get("weight")).get("candidates")),
            bytes_=_as_int(_mapping(member.get("weight")).get("bytes")),
        )
        for member in _dicts(review.get("surfaces"))
    ]
    return Objective(
        declared=str(review.get("declared_objective", "")),
        supported=review.get("supported"),
        predicted_count=payload.get("predicted_surface_count"),
        surfaces=surfaces,
    )


@dataclass(frozen=True)
class Dispositions:
    admits: list[dict]
    declines_by_reason: dict[str, list[dict]]
    admit_count: int
    decline_count: int


def dispositions(run: RunPaths) -> Dispositions | Absent:
    """Admits priority-sorted, declines grouped by reason code.

    `admit_sort_key` rather than a local sort, for the reason brief.py imports it:
    the priority order a human reads at gate 0 is one definition, and a second
    spelling of it here would drift from the first.
    """
    payload = _mapping(_quietly(run.triage))
    if not payload:
        return Absent("00-triage.json")
    admits: list[dict] = []
    declines: dict[str, list[dict]] = {}
    for member in _dicts(payload.get("dispositions")):
        if member.get("disposition") == "admit":
            admits.append(member)
        elif member.get("disposition") == "decline":
            code = member.get("reason_code")
            # `str(code) if code else "?"`, gate 0's own expression rather than a
            # variation on it: `reason_code` is *optional* in triage-0.1.json, so a
            # decline without one is a valid record and not a malformation, and an
            # empty group label on the page would read as a rendering bug instead
            # of as a fact about the record. str() on the key besides, because this
            # is grouped on and then sorted: a non-string code both risks being
            # unhashable and would make the sort compare str to int.
            declines.setdefault(str(code) if code else "?", []).append(member)
    # No try/except around this sort, deliberately. admit_sort_key is documented
    # total and coerces every value precisely so it cannot raise -- a non-integer
    # priority sorts as if absent and the id goes through repr(). Guarding it here
    # would assert a failure mode its docstring says it removed.
    admits.sort(key=admit_sort_key)
    return Dispositions(
        admits=admits,
        # Sorted rather than insertion-ordered: insertion order is whatever the
        # triage record listed, and two runs of the same pipeline must render the
        # same table for the page to be diffable.
        declines_by_reason=dict(sorted(declines.items())),
        admit_count=len(admits),
        decline_count=sum(len(v) for v in declines.values()),
    )


@dataclass(frozen=True)
class Deficiency:
    id_: str
    statement: str
    projection: str
    # The empty string, never None, when the record carries no `closed_by`: the
    # page renders this cell either way, and "" is the blank a reader reads as
    # open. `seal.seal` stamps the field on from an adoption, so it is the only
    # thing separating a deficiency a human has answered from one nothing has.
    closed_by: str


def deficiencies(run: RunPaths) -> list[Deficiency]:
    """Every deficiency the run recorded, each beside the projection that would
    close it.

    The sealed record if there is one, the audit part otherwise -- never both.
    `seal.seal` *copies* 00-audit.json's `deficiencies` and `projections` into
    00-triage.json, enriching them with `closed_by` and `satisfied_by` from any
    adoption, so a union over the two documents lists every deficiency of every
    sealed run twice; and a sealed run is not an edge case, it is every run that
    has reached gate 0. The sealed copy is also the strictly better one, since it
    is the only one carrying what a human adopted -- `closed_by` is stamped on by
    the seal from an adoption and is absent from the audit part by construction.

    A list rather than `Absent`: both documents are optional, and an empty list is
    the honest reading of a run that has neither.

    The pairing is by `closes`, which is a projection's *list* of the deficiency
    ids it would close -- `refs.check_triage` and gate 0 both read it that way, and
    it is the only field of a projection that names a deficiency at all. A
    deficiency with no projection renders the empty string, and that absence is
    the point: a deficiency nothing would close is the one gate 0 has to rule on
    unaided. The projection's id leads its text because that id is the argument
    `adopt-projection` takes, so the page names the next command rather than only
    the wish.
    """
    payload = _mapping(_quietly(run.triage)) or _mapping(_quietly(run.audit))
    if not payload:
        return []
    projections: dict[str, list[str]] = {}
    for proj in _dicts(payload.get("projections")):
        wanted = _mapping(proj.get("wanted")).get("statement", "")
        text = f"{proj.get('projection_id', '?')}: {wanted}"
        # _strings, not the raw list: a hand-edited `"closes": "def-1"` is a
        # string whose characters would each be taken for a deficiency id, and a
        # non-string member can be unhashable (`setdefault` raises TypeError on a
        # list key) while being unable to match an id that is a string anyway.
        for closes in _strings(proj.get("closes")):
            projections.setdefault(closes, []).append(text)
    found: list[Deficiency] = []
    for member in _dicts(payload.get("deficiencies")):
        did = str(member.get("deficiency_id", ""))
        found.append(
            Deficiency(
                id_=did,
                statement=str(member.get("statement", "")),
                projection="; ".join(projections.get(did, [])),
                closed_by=str(member.get("closed_by", "")),
            )
        )
    return found
