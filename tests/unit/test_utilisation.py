"""Per-artifact claim utilisation, and the one case that is a finding.

The measurement this exists for: run-20260812-130056 extracted 287 claims and
its world model cited 157, so 130 were cited by nothing and neither gate said a
word. `refs.check_world_model` checks that a cited claim id resolves; nothing
checked the reverse.

Why the gate fires only on *zero* and not on a percentage: sampling the uncited
claims returned deployment facts -- LOG_LEVEL, PORT, "listening on 0.0.0.0:8000"
-- which rb-reconcile was right to drop. A cite-everything gate would emit ~130
findings to catch one real loss, and the cheapest way to satisfy it would be to
promote that trivia into the world model.
"""

from __future__ import annotations

import json

from rubrica.artifacts import read_json, write_json
from rubrica.paths import RunPaths
from rubrica.refs import check_claim_utilisation
from rubrica.utilisation import _cited_claim_ids, claim_utilisation
from tests.toy import build_toy_run


def _strip_claim_refs(world: dict, doomed: set[str]) -> None:
    """Drop every id in `doomed` from every citation site in `world`, in place.

    Every site, including the three child ones $defs/invariant, $defs/outcome_class
    and $defs/gap gained when the read-coverage variance (docs/design/findings.md)
    was closed. A stripper that walked only the four top-level groups would leave
    the golden fixture still citing api-json from
    its outcome classes -- so a test that means "nothing in the world model rests
    on this input" would be asserting against a world model that plainly does,
    and `check_claim_utilisation` would be right to stay quiet.
    """
    for group in ("capabilities", "entities", "actors", "goals"):
        for item in world.get(group, []):
            item["claims"] = [c for c in item.get("claims", []) if c not in doomed]
    for capability in world.get("capabilities", []):
        for outcome_class in capability.get("outcome_classes", []) or []:
            outcome_class["claims"] = [
                c for c in outcome_class.get("claims", []) if c not in doomed
            ]
    for entity in world.get("entities", []):
        for invariant in entity.get("invariants", []) or []:
            invariant["claims"] = [c for c in invariant.get("claims", []) if c not in doomed]
    for gap in world.get("gaps", []) or []:
        gap["claims"] = [c for c in gap.get("claims", []) if c not in doomed]


def _blank_world_model_claim_refs(run: RunPaths, artifact_id: str) -> None:
    """Remove every reference to one artifact's claims from the world model.

    Simulates the exact defect: the claims file is present and well-formed, and
    nothing in the world model rests on it.
    """
    claims = json.loads((run.claims_dir / f"{artifact_id}.json").read_text(encoding="utf-8"))
    doomed = {c["id"] for c in claims["claims"]}
    world = json.loads(run.world_model.read_text(encoding="utf-8"))
    _strip_claim_refs(world, doomed)
    run.world_model.write_text(json.dumps(world, indent=2) + "\n", encoding="utf-8")


def test_the_toy_run_utilises_every_input(tmp_path):
    run = build_toy_run(tmp_path / "runs")
    report = claim_utilisation(run)
    assert report["format"] == "rubrica-utilisation/1"
    assert report["artifacts"], "no artifacts reported for a run with claims"
    for entry in report["artifacts"]:
        assert entry["cited"] > 0, entry


def test_the_toy_run_has_no_utilisation_finding(tmp_path):
    run = build_toy_run(tmp_path / "runs")
    assert check_claim_utilisation(run) == []


def test_an_input_cited_by_nothing_is_one_finding_naming_it(tmp_path):
    """The red direction. Without it this predicate has never been watched fail,
    and a guard nobody has seen fail is not yet a guard."""
    run = build_toy_run(tmp_path / "runs")
    _blank_world_model_claim_refs(run, "api-json")
    findings = check_claim_utilisation(run)
    assert len(findings) == 1, findings
    assert "api-json" in findings[0].message


def test_it_does_not_fire_before_a_world_model_exists(tmp_path):
    """check-refs runs at every stage gate. A run stopped at extract has claims
    and no world model, and reporting all of them as uncited would make the
    extract gate unpassable."""
    run = build_toy_run(tmp_path / "runs", upto="extract")
    assert check_claim_utilisation(run) == []
    assert claim_utilisation(run)["artifacts"] == []


def test_an_input_cited_only_through_a_contradiction_is_not_a_finding(tmp_path):
    """The false-positive direction. `refs.check_world_model` (refs.py:1920-1923,
    its `/contradictions/` loop)
    already resolves contradictions[].claim_a and claim_b as claim references, so a
    definition of "cited" that ignores them disagrees with that checker. Measured
    before this test existed: stripping an artifact's citations from the four walked
    groups and putting two of its claim ids into a new `contradictions` entry made
    `check_claim_utilisation` return "no world-model element cites any claim from
    api-json (9 claims)" against a world model that visibly cites it -- the
    wrong-artifact class this repo calls out specifically.
    """
    run = build_toy_run(tmp_path / "runs")
    claims = json.loads((run.claims_dir / "api-json.json").read_text(encoding="utf-8"))
    doomed = [c["id"] for c in claims["claims"]]
    world = json.loads(run.world_model.read_text(encoding="utf-8"))
    _strip_claim_refs(world, set(doomed))
    world.setdefault("contradictions", []).append(
        {
            "claim_a": doomed[0],
            "claim_b": doomed[1],
            "description": "test contradiction",
        }
    )
    run.world_model.write_text(json.dumps(world, indent=2) + "\n", encoding="utf-8")

    assert check_claim_utilisation(run) == []


def test_partial_utilisation_is_reported_but_is_not_a_finding(tmp_path):
    """The whole design decision, pinned: 8% is data, 0% is a defect."""
    run = build_toy_run(tmp_path / "runs")
    claims = json.loads((run.claims_dir / "api-json.json").read_text(encoding="utf-8"))
    keep = claims["claims"][0]["id"]
    world = json.loads(run.world_model.read_text(encoding="utf-8"))
    doomed = {c["id"] for c in claims["claims"]} - {keep}
    _strip_claim_refs(world, doomed)
    run.world_model.write_text(json.dumps(world, indent=2) + "\n", encoding="utf-8")

    entry = next(e for e in claim_utilisation(run)["artifacts"] if e["artifact_id"] == "api-json")
    assert entry["cited"] == 1
    assert entry["percent"] < 100
    assert check_claim_utilisation(run) == []


def test_a_claim_cited_only_on_a_child_element_counts_as_cited(tmp_path):
    """An invariant's, outcome class's or gap's own claims are citations.

    Measured on run-20260823-112746 before this walk existed: 38 claim ids
    appeared somewhere in the world model and nowhere in this function's
    result, because the only structured place those three elements had to
    record provenance was their parent's `claims` array or their own
    `description` prose. A counter that misses them reports an input as
    uncited while the world model rests on it -- the self-contradicting gate-1
    brief the read-coverage variance records.
    """
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    world = read_json(run.world_model)
    # One id per new site, moved *out* of every existing site so the only way
    # it can be counted is the new walk.
    world["capabilities"][0]["claims"] = ["clm-api-001"]
    world["capabilities"][0]["outcome_classes"][0]["claims"] = ["clm-api-005"]
    world["entities"][0]["claims"] = ["clm-api-003"]
    world["entities"][0]["invariants"][0]["claims"] = ["clm-notes-005"]
    world["gaps"] = [
        {
            "id": "gap-x",
            "subject": "x",
            "unknown": "x",
            "why_it_matters": "x",
            "blocks": ["propose"],
            "claims": ["clm-notes-006"],
        }
    ]
    write_json(run.world_model, world)

    cited = _cited_claim_ids(run)
    assert "clm-api-005" in cited, "an outcome class's own claims are not counted"
    assert "clm-notes-005" in cited, "an invariant's own claims are not counted"
    assert "clm-notes-006" in cited, "a gap's own claims are not counted"
