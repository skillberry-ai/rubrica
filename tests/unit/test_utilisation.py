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

from rubrica.paths import RunPaths
from rubrica.refs import check_claim_utilisation
from rubrica.utilisation import claim_utilisation
from tests.toy import build_toy_run


def _blank_world_model_claim_refs(run: RunPaths, artifact_id: str) -> None:
    """Remove every reference to one artifact's claims from the world model.

    Simulates the exact defect: the claims file is present and well-formed, and
    nothing in the world model rests on it.
    """
    claims = json.loads((run.claims_dir / f"{artifact_id}.json").read_text(encoding="utf-8"))
    doomed = {c["id"] for c in claims["claims"]}
    world = json.loads(run.world_model.read_text(encoding="utf-8"))
    for group in ("capabilities", "entities", "actors", "goals"):
        for item in world.get(group, []):
            item["claims"] = [c for c in item.get("claims", []) if c not in doomed]
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


def test_partial_utilisation_is_reported_but_is_not_a_finding(tmp_path):
    """The whole design decision, pinned: 8% is data, 0% is a defect."""
    run = build_toy_run(tmp_path / "runs")
    claims = json.loads((run.claims_dir / "api-json.json").read_text(encoding="utf-8"))
    keep = claims["claims"][0]["id"]
    world = json.loads(run.world_model.read_text(encoding="utf-8"))
    doomed = {c["id"] for c in claims["claims"]} - {keep}
    for group in ("capabilities", "entities", "actors", "goals"):
        for item in world.get(group, []):
            item["claims"] = [c for c in item.get("claims", []) if c not in doomed]
    run.world_model.write_text(json.dumps(world, indent=2) + "\n", encoding="utf-8")

    entry = next(e for e in claim_utilisation(run)["artifacts"] if e["artifact_id"] == "api-json")
    assert entry["cited"] == 1
    assert entry["percent"] < 100
    assert check_claim_utilisation(run) == []
