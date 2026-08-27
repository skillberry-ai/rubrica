"""`target-brief`: the run's understanding of the target, addressed to its owners.

A composer, not a new analysis -- `summary.py`'s ruling and `brief.py`'s before
it. Every sentence on the page is read from an artifact or is arithmetic over
artifacts, so the page is reproducible and diffable, and nothing about producing
it dispatches a model.

What differs from `run-summary` is the audience, and it decides every judgment in
this module. This page never names a stage, a gate, a coverage number or a
scenario: it describes the *target*, and asks the people who own it to correct
it. So prose is selected and relabelled here but never rewritten -- shipping a
claim id inside a description is a smaller cost than laundering the sentence that
carries it, and a paraphrase in a document someone is asked to ratify is the
orchestrator's conclusion wearing a finding's clothes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Private helpers from three siblings, deliberately: `summary.py` imports the
# same four out of `brief.py` for the reason stated there, which is that a second
# spelling of one rule is how two reports come to disagree about one run.
from .brief import _dicts, _mapping, _quietly, _strings
from .paths import RunPaths
from .refs import _claims_by_artifact
from .summary import Marker, _absent_or_malformed


@dataclass(frozen=True)
class SourceRef:
    """One claim resolved to the place in the target that states it.

    `quote` is `""` rather than `None` when the evidence record carries none, and
    that is a permitted shape rather than a defect: `quote` is the one optional
    field of the three in the claims schema, and measured over the claims a world
    model cites, parsec quotes 224 of 230 and reservation-service 154 of 154 --
    but executive-agent only 67 of 126. So every rendering degrades to path plus
    locator, and nothing anywhere invents the missing line.
    """

    claim_id: str
    path: str
    locator: str
    quote: str
    kind: str


def _common_prefix(files: list[str]) -> str:
    """The directory every source path shares, or `""` when they share none.

    Stripped from every rendered path because `manifest.inputs[].source_path` is
    absolute *on the machine rubrica ran on*: all three runs measured share
    `/home/agent/runs/<target>`, which is where the corpus was staged and is not a
    path any owner recognises. What is left is the owner's own tree.

    The `#` fragment is cut off before any of that, because `os.path` is
    component-aware and a JSON pointer starts with `/`: `intake.py:333` writes a
    sliced input's `source_path` as `<container>#<json_pointer>`, so `commonpath`
    over two slices of one capture answers `.../trace.json#` -- measured -- and
    `_shorten` then matches that against nothing and strips nothing. It never
    mis-strips, only under-strips, so the failure it caused was the staging path
    of the machine rubrica ran on shipping to the target's owner, which is the one
    outcome this function exists to prevent.
    """
    # The emptiness filter is load-bearing, not defensive: `_input_sources` yields
    # "" for a record whose `source_path` is not a string, and one "" makes
    # `commonpath` raise, which the handler below reads as "no shared root" --
    # silently disabling shortening for every other path in the run.
    #
    # It filters *after* the partition because the value that must be non-empty is
    # the base, not the raw entry, and a fragment-only `source_path` ("#/0") is
    # what tells the two apart: it is non-empty raw and empty once partitioned, so
    # testing the raw string lets "" into the set anyway. Measured -- filtering
    # first, `["#/0", "/a/b/one.py", "/a/b/two.py"]` returned "" and both absolute
    # paths rendered whole. `intake.py:333` builds its fragment from a `Path`,
    # which never stringifies empty, so the pipeline cannot produce that shape;
    # a hand-edited manifest can, and it fails open with no marker and no finding.
    real = sorted({base for base in (f.partition("#")[0] for f in files) if base})
    if not real:
        return ""
    try:
        # dirname for a single path, not commonpath: `commonpath(["/a/b/x.py"])`
        # returns the file itself, which would strip the filename and leave every
        # row blank.
        prefix = os.path.commonpath(real) if len(real) > 1 else os.path.dirname(real[0])
    except ValueError:
        # Mixed absolute and relative paths, or different drives. No shared root
        # exists, and a half-trimmed path is worse than an untrimmed one.
        return ""
    return "" if prefix in ("", os.sep) else prefix


def _shorten(path: str, prefix: str) -> str:
    """`path` with `prefix` removed, keeping any `#` slice fragment.

    The fragment is load-bearing: parsec's 269 inputs are 199 distinct files
    because 71 `trace` inputs are 71 slices of one capture, and the fragment is
    the only thing telling them apart.
    """
    base, sep, fragment = path.partition("#")
    if prefix and base.startswith(prefix + os.sep):
        base = base[len(prefix) + 1 :]
    return base + sep + fragment


def _input_sources(run: RunPaths) -> dict[str, tuple[str, str]]:
    """artifact_id -> (source_path, kind), from the manifest and nothing else."""
    out: dict[str, tuple[str, str]] = {}
    for record in _dicts(_mapping(_quietly(run.manifest)).get("inputs")):
        artifact_id = record.get("artifact_id")
        if not isinstance(artifact_id, str):
            continue
        source_path = record.get("source_path")
        kind = record.get("kind")
        out[artifact_id] = (
            source_path if isinstance(source_path, str) else "",
            kind if isinstance(kind, str) else "",
        )
    return out


def source_index(run: RunPaths) -> dict[str, SourceRef] | Marker:
    """Every claim id in `01-claims/`, resolved to a place in the target.

    A `Marker` rather than an empty dict when the directory cannot be read.
    `list_json` raises `UsageError` on an unreadable directory -- a `ValueError`
    and **not** an `OSError`, which is why the guard below cannot be narrower --
    and `summary.py` catches the same thing for the same reason: so a page
    renders a marker instead of crashing. That is a promise about the page and
    not about an exit code.

    Empty-dict-on-failure was the shape rejected: this page leaves the project,
    and a document that quietly showed no evidence would be indistinguishable
    from a target that has none.
    """
    try:
        by_artifact = _claims_by_artifact(run)
    except Exception:  # deliberate: list_json raises UsageError, not an OSError
        return _absent_or_malformed(run.claims_dir, "01-claims/", "nothing could be read from it")
    where = _input_sources(run)
    prefix = _common_prefix([source for source, _ in where.values()])
    index: dict[str, SourceRef] = {}
    for claims in by_artifact.values():
        for claim in claims:
            claim_id = claim.get("id")
            if not isinstance(claim_id, str) or claim_id in index:
                continue
            records = _dicts(claim.get("evidence"))
            if not records:
                continue
            # Prefer a record carrying a quote over the first record. Measured:
            # executive-agent quotes only 67 of the 126 claims its world model
            # cites, so evidence[0] blindly would drop quotes the run has.
            chosen = next(
                (r for r in records if isinstance(r.get("quote"), str) and r["quote"].strip()),
                records[0],
            )
            artifact_id = chosen.get("artifact_id")
            source, kind = (
                where.get(artifact_id, ("", "")) if isinstance(artifact_id, str) else ("", "")
            )
            locator = chosen.get("locator")
            quote = chosen.get("quote")
            index[claim_id] = SourceRef(
                claim_id=claim_id,
                # The artifact id when the manifest does not register the
                # artifact: it names *something* the reader can chase, where a
                # blank names nothing. Never a constructed path.
                path=_shorten(source, prefix) if source else (artifact_id or ""),
                locator=locator if isinstance(locator, str) else "",
                quote=quote if isinstance(quote, str) else "",
                kind=kind,
            )
    return index


@dataclass(frozen=True)
class Provenance:
    """What an element rests on, in the three terms that measurably discriminate.

    The first design badged each element with its claims' `derivation` -- "your
    documents state this" / "we read this off your code". Measured per element it
    reads the same on every row: all 39 parsec capabilities, all 30 entities, all
    26 goals and both actors come out `stated`, because `derivation` records
    whether *an artifact asserted* the fact and source code is an artifact that
    asserts things. Capability `confidence` is worse -- all 39 `high`. A badge
    that never varies is not neutral in a document someone is asked to ratify: it
    implies a distinction was checked.

    These three vary. Across the three runs measured: capabilities resting on one
    source are 4 of 39, **13 of 37**, and 0 of 5; entities on one source are **28
    of 30**, 18 of 18, 1 of 4; capabilities a contradiction touches are 6 of 39,
    **16 of 37**, 2 of 5. And each states something an owner can act on without
    knowing what rubrica is -- 13 of executive-agent's 37 operations rest on a
    design document alone, with no schema, no code and no trace behind them.
    """

    files: tuple[str, ...]
    kinds: tuple[str, ...]
    disputed: bool

    @property
    def single_source(self) -> bool:
        """Whether exactly one file is behind this element.

        A property rather than a stored field so it cannot disagree with `files`.
        """
        return len(self.files) == 1


def disputed_claim_ids(world_model: dict) -> frozenset[str]:
    """Every claim id either side of a contradiction names.

    The schema *requires* a string: `contradiction` lists `claim_a` and `claim_b`
    in `required`, both `$ref`-ing `$defs/id`, which is `{"type": "string"}`. So a
    list fails layer 1, the string branch is the conformant path, and the list
    branch is tolerance for a hand-edit made after validation passed -- which is
    the shape a human gate invites.

    `_strings` reads that branch because it *drops* a non-string member instead of
    raising, which is what the `{"claim_a": 7}` case pins. It does not explode a
    string into characters: it returns `[]` for anything that is not a list
    (`brief.py:165-167`), so routing a conformant string through it would drop the
    id **silently** -- measured, an element citing `clm-notes-004` came out
    undisputed and the id vanished. That silent drop, not a character explosion,
    is why the string branch exists. (The character explosion is the failure
    `_strings` was written to *prevent*, described in its own docstring; an earlier
    revision of this comment transposed it onto `_strings` itself and was wrong.)

    `_mapping` guards the read for the reason `_input_sources` above guards its
    own: a world model that parses but is not an object made this raise
    `AttributeError`, and this module's contract is that a report never raises on
    readable content.
    """
    out: set[str] = set()
    for contradiction in _dicts(_mapping(world_model).get("contradictions")):
        for side in ("claim_a", "claim_b"):
            value = contradiction.get(side)
            if isinstance(value, str):
                out.add(value)
            else:
                out.update(_strings(value))
    return frozenset(out)


def provenance(claim_ids, index: dict[str, SourceRef], disputed: frozenset[str]) -> Provenance:
    """What the claims behind one element rest on.

    `disputed` is computed from the ids themselves rather than from the resolved
    refs: an element every one of whose claims is unresolvable has no files to
    show, and losing its dispute marker at the same time would hide the more
    important of the two facts.

    Two slices of one file count as two sources, deliberately. `intake.py:333`
    writes a sliced input's `source_path` as `<container>#<json_pointer>`, so
    `files` holds `trace.json#/12` and `trace.json#/41` separately and such an
    element is not `single_source`. That is what "how many sources back this"
    asks: parsec's 71 trace inputs are 71 slices of one capture and 71
    independent observations of the target, and collapsing them on the container
    would tell an owner that 71 recorded interactions are one piece of evidence.
    `kinds` does collapse them, because both slices are the same kind of file --
    the two counts are independent by design.
    """
    ids = [c for c in claim_ids if isinstance(c, str)]
    resolved = [index[c] for c in ids if c in index]
    return Provenance(
        files=tuple(sorted({r.path for r in resolved if r.path})),
        kinds=tuple(sorted({r.kind for r in resolved if r.kind})),
        disputed=any(c in disputed for c in ids),
    )


@dataclass(frozen=True)
class InputGroup:
    """The files of one kind in one directory that the run read.

    `files` holds bare names and `directory` the path they sit under, so a
    rendering that wants the whole path joins the two: the directory is factored
    out because it is what the group is keyed on, and repeating it on every row of
    a group is how a 199-file listing becomes unreadable.

    `slices` is neither a count of inputs nor a count of slices: it is how many
    inputs this group holds *beyond* one per file, so `len(files) + slices` is the
    number of manifest records the group collapsed. A `#/NN` fragment marks one
    slice of a sliced artifact, so parsec's 71 trace inputs over one capture come
    out as a single-file group with `slices` 70 -- measured, and 1 + 70 == 71.
    Rendering that as 71 files would misstate what we read, and "1 trace file,
    read as 71 recorded calls" is both shorter and true.
    """

    kind: str
    directory: str
    files: tuple[str, ...]
    slices: int


def inputs_read(run: RunPaths) -> list[InputGroup] | Marker:
    """Every file the run admitted, grouped by kind and directory.

    First on the page, because it is the one question the pipeline structurally
    cannot ask itself. Gate 0 decides what the run can ever know and nothing below
    `intake` reads the corpus again, so a declined candidate is gone as completely
    as if the corpus never held it -- and the party that selected the inputs
    cannot also be the party that ratifies the selection.
    """
    # The manifest is read here as well as through `_input_sources`, and that is
    # not a duplicate read: `_input_sources` returns `{}` for an absent manifest
    # and for an unreadable one alike, so it cannot tell the two facts apart. This
    # is `summary.py`'s spelling of that test (`header`, `inputs`), so the two
    # pages cannot disagree about which fact a run is showing.
    #
    # The two reads can also diverge, and the `_input_sources` one is kept anyway:
    # it drops a record whose `artifact_id` is not a string and collapses
    # duplicate ids, where the loop below walks every record. That difference
    # reaches only `prefix`, where it fails open into rendering an unstripped
    # staging path -- the one outcome `_common_prefix` exists to prevent. Deriving
    # `prefix` from `records` instead would close that and is still the wrong fix,
    # because `source_index` shortens against the `_input_sources` basis: two bases
    # would let one file render `src/x.py` here and `x.py` in an evidence row, and
    # a page the owner is asked to ratify must not spell one path two ways.
    payload = _mapping(_quietly(run.manifest))
    if not payload:
        return _absent_or_malformed(run.manifest, "manifest.json", "nothing could be read from it")
    records = _dicts(payload.get("inputs"))
    where = _input_sources(run)
    prefix = _common_prefix([source for source, _ in where.values()])
    # (kind, directory) -> [file, ...] with repeats, so `slices` can be the
    # difference between inputs seen and distinct files.
    seen: dict[tuple[str, str], list[str]] = {}
    for record in records:
        artifact_id = record.get("artifact_id")
        source = record.get("source_path")
        kind = record.get("kind")
        kind = kind if isinstance(kind, str) else ""
        if isinstance(source, str) and source:
            # The fragment is cut, which is the whole point of this group: an
            # input is not a file, and grouping on the raw `source_path` would
            # list one capture once per recorded call.
            path = _shorten(source.partition("#")[0], prefix)
        else:
            # The artifact id, for the reason SourceRef.path takes it: it names
            # something chaseable where a blank names nothing. A record with
            # neither still gets a row rather than being dropped, because
            # `len(files) + slices` is this group's arithmetic against the
            # manifest and a dropped record makes the count disagree with the
            # file silently -- which is the worse of the two failures.
            path = artifact_id if isinstance(artifact_id, str) else ""
        # `os.sep`, not a literal: `_shorten` and `_common_prefix` do their
        # filesystem-path arithmetic on this same string three lines up, and one
        # spelling in one flow is the point -- a consistency change, not a
        # measured one, and behaviour-preserving on posix.
        #
        # Plain `name`: `rpartition` already returns the whole path as `name` when
        # there is no separator, so an `or path` fallback is dead everywhere the
        # pipeline can reach and live only on a trailing-slash `source_path`,
        # where it would set both `directory` and the name to the directory and a
        # renderer joining the two would print `dir/dir/`.
        directory, _, name = path.rpartition(os.sep)
        seen.setdefault((kind, directory), []).append(name)
    groups = []
    for (kind, directory), names in sorted(seen.items()):
        files = tuple(sorted(set(names)))
        groups.append(
            InputGroup(
                kind=kind,
                directory=directory,
                files=files,
                slices=len(names) - len(files),
            )
        )
    return groups
