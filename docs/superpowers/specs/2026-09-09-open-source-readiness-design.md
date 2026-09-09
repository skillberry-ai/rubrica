# Open-source readiness: policy files, DCO enforcement, and the internal issue citations

**Issue:** #24 — "Open-source readiness for the move to
`github.com/skillberry-ai/rubrica`: policy files, DCO enforcement, scanning, and
the internal references the tree still carries"

Design for the two workstreams of issue #24 that change files in this repository:
the preparation commit that mirrors `simulation-harness`'s `fb7116a`, and the
execution of decision 2 — rewriting every internal issue citation to carry its
finding rather than a pointer that will resolve to an unrelated issue in the
public repo.

Measured against both trees on 2026-09-09: rubrica's working tree on `main` at
`9f877b6`, and `simulation-harness` at `acb1c55`. Every count below is a
`git grep` over tracked files.

## What this design does not cover

Deliberately out of scope, each to its own follow-on:

- **The move itself** — pushing history, and configuring
  `skillberry-ai/rubrica`'s ruleset and scanning settings. The ordering
  constraint is real and is why this split is safe: a ruleset cannot require the
  `DCO` status check until a workflow publishes one, so the preparation commit
  has to land first regardless.
- **The post-move security-triage round.** Its size is unknown until scanning
  runs against a populated repo, so specifying it now would be inventing work.
- **`CHANGELOG.md`, a release process, and PyPI publication.** Issue #24 rules
  these out on the grounds that rubrica has no release process today and
  inventing one is not migration work.
- **History rewriting.** All 666 commits will carry `parsec`, `/home/bnayahu`
  and `github.ibm.com` into the public repo. `simulation-harness` did the same
  with its 292 — `fb7116a` is present in the public history at its original sha
  — so the preparation commit scrubs the tip and nothing else. This is stated
  rather than assumed because it is the one thing a reader might expect a
  "readiness" change to have done.

## The destination already exists

`skillberry-ai/rubrica` was created 2026-08-31: public, default branch `main`,
**empty** (`size: 0`, no commits — the API returns 409 on the commits endpoint).
So the destination is a reserved shell, not a repo mid-migration, and no scanning
wave has fired because there is nothing to scan yet. Issue #24 predates this
being checked.

## The five decisions, ruled

Issue #24 raises five decisions and states plainly that they are judgments rather
than patches. Two were ruled before it was parked; three are ruled here. All five
are recorded together because a future reader needs to know the last three were
*decided* rather than skipped.

### Decision 1 — internal target names: keep

`parsec` (41 tracked files) and `rossoctl` (6) are **kept**, unsubstituted and
ungeneralised. Pre-ruled: they are not secrets, so the measurements citing them
stay auditable, and two entries measured on the same corpus stay linked to each
other.

### Decision 2 — internal issue citations: rewrite to carry the finding

Pre-ruled. A bare `#N` resolves to a different, unrelated issue in the public
repo, which is worse than a dead link — it is a live link to the wrong thing. A
disclaimer line was considered and rejected, because it leaves the provenance
unverifiable for a reader who cannot reach the internal tracker.

The ruling says *what*, not *how*. The how is this design's second workstream,
and it is specified in "Workstream B" below.

### Decision 3 — personal paths and dead internal links: keep the records, fix the code

`/home/bnayahu` appears in 11 tracked files, and the three groups are different
in kind:

| Where | Hits | Ruling |
|---|---|---|
| `tests/fixtures/reservation-trajectories/trajectories{,2}.json` | 27 | **Keep.** Committed capture output; every hit is an `mlflow.source.name` value. |
| `docs/superpowers/` plans and specs | 7 | **Keep.** Inside the do-not-edit tree. |
| `scripts/capture-reservation-trajectories.py` | 2 | **Change.** `TOOL_DIR` and `AGENT_SRC` are live constants, not a record. |

The two `github.ibm.com` links, both in `docs/superpowers/specs/`, are **kept**
as dated provenance for the same reason as the seven docs hits.

Two grounds. First, `CLAUDE.md` and `docs/README.md` both hold that the dated
tree is recorded history and that a record of what happened is falsified, not
corrected, by a later edit — and committed capture output is the most literal
record in the tree, not the least. Second, and this is what makes the first
ground cheap to honour: **`bnayahu` is already public regardless.** All 666
commits carry `Jonathan Bnayahu <bnayahu@il.ibm.com>` as git author. Scrubbing a
home-directory path out of a fixture buys no privacy that `git log` does not hand
over on the first clone; it only costs a falsified record.

`simulation-harness`'s public tree has zero `/home/` hits, so this is a
divergence from the precedent, taken knowingly. The precedent is what we did
once, not a policy, and the harness had no committed capture output to weigh
against it.

What changes instead: `TOOL_DIR` and `AGENT_SRC` become environment reads with
their current values as documented defaults, and
`tests/fixtures/reservation-trajectories/README.md:35` — which today tells a
re-runner to edit both constants by hand — names the variables instead. That is
an improvement to live code, not a scrub.

### Decision 4 — the `rossoctl`-derived fixture: publish

`tests/fixtures/reservation-trajectories/` is live capture against
`rossoctl/examples` at `dbbc5e0f46cc92c8f642e44d1124965394cf36e5`. Issue #24
frames this as the one item that can stop the move, on the grounds that
publishing the fixture publishes a description of that target's tool surface.

**It is ruled publish, and the evidence is that the surface is already
published.** `skillberry-ai/simulation-harness` has shipped
`tests/fixtures/restaurant-reservation-api/` publicly since 2026-08-31, carrying
the same operations — `search_restaurants`, `check_availability`,
`place_reservation`, `list_reservations`, `cancel_reservation` — under the title
"Restaurant Reservation API" with a generic `contact.name` of "Reservation
Service Team" that `fb7116a` itself put there. The harness tree cites `rossoctl`
zero times.

So what rubrica's fixture would newly publish is not the tool surface. It is
1.8MB of agent *behaviour* against `examples/`, a demo application. No external
sign-off is sought, and the harness fixture is the evidence recorded on the
issue.

The fixture is load-bearing, which is why "drop it" was never the cheap option:
`tests/unit/test_trajectory_fixtures.py`, `tests/toy.py` and a comment in
`src/rubrica/survey.py` all depend on it.

One fact worth recording because it bears on any future re-capture rather than on
this ruling: `/home/bnayahu/work/rossoctl` no longer exists, so the capture is
not currently reproducible from this machine in any case.

### Decision 5 — no `THREAT_MODEL.md`; a scope statement in `SECURITY.md`

`simulation-harness` carries a `THREAT_MODEL.md` because it is a server that
accepts requests. Rubrica is a CLI, and the security-relevant surface it does
have is the dispatch harness, which a `SECURITY.md` scope paragraph can hold.

That paragraph must name three things, and the third is the one a reader cannot
get anywhere else:

1. `scripts/dispatch-stage.sh` passes credentials to a dispatched model.
2. It grants that model `Write`, **derived from the dispatched stage's own
   `writes` contract** — this is current state as of `9f877b6` (#33). The
   historical evidence for why the surface is worth naming is recorded at
   `docs/design/limitations.md:80`: a blanket grant, and later a run-directory
   grant, were each used by a stage to drop a scratch script where nothing
   reacted to it. Both scopings are pinned by tests. Stating the derived grant as
   today's behaviour and the wider ones as history is not a detail — describing a
   closed hole as open is the same class of error as the reverse.
3. **CodeQL does not read shell.** `dispatch-stage.sh` is a substantial shell
   program, so a clean CodeQL run is not evidence about it. Worth saying in
   `SECURITY.md` rather than only in a commit message, because the reader who
   most needs it is someone deciding what a green badge means.

Because there is no `THREAT_MODEL.md`, the harness `SECURITY.md`'s cross-reference
to it (its line 41) drops rather than being transplanted.

## Workstream A — the preparation commit

Mirrors `fb7116a`. The issue's own caveat governs the divergences: matching is
worth wanting for what a contributor sees and a scanner enforces, and is not a
reason to copy a choice whose cause does not apply here.

### Files added

| Path | Source | Adaptation |
|---|---|---|
| `CODE_OF_CONDUCT.md` | harness, Contributor Covenant 2.1 | enforcement routed to `skillberry-ai/rubrica`'s private advisories |
| `SECURITY.md` | harness | decision 5's scope paragraph added; the `THREAT_MODEL.md` reference dropped |
| `.github/PULL_REQUEST_TEMPLATE.md` | harness | as-is |
| `.github/ISSUE_TEMPLATE/bug_report.md` | harness | as-is |
| `.github/ISSUE_TEMPLATE/feature_request.md` | harness | as-is |
| `.github/ISSUE_TEMPLATE/config.yml` | harness | contact links repointed |
| `.github/dependabot.yml` | harness | **`docker` ecosystem block dropped** — rubrica has no Dockerfile |
| `.github/workflows/codeql.yml` | harness | `security-extended`, weekly cron |
| `scripts/check-dco.sh` | harness | as-is; it takes `BASE_SHA HEAD_SHA` as arguments, so it is portable unchanged |

Neither harness policy file carries a personal address — both route to GitHub
private vulnerability reporting — so the transplant is a URL swap, with no
contact to invent.

### Files changed

- **`pyproject.toml`** — `authors = [{name = "IBM Corp."}]`, matching `NOTICE`'s
  `Copyright IBM Corp. 2026` and the harness. This is package-metadata hygiene,
  not privacy: the git history carries the personal identity either way, as
  decision 3 records. Plus a `[project.urls]` block pointing at
  `github.com/skillberry-ai/rubrica`. PEP 639's `license` string is already
  present and there is no `License ::` classifier, so the mutual exclusion issue
  #24 flags is already satisfied — no change needed there, and no change should
  be made.
- **`.github/workflows/ci.yml`** — a `dco` job, and the action bumps
  (`actions/checkout@v4` → `@v7`, `astral-sh/setup-uv@v5` → `@v7`).
- **`scripts/capture-reservation-trajectories.py`** — decision 3's constants.
- **`tests/fixtures/reservation-trajectories/README.md`** — line 35 names the
  new environment variables.

`LICENSE`, `NOTICE` and `CONTRIBUTING.md` need no change. All three already exist
and are correct; `CONTRIBUTING.md` already documents `-S -s` with both flags
explained. What is missing is not the instruction but the enforcement.

### The `dco` job

Transplanted from the harness: pull-request only (a direct push to `main` has no
base to diff against), merge-base scoped so a moving base branch does not drag
unrelated commits in, and exempting merge commits and bot commits — a merge
commit contributes no authored patch and a bot cannot sign off. It needs
`fetch-depth: 0`, because the merge-base lookup fails against a shallow clone.

The harness's closing note applies verbatim and belongs in the issue rather than
in a file: the job is pull-request only, so a ruleset requiring a PR and the
`DCO` check is still needed on the public repo for it to bind. That is the
follow-on's first task.

### Its test is a pytest module, not a shell harness

The harness pairs `scripts/check-dco.sh` with
`scripts/tests/test-check-dco.sh`. Rubrica does **not** copy that. This repo
already drives a shell script from pytest —
`tests/unit/test_dispatch_harness.py` exercises `scripts/dispatch-stage.sh`, and
`tests/unit/test_docs_accuracy.py` loads `scripts/render-pipeline-diagram.py` by
path on the stated grounds that `scripts/` is a directory of tools rather than a
package. Adding a second, shell-native test harness would introduce a parallel
convention with no cause here, and `make test` would not run it.

So: `tests/unit/test_check_dco.py`, covering the signed case, the unsigned case,
the merge-commit exemption, the bot exemption, and the merge-base scoping.

## Workstream B — `docs/design/findings.md` and the 85 rewrites

### The measurement

85 citations across 35 tracked files, outside `docs/superpowers/`. Eleven
distinct issue numbers, heavily skewed:

| Issue | Hits | Issue | Hits |
|---|---|---|---|
| #6 | 46 | #8 | 2 |
| #18 | 10 | #15 | 2 |
| #17 | 8 | #12 | 2 |
| #4 | 5 | #1 | 2 |
| #3 | 4 | #19 | 1 |
| #5 | 3 | | |

Most of the hits are in code, not documentation: `src/` and `tests/` hold 62 of
the 85 between them, against 18 in `docs/` and 5 in `scripts/`. `tests/` alone
carries 48 across 21 files, and `docs/design/limitations.md` carries 13.

Two properties of the current state were measured because they set the risk:

- **No test asserts on the literal citation text.** Every hit in `tests/` is a
  docstring or a comment. So this is a prose problem, not a test-breakage
  problem.
- **Only `#3` has a `limitations.md` heading** (`### Issue #3 was closed on
  arithmetic…`, line 952). The other eleven are inline prose with nothing in-repo
  to point at. This is what rules out the cheapest-looking approach: "redirect
  each citation at the existing entry that records it" does not generalise,
  because for ten of the eleven there is no such entry. The provenance has to be
  *created*, not redirected.

### The document

New `docs/design/findings.md`: one short entry per cited issue, each carrying the
issue's title, what was measured, and what changed. Written from each issue's own
title and body — every one of the titles is already a descriptive statement of
its own finding, which is what makes this tractable.

It sits beside `limitations.md` rather than inside it, and the distinction is
load-bearing: `limitations.md` is *what is known to be wrong or missing, each
entry with the ruling that parked it*. Every one of these is closed and fixed.
Folding a fixed finding into the parked-defects document would misfile it in a
way a reader would act on.

`docs/README.md` gains one line under `## Design`, alongside `rationale.md` and
`limitations.md`.

Two constraints on how it is written, both from existing policy in
`tests/unit/test_docs_accuracy.py`:

- It is user-facing, so **no heading may count something that grows**. A
  heading like "The eleven findings" is not caught by the current `_GROWING`
  token, but the set grows every time an issue is closed and cited, so no heading
  carries a number. The document's own prose avoids one too.
- It must not carry a hand-typed test count.

### The rewrites

Each of the 85 sites becomes a named finding plus an anchor into
`findings.md`. The names derive from the issue titles, one per issue, fixed once
so that two sites citing the same finding stay linked to each other — decision
1's reasoning about co-measured corpora, applied to co-measured findings:

| Issue | Name |
|---|---|
| #1 | the unnamed disposition key |
| #3 | the untriageable catalogue |
| #4 | the chat-trajectory skeletons |
| #5 | the fan-out output directory |
| #6 | the read-coverage variance |
| #8 | the uncapped digest names |
| #12 | the digest over-read |
| #15 | the unfiltered stray write |
| #17 | the undrivable denominator |
| #18 | the enumeration deadlock |
| #19 | the silent fan-out gap |

Sites needing more than substitution:

- **`docs/design/limitations.md:952`** is a *heading* naming issue #3. It
  rewrites to the finding's name.
- **`src/rubrica/schema/inputs-seen-0.1.json`**'s `description` is shipped
  package data (`[tool.setuptools.package-data]` includes `schema/*.json`), so its
  rewrite lands in a wheel. It gets the same treatment, and cannot carry a
  relative Markdown anchor usefully — it names the finding in prose instead.
- **Sites where `issue #N` is doing grammatical work as a noun** — "Issue #6
  widened `utilisation.py`" — need the sentence recast rather than the token
  swapped. This is the part the ruling meant by "not mechanical", and it is why
  this is prose work rather than a `sed` script.

### The guard

A new policy predicate in `tests/unit/test_docs_accuracy.py`, following the
existing `_HISTORY_TREE` idiom in that file's policy block: no bare `#N` or
`issue N` outside `docs/superpowers/`.

It needs **two scan sets**, and that is the one structural change to the module.
The existing predicates run over `_user_facing()` — `README.md`,
`CONTRIBUTING.md`, `CLAUDE.md`, and `docs/**/*.md` excluding `superpowers`. A
docs-only guard would leave 62 of the 85 hits unguarded — 73% of them, in
exactly the `src/` and `tests/` comments where the problem mostly lives. So the
predicate also scans tracked files under `src/` and `tests/`, and `scripts/` for
the remaining 5.

Per `CLAUDE.md`'s rule for this repo, the predicate is **measured in both
directions before it is committed**: reintroduce a bare `#N` and confirm it goes
red; reword a rewritten citation meaning-preservingly and confirm it stays green.
A predicate nobody has watched fail is not yet a guard, and the mirror failure —
a phrase pin that breaks on an innocuous reformat — is equally real here.

## Testing

The three gates, green at every commit: `make test`, `make check` (which covers
`README.md` and `CLAUDE.md`, though neither is edited here), and
`uv run rubrica check-skills` exiting 0.

New tests:

- `tests/unit/test_check_dco.py` — the five cases named above.
- One predicate in `tests/unit/test_docs_accuracy.py`, measured in both
  directions.

No existing test should need changing. If one does, that is a signal worth
stopping on rather than editing through: it would mean a citation was
load-bearing in a way the measurement above missed.

`docs/` is excluded from ruff (`extend-exclude = ["docs"]`), so `findings.md` and
this spec carry no formatting obligation. `scripts/capture-reservation-trajectories.py`
is not excluded and must satisfy `ruff check` and `ruff format --check`.

## Commit sequence

Four commits, each `git commit -S -s`, each leaving the three gates green.
Workstream B lands before A so that the policy files arrive into a tree whose
citations are already clean, rather than the reverse — which would publish
`SECURITY.md` alongside 85 pointers to the wrong issues.

1. **Decision 3's code change** — `capture-reservation-trajectories.py`'s two
   constants become environment reads; the fixture README names them.
2. **`findings.md` and its index line** — the document only. No guard yet,
   because a predicate banning bare `#N` cannot be committed green while the 85
   citations are still there.
3. **The 85 rewrites, then the guard** — the substantive prose work across 35
   files, and in the same commit the predicate that pins it. They land together
   because that is the first point at which the guard passes. The predicate's
   red direction is measured against the pre-rewrite tree *before* this commit is
   made, not asserted after.
4. **The preparation commit** — everything in workstream A.

## What would falsify this design

Three things, named so they are checked rather than assumed:

- **A test that does assert on citation text.** The measurement says none does.
  If commit 3 breaks a test, the measurement was wrong and the rewrite needs
  per-site review rather than a naming table.
- **`check-dco.sh` depending on something the harness has and rubrica does not.**
  It was read as taking `BASE_SHA HEAD_SHA` and shelling out to git only. If it
  reaches for harness-specific configuration, the transplant becomes an adaptation
  and commit 4 grows.
- **A finding with no honest short name.** The naming table assigns one phrase
  to each of the eleven issues, written from its title before its body was read
  in full. If writing `findings.md` shows an issue whose finding cannot be carried
  by a phrase without distorting it, that entry keeps a longer name and the table
  is corrected. The finding is never trimmed to fit the name it was given — that
  would be the same error as presenting a reasoned number as an observed one.
