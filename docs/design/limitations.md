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
synthetic by construction.** A concrete value anywhere downstream of the
reconcile passes — a ticket id in a seed, a queue name in an oracle — is a
*prescription* to `rb-instantiate` about the world it should build. It is never
an assertion about the target system, because no artifact in the run carries
the information that would make it one.

So **do not raise findings that require a stage to ground a value against the
claims.** That finding cannot be satisfied by any stage, because the domains
are not in the artifacts. `rb-instantiate`'s own prose says the values are its
to invent; the schema is why.

Parked rather than fixed because adding a value domain is a schema change with
a long tail: `rb-extract` would have to decide when an observed value is
evidence of a domain rather than a single sample, the reconcile passes would
have to reconcile two claims that disagree about a domain, and layer 2 would then be
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

### The corroboration test never says what "independent" excludes

`rb-reconcile-contradict` asks whether "a second, independent claim" supports
one side of a contradiction — prose carried unchanged from the single-pass
`rb-reconcile` this observation was made against, so the gap came with it. Its worked example contributes exactly one claim per artifact,
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

### Two disagreeing claims filed under different subjects are never compared

`rb-reconcile-contradict` is a fan-out over `01-subjects.json`, one member per
subject, and a member sweeps only the claims its own subject names — "claims
outside your subject are not yours to sweep; a sibling member has them." So a
pair of claims that disagree and share no subject is compared by nobody, and the
sealed world model reaches gate 1 recording one contradiction fewer than the
corpus holds.

**Do not defend this with `survey`'s digest.** That is the analogy it invites and
the analogy is wrong, in kind rather than in degree. Triage's loss is a
*decision*: the catalogue lists every candidate, a decline names one and carries
a reason, `rb-triage` has a `digest_insufficient` disposition for the case where
it knows the digest was not enough to judge, and a human at gate 0 can overrule
any of it per candidate. A cross-subject pair is an **absence**. Nothing wrote
the pair down, so no reason attaches to it, no disposition covers it, and there
is nothing at gate 1 for a person to point at. An argument that treats the two
costs as interchangeable licenses the pair filter this design rejected, which is
why the difference is stated before the mitigation.

Why the cover is nevertheless the right shape, in the order the properties do
work:

- **It is total, and totality is mechanical.** `refs.check_subjects` reports
  every claim id in `01-claims/` that no subject covers, and says why — the
  cover must be total, or the contradiction sweep never compares that claim
  against anything. So the failure that survives is narrow: two claims each
  covered, and covered *apart*. "A claim nobody swept" is a finding.
- **Over-assignment is instructed, not merely permitted.** The subjects pass is
  told to assign a claim to every plausible subject where it is unsure, on the
  stated asymmetry that over-assignment costs a member a little re-reading while
  under-assignment costs a contradiction nobody will ever find.
  `subjects-0.1.json`'s own description records the same rule, where a reader of
  the schema rather than of the prompt will find it. A cover rather than a
  partition is what makes the mitigation a dial the pass can turn on exactly the
  claims it is least sure about.
- **It is on disk and legible to a human.** Every subject carries a
  schema-required `label`, and `rubrica gate-brief` reports at gate 1 how many
  subjects cover how many claims, how many subjects were swept, how many
  contradictions were recorded, and — whenever any were — the tally by
  resolution with `unresolved` first. A cover cut too fine is therefore a
  judgment a person can question before the world model is ratified.

The rejected alternative had none of those three. An earlier draft put a
deterministic step ahead of contradiction finding: group claims by
subject/kind/target in code and emit candidate contradiction *neighbourhoods*,
the way `dedupe-candidates` proposes pairs and never decides. Its unit is a
**pair**, so the population is of the order of n²/2 — around 174,000 at the claim
counts real runs here have produced — and only the pairs it proposed would exist
on disk. Nothing enumerates the pairs it did not propose, the prompt downstream
cannot know what it was not shown, and a human has nothing to overrule.

The decisive cost is **attribution**, and it compounds with triage rather than
sitting beside it. A thin contradiction set has four candidate explanations
today: the corpus genuinely lacks disagreement; triage declined the wrong inputs;
extract missed the claims; the sweep under-recorded. A pair filter adds a fifth —
the pair was never proposed — and the fifth is indistinguishable from the first
and the fourth. Two unattributable losses in series is much worse than one,
because a thin result can no longer be traced to a stage, and for a project whose
value is falsifiability that is a bad trade for a gateway timer.

Parked as bounded rather than closed. The residue is real, and its only
instruments are the subject-size judgment the subjects pass makes and the human
reading the cover at gate 1. Note the shape any fix would have to take: something
that compares across subjects at least once, which costs another dispatch holding
every claim — the shape the pass split exists to avoid — and not a filter that
decides for the pass. If you are about to propose one, engage the attribution
argument above rather than the throughput one.

### Every directory a fan-out writes into is created by a member's `Write`, and until 2026-08-23 nothing told the member so

`grep -rn mkdir src/rubrica/` creates exactly three of a run's directories:
`run.root`, `inputs_dir` and `slices_dir`. Every other one exists only as a side
effect of a dispatched member's `Write`, which creates parents — `01-claims/`,
`03-coverage/`, `04-instances/`, `05-verdicts/`, and, in the staged families,
`00-dispositions/` and `01-contradictions/`. That is a consistent design, and
`validate.py` states it plainly for one of them: "a directory that does not exist
until the first member has written to it". The sentence sits in a module no
member reads, and every `SKILL.md` was silent on it.

**Measured 2026-08-23, on a reservation-service run of the staged-triage
family.** An `rb-triage-rule` member dispatched into a run whose
`00-dispositions/` did not exist spent roughly seven turns and one
`dangerouslyDisableSandbox` escalation attempt trying to `mkdir` it, then named
`Write` as the way round. `mkdir` is not on the dispatch's Bash allowlist —
`scripts/dispatch-stage.sh` allows `rubrica *` and nothing else — so under
`claude -p` the command lands on an approval prompt that cannot be answered. The
dispatch was killed during the stall that followed, so whether it would have
recovered on its next turn is **not** known; what was measured is turns, budget
and an escalation attempt, not a dead run.

Of them all, `00-dispositions/` is where the wrong inference is most inviting:
`triage-slices` mkdirs `00-slices/` — the shard the member has just read — one
line above the fan-out that writes the sibling directory nothing mkdirs.
`01-contradictions/` is the same shape one family down, and its member reads a
*directory* (`01-claims/`) rather than a file, so directories-already-exist is
its ambient experience too. That second exposure is reasoned, not measured: no
`rb-reconcile-contradict` dispatch has ever run, and no run in `runs/` has ever
held either directory.

**The fix is a paragraph in each affected Output section, and the reason it is
not code is measured.** The cheaper-looking alternative — one line beside the
existing mkdir in `slices.py` — buys the triage family a directory and costs
`check-refs` a signal. All three checkers over these fan-outs key on `.is_dir()`
to tell "fan-out not started" from "fan-out in progress"
(`refs.check_disposition_parts`, `refs.check_triage_audit`,
`refs.check_contradiction_parts`). On the toy run, pre-creating
`00-dispositions/` turns `check-refs` from 0 findings to 1 (`slice s01 has no
disposition part on disk`); pre-creating `01-contradictions/` turns 0 into 6, one
per subject, and a real run has far more subjects than slices. It would also
falsify `refs.py`'s own comment that an absent `dispositions_dir` at the audit
check "means a hand-assembled or manufactured audit artifact rather than a
mid-fan-out one". And it has no counterpart for the reconcile family in any case:
the pass above `reconcile-contradict` is itself a prompt pass, so there is no
code pass to hang the mkdir on nearer than `intake`, three stages earlier.

**Parked because only the prose half is enforceable, and it is the weaker half.**
`tests/unit/test_skills_output_dirs.py` pins both directions of the statement —
that the directory really is absent at the checkpoint before its writer, and that
each skill's Output section keeps the rule in one paragraph naming `mkdir`, the
directory and `Write`. Neither predicate can reach the thing that actually
failed: whether a dispatched member *reads and obeys* the paragraph. That is what
an `exercise.md` would show, and neither staged family's fan-out has one. Until
one exists, "the prose fixes it" is a reasonable expectation and not an
observation.

One narrower thing this does not park: **widening the Bash allowlist is not the
fix.** It would grant every dispatched stage broader shell access to solve a
problem `Write` already solves, against the isolation entry at the top of this
file, which records how wide the reachable surface already is.

---

## Before you trust a number a run reports

### One exercise is one sample

Most of the pipeline's skills carry an `exercise.md` beside their `SKILL.md`,
each recording what **one** measured dispatch actually did. The prompt passes of
the `triage-*` and `reconcile-*` families are the exception, and the entries
below say what that costs. An exercise record is the only behavioural evidence
this project has, and one sample is one sample: a prompt that refused correctly
once, or built a sound world model once, has not thereby been shown to do so
reliably.

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
candidate that declares what a tool returns" — and `rb-reconcile-outcomes` builds the
coverage denominator by reading those claims, so how many of them arrive bounds
the width of the test matrix downstream.

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

### No pass of the triage family carries an `exercise.md`, and what the stage it replaced produced is not in the repository

`rb-triage-objective`, `rb-triage-rule` and `rb-triage-audit` are the skills
without one. For them the explanation is that none has ever been dispatched,
which is the entry directly below this one. For the single `rb-triage` stage
this family replaced it was **not** that: that stage was dispatched at least
twice
against a real, non-toy target. One of those runs catalogued 351
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
shorter life than most — and the skill those dispatches exercised has since been
deleted, so what survives of them is a catalogue and a ruling on one disk, plus
the numbers quoted in this file.

It matters more here than it would for another stage, because triage is what
holds **gate 0**, and gate 0 is different in kind from the other
three. Gates 1 through 3 review a judgment made from evidence already in the
run; a human overturning one of them corrects an inference. Gate 0 decides what
the run can ever know — nothing downstream of `intake` reads the corpus again,
so a candidate triage declines is gone as completely as if the corpus had never
contained it. The part of the pipeline with the least recoverable authority is
the one whose only real-world evidence is the most perishable.

Recorded here rather than quietly fixed because writing the record honestly
means transcribing a specific run's numbers, declines and gate ruling from a
machine that still has it, and an `exercise.md` assembled from reasoning
instead of transcription is worse than none at all — a reasoned number
presented as an observed one has corrupted this project's evidence once
already, and had to be retracted. So the obligation is a transcription job with
a named owner, not an edit anybody can make from the committed tree. And it is
no longer a transcription that would tell you about the code in this repository:
it is evidence about a stage that has been deleted, which is why the family that
replaced it owes its own dispatches separately.

### The staged triage family has never been dispatched, and everything measured about it is arithmetic

One prototype, four real catalogues, ten synthetic shapes, and **no dispatch.**

Every number the staged design was argued from is arithmetic over catalogues
that already existed. How many slices the 595KB / 351-candidate `parsec`
catalogue cuts into (11, largest 63KB, against 5 for appworld, 5 for tau2 and 7
for tau2 plus 200 trajectory files). How many distinct digest signatures a real
130-element trace capture carries (44). What the packer does to a synthetic
catalogue of 500 identical signatures, or 500 distinct ones, or one 200KB row
among 50 normal ones. Not one of those numbers is a model's output, and the
prototype that produced them was thrown away rather than shipped. No pass of the
family has been dispatched once, against the toy world or anything else.

**So the claim the whole design rests on is unmeasured.** The design says a
member dispatched over a 64KB shard produces a *better* record than one
dispatched over 595KB — better because the input fits, because the member can
attend to every candidate in it rather than to whatever survived compaction, and
because a bounded read cannot exhaust a budget before it writes. What is
actually established is much narrower: the single dispatch **did** die, twice
and in two different ways, and the slicer **does** produce shards a dispatch can
hold. That a dispatch which completes produces a better *judgment* than one
which died does not follow from either fact, and nothing in this repository has
measured it.

It is entirely possible for every pass to run clean and for the assembled record
to be worse than the monolithic stage's. Members ruling on scope from a slice
they cannot situate; an objective pass naming surfaces from directory names and
byte counts; an audit reasoning over parts whose candidates it never read; a
near-duplicate admitted twice because no member saw both. Each of those is an
entry in this file, each is a cost this design took on deliberately, and not one
of them has been observed in either direction. The gain is a hypothesis of the
same kind, and it is the one that justified the work.

The test suite cannot close this and is not the instrument for it. It proves the
partition is total and disjoint, that the shards match the plan, that the seal
refuses rather than half-assembles, and that each skill's prose says what its
contract says. What no test can reach is whether a dispatched model followed the
prompt — which is what the live exercises exist for. The obligation is therefore
one dispatch per pass against a real target, one `exercise.md` each stating what
happened rather than what should have happened, and the willingness to correct
every entry this design added to this file wherever the arithmetic guessed
wrong. Until that exists, the staged family is a well-tested hypothesis about
judgment and not a demonstrated improvement in it.

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

### The coverage denominator is arithmetic done by code, so it is no longer a checkable claim about a prompt's output

The single-dispatch `rb-reconcile` computed the frozen denominator itself, and one
of its stated invariants was that `denominator.capability_cells` equalled the
capability × outcome-class pairs it had actually written. `refs.check_world_model`
checked exactly that: a number a prompt wrote, against the model that same prompt
wrote. `reconcile-seal` now computes both fields while assembling the partials,
and the check still recomputes both — `capability_cells` as
`len(refs._cells(world))`, `goals` as the length of the model's `goals` array —
against numbers the same code derived from the same lists. **For any world model
this pipeline now produces, both comparisons are identities.** They can fail only
if `reconcile.seal` and `refs.py` come to disagree about the arithmetic, or if
somebody hand-edits a sealed world model.

The scope of that sentence is load-bearing, because the tree still holds world
models the pipeline did not produce. `tests/fixtures/toy-contradiction/recorded/`
and `tests/fixtures/toy-gap/recorded/` are committed output of the superseded
single-dispatch `rb-reconcile`, denominators included, and
`tests/unit/test_refusals_live.py` recomputes the cell count against one of them
— so over a recording, `check_world_model` and that live assertion are still
genuine checks of a number a prompt wrote. The check did not become vacuous; it
became vacuous *for new runs*. Re-recording either fixture against the
`reconcile-*` family would close the last place this property is measured on a
prompt, which is a reason to keep the recordings as they are rather than to
refresh them for tidiness.

One precision, because getting it wrong is how that identity would break in the
direction nobody notices: `capability_cells` counts **distinct**
`(capability_id, outcome_class_id)` pairs. `refs._cells` is a set comprehension
and the check compares against its length, so the seal builds the same set. A sum
of per-capability outcome-class counts agrees with it only until a capability id
or an outcome-class id repeats, at which point the sum is simply the wrong
number; the seal carries a comment saying not to "simplify" it back into one. Do
not describe this field as a total of outcome classes anywhere — the total is the
spelling that diverges.

The ruling is that this is the right trade, for the reason that makes `emit` code:
arithmetic is not judgment. Which outcome classes a capability has is judgment and
belongs to a pass; counting the pairs afterwards is something code does exactly,
every time, and a prompt asked to do it spends its think on arithmetic instead of
on the merge — the opposite of what a bounded pass is for.

What was lost is not correctness. It is an **observation**: one of the few places
where a prompt's output was checkable against a mechanically derivable truth, in a
design whose whole value is how many such places it has. Recorded here so the loss
is not rediscovered as a hole in layer 2 and closed by moving the count back into
a pass. Keeping the identity is deliberate: as an identity it still catches a
hand-edited world model and a divergence between the two spellings of the count,
which is worth more than the line it costs.

### Whether the gateway's contended connection pool is per-API-key or global is unknown

`rb-orchestrate` runs the `reconcile-contradict` fan-out **at most three members
at a time**, and that number is not a judgment about what this machine can drive.
It is there because envoy in front of the shared gateway returns `upstream connect
error or disconnect/reset before headers. reset reason: connection timeout`
intermittently once five or more dispatches are streaming output concurrently,
while one to three was measured clean. A subject cover is a cover, so this is the
widest fan-out in the run and the one most likely to reach that boundary.

What the cap cannot tell you is whose problem exceeding it is. If the contended
pool is per-API-key, a wide fan-out costs this run its own stability and nobody
else's, and the cap is a robustness setting a later measurement could raise. If
the pool is global, a wide fan-out degrades other people's runs while they are
using the same gateway, and the cap is an obligation rather than a tuning
parameter. The two readings give different answers to "may I raise it?", and
nothing in this repository distinguishes them.

**Attributed, not confirmed: nobody has read the envoy config.** "Contended
connection pool" is an inference from a symptom — a stalled stream reported with
no HTTP status rather than a `429`, and gateway health checks green throughout. It
is the most plausible account of what was observed; it is not a verified
mechanism, and it must not be repeated as one. This attribution has the shape that
gets repeated anyway: it is short, it explains everything it was written to
explain, and the configuration that would falsify it belongs to somebody else.

Parked because settling it means reading a configuration this codebase does not
own, and because three is defensible under either reading, so no run is waiting on
the answer. One thing not to do while it is open: do not reason from the cap to
the pass split or back. The split addresses one over-long request that returns no
bytes; the cap addresses several requests generating at once. `rb-orchestrate`
says so in the same section as the cap, and a reader who "fixes" either by
reasoning about the other has removed a mitigation and fixed nothing.

### The premise the pass split rests on has not been measured, and neither has the one under the outcomes pass

Two hypotheses, both load-bearing, both stated here as hypotheses because nobody
has measured either.

**"A bounded pass needs a shallower think, so time to first byte stays under
300s."** That is the reason `reconcile` is a sequence of passes closed by a code
seal rather than one dispatch: the gateway closes a streaming connection that has
produced no bytes at around 300 seconds, and the single-dispatch stage had to plan
the whole merge before writing anything. **Nothing in this repository measures
time to first byte.** A manifest stage entry holds `model`, `effort` and
`skill_sha256` under `additionalProperties: false`, so there is nowhere to record
a timing even if something took one, and no script here records, extracts or
reports one. The premise is therefore exactly as strong as the reasoning behind
it, which is: a smaller job is a shorter think. It has to be measured per pass on
the first real dispatch of the family, and the number belongs in that pass's own
`exercise.md` — none of the passes carries one yet.

Know what a negative result would mean, because it is easy to overstate: if a
pass still stalls, the split has **narrowed** the problem to one pass rather than
solved it. That is progress — a stall attributable to `reconcile-outcomes` is a
far smaller thing to fix than a stall attributable to "reconcile" — but it is not
the claim this design makes, and reporting it as that claim would file a
hypothesis in this project's evidence as a measurement.

**"Quantifying over a capability list read from a file is at least as strong as
quantifying over one just written."** `rb-reconcile-outcomes` opens its method
with "for each capability in `01-capabilities.json`", and cites a measurement for
the quantifier: "for every capability" produced every outcome-class cell a real
run needed, while an unquantified instruction to group claims dropped 45% of
them.
That measurement was taken **with the capabilities in the same turn** — the
dispatch had just written them. Reading them from a file instead is the stated
point of splitting capabilities from outcomes, and it is plausibly the stronger
arrangement, because a list on disk can be reread and checked against. It is not
known to be. Re-measure rather than assume the number carries over, and remember
what the standing rule above says about it: one exercise is one sample, so 45% is
one dispatch's number even in the arrangement where it was measured.

Parked because both are measurements owed to a real dispatch, and neither can be
taken from the committed tree. Written down now rather than when somebody runs the
family, so that the first run's numbers land against a premise already on the
record instead of quietly becoming the premise.

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

`rb-triage-objective` writes an `objective_review` block asserting whether the
selection supported the objective it was given. A triage that silently re-scoped
and then wrote `supported: true` produces an artifact **both gates pass**.

Nothing mechanical catches it, and nothing can: the claim is about the
relationship between an instruction and a judgment, which is the same shape as
the isolation rule at the top of this document. The instruments are gate 0 and
a transcript audit.

Parked because this is a restatement of the design's central bet rather than a
defect with a fix. The mitigation that exists is structural and worth
understanding: **triage does not hold its own gate.** The same party selecting
the inputs and ratifying the selection would make the whole run unfalsifiable,
which is why gate 0 belongs to a human and not to any pass of the triage family,
and why `rb-orchestrate` never dispatches one of them at all.

### `supported` is ruled from a corpus map, not from the digests

`rb-triage-objective` runs before any candidate has been ruled on, and its input
is `request` plus a code-computed corpus map: the directory tree, kind and byte
counts per subtree, the slice labels and their sizes. It reads no digest at all.
So `supported`, the surfaces it enumerates, and each surface's weight are ruled
from directory names and byte counts — and a surface ruling made from that view
can be wrong in ways a reading of the digests would not have been. Two subtrees
whose names suggest one surface may hold unrelated behaviour; a subtree whose
name says nothing may hold the corpus's only failure evidence.

The trade was made deliberately and the reason is worth keeping. The objective
decides every subsequent call, and a pass that reads the candidates first
arrives at a scope and then rationalises the objective to fit it — the single
stage's own prose said so, which is why it read `request` before any candidate.
Ruling the objective *after* the per-candidate passes would not remove that
rationalisation; it would move it across a stage boundary, where it is harder to
see rather than absent. The thin view is what keeps the objective pass's input
from growing with the corpus at all.

What makes it a recorded cost rather than a regression is a new instrument. The
objective pass **predicts** a surface count from the map; the members
**observe** surfaces in their slices; the seal carries both, and `gate-brief`
renders the divergence at gate 0. "Predicted 7, observed 11" is a statement
about the corpus map's adequacy that nothing in this pipeline could previously
make. It does not say which reading was right — only that the thin view and the
thick view disagreed, which is the point at which a human can look.

### Slice coherence is a code judgment no test can rule on

`triage-slices` cuts the catalogue into byte-bounded slices by descending the
directory tree only where the cap forces it, clustering a container's elements
by digest signature before any byte split, and packing adjacent siblings.
Whether the cut it lands on is *meaningful* — whether `parsec/tests` is one
surface or
three — is editorial. `refs.check_slices` verifies that the plan and the shards
are the same total, disjoint partition of the catalogue, that each slice's
declared `bytes` recomputes from its own candidates, and that no slice exceeds
the declared cap. Every one of those holds identically for a partition that cuts
straight through the middle of a coherent subtree.

It matters because a slice is the unit a member reads, and a member's ruling is
only as good as the neighbourhood it can see. A slice assembled from three
unrelated subtrees invites a scoping judgment made against no coherent subject,
and it is also the configuration in which the near-duplicate residue below is
most likely.

Parked because the only instrument available is prose a human reads. Every slice
carries a `label` naming what it drew from, and `gate-brief` renders the slice
table together with every group the slicer split across more than one slice.
Measured on the four real catalogues, the labels came out legible —
`apps/splitwise +spotify +supervisor +todoist +venmo`, `domains +environment
+evaluator +gym`, `voice` — which is evidence that the cut tends to follow
structure, not proof that it did on any particular run. A mechanical coherence
check would have to know what the target's surfaces are, and that is the
judgment the pipeline exists to make rather than a fact it can look up.

### Two near-duplicate candidates in different slices are both admitted

An `rb-triage-rule` member reads one shard and never a sibling's. If two
candidates say substantially the same thing and the slicer put them in different
slices, each member rules on its own candidate on that candidate's merits, and
both are admitted. The single dispatch this family replaced could in principle
have folded one into the other; no member can, because the comparison it would
need is the one thing its shard does not contain. This is the residue of
slicing, and it is the thing slicing costs.

It is **over**-admission, and the difference from an invisible absence is the
whole reason it is tolerable. Every candidate still reaches a member and still
gets a reasoned, per-candidate disposition, so the cut drops nothing and causes
no decline. What it spends is extraction budget: a duplicate admitted twice
becomes two inputs, two `extract` dispatches, and two claim sets saying the same
thing. And the spend leaves evidence — `claim-utilisation` reports each input's
cited/total claim count for a human to read at gate 1, and a redundant input is
precisely the shape that surfaces there as claims nothing cited.

Resist the argument that this is the same class of loss as the digest's
blindness. A digest that omits the fact triage needed can make triage *decline*
something valuable, and that decline is indistinguishable, from every downstream
artifact, from a corpus that never held it. A slice boundary cannot produce that
outcome at all: its failure mode is one candidate too many, in the direction
that leaves a trace. Claiming kinship between the two would launder a recorded
over-admission into the same bucket as an unrecoverable absence.

Mitigated twice, and neither mitigation eliminates it. A container's elements
are clustered on their digest signature before any byte split, so near-duplicate
families land in one member's slice by construction rather than by luck of where
a byte count fell — that mitigation is conditional, and the entry below states
the condition. And every slice records provenance: for each group it draws from,
how many of that group's candidates are in this slice, how many exist in total,
and which other slices hold the rest. A member holding 42 of 500 elements that
share one signature can therefore say so in a disposition's `reason` instead of
ruling as though it held the whole family, and gate 0's brief flags every group
that was split. That converts an invisible over-admission into a recorded one,
which is the property a code-side pair filter could not have offered.

### Signature clustering is conditional, and specific to traces

The clustering mitigation above keys on `heuristics_fired` and `names`, and only
a `trace` digest carries either. Three regimes, and the difference between the
one that was observed and the two that were constructed matters:

- **Measured, on a real 130-element trace capture.** 44 distinct signatures, and
  the large clusters are the near-duplicate families a human would have named by
  hand: 18 AAP2-investigation elements, icinga-streaming variants at 10+9+8+4+4,
  9+3 babylon, 9 provisions-db. The fact the clustering exists to protect is in
  the same capture — `error_markers`, the digest's only structural failure
  signal, fires on **exactly one** of the 130 elements, and that element is the
  run's only evidence of what the target does when something goes wrong.
  Clustering makes it a singleton by construction, so it cannot be swallowed as
  a duplicate by a member that never saw its peers.
- **Constructed, not observed: 500 identical signatures.** Clustering
  degenerates to byte-splitting — one cluster larger than any slice, cut where
  the bytes ran out — and slice provenance is the only thing left saying so.
- **Constructed, not observed: 500 distinct signatures.** Clustering degenerates
  to arbitrary packing: every element is its own cluster, and the boundaries
  fall wherever adjacency and the cap put them.

Those last two are synthetic catalogues built to probe the packer, not corpora
anybody surveyed. They say what the algorithm does at its limits and nothing
about how often a real corpus sits there.

On a corpus whose container elements classify as `other` rather than `trace`,
the mitigation does not apply at all — such elements cluster on skeleton shape
alone.

Issue #4 was read as an instance of that, and the reading was wrong twice over.
Measured on the skeleton digests those 200 tau2 chat trajectories used to get,
the digests were **39 distinct**, largest identical group 18, differing only by
message count — not identical, as this entry previously said. They no longer get
a skeleton at all: they classify `trace`, and their digests carry `names`, which
is where the 68 toolset signatures in the entry below come from. So the
conclusion cannot rest on a skeleton carrying neither `heuristics_fired` nor
`names` — it rests on the grouping key described below, which holds before and
after.

The second correction is the ordering. The projection that made #4 look
downstream of this design — roughly 5,425 candidates and ~2.9MB, past both of
`survey`'s caps — holds only if chat trajectories *explode* into one candidate
per message. They should not: a trajectory is one episode, in which message 7 is
unreadable without 1 through 6, which is the same shape the OpenAPI ruling keeps
whole. Measured for the file-level digest instead: 443 candidates unchanged, a
472,799-byte catalogue against a 444,355-byte baseline, 7 slices. The candidate
count does not change at all and the byte figure barely moves, so there is no
ordering dependency in either direction.

That "should not" was a ruling with nothing enforcing it, and the gap was not
theoretical. The trajectory files those figures were taken on are the stripped
projection, whose per-file key intersection is one key, so `explode` declined
them by luck of what the projection happened to drop rather than by any rule
about conversations. On a metadata-rich capture of the same target the
intersection is 4 on all 200 episodes and every one carries at least 3 messages,
so 200 of 200 satisfied `EXPLODE_MIN_COMMON_KEYS` and the fragmentation this
paragraph called impossible happened — at a different scale, 200 files plus
5,800 message rows against a `--max-candidates` default of 500. The count is
not even the worst of it: the file candidate is the only row carrying the
behavioural digest, and exploding it marked that row inadmissible while
admitting one row per turn, each classified `other` and digesting to a one-turn
skeleton.

`survey`'s corpus loop now declines to explode any payload
`digest.is_message_list` admits, so the ruling is the code's rather than this
entry's. The gate is on that shape and deliberately not on `kind == "trace"`: a
list of `{spans, trace_id}` records classifies `trace` too and must keep
exploding, and all three of this repository's exploding JSON fixtures are
`is_message_list == False`.

What does not change is which grouping key those candidates get. They are corpus
candidates, not container elements, and `slices._signature` clusters only an
oversized container's elements — so signature clustering still does not reach
them, and they are grouped by `(root_index, dirname)` exactly as before.

### A chat trajectory cannot say whether it succeeded

`rb-triage-rule` §3 step 2 rules that "a failing trace is almost never a
near-duplicate of a successful one", and near-duplicate ruling is the dominant
task on a corpus of 200 trajectories carrying 68 distinct toolset signatures.
The fact that decides it is not in the file.

Measured on `tau2-bench`. The 200 trajectory files under
`data/tau2/trajectories` are a projection of the `simulations` records inside
`data/tau2/results/final/*.json`, and the projection dropped everything that
scores the episode: each simulation record carries `reward_info` — **`reward` is
1.0 for 100 records and 0.0 for the other 100** — plus `start_time`, `end_time`,
`duration`, `task_id` and `trial`, and the trajectory keeps only `messages`.

So the digest's silence here is honest rather than thin: `status` cannot fire
because no key in `_STATUS_KEYS` appears in any of the 5,182 messages, and
`error_markers` fires on 0 of the 200 because the structural error-key check
finds nothing. The only failure signal the file carries at all is a tool result
whose `content` begins with an error sentinel, present in 12 of the 200 —
nowhere near the 100 that scored 0.0 — and reading it is the value inspection
`_has_error_marker` was deliberately narrowed to exclude.

That 0 of 200 holds and stays. What it does not describe is the same target's
metadata-rich capture, on which the same check measured the exact opposite — and
for a reason that was a defect rather than a difference in corpus. Those
messages carry a top-level **`error: False`**, a field whose whole content is
that nothing failed, and `_has_error_key`'s emptiness guard tested
`value not in (None, "", [], {})` — a tuple omitting `False`. So the key fired
on **200 of 200 episodes, including all 100 that scored `reward` 1.0**, and
`error_markers` reached triage through `heuristics_fired` as a found fact about
every successful episode. Not thin but backwards, and the one assertion
`rb-triage-rule`'s near-duplicate step must never be handed, since it says
failure everywhere. Fixed by adding `False`
to that tuple, which covers a zero count with it because `in` compares by
equality. The count above is unaffected either way: the fix only ever removes a
firing, and there it was already zero.

The authoritative artifact is reachable in principle and not admitted in
practice, for a third independent reason: `results/final/*.json` is
`{info, simulations, tasks, timestamp}`, so `explode` refuses it — the top-level
dict's values are not all dicts, and a container whose records sit under one key
is invisible to explosion. Its existing skeleton digest is unusually good (43
nodes, untruncated, showing `/simulations` as `array[200]` carrying
`reward_info`, `messages` and `start_time`), so a triage member could rule on it
and request a projection. Exploding it is not affordable today regardless: the
per-record canonical size is **mean 38,723 bytes, max 111,626**, against a
65,536-byte slice cap, so `survey`'s row check would exit 2.

Parked, not fixed. Ruling: near-duplicate ruling over a chat-trajectory corpus
is unsound in a way no digest change repairs, and the fix — teaching `explode`
the records-under-a-key envelope — must wait for the row-bytes and
catalogue-bytes problem it creates.

### A trajectory wrapped in an envelope digests to almost nothing

The shape one key away from the fixed one is unrecorded here: the same
conversation with an envelope around it. Measured on one conversation of four
messages — a system policy, a user request, an assistant tool call and a tool
result:

- As a bare list — `[{"role": ...}, ...]` — the digest carries `element_counts`
  with the per-role breakdown, `request_text`, and `names` naming the tool the
  assistant called. `heuristics_fired` lists all three.
- Wrapped as `{"trace_id": "t", "messages": [...]}`, the same conversation
  digests to `element_counts: {"messages": 4}` and nothing else. No tool names,
  no request text, `heuristics_fired` listing `element_counts` alone.

The cause is the one the producer's own comment already documents for why it
walks each message rather than the list: the dict producer spends its depth
budget on the envelope, so `tool_calls[].function.name` sits one level out of
reach. Its counts heuristic still finds `messages`, which is why the wrapped
digest is not empty — it is worse than empty, because a row that carries a count
and no names looks like a thin episode rather than like a digest that could not
see one.

Classification is what routes it there, and it does so correctly. Both
`intake.classify` and `survey.classify_payload` call the wrapped payload above
`trace` on its `trace_id`, so the candidate is recognised as the capture it is
and then handed to the producer that cannot read it. Measured on the same
conversation with the envelope key dropped, `{"messages": [...]}`: both
classifiers say `other`, so that one does not reach a trace producer at all — it
gets the skeleton, which shows `/messages` as `array[4]` and one message's keys.
Neither outcome carries a tool name.

Parked, not fixed. Ruling: the fix is real and small — have the dict producer
check each `_lookup_scopes` value for a message list and hand it to the
message-list producer — and it is out of scope here for the reason that producer
already gives against widening `_REQUEST_KEYS`. It changes the shared dict
producer for every capture carrying a message list under a scope key, which
obliges re-measuring what those digest to, and there is no corpus of wrapped
trajectories here to measure it against: the trajectory files
this work was driven by are bare lists, and the envelope shape above is
constructed rather than observed. A change to the shared producer justified by a
payload nobody captured is the kind of unfalsifiable widening this register
exists to catch.

### The catalogue digest is the single point of failure for triage

Every triage decision rests on the per-candidate digest `rubrica survey`
writes. That digest is produced by code that cannot know the target, and its
insufficiency for a given candidate is only visible when triage notices and
says so.

Mitigated rather than eliminated, in two ways that are both worth knowing at
gate 0: `rb-triage-rule` has a `digest_insufficient` decline it is expected to
use, and the catalogue records which heuristics fired for each candidate, so a
human can see what the decision was made from.

Parked because the alternative is triage reading the candidates themselves,
which is the cost the digest exists to avoid — and at a few hundred candidates
that is the difference between a barrier a model can hold in context and one it
cannot.

**The arithmetic that used to sit here was three times optimistic.** It sized a
barrier over several hundred candidates at "roughly 400 bytes of digest each".
Measured on the 595KB / 351-candidate `parsec` catalogue that motivated the
staged family: the mean candidate row is **1,645 bytes**, the mean digest
**1,186**, and digests are **72%** of the `candidates` array. So the barrier was
most of a megabyte of digest, and `--max-candidates` — default 500, against an
observed death at 351 — was never going to hold it. Do not read those figures
onto the golden fixture: `tests/fixtures/toy/` is a three-file world whose rows
are an order of magnitude smaller (2,381 / 1,303 / 418 bytes), and an entry
citing a three-file fixture as evidence about real corpora would be exactly the
misattribution this project has had to retract once already.

That correction is also this entry's own prediction coming true. It closed with
"if real corpora routinely exceed it, triage needs a clustering pass, and that
is a redesign rather than a parameter." They did, and that redesign is the
`triage-*` family: a code pass that cuts the catalogue into byte-bounded slices,
a fan-out that rules one slice each, an audit over the parts, and a code seal
that assembles the record. The prediction was right about the class of fix. What
it did not say is that the cut is itself a source of new limitations, which are
the entries directly above this one.

**The clamp that redesign required is a second truncation.** Boundedness by
construction depends on no single candidate row exceeding a slice cap — a slice
holding one candidate is already minimal, so no slicer can rescue an oversized
row. Measured before the clamp existed: `ec2-pricing-json`, a 2.7MB pricing
file, produced 261 skeleton nodes and 39,162 bytes in one candidate row, 6.8% of
the whole `candidates` array in a single entry. `digest.py` therefore caps a
skeleton's total node count (`_SKELETON_MAX_NODES` is 128) as well as its
breadth and depth, and `survey` now refuses a catalogue outright, exiting 2,
when any row exceeds one slice.

A digest can consequently be cut two ways rather than one, and both are recorded
in the digest itself: `keys_truncated` where breadth bit and
`skeleton_nodes_truncated` where the node budget did. That is the whole reason
this is a cost
rather than a defect — a truncation a prompt can see is a fact about the
candidate, and one it cannot see is a lie about it. What remains true is that
this adds a second place where a fact can be lost before any model reads
anything, in the artifact this entry already calls the single point of failure.
What it does **not** license: lowering `digest_body_chars` to make catalogues
smaller. That narrows the single point of failure in order to buy bytes; the
clamp exists to make a bound enforceable, not to make digests thinner across the
board.

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
deliberate. Slug generation cannot emit an unsafe segment, and IO raises
`OSError`, which is caught.

**The second of the two triggers this entry named has since fired, for
`adopt-projection` only.** The reasoning above rested on all three blocks
reading paths a human or an orchestrator supplied rather than artifacts a stage
wrote — so a failure there was a usage error, with no stage to send a finding
back to. That is no longer true of `adopt-projection`: it parses
`00-triage.json`, `00-catalogue.json` and `00-adoptions.json`, and it now
returns findings rather than only raising. The two container-shape defects that
path can reach — a triage record or a catalogue that is readable JSON but not an
object — were closed where they arise, each returning a `Finding` naming the
artifact it came from instead of an `AttributeError`; before that, a
`00-triage.json` holding `null` exited 1 with empty stdout, verbatim the mode the
net exists to close.

Still live, and still parked, because the *placement* is unchanged: those are
the two defects that were measured, not a proof that the path has no others, and
any further unexpected exception inside `adopt-projection` exits 1 with empty
stdout exactly as before. What would close it is moving the block inside the
net — which means giving the three a finding-shaped exit for genuine usage errors
too, a wider change than this entry's cost justifies. The first trigger, a
fourth block, has not fired: there are still three.

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

### Fourteen prose predicates in the triage family's test module do not discriminate

`tests/unit/test_skills_triage_family.py` contains two shapes of prose
predicate. The windowed shape — `_window_after` / `_window_around` around an
anchor token — constrains what it claims to. The plain `"X" in body and "Y" in
body` shape does not, and there are **fourteen** of them (`grep -c "in body
and"`). The section scoping via `skills.section_body` that `CLAUDE.md` requires
is present in both, so these are not the vacuous-against-the-whole-file case
that convention already closed; they are vacuous *within a correctly scoped
section*, because a section that says a thing and a section that says its
opposite contain the same tokens.

Five were measured, each by **inverting** the claim in a `/tmp` copy under
`RUBRICA_SKILLS_DIR` — a stronger probe than deletion, because the tokens do not
vanish and the predicate is handed everything it asks for while the prose now
says the reverse. Every test in the module stayed green in every case, and
`rubrica check-skills` exited 0:

| Predicate | Inversion written into the skill |
|---|---|
| `:117` `…forbids_reading_candidate_digests` | "you **may** read every field of `candidates[]`, including each candidate's `digest`" |
| `:122` `…admits_that_a_map_is_thinner_than_the_digests` | "`supported` is a reliable verdict … this pass has no blind spot to flag" |
| `:139` `…states_which_bytes_weight_sums` | `weight.bytes` sums serialized row size, "never a candidate's own catalogue `bytes`" |
| `:168` `…explains_predicted_surface_count_is_a_prediction` | the member "has made an error … reconcile the member's count to this prediction" |
| `:268` `test_the_rule_pass_inverts_the_decline_everything_refusal` | "**Refuse** if you would decline every candidate in your slice" |

The first is the consequential one. `CLAUDE.md`'s stage table describes
`triage-objective` as the barrier that "reads the corpus map, **never a
digest**", and that property is the entire reason the pass is bounded — it is
what makes the staged family survive a corpus the monolithic stage died on.
Granting the opposite permission in the skill's own Inputs section *and* in
Invariant 1 left the whole unit suite green. The design's bounding constraint is
prose that nothing checks.

The five are not equally severe, and the difference is the mirror question
`CLAUDE.md` asks of any proposed guard. `:139`'s property is already gated
deterministically: `refs.check_objective` recomputes `weight.bytes` from the
catalogue, so that predicate is redundant belt-and-braces and its vacuity costs
nothing. `:168`'s is not gated anywhere — a member that quietly reconciles its
observed surface count to the prediction erases the divergence from the data,
and `gate-brief`'s predicted-vs-observed surface at gate 0 then has nothing to
show. `:268` inverts a **refusal condition**, the do-not-refuse that keeps the
fan-out from stranding on a legitimately all-declines slice, which
[`rationale.md`](rationale.md) uses as its worked example of decorativeness.

**The remedy is known because it was measured, in the same file.** Inverting
`rb-triage-objective`'s primary refusal condition left the unwindowed `:178`
green and turned the windowed `:184` **red**. Same prose, same file, same
section: the shape of the predicate is the whole difference. The windowed
predicates also hold in the other direction — the two tightest were recomputed
from the shipped prose and their docstrings' stated distances are exact (the
objective's Invariants anchor sits 142 chars from the nearest prohibition word
inside a radius-300 forward window, 2.11x; the audit's `deficiency_notes` anchor
208 chars from `your job` inside radius 500, 2.40x), so the 2x floor holds and no
window on this branch is a length pin in disguise.

One predicate fails in the opposite direction: `:551` asserts `"is also a claim"
in body or "is itself a claim" in body`, and rewording the audit's Output prose
to "is a claim in its own right" — meaning identical — turns it red. The
module's `_norm` handles whitespace reflow; nothing handles synonym. The
predicate is the wrong one, not the prose.

**Why it is parked.** Every one of these is a test that fails to constrain, not
shipped behaviour that is wrong: the prose the predicates were written to guard
is correct on disk in all fourteen cases, and the two check layers are
unaffected. Fixing them properly means converting fourteen predicates to the
windowed co-occurrence form, each conversion requiring its own anchor-to-token
measurement and its own both-directions probe — real work, and work that is
worse than useless done in a hurry, because a window sized by guess rather than
by measurement is the length pin this module's docstring already warns about.
The branch converted the hardest ones and left the rest in the shape it found
them. What is owed is the conversion, not a decision.

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
