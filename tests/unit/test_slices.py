import json
from pathlib import Path

import pytest

from rubrica import slices, survey, validate
from rubrica.artifacts import canonical_bytes, read_json, write_json
from rubrica.errors import UsageError


def _cand(cid, *, path=None, kind="source_code", root=0, container=None, pad=1000, sig=None):
    """One catalogue candidate, padded to a known byte cost."""
    row = {
        "candidate_id": cid,
        "kind": kind,
        "bytes": pad,
        "sha256": "0" * 64,
        "admissible": True,
    }
    if container:
        row |= {
            "origin": "container_element",
            "container": {"candidate_id": container, "json_pointer": f"/{cid}"},
        }
    else:
        row |= {"origin": "corpus", "path": path, "root_index": root}
    digest = {"_pad": "p" * pad}
    if sig:
        digest |= {"heuristics_fired": sig[0], "names": sig[1]}
    row["digest"] = digest
    return row


def test_every_candidate_lands_in_exactly_one_slice():
    cands = [_cand(f"c{i}", path=f"src/m{i}.py") for i in range(80)]
    plan = slices.plan_slices(cands, cap=16384)
    seen = [cid for s in plan for cid in s.candidate_ids]
    assert sorted(seen) == sorted(c["candidate_id"] for c in cands)
    assert len(seen) == len(set(seen))


def test_no_slice_exceeds_the_cap():
    cands = [_cand(f"c{i}", path=f"src/a/b/m{i}.py") for i in range(200)]
    plan = slices.plan_slices(cands, cap=16384)
    by_id = {c["candidate_id"]: c for c in cands}
    for s in plan:
        assert sum(slices.row_bytes(by_id[cid]) for cid in s.candidate_ids) <= 16384


def test_two_roots_with_the_same_directory_do_not_merge():
    # The bug real data caught: every measured catalogue is single-root, so a
    # key on `path` alone would merge two corpora's src/ and nothing on disk
    # would show it.
    cands = [_cand(f"a{i}", path=f"src/m{i}.py", root=0) for i in range(4)] + [
        _cand(f"b{i}", path=f"src/m{i}.py", root=1) for i in range(4)
    ]
    plan = slices.plan_slices(cands, cap=200)  # small cap: forces separate slices
    for s in plan:
        roots = {
            next(c for c in cands if c["candidate_id"] == cid)["root_index"]
            for cid in s.candidate_ids
        }
        assert len(roots) == 1, f"slice {s.id} mixes roots {roots}"


def test_two_roots_do_not_share_a_slice_even_when_both_would_fit_together():
    # test_two_roots_with_the_same_directory_do_not_merge uses cap=200, which
    # is smaller than a single row's own cost -- every unit gets its own
    # slice regardless of any root boundary, so that test cannot tell the
    # `_pack_adjacent` root guard apart from its absence. This one uses small
    # rows and a cap generous enough that both roots' whole contribution would
    # comfortably pack into ONE slice if nothing stopped it -- the sanity
    # assertion below confirms that's really true of these numbers, so a
    # passing root-separation assertion after it means the guard did the work.
    root0 = [_cand(f"a{i}", path=f"src/m{i}.py", root=0, pad=50) for i in range(5)]
    root1 = [_cand(f"b{i}", path=f"src/m{i}.py", root=1, pad=50) for i in range(5)]
    cands = root0 + root1
    cap = 4000
    assert sum(slices.row_bytes(c) for c in cands) <= cap
    plan = slices.plan_slices(cands, cap=cap)
    for s in plan:
        roots = {
            next(c for c in cands if c["candidate_id"] == cid)["root_index"]
            for cid in s.candidate_ids
        }
        assert len(roots) == 1, f"slice {s.id} mixes roots {roots}"


def test_slice_labels_are_unique():
    cands = [_cand(f"a{i}", path=f"m{i}.py", root=0) for i in range(3)] + [
        _cand(f"b{i}", path=f"m{i}.py", root=1) for i in range(3)
    ]
    plan = slices.plan_slices(cands, cap=200)
    labels = [s.label for s in plan]
    assert len(labels) == len(set(labels)), labels


def test_slice_ids_are_safe_path_segments_in_order():
    from rubrica.paths import safe_segment

    plan = slices.plan_slices([_cand(f"c{i}", path=f"src/m{i}.py") for i in range(40)], cap=8192)
    assert [s.id for s in plan] == [f"s{i:02d}" for i in range(1, len(plan) + 1)]
    for s in plan:
        assert safe_segment(s.id) == s.id


def _signature_of(candidate):
    """The §5 step-5 clustering key, computed independently of `slices._signature`
    so this test exercises observable behaviour rather than the private helper."""
    digest = candidate.get("digest") or {}
    fired = digest.get("heuristics_fired") or []
    names = digest.get("names") or []
    return (tuple(sorted(fired)), tuple(sorted(names[:6])))


def test_a_signature_family_that_fits_is_never_split_across_slices():
    # Two equal-sized families in one container, ids interleaved (e00 is
    # family A, e01 is family B, e02 is family A, ...) so that a splitter
    # ignoring signature and simply chunking by candidate_id would scatter
    # both families across every chunk. Each family alone fits the cap; the
    # two together do not, so the container must still be split -- the
    # question is whether the split respects signature or candidate_id.
    #
    # This replaces test_a_container_clusters_near_duplicates_into_one_slice
    # from the task brief: that test's assertion carried an `or` that could
    # pass even if the family were scattered, as long as *a* fragment shared
    # the odd element's slice -- not a guard, because nothing distinguishing
    # scattered-but-technically-true from actually-clustered was ever checked.
    fam_a = [
        _cand(f"e{2 * i:02d}", kind="trace", container="cap", sig=(["names"], ["op_a"]), pad=200)
        for i in range(10)
    ]
    fam_b = [
        _cand(
            f"e{2 * i + 1:02d}", kind="trace", container="cap", sig=(["names"], ["op_b"]), pad=200
        )
        for i in range(10)
    ]
    cands = fam_a + fam_b
    cap = 6000  # each family (~5900B) fits alone; both together (~11800B) do not
    plan = slices.plan_slices(cands, cap=cap)

    by_id = {c["candidate_id"]: c for c in cands}
    slice_of = {cid: s.id for s in plan for cid in s.candidate_ids}

    families: dict[tuple, list[str]] = {}
    for c in cands:
        families.setdefault(_signature_of(c), []).append(c["candidate_id"])

    for signature, member_ids in families.items():
        total = sum(slices.row_bytes(by_id[cid]) for cid in member_ids)
        holding_slices = {slice_of[cid] for cid in member_ids}
        if total <= cap:
            assert len(holding_slices) == 1, (
                f"signature {signature} fits the cap ({total}B <= {cap}B) but its members "
                f"landed in {sorted(holding_slices)} instead of one slice"
            )
        else:
            assert len(holding_slices) > 1, (
                f"signature {signature} exceeds the cap ({total}B > {cap}B) but was not split"
            )


def test_provenance_states_how_much_of_a_group_a_slice_holds():
    # The homogeneous worst case: a member holding part of an identical family
    # cannot otherwise know it. Code knows; stating it takes no judgment away.
    cands = [
        _cand(f"h{i}", kind="trace", container="big", sig=(["names"], ["same"]), pad=900)
        for i in range(60)
    ]
    plan = slices.plan_slices(cands, cap=8192)
    assert len(plan) > 1
    for s in plan:
        entry = next(p for p in s.provenance if p["group"].startswith("container:big"))
        assert entry["in_this_slice"] == len(s.candidate_ids)
        assert entry["in_group_total"] == 60
        assert entry["other_slices"]
        assert s.id not in entry["other_slices"]


def test_a_flat_corpus_falls_through_to_kind_then_bytes():
    cands = [_cand(f"c{i}", path=f"all/f{i}.py") for i in range(120)]
    plan = slices.plan_slices(cands, cap=8192)
    assert len(plan) > 1
    assert sum(len(s.candidate_ids) for s in plan) == 120


def test_a_single_row_over_cap_is_reported_not_silently_split():
    big = _cand("mega", path="d/mega.json", kind="other", pad=40000)
    small = [_cand(f"n{i}", path="d/n.py") for i in range(3)]
    assert slices.oversized_rows([big] + small, cap=8192) == [("mega", slices.row_bytes(big))]
    assert slices.oversized_rows(small, cap=8192) == []


def test_planning_is_deterministic():
    cands = [_cand(f"c{i}", path=f"src/x{i % 7}/m{i}.py") for i in range(90)]
    first = slices.plan_slices(cands, cap=8192)
    second = slices.plan_slices(list(reversed(cands)), cap=8192)
    assert [(s.id, s.candidate_ids) for s in first] == [(s.id, s.candidate_ids) for s in second]


def test_one_200kb_row_is_reported_not_partitioned():
    # Spec §5.3's tenth shape, absent from the code block the task brief
    # gave verbatim: one row too large for any slice to hold, plus a handful
    # of ordinary candidates. It cannot go in SHAPES -- no partition of it
    # can satisfy test_every_corpus_shape_partitions_within_the_cap's cap
    # assertion, by construction -- so it gets its own test, asserting
    # oversized_rows reports exactly the one row Task 3 is what refuses.
    huge = _cand("huge", path="d/huge.json", kind="other", pad=200_000)
    normal = [_cand(f"c{i}", path=f"d/c{i}.py") for i in range(5)]
    cands = [huge, *normal]
    assert slices.row_bytes(huge) > slices.DEFAULT_SLICE_BYTES
    assert slices.oversized_rows(cands) == [("huge", slices.row_bytes(huge))]


SHAPES = {
    "flat": lambda: [_cand(f"c{i}", path=f"all/f{i}.py") for i in range(400)],
    "dominant_subtree": lambda: (
        [_cand(f"d{i}", path=f"src/a/b/c/d{i}.py") for i in range(380)]
        + [_cand(f"t{i}", path=f"t{i}.md", kind="design_doc") for i in range(20)]
    ),
    "deep_narrow": lambda: [
        _cand(f"n{i}", path="/".join(f"l{j}" for j in range(12)) + f"/n{i}.py") for i in range(300)
    ],
    "many_containers": lambda: [
        _cand(f"c{c}e{e}", kind="trace", container=f"cont{c}", sig=(["names"], [f"op{c}"]))
        for c in range(40)
        for e in range(15)
    ],
    "homogeneous_container": lambda: [
        _cand(f"h{i}", kind="trace", container="big", sig=(["names"], ["same"])) for i in range(500)
    ],
    "unique_signatures": lambda: [
        _cand(f"u{i}", kind="trace", container="big", sig=(["names"], [f"u{i}"]))
        for i in range(500)
    ],
    "multi_root": lambda: (
        [_cand(f"r{r}s{i}", path=f"src/m{i}.py", root=r) for r in range(3) for i in range(60)]
        + [_cand(f"r{r}t{i}", path=f"tests/t{i}.py", root=r) for r in range(3) for i in range(40)]
    ),
    "few_huge_rows": lambda: [
        _cand(f"g{i}", path=f"d/g{i}.json", kind="other", pad=30000) for i in range(20)
    ],
    "tiny": lambda: [_cand(f"s{i}", path=f"s{i}.md", kind="design_doc") for i in range(5)],
}


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_every_corpus_shape_partitions_within_the_cap(name):
    cands = SHAPES[name]()
    plan = slices.plan_slices(cands, cap=slices.DEFAULT_SLICE_BYTES)
    seen = [cid for s in plan for cid in s.candidate_ids]
    assert sorted(seen) == sorted(c["candidate_id"] for c in cands)
    by_id = {c["candidate_id"]: c for c in cands}
    for s in plan:
        assert (
            sum(slices.row_bytes(by_id[cid]) for cid in s.candidate_ids)
            <= slices.DEFAULT_SLICE_BYTES
        )


def _toy_run(tmp_path):
    return survey.survey(
        corpus_roots=[Path("tests/fixtures/toy")],
        runs_dir=tmp_path / "runs",
        target_name="toy",
        target_interface="http",
        objective="breadth",
        max_rounds=2,
        max_scenarios=128,
    )


def test_writing_slices_produces_one_shard_per_slice_each_readable_whole(tmp_path):
    run = _toy_run(tmp_path)
    # cap=2048 (the brief's own "small cap: forces several") is smaller than
    # this fixture's own api-json candidate (2381B), which oversized_rows
    # correctly refuses -- 2500 is the smallest cap over every single row that
    # still splits the toy fixture's ~4.1KB of candidates into more than one
    # slice.
    path, plan = slices.write_slices(run, cap=2500)
    assert path == run.slices
    assert len(plan) > 1
    for s in plan:
        shard = read_json(run.slice_shard(s.id))
        assert shard["slice_id"] == s.id
        assert shard["run_id"] == read_json(run.catalogue)["run_id"]
        # The head fields every member needs, in every shard, by construction.
        assert shard["request"] == read_json(run.catalogue)["request"]
        assert shard["policy"] == read_json(run.catalogue)["policy"]
        assert [c["candidate_id"] for c in shard["candidates"]] == list(s.candidate_ids)
        assert len(canonical_bytes(shard)) < 256 * 1024  # one Read
    assert validate.validate_stage(run, "triage-slices") == []


def test_writing_slices_is_idempotent(tmp_path):
    """Re-runnable, because a later task's adoption path re-mints the plan
    after a human admits a projection."""
    run = _toy_run(tmp_path)
    slices.write_slices(run)
    first = run.slices.read_bytes()
    shards_first = sorted(p.name for p in run.slices_dir.iterdir())
    slices.write_slices(run)
    assert run.slices.read_bytes() == first
    assert sorted(p.name for p in run.slices_dir.iterdir()) == shards_first


def test_a_stale_shard_from_a_previous_plan_is_removed(tmp_path):
    """Otherwise a re-plan leaves an orphan shard on disk that a later
    check_slices would report against a plan that no longer names it."""
    run = _toy_run(tmp_path)
    slices.write_slices(run)
    (run.slices_dir / "s99.json").write_text("{}", encoding="utf-8")
    slices.write_slices(run)
    assert not (run.slices_dir / "s99.json").exists()


# Two of these four were already refused correctly and two were not, which is
# why all four are here rather than only the broken pair: `[]` and `"hi"`
# answer `key not in catalogue` (the second by substring test, which is a
# coincidence rather than a check), while `null` and `7` raised TypeError and
# surfaced as an [internal] finding at exit 1 naming the run root -- a
# filesystem-shaped problem reported as a stage defect, against the wrong
# artifact. The guard's job is to make all four the same refusal.
@pytest.mark.parametrize("document", ["null", "7", '"hi"', "[]"])
def test_a_catalogue_that_is_not_an_object_is_refused_not_partitioned(tmp_path, document):
    run = _toy_run(tmp_path)
    run.catalogue.write_text(f"{document}\n", encoding="utf-8")
    with pytest.raises(UsageError) as caught:
        slices.write_slices(run, cap=2500)
    # The message must name the catalogue, because the operator's next move is
    # to look at it; a UsageError naming the run root sends them to a directory.
    assert str(run.catalogue) in str(caught.value)


@pytest.mark.parametrize("candidates", ["7", '"hi"', "{}"])
def test_a_candidates_that_is_not_an_array_is_refused(tmp_path, candidates):
    """A string `candidates` passed the old guards by coincidence.

    `"candidate_id" not in "abc"` is a substring test that answers True, so a
    string reached planning with the right exit code for the wrong reason. A
    number raised TypeError out of `enumerate`. Neither was checked.
    """
    run = _toy_run(tmp_path)
    catalogue = read_json(run.catalogue)
    catalogue["candidates"] = json.loads(candidates)
    write_json(run.catalogue, catalogue)
    with pytest.raises(UsageError):
        slices.write_slices(run, cap=2500)


def test_a_candidate_that_is_not_an_object_is_refused(tmp_path):
    run = _toy_run(tmp_path)
    catalogue = read_json(run.catalogue)
    catalogue["candidates"] = [catalogue["candidates"][0], 7]
    write_json(run.catalogue, catalogue)
    with pytest.raises(UsageError) as caught:
        slices.write_slices(run, cap=2500)
    # The index, because a catalogue of 351 candidates is not one an operator
    # reads end to end looking for the broken row.
    assert "1" in str(caught.value)


def test_a_candidate_id_that_is_present_but_not_a_string_is_refused(tmp_path):
    """Presence was not enough, and the defect hid on the one-candidate case.

    A single non-string id sorts alone and passed; two ids of different types
    raise TypeError comparing them. So the old guard was measurably fine on a
    one-row catalogue and fatal on any realistic one -- `_top_key` and
    `_group_key` both read the id bare and both sort on it, which makes a
    string id a precondition of planning rather than a tidiness check.
    """
    run = _toy_run(tmp_path)
    catalogue = read_json(run.catalogue)
    catalogue["candidates"][0]["candidate_id"] = 7
    write_json(run.catalogue, catalogue)
    with pytest.raises(UsageError):
        slices.write_slices(run, cap=2500)


def _excl(reason, *, path_len=20):
    """One catalogue exclusion, padded to a known byte cost."""
    return {"path": "/corpus/" + "p" * path_len, "reason": reason}


def test_the_tally_counts_every_exclusion_including_ones_whose_paths_are_dropped():
    """`total` and `by_reason` describe the whole array, not the kept subset.

    The tally is the only thing a human at gate 0 has to tell "the corpus had
    123 binaries" from "the corpus had none", and `binary` is precisely a
    reason whose paths this function drops. A tally computed over `entries`
    would report zero binaries for a corpus full of them.
    """
    summary = slices.excluded_summary(
        [_excl("binary") for _ in range(123)] + [_excl("duplicate") for _ in range(11)]
    )
    assert summary["total"] == 134
    assert summary["by_reason"] == {"binary": 123, "duplicate": 11}
    assert len(summary["entries"]) == 11
    assert {e["reason"] for e in summary["entries"]} == {"duplicate"}


def test_only_reasons_carrying_a_judgment_keep_their_paths():
    """The four disputable reasons keep paths; the four mechanical ones do not.

    Asserted as set equality over both halves rather than "duplicate is kept",
    so adding a ninth exclusion_reason without ruling on which side it falls
    fails here instead of silently defaulting to dropped.
    """
    every = [
        "duplicate",
        "operator_excluded",
        "unreadable",
        "vendored",
        "gitignored",
        "vcs_metadata",
        "binary",
        "lockfile",
    ]
    summary = slices.excluded_summary([_excl(r) for r in every])
    assert summary["total"] == 8
    assert {e["reason"] for e in summary["entries"]} == set(slices.DISPUTABLE_EXCLUSION_REASONS)
    assert set(slices.DISPUTABLE_EXCLUSION_REASONS) == {
        "duplicate",
        "operator_excluded",
        "unreadable",
        "vendored",
    }


def test_by_reason_is_sorted_so_two_runs_produce_one_byte_shape():
    """Insertion order must not reach the document: the plan is byte-compared."""
    summary = slices.excluded_summary(
        [_excl("vendored"), _excl("binary"), _excl("duplicate"), _excl("binary")]
    )
    assert list(summary["by_reason"]) == ["binary", "duplicate", "vendored"]


def test_an_empty_exclusion_list_produces_the_zero_shape_not_absent_keys():
    """Every key is present at zero, because the toy fixture excludes nothing.

    `tests/fixtures/toy/` surveys to `excluded: []`, so this is the shape every
    toy-based test in the suite sees. Absent keys here would make the schema's
    `required` list unsatisfiable on the fixture the whole suite is built on.
    """
    assert slices.excluded_summary([]) == {
        "total": 0,
        "by_reason": {},
        "entries": [],
        "entries_truncated": False,
    }


def test_the_entry_block_is_bounded_by_bytes_and_says_so_when_it_bit():
    """The budget stops filling before it is exceeded, and records that it did.

    A count cap is what remains open under the uncapped digest names
    (docs/design/findings.md): `digest`'s `names` is capped at 64 entries and
    unbounded in characters, so a verbose value makes `survey` exit 2 on a row
    that used to be small. Paths vary in length far more than
    tool names do, so this block is bounded in bytes.
    """
    many = [_excl("duplicate", path_len=400) for _ in range(40)]
    summary = slices.excluded_summary(many)

    assert summary["entries_truncated"] is True
    assert summary["total"] == 40, "the tally still describes all forty"
    assert summary["by_reason"] == {"duplicate": 40}
    kept = summary["entries"]
    assert 0 < len(kept) < 40
    # The invariant is "the longest prefix that fits", so the block is under
    # the budget and one more entry would have broken it.
    assert len(canonical_bytes(kept)) <= slices.MAX_EXCLUDED_ENTRY_BYTES
    assert len(canonical_bytes([*kept, many[len(kept)]])) > slices.MAX_EXCLUDED_ENTRY_BYTES


def test_truncation_stops_filling_rather_than_skipping_to_smaller_entries():
    """Once the budget bites the block ends, even if a later entry would fit.

    Fill-what-fits would make the kept set depend on the size of entries the
    operator never sees, so two corpora differing only in one long path would
    produce entry lists that are not prefixes of each other. A prefix is
    explainable at gate 0; a subset chosen by size is not.
    """
    entries = [_excl("duplicate", path_len=9000), _excl("duplicate", path_len=10)]
    summary = slices.excluded_summary(entries)
    assert summary["entries"] == [], "the first entry alone exceeds the budget"
    assert summary["entries_truncated"] is True


def test_a_malformed_exclusion_entry_does_not_raise():
    """`excluded` is schema-required to hold objects, but this runs before validate.

    `write_slices` is reached with whatever is on disk. A non-object entry
    counts toward `total` -- it is an exclusion the catalogue records -- and
    contributes no reason, rather than crashing a code stage into the exit 2
    that means "no retry can help".
    """
    summary = slices.excluded_summary(["nonsense", 7, None, _excl("duplicate")])
    assert summary["total"] == 4
    assert summary["by_reason"] == {"duplicate": 1}
    assert len(summary["entries"]) == 1


def test_truncation_keeps_the_prefix_before_the_oversized_entry_not_what_fits_after():
    """The prefix invariant, measured where truncation does *not* bite at index 0.

    The sibling case above proves it only for a first entry that alone busts
    the budget, where "the prefix that fit" and "the empty list" are the same
    list. Here three short entries fit, a 9KB one cannot, and three more short
    ones would -- so a fill-what-fits implementation is distinguishable from a
    prefix one by exactly the last assertion.
    """
    early = [{"path": f"/corpus/early-{i}.json", "reason": "duplicate"} for i in range(3)]
    oversized = [{"path": "/corpus/" + "p" * 9000, "reason": "duplicate"}]
    late = [{"path": f"/corpus/late-{i}.json", "reason": "duplicate"} for i in range(3)]
    summary = slices.excluded_summary([*early, *oversized, *late])

    assert summary["entries"] == early, "the leading run that fit, and nothing past it"
    assert summary["entries_truncated"] is True
    assert summary["total"] == 7, "the tally still describes all seven"
    # The discriminating assertion: each of these three fits inside what the
    # oversized entry left unspent, so fill-what-fits would have picked them up.
    assert not any("late-" in entry["path"] for entry in summary["entries"])


def test_candidate_bytes_indexes_every_candidate_by_its_own_source_size():
    """The map is source `bytes`, never `row_bytes`, and covers inadmissible rows.

    Source size is the metric `weight.bytes` needs: digest.py clamps a skeleton
    at 128 nodes, so a 2.7MB file and a 20KB one serialize to nearly the same
    row once both are past the cap, and a metric that saturates cannot say
    which of two surfaces carries more evidence. Inadmissible candidates are
    included because plan_slices partitions every candidate and a surface's
    evidence may name any of them.
    """
    rows = [_cand("c1", pad=1000), _cand("c2", pad=2000) | {"admissible": False}]
    index = slices.candidate_bytes_index(rows)
    assert index == {"c1": 1000, "c2": 2000}
    assert index["c2"] != slices.row_bytes(rows[1]), "source bytes, not serialized row bytes"


def test_catalogue_facts_carries_exactly_four_fields():
    """Pinned as set equality: a fifth field is a schema change, not a detail.

    `additionalProperties: false` would reject an unknown key at layer 1, but
    this asserts the *producer* stays in shape, so a field added here without
    the schema fails in this file rather than in every validate call.
    """
    catalogue = {
        "run_id": "run-20260825-120000",
        "request": {"objective": "breadth"},
        "policy": {"max_candidates": 500},
        "excluded": [],
        "candidates": [_cand("c1", pad=11)],
    }
    facts = slices.catalogue_facts(catalogue)
    assert set(facts) == {"request", "policy", "excluded", "candidate_bytes"}
    assert facts["request"] == {"objective": "breadth"}, "verbatim, not reshaped"
    assert facts["policy"] == {"max_candidates": 500}, "verbatim, not reshaped"
    assert facts["candidate_bytes"] == {"c1": 11}
    assert facts["excluded"]["total"] == 0


def test_the_written_plan_carries_catalogue_facts_agreeing_with_the_catalogue(tmp_path):
    """The whole point, end to end on the real fixture."""
    run = _toy_run(tmp_path)
    slices.write_slices(run, cap=2500)

    catalogue = read_json(run.catalogue)
    facts = read_json(run.slices)["catalogue_facts"]

    assert facts["request"] == catalogue["request"]
    assert facts["policy"] == catalogue["policy"]
    assert facts["candidate_bytes"] == {
        c["candidate_id"]: c["bytes"] for c in catalogue["candidates"]
    }
    assert facts["excluded"] == {
        "total": 0,
        "by_reason": {},
        "entries": [],
        "entries_truncated": False,
    }


def test_catalogue_facts_sorts_ahead_of_the_slices_array_on_disk(tmp_path):
    """The head lands in the first bytes, which is the seek the untriageable
    catalogue records.

    canonical_bytes sorts keys, so `catalogue_facts` and `run_id` both precede
    `slices`. On the 472,799-byte tau2 catalogue `run_id` sat at byte 470,054
    and a dispatch had to seek the whole file for it; this asserts the plan
    does not repeat that. Asserted on byte offsets rather than on key order,
    because a reader pays for offsets.
    """
    run = _toy_run(tmp_path)
    slices.write_slices(run, cap=2500)
    text = run.slices.read_text(encoding="utf-8")
    assert text.index('"catalogue_facts"') < text.index('"slices"')
    assert text.index('"run_id"') < text.index('"slices"')


def test_a_catalogue_with_no_excluded_field_is_refused_at_exit_two(tmp_path):
    """`excluded` joins the three fields write_slices reads bare.

    It is `required` in catalogue-0.1.json, so its absence is a broken
    catalogue rather than a shape this stage should tolerate. UsageError, so
    cli.py maps it to exit 2: no retry of triage-slices can fix a catalogue.
    The message must name the catalogue, because that is where the operator
    looks next -- naming this stage would send them to the wrong file.
    """
    run = _toy_run(tmp_path)
    catalogue = read_json(run.catalogue)
    del catalogue["excluded"]
    write_json(run.catalogue, catalogue)
    with pytest.raises(UsageError) as caught:
        slices.write_slices(run, cap=2500)
    assert str(run.catalogue) in str(caught.value)
    assert "excluded" in str(caught.value)


@pytest.mark.parametrize("excluded", ["7", "null", '"hi"', "{}"])
def test_an_excluded_that_is_not_an_array_is_refused(tmp_path, excluded):
    """Present but of the wrong container shape, guarded the way `candidates` is.

    Two of these raise and two do not, and both halves are wrong in their own
    way. `7` and `null` raise TypeError out of `excluded_summary`'s `len()` --
    from a *code* stage, so cli.py's catch-all reports it as exit 1 with an
    `[internal]` finding naming the run root: a stage defect where a malformed
    catalogue belongs, against the wrong artifact, two rules of the exit-code
    contract at once. `"hi"` and `{}` do not raise, which is worse: both
    iterate to zero well-formed entries, so the plan would carry a plausible
    and wrong summary with nothing on disk to say so.
    """
    run = _toy_run(tmp_path)
    catalogue = read_json(run.catalogue)
    catalogue["excluded"] = json.loads(excluded)
    write_json(run.catalogue, catalogue)
    with pytest.raises(UsageError) as caught:
        slices.write_slices(run, cap=2500)
    assert str(run.catalogue) in str(caught.value)
    assert "excluded" in str(caught.value)


def test_a_populated_exclusion_list_reaches_the_plan_summarised(tmp_path):
    """The toy fixture excludes nothing, so the populated path needs injecting."""
    run = _toy_run(tmp_path)
    catalogue = read_json(run.catalogue)
    catalogue["excluded"] = [
        {"path": "/corpus/a.png", "reason": "binary"},
        {"path": "/corpus/b.png", "reason": "binary"},
        {"path": "/corpus/c.json", "reason": "duplicate"},
    ]
    write_json(run.catalogue, catalogue)
    slices.write_slices(run, cap=2500)

    excluded = read_json(run.slices)["catalogue_facts"]["excluded"]
    assert excluded["total"] == 3
    assert excluded["by_reason"] == {"binary": 2, "duplicate": 1}
    assert [e["path"] for e in excluded["entries"]] == ["/corpus/c.json"]
    assert excluded["entries_truncated"] is False


def test_the_plan_still_validates_against_its_schema(tmp_path):
    """Layer 1, on the real writer's output rather than on a builder."""
    run = _toy_run(tmp_path)
    slices.write_slices(run, cap=2500)
    assert validate.validate_stage(run, "triage-slices") == []


def test_adding_catalogue_facts_left_the_partition_byte_identical(tmp_path):
    """`slices[]` and every shard are untouched by this change.

    The spec's global constraint: nothing here touches plan_slices. Compared
    against plan_slices' own output rather than a recorded fixture, so the
    assertion cannot rot into agreeing with a regression.
    """
    run = _toy_run(tmp_path)
    _, plan = slices.write_slices(run, cap=2500)
    document = read_json(run.slices)
    expected = slices.plan_slices(read_json(run.catalogue)["candidates"], cap=2500)

    assert [s["id"] for s in document["slices"]] == [s.id for s in expected]
    assert [s["candidate_ids"] for s in document["slices"]] == [
        list(s.candidate_ids) for s in expected
    ]
    assert [s.id for s in plan] == [s.id for s in expected]
