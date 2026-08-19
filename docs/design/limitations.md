# Known limitations

Read this before you propose a fix.

Most things that look like new bugs in this repository have already been found,
argued about, and **ruled on**. Every entry below is one of those: something
that is genuinely wrong, or genuinely missing, and was left that way on
purpose. Two fix rounds have already been spent re-litigating an item that was
sitting in a parked list nobody could find, which is the entire reason this
file exists.

Each entry states three things:

1. **what is wrong** — precisely enough to recognise it in the code;
2. **why it matters** — what a reader or a stage gets wrong because of it;
3. **why it is parked** — the reasoning, not just the verdict.

The third part is the one that earns its space. A ruling without its reasoning
cannot be responsibly re-opened when circumstances change, and several of these
*should* be re-opened — some are waiting on a design decision, some on a second
measurement, one on nothing more than somebody deciding it is worth the churn.
So this is not a list of things you may not touch. It is a list of things you
may not touch *without engaging the argument that parked them*.

Three conventions, so you can read an entry quickly:

- **Measured** means somebody ran it and watched the result. **Reasoned** means
  nobody has. Where an entry says a thing was measured, that is a claim about
  history, not a guess.
- Where an entry says a defect is *unreachable through the pipeline*, it means
  producing it requires a hand-authored or tampered artifact. That lowers its
  priority; it does not close it, because a defect that was equally unreachable
  has been fixed here before.
- Absence of a finding is not evidence a corner works. Several entries below
  are exactly the gap between "no gate objected" and "this is right."

Related reading:
[`docs/concepts/pipeline.md`](../concepts/pipeline.md) for the stages,
[`docs/concepts/artifact-contract.md`](../concepts/artifact-contract.md) for
the rule most of these limitations are about,
[`docs/reference/artifacts.md`](../reference/artifacts.md) for what each
artifact carries, and [`docs/design/rationale.md`](rationale.md) for why the
pipeline is shaped this way at all.

---

## Before you raise a finding against a stage's output

The first three are the ones most often reported as new bugs. Before writing any
finding in this group, **check what the stage's `reads` actually gives it.** A
finding that requires knowledge outside the contract is a finding against the
*contract or the fixture*, never against the prompt. That mistake is what cost
this project the two fix rounds mentioned above: a stage was blamed for not
knowing a fact that lived only in a claims file it is forbidden to read, and one
`grep` would have settled it before the first round instead of after the third.
The mirror question, for a `reads` addition you are about to propose: does a
deterministic gate already enforce the property? If so, the requirement belongs
to the gate.

### The isolation rule is enforceable on artifacts inside a run, and unenforceable on everything else a subagent can reach

**This is the weakest link in the design.**

A fan-out member that read a sibling's slice produces a **byte-identical
artifact** to one that did not. There is nothing in the output to check. No
schema, no `check-refs`, no digest and no hash comparison can distinguish the
two cases, because the violation happens in the reading, not in the writing.

Two read violations have been observed. An `rb-extract` member read *both*
sibling input files while checking how locators are formatted; an
`rb-reconcile` member consulted a *different fixture* entirely, outside its
declared `reads`. In both cases the resulting artifact was correct and was
independently verified, so nothing downstream was harmed — and in both cases
the only reason anybody knows it happened is that **the subagent volunteered it
in a report nobody obliged it to write.** That is luck, not an instrument.

The exposure is therefore not "another scenario's slice." It is anything on the
filesystem the dispatched process can open. (One *write* outside a run has also
been observed, when the dispatch harness's permission allow list carried a bare
`Write` grant and a stage used it to drop a scratch script in the repository
root. That grant is now scoped to the run directory and the scoping is pinned by
a test — it is named here only because it is the sharpest evidence for how wide
the reachable surface is.)

The only instrument that exists is a **transcript audit at dispatch time**:
`scripts/audit-reads.sh` extracts every path a dispatched stage actually
touched from the stream-JSON transcript `scripts/dispatch-stage.sh` writes, so
the list can be read against that stage's Contract `reads`. Run it — see
[`docs/guides/running-a-stage-by-hand.md`](../guides/running-a-stage-by-hand.md)
for where the transcript lands. A path outside the contract is graded Important,
not Minor.

Parked because the alternative is not a check — it is a different architecture.
Enforcing isolation mechanically means running each member in a container or a
filesystem namespace scoped to its slice, which changes how every stage is
dispatched and is a larger commitment than this experiment has made. Until
then: the rule is real, the audit is the enforcement, and **any claim that a
run "respected isolation" that is not backed by a transcript is an assumption**.

### The world model has no representation for a field's value domain

`capability.params` entries carry a name, a type and a `required` flag.
`entity.fields` entries carry a name and a type. Both are
`additionalProperties: false`, so there is nowhere to put a range, an
enumeration, a format, an example, or a real observed value.

**The consequence is the important part: every seed value in this pipeline is
synthetic by construction.** A concrete value anywhere downstream of
`rb-reconcile` — a ticket id in a seed, a queue name in an oracle — is a
*prescription* to `rb-instantiate` about the world it should build. It is never
an assertion about the target system, because no artifact in the run carries
the information that would make it one.

So **do not raise findings that require a stage to ground a value against the
claims.** That finding cannot be satisfied by any stage, because the domains
are not in the artifacts. `rb-instantiate`'s own prose says the values are its
to invent; the schema is why.

Parked rather than fixed because adding a value domain is a schema change with
a long tail: `rb-extract` would have to decide when an observed value is
evidence of a domain rather than a single sample, `rb-reconcile` would have to
reconcile two claims that disagree about a domain, and layer 2 would then be
able — and therefore obliged — to check seeds against it. That is a design
increment, not a patch. See
[`docs/concepts/glossary.md`](../concepts/glossary.md) under the world model
for the same point stated for a reader rather than a contributor.

### Seed conformance is one-directional

`refs._check_seed_conformance` checks seed→world: it computes
`set(collections) - set(entities)` and reports a seed collection that no
world-model entity declares. **Nothing anywhere runs world→seed.** No check
asks whether every entity the world model declares has a collection in the
seed, or whether that collection holds a single record.

Measured on the toy run: dropping `tickets` from `scn-empty`'s seed, and
separately keeping both of its collections present but empty, each leave
`validate --stage instantiate` **and** `check-refs` at exit 0 with zero
findings. Layer 1 catches only the fully degenerate `{"collections": {}}`, via
the seed schema's `minProperties: 1`.

The cases that *are* caught are caught by accident, which is the part worth
knowing. Dropping `comments` trips `inv-comment-count`, an invariant that
happens to count related records. Emptying `scn-open`'s seed trips
*reachability*, because its `value_equals` grounds in a pointer that has to
resolve. Neither accident is available for an absence-shaped scenario:
`scn-empty` and `scn-missing` ground `answer_excludes` at a pointer that must
resolve to *nothing*, so an emptied seed satisfies it — and those are precisely
the scenarios where an under-built world is most plausible.

There is a false docstring underneath this, and it is why the gap survived.
`invariants._records` returns `[]` for an absent collection, explaining that an
absent collection is "refs.py's finding to report" and that duplicating it
would double-count one defect. `refs.py` never reports it. Each half was
written believing the other half held it.

**Parked because it needs a design ruling before anyone writes code.**
`rb-instantiate` states only the one-directional rule — every collection must
be one some entity declares — so a *partial* seed may well be intended: a
scenario about one entity has no obvious duty to populate every other. What is
indefensible under any reading is "every declared collection present and
empty": a seed that satisfies the letter of conformance while containing no
world at all. The follow-up is real; what it is not is obvious, and guessing
the rule in code would be the wrong order.

### Layer 2 checks that an element *references* a resolvable claim, never that the claim *supports* it

`check-refs` will tell you that a world-model capability cites claim `clm-7`
and that `clm-7` exists. It will never tell you that `clm-7` has anything to do
with that capability.

Support is semantic, and this hole is load-bearing in the sense that things
have actually fallen through it: **two real defects lived under it in the
golden fixture itself** — the model answer every skill imitates.

Parked, and this one is a deliberate design position rather than a deferral: do
not invent a mechanical check for support. Any such check would have to encode a
judgment about whether a sentence backs a structural claim, which is the exact
judgment the experiment exists to observe a *prompt* making. A mechanical
approximation would either fire on correct citations or pass wrong ones, and in
both cases it would make the stage's judgment less observable rather than more.
Checking support is what the human gates are for — gate 1 in particular, where a
person reads the world model against the claims it cites.

### `rb-propose` is not held to the world model's declared entity set

A scenario declares `capability_refs`, and layer 2 checks each one against the
world model's capabilities. Nothing checks the *entities* a scenario's premise
requires, because a scenario has no field in which to declare them.

Measured, at cost. On a real run, `rb-propose` wrote scenarios requiring seeded
pipeline results, repository file content, cloud account records with a region
field, and monitoring downtime objects — none of them declared as entities.
`validate` and `check-refs` pass such a scenario without comment. The cost
lands two stages later, at `rb-instantiate`, which correctly refuses to
fabricate a world it was never told about: six refusals plus one rejection,
roughly five dollars, and seven of thirty-six scenarios lost.

Parked because the fix is a gate on a field that does not exist yet, so it is a
schema change plus a check plus a prompt change to `rb-propose`, in that order.
The refusals are the *designed* behaviour of the stage that receives the
problem — the pipeline reported an honest hole rather than inventing a world —
so this is a cost-and-latency defect rather than a correctness one, which is
what put it behind the correctness items.

### `rb-extract` may speculate in its report about the sibling it did not read

Three of five dispatches honoured the file boundary on reads and then
volunteered a guess about the unread sibling's contents in the report they
wrote back — "that lives only in `notes.md`", "presumably in the sibling
`api.json`". No file was opened and no claim was filed on any of it, so the
rule held where it is enforceable.

It matters because a guess about an unread sibling in a *report* is one step
from the same guess inside a *claim*, and a confabulated claim is
byte-identical to an extracted one — see the isolation entry above for why
that is not recoverable after the fact. The prompt currently binds the *claims* —
a claim of yours must never read as though you knew what a sibling artifact
says — and says nothing about the report.

Parked as prompt hardening rather than dismissed: nothing was harmed in the
observed cases, and the one-sentence extension to cover the report is a change
to a prompt whose predicates are measured, so it goes with the next deliberate
re-record of that skill rather than as a drive-by edit.

### `rb-reconcile`'s corroboration test never says what "independent" excludes

The skill asks whether "a second, independent claim" supports one side of a
contradiction. Its worked example contributes exactly one claim per artifact,
so nothing in the text rules out counting **two claims from the same document**
as independent corroboration — which would make a self-contradicting document
look like two agreeing sources.

Settled empirically rather than pre-emptively, and the distinction matters:
the prose gap is real, and it did not mislead the model, which reasoned that
two such claims "cancel out rather than one confidently corroborating the
other" and named the pull it was resisting. That is recorded as **sufficient
for this model on this input** — weaker evidence than "the prompt says so", and
it must not be filed as the latter.

Parked because the one-line clarification is a hardening, not a fix, and
because tightening prose that a model already navigates correctly risks the
mirror failure this repository has also measured: a predicate pinned to a
phrase, broken by an innocuous reformat.

### `rb-emit`'s `reads` is over-broad by the skill's own stated criterion

`rb-emit` declares `reads = ["scenarios", "verdict", "expected",
"world_model"]`, and its own first section justifies two of those four with a
rule stated as general: they are there "because a requirement of this skill
needs them, which is the only reason anything is ever in a `reads` list." By
that criterion the other two — `expected` and `world_model` — do not belong.
`rubrica emit` consumes them to compile a package; no requirement of *this
skill* opens either. Its Method steps read `emit`'s stdout, `02-scenarios.json`
and `05-verdicts/`, and its own enumeration of where every reported fact comes
from names those three and not these two.

The cost is not tidiness. `reads` is what a dispatched model is told it may
open, and a declared read it cannot tie to any step of its own Method invites
the plausible reading — open every oracle "to understand the compilation" —
which is one step from reviewing the suite instead of reporting it, the exact
move that skill's invariants forbid by name.

Parked rather than narrowed because the two names are also the truthful answer
to a different question the same section asks and answers well — *what will a
finding about a package name?* — so removing them would make one paragraph
wrong to make another right. The fix is a wording decision about what `reads`
means for a stage that only reports, and `check-skills` holds `reads` to the
artifact vocabulary rather than to the skill's Method, so no gate moves either
way.

### Two prompt statements are stronger or narrower than the rule they describe

`rb-score`'s survivor rule tells the stage to keep the scenario whose
`discriminating_fact` "pins its world down more tightly", and then claims the
surviving id is therefore "stable across two scorings of the same state." It is
not: tightness is a judgment, and the only part of that rule that delivers
determinism is the round tiebreak that follows it.

`rb-instantiate`'s self-check sorts a gate finding into *yours* or *a
sibling's* — "a finding whose path names another scenario's directory under
`04-instances/` is not yours" — and is silent on a third case: a finding
against a **shared frozen input**, which names neither instance directory.
Nothing tells the member to forward it, and the stated bar for success ("no
finding names a path inside your own instance directory") is satisfied while it
stands.

Parked together because both are one-sentence prose edits to skills whose
predicates are measured, and because the failure mode of fixing them carelessly
is documented: pinning a prompt sentence produces an assertion satisfiable by
unrelated content unless the assertion is scoped to the section that owns the
rule. They go with a deliberate re-record of those two skills.

---

## Before you trust a number a run reports

### One exercise is one sample

Eight of the pipeline's nine skills carry an `exercise.md` beside their
`SKILL.md`, each recording what **one** measured dispatch actually did. That is
the only behavioural evidence this project has, and one sample is one sample: a
prompt that refused correctly once, or built a sound world model once, has not
thereby been shown to do so reliably.

`rubrica diff-runs` exists for exactly this measurement — per-stage stability
across two runs — and the measurement has not been taken. The two real-target
runs that exist are incomparable by construction, because they read different
input sets, so their stage diffs localise differences rather than quantify
variance. Nobody has yet run the same inputs twice and diffed the result.

Parked on cost: a variance measurement means running the whole chain several
times over one input set, and each full run over a real target costs real money.
`sample-for-review` has the same shape for the human half — the tool ships, and
sampling a suite at a scale that would say something needs human hours nobody
has spent.

What this means for you: **a number in an exercise record is an observation, not
a rate.** If you are about to reason from one, say which run it came from.

### Two runs over the same inputs disagreed on claim count, and on which stages a gap blocks

The entry above says nobody has yet run the same inputs twice and diffed the
result. On 2026-08-16 that happened by accident, for one stage, and the answer is
worth writing down.

`run-20260816-172810` ran the `extract` fan-out twice over the same 31 admitted
inputs, `sonnet` at `medium` effort both times. Claim totals came out **639 and
then 546**, and the drop is concentrated in two inputs that the intervening
prompt change explicitly excludes:

| input | first run | second run |
|---|---|---|
| `tools-list-json` | 54 | 22 |
| `readme-md` | 42 | 30 |
| 27 trace inputs, combined | 493 | 453 |

`tools-list-json` is a static JSON schema file. Same model, same effort, same
input bytes, and one dispatch extracted 54 claims where the next extracted 22.
Not truncation: both reported `subtype: success` at about $0.46, far short of the
$2 ceiling, and `rubrica validate --stage extract` exited 0 over both sets.

Why this one hurts more than a count normally would: `tools-list-json` is the
input `rb-triage` ranked priority 1, on the grounds that it is "the only
candidate that declares what a tool returns" — and `rb-reconcile` builds its
coverage denominator from `outcome_class` claims, so how many of them arrive
bounds the width of the test matrix downstream.

**The confound, stated plainly.** The prompt was not byte-identical between the
two runs: Method step 3 gained the capture-instant paragraph. That paragraph is
scoped to trace inputs, and both files above cite `/info/request_time` zero
times, so it is inapplicable to them rather than merely unused — but it was still
in the prompt they were dispatched with, and a longer prompt is not a neutral
change. So this is *evidence of large variance* and not a clean variance
measurement. A clean one needs the identical skill dispatched twice.

**What was not measured.** Whether the claim *content* diverged as much as the
count — no semantic diff of the two claim sets was taken, so 22 claims may say
most of what 54 said at lower granularity, or may not. `rubrica diff-runs` is
the tool for the stage-level form of this and was not run across the pair.

Parked for the same reason as the entry above: taking it properly means paying
for repeated fan-outs over a real corpus, and this one cost $21.69 per pass.

What this means for you: **a claim count is a property of a dispatch, not of an
input.** If a run's numbers look thin, that is not by itself evidence the input
was thin, and if they look rich, that is not evidence the extraction was
thorough. `src/rubrica/skills/rb-extract/exercise.md` round 4 records the
observation in full.

#### The same pair of runs moved a halt, which is worse

`rb-reconcile` was dispatched twice in that run, `opus` at `high` effort both
times, over claim sets differing only as described above. Both produced a clean
world model. They did not agree on which stages a gap blocks -- and `blocks` is
the field `rb-orchestrate` branches on at B4 to decide whether the pipeline
stops.

| first run | second run |
|---|---|
| `gap.place_reservation_failure_paths` -> `propose`, `challenge` | `gap-place-reservation-unknown-restaurant` -> `score` |
| `gap.tool_argument_validation` -> `propose`, `challenge` | `gap-search-tool-level-validation` -> `score` |
| `gap.llm_failure_visible_result` -> `propose` | `gap-deployed-llm-backend` -> `instantiate`, `score` |

The substantive unknown is the same in each row: `place_reservation`'s
non-success surface is unobserved, tool-level argument validation is unobserved,
the deployed chat model is undetermined. What moved is the stage each one is
declared to block. The first run halted `propose`; the second explicitly declined
to, on the stated grounds that "scenario design against all 7 capabilities'
described behaviour is possible, so claiming a halt would have been dishonest."
Both positions are defensible, which is the problem: nothing in the artifact
distinguishes a considered judgment here from a coin flip, and the reader of a
single run cannot tell which they have.

Neither run's `blocks` assignment is wrong, and no gate can see the difference --
`validate` and `check-refs` passed on both world models, because `blocks` is a
free enum of stage names and any subset of them is well-formed. The consequence
is asymmetric: claim-count variance costs coverage that a human at gate 1 might
notice, while `blocks` variance decides whether the run reaches gate 2 at all.

This also means an easy misattribution is available and was nearly made in the
run that found it: after a prompt fix aimed at a *different* gap, `propose` came
out unblocked, and the fix looked responsible. It was not. The fix closed
`gap.cancellation_aftermath`, which is attributable and confirmed; `propose`
cleared because a second dispatch of an unchanged prompt filed the same unknowns
against a different stage. **Before crediting a change with unblocking a stage,
check whether the gap closed or merely moved.**

What this means for you: **do not read a single run's `blocks` as the design's
verdict on what is answerable.** It is one dispatch's judgment about one claim
set, and B4 is strict enough that on a real corpus the question is usually which
stage halts rather than whether one does.

### `rb-triage` carries no `exercise.md`, and the evidence it would hold is not in the repository

`rb-triage` is the skill without one — and **not** because it has never been
dispatched. It has been dispatched at least twice against a real, non-toy
target. One of those runs catalogued 351
candidates and admitted 130 of them, and its `decisions.md` records a genuine
human gate-0 ruling: an operator accepting the triage record with no
disposition overrides, accepting the risks named in all twelve of the
deficiencies triage had raised, and recording that one of them (breadth
supported at the persona level but not at the tool level) makes per-surface
pass rates from the resulting suite non-comparable. That is the richest single
piece of behavioural evidence this pipeline has produced.

**None of it is committed.** Run directories live under `runs/`, which is
gitignored, so those records exist on one machine and nowhere else. This
project's own rule is that an exercise record states what *happened*, and that
results belong in that file rather than only in a ledger somewhere else,
because ledgers get deleted. A gitignored run directory is a ledger with a
shorter life than most.

It matters more here than it would for another stage, because `rb-triage` is
the stage that holds **gate 0**, and gate 0 is different in kind from the other
three. Gates 1 through 3 review a judgment made from evidence already in the
run; a human overturning one of them corrects an inference. Gate 0 decides what
the run can ever know — nothing downstream of `intake` reads the corpus again,
so a candidate triage declines is gone as completely as if the corpus had never
contained it. The stage with the least recoverable authority in the pipeline is
the one whose only real-world evidence is the most perishable.

Recorded here rather than quietly fixed because writing the record honestly
means transcribing a specific run's numbers, declines and gate ruling from a
machine that still has it, and an `exercise.md` assembled from reasoning
instead of transcription is worse than none at all — a reasoned number
presented as an observed one has corrupted this project's evidence once
already, and had to be retracted. So the obligation is a transcription job with
a named owner, not an edit anybody can make from the committed tree.

### The loop's stopping rule is blind to goal-coverage progress

`coverage-0.1.json` defines `progress` as exactly `new_cells_this_round` plus
`rounds_without_progress`, with `additionalProperties: false` — **there is no
goal term.**

Measured on a real run. Every remaining cell hole was `blocked_by_gap`, so
`new_cells_this_round` was structurally guaranteed to be 0 in every future
round: the loop was certain to halt however much goal coverage remained
closable. Round 2 tripled goal coverage and registered as zero progress. After
it, each of the nine uncovered goals was missing exactly one hop depth — always
the deepest — and `max_rounds` still permitted a third round. The suite shipped
at three of twelve goals as a direct result.

So `halted_no_progress` does not mean what its name says. It means "no new
cells."

Parked at the run level and owed at the schema level: that arithmetic is
`rb-score`'s to own, and the fix belongs in `coverage-0.1.json` rather than in
one run's control flow, so overriding it by hand in a live run was declined on
purpose. Either `progress` gains a goal term or `halted_no_progress` gets a
name that admits what it measures. Note the coupling before you touch
`max_rounds`: raising the round ceiling while `progress` stays blind to goal
coverage buys rounds the stopping rule will refuse to use.

### `max_scenarios` has no sizing heuristic, and the implied-size formula rests on one run

`max_scenarios` is a **blast-radius ceiling**, not a sizing decision: it is the
point past which nobody will read the output. It says nothing about whether a
given target's world model wants twelve scenarios or sixty. The default is 128,
which is a bound on damage; the number that would actually size a run is still
owed.

What is known: the floor for a real target is far above the toy world's, and
somewhere around fifty rather than the eight this project originally defaulted
to — a number set by instinct after a real run had to have its ceiling raised
by hand mid-flight. `rubrica gate-brief` reports an *implied* size at gates 1
and 2, derived in `sizing.py` from the world model's own denominator
(capability cells plus expected hop-depth slots, divided by a measured
acceptance rate). Nothing acts on it; it is a diagnostic a human reads in both
directions — implied size above the ceiling means the target wants splitting
across runs, and a suite that halts far below it is a signal that the stopping
rule gave up early.

Three caveats attach to that formula, and all three are why the heuristic is
still owed rather than chosen. The acceptance allowance (0.75) is **one run's
constant**, labelled as one rather than as a law. The denominator arithmetic
that validated the formula also comes from that single run, and a second target
could move it substantially. And there is an unresolved ruling inside the
denominator itself: whether internal-persona goals belong in it at all, given
that on the run in question three of twelve goals described one journey from
three vantage points and only the end-user goals were exercisable through the
target's actual interface. Settling that moves the gate-1 denominator by
roughly ten percent, so the formula should not be trusted to more precision
than that ruling.

Parked because a sizing heuristic derived from one target is a constant wearing
a formula's clothes. It needs a second real run before it is worth writing
down, and the ceiling holds in the meantime — which is what a ceiling is for.

### `max_rounds`' default is binding rather than protective

The default is 2. A guard is a number a healthy run never reaches; a parameter
is a number that decides the outcome. At 2 this is a parameter: a real run's
bound is often the round cap rather than its coverage, which is the same error
`max_scenarios` had when its default was 8. A ceiling nearer 6 would make it a
guard, and the loop would then stop on `converged` or `halted_no_progress` as
designed.

Parked and explicitly sequenced behind the entry above it: raising the ceiling
while `progress` is blind to goal coverage buys rounds `halted_no_progress`
will refuse to use, so the schema change comes first. Raising it also changes
the propose/score loop's cost profile, which is a deliberate decision rather
than a default worth flipping quietly. `rubrica set-limit` is how you raise it
for one run, with the reason recorded in `decisions.md`.

### The orchestrator has no lever for `effort`

`rubrica record-stage` records a `model` and an `effort` per stage, and
`rb-orchestrate`'s prose says where both come from. But **the dispatch
mechanism cannot supply an effort level.** There is no channel through which
the orchestrator sets it.

So every `effort` value in a manifest today is a *characterization* of what was
run, not a *setting* that made it run that way. The one completed run recorded
the most neutral characterization available and flagged the assumption rather
than presenting it as fact — which is the right handling, and is also why you
should not read an `effort` field as reproducibility information.
Reproducibility rests on `model` and `skill_sha256`, which do the real work in
`diff-runs`' comparability precondition.

Parked because supplying it is a property of the dispatch mechanism rather than
of this codebase: nothing in `rubrica` can add a lever the harness does not
expose. Recording the field anyway is deliberate — the field is where the value
goes the moment a harness can supply one, and dropping it would lose the
comparability slot.

### Input digests are re-verified within a run, never across two

`refs.check_inputs` re-hashes the bytes in `00-inputs/` against the digests
`manifest.json` records for them, which closes the reproducibility hole inside
one run.

`diff-runs` does not chain to it. Its comparability precondition refuses to
call two runs comparable unless their manifests record identical input
digests — but it compares the two manifests' *recorded* digests, trusting each
at face value, rather than re-hashing either run's bytes itself. So two runs
tampered identically, or a run whose `check_inputs` was never executed, can
still report `comparable: true` on a false premise.

Parked because the honest fix is a decision about what `diff-runs` is for.
Calling `check_inputs` on both runs makes a comparison command a verification
command, doubles its IO on large input sets, and raises the question of what it
should report when run *a* is internally inconsistent — which is not a
comparability finding. The cheaper answer is procedural: run `check-refs` on
each run before you diff them. That answer is only good enough while the person
diffing knows to do it, which is why this is recorded rather than closed.

### Golden `scn-empty`'s `answer_excludes` marks a correct answer wrong

Measured through the real scorer on the emitted package. The oracle's own
`answer_reference` scores `reward` 1.0. That same answer plus "its only ticket,
4103 (Label printer offline in DC2), is open" — correct, and strictly more
informative — trips the exclusion and scores assertions 0.5, `reward` 0.6.

Nothing mechanical will ever raise it. The exclusion is grounded at
`/collections/tickets/2`, which resolves to nothing, so layer 2 is right to be
silent, and the absence-scoring ruling that says an exclusion satisfied by
absence scores a point is untouched by this.

It matters because of what this fixture *is*. The golden run is the model answer
a skill imitates and the worked shape a reader calibrates from, so a label that
punishes the better answer teaches that as the pattern.

Parked rather than fixed because the numbers this one assertion feeds are
pinned in three separate places in `tests/unit/test_toy_end_to_end.py`: an exact
`mean_reward_by_role` dict, the per-task weak-baseline values for both
absence-shaped tasks, and a third test's docstring reasoning from the
absence-shaped spread to why swapping two seeds moves nothing. Deleting the
assertion turns the first two red — measured — and re-deriving all three
belongs with a deliberate re-record rather than an edit made in passing.
`tests/toy.py` carries the same admission in a comment above the oracles; this
entry exists so the finding does not depend on somebody reading that comment.

---

## Before you file a bug against a human gate

### `--no-gate` is a prompt-level flag, not a CLI flag

The human gates live in `rb-orchestrate`'s prose. No code enforces them, so
`--no-gate` is an argument to the *skill's invocation* — a string in a prompt,
not a parsed option. Grep the CLI for it and you will find nothing.

A prompt-level flag can be forgotten in a way a CLI flag cannot, and this one
is what makes the reproducibility claim honest: a run that skipped its gates
has to say so.

Accepted as the right cost for this stage of the experiment, and the reasoning
is the point: enforcing the gates in code would mean the orchestrator stops
being a skill, and whether a skill can hold a gate is part of what is being
tested. There is behavioural evidence that it can — an orchestrator handed
`--no-gate` still refused to overrule a blocking gap, on the correct grounds
that the flag skips *human review* and a blocking gap is not a human gate, a
distinction that lives in one sentence of prose and had no other instrument.

### `objective_review` is prose a model writes about its own compliance

`rb-triage` writes an `objective_review` block asserting whether its selection
supported the objective it was given. A triage that silently re-scoped and then
wrote `supported: true` produces an artifact **both gates pass**.

Nothing mechanical catches it, and nothing can: the claim is about the
relationship between an instruction and a judgment, which is the same shape as
the isolation rule at the top of this document. The instruments are gate 0 and
a transcript audit.

Parked because this is a restatement of the design's central bet rather than a
defect with a fix. The mitigation that exists is structural and worth
understanding: **triage does not hold its own gate.** The same party selecting
the inputs and ratifying the selection would make the whole run unfalsifiable,
which is why gate 0 belongs to a human and not to `rb-triage`, and why
`rb-orchestrate` never dispatches triage at all.

### The catalogue digest is the single point of failure for triage

Every triage decision rests on the per-candidate digest `rubrica survey`
writes. That digest is produced by code that cannot know the target, and its
insufficiency for a given candidate is only visible when triage notices and
says so.

Mitigated rather than eliminated, in two ways that are both worth knowing at
gate 0: `rb-triage` has a `digest_insufficient` decline it is expected to use,
and the catalogue records which heuristics fired for each candidate, so a human
can see what the decision was made from.

Parked because the alternative is triage reading the candidates themselves,
which is the cost the digest exists to avoid — and at a few hundred candidates
that is the difference between a barrier a model can hold in context and one it
cannot. A related bound sits next to it: a barrier over several hundred
candidates is a large context (roughly 400 bytes of digest each), and
`--max-candidates` is the only thing holding it. If real corpora routinely
exceed it, triage needs a clustering pass, and that is a redesign rather than a
parameter.

---

## Before you file a bug against the check layers or the CLI

Every entry here is real, and several are unreachable through the deterministic
pipeline — which is why they are ranked below the ones above, and not why they
are still open. A defect that was equally unreachable has been fixed here
before, so reachability alone is not the test. Each entry says which it is. The
[exit-code contract](../reference/cli.md) is what several of them are measured
against, and it is worth reading first: a `1` is a repairable stage defect, a
`2` means retrying cannot help, and the orchestrator branches on the
difference.

### `refs.py` never checks a `machine:` invariant's field names against the entity's declared fields

The invariant loop in `refs.py` iterates exactly `("collection", "of")` and
checks those two against the world model's declared collections. The other five
keys a `machine:` invariant can carry — `field`, `local_key`, `foreign_key`,
`order_by`, `source_field` — **are checked by nobody.** The schema requires all
five to be non-empty strings and cannot tie any of them to a declared field
name, because a field name is a fact about the entity being referenced.

So a typo in any of the five is caught only coincidentally: by an invariant
message about a record missing a field, and only if the seed happens to hold
records at all.

One of the five is worse than the others. `invariants.py` reads a record's
`source_field` as `r.get(source_field, "")` — a `""` default where every other
key goes through `_field`, which returns a `MISSING` sentinel. A mistyped
`source_field` therefore compares against a join of empty strings and produces
**no diagnostic at all**, not even a coincidental one; it is caught only by a
string mismatch happening to differ.

Parked, and the shape of the ruling matters: fixing the sentinel narrows one
symptom, while **the check that would remove the whole class is the missing
one** — and it is a perfectly checkable check, because the entity's
`fields[].name` set is right there in the same object. So if you are going to
touch this, write the field-name check rather than the sentinel. It is latent
today because the golden fixture uses no `join` invariant, and adding one
purely to reach the sentinel bug would be building a fixture to exercise a
fix nobody is making.

### Two content-derived failures exit 2 rather than 1

Both measured.

A stage that wrote a **directory** where `04-instances/<sid>/seed.json` belongs:
`validate --stage instantiate` and `check-refs` both exit 2 with
`[Errno 21] Is a directory` on stderr and an empty stdout — where an absent or
unparseable `seed.json` at the same path is an exit-1 layer-1 finding naming the
file.

An **over-long `stored_as`** in the manifest: layer 1 does report it,
`validate --stage intake` exiting 1 on the schema's `maxLength`, while
`check-refs` exits 2 with `ENAMETOOLONG` — where a `stored_as` naming a merely
absent file is an exit-1 finding at that same pointer.

The `OSError` catch these fall under was widened deliberately, to close a
family of failures where the *filesystem* refusing was being reported as a
repairable stage defect. That widening was right. What it swept in are two
cases where a stage wrote the content that fails.

Parked because deciding it means deciding whether the 1-versus-2 line is drawn
on **what failed** or on **what a repair could do**, and the two readings
genuinely disagree here rather than one being an oversight. For the directory
case exit 2 is arguably *correct* under the contract's own definition:
`write_json` cannot overwrite a directory, so a re-dispatch of that stage
cannot clear it, and exit 2 means "repeating the stage cannot help." The
over-long name is the weaker case, since layer 1 demonstrates that a repairable
finding exists.

**No test pins this boundary either way, which is the part that should not
survive another build.** Whichever reading wins, both states belong in
`tests/unit/test_refs_states.py`.

### `dedupe-candidates` maps a stage defect to exit 2

It reads `02-scenarios.json` directly, so an unparseable file raises out to the
shared handler and becomes exit 2 — a misconfigured harness — while `validate`,
`check-refs`, `emit`, `compare-gold` and `sample-for-review` all return exit 1
with a finding for the same file.

This violates the exit-code contract in the direction that costs the most: a
repairable stage defect surfacing as a misconfigured harness makes the
orchestrator halt instead of spending its one repair attempt.

Parked as a single-subcommand inconsistency in a class that is otherwise
closed, and because the deterministic pipeline never reaches it —
`dedupe-candidates` is invoked by `rb-score` on a file `validate` has already
passed. Small fix, low reach; it is here so that finding it does not cost a
round.

### `survey`, `intake` and `adopt-projection` sit outside the exception net

`cli.py` wraps its subcommand dispatch in a catch-all that converts an
unexpected exception into a finding-shaped exit 1, precisely so that no
subcommand can exit 1 with empty stdout. Three blocks return before that `try`
begins, each with its own narrower catch for `UsageError`, `ArtifactError` and
`OSError`.

So an unexpected exception in one of the three exits 1 with empty stdout — the
exact mode the net was added to close.

Parked because the crash surface is genuinely small and the placement is
deliberate. All three read paths a human or an orchestrator supplied rather
than artifacts a stage wrote, so a failure there really is a usage error or a
misconfigured harness: there is no stage to send a finding back to. Slug
generation cannot emit an unsafe segment, and IO raises `OSError`, which is
caught. This has been re-examined twice and still holds; what would change it
is a fourth block, or one of these three growing a real content-parsing path.

### The catch-all blames the artifact, and names the wrong run for `diff-runs`

Two facets of the same handler, both live.

**It blames the artifact.** A genuine bug in `rubrica`'s own code is reported as
"an artifact in this run is malformed; run `rubrica validate`". If `validate` is
then clean, the orchestrator has two signals that contradict each other.
Mitigated by the traceback the handler prints to stderr, and by the finding
naming the exception type and message, so the line is diagnosable by a human
even when it is misdirected.

**It names the wrong run for `diff-runs`.** The handler builds its finding
against `args.run`, falling back to `args.a`. `diff-runs` is the only
subcommand taking two run directories, so a defect in run **b** surfaces as a
malformed artifact in run **a** — which an orchestrator would attempt to
repair.

Parked because the finding line is present and parseable in both cases, which
is strictly better than the empty exit 1 it replaced, and because nothing
downstream reads the artifact field programmatically. The fix for the second
facet means either naming both roots or dropping the "this run" phrasing when
the subcommand has two, and the fallback chain ends in `"."` deliberately so
that this line can never itself be the thing that fails.

### A symlink loop in an artifact position is silently skipped

`paths.list_json` filters on `is_file()`, which swallows `ELOOP` and answers
False rather than raising. So a self-referential `01-claims/loop.json` is not a
claims artifact, not a finding, and not an error: `validate --stage extract` and
`check-refs` both exit 0 over it. Measured.

Arguably the right tolerance — a loop is neither a claims file nor evidence
that the ones present are wrong, and it is the same "skip what is not a file"
rule that keeps a stray subdirectory from being read as JSON.

What makes it worth recording is that it is the one listing shape `list_json`
does not surface, and the whole reason `list_json` replaced a bare glob was
that a listing failure must be *visible*: `list_dir` converts `EACCES` and its
neighbours into a `UsageError` naming the directory, so the run stops with the
harness blamed rather than an artifact. `ELOOP` on a member of the listing gets
through, inside the guard added to close exactly that class.

### An unsafe directory name under `06-suite/` is neither pruned nor reported

`scenario_ids_with_tasks()` skips a directory whose name is not a safe segment,
so such a directory is not pruned, not reported, and would ship in the emitted
suite. There is no `unsafe_task_dir_names()` counterpart to the
`unsafe_instance_dir_names()` that `04-instances/` has.

Parked because it requires manual tampering: every directory under `06-suite/`
is created by `rubrica emit` from a scenario id that layer 1 has already
constrained. The fix is small and symmetric with the `04-instances/` case, so
the reason it has not been made is priority rather than difficulty.

### `skills.load()` ignores a second `## Contract` section

The loader is deliberately strict about the fence: it counts `toml` blocks
*within* the Contract section and refuses anything but exactly one, precisely so
a toml-fenced example earlier in the prose cannot be mistaken for the
declaration. But its section reader returns on the first heading that matches,
so a file with **two** `## Contract` sections is parsed from the first and the
second is never looked at. The one-block rule is enforced inside a window that
stops before the impostor.

Demonstrated: a whole second Contract block appended to a skill, declaring a
bogus stage and a nonexistent `reads` name, gives `check-skills` exit 0 with
neither name reaching the contract checker.

The hazard is not the tampering case. It is the ordinary one — an author who
edits the wrong block, sees a green `check-skills`, and reads that 0 as
validation of the edit they just made. That is the declaration-drifts-from-the-code
failure the module exists to prevent, arriving with the module's own blessing.

Parked because the narrow fix (refuse a duplicate heading) is a change to a
parsing core that two reviews validated, and because `SKILL.md` files are
hand-authored and repo-shipped. It belongs with the contract-block regex
replacement in the next entry, which touches the same code.

### The contract-block regex backtracks quadratically on unclosed fences

Measured: 6 seconds at 8000 unclosed fences against 0.37 seconds at 2000.

Not reachable. `SKILL.md` files are hand-authored and shipped in this
repository, a small fixed set of them, each a few hundred lines.

Parked with a named replacement rather than a narrow patch, because the narrow
patch does not help: proving "exactly one `toml` block in this section" requires
scanning to the end of the section either way. The real fix is replacing the
regex with the fence-aware line walk that already exists in the same module,
which churns a parsing core two reviews validated for no reachable benefit
today. **If `SKILL.md` ever becomes user-supplied, that walk is the
replacement** — and that is the condition under which this entry stops being
parked.

### `check_contract`'s message for a non-string element names the wrong problem

Given `invokes = [{"tool": "validate"}]`, the finding reads "invokes `{'tool':
'validate'}`, which is not a rubrica subcommand" rather than "must be a
string". Same for a non-string element of `reads` or `writes`.

Deliberately not fixed, and the distinction from the case that *was* fixed is
the exit-code contract. A bad `schemas` element used to **crash** into exit 1
with an internal message naming the wrong tool; these all return a parseable
exit-1 finding that renders the offending element, so a reader can see what to
edit. Unifying all four keys behind one helper would remove the class and
refactor a function three reviews validated, for a cosmetic gain in a message a
human reads once.

---

## Before you rely on a test or a fixture

One batch of this repository's text-level assertions was audited for vacuity by
deleting the prose each one claimed to check, and the result was bad enough to
change how tests are written here: roughly nineteen of them stayed green with
that prose gone, satisfied by content unrelated to the property their own
docstring named. The general procedure that came out of it — measure a predicate
in both directions before you commit it — is in
[`CONTRIBUTING.md`](../../CONTRIBUTING.md). What follows is the residue that
audit and its successors left behind.

### No test reads any `exercise.md`, and three reconciled handoff statements are unpinned

Measured by deletion, one at a time, restoring between: remove `rb-score`'s
rejection-notice exception together with its matching Method step; remove
`rb-instantiate`'s entire re-seed notice section; remove `rb-score`'s Method
step on what `dedupe-candidates` does *not* exclude, along with the matching
passage in `dedupe.py`'s docstring. Each deletion leaves the suite green.

So all three can regress silently, and each of the three failure modes those
statements were written to prevent is reachable again by an edit no gate
objects to: a silently-green coverage report after a rejection, a re-seed
notice read as out-of-contract text, and a deliberately non-folded pair folded
on its re-raise.

The same holds for every `exercise.md`. **No test reads one** — including the
requirement, written inside one of them, that a negative result belongs in that
file rather than only in a review ledger elsewhere.

Accepted rather than fixed, and the reasoning is a measurement this repository
already owns: pinning prompt prose produces assertions satisfiable by unrelated
content, and the fix wave immediately before this ruling had to repair six such
predicates that each passed with the rule they name deleted. A predicate written
under time pressure would most likely be the seventh, and **a test that gives
false confidence about a handoff is worse than a recorded gap about one,
because it retires the question.** If you write one of these, measure it in
both directions first: red on deletion of the prose it claims to check, green on
a meaning-preserving rewording.

### The negative fixtures have remaining unguarded surfaces

`tests/fixtures/toy-contradiction/` and `tests/fixtures/toy-gap/` are the
golden world with specific prose subtracted, and
`tests/unit/test_refusal_fixtures.py` guards that each still carries its defect
*and* has not silently lost anything else. Four gaps remain in that guarding,
each ruled rather than overlooked.

**The structural guard is one-directional.** It asserts
`_key_paths(golden) - _key_paths(fixture)`, so it says nothing about structure
the fixture *added*. The value guard written alongside it does not cover the gap
either, because it reads exactly one path (`tools[0].returns`). So appending a
*second* tool to the contradiction fixture's `api.json`, whose `returns`
describes error behaviour, would reconstruct the two-independent-artifacts
corroboration that makes the fixture's recorded `unresolved` rationale
defensible — the precise property the fixture exists to deny. Demonstrated: with
such a tool appended, the whole suite passes. Left open rather than patched
because the honest fix is the *direction*, not another path: assert the key-path
sets **equal** and let a legitimate fixture edit be the thing that has to
justify itself.

**The structural guard keys on positional list indices**, so inserting a tool
ahead of the existing one reports many paths missing when nothing was lost.
Demonstrated.

**The gap fixture's goal prose is unguarded.** No predicate catches its deletion
without anchoring on a single incidental word — and that prose is byte-identical
across all three fixtures including the golden one, so it is not a
negative-fixture property at all. Declining to write a test that would give
false confidence was the right call.

**Several contradiction-fixture predicates key off exact substrings** rather
than the semantic property they name.

One related schema gap sits underneath all of it: `capabilities` has no
`minItems`, so a world model with none is valid, and the thing standing between
a re-recording with zero capabilities and a green suite is a test rather than a
gate.

The gap fixture's forbidden-substring list **is its specification.** Do not
relax it to make prose easier; if a word is truly unavoidable, remove it and say
so.

### Three smaller test-accuracy residues

`test_the_effort_choices_are_read_from_the_schema` opens "Not a second copy of
the enum" and then asserts the tuple against a literal copy of the enum. It is
harmless in effect, because the property it names is genuinely covered by a
different test that points `RUBRICA_SCHEMA_DIR` at a rewritten schema and
asserts the tuple follows it. Recorded because it is a small instance of the
shape that recurred here at full size — a name and a docstring asserting a
property that lives in a *different* test than the reader is looking at — and a
reader who checks only the first one concludes the value pin is the guard.

One strengthened predicate in the orchestrator's test file passes on the
delivered file partly *because* the same fix round retitled a table cell in that
file. The property still generalizes — it survives a full prose rewrite and goes
red on deletion — but a fix that tightened its source document to satisfy its own
new test is a shape that could hide a real circularity in a less careful
instance. Separately, one strengthened predicate's docstring justifies itself
with a hazard that measurement showed never occurs in that document.

All three parked as accuracy residues in tests whose properties hold: the cost
of each is one misleading docstring, and the benefit of an edit is not worth
re-measuring predicates that are currently pinned in four directions.

### `tests/unit/test_live_marker.py` writes into the tracked tree

Its subprocess helper writes `tests/test_generated_<name>.py` into the
repository's own `tests/` directory — on purpose and for a good reason, since
the property under test is default *collection* behaviour with
`tests/conftest.py` in scope, which an in-process run would not reproduce. The
ordinary path is clean: the file is unlinked in a `finally`.

Two things are not covered, and no `.gitignore` pattern matches the name. A
hard-killed run leaves a file in the tracked tree that looks committable and is
named as though a tool generated it deliberately, which is exactly the shape a
`git add -A` sweeps up. And the write makes the suite unrunnable from a
read-only checkout, where every other test here is a pure function of its
inputs and a `tmp_path` — the path is relative, so it is a fact about the
working directory rather than about the repository.

Parked as the smallest of these, and half of it is one line: a
`tests/test_generated_*.py` entry in `.gitignore` closes the looks-committable
half outright. The other half is not a relocation, which is why it is parked
rather than done — the default skip lives in `tests/conftest.py` and applies to
what is collected beneath it, so a file written into `tmp_path` is a file the
hook under test never sees. Moving the write means finding a different way to
put the repository's own `conftest.py` in scope.

---

## Before you file a bug against the repair loop

### A rejection does not loop back to `rb-propose`

Not once, and not for a cell that matters. When `rb-challenge` rejects a
scenario, the cell that scenario claimed becomes an honest **hole** in the
coverage report, and the run reports it as one. The re-dispatch of `rb-score`
that follows a rejection is a recompute, not a reopening.

This surprises people, because it means a run can *lose* coverage between gate 2
and gate 3 and finish anyway — measured on a real run, where the cell count fell
by one when a rejected scenario stopped crediting a row. If that looks like a
missing repair path, it is not: it is the repair path being deliberately absent.

Deferred on purpose rather than forgotten, and the reasoning is worth keeping
even if it is ever reversed: looping after instantiation makes run cost
unbounded and the experiment much harder to read, and "87%, three cells lost to
rejected scenarios" tells a reader more than a 100% that hides how it got there.

### A re-challenge is indistinguishable from a first challenge

The repair loop for a `re-seed` is "re-dispatch `rb-instantiate`, then
re-challenge." Measured: a plain challenge re-dispatch found a complete verdict
in its one `writes` slot and correctly declined to re-judge, so the loop's
second half was a no-op that left a verdict describing a seed which no longer
existed. Once the stale verdict was moved aside by hand, the genuine
re-judgment returned `accept`.

**The repair worked; only the signalling was missing.** There is no field in
`verdict-0.1.json` that says "this is a re-judgment", so a stage cannot tell the
two situations apart from what is on disk.

Parked because the fix is a schema field plus a prompt change plus an
orchestrator step, and because the manual workaround is one file move that a
human at gate 3 can see the need for. It is owed, and it is cheap; it is not
free.

### A re-seed whose remedy lies outside `rb-instantiate`'s `writes` cannot be repaired at all

Measured. A rejection notice asked for a `capability_refs` change in
`02-scenarios.json`, which `rb-propose` owns. The `rb-instantiate` member
verified that changing its seed and its oracle could not close the notice, and
declined — correctly, since that file is not in its `writes`, and
`rb-orchestrate` shuts the propose door explicitly (see the entry above). That
scenario was the run's one unrepairable case and the sole reason `emit` exited
1.

Parked because the two obvious remedies are both worse than the hole. Widening
`rb-instantiate`'s `writes` to reach `02-scenarios.json` gives a fan-out member
write access to a barrier artifact every sibling reads. Reopening the propose
loop is the unbounded path the entry above rules out. What is actually owed is a
*disposition* for this case — a way for the pipeline to record "unrepairable
here, remedy lives upstream" as a first-class outcome rather than as a stage
declining and an `emit` exit 1.

### The rejection notice cannot express an escalated re-seed

The notice a score re-dispatch carries quotes three fields from the verdict —
`uniquely_determined`, `derivable_without_guessing` and `notes`. All three are
the adversary's own judgment fields, and none of them encodes a *rejection
reason*. So `rb-score` cannot choose a value from `rejected_reason`'s enum
(`ambiguous`, `not_derivable`, `wrong_label`, `out_of_scope`,
`blocked_by_gap`) for a re-seed that has been escalated to a rejection. On the
one occasion this arose, `rb-score` reported that back rather than guessing,
which is the correct behaviour and also a stall.

Parked with the entry above it, because both are the same missing concept: the
verdict vocabulary can express what the adversary concluded and not what the
pipeline should now do about it. Fixing either one alone leaves the other
stalling on the same run.

---

## Deliberately out of scope

None of these is an oversight. Each was considered and left out, and the reason
is worth knowing before you propose adding one — a few have since drifted from
"deferred" to "owed", and where that has happened the entry says so.

- **No live-backend binding.** Every emitted suite runs against the synthetic
  seeded world in its package, never against a running instance of the target.
  Binding to a live backend requires a second binder for the instantiate and
  challenge stages, and a live target makes a run non-reproducible — which
  removes the property the whole measurement rests on. Out of scope until there
  is a reason to trade it away.
- **Source code is a declared input kind that no run has extracted from.**
  `source_code` is a first-class kind in the manifest schema, `rubrica survey`
  classifies it, and `intake` registers it — the plumbing is real. But no run
  has filed claims from a source file, and no skill's prose addresses one. The
  one real run that had the option deliberately assembled a tool-schema
  document from a source module instead of registering the module, on the
  grounds that an input should be a *contract* rather than an implementation.
  That preference is a position, not a limitation; the absence of evidence
  either way is the limitation.
- **One target per run.** One target is enough to test the hypothesis, and a
  multi-target run would make a stage's variance impossible to attribute.
- **No difficulty calibration.** A verdict can flag `difficulty_overstated`,
  and a scenario declares a `hop_depth`, but nothing calibrates difficulty
  across a suite. The original ruling was to decide after seeing a real spread
  from the smoke stage; two real spreads now exist and the decision has still
  not been taken, which makes this owed rather than merely deferred.
- **The pipeline is not a declarative manifest.** `paths.STAGES` is a Python
  tuple, and each stage's shape lives in code and prose. A declarative pipeline
  manifest is probably where this design converges after another iteration or
  two, and it is the wrong place to start — the stage set is still changing.
- **Projections are admitted, never produced.** `rubrica adopt-projection`
  admits a hand-authored artifact into the catalogue structurally, without
  touching the corpus or the run's identity. Nothing *generates* one: a
  projection fan-out stage is costed and unbuilt. The artifact exists first on
  purpose, because it is the expensive half to add later.
- **Plugin packaging.** How a dispatched skill reaches the `rubrica` CLI when
  Rubrica ships as a plugin rather than as this repository is unsolved. The
  design is compatible with it — every stage reads only run artifacts — but
  packaging is the other half of "standalone plugin" and no work has been done
  on it.

---

## If you think an entry here is wrong

Some of these would be closed by a measurement rather than by an argument, and
several by a design ruling that nobody has made. The way to re-open one is to
engage the reasoning in its **why it is parked** paragraph and say what changed —
a second real run, a ruling on partial seeds, a harness that can supply an effort
level. "This looks like a bug" is what the entry already says.

If you find something that is genuinely not here, it belongs here: add the
entry in the same three parts, in the group a reader would be about to work in.
An undocumented limitation costs somebody a fix round, which is the thing this
file was written to stop.
