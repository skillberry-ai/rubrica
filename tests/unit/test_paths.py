from pathlib import Path

import pytest

from testgen.paths import STAGES, RunPaths, UnsafeSegment, is_safe_segment, safe_segment

# Directory names a confused stage could plausibly write that are not usable
# scenario ids. All of these can really exist on disk -- a literal ".." cannot,
# which is why it is tested through safe_segment rather than through a listing.
UNSAFE_DIR_NAMES = ("scn 001", ".hidden", "scn:001", "-leading")


def test_stages_are_in_pipeline_order():
    assert STAGES == (
        "intake",
        "extract",
        "reconcile",
        "propose",
        "score",
        "instantiate",
        "challenge",
        "emit",
        "smoke",
    )


def test_safe_segment_accepts_ordinary_ids():
    assert safe_segment("scn-001") == "scn-001"
    assert safe_segment("aap2.api.json") == "aap2.api.json"


@pytest.mark.parametrize(
    "bad",
    [
        "../etc",
        "a/b",
        "..",
        "",
        ".hidden",
        "with space",
        "trailing/",
        "x\x00y",
    ],
)
def test_safe_segment_rejects_anything_that_could_escape(bad):
    with pytest.raises(UnsafeSegment):
        safe_segment(bad)


def test_singleton_artifact_paths():
    rp = RunPaths(Path("/runs/r1"))
    assert rp.manifest == Path("/runs/r1/manifest.json")
    assert rp.inputs_dir == Path("/runs/r1/00-inputs")
    assert rp.claims_dir == Path("/runs/r1/01-claims")
    assert rp.world_model == Path("/runs/r1/01-world-model.json")
    assert rp.scenarios == Path("/runs/r1/02-scenarios.json")
    assert rp.coverage_dir == Path("/runs/r1/03-coverage")
    assert rp.coverage_latest == Path("/runs/r1/03-coverage/latest.json")
    assert rp.instances_dir == Path("/runs/r1/04-instances")
    assert rp.verdicts_dir == Path("/runs/r1/05-verdicts")
    assert rp.suite_dir == Path("/runs/r1/06-suite")
    assert rp.report == Path("/runs/r1/07-report.json")
    assert rp.decisions == Path("/runs/r1/decisions.md")


def test_per_id_artifact_paths():
    rp = RunPaths(Path("/runs/r1"))
    assert rp.claims("aap2-api") == Path("/runs/r1/01-claims/aap2-api.json")
    assert rp.coverage_round(2) == Path("/runs/r1/03-coverage/round-2.json")
    assert rp.instance_dir("scn-001") == Path("/runs/r1/04-instances/scn-001")
    assert rp.seed("scn-001") == Path("/runs/r1/04-instances/scn-001/seed.json")
    assert rp.expected("scn-001") == Path("/runs/r1/04-instances/scn-001/expected.json")
    assert rp.rationale("scn-001") == Path("/runs/r1/04-instances/scn-001/rationale.md")
    assert rp.verdict("scn-001") == Path("/runs/r1/05-verdicts/scn-001.json")
    assert rp.task_dir("scn-001") == Path("/runs/r1/06-suite/scn-001")
    assert rp.measurement_dir == Path("/runs/r1/measurement")
    assert rp.smoke_dir("under_test", "scn-001") == Path(
        "/runs/r1/measurement/smoke/under_test/scn-001"
    )


def test_smoke_dir_refuses_an_unsafe_role_or_scenario_id():
    rp = RunPaths(Path("/runs/r1"))
    with pytest.raises(UnsafeSegment):
        rp.smoke_dir("../../etc", "scn-001")
    with pytest.raises(UnsafeSegment):
        rp.smoke_dir("under_test", "../../etc/passwd")


def test_per_id_paths_refuse_unsafe_ids():
    """Every per-id method, since paths.py is the security boundary."""
    rp = RunPaths(Path("/runs/r1"))
    for call in (
        rp.claims,
        rp.instance_dir,
        rp.seed,
        rp.expected,
        rp.rationale,
        rp.verdict,
        rp.task_dir,
    ):
        with pytest.raises(UnsafeSegment):
            call("../../etc/passwd")


def test_coverage_round_must_be_positive():
    rp = RunPaths(Path("/runs/r1"))
    with pytest.raises(ValueError):
        rp.coverage_round(0)


def test_scenario_ids_with_instances_lists_sorted_dirs(tmp_path):
    rp = RunPaths(tmp_path)
    for sid in ("scn-002", "scn-001"):
        rp.instance_dir(sid).mkdir(parents=True)
    (rp.instances_dir / "stray-file.json").write_text("{}", encoding="utf-8")
    assert rp.scenario_ids_with_instances() == ["scn-001", "scn-002"]


def test_scenario_ids_with_instances_is_empty_when_stage_has_not_run(tmp_path):
    assert RunPaths(tmp_path).scenario_ids_with_instances() == []


def test_scenario_ids_with_instances_excludes_unsafe_names(tmp_path):
    """The listing partitions rather than handing back a name that will raise.

    Every caller joins these onto a path, so returning an unsafe one only
    defers UnsafeSegment to a call site that cannot report it usefully.
    """
    rp = RunPaths(tmp_path)
    for name in UNSAFE_DIR_NAMES + ("scn-001",):
        (rp.instances_dir / name).mkdir(parents=True, exist_ok=True)
    assert rp.scenario_ids_with_instances() == ["scn-001"]


def test_unsafe_instance_dir_names_returns_the_rejected_ones_sorted(tmp_path):
    rp = RunPaths(tmp_path)
    for name in UNSAFE_DIR_NAMES + ("scn-001",):
        (rp.instances_dir / name).mkdir(parents=True, exist_ok=True)
    assert rp.unsafe_instance_dir_names() == sorted(UNSAFE_DIR_NAMES)


def test_the_two_listings_partition_every_instance_directory(tmp_path):
    """Nothing on disk is silently dropped by either listing."""
    rp = RunPaths(tmp_path)
    names = UNSAFE_DIR_NAMES + ("scn-001", "scn-002")
    for name in names:
        (rp.instances_dir / name).mkdir(parents=True, exist_ok=True)
    (rp.instances_dir / "stray-file.json").write_text("{}", encoding="utf-8")
    safe, unsafe = rp.scenario_ids_with_instances(), rp.unsafe_instance_dir_names()
    assert set(safe) | set(unsafe) == set(names)
    assert not set(safe) & set(unsafe)


def test_unsafe_instance_dir_names_is_empty_when_stage_has_not_run(tmp_path):
    assert RunPaths(tmp_path).unsafe_instance_dir_names() == []


def test_input_file_resolves_under_the_inputs_directory():
    run = RunPaths("/runs/run-1")
    assert run.input_file("aap2-api.json") == Path("/runs/run-1/00-inputs/aap2-api.json")


def test_input_file_refuses_an_unsafe_stored_name():
    run = RunPaths("/runs/run-1")
    with pytest.raises(UnsafeSegment):
        run.input_file("../../etc/passwd")


def test_is_safe_segment_agrees_with_safe_segment():
    """One definition of safety, asked two ways."""
    for good in ("scn-001", "aap2.api.json", "a"):
        assert is_safe_segment(good)
        assert safe_segment(good) == good
    for bad in ("../etc", "a/b", "..", "", ".hidden", "with space", "x\x00y", 7):
        assert not is_safe_segment(bad)
        with pytest.raises(UnsafeSegment):
            safe_segment(bad)
