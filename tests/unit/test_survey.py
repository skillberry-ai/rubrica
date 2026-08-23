"""Minting a run from a corpus.

The run directory now exists before anything is admitted, which is the change
this whole design turns on: the triage record has to live inside the run so
check-refs can resolve against it, and check-refs reads a run and nothing else.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from rubrica import intake, slices, survey, validate
from rubrica.artifacts import canonical_bytes, read_json
from rubrica.errors import UsageError
from rubrica.paths import is_safe_segment

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


def test_the_default_catalogue_is_comfortably_under_budget(tmp_path):
    """A small corpus writes normally under the default budget -- the common
    case Fix 2 must not disturb."""
    catalogue = read_json(_survey(tmp_path).catalogue)
    assert catalogue["policy"]["max_catalogue_bytes"] == survey.DEFAULT_MAX_CATALOGUE_BYTES


def test_a_catalogue_over_the_byte_budget_is_a_usage_error_not_a_finding(tmp_path):
    """--max-candidates is a count guard, but the parsec corpus produced 351
    candidates (under that cap) and a 476KB catalogue -- bytes, not count, is
    what fills a dispatched model's context window. Same exit-2 shape as the
    count guard: narrowing --corpus/--exclude is the only fix, and no repair
    prompt can shrink a corpus, so this is UsageError, never a Finding.

    Also proves the ordering the count guard already holds: validate before
    run.root.mkdir(), so a rejected run leaves no trace on disk for a human or
    orchestrator to puzzle over.
    """
    runs_dir = tmp_path / "runs"
    with pytest.raises(UsageError, match=r"catalogue.*bytes.*max_catalogue_bytes=64"):
        _survey(tmp_path, runs_dir=runs_dir, max_catalogue_bytes=64)
    assert not runs_dir.exists()


def test_survey_refuses_a_corpus_whose_digest_row_exceeds_a_slice(tmp_path):
    """A file wide and deep enough to survive the Task 1 clamp and still exceed
    one slice would have to be pathological; construct the condition directly
    by lowering nothing and raising the corpus instead.

    200 keys of 1200 "k"s each: measured to a 64-node skeleton with
    skeleton_nodes_truncated False -- Task 1's node clamp bounds node *count*
    and does not bind here -- and an 83,601-byte row against the 65,536-byte
    cap. (900 "k"s, tried first, measured at only 64,396 bytes: 1,140 bytes
    *under* the cap, too small to raise this guard.) The clamp and this guard
    are independent checks, not redundant ones -- the clamp bounds node count,
    this guard bounds row width, and this payload proves the first can hold
    while the second still fires.
    """
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    payload = {("k" * 1200) + str(i): {"a": 1} for i in range(200)}
    (corpus / "wide.json").write_text(json.dumps(payload), encoding="utf-8")
    runs_dir = tmp_path / "runs"
    with pytest.raises(UsageError) as exc:
        survey.survey(
            corpus_roots=[corpus],
            runs_dir=runs_dir,
            target_name="t",
            target_interface="http",
            objective="breadth",
            max_rounds=2,
            max_scenarios=128,
            now=NOW,
        )
    message = str(exc.value)
    assert "wide-json" in message  # names the candidate
    assert str(slices.DEFAULT_SLICE_BYTES) in message  # names both numbers
    assert not runs_dir.exists()  # leaves no directory behind


def test_survey_leaves_a_normal_corpus_alone(tmp_path):
    """The common case this guard must not disturb."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "notes.md").write_text("# A\nprose\n", encoding="utf-8")
    run = survey.survey(
        corpus_roots=[corpus],
        runs_dir=tmp_path / "runs",
        target_name="t",
        target_interface="http",
        objective="breadth",
        max_rounds=2,
        max_scenarios=128,
        now=NOW,
    )
    assert run.catalogue.is_file()


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


def test_a_file_duplicated_across_two_roots_is_excluded_once(tmp_path):
    """The cross-root dedup gap the per-root loop opened: each walk_corpus
    call used to start with its own empty `seen`, so a byte-identical file
    present under two --corpus roots (a source tree and a docs tree, say) was
    admitted twice -- two identical inputs, two identical claims files, no
    finding anywhere. survey() now shares one `seen` dict across every
    per-root call, so the duplicate is caught exactly once, and the surviving
    copy is the one under the earlier root -- same rule as within one root.
    """
    root0 = tmp_path / "root0"
    root0.mkdir()
    root1 = tmp_path / "root1"
    root1.mkdir()
    (root0 / "shared.md").write_text("identical bytes\n", encoding="utf-8")
    (root1 / "shared.md").write_text("identical bytes\n", encoding="utf-8")

    catalogue = read_json(_survey(tmp_path, corpus_roots=[root0, root1]).catalogue)
    corpus_candidates = [c for c in catalogue["candidates"] if c["origin"] == "corpus"]
    assert [c["root_index"] for c in corpus_candidates] == [0]

    duplicates = [e for e in catalogue["excluded"] if e["reason"] == "duplicate"]
    assert len(duplicates) == 1
    assert duplicates[0]["path"] == "shared.md"


def test_an_unreadable_corpus_root_is_exit_two_material(tmp_path):
    root = _corpus(tmp_path)
    root.chmod(0o000)
    try:
        with pytest.raises(UsageError, match="cannot read corpus root"):
            _survey(tmp_path, corpus_roots=[root])
    finally:
        root.chmod(0o755)


# 200,000 opening brackets: deep enough that CPython's json decoder exhausts
# its recursion limit rather than reporting a syntax error, which is the whole
# point -- it raises RecursionError, not JSONDecodeError, and nothing on either
# new command's dispatch path caught that.
_PATHOLOGICALLY_NESTED = "[" * 200_000 + "]" * 200_000


def test_a_pathologically_nested_file_does_not_abort_the_inventory(tmp_path):
    """survey.py's own header rules out size-based exclusion, so an arbitrary
    user tree's worst file reaches `json.loads` on the explode path with nothing
    upstream having filtered it. Measured: `survey --corpus DIR` over a corpus
    containing one 200,000-deep `[[[...]]]` raised RecursionError out of
    cli.main() -- one hostile file took down the whole inventory, and cli.py's
    survey block catches only (UsageError, ArtifactError, OSError) so it was an
    empty-stdout exit rather than a message.

    Task 6 had already fixed exactly this in digest.digest_for_path; the two
    siblings that decode JSON (this one and intake._json_or_none) were missed
    and are now on the hot path of both new commands.

    Not exploding the file is the right outcome and is asserted, not merely
    tolerated: a container this decoder cannot read is one candidate, and the
    catalogue must still validate.
    """
    root = _corpus(tmp_path)
    (root / "nested.json").write_text(_PATHOLOGICALLY_NESTED, encoding="utf-8")

    run = _survey(tmp_path, corpus_roots=[root])

    catalogue = read_json(run.catalogue)
    nested = [c for c in catalogue["candidates"] if c.get("path") == "nested.json"]
    assert len(nested) == 1, "the file is one candidate, exploded into nothing"
    assert nested[0]["admissible"] is True
    assert not [
        c
        for c in catalogue["candidates"]
        if (c.get("container") or {}).get("candidate_id") == nested[0]["candidate_id"]
    ]
    assert validate.validate_stage(run, "survey") == []


def test_classify_returns_a_kind_for_a_pathologically_nested_file(tmp_path):
    """intake._json_or_none's half of the same gap. `classify` is reached by
    `survey` (for every corpus file), by `intake --input`, and by
    `adopt-projection` through triage.check_acceptance -- three commands, none
    of whose dispatch blocks catch RecursionError. A kind of "other" is the
    correct answer: nothing about the content is readable, and the extract skill
    reads the artifact itself and is free to disagree.
    """
    source = tmp_path / "nested.json"
    source.write_text(_PATHOLOGICALLY_NESTED, encoding="utf-8")
    assert intake.classify(source) == "other"


def _dict_keyed_corpus(tmp_path):
    """A corpus whose only container is an *object*, keyed on ids like real ones.

    Its own directory rather than an addition to `_corpus` or to the committed
    `corpus-toy/` fixture: both are pinned by candidate-count assertions here and
    in test_admit.py / test_survey_fixture.py, and this test is about ids, not
    counts.

    The three keys are not adversarial inventions -- spec section 5.2 makes
    id-keyed containers first-class, and the ids real captures use carry `:`,
    `/` and spaces. `~` is here because `_escape_pointer_token` turns it into
    `~0` and `/` into `~1`, so the escaping the pointer *needs* is itself a
    source of characters no id may contain.
    """
    root = tmp_path / "dict-corpus"
    root.mkdir()
    (root / "traces.json").write_text(
        json.dumps(
            {
                "trace one/a": {"trace_id": "a", "status": "OK", "spans": [{"name": "t"}]},
                "trace two~b": {"trace_id": "b", "status": "OK", "spans": [{"name": "t"}]},
                "Trace Three": {"trace_id": "c", "status": "OK", "spans": [{"name": "t"}]},
            }
        ),
        encoding="utf-8",
    )
    return root


def test_a_dict_keyed_container_mints_a_catalogue_that_passes_its_own_gate(tmp_path):
    """The coverage gap that let this survive twenty reviews.

    `test_survey_explode.py` exercises `explode()` in isolation and
    `corpus-toy/capture.json` is an *array*, so no test had ever driven a
    dict-keyed container through `survey()` into a validated catalogue.
    Measured on the keys below: survey exited 0 and `validate --stage survey`
    then reported three schema findings -- the command minting an artifact that
    fails its own layer-1 gate, which no exit code anywhere would have revealed.

    validate_stage == [] is the assertion that matters. The id-shape assertions
    below it say the same thing more legibly when it fails.
    """
    run = _survey(tmp_path, corpus_roots=[_dict_keyed_corpus(tmp_path)])

    assert validate.validate_stage(run, "survey") == []

    catalogue = read_json(run.catalogue)
    elements = [c for c in catalogue["candidates"] if c["origin"] == "container_element"]
    assert len(elements) == 3, "one candidate per key, in document order"
    for element in elements:
        assert is_safe_segment(element["candidate_id"]), element["candidate_id"]
        assert len(element["candidate_id"]) <= 128
    # The pointers themselves keep their RFC 6901 escaping -- the id is slugged,
    # the pointer is not, because intake resolves the element with it.
    assert [e["container"]["json_pointer"] for e in elements] == [
        "/trace one~1a",
        "/trace two~0b",
        "/Trace Three",
    ]
    # Distinct ids, so intake materialises three inputs rather than overwriting.
    assert len({e["candidate_id"] for e in elements}) == 3


def test_an_exploded_array_element_keeps_the_id_it_already_had(tmp_path):
    """The other direction of the slug fix, and the reason it is a `-` join
    rather than a rewrite: `capture-json-0` is written into committed fixtures
    and named by tests/unit/test_admit.py's triage records, so slugging the
    pointer half had to leave the array case byte-identical."""
    run = _survey(tmp_path)
    catalogue = read_json(run.catalogue)
    elements = [c for c in catalogue["candidates"] if c["origin"] == "container_element"]
    assert [e["candidate_id"] for e in elements] == [
        "capture-json-0",
        "capture-json-1",
        "capture-json-2",
        "capture-json-3",
    ]


def test_a_long_container_name_and_a_long_key_stay_inside_the_id_cap(tmp_path):
    """maxLength 128 on catalogue-0.1.json's `id`, which the composed id can
    exceed on its own: `slug` caps each half at 96, so an unbudgeted join
    reaches 193. The container prefix is what gets truncated, never the
    pointer-derived suffix -- every element of one container shares the prefix,
    so trimming it identically keeps the elements distinguishable, while
    trimming the suffix would collapse them onto one base id."""
    root = tmp_path / "long-corpus"
    root.mkdir()
    long_key = "k" * 120
    (root / f"{'c' * 120}.json").write_text(
        json.dumps(
            {
                f"{long_key}-{index}": {"trace_id": str(index), "status": "OK", "spans": []}
                for index in range(3)
            }
        ),
        encoding="utf-8",
    )

    run = _survey(tmp_path, corpus_roots=[root])

    assert validate.validate_stage(run, "survey") == []
    catalogue = read_json(run.catalogue)
    element_ids = [
        c["candidate_id"] for c in catalogue["candidates"] if c["origin"] == "container_element"
    ]
    assert len(element_ids) == 3
    assert len(set(element_ids)) == 3, "truncation must not make two elements the same candidate"
    for element_id in element_ids:
        assert len(element_id) <= 128
        assert is_safe_segment(element_id), element_id
