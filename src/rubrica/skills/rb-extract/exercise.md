# rb-extract -- live exercise

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

Dispatch `rb-extract` three times, once per registered input artifact
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
- `rubrica validate --stage extract` exits 0.
- `rubrica check-refs` exits 0.
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

Both gates were clean: `rubrica validate --stage extract` and `rubrica
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
  outcome_class pair does, and `rb-reconcile`, not `rb-extract`, is the
  stage that decides whether a claim like this becomes a world-model
  entity. Left unchanged rather than adding a second worked pair to
  Method step 3 for a lower-stakes distinction that risks diluting the one
  the coverage denominator actually depends on.
- `notes-md` produced two `goal` claims and then two more restating them
  as "in practice, a single lookup" / "in practice, a two-step workflow."
  This reads as legitimate added granularity, not redundancy: the second
  pair carries hop-depth information the first pair does not, and
  `rb-propose` uses exactly that. Left unchanged.

## Run record: round 2, from Task 13's whole-pipeline exercise

Not a re-run of the exercise above. This round's evidence comes from the
chained end-to-end run of the whole pipeline (Task 13), where `rb-extract`
was dispatched as stage 1a rather than in isolation, so the finding is about
the same skill seen from a different exercise.

**The extract subagent dispatched for `notes-md` read both sibling input
files.** It opened `api.json` and `trace.json` while checking locator-format
conventions, then said so in its own report. Its claims content rested only
on `notes-md.md` -- inspection of `01-claims/notes-md.json` showed no
contamination -- and `rubrica validate --stage extract` and `rubrica
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

## Run record: round 3, re-record after the section-coverage change

Task 2 of the claim-utilisation-and-observable-judgment plan added Method's
"Cover the whole artifact" paragraph: for a prose artifact, every `##` heading
must be cited by at least one claim's `evidence.locator`, or the report must
say why not. This round re-records the exercise against the changed prompt,
per this repository's obligation to re-record after a skill changes.

Dispatched via `scripts/dispatch-stage.sh`, isolated instance
(`--safe-mode`, its own `CLAUDE_CONFIG_DIR`, `permissions.deny` over `docs/`,
`tests/`, `CLAUDE.md`, `README.md` and every sibling skill), model `sonnet`,
effort `medium` (both the script's defaults -- neither `RUBRICA_MODEL` nor
`RUBRICA_EFFORT` was set). One dispatch, `artifact_id: api-json`, against a
toy run stopped after `intake`. 8 turns, `total_cost_usd` `0.39678075` from
the transcript's `result` event.

**Both gates clean:** `rubrica validate --stage extract` and `rubrica
check-refs` each exited 0 against the written `01-claims/api-json.json` (13
claims: 6 `capability`, 4 `entity`, 3 `outcome_class`).

**Read audit (`scripts/audit-reads.sh`), against the contract's `reads =
["manifest", "input_file"]`:** `Read` calls were `SKILL.md`, its own
`00-inputs/api-json.json`, and `manifest.json`; the only `Write` was its own
`01-claims/api-json.json`. The two `Bash` lines were both `rubrica validate`
invocations plus one `find` for the claims schema path -- no sibling input,
no `docs/`, no `tests/`, no other skill. Nothing out-of-contract.

**Scope note, stated plainly rather than overclaimed:** `api-json` is a
`mcp_tool_schema` artifact, not prose, so this dispatch does not exercise the
new "Cover the whole artifact" heading rule at all -- that rule is scoped to
prose artifacts and the toy fixture's only prose input is `notes-md`. This
round shows the changed prompt still produces a clean, schema-valid,
gate-passing `api-json` claims file; it is not evidence one way or the other
about whether the heading-coverage instruction changes behaviour on a prose
input. Re-running against `notes-md` specifically would be needed to observe
that, and was not done here because the plan's Step 2 script names `api-json`
as the slice to dispatch.

## Run record: round 4, re-record after the capture-instant change

Method step 3 gained "A state observation needs its instant": when the input is
a trace, a claim about observed state must state the capture instant and cite it
as a second `evidence` entry, and must not attach it to a claim about a declared
contract, a capability or an argument schema. This round re-records against the
changed prompt, per the obligation to re-record after a skill changes.

Unlike rounds 1-3 this was not a toy run. The fan-out ran against a real corpus
(`run-20260816-172810`, the reservation-service target: two MLflow trace
captures, a tool schema, a README and two source files), so it is 31 dispatches
rather than one. That is a larger sample than this file's format assumes, and
the aggregate is reported as an aggregate rather than dressed up as a single
observation.

Dispatched via `scripts/dispatch-stage.sh`, one isolated instance per member,
each with its own `RUBRICA_LAB` so no two shared a `CLAUDE_CONFIG_DIR`. Model
`sonnet`, effort `medium`, five concurrent. **31 of 31 exited 0 with
`subtype: success`**, 251 turns and $21.69 in total, mean $0.70 per member.
`rubrica validate --stage extract` exited 0 over all 31 claims files.

**The rule fired where it applies and nowhere else.** 25 claims files cite
`/info/request_time` as evidence. The four non-trace inputs -- `tools-list-json`,
`readme-md`, `agent-py`, `test-agent-py` -- cite it zero times between them, so
the scoping clause held rather than every claim in the run acquiring a
timestamp. The two trace inputs that do not cite it are `trajectories2-json-13`
and `trajectories2-json-14`, the two captures in which the agent called no tool
at all: it rejected an unparseable datetime and an out-of-range `price_tier` in
its own turn. Those traces observe no state, so the rule correctly does not
reach them. Of the 25 trace inputs that do observe state, 25 carried the
instant.

**What the change was for, observed end to end.** The three claims that had been
unorderable now carry their moments:

| claim | `evidence[].quote` | statement |
|---|---|---|
| `clm-trajectories2-json-3-016` | `2026-08-16T15:05:04.297Z` | `list_reservations` for jane@example.com returned exactly one reservation |
| `clm-trajectories2-json-4-013` | `2026-08-16T15:05:20.180Z` | that reservation id was cancelled |
| `clm-trajectories2-json-10-017` | `2026-08-16T15:07:24.653Z` | the same call returned an empty list |

Before the change, the first and third of these were two claims that read as a
flat contradiction, and `rb-reconcile` recorded them `both_possible` on the
stated grounds that "no input carries a timestamp or sequence relating them" --
while all three input files carried `info.request_time` the whole time, inside
the one artifact each member is allowed to read.

Compliance was to the letter but not uniform in form: 25 files put the instant in
`evidence`, and 7 also wrote it into the `statement` as the paragraph asks.
Phrasings varied ("as observed at the request instant", "as captured at
request_time"). The instant is machine-readable in `evidence[].quote` either
way, so this is not a defect, but a later round wanting the statement form
consistently would need the paragraph to say so more plainly than it does.

**Read audit, all 31 transcripts, against `reads = ["manifest", "input_file"]`:**
every member touched its own `00-inputs/<id>` and its own `01-claims/<id>.json`
and no other member's slice. Zero foreign reads across 31 concurrent processes.
This is the strongest isolation evidence recorded here: rounds 1-3 covered three
members or one, and round 2 recorded an actual sibling read, so a clean 31 is a
result rather than a formality.

**A finding this round produced that has nothing to do with the change, and
matters more than it.** Claim totals across the same 31 inputs moved 639 -> 546
between the round-3-era prompt and this one, and the drop is concentrated in two
inputs the new rule explicitly excludes: `tools-list-json` 54 -> 22 and
`readme-md` 42 -> 30. `tools-list-json` is a static JSON schema file. Same
prompt for it, same model, same effort, same input bytes, and one run extracted
54 claims where the next extracted 22 -- both `success`, both around $0.46, both
far short of the $2 ceiling, so not truncation. The variance is run-to-run
nondeterminism on the single input triage ranked priority 1, "the only candidate
that declares what a tool returns".

Two consequences worth stating rather than leaving implicit. First, this round
cannot cleanly attribute anything else to the prompt change: the noise floor
between two extract runs is larger than most effects anyone would want to
measure, so the timestamp result above is trusted because it is a
presence/absence check with a scoping control, not because 546 differs from 639.
Second, the sample size in this file has been one dispatch per round until now.
`docs/design/limitations.md` carries the entry this observation motivated.

## Run record: round 5, re-record after the prose-instant clause

Method step 3's capture-instant paragraph gained a clause: where the capture
states the instant in prose rather than in a field, and there is no timestamped
field anywhere in the file -- a chat trajectory whose opening message says "The
current time is ..." -- cite the locator of that message with the sentence in
`quote`. The no-field qualifier is part of the clause: it is a fallback for a
capture with nothing else to cite, not a general alternative to citing a field.
This round re-records against the changed prompt, per the obligation to
re-record after a skill changes.

**Read this round beside rounds 3 and 4, not against them.** Those two ran on
`sonnet`; this one ran on `opus`, set explicitly through `RUBRICA_MODEL` rather
than taking the script's `sonnet` default, because this gateway's allowlist is
reported to refuse `claude-sonnet-5` and `claude-haiku-4-5` with `403 team not
allowed to access model`. That refusal was not re-measured here -- what was
measured is that opus authenticated and completed. A model change is part of what
happened, so no number in this section is comparable to a number in those, and
round 4 already found the run-to-run noise floor on this stage larger than most
effects worth measuring with the model held constant.

Dispatched via `scripts/dispatch-stage.sh extract <run> trace-json` with
`RUBRICA_MODEL=opus` and `RUBRICA_EFFORT=medium`, isolated instance as in round
3 (`--safe-mode`, its own `CLAUDE_CONFIG_DIR`, `permissions.deny` over `docs/`,
`tests/`, `CLAUDE.md`, `README.md` and every sibling skill). One dispatch,
`artifact_id: trace-json`, against a toy run stopped after `intake`. The
transcript's `result` event reports `subtype: success`, `canonicalModel:
claude-opus-5`, 10 turns, 104,950 ms, `total_cost_usd` `0.5768599999999999` --
well short of the script's default `$2` ceiling, so nothing here is truncation.

`trace-json` was the slice chosen rather than round 3's `api-json` because it is
the toy fixture's only input of kind `trace`, and the capture-instant rule is
scoped to a trace. Dispatching any other slice could not have put the rule in
scope at all.

**Both gates clean:** `rubrica validate --stage extract` and `rubrica check-refs`
each exited 0 against the written `01-claims/trace-json.json` (10 claims: 3
`capability`, 3 `entity`, 2 `outcome_class`, 1 `actor`, 1 `goal`).

### The capture instant: not cited, and the new clause is still unexercised

**No claim in this file cites a capture instant, from a field or from prose.**
Every claim carries exactly one `evidence` entry except `clm-trace-json-001` and
`clm-trace-json-010`, whose two entries are both span locators; no entry anywhere
in the file holds an instant. The two observed-state claims are
`clm-trace-json-007` and `-008`, and their sole evidence locators are
`#/spans/0/output` and `#/spans/1/output`.

That is the correct output for this input, and it is why the clause remains
unexercised rather than validated. The toy `trace-json.json` is 318 bytes,
`{"spans": [...], "trace_id": "toy-0001"}`: no `info` object, no `request_time`,
zero keys matching `time|date|stamp|_at|seq`, and no message list, so no prose
sentence either. The capture states its instant in **neither** form. A clause
scoped to "where the capture states the instant in prose" cannot fire against a
capture that states it nowhere. **Nothing in this repository's fixtures has yet
been observed exercising the prose-instant clause**, and this round does not
change that; the change was motivated by tau2-bench trajectories, and observing
it would take a dispatch against one.

What this round does show, which is a negative control on the rule rather than
evidence for the clause: with the rule in scope and no instant obtainable, the
member neither fabricated one nor silently dropped the requirement. It recorded
the absence in the `statement` of both observed-state claims, verbatim from
`clm-trace-json-007`:

> For the input `action=find_tickets, queue="shipping", status="open"`,
> `query_tickets` returned an empty array. Gap: this artifact records no capture
> instant -- it carries no timestamp, request-time or sequence field anywhere,
> and no prose statement of the current time -- so this observed-state result
> cannot be placed in time relative to any other observation.

Its own report named the same thing under "refusal conditions hit": "*No capture
instant available.* ... I recorded that as an explicit gap in each `statement`
rather than supplying one." Note what that is not: the paragraph tells the member
what to do when an instant exists and says nothing about what to do when none
does, so this is behaviour the prompt did not ask for and did not forbid. One
sample, one model.

### Round 1's epistemic-isolation check, re-measured on the same slice

Round 1 read the `trace-json` claims for characterizing language and found none;
that is the check this slice makes available again, so it was re-run. Zero
matches for `unusual|unexpected|atypical|surprising|typically|usually|one would
expect|bug`, case-insensitive, across the whole file. `clm-trace-json-008`
phrases the `get_ticket(9999) -> {}` call as "returned an empty object rather
than any error value visible in the span", with the id qualified as "an id no
other span in this trace establishes as valid" -- and does not import
`notes.md`'s documented error behaviour, which this member never read. Refusal
condition 5's trigger held on the model this round ran on.

**Read audit (`scripts/audit-reads.sh`), against `reads = ["manifest",
"input_file"]`:** `Read` calls were `SKILL.md`, its own
`00-inputs/trace-json.json`, `manifest.json`, and the packaged claims schema
`src/rubrica/schema/claims-0.1.json`; the only `Write` was its own
`01-claims/trace-json.json`. The `Bash` lines were one `find` for the claims
schema path and two `rubrica validate` invocations. No sibling input, no
`docs/`, no `tests/`, no other skill. That schema is not a run artifact and not
any member's slice, and round 3 recorded the same lookup by `find`; here the
member read the file the `find` located. **Nothing out-of-contract** -- and the
schema read is the part of that ruling worth stating: the contract block declares
`schemas = ["claims"]`, so the contract names that file itself, and `reads` can
only ever hold `paths.RunPaths` attribute names, so a packaged schema path could
not appear there by construction. That rules on this read; it says nothing about
whether isolation is enforceable in general.

**Two harness facts, neither of which touched the artifact.** The member's
sandboxed `rubrica validate` failed with `apply-seccomp: unshare(CLONE_NEWUSER):
Invalid argument` on this WSL2 kernel and it re-ran the command unsandboxed; and
one `Bash` call was refused for being compound (`echo "EXIT=$?"` appended),
after which it ran the bare command. Both are recorded because a future round
seeing either should know it is the lab, not the prompt.
