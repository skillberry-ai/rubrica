"""refs.check_readable: name the artifact that is broken, not its neighbours.

Every checker in refs treats an unreadable document as an absent one, because
_load swallows ArtifactError. That is right for absence -- a stage that has not
run yet is not a finding -- and wrong for a truncated file: four checkers each
concluded something from the silence, none of them named the file, and the
repair prompt rewrote an artifact that was fine.
"""

from __future__ import annotations

from rubrica.paths import RunPaths
from rubrica.refs import check_all, check_readable
from tests.builders import minimal_subjects
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
        # The seven reconcile partials, each proved covered individually. Three of
        # them -- entities, goals, gaps -- have no layer-2 checker reading them at
        # all; they are listed in _readable_targets because they are the seal's
        # inputs, and a truncated one left unnamed is a check-refs that came back
        # clean over a run the seal is about to choke on.
        run.subjects,
        run.contradiction_part(minimal_subjects()["subjects"][0]["id"]),
        run.capabilities_part,
        run.outcomes_part,
        run.entities_part,
        run.goals_part,
        run.gaps_part,
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


def test_every_per_round_loop_artifact_is_covered(tmp_path):
    """The same enumeration guard for the loop's three per-round documents, and it
    needs a different fixture to reach them at all.

    `build_state` writes `02-scenarios.json` and the coverage documents directly
    rather than through the parts, so a `02-batches/round-N.json` left out of
    `_readable_targets` sails through the test above -- the fixture-cannot-reach
    weakness, exactly as an empty `05-verdicts/` once hid a real deny in
    test_dispatch_harness. `build_toy_run` goes through `propose-batches`, the
    propose part and the score part, so it can reach all three.

    Each one is read by a layer-2 checker of its own -- `check_batches`,
    `check_scenario_parts`, `check_score_parts` -- and `check_scenario_parts` reads
    the *plan* beside the parts as well, so a truncated plan left unnamed here is a
    checker reporting a missing batch for every correct part in the round while
    naming the wrong artifact.
    """
    from tests.toy import TOY_BATCH_ID, build_toy_run

    run = build_toy_run(tmp_path / "runs")
    assert check_readable(run) == [], "the baseline this state is measured against"
    for path in (
        run.batches(1),
        run.scenario_part(1, TOY_BATCH_ID),
        run.score_part(1),
    ):
        original = path.read_text(encoding="utf-8")
        path.write_text("{", encoding="utf-8")
        assert [f.artifact for f in check_readable(run)] == [path], f"not covered: {path}"
        path.write_text(original, encoding="utf-8")
    assert check_readable(run) == []
