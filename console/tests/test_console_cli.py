"""The console's entry point: exit codes when the parser itself cannot be built."""

from __future__ import annotations

import pytest
from rubrica_console.cli import main


@pytest.mark.parametrize("make_dir", [True, False], ids=["empty", "missing"])
def test_bad_schema_dir_exits_2_with_one_line(tmp_path, monkeypatch, capsys, make_dir):
    # --effort's choices come from the manifest schema, so a schema dir with no
    # manifest schema in it breaks the parser before any argument is read.
    schema_dir = tmp_path / "schema"
    if make_dir:
        schema_dir.mkdir()
    monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(schema_dir))
    code = main(["--runs-dir", str(tmp_path)])
    out, err = capsys.readouterr()
    assert code == 2
    assert out == ""
    lines = err.splitlines()
    assert len(lines) == 1, err
    assert lines[0].startswith("error: cannot build the command-line parser: ")
    assert "RUBRICA_SCHEMA_DIR" in lines[0]
    assert "Traceback" not in err
