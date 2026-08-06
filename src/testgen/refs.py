"""Referential integrity across run artifacts: layer 2 of three.

Layer 1 (validate.py) checks that each artifact has the right shape. This
module checks what a schema cannot see: whether ids resolve across artifact
boundaries, whether declared arithmetic matches the data it summarizes, and
(Task 8) whether every assertion is reachable in its own seed.

check_all tolerates a partially-populated run directory. It runs after every
stage, so when reconcile finishes there is no 02-scenarios.json yet and that
absence is normal. A stage that should have produced an artifact and did not
is validate.validate_stage's finding, not this module's.
"""

from __future__ import annotations

import re
from typing import Any

from testgen.artifacts import ArtifactError, read_json
from testgen.findings import Finding
from testgen.paths import RunPaths

_CELL_RE = re.compile(r"\Acell:([A-Za-z0-9][A-Za-z0-9._-]*)/([A-Za-z0-9][A-Za-z0-9._-]*)\Z")
_GOAL_RE = re.compile(r"\Agoal:([A-Za-z0-9][A-Za-z0-9._-]*)\Z")


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


def _claim_ids(run: RunPaths) -> set[str]:
    """Every claim id across every 01-claims file."""
    ids: set[str] = set()
    if not run.claims_dir.is_dir():
        return ids
    for path in sorted(run.claims_dir.glob("*.json")):
        payload = _load(path)
        if isinstance(payload, dict):
            ids.update(c["id"] for c in payload.get("claims", []) if "id" in c)
    return ids


def _cells(world: dict) -> set[tuple[str, str]]:
    """Every (capability_id, outcome_class_id) pair the world model declares."""
    return {
        (cap["id"], oc["id"])
        for cap in world.get("capabilities", [])
        for oc in cap.get("outcome_classes", [])
    }


def _dupes(values: list[str]) -> list[str]:
    return sorted({v for v in values if values.count(v) > 1})


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
    for i, row in enumerate(rows):
        for j, sid in enumerate(row.get("scenario_ids", [])):
            if sid not in scenario_ids:
                report(f"/goal_matrix/rows/{i}/scenario_ids/{j}", f"no such scenario: {sid}")
    _check_matrix_arithmetic(
        report, "/goal_matrix", [bool(r.get("covered")) for r in rows], goal_matrix
    )

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
        gap_id = hole.get("gap_id")
        if gap_id is not None and gap_id not in gap_ids:
            report(f"/holes/{i}/gap_id", f"no such gap: {gap_id}")
    return out


def check_all(run: RunPaths) -> list[Finding]:
    """Every layer-2 check that the run directory currently has inputs for."""
    findings: list[Finding] = []
    findings.extend(check_world_model(run))
    findings.extend(check_scenarios(run))
    findings.extend(check_coverage(run))
    return findings
