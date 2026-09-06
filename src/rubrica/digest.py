"""One bounded digest per candidate: the only thing triage ever reads.

This module is the design's single point of failure and is written knowing it.
Triage's `reads` is the catalogue alone, so a fact absent from a digest is a
fact triage does not have -- and the generator is code that cannot know what
matters about a target it has never seen.

Completeness is unreachable, so the mitigation is honesty instead:
`heuristics_fired` records which extractors actually found something. A triage
that cannot rule on a candidate declines it `digest_insufficient` and names the
field it needed, which turns this module's blindness into a finding a human
reads at gate 0 rather than a silent bad selection.

Every field here is anchored to a decision the 2026-08-13 development run made
by hand -- a full-pipeline run over a large real-world corpus, referred to
throughout this module as "the development corpus". If a new field cannot be
traced to a decision somebody actually took, it is weight in a barrier's
context window and does not belong.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

# Named so a skill can cite them and a test can prove each is reachable.
TRACE_HEURISTICS: tuple[str, ...] = (
    "status",
    "element_counts",
    "request_text",
    "names",
    "error_markers",
)

_STATUS_KEYS = ("status", "state", "outcome")
_COUNT_KEYS = ("spans", "steps", "messages", "events", "turns", "calls")
_REQUEST_KEYS = ("question", "request_preview", "input", "request", "query", "prompt")
_NAME_KEYS = ("name", "tool", "tool_name", "tools_called", "operation")
_ERROR_KEYS = ("error", "exception", "traceback", "stack_trace")
# Substrings checked against string *values* regardless of their key -- the
# development corpus's traces carry the failure as "TraceStatus.ERROR", not
# under a key named "error", so a key-name-only check misses the exact fact t7
# was kept for.
_ERROR_SUBSTRINGS = ("exception", "error")
_SKELETON_DEPTH = 3
# What `_source_digest` actually has a parser for. `intake._SOURCE_SUFFIXES`
# classifies eight languages as `source_code`, which is true of the files; this is
# the one whose grammar `ast` reads. Measured on the parsec corpus
# (run-20260826-090456): 135 of 135 `.py` candidates parsed and 0 of 5 `.js` did --
# a split falling exactly on the language boundary, which is not something file
# contents do. The cause is the language and not the characters: four of those
# five files name a unicode character in their SyntaxError, but pure-ASCII
# JavaScript fails `ast.parse` identically, so a fix aimed at the unicode would
# leave the defect intact. This set grows only when a parser for that language
# lands; until then its suffix takes the prose route below.
_PARSEABLE_SUFFIXES = {".py"}
_MAX_NAMES = 64
# The development corpus carries a 1191-key pricing table as one JSON file
# (classified "other"). Recursing into every key produced a
# 783KB digest for that single candidate -- measured, not assumed. The "keys"
# list below was already capped at this width for display; recursion now
# matches it, so a wide dict costs the same whether it has ten entries or a
# thousand.
#
# Two consumers now, and a tuning for one is a change to the other: the skeleton
# walk above, and `is_message_list`, where this is the distinct-role ceiling and
# therefore part of what does and does not classify as a chat trajectory. The
# boundary test for that ceiling is parameterised by this constant, so it would
# follow a retune silently rather than object to it -- retuning for digest bytes
# means re-measuring the classification, not only the digest.
_SKELETON_MAX_CHILDREN = 32
# Total pointers a skeleton may hold, not just children per node. _SKELETON_DEPTH
# and _SKELETON_MAX_CHILDREN bound breadth and depth *per node*, which leaves the
# product unbounded: measured, a 2.7MB pricing table yielded 261 pointers and a
# 39,162-byte candidate row -- 6.8% of the parsec candidates array in one entry.
# A slice's byte cap cannot be enforced if a single row can exceed it, so this is
# a precondition for the fan-out and not a tidying. 128 binds on exactly one of
# the 209 skeleton digests measured across four real catalogues (that pricing
# file) and leaves tau2's 69-pointer trajectory digests whole.
_SKELETON_MAX_NODES = 128
# How much of a role name an `element_counts` key may spell.
# `_SKELETON_MAX_CHILDREN` bounds how *many* role keys a message-list digest can
# have; nothing bounded how long one is, because the key is built by
# interpolating the role verbatim. Measured on a payload `is_message_list`
# admits -- 32 records with 3,000-character `role` values plus a `content` key --
# the trace digest is 96,514 bytes against 248 for the skeleton the same payload
# got before this branch, so it clears `slices.DEFAULT_SLICE_BYTES` (65,536) and
# `survey`'s oversized-row check exits 2 for the whole corpus. A key-count bound
# is not a byte bound.
#
# 64 is measured against the vocabulary rather than against the cap: tau2's 200
# trajectories use exactly four roles -- `assistant`, `system`, `tool`, `user` --
# and the longest is `assistant` at 9 characters. 64 therefore never binds on any
# dialogue this was measured on and still leaves room for a longer convention
# (a namespaced `agent.planner.tool_result`), while holding the whole field to
# 33 keys of at most 69 characters.
_MAX_ROLE_CHARS = 64

# The character bound `_MAX_NAMES` was missing. That cap is on *entries*, so a
# candidate with verbose names produced a row larger than one slice and made
# `survey` exit 2 on the whole corpus -- measured end-to-end at 80,549 bytes
# against the 65,536-byte cap, from a file that digests to 433 bytes as a
# skeleton.
#
# Justified against the real vocabulary rather than against the slice cap, which
# is how `_MAX_ROLE_CHARS` is justified: the longest name in any corpus on this
# pod is `query_tickets.find_tickets` at 26 characters, and tau2's are ordinary
# identifiers such as `get_reservation_details` at 23. 128 is ~4.9x the longest
# observed, which leaves room for the shapes that legitimately compose -- a
# dotted path, or a server-prefixed MCP tool name -- rather than pinning the cap
# to today's sample. The arithmetic in the other direction is what makes it safe:
# `_MAX_NAMES` * `_MAX_NAME_CHARS` is 64 * 128 = 8,192 bytes of names in the worst
# case, an eighth of one slice, so this field can no longer be the reason a row
# is refused.
_MAX_NAME_CHARS = 128


# Capture formats that wrap the trace in an envelope, keyed by the envelope's own
# field names. MLflow 3 puts everything one level down -- `info.state`,
# `info.request_preview`, `data.spans` -- so a top-level-only lookup finds none of
# them.
#
# MEASURED on the reservation-service corpus, 27 MLflow trace elements: `names`
# was the only heuristic that fired on any of them, because it is the only one
# that recurses. `status`, `request_text` and `element_counts` were structurally
# unable to fire, and the triage stage of the day (then a single `rb-triage`
# dispatch over the whole catalogue) consequently reported that nothing in the
# catalogue attested a failure -- for a corpus in which nine traces carry an
# error payload or an empty result. It was reasoning correctly from one signal out
# of five.
#
# Deliberately a fixed one-level widening and NOT a tree walk. `_has_error_marker`
# documents why: an earlier version scanned every string in the tree and fired on
# 63 of 130 elements, 62 of them successful, because span-level attributes and
# ordinary prose both look like failures from a distance. Two named envelope keys
# reach the fields real captures put there without going near a span.
_ENVELOPE_KEYS = ("info", "data")


def _lookup_scopes(payload: dict) -> list[dict]:
    """The payload, then any envelope object it carries, outermost first.

    Order is precedence: a capture that puts `status` at the top level keeps
    that value, and the envelope is consulted only when the top level is silent.
    """
    scopes = [payload]
    for key in _ENVELOPE_KEYS:
        value = payload.get(key)
        if isinstance(value, dict):
            scopes.append(value)
    return scopes


def is_message_list(payload: Any) -> bool:
    """Whether this payload is a conversation: a list of role-tagged messages.

    One home for the shape rule, because `intake.classify` and
    `digest_for_payload` must agree on it: a file classified `trace` for being a
    message list and then digested by the dict producer would fall through to a
    skeleton, which is exactly the defect issue #4 reported.

    Measured on tau2-bench's 200 chat trajectories, which is what this exists
    for: every file's key intersection is exactly {'role'} -- 895 of 5,182
    messages are {role, tool_calls} and carry no `content` -- so no key-set rule
    reaches them, and `EXPLODE_MIN_COMMON_KEYS` relaxed to 2 admits 0 of the
    200. A string `role` on every element is the only invariant they have.

    Two elements, not one: a one-element list carrying `role` is a shape common
    in configuration, and digesting it as a dialogue reports a conversation that
    does not exist.

    The distinct-role cap bounds how many keys `element_counts` can have, and
    nothing more: `_SKELETON_MAX_CHILDREN` is already this module's breadth
    budget, so it is borrowed here rather than a second number invented, but a
    key count is not a byte count and a role string is interpolated into the key.
    The bytes are bounded separately, by `_MAX_ROLE_CHARS` in the producer, and
    that truncation is reported as `role_keys_truncated`. Measured on tau2: 4
    roles.

    Precision, measured: 200 of 200 tau2 trajectories and 0 of the 15 JSON
    fixtures under tests/fixtures/. The wider negative is 0 of the 1,731 other
    JSON files under tau2-bench -- not the src/tau2 tree an earlier draft cited,
    which holds no JSON at all and so evidenced nothing.
    """
    if not isinstance(payload, list) or len(payload) < 2:
        return False
    # A *string* role, not merely a present one: the distinct-role set below
    # would raise on an unhashable value, and a role is a string in every shape
    # this targets.
    if not all(
        isinstance(message, dict) and isinstance(message.get("role"), str) for message in payload
    ):
        return False
    if not any("content" in message or "tool_calls" in message for message in payload):
        return False
    return len({message["role"] for message in payload}) <= _SKELETON_MAX_CHILDREN


def _first_scalar(payload: dict, keys: tuple[str, ...]) -> Any | None:
    for scope in _lookup_scopes(payload):
        for key in keys:
            value = scope.get(key)
            if isinstance(value, str | int | float | bool):
                return value
    return None


def _collect_names(node: Any, depth: int, out: set[str], truncated: list[bool]) -> None:
    """Collect names, each bounded by `_MAX_NAME_CHARS`.

    `truncated` is written at the moment a name is actually cut, not re-derived
    afterwards by comparing widths to the cap -- the same reason `_skeleton`
    records its own budget refusal inline. A name landing exactly on the cap
    loses nothing, so the comparison is `>`, and reporting it truncated would be
    the false positive that rewrite existed to remove.

    Because `out` is a set, two names differing only past the cap collapse into
    one entry and the sorted list loses one. That is a possibility of truncating
    into a set rather than a certainty -- names differing within the cap keep both
    entries -- and it is the reason the flag is not optional: a narrow digest is
    fine, a digest that quietly drops a tool the candidate calls is not.
    """
    if depth < 0 or len(out) >= _MAX_NAMES:
        return
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _NAME_KEYS and isinstance(value, str):
                out.add(_bounded_name(value, truncated))
            elif key in _NAME_KEYS and isinstance(value, list):
                out.update(_bounded_name(v, truncated) for v in value if isinstance(v, str))
            else:
                _collect_names(value, depth - 1, out, truncated)
    elif isinstance(node, list):
        for item in node:
            _collect_names(item, depth - 1, out, truncated)


def _bounded_name(name: str, truncated: list[bool]) -> str:
    if len(name) > _MAX_NAME_CHARS:
        truncated[0] = True
        return name[:_MAX_NAME_CHARS]
    return name


def _has_error_key(node: Any, depth: int) -> bool:
    """Structural signal only: a literal error-shaped key with a non-empty
    value, anywhere in the tree. No value-substring scan here -- see
    `_has_error_marker`'s docstring for why that was measured too noisy to
    keep."""
    if depth < 0:
        return False
    if isinstance(node, dict):
        for key, value in node.items():
            # `False` belongs in the emptiness tuple, and it carries `0` with it:
            # `in` compares by equality and `0 == False`, so one entry covers the
            # boolean flag and the zero count alike. Without it, a field that
            # explicitly states no error occurred *asserted* one -- measured on
            # each of the four metadata-rich airline result files under
            # tau2-bench's `data/tau2/results/final`, whose messages carry a
            # top-level `error: False`: this fired on 200 of 200 episodes in all
            # four, including every episode that scored `reward == 1.0`. No count
            # here on purpose: how many episodes succeeded varies by file, and the
            # point is that success and failure were indistinguishable rather than
            # how many of each there were. `error_markers` reached triage as a
            # found fact about every successful episode, which is worse than
            # silence, because `rb-triage-rule` reads a failing trace as almost
            # never a near-duplicate of a successful one and this asserted failure
            # everywhere. `{"error": None}` was already correct.
            if key.lower() in _ERROR_KEYS and value not in (None, "", [], {}, False):
                return True
            if _has_error_key(value, depth - 1):
                return True
    elif isinstance(node, list):
        return any(_has_error_key(item, depth - 1) for item in node)
    return False


def _has_error_marker(payload: dict, status: Any, depth: int) -> bool:
    """Whether this trace shows a structural sign of failure.

    Originally also scanned every string value in the tree for "error" or
    "exception" as a substring. Measured against the development corpus's real
    130-element trace capture, that fired on 63 elements -- 62 of them
    `TraceStatus.OK` (47.7% of the whole corpus) -- because its target was an
    operations assistant whose ordinary, successful answers discuss "error
    logs" and "error rate" as domain
    vocabulary, and because span-level attributes like `{"status": "error"}`
    show up on internal or recovered steps, not just trace-level failures.
    That noise made the field useless: `heuristics_fired` only records that
    it *fired*, so a triage reading it could not tell the one real failure
    (t7, the corpus's only `TraceStatus.ERROR`) from ordinary prose.

    Narrowed to two structural signals only: the trace's own status/state/
    outcome value (the same field already surfaced as `result["status"]`)
    naming an error, or a literal error-shaped key (`_ERROR_KEYS`) somewhere
    in the tree with a non-empty value.
    """
    if isinstance(status, str) and any(marker in status.lower() for marker in _ERROR_SUBSTRINGS):
        return True
    return _has_error_key(payload, depth)


def _json_type_name(value: Any) -> str:
    """JSON Schema's vocabulary, not Python's -- the skeleton sits next to
    `{"type": "object"}` / `{"type": "array"}` nodes, and a leaf reported as
    "str" or "int" would be the odd one out a triage prompt has to translate."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


def _skeleton(node: Any, pointer: str, depth: int, out: dict, truncated: list[bool]) -> None:
    # The total-node budget is checked here rather than by the callers because
    # recursion is where pointers are minted. Stopping mid-walk leaves a
    # *prefix* of the skeleton, which is why the flag below is written by the
    # caller: a reader must be able to tell a small object from a clamped one.
    #
    # depth < 0 and the node-budget check below are NOT the same event and must
    # not share a flag. depth < 0 is the ordinary per-node depth bound reaching
    # its own floor -- ordinary shape, not truncation -- so it returns quietly.
    # Only the budget branch means the walk was turned away from a node it would
    # otherwise have visited: that is what truncation *is*, so it is the only
    # branch that marks `truncated`. Recording it here, at the moment a visit is
    # refused, rather than inferring it afterward by comparing the final
    # `len(out)` to the cap, is what keeps a skeleton whose *natural* size lands
    # exactly on the cap from being falsely marked truncated -- measured: 8 keys
    # of 15 leaves each is exactly 8 + 8*15 = 128 nodes, and no visit is ever
    # refused while producing it, since the guard is checked before each write
    # and the count only reaches 128 on the last one. A length comparison alone
    # cannot tell "exactly full" apart from "cut off"; this can.
    if depth < 0:
        return
    if len(out) >= _SKELETON_MAX_NODES:
        truncated[0] = True
        return
    if isinstance(node, dict):
        shown = sorted(node)[:_SKELETON_MAX_CHILDREN]
        if pointer:
            out[pointer] = {
                "type": "object",
                "keys": shown,
                # True count and an explicit flag, not just a shorter list --
                # the array branch below reports the true `length` even
                # though it only expands element 0, and a capped `keys` list
                # with no count is the exact silent-truncation shape that
                # produced the 783KB pricing-table digest this module was
                # measured against.
                "key_count": len(node),
                "keys_truncated": len(node) > len(shown),
            }
        # Recurse only into the keys actually listed above -- see
        # _SKELETON_MAX_CHILDREN. A key omitted from `keys` would be a fact the
        # skeleton can't cite anyway, so descending into it buys nothing.
        for key in shown:
            _skeleton(node[key], f"{pointer}/{key}", depth - 1, out, truncated)
    elif isinstance(node, list):
        out[pointer or "/"] = {"type": "array", "length": len(node)}
        if node:
            _skeleton(node[0], f"{pointer}/0", depth - 1, out, truncated)
    else:
        out[pointer or "/"] = {"type": _json_type_name(node)}


def _prose_digest(text: str, body_chars: int) -> dict:
    lines = text.splitlines()
    headings = [line.rstrip() for line in lines if line.startswith("#")]
    body = "\n".join(line for line in lines if not line.startswith("#")).strip()
    return {
        # Complete, never truncated: the outline is the cheapest full statement
        # of what a document covers, and a truncated one is how triage misses
        # the one section that mattered.
        "headings": headings,
        "lines": len(lines),
        "body_head": body[:body_chars],
        "digest_truncated": len(body) > body_chars,
    }


def _source_digest(text: str) -> dict:
    """Top-level names only, via ast -- never a regex over source.

    Python only. `ast` reads one of the eight suffixes `intake` classifies as
    source code, and `digest_for_path` routes the other seven to its prose
    fallback, so `parse_failed` below means "these bytes are not valid Python"
    and never "this digester has no parser for this language".

    `assignments` is the field a projection brief depends on: such a brief can only
    say "the schemas are the literals named TOOL_DEFINITIONS" if triage can see
    that name, and defs and classes alone do not carry it.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {"parse_failed": True}
    assignments: set[str] = set()
    defs: list[str] = []
    classes: list[str] = []
    imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            assignments.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assignments.add(node.target.id)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            defs.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return {
        "assignments": sorted(assignments),
        "defs": defs,
        "classes": classes,
        "imports": sorted(imports),
        "lines": len(text.splitlines()),
    }


def _trace_digest_from_dict(payload: dict, *, body_chars: int) -> tuple[dict, list[str]]:
    """The trace facts a dict-shaped capture carries. Unchanged behaviour; split
    out only so the message-list producer beside it can share
    `digest_for_payload`'s single assembly of `heuristics_fired`."""
    fired: list[str] = []
    result: dict[str, Any] = {}

    status = _first_scalar(payload, _STATUS_KEYS)
    if status is not None:
        result["status"] = status
        fired.append("status")

    # Same envelope widening as _first_scalar, and first scope wins for the
    # same reason: MLflow's span list is `data.spans`, not `spans`.
    counts: dict[str, int] = {}
    for scope in _lookup_scopes(payload):
        for key in _COUNT_KEYS:
            if key not in counts and isinstance(scope.get(key), list):
                counts[key] = len(scope[key])
    if counts:
        result["element_counts"] = counts
        fired.append("element_counts")

    request = _first_scalar(payload, _REQUEST_KEYS)
    if isinstance(request, str) and request.strip():
        # Kept raw and truncated rather than parsed: those captures
        # store request_preview as a *truncated* JSON string, so json.loads
        # fails on it while the question text sits in the first 80 chars.
        result["request_text"] = request[:body_chars]
        fired.append("request_text")

    names: set[str] = set()
    names_truncated = [False]
    _collect_names(payload, _SKELETON_DEPTH, names, names_truncated)
    if names:
        result["names"] = sorted(names)
        # A sibling of the field, not of the digest: a candidate carrying no name
        # must not grow a flag about names it does not have, which is the rule
        # that keeps `role_keys_truncated` off a dict-shaped trace.
        result["names_truncated"] = names_truncated[0]
        fired.append("names")

    if _has_error_marker(payload, status, _SKELETON_DEPTH):
        result["error_markers"] = True
        fired.append("error_markers")

    return result, fired


def _trace_digest_from_messages(payload: list, *, body_chars: int) -> tuple[dict, list[str]]:
    """The trace facts a conversation carries, for the shape `is_message_list`
    admits.

    Reads `content` directly rather than through `_REQUEST_KEYS`: widening that
    tuple would change every existing dict-shaped trace digest and oblige
    re-recording the committed fixtures, for a key only this shape uses.

    Two of the five named heuristics are missing from what this path produced on
    tau2, for reasons that are different in kind and must not be stated as one.

    `status` is not implemented here at all: this function makes no `_first_scalar`
    call and no `_STATUS_KEYS` lookup. The measurement -- no key in `_STATUS_KEYS`
    appears in any of tau2's 5,182 messages, because a chat trajectory has no
    terminal status field -- is why implementing it was unnecessary, and it cannot
    also be the reason it does not fire: widen the corpus to trajectories that do
    carry a status key and this producer still would not read one.

    `error_markers` *is* implemented, by the `_has_error_key` clause at the end of
    this function, and it does fire: tests/unit/test_digest.py asserts it on a
    message carrying an error-shaped key, and measured, deleting the clause turns
    that test red. It fired on 0 of tau2's 200 files, which is a fact about that
    corpus rather than about the clause. A rule matching a tool result whose
    `content` begins with an error sentinel would have fired on 12 of 200 --
    rejected, because that is the value inspection `_has_error_marker` was
    deliberately narrowed to exclude, and `heuristics_fired` reporting nothing
    found is the honest record.
    """
    fired: list[str] = []
    result: dict[str, Any] = {}

    # Always fires: a conversation always has messages. The role tally rides
    # along because it is the cheapest statement of an episode's shape -- how
    # many turns, how many tool results.
    #
    # Two bounds, because the predicate's distinct-role cap supplies only one of
    # them: it caps the number of keys at 33, and the role text spelled into each
    # key is truncated here to cap their width. Measured, before the truncation
    # existed: 32 records carrying 3,000-character roles digested to 96,514 bytes
    # against 248 as a skeleton, past a 65,536-byte slice -- one such row makes
    # `survey`'s oversized-row check refuse the whole corpus.
    #
    # And truncating is reported, not silent: two distinct long roles can
    # truncate to the same key and merge their tallies, which would be a digest
    # that lies about the candidate rather than one that is merely narrow. Same
    # convention as `keys_truncated` and `skeleton_nodes_truncated`, unconditional
    # for the same reason they are -- a flag a reader only sees when it is true
    # cannot be told apart from a digest written before the flag existed.
    counts: dict[str, int] = {"messages": len(payload)}
    roles_truncated = False
    for message in payload:
        role = message["role"]
        if len(role) > _MAX_ROLE_CHARS:
            roles_truncated = True
        key = f"role_{role[:_MAX_ROLE_CHARS]}"
        counts[key] = counts.get(key, 0) + 1
    result["element_counts"] = counts
    result["role_keys_truncated"] = roles_truncated
    fired.append("element_counts")

    # The first *user* turn, with no fallback to the first message of any role:
    # the system prompt is corpus-wide boilerplate, measured at 118 distinct
    # user prefixes against 1 distinct system prefix across tau2's 200 files, so
    # a fallback would return the same bytes for nearly every candidate.
    for message in payload:
        content = message.get("content")
        if message["role"] == "user" and isinstance(content, str) and content.strip():
            result["request_text"] = content[:body_chars]
            fired.append("request_text")
            break

    # Per message rather than over the list, so the depth budget is spent inside
    # a message: that is what reaches `tool_calls[].function.name`, which is the
    # field carrying 14 distinct tool names and 68 toolset signatures here.
    names: set[str] = set()
    names_truncated = [False]
    for message in payload:
        _collect_names(message, _SKELETON_DEPTH, names, names_truncated)
    if names:
        result["names"] = sorted(names)
        result["names_truncated"] = names_truncated[0]
        fired.append("names")

    if any(_has_error_key(message, _SKELETON_DEPTH) for message in payload):
        result["error_markers"] = True
        fired.append("error_markers")

    return result, fired


def digest_for_payload(payload: Any, kind: str, *, body_chars: int) -> dict:
    """Digest an already-parsed JSON payload -- a container element, or a file
    survey has read. `heuristics_fired` is the field that matters; see module doc."""
    if kind == "trace":
        produced: tuple[dict, list[str]] | None = None
        if isinstance(payload, dict):
            produced = _trace_digest_from_dict(payload, body_chars=body_chars)
        elif is_message_list(payload):
            produced = _trace_digest_from_messages(payload, body_chars=body_chars)
        if produced is not None:
            result, fired = produced
            result["heuristics_fired"] = [h for h in TRACE_HEURISTICS if h in fired]
            return result
        # Neither shape: fall through to the skeleton, one candidate with a
        # structural digest.
        #
        # The route that reaches here is `intake.classify`'s list branch, which
        # decides on `payload[0]` alone: a heterogeneous file such as
        # `[{"trace_id": "t1", "spans": []}, "scalar", 3]` classifies `trace`,
        # `survey.explode` returns None because the list is not homogeneous, so
        # the whole payload -- not an element of it -- arrives here.
        #
        # Not `survey.explode`, which cannot produce this two ways over:
        # `survey._homogeneous` refuses any element list holding a non-dict, so
        # explode never yields a non-dict element, and `survey.classify_payload`
        # has no branch outside `isinstance(payload, dict)`, so it could not
        # return "trace" for one even if it did.

    skeleton: dict[str, Any] = {}
    truncated = [False]
    _skeleton(payload, "", _SKELETON_DEPTH, skeleton, truncated)
    # Stated rather than implied, for the reason keys_truncated is stated: a
    # truncation a prompt can see is a fact about the digest, and one it cannot
    # see is a lie about the candidate. Read from `truncated`, not re-derived
    # from `len(skeleton) >= _SKELETON_MAX_NODES`: that comparison was measured
    # to false-positive on a skeleton whose natural, uncapped size lands exactly
    # on the cap (8 keys of 15 leaves each is exactly 128 nodes) -- nothing was
    # cut off, but the length check alone cannot tell that from a walk that was.
    # `truncated[0]` is set only at the moment `_skeleton`'s budget guard actually
    # refuses a node, which is the same "record the real event, not a proxy for
    # it" precedent `keys_truncated` above already sets for the breadth cap.
    return {"skeleton": skeleton, "skeleton_nodes_truncated": truncated[0]}


def digest_for_path(path: Path, kind: str, *, body_chars: int) -> dict:
    """Digest one file. Never raises: survey already filtered unreadable files,
    so a failure here is a property of the bytes and belongs in the record."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {"undecodable": True}

    if kind == "design_doc":
        return _prose_digest(text, body_chars)
    if kind == "source_code":
        suffix = path.suffix.lower()
        if suffix in _PARSEABLE_SUFFIXES:
            return _source_digest(text)
        # No parser for this language. Prose rather than a bare flag, for the
        # reason `digest_for_path`'s JSON fallback below already states: give
        # triage something it can rule on and let it decline if that is not
        # enough. Measured on parsec's `static/app.js`, 101,483 bytes: `lines`
        # 2650, a 2000-char `body_head` at the first real statement, and
        # `digest_truncated` true. `unsupported_language` names the suffix
        # because a reader must be able to tell "this digester has no parser"
        # from "these bytes are broken" -- conflating the two put a digester bug
        # into a gate-0 brief as a 101KB corpus gap, in language a human
        # reviewer had no way to challenge.
        result = _prose_digest(text, body_chars)
        # `headings` means markdown headings, and `_prose_digest` keeps it
        # complete rather than truncated on purpose. Over a `#`-commented
        # language that is every comment line, unbounded in comment count:
        # measured, 500 Ruby comment lines produce 500 headings and 21,890 bytes
        # in one candidate row, against the 65,536-byte slice a row may not
        # exceed without `survey` exiting 2. Six of the seven suffixes routed
        # here use `//` and would collect an empty list, so the field earns
        # nothing in either direction. Dropped here rather than bounded in
        # `_prose_digest`, which must keep the complete outline it gives a
        # `design_doc`.
        del result["headings"]
        result["unsupported_language"] = suffix
        return result
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, RecursionError):
        # Not JSON and not a kind we have a reader for: give triage the prose
        # digest rather than nothing, and let it decline if that is not enough.
        # RecursionError alongside JSONDecodeError: survey.py's "no
        # size-based exclusion" rule means a pathologically nested file (a
        # 200,000-deep [[[...]]]) reaches here uncaught by anything upstream,
        # and CPython's json decoder raises RecursionError rather than
        # JSONDecodeError for that shape. The module's own contract is never
        # to raise; this is that contract's other half.
        return _prose_digest(text, body_chars)
    return digest_for_payload(payload, kind, body_chars=body_chars)
