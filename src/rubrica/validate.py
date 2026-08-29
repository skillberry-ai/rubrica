"""JSON Schema validation of run artifacts: layer 1 of three.

Layer 1 checks shape only. Cross-artifact references, seed-pointer
reachability, and world-model invariants are layer 2 and live in refs.py;
layer 3 is the smoke gate. A stage's output must clear layer 1 before the
orchestrator dispatches the next stage.

Findings are returned, never raised: the orchestrator's contract is one
bounded repair attempt with the findings appended to the stage prompt, which
needs the full list rather than the first failure.

**The schemas anchor patterns with `\\A` and `\\Z`, not `^` and `$`.** JSON
Schema specifies ECMA-262 regexes, where those escapes are not defined, so
these schemas are portable only to a Python validator. That is a deliberate
trade: Python's `re` lets `$` match immediately before a trailing newline, so
`"scn-001\\n"` would satisfy every id pattern and then raise UnsafeSegment when
joined into a path -- surfacing a repairable stage defect as exit 2, a
misconfigured harness. Nothing outside this package validates these artifacts.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

from rubrica.artifacts import ArtifactError, read_json
from rubrica.errors import UsageError
from rubrica.findings import Finding
from rubrica.paths import STAGES, RunPaths, list_json

# Artifact kind -> schema filename.
ARTIFACT_SCHEMAS: dict[str, str] = {
    "manifest": "manifest-0.1.json",
    "claims": "claims-0.1.json",
    "world-model": "world-model-0.1.json",
    "scenarios": "scenarios-0.1.json",
    "coverage": "coverage-0.1.json",
    "seed": "seed-0.1.json",
    "expected": "expected-0.1.json",
    "verdict": "verdict-0.1.json",
    "suite-expected": "suite-expected-0.1.json",
    "report": "report-0.1.json",
    "catalogue": "catalogue-0.1.json",
    "triage": "triage-0.1.json",
    # The triage split's part kinds. Each is one pass's (or, for adoptions,
    # one code subcommand's) slice of what was once a single triage record,
    # and every one of them $refs triage-0.1.json's $defs (a disposition, a
    # surface, a deficiency, a projection) rather than restating them --
    # spec section 7 of the staged-triage design.
    "slices": "slices-0.1.json",
    "objective": "objective-0.1.json",
    "dispositions-part": "dispositions-part-0.1.json",
    "audit": "audit-0.1.json",
    "adoptions": "adoptions-0.1.json",
    # The reconcile partials. Each is one pass's slice of what was once a single
    # world model, and every one of them $refs world-model-0.1.json's $defs
    # rather than restating an element definition.
    "subjects": "subjects-0.1.json",
    "contradictions-part": "contradictions-part-0.1.json",
    "capabilities-part": "capabilities-part-0.1.json",
    "outcomes-part": "outcomes-part-0.1.json",
    "entities-part": "entities-part-0.1.json",
    "goals-part": "goals-part-0.1.json",
    "gaps-part": "gaps-part-0.1.json",
    # The tool-interface kinds. `services-part` now has a producer --
    # reconcile-services, the barrier pass that groups the declared tools -- and
    # so has a STAGE_ARTIFACTS row and an entry in artifacts.md. `interface` is
    # still deliberately absent from STAGE_ARTIFACTS: no stage in paths.STAGES
    # writes one yet, so a stage entry would name a stage validate_stage's
    # UnknownStage exists to reject, and would put an undocumented kind in front
    # of test_docs_accuracy's per-kind check, which reads STAGE_ARTIFACTS. Its
    # shape is reviewable before any stage depends on it, which is the point of
    # landing it without a producer.
    "services-part": "services-part-0.1.json",
    "interface": "interface-0.1.json",
    # inputs-seen-0.1.json is deliberately absent from this map, and is the only
    # schema in the package that is not an artifact kind. It holds one $defs/row
    # that every reconcile partial whose pass owns a claim kind $refs, and no
    # stage produces a document of that shape on its own -- so a kind here would
    # name an artifact `validate --stage X` must never look for.
    # _schema_registry globs the directory and registers by filename, so the
    # cross-file $ref resolves without an entry.
    #
    # The propose/score loop's part kinds. Each is one dispatch's slice of a
    # document that used to be emitted whole by a model, and none of them restates
    # an element it shares with a sealed document: they resolve into
    # scenarios-0.1.json and coverage-0.1.json instead. Two of those refs target a
    # *property* subschema rather than a $defs entry, which is a legal target and
    # the one available here -- and score-part's `status` is a deliberate
    # restatement rather than a ref, because it is a proper SUBSET of the sealed
    # scenario's enum. artifacts.md's "The propose/score loop's parts" section
    # argues both, and the ref/restatement split is the rule to cite rather than
    # any one schema's wording.
    "batches": "batches-0.1.json",
    "scenarios-part": "scenarios-part-0.1.json",
    "score-part": "score-part-0.1.json",
    # Config kinds. Human-authored inputs, not stage outputs, so they are
    # deliberately absent from STAGE_ARTIFACTS: no stage produces them and
    # `validate --stage X` must never look for them.
    "agents": "agents-0.1.json",
    "gold": "gold-0.1.json",
}

# Config artifact kinds: human-authored, never joined into a run path, never
# produced by a stage. The one definition of this set -- tests that need to
# know which kinds are config rather than stage output import it rather than
# restating the literal, which is how {"agents", "gold"} drifted out of sync
# with ARTIFACT_SCHEMAS before this constant existed.
CONFIG_KINDS: frozenset[str] = frozenset({"agents", "gold"})

# Which artifact kinds each stage must produce. Every stage now has a real
# gate: a stage that produced none of its required kinds fails layer 1
# rather than passing trivially, so the orchestrator never dispatches the
# next stage against an empty or missing output.
STAGE_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "survey": ("catalogue",),
    "triage-slices": ("slices",),
    "triage-objective": ("objective",),
    "triage-rule": ("dispositions-part",),
    # The self-audit, dispatched once every triage-rule part has landed. It
    # writes the same "audit" kind check_audit already reads and rejects on
    # a missing digest_insufficient/needs_projection pairing.
    "triage-audit": ("audit",),
    # triage-seal writes the "triage" kind: the same 00-triage.json the
    # monolithic triage stage this family replaced used to write directly.
    # That is exactly why triage-0.1.json needed no revision for the split:
    # the sealed record's shape does not change, only which code produces it.
    "triage-seal": ("triage",),
    "intake": ("manifest",),
    "extract": ("claims",),
    "reconcile-subjects": ("subjects",),
    "reconcile-contradict": ("contradictions-part",),
    "reconcile-capabilities": ("capabilities-part",),
    "reconcile-outcomes": ("outcomes-part",),
    "reconcile-entities": ("entities-part",),
    "reconcile-goals": ("goals-part",),
    "reconcile-gaps": ("gaps-part",),
    "reconcile-services": ("services-part",),
    "reconcile-seal": ("world-model",),
    "propose-batches": ("batches",),
    # propose now writes only its own batch's part. The stage that produces the
    # accumulating 02-scenarios.json is propose-seal, which is code.
    "propose": ("scenarios-part",),
    "propose-seal": ("scenarios",),
    # score writes only what it decides; the matrices and the report around them
    # are score-seal's, which is why the "coverage" kind moved off this row.
    "score": ("score-part",),
    "score-seal": ("coverage",),
    "instantiate": ("seed", "expected"),
    "challenge": ("verdict",),
    "emit": ("suite-expected",),
    "smoke": ("report",),
}


class UnknownStage(ValueError):
    """Raised for a stage name that is not in paths.STAGES."""


def schema_dir() -> Path:
    """Directory holding the artifact schemas.

    The schemas ship as package data beside this module rather than at the
    repository root, so an installed (non-editable) copy can validate. Walking
    up to the repo root only ever worked for an editable install.

    Overridable via RUBRICA_SCHEMA_DIR so a caller can validate against a
    candidate schema set without reinstalling the package.
    """
    override = os.environ.get("RUBRICA_SCHEMA_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "schema"


@functools.cache
def _manifest_stage_efforts(schema_root: Path) -> tuple[str, ...]:
    """The cached half of manifest_stage_efforts, keyed on schema_root.

    Same reason _validator_for below takes schema_root as a cache key rather
    than reading schema_dir() inside: a plain zero-argument @functools.cache
    would return the first schema it ever saw for the life of the process, so
    a test overriding RUBRICA_SCHEMA_DIR after some earlier call (parser
    construction happens on every CLI invocation, so there always is an
    earlier call) would silently get the old effort list back -- correct only
    as long as every caller remembered to `.cache_clear()` first. Keying on
    the root makes that scaffolding unnecessary rather than merely documented.
    """
    schema = read_json(schema_root / ARTIFACT_SCHEMAS["manifest"])
    stage = schema["properties"]["stages"]["additionalProperties"]
    return tuple(stage["properties"]["effort"]["enum"])


def manifest_stage_efforts() -> tuple[str, ...]:
    """The effort levels manifest.stages accepts, read out of the active schema.

    `record-stage` uses this as its argparse choices, so the CLI cannot accept
    an effort the manifest schema will reject -- and there is no second copy of
    the enum to keep in step. Reads the *active* schema_dir() on every call
    (cheap: a small JSON file, cached per root by _manifest_stage_efforts), so
    a RUBRICA_SCHEMA_DIR override takes effect immediately with no cache to
    clear.
    """
    return _manifest_stage_efforts(schema_dir())


@functools.cache
def _schema_registry(schema_root: Path) -> Registry:
    """Every schema in `schema_root`, keyed by filename, for cross-file `$ref`.

    The partial schemas the reconcile passes write are made of the *same*
    elements as the world model -- a capability, an entity, a gap -- so they
    `$ref` `world-model-0.1.json#/$defs/...` rather than restate the definitions.
    Restating them is the drift this package already refuses elsewhere ("derive,
    do not restate"), and a duplicated `$defs/entity` that fell behind would make
    a partial accept an element the assembled world model then rejects.
    The triage part schemas are made of the *same* elements as the sealed
    triage record -- a disposition, a surface, a deficiency, a projection --
    so they `$ref` `triage-0.1.json#/$defs/...` rather than restate the
    definitions. Restating them is the drift this package already refuses
    elsewhere ("derive, do not restate"), and a duplicated `$defs/disposition`
    that fell behind would let a part accept a shape the seal then rejects.

    Keyed on schema_root for the same reason _validator_for is: a plain
    zero-argument cache would pin the first directory it ever saw, so a test
    overriding RUBRICA_SCHEMA_DIR would validate against the old one.

    Registered by filename rather than relying on each schema's `$id` alone,
    even though every shipped schema carries one equal to its filename: a new
    schema that forgets `$id` then still resolves, instead of failing only for
    the file that refs it.
    """
    return Registry().with_resources(
        [
            (
                path.name,
                Resource.from_contents(read_json(path), default_specification=DRAFT202012),
            )
            for path in sorted(schema_root.glob("*.json"))
        ]
    )


@functools.cache
def _validator_for(kind: str, schema_root: Path) -> Draft202012Validator:
    """Compiled validator, cached on (kind, schema_root).

    schema_root is part of the key rather than read inside, so overriding
    RUBRICA_SCHEMA_DIR does not return a validator built from the old one.
    """
    try:
        filename = ARTIFACT_SCHEMAS[kind]
    except KeyError as exc:
        raise KeyError(f"no schema registered for artifact kind {kind!r}") from exc
    schema = read_json(schema_root / filename)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        # A schema file that is readable JSON but not a valid schema is the same
        # class of problem as one that is absent: the harness was pointed at a
        # schema directory it cannot work with, and no repair of any *artifact*
        # can help. UsageError, so cli.py's handler exits 2 naming this file --
        # matching the ArtifactError read_json raises one line above when the
        # same file is missing, which already exits 2.
        #
        # Measured before this door existed, with a copied schema/ whose
        # slices-0.1.json was replaced by {"type": 7}: exit 1, nine stdout
        # lines, and an [internal] finding anchored on the run directory. Three
        # violations at once -- a misconfigured run reported as a repairable
        # stage defect, one finding spread over nine lines, and the wrong
        # artifact named, since nothing was wrong with the run at all.
        # exc.message, not exc: SchemaError's str dumps the whole metaschema
        # branch it failed against, eleven lines for one sentence of reason.
        raise UsageError(f"invalid JSON Schema in {schema_root / filename}: {exc.message}") from exc
    return Draft202012Validator(schema, registry=_schema_registry(schema_root))


def _pointer(parts) -> str:
    """RFC 6901 pointer naming where in the artifact the error is.

    Tokens are escaped, `~` before `/`, or the second replacement would
    re-escape what the first produced. Same rule and same order as
    survey.py's `_escape_pointer_token`, which carries the measurement that
    established it -- one convention with two call sites rather than two
    coincidences, and if it ever needs changing both must change together.

    Unescaped, this was already wrong and became commonly wrong with the
    `interface` kind: every path key in an interface document is
    `/<tool_name>`, so a finding there rendered `/paths//query_tickets`, which
    is also exactly how a property named `""` followed by `"query_tickets"`
    renders. `/paths/~1query_tickets` says which one it is.

    `str(part)` because `error.absolute_path` carries array indices as ints
    alongside property names, and only the names need escaping.
    """
    return "".join(f"/{str(part).replace('~', '~0').replace('/', '~1')}" for part in parts)


def validate_artifact(path: Path, kind: str) -> list[Finding]:
    """Validate one artifact file against the schema for `kind`.

    A `$ref` the registry cannot resolve is re-raised as an ArtifactError naming
    the **schema directory**, because that is the thing that is wrong. Measured
    before this wrapper existed, with world-model-0.1.json absent from
    RUBRICA_SCHEMA_DIR and a partial schema $ref-ing into it: iter_errors raised
    jsonschema's _WrappedReferencingError, which is neither ArtifactError nor
    OSError, so cli.py's catch-all turned a misconfigured schema set into exit 1
    with an [internal] finding against the run root -- telling the orchestrator to
    spend its one repair attempt rewriting an artifact that was fine. A
    misconfigured run is exit 2, and a 1 must name the right artifact; this is
    both rules at once. Resolution is lazy, so the raise happens here inside
    iter_errors rather than when _validator_for compiled the schema.
    """
    path = Path(path)
    try:
        payload = read_json(path)
    except ArtifactError as exc:
        return [Finding(path, "schema", "", str(exc))]
    root = schema_dir()
    validator = _validator_for(kind, root)
    try:
        return [
            Finding(path, "schema", _pointer(error.absolute_path), error.message)
            for error in validator.iter_errors(payload)
        ]
    except Unresolvable as exc:
        raise ArtifactError(
            f"unresolvable schema reference while validating {kind!r} against the schemas "
            f"in {root}: {exc}"
        ) from exc


def _artifact_paths(run: RunPaths, kind: str) -> list[Path]:
    """Every file of `kind` that should exist in this run."""
    if kind == "catalogue":
        # Returned even when absent, unlike manifest and world-model's plain
        # is_file() gate: read_json's ArtifactError names the path in its
        # message ("missing artifact: <path>"), so validate_artifact anchors
        # the finding on 00-catalogue.json itself rather than on the run root.
        # An expected artifact that is missing has to be reported by name, or
        # a survey that wrote nothing passes its own gate.
        return [run.catalogue]
    if kind == "triage":
        return [run.triage] if run.triage.is_file() else []
    if kind == "objective":
        return [run.objective] if run.objective.is_file() else []
    if kind == "audit":
        return [run.audit] if run.audit.is_file() else []
    if kind == "slices":
        # Returned even when absent, for the same reason as catalogue above:
        # read_json's ArtifactError names 00-slices.json itself, so a
        # triage-slices that wrote nothing is reported by path rather than
        # passing because a bare is_file() gate found no expected file to check.
        return [run.slices]
    if kind == "manifest":
        return [run.manifest] if run.manifest.is_file() else []
    if kind == "world-model":
        return [run.world_model] if run.world_model.is_file() else []
    if kind == "scenarios":
        return [run.scenarios] if run.scenarios.is_file() else []
    if kind == "claims":
        return list_json(run.claims_dir)
    if kind == "dispositions-part":
        # Same shape as claims above: one file per fan-out member, named by
        # its own id, in a directory that does not exist until the first
        # member has written to it.
        return list_json(run.dispositions_dir)
    if kind == "coverage":
        # latest.json is a singleton artifact that happens to live in a
        # directory of round files, so it is required the way manifest.json and
        # 02-scenarios.json are, not merely globbed. Globbing alone let
        # round-1.json satisfy the gate on its own -- and since refs.check_limits
        # and refs.check_coverage both read coverage_latest and return [] when it
        # is absent, a score stage that wrote the round file and forgot the
        # pointer passed *both* gates with every coverage check bypassed.
        # Returning the absent path makes validate_artifact report it by name.
        rounds = list_json(run.coverage_dir)
        if not rounds and not run.coverage_dir.is_dir():
            return []
        if run.coverage_latest.is_file():
            return rounds
        return [run.coverage_latest, *rounds]
    if kind == "verdict":
        return list_json(run.verdicts_dir)
    if kind == "seed":
        return [run.seed(sid) for sid in run.scenario_ids_with_instances()]
    if kind == "expected":
        return [run.expected(sid) for sid in run.scenario_ids_with_instances()]
    if kind == "suite-expected":
        return [
            run.task_dir(sid) / "tests" / "expected.json" for sid in run.scenario_ids_with_tasks()
        ]
    if kind == "report":
        return [run.report] if run.report.is_file() else []
    if kind == "subjects":
        # Returned even when absent, like catalogue: read_json's ArtifactError
        # names the path, so a pass that wrote nothing fails its own gate by name
        # rather than passing trivially.
        return [run.subjects]
    if kind == "contradictions-part":
        return list_json(run.contradictions_dir)
    if kind == "capabilities-part":
        return [run.capabilities_part]
    if kind == "outcomes-part":
        return [run.outcomes_part]
    if kind == "entities-part":
        return [run.entities_part]
    if kind == "goals-part":
        return [run.goals_part]
    if kind == "gaps-part":
        return [run.gaps_part]
    if kind == "services-part":
        # The always-return form the other partials use, not the iterated one: a
        # pass that wrote nothing must fail its own gate by name rather than
        # passing trivially on an empty list.
        return [run.services_part]
    if kind == "batches":
        # Iterated, and so empty when no round has a plan -- NOT the
        # always-return form catalogue/slices/subjects use. propose-batches
        # legitimately writes nothing when no hole is closable, and that absence
        # is how the loop learns it is over. What the iterated form buys is that
        # the finding, when there is one, names a plan that EXISTS: this function
        # has no round number, so the always-return form could only ever invent a
        # path. It does NOT stop layer 1 firing on a terminal round -- an empty
        # list still reaches validate_stage's "produced no batches artifact" arm
        # against the run root, which is why the orchestrator gates this stage
        # only when a plan was written (pinned by
        # test_the_batches_gate_over_a_run_with_no_plan_names_the_run_root).
        # "Failed" is distinguished from "no holes" by the subcommand's exit code,
        # which is 2 on every real failure, not by this gate. (Rulings R2, R9.)
        return [run.batches(r) for r in run.batches_rounds()]
    if kind == "scenarios-part":
        return [
            run.scenario_part(r, b)
            for r in run.scenario_part_rounds()
            for b in run.scenario_part_batch_ids(r)
        ]
    if kind == "score-part":
        return [run.score_part(r) for r in run.score_part_rounds()]
    raise KeyError(f"unknown artifact kind {kind!r}")


def validate_stage(run: RunPaths, stage: str) -> list[Finding]:
    """Validate every artifact the named stage is responsible for.

    An expected-but-absent artifact is itself a finding. A stage that
    produced nothing has failed, and passing silently would let the
    orchestrator dispatch the next stage against a missing input.
    """
    if stage not in STAGES:
        raise UnknownStage(f"unknown stage {stage!r}; expected one of {', '.join(STAGES)}")
    findings: list[Finding] = []
    for kind in STAGE_ARTIFACTS[stage]:
        paths = _artifact_paths(run, kind)
        if not paths:
            findings.append(
                Finding(run.root, "schema", "", f"stage {stage!r} produced no {kind} artifact")
            )
        for path in paths:
            findings.extend(validate_artifact(path, kind))
    return findings
