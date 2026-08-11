"""diff-runs: attributing variance to a stage rather than to "the pipeline".

The numbers are Jaccards, which is the easy part. What these tests pin is the
part that makes them mean something: that two runs which read different inputs
are declared incomparable rather than scored, and that every number arrives with
its set sizes and its difference attached.
"""

from __future__ import annotations

from testgen.artifacts import read_json, write_json
from testgen.stability import (
    capability_ids,
    comparability,
    diff_runs,
    emitted_task_ids,
    goal_cell_claims,
    input_digests,
    stage_config,
)
from tests.builders import minimal_manifest, minimal_scenarios, minimal_world_model
from tests.unit.test_refs_states import build_state


def _pair(tmp_path, state="emit"):
    return build_state(tmp_path / "a", state), build_state(tmp_path / "b", state)


# -- the per-stage sets ------------------------------------------------------


def test_capability_ids_come_from_the_world_model(tmp_path):
    run = build_state(tmp_path, "reconcile")
    assert capability_ids(run) == frozenset({"cap-find-jobs"})


def test_goal_cell_claims_are_goal_capability_outcome_triples(tmp_path):
    run = build_state(tmp_path, "propose")
    assert goal_cell_claims(run) == frozenset({("goal-triage", "cap-find-jobs", "oc-success")})


def test_a_discarded_scenario_makes_no_claim(tmp_path):
    """Stability is about what the run produced, and a duplicate produced nothing."""
    run = build_state(tmp_path, "propose")
    scenarios = minimal_scenarios()
    scenarios["scenarios"][0]["status"] = "duplicate"
    scenarios["scenarios"][0]["duplicate_of"] = "scn-000"
    write_json(run.scenarios, scenarios)
    assert goal_cell_claims(run) == frozenset()


def test_emitted_task_ids_come_from_the_suite_directory(tmp_path):
    run = build_state(tmp_path, "emit")
    assert emitted_task_ids(run) == frozenset({"scn-001"})


def test_an_absent_artifact_gives_an_empty_set_rather_than_raising(tmp_path):
    """diff-runs must be usable on a run that halted early.

    Comparing a complete run against one that stopped after propose is exactly the
    comparison that localizes where it stopped being reproducible.
    """
    from testgen.paths import RunPaths

    run = RunPaths(tmp_path / "nothing")
    run.root.mkdir(parents=True)
    assert capability_ids(run) == frozenset()
    assert goal_cell_claims(run) == frozenset()
    assert emitted_task_ids(run) == frozenset()


# -- comparability -----------------------------------------------------------


def test_two_identical_runs_are_comparable(tmp_path):
    a, b = _pair(tmp_path)
    assert comparability(a, b) == []


def test_different_input_bytes_make_the_runs_incomparable(tmp_path):
    """A stability number over different inputs measures the inputs."""
    a, b = _pair(tmp_path)
    manifest = read_json(b.manifest)
    manifest["inputs"][0]["sha256"] = "f" * 64
    write_json(b.manifest, manifest)
    reasons = comparability(a, b)
    assert len(reasons) == 1
    assert "different input" in reasons[0]


def test_a_stage_run_under_a_different_model_makes_the_runs_incomparable(tmp_path):
    """Design spec section 291: two runs are comparable only if these match."""
    a, b = _pair(tmp_path)
    manifest = read_json(b.manifest)
    manifest["stages"]["reconcile"]["model"] = "claude-sonnet-5"
    write_json(b.manifest, manifest)
    assert any("reconcile" in reason and "model" in reason for reason in comparability(a, b))


def test_a_stage_run_under_a_different_effort_or_skill_hash_is_caught(tmp_path):
    a, b = _pair(tmp_path)
    manifest = read_json(b.manifest)
    manifest["stages"]["reconcile"]["effort"] = "low"
    manifest["stages"]["reconcile"]["skill_sha256"] = "c" * 64
    write_json(b.manifest, manifest)
    reasons = " ".join(comparability(a, b))
    assert "effort" in reasons and "skill_sha256" in reasons


def test_a_stage_recorded_in_only_one_run_is_reported(tmp_path):
    """And attributed to the right side.

    A human reads this reason to localize a reproducibility break, so naming the
    wrong run is worse than saying nothing: `propose` is recorded only in run b
    here, and asserting merely that "propose" appears somewhere let the two labels
    be swapped without a single test noticing.
    """
    a, b = _pair(tmp_path)
    manifest = read_json(b.manifest)
    manifest["stages"]["propose"] = {
        "model": "claude-opus-5",
        "effort": "high",
        "skill_sha256": "d" * 64,
    }
    write_json(b.manifest, manifest)
    reasons = [reason for reason in comparability(a, b) if "propose" in reason]
    assert reasons == ["stage 'propose' is recorded only in run b"]


def test_only_the_unreadable_manifest_is_reported_not_the_cascade_it_causes(tmp_path):
    """comparability returns early on an unreadable manifest, and that is load-bearing.

    Not for `comparable`, which is False either way, but for the reasons list a
    human reads. With one manifest gone, that side's input digests and stage
    config are empty while the other side's are real, so falling through would
    append "the two runs read different input bytes" plus one "recorded only in
    run a" per stage -- every one derived from the absence rather than from a
    difference, burying the single fact that explains them all.
    """
    a, b = _pair(tmp_path)
    b.manifest.unlink()
    reasons = comparability(a, b)
    assert reasons == ["run b has no readable manifest.json, so nothing can be pinned"]


def test_an_unreadable_manifest_makes_the_runs_incomparable_rather_than_equal(tmp_path):
    """Absence must not read as agreement.

    Two runs whose manifests cannot be read would otherwise both yield empty
    digest sets, and jaccard(empty, empty) is 1.0 -- the runs would be declared
    perfectly comparable *because* nothing could be checked.
    """
    a, b = _pair(tmp_path)
    b.manifest.unlink()
    assert comparability(a, b) != []


def test_two_runs_with_no_manifest_at_all_are_not_declared_comparable(tmp_path):
    """The digest and stage-config checks alone cannot catch this case.

    Unlike the test above, both manifests are missing here rather than just one:
    with only one side unlinked, the digest comparison already differs (a real
    manifest's inputs against none) and would report incomparability even
    without a dedicated readability check. Two runs that both have no manifest
    yield identical -- empty -- digest sets and identical -- empty -- stage
    configs, so only a check for manifest readability itself catches this one.
    """
    from testgen.paths import RunPaths

    a, b = RunPaths(tmp_path / "a"), RunPaths(tmp_path / "b")
    a.root.mkdir(parents=True)
    b.root.mkdir(parents=True)
    assert comparability(a, b) != []


def test_a_run_that_records_no_stages_is_not_comparable_with_one_that_does(tmp_path):
    """One-sided: the reason names the side that recorded nothing, and only it.

    Everything else about the pair agrees -- same inputs, same bytes -- so the
    empty map is the only thing left to catch, and attributing it to the wrong
    run is the failure mode `test_a_stage_recorded_in_only_one_run_is_reported`
    exists for one level up.
    """
    a, b = _pair(tmp_path)
    manifest = read_json(b.manifest)
    manifest["stages"] = {}
    write_json(b.manifest, manifest)
    reasons = comparability(a, b)
    assert [reason for reason in reasons if "records no stages" in reason] == [
        "run b records no stages in manifest.json, so no model, effort or skill hash can be pinned"
    ]
    assert not any("run a records no stages" in reason for reason in reasons)


def test_two_runs_that_both_record_no_stages_are_not_declared_comparable(tmp_path):
    """The case the per-stage loop cannot catch, and the bug this closes.

    `stages: {}` on both sides takes the loop over the union of stage names zero
    times and appends no reason, so the pair came back `comparable: True` with an
    empty reasons list -- absence read as agreement, the exact misreading the
    unreadable-manifest check four lines above already exists to prevent. It is
    not a hypothetical state either: every intake-only run has this manifest, as
    does any run where the orchestrator never called `record-stage`.
    """
    a, b = _pair(tmp_path)
    for run in (a, b):
        manifest = read_json(run.manifest)
        manifest["stages"] = {}
        write_json(run.manifest, manifest)
    reasons = comparability(a, b)
    assert sorted(reason for reason in reasons if "records no stages" in reason) == [
        "run a records no stages in manifest.json, so no model, effort or skill hash can be pinned",
        "run b records no stages in manifest.json, so no model, effort or skill hash can be pinned",
    ]
    assert diff_runs(a, b)["comparable"] is False


def test_a_stages_key_that_is_not_a_mapping_is_read_as_no_stages(tmp_path):
    """A hand-edited `stages: []` must not become a TypeError at exit 1.

    Indexing a list by stage name raises TypeError, which cli.py reports as a
    malformed artifact -- true, but it routes a diff-runs reader to a repair
    prompt. Read as absent, it lands on the empty-map reason instead, which is
    both accurate and the answer that cannot be mistaken for agreement.
    """
    a, b = _pair(tmp_path)
    manifest = read_json(b.manifest)
    manifest["stages"] = []
    write_json(b.manifest, manifest)
    assert stage_config(b) == {}
    assert any("run b records no stages" in reason for reason in comparability(a, b))


# -- diff_runs ---------------------------------------------------------------


def test_two_identical_runs_are_stable_everywhere(tmp_path):
    a, b = _pair(tmp_path)
    report = diff_runs(a, b)
    assert report["comparable"] is True
    assert report["incomparable_reasons"] == []
    for stage in ("1b_capabilities", "2_goal_cell_claims", "6_task_ids"):
        assert report["stages"][stage]["jaccard"] == 1.0
        assert report["stages"][stage]["only_a"] == []
        assert report["stages"][stage]["only_b"] == []


def test_every_number_arrives_with_its_set_sizes(tmp_path):
    """A jaccard of 1.0 over two empty sets is true and reads as success.

    Only the sizes make that visible, which is why the metric's own docstring
    requires every caller to report them.
    """
    from testgen.paths import RunPaths

    a, b = RunPaths(tmp_path / "x"), RunPaths(tmp_path / "y")
    a.root.mkdir(parents=True)
    b.root.mkdir(parents=True)
    stage = diff_runs(a, b)["stages"]["6_task_ids"]
    assert stage["jaccard"] == 1.0
    assert (stage["a_size"], stage["b_size"]) == (0, 0)


def test_a_capability_only_one_run_found_is_named(tmp_path):
    """A bare 0.5 tells nobody which capability moved."""
    a, b = _pair(tmp_path)
    world = minimal_world_model()
    world["capabilities"][0]["id"] = "cap-renamed"
    write_json(b.world_model, world)
    stage = diff_runs(a, b)["stages"]["1b_capabilities"]
    assert stage["only_a"] == ["cap-find-jobs"]
    assert stage["only_b"] == ["cap-renamed"]
    assert stage["jaccard"] == 0.0


def test_a_goal_cell_claim_difference_is_rendered_as_a_readable_triple(tmp_path):
    a, b = _pair(tmp_path)
    write_json(b.scenarios, minimal_scenarios(scenarios=[]))
    stage = diff_runs(a, b)["stages"]["2_goal_cell_claims"]
    assert stage["only_a"] == ["goal-triage/cap-find-jobs/oc-success"]
    assert stage["only_b"] == []


def test_the_stage_variance_is_still_reported_when_the_runs_are_incomparable(tmp_path):
    """Refusing to report would hide the localization that is the whole point.

    An incomparable pair is often the interesting one -- the report says so and
    reports the numbers anyway, so a reader can see that stage 2 diverged *and*
    that the inputs differed.
    """
    a, b = _pair(tmp_path)
    manifest = read_json(b.manifest)
    manifest["inputs"][0]["sha256"] = "f" * 64
    write_json(b.manifest, manifest)
    report = diff_runs(a, b)
    assert report["comparable"] is False
    assert report["stages"]["1b_capabilities"]["jaccard"] == 1.0


def test_the_report_names_both_runs_and_is_deterministic(tmp_path):
    a, b = _pair(tmp_path)
    report = diff_runs(a, b)
    assert report["a"] == str(a.root)
    assert report["b"] == str(b.root)
    assert report == diff_runs(a, b)
    assert "format" in report


def test_stage_config_and_input_digests_read_what_the_manifest_records(tmp_path):
    run = build_state(tmp_path, "intake")
    manifest = minimal_manifest()
    assert stage_config(run) == manifest["stages"]
    assert input_digests(run) == frozenset(
        {(manifest["inputs"][0]["artifact_id"], manifest["inputs"][0]["sha256"])}
    )
