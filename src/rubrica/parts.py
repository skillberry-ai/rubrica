"""The one door both seals read their staged parts through.

`seal` (triage-seal, assembling 00-triage.json) and `reconcile` (reconcile-seal,
assembling 01-world-model.json) each read a fixed set of staged artifacts and
refuse to assemble from any that is absent, unparseable, or the wrong shape.
Those helpers used to live in both modules line for line, differing only in the
Finding's check label; they live here once, and each caller passes its own label
as `check=` so the findings each seal emits are unchanged.

Presence, parseability, payload-key presence and (for a caller that declares
one) nested *container* shape are the whole of what this door checks -- never
the type of a scalar a payload key holds. Layer 1 (one schema per staged
artifact) is the rejection point for a wrong-typed value, and duplicating that
here would put the same rule in two places with two messages.
"""

from __future__ import annotations

from pathlib import Path

from rubrica.artifacts import ArtifactError, read_json
from rubrica.findings import Finding

# The read-failure sentinel, and specifically *not* None. `null` is a legitimate
# JSON document and read_json is annotated `-> Any` and rejects no shape, so it
# returns None for a part containing `null` -- which made `document is not None`
# mean two different things at once. Measured on reconcile-seal: with
# 01-gaps.json set to `null` the payload-key check was skipped entirely and the
# assembly raised `KeyError: 'gaps_part'`, which cli.py's catch-all reported
# against the run root, naming a RunPaths attribute rather than any artifact.
# triage-seal had the same hole: a `null` part skipped the payload-key check and
# reached a bare dict index. An object() cannot be read off disk.
UNREADABLE = object()


def read_part(path: Path, out: list[Finding], *, check: str) -> object:
    """One part's parsed JSON, or UNREADABLE with a finding naming *that* part.

    Naming the right artifact is the third rule of the exit-code contract, learned
    the hard way here: check-refs over an unreadable 01-claims/ once reported four
    fabricated `no such claim` findings against a world model that was correct.
    """
    try:
        return read_json(path)
    except ArtifactError as exc:
        out.append(Finding(path, check, "", str(exc)))
        return UNREADABLE


# JSON's own type names, because the finding is read next to the JSON file it
# names: `found NoneType` and `found list` describe Python to someone looking at
# `null` and `[...]` on disk.
JSON_TYPES: dict[type, str] = {
    type(None): "null",
    bool: "boolean",
    int: "number",
    float: "number",
    str: "string",
    list: "array",
}


def json_type(document: object) -> str:
    return JSON_TYPES.get(type(document), type(document).__name__)


def payload_keys(
    path: Path, keys: tuple[str, ...], document: object, out: list[Finding], *, check: str
) -> bool:
    """Whether `document` is an object carrying every key declared for it.

    A part that is present and valid JSON but has no payload key used to reach
    the assembly and raise KeyError there. cli.py's catch-all turned that into an
    exit-1 `[internal]` finding against the *run root*: two of the three exit-code
    rules held, and the third -- name the right artifact -- did not. That is the
    rule this repo learned when check-refs reported four fabricated `no such
    claim` findings against a world model that was correct, so the keys each
    caller's table declares are checked here rather than carried and discarded.

    The isinstance guard is part of the same check and not a separate one: a
    part whose top level is anything but an object has no payload key either.
    Two of those shapes answer `key not in document` correctly (a list, a string)
    and two cannot answer it at all -- `"gaps" not in 5` and `"gaps" not in None`
    both raise TypeError -- and the guard is what makes all four one finding
    instead of one finding and three tracebacks. It is the shape refs._as_list
    exists for, one layer up.

    It checks the *shape of the document*, never the type of what a payload key
    holds: `{"capabilities": 5}` passes here and is layer 1's to reject.

    For reconcile-seal the return value is defensive rather than load-bearing,
    and measurably so: returning True unconditionally left every test green,
    because the finding is already recorded and that seal returns before it
    touches its parts. It keeps an incomplete document out of the parts anyway,
    so a future caller that stops returning early cannot read a payload key this
    function just reported absent.
    """
    if not isinstance(document, dict):
        out.append(
            Finding(
                path,
                check,
                "",
                f"expected a JSON object with {' and '.join(sorted(keys))}, found "
                f"{json_type(document)}",
            )
        )
        return False
    missing = [key for key in keys if key not in document]
    for key in missing:
        out.append(
            Finding(
                path,
                check,
                "",
                f"no {key!r} key; whatever wrote this artifact did not record its "
                "payload, so there is nothing to assemble from it",
            )
        )
    return not missing


# The marker for "every element of the array here", as a spec key. An object()
# rather than a string so it can never collide with a JSON key name a part
# might legitimately carry.
EACH = object()


def nested_shape(
    path: Path, document: object, spec: dict, pointer: str, out: list[Finding], *, check: str
) -> None:
    """Report every nested container shape `spec` declares and `document` breaks.

    A spec maps a key to the spec for its value, or to None when presence is the
    whole requirement; a spec carrying EACH describes the elements of an array
    rather than the keys of an object, and EACH mapped to None asserts array-ness
    alone.

    Recursive rather than a flat list of walks so a defect high in the tree is
    reported once, at the pointer where it lives, instead of once per leaf the
    seal would have read beneath it.
    """
    if EACH in spec:
        if not isinstance(document, list):
            out.append(
                Finding(path, check, pointer, f"expected an array, found {json_type(document)}")
            )
            return
        element_spec = spec[EACH]
        if element_spec is None:
            return
        for index, element in enumerate(document):
            nested_shape(path, element, element_spec, f"{pointer}/{index}", out, check=check)
        return
    if not isinstance(document, dict):
        out.append(
            Finding(path, check, pointer, f"expected a JSON object, found {json_type(document)}")
        )
        return
    for key, child in spec.items():
        if key not in document:
            out.append(
                Finding(
                    path,
                    check,
                    f"{pointer}/{key}",
                    f"no {key!r} key; this seal indexes it directly and cannot assemble "
                    "a record without it",
                )
            )
            continue
        if child is not None:
            nested_shape(path, document[key], child, f"{pointer}/{key}", out, check=check)


def read_checked(
    path: Path,
    keys: tuple[str, ...],
    out: list[Finding],
    *,
    check: str,
    nested: dict | None = None,
) -> dict | None:
    """One artifact that is readable, carries its payload keys, and (when
    `nested` is given) holds the nested containers the caller indexes -- else None.

    The one door every artifact a seal reads comes through, so the halves cannot
    drift apart: a read failure, a document missing a payload key and a nested
    container of the wrong shape are different findings but the same outcome,
    and folding them into a single `None` return means a caller cannot use one
    artifact while forgetting to check the other. That is the shape a `null`
    part exploited at the top level before this existed, and that twenty nested
    defects exploited one level down in triage-seal.
    """
    document = read_part(path, out, check=check)
    if document is UNREADABLE:
        return None
    if not payload_keys(path, keys, document, out, check=check):
        return None
    if nested is not None:
        before = len(out)
        nested_shape(path, document, nested, "", out, check=check)
        if len(out) > before:
            return None
    return document
