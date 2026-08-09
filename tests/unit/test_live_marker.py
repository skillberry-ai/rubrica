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
    out = _run_pytest(tmp_path, {"TESTGEN_LIVE": ""})
    assert "1 skipped" in out, out
    assert "1 passed" not in out, out


def test_the_same_test_runs_with_the_opt_in(tmp_path):
    """The other direction, and the one that makes the first meaningful: without
    it, a marker that skipped unconditionally would satisfy the test above --
    and a live suite nothing can ever run is ornamental.
    """
    out = _run_pytest(tmp_path, {"TESTGEN_LIVE": "1"})
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
            env={**os.environ, "TESTGEN_LIVE": ""},
        ).stdout
    finally:
        target.unlink(missing_ok=True)
    assert LIVE_ENV in out, out
    assert "make live" in out, out
