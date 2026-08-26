import os
from pathlib import Path

import pytest

from rubrica import paths
from rubrica.errors import UsageError
from rubrica.paths import (
    STAGES,
    RunPaths,
    UnsafeSegment,
    is_safe_segment,
    list_dir,
    list_json,
    safe_segment,
)

# Directory names a confused stage could plausibly write that are not usable
# scenario ids. All of these can really exist on disk -- a literal ".." cannot,
# which is why it is tested through safe_segment rather than through a listing.
UNSAFE_DIR_NAMES = ("scn 001", ".hidden", "scn:001", "-leading")


def test_stages_are_in_pipeline_order():
    assert STAGES == (
        "survey",
        "triage-slices",
        "triage-objective",
        "triage-rule",
        "triage-audit",
        "triage-seal",
        "intake",
        "extract",
        "reconcile-subjects",
        "reconcile-contradict",
        "reconcile-capabilities",
        "reconcile-outcomes",
        "reconcile-entities",
        "reconcile-goals",
        "reconcile-gaps",
        "reconcile-seal",
        "propose",
        "score",
        "instantiate",
        "challenge",
        "emit",
        "smoke",
    )


def test_survey_and_triage_lead_the_stage_ordering():
    """STAGES is the pipeline order and the on-disk numbering.

    survey, triage-slices, triage-objective, triage-rule, triage-audit and
    triage-seal are all 00-family, so they precede intake -- which is no
    longer the first thing that happens in a run. triage-seal sorts last in
    the family regardless of how many of the passes between triage-slices and
    triage-seal have landed (see paths.py's own comment): it is the pass that
    seals every one of their outputs into 00-triage.json.
    """
    assert paths.STAGES[:7] == (
        "survey",
        "triage-slices",
        "triage-objective",
        "triage-rule",
        "triage-audit",
        "triage-seal",
        "intake",
    )


def test_the_catalogue_and_triage_record_are_run_paths(tmp_path):
    """Both are 00-family singletons beside 00-inputs/.

    They are RunPaths properties rather than paths joined at a call site
    because check_contract resolves a skill's declared `reads` names against
    this class -- a literal path in a contract is a check-skills finding.
    """
    run = paths.RunPaths(tmp_path / "run-20260814-000000")
    assert run.catalogue == run.root / "00-catalogue.json"
    assert run.triage == run.root / "00-triage.json"
    assert run.catalogue.parent == run.inputs_dir.parent


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


def _write_parts(rp, *stems):
    rp.contradictions_dir.mkdir(parents=True, exist_ok=True)
    for stem in stems:
        (rp.contradictions_dir / f"{stem}.json").write_text("{}", encoding="utf-8")


def test_subject_part_ids_lists_sorted_stems(tmp_path):
    rp = RunPaths(tmp_path)
    _write_parts(rp, "sub-jobs", "sub-api")
    (rp.contradictions_dir / "notes.md").write_text("x", encoding="utf-8")
    assert rp.subject_part_ids() == ["sub-api", "sub-jobs"]


def test_subject_part_ids_is_empty_when_the_pass_has_not_run(tmp_path):
    assert RunPaths(tmp_path).subject_part_ids() == []


# UNSAFE_DIR_NAMES rather than a subject-flavoured copy: segment safety is one
# property of a name, defined once in is_safe_segment, not a per-artifact rule --
# and these four are all legal filename stems as well as legal directory names.
def test_subject_part_ids_excludes_unsafe_names(tmp_path):
    """The same ruling scenario_ids_with_instances records, on the same evidence.

    refs.check_contradiction_parts joins these back onto a path through
    contradiction_part(), so handing one back raises UnsafeSegment at a call site
    that maps it to exit 2 -- a repairable stage defect misreported as a broken
    harness, and every other finding in the run discarded with it.
    """
    rp = RunPaths(tmp_path)
    _write_parts(rp, *UNSAFE_DIR_NAMES, "sub-jobs")
    assert rp.subject_part_ids() == ["sub-jobs"]
    for name in rp.subject_part_ids():
        rp.contradiction_part(name)  # would raise UnsafeSegment on a leaked name


def test_unsafe_contradiction_part_names_returns_the_rejected_ones_sorted(tmp_path):
    rp = RunPaths(tmp_path)
    _write_parts(rp, *UNSAFE_DIR_NAMES, "sub-jobs")
    assert rp.unsafe_contradiction_part_names() == sorted(UNSAFE_DIR_NAMES)


def test_the_two_contradiction_listings_partition_every_part_file(tmp_path):
    """Nothing on disk is silently dropped by either listing."""
    rp = RunPaths(tmp_path)
    stems = UNSAFE_DIR_NAMES + ("sub-api", "sub-jobs")
    _write_parts(rp, *stems)
    (rp.contradictions_dir / "notes.md").write_text("x", encoding="utf-8")
    safe, unsafe = rp.subject_part_ids(), rp.unsafe_contradiction_part_names()
    assert set(safe) | set(unsafe) == set(stems)
    assert not set(safe) & set(unsafe)


def test_unsafe_contradiction_part_names_is_empty_when_the_pass_has_not_run(tmp_path):
    assert RunPaths(tmp_path).unsafe_contradiction_part_names() == []


def test_the_new_triage_paths_sit_in_the_double_zero_band(tmp_path):
    run = RunPaths(tmp_path / "run-1")
    assert run.slices.name == "00-slices.json"
    assert run.slices_dir.name == "00-slices"
    assert run.objective.name == "00-objective.json"
    assert run.dispositions_dir.name == "00-dispositions"
    assert run.audit.name == "00-audit.json"
    assert run.adoptions.name == "00-adoptions.json"


def test_a_slice_id_that_would_escape_the_run_is_refused(tmp_path):
    run = RunPaths(tmp_path / "run-1")
    for evil in ("../etc", "a/b", "..", ""):
        with pytest.raises(UnsafeSegment):
            run.slice_shard(evil)
        with pytest.raises(UnsafeSegment):
            run.disposition_part(evil)


def test_slice_ids_with_parts_lists_only_what_is_on_disk(tmp_path):
    run = RunPaths(tmp_path / "run-1")
    assert run.slice_ids_with_parts() == []
    run.dispositions_dir.mkdir(parents=True)
    (run.dispositions_dir / "s02.json").write_text("{}", encoding="utf-8")
    (run.dispositions_dir / "s01.json").write_text("{}", encoding="utf-8")
    (run.dispositions_dir / "notes.txt").write_text("x", encoding="utf-8")
    assert run.slice_ids_with_parts() == ["s01", "s02"]


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


# -- listing a run directory ---------------------------------------------------


def test_list_dir_and_list_json_are_empty_for_a_directory_that_does_not_exist(tmp_path):
    """Absence is not an error: a stage that has not run yet has no directory."""
    assert list_dir(tmp_path / "nope") == []
    assert list_json(tmp_path / "nope") == []


def test_list_json_returns_only_json_files_sorted(tmp_path):
    for name in ("b.json", "a.json", "notes.md"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    (tmp_path / "subdir.json").mkdir()
    assert list_json(tmp_path) == [tmp_path / "a.json", tmp_path / "b.json"]
    assert (tmp_path / "subdir.json") in list_dir(tmp_path), "list_dir does not filter"


@pytest.mark.parametrize("mode", [0o000, 0o444])
def test_listing_an_unreadable_directory_raises_a_usage_error(tmp_path, mode):
    """Not `[]`, and not a bare PermissionError.

    `Path.glob` swallows EACCES and yields nothing, which made every caller
    report the artifacts as absent rather than as unreadable. `iterdir` raises
    PermissionError, which cli.py's catch tuple did not cover, so it became an
    exit-1 finding about a run that was fine. Both become the UsageError cli.py
    maps to exit 2 -- the same conversion skills._skill_dirs does for the prompt
    directory.

    The two modes are two different code paths, and only list_json is affected by
    both. At 0o000 the listing itself fails. At 0o444 the listing succeeds and
    stat'ing a child is what fails -- so list_dir, which stats nothing, correctly
    still answers, and every caller that goes on to stat wraps its own loop.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")
    (tmp_path / "child").mkdir()
    tmp_path.chmod(mode)
    try:
        with pytest.raises(UsageError, match="cannot read run directory"):
            list_json(tmp_path)
        if mode == 0o000:
            with pytest.raises(UsageError, match="cannot read run directory"):
                list_dir(tmp_path)
        else:
            assert [p.name for p in list_dir(tmp_path)] == ["a.json", "child"]
    finally:
        tmp_path.chmod(0o755)


@pytest.mark.parametrize("mode", [0o000, 0o444])
def test_the_listing_methods_raise_a_usage_error_on_an_unreadable_directory(tmp_path, mode):
    """Every RunPaths listing a checker iterates over, same ruling."""
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = RunPaths(tmp_path)
    directories = (run.instances_dir, run.suite_dir, run.contradictions_dir)
    for directory in (run.instances_dir, run.suite_dir):
        (directory / "scn-001").mkdir(parents=True)
    # A *.json child, not a subdirectory, because that is what 01-contradictions/
    # really holds -- and because it is what makes mode 0o444 raise here at all.
    # list_json short-circuits `p.suffix == ".json" and p.is_file()`, so with only
    # non-json entries the is_file() stat that raises inside a listable but
    # untraversable directory is never reached and the listing comes back empty.
    run.contradictions_dir.mkdir(parents=True)
    (run.contradictions_dir / "sub-jobs.json").write_text("{}", encoding="utf-8")
    for directory in directories:
        directory.chmod(mode)
    try:
        for call in (
            run.scenario_ids_with_instances,
            run.unsafe_instance_dir_names,
            run.scenario_ids_with_tasks,
            # The contradictions listings go through list_json, so an unreadable
            # 01-contradictions/ must be exit 2 as well -- not an empty listing
            # that reports every subject's part as missing.
            run.subject_part_ids,
            run.unsafe_contradiction_part_names,
        ):
            with pytest.raises(UsageError, match="cannot read run directory"):
                call()
    finally:
        for directory in directories:
            directory.chmod(0o755)


def test_new_round_artifact_paths(tmp_path):
    run = RunPaths(tmp_path)
    assert run.batches == tmp_path / "02-batches.json"
    assert run.scenario_parts_dir == tmp_path / "02-scenarios"
    assert run.scenario_round_dir(1) == tmp_path / "02-scenarios" / "round-1"
    assert run.scenario_part(2, "b01") == tmp_path / "02-scenarios" / "round-2" / "b01.json"
    assert run.score_parts_dir == tmp_path / "03-score"
    assert run.score_part(3) == tmp_path / "03-score" / "round-3.json"


def test_score_part_rounds_reads_what_is_on_disk(tmp_path):
    run = RunPaths(tmp_path)
    run.score_parts_dir.mkdir()
    for name in ("round-1.json", "round-10.json", "round-2.json", "notes.json"):
        (run.score_parts_dir / name).write_text("{}", encoding="utf-8")
    # Numeric, so round-10 does not sort between round-1 and round-2, and a file
    # that is not a round is ignored rather than crashing the seal.
    assert run.score_part_rounds() == [1, 2, 10]


def test_round_numbers_must_be_positive(tmp_path):
    run = RunPaths(tmp_path)
    # Mirrors coverage_round's guard: a round of 0 or -1 is a caller bug, and a
    # path built from one would silently address a directory nobody writes.
    for bad in (0, -1):
        with pytest.raises(ValueError):
            run.scenario_round_dir(bad)
        with pytest.raises(ValueError):
            run.score_part(bad)


def test_scenario_part_rejects_an_unsafe_batch_id(tmp_path):
    run = RunPaths(tmp_path)
    # Batch ids are code-minted, but this joins the same way disposition_part
    # does and the guard is what stops an artifact-sourced id escaping the run.
    with pytest.raises(UnsafeSegment):
        run.scenario_part(1, "../../etc/passwd")


def test_part_listings_are_empty_when_nothing_exists(tmp_path):
    run = RunPaths(tmp_path)
    assert run.scenario_part_rounds() == []
    assert run.scenario_part_batch_ids(1) == []


def test_part_listings_read_what_is_on_disk(tmp_path):
    run = RunPaths(tmp_path)
    for round_n, batch in ((1, "b01"), (1, "b02"), (2, "b01")):
        part = run.scenario_part(round_n, batch)
        part.parent.mkdir(parents=True, exist_ok=True)
        part.write_text("{}", encoding="utf-8")
    assert run.scenario_part_rounds() == [1, 2]
    assert run.scenario_part_batch_ids(1) == ["b01", "b02"]
    assert run.scenario_part_batch_ids(2) == ["b01"]


def test_unsafe_scenario_part_names_are_listed_not_raised(tmp_path):
    run = RunPaths(tmp_path)
    # Same split unsafe_contradiction_part_names exists for: the id-listing
    # accessor must not raise, because returning an unsafe id made the later
    # scenario_part() call raise at a call site that cannot handle it.
    d = run.scenario_round_dir(1)
    d.mkdir(parents=True)
    (d / "b01.json").write_text("{}", encoding="utf-8")
    (d / "..bad.json").write_text("{}", encoding="utf-8")
    assert run.scenario_part_batch_ids(1) == ["b01"]
    assert run.unsafe_scenario_part_names(1) == ["..bad"]
