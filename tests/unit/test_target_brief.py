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
from rubrica.summary import Malformed
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
