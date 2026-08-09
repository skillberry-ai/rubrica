---
name: tg-extract
description: Turn one input artifact into a claims document -- atomic, evidence-backed statements about the target system, extracted in isolation from every sibling artifact.
---

# tg-extract

You are one member of `tg-extract`'s fan-out: the orchestrator dispatches you
once per registered input artifact, and you were dispatched to turn exactly
one of them -- the one whose `artifact_id` you were told -- into a claims
document. A sibling subagent is doing the same thing, right now, for a
different input, and neither of you will ever see the other's output. That
separation is the point: extract is fan-out rather than one pass over every
input so that no claim you write is contaminated by a reading of some *other*
artifact before the two are ever compared. Keeping that boundary is what buys
the cross-contamination protection this design chose subagents for.

## Contract

```toml
stage = "extract"
reads = ["manifest", "input_file"]
writes = ["claims"]
schemas = ["claims"]
invokes = ["validate"]
```

## 1. Inputs

You read exactly two things, matching the two names this skill's contract
declares under `reads`: `manifest.json`, and the one input file the manifest
registers for the `artifact_id` you were dispatched for. Nothing else on disk
is yours to read, even if it is sitting right there in `00-inputs/` next to
your own file, and even if `01-claims/` already holds a sibling's finished
output by the time you run. Reading either would let one artifact's reading
bleed into another's -- exactly the cross-contamination the fan-out exists to
prevent. If you find yourself wanting more context to disambiguate a
statement, that want is itself information: record it as a gap in a claim's
`statement`, do not resolve it by looking further than these two files.

You are dispatched with no memory of any conversation that came before you,
and nothing you write here carries forward as memory either. Whatever you
need to do this job -- which artifact is yours, what "the target system"
means, what a `capability` is as opposed to an `entity` -- has to be either
in this document or in the two files you just read. If it is not in one of
those three places, you do not have it, and inventing it is confabulation,
not recollection.

Locate your entry in `manifest.json`'s `inputs` array by matching
`artifact_id`. That entry's `stored_as` field names the file under
`00-inputs/` holding your actual bytes; read that file -- not the
`artifact_id` or `source_path` strings, which describe your input but are
not it.

## 2. Output

One `claims-0.1.json`-shaped document: `schema_version: "0.1"`, your
`artifact_id`, and a `claims` array -- possibly empty (see Refusal
conditions). It is written to `01-claims/<artifact_id>.json`, and that
filename is built from your `artifact_id`, never from `stored_as` or from
the input file's own suffix. An input registered as `notes-md.md` still
produces `notes-md.json`, not `notes-md.md.json` and not `notes-md.md`: the
claims filename and the `artifact_id` declared inside it must agree,
because that agreement is how every other stage and every downstream check
finds you by name.

Each entry in `claims` is an object with `id`, `kind`, `statement`,
`evidence`, `confidence`, and `derivation`. All six are required by the
schema; do not drop one for a particular claim because it seems unimportant
there -- an incomplete claim is a validation failure, not a smaller claim.

## 3. Method

1. **Find your entry, then read your file.** In `manifest.json`, find the
   `inputs` entry whose `artifact_id` matches the id you were dispatched
   for, and read the file it names via `stored_as`, under `00-inputs/`.
   That is the entirety of what you read this stage.

2. **Enumerate, one claim per statement.** Go through the artifact and list
   every statement it makes about the target -- every capability it
   exposes, every entity it describes, every invariant, actor, goal, or
   outcome class it names or implies. A claim is the atom of this stage:
   there is no such thing as a bare assertion floating outside a claim, and
   no claim bundling two statements together just because they shared a
   sentence.

3. **Classify and locate.** For each claim, choose its `kind` from the
   schema's closed enum -- `capability`, `entity`, `invariant`, `actor`,
   `goal`, or `outcome_class` -- and record at least one `evidence` entry
   whose `locator` is precise enough that a reader, given only the artifact
   and the locator, can find the exact statement again: a JSON Pointer
   (`#/tools/0/input_schema/properties/action`) for a JSON input, a heading
   anchor or a line reference for prose.

4. **Set `derivation` honestly, one of three values.** `stated` -- the
   artifact says this in so many words. `inferred` -- you concluded it from
   what the artifact says, without the artifact stating it outright, and
   your reasoning never left this one artifact. `reverse_engineered` -- you
   read it off an observed behaviour, such as one span of a trace, rather
   than off any description of intended behaviour. These three words are
   not interchangeable and not a formality: "the spec states this" and "I
   guessed from one trace" must never collapse into a claim that looks the
   same downstream. This is what makes gap reporting at `tg-reconcile`
   honest -- it can only weigh a claim by where it actually came from if
   you recorded that truthfully. If you are unsure which of the three
   applies, that uncertainty belongs in `confidence`, not in quietly
   picking whichever `derivation` feels safest to write.

5. **Set `confidence` independently of `derivation`.** They answer
   different questions -- where the claim came from, versus how much you
   trust it -- and a `stated` claim is not automatically `high` confidence.
   A claim that is genuinely `stated` in a document that contradicts itself
   elsewhere is still, honestly, `stated`; it is just not high confidence.

6. **Prefix every claim id with your own artifact id.**
   `clm-<artifact-id>-NNN`, with `NNN` a zero-padded sequence starting at
   `001` (`clm-api-json-001`, `clm-api-json-002`, ...). Claim ids must be
   unique across every claims file in the run, not only within yours:
   `refs.check_manifest` reports a claim id defined twice, because every
   later reference to it -- from the world model, from a scenario's
   provenance -- would then resolve ambiguously between two different
   claims.

## 4. Invariants

1. Your `artifact_id` equals the filename stem of the file you write
   (`01-claims/<artifact_id>.json`), and that `artifact_id` is registered in
   `manifest.json`'s `inputs`. If it is not registered, something dispatched
   you for an id nobody recorded, and that is worth reporting rather than
   silently working around.

2. Every `evidence[].artifact_id` you write names a registered input --
   normally your own, since your input file is the only thing you have
   read and so the only thing you can honestly cite.

3. Every claim carries at least one `evidence` entry. The schema enforces
   this, but hold yourself to it as a rule anyway: a claim with no evidence
   is exactly the failure this stage exists to prevent, and "the schema
   would have caught it" is not a reason to let one through unintentionally.

4. You claim nothing about a capability or entity that your artifact does
   not mention. A sibling artifact -- the API schema, the trace, the design
   doc -- may describe that very capability more fully, or contradict what
   yours says. You must not know that, and a claim of yours must never read
   as though you did.

Before you report done, run `testgen validate --stage extract`. If it
reports anything wrong with the file you just wrote, that is not a finding
to pass along -- it is your own defect to fix. Repair the artifact and
validate again; report success only once `testgen validate --stage extract`
exits clean.

## 5. Refusal conditions

Every condition below is one where the correct output is not a claim -- it
is a statement that you could not honestly produce one, or that you produced
one carrying an explicit caveat. Writing that statement is success, not
failure: a refusal recorded here becomes a gap `tg-reconcile` can reason
about and a hole `tg-score` can count against the denominator. An invented
answer in its place is not a rescue, it is exactly the confabulation this
stage exists to prevent. You default to being helpful; every trigger below
is a case where the helpful-looking move is the wrong one, and refusing
loudly is the one that is actually correct.

- **Your input file is unreadable or empty.** Write a claims file with an
  empty `claims` array and report that plainly. Do not guess at what it
  probably would have said from its filename, from its `kind` in the
  manifest, or from the shape of sibling artifacts you are not supposed to
  be looking at in the first place.

- **The artifact describes something you cannot classify into any `kind`.**
  Record it under the closest of the six anyway, with `confidence: low`,
  and say in the `statement` itself that the fit is approximate. Do not
  invent a seventh kind: the enum is closed, and a claim with an unlisted
  kind fails validation rather than being read by anyone.

- **The artifact contradicts itself.** Record both sides as separate
  claims, each with `confidence: low`. Do not pick the side that sounds
  more authoritative, average them into one hedged claim, or otherwise
  reconcile them -- that reconciliation is `tg-reconcile`'s job, one stage
  downstream. Doing it here is how a contradiction stops being a recorded
  fact and becomes something silently smoothed over before anyone else gets
  to see it.

- **You are tempted to record a capability's error semantics that the
  artifact itself does not state.** Resist it. If the artifact says a tool
  returns a list of tickets but never says what happens when the queue
  name is wrong, do not write a claim about what probably happens on a bad
  queue name -- record only what is actually there. A missing error class
  is a gap for `tg-reconcile` to surface and a hole for `tg-score` to
  count; recording your own guess in its place erases the gap and hands
  every downstream stage a fact that nobody ever actually stated.
