"""The split, and the invariant that survives it.

intake() keeps its exact signature because twenty call sites and
tests/toy.py's build_toy_run depend on it. What changes is that survey can now
mint a run without writing a manifest, and admit can write a manifest into a
run it did not mint.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rubrica import intake, validate
from rubrica.artifacts import ArtifactError, canonical_bytes, read_json, write_json

NOW = datetime(2026, 8, 14, 21, 30, 0, tzinfo=UTC)


def _write_catalogue(run, *, corpus_roots: list[Path], candidates: list[dict]) -> None:
    """A minimal 00-catalogue.json, just enough for _container_path to resolve.

    Not schema-validated here -- this module tests intake.materialise, not
    layer 1 -- but shaped like the real thing (request.corpus_roots + a
    candidates list) since that is exactly what _container_path reads.
    """
    write_json(
        run.catalogue,
        {
            "schema_version": "0.1",
            "run_id": run.root.name,
            "created_utc": "2026-08-14T21:30:00Z",
            "request": {
                "target": {"name": "t", "interface": "i"},
                "objective": "breadth",
                "corpus_roots": [str(root) for root in corpus_roots],
                "limits": {"max_rounds": 1, "max_scenarios": 1},
            },
            "policy": {
                "exclusion_reasons": ["binary"],
                "explode_min_elements": 3,
                "explode_min_common_keys": 3,
                "digest_body_chars": 2000,
                "max_candidates": 500,
                "max_catalogue_bytes": 1_048_576,
            },
            "candidates": candidates,
            "excluded": [],
        },
    )


def test_mint_run_creates_a_directory_and_no_manifest(tmp_path):
    run, stamp = intake.mint_run(tmp_path / "runs", now=NOW)
    assert run.root.is_dir()
    assert run.root.name == "run-20260814-213000"
    assert stamp == NOW
    assert not run.manifest.exists()


def test_mint_run_refuses_an_existing_run_directory(tmp_path):
    intake.mint_run(tmp_path / "runs", now=NOW)
    with pytest.raises(FileExistsError):
        intake.mint_run(tmp_path / "runs", now=NOW)


def test_intake_still_mints_and_registers_in_one_call(tmp_path):
    """The regression guard for the whole split: the old entry point behaves
    exactly as it did, or twenty call sites change meaning silently."""
    source = tmp_path / "api.json"
    source.write_text(json.dumps({"tools": []}), encoding="utf-8")
    run = intake.intake(
        inputs=[source],
        runs_dir=tmp_path / "runs",
        target_name="t",
        target_interface="i",
        max_rounds=2,
        max_scenarios=128,
        now=NOW,
    )
    manifest = read_json(run.manifest)
    assert manifest["run_id"] == "run-20260814-213000"
    assert [e["artifact_id"] for e in manifest["inputs"]] == ["api-json"]
    assert validate.validate_stage(run, "intake") == []


def test_materialising_a_container_element_writes_canonical_bytes(tmp_path):
    """The digest survey computed must equal the digest of the file written here,
    because refs.check_inputs re-hashes the written bytes.

    A catalogue is written here, unlike the brief's own sketch of this test:
    _container_path resolves the container's location (root + path) from
    00-catalogue.json rather than from materialise's own `source_root`
    argument, precisely so a container under a *different* corpus root than
    the element being admitted still resolves correctly (see
    test_materialising_a_container_element_under_a_second_corpus_root below,
    and the report's discussion of _container_path's signature). Without a
    catalogue on disk, _container_path has nothing to resolve the container
    against -- and in a real run there always is one, because triage and
    intake --run only ever operate on a run survey already populated.
    """
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    records = [{"trace_id": f"tr-{i}", "status": "OK", "spans": []} for i in range(3)]
    (corpus / "capture.json").write_text(json.dumps(records), encoding="utf-8")

    run, stamp = intake.mint_run(tmp_path / "runs", now=NOW)
    run.inputs_dir.mkdir()
    _write_catalogue(
        run,
        corpus_roots=[corpus],
        candidates=[
            {
                "candidate_id": "capture-json",
                "origin": "corpus",
                "path": "capture.json",
                "root_index": 0,
                "bytes": (corpus / "capture.json").stat().st_size,
                "sha256": hashlib.sha256((corpus / "capture.json").read_bytes()).hexdigest(),
                "kind": "trace",
                "admissible": False,
                "digest": {},
            }
        ],
    )
    candidate = {
        "candidate_id": "capture-json-1",
        "origin": "container_element",
        "container": {"candidate_id": "capture-json", "json_pointer": "/1"},
        "bytes": len(canonical_bytes(records[1])),
        "sha256": hashlib.sha256(canonical_bytes(records[1])).hexdigest(),
        "kind": "trace",
        "admissible": True,
        "digest": {},
    }
    entry = intake.materialise(
        run, candidate=candidate, source_root=corpus, artifact_id="capture-json-1"
    )
    written = run.input_file(entry["stored_as"])
    assert written.read_bytes() == canonical_bytes(records[1])
    assert entry["sha256"] == candidate["sha256"]
    assert entry["provenance"] == {
        "container_sha256": entry["provenance"]["container_sha256"],
        "json_pointer": "/1",
    }
    assert len(entry["provenance"]["container_sha256"]) == 64


def test_materialising_a_container_element_under_a_second_corpus_root(tmp_path):
    """_container_path must resolve against the *container's own* root_index,
    not against whatever `source_root` the caller happened to pass in.

    A multi-root survey assigns root_index per corpus root (survey.py's own
    per-root walk_corpus loop), so a container living under corpus_roots[1]
    must still resolve correctly even when materialise's own `source_root`
    argument for *this* admitted element points at corpus_roots[0] -- the two
    need not agree, because the element being admitted and the container it
    was exploded from are two different candidates and may not share a root
    in every survey. Getting this wrong is silent: a naive
    Path(source_root) / container["path"] join would read the wrong file, or
    read no file at all, without raising anything a human would notice.
    """
    root0 = tmp_path / "root0"
    root1 = tmp_path / "root1"
    root0.mkdir()
    root1.mkdir()
    records = [{"trace_id": f"tr-{i}", "status": "OK", "spans": []} for i in range(3)]
    (root1 / "capture.json").write_text(json.dumps(records), encoding="utf-8")

    run, _ = intake.mint_run(tmp_path / "runs", now=NOW)
    run.inputs_dir.mkdir()
    _write_catalogue(
        run,
        corpus_roots=[root0, root1],
        candidates=[
            {
                "candidate_id": "capture-json",
                "origin": "corpus",
                "path": "capture.json",
                "root_index": 1,
                "bytes": (root1 / "capture.json").stat().st_size,
                "sha256": hashlib.sha256((root1 / "capture.json").read_bytes()).hexdigest(),
                "kind": "trace",
                "admissible": False,
                "digest": {},
            }
        ],
    )
    candidate = {
        "candidate_id": "capture-json-1",
        "origin": "container_element",
        "container": {"candidate_id": "capture-json", "json_pointer": "/1"},
        "bytes": len(canonical_bytes(records[1])),
        "sha256": hashlib.sha256(canonical_bytes(records[1])).hexdigest(),
        "kind": "trace",
        "admissible": True,
        "digest": {},
    }
    # source_root deliberately points at root0, which does NOT hold
    # capture.json -- a naive Path(source_root)/container_path join would
    # miss it. Resolution must come from the container's own root_index=1.
    entry = intake.materialise(
        run, candidate=candidate, source_root=root0, artifact_id="capture-json-1"
    )
    written = run.input_file(entry["stored_as"])
    assert written.read_bytes() == canonical_bytes(records[1])


def test_materialising_a_container_element_uses_stored_names_own_fallback(tmp_path):
    """The container branch must derive its filename through the same rule as
    the corpus/projection branch, not a second, unchecked one.

    Before the fix this pins, the container branch wrote
    `f"{artifact_id}.json"` straight to disk with no safety check at all --
    an asymmetry with stored_name(), which falls back to the bare artifact_id
    whenever the *suffixed* name would be an unsafe path segment
    (is_safe_segment rejects any segment containing ".."). An artifact_id
    ending in a single "." (itself a safe segment: one dot, no "..") becomes
    unsafe once ".json" is appended -- "a." + ".json" = "a..json", which
    contains "..". That is exactly the gap the corpus branch already closes
    via stored_name() and the container branch, before this fix, did not.
    """
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    records = [{"trace_id": f"tr-{i}", "status": "OK", "spans": []} for i in range(2)]
    (corpus / "capture.json").write_text(json.dumps(records), encoding="utf-8")

    run, _ = intake.mint_run(tmp_path / "runs", now=NOW)
    run.inputs_dir.mkdir()
    _write_catalogue(
        run,
        corpus_roots=[corpus],
        candidates=[
            {
                "candidate_id": "capture-json",
                "origin": "corpus",
                "path": "capture.json",
                "root_index": 0,
                "bytes": (corpus / "capture.json").stat().st_size,
                "sha256": hashlib.sha256((corpus / "capture.json").read_bytes()).hexdigest(),
                "kind": "trace",
                "admissible": False,
                "digest": {},
            }
        ],
    )
    candidate = {
        "candidate_id": "capture-json-1",
        "origin": "container_element",
        "container": {"candidate_id": "capture-json", "json_pointer": "/1"},
        "bytes": len(canonical_bytes(records[1])),
        "sha256": hashlib.sha256(canonical_bytes(records[1])).hexdigest(),
        "kind": "trace",
        "admissible": True,
        "digest": {},
    }
    # "a." is itself a safe segment (a single dot, no ".."), but suffixing it
    # with ".json" produces "a..json" -- which contains ".." and is therefore
    # unsafe. This is the exact case stored_name()'s fallback exists for.
    suffixed_unsafe_id = "a."
    entry = intake.materialise(
        run, candidate=candidate, source_root=corpus, artifact_id=suffixed_unsafe_id
    )
    # stored_name() itself is the oracle: whatever it would derive for this
    # artifact_id given a ".json"-suffixed source is what materialise must
    # have written -- one rule, asked once, not restated.
    assert entry["stored_as"] == intake.stored_name(suffixed_unsafe_id, Path("x.json"))
    assert entry["stored_as"] == suffixed_unsafe_id  # fallback: no ".json" appended
    assert run.input_file(entry["stored_as"]).read_bytes() == canonical_bytes(records[1])


def test_materialising_a_container_whose_id_does_not_resolve_raises(tmp_path):
    """check_catalogue already reports an unresolvable container reference as
    an ordinary finding; materialise does not need to duplicate that check,
    but it must not silently produce nothing either -- ArtifactError is what
    a caller (admission) can catch and turn into its own refusal.
    """
    run, _ = intake.mint_run(tmp_path / "runs", now=NOW)
    run.inputs_dir.mkdir()
    _write_catalogue(run, corpus_roots=[tmp_path], candidates=[])
    candidate = {
        "candidate_id": "ghost-1",
        "origin": "container_element",
        "container": {"candidate_id": "ghost", "json_pointer": "/0"},
        "bytes": 2,
        "sha256": hashlib.sha256(b"{}").hexdigest(),
        "kind": "other",
        "admissible": True,
        "digest": {},
    }
    with pytest.raises(ArtifactError):
        intake.materialise(run, candidate=candidate, source_root=tmp_path, artifact_id="ghost-1")


def test_materialising_a_container_with_no_path_raises_a_message_that_says_so(tmp_path):
    """The container candidate_id *did* resolve here -- unlike the previous
    test, where it did not -- so the message must say the entry was found and
    malformed, not repeat "no such candidate", which would misdescribe this
    case to whoever reads the ArtifactError.
    """
    run, _ = intake.mint_run(tmp_path / "runs", now=NOW)
    run.inputs_dir.mkdir()
    _write_catalogue(
        run,
        corpus_roots=[tmp_path],
        candidates=[
            {
                "candidate_id": "capture-json",
                "origin": "corpus",
                # no "path" key: a malformed entry, not an absent one.
                "root_index": 0,
                "bytes": 2,
                "sha256": hashlib.sha256(b"{}").hexdigest(),
                "kind": "trace",
                "admissible": False,
                "digest": {},
            }
        ],
    )
    candidate = {
        "candidate_id": "capture-json-1",
        "origin": "container_element",
        "container": {"candidate_id": "capture-json", "json_pointer": "/0"},
        "bytes": 2,
        "sha256": hashlib.sha256(b"{}").hexdigest(),
        "kind": "trace",
        "admissible": True,
        "digest": {},
    }
    with pytest.raises(ArtifactError, match="no path to resolve"):
        intake.materialise(
            run, candidate=candidate, source_root=tmp_path, artifact_id="capture-json-1"
        )


def test_materialising_a_container_with_an_out_of_range_root_index_raises_a_message_that_says_so(
    tmp_path,
):
    """Same shape as the no-path case above: the entry resolved, and its
    root_index is what is wrong, so the message must name that rather than
    falling through to the generic "no such candidate" text.
    """
    run, _ = intake.mint_run(tmp_path / "runs", now=NOW)
    run.inputs_dir.mkdir()
    _write_catalogue(
        run,
        corpus_roots=[tmp_path],  # only one root: index 0
        candidates=[
            {
                "candidate_id": "capture-json",
                "origin": "corpus",
                "path": "capture.json",
                "root_index": 7,  # out of range for a single-root survey
                "bytes": 2,
                "sha256": hashlib.sha256(b"{}").hexdigest(),
                "kind": "trace",
                "admissible": False,
                "digest": {},
            }
        ],
    )
    candidate = {
        "candidate_id": "capture-json-1",
        "origin": "container_element",
        "container": {"candidate_id": "capture-json", "json_pointer": "/0"},
        "bytes": 2,
        "sha256": hashlib.sha256(b"{}").hexdigest(),
        "kind": "trace",
        "admissible": True,
        "digest": {},
    }
    with pytest.raises(ArtifactError, match="invalid root_index"):
        intake.materialise(
            run, candidate=candidate, source_root=tmp_path, artifact_id="capture-json-1"
        )


def test_materialising_a_plain_corpus_file_copies_it_byte_for_byte(tmp_path):
    corpus = tmp_path / "corpus"
    (corpus / "docs").mkdir(parents=True)
    (corpus / "docs" / "notes.md").write_text("# Notes\n", encoding="utf-8")
    run, _ = intake.mint_run(tmp_path / "runs", now=NOW)
    run.inputs_dir.mkdir()
    candidate = {
        "candidate_id": "notes-md",
        "origin": "corpus",
        "path": "docs/notes.md",
        "bytes": 9,
        "sha256": hashlib.sha256(b"# Notes\n").hexdigest(),
        "kind": "design_doc",
        "admissible": True,
        "digest": {},
    }
    entry = intake.materialise(run, candidate=candidate, source_root=corpus, artifact_id="notes-md")
    assert run.input_file(entry["stored_as"]).read_bytes() == b"# Notes\n"
    assert "provenance" not in entry
    assert entry["source_path"].endswith("docs/notes.md")


def test_materialising_a_projection_with_an_absolute_path_is_used_directly(tmp_path):
    """A projection candidate's `path` can be absolute and outside any corpus
    root -- the human manufactured the file, so it is not relative to
    anything survey walked. Path(root) / "/abs/path" happens to return the
    absolute path unchanged in pathlib, but that is an accident of how
    pathlib's `/` operator treats an absolute right-hand side, not a rule
    materialise should rely on implicitly: this test pins the branch that
    checks is_absolute() and uses the path directly, so the behaviour holds
    even if a future refactor stops joining through `/` at all.
    """
    projections_dir = tmp_path / "projections"
    projections_dir.mkdir()
    absolute_source = projections_dir / "manufactured.json"
    absolute_source.write_text('{"joined": true}', encoding="utf-8")

    # source_root points somewhere that does NOT contain manufactured.json --
    # if the absolute path were not honoured directly, a join that ignored
    # is_absolute() would still (by pathlib's accident) resolve correctly, so
    # this test additionally proves the absolute path is used by asserting
    # against content only present at the absolute location.
    unrelated_root = tmp_path / "unrelated"
    unrelated_root.mkdir()

    run, _ = intake.mint_run(tmp_path / "runs", now=NOW)
    run.inputs_dir.mkdir()
    candidate = {
        "candidate_id": "manufactured-json",
        "origin": "projection",
        "path": str(absolute_source),
        "bytes": absolute_source.stat().st_size,
        "sha256": hashlib.sha256(absolute_source.read_bytes()).hexdigest(),
        "kind": "other",
        "admissible": True,
        "digest": {},
        "provenance": {"projection_id": "proj-1", "source_candidate_ids": ["capture-json"]},
    }
    entry = intake.materialise(
        run, candidate=candidate, source_root=unrelated_root, artifact_id="manufactured-json"
    )
    assert run.input_file(entry["stored_as"]).read_bytes() == b'{"joined": true}'
    assert entry["provenance"] == {
        "projection_id": "proj-1",
        "source_candidate_ids": ["capture-json"],
    }


def test_a_manifest_with_provenance_validates(tmp_path):
    """Additive schema change: existing manifests without it stay valid."""
    schema = json.loads((validate.schema_dir() / "manifest-0.1.json").read_text(encoding="utf-8"))
    provenance = schema["properties"]["inputs"]["items"]["properties"]["provenance"]
    assert "provenance" not in schema["properties"]["inputs"]["items"]["required"]
    assert provenance["oneOf"]
