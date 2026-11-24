"""smoke, compare-gold and sample-for-review refuse a manifest with no usable run_id.

Each used to index `read_json(run.manifest)["run_id"]` bare: a manifest of `[]`
or `"hi"` raised TypeError and `{}` raised KeyError, and cli.py's catch-all made
each an exit-1 `[internal]` finding telling the reader to run `validate` -- which
does not cover manifest.json. manifest.json is intake's code output, so no stage
can repair it: exit 2, one error line naming the file, and nothing written.
"""

from __future__ import annotations

import json

import pytest

from rubrica.cli import main
from tests.builders import minimal_gold
from tests.unit.test_cli import _write_roster
from tests.unit.test_refs_states import build_state

BAD_MANIFESTS = ([], "hi", {}, {"run_id": 7}, {"run_id": ""})


def _corrupt(tmp_path, payload):
    run = build_state(tmp_path / "run", "emit")
    run.manifest.write_text(json.dumps(payload), encoding="utf-8")
    return run


def _assert_refused(code, capsys, run):
    out, err = capsys.readouterr()
    assert code == 2
    assert out == ""
    lines = err.strip().splitlines()
    assert len(lines) == 1, err
    assert lines[0].startswith("error: ")
    assert "manifest.json" in lines[0]
    assert "[internal]" not in err


@pytest.mark.parametrize("payload", BAD_MANIFESTS)
def test_sample_for_review_refuses_a_manifest_with_no_run_id(tmp_path, capsys, payload):
    run = _corrupt(tmp_path, payload)
    code = main(["sample-for-review", "--run", str(run.root)])
    _assert_refused(code, capsys, run)
    assert not run.measurement_dir.exists()


@pytest.mark.parametrize("payload", BAD_MANIFESTS)
def test_compare_gold_refuses_a_manifest_with_no_run_id(tmp_path, capsys, payload):
    run = _corrupt(tmp_path, payload)
    gold = tmp_path / "gold.json"
    gold.write_text(json.dumps(minimal_gold()), encoding="utf-8")
    code = main(["compare-gold", "--run", str(run.root), "--gold", str(gold)])
    _assert_refused(code, capsys, run)
    assert not run.measurement_dir.exists()


@pytest.mark.parametrize("payload", BAD_MANIFESTS)
def test_smoke_refuses_a_manifest_with_no_run_id(tmp_path, capsys, payload):
    run = _corrupt(tmp_path, payload)
    roster = _write_roster(tmp_path)
    code = main(["smoke", "--run", str(run.root), "--agents", str(roster)])
    _assert_refused(code, capsys, run)
    # Refused before any agent ran: no report, no per-role measurement tree.
    assert not run.report.exists()
    assert not run.measurement_dir.exists()
