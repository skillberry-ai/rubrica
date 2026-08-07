"""check_limits: the manifest's loop and suite bounds, enforced."""

from __future__ import annotations

from testgen.artifacts import write_json
from testgen.paths import RunPaths
from testgen.refs import check_limits
from tests.builders import minimal_coverage, minimal_manifest, minimal_scenarios


def _run(tmp_path, *, manifest=None, scenarios=None, coverage=None) -> RunPaths:
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    write_json(run.manifest, manifest if manifest is not None else minimal_manifest())
    if scenarios is not None:
        write_json(run.scenarios, scenarios)
    if coverage is not None:
        write_json(run.coverage_latest, coverage)
    return run


def _messages(findings) -> str:
    return " || ".join(f.message for f in findings)


def _scenario(sid: str, **over):
    base = dict(minimal_scenarios()["scenarios"][0])
    base["id"] = sid
    base.update(over)
    return base


def test_a_run_inside_its_limits_is_clean(tmp_path):
    run = _run(tmp_path, scenarios=minimal_scenarios(), coverage=minimal_coverage())
    assert check_limits(run) == []


def test_no_manifest_means_nothing_to_enforce(tmp_path):
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    write_json(run.scenarios, minimal_scenarios())
    assert check_limits(run) == []


def test_a_scenario_beyond_max_rounds_is_reported(tmp_path):
    scenarios = minimal_scenarios(scenarios=[_scenario("scn-001", round=99)])
    run = _run(tmp_path, scenarios=scenarios)
    messages = _messages(check_limits(run))
    assert "round 99" in messages
    assert "max_rounds=2" in messages


def test_a_provenance_round_beyond_max_rounds_is_reported(tmp_path):
    scenario = _scenario("scn-001")
    scenario["provenance"] = dict(scenario["provenance"], round=7)
    run = _run(tmp_path, scenarios=minimal_scenarios(scenarios=[scenario]))
    findings = check_limits(run)
    assert [f.pointer for f in findings] == ["/scenarios/0/provenance/round"]


def test_too_many_open_scenarios_is_reported(tmp_path):
    manifest = minimal_manifest(limits={"max_rounds": 2, "max_scenarios": 2})
    scenarios = minimal_scenarios(
        scenarios=[_scenario("scn-001"), _scenario("scn-002"), _scenario("scn-003")]
    )
    run = _run(tmp_path, manifest=manifest, scenarios=scenarios)
    messages = _messages(check_limits(run))
    assert "3 scenarios are proposed or active" in messages
    assert "max_scenarios=2" in messages


def test_duplicate_and_rejected_scenarios_do_not_count_against_the_cap(tmp_path):
    """The cap bounds per-scenario fan-out cost, which discarded work does not incur."""
    manifest = minimal_manifest(limits={"max_rounds": 2, "max_scenarios": 1})
    scenarios = minimal_scenarios(
        scenarios=[
            _scenario("scn-001"),
            _scenario("scn-002", status="duplicate", duplicate_of="scn-001"),
            _scenario("scn-003", status="rejected", rejected_reason="ambiguous"),
        ]
    )
    run = _run(tmp_path, manifest=manifest, scenarios=scenarios)
    assert check_limits(run) == []


def test_a_coverage_round_beyond_max_rounds_is_reported(tmp_path):
    run = _run(tmp_path, coverage=minimal_coverage(round=5))
    findings = check_limits(run)
    assert len(findings) == 1
    assert findings[0].artifact == run.coverage_latest
    assert findings[0].pointer == "/round"


def test_the_cap_is_a_ceiling_not_an_equality(tmp_path):
    manifest = minimal_manifest(limits={"max_rounds": 9, "max_scenarios": 9})
    run = _run(tmp_path, manifest=manifest, scenarios=minimal_scenarios())
    assert check_limits(run) == []
