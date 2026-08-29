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
        "propose-batches",
        "propose",
        "propose-seal",
        "score",
        "score-seal",
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


def test_the_two_new_artifacts_sit_in_the_01_band(tmp_path):
    """In the 01 band with the rest of world-model construction, because the
    numbering stays intake's: everything between 01-claims/ and
    01-world-model.json is one logical step engineered as substeps.
    """
    run = RunPaths(tmp_path / "run-1")
    assert run.services_part == run.root / "01-services.json"
    assert run.interfaces_dir == run.root / "01-interfaces"
    assert run.interface("svc-tickets") == run.root / "01-interfaces" / "svc-tickets.json"


def test_an_unsafe_service_id_never_becomes_a_path(tmp_path):
    """Ids in artifacts are produced by language models and must never be joined
    into a path unchecked. `interface()` raises; the *stage* asks
    `is_safe_segment` first so it can report a finding instead of exiting 2.
    """
    run = RunPaths(tmp_path / "run-1")
    with pytest.raises(UnsafeSegment):
        run.interface("../../etc/passwd")


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
    assert run.batches_dir == tmp_path / "02-batches"
    assert run.batches(1) == tmp_path / "02-batches" / "round-1.json"
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


def test_batches_rounds_reads_what_is_on_disk(tmp_path):
    """The batch plan is per-round, so its listing is pinned like the other two.

    The zero-padded name is the case with teeth. A singleton 02-batches.json had
    no listing at all, and the accessor that replaced it resolves the roster
    check_scenario_parts holds each round's parts to -- so round-01 folded onto 1
    would give round 1 two candidate plans, and whichever sorted last would
    decide which batch ids that round's parts were allowed to name.
    """
    run = RunPaths(tmp_path)
    run.batches_dir.mkdir()
    for name in ("round-1.json", "round-10.json", "round-2.json", "notes.json", "round-01.json"):
        (run.batches_dir / name).write_text("{}", encoding="utf-8")
    # Numeric, so round-10 does not sort between round-1 and round-2; notes.json
    # is ignored rather than crashing the read; and round-01 is rejected outright
    # rather than normalised onto the 1 that is already here.
    assert run.batches_rounds() == [1, 2, 10]


def test_an_unreadable_batches_directory_is_a_usage_error(tmp_path):
    """Exit 2, not an empty listing.

    Same ruling as the other run-directory listings: an empty [] here would let a
    caller conclude the run has no batch plans when it has plans it cannot read,
    and report every round's parts as unexplained -- a stage defect fabricated
    out of a permissions problem.
    """
    run = RunPaths(tmp_path)
    run.batches_dir.mkdir()
    run.batches_dir.chmod(0o000)
    try:
        with pytest.raises(UsageError, match="cannot read run directory"):
            run.batches_rounds()
    finally:
        run.batches_dir.chmod(0o755)


def test_scenario_part_rounds_ignores_entries_that_are_not_rounds(tmp_path):
    """The stray-tolerance the docstring claims, exercised.

    Matches score_part_rounds' notes.json case, and covers all three branches
    the filter has: a file that is not a round at all, a round- name whose
    suffix is not a number, and a round- name that is a plain *file* rather
    than the directory a round part is.
    """
    run = RunPaths(tmp_path)
    real = run.scenario_part(1, "b01")
    real.parent.mkdir(parents=True)
    real.write_text("{}", encoding="utf-8")
    (run.scenario_parts_dir / "notes.json").write_text("{}", encoding="utf-8")
    (run.scenario_parts_dir / "round-x").mkdir()
    # A *file* named round-3, which is what a half-written run or a hand-edit
    # leaves behind. It matches the name pattern and is still not a round.
    (run.scenario_parts_dir / "round-3").write_text("{}", encoding="utf-8")
    assert run.scenario_part_rounds() == [1]


@pytest.mark.parametrize("name", ["round-²", "round-1²", "round-１", "round-٣", "round-1٣"])
def test_round_listings_reject_non_ascii_digits(tmp_path, name):
    r"""str.isdigit() is wider than int(), in both directions.

    Measured, U+00B2 (superscript two): isdigit() is True and int() raises a bare
    ValueError. Unlike an unreadable directory, that one is NOT in cli.py's exit-2
    tuple, so it reaches the catch-all and becomes an exit-1 [internal] finding
    over a directory name -- the misclassification the exit-code contract forbids.

    U+FF11 and U+0663 (fullwidth one, Arabic-Indic three) are the mirror: isdigit()
    and int() BOTH accept them, so guarding int() cannot help, and the older filter
    silently invented rounds 1 and 3 from names nothing ever wrote.

    The last case puts U+0663 in the *tail*, and it is here because writing this
    predicate the other way round found the hole: `[1-9]\d{0,}` reads as a
    meaning-preserving rewrite of `[1-9][0-9]*` and is not one, because re's `\d`
    is Unicode-wide -- it matches that name and int() then returns 13, inventing a
    round no digit-by-digit reading of the name contains. The explicit [0-9] class
    is what refuses it, so the class is load-bearing and pinned here.
    """
    run = RunPaths(tmp_path)
    (run.scenario_parts_dir / name).mkdir(parents=True)
    run.score_parts_dir.mkdir(parents=True)
    (run.score_parts_dir / f"{name}.json").write_text("{}", encoding="utf-8")
    run.batches_dir.mkdir(parents=True)
    (run.batches_dir / f"{name}.json").write_text("{}", encoding="utf-8")
    assert run.scenario_part_rounds() == []
    assert run.score_part_rounds() == []
    assert run.batches_rounds() == []


def test_leading_zero_rounds_are_rejected_not_normalised(tmp_path):
    r"""round-01 is not round 1, and must not become it.

    The ruling _ROUND_PART records: `\d+` accepts round-01 and int() folds it
    onto 1, so round-01 beside round-1 yields [1, 1] -- and a duplicated round
    makes a caller walk one round twice and collide every scenario id it mints.
    Rejecting is the honest answer, since nothing in this package ever writes a
    zero-padded round; normalising would invent a round from a name that is not
    ours. round-0 goes the same way, which is what the round_n >= 1 guards
    already refuse to build.
    """
    run = RunPaths(tmp_path)
    for name in ("round-1", "round-01", "round-007", "round-0"):
        (run.scenario_parts_dir / name).mkdir(parents=True, exist_ok=True)
    run.score_parts_dir.mkdir(parents=True)
    run.batches_dir.mkdir(parents=True)
    for name in ("round-1.json", "round-01.json", "round-007.json", "round-0.json"):
        (run.score_parts_dir / name).write_text("{}", encoding="utf-8")
        (run.batches_dir / name).write_text("{}", encoding="utf-8")
    # Exactly one 1, not two: this is the assertion that fails on `\d+`.
    assert run.scenario_part_rounds() == [1]
    assert run.score_part_rounds() == [1]
    assert run.batches_rounds() == [1]


def test_round_numbers_must_be_positive(tmp_path):
    run = RunPaths(tmp_path)
    # Mirrors coverage_round's guard: a round of 0 or -1 is a caller bug, and a
    # path built from one would silently address a directory nobody writes.
    #
    # `match=` rather than a bare pytest.raises(ValueError): UsageError and
    # UnsafeSegment are both ValueError subclasses, so the unnarrowed form would
    # have passed on an unreadable directory or a rejected segment -- the wrong
    # failure entirely. The message is also what names the domain, so each
    # accessor is pinned to its own text rather than to a shared one.
    for bad in (0, -1):
        with pytest.raises(ValueError, match=f"scenario round must be >= 1, got {bad}"):
            run.scenario_round_dir(bad)
        with pytest.raises(ValueError, match=f"score round must be >= 1, got {bad}"):
            run.score_part(bad)
        with pytest.raises(ValueError, match=f"batches round must be >= 1, got {bad}"):
            run.batches(bad)


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


@pytest.mark.parametrize("mode", [0o000, 0o444])
def test_the_round_part_listings_raise_a_usage_error_on_an_unreadable_directory(tmp_path, mode):
    """The new round-part listings, held to the same ruling as every other one.

    This pins message fidelity, not an exit code. cli.py's `except (OSError,
    UsageError, ArtifactError, UnknownStage)` already maps both the bare
    PermissionError and the UsageError to exit 2, so the conversion changes no
    exit code -- the earlier claim that it did described a cli.py that predates
    the commit which added OSError to that tuple.

    What it does change is *which artifact the error names*. Observed before the
    fix: `PermissionError ... '<run>/02-scenarios/round-1'`, naming an arbitrary
    child the loop happened to stat first, where every sibling listing names the
    directory the accessor actually reads. That is CLAUDE.md's "a finding must
    name the right artifact" rule applied to a 2, and it is what makes this
    accessor indistinguishable from _instance_dir_names to a caller.

    Both modes, because they fail in different places. At 0o000 the listing
    itself raises and list_dir/list_json converts it. At 0o444 the listing
    succeeds and stat'ing a *child* is what raises -- which list_dir cannot
    convert because it never touches the child, so scenario_part_rounds carries
    its own catch the way _instance_dir_names does.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = RunPaths(tmp_path)
    # A round directory holding a *.json child, because that is what both
    # listings really read: scenario_part_rounds stats round-1 as a child of
    # 02-scenarios/, and the batch-id listings stat b01.json inside it. Without
    # each of those children the 0o444 stat that raises is never reached and the
    # listing comes back empty instead.
    part = run.scenario_part(1, "b01")
    part.parent.mkdir(parents=True)
    part.write_text("{}", encoding="utf-8")
    run.score_parts_dir.mkdir(parents=True)
    run.score_part(1).write_text("{}", encoding="utf-8")

    directories = (run.scenario_parts_dir, run.scenario_round_dir(1), run.score_parts_dir)
    calls = (
        run.scenario_part_rounds,
        lambda: run.scenario_part_batch_ids(1),
        lambda: run.unsafe_scenario_part_names(1),
        run.score_part_rounds,
    )
    # Innermost first, so the parent is still traversable while the child's mode
    # is being set -- and restored outermost first in the finally for the same
    # reason, which is why a failed assertion cannot leave the tree unreadable.
    for directory in reversed(directories):
        directory.chmod(mode)
    try:
        for call in calls:
            # UsageError is a ValueError, so a bare PermissionError would not
            # satisfy this -- pytest.raises does not match sibling exceptions.
            with pytest.raises(UsageError, match="cannot read run directory"):
                call()
    finally:
        for directory in directories:
            directory.chmod(0o755)

    # And the same four calls answer normally once the modes are back: without
    # this the test would pass just as well if the accessors were broken outright
    # and raised UsageError on a perfectly readable run.
    assert run.scenario_part_rounds() == [1]
    assert run.scenario_part_batch_ids(1) == ["b01"]
    assert run.unsafe_scenario_part_names(1) == []
    assert run.score_part_rounds() == [1]
