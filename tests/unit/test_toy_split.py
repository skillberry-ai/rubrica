"""build_toy_run's staged-triage checkpoints, and the multi-slice fixture.

The rest of the suite reaches the triage family only through hand-written
parts (tests/unit/test_seal.py's `_staged_run`). These tests cover the shared
fixture builder instead: the five new `upto` checkpoints, and the two slicing
paths the toy world can be put on -- one slice at the default cap, more than
one at a cap small enough to make the slicer actually partition.

Both paths are exercised deliberately. The golden catalogue is 4102 row-bytes
against `DEFAULT_SLICE_BYTES` (65536), so at the default cap the fan-out is a
single member and every "one part per slice" property holds trivially. A
fixture that only ever ran multi-slice would stop covering the shape every
existing test sees, and one that only ever ran single-slice would leave the
fan-out unexercised -- so each has its own test here.
"""

from __future__ import annotations

import pytest

from rubrica import refs, seal, validate
from rubrica.artifacts import read_json
from tests.toy import ARTIFACT_IDS, build_toy_catalogue_and_triage, build_toy_run

# The artifact that the *next* pass writes, for each new checkpoint. Asserting
# it is absent is the half that shows the checkpoint actually stopped where it
# says: a test that only validated the requested stage's own output would pass
# just as well against a build_toy_run that ignored `upto` and wrote the whole
# family every time -- which is exactly the silent acceptance _UPTO_STAGES
# exists to make impossible.
_NEXT_PASS_WRITES = {
    "triage-slices": "objective",
    "triage-objective": "dispositions_dir",
    "triage-rule": "audit",
    "triage-audit": "triage",
    # The seal is the family's last pass; what must not exist after it is the
    # manifest, because intake is what runs next and gate 0 stands in between.
    "triage-seal": "manifest",
}


@pytest.mark.parametrize("upto", list(_NEXT_PASS_WRITES))
def test_each_new_checkpoint_stops_where_it_says(tmp_path, upto):
    run = build_toy_run(tmp_path / "runs", upto=upto)
    assert validate.validate_stage(run, upto) == []
    unreached = getattr(run, _NEXT_PASS_WRITES[upto])
    assert not unreached.exists(), f"{upto} left {unreached.name} behind"
    # Every triage checkpoint is upstream of intake, so none of them may mint
    # a manifest or 00-inputs/: a family checkpoint that had been through
    # intake would be a run one gate past where it claims to stop.
    assert not run.manifest.exists()
    assert not run.inputs_dir.exists()


def test_the_multi_slice_fixture_actually_fans_out(tmp_path):
    """The golden catalogue is small enough to be one slice, which leaves the
    fan-out unexercised by the toy world -- so the builder overrides the cap
    and drives the real slicer rather than hand-writing a plan.

    4096, not the brief's 1024: `write_slices` refuses any candidate whose own
    row exceeds the cap (no splitter can shrink a single row), and the golden
    rows are api-json 2381, notes-md 1303, trace-json 418 -- so 1024 trips on
    two of the three and 2048 on one. 4096 is the smallest round cap above the
    largest row, and it partitions the three candidates into two slices.
    """
    run = build_toy_run(tmp_path / "runs", upto="triage-seal", slice_cap=4096)
    plan = read_json(run.slices)["slices"]
    assert len(plan) > 1
    assert len(list(run.dispositions_dir.iterdir())) == len(plan)
    assert refs.check_all(run) == []


def test_the_default_cap_leaves_the_toy_world_a_single_slice(tmp_path):
    """The other slicing path, and the reason `slice_cap` has to exist at all:
    at DEFAULT_SLICE_BYTES the whole toy catalogue fits in one slice, so the
    single-member fan-out is what every other fixture in the suite sees."""
    run = build_toy_run(tmp_path / "runs", upto="triage-seal")
    plan = read_json(run.slices)["slices"]
    assert len(plan) == 1
    assert len(list(run.dispositions_dir.iterdir())) == 1
    assert refs.check_all(run) == []


def test_a_slice_cap_on_a_run_that_never_slices_is_refused(tmp_path):
    """`slice_cap` reaches the slicer or it reaches nothing -- a caller passing
    it with a post-intake checkpoint has asked for a cap on a run that has no
    catalogue to partition, and silently ignoring it would hand them a run
    they think was sliced differently from the way it was."""
    with pytest.raises(ValueError):
        build_toy_run(tmp_path / "runs", upto="reconcile", slice_cap=4096)


def test_the_sealed_toy_record_is_what_the_old_builder_produced(tmp_path):
    """The seal's output must be a record the rest of the pipeline already
    accepts, or every downstream fixture silently changes meaning."""
    run = build_toy_run(tmp_path / "runs", upto="triage-seal")
    record = read_json(run.triage)
    assert set(record) >= {
        "schema_version",
        "run_id",
        "objective_review",
        "dispositions",
        "deficiencies",
        "projections",
    }
    assert validate.validate_stage(run, "triage-seal") == []
    assert [d["candidate_id"] for d in record["dispositions"]] != []
    assert {d["candidate_id"] for d in record["dispositions"]} == set(ARTIFACT_IDS)


def test_the_catalogue_helper_seals_rather_than_hand_writing_the_record(tmp_path):
    """build_toy_catalogue_and_triage's 00-triage.json comes from seal.seal
    over staged parts it also writes, not from a literal in the fixture: a
    hand-written record only ever satisfies a check that was not looking, and
    a re-seal proves the one on disk is what the real code assembles.
    """
    run = build_toy_run(tmp_path / "runs")
    build_toy_catalogue_and_triage(run)
    assert run.objective.is_file()
    assert run.audit.is_file()
    assert list(run.dispositions_dir.iterdir())
    before = run.triage.read_bytes()
    path, findings = seal.seal(run)
    assert findings == []
    assert path == run.triage
    assert run.triage.read_bytes() == before
    assert refs.check_all(run) == []
