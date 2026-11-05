# `target-brief`: a report, then a workbook

## Why

`target-brief` is unreadable at real scale. Measured on `run-20261103-172151` (the
`fullsend-triage` corpus, 21 files): the page is 485 KB. About 200 KB of it is 119
disagreements in one flat list, each carrying a ~520-character `nature` paragraph that
holds 239 claim ids between them. Another ~195 KB is a 130-row capability table, with
122 "Not addressed" outcome lines inside it. The three asks fit on one screen;
everything after them is a wall.

Flat is the wrong shape for 119 items. The reader cannot see that `docs/triage.md` is
in 37 of them, and that when a disagreement was settled the other file won 14 times out
of 17. That observation is the most useful thing the run knows about the owner's
system, and the page never says it.

The page also serves only one of the two needs it has. It asks the owner to *correct
us*. The owner gets nothing back for reading it, so they have little reason to read.

## Intent: two needs, one file

1. **Immediate value to the owner.** An independent reviewer read your system. Here is
   what it seems to do, what it can do, and where its design looks inconsistent. Many
   of the run's disagreements are findings about the owner's system, not only about our
   confusion. This part must be readable by someone who will never answer a question.
2. **What we need back.** To build a benchmark for the system, we need the owner to
   confirm that our understanding is right and to settle the questions we could not.

**The owner must never feel handed a to-do list just for opening the page.** That is
the requirement that shapes the page (the user's own concern): a reader who sees "119
items need you" closes the tab. So the page is split into a **Report**, which asks for
nothing, and a **Workbook**, which asks for a short, bounded set of answers first.

## Goals

- A Report tab, open by default, that someone after need 1 alone can read in a few
  minutes and finish without being asked for anything.
- A Workbook tab that starts with **10 items** (stated, finite, "stop whenever you
  like"), with everything else beneath it, collapsed and marked optional.
- Disagreements grouped by **topic** (the run's subjects) instead of listed flat, with
  the per-file observations surfaced as **quick takes** in the Report.
- Answers captured in the page and returned two ways: **Print / save as PDF**, and
  **Download answers** as a JSON file.
- The "We went with X" limitation resolved (see its section below).
- Still **one self-contained HTML file**: inline CSS and inline JS, no network, no
  external asset, no CDN.

## Non-goals

- Nothing reads `answers.json` back into a run yet. The file is shaped so a later
  command could ingest it (stable ids, versioned), but ingestion is a separate design.
- No new judgment at render time. Every quick take is arithmetic over recorded fields.
  The page does not decide anything a stage did not record.
- No change to any stage, skill, schema, or recorded fixture. This is a renderer and
  reader change. (One exception is considered and **deferred**: a short `question`
  field on contradictions. See "Headlines".)
- No server, no persistence beyond the reader's own browser.

## Anti-goals (failure even if it works)

- **A Report that nags.** If the Report shows counts of open items, progress bars, or
  "needs your ruling" chips, the split has failed. Open counts belong in the Workbook.
- **A paraphrase presented as the owner's or the run's words.** The selected-never-
  rewritten rule stands (`target_brief.py` module docstring; CLAUDE.md). Sentences
  *we* compose about patterns are allowed and are visibly ours (see "Quick takes"). A
  stage's prose is still shipped verbatim or not at all.
- **A page that is blank with scripts off.** Scripts are now allowed (the user's
  ruling), but the page must still read without them. See "No-JS behaviour".
- **Our vocabulary in what the reader sees.** The two existing tests stay
  (`test_the_pages_own_prose_never_names_a_stage_a_gate_or_an_artifact`,
  `test_page_never_shows_a_rubrica_identifier`), along with
  `test_page_drops_the_target_name_rather_than_showing_the_run_directory`, but they are
  **rescoped to visible text** (the user's ruling, 2026-11-05). The answers export
  needs machine ids: item ids in `data-` attributes, the format name, the manifest
  digest, the run id in the download file name, and the storage key. Those may sit in
  attributes, in the `<script>` element and in the exported file. They may never sit in
  text a reader sees, on screen or in print. A shared test helper produces the visible
  text: parse the page with `html.parser`, drop `<script>`, `<style>` and every
  attribute, keep text nodes. Each rescoped test must be measured both ways: it still
  goes red when an id is planted in a visible cell, and it stays green with ids in
  `data-` attributes. The loosening is accepted on purpose: a leak into markup no
  reader sees is no longer caught. "Topic" is the owner-facing word for a subject;
  never "subject" and never "claim".
- **Severity vocabulary.** `test_no_severity_vocabulary_reaches_the_page` stays. The
  quick takes describe patterns ("looks out of date"), never rank harm ("critical").

## Rulings this design overturns, explicitly

1. **"No JavaScript. Not one line."** (`target_brief_html.py` docstring;
   `docs/reference/cli.md` §`rubrica target-brief`). The user overturned it on
   2026-11-05, on the condition that the report stays a single self-contained file.
   The reason the old ruling gave (opened in a mail client's view, behind a proxy,
   scripts off) is answered by the no-JS fallback below rather than ignored.
   `test_page_is_self_contained_and_carries_no_script` changes: it keeps the
   no-`http(s)://` and inline-`<style>` assertions, replaces "no `<script`" with
   "exactly one inline `<script>` with no `src`", and gains a no-JS check (below).
2. **"No `<ul>`/`<li>`"** (`test_a_populated_page_carries_no_bullet_list`). The quick
   takes are a list by nature. Either render them as a one-column table (keeping the
   test) or relax the test to exempt the quick-takes block by its own constant, the
   way `_LEGEND` is exempted. **Builder's call;** the table keeps one rule intact and
   is the default.
3. **"There is no place on it to record an approval"** (`docs/reference/cli.md`). The
   Workbook records answers. It still records no *ratification of the run*; it records
   per-item answers. The reference text changes accordingly.
4. **"Three ranked asks lead"** (CLAUDE.md, `docs/reference/cli.md`). The asks become
   the Workbook. CLAUDE.md's `target-brief` paragraph and the cli reference must be
   rewritten to describe Report + Workbook.

## The page

Two tabs at the top: **Report** (default) and **Workbook**. A tab is a JS toggle over
two `<section>`s. With JS off, both sections render one after the other (Report first),
which is the fallback layout.

### Report

In order:

1. **Header.** Target name and interface (existing `headline`). One lede sentence,
   reframed from "does this describe your system?" to "an independent reader went
   through 21 of your files; here is what we took away". The question moves to the
   Workbook. The existing banners (unreadable description, unreadable sources) stay
   here, unchanged.
2. **What it seems to do.** A short orientation:
   - the actors (`world_model.actors`, 19 on the measured run) and their goals
     (`world_model.goals`, 40), shown as "who uses it and what for" — the current
     "Who uses it" content, promoted and compressed to one line per actor with its goal
     count, expandable;
   - capabilities grouped, each group expandable to the existing per-operation rows.

   **Grouping capabilities:** not by service. Measured, `01-services.json` holds two
   services with one tool each (`Bash`, `Skill`), so it does not partition 130
   capabilities. Group by the **capability id's second segment** (`cap.<group>.…`):
   measured, `agent` 50, `tracker` 44, `post` 13, `skill` 7, `config` 5, `dispatch`
   4, `harness` 4, `labels` 2, `util` 1. That segment is an id convention rather than a
   schema field, so: when an id does not have the shape, it goes into an "Other"
   group; and the group label shown is the segment itself, title-cased, not invented
   prose. **Builder's call** whether a capability with outcomes marked "Not addressed"
   shows them inline or as a per-row count ("3 outcomes not described"). A count is the
   default, with the lines in the expanded row.
3. **What looks off** — the **quick takes**. See below. Each take has an "Examples ▸"
   disclosure showing up to three of the disagreements the take counts (both quotes,
   read-only), plus a link "See all N in the workbook". Which three is mechanical, not
   "representative": undecided ones first, then by id. For "Looks out of date", only
   ones the file lost are shown, because that is what the sentence claims.
4. **What we could not find.** The open questions (gaps) shown read-only, grouped by
   topic where a gap can be placed (see "Grouping"), headline only (`unknown`), with a
   link into the Workbook. **Builder's call** whether to cap this at a few with "and N
   more"; the default is to show them all, collapsed under their group, since they are
   headlines.
5. **Invitation.** A single box: "Want to help us test this system? Answering a few
   questions lets us build a benchmark that matches how it really behaves. Open the
   workbook →". This is the Report's only ask.
6. **Full reference** (collapsed): what data it holds (entities), what we read (the
   existing inputs table). The capability rows live under section 2.

No open-item counts, no status chips meaning "needs you", and no progress anywhere in
the Report. Resolution status may appear inside the examples as a plain label ("we
could not decide", "we went with this side") because that is a fact, not a task.

### Workbook

1. **Lede.** The question that moved from the Report: "Does this describe your system?
   Where it does not, we would rather hear it now than build on it."
2. **Start here: the 10 answers that help us most.** "About 15 minutes. Stop whenever
   you like; whatever you answer still counts." A counter `Answered k / 10`. The two
   export buttons.
3. The 10 items, each an **answer card** (see below).
4. **Everything else (optional).** Collapsed groups:
   - remaining disagreements, grouped by topic, with filter chips by kind of ask
     (*we could not decide* / *please confirm our pick* / *both readings may hold*) and
     a group-by toggle: **topic** (default) or **file**;
   - remaining open questions, grouped by topic;
   - "Did we miss a source?" — the existing what-we-read table, with a free-text card
     ("a file we should have read").
   Each has its own counter. The export includes every answer, inside or outside the
   10.

**The 10 are chosen mechanically** (my call, stated so it can be changed). A strict
kind order would fill all 10 with undecided disagreements on the measured run (43 of
them), so no confirmation and no open question would ever reach the owner. So the 10
are filled by **quota per kind**:

| Kind | Quota |
|---|---|
| undecided disagreements (`unresolved`, or off-enum) | 5 |
| confirm our pick (`preferred_a` / `preferred_b`) | 3 |
| open questions | 2 |
| `both_possible` | 0 |

When a kind has fewer items than its quota, the unused slots go to the next kind in the
order of the table (and from the last back to the first), then to `both_possible`. If
fewer than 10 items exist in total, take them all and change the copy to state the real
number. The quotas are named constants.

Within a kind, the order is:

1. items that **touch a quick take**: a disagreement whose side files include a file a
   take names, or whose topic is a take's topic; an open question whose topic is a
   take's topic;
2. then items whose topic has the most disagreements;
3. then by id, for determinism.

The first slot in the 10 goes to the first undecided item, and slots then alternate
through the kinds in table order, so a reader who stops after three has seen one of
each. The choice has to be deterministic: two
renders of one run must select the same 10 (byte-identical page; see "Determinism").
This ranking is the one "piece of new analysis" `disputes()`'s docstring warned
against, so it is labelled as ordering, never as importance: the copy says "the
answers that help us most", which is a statement about *us*, and nothing per-item says
"important" or "critical".

### Answer cards

A disagreement card shows a **headline** (see "Headlines"), the two sides as two columns
(file, locator, quote; the existing `_side_rows` data), and the run's full `nature` and
`rationale` under a "Our full reasoning ▸" disclosure. Controls by kind:

| Kind | Controls |
|---|---|
| `unresolved` | ◯ The left is right · ◯ The right is right · ◯ Both, in different cases · ◯ Neither · note |
| `preferred_a`/`_b` | ◯ Yes, our pick is right · ◯ No, the other side is · ◯ Neither · note |
| `both_possible` | ◯ Yes, both hold · ◯ No, only the left · ◯ No, only the right · note |
| open question | free-text answer · ◯ I don't know either |
| missed source | free-text |

Unknown `resolution` values render as `unresolved` (existing rule, kept). A note is
always optional; a choice is never required before export.

### "Our pick" replaces "We went with X" (resolves the limitation)

`docs/design/limitations.md` § *"We went with X" identifies nothing when both sides of a
disagreement were read from the same file* parked the fix because every **sentence**
reachable from the reader was worse. The fix is to drop the sentence. The renderer
marks the chosen **side** with an *our pick* badge on that side's column, which already
carries its own locator and quote. A same-file pair now reads exactly as a cross-file
pair does: the owner sees which quote we took, not which file.

Concretely:

- `Dispute.taken: str` is replaced by `Dispute.chosen: Literal["a", "b", None]`
  (`None` for `unresolved`, `both_possible`, or an off-enum value). The reader keeps no
  layout strings, which keeps the reader/renderer split the limitation was protecting.
- The renderer badges column a or b. The `_UNRESOLVED_SIDE` case (a chosen side that
  resolves to no source) keeps its existing sentence, placed in the badged column.
- `both_possible` shows a neutral badge on both columns ("both may hold"). The
  `_BOTH_POSSIBLE` sentence is no longer needed.
- The limitations entry is **removed** from `limitations.md` (it is a list of open
  items), and its resolution recorded in the commit message and this spec. Its
  measurement (4 of 41 on `run-20260826-090456`, 27 of 119 same-file here) moves into a
  test docstring that renders a same-file pair and asserts the badge sits on the chosen
  side.
- Tests that pin `taken` text (`test_a_settled_dispute_carries_the_settled_chip_and_names_the_file`
  and any in `test_target_brief.py`) are rewritten to assert the badge position.

### Headlines

Each item needs a short line a reader can scan. Rules in priority order:

1. **The first sentence of `nature`, when it is ≤ 200 characters and carries no claim
   id.** Measured on this run, that holds for only 16 of 119, since 101 first sentences
   carry an id or the word "claim" and 100 run past 200 characters. Selecting a
   sentence is allowed (selected, never rewritten).
2. Otherwise **no headline sentence**: the card is headed by its topic label and the two
   file names ("docs/triage.md vs scripts/post-triage.src.sh"), with `nature` under the
   disclosure. That is chrome we compose from facts, not a paraphrase.

So most cards on a real run get rule 2. That is acceptable for this design. A better
headline needs a stage to write one: an optional, owner-facing `question` field on each
contradiction, written by `rb-reconcile-contradict`. That is a schema, skill and
re-record change, and it is **deferred to a follow-up**. When the field is present, the
renderer prefers it over rule 1; build the reader to take it if present, so the
follow-up is a stage change only.

### Quick takes

Sentences we compose, from counts over recorded fields. They are visibly ours (the
section says "patterns we noticed"), and each one links to the items it rests on so
the owner can check it. Templates, all deterministic:

| Take | Fires when | Sentence |
|---|---|---|
| Looks out of date | a file was on the losing side of ≥ 5 settled cross-file disagreements **and** lost ≥ 75% of its settled ones | "**F** looks out of date. Of the S disagreements with other files we could settle, the other file was right in L." |
| Likely source of truth | a file won ≥ 5 settled cross-file disagreements and lost ≤ 1 | "**F** looks like your real source of truth: it was on the winning side in W of S." |
| Contradicts itself | a file has ≥ 3 disagreements where both sides are read from it | "**F** contradicts itself in N places." |
| Busiest topic | the topic(s) with the most disagreements; top 3 | "Your files disagree most about **T** (N places, U we could not decide)." |

Measured on `run-20261103-172151` (cross-file = 92 after excluding 27 same-file):
`docs/triage.md` 3 won / 14 lost (fires: out of date); `scripts/post-triage.src.sh` 6
won / 1 lost (fires: source of truth); `agents/triage.md` 6 self-contradictions; the
top topics `forge-label-write-ops` (9) and `triggers-and-dispatch` (8). **The
thresholds are my call**, chosen to fire on this run and stay quiet on a small run; they
live as named constants with a comment citing this measurement. A take that fires for
nobody is simply absent. If none fire, the section says "No pattern stood out across
your files", not nothing.

"Out of date" is an inference from a loss ratio, so the sentence must stay hedged
("looks"), and the take's Examples must show the disagreements it lost.

**Sides that span several files** (my call; never reached on the measured run, where
every side resolves to one file). A side's *file set* is the set of owner-openable
files its claims resolve to. A pair is **same-file** only when both sides' file sets are
equal and have one member. Every other pair is cross-file. On a settled cross-file pair,
every file in the winning set that is not also in the losing set is credited a win, and
likewise for losses. A file on both sides is credited neither. The badge rule does not
depend on this, since it marks a column, not a file.

The "file" here is the owner-openable file (`_file_and_piece(...)[0]`), so slices of
one capture count as one file, the same rule as everywhere else on the page.

### Grouping

- **Disagreement → topic.** The run writes one `01-contradictions/<subject_id>.json` per
  subject, so a contradiction's topic is the file it was written to (measured: all 119
  world-model contradictions appear in exactly one part). The topic label is the
  subject's `label` from `01-subjects.json`, shown verbatim (selected). Some labels are
  long (`actors-and-roles` is a 160-character list); show the label up to its first
  `:` when it has one, otherwise in full. That trims; it does not rewrite. The reader
  reads `01-contradictions/` and `01-subjects.json`. If either is unreadable, the topic
  falls back to a single "All disagreements" group and the page says it could not group
  them, the same marker pattern as elsewhere. It never drops the items.
- **Disagreement → file** (Workbook toggle). The files on each side.
- **Open question → topic.** A gap carries `claims`; its topic is the subject holding
  most of those claims (ties broken by subject id). No claims, or none in any subject,
  means an "Other questions" group.
- **Capability → group.** The id segment, as above.

### Answers: in page, PDF, JSON

- State lives in a JS object keyed by **item id** (contradiction `id`, gap `id`, or the
  fixed id `missed-source`). It is also mirrored into `localStorage` under a key that
  includes the run's manifest digest, wrapped in try/catch, so a reload keeps work in
  progress. Losing it (private window) is acceptable.
- **Print / save as PDF** calls `window.print()`. A print stylesheet shows both tabs,
  expands every `<details>` that holds an answered item, hides unanswered optional
  groups, and prints each answer beside its question (the selected option's label and
  the note). Hiding the unanswered optional groups is my call: the PDF is a record of
  what was answered, not a second copy of the page.
- **Download answers** builds a JSON Blob and triggers a download via an `<a download>`
  with an object URL. Works offline and from a `file://` page. File name
  `answers-<target-name>-<run-id>.json`. The run id is allowed here because it is
  machine text for us, and it is not displayed on the page.

```json
{
  "format": "rubrica-target-brief-answers",
  "version": 1,
  "run_id": "run-20261103-172151",
  "manifest_sha256": "…",
  "generated": "<page render time, embedded at render>",
  "exported": "<ISO time of the click>",
  "answers": [
    {"item": "ctr-sandbox-denial-handling-002", "ref": "D88", "kind": "unresolved",
     "choice": "left", "note": "…"},
    {"item": "gap.fullsend-cli-contract", "ref": "Q7", "kind": "question",
     "choice": null, "text": "…"}
  ]
}
```

`choice` values are fixed tokens per kind (`left`, `right`, `both`, `neither`, `yes`,
`no_other`, `only_left`, `only_right`, `dont_know`), with **left = `claim_a`, right =
`claim_b`**, always. The renderer must never swap columns, so that left/right stays
meaningful to a later ingester. `generated` is a problem for determinism (below); use
the manifest's recorded time, not wall-clock.

### No-JS behaviour

With scripts off: both sections render one after the other (Report first), every group
is a native `<details>`, the cards show their sides and disclosures, and the controls
are absent or disabled, with one line explaining that answering needs scripts and that
the owner can still reply by email quoting each item's visible reference. The existing "How to reply"
block keeps that path. Test: render, strip the `<script>` element, and assert that
every disagreement id's headline/sides and every section heading are still present in
the HTML. Tabs are implemented as JS adding a class over sections that are both visible
by default; never as content that JS injects.

### Determinism and size

- Byte-identical output for identical inputs (existing property of the composer). All
  data the JS needs is embedded at render time: either as server-rendered HTML that the
  JS only toggles, or as one `<script type="application/json">` data block. **Default:
  server-rendered HTML,** because the no-JS requirement needs it anyway. The JS reads
  ids from `data-` attributes and builds nothing that is content.
- No `Date.now()` in rendered output. Time only enters at export.
- Size: the measured page's content barely shrinks, since nothing is deleted, only
  collapsed. The goal is what is *visible*, not bytes. Two cheap wins: the 239 claim
  ids now sit inside collapsed `nature` text, and the "Not addressed" lines become a
  count with the detail collapsed.

### Visible references

Every item carries a short reference printed on its card, its Report example and its
PDF line: `D<n>` for a disagreement, `Q<n>` for an open question. `n` is the item's
1-based position in **id order** within its kind. So it is stable for one run, and
independent of grouping, filters and the Workbook's top 10. It does not survive into a
different run; nothing claims it does. The export carries both `ref` and `item`
(the real id) on every answer, so an email quoting `D12` and a JSON file both map back
to the run. The "How to reply" block tells a no-JS reader to quote the reference.

### Escaping and safety

Everything user-controlled still goes through `summary.esc`. Text inside the JSON data
block (if one is used) must be JSON-encoded **and** have `</` escaped as `<\/` so a
quote can't close the script element. The JS sets `textContent`, never `innerHTML`,
for anything from the run.

## Where code changes

- `src/rubrica/target_brief.py` (reader):
  - `Dispute`: drop `taken`, add `chosen`, `topic_id`, `topic_label`, and
    `headline` (rule 1, or `""`).
  - new `topics(run)`: subject id → trimmed label; and the contradiction→subject map
    from `01-contradictions/`.
  - `OpenQuestion`: add `topic_id`.
  - new `quick_takes(run)`, returning dataclasses (kind, file or topic, counts, item
    ids), with no prose; the renderer owns sentences.
  - new `workbook_order(...)`, the deterministic 10.
  - capability grouping helper (id segment).
- `src/rubrica/target_brief_html.py` (renderer): the two sections, cards, quick takes,
  inline `<script>`, print CSS. `_taken`-related strings go.
- `src/rubrica/cli.py`: no interface change. `rubrica target-brief --run R [-o P]`.
- Docs: `docs/reference/cli.md` §`rubrica target-brief`; the CLAUDE.md `target-brief`
  paragraph; `docs/design/limitations.md` (remove the entry);
  `docs/reference/artifacts.md` if it describes the page's sections. Run
  `tests/unit/test_docs_accuracy.py`.

## Testing

- Keep: the vocabulary, identifier, escaping, lone-surrogate, severity, marker and
  banner tests. Re-point them at the new layout where they assert positions. The
  vocabulary, identifier and run-directory tests move to the visible-text helper
  (see "Anti-goals"), measured both ways.
- Change: the no-script test (above); the bullet test (rule 2 above); the `taken`
  tests (badge).
- Add, measured both directions per CLAUDE.md:
  - a same-file disagreement renders the badge on the chosen side only (and on neither
    side when unresolved);
  - the Report contains no answer control and no open-count text (scope the assertion
    to the Report `<section>`, not the page);
  - the Workbook's first block holds exactly `min(10, n)` items, in the documented
    order, on a fixture built to make the order observable;
  - quick-take thresholds fire and stay silent on constructed fixtures (a file losing
    5 of 6 fires; 4 of 6 doesn't; one losing 4 of 4 doesn't);
  - grouping falls back to one group, with a marker, when `01-subjects.json` is
    unreadable;
  - no-JS: strip the script; all content ids present;
  - determinism: two renders are byte-identical;
  - the JSON data block (if used) survives a quote containing `</script>`.
- The toy run has one contradiction and no gaps, so it cannot reach most of this.
  Tests build fixtures by editing a toy run's world model and parts in `tmp_path`, as
  existing tests already do. Do not edit `tests/fixtures/toy/`.
- Manual check: render `run-20261103-172151` and open it in a browser, with JS on and
  JS off, and print to PDF.

## Left to the builder

The visual design (colours, spacing, tab style) within the existing `_CSS` token
system; whether a JSON data block is used at all; the exact copy of chrome sentences,
within the vocabulary rules; table vs relaxed-test for quick takes.
