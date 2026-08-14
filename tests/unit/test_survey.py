"""Minting a run from a corpus.

The run directory now exists before anything is admitted, which is the change
this whole design turns on: the triage record has to live inside the run so
check-refs can resolve against it, and check-refs reads a run and nothing else.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from rubrica import survey, validate
from rubrica.artifacts import canonical_bytes, read_json
from rubrica.errors import UsageError

NOW = datetime(2026, 8, 14, 21, 30, 0, tzinfo=UTC)


def _corpus(tmp_path, *, traces=4):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "README.md").write_text("# Target\n\n## Tools\n\nprose\n", encoding="utf-8")
    (root / "capture.json").write_text(
        json.dumps(
            [
                {"trace_id": f"tr-{i}", "status": "OK", "spans": [{"name": "t"}]}
                for i in range(traces)
            ]
        ),
        encoding="utf-8",
    )
    return root


def _survey(tmp_path, **over):
    kwargs = dict(
        runs_dir=tmp_path / "runs",
        target_name="parsec",
        target_interface="http-sse",
        objective="breadth",
        max_rounds=2,
        max_scenarios=128,
        now=NOW,
    )
    # corpus_roots is built lazily, only when the caller has not supplied its
    # own: building it eagerly (as a `dict(corpus_roots=[_corpus(tmp_path)],
    # ...)` keyword-argument expression, evaluated unconditionally before
    # `kwargs.update(over)` can override it) collides with a caller that
    # already minted `tmp_path/"corpus"` itself -- measured: two tests below
    # pass their own `corpus_roots=[_corpus(tmp_path, ...)]` and the eager
    # form raised FileExistsError on the helper's own redundant mkdir, before
    # survey.survey was ever called.
    if "corpus_roots" not in over:
        kwargs["corpus_roots"] = [_corpus(tmp_path)]
    kwargs.update(over)
    return survey.survey(**kwargs)


def test_survey_mints_a_run_and_writes_a_valid_catalogue(tmp_path):
    run = _survey(tmp_path)
    assert run.root.name == "run-20260814-213000"
    assert run.catalogue.is_file()
    assert validate.validate_stage(run, "survey") == []
    # No manifest yet: intake still writes it, so manifest.json appears only when
    # there are inputs to name and inputs.minItems stays as strict as it is.
    assert not run.manifest.exists()
    assert not run.inputs_dir.exists()


def test_the_container_and_its_elements_are_all_candidates(tmp_path):
    catalogue = read_json(_survey(tmp_path).catalogue)
    by_origin = {}
    for candidate in catalogue["candidates"]:
        by_origin.setdefault(candidate["origin"], []).append(candidate)
    assert len(by_origin["container_element"]) == 4
    corpus_paths = {c["path"] for c in by_origin["corpus"]}
    assert corpus_paths == {"README.md", "capture.json"}
    container = next(c for c in by_origin["corpus"] if c["path"] == "capture.json")
    # The container stays visible but cannot be admitted: admitting it would
    # hand rb-extract all four records as one artifact, which is the thing
    # exploding exists to prevent.
    assert container["admissible"] is False
    assert all(c["admissible"] for c in by_origin["container_element"])


def test_an_element_carries_a_resolvable_pointer_and_its_materialised_digest(tmp_path):
    """The sha256 is of the bytes intake will write, not of the container.

    Task 14 materialises this element and refs.check_inputs re-hashes the file;
    if this digest were of anything else, every exploded input would report a
    mismatch the moment it was admitted.
    """
    catalogue = read_json(_survey(tmp_path).catalogue)
    element = next(c for c in catalogue["candidates"] if c["origin"] == "container_element")
    assert element["container"]["json_pointer"].startswith("/")
    assert element["container"]["candidate_id"] == "capture-json"
    source = json.loads((tmp_path / "corpus" / "capture.json").read_text(encoding="utf-8"))
    index = int(element["container"]["json_pointer"].lstrip("/"))
    import hashlib

    assert element["sha256"] == hashlib.sha256(canonical_bytes(source[index])).hexdigest()
    assert element["bytes"] == len(canonical_bytes(source[index]))


def test_candidate_ids_are_unique_and_safe_path_segments(tmp_path):
    catalogue = read_json(_survey(tmp_path).catalogue)
    ids = [c["candidate_id"] for c in catalogue["candidates"]]
    assert len(ids) == len(set(ids))
    from rubrica.paths import is_safe_segment

    assert all(is_safe_segment(cid) for cid in ids)


def test_the_policy_that_shaped_the_set_is_recorded(tmp_path):
    """A reader of a catalogue needs to know which rules produced it, or the
    exclusions and the splits are unexplainable a week later."""
    policy = read_json(_survey(tmp_path).catalogue)["policy"]
    assert policy["explode_min_elements"] == survey.EXPLODE_MIN_ELEMENTS
    assert policy["explode_min_common_keys"] == survey.EXPLODE_MIN_COMMON_KEYS
    assert set(policy["exclusion_reasons"]) == set(survey.EXCLUSION_REASONS)


def test_too_many_candidates_is_a_usage_error_not_a_finding(tmp_path):
    """Narrowing --corpus is the fix, and the exit-code contract puts a usage
    error at 2. No orchestrator repair can shrink a corpus."""
    with pytest.raises(UsageError, match="max_candidates"):
        _survey(tmp_path, corpus_roots=[_corpus(tmp_path, traces=40)], max_candidates=10)


def test_a_naive_datetime_is_refused(tmp_path):
    """Same rule intake already holds: .astimezone() would assume the host zone,
    so two hosts would mint two different run ids for the same call."""
    with pytest.raises(UsageError, match="timezone-aware"):
        _survey(tmp_path, now=datetime(2026, 8, 14, 21, 30, 0))


def test_a_blank_target_name_is_refused_before_the_run_is_minted(tmp_path):
    """intake refuses this and the reason transfers: minting anyway exits 0 and
    surfaces steps later as findings against an artifact no repair can fix."""
    with pytest.raises(UsageError, match="target-name"):
        _survey(tmp_path, target_name="   ")
    assert not (tmp_path / "runs").exists()


def test_root_index_is_the_loop_index_not_a_rematch(tmp_path):
    """The required change this task made over the brief's own pseudocode:
    root_index comes from enumerate(corpus_roots) inside the walk_corpus loop,
    never from re-matching a candidate's path against corpus_roots afterwards
    (the brief's `next(r for r in corpus_roots if path.is_relative_to(r))`,
    which picks the wrong root whenever two roots share a path).

    Pinned two ways at once, because both are the point of the field:
    - two roots share the relative path "shared.md" with different content,
      so the same `path` string appears with root_index 0 from the first root
      and root_index 1 from the second -- the exact case a re-match approach
      gets wrong, since it would have to guess which root "shared.md" came
      from after the fact.
    - a container_element candidate carries no root_index at all: the field
      is scoped to origin "corpus" only, and this pins the absence, not just
      the presence.

    Not attempted: making the shared path also byte-identical across roots to
    additionally exercise duplicate detection. walk_corpus's `seen` dict is
    local to one call (see the task report's cross-root-dedupe finding), so a
    byte-identical file across two roots is never flagged `duplicate` under
    the current per-root loop regardless of this test -- forcing that here
    would test the dedupe gap, not root_index, so the two roots' shared file
    deliberately differs in content instead.
    """
    root0 = tmp_path / "root0"
    root0.mkdir()
    (root0 / "shared.md").write_text("# From root0\n", encoding="utf-8")
    root1 = tmp_path / "root1"
    root1.mkdir()
    (root1 / "shared.md").write_text("# From root1, different bytes\n", encoding="utf-8")
    (root1 / "capture.json").write_text(
        json.dumps(
            [{"trace_id": f"tr-{i}", "status": "OK", "spans": [{"name": "t"}]} for i in range(4)]
        ),
        encoding="utf-8",
    )

    catalogue = read_json(_survey(tmp_path, corpus_roots=[root0, root1]).catalogue)
    corpus_candidates = [c for c in catalogue["candidates"] if c["origin"] == "corpus"]
    shared = [c for c in corpus_candidates if c["path"] == "shared.md"]
    assert {c["root_index"] for c in shared} == {0, 1}
    assert len({c["sha256"] for c in shared}) == 2  # not deduped against each other

    element_candidates = [c for c in catalogue["candidates"] if c["origin"] == "container_element"]
    assert element_candidates, "fixture must still explode something to exercise the negative case"
    assert all("root_index" not in c for c in element_candidates)


def test_an_unreadable_corpus_root_is_exit_two_material(tmp_path):
    root = _corpus(tmp_path)
    root.chmod(0o000)
    try:
        with pytest.raises(UsageError, match="cannot read corpus root"):
            _survey(tmp_path, corpus_roots=[root])
    finally:
        root.chmod(0o755)
