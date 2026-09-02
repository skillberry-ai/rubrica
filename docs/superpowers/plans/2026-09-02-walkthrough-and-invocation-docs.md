# Walkthrough and Invocation Documents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `docs/getting-started.md` a single readable walkthrough that runs
Rubrica from install to `emit`, and turn the hand-dispatch runbook into
`docs/guides/invoking-rubrica.md`, the reference for both invocation types.

**Architecture:** Two documents split on sequence versus mechanics. The
walkthrough owns the order and never explains an option; the invocation guide
owns every flag, environment variable and measurement and never implies an
order. One code fix precedes both, because the walkthrough's `propose` loop
cannot be written until `scripts/dispatch-stage.sh` accepts a batch id.

**Tech Stack:** Markdown; `bash` + `jq` for the harness script; `pytest` for the
harness test; `ruff` (line length 100, `docs/` excluded from formatting).

**Spec:** [`docs/superpowers/specs/2026-09-02-walkthrough-and-invocation-docs-design.md`](../specs/2026-09-02-walkthrough-and-invocation-docs-design.md)

## Global Constraints

- **Every commit signed and DCO'd: `git commit -S -s`.** Both flags. If signing
  fails, stop and report it; never fall back to unsigned.
- Attribution trailer is `Assisted-By: Claude (Anthropic AI)
  <noreply@anthropic.com>`. Never `Co-Authored-By` or `Made-with`.
- The three gates: `make test` green, `make check` clean, `uv run rubrica
  check-skills` exiting 0.
- **No hand-typed test count** in any user-facing document. **No heading that
  counts something that grows** — `_COUNTED_HEADING` in
  `tests/unit/test_docs_accuracy.py` fires on a number (digits, or `one`
  through `twenty`) followed within one word by `stages`, `skills`,
  `subcommands` or `gates`. `## The three human gates` fails; `## The human
  gates` passes. `### 4. Triage rules …` is safe — the numeral is followed by
  `.`, not whitespace.
- **Only `docs/README.md` may cite `docs/superpowers/`.** No other user-facing
  document may link the recorded-history tree.
- **Never edit anything under `docs/superpowers/`** except the two files this
  plan creates or has created. A record of what happened is falsified, not
  corrected, by a later edit.
- British spellings are this repository's convention: `synthesise`,
  `utilisation`, `normalise`. cSpell warnings on these are noise.
- Comment density in `src/` and `scripts/` is high and deliberate — comments
  explain *why*, usually citing a measurement. Match it; do not strip.
- `docs/` is in ruff's `extend-exclude`, so its code blocks are not reformatted.
  `README.md` and `CLAUDE.md` are **not** excluded — run `make check` after
  editing either.

## File Structure

| File | Responsibility |
|---|---|
| `scripts/dispatch-stage.sh` | Gains a `propose` arm in the slice-id `case`. Two header comments get the new guide path and renumbered sections. |
| `tests/unit/test_dispatch_harness.py` | Gains one test asserting the composed prompt carries `Your batch_id`, read from the prompt file rather than grepped from the script. |
| `docs/guides/invoking-rubrica.md` | **Renamed from** `running-a-stage-by-hand.md`. The reference for both invocation types: shared setup, `uv run rubrica`, `dispatch-stage.sh`, what a dispatch carries, isolation, one-stage exercising, verification, the live suite, re-seeding. |
| `docs/getting-started.md` | Rewritten. The linear walkthrough, install to `emit`, plus the one-step orchestrator path. |
| `docs/design/limitations.md` | Gains the id-naming entry under `## Before you file a bug against the check layers or the CLI`. |
| `docs/README.md` | Both index lines rewritten — the questions each document answers have changed. |
| `README.md`, `CLAUDE.md`, `docs/concepts/artifact-contract.md`, `docs/reference/artifacts.md` | Rename-sweep targets; `artifacts.md` also carries a section-number citation. |
| `tests/unit/test_refusals_live.py`, `tests/unit/test_toy_fixture.py` | Rename-sweep targets in a docstring, a skip message and a comment. |

**Task order is load-bearing.** Task 1 first, because the walkthrough's
`propose` loop documents behaviour that does not exist until it lands. Task 2
(pure path substitution) before Task 3 (restructure and renumber), because
renumbering citations against sections that have not moved yet points them at
nothing.

---

### Task 1: `dispatch-stage.sh` accepts a `propose` batch id

**Files:**
- Modify: `scripts/dispatch-stage.sh:85-91`
- Test: `tests/unit/test_dispatch_harness.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `./scripts/dispatch-stage.sh propose "$RUN" <batch-id>` exits 0 and
  composes a prompt whose address line is `Your batch_id:     <batch-id>`.
  Task 5's round-loop block depends on this.

**Why:** `rb-propose` is a fan-out, one member per batch, each reading its own
`hole_refs` out of `02-batches/round-N.json`. Today the `case` has no `propose`
arm, so a batch id hits the fallthrough and exits 2 with "propose is a single
dispatch over everything; it takes no slice id" — which is false — while
omitting the id dispatches a member with no address at all.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_dispatch_harness.py`, immediately after
`test_dispatch_hands_a_rule_member_its_slice_id` (around line 251):

```python
def test_dispatch_hands_a_propose_member_its_batch_id(tmp_path):
    """propose is a fan-out over the round's batch partition, so its dispatch
    case must hand the member its own batch_id -- the key it resolves against
    `02-batches/round-N.json` to find its own hole_refs.

    Asserted against the *composed prompt*, not against the script's source.
    A `"propose)" in script` grep passes on a rule that is present and
    unreachable, which is the weakness the script's own print-settings comment
    names; reading the prompt file proves the arm is reached. Whitespace is
    split rather than pinned, because the arms are column-aligned and a
    realignment is not a behaviour change.
    """
    run = tmp_path / "run"
    run.mkdir()
    _, _, prompt = _paths(_dispatch(tmp_path, "propose", str(run), "b01", run=run))
    lines = [ln for ln in Path(prompt).read_text().splitlines() if "batch_id" in ln]
    assert lines, "the composed prompt carries no batch_id line"
    assert lines[0].split() == ["Your", "batch_id:", "b01"]
```

- [ ] **Step 2: Run it and watch it fail for the right reason**

```bash
uv run pytest tests/unit/test_dispatch_harness.py::test_dispatch_hands_a_propose_member_its_batch_id -q
```

Expected: FAIL. `_paths` asserts `returncode == 0` first, so the failure
message carries the script's own stderr — `propose is a single dispatch over
everything; it takes no slice id`. **If it fails any other way, stop**: the
test is not measuring what it claims.

- [ ] **Step 3: Add the arm**

In `scripts/dispatch-stage.sh`, in the `case "$STAGE"` block at lines 85-91,
add the `propose` arm between `reconcile-contradict` and `instantiate|challenge`
so the list reads in pipeline order:

```sh
    extract)               SLICE_LINE="Your artifact_id:  $SLICE" ;;
    reconcile-contradict)  SLICE_LINE="Your subject_id:   $SLICE" ;;
    propose)               SLICE_LINE="Your batch_id:     $SLICE" ;;
    instantiate|challenge) SLICE_LINE="Your scenario_id:  $SLICE" ;;
    triage-rule)           SLICE_LINE="Your slice_id:     $SLICE" ;;
```

Column alignment matches the existing arms: the value starts at the same
column in all five.

- [ ] **Step 4: Run the test and the whole harness module**

```bash
uv run pytest tests/unit/test_dispatch_harness.py::test_dispatch_hands_a_propose_member_its_batch_id -q
uv run pytest tests/unit/test_dispatch_harness.py -q
```

Expected: both PASS. The second matters because the module's `settings`
fixture dispatches `propose` with **no** slice id; if that regressed, every
permissions test in the file fails.

- [ ] **Step 5: Confirm the arm is reachable by hand**

```bash
mkdir -p /tmp/rb-arm/run
RUBRICA_PRINT_SETTINGS=1 RUBRICA_LAB=/tmp/rb-arm/lab \
  ./scripts/dispatch-stage.sh propose /tmp/rb-arm/run b01 | tail -1 | xargs grep -n batch_id
```

Expected: one line reading `Your batch_id:     b01`.

- [ ] **Step 6: Commit**

```bash
git add scripts/dispatch-stage.sh tests/unit/test_dispatch_harness.py
git commit -S -s -m "fix: Let dispatch-stage.sh hand a propose member its batch id

rb-propose is a fan-out, one member per batch, each reading its own hole_refs
out of 02-batches/round-N.json. The slice-id case had no propose arm, so a
batch id hit the fallthrough and exited 2 claiming propose takes no slice id --
which is false -- while omitting it dispatched a member with no address at all.

The test reads the composed prompt rather than grepping the script, because a
source grep passes on a rule that is present and unreachable.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 2: Rename the guide, paths only

**Files:**
- Rename: `docs/guides/running-a-stage-by-hand.md` → `docs/guides/invoking-rubrica.md`
- Modify: `docs/README.md:37`, `README.md:84,123`, `CLAUDE.md:406`,
  `docs/concepts/artifact-contract.md:48`, `docs/reference/artifacts.md:228`,
  `docs/design/limitations.md:115`, `scripts/dispatch-stage.sh:6,503`,
  `tests/unit/test_refusals_live.py:5,30`, `tests/unit/test_toy_fixture.py:316`

**Interfaces:**
- Consumes: nothing.
- Produces: the path `docs/guides/invoking-rubrica.md`, which Tasks 3, 5 and 6
  cite.

**Scope discipline:** this task changes **paths only**. Section numbers cited
across files (`§4`, `§7`, `§2`) still refer to the old structure and stay
untouched here — Task 3 moves the sections and renumbers the citations in the
same commit that makes them true. `docs/getting-started.md` has four references
and is deliberately **not** touched: Task 5 rewrites the file wholesale.

- [ ] **Step 1: Move the file**

```bash
git mv docs/guides/running-a-stage-by-hand.md docs/guides/invoking-rubrica.md
```

- [ ] **Step 2: Substitute the path everywhere except getting-started.md**

```bash
grep -rln "running-a-stage-by-hand" \
    README.md CLAUDE.md docs scripts tests \
  | grep -v "^docs/superpowers/" \
  | grep -v "^docs/getting-started.md$" \
  | xargs sed -i 's#running-a-stage-by-hand#invoking-rubrica#g'
```

`docs/superpowers/` is excluded because it is recorded history — those files
described a real path on their own date and must not be edited.

- [ ] **Step 3: Verify the sweep in both directions**

```bash
echo "--- stale references outside recorded history (expect only getting-started.md):"
grep -rn "running-a-stage-by-hand" . --exclude-dir=.git --exclude-dir=docs/superpowers \
    --exclude-dir=runs --exclude-dir=.venv || echo "(none)"
echo "--- new path resolves:"
test -f docs/guides/invoking-rubrica.md && echo OK
echo "--- every markdown link to it points at a real file:"
grep -rn "invoking-rubrica.md" --include=*.md . --exclude-dir=.git \
    --exclude-dir=docs/superpowers | wc -l
```

Expected: the only remaining old-path hits are the four in
`docs/getting-started.md`. If any other file still names it, the `sed` missed
it — a one-directional sweep is exactly how a stale pointer survives.

- [ ] **Step 4: Run the gates**

```bash
make test && make check && uv run rubrica check-skills
```

Expected: all green. `tests/unit/test_refusals_live.py` and
`test_toy_fixture.py` carry the path in a docstring, a skip message and a
comment; nothing asserts on it, so this is a no-op for behaviour.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -S -s -m "docs: Rename running-a-stage-by-hand.md to invoking-rubrica.md

The document is the reference for both invocation types -- uv run rubrica and
scripts/dispatch-stage.sh -- and its name promised a runbook for one stage.
Paths only in this commit; the sections it cites move in the next one.

docs/superpowers/ is untouched: it is recorded history, and a record is
falsified rather than corrected by a later edit.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 3: Restructure `invoking-rubrica.md` around the two invocation types

**Files:**
- Modify: `docs/guides/invoking-rubrica.md` (whole-file restructure)
- Modify: `docs/reference/artifacts.md:228` (`§4` → `§8`)
- Modify: `scripts/dispatch-stage.sh:6` (`§7` → `§6`), `:503` (`§2` → `§7`)

**Interfaces:**
- Consumes: the path from Task 2.
- Produces: a nine-section document whose numbering Tasks 5 and 6 cite, and
  whose §4 is the `dispatch-stage.sh` reference the walkthrough points at for
  every flag.

**Nothing is deleted.** Every measurement, ruling and "this was tried and
broke" paragraph in the current file survives. The work is regrouping, plus the
`uv run rubrica` half that does not exist yet.

- [ ] **Step 1: Read the current file end to end**

```bash
wc -l docs/guides/invoking-rubrica.md
sed -n 1,120p docs/guides/invoking-rubrica.md
```

Do not restructure from the outline alone. The paragraphs carry measurements
with dates and version numbers (`2.1.227`, `2.1.231`, `bubblewrap 0.9.0`, issue
#18, `2026-08-13`) that must move verbatim.

- [ ] **Step 2: Write the new section order**

Target structure, from the spec's table:

| § | Content | Where it comes from |
|---|---|---|
| 1 | The two invocation types; a table of stage → code or prompt → invocation; a pointer to `docs/getting-started.md` for the order | new |
| 2 | Setup they share: venv on `PATH` vs. the `uv run` prefix; the exit-code contract and how to route each code; the four `RUBRICA_*` overrides | new, plus the `PATH` measurement from old §7 |
| 3 | `uv run rubrica …`: `--run`/`--stage`/`--round` conventions, stdout vs. findings, pointer to `docs/reference/cli.md` | new |
| 4 | `scripts/dispatch-stage.sh …`: prerequisites, positional arguments, the slice-id table, the environment table, print modes, transcripts, `audit-reads.sh`, the cost line | old §7, regrouped and completed from the script's header |
| 5 | What a dispatch carries: the three things, the slice id as an address, the two permitted appends | old §§1–2 |
| 6 | Isolation: why it is not tidiness, the three mechanisms, the two settings scopes, the sandbox probe, never deny a path `check-refs` reads | old §7, kept whole |
| 7 | Exercising one stage against a checkpoint: the prompt template, the `upto=` table, `toy-run-to.py` | old §§2–3 |
| 8 | Verification, reading a failure, the live exercise suite | old §§4–6 |
| 9 | Re-dispatching a `re-seed` | old §8 |

- [ ] **Step 3: Write §1's stage table**

The table must partition `paths.STAGES`. Generate the ground truth rather than
retyping it:

```bash
uv run python -c "
from rubrica import paths
code = {'survey','triage-slices','triage-seal','intake','synthesise-interfaces',
        'reconcile-seal','propose-batches','propose-seal','score-seal','smoke'}
for s in paths.STAGES:
    print(f'{s:24} {\"code\" if s in code else \"prompt\"}')
"
```

Every `prompt` row is invoked with `./scripts/dispatch-stage.sh <stage> \$RUN
[slice-id]`; every `code` row with `uv run rubrica <subcommand> --run \$RUN`.

- [ ] **Step 4: Write §4's slice-id table, including the `propose` row Task 1 added**

```markdown
| Stage | Address line the prompt carries | Where the ids come from |
|---|---|---|
| `extract` | `Your artifact_id:` | `jq -r '.inputs[].artifact_id' "$RUN"/manifest.json` |
| `triage-rule` | `Your slice_id:` | `jq -r '.slices[].id' "$RUN"/00-slices.json` |
| `reconcile-contradict` | `Your subject_id:` | `jq -r '.subjects[].id' "$RUN"/01-subjects.json` |
| `propose` | `Your batch_id:` | `jq -r '.batches[].id' "$RUN"/02-batches/round-N.json` |
| `instantiate`, `challenge` | `Your scenario_id:` | `jq -r '.scenarios[] \| select(.status=="active") \| .id' "$RUN"/02-scenarios.json` |
```

**State the asymmetry in prose beneath it**, because it is the trap: the address
line is always qualified, while the field is bare `id` everywhere except the
manifest. `jq -r '.subjects[].subject_id'` prints one `null` per subject rather
than failing. Point at the `limitations.md` entry Task 4 adds for why the
schemas are not changing.

- [ ] **Step 5: Write §2's exit-code contract**

```markdown
| Code | Meaning | What to do |
|---|---|---|
| `0` | clean | continue |
| `1` | findings, one per line on stdout | a repairable stage defect: worth one re-dispatch, carrying the gate's stdout verbatim |
| `2` | usage error, or an unreadable/misconfigured run | retrying cannot help; fix the run or the invocation |
```

Note that `dispatch-stage.sh` exits 2 for a missing `claude` or `jq` for this
reason, and that a stage defect must never surface as 2.

- [ ] **Step 6: Renumber every internal cross-reference**

The old file carries fifteen internal `§` references. Find them and rewrite
each to the new numbering:

```bash
grep -n "§§\?[0-9]" docs/guides/invoking-rubrica.md
```

Old → new: §1 → §5 · §2 → §7 (prompt template) or §5 (the rule) · §3 → §7 ·
§4 → §8 · §5 → §8 · §6 → §8 · §7 → §4 (mechanics) or §6 (isolation) · §8 → §9.

**Two hits are not internal references and must not be renumbered:**
`rb-orchestrate` step 227 and step 505 are that skill's own line numbers.

- [ ] **Step 7: Fix the three external citations that name a section**

```bash
# docs/reference/artifacts.md:228 -- "§4 has the command" is now §8
sed -i '228s/§4 has the command/§8 has the command/' docs/reference/artifacts.md
grep -n "§8 has the command" docs/reference/artifacts.md
```

Then in `scripts/dispatch-stage.sh`, by hand:

- line 6: `§7 there covers why an isolated instance is worth the trouble` → `§6`
- line 503: `verbatim from docs/guides/invoking-rubrica.md §2` → `§7`

```bash
grep -n "invoking-rubrica" scripts/dispatch-stage.sh
```

Expected: line 6 cites §6, line 503 cites §7.

- [ ] **Step 8: Check the policy predicates and the gates**

```bash
uv run pytest tests/unit/test_docs_accuracy.py -q
make test && make check && uv run rubrica check-skills
```

Then confirm no heading counts a growing set:

```bash
uv run python -c "
import re, pathlib
N=(r'(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|'
   r'thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)')
G=r'(?:stages?|skills?|subcommands?|gates?)'
pat=re.compile(rf'^#+[ \t]+[^\n]*\b{N}[ \t]+(?:\w+[ \t]+)?{G}\b', re.I|re.M)
t=pathlib.Path('docs/guides/invoking-rubrica.md').read_text()
out,f=[],False
for ln in t.splitlines():
    if ln.lstrip().startswith('\`\`\`'): f=not f; continue
    out.append('' if f else ln)
print('hits:', pat.findall('\n'.join(out)) or '(none)')
"
```

- [ ] **Step 9: Commit**

```bash
git add docs/guides/invoking-rubrica.md docs/reference/artifacts.md scripts/dispatch-stage.sh
git commit -S -s -m "docs: Restructure invoking-rubrica.md around the two invocation types

The document covered dispatch-stage.sh and nothing of the uv run rubrica half,
and its material was ordered as a runbook rather than as a reference. It now
opens with the two types and the setup they share, then documents each, then
keeps the one-stage runbook it started as.

Nothing was dropped: every measurement, ruling and superseded-attempt paragraph
survives. Internal section references are renumbered, along with the three
external citations that named a section -- artifacts.md's record-stage pointer
and dispatch-stage.sh's two header comments.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 4: Record the id-naming ruling in `limitations.md`

**Files:**
- Modify: `docs/design/limitations.md`, under `## Before you file a bug against
  the check layers or the CLI` (section begins at line 2258)

**Interfaces:**
- Consumes: nothing.
- Produces: the entry §4 of the invocation guide and the walkthrough both point
  at when they state the label-versus-field asymmetry.

**Why here:** that section holds entries about field-name and exit-code
surfaces — `refs.py never checks a machine: invariant's field names`, `Two
content-derived failures exit 2 rather than 1`. `## Deliberately out of scope`
is a bullet list of unbuilt features, which this is not.

- [ ] **Step 1: Read two neighbouring entries for the house form**

```bash
sed -n 2269,2296p docs/design/limitations.md
```

The form is: `### <the finding stated as a fact>`, the analysis, then the
ruling, usually opening `Parked` and saying what would actually close it.

- [ ] **Step 2: Add the entry**

Insert after the last entry of that section, before `## Before you rely on a
test or a fixture` (line 2719). Heading — deliberately carrying no number, so
`_COUNTED_HEADING` cannot fire:

```markdown
### An id field is bare where a thing is defined and qualified where it is referenced, and the dispatch address line is always qualified

A fan-out member is addressed by a qualified name — `Your subject_id:`,
`Your batch_id:`, `Your slice_id:`, `Your scenario_id:`, `Your artifact_id:` —
and four of those five read a field named plain `id`:

| Kind | Definition site | Referenced from another artifact as |
|---|---|---|
| slice | `.slices[].id` | `slice_id` (`dispositions-part`) |
| subject | `.subjects[].id` | `subject_id` (`contradictions-part`) |
| batch | `.batches[].id` | `batch_id` (`scenarios-part`) |
| scenario | `.scenarios[].id` | `scenario_id` (`expected`, `score-part`, `suite-expected`, `report`, `verdict`) |
| candidate | `.candidates[].candidate_id` | `candidate_id` (`adoptions`, `dispositions-part`, `triage`) |
| artifact | `.inputs[].artifact_id` | `artifact_id` (`claims`, `inputs-seen`, `world-model`) |

The convention is bare `id` at the definition site and `<thing>_id` wherever
another artifact points at it, which carries the information that you are
holding a foreign key. The catalogue and the manifest qualify at their own
definition sites too, and they are the two artifacts that mint a run from
outside the system.

The cost lands on anyone writing a loop over a fan-out. `jq -r
'.subjects[].subject_id'` does not fail — it prints one `null` per subject, so a
dispatch loop addresses every member as `null` and the mistake surfaces as a
stage that cannot find its slice.

**Both normalisations were priced and both declined.** Bare `id` everywhere
makes it worse: `extract` is the only fan-out whose address line and field
already agree, and it agrees *because* the manifest qualifies, so normalising
down puts all five loops in disagreement and leaves `artifact_id` meaning
something else in three other schemas. Qualifying the four definition sites is
the direction that would remove it, and it costs four breaking schema versions
cascading into `validate.py`'s mapping, roughly 109 sites in `src/` and 122 in
`tests/`, 36 in `tests/toy.py` — the golden-fixture builder, which is the model
answer a skill imitates — and edits to skill `Output` prose that models imitate,
`rb-reconcile-subjects/SKILL.md:67` among them. No behaviour changes either way.

Parked, and the ruling is that the documents carry it instead of the schemas:
[`docs/getting-started.md`](../getting-started.md) and
[`docs/guides/invoking-rubrica.md`](../guides/invoking-rubrica.md) each state the
address-line-to-`jq`-path mapping in a table. What would close it properly is
neither rename but a command that answers "what are this stage's slice ids",
so no document names a field at all — which is a CLI addition rather than a
schema one, and nobody has needed it enough to specify it.
```

- [ ] **Step 3: Verify placement and the predicates**

```bash
grep -n "^## \|^### An id field" docs/design/limitations.md | sed -n '/2258/,$p' | head
uv run pytest tests/unit/test_docs_accuracy.py -q
```

Expected: the new `###` sits inside the check-layers/CLI section, before
`## Before you rely on a test or a fixture`; the test module passes.

- [ ] **Step 4: Commit**

```bash
git add docs/design/limitations.md
git commit -S -s -m "docs: Record the id-naming asymmetry and why neither rename happened

Writing the walkthrough's fan-out loops surfaced it: the dispatch address line
is always qualified while the field is bare id everywhere except the manifest,
and jq prints null rather than failing when the two are confused.

There was no entry, so the next reader re-derives the analysis. This one states
the convention, names the catalogue and the manifest as its outliers, prices
both normalisation directions, and records that the documents carry the mapping
instead of the schemas.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 5: Rewrite `docs/getting-started.md` as the walkthrough

**Files:**
- Modify: `docs/getting-started.md` (whole-file rewrite)

**Interfaces:**
- Consumes: `propose` batch ids from Task 1; the guide path and its §
  numbering from Tasks 2–3; the `limitations.md` anchor from Task 4.
- Produces: the walkthrough `docs/README.md` indexes in Task 6.

**Shape:** every stage block has the same four parts in the same order — one or
two sentences on what the stage does, the command, the gate that checks it, and
where a model was dispatched the `record-stage` that records it. **No block
explains a flag**; that is §§2–4 of the guide and `docs/reference/cli.md`.

- [ ] **Step 1: Drop the executed-commands claim**

Delete the opening sentence "Every command below was run against this
repository before this page was committed" and the paragraph hedging §§3–5.
A page that runs the whole pipeline cannot hold that claim, and per-block
markers would not make it true. **Nothing replaces it** — no provenance marks.

- [ ] **Step 2: Write the framing — the two ways, and no third**

Two ways, both CLI, both covered here: step by step, or one step through the
orchestrator. **Name no future interface.** There is no plugin; a document that
describes an interface nobody can use sends readers looking for something that
is not there.

- [ ] **Step 3: Write the install and survey blocks**

```bash
make setup
export PATH="$PWD/.venv/bin:$PATH"   # or prefix every command with `uv run`
```

```bash
export RUNS=runs
export RUN=$(rubrica survey --corpus tests/fixtures/corpus-toy --runs-dir "$RUNS" \
  --target-name toy --target-interface mcp --objective breadth)
echo "$RUN"
rubrica validate --run "$RUN" --stage survey
```

Say why `$RUN` is captured from stdout rather than found afterwards: `survey`
prints the run directory and nothing else, and `ls -d "$RUNS"/run-*` stops being
unambiguous the moment a second run exists.

- [ ] **Step 4: Write the triage family, gate 0, and intake**

```bash
rubrica triage-slices --run "$RUN"
rubrica validate --run "$RUN" --stage triage-slices
```

```bash
./scripts/dispatch-stage.sh triage-objective "$RUN"
rubrica validate --run "$RUN" --stage triage-objective
```

```bash
for slice_id in $(jq -r '.slices[].id' "$RUN"/00-slices.json); do
  ./scripts/dispatch-stage.sh triage-rule "$RUN" "$slice_id"
done
rubrica validate --run "$RUN" --stage triage-rule
```

```bash
./scripts/dispatch-stage.sh triage-audit "$RUN"
rubrica validate --run "$RUN" --stage triage-audit
rubrica check-refs --run "$RUN"
```

```bash
rubrica triage-seal --run "$RUN"
rubrica validate --run "$RUN" --stage triage-seal
rubrica check-refs --run "$RUN"
```

```bash
rubrica gate-brief --run "$RUN" --gate 0
```

Gate 0 is different in kind: nothing downstream of `intake` reads the corpus
again, so a declined candidate is gone as completely as if the corpus never
held it. Then:

```bash
rubrica intake --run "$RUN"
rubrica validate --run "$RUN" --stage intake
```

```bash
# record-stage merges into manifest.json, which did not exist until now, so the
# three dispatched triage passes are recorded here rather than where they ran
for stage in triage-objective triage-rule triage-audit; do
  rubrica record-stage --run "$RUN" --stage "$stage" \
    --model sonnet --effort medium \
    --skill src/rubrica/skills/rb-$stage/SKILL.md
done
```

`triage-slices` and `triage-seal` are code, have no skill file, and take no
entry at all — their absence from `manifest.stages` is not a finding.

- [ ] **Step 5: Write the extract fan-out**

```bash
for artifact_id in $(jq -r '.inputs[].artifact_id' "$RUN"/manifest.json); do
  ./scripts/dispatch-stage.sh extract "$RUN" "$artifact_id"
done
rubrica validate --run "$RUN" --stage extract
rubrica record-stage --run "$RUN" --stage extract \
  --model sonnet --effort medium --skill src/rubrica/skills/rb-extract/SKILL.md
```

Note that `extract` is the one loop reading a qualified field name, and link
the `limitations.md` entry from Task 4.

- [ ] **Step 6: Write the reconcile band as eight separate blocks**

**Do not compress these into a loop.** Each pass has its own
`validate --stage`, its own `check-refs`, and its own `record-stage` carrying
that pass's model and effort — which is the reason the band is eight stages
rather than one skill branching on a slice id. A loop would either drop those
lines or bury them in a body that no longer reads as a sequence.

`reconcile-subjects` (barrier):

```bash
./scripts/dispatch-stage.sh reconcile-subjects "$RUN"
rubrica validate --run "$RUN" --stage reconcile-subjects
rubrica check-refs --run "$RUN"
rubrica record-stage --run "$RUN" --stage reconcile-subjects \
  --model sonnet --effort medium \
  --skill src/rubrica/skills/rb-reconcile-subjects/SKILL.md
```

`reconcile-contradict` (fan-out over the cover just written):

```bash
for subject_id in $(jq -r '.subjects[].id' "$RUN"/01-subjects.json); do
  ./scripts/dispatch-stage.sh reconcile-contradict "$RUN" "$subject_id"
done
rubrica validate --run "$RUN" --stage reconcile-contradict
rubrica check-refs --run "$RUN"   # only meaningful once every member has landed
rubrica record-stage --run "$RUN" --stage reconcile-contradict \
  --model sonnet --effort medium \
  --skill src/rubrica/skills/rb-reconcile-contradict/SKILL.md
```

Say why the `check-refs` comment is there: `refs.check_contradiction_parts`
reports every missing slice from the moment the directory exists, so
mid-fan-out most are missing by construction.

Then one block each, identical in shape to `reconcile-subjects`, for
`reconcile-capabilities`, `reconcile-outcomes`, `reconcile-entities`,
`reconcile-goals`, `reconcile-gaps` and `reconcile-services` — in that order,
which is `paths.STAGES` order. Each block: dispatch, `validate --stage <it>`,
`check-refs`, `record-stage` with `--skill
src/rubrica/skills/rb-<it>/SKILL.md`.

- [ ] **Step 7: Write the interface derivation, the seal, and gate 1**

```bash
rubrica synthesise-interfaces --run "$RUN"
rubrica validate --run "$RUN" --stage synthesise-interfaces
rubrica check-refs --run "$RUN"
```

```bash
rubrica reconcile-seal --run "$RUN"
rubrica validate --run "$RUN" --stage reconcile-seal
rubrica check-refs --run "$RUN"
rubrica claim-utilisation --run "$RUN"
```

```bash
rubrica gate-brief --run "$RUN" --gate 1
rubrica target-brief --run "$RUN"   # the page written for the target's owners
```

Both `claim-utilisation` and `gate-brief` are reports, not gates: each exits
clean on a readable run.

- [ ] **Step 8: Write the round loop, with `propose-seal` twice**

`propose-seal` runs **twice per round** and takes no `--round`: once after
`propose` so `score` has a document to read, and again after `score` so
`instantiate` sees the statuses. It never reads its own output, so the second
run cannot disagree with the first.

```bash
ROUND=1

rubrica propose-batches --run "$RUN" --round "$ROUND"
rubrica validate --run "$RUN" --stage propose-batches

for batch_id in $(jq -r '.batches[].id' "$RUN"/02-batches/round-$ROUND.json); do
  ./scripts/dispatch-stage.sh propose "$RUN" "$batch_id"
done
rubrica validate --run "$RUN" --stage propose
rubrica record-stage --run "$RUN" --stage propose \
  --model sonnet --effort medium --skill src/rubrica/skills/rb-propose/SKILL.md

rubrica propose-seal --run "$RUN"          # so score has a document to read
rubrica validate --run "$RUN" --stage propose-seal

./scripts/dispatch-stage.sh score "$RUN"
rubrica validate --run "$RUN" --stage score
rubrica record-stage --run "$RUN" --stage score \
  --model sonnet --effort medium --skill src/rubrica/skills/rb-score/SKILL.md

rubrica propose-seal --run "$RUN"          # again, folding this round's rulings in
rubrica score-seal --run "$RUN" --round "$ROUND"
rubrica validate --run "$RUN" --stage score-seal
rubrica check-refs --run "$RUN"

jq -r '.verdict' "$RUN"/03-score/round-$ROUND.json
```

The verdict is one of `continue`, `converged`, `halted_no_progress`,
`halted_round_cap`. Only `continue` means another round: increment `ROUND` and
repeat the whole block, `propose-batches` included. `score` computes the
verdict; nothing but the reader acts on it.

- [ ] **Step 9: Write gate 2, instantiate, challenge, gate 3 and emit**

```bash
rubrica gate-brief --run "$RUN" --gate 2
```

```bash
for scenario_id in $(jq -r '.scenarios[] | select(.status=="active") | .id' \
                        "$RUN"/02-scenarios.json); do
  ./scripts/dispatch-stage.sh instantiate "$RUN" "$scenario_id"
done
rubrica validate --run "$RUN" --stage instantiate
rubrica check-refs --run "$RUN"
rubrica record-stage --run "$RUN" --stage instantiate \
  --model sonnet --effort medium --skill src/rubrica/skills/rb-instantiate/SKILL.md
```

`status` is one of `proposed`, `active`, `duplicate`, `rejected`; `active` is
the set that gets instantiated.

```bash
for scenario_id in $(ls "$RUN"/04-instances); do
  ./scripts/dispatch-stage.sh challenge "$RUN" "$scenario_id"
done
rubrica validate --run "$RUN" --stage challenge
rubrica check-refs --run "$RUN"   # only meaningful once every member has landed
rubrica record-stage --run "$RUN" --stage challenge \
  --model sonnet --effort medium --skill src/rubrica/skills/rb-challenge/SKILL.md
```

```bash
rubrica gate-brief --run "$RUN" --gate 3
```

```bash
./scripts/dispatch-stage.sh emit "$RUN"
rubrica validate --run "$RUN" --stage emit
rubrica check-refs --run "$RUN"
rubrica record-stage --run "$RUN" --stage emit \
  --model sonnet --effort medium --skill src/rubrica/skills/rb-emit/SKILL.md
rubrica run-summary --run "$RUN"
```

Then say what is in `06-suite/`, and name `rubrica smoke --agents agents.json`
as the next thing with a pointer to `docs/reference/cli.md` — the roster is a
detour this page does not take.

If `challenge` returned `re-seed` for any instance, `emit` refuses to compile
it; the repair is §9 of the guide.

- [ ] **Step 10: Write the two closing paths**

**The hand-picked shortcut** — reaches the same state as the intake step with no
corpus, no catalogue, no triage record and no gate 0:

```bash
rubrica intake \
  --input tests/fixtures/toy/api.json \
  --input tests/fixtures/toy/notes.md \
  --input tests/fixtures/toy/trace.json \
  --runs-dir "$RUNS" \
  --target-name toy --target-interface mcp \
  --max-rounds 2 --max-scenarios 128
```

**The same run in one step** — way 2, a peer of the sequence above. Point a
`claude` session at the orchestrator skill with the run directory:

```
You are the rubrica orchestrator.

Run directory: <absolute path to $RUN>
Your skill:    <absolute path>/src/rubrica/skills/rb-orchestrate/SKILL.md
```

State plainly: it dispatches `extract` through `emit`, gates every artifact,
holds the round loop and gates 1 through 3, spends at most one repair per stage
failure, writes `decisions.md`. It never runs `survey`, never dispatches a
triage pass and never holds gate 0 — all three are finished before it is handed
a run. `--no-gate` goes in that prompt's text, not on a command line.

**And say why this is not `dispatch-stage.sh orchestrate`:** that script grants
no subagent capability (its `permissions.allow` is `Read`/`Edit`/`Write` on the
run, `Read` on one skill directory, `Bash(rubrica *)`) and its `DENY` enumerates
every sibling `rb-*` skill directory. Both are deliberate — they are what makes
a single-stage dispatch measure the skill rather than the skill plus a
briefing — so an orchestrator dispatched through it could neither read nor hand
out the skills it exists to dispatch.

- [ ] **Step 11: Execute every command that does not dispatch a model**

This is the step that keeps the page honest. Against a scratch directory:

```bash
export RUNS=/tmp/rb-walkthrough/runs
mkdir -p "$RUNS"
export RUN=$(uv run rubrica survey --corpus tests/fixtures/corpus-toy --runs-dir "$RUNS" \
  --target-name toy --target-interface mcp --objective breadth)
uv run rubrica validate --run "$RUN" --stage survey;      echo "exit=$?"
uv run rubrica triage-slices --run "$RUN"
uv run rubrica validate --run "$RUN" --stage triage-slices; echo "exit=$?"
uv run rubrica check-refs --run "$RUN";                     echo "exit=$?"
uv run rubrica gate-brief --run "$RUN" --gate 0;            echo "exit=$?"
```

`gate-brief --gate 0` and `validate --stage triage-seal` will report the triage
record as absent — correct, since no dispatch has happened. Confirm the message
each prints and that the page's prose matches it.

For everything below `intake`, use a toy checkpoint so the deterministic
commands run against real artifacts:

```bash
R=$(PYTHONPATH=. uv run python -c "
from pathlib import Path
from tests.toy import build_toy_run
print(build_toy_run(Path('/tmp/rb-walkthrough/toy'), upto='challenge').root)")
for s in intake extract reconcile-subjects reconcile-contradict \
         reconcile-capabilities reconcile-outcomes reconcile-entities \
         reconcile-goals reconcile-gaps reconcile-services \
         synthesise-interfaces reconcile-seal propose-batches propose \
         propose-seal score score-seal instantiate challenge; do
  uv run rubrica validate --run "$R" --stage "$s" >/dev/null 2>&1
  printf '%-26s validate exit=%s\n' "$s" "$?"
done
uv run rubrica check-refs --run "$R";          echo "check-refs exit=$?"
uv run rubrica claim-utilisation --run "$R" >/dev/null; echo "claim-utilisation exit=$?"
uv run rubrica run-summary --run "$R" >/dev/null;       echo "run-summary exit=$?"
for g in 1 2 3; do uv run rubrica gate-brief --run "$R" --gate $g >/dev/null; echo "gate $g exit=$?"; done
```

- [ ] **Step 12: Execute every `jq` expression the page contains**

```bash
jq -r '.slices[].id'          "$R"/00-slices.json      2>/dev/null || echo "(no slices at this checkpoint)"
jq -r '.inputs[].artifact_id' "$R"/manifest.json
jq -r '.subjects[].id'        "$R"/01-subjects.json
jq -r '.batches[].id'         "$R"/02-batches/round-1.json
jq -r '.scenarios[] | select(.status=="active") | .id' "$R"/02-scenarios.json
jq -r '.verdict'              "$R"/03-score/round-1.json
ls "$R"/04-instances
```

Every one must print a non-empty list of ids with **no `null`**. A `null` means
the field name is wrong — that is the whole reason this step exists.

- [ ] **Step 13: Run the gates and the policy predicates**

```bash
make test && make check && uv run rubrica check-skills
uv run pytest tests/unit/test_docs_accuracy.py -q
grep -rn "running-a-stage-by-hand" docs/getting-started.md || echo "(no stale path)"
```

`make check` matters here: `README.md` and `CLAUDE.md` are not ruff-excluded,
and this task may have touched neither — but if it did, ruff formats them.

- [ ] **Step 14: Commit**

```bash
git add docs/getting-started.md
git commit -S -s -m "docs: Rewrite getting-started.md as the full walkthrough

It stopped at intake and handed the rest of the pipeline to a page that shows
no commands, so nobody could run Rubrica from a single document. It now walks
install to emit in order: every uv run rubrica command, every dispatch, the
five fan-out loops, all four gates, and record-stage in every dispatched block.

Two ways, both CLI, both covered: step by step, or one step through
rb-orchestrate -- with why that one is not dispatch-stage.sh orchestrate. No
future interface is described.

The claim that every command was executed first is dropped rather than
qualified: this page dispatches models, and per-block markers would not make
the claim true. Every command that does not dispatch one was executed anyway,
and every jq expression was checked against a real run for null.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 6: Reindex both documents in `docs/README.md`

**Files:**
- Modify: `docs/README.md:8-9` (the getting-started line), `:37-39` (the guide
  line)

**Interfaces:**
- Consumes: both rewritten documents.
- Produces: nothing downstream.

**Why both:** the index groups by the question each document answers. Leaving
either line as it stands files a new document under an old document's question.

- [ ] **Step 1: Rewrite the "Start here" line**

Current: "How do I get from a clone of this repository to a minted run I can
inspect?" — that was the old scope. Replace with a question about reaching an
emitted suite, e.g.:

```markdown
## Start here

- [`getting-started.md`](getting-started.md) — How do I run Rubrica end to end,
  one command at a time, from a clone of this repository to an emitted suite?
```

- [ ] **Step 2: Rewrite the "Guides" line**

Current: "How do I dispatch one skill for real, against a fresh run, and check
what it did?" Replace with:

```markdown
## Guides

- [`guides/invoking-rubrica.md`](guides/invoking-rubrica.md) — What are the two
  ways to invoke a stage, what does each take, and what setup do they share?
```

- [ ] **Step 3: Verify**

```bash
sed -n 1,12p docs/README.md; sed -n 34,42p docs/README.md
uv run pytest tests/unit/test_docs_accuracy.py -q
```

Confirm no line still promises "a minted run I can inspect", and that
`docs/README.md` remains the only user-facing file citing `superpowers`.

- [ ] **Step 4: Commit**

```bash
git add docs/README.md
git commit -S -s -m "docs: Reindex both walkthrough documents by the questions they now answer

The index groups by question, and both documents' questions changed:
getting-started.md now reaches an emitted suite rather than a minted run, and
the guide covers both invocation types rather than one hand dispatch.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 7: Final sweep and the three gates

**Files:** none modified unless a check fails.

**Interfaces:**
- Consumes: every earlier task.
- Produces: the evidence that the restructure is complete and consistent.

- [ ] **Step 1: The rename resolved, in both directions**

```bash
echo "--- old path anywhere outside recorded history (expect none):"
grep -rn "running-a-stage-by-hand" . \
    --exclude-dir=.git --exclude-dir=.venv --exclude-dir=runs \
  | grep -v "^./docs/superpowers/" || echo "(none)"

echo "--- every link to the new path resolves to a file:"
grep -rho "[a-z./-]*invoking-rubrica\.md" --include=*.md . --exclude-dir=.git \
  | sort -u
test -f docs/guides/invoking-rubrica.md && echo "target exists"
```

A one-directional sweep is how a stale pointer survives, so both run.

- [ ] **Step 2: Section citations point at sections that exist**

```bash
grep -n "invoking-rubrica.md" scripts/dispatch-stage.sh docs/reference/artifacts.md
grep -n "^## " docs/guides/invoking-rubrica.md
```

Confirm `dispatch-stage.sh:6` cites the isolation section, `:503` cites the
prompt-template section, and `artifacts.md` cites the verification section —
each by the number that section actually carries.

- [ ] **Step 3: The three gates**

```bash
make test
make check
uv run rubrica check-skills; echo "check-skills exit=$?"
```

Expected: green, clean, `0`.

- [ ] **Step 4: The documentation policy predicates over every changed document**

```bash
uv run pytest tests/unit/test_docs_accuracy.py -q
uv run python -c "
import re, pathlib
N=(r'(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|'
   r'thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)')
G=r'(?:stages?|skills?|subcommands?|gates?)'
pat=re.compile(rf'^#+[ \t]+[^\n]*\b{N}[ \t]+(?:\w+[ \t]+)?{G}\b', re.I|re.M)
for f in ['docs/getting-started.md','docs/guides/invoking-rubrica.md',
          'docs/design/limitations.md','docs/README.md']:
    t=pathlib.Path(f).read_text(); out,fence=[],False
    for ln in t.splitlines():
        if ln.lstrip().startswith('\`\`\`'): fence=not fence; continue
        out.append('' if fence else ln)
    hits=pat.findall('\n'.join(out))
    print(f, '->', hits or 'clean')
"
```

- [ ] **Step 5: The walkthrough is followable — read it once, top to bottom**

Not a command. Read `docs/getting-started.md` as a stranger would and check
three properties no test can:

1. **Every `$VAR` is defined before it is used** — `$RUNS`, `$RUN`, `$ROUND`.
2. **No block explains a flag** — that is the boundary rule; a block that
   drifted into explaining one belongs in the guide.
3. **The order matches `paths.STAGES`**, including `propose-seal` appearing
   twice in the round loop and `synthesise-interfaces` before `reconcile-seal`.

```bash
uv run python -c "from rubrica import paths; print(' '.join(paths.STAGES))"
```

- [ ] **Step 6: Commit anything the sweep corrected**

```bash
git status --short
# only if the sweep found something:
git add -A && git commit -S -s -m "docs: Fix what the final sweep found

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

- [ ] **Step 7: Report**

State, with the command output as evidence: the three gates' results, that the
old path is gone outside recorded history, that every `jq` line printed ids
with no `null`, and which commands in the walkthrough were **not** executed
(every `dispatch-stage.sh` line and everything that depends on one) — because
that is precisely what dropping the executed-commands claim commits this page
to being honest about.

---

## Self-Review

**Spec coverage.** Every section of the spec maps to a task: the two ways and
the plugin omission → Task 5 steps 2 and 10; decision 1 → Task 5 step 1;
decision 2 → Task 1; decision 3 → Task 5 steps 4–9; decision 4 → Task 5 step 9;
decision 5 → Task 4, plus the tables in Task 3 step 4 and Task 5 step 5; the
walkthrough sequence → Task 5 steps 3–10; the reconcile-band ruling → Task 5
step 6; the guide's nine sections → Task 3; the code change → Task 1; files
touched → Tasks 2, 4, 6; verification → Task 5 steps 11–13 and Task 7.

**Placeholders.** None. Every command block is literal, every `jq` expression
was executed against a real run directory before being written here, and the
one test is complete code.

**Consistency.** `$RUN`, `$RUNS`, `$ROUND` and `$R` are used consistently
(`$R` only inside Task 5's verification steps, where it names a toy checkpoint
rather than the walkthrough's own run). Section numbers for the guide are the
same nine everywhere they appear: §4 for `dispatch-stage.sh` mechanics, §6 for
isolation, §7 for the prompt template and checkpoints, §8 for verification, §9
for re-seeding.

**One known gap, deliberate.** No task executes a `dispatch-stage.sh` line
against a real model. That is decision 1: the walkthrough is a prescription for
those blocks, the executed-commands claim is dropped, and Task 7 step 7
requires the report to say so rather than imply otherwise.
