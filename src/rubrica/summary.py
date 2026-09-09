"""`run-summary`: one run directory rendered as a single HTML page.

A composer, not a new analysis -- the same ruling `brief.py` states for
`gate-brief`, and for the same reason. Every number here is read from an
artifact or is arithmetic over numbers read from artifacts, so the page is
reproducible and diffable, and nothing about producing it dispatches a model.

Partial runs are the primary case. Measured across the 11 run directories on
disk when this was designed: 1 reached an emitted suite, 2 had any scenarios, 4
had a world model, and 6 held nothing past intake. A summary that rendered only
complete runs would have been useless for 10 of the 11, so every section returns
a marker rather than raising when it cannot build a body -- `Absent` when the
artifact is not there and `Malformed` when it is there and unreadable, which the
spine's existence test makes two different facts -- and the stage spine leads the
page because "how far did this get" is the first thing a reader of a partial run
needs.

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
from rubrica.paths import STAGES, RunPaths, is_safe_segment, list_json

# The implied suite size, composed rather than recomputed for `claim_utilisation`'s
# reason: `gate-brief` reports this same number at gates 1 and 2, and a second
# spelling of the acceptance-allowance arithmetic here is how the page and the gate
# would come to disagree about one run. It is not total -- see `coverage`'s
# docstring for the shape measured escaping it, and the guard at its call site.
from rubrica.sizing import implied_size

# The one place utilisation is computed in this build, imported rather than
# re-derived: `refs.check_claim_utilisation` and the `claim-utilisation`
# subcommand already read it from here, and a third spelling of the same
# arithmetic is how the gate and the report would come to disagree about what
# utilisation means. This module composes; it does not analyse.
from rubrica.utilisation import claim_utilisation

# The tolerant reader, not `waived_subjects`: a waiver is a human's ruling that a
# finding is correct and unrepairable where it was raised, and a page that reported
# a ruled-on finding as an open problem is the page and the gate disagreeing about
# one run in judgment rather than in arithmetic. Tolerant because `run-summary` is a
# report -- see the accessor's docstring for why raising here would be a new way for
# it to fail on a run it can otherwise read.
from rubrica.waivers import waived_subjects_quietly

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

    **A lone surrogate is turned into text here, and this is the one place that
    decides it.** `html.escape` does not touch surrogates, and the page is written
    with `Path.write_text(..., encoding="utf-8")`, which cannot encode one:
    `UnicodeEncodeError` is a `ValueError`, so it escaped every handler in
    `cli.py` but the catch-all and made a *report* exit 1 -- with an `[internal]`
    finding advising `rubrica validate --stage <stage>`, which no stage can act
    on, and after the page had already rendered completely and correctly. Three
    independent sources were measured, which is why the decision is here rather
    than at any one of them: artifact JSON content, since `json.loads('"\\udcff"')`
    returns the lone surrogate and `artifacts.read_json` accepts it by default
    exactly as it accepts `Infinity`; a non-UTF-8 filename under the run root,
    which `Path.iterdir` surrogate-escapes into `orphaned_temp_files`; and the run
    directory's own name, which the page's `<title>` and `<h1>` interpolate. Fixing
    it at the write instead would have left the page's one escaping rule with an
    exception, and `artifacts.read_json` has already ruled on this class in this
    shape at the *reading* end -- bytes that are not UTF-8 are malformed content,
    reported against the path that holds them rather than raised past the handler
    that knows one.

    `backslashreplace` rather than `replace`: the surrogate renders as the six
    characters `\\udcff`, which is the escape `os.fsdecode` produced and a reader
    can recognise as a byte that was never text, where `?` or U+FFFD would erase
    which byte it was.
    """
    if value is None:
        return ""
    # Encode-then-decode is the identity for every string that is already text,
    # so this costs one round trip and changes nothing but the surrogates.
    text = str(value).encode("utf-8", "backslashreplace").decode("utf-8")
    return escape(text, quote=True)


@dataclass(frozen=True)
class Absent:
    """A section whose artifact is not there, carrying what was looked for.

    Returned rather than raised, and rendered rather than skipped: on a run that
    stopped at extract, "no world model" is the most informative thing the world
    model section can say, and a section silently omitted is indistinguishable
    from one the renderer forgot.

    **Not there, never there-but-unreadable** -- that second state is `Malformed`
    below, and the two were one word until a run measured with `02-scenarios.json`
    holding `[]` and a garbage `latest.json` said, on one page, that `propose` and
    `score` had produced an artifact *and* that neither artifact was present. The
    spine tests existence and a section tests readability, so a page that spells
    both absences the same asserts a contradiction it never reconciles.
    """

    what: str
    # The reading, when the artifact's name is not the whole fact: `utilisation`
    # is absent because "the seal has not run", which names no artifact at all. A
    # field rather than a sentence folded into `what`, so that every marker's
    # `what` is the artifact and nothing else -- before this, ten of the twelve
    # were bare paths and two were prose, and nothing said which a reader should
    # expect.
    why: str = ""


@dataclass(frozen=True)
class Malformed:
    """An artifact that is *there* and that nothing could be read out of.

    A sibling of `Absent` rather than a subclass of it: the two are different
    facts about a run, and an `isinstance(x, Absent)` that quietly answered True
    for both is how the distinction this class exists to draw would be lost again
    at the first call site that forgot. `Marker` below is what the renderer tests
    when it only needs to know that a body was not built.

    The same reading `artifacts.read_json` takes on bytes that are not UTF-8:
    malformed content, reported against the path that holds it. What differs is
    that a report cannot raise -- so this is returned, rendered, and named.
    """

    what: str
    why: str = ""


# What a section builder returns in place of a body. Spelled once so the renderer
# can ask "is there a body?" without enumerating the marker types at eleven call
# sites, and so adding a third marker cannot leave one of them behind.
Marker = Absent | Malformed


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


def _absent_or_malformed(path: Path, what: str, why: str) -> Marker:
    """`Absent` when the artifact is not there, `Malformed` when it is unreadable.

    The one place the distinction is decided, so that every section draws it the
    same way and the spine above cannot disagree with a section below: the spine
    marks a stage produced when its evidence *exists*, which is exactly the test
    made here, so an artifact the spine counts is one this returns `Malformed`
    for rather than `Absent`.

    `_exists` rather than a bare `Path.exists()`, for that helper's reason: a run
    root at mode 000 makes the stat raise, and "not there" is the honest answer
    for a section that cannot see the artifact at all.
    """
    if _exists(path):
        return Malformed(what, why)
    return Absent(what)


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


def _stage_evidence(run: RunPaths) -> dict[str, tuple[Path, ...]]:
    """Per stage, the paths whose presence proves it ran.

    A fan-out stage's evidence is a directory with at least one part in it; a
    sealing stage's is one file. Keyed by every name in `paths.STAGES` so the
    spine cannot silently omit a stage added there -- a stage with no entry
    renders absent forever, which is why
    test_stage_spine_covers_every_declared_stage_in_order asserts against STAGES
    rather than against this mapping.

    Every path here comes from a `RunPaths` property, every reconcile partial
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
        "reconcile-services": (run.services_part,),
        "synthesise-interfaces": (run.interfaces_dir,),
        "reconcile-seal": (run.world_model,),
        "propose-batches": (run.batches_dir,),
        "propose": (run.scenario_parts_dir,),
        "propose-seal": (run.scenarios,),
        "score": (run.score_parts_dir,),
        "score-seal": (run.coverage_dir,),
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
            # The filter has already proved the path stat-able, so a non-directory
            # is evidence by existing: the `else _exists(path)` this replaces could
            # only ever be True, and asking cost a second stat of every path.
            # `path.is_dir()` is safe only *inside* the filter -- it raises EACCES,
            # which is why `_exists` exists at all.
            not path.is_dir() or _has_part(path)
            for path in paths
            if _exists(path)
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
    # The third limit, and the only optional one: manifest-0.1.json does not
    # require it, so an absent value means rounds.DEFAULT_SCENARIO_PART_BYTES
    # rather than "no bound". Surfaced here because it is the dial that decides
    # how finely a round's holes were partitioned, and two runs whose scenario
    # counts differ for that reason alone were otherwise indistinguishable on
    # this page -- `_val` renders the absence explicitly, so a reader can tell a
    # run that set it from one that took the default.
    max_scenario_part_bytes: object
    stages: list[StageRecord]


def header(run: RunPaths) -> Header | Marker:
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
        return _absent_or_malformed(run.manifest, "manifest.json", "nothing could be read from it")
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
        max_scenario_part_bytes=limits.get("max_scenario_part_bytes"),
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


def _ints(value) -> list[int]:
    """The int members of `value`, or `[]` if it is not a list at all.

    `_strings`' and `_dicts`' sibling for the one field family whose elements are
    numbers: a goal row's `hop_depths_present` and `hop_depths_expected`. The
    measured failure is theirs exactly -- a hand-edited `"hop_depths_present":
    "two"` is iterable, and iterating it yields the characters `t`, `w`, `o`, each
    of which would head a column of the goal matrix.

    **`bool` is excluded here and deliberately not in `_as_int` above.** The two
    differ because the value is *displayed* rather than summed: `isinstance(True,
    int)` is true, so the plain member test admits `[true, 2]` and draws a column
    headed `hop True`. A malformed count rendering as 1 is a wrong number a reader
    can catch against its neighbours; a column headed with a word is a rendering
    bug wearing a document's clothes. Excluded by type rather than by the schema's
    1..5 range, because a depth outside that range is a `score` defect for
    `validate` to name and dropping it here would hide it.
    """
    if not isinstance(value, list):
        return []
    return [member for member in value if isinstance(member, int) and not isinstance(member, bool)]


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


def inputs(run: RunPaths) -> Inputs | Marker:
    """`manifest.inputs[]`, with bytes totalled and kinds tallied.

    In the manifest's own order, which is the order intake registered them in --
    `admit_from_triage` materialises by `admit_sort_key`, so on a run that came
    through triage the sequence here *is* the priority order, and re-sorting the
    rows would hide it.
    """
    payload = _mapping(_quietly(run.manifest))
    if not payload:
        return _absent_or_malformed(run.manifest, "manifest.json", "nothing could be read from it")
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


def objective(run: RunPaths) -> Objective | Marker:
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
        return _absent_or_malformed(
            run.objective, "00-objective.json", "nothing could be read from it"
        )
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


def dispositions(run: RunPaths) -> Dispositions | Marker:
    """Admits priority-sorted, declines grouped by reason code.

    `admit_sort_key` rather than a local sort, for the reason brief.py imports it:
    the priority order a human reads at gate 0 is one definition, and a second
    spelling of it here would drift from the first.
    """
    payload = _mapping(_quietly(run.triage))
    if not payload:
        return _absent_or_malformed(run.triage, "00-triage.json", "nothing could be read from it")
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
# them: what the target can do, what it does it to, who asks, why, what a
# simulator would stand in for, then the two collections that are about the
# *evidence* rather than about the target. Keyed from this tuple rather than from
# the document's own keys so a count of 0 still renders -- "0 gaps" is a fact about
# the run, while a missing row is indistinguishable from a renderer that forgot the
# kind. Measured on the toy world model, which carries `"gaps": []`: keying off the
# payload would have dropped the gaps row from the one fixture the page is
# developed against.
#
# `services` is the one key a *conforming* sealed model may omit entirely -- the seal
# writes it only when 01-services.json exists -- so it is the one row where the
# document's silence is the ordinary case rather than a hand edit. The row is still
# keyed from here and still rendered, but its value is None rather than 0 in that
# state; see `world_model` below for why 0 would have been a false report.
_WORLD_MODEL_COLLECTIONS = (
    "capabilities",
    "entities",
    "actors",
    "goals",
    "services",
    "gaps",
    "contradictions",
)


@dataclass(frozen=True)
class WorldModel:
    # `int | None`, and the None is load-bearing: a collection key the document does
    # not carry at all counts as None, never as 0. See `world_model` below.
    counts: dict[str, int | None]
    # Rendered as whatever they hold rather than unpacked into fields, for
    # `Header.max_rounds`' reason: both are small closed objects (`target` is
    # name/interface/notes, `denominator` is version/capability_cells/goals) that
    # the page prints key by key, and naming their fields here would be a second
    # spelling of world-model-0.1.json that a schema revision could silently
    # outdate.
    target: dict
    denominator: dict


def world_model(run: RunPaths) -> WorldModel | Marker:
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

    **A count of None means the document carries no such key, and it is not the same
    fact as 0.** `services` is where this bites, because it is the one key a
    conforming sealed model omits: `reconcile-seal` writes it only when
    01-services.json exists, and it deliberately omits it rather than writing `[]`,
    because an empty array asserts that a pass looked and found no tools while
    absence says no pass ran. Collapsing both to 0 here would erase on the page the
    exact distinction the artifact shape exists to preserve -- so this is `Absent`
    versus `Malformed` one level down, and the same ruling as the `manifest.stages`
    record that renders blank fields rather than dropping its row.

    The rule is applied to every collection rather than special-cased for
    `services`, because it is the honest reading for all of them: for the other six
    a missing key means a hand-edited or truncated model, which is again a different
    fact about the run from an empty array. A key that is present but not a list
    still counts 0 -- `_dicts` owns that shape, and "carries something unreadable as
    a collection" is the malformed case layer 1 rejects, not an absent key.
    """
    payload = _mapping(_quietly(run.world_model))
    if not payload:
        return _absent_or_malformed(
            run.world_model, "01-world-model.json", "nothing could be read from it"
        )
    # `_dicts` rather than `len(...)` on the raw value: a hand-edited
    # `"actors": "nope"` is not a list at all, and iterating it would count four
    # characters as four actors.
    #
    # `name in payload` before the length, so an absent key is None and an empty
    # array is 0: the docstring above is the whole argument, and a `.get(name, [])`
    # here is exactly the collapse it forbids.
    counts: dict[str, int | None] = {
        name: (len(_dicts(payload[name])) if name in payload else None)
        for name in _WORLD_MODEL_COLLECTIONS
    }
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
    # The inputs whose claims nothing cites and on which *nobody has ruled*, which
    # is `check-refs`' judgment and not merely its arithmetic. A waived subject is
    # in `waived` below instead, so the two lists are disjoint and their union is
    # the raw `total and cited == 0` set.
    uncited: list[str]
    # The same predicate's members a human waived. Kept beside `uncited` rather
    # than folded into it or dropped: a waived finding still prints from
    # `check-refs`, so a page that showed nothing at all would be the mute button
    # the waiver design refuses -- it just must not be listed as an open problem.
    waived: list[str]
    per_artifact: list[dict]


def utilisation(run: RunPaths) -> Utilisation | Marker:
    """Claim utilisation, from `claim_utilisation` rather than recomputed.

    The uncited artifacts are named rather than counted, because that is the
    actionable half: "18.4% overall" tells a reader the run is thin, and "these
    eleven inputs contributed nothing" tells them where to look. Measured across
    the three runs on disk at design time: 32.3%, 33.6%, 65.6%.

    They are split into `uncited` and `waived` for the reason the arithmetic is
    imported rather than rewritten: `check-refs` prints a waived finding and does
    not let it set the exit code, so a page listing that same input among the open
    ones disagrees with the gate about one run -- measured, on a run where
    `check-refs` exited 0. The split is on the human's ruling only; the predicate
    underneath is unchanged, and both lists still appear on the page.

    `Absent` when the report holds no artifacts, which is the one state
    `claim_utilisation` documents for a run with no world model yet -- an empty
    report there means "the seal has not run", not "no input was cited", and a
    0-of-0 row on the page would assert the second.

    **`claim_utilisation` is not total, and the call is guarded for it.** It reads
    every `01-claims/` document to get each input's denominator, and it indexes
    into those documents bare. These shapes of a *readable* run were measured
    escaping it as exceptions, and this module's promise is that none of them
    raises:

    - a `01-claims/` member of `claims[]` that is a string -- `TypeError: string
      indices must be integers`, from `utilisation.py`'s bare `claim["id"]`;
    - a claim dict with no `id` -- `KeyError: 'id'`, same line;
    - `"claims": 7` -- `TypeError: 'int' object is not iterable`;
    - `01-claims/` unreadable -- `UsageError` from `list_json`, a ValueError and
      **not** an OSError, which is why the guard below cannot be `except OSError`.

    Three world-model shapes used to be on that list -- a group member that is a
    string, `"contradictions": ["oops"]`, `"capabilities": "nope"`, all three
    `AttributeError: 'str' object has no attribute 'get'` out of
    `_cited_claim_ids`. Issue #6 widened `utilisation.py` for those instead of
    guarding them here, because `claim-utilisation` and `gate-brief` are reports
    that must exit 0 on a readable run and neither has a findings channel to report
    a malformed document through. They no longer reach this guard, and this page
    renders the numbers computed over what the walk could read rather than a
    marker.

    **That contract argument reaches the three hand-edited-document shapes above
    just as far**: each takes both reports to exit 1 on a readable run, and
    `utilisation.py` says so beside the unguarded line. What kept them here is
    scope and authorisation, not the contract -- issue #6 widened the world-model
    walk and never touched the `01-claims/` path, the ruling being overturned was
    written specifically about these shapes with this page's marker attached to
    them, and only the world-model half was ruled in. So this guard is the whole
    answer for them *for now*, and it is a known-wrong thing rather than a settled
    one -- which belongs in `docs/design/limitations.md`, where this project keeps
    what it knows is wrong, rather than only in a comment beside the code.

    **The fourth bullet is not part of that hole, and closing it would be a
    regression.** An unreadable `01-claims/` is a filesystem problem, and the
    exit-code contract's ruling for one is **exit 2** -- measured, both reports exit
    2 on it, because `list_json`'s `UsageError` reaches `cli.py`'s
    `(OSError, UsageError, ArtifactError, UnknownStage)` arm rather than the
    catch-all. That is the contract working, not breaching: guarding it in
    `utilisation.py` would turn a run whose claims cannot be read into an exit 0
    reporting empty utilisation, which is the one reading a human at gate 1 must
    never be handed. It is caught *here* only so this page renders a marker instead
    of crashing, which is a promise about the page and not about an exit code.

    The absence names both artifacts because either can be the unreadable one, and
    the reading is different from the no-world-model absence above: there, nothing
    is wrong with the run; here, something in it could not be read.
    """
    try:
        report = _mapping(claim_utilisation(run))
    except Exception:  # deliberate: the 01-claims/ shapes named in the docstring
        return Malformed("claim utilisation", "01-claims/ or 01-world-model.json unreadable")
    artifacts = _dicts(report.get("artifacts"))
    if not artifacts:
        return Absent("claim utilisation", "no world model yet")
    # _as_int over both columns: these come from claim_utilisation, which builds
    # them itself, but they are summed here and a summed column must not raise --
    # and the same reading is what makes the `total and cited == 0` filter below
    # total.
    cited = sum(_as_int(a.get("cited")) for a in artifacts)
    total = sum(_as_int(a.get("total")) for a in artifacts)
    raw_uncited = [
        str(a.get("artifact_id", ""))
        for a in artifacts
        if _as_int(a.get("total")) and _as_int(a.get("cited")) == 0
    ]
    # Read tolerantly, never through `waivers.load`: this command exits 0 on a run
    # it cannot read at all, and a malformed waivers.json must not be the one
    # content shape that changes that. `check-refs` raises its exit 2 on the same
    # file, so nothing goes unreported.
    waived = waived_subjects_quietly(run, "claim-utilisation")
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
        #
        # Split on the waiver, for the same reason the predicate is imported rather
        # than reinvented: mirroring the gate's arithmetic while ignoring its
        # *judgment* was measured producing exactly the disagreement above -- a run
        # where `check-refs` exited 0 with a `[waived] ` line while this page called
        # the same input an open problem with nothing marking it as ruled on.
        uncited=[a for a in raw_uncited if a not in waived],
        waived=[a for a in raw_uncited if a in waived],
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


def contradictions(run: RunPaths) -> Contradictions | Marker:
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
        # `list_json` answers `[]` for a directory that is not there and *raises*
        # for one it cannot list, so reaching this handler means the directory
        # exists -- except when the run root itself is unreadable, which is what
        # `_absent_or_malformed` re-tests rather than assuming.
        return _absent_or_malformed(
            run.contradictions_dir, "01-contradictions/", "the directory could not be listed"
        )
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


@dataclass(frozen=True)
class RoundRow:
    round_: object
    verdict: str
    cells_covered: int
    cells_total: int
    # `object`, not `float`: see the comment at the assignment in `_round_row`.
    pct: object
    goals_covered: int
    goals_total: int
    # `object` for the same reason as `pct`, and both are `progress` fields rather
    # than matrix fields: rendering a hand-edited `new_cells_this_round: "two"` as
    # `0` would say the round made no progress, which is a claim about the run
    # rather than a claim about the document.
    new_cells: object
    rounds_without_progress: object
    holes: int


@dataclass(frozen=True)
class Cell:
    capability_id: str
    outcome_class_id: str
    covered: bool
    scenario_ids: list[str]


@dataclass(frozen=True)
class GoalRow:
    goal_id: str
    scenario_ids: list[str]
    # `present` and `expected` rather than the document's `hop_depths_present` and
    # `hop_depths_expected`: the pair is read together at every call site, and the
    # long names made the renderer's set arithmetic unreadable. The *document*
    # keeps its field names; this is the in-memory shape.
    present: list[int]
    expected: list[int]
    # Carried as `score` wrote it rather than recomputed from the two lists. The
    # arithmetic looks obvious -- covered iff `expected` is a subset of `present` --
    # and it is `rb-score`'s to own: a page that recomputed it would report its own
    # opinion of coverage and silently agree with the document on every run where
    # the two happen to match. If they ever diverge, that is a score defect, and
    # this field is what makes it visible rather than what hides it.
    covered: bool


@dataclass(frozen=True)
class Hole:
    ref: str
    reason: str
    justification: str


@dataclass(frozen=True)
class Coverage:
    rounds: list[RoundRow]
    terminal_verdict: str
    cells: list[Cell]
    goals: list[GoalRow]
    holes: list[Hole]
    # None in three situations that share one return value: no world model yet, a
    # world model `implied_size` could not read, and the one shape measured
    # escaping it as an exception -- see `coverage`'s docstring. All three read the
    # same way on the page ("not computed"), and separating them would put a
    # sizing diagnostic's failure modes on a page that composes rather than
    # analyses.
    implied: dict | None


def _round_row(doc: dict) -> RoundRow:
    """One row from one coverage document, `latest.json` included.

    Split out rather than inlined because `latest` is read through it too: the
    fallback below builds a row from `latest` when no `round-N.json` is readable,
    and two spellings of the same ten columns is how the fallback row would come
    to disagree with the rows beside it.
    """
    caps = _mapping(doc.get("capability_matrix"))
    goals = _mapping(doc.get("goal_matrix"))
    progress = _mapping(doc.get("progress"))
    return RoundRow(
        # Passed through rather than `_as_int`'d, unlike the sort key below: a
        # document saying `"round": "two"` must render "two", because `0` beside a
        # readable file reads as a rendering bug rather than as the score-stage
        # defect it is. The sort reads the same value through `_as_int` precisely
        # so that this one can stay uncoerced.
        round_=doc.get("round"),
        verdict=str(doc.get("verdict", "")),
        cells_covered=_as_int(caps.get("covered")),
        cells_total=_as_int(caps.get("total")),
        # pct is passed through rather than coerced: a non-numeric pct is a
        # score-stage defect for `validate` to name, and rendering the value the
        # file actually holds is more use to a reader than rendering 0.
        pct=caps.get("pct"),
        goals_covered=_as_int(goals.get("covered")),
        goals_total=_as_int(goals.get("total")),
        new_cells=progress.get("new_cells_this_round"),
        rounds_without_progress=progress.get("rounds_without_progress"),
        # Counted from `holes[]` rather than read from a field, because the
        # document has no hole count to read: `holes` is the array itself, and
        # `_dicts` is what keeps a hand-edited `"holes": "nope"` from being counted
        # as four.
        holes=len(_dicts(doc.get("holes"))),
    )


def coverage(run: RunPaths) -> Coverage | Marker:
    """The round progression, the capability matrix, the holes, the implied size.

    Rows come from the `round-N.json` documents so the progression is visible;
    the matrix and holes come from `latest.json`, which is the state the run
    ended in. A run holding only `latest.json` still renders one row, because
    `latest` is a round document too -- the fallback is on the *rows*, not on the
    paths, so a run whose only round document is corrupt still reports where it
    ended rather than reporting that it ran no rounds.

    **`implied_size` is not total, and the call is guarded for it** -- the same
    finding `utilisation` above records against `claim_utilisation`, in a different
    place in the callee. `sizing.py` wraps its reads in `except Exception`, but
    `ceiling_binding` is computed in the `return` statement *below* that handler,
    so a hand-edited `manifest.limits.max_scenarios` that is not a number raises
    from `implied > ceiling`: measured `TypeError: '>' not supported between
    instances of 'int' and 'str'` for `"eight"`, and the same for `None` and for a
    list. A second shape was measured too, `PermissionError` from
    `run.world_model.is_file()` on a run root with mode 000 -- `Path.is_file`
    ignores ENOENT and ENOTDIR but not EACCES. Which permission layouts let that
    one reach *this* section is not something this docstring asserts either way:
    it was measured escaping `sizing.py`, and the guard below covers it because it
    catches the class rather than the instance.

    Guarded here rather than widened in `sizing.py`: that module is a report with
    its own contract and its own callers (`gate-brief` at gates 1 and 2), and
    changing what it raises is a change to theirs.
    """
    latest = _mapping(_quietly(run.coverage_latest))
    try:
        round_paths = [p for p in list_json(run.coverage_dir) if p.name != "latest.json"]
    except Exception:  # deliberate: list_json raises UsageError, which is not an OSError
        round_paths = []
    if not latest and not round_paths:
        # The directory being there with nothing readable in it is the shape this
        # distinction was measured on: a garbage `latest.json` and no round
        # document left the spine bolding `score` while this section said the
        # directory was not present.
        return _absent_or_malformed(
            run.coverage_dir, "03-coverage/", "no round document could be read"
        )

    rows = []
    for path in round_paths:
        doc = _mapping(_quietly(path))
        # A document that could not be read contributes no row rather than a row of
        # zeros: an all-zero round reads as a round that made no progress, which is
        # a statement about the run, and "this file is broken" is not.
        if doc:
            rows.append(_round_row(doc))
    if not rows and latest:
        rows.append(_round_row(latest))
    # Sorted on the number rather than left in `list_json`'s order, which is by
    # name: `round-10.json` sorts before `round-2.json`, so a run that reached ten
    # rounds would render its progression out of order. `_as_int` is what makes the
    # key total over a hand-edited `"round": "two"`.
    rows.sort(key=lambda r: _as_int(r.round_))

    caps = _mapping(latest.get("capability_matrix"))
    goals_matrix = _mapping(latest.get("goal_matrix"))
    cells = [
        Cell(
            capability_id=str(member.get("capability_id", "")),
            outcome_class_id=str(member.get("outcome_class_id", "")),
            covered=bool(member.get("covered")),
            scenario_ids=_strings(member.get("scenario_ids")),
        )
        for member in _dicts(caps.get("cells"))
    ]
    # `latest`'s, for the reason the cells are: it is the state the run ended in.
    # Document order, like the cells and the holes -- re-sorting would make the
    # page disagree with the file a reader opens beside it.
    goals = [
        GoalRow(
            goal_id=str(member.get("goal_id", "")),
            scenario_ids=_strings(member.get("scenario_ids")),
            present=_ints(member.get("hop_depths_present")),
            expected=_ints(member.get("hop_depths_expected")),
            covered=bool(member.get("covered")),
        )
        for member in _dicts(goals_matrix.get("rows"))
    ]
    holes = [
        Hole(
            ref=str(member.get("ref", "")),
            reason=str(member.get("reason", "")),
            # Carried in full, not summarised: the reason is a closed enum a reader
            # scans, and the justification is the sentence that says why *this*
            # cell was left open, which is the half a human at gate 2 acts on.
            justification=str(member.get("justification", "")),
        )
        for member in _dicts(latest.get("holes"))
    ]
    try:
        implied = implied_size(run)
    except Exception:  # deliberate: the non-numeric ceiling measured in the docstring
        implied = None
    return Coverage(
        rounds=rows,
        # `latest`'s, never the last row's. They are the same on a run `score`
        # wrote, and they diverge on a run whose round documents were copied
        # without `latest` or the other way round -- and "where the run ended" is
        # the fact this field names.
        terminal_verdict=str(latest.get("verdict", "")),
        cells=cells,
        goals=goals,
        holes=holes,
        implied=implied,
    )


# The files `emit` writes into one package. Listed rather than reduced to a
# boolean so the table can report which of them landed: a package missing its
# `golden.json` is a different failure from a package that was never written, and
# a column saying only "emitted" cannot draw that line. `tests` is a *directory*
# and the other five are files, which is why the probe below asks about existence
# rather than about being a file -- measured: emit writes all six for every
# accepted toy scenario.
SUITE_FILES: tuple[str, ...] = (
    "task.toml",
    "seed.json",
    "golden.json",
    "instruction.md",
    "provenance.md",
    "tests",
)


@dataclass(frozen=True)
class ScenarioRow:
    id_: str
    round_: object
    title: str
    goal_id: str
    actor_id: str
    # `object` rather than `int`, for `_round_row`'s ruling on `round`: a
    # hand-edited `"hop_depth": "two"` renders as "two", because a `0` beside a
    # readable file reads as a rendering bug rather than as the propose-stage defect
    # it is. The flag below is what has to be total over that, not this field.
    hop_depth: object
    cells: list[str]
    status: str
    discriminating_fact: str
    verdict: str
    uniquely_determined: object
    derivable: object
    min_tool_calls: object
    notes: str
    has_instance: bool
    suite_files: list[str]
    difficulty_overstated: bool


def _suite_files(run: RunPaths, scenario_id: str) -> list[str]:
    """Which of `SUITE_FILES` the emitted package holds, or `[]` if there is none.

    Split out rather than inlined because Task 7's challenge section reads it too:
    it tells an accepted scenario whose package landed from one whose did not, so
    the `[]`-for-no-package answer is an interface rather than a detail of the
    table.

    `is_safe_segment` before `task_dir`, which calls `safe_segment` and *raises*
    `UnsafeSegment` on a bad id -- the same defensive filter
    `paths.scenario_ids_with_tasks` applies to the same directory, and for the
    reason its docstring gives: `UnsafeSegment` is a `ValueError`, so it is caught
    by neither an `except OSError` nor `_quietly`, whose guard wraps the read and
    not the path construction. It also answers `False` for the empty string, so a
    record with no `id` takes this branch too rather than probing `06-suite/`
    itself and reporting the whole suite directory as one scenario's package.

    `_exists` rather than a bare `Path.exists()`: `exists` swallows ENOENT and
    ENOTDIR but not EACCES, so probing under a `06-suite/` at mode 000 raises
    rather than answering False -- the same distinction that made the stage spine
    need the helper.
    """
    if not is_safe_segment(scenario_id):
        return []
    directory = run.task_dir(scenario_id)
    return [name for name in SUITE_FILES if _exists(directory / name)]


def scenarios(run: RunPaths) -> list[ScenarioRow] | Marker:
    """One row per scenario, joined across the record, its verdict and its package.

    The section the report exists for, and the only one reading three directories
    at once: `02-scenarios.json` for what was proposed, `05-verdicts/<sid>.json`
    for what `challenge` found, and `06-suite/<sid>/` for what `emit` wrote.

    Long prose is carried on the row but is deliberately not a column:
    `discriminating_fact` and the verdict's `notes` are paragraphs, and the
    renderer puts each in a `title` attribute. That is what keeps a 128-scenario
    run a scannable table, and it is why every id is rendered as a link to the
    artifact on disk -- the drill-in path replaces inlining the seed and the golden
    answer, either of which would make one row taller than the rest of the page.

    **The three joins are gated on `is_safe_segment`, not just the package probe.**
    `run.verdict` and `run.instance_dir` call `safe_segment` exactly as
    `run.task_dir` does, so an id like `"../../etc"` -- the shape `safe_segment`'s
    docstring names -- raises `UnsafeSegment` while the *argument* is being built,
    upstream of `_quietly`'s guard around the read. Guarding the package probe
    alone would leave two of the three raising, which is this module's one absolute
    promise broken for a run that is perfectly readable.
    """
    payload = _mapping(_quietly(run.scenarios))
    if not payload:
        return _absent_or_malformed(
            run.scenarios, "02-scenarios.json", "nothing could be read from it"
        )
    rows = []
    for member in _dicts(payload.get("scenarios")):
        sid = str(member.get("id", ""))
        # One predicate for two cases, rather than a `bool(sid)` test beside an
        # `is_safe_segment(sid)` one that could drift: `is_safe_segment("")` is
        # False, so a record with no id joins nothing instead of probing
        # `05-verdicts/.json`.
        joinable = is_safe_segment(sid)
        verdict = _mapping(_quietly(run.verdict(sid))) if joinable else {}
        hop = member.get("hop_depth")
        found = verdict.get("minimum_tool_calls_found")
        rows.append(
            ScenarioRow(
                id_=sid,
                round_=member.get("round"),
                title=str(member.get("title", "")),
                goal_id=str(member.get("goal_id", "")),
                actor_id=str(member.get("actor_id", "")),
                hop_depth=hop,
                # Flattened to one label per ref rather than kept as pairs: the cell
                # is what the coverage matrix is indexed by, so `cap/oc` is the string
                # a reader matches against section 3.4 by eye.
                cells=[
                    f"{ref.get('capability_id', '')}/{ref.get('outcome_class_id', '')}"
                    for ref in _dicts(member.get("capability_refs"))
                ],
                status=str(member.get("status", "")),
                discriminating_fact=str(member.get("discriminating_fact", "")),
                verdict=str(verdict.get("verdict", "")),
                uniquely_determined=verdict.get("uniquely_determined"),
                # The verdict spells this `derivable_without_guessing`; the row
                # shortens it, because the column heading shares a line with every
                # other column's. The rename is one-sided, which is why the test
                # pins the value rather than its truthiness: the toy fixture makes
                # every verdict `true` here, so a `.get("derivable")` reading None
                # for all four rows is indistinguishable from a uniform read.
                derivable=verdict.get("derivable_without_guessing"),
                min_tool_calls=found,
                notes=str(verdict.get("notes", "")),
                has_instance=(_exists(run.instance_dir(sid)) if joinable else False),
                suite_files=_suite_files(run, sid),
                # Both sides must be real ints before this comparison means
                # anything, and each exclusion closes a measured shape rather than a
                # hypothetical one. A scenario with no verdict leaves `found` None
                # and `None < 1` raises TypeError -- reachable on an unedited toy
                # run, whose folded duplicate is exactly that. A hand-edited
                # `"hop_depth": 2.5` compares fine and would flag a malformed
                # document as an overstated difficulty. And `bool` is an `int`
                # subclass, so `"minimum_tool_calls_found": true` would make
                # `True < 3` report a scenario's difficulty as overstated on the
                # strength of a nonsense comparison -- the opposite ruling from
                # `_as_int`'s, which renders `True` as 1 rather than crash, because
                # rendering a count is not asserting a relation between two.
                difficulty_overstated=(
                    isinstance(found, int)
                    and not isinstance(found, bool)
                    and isinstance(hop, int)
                    and not isinstance(hop, bool)
                    and found < hop
                ),
            )
        )
    return rows


# The stages that run as code rather than as a dispatched skill. They have no
# manifest.stages entry by design, so stage-record-incomplete must not accuse
# them -- CLAUDE.md states their absence there is not a finding.
#
# Measured, not assumed: `set(STAGES) - {every skill's declared stage}` is
# exactly {intake, propose-batches, propose-seal, reconcile-seal, score-seal,
# smoke, survey, synthesise-interfaces, triage-seal, triage-slices}.
# Note `emit` is NOT in it -- rb-emit is a thin wrapper over `rubrica emit`, so
# emit does get a manifest.stages entry and must stay accusable. Hardcoding the
# set here got that wrong once;
# test_code_stages_is_exactly_the_stages_that_run_as_code re-derives it from
# skills.discover() so a stage converted between code and a skill fails there
# rather than being exempted forever in silence.
#
# Spelled out rather than derived at import time on purpose: `skills.discover()`
# reads every SKILL.md off disk and honours RUBRICA_SKILLS_DIR, so deriving it
# here would make one flag on a page about a *run* depend on the skills directory
# the reader happens to have configured.
_CODE_STAGES = frozenset(
    {
        "intake",
        "propose-batches",
        "propose-seal",
        "reconcile-seal",
        "score-seal",
        "smoke",
        "survey",
        "synthesise-interfaces",
        "triage-seal",
        "triage-slices",
    }
)


@dataclass(frozen=True)
class Challenge:
    tallies: dict[str, int]
    judged: int
    packages: int
    incomplete_packages: list[str]
    # The smoke report as it stands on disk, or None. A document rather than a
    # boolean, for `SUITE_FILES`' reason one section up: "smoke ran" and "smoke
    # ran and found nothing" are different facts, and a flag cannot draw that
    # line.
    smoke: dict | None


def challenge(run: RunPaths) -> Challenge | Marker:
    """Verdict tallies and what actually landed in the emitted suite.

    Two counts that a reader will assume agree and that diverge for real reasons:
    `judged` counts `05-verdicts/`, `packages` counts `06-suite/`. A re-seeded
    scenario is judged and never emitted; a scenario whose record disappeared
    between the two stages is emitted and pruned. They are read from separate
    directories rather than one being derived from the other, so the divergence is
    visible instead of being averaged away.

    `incomplete_packages` is the third state, and the one `_suite_files` exists to
    expose: a directory under `06-suite/` holding some of `SUITE_FILES` but not
    all six is a package `emit` began and did not finish, which is a different
    failure from a package that was never written. `_suite_files` returns `[]` for
    three distinguishable states -- no package, an unreadable `06-suite/`, and an
    unsafe scenario id -- and this section reads all three as "no package landed",
    which is the honest reading for an inventory: none of the three put a task on
    disk that Harbor could score.

    `Absent` when `05-verdicts/` holds nothing, which is every run short of
    `challenge`. Both directory reads are guarded, and neither guard can be
    `except OSError`: `list_json` and `scenario_ids_with_tasks` both raise
    `UsageError`, which is a `ValueError` -- the same measurement
    `contradictions` records against the same helper. The suite guard is separate
    from the verdict one so that an unreadable `06-suite/` costs the inventory and
    not the tally: the verdicts are still perfectly readable, and how the
    adversary judged the run is the half a reader came for.
    """
    try:
        verdict_paths = list_json(run.verdicts_dir)
    except Exception:  # deliberate: list_json raises UsageError, which is not an OSError
        # Not `verdict_paths = []` and on to the shared absence below: an
        # unreadable directory and a run that has not reached `challenge` are
        # different facts, and collapsing them told a reader "no verdicts yet"
        # about a run whose verdicts were all on disk and unlistable.
        return _absent_or_malformed(
            run.verdicts_dir, "05-verdicts/", "the directory could not be listed"
        )
    if not verdict_paths:
        return Absent("05-verdicts/")
    tallies: dict[str, int] = {}
    for path in verdict_paths:
        doc = _mapping(_quietly(path))
        # `or "(unrecorded)"` for both the missing key and the empty string, which
        # is `contradictions`' ruling on `resolution` and `dispositions`' on a
        # decline with no reason code: a blank group label on the page reads as a
        # rendering bug rather than as a fact about the record.
        key = str(doc.get("verdict", "")) or "(unrecorded)"
        tallies[key] = tallies.get(key, 0) + 1
    try:
        package_ids = run.scenario_ids_with_tasks()
    except Exception:  # deliberate: UsageError again, on an unreadable 06-suite/
        package_ids = []
    incomplete = [sid for sid in package_ids if len(_suite_files(run, sid)) != len(SUITE_FILES)]
    return Challenge(
        # Sorted for `dispositions`' reason: two runs over the same verdicts must
        # render the same table for the page to be diffable, and a dict keyed in
        # first-seen order is keyed by whichever scenario id sorted first.
        tallies=dict(sorted(tallies.items())),
        judged=len(verdict_paths),
        packages=len(package_ids),
        incomplete_packages=incomplete,
        smoke=_mapping(_quietly(run.report)) or None,
    )


def orphaned_temp_files(run: RunPaths) -> list[str]:
    """Names of `*.tmp.*` files left in the run root, sorted.

    A stage writes its artifact to a temp file and renames it, so one left behind
    is a dispatch that died mid-write. Found by inspection while this was
    designed: `02-scenarios.json.tmp.43146.cb890a5abaf7` was sitting in the
    newest run on disk, and `decisions.md` records an earlier one removed by hand
    after a budget ceiling killed a reconcile pass.

    The run root only, which is the scope rather than an oversight: every sealed
    artifact lives there, and a stray one level down is already invisible to
    `list_json`, which keeps only a `.json` suffix. Naming one would put a file on
    the page that nothing else in the run reacts to.

    `except OSError` because the whole point is a run too broken to read: a root
    at mode 000 -- the shape a run copied out of a container under a different uid
    has -- makes `iterdir` raise, and "no strays visible" is the honest answer.
    """
    try:
        return sorted(p.name for p in run.root.iterdir() if ".tmp." in p.name)
    except OSError:
        return []


@dataclass(frozen=True)
class Flag:
    id_: str
    headline: str
    # The rule that fired, in words, and not optional. A flag whose threshold is
    # not on the page is a black box a reader cannot argue with -- which is the one
    # property test_every_flag_states_its_threshold asserts over a run where all
    # of them fire at once.
    threshold: str
    detail: str


def flags(run: RunPaths) -> list[Flag]:
    """Every rule-based flag that fires for this run.

    Each carries the threshold that fired it, because a flag whose rule is not on
    the page is a black box a reader cannot argue with. `LOW_UTILISATION_PCT` is
    the only tunable threshold in the table; every other flag triggers on a count
    crossing zero or on a comparison between two fields the artifacts already
    hold, which is deliberate -- a page that composes rather than analyses has no
    business carrying a second dial nobody has calibrated.

    **Every builder result is `isinstance`-checked before it is indexed.** This
    function calls six of them and each can return `Absent`; `utilisation` can
    return it for two distinct reasons, and one of those -- an unreadable
    `01-claims/` -- is a run that is otherwise perfectly readable. An unchecked
    `.pct` there breaks this module's one absolute promise at the section a reader
    scans first.

    An absent section flags nothing, and that is a ruling rather than a fallback:
    a run with no world model has no claim utilisation, not 0%, and a run that has
    not scored has no coverage verdict, not a halt. Flagging either would put a
    finding on the page of every partial run -- and partial runs are the primary
    case.
    """
    found: list[Flag] = []

    util = utilisation(run)
    if isinstance(util, Utilisation) and util.pct is not None:
        # Strictly `<`, matching the threshold string below and
        # `refs.check_claim_utilisation`'s own predicate: a run exactly at the
        # threshold is not below it.
        if util.pct < LOW_UTILISATION_PCT:
            found.append(
                Flag(
                    id_="low-utilisation",
                    headline=f"Claim utilisation {util.pct:.1f}%",
                    threshold=f"overall cited/total below {LOW_UTILISATION_PCT:.0f}%",
                    detail=f"{util.cited} of {util.total} claims cited by the world model",
                )
            )
        # `util.uncited` is already the unwaived half, so a run whose only
        # zero-citation input a human ruled on raises no flag here -- which is the
        # judgment `check-refs` reaches on that same run when it exits 0 with the
        # `[waived] ` line still printed. The waived ones are named in the detail
        # rather than left out of the page: dropping them would make this section
        # quieter than the record, and the count in the headline stays the number of
        # inputs still open so a reader can act on it.
        if util.uncited:
            waived_note = (
                f" ({len(util.waived)} more waived: {', '.join(util.waived)})"
                if util.waived
                else ""
            )
            found.append(
                Flag(
                    id_="uncited-artifacts",
                    headline=f"{len(util.uncited)} input(s) contributed no cited claim",
                    # `cited == 0` and not a percentage: the `total` guard is
                    # already applied in `utilisation`, so a 0-of-0 artifact is not
                    # in this list and the gate this mirrors exempts it too.
                    threshold="any artifact with claims of which none is cited "
                    "and not waived by a human",
                    detail=", ".join(util.uncited) + waived_note,
                )
            )

    cons = contradictions(run)
    if isinstance(cons, Contradictions):
        # `by_resolution["unresolved"]`, never `total`: a recorded and resolved
        # contradiction is the reconcile family working, and the toy fixture holds
        # one, so a flag on `total` fires on the golden world.
        unresolved = cons.by_resolution.get("unresolved", 0)
        if unresolved:
            found.append(
                Flag(
                    id_="unresolved-contradictions",
                    headline=f"{unresolved} unresolved contradiction(s)",
                    threshold="any contradiction whose resolution is unresolved",
                    detail=(
                        "a later pass may be modelling one side without saying so; "
                        f"swept {cons.parts_swept} subject part(s)"
                    ),
                )
            )

    cov = coverage(run)
    # `and cov.terminal_verdict` before the inequality: a `latest.json` with no
    # verdict leaves the field `""`, and `"" != "converged"` would render
    # "Coverage ended" with nothing after it -- the blank-label shape the verdict
    # tally and `dispositions` both rule against. An unrecorded verdict is a
    # score-stage defect for `validate` to name, not a halt.
    if isinstance(cov, Coverage) and cov.terminal_verdict not in ("", "converged"):
        found.append(
            Flag(
                id_="coverage-halted",
                headline=f"Coverage ended {cov.terminal_verdict}",
                threshold="terminal verdict is not converged",
                detail=f"{len(cov.holes)} open hole(s) at the last round",
            )
        )

    rows = scenarios(run)
    if isinstance(rows, list):
        overstated = [r.id_ for r in rows if r.difficulty_overstated]
        if overstated:
            found.append(
                Flag(
                    id_="difficulty-overstated",
                    headline=f"{len(overstated)} scenario(s) reachable in fewer calls",
                    threshold="minimum_tool_calls_found < hop_depth",
                    detail=", ".join(overstated),
                )
            )

    strays = orphaned_temp_files(run)
    if strays:
        found.append(
            Flag(
                id_="orphaned-temp",
                headline=f"{len(strays)} orphaned temp file(s)",
                threshold="any *.tmp.* in the run root",
                detail=", ".join(strays) + " -- a dispatch died mid-write",
            )
        )

    head = header(run)
    if isinstance(head, Header):
        recorded = {s.stage for s in head.stages}
        # Only a stage the spine shows as *produced* is owed a record: accusing
        # `score` on a run that stopped at `propose` would put four findings on
        # every partial run's page. `- _CODE_STAGES` is the other half -- see that
        # constant for why hardcoding it once got `emit` wrong.
        produced = {row.name for row in stage_spine(run) if row.produced}
        missing = sorted(produced - recorded - _CODE_STAGES)
        if missing:
            found.append(
                Flag(
                    id_="stage-record-incomplete",
                    headline=f"{len(missing)} dispatched stage(s) unrecorded in the manifest",
                    threshold="a produced prompt stage with no manifest.stages entry",
                    detail=(
                        ", ".join(missing)
                        + " -- without model, effort and skill hash the run is not comparable"
                    ),
                )
            )

    return found


def run_summary(run: RunPaths) -> str:
    """The whole page. One entry point, so callers never import the markup half.

    Imported here rather than at module scope: summary_html imports this module
    for its dataclasses and `esc`, so a top-level import would be circular.
    """
    from rubrica import summary_html

    return summary_html.render(run)
