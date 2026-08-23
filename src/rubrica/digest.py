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
_MAX_NAMES = 64
# The development corpus carries a 1191-key pricing table as one JSON file
# (classified "other"). Recursing into every key produced a
# 783KB digest for that single candidate -- measured, not assumed. The "keys"
# list below was already capped at this width for display; recursion now
# matches it, so a wide dict costs the same whether it has ten entries or a
# thousand.
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


def _first_scalar(payload: dict, keys: tuple[str, ...]) -> Any | None:
    for scope in _lookup_scopes(payload):
        for key in keys:
            value = scope.get(key)
            if isinstance(value, str | int | float | bool):
                return value
    return None


def _collect_names(node: Any, depth: int, out: set[str]) -> None:
    if depth < 0 or len(out) >= _MAX_NAMES:
        return
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _NAME_KEYS and isinstance(value, str):
                out.add(value)
            elif key in _NAME_KEYS and isinstance(value, list):
                out.update(v for v in value if isinstance(v, str))
            else:
                _collect_names(value, depth - 1, out)
    elif isinstance(node, list):
        for item in node:
            _collect_names(item, depth - 1, out)


def _has_error_key(node: Any, depth: int) -> bool:
    """Structural signal only: a literal error-shaped key with a non-empty
    value, anywhere in the tree. No value-substring scan here -- see
    `_has_error_marker`'s docstring for why that was measured too noisy to
    keep."""
    if depth < 0:
        return False
    if isinstance(node, dict):
        for key, value in node.items():
            if key.lower() in _ERROR_KEYS and value not in (None, "", [], {}):
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


def digest_for_payload(payload: Any, kind: str, *, body_chars: int) -> dict:
    """Digest an already-parsed JSON payload -- a container element, or a file
    survey has read. `heuristics_fired` is the field that matters; see module doc."""
    if kind == "trace" and isinstance(payload, dict):
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
        _collect_names(payload, _SKELETON_DEPTH, names)
        if names:
            result["names"] = sorted(names)
            fired.append("names")

        if _has_error_marker(payload, status, _SKELETON_DEPTH):
            result["error_markers"] = True
            fired.append("error_markers")

        result["heuristics_fired"] = [h for h in TRACE_HEURISTICS if h in fired]
        return result

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
        return _source_digest(text)
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
