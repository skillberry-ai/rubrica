# Design rationale

The other documents under `docs/` describe what Rubrica does: the stages it
runs ([`docs/concepts/pipeline.md`](../concepts/pipeline.md)), the files that
pass between them
([`docs/concepts/artifact-contract.md`](../concepts/artifact-contract.md)),
the commands that drive it ([`docs/reference/cli.md`](../reference/cli.md)).
This one is about why it is shaped that way — including the shape decisions
that cost something, and were made anyway.

## The experiment

Rubrica is an experiment before it is a tool, and the question it exists to
answer is falsifiable: **does prompt-carried judgment survive a chain of
artifact handoffs well enough to produce a suite worth running?**

Every stage in the pipeline is a skill — a prompt, dispatched fresh, with no
memory of any stage before it. A skill carries judgment; it does not carry
state. The state lives entirely in the files each stage reads and writes. So
the question is really about the handoffs themselves: extract's claims have
to survive being read by reconcile, reconcile's world model has to survive
being read by propose, and so on down the rest of the pipeline, each stage a
fresh dispatch with no conversation to fall back on. If judgment degrades at any
handoff — if a claim reconcile should have kept gets dropped, if a
contradiction extract should have flagged gets silently resolved — nothing
carries it forward to be caught later. The chain is only as good as its
weakest link, and every link is a prompt.

That makes the question answerable both ways. It is falsified by a
reproducible failure mode: a defect that traces back not to a bad input or a
bug in the deterministic code, but to a stage's prompt-carried judgment
failing to survive its handoff — the same kind of information loss, showing
up run after run, at the same seam. It is *not* falsified by the pipeline
running to completion and producing a suite; a suite full of confabulated,
unfalsifiable-in-hindsight assertions would be evidence against the
hypothesis, not for it, if nothing could tell the difference. That is why so
much of what follows is about making a stage's reasoning visible enough that
a failure like that has somewhere to be seen, rather than about making the
pipeline more likely to finish.

## The yardstick

That last point is worth stating as a rule, because it is the test this
project applies to every change under consideration, including changes that
look like straightforward improvements:

> A change that makes the pipeline more likely to produce output while making
> a stage's judgment less observable is a loss, not a win.

Read literally: if a change makes some stage more likely to write a
schema-valid artifact — a looser refusal condition, a wider `reads`, a retry
that papers over a bad dispatch — but makes it harder to tell, afterward,
whether that stage reasoned correctly or guessed, the change has moved the
pipeline further from being able to answer the falsifiable question, not
closer. Throughput is not the metric. Observability of judgment is. A change
that costs some throughput to keep a stage's reasoning inspectable is the
kind of trade this project takes on purpose.

## Why artifacts on disk are the only channel

A stage is dispatched with exactly three things: the run directory, its stage
name, and the path to its skill file. Nothing else — no summary of what an
earlier stage concluded, no aside from the orchestrator about what to expect.
If a stage needs a fact, it reads it from an artifact in that run directory,
or it does not have it.

What this buys: every handoff between stages is a file that exists
independently of the conversation that produced it. It can be opened,
schema-checked, and diffed against the same stage's output from a different
run. Nothing a stage "knew" but didn't write down can affect a later stage,
because there is no channel for it to travel on. That is what makes the
chain in the falsifiable question actually testable — if the only thing that
crosses a handoff is a file, then a handoff failure has to show up as a
defect in that file, somewhere `rubrica validate` or `rubrica check-refs` (or
a human, at a gate) can find it.

What it costs is real and is paid on every single stage: nothing can be told
to a stage. If a fact needs to reach `rb-propose`, it has to already be
written into an artifact `rb-propose` is contracted to read — there is no
shortcut where the orchestrator just mentions it. This is why the skill
contract's `reads` list is not a suggestion; a fact missing from it is a fact
the stage provably cannot have used, and a fact present in it had better
actually be needed, or the contract is claiming an anchoring surface for
nothing.

## Why fan-out is about isolation, not parallelism

Several stages dispatch one subagent per item — one `rb-extract` per input
file, one `rb-instantiate` per active scenario, one `rb-challenge` per
instantiated instance — and it would be easy to read that as an optimization:
running independent work concurrently instead of serially. That is not the
reason it exists.

An `rb-extract` member for one input sees only that input's file, plus the
manifest. It does not see what any other extract member concluded, because
there is no file boundary through which it could. That means when a design
document says an endpoint returns 404 and a trace shows it returning an empty
list, no single subagent ever holds both facts at once and has to pick a
winner. Each writes what its own input actually shows;
`rb-reconcile-contradict`, reading every claim in its own subject across both
claim sets afterward, is where the disagreement first becomes visible —
and it is recorded as a contradiction in the world model, not silently
resolved by whichever file happened to load last into the same context. The
same logic runs through instantiate and challenge: an instantiate member
builds one seed world without seeing what any other scenario's world looks
like, and a challenge member is handed the seed and the scenario's claimed
answer with no visibility into how confident the pipeline is about anything
else. Isolation is what turns "the inputs disagree" from something one
reader would have to adjudicate on the spot into something the pipeline is
structurally forced to write down.

## Why `emit` is code and not a prompt

Every judgment-bearing stage in Rubrica is a skill — a prompt. `emit` is the
one stage that *looks* like judgment and is not: it is deterministic Python
(`src/rubrica/emit.py`), invoked through a thin skill (`rb-emit`) that exists
only as the human-facing entry point.

The stages in `skills.CODE_ONLY_STAGES` are code as well, and the argument below
is the one several of them rest on — but none of them was ever a candidate for
judgment. They mint run ids and timestamps, partition a catalogue by byte budget,
assemble a family's staged parts, or derive one document from another that a pass
has already judged. `emit` is the case where this argument had to overrule a
stage a reader would expect to be a prompt, which is why it is the one the
heading names.

The reason is the reproducibility criterion the whole pipeline is held to. If
`emit` compiled the accepted scenarios into a runnable suite by prompting a
model, then two runs that produced byte-for-byte identical stage-4
(`04-instances/`) and stage-5 (`05-verdicts/`) artifacts could still emit two
different suites — different task wording, different ordering, different
verifier code — for no reason traceable to anything either run actually
decided. At that point a difference between two suites could no longer be
attributed to a stage: it might be a real difference in judgment somewhere
upstream, or it might just be emit rolling differently on an identical
input, and nothing would tell you which. Making emit a pure function of its
inputs closes that off. Every other stage is judgment by design; emit is
input-in, package-out by design, for the same reason a scorer has to be
trustworthy rather than merely plausible.

## Why gate 0 cannot be triage's own gate

Rubrica has four human gates. Gates 1 through 3 all share a shape: each
reviews a judgment made *from* evidence that is already sitting in the run —
a world model, a scenario list, a set of verdicts. A human overturning one of
them is correcting an inference about the target system, using the same
artifacts the stage that made the inference had in front of it.

Gate 0 is not that. The `triage-*` family reads a catalogue of candidate
inputs and rules on each one — admit, decline, or flag for a manufactured
projection — and nothing downstream of `intake` ever reads the corpus again.
`rb-extract` sees only what `intake` admitted; a candidate the family
declined is not deferred for some later stage to reconsider, it is gone as
completely as if the corpus had never contained it. That makes gate 0 a
decision about what the run can ever know, not a decision about how well the
run reasoned from what it already had — and it is why triage cannot also
hold its own gate. If the party selecting which inputs to admit were also
the party ratifying that selection, no stage after it could ever surface a
candidate it was wrong to exclude, and the run's account of the target would
be unfalsifiable in exactly the way the whole project is trying not to be: a
bad exclusion would look, from every downstream artifact, identical to a
corpus that simply never contained the excluded fact. A separate human at
gate 0 is what keeps "we decided not to look at this" a decision someone
else can see and overturn, rather than a foregone conclusion the run
rubber-stamps on its own input selection. `rb-orchestrate` — the skill that
holds gates 1 through 3 — dispatches no pass of the triage family and never
holds gate 0; by the time it is ever dispatched, triage and gate 0 are both
already finished.

## Why refusal conditions are the most important prompt-level decision

Every skill's prompt ends with a "Refusal conditions" section: the
circumstances under which the stage should record a gap, or halt, rather than
produce an answer. This is treated as the single highest-leverage
prompt-level decision in the whole design, and the reason is a specific
failure mode rather than a general worry about quality.

A model handed an underspecified input does not usually stall — it fills the
gap with something plausible and keeps going, because that is what being
helpful trained it to do. Handed a world model with a hole where error
semantics should be, a stage with no refusal condition covering that hole
will invent error semantics rather than say so, and every stage downstream of
it will treat the invention as fact, with no artifact anywhere recording that
it was ever a guess. A refusal condition is explicit license to fail loudly
instead: write `blocked_by_gap`, decline a candidate, rule a scenario
ambiguous — and that has to be written against the model's own default,
because the default is confident completion, not honest uncertainty.

Not every refusal condition earns its place, and the same three checks apply
to each one written into a skill. A trigger with no stated action is
decorative — it names a bad situation but never says what the stage should
do about it. An action a model cannot actually take is decorative — telling a
stage to "invoke a check it has no access to" is not a real instruction. And a
condition a model cannot detect from what it is contracted to read is
decorative for the same reason a `reads` list matters at all: a stage cannot
act on evidence it was never given.

The third check has a worked example in the pipeline. Each member of
`rb-triage-rule` reads one slice of the catalogue, so "every candidate in
the corpus was declined" — the clearest available signal that the objective
or the scope itself is wrong — is a condition no member can detect. A member
drawing a `tests/` subtree with nothing worth admitting would be right to
decline all of it, and refusing there would strand the run on an answer that
was correct. Written into the member's prompt the condition would be
decorative in exactly the third sense, so it is written into `triage-seal`
instead — the one layer that reads the union of every part. That is the
usual remedy: a condition a stage cannot detect moves to the layer that can,
rather than being dropped.

## What has actually been observed

The pipeline has been run end to end, with a model dispatched at every stage,
against the two-capability toy world that this repository's fixtures are
built around. Separately, both negative refusal fixtures — one built around a
contradiction between inputs, one built around a genuine gap — have been
exercised against a live model, and in both cases the stage produced a
recorded decline rather than a guess. Those outputs are committed under
`tests/fixtures/<name>/recorded/`, so a refusal observed once does not have
to be taken on faith the next time this repository is read; it is a
regression test.

`tests/unit/test_refusal_fixtures.py` and
`tests/unit/test_refusals_live.py` are the assertions that hold those facts;
they will fail loudly if a fixture stops carrying the defect it was built to
exercise, or if a re-recorded dispatch stops declining where the earlier one
did. Most of the pipeline's skills also carry an `exercise.md` beside their
`SKILL.md`, recording what one measured dispatch actually did — not a
reasoned estimate of what it should do. The prompt passes of the `triage-*` and
`reconcile-*` families are the exception and have none, which
[`docs/design/limitations.md`](limitations.md) records as a gap in the
evidence rather than something this document should explain away.

## What is not yet known

One exercise is one sample. A prompt that refused correctly once, or produced
a sound world model once, has not thereby been shown to do so reliably —
`diff-runs` exists specifically to measure whether two runs over the same
inputs land on the same judgment, and that measurement has not been taken at
scale. The prompt stages this document's reasoning is built around —
extract through emit — have not yet been run, end to end, against a real
target system; the only run of that chain this document can point to is
against the toy world built to exercise the contract. What changes when the
inputs are large, messy, and genuinely contradictory in ways nobody
constructed on purpose is open. [`docs/design/limitations.md`](limitations.md)
is the record of what is known not to work yet, including the design
questions that were raised and deliberately parked rather than resolved —
read it before treating an absence of a finding as evidence that a corner of
the pipeline works.
