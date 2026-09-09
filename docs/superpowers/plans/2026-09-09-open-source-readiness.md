# Open-Source Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare rubrica for its public home at `github.com/skillberry-ai/rubrica` — policy files, DCO enforcement, a release process — and rewrite every internal issue citation so it carries its finding rather than a pointer that would resolve to an unrelated issue in the public repo.

**Architecture:** Three independent workstreams executed in a fixed order. **B first** (provenance: a new `docs/design/findings.md`, 118 citation rewrites, a guard predicate) so that policy files land into a citation-clean tree. **A second** (the preparation commit mirroring `simulation-harness`'s `fb7116a`: policy files, `.github/` templates, `check-dco.sh` + a `dco` CI job, package metadata). **C last** (a release process modelled on the harness: three transplanted shell scripts, a generated `CHANGELOG.md`, PyPI publication via Trusted Publishing) because it is the only workstream whose output is inert until somebody configures a service.

**Tech Stack:** Python 3.13, `uv`, pytest, ruff, bash, GitHub Actions, `gh` CLI. No new runtime dependencies.

**Spec:** [`docs/superpowers/specs/2026-09-09-open-source-readiness-design.md`](../specs/2026-09-09-open-source-readiness-design.md)

## Global Constraints

- **Every commit is `git commit -S -s`.** Both flags — `-s` is the `Signed-off-by` trailer, `-S` the cryptographic signature. If signing fails, **stop and report it**; never fall back to unsigned, never work around it.
- **Attribution trailer:** the session convention in force is `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`. Note this contradicts `CLAUDE.md` and `CONTRIBUTING.md`, which require `Assisted-By:` and forbid `Co-Authored-By:`. **Ask before the first commit which one this branch uses** and then use it consistently.
- **The three gates must be green at the end of every task:** `make test`, `make check`, and `uv run rubrica check-skills` exiting 0. There is no fourth gate, and this plan must not create one.
- **ruff:** `line-length = 100`, `select = ["E","F","I","UP","B","SIM"]`, `target-version = "py313"`. All of `docs/` is `extend-exclude`d, so Markdown carries no formatting obligation; everything under `src/`, `tests/` and `scripts/*.py` does.
- **Never edit a *record* under `docs/superpowers/`.** It is recorded history: a record of what happened is falsified, not corrected, by a later edit. **Two files there are exempt, and only these two:** `specs/2026-09-09-open-source-readiness-design.md` and `plans/2026-09-09-open-source-readiness.md` — this work's own live design and plan, created on this branch, describing work still in flight rather than work that happened. They are corrected when they turn out to be wrong, and leaving a known-false statement in either would be worse than editing it. The 45 other dated files in that tree are records and are off-limits. Verify with `git log --format='' --name-status origin/main..HEAD -- docs/superpowers/ | grep '^M'` — it must list only those two paths.
- **Never edit `tests/fixtures/reservation-trajectories/*.json`.** Committed capture output, ruled a record in the spec's decision 3.
- **The exit-code contract is load-bearing:** `0` clean, `1` findings one per line on stdout, `2` usage error or unreadable run. A stage defect must never surface as `2`; a `1` must never have empty stdout.
- **Comment density here is high and deliberate** — comments explain *why*, usually citing a measurement. Match that; do not strip them.
- **Do not write a test count anywhere.** `tests/unit/test_docs_accuracy.py` fails on a hand-typed count in any user-facing document, and no heading may count something that grows (stages, skills, subcommands, gates).
- **Measured baseline, corrected TWICE — read this before trusting any count below.** Total scope is **128** citations across 41 files spanning **14** issues. The first baseline (89/35/11) missed four citations that wrap across a line break. The second (118/40/13) missed **ten more in bare `#N` form** — a `#19` with no "issue" before it, and nine others — because the counting pattern required the word "issue", a "PR" prefix, or parentheses. It also missed a fourteenth issue, **#20**, cited once. Task 3 rewrote 31 sites in `src/` and `scripts/`; **97 remain — `docs/` 24 across 4 files, `tests/` 73 across 25.** Use the canonical enumeration script in the conventions section; do not write your own pattern.
- **Harness source tree for every transplant:** `/home/bnayahu/work/kaegis/simulation-harness` at `acb1c55`. Referred to below as `$HARNESS`.

---

## File Structure

### Created

| Path | Responsibility |
|---|---|
| `docs/design/findings.md` | One entry per closed-and-cited issue: title, what was measured, what changed. The in-repo provenance the 118 rewrites anchor at. Sibling to `limitations.md`, never inside it — `limitations.md` is what is *parked*, these are *closed*. |
| `CODE_OF_CONDUCT.md` | Contributor Covenant 2.1, enforcement routed to this repo's private advisories. |
| `SECURITY.md` | Reporting route plus the decision-5 scope statement naming the dispatch harness's credential handling, its contract-derived `Write` grant, and that CodeQL does not read shell. |
| `CHANGELOG.md` | Keep a Changelog header and compare links only. `release.sh` prepends every section after that. |
| `docs/releasing.md` | How to cut a release, and the four resumable partial-failure states. |
| `.github/PULL_REQUEST_TEMPLATE.md` | PR checklist, adapted to rubrica's actual three gates. |
| `.github/ISSUE_TEMPLATE/bug_report.md` | Bug form, adapted — rubrica has no server, no transport, no log path. |
| `.github/ISSUE_TEMPLATE/feature_request.md` | Enhancement form. |
| `.github/ISSUE_TEMPLATE/config.yml` | `blank_issues_enabled: true`. |
| `.github/dependabot.yml` | `pip` + `github-actions` weekly. **No `docker` block** — rubrica has no Dockerfile. |
| `.github/workflows/codeql.yml` | `security-extended`, weekly cron, **`language: [python]` only**. |
| `.github/workflows/dependency-review.yml` | PR-scoped, `fail-on-severity: high`. Adopted from `llm-switchboard`. |
| `.github/workflows/publish.yml` | On `release: published`. PyPI Trusted Publishing, **no `password:` input**. |
| `scripts/check-dco.sh` | Verifies every commit in a range carries a sign-off matching its author. Transplanted unchanged. |
| `scripts/release.sh` | Cuts a release: bump, re-lock, changelog, commit, sign, tag, atomic push, GitHub Release. Resumable. |
| `scripts/lib/release-tag.sh` | The single definition of a release tag: strictly `vX.Y.Z`. |
| `scripts/lib/release-notes.sh` | Conventional Commit subjects → grouped markdown. |
| `tests/unit/test_check_dco.py` | Port of `$HARNESS/scripts/tests/test-check-dco.sh` (121 lines). |
| `tests/unit/test_release_notes.py` | Port of `$HARNESS/scripts/tests/test-release-notes.sh` (150 lines). |
| `tests/unit/test_release.py` | Port of `$HARNESS/scripts/tests/test-release.sh` (402 lines). |

### Modified

| Path | Change |
|---|---|
| `docs/README.md` | One index line for `findings.md` under `## Design`. |
| 40 files across `src/`, `tests/`, `docs/`, `scripts/` | The 118 citation rewrites. Enumerated per task below. |
| `tests/unit/test_docs_accuracy.py` | One new policy predicate plus a `_code_files()` scan set. |
| `scripts/capture-reservation-trajectories.py:38-39` | `TOOL_DIR` / `AGENT_SRC` become environment reads with documented defaults. |
| `tests/fixtures/reservation-trajectories/README.md:35` | Names the new environment variables instead of telling re-runners to edit source. |
| `pyproject.toml:9` | `authors = [{name = "IBM Corp."}]`, plus a new `[project.urls]` block. |
| `.github/workflows/ci.yml` | A `dco` job, a workflow-level `permissions:` block, and action bumps `checkout@v4`→`@v7`, `setup-uv@v5`→`@v7`. |
| `Makefile` | A `release` target with a `VERSION` guard. |
| `CLAUDE.md`, `CONTRIBUTING.md` | Command lists gain `make release`. **No test guards these lists** — see Task 11. |

### Deliberately absent

- **No `THREAT_MODEL.md`** (spec decision 5). The harness `SECURITY.md`'s cross-reference to it drops with it.
- **No `docker-publish.yml`** — nothing to build.
- **No `.pre-commit-config.yaml` / `.secrets.baseline`** — not scoped by the spec.
- **No `scripts/tests/` directory and no `make test-scripts` target.** That would be a fourth gate. See Task 9's rationale.
- **No sha-pinning of GitHub Actions.** Org-wide policy, argued explicitly in the harness's `dependabot.yml`; out of scope.
- **No change to `llm-switchboard`.** Cited as evidence only.

---

# Phase 1 — Provenance and the citation rewrite (Workstream B)

The spec puts the 118 rewrites and the guard in one commit. **This plan splits
them into four commits** — one per tree, then the guard — and the deviation is
deliberate: a 35-file prose commit is not reviewable, and each tree's rewrites
pass the gates on their own because the guard does not exist yet. The guard lands
last, which is the first point at which it can be green.

### Task 1: Make the capture harness's target paths configurable

Spec decision 3: the fixture JSON and the `docs/superpowers/` hits are records
and stay. These two constants are live code, not a record, so they change.

**Files:**
- Modify: `scripts/capture-reservation-trajectories.py:38-39`
- Modify: `tests/fixtures/reservation-trajectories/README.md:35`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: two environment variable names later documentation refers to —
  `RUBRICA_ROSSOCTL_TOOL_DIR` and `RUBRICA_ROSSOCTL_AGENT_SRC`. No Python symbol
  changes: `TOOL_DIR` and `AGENT_SRC` keep their names and their `Path` type.

- [ ] **Step 1: Read the current constants and their surroundings**

Run: `sed -n '25,50p' scripts/capture-reservation-trajectories.py`

You are looking for how the file imports and whether `os` is already available.
Note the exact indentation and comment style — this repo's comments explain
*why*, citing measurements, and you must match that.

- [ ] **Step 2: Check whether this script is under test**

Run: `git grep -ln 'capture-reservation-trajectories' -- tests/`

Expected: `tests/fixtures/reservation-trajectories/README.md` only, plus possibly
`tests/unit/test_trajectory_fixtures.py`. If `test_trajectory_fixtures.py`
imports the script or loads it by path, read how before editing — that test must
keep passing.

- [ ] **Step 3: Replace the two constants with environment reads**

Both defaults are the current literal values, so behaviour on this machine is
unchanged. Note the script is not importable as a module (it lives in `scripts/`,
which is a directory of tools rather than a package), so there is no import-time
cost concern.

```python
# These two paths point into a checkout of the target this fixture was captured
# against. They are environment-overridable rather than hard-coded because the
# fixture README used to instruct re-runners to edit this source file by hand,
# which is a worse contract than a variable: editing source to run a script makes
# the edit indistinguishable from a change to the script. The defaults are the
# paths the 2026-08-12 capture actually used, kept verbatim so that record stays
# reproducible for whoever still has that checkout. Measured 2026-09-09: that
# directory is still present on the capture machine and both defaults still
# resolve there, but it is no longer a git checkout (`git rev-parse HEAD` reports
# "not a git repository"), so the commit sha the fixture README's capture
# conditions record can no longer be verified against it. Anyone re-running this
# anywhere else must set both.
TOOL_DIR = Path(
    os.environ.get(
        "RUBRICA_ROSSOCTL_TOOL_DIR",
        "/home/bnayahu/work/rossoctl/examples/mcp/reservation_tool",
    )
)
AGENT_SRC = Path(
    os.environ.get(
        "RUBRICA_ROSSOCTL_AGENT_SRC",
        "/home/bnayahu/work/rossoctl/examples/a2a/reservation_service/src",
    )
)
```

- [ ] **Step 4: Ensure `os` is imported**

Run: `grep -n '^import os\|^import ' scripts/capture-reservation-trajectories.py | head`

If `os` is absent, add `import os` in correct ruff `I` (isort) order — standard
library block, alphabetical.

- [ ] **Step 5: Verify ruff is clean**

Run: `uv run ruff check scripts/capture-reservation-trajectories.py && uv run ruff format --check scripts/capture-reservation-trajectories.py`
Expected: both pass. If `format --check` fails, run `uv run ruff format scripts/capture-reservation-trajectories.py` and re-check.

- [ ] **Step 6: Update the fixture README**

Replace the sentence at `tests/fixtures/reservation-trajectories/README.md:35`.
Current text:

```
`capture-reservation-trajectories.py`'s `TOOL_DIR` and `AGENT_SRC` constants
are absolute paths into this author's `rossoctl` checkout. Anyone else
re-running the harness must edit both before it will find the target.
```

Replacement:

```
`capture-reservation-trajectories.py` reads its two target paths from the
environment. The defaults are the paths the 2026-08-12 capture actually used,
written here relative to the `rossoctl` checkout named in *Capture conditions*
below; the script's own defaults are those two paths absolute:

    RUBRICA_ROSSOCTL_TOOL_DIR    -> examples/mcp/reservation_tool
    RUBRICA_ROSSOCTL_AGENT_SRC   -> examples/a2a/reservation_service/src

That checkout is still present on the capture machine and both defaults still
resolve there, but it is no longer a git checkout, so the commit sha in the table
below can no longer be verified against it. Anyone re-running the harness
anywhere else must set both. Set them rather than editing the script: an edit to
the source is indistinguishable from a change to the harness, which is exactly
what this record exists to let a reader rule out.
```

Do **not** touch anything else in this README. The capture-conditions table, the
`rossoctl` commit sha and the capture history are records.

- [ ] **Step 7: Run the three gates**

Run: `make test && make check && uv run rubrica check-skills`
Expected: all green, `check-skills` exits 0.

- [ ] **Step 8: Commit**

```bash
git add scripts/capture-reservation-trajectories.py tests/fixtures/reservation-trajectories/README.md
git commit -S -s -m "$(cat <<'MSG'
refactor(capture): read the rossoctl target paths from the environment

The fixture README told re-runners to edit two constants in the script by hand.
That is a worse contract than a variable: editing source to run a script makes
the edit indistinguishable from a change to the script, which is the one thing
this committed capture exists to let a reader rule out.

Defaults are the paths the 2026-08-12 capture used, kept verbatim so the record
stays reproducible for anyone who still has that checkout. The committed
trajectory JSON and the docs/superpowers/ hits are untouched -- they are records,
ruled so in the design, and /home/bnayahu is already public in every commit's
author field regardless.
MSG
)"
```

---

### Task 2: Create `docs/design/findings.md`

**Files:**
- Create: `docs/design/findings.md`
- Modify: `docs/README.md` (one line under `## Design`)

**Interfaces:**
- Consumes: nothing.
- Produces: **the anchor slugs every later rewrite links to.** Each entry's
  heading determines its GitHub anchor, so the heading text is an interface.
  Tasks 3–5 link to `docs/design/findings.md#<slug>`. Fix the headings here and
  do not rename them later.

- [ ] **Step 1: Read the two sibling documents to match their voice**

Run: `sed -n '1,40p' docs/design/limitations.md; echo ---; sed -n '1,30p' docs/design/rationale.md`

`findings.md` is a sibling of these, not a new genre. Match the register.

- [ ] **Step 2: Read all eleven issue bodies**

Run: `for n in 1 3 4 5 6 8 12 15 17 18 19; do echo "===== #$n"; gh issue view $n --json title,body --jq '.title, .body'; done`

This is the source material. Each entry states **what was measured** and **what
changed** — both from the issue itself. Do not reason a number into existence: if
an issue does not state a measurement, the entry says what it does say and no
more. A reasoned number presented as an observed one corrupts the evidence.

- [ ] **Step 3: Write the document**

Structure. **No heading carries a count** — the set grows every time an issue is
closed and cited, and `test_docs_accuracy.py` bans counting headings in
user-facing documents.

````markdown
# Findings

Defects that were found, measured, and fixed. Each entry is the finding a
comment or a document elsewhere in this tree cites: the citation names the
finding, and this file is where the measurement behind it lives.

This is not [`limitations.md`](limitations.md), and the difference decides which
file an entry belongs in. `limitations.md` holds what is **known to be wrong or
missing**, each entry with the ruling that parked it. Everything here is
**closed**. A fixed finding filed among the parked defects would be read as
still open, which is a difference a reader would act on.

Entries carry the finding's name, what was measured, and what changed. They do
not carry issue numbers: this project's history lived in an internal tracker
whose numbers do not survive into this repository, where the same number means
a different, unrelated issue.

## The unnamed disposition key

**What was measured.** <from issue #1: rb-triage's SKILL.md never named the
disposition key its schema required, so triage wrote `verdict` and gate 0
rendered an empty ruling while exiting 0.>

**What changed.** <what the issue records as the fix.>

## The untriageable catalogue

...
````

The fourteen entries, in this order, with these exact headings — **the naming table
is the interface Tasks 3–5 consume, so it is fixed here**. The last two were added
when PRs #38, #39 and #40 merged mid-execution and brought two newly-closed issues
into the tree; if Task 2 has already landed, they are Task 2b's job, not a rewrite
of Task 2:

| Heading | Anchor | Source issue |
|---|---|---|
| `## The unnamed disposition key` | `#the-unnamed-disposition-key` | #1 |
| `## The untriageable catalogue` | `#the-untriageable-catalogue` | #3 |
| `## The chat-trajectory skeletons` | `#the-chat-trajectory-skeletons` | #4 |
| `## The fan-out output directory` | `#the-fan-out-output-directory` | #5 |
| `## The read-coverage variance` | `#the-read-coverage-variance` | #6 |
| `## The uncapped digest names` | `#the-uncapped-digest-names` | #8 |
| `## The digest over-read` | `#the-digest-over-read` | #12 |
| `## The unfiltered stray write` | `#the-unfiltered-stray-write` | #15 |
| `## The undrivable denominator` | `#the-undrivable-denominator` | #17 |
| `## The enumeration deadlock` | `#the-enumeration-deadlock` | #18 |
| `## The silent fan-out gap` | `#the-silent-fan-out-gap` | #19 |
| `## The gap about the run` | `#the-gap-about-the-run` | #36 |
| `## The unrecordable understatement` | `#the-unrecordable-understatement` | #37 |
| `## The colliding batch ids` | `#the-colliding-batch-ids` | #20 |

If an issue's finding genuinely cannot be carried by its phrase without
distorting it, **change the heading here and record why in the commit message** —
then use the changed heading in Tasks 3–5. Never trim the finding to fit the
name.

- [ ] **Step 4: Add the index line to `docs/README.md`**

Run: `sed -n '43,50p' docs/README.md`

Insert after the `limitations.md` bullet, matching its question-form style:

```markdown
- [`design/findings.md`](design/findings.md) — What was found, measured and
  fixed, and what is the measurement a comment elsewhere is citing?
```

- [ ] **Step 5: Confirm no policy predicate fires on the new document**

Run: `uv run pytest tests/unit/test_docs_accuracy.py -q`
Expected: PASS. `findings.md` is under `docs/` and not under `superpowers/`, so
it is in `_user_facing()` and subject to the no-hand-typed-count and
no-counting-heading policies from the moment it exists.

If it fails on a counting heading, reword the heading — do not weaken the
predicate.

- [ ] **Step 6: Run the three gates**

Run: `make test && make check && uv run rubrica check-skills`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add docs/design/findings.md docs/README.md
git commit -S -s -m "$(cat <<'MSG'
docs(design): record the findings that closed, as the anchor citations will use

Issue numbers do not survive the move: the public repo starts at #1, so a bare
`#N` in a comment would resolve to a different, unrelated issue -- a live link to
the wrong thing, which is worse than a dead one. A disclaimer line was considered
and rejected, because it leaves the provenance unverifiable for a reader who
cannot reach the internal tracker.

This file is that provenance, in-repo and verifiable by anyone who clones. It is
a sibling of limitations.md rather than part of it: limitations.md holds what is
parked, and every entry here is closed. A fixed finding filed among parked
defects reads as still open.

The rewrites that cite these anchors follow, one commit per tree.
MSG
)"
```

---

### Task 2b: Add the two findings entries the merged PRs brought into scope

**Why this exists.** PRs #38, #39 and #40 merged into `main` while this plan was
executing, and were merged into this branch. They added 29 tracker citations across
five files and two newly-closed issues to cite: **#36** and **#37**. Task 2 shipped
eleven entries; the tree now needs thirteen. This is an extension of Task 2, not a
rewrite of it — the eleven existing entries and their anchors are untouched.

**Files:**
- Modify: `docs/design/findings.md` — append two entries

**Interfaces:**
- Consumes: the document and prose register Task 2 established.
- Produces: two more anchors that Tasks 3, 4 and 5 consume:
  - `## The gap about the run` → `#the-gap-about-the-run` (issue #36)
  - `## The unrecordable understatement` → `#the-unrecordable-understatement` (issue #37)

- [ ] **Step 1: Read the document you are extending**

Run: `sed -n '1,60p' docs/design/findings.md` then `grep -n '^## ' docs/design/findings.md`

Expected: a preamble and eleven `## ` headings. Match their register, structure and
length exactly — each entry is a short reference under two bold labels, not an essay.
**Do not edit any existing entry or the preamble.**

- [ ] **Step 2: Read both issues in full**

Run: `for n in 36 37; do echo "===== #$n"; gh issue view $n --json title,body,comments --jq '.title, .body, (.comments[]?.body)'; done`

Titles, for reference:
- **#36** — "rb-reconcile-gaps writes a blocking gap about the run when its inputs are absent, where its siblings refuse"
- **#37** — "Verdict flags carry difficulty_overstated but not difficulty_understated — the harmful direction is unrecordable"

- [ ] **Step 3: Write the two entries**

Append after `## The silent fan-out gap`, in this order, with these exact headings:

```markdown
## The gap about the run

**What was measured.** <from #36 and its closure>

**What changed.** <what the issue and its closing commit record>

## The unrecordable understatement

**What was measured.** <from #37 and its closure>

**What changed.** <what the issue and its closing commit record>
```

**The rule that governs this task, as it governed Task 2:** state what the issue
*measured*, and never present a reasoned, projected or constructed figure as an
observed one. If a figure was arithmetic, or a fix was verified structurally rather
than by a dispatch, say so in those words — the issues themselves carry such
qualifiers, and Task 2's entries preserved five of them. A defect of exactly this
class was found and fixed in Task 1 of this plan, so it is live, not hypothetical.

For #37 specifically, the tree already carries a long `limitations.md` entry
(`### An understated hop_depth is flagged and cannot be repaired`). **Read it before
writing**, and do not duplicate it: `findings.md` records what was measured and what
changed, `limitations.md` records what remains open. Cite neither from the other.

- [ ] **Step 4: Confirm no placeholder survives and the anchors are right**

```bash
grep -n '<[a-z]' docs/design/findings.md | grep -v '`' || echo "  no placeholders"
grep -c '^## ' docs/design/findings.md
```

Expected: no angle-bracket placeholders, and `13`.

- [ ] **Step 5: Run the docs policy suite, then the three gates**

Run: `uv run pytest tests/unit/test_docs_accuracy.py -q`
Expected: PASS. `findings.md` is user-facing: no hand-typed test count, and no heading
that counts something which grows. If a predicate fires, reword — never touch it.

Run: `make test && make check && uv run rubrica check-skills`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add docs/design/findings.md
git commit -S -s -m "$(cat <<'MSG'
docs(design): record the two findings the merged work brought into scope

PRs #38, #39 and #40 merged mid-execution and added 29 tracker citations across
five files, along with two newly-closed issues to cite. The document shipped
eleven entries; the tree needs thirteen, or those citations have nowhere to point
and the guard predicate cannot go green.

Extends the document rather than rewriting it: the eleven existing entries and
their anchors are untouched, so nothing already consuming them has to change.

Same evidence rule as the first eleven -- what the issue measured, with its own
qualifiers kept where a figure was arithmetic or a fix was verified structurally
rather than by a dispatch.
MSG
)"
```

---

### Task 2c: Add the fourteenth findings entry, for issue #20

**Why this exists.** The citation count was corrected twice. The second correction
found ten citations in bare `#N` form that the counting pattern had never matched —
and one of them, in `tests/unit/test_rounds.py:902`, is the only reference anywhere
to **issue #20**, a fourteenth closed issue. `findings.md` has thirteen entries, so
that citation has nowhere to point and Task 5 cannot rewrite it.

**Files:**
- Modify: `docs/design/findings.md` — append one entry

**Interfaces:**
- Consumes: the register Tasks 2 and 2b established.
- Produces: one anchor Task 5 consumes —
  `## The colliding batch ids` → `#the-colliding-batch-ids` (issue #20).

- [ ] **Step 1: Read what you are extending**

Run: `grep -n '^## ' docs/design/findings.md` — expect thirteen headings. Read two
entries in full to match the register: a short reference under two bold labels,
roughly 25-40 lines. **Do not edit the preamble or any existing entry.**

- [ ] **Step 2: Read the issue and its closing commit**

Run: `gh issue view 20 --json title,body,comments --jq '.title, .body, (.comments[]?.body)'`

Title: *"`propose-batches` restarts batch numbering each round, so round 2's scenario
ids collide with round 1's and the seal refuses the round"*.

Then find the commit that closed it: `git log --all --grep='Closes #20' --format='%h %s'`.
If the issue carries no closing comment, the commit is your evidence for what
changed — say so in the entry rather than implying the tracker recorded it.

- [ ] **Step 3: Read the site that cites it, so the entry serves that citation**

Run: `sed -n '895,910p' tests/unit/test_rounds.py`

This is the one place `#20` appears. The entry has to make that docstring
comprehensible to a reader who follows it.

- [ ] **Step 4: Write the entry**

Append after `## The unrecordable understatement`, with this exact heading:

```markdown
## The colliding batch ids

**What was measured.** <from the issue and its closing commit>

**What changed.** <what the closing commit records>
```

**The rule that governs this task.** State what the source *measured*. Never present
a reasoned, projected or constructed figure as an observed one; if the fix was
verified structurally rather than by a real dispatch, say so in those words. Three
prior tasks in this plan preserved such qualifiers and one earlier defect in this
plan was exactly this class of error.

- [ ] **Step 5: Verify**

```bash
grep -c '^## ' docs/design/findings.md
grep -n '<[a-z]' docs/design/findings.md | grep -v '`' || echo "  no placeholders"
uv run pytest tests/unit/test_docs_accuracy.py -q
```

Expected: `14`, no placeholders, docs suite PASS.

- [ ] **Step 6: Three gates, then commit**

Run: `make test && make check && uv run rubrica check-skills`
Expected: all green; the test count must stay at its current baseline.

```bash
git add docs/design/findings.md
git commit -S -s -m "$(cat <<'MSG'
docs(design): record the colliding batch ids, the fourteenth cited finding

The citation count was corrected twice. The second correction found ten citations
in bare `#N` form that the counting pattern had never matched, and one of them was
the only reference anywhere to a fourteenth closed issue -- so a real citation had
nowhere to point and the guard predicate could not have gone green.

Same evidence rule as the thirteen before it: what the source measured, with its
own qualifiers kept where a fix was verified structurally rather than by a
dispatch.
MSG
)"
```

---

## How to rewrite a citation (read once, applies to Tasks 3, 4 and 5)

**The rule:** replace the pointer with the finding's name from Task 2's table, and
make the provenance reachable. Two link forms, chosen by file type:

- **In Markdown** (`docs/**.md`): the name, linked to its anchor —
  `` [the read-coverage variance](findings.md#the-read-coverage-variance) ``.
  Use a path relative to the citing file: from `docs/design/limitations.md` that
  is `findings.md#...`; from `docs/reference/cli.md` it is
  `../design/findings.md#...`.
- **In code** (`.py`, `.sh`, `.json`): the name in prose, plus a bare path. A
  Markdown link in a Python comment is noise, and a JSON `description` string
  cannot carry one usefully. Write
  `the read-coverage variance (docs/design/findings.md)` on first mention in a
  file, and just the name on later mentions in that same file.

**Four grammatical shapes, with a worked rewrite each.** These are real current
sites; the pattern generalises to the rest.

1. **Subject noun** — the token is the sentence's subject.
   `src/rubrica/refs.py:2148`:
   `Issue #6 measured a pass's read coverage of 01-claims/ varying 3/23 to 23/23`
   → `A pass's read coverage of 01-claims/ was measured varying 3/23 to 23/23 --`
   `the read-coverage variance (docs/design/findings.md)`.
   Recast to put the *measurement* in subject position. Do **not** write "the
   read-coverage variance measured …" — a finding does not measure anything.
2. **Temporal / prepositional** — `until issue #6`, `since issue #6`.
   `src/rubrica/utilisation.py:83`:
   `$defs/gap carried no claims array at all until issue #6`
   → `$defs/gap carried no claims array at all until the read-coverage variance`
   `was closed`. The added verb is required: a finding is not a point in time, but
   its closure is.
3. **Attributive possessive** — `issue #6's three sites`.
   `tests/unit/test_refs_planning.py:473`:
   `at each of issue #6's three sites` → `at each of the read-coverage variance's`
   `three sites`. Substitutes cleanly; no recast needed.
4. **Heading** — the only one in the tree.
   `docs/design/limitations.md:1021`:
   `### Issue #3 was closed on arithmetic, and the run that would confirm it has not happened`
   → `### The untriageable catalogue was closed on arithmetic, and the run that would confirm it has not happened`.
   Then run `git grep -n 'closed on arithmetic'` and fix any cross-reference to the
   old heading text or its anchor.

**What must not change:** the surrounding claim, any measurement, and any number.
You are renaming a citation, not editing evidence. If a rewrite tempts you to
adjust the sentence's claim, stop — that is a content change and belongs in its
own commit with its own justification.

**The four cross-line sites need care**, because they wrap mid-citation and a
naive single-line edit leaves a fragment behind:

| Site | Current text |
|---|---|
| `src/rubrica/brief.py:45` | `issue` / newline+2 spaces / `#6` |
| `src/rubrica/refs.py:3934` | `issue` / newline+4 spaces / `#19` |
| `src/rubrica/rounds.py:939` | `issue` / newline+4 spaces / `17` |
| `src/rubrica/utilisation.py:157` | `Issue` / newline+4 spaces / `#6` |

Rewrite each as a whole sentence and re-wrap the comment to 100 columns
afterwards.

---

### Task 3: Rewrite the citations in `src/` and `scripts/`

30 hits across 11 files. Do this tree first: it is the smallest, it contains all
four cross-line sites, and one of its files ships inside the wheel.

**Files:**

| Modify | Hits | Issues cited |
|---|---|---|
| `scripts/dispatch-stage.sh` | 4 | #12, #18 |
| `scripts/stage-write-scope.py` | 1 | #12 |
| `src/rubrica/brief.py` | 3 | #6, #17 |
| `src/rubrica/digest.py` | 1 | #4 |
| `src/rubrica/intake.py` | 1 | #4 |
| `src/rubrica/refs.py` | 5 | #6, #19, #37 |
| `src/rubrica/rounds.py` | 2 | #17 |
| `src/rubrica/schema/inputs-seen-0.1.json` | 1 | #6 |
| `src/rubrica/summary.py` | 6 | #6, #37 |
| `src/rubrica/summary_html.py` | 2 | #37 |
| `src/rubrica/utilisation.py` | 4 | #6 |

**Interfaces:**
- Consumes: the thirteen finding names and anchors fixed in Task 2's table (the last two added by Task 2b).
- Produces: nothing other tasks depend on. Tasks 4 and 5 are independent of this
  one and may be done in any order relative to it.

- [ ] **Step 1: List the exact sites**

Run:

```bash
python3 - <<'EOF'
import re, subprocess, sys
TREES = ["src", "scripts"]
# Two patterns, because one was not enough and the second was learned the hard
# way. NAMED catches "issue 17", "Issue #6", "PR #12", "(#33)". BARE catches a
# lone "#19" -- the form that made the second baseline undercount by ten, and
# hid a fourteenth cited issue entirely.
NAMED = re.compile(r"(?i)\bissues?\s+#?(\d+)\b|\bPR\s+#(\d+)\b|\(#(\d+)\)")
BARE  = re.compile(r"(?<![0-9A-Fa-f#])#(\d{1,3})(?![0-9A-Fa-f])")
# Three verified false-positive families, each eyeballed against the tree: the
# `notes#2.md` filename example, CSS colours like `#000`, and "Success criterion
# #1". None is a tracker citation. Narrow this list only with evidence.
def is_false(txt, m):
    line = txt[txt.rfind("\n", 0, m.start()) + 1 : txt.find("\n", m.end())]
    return bool("notes#" in line or "#2.md" in line
                or re.search(r"(?:color|fill|background|stroke)\s*:", line)
                or re.search(r"criterion\s+#", line))
files = [f for f in subprocess.run(["git", "ls-files", *TREES],
         capture_output=True, text=True).stdout.split()
         if not f.startswith("docs/superpowers/")]
total = 0
for f in files:
    try: txt = open(f, encoding="utf-8").read()
    except Exception: continue
    covered = set()
    for m in NAMED.finditer(txt):
        covered.update(range(m.start(), m.end()))
        print(f"{f}:{txt[:m.start()].count(chr(10)) + 1}: {m.group(0)!r}"); total += 1
    for m in BARE.finditer(txt):
        if m.start() in covered or is_false(txt, m): continue
        print(f"{f}:{txt[:m.start()].count(chr(10)) + 1}: {m.group(0)!r} (bare)"); total += 1
print("total:", total)
EOF
```

Expected: 30 lines. Keep this output — it is your worklist and your checklist.

- [ ] **Step 2: Rewrite `src/rubrica/schema/inputs-seen-0.1.json` first, and carefully**

This one ships in the wheel (`[tool.setuptools.package-data]` includes
`schema/*.json`), so its rewrite reaches installed copies. It is a JSON
`description` string: no Markdown link, no newline, and the JSON must stay valid.

Run: `python3 -c "import json;print(json.load(open('src/rubrica/schema/inputs-seen-0.1.json'))['description'][:200])"`

Rewrite the sentence beginning `Issue #6 measured` to name the finding and cite
the path in prose. Then verify:

Run: `python3 -c "import json;json.load(open('src/rubrica/schema/inputs-seen-0.1.json'));print('valid')"`
Expected: `valid`

- [ ] **Step 3: Rewrite the four cross-line sites**

`src/rubrica/brief.py:40`, `src/rubrica/refs.py:3890`, `src/rubrica/rounds.py:939`,
`src/rubrica/utilisation.py:157`. Read ±6 lines around each, rewrite the whole
sentence, re-wrap to 100 columns.

Run after each: `uv run ruff format --check <file>`

- [ ] **Step 4: Rewrite the remaining sites in this tree**

Work file by file from Step 1's list. On first mention in a file use
`the <name> (docs/design/findings.md)`; on later mentions in the same file use
just `the <name>`.

- [ ] **Step 5: Verify this tree is clean**

Run:

```bash
python3 - <<'EOF'
import re, subprocess, sys
TREES = ["src", "scripts"]
# Two patterns, because one was not enough and the second was learned the hard
# way. NAMED catches "issue 17", "Issue #6", "PR #12", "(#33)". BARE catches a
# lone "#19" -- the form that made the second baseline undercount by ten, and
# hid a fourteenth cited issue entirely.
NAMED = re.compile(r"(?i)\bissues?\s+#?(\d+)\b|\bPR\s+#(\d+)\b|\(#(\d+)\)")
BARE  = re.compile(r"(?<![0-9A-Fa-f#])#(\d{1,3})(?![0-9A-Fa-f])")
# Three verified false-positive families, each eyeballed against the tree: the
# `notes#2.md` filename example, CSS colours like `#000`, and "Success criterion
# #1". None is a tracker citation. Narrow this list only with evidence.
def is_false(txt, m):
    line = txt[txt.rfind("\n", 0, m.start()) + 1 : txt.find("\n", m.end())]
    return bool("notes#" in line or "#2.md" in line
                or re.search(r"(?:color|fill|background|stroke)\s*:", line)
                or re.search(r"criterion\s+#", line))
files = [f for f in subprocess.run(["git", "ls-files", *TREES],
         capture_output=True, text=True).stdout.split()
         if not f.startswith("docs/superpowers/")]
total = 0
for f in files:
    try: txt = open(f, encoding="utf-8").read()
    except Exception: continue
    covered = set()
    for m in NAMED.finditer(txt):
        covered.update(range(m.start(), m.end()))
        print(f"{f}:{txt[:m.start()].count(chr(10)) + 1}: {m.group(0)!r}"); total += 1
    for m in BARE.finditer(txt):
        if m.start() in covered or is_false(txt, m): continue
        print(f"{f}:{txt[:m.start()].count(chr(10)) + 1}: {m.group(0)!r} (bare)"); total += 1
print("total:", total)
EOF
```

Expected: `remaining: 0`

- [ ] **Step 6: Run the three gates**

Run: `make test && make check && uv run rubrica check-skills`
Expected: all green. **If a test fails, stop and report it** — the spec's
measurement says no test asserts on citation text, so a failure means that
measurement was wrong and the remaining rewrites need per-site review rather than
a naming table.

- [ ] **Step 7: Commit**

```bash
git add src scripts
git commit -S -s -m "$(cat <<'MSG'
docs(src): name the finding each comment cites, not the tracker issue

23 citations across src/ and scripts/. Each now names its finding and points at
docs/design/findings.md, where the measurement lives, instead of a bare `#N` that
would resolve to an unrelated issue once this repo is public.

Four of these wrapped across a line break and are invisible to a line-scoped
grep -- brief.py, refs.py, rounds.py, utilisation.py -- which is how the true
count came to be 89 rather than the 85 a line-based search reports.

inputs-seen-0.1.json is included and ships in the wheel, so its rewrite reaches
installed copies. No measurement, number or claim was altered: this renames
citations, it does not edit evidence.
MSG
)"
```

---

### Task 4: Rewrite the citations in `docs/`

24 hits across 4 files. This tree uses real anchor links, and it holds the only
heading citation in the repository.

**Files:**

| Modify | Hits | Issues cited |
|---|---|---|
| `docs/design/limitations.md` | 19 | #3, #4, #6, #8, #17, #18, #36, #37 |
| `docs/guides/invoking-rubrica.md` | 2 | #18 |
| `docs/reference/artifacts.md` | 2 | #6 |
| `docs/reference/cli.md` | 1 | #6 |

**Interfaces:**
- Consumes: Task 2's headings and anchors.
- Produces: nothing other tasks depend on.

- [ ] **Step 1: List the exact sites**

Run:

```bash
python3 - <<'EOF'
import re, subprocess, sys
TREES = ["docs"]
# Two patterns, because one was not enough and the second was learned the hard
# way. NAMED catches "issue 17", "Issue #6", "PR #12", "(#33)". BARE catches a
# lone "#19" -- the form that made the second baseline undercount by ten, and
# hid a fourteenth cited issue entirely.
NAMED = re.compile(r"(?i)\bissues?\s+#?(\d+)\b|\bPR\s+#(\d+)\b|\(#(\d+)\)")
BARE  = re.compile(r"(?<![0-9A-Fa-f#])#(\d{1,3})(?![0-9A-Fa-f])")
# Three verified false-positive families, each eyeballed against the tree: the
# `notes#2.md` filename example, CSS colours like `#000`, and "Success criterion
# #1". None is a tracker citation. Narrow this list only with evidence.
def is_false(txt, m):
    line = txt[txt.rfind("\n", 0, m.start()) + 1 : txt.find("\n", m.end())]
    return bool("notes#" in line or "#2.md" in line
                or re.search(r"(?:color|fill|background|stroke)\s*:", line)
                or re.search(r"criterion\s+#", line))
files = [f for f in subprocess.run(["git", "ls-files", *TREES],
         capture_output=True, text=True).stdout.split()
         if not f.startswith("docs/superpowers/")]
total = 0
for f in files:
    try: txt = open(f, encoding="utf-8").read()
    except Exception: continue
    covered = set()
    for m in NAMED.finditer(txt):
        covered.update(range(m.start(), m.end()))
        print(f"{f}:{txt[:m.start()].count(chr(10)) + 1}: {m.group(0)!r}"); total += 1
    for m in BARE.finditer(txt):
        if m.start() in covered or is_false(txt, m): continue
        print(f"{f}:{txt[:m.start()].count(chr(10)) + 1}: {m.group(0)!r} (bare)"); total += 1
print("total:", total)
EOF
```

Expected: 24 lines.

- [ ] **Step 2: Rewrite the heading at `docs/design/limitations.md:1021`**

Run: `sed -n '1019,1025p' docs/design/limitations.md`

`### Issue #3 was closed on arithmetic, …` → `### The untriageable catalogue was closed on arithmetic, …`

- [ ] **Step 3: Find and fix anything that referenced the old heading**

Run: `git grep -n 'closed on arithmetic' -- . ':!docs/superpowers'`

Any table of contents entry, anchor link or cross-reference must move to the new
text. `docs/superpowers/` hits are records — leave them.

- [ ] **Step 4: Rewrite the remaining 17 sites with anchor links**

Relative paths: from `docs/design/limitations.md` use `findings.md#...`; from
`docs/guides/` and `docs/reference/` use `../design/findings.md#...`.

- [ ] **Step 5: Verify every new link resolves**

Run:

```bash
python3 - <<'PY'
import re, pathlib
root = pathlib.Path("docs")
slugs = set()
for line in (root / "design/findings.md").read_text().splitlines():
    if line.startswith("## "):
        s = line[3:].strip().lower()
        slugs.add("#" + re.sub(r"[^a-z0-9 -]", "", s).replace(" ", "-"))
bad = 0
for f in root.rglob("*.md"):
    if "superpowers" in f.parts: continue
    for m in re.finditer(r"\]\(([^)]*findings\.md)(#[^)]*)?\)", f.read_text()):
        target = (f.parent / m.group(1)).resolve()
        if not target.is_file():
            print("BAD PATH", f, m.group(0)); bad += 1
        elif m.group(2) and m.group(2) not in slugs:
            print("BAD ANCHOR", f, m.group(2)); bad += 1
print("broken:", bad)
PY
```

Expected: `broken: 0`. A bad anchor here is a link to nothing — the same class of
defect this whole workstream exists to remove, so do not proceed with any.

- [ ] **Step 6: Confirm this tree is clean and the gates are green**

Run: re-run Step 1's script (expect 0 lines), then
`make test && make check && uv run rubrica check-skills`
Expected: all green. `test_docs_accuracy.py` is the one most likely to react
here, since all four files are in `_user_facing()`.

- [ ] **Step 7: Commit**

```bash
git add docs
git commit -S -s -m "$(cat <<'MSG'
docs(design,reference,guides): link citations to the finding, not the tracker

18 citations across four documents, each now naming its finding and linking the
anchor in docs/design/findings.md that carries the measurement. Every link was
checked to resolve to an existing file and an existing heading.

Includes the repository's only heading citation, limitations.md's "Issue #3 was
closed on arithmetic", which becomes "The untriageable catalogue was closed on
arithmetic"; cross-references to the old heading text were followed and fixed.

docs/superpowers/ is untouched. It is recorded history, and a bare `#N` there is
a correct record of what was cited on its own date.
MSG
)"
```

---

### Task 5: Rewrite the citations in `tests/`

73 hits across 25 files — the largest tree, and the lowest-risk: every hit is a
docstring or a comment. **The spec measured that no test asserts on citation
text.** That measurement is the reason this task is safe; if it turns out wrong,
that is a finding, not something to edit through.

**Files:**

| Modify | Hits | Issues | | Modify | Hits | Issues |
|---|---|---|---|---|---|---|
| `tests/builders.py` | 2 | #6 | | `tests/unit/test_review.py` | 1 | #37 |
| `tests/toy.py` | 3 | #6, #37 | | `tests/unit/test_rounds.py` | 1 | #17 |
| `tests/unit/test_brief.py` | 5 | #6, #17 | | `tests/unit/test_schemas_instance.py` | 3 | #6, #37 |
| `tests/unit/test_digest.py` | 1 | #4 | | `tests/unit/test_skills_challenge.py` | 4 | #37 |
| `tests/unit/test_dispatch_harness.py` | 5 | #15, #18 | | `tests/unit/test_skills_output_dirs.py` | 3 | #5 |
| `tests/unit/test_intake.py` | 1 | #4 | | `tests/unit/test_skills_propose.py` | 1 | #37 |
| `tests/unit/test_reconcile_seal.py` | 2 | #17 | | `tests/unit/test_skills_reconcile_family.py` | 6 | #6, #36 |
| `tests/unit/test_refs_input_dispositions.py` | 1 | #6 | | `tests/unit/test_skills_triage_family.py` | 3 | #1, #3 |
| `tests/unit/test_refs_instance.py` | 2 | #37 | | `tests/unit/test_slices.py` | 2 | #3, #8 |
| `tests/unit/test_refs_planning.py` | 4 | #6, #17 | | `tests/unit/test_stage_write_scope.py` | 1 | #15 |
| `tests/unit/test_summary.py` | 11 | #6, #37 | | `tests/unit/test_toy_split.py` | 2 | #6 |
| `tests/unit/test_utilisation.py` | 2 | #6 | | `tests/unit/test_validate.py` | 1 | #6 |
| `tests/unit/test_validate_registry_triage.py` | 1 | #6 | | | | |

**Interfaces:**
- Consumes: Task 2's eleven finding names.
- Produces: nothing. Task 6 depends on Tasks 3, 4 **and** 5 all being done.

- [ ] **Step 1: Confirm the safety measurement before editing anything**

Run:

```bash
git grep -nE '(assert|==|in )[^\n]*[Ii]ssue #?[0-9]+' -- tests/ | grep -v '"""' | head -20
```

Expected: no line where a citation sits inside an assertion's compared value.
Every hit should be a docstring or a `#` comment. **If a real assertion compares
citation text, stop and report** — the plan's premise is wrong and the rewrite
needs per-site review.

- [ ] **Step 2: List the exact sites**

Run:

```bash
python3 - <<'EOF'
import re, subprocess, sys
TREES = ["tests"]
# Two patterns, because one was not enough and the second was learned the hard
# way. NAMED catches "issue 17", "Issue #6", "PR #12", "(#33)". BARE catches a
# lone "#19" -- the form that made the second baseline undercount by ten, and
# hid a fourteenth cited issue entirely.
NAMED = re.compile(r"(?i)\bissues?\s+#?(\d+)\b|\bPR\s+#(\d+)\b|\(#(\d+)\)")
BARE  = re.compile(r"(?<![0-9A-Fa-f#])#(\d{1,3})(?![0-9A-Fa-f])")
# Three verified false-positive families, each eyeballed against the tree: the
# `notes#2.md` filename example, CSS colours like `#000`, and "Success criterion
# #1". None is a tracker citation. Narrow this list only with evidence.
def is_false(txt, m):
    line = txt[txt.rfind("\n", 0, m.start()) + 1 : txt.find("\n", m.end())]
    return bool("notes#" in line or "#2.md" in line
                or re.search(r"(?:color|fill|background|stroke)\s*:", line)
                or re.search(r"criterion\s+#", line))
files = [f for f in subprocess.run(["git", "ls-files", *TREES],
         capture_output=True, text=True).stdout.split()
         if not f.startswith("docs/superpowers/")]
total = 0
for f in files:
    try: txt = open(f, encoding="utf-8").read()
    except Exception: continue
    covered = set()
    for m in NAMED.finditer(txt):
        covered.update(range(m.start(), m.end()))
        print(f"{f}:{txt[:m.start()].count(chr(10)) + 1}: {m.group(0)!r}"); total += 1
    for m in BARE.finditer(txt):
        if m.start() in covered or is_false(txt, m): continue
        print(f"{f}:{txt[:m.start()].count(chr(10)) + 1}: {m.group(0)!r} (bare)"); total += 1
print("total:", total)
EOF
```

Expected: 73 lines.

- [ ] **Step 3: Rewrite file by file**

Same rules as Task 3 — code form, not Markdown links. Work in the order of the
table above; do the six-hit `test_summary.py` and five-hit `test_brief.py` /
`test_dispatch_harness.py` when you are warmed up rather than first.

Watch for the attributive shape, which is common in this tree:
`the three sites issue #6 added` → `the three sites the read-coverage variance added`.

- [ ] **Step 4: Verify this tree is clean**

Run: re-run Step 2's script.
Expected: 0 lines.

- [ ] **Step 5: Verify the whole tree is now clean**

Run:

```bash
python3 - <<'PY'
import re, subprocess
PAT = re.compile(r"(?i)\bissues?\s+#?\d+\b|\bPR\s+#\d+\b|\(#\d+\)")
files = [f for f in subprocess.run(["git","ls-files"],capture_output=True,text=True).stdout.split()
         if not f.startswith("docs/superpowers/")]
n = 0
for f in files:
    try: txt = open(f, encoding="utf-8").read()
    except Exception: continue
    for m in PAT.finditer(txt):
        print(f"{f}:{txt[:m.start()].count(chr(10))+1}: {m.group(0)!r}"); n += 1
print("remaining across the whole tree:", n)
PY
```

Expected: `remaining across the whole tree: 0`. This is the precondition for Task
6 — the guard cannot be committed green until this prints 0.

- [ ] **Step 6: Run the three gates**

Run: `make test && make check && uv run rubrica check-skills`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add tests
git commit -S -s -m "$(cat <<'MSG'
test: name the finding each docstring cites, not the tracker issue

48 citations across 21 files, every one a docstring or a comment -- verified
before editing that none sits inside an assertion's compared value, which is what
made this the low-risk tree despite being the largest.

With this the tree carries no tracker citation outside docs/superpowers/, which is
the precondition for the guard predicate that follows.
MSG
)"
```

---

### Task 6: Add the guard predicate

**Files:**
- Modify: `tests/unit/test_docs_accuracy.py` — one new scan-set helper and one new
  policy predicate, in the existing "Policy predicates" block.

**Interfaces:**
- Consumes: a tree with zero tracker citations outside `docs/superpowers/` (Tasks
  3, 4 and 5 all complete).
- Produces: `_code_files() -> list[Path]` and
  `_TRACKER_CITATION: re.Pattern`, both module-private.

- [ ] **Step 1: Read the existing policy block to match its idiom**

Run: `sed -n '131,215p' tests/unit/test_docs_accuracy.py`

Note three things you must copy: the `_user_facing()` / `_doc_id()` helpers, the
`@pytest.mark.parametrize` shape with `ids=_doc_id`, and the comment convention —
every predicate records the measurement that motivated it, because a future author
will feel it as friction and deserves the reason.

- [ ] **Step 2: Write the failing test**

Add to the policy-predicate block. The regex is **multiline by construction** and
the comment says why, because that is the part a later reader would otherwise
"simplify".

```python
# Citations of the internal tracker. Issue numbers do not survive the move to
# github.com/skillberry-ai/rubrica: the public repo starts at #1, so a bare `#N`
# resolves to a different, unrelated issue there. That is worse than a dead link
# -- it is a live link to the wrong thing -- so every citation was rewritten to
# name its finding and point at docs/design/findings.md.
#
# `\s+` rather than a space, and no line anchors, because four citations wrapped
# across a line break: `issue\n  #6` in brief.py, `issue\n    #19` in refs.py,
# `issue\n    17` in rounds.py and `Issue\n    #6` in utilisation.py. A
# line-scoped search reports fewer hits than exist, so a line-based guard
# would have gone green over the four it could not see -- a passing gate over the
# exact defect it exists for.
#
# `PR #N` and `(#N)` are included although the tree carried none of either when
# this was written: both are pointer forms a future comment would reach for, and
# the point of a guard is the citation nobody has written yet.
_TRACKER_CITATION = re.compile(
    r"\bissues?\s+#?\d+\b|\bPR\s+#\d+\b|\(#\d+\)",
    re.IGNORECASE,
)

# The bare form, and it is not optional. A pattern requiring the word "issue", a
# "PR" prefix or parentheses undercounted this repository by ten -- a lone `#19`
# in refs.py, three `#3` and one `#4` in limitations.md, `#15` twice and `#12`
# once in test_dispatch_harness.py, `#36` in test_skills_reconcile_family.py, and
# a `#20` that was the only citation of a fourteenth issue nobody had noticed was
# referenced at all. A guard without this half would have gone green over all of
# them.
#
# 1-3 digits with hex-digit context excluded on both sides, because CSS colours
# here are pure decimal (`#121514`, `#000`) and would otherwise match.
_TRACKER_CITATION_BARE = re.compile(r"(?<![0-9A-Fa-f#])#(\d{1,3})(?![0-9A-Fa-f])")

# Three false-positive families, each eyeballed against the tree rather than
# guessed: `notes#2.md` is a filename this repo uses as a fixture example, `#000`
# and friends are CSS colours in the rendered-brief and diagram code, and
# "Success criterion #1" in test_toy_end_to_end.py is a label, not a reference.
# Narrow this list only with evidence -- each entry stands for real content that
# would otherwise fail the gate.
_CITATION_FALSE_POSITIVES = ("notes#", "#2.md")


def _bare_citations(text: str) -> list[str]:
    """Bare `#N` hits, minus the three verified false-positive families."""
    out = []
    for m in _TRACKER_CITATION_BARE.finditer(text):
        line = text[text.rfind("\n", 0, m.start()) + 1 : text.find("\n", m.end())]
        if any(tok in line for tok in _CITATION_FALSE_POSITIVES):
            continue
        if re.search(r"(?:color|fill|background|stroke)\s*:", line):
            continue
        if re.search(r"criterion\s+#", line):
            continue
        out.append(m.group(0))
    return out


def _code_files() -> list[Path]:
    """Tracked source, test and script files the citation guard scans.

    The predicates above run over documentation only. This set exists because 66
    of the 118 tracker citations lived in code comments and docstrings -- 79% of
    them -- so a docs-only guard would have reported a clean tree over three
    quarters of the defect.

    Fixtures and vendored trees are excluded for the same reason
    docs/superpowers/ is: tests/fixtures/reservation-trajectories/ is committed
    capture output, a record rather than prose, and a guard that fired on a
    record would demand an edit the project's own rules forbid. Measured: the
    excluded paths carry no citation, so the exclusion costs no coverage today
    and prevents an unfixable failure later.
    """
    keep = {".py", ".sh", ".json", ".md"}
    skip = ("fixtures", "node_modules", "__pycache__")
    out: list[Path] = []
    for top in ("src", "tests", "scripts"):
        for path in sorted((REPO_ROOT / top).rglob("*")):
            if not path.is_file() or path.suffix not in keep:
                continue
            if any(part in skip for part in path.relative_to(REPO_ROOT).parts):
                continue
            out.append(path)
    return out


@pytest.mark.parametrize("doc", _user_facing(), ids=_doc_id)
def test_no_user_facing_document_cites_the_internal_tracker(doc):
    """A bare `#N` resolves to an unrelated issue in the public repo.

    Findings are named and anchored at docs/design/findings.md instead.
    """
    text = _read(doc)
    hits = _TRACKER_CITATION.findall(text) + _bare_citations(text)
    assert not hits, (
        f"{_doc_id(doc)} cites the internal tracker: {hits}. "
        "Name the finding and link docs/design/findings.md instead."
    )


@pytest.mark.parametrize("src", _code_files(), ids=_doc_id)
def test_no_source_file_cites_the_internal_tracker(src):
    """The same rule for code. 93 of the 118 citations are here."""
    text = _read(src)
    hits = _TRACKER_CITATION.findall(text) + _bare_citations(text)
    assert not hits, (
        f"{_doc_id(src)} cites the internal tracker: {hits}. "
        "Name the finding and cite docs/design/findings.md instead."
    )
```

- [ ] **Step 3: Measure the red direction — the step that makes this a guard**

`CLAUDE.md`: *"Measure every predicate in both directions before committing it. A
predicate nobody has watched fail is not yet a guard."*

Reintroduce a citation in each scan set, confirm each predicate fails, then revert:

```bash
printf '\n<!-- issue #6 -->\n' >> docs/design/findings.md
uv run pytest tests/unit/test_docs_accuracy.py -k tracker -q 2>&1 | tail -5
git checkout docs/design/findings.md

printf '\n# issue #6\n' >> src/rubrica/utilisation.py
uv run pytest tests/unit/test_docs_accuracy.py -k tracker -q 2>&1 | tail -5
git checkout src/rubrica/utilisation.py
```

Expected: the first run fails the `_user_facing` predicate, the second fails the
`_code_files` one. **Both must be observed to fail.** If either stays green, the
scan set does not reach that file and the predicate is not yet a guard.

- [ ] **Step 4: Measure the cross-line direction specifically**

The whole reason the regex has no line anchors. Reintroduce a *wrapped* citation:

```bash
printf '\n# see issue\n#   6\n' >> src/rubrica/refs.py
uv run pytest tests/unit/test_docs_accuracy.py -k tracker -q 2>&1 | tail -3
git checkout src/rubrica/refs.py
```

Expected: FAIL. If it passes, the regex has lost its multiline behaviour and the
four sites Task 3 fixed could silently come back.

- [ ] **Step 4b: Measure the bare form, in both directions**

The half that was missing when this plan was first written. Reintroduce a bare
citation and a false positive, and confirm the guard tells them apart:

```bash
printf '\n# see #20 for the batch-id collision\n' >> src/rubrica/rounds.py
uv run pytest tests/unit/test_docs_accuracy.py -k tracker -q 2>&1 | tail -3
git checkout src/rubrica/rounds.py

printf '\n# a piece like notes#2.md is a filename, not a citation\n' >> src/rubrica/rounds.py
uv run pytest tests/unit/test_docs_accuracy.py -k tracker -q 2>&1 | tail -3
git checkout src/rubrica/rounds.py
```

Expected: the first FAILS, the second PASSES. If the first passes, the bare half
is inert and nine real citations could return unseen. If the second fails, the
false-positive list is too narrow and the gate will block correct content.

- [ ] **Step 5: Measure the green direction — no false positives on a reword**

Reword a rewritten citation meaning-preservingly and confirm the predicate stays
green. The mirror failure is real in this repo: a phrase pin once broke on an
innocuous reformat.

```bash
uv run pytest tests/unit/test_docs_accuracy.py -q
```

Expected: PASS. Also confirm the guard does not fire on incidental `#`:

```bash
git grep -nE '#[0-9]' -- src tests scripts ':!*fixtures*' | grep -vE '#!/|#[0-9a-fA-F]{3,6}\b' | head
```

Anything listed that is not a tracker citation is a false-positive risk — narrow
the regex rather than editing the file.

- [ ] **Step 6: Run the three gates**

Run: `make test && make check && uv run rubrica check-skills`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add tests/unit/test_docs_accuracy.py
git commit -S -s -m "$(cat <<'MSG'
test(docs): guard against citing the internal tracker, in docs and in code

Two predicates, because a docs-only guard would have covered a quarter of the
problem: 93 of the 118 citations live in code comments and docstrings.
The second scan set reaches src/, tests/ and scripts/, excluding fixtures and
vendored trees -- measured to carry no citation, and records that a guard must
never demand an edit to.

The regex spans newlines deliberately. Four citations wrapped across a line
break, so a line-scoped search under-reports; a line-based guard
would have passed over the exact four it could not see. Measured in three
directions before committing: fails on a reintroduced citation in each scan set,
fails on a wrapped one, and stays green on a meaning-preserving reword.

PR #N and (#N) are covered although the tree carried neither -- the point of a
guard is the citation nobody has written yet.
MSG
)"
```

---

# Phase 2 — The preparation commit (Workstream A)

Mirrors `$HARNESS`'s `fb7116a`. Split into two tasks on a reviewer boundary: the
DCO machinery has tests and behaviour; the policy files are static text. A
reviewer could reasonably accept one and reject the other.

### Task 7: DCO enforcement — script, test, and CI job

**Files:**
- Create: `scripts/check-dco.sh` (copied from `$HARNESS/scripts/check-dco.sh`)
- Create: `tests/unit/test_check_dco.py`
- Modify: `.github/workflows/ci.yml` (add a `dco` job)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `scripts/check-dco.sh`, invoked as
  `scripts/check-dco.sh <base-ref> <head-ref>`. Exit codes: **`0`** clean,
  **`1`** one or more commits lack a matching sign-off *or* a ref cannot be
  resolved, **`2`** wrong argument count. These three match rubrica's own
  exit-code contract, which is why the script transplants without adaptation.

- [ ] **Step 1: Copy the script and confirm it is self-contained**

```bash
cp /home/bnayahu/work/kaegis/simulation-harness/scripts/check-dco.sh scripts/check-dco.sh
chmod +x scripts/check-dco.sh
grep -nE 'simulation|harness|logs/|config/' scripts/check-dco.sh
```

Expected: the `grep` prints nothing. The script reads only `git` and its two
arguments — verified before transplant, and this re-verifies it. If it prints
anything, adapt that line and note it in the commit message.

- [ ] **Step 2: Exercise it by hand against this branch, to see it pass**

```bash
scripts/check-dco.sh main HEAD; echo "exit=$?"
```

Expected: `DCO ok — N commit(s) signed off.` and `exit=0`. Every commit on this
branch was made with `-s`, so this is the positive case for free.

- [ ] **Step 3: Write the failing test**

Create `tests/unit/test_check_dco.py`. Nine cases, driving the script as a
subprocess against throwaway repositories — the idiom
`tests/unit/test_dispatch_harness.py` already uses.

```python
"""Tests for scripts/check-dco.sh.

The script is shell, so it is driven as a subprocess against throwaway git
repositories rather than imported. That is the idiom test_dispatch_harness.py
already uses for scripts/dispatch-stage.sh, and it is deliberate: the harness
this was transplanted from keeps its script tests in shell behind a separate
`make test-scripts` target, which here would be a fourth gate on a project whose
documentation names exactly three. A gate nobody is obliged to run stops running
silently.

Commits are made with `-c commit.gpgsign=false` so the suite never depends on a
developer's signing key or an unlocked agent -- the script checks the DCO
trailer, which is `-s`, and has nothing to say about `-S`.
"""

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-dco.sh"

AUTHOR = "Test Author"
EMAIL = "test.author@example.com"


def _git(repo: Path, *args: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-C", str(repo), *args],
        capture_output=True, text=True, check=kw.pop("check", True), **kw,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo with one signed-off commit on `main`."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.name", AUTHOR)
    _git(r, "config", "user.email", EMAIL)
    (r / "README.md").write_text("base\n")
    _git(r, "add", "README.md")
    _git(r, "commit", "-q", "-m", f"chore: base\n\nSigned-off-by: {AUTHOR} <{EMAIL}>")
    return r


def _commit(repo: Path, subject: str, *, signoff: str | None = None, author: str | None = None):
    """Add a commit. `signoff` is the full trailer value, or None for none."""
    path = repo / f"f{subject.replace(' ', '_').replace(':', '')}.txt"
    path.write_text(subject)
    _git(repo, "add", str(path.name))
    msg = subject if signoff is None else f"{subject}\n\nSigned-off-by: {signoff}"
    args = ["commit", "-q", "-m", msg]
    if author:
        args += [f"--author={author}"]
    _git(repo, *args)


def _check(repo: Path, base: str = "main", head: str = "HEAD"):
    return subprocess.run(
        [str(SCRIPT), base, head], cwd=repo, capture_output=True, text=True
    )


def test_a_signed_off_commit_passes(repo):
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "feat: one", signoff=f"{AUTHOR} <{EMAIL}>")
    result = _check(repo)
    assert result.returncode == 0, result.stderr


def test_a_commit_with_no_trailer_fails_and_names_it(repo):
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "feat: unsigned", signoff=None)
    result = _check(repo)
    assert result.returncode == 1
    assert "no Signed-off-by trailer" in result.stderr
    assert "feat: unsigned" in result.stderr


def test_a_trailer_naming_someone_else_fails(repo):
    """A sign-off naming a non-author certifies nothing about the author."""
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "feat: mismatched", signoff="Someone Else <someone@example.com>")
    result = _check(repo)
    assert result.returncode == 1
    assert "does not match the author" in result.stderr


def test_the_match_ignores_case_and_surrounding_whitespace(repo):
    """Contributors are not failed over capitalisation."""
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "feat: casing", signoff=f"  {AUTHOR.upper()}   <{EMAIL.upper()}>")
    result = _check(repo)
    assert result.returncode == 0, result.stderr


def test_a_merge_commit_is_exempt(repo):
    """A merge commit contributes no authored patch, so it certifies nothing."""
    _git(repo, "checkout", "-q", "-b", "side")
    _commit(repo, "feat: on side", signoff=f"{AUTHOR} <{EMAIL}>")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "feat: on feature", signoff=f"{AUTHOR} <{EMAIL}>")
    _git(repo, "merge", "--no-ff", "-q", "--no-gpg-sign", "-m", "Merge side", "side")
    result = _check(repo)
    assert result.returncode == 0, result.stderr


def test_a_bot_commit_is_exempt_and_reported_as_such(repo):
    """A bot cannot make the certification the DCO describes."""
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(
        repo, "chore(deps): bump", signoff=None,
        author="dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
    )
    result = _check(repo)
    assert result.returncode == 0, result.stderr
    assert "exempt" in result.stdout


def test_commits_already_on_the_base_branch_are_not_checked(repo):
    """Merge-base scoping: an advanced base must not drag its commits in."""
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "feat: mine", signoff=f"{AUTHOR} <{EMAIL}>")
    _git(repo, "checkout", "-q", "main")
    _commit(repo, "feat: theirs unsigned", signoff=None)
    _git(repo, "checkout", "-q", "feature")
    result = _check(repo)
    assert result.returncode == 0, (
        "an unsigned commit on the advanced base branch was wrongly attributed "
        f"to this branch: {result.stderr}"
    )


def test_wrong_argument_count_is_a_usage_error(repo):
    result = subprocess.run([str(SCRIPT), "main"], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 2
    assert "Usage:" in result.stderr


def test_an_unresolvable_base_ref_is_reported_not_ignored(repo):
    result = _check(repo, base="no/such/ref")
    assert result.returncode == 1
    assert "cannot resolve base ref" in result.stderr
    assert "fetch-depth" in result.stderr
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_check_dco.py -v`
Expected: 9 passed. If `test_a_merge_commit_is_exempt` fails on signing, confirm
`--no-gpg-sign` is on the `merge` call. If the bot test fails, check the email
ends exactly with `[bot]@users.noreply.github.com` — that is what the script matches.

- [ ] **Step 5: Add the `dco` job to `.github/workflows/ci.yml`**

Insert as the **first** job under `jobs:`, above `check:`.

```yaml
  dco:
    name: DCO
    runs-on: ubuntu-latest
    # Only a pull request has a base to diff against; a direct push to main has
    # no meaningful range to check. This is also why a branch ruleset requiring a
    # pull request is needed for this job to bind -- without one, a direct push
    # bypasses the check entirely rather than failing it.
    if: github.event_name == 'pull_request'
    steps:
      - name: Checkout
        uses: actions/checkout@v7
        with:
          # The check walks the PR's commits, so it needs their history, not just
          # the tip. Without this the merge-base lookup fails and the script
          # exits 1 with "cannot resolve base ref".
          fetch-depth: 0

      - name: Check DCO sign-off
        run: ./scripts/check-dco.sh "$BASE_SHA" "$HEAD_SHA"
        env:
          BASE_SHA: ${{ github.event.pull_request.base.sha }}
          HEAD_SHA: ${{ github.event.pull_request.head.sha }}
```

- [ ] **Step 6: Validate the workflow YAML parses**

Run: `python3 -c "import yaml,sys;d=yaml.safe_load(open('.github/workflows/ci.yml'));print(sorted(d['jobs']))"`
Expected: `['check', 'dco']`

If `yaml` is unavailable, run `uv run --with pyyaml python3 -c "..."` instead.

- [ ] **Step 7: Run the three gates**

Run: `make test && make check && uv run rubrica check-skills`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add scripts/check-dco.sh tests/unit/test_check_dco.py .github/workflows/ci.yml
git commit -S -s -m "$(cat <<'MSG'
ci: enforce the DCO sign-off CONTRIBUTING.md already requires

CONTRIBUTING.md has required `-S -s` all along and nothing checked it. The script
is transplanted from simulation-harness unchanged -- verified self-contained, and
its exit codes (0 clean, 1 findings, 2 usage) already match this project's own
contract, which is why no adaptation was needed.

Its test is a pytest module rather than the harness's shell suite. The harness
runs script tests behind a separate `make test-scripts` target; here that would be
a fourth gate on a project whose documentation names exactly three, and a gate
nobody is obliged to run stops running silently. Nine cases: signed, unsigned,
mismatched trailer, case and whitespace tolerance, merge exemption, bot exemption,
merge-base scoping, usage error, unresolvable ref.

The job is pull-request only, so a branch ruleset requiring a PR and the `DCO`
check is still needed on the public repo for it to bind -- a direct push bypasses
it rather than failing it. That is a repository setting, not something this commit
can carry.
MSG
)"
```

---

### Task 8: Policy files, `.github/` templates, and package metadata

**Files:**
- Create: `CODE_OF_CONDUCT.md`, `SECURITY.md`
- Create: `.github/PULL_REQUEST_TEMPLATE.md`,
  `.github/ISSUE_TEMPLATE/{bug_report.md,feature_request.md,config.yml}`
- Create: `.github/dependabot.yml`, `.github/workflows/codeql.yml`
- Modify: `pyproject.toml` (`authors`, new `[project.urls]`)
- Modify: `.github/workflows/ci.yml` (action bumps only — the `permissions:` block
  is Task 11, with the other hardening)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing other tasks consume. `SECURITY.md` is referenced by
  `CODE_OF_CONDUCT.md`'s reporting route.

- [ ] **Step 1: Copy the four transplantable files**

```bash
H=/home/bnayahu/work/kaegis/simulation-harness
mkdir -p .github/ISSUE_TEMPLATE
cp $H/CODE_OF_CONDUCT.md .
cp $H/SECURITY.md .
cp $H/.github/PULL_REQUEST_TEMPLATE.md .github/
cp $H/.github/ISSUE_TEMPLATE/config.yml .github/ISSUE_TEMPLATE/
cp $H/.github/ISSUE_TEMPLATE/feature_request.md .github/ISSUE_TEMPLATE/
cp $H/.github/ISSUE_TEMPLATE/bug_report.md .github/ISSUE_TEMPLATE/
cp $H/.github/dependabot.yml .github/
cp $H/.github/workflows/codeql.yml .github/workflows/
```

- [ ] **Step 2: Swap every repository-name reference**

```bash
grep -rn 'simulation-harness' CODE_OF_CONDUCT.md SECURITY.md .github/
```

Expected before: hits in `SECURITY.md:9`, `CODE_OF_CONDUCT.md:39`, and two in
`.github/ISSUE_TEMPLATE/bug_report.md`. Replace the URLs with
`skillberry-ai/rubrica`; the `bug_report.md` hits are handled in Step 5.

```bash
sed -i 's#skillberry-ai/simulation-harness#skillberry-ai/rubrica#g' CODE_OF_CONDUCT.md SECURITY.md
grep -rn 'simulation-harness' CODE_OF_CONDUCT.md SECURITY.md
```

Expected after: nothing. Neither file carries a personal address — both route to
GitHub private vulnerability reporting — so there is no contact to invent.

- [ ] **Step 3: Add the scope statement to `SECURITY.md` and drop the threat-model link**

Remove the cross-reference at `SECURITY.md:41` (`Before reporting, please read
[THREAT_MODEL.md]…`) — rubrica has none, per spec decision 5. In its place add:

```markdown
## Scope: the dispatch harness

Rubrica is a command-line tool, not a service, so most of its surface is the file
system of whoever runs it. One part is worth naming explicitly.

`scripts/dispatch-stage.sh` dispatches a model to run a pipeline stage. It passes
that model credentials, and it grants it `Write` access derived from the
dispatched stage's own `writes` contract — narrower than the run directory the
grant was first scoped to. Both of the wider scopings that preceded it were
observed being used to drop a scratch file where nothing reacted to it, which is
recorded in `docs/design/limitations.md`; both are now pinned by tests. `Read`
access is still the whole run directory.

**CodeQL does not analyse shell.** `dispatch-stage.sh` is a substantial shell
program, so a clean CodeQL run on this repository is not evidence about it. If you
are deciding what a green scanning badge covers here, it covers the Python.
```

**Accuracy matters in that middle paragraph.** The contract-derived grant is
current behaviour; the blanket and run-directory grants are history. Describing a
closed hole as open is the same class of error as the reverse.

- [ ] **Step 4: Adapt `.github/PULL_REQUEST_TEMPLATE.md` to rubrica's real gates**

The harness template claims `make check` is "lint + type-check + format". Rubrica's
`make check` is `ruff check` plus `ruff format --check` — there is no type-check —
and rubrica has a third gate the harness does not. Replace the Testing block:

```markdown
## Testing

<!-- How was this verified? -->

- [ ] `make check` passes (ruff lint + format check)
- [ ] `make test` passes
- [ ] `uv run rubrica check-skills` exits 0
- [ ] Added/updated tests for the change
```

In the Checklist block, change the DCO line to require both flags, since that is
what `CONTRIBUTING.md` promises:

```markdown
- [ ] Commits are signed off **and** signed (`git commit -S -s`)
```

- [ ] **Step 5: Rewrite `.github/ISSUE_TEMPLATE/bug_report.md` for a CLI**

The harness version asks for a running server, a POSTed spec, a transport, and
lines from `logs/<timestamp>_pid<PID>_simulation-harness.log`. None of that exists
here. Replace the body (keep the front matter, changing nothing but leaving
`labels: bug`):

```markdown
**Describe the bug**
A clear and concise description of what the bug is.

**To reproduce**
1. The `rubrica` subcommand you ran, with its flags
2. The stage and run directory it was pointed at, if relevant
3. What it printed

**Expected behavior**
What you expected to happen.

**Exit code and output**
Rubrica's exit codes are contractual: `0` clean, `1` findings (one per line on
stdout), `2` a usage error or an unreadable run. Please include the exit code —
`echo $?` — and the output verbatim.

```
<paste output here>
```

**Environment**
- OS:
- Python version (`uv run python --version`):
- rubrica version or commit:
- Installed how (`uv sync`, `pip install`, from a checkout):

**Additional context**
Anything else that helps diagnose the issue. If a run directory is involved,
please say which stage it had reached — but do not paste artifacts that contain
anything you would not publish.
```

- [ ] **Step 6: Drop the `docker` block from `.github/dependabot.yml`**

Run: `grep -n 'docker' .github/dependabot.yml`

Delete the whole `- package-ecosystem: docker` entry and its comment. Rubrica has
no Dockerfile, and Dependabot logs an error for an ecosystem with no manifest.

Keep the `github-actions` block's `ignore` rules and their comment verbatim —
that comment is the argument for floating major tags, and this plan explicitly
does not overturn it.

Run: `python3 -c "import yaml;d=yaml.safe_load(open('.github/dependabot.yml'));print([u['package-ecosystem'] for u in d['updates']])"`
Expected: `['pip', 'github-actions']`

- [ ] **Step 7: Restrict the CodeQL matrix to Python**

Run: `grep -n 'language:' .github/workflows/codeql.yml`

Change `language: [python, javascript-typescript]` to `language: [python]`, with
the reason recorded — it is not simply "no JavaScript":

```yaml
      matrix:
        # Python only. There is exactly one tracked .js file,
        # tests/fixtures/corpus-toy/node_modules/dep/index.js, and it is a
        # deliberate fixture: the survey walker needs a vendored tree to skip.
        # Analysing it would produce alerts against content written to be toy.
        language: [python]
```

Run: `python3 -c "import yaml;d=yaml.safe_load(open('.github/workflows/codeql.yml'));print(d['jobs']['analyze']['strategy']['matrix'])"`
Expected: `{'language': ['python']}`

- [ ] **Step 8: Update `pyproject.toml`**

Replace line 9 and add a URLs block after `classifiers`:

```toml
# IBM Corp. rather than an individual, matching NOTICE's `Copyright IBM Corp.
# 2026` and the sibling project. This is package-metadata hygiene, not privacy:
# every commit in this repository carries its author's name and address in git's
# own fields, so the personal identity is public either way.
authors = [{name = "IBM Corp."}]
```

```toml
[project.urls]
Homepage = "https://github.com/skillberry-ai/rubrica"
Repository = "https://github.com/skillberry-ai/rubrica"
Issues = "https://github.com/skillberry-ai/rubrica/issues"
Changelog = "https://github.com/skillberry-ai/rubrica/blob/main/CHANGELOG.md"
```

**Do not add a `License ::` classifier.** PEP 639's `license = "Apache-2.0"`
string is already present on line 7 and the two are mutually exclusive — the
build fails if both appear. Confirm:

Run: `grep -n 'License ::' pyproject.toml`
Expected: nothing.

Note the `Changelog` URL points at a file Task 10 creates. That is fine — it is
metadata, not a build input — but do not reorder the tasks such that a release is
cut before `CHANGELOG.md` exists.

- [ ] **Step 9: Verify the package still builds and the metadata is what you think**

```bash
uv build 2>&1 | tail -3
python3 -c "
import tarfile,glob
t=sorted(glob.glob('dist/rubrica-*.tar.gz'))[-1]
with tarfile.open(t) as f:
    n=[m for m in f.getnames() if m.endswith('PKG-INFO')][0]
    for line in f.extractfile(n).read().decode().splitlines():
        if line.startswith(('Author','License','Project-URL','Name','Version')): print(line)
"
rm -rf dist
```

Expected: `Author: IBM Corp.`, `License-Expression: Apache-2.0`, and four
`Project-URL:` lines. If `uv build` fails on the license/classifier conflict, you
added a `License ::` classifier — remove it.

- [ ] **Step 10: Bump the CI action pins**

```bash
sed -i 's#actions/checkout@v4#actions/checkout@v7#; s#astral-sh/setup-uv@v5#astral-sh/setup-uv@v7#' .github/workflows/ci.yml
grep -n 'uses:' .github/workflows/ci.yml
```

Expected: `actions/checkout@v7` in both jobs and `astral-sh/setup-uv@v7`.

- [ ] **Step 11: Run the three gates**

Run: `make test && make check && uv run rubrica check-skills`
Expected: all green. `make check` reads `README.md` and `CLAUDE.md`; neither is
edited in this task, so a failure here means a policy predicate is reacting to a
new root-level Markdown file — read the failure before changing anything, and if
`CODE_OF_CONDUCT.md` or `SECURITY.md` is being scanned, that is a real finding
worth reporting rather than silencing.

- [ ] **Step 12: Commit**

```bash
git add CODE_OF_CONDUCT.md SECURITY.md .github pyproject.toml
git commit -S -s -m "$(cat <<'MSG'
chore: prepare the repo for its public home

Mirrors simulation-harness's fb7116a, with the divergences its own caveat asks
for -- matching is worth wanting for what a contributor sees and a scanner
enforces, not for a choice whose cause does not apply here.

Transplanted: CODE_OF_CONDUCT.md (Contributor Covenant 2.1), SECURITY.md, the
.github/ templates, dependabot.yml and codeql.yml. Both policy files route
reporting to this repository's private advisories, so the transplant was a URL
swap with no contact to invent.

Adapted rather than copied:

- SECURITY.md gains a scope paragraph naming the dispatch harness's credential
  passing, its contract-derived Write grant, and that CodeQL does not read shell
  -- so a green scanning badge here covers the Python and not dispatch-stage.sh.
  No THREAT_MODEL.md: the harness has one because it is a server, and a CLI's
  dispatch surface fits in a paragraph.
- dependabot.yml drops the docker ecosystem; there is no Dockerfile.
- codeql.yml analyses Python only. The one tracked .js file is a fixture the
  survey walker needs a vendored tree to skip, and analysing it would raise
  alerts against content written to be toy.
- The PR template names rubrica's actual three gates. The harness template
  claims `make check` type-checks; here it is ruff only, and check-skills is a
  gate the harness does not have.
- bug_report.md asks for an exit code, because rubrica's are contractual.

pyproject.toml: authors becomes IBM Corp. to match NOTICE, and [project.urls]
points at the public repo. No License :: classifier -- PEP 639's license string
is already present and the two are mutually exclusive.

CI actions bumped to checkout@v7 and setup-uv@v7.
MSG
)"
```

---

# Phase 3 — The release process (Workstream C)

Modelled on the harness. Ordered so each task delivers a *tested* unit: the two
sourced libraries and their tests first, then the driver script and its tests,
then the workflows that are inert until a service is configured.

**Why these tests are pytest and not the harness's shell suites.** The harness
keeps 673 lines of shell tests behind `make test-scripts`. `CLAUDE.md` states that
`make test`, `make check` and `rubrica check-skills` **are** the three gates and
anything else means something broke. A fourth gate is one more command a
contributor and CI must remember, sitting outside the set the project documents as
complete — and it would stop running silently. The shell scripts are also invisible
to ruff, so their tests are the only gate they have. That is two reasons to put
them under the gate that already exists.

### Task 9: Transplant the release libraries with their tests

**Files:**
- Create: `scripts/lib/release-tag.sh`, `scripts/lib/release-notes.sh`
- Create: `tests/unit/test_release_notes.py`

**Interfaces:**
- Consumes: nothing.
- Produces, for Task 10's `release.sh` to source:
  - `RELEASE_TAG_RE` — extended regex, `^v[0-9]+\.[0-9]+\.[0-9]+$`
  - `RELEASE_TAG_GLOB` — `v[0-9]*`, a pre-filter, never the authority
  - `release_tag_is <tag-or-refname>` — exit 0 when it names a release tag
  - `release_tag_latest` — highest local release tag by `sort -V`, empty if none;
    never fails, so a caller under `set -e` can assign it directly
  - `RELEASE_NOTES_TYPES` — `(feat fix perf refactor docs test build ci chore)`
  - `release_notes_heading <type>` — the section heading for a type
  - `generate_release_notes <range>` — markdown on stdout, nothing for an empty range

- [ ] **Step 1: Copy both libraries and confirm they are self-contained**

```bash
H=/home/bnayahu/work/kaegis/simulation-harness
mkdir -p scripts/lib
cp $H/scripts/lib/release-tag.sh scripts/lib/
cp $H/scripts/lib/release-notes.sh scripts/lib/
grep -nE 'simulation|harness|/home/|config/' scripts/lib/*.sh
```

Expected: the `grep` prints nothing. Both were read in full before transplant and
are pure functions over `git` output. Do **not** `chmod +x` them: they are
sourced-only and deliberately set no shell options, because that would affect the
caller's shell.

- [ ] **Step 2: Confirm the generator works on this repository's real history**

```bash
bash -c 'source scripts/lib/release-notes.sh; generate_release_notes "HEAD~12..HEAD"' | head -20
```

Expected: `### Features` / `### Fixes` / `### Documentation` / `### Tests`
sections with bold scope prefixes. This was measured before the spec was written —
99% of this repository's non-merge commits are Conventional Commits — so a failure
here means the copy went wrong, not that the approach is unsuitable.

- [ ] **Step 3: Write the failing test**

Create `tests/unit/test_release_notes.py`.

```python
"""Tests for scripts/lib/release-tag.sh and scripts/lib/release-notes.sh.

Both are sourced-only bash, so each case runs a `bash -c 'source ...; ...'`
snippet against a throwaway git repository. No network, no `gh`.

Ported from the harness's shell suite rather than transplanted as shell: see the
Phase 3 note in the implementation plan. The short version is that a separate
`make test-scripts` target would be a fourth gate on a project whose
documentation names exactly three.
"""

import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
NOTES_LIB = REPO_ROOT / "scripts" / "lib" / "release-notes.sh"
TAG_LIB = REPO_ROOT / "scripts" / "lib" / "release-tag.sh"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    ).stdout


def _bash(repo: Path, lib: Path, snippet: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", f"source {lib}\n{textwrap.dedent(snippet)}"],
        cwd=repo, capture_output=True, text=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.name", "Test Author")
    _git(r, "config", "user.email", "test@example.com")
    return r


def _commit(repo: Path, subject: str, body: str = "") -> None:
    n = len(list(repo.glob("f*.txt")))
    (repo / f"f{n}.txt").write_text(subject)
    _git(repo, "add", "-A")
    msg = subject if not body else f"{subject}\n\n{body}"
    _git(repo, "commit", "-q", "-m", msg)


# --- release-tag.sh ---------------------------------------------------------

@pytest.mark.parametrize(
    "tag,expected",
    [
        ("v1.2.3", 0),
        ("refs/tags/v1.2.3", 0),
        ("v0.3.0-rc1", 1),   # a pre-release is not a release
        ("v1.2", 1),
        ("1.2.3", 1),
        ("v1.2.3.4", 1),
    ],
)
def test_release_tag_is_accepts_only_exact_release_tags(repo, tag, expected):
    result = _bash(repo, TAG_LIB, f'release_tag_is "{tag}"')
    assert result.returncode == expected


def test_release_tag_latest_picks_the_highest_and_ignores_pre_releases(repo):
    _commit(repo, "chore: base")
    for tag in ("v0.1.0", "v0.9.0", "v0.10.0", "v0.11.0-rc1"):
        _git(repo, "tag", tag)
    result = _bash(repo, TAG_LIB, "release_tag_latest")
    # sort -V, so v0.10.0 outranks v0.9.0 -- a lexical sort would get this wrong.
    assert result.stdout.strip() == "v0.10.0"


def test_release_tag_latest_is_empty_and_succeeds_with_no_tags(repo):
    _commit(repo, "chore: base")
    result = _bash(repo, TAG_LIB, "set -e; latest=$(release_tag_latest); echo \"[$latest]\"")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


# --- release-notes.sh -------------------------------------------------------

def test_notes_group_by_type_in_declared_order(repo):
    _commit(repo, "chore: base")
    _commit(repo, "fix(digest): bound a name")
    _commit(repo, "feat(brief): add a block")
    _commit(repo, "docs: explain the gate")
    out = _bash(repo, NOTES_LIB, 'generate_release_notes "HEAD~3..HEAD"').stdout
    assert out.index("### Features") < out.index("### Fixes") < out.index("### Documentation")
    assert "- **brief:** add a block" in out
    assert "- **digest:** bound a name" in out
    assert "- explain the gate" in out


def test_an_empty_range_produces_nothing(repo):
    _commit(repo, "chore: base")
    out = _bash(repo, NOTES_LIB, 'generate_release_notes "HEAD..HEAD"').stdout
    assert out.strip() == ""


def test_a_range_starting_at_a_tag_excludes_the_tagged_commit(repo):
    _commit(repo, "feat: before the tag")
    _git(repo, "tag", "v0.1.0")
    _commit(repo, "feat: after the tag")
    out = _bash(repo, NOTES_LIB, 'generate_release_notes "v0.1.0..HEAD"').stdout
    assert "after the tag" in out
    assert "before the tag" not in out


def test_a_merge_commits_own_subject_is_excluded_but_its_content_is_not(repo):
    """--no-merges. This repository's history is merge-based, so this case is the
    one that decides whether generated notes are usable here at all."""
    _commit(repo, "chore: base")
    _git(repo, "checkout", "-q", "-b", "side")
    _commit(repo, "feat(side): brought in by the merge")
    _git(repo, "checkout", "-q", "main")
    _commit(repo, "fix(main): on the trunk")
    _git(repo, "merge", "--no-ff", "-q", "--no-gpg-sign", "-m", "Merge the side branch", "side")
    out = _bash(repo, NOTES_LIB, 'generate_release_notes "HEAD~3..HEAD"').stdout
    assert "brought in by the merge" in out
    assert "Merge the side branch" not in out


def test_unparseable_subjects_fall_under_other(repo):
    _commit(repo, "chore: base")
    _commit(repo, "just some words")
    out = _bash(repo, NOTES_LIB, 'generate_release_notes "HEAD~1..HEAD"').stdout
    assert "### Other" in out
    assert "- just some words" in out


def test_a_bang_in_the_subject_declares_a_breaking_change(repo):
    _commit(repo, "chore: base")
    _commit(repo, "feat(api)!: rename the flag")
    out = _bash(repo, NOTES_LIB, 'generate_release_notes "HEAD~1..HEAD"').stdout
    assert out.index("### Breaking changes") < out.index("### Features")
    assert "- **api:** rename the flag" in out
    # Breaking commits still appear under their own type: the section adds
    # emphasis without removing anything.
    assert out.count("rename the flag") == 2


def test_a_breaking_change_footer_wins_over_the_subject(repo):
    """The footer says what the reader must *do*; the subject only says what
    changed. Both spellings of the token are accepted."""
    _commit(repo, "chore: base")
    _commit(
        repo, "feat(cli): change the default",
        body="BREAKING CHANGE: pass --explicit to keep the\nold behaviour.",
    )
    out = _bash(repo, NOTES_LIB, 'generate_release_notes "HEAD~1..HEAD"').stdout
    assert "### Breaking changes" in out
    # Folded onto one line, and the footer's prose is used, not the subject's.
    assert "- **cli:** pass --explicit to keep the old behaviour." in out


def test_trailers_below_the_footer_do_not_leak_into_the_notes(repo):
    """Collection stops at the first blank line, so Signed-off-by and
    Co-Authored-By never reach a bullet."""
    _commit(repo, "chore: base")
    _commit(
        repo, "feat(cli): change the default",
        body="BREAKING CHANGE: pass --explicit.\n\nSigned-off-by: Test Author <test@example.com>",
    )
    out = _bash(repo, NOTES_LIB, 'generate_release_notes "HEAD~1..HEAD"').stdout
    assert "Signed-off-by" not in out
    assert "- **cli:** pass --explicit." in out
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_release_notes.py -v`
Expected: all pass (the `release_tag_is` case is parametrized six ways).

If `test_release_tag_latest_picks_the_highest...` fails returning `v0.9.0`, the
copy lost `sort -V`. If the merge test fails, it lost `--no-merges` — and that one
matters most here, because this repository's history is merge-based.

- [ ] **Step 5: Run the three gates**

Run: `make test && make check && uv run rubrica check-skills`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add scripts/lib tests/unit/test_release_notes.py
git commit -S -s -m "$(cat <<'MSG'
build(release): add the release-tag and release-notes libraries

Transplanted from simulation-harness, verified self-contained: both are pure
functions over git output, sourced-only, and deliberately set no shell options
because that would affect the caller's shell.

release-tag.sh is the single definition of what a release tag is -- strictly
vX.Y.Z, so a v0.3.0-rc1 is never treated as the previous release. release-notes.sh
turns Conventional Commit subjects into grouped markdown.

Generated notes are the right choice here on measurement rather than preference.
A sibling project hand-maintains its changelog and states why -- squash-merge
collapses commit messages -- and that reason does not hold here: this repository
merges, so every subject survives. 640 of 643 non-merge commits are Conventional,
and the generator was run against this history before any of this was specified.

Tests are pytest driving `bash -c 'source ...'` against throwaway repositories,
not the harness's shell suite: a separate `make test-scripts` target would be a
fourth gate on a project whose documentation names three, and these scripts are
invisible to ruff, so their tests are the only gate they have.
MSG
)"
```

---

### Task 10: Transplant `release.sh` with its changelog, docs, target and tests

**Files:**
- Create: `scripts/release.sh`, `CHANGELOG.md`, `docs/releasing.md`
- Create: `tests/unit/test_release.py`
- Modify: `Makefile` (a `release` target)
- Modify: `docs/README.md` (index line for `releasing.md`)

**Interfaces:**
- Consumes: everything Task 9 produced (`release.sh` sources both libraries).
- Produces: `scripts/release.sh <version>`, plus `--dry-run <version>`. Env knobs,
  all with defaults: `RELEASE_REMOTE` (default `origin`), `RELEASE_GH_REPO`
  (default `github.com/skillberry-ai/rubrica`), `RELEASE_SKIP_GH` (set to skip the
  release page). Exit `0` on success, non-zero with a message on any preflight
  rejection.

- [ ] **Step 1: Copy the script and repoint its default repo**

```bash
H=/home/bnayahu/work/kaegis/simulation-harness
cp $H/scripts/release.sh scripts/release.sh
chmod +x scripts/release.sh
sed -i 's#github.com/skillberry-ai/simulation-harness#github.com/skillberry-ai/rubrica#g' scripts/release.sh
grep -nE 'simulation|harness|/home/' scripts/release.sh
```

Expected: nothing. Two lines carried the name — the usage text and the
`: "${RELEASE_GH_REPO:=...}"` default — and both are now rubrica's.

- [ ] **Step 2: Confirm it reaches for nothing rubrica lacks**

```bash
grep -nE '(^|[^a-z])(config/|deploy/|docker|Dockerfile|IMAGE_NAME|mypy|lint-imports)' scripts/release.sh
```

Expected: nothing. Its preflight reads `pyproject.toml`, `uv.lock`,
`CHANGELOG.md`, `git` and `gh` only — verified before transplant. **If this prints
anything, stop and report it**: the spec named exactly this as a way the plan could
be falsified, and the honest response is to widen the task, not to patch around it.

- [ ] **Step 3: Create `CHANGELOG.md` — header and compare links only**

`release.sh` prepends each section, so this file starts with nothing but its
header. The compare links are the practice adopted from `cap-evolve`; the harness
has none.

```markdown
# Changelog

Notable changes to rubrica, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows
[Semantic Versioning](https://semver.org/) — currently `0.x`, so anything may
change.

Sections below are generated at release time from Conventional Commit subjects
since the previous release tag, by `scripts/release.sh`. Write the commit subject
you would want to read here.

[Unreleased]: https://github.com/skillberry-ai/rubrica/compare/main...HEAD
```

**Exactly one trailing newline.** The harness's own test pins this invariant, and
Step 7 ports that assertion.

- [ ] **Step 4: Add the `release` target to the `Makefile`**

Read the existing style first: `sed -n '15,30p' Makefile`. Targets here carry `##`
help text.

```makefile
release: ## Cut a release: make release VERSION=0.2.0
ifndef VERSION
	$(error VERSION is required, e.g. make release VERSION=0.1.0)
endif
	./scripts/release.sh "$(VERSION)"
```

Run: `make release 2>&1 | head -3`
Expected: the `VERSION is required` error. That is the guard working.

- [ ] **Step 5: Write `docs/releasing.md`**

Adapt `$HARNESS/docs/releasing.md`. Keep verbatim: the tag definition, the cut
procedure, the dry-run note, and **the whole "Recovering from a partial run"
table** — five states, each with exactly one move. That table is the most valuable
thing in the document and it is all still true here.

Three changes:

1. Repoint `$RELEASE_GH_REPO`'s default to `github.com/skillberry-ai/rubrica`.
2. **Delete the "Container images" section entirely**, including its note about
   the atomic push firing the workflow twice. There is no image.
3. Replace it with:

````markdown
## PyPI

Cutting a release does not publish the package — publishing the *release* does.
`.github/workflows/publish.yml` triggers on `release: published`, builds an sdist
and a wheel, and uploads them to PyPI with a Trusted Publisher: no API token is
stored anywhere, and PEP 740 attestations are generated automatically.

This means the workflow is **inert until a trusted publisher is registered on
PyPI** for this repository, the workflow filename `publish.yml`, and the `pypi`
environment. Until then a release cuts a tag and a release page and publishes
nothing, which fails visibly in the Actions tab rather than silently.

To build the distributions locally without involving CI: `uv build`.
````

4. Replace the "Tests" section — there is no `make test-scripts` here:

````markdown
## Tests

The release scripts are covered by `tests/unit/test_release.py` and
`tests/unit/test_release_notes.py`, which build throwaway git repositories as
fixtures. They touch no network remote and call no `gh`, so they run in
`make test` like everything else.
````

Then add an index line to `docs/README.md` in the appropriate section.

- [ ] **Step 6: Read the harness's test suite before porting it**

Run: `sed -n '1,60p' /home/bnayahu/work/kaegis/simulation-harness/scripts/tests/test-release.sh`

Note especially the fixture: it gives the throwaway repo **its own SSH signing
key**, because `release.sh` passes `-S` unconditionally and the test must not
depend on the developer's real key or an unlocked agent. Your port must do the
same.

- [ ] **Step 7: Write the failing test**

Create `tests/unit/test_release.py`. Port the harness's fourteen sections. The
fixture is the hard part; get it right first and the cases follow.

```python
"""Tests for scripts/release.sh.

Builds a fixture repository with a local bare origin, copies scripts/ into it,
and drives release.sh there. Never touches a network remote and never calls gh --
RELEASE_SKIP_GH=1 covers the release-page step.

release.sh passes -S and -s unconditionally, which forces signing regardless of
commit.gpgsign. The fixture gets its own throwaway SSH signing key so the suite
never depends on a developer's real key or on an unlocked ssh-agent.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

PYPROJECT = """\
[project]
name = "fixture"
version = "0.1.0"
requires-python = ">=3.13"
"""

CHANGELOG = "# Changelog\n\nNotable changes, newest first.\n"


def _git(repo: Path, *args: str, check: bool = True):
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=check
    )


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    """A repo with pyproject.toml, CHANGELOG.md, scripts/, and a bare origin."""
    key = tmp_path / "signing_key"
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "fixture", "-f", str(key)],
        check=True, capture_output=True,
    )

    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "Test Author")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "gpg.format", "ssh")
    _git(repo, "config", "user.signingkey", str(key))
    _git(repo, "config", "commit.gpgsign", "true")
    _git(repo, "config", "tag.gpgsign", "true")

    (repo / "pyproject.toml").write_text(PYPROJECT)
    (repo / "CHANGELOG.md").write_text(CHANGELOG)
    shutil.copytree(REPO_ROOT / "scripts", repo / "scripts")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "chore: base")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "-u", "origin", "main")
    return repo


def _release(repo: Path, *args: str, **env) -> subprocess.CompletedProcess:
    e = {**os.environ, "RELEASE_SKIP_GH": "1", **env}
    return subprocess.run(
        [str(repo / "scripts" / "release.sh"), *args],
        cwd=repo, capture_output=True, text=True, env=e,
    )


def _commit(repo: Path, subject: str) -> None:
    n = len(list(repo.glob("f*.txt")))
    (repo / f"f{n}.txt").write_text(subject)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", subject)


def _version(repo: Path) -> str:
    for line in (repo / "pyproject.toml").read_text().splitlines():
        if line.startswith("version = "):
            return line.split('"')[1]
    raise AssertionError("no version in pyproject.toml")


# --- dry run ----------------------------------------------------------------

def test_dry_run_reports_and_changes_nothing(fixture_repo):
    _commit(fixture_repo, "feat: something")
    before = _git(fixture_repo, "rev-parse", "HEAD").stdout
    result = _release(fixture_repo, "--dry-run", "0.2.0")
    assert result.returncode == 0, result.stderr
    assert "dry run" in result.stdout
    assert _version(fixture_repo) == "0.1.0"
    assert _git(fixture_repo, "rev-parse", "HEAD").stdout == before
    assert _git(fixture_repo, "tag", "-l").stdout.strip() == ""


# --- preflight rejections ---------------------------------------------------

def test_a_dirty_worktree_is_rejected(fixture_repo):
    (fixture_repo / "pyproject.toml").write_text(PYPROJECT + "# scratch\n")
    result = _release(fixture_repo, "0.2.0")
    assert result.returncode != 0
    assert "uncommitted changes" in result.stderr


def test_a_non_main_branch_is_rejected(fixture_repo):
    _git(fixture_repo, "checkout", "-q", "-b", "feature")
    result = _release(fixture_repo, "0.2.0")
    assert result.returncode != 0
    assert "must be on main" in result.stderr


def test_a_bare_double_dash_with_no_version_is_rejected(fixture_repo):
    """`--` used to leave VERSION empty: usage printed here, but an empty version
    went through to the release step. The empty version is the failure that
    mattered, so assert on it directly rather than on the presence of a string
    somewhere in the combined output -- which almost nothing could fail.
    """
    result = _release(fixture_repo, "--")
    assert result.returncode != 0
    assert "sage" in result.stderr or "version" in result.stderr.lower()
    assert _version(fixture_repo) == "0.1.0", "an empty version reached the bump"
    assert _git(fixture_repo, "tag", "-l").stdout.strip() == ""


# --- first release ----------------------------------------------------------

def test_the_first_release_may_equal_the_current_version(fixture_repo):
    _commit(fixture_repo, "feat: something")
    result = _release(fixture_repo, "0.1.0")
    assert result.returncode == 0, result.stderr
    assert _git(fixture_repo, "tag", "-l").stdout.strip() == "v0.1.0"
    assert _git(fixture_repo, "log", "-1", "--format=%s").stdout.strip() == (
        "chore(release): v0.1.0"
    )


def test_the_changelog_gains_a_section_and_keeps_one_trailing_newline(fixture_repo):
    _commit(fixture_repo, "feat(scope): a feature")
    assert _release(fixture_repo, "0.1.0").returncode == 0
    text = (fixture_repo / "CHANGELOG.md").read_text()
    assert "## v0.1.0" in text
    assert "- **scope:** a feature" in text
    assert text == text.rstrip("\n") + "\n", "exactly one trailing newline"


def test_the_release_commit_and_tag_are_both_signed(fixture_repo):
    """`cat-file -t` reports "tag" for signed and unsigned annotated tags alike,
    so it cannot catch a dropped -S. Look at the objects themselves."""
    _commit(fixture_repo, "feat: something")
    assert _release(fixture_repo, "0.1.0").returncode == 0
    commit = _git(fixture_repo, "cat-file", "-p", "HEAD").stdout
    assert "gpgsig" in commit, "release commit is not signed (-S dropped?)"
    tag = _git(fixture_repo, "cat-file", "-p", "v0.1.0").stdout
    assert "SSH SIGNATURE" in tag or "SIGNATURE" in tag, "tag is not signed"
    body = _git(fixture_repo, "log", "-1", "--format=%B").stdout
    assert "Signed-off-by:" in body, "release commit lacks DCO sign-off (-s dropped?)"


def test_uv_lock_is_refreshed_with_the_bump_when_present(fixture_repo):
    """uv.lock pins the project's own version, so a bump that skipped the re-lock
    would leave the lockfile stale -- and CI runs `uv sync --locked`."""
    (fixture_repo / "uv.lock").write_text(
        'version = 1\n\n[[package]]\nname = "fixture"\nversion = "0.1.0"\n'
    )
    _git(fixture_repo, "add", "-A")
    _git(fixture_repo, "commit", "-q", "-m", "chore: add a lockfile")
    _git(fixture_repo, "push", "-q", "origin", "main")
    result = _release(fixture_repo, "0.2.0")
    if result.returncode != 0 and "uv is not on PATH" in result.stderr:
        pytest.skip("uv not on PATH; the preflight check for it is the behaviour here")
    assert result.returncode == 0, result.stderr
    assert _version(fixture_repo) == "0.2.0"
    # The point of the test: a stale lock is what breaks `uv sync --locked` in CI,
    # so assert the lockfile's own recorded version moved -- not just pyproject's.
    assert '0.2.0' in (fixture_repo / "uv.lock").read_text(), (
        "uv.lock still records the old version; the re-lock step did not run"
    )


# --- second release ---------------------------------------------------------

def test_an_equal_version_is_rejected_once_a_release_tag_exists(fixture_repo):
    _commit(fixture_repo, "feat: one")
    assert _release(fixture_repo, "0.1.0").returncode == 0
    _commit(fixture_repo, "feat: two")
    _git(fixture_repo, "push", "-q", "origin", "main")
    result = _release(fixture_repo, "0.1.0")
    assert result.returncode != 0
    assert "already exists locally" in result.stderr or "greater than" in result.stderr


def test_a_pre_release_tag_is_not_treated_as_the_previous_release(fixture_repo):
    """The notes range must stay anchored at the last real release."""
    _commit(fixture_repo, "feat: one")
    assert _release(fixture_repo, "0.1.0").returncode == 0
    _git(fixture_repo, "tag", "v0.2.0-rc1")
    _commit(fixture_repo, "feat: after the rc")
    _git(fixture_repo, "push", "-q", "origin", "main")
    result = _release(fixture_repo, "--dry-run", "0.2.0")
    assert result.returncode == 0, result.stderr
    assert "v0.1.0..HEAD" in result.stdout


def test_no_conventional_commits_still_produces_a_valid_section(fixture_repo):
    _commit(fixture_repo, "feat: one")
    assert _release(fixture_repo, "0.1.0").returncode == 0
    _git(fixture_repo, "push", "-q", "origin", "main")
    result = _release(fixture_repo, "0.2.0")
    assert result.returncode == 0, result.stderr
    text = (fixture_repo / "CHANGELOG.md").read_text()
    assert "No changes recorded." in text
    assert "\n\n## v0.1.0" in text, "a blank line must separate the new section"


# --- rollback and resume ----------------------------------------------------

def test_a_failed_commit_restores_the_worktree(fixture_repo):
    """Signing is mandatory, so point signingkey at a file that does not exist.
    Nothing may be left half-applied: a version bump with no tag makes that
    version permanently unreleasable."""
    _commit(fixture_repo, "feat: something")
    _git(fixture_repo, "config", "user.signingkey", str(fixture_repo / "nope"))
    result = _release(fixture_repo, "0.2.0")
    assert result.returncode != 0
    assert _version(fixture_repo) == "0.1.0", "pyproject.toml was left bumped"
    assert (fixture_repo / "CHANGELOG.md").read_text() == CHANGELOG
    assert _git(fixture_repo, "tag", "-l").stdout.strip() == ""


def test_a_tag_this_script_did_not_create_does_not_trigger_a_resume(fixture_repo):
    """There would be no bump and no changelog section to publish."""
    _commit(fixture_repo, "feat: something")
    _git(fixture_repo, "tag", "-a", "-m", "by hand", "v0.2.0")
    result = _release(fixture_repo, "0.2.0")
    assert result.returncode != 0
    assert "already exists locally" in result.stderr


def test_a_failed_push_is_resumable(fixture_repo):
    """Point the remote at nothing so the push fails, then repair it and re-run
    the same command; it must resume rather than start over."""
    _commit(fixture_repo, "feat: something")
    _git(fixture_repo, "remote", "set-url", "origin", str(fixture_repo / "nope.git"))
    first = _release(fixture_repo, "0.2.0")
    assert first.returncode != 0
    assert _git(fixture_repo, "log", "-1", "--format=%s").stdout.strip() == (
        "chore(release): v0.2.0"
    ), "the release commit should exist locally after a failed push"
    real = fixture_repo.parent / "origin.git"
    _git(fixture_repo, "remote", "set-url", "origin", str(real))
    second = _release(fixture_repo, "0.2.0")
    assert second.returncode == 0, second.stderr


def test_tempfiles_are_cleaned_up(fixture_repo):
    _commit(fixture_repo, "feat: something")
    assert _release(fixture_repo, "0.1.0").returncode == 0
    leftovers = [p.name for p in fixture_repo.iterdir() if ".tmp" in p.name]
    assert leftovers == [], leftovers
```

- [ ] **Step 8: Run the tests and iterate**

Run: `uv run pytest tests/unit/test_release.py -v`

Expect to iterate here — this is the largest single piece of the plan. Two known
sharp edges:

- **`ssh-keygen` must exist.** If it does not, add a module-level
  `pytest.importorskip`-style guard:
  `pytestmark = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="ssh-keygen not available")`.
- **`git` needs 2.34+ for SSH signing.** Check with `git --version`; if older,
  skip the two signing assertions rather than weakening them.

If a case cannot be made to pass, **do not delete it** — mark it
`@pytest.mark.xfail(reason=...)` with a specific reason and report it. A silently
dropped case is how the harness's four resumable states stop being covered.

- [ ] **Step 9: Verify the dry run works against this real repository**

Run: `./scripts/release.sh --dry-run 0.2.0`

Expected: a release plan naming the tag, the version transition `0.1.0 -> 0.2.0`,
the commit range, the remote, `github.com/skillberry-ai/rubrica`, and generated
notes — then `dry run: nothing was written`. Confirm afterwards that nothing changed:

Run: `git status --porcelain && git tag -l`
Expected: both empty.

This is the check the spec named as its own falsification condition: the generator
was only ever exercised over a range with no tag in it, and the first real run
computes an empty `prev_tag` and takes the whole history. Watch for the notes
being enormous — that is correct for a first release, but confirm it is not
malformed.

- [ ] **Step 10: Run the three gates**

Run: `make test && make check && uv run rubrica check-skills`
Expected: all green.

- [ ] **Step 11: Commit**

```bash
git add scripts/release.sh CHANGELOG.md docs/releasing.md docs/README.md Makefile tests/unit/test_release.py
git commit -S -s -m "$(cat <<'MSG'
build(release): add scripts/release.sh, a seeded CHANGELOG, and the release docs

`make release VERSION=X.Y.Z` bumps pyproject.toml, re-locks uv.lock, prepends a
generated CHANGELOG section, commits chore(release): vX.Y.Z, creates a signed
annotated tag, pushes main and the tag atomically, and creates the GitHub Release.
--dry-run previews it.

The re-lock is required here rather than optional: uv.lock pins this project's own
version, and CI runs `uv sync --locked`. A bump that skipped it would have the
release break the build it had just tagged.

Resumability is transplanted intact -- four partial-failure states, each with one
move, documented in docs/releasing.md. Resume is deliberately narrow: it fires
only for a tag this script created, on a chore(release) commit at HEAD whose
pyproject.toml already holds that version, so a hand-made tag is rejected rather
than resumed into a release with no bump.

CHANGELOG.md ships with a Keep a Changelog header and compare links and nothing
else; release.sh prepends every section after that. Compare links are adopted from
a sibling project -- the harness CHANGELOG has none.

No container step: nothing to build. docs/releasing.md's image section is replaced
by a PyPI one, which says plainly that publish.yml is inert until a trusted
publisher is registered, so a release publishes nothing and fails visibly rather
than silently.

Tests port the harness's shell suite to pytest, fixture and all -- including its
own throwaway SSH signing key, since release.sh passes -S unconditionally and the
suite must not depend on a developer's key.
MSG
)"
```

---

### Task 11: Publishing and hardening workflows, and the command lists

Separate from Task 10 because these three workflows do nothing until the PyPI
trusted publisher and the `pypi` environment exist. A reviewer should be able to
see that boundary in the history.

**Files:**
- Create: `.github/workflows/publish.yml`, `.github/workflows/dependency-review.yml`
- Modify: `.github/workflows/ci.yml` (workflow-level `permissions:`)
- Modify: `CLAUDE.md`, `CONTRIBUTING.md` (command lists gain `make release`)

**Interfaces:**
- Consumes: Task 10's `CHANGELOG.md` and release flow; Task 8's `[project.urls]`.
- Produces: nothing in-repo. Two out-of-repo prerequisites, which belong in the
  follow-on issue: a PyPI trusted publisher for `skillberry-ai/rubrica` +
  `publish.yml` + environment `pypi`, and a GitHub environment named `pypi`.

- [ ] **Step 1: Create `.github/workflows/publish.yml`**

**No `password:` input.** That single omission is the whole point: it is what makes
this OIDC rather than a stored token.

```yaml
name: Publish

on:
  release:
    types: [published]
  workflow_dispatch:

# id-token: write is what lets the job mint an OIDC token for PyPI's trusted
# publisher. contents: read is everything else it needs.
permissions:
  contents: read
  id-token: write

jobs:
  publish:
    name: Build and publish
    runs-on: ubuntu-latest
    # A GitHub environment, so publication can carry its own protection rules
    # (required reviewers, branch restrictions) independently of the workflow.
    # PyPI's trusted publisher is registered against this name, so it is not
    # decorative -- changing it breaks publication.
    environment: pypi

    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Set up uv
        uses: astral-sh/setup-uv@v7
        with:
          python-version: "3.13"

      - name: Build
        run: uv build

      - name: Check distribution metadata
        run: uv run --with twine twine check dist/*

      # No `password:` and no `secrets.*`. Authentication is the OIDC token the
      # `id-token: write` permission above allows, exchanged for a short-lived
      # upload token by the trusted publisher registered on PyPI for this
      # repository, this workflow filename and the `pypi` environment. A stored
      # API token would be a long-lived credential with upload rights to the
      # package, and PEP 740 attestations are generated automatically only on the
      # OIDC path.
      #
      # This step fails until that publisher is registered. That is the intended
      # failure mode: visible in the Actions tab, rather than a release that
      # silently ships nothing.
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
```

- [ ] **Step 2: Create `.github/workflows/dependency-review.yml`**

```yaml
name: Dependency Review

on:
  pull_request:
    branches: [main]

permissions:
  contents: read
  pull-requests: read

jobs:
  dependency-review:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v7

      - name: Review dependency changes
        uses: actions/dependency-review-action@v4
        with:
          fail-on-severity: high
```

- [ ] **Step 3: Add the `permissions:` block to `ci.yml`**

Insert at workflow level, after `on:` and before `jobs:`.

```yaml
# Least privilege at the workflow level rather than per job. Nothing in CI writes
# to the repository: the gates read the tree, and the DCO job reads history. Set
# here so a job added later is constrained by default instead of inheriting the
# repository-wide token permissions.
permissions:
  contents: read
```

Then confirm nothing broke:

Run: `python3 -c "import yaml;d=yaml.safe_load(open('.github/workflows/ci.yml'));print(d['permissions'], sorted(d['jobs']))"`
Expected: `{'contents': 'read'} ['check', 'dco']`

- [ ] **Step 4: Validate all five workflow files parse**

```bash
for f in .github/workflows/*.yml .github/dependabot.yml; do
  python3 -c "import yaml,sys;yaml.safe_load(open(sys.argv[1]));print('ok', sys.argv[1])" "$f"
done
```

Expected: `ok` for `ci.yml`, `codeql.yml`, `dependency-review.yml`, `publish.yml`,
and `dependabot.yml`.

- [ ] **Step 5: Update `CLAUDE.md`'s command block**

Run: `grep -n -A12 'make setup' CLAUDE.md | head -20`

Add `make release` to the fenced list, matching the existing comment alignment.
Keep the sentence that names the three gates **exactly as it is** — `make release`
is not a gate, and adding it to that sentence would be wrong.

- [ ] **Step 6: Update `CONTRIBUTING.md`**

Run: `grep -n -iE '^## |make ' CONTRIBUTING.md | head -30`

Add a short `## Releasing` section pointing at `docs/releasing.md` rather than
duplicating it — one command and one link. Do not restate the recovery table.

- [ ] **Step 7: Confirm the docs policies still hold**

Run: `uv run pytest tests/unit/test_docs_accuracy.py -q`
Expected: PASS. Both files are in `_user_facing()`, so both are subject to the
no-hand-typed-count and no-counting-heading rules — and to Task 6's new citation
guard, which is why this task must come after Task 6.

- [ ] **Step 8: Run the three gates**

Run: `make test && make check && uv run rubrica check-skills`
Expected: all green. `make check` reads `CLAUDE.md` and `CONTRIBUTING.md`, both
edited here, so this is the step that catches a line over 100 columns in a fenced
block or a reformatted table.

- [ ] **Step 9: Commit**

```bash
git add .github CLAUDE.md CONTRIBUTING.md
git commit -S -s -m "$(cat <<'MSG'
ci: publish to PyPI over OIDC, review dependency changes, drop token permissions

Three practices adopted from a sibling project, each measured absent here.

publish.yml triggers on `release: published` and carries no `password:` and no
`secrets.*`. That omission is the point: the one org repo publishing to PyPI today
already sets id-token: write and environment: pypi -- the complete OIDC
scaffolding -- and then passes a stored API token anyway, so the token does the
work and the OIDC block is inert. This takes the configuration that setup was
evidently reaching for: no long-lived credential with upload rights, and PEP 740
attestations, which are generated only on the OIDC path.

The workflow fails until a trusted publisher is registered on PyPI for this
repository, this filename and the pypi environment. That is the intended failure
mode -- visible in the Actions tab rather than a release that silently ships
nothing.

dependency-review.yml gates dependency changes on a PR at severity high; neither
this project nor the harness had it. ci.yml gains `permissions: contents: read` at
workflow level -- neither ci.yml declared one, so both inherited repository-wide
token permissions. Nothing in CI writes to the repository.

CLAUDE.md and CONTRIBUTING.md gain `make release`. No test guards those command
lists: test_docs_accuracy.py checks stages, skills, subcommands and artifact kinds
against the code that owns them, and a Makefile target is none of those -- so this
is done by hand deliberately rather than left for a gate to catch. The sentence
naming the three gates is unchanged; a release is not a gate.
MSG
)"
```

---

### Task 12: File the follow-on issues

Not a commit — two issues, so the out-of-repo prerequisites and the sibling
findings are on a tracker rather than only in this plan.

**Interfaces:**
- Consumes: everything above, since the issue bodies cite what landed.
- Produces: nothing.

- [ ] **Step 1: File the issue against `simulation-harness`**

Practices 2, 3 and 4 apply there and it has none of them. **`llm-switchboard` is
out of scope — do not file anything against it.**

```bash
gh issue create --repo skillberry-ai/simulation-harness \
  --title "Adopt three CI and changelog practices measured absent: workflow permissions, dependency review, changelog compare links" \
  --body "$(cat <<'MSG'
Found while preparing `rubrica` for its public home against this repository as the
template. Three things this repo does not have that are cheap and that `rubrica`
now does. Each is measured, not recalled.

**1. `ci.yml` declares no `permissions:` block.** `codeql.yml` and
`docker-publish.yml` each do; `ci.yml` does not, so its jobs inherit the
repository-wide token permissions. Nothing in that workflow writes to the repo.
One block at workflow level fixes it and constrains any job added later by
default:

    permissions:
      contents: read

**2. No `.github/workflows/dependency-review.yml`.** `llm-switchboard` has one.
PR-scoped, ~15 lines, `fail-on-severity: high`.

**3. `CHANGELOG.md` carries zero compare links.** `cap-evolve` uses Keep a
Changelog with `[Unreleased]` and per-version `compare` links. Generation does not
preclude them — they are header lines, not section content.

Not proposed, and deliberately so: sha-pinning of actions. This repo's
`dependabot.yml` argues the floating-major-tag choice explicitly, and overturning
it means revisiting those `ignore` rules in the same change. That is org-wide
supply-chain policy, not this.
MSG
)"
```

- [ ] **Step 2: File the prerequisites issue against this repository**

The two service-side settings, plus the ruleset. None of these can live in a commit.

```bash
gh issue create \
  --title "Post-move configuration: PyPI trusted publisher, the pypi environment, and the branch ruleset" \
  --body "$(cat <<'MSG'
Everything in the open-source readiness work that is a setting on a service rather
than a file in a commit. Each is inert-but-harmless until done, and each has a
workflow already waiting for it.

**1. Register a PyPI trusted publisher.** Owner `skillberry-ai`, repository
`rubrica`, workflow `publish.yml`, environment `pypi`. Until this exists,
`publish.yml`'s final step fails — visibly in the Actions tab, which is the
intended failure mode rather than a release that silently ships nothing. The
`rubrica` name was unclaimed on PyPI when this was checked.

**2. Create the `pypi` GitHub environment**, with whatever protection rules
publication should carry (required reviewers, branch restrictions). `publish.yml`
names it and PyPI's trusted publisher is registered against it, so it is not
decorative.

**3. Add the default-branch ruleset**, enforcement `active`: block `deletion`,
block `non_fast_forward`, require a pull request, and require the **`DCO`** status
check. This is the one that actually binds the DCO: the job is pull-request only,
so without a ruleset requiring a PR, a direct push to `main` bypasses the check
rather than failing it.

**4. Enable `secret_scanning`, `secret_scanning_push_protection` and
`dependabot_security_updates`**, and set the repository description and topics.

Then budget a security-triage round for whatever scanning reports once the repo is
populated. Worth knowing before reading a clean CodeQL run as evidence:
**CodeQL does not analyse shell**, and `scripts/dispatch-stage.sh` is a substantial
shell program. `SECURITY.md` says so too.
MSG
)"
```

- [ ] **Step 3: Report the issue URLs**

Print both URLs in your task report so they can be linked from issue #24.

---

## Self-Review

Run against the spec after the plan is written, before execution starts.

**Spec coverage.** Every section of
`docs/superpowers/specs/2026-09-09-open-source-readiness-design.md` maps to a task:

| Spec section | Task |
|---|---|
| Decision 1 — target names kept | no task; nothing to do is the ruling |
| Decision 2 — citations rewritten | 2, 3, 4, 5, 6 |
| Decision 3 — records kept, script fixed | 1 |
| Decision 4 — fixture published | no task; the ruling is to change nothing |
| Decision 5 — `SECURITY.md` scope, no threat model | 8 (Step 3) |
| Workstream A — files added / changed | 7, 8 |
| Workstream A — `dco` job and its pytest test | 7 |
| Workstream B — `findings.md`, 118 rewrites, guard | 2, 2b, 3, 4, 5, 6 |
| Workstream C — transplant, changelog, docs, target | 9, 10 |
| Workstream C — four adopted practices | 10 (compare links), 11 (OIDC, dependency review, permissions) |
| Workstream C — practice not adopted (sha pins) | 8 (Step 6 keeps the `ignore` comment); Task 12 restates it |
| Workstream C — harness gets an issue | 12 |
| Workstream C — stale command lists | 11 (Steps 5–6) |
| Testing — pytest not shell, both suites | 7, 9, 10 |
| Out of scope — publisher, environment, ruleset | 12 (Step 2) |

**Placeholder scan.** No `TBD`, `TODO`, "add error handling", or "similar to Task
N". Where a file is transplanted rather than written, the plan gives the exact
source path and the exact adaptations. Where content depends on reading source
material that would not survive being paraphrased — the thirteen issue bodies in
Task 2, the harness's `releasing.md` in Task 10 — the plan gives the exact command
to read it and the exact structure to produce.

**Type and name consistency.**

- The eleven finding names and their anchors are fixed once, in Task 2's table, and
  consumed unchanged by Tasks 3, 4 and 5.
- `_TRACKER_CITATION` and `_code_files()` are defined in Task 6 and used only there.
- `RELEASE_TAG_RE`, `release_tag_is`, `release_tag_latest`, `RELEASE_NOTES_TYPES`,
  `release_notes_heading` and `generate_release_notes` are declared as Task 9's
  Produces and consumed by Task 10's `release.sh`.
- `RUBRICA_ROSSOCTL_TOOL_DIR` / `RUBRICA_ROSSOCTL_AGENT_SRC` are introduced in
  Task 1 and referenced nowhere else.
- `RELEASE_REMOTE`, `RELEASE_GH_REPO`, `RELEASE_SKIP_GH` are declared in Task 10's
  Produces and used by its own test helper.
- `pypi` names one thing throughout: a GitHub environment, referenced by
  `publish.yml` in Task 11 and by the registration step in Task 12.

**Known deviations from the spec, both deliberate.**

1. **The spec's commit 3 becomes four commits** (Tasks 3, 4, 5, 6). A 35-file prose
   commit is not reviewable, and each tree passes the gates alone because the guard
   does not exist yet.
2. **The spec's commit 5 becomes two** (Tasks 9, 10), so each delivers a tested
   unit rather than shipping `release.sh` before anything exercises it.

Net: nine commits plus two issues, against the spec's six commits plus one issue.
