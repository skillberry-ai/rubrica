#!/usr/bin/env python
"""The paths one dispatched stage is permitted to write, from its own contract.

`dispatch-stage.sh` granted `Write(/$RUN/**)` and `Edit(/$RUN/**)`, so a stage
could write anything anywhere inside the run directory. It was measured doing
exactly that: the `rb-triage-objective` dispatch recorded under the digest
over-read (docs/design/findings.md) wrote a `compute_weights.py` helper into the
run root, which is not an artifact, is not cleaned up, is covered by no schema,
and leaves `check-refs` at exit 0. The one mechanism that looks for unmanaged
files keeps `p.name` where `".tmp." in p.name`, so a scratch script is a shape it
does not cover.

The ruling was that a stage's `writes` is the whole truth about what appears in
`$RUN`, and that the sandbox scope rather than prose is what enforces it. This
resolves that contract to concrete paths so the shell can grant exactly them.
`check-skills` already holds every `writes` entry to a `RunPaths` attribute name,
so the resolution below is well defined for any contract that passes that gate.

Two things it deliberately does not do:

- It does not fail when an id-parameterised path cannot be pinned. A grant that is
  too tight breaks the dispatch it was meant to protect, and a denied write
  surfaces mid-turn as a model working around it rather than as a clean error. So
  where the id is unavailable the artifact's own directory is granted instead --
  still a real narrowing, because the point of the ruling is that a scratch file at
  the run root is refused, not that a member is confined to one filename.
- It does not read the run's artifacts. Everything here comes from the contract,
  the `RunPaths` shape, and at most the list of round directories on disk.

Usage: stage-write-scope.py <run-dir> <stage> [slice-id]
Prints one absolute path or glob per line, sorted, with no duplicates.
"""

from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path

from rubrica.paths import RunPaths
from rubrica.skills import SKILL_PREFIX, load, skills_dir

# A placeholder id, only ever used to discover which directory an
# id-parameterised path lives in -- never printed. Chosen to be a safe path
# segment so `safe_segment` does not raise on it.
_PROBE = "probe"


def _current_round(run: RunPaths) -> int | None:
    """The round a dispatch of a round-parameterised stage is working on.

    The latest round with a batch plan, because `propose-batches` writes that plan
    before either `propose` or `score` is dispatched for the round. Returns None on
    a run that has no plan yet, where the caller falls back to a directory grant.
    """
    try:
        rounds = run.batches_rounds()
    except OSError:
        return None
    return max(rounds) if rounds else None


def _resolve(run: RunPaths, name: str, slice_id: str | None) -> list[Path]:
    attribute = getattr(type(run), name, None)
    if attribute is None:
        raise SystemExit(f"error: {name!r} is not a RunPaths attribute")

    if isinstance(attribute, property):
        return [Path(getattr(run, name))]

    method = getattr(run, name)
    parameters = [
        p
        for p in inspect.signature(method).parameters.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    wants_round = any(p.name == "round_n" for p in parameters)
    wants_id = [p for p in parameters if p.name != "round_n"]

    round_n = _current_round(run) if wants_round else None
    if wants_round and round_n is None:
        # No plan on disk yet, so no round to pin: grant the artifact's own tree.
        #
        # Found as what two different rounds share, rather than by walking up a
        # fixed number of levels, because the depth differs by artifact and guessing
        # it was measured wrong: `score_part(1)` is `<dir>/round-1.json` while
        # `scenario_part(1, id)` is `<dir>/round-1/<id>.json`, so a single
        # `parent.parent` gave the run root itself for the first -- reinstating
        # exactly the blanket grant this script exists to remove.
        first = Path(method(1, _PROBE) if wants_id else method(1))
        second = Path(method(2, _PROBE) if wants_id else method(2))
        root = Path(os.path.commonpath([first, second]))
        if root == run.root or run.root not in root.parents:
            raise SystemExit(
                f"error: {name!r} resolves to the run root, which would grant "
                "everything; refusing rather than widening the scope"
            )
        return [root / "**"]

    if wants_id and slice_id is None:
        # A barrier pass dispatched without an id, or an operator invoking the
        # harness by hand. The directory is the honest grant: which file inside it
        # this dispatch will write is not knowable here.
        probe = Path(method(round_n, _PROBE) if wants_round else method(_PROBE))
        return [probe.parent / "**"]

    if wants_round and wants_id:
        return [Path(method(round_n, slice_id))]
    if wants_round:
        return [Path(method(round_n))]
    return [Path(method(slice_id))]


def main(argv: list[str]) -> int:
    if not 2 <= len(argv) <= 3:
        print(__doc__.strip().splitlines()[-2], file=sys.stderr)
        return 2
    run_dir, stage = argv[0], argv[1]
    slice_id = argv[2] if len(argv) == 3 else None

    skill_path = skills_dir() / f"{SKILL_PREFIX}{stage}" / "SKILL.md"
    if not skill_path.is_file():
        # Every stage this script is asked about is one dispatch-stage.sh dispatches,
        # and those all have a skill. A code stage reaching here is a caller bug, so
        # it is a usage error rather than an empty grant that would look like a stage
        # allowed to write nothing.
        print(f"error: no skill for stage {stage!r} at {skill_path}", file=sys.stderr)
        return 2

    writes = load(skill_path).contract.get("writes", [])
    if not isinstance(writes, list):
        print(f"error: {skill_path}'s contract has a non-list writes", file=sys.stderr)
        return 2

    run = RunPaths(Path(run_dir))
    paths: set[str] = set()
    for name in writes:
        for path in _resolve(run, name, slice_id):
            paths.add(str(path))
    for path in sorted(paths):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
