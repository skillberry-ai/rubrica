# `target-brief` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new `rubrica target-brief` subcommand that renders one run's
understanding of the target as a single self-contained HTML page, written for the
people who own that target and asking them to correct it.

**Architecture:** A reader/selector module (`target_brief.py`) turns the world
model, the manifest and `01-claims/` into owner-facing dataclasses; a renderer
(`target_brief_html.py`) turns those into one HTML string; `cli.py` writes it to
a file. It is a **report, not a gate** — always exit 0 on a readable run, no
schema, no artifact, read by no stage. Every fact on the page is read from an
artifact or is arithmetic over artifacts; nothing dispatches a model.

**Tech Stack:** Python 3.13, stdlib only (`dataclasses`, `os.path`, `html`),
`pytest`, `ruff`. No new dependency.

**Spec:** [`docs/superpowers/specs/2026-08-27-target-brief-design.md`](../specs/2026-08-27-target-brief-design.md)

## Global Constraints

Every task's requirements implicitly include this section.

- **Commit form, both flags, every time: `git commit -S -s`.** `-s` is the
  `Signed-off-by` DCO trailer, `-S` the cryptographic signature. **If signing
  fails, stop and report it** — never fall back to an unsigned commit, never
  disable or work around signing.
- **Attribution trailer is exactly `Assisted-By: Claude (Anthropic AI)
  <noreply@anthropic.com>`.** Never `Co-Authored-By`, never `Made-with` — GitHub
  parses those as co-authorship.
- **ruff:** `line-length = 100`, `select = ["E","F","I","UP","B","SIM"]`. Run
  `make check` before every commit; it must report no changes.
- **`make test` must stay green** and `uv run rubrica check-skills` must exit 0.
  Those plus `make check` are the three gates.
- **Comment density here is high and deliberate.** Comments explain *why*,
  usually citing a measurement. Match the surrounding code; do not strip them.
- **Exit-code contract, load-bearing:** `0` clean, `1` findings one per line on
  stdout, `2` usage error or unreadable run. This feature never returns `1` — a
  report cannot turn a readable run into a defect finding. An `OSError` from
  writing the page is the filesystem refusing and maps to `2` through `cli.py`'s
  existing shared handler; **do not add a local `except` on the write path.**
- **Never fabricate a quote, a path or a locator.** An unreadable `01-claims/`
  renders evidence as a stated absence. The `chmod 000` incident that produced
  four fabricated `no such claim` findings against a correct world model is this
  exact shape, and a fabricated quote in a document sent to the system's owner
  would be read as our assertion about their file.
- **Prose from the world model is selected and relabelled, never rewritten.**
  Ship a claim id inside a description rather than regex it out. A paraphrase is
  the orchestrator's conclusion wearing a finding's clothes.
- **Absent and Malformed are two facts, not one.** Use
  `summary._absent_or_malformed`; never spell both "not present".
- **Measure every new test predicate in both directions before committing it.**
  Blank the field or prose it claims to check (in a copy, under the relevant env
  override) and confirm it goes red; then reword that content meaning-preservingly
  and confirm it stays green. `skills.section_body` scoping and the
  substring-of-message trap in CLAUDE.md apply to any text assertion.

## File Structure

| File | Responsibility |
|---|---|
| `src/rubrica/target_brief.py` (create) | Reading and selection only: resolve claims to sources, compute provenance, build the four ask-groups and the three description sections as dataclasses. No HTML. |
| `src/rubrica/target_brief_html.py` (create) | Rendering only: those dataclasses to one HTML string. Reuses `summary_html`'s CSS and table/section/marker chrome. |
| `src/rubrica/cli.py` (modify) | One `SUBCOMMANDS` entry, one parser block, one handler block. |
| `tests/unit/test_target_brief.py` (create) | Selection layer: source resolution, provenance, all four groups, all three description sections, every degradation path. |
| `tests/unit/test_target_brief_html.py` (create) | Rendering and the CLI: page assembly, markers rendered not skipped, `-o`, exit codes. |
| `docs/reference/cli.md` (modify) | A `rubrica target-brief` section. `tests/unit/test_docs_accuracy.py` fails until it exists. |
| `CLAUDE.md` (modify) | The reports-not-gates paragraph, which names `claim-utilisation` and `gate-brief` today. |

Split into two modules from the start rather than one that grows: `summary.py`
(1576 lines) and `summary_html.py` (1108) already draw this line, and the reason
is that a reader you can hold in context edits reliably.

## Why these eight tasks

Each ends with an independently testable deliverable a reviewer could reject on
its own. Tasks 1 and 2 build the two primitives every later task consumes, so
they come first and their interfaces are fixed there. Tasks 3–6 are the four
tier-1 groups and the tier-2 body, each readable alone. Task 7 assembles the
page. Task 8 wires the command and updates the docs the tests enforce.

---
### Task 1: Resolve a claim id to the place in the target that states it

Every later task consumes this. A world-model element cites claim ids; an owner
can only check a file, a locator and a quote. This is the translation.

**Files:**
- Create: `src/rubrica/target_brief.py`
- Test: `tests/unit/test_target_brief.py`

**Interfaces:**
- Consumes: `RunPaths` (`.manifest`, `.claims_dir`); `refs._claims_by_artifact`;
  `brief._quietly/_mapping/_dicts`; `summary.Marker/_absent_or_malformed`.
- Produces: `SourceRef(claim_id: str, path: str, locator: str, quote: str, kind: str)`;
  `source_index(run: RunPaths) -> dict[str, SourceRef] | Marker`;
  `_common_prefix(files: list[str]) -> str`; `_shorten(path: str, prefix: str) -> str`.

**The ruling this task must not re-decide.** `01-claims/` unreadable raises
`UsageError` out of `paths.list_json` — a `ValueError`, *not* an `OSError`, so a
guard cannot be `except OSError`. `summary.py:725-770` rules on it at length:
`claim-utilisation` and `gate-brief` exit **2** on it and that is the contract
working, while `summary.py` catches it "only so this page renders a marker
instead of crashing, which is a promise about the page and not about an exit
code." Follow `run-summary`: catch, return a marker.

But that same ruling warns that reporting empty on an unreadable claims
directory is "the one reading a human at gate 1 must never be handed" — and this
page *is* a gate-1 artifact that gets mailed outside the project. So
`source_index` returns a **`Marker`**, never a silently empty dict, and Task 7
renders it as a page-level banner. A page that quietly showed no evidence would
be indistinguishable from a target that has none.

- [ ] **Step 1: Write the failing tests**

```python
"""target-brief: the run's understanding of the target, addressed to its owners.

Every assertion here names a real toy claim id. `clm-api-001` carries evidence
with no `quote` and `clm-api-007` carries one, which is what makes the
quote-absent and quote-present paths two different tests rather than one.
"""

from __future__ import annotations

import json
import os

import pytest

from rubrica import target_brief
from rubrica.summary import Malformed
from tests.toy import build_toy_run


def test_source_index_resolves_a_claim_to_path_locator_and_kind(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    index = target_brief.source_index(run)
    ref = index["clm-api-001"]
    # The shared prefix is stripped: the toy corpus lives under
    # tests/fixtures/toy, and an owner recognises "api.json", never the absolute
    # path of the machine rubrica happened to run on.
    assert ref.path == "api.json"
    assert ref.kind == "mcp_tool_schema"
    assert ref.locator.startswith("#/tools/")


def test_source_index_reports_a_missing_quote_as_empty_never_as_invented_text(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    index = target_brief.source_index(run)
    assert index["clm-api-001"].quote == ""
    assert index["clm-api-007"].quote == '"required": ["action"]'


def test_source_index_prefers_the_evidence_record_that_carries_a_quote(tmp_path):
    """Measured: executive-agent quotes only 67 of the 126 claims its world model
    cites, so taking evidence[0] blindly drops quotes the run does have."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    path = run.claims_dir / "api-json.json"
    payload = json.loads(path.read_text())
    payload["claims"][0]["evidence"] = [
        {"artifact_id": "api-json", "locator": "#/first"},
        {"artifact_id": "api-json", "locator": "#/second", "quote": "the quoted line"},
    ]
    path.write_text(json.dumps(payload))
    ref = target_brief.source_index(run)[payload["claims"][0]["id"]]
    assert ref.quote == "the quoted line"
    assert ref.locator == "#/second"


def test_source_index_omits_a_claim_id_nothing_defines(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    assert "clm-does-not-exist" not in target_brief.source_index(run)


def test_source_index_returns_a_marker_when_claims_cannot_be_read(tmp_path):
    """Never a silently empty dict. summary.py:725-770 rules that reporting empty
    on an unreadable 01-claims/ is the one reading a human at gate 1 must never be
    handed, and this page is mailed outside the project."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    os.chmod(run.claims_dir, 0o000)
    try:
        result = target_brief.source_index(run)
    finally:
        os.chmod(run.claims_dir, 0o755)
    assert isinstance(result, Malformed)
    assert "01-claims" in result.what


@pytest.mark.parametrize(
    "files, expected",
    [
        # More than one file: the directory they share.
        (["/a/b/one.py", "/a/b/two.py"], "/a/b"),
        # Exactly one: its directory, never the file itself. os.path.commonpath
        # of a single path returns that path, which would strip the filename.
        (["/a/b/only.py"], "/a/b"),
        # Nothing shared but the root: strip nothing, or every path renders bare.
        (["/one.py", "/two.py"], ""),
        # Mixed absolute and relative: commonpath raises ValueError, and a
        # half-trimmed path is worse than a full one.
        (["/abs/one.py", "rel/two.py"], ""),
        ([], ""),
    ],
)
def test_common_prefix(files, expected):
    assert target_brief._common_prefix(files) == expected


def test_shorten_keeps_the_slice_fragment(tmp_path):
    """A `#/NN` fragment marks one slice of a sliced artifact. parsec's 71 trace
    inputs are 71 slices of one capture, so the fragment is the only thing
    distinguishing them and dropping it would collapse 71 records into one."""
    assert target_brief._shorten("/a/b/trace.json#/41", "/a/b") == "trace.json#/41"
    assert target_brief._shorten("/a/b/src/tool.py", "/a/b") == "src/tool.py"
    # A prefix that is not actually a parent leaves the path alone rather than
    # slicing characters off its front.
    assert target_brief._shorten("/other/tool.py", "/a/b") == "/other/tool.py"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_target_brief.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'rubrica.target_brief'`

- [ ] **Step 3: Write the minimal implementation**

Create `src/rubrica/target_brief.py`:

```python
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
    """
    real = sorted({f for f in files if f})
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
        return _absent_or_malformed(
            run.claims_dir, "01-claims/", "nothing could be read from it"
        )
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_target_brief.py -q`
Expected: PASS, all eleven (five named tests, five `_common_prefix` parameters, one `_shorten`).

- [ ] **Step 5: Measure the quote predicate in both directions**

The plan's own rule, and this is the predicate most likely to be vacuous.

```bash
# Red: blank the quote the test pins, and the assertion must fail.
uv run python - <<'PY'
import json, pathlib, sys, tempfile
sys.path.insert(0, "tests")
from toy import build_toy_run
run = build_toy_run(pathlib.Path(tempfile.mkdtemp()), upto="reconcile-seal")
p = run.claims_dir / "api-json.json"
d = json.loads(p.read_text())
for c in d["claims"]:
    for e in c["evidence"]:
        e.pop("quote", None)
p.write_text(json.dumps(d))
from rubrica import target_brief
print("quote after blanking:", repr(target_brief.source_index(run)["clm-api-007"].quote))
PY
```
Expected: prints `''` — confirming the assertion `== '"required": ["action"]'` would
have gone red. If it still prints the quote, the test is reading something else.

- [ ] **Step 6: `make check` and commit**

```bash
make check
git add src/rubrica/target_brief.py tests/unit/test_target_brief.py
git commit -S -s -F - <<'MSG'
feat: Resolve a claim id to the place in the target that states it

An owner cannot check `clm-api-001`; they can check a file, a locator and a
quoted line. source_index is that translation, and every later section of the
brief consumes it.

Three shapes measured rather than assumed. `source_path` is absolute on the
machine rubrica ran on -- all three runs on disk share `/home/agent/runs/<target>`
-- so the shared prefix is stripped and what remains is the owner's own tree. A
`#` fragment is kept, because parsec's 269 inputs are 199 distinct files and 71
trace slices of one capture are told apart by nothing else. And a quote is
preferred over evidence[0] but never required: executive-agent quotes only 67 of
the 126 claims its world model cites, so the rendering degrades to path plus
locator and nothing invents the missing line.

An unreadable 01-claims/ returns a marker rather than an empty dict. list_json
raises UsageError there, a ValueError and not an OSError, which is why the guard
is wide; summary.py catches the same thing so a page renders instead of crashing,
and that is a promise about the page rather than about an exit code. Empty was
rejected because this page leaves the project: a document quietly showing no
evidence is indistinguishable from a target that has none.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
```

---
### Task 2: Provenance — how many sources, which kinds, and whether disputed

The spec's §3.1 records that the first design ranked attention by a claim's
`derivation` and that it was **dropped on measurement**: per element it reads the
same on every row — all 39 parsec capabilities, all 30 entities, all 26 goals and
both actors badge `stated`, because source code is an artifact that states
things. These three replace it, and each one varies across the three runs
measured. **Do not reintroduce a `derivation` badge.**

**Files:**
- Modify: `src/rubrica/target_brief.py`
- Test: `tests/unit/test_target_brief.py`

**Interfaces:**
- Consumes: `SourceRef`, `source_index` (Task 1); `brief._strings`.
- Produces: `Provenance(files: tuple[str, ...], kinds: tuple[str, ...], disputed: bool)`
  with property `single_source: bool`;
  `disputed_claim_ids(world_model: dict) -> frozenset[str]`;
  `provenance(claim_ids, index: dict[str, SourceRef], disputed: frozenset[str]) -> Provenance`.
- **Callers normalise the marker:** `source_index` may return a `Marker`, and
  `provenance` takes a plain dict. Every call site writes
  `refs = index if isinstance(index, dict) else {}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_target_brief.py`:

```python
def test_provenance_counts_distinct_files_and_kinds(tmp_path):
    """The discriminator that replaced the derivation badge. Measured: 13 of
    executive-agent's 37 operations rest on a design document alone, and 28 of
    parsec's 30 data shapes were seen in exactly one file."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    index = target_brief.source_index(run)
    # clm-api-001 is in api.json (mcp_tool_schema); clm-notes-002 in notes.md
    # (design_doc). Two files, two kinds.
    across = target_brief.provenance(["clm-api-001", "clm-notes-002"], index, frozenset())
    assert across.files == ("api.json", "notes.md")
    assert across.kinds == ("design_doc", "mcp_tool_schema")
    assert across.single_source is False
    # The three claims cap-find-tickets cites are all in api.json.
    within = target_brief.provenance(
        ["clm-api-001", "clm-api-007", "clm-api-008"], index, frozenset()
    )
    assert within.files == ("api.json",)
    assert within.single_source is True


def test_provenance_marks_an_element_a_contradiction_touches(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    index = target_brief.source_index(run)
    world_model = json.loads(run.world_model.read_text())
    disputed = target_brief.disputed_claim_ids(world_model)
    # The toy contradiction is con-missing-semantics, claim_a clm-notes-004
    # against claim_b clm-trace-002.
    assert disputed == {"clm-notes-004", "clm-trace-002"}
    assert target_brief.provenance(["clm-notes-004"], index, disputed).disputed is True
    assert target_brief.provenance(["clm-api-001"], index, disputed).disputed is False


def test_disputed_claim_ids_reads_a_side_written_as_a_string_or_a_list():
    """The committed recordings write each side as one claim id; nothing forbids a
    list, and a `str` iterated as a list contributes one character per entry."""
    as_string = {"contradictions": [{"claim_a": "clm-one", "claim_b": "clm-two"}]}
    assert target_brief.disputed_claim_ids(as_string) == {"clm-one", "clm-two"}
    as_list = {"contradictions": [{"claim_a": ["clm-one", "clm-three"], "claim_b": ["clm-two"]}]}
    assert target_brief.disputed_claim_ids(as_list) == {"clm-one", "clm-two", "clm-three"}
    # Hand-edited shapes that must not raise and must not invent an id.
    assert target_brief.disputed_claim_ids({"contradictions": "nope"}) == frozenset()
    assert target_brief.disputed_claim_ids({"contradictions": [{"claim_a": 7}]}) == frozenset()
    assert target_brief.disputed_claim_ids({}) == frozenset()


def test_provenance_of_an_unresolvable_id_names_no_file_but_still_reports_disputed():
    """Provenance is arithmetic over what resolved; dispute is a property of the id
    itself. An element whose claims are all unresolvable must not silently lose its
    disputed marker as well as its files."""
    result = target_brief.provenance(
        ["clm-ghost"], {}, frozenset({"clm-ghost"})
    )
    assert result.files == ()
    assert result.kinds == ()
    assert result.disputed is True


def test_provenance_ignores_non_string_members_of_a_claims_array():
    assert target_brief.provenance([7, None, {}], {}, frozenset()).files == ()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_target_brief.py -q -k "provenance or disputed"`
Expected: FAIL — `AttributeError: module 'rubrica.target_brief' has no attribute 'provenance'`

- [ ] **Step 3: Write the minimal implementation**

Add to `src/rubrica/target_brief.py` (extend the `brief` import to include
`_strings`):

```python
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

    Both spellings are read. The committed recordings write each side as a single
    claim id string, nothing in the schema forbids a list, and a `str` fed through
    `_strings` would contribute one entry per character -- which is how an element
    citing `clm-notes-004` would come out undisputed while five single letters
    came out disputed.
    """
    out: set[str] = set()
    for contradiction in _dicts(world_model.get("contradictions")):
        for side in ("claim_a", "claim_b"):
            value = contradiction.get(side)
            if isinstance(value, str):
                out.add(value)
            else:
                out.update(_strings(value))
    return frozenset(out)


def provenance(
    claim_ids, index: dict[str, SourceRef], disputed: frozenset[str]
) -> Provenance:
    """What the claims behind one element rest on.

    `disputed` is computed from the ids themselves rather than from the resolved
    refs: an element every one of whose claims is unresolvable has no files to
    show, and losing its dispute marker at the same time would hide the more
    important of the two facts.
    """
    ids = [c for c in claim_ids if isinstance(c, str)]
    resolved = [index[c] for c in ids if c in index]
    return Provenance(
        files=tuple(sorted({r.path for r in resolved if r.path})),
        kinds=tuple(sorted({r.kind for r in resolved if r.kind})),
        disputed=any(c in disputed for c in ids),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_target_brief.py -q`
Expected: PASS, all of Task 1's plus five more.

- [ ] **Step 5: Confirm the discriminator is not vacuous on a real run**

A predicate nobody has watched vary is not yet a discriminator. This reads the
three runs on disk and must print differing single-source counts.

```bash
uv run python - <<'PY'
import json, pathlib
from rubrica import target_brief
from rubrica.paths import RunPaths
for name in ("run-20260826-090456", "run-20260825-094033", "run-20260824-054040"):
    root = pathlib.Path("runs") / name
    if not root.exists():
        print(f"{name}: absent, skipping")
        continue
    run = RunPaths(root)
    index = target_brief.source_index(run)
    index = index if isinstance(index, dict) else {}
    wm = json.loads(run.world_model.read_text())
    disputed = target_brief.disputed_claim_ids(wm)
    caps = [target_brief.provenance(c.get("claims", []), index, disputed)
            for c in wm.get("capabilities", [])]
    print(f"{name}: capabilities={len(caps)} "
          f"single_source={sum(p.single_source for p in caps)} "
          f"disputed={sum(p.disputed for p in caps)}")
PY
```
Expected: three different profiles, matching the spec's §3.2 table — parsec
`39/4/6`, executive-agent `37/13/16`, reservation-service `5/0/2`. If all three
report the same shape, the discriminator has failed the way `derivation` did and
this task is not done. (`RunPaths` is constructed directly here rather than
through `cli._run_dir` because this is a probe, not a command.)

- [ ] **Step 6: `make check` and commit**

```bash
make check
git add src/rubrica/target_brief.py tests/unit/test_target_brief.py
git commit -S -s -F - <<'MSG'
feat: Rank an element by its sources and its disputes, not by derivation

The first design badged each element with its claims' `derivation`. Measured per
element it reads the same on every row: all 39 parsec capabilities, all 30
entities, all 26 goals and both actors come out `stated`, because `derivation`
records whether an artifact asserted the fact and source code is an artifact that
asserts things. Capability `confidence` is worse -- all 39 `high`. Dropped rather
than shipped: a badge that never varies implies a distinction was checked, which
in a document someone is asked to ratify is a harm rather than a neutral.

Provenance replaces it with three things that do vary. Capabilities resting on a
single source across the three runs on disk: 4 of 39, 13 of 37, 0 of 5. Entities:
28 of 30, 18 of 18, 1 of 4. Capabilities a contradiction touches: 6 of 39, 16 of
37, 2 of 5. Each says something an owner can act on without knowing what rubrica
is -- 13 of executive-agent's 37 operations rest on a design document alone, with
no schema, no code and no trace behind them.

disputed_claim_ids reads a side written as a string and as a list, because a str
fed through _strings contributes one entry per character, and an element citing
clm-notes-004 would then come out undisputed while five single letters came out
disputed. Dispute is computed from the ids rather than the resolved refs so an
element whose claims all fail to resolve keeps the more important of the two
facts.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
```

---
### Task 3: Group A — "we read these files, did we miss anything?"

First on the page on purpose. Gate 0 decides what the run can ever know, and
nothing downstream of `intake` reads the corpus again, so a candidate the triage
family declines is gone as completely as if the corpus never held it. `CLAUDE.md`
argues that triage cannot also hold its own gate, because "the same party
selecting the inputs and ratifying the selection would make the whole run
unfalsifiable." The target's owner is the only party outside that loop who can say
a document was missing.

**Files:**
- Modify: `src/rubrica/target_brief.py`
- Test: `tests/unit/test_target_brief.py`

**Interfaces:**
- Consumes: `_common_prefix`, `_shorten`, `_input_sources` (Task 1).
- Produces: `InputGroup(kind: str, directory: str, files: tuple[str, ...], slices: int)`;
  `inputs_read(run: RunPaths) -> list[InputGroup] | Marker`.

**An input is not a file.** parsec's 269 inputs are **199 distinct files** — its
71 `trace` inputs are 71 `#/NN` slices of a single capture, and
reservation-service's 25 inputs are 11 files. Counting inputs would tell parsec's
owners we read 269 files when we read 199, and would list one trace file 71 times.
So this groups on the path *before* the `#` and reports slices separately.

- [ ] **Step 1: Write the failing tests**

```python
def test_inputs_read_groups_by_kind_and_directory(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    groups = target_brief.inputs_read(run)
    # The toy corpus is three files of three kinds, all directly under the shared
    # prefix, so each is its own group and no directory qualifies any of them.
    assert [(g.kind, g.directory, g.files, g.slices) for g in groups] == [
        ("design_doc", "", ("notes.md",), 0),
        ("mcp_tool_schema", "", ("api.json",), 0),
        ("trace", "", ("trace.json",), 0),
    ]


def test_inputs_read_collapses_slices_of_one_file(tmp_path):
    """parsec's 71 trace inputs are 71 slices of one capture. Counting inputs
    would report 269 files where the run read 199, and would list one file 71
    times."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    manifest = json.loads(run.manifest.read_text())
    base = "/corpus/traces/capture.json"
    manifest["inputs"] = [
        {"artifact_id": "t-41", "kind": "trace", "source_path": f"{base}#/41"},
        {"artifact_id": "t-44", "kind": "trace", "source_path": f"{base}#/44"},
        {"artifact_id": "t-68", "kind": "trace", "source_path": f"{base}#/68"},
        {"artifact_id": "src", "kind": "source_code", "source_path": "/corpus/src/tool.py"},
    ]
    run.manifest.write_text(json.dumps(manifest))
    groups = {g.kind: g for g in target_brief.inputs_read(run)}
    assert groups["trace"].files == ("traces/capture.json",)
    assert groups["trace"].slices == 2  # three inputs, one file
    assert groups["source_code"].files == ("src/tool.py",)
    assert groups["source_code"].slices == 0


def test_inputs_read_names_the_artifact_when_the_manifest_records_no_path(tmp_path):
    """Names something the reader can chase. A blank row names nothing, and a
    constructed path would be a fabrication about the owner's tree."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    manifest = json.loads(run.manifest.read_text())
    manifest["inputs"] = [{"artifact_id": "orphan", "kind": "other"}]
    run.manifest.write_text(json.dumps(manifest))
    assert target_brief.inputs_read(run)[0].files == ("orphan",)


def test_inputs_read_marks_an_absent_manifest_absent_and_a_broken_one_malformed(tmp_path):
    """Two facts, not one. They were a single word until a run said on one page
    that a stage had produced an artifact and that the artifact was not present."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    run.manifest.write_text("{ not json")
    broken = target_brief.inputs_read(run)
    assert isinstance(broken, Malformed)
    assert broken.what == "manifest.json"
    run.manifest.unlink()
    assert isinstance(target_brief.inputs_read(run), Absent)
```

Extend the test module's imports to `from rubrica.summary import Absent, Malformed`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_target_brief.py -q -k inputs_read`
Expected: FAIL — `AttributeError: module 'rubrica.target_brief' has no attribute 'inputs_read'`

- [ ] **Step 3: Write the minimal implementation**

```python
@dataclass(frozen=True)
class InputGroup:
    """The files of one kind in one directory that the run read.

    `slices` is inputs beyond one per file, not a count of inputs: a `#/NN`
    fragment marks one slice of a sliced artifact, so three inputs over one
    capture is one file read as three recorded calls. Rendering it as three files
    would misstate what we read, and "1 trace file, read as 71 recorded calls" is
    both shorter and true.
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
    payload = _mapping(_quietly(run.manifest))
    if not payload:
        return _absent_or_malformed(
            run.manifest, "manifest.json", "nothing could be read from it"
        )
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
            path = _shorten(source.partition("#")[0], prefix)
        else:
            # The artifact id, for the reason SourceRef.path takes it: it names
            # something chaseable where a blank names nothing.
            path = artifact_id if isinstance(artifact_id, str) else ""
        directory, _, name = path.rpartition("/")
        seen.setdefault((kind, directory), []).append(name or path)
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_target_brief.py -q`
Expected: PASS.

- [ ] **Step 5: Check the file count against the real runs**

The number this group puts at the top of the document must match the corpus.

```bash
uv run python - <<'PY'
import json, pathlib
from rubrica import target_brief
from rubrica.paths import RunPaths
for name, expect in (("run-20260826-090456", 199), ("run-20260825-094033", 5),
                     ("run-20260824-054040", 11)):
    root = pathlib.Path("runs") / name
    if not root.exists():
        print(f"{name}: absent, skipping")
        continue
    groups = target_brief.inputs_read(RunPaths(root))
    files = sum(len(g.files) for g in groups)
    slices = sum(g.slices for g in groups)
    inputs = len(json.loads((root / "manifest.json").read_text())["inputs"])
    print(f"{name}: files={files} (expect {expect}) slices={slices} inputs={inputs} "
          f"-> {'OK' if files == expect and files + slices == inputs else 'WRONG'}")
PY
```
Expected: `OK` on every run present. `files + slices == inputs` is the arithmetic
that must hold — every input is either a file or a further slice of one.

- [ ] **Step 6: `make check` and commit**

```bash
make check
git add src/rubrica/target_brief.py tests/unit/test_target_brief.py
git commit -S -s -F - <<'MSG'
feat: Ask the owners what the corpus missed, counting files rather than inputs

Gate 0 decides what a run can ever know, and nothing below intake reads the
corpus again, so a declined candidate is gone as completely as if the corpus
never held it. CLAUDE.md argues triage cannot also hold its own gate, the same
party selecting and ratifying making the run unfalsifiable -- which leaves the
target's owner as the only party who can say a document was missing. So this
group leads the document.

An input is not a file. parsec's 269 inputs are 199 distinct files, because its 71
trace inputs are 71 `#/NN` slices of a single capture, and reservation-service's
25 inputs are 11 files. Counting inputs would tell parsec's owners we read 269
files when we read 199, and would list one capture 71 times. So grouping is on
the path before the `#` and slices are reported separately, which also makes
files + slices == inputs an arithmetic check on the whole group.

An input the manifest records with no source_path is named by its artifact id
rather than left blank or given a constructed path: one names something chaseable,
the others name nothing and fabricate respectively.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
```

---
### Task 4: Groups B and C — where the target's own documents disagree

The section that earns the report. parsec records 41 contradictions and they are
documentation-vs-implementation drift stated in the owner's own terms: a design
doc specifying `verify=False` on a client the connections claim describes without
it; a doc stating `query_aap2` exposes three actions against a module exposing
four; `elapsed`/`name` in the agent instructions against `duration_seconds`/
`job_name` in the implementation. An owner acts on those the day they read them,
whether or not they ever comment on the rest of the page.

**Files:**
- Modify: `src/rubrica/target_brief.py`
- Test: `tests/unit/test_target_brief.py`

**Interfaces:**
- Consumes: `SourceRef`, `source_index` (Task 1).
- Produces: `Dispute(id, nature, resolution, taken, side_a, side_b)` where the
  sides are `tuple[SourceRef, ...]`; `disputes(run: RunPaths) -> list[Dispute] | Marker`;
  `_side(value, index) -> tuple[SourceRef, ...]`;
  `_taken(resolution, side_a, side_b) -> str`.
- Task 7 partitions the list on `resolution == "unresolved"` — group B is the
  unresolved ones, group C the rest. One builder, because they differ only in
  which sentence follows them.

**Deliberate deviation from the spec.** §4.1.C illustrates the resolved-side
sentence as *"We went with the code."* Implemented as **"We went with
`src/tools/aap2.py`."** — naming the file. "The code" would require inferring
code-ness from the side's `kind`, which is a heuristic that fails on the mixed
kinds measured (reservation-service's capabilities span four kinds at once), and
naming the file is both checkable by the owner and free of inference. The spec's
`resolution` → phrase mapping stands for `both_possible` and `unresolved`.

- [ ] **Step 1: Write the failing tests**

```python
def test_disputes_renders_nature_verbatim_and_resolves_both_sides(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    recorded = json.loads(run.world_model.read_text())["contradictions"][0]
    found = target_brief.disputes(run)
    assert [d.id for d in found] == ["con-missing-semantics"]
    dispute = found[0]
    # Verbatim, compared against the artifact rather than a copied string, so the
    # assertion cannot rot into agreeing with a paraphrase.
    assert dispute.nature == recorded["nature"]
    assert dispute.resolution == "preferred_a"
    assert [r.claim_id for r in dispute.side_a] == ["clm-notes-004"]
    assert [r.claim_id for r in dispute.side_b] == ["clm-trace-002"]
    # Each side arrives as a file the owner can open, with the quoted line.
    assert dispute.side_a[0].path == "notes.md"
    assert dispute.side_a[0].quote.startswith("`get_ticket` with an id no ticket has")
    assert dispute.side_b[0].path == "trace.json"


def test_taken_names_the_file_rather_than_inferring_the_kind():
    """"We went with the code" needs a code-ness heuristic that fails on the mixed
    kinds measured -- reservation-service's capabilities span four at once. A file
    the owner can open needs no inference."""
    a = (target_brief.SourceRef("clm-a", "notes.md", "L1", "", "design_doc"),)
    b = (target_brief.SourceRef("clm-b", "src/tool.py", "L2", "", "source_code"),)
    assert target_brief._taken("preferred_a", a, b) == "We went with notes.md."
    assert target_brief._taken("preferred_b", a, b) == "We went with src/tool.py."
    assert target_brief._taken("both_possible", a, b) == "We are treating both as possible."
    # Unresolved carries no sentence: group B's whole point is that we could not
    # tell, and a sentence there would assert a decision nobody made.
    assert target_brief._taken("unresolved", a, b) == ""


def test_taken_says_so_when_the_chosen_side_resolves_to_nothing():
    """Never a bare "We went with ." -- the sentence states its own hole."""
    b = (target_brief.SourceRef("clm-b", "src/tool.py", "L2", "", "source_code"),)
    assert target_brief._taken("preferred_a", (), b) == (
        "We took one side, but could not resolve which file states it."
    )


def test_disputes_keeps_a_contradiction_whose_claims_do_not_resolve(tmp_path):
    """The nature prose is the payload; the sides are corroboration. Dropping the
    record because a citation dangles would hide a real disagreement, and a
    dangling citation is check-refs' finding rather than this page's."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["contradictions"][0]["claim_a"] = "clm-ghost"
    run.world_model.write_text(json.dumps(world_model))
    dispute = target_brief.disputes(run)[0]
    assert dispute.side_a == ()
    assert dispute.nature  # still there, still rendered
    assert dispute.taken == "We took one side, but could not resolve which file states it."


def test_disputes_orders_by_id_and_reports_an_unreadable_world_model(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    first = dict(world_model["contradictions"][0])
    world_model["contradictions"] = [
        {**first, "id": "con-zebra"},
        {**first, "id": "con-alpha"},
    ]
    run.world_model.write_text(json.dumps(world_model))
    assert [d.id for d in target_brief.disputes(run)] == ["con-alpha", "con-zebra"]
    run.world_model.write_text("{ not json")
    assert isinstance(target_brief.disputes(run), Malformed)
    run.world_model.unlink()
    assert isinstance(target_brief.disputes(run), Absent)


def test_disputes_is_empty_rather_than_absent_when_the_target_has_none(tmp_path):
    """An empty list and a missing world model are different facts, and the
    renderer says different things about them."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["contradictions"] = []
    run.world_model.write_text(json.dumps(world_model))
    assert target_brief.disputes(run) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_target_brief.py -q -k "disputes or taken"`
Expected: FAIL — `AttributeError: ... has no attribute 'disputes'`

- [ ] **Step 3: Write the minimal implementation**

```python
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
    """One side of a contradiction, resolved. A string or a list of ids."""
    ids = [value] if isinstance(value, str) else _strings(value)
    return tuple(index[c] for c in ids if c in index)


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
    files = sorted({ref.path for ref in chosen if ref.path})
    if not files:
        return _UNRESOLVED_SIDE
    return "We went with " + ", ".join(files) + "."


def disputes(run: RunPaths) -> list[Dispute] | Marker:
    """Every contradiction the world model records, both sides resolved.

    Ordered by id. Ranking by blast radius -- how many elements rest on a disputed
    claim -- would order better and the inputs already exist in `provenance`, but
    it is the one piece of genuinely new analysis in this design and shipping it
    unmeasured is how a report starts asserting a judgment it did not earn.
    """
    payload = _mapping(_quietly(run.world_model))
    if not payload:
        return _absent_or_malformed(
            run.world_model, "01-world-model.json", "nothing could be read from it"
        )
    index = source_index(run)
    refs = index if isinstance(index, dict) else {}
    out = []
    for record in _dicts(payload.get("contradictions")):
        identifier = record.get("id")
        nature = record.get("nature")
        resolution = record.get("resolution")
        resolution = resolution if isinstance(resolution, str) else ""
        side_a = _side(record.get("claim_a"), refs)
        side_b = _side(record.get("claim_b"), refs)
        out.append(
            Dispute(
                id=identifier if isinstance(identifier, str) else "",
                # Verbatim, and `""` rather than a stand-in sentence when the
                # field is missing: the renderer says it could not read the
                # description, which is true, where invented prose would not be.
                nature=nature if isinstance(nature, str) else "",
                resolution=resolution,
                taken=_taken(resolution, side_a, side_b),
                side_a=side_a,
                side_b=side_b,
            )
        )
    return sorted(out, key=lambda d: d.id)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_target_brief.py -q`
Expected: PASS.

- [ ] **Step 5: Read one real dispute end to end**

The prose is the deliverable, so read it rather than only asserting on it.

```bash
uv run python - <<'PY'
import pathlib
from rubrica import target_brief
from rubrica.paths import RunPaths
root = pathlib.Path("runs/run-20260826-090456")
if not root.exists():
    print("parsec run absent; read a dispute from any run in runs/ instead")
else:
    found = target_brief.disputes(RunPaths(root))
    unresolved = [d for d in found if d.resolution == "unresolved"]
    print(f"total={len(found)} unresolved={len(unresolved)}")
    d = found[0]
    print(f"\n{d.nature}\n")
    for label, side in (("A", d.side_a), ("B", d.side_b)):
        for ref in side:
            print(f"  {label}: {ref.path}  {ref.locator}\n     {ref.quote[:100]}")
    print(f"\n  {d.taken}   ref: {d.id}")
PY
```
Expected: 41 total, 15 unresolved, and a dispute that reads as two files quoting
themselves. **Judgment check, not an assertion:** if the printed block would not
make sense to someone who has never heard of rubrica, say so in the review rather
than proceeding — that is the whole premise of the document.

- [ ] **Step 6: `make check` and commit**

```bash
make check
git add src/rubrica/target_brief.py tests/unit/test_target_brief.py
git commit -S -s -F - <<'MSG'
feat: Put the target's own disagreements to its owners, with both sides quoted

The section that earns the report. parsec's 41 contradictions are
documentation-vs-implementation drift in the owner's own terms: a design doc
specifying verify=False on a client the connections claim describes without it, a
doc stating query_aap2 exposes three actions against a module exposing four,
elapsed/name in the agent instructions against duration_seconds/job_name in the
implementation. Those get acted on the day they are read.

It is also where the claim-id leak dissolves rather than being stripped. Every
cited id resolves to a path, a locator and a quoted line -- measured, parsec
resolves all 230 of the claims its world model cites and quotes 224 -- so a
contradiction renders as two real files quoting themselves instead of two ids.

Two judgments. `nature` is carried verbatim and `rationale` is dropped: the second
is dense with claim ids and argues the case to a reader who already accepts the
framing, and it stays available in run-summary. And the resolved-side sentence
names the file rather than saying "we went with the code", because code-ness would
have to be inferred from `kind` and the kinds measured do not support it --
reservation-service's capabilities each span four at once.

A contradiction whose citations dangle is still rendered. The nature prose is the
payload and the sides corroborate it; a dangling citation is check-refs' finding,
not a reason to hide a real disagreement from the people who can settle it.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
```

---
### Task 5: Group D — "your documents never said"

**Files:**
- Modify: `src/rubrica/target_brief.py`
- Test: `tests/unit/test_target_brief.py`

**Interfaces:**
- Consumes: nothing beyond `brief._quietly/_mapping/_dicts` and
  `summary._absent_or_malformed`.
- Produces: `OpenQuestion(id: str, subject: str, unknown: str)`;
  `open_questions(run: RunPaths) -> list[OpenQuestion] | Marker`.

**Two fields deliberately dropped, and one of them is the design's weakest
point.**

`blocks` is a list of pipeline stage names — pure internals.

`why_it_matters` is the harder call, and §4.3 records it as the weakest point in
the design. It is the one field where owner-facing and internal prose are fused
inside a single string: *"a scenario built on the empty outcome class has no
stated ground truth"* is rubrica talking about itself. Selecting it leaks;
splitting it means rewriting it, which the whole document forbids. So one generic
sentence heads the group instead (Task 7), and the acknowledged cost is that an
owner is not told why each individual question matters. **If a reviewer wants this
revisited, it is a spec change, not a code change.**

**No provenance line on a gap.** Measured: every gap in all three runs carries no
`claims` key at all — 0 of 18, 0 of 19, 0 of 15. This costs nothing, because a gap
is by definition a place no claim reached and the `unknown` prose *is* the
question.

- [ ] **Step 1: Write the failing tests**

```python
def test_open_questions_carries_unknown_verbatim_and_drops_the_internals(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["gaps"] = [
        {
            "id": "gap-002",
            "subject": "get_ticket",
            "unknown": "What get_ticket returns for an unknown ticket_id",
            # Fused owner-facing and internal prose, which is why the field is
            # dropped rather than selected or rewritten.
            "why_it_matters": "a scenario built on the empty outcome class has no "
            "stated ground truth, so score cannot rank it",
            "blocks": ["propose", "score"],
        },
        {
            "id": "gap-001",
            "subject": "rate limits",
            "unknown": "Whether the API rate-limits and with what response",
            "why_it_matters": "instantiate cannot seed a limit it cannot name",
            "blocks": ["instantiate"],
        },
    ]
    run.world_model.write_text(json.dumps(world_model))
    found = target_brief.open_questions(run)
    assert [q.id for q in found] == ["gap-001", "gap-002"]
    assert found[1].unknown == "What get_ticket returns for an unknown ticket_id"
    assert found[1].subject == "get_ticket"
    # The two internal fields reach no attribute of the record. Asserted over
    # every field rather than by naming two, so a third internal field added to
    # the schema later cannot arrive here unnoticed.
    rendered = " ".join(str(v) for q in found for v in vars(q).values())
    for leaked in ("propose", "score", "instantiate", "outcome class", "ground truth"):
        assert leaked not in rendered
    assert not hasattr(found[0], "why_it_matters")
    assert not hasattr(found[0], "blocks")


def test_open_questions_renders_a_gap_that_cites_no_claim(tmp_path):
    """The normal case, not the edge case: every gap in all three runs measured
    carries no `claims` key -- 0 of 18, 0 of 19, 0 of 15."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["gaps"] = [{"id": "gap-001", "subject": "s", "unknown": "u"}]
    run.world_model.write_text(json.dumps(world_model))
    assert target_brief.open_questions(run)[0].unknown == "u"


def test_open_questions_is_empty_on_the_toy_world_and_marks_an_unreadable_one(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    # The golden toy world has no gaps; an empty group and a missing world model
    # are different facts and the renderer says different things about them.
    assert target_brief.open_questions(run) == []
    run.world_model.write_text("{ not json")
    assert isinstance(target_brief.open_questions(run), Malformed)
    run.world_model.unlink()
    assert isinstance(target_brief.open_questions(run), Absent)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_target_brief.py -q -k open_questions`
Expected: FAIL — `AttributeError: ... has no attribute 'open_questions'`

- [ ] **Step 3: Write the minimal implementation**

```python
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
    payload = _mapping(_quietly(run.world_model))
    if not payload:
        return _absent_or_malformed(
            run.world_model, "01-world-model.json", "nothing could be read from it"
        )
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
```

Add the small helper this introduces, near `_shorten`:

```python
def _text(value) -> str:
    """`value` when it is a string, else `""`.

    A hand-edited `"unknown": 7` renders as an empty question rather than as the
    characters of an integer, and `""` is what the renderer tests to say it could
    not read the description. Never a stand-in sentence: invented prose in this
    document would be read as our assertion about the target.
    """
    return value if isinstance(value, str) else ""
```

Then use `_text` for the equivalent fields in Task 4's `Dispute` construction as
well, replacing the two inline `isinstance` ternaries there — one spelling, for
the reason this module imports its helpers rather than re-spelling them.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_target_brief.py -q`
Expected: PASS.

- [ ] **Step 5: Measure the leak predicate in both directions**

The `leaked not in rendered` loop is the one most likely to be vacuous — it passes
trivially if `open_questions` returns an empty list.

```bash
# Red: make the record carry why_it_matters, and the loop must fail.
uv run python - <<'PY'
import dataclasses, json, pathlib, sys, tempfile
sys.path.insert(0, "tests")
from toy import build_toy_run
from rubrica import target_brief
run = build_toy_run(pathlib.Path(tempfile.mkdtemp()), upto="reconcile-seal")
wm = json.loads(run.world_model.read_text())
wm["gaps"] = [{"id": "gap-001", "subject": "s", "unknown": "u",
               "why_it_matters": "score cannot rank it", "blocks": ["propose"]}]
run.world_model.write_text(json.dumps(wm))
found = target_brief.open_questions(run)
print("fields:", [f.name for f in dataclasses.fields(found[0])])
print("rendered:", " ".join(str(v) for v in vars(found[0]).values()))
PY
```
Expected: fields are exactly `['id', 'subject', 'unknown']` and the rendered
string contains neither `score` nor `propose`. Then confirm the test is not
vacuous by checking it fails if `why_it_matters` is added to the dataclass — add
the field temporarily, run the test, watch it go red, remove it.

- [ ] **Step 6: `make check` and commit**

```bash
make check
git add src/rubrica/target_brief.py tests/unit/test_target_brief.py
git commit -S -s -F - <<'MSG'
feat: Ask the owners what their documents never said

Three of a gap's seven fields. `blocks` is a list of stage names, pure internals.

`why_it_matters` is the harder omission and this design's acknowledged weak point.
It is the one field where owner-facing and internal prose are fused inside a
single string -- "a scenario built on the empty outcome class has no stated ground
truth" is rubrica talking about itself. Selecting it leaks and splitting it means
rewriting prose this document never rewrites, so one generic sentence heads the
group instead. The cost is real and recorded rather than hidden: an owner is not
told why each individual question matters.

No provenance line on a gap, because there is nothing to build one from and
nothing missing. Measured: every gap in all three runs on disk carries no
`claims` key -- 0 of 18, 0 of 19, 0 of 15 -- and a gap is by definition a place no
claim reached, so the `unknown` prose is the whole record.

The leak test asserts over every field of the record rather than naming the two
dropped ones, so a third internal field added to the schema later cannot arrive in
this document unnoticed.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
```

---
### Task 6: Tier 2 — what we believe, in full

Three collapsed sections beneath the asks: what it can do, what data it holds, who
uses it. Each element carries Task 2's provenance line.

**Files:**
- Modify: `src/rubrica/target_brief.py`
- Test: `tests/unit/test_target_brief.py`

**Interfaces:**
- Consumes: `Provenance`, `provenance`, `disputed_claim_ids` (Task 2);
  `source_index` (Task 1).
- Produces: `Outcome(label: str, description: str)`;
  `Operation(id, handle, sentence, params: tuple[str, ...], outcomes: tuple[Outcome, ...], provenance: Provenance)`;
  `Field(name: str, type: str)`;
  `DataType(id, name, collection, fields: tuple[Field, ...], relations: tuple[str, ...], rules: tuple[str, ...], provenance: Provenance)`;
  `Persona(id, name, goals: tuple[str, ...], provenance: Provenance)`;
  `operations(run) -> list[Operation] | Marker`;
  `data_types(run) -> list[DataType] | Marker`;
  `personas(run) -> list[Persona] | Marker`.

**Outcome provenance comes from the parent capability.** An outcome class's own
`claims` may not exist: the parsec run fails layer 1 with 213 findings, 195 of them
`'claims' is a required property` on outcome classes. That is the parked
[`limitations.md`](../../design/limitations.md) ruling "Two committed recordings
predate the requirement that every element cite a claim" — the three `$defs` gained
required `claims` arrays when read coverage was forced, and re-recording is parked
because hand-writing them would fabricate the project's only behavioural evidence.
**Do not attempt to fix it here.** Capability-level `claims` are present on 39 of
39, 37 of 37 and 5 of 5, so `Operation.provenance` reads those and `Outcome` carries
none.

**No mechanical absence detection.** parsec records exactly one outcome class of
each of the five kinds per capability, and absence is expressed *in prose under the
semantic kind*: `oc-qac-empty` is `kind: empty` carrying "No claim addresses what is
returned when no cost data exists." So `kind` does not mark absence, no other field
does, and the alternative is string-matching model prose. The five plain labels plus
a legend (Task 7) carry it instead.

- [ ] **Step 1: Write the failing tests**

```python
def test_operations_reads_handle_sentence_params_and_labelled_outcomes(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    found = {op.id: op for op in target_brief.operations(run)}
    op = found["cap-find-tickets"]
    assert op.handle == "query_tickets"          # binding.tool
    assert op.sentence == "query_tickets.find_tickets"
    assert op.params == ("queue (string, optional)", "status (string, optional)")
    # Labels are owner-facing, and only the kinds actually present appear. The toy
    # world records success and empty; parsec records all five.
    assert [(o.label, o.description) for o in op.outcomes] == [
        ("On success", "one or more tickets match the filters"),
        ("When there is nothing to return", "no ticket matches the filters"),
    ]
    # Provenance is the capability's own claims, all three in api.json.
    assert op.provenance.files == ("api.json",)
    assert op.provenance.single_source is True
    assert found["cap-get-ticket"].params == ("ticket_id (integer, required)",)


def test_operations_takes_provenance_from_the_capability_when_an_outcome_cites_nothing(
    tmp_path,
):
    """The parsec run fails layer 1 with 195 findings of `'claims' is a required
    property` on outcome classes -- the parked "recordings predate the requirement"
    ruling. Capability-level claims are present on 39 of 39, so provenance reads
    those."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    for capability in world_model["capabilities"]:
        for outcome in capability["outcome_classes"]:
            outcome.pop("claims", None)
    run.world_model.write_text(json.dumps(world_model))
    op = target_brief.operations(run)[0]
    assert op.provenance.files == ("api.json",)
    assert op.outcomes  # still rendered, still labelled
    assert not hasattr(op.outcomes[0], "provenance")


def test_operations_falls_back_to_the_operation_string_when_there_is_no_binding(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["capabilities"][0].pop("binding")
    run.world_model.write_text(json.dumps(world_model))
    assert target_brief.operations(run)[0].handle == "query_tickets.find_tickets"


def test_operations_keeps_an_outcome_whose_kind_is_not_in_the_enum(tmp_path):
    """A label we do not have is not a reason to drop an outcome: the description
    is the payload. The kind itself is shown so the row is not mislabelled."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["capabilities"][0]["outcome_classes"][0]["kind"] = "invented"
    run.world_model.write_text(json.dumps(world_model))
    assert target_brief.operations(run)[0].outcomes[0].label == "invented"


def test_data_types_reads_fields_relations_and_rules(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    found = {d.id: d for d in target_brief.data_types(run)}
    ticket = found["ent-ticket"]
    assert ticket.name == "Ticket"
    assert ticket.collection == "tickets"
    assert ticket.fields[0] == target_brief.Field("ticket_id", "integer")
    assert len(ticket.fields) == 5
    # The relation names the target entity, resolved. `ent-comment` is an id no
    # owner recognises; "Comment" is a word from their own vocabulary.
    assert ticket.relations == ("comments → Comment (many)",)
    # The toy invariants carry `statement` and no `prose`, so the fallback is the
    # measured-normal path rather than the edge case.
    assert "comment_count is the number of comments on the ticket" in ticket.rules


def test_data_types_prefers_invariant_prose_over_statement_when_present(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["entities"][0]["invariants"][0]["prose"] = "Every comment is counted once."
    run.world_model.write_text(json.dumps(world_model))
    rules = target_brief.data_types(run)[0].rules
    assert "Every comment is counted once." in rules
    assert not any("comment_count is the number" in r for r in rules)


def test_data_types_names_an_unresolvable_relation_target_by_its_id(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["entities"][0]["relations"][0]["target_entity_id"] = "ent-ghost"
    run.world_model.write_text(json.dumps(world_model))
    assert target_brief.data_types(run)[0].relations == ("comments → ent-ghost (many)",)


def test_personas_pair_each_actor_with_its_goals(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    found = target_brief.personas(run)
    assert [p.name for p in found] == ["Support engineer"]
    assert found[0].goals == (
        "Locate the ticket that needs action, or establish that it does not exist",
        "Read the comments on a ticket to decide what to do next",
    )
    assert found[0].provenance.files == ("notes.md",)


def test_personas_keeps_a_goal_no_actor_claims(tmp_path):
    """A goal whose actor_id resolves to nothing must not vanish: it is something
    the run believes about the target, and dropping it silently would make the
    description quietly incomplete."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["goals"][0]["actor_id"] = "act-ghost"
    run.world_model.write_text(json.dumps(world_model))
    everything = " ".join(g for p in target_brief.personas(run) for g in p.goals)
    assert "Locate the ticket that needs action" in everything


@pytest.mark.parametrize("builder", ["operations", "data_types", "personas"])
def test_tier_two_builders_mark_an_unreadable_world_model(tmp_path, builder):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    run.world_model.write_text("{ not json")
    assert isinstance(getattr(target_brief, builder)(run), Malformed)
    run.world_model.unlink()
    assert isinstance(getattr(target_brief, builder)(run), Absent)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_target_brief.py -q -k "operations or data_types or personas or tier_two"`
Expected: FAIL — `AttributeError: ... has no attribute 'operations'`

- [ ] **Step 3: Write the minimal implementation**

```python
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


def _world(run: RunPaths):
    """The world model, or the marker naming why there is none.

    One reader for the five builders below, so they cannot disagree about whether
    a run has a world model.
    """
    payload = _mapping(_quietly(run.world_model))
    if not payload:
        return _absent_or_malformed(
            run.world_model, "01-world-model.json", "nothing could be read from it"
        )
    return payload


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
    """
    out = []
    for record in _dicts(value):
        name = _text(record.get("name"))
        target = _text(record.get("target_entity_id"))
        cardinality = _text(record.get("cardinality"))
        label = names.get(target, target)
        out.append(f"{name} → {label} ({cardinality})" if cardinality else f"{name} → {label}")
    return tuple(out)


def _rules(value) -> tuple[str, ...]:
    """Each invariant as one sentence, `prose` preferred over `statement`.

    `prose` is the human phrasing where a pass wrote one; the toy world and the
    committed recordings carry `statement` only, so the fallback is the normal
    path rather than the edge case.
    """
    return tuple(
        sentence
        for record in _dicts(value)
        if (sentence := _text(record.get("prose")) or _text(record.get("statement")))
    )


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
    index = source_index(run)
    refs = index if isinstance(index, dict) else {}
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
    index = source_index(run)
    refs = index if isinstance(index, dict) else {}
    disputed = disputed_claim_ids(payload)
    entities = _dicts(payload.get("entities"))
    names = {
        _text(e.get("id")): _text(e.get("name")) for e in entities if _text(e.get("name"))
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
    index = source_index(run)
    refs = index if isinstance(index, dict) else {}
    disputed = disputed_claim_ids(payload)
    goals = _dicts(payload.get("goals"))
    out = []
    claimed: set[str] = set()
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_target_brief.py -q`
Expected: PASS.

- [ ] **Step 5: Confirm it survives the run that fails layer 1**

```bash
uv run rubrica validate --run runs/run-20260826-090456 --stage reconcile-seal > /dev/null 2>&1; echo "validate exit: $?  (1 expected -- the parked ruling)"
uv run python - <<'PY'
import pathlib
from rubrica import target_brief
from rubrica.paths import RunPaths
root = pathlib.Path("runs/run-20260826-090456")
if not root.exists():
    print("parsec run absent; skip")
else:
    run = RunPaths(root)
    ops = target_brief.operations(run)
    print(f"operations={len(ops)} with_provenance={sum(1 for o in ops if o.provenance.files)}")
    print(f"outcomes={sum(len(o.outcomes) for o in ops)}")
    print(f"data_types={len(target_brief.data_types(run))} personas={len(target_brief.personas(run))}")
PY
```
Expected: `validate exit: 1` (the parked ruling, not a regression), and
`operations=39 with_provenance=39`, `outcomes=195`, `data_types=30 personas=3`
(two actors plus the unattributed-goals bucket, if any goal is unattributed). The
point of this step is that a world model failing layer 1 still renders completely.

- [ ] **Step 6: `make check` and commit**

```bash
make check
git add src/rubrica/target_brief.py tests/unit/test_target_brief.py
git commit -S -s -F - <<'MSG'
feat: Describe the target's operations, data and users in the owner's vocabulary

The tier-2 body: what it can do, what it holds, who uses it. Selection and
relabelling only -- `binding.tool` as the handle, `operation` as the sentence, the
five outcome kinds under plain labels, entity relations with their target ids
resolved to names because `ent-comment` is an id no owner recognises and "Comment"
is a word from theirs.

Outcome provenance reads the parent capability's claims, never the outcome's own.
The parsec run fails layer 1 with 213 findings, 195 of them `'claims' is a
required property` on outcome classes, which is the parked "recordings predate the
requirement that every element cite a claim" ruling and not this feature's to fix.
Capability-level claims are present on 39 of 39, 37 of 37 and 5 of 5, so the
fallback is exact rather than approximate, and a world model failing layer 1 still
renders completely.

No mechanical absence detection. parsec records exactly one outcome class of each
of the five kinds per capability and expresses absence *in prose under the
semantic kind* -- `oc-qac-empty` is `kind: empty` carrying "No claim addresses what
is returned when no cost data exists." So `kind` cannot mark absence, nothing else
can, and the alternative is string-matching model prose. Plain labels plus a legend
carry it.

Two things kept rather than dropped, both because a description asking "is this
accurate?" cannot afford to be quietly incomplete: an outcome whose kind is outside
the enum keeps its raw kind as the label, and a goal whose actor_id resolves to
nothing goes in a named bucket instead of vanishing.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
```

---
### Task 7: The page

The document itself: a headline naming the target, the four asks, the three
collapsed belief sections, and one paragraph saying how to reply.

**Files:**
- Create: `src/rubrica/target_brief_html.py`
- Modify: `src/rubrica/target_brief.py` (add `headline`)
- Test: `tests/unit/test_target_brief_html.py`, `tests/unit/test_target_brief.py`

**Interfaces:**
- Consumes: every builder from Tasks 1–6.
- Produces: `target_brief.Headline(name: str, interface: str, notes: str)`;
  `target_brief.headline(run) -> Headline | Marker`;
  `target_brief_html.render(run) -> str`.

**Three rulings this task makes, each with its measurement:**

**1. No JavaScript at all.** `summary_html` ships `_JS` for sortable tables. This
page ships none: `<details>` collapses natively, nothing here sorts, and the page
is *emailed out of the project* — an attachment opened in a mail client's browser
view, a corporate proxy, or a reader with scripts off. A page that needs a script
to be readable is a page that arrives broken for some recipients. Self-contained
still holds: inline CSS, no network, no external asset.

**2. Its own `_CSS`, not an import of `summary_html._CSS`.** Coupling them would
let a tweak to the operator page silently restyle a document that has already
been sent to somebody outside the project. The two pages also want different
things — this one has no matrix, no spine and no sortable header, and it does want
generous type for reading rather than density for scanning.

**3. Its own marker prose.** `summary_html._marker` says
`Not present: 01-world-model.json`, which is exactly right for an operator and
meaningless to an owner. Here the same fact reads "We have not got far enough to
describe this yet." — the artifact name is dropped because the recipient cannot
act on it, and a marker is still *rendered rather than skipped*, for
`summary_html._section`'s reason: a section that disappears is indistinguishable
from one this renderer forgot.

**A page-level banner when `source_index` returns a `Marker`.** Task 1 returns a
marker rather than an empty index when `01-claims/` cannot be read, so every
provenance line on the page would silently read as unsourced. Silently is the
problem: this document's whole claim is "here is what we believe and here is where
we read it", and a version that quietly drops every citation looks like a
confident description with no sources rather than a broken render. The banner says
so at the top, once.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_target_brief_html.py
from __future__ import annotations

import json
import re

from rubrica import target_brief_html
from tests.toy import build_toy_run


def test_page_is_self_contained_and_carries_no_script(tmp_path):
    page = target_brief_html.render(build_toy_run(tmp_path, upto="reconcile-seal"))
    assert page.startswith("<!doctype html>")
    assert page.rstrip().endswith("</html>")
    # Ruling 1: emailed out of the project, so it must read with scripts off.
    assert "<script" not in page.lower()
    # Self-contained: no network, no external asset.
    assert "http://" not in page and "https://" not in page
    assert "<style>" in page


def test_page_names_the_target_and_asks_the_question(tmp_path):
    page = target_brief_html.render(build_toy_run(tmp_path, upto="reconcile-seal"))
    assert "ticketq" in page
    assert "does this accurately describe your system?" in page.lower()
    # The dropped sign-off block must not come back by accident.
    for word in ("sign off", "sign-off", "signature", "approve", "ratif"):
        assert word not in page.lower()


def test_page_leads_with_the_asks_and_puts_the_description_beneath(tmp_path):
    page = target_brief_html.render(build_toy_run(tmp_path, upto="reconcile-seal"))
    # Tier 1 before tier 2: the ask-list is the point, the full description is
    # the appendix that supports it.
    assert page.index("Where our sources disagree") < page.index("What we believe")
    # Tier 2 is collapsed; tier 1 is not.
    body = page[page.index("What we believe") :]
    assert "<details>" in body
    assert "<details>" not in page[: page.index("What we believe")]


def test_page_renders_every_group_and_every_tier_two_section(tmp_path):
    page = target_brief_html.render(build_toy_run(tmp_path, upto="reconcile-seal"))
    for heading in (
        "What we read",
        "Where our sources disagree",
        "What we could not tell",
        "What we believe",
        "What it can do",
        "What data it holds",
        "Who uses it",
    ):
        assert heading in page


def test_page_renders_the_toy_contradiction_with_both_files_named(tmp_path):
    page = target_brief_html.render(build_toy_run(tmp_path, upto="reconcile-seal"))
    # The claim ids dissolve into the files that state them: an owner reads two
    # of their own documents disagreeing, never `clm-notes-004`.
    assert "notes.md" in page and "trace.json" in page
    assert "clm-notes-004" not in page and "clm-trace-002" not in page


def test_page_distinguishes_two_operations_that_share_a_handle(tmp_path):
    """Both toy capabilities carry `binding.tool == "query_tickets"`, so heading
    each entry on the handle prints the same word twice and the reader cannot tell
    which operation is which. The `operation` string is what distinguishes them."""
    page = target_brief_html.render(build_toy_run(tmp_path, upto="reconcile-seal"))
    assert "query_tickets.find_tickets" in page
    assert "query_tickets.get_ticket" in page


def test_page_states_a_marker_instead_of_dropping_the_section(tmp_path):
    """A partial run must produce a page that says what it has not got to, in the
    owner's words -- not a page missing a section, which is indistinguishable from
    a renderer that forgot one."""
    run = build_toy_run(tmp_path, upto="extract")
    page = target_brief_html.render(run)
    assert "What we believe" in page
    assert "not got far enough" in page
    # An operator's artifact name is not something an owner can act on.
    assert "01-world-model.json" not in page


def test_page_banners_an_unreadable_claims_directory_once(tmp_path):
    """Task 1 returns a marker rather than an empty index, so the page must say
    the citations are missing rather than render as a confident description with
    no sources."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    run.claims_dir.chmod(0o000)
    try:
        page = target_brief_html.render(run)
    finally:
        run.claims_dir.chmod(0o755)
    assert page.count('class="banner"') == 1
    assert "could not read" in page.lower()
    # It still describes the target: the banner qualifies the page, not the read.
    assert "ticketq" in page and "What it can do" in page


def test_page_carries_the_not_addressed_legend_only_when_that_label_appears(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    legend = "we looked for it and no document stated it"
    assert legend not in target_brief_html.render(run)
    world_model = json.loads(run.world_model.read_text())
    world_model["capabilities"][0]["outcome_classes"][0]["kind"] = "underspecified"
    run.world_model.write_text(json.dumps(world_model))
    assert legend in target_brief_html.render(run)


def test_page_escapes_owner_controlled_prose(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["target"]["notes"] = '<script>alert("x")</script>'
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    assert "<script" not in page.lower()
    assert "&lt;script&gt;" in page


def test_page_renders_a_lone_surrogate_rather_than_failing_to_write(tmp_path):
    """`summary.esc` is the one place that decides this, and it is why this module
    escapes everything through it -- a `UnicodeEncodeError` from `write_text` is a
    ValueError that escaped every handler but the catch-all once."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["target"]["notes"] = "bad \udcff byte"
    run.world_model.write_text(json.dumps(world_model))
    out = tmp_path / "brief.html"
    out.write_text(target_brief_html.render(run), encoding="utf-8")  # must not raise
    assert "bad" in out.read_text(encoding="utf-8")


def test_page_never_shows_a_rubrica_identifier(tmp_path):
    """The whole premise: about the target, not about rubrica. Any id shape
    reaching the page is a builder leaking, and this is the net that catches one
    no per-builder test thought to look for."""
    page = target_brief_html.render(build_toy_run(tmp_path, upto="reconcile-seal"))
    leaked = re.findall(r"\b(?:clm|cap|ent|act|goal|gap|con|oc|art)-[a-z0-9-]+", page)
    assert leaked == [], leaked


def test_page_never_names_a_stage_a_gate_or_an_artifact(tmp_path):
    page = target_brief_html.render(build_toy_run(tmp_path, upto="reconcile-seal")).lower()
    for word in (
        "reconcile",
        "extract",
        "triage",
        "world model",
        "claim",
        "artifact",
        "gate",
        "manifest",
        "rubrica",
        "scenario",
    ):
        assert word not in page, word
```

```python
# tests/unit/test_target_brief.py -- the one builder this task adds
def test_headline_reads_name_interface_and_notes(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    head = target_brief.headline(run)
    assert head.name == "ticketq"
    assert head.interface == "mcp"
    assert head.notes == ""  # the toy target carries none, and neither does parsec


def test_headline_keeps_notes_where_a_pass_wrote_them(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["target"]["notes"] = "A ticket queue behind MCP."
    run.world_model.write_text(json.dumps(world_model))
    assert target_brief.headline(run).notes == "A ticket queue behind MCP."


def test_headline_marks_a_missing_world_model(tmp_path):
    run = build_toy_run(tmp_path, upto="extract")
    assert isinstance(target_brief.headline(run), Absent)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_target_brief_html.py tests/unit/test_target_brief.py -q -k "html or page or headline"`
Expected: FAIL — `ModuleNotFoundError: No module named 'rubrica.target_brief_html'`

- [ ] **Step 3: Add `headline` to `target_brief.py`**

```python
@dataclass(frozen=True)
class Headline:
    """The target, as the run names it.

    `notes` is optional in the schema and absent from both of the two most recent
    recordings, so the page must read without it: `interface` and `name` are the
    two required fields and the only two guaranteed to be there.
    """

    name: str
    interface: str
    notes: str


def headline(run: RunPaths) -> Headline | Marker:
    payload = _world(run)
    if isinstance(payload, Marker):
        return payload
    target = _mapping(payload.get("target"))
    return Headline(
        name=_text(target.get("name")),
        interface=_text(target.get("interface")),
        notes=_text(target.get("notes")),
    )
```

- [ ] **Step 4: Write `target_brief_html.py`**

```python
"""The markup half of `target-brief`. `target_brief.py` reads and computes.

The same split as `summary.py` / `summary_html.py`, for the same reason: a section
that disagrees with the numbers a human reads beside it is then a defect in one
builder rather than in two spellings of the same read.

Three things this page does differently from `summary_html`, all because it leaves
the project rather than sitting in a run directory:

**No JavaScript.** Not one line. `<details>` collapses natively, nothing here
sorts, and this page is emailed -- opened in a mail client's browser view, behind a
corporate proxy, by a reader with scripts off. A page that needs a script to be
readable arrives broken for some of its recipients.

**Its own `_CSS`.** Importing `summary_html._CSS` would let a tweak to the operator
page restyle a document already sent to somebody outside the project.

**Its own marker prose.** `summary_html` says `Not present: 01-world-model.json`,
which is right for an operator and meaningless to an owner; here the same fact
reads "We have not got far enough to describe this yet."

**Nothing on this page names a stage, a gate, an artifact, a claim id or rubrica
itself,** and `test_page_never_names_a_stage_a_gate_or_an_artifact` plus
`test_page_never_shows_a_rubrica_identifier` fail the suite rather than let one
back in. That is not tidiness: a recipient asked "does this describe your system?"
who is instead reading about `01-world-model.json` has been handed the wrong
question.

Everything user-controlled goes through `summary.esc`, including numbers and dict
keys, for the reason its docstring gives -- a lone surrogate becomes text there,
and it was a report exiting 1 after rendering correctly before it did.
"""

from __future__ import annotations

from rubrica import target_brief
from rubrica.paths import RunPaths
from rubrica.summary import Malformed, Marker, esc

# Wider measure and larger type than `summary_html`: this is read as prose by
# somebody deciding whether it is true, not scanned as a table by an operator.
_CSS = """
:root { color-scheme: light dark; }
body { font: 16px/1.65 system-ui, sans-serif; margin: 0 auto; max-width: 46rem;
       padding: 2.5rem 1.5rem 6rem; }
h1 { font-size: 1.6rem; margin-bottom: .2rem; }
h2 { font-size: 1.15rem; margin-top: 2.75rem; border-bottom: 1px solid currentColor;
     padding-bottom: .3rem; }
h3 { font-size: 1rem; margin: 1.75rem 0 .35rem; }
p { margin: .6rem 0; }
ul { margin: .5rem 0; padding-left: 1.3rem; }
li { margin: .3rem 0; }
.lede { font-size: 1.05rem; }
.meta { opacity: .75; font-size: .9rem; margin-top: 0; }
/* The one thing on the page that qualifies the whole page. */
.banner { border-left: 4px solid #c60; padding: .6rem .9rem; margin: 1.5rem 0;
          font-weight: 600; }
.absent, .malformed { opacity: .75; font-style: italic; }
.malformed { border-left: 3px solid #c60; padding-left: .6rem; }
/* Where we read it. Subordinate to the sentence above it, never competing. */
.src { display: block; font-size: .85rem; opacity: .7; margin-top: .15rem; }
.src .file { font-family: ui-monospace, monospace; }
.disputed { font-weight: 600; }
.quote { font-family: ui-monospace, monospace; font-size: .85rem; }
.legend { font-size: .9rem; opacity: .8; }
.reply { border: 1px solid #8886; border-radius: 4px; padding: 1rem 1.2rem;
         margin-top: 3rem; }
details { margin: .8rem 0; }
details summary { cursor: pointer; font-weight: 600; }
dl { margin: .4rem 0; }
dt { font-weight: 600; margin-top: .7rem; }
dd { margin: .15rem 0 .15rem 1.2rem; }
"""

# One rendering of "we looked and no document said", emitted at most once per page
# and only when a `Not addressed` label actually appears. A legend for a label the
# page does not use is noise on a document somebody is asked to read closely.
_NOT_ADDRESSED = "Not addressed"
_LEGEND = (
    '<p class="legend">“Not addressed” below means we looked for it and no '
    "document stated it — not that the behaviour is missing from your system.</p>"
)


def _marker(body: Marker) -> str:
    """A marker in the recipient's terms.

    The artifact name is dropped deliberately: an owner cannot act on
    `01-world-model.json`, and the operator page beside this one already names it.
    The two markers stay two sentences for `summary_html._marker`'s reason -- one
    is work not yet done, the other is a defect -- because spelling both the same
    way is what let one page say a stage had produced an artifact and that the
    artifact was not there.
    """
    if isinstance(body, Malformed):
        return (
            '<p class="malformed">We have this on file but could not read it back, '
            "so this section is incomplete.</p>"
        )
    return '<p class="absent">We have not got far enough to describe this yet.</p>'


def _section(heading: str, body) -> str:
    """One section, its heading always present, a marker rendered rather than skipped."""
    inner = _marker(body) if isinstance(body, Marker) else body
    return f"<h2>{esc(heading)}</h2>\n{inner}\n"


def _provenance(prov) -> str:
    """Where we read it: the files, their kinds, and whether they disagreed.

    One line under the sentence it supports rather than a column, because the
    sentence is what the recipient is being asked about and the source is how they
    check it. `single_source` is read from the property rather than recomputed here
    -- Task 2 made it a property precisely so no caller can disagree with `files`.
    """
    if not prov.files:
        return ""
    files = ", ".join(f'<span class="file">{esc(f)}</span>' for f in prov.files)
    if prov.single_source:
        text = f"From {files}"
    else:
        kinds = ", ".join(esc(k) for k in prov.kinds)
        text = f"From {len(prov.files)} sources ({kinds}): {files}"
    if prov.disputed:
        text += ' — <span class="disputed">our sources disagree about this</span>'
    return f'<span class="src">{text}.</span>'


def _group_a(run: RunPaths):
    """What we read. The first ask, because it is the one an owner can answer
    without reading anything else: a file they know we should have had and did not
    is a correction that invalidates everything below it."""
    groups = target_brief.inputs_read(run)
    if isinstance(groups, Marker):
        return groups
    if not groups:
        return '<p class="absent">We have no record of what we read.</p>'
    items = []
    for group in groups:
        files = ", ".join(f'<span class="file">{esc(f)}</span>' for f in group.files)
        # The slice count is why "we read 269 things" and "we read 199 files" are
        # both true: 71 of parsec's inputs are `#/NN` slices of one capture.
        tail = (
            f" (read as {len(group.files) + group.slices} pieces)" if group.slices else ""
        )
        items.append(
            f"<li><strong>{esc(group.kind)}</strong> "
            f'under <span class="file">{esc(group.directory)}</span>{tail}: {files}</li>'
        )
    return (
        "<p>We built this description by reading the following. "
        "<strong>If something important is not here, tell us — that is the most "
        "useful correction you can give us.</strong></p>"
        f"<ul>{''.join(items)}</ul>"
    )


def _group_bc(run: RunPaths):
    """Where our sources disagree, and what we did about it. Tasks 4's `Dispute`
    carries both the two sides and the side taken, so B and C are one list rather
    than two: a reader deciding "which of these two is right" needs to see in the
    same place which one we acted on."""
    found = target_brief.disputes(run)
    if isinstance(found, Marker):
        return found
    if not found:
        return (
            '<p class="absent">Nothing we read contradicted anything else we read. '
            "That is a weaker statement than it sounds: it means we found no "
            "disagreement, not that your documents agree.</p>"
        )
    items = []
    for dispute in found:
        items.append(
            f"<li><p>{esc(dispute.nature)}</p>"
            f"<p>{esc(dispute.side_a)}</p><p>{esc(dispute.side_b)}</p>"
            f"<p><strong>{esc(dispute.taken)}</strong></p></li>"
        )
    return (
        "<p>Two things we read said different things. Each one below is a place "
        "where a word from you settles it.</p>"
        f"<ul>{''.join(items)}</ul>"
    )


def _group_d(run: RunPaths):
    """What we could not tell. No provenance line: a gap cites nothing in any of
    the three recordings measured (0 of 18, 0 of 19, 0 of 15), so a provenance
    line here would be blank on every real run."""
    found = target_brief.open_questions(run)
    if isinstance(found, Marker):
        return found
    if not found:
        return (
            '<p class="absent">We did not record any open question. On a real '
            "target that is more likely to mean we did not notice one than that "
            "none exists.</p>"
        )
    items = [
        f"<li><strong>{esc(q.subject)}</strong> — {esc(q.unknown)}</li>" for q in found
    ]
    return (
        "<p>These are things we could not work out from what we read. They are "
        "questions, not criticisms.</p>"
        f"<ul>{''.join(items)}</ul>"
    )


def _operations(run: RunPaths):
    """What it can do."""
    found = target_brief.operations(run)
    if isinstance(found, Marker):
        return found
    if not found:
        return '<p class="absent">We did not identify anything it can be asked to do.</p>'
    blocks = []
    for op in found:
        params = (
            "<dd>Takes: " + esc(", ".join(op.params)) + "</dd>"
            if op.params
            else "<dd>Takes no parameters.</dd>"
        )
        outcomes = "".join(
            f"<dd><em>{esc(o.label)}:</em> {esc(o.description)}</dd>" for o in op.outcomes
        )
        # `sentence` (the `operation` string) heads the entry, not `handle`.
        # Measured on the toy world: both capabilities carry
        # `binding.tool == "query_tickets"`, so heading on the handle prints the
        # same word twice and the reader cannot tell which operation is which.
        # `operation` is `query_tickets.find_tickets` and distinguishes them. The
        # handle is shown under it only when it says something the sentence does
        # not -- on the toy it never does, which is why it is conditional.
        title = op.sentence or op.handle
        called = (
            f"<dd>Called as: {esc(op.handle)}</dd>"
            if op.handle and op.handle != title
            else ""
        )
        blocks.append(
            f"<dt>{esc(title)}</dt>{called}{params}{outcomes}"
            f"<dd>{_provenance(op.provenance)}</dd>"
        )
    return f"<dl>{''.join(blocks)}</dl>"


def _data_types(run: RunPaths):
    """What data it holds."""
    found = target_brief.data_types(run)
    if isinstance(found, Marker):
        return found
    if not found:
        return '<p class="absent">We did not identify the kinds of data it holds.</p>'
    blocks = []
    for kind in found:
        rows = [f"<dt>{esc(kind.name)}</dt>"]
        if kind.fields:
            fields = ", ".join(f"{esc(f.name)} ({esc(f.type)})" for f in kind.fields)
            rows.append(f"<dd>Fields: {fields}</dd>")
        for relation in kind.relations:
            rows.append(f"<dd>Related to: {esc(relation)}</dd>")
        for rule in kind.rules:
            rows.append(f"<dd>Rule we believe holds: {esc(rule)}</dd>")
        rows.append(f"<dd>{_provenance(kind.provenance)}</dd>")
        blocks.append("".join(rows))
    return f"<dl>{''.join(blocks)}</dl>"


def _personas(run: RunPaths):
    """Who uses it, and what they are trying to do."""
    found = target_brief.personas(run)
    if isinstance(found, Marker):
        return found
    if not found:
        return '<p class="absent">We did not identify who uses it.</p>'
    blocks = []
    for persona in found:
        goals = "".join(f"<dd>{esc(goal)}</dd>" for goal in persona.goals) or (
            "<dd>We did not record what they are trying to do.</dd>"
        )
        blocks.append(
            f"<dt>{esc(persona.name)}</dt>{goals}<dd>{_provenance(persona.provenance)}</dd>"
        )
    return f"<dl>{''.join(blocks)}</dl>"


def _banner(run: RunPaths) -> str:
    """One line qualifying the whole page when the citations could not be read.

    Task 1 returns a marker rather than an empty index for exactly this: without
    the banner every "From x.py" line on the page would silently vanish, and the
    result reads as a confident description with no sources rather than as a
    broken render. Emitted once, at the top, because it is a property of the page.
    """
    if isinstance(target_brief.source_index(run), Marker):
        return (
            '<p class="banner">We could not read our own record of where each '
            "statement below came from, so this copy does not show its sources. "
            "The statements themselves are unaffected — but ask us for a copy that "
            "cites them before relying on this one.</p>"
        )
    return ""


def _reply() -> str:
    """How to reply. This is what stands in place of the sign-off block the design
    dropped: the document asks for corrections in prose and offers no place to
    record an approval, because whether a ratification is worth collecting is a
    question these conversations have not answered yet."""
    return (
        '<div class="reply"><h2>How to reply</h2>'
        "<p>Reply in whatever form suits you — prose in an email is ideal. The four "
        "sections above are ranked: a missing source is worth more to us than a "
        "misread field, and a settled disagreement is worth more than a confirmed "
        "detail. You do not need to go through the full description below to be "
        "useful to us.</p>"
        "<p>We are not asking you to approve anything. We are asking whether this "
        "is true.</p></div>"
    )


def render(run: RunPaths) -> str:
    """The whole page, as one string."""
    head = target_brief.headline(run)
    name = head.name if isinstance(head, target_brief.Headline) else run.root.name
    interface = head.interface if isinstance(head, target_brief.Headline) else ""
    notes = head.notes if isinstance(head, target_brief.Headline) else ""
    # Built once, so the legend below can ask whether the label is on the page
    # rather than recomputing the operations to find out.
    operations = _operations(run)
    body = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{esc(name)} — does this describe your system?</title>",
        f"<style>{_CSS}</style></head><body>",
        f"<h1>{esc(name)}</h1>",
        f'<p class="meta">Reached over {esc(interface)}.</p>' if interface else "",
        '<p class="lede">This is what we currently believe about '
        f"<strong>{esc(name)}</strong>, written from your own documents. "
        "<strong>Does this accurately describe your system?</strong> Where it does "
        "not, we would rather hear it now than build on it.</p>",
        _banner(run),
        f"<p>{esc(notes)}</p>" if notes else "",
        "<h2>What we most need from you</h2>",
        _section("What we read", _group_a(run)),
        _section("Where our sources disagree", _group_bc(run)),
        _section("What we could not tell", _group_d(run)),
        "<h2>What we believe, in full</h2>",
        "<p>Everything below is the detail behind the asks above. Skim it or skip "
        "it — the sections above are where a correction helps us most.</p>",
        _LEGEND if _NOT_ADDRESSED in str(operations) else "",
        "<details><summary>What it can do</summary>",
        _section("What it can do", operations),
        "</details>",
        "<details><summary>What data it holds</summary>",
        _section("What data it holds", _data_types(run)),
        "</details>",
        "<details><summary>Who uses it</summary>",
        _section("Who uses it", _personas(run)),
        "</details>",
        _reply(),
        "</body></html>",
    ]
    return "\n".join(part for part in body if part)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_target_brief_html.py tests/unit/test_target_brief.py -q`
Expected: PASS.

`test_page_never_names_a_stage_a_gate_or_an_artifact` is the one most likely to
fail on the first attempt, and its failure is the guard working: the offending word
is prose to reword, never an assertion to relax. The one exception a reviewer may
grant is a word that is genuinely the *target's* vocabulary rather than rubrica's —
if the target under test is itself a claims-processing system, the test's word list
is wrong for that target and belongs behind a fixture-specific skip, argued in the
commit message.

- [ ] **Step 6: Render all three real runs and read the output**

```bash
for r in runs/run-20260826-090456 runs/run-20260825-094033 runs/run-20260816-172810; do
  [ -d "$r" ] || continue
  uv run python -c "
import pathlib, sys
from rubrica import target_brief_html
from rubrica.paths import RunPaths
page = target_brief_html.render(RunPaths(pathlib.Path('$r')))
out = pathlib.Path('$CLAUDE_JOB_DIR/tmp/$(basename $r).html')
out.write_text(page, encoding='utf-8')
print(f'{out} {len(page)} bytes script={\"<script\" in page.lower()}')
"
done
```

Expected: three files, no `<script`, and — this is the step that matters — **read
one of them end to end as the recipient.** The predicate tests cannot tell you
whether the document reads as a description of somebody's system or as a database
dump with polite headings. If it reads as the latter, that is a finding against
this task, not against the spec.

- [ ] **Step 7: `make check` and commit**

```bash
make check
git add src/rubrica/target_brief.py src/rubrica/target_brief_html.py \
        tests/unit/test_target_brief.py tests/unit/test_target_brief_html.py
git commit -S -s -F - <<'MSG'
feat: Render the target brief as one self-contained page for the target's owners

The document: a headline naming the target, the four asks ranked with "what did we
miss" first, the three belief sections collapsed beneath them, and one paragraph
saying how to reply.

Three deliberate departures from summary_html, all because this page leaves the
project rather than sitting in a run directory. No JavaScript at all -- <details>
collapses natively, nothing sorts, and an emailed attachment is opened behind
proxies and by readers with scripts off, so a page needing a script to be readable
arrives broken for some recipients. Its own _CSS, so a tweak to the operator page
cannot restyle a document already sent outside the project. Its own marker prose,
because "Not present: 01-world-model.json" is right for an operator and meaningless
to an owner.

Two tests are the premise rather than coverage: no rubrica identifier of any shape
reaches the page, and no stage, gate, artifact or the project's own name appears in
it. A recipient asked "does this describe your system?" who is instead reading
about 01-world-model.json has been handed the wrong question. Both failures are
prose to reword, never assertions to relax.

The page banners an unreadable claims directory once, at the top. Without it every
"From x.py" line silently vanishes and the result reads as a confident description
with no sources -- which is why the source index returns a marker rather than an
empty dict.

No sign-off block, no signature, no place to record an approval: the design dropped
it pending whether these conversations turn out to want one, and the closing
paragraph says outright that we are asking whether this is true rather than asking
anyone to approve it.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
```

---
### Task 8: The subcommand, and the documents that must agree with it

`rubrica target-brief --run RUN [-o PATH]`, plus the three documents
`test_docs_accuracy.py` will fail until they name it, plus the one line at gate 1
that tells a human this exists.

**Files:**
- Modify: `src/rubrica/target_brief.py` (add the `page` entry point)
- Modify: `src/rubrica/cli.py:100-110` (`SUBCOMMANDS`), the parser block after
  `run-summary`'s, and the handler arm after `run-summary`'s
- Modify: `src/rubrica/brief.py` (one line at the end of `_gate_1`)
- Modify: `docs/reference/cli.md` (a `### rubrica target-brief` section, and the
  "The human's own reports" paragraph that lists which subcommands are reports)
- Modify: `CLAUDE.md` (the reports-not-gates paragraph under "The deterministic
  subcommands")
- Test: `tests/unit/test_cli.py`, `tests/unit/test_brief.py`

**Interfaces:**
- Consumes: `target_brief_html.render` (Task 7).
- Produces: `target_brief.page(run) -> str`.

**Why `page` rather than `target_brief`.** `summary.run_summary` exists so `cli.py`
never imports the markup half, and the import is inside the function because
`summary_html` imports `summary` for its dataclasses. Both hold here identically.
The name does not: `target_brief.target_brief(run)` stutters at every call site, so
the entry point is `page`, and its docstring says what it is the entry point *for*.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_cli.py
def test_target_brief_writes_the_page_and_prints_its_path(tmp_path, capsys):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    assert cli.main(["target-brief", "--run", str(run.root)]) == 0
    printed = capsys.readouterr().out.strip()
    destination = run.root / "target-brief.html"
    assert printed == str(destination)
    # The path, not the page: markup on a terminal is not a report.
    assert "<!doctype html>" not in printed
    assert destination.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_target_brief_honours_output(tmp_path, capsys):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    destination = tmp_path / "elsewhere" / "brief.html"
    destination.parent.mkdir()
    assert cli.main(["target-brief", "--run", str(run.root), "-o", str(destination)]) == 0
    assert capsys.readouterr().out.strip() == str(destination)
    assert destination.exists()


def test_target_brief_exits_clean_on_a_run_that_stopped_early(tmp_path, capsys):
    """A report, not a gate. A partial run is a page saying so, never a finding --
    the same ruling as claim-utilisation, gate-brief and run-summary."""
    run = build_toy_run(tmp_path, upto="extract")
    assert cli.main(["target-brief", "--run", str(run.root)]) == 0
    assert (run.root / "target-brief.html").exists()


def test_target_brief_exits_clean_when_the_claims_cannot_be_read(tmp_path):
    """Deliberately different from claim-utilisation and gate-brief, which exit 2
    on this. Those two report *numbers* a human acts on, and an empty utilisation
    table is the one reading gate 1 must never be handed. This page reports the
    target's own description with a banner saying the citations are missing, so
    there is no number to be quietly wrong."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    run.claims_dir.chmod(0o000)
    try:
        assert cli.main(["target-brief", "--run", str(run.root)]) == 0
    finally:
        run.claims_dir.chmod(0o755)
    assert 'class="banner"' in (run.root / "target-brief.html").read_text(encoding="utf-8")


def test_target_brief_maps_an_unwritable_destination_to_usage(tmp_path):
    """USAGE, not FINDINGS: the filesystem refusing is not a stage defect, and the
    inversion this closes is the one cli.py's docstring names."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    assert cli.main(["target-brief", "--run", str(run.root), "-o", str(tmp_path / "no" / "x.html")]) == 2


def test_target_brief_rejects_a_missing_run(tmp_path):
    assert cli.main(["target-brief", "--run", str(tmp_path / "nope")]) == 2
```

```python
# tests/unit/test_brief.py
def test_gate_1_points_at_the_target_brief(tmp_path):
    """The report is useless if the human holding gate 1 does not know it exists,
    and gate 1's brief is the one thing that human certainly reads."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    text = brief.gate_brief(run, 1)
    assert "rubrica target-brief" in text
    assert "--run" in text.split("rubrica target-brief")[1]


@pytest.mark.parametrize("gate", [0, 2, 3])
def test_only_gate_1_points_at_the_target_brief(tmp_path, gate):
    """Gate 1 is where the world model is ratified, so it is the only gate at which
    sending the description out for correction is the next action."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    assert "target-brief" not in brief.gate_brief(run, gate)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_cli.py tests/unit/test_brief.py -q -k target_brief`
Expected: FAIL — `invalid choice: 'target-brief'` (SystemExit 2 from argparse), and
`assert "rubrica target-brief" in text`.

- [ ] **Step 3: Add the entry point to `target_brief.py`**

```python
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
```

- [ ] **Step 4: Wire `cli.py`**

Add to `SUBCOMMANDS`, immediately after the `run-summary` entry so the reports sit
together:

```python
    ("target-brief", "render one run's description of the target for its owners"),
```

Add the parser block immediately after `p_summary`'s:

```python
    p_target = parsers["target-brief"]
    p_target.add_argument("--run", required=True)
    # Defaulted for run-summary's reason -- the page's home is the run it
    # describes -- and `-o` matters more here than there: this page is the one
    # that gets attached to an email, so writing it somewhere an operator can
    # find is the normal case rather than the read-only-run exception.
    p_target.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="PATH",
        help="where to write the page (default: <run>/target-brief.html)",
    )
```

Add the handler arm immediately after `run-summary`'s:

```python
        if args.command == "target-brief":
            # A report, the same ruling as claim-utilisation, gate-brief and
            # run-summary: it composes what the run already contains and is never
            # the thing that turns a readable run into exit 1. It goes one step
            # further than run-summary, deliberately: an unreadable 01-claims/
            # exits 2 out of claim-utilisation and gate-brief, because an empty
            # utilisation table is the one reading a human at gate 1 must never be
            # handed -- but this page has no number to be quietly wrong, so it
            # banners the missing citations and still exits 0.
            run = _run_dir(args.run)
            destination = Path(args.output) if args.output else run.root / "target-brief.html"
            # No local catch, for run-summary's reason: an OSError from write_text
            # is the filesystem refusing, and the shared handler below already
            # maps that to USAGE. Catching it here to return FINDINGS would be the
            # 2-as-1 inversion this module's docstring says it closed.
            destination.write_text(target_brief.page(run), encoding="utf-8")
            print(destination)
            return CLEAN
```

Add `target_brief` to the module's `from rubrica import ...` line beside `summary`.

- [ ] **Step 5: Add the gate-1 pointer to `brief.py`**

At the very end of `_gate_1`, immediately before its `return`:

```python
    # The one place a human at gate 1 certainly looks. Gate 1 ratifies the world
    # model, so it is the only gate at which "send this description to the people
    # who own the target and ask whether it is true" is the next action -- and a
    # report nobody knows exists is a report nobody runs.
    lines.append("")
    lines.append(
        f"To ask the target's owners whether this description is right:\n"
        f"  rubrica target-brief --run {run.root}"
    )
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli.py tests/unit/test_brief.py -q`
Expected: PASS. If a gate-1 golden-text assertion elsewhere in `test_brief.py`
breaks on the added lines, that assertion pins the whole brief and should be
narrowed to the block it cares about — the two lines added are a genuine change to
gate 1's reading surface.

- [ ] **Step 7: Update `docs/reference/cli.md`**

`test_docs_accuracy.py` asserts every `cli.SUBCOMMANDS` name has a
`### rubrica <name>` section and that no section names a command `SUBCOMMANDS` does
not define, so this is not optional. Add after the `### rubrica run-summary`
section:

````markdown
### `rubrica target-brief`

Renders one run's *description of the target* as a single self-contained HTML page,
written for the people who own that target and asking them to correct it. Four
ranked asks lead: the files we read, the places our sources disagreed and which
side we took, and what we could not tell from what we read. Beneath them, collapsed,
the description itself — what it can be asked to do, what data it holds, who uses
it — each statement carrying the file it was read from.

Required: `--run RUN`. Optional: `-o PATH` / `--output PATH` — where to write
the page, defaulting to `<run>/target-brief.html`.

**A report, not a gate: it always exits clean on a readable run.** It goes one step
further than `run-summary` there, on purpose. An unreadable `01-claims/` exits 2 out
of `claim-utilisation` and `gate-brief`, because an empty utilisation table is the
one reading a human at gate 1 must never be handed; this page has no number to be
quietly wrong, so it states at the top that it could not read where each statement
came from and renders the description anyway.

Nothing on the page names a stage, a gate, an artifact, a claim id, or rubrica
itself, and two tests fail the suite rather than let one back in. A recipient asked
"does this accurately describe your system?" who is instead reading about
`01-world-model.json` has been handed the wrong question. Prose written by a stage
is *selected and relabelled, never rewritten* — an owner correcting a sentence we
paraphrased would be correcting our paraphrase.

The page carries no JavaScript at all, unlike `run-summary`: it is meant to be sent
out of the project, and an attachment opened behind a corporate proxy or by a reader
with scripts off must still read. It is otherwise self-contained the same way —
inline CSS, no external asset, no network — and unlike `run-summary` it links to no
sibling artifact, so it reads identically wherever it is written or forwarded.

There is no place on it to record an approval, deliberately: it asks whether the
description is true, and whether a ratification is worth collecting is a question
the conversations this report exists for have not answered yet.

```bash
rubrica target-brief --run runs/run-20260806-123005
```
````

Then extend the "The human's own reports" paragraph, which currently names three
reports:

```markdown
them — `gate-brief`, `claim-utilisation`, `run-summary` and `target-brief` — only
compose or report what the run already contains; `set-limit` is the odd one out and
```

- [ ] **Step 8: Update `CLAUDE.md`**

The reports-not-gates paragraph under "The deterministic subcommands" begins
"`claim-utilisation` and `gate-brief` are **reports, not gates**". Add after the
`gate-brief` sentences:

```markdown
  `target-brief` is the one report written for somebody outside the project: it
  renders a run's description of the *target* — not of the run — for the people who
  own that target, asking them to correct it. Four ranked asks lead, the full
  description sits collapsed beneath, and every statement names the file it was read
  from. Two things about it are load-bearing rather than stylistic: prose written by
  a stage is **selected and relabelled, never rewritten**, since an owner correcting
  a sentence we paraphrased would be correcting our paraphrase; and no stage, gate,
  artifact, claim id or mention of rubrica reaches the page, which two tests enforce
  because a recipient reading about `01-world-model.json` has been handed the wrong
  question. It is the one report that exits **0** on an unreadable `01-claims/`
  rather than 2 — it has no number to be quietly wrong, so it says at the top that
  it could not cite its sources and describes the target anyway.
```

- [ ] **Step 9: Run the full gates**

```bash
make test
make check
uv run rubrica check-skills; echo "check-skills exit: $?"
uv run pytest tests/unit/test_docs_accuracy.py -q
```
Expected: all green, `check-skills exit: 0`. `test_docs_accuracy.py` is the one
that fails if step 7 or 8 was skipped, and that failure is the guard working:
update the document, never the assertion.

- [ ] **Step 10: Exercise it end to end on a real run**

```bash
uv run rubrica target-brief --run runs/run-20260826-090456 -o "$CLAUDE_JOB_DIR/tmp/parsec-brief.html"; echo "exit: $?"
uv run rubrica gate-brief --run runs/run-20260826-090456 --gate 1 | tail -4
```
Expected: `exit: 0`, a path printed, and the gate-1 brief ending with the pointer.

- [ ] **Step 11: Commit**

```bash
make check
git add src/rubrica/target_brief.py src/rubrica/cli.py src/rubrica/brief.py \
        docs/reference/cli.md CLAUDE.md tests/unit/test_cli.py tests/unit/test_brief.py
git commit -S -s -F - <<'MSG'
feat: Add `rubrica target-brief`, and point gate 1 at it

The subcommand: `--run` required, `-o` defaulting to <run>/target-brief.html,
mirroring run-summary's parser and its no-local-catch handler so an unwritable
destination stays USAGE rather than becoming a fabricated stage defect.

One deliberate divergence from the other three reports. claim-utilisation and
gate-brief exit 2 on an unreadable 01-claims/, and that ruling stands: an empty
utilisation table is the one reading a human at gate 1 must never be handed. This
page has no number to be quietly wrong, so it banners the missing citations and
exits 0 -- a description of the target with its sources visibly absent is still
worth sending; a description with its sources silently absent is not, which is why
the banner and not an empty index.

gate-brief --gate 1 now ends by naming the command. Gate 1 ratifies the world
model, so it is the only gate at which sending the description out for correction
is the next action, and a report nobody knows exists is a report nobody runs. The
other three gates deliberately say nothing about it.

cli.md and CLAUDE.md updated because test_docs_accuracy.py requires it, and both
record the two load-bearing properties rather than just the flags: prose is
selected and relabelled and never rewritten, since an owner correcting a sentence
we paraphrased would be correcting our paraphrase; and no stage, gate, artifact,
claim id or mention of this project reaches the page.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
```

---

## Self-review

Run after the plan is written, before execution. Findings recorded here rather than
silently fixed, because a plan whose review left no trace cannot be re-read.

**1. Spec coverage** — every section of
[`../specs/2026-08-27-target-brief-design.md`](../specs/2026-08-27-target-brief-design.md)
mapped to a task:

| Spec | Task |
|---|---|
| §1 The problem | Task 7's page voice; Task 8's cli.md prose |
| §2 Field selection (selected / dropped / prose relabelled not rewritten) | Tasks 3–6; the rule is a Global Constraint |
| §3.1 derivation badge dropped | Task 2, with an explicit "do not reintroduce" |
| §3.2 source count, kinds, disputed | Task 2 |
| §3.3 contradictions are the payload | Task 4 |
| §3.4 real runs omit `claims` | Task 6 (outcome provenance from the parent capability) |
| §4.1.A what we read | Task 3 |
| §4.1.B/C disagreements and the side taken | Task 4 |
| §4.1.D open questions | Task 5 |
| §4.2 tier 2, collapsed | Tasks 6 and 7 |
| §4.3 deliberate absences (sign-off, gap `why_it_matters`) | Task 5 (`why_it_matters`), Task 7 (`_reply`, and the test forbidding the words) |
| §5 Where it lives | Task 8 |
| §6 Degradation, quote-optional | Task 1 (marker), Task 7 (banner, markers rendered) |
| §7 Testing | every task's Steps 1–2, plus Task 7's two premise tests |
| §8 Docs to update | Task 8 Steps 7–8 |
| §9 Deferred | not implemented, by definition — blast-radius ranking is named as deferred in Task 4 |

**2. Placeholder scan** — no `TBD`, no "add appropriate error handling", no "similar
to Task N"; every code step carries the code. Two forward references are stated
where they occur rather than left implicit: Task 5's `_text` is back-applied to
Task 4's `Dispute` construction, and Task 7 adds `headline` to a module Task 1
created.

**Finding 1, fixed in Task 7.** `_operations` headed each entry on `op.handle`,
and both toy capabilities carry `binding.tool == "query_tickets"` — so the page
printed the same word twice and the reader could not tell which operation was
which. The entry now heads on `op.sentence` (the `operation` string,
`query_tickets.find_tickets`), showing the handle beneath only when it differs.
Caught by checking which dataclass fields the renderer never reads: `sentence` was
dangling, and a dangling field is usually the renderer having picked the wrong one.

**Finding 2, NOT fixed — a spec question, raised rather than decided.** The gap
`$def` carries `suggested_input`, which neither the spec nor this plan mentions,
and it is populated on 18 of 18, 17 of 19 and 7 of 12 gaps in the three real runs.
It is also, read plainly, the most actionable sentence available to this document:
it turns "we could not tell X" into "and here is what would settle it." Group D
currently renders only `subject` and `unknown`, so it is dropped.

It was left dropped because including it collides with two rules at once, and the
collision is real rather than a technicality. The prose is written in rubrica's
vocabulary — *"A definitive code-level claim from azure-costs-py that either adds
or removes `subscriptions_queried` from the return dict"* — so rendering it
verbatim breaks the premise that no claim, artifact or stage vocabulary reaches
the page, while paraphrasing it into the owner's words breaks the rule that stage
prose is **selected and relabelled, never rewritten**. There is no third option
available to code: the only way to get an owner-facing "what would settle this"
is for the pass that writes the gap to write one, which is a skill change.

**Recommendation, for the spec owner and not for an implementer:** leave Group D
as planned, and treat "`rb-reconcile-gaps` should write `suggested_input` in the
target's vocabulary rather than rubrica's" as a separate question. Do not have an
implementer add the field to Task 5 on their own judgment.

**3. Type consistency** — checked across tasks: `Provenance.single_source` is a
property everywhere it is read (Tasks 2, 7); `source_index` returns
`dict[str, SourceRef] | Marker` and every consumer narrows with
`isinstance(index, dict)` before use (Tasks 2, 6); every builder returns
`list[X] | Marker` and every renderer branches on `isinstance(..., Marker)` first
(Task 7); `_strings` is named in Task 1's import block because Tasks 2–6 use it.

## Execution

**Plan complete and saved to `docs/superpowers/plans/2026-08-27-target-brief.md`.**

Two things worth knowing before it is executed:

- **Task 7 Step 6 cannot be automated and is not optional.** The predicate tests
  cannot tell whether the page reads as a description of somebody's system or as a
  database dump with polite headings. Somebody has to read one end to end.
- **Task 8 Step 5 changes gate 1's reading surface.** If a golden-text assertion in
  `test_brief.py` breaks there, narrow the assertion — do not drop the pointer.
