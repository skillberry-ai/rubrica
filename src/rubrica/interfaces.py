"""One service's OpenAPI document, derived from the tool contract it must preserve.

Code rather than a prompt, on `emit`'s argument: the document is a pure function
of the tool contract, so two runs with identical groupings must produce
byte-identical documents. Otherwise a difference in an emitted lab can no longer
be attributed to a stage, which is the property the whole measurement rests on.
"""

from __future__ import annotations

import re

# The predicate a tool name must satisfy for the harness to return it unchanged,
# which is what "the agent's tool contract is preserved" reduces to.
#
# NOT the harness's character class. simulation_harness.openapi.parser's
# sanitize_operation_id replaces every character outside [a-zA-Z0-9_-] with `_`,
# caps the result at 64, *and* strips leading and trailing `_` and `-` -- twice,
# once before the cap and once after. So `_query_tickets` matches the character
# class and is still rewritten to `query_tickets`: the agent would call a name the
# simulator does not serve, and nothing downstream would say so. Hence the
# anchored first and last character.
#
# Restated here rather than imported, because Rubrica takes no dependency on
# simulation-harness -- whether the harness accepts a document is the harness's
# test, not ours. The cost is that the two can drift, and the mirror of this
# constant in interface-0.1.json is held equal to it by
# tests/unit/test_interfaces.py.
TOOL_NAME_PATTERN = r"\A[a-zA-Z0-9](?:[a-zA-Z0-9_-]{0,62}[a-zA-Z0-9])?\Z"
TOOL_NAME = re.compile(TOOL_NAME_PATTERN)
