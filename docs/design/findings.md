# Findings

Defects that were found, measured, and fixed. Each entry is the finding a
comment or a document elsewhere in this tree cites: the citation names the
finding, and this file is where the measurement behind it lives.

This is not [`limitations.md`](limitations.md), and the difference decides which
file an entry belongs in. `limitations.md` holds what is **known to be wrong or
missing**, each entry with the ruling that parked it. Everything here is
**closed**. A fixed finding filed among the parked defects would be read as
still open, which is a difference a reader would act on.

Entries carry the finding's name, what was measured, and what changed. They do
not carry issue numbers: this project's history lived in an internal tracker
whose numbers do not survive into this repository, where the same number means
a different, unrelated issue. Where an entry's own measurement was constructed,
projected or later corrected, it says so — several were, and the distinction
between what somebody ran and what somebody computed is the whole value of the
record.

## The unnamed disposition key

**What was measured.** `rb-triage`'s `SKILL.md` documented the `dispositions[]`
block at length and never named the `disposition` key its schema required —
`grep -nE '`disposition`|"disposition"'` over the file returned nothing, while
`triage-0.1.json` still required it. Three consecutive dispatches at defaults
over the same 41-candidate corpus all wrote `verdict` instead; the report calls
that out as not sampling noise. `validate --stage triage` emitted 82 findings
over the 41 entries and `check-refs` 20 more, two of which were false — the two
container candidates named in them had been correctly declined. The worst
symptom was gate 0, which rendered "objective supported: yes" over zero admits
and zero declines and exited 0.

**What changed.** Fixed in `b596a69`. The monolithic stage had been split by
then, and the paragraph had moved into `rb-triage-rule/SKILL.md` verbatim,
omission included; §2 there now states the required key set, names `disposition`
as the ruling field with both its literal values, and records the three-dispatch
measurement as the reason it is spelled out. Two predicates scoped to §2 assert a
**key-position** mention rather than the bare word, since the bare word was
already everywhere in prose that left the key unnamed. The sweep the report asked
for found one sibling in the same commit — `rb-triage-objective` never named
`surfaces` — and left four other reports open, each needing a per-field ruling on
whether the prompt authors the key at all.

## The untriageable catalogue

**What was measured.** On the `parsec` corpus, `survey` produced a
`00-catalogue.json` of 595KB / 14,055 lines / 351 candidates that passed
`validate --stage survey` and `check-refs` cleanly and that `rb-triage` could not
rule on within its dispatch budget. Three dispatches produced no
`00-triage.json`: two died during context compaction, still at line 9,100 of
14,055 after 29 chunked `Read`s, and one exhausted the whole $2 budget
(`error_max_budget_usd`, 34 turns, $2.19, ~17 minutes, 2.0M cache-read tokens).
The blocking limit was the dispatched stage's context window, not any cap
rubrica enforces: `--max-candidates` (500) and `--max-catalogue-bytes` (1MiB)
both passed, and the 256KB per-`Read` ceiling is outside rubrica. Because
`canonical_bytes` sorts keys, `candidates` sorts first and the metadata a stage
needs to situate its work lands in the last 0.1% of the file — `run_id` at byte
608,766 — so much of the spend went to locating metadata rather than judging
candidates. The two compaction runs' token figures were read at the time and are
not re-derivable from disk; the budget-exhaustion figures come from that run's
own result event.

**What changed.** Merged at `2d77942`, after the `triage-*` family had already
sharded the candidate list so that each member reads one holdable shard.
`rb-triage-objective` was the last pass reading the whole catalogue and its
contract became `reads = ["slices"]`, with `request`, `policy`, the exclusion
tally and each candidate's own source bytes carried on `00-slices.json` as a
`catalogue_facts` block that `triage-slices` writes and `refs.check_slices`
recomputes from the catalogue. On this issue's own corpus the objective
dispatch's input measured **472,799 bytes down to 51,792**, 9.13x, inside the
harness's whole-file `Read` refusal where the catalogue was not; a re-run during
the work measured 480,399 to 52,542, and the ratio held while the absolutes
moved. Reordering the catalogue was rejected on measurement rather than risk, and
`canonical_bytes` was not touched. Two things the closure records rather than
claims: **no staged run has been observed writing `00-triage.json` on the corpus
that killed the monolith**, and the plan costs 116.9–118.6 bytes per candidate,
so raising `--max-candidates` into the low thousands reopens the finding on the
artifact that closed it.

## The chat-trajectory skeletons

**What was measured.** A corpus of 200 OpenAI-style chat trajectories from
`tau2-bench` — 4.5MB of agent behaviour — reached triage as opaque rows: 443
candidates, a 428KB catalogue, zero container elements, and 200 candidates
classified `other` carrying skeleton-only digests with no tool names, no request
text and no status. Two content-shape assumptions caused it: the per-file key
intersection across chat messages is `{role}`, below
`survey.EXPLODE_MIN_COMMON_KEYS = 3`, and `classify_payload` calls a payload a
`trace` only on `spans` or `trace_id`. Two numbers in the report were qualified
at closure. The 5,425-candidate / ~2.9MB figure for what explosion would have
produced is arithmetic over what `explode` would yield, stated in the report
itself as a computed figure and not an observed survey run. And the digests were
not "mutually indistinguishable" as first written: they are **39 distinct**,
largest identical group 18, differing by message count — corrected in
`limitations.md` too, which had repeated the stronger claim.

**What changed.** Fixed at `06f9d40`. Neither lever the report proposed was
used, and both were measured wrong: `EXPLODE_MIN_COMMON_KEYS = 2` explodes 0 of
200 files, because 895 of the 5,182 messages carry `{role, tool_calls}` and no
`content`; and digesting the message elements as traces fires zero heuristics on
4,267 of 5,182 at a mean 39 bytes, thinner than the skeleton it would replace.
The cause was one guard — `digest_for_payload`'s trace branch tested
`isinstance(payload, dict)`, so a message *list* could never reach it however it
was classified. `digest.is_message_list` now recognises the shape, a second
producer digests it, and `intake.classify` routes it to the existing `trace`
kind. Measured after: 443 candidates unchanged, catalogue 444,355 → 472,799
bytes, 7 slices, all 200 firing `[element_counts, request_text, names]`, yielding
14 distinct tool names and 68 distinct toolset signatures. Two further defects
were fixed in the same round: `survey.explode` was splitting a metadata-rich
trajectory per turn, and `_has_error_key` read `error: False` as an error, firing
on 200 of 200 episodes. What the fix does not reach is in `limitations.md`: a
chat trajectory cannot say whether it succeeded, because `reward` lives in the
sibling `simulations` record and not in the projection, so near-duplicate ruling
over such a corpus remains unsound.

## The fan-out output directory

**What was measured.** Dispatching `rb-triage-rule` for the only slice of a fresh
41-candidate run burned ~7 turns and ~4 minutes without writing
`00-dispositions/s01.json`. After reading its two contract files the member's
first act was to create its own output directory: `mkdir -p` landed on an
approval prompt `claude -p` cannot answer, followed by a malformed tool call and
a `dangerouslyDisableSandbox` escalation attempt. `00-dispositions/` is the only
fan-out output directory whose sibling is created in code — `triage-slices`
mkdirs `00-slices/` at `slices.py:613` — so "the directory my sibling artifact
lives in already exists" is a reasonable inference for a member to make, and it
is wrong. The report is explicit about the limit of its own evidence: the
dispatch was killed during the stall that followed, so it cannot claim the stage
would not have recovered on the next turn, and the cost was turns, budget and an
escalation attempt rather than a dead run. That `Write` creates parent
directories was confirmed independently — nothing in `src/rubrica/` calls
`claims_dir.mkdir`, yet an `rb-extract` fan-out's `Write` had populated one.

**What changed.** Fixed at `631995c`, by the second of the two options the report
offered: a paragraph in the `## 2. Output` section of all six skills whose stage
writes into a directory, stating that the directory does not exist at dispatch,
that the member's own `Write` creates it parents-and-all, and that `mkdir` is not
to be reached for. The suggested one-liner beside `slices.py:613` was rejected on
measurement: three checkers key on `.is_dir()` to distinguish "fan-out not
started" from "fan-out in progress", so on the toy run pre-creating
`00-dispositions/` moves `check-refs` from 0 findings to 1 and pre-creating
`01-contradictions/` from 0 to 6, one per subject. Widening the Bash allowlist
was rejected for the reason the report already gave. The sibling exposure the
report did not name — `01-contradictions/`, which no dispatch had ever created,
so it was unmeasured rather than clean — carries the same paragraph.
`tests/unit/test_skills_output_dirs.py` pins the absent-directory premise and the
prose together, so neither can drift alone.

## The read-coverage variance

**What was measured.** The three reconcile passes that own structured `claims[]`
arrays were re-dispatched over a **byte-identical run directory** — same skill,
same model, same effort, no appended findings — on a run of 23 admitted inputs
and 434 claims. Distinct `01-claims/*.json` files each pass opened, run 1 against
run 2: `rb-reconcile-capabilities` 12/23 then 23/23, `rb-reconcile-entities`
10/23 then 13/23, `rb-reconcile-goals` 9/23 then **3/23**. One pass went to full
coverage, one improved slightly, one got materially worse; both dispatches
reported success and both passed `validate` at exit 0. Downstream, claim
utilisation moved 80/434 (18.4%) to 146/434 (33.6%) with the world model's
element counts byte-for-byte identical. The correlation that identifies read
coverage as the cause is exact: in run 1, of the claims in files the citing
passes read, 80 of 212 were cited (37.7%); of the claims in files they never
opened, **0 of 167**. Two adjacent defects were found alongside it: 55 of the 434
claims were `invariant` claims that no citation could reach, because
`$defs/invariant` had no `claims` property, and 38 more were cited only in prose
that the counter does not walk.

**What changed.** Fixed in `b150248..93e82a2`. `claims` became required with
`minItems: 1` on `$defs/invariant`, `$defs/outcome_class` **and `$defs/gap`** —
the third one the report did not name — which closed the uncitable case for 117
of the 434 claims and made the prose citations structural rather than
regex-counted. A new `inputs_seen` row, required on the four partials whose
passes own a claim kind, carries each input's own-kind claim total, how many were
cited, how many dropped and a note required whenever anything was dropped, and
`refs.check_input_dispositions` recomputes every number from the files it
describes. `gate-brief --gate 1` now reports coverage per pass with the drop rows
and their notes, which is the surface that would have made run 1 unmissable: the
aggregate read 33.6% while the capabilities pass cited 110/135 of its own kind
and the goals pass 2/38. Three corrections to the framing are on the record. A
declared `read_artifacts[]` list was rejected as prose about a pass's own
compliance. The claim that `own_kind_total` is a figure a pass cannot state for a
file it never opened is **false**, and the shipped code and docs say so — three
routes yield a correct count without a read — so the shipped property is
recomputability, and what the change delivers is **visibility, not forcing**. And
no dispatch has tested any of it: the premise that an output obligation changes
read behaviour where an exhortation did not rests on a measurement nobody has
taken.

## The uncapped digest names

**What was measured.** `digest`'s `names` field was capped at 64 **entries** by
`_MAX_NAMES` and bounded in no way at all in characters, so one verbose name
could produce a candidate row larger than the slice that has to hold it.
End-to-end, a two-message conversation whose `name` values are 40,000 characters
each surveyed to `error: 1 candidate row(s) exceed one slice of 65536 bytes:
chat-json at 80549 bytes`, exit 2 refusing the whole corpus, where the same file
digested as a skeleton is 433 bytes. The report states the standing of that
figure plainly: it is measured on a **constructed** payload, not on a real
corpus, and no corpus surveyed so far has tool names long enough to trip it —
tau2's are ordinary identifiers such as `get_reservation_details`. So this was a
reachable failure mode rather than an observed one, which is the same standing
the already-fixed role-key bound had before it was fixed.

**What changed.** Fixed at `1029d5a`, taking the `_MAX_ROLE_CHARS` remedy rather
than inventing a second pattern. `_MAX_NAME_CHARS = 128` is justified against the
real vocabulary rather than against the slice cap — the longest name in any
corpus on that pod was `query_tickets.find_tickets` at 26 characters — so
64 × 128 = 8,192 bytes is the field's worst case, an eighth of one slice, and
`names` can no longer be why a row is refused. A `names_truncated` flag is set at
the moment a name is actually cut rather than re-derived from a width comparison,
emitted as a sibling of the field so a candidate carrying no names grows no flag
about names it does not have. It is applied in `_collect_names`, the shared
collector, so both producers get it — the dict-shaped route had always been
exposed and the message-list route was one more way in. `rb-triage-rule` gained a
paragraph on reading the flag, because it is the one flag there that can make a
digest carry fewer entries than the candidate has tools. The collision
consequence is stated as a possibility rather than a certainty: `names` is a set,
so two names differing only past the cap collapse to one entry.

## The digest over-read

**What was measured.** `rb-triage-objective`'s contract was
`reads = ["slices", "catalogue"]`, so on the `parsec` run it had to open all
585,261 bytes of `00-catalogue.json` to use 26,288 of them (4.5%) — while
365,385 bytes, **62.4%**, are the candidate `digest` objects its own §1 forbids
it to read in bold. It succeeded, at **$1.84 of the $2 default budget**, 23
turns, 14.7 minutes and 1.2M cache-read tokens, against a $0.45 median for a
fan-out member reading one shard; the cost figures are from the dispatch's own
result event and not estimated. Ten of its fifteen Bash calls touched the
catalogue, reconstructing the `candidate_id` → `bytes` map by hand and seeking
for tail metadata that `sort_keys=True` puts at the far end (`run_id` at byte
585,200) — while `00-slices.json`, which the pass already read, carries the same
`run_id` at byte ~50. Every gate exits 0 and the pass's verdict was sound: the
finding is what the correct answer cost.

**What changed.** Fixed on `main` by the `catalogue_facts` work, taking the
report's preferred direction rather than its sidecar fallback. `4a22ef4` carries
the facts the pass needs on `00-slices.json`, including
`catalogue_facts.candidate_bytes` — each candidate's own source bytes, copied by
`triage-slices` and never recomputed, so `refs.check_objective`'s recomputation
from the catalogue cannot disagree with the pass's arithmetic — plus `request`,
`policy` and `excluded` in the block's header. `f6b0c96` drops `catalogue` from
the pass's `reads`, leaving `reads = ["slices"]`, and `5ba0e33` carries the
narrowing into the prose beside it so §1 and the contract agree.
`canonical_bytes` was not touched. Lowering `max_catalogue_bytes` was named as
not the fix, since it rejects a corpus rather than triaging it. The report's
secondary finding — the dispatch wrote `compute_weights.py` into the run
directory — was not fixed here and was re-filed rather than left in a closed
issue; it is [the unfiltered stray write](#the-unfiltered-stray-write).

## The unfiltered stray write

**What was measured.** A stage may write a non-artifact into the run directory,
and the one mechanism that looks for unmanaged files filters it out by name.
`rb-triage-objective`'s contract is `writes = ["objective"]`, and the dispatch
above also wrote `compute_weights.py` into the run root. Both check layers are
indifferent to it: on a toy run with the file hand-placed at the run root,
`check-refs` and `validate` over four stages returned identical results before
and after — the two exit-1 rows are the default toy build stopping short of
`emit` and are the same in both columns, so the invariant measured is that
nothing changes. `summary.orphaned_temp_files` walks the run root and keeps
`p.name` where `".tmp." in p.name`, so on the same run
a `01-world-model.json.tmp.9999` stray is named on `run-summary.html` and
`compute_weights.py` is not, at zero occurrences. Two caveats the report states:
everything under its own Measured heading was measured on a toy run with a
hand-placed file rather than a dispatch that produced one, and the
`compute_weights.py` observation is the other report's, read from it rather than
re-observed.

**What changed.** Fixed at `71fc8af`, by the first of the three options — the
ruling that a stage's `writes` is the whole truth about what appears in the run,
with the sandbox scope rather than prose holding it there.
`scripts/stage-write-scope.py` resolves the contract's `writes` to concrete paths
and `dispatch-stage.sh` grants exactly those in place of `Write(/$RUN/**)`, so an
`extract` member working on one input now gets `Write` and `Edit` on its own
claims file and nothing else — which makes the grant enforce the fan-out
isolation rule as well as the artifact one. A resolution that reaches the run
root is refused rather than granted, a failure to resolve is fatal rather than
falling back to the old grant, and `Read` stays run-wide because a stage reads
widely by design. `orphaned_temp_files` was deliberately **not** widened: that
was option 3, and the function's own docstring argues against putting a file on
the page nothing else in the run reacts to. **No real dispatch has been run
against the new grant** — it is verified structurally, over the settings file the
harness writes for every dispatchable stage.

## The undrivable denominator

**What was measured.** `denominator.capability_cells` is the coverage denominator
the whole experiment is scored against, and `reconcile-seal` computed it over
every capability × outcome-class pair without consulting `binding`. On a
reservation-service run: 24 capabilities, 5 of them tool-bound, 56 cells, of
which **37 (66%) sat on capabilities with no tool binding** — capabilities
`emit.bindings` drops outright, so no scenario can drive them. The 19 unbound
capabilities were largely not behaviours of the target: one rests on a line in
`pyproject.toml`, one has a single `underspecified` class saying nothing
addresses it, one describes a `docker build`. The previous run on the same corpus
had 5 capabilities, all bound, a 20-cell denominator in which every cell was
drivable, and scored 55% (11/20). No gate catches it — `binding` is not in the
capability schema's `required` list, `refs.check_world_model` recomputes the
field and so agrees with whatever cells exist, and the only code consulting
`binding` is `emit.py` at stage 06, after gates 1, 2 and 3 have passed. The
report is explicit that this is one run against one prior run and not a
controlled experiment: the two admitted 26 versus 23 inputs.

**What changed.** Fixed in `d2942f3..4c9fa10`. `refs.drivable_cells` was added
**beside** `refs._cells`, and the four numbers that disagreed now agree — on that
run `denominator.capability_cells` 56 → 19, `capability_matrix.total` 56 → 19,
both rounds' worklists 56 → 19, and `sizing.implied_size` 87 → 38. Undrivable
cells are not dropped from the report: `score-seal` injects one mechanical
`unreachable` hole per undrivable cell, so matrix-plus-holes still accounts for
all 56, and `gate-brief --gate 1` lists the excluded capabilities with their
operation, citing inputs and remedy. Three specifics in the report did not
survive measurement. Narrowing `refs._cells` itself, as it suggested, would have
fabricated findings against correct scenarios, batch plans and matrices, because
that function is a reference resolver rather than the denominator's arithmetic.
`denominator.version` is a per-run amendment counter tied to a recorded
orchestrator decision, so it stays at 1, and nothing in the repository compares
the field across runs anyway. And the defect predates the accounting commits the
report suspected: an earlier run already carried 9 unbound capabilities
contributing 36 of 148 cells, so the class is structural while the magnitude on
that corpus is accounting-driven. Two residues are recorded rather than absorbed:
`rb-score`'s new binding-conditional prose is **dispatch-unvalidated**, and
`binding.tool` is a lossy proxy — of the 37 excluded cells, 29 are correctly
excluded and 8 are real agent-level behaviour the `{tool, fixed_args}` shape
cannot express.

## The enumeration deadlock

**What was measured.** `rb-reconcile-subjects`, dispatched over a 206-input run,
spent **38 turns and $3.72** trying to list `01-claims/` and never began its
actual work, then refused rather than write an artifact it could not stand
behind. Every command it attempted was a variant of enumerating the directory,
and three routes were closed at once: Bash `ls`/`find`, a `Read` on the directory
(`EISDIR`), and the sandbox escalation. The dispatch's own result event reads
`num_turns: 38`, `total_cost_usd: 3.716`, `subtype: success`, `is_error: false` —
so **nothing in the run's exit codes marked it**, and the absent artifact was the
only signal. The name of this finding records the state that was observed; the
report's diagnosis of its cause was then measured wrong. Three dispatches
replicating the harness's exact flags, ~$0.49 in total, found that `ls` and
`find` succeed **both** with the sandbox live and with no sandbox block at all,
and fail in exactly one state: a sandbox configured that `bwrap` cannot engage,
where every Bash command dies at the `bwrap` layer, `rubrica validate` and
`check-refs` included. Read-only Bash is auto-approved with no sandbox block
present, so the allowlist was never the constraint. `Glob` and `Grep` appear in
no configuration's toolset. And `bwrap --unshare-all --dev-bind / / true` without
`--proc` still succeeds, which is how the pod fault stayed hidden through seven
triage transcripts.

**What changed.** Fixed at `930230f`. `scripts/dispatch-stage.sh` now probes
`bwrap --unshare-all --dev-bind / / --proc /proc true` before writing the sandbox
block; when it fails the block is dropped, the reason goes to stderr, the probe's
output is kept under `$RUBRICA_LAB`, and the closing summary records
`sandbox off -- <reason>` beside the cost. `RUBRICA_REQUIRE_SANDBOX=1` refuses
with exit 2 instead of falling back, for a measured run where losing the layer
silently is worse than not running. The `--proc` in the probe is not optional: it
is the mount that fails, and omitting it is what let a smoke test pass on a pod
where the sandbox cannot work. The report's own suggested direction — deriving
the claims file list from `manifest.inputs[].artifact_id` — was **not**
implemented, because the enumeration route was never missing and it would have
made the manifest authoritative over `01-claims/` for nothing in return; no
barrier skill's prose changed. Two things this surfaced are in `limitations.md`
rather than closed: the absent `Glob` and `Grep` tools, whose cause is not
established, and the exit-0-with-no-artifact hole, where an honest refusal is
indistinguishable from a clean success from outside the run.

## The silent fan-out gap

**What was measured.** A fan-out member that writes no slice — because it
refused, died or was killed — passes both check layers while its siblings write
theirs. On a toy run stopped at `extract` with one of three claims files removed,
`validate --stage extract` and `check-refs` both exit 0; with `01-claims/` absent
entirely, `validate` exits 1 and names the stage. The hole is that
`validate._artifact_paths` enumerates the files that exist rather than the files
that should. It does not stay silent: left to run on, the same missing member
produced 15 `check-refs` findings once the reconcile family had read
`01-claims/`, every one of them naming an artifact whose only fault is citing a
claim nobody extracted — a live instance of the class `CLAUDE.md` records as
having already cost this project a fix round, since the repair those findings
suggest is to the reconcile partials and re-dispatching every one changes
nothing.

**What changed.** Fixed at `b41fff1` and `8fc17a7`. `refs.check_manifest` now
checks the manifest-to-claims relation in **both** directions: a registered input
with no claims file is reported against `01-claims/`, guarded on that directory
existing exactly as the sibling fan-out checkers guard theirs, and the message
says every registered input needs one even where nothing could be extracted,
because `rb-extract`'s own refusal condition is to write an empty `claims` array.
Completeness stayed in code rather than moving to `rb-orchestrate`, on the
precedent of the sibling fan-outs, and layer 1 was left alone: enumerating what
exists is correct for one-schema-per-artifact, and completeness needs the
manifest. Verifying the scope turned up the same defect in the `instantiate`
fan-out, where removing one `active` scenario's directory from `04-instances/`
left both layers at 0 and compounded worse — `check_verdicts`, `check_suite` and
`emit` all derive their populations from what is on disk, so a dropped scenario
reached an emitted suite one test short with nothing reporting it.
`refs.check_instances` now reports it, with `rejected` excluded from the
population for two prescribed reasons. `extract` and `propose` both now run
`check-refs`. On a full toy run missing one claims file the new finding is
**first** of 25, the 24 after it being the sibling-blaming misdirection.
`triage-rule` is a fourth instance of the class and was left for a separate
decision.

## The gap about the run

**What was measured.** On `run-20260907-065440` (tau2-retail), six singleton
reconcile passes were dispatched concurrently ahead of inputs that were not yet
on disk — a sequencing mistake in the dispatch rather than a stage defect, and
the point of the report is what each pass did with the same bad condition.
`rb-reconcile-outcomes` and `rb-reconcile-entities` **refused**, each naming
the missing `01-capabilities.json`. `rb-reconcile-gaps`, under the identical
condition, wrote `gap-prior-pass-partials-absent` with `subject: pipeline:` and
six stages in `blocks` — which is the orchestrator's blocking-halt trigger —
and the run stopped. The gap was **true when it was written** and false by the
time anybody could read it: all four partials it named were present and the
world model had sealed. Neither check layer reaches that, because the gap is
schema-valid, its `blocks` entries are real stage names, and `check-refs` has
nothing to compare prose about the filesystem against. The recorded cost is a
re-dispatch of the gaps pass and a fresh gate evaluation before the run could
proceed at all. The pass had not misread its skill: §5 said a defect the audit
finds in an earlier artifact is recorded as a gap, and an absent artifact is a
defect by any reading.

**What changed.** Fixed across `3d9d673`, `fcd94c2` and `a112f60`. A `gaps`
entry is now stated to be about the target and never about the run, and the
rule is located on what a gap asserts `unknown` rather than on `subject` — the
first draft pinned it to `subject` and had to be corrected out twice, because
§3 step 3 legitimately requires an audit gap's `subject` to name the artifact
and element it found wrong. `rb-reconcile-gaps` carries the split in **both**
sections, since §3 is the procedure and §5 only the exception list, and the
undifferentiated §3 sentence is the one the measured run actually obeyed. All
eight passes of the family now carry the same missing-input refusal worded
identically, with `tests/unit/test_skills_reconcile_family.py` holding the
byte-identity, since a `SKILL.md` has no include mechanism. The issue's third
suggestion — a schema constraint forbidding `blocks` on a gap with no target
subject — was rejected rather than parked: `subject` is prose, so such a check
would be deciding whether a subject is *about* the target. Two things the
closure records rather than claims: the fix is prompt-level, so it **buys a
probability rather than a guarantee**, and it was verified structurally — every
predicate measured in both directions under `RUBRICA_SKILLS_DIR`, with **no
dispatch of the amended prose on record** either way.

## The unrecordable understatement

**What was measured.** The challenge verdict's `flags` enum had exactly one
member, `difficulty_overstated`, computed as `found < hop`. The opposite
relation had no flag and no computation, so an adversary that measured a
scenario as *harder* than declared had only free-text `notes`, which no report
reads. Measured on `run-20260907-065438` (reservation-service), scenario
`sc-r1-b01-05`: `rb-challenge` returned `re-seed` **twice**, before and after a
re-instantiate, with `minimum_tool_calls_found: 2` against a declared
`hop_depth: 1`, and wrote the direction into prose while saying in the same
sentence that no flag for it existed. The cause was a real declaration defect —
`user_intent` names the restaurant while `check_availability` takes a
`restaurant_id` that appears nowhere in the intent, so a solving agent must
first call `search_restaurants`, and `capability_refs` declared only
`cap-check-availability`, which was credited at hop 1 for
`oc-check-no-availability` by a scenario needing two calls. The finding did
cost that run a cell, coverage recomputed 13/17 to 12/17, but only because the
double `re-seed` escalated to a rejection. That an `accept` plus a note would
have shipped the mislabel silently is the issue's **reasoned** path, not one it
observed.

**What changed.** Fixed across `c25f03c`, `c9c4897` and `fa451d3`.
`difficulty_understated` is in the enum and computed as the mirror, with the
`bool`-versus-`int` guard hoisted into one local because it is a property of
the pair of operands rather than of either inequality. It is surfaced *ahead*
of its sibling and bolded beside the call count, both asserted, since an append
at the end would have satisfied every other assertion. Layer 2 requires
whichever flag holds — not on the issue's list, and safe only because a missing
flag is repairable inside `rb-challenge`'s own `writes`. Layer 1 now forbids
both flags on one verdict, which **reverses** the first ruling that exclusivity
was a semantic judgment: a verdict carrying both was measured passing layer 1,
passing `check-refs` at exit 0 and surfacing nowhere, because the summary
recomputes both booleans from the two numbers and never reads the array. An
understatement forces no verdict, and the reason is written down so nobody
later fixes it into one: the remedy is an edit to `hop_depth` in
`02-scenarios.json`, which `rb-propose` owns and `rb-instantiate` cannot write.
A docstring resting on the confidence-band demotion is now pinned, after
measuring that narrowing that one clause to the overstated flag alone left the
whole repository green while making the docstring false. The flag closes half
the hole; the unrepairable half is parked rather than fixed, and **nothing here
was verified by a dispatch** — the toy fixture's data is unchanged, and no
exercise record was produced or re-recorded, because those state what a
dispatch did against the schema as it stood.

## The colliding batch ids

**What was measured.** `rounds.write_batches` minted batch ids from
`enumerate(batches, start=1)` with no round term, so **every round's first batch
was `b01`**. `rb-propose` has each member mint scenario ids beginning
`sc-<batch_id>-`, numbering from its own batch's position, and its invariant 4
stated that the prefix is the whole of what stops two members choosing the same
id — true *within* a round and false *across* rounds, since two rounds' `b01`
members were told to mint from one namespace. Observed on `run-20260906-102327`
(tau2-retail), round 2: the round-2 batch was planned as `b01`, the dispatched
member complied with the prefix rule and minted `sc-b01-01` .. `sc-b01-05`,
colliding with round 1's five. `propose-seal` exited 1 and wrote nothing, layer 2
named the collision, and the `RUBRICA_FINDINGS_FILE` repair path fixed the ids in
one dispatch at 0.33 USD. So the consequence was a **blocked round rather than a
wrong artifact**, and each mechanism downstream of the defect behaved exactly as
designed. That it would hit every run reaching round 2 is the issue's
**reasoned** claim from both terms sitting in code and prompt with neither
reading the round — the sample was one run and one round-2 dispatch. No test
caught it, and the reason is *fixture-cannot-reach* rather than a missing test:
`test_the_seal_assembles_every_round_in_order` was the one test that assembled
two rounds, and it hand-picked `sc-b01-002` for round 2 — an id that happens not
to collide with round 1's `sc-b01-001` — so it constructed the cross-round case
and then chose an id no member would have chosen, sidestepping the defect inside
it. A narrower finding shares the root cause and is visible only because the
transcript was read: both round-2 members went looking for the ids already taken,
one of them reading `02-scenarios.json`, which its own frontmatter forbids, and
minting a colliding id anyway while holding all 49 existing ones. All five
round-1 members were clean. That the old scheme left a round-2 member **no
in-contract way to see which ids exist** is the issue's own charitable reading of
that, offered as a contract gap rather than measured as one.

**What changed.** Fixed at `b0e1ac5`; the issue carries no closing comment, so
that commit is the record of what changed. Batch ids are now `r<N>-b<NN>`, making
scenario ids `sc-r2-b01-01`. The round went into the id rather than into a second
field a prompt has to read, because that puts the guarantee in code: a member
needs to know nothing about any other round to avoid a collision, and so has no
reason to go looking — which is how the read half was addressed, there being no
artifact-level check that can detect a read violation at all. `rb-propose` says
so in both places, §2's prefix rule and invariant 4, since the invariant is where
the false across-round claim was written down. The issue's second candidate —
have members number from the coverage document — was rejected rather than parked:
it moves a uniqueness guarantee from code into a prompt whose invariant text
already concedes that nothing checks the prefix. Two guards were added, each
watched failing first. `test_batch_ids_are_scoped_to_their_round` pins the
mechanism, and
`test_two_rounds_of_members_minting_from_their_batch_id_do_not_collide` is the
reproduction: it takes the batch ids `write_batches` actually plans and mints
exactly what the prompt asks for in both rounds, so reverting the fix fails it
with the collision the issue reports. The sidestepping test now uses ids a member
would mint; its own assertion is about ordering and passes either way, so the
edit is about no longer teaching the wrong id shape. `TOY_BATCH_ID` followed, and
it is asserted against the real `write_batches` plan, so a stale value fails at
the assert rather than leaving a fixture that disagrees with the code. The
`refs.py` comment recording a measured 20-cell/2-goal partition now names its two
batches positionally: restating them as `r1-b01`/`r1-b02` would attribute that
measurement to a partition nobody ran, and its numbers are unchanged. The prompt
half was **verified structurally** — the guards are unit tests over
`write_batches` and the seal, and there is **no dispatch of the amended prose on
record**; `rb-propose`'s exercise record predates the fix and was not
re-recorded.
