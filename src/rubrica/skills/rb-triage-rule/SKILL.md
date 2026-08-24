---
name: rb-triage-rule
description: Rule on every candidate in one slice of the catalogue against the declared objective -- admit, or decline with a reason -- one fan-out member per slice.
---

# rb-triage-rule

You decide what this run will be able to know about the candidates in your
slice. You are one member of a fan-out, dispatched once per slice that
`triage-slices` cut, after `rb-triage-objective` has already ruled on whether
the declared objective can be met at all. Your question is the one the
monolithic `rb-triage` this family was split out of used to ask about the
whole corpus at once: *for each candidate in front of you, admit it, or
decline it and say why.*

Every candidate you decline is a fact about the target that no later stage
can recover, because nothing downstream reads the corpus -- `rb-extract`
reads only what `intake` admitted, and `intake` admits only what the sealed
triage record marks `admit`. There is no stage after you that can notice you
were wrong. That is why your part records a reason for every single
candidate in your slice rather than a list of the ones you kept: a human
holds a gate on the sealed record, and they can only overturn a decision they
can see.

The failure this whole family exists to prevent has been measured, and you
are the pass that carries most of the weight of preventing a repeat, because
you are the one doing the declining. On 2026-08-13 a run selected sixteen
inputs by hand and excluded, among other things, the files that declared what
each of the target's thirteen tools returns. Six scenarios later died because
no artifact carried those shapes, and the world model recorded the absence as
four gaps that looked identical to gaps nothing could ever close. The
information that would have distinguished them -- *this was declined, and
here is why* -- existed only in a conversation that no longer exists.

## Contract

```toml
stage = "triage-rule"
reads = ["slice_shard", "objective"]
writes = ["disposition_part"]
schemas = ["dispositions-part"]
invokes = ["validate"]
```

## 1. Inputs

You read exactly two files: your own shard, `00-slices/<slice_id>.json`, and
`00-objective.json`. **Never a sibling's shard, and never another member's
part.** Not `00-slices.json` (the plan every shard was cut from) and not
`00-catalogue.json` directly -- your shard already carries everything the
plan and the catalogue would have told you about the candidates you own:
`request`, `policy`, `provenance`, and each candidate's `candidate_id`,
`kind`, `bytes`, `sha256`, `origin`, its `path` or the `container` it was
exploded out of, and its `digest`.

**Opening a candidate file is out of contract.** The prohibition is on
opening the file, not on what you would have taken from it, for two reasons
that were true of the monolithic `rb-triage` and are still true of your
narrower slice of its job.

The first is cost. The catalogue -- and now your shard -- exists so your
judgment costs one bounded digest per candidate instead of the whole corpus.
A corpus can be gigabytes; your shard is a few tens of kilobytes. Opening
candidates one by one to "check" them is how a stage designed to be
affordable becomes the most expensive one in the pipeline.

The second matters more, and it is now true in fact rather than only by
assumption. The digests are the same width for every candidate, so your
reasons are comparable -- "declined, no tool schema in the digest" means the
same thing said about candidate 3 and candidate 300. That comparability used
to rest on a convention `digest.py` was merely expected to honour; it is now
enforced, because the digest's skeleton is clamped to a fixed total node
count (see `skeleton_nodes_truncated` below), so no digest can quietly grow
wider than another's and erode the comparison. Once you have read some
candidates in full and others only as digests, your record no longer says
what it appears to say, and nobody reading it can tell which decisions were
made on which basis.

**The field that matters most is `heuristics_fired`**, on trace digests: it
lists which extractors found something. A heuristic missing from that list
found nothing, which is a fact about the digest and not about the candidate.

Non-trace digests carry no such list; instead they carry a `skeleton`, and it
can mislead the same way if you read it as complete. `digest.py` caps how
many of an object's keys it shows -- thirty-two -- and records the true count
and a **`keys_truncated`** flag beside the capped list. A `keys_truncated:
true` skeleton is a fact about the digest -- that the object was wide enough
to be capped -- not a fact about the candidate having only thirty-two keys.
Ruling a wide object `no_evidence_value` because its visible keys look thin,
when `keys_truncated` says there were more, is the skeleton's version of the
mistake `heuristics_fired` exists to prevent on traces. **`skeleton_nodes_truncated`**
is the same fact one level up: the skeleton's total node count is itself
clamped, and a `skeleton_nodes_truncated: true` digest has more structure
than what you can see, exactly the way a capped key list does. All three --
`heuristics_fired`, `keys_truncated`, `skeleton_nodes_truncated` -- are facts
about the digest, never facts about the candidate.

Two of `heuristics_fired`'s names are not always independent evidence,
either. Measured on a real 130-element trace capture, after the noisy
substring scan was narrowed out of `error_markers`: it fired on exactly one
element, and that firing resolved through the same value already reported
under `status` -- the independent error-key path fired zero times on that
corpus. On a corpus shaped like that one, `status` and `error_markers` both
firing on a candidate is one fact about it stated twice, not two facts. Treat
a repeated signal as one piece of evidence when you weigh how well-attested a
candidate's behaviour is; counting it twice inflates a single failure into
two.

Your shard's `provenance` says, for every group your slice draws from, how
many of that group's candidates landed here versus how many exist across the
whole corpus, and which other slice ids hold the rest. This is what lets you
tell a near-duplicate you can actually judge from one your shard cannot see
the other half of -- see §3 Step 2.

`00-objective.json` carries `rb-triage-objective`'s ruling: `declared_objective`,
whether it is `supported`, `predicted_surface_count`, and the `surfaces` that
pass's map-level reading already named. Read it for two things. First, the
same objective your shard's own `request.objective` already states -- reading
both is not redundant, because `00-objective.json` also carries whether a
human is going to see it marked unsupported, which does not change how you
rule (§5) but tells you the record you are contributing to is one a human at
gate 0 will be reading skeptically. Second, and this is what `observed_surfaces`
(§2) is for: which surfaces that pass already predicted, so you report only
the ones your shard's candidates show that its map-level reading did not
already name.

You are dispatched with no memory of any conversation before you, and
nothing you write carries forward as memory. What you need is in these two
files.

## 2. Output

One file: `00-dispositions/<slice_id>.json`, validating against
`dispositions-part-0.1.json`. It carries `schema_version: "0.1"`, the
`run_id` and `slice_id` read from your own shard (never invent either, and
never derive `run_id` from the run directory's name), and three arrays:
`dispositions`, `observed_surfaces`, and `deficiency_notes`.

**`00-dispositions/` does not exist when you are dispatched, and creating it
is not your job.** `triage-slices` mkdirs `00-slices/` for the shard you
just read, which makes the sibling directory look like a precedent; it is
not one. Nothing in `src/rubrica/` mkdirs yours -- your `Write` creates it,
parents and all, exactly as every `rb-extract` member's `Write` creates
`01-claims/`. **Do not reach for `mkdir`.** This project's dispatch allows
`rubrica *` through Bash and nothing else, so the command lands on an
approval prompt that `claude -p` cannot answer. MEASURED 2026-08-23: a
member that tried it spent roughly seven turns and one
`dangerouslyDisableSandbox` escalation attempt on that one command before
naming `Write` as the way round it.

**All three are required at the document root, and an empty
`observed_surfaces` or `deficiency_notes` is still written as `[]`** --
`dispositions-part-0.1.json` requires every one of them, so a part with
nothing new to report in the last two still carries `"observed_surfaces": []`
and `"deficiency_notes": []`. `dispositions` alone carries a floor of one:
your shard always holds at least one candidate, and a part with none is a
member that wrote nothing, not a member with nothing to say.

**`dispositions[]`** -- **one entry for every candidate in your slice,
exactly once, including the ones you decline and the ones marked
`admissible: false`.** A container is inadmissible because its elements are
the real candidates; decline it, and say that is why. Nothing you write may
name a candidate outside your own shard.

**Every entry carries four required keys: `candidate_id`, `disposition`,
`reason`, and `authority`** -- and the ruling itself is the one called
`disposition`, holding exactly `"admit"` or `"decline"`. Nothing here is a
field you may rename: `dispositions-part-0.1.json` requires all four and is
`additionalProperties: false`, so a synonym does not read as a near miss, it
fails layer 1 outright. MEASURED 2026-08-20, on three consecutive dispatches
of the monolithic stage this pass replaced: all three wrote `verdict` instead,
which the prose of the day described at length while never once naming, and
every entry failed validation. Worse than the failure, the consuming code
keys off `disposition`, so `rubrica gate-brief --gate 0` rendered zero admits
and zero declines at exit 0 -- a human was handed an empty selection presented
as a clean one. State the key, not only what it means.

Every disposition also carries `authority: "triage"`. You are the only
writer of your part, so every disposition you write carries that value --
`"human"` is what a gate-0 override or `rubrica adopt-projection` carries once
the sealed record exists. State the value rather than leaving it implicit:
once `triage-seal` composes every slice's part into `00-triage.json`, a
reader needs to tell which admissions this pass authored from which a human
made at the gate, and `authority` is the only field that says so.

An `admit` carries `disposition: "admit"`, `reason` (prose) and a `priority`
-- an integer rank, 1 for the most valuable, expressing where you would spend
the extraction budget first. **This rank is within your slice only.** You
cannot see any other slice's candidates, so you cannot and must not guess at a
global rank -- `triage-seal` is what composes every slice's within-slice
priorities with a surface-level ranking into the run's actual global order.
Rank only against the other admits in front of you.

A `decline` carries `disposition: "decline"`, `reason` (prose) and a
`reason_code` from this list:

| Code | Use it when |
|---|---|
| `off_objective` | Real evidence about the target, but not about what this run is for |
| `out_of_scope` | Belongs to a surface `scope_note` excludes |
| `near_duplicate` | An admitted candidate *in this slice* carries the same shape; name it in `reason` |
| `superseded` | Something more authoritative says the same thing; name it |
| `implementation_detail` | Describes how, where the objective needs what |
| `no_evidence_value` | Carries no statement about the target at all |
| `digest_insufficient` | You cannot rule on it from its digest |
| `needs_projection` | Valuable, not usable as-is; write the projection's brief in `reason` |

`digest_insufficient` obliges you to write a matching entry in
`deficiency_notes[]` naming that same `candidate_id` -- `check-refs` rejects
your part if the pair never appears. `needs_projection` obliges no entry in
your own part (`dispositions-part-0.1.json` has no `projections[]` field);
`rb-triage-audit` reads every part's `needs_projection` declines and their
`reason` prose, across every slice, and writes the actual `projections[]`
entries into `00-audit.json` once your part and every sibling's have landed.
Your `reason` is the only material it has to work from, so write it as if it
were the brief.

**`observed_surfaces[]`** -- surfaces your slice's candidates show that
`00-objective.json`'s own `surfaces` did not already name. You are not
reconciling the two lists yourself; `triage-seal` does that once every part
has landed. Write only what you see that the map-level pass missed, in the
same shape as its own surfaces (`name`, `evidence`, `weight`).

**`deficiency_notes[]`** -- raw notes, not full `deficiencies[]` records:
each is a `candidate_id` and a `statement`. Every `digest_insufficient`
decline needs one entry naming it here. `rb-triage-audit` deduplicates notes
across every slice and mints the real `deficiency_id`s in `00-audit.json`;
you are not minting one yourself.

## 3. Method

**Step 1 -- read your shard's `request` and `00-objective.json` first,
before any candidate.** The objective decides every subsequent call, and a
reading that starts from the candidates arrives at a scope and then
rationalises the objective to fit it.

**Step 2 -- rule on every candidate in your slice.** Prefer behavioural
evidence over prose about behaviour: a trace records what the target *did*,
prose records what someone intended. Both are legitimate, and when they
conflict that conflict is itself worth admitting rather than resolving --
`rb-reconcile` records contradictions and is better placed to.

For near-duplicates, admit the one with the most distinct shape rather than
the largest or the newest. On the 2026-08-13 corpus, seven traces of 130 were
kept for distinct shape across the whole corpus -- one aggregation, two
triages, two multi-hop debugs, one identity lookup, and one failure -- and
that last one was the run's only evidence of what the target does when
something goes wrong. **A failing trace is almost never a near-duplicate of a
successful one**, however similar its request looks.

Your shard's `provenance` bounds this judgment to what you can actually see.
`near_duplicate` is a judgment about candidates *in this shard* -- a
candidate whose only twin sits in a sibling slice is one you cannot compare
against, because you cannot read that slice's shard. Where `provenance` shows
a group was split (`other_slices` non-empty for a group your candidate
belongs to), say so in `reason` rather than writing it as if you had compared
against the whole group: "no duplicate found in this slice; this group is
also split across s02, s03" is honest about what you checked, and "no
duplicate exists" is a claim about candidates you never read.

**Step 3 -- note any surface your slice shows that the objective pass did not
already predict.** Compare what your candidates are evidence *about* against
`00-objective.json`'s `surfaces`. Anything not already named there is an
`observed_surfaces[]` entry.

**Step 4 -- check for absence you can see from here.** Walk the candidates
you declined `digest_insufficient` and confirm each has a matching
`deficiency_notes[]` entry. A note here is raw material for `rb-triage-audit`,
not a claim you are settling yourself.

**Step 5 -- run your gate.** `rubrica validate --stage triage-rule --run
<RUN>`. Fix what it reports and run it again. `check-refs` for your own part
is meaningful only after every sibling member has also finished -- it runs
once, over the whole fan-out, not per member.

## 4. Invariants

1. **Exactly one disposition per candidate in your shard.** Not fewer: an
   unruled candidate is indistinguishable from one nobody saw. Not more.
2. **Nothing in `dispositions[]` that is not in your shard's own
   `candidates[]`.** A candidate you wish existed, or one from a sibling
   slice, is out of contract, not a disposition you can write.
3. **Never admit a candidate whose `admissible` is `false`.**
4. **Every `digest_insufficient` decline is referenced by a `deficiency_notes[]`
   entry naming the same candidate, in this same part.**
5. **`priority` ranks only the admits in your own slice.** It is never a
   claim about the run's global order -- `triage-seal` composes that.
6. **`near_duplicate` is a judgment about candidates your shard can see.**
   Where `provenance` shows the group is split, say so in `reason`.
7. **You read your own shard and `00-objective.json`, and nothing else.** No
   candidate file, no sibling's shard, no other member's part, no
   `decisions.md`, no artifact from another run.
8. **`run_id` and `slice_id` are read from your own shard**, never invented
   and never derived from the run directory's name.

## 5. Refusal conditions

Each of these means: write no `00-dispositions/<slice_id>.json`, and report
what you found and why you stopped. A partial part is worse than none,
because it passes layer 1 and a reader has no way to tell it is incomplete.

**Refuse if your shard is missing, empty of candidates, or not readable as
its schema describes.** That is a `triage-slices` defect or a broken run, and
producing a ruling against it would attribute a scoping decision to a member
that was never actually dispatched with anything to rule on.

**Do not refuse if you would decline every candidate in your slice --
write the part anyway.** A slice can legitimately be all declines: a tests
subtree, a docs subtree, a slice that happened to draw nothing but
superseded copies. Refusing here would strand the run on a member whose
answer was correct. Only the union across every slice can say the corpus,
the objective, or the scope itself is wrong, and that judgment belongs to
`triage-seal`, once every part is in -- not to you, looking at one slice
alone.

**Do not refuse for a candidate you cannot judge.** Decline it
`digest_insufficient`, name the field you needed in `reason`, and write the
matching `deficiency_notes[]` entry. `rb-triage-audit` is what turns that
note into a real deficiency once every slice has reported what it saw, and
`check-refs` rejects your part if a `digest_insufficient` decline and its
note never appear together. One unreadable digest is not a reason to
abandon the rest of a good slice.
