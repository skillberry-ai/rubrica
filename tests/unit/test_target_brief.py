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
    assert "clm-does-not-exist" not in target_brief.source_index(run)


def test_source_index_returns_a_marker_when_claims_cannot_be_read(tmp_path):
    """Never a silently empty dict. summary.py:725-770 rules that reporting empty
    on an unreadable 01-claims/ is the one reading a human at gate 1 must never be
    handed, and this page is mailed outside the project."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    os.chmod(run.claims_dir, 0o000)
    try:
        result = target_brief.source_index(run)
    finally:
        os.chmod(run.claims_dir, 0o755)
    assert isinstance(result, Malformed)
    assert "01-claims" in result.what


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
    ],
)
def test_common_prefix(files, expected):
    assert target_brief._common_prefix(files) == expected


def test_shorten_keeps_the_slice_fragment(tmp_path):
    """A `#/NN` fragment marks one slice of a sliced artifact. parsec's 71 trace
    inputs are 71 slices of one capture, so the fragment is the only thing
    distinguishing them and dropping it would collapse 71 records into one."""
    assert target_brief._shorten("/a/b/trace.json#/41", "/a/b") == "trace.json#/41"
    assert target_brief._shorten("/a/b/src/tool.py", "/a/b") == "src/tool.py"
    # A prefix that is not actually a parent leaves the path alone rather than
    # slicing characters off its front.
    assert target_brief._shorten("/other/tool.py", "/a/b") == "/other/tool.py"
