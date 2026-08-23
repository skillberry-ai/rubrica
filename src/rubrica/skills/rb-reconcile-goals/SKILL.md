---
name: rb-reconcile-goals
description: Name the actors the claims support and enumerate, from their perspective, the goals this run will be measured against -- the half of the coverage denominator no later stage may add to.
---

# rb-reconcile-goals

You are dispatched once, after `rb-reconcile-entities` and before
`rb-reconcile-gaps`. You write the goal list, and the goal list is half the
frozen coverage denominator: `reconcile-seal` counts it, `rb-propose` designs
scenarios against exactly it, and a later stage may only *request* an
amendment. Nothing else in this family is frozen the way your output is.

## Contract

```toml
stage = "reconcile-goals"
reads = ["manifest", "claims_dir", "contradictions_dir", "capabilities_part", "entities_part"]
writes = ["goals_part"]
schemas = ["goals-part"]
invokes = ["validate", "check-refs"]
```

## 1. Inputs

You read the five things this skill's contract names under `reads`:
`manifest.json`, every file under `01-claims/` (`claims_dir`) -- not one of
them, all of them -- every file under `01-contradictions/`
(`contradictions_dir`), `01-capabilities.json` (`capabilities_part`), and
`01-entities.json` (`entities_part`). Every pass in this family reads all of
the claims; the family is split on *output*, not on claims, which is what keeps
the barrier property the single-dispatch stage had.

The capability and entity lists are there so a goal you write is one the
target can actually be asked to serve: a goal no declared capability could
advance is a denominator cell no scenario can ever close. The contradictions
are a constraint, not background: where a disagreement is recorded
`unresolved`, a goal must not be phrased so that it presumes one side. A goal
has no `rationale` field, so a disagreement settled here is settled with no
record that a choice was made.

Nothing else on disk is yours to read. In particular, no pass reads
`01-world-model.json`: it does not exist yet when you run, and on a re-run of
this family it is an answer some earlier run assembled rather than evidence
about the target. A later pass reading an earlier pass's partial *is* the
design here -- that is what each pass's `reads` list is for -- but a
re-dispatched pass does not read its own previous output: a repair hands you
findings about the artifact you wrote, not permission to reread it instead of
the claims. You are dispatched with no memory of any conversation that came
before you, and nothing you write here carries forward as memory either:
whatever you need to do this job has to be in the manifest, in the claims, in
the contradictions, in the two partials above, or in this document.

## 2. Output

One `goals-part-0.1.json`-shaped document, written to `01-goals.json`
(`goals_part`). It carries `schema_version: "0.1"`, an `actors` array, and a
`goals` array. Each actor has an `id`, a `name` and its `claims`; each goal has
an `id`, the `actor_id` that holds it, a `statement`, the
`expected_hop_depths` it supports, and its `claims`. Actors travel with goals
in one artifact because every goal needs a real `actor_id` to resolve, and a
goal list written against actors from another file could not check itself.

**This goal list is frozen the moment you write it.** `rb-propose` designs
scenarios against exactly this list and may only *request* an amendment, which
costs an explicit orchestrator decision recorded in `decisions.md` and a
`denominator_version` bump passed to `reconcile-seal` -- never a silent
addition by a later stage. A denominator that a later, more permissive stage
could also invent goals into is not a real denominator: it is a number that
stage can inflate its own coverage against by discovering more of it after the
fact. So write every goal the claims honestly support **now**. Writing too few
is a request-and-wait later, not a quiet fix.

## 3. Method

1. **Identify the actors from the claims.** An actor is someone or something
   the claims say uses the target -- a role, a job function, a calling system.
   Cite the claims each one rests on. An actor you cannot cite is one you
   invented, and every goal under it inherits that.

2. **Enumerate goals from the actors' perspective, each with the
   `expected_hop_depths` it supports.** A goal is what an actor is trying to
   find out or get done, stated in their terms rather than in the target's:
   "find out why a job failed", not "call the jobs endpoint twice". The hop
   depths are how many tool calls a scenario serving this goal would
   reasonably need -- one for a direct lookup, two or more where the answer
   requires a result from a previous call.

3. **Check each goal against `01-capabilities.json`.** If no declared
   capability could advance it, either the goal rests on a capability nobody
   declared -- which is something `rb-reconcile-gaps` audits for and records --
   or the goal is one you invented. Neither is fixed by writing the goal
   anyway.

4. **Write every goal the claims support, including the unglamorous ones.**
   The pressure here runs the wrong way in both directions: too few goals and
   the denominator is small enough that a thin suite looks complete; too many
   invented ones and `rb-propose` is asked to design against goals no claim
   supports. Only the claims settle which.

## 4. Invariants

1. Every `goal.actor_id` names an actor you declared in `actors` in this same
   file. A goal with no real actor resolves to nothing downstream, and
   `refs.check_world_model` reports it after the seal.

2. Every actor and every goal carries at least one `claims[]` entry, and every
   entry resolves to a claim id that actually exists in `01-claims/`. Layer 1
   enforces the first (`claim_refs` carries `minItems: 1`);
   `refs.check_world_model` enforces the second, after the seal.

3. Actor and goal `id`s are unique. `reconcile-seal` counts the goals into
   `denominator.goals` and `rb-propose` cites `goal_id` on every scenario, so
   two goals sharing an id are one cell in the denominator and two in the
   design.

4. `expected_hop_depths` is non-empty for every goal, and every value is a hop
   count a scenario could actually reach against the declared capabilities.

Before you report done, run
`rubrica validate --stage reconcile-goals --run <run>` and then
`rubrica check-refs --run <run>`, where `<run>` is the run directory you were
dispatched with. `--run` is required on both: without it the command exits 2
on a usage error and tells you nothing about your artifact. `check-refs` runs
every checker the run has inputs for, so it may also name an artifact an
earlier pass wrote; the findings that are yours name `01-goals.json`, and those
are your own defect to fix rather than findings to pass along. Repair the
artifact and run both again; report success only once both exit clean.

## 5. Refusal conditions

Every condition below is one where the honest goal list is shorter, or
emptier, than one you could have written -- and one of them is the case where
the honest output is a list with no goals in it at all. Both failures are real
here: an invented goal is a denominator cell `rb-propose` must design against
with nothing to design from, and a missing one is coverage the run can never be
measured on.

- **You cannot identify any actor.** Write no goals, and report that. A goal
  list with no actor behind it is not a smaller, more conservative denominator
  -- it is a denominator you invented the shape of, because every goal needs a
  real `actor_id` to resolve. This is a gap that blocks `propose`, and
  `rb-reconcile-gaps` reads the same claims you do; your part of it is to
  refuse to manufacture an actor so that the goal list looks populated.

- **You are tempted to add a goal because a user of a system like this would
  obviously want it.** Do not. That reasoning is convention knowledge standing
  in for evidence the claims do not contain, and it would produce the same goal
  whether or not any input had ever been extracted. Every goal you write is a
  cell `rb-propose` is obliged to design a scenario against and `rb-score`
  counts against the run's coverage: an invented one is a permanent hole that
  no evidence can ever close.

- **A goal is supported by the claims but you are unsure it is worth
  testing.** Write it. Worth is not your call and it is not `rb-propose`'s
  either -- the goal list is frozen at your dispatch, so a goal you leave out
  because it looked minor costs an explicit orchestrator decision, a
  `denominator_version` bump and a re-score to put back.

- **A goal's phrasing would settle a disagreement recorded `unresolved`.**
  Phrase it so it does not: state what the actor wants, not what the target
  does. If the goal cannot be stated at all without picking a side, leave it
  out rather than picking one, because a goal is a place with no `rationale`
  in which to say that you did.
