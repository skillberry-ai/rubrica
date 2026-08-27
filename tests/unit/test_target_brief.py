"""target-brief: the run's understanding of the target, addressed to its owners.

Every assertion here names a real toy claim id. `clm-api-001` carries evidence
with no `quote` and `clm-api-007` carries one, which is what makes the
quote-absent and quote-present paths two different tests rather than one.
"""

from __future__ import annotations

import json
import os

import pytest

from rubrica import target_brief
from rubrica.summary import Absent, Malformed
from tests.toy import build_toy_run


def test_source_index_resolves_a_claim_to_path_locator_and_kind(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    index = target_brief.source_index(run)
    ref = index["clm-api-001"]
    # The shared prefix is stripped: the toy corpus lives under
    # tests/fixtures/toy, and an owner recognises "api.json", never the absolute
    # path of the machine rubrica happened to run on.
    assert ref.path == "api.json"
    assert ref.kind == "mcp_tool_schema"
    assert ref.locator.startswith("#/tools/")


def test_source_index_reports_a_missing_quote_as_empty_never_as_invented_text(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    index = target_brief.source_index(run)
    assert index["clm-api-001"].quote == ""
    assert index["clm-api-007"].quote == '"required": ["action"]'


def test_source_index_prefers_the_evidence_record_that_carries_a_quote(tmp_path):
    """Measured: executive-agent quotes only 67 of the 126 claims its world model
    cites, so taking evidence[0] blindly drops quotes the run does have."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    path = run.claims_dir / "api-json.json"
    payload = json.loads(path.read_text())
    payload["claims"][0]["evidence"] = [
        {"artifact_id": "api-json", "locator": "#/first"},
        {"artifact_id": "api-json", "locator": "#/second", "quote": "the quoted line"},
    ]
    path.write_text(json.dumps(payload))
    ref = target_brief.source_index(run)[payload["claims"][0]["id"]]
    assert ref.quote == "the quoted line"
    assert ref.locator == "#/second"


def test_source_index_omits_a_claim_id_nothing_defines(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    index = target_brief.source_index(run)
    # The positive is the control, and without it this test asserts nothing: a
    # bare `not in` passes for any implementation that iterates over claims that
    # exist, an index of `{}` included, so the absence would be
    # indistinguishable from an index that resolved nothing at all.
    assert "clm-api-001" in index
    assert "clm-does-not-exist" not in index


def test_source_index_returns_a_marker_when_claims_cannot_be_read(tmp_path):
    """Never a silently empty dict. summary.py:725-770 rules that reporting empty
    on an unreadable 01-claims/ is the one reading a human at gate 1 must never be
    handed, and this page is mailed outside the project."""
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    os.chmod(run.claims_dir, 0o000)
    try:
        result = target_brief.source_index(run)
    finally:
        os.chmod(run.claims_dir, 0o755)
    assert isinstance(result, Malformed)
    # Equality, not a substring, matching the sibling convention at
    # test_summary.py:1722 -- it also pins the trailing slash, which is what
    # says a directory rather than a file could not be read.
    assert result.what == "01-claims/"


@pytest.mark.parametrize(
    "files, expected",
    [
        # More than one file: the directory they share.
        (["/a/b/one.py", "/a/b/two.py"], "/a/b"),
        # Exactly one: its directory, never the file itself. os.path.commonpath
        # of a single path returns that path, which would strip the filename.
        (["/a/b/only.py"], "/a/b"),
        # Nothing shared but the root: strip nothing, or every path renders bare.
        (["/one.py", "/two.py"], ""),
        # Mixed absolute and relative: commonpath raises ValueError, and a
        # half-trimmed path is worse than a full one.
        (["/abs/one.py", "rel/two.py"], ""),
        ([], ""),
        # Fragment-bearing paths sharing one container file. `intake.py:333`
        # builds a sliced input's source_path as `<container>#<json_pointer>`
        # and a JSON pointer starts with "/", so commonpath -- which is
        # component-aware -- walks into the fragment and answers
        # ".../trace.json#", a prefix `_shorten` then matches nothing against.
        # Measured: the absolute staging path shipped to the owner unstripped,
        # which is the one outcome this function exists to prevent.
        (["/a/b/trace.json#/41", "/a/b/trace.json#/42"], "/a/b"),
        # An empty source_path among real ones. `_input_sources` yields "" for a
        # record whose `source_path` is not a string, and an unfiltered "" makes
        # commonpath raise ValueError -- which the handler below turns into "no
        # prefix", silently disabling shortening for every path in the run.
        (["", "/a/b/one.py", "/a/b/two.py"], "/a/b"),
        # A fragment with no container: the base it partitions to is empty, so it
        # must be filtered *after* the partition. Filtering the raw string instead
        # lets "" into the set, commonpath raises, and shortening turns off for
        # every path in the run -- leaking the staging path this helper exists to
        # strip.
        (["#/0", "/a/b/one.py", "/a/b/two.py"], "/a/b"),
    ],
)
def test_common_prefix(files, expected):
    assert target_brief._common_prefix(files) == expected


def test_shorten_keeps_the_slice_fragment():
    """A `#/NN` fragment marks one slice of a sliced artifact. parsec's 71 trace
    inputs are 71 slices of one capture, so the fragment is the only thing
    distinguishing them and dropping it would collapse 71 records into one."""
    assert target_brief._shorten("/a/b/trace.json#/41", "/a/b") == "trace.json#/41"
    assert target_brief._shorten("/a/b/src/tool.py", "/a/b") == "src/tool.py"
    # A prefix that is not actually a parent leaves the path alone rather than
    # slicing characters off its front.
    assert target_brief._shorten("/other/tool.py", "/a/b") == "/other/tool.py"


def test_provenance_counts_distinct_files_and_kinds(tmp_path):
    """The discriminator that replaced the derivation badge. Measured: 13 of
    executive-agent's 37 operations rest on a design document alone, and 28 of
    parsec's 30 data shapes were seen in exactly one file."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    index = target_brief.source_index(run)
    # clm-api-001 is in api.json (mcp_tool_schema); clm-notes-002 in notes.md
    # (design_doc). Two files, two kinds.
    across = target_brief.provenance(["clm-api-001", "clm-notes-002"], index, frozenset())
    assert across.files == ("api.json", "notes.md")
    assert across.kinds == ("design_doc", "mcp_tool_schema")
    assert across.single_source is False
    # The three claims cap-find-tickets cites are all in api.json.
    within = target_brief.provenance(
        ["clm-api-001", "clm-api-007", "clm-api-008"], index, frozenset()
    )
    assert within.files == ("api.json",)
    assert within.single_source is True


def test_provenance_marks_an_element_a_contradiction_touches(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    index = target_brief.source_index(run)
    world_model = json.loads(run.world_model.read_text())
    disputed = target_brief.disputed_claim_ids(world_model)
    # The toy contradiction is con-missing-semantics, claim_a clm-notes-004
    # against claim_b clm-trace-002.
    assert disputed == {"clm-notes-004", "clm-trace-002"}
    assert target_brief.provenance(["clm-notes-004"], index, disputed).disputed is True
    assert target_brief.provenance(["clm-api-001"], index, disputed).disputed is False


def test_disputed_claim_ids_reads_a_side_written_as_a_string_or_a_list():
    """The schema requires each side to be a single id string, so the string branch
    is the conformant path and the list branch is tolerance for a hand-edit made
    after layer 1 passed. `_strings` is what reads the list, because it drops a
    non-string member rather than raising -- which is what the `{"claim_a": 7}`
    case below pins."""
    as_string = {"contradictions": [{"claim_a": "clm-one", "claim_b": "clm-two"}]}
    assert target_brief.disputed_claim_ids(as_string) == {"clm-one", "clm-two"}
    as_list = {"contradictions": [{"claim_a": ["clm-one", "clm-three"], "claim_b": ["clm-two"]}]}
    assert target_brief.disputed_claim_ids(as_list) == {"clm-one", "clm-two", "clm-three"}
    # Hand-edited shapes that must not raise and must not invent an id.
    assert target_brief.disputed_claim_ids({"contradictions": "nope"}) == frozenset()
    assert target_brief.disputed_claim_ids({"contradictions": [{"claim_a": 7}]}) == frozenset()
    assert target_brief.disputed_claim_ids({}) == frozenset()


def test_provenance_of_an_unresolvable_id_names_no_file_but_still_reports_disputed():
    """Provenance is arithmetic over what resolved; dispute is a property of the id
    itself. An element whose claims are all unresolvable must not silently lose its
    disputed marker as well as its files."""
    result = target_brief.provenance(["clm-ghost"], {}, frozenset({"clm-ghost"}))
    assert result.files == ()
    assert result.kinds == ()
    # Zero files is not one file: `single_source` reads off `files`, and an
    # element with nothing behind it must not badge as resting on a single source.
    assert result.single_source is False
    assert result.disputed is True


def test_provenance_ignores_non_string_members_of_a_claims_array(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    index = target_brief.source_index(run)
    assert target_brief.provenance([7, None, {}], index, frozenset()).files == ()
    # The positive control, and without it this test asserts nothing: an
    # implementation returning no files for any input at all satisfies the
    # absence above. The string member has to survive the same filter that drops
    # its three neighbours -- which is also what says the filter is a type test
    # rather than a length test on the array.
    mixed = target_brief.provenance([7, "clm-api-001", None, {}], index, frozenset())
    assert mixed.files == ("api.json",)


def test_disputed_claim_ids_tolerates_a_world_model_that_is_not_an_object():
    """A report never raises on readable content, and a world model is hand-edited
    at a human gate -- which is exactly when a non-object appears. Bare `.get`
    raised AttributeError on both shapes below, measured.

    The truthy string is the case `brief._mapping`'s docstring records as measured
    at gates 0, 1 and 2; `[]` is here as well because bare `.get` raises on a
    non-object whether it is truthy or falsy, and the `x or {}` idiom `_mapping`
    replaced would have masked exactly the falsy half.
    """
    assert target_brief.disputed_claim_ids([]) == frozenset()
    assert target_brief.disputed_claim_ids("nope-a-truthy-string") == frozenset()
    # The positive control: an object still reads, so the guard above cannot be a
    # blanket "return nothing" that would hide every real contradiction too.
    readable = {"contradictions": [{"claim_a": "clm-one", "claim_b": "clm-two"}]}
    assert target_brief.disputed_claim_ids(readable) == {"clm-one", "clm-two"}


def test_provenance_counts_two_slices_of_one_file_as_two_sources():
    """A ruling, not an accident. `intake.py:333` writes a sliced input's
    source_path as `<container>#<json_pointer>`, so two slices of one capture reach
    `files` as two entries and the element is not single-source. That is what "how
    many sources back this" asks: parsec's 71 trace inputs are 71 slices of one
    capture and 71 independent observations of the target, and collapsing them
    would tell an owner that 71 recorded interactions are one piece of evidence.

    A synthetic index because the toy run has no sliced input -- `tests/toy.py`'s
    `#/...` strings are evidence *locators*, not source_path fragments -- so
    without this the whole fragment behaviour is fixture-cannot-reach.
    """
    index = {
        "clm-one": target_brief.SourceRef(
            claim_id="clm-one", path="trace.json#/12", locator="#/0", quote="", kind="trace"
        ),
        "clm-two": target_brief.SourceRef(
            claim_id="clm-two", path="trace.json#/41", locator="#/0", quote="", kind="trace"
        ),
    }
    result = target_brief.provenance(["clm-one", "clm-two"], index, frozenset())
    assert result.files == ("trace.json#/12", "trace.json#/41")
    # One kind, because both slices are the same kind of file. The two counts are
    # independent, and this is the case that says so.
    assert result.kinds == ("trace",)
    assert result.single_source is False


def test_inputs_read_groups_by_kind_and_directory(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    groups = target_brief.inputs_read(run)
    # The toy corpus is three files of three kinds, all directly under the shared
    # prefix, so each is its own group and no directory qualifies any of them.
    assert [(g.kind, g.directory, g.files, g.slices) for g in groups] == [
        ("design_doc", "", ("notes.md",), 0),
        ("mcp_tool_schema", "", ("api.json",), 0),
        ("trace", "", ("trace.json",), 0),
    ]


def test_inputs_read_collapses_slices_of_one_file(tmp_path):
    """parsec's 71 trace inputs are 71 slices of one capture. Counting inputs
    would report 269 files where the run read 199, and would list one file 71
    times."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    manifest = json.loads(run.manifest.read_text())
    base = "/corpus/traces/capture.json"
    manifest["inputs"] = [
        {"artifact_id": "t-41", "kind": "trace", "source_path": f"{base}#/41"},
        {"artifact_id": "t-44", "kind": "trace", "source_path": f"{base}#/44"},
        {"artifact_id": "t-68", "kind": "trace", "source_path": f"{base}#/68"},
        {"artifact_id": "src", "kind": "source_code", "source_path": "/corpus/src/tool.py"},
    ]
    run.manifest.write_text(json.dumps(manifest))
    groups = {g.kind: g for g in target_brief.inputs_read(run)}
    # The directory is factored out of the names, so the rendered path is the two
    # joined: this group is keyed on (kind, directory) and repeating the directory
    # on every row of a 199-file listing is what the field exists to avoid. Both
    # halves are asserted, or the file name alone would leave the directory free
    # to be anything at all.
    assert (groups["trace"].directory, groups["trace"].files) == ("traces", ("capture.json",))
    assert groups["trace"].slices == 2  # three inputs, one file
    assert (groups["source_code"].directory, groups["source_code"].files) == (
        "src",
        ("tool.py",),
    )
    # Zero is the control for the 2 above: an implementation returning the input
    # count, or a constant, satisfies neither this line nor that one. The two
    # together are what say `slices` counts records collapsed away, not records.
    assert groups["source_code"].slices == 0


def test_inputs_read_names_the_artifact_when_the_manifest_records_no_path(tmp_path):
    """Names something the reader can chase. A blank row names nothing, and a
    constructed path would be a fabrication about the owner's tree."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    manifest = json.loads(run.manifest.read_text())
    manifest["inputs"] = [{"artifact_id": "orphan", "kind": "other"}]
    run.manifest.write_text(json.dumps(manifest))
    group = target_brief.inputs_read(run)[0]
    assert group.files == ("orphan",)
    # And no directory around it. A record with no `source_path` says nothing
    # about where the file sits, so anything here would be a sentence about the
    # owner's tree that no artifact supports.
    assert group.directory == ""


def test_inputs_read_marks_an_absent_manifest_absent_and_a_broken_one_malformed(tmp_path):
    """Two facts, not one. They were a single word until a run said on one page
    that a stage had produced an artifact and that the artifact was not present."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    # The control, before either fact is manufactured: a readable manifest yields
    # groups. Without it both assertions below pass for an implementation that
    # returns a marker for every run, which would put "we could not read what we
    # read" on a page sent to the owner of a run that is entirely healthy.
    assert isinstance(target_brief.inputs_read(run), list)
    run.manifest.write_text("{ not json")
    broken = target_brief.inputs_read(run)
    assert isinstance(broken, Malformed)
    assert broken.what == "manifest.json"
    run.manifest.unlink()
    assert isinstance(target_brief.inputs_read(run), Absent)


def test_disputes_renders_nature_verbatim_and_resolves_both_sides(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    recorded = json.loads(run.world_model.read_text())["contradictions"][0]
    found = target_brief.disputes(run)
    assert [d.id for d in found] == ["con-missing-semantics"]
    dispute = found[0]
    # Verbatim, compared against the artifact rather than a copied string, so the
    # assertion cannot rot into agreeing with a paraphrase.
    assert dispute.nature == recorded["nature"]
    assert dispute.resolution == "preferred_a"
    assert [r.claim_id for r in dispute.side_a] == ["clm-notes-004"]
    assert [r.claim_id for r in dispute.side_b] == ["clm-trace-002"]
    # Each side arrives as a file the owner can open, with the quoted line.
    assert dispute.side_a[0].path == "notes.md"
    assert dispute.side_a[0].quote.startswith("`get_ticket` with an id no ticket has")
    assert dispute.side_b[0].path == "trace.json"


def test_side_reads_a_list_of_ids_as_well_as_the_conformant_single_string():
    """Both branches of the shared `_side_ids` helper, reached through `_side`.

    The list branch is unreachable from the toy world model, whose sides are the
    conformant strings, so without this the tolerance `_side_ids` exists to
    provide is fixture-cannot-reach on this call path -- and the silent-drop
    failure its docstring records was measured on exactly this shape.
    """
    index = {
        "clm-one": target_brief.SourceRef("clm-one", "notes.md", "L1", "", "design_doc"),
        "clm-two": target_brief.SourceRef("clm-two", "src/tool.py", "L2", "", "source_code"),
    }
    assert [r.claim_id for r in target_brief._side("clm-one", index)] == ["clm-one"]
    assert [r.claim_id for r in target_brief._side(["clm-one", "clm-two"], index)] == [
        "clm-one",
        "clm-two",
    ]
    # An id nothing defines drops out, and the resolvable neighbour beside it is
    # the control: without it, an empty tuple would also satisfy an
    # implementation that resolves nothing at all.
    assert [r.claim_id for r in target_brief._side(["clm-ghost", "clm-two"], index)] == ["clm-two"]
    # Neither a non-string nor a hand-edited non-list invents a ref.
    assert target_brief._side(7, index) == ()
    assert target_brief._side(None, index) == ()


def test_taken_names_the_file_rather_than_inferring_the_kind():
    """ "We went with the code" needs a code-ness heuristic that fails on the mixed
    kinds measured -- reservation-service's capabilities span four at once. A file
    the owner can open needs no inference."""
    a = (target_brief.SourceRef("clm-a", "notes.md", "L1", "", "design_doc"),)
    b = (target_brief.SourceRef("clm-b", "src/tool.py", "L2", "", "source_code"),)
    assert target_brief._taken("preferred_a", a, b) == "We went with notes.md."
    assert target_brief._taken("preferred_b", a, b) == "We went with src/tool.py."
    assert target_brief._taken("both_possible", a, b) == "We are treating both as possible."
    # Unresolved carries no sentence: group B's whole point is that we could not
    # tell, and a sentence there would assert a decision nobody made.
    assert target_brief._taken("unresolved", a, b) == ""


def test_taken_says_so_when_the_chosen_side_resolves_to_nothing():
    """Never a bare "We went with ." -- the sentence states its own hole."""
    b = (target_brief.SourceRef("clm-b", "src/tool.py", "L2", "", "source_code"),)
    assert target_brief._taken("preferred_a", (), b) == (
        "We took one side, but could not resolve which file states it."
    )
    # The control for the hole above: the *other* resolution over the same two
    # sides names its file, so the sentence is chosen by which side was taken
    # rather than returned for every input that has an empty side anywhere.
    assert target_brief._taken("preferred_b", (), b) == "We went with src/tool.py."


def test_disputes_keeps_a_contradiction_whose_claims_do_not_resolve(tmp_path):
    """The nature prose is the payload; the sides are corroboration. Dropping the
    record because a citation dangles would hide a real disagreement, and a
    dangling citation is check-refs' finding rather than this page's."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["contradictions"][0]["claim_a"] = "clm-ghost"
    run.world_model.write_text(json.dumps(world_model))
    dispute = target_brief.disputes(run)[0]
    assert dispute.side_a == ()
    # The controls for that empty side, and what says it is one dangling id
    # rather than an index that resolved nothing at all: side_b runs through the
    # same `_side` against the same index and still arrives as a file.
    assert [r.claim_id for r in dispute.side_b] == ["clm-trace-002"]
    assert dispute.side_b[0].path == "trace.json"
    assert dispute.nature  # still there, still rendered
    assert dispute.taken == "We took one side, but could not resolve which file states it."


def test_disputes_orders_by_id_and_reports_an_unreadable_world_model(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    first = dict(world_model["contradictions"][0])
    world_model["contradictions"] = [
        {**first, "id": "con-zebra"},
        {**first, "id": "con-alpha"},
    ]
    run.world_model.write_text(json.dumps(world_model))
    assert [d.id for d in target_brief.disputes(run)] == ["con-alpha", "con-zebra"]
    run.world_model.write_text("{ not json")
    broken = target_brief.disputes(run)
    assert isinstance(broken, Malformed)
    # The artifact the marker names, not just that a marker came back: CLAUDE.md's
    # third exit-code rule is that a report must name the *right* artifact, and an
    # unreadable `01-claims/` reaches this same function through `source_index`.
    assert broken.what == "01-world-model.json"
    run.world_model.unlink()
    assert isinstance(target_brief.disputes(run), Absent)


def test_disputes_is_empty_rather_than_absent_when_the_target_has_none(tmp_path):
    """An empty list and a missing world model are different facts, and the
    renderer says different things about them."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    # The control, before the field is emptied: this run does record a
    # disagreement, so the `[]` below is the emptied field being read and not a
    # builder that finds nothing in any run at all.
    assert len(target_brief.disputes(run)) == 1
    world_model = json.loads(run.world_model.read_text())
    world_model["contradictions"] = []
    run.world_model.write_text(json.dumps(world_model))
    assert target_brief.disputes(run) == []
