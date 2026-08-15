"""Task 19: `set-limit`, so a manifest limit change carries its reason.

Design spec section 10's error 4: a hand edit of `max_scenarios` had left no
trace of who changed it or why, and was read as an unexplained discrepancy
because every mechanism got checked before the person. `set_limit` is the
replacement for that hand edit -- it writes the same field, but a reason is
mandatory and lands in decisions.md alongside the old and new value.
"""

from __future__ import annotations

import pytest

from rubrica.artifacts import read_json, write_json
from rubrica.cli import main
from rubrica.errors import UsageError
from rubrica.manifest import set_limit
from rubrica.validate import validate_stage
from tests.toy import build_toy_run


def test_setting_a_limit_records_the_reason_in_decisions(tmp_path):
    """§10 error 4: a hand edit of max_scenarios was read as an unexplained
    discrepancy because every mechanism was checked except the person."""
    run = build_toy_run(tmp_path / "runs", upto="intake")
    before = read_json(run.manifest)["limits"]["max_scenarios"]

    set_limit(
        run,
        max_scenarios=32,
        reason="probing a small corpus; the ceiling was set for a real target",
    )

    after = read_json(run.manifest)
    assert after["limits"]["max_scenarios"] == 32
    decisions_text = run.decisions.read_text()
    assert "probing a small corpus" in decisions_text
    assert str(before) in decisions_text
    assert "32" in decisions_text


def test_a_reason_is_required_and_may_not_be_blank(tmp_path):
    """A limit change with no reason is the hand edit this replaces."""
    run = build_toy_run(tmp_path / "runs", upto="intake")

    with pytest.raises(UsageError):
        set_limit(run, max_scenarios=32, reason="")

    with pytest.raises(UsageError):
        set_limit(run, max_scenarios=32, reason="   ")


def test_setting_neither_limit_is_a_usage_error(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="intake")

    with pytest.raises(UsageError):
        set_limit(run, reason="no limit named, so nothing to do")


def test_a_reason_with_a_newline_is_a_usage_error(tmp_path):
    """Mirrors `decide`'s own rule: decisions.md is one entry per line, and
    append_decision only strips a *trailing* newline, so an embedded one would
    split the entry across two physical lines."""
    run = build_toy_run(tmp_path / "runs", upto="intake")

    with pytest.raises(UsageError):
        set_limit(run, max_scenarios=32, reason="two lines\nof reasoning")


def test_the_manifest_still_validates_after_the_change(tmp_path):
    run = build_toy_run(tmp_path / "runs", upto="intake")

    set_limit(run, max_rounds=1, max_scenarios=16, reason="a cheap probe run")

    assert validate_stage(run, "intake") == []


@pytest.mark.parametrize(
    ("kwargs", "label"),
    [
        ({"max_scenarios": 0}, "max_scenarios 0"),
        ({"max_rounds": 0}, "max_rounds 0"),
        ({"max_rounds": -3}, "max_rounds negative"),
        ({"max_scenarios": -1}, "max_scenarios negative"),
        ({"max_rounds": 2.5}, "max_rounds a float"),
        ({"max_scenarios": "16"}, "max_scenarios a string"),
        ({"max_rounds": True}, "max_rounds a bool"),
    ],
)
def test_a_limit_the_schema_would_reject_is_refused_before_it_is_written(tmp_path, kwargs, label):
    """set_limit validated `reason` thoroughly and never validated the integers.

    Measured: `set-limit --max-scenarios 0 --max-rounds -3` exited 0, wrote both
    values, and appended a decisions.md line announcing the change -- leaving a
    manifest that `validate` then rejects with two findings. That is the exact
    misdirection intake()'s and record_stage()'s own argument checks exist to
    prevent, and both carry comments explaining it at length: a bad orchestrator
    argument surfacing as a finding against manifest.json, an artifact no skill
    wrote and no repair prompt can fix.

    The float, string and bool cases are here because set_limit is a library
    function too -- argparse's `type=int` protects the CLI only, and
    `isinstance(True, int)` is True in Python, so `max_rounds=True` would write
    JSON `true`, which the schema rejects for its *type* rather than its value.
    """
    run = build_toy_run(tmp_path / "runs", upto="intake")
    before = read_json(run.manifest)["limits"]
    decisions_before = run.decisions.read_text() if run.decisions.exists() else ""

    with pytest.raises(UsageError, match="integer >= 1"):
        set_limit(run, reason="a reason good enough that only the limit is wrong", **kwargs)

    # Nothing written, either file: the refusal is before the first write.
    assert read_json(run.manifest)["limits"] == before, label
    after = run.decisions.read_text() if run.decisions.exists() else ""
    assert after == decisions_before, "a refused change must not leave a decisions.md line"
    assert validate_stage(run, "intake") == []


def test_a_corrupt_limits_block_is_a_usage_error_not_a_fabricated_finding(tmp_path):
    """The guard `record_stage` already applies to `manifest.stages`.

    `dict(manifest.get("limits") or {})` raises ValueError on a present-but-not-a-
    mapping limits, which cli.py's set-limit handler does not catch -- so it fell
    through to the catch-all and became exit 1 with a fabricated `[internal]`
    finding, telling the orchestrator to repair a stage when the manifest itself
    is corrupt. A falsy non-mapping is worse than that rather than better: it
    would be silently discarded and the limit this call was asked to leave alone
    would vanish.
    """
    run = build_toy_run(tmp_path / "runs", upto="intake")
    manifest = read_json(run.manifest)
    manifest["limits"] = "nope"
    write_json(run.manifest, manifest)

    with pytest.raises(UsageError, match="corrupt"):
        set_limit(run, max_scenarios=32, reason="the manifest is what is wrong here")


def test_a_corrupt_limits_block_reaches_the_cli_as_exit_two(tmp_path, capsys):
    """The exit code the test above protects: 2, not 1. A stage defect must never
    surface as 2 and its mirror holds too -- a corrupt manifest is the harness
    pointed at something it cannot act on, and no repair prompt fixes it."""
    run = build_toy_run(tmp_path / "runs", upto="intake")
    manifest = read_json(run.manifest)
    manifest["limits"] = ["nope"]
    write_json(run.manifest, manifest)

    code = main(["set-limit", "--run", str(run.root), "--max-scenarios", "32", "--reason", "r"])

    assert code == 2
    assert "corrupt" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv_limit", [["--max-scenarios", "0"], ["--max-rounds", "-3"], ["--max-rounds", "0"]]
)
def test_the_cli_refuses_an_out_of_range_limit_at_exit_two(tmp_path, argv_limit, capsys):
    """Exit 2, on stderr: these are the orchestrator's own arguments, so a bad
    one is a misconfigured harness rather than a repairable stage defect -- the
    same ruling cli.py's set-limit arm already applies to a blank --reason."""
    run = build_toy_run(tmp_path / "runs", upto="intake")
    before = read_json(run.manifest)["limits"]

    code = main(["set-limit", "--run", str(run.root), *argv_limit, "--reason", "probing"])

    assert code == 2
    assert "integer >= 1" in capsys.readouterr().err
    assert read_json(run.manifest)["limits"] == before
