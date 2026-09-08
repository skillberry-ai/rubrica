---
name: rb-reconcile-subjects
description: Cut the claim set into subjects -- every claim assigned to one or more of them -- so the contradiction sweep has a slice to fan out over. A cover, not a partition, and never a resolution.
---

# rb-reconcile-subjects

You are the first of the `reconcile-*` passes, dispatched once after every
`rb-extract` subagent has finished and before any other pass in the family
begins. You are the barrier the design calls for: extract's fan-out is done,
and every claims file it produced is in front of you at once. Extract was
split into a fan-out precisely so that no claim would be contaminated by a
reading of some other artifact; the reconcile family exists to undo that
isolation in exactly one place, on purpose, so that "the spec says one thing
and the trace shows another" becomes a fact recorded in the world model
rather than something silently settled by whichever claims file a later
stage happened to read first.

Your own contribution to that sounds mechanical and is load-bearing: you
decide which claims ever get compared against which. A disagreement whose
two claims you file under different subjects is swept by neither member of
the contradiction fan-out, and no gate in this pipeline reports the
omission.

## Contract

```toml
stage = "reconcile-subjects"
reads = ["manifest", "claims_dir"]
writes = ["subjects"]
schemas = ["subjects"]
invokes = ["validate", "check-refs"]
```

## 1. Inputs

You read exactly the two things this skill's contract names under `reads`:
`manifest.json`, and every file under `01-claims/` (`claims_dir`) -- not one
of them, all of them. Every pass in this family reads all of `01-claims/`;
the family is split on *output*, not on claims, which is what keeps the
barrier property the single-dispatch stage had.

Nothing else on disk is yours to read. In particular, no pass reads
`01-world-model.json`: it does not exist yet when you run, and on a re-run of
this family it is an answer some earlier run assembled rather than evidence
about the target. A later pass reading an earlier pass's partial *is* the
design here -- that is what each pass's `reads` list is for -- but a
re-dispatched pass does not read its own previous output: a repair hands you
findings about the artifact you wrote, not permission to reread it instead of
the claims. You are dispatched with no memory of any conversation that came
before you, and nothing you write here carries forward as memory either:
whatever you need to do this job has to be in the manifest, in the claims, or
in this document.

Being the barrier means you legitimately see more than any single
`rb-extract` subagent did, and that is not a leak -- it is the design. What
you do with that view, though, is *not* to settle anything. You write no
`resolution`, no `nature` and no rationale; `subjects-0.1.json` has nowhere
to put one. When two claims in front of you contradict each other, the whole
of your job is to file them under the same subject, so that one
`rb-reconcile-contradict` member is dispatched over both at once.

## 2. Output

One `subjects-0.1.json`-shaped document, written to `01-subjects.json`
(`subjects`). It carries `schema_version: "0.1"` and a `subjects` array;
each subject has an `id`, a human-readable `label`, a `claims` array naming
every claim id it covers, and an optional `note`.

This is a **cover, not a partition.** A claim may appear under several
subjects; what may not happen is a claim appearing under none.
`refs.check_subjects` reports every claim id in the run that no subject
covers, and every subject citing a claim that was never extracted.

Each subject's `id` becomes a filename: `rb-reconcile-contradict` is fanned
out one member per subject and writes `01-contradictions/<subject_id>.json`.
Layer 1 already refuses an id that is not a usable path segment -- it must
start with a letter or digit and hold only letters, digits, dots, dashes and
underscores -- so that is not yours to check. It is a reason to choose short,
stable ids and to put the prose in `label`.

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

1. **Read every file under `01-claims/`.** Skim first for scope, then read
   closely enough to know what each claim is *about*. You do not have to
   judge whether a claim is true; you have to know which other claims it
   would have to be compared against if it were wrong. A claim you never
   actually read is a claim no subject covers, and `refs.check_subjects`
   will name it.

2. **Choose subjects the size a disagreement is.** A subject is a topic two
   claims could disagree inside: one operation, one entity, one rule the
   store maintains, the actors and what they want. Too coarse and the member
   dispatched over it has to hold the whole target in view again, which is
   the shape this split exists to avoid. Too fine and two claims about the
   same operation land in different files, where nothing ever compares them.

3. **Assign every claim to at least one subject.** A claim may go to
   several, and where you are unsure which subject a claim belongs to,
   assign it to all the plausible ones. Over-assignment costs a member a
   little re-reading; under-assignment costs a contradiction that nobody
   will ever find. That asymmetry is the entire reason this artifact is a
   cover rather than a partition.

4. **Open a catch-all subject for whatever is left.** Claims that fit none
   of the topics you named still have to appear somewhere, because the cover
   is total and a claim outside it is silently excluded from the sweep. Label
   it for what it is.

5. **Label every subject for the human who reads this file.** `id` is for
   the machine that fans out over it; `label` is what makes a sweep that
   found nothing legible as a claim about the corpus rather than as silence.

## 4. Invariants

1. Every claim id in `01-claims/` appears under at least one subject.
   `refs.check_subjects` reports each one that does not, and says why: the
   cover must be total, or the contradiction sweep never compares that claim
   against anything.

2. Every `claims[]` entry resolves to a claim id that actually exists in
   `01-claims/`. A reference to a claim nobody extracted is not a citation,
   it is a broken pointer, and `check_subjects` reports it as `no such
   claim`.

3. Subject `id`s are unique. `check_subjects` reports a duplicate directly,
   and a duplicate would also collapse two subjects onto one contradictions
   part filename.

4. Every subject holds at least one claim. Layer 1 enforces this -- the
   schema's `claim_refs` carries `minItems: 1` -- so an empty subject is a
   validate failure rather than a judgment call. Do not write a subject you
   have nothing to put in.

Before you report done, run
`rubrica validate --stage reconcile-subjects --run <run>` and then
`rubrica check-refs --run <run>`, where `<run>` is the run directory you were
dispatched with. `--run` is required on both: without it the command exits 2
on a usage error and tells you nothing about your artifact. `check-refs` runs
every checker the run has inputs for, so it may also name an artifact an
earlier stage wrote; the findings that are yours name `01-subjects.json`, and
those are not findings to pass along -- they are your own defect to fix.
Repair the artifact and run both again; report success only once both exit
clean.

## 5. Refusal conditions

Every condition below is one where the honest cover looks *less* tidy than
one you could have written: more subjects holding the same claim, a catch-all
with awkward contents, two claims you suspect disagree filed together instead
of neatly apart. You default to producing something clean and finished, and a
clean cover here is the one that loses a contradiction with no record that it
ever did.

- **You cannot tell which subject a claim belongs to.** Over-assign: put it
  under every subject it plausibly belongs to. Never drop it, and never
  invent a one-claim subject to hold it out of the way -- a claim in no
  subject is never compared against anything, and a claim alone in a subject
  is compared against nothing either.

- **A subject is getting large and you are tempted to split it.** Split on
  topic, never on size. If the split would put two claims about the same
  operation, entity or rule under different subjects, do not make it: their
  disagreement is then swept by neither member, and no gate in this pipeline
  reports the omission. A large subject is a slow member; a wrongly split
  one is a missed contradiction.

- **Two claims in front of you plainly contradict each other.** File them
  under the same subject and write nothing else. Deciding which one to
  believe is `rb-reconcile-contradict`'s job, and there is nowhere in
  `subjects-0.1.json` to record such a decision -- so a resolution you reach
  here is one that never gets written down anywhere. It just quietly shapes
  the cover, which is the least observable place in this whole family for a
  judgment to hide.

- **You are tempted to leave out a claim that looks irrelevant, redundant or
  simply wrong.** Do not. A claim you judge redundant is exactly the
  independent corroboration `rb-reconcile-contradict` needs before it may
  prefer one side of a disagreement, and a claim you judge wrong is one half
  of a contradiction that will now never be recorded. If it fits none of
  your topics, it goes in the catch-all.
