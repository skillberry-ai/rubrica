"""`read_progress` on odd dispatch logs: it is called from the job monitor and the
status poll with no try/except around it, so an exception here stops a member's
monitor or turns the poll into a 500. Every malformed line must be skipped."""

from __future__ import annotations

import json

import pytest
from rubrica_console.dispatch import read_progress


def _write(tmp_path, *lines):
    log = tmp_path / "dispatch.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log


def _assistant(message):
    return json.dumps({"type": "assistant", "message": message})


def test_normal_cost_line_is_read(tmp_path):
    progress = read_progress(_write(tmp_path, "cost $0.42 over 3 turns, ceiling 5"))
    assert progress.cost == pytest.approx(0.42)
    assert progress.turns == 3
    assert progress.finished is True


# jq 1.7.1 (measured) prints 0.0000001 as `1E-7`, and dispatch-stage.sh puts jq's
# text straight into the cost line, so a tiny spend reaches the log in that form.
@pytest.mark.parametrize(
    ("text", "value"),
    [("1E-7", 1e-7), ("1e-05", 1e-5), ("1.5E-8", 1.5e-8), ("2E+3", 2e3)],
)
def test_scientific_notation_cost_is_read(tmp_path, text, value):
    progress = read_progress(_write(tmp_path, f"cost ${text} over 2 turns, ceiling 5"))
    assert progress.cost == pytest.approx(value)
    assert progress.turns == 2
    assert progress.finished is True


@pytest.mark.parametrize("text", [".", "..", "1.2.3"])
def test_unparseable_cost_line_is_skipped(tmp_path, text):
    progress = read_progress(_write(tmp_path, f"cost ${text} over 3 turns"))
    assert progress.cost is None
    assert progress.finished is False


def test_assistant_message_that_is_a_list_is_skipped(tmp_path):
    progress = read_progress(_write(tmp_path, _assistant([{"type": "text"}])))
    assert progress.turns == 1
    assert progress.last == ""


def test_tool_use_input_that_is_a_list_is_skipped(tmp_path):
    block = {"type": "tool_use", "name": "Bash", "input": ["ls"]}
    progress = read_progress(_write(tmp_path, _assistant({"content": [block]})))
    assert progress.turns == 1
    assert progress.last == "Bash"


def test_tool_use_with_dict_input_names_the_tool_and_target(tmp_path):
    block = {"type": "tool_use", "name": "Read", "input": {"file_path": "/x/y.json"}}
    progress = read_progress(_write(tmp_path, _assistant({"content": [block]})))
    assert progress.last == "Read /x/y.json"


def test_missing_log_gives_empty_progress(tmp_path):
    progress = read_progress(tmp_path / "absent.log")
    assert progress.turns == 0
    assert progress.cost is None
    assert progress.finished is False


def test_log_that_is_a_directory_gives_empty_progress(tmp_path):
    # A path that exists but cannot be read as a file: the same OSError branch an
    # unreadable (chmod 000) file takes, without depending on not running as root.
    progress = read_progress(tmp_path)
    assert progress.turns == 0
    assert progress.cost is None
    assert progress.finished is False
