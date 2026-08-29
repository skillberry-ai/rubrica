"""The tool-name survival predicate, and the one place it is defined."""

from __future__ import annotations

import json
import re
from pathlib import Path

from rubrica.interfaces import TOOL_NAME, TOOL_NAME_PATTERN

_SCHEMA_DIR = Path(__file__).parents[2] / "src/rubrica/schema"


def test_the_predicate_admits_a_name_the_harness_returns_unchanged():
    assert TOOL_NAME.match("query_tickets")
    assert TOOL_NAME.match("a")
    assert TOOL_NAME.match("a" * 64)
    assert TOOL_NAME.match("get-ticket_2")


def test_the_predicate_rejects_a_leading_separator_the_character_class_admits():
    """The case the character class alone waves through, and the reason this
    predicate is not `^[a-zA-Z0-9_-]{1,64}$`.

    sanitize_operation_id replaces out-of-class characters with `_`, caps at 64,
    *and* strips leading and trailing `_` and `-` -- twice, before and after the
    cap. So `_query_tickets` matches the character class and is still rewritten to
    `query_tickets`, which is a silently broken tool contract: the agent calls a
    name the simulator does not serve. This is the regression test for that.
    """
    assert not TOOL_NAME.match("_query_tickets")
    assert not TOOL_NAME.match("query_tickets_")
    assert not TOOL_NAME.match("-query")
    assert not TOOL_NAME.match("query-")
    assert not TOOL_NAME.match("_")


def test_the_predicate_rejects_an_out_of_class_character_and_an_over_long_name():
    assert not TOOL_NAME.match("query/tickets")
    assert not TOOL_NAME.match("query tickets")
    assert not TOOL_NAME.match("a" * 65)


def test_the_schema_pattern_and_the_python_constant_are_the_same_predicate():
    """Two homes for one rule, and a test instead of an import.

    A JSON Schema cannot import a Python constant, so the pattern is stated twice
    -- once in interface-0.1.json, once in interfaces.py. That is a genuine
    duplication, and this is what stops it becoming a drift: change one and this
    goes red naming both.
    """
    schema = json.loads((_SCHEMA_DIR / "interface-0.1.json").read_text(encoding="utf-8"))
    pattern = schema["$defs"]["operation"]["properties"]["operationId"]["pattern"]
    assert pattern == TOOL_NAME_PATTERN, (
        f"interface-0.1.json pins {pattern!r} and interfaces.py pins "
        f"{TOOL_NAME_PATTERN!r}; they must be the same predicate"
    )
    # Compiled as well as compared: a pattern that is equal but not valid Python
    # regex would pass the comparison and fail at first use.
    assert re.compile(pattern).match("query_tickets")
