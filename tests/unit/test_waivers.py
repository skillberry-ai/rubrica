import json

import pytest

from rubrica import waivers
from rubrica.artifacts import ArtifactError
from rubrica.paths import STAGES, RunPaths


def _run(tmp_path) -> RunPaths:
    (tmp_path / "run-x").mkdir()
    return RunPaths(tmp_path / "run-x")


def test_an_absent_file_is_no_waivers(tmp_path):
    """The common case. Most runs never record one, and that is not a defect."""
    assert waivers.load(_run(tmp_path)) == []


def test_a_recorded_waiver_loads(tmp_path):
    run = _run(tmp_path)
    run.waivers.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "waivers": [
                    {
                        "id": "wv-0001",
                        "check": "claim-utilisation",
                        "subject": "llm-agent-py",
                        "remedy": "triage-rule",
                        "reason": "out of target domain",
                        "finding_text": "no world-model element cites any claim from llm-agent-py",
                        "recorded_at": "2026-09-08T04:12:33Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert waived_ids(run) == {"llm-agent-py"}


def waived_ids(run):
    return set(waivers.waived_subjects(run, "claim-utilisation"))


def test_a_waiver_for_another_check_does_not_leak(tmp_path):
    """The property that keeps a waiver narrow: subjects are per check."""
    run = _run(tmp_path)
    run.waivers.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "waivers": [
                    {
                        "id": "wv-0001",
                        "check": "some-other-check",
                        "subject": "llm-agent-py",
                        "remedy": "none",
                        "reason": "r",
                        "finding_text": "t",
                        "recorded_at": "2026-09-08T04:12:33Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert waived_ids(run) == set()


def test_a_malformed_document_raises_rather_than_failing_open(tmp_path):
    """Loud, not safe-by-accident. Failing open would hide a corrupted human
    record behind a gate that then looks correct."""
    run = _run(tmp_path)
    run.waivers.write_text("[]", encoding="utf-8")
    with pytest.raises(ArtifactError):
        waivers.load(run)


def test_a_non_object_entry_raises(tmp_path):
    run = _run(tmp_path)
    run.waivers.write_text(
        json.dumps({"schema_version": "0.1", "waivers": ["nope"]}), encoding="utf-8"
    )
    with pytest.raises(ArtifactError):
        waivers.load(run)


def test_a_document_without_the_waivers_array_raises(tmp_path):
    """The likeliest hand-produced shape: the wrapper key forgotten. It reaches
    the same raise as a malformed root rather than reading as "no waivers"."""
    run = _run(tmp_path)
    run.waivers.write_text(json.dumps({"schema_version": "0.1"}), encoding="utf-8")
    with pytest.raises(ArtifactError):
        waivers.load(run)


def test_next_id_is_one_past_the_highest_even_with_a_gap(tmp_path):
    """A gap in the sequence must not remint an id already used, which is what
    len(entries) + 1 would do after a human deleted a middle entry."""
    entries = [{"id": "wv-0001"}, {"id": "wv-0007"}]
    assert waivers.next_id(entries) == "wv-0008"


def test_next_id_starts_at_one(tmp_path):
    assert waivers.next_id([]) == "wv-0001"


def test_every_stage_is_a_remedy_and_so_are_the_two_sentinels():
    """`none` has to exist or the ruling this exists for is inexpressible: a
    human who believes no artifact should change must not be made to name a
    remedy they do not believe in."""
    choices = waivers.remedy_choices()
    assert set(choices) == set(STAGES) | {"outside-the-run", "none"}
    # Kept as its own line even though the equality above covers it: `none` is
    # the editorial point of the docstring, not just one more member.
    assert "none" in choices


def test_the_registry_names_what_a_subject_is():
    """A check absent from the registry is not waivable, and the value is what
    lets the CLI say what a subject means rather than just rejecting one."""
    assert waivers.WAIVABLE_CHECKS["claim-utilisation"] == "artifact_id"
