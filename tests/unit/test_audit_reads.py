"""`scripts/audit-reads.sh`, the only instrument this project has for isolation.

The script had no test at all until the toolset section was added to it, which is
worth stating plainly: `docs/design/limitations.md` calls a transcript audit the
sole enforcement of the read isolation rule, and the two read violations on record
surfaced because a subagent volunteered them rather than because anything checked.

These tests drive the real script against synthetic transcripts. They assert what
it *reports*, never how it greps -- a source-level assertion would pass on a filter
that is present and unreachable, which is exactly the defect the toolset section
exists to expose.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "audit-reads.sh"

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="audit-reads.sh requires jq")


def _tool_use(name, **inp):
    """One assistant event carrying one tool_use, shaped as the transcript has it."""
    event = {"type": "tool_use", "name": name, "input": inp}
    return json.dumps({"type": "assistant", "message": {"content": [event]}})


def _transcript(tmp_path, *lines):
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _audit(path):
    proc = subprocess.run(
        [str(SCRIPT), str(path)], capture_output=True, text=True, env={**os.environ}
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    return proc.stdout


def test_the_audit_prints_the_toolset_the_dispatch_was_given(tmp_path):
    """Without it, an empty file-tools section is unreadable.

    MEASURED 2026-09-01: a dispatch's init event carries no `Glob` and no `Grep`, so
    two arms of the file-tools filter cannot match. A reader who cannot see the
    array has no way to tell "the stage used no Glob" from "there was no Glob to
    use", and one of those is evidence about the stage while the other is not.
    """
    t = _transcript(
        tmp_path,
        '{"type": "system", "subtype": "init", "tools": ["Bash", "Read", "Write"]}',
        _tool_use("Read", file_path="/run/01-claims/api.json"),
    )
    out = _audit(t)
    assert "== toolset the dispatch was given ==" in out
    assert "Bash, Read, Write" in out


def test_a_transcript_with_no_init_event_still_audits(tmp_path):
    """A hand-trimmed or older transcript must not take the script down.

    `set -euo pipefail` is on, and this section is a `jq` in a pipeline. The audit
    is run *after* a dispatch, often on a transcript somebody has already cut down,
    and refusing to report the reads because the header is missing would lose the
    only isolation evidence there is.
    """
    t = _transcript(tmp_path, _tool_use("Read", file_path="/run/01-claims/api.json"))
    out = _audit(t)
    assert "01-claims/api.json" in out


def test_the_audit_still_reports_a_file_tool_the_current_build_cannot_produce(tmp_path):
    """The Glob and Grep filter arms are kept deliberately, so they must work.

    Deleting them would tidy away two arms that cannot match at 2.1.252 and would
    leave a build that restores those tools silently unaudited. This test is what
    makes keeping them a decision rather than a leftover: it feeds a Glob event in
    and requires the audit to name it.
    """
    t = _transcript(
        tmp_path,
        '{"type": "system", "subtype": "init", "tools": ["Bash", "Read", "Glob"]}',
        _tool_use("Glob", pattern="01-claims/*.json"),
    )
    out = _audit(t)
    assert "01-claims/*.json" in out


def test_the_audit_lists_bash_commands_separately_from_the_file_tools(tmp_path):
    """Bash is the hole the file-tool list does not cover, and now the only one.

    With no Glob and no Grep in the toolset, Bash is a dispatched stage's sole route
    to enumerating a directory -- measured 2026-09-01 -- so every read it performs
    that way appears here and nowhere else.
    """
    t = _transcript(
        tmp_path,
        '{"type": "system", "subtype": "init", "tools": ["Bash", "Read"]}',
        _tool_use("Bash", command="ls -1 01-claims"),
    )
    out = _audit(t)
    bash_section = out.split("== bash commands ==")[1]
    assert "ls -1 01-claims" in bash_section
