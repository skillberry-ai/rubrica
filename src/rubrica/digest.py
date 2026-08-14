"""One bounded digest per candidate: the only thing rb-triage reads.

This module is the design's single point of failure and is written knowing it.
Triage's `reads` is the catalogue alone, so a fact absent from a digest is a
fact triage does not have -- and the generator is code that cannot know what
matters about a target it has never seen.

Completeness is unreachable, so the mitigation is honesty instead:
`heuristics_fired` records which extractors actually found something. A triage
that cannot rule on a candidate declines it `digest_insufficient` and names the
field it needed, which turns this module's blindness into a finding a human
reads at gate 0 rather than a silent bad selection.

Every field here is anchored to a decision the 2026-08-13 parsec run made by
hand. If a new field cannot be traced to a decision somebody actually took, it
is weight in a barrier's context window and does not belong.
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
# parsec traces carry the failure as "TraceStatus.ERROR", not under a key
# named "error", so a key-name-only check misses the exact fact t7 was kept
# for.
_ERROR_SUBSTRINGS = ("exception", "error")
_SKELETON_DEPTH = 3
_MAX_NAMES = 64
# The parsec corpus carries a 1191-key pricing table as one JSON file
# (ec2_pricing.json, classified "other"). Recursing into every key produced a
# 783KB digest for that single candidate -- measured, not assumed. The "keys"
# list below was already capped at this width for display; recursion now
# matches it, so a wide dict costs the same whether it has ten entries or a
# thousand.
_SKELETON_MAX_CHILDREN = 32


def _first_scalar(payload: dict, keys: tuple[str, ...]) -> Any | None:
    for key in keys:
        value = payload.get(key)
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


def _has_error_marker(node: Any, depth: int) -> bool:
    if depth < 0:
        return False
    if isinstance(node, dict):
        for key, value in node.items():
            lowered = key.lower()
            if lowered in _ERROR_KEYS and value not in (None, "", [], {}):
                return True
            if isinstance(value, str) and any(
                marker in value.lower() for marker in _ERROR_SUBSTRINGS
            ):
                return True
            if _has_error_marker(value, depth - 1):
                return True
    elif isinstance(node, list):
        return any(_has_error_marker(item, depth - 1) for item in node)
    return False


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


def _skeleton(node: Any, pointer: str, depth: int, out: dict) -> None:
    if depth < 0:
        return
    if isinstance(node, dict):
        shown = sorted(node)[:_SKELETON_MAX_CHILDREN]
        if pointer:
            out[pointer] = {"type": "object", "keys": shown}
        # Recurse only into the keys actually listed above -- see
        # _SKELETON_MAX_CHILDREN. A key omitted from `keys` would be a fact the
        # skeleton can't cite anyway, so descending into it buys nothing.
        for key in shown:
            _skeleton(node[key], f"{pointer}/{key}", depth - 1, out)
    elif isinstance(node, list):
        out[pointer or "/"] = {"type": "array", "length": len(node)}
        if node:
            _skeleton(node[0], f"{pointer}/0", depth - 1, out)
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

    `assignments` is the field spec §8 depends on: a projection brief can only
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

        counts = {
            key: len(payload[key]) for key in _COUNT_KEYS if isinstance(payload.get(key), list)
        }
        if counts:
            result["element_counts"] = counts
            fired.append("element_counts")

        request = _first_scalar(payload, _REQUEST_KEYS)
        if isinstance(request, str) and request.strip():
            # Kept raw and truncated rather than parsed: the parsec captures
            # store request_preview as a *truncated* JSON string, so json.loads
            # fails on it while the question text sits in the first 80 chars.
            result["request_text"] = request[:body_chars]
            fired.append("request_text")

        names: set[str] = set()
        _collect_names(payload, _SKELETON_DEPTH, names)
        if names:
            result["names"] = sorted(names)
            fired.append("names")

        if _has_error_marker(payload, _SKELETON_DEPTH):
            result["error_markers"] = True
            fired.append("error_markers")

        result["heuristics_fired"] = [h for h in TRACE_HEURISTICS if h in fired]
        return result

    skeleton: dict[str, Any] = {}
    _skeleton(payload, "", _SKELETON_DEPTH, skeleton)
    return {"skeleton": skeleton}


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
    except json.JSONDecodeError:
        # Not JSON and not a kind we have a reader for: give triage the prose
        # digest rather than nothing, and let it decline if that is not enough.
        return _prose_digest(text, body_chars)
    return digest_for_payload(payload, kind, body_chars=body_chars)
