---
name: rb-triage
description: Rule on every candidate in a run's catalogue against the declared objective -- admit, or decline with a reason -- and state what the admitted set cannot cover.
---

# rb-triage

You decide what this run will be able to know.

Every candidate you decline is a fact about the target that no later stage can
recover, because nothing downstream reads the corpus -- `rb-extract` reads only
what `intake` admitted, and `intake` admits only what you marked `admit`. There
is no stage after you that can notice you were wrong. That is why your output
records a reason for every single candidate rather than a list of the ones you
kept: a human holds a gate on this record, and they can only overturn a decision
they can see.

The failure this stage exists to prevent has been measured. On 2026-08-13 a run
selected sixteen inputs by hand and excluded, among other things, the files that
declared what each of the target's thirteen tools returns. Six scenarios later
died because no artifact carried those shapes, and the world model recorded the
absence as four gaps that looked identical to gaps nothing could ever close. The
information that would have distinguished them -- *this was declined, and here is
why* -- existed only in a conversation that no longer exists.

## Contract

```toml
stage = "triage"
reads = ["catalogue"]
writes = ["triage"]
schemas = ["triage"]
invokes = ["validate"]
```

## 1. Inputs

You read exactly one file: `00-catalogue.json`.

Not the corpus. The catalogue's candidates name paths on disk, and some of those
paths exist and are readable right now. **Opening one is out of contract.** The
prohibition is on opening the file, not on what you would have taken from it,
for two reasons that are worth stating because the temptation is real and
constant.

The first is cost. The catalogue exists so that your judgment costs one bounded
digest per candidate instead of the whole corpus. A corpus can be gigabytes; a
catalogue is a few hundred kilobytes. Opening candidates one by one to "check"
them is how a stage that was designed to be affordable becomes the most
expensive one in the pipeline.

The second matters more. The digests are the same width for every candidate, so
your reasons are comparable — "declined, no tool schema in the digest" means the
same thing said about candidate 3 and candidate 300. Once you have read some
candidates in full and others only as digests, your record no longer says what
it appears to say, and nobody reading it can tell which decisions were made on
which basis.

What you get for each candidate: its `candidate_id`, `kind`, `bytes`, `sha256`,
`origin`, its `path` or the `container` it was exploded out of, and its `digest`.
What the digest contains depends on the kind, and it is described in §2 of
`policy` and in the digest itself. **The field that matters most is
`heuristics_fired`**, on trace digests: it lists which extractors found
something. A heuristic missing from that list found nothing, which is a fact
about the digest and not about the candidate.

Non-trace digests carry no such list; instead they carry a `skeleton`, and it
can mislead the same way if you read it as complete. `digest.py` caps how many
of an object's keys it shows -- thirty-two -- and records the true count and a
`keys_truncated` flag beside the capped list. A `keys_truncated: true` skeleton
is a fact about the digest -- that the object was wide enough to be capped --
not a fact about the candidate having only thirty-two keys. Ruling a wide
object `no_evidence_value` because its visible keys look thin, when
`keys_truncated` says there were more, is the skeleton's version of the mistake
`heuristics_fired` exists to prevent on traces.

Two of `heuristics_fired`'s five names are not always independent evidence,
either. Measured on a real 130-element trace capture, after the noisy
substring scan was narrowed out of `error_markers`: it fired on exactly one
element, and that firing resolved through the same value already reported under
`status` -- the independent error-key path fired zero times on that corpus. On
a corpus shaped like that one, `status` and `error_markers` both firing on a
candidate is one fact about it stated twice, not two facts. Treat a repeated
signal as one piece of evidence when you weigh how well-attested a candidate's
behaviour is; counting it twice inflates a single failure into two.

`request` carries what you are being asked for: the target's name and
interface, the `objective` (`breadth` or `depth`), and optionally an
`objective_note` and a `scope_note`. `policy` carries the rules that shaped the
set — which exclusion reasons were in force, the explosion thresholds, the
digest caps. `excluded` lists what `survey` dropped mechanically and why; read
it, because a mechanical exclusion you believe was wrong is a `deficiencies[]`
entry, not something to stay quiet about.

You are dispatched with no memory of any conversation before you, and nothing
you write carries forward as memory. What you need is in this document or in
that one file.

## 2. Output

One file: `00-triage.json`, validating against `triage-0.1.json`. It carries
`schema_version: "0.1"`, the `run_id` of the run you are working in (read it
from `00-catalogue.json`'s `run_id` — never invent it, and never derive it from
the directory name), and four blocks: `objective_review`, `dispositions`,
`deficiencies`, and `projections`.

**All four blocks are required at the document root, and an empty one is still
written.** `triage-0.1.json` requires every one of them, so a record with
nothing to report in the last two carries `"deficiencies": []` and
`"projections": []` — omitting a block because it would be empty fails layer 1
and costs the run a repair round for a record whose *judgment* was fine. An
empty `deficiencies` is also a claim, not an absence: it says the admitted set
covers everything the objective needs, which is a statement a human at gate 0
will read as one.

**`objective_review`** — the surfaces you found, and whether the objective you
were given is supported by them.

A *surface* is a coherent region of the target's behaviour that a suite could
be built about: a persona, an API area, a workflow, a subsystem. You are not
guessing at the target's internal structure; you are grouping the evidence in
front of you by what it is evidence *about*. For each one: a `name`, the
`evidence` candidate ids, and a `weight` of `{candidates, bytes}` — both
arithmetic over the catalogue, so a reader can check them.

`declared_objective` echoes `request.objective`. `supported` is your judgment on
whether the evidence can carry it: `depth` on a surface with one candidate is
not supported, and neither is `breadth` when eleven of twelve surfaces have no
behavioural evidence at all. If you would have chosen differently, say so in
`recommended_objective` with a reason. **You may not act on that
recommendation.** Select against the objective you were given, and let the human
at the gate decide whether to change it — a re-scope you perform yourself is
invisible, and it produces a selection that looks coherent and answers a
question nobody asked.

Enumerating the surfaces is not a courtesy. It is the part of this record that
lets a human see that the objective they declared excludes something they wanted.

**`dispositions[]`** — **one entry for every candidate in the catalogue, exactly
once, including the ones you decline and the ones marked
`admissible: false`.** A container is inadmissible because its elements are the
real candidates; decline it, and say that is why.

Every disposition also carries `authority: "triage"`. You are the only writer of
this record, so every disposition you write carries that value; `"human"` is
what a gate-0 override carries — written by a person, or by `rubrica
adopt-projection` when a manufactured projection is admitted. Both of those edit
**this same record**, appending to the file you produced rather than starting a
new run's. State the value rather than leaving it implicit — a reader of the
finished record needs to tell which admissions this stage authored from which a
human made at the gate, and `authority` is the only field that says so.

An `admit` carries `reason` (prose) and a `priority` — an integer rank, 1 for
the most valuable, expressing where you would spend the extraction budget first.
No code acts on `priority`; it orders the human's reading.

A `decline` carries `reason` (prose) and a `reason_code` from this list:

| Code | Use it when |
|---|---|
| `off_objective` | Real evidence about the target, but not about what this run is for |
| `out_of_scope` | Belongs to a surface `scope_note` excludes |
| `near_duplicate` | An admitted candidate carries the same shape; name it in `reason` |
| `superseded` | Something more authoritative says the same thing; name it |
| `implementation_detail` | Describes how, where the objective needs what |
| `no_evidence_value` | Carries no statement about the target at all |
| `digest_insufficient` | You cannot rule on it from its digest |
| `needs_projection` | Valuable, not usable as-is; write the projection |

`digest_insufficient` and `needs_projection` each oblige you to write something
else — a `deficiencies[]` entry for the first, a `projections[]` entry for the
second — and `check-refs` will reject the record if you don't. Those two codes
exist to make a loss visible, so a decline nothing else points at is worse than
no code at all.

**`deficiencies[]`** — what the admitted set cannot cover that the objective
needs. Each has a `deficiency_id`, a `subject` naming the thing that is missing,
and a `statement` saying what will not be answerable without it.

This is the block that would have prevented the failure in the header. Ask it
directly, every time: *for each capability the admitted set implies, does
anything in the admitted set declare what it returns?* If not, that is a
deficiency, and writing it costs one paragraph now instead of six dead scenarios
later.

**`projections[]`** — a brief for something that has to be manufactured. See §3
step 6.

## 3. Method

**Step 1 — read `request` first, before any candidate.** The objective decides
every subsequent call, and a reading that starts from the candidates arrives at
a scope and then rationalises the objective to fit it.

**Step 2 — group every candidate into a surface.** Work from `path`, `kind`, and
the digest's own contents: a prose document's headings, a trace's `request_text`
and `names`, a source file's `assignments` and `defs`. Every candidate belongs
to exactly one surface for the purpose of this pass, including ones you will
decline — a surface with nothing but declines is exactly what a human needs to
see.

**Step 3 — weigh each surface and rule on the objective.** Count candidates and
bytes per surface. Then answer: can the declared objective be met from this?
Write `supported`, and `recommended_objective` if you disagree.

**Step 4 — rule on every candidate.** Prefer behavioural evidence over prose
about behaviour: a trace records what the target *did*, prose records what
someone intended. Both are legitimate, and when they conflict that conflict is
itself worth admitting rather than resolving — `rb-reconcile-contradict`
records contradictions and is better placed to.

For near-duplicates, admit the one with the most distinct shape rather than the
largest or the newest. On the 2026-08-13 corpus, seven traces of 130 were kept
for distinct shape — one aggregation, two triages, two multi-hop debugs, one
identity lookup, and one failure — and that last one was the run's only evidence
of what the target does when something goes wrong. **A failing trace is almost
never a near-duplicate of a successful one**, however similar its request looks.

**Step 5 — check for absence, not just presence.** Walk the capabilities the
admitted set implies and ask what each one's result shape is declared in. Walk
the surfaces and ask which have no behavioural evidence. Each answer that comes
back empty is a `deficiencies[]` entry.

**Step 6 — write a projection for anything valuable that is not usable as-is.**

A projection is a work order someone else executes — a human tonight, possibly a
subagent later — so it has to be complete without you. It carries all seven
fields the schema requires: a `projection_id`; `closes` (the deficiency ids it
remedies); `sources` (each a `candidate_id` and a `digest_note` saying what
that candidate's digest told you, plus an optional `path`); `wanted` (the `kind`, a `statement` of the artifact, and `why` it matters);
`method` (`steps`, and a `confidence` of `high`, `medium` or `unknown` —
**`unknown` is an honest value**; you usually cannot know an extraction method
from a digest, and a confident-sounding wrong method is worse than an admitted
gap); `acceptance`; and a `boundary` saying what must not be included.

`acceptance` is how the worker knows they are done: `classifies_as`,
`pointers_required`, `must_contain` (the exact strings that must appear),
`must_not_contain` (the scope boundary, as strings), and `prose`. The four
structural fields are checked mechanically by `rubrica adopt-projection`. They
are necessary and never sufficient — `prose` is where you say what *correct*
means, and a brief without it has not specified anything.

**Step 7 — run your gate.** `rubrica validate --stage triage --run <RUN>`. Fix
what it reports and run it again. Then `rubrica check-refs --run <RUN>`, which
will tell you if any candidate went unruled or any code went unreferenced.

## 4. Invariants

1. **Exactly one disposition per catalogue candidate.** Not fewer: an unruled
   candidate is indistinguishable from one nobody saw. Not more.
2. **Nothing in `dispositions[]` that is not in `candidates[]`.** A candidate you
   wish existed is a `deficiencies[]` entry.
3. **At least one admit.** An empty admitted set is a scoping failure; see §5.
4. **Never admit a candidate whose `admissible` is `false`.**
5. **Every `digest_insufficient` decline is referenced by a deficiency, and every
   `needs_projection` decline by a projection.**
6. **`weight` is arithmetic over the catalogue**, not an impression. A reader
   recomputes it.
7. **You read `00-catalogue.json` and nothing else.** No candidate file, no
   `decisions.md`, no artifact from another run.
8. **`recommended_objective` is a recommendation.** Your selection is against
   `request.objective` as written.

## 5. Refusal conditions

Each of these means: write no `00-triage.json`, and report what you found and
why you stopped. A partial record is worse than none, because it passes layer 1
and the gate reads it as complete.

**Refuse if `request.objective` is absent, or contradicts `scope_note`.** A
triage held to no objective cannot be held to anything, and this stage exists
because that judgment was previously unwritten. If the objective says `breadth`
and `scope_note` confines the run to one surface, those are two different runs;
say so and stop.

**Refuse if you would decline every candidate.** Zero admits is not a result you
can report by writing it down — it means the corpus, the objective, or the scope
is wrong, and all three are outside your authority to change. Report which one
you believe it is.

**Refuse if the catalogue has no candidates at all**, or if it is not readable as
the schema describes. That is a `survey` defect or a broken run, and producing a
record against it would attribute a scoping decision to a stage that never ran.

**Do not refuse when the declared objective is unsupported.** Write the record,
set `objective_review.supported` to `false`, state why, and let the gate rule.
Refusing here would leave the human with nothing to rule *on*, which is the
opposite of the help they need.

**Do not refuse for a candidate you cannot judge.** Decline it
`digest_insufficient`, name the field you needed in `reason`, and write the
matching deficiency. One unreadable digest is not a reason to abandon three
hundred good decisions.
