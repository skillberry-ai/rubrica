import json

import pytest

from testgen.artifacts import ArtifactError, append_decision, read_json, write_json


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
