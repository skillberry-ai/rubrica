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
    component-aware and a JSON pointer starts with `/`: `intake.py:334` writes a
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
    # paths rendered whole. `intake.py:334` builds its fragment from a `Path`,
    # which never stringifies empty, so the pipeline cannot produce that shape;
    # a hand-edited manifest can, and it fails open with no marker and no finding.
    # `.strip()`, not truthiness: a `source_path` of `" "` partitions to `" "`,
    # which is truthy, reaches `commonpath`, raises, and fails open to no
    # shortening at all -- measured, the absolute staging path of the machine
    # rubrica ran on then shipped onto a page addressed outside this project,
    # which is the one outcome this function exists to prevent.
    real = sorted({base for base in (f.partition("#")[0].strip() for f in files) if base})
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


def _file_and_piece(path: str) -> tuple[str, str]:
    """One recorded source path as the file it names and the piece inside it.

    The one home for the sliced-path rule, because this page had three call sites
    for it and only two spellings: `inputs_read` and `target_brief_html._side_rows`
    each carried the clause, `_taken` carried none, and the site with none shipped
    `We went with traces_parsec-agent-metrics_20260713_115226.json#/11.` -- three
    of the 25 resolution lines on `run-20260826-090456`, each naming a path the
    owner cannot open, while `_side_rows` spelled the same source correctly two
    paragraphs above it on the same page. A document asking somebody whether it is
    true must not spell one of their files two ways.

    `piece` carries its `#` and is `""` unless the path is sliced, so a caller that
    labels the piece needs no second parse. Only a JSON pointer counts as one:
    `intake.py:334` writes a sliced input's `source_path` as
    `<container>#<json_pointer>` and a pointer always begins `/`, so a `#` anywhere
    else belongs to the owner's own filename. Without that clause `notes#2.md` was
    listed as `notes` in the section whose whole ask is "did we read the right
    files", and rendered as a piece `#2.md` that does not exist -- both measured.
    A path that is *only* a fragment ("#/0") has no file to separate the pointer
    from, so it comes back whole rather than as a piece of nothing -- and so does
    one whose container is nothing but whitespace (" #/1"), which is the same shape
    a space further on. Splitting that one would hand a caller a blank filename and
    a piece of it, which is the pair of blanks this helper exists to stop.

    `file` is `""` when there is nothing nameable in the whole path, which is the
    second thing every caller needs to know: a `source_path` of `" "` is truthy, and
    it reached the page as a blank `<span class="file">` and as `We went with  .` --
    two blanks in one section, measured on a hand-edited world model. `""` is what a
    caller tests to say so in words instead. `.strip()` decides nameability and
    nothing else strips: what can be named ships exactly as it was recorded.
    """
    base, sep, piece = path.partition("#")
    if sep and base.strip() and piece.startswith("/"):
        return base, sep + piece
    return (path if path.strip() else ""), ""


def _text(value) -> str:
    """`value` when it is a string, else `""`.

    A hand-edited `"unknown": 7` renders as an empty question rather than as the
    characters of an integer, and `""` is what the renderer tests to say it could
    not read the description. Never a stand-in sentence: invented prose in this
    document would be read as our assertion about the target.
    """
    return value if isinstance(value, str) else ""


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
            _text(source_path),
            _text(kind),
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
                locator=_text(locator),
                quote=_text(quote),
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


def _side_ids(value) -> list[str]:
    """The claim ids one side of a contradiction names -- `claim_a` or `claim_b`.

    One home for the two-branch rule, because both readers of a contradiction's
    sides need it: `disputed_claim_ids` below, which only wants the ids, and
    `_side` further down, which resolves them. A second spelling of one rule is
    how two reports come to disagree about one run.

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
    """
    return [value] if isinstance(value, str) else _strings(value)


def disputed_claim_ids(world_model: dict) -> frozenset[str]:
    """Every claim id either side of a contradiction names.

    Each side is read through `_side_ids` above, which owns the string-or-list
    rule and records why the two branches both exist.

    `_mapping` guards the read for the reason `_input_sources` above guards its
    own: a world model that parses but is not an object made this raise
    `AttributeError`, and this module's contract is that a report never raises on
    readable content.
    """
    out: set[str] = set()
    for contradiction in _dicts(_mapping(world_model).get("contradictions")):
        for side in ("claim_a", "claim_b"):
            out.update(_side_ids(contradiction.get(side)))
    return frozenset(out)


def provenance(claim_ids, index: dict[str, SourceRef], disputed: frozenset[str]) -> Provenance:
    """What the claims behind one element rest on.

    `disputed` is computed from the ids themselves rather than from the resolved
    refs: an element every one of whose claims is unresolvable has no files to
    show, and losing its dispute marker at the same time would hide the more
    important of the two facts.

    Two slices of one file count as two sources, deliberately. `intake.py:334`
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


def _world(run: RunPaths) -> dict | Marker:
    """The world model, or the marker naming why there is none.

    The one world-model reader in this module -- `disputes`, `open_questions` and
    the three tier-2 builders all come through here -- so no two of them can
    disagree about whether a run has a world model, or say it differently when it
    has not.

    A `Marker` rather than an empty result on a world model that parses to `{}`,
    and that is the right way round for every caller: `[]` would tell the target's
    owner we found no disagreements in their system, or that nothing about it was
    left unanswered, or that it can do nothing and holds no data -- where the truth
    is that we could not read a world model at all.
    """
    payload = _mapping(_quietly(run.world_model))
    if not payload:
        return _absent_or_malformed(
            run.world_model, "01-world-model.json", "nothing could be read from it"
        )
    return payload


def _refs(run: RunPaths) -> dict[str, SourceRef]:
    """The source index, with an unreadable one flattened to no sources at all.

    One home for that decision, because it is a decision and not a shape: dropping
    the marker turns every provenance line on the page into nothing, and read alone
    a blank provenance asserts to the owner that no document of theirs states the
    sentence above it. It is only safe because the renderer calls `source_index`
    itself and puts that same marker up as a run-level banner over the whole page,
    saying the citations are missing rather than that the sources are.

    The alternative -- returning the marker from every builder that needs refs --
    would lose the contradictions, the operations, the entities and the actors,
    all of which are readable and are the part an owner acts on. So the marker
    costs the page its citations, never its content.
    """
    index = source_index(run)
    return index if isinstance(index, dict) else {}


@dataclass(frozen=True)
class Headline:
    """The target, as the run names it.

    `notes` is optional in the schema and absent from the toy world and from both
    of the two most recent recordings, so the page must read without it:
    `interface` and `name` are the two required fields and the only two guaranteed
    to be there. Measured on the toy, `target` is exactly `{"interface": "mcp",
    "name": "ticketq"}`.
    """

    name: str
    interface: str
    notes: str


def headline(run: RunPaths) -> Headline | Marker:
    """The target's own name, how it is reached, and any note a pass wrote.

    Through `_world`, so this cannot disagree with the five builders below about
    whether the run has a description to show -- and so the renderer gets the
    world-model marker from the one call it already has to make, rather than
    reaching for `_world` itself to decide whether to raise its banner.

    No fallback to the manifest's `target.name`, which is also required there and
    also a string: a `Marker` here is what tells the renderer the description could
    not be read at all, and a headline assembled from a second artifact would
    silence that while leaving all five sections empty.
    """
    payload = _world(run)
    if isinstance(payload, Marker):
        return payload
    target = _mapping(payload.get("target"))
    return Headline(
        name=_text(target.get("name")),
        interface=_text(target.get("interface")),
        notes=_text(target.get("notes")),
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
        kind = _text(kind)
        if isinstance(source, str) and source:
            # The piece is dropped, which is the whole point of this group: an
            # input is not a file, and grouping on the raw `source_path` would
            # list one capture once per recorded call. 71 slices of one capture
            # still group as one file, which is that decision unchanged.
            #
            # Which part of the path is the file is `_file_and_piece`'s single
            # ruling for all three sites that ask -- here, `_taken` below, and
            # `target_brief_html`'s `_side_rows`. `_files_html` is deliberately not
            # one of them and says so in its own docstring: it asks only whether a
            # path can be named at all, which `.strip()` answers.
            #
            # The raw `source_path` is what survives when there is no piece to
            # drop, including a path with nothing nameable in it: this group's
            # arithmetic is `len(files) + slices` against the manifest, and
            # collapsing two unreadable paths onto one blank name made the second
            # record read as a *slice* of the first -- measured, `""` and `" "` in
            # one group rendered "1 more we could not name" under a "read as 3
            # pieces" tail, where they are two records and no slice of anything.
            # So the row keeps its own string, and the nameability question that
            # `_files_html` asks stays its own.
            name, piece = _file_and_piece(source)
            path = _shorten(name if piece else source, prefix)
        else:
            # The artifact id, for the reason SourceRef.path takes it: it names
            # something chaseable where a blank names nothing. A record with
            # neither still gets a row rather than being dropped, because
            # `len(files) + slices` is this group's arithmetic against the
            # manifest and a dropped record makes the count disagree with the
            # file silently -- which is the worse of the two failures.
            path = _text(artifact_id)
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


# `resolution` -> the sentence that follows a resolved disagreement. Only the two
# that need no file name live here; `preferred_a` and `preferred_b` are answered
# by naming the side, in `_taken` below.
_BOTH_POSSIBLE = "We are treating both as possible."
_UNRESOLVED_SIDE = "We took one side, but could not resolve which file states it."


@dataclass(frozen=True)
class Dispute:
    """One contradiction, with both sides resolved to places in the target.

    `nature` is carried verbatim. It is the sentence an owner acts on, and the
    world model writes it in their terms already -- "the design document states
    three actions; the tool module states four". `rationale` is deliberately not
    here: it is dense with claim ids and argues the case to a reader who already
    accepts the framing, and it stays available in `run-summary`.
    """

    id: str
    nature: str
    resolution: str
    taken: str
    side_a: tuple[SourceRef, ...]
    side_b: tuple[SourceRef, ...]


def _side(value, index: dict[str, SourceRef]) -> tuple[SourceRef, ...]:
    """One side of a contradiction, resolved. A string or a list of ids.

    `_side_ids` reads the two shapes, so this cannot disagree with
    `disputed_claim_ids` about which ids a side names.

    `sorted(set(...))`, matching `_taken` immediately below: a hand-edited
    `"claim_a": ["clm-notes-004", "clm-notes-004"]` rendered the same file quoting
    the same line twice under one side -- measured -- and the argument is less the
    duplicate than that the two adjacent functions read one list two ways. The
    schema requires a string here, so ordering is the hand-edited list's alone and
    sorting it is the deterministic answer.
    """
    return tuple(index[c] for c in sorted(set(_side_ids(value))) if c in index)


def _taken(resolution: str, side_a, side_b) -> str:
    """Which side was taken, as a sentence naming the file.

    Not "we went with the code": that needs code-ness inferred from `kind`, and
    the kinds measured do not support it -- reservation-service's capabilities
    each span `design_doc`, `mcp_tool_schema`, `source_code` and `trace` at once.
    A path the owner can open needs no inference and is checkable.
    """
    if resolution == "both_possible":
        return _BOTH_POSSIBLE
    if resolution == "preferred_a":
        chosen = side_a
    elif resolution == "preferred_b":
        chosen = side_b
    else:
        # `unresolved`, or a value the enum does not cover. Group B's whole point
        # is that we could not tell, and a sentence here would assert a decision
        # nobody made.
        return ""
    # The file, never the raw `ref.path`: this sentence tells the owner which of
    # their own sources we believed, so it has to name something they can open --
    # `_file_and_piece` owns that rule and records what shipped without it. Two
    # slices of one capture collapse to the one filename here, which is right for
    # a sentence about which file we went with and is why the piece is dropped
    # rather than labelled: `_side_rows` above has already shown both sides piece
    # by piece, and this line is the decision over them.
    names = (_file_and_piece(ref.path)[0] for ref in chosen)
    files = sorted({name for name in names if name})
    if not files:
        # Reached now by a side that resolves to nothing *and* by one whose paths
        # name nothing readable -- `We went with  .` was the second case before
        # `_file_and_piece` answered it, and this sentence is already the true one
        # for it: we took a side and cannot say which file states it.
        return _UNRESOLVED_SIDE
    return "We went with " + ", ".join(files) + "."


def disputes(run: RunPaths) -> list[Dispute] | Marker:
    """Every contradiction the world model records, both sides resolved.

    Ordered by id. Ranking by blast radius -- how many elements rest on a disputed
    claim -- would order better and the inputs already exist in `provenance`, but
    it is the one piece of genuinely new analysis in this design and shipping it
    unmeasured is how a report starts asserting a judgment it did not earn.

    One asymmetry, recorded rather than fixed: a hand-edited `"contradictions":
    "nope"` is dropped by `_dicts` and renders as `[]`, which tells the owner
    nothing in their system contradicted anything else -- the same false
    reassurance `_world` refuses for a world model that parses to `{}`. It stays
    because `_dicts` is how every reader in this module reads a list, and one
    spelling of that rule is worth more than a second marker branch for a shape
    layer 1 rejects outright.
    """
    payload = _world(run)
    if isinstance(payload, Marker):
        return payload
    refs = _refs(run)
    out = []
    for record in _dicts(payload.get("contradictions")):
        resolution = _text(record.get("resolution"))
        side_a = _side(record.get("claim_a"), refs)
        side_b = _side(record.get("claim_b"), refs)
        out.append(
            Dispute(
                id=_text(record.get("id")),
                # Verbatim, and `_text`'s `""` rather than a stand-in sentence
                # when the field is missing: the renderer says it could not read
                # the description, which is true, where invented prose would not
                # be. That is a ruling about *this* field, not just about the
                # helper -- `nature` is the one sentence an owner acts on, so an
                # invented one would be read as our assertion about their system.
                nature=_text(record.get("nature")),
                resolution=resolution,
                taken=_taken(resolution, side_a, side_b),
                side_a=side_a,
                side_b=side_b,
            )
        )
    return sorted(out, key=lambda d: d.id)


@dataclass(frozen=True)
class OpenQuestion:
    """One gap, as the question it is.

    Three fields of the schema's seven. `blocks` is a list of stage names, pure
    internals. `why_it_matters` is the harder omission and the acknowledged weak
    point of this design: it is the one field where owner-facing and internal
    prose are fused inside a single string -- "a scenario built on the empty
    outcome class has no stated ground truth" is rubrica talking about itself.
    Selecting it leaks, and splitting it means rewriting prose this document never
    rewrites. One generic sentence heads the group instead, and the cost is real:
    an owner is not told why each individual question matters.

    No provenance, deliberately. Every gap in all three runs measured carries no
    `claims` key -- 0 of 18, 0 of 19, 0 of 15 -- and a gap is by definition a
    place no claim reached, so the `unknown` prose is the whole record.
    """

    id: str
    subject: str
    unknown: str


def open_questions(run: RunPaths) -> list[OpenQuestion] | Marker:
    """Every gap the world model records, ordered by id."""
    payload = _world(run)
    if isinstance(payload, Marker):
        return payload
    out = []
    for record in _dicts(payload.get("gaps")):
        out.append(
            OpenQuestion(
                id=_text(record.get("id")),
                subject=_text(record.get("subject")),
                unknown=_text(record.get("unknown")),
            )
        )
    return sorted(out, key=lambda q: q.id)


# `outcome_class.kind` -> the words an owner reads. The enum is the schema's five.
#
# No mechanical absence detection anywhere near this table, deliberately. parsec
# records exactly one outcome class of each of the five kinds for each of its 39
# capabilities, and absence is expressed *in prose under the semantic kind*:
# `oc-qac-empty` is `kind: empty` carrying "No claim addresses what is returned
# when no cost data exists." So `kind` does not mark absence, no other field does,
# and the only alternative is string-matching model prose. The labels plus one
# legend line carry it instead.
_OUTCOME_LABELS = {
    "success": "On success",
    "empty": "When there is nothing to return",
    "not_found": "When it is not found",
    "error": "On error",
    "underspecified": "Not addressed",
}


@dataclass(frozen=True)
class Outcome:
    """One outcome class, relabelled. No provenance of its own -- see `Operation`."""

    label: str
    description: str


@dataclass(frozen=True)
class Operation:
    """One capability, as something the target can be asked to do."""

    id: str
    handle: str
    sentence: str
    params: tuple[str, ...]
    outcomes: tuple[Outcome, ...]
    provenance: Provenance


@dataclass(frozen=True)
class Field:
    """One field of an entity, as its name and the type the schema gives it."""

    name: str
    type: str


@dataclass(frozen=True)
class DataType:
    """One entity, as a kind of thing the target holds."""

    id: str
    name: str
    collection: str
    fields: tuple[Field, ...]
    relations: tuple[str, ...]
    rules: tuple[str, ...]
    provenance: Provenance


@dataclass(frozen=True)
class Persona:
    """One actor and what it is trying to do."""

    id: str
    name: str
    goals: tuple[str, ...]
    provenance: Provenance


def _params(value) -> tuple[str, ...]:
    """Each parameter as `name (type, required|optional)`."""
    out = []
    for record in _dicts(value):
        name = _text(record.get("name"))
        if not name:
            continue
        kind = _text(record.get("type")) or "unspecified"
        needed = "required" if record.get("required") is True else "optional"
        out.append(f"{name} ({kind}, {needed})")
    return tuple(out)


def _relations(value, names: dict[str, str]) -> tuple[str, ...]:
    """Each relation as `name → Target (cardinality)`, the target resolved.

    Resolved because `ent-comment` is an id no owner recognises and `Comment` is a
    word from their own vocabulary. Unresolvable ids keep the id: it names
    something, where a blank names nothing.

    A relation with no `name` is kept, where `_params` drops a param with no name,
    and the asymmetry is the point rather than an oversight: this record's payload
    is the *target*, so `→ Comment (many)` still tells an owner these records point
    at those, while a param reduced to a type and a required flag says nothing they
    could correct. What is dropped is the record with neither name nor target,
    which would render as bare punctuation.
    """
    out = []
    for record in _dicts(value):
        name = _text(record.get("name"))
        target = _text(record.get("target_entity_id"))
        if not (name or target):
            continue
        cardinality = _text(record.get("cardinality"))
        label = names.get(target, target)
        out.append(f"{name} → {label} ({cardinality})" if cardinality else f"{name} → {label}")
    return tuple(out)


def _rules(value) -> tuple[str, ...]:
    """Each invariant as one sentence, `prose` preferred over `statement`.

    `prose` is the human phrasing where a pass wrote one; the toy world and the
    committed recordings carry `statement` only, so the fallback is the normal
    path rather than the edge case.

    Stripped before the `or`, because the schema's `minLength: 1` admits `" "` and
    an unstripped `prose` of one space is truthy -- it would shadow a `statement`
    the run could read and render the rule as a blank line.
    """
    out = []
    for record in _dicts(value):
        sentence = _text(record.get("prose")).strip() or _text(record.get("statement")).strip()
        if sentence:
            out.append(sentence)
    return tuple(out)


def operations(run: RunPaths) -> list[Operation] | Marker:
    """Every capability, in the sealed world model's own order.

    Source order rather than sorted: two runs with identical partials produce a
    byte-identical world model, so the order is already reproducible, and it groups
    related capabilities the way the pass that wrote them chose to. Re-sorting would
    scramble that grouping for no gain in determinism.
    """
    payload = _world(run)
    if isinstance(payload, Marker):
        return payload
    refs = _refs(run)
    disputed = disputed_claim_ids(payload)
    out = []
    for record in _dicts(payload.get("capabilities")):
        sentence = _text(record.get("operation"))
        handle = _text(_mapping(record.get("binding")).get("tool")) or sentence
        outcomes = tuple(
            Outcome(
                # The raw kind when the enum does not cover it: a label we do not
                # have is no reason to drop an outcome, and the description is the
                # payload. Mislabelling it would be worse than showing the kind.
                label=_OUTCOME_LABELS.get(_text(o.get("kind")), _text(o.get("kind"))),
                description=_text(o.get("description")),
            )
            for o in _dicts(record.get("outcome_classes"))
        )
        out.append(
            Operation(
                id=_text(record.get("id")),
                handle=handle,
                sentence=sentence,
                params=_params(record.get("params")),
                outcomes=outcomes,
                # The capability's claims, never the outcome's: see this task's
                # note on the parked missing-`claims` ruling.
                provenance=provenance(_strings(record.get("claims")), refs, disputed),
            )
        )
    return out


def data_types(run: RunPaths) -> list[DataType] | Marker:
    """Every entity, with relation targets resolved to their names."""
    payload = _world(run)
    if isinstance(payload, Marker):
        return payload
    refs = _refs(run)
    disputed = disputed_claim_ids(payload)
    entities = _dicts(payload.get("entities"))
    # Both halves guarded, not just the name. Keyed on an unreadable id, this dict
    # holds `"" -> "Ticket"`, and a relation with no `target_entity_id` then looks
    # up `""` and renders as pointing at Ticket -- a relation this run never read,
    # in a document whose owner is being asked whether it is true. Both shapes fail
    # layer 1, and this feature exists to render a world model that does.
    names = {
        _text(e.get("id")): _text(e.get("name"))
        for e in entities
        if _text(e.get("id")) and _text(e.get("name"))
    }
    out = []
    for record in entities:
        out.append(
            DataType(
                id=_text(record.get("id")),
                name=_text(record.get("name")),
                collection=_text(record.get("collection")),
                fields=tuple(
                    Field(_text(f.get("name")), _text(f.get("type")))
                    for f in _dicts(record.get("fields"))
                    if _text(f.get("name"))
                ),
                relations=_relations(record.get("relations"), names),
                rules=_rules(record.get("invariants")),
                provenance=provenance(_strings(record.get("claims")), refs, disputed),
            )
        )
    return out


def personas(run: RunPaths) -> list[Persona] | Marker:
    """Every actor with its goals, plus one bucket for goals no actor claims.

    A goal whose `actor_id` resolves to nothing is still something the run believes
    about the target. Dropping it would make the description quietly incomplete,
    which is the one failure a document asking "is this accurate?" cannot afford.
    """
    payload = _world(run)
    if isinstance(payload, Marker):
        return payload
    refs = _refs(run)
    disputed = disputed_claim_ids(payload)
    goals = _dicts(payload.get("goals"))
    out = []
    # `set[int]`, not `set[str]`: what goes in is `id(g)`, the identity of the goal
    # record, so two goals with identical text still count separately.
    claimed: set[int] = set()
    for record in _dicts(payload.get("actors")):
        actor_id = _text(record.get("id"))
        mine = [g for g in goals if _text(g.get("actor_id")) == actor_id]
        claimed.update(id(g) for g in mine)
        out.append(
            Persona(
                id=actor_id,
                name=_text(record.get("name")),
                goals=tuple(_text(g.get("statement")) for g in mine if _text(g.get("statement"))),
                provenance=provenance(_strings(record.get("claims")), refs, disputed),
            )
        )
    orphaned = [g for g in goals if id(g) not in claimed]
    if orphaned:
        out.append(
            Persona(
                id="",
                name="Goals we could not attribute to a user",
                goals=tuple(
                    _text(g.get("statement")) for g in orphaned if _text(g.get("statement"))
                ),
                provenance=provenance(
                    [c for g in orphaned for c in _strings(g.get("claims"))], refs, disputed
                ),
            )
        )
    return out


def page(run: RunPaths) -> str:
    """The whole page. One entry point, so callers never import the markup half.

    Imported here rather than at module scope, exactly as `summary.run_summary`
    does it: `target_brief_html` imports this module for its dataclasses, so a
    top-level import would be circular.

    Named `page` rather than `target_brief` because `target_brief.target_brief`
    stutters at every call site; the subcommand's name lives in `cli.SUBCOMMANDS`
    and does not need repeating here.
    """
    from rubrica import target_brief_html

    return target_brief_html.render(run)
