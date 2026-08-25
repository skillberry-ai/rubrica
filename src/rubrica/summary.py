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
from rubrica.paths import STAGES, RunPaths, list_json

# The one place utilisation is computed in this build, imported rather than
# re-derived: `refs.check_claim_utilisation` and the `claim-utilisation`
# subcommand already read it from here, and a third spelling of the same
# arithmetic is how the gate and the report would come to disagree about what
# utilisation means. This module composes; it does not analyse.
from rubrica.utilisation import claim_utilisation

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


# Every collection the sealed world model can carry, in the order a reader wants
# them: what the target can do, what it does it to, who asks, why, then the two
# collections that are about the *evidence* rather than about the target. Keyed
# from this tuple rather than from the document's own keys so a count of 0 still
# renders -- "0 gaps" is a fact about the run, while a missing row is
# indistinguishable from a renderer that forgot the kind. Measured on the toy
# world model, which carries `"gaps": []`: keying off the payload would have
# dropped the gaps row from the one fixture the page is developed against.
_WORLD_MODEL_COLLECTIONS = (
    "capabilities",
    "entities",
    "actors",
    "goals",
    "gaps",
    "contradictions",
)


@dataclass(frozen=True)
class WorldModel:
    counts: dict[str, int]
    # Rendered as whatever they hold rather than unpacked into fields, for
    # `Header.max_rounds`' reason: both are small closed objects (`target` is
    # name/interface/notes, `denominator` is version/capability_cells/goals) that
    # the page prints key by key, and naming their fields here would be a second
    # spelling of world-model-0.1.json that a schema revision could silently
    # outdate.
    target: dict
    denominator: dict


def world_model(run: RunPaths) -> WorldModel | Absent:
    """The sealed world model's collection counts, plus target and denominator.

    Counts, not contents, for every collection but `gaps` -- `gaps()` below reads
    those in full because each one names the stages it blocks, which is the only
    thing on this page that says what the run cannot do. A capability list read in
    full would be the world model rendered rather than summarised.

    The `contradictions` count here is the *sealed* one, and `contradictions()`
    below tallies the fan-out parts instead. They are two different facts and both
    are rendered: the parts are what `reconcile-contradict` recorded, the sealed
    array is what survived the seal, and a divergence between them is a real
    finding about the run rather than a rendering to reconcile.
    """
    payload = _mapping(_quietly(run.world_model))
    if not payload:
        return Absent("01-world-model.json")
    # `_dicts` rather than `len(...)` on the raw value: a hand-edited
    # `"actors": "nope"` is not a list at all, and iterating it would count four
    # characters as four actors.
    counts = {name: len(_dicts(payload.get(name))) for name in _WORLD_MODEL_COLLECTIONS}
    return WorldModel(
        counts=counts,
        target=_mapping(payload.get("target")),
        denominator=_mapping(payload.get("denominator")),
    )


@dataclass(frozen=True)
class Utilisation:
    cited: int
    total: int
    # None, not 0.0, when nothing was extracted: 0% says every claim was dropped,
    # which is a judgment about the reconcile passes, and "no claims to cite" is a
    # different fact about the run. A claims file with an empty `claims` array is
    # schema-valid (claims-0.1.json sets no minItems), so this is reachable
    # without a hand edit.
    pct: float | None
    uncited: list[str]
    per_artifact: list[dict]


def utilisation(run: RunPaths) -> Utilisation | Absent:
    """Claim utilisation, from `claim_utilisation` rather than recomputed.

    The uncited artifacts are named rather than counted, because that is the
    actionable half: "18.4% overall" tells a reader the run is thin, and "these
    eleven inputs contributed nothing" tells them where to look. Measured across
    the three runs on disk at design time: 32.3%, 33.6%, 65.6%.

    `Absent` when the report holds no artifacts, which is the one state
    `claim_utilisation` documents for a run with no world model yet -- an empty
    report there means "the seal has not run", not "no input was cited", and a
    0-of-0 row on the page would assert the second.

    **`claim_utilisation` is not total, and the call is guarded for it.** It is a
    report with its own contract and its own callers, so it is guarded here rather
    than widened there. Seven shapes of a *readable* run were measured escaping it
    as exceptions, and this module's promise is that none of them raises:

    - a `01-claims/` member of `claims[]` that is a string -- `TypeError: string
      indices must be integers`, from `utilisation.py`'s bare `claim["id"]`;
    - a claim dict with no `id` -- `KeyError: 'id'`, same line;
    - `"claims": 7` -- `TypeError: 'int' object is not iterable`;
    - `01-claims/` unreadable -- `UsageError` from `list_json`, a ValueError and
      **not** an OSError, which is why the guard below cannot be `except OSError`;
    - a world-model group member that is a string, `"contradictions": ["oops"]`,
      and `"capabilities": "nope"` -- all three `AttributeError: 'str' object has
      no attribute 'get'`, from `_cited_claim_ids`' bare `.get` over group members.

    The absence names both artifacts because either can be the unreadable one, and
    the reading is different from the no-world-model absence above: there, nothing
    is wrong with the run; here, something in it could not be read.
    """
    try:
        report = _mapping(claim_utilisation(run))
    except Exception:  # deliberate: the seven measured shapes named in the docstring
        return Absent("claim utilisation (01-claims/ or 01-world-model.json unreadable)")
    artifacts = _dicts(report.get("artifacts"))
    if not artifacts:
        return Absent("claim utilisation (no world model yet)")
    # _as_int over both columns: these come from claim_utilisation, which builds
    # them itself, but they are summed here and a summed column must not raise --
    # and the same reading is what makes the `cited == 0` filter below total.
    cited = sum(_as_int(a.get("cited")) for a in artifacts)
    total = sum(_as_int(a.get("total")) for a in artifacts)
    return Utilisation(
        cited=cited,
        total=total,
        pct=(cited / total * 100) if total else None,
        # `total and cited == 0`, which is `refs.check_claim_utilisation`'s
        # predicate and not a variation on it. The `total` guard is the load-bearing
        # half: `rb-extract` is explicitly allowed to produce nothing for an input
        # with nothing to extract, so a 0-of-0 artifact is not a finding there --
        # and the comment above that gate says why exempting it is not a hole,
        # namely that the artifact still appears in the report for a human at gate
        # 1 to see. Dropping the guard here would name inputs the gate deliberately
        # exempts, which is the disagreement this docstring claims not to have; the
        # row is still in `per_artifact`, so the page still shows it.
        uncited=[
            str(a.get("artifact_id", ""))
            for a in artifacts
            if _as_int(a.get("total")) and _as_int(a.get("cited")) == 0
        ],
        # The report's own rows, unmodified and in its own order, which is
        # `list_json(run.claims_dir)`'s sort. Re-sorting them here would make the
        # page disagree with the `claim-utilisation` subcommand a reader runs
        # beside it.
        per_artifact=artifacts,
    )


@dataclass(frozen=True)
class Gap:
    id_: str
    subject: str
    blocks: list[str]
    unknown: str
    # `why_it_matters` in the schema, `why` here: the field is rendered under a
    # column header on a page whose width is a real constraint, and this dataclass
    # is the one place the two spellings meet.
    why: str


def gaps(run: RunPaths) -> list[Gap]:
    """Every gap, with the stages it blocks.

    `blocks` is a column rather than a flag. Measured at design time: every gap
    in every run on disk carried a non-empty `blocks` (8 of 8, 19 of 19, 15 of
    15), so a flag on it would fire always and discriminate nothing.

    A list rather than `Absent`, matching `deficiencies`: an empty list is the
    honest reading of both a run with no world model and a run whose world model
    records no gap, and the section above already says which of the two it is --
    `world_model` returns `Absent` for the first and a `gaps: 0` count for the
    second.
    """
    payload = _mapping(_quietly(run.world_model))
    return [
        Gap(
            id_=str(member.get("id", "")),
            subject=str(member.get("subject", "")),
            blocks=_strings(member.get("blocks")),
            unknown=str(member.get("unknown", "")),
            why=str(member.get("why_it_matters", "")),
        )
        for member in _dicts(payload.get("gaps"))
    ]


@dataclass(frozen=True)
class Contradictions:
    total: int
    by_resolution: dict[str, int]
    parts_swept: int


def contradictions(run: RunPaths) -> Contradictions | Absent:
    """A tally over `01-contradictions/`, never the contradictions themselves.

    An aggregate on purpose -- the ruling gate-brief already makes: this is a
    pointer at the directory rather than a substitute for reading it.

    **`resolution` is nested inside each member of a part's `contradictions[]`,
    not a top-level field of the part.** A part is `{schema_version, subject_id,
    contradictions[]}`, and contradictions-part-0.1.json closes it with
    `additionalProperties: false`, so a top-level `resolution` cannot exist on a
    valid part at all. Reading it off the part was measured against the real parts
    during design and tallied `{"null": 14}` for a run whose actual tally is
    `both_possible=1 preferred_a=1 preferred_b=1`.

    `unresolved` is named at zero whenever this renders at all, because a
    non-zero unresolved is the cheapest signal that a part is worth opening and a
    reader scanning for it must not have to infer its absence from a missing key.

    `parts_swept` counts every part, including the ones recording no
    disagreement: an empty `contradictions` array is a real record -- the schema
    says so where it declines to set `minItems` -- and it is what separates "this
    subject was swept and was clean" from "this subject was never swept".
    """
    try:
        parts = list_json(run.contradictions_dir)
    except Exception:  # deliberate: list_json raises UsageError, which is not an OSError
        return Absent("01-contradictions/")
    # An existing directory holding no part is absence too: `reconcile-contradict`
    # writes one file per subject, so a directory with nothing in it has the same
    # meaning for this section as no directory at all.
    if not parts:
        return Absent("01-contradictions/")
    by_resolution: dict[str, int] = {"unresolved": 0}
    total = 0
    for path in parts:
        part = _mapping(_quietly(path))
        for member in _dicts(part.get("contradictions")):
            total += 1
            # `or "(unrecorded)"` catches both the missing key and an empty
            # string. `resolution` is required by the schema, so this is the
            # hand-edited case -- and a blank group label on the page would read
            # as a rendering bug rather than as a fact about the record, which is
            # the ruling `dispositions` makes for a decline with no reason code.
            key = str(member.get("resolution", "")) or "(unrecorded)"
            by_resolution[key] = by_resolution.get(key, 0) + 1
    return Contradictions(
        total=total,
        # Sorted for `dispositions`' reason: two runs over the same parts must
        # render the same table for the page to be diffable, and a dict keyed in
        # first-seen order is keyed by whichever subject sorted first.
        by_resolution=dict(sorted(by_resolution.items())),
        parts_swept=len(parts),
    )
