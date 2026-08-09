"""Shared pytest configuration: the live marker and its default skip.

A live test dispatches a model. It costs money, it is not deterministic, and it
needs credentials, so it is skipped unless TESTGEN_LIVE is set. The skip
message names the command that runs it, because a marker nobody can find is a
suite that does not exist.
"""

from __future__ import annotations

import os

import pytest

LIVE_ENV = "TESTGEN_LIVE"
LIVE_SKIP_REASON = (
    f"live test: dispatches a model. Run with `{LIVE_ENV}=1 make live`, or "
    f"`{LIVE_ENV}=1 uv run pytest -m live`."
)


def pytest_collection_modifyitems(config, items):
    if os.environ.get(LIVE_ENV):
        return
    skip = pytest.mark.skip(reason=LIVE_SKIP_REASON)
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
