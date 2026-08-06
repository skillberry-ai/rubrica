import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from testgen.artifacts import read_json
from testgen.intake import classify, intake, sha256_of, slug
from testgen.validate import validate_artifact

NOW = datetime(2026, 8, 6, 12, 30, 5, tzinfo=UTC)


def _write(tmp_path, name, payload):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("api.json", "api-json"),
        ("parsec-aap2/api.json", "parsec-aap2-api-json"),
        ("Weird Name!!.MD", "weird-name-md"),
        ("---leading", "leading"),
        ("", "input"),
    ],
)
def test_slug_produces_safe_path_segments(raw, expected):
    from testgen.paths import safe_segment

    result = slug(raw)
    assert result == expected
    assert safe_segment(result) == result


def test_classify_recognises_an_mcp_tool_schema(tmp_path):
    assert classify(_write(tmp_path, "api.json", {"tools": []})) == "mcp_tool_schema"


def test_classify_recognises_an_entity_schema(tmp_path):
    assert classify(_write(tmp_path, "schema.json", {"jobs": {}})) == "entity_schema"


def test_classify_recognises_openapi_by_content(tmp_path):
    assert classify(_write(tmp_path, "spec.json", {"openapi": "3.1.0"})) == "openapi"


def test_classify_recognises_a_trace_by_content(tmp_path):
    assert classify(_write(tmp_path, "run1.json", {"trace_id": "tr-1", "spans": []})) == "trace"


def test_classify_recognises_a_design_document(tmp_path):
    assert classify(_write(tmp_path, "notes.md", "# Design")) == "design_doc"


def test_classify_recognises_source_code(tmp_path):
    assert classify(_write(tmp_path, "agent.py", "def run(): ...")) == "source_code"


def test_classify_falls_back_to_other(tmp_path):
    assert classify(_write(tmp_path, "blob.bin", "\x00\x01")) == "other"


def test_sha256_matches_the_known_digest_of_empty_input(tmp_path):
    path = _write(tmp_path, "empty", "")
    assert sha256_of(path) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_sha256_of_a_file_larger_than_one_chunk(tmp_path):
    """The empty-file case runs zero loop iterations, so the read loop needs
    a file that spans several 64 KiB chunks to be exercised at all."""
    data = bytes(range(256)) * 1024  # 256 KiB: four full chunks
    path = tmp_path / "big.bin"
    path.write_bytes(data)
    assert len(data) > (1 << 16)
    assert sha256_of(path) == hashlib.sha256(data).hexdigest()


def test_sha256_of_a_file_that_does_not_end_on_a_chunk_boundary(tmp_path):
    """A partial final read is the case an off-by-one in the loop would break."""
    data = bytes(range(256)) * 1024 + b"tail"
    path = tmp_path / "ragged.bin"
    path.write_bytes(data)
    assert sha256_of(path) == hashlib.sha256(data).hexdigest()


def test_intake_mints_a_run_id_from_the_supplied_timestamp(tmp_path):
    run = intake(
        inputs=[_write(tmp_path / "src", "api.json", {"tools": []})],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
        now=NOW,
    )
    assert run.root.name == "run-20260806-123005"


def test_intake_refuses_a_naive_datetime(tmp_path):
    """Guessing the zone would make the run id host-dependent.

    .astimezone() on a naive value assumes the *system local* zone, so the
    same call on a UTC host and a US/Pacific host would mint two different
    run ids and created_utc values -- the two fields the design says must
    never come from a skill because they must be stable.
    """
    with pytest.raises(ValueError, match="timezone-aware"):
        intake(
            inputs=[_write(tmp_path / "src", "api.json", {"tools": []})],
            runs_dir=tmp_path / "runs",
            target_name="aap2",
            target_interface="mcp",
            max_rounds=2,
            max_scenarios=8,
            now=datetime(2026, 8, 6, 23, 30),
        )


def test_intake_converts_an_aware_non_utc_timestamp_to_utc(tmp_path):
    """23:30+02:00 on the 6th is 21:30Z on the 6th, in both fields."""
    run = intake(
        inputs=[_write(tmp_path / "src", "api.json", {"tools": []})],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
        now=datetime(2026, 8, 6, 23, 30, tzinfo=timezone(timedelta(hours=2))),
    )
    assert run.root.name == "run-20260806-213000"
    manifest = read_json(run.manifest)
    assert manifest["created_utc"] == "2026-08-06T21:30:00Z"
    assert manifest["run_id"] == "run-20260806-213000"


def test_intake_converts_an_aware_timestamp_that_crosses_the_date_line(tmp_path):
    """A -08:00 evening is the next UTC day; the run id must say so."""
    run = intake(
        inputs=[_write(tmp_path / "src", "api.json", {"tools": []})],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
        now=datetime(2026, 8, 6, 23, 30, tzinfo=timezone(timedelta(hours=-8))),
    )
    assert run.root.name == "run-20260807-073000"


def test_intake_writes_a_schema_valid_manifest(tmp_path):
    run = intake(
        inputs=[_write(tmp_path / "src", "api.json", {"tools": []})],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
        now=NOW,
    )
    assert validate_artifact(run.manifest, "manifest") == []


def test_intake_copies_inputs_and_records_hash_kind_and_size(tmp_path):
    source = _write(tmp_path / "src", "api.json", {"tools": []})
    run = intake(
        inputs=[source],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
        now=NOW,
    )
    entry = read_json(run.manifest)["inputs"][0]
    assert entry["artifact_id"] == "api-json"
    assert entry["kind"] == "mcp_tool_schema"
    assert entry["sha256"] == sha256_of(source)
    assert entry["bytes"] == source.stat().st_size
    copied = run.inputs_dir / "api-json.json"
    assert copied.read_bytes() == source.read_bytes()


def test_intake_disambiguates_colliding_artifact_ids(tmp_path):
    first = _write(tmp_path / "a", "api.json", {"tools": [1]})
    second = _write(tmp_path / "b", "api.json", {"tools": [2]})
    run = intake(
        inputs=[first, second],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
        now=NOW,
    )
    ids = [e["artifact_id"] for e in read_json(run.manifest)["inputs"]]
    assert ids == ["api-json", "api-json-2"]


def test_intake_records_the_limits_the_orchestrator_will_enforce(tmp_path):
    run = intake(
        inputs=[_write(tmp_path / "src", "api.json", {"tools": []})],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
        now=NOW,
    )
    assert read_json(run.manifest)["limits"] == {"max_rounds": 2, "max_scenarios": 8}


def test_intake_refuses_an_empty_input_set(tmp_path):
    with pytest.raises(ValueError, match="at least one input"):
        intake(
            inputs=[],
            runs_dir=tmp_path / "runs",
            target_name="aap2",
            target_interface="mcp",
            max_rounds=2,
            max_scenarios=8,
            now=NOW,
        )


def test_intake_refuses_a_missing_input(tmp_path):
    with pytest.raises(FileNotFoundError):
        intake(
            inputs=[tmp_path / "absent.json"],
            runs_dir=tmp_path / "runs",
            target_name="aap2",
            target_interface="mcp",
            max_rounds=2,
            max_scenarios=8,
            now=NOW,
        )


def test_intake_refuses_to_overwrite_an_existing_run(tmp_path):
    kwargs = dict(
        inputs=[_write(tmp_path / "src", "api.json", {"tools": []})],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
        now=NOW,
    )
    intake(**kwargs)
    with pytest.raises(FileExistsError):
        intake(**kwargs)
