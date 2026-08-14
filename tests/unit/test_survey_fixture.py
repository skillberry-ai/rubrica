"""The corpus fixture, guarded in both directions.

Both directions, because tests/fixtures/toy-gap/ taught this lesson: an
over-subtraction there once destroyed a capability fact while still passing
every forbidden-substring check. So this file asserts what the fixture still
contains as well as what survey does with it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from rubrica import refs, survey, validate
from rubrica.artifacts import read_json

FIXTURE = Path(__file__).parent.parent / "fixtures" / "corpus-toy"


def _survey(tmp_path):
    return survey.survey(
        corpus_roots=[FIXTURE],
        runs_dir=tmp_path / "runs",
        target_name="ticketq",
        target_interface="mcp",
        objective="breadth",
        max_rounds=2,
        max_scenarios=128,
        now=datetime(2026, 8, 14, 21, 30, 0, tzinfo=UTC),
    )


def test_the_fixture_still_carries_one_of_every_exclusion_class():
    """If a file is deleted from the fixture, the reason code it proved stops
    being covered -- silently, because nothing else in the suite reaches it."""
    names = {p.relative_to(FIXTURE).as_posix() for p in FIXTURE.rglob("*") if p.is_file()}
    for required in (
        ".hg/branch",
        "node_modules/dep/index.js",
        "package-lock.json",
        "logo.png",
        ".gitignore",
        "generated.txt",
        "copy-of-README.md",
        "capture.json",
        "src/tool_defs.py",
        "locked.md",
    ):
        assert required in names, f"corpus-toy lost {required}"


def test_surveying_the_fixture_clears_both_gates(tmp_path):
    run = _survey(tmp_path)
    assert validate.validate_stage(run, "survey") == []
    assert refs.check_catalogue(run) == []


def test_the_fixture_produces_every_exclusion_reason_but_operator_excluded(tmp_path):
    """operator_excluded needs an --exclude flag, so it is the one reason a
    corpus alone cannot produce; test_survey_walk covers it.

    `unreadable` fires on an OSError raised while actually opening a file, and
    committed fixture bytes cannot express that: git tracks the executable
    bit, not the read bit. locked.md is chmod'd 0o000 for the duration of this
    call only, mirroring test_survey_walk.py's own
    test_an_unreadable_file_is_recorded_rather_than_raised -- the fixture
    reads like an ordinary file everywhere else, including in
    test_surveying_the_fixture_clears_both_gates above.
    """
    locked = FIXTURE / "locked.md"
    locked.chmod(0o000)
    try:
        catalogue = read_json(_survey(tmp_path).catalogue)
    finally:
        locked.chmod(0o644)
    produced = {entry["reason"] for entry in catalogue["excluded"]}
    assert produced == set(survey.EXCLUSION_REASONS) - {"operator_excluded"}


def test_the_exclusion_reasons_in_code_and_schema_cannot_drift(tmp_path):
    """validate.CONFIG_KINDS exists because {"agents", "gold"} drifted out of
    sync with a literal restated in tests. Same shape, same pin."""
    import json

    enum = json.loads((validate.schema_dir() / "catalogue-0.1.json").read_text(encoding="utf-8"))[
        "$defs"
    ]["exclusion_reason"]["enum"]
    assert sorted(enum) == sorted(survey.EXCLUSION_REASONS)
