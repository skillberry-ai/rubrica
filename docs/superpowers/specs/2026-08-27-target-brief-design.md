# `target-brief`: the run's understanding of the target, put to the people who own it

**Date:** 2026-08-27
**Issue:** none — raised in conversation: "at gate 1, it would be helpful to be
able to generate a report I can send to the AUT owners and ask: does this
accurately describe your system?"
**Status:** design approved, plan not yet written

## 1. The problem

Gate 1 asks a human to read `01-world-model.json` against the claims it cites.
That is the gate's whole purpose — [`limitations.md`](../../design/limitations.md)
states it directly, under the entry ruling that layer 2 checks that an element
*references* a resolvable claim and never that the claim *supports* it: "Checking
support is what the human gates are for — gate 1 in particular."

The person holding gate 1 is the wrong person to answer one half of that
question. They can check that a citation resolves and that the cited sentence
plausibly backs the structural claim. They cannot check whether the resulting
picture is **true of the system**, because they do not own the system. The people
who do own it have never been shown the picture, and every artifact in the run
that would show it to them is written for rubrica rather than for them.

So: a report, generated from a run at gate 1, that describes the target in the
target owner's vocabulary and asks them to correct it.

Two things this is not. It is not a gate — nothing branches on it, and an owner's
reply enters the run only as whatever the operator chooses to write with
`rubrica decide`. And it is not a new analysis: every sentence in it is either
read from an artifact or is arithmetic over artifacts, which is `run-summary`'s
ruling and `gate-brief`'s before it.

## 2. The world model already carries the prose; what it lacks is an audience

The finding that decides the whole approach: **this is a field-selection problem,
not a prose-generation problem.** The world model's own prose is already good
English. What makes it unreadable to an outsider is that owner-facing and
internal fields sit side by side in the same records.

| Selected | Dropped, and why |
|---|---|
| gap `unknown` — "What `get_ticket` returns for an unknown `ticket_id`" | gap `blocks: [propose, score, …]` — pipeline stage names |
| goal `statement`, actor `name` | goal `expected_hop_depths` — a scoring input |
| capability `operation`, `params`, `binding.tool` | capability `confidence` — measured all-`high` on 39 of 39 (§3.1) |
| outcome-class `description` | `denominator` — coverage arithmetic |
| entity `name`, `collection`, `fields`, `relations` | element `id`s, except as a muted reply handle (§4.1) |
| invariant `prose` where present, else `statement` | — |
| contradiction `nature`, `resolution` | contradiction `rationale` — see §4.1.C |
| gap `why_it_matters` | **Judgment call.** Fused, not separable — see §4.3 |

Prose is selected and relabelled, **never rewritten.** A description that reads
"Returns cost data … (clm-aws-costs-py-013 via cost-tools-001 preferred_b
resolution)" ships with that parenthetical intact. Paraphrasing a stage's output
so it reads better is the failure this project names in its own words — "a
paraphrase is the orchestrator's conclusion wearing a finding's clothes" — and a
laundered sentence in a document an owner is asked to ratify is that failure at
its most expensive. A legend covers the one recurring idiom: where the model
writes "no claim addresses X", the report says that means the owner's documents
did not say.

## 3. Measurements that shaped the design

Taken on the three most recent runs on disk carrying a world model:
`run-20260826-090456` (parsec, `http-sse`, 269 inputs, 7,664 claims),
`run-20260825-094033` (executive-agent, `agent`, 192 claims) and
`run-20260824-054040` (reservation-service, `http-sse`, 476 claims).

### 3.1 The derivation badge does not discriminate, and is dropped

The first design carried a per-element badge from its cited claims' `derivation`:
"your documents state this" / "we inferred this" / "we read this off your code".
The corpus-wide numbers looked promising — parsec's claims are 6,379 `stated`,
1,130 `reverse_engineered`, 155 `inferred`.

Measured at the element level it collapses. On parsec, **all 39 capabilities, all
30 entities, all 26 goals and both actors badge `stated`.** On executive-agent, 1
capability of 37, 1 entity of 18 and its single actor badge anything else.
reservation-service discriminates on 4 of 4 entities and 1 of 6 goals, and on
neither of its other two kinds.

The cause is that `derivation` measures whether *an artifact asserted* the fact,
and source code is an artifact that asserts things. A capability read straight out
of `src/tools/aap2.py` is `stated`, which is correct and tells an owner nothing.
Capability `confidence` is worse: all 39 `high`.

Dropped rather than shipped. A badge that reads the same on every row is
decoration, and decoration in a ratification document is harmful — it implies a
distinction was checked.

### 3.2 Source count and source kind do discriminate, and replace it

Both are arithmetic over `claims` → `01-claims/` → `manifest.inputs[].kind`.

| | parsec | executive-agent | reservation-service |
|---|---|---|---|
| capabilities resting on **one** source | 4 of 39 | **13 of 37** | 0 of 5 |
| entities resting on **one** source | **28 of 30** | 18 of 18 | 1 of 4 |
| capability source kinds | 38 `source_code`, 1 `source_code+trace` | **13 `design_doc` only**, 24 `design_doc+openapi` | 5 spanning four kinds |
| goal source kinds | 19 `design_doc+source_code`, **7 `source_code` only** | 12 `design_doc` only, 10 mixed | mixed |
| capabilities touched by a contradiction | 6 of 39 | **16 of 37** | 2 of 5 |

Every row discriminates on at least one run, and each states something an owner
can act on without knowing what rubrica is:

- *13 of executive-agent's 37 operations rest on a design document alone* — no
  schema, no code, no trace. Either they are unimplemented, or we read a plan as
  a description of reality.
- *28 of parsec's 30 data shapes were seen in exactly one file.*
- *2 of reservation-service's 4 data shapes were seen only in a captured trace* —
  never specified anywhere.

So each element carries a **provenance line** rather than a badge: the files it
rests on, their count, and a `disputed` marker when any cited claim appears in a
contradiction. Same three inputs also order the tier-1 ask list (§4.1).

### 3.3 The contradictions are the payload

parsec records 41 contradictions — 15 `unresolved`, 22 `preferred_b`, 3
`preferred_a`, 1 `both_possible` — and they are documentation-vs-implementation
drift, stated in the owner's own terms:

- the design document states `verify=False` on the `httpx.AsyncClient`; the
  connections claim describes the same client without it;
- the design document states `query_aap2` exposes three actions; the tool module
  states four, adding `get_job_log`;
- the agent instructions describe the response with `elapsed` and `name`; the
  implementation returns `duration_seconds` and `job_name`;
- the design document specifies a uniform 500-character stdout truncation; the
  implementation uses 4,000 for failed events and 500 otherwise.

An owner acts on those the day they read them, whether or not they ever comment on
the rest of the document. This is the section that earns the report.

And it is where the claim-id "leak" dissolves. Every claim id resolves through
`01-claims/` to `manifest.inputs[].source_path`, a `locator` and a `quote` —
measured over every citing field, including both sides of a contradiction:
of parsec's 230 distinct cited claims **all 230 resolve and 224 carry a quote**;
reservation-service is 154 of 154 with quotes. Executive-agent is the warning —
126 of 126 resolve but only **67 carry a quote**, so a quote is a bonus and a
locator is the floor (§6). So a contradiction renders
as two real files quoting themselves, not as two ids:

```
Your design doc and your code disagree about what query_aap2 can do.

  docs/…/2026-03-12-aap2-job-investigation-design.md   #query_aap2
    "Single tool with three actions, following the query_babylon_catalog pattern."

  src/tools/aap2.py   line:449-460
    async def query_aap2(action: str, controller: str = "", …)
    → four actions: get_job, get_job_log, get_job_events, find_jobs

  We went with the code. Is that right?                    ref: ctr-aap2-agent-002
```

### 3.4 Real runs omit `claims` where the schema now requires it

`validate --stage reconcile-seal` on the parsec run exits 1 with 213 findings:
**195 on `capabilities[].outcome_classes` and 18 on `gaps`, every one of them
`'claims' is a required property`.** Every gap in all three runs carries no
`claims` key at all.

This is not a new defect and is not this design's to fix. It is the same parked
class as the entry in [`limitations.md`](../../design/limitations.md) titled "Two
committed recordings predate the requirement that every element cite a claim":
those three `$defs` gained a required `claims` array when read coverage was
forced on 2026-08-26, and these runs predate it by hours.

Three consequences the report must absorb:

1. **An outcome class's provenance comes from its parent capability's `claims`**,
   because its own may not exist. Measured: capability-level `claims` are present
   on 39 of 39, 37 of 37 and 5 of 5.
2. **A gap gets no provenance line.** Its `unknown` prose stands alone. This costs
   nothing — the prose is the question, and a gap is by definition a place no
   claim reached.
3. **The report will routinely run against world models that fail layer 1**, so it
   must state absence rather than raise. That is already its posture (§6); this
   makes it load-bearing rather than defensive.

## 4. The document

One self-contained HTML page — inline CSS, no network, no external asset — so it
survives being emailed and archived, and prints. `run-summary`'s shape, reused for
`run-summary`'s reason.

### 4.1 Tier 1 — what we need them to answer

Four groups, in this order. Each item carries its rubrica id in muted small print,
for two measured reasons: gap prose cross-references contradiction ids in the
plain text (parsec's `gap-001` opens "cost-tools-003: subscriptions_queried field
presence…"), so an unreferenceable id makes the prose unresolvable; and because
nothing structural comes back (§5), a prose reply needs a handle to name.

**A. We read these files — did we miss anything?** From `manifest.inputs`:
`source_path` relative to its common prefix, grouped by `kind` and directory, with
counts shown and the file list collapsed. parsec is 269 files across
`source_code`, `design_doc` and `trace`.

This group is first on purpose. It is the one question the pipeline structurally
cannot ask itself: gate 0 decides what the run can ever know, and
[`CLAUDE.md`](../../../CLAUDE.md) argues that triage cannot also hold its own gate
because "the same party selecting the inputs and ratifying the selection would
make the whole run unfalsifiable." The target's owner is the only party outside
that loop who can say a document was missing.

**B. Your documents disagree and we could not tell which is right** —
`resolution == "unresolved"`. parsec: 15. `nature` verbatim, then both sides as
file, locator and quote.

**C. They disagreed and we picked one** — `preferred_a`, `preferred_b`,
`both_possible`. parsec: 26. Same rendering, plus which side was taken, in words:
"We went with the code." The `resolution` enum maps to a phrase; `rationale` is
dropped from this tier because it is dense with claim ids and argues the case to a
reader who already accepts the framing. It stays available in `run-summary`.

**D. Your documents never said** — `gaps`, `unknown` verbatim. parsec: 18.

Within each group, items are ordered by id. Ranking by blast radius — how many
world-model elements rest on a disputed claim — would order better, and §3.2 shows
the inputs are already computed. Deferred anyway: it is the one piece of genuinely
new analysis in the design, and shipping it unmeasured is how a report starts
asserting a judgment it did not earn.

### 4.2 Tier 2 — what we believe, in full

Each section a collapsed `<details>`, so the page skims in three screens and reads
in forty.

- **Operations** — `binding.tool` as the handle, `operation` as the sentence,
  `params` as a compact list, then the five outcome classes under plain labels:
  *On success* / *When there is nothing to return* / *When it is not found* / *On
  error* / *Not addressed*. Labels come from `kind`; the prose is verbatim.
- **Kinds of data** — entity `name` and `collection`, `fields` as a table,
  `relations` as prose, invariants from `prose` where present.
- **Who uses it, and what they are trying to do** — actor `name`, then that
  actor's goals by `statement`.

Every element carries its §3.2 provenance line.

Deliberately no attempt to detect, mechanically, which outcome classes are
statements of behaviour and which are statements of absence. Measured: parsec
records exactly one outcome class of each of the five kinds for each of its 39
capabilities, and absence is expressed *in prose under the semantic kind* —
`oc-qac-empty` is `kind: empty` with the description "No claim addresses what is
returned when no cost data exists." So `kind` does not mark absence, no other
field does, and the alternative is string-matching model prose. The five labels
plus the legend carry it instead.

### 4.3 What is deliberately absent

- **No sign-off block.** Dropped by decision: whether this becomes an instrument
  people sign depends on how the first conversations with owners actually go, and
  a signature line on a document nobody has used yet asserts a process that does
  not exist. The page asks the question; it does not collect a ratification.
- **No gap `why_it_matters`.** Judgment call, and the weakest point in the design.
  It is the one field where owner-facing and internal are fused inside a single
  string: "a scenario built on the empty outcome class has no stated ground truth"
  is rubrica talking about itself. Selecting it leaks; splitting it means
  rewriting it, which §2 forbids. One generic sentence heads group D instead, and
  the cost is real — an owner is not told why each individual question matters.
- **No coverage, scenario, verdict or suite content.** That is the run's story, not
  the target's, and `run-summary` already tells it.

## 5. Where it lives

New subcommand **`rubrica target-brief --run RUN [-o PATH]`**, defaulting to
`<run>/target-brief.html`. New module `src/rubrica/target_brief.py`, splitting into
a `target_brief_html.py` if the renderer passes roughly 400 lines, as
`summary.py` / `summary_html.py` already does.

Named for its subject, not its gate: `gate-brief` is the brief about the run at a
gate; this is the brief about the target. It joins `claim-utilisation`,
`gate-brief` and `run-summary` as a **report, not a gate — always exit 0 on a
readable run.** No schema, no `0N-` prefix, outside the numbered artifact
contract, read by no stage, and never the thing that turns a readable run into a
defect finding. An unreadable run directory is a different failure and still
exits 2.

`gate-brief --gate 1` gains one line naming the command, because that is the only
place an operator will discover it exists.

Reuse, not re-spelling — this repo has been bitten by second spellings of one
rule:

| Need | Existing home |
|---|---|
| claim id → artifact, then source, locator, quote | `refs._claims_by_artifact` |
| HTML escaping, including the lone-surrogate ruling | `summary.esc` |
| absent vs. malformed, stated separately | `summary.Absent`, `summary.Malformed` |
| read-or-`None`, dict-or-nothing, dict/str members of a list | `brief._quietly`, `_mapping`, `_dicts`, `_strings` |
| table, section and marker chrome; CSS | `summary_html` |

Nothing here recomputes a number another module owns.

## 6. Degradation

Absence and malformation are stated separately per section, for the reason
`summary.py` records: the two were one word until a run reported that an artifact
had been produced *and* that it was not present, on one page.

**A quote is not guaranteed and its absence is not a defect.** Measured in §3.3:
of the claims cited by a world model, parsec quotes 224 of 230 and
reservation-service 154 of 154, but executive-agent quotes only 67 of 126. So
every rendering degrades to file plus `locator` alone, silently — an evidence
record carrying no `quote` is schema-valid, `quote` being the one optional field
of the three, and a report that flagged it would be reporting a permitted shape
as a fault to a reader who cannot act on it.

A run at gate 1 has a manifest, `01-claims/` and `01-world-model.json` by
construction, and each is still optional in the reader. `01-claims/` unreadable
renders every quote as stated-absent and never as a fabricated one: the
`chmod 000` incident that produced four fabricated `no such claim` findings
against a correct world model is exactly this shape, and this report has more
room to commit it than `check-refs` did, because a fabricated quote in a document
sent to the system's owner would be read as our assertion about their file.

## 7. Testing

Against the toy run and both negative fixtures, which between them carry a
contradiction and a gap. Then the paths that have actually broken things here:
`chmod 000` on `01-claims/`; a claim id in the world model that resolves to
nothing; a `01-claims/` member that is valid JSON of the wrong shape; a lone
surrogate in a `quote`, a `source_path` and the run directory name; a world model
whose outcome classes and gaps carry no `claims` (§3.4 — the committed recordings
are already this shape, so the fixture exists); and `-o` to a path outside the run.

Every predicate measured in both directions before it is committed, per the repo
rule: blank the prose or field it claims to check and watch it go red, then reword
that prose meaning-preservingly and watch it stay green. The provenance line and
group ordering are the two most likely to be vacuous, since both can be satisfied
by any non-empty world model.

## 8. Documentation to update

- [`docs/reference/cli.md`](../../reference/cli.md) — a `rubrica target-brief`
  section. `tests/unit/test_docs_accuracy.py` fails until it exists.
- [`CLAUDE.md`](../../../CLAUDE.md) — the reports-not-gates paragraph, which names
  `claim-utilisation` and `gate-brief` today.
- [`docs/README.md`](../../README.md) if it indexes per-command reference.

Not `pipeline.md` and not `artifacts.md`: this is not a stage and mints no
artifact. Neither `cli.md` nor `CLAUDE.md` may cite this spec — `docs/README.md`
is the one user-facing file permitted to link the recorded-history tree this file
sits in, and `test_docs_accuracy.py` enforces it.

## 9. Deferred, with the reason

- **Blast-radius ranking** of the tier-1 groups (§4.1). Inputs already computed;
  wants a measurement before it ships.
- **Structured owner replies.** The decision was explicit: an owner's correction
  comes back as prose and reaches the run only through `rubrica decide`. The two
  alternatives considered were admitting the reply as a corpus input and re-running
  from survey, and writing a `01-signoff.json` the gate reads. The first is
  cheap and remains available with no new code; the second would put a fact about
  the target into the run that no claim grounds, which is a larger commitment than
  a first conversation with an owner justifies.
- **A Markdown twin** for owners who would rather annotate than reply in email.
  One selection pass, two renderers; declined for now because two renderers over
  one selection drift, and nothing has yet established which format an owner
  actually returns.
