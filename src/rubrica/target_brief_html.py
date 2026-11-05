"""The markup half of `target-brief`. `target_brief.py` reads and computes.

The same split as `summary.py` / `summary_html.py`, for the same reason: a section
that disagrees with the numbers a human reads beside it is then a defect in one
builder rather than in two spellings of the same read.

Three things this page does differently from `summary_html`, all because it leaves
the project rather than sitting in a run directory:

**One inline script, and a page that reads without it.** This page used to carry no
JavaScript at all, because it is emailed -- opened in a mail client's view, behind a
proxy, with scripts off. The user overturned that on 2026-11-05 so the page can
collect answers, on the condition that it stays one self-contained file. So the
script builds nothing a reader reads: every disagreement, question and table is in
the HTML, both sections render one after the other with scripts off, and the script
only switches tabs, enables and records the answer controls, prints and exports.

**Its own `_CSS`.** Importing `summary_html._CSS` would let a tweak to the operator
page restyle a document already sent to somebody outside the project.

**Its own marker prose.** `summary_html` says `Not present: 01-world-model.json`,
which is right for an operator and meaningless to an owner; here the same fact
reads "We do not have this on file, so this section is empty."

**Nothing a reader can see in this module's own prose names a stage, a gate, an
artifact or rubrica itself,** and
`test_the_pages_own_prose_never_names_a_stage_a_gate_or_an_artifact` plus
`test_page_never_shows_a_rubrica_identifier` fail the suite rather than let one back
in. Both are scoped to *visible* text, by the user's ruling of 2026-11-05: the
answers export needs our ids, so they sit in `data-` attributes and in the script,
and never in a text node. The claim is also about our own chrome and not about the
page as a whole: prose this module *selects* from the run ships as written, ids and
all. That is not tidiness: a recipient asked "does this describe your system?" who
is instead reading about `01-world-model.json` has been handed the wrong question.

One id shape can still reach the page and is accepted rather than suppressed.
`SourceRef.path` falls back to the artifact id when the manifest does not register
the cited artifact, so a side can name `art-notes-md-1` as its source. Suppressing
it would need this module to decide, from a string, whether a path names a real
file -- a second spelling of a rule `target_brief` already rules on, in favour of
naming *something* chaseable over naming nothing. The no-identifier test is
therefore a test about the toy corpus, where every cited artifact is registered,
and not a proof about every run.

Everything user-controlled goes through `summary.esc`, including numbers and dict
keys, for the reason its docstring gives -- a lone surrogate becomes text there,
and it was a report exiting 1 after rendering correctly before it did.
"""

from __future__ import annotations

import hashlib

from rubrica import target_brief
from rubrica.brief import _dicts, _mapping, _quietly
from rubrica.paths import RunPaths
from rubrica.summary import Malformed, Marker, esc

# Wider measure than `summary_html` for the reason it always had -- this is read as
# prose by somebody deciding whether it is true -- and wider again than the 46rem it
# shipped at, because the same reader now scans it as tables. That is a change to
# record rather than an argument against the original: the page is read both ways.
#
# Every colour is a custom property defined twice, once per palette. Explicit `--bg`
# and `--fg` rather than leaning on `color-scheme: light dark` alone: once a chip has
# a background, the UA default is no longer a surface the contrast was checked
# against.
#
# **Everything below this line is page content, comments included.** `_CSS` is
# interpolated into the page's own `<style>`, so a class name or a CSS comment inside
# it is text a page-wide assertion will find -- and most assertions on this page are
# page-wide greps, because what they guard is what a recipient can read. Three
# symptoms of that one property, each measured here rather than reasoned about:
#
#   - a class named `kind-openapi` failed
#     `test_page_relabels_every_input_kind_rather_than_shipping_the_token`, which greps
#     for a bare `openapi` and treats a hyphen as a word boundary; the obvious retry,
#     `kind-http`, failed the no-webfont guard, which cannot tell a class name from the
#     start of a URL. `_KIND_SLUG`'s comment records where that landed.
#   - a comment quoting the disputed chip's wording verbatim, to explain why that chip
#     is exempted from `nowrap`, put the phrase on every page and failed
#     `test_page_relabels_the_kinds_and_flags_the_dispute_in_a_multi_source_line`, whose
#     positive control is that the phrase is *absent* from a page with no disputed
#     element.
#   - a comment naming the tag of the definition list the tables replaced shipped that
#     tag as page text. Green, because no test asserts those tags are gone -- and
#     therefore a trap set for the test that one day does.
#
# So: quote no wording the page carries and no tag the page emits. Describe the shape
# instead. A comment here explaining a rule costs nothing; a comment here quoting the
# thing the rule is about is a false positive somebody else has to debug.
_CSS = """
:root {
  color-scheme: light dark;
  --bg: #fbfaf8; --fg: #1c1c1a; --muted: #5d5c58; --rule: #dedcd6;
  --surface: #f1efe9; --zebra: #f7f6f2; --quote: #f4f3ee;
  --attn-bg: #fdf1da; --attn-fg: #7a4a05; --attn-line: #d59a1f;
  --settled-bg: #e5eef7; --settled-fg: #1f4a70; --settled-line: #6b9dc7;
  --both-bg: #eceae5; --both-fg: #4e4d49; --both-line: #a8a6a0;
  --one-bg: #f6f1f8; --one-fg: #64407c; --one-line: #a97fc0;
  --kind-api: #16645f; --kind-mcp: #6b3f7a; --kind-entity: #74551a;
  --kind-trace: #7a4718; --kind-doc: #2f5d8a; --kind-code: #2c6549;
  --kind-other: #55544f;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #16171a; --fg: #e7e6e2; --muted: #a3a19b; --rule: #33353a;
    /* Opaque, necessarily. This shipped with a 20% alpha byte -- the only alpha value
       in either palette -- and composited over the background it measured 1.02 there
       while --zebra measured 1.07, which put the heading band *below* the striped rows
       and made it the least distinct of the three surfaces, inverting light mode. It
       also cost the reply block its card. Opaque it measures 1.14 against the
       background and 1.06 against --zebra, matching light's 1.10 and 1.06.

       The rejected value is described rather than written: an eight-digit hex here is
       a literal a future palette check would find in the stylesheet it is checking. */
    --surface: #212327; --zebra: #1c1e21; --quote: #1e2024;
    --attn-bg: #3a2c10; --attn-fg: #f0c675; --attn-line: #8a6a20;
    --settled-bg: #17293a; --settled-fg: #9dc4e6; --settled-line: #3d6a94;
    --both-bg: #262825; --both-fg: #b6b4ae; --both-line: #55544f;
    --one-bg: #2a2033; --one-fg: #c9a5e0; --one-line: #6b4a80;
    --kind-api: #5ec4bc; --kind-mcp: #c39ad4; --kind-entity: #d4b869;
    --kind-trace: #e0a06a; --kind-doc: #8ab4dd; --kind-code: #77c79c;
    --kind-other: #a3a19b;
  }
}
body { font: 16px/1.6 system-ui, -apple-system, "Segoe UI", sans-serif;
       margin: 0 auto; max-width: 70rem; padding: 2.5rem 1.5rem 6rem;
       background: var(--bg); color: var(--fg); }
h1 { font-size: 1.7rem; margin-bottom: .2rem; letter-spacing: -.01em; }
h2 { font-size: 1.1rem; margin-top: 3rem; padding-bottom: .35rem;
     border-bottom: 2px solid var(--rule); letter-spacing: .01em; }
h3 { font-size: .98rem; margin: 2rem 0 .4rem; }
p { margin: .6rem 0; max-width: 62rem; }
.lede { font-size: 1.08rem; max-width: 46rem; }
.meta { opacity: .75; font-size: .9rem; margin-top: 0; }
/* The one thing on the page that qualifies the whole page. */
.banner { border-left: 4px solid var(--attn-line); background: var(--attn-bg);
          color: var(--attn-fg); padding: .7rem 1rem; margin: 1.5rem 0;
          font-weight: 600; border-radius: 0 4px 4px 0; }
.absent, .malformed { color: var(--muted); font-style: italic; }
.malformed { border-left: 3px solid var(--attn-line); padding-left: .6rem; }
/* Top level rather than scoped under `.src`, which is where the brief put it:
   `_group_a` and `_data_types` both use `.file` outside a source line, and a
   selector that only matched inside one left every filename in the first section's
   listing of what we read in the body face. `.ident` is the target's own name for
   something that is not a file -- a collection -- and wants the same treatment for
   the same reason: it is a string to copy exactly, not prose to read. */
.file, .ident { font-family: ui-monospace, monospace; font-size: .93em; }
/* Where we read it. Subordinate to the sentence above it, never competing. */
.src { display: block; font-size: .85rem; color: var(--muted); margin-top: .15rem; }
.quote { font-family: ui-monospace, monospace; font-size: .85rem;
         background: var(--quote); padding: .05rem .3rem; border-radius: 3px; }
.legend { font-size: .9rem; color: var(--muted); }
.reply { border: 1px solid var(--rule); border-radius: 6px; padding: 1rem 1.4rem;
         margin-top: 3rem; background: var(--surface); }
details { margin: 1rem 0; border: 1px solid var(--rule); border-radius: 6px;
          padding: .6rem .9rem; }
details summary { cursor: pointer; font-weight: 600; }
/* Each table scrolls inside its own wrapper, so a narrow screen scrolls one
   table and never the whole page. */
.tw { overflow-x: auto; margin: 1rem 0; }
table { border-collapse: collapse; width: 100%; font-size: .93rem; }
th { text-align: left; background: var(--surface); color: var(--fg);
     font-size: .78rem; text-transform: uppercase; letter-spacing: .05em;
     padding: .5rem .6rem; border-bottom: 2px solid var(--rule);
     white-space: nowrap; }
td { padding: .55rem .6rem; border-bottom: 1px solid var(--rule);
     vertical-align: top; }
tbody tr:nth-child(even) { background: var(--zebra); }
.num { color: var(--muted); font-variant-numeric: tabular-nums; }
/* One class per chip, never a shared `chip` class plus a variant: a bare class
   string is what the existing suite asserts on, and a shared prefix would break
   `class="x"` into `class="chip x"` under it. */
.undecided, .settled, .both, .one-source, .disputed,
.kind-api, .kind-mcp, .kind-entity, .kind-trace, .kind-doc, .kind-code,
.kind-other {
  display: inline-block; font-size: .76rem; font-weight: 600;
  padding: .08rem .45rem; border-radius: 999px; border: 1px solid;
  white-space: nowrap; line-height: 1.5;
}
.undecided, .disputed { background: var(--attn-bg); color: var(--attn-fg);
                        border-color: var(--attn-line); }
.settled { background: var(--settled-bg); color: var(--settled-fg);
           border-color: var(--settled-line); }
.both { background: var(--both-bg); color: var(--both-fg);
        border-color: var(--both-line); }
.one-source { background: var(--one-bg); color: var(--one-fg);
              border-color: var(--one-line); }
/* The base rule's `nowrap` is right for a chip carrying one or two words and wrong
   for the one chip whose word is a whole clause of 30 characters. That chip is also
   the only one rendered inside a source line rather than inside a `.tw` wrapper that
   scrolls itself, so an unbreakable run of that length there sets the page's own
   minimum width. Wrapping is the narrow-viewport cost, and it is borne by the chip
   rather than by the whole document.

   Its wording is deliberately not quoted here. This block ships inside the page's
   own `<style>`, and the suite's negative control for that phrase greps the whole
   page: a comment naming it puts it on every page whether the run has a disputed
   element or not, which is exactly the trap `.file`'s comment above already sprang
   by naming the first section's heading. */
.disputed { white-space: normal; }
/* One outcome, relation, rule or goal per line inside its cell. A cell holding
   several of them run together reads as one sentence about the row rather than as
   the several things we recorded separately -- which is the one thing the definition
   list this replaced got right, where it gave each fact a line of its own. Named for
   the shape rather than for any of the four, since all four want it.

   No tag name is quoted in this comment. The stylesheet ships inside the page, so a
   tag written here is markup text a page-wide grep will find, and the tests on this
   page are page-wide greps. */
.oc { margin: .1rem 0; }
.kind-api { color: var(--kind-api); border-color: currentColor; }
.kind-mcp { color: var(--kind-mcp); border-color: currentColor; }
.kind-entity { color: var(--kind-entity); border-color: currentColor; }
.kind-trace { color: var(--kind-trace); border-color: currentColor; }
.kind-doc { color: var(--kind-doc); border-color: currentColor; }
.kind-code { color: var(--kind-code); border-color: currentColor; }
.kind-other { color: var(--kind-other); border-color: currentColor; }
/* Two tabs over two sections. Both sections are visible until the script runs,
   so a reader with scripts off gets the whole page; the script hides one. */
.tabs { display: flex; gap: .4rem; margin: 1rem 0 0; border-bottom: 2px solid var(--rule); }
.tabs a { padding: .4rem .9rem; text-decoration: none; color: var(--muted);
          font-weight: 600; border-bottom: 3px solid transparent; margin-bottom: -2px; }
.tabs a.on { color: var(--fg); border-bottom-color: var(--settled-line); }
.js .nojs { display: none; }
.invite { border: 1px solid var(--settled-line); background: var(--settled-bg);
          color: var(--settled-fg); border-radius: 6px; padding: .8rem 1.1rem;
          margin: 2.5rem 0; }
.invite a { color: inherit; font-weight: 600; }
.ref { font-family: ui-monospace, monospace; font-size: .85em; color: var(--muted);
       margin-right: .3rem; }
.card { border: 1px solid var(--rule); border-left: 4px solid var(--rule);
        border-radius: 6px; padding: .6rem 1rem; margin: 1rem 0; background: var(--bg); }
.card[data-kind="undecided"] { border-left-color: var(--attn-line); }
.card[data-kind="confirm"] { border-left-color: var(--settled-line); }
.card.done { border-left-color: var(--kind-code); }
.card h4 { margin: .2rem 0 .5rem; font-size: .98rem; }
.sides td { width: 50%; }
.side + .side { margin-top: .6rem; padding-top: .6rem; border-top: 1px dashed var(--rule); }
.said { margin-top: .2rem; }
.pick, .maybe { display: inline-block; font-size: .72rem; font-weight: 700;
                text-transform: uppercase; letter-spacing: .05em; padding: .05rem .4rem;
                border-radius: 4px; margin-bottom: .3rem; border: 1px solid; }
.pick { color: var(--settled-fg); background: var(--settled-bg);
        border-color: var(--settled-line); }
.maybe { color: var(--both-fg); background: var(--both-bg); border-color: var(--both-line); }
fieldset.answer { border: 1px solid var(--rule); border-radius: 6px; margin: .6rem 0 .2rem;
                  padding: .4rem .8rem .6rem; display: flex; flex-wrap: wrap; gap: .3rem 1.2rem; }
fieldset.answer legend { font-size: .78rem; color: var(--muted); text-transform: uppercase;
                         letter-spacing: .05em; padding: 0 .3rem; }
fieldset.answer .note { flex-basis: 100%; font-size: .85rem; color: var(--muted); }
fieldset.answer textarea { display: block; width: 100%; box-sizing: border-box;
                           font: inherit; margin-top: .2rem; background: var(--bg);
                           color: var(--fg); border: 1px solid var(--rule); border-radius: 4px; }
.counter { font-weight: 600; white-space: nowrap; }
.actions button, .filters button { font: inherit; font-size: .9rem; padding: .3rem .8rem;
                                   border-radius: 4px; border: 1px solid var(--rule);
                                   background: var(--surface); color: var(--fg); cursor: pointer; }
/* The page is emailed, so it is printed. Backgrounds do not print by default;
   the border and the chip's own word are what survive. Both sections print; the
   controls do not, and an answered card prints the option chosen and the note. */
@media print {
  #report, #workbook { display: block !important; }
  .tabs, .actions, .filters, .nojs { display: none !important; }
  .printing details.untouched { display: none; }
  fieldset.answer label:has(input:not(:checked)) { display: none; }
  fieldset.answer label.note:has(textarea) { display: block; }
  fieldset.answer input { display: none; }
  body { max-width: none; background: #fff; color: #000; }
  .tw { overflow: visible; }
  thead { display: table-header-group; }
  tr { page-break-inside: avoid; }
  .undecided, .settled, .both, .one-source, .disputed,
  .kind-api, .kind-mcp, .kind-entity, .kind-trace, .kind-doc, .kind-code,
  .kind-other { background: transparent; color: inherit;
                border-color: currentColor; }
}
"""

# One rendering of "we looked and no document said", emitted at most once per page
# and only when something on the page actually uses one of the two phrasings it
# glosses. A legend for words the page does not use is noise on a document somebody
# is asked to read closely.
#
# Two phrasings, not one. `_NOT_ADDRESSED` is our own label, and the draft legend
# glossed only that -- but the idiom a stage writes into its prose is the one a
# recipient meets far more often. Case-folded on run-20260826-090456's page and binned
# between the page's own headings: `no claim` 122 times against `not addressed` 41, and
# both land overwhelmingly in the collapsed "What we believe, in full" section -- 115
# and 40 respectively, against 7 and 1 in the "What we could not tell" ask. So the
# label is used, and used heavily: it is what fired the earlier version of this legend
# on both real runs. Glossing it alone still left the more common phrasing unexplained,
# and the gloss sat at the head of that collapsed section, below the occurrences
# already standing in the ask above it.
#
# State the fold when quoting those counts. Two reviews of this feature reported 110
# and 117 for the same page because one counted `No claim` capitalised and the other
# did not.
#
# The idiom is matched on `no claim` rather than on a whole sentence because the
# stages write it at least three ways -- "No claim addresses ...", "No claim
# directly addresses ...", "no claim explicitly states this" -- and all three must
# fire it. This is a rendering decision about our own chrome, not absence detection
# over model prose: nothing about the target is inferred from the match, and the
# worst a false positive can do is explain a phrasing that is not there.
_NOT_ADDRESSED = "Not addressed"
_CLAIM_IDIOM = "no claim"
_LEGEND = (
    '<p class="legend">Two phrasings below are ours, not statements about your '
    "system. Where a line says that no claim addresses something — directly "
    "addresses it, or explicitly states it — we mean we found nothing in the "
    "documents you gave us that settled the point; a “claim” is one statement we "
    "recorded while reading them. An outcome labelled “Not addressed” says the same "
    "thing. Neither means the behaviour is missing from your system.</p>"
)

# `kind` -> the words an owner reads, for all seven values of the schema's shared
# `$defs/kind` enum (`catalogue-0.1.json`, `triage-0.1.json` and `manifest-0.1.json`
# each spell the same seven). All seven rather than the ones runs have produced,
# because the table is what stops a token shipping and a kind nobody has seen yet
# is exactly the one nobody would notice shipping raw.
#
# Read through `.get(kind, kind)`, for `_OUTCOME_LABELS`' reason: an off-schema
# kind ships as its own token rather than as a label we invented for it.
#
# No label names the format the way the enum does -- "HTTP API description" rather
# than "OpenAPI", "Recorded interactions" rather than "trace" -- because the
# recipient is being asked whether we read the right things about their system, and
# the kinds are our filing categories over their files.
_KIND_LABELS = {
    "openapi": "HTTP API description",
    "mcp_tool_schema": "MCP tool definitions",
    "entity_schema": "Data model definitions",
    "trace": "Recorded interactions",
    "design_doc": "Written documentation",
    "source_code": "Source code",
    "other": "Other material",
}

# The sentence that stands in for a section's body when the run-level banner has
# already stated the fact. Five sections carry the identical marker when one file
# is unreadable -- `disputes`, `open_questions`, `operations`, `data_types` and
# `personas` all return whatever `_world` returned, and nothing else -- so
# rendering the whole sentence five times tells the owner five times that one thing
# is missing. The heading and a line stay, which is the guarantee that matters: a
# section that disappears is indistinguishable from one this renderer forgot.
_SEE_BANNER = "see the note at the top of this page"


def _kind(kind: str) -> str:
    """One input kind in the owner's vocabulary, or its own token if we have none."""
    return _KIND_LABELS.get(kind, kind)


# `kind` -> the CSS class carrying that kind's hue. Seven, matching `_KIND_LABELS`,
# and an off-schema kind falls to `kind-other` while `_kind` still ships its own
# token as the word: an unknown kind gets a neutral colour and its real name, never
# a colour we invented a meaning for.
#
# These are unordered categories, so the hues are seven distinct families and not a
# light-to-dark ramp. A ramp would say one kind outranks another, which is a claim
# the run does not make.
#
# `openapi` is the one slug that is not its own key shortened, and both reasons are
# measured rather than aesthetic. A slug spelled `kind-openapi` puts that enum token
# into the `<style>` block of every page regardless of what the run read, which
# `test_page_relabels_every_input_kind_rather_than_shipping_the_token` fails on --
# it greps the whole page for a bare `openapi`, and a hyphen is a word boundary. The
# obvious second try, `kind-http`, fails the no-webfont guard for the same structural
# reason: that one asserts no `http` anywhere in the stylesheet, and it cannot tell a
# class name from the start of a URL. So the slug follows `_KIND_LABELS`, which
# already refuses to name the format the way the enum does, and lands on the words
# the owner actually reads.
_KIND_SLUG = {
    "openapi": "kind-api",
    "mcp_tool_schema": "kind-mcp",
    "entity_schema": "kind-entity",
    "trace": "kind-trace",
    "design_doc": "kind-doc",
    "source_code": "kind-code",
    "other": "kind-other",
}

# `resolution` -> (CSS class, the word the chip carries).
#
# Amber for `unresolved` because it is the only one of the four an owner can act on,
# and this page exists to be acted on. Blue for the two `preferred_*` and grey for
# `both_possible`: both are decisions we already took, so they report rather than
# ask.
#
# Read through `.get(resolution, _STATUS_CHIP["unresolved"])`. An off-enum value is
# undecided, never a decision: `target_brief._chosen` returns `None` and
# `target_brief.kind_of` returns "undecided" for anything outside the values they
# know, so the chip, the badge and the controls agree without consulting each other.
#
# Kept for the colour variants; the words a card shows are `_ASK`'s.
_STATUS_CHIP = {
    "unresolved": ("undecided", "Undecided"),
    "preferred_a": ("settled", "Side chosen"),
    "preferred_b": ("settled", "Side chosen"),
    "both_possible": ("both", "Both possible"),
}


def _chip(variant: str, word: str) -> str:
    """A coloured chip that always carries its word.

    One class, not a shared `chip` class plus a variant, for the reason `_CSS`
    gives: the suite asserts on bare `class="x"` strings and a shared prefix would
    break them.

    The word is not optional and there is no branch that omits it. Colour is never
    the only carrier of meaning here -- this page is emailed, printed, and forwarded
    into clients that strip CSS, and a chip whose meaning lives in its background is
    a chip that loses its meaning in transit.
    """
    return f'<span class="{variant}">{esc(word)}</span>'


def _kind_chip(kind: str) -> str:
    """One input kind as a chip, in the owner's vocabulary."""
    return _chip(_KIND_SLUG.get(kind, "kind-other"), _kind(kind))


# No cell on this page is ever empty, and which of the two forms an empty value takes
# is decided per column rather than per module. Both forms are in use on purpose, and
# the difference between analogous-looking columns is this rule rather than drift:
#
#   - a **sentence** where the empty set is itself a recorded fact about the target
#     rather than a hole in our record ("Takes no parameters." -- an operation with no
#     parameters genuinely takes none, which is a statement an owner can correct), or
#     where every filled cell in that column is prose, so a lone dash among them reads
#     as a render that broke. That covers the two in "What it can do" and the one in
#     "Who uses it".
#   - a **dash** where the column's filled cells are names, types and short labelled
#     lines a reader scans rather than reads -- three such slots in "What data it
#     holds" alone, plus the handle and the directory. A sentence set among identifiers
#     is read as one of them; a dash cannot be.
#
# Unifying either way would mean dashing a column whose neighbours are all sentences,
# or writing a sentence into a column of identifiers. Neither is an improvement, so
# the split stands and is recorded here instead.
def _row(*cells: str) -> str:
    """One table row from cell contents that are already escaped or already markup.

    Deliberately not escaping: every caller passes either markup it built (a chip, a
    `.file` span) or a string it has already put through `esc`. A second escape here
    would double-encode every filename on the page, and the alternative -- escaping
    here and not at the call site -- would mean no cell could contain markup.
    """
    return "<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>"


def _table(headers: tuple[str, ...], rows: list[str]) -> str:
    """One table, in a wrapper that scrolls it rather than the page.

    Returns `""` for no rows rather than an empty table, so that no caller can ship
    a header row with nothing under it: a table with headings and no body reads as a
    render that broke, which is the same failure the five "absent" sentences in this
    module exist to avoid. Every caller already has a sentence for its empty case
    and must keep using it.
    """
    if not rows:
        return ""
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    return (
        f'<div class="tw"><table><thead><tr>{head}</tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def _marker(body: Marker, terse: bool) -> str:
    """A marker in the recipient's terms.

    The artifact name is dropped deliberately: an owner cannot act on
    `01-world-model.json`, and the operator page beside this one already names it.
    The two markers stay two sentences for `summary_html._marker`'s reason -- one
    is something we do not have, the other something we have and could not read back
    -- because spelling both the same way is what let one page say a stage had
    produced an artifact and that the artifact was not there.

    Neither sentence says how far the work has got. The draft's did ("we have not got
    far enough"), and it was measured on a run root at mode 000, where the run may
    well be finished and merely unreadable: the page cannot tell the difference, so it
    states what it has on file, which is the thing it does know. "Yet" was also the
    entire difference between the two terse markers, so dropping it from one obliged
    rewording that one rather than leaving the pair a word apart.

    `terse` is only ever True for a section whose marker is the one the page banner
    above it states, which is the five world-model-backed sections and no others.
    `What we read` reads a different file, so its marker is a second fact and says
    the whole thing where it stands -- pointing it at a banner about the
    description would misattribute one absence to another.
    """
    if isinstance(body, Malformed):
        if terse:
            return f'<p class="malformed">Nothing to show here — {_SEE_BANNER}.</p>'
        return (
            '<p class="malformed">We have this on file but could not read it back, '
            "so this section is incomplete.</p>"
        )
    if terse:
        return f'<p class="absent">Nothing on file here — {_SEE_BANNER}.</p>'
    return '<p class="absent">We do not have this on file, so this section is empty.</p>'


def _body(body, terse: bool) -> str:
    """A section's body, with a marker rendered rather than skipped."""
    return _marker(body, terse) if isinstance(body, Marker) else body


def _section(heading: str, body, terse: bool = False, lead: str = "") -> str:
    """One tier-1 section, its heading always present.

    `lead` goes between the heading and the body rather than being prepended to the
    body by the caller, because a body may be a `Marker` and only `_body` may decide
    how one renders. It is what lets `_LEGEND` be the first thing read under a
    heading whose lines need it, without the legend becoming part of the group.
    """
    opening = f"<h2>{esc(heading)}</h2>\n"
    return opening + (f"{lead}\n" if lead else "") + f"{_body(body, terse)}\n"


def _needs_legend(*bodies) -> bool:
    """Whether anything rendered on this page uses a phrasing `_LEGEND` glosses.

    Every body the page will show, tier 1 and tier 2 together, rather than the one
    section the legend sits in: the label lives in "What it can do" and the idiom in
    both asks and detail, and a reader who meets either anywhere has met the words
    the legend exists for. A body can be a `Marker`, so this reads `str()` of each
    rather than assuming HTML -- an unreadable section cannot carry the phrasing, and
    stringifying it is how that stays true without a type test here.
    """
    text = " ".join(str(body) for body in bodies).lower()
    return _NOT_ADDRESSED.lower() in text or _CLAIM_IDIOM in text


def _collapsed(heading: str, body, terse: bool = False) -> str:
    """One tier-2 section, collapsed, with the disclosure control as its heading.

    No `<h2>` inside the `<details>`: the `<summary>` already prints the heading,
    and a section that carries both prints its own name twice to a reader. The
    heading is still there for `test_page_renders_every_group_and_every_tier_two_section`
    to find, and a marker still renders rather than the section disappearing --
    which is the whole point of routing a body through `_body` rather than
    interpolating it.
    """
    return f"<details><summary>{esc(heading)}</summary>\n{_body(body, terse)}\n</details>"


def _file_spans(files) -> str:
    """A comma-separated run of filenames, each in the monospace face.

    One helper for the three sites that build this -- the source sentence under a
    statement, one group's file listing, and the disagreement index's cell naming the
    files two sides came from. All three were the same expression character for
    character, and holding the `esc` in one place is the point of folding them: a
    filename is the one string on this page a reader is meant to copy exactly.

    Callers own everything around the run. `_files_html` appends its own "and N more
    we could not name" tail, which is why the count and the join stay separate: the
    tail is that group's arithmetic against the run's record and not another name.
    """
    return ", ".join(f'<span class="file">{esc(f)}</span>' for f in files)


def _provenance(prov) -> str:
    """Where we read it: the files and their kinds, as one sentence.

    Whether they disagreed used to be a clause appended here, and is now `_where`'s,
    which wraps this: once the three detail sections became tables the fact reads
    better stated once, as a chip, at the head of the cell a reader scans for it.

    Still one sentence rather than columns of its own, and the original reason holds
    in the cell it now sits in: the statement is what the recipient is being asked
    about and the source is how they check it, so it stays subordinate to the
    statement rather than ranged against it. `single_source` is read from the property
    rather than recomputed here -- Task 2 made it a property precisely so no caller
    can disagree with `files`.

    Kinds go through `_kind`: unrelabelled, the toy alone puts `design_doc` and
    `mcp_tool_schema` on the page, which is the machine vocabulary this document
    exists to avoid.
    """
    if not prov.files:
        # Stated, not silent. Measured with `01-claims/` *removed* rather than
        # unreadable -- `paths.list_dir` returns `[]` for a missing directory, so
        # `source_index` returns `{}` and no banner fires -- this rendered five
        # blank `<dd></dd>` rows, and read alone a blank provenance asserts to the
        # owner that no document of theirs states the sentence above it. That is
        # what `target_brief._refs`' docstring argues is intolerable.
        #
        # The prose is safe in both directions because `world-model-0.1.json`'s
        # `$defs/claim_refs` is `minItems: 1`: a conforming element always cites at
        # least one claim, so an empty `files` can only ever mean we failed to
        # resolve them and never that the element legitimately rests on nothing.
        # No pointer to the page banner either -- on the path that produces this,
        # there is no banner to point at.
        return '<span class="src">We could not work out which of your files this came from.</span>'
    files = _file_spans(prov.files)
    if prov.single_source:
        text = f"From {files}"
    else:
        kinds = ", ".join(esc(_kind(k)) for k in prov.kinds)
        text = f"From {esc(len(prov.files))} sources ({kinds}): {files}"
    return f'<span class="src">{text}.</span>'


def _where(prov) -> str:
    """The "Where we read it" cell: the chips this element earns, then the sentence.

    Two chips, both recorded and both measured to vary on run-20260826-090456 through
    these same helpers -- single-source is 28 of 30 entities and 4 of 39 operations,
    disputed is 4 of 30 and 6 of 39. That is the whole test for whether something may
    be coloured here: `Provenance`'s docstring records that `derivation` and
    `confidence` were built as badges and dropped because both come out identical on
    every row, and that a badge which never varies "implies a distinction was
    checked".

    The disputed chip carries the full phrase `our sources disagree about this` rather
    than a shorter word, because the suite pins that phrase and it is the clause
    `_provenance` used to append. Stating it once, as a chip, is the same fact in the
    place a reader scans for it.
    """
    chips = []
    # `prov.files and prov.single_source`: with no files at all, `_provenance` already
    # says it could not work out where the element came from, and a "One source only"
    # chip above that sentence would contradict it.
    if prov.files and prov.single_source:
        chips.append(_chip("one-source", "One source only"))
    if prov.disputed:
        chips.append(_chip("disputed", "our sources disagree about this"))
    return "".join(chips) + _provenance(prov)


def _files_html(files) -> str:
    """One group's filenames, with the ones we could not name counted rather than
    printed.

    `inputs_read` keeps a record whose `source_path` and `artifact_id` are both
    unreadable, on purpose: `len(files) + slices` is that group's arithmetic against
    the run's own record of what it read, and dropping the record makes the count
    disagree with the listing silently. Task 3 measured exactly one such blank row
    on a real run. So it is counted here -- an empty monospace span in a comma list
    renders as stray punctuation, and the count is the honest form of the same fact.

    `.strip()` rather than `target_brief._file_and_piece`, which is the nameability
    rule the disagreement section asks: measured over every shape that reaches this
    listing the two agree, because `inputs_read` has already dropped any piece it
    could name a file for, and routing a bare filename back through a rule about
    container-plus-pointer paths would judge `x#/1` on `x` while printing `x#/1`.
    """
    named = [f for f in files if f.strip()]
    missing = len(files) - len(named)
    shown = _file_spans(named)
    if not missing:
        return shown
    tail = (
        f"{esc(missing)} more we could not name" if shown else f"{esc(missing)} we could not name"
    )
    return f"{shown} and {tail}" if shown else tail


def _group_a(run: RunPaths):
    """What we read. The first ask, because it is the one an owner can answer
    without reading anything else: a file they know we should have had and did not
    is a correction that invalidates everything below it.

    The full listing, uncapped, and that is a judgment rather than an oversight:
    Task 3 measured parsec's run as 39 groups over 199 files, which renders as a
    wall. It stays whole because this section's ask is "what did we miss", and a
    truncated listing cannot be answered -- the file the owner would have named is
    the one most likely to be behind the "and 24 more". The count sentence above the
    list is what gives a reader the size before they wade into it.
    """
    groups = target_brief.inputs_read(run)
    if isinstance(groups, Marker):
        return groups
    if not groups:
        return '<p class="absent">We have no record of what we read.</p>'
    rows = []
    for group in groups:
        # Conditional: every toy group has `directory == ""` -- the three inputs
        # share their whole directory, so nothing survives the prefix strip -- and
        # unconditionally this printed `... under : notes.md` with an empty span.
        #
        # The leading space is load-bearing: the suite pins
        # `' under <span class="file">docs</span>'` with it, and inside a `<td>` it
        # is invisible.
        #
        # The dash is the stated absence this module owes every empty value -- the
        # bullet form could hide it by simply omitting a clause, a table cell cannot
        # -- and it says the right thing: no directory means the group's files sit at
        # the root of what we read, not that we failed to work out where they are.
        where = (
            f' under <span class="file">{esc(group.directory)}</span>' if group.directory else "—"
        )
        # The slice count is why "we read 269 things" and "we read 199 files" are
        # both true: 71 of parsec's inputs are `#/NN` slices of one capture. It sits
        # in the `Where` cell rather than becoming a column of its own, because a
        # column would print a number for every group and the ruling below is that
        # two counts appear only when they differ.
        tail = f" (read as {esc(len(group.files) + group.slices)} pieces)" if group.slices else ""
        rows.append(_row(_kind_chip(group.kind), f"{where}{tail}", _files_html(group.files)))
    files = sum(len(group.files) for group in groups)
    pieces = sum(len(group.files) + group.slices for group in groups)
    # Two counts only when they differ, because "199 files, read as 269 pieces" is
    # a fact about how the run split a capture and "3 files, read as 3 pieces" is
    # arithmetic the reader did not ask for.
    read_as = f", read as {esc(pieces)} separate pieces" if pieces != files else ""
    return (
        f"<p>We built this description by reading {esc(files)} "
        f"file{'' if files == 1 else 's'} of yours{read_as}. "
        "<strong>If something important is not here, tell us — that is the most "
        "useful correction you can give us.</strong></p>"
        + _table(("What kind", "Where", "The files"), rows)
    )


def _status_chip(resolution: str) -> str:
    """One dispute's status, as a chip, in the Workbook only.

    Anything outside the three values `_STATUS_CHIP` knows reads as undecided, which
    is what `target_brief.kind_of` and `target_brief._chosen` independently do with
    the same field: the chip, the controls and the badge all default to "we did not
    decide" rather than consulting each other.
    """
    variant, word = _STATUS_CHIP.get(resolution, _STATUS_CHIP["unresolved"])
    return _chip(variant, word)


def _side_cell(refs) -> str:
    """One side of a disagreement as one cell: each source, where in it, and what it
    says.

    Was `_side_rows`, which emitted a row per source under a "One side" / "The other
    side" label. A card shows the two sides as two columns instead, so the side a
    reader compares against is beside it rather than below it, and the column, not a
    sentence, is what the "our pick" badge marks -- the fix for the "We went with X"
    limitation.

    Every absence is stated, never blank, for `_side_rows`' reasons, which still
    hold: a side that resolves to no source says so, a path with nothing nameable in
    it is "a file we could not name" (`_files_html`'s phrase), and a missing quote
    is "we did not record the wording".

    A sliced input's piece is separated from its file and labelled: measured on
    run-20260816-172810, `trajectories2.json#/10 (at /data/spans/5/...)` read as
    one path. Which part is the file is `target_brief._file_and_piece`'s ruling.
    """
    if not refs:
        return '<div class="src">we could not resolve which file states it</div>'
    out = []
    for ref in refs:
        base, piece = target_brief._file_and_piece(ref.path)
        where = f'<span class="file">{esc(base)}</span>' if base else "a file we could not name"
        inside = []
        if piece:
            inside.append(f"piece {esc(piece)}")
        if ref.locator:
            inside.append(f"at {esc(ref.locator)}")
        if inside:
            where += f" ({', '.join(inside)})"
        said = (
            f'<span class="quote">“{esc(ref.quote)}”</span>'
            if ref.quote
            else '<span class="src">we did not record the wording</span>'
        )
        out.append(f'<div class="side">{where}<div class="said">{said}</div></div>')
    return "".join(out)


def _files_label(refs) -> str:
    """The files one side names, for a card's heading."""
    files = sorted(target_brief.side_files(refs))
    return ", ".join(files) if files else "a source we could not name"


def _card_title(dispute) -> str:
    """A card's heading: its reference, then the selected first sentence when there
    is one, else facts we compose -- the topic and the two sides' files. Never a
    paraphrase: `Dispute.headline` is `nature`'s own first sentence or nothing."""
    if dispute.headline:
        text = esc(dispute.headline)
    else:
        a, b = _files_label(dispute.side_a), _files_label(dispute.side_b)
        files = esc(a) if a == b else f"{esc(a)} and {esc(b)}"
        text = f"{esc(dispute.topic_label)} — {files}" if dispute.topic_label else files
    return f'<span class="ref">{esc(dispute.ref)}</span> {text}'


# `kind` -> the answer choices a card offers, as (token, label). The tokens are
# the export format's and are fixed (spec, "Answers"); left is always `claim_a` and
# right always `claim_b`, so the columns are never swapped anywhere on the page.
_CHOICES = {
    "undecided": (
        ("left", "The left is right"),
        ("right", "The right is right"),
        ("both", "Both, in different cases"),
        ("neither", "Neither"),
    ),
    "confirm": (
        ("yes", "Yes, our pick is right"),
        ("no_other", "No, the other side is"),
        ("neither", "Neither"),
    ),
    "both": (
        ("yes", "Yes, both hold"),
        ("only_left", "No, only the left"),
        ("only_right", "No, only the right"),
    ),
    "question": (("dont_know", "I don't know either"),),
}

# What each kind asks, as the card's chip. Workbook only: the Report never shows
# what is outstanding, because a reader who only came for the findings must never be
# handed a to-do list (spec, "Anti-goals").
_ASK = {
    "undecided": ("undecided", "We could not decide"),
    "confirm": ("settled", "Please confirm our pick"),
    "both": ("both", "Both readings may hold"),
    "question": ("both", "Open question"),
}


def _answer(item_id: str, kind: str, text: bool) -> str:
    """The answer controls for one item. Disabled until the script enables them, so
    a reader with scripts off is not offered controls that record nothing -- the
    note above the Workbook tells them to reply quoting the reference instead.

    `name` is the item id, escaped for an attribute: an id is ours and never
    visible, and `esc` quotes `"` and `&` for exactly this position.
    """
    name = esc(item_id)
    radios = "".join(
        f'<label><input type="radio" name="{name}" value="{token}" disabled> {esc(label)}</label>'
        for token, label in _CHOICES[kind]
    )
    box = "Your answer" if text else "A note (optional)"
    return (
        f'<fieldset class="answer"><legend>Your answer</legend>{radios}'
        f'<label class="note">{box}<textarea data-note rows="2" disabled></textarea></label>'
        "</fieldset>"
    )


def _dispute_card(dispute, answerable: bool) -> str:
    """One disagreement: heading, the two sides side by side, our reasoning behind a
    disclosure, and -- in the Workbook only -- the controls.

    The badge goes on the column we took. A pair read from one file shows which
    reading won exactly as a pair read from two does, which is what the sentence it
    replaces could not do (spec, "Our pick").
    """
    badge_a = badge_b = ""
    if dispute.chosen == "a":
        badge_a = '<span class="pick">our pick</span> '
    elif dispute.chosen == "b":
        badge_b = '<span class="pick">our pick</span> '
    elif dispute.resolution == "both_possible":
        badge_a = badge_b = '<span class="maybe">both may hold</span> '
    chosen = dispute.side_a if dispute.chosen == "a" else dispute.side_b
    hole = (
        f'<p class="src">{esc(target_brief._UNRESOLVED_SIDE)}</p>'
        if dispute.chosen and not chosen
        else ""
    )
    # `nature` only, never `rationale`. The spec put both here and was wrong to:
    # `Dispute`'s earlier ruling kept `rationale` off this page because it argues in
    # our vocabulary, and the toy's own proves it -- it names claim ids and says "a
    # scenario built on the trace's behaviour would be labelled", which is rubrica
    # talking about itself to a reader who never asked.
    nature = esc(dispute.nature) or "we could not read our own note of what about"
    reasoning = f"<p>The disagreement: {nature}</p>"
    kind = dispute.kind
    variant, word = _ASK[kind]
    chip = _chip(variant, word) if answerable else ""
    return (
        f'<article class="card" data-item="{esc(dispute.id)}" data-ref="{esc(dispute.ref)}" '
        f'data-kind="{esc(kind)}">'
        f"<h4>{_card_title(dispute)} {chip}</h4>"
        '<div class="tw"><table class="sides"><thead><tr><th>Left</th><th>Right</th></tr>'
        f"</thead><tbody><tr><td>{badge_a}{_side_cell(dispute.side_a)}</td>"
        f"<td>{badge_b}{_side_cell(dispute.side_b)}</td></tr></tbody></table></div>"
        f"{hole}"
        f"<details><summary>The disagreement in full</summary>{reasoning}</details>"
        + (_answer(dispute.id, kind, text=False) if answerable else "")
        + "</article>"
    )


def _question_card(q) -> str:
    """One open question, in the Workbook: the question, our reference, an answer box."""
    asked = esc(q.unknown) or "We did not record what it was that we could not tell."
    ref = f' <span class="ident">(our reference: {esc(q.subject)})</span>' if q.subject else ""
    return (
        f'<article class="card" data-item="{esc(q.id)}" data-ref="{esc(q.ref)}" '
        'data-kind="question">'
        f'<h4><span class="ref">{esc(q.ref)}</span> {asked}{ref} {_chip(*_ASK["question"])}</h4>'
        + _answer(q.id, "question", text=True)
        + "</article>"
    )


def _no_disputes() -> str:
    return (
        '<p class="absent">Nothing we read contradicted anything else we read. '
        "That is a weaker statement than it sounds: it means we found no "
        "disagreement, not that your documents agree.</p>"
    )


def _no_questions() -> str:
    return (
        '<p class="absent">We did not record any open question. On a real '
        "target that is more likely to mean we did not notice one than that "
        "none exists.</p>"
    )


def _take_sentence(take) -> str:
    """One quick take as a sentence. These are ours, composed from counts, and the
    section heading says so; each sits beside the disagreements it counts so a
    reader can check it. Hedged ("looks") because a threshold tuned on one run is
    one sample (`target_brief`'s constants record it)."""
    f = f'<span class="file">{esc(take.subject)}</span>'
    if take.kind == "stale":
        return (
            f"<strong>{f} looks out of date.</strong> Of the {esc(take.settled)} "
            "disagreements with other files we could settle, the other file was "
            f"right in {esc(take.lost)}."
        )
    if take.kind == "trusted":
        return (
            f"<strong>{f} looks like your real source of truth.</strong> It was on "
            f"the winning side in {esc(take.won)} of {esc(take.settled)}."
        )
    if take.kind == "self":
        return f"<strong>{f} contradicts itself</strong> in {esc(take.count)} places."
    undecided = f", {esc(take.open)} of them we could not decide" if take.open else ""
    return (
        f"Your files disagree most about <strong>{esc(take.subject)}</strong> "
        f"({esc(take.count)} places{undecided})."
    )


def _takes_html(takes, by_id) -> str:
    """What looks off: one row per take, its examples read-only beneath it."""
    if not takes:
        return "<p>No pattern stood out across your files.</p>"
    rows = []
    for take in takes:
        cards = "".join(_dispute_card(by_id[i], answerable=False) for i in take.examples)
        more = len(take.item_ids) - len(take.examples)
        refs = ", ".join(esc(by_id[i].ref) for i in take.item_ids)
        tail = (
            f'<p class="src">All {esc(len(take.item_ids))} in the workbook: {refs}.</p>'
            if more > 0
            else ""
        )
        # One column, the examples opening under the sentence: measured on
        # run-20261103-172151, a second column for them left each card a quarter of
        # the page wide, and a card is two quotes side by side.
        rows.append(
            _row(
                _take_sentence(take)
                + f'<details class="examples"><summary>Examples ({esc(len(take.examples))})'
                f"</summary>{cards}{tail}</details>"
            )
        )
    return (
        "<p>Patterns we noticed across the places your files disagree. These "
        "sentences are ours, worked out from counts; the examples under each are "
        "what it rests on.</p>" + _table(("What we noticed",), rows)
    )


def _topic_groups(items, heading_of) -> list[tuple[str, list]]:
    """Items by topic, largest group first, then by label; no-topic last."""
    groups: dict[str, list] = {}
    for item in items:
        groups.setdefault(item.topic_id, []).append(item)
    return sorted(
        groups.items(),
        key=lambda kv: (kv[0] == target_brief.NO_TOPIC, -len(kv[1]), heading_of(kv[1][0])),
    )


def _topic_name(item, fallback: str) -> str:
    return item.topic_label or fallback


def _group_d(run: RunPaths, found):
    """What we could not find, in the Report: the questions read-only, grouped by
    topic. No answer box -- the Report asks for nothing.

    The question leads and our label for it trails, which is the reverse of the
    draft. Measured over the 49 questions in the three recordings: `unknown` is a
    self-contained sentence in all 49, while `subject` is a bare slug or an id pair
    in most. The label is kept rather than dropped, and named as ours, because it is
    what a reader would quote back at us -- now beside the visible `Q<n>`, which is
    the handle the reply block asks for.
    """
    if isinstance(found, Marker):
        return found
    if not found:
        return _no_questions()
    blocks = []
    for _, items in _topic_groups(found, lambda q: _topic_name(q, "")):
        rows = []
        for q in items:
            ref = (
                f'<span class="ident">(our reference: {esc(q.subject)})</span>'
                if q.subject
                else "—"
            )
            asked = esc(q.unknown) or "We did not record what it was that we could not tell."
            rows.append(_row(f'<span class="ref">{esc(q.ref)}</span>', asked, ref))
        name = _topic_name(items[0], "Other questions")
        blocks.append(
            f"<details><summary>{esc(name)} ({esc(len(items))})</summary>"
            + _table(("#", "The question", "Our reference"), rows)
            + "</details>"
        )
    return (
        "<p>These are things we could not work out from what we read. They are "
        "questions, not criticisms.</p>" + "".join(blocks)
    )


def _file_index(found) -> str:
    """Every file a disagreement names, with the references that name it -- the
    by-file view over the topic grouping below it (plan, Task 4: one rendering of
    each card, never two)."""
    by_file: dict[str, list[str]] = {}
    for d in found:
        for f in sorted(target_brief.side_files(d.side_a) | target_brief.side_files(d.side_b)):
            by_file.setdefault(f, []).append(d.ref)
    rows = [
        _row(f'<span class="file">{esc(f)}</span>', esc(len(refs)), esc(", ".join(refs)))
        for f, refs in sorted(by_file.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    ]
    return _table(("File", "Disagreements", "References"), rows)


def _workbook(run: RunPaths, found, questions, takes) -> str:
    """The Workbook: the ten answers that help us most, then everything else."""
    disputes = found if isinstance(found, list) else []
    asked = questions if isinstance(questions, list) else []
    order = target_brief.workbook_order(disputes, asked, takes)
    by_id = {d.id: d for d in disputes} | {q.id: q for q in asked}
    first = set(order)
    n = len(order)
    cards = "".join(
        _dispute_card(by_id[i], answerable=True)
        if isinstance(by_id[i], target_brief.Dispute)
        else _question_card(by_id[i])
        for i in order
    )
    if n:
        start = (
            f"<h3>Start here: the {esc(n)} answer{'' if n == 1 else 's'} that help us most</h3>"
            f'<p class="lede">About {esc(max(5, n * 3 // 2))} minutes. Stop whenever you '
            "like; whatever you answer still counts. "
            f'<span class="counter">Answered <span id="wb-count">0</span> / {esc(n)}</span></p>'
            + cards
        )
    else:
        start = "<p>We have nothing to ask you about here.</p>"
    rest_d = [d for d in disputes if d.id not in first]
    rest_q = [q for q in asked if q.id not in first]
    if isinstance(found, Marker):
        rest_disputes = _marker(found, True)
    elif not disputes:
        rest_disputes = _no_disputes()
    elif not rest_d:
        rest_disputes = "<p>Every disagreement is in the ten above.</p>"
    else:
        groups = "".join(
            f'<details class="group"><summary>{esc(_topic_name(items[0], "Other disagreements"))} '
            f"({esc(len(items))})</summary>"
            + "".join(_dispute_card(d, answerable=True) for d in items)
            + "</details>"
            for _, items in _topic_groups(rest_d, lambda d: _topic_name(d, ""))
        )
        chips = "".join(
            f'<button type="button" class="filter" data-filter="{kind}" disabled>'
            f"{esc(_ASK[kind][1])} ({esc(sum(d.kind == kind for d in rest_d))})</button>"
            for kind in ("undecided", "confirm", "both")
        )
        rest_disputes = (
            f'<p class="filters">Show only: {chips} '
            '<button type="button" class="filter" data-filter="" disabled>All</button></p>'
            f"<details><summary>By file</summary>{_file_index(disputes)}</details>" + groups
        )
    if isinstance(questions, Marker):
        rest_questions = _marker(questions, True)
    elif not rest_q:
        rest_questions = (
            "<p>Every open question is in the ten above.</p>" if asked else _no_questions()
        )
    else:
        rest_questions = "".join(_question_card(q) for q in rest_q)
    missed = (
        '<article class="card" data-item="missed-source" data-ref="S1" data-kind="question">'
        '<h4><span class="ref">S1</span> A file we should have read</h4>'
        '<fieldset class="answer"><legend>Your answer</legend><label class="note">'
        "Which file, and why it matters"
        '<textarea data-note rows="2" disabled></textarea></label></fieldset></article>'
    )
    return (
        '<section id="workbook">'
        "<h2>Your answers</h2>"
        '<p class="lede"><strong>Does this accurately describe your system?</strong> '
        "Where it does not, we would rather hear it now than build on it. Your answers "
        "help us build tests that match how your system really behaves.</p>"
        '<p class="nojs">Answering here needs scripts, which are off in this view. You can '
        "still reply by email: quote each item's reference (D12, Q3) with your "
        "answer.</p>"
        '<p class="actions"><button type="button" id="wb-print" disabled>Print or save as PDF'
        '</button> <button type="button" id="wb-download" disabled>Download answers</button></p>'
        + start
        + "<h2>Everything else</h2>"
        "<p>Optional, for anyone who wants to go deeper.</p>"
        f'<details class="group"><summary>Other disagreements ({esc(len(rest_d))})</summary>'
        f"{rest_disputes}</details>"
        f'<details class="group"><summary>Other open questions ({esc(len(rest_q))})</summary>'
        f"{rest_questions}</details>"
        f'<details class="group"><summary>Did we miss a source?</summary>'
        f"{_body(_group_a(run), False)}{missed}</details>" + _reply() + "</section>"
    )


def _operations(run: RunPaths):
    """What it can do. Source order, never re-sorted -- `operations` returns the
    sealed description's own order, which is already reproducible and groups related
    operations the way the pass that wrote them chose to."""
    found = target_brief.operations(run)
    if isinstance(found, Marker):
        return found
    if not found:
        return '<p class="absent">We did not identify anything it can be asked to do.</p>'
    return _operations_table(found)


def _operations_table(found) -> str:
    """One table of operations -- the whole set, or one capability group's."""
    rows = []
    for op in found:
        params = esc(", ".join(op.params)) if op.params else "Takes no parameters."
        outcomes = (
            "".join(
                # A description can be `""` -- Task 5's handoff -- and `label:` with
                # nothing after it reads as prose that got truncated. The label is
                # still a fact about the target, so it stays and the absence is stated.
                f'<div class="oc"><em>{esc(o.label)}</em>'
                + (
                    f": {esc(o.description)}"
                    if o.description
                    else " — we did not record what happens"
                )
                + "</div>"
                for o in op.outcomes
            )
            or "We did not record what can come back."
        )
        # `sentence` (the `operation` string) heads the entry, not `handle`.
        # Measured on the toy world: both capabilities carry
        # `binding.tool == "query_tickets"`, so heading on the handle prints the
        # same word twice and the reader cannot tell which operation is which.
        # `operation` is `query_tickets.find_tickets` and distinguishes them.
        #
        # The handle is shown under it whenever it says something the title does
        # not. Measured, that is both toy operations -- `query_tickets` differs from
        # `query_tickets.find_tickets` -- so the line is the normal case rather than
        # the edge one, and it is worth keeping: the handle is the name the owner's
        # own tooling calls, where the title is ours composed from two fields. It
        # goes only when `operations` has already fallen back to the sentence for
        # want of a `binding.tool`, which is when the two are the same string.
        # `.strip()` on both: `capability.operation` is `minLength: 1`, which admits
        # `" "`, and an unstripped space is truthy -- measured, it shadowed
        # `query_tickets` and headed the entry with a blank `<dt> </dt>` while every
        # other empty field in this module is a stated absence.
        # `target_brief._rules` stripped for this exact hole one module over.
        #
        # The handle is stripped once here rather than tested raw below, because
        # `operations` falls the handle back to the `operation` string when there is
        # no `binding.tool`: with `operation: " "` and no binding, both are `" "`, so
        # the raw test was truthy against a stripped title and the entry shipped
        # `<dt></dt><dd>Called as:  </dd>` -- two blanks in one entry, measured. When
        # nothing in either field is nameable the absence is stated in the heading,
        # and the parameters, outcomes and sources below it still say what the
        # operation does: an unrecorded name is no reason to drop a fact the owner
        # can still recognise the operation by.
        handle = op.handle.strip()
        title = op.sentence.strip() or handle
        # The bare handle, with the label carried by the column heading rather than
        # repeated down 39 rows. `test_page_names_the_handle_under_both_toy_operations`
        # pinned `"Called as: query_tickets<"` twice and now counts
        # `"<td>query_tickets</td>"` instead, which is the same ruling against the new
        # markup -- the handle is shown when it differs from the title, and once when
        # one operation's title has become the handle itself.
        called = esc(handle) if handle and handle != title else "—"
        heading = esc(title) if title else "One operation whose name we did not record"
        rows.append(
            _row(
                f"<strong>{heading}</strong>",
                called,
                params,
                outcomes,
                _where(op.provenance),
            )
        )
    return _table(
        ("Operation", "Called as", "Takes", "What can come back", "Where we read it"), rows
    )


def _data_types(run: RunPaths):
    """What data it holds."""
    found = target_brief.data_types(run)
    if isinstance(found, Marker):
        return found
    if not found:
        return '<p class="absent">We did not identify the kinds of data it holds.</p>'
    rows = []
    for kind in found:
        # Measured `tickets` and `comments` on the toy. This is the one
        # `DataType` field that is the owner's own name rather than ours, so
        # it is the one a reader can confirm or correct outright -- and it is
        # the string that tells them which store we mean when their system has
        # two things called a Ticket.
        held = f'<span class="ident">{esc(kind.collection)}</span>' if kind.collection else "—"
        if kind.fields:
            # The type is parenthesised only when there is one. Measured, an empty
            # `type` rendered `ticket_id ()`, where the sibling outcome path states
            # its absence -- and a bare pair of brackets reads as a rendering fault
            # rather than as something we did not record.
            fields = ", ".join(
                f"{esc(f.name)} ({esc(f.type)})" if f.type.strip() else esc(f.name)
                for f in kind.fields
            )
        else:
            fields = "—"
        # Relations and rules share one column because both are things we believe
        # hold *between* records rather than fields of one, and each keeps the label
        # its `<dd>` carried: the column heading names the pair, and inside a cell
        # holding both a reader still has to be told which is which.
        extra = [f'<div class="oc">Related to: {esc(r)}</div>' for r in kind.relations]
        extra += [f'<div class="oc">Rule we believe holds: {esc(r)}</div>' for r in kind.rules]
        rows.append(
            _row(
                f"<strong>{esc(kind.name)}</strong>",
                held,
                fields,
                "".join(extra) or "—",
                _where(kind.provenance),
            )
        )
    return _table(
        ("What it is", "Held as", "Fields", "Rules and relations", "Where we read it"), rows
    )


def _personas(run: RunPaths):
    """Who uses it, and what they are trying to do.

    `personas` can return one bucket whose `id` is `""` and whose name is "Goals we
    could not attribute to a user". It renders like any other entry, deliberately:
    Task 6 wrote that name as owner-facing prose precisely so this renderer would
    need no branch, and a goal we hold about the target is worth showing whether or
    not we worked out who has it.
    """
    found = target_brief.personas(run)
    if isinstance(found, Marker):
        return found
    if not found:
        return '<p class="absent">We did not identify who uses it.</p>'
    rows = []
    for persona in found:
        goals = "".join(f'<div class="oc">{esc(goal)}</div>' for goal in persona.goals) or (
            "We did not record what they are trying to do."
        )
        rows.append(
            _row(f"<strong>{esc(persona.name)}</strong>", goals, _where(persona.provenance))
        )
    return _table(("Who", "What they are trying to do", "Where we read it"), rows)


def _sources_banner(run: RunPaths) -> str:
    """One line qualifying the whole page when the citations could not be read.

    Task 1 returns a marker rather than an empty index for exactly this: without
    the banner every "From x.py" line on the page would silently vanish, and the
    result reads as a confident description with no sources rather than as a
    broken render. Emitted once, at the top, because it is a property of the page.
    """
    if isinstance(target_brief.source_index(run), Marker):
        return (
            '<p class="banner">We could not read our own record of where each '
            "statement below came from, so this copy does not show its sources. "
            "The statements themselves are unaffected — but ask us for a copy that "
            "cites them before relying on this one.</p>"
        )
    return ""


def _description_banner(head) -> str:
    """One line qualifying the whole page when the description could not be read.

    The five sections below it -- disagreements, open questions, operations, data
    and users -- all return the identical marker in that case, because all five read
    the one file. Five panels saying so is one fact told five times, so it is told
    once here with weight and each section keeps its heading and a short line
    pointing back up at this.

    `head` rather than a second read: `headline` is a `Marker` exactly when the
    five builders are, so the caller already has the answer.
    """
    if isinstance(head, Malformed):
        return (
            '<p class="banner">We have a description of your system on file but '
            "could not read it back, so the sections below are empty. This is a "
            "fault at our end and not a statement about your system.</p>"
        )
    if isinstance(head, Marker):
        return (
            '<p class="banner">We do not have a description of your system on '
            "file, so the sections below are empty. What we read is the part that "
            "is worth your time on this copy.</p>"
        )
    return ""


def _reply() -> str:
    """How to reply, at the foot of the Workbook.

    It records answers per item and never a ratification of the run: whether one is
    worth collecting is a question these conversations have not answered yet, and
    `test_page_names_the_target_and_asks_the_question` keeps the word for it off
    the page.
    """
    return (
        '<div class="reply"><h3>How to reply</h3>'
        "<p>Download your answers and send us the file, or save the page as a PDF, or "
        "simply reply by email quoting each item's reference (D12, Q3) — whatever "
        "suits you. Ten answers are worth more to us than none, and a source we should "
        "have read is worth more than any of them.</p>"
        "<p>Nothing here needs to be agreed to. We are asking whether it is "
        "true.</p></div>"
    )


def _what_it_does(run: RunPaths, operations, personas, terse: bool) -> str:
    """What it seems to do: who uses it, then what it can do, in groups.

    Capabilities are grouped by their id's middle segment (`capability_group`),
    because 130 rows in one table is a reference dump and the run's services do not
    partition them. Each group is collapsed, so the section reads as a list of what
    the system does before it reads as a table of how.
    """
    users = _collapsed("Who uses it", personas, terse)
    found = target_brief.operations(run)
    if isinstance(found, Marker) or not found:
        return users + _collapsed("What it can do", operations, terse)
    groups = []
    for group, ops in target_brief.grouped_operations(found):
        name = group.capitalize() if group else "Other"
        groups.append(
            f"<details><summary>{esc(name)} ({esc(len(ops))})</summary>"
            f"{_operations_table(ops)}</details>"
        )
    return (
        users
        + f"<p>It can be asked to do {esc(len(found))} things, which we have grouped:</p>"
        + "".join(groups)
    )


_JS = r"""
(function () {
  var body = document.body;
  var key = 'tb:' + (body.getAttribute('data-digest') || body.getAttribute('data-run') || '');
  var store = {};
  try { store = JSON.parse(localStorage.getItem(key) || '{}') || {}; } catch (e) { store = {}; }
  function save() { try { localStorage.setItem(key, JSON.stringify(store)); } catch (e) {} }
  body.classList.add('js');
  var cards = Array.prototype.slice.call(document.querySelectorAll('#workbook .card'));
  var first = cards.filter(function (c) { return !c.closest('.group'); });
  function answered(card) {
    var a = store[card.getAttribute('data-item')];
    return !!(a && (a.choice || a.text));
  }
  function refresh() {
    cards.forEach(function (c) { c.classList.toggle('done', answered(c)); });
    var n = first.filter(answered).length;
    var out = document.getElementById('wb-count');
    if (out) { out.textContent = String(n); }
  }
  cards.forEach(function (card) {
    var id = card.getAttribute('data-item');
    var saved = store[id] || {};
    card.querySelectorAll('input, textarea').forEach(function (el) { el.disabled = false; });
    card.querySelectorAll('input[type=radio]').forEach(function (r) {
      if (saved.choice === r.value) { r.checked = true; }
      r.addEventListener('change', function () {
        store[id] = store[id] || {};
        store[id].choice = r.value;
        save(); refresh();
      });
    });
    var note = card.querySelector('textarea');
    if (note) {
      note.value = saved.text || '';
      note.addEventListener('input', function () {
        store[id] = store[id] || {};
        store[id].text = note.value;
        save(); refresh();
      });
    }
  });
  function show(tab) {
    ['report', 'workbook'].forEach(function (name) {
      var s = document.getElementById(name);
      if (s) { s.hidden = name !== tab; }
      var a = document.querySelector('.tabs a[href="#' + name + '"]');
      if (a) { a.classList.toggle('on', name === tab); }
    });
    window.scrollTo(0, 0);
  }
  function route() { show(location.hash === '#workbook' ? 'workbook' : 'report'); }
  window.addEventListener('hashchange', route);
  document.querySelectorAll('a[href="#workbook"], a[href="#report"]').forEach(function (a) {
    a.addEventListener('click', function (ev) {
      ev.preventDefault();
      history.replaceState(null, '', a.getAttribute('href'));
      route();
    });
  });
  route();
  document.querySelectorAll('button.filter').forEach(function (b) {
    b.disabled = false;
    b.addEventListener('click', function () {
      var want = b.getAttribute('data-filter');
      document.querySelectorAll('#workbook .group .card').forEach(function (c) {
        c.hidden = !!want && c.getAttribute('data-kind') !== want;
      });
    });
  });
  var print = document.getElementById('wb-print');
  if (print) {
    print.disabled = false;
    print.addEventListener('click', function () { window.print(); });
  }
  window.addEventListener('beforeprint', function () {
    body.classList.add('printing');
    document.querySelectorAll('#workbook details').forEach(function (d) {
      var hit = Array.prototype.some.call(d.querySelectorAll('.card'), answered);
      d.classList.toggle('untouched', !hit && d.classList.contains('group'));
      if (hit) { d.setAttribute('data-was', d.open ? '1' : '0'); d.open = true; }
    });
  });
  window.addEventListener('afterprint', function () {
    body.classList.remove('printing');
    document.querySelectorAll('#workbook details[data-was]').forEach(function (d) {
      d.open = d.getAttribute('data-was') === '1';
      d.removeAttribute('data-was');
    });
  });
  var dl = document.getElementById('wb-download');
  if (dl) {
    dl.disabled = false;
    dl.addEventListener('click', function () {
      var answers = cards.filter(answered).map(function (c) {
        var a = store[c.getAttribute('data-item')];
        return {
          item: c.getAttribute('data-item'),
          ref: c.getAttribute('data-ref'),
          kind: c.getAttribute('data-kind'),
          choice: a.choice || null,
          note: a.text || ''
        };
      });
      var doc = {
        format: 'rubrica-target-brief-answers',
        version: 1,
        run_id: body.getAttribute('data-run'),
        target: body.getAttribute('data-target'),
        generated: body.getAttribute('data-generated'),
        exported: new Date().toISOString(),
        answers: answers
      };
      var blob = new Blob([JSON.stringify(doc, null, 2)], {type: 'application/json'});
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'answers-' + (body.getAttribute('data-target') || 'system') + '-' +
        (body.getAttribute('data-run') || 'run') + '.json';
      document.body.appendChild(a);
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 0);
    });
  }
  refresh();
})();
"""


def _slug(value: str) -> str:
    """A file-name-safe form of the target's name, for the download's file name."""
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in value).strip("-")[:60]


def render(run: RunPaths) -> str:
    """The whole page, as one string: a Report that asks for nothing, then a
    Workbook that asks for a bounded set of answers first.

    Both are rendered in full, and the script only shows one at a time: with
    scripts off, the reader gets the Report and then the Workbook, one after the
    other, and every disagreement and question is still on the page.
    """
    head = target_brief.headline(run)
    known = isinstance(head, target_brief.Headline)
    # `head.name` can be `""` on a description that was read but names nothing, so
    # the test is the name and not the type. No fallback to `run.root.name`:
    # measured, that is `run-20260827-115248`, rubrica's identifier for the work
    # rather than anything the recipient has seen.
    name = head.name.strip() if known else ""
    # `.strip()` on all three: the schema's `minLength: 1` admits `" "`. Stripping
    # what is displayed is not rewriting it.
    interface = head.interface.strip() if known else ""
    notes = head.notes.strip() if known else ""
    subject = f"<strong>{esc(name)}</strong>" if name else "your system"
    terse = isinstance(head, Marker)
    operations = _operations(run)
    data_types = _data_types(run)
    personas = _personas(run)
    found = target_brief.disputes(run)
    questions = target_brief.open_questions(run)
    disputes = found if isinstance(found, list) else []
    takes = target_brief.quick_takes(disputes)
    by_id = {d.id: d for d in disputes}
    could_not_find = _group_d(run, questions)
    legend = _LEGEND if _needs_legend(could_not_find, operations, data_types, personas) else ""
    looks_off = (
        found
        if isinstance(found, Marker)
        else (_takes_html(takes, by_id) if disputes else _no_disputes())
    )
    manifest = _mapping_of(run)
    files = _files_read(run)
    report = (
        '<section id="report">'
        f'<p class="lede">An independent reader went through {files} of yours and wrote '
        f"down what {subject} seems to do, what it can do, and where its documents "
        "disagree. Here is what we took away.</p>"
        + _description_banner(head)
        + _sources_banner(run)
        + (f"<p>{esc(notes)}</p>" if notes else "")
        + _section("What it seems to do", _what_it_does(run, operations, personas, terse))
        + _section("What looks off", looks_off, terse)
        + _section("What we could not find", could_not_find, terse, lead=legend)
        + '<p class="invite"><strong>Want to help us test this system?</strong> '
        "Answering a few questions lets us build tests that match how it really "
        'behaves. <a href="#workbook">Open the workbook →</a></p>'
        + "<h2>Reference</h2>"
        + _collapsed("What data it holds", data_types, terse)
        + _collapsed("What we read", _group_a(run))
        + "</section>"
    )
    target = _slug(name)
    body = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{esc(name)} — does this describe your system?</title>"
        if name
        else "<title>Does this describe your system?</title>",
        f"<style>{_CSS}</style></head>",
        # Machine text for the export, in attributes only: never in what a reader
        # sees (the visible-text tests hold that), and constant for one run, so the
        # page stays byte-identical across renders.
        f'<body data-run="{esc(_text_of(manifest, "run_id"))}" '
        f'data-generated="{esc(_text_of(manifest, "created_utc"))}" '
        f'data-digest="{esc(_digest(manifest))}" data-target="{esc(target)}">',
        f"<h1>{esc(name)}</h1>" if name else "<h1>The system we are describing</h1>",
        f'<p class="meta">Reached over {esc(interface)}.</p>' if interface else "",
        '<nav class="tabs"><a href="#report">Report</a> <a href="#workbook">Workbook</a></nav>',
        report,
        _workbook(run, found, questions, takes),
        f"<script>{_JS}</script>",
        "</body></html>",
    ]
    return "\n".join(part for part in body if part)


def _mapping_of(run: RunPaths) -> dict:
    return _mapping(_quietly(run.manifest))


def _text_of(manifest: dict, key: str) -> str:
    value = manifest.get(key)
    return value if isinstance(value, str) else ""


def _digest(manifest: dict) -> str:
    """A short stable digest of the manifest's inputs, so answers in one browser for
    one run never restore into the page for another. sha256 over the sorted input
    digests; the raw ones are already recorded, so nothing new is asserted."""
    digests = sorted(
        r.get("sha256") for r in _dicts(manifest.get("inputs")) if isinstance(r.get("sha256"), str)
    )
    return hashlib.sha256("\n".join(digests).encode()).hexdigest()[:16] if digests else ""


def _files_read(run: RunPaths) -> str:
    groups = target_brief.inputs_read(run)
    if isinstance(groups, Marker) or not groups:
        return "the documents"
    n = sum(len(g.files) for g in groups)
    return f"{esc(n)} file{'' if n == 1 else 's'}"
