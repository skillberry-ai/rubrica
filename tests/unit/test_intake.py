import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from rubrica.artifacts import read_json, sha256_of
from rubrica.intake import classify, intake, slug
from rubrica.validate import validate_artifact

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
    from rubrica.paths import safe_segment

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


def test_a_suffix_never_lands_on_an_id_another_input_already_has(tmp_path):
    """Measured: `d1/x.md d2/x.md x-md-2` gave ids `x-md`, `x-md-2`, `x-md-2`,
    intake exited 0, and check-refs then named manifest.json -- which no stage
    can repair. Every id handed out is now remembered, suffixed ones too."""
    from rubrica.refs import check_all

    inputs = [
        _write(tmp_path / "d1", "x.md", "# one\n"),
        _write(tmp_path / "d2", "x.md", "# two\n"),
        _write(tmp_path / "d3", "x-md-2", "# three\n"),
    ]
    run = intake(
        inputs=inputs,
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
        now=NOW,
    )
    ids = [e["artifact_id"] for e in read_json(run.manifest)["inputs"]]
    assert len(set(ids)) == 3, ids
    assert ids[:2] == ["x-md", "x-md-2"]
    assert len(list(run.inputs_dir.iterdir())) == 3
    assert check_all(run) == []


def test_unique_artifact_id_compares_under_segment_key():
    """Case-only repeats share one file on macOS, so they are repeats here too.
    Plain lower-case runs keep exactly the ids they always had."""
    from rubrica.intake import _unique_artifact_id

    used: dict[str, int] = {}
    assert [_unique_artifact_id(b, used) for b in ["a", "a", "a", "b"]] == ["a", "a-2", "a-3", "b"]
    used = {}
    assert [_unique_artifact_id(b, used) for b in ["Orders", "orders", "ORDERS-2"]] == [
        "Orders",
        "orders-2",
        "ORDERS-2-2",
    ]


def test_a_case_only_pair_of_filenames_gets_distinct_ids(tmp_path):
    run = intake(
        inputs=[_write(tmp_path / "p", "A.md", "# A\n"), _write(tmp_path / "q", "a.md", "# a\n")],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
        now=NOW,
    )
    ids = [e["artifact_id"] for e in read_json(run.manifest)["inputs"]]
    assert len({i.casefold() for i in ids}) == 2, ids
    assert len(list(run.inputs_dir.iterdir())) == 2


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


def test_the_manifest_records_the_name_each_input_was_stored_under(tmp_path):
    source = tmp_path / "api.json"
    source.write_text('{"tools": []}', encoding="utf-8")
    run = intake(
        inputs=[source],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
    )
    entry = read_json(run.manifest)["inputs"][0]
    # slug("api.json") is "api-json" (test_slug_produces_safe_path_segments pins
    # this), and stored_name appends the suffix on top of that, exactly as
    # test_intake_copies_inputs_and_records_hash_kind_and_size already pins for
    # this same source name -- so the registered name is "api-json.json", not a
    # copy of the source's own name.
    assert entry["stored_as"] == "api-json.json"
    assert run.input_file(entry["stored_as"]).is_file()
    assert sha256_of(run.input_file(entry["stored_as"])) == entry["sha256"]


def test_a_suffix_that_would_make_an_unsafe_name_is_dropped(tmp_path):
    """The extension is cosmetic; the artifact id is the identity.

    A source named `weird.js on` would otherwise be stored as `weird-js on`,
    which manifest.stored_as cannot safely reference and paths.input_file would
    raise on -- turning a registrable input into an exit 2.
    """
    source = tmp_path / "weird.js on"
    source.write_text("{}", encoding="utf-8")
    run = intake(
        inputs=[source],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
    )
    entry = read_json(run.manifest)["inputs"][0]
    assert entry["stored_as"] == "weird-js-on"
    assert run.input_file("weird-js-on").is_file()


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


# -- intake must never mint a run its own schema rejects ----------------------

_BAD_ARGUMENTS = {
    "empty-name": {"target_name": ""},
    "blank-name": {"target_name": "   "},
    "empty-interface": {"target_interface": ""},
    "blank-interface": {"target_interface": "\t\n"},
    "zero-rounds": {"max_rounds": 0},
    "negative-rounds": {"max_rounds": -1},
    "zero-scenarios": {"max_scenarios": 0},
    "negative-scenarios": {"max_scenarios": -3},
    "float-rounds": {"max_rounds": 2.5},
    "string-scenarios": {"max_scenarios": "8"},
}


@pytest.mark.parametrize("case", sorted(_BAD_ARGUMENTS))
def test_intake_refuses_arguments_the_manifest_schema_would_reject(tmp_path, case):
    """The defect intake could mint at exit 0 and no repair prompt could ever clear.

    manifest-0.1.json puts minLength 1 on both target strings and minimum 1 on
    both limits, so these arguments produced a run directory, a printed path and
    exit 0 -- then three exit-1 schema findings against manifest.json the next
    time anyone ran `validate --stage intake`. intake is code: no skill wrote
    that manifest, so the repair loop the finding routes to has nothing to
    re-dispatch. Refused at the call, like manifest.record_stage refuses a blank
    --model, and nothing is written.
    """
    kwargs = dict(
        inputs=[_write(tmp_path / "src", "api.json", {"tools": []})],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
        now=NOW,
    )
    kwargs.update(_BAD_ARGUMENTS[case])
    with pytest.raises(ValueError):
        intake(**kwargs)
    assert not (tmp_path / "runs").exists(), "a refused intake must mint nothing"


@pytest.mark.parametrize("case", sorted(_BAD_ARGUMENTS))
def test_whatever_intake_does_mint_validates_as_the_intake_stage(tmp_path, case):
    """The property behind the test above, stated over the same arguments.

    Rather than pinning the four guards one at a time, this asserts the invariant
    they exist for: intake either refuses, or mints a manifest that clears layer 1
    on the spot. A future argument that slips past the guards fails here even if
    nobody thought to add a case for it.
    """
    kwargs = dict(
        inputs=[_write(tmp_path / "src", "api.json", {"tools": []})],
        runs_dir=tmp_path / "runs",
        target_name="aap2",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
        now=NOW,
    )
    kwargs.update(_BAD_ARGUMENTS[case])
    try:
        run = intake(**kwargs)
    except ValueError:
        return
    assert validate_artifact(run.manifest, "manifest") == []


def test_classify_recognises_a_chat_trajectory_as_a_trace(tmp_path):
    """The chat-trajectory skeletons (docs/design/findings.md): a list of
    {role, content} messages carries neither `spans` nor `trace_id`, so it
    classified `other` and got a skeleton digest. It is a capture of what the
    target did, which is what `trace` means."""
    payload = [
        {"role": "system", "content": "You are an airline agent."},
        {"role": "user", "content": "Cancel EHGLP3."},
        {"role": "assistant", "tool_calls": [{"function": {"name": "cancel_reservation"}}]},
    ]
    assert classify(_write(tmp_path, "37_1_abc.json", payload)) == "trace"


def test_classify_leaves_a_list_of_non_message_records_alone(tmp_path):
    """The widening is scoped to conversations. A homogeneous list of records
    without roles is not one, and calling it a trace would hand the trace
    producer a payload with no field it can read."""
    payload = [{"id": 1, "value": "a"}, {"id": 2, "value": "b"}, {"id": 3, "value": "c"}]
    assert classify(_write(tmp_path, "records.json", payload)) == "other"


# --- T-136: a unique artifact id is not a unique stored file name -------------------------

# The two pairs measured to collide: an id containing a dot beside a suffixed
# one, and a case-only pair that is one file on a case-insensitive disk.
_STORED_NAME_PAIRS = [
    (("capture-json-0", "container-element.json"), ("capture-json-0.json", "tool")),
    (("orders", "orders.json"), ("Orders.json", "tool")),
]


@pytest.mark.parametrize("first,repeat", _STORED_NAME_PAIRS)
def test_the_measured_pairs_collide_under_segment_key(first, repeat):
    from pathlib import Path

    from rubrica.intake import stored_name, stored_name_collisions

    named = [(aid, stored_name(aid, Path(src))) for aid, src in (first, repeat)]
    collisions = stored_name_collisions(named)
    assert [(c[0], c[2]) for c in collisions] == [(first[0], repeat[0])]


def test_distinct_stored_names_are_not_collisions():
    from rubrica.intake import stored_name_collisions

    assert stored_name_collisions([("a", "a.json"), ("a-json", "a-json.json"), ("b", "b")]) == []


def test_intake_input_refuses_a_stored_name_collision_and_mints_nothing(tmp_path, monkeypatch):
    """slug() leaves no dot in an id, so the --input path is reached here by
    forcing the ids; the guard is what keeps a future slug() change from
    reopening the silent overwrite. A UsageError, like a missing input."""
    import rubrica.intake as intake_module
    from rubrica.errors import UsageError

    one = _write(tmp_path / "src", "a.json", {"tools": []})
    two = _write(tmp_path / "src", "b", "plain")
    monkeypatch.setattr(intake_module, "_unique_ids", lambda inputs: ["orders", "Orders.json"])
    runs = tmp_path / "runs"
    with pytest.raises(UsageError, match=r"'orders' and 'Orders\.json'.*00-inputs/orders\.json"):
        intake(
            inputs=[one, two],
            runs_dir=runs,
            target_name="t",
            target_interface="mcp",
            max_rounds=2,
            max_scenarios=8,
            now=NOW,
        )
    assert not runs.exists() or not any(runs.iterdir())


def _add_admitted_candidate(run, candidate_id, path):
    from rubrica.artifacts import write_json

    catalogue = read_json(run.catalogue)
    template = next(c for c in catalogue["candidates"] if c["origin"] == "corpus")
    catalogue["candidates"].append(
        {**template, "candidate_id": candidate_id, "path": path, "kind": "other"}
    )
    write_json(run.catalogue, catalogue)
    record = read_json(run.triage)
    record["dispositions"].append(
        {
            "candidate_id": candidate_id,
            "disposition": "admit",
            "reason": "carries evidence of the target's shape",
            "authority": "triage",
        }
    )
    write_json(run.triage, record)


@pytest.mark.parametrize("first,repeat", _STORED_NAME_PAIRS)
def test_intake_run_refuses_admits_that_share_a_stored_file(tmp_path, first, repeat):
    """The reproduction: two admitted candidates whose ids differ but whose
    stored names are one file. Refused as findings against the catalogue
    (exit 1, like intake --run's other catalogue refusals), nothing copied."""
    from rubrica import intake as intake_module
    from rubrica import refs
    from tests.unit.test_admit import _surveyed_and_triaged

    run = _surveyed_and_triaged(tmp_path)
    if first[0] != "capture-json-0":  # capture-json-0 is already an admitted container element
        _add_admitted_candidate(run, first[0], first[1])
    _add_admitted_candidate(run, repeat[0], repeat[1])
    assert refs.check_triage(run) == []

    findings = intake_module.admit_from_triage(run)
    assert len(findings) == 1
    assert findings[0].artifact == run.catalogue
    assert repr(first[0]) in findings[0].message and repr(repeat[0]) in findings[0].message
    assert not run.inputs_dir.exists()
    assert not run.manifest.exists()


def test_intake_run_without_collisions_is_unchanged(tmp_path):
    from rubrica import intake as intake_module
    from tests.unit.test_admit import _surveyed_and_triaged

    run = _surveyed_and_triaged(tmp_path)
    assert intake_module.admit_from_triage(run) == []
    names = sorted(e["stored_as"] for e in read_json(run.manifest)["inputs"])
    assert names == ["capture-json-0.json", "capture-json-1.json", "readme-md.md"]


@pytest.mark.parametrize("case_only", [False, True])
def test_check_inputs_reports_a_repeated_stored_as(tmp_path, case_only):
    from rubrica import refs
    from rubrica.artifacts import write_json

    one = _write(tmp_path / "src", "a.json", {"tools": []})
    two = _write(tmp_path / "src", "b.json", {"tools": [1]})
    run = intake(
        inputs=[one, two],
        runs_dir=tmp_path / "runs",
        target_name="t",
        target_interface="mcp",
        max_rounds=2,
        max_scenarios=8,
        now=NOW,
    )
    assert refs.check_inputs(run) == []
    manifest = read_json(run.manifest)
    first = manifest["inputs"][0]["stored_as"]
    manifest["inputs"][1]["stored_as"] = first.upper() if case_only else first
    write_json(run.manifest, manifest)
    repeats = [f for f in refs.check_inputs(run) if f.pointer == "/inputs/1/stored_as"]
    assert len(repeats) == 1
    assert "the same file as /inputs/0" in repeats[0].message
    assert ("differing only in case" in repeats[0].message) is case_only
