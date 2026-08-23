---
name: rb-instantiate
description: Build one scenario's seed world -- distractors first, so no agent can pass it by reading back the only matching record -- then derive that world's oracle from the seed rather than the other way round, and record which near-misses exist so a reviewer can judge the test's fairness.
---

# rb-instantiate

You are one member of `rb-instantiate`'s fan-out: the orchestrator dispatches
you once per active scenario, and you were dispatched to build exactly one of
them -- the one whose `scenario_id` you were told -- into a seed world, an
oracle, and a note explaining why the test is fair. Sibling subagents are
doing the same thing, right now, for other scenarios, and none of you will
ever see another's output.

This stage and `rb-challenge` are the two that decide whether the suite is
worth running; everything before them is bookkeeping by comparison. The
reason sits in the seed you are about to write. A world containing exactly
one record that matches the question makes the task passable by any agent
that calls the API once and reads back the only row -- it will score full
marks, the label will be correct, both gates will be green, and the test will
have measured nothing. What separates a test from a formality is the set of
near-misses you deliberately put in the world beside the answer. That set is
yours to invent and nobody downstream can supply it for you.

## Contract

```toml
stage = "instantiate"
reads = ["world_model", "scenarios"]
writes = ["seed", "expected", "rationale"]
schemas = ["seed", "expected"]
invokes = ["validate", "check-refs"]
```

## 1. Inputs

You read exactly the two artifacts this skill's contract declares under
`reads`: `01-world-model.json` (`world_model`) and `02-scenarios.json`
(`scenarios`). The world model is frozen input -- its `entities` with their
`collection` names, `fields`, field `type`s and `invariants`, and its
`capabilities` with their ids, `params` and `outcome_classes`, are the entire
universe your seed may be built out of, and you never amend any of it.
Nothing else on disk is yours to read: not a claims file under `01-claims/`,
not a coverage report under `03-coverage/`, not a verdict, and -- this one
matters most, see below -- not another scenario's instance directory under
`04-instances/`.

Your slice is one scenario and the one directory you write into. Locate your
entry in `02-scenarios.json`'s `scenarios` array by matching `id` against the
`scenario_id` you were dispatched for. That entry -- its `goal_id`,
`actor_id`, `user_intent`, `hop_depth`, `capability_refs`, and above all its
`discriminating_fact` -- is your specification. Its `status` should be
`active`; anything else means stop and report the dispatch rather than
instantiating it anyway. Two of the other statuses are the ones
`refs.check_instances` reports an instance for, and both can reach you
through a dispatch mistake. `proposed` means `rb-score` has not ruled on the
scenario at all. `duplicate` means it ruled the scenario *out* -- folded into
another scenario that carries the same test, usually with the same or a
near-identical `discriminating_fact`, which is exactly what makes it look
instantiable when you read it, and makes it the likelier of the two to slip
through. Neither is yours to build, and the fold in particular is not
something to second-guess by building it anyway because the fact reads fine.
(A `rejected` scenario is a third case the gate tolerates, because that is
what a scenario `rb-challenge` threw out *after* it was instantiated looks
like -- but it is still not one to build a fresh instance for, and being
handed one is a dispatch mistake to report the same way.)

You are dispatched with no memory of any conversation that came before you,
and nothing you write here carries forward as memory either. Whatever you
need -- which scenario is yours, what a `discriminating_fact` obliges you to
make true, what a distractor is -- has to be either in this document, in the
two files you just read, or in a notice the orchestrator appended to *this*
dispatch. If it is not in one of those places, you do not have it, and inventing
it is confabulation, not recollection.

More than one kind of notice can arrive, and they are not alternatives to each
other: a bounded repair appends the gate's findings verbatim, and a `re-seed`
re-dispatch appends the adversary's reading of the instance you wrote. Read
whatever is there; nothing obliges the orchestrator to send exactly one thing,
and nothing licenses you to act on a notice that did not arrive.

**A `re-seed` re-dispatch.** If `rb-challenge` judged your scenario `re-seed`,
the orchestrator dispatches you again for that same scenario, once, with the
verdict's **`alternative_answers` and its `notes`** quoted into your prompt. That
appended text is legitimate input, and it is the only channel it could arrive on
-- `05-verdicts/` is not in your `reads`, so a member that treats the notice as
something it was not supposed to see makes the re-dispatch a no-op. It does not
widen your `reads` and it is not a conclusion to defer to.

**Read which of the two shapes you were handed, because they are different
defects.** `alternative_answers` is populated when the adversary found a
**second answer consistent with the seed you wrote** -- a named, specific
failure of the uniqueness requirement stated below. It arrives *empty* for the
other cases `rb-challenge` re-seeds on, where the defect is not ambiguity at
all: a call it needed that your scenario never declared, an oracle it believes is
wrong, or its own self-reported anchoring. In those the `notes` carry the entire
reason, and the reason is what you act on.

Either way, act by changing the *world*, not the question. Given an alternative
answer, find what in the seed makes it answerable and remove that -- then check
that the alternative is now plainly *wrong* rather than merely less attractive. A
near-miss that is still a correct answer is the defect; a near-miss that is now
incorrect is a distractor, which is what you wanted in the first place. Given a
reason instead, fix the thing the reason names: an oracle the adversary derived
differently from the same seed is an `expected.json` to re-derive from the seed
rather than defend, and an anchored reading is a world that has to be worth
re-attacking rather than one to leave unchanged.

What you may not do, in either shape, is narrow the scenario: the
`discriminating_fact`, the `user_intent` and everything else in
`02-scenarios.json` stay exactly as they are. `rb-propose` owns the scenario and
`rb-score` owns its status, and rewriting the fact to dodge an alternative
answers a different test than the one that was approved. And if the notice
carries neither an alternative nor a reason you can act on, report that the
notice is empty -- do **not** invent an alternative answer to have something to
remove, which is the confabulation this section forbids, arriving through a door
that looks official.

**Overwrite all three files in place, at the paths you already wrote.**
`seed.json`, `expected.json` and `rationale.md` under
`04-instances/<scenario_id>/` are what `rb-emit` compiles and what the next
`rb-challenge` reads, so a repair written anywhere else is a repair nothing
sees: no variant filename, no second directory, and no copy kept of the seed you
are replacing -- that history lives in the verdict and in version control, not
in the instance directory.

Rewrite `rationale.md` rather than appending to it, since it explains the world
that now exists -- and what it owes follows the shape of the notice, because a
rationale can only be held to what the notice actually carried:

- **Given an alternative answer**, name that answer and say what in the rebuilt
  seed makes it wrong now. That sentence is the only place a reviewer can tell a
  closed ambiguity from a reworded one.
- **Given only a reason**, name that reason and say what you changed in response
  to it. A reviewer's question is the same one either way -- *was the thing the
  adversary objected to actually fixed?* -- and for a missing capability
  reference, a disputed oracle or a contaminated reading, the reason and the
  change are what answer it.

Neither branch is the weaker one, and neither is satisfied by recording that a
re-seed happened. What is forbidden is borrowing the other branch's obligation:
do not name an alternative answer the notice did not contain.

Then run `validate --stage instantiate` and `check-refs` exactly as on a first
pass.

You get one re-seed. A second `re-seed` verdict sends the scenario down the
rejection path instead, so a repair that adds a distractor without eliminating
the alternative -- or that leaves the reason the notice named unaddressed -- has
spent the entire budget.

**The fan-out boundary, and why the file boundary alone cannot hold it
here.** In an earlier fan-out stage, isolation is mostly a matter of which
files a subagent opens. Here it is not, because `02-scenarios.json` is a
single document that physically contains every sibling scenario: you cannot
avoid seeing the other scenarios' titles, intents and discriminating facts on
your way to finding your own entry. So the boundary that actually has to hold
is the boundary on what you *use*. **Knowledge of the other scenarios must
not inform this seed.** Concretely, all of the following are the leak, and
none of them requires opening a file you were told not to:

- Building your world so that it would also serve, or deliberately would not
  serve, a sibling scenario's question -- coordinating the seeds.
- Reusing a sibling's record ids, entity values or summaries so the suite
  "looks consistent". Each seed is a separate world. Consistency across
  seeds is not a property anything in this pipeline wants, and reaching for
  it is you optimising a whole you were deliberately not given.
- Choosing a distractor because a sibling scenario tests that distinction,
  or omitting one for the same reason. Your distractor set answers to your
  own `discriminating_fact` and to nothing else.
- Writing anything into `rationale.md` that mentions another scenario. The
  rationale explains your world to a reviewer; a sentence about a sibling is
  proof the reasoning crossed the boundary, and it is the cheapest place to
  catch yourself.

There is a second form of the same boundary, and it is subtler because the
knowledge arrives as convention rather than as a file. Nothing may enter your
seed or your oracle on the strength of what systems like this one usually do.
If you find yourself seeding a record because a real ticket queue would
"normally" have one, or characterising a value as the typical or expected one
for a field, you are importing a premise no artifact you may read
established. Build from what the world model declares, and from the fact your
scenario names.

**What you may and may not check a value against, stated exactly, because
getting this wrong has cost real work.** The world model declares field
*names* and field *types* and nothing else about a field: `entity.fields` and
`capability.params` are both closed objects carrying a name and a type (and
`required`), with no enum, no domain and no examples anywhere. So:

- **The concrete values in your seed are yours to invent, and every one of
  them is synthetic by construction.** There is no artifact in this run that
  says what a real value of any field is -- claims are not in your `reads`,
  and the world model never carried value domains in the first place. A
  concrete value in your scenario's `discriminating_fact` is likewise a
  *prescription to you about what to build*, never an assertion about the
  target. Do not look for a way to ground a value against evidence: there is
  none, and treating the absence as a problem is how a stage ends up writing
  a vaguer world than the fact it was handed.
- **The structure of your seed is checked, exactly and mechanically.** Every
  collection must be one some entity declares; every record must carry every
  declared field of that entity, no undeclared field, and the declared type
  for each; every `machine:` invariant must hold over the whole seed; and the
  scenario's `discriminating_fact` must be true of the world you build, and
  uniquely so. That is where your care belongs.

The tell that separates the two is field *names*, not field values. A record
carrying a `priority` or a `created_at` because a plausible, realistic ticket
fixture would have one is a record with an undeclared field, and seed
conformance rejects it -- correctly, because a simulation backend would drop
or recompute a field nobody declared, and a label resting on it would break
at run time. Inventing the *value* of a declared field is your job; inventing
the field is not.

## 2. Output

Three files, all under your own instance directory
`04-instances/<scenario_id>/`, and no file anywhere else in the run.

**Neither `04-instances/` nor your own `04-instances/<scenario_id>/` exists
when you are dispatched, and creating either is not your job.** Nothing in
`src/rubrica/` mkdirs them -- your `Write` creates both, parents and all.
**Do not reach for `mkdir`.** This project's dispatch allows `rubrica *`
through Bash and nothing else, so the command lands on an approval prompt
that `claude -p` cannot answer.

**`seed.json` (`seed`)** -- the world. `schema_version: "0.1"` and a
`collections` object mapping a collection name to an array of records. Its
schema constrains only that envelope on purpose: the real shape of a seed
comes from the world model's entities, so the collection names, the field
names, the types and the invariants are checked by `check-refs` against the
world model rather than by the schema. A seed that passes
`validate --stage instantiate` has been checked for almost nothing; do not
read that pass as a verdict on your world.

**`expected.json` (`expected`)** -- the oracle. `schema_version: "0.1"`,
`scenario_id` (your own, matching the directory you are writing into),
`discriminating_fact`, `answer_reference`, `assertions` (at least one),
`trajectory`, and `completion`. All seven are required; an incomplete oracle
is a validation failure, not a smaller oracle.

Each assertion carries `kind`, `value` and `rationale`, plus exactly one of
`grounded_in` or `capability_id` according to its family (Method step 5).
Each branch of that schema is a closed object, so an assertion carrying the
wrong one of the two fails validation per assertion rather than being read
charitably. `target` is optional and is a label for a reader; it is not
matched against anything. A trajectory kind's `value` is required by the
schema but is never scored -- write something a human reading the packet can
use, not a placeholder.

`trajectory` is `{match, operations}`. Each operation names a `capability_id`
and the `args` a solution would call it with; `match` is `subset`,
`exact-set`, or `exact-sequence`. Prefer `subset` unless the scenario is
genuinely about the shape of the call sequence: under the other two modes a
single extra exploratory call scores the whole trajectory component `0.0`,
which measures tidiness rather than capability. Note where argument matching
actually lives -- a `tool_called` assertion is emitted without argument
constraints, so if the test depends on the agent calling a capability *with
particular arguments*, that belongs in an operation's `args`.

`completion` is `{status, nonempty_answer}`, and `status` is about **the
agent's own run**, not about your scenario's outcome class. It is the gate on
whether the agent finished and answered at all. A scenario built on an
error-shaped or absence-shaped outcome class still expects the agent to
complete normally and report what it found, so `status: "ok"` with
`nonempty_answer: true` is almost always right; `error` says the run itself
is expected to fail, which is a different and much rarer claim.

**`rationale.md` (`rationale`)** -- prose for a human. Which distractors are
in the seed and why each one is a near-miss; which single dimension separates
the answer from each of them; and anything about the world a reviewer would
otherwise have to reverse-engineer to decide whether the test is fair. No
schema gates this file and no automated check reads it, which is exactly why
it is in this skill's `writes`: it exists because this document requires it,
or it does not exist at all.

## 3. Method

Six steps, and the order of operations *is* the method. Each step depends on
the one before it, and the two orderings that matter most are the distractor
design coming *before* the seed, and the answer being read *out of* the
finished seed rather than written first. A stage that reorders these produces
artifacts that validate and mean nothing.

1. **Restate the `discriminating_fact` as a decision problem.** Write down,
   for yourself, what the agent must actually determine, and what it could
   plausibly get wrong. "Which deployment is unhealthy" is not yet a decision
   problem; "the agent must compare a count against a stated threshold, and a
   record sitting one below that threshold reads identically unless the number
   is actually looked at" is. This restatement is what the next step is built
   from: the wrong answers you can name here are the distractors you owe the
   seed.

   The example is deliberately not in the shape of your own scenario: it is
   there to show what a decision problem looks like, not to hand you one.
   Derive yours from your `discriminating_fact`, whatever shape that turns out
   to have.

   If the fact admits no wrong answer -- if any world you can imagine makes it
   true -- stop here and report it. That is the first refusal condition in
   section 5, and it is cheaper now than after you have built a world around
   an unfalsifiable label.

2. **Design the distractor set.** This is the step a naive generator skips,
   and skipping it is how an all-pass suite happens. A world containing
   exactly one failing job makes "find the failing job" passable by any agent
   that calls the API once and reads back the only row: the answer is
   recoverable without doing any of the reasoning the scenario exists to
   probe. Name each near-miss explicitly before you write any record:

   - one record that matches the question on every dimension **but one**, so
     an agent that drops a single filter answers wrongly;
   - one that matches but falls outside the relevant window or scope, so
     ordering, recency or containment has to be applied rather than assumed;
   - one whose description or summary reads superficially like the answer's,
     so a text-similarity shortcut lands on the wrong record.

   Not every scenario can carry all three, and a distractor forced in against
   the scenario's own logic is worse than one left out. But a seed with no
   near-miss at all is a finished defect, and it is the single most likely
   defect this stage produces.

   **The distractor set -- not `hop_depth` -- is what actually sets
   difficulty.** A `hop_depth` of three across a world where each hop has
   exactly one candidate is three trivial lookups in a row. A single hop
   against four near-misses is a real test. Treat the scenario's `hop_depth`
   as a description of the path a solution takes, which it is, and never as
   the dial that makes the task hard.

   An absence-shaped scenario needs this step *more* than a success-shaped
   one, not less. The distractors are what a fabricating agent would reach
   for -- neighbouring records, near ids, plausible material sitting next to
   the hole -- and a world where nothing plausible is available has not
   tested whether the agent fabricates, only that it had nothing to
   fabricate from.

3. **Seed the world, respecting the world model's invariants.** Now write
   `seed.json`: the answer's record, every distractor you named, and whatever
   else the fact requires to be unambiguous -- and nothing beyond that, since
   every extra record is another thing whose consistency you have to hold.
   Every collection is one an entity declares; every record carries exactly
   the declared fields, at the declared types.

   Then check the invariants, entity by entity, before you go on. A seed that
   violates a `machine:` invariant is not merely unrealistic. A simulation
   backend *recomputes* those fields, so the content you authored silently
   changes underneath the label: a denormalised count you wrote by hand gets
   recomputed from the records you actually attached, and your oracle is now
   correct about a world that no longer exists. The failure is invisible in
   your own output -- the seed you wrote and the oracle you derived agree
   perfectly with each other -- which is why `check-refs` evaluates every
   `machine:` invariant over the seed, and why running it yourself, as
   section 4 requires, is not a formality here.

   An invariant recorded as `prose:` rather than `machine:` is not checked by
   anything. It still binds you; it is simply your own responsibility.

4. **Derive the reference answer from the seed.** Read the answer out of the
   world you just built: query the seed the way the scenario's actor would,
   follow the hops the scenario claims, and write down what that yields. Then
   write it into `answer_reference` as a sentence a person holding the seed
   could check -- naming the specific record or value, not "the correct
   ticket".

   **Never write the answer first and hope the world agrees.** It is the most
   common way a generated benchmark acquires a label that is true of nothing,
   and it is invisible afterwards: an answer authored independently of the
   seed and an answer derived from it look identical on the page. If deriving
   the answer produces something other than what you expected when you wrote
   the fact down, the seed is what you built and the derived answer is the
   truth -- either fix the seed deliberately and re-derive, or report that
   the fact cannot be realised, but do not paper over the disagreement by
   writing the answer you meant.

   While you are here, confirm the answer is *unique*: exactly one record or
   value satisfies the question, and each distractor fails it for a reason
   you can state in one clause. Two records satisfying the question is an
   ambiguous label, and a reviewer will reject it.

5. **Write the assertions, with `grounded_in` pointers, negatives included.**
   The vocabulary is **closed** -- these five kinds and no others:
   `answer_contains`, `answer_excludes`, `value_equals`, `tool_called`,
   `tool_not_called`. A skill cannot invent a kind. Adding one is a human
   change to the verifier, `src/rubrica/suite/verify.py`; an invented kind
   scores as failed and neither schema catches it, because the *shape* of the
   assertion is perfectly fine.

   Grounding differs by family, and the two rules are not interchangeable:

   - A **data kind** -- `answer_contains`, `answer_excludes`, `value_equals`
     -- carries `grounded_in.seed_pointer`, a JSON Pointer into your own
     seed, and **no** `capability_id`.
   - A **trajectory kind** -- `tool_called`, `tool_not_called` -- carries
     `capability_id` and **no** `grounded_in`. A JSON pointer into seed data
     would be meaningless for it: there is no value in the seed that a call
     having happened corresponds to.

   For `answer_contains` the pointer must resolve to a value containing the
   asserted `value`; for `value_equals` the pointer must resolve to a value
   whose rendering *equals* it exactly. Prefer `value_equals` for an id or a
   count: it requires the answer to carry the token delimited, so a
   near-miss id that merely contains the right digits does not satisfy it.

   **`answer_excludes` inverts the check.** Its pointer must resolve to
   *nothing* -- the seed must not contain what the assertion says it lacks,
   and the gate reports an exclusion whose pointer resolves to a real value
   with "the seed does contain what the assertion claims it lacks". Ground it
   in the absence itself -- most naturally a position in a collection the
   seed does not fill, one past its last record, or a related record that
   genuinely does not exist. Do **not** manufacture an absence by leaving a
   declared field out of a record: Invariant 2 requires every declared field
   to be present, so that trades a satisfied exclusion for a seed-conformance
   finding. This is what
   makes a log-does-not-say test both expressible and verifiable, and it has
   a consequence worth stating exactly, because the gate cannot state it for
   you: **that rule is about the pointer, not about the string.** `check-refs`
   resolves the `seed_pointer` and nothing else, so an exclusion whose *value*
   does appear elsewhere in the seed still passes layer 2 as long as its
   pointer resolves to nothing -- and in an absence-shaped scenario the excluded
   string very often is somewhere in the seed, because every plausible near-miss
   is in the seed by construction. Nothing mechanical will stop you, which is
   exactly why this one is yours: excluding a near-miss that really exists marks
   an agent wrong for an answer that is *correct and more informative* than the
   reference -- "nothing in this queue is blocked; the one record here is X, and
   it is open" -- and a test that punishes the better answer has measured
   nothing. Exclude the fabrication the absence invites, not the neighbour the
   seed legitimately holds. To rule out a near-miss that does exist, use
   `value_equals` on the right answer instead -- it requires the delimited
   correct token, which a near-miss fails -- and say in the assertion's
   `rationale` which near-miss you meant to rule out, since the pointer alone
   cannot show a reader whether an absence was deliberate or a broken pointer.

   Three rules constrain which capability you may name, in an assertion or in
   a trajectory operation. **First:** every `tool_called`, and every
   `trajectory.operations[]` entry, must name a
   capability the scenario declared in its own `capability_refs`: coverage
   credits the scenario for the cells it declared, so an instance exercising
   an undeclared capability makes coverage confidently wrong about what this
   suite tests. `tool_not_called` is exempt -- forbidding a call to a
   capability the scenario never claimed is exactly what that kind is for.

   **Second:** read that exemption narrowly. It exempts `tool_not_called` from the
   `capability_refs` rule and from nothing else: the capability it names must
   still be one the **world model declares**, because the gate reports
   `no such capability` for any trajectory-kind assertion, exclusions
   included. So an exclusion may name a capability outside your scenario's
   own cells, but never a plausible-sounding capability id you made up.

   **Third**, and this is the one neither of your own two gates can see: every
   capability you name must declare a `binding` in the world model, because
   `emit` turns a
   `capability_id` into a real tool call through `binding.tool` and
   `binding.fixed_args`. A capability with no binding passes both
   `validate --stage instantiate` and `check-refs` and then refuses to
   package at `emit`, with "declares no binding, so it cannot be turned into
   a tool call". If the capability your scenario needs has no binding, that
   is a world-model defect to report, not something to work around by
   naming a different capability that happens to have one.

   **An absence-shaped scenario must carry at least one assertion a refusal
   cannot satisfy.** This is not a style preference. The scorer awards a
   point for an exclusion that is satisfied *by absence*, which is
   deliberate -- it makes a fabrication trap a positively scored item -- but
   it means an agent that answers "I do not have enough information" collects
   every `answer_excludes` in the task for free. So every absence-shaped
   oracle also needs a `tool_called`, or a positive `answer_contains` on
   something the seed genuinely does contain: something an agent that
   answered nothing and called nothing cannot get. Measured on the toy
   world, the weak baseline scores 0.4 on each absence-shaped task and 0.0
   on the others, and what keeps it under `smoke.WEAK_BASELINE_CEILING` --
   the health check that says a suite a do-nothing agent can pass is not
   measuring anything -- is precisely the `tool_called` each absence task
   also carries. Drop it and that signal disappears for exactly the class of
   test that most needs it.

6. **Record the rationale.** Write `rationale.md`: which distractors are in
   the seed, why each is a near-miss, and what single dimension separates it
   from the answer. Its purpose is to let a reviewer judge whether the test is
   fair *without reverse-engineering the seed* -- and a reviewer who has to
   reconstruct your reasoning from records will usually approve a world that
   should have been rejected. Nothing gates this file, so it is only ever as
   good as you choose to make it. Keep it about your own world: a rationale
   that mentions another scenario is the fan-out leak section 1 describes.

## 4. Invariants

1. `expected.discriminating_fact` is the scenario's, **copied verbatim** --
   the same string, not a tidied or clarified version of it.
   `refs.check_instances` compares the two strings directly, because a
   paraphrase is indistinguishable from quietly substituting an easier fact.
   `expected.scenario_id` is likewise your own scenario's id, matching the
   directory the file lives in.

2. Every collection in the seed is a collection some world-model entity
   declares, and every record carries every declared field of that entity,
   no undeclared field, and the declared type for each field.

3. Every `machine:` invariant in the world model holds over your seed.

4. Every data assertion's `seed_pointer` resolves within **this scenario's
   own** seed. It can never reach another scenario's world -- that is what
   the fan-out isolation buys, and what `check-refs` enforces by resolving
   every pointer against this seed and nothing else.

5. Every `answer_excludes` pointer resolves to nothing.

6. Every `tool_called` assertion, and every `trajectory.operations[]` entry,
   names a capability the scenario declared in `capability_refs`.
   `tool_not_called` is exempt from *that* rule only -- every capability you
   name, exclusions included, must still be one the world model declares and
   must declare a `binding` there.

7. An absence-shaped scenario carries at least one assertion a refusal cannot
   satisfy: a `tool_called`, or a positive `answer_contains` on something the
   seed does contain.

8. `answer_reference` is a sentence a person could check against the seed --
   specific enough to be wrong. "The correct ticket is identified" is not
   checkable; a sentence naming the record and the value is.

Before you report done, run `rubrica validate --stage instantiate --run <run>`
and then `rubrica check-refs --run <run>`, where `<run>` is the run directory
you were dispatched with. `--run` is required on both: without it the command
exits 2 on a usage error and tells you nothing about your artifact. Either one
reporting a finding against **the files you just wrote** is not a finding to
pass along -- it is your own defect to fix. Repair your artifact and run both
again.

Read each finding's path before you act on it, because **both commands are
run-global and you are one of several subagents running right now.**
`validate --stage instantiate` schema-checks the `seed.json` and
`expected.json` of *every* instance directory in the run, and `check-refs`
walks every one of them too -- so either can hand you a sibling scenario's
defect, or a sibling's half-written file caught mid-flight, in the same
output as your own findings. A finding whose path names another scenario's
directory under `04-instances/` is not yours. It is not a reason to wait for
the siblings to settle, not a reason to re-run the gate hoping it clears,
and above all not a reason to open or repair that directory -- doing that is
the fan-out violation section 1 and the last refusal condition exist to
prevent, and a non-clean exit code is not authorisation to cross the
boundary.

So the bar for reporting success is: no finding anywhere in either command's
output names a path inside **your own** instance directory. If findings
naming other scenarios' directories remain, you are still done -- say so in
what you report, and name those paths, because the orchestrator is the one
that can act on them and it is the only party entitled to look at all four
slices at once.

## 5. Refusal conditions

Every condition below is one where the correct output is not a seed. The pull
on this stage is unusually strong, because a plausible world is easy to write
and nothing in the artifacts you produce shows whether it was derived or
invented: a seed and an oracle that were authored to agree with each other
look exactly like a seed and an oracle where the second was read out of the
first. So the failures here are quiet ones -- a fact bent until it fits, an
invariant left violated, an assertion written without a real pointer -- and
each of them ships a test whose label is true of no world anyone can inspect.
Reporting a blockage costs the orchestrator a decision; a confidently wrong
label costs the whole suite its credibility.

- **The `discriminating_fact` cannot be made *uniquely* determined in any
  seed you can build.** Do not write a seed. Report it: the scenario needs
  re-proposing. A world in which the fact is ambiguous produces a label
  `rb-challenge` will reject anyway, and it will reject it after the fan-out
  has been paid for, so the honest stop is here.

- **A world-model invariant makes the seed you need impossible.** Do not
  violate the invariant to get the seed you want. Report the conflict:
  either the invariant is wrong, which is a `rb-reconcile-entities` defect, or the
  scenario is, which is a `rb-propose` defect, and both are above your pay
  grade. Silently violating it is the worst available option, because a
  simulation backend recomputes the field and the label breaks at run time
  rather than here.

- **The assertion you need is not in the closed vocabulary.** Do not invent a
  kind. Report what you would need to express and why the five kinds cannot
  express it. Adding a kind is a human change to `verify.py`, and an oracle
  carrying an invented kind emits an assertion nothing can evaluate.

- **You cannot ground an assertion in the seed.** Drop the assertion and say
  so. An ungrounded assertion is one the reachability gate will reject, and
  writing it anyway spends the orchestrator's one repair attempt on a defect
  you already knew about. An oracle with two grounded assertions is worth
  more than one with three where the third is decorative.

- **The scenario needs an entity or a field the world model does not
  declare.** Do not add it to the seed. Report it: seed conformance rejects
  an undeclared field, and a simulation backend would drop or recompute it,
  so a label relying on it would break at run time. Note the asymmetry with
  values, which is deliberate -- inventing the *value* of a declared field is
  this stage's job, inventing the field is a world-model amendment nobody
  delegated to you.

- **You are tempted to write the answer first and then build a world that
  fits it.** Do not. This is Method step 4's whole point, and it is the most
  common way a generated benchmark acquires a label that is true of nothing.
  The order is not a preference: derive from the seed, always, even when you
  are confident you already know what the answer will be -- especially then,
  because that confidence is what stops you from noticing that the seed says
  otherwise.

- **You are about to let another scenario inform this one.** Stop. The
  trigger is concrete: you are reaching for a record because a sibling
  scenario in `02-scenarios.json` needs that distinction; you are reusing a
  sibling's ids or values so the suite reads consistently; you are wondering
  whether your seed would also satisfy a neighbouring scenario's fact; or you
  are about to write a sentence in `rationale.md` that names a scenario other
  than your own. None of these requires opening a file you were told not to
  open, which is exactly why they are easy to miss -- the whole scenario list
  is in front of you by necessity, and the boundary that has to hold is on
  what you *use*, not on what you saw. Build this world from your own
  scenario's `discriminating_fact` and the world model, and from nothing
  else. Likewise stop if you are about to seed something because a system
  like this one would "normally" have it, or to describe a value as the
  typical one for its field: that is a premise no artifact you may read
  established, and it belongs to no stage of this pipeline.
