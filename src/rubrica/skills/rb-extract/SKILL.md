---
name: rb-extract
description: Turn one input artifact into a claims document -- atomic, evidence-backed statements about the target system, extracted in isolation from every sibling artifact.
---

# rb-extract

You are one member of `rb-extract`'s fan-out: the orchestrator dispatches you
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

That prohibition is on *opening* a sibling file, and it does not depend on
why you opened it. Harvesting its content is the obvious violation; the
quieter one -- the one that has actually happened -- is opening `api.json`
or `trace.json` to check how a locator is formatted, what heading style a
neighbour used, or how another artifact is laid out, meaning to take nothing
from it. There is no reading small enough to be allowed, because the file
boundary is the only one anybody can hold you to. Unlike your own artifact,
a sibling's content is not in your context until you open it; once it is, a
claim of yours can rest on it without your ever deciding to let it, and "I
only looked at the shape" is a distinction no gate, no schema and no reader
of your output can check. So the rule is the file, not the motive.

If it was the locator convention you wanted, you already have it. The claims
schema constrains `evidence.locator` only to a non-empty string, so the
house style is not hiding in a neighbour's file; Method step 3 below is
where it is stated -- a JSON Pointer for a JSON input, a heading anchor or a
line reference for prose. That is the whole convention, and a sibling could
not add to it. The same holds for every other question of form: it is
answered by the schema and by this document, or it is not answered, and a
neighbour's file is not the tiebreaker.

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

Everything above is about which *files* you may read. There is a second,
easier-to-miss boundary: what you may *know*. A claim may rest only on what
this one artifact actually says -- not on what similar systems usually do,
not on what a convention would suggest, not on whether an observed
behaviour strikes you as surprising. Say `trace.json` shows a call to
`get_ticket` with an id no other span establishes as valid, returning `{}`.
The honest claim reports exactly that call and that response. A claim that
adds "-- unusual, since APIs typically error on an unrecognized id" has read
no sibling file and invented no undocumented error class, so it looks clean
by every rule above it; but "unusual" is a premise this artifact never
supplied, borrowed from a general convention about how APIs behave. In this
toy world that convention happens to be exactly what `notes.md` documents,
so the borrowed premise is a sibling-file leak wearing a disguise: the file
boundary held and the knowledge boundary did not. Refusal condition 5 below
gives the concrete trigger to catch yourself on.

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

**`01-claims/` does not exist when the first member is dispatched, and
creating it is not your job.** Nothing in `src/rubrica/` mkdirs it -- your
`Write` creates it, parents and all, and a sibling member's `Write` may have
created it already. **Do not reach for `mkdir`.** This project's dispatch
allows `rubrica *` through Bash and nothing else, so the command lands on an
approval prompt that `claude -p` cannot answer.

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
   `goal`, `outcome_class`, or `tool` -- and record at least one `evidence` entry
   whose `locator` is precise enough that a reader, given only the artifact
   and the locator, can find the exact statement again: a JSON Pointer
   (`#/tools/0/input_schema/properties/action`) for a JSON input, a heading
   anchor or a line reference for prose.

   `invariant` and `outcome_class` are the pair most often swapped, and the
   swap is invisible downstream: `rb-reconcile-outcomes` enumerates the
   coverage denominator -- every operation crossed with its outcome classes --
   and although it is instructed to harvest from claims of every `kind`
   precisely because this swap happens, it is reading for a fact the wrong
   label hides. So a genuine error behaviour filed as `invariant` can still
   miss that enumeration, and a column of the test matrix goes missing with no
   schema, no `check-refs`, and no validation error ever naming it. Tell the two apart by what the statement is
   *about*: a statement about what an operation returns or raises for some
   class of input is an `outcome_class`; a statement about a data or state
   rule the store maintains regardless of any call is an `invariant`. Two
   statements from `notes.md`, three paragraphs apart, that must not land
   the same way: "`comment_count` is always the number of comment records
   attached to it" is an `invariant` -- a rule about stored data, true
   whether or not anyone ever calls anything. "`get_ticket` with an id no
   ticket has is an error, not an empty result" is an `outcome_class` --
   what `get_ticket` does for the class of input "unknown id." If you catch
   yourself about to write `invariant` for a sentence describing what an
   operation *does*, that is the sign you have the pair backwards.

   A `tool` claim is the one kind whose `payload` is load-bearing rather than
   optional. File one per tool the target declares -- not one per action a tool
   dispatches on, because the unit is what the agent registers. Copy the tool's
   input schema into `payload` **verbatim**: do not summarise it, reformat it,
   fill in a type you think was implied, or drop a field you judge unused. A
   later stage builds the request body of a synthesised interface out of exactly
   these bytes, and an agent's tool contract survives that substitution only if
   they are unchanged. Set `evidence[0].locator` to the JSON pointer the schema
   was copied from -- `#/tools/0/input_schema` for the first tool of a tool-schema
   document -- because a deterministic check re-reads the input at that pointer
   and compares it to what you wrote. A `payload` that disagrees with its pointer
   is a finding against this stage, so the pointer is not decoration.

   **A state observation needs its instant.** A trace records what the target
   did at one moment, and for a target that stores anything, the same call can
   correctly return different results at different moments. So when this input
   is a trace and you are writing a claim about *observed state* -- what a
   query returned, what the store held at the time -- state the capture instant
   in the `statement`, and cite it as a second `evidence` entry: the locator of
   the field it came from (`/info/request_time` in an MLflow trace) with the
   value in `quote`. Where the capture states the instant in prose rather than
   in a field -- a chat trajectory whose opening message says "The current time
   is ...", with no timestamped field anywhere in the file -- cite the locator
   of that message with the sentence in `quote`. The rule is the same and only
   the locator moves. It rides as evidence because that is what it is, a fact
   read off this artifact rather than anything you concluded. Do not attach it
   to a claim about a declared contract, a capability or an argument schema,
   where the moment of capture means nothing.

   You are the only stage that reads this artifact. Every reconcile pass sees
   claims and never a trace, so an instant you leave out is one no later stage can
   recover. Measured on a real run: two traces listing the same user's
   reservations, either side of a cancellation, produced two claims that read
   as a flat contradiction, and reconcile could only record it unresolved
   "because no input carries a timestamp or sequence relating them" -- while
   both input files carried `info.request_time` all along.

4. **Set `derivation` honestly, one of three values.** `stated` -- the
   artifact says this in so many words. `inferred` -- you concluded it from
   what the artifact says, without the artifact stating it outright, and
   your reasoning never left this one artifact. `reverse_engineered` -- you
   read it off an observed behaviour, such as one span of a trace, rather
   than off any description of intended behaviour. These three words are
   not interchangeable and not a formality: "the spec states this" and "I
   guessed from one trace" must never collapse into a claim that looks the
   same downstream. This is what makes resolution at
   `rb-reconcile-contradict` and gap reporting at `rb-reconcile-gaps` honest --
   neither can weigh a claim by where it actually came from unless you recorded
   that truthfully. If you are unsure which of the three
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

**Cover the whole artifact.** For a prose artifact, every `##` heading must be
cited by at least one claim's `evidence.locator`, or your report must say why
that section carries nothing about the target. Headings are a small, closed set
the artifact itself writes down, which is what makes this checkable where "every
statement" is not: a real dispatch that had been told "every statement it makes
about the target" filed a claim for a licence line and skipped a whole section of
usage examples -- the five requests a user actually makes of this target.

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

Before you report done, run `rubrica validate --stage extract --run <run>`,
where `<run>` is the run directory you were dispatched with. `--run` is
required: without it the command exits 2 on a usage error and tells you
nothing about your artifact. If it reports anything wrong with the file you
just wrote, that is not a finding to pass along -- it is your own defect to
fix. Repair the artifact and validate again; report success only once
`rubrica validate --stage extract --run <run>` exits clean.

## 5. Refusal conditions

Every condition below is one where the correct output is not a claim -- it
is a statement that you could not honestly produce one, or that you produced
one carrying an explicit caveat. Writing that statement is success, not
failure: a refusal recorded here becomes a gap `rb-reconcile-gaps` can
reason about and a hole `rb-score` can count against the denominator. An invented
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
  Record it under the closest of the seven anyway, with `confidence: low`,
  and say in the `statement` itself that the fit is approximate. Do not
  invent an eighth kind: the enum is closed, and a claim with an unlisted
  kind fails validation rather than being read by anyone.

- **The artifact contradicts itself.** Record both sides as separate
  claims, each with `confidence: low`. Do not pick the side that sounds
  more authoritative, average them into one hedged claim, or otherwise
  reconcile them -- that reconciliation is `rb-reconcile-contradict`'s job, a
  few stages downstream. Doing it here is how a contradiction stops being a recorded
  fact and becomes something silently smoothed over before anyone else gets
  to see it.

- **You are tempted to record a capability's error semantics that the
  artifact itself does not state.** Resist it. If the artifact says a tool
  returns a list of tickets but never says what happens when the queue
  name is wrong, do not write a claim about what probably happens on a bad
  queue name -- record only what is actually there. A missing error class
  is a gap for `rb-reconcile-gaps` to surface and a hole for `rb-score` to
  count; recording your own guess in its place erases the gap and hands
  every downstream stage a fact that nobody ever actually stated.

- **You are about to describe an observed behaviour as unusual, unexpected,
  atypical, or as probably a bug.** Stop. Words like those are you comparing
  what the artifact shows against a convention or expectation the artifact
  itself never stated -- and that comparison is knowledge from outside it,
  every bit as much a contamination risk as reading a sibling file, even
  though no sibling file was touched. Record the observation alone, at
  whatever `derivation` and `confidence` it honestly earns, and drop the
  characterization. Concretely: if `trace.json` shows `get_ticket` called
  with `ticket_id: 9999` returning `{}`, the honest claim is
  `reverse_engineered`, `confidence: medium`, with a statement close to
  "`get_ticket` returned an empty object for `ticket_id=9999`, an id no
  other span establishes as valid" -- full stop. Appending "which is
  unusual, since APIs typically error on an unrecognized id" is the same
  observation with an unstated premise bolted on. Whether that premise is
  true is `rb-reconcile-contradict`'s question, to be answered by comparing your
  claim against whatever a sibling claims file independently says; it is not
  yours to pre-answer by assuming the convention holds here.
