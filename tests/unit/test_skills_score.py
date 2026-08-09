"""tg-score's contract, and the vocabularies it must be complete over.

This stage writes the numbers every later judgment is measured against, so the
completeness checks here are about vocabulary coverage: a verdict it cannot
name is a loop state it cannot report, and a hole reason it cannot name is an
uncovered cell it will mislabel as closable.
"""

from __future__ import annotations

from testgen.artifacts import read_json
from testgen.cli import subcommand_names
from testgen.skills import SECTIONS, load, skills_dir
from testgen.validate import ARTIFACT_SCHEMAS, STAGE_ARTIFACTS, schema_dir

SKILL = skills_dir() / "tg-score" / "SKILL.md"


def _coverage_schema():
    return read_json(schema_dir() / ARTIFACT_SCHEMAS["coverage"])


def test_the_contract_matches_the_stage_gate():
    skill = load(SKILL)
    assert skill.contract["stage"] == "score"
    assert set(skill.contract["schemas"]) == set(STAGE_ARTIFACTS["score"])


def test_it_writes_both_the_round_file_and_the_latest_pointer():
    """validate --stage score requires latest.json by name. A score stage that
    wrote only the round file passed both gates with every coverage check
    bypassed, because check_limits and check_coverage both return [] when
    latest.json is absent.
    """
    writes = load(SKILL).contract["writes"]
    assert "coverage_round" in writes
    assert "coverage_latest" in writes


def test_it_writes_the_scenarios_file_because_it_owns_the_status_transitions():
    assert "scenarios" in load(SKILL).contract["writes"]


def test_it_invokes_dedupe_candidates():
    """The deterministic half of dedupe. A skill that eyeballs the scenario list
    instead is doing by judgment what code already did, and inconsistently.
    """
    assert "dedupe-candidates" in load(SKILL).contract["invokes"]
    assert "dedupe-candidates" in subcommand_names()


def test_it_has_the_five_sections():
    assert all(section in load(SKILL).headings for section in SECTIONS)


def test_it_names_every_coverage_verdict():
    """The verdict the orchestrator branches on. A skill that cannot name
    halted_no_progress cannot report a fixpoint, and the loop runs to the cap
    every time.
    """
    enum = _coverage_schema()["properties"]["verdict"]["enum"]
    body = load(SKILL).body
    missing = [verdict for verdict in enum if verdict not in body]
    assert not missing, f"the skill never mentions verdict(s) {missing}"


def test_it_names_every_hole_reason():
    enum = _coverage_schema()["$defs"]["hole"]["properties"]["reason"]["enum"]
    body = load(SKILL).body
    missing = [reason for reason in enum if reason not in body]
    assert not missing, f"the skill never mentions hole reason(s) {missing}"


def test_it_names_both_matrices_and_the_three_summary_fields():
    body = load(SKILL).body
    for name in (
        "capability_matrix",
        "goal_matrix",
        "hop_depths_present",
        "hop_depths_expected",
        "covered",
        "total",
        "pct",
    ):
        assert name in body, name


def test_it_states_the_status_values_it_may_set():
    """score owns every transition out of `proposed`. The three it may write are
    checked against refs' sets rather than a literal list.
    """
    from testgen.refs import JUDGED_STATUSES

    body = load(SKILL).body
    assert "duplicate" in body and "duplicate_of" in body
    for status in sorted(JUDGED_STATUSES):
        assert status in body, f"the skill never mentions {status!r}"


def test_it_states_that_a_rejection_reopens_a_row():
    """The state test_refs_states.py's post-rejection case exists for. A skill
    that does not know a rejected scenario loses its credit leaves latest.json
    reporting a cell covered by a scenario the adversary threw out -- coverage
    confidently wrong with both gates green.
    """
    body = load(SKILL).body
    assert "rejected" in body
    assert "recompute" in body.lower()
