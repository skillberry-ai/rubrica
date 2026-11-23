"""Evaluating world-model `machine:` invariants against a seed.

Deliberately not an expression language. Each invariant is a structured
directive with a `form` discriminator, so there is nothing to parse and
nothing to sandbox: a malformed directive fails schema validation before it
ever reaches this module. Four forms cover the invariant classes observed in
the simulation skill of the corpus this was developed against; anything that
does not fit is recorded as `prose:` and left to the authoring stage's own
self-check.

Known limit: arithmetic over timestamps (a
`duration_seconds == finished - started` invariant seen in that corpus) is not
expressible here and must be prose. A `derive` form is the natural extension
when a second target needs it.

Every function returns violation messages rather than raising, because a
seed with three problems should report three problems in one pass.
"""

from __future__ import annotations

import operator
from collections.abc import Callable
from typing import Any

OPS: dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}


class InvariantForm(ValueError):
    """Raised when an invariant's form is not one this module implements."""


class _Missing:
    def __repr__(self) -> str:
        return "<missing>"


MISSING = _Missing()


def _records(collections: dict[str, Any], name: str) -> list[dict[str, Any]]:
    """Records in a collection, or empty if the seed has no such collection.

    An absent collection is refs.py's finding to report; duplicating it here
    would double-count one defect in the check-refs output.
    """
    value = collections.get(name)
    return value if isinstance(value, list) else []


def _field(record: dict[str, Any], name: str) -> Any:
    return record.get(name, MISSING)


def evaluate(machine: dict[str, Any], collections: dict[str, Any]) -> list[str]:
    """Check one invariant against a seed's collections.

    Returns one message per violation; an empty list means the invariant
    holds (or that there was nothing in the seed to check it against).
    """
    form = machine.get("form")
    handler = _HANDLERS.get(form)
    if handler is None:
        raise InvariantForm(f"unimplemented invariant form: {form!r}")
    return handler(machine, collections)


def _compare(m: dict[str, Any], collections: dict[str, Any]) -> list[str]:
    out: list[str] = []
    coll, left_name, op = m["collection"], m["left"], m["op"]
    for i, record in enumerate(_records(collections, coll)):
        left = _field(record, left_name)
        if left is MISSING:
            out.append(f"{coll}[{i}] has no field {left_name!r}")
            continue
        if "literal" in m["right"]:
            right = m["right"]["literal"]
            right_label = repr(right)
        else:
            right_name = m["right"]["field"]
            right = _field(record, right_name)
            if right is MISSING:
                out.append(f"{coll}[{i}] has no field {right_name!r}")
                continue
            right_label = f"{right_name}={right!r}"
        try:
            holds = OPS[op](left, right)
        except TypeError:
            out.append(f"{coll}[{i}]: cannot compare {left!r} {op} {right!r}")
            continue
        if not holds:
            out.append(f"{coll}[{i}]: {left_name}={left!r} {op} {right_label} is false")
    return out


def _related(m: dict[str, Any], collections: dict[str, Any], key: Any) -> list[dict[str, Any]]:
    return [r for r in _records(collections, m["of"]) if r.get(m["foreign_key"]) == key]


def _count(m: dict[str, Any], collections: dict[str, Any]) -> list[str]:
    out: list[str] = []
    coll, field, local_key = m["collection"], m["field"], m["local_key"]
    for i, record in enumerate(_records(collections, coll)):
        declared = _field(record, field)
        key = _field(record, local_key)
        if declared is MISSING:
            out.append(f"{coll}[{i}] has no field {field!r}")
            continue
        if key is MISSING:
            out.append(f"{coll}[{i}] has no field {local_key!r}")
            continue
        actual = len(_related(m, collections, key))
        if declared != actual:
            out.append(
                f"{coll}[{i}].{field}={declared} but {m['of']} has {actual} record(s) "
                f"with {m['foreign_key']}=={key!r}"
            )
    return out


def _join(m: dict[str, Any], collections: dict[str, Any]) -> list[str]:
    out: list[str] = []
    coll, field, local_key = m["collection"], m["field"], m["local_key"]
    order_by, source_field, sep = m["order_by"], m["source_field"], m["separator"]
    for i, record in enumerate(_records(collections, coll)):
        declared = _field(record, field)
        key = _field(record, local_key)
        if declared is MISSING:
            out.append(f"{coll}[{i}] has no field {field!r}")
            continue
        if key is MISSING:
            out.append(f"{coll}[{i}] has no field {local_key!r}")
            continue
        matches = _related(m, collections, key)
        if any(order_by not in r for r in matches):
            out.append(
                f"{m['of']} record(s) for {m['foreign_key']}=={key!r} are missing "
                f"order_by field {order_by!r}"
            )
            continue
        try:
            matches = sorted(matches, key=lambda r: r[order_by])
        except TypeError:
            out.append(f"{m['of']} order_by field {order_by!r} has incomparable values")
            continue
        expected = sep.join(str(r.get(source_field, "")) for r in matches)
        if declared != expected:
            out.append(
                f"{coll}[{i}].{field} is not the ordered join of "
                f"{m['of']}.{source_field} by {order_by}"
            )
    return out


def _frozen(value: Any) -> Any:
    """A hashable stand-in for a seed value, equal exactly when the values are.

    The seed schema only requires records to be objects, so a field `unique`
    reads can hold a list or an object, and putting either into a set or a
    dict key raises TypeError. That error once escaped `check-refs` as a lone
    `[internal]` line which hid every real finding in the run and named no
    seed. Lists become tuples and objects become frozensets of their items,
    recursively, so equality is still Python's `==` (as `values.count` used)
    rather than a JSON string's, which would split `1` from `1.0`.
    """
    if isinstance(value, list):
        return tuple(_frozen(v) for v in value)
    if isinstance(value, dict):
        return frozenset((k, _frozen(v)) for k, v in value.items())
    return value


def _unique(m: dict[str, Any], collections: dict[str, Any]) -> list[str]:
    out: list[str] = []
    coll, field = m["collection"], m["field"]
    within = m.get("within")
    # Keyed on the frozen group key; each entry keeps the original key so
    # messages show the value as the seed wrote it, not its frozen form.
    groups: dict[Any, tuple[Any, list[Any]]] = {}
    for i, record in enumerate(_records(collections, coll)):
        value = _field(record, field)
        if value is MISSING:
            out.append(f"{coll}[{i}] has no field {field!r}")
            continue
        key: Any = None
        if within is not None:
            key = _field(record, within)
            if key is MISSING:
                out.append(f"{coll}[{i}] has no field {within!r}")
                continue
        groups.setdefault(_frozen(key), (key, []))[1].append(value)

    # Groups are walked in a repr-sorted order so messages are identical
    # across runs; diff-runs would otherwise report ordering as variance.
    for key, values in sorted(groups.values(), key=lambda g: repr(g[0])):
        where = f" within {within}=={key!r}" if within is not None else ""
        counts: dict[Any, int] = {}
        originals: dict[Any, Any] = {}
        for v in values:
            f = _frozen(v)
            counts[f] = counts.get(f, 0) + 1
            originals.setdefault(f, v)
        duplicates = sorted((originals[f] for f, n in counts.items() if n > 1), key=repr)
        if duplicates:
            out.append(f"{coll}.{field} has duplicate value(s) {duplicates}{where}")
        if m.get("increasing"):
            try:
                ascending = all(a < b for a, b in zip(values, values[1:], strict=False))
            except TypeError:
                out.append(f"{coll}.{field} has incomparable values{where}")
                continue
            if not ascending:
                out.append(f"{coll}.{field} is not strictly increasing{where}")
    return out


_HANDLERS: dict[Any, Callable[[dict[str, Any], dict[str, Any]], list[str]]] = {
    "compare": _compare,
    "count": _count,
    "join": _join,
    "unique": _unique,
}
