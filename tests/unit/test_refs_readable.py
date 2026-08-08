"""refs.check_readable: name the artifact that is broken, not its neighbours.

Every checker in refs treats an unreadable document as an absent one, because
_load swallows ArtifactError. That is right for absence -- a stage that has not
run yet is not a finding -- and wrong for a truncated file: four checkers each
concluded something from the silence, none of them named the file, and the
repair prompt rewrote an artifact that was fine.
"""

from __future__ import annotations

from testgen.paths import RunPaths
from testgen.refs import check_all, check_readable
from tests.unit.test_refs_states import build_state


def test_a_complete_run_has_nothing_unreadable(tmp_path):
    assert check_readable(build_state(tmp_path, "smoke")) == []


def test_an_empty_run_has_nothing_unreadable(tmp_path):
    """Absence is not unreadability. Reporting it would fire before intake."""
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    assert check_readable(run) == []


def test_a_truncated_scenarios_file_is_named(tmp_path):
    run = build_state(tmp_path, "smoke")
    run.scenarios.write_text('{"schema_version": "0.1", "scen', encoding="utf-8")
    findings = check_readable(run)
    assert [f.artifact for f in findings] == [run.scenarios]
    assert "malformed JSON" in findings[0].message


def test_check_all_names_only_the_broken_file(tmp_path):
    """The defect this check exists to remove.

    Before it, check_all returned four findings against 03-coverage/latest.json
    and 04-instances/ and never mentioned 02-scenarios.json at all.
    """
    run = build_state(tmp_path, "smoke")
    assert check_all(run) == [], "the baseline this state is measured against"
    run.scenarios.write_text("not json at all", encoding="utf-8")

    findings = check_all(run)
    assert [f.artifact for f in findings] == [run.scenarios]


def test_every_artifact_kind_layer_two_reads_is_covered(tmp_path):
    """Guards the target list itself.

    A check that names the broken file is only as good as its enumeration: an
    artifact missing from _readable_targets is one whose truncation still
    misdirects the repair. Breaking each in turn is the only way to prove the
    list is complete.
    """
    run = build_state(tmp_path, "smoke")
    task = run.task_dir("scn-001")
    for path in (
        run.manifest,
        run.claims("aap2-api"),
        run.world_model,
        run.scenarios,
        run.coverage_latest,
        run.seed("scn-001"),
        run.expected("scn-001"),
        run.verdict("scn-001"),
        task / "seed.json",
        task / "golden.json",
        task / "tests" / "expected.json",
        run.report,
    ):
        original = path.read_text(encoding="utf-8")
        path.write_text("{", encoding="utf-8")
        assert [f.artifact for f in check_readable(run)] == [path], f"not covered: {path}"
        path.write_text(original, encoding="utf-8")
    assert check_readable(run) == []
