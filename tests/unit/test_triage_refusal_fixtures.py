"""Both directions on the two negative catalogues.

tests/unit/test_refusal_fixtures.py guards the existing pair this way for a
measured reason: an over-subtraction once destroyed a capability fact while
passing every forbidden-substring check. So each fixture is checked for still
carrying its defect AND for not having lost anything else.
"""

from __future__ import annotations

import json
from pathlib import Path

from rubrica import validate
from rubrica.paths import RunPaths

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _staged(tmp_path, name):
    # exist_ok=True: test_both_fixtures_clear_layer_one calls this twice against
    # the same tmp_path, one call per fixture, and both mint the same run id --
    # a bare mkdir would raise FileExistsError on the second call.
    run = RunPaths(tmp_path / "run-20260814-213000")
    run.root.mkdir(parents=True, exist_ok=True)
    run.catalogue.write_text((FIXTURES / name).read_text(encoding="utf-8"), encoding="utf-8")
    return run


def test_both_fixtures_clear_layer_one(tmp_path):
    """The defect is semantic. A fixture that fails validate tests the schema."""
    for name in ("catalogue-unsupported-objective.json", "catalogue-all-declinable.json"):
        assert validate.validate_stage(_staged(tmp_path, name), "survey") == [], name


def test_the_unsupported_objective_fixture_still_declares_depth():
    catalogue = json.loads(
        (FIXTURES / "catalogue-unsupported-objective.json").read_text(encoding="utf-8")
    )
    assert catalogue["request"]["objective"] == "depth"


def test_the_unsupported_objective_fixture_still_has_only_one_behavioural_candidate():
    """This is the subtraction. If a second trace creeps in, depth becomes
    arguably supportable and the fixture stops firing refusal condition 3."""
    catalogue = json.loads(
        (FIXTURES / "catalogue-unsupported-objective.json").read_text(encoding="utf-8")
    )
    traces = [c for c in catalogue["candidates"] if c["kind"] == "trace" and c["admissible"]]
    assert len(traces) == 1


def test_the_unsupported_objective_fixture_has_not_lost_its_other_candidates():
    """Over-subtraction check: it still has enough prose to make a real triage
    pass possible, so the refusal is about the objective and not about emptiness."""
    catalogue = json.loads(
        (FIXTURES / "catalogue-unsupported-objective.json").read_text(encoding="utf-8")
    )
    assert len([c for c in catalogue["candidates"] if c["kind"] == "design_doc"]) >= 3


def test_the_all_declinable_fixture_scope_note_names_nothing_in_the_set():
    catalogue = json.loads((FIXTURES / "catalogue-all-declinable.json").read_text(encoding="utf-8"))
    scope = catalogue["request"]["scope_note"].lower()
    assert catalogue["candidates"]
    for candidate in catalogue["candidates"]:
        assert candidate.get("path", "").lower() not in scope
