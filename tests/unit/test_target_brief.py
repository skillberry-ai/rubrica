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
        # Fragment-bearing paths sharing one container file. `intake.py:334`
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
        # A whitespace-only source_path among real ones. `" "` is truthy, so the
        # truthiness filter let it through to commonpath, where it counts as a
        # *relative* path and raises against the absolute ones -- turning shortening
        # off for the whole run. Measured on a toy page: every row of `What we read`
        # and the disagreement's side line rendered the absolute staging path of the
        # machine rubrica ran on, which is the one outcome this function exists to
        # prevent.
        ([" ", "/a/b/one.py", "/a/b/two.py"], "/a/b"),
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


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        # The ordinary source path: no piece, and the file is the whole string.
        ("src/tool.py", ("src/tool.py", "")),
        # The slicer's own shape, `intake.py:334`'s `<container>#<json_pointer>`.
        ("capture.json#/41", ("capture.json", "#/41")),
        # A `#` the owner put in their own filename. Read as a piece, this named a
        # file we never read (`notes`) and a piece that does not exist (`#2.md`).
        ("notes#2.md", ("notes#2.md", "")),
        # A pointer with no container has no file to separate it from, so it stays
        # whole rather than being labelled a piece of nothing.
        ("#/0", ("#/0", "")),
        # Nothing nameable: `" "` is truthy, and it reached the page as a blank
        # `<span class="file">` and as `We went with  .`.
        (" ", ("", "")),
        ("", ("", "")),
        # A pointer whose container is nothing but whitespace: the same shape as the
        # fragment-only path above, one space further on, so it comes back whole for
        # the same reason. Split, it would hand the caller a blank filename and a
        # piece of it -- the pair of blanks the rule exists to stop.
        (" #/1", (" #/1", "")),
    ],
)
def test_file_and_piece(path, expected):
    """The one home for the sliced-path rule, which had two spellings and three
    call sites -- and the site with none shipped
    `We went with traces_parsec-agent-metrics_20260713_115226.json#/11.` on
    run-20260826-090456, naming a path the owner cannot open."""
    assert target_brief._file_and_piece(path) == expected


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
    """A ruling, not an accident. `intake.py:334` writes a sliced input's
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


def test_taken_names_the_file_a_slice_came_out_of_rather_than_the_slice(tmp_path):
    """The resolution line tells the owner which of *their* files we believed, so it
    has to name one they can open.

    Measured on run-20260826-090456 before the fix: 3 of its 25 resolution lines
    read `We went with traces_parsec-agent-metrics_20260713_115226.json#/11.` and
    the two nearby, while `_side_rows` two paragraphs above rendered the same source
    as `traces_....json (piece #/11)`. One page spelling one file two ways.

    Reached by pointing the *manifest* at a sliced `source_path` rather than by
    editing `tests/fixtures/toy/`: the golden world's one contradiction resolves
    `preferred_a` onto `notes.md`, an unsliced input, and CLAUDE.md treats an edit
    to that fixture as higher-risk than an edit to source.
    """
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    manifest = json.loads(run.manifest.read_text())
    # The control, taken before the mutation: the chosen side already names this
    # file, so what the mutation changes is the *shape of the path* and not which
    # side won.
    assert target_brief.disputes(run)[0].taken == "We went with notes.md."
    for record in manifest["inputs"]:
        if record["artifact_id"] == "notes-md":
            record["source_path"] = record["source_path"] + "#/11"
    run.manifest.write_text(json.dumps(manifest))
    dispute = target_brief.disputes(run)[0]
    assert dispute.taken == "We went with notes.md."
    # And the piece is not lost on the way: `SourceRef.path` still carries it, which
    # is what `_side_rows` labels and what tells 71 slices of one capture apart. The
    # sentence drops it; the record does not.
    assert [ref.path for ref in dispute.side_a] == ["notes.md#/11"]


def test_taken_says_it_could_not_name_the_file_rather_than_going_with_nothing(tmp_path):
    """`We went with  .` -- measured on a hand-edited world model, and the sentence
    that already covers it says we took a side and could not resolve which file
    states it. Reachable only by hand-editing, because `SourceRef.path` falls back
    to the artifact id when the manifest registers no path at all."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    manifest = json.loads(run.manifest.read_text())
    # The control: with the path readable the sentence names the file, so the
    # sentence below is this shape's and not one returned for every run.
    assert target_brief.disputes(run)[0].taken == "We went with notes.md."
    for record in manifest["inputs"]:
        if record["artifact_id"] == "notes-md":
            record["source_path"] = "   "
    run.manifest.write_text(json.dumps(manifest))
    assert target_brief.disputes(run)[0].taken == (
        "We took one side, but could not resolve which file states it."
    )


def test_side_drops_a_duplicate_id_the_way_taken_does(tmp_path):
    """A hand-edited `"claim_a": ["clm-notes-004", "clm-notes-004"]` rendered the
    same file quoting the same line twice under one side -- measured. The argument
    is less the duplicate than that `_side` and `_taken`, one function apart, read
    one list two ways."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["contradictions"][0]["claim_a"] = ["clm-notes-004", "clm-notes-004"]
    run.world_model.write_text(json.dumps(world_model))
    assert [ref.claim_id for ref in target_brief.disputes(run)[0].side_a] == ["clm-notes-004"]
    # The control: two *distinct* ids on one side both survive, so the line above is
    # a duplicate collapsing and not a side truncated to its first ref.
    world_model["contradictions"][0]["claim_a"] = ["clm-notes-004", "clm-api-001"]
    run.world_model.write_text(json.dumps(world_model))
    assert [ref.claim_id for ref in target_brief.disputes(run)[0].side_a] == [
        "clm-api-001",
        "clm-notes-004",
    ]


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


def test_open_questions_carries_unknown_verbatim_and_drops_the_internals(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["gaps"] = [
        {
            "id": "gap-002",
            "subject": "get_ticket",
            "unknown": "What get_ticket returns for an unknown ticket_id",
            # Fused owner-facing and internal prose, which is why the field is
            # dropped rather than selected or rewritten.
            "why_it_matters": "a scenario built on the empty outcome class has no "
            "stated ground truth, so score cannot rank it",
            "blocks": ["propose", "score"],
        },
        {
            "id": "gap-001",
            "subject": "rate limits",
            "unknown": "Whether the API rate-limits and with what response",
            "why_it_matters": "instantiate cannot seed a limit it cannot name",
            "blocks": ["instantiate"],
        },
    ]
    run.world_model.write_text(json.dumps(world_model))
    found = target_brief.open_questions(run)
    assert [q.id for q in found] == ["gap-001", "gap-002"]
    assert found[1].unknown == "What get_ticket returns for an unknown ticket_id"
    assert found[1].subject == "get_ticket"
    # Two assertions, because they catch different things and the first alone was
    # measured to overstate its reach. The prose loop reads every field of the
    # record, but the strings it hunts are values *this fixture* carries, so it
    # only proves that no internal field the schema has today reaches an
    # attribute. The set equality is what closes the general case: any fourth
    # field arriving on the record fails it, whether or not the fixture happens
    # to populate the field it came from. It also subsumes the two `hasattr`
    # checks it replaced.
    rendered = " ".join(str(v) for q in found for v in vars(q).values())
    for leaked in ("propose", "score", "instantiate", "outcome class", "ground truth"):
        assert leaked not in rendered
    assert set(vars(found[0])) == {"id", "subject", "unknown"}


def test_open_questions_is_empty_on_the_toy_world_and_marks_an_unreadable_one(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    # The golden toy world has no gaps; an empty group and a missing world model
    # are different facts and the renderer says different things about them.
    assert target_brief.open_questions(run) == []
    run.world_model.write_text("{ not json")
    assert isinstance(target_brief.open_questions(run), Malformed)
    run.world_model.unlink()
    assert isinstance(target_brief.open_questions(run), Absent)


def test_operations_reads_handle_sentence_params_and_labelled_outcomes(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    found = {op.id: op for op in target_brief.operations(run)}
    op = found["cap-find-tickets"]
    assert op.handle == "query_tickets"  # binding.tool
    assert op.sentence == "query_tickets.find_tickets"
    assert op.params == ("queue (string, optional)", "status (string, optional)")
    # Labels are owner-facing, and only the kinds actually present appear. The toy
    # world records success and empty; parsec records all five.
    assert [(o.label, o.description) for o in op.outcomes] == [
        ("On success", "one or more tickets match the filters"),
        ("When there is nothing to return", "no ticket matches the filters"),
    ]
    # Provenance is the capability's own claims, all three in api.json.
    assert op.provenance.files == ("api.json",)
    assert op.provenance.single_source is True
    assert found["cap-get-ticket"].params == ("ticket_id (integer, required)",)


def test_operations_takes_provenance_from_the_capability_when_an_outcome_cites_nothing(
    tmp_path,
):
    """The parsec run fails layer 1 with 195 findings of `'claims' is a required
    property` on outcome classes -- the parked "recordings predate the requirement"
    ruling. Capability-level claims are present on 39 of 39, so provenance reads
    those."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    for capability in world_model["capabilities"]:
        for outcome in capability["outcome_classes"]:
            outcome.pop("claims", None)
    run.world_model.write_text(json.dumps(world_model))
    op = target_brief.operations(run)[0]
    assert op.provenance.files == ("api.json",)
    # Both label/description pairs rather than a bare `assert op.outcomes`: a
    # non-empty tuple is truthy whatever it holds, so the bare form can only fail
    # by the rows disappearing entirely and says nothing about whether the labels
    # and the prose survived losing `claims`. This form fails on a lost row and on
    # a blanked description alike.
    assert [(o.label, o.description) for o in op.outcomes] == [
        ("On success", "one or more tickets match the filters"),
        ("When there is nothing to return", "no ticket matches the filters"),
    ]
    # Set equality rather than `not hasattr(..., "provenance")`, plus the sibling
    # assertion beside it: an outcome carries exactly two fields, and the operation
    # over it does carry `provenance`. The `hasattr` alone would still pass if
    # `Outcome` grew three unrelated fields, and would also pass if provenance
    # moved off `Operation` too -- an absence with no positive control asserts
    # nothing, which is this repo's named recurring failure.
    assert set(vars(op.outcomes[0])) == {"label", "description"}
    assert "provenance" in vars(op)


def test_operations_falls_back_to_the_operation_string_when_there_is_no_binding(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["capabilities"][0].pop("binding")
    run.world_model.write_text(json.dumps(world_model))
    assert target_brief.operations(run)[0].handle == "query_tickets.find_tickets"


def test_operations_keeps_an_outcome_whose_kind_is_not_in_the_enum(tmp_path):
    """A label we do not have is not a reason to drop an outcome: the description
    is the payload. The kind itself is shown so the row is not mislabelled."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["capabilities"][0]["outcome_classes"][0]["kind"] = "invented"
    run.world_model.write_text(json.dumps(world_model))
    assert target_brief.operations(run)[0].outcomes[0].label == "invented"


def test_data_types_reads_fields_relations_and_rules(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    found = {d.id: d for d in target_brief.data_types(run)}
    ticket = found["ent-ticket"]
    assert ticket.name == "Ticket"
    assert ticket.collection == "tickets"
    assert ticket.fields[0] == target_brief.Field("ticket_id", "integer")
    assert len(ticket.fields) == 5
    # The relation names the target entity, resolved. `ent-comment` is an id no
    # owner recognises; "Comment" is a word from their own vocabulary.
    assert ticket.relations == ("comments → Comment (many)",)
    # The toy invariants carry `statement` and no `prose`, so the fallback is the
    # measured-normal path rather than the edge case.
    assert "comment_count is the number of comments on the ticket" in ticket.rules


def test_data_types_prefers_invariant_prose_over_statement_when_present(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["entities"][0]["invariants"][0]["prose"] = "Every comment is counted once."
    run.world_model.write_text(json.dumps(world_model))
    rules = target_brief.data_types(run)[0].rules
    assert "Every comment is counted once." in rules
    assert not any("comment_count is the number" in r for r in rules)


def test_data_types_names_an_unresolvable_relation_target_by_its_id(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["entities"][0]["relations"][0]["target_entity_id"] = "ent-ghost"
    run.world_model.write_text(json.dumps(world_model))
    assert target_brief.data_types(run)[0].relations == ("comments → ent-ghost (many)",)


def test_personas_pair_each_actor_with_its_goals(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    found = target_brief.personas(run)
    assert [p.name for p in found] == ["Support engineer"]
    assert found[0].goals == (
        "Locate the ticket that needs action, or establish that it does not exist",
        "Explain why a ticket is stuck",
    )
    assert found[0].provenance.files == ("notes.md",)


def test_personas_keeps_a_goal_no_actor_claims(tmp_path):
    """A goal whose actor_id resolves to nothing must not vanish: it is something
    the run believes about the target, and dropping it silently would make the
    description quietly incomplete."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["goals"][0]["actor_id"] = "act-ghost"
    run.world_model.write_text(json.dumps(world_model))
    found = target_brief.personas(run)
    # Not a substring over every goal joined into one string: that substring is
    # present in the un-mutated world too, so the joined form passes whether or not
    # the bucket was built -- satisfiable by content the mutation never touched,
    # which is this repo's named recurring failure. The bucket is asserted as its
    # own persona holding exactly the orphaned goal.
    assert [p.id for p in found] == ["act-support", ""]
    assert found[1].name == "Goals we could not attribute to a user"
    assert found[1].goals == (
        "Locate the ticket that needs action, or establish that it does not exist",
    )
    # The positive control: the actor is still rendered, with the goal it still
    # claims. So neither assertion above can pass by every goal collapsing into the
    # bucket, nor by the actor row vanishing along with its goal.
    assert found[0].goals == ("Explain why a ticket is stuck",)


@pytest.mark.parametrize("builder", ["operations", "data_types", "personas"])
def test_tier_two_builders_mark_an_unreadable_world_model(tmp_path, builder):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    run.world_model.write_text("{ not json")
    assert isinstance(getattr(target_brief, builder)(run), Malformed)
    run.world_model.unlink()
    assert isinstance(getattr(target_brief, builder)(run), Absent)


def test_relations_never_borrow_a_name_from_an_entity_with_no_readable_id(tmp_path):
    """Both halves of the `names` key are guarded, not just the name.

    Keyed on an unreadable id, the lookup holds `"" -> "Ticket"`, and a relation
    with no `target_entity_id` then renders as pointing at Ticket -- a relation this
    run never read, in a document whose owner is asked whether it is true.
    """
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["entities"] = [
        # No `id`, so it must contribute no name to resolve against.
        {"name": "Ticket", "collection": "tickets", "claims": ["clm-api-001"]},
        {
            "id": "ent-comment",
            "name": "Comment",
            "collection": "comments",
            "claims": ["clm-api-001"],
            "relations": [
                # No `target_entity_id`: this must not resolve to Ticket.
                {"name": "orphan", "cardinality": "one"},
                # The positive control, same shape and same test: a readable id
                # still resolves to its own entity's name, so the assertion below
                # cannot pass by relation resolution being broken outright.
                {"name": "sibling", "target_entity_id": "ent-comment", "cardinality": "many"},
            ],
        },
    ]
    run.world_model.write_text(json.dumps(world_model))
    found = target_brief.data_types(run)
    assert found[1].relations == ("orphan →  (one)", "sibling → Comment (many)")


def test_relations_drop_a_record_with_neither_name_nor_target_but_keep_a_nameless_one(tmp_path):
    """The asymmetry with `_params` is deliberate, and both halves are asserted.

    A relation with no `name` is kept because its payload is the target; a record
    with neither would render as bare punctuation and is dropped.
    """
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["entities"] = [
        {"id": "ent-ticket", "name": "Ticket", "collection": "tickets", "claims": ["clm-api-001"]},
        {
            "id": "ent-comment",
            "name": "Comment",
            "collection": "comments",
            "claims": ["clm-api-001"],
            "relations": [
                {"cardinality": "many"},
                {"target_entity_id": "ent-ticket", "cardinality": "one"},
            ],
        },
    ]
    run.world_model.write_text(json.dumps(world_model))
    # Dropped: the first record names nothing at all. Kept: the second still says
    # these records point at Ticket, which is a statement an owner can correct.
    assert target_brief.data_types(run)[1].relations == (" → Ticket (one)",)


def test_rules_prefer_a_readable_statement_over_a_whitespace_only_prose(tmp_path):
    """The schema's `minLength: 1` admits `" "`, and an unstripped one-space `prose`
    is truthy -- it would shadow a `statement` the run could read."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["entities"][0]["invariants"] = [
        {"id": "inv-001", "statement": "ticket_id is unique", "prose": " "},
        # The positive control: a real `prose` still wins over its `statement`, so
        # the assertion cannot pass by `prose` being ignored everywhere.
        {"id": "inv-002", "statement": "machine phrasing", "prose": "the human phrasing"},
    ]
    run.world_model.write_text(json.dumps(world_model))
    assert target_brief.data_types(run)[0].rules == ("ticket_id is unique", "the human phrasing")


def test_headline_reads_name_interface_and_notes(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    head = target_brief.headline(run)
    assert head.name == "ticketq"
    assert head.interface == "mcp"
    assert head.notes == ""  # the toy target carries none, and neither does parsec


def test_headline_keeps_notes_where_a_pass_wrote_them(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["target"]["notes"] = "A ticket queue behind MCP."
    run.world_model.write_text(json.dumps(world_model))
    assert target_brief.headline(run).notes == "A ticket queue behind MCP."


def test_headline_marks_a_missing_world_model(tmp_path):
    run = build_toy_run(tmp_path, upto="extract")
    assert isinstance(target_brief.headline(run), Absent)


def test_inputs_read_keeps_a_hash_that_belongs_to_the_filename(tmp_path):
    """Only a JSON pointer is the slicer's fragment. `intake.py:334` writes a slice
    as `<container>#<json_pointer>` and a pointer always begins `/`, so a `#`
    followed by anything else is part of the name the owner gave the file.

    Measured pre-fix: the row read `notes`, a file the run never read, in the one
    section whose entire ask is "did we read the right files"."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    manifest = json.loads(run.manifest.read_text())
    manifest["inputs"] = [
        {"artifact_id": "n2", "kind": "design_doc", "source_path": "/corpus/docs/notes#2.md"},
        {"artifact_id": "t-41", "kind": "trace", "source_path": "/corpus/docs/capture.json#/41"},
        {"artifact_id": "t-44", "kind": "trace", "source_path": "/corpus/docs/capture.json#/44"},
    ]
    run.manifest.write_text(json.dumps(manifest))
    groups = {g.kind: g for g in target_brief.inputs_read(run)}
    assert (groups["design_doc"].files, groups["design_doc"].slices) == (("notes#2.md",), 0)
    # The positive control in the same test: two real slices of one capture still
    # group as one file with the second counted away, so the clause tells the two
    # shapes apart rather than switching the collapse off. parsec's 71 slices of one
    # capture are what that behaviour is for.
    assert (groups["trace"].files, groups["trace"].slices) == (("capture.json",), 1)
