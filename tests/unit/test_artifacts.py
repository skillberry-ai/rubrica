import json
import os
import re

import pytest

from rubrica import artifacts
from rubrica.artifacts import ArtifactError, append_decision, read_json, write_json


def test_canonical_bytes_are_exactly_what_write_json_writes(tmp_path):
    """Survey hashes an element before it exists as a file; intake materialises
    it later and refs re-hashes the result. One function, or the two disagree
    and every exploded input reports a digest mismatch."""
    payload = {"b": 1, "a": [2, 3]}
    path = tmp_path / "x.json"
    artifacts.write_json(path, payload)
    assert path.read_bytes() == artifacts.canonical_bytes(payload)


def test_round_trip(tmp_path):
    path = tmp_path / "nested" / "a.json"
    write_json(path, {"b": 1, "a": [1, 2]})
    assert read_json(path) == {"b": 1, "a": [1, 2]}


def test_output_is_canonical_and_key_order_independent(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_json(first, {"b": 1, "a": 2})
    write_json(second, {"a": 2, "b": 1})
    assert first.read_bytes() == second.read_bytes()
    assert first.read_text(encoding="utf-8") == '{\n  "a": 2,\n  "b": 1\n}\n'


def test_non_ascii_is_written_literally_not_escaped(tmp_path):
    path = tmp_path / "a.json"
    write_json(path, {"msg": "café"})
    assert "café" in path.read_text(encoding="utf-8")


def test_read_missing_artifact_names_the_path(tmp_path):
    with pytest.raises(ArtifactError, match="missing artifact"):
        read_json(tmp_path / "absent.json")


def test_read_malformed_artifact_names_the_path(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ArtifactError, match="malformed JSON"):
        read_json(path)


def test_failed_write_leaves_the_previous_content_intact(tmp_path):
    path = tmp_path / "a.json"
    write_json(path, {"keep": True})
    with pytest.raises(TypeError):
        write_json(path, {"bad": object()})
    assert read_json(path) == {"keep": True}


def test_failed_write_leaves_no_temp_files_behind(tmp_path):
    path = tmp_path / "a.json"
    write_json(path, {"keep": True})
    with pytest.raises(TypeError):
        write_json(path, {"bad": object()})
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.json"]


def test_write_overwrites_in_place(tmp_path):
    path = tmp_path / "a.json"
    write_json(path, {"v": 1})
    write_json(path, {"v": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {"v": 2}


def test_append_decision_creates_then_appends(tmp_path):
    path = tmp_path / "decisions.md"
    append_decision(path, "round 1: continue")
    append_decision(path, "round 2: converged\n")
    assert path.read_text(encoding="utf-8") == "round 1: continue\nround 2: converged\n"


def test_a_failure_after_the_temp_file_exists_cleans_it_up(tmp_path, monkeypatch):
    path = tmp_path / "a.json"
    write_json(path, {"keep": True})

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        write_json(path, {"v": 2})

    assert read_json(path) == {"keep": True}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.json"]


def test_read_non_utf8_artifact_names_the_path(tmp_path):
    """Bytes that are not UTF-8 raise ArtifactError, exactly like unparseable JSON.

    Without this door UnicodeDecodeError escaped read_json. It is a ValueError,
    not an OSError, so nothing between here and cli.py's catch-all knew a path:
    `validate --stage triage-slices` over such a file exited 1 with an
    [internal] finding anchored on the *run root* whose advice was to run the
    very command that had just been run. Both directions were measured -- the
    same invocation now prints one [schema] line naming 00-slices.json.
    """
    path = tmp_path / "a.json"
    path.write_bytes(b"\xff\xfe\x00bogus")
    with pytest.raises(ArtifactError, match="not UTF-8 text"):
        read_json(path)
    # The path is in the message, which is the half that was missing: the layer
    # above turns str(exc) into the finding, so a message without the path
    # produces a finding that cannot be acted on.
    with pytest.raises(ArtifactError, match=re.escape(str(path))):
        read_json(path)
