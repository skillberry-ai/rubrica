# Claim Utilisation and Observable Judgment — Design

**Date:** 2026-08-12
**Status:** Approved design, not yet implemented. Every number in §1 was measured
against `runs/run-20260812-130056` and `runs/run-20260812-074017` on the date
above; the two skill-prose failures in §2 and §3 were located by reading those
runs' artifacts, not inferred.
**Author:** Jonathan Bnayahu (with Claude)

## 1. What this is, and the measurement that shaped it

Three changes with one theme: **a stage that silently drops evidence should be
visible, without punishing a stage that correctly drops noise.**

They come out of the trajectory run
([`2026-08-12-reservation-service-trajectory-run-design.md`](2026-08-12-reservation-service-trajectory-run-design.md)),
whose predictions P3 and P4 both failed, and whose failures turned out to have
different owners than first supposed.

### The measurement

`runs/run-20260812-130056` extracted 287 claims. The world model cites 157 of
them. **130 claims — 45% — are cited by nothing, with zero findings from either
gate.** `refs.py:437` checks that a world model citing a claim id refers to a
real one; nothing checks the reverse.

The obvious fix is wrong, and the per-kind split is why:

| kind | total | uncited | |
|---|---|---|---|
| `outcome_class` | 44 | 6 | 13% |
| `capability` | 99 | 28 | 28% |
| `actor` | 22 | 13 | 59% |
| `goal` | 41 | 25 | 60% |
| `invariant` | 29 | 18 | 62% |
| `entity` | 52 | 40 | 76% |

Sampling the uncited `entity` claims explains the 76%: they are deployment
facts — `MockProvider supplies deterministic data`, `The server reads an optional
LOG_LEVEL environment variable`, `By default the server starts listening on
http://0.0.0.0:8000`. Those are **correctly dropped**. `rb-reconcile` is
filtering noise that entered through deployment-heavy READMEs.

Per input artifact:

| Input class | Utilisation |
|---|---|
| ten trajectory slices | 64–92% |
| `tools-list-json` | 83% |
| `agent-graph-py` | 36% |
| `mcp-tool-notes-md` | 27% |
| `agent-notes-md` | 16% |
| `agent-server-py` | 8% (2 of 25) |

The control run's five inputs ran 60–100%, none below 60%.

So **utilisation rate is a fact about the input, not about reconcile's
diligence.** Observation- and interface-derived claims get used; prose and
deployment documentation mostly does not.

### Why a "cite everything" gate is rejected

It would emit roughly 130 findings to catch one real loss, and the cheapest way
for `rb-reconcile` to satisfy it would be to promote `LOG_LEVEL` and `PORT` into
the world model. That is the trade this repository's own guidance names as a
loss: a change that makes the pipeline more likely to produce output while making
a stage's judgment less observable.

The design instead follows the precedent in the **§8 parked table of
`2026-08-06-skill-based-test-generator-design.md`** (referred to below as *the
parked table*, to avoid collision with this document's own §8). Claim utilisation
is not in that table — this is new — but its *shape* has four rows already (seed
conformance, coverage holes, the manifest chain, the negative fixtures'
key-paths). The seed-conformance row's ruling is the one to copy: it declined to
rule on the general case and named the specific indefensible one.

## 2. Change 1 — the zero-utilisation check

`refs.py` already loads every claim id and the world model, so this is
arithmetic over data it holds.

**The check:** for each `01-claims/<artifact_id>.json`, if none of that file's
claim ids appears in any world-model `claims[]` array, report one finding naming
the artifact. Exit 1, one line per zero-utilisation input.

**Why zero and not a threshold.** A percentage is arbitrary and gameable, and
25% would have failed a run whose `rb-reconcile` was behaving correctly. Zero is
indefensible under every reading: a human deliberately registered that input
through `intake`, and either `rb-extract` produced nothing usable from it or
`rb-reconcile` ignored a whole artifact. Neither run would have fired it — the
lowest observed was 8% — so it does not cry wolf.

**It runs only when `01-world-model.json` exists**, so `check-refs` stays clean
at intake and extract, where no world model has been written yet.

Two things to state rather than discover:

- This is the **mirror of an existing check**, not a new kind. `refs.py:437`
  reports a world model citing a claim that does not exist; this reports a claims
  file no world model cites. Same pair, opposite directions.
- It **inherits a parked defect.** `_claim_ids` unions ids into a set, and the
  parked table records that two claims files defining the same claim id merge
  silently. This new check is the first thing that depends on per-file
  attribution, so that parked row becomes load-bearing here. Not introduced by
  this change; recorded as a stated limitation.

## 3. Change 2 — `rb-reconcile` gains one quantified sentence

**The defect, precisely.** P4 failed because a claim was dropped that should not
have been. It was `confidence: high`, `derivation: reverse_engineered`, carried a
JSON Pointer into an observed span, named all six fields of
`cancel_reservation`'s success payload, and quoted the actual `refund_policy`
string. `rb-reconcile` read it and produced four entities, none of them a
cancellation receipt.

Nothing in the prompt was violated. Method step 2 says "**Group** claims into
capabilities, entities, actors, and goals" — an unquantified verb with no
completeness requirement and no obligation to record a decision to decline.

**The contrast that dictates the fix.** Method step 3 says "**For every
capability**, enumerate its outcome classes," and it worked: five capabilities ×
three outcome classes = the 15 cells the run produced. Step 2's unquantified
"group" dropped 130 claims.

But quantified prose is not sufficient on its own, and `rb-extract` proves it:
its Method already says "every statement it makes about the target — every
capability it exposes, every entity it describes…" and it still skipped an entire
section (§4). **Universal quantification works when the set is small, closed, and
already written down.** A stage can check itself against five capabilities it has
just declared. It cannot check itself against every statement in a document.

**The addition**, after Method step 3:

> For every capability you declare, if any claim describes the shape of what that
> capability returns, that shape becomes an entity. A capability whose success
> payload a claim spells out field by field, with no entity modelling it, is a
> response nothing downstream can assert against.

Quantified over capabilities — a closed set of five — not over claims. It targets
P4 exactly and touches none of the 130 correct drops.

## 4. Change 3 — `rb-extract` gains section coverage

**The defect, precisely.** P3 was predicted to surface as a contradiction between
the agent README's `res_12345` and `/tools/list`'s `reservation_abc123`. It could
not: `res_12345` is in `00-inputs/agent-notes-md.md` and appears in **no claims
file**. `rb-reconcile` had nothing to contradict. This was never a reconcile
defect, and blaming it there was the mistake this repository's guidance warns
about — one grep settled it.

What actually happened is worse and more useful. The claims from
`agent-notes-md` carry locators L51…L55, then jump to L84. The gap, L57–L80, is
the entire **Usage Examples** section:

```
Find Italian restaurants in Boston
Check availability at Trattoria di Mare for 4 people on December 25th at 7 PM
Make a reservation at Trattoria di Mare ... Name: Jane Smith, Phone: ...
List all my reservations using email jane@example.com
Cancel reservation res_12345 because plans changed
```

Five canonical user asks — the closest that README comes to stating *goals* — and
`res_12345`. Extract filed a claim for the Apache licence at L187 and for the
Docker build at L143–149, and skipped these.

Two corroborating observations. Three slices produced **exactly 25 claims** —
`agent-graph-py`, `agent-notes-md`, `agent-server-py` — against 47, 20, 18, 17,
17, 16, 15, 15, 14, 13, 12, 8 for the rest; three exact matches out of fifteen
reads as a stopping heuristic rather than coincidence. And the treatment of
illustrative values was **inconsistent across slices**: `tools-list-json` filed
`A reservation is identified by a reservation_id string (e.g. "reservation_abc123")`
while `agent-notes-md` filed nothing for `res_12345`.

So this is not an ambiguity about whether example values are claim-worthy. It is
that extract has no completeness obligation over its own artifact.

**The addition** to `rb-extract`'s Method:

> For a prose artifact, every `##` heading must be cited by at least one claim's
> `evidence.locator`, or your report must say why that section carries nothing
> about the target.

Headings are a small, closed, already-written-down set — §3's condition for
quantification to work.

## 5. Change 4 — a reporting subcommand

`check-refs` is silent at exit 0 (verified), and the exit-code contract reserves
stdout for findings, one per line, at exit 1. So the per-artifact utilisation
table has no home in a gate.

**`rubrica claim-coverage --run <run>`**, always exit 0 on a readable run, exit 2
on an unreadable or misconfigured one. It prints per-artifact utilisation: cited
count, total, percentage. No thresholds, no verdict.

It joins the measurement family rather than the gate family — `compare-gold`,
`diff-runs` and `sample-for-review` are reports, not gates. `rb-orchestrate` adds
it to `invokes` and surfaces its output at **human gate 1**, which is where a
human is already deciding whether the input set was right. An 8% input is
precisely the signal that belongs in that decision.

**Consequence to carry through:** CLAUDE.md's "Twelve deterministic subcommands"
heading and its list become thirteen. `cli.SUBCOMMANDS` and `check-skills` follow
automatically, since the skill contract validates against that list.

## 6. Re-recording, and a documented contradiction resolved by ruling

Changing two skills obliges re-recording under this repository's convention. The
scope splits three ways.

| Artifact | Owner | Collision |
|---|---|---|
| `rb-extract/exercise.md` | change 3 | none — no test reads any `exercise.md` |
| `rb-reconcile/exercise.md` | change 2 | none |
| `tests/fixtures/toy-{gap,contradiction}/recorded/01-world-model.json` | change 2 | **direct** |

**The contradiction.** CLAUDE.md, in the paragraph about those recordings, says
"Changing a skill obliges re-recording, and that re-record is a reviewable diff
rather than silent drift." `tests/unit/test_refusal_fixtures.py`'s
`test_the_recorded_world_model_keeps_its_pre_rubrica_spelling` guards the same
two files and says the opposite: rewriting the `tg-propose` spelling "whether by
a future sweep's sed, or by re-recording — would fabricate evidence… the fix is
`git checkout` of the recording, **never a re-record**."

Both recordings are `rb-reconcile` output and change 2 edits `rb-reconcile`, so
the conflict lands on this work rather than remaining theoretical.

**Ruling (human, 2026-08-12): re-record in place and retire the spelling test.**
CLAUDE.md governs. The guard test is deleted as the losing side of a documented
contradiction, not as an oversight.

Recorded here because the alternatives were considered and declined, and because
a future reader finding refreshed recordings and a deleted test needs to see a
decision rather than infer drift. The two costs, both stated before the ruling:

- The `tg-propose` spelling is the only in-repo marker that those recordings
  predate the rename — 2 occurrences in one file, 3 in the other. Retiring it
  ends that evidence.
- **Four live assertions in `test_refusals_live.py` must survive the
  re-record**: the contradiction still resolving `unresolved`; the gap still
  blocking `propose` with action-named subjects; a malformed-calls gap alone not
  satisfying that test; and the gap fixture acquiring no invented outcome
  classes, with `cells == denominator.capability_cells`. A failure there is
  ambiguous between "change 2 broke refusal detection" and "model variance,"
  which is the ambiguity a recording exists to remove. If any of the four fails,
  **stop and report rather than adjusting the assertion** — the re-record has
  then produced a finding, not a fixture.

## 7. Testing

Every predicate measured in both directions before it is committed, per this
repository's protocol and the nineteen assertions once measured satisfiable by
unrelated content.

**Change 1** — red on a toy run with one claims file's ids removed from every
world-model `claims[]` array; green on the unmodified toy run; green on a run
built to `upto="extract"`, proving it does not fire before a world model exists.

**Changes 2 and 3** — assertions scoped with
`skills.section_body(skill, "Method")`, never `body`, since the frontmatter
`description:` and the contract block satisfy naive substring checks and make
`"refusal" in body.lower()` vacuous for every conforming skill. Each predicate
proved red by deleting the prose in a `/tmp` copy under `RUBRICA_SKILLS_DIR`, and
proved still green after a meaning-preserving rewording — the mirror direction,
because a phrase pin has broken on an innocuous reformat here before.

**Change 4** — exit 0 on a readable run, exit 2 on an unreadable one
(`chmod 000`) and on a bad `RUBRICA_SCHEMA_DIR`, per the rule that a stage defect
must never surface as 2 and a misconfigured run must never surface as 1.

The toy fixture reaches all four changes; no pipeline re-run is needed to
validate them. The re-records in §6 are the only live dispatches.

## 8. Not in scope

- **Gap dispositions.** Raised in the same conversation and deliberately deferred
  until after the next run, so the next run's gaps inform the vocabulary.
- **The 130 uncited claims themselves.** Most are correct drops. Nothing here
  asks `rb-reconcile` to cite more.
- **The `_claim_ids` id-collision defect** (§2). Stated as a limitation; fixing
  it is its own change.
- **Whether `agent-server-py` belongs in an input set at all.** Its 8%
  utilisation is a finding about that input, and change 4 exists to surface such
  findings, not to act on them.
