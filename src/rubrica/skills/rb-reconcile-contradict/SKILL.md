---
name: rb-reconcile-contradict
description: One fan-out member per subject: compare claim against claim within your own subject, across every input file, and record what disagrees -- resolving only what the claims themselves settle.
---

# rb-reconcile-contradict

You are one member of `rb-reconcile-contradict`'s fan-out. The orchestrator
dispatches you once per subject in `01-subjects.json`, and you were dispatched
with exactly one `subject_id` -- yours. A sibling member is doing the same
thing for a different subject right now, and neither of you will see the
other's output.

What the fan-out does *not* give you is a slice of the claims. You read every
claim your subject names, wherever it came from, across every input file --
and that is what preserves cross-artifact contradiction detection through the
split. The family is cut on output, not on claims. "The spec says one thing
and the trace shows another" is exactly the fact you exist to record, and it
is only visible because your subject holds both claims at once.

## Contract

```toml
stage = "reconcile-contradict"
reads = ["manifest", "claims_dir", "subjects"]
writes = ["contradiction_part"]
schemas = ["contradictions-part"]
invokes = ["validate", "check-refs"]
```

## 1. Inputs

You read the three things this skill's contract names under `reads`:
`manifest.json`, `01-subjects.json` (`subjects`), and every file under
`01-claims/` (`claims_dir`).

You are dispatched with a fourth thing beside the run directory, the stage
name and this file: the `subject_id` of your own slice. Never a sibling's, and
never a list. Find your subject in `01-subjects.json`, take its `claims`
array, and read every one of those claims out of `01-claims/` -- **all of
them, from every file they appear in.** Two claims in your subject that came
from two different inputs are the pair most likely to disagree, and reading
only one input's file is how that pair goes unrecorded. Claims outside your
subject are not yours to sweep; a sibling member has them.

Nothing else on disk is yours to read. In particular, no pass reads
`01-world-model.json`: it does not exist yet when you run, and on a re-run of
this family it is an answer some earlier run assembled rather than evidence
about the target. A later pass reading an earlier pass's partial *is* the
design here -- that is what each pass's `reads` list is for -- but a
re-dispatched pass does not read its own previous output: a repair hands you
findings about the artifact you wrote, not permission to reread it instead of
the claims. You are dispatched with no memory of any conversation that came
before you, and nothing you write here carries forward as memory either:
whatever you need to do this job has to be in the manifest, in the subjects,
in the claims, or in this document.

Seeing every claim in your subject at once means you legitimately see more
than any single `rb-extract` subagent did, and that is not a leak -- it is the
design. Comparing claim sets is inherently cross-artifact work; a pass
forbidden from seeing both sides could not compare them at all. The boundary
that still holds here is not about which *files* you may open -- you may open
all of them -- it is about which *knowledge* you may bring to bear while
reading them. A resolution may rest only on what the claims themselves
establish: that one claim's evidence is stronger, that a second independent
claims file corroborates one side, that a claim's own `derivation` marks it as
a guess. It may never rest on what a system "like this" usually does, because
no claim said that -- you inferred it from experience the claims do not
contain. Concretely: if `notes.md`'s claims say `get_ticket` on an unknown id
is an error and `trace.json`'s claims show it returning `{}`, the wrong move
is "APIs conventionally error on bad ids, so the notes must be right" -- that
is a convention standing in for evidence, and it would have produced the same
resolution even if `notes.md` had never been extracted at all. The honest move
is to look at what actually corroborates each side inside the claim set you
were given: does a second, independent claim support one of them, does one
claim's `derivation` mark it `reverse_engineered` from a single trace span
while the other is `stated` in a document describing the current contract? If
you catch yourself resolving a disagreement because one side "sounds like" the
normal, expected, or textbook answer rather than because some other claim in
front of you actually supports it, stop -- write `resolution: unresolved`
instead. §5 gives the concrete refusal condition this paragraph is the
reasoning behind.

## 2. Output

One `contradictions-part-0.1.json`-shaped document, written to
`01-contradictions/<subject_id>.json` (`contradiction_part`) for your own
subject id and no other. It carries `schema_version: "0.1"`, the `subject_id`
you were dispatched with, and a `contradictions` array; each entry has an
`id`, `claim_a`, `claim_b`, a `nature`, one of the four `resolution` values,
and a `rationale`.

**`01-contradictions/` does not exist when you are dispatched, and creating
it is not your job.** `01-claims/`, which you read, does exist -- an earlier
fan-out's `Write` created it, not any code path -- and nothing in
`src/rubrica/` mkdirs either one. Your `Write` creates yours, parents and
all. **Do not reach for `mkdir`.** This project's dispatch allows
`rubrica *` through Bash and nothing else, so the command lands on an
approval prompt that `claude -p` cannot answer. The triage family's fan-out
measurably lost turns to exactly that mistake, which is why this paragraph
exists.

**Write the part even when you found nothing.** An empty `contradictions`
array is not a non-answer -- it is the record that this subject was swept, and
the schema carries no `minItems` for exactly that reason.
`refs.check_contradiction_parts` requires a file per subject rather than a
non-empty one, because a missing file cannot be told apart from a member that
was never dispatched at all.

Two consequences of being a fan-out member rather than one pass:

- **Your contradiction `id`s have to be unique across every part, and you
  cannot see a sibling's part to avoid a collision.** Derive them from your
  own subject id -- one stable prefix, then a counter -- because
  `check_contradiction_parts` reports a duplicate id across parts and neither
  of the two members that collided will know which of them to fix.
- **That checker is meaningful only once every member has finished.** It
  reports every subject without a part from the moment `01-contradictions/`
  exists, so while the fan-out is still running most of them are missing by
  construction. A finding naming a sibling's subject is not your defect.

## 3. Method

**Read each claims file once, in bounded slices, and never re-open one you
have finished.** This is a budget instruction, not a matter of style. Measured on a real dispatch of `rb-reconcile-outcomes`, a sibling pass in this family, against a 22-input, 403 KB `01-claims/`:
the dispatch died with `Prompt is too long` after 84 turns and 80 `Read` calls,
**none** of which passed `offset` or `limit`, and the same eight claim files were
re-read three times each as the member ran out of room. It wrote nothing, so the
round cost a whole pass and produced no partial to repair.

Concretely: work through `manifest.inputs` in order, so you can always say which
files you have not opened yet; read a large claims file in slices with `offset`
and `limit` rather than whole; and when you have taken what a file offers, write
down the claim ids you are carrying forward instead of planning to re-read it. A
re-read is the one behaviour that turns a bounded read into an unbounded one, and
it does not feel like one at the time -- it feels like checking.

This pass has **no field in which a partial read can be recorded**: it carries no `inputs_seen`, so nothing downstream can tell that you read half the claims rather than all of them. That is a reason to hold the bound tighter here, not looser -- there is nowhere to confess it later.

1. **Read your subject, then read the claims it names.** Every claim, from
   every file it appears in. Note as you go which input each claim came from
   and what its `derivation` and `confidence` say -- those three facts are
   the whole of the evidence you are allowed to weigh in step 3.

2. **Compare claim against claim inside your subject.** You are looking for
   two claims that cannot both be true of the same target: one says an
   operation errors where another says it returns an empty result, one says a
   field is required where another shows it omitted, one states a rule the
   store maintains that another's evidence violates. Compare across inputs
   first, since two claims filed from the same input by the same subagent
   rarely disagree with each other. Two claims that describe the same fact
   under different `kind` labels are not a disagreement -- they agree about
   the target and differ only on a bookkeeping label, which is
   `rb-extract`'s mistake to have made, not the target's behaviour.

3. **Record every contradiction you find, rather than resolving it
   silently.** Give it a `nature` describing the disagreement, pick one of
   the four `resolution` values -- `unresolved`, `preferred_a`,
   `preferred_b`, `both_possible` -- and write a `rationale` that states
   *why*, not just which. `unresolved` is not a failure to reach a
   conclusion; for a real disagreement the claims do not settle, it is the
   only honest one, and it is the value under the most pressure to be
   dropped by a model that wants to look decisive. When you do prefer a
   side, the rationale has to name what in the claim set actually earns
   that preference -- a second, independent claim corroborating it, a
   `derivation` difference between `stated` and `reverse_engineered` from
   one trace span -- not a restatement of the conclusion with "because it
   makes more sense" attached. The toy fixture is the worked example:
   `api.json` and `notes.md` both state, independently, that `get_ticket` on
   an unknown id is an error, while `trace.json` shows one captured call
   returning an empty object; two independent artifacts agreeing is what
   makes `preferred_a` defensible there, and the rationale should say so in
   those terms, not "errors are more typical." Take that corroboration away
   -- one claim each, nothing else in the set breaking the tie -- and the
   only honest `resolution` left is `unresolved`.

4. **Write your part, empty or not.** Then gate it, as §4 says.

Every resolution you write binds every pass below you.
`rb-reconcile-capabilities`, `-outcomes`, `-entities`, `-goals` and `-gaps`
all read `01-contradictions/`, and a disagreement you record `unresolved` is
one they are forbidden to quietly settle. That is the leverage this pass has,
and the reason a resolution reached on convention rather than evidence does
its damage five passes downstream.

## 4. Invariants

1. The `subject_id` field equals the id you were dispatched with, which is
   also this file's own name. `refs.check_contradiction_parts` compares the
   two, because they answer different questions: the filename is the slice
   you were dispatched with, the field is the slice you believed you were
   working on. A mismatch means one member wrote a sibling's slice.

2. Every contradiction's `claim_a` and `claim_b` both resolve to real claim
   ids. A contradiction that names a claim nobody extracted is not a
   recorded disagreement, it is a reference to nothing, and
   `check_contradiction_parts` reports it as `no such claim`.

3. Both sides of every contradiction you record are claims your own subject
   names. A pair you reach outside your slice is one a sibling is also
   looking at, and recording it twice with two ids is two disagreements in
   the world model where the target has one.

4. Contradiction `id`s are unique across every part in the run.
   `check_contradiction_parts` reports a duplicate across parts, and you
   cannot see the sibling you collided with -- so derive the id from your own
   subject id rather than from a counter that starts at 1 in every member.

Before you report done, run
`rubrica validate --stage reconcile-contradict --run <run>` and then
`rubrica check-refs --run <run>`, where `<run>` is the run directory you were
dispatched with. `--run` is required on both: without it the command exits 2
on a usage error and tells you nothing about your artifact. The findings that
are yours name your own part file; a finding naming a sibling's subject, or
naming the subject cover, is not your defect to repair. Repair your own
artifact and run both again.

## 5. Refusal conditions

Every condition below is one where the correct output is not a tidy, fully
resolved set of disagreements -- it is one that honestly shows where the claims
disagree and where nothing in front of you settles it. A part with zero
contradictions, written over a subject whose claims actually disagree, has not
swept anything; it has erased the disagreement before anyone downstream got to
see it. You default to being helpful and to producing something that looks
finished; every trigger below is a case where that instinct is the wrong one,
and recording the mess honestly is what is actually correct.

- **Two claims disagree and you cannot tell which is right.** Record the
  contradiction with `resolution: unresolved`, and say in the `rationale`
  that nothing in the claim set breaks the tie. Do not pick one side to
  keep the part looking tidy -- an invented resolution here is a
  fact nobody stated, and every scenario built on it inherits a wrongness
  with no record of where it came from.

- **The disagreement turns on behaviour that no claim in your subject
  describes at all** -- what the operation does on a bad argument, whether an
  empty result is even possible. Record the contradiction `unresolved` and
  say in the `rationale` that the deciding behaviour is described nowhere.
  Do not fill the silence in order to break the tie: the silence itself is
  `rb-reconcile-gaps`' to record as a gap, you have nowhere to write one, and
  a behaviour you invent here arrives downstream indistinguishable from a
  fact some input actually stated.

- **You found no disagreement in your subject.** Write the part anyway, with
  an empty `contradictions` array. Skipping the file does not communicate "no
  disagreement here"; it communicates nothing, and
  `refs.check_contradiction_parts` will report your subject as unswept
  because a missing part and a member that never ran look identical.

- **You are about to resolve a contradiction, or fill a silence, because
  one side matches what a system like this usually does.** Stop. That
  reasoning is convention knowledge standing in for evidence the claims
  do not actually contain, and it would produce the same answer whether or
  not the losing claim had ever been extracted at all -- which is the tell
  that it was never really settled by anything in front of you. Record the
  contradiction as `unresolved` and let the `rationale` say plainly that no
  claim actually settled it, rather than let a well-worn convention quietly
  stand in for one.
