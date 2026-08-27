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
from .brief import _dicts, _mapping, _quietly
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
