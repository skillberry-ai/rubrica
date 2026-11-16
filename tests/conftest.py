"""Shared pytest configuration: the live marker and its default skip.

A live test checks a recording of a real model run that is committed in the
repo. Running it dispatches nothing and costs nothing. Making a new recording
is what dispatches a model and costs money. Live tests are skipped unless
RUBRICA_LIVE is set. The skip message names the command that runs them,
because a marker nobody can find is a suite that does not exist.
"""

from __future__ import annotations

import os

import pytest

LIVE_ENV = "RUBRICA_LIVE"
LIVE_SKIP_REASON = (
    "live test: asserts against committed recordings (free; re-recording costs money). "
    f"Run with `{LIVE_ENV}=1 make live`, or "
    f"`{LIVE_ENV}=1 uv run pytest -m live`."
)

# Spellings that mean "off". Live tests are opt-in (and re-recording spends
# money), so treating *any* non-empty string as "on" -- os.environ.get(...) alone is
# truthy for "0" and "false" -- would make `RUBRICA_LIVE=0`, typed by someone
# who means "off", opt IN instead. Checked case-insensitively and stripped, so
# whitespace or capitalization cannot smuggle a value past the comparison.
_LIVE_OFF_SPELLINGS = frozenset({"", "0", "false", "no"})


def _live_opted_in() -> bool:
    """Whether RUBRICA_LIVE's value means "on" rather than "off".

    Unset counts as "" (off): os.environ.get returns None with no default, and
    None is not a string _LIVE_OFF_SPELLINGS can be asked about.
    """
    raw = os.environ.get(LIVE_ENV, "")
    return raw.strip().lower() not in _LIVE_OFF_SPELLINGS


def pytest_collection_modifyitems(config, items):
    if _live_opted_in():
        return
    skip = pytest.mark.skip(reason=LIVE_SKIP_REASON)
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
