"""The seal: assemble the reconcile partials into one world model.

Code rather than a prompt, for the reason emit is code: two runs with identical
partials must produce a byte-identical world model, or variance stops being
attributable to the pass that caused it. There is a second reason here, specific
to this pipeline's gateway: a code step streams nothing, so it cannot be killed
by the ~300s idle reset that splitting reconcile exists to avoid, however large
the assembled model gets.

This module assembles; it does not check. Cross-artifact checking is layer 2 and
lives in refs.py. What it *does* report is the narrow class where assembly cannot
faithfully represent what it was handed, and the list is exactly four items long:

1. an artifact absent, unparseable, or not a JSON object carrying every payload
   key its entry in _SINGLETON_PARTS declares (`target` for the manifest);
2. a declared capability with no outcome classes;
3. an outcome record naming a capability nobody declared;
4. two outcome records for one capability.

It writes nothing at all when it reports any of them. A half-assembled world model
would be worse than none: it would clear layer 1 for the collections it did manage
to fill.

Presence, parseability and payload-key presence are the whole of what item 1
checks -- not the *type* of what a payload key holds. `{"capabilities": 5}` and
`{"outcomes": [5]}` still reach the assembly and raise out of it, and that is by
design: layer 1 is the rejection point for a wrong-typed value (`rubrica validate
--stage reconcile-<pass>`, one schema per partial), and duplicating it here would
put the same rule in two places with two messages.

Items 2 and 3 overlap layer 2's refs.check_outcomes deliberately, and the overlap
is not an accident to be tidied away later. Item 2 is that check's first clause
(every declared capability has an outcomes record) and item 3 is its second (every
record names a declared capability). check_outcomes owns the after-the-fact report
-- it runs over any run, including one the seal never sealed -- while the branches
here refuse *before the write*, because assembly is perfectly possible in both
cases: the dict lookup simply drops the entry, and the world model then reaches
gate 1 missing cells an artifact declared, looking coherent to the human reading it
and to check_world_model, which recomputes capability_cells from the assembled
model and so agrees with the reduced set. A pipeline more likely to produce output
at the cost of an unobservable drop is a loss, not a win.

Item 4 overlaps nothing, in any layer, and that is the strongest reason of the four
to refuse rather than drop: check_outcomes compares *sets* of capability ids, so
two records for one capability collapse to one member and neither direction of that
comparison reports anything. The seal is the only place a duplicate outcomes record
is ever caught.
"""

from __future__ import annotations

from pathlib import Path

from rubrica.artifacts import ArtifactError, read_json, sha256_of, write_json
from rubrica.findings import Finding
from rubrica.paths import RunPaths, list_json
from rubrica.refs import drivable_cells

# (RunPaths attribute, the payload keys inside that partial) in the order the
# passes run, so a run missing several partials names the earliest pass first --
# the one a repair should start from, the same ordering _readable_targets uses.
# The keys are checked, not merely documented: see _payload_keys below.
_SINGLETON_PARTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("capabilities_part", ("capabilities",)),
    ("outcomes_part", ("outcomes",)),
    ("entities_part", ("entities",)),
    ("goals_part", ("actors", "goals")),
    ("gaps_part", ("gaps",)),
)


# The read-failure sentinel, and specifically *not* None. `null` is a legitimate
# JSON document and read_json is annotated `-> Any` and rejects no shape, so it
# returns None for a partial containing `null` -- which made `document is not None`
# mean two different things at once. Measured: with 01-gaps.json set to `null` the
# payload-key check was skipped entirely and the assembly raised `KeyError:
# 'gaps_part'`, which cli.py's catch-all reported against the run root, naming a
# RunPaths attribute rather than any artifact. An object() cannot be read off disk.
_UNREADABLE = object()


def _read_part(path: Path, out: list[Finding]) -> object:
    """One partial's parsed JSON, or _UNREADABLE with a finding naming *that* partial.

    Naming the right artifact is the third rule of the exit-code contract, learned
    the hard way here: check-refs over an unreadable 01-claims/ once reported four
    fabricated `no such claim` findings against a world model that was correct.
    """
    try:
        return read_json(path)
    except ArtifactError as exc:
        out.append(Finding(path, "reconcile", "", str(exc)))
        return _UNREADABLE


# JSON's own type names, because the finding is read next to the JSON file it
# names: `found NoneType` and `found list` describe Python to someone looking at
# `null` and `[...]` on disk.
_JSON_TYPES: dict[type, str] = {
    type(None): "null",
    bool: "boolean",
    int: "number",
    float: "number",
    str: "string",
    list: "array",
}


def _json_type(document: object) -> str:
    return _JSON_TYPES.get(type(document), type(document).__name__)


def _payload_keys(path: Path, keys: tuple[str, ...], document: object, out: list[Finding]) -> bool:
    """Whether `document` is an object carrying every key declared for it.

    A partial that is present and valid JSON but has no payload key used to reach
    the assembly below and raise KeyError there. cli.py's catch-all turned that
    into an exit-1 `[internal]` finding against the *run root*: two of the three
    exit-code rules held, and the third -- name the right artifact -- did not. That
    is the rule this repo learned when check-refs reported four fabricated `no such
    claim` findings against a world model that was correct, so the keys the table
    declares are checked here rather than carried and discarded.

    The isinstance guard is part of the same check and not a separate one: a
    partial whose top level is anything but an object has no payload key either.
    Two of those shapes answer `key not in document` correctly (a list, a string)
    and two cannot answer it at all -- `"gaps" not in 5` and `"gaps" not in None`
    both raise TypeError -- and the guard is what makes all four one finding
    instead of one finding and three tracebacks. It is the shape refs._as_list
    exists for, one layer up.

    It checks the *shape of the document*, never the type of what a payload key
    holds: `{"capabilities": 5}` passes here and is layer 1's to reject.

    The return value is defensive rather than load-bearing today, and measurably so:
    returning True unconditionally leaves every test green, because the finding is
    already recorded and seal() returns before it touches `parts`. It keeps an
    incomplete document out of `parts` anyway, so a future caller that stops
    returning early cannot read a payload key this function just reported absent.
    """
    if not isinstance(document, dict):
        out.append(
            Finding(
                path,
                "reconcile",
                "",
                f"expected a JSON object with {' and '.join(sorted(keys))}, found "
                f"{_json_type(document)}",
            )
        )
        return False
    missing = [key for key in keys if key not in document]
    for key in missing:
        out.append(
            Finding(
                path,
                "reconcile",
                "",
                f"no {key!r} key; whatever wrote this artifact did not record its "
                "payload, so there is nothing to assemble from it",
            )
        )
    return not missing


def _read_checked(path: Path, keys: tuple[str, ...], out: list[Finding]) -> dict | None:
    """One artifact that is readable *and* carries its payload keys, else None.

    The one door every artifact the seal reads comes through, so the two halves
    cannot drift apart: a read failure and a document that carries no payload key
    are different findings but the same outcome, and folding them into a single
    `None` return means a caller cannot use one artifact while forgetting to check
    the other. That is the shape the `null` case exploited.
    """
    document = _read_part(path, out)
    if document is _UNREADABLE:
        return None
    return document if _payload_keys(path, keys, document, out) else None


def seal(run: RunPaths, *, denominator_version: int = 1) -> tuple[Path | None, list[Finding]]:
    """Assemble 01-world-model.json from the partials, or report why it cannot be.

    `denominator_version` is passed in rather than inferred: an amendment costs an
    explicit orchestrator decision recorded in decisions.md, and a seal that
    incremented a version it found on disk would let the number move without one.
    """
    findings: list[Finding] = []

    # The manifest, not a partial, is where `target` comes from. The single-turn
    # stage wrote it itself and nothing ever checked it against the manifest, so
    # sourcing it here removes an unchecked restatement rather than moving one. It
    # goes through the same door as the partials, and `target` is its payload key,
    # because a `null` manifest reached manifest["target"] with exactly the failure
    # a `null` partial reached the assembly with.
    manifest = _read_checked(run.manifest, ("target",), findings)

    parts: dict[str, dict] = {}
    # The partials this seal actually assembled from, collected as they are read
    # rather than re-derived afterwards from _SINGLETON_PARTS: the optional services
    # part and the contradiction parts are not in that tuple, and a list rebuilt from
    # the roster would record a file the seal never opened. `01-subjects.json` is
    # absent for the same reason -- the seal does not read it.
    assembled: list[Path] = []
    for attribute, keys in _SINGLETON_PARTS:
        part_path = getattr(run, attribute)
        parts_document = _read_checked(part_path, keys, findings)
        if parts_document is not None:
            parts[attribute] = parts_document
            assembled.append(part_path)

    # Read outside _SINGLETON_PARTS because it is the one optional partial. Every
    # entry in that tuple is required and an absent one is a finding, which is right
    # for the five the world model cannot be assembled without and wrong here: a run
    # whose services pass never ran has no services part at all, and the world model
    # it seals is complete without one. The write site below carries the rest of that
    # argument.
    #
    # Through the same door as the rest when it *does* exist: a `null` or
    # list-shaped document must be a finding naming this artifact, not an
    # AttributeError against the run root.
    #
    # No element type on the annotation, matching every other payload value here:
    # _payload_keys checks the shape of the *document* and never the type of what a
    # payload key holds, so `{"services": 5}` reaches this line and is layer 1's to
    # reject, exactly as `{"capabilities": 5}` is.
    services: list | None = None
    if run.services_part.is_file():
        services_document = _read_checked(run.services_part, ("services",), findings)
        if services_document is not None:
            services = services_document["services"]
            assembled.append(run.services_part)

    contradictions: list[dict] = []
    for path in list_json(run.contradictions_dir):
        # Through the same door, for the same reason: a `null` contradiction part
        # made `part.get(...)` raise AttributeError against the run root. The .get
        # default stays even though presence is now reported above -- a fan-out
        # member's file is a record that it swept its subject, so "no
        # contradictions" and "no key" must not become two spellings of a crash.
        part = _read_checked(path, ("contradictions",), findings)
        if part is not None:
            contradictions.extend(part.get("contradictions", []))
            assembled.append(path)

    if findings:
        return None, findings

    capabilities = [dict(item) for item in parts["capabilities_part"]["capabilities"]]

    # Built with a loop rather than a dict comprehension so a repeated
    # capability_id is reported instead of silently overwritten. Two records for
    # one capability are schema-legal -- outcomes-part-0.1.json puts no uniqueItems
    # on the array -- and a comprehension keeps the last, so the first record's
    # cells vanish with nothing downstream to notice: check_world_model recomputes
    # capability_cells from the assembled model, so the denominator agrees with the
    # reduced cell set and the world model reads as coherent. Unlike the two
    # capability-vs-record branches below, this one overlaps *no* layer-2 check:
    # check_outcomes compares sets of capability ids, so two records for one
    # capability collapse to one member and neither direction of that comparison
    # sees anything. The seal is the only place this is ever caught, which is why
    # it refuses rather than choosing one of the two records for the reader.
    outcomes: dict[str, list] = {}
    repeated: list[str] = []
    for entry in parts["outcomes_part"]["outcomes"]:
        capability_id = entry["capability_id"]
        if capability_id in outcomes:
            repeated.append(capability_id)
        else:
            outcomes[capability_id] = entry["outcome_classes"]
    declared = {capability["id"] for capability in capabilities}

    for capability_id in sorted(set(repeated)):
        findings.append(
            Finding(
                run.outcomes_part,
                "reconcile",
                "/outcomes",
                f"more than one outcomes record for {capability_id}; keeping either one "
                "would drop the other's cells from the coverage denominator without "
                "anything downstream reporting the loss",
            )
        )

    # check_outcomes' *second* clause -- every record names a declared capability --
    # and the overlap is deliberate rather than pending removal: that check reports
    # after the fact on any run, while this one refuses before the write, because the
    # entry is otherwise dropped by the lookup above and the world model goes to
    # gate 1 missing cells an artifact declared.
    for capability_id in sorted(set(outcomes) - declared):
        findings.append(
            Finding(
                run.outcomes_part,
                "reconcile",
                "/outcomes",
                f"outcome classes for {capability_id}, which no capability in "
                f"{run.capabilities_part.name} declares",
            )
        )
    # check_outcomes' *first* clause -- every declared capability has a record --
    # overlapped for the same reason as the second, one loop up.
    for capability in capabilities:
        if capability["id"] not in outcomes:
            findings.append(
                Finding(
                    run.outcomes_part,
                    "reconcile",
                    "/outcomes",
                    # The reason names both halves of the narrowed arithmetic on
                    # purpose. "which is what the coverage denominator counts" was
                    # true of every capability before the denominator narrowed to
                    # the drivable ones; an unbound capability's missing record now
                    # costs the denominator nothing, so the refusal needed a reason
                    # that is still true of the capability in front of it. The
                    # refusal itself is unchanged and stays right either way: a
                    # declared capability with no outcome classes names no cells,
                    # so neither the matrices nor the seal's `unreachable` holes
                    # can account for it.
                    f"capability {capability['id']} has no outcome classes; a capability's "
                    "outcome classes are what name its cells at all -- for a bound capability "
                    "those are what the coverage denominator counts, and for an unbound one "
                    "they are what the seal's unreachable holes account for",
                )
            )
        else:
            capability["outcome_classes"] = outcomes[capability["id"]]

    if findings:
        return None, findings

    world = {
        "schema_version": "0.1",
        "target": manifest["target"],
        "capabilities": capabilities,
        "entities": parts["entities_part"]["entities"],
        "actors": parts["goals_part"]["actors"],
        "goals": parts["goals_part"]["goals"],
        "contradictions": contradictions,
        "gaps": parts["gaps_part"]["gaps"],
        "denominator": {
            "version": denominator_version,
            # *Distinct* (capability_id, outcome_class_id) pairs among the
            # capabilities that declare a tool binding -- the cells this suite can
            # actually be scored against, not every cell the model declares. A
            # capability with no binding cannot be driven through the target:
            # emit.bindings drops it outright, so a cell on one is a target no
            # emitted test could ever hit. Measured on run-20260827-070444, before
            # this narrowed: 37 of 56 cells (66%) sat on unbound capabilities and
            # both gate layers exited 0 on the result.
            #
            # refs.drivable_cells and not a local comprehension, because
            # refs.check_world_model recomputes this field through that same
            # function. The recomputation is what makes the field an identity:
            # whatever is written here has to be what the check derives, or
            # check-refs reports a finding against a world model this seal had just
            # produced. A set and not a sum for the reason
            # `docs/design/limitations.md` records under "One precision": the two
            # agree only until a capability id or an outcome-class id repeats, at
            # which point a sum is simply the wrong number -- so do not "simplify"
            # this into sum(len(c["outcome_classes"]) for c in bound capabilities).
            "capability_cells": len(drivable_cells({"capabilities": capabilities})),
            "goals": len(parts["goals_part"]["goals"]),
        },
    }
    # Folded verbatim rather than re-derived: the grouping is rb-reconcile-services'
    # judgment and it is what a human ratifies at gate 1, so a seal that rebuilt the
    # records would be handing them the seal's judgment instead.
    #
    # Omitted rather than written as [] when the part is absent: `[]` asserts a pass
    # looked and found no tools, which is a different claim about the target from "no
    # pass ran". Consumers read it as `.get("services", [])`, so absence is the honest
    # shape and not a special case anyone downstream must handle -- and it is what
    # leaves both committed live recordings valid without a paid re-record, since each
    # is a world model sealed before this key existed and neither records anything
    # this change touches.
    #
    # Assigned after the literal rather than folded into it because write_json sorts
    # keys, so insertion order cannot move a byte of the result.
    if services is not None:
        world["services"] = services
    write_json(run.world_model, world)
    _record_partials(run, assembled)
    return run.world_model, []


def _record_partials(run: RunPaths, assembled: list[Path]) -> None:
    """Record a digest per assembled partial into `manifest.json`.

    Closes a hole that had been confirmed on two domains: nothing in the sealed
    world model digested its inputs, so a partial rewritten *after* the seal left
    `validate --stage reconcile-seal`, `check-refs` and `gate-brief --gate 1`
    byte-identical to the clean run. `refs.check_partials` re-hashes against this,
    which makes it mechanically the same shape as `check_inputs` one layer in.

    In the manifest rather than in the sealed document, which is the ruling this
    implements: `01-world-model.json` keeps its path, schema and byte shape --
    frozen deliberately, so nothing below the seal can tell it was assembled pass by
    pass -- and the manifest is already where digests live here.

    Written only after the world model is, and never when the seal reported: a
    digest record for a document that was not written would describe an assembly
    that did not happen.

    Sorted, and every field content-derived, so two runs sealed from identical
    partials record an identical array. `relative_to(run.root)` with `as_posix()`
    rather than a raw path, so the record does not embed the machine the run
    happened on and does not change spelling on a different filesystem.

    A missing or unreadable manifest is left alone rather than raised on. The seal
    has already written its world model at this point, so raising would turn a
    successful assembly into a traceback, and a manifest that cannot be read is
    check_inputs' finding to report rather than this function's to discover.
    """
    try:
        manifest = read_json(run.manifest)
    except (ArtifactError, OSError):
        return
    if not isinstance(manifest, dict):
        return
    manifest["partials"] = sorted(
        (
            {
                "path": path.relative_to(run.root).as_posix(),
                "sha256": sha256_of(path),
                "bytes": path.stat().st_size,
            }
            for path in assembled
        ),
        key=lambda entry: entry["path"],
    )
    write_json(run.manifest, manifest)
