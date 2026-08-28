# `target-brief`: tables, a theme, and colour that encodes only what was recorded

## Why

`target-brief` renders correctly and reads badly. Measured on
`run-20260826-090456`, one page carries 39 `<li>` groups in "What we read", 123
`<li>` across 41 disagreements (each with two nested source lists), 18 `<li>`
questions and 71 `<dt>`/`<dd>` pairs in the collapsed description. Every one of
those is a bullet, and the recipient's job is to *compare* — one side of a
disagreement against the other, one operation's sources against the next. A
bullet list is the wrong shape for a comparison: nothing lines up, so the reader
holds the columns in their head.

The reader is the target's owner, reading under no obligation, deciding whether
to reply. Comprehension is not a nicety here — it is the whole mechanism by
which this document earns a correction.

`run-summary` already uses tables and coloured cells. This page is the outlier.

## What changes

Three things, in one renderer: `src/rubrica/target_brief_html.py`.

1. **Every populated section becomes a table** with a real header row.
2. **A theme**, with explicit light and dark palettes.
3. **Colour**, encoding recorded status and kind — never invented severity.

`src/rubrica/target_brief.py` is untouched. It already computes every field the
new markup needs, and the compute/render split is what keeps a section from
disagreeing with the numbers beside it.

## The colour ruling, which is the load-bearing decision

**Colour may encode only a field the run recorded, whose value varies across
rows.** No severity, no priority, no ranking.

This is not caution for its own sake; the module already measured it. The
`Provenance` docstring records that badging each element with `derivation` or
`confidence` was built and dropped, because both come out identical on every row
— all 39 parsec capabilities `high`, all 39 `stated` — and:

> A badge that never varies is not neutral in a document someone is asked to
> ratify: it implies a distinction was checked.

`disputes()` refuses to rank by blast radius for the same reason: it is "the one
piece of genuinely new analysis in this design and shipping it unmeasured is how
a report starts asserting a judgment it did not earn."

A severity ramp we assigned would be exactly that judgment, in colour, on a page
whose only claim to authority is that every statement on it came from the
owner's own documents. So the palette carries these four, all recorded, all
measured to vary:

| Visual | Encodes | Recorded in | Varies (run-20260826-090456) |
|---|---|---|---|
| Amber chip, "Undecided — your word settles it" | `resolution == "unresolved"` | `contradictions[].resolution` | 15 of 41 |
| Blue chip, "We went with *file*" | `preferred_a` / `preferred_b` | same | 25 of 41 |
| Grey chip, "Both treated as possible" | `both_possible` | same | 1 of 41 |
| Amber accent on a detail row | `provenance.disputed` | claim overlap with a contradiction | 6 of 39 operations, 4 of 30 entities |
| Outline chip, "One source only" | `len(provenance.files) == 1` | resolved claim refs | 28 of 30 entities, 4 of 39 operations |
| Categorical hue per source kind | `kind` | `_KIND_LABELS`, seven schema values | 4 kinds present |

Every figure above was measured on `run-20260826-090456` through the helpers
that render them, not reasoned from the artifacts.

Source kind is a *category*, so its seven hues must read as a set of unordered
labels and never as a ramp — no light-to-dark progression that would imply one
kind outranks another.

**Colour is never the only carrier.** Every chip prints its word inside itself.
The page is emailed, printed, forwarded into clients that strip CSS, and read by
people who do not distinguish the hues. A chip whose meaning lives in its
background is a chip that loses its meaning in transit.

**`gaps[].blocks` stays off the page.** It is the one field that would look like
a severity axis — it names what a gap blocks — and its values are pipeline stage
names (`propose`, `instantiate`, `score`), which the page's own prose may never
carry.

## Section by section

`#` below is the row's position in its own table, 1-based. It is not any
recorded id: `Dispute.id` and `OpenQuestion.subject` are the run's own strings,
and the existing rulings keep the first off the page entirely and label the
second as ours.

| Section | Columns | Notes |
|---|---|---|
| What we most need from you | Rank · What we need · Where it is | Three rows. Replaces the static sentence; the sentence's ranking becomes the table's order, which is what `_reply()` already refers back to. |
| What we read | What kind · Where · The files | Kind cell carries the kind chip. The conditional "(read as N pieces)" stays in the *Where* cell, attached to the group it counts, per the existing ruling that two counts appear only when they differ. Uncapped, per `_group_a`'s ruling. |
| Where our sources disagree | **Index:** # · Status · Files involved. **Then per dispute:** an `<h3>` carrying the number and the status chip, the verbatim `nature` in a paragraph beneath it, a Side · Source · What it says table, and the decision sentence. | The index is the new affordance: 41 disputes are unscannable today. Detail stays because the two verbatim quotes are what let an owner settle it, and they cannot be shortened. **Amended during implementation, measured:** this specified a fourth index column, `What kind of disagreement`, carrying `nature`, and an `<h3>` carrying `nature` inline. Across the 41 disputes on run-20260826-090456 `nature` runs 14 characters at its shortest, 305 at the median and 780 at its longest, with 38 of 41 over 200 — so that shape put a multi-hundred-character paragraph inside 38 of 41 headings and made the index column a wall of the same paragraphs, destroying the one thing an index is for. Only `count_mismatch` and `incompatible_precondition` are the short tokens this spec assumed. The files stay as the index's handle: an owner recognises a filename in their own tree, which a 305-character median does not give them. Truncating `nature` into the index was rejected — an excerpt of a 780-character paragraph can invert its meaning, and this page may not rewrite selected prose. |
| What we could not tell | # · The question · Our reference | Question leads, our label trails, per `_group_d`'s measured ruling. |
| What it can do | Operation · Called as · Takes · What can come back · Where we read it | One row per operation; outcomes stack as labelled lines inside their cell. |
| What data it holds | What it is · Held as · Fields · Rules and relations · Where we read it | |
| Who uses it | Who · What they are trying to do · Where we read it | |

### Rejected: `rowspan` for outcomes

One row per outcome with the operation cell spanning them reads better as a grid
and was rejected anyway: 39 operations carry 195 outcomes on this run, several
carry none, and a spanning cell over an empty set is a rendering branch whose
edge case is invisible until an owner meets it. Stacked labelled lines in one
cell lose a little alignment and no correctness.

## Theme

**No webfonts, and still no JavaScript.** Both for the reason the module already
gives: the page is opened in a mail client's browser view, behind a corporate
proxy, with scripts off. A downloaded face is one more thing that fails to
arrive. "Nicer" comes from the type scale, spacing, rules and colour.

- Palettes as custom properties on `:root`, redefined under
  `@media (prefers-color-scheme: dark)`. Explicit `--bg` and `--fg` rather than
  today's bare `color-scheme: light dark`: once chips have backgrounds, the UA
  default is no longer a background the contrast was checked against.
- Measure widens from 46rem to about 70rem, because the grids need it. The
  existing comment says the wide measure exists because the page "is read as
  prose"; it is now read as prose *and* scanned as tables, which is a change to
  record rather than an argument to overturn.
- Each table sits in an `overflow-x: auto` wrapper, so a narrow screen scrolls
  one table and never the page.
- Zebra rows, a shaded header row, hairline rules, monospace kept for filenames,
  identifiers and verbatim quotes.
- A `@media print` block: chips keep their border and their word when the
  background does not print.

## What must not break

Six properties, each already guarded by a test that must stay green:

1. No JavaScript, anywhere.
2. This module's own prose names no stage, no gate, no artifact and not
   rubrica. Prose *selected* from the run still ships verbatim, ids and all.
3. Selected prose is relabelled, never rewritten. Markup may change around a
   sentence; the sentence may not change.
4. A section whose body is a `Marker` keeps its heading and renders the marker
   sentence — never a table, and never nothing.
5. Everything user-controlled goes through `summary.esc`, including numbers and
   dict keys.
6. An unreadable `01-claims/` still exits **0**, banners the missing citations,
   and describes the target anyway.

## Testing

TDD, and every predicate measured in both directions — blank the prose or flip
the field it claims to check, confirm red, restore, confirm green. The existing
46 test functions in `tests/unit/test_target_brief_html.py` assert no `<li>` or
`<ul>` anywhere, so the suite is not the obstacle it looked like.

New tests:

- Every populated section emits a `<table>` with a `<th>` header row.
- A populated page emits no `<li>` and no `<ul>`. This is the regression guard
  for the whole change, so it is measured against a fixture that reaches every
  section.
- Each resolution value renders its chip class *and* its word, in the same cell.
- An off-enum `resolution` renders as undecided and asserts no decision.
- No severity vocabulary reaches the page: `severity`, `critical`,
  `high priority`, `P1`, `blocker`, and the stage names in `gaps[].blocks`.
- Every `var(--token)` used in `_CSS` is defined in both the light and the dark
  block. A token defined in one is the failure mode a light-mode-only author
  cannot see.
- Marker paths render heading plus sentence and no table.
- An empty section renders its "absent" paragraph and no empty table.

## Documents to update

`tests/unit/test_docs_accuracy.py` gates these:

- `CLAUDE.md`'s `target-brief` paragraph — the "three ranked asks lead"
  sentence stays true, since the asks become a three-row table in the same
  order. Check rather than assume.
- `docs/reference/cli.md`'s `rubrica target-brief` section, same check.

No new subcommand, no new artifact kind, no stage change, so
`docs/concepts/pipeline.md` and `docs/reference/artifacts.md` are untouched.

## Out of scope

- `summary_html.py` and `run-summary.html`, which already use tables.
- `brief.py` and `gate-brief`'s terminal output.
- Any change to what the page *says* — this is a change to how it is laid out
  and coloured, not to what the run believes about the target.
