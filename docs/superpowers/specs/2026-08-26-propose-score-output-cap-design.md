# Bounding the propose/score loop's per-response output

Design for GitHub issue 9, `rb-propose` must re-emit every prior round's
scenarios, so round N fails the 32k output cap.

Status: design approved in conversation, not yet implemented.
Measurements in this document were taken on 2026-08-26 against the surviving
run `runs/run-20260825-094033` and the comparison run
`runs/run-20260823-112746`. The dispatch transcripts and the `/tmp` per-attempt
logs the issue cites were already gone; the runs and their `decisions.md` were
not.

## 1. What was measured

`run-20260825-094033`, the `executive-agent` corpus, sonnet/medium:

| Quantity | Value |
|---|---|
| `01-world-model.json` | 139,283 B, 37 capabilities, 148 capability cells + 22 goals = 170 denominator rows |
| `02-scenarios.json` after round 1 | 18 scenarios, 24,613 B, mean 1,162 B/scenario, max 1,579 |
| `03-coverage/latest.json` | 61,342 B, 151 holes: 86 `not_yet_attempted`, 65 `blocked_by_gap` |
| holes as a share of that document | 35,773 of 59,631 serialized bytes |
| round-1 verdict | `continue` |

`rb-propose` Method step 4 instructs the stage to take every closable hole:
"Take every closable hole in front of you, not only the ones that happen to be
easiest to reach for first." So round 2's assignment was 86 new scenarios.

```
re-emit of round 1        24,613 B
86 new scenarios          99,932 B   (86 x 1,162)
                         ---------
one response             124,545 B   ~ 35,600 output tokens   >  32,000
```

That reproduces the observed failure. Round 1's own first attempt, killed by the
dollar ceiling, had emitted a 43,914-char Write, so a single write of ~44 KB is
not itself the problem.

## 2. Where the issue's diagnosis is wrong, and why it changes the fix

The issue concludes that "the cap does not bind on round count -- it binds on
how large round 1 was, and the boundary lies between those two figures"
(17,669 B and 24,571 B). Against the run it cites as the counter-example:

| | `run-20260823-112746` (cleared round 2) | `run-20260825-094033` (failed) | ratio |
|---|---|---|---|
| round-1 file | 17,669 B | 24,613 B | 1.4x |
| denominator rows | 25 | 170 | 6.8x |
| closable holes after round 1 | 4 | 86 | 21.5x |
| round 2 | +3 scenarios | never wrote | |

Round-1 file size differs by 1.4x. The quantity that differs by 21.5x is the
closable-hole count. The re-emit the issue blames is 24,613 of 124,545 bytes,
20% of round 2's output; the round's own new batch is the other 80%.

So the issue's recommended option 1, a deterministic `append-scenarios` that
removes only the re-emit, leaves 99,932 B ~ 28,600 tokens against a 32,000 cap:
about 11% headroom, before thinking tokens, which count toward the same
ceiling. It removes the minority contributor and leaves the majority
unbounded, on a term that scales with the world model. Shipping it would have
closed the issue without closing the class.

One further correction. The issue lists its option 4, having `rb-score` refuse
`continue`, as "to be rejected" because a model cannot observe an output
ceiling. That is right about a *prompt* refusal and wrong about the check: the
closable-hole count and the mean bytes-per-scenario are both already on disk,
so a deterministic predictor is available. It does not belong in a refusal
condition, and after this design it is not needed, because the batch partition
bounds the work by construction rather than predicting it.

## 3. The invariant this design establishes

**No prompt-written response contains a document whose size grows with the
world model's denominator.**

Section 6 records the one place this invariant is not fully reached, and why.

## 4. Root cause

Two independent exposures, both linear in the denominator:

1. `rb-propose` declares `scenarios` under both `reads` and `writes`, so a
   round's response carries rounds 1..N-1 (grows with rounds) plus this
   round's new scenarios (grows with closable holes). `manifest.limits.
   max_scenarios` is a run-total ceiling; nothing caps a single round.
2. `rb-score` also declares `scenarios` under `writes`, so it re-emits the same
   growing file to apply status transitions. Its coverage document is
   additionally required by its own Output section to be written twice, to
   `03-coverage/round-N.json` and `03-coverage/latest.json`, "with identical
   content". At 170 denominator rows that is ~61 KB per write, ~17.5k tokens,
   55% of the cap, in a stage the issue never mentions.

The 32,000 is not a model limit and not anything this project sets. Verified on
2026-08-26: `CLAUDE_CODE_MAX_OUTPUT_TOKENS` appears nowhere in the repository
and is unset in the environment, so 32,000 is Claude Code's own built-in
default `max_tokens` for the `claude -p` process `dispatch-stage.sh` spawns.
The only record of the number anywhere is the API error string quoted into the
run's `decisions.md`, which is also where the env var's name came from.

That is a finding in its own right, and sharper than "the cap is low": **the
round loop's viability depends on an undeclared default belonging to a tool the
project shells out to.** A Claude Code upgrade could move it in either
direction and nothing here would notice. The issue's phrase for this -- "bounded
by an output-token ceiling nothing in the design declares" -- is exactly right,
and declaring it is the remedy for that half of the problem.

## 5. Design

### 5.1 Propose becomes a bounded fan-out

| Dir | Stage | Runs as | Writes |
|---|---|---|---|
| `02a` | `propose-batches` | code | `02-batches.json` (`batches`) |
| `02b` | `propose` | `rb-propose`, fan-out one member per batch | `02-scenarios/round-N/<batch>.json` (`scenarios-part`) |
| `02c` | `propose-seal` | code | `02-scenarios.json` (`scenarios`) |

`propose-batches` reads the world model and, from round 2 on,
`03-coverage/latest.json`, and partitions the closable holes -- the
`not_yet_attempted` ones only, the other three reasons not being closable by
proposing -- into batches whose projected output stays inside a byte budget.
In round 1 there is no coverage report and every cell and goal is open by
default, which is the same worklist `rb-propose` already constructs for itself
in that case.

Projected bytes per batch = holes in batch x bytes-per-scenario estimate. The
estimate is `DEFAULT_BYTES_PER_SCENARIO = 1600` (the measured max of 1,579,
rounded up) until a sealed `02-scenarios.json` exists, and the actual mean over
the sealed file thereafter, so the partition self-calibrates and stays a
deterministic function of what is on disk.

A new manifest limit `max_scenario_part_bytes` carries the budget, default
28,000 (~8k output tokens). It is a manifest limit rather than a module
constant so `rubrica set-limit` can change it with the reason recorded in
`decisions.md`, which is the treatment `max_scenarios` already gets: this is
the dial that bounds the failure class, so moving it should be a decision on
the record. At the default, this run's 86 holes become 6 batches.

Two consequences, both of which simplify the contract:

**`scenarios` leaves `rb-propose`'s contract on both sides.** A member does not
need prior rounds: a `not_yet_attempted` hole is by definition one no scenario
covers, and `rb-score` is the barrier that folds any duplicate that slips
through. So propose stops reading and writing the accumulating document, which
is precisely what made it a whole-file emitter. `02-scenarios.json` becomes
entirely code-owned -- the same argument that already makes `emit` and both
existing seals code.

Its contract becomes:

```toml
stage = "propose"
reads = ["manifest", "world_model", "batches", "coverage_latest"]
writes = ["scenario_part"]
schemas = ["scenarios-part"]
invokes = ["validate"]
```

**A member reading its own batch out of a shared file is the sanctioned
pattern.** `rb-reconcile-contradict` receives a `subject_id` and reads that
subject's claim list out of `01-subjects.json` itself; `batch_id` is an address
in exactly the same sense. The member is given its `batch_id` and no sibling's,
and never a batch's contents.

That also buys a real layer-2 check: every scenario in part `<batch>` must
target a hole assigned to that batch. This mirrors the triage seal's existing
refusal on "a disposition naming a candidate outside the slice its own part
rules on", and it is the check that makes the partition enforceable rather than
merely instructed.

`propose-seal` assembles `02-scenarios.json` from every round's parts plus
every round's score rulings. It is a pure function of those parts -- it never
reads its own output -- so two runs with identical parts produce a
byte-identical document, which is the property `reconcile-seal` and `emit` exist
to hold.

### 5.2 Score keeps its barrier and sheds the bulk

`rb-score` must stay a barrier: folding duplicates and computing coverage both
need every scenario in one context, which is why it is not fanned out. It can
only write less.

| Dir | Stage | Runs as | Writes |
|---|---|---|---|
| `03a` | `score` | `rb-score`, barrier | `03-score/round-N.json` (`score-part`) |
| `03b` | `score-seal` | code | `02-scenarios.json`, `03-coverage/round-N.json`, `03-coverage/latest.json` |

Score writes one part carrying only its judgments:

- `rulings` -- one entry per scenario whose status changes, with
  `duplicate_of` on a fold and `rejected_reason` on a rejection. Measured
  against this run: 17 rulings, under 2 KB, replacing a 24,613 B re-emit.
- `holes` -- one entry per uncovered row, with `reason`, `justification` and
  `gap_id`. This is genuine judgment and stays with the prompt.
- `verdict` -- score computes the coverage verdict; only the orchestrator acts
  on it. Unchanged.

`score-seal` then, in code: applies the rulings through the same shared
assembly `propose-seal` uses; computes both matrices and `progress`; composes
`03-coverage/round-N.json` from those plus score's holes and verdict; and
publishes `03-coverage/latest.json` as a copy.

**Why the matrices move to code, and why that is not a loss of judgment.**
`rb-score`'s Method already specifies both matrices as pure functions of the
world model and the scenario list, leaving nothing for a model to decide:

- capability matrix: one cell per (capability, outcome class) pair enumerated
  from the world model; `scenario_ids` are the scenarios whose
  `capability_refs` name that cell; `covered` is true iff at least one of them
  is `proposed` or `active`.
- goal matrix: one row per goal; `hop_depths_expected` is *copied* from that
  goal's `expected_hop_depths`, which `world-model-0.1.json` requires;
  `hop_depths_present` is the set of `hop_depth` values over that row's live
  scenarios; `covered` is true iff the row has a live scenario and every
  expected depth is present.
- `covered`, `total`, `pct`: arithmetic over the rows.

`refs.py` already contains this logic in checker form -- `_cells`,
`_check_matrix_arithmetic`, and `check_coverage` recomputing
`hop_depths_present` -- and `rb-score`'s own prose points at those checkers to
tell the stage its arithmetic is "a checkable claim about your own output
rather than a summary you are trusted on". So this change deletes a
transcription step that a checker already exists to police, and removes the
failure mode that section's warning names: a percentage that disagrees with the
matrix beneath it. What remains in score's output is judgment only.

`score-seal` refuses before writing, rather than assembling something a human
would read as coherent, on the narrow class where assembly cannot faithfully
represent what it was handed -- a part absent or unparseable, a ruling naming
an unknown scenario, an uncovered row with no hole, a hole naming a covered
row. That is the door `seal.py` already documents for triage, and the same
reasoning applies: `check_coverage` reports after the fact against whatever it
was handed, while the seal can refuse before the write.

### 5.3 Harness parameter and the destroyed evidence

- Set `CLAUDE_CODE_MAX_OUTPUT_TOKENS` explicitly in
  `scripts/dispatch-stage.sh`, in the style of the sandbox and WebSearch
  comments already in that file. The point is not headroom, it is **turning an
  undeclared dependency into a declared one**: today the ceiling is a default
  inside another tool, so the value the loop actually ran under is not
  recoverable from the repository at any later date.

  **The value is owed a measurement before it is chosen.** The effective cap is
  presumably `min(env var, model max)`, and neither term is established here:
  whether this Claude Code version honours an arbitrary value for that env var
  is untested, and `--model sonnet` resolves to a specific sonnet whose own API
  output ceiling fixes the second term. Establishing both is cheap -- one
  dispatch with the var set high and a deliberately large write -- and must
  happen before a number is written into the script, so that the comment
  records a measurement rather than an assumption. Do not carry the 128K figure
  from the API documentation into the script as though it had been observed
  through Claude Code.

  Either way this is margin on top of the structural bound, never the fix: the
  growth is what the design in section 5 removes.
- `TRANSCRIPT="$LAB/transcripts/$STAGE${SLICE:+-$SLICE}.jsonl"` is named by
  stage, not round, so round 2's transcript overwrote round 1's and destroyed
  the primary evidence for this issue. Fix by never overwriting: suffix on
  collision. The script does not know the round and does not need to; "do not
  destroy the prior attempt" is the whole requirement.

## 6. What stays unbounded, stated plainly

After this change, score's remaining write is its holes: one justification per
uncovered row, measured at 35,773 B (~10k tokens) at 170 denominator rows.
That is a 4x reduction from the ~147 KB a score dispatch emits today, and it
fits comfortably. **It is still linear in the denominator.** A target roughly
3x this one re-approaches the cap even with the raised harness ceiling.

It is left linear deliberately. A hole's `reason` and `justification` are
judgment, so they cannot move to code; and bounding them would mean sharding
score, which would break the barrier property that lets it fold duplicates at
all. Sharding score was considered and rejected for that reason.

This belongs in `docs/design/limitations.md` as an entry with these figures and
that ruling, so the next person to hit an output cap in this loop finds the
arithmetic rather than re-deriving it.

## 7. Change surface

Code:

- `src/rubrica/rounds.py`, new: the batch partition, the shared scenarios
  assembly, the matrix computation, and the coverage composition. One module
  because the loop's determinism is one concern.
- `paths.STAGES`: `propose-batches`, `propose`, `propose-seal`, `score`,
  `score-seal`, in that order.
- `paths.RunPaths`: `batches`, `scenario_parts_dir`, `scenario_part(round,
  batch)`, `score_parts_dir`, `score_part(round)`, plus the id-listing
  accessors the fan-out and the seals need. Unsafe-segment handling follows
  `contradiction_part` and `disposition_part`.
- `validate.ARTIFACT_SCHEMAS` and three new schemas: `batches-0.1.json`,
  `scenarios-part-0.1.json`, `score-part-0.1.json`. Each `$ref`s the existing
  `scenarios-0.1.json` and `coverage-0.1.json` `$defs` rather than restating a
  scenario, a ruling or a hole, as the triage and reconcile part schemas
  already do.
- `validate.STAGE_ARTIFACTS`: entries for the three new stages. `propose` moves
  from `scenarios` to `scenarios-part`; `score` from `coverage` to
  `score-part`; `score-seal` owns `coverage`.
- `manifest-0.1.json` and `refs.check_limits`: `max_scenario_part_bytes`.
- `refs.py`: `check_batches`, `check_scenario_parts` (including the
  own-batch-only check), `check_score_parts`, all folded into `check_all`.
  `check_scenario_parts` and `check_score_parts` report every missing slice
  from the moment their directory exists, so they run only once the fan-out has
  finished -- the property `check_verdicts` and `check_contradiction_parts`
  already have.
- `cli.SUBCOMMANDS`: `propose-batches`, `propose-seal`, `score-seal`. Test the
  unreadable-input paths, not just the happy path, per the exit-code contract.

Skills:

- `rb-propose/SKILL.md`: contract as in 5.1, and all five mandatory sections
  rewritten for a fan-out member that writes only its own batch.
- `rb-score/SKILL.md`: writes `score_part`, no scenarios re-emit, no matrices,
  single document. Its Output section's "written twice ... with identical
  content" instruction goes away, as does the `mkdir` warning attached to it,
  since code now creates `03-coverage/`.
- `rb-orchestrate/SKILL.md`: the loop is now five stages per round, with the
  fan-out capped at 3 concurrent members per the gateway note in the user's
  global instructions.
- `rb-propose/exercise.md` and `rb-score/exercise.md` record dispatches of the
  shape this change replaces. Keep each where it is and add a `SUPERSEDED.md`
  saying which stage shape it recorded and why it was neither relocated nor
  rewritten -- the `rb-reconcile/` precedent exactly. Re-recording against the
  new shape is deferred, which leaves propose and score without behavioural
  evidence for their new shape; the limitations entry must say so, since that
  is now true of them as well as of both staged families.

Fixtures and tests:

- `tests/toy.py`: build the new parts, and grow `_UPTO_STAGES`. Add a
  checkpoint only where something consumes it.
- A test that the partition holds every batch inside the budget, including the
  degenerate cases: zero closable holes, and one hole whose own projection
  already exceeds the budget.
- A test that two runs with identical parts produce a byte-identical
  `02-scenarios.json`, and the same for the composed coverage document.
- Any new prompt-level predicate measured in both directions before commit --
  blank the prose in a `/tmp` copy under `RUBRICA_SKILLS_DIR` and watch it go
  red, then reword meaning-preservingly and watch it stay green -- and scoped
  with `skills.section_body`, never a bare substring over `body`.

Docs:

- `docs/concepts/pipeline.md`, `docs/reference/cli.md`,
  `docs/reference/artifacts.md`: the three stages, the three subcommands, the
  three artifact kinds. `tests/unit/test_docs_accuracy.py` fails until each is
  named.
- `scripts/render-pipeline-diagram.py` `ROWS` plus a re-render;
  `scripts/render-readme-diagram.py` `PHASES` must gain the three new stage
  names in the phase that already holds propose and score, plus a re-render.
  Both committed drawings are byte-compared, and neither may be hand-edited.
- `CLAUDE.md`: the stage table, the "one architectural rule" fan-out paragraph
  (a third slice-id kind, `batch_id`), and the list of stages that are code.
- `docs/design/limitations.md`: the entry from section 6.

## 8. Verification

`make test` green, `make check` clean, `uv run rubrica check-skills` exit 0 --
the three gates. Plus both diagrams re-rendered and byte-identical to a fresh
render, and the unreadable-input paths exercised for every new subcommand
(`chmod 000`, `chmod 0444`, a bad `RUBRICA_SCHEMA_DIR`) to hold the exit-code
contract: a stage defect must never surface as `2`, and a `1` must never have
empty stdout or name the wrong artifact.

The change is not verifiable end to end without a real corpus: the toy fixture
cannot reach this class, because re-emitting its scenario set was always cheap.
That is why the exercise re-record is a deferred, tracked expense rather than
something this change can claim.

## 9. Alternatives rejected

- **Deterministic `append-scenarios` alone**, the issue's own lean. Measured to
  leave ~11% headroom before thinking tokens, on a term that grows with the
  denominator. Section 2.
- **Raising `CLAUDE_CODE_MAX_OUTPUT_TOKENS` alone.** Removes nothing: the
  growth stays linear in the denominator, and the amount of headroom it buys is
  not yet measured (5.3). Kept as a declaration of an undeclared dependency,
  not as the fix.
- **A refusal condition in `rb-score` for "another round will not fit".** The
  condition is detectable from artifacts, but a deterministic partition removes
  the need to predict at all, and `CLAUDE.md` treats a refusal whose trigger a
  model cannot act on as decorative.
- **Sharding score's holes.** Would break the barrier that lets score fold
  duplicates. Section 6.
