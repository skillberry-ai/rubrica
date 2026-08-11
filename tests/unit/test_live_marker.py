"""The live marker exists, is registered, and is skipped by default.

A live test is one that dispatches a model. It cannot run in CI, and a marker
nobody can find is a suite that does not exist -- so this file pins that the
marker is registered (an unregistered marker is a ruff/pytest warning, not an
error, and would silently do nothing) and that the skip message names the
command that runs it.
"""

from __future__ import annotations

import subprocess
import sys

import pytest


def test_the_live_marker_is_registered():
    """An unregistered marker still applies but warns, and `--strict-markers`
    would then fail the whole run. Registered means both work.
    """
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--markers"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "@pytest.mark.live" in out


LIVE_TEST = """\
import pytest


@pytest.mark.live
def test_marked_live():
    assert True
"""


def _run_pytest(tmp_path, env_extra):
    """Run pytest over a generated test file, with the repo's conftest in scope.

    A subprocess rather than pytester: this project has no pytester dependency,
    and the property under test is the default *collection* behaviour, which is
    exactly what an in-process run would not reproduce faithfully.

    rootdir is the repository, so tests/conftest.py applies -- the file under
    test is written into the repo's own tests/ tree under a tmp-derived name and
    removed afterwards.
    """
    import os
    from pathlib import Path

    target = Path("tests") / f"test_generated_{tmp_path.name}.py"
    target.write_text(LIVE_TEST, encoding="utf-8")
    try:
        return subprocess.run(
            [sys.executable, "-m", "pytest", str(target), "-q", "-p", "no:cacheprovider"],
            capture_output=True,
            text=True,
            env={**os.environ, **env_extra},
        ).stdout
    finally:
        target.unlink(missing_ok=True)


def test_a_live_test_is_skipped_without_the_opt_in(tmp_path):
    out = _run_pytest(tmp_path, {"RUBRICA_LIVE": ""})
    assert "1 skipped" in out, out
    assert "1 passed" not in out, out


def test_the_same_test_runs_with_the_opt_in(tmp_path):
    """The other direction, and the one that makes the first meaningful: without
    it, a marker that skipped unconditionally would satisfy the test above --
    and a live suite nothing can ever run is ornamental.
    """
    out = _run_pytest(tmp_path, {"RUBRICA_LIVE": "1"})
    assert "1 passed" in out, out


@pytest.mark.parametrize("value", ["0", "false", "no", "", "FALSE", " No "])
def test_falsy_spellings_of_rubrica_live_stay_off(tmp_path, value):
    """os.environ.get(...) alone is truthy for any non-empty string, so a naive
    check would make RUBRICA_LIVE=0 -- typed by someone who means "off" --
    opt IN and dispatch (and bill for) exactly the model call they meant to
    prevent. Every one of these spellings must still skip; case and
    surrounding whitespace must not change the answer.
    """
    out = _run_pytest(tmp_path, {"RUBRICA_LIVE": value})
    assert "1 skipped" in out, out
    assert "1 passed" not in out, out


@pytest.mark.parametrize("value", ["1", "true", "yes"])
def test_other_truthy_spellings_opt_in_too(tmp_path, value):
    """Not just "1" -- anything that is not a recognized off-spelling opts in,
    so the common words people actually type ("true", "yes") must work too.
    """
    out = _run_pytest(tmp_path, {"RUBRICA_LIVE": value})
    assert "1 passed" in out, out


def test_the_skip_reason_names_the_command_that_runs_it(tmp_path):
    """A marker nobody can find is a suite that does not exist. `-rs` prints the
    skip reasons, so the reason string is checkable rather than aspirational.
    """
    import os
    from pathlib import Path

    from tests.conftest import LIVE_ENV

    target = Path("tests") / f"test_generated_reason_{tmp_path.name}.py"
    target.write_text(LIVE_TEST, encoding="utf-8")
    try:
        out = subprocess.run(
            [sys.executable, "-m", "pytest", str(target), "-rs", "-q", "-p", "no:cacheprovider"],
            capture_output=True,
            text=True,
            env={**os.environ, "RUBRICA_LIVE": ""},
        ).stdout
    finally:
        target.unlink(missing_ok=True)
    assert LIVE_ENV in out, out
    assert "make live" in out, out
