"""check-refs over a 01-claims/ member that parses but has the wrong shape.

Measured before refs._claims_shape_problem existed: `[]` in place of the toy's
api-json claims file made check-refs exit 1 with 28 `no such claim` findings
against the world model and its partials, none naming the broken file, and `{}`
surfaced as an `[internal]` KeyError. Both now name `01-claims/<id>.json` and
nothing else, the way a truncated claims file already did.
"""

from __future__ import annotations

import os

import pytest

from rubrica.cli import main
from rubrica.paths import RunPaths
from rubrica.refs import check_all
from tests.toy import build_toy_run


@pytest.fixture
def toy_run(tmp_path) -> RunPaths:
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    assert check_all(run) == [], "the healthy baseline these tests break"
    return run


@pytest.mark.parametrize(
    "text",
    [
        "[]",
        '"x"',
        "null",
        "{}",
        '{"schema_version": "0.1", "artifact_id": "api-json"}',
        '{"schema_version": "0.1", "artifact_id": "api-json", "claims": {}}',
        '{"schema_version": "0.1", "artifact_id": "api-json", "claims": [{"kind": "x"}]}',
    ],
)
def test_a_misshapen_claims_file_is_the_only_finding(toy_run, text):
    path = toy_run.claims("api-json")
    assert path.is_file()
    path.write_text(text, encoding="utf-8")

    findings = check_all(toy_run)
    assert [f.artifact for f in findings] == [path]
    assert not any("no such claim" in f.message for f in findings)


def test_check_refs_cli_names_the_claims_file(toy_run, capsys):
    path = toy_run.claims("api-json")
    path.write_text("[]", encoding="utf-8")

    code = main(["check-refs", "--run", str(toy_run.root)])
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    assert code == 1
    assert len(lines) == 1
    assert "01-claims/api-json.json" in lines[0]
    assert "world-model" not in out
    assert "[internal]" not in out


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a chmod 000 file")
def test_an_unreadable_claims_file_fabricates_no_claim_findings(toy_run, capsys):
    """chmod 000 is an unreadable run (exit 2), never `no such claim` lines."""
    path = toy_run.claims("api-json")
    path.chmod(0o000)
    try:
        code = main(["check-refs", "--run", str(toy_run.root)])
    finally:
        path.chmod(0o644)
    out = capsys.readouterr().out
    assert code == 2
    assert "no such claim" not in out
