# Open-source readiness: policy files, DCO enforcement, and the internal issue citations

**Issue:** #24 — "Open-source readiness for the move to
`github.com/skillberry-ai/rubrica`: policy files, DCO enforcement, scanning, and
the internal references the tree still carries"

Design for the three workstreams of issue #24 that change files in this
repository: the preparation commit that mirrors `simulation-harness`'s `fb7116a`,
the execution of decision 2 — rewriting every internal issue citation to carry its
finding rather than a pointer that will resolve to an unrelated issue in the
public repo — and a release process modelled on the harness's.

**The release process is a scoped-in reversal of one of issue #24's own
rulings.** The issue excluded it: *"`CHANGELOG.md` and a release path are
deliberately not in that list — rubrica has no release process today and
inventing one is not migration work. Whether it should be published to PyPI is a
separate question worth its own issue."* That ruling was overturned deliberately
on 2026-09-09, and it is recorded here rather than quietly dropped so that a
reader who finds the issue text first can see which document is later.

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
- **Registering the PyPI trusted publisher and creating the `pypi` GitHub
  environment.** Both are settings on services, not files in a commit, and they
  share the ordering property that makes this split safe: `publish.yml` is inert
  until a trusted publisher exists for this repository, workflow filename and
  environment, exactly as the `DCO` ruleset rule is inert until the job exists.
  Workstream C specifies the workflow; the follow-on registers the publisher.
- **`llm-switchboard`.** Its `publish.yml` carries the finding that motivates
  rubrica's OIDC choice (below) and it is cited here as evidence, but it is
  explicitly out of scope: no issue is filed against it and no change is proposed
  to it.
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
this ruling: `/home/bnayahu/work/rossoctl` is still present on this machine and
both default paths still resolve, but it is no longer a git checkout
(`git rev-parse HEAD` there reports "not a git repository"), so the
`dbbc5e0f46cc92c8f642e44d1124965394cf36e5` the fixture README's capture
conditions record can no longer be verified against it.

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

## Workstream B — `docs/design/findings.md` and the 118 rewrites

### The measurement

118 citations across 40 tracked files, outside `docs/superpowers/`. Thirteen
distinct issue numbers, heavily skewed:

| Issue | Hits | Issue | Hits |
|---|---|---|---|
| #6 | 48 | #4 | 5 |
| #37 | 23 | #3 | 4 |
| #18 | 10 | #5 | 3 |
| #17 | 9 | #1, #8, #12, #15, #19 | 2 each |
| #36 | 6 | | |

Most of the hits are in code, not documentation: `src/` and `tests/` hold 93 of
the 118 between them (`tests/` 68 across 25 files, `src/` 25 across 9), against 20
in `docs/` across 4 files and 5 in `scripts/` across 2.
`docs/design/limitations.md` carries 15.

**This baseline was re-measured on 2026-09-09 after PRs #38, #39 and #40 merged**,
superseding an earlier one of 89 across 35 files spanning eleven issues. Those
three added 29 citations in five files that did not exist when this design was
written, and two newly-closed issues to cite — #36 and #37. The re-measure was not
optional: the guard predicate below scans `src/`, `tests/` and `scripts/`, so it
cannot go green while any citation remains, and a stale scope would have left the
workstream unable to complete. Expect the same again if further work merges before
this lands.

**Four of the original 89 are invisible to a line-scoped search, and finding them changed
this number.** `git grep -E '(Issue|issue) #?[0-9]+'` reports 85, because four
citations wrap across a line break: `src/rubrica/brief.py:40` (`issue\n  #6`),
`src/rubrica/refs.py:3890` (`issue\n    #19`), `src/rubrica/rounds.py:939`
(`issue\n    17`) and `src/rubrica/utilisation.py:157` (`Issue\n    #6`). This is
why the guard predicate below must match across newlines rather than line by
line: a line-based guard would report a clean tree while four citations survived
it, which is the worst available outcome — a green gate over the exact defect it
was written for.

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

Each of the 118 sites becomes a named finding plus an anchor into
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
docs-only guard would leave 93 of the 118 hits unguarded — 79% of them, in
exactly the `src/` and `tests/` comments where the problem mostly lives. So the
predicate also scans tracked files under `src/` and `tests/`, and `scripts/` for
the remaining 5.

Per `CLAUDE.md`'s rule for this repo, the predicate is **measured in both
directions before it is committed**: reintroduce a bare `#N` and confirm it goes
red; reword a rewritten citation meaning-preservingly and confirm it stays green.
A predicate nobody has watched fail is not yet a guard, and the mirror failure —
a phrase pin that breaks on an innocuous reformat — is equally real here.

## Workstream C — the release process

Modelled on the harness, which is the instruction: mimic it except where a
sibling repo shows something better. Four places do, and one place cannot be
mimicked at all.

### What transplants unchanged

`scripts/release.sh` and the **two** libraries it sources — `scripts/lib/release-tag.sh`
(the single definition of what a release tag is: strictly `vX.Y.Z`, so a
`v0.3.0-rc1` is never treated as the previous release) and
`scripts/lib/release-notes.sh` (Conventional Commit subjects → grouped markdown).
Issue #24's checklist named only `check-dco.sh`, so the transplant is three
scripts and their tests rather than one — worth stating because it roughly triples
what the checklist implies.

`make release VERSION=0.2.0` runs on `main` only, with a clean worktree in sync
with `origin/main`. It bumps `version` in `pyproject.toml`, re-locks `uv.lock`,
prepends a `CHANGELOG.md` section, commits `chore(release): vX.Y.Z`, creates a
signed annotated tag, pushes `main` and the tag `--atomic`, and creates the
GitHub Release. `--dry-run` previews without writing.

The re-lock step is **required here, not optional**: `uv.lock:198` pins rubrica's
own version (`0.1.0`), so a bump that skipped the re-lock would leave the lockfile
stale — and CI runs `uv sync --locked`, which fails on a stale lock. The release
would therefore break the build it just tagged.

Resumability transplants with it, and it is the part worth keeping rather than
simplifying: four partial-failure states, each with exactly one move, documented
in a table. Resume is deliberately narrow — it fires only for a tag this script
created, on a `chore(release): vX.Y.Z` commit at `HEAD` whose `pyproject.toml`
already holds that version — so a hand-made tag is rejected rather than resumed
into a release with no bump and no changelog section.

### Generated changelog, and the measurement that settles it

The org holds two positions. `cap-evolve` and `skillberry-store` hand-maintain a
Keep a Changelog `## [Unreleased]` section; the harness generates from commit
subjects at release time.

Generation is right for rubrica, on evidence rather than preference:

- **`skillberry-store` states its own reason for hand-maintaining, and that
  reason does not hold here.** Its header says the squash-merge workflow collapses
  commit messages, so the changelog is the only place a migration note survives.
  Rubrica merges rather than squashes — 24 merge commits, every underlying subject
  preserved — so nothing is collapsed and nothing needs rescuing by hand.
- **640 of rubrica's 643 non-merge commits (99%) are Conventional Commits.**
  Measured on 2026-09-09 with the harness's own type list.
- **The generator was run against rubrica's history before this was specified,
  not after.** `generate_release_notes 'HEAD~12..HEAD'`, sourced unmodified,
  produced correctly grouped Features / Fixes / Documentation / Tests sections
  with scopes rendered as bold prefixes. `--no-merges` drops the 24 merge commits
  and picks up the real subjects beneath them, which is the behaviour rubrica's
  merge-based history needs.

So `CHANGELOG.md` is created seeded with a Keep a Changelog header and nothing
else; `release.sh` prepends every section after that.

### The four practices adopted from siblings

1. **PyPI Trusted Publishing, no stored token.** `.github/workflows/publish.yml`
   on `release: published` (plus `workflow_dispatch`), `permissions: {contents: read,
   id-token: write}`, `environment: pypi`, building an sdist and a wheel, `twine
   check dist/*`, then `pypa/gh-action-pypi-publish` **with no `password:` input**
   — OIDC only.

   The evidence is a gap in the one org repo that publishes to PyPI today:
   `llm-switchboard`'s `publish.yml` already sets `id-token: write` and
   `environment: pypi`, the complete OIDC scaffolding, and then passes
   `password: ${{ secrets.PYPI_API_TOKEN }}`. It is live on PyPI at 0.1.0, so the
   token path is the one doing the work and the OIDC block is inert. Rubrica takes
   the configuration that repo was evidently reaching for: no long-lived secret to
   rotate or leak, and PEP 740 attestations generated automatically. The
   `rubrica` name is unclaimed on PyPI as of 2026-09-09 (the JSON API returns
   404), which is also an argument for claiming it before the repo is public.
2. **`.github/workflows/dependency-review.yml`** — `llm-switchboard` has it,
   neither the harness nor rubrica does. Pull-request scoped,
   `fail-on-severity: high`, `permissions: {contents: read, pull-requests: read}`.
3. **Least-privilege `permissions:` at workflow level.** Neither the harness's
   `ci.yml` nor rubrica's declares a `permissions:` block, so both inherit the
   repository default. `ci.yml` gains `permissions: {contents: read}`; the `dco`
   job needs nothing more, since it only reads history.
4. **Changelog compare links**, from `cap-evolve`: `[Unreleased]` and per-version
   links to GitHub's `compare` view. The harness `CHANGELOG.md` has **zero** of
   them. Generation does not preclude them — they are header lines, not section
   content — so they go in the seeded header.

### What cannot be mimicked, and what replaces it

The harness's release publishes a **container image**: `docker-publish.yml`
triggers on `tags: ["v*.*.*"]`, so the tag push builds and pushes to
`ghcr.io/<owner>/simulation-harness`. Rubrica has no Dockerfile and is a CLI
library, so there is nothing to build and `docker-publish.yml` is not
transplanted. `docs/releasing.md`'s "Container images" section is replaced by a
PyPI section, and its note about the atomic push firing that workflow twice
drops with it.

`publish.yml` is what takes its place, and the two are the same shape: cutting a
release does not publish the artifact directly — publishing the *release* does.

### One practice deliberately not adopted

**No sha-pinning of actions.** Nothing in the org pins by commit sha; everything
floats on major tags, and the harness's `dependabot.yml` argues the choice
explicitly — floating majors pick up patches at run time, and Dependabot would
otherwise open a PR per patch release, which *narrows* the ref and adds churn.
Sha-pinning is GitHub's own hardening advice and the trade-off is real, but it is
org-wide supply-chain policy rather than release-process work, and adopting it
would mean revisiting those `ignore` rules in the same change. Named here so that
a reader can tell it was weighed rather than missed.

### Two documents no test will remind us about

`make release` is a new target, and two documents enumerate this project's
commands by hand: `CLAUDE.md`'s "Setup and commands" block and
`CONTRIBUTING.md`'s gate list. **No test guards either list** —
`tests/unit/test_docs_accuracy.py` checks stages, skills, subcommands and
artifact kinds against the code that owns them, and a Makefile target is none of
those. `release.sh` is a script rather than a `rubrica` subcommand, so
`cli.SUBCOMMANDS` and `docs/reference/cli.md` are correctly untouched and their
guard will stay green while the command list goes stale.

So both documents are updated in commit 5 as part of the work, not left to a test
to catch. Both are in `_user_facing()`, so their edits are subject to the
no-hand-typed-count and no-counting-heading policies, and `CLAUDE.md` and
`README.md` are not ruff-excluded — `make check` reads them.

### The harness gets an issue, not a patch

Practices 2, 3 and 4 apply to `simulation-harness` and it has none of them.
Rather than open a PR into another project's live release path from this branch,
this cycle files one issue against `skillberry-ai/simulation-harness` recording
all three with the evidence: no `permissions:` block in `ci.yml`, no
`dependency-review.yml`, and zero compare links in `CHANGELOG.md`. Practice 1
does not apply to it — it publishes images with `GITHUB_TOKEN`, not packages to
an index.

## Testing

The three gates, green at every commit: `make test`, `make check` (which covers
`README.md` and `CLAUDE.md`, though neither is edited here), and
`uv run rubrica check-skills` exiting 0.

New tests:

- `tests/unit/test_check_dco.py` — the five cases named above.
- One predicate in `tests/unit/test_docs_accuracy.py`, measured in both
  directions.
- `tests/unit/test_release.py` and `tests/unit/test_release_notes.py` — the ports
  of the harness's two shell suites (402 and 150 lines respectively).

### Why the shell suites become pytest modules

The harness keeps its script tests as shell — `scripts/tests/test-release.sh`,
`test-release-notes.sh`, `test-check-dco.sh`, 673 lines across the three — behind
a `make test-scripts` target. Rubrica does not copy that, and the reason is
stronger than the stylistic one given for `check-dco.sh` in workstream A.

`CLAUDE.md` states that `make test` green, `make check` clean, and
`rubrica check-skills` exiting 0 **are the three gates, and anything else means
something broke.** A `make test-scripts` target would be a fourth gate: one more
command a contributor and CI both have to remember, sitting outside the set the
project documents as complete. A gate nobody is obliged to run is a gate that
eventually stops running, and it would stop running silently.

Porting instead puts the release scripts under the gate that already exists.
The idiom is present: `tests/unit/test_dispatch_harness.py` drives
`scripts/dispatch-stage.sh` through `subprocess.run` with `tmp_path` fixtures,
and `tests/unit/test_docs_accuracy.py` loads a script from `scripts/` by path on
the stated grounds that it is a directory of tools rather than a package. The
harness suites build throwaway git repositories as fixtures, touch no network
remote and call no `gh`; `tmp_path` plus `git init` reproduces that directly.

This is the largest single piece of work in workstream C, and it is the piece
most likely to be underestimated — 552 lines of shell assertions to port, against
a script whose failure modes are the four resumable states.

No existing test should need changing. If one does, that is a signal worth
stopping on rather than editing through: it would mean a citation was
load-bearing in a way the measurement above missed.

`docs/` is excluded from ruff (`extend-exclude = ["docs"]`), so `findings.md`,
`CHANGELOG.md` and this spec carry no formatting obligation.
`scripts/capture-reservation-trajectories.py` is not excluded and must satisfy
`ruff check` and `ruff format --check`. The three transplanted shell scripts are
not Python and ruff does not read them, so nothing in `make check` covers them —
their tests are the only gate they have, which is a second reason those tests
belong under `make test`.

## Commit sequence

Six commits, each `git commit -S -s`, each leaving the three gates green.
Workstream B lands before A so that the policy files arrive into a tree whose
citations are already clean, rather than the reverse — which would publish
`SECURITY.md` alongside 118 pointers to the wrong issues. C lands last because it
is the only workstream whose output is inert until somebody configures a service,
so it is the one where a review pause costs nothing.

1. **Decision 3's code change** — `capture-reservation-trajectories.py`'s two
   constants become environment reads; the fixture README names them.
2. **`findings.md` and its index line** — the document only. No guard yet,
   because a predicate banning bare `#N` cannot be committed green while the 118
   citations are still there.
3. **The 118 rewrites, then the guard** — the substantive prose work across 40
   files, and in the same commit the predicate that pins it. They land together
   because that is the first point at which the guard passes. The predicate's
   red direction is measured against the pre-rewrite tree *before* this commit is
   made, not asserted after.
4. **The preparation commit** — everything in workstream A.
5. **The release scripts and their tests** — the three transplanted scripts,
   `CHANGELOG.md` seeded with its header and compare links, `docs/releasing.md`,
   the `release` Makefile target, and the two ported pytest modules.
6. **The publishing and hardening workflows** — `publish.yml`,
   `dependency-review.yml`, and the `permissions:` block on `ci.yml`. Separate
   from commit 5 because these three are the ones that do nothing until the PyPI
   trusted publisher and the `pypi` environment exist, and a reviewer should be
   able to see that boundary in the history.

Plus one action outside this repository: **an issue filed against
`skillberry-ai/simulation-harness`** for practices 2, 3 and 4. No change is
proposed to `llm-switchboard`.

## What would falsify this design

Five things, named so they are checked rather than assumed:

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
- **`release.sh` depending on something the harness has and rubrica does not.**
  The same risk as `check-dco.sh`, and larger: it is 18KB and it was read for its
  structure and its env knobs (`RELEASE_REMOTE`, `RELEASE_GH_REPO`,
  `RELEASE_SKIP_GH`), not line by line. The two sourced libraries were read in
  full and are self-contained. If `release.sh` reaches for a harness-specific
  path, target or config file, commit 5 grows and the port grows with it.
- **The changelog generator behaving differently at a real release boundary.**
  It was exercised over `HEAD~12..HEAD`, a range with no tag in it, because
  rubrica has no tags yet. The first real run computes `prev_tag` as empty and
  takes the whole history as its range, which is a path the trial did not cover.
  The dry run is what checks this, and it must be run before the first release
  rather than after.
