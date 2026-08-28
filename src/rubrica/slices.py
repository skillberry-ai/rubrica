"""Cutting a catalogue into slices a dispatch can hold.

The catalogue is the only input triage has, and on a real corpus it does not fit
one dispatch: 595KB / 351 candidates killed three of them, one in context
compaction and one by exhausting its whole dollar budget. Chunked reads do not
help -- reading 595KB in thirty pieces is still having read 595KB -- so the fix
is to bound what any single dispatch reads, which means partitioning the
candidates rather than summarising them.

Code rather than a prompt, and that inverts the reconcile family on purpose:
cutting requires seeing every candidate, so a prompt that cut the slices would
itself be the unbounded dispatch. What makes it acceptable where a heuristic
filter would not is that nothing here *decides* anything -- every candidate
still reaches a member, still gets a reasoned disposition, and is still
overrulable per candidate by a human at gate 0. A slice is a reading unit, not
a decision unit.

Two design choices were measured, not guessed, and the measurement is why they
are rejected rather than merely undocumented:

* Bottom-up roll-up (merge small leaves upward until they fill the cap) was
  tried first and produced 20 slices on parsec with both failure modes at
  once: an 85-file kind-split mega-slice (small leaves rolled up past the
  point of coherence) and eight 1-candidate orphans (leaves too large to roll
  up into anything, left alone). Top-down recursion -- descend only where the
  cap forces it, keep everything else whole -- produced 11.
* First-fit-decreasing packing (sort every unit by size, greedy-fill) was
  tried for the final pass and rejected: it fills a slice by size alone,
  which spends the coherence the grouping key just bought. Packing here is
  adjacent siblings only, in the order the recursion already produced.

The one fact this module exists to protect: on a real 130-element trace
capture, `error_markers` -- digest.py's only structural failure signal --
fires on exactly one element, the run's only evidence of what the target does
when something goes wrong. Clustering container elements by digest signature
before splitting (§5 step 5) makes that element a singleton by construction,
not by luck of where a byte-count split happened to land.
"""

from __future__ import annotations

import posixpath
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

from rubrica.artifacts import canonical_bytes, read_json, write_json
from rubrica.errors import UsageError
from rubrica.paths import RunPaths, list_json

# The harness refuses a whole-file Read at 256KB, and a member's shard must be
# one Read. 64KB leaves room for the request/policy head every shard carries
# plus indentation, and it produced 11 slices on parsec, 5 on appworld, 5 on
# tau2, 7 on tau2+trajectories -- four real catalogues, none of them close to
# needing a second dispatch per slice.
DEFAULT_SLICE_BYTES = 65536


@dataclass(frozen=True)
class Slice:
    """One reading unit: a bounded set of candidates one dispatch can hold.

    `groups` and `provenance` both describe the §5 step-1 grouping fact each
    member candidate belongs to (a container id, or a corpus (root_index,
    dirname)) -- never the finer units a splitter produced internally, because
    a member holding part of a family cannot otherwise know it split at all.
    """

    id: str
    label: str
    groups: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    provenance: tuple[dict, ...]


@dataclass(frozen=True)
class _Unit:
    """One atomic packing block.

    `_pack_adjacent` combines units with their neighbours or gives one a slice
    to itself; it never breaks a unit apart, because a unit *is* the thing a
    splitter already decided must not be split further (a family that fits,
    or the finest chunk a leaf fallback could produce).

    `root_index` is stamped onto every unit a corpus top-level group produces,
    after the splitter runs rather than by the splitter itself: tagging is the
    same for every unit one group yields regardless of how it split, so it is
    plan_slices's job, not _split_tree's or _split_by_kind_then_bytes's.
    `None` for every container/solo unit, which carries no such boundary.
    """

    label: str
    members: tuple[dict, ...]
    root_index: int | None = None


def row_bytes(candidate: dict) -> int:
    """A candidate's canonical byte cost -- what actually lands on disk.

    Via `artifacts.canonical_bytes` rather than a hand-rolled serializer,
    because a shard's real size on disk is what a dispatch's Read call pays
    for, and the two must never be allowed to disagree.
    """
    return len(canonical_bytes(candidate))


def oversized_rows(
    candidates: list[dict], *, cap: int = DEFAULT_SLICE_BYTES
) -> list[tuple[str, int]]:
    """`(candidate_id, bytes)` for every row over `cap`, in input order.

    A row this large cannot be made to fit by any splitter here -- there is
    nothing smaller than one candidate to split it into -- so reporting it is
    the only honest move. Task 3 turns this into a refused catalogue rather
    than a slice this module would otherwise have to silently truncate.
    """
    return [
        (candidate["candidate_id"], n)
        for candidate in candidates
        if (n := row_bytes(candidate)) > cap
    ]


# Four of the eight exclusion_reason values embed a judgment that could be
# wrong, and those are the ones an operator could dispute at gate 0: an
# --exclude that over-reached, a permissions failure, a near-duplicate that is
# not one, a heuristic vendored-detection. The other four -- gitignored,
# vcs_metadata, binary, lockfile -- are mechanical facts about a file with no
# scoping decision in them. Measured on the tau2 catalogue: keeping these four
# kept all 11 `duplicate` entries and dropped 123 `binary` paths, 1,062 bytes
# against 12,914 for the whole array.
DISPUTABLE_EXCLUSION_REASONS = ("duplicate", "operator_excluded", "unreadable", "vendored")

# A byte budget rather than an entry count, and the reason is a defect open
# against this repository right now: digest's `names` is capped at 64 entries
# and unbounded in characters, so one verbose tool name makes survey exit 2 on
# a row that used to be small. Paths vary in length far more than tool names
# do, so a count cap here would reproduce that defect in a new place.
# Truncating a path is not the alternative -- a mangled path cannot be
# disputed at a gate -- so the block is bounded rather than its contents.
MAX_EXCLUDED_ENTRY_BYTES = 8192


def excluded_summary(excluded: list) -> dict:
    """`excluded` compressed to a tally plus the paths an operator could dispute.

    Shared with refs.check_slices rather than mirrored there, the same way
    check 5 recomputes a slice's bytes through row_bytes: what the check is
    for is drift between the plan and the catalogue -- a plan minted before a
    human adopted a projection at gate 0 -- not whether this arithmetic is
    right. A second implementation would let a defect in this one pass both.

    `total` counts every element of the array, including entries this function
    keeps no path for and entries too malformed to carry a reason, because it
    is the only thing at gate 0 that separates "the corpus had 123 binaries"
    from "the corpus had none".
    """
    tally: Counter[str] = Counter()
    entries: list[dict] = []
    truncated = False
    for entry in excluded:
        if isinstance(entry, dict) and isinstance(reason := entry.get("reason"), str):
            tally[reason] += 1
        else:
            continue
        if truncated or reason not in DISPUTABLE_EXCLUSION_REASONS:
            continue
        # Stop filling rather than skip to whatever still fits: the kept list
        # must be a prefix, so two corpora differing in one long path produce
        # entry lists one of which is a prefix of the other. A prefix is
        # explainable at a gate; a subset chosen by size is not.
        if len(canonical_bytes([*entries, entry])) > MAX_EXCLUDED_ENTRY_BYTES:
            truncated = True
            continue
        entries.append(entry)
    return {
        "total": len(excluded),
        "by_reason": dict(sorted(tally.items())),
        "entries": entries,
        "entries_truncated": truncated,
    }


def candidate_bytes_index(candidates: list[dict]) -> dict[str, int]:
    """`candidate_id` -> that candidate's own catalogue `bytes`, for every candidate.

    Source file size, never row_bytes' serialized size. digest.py clamps a
    skeleton at 128 nodes, so two candidates of very different evidential size
    serialize to nearly the same row once both are past the cap -- a metric
    that saturates stops discriminating exactly where rb-triage-objective's
    weight.bytes needs it to.

    Every candidate, admissible or not: plan_slices partitions all of them and
    a surface's `evidence` may name any. A map rather than a list of objects
    because it measured 41.1 bytes per candidate against 80.1 for the list
    form, on a field the whole point of which is to be small.

    Shared with refs.check_slices for the reason excluded_summary is.
    """
    return {
        cid: b
        for candidate in candidates
        if isinstance(candidate, dict)
        and isinstance(cid := candidate.get("candidate_id"), str)
        # `isinstance(True, int)` is True in Python, so a `bytes: true` would
        # otherwise index as the integer 1. The standing guard in this repo,
        # present at the guard clauses in triage.py:456, manifest.py:176,
        # intake.py:247, seal.py:311.
        and isinstance(b := candidate.get("bytes"), int)
        and not isinstance(b, bool)
    }


def catalogue_facts(catalogue: dict) -> dict:
    """Everything rb-triage-objective may know about the catalogue, without opening it.

    Named `catalogue_facts` and not `catalogue_projection`: `projection`
    already means "a manufactured artifact admitted to close a deficiency"
    throughout this subsystem, and a second sense of the word in the most
    projection-dense part of the codebase is a readability cost with no
    upside. The design spec specs the other name; it is recorded history and
    is not edited to match.

    `request` and `policy` are copied verbatim, which is not a new pattern:
    write_slices' docstring already argues for the shards carrying both rather
    than each member seeking a sorted-keys catalogue for two small fields.
    """
    return {
        "request": catalogue["request"],
        "policy": catalogue["policy"],
        "excluded": excluded_summary(catalogue["excluded"]),
        "candidate_bytes": candidate_bytes_index(catalogue.get("candidates", [])),
    }


def _str_tuple(value: object) -> tuple[str, ...]:
    """Every string in `value`, sorted -- or an empty tuple for anything else.

    One place both halves of `_signature`'s key go through, so a `names` that
    is not a list, or a list holding a non-string, degrades to "no signal"
    instead of raising.
    """
    if not isinstance(value, list):
        return ()
    return tuple(sorted(item for item in value if isinstance(item, str)))


def _signature(candidate: dict) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The §5 step-5 clustering key: `(heuristics_fired, names[:6])`, both sorted.

    Tolerates every malformed shape a digest can arrive in -- missing
    `digest`, missing `heuristics_fired`, a `names` that is not a list -- by
    design: a malformed digest is check-refs' finding in a later task, not a
    crash here. Every candidate with no readable signal collapses to the same
    `((), ())` signature, which is the correct outcome for an element this
    module cannot see into: they cluster together rather than each becoming
    its own family.
    """
    digest = candidate.get("digest")
    digest = digest if isinstance(digest, dict) else {}
    fired = _str_tuple(digest.get("heuristics_fired"))
    names = digest.get("names")
    names_head = names[:6] if isinstance(names, list) else []
    return (fired, _str_tuple(names_head))


def _group_key(candidate: dict) -> tuple:
    """The §5 step-1 grouping fact, at the grain provenance needs.

    Container elements group by `container.candidate_id`. Corpus files group
    by `(root_index, dirname(path))` -- the exact directory, not the whole
    root -- because provenance answers "how much of *this* family is
    elsewhere", and tagging a whole root with one label would hide that one
    specific directory got split. `root_index` is load-bearing: two roots may
    each hold `src/`, and every real catalogue measured is single-root, so
    nothing on disk would catch a merge that dropped it.

    Anything with neither a resolvable container nor both `path` and
    `root_index` -- a malformed candidate, or a `projection`-origin one, which
    carries `path` but no `root_index` -- gets its own singleton group rather
    than a guessed one: guessing is exactly the two-root merge bug above.
    """
    origin = candidate.get("origin")
    if origin == "container_element":
        container = candidate.get("container")
        container_id = container.get("candidate_id") if isinstance(container, dict) else None
        if isinstance(container_id, str) and container_id:
            return ("container", container_id)
        return ("solo", candidate.get("candidate_id", ""))
    path = candidate.get("path")
    root_index = candidate.get("root_index")
    if isinstance(path, str) and isinstance(root_index, int) and not isinstance(root_index, bool):
        return ("corpus", root_index, posixpath.dirname(path))
    return ("solo", candidate.get("candidate_id", ""))


def _group_label(key: tuple) -> str:
    """The human-readable spelling of a `_group_key` tuple."""
    if key[0] == "container":
        return f"container:{key[1]}"
    if key[0] == "corpus":
        _, root_index, dirname = key
        return f"corpus:{root_index}:{dirname or '.'}"
    return f"solo:{key[1]}"


def _top_key(candidate: dict) -> tuple:
    """The §5 step-1 fact used to decide *what a splitter sees*.

    Coarser than `_group_key` for corpus candidates on purpose: a splitter
    needs a whole root's worth of files to recurse into its directory tree,
    not one directory at a time, so this groups by `root_index` alone and
    lets `_split_tree` discover the directories underneath. Same two
    fallbacks as `_group_key`, for the same reason.
    """
    origin = candidate.get("origin")
    if origin == "container_element":
        container = candidate.get("container")
        container_id = container.get("candidate_id") if isinstance(container, dict) else None
        if isinstance(container_id, str) and container_id:
            return ("container", container_id)
        return ("solo", candidate.get("candidate_id", ""))
    path = candidate.get("path")
    root_index = candidate.get("root_index")
    if isinstance(path, str) and isinstance(root_index, int) and not isinstance(root_index, bool):
        return ("corpus", root_index)
    return ("solo", candidate.get("candidate_id", ""))


def _top_label(key: tuple) -> str:
    """The human-readable spelling of a `_top_key` tuple's whole-group unit."""
    if key[0] == "container":
        return f"container:{key[1]}"
    if key[0] == "corpus":
        return f"corpus:{key[1]}"
    return f"solo:{key[1]}"


def _top_level_groups(candidates: list[dict]) -> list[tuple[tuple, list[dict]]]:
    """Every §5 step-1 top-level group, keyed and member-sorted for determinism.

    Both the group keys and each group's members are sorted here -- by tuple
    and by `candidate_id` respectively -- so `plan_slices` is invariant to the
    order candidates arrived in, which `test_planning_is_deterministic` holds
    to exactly.
    """
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for candidate in candidates:
        buckets[_top_key(candidate)].append(candidate)
    return [(key, sorted(buckets[key], key=lambda c: c["candidate_id"])) for key in sorted(buckets)]


def _chunk_by_bytes(members: list[dict], cap: int) -> list[list[dict]]:
    """Sequential greedy packing of already-sorted rows, one adjacent run per chunk.

    The last lever a leaf bucket has: once §5 step 4's kind split still leaves
    a bucket over cap, individual candidate rows are the finest unit left, and
    adjacent-only packing (the same rule `_pack_adjacent` uses at the unit
    grain) is what keeps a directory's files in `candidate_id` order rather
    than scattering them by size.
    """
    chunks: list[list[dict]] = []
    current: list[dict] = []
    total = 0
    for member in members:
        n = row_bytes(member)
        if current and total + n > cap:
            chunks.append(current)
            current, total = [], 0
        current.append(member)
        total += n
    if current:
        chunks.append(current)
    return chunks


def _split_by_kind_then_bytes(label: str, members: list[dict], cap: int) -> list[_Unit]:
    """§5 step 4: the leaf fallback when a directory (or an oversized
    signature family) is still over cap with nothing structural left to
    descend into. Splits by `kind` first, then by bytes within a kind,
    sorting by `candidate_id` throughout so the result is deterministic.
    """
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for member in sorted(members, key=lambda m: m["candidate_id"]):
        by_kind[member.get("kind", "")].append(member)

    units: list[_Unit] = []
    for kind in sorted(by_kind):
        kind_members = by_kind[kind]
        total = sum(row_bytes(m) for m in kind_members)
        if total <= cap:
            units.append(_Unit(f"{label} kind={kind}", tuple(kind_members)))
            continue
        for chunk in _chunk_by_bytes(kind_members, cap):
            first, last = chunk[0]["candidate_id"], chunk[-1]["candidate_id"]
            units.append(_Unit(f"{label} kind={kind} [{first}..{last}]", tuple(chunk)))
    return units


def _split_container(label: str, members: list[dict], cap: int) -> list[_Unit]:
    """§5 step 5: cluster an oversized container's elements by digest
    signature before splitting, largest family first.

    Largest first so packing (adjacent siblings, §5 step 6) spends the cap on
    the family that dominates the container before it ever reaches the small
    ones step 7 exists to combine -- and so a singleton family sorts last,
    where nothing bigger is still waiting to absorb it into a shared slice.
    Measured on parsec's 130 real trace elements: 44 distinct signatures, with
    `error_markers` firing on exactly one of them. Clustering first means that
    one element is a family of one by construction, never a fragment of a
    byte-count split that happened to land where it did.

    A family that itself exceeds the cap has nothing left to cluster on --
    §5 step 4's kind/bytes fallback is the only lever remaining.
    """
    families: dict[tuple, list[dict]] = defaultdict(list)
    for member in sorted(members, key=lambda m: m["candidate_id"]):
        families[_signature(member)].append(member)

    ordered = sorted(families, key=lambda sig: (-sum(row_bytes(m) for m in families[sig]), sig))
    units: list[_Unit] = []
    for signature in ordered:
        family = families[signature]
        total = sum(row_bytes(m) for m in family)
        sig_label = f"{label} sig={signature}"
        if total <= cap:
            units.append(_Unit(sig_label, tuple(family)))
        else:
            units.extend(_split_by_kind_then_bytes(sig_label, family, cap))
    return units


def _split_tree(prefix: str, members: list[dict], cap: int) -> list[_Unit]:
    """§5 step 3: top-down recursion over one root's directory tree.

    `members` are every corpus candidate under `prefix` (the whole root, on
    the first call). If the subtree fits, it is one unit -- whole, even if it
    spans several directories, because nothing forced a split. Otherwise this
    descends one directory level at a time, keeping each child's whole subtree
    together and recursing only into a child still over cap; a child with no
    further subdirectory (files sitting directly in `prefix`) is exactly the
    `(root_index, dirname)` leaf group §5 step 1 names, and falls through to
    §5 step 4 if it alone is still oversized.

    Bottom-up roll-up was tried instead and rejected -- see the module header
    for the parsec measurement (an 85-file mega-slice plus eight orphans) that
    made top-down the kept design.
    """
    total = sum(row_bytes(m) for m in members)
    root_index = members[0]["root_index"]
    label = f"corpus:{root_index}:{prefix or '.'}"
    if total <= cap:
        return [
            _Unit(
                f"{label} ({len(members)} candidates)",
                tuple(sorted(members, key=lambda m: m["candidate_id"])),
            )
        ]

    children: dict[str, list[dict]] = defaultdict(list)
    for member in sorted(members, key=lambda m: m["candidate_id"]):
        rel = member["path"][len(prefix) :].lstrip("/") if prefix else member["path"]
        head, _, rest = rel.partition("/")
        # rest == "" means this file has no further subdirectory to descend
        # into: it lives directly in `prefix`, so it belongs to the leaf
        # bucket keyed "" rather than to a child named after itself.
        children[head if rest else ""].append(member)

    units: list[_Unit] = []
    for name in sorted(children):
        child_members = children[name]
        child_total = sum(row_bytes(m) for m in child_members)
        if name == "":
            leaf_label = f"{label} (leaf)"
            if child_total <= cap:
                units.append(
                    _Unit(f"{leaf_label} ({len(child_members)} candidates)", tuple(child_members))
                )
            else:
                units.extend(_split_by_kind_then_bytes(leaf_label, child_members, cap))
        elif child_total <= cap:
            child_prefix = f"{prefix}/{name}" if prefix else name
            child_label = f"corpus:{root_index}:{child_prefix} ({len(child_members)} candidates)"
            units.append(_Unit(child_label, tuple(child_members)))
        else:
            child_prefix = f"{prefix}/{name}" if prefix else name
            units.extend(_split_tree(child_prefix, child_members, cap))
    return units


def _pack_adjacent(units: list[_Unit], cap: int) -> list[list[_Unit]]:
    """§5 steps 6 and 7: merge whole small units with their neighbours,
    respecting the cap, in the recursion's own order.

    First-fit-decreasing (sort by size, greedy-fill) was tried here and
    rejected -- see the module header -- because it spends the coherence the
    grouping key just bought. Adjacent-only means a unit only ever shares a
    slice with the units immediately beside it in plan order, which is what
    lets step 7 combine several small whole containers (measured: 40
    containers x 15 elements went from 40 slices of 21KB to 20) without also
    letting an unrelated pair merge just because both happened to be small.

    `root_index` is a hard boundary on top of the cap: two different corpus
    roots must never share a slice even when both are tiny, because -- as the
    module header's `_group_key` docstring says -- nothing on disk would catch
    that merge. No such boundary exists between two different containers,
    which is exactly the case step 7 wants to combine.
    """
    packed: list[list[_Unit]] = []
    current: list[_Unit] = []
    total = 0
    current_root: int | None = None
    for unit in units:
        n = sum(row_bytes(m) for m in unit.members)
        crosses_root = (
            current_root is not None
            and unit.root_index is not None
            and unit.root_index != current_root
        )
        if current and (total + n > cap or crosses_root):
            packed.append(current)
            current, total, current_root = [], 0, None
        current.append(unit)
        total += n
        if unit.root_index is not None:
            current_root = unit.root_index
    if current:
        packed.append(current)
    return packed


def plan_slices(candidates: list[dict], *, cap: int = DEFAULT_SLICE_BYTES) -> list[Slice]:
    """Partition `candidates` into byte-bounded, deterministic `Slice`s.

    Every candidate lands in exactly one slice; no slice's members sum past
    `cap` unless a single row already exceeds it on its own (`oversized_rows`
    is what reports that case -- nothing here can make a one-row unit
    smaller). Invariant to the order `candidates` arrives in: every grouping
    step below sorts its keys and its members before iterating.
    """
    if not candidates:
        return []

    units: list[_Unit] = []
    for key, members in _top_level_groups(candidates):
        total = sum(row_bytes(m) for m in members)
        label = _top_label(key)
        if total <= cap:
            group_units = [_Unit(f"{label} ({len(members)} candidates)", tuple(members))]
        elif key[0] == "container":
            group_units = _split_container(label, members, cap)
        elif key[0] == "corpus":
            group_units = _split_tree("", members, cap)
        else:
            # A single oversized "solo" candidate: nothing smaller to split
            # it into. oversized_rows is what refuses this, not this module.
            group_units = [_Unit(f"{label} ({len(members)} candidates)", tuple(members))]
        if key[0] == "corpus":
            # Stamped after the splitter runs rather than threaded through
            # it -- see _Unit's docstring -- because every unit one corpus
            # group produces gets the same root_index regardless of how the
            # splitter cut it up.
            group_units = [replace(u, root_index=key[1]) for u in group_units]
        units.extend(group_units)

    packed = _pack_adjacent(units, cap)

    # Slice identity (id, label, candidate_ids) is fixed here; groups and
    # provenance are computed in a second pass below because "how much of a
    # group is elsewhere" needs every slice's membership settled first.
    prelim: list[tuple[str, str, tuple[str, ...]]] = []
    for index, unit_group in enumerate(packed, start=1):
        slice_id = f"s{index:02d}"
        candidate_ids = tuple(
            candidate["candidate_id"] for unit in unit_group for candidate in unit.members
        )
        slice_label = " + ".join(unit.label for unit in unit_group)
        prelim.append((slice_id, slice_label, candidate_ids))

    candidates_by_id = {c["candidate_id"]: c for c in candidates}
    group_of = {cid: _group_label(_group_key(c)) for cid, c in candidates_by_id.items()}
    group_total = Counter(group_of.values())
    group_slice_ids: dict[str, set[str]] = defaultdict(set)
    for slice_id, _, candidate_ids in prelim:
        for cid in candidate_ids:
            group_slice_ids[group_of[cid]].add(slice_id)

    plan: list[Slice] = []
    for slice_id, slice_label, candidate_ids in prelim:
        counts = Counter(group_of[cid] for cid in candidate_ids)
        groups = tuple(sorted(counts))
        provenance = tuple(
            {
                "group": group,
                "in_this_slice": counts[group],
                "in_group_total": group_total[group],
                "other_slices": tuple(sorted(s for s in group_slice_ids[group] if s != slice_id)),
            }
            for group in groups
        )
        plan.append(
            Slice(
                id=slice_id,
                label=slice_label,
                groups=groups,
                candidate_ids=candidate_ids,
                provenance=provenance,
            )
        )
    return plan


def write_slices(run: RunPaths, *, cap: int = DEFAULT_SLICE_BYTES) -> tuple[Path, list[Slice]]:
    """Partition the run's catalogue into slices and write the plan plus one shard each.

    Several failure modes are refused before planning even starts, all exit 2
    at the CLI rather than a finding: a catalogue that is not a JSON object at
    all, or that is one but is missing `run_id`, `request`, `policy`, or
    `excluded` (the four fields this function reads verbatim, three of which
    every shard carries); an `excluded` that is not an array; a `candidates`
    that is not an array, or an empty one (nothing for a slice to hold -- a
    survey defect, not a triage-slices one); a candidate that is not an object
    carrying a *string* `candidate_id` (read bare, and sorted on, by every
    grouping step `plan_slices` runs); and any candidate over `cap` on its own
    (oversized_rows is what reports that; no splitter here can shrink a single
    row). Those guards stand in front of fields this module reads with a bare
    `[...]` rather than `.get(...)` -- deliberately, so a genuine `KeyError`
    elsewhere in this module (a real defect in this stage) still surfaces as
    the exit 1 a stage defect should be, rather than every KeyError being
    swallowed into exit 2 by a broadened catch in `cli.py`. A malformed
    catalogue cannot be fixed by retrying the stage, so it must reach the
    orchestrator as exit 2, never the exit 1 that spends the run's one
    repair attempt on something no retry can fix -- and the message below
    names the catalogue, not this stage, because the defect is in the
    artifact `triage-slices` was handed, not in what it did with it.

    Every shard carries the run's `request` and `policy` verbatim alongside
    its own slice's full candidate records, rather than each member re-reading
    00-catalogue.json for them. That duplication is deliberate: on the
    595KB/351-candidate corpus that motivated this whole module,
    canonical_bytes's sorted keys put `run_id` 608KB into the file, so a
    dispatch reading only its own slice range still had to seek across the
    catalogue for two small top-level fields -- exactly the chunk-reading cost
    this module exists to eliminate. Paying a few duplicated bytes per shard
    is cheaper than one extra seek per member, every time.

    The plan carries a `catalogue_facts` block for the same reason one step
    further out: it is everything rb-triage-objective needs, so that pass's
    `reads` no longer names the catalogue at all. Measured on the tau2
    catalogue, that took the objective dispatch's input from 472,799 bytes to
    51,792 -- inside the harness's 256KB whole-file Read refusal, where the
    catalogue was not -- and bounded it by max_candidates, since the block's
    only term that grows with the run is `candidate_bytes`, at 41.1 bytes per
    candidate on that catalogue. The rest is `excluded`, capped at
    MAX_EXCLUDED_ENTRY_BYTES, plus verbatim `request` and `policy`, neither of
    which grows with corpus size. canonical_bytes sorts keys, so the block
    and run_id both land ahead of the slices array: the 470KB seek for run_id
    that chunk-reading dispatches used to pay is gone as a consequence of the
    sort rather than as a special case.

    Idempotent and safe to re-run: a human adopting a projection at gate 0
    changes the catalogue, and the plan must be mintable again from scratch.
    Every shard the new plan does not name is deleted, so a slice id that
    existed under the old plan but not the new one does not linger as a
    stale, unreferenced file a later stage could mistakenly read.
    """
    catalogue = read_json(run.catalogue)
    # The container door, and the same one seal._payload_keys' docstring
    # describes: two of the four wrong top-level shapes (`[]`, `"hi"`) answer
    # `key not in catalogue` correctly and reach the exit-2 refusal below,
    # while `null` and `7` raised TypeError -- an `[internal]` finding at exit 1
    # naming the RUN ROOT rather than the catalogue, which is the exit-code
    # contract's third rule breached. The guard is what makes all four the same
    # refusal instead of two refusals and two tracebacks.
    if not isinstance(catalogue, dict):
        raise UsageError(
            f"{run.catalogue} is not a JSON object: found {catalogue!r}; there is no catalogue "
            "here to partition"
        )
    missing_top = [
        key for key in ("run_id", "request", "policy", "excluded") if key not in catalogue
    ]
    if missing_top:
        raise UsageError(f"{run.catalogue} is missing required field(s): {missing_top}")
    # `excluded` of the wrong container shape, guarded for the reason
    # `candidates` is below, and both halves are wrong differently. `7` and
    # `null` raise TypeError out of excluded_summary's `len()` -- from a *code*
    # stage, so cli.py's catch-all turns it into an exit 1 `[internal]` finding
    # naming the RUN ROOT: a malformed catalogue arriving as a stage defect,
    # against the wrong artifact. A string or an object does not raise at all,
    # which is worse: both iterate to zero well-formed entries, so the plan
    # would carry a plausible and wrong summary with nothing to say so.
    if not isinstance(catalogue["excluded"], list):
        raise UsageError(
            f"{run.catalogue}'s excluded is not an array: found {catalogue['excluded']!r}; its "
            "exclusions cannot be summarised"
        )
    candidates = catalogue.get("candidates", [])
    # `candidates` of the wrong container shape, for the same reason: a number
    # raised TypeError out of `enumerate`, and a *string* passed every guard
    # below only because `"candidate_id" not in "a"` happens to be a substring
    # test that answers True -- correct exit code by coincidence, which is not
    # the same as a checked one.
    if not isinstance(candidates, list):
        raise UsageError(
            f"{run.catalogue}'s candidates is not an array: found {candidates!r}; there is "
            "nothing here to partition"
        )
    if not candidates:
        raise UsageError(f"{run.catalogue} has no candidates to slice")
    # Presence was not enough, and both halves were measured. A candidate that
    # is not an object at all raised TypeError from the `in` below; and a
    # candidate_id present but not a string reached `sorted`, where a single
    # non-string id sorts alone and passes while *two* ids of different types
    # raise TypeError comparing them -- so the defect was invisible on the
    # one-candidate case and fatal on the realistic one. `_top_key` and
    # `_group_key` both read the id bare and both sort on it, so a string id
    # is a precondition of planning rather than a tidiness check.
    unshaped_at = [
        i
        for i, c in enumerate(candidates)
        if not isinstance(c, dict) or not isinstance(c.get("candidate_id"), str)
    ]
    if unshaped_at:
        raise UsageError(
            f"{run.catalogue} has candidate(s) that are not an object with a string "
            f"candidate_id at index {unshaped_at}"
        )
    oversized = oversized_rows(candidates, cap=cap)
    if oversized:
        raise UsageError(
            f"{run.catalogue} has candidates too large for any {cap}-byte slice: {oversized}"
        )
    plan = plan_slices(candidates, cap=cap)

    candidates_by_id = {c["candidate_id"]: c for c in candidates}
    document = {
        "schema_version": "0.1",
        "run_id": catalogue["run_id"],
        "cap_bytes": cap,
        "catalogue_facts": catalogue_facts(catalogue),
        "slices": [
            {
                "id": s.id,
                "label": s.label,
                "groups": list(s.groups),
                "bytes": sum(row_bytes(candidates_by_id[cid]) for cid in s.candidate_ids),
                "candidate_ids": list(s.candidate_ids),
                "provenance": [dict(p) for p in s.provenance],
            }
            for s in plan
        ],
    }
    write_json(run.slices, document)

    run.slices_dir.mkdir(parents=True, exist_ok=True)
    written_names: set[str] = set()
    for s in plan:
        shard = {
            "schema_version": "0.1",
            "run_id": catalogue["run_id"],
            "slice_id": s.id,
            "request": catalogue["request"],
            "policy": catalogue["policy"],
            "provenance": [dict(p) for p in s.provenance],
            "candidates": [candidates_by_id[cid] for cid in s.candidate_ids],
        }
        shard_path = run.slice_shard(s.id)
        write_json(shard_path, shard)
        written_names.add(shard_path.name)

    # Stale-shard removal: a re-run's plan is the only source of truth for
    # what should exist under 00-slices/, so anything else there is left over
    # from a plan this run no longer has -- see the docstring's idempotence
    # paragraph for why that situation is expected, not a defect.
    for existing in list_json(run.slices_dir):
        if existing.name not in written_names:
            existing.unlink()

    return run.slices, plan
