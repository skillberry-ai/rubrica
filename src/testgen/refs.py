"""Referential integrity across run artifacts: layer 2 of three.

Layer 1 (validate.py) checks that each artifact has the right shape. This
module checks what a schema cannot see: whether ids resolve across artifact
boundaries, whether declared arithmetic matches the data it summarizes, and
(Task 8) whether every assertion is reachable in its own seed.

check_all tolerates a partially-populated run directory. It runs after every
stage, so when reconcile finishes there is no 02-scenarios.json yet and that
absence is normal. A stage that should have produced an artifact and did not
is validate.validate_stage's finding, not this module's. The enumeration of
those valid partial states is executable, in tests/unit/test_refs_states.py.

**Precondition: layer 1 must have run first.** This module assumes every
artifact present is already schema-valid -- _check_reachability and
_check_seed_conformance index required keys directly and would raise KeyError
on a malformed document rather than return a finding. check_all is publicly
callable and the CLI exposes check-refs with no way to require that validate
ran, so a caller running them out of order gets a traceback, not a finding.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from testgen.artifacts import ArtifactError, read_json
from testgen.findings import Finding
from testgen.invariants import InvariantForm
from testgen.invariants import evaluate as evaluate_invariant
from testgen.paths import RunPaths

_CELL_RE = re.compile(r"\Acell:([A-Za-z0-9][A-Za-z0-9._-]*)/([A-Za-z0-9][A-Za-z0-9._-]*)\Z")
_GOAL_RE = re.compile(r"\Agoal:([A-Za-z0-9][A-Za-z0-9._-]*)\Z")

# A scenario that still counts: one the pipeline has not discarded. Shared with
# dedupe.py, which must exclude the same set -- re-proposing a pair resolved in
# an earlier round is how the enrichment loop fails to converge.
OPEN_STATUSES = frozenset({"proposed", "active"})


def cell_ref(capability_id: str, outcome_class_id: str) -> str:
    """Canonical hole reference for one capability x outcome-class cell."""
    return f"cell:{capability_id}/{outcome_class_id}"


def goal_ref(goal_id: str) -> str:
    """Canonical hole reference for one goal row."""
    return f"goal:{goal_id}"


def parse_hole_ref(ref: str) -> tuple[str, tuple[str, ...]]:
    """Parse a hole reference into ("cell", (cap, oc)) or ("goal", (goal,))."""
    match = _CELL_RE.match(ref or "")
    if match:
        return "cell", (match.group(1), match.group(2))
    match = _GOAL_RE.match(ref or "")
    if match:
        return "goal", (match.group(1),)
    raise ValueError(f"malformed hole reference: {ref!r}")


def _load(path) -> Any | None:
    """Read an artifact, or None when it does not exist yet."""
    try:
        return read_json(path)
    except ArtifactError:
        return None


def _claim_index(run: RunPaths) -> dict[str, list[Path]]:
    """Claim id -> every claims file defining it, one entry per definition.

    A list rather than a set: two definitions of one id in the *same* file is
    as much of a reconciliation hazard as two across files, and a set would
    hide it. check_manifest reports any id with more than one entry.
    """
    index: dict[str, list[Path]] = {}
    if not run.claims_dir.is_dir():
        return index
    for path in sorted(run.claims_dir.glob("*.json")):
        payload = _load(path)
        if not isinstance(payload, dict):
            continue
        for claim in payload["claims"]:
            index.setdefault(claim["id"], []).append(path)
    return index


def _claim_ids(run: RunPaths) -> set[str]:
    """Every claim id across every 01-claims file."""
    return set(_claim_index(run))


def _cells(world: dict) -> set[tuple[str, str]]:
    """Every (capability_id, outcome_class_id) pair the world model declares."""
    return {
        (cap["id"], oc["id"])
        for cap in world.get("capabilities", [])
        for oc in cap.get("outcome_classes", [])
    }


def _dupes(values: list[str]) -> list[str]:
    return sorted({v for v in values if values.count(v) > 1})


def check_manifest(run: RunPaths) -> list[Finding]:
    """The manifest against 01-claims, and each claim's evidence against the manifest.

    Checked in one direction only: every claims file must name a registered
    input, never the reverse. A registered input with no claims file yet is the
    normal state during the extract fan-out, and reporting it there would fire
    on a run in which nothing is wrong.
    """
    manifest = _load(run.manifest)
    if manifest is None:
        return []
    out: list[Finding] = []

    def report(pointer: str, message: str) -> None:
        out.append(Finding(run.manifest, "refs", pointer, message))

    # A JSON Schema `format` keyword cannot express calendar validity: the
    # schema declares created_utc's format as date-time, but jsonschema's
    # date-time format is a no-op without rfc3339-validator, which this
    # project does not depend on -- so month 13 and hour 99 pass layer 1
    # unchallenged. This strptime call is what actually rejects them, which
    # makes it a genuine layer-2 check, not defensive tolerance of a run that
    # skipped validate; the try/except is only converting strptime's
    # documented raise into a finding instead of a traceback.
    created = manifest["created_utc"]
    try:
        datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        report(
            "/created_utc",
            f"{created!r} is not a real UTC timestamp of the form YYYY-MM-DDTHH:MM:SSZ",
        )

    registered: dict[str, int] = {}
    for i, entry in enumerate(manifest["inputs"]):
        artifact_id = entry["artifact_id"]
        if artifact_id in registered:
            report(
                f"/inputs/{i}/artifact_id",
                f"artifact_id {artifact_id!r} is already registered at "
                f"/inputs/{registered[artifact_id]}",
            )
            continue
        registered[artifact_id] = i

    for claim_id, paths in sorted(_claim_index(run).items()):
        if len(paths) > 1:
            names = ", ".join(sorted(p.name for p in paths))
            out.append(
                Finding(
                    run.claims_dir,
                    "refs",
                    "",
                    f"claim id {claim_id!r} is defined more than once, in {names}; every "
                    "world-model reference to it would resolve ambiguously",
                )
            )

    if not run.claims_dir.is_dir():
        return out

    for path in sorted(run.claims_dir.glob("*.json")):
        payload = _load(path)
        if not isinstance(payload, dict):
            continue
        declared = payload["artifact_id"]
        if declared != path.stem:
            out.append(
                Finding(
                    path,
                    "refs",
                    "/artifact_id",
                    f"file declares artifact_id {declared!r} but is named {path.name}; the "
                    "filename is how every other stage addresses it",
                )
            )
        elif declared not in registered:
            out.append(
                Finding(
                    path,
                    "refs",
                    "/artifact_id",
                    f"artifact_id {declared!r} is not registered in the manifest",
                )
            )
        for i, claim in enumerate(payload["claims"]):
            for j, evidence in enumerate(claim["evidence"]):
                if evidence["artifact_id"] not in registered:
                    out.append(
                        Finding(
                            path,
                            "refs",
                            f"/claims/{i}/evidence/{j}/artifact_id",
                            f"evidence cites unregistered artifact: {evidence['artifact_id']}",
                        )
                    )
    return out


def check_limits(run: RunPaths) -> list[Finding]:
    """The manifest's loop and suite bounds against what the run actually holds.

    intake writes these and, until now, nothing read them. They are the reason
    run cost is finite, so an unenforced cap is not a documentation gap: it is
    the absence of the bound.

    `limits`, `max_rounds`, `max_scenarios`, and every key indexed below are
    `required` by their schemas, so on a schema-valid document they are always
    present -- but not guaranteed to be a Python `int`: jsonschema's `type:
    integer` accepts any float with a zero fractional part, so a schema-valid
    manifest can carry max_rounds as 2.0. No isinstance guard is added here
    for that, because `>` compares int and float transparently and needs no
    help. A guard would be actively wrong: the brief this function was
    transcribed from wrapped the entire round-check loop in `if
    isinstance(max_rounds, int):`, which would make a float bound silently
    turn the check into a no-op instead of enforcing it -- the exact
    unenforced-cap defect this task exists to close, not a safer version of
    it. A malformed document (e.g. a non-numeric bound) raises on the `>`
    comparison, per this module's documented precondition that layer 1 ran
    first.
    """
    manifest = _load(run.manifest)
    if manifest is None:
        return []
    limits = manifest["limits"]
    max_rounds = limits["max_rounds"]
    max_scenarios = limits["max_scenarios"]
    out: list[Finding] = []

    scenarios_doc = _load(run.scenarios)
    if scenarios_doc is not None:
        scenarios = scenarios_doc["scenarios"]

        def report(pointer: str, message: str) -> None:
            out.append(Finding(run.scenarios, "refs", pointer, message))

        for i, scenario in enumerate(scenarios):
            if scenario["round"] > max_rounds:
                report(
                    f"/scenarios/{i}/round",
                    f"scenario is tagged round {scenario['round']} but the manifest caps "
                    f"the enrichment loop at max_rounds={max_rounds}",
                )
            provenance_round = scenario["provenance"]["round"]
            if provenance_round > max_rounds:
                report(
                    f"/scenarios/{i}/provenance/round",
                    f"provenance records round {provenance_round} but the manifest caps "
                    f"the enrichment loop at max_rounds={max_rounds}",
                )
        open_count = sum(1 for s in scenarios if s["status"] in OPEN_STATUSES)
        if open_count > max_scenarios:
            report(
                "/scenarios",
                f"{open_count} scenarios are proposed or active but the manifest caps the "
                f"suite at max_scenarios={max_scenarios}; duplicate and rejected scenarios "
                "do not count against it",
            )

    coverage = _load(run.coverage_latest)
    if coverage is not None and coverage["round"] > max_rounds:
        out.append(
            Finding(
                run.coverage_latest,
                "refs",
                "/round",
                f"coverage is reported for round {coverage['round']} but the manifest caps the "
                f"enrichment loop at max_rounds={max_rounds}",
            )
        )
    return out


def check_world_model(run: RunPaths) -> list[Finding]:
    """Internal consistency of the world model, including the denominator."""
    world = _load(run.world_model)
    if world is None:
        return []
    out: list[Finding] = []
    path = run.world_model

    def report(pointer: str, message: str) -> None:
        out.append(Finding(path, "refs", pointer, message))

    known_claims = _claim_ids(run)
    entity_ids = {e["id"] for e in world.get("entities", [])}
    actor_ids = {a["id"] for a in world.get("actors", [])}
    collections = {e["collection"] for e in world.get("entities", [])}

    for group in ("capabilities", "entities", "actors", "goals"):
        ids = [item["id"] for item in world.get(group, [])]
        for dupe in _dupes(ids):
            report(f"/{group}", f"duplicate id {dupe!r}")
        for i, item in enumerate(world.get(group, [])):
            for j, claim_id in enumerate(item.get("claims", [])):
                if claim_id not in known_claims:
                    report(f"/{group}/{i}/claims/{j}", f"no such claim: {claim_id}")

    for i, entity in enumerate(world.get("entities", [])):
        for j, relation in enumerate(entity.get("relations", [])):
            if relation["target_entity_id"] not in entity_ids:
                report(
                    f"/entities/{i}/relations/{j}/target_entity_id",
                    f"no such entity: {relation['target_entity_id']}",
                )
        for j, invariant in enumerate(entity.get("invariants", [])):
            machine = invariant.get("machine")
            if not machine:
                continue
            for key in ("collection", "of"):
                name = machine.get(key)
                if name is not None and name not in collections:
                    report(
                        f"/entities/{i}/invariants/{j}/machine/{key}",
                        f"invariant references undeclared collection: {name}",
                    )

    for i, goal in enumerate(world.get("goals", [])):
        if goal["actor_id"] not in actor_ids:
            report(f"/goals/{i}/actor_id", f"no such actor: {goal['actor_id']}")

    for i, contradiction in enumerate(world.get("contradictions", [])):
        for side in ("claim_a", "claim_b"):
            if contradiction[side] not in known_claims:
                report(f"/contradictions/{i}/{side}", f"no such claim: {contradiction[side]}")

    denominator = world.get("denominator", {})
    actual_cells = len(_cells(world))
    if denominator.get("capability_cells") != actual_cells:
        report(
            "/denominator/capability_cells",
            f"declared capability_cells={denominator.get('capability_cells')} but the world "
            f"model declares {actual_cells} capability x outcome-class cells",
        )
    actual_goals = len(world.get("goals", []))
    if denominator.get("goals") != actual_goals:
        report(
            "/denominator/goals",
            f"declared goals={denominator.get('goals')} but the world model declares "
            f"{actual_goals}",
        )
    return out


def check_scenarios(run: RunPaths) -> list[Finding]:
    """Scenario references into the world model, and internal consistency."""
    scenarios_doc = _load(run.scenarios)
    world = _load(run.world_model)
    if scenarios_doc is None or world is None:
        return []
    out: list[Finding] = []
    path = run.scenarios

    def report(pointer: str, message: str) -> None:
        out.append(Finding(path, "refs", pointer, message))

    cells = _cells(world)
    capability_ids = {cap["id"] for cap in world.get("capabilities", [])}
    goal_ids = {g["id"] for g in world.get("goals", [])}
    actor_ids = {a["id"] for a in world.get("actors", [])}
    scenarios = scenarios_doc.get("scenarios", [])
    scenario_ids = {s["id"] for s in scenarios}

    declared_version = scenarios_doc.get("denominator_version")
    world_version = world.get("denominator", {}).get("version")
    if declared_version != world_version:
        report(
            "/denominator_version",
            f"scenarios were proposed against denominator_version={declared_version} but the "
            f"world model is at {world_version}",
        )

    for dupe in _dupes([s["id"] for s in scenarios]):
        report("/scenarios", f"duplicate scenario id {dupe!r}")

    for i, scenario in enumerate(scenarios):
        if scenario["goal_id"] not in goal_ids:
            report(f"/scenarios/{i}/goal_id", f"no such goal: {scenario['goal_id']}")
        if scenario["actor_id"] not in actor_ids:
            report(f"/scenarios/{i}/actor_id", f"no such actor: {scenario['actor_id']}")
        target = scenario.get("duplicate_of")
        if target is not None and target not in scenario_ids:
            report(f"/scenarios/{i}/duplicate_of", f"no such scenario: {target}")
        for j, ref in enumerate(scenario.get("capability_refs", [])):
            pair = (ref["capability_id"], ref["outcome_class_id"])
            if ref["capability_id"] not in capability_ids:
                report(
                    f"/scenarios/{i}/capability_refs/{j}/capability_id",
                    f"no such capability: {ref['capability_id']}",
                )
            elif pair not in cells:
                report(
                    f"/scenarios/{i}/capability_refs/{j}/outcome_class_id",
                    f"capability {ref['capability_id']} has no outcome class "
                    f"{ref['outcome_class_id']}",
                )
        for j, ref in enumerate(scenario.get("provenance", {}).get("hole_refs", [])):
            pointer = f"/scenarios/{i}/provenance/hole_refs/{j}"
            try:
                kind, parts = parse_hole_ref(ref)
            except ValueError as exc:
                report(pointer, str(exc))
                continue
            if kind == "cell" and parts not in cells:
                report(pointer, f"hole reference names no real cell: {ref}")
            if kind == "goal" and parts[0] not in goal_ids:
                report(pointer, f"hole reference names no real goal: {ref}")
    return out


def _check_matrix_arithmetic(
    report, pointer: str, covered_flags: list[bool], declared: dict
) -> None:
    """Covered/total/pct must agree with the rows they summarize."""
    total = len(covered_flags)
    covered = sum(1 for flag in covered_flags if flag)
    if declared.get("total") != total:
        report(f"{pointer}/total", f"declared total={declared.get('total')} but found {total}")
    if declared.get("covered") != covered:
        report(
            f"{pointer}/covered",
            f"declared covered={declared.get('covered')} but {covered} rows are marked covered",
        )
    expected_pct = (covered / total) if total else 0.0
    if abs(float(declared.get("pct", -1)) - expected_pct) > 1e-9:
        report(
            f"{pointer}/pct",
            f"declared pct={declared.get('pct')} but covered/total is {expected_pct}",
        )


def check_coverage(run: RunPaths) -> list[Finding]:
    """Coverage matrices against the world model and the scenario list."""
    coverage = _load(run.coverage_latest)
    world = _load(run.world_model)
    if coverage is None or world is None:
        return []
    out: list[Finding] = []
    path = run.coverage_latest

    def report(pointer: str, message: str) -> None:
        out.append(Finding(path, "refs", pointer, message))

    cells = _cells(world)
    goal_ids = {g["id"] for g in world.get("goals", [])}
    gap_ids = {g["id"] for g in world.get("gaps", [])}
    scenarios_doc = _load(run.scenarios) or {"scenarios": []}
    scenario_ids = {s["id"] for s in scenarios_doc.get("scenarios", [])}

    world_version = world.get("denominator", {}).get("version")
    if coverage.get("denominator_version") != world_version:
        report(
            "/denominator_version",
            f"coverage was computed against denominator_version="
            f"{coverage.get('denominator_version')} but the world model is at {world_version}",
        )

    matrix = coverage.get("capability_matrix", {})
    matrix_cells = matrix.get("cells", [])
    seen = {(c["capability_id"], c["outcome_class_id"]) for c in matrix_cells}
    for missing in sorted(cells - seen):
        report("/capability_matrix/cells", f"matrix omits cell {cell_ref(*missing)}")
    for invented in sorted(seen - cells):
        report("/capability_matrix/cells", f"matrix invents cell {cell_ref(*invented)}")
    for i, cell in enumerate(matrix_cells):
        for j, sid in enumerate(cell.get("scenario_ids", [])):
            if sid not in scenario_ids:
                report(f"/capability_matrix/cells/{i}/scenario_ids/{j}", f"no such scenario: {sid}")
        if cell.get("covered") and not cell.get("scenario_ids"):
            report(
                f"/capability_matrix/cells/{i}",
                f"cell {cell_ref(cell['capability_id'], cell['outcome_class_id'])} is marked "
                "covered but lists no scenarios",
            )
    _check_matrix_arithmetic(
        report, "/capability_matrix", [bool(c.get("covered")) for c in matrix_cells], matrix
    )

    goal_matrix = coverage.get("goal_matrix", {})
    rows = goal_matrix.get("rows", [])
    seen_goals = {r["goal_id"] for r in rows}
    for missing_goal in sorted(goal_ids - seen_goals):
        report("/goal_matrix/rows", f"matrix omits goal {missing_goal}")
    for invented_goal in sorted(seen_goals - goal_ids):
        report("/goal_matrix/rows", f"matrix invents goal {invented_goal}")

    goals_by_id = {g["id"]: g for g in world["goals"]}
    hop_by_scenario = {s["id"]: s["hop_depth"] for s in scenarios_doc["scenarios"]}
    for i, row in enumerate(rows):
        for j, sid in enumerate(row["scenario_ids"]):
            if sid not in scenario_ids:
                report(f"/goal_matrix/rows/{i}/scenario_ids/{j}", f"no such scenario: {sid}")
        goal = goals_by_id.get(row["goal_id"])
        expected_depths: set[int] = set()
        if goal is not None:
            expected_depths = set(goal["expected_hop_depths"])
            if set(row["hop_depths_expected"]) != expected_depths:
                report(
                    f"/goal_matrix/rows/{i}/hop_depths_expected",
                    f"row expects hop depths {sorted(row['hop_depths_expected'])} but the "
                    f"world model declares {sorted(expected_depths)} for {row['goal_id']}",
                )
        present = {
            hop_by_scenario[sid]
            for sid in row["scenario_ids"]
            if isinstance(hop_by_scenario.get(sid), int)
        }
        if set(row["hop_depths_present"]) != present:
            report(
                f"/goal_matrix/rows/{i}/hop_depths_present",
                f"row reports hop depths {sorted(row['hop_depths_present'])} but its "
                f"scenarios have {sorted(present)}",
            )
        # A goal row is covered iff it has a scenario and every expected hop
        # depth is present. A goal exercised at one depth when two are expected
        # is a partial row, and calling it covered is how a goal denominator
        # reaches 100% without testing the hard half of the goal.
        if not row["scenario_ids"]:
            if row["covered"]:
                report(
                    f"/goal_matrix/rows/{i}/covered",
                    f"goal {row['goal_id']} is marked covered but lists no scenarios",
                )
        elif bool(row["covered"]) != (expected_depths <= present):
            report(
                f"/goal_matrix/rows/{i}/covered",
                f"goal {row['goal_id']} is marked covered={row['covered']} but its scenarios "
                f"reach hop depths {sorted(present)} against an expected {sorted(expected_depths)}",
            )
    _check_matrix_arithmetic(
        report, "/goal_matrix", [bool(r.get("covered")) for r in rows], goal_matrix
    )

    hole_refs: set[str] = set()
    for i, hole in enumerate(coverage.get("holes", [])):
        try:
            kind, parts = parse_hole_ref(hole["ref"])
        except ValueError as exc:
            report(f"/holes/{i}/ref", str(exc))
            continue
        if kind == "cell" and parts not in cells:
            report(f"/holes/{i}/ref", f"hole names no real cell: {hole['ref']}")
        if kind == "goal" and parts[0] not in goal_ids:
            report(f"/holes/{i}/ref", f"hole names no real goal: {hole['ref']}")
        hole_refs.add(hole["ref"])
        gap_id = hole.get("gap_id")
        if gap_id is not None and gap_id not in gap_ids:
            report(f"/holes/{i}/gap_id", f"no such gap: {gap_id}")

    # Every uncovered row must be justified, and no justified row may be
    # covered. Without both directions the hole vocabulary is decorative: a
    # report could show 60% and explain none of the missing 40%.
    uncovered = {
        cell_ref(c["capability_id"], c["outcome_class_id"])
        for c in matrix_cells
        if not c["covered"]
    } | {goal_ref(r["goal_id"]) for r in rows if not r["covered"]}
    covered = {
        cell_ref(c["capability_id"], c["outcome_class_id"]) for c in matrix_cells if c["covered"]
    } | {goal_ref(r["goal_id"]) for r in rows if r["covered"]}
    for ref in sorted(uncovered - hole_refs):
        report("/holes", f"{ref} is uncovered but no hole justifies it")
    for ref in sorted(hole_refs & covered):
        report("/holes", f"hole {ref} names a row the matrix marks covered")
    return out


class _Unset:
    def __repr__(self) -> str:
        return "<unset>"


UNSET = _Unset()

# Declared field type -> the predicate a seed value must satisfy. `integer`
# excludes bool deliberately: bool is an int subclass in Python, and a seed
# writing `true` where an id belongs is a real defect, not a wide integer.
_TYPE_CHECKS: dict[str, Any] = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}

_DATA_KINDS = ("answer_contains", "answer_excludes", "value_equals")
_TRAJECTORY_KINDS = ("tool_called", "tool_not_called")


def resolve_pointer(document: Any, pointer: str) -> Any:
    """Resolve an RFC 6901 JSON Pointer, returning UNSET if it does not exist.

    Written here rather than pulled from a library because the whole surface
    is fifteen lines and the reachability gate depends on its exact
    does-not-resolve semantics.
    """
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError(f"not a JSON pointer: {pointer!r}")
    current = document
    for raw in pointer.split("/")[1:]:
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                return UNSET
            current = current[token]
        elif isinstance(current, list):
            if not token.isdigit() or int(token) >= len(current):
                return UNSET
            current = current[int(token)]
        else:
            return UNSET
    return current


def _is_empty(value: Any) -> bool:
    return value is UNSET or value is None or value in ("", [], {})


def _check_seed_conformance(report, world: dict, seed: dict) -> None:
    """Seed collections, fields, and types against the world model's entities."""
    entities = {e["collection"]: e for e in world.get("entities", [])}
    collections = seed.get("collections", {})
    for name in sorted(set(collections) - set(entities)):
        report(
            f"/collections/{name}",
            f"seed declares collection {name!r}, which no world-model entity declares",
        )
    for name, records in sorted(collections.items()):
        entity = entities.get(name)
        if entity is None:
            continue
        declared = {f["name"]: f["type"] for f in entity.get("fields", [])}
        for i, record in enumerate(records):
            pointer = f"/collections/{name}/{i}"
            for missing in sorted(set(declared) - set(record)):
                report(pointer, f"record is missing declared field {missing!r}")
            for extra in sorted(set(record) - set(declared)):
                report(
                    pointer,
                    f"record carries undeclared field {extra!r}; a simulation backend will "
                    "drop or recompute it, so a label relying on it would break at run time",
                )
            for field, type_name in sorted(declared.items()):
                if field not in record:
                    continue
                check = _TYPE_CHECKS.get(type_name)
                if check is not None and not check(record[field]):
                    report(
                        f"{pointer}/{field}",
                        f"field {field!r} is declared {type_name} but holds {record[field]!r}",
                    )


def _check_invariants(report_invariant, world: dict, seed: dict) -> None:
    collections = seed.get("collections", {})
    for entity in world.get("entities", []):
        for invariant in entity.get("invariants", []):
            machine = invariant.get("machine")
            if not machine:
                continue
            try:
                violations = evaluate_invariant(machine, collections)
            except InvariantForm as exc:
                report_invariant("", f"invariant {invariant['id']}: {exc}")
                continue
            for violation in violations:
                report_invariant("", f"invariant {invariant['id']}: {violation}")


def _check_reachability(
    report, world: dict, seed: dict, expected: dict, scenario_caps: set[str]
) -> None:
    """Every assertion is grounded in this scenario's own seed.

    Resolution happens against `seed` and nothing else, so an assertion can
    never reach another scenario's world.

    `scenario_caps` is the scenario's own declared capability_refs. A positive
    trajectory claim must stay inside it: coverage credits the scenario for the
    cells it declared, so an instance exercising a capability the scenario never
    claimed makes coverage confidently wrong. tool_not_called is exempt --
    forbidding a call to an unclaimed capability is exactly what the kind is for.
    """
    capability_ids = {cap["id"] for cap in world.get("capabilities", [])}
    for i, assertion in enumerate(expected["assertions"]):
        kind = assertion["kind"]
        pointer = f"/assertions/{i}"
        if kind in _TRAJECTORY_KINDS:
            capability_id = assertion.get("capability_id")
            if capability_id not in capability_ids:
                report(f"{pointer}/capability_id", f"no such capability: {capability_id}")
            elif kind == "tool_called" and capability_id not in scenario_caps:
                report(
                    f"{pointer}/capability_id",
                    f"asserts a call to {capability_id}, which the scenario does not claim in "
                    "capability_refs; coverage would credit cells this test does not exercise",
                )
            continue
        if kind not in _DATA_KINDS:
            continue
        seed_pointer = assertion["grounded_in"]["seed_pointer"]
        resolved = resolve_pointer(seed, seed_pointer)
        if kind == "answer_excludes":
            if not _is_empty(resolved):
                report(
                    f"{pointer}/grounded_in/seed_pointer",
                    f"answer_excludes is grounded at {seed_pointer}, which resolves to a value "
                    f"({resolved!r}); the seed does contain what the assertion claims it lacks",
                )
            continue
        if resolved is UNSET:
            report(
                f"{pointer}/grounded_in/seed_pointer",
                f"{seed_pointer} does not resolve in this scenario's seed",
            )
            continue
        rendered = str(resolved)
        value = assertion["value"]
        if kind == "answer_contains" and value not in rendered:
            report(
                f"{pointer}/value",
                f"asserted value {value!r} is not present at {seed_pointer} (found {resolved!r})",
            )
        if kind == "value_equals" and rendered != value:
            report(
                f"{pointer}/value",
                f"asserted value {value!r} does not equal the seed value {resolved!r} at "
                f"{seed_pointer}",
            )

    for i, operation in enumerate(expected["trajectory"]["operations"]):
        capability_id = operation["capability_id"]
        if capability_id not in capability_ids:
            report(
                f"/trajectory/operations/{i}/capability_id",
                f"no such capability: {capability_id}",
            )
        elif capability_id not in scenario_caps:
            report(
                f"/trajectory/operations/{i}/capability_id",
                f"the trajectory uses {capability_id}, which the scenario does not claim in "
                "capability_refs; coverage would credit cells this test does not exercise",
            )


def check_instances(run: RunPaths) -> list[Finding]:
    """Seed conformance, machine invariants, and the reachability gate."""
    world = _load(run.world_model)
    if world is None:
        return []
    scenarios_doc = _load(run.scenarios) or {"scenarios": []}
    by_id = {s["id"]: s for s in scenarios_doc.get("scenarios", [])}
    out: list[Finding] = []

    # A directory name that is not a safe path segment cannot be a scenario id,
    # so no artifact under it can be read. That is a repairable defect in the
    # stage that wrote it, so it is an ordinary finding at exit 1 rather than
    # an UnsafeSegment escaping to cli.py as exit 2 and taking every other
    # finding in the run with it.
    for name in run.unsafe_instance_dir_names():
        out.append(
            Finding(
                run.instances_dir,
                "refs",
                "",
                f"instance directory {name!r} is not a usable scenario id: a scenario id must "
                "start with a letter or digit and contain only letters, digits, dots, dashes, "
                "and underscores",
            )
        )

    for sid in run.scenario_ids_with_instances():
        scenario = by_id.get(sid)
        if scenario is None:
            out.append(
                Finding(run.instance_dir(sid), "refs", "", f"no scenario named {sid} was proposed")
            )
            continue
        # The design spec requires every scenario_id under 04/05/06 to be
        # `active` in 02, not merely not-duplicate: a `rejected` scenario and
        # one still `proposed` are both unfit to instantiate, the first because
        # score threw it out and the second because score has not judged it.
        status = scenario.get("status")
        if status != "active":
            out.append(
                Finding(
                    run.instance_dir(sid),
                    "refs",
                    "",
                    f"scenario {sid} has status {status!r} but only an active scenario should "
                    "have been instantiated",
                )
            )

        seed = _load(run.seed(sid))
        expected = _load(run.expected(sid))
        if seed is None or expected is None:
            continue

        seed_path, expected_path = run.seed(sid), run.expected(sid)

        def out_seed(pointer: str, message: str, path=seed_path) -> None:
            out.append(Finding(path, "refs", pointer, message))

        def out_inv(pointer: str, message: str, path=seed_path) -> None:
            out.append(Finding(path, "invariant", pointer, message))

        def out_exp(pointer: str, message: str, path=expected_path) -> None:
            out.append(Finding(path, "refs", pointer, message))

        _check_seed_conformance(out_seed, world, seed)
        _check_invariants(out_inv, world, seed)
        if expected["scenario_id"] != sid:
            out_exp(
                "/scenario_id",
                f"expected.json names scenario {expected['scenario_id']} but lives in the "
                f"instance directory for {sid}",
            )
        scenario_fact = scenario["discriminating_fact"]
        if expected["discriminating_fact"] != scenario_fact:
            out_exp(
                "/discriminating_fact",
                f"the oracle's discriminating_fact is {expected['discriminating_fact']!r} but "
                f"the scenario declared {scenario_fact!r}; copy the scenario's verbatim -- a "
                "paraphrase is indistinguishable from substituting an easier fact",
            )
        scenario_caps = {ref["capability_id"] for ref in scenario["capability_refs"]}
        _check_reachability(out_exp, world, seed, expected, scenario_caps)
    return out


def check_verdicts(run: RunPaths) -> list[Finding]:
    """One coherent verdict per instantiated scenario.

    Returns nothing until challenge has produced at least one verdict: an
    instance without a verdict is the normal state between instantiate and
    challenge, and reporting it there would spend the orchestrator's single
    repair attempt on a phantom.
    """
    if not run.verdicts_dir.is_dir():
        return []
    scenarios_doc = _load(run.scenarios) or {"scenarios": []}
    hop_depths = {s["id"]: s.get("hop_depth") for s in scenarios_doc.get("scenarios", [])}
    instantiated = run.scenario_ids_with_instances()
    out: list[Finding] = []

    for sid in instantiated:
        path = run.verdict(sid)
        verdict = _load(path)
        if verdict is None:
            out.append(Finding(run.instance_dir(sid), "refs", "", f"instance {sid} has no verdict"))
            continue

        def report(pointer: str, message: str, path=path) -> None:
            out.append(Finding(path, "refs", pointer, message))

        if verdict.get("scenario_id") != sid:
            report(
                "/scenario_id",
                f"verdict names scenario {verdict.get('scenario_id')} but is filed under {sid}",
            )
        if verdict.get("verdict") == "accept":
            if not verdict.get("derivable_without_guessing", True):
                report(
                    "/verdict",
                    "verdict is accept but the test is reported as not derivable without "
                    "guessing; those cannot both be true",
                )
            if not verdict.get("uniquely_determined", True):
                report(
                    "/verdict",
                    "verdict is accept but the answer is reported as not uniquely determined; "
                    "those cannot both be true",
                )
        claimed = hop_depths.get(sid)
        found = verdict.get("minimum_tool_calls_found")
        if (
            isinstance(claimed, int)
            and isinstance(found, int)
            and found < claimed
            and "difficulty_overstated" not in verdict.get("flags", [])
        ):
            report(
                "/minimum_tool_calls_found",
                f"adversary solved this in {found} call(s) but the scenario claims hop_depth "
                f"{claimed}; the difficulty_overstated flag is required",
            )

    if run.verdicts_dir.is_dir():
        known = set(instantiated)
        for path in sorted(run.verdicts_dir.glob("*.json")):
            if path.stem not in known:
                out.append(
                    Finding(path, "refs", "", f"verdict for {path.stem}, which has no instance")
                )
    return out


def check_all(run: RunPaths) -> list[Finding]:
    """Every layer-2 check that the run directory currently has inputs for."""
    findings: list[Finding] = []
    findings.extend(check_manifest(run))
    findings.extend(check_limits(run))
    findings.extend(check_world_model(run))
    findings.extend(check_scenarios(run))
    findings.extend(check_coverage(run))
    findings.extend(check_instances(run))
    findings.extend(check_verdicts(run))
    return findings
