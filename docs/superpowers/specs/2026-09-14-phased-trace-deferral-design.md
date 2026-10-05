# Phased trace deferral

Design for making a benchmark-ready world model reachable in hours rather than
in a day, by deferring the corpus's most expensive input kind to a later phase
instead of dropping it.

Measured on `run-20260911-120324` (parsec, `http-sse`, `breadth`, 149 admitted
inputs, 4.4 MB) at `dc0f618`, which reached gate 1 on 2026-09-14 for
**$516.87**. $119.18 of that was the `reconcile` output-budget defect PR 7 has
since fixed, so the figure this design is measured against is the
**post-fix ~$390 and ~14h wall clock**, not the $517 actually spent.

## The problem, and the two framings that turned out to be one

The operator's diagnosis was that the run is too heavy for a medium-sized
target, with two candidate routes: better triage heuristics so less
low-relevance material is admitted, and simplifying the "forensic"
capabilities. Measurement shows these are **one lever pulled from two ends**,
not two independent optimisations.

Joining `claim-utilisation` against `00-catalogue.json`'s `kind`:

| kind | inputs | corpus KB | claims | cited |
|---|---|---|---|---|
| trace | 68 | 3,442 (78%) | 3,287 | **12%** |
| source_code | 54 | 756 | 2,356 | 63% |
| design_doc | 20 | 185 | 1,481 | 41% |
| other | 7 | 41 | 295 | 38% |

Traces are 78% of the corpus by bytes and the least cited. But attributing
every world-model citation back to the kind of input that produced it shows
where their value actually lands:

| world-model group | citations | trace share |
|---|---|---|
| outcome_classes | 1,853 | **1%** |
| invariants | 565 | 5% |
| capabilities | 789 | 6% |
| gaps | 109 | 6% |
| goals | 254 | 35% |
| **actors** | 188 | **54%** |
| **contradictions** | 408 | **53%** |

Traces are near-irrelevant to the parts that drive the benchmark and are the
*majority source* for the two forensic outputs. So "admit less low-relevance
material" and "cut the forensic capabilities" are the same cut. They are not
low-value inputs; they are inputs whose entire value lands in outputs the
benchmark never reads.

That is what makes deferral the right shape rather than exclusion. The
operator's framing -- analyse trajectories *after* capabilities and gaps are
known, and use them to validate capabilities, close gaps and resolve
contradictions -- keeps the value and reorders the spend.

## What phase 1 loses, measured rather than estimated

Every world-model element was classified by whether it would survive if traces
were never extracted (an element survives if any non-trace claim cites it,
counting `outcome_classes` and `invariants` against their parent):

| element | total | trace-only, would vanish | survives |
|---|---|---|---|
| capabilities | 235 | **0** | 235 |
| outcome_classes | 943 | 1 | 942 |
| entities | 113 | 4 | 109 |
| invariants | 354 | 16 | 338 |
| gaps | 32 | **1** | 31 |
| goals | 78 | **23** | 55 |
| actors | 19 | 0 | 19 |
| contradictions | 204 | **119** (99 both sides, 20 one side) | 85 |

The figure that decides the design: of the **113 capabilities carrying a tool
`binding`** -- the drivable ones `denominator.capability_cells` counts --
**zero** depend on traces. `capability_cells` stays 448 in both phases. The
denominator moves only through goals: 23 goals are trace-only and contribute 52
of 170 hop slots.

    phase 1 denominator = 448 cells + 118 hop slots = 566
    full run            = 448 cells + 170 hop slots = 618

So phase 1 gives up 85 of 204 contradictions, 23 of 78 goals, 52 of 170 hop
slots, 16 of 354 invariants, 4 of 113 entities and 1 of 32 gaps -- and gives up
nothing the benchmark's spine rests on.

## The seam already exists

No change to the benchmark half is required, because nothing in it reads a
forensic artifact. The `reads` contracts:

| skill | `reads` |
|---|---|
| `rb-propose` | `manifest`, `world_model`, `batches`, `coverage_latest` |
| `rb-score` | `manifest`, `world_model`, `scenarios`, `batches` |
| `rb-instantiate` | `world_model`, `scenarios` |
| `rb-challenge` | `scenarios`, `seed`, `expected` |
| `rb-emit` | `scenarios`, `verdict`, `expected`, `world_model` |

Neither `01-subjects.json` (942 KB) nor `01-contradictions/` (14 parts, 19% of
the world model) appears in any of them. The two textual mentions of
`01-subjects.json` in `rb-propose` and `rb-score` are **prose analogies** about
how a barrier stage finds its own slice, not reads; `rb-challenge`'s single
"contradictions" mention is about self-contradictory verdicts. Verified by
reading each occurrence.

This is why the operator's "maybe we should split them" instinct is correct
about the boundary but does not need to be acted on to get the speed: the
interface between the two tools is already exactly `01-world-model.json` plus
`01-claims/`. Splitting the repositories would buy the ability to feed the
benchmark half a hand-written world model -- real value, but orthogonal to cost
-- at the price of publishing that artifact as an inter-tool contract and
duplicating `refs.py` and `schema/`. Deferred, not rejected; see Follow-ups.

## The corpus is already partitioned by kind

`00-slices.json` groups the 353 candidates into 11 slices, and the grouping is
almost exactly the kind boundary:

| slice | admitted | of which trace | phase-1 admits |
|---|---|---|---|
| s01 | 15 | 15 | **0** |
| s02 | 18 | 18 | **0** |
| s03 | 20 | 20 | **0** |
| s04 | 20 | 15 | 5 |
| s05–s11 | 76 | 0 | 76 |

**Three of the eleven `rb-triage-rule` dispatches become empty**, and one is
mixed. This is what removes the need for new triage heuristics: the partition
that matters is structural and already computed.

It also corrects a claim made earlier in the investigation and worth recording
so it is not repeated. Triage's `priority` ranking looks inverted against
utilisation -- its top-ranked 25 inputs are 47% of corpus bytes and only 13%
cited, while inputs ranked 76-100 are 65% cited. Triage is not ranking *badly*.
It ranked traces first because for forensics they genuinely are the richest
inputs, supplying 53% of contradictions. It was ranking for the wrong phase.
The fix is phase-awareness, not a better heuristic, and no change to triage's
judgment is in this design.

## The design

### `defer`, a third disposition

`schema/triage-0.1.json:97` becomes `{"enum": ["admit", "decline", "defer"]}`,
and `decline_reason` gains `deferred_to_phase`. A deferred candidate keeps its
`priority`, so phase 3 consumes triage's ranking directly instead of
recomputing it.

The property that makes this cheap: **eight call sites read
`disposition == "admit"`** -- `intake.py:571`, `refs.py:1582`,
`seal.py:444/472/514`, `brief.py:917/1224`, `summary.py:564` -- and **none needs
changing**. `defer` is not `admit`, so intake does not materialise it, `refs`
does not expect a claims file for it, and the seal does not count it. A deferred
candidate is invisible to every existing consumer exactly as a declined one is,
while remaining distinguishable from it by anything that asks.

`defer` is a distinct value rather than a `decline` with a special reason code
because the two make opposite promises. A decline says this input has no
evidence value; a defer says it has value this phase cannot spend. Collapsing
them would make `triage-seal`'s counts and the gate-0 brief tell the operator
that 68 inputs were judged useless.

### Where deferral is decided

At triage, not at survey and not at extract.

`survey` is unchanged: all 353 candidates catalogued, all digests computed. Two
consequences argued for this. Deferring at survey would need a fresh
survey-and-triage pass in phase 3 and would relieve the 1 MiB
`max_catalogue_bytes` ceiling for the wrong reason. Deferring at extract -- with
triage still admitting all 149 -- would leave `01-claims/` missing files for
admitted inputs, which `claim-utilisation` and `refs.check_claim_utilisation`
correctly read as a hole.

Deferring at triage costs gate 0's dispatch budget once and puts the decision
in `00-triage.json`, where it is auditable and reversible.

### The manifest carries the phase

Declared at intake:

    rubrica intake ... --phase 1 --defer-kind trace

`manifest.json` gains `phase: {number: 1, deferred_kinds: ["trace"]}`. Three
consumers read it:

- **`triage-slices`** marks a slice whose every candidate is a deferred kind, so
  the driver does not dispatch `rb-triage-rule` for it. s01/s02/s03 on this
  corpus.
- **`rb-triage-rule`** gains one instruction, for mixed slices only: a
  candidate of a deferred kind takes `disposition: defer` with
  `reason_code: deferred_to_phase`, and keeps its `priority`. s04 only.
- **`reconcile-seal`** marks `reconcile-subjects` and `reconcile-contradict`
  not-required, and writes the `phase` block into the world model.

`--defer-kind <kind>` rather than `--profile benchmark`: it says what it does,
it generalises to a corpus whose expensive kind is not traces, and it does not
create a named profile whose meaning drifts as stages are added.

### The world model records its own incompleteness

`01-world-model.json` gains one optional field, written whenever the manifest
declares a phase and absent on a run that does not:

    "phase": {"number": 1, "deferred_kinds": ["trace"], "deferred_count": 68}

This is load-bearing rather than informational. `target_brief` reads it and says
so on the page: a brief that shows the parsec team 85 contradictions without
stating that 119 more are unread would misrepresent the analysis, and the
current tool has no way to say it. `summary` renders it for the same reason.

### Phase 1 skips two passes

`reconcile-subjects` and `reconcile-contradict` are not dispatched. Both become
not-required under a phase with deferred kinds. They are the two slowest passes
in the run -- 91 min and 81 min, $73.40 together -- and with traces deferred
they would have roughly half their material.

This is also why **phase 3 is a pipeline segment rather than a bolt-on**:
`reconcile-contradict` slices on `01-subjects.json`, so phase 3 must run
subjects first. Recorded here so the follow-up is not scoped as "re-run the
skipped passes."

## What it costs and what it saves

| band | full run (post-PR-7) | phase 1 |
|---|---|---|
| gate 0 | $23.05, 11 slices | ~$17, 8 slices |
| `extract` | $223.03, 149 inputs, 4.4 MB | ~$37, 81 inputs, 0.98 MB |
| `subjects` + `contradict` | $73.40, 172 min | **$0**, skipped |
| `capabilities`…`services` | $70.86 | ~$50 |
| **total to a sealed world model** | **~$390, ~14h** | **~$104, ~4h** |

Both estimates are stated with their basis and their weakness. The extract
figure applies the run's own measured fit of $0.0375/KB -- the same fit that
**overshot its projection by 51%** on this corpus, so treat ~$37 as a floor and
~$56 as the plausible top. The reconcile figure scales by claims-directory size
(4.7x smaller), which is the softest number in the table: those passes have a
per-pass floor that does not shrink linearly, and `goals`/`gaps`/`services`
already ran at $8.49-$13.89 on the *full* corpus. If reconcile does not shrink
at all, phase 1 is ~$125.

**What phase 1 does not fix.** Implied suite size at v1 is 448 + 118 = **566,
still far above the `max_scenarios` ceiling of 128.** The target still needs
narrowing or the ceiling raising. What changes is the price of iterating on that
decision: ~$104 per attempt instead of ~$390.

## Phase 3's boundary, defined but not designed

In scope for this spec: the contract phase 3 must honour. Out of scope: the
validation semantics.

- A `rubrica admit-deferred` command flips `defer` to `admit` with
  `authority: human`, in the manner of `adopt-projection`.
- The 68 traces are extracted; `reconcile-subjects` runs, then
  `reconcile-contradict`.
- `reconcile-seal --denominator-version 2` re-seals. `refs.py:3459` already
  refuses to score v1-proposed scenarios against a v2 denominator, so the guard
  against silently mixing phases exists and is not new work.
- **Phase 3 implies a propose round 2, not merely a re-seal.** v2 adds 52 hop
  slots the phase-2 suite does not cover, and `refs` will flag that rather than
  let it pass.

The genuinely novel part, deferred to its own spec: phase 3 consumes a phase-1
world model as *input*, and the reconcile skills currently assume they are
building from scratch rather than confirming or refuting a prior assertion. A
new `rb-validate-traces` pass is needed, with a stated rule about what it may
and may not overwrite. Nothing in `intake.py`, `triage.py` or `reconcile.py`
supports admitting inputs after a seal today, which is what makes this a design
question rather than a plumbing one.

## Follow-ups, explicitly not in this spec

- **`rb-validate-traces`** and the phase-3 semantics above.
- **Repository split** into a spec-recovery tool and a benchmark builder. The
  seam is clean and this design does not disturb it; the motivation would be
  accepting a hand-written world model, not cost.
- **Effort tiering by stage.** One global `RUBRICA_EFFORT` charges the
  world-model band as if it were the propose/score loop; an `extract` member
  reads 11.5 KB while every `reconcile-*` pass re-reads the whole claims
  directory. Drafted separately at
  `~/work/issues-draft/rubrica-issue-effort-should-be-tiered-by-stage.md`.
  Independent of phasing and compounds with it.

## Limitations this design accepts

- **A phase-1 world model is not comparable to a full one** through
  `stability.diff-runs`, and the `phase` block is what makes that detectable
  rather than silent. `_STAGE_FIELDS` compares `model`, `effort` and
  `skill_sha256`; it does not read `phase`, so `diff-runs` will not itself
  object. Recording the limitation rather than widening `stability.py` in this
  spec.
- **`deferred_kinds` is a kind-level instrument, so a valuable trace is deferred
  along with the rest.** On this corpus that costs 23 goals and 1 gap in phase
  1. A per-candidate override is deliberately not designed: it would reintroduce
  the per-input judgment this design exists to avoid paying for.
- **The 12%-cited figure for traces is a fact about this corpus at this
  objective.** A `depth` run, or a target whose behaviour is only observable in
  trajectories, could invert it. `--defer-kind` is per-run for that reason and
  has no default; a run that does not pass it behaves exactly as today.
