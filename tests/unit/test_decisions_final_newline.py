"""decide on a decisions.md a person saved without a final newline (T-82).

Before the fix the new entry was glued onto the hand-written last line, so the
console's gate reader -- which needs each entry to start its own line with `- `
-- saw no approval, and the Approve button reported success with the gate open.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from rubrica.manifest import decide
from rubrica.paths import RunPaths

NOW = datetime(2026, 11, 18, 22, 2, 44, tzinfo=UTC)
ENTRY = "- 2026-11-18T22:02:44Z human gate 1 (console): looks good"


def _run(tmp_path) -> RunPaths:
    run = RunPaths(tmp_path / "run-20261118-100000")
    run.root.mkdir()
    return run


def test_an_entry_after_a_missing_final_newline_starts_its_own_line(tmp_path):
    run = _run(tmp_path)
    run.decisions.write_bytes(b"- 2026-11-18T10:00:00Z hand note without newline")
    decide(run, "human gate 1 (console): looks good", now=NOW)
    lines = run.decisions.read_text(encoding="utf-8").splitlines()
    assert lines == ["- 2026-11-18T10:00:00Z hand note without newline", ENTRY]
    assert all(line.startswith("- ") for line in lines)


def test_a_non_utf8_last_line_without_newline_still_gets_its_own_line(tmp_path):
    # Only the last byte is read, so a Latin-1 byte a human typed (T-81) neither
    # breaks the append nor hides the missing newline.
    run = _run(tmp_path)
    run.decisions.write_bytes(b"- 2026-11-18T10:00:00Z caf\xe9")
    decide(run, "human gate 1 (console): looks good", now=NOW)
    assert (
        run.decisions.read_bytes() == b"- 2026-11-18T10:00:00Z caf\xe9\n" + ENTRY.encode() + b"\n"
    )


@pytest.mark.parametrize("before", [b"", b"- 2026-11-18T10:00:00Z hand note\n"])
def test_an_empty_or_newline_ended_file_gets_no_blank_line(tmp_path, before):
    run = _run(tmp_path)
    run.decisions.write_bytes(before)
    decide(run, "human gate 1 (console): looks good", now=NOW)
    assert run.decisions.read_bytes() == before + ENTRY.encode() + b"\n"


def test_a_missing_file_gets_no_blank_line(tmp_path):
    run = _run(tmp_path)
    decide(run, "human gate 1 (console): looks good", now=NOW)
    assert run.decisions.read_text(encoding="utf-8") == ENTRY + "\n"
