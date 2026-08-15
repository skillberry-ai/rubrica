"""Task 19: `set-limit`, so a manifest limit change carries its reason.

Design spec section 10's error 4: a hand edit of `max_scenarios` had left no
trace of who changed it or why, and was read as an unexplained discrepancy
because every mechanism got checked before the person. `set_limit` is the
replacement for that hand edit -- it writes the same field, but a reason is
mandatory and lands in decisions.md alongside the old and new value.
"""

from __future__ import annotations

import pytest

from rubrica.artifacts import read_json
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
