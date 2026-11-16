"""`set-limit` when the decisions.md append fails after the manifest is written.

The manifest is written first on purpose (see `manifest.set_limit`), so a failed
append leaves a live limit change with no decisions.md line. The scout's repro
printed a bare `[Errno 13] Permission denied`, exit 2, which reads as "nothing
happened". The exit stays 2; the message must say the limit changed.
"""

from __future__ import annotations

import os

import pytest

from rubrica.artifacts import read_json
from rubrica.cli import main
from tests.toy import build_toy_run


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root ignores file permissions, so a read-only decisions.md stays writable",
)
def test_a_read_only_decisions_md_says_the_limit_was_changed(tmp_path, capsys):
    run = build_toy_run(tmp_path / "runs", upto="intake")
    old = read_json(run.manifest)["limits"]["max_rounds"]
    new = old + 2
    if not run.decisions.exists():
        run.decisions.write_text("", encoding="utf-8")
    before = run.decisions.read_text(encoding="utf-8")
    run.decisions.chmod(0o444)
    try:
        code = main(
            [
                "set-limit",
                "--run",
                str(run.root),
                "--max-rounds",
                str(new),
                "--reason",
                "probing the loop bound",
            ]
        )
    finally:
        run.decisions.chmod(0o644)
    captured = capsys.readouterr()

    assert code == 2, captured.out
    assert captured.out.strip() == ""
    assert f"max_rounds {old} -> {new}" in captured.err
    assert "WAS changed" in captured.err
    assert "note is missing" in captured.err
    # The message is telling the truth: the manifest holds the new value and
    # decisions.md gained nothing.
    assert read_json(run.manifest)["limits"]["max_rounds"] == new
    assert run.decisions.read_text(encoding="utf-8") == before
