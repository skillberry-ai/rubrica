# The artifact contract

Rubrica's stages are dispatched in the order
[`docs/concepts/pipeline.md`](pipeline.md) describes. This document is about
the rule that governs *how* each dispatch happens, the run directory that
rule produces, and the two layers that check what lands in it.

## The one architectural rule

**Artifacts on disk are the only channel between stages.** A stage is
dispatched with exactly three things: the run directory, the stage name, and
the path to its skill file. No conversational context is threaded through. If
a stage needs a fact, it reads it from an artifact, or it does not have it.

Fan-out members — extract, instantiate, challenge — get a fourth thing: the id
of their own slice (`artifact_id`, `scenario_id`). That id is an address, not
context: it tells a member which file to open, never what a sibling
concluded. It is never a sibling's id.

### What the orchestrator may append to a re-dispatch

Exactly two things, and both are verbatim machine text, never paraphrased:

- a repair's gate findings — the exact lines a check layer produced, unedited;
- a re-seed's verdict fields — the exact fields `rb-challenge` wrote when it
  ruled `re-seed`, unedited.

A paraphrase is the orchestrator's conclusion wearing a finding's clothes: the
moment the orchestrator summarizes *why* a stage failed instead of quoting
what failed, its own judgment has entered the dispatch, and the artifact
contract is broken for that one round even though every file still validates.

### Why this is a rule, not a check

Nothing on disk can catch a violation of the one architectural rule. A
dispatch that pastes in "helpful" context — a summary of the world model, an
excerpt of what an earlier stage concluded — removes the fan-out isolation the
design was chosen for, and the artifact the stage then writes still validates
against its schema and still passes every reference check. The contamination
lives only in the dispatch itself, which no artifact records.

- For the tooling that dispatches one stage in isolation, by hand, see
  [`docs/guides/running-a-stage-by-hand.md`](../guides/running-a-stage-by-hand.md).
- For why this is called the weakest link in the whole design — no schema, no
  `check-refs`, and no digest can detect a violation after the fact — see
  [`docs/design/limitations.md`](../design/limitations.md).

## A run on disk

One directory per run is the whole state of the system. There is nowhere else
state hides — not in a database, not in an agent's context window between
dispatches, not in a cache.

```
runs/run-20260810-051723/
├── 00-catalogue.json        # every candidate survey found, one bounded digest each
├── 00-triage.json           # one disposition per candidate, plus deficiencies and projections
├── manifest.json            # inputs, hashes, limits, per-stage model + skill hash
├── decisions.md             # append-only lab notebook
├── 00-inputs/               # byte copies of every registered input
├── 01-claims/
│   ├── api-json.json        # one file per input artifact
│   ├── notes-md.json
│   └── trace-json.json
├── 01-world-model.json      # capabilities, entities, goals, invariants,
│                            # contradictions, gaps, frozen denominator
├── 02-scenarios.json        # every round's scenarios, with status
├── 03-coverage/
│   ├── round-1.json
│   └── latest.json          # the pointer the next round reads
├── 04-instances/<scenario-id>/
│   ├── seed.json            # the world, distractors included
│   ├── expected.json        # the oracle, derived from that seed
│   └── rationale.md         # which near-misses exist, and why
├── 05-verdicts/<scenario-id>.json
├── 06-suite/<scenario-id>/   # the emitted task package
├── 07-report.json
└── measurement/             # recall, stability, review sampling
```

`00-catalogue.json` and `00-triage.json` sit above `manifest.json` because
they exist before a run has one: `survey` writes the catalogue and
`triage-seal` writes the triage record before `intake` mints `manifest.json` and
`00-inputs/` — the numbering in the directory names stays intake's regardless,
since intake is still what fixes the run's identity. A run that skips the
survey/triage path (`intake --input`, hand-picked files) simply never writes
either file.

## Two check layers

- **Layer 1** — `rubrica validate --stage X`: JSON Schema, one schema per
  artifact kind. Schemas live in `src/rubrica/schema/*.json`, shipped as
  package data; `validate.STAGE_ARTIFACTS` maps each stage to the artifact
  kind(s) it must produce, so a stage that wrote none of them fails layer 1
  rather than passing on an empty output. This is the *is-this-file-shaped-
  correctly* layer.
- **Layer 2** — `rubrica check-refs`: cross-artifact references, seed
  conformance, reachability, and invariant evaluation. This is the *do-the-
  files-agree-with-each-other* layer.

A stage's output must clear layer 1 before the orchestrator dispatches the
next stage; the barrier and gated stages also clear layer 2 before their gate.

### What layer 2 does not do

Layer 2 checks that an element *references* a resolvable claim — the claim id
it cites exists somewhere in `01-world-model.json` — never that the claim
*supports* what the element says. Support is semantic: whether a claim's text
actually backs the assertion built on it is a judgment call, not a mechanical
property a reference check can compute, so this document does not pretend one
exists. Do not invent a mechanical check for it. Two real defects lived under
exactly that hole in the golden fixture itself, and **neither check layer ever
objected to either of them** — that is the load-bearing part. What surfaced both
was a live `rb-reconcile` dispatch, which reported one of them — a capability
whose described behaviour no claim in the set supports — as a *gap*; both were
then confirmed by a human reading `tests/toy.py`. A prompt noticing and a person
reading, in other words, and no check in between.

That gap is deliberate, not an oversight: matching an element's prose against
the claim it cites is a human's call, made at the gate that follows the
stage — not a rule layer 2 can enforce.

## The exit-code contract

| Code | Meaning |
|---|---|
| `0` | clean |
| `1` | findings, one per line on stdout |
| `2` | usage error, or an unreadable/misconfigured run |

Two invariants follow from that split, and this repository has violated both
of them before:

- **A stage defect must never surface as `2`.** A malformed artifact — a
  coverage document with `pct: "half"`, a scenario missing a required field —
  is a repairable failure of the stage that wrote it, and belongs on the `1`
  side even when the failure is an unexpected exception rather than an
  anticipated finding.
- **A `1` must never have empty stdout.** An orchestrator that branches on `1`
  and finds nothing to read on stdout has no findings to hand back as a repair
  prompt, and retries blind.

A third rule was learned the hard way, after both of the above were already
enforced: **a `1` must name the *right* artifact.** `check-refs` run over an
unreadable `01-claims/` once reported four fabricated `no such claim`
findings against a world model that was, in fact, correct — because the
directory listing that fed the check swallowed the permission error and
reported the directory as empty rather than unreadable, and an empty claims
set makes every claim id in the world model look invented.

### Why the split matters to a caller

A `1` is a repairable stage defect worth one retry: hand the findings back to
the stage that produced the bad artifact and let it try again. A `2` means
retrying cannot help — the harness itself is misconfigured, or the run
directory cannot be read — so the orchestrator's one bounded repair attempt is
reserved for `1` and never spent on `2`.

### The mirror rule

A filesystem problem must never surface as `1` either. `Path.glob` swallows
`EACCES` and yields nothing, so a check running over a directory it cannot
read used to announce *absence* — "stage 'extract' produced no claims
artifact" — when the true condition was that the input could not be read at
all. That is the same defect that produced the four fabricated findings above,
traced to its root cause: a directory listing must distinguish "this does not
exist" from "this exists and I cannot read it," and only the second belongs at
exit `2`.

Every listing of an artifact a check reads goes through
`paths.list_dir`/`paths.list_json` rather than a bare `glob` or `iterdir`
call, specifically because both of those raise `UsageError` — and therefore
map to exit `2` — on a directory that cannot be read, instead of silently
reporting it as empty. Transcript logs are a separate class and are globbed
directly: they are an agent's output being collected, not an artifact a gate
resolves references against, and the one that lives inside the run
(`smoke.py`'s clearing of a role's log directory) handles the `OSError` on the
spot — a transcript it could not clear is exactly the transcript it must not
score, so it returns that as a note instead of failing the run.

## The two checks worth understanding

**The reachability gate.** Every data assertion in a gold label carries a JSON
Pointer into its *own* scenario's seed. A positive assertion must resolve that
pointer with the value present; `answer_excludes` must resolve to nothing.
Resolution happens against that scenario's `seed.json` and nothing else, so a
label can never assert something true only of a different scenario's world —
it cannot reach another scenario's seed at all.

**The denominator check.** `denominator.capability_cells`, frozen once by
`rb-reconcile`, must equal the real number of capability × outcome-class
pairs the world model declares. A miscount here corrupts every coverage
percentage computed downstream, and nothing else in the pipeline would
notice — the numbers would simply be confidently wrong from that point on.

## The skill contract

Every `SKILL.md` under `src/rubrica/skills/rb-*/` carries a `## Contract`
block: exactly one TOML fence, declaring `stage`, `reads`, `writes`,
`schemas`, and `invokes`. Below that block, five sections are mandatory, in
this order: Inputs, Output, Method, Invariants, Refusal conditions.

`rubrica check-skills` holds each contract's declared names to the code that
owns them:

- every `reads`/`writes` entry must name a real `paths.RunPaths` attribute;
- every `schemas` entry must match what `validate.STAGE_ARTIFACTS` requires
  for that stage;
- every `invokes` entry must name a real `rubrica` subcommand.

It validates the *names* — that each one resolves to something the code
actually has — never whether the declared set is the *right* one. A `reads`
list can be complete, over-broad, or missing something the stage's own prose
depends on, and `check-skills` passes all three; only reading the prose
against what it actually needs catches that.
