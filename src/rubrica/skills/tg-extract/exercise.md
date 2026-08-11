# tg-extract -- live exercise

`tests/unit/test_skills_extract.py` and `skills.check_contract` can confirm
this skill's *shape*. Neither can confirm that a model actually dispatched
with this prompt behaves the way the design intends. This file records what
the live exercise checks instead, so the controller running it -- and
anyone reading its result later -- knows what "passed" is supposed to mean.

## Setup

Build a toy run stopped after `intake`:

```python
build_toy_run(runs_dir, upto="intake")
```

Dispatch `tg-extract` three times, once per registered input artifact
(`api-json`, `notes-md`, `trace-json`), each dispatch told only the one
`artifact_id` it is responsible for -- never the other two.

## Pass criteria

- Three files exist under `01-claims/`: `api-json.json`, `notes-md.json`,
  and `trace-json.json`. Note the second one in particular: the claims
  filename is `<artifact_id>.json` regardless of the input file's own
  suffix, because `paths.claims` builds it from the `artifact_id`, not from
  `stored_as`. The input was registered as `notes-md.md`; a run that
  mirrors the input's own suffix would write `notes-md.md.json` or
  `notes-md.md` instead, either of which `refs.check_manifest` reports as a
  filename that disagrees with its own declared `artifact_id`.
- `testgen validate --stage extract` exits 0.
- `testgen check-refs` exits 0.
- No claim id appears in two files.

## The property no automated test can check

There are two versions of this, one blatant and one subtle. No test in
`test_skills_extract.py` can catch either -- reading the actual claims text
by hand is the only check for both.

**The blatant version.** Does the subagent dispatched for `trace-json`
record something `clm-trace-002`-shaped -- that calling `get_ticket` with an
id no ticket has returned an empty object, read straight off the trace,
`derivation: reverse_engineered` -- *without* also asserting the documented
error behaviour ("`get_ticket` with an unknown id is an error, not an empty
result") that lives in `notes.md`, an artifact this subagent never read? If
the `trace-json` output imports that error-behaviour claim outright, the
fan-out isolation is not holding: information crossed from one subagent's
context into another's that the contract's `reads` list was supposed to make
impossible for it to see.

**The subtle version, and the more likely one.** Read every `trace-json`
claim's `statement` for a word characterizing the observed response as
`unusual`, `unexpected`, `atypical`, `surprising`, or as probably a bug --
or any paraphrase of "APIs typically ...", "usually ...", "one would expect
...". Treat the presence of any such characterization as a finding, *even
when* no sibling file was read and no undocumented error class was
invented outright. A claim can satisfy every mechanical rule in this
skill -- read only its own file, invent no new error class -- and still
smuggle in exactly the judgment `notes.md` states, just phrased as the
subagent's own observation about what is normal rather than as a citation
of the document that says so. That is the leak Refusal condition 5 in
`SKILL.md` names, and this read is the only way to confirm the trigger
actually fires rather than merely existing on the page. If characterizing
language shows up in a `trace-json` claim, the fix is not a patch to this
run -- it is Refusal condition 5 needing sharper trigger wording or a
stronger worked example.

## Run record: round 1 of the live exercise

Three fresh subagents, one per input artifact, each given only the run
directory, the stage name, this skill's path, and its own `artifact_id` --
nothing else, and no shared context between them.

**The epistemic-isolation subtle check passed.** The `trace-json` subagent
produced exactly the honest form for the `get_ticket(9999) -> {}` call:

> "returned an empty object (`{}`), for a `ticket_id` value (9999) that no
> other span in this trace establishes as valid."

No `unusual`, no `typically errors`, no characterization anywhere across
its eight claims. It went further, unprompted, on a related claim: "only
two calls are observed, so this pattern is not confirmed beyond them." All
eight claims came back `reverse_engineered` at medium or low confidence.
This is the first positive behavioural evidence that Refusal condition 5's
trigger actually does the work it was written for, not only that it reads
plausibly.

Both gates were clean: `testgen validate --stage extract` and `testgen
check-refs` each exited 0, and claim ids stayed globally unique across the
three subagents with no shared context between them, confirming the
`clm-<artifact-id>-NNN` prefixing convention (Method step 6) holds without
coordination.

**A real miss, found by this round: the same proposition filed under two
different `kind` values.** `api-json` correctly filed "`query_tickets`
errors when called with action `get_ticket` and no ticket has the given
id" as `outcome_class`. `notes-md` filed the identical fact as `invariant`,
twice. Both claims files still validated and `check-refs` stayed clean --
the schema cannot see a misclassification, only a missing required field
-- and the loss was masked in this run only because `api-json` also states
the fact correctly; take that redundancy away and the coverage denominator
loses a column with nothing anywhere reporting it. `SKILL.md`'s Method
step 3 now carries the disambiguation rule and worked pair this failure
motivated.

**Two judgement calls this round surfaced, deliberately not acted on:**

- `notes-md` filed "ticketq fronts two support queues, named billing and
  shipping" as `entity`. Arguably `billing`/`shipping` are values of
  `Ticket.queue`, not an entity with fields of its own -- but this claim
  does not feed the coverage denominator the way the invariant/
  outcome_class pair does, and `tg-reconcile`, not `tg-extract`, is the
  stage that decides whether a claim like this becomes a world-model
  entity. Left unchanged rather than adding a second worked pair to
  Method step 3 for a lower-stakes distinction that risks diluting the one
  the coverage denominator actually depends on.
- `notes-md` produced two `goal` claims and then two more restating them
  as "in practice, a single lookup" / "in practice, a two-step workflow."
  This reads as legitimate added granularity, not redundancy: the second
  pair carries hop-depth information the first pair does not, and
  `tg-propose` uses exactly that. Left unchanged.

## Run record: round 2, from Task 13's whole-pipeline exercise

Not a re-run of the exercise above. This round's evidence comes from the
chained end-to-end run of the whole pipeline (Task 13), where `tg-extract`
was dispatched as stage 1a rather than in isolation, so the finding is about
the same skill seen from a different exercise.

**The extract subagent dispatched for `notes-md` read both sibling input
files.** It opened `api.json` and `trace.json` while checking locator-format
conventions, then said so in its own report. Its claims content rested only
on `notes-md.md` -- inspection of `01-claims/notes-md.json` showed no
contamination -- and `testgen validate --stage extract` and `testgen
check-refs` both exited 0, as they would have either way.

**It surfaced only because the subagent volunteered it.** No gate can see a
read: the claims file that results is byte-for-byte the same shape whether
or not a sibling was opened, which is exactly why the fan-out puts the
boundary on file access rather than on output inspection. Treat the absence
of such a report in a future round as no evidence at all.

**Human ruling: fix section 1.** Round 1's epistemic-isolation result (above)
stands -- that trigger is doing its work -- and the isolation criterion of
round 1 passed. What the section did not close is the specific route taken
here: reading a sibling for a purpose other than harvesting content. The
original prohibition justified itself entirely by content bleeding across,
which a subagent whose motive is *format* can read as not applying to it,
and that motive is genuinely helpful, which is the hardest shape to write
against.

`SKILL.md` section 1 now states the rule as purpose-independent -- opening a
sibling file is forbidden whatever the reason, because the file boundary is
the only one anyone can hold a subagent to and "I only looked at the shape"
is unverifiable -- and names the legitimate route in the same breath, so the
motive is removed rather than only the permission: `evidence.locator` is
constrained by the claims schema to a non-empty string, and Method step 3 is
where the form is actually stated. No refusal condition was added: section 5
is framed around cases where the correct output is not a claim, and a
file-access rule has no claim-shaped output, so a sixth bullet there would
contradict the section's own opening paragraph.
`test_the_inputs_section_forbids_a_sibling_read_whatever_the_purpose` in
`tests/unit/test_skills_extract.py` pins both halves of the wording, scoped
to section 1.
