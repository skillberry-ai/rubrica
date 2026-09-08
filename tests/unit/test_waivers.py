import json

import pytest

from rubrica import waivers
from rubrica.artifacts import ArtifactError
from rubrica.errors import UsageError
from rubrica.paths import STAGES, RunPaths


def _run(tmp_path) -> RunPaths:
    (tmp_path / "run-x").mkdir()
    return RunPaths(tmp_path / "run-x")


def _entry(**over):
    """One schema-valid waiver, for a test to break in exactly one place."""
    entry = {
        "id": "wv-0001",
        "check": "claim-utilisation",
        "subject": "llm-agent-py",
        "remedy": "none",
        "reason": "out of target domain",
        "finding_text": "no world-model element cites any claim from llm-agent-py",
        "recorded_at": "2026-09-08T04:12:33Z",
    }
    entry.update(over)
    return entry


def _write(run, *entries):
    run.waivers.write_text(
        json.dumps({"schema_version": "0.1", "waivers": list(entries)}), encoding="utf-8"
    )


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


@pytest.mark.parametrize("bad", ["wv-²", "wv-000²", "wv-００01", "wv-٠٠٠٣", "wv-000٣"])
def test_next_id_counts_no_id_outside_ascii_digits(bad):
    r"""str.isdigit(), str.isdecimal() and re's `\d` are all wider than [0-9], and
    the two failure modes are different in kind.

    U+00B2 (superscript two) is the loud one: isdigit() accepts it and int()
    raises a bare ValueError, which is neither OSError nor UsageError, so it
    escapes cli.py's exit-2 tuple into the catch-all and becomes an exit-1
    [internal] finding -- a malformed *human* artifact reported to the
    orchestrator as a repairable stage defect. isdecimal() closes that one.

    U+FF11 and U+0663 (fullwidth one, Arabic-Indic three) are the quiet one, and
    isdecimal() does NOT close them: isdecimal() and int() both accept them, so
    no amount of guarding int() helps. `wv-١٢` would be counted as 12 -- a number
    no ASCII digit-by-digit reading of the id contains. paths.py's _ROUND_PART
    records this as a ruling for round directories; a waiver id is the same class.

    The last case puts U+0663 in the *tail*, where `\Awv-([0-9]{4,})\Z` refuses it
    and the meaning-preserving-looking `\Awv-(\d{4,})\Z` would not. That is what
    makes the explicit [0-9] class load-bearing rather than stylistic, so it is
    pinned here.
    """
    assert waivers.next_id([{"id": bad}]) == "wv-0001"


def test_a_waiver_missing_a_required_field_is_a_usage_error(tmp_path):
    """Schema-validated in the consumer, because nothing else validates this file.

    It is outside STAGE_ARTIFACTS by design, so no `validate --stage X` reaches
    it, and `rubrica waive`'s checks are bypassed by exactly the hand-edit that
    revokes a waiver. UsageError rather than a finding for smoke.load_agents'
    reason: a person wrote this file, so there is no stage to repair.
    """
    run = _run(tmp_path)
    entry = _entry()
    del entry["reason"]
    _write(run, entry)
    with pytest.raises(UsageError) as caught:
        waivers.load(run)
    # The message must name the field, or a human cannot find what to edit.
    assert "reason" in str(caught.value)


def test_a_remedy_the_schema_rejects_is_a_usage_error(tmp_path):
    """An empty remedy, which `minLength: 1` refuses.

    Deliberately not `remedy: "banana"`: waivers-0.1.json types `remedy` as a
    bare string on purpose -- the choices are paths.STAGES plus two sentinels and
    STAGES grows, so the enum lives in `rubrica waive` rather than in the schema.
    Measured: a document carrying `remedy: "banana"` validates clean, so this test
    pins what the schema does refuse rather than asserting a check it does not
    make. See the fix report for the ruling that gap is owed.
    """
    run = _run(tmp_path)
    _write(run, _entry(remedy=""))
    with pytest.raises(UsageError) as caught:
        waivers.load(run)
    assert "remedy" in str(caught.value)


def test_a_valid_document_still_loads_after_validation(tmp_path):
    """The other half of the two above: the gate does not reject the good case."""
    run = _run(tmp_path)
    _write(run, _entry())
    assert [entry["id"] for entry in waivers.load(run)] == ["wv-0001"]
