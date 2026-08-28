"""The markup half of `target-brief`. `target_brief.py` reads and computes.

The same split as `summary.py` / `summary_html.py`, for the same reason: a section
that disagrees with the numbers a human reads beside it is then a defect in one
builder rather than in two spellings of the same read.

Three things this page does differently from `summary_html`, all because it leaves
the project rather than sitting in a run directory:

**No JavaScript.** Not one line. `<details>` collapses natively, nothing here
sorts, and this page is emailed -- opened in a mail client's browser view, behind a
corporate proxy, by a reader with scripts off. A page that needs a script to be
readable arrives broken for some of its recipients.

**Its own `_CSS`.** Importing `summary_html._CSS` would let a tweak to the operator
page restyle a document already sent to somebody outside the project.

**Its own marker prose.** `summary_html` says `Not present: 01-world-model.json`,
which is right for an operator and meaningless to an owner; here the same fact
reads "We do not have this on file, so this section is empty."

**Nothing this module's own prose puts on the page names a stage, a gate, an
artifact or rubrica itself,** and
`test_the_pages_own_prose_never_names_a_stage_a_gate_or_an_artifact` plus
`test_page_never_shows_a_rubrica_identifier` fail the suite rather than let one back
in. The claim is deliberately about our own chrome and not about the page as a whole:
prose this module *selects* from the run ships as written, ids and all, for the reason
the next paragraph gives. That is not tidiness: a recipient asked "does this describe
your system?" who is instead reading about `01-world-model.json` has been handed the
wrong question.

One id shape can still reach the page and is accepted rather than suppressed.
`SourceRef.path` falls back to the artifact id when the manifest does not register
the cited artifact, so `_taken` can render "We went with art-notes-md-1." and a
source row can name the same string. Suppressing it would need this module to
decide, from a string, whether Task 4's sentence names a real file -- a second
spelling of a rule Task 1 already ruled on, in the module that owns it, in favour
of naming *something* chaseable over naming nothing. The no-identifier test is
therefore a test about the toy corpus, where every cited artifact is registered,
and not a proof about every run.

Everything user-controlled goes through `summary.esc`, including numbers and dict
keys, for the reason its docstring gives -- a lone surrogate becomes text there,
and it was a report exiting 1 after rendering correctly before it did.
"""

from __future__ import annotations

from rubrica import target_brief
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
    --surface: #21232733; --zebra: #1c1e21; --quote: #1e2024;
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
   selector that only matched inside one left every filename in the "What we read"
   listing in the body face. `.ident` is the target's own name for something that
   is not a file -- a collection -- and wants the same treatment for the same
   reason: it is a string to copy exactly, not prose to read. */
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
.kind-api { color: var(--kind-api); border-color: currentColor; }
.kind-mcp { color: var(--kind-mcp); border-color: currentColor; }
.kind-entity { color: var(--kind-entity); border-color: currentColor; }
.kind-trace { color: var(--kind-trace); border-color: currentColor; }
.kind-doc { color: var(--kind-doc); border-color: currentColor; }
.kind-code { color: var(--kind-code); border-color: currentColor; }
.kind-other { color: var(--kind-other); border-color: currentColor; }
/* The page is emailed, so it is printed. Backgrounds do not print by default;
   the border and the chip's own word are what survive. */
@media print {
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
# undecided, never a decision: `target_brief._taken` already returns `""` for
# anything outside the three it knows, so the chip and the sentence agree without
# either consulting the other.
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


def _row(*cells: str) -> str:
    """One table row from cell contents that are already escaped or already markup.

    Deliberately not escaping: every caller passes either markup it built (a chip, a
    `.file` span) or a string it has already put through `esc`. A second escape here
    would double-encode every filename on the page, and the alternative -- escaping
    here and not at the call site -- would mean no cell could contain markup.
    """
    return "<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>"


def _table(headers: tuple[str, ...], rows: list[str], klass: str = "") -> str:
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
    attr = f' class="{klass}"' if klass else ""
    return (
        f'<div class="tw"><table{attr}><thead><tr>{head}</tr></thead>'
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


def _provenance(prov) -> str:
    """Where we read it: the files, their kinds, and whether they disagreed.

    One line under the sentence it supports rather than a column, because the
    sentence is what the recipient is being asked about and the source is how they
    check it. `single_source` is read from the property rather than recomputed here
    -- Task 2 made it a property precisely so no caller can disagree with `files`.

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
    files = ", ".join(f'<span class="file">{esc(f)}</span>' for f in prov.files)
    if prov.single_source:
        text = f"From {files}"
    else:
        kinds = ", ".join(esc(_kind(k)) for k in prov.kinds)
        text = f"From {len(prov.files)} sources ({kinds}): {files}"
    if prov.disputed:
        text += ' — <span class="disputed">our sources disagree about this</span>'
    return f'<span class="src">{text}.</span>'


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
    shown = ", ".join(f'<span class="file">{esc(f)}</span>' for f in named)
    if not missing:
        return shown
    tail = f"{missing} more we could not name" if shown else f"{missing} we could not name"
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
        tail = f" (read as {len(group.files) + group.slices} pieces)" if group.slices else ""
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
    """One dispute's status, as a chip.

    Anything outside the three values `_STATUS_CHIP` knows reads as undecided, which
    is what `target_brief._taken` independently does with the same field: it returns
    `""` for an unrecognised resolution, so the sentence below the sides also says
    nothing was decided. The two agree by both defaulting to "we did not decide"
    rather than by consulting each other -- a colour claiming a decision over a
    sentence denying one is the page asserting a judgment nobody made.
    """
    variant, word = _STATUS_CHIP.get(resolution, _STATUS_CHIP["unresolved"])
    return _chip(variant, word)


def _side_rows(refs, label: str) -> list[str]:
    """One side of a disagreement, as rows of a source-and-quote table.

    Was `_side_html`, which returned a `<p>` plus a `<ul>`. The rows carry the same
    three facts and let the reader compare the two sides down a column, which is the
    comparison the section is asking them to make and the one a pair of nested
    bullet lists made hardest.

    `Dispute.side_a` is a `tuple[SourceRef, ...]`, not a sentence. Rendering it
    through `esc()` directly would print the dataclass repr and put
    `claim_id='clm-notes-004'` on a page whose entire premise is that no rubrica
    identifier appears on it -- the no-identifier test would catch it, with nothing
    to say about the fix. Each ref becomes its path, its locator and the line it
    quotes, which is what spec section 3.3 asks for: each side shown as a real file
    quoting itself. `_provenance` is not reused here because that renders a whole
    element's sources as one subordinate line, and a side of a disagreement is the
    thing being read, not a footnote under it.

    The locator is labelled `at`, not dropped into bare parentheses: it is a
    fragment or a JSON pointer -- `#error-behaviour` and `#/spans/1/output` on the
    toy, and Task 3 measured `#/126` shapes on a real run -- and `notes.md
    (#error-behaviour)` reads as a note about the file where `notes.md (at
    #error-behaviour)` reads as a place inside it.

    The label repeats down every row of a multi-ref side rather than spanning them.
    A `rowspan` over a side whose refs are empty is a branch whose edge case is
    invisible until an owner meets it, and the empty case is real: a side can resolve
    to no refs at all.
    """
    if not refs:
        # A side whose claims did not resolve to any input. Saying so beats
        # dropping the side: `taken` below may still name a file, and a page that
        # answers a question it never asked reads as a page with something missing.
        return [_row(esc(label), "we could not resolve which file states it", "")]
    rows = []
    for ref in refs:
        # Task 4's handoff: a sliced input's `path` carries the slicer's fragment,
        # and juxtaposing it against the filename does not explain itself. Measured
        # on run-20260816-172810, this side line read `trajectories2.json#/10 (at
        # /data/spans/5/...)`; the file is the owner's and the `#/10` is our index
        # into it, so the two are separated and only the index is labelled. Nothing
        # is dropped -- `_shorten` keeps the fragment precisely because it is the
        # only thing telling 71 slices of one capture apart.
        #
        # Which part is the file is `target_brief._file_and_piece`'s ruling, not a
        # second reading of the same path here: it owns the JSON-pointer clause and
        # the measurements behind it, and the sentence under these two sides now
        # names the file through the same helper, so one source cannot be spelled
        # two ways on one page.
        base, piece = target_brief._file_and_piece(ref.path)
        # A path with nothing nameable in it rendered as a blank
        # `<span class="file">` -- measured on a hand-edited world model, reachable
        # only there because `SourceRef.path` falls back to the artifact id. The
        # phrase is `_files_html`'s, which already counts the files it could not
        # name in the section above, so the absence is stated in words this page
        # already uses rather than in a new sentence.
        where = f'<span class="file">{esc(base)}</span>' if base else "a file we could not name"
        # One parenthesis, not two in a row: the piece and the locator are both
        # "where inside your material this is", and reading them as one clause is
        # why they are joined rather than emitted as separate spans.
        inside = []
        if piece:
            inside.append(f"piece {esc(piece)}")
        if ref.locator:
            inside.append(f"at {esc(ref.locator)}")
        if inside:
            where += f" ({', '.join(inside)})"
        # Degrades to path plus locator when the evidence record carries no quote --
        # 59 of executive-agent's 126 cited claims, per Task 1, and the toy's own
        # side_b, whose `quote` is `""`. The cell states the absence rather than
        # sitting empty: an empty cell in a quote column reads as a quote we lost.
        said = (
            f'<span class="quote">“{esc(ref.quote)}”</span>'
            if ref.quote
            else "we did not record the wording"
        )
        rows.append(_row(esc(label), where, said))
    return rows


def _group_bc(run: RunPaths):
    """Where our sources disagree, and what we did about it.

    Task 4's `Dispute` carries both the two sides and the side taken, so B and C
    are one list rather than two: a reader deciding "which of these two is right"
    needs to see in the same place which one we acted on. An unresolved
    contradiction is not split out either -- it is visibly undecided in its own
    position in the list, and splitting would break the comparison the reader is
    making across it.

    Two tiers, which is new. The index table exists because 41 disputes -- measured
    on run-20260826-090456 -- is more than anyone scans as prose, and the one thing
    a reader wants first is which of them are still open. The detail stays whole
    beneath it because the two verbatim quotes are what let an owner settle a
    dispute, and they cannot be shortened without taking away the thing they are
    being asked to rule on.

    Numbering is positional, 1-based, and is not `Dispute.id`: the id is the run's
    own string and this page never shows one.
    """
    found = target_brief.disputes(run)
    if isinstance(found, Marker):
        return found
    if not found:
        return (
            '<p class="absent">Nothing we read contradicted anything else we read. '
            "That is a weaker statement than it sounds: it means we found no "
            "disagreement, not that your documents agree.</p>"
        )
    index_rows = []
    blocks = []
    for position, dispute in enumerate(found, start=1):
        chip = _status_chip(dispute.resolution)
        # The files on both sides, deduplicated and in first-seen order, so the index
        # row names what the reader would search their own tree for. `dict.fromkeys`
        # rather than a set: a set reorders, and the order the sides were read in is
        # the order the detail below shows them.
        names = [
            target_brief._file_and_piece(ref.path)[0] for ref in (*dispute.side_a, *dispute.side_b)
        ]
        files = list(dict.fromkeys(n for n in names if n))
        involved = (
            ", ".join(f'<span class="file">{esc(f)}</span>' for f in files)
            if files
            else "we could not name them"
        )
        # `nature` is carried verbatim. Verbatim because this document never rewrites
        # prose; and it is the cell an owner scans to decide whether this row is one
        # they know something about.
        nature = esc(dispute.nature) or "we could not read our own note of what about"
        # `esc(position)` on an integer this function itself produced, matching the
        # `<h3>` below rather than being spelled two ways in one function: the module
        # docstring's rule covers numbers, `_group_a` already escapes its two counts,
        # and one number rendered escaped in one place and raw in another is the shape
        # a later edit reads as permission to skip it.
        index_rows.append(_row(f'<span class="num">{esc(position)}</span>', chip, nature, involved))
        # `taken` is `""` for `unresolved` -- Task 4 leaves it empty rather than
        # asserting a decision nobody made. The renderer says so out loud instead
        # of emitting an empty bold paragraph: on this page, silence after two
        # contradicting sides reads as a decision the reader missed.
        taken = dispute.taken or "We have not decided between them."
        rows = _side_rows(dispute.side_a, "One side") + _side_rows(dispute.side_b, "The other side")
        blocks.append(
            # "The disagreement: " is pinned by
            # `test_page_labels_the_nature_of_a_disagreement_rather_than_leading_with_it`,
            # which records that a bare `count_mismatch` reads as a sentence we wrote
            # badly rather than as a category we were handed. The label lives here,
            # once, and the index cell carries the bare nature because its column
            # heading is already the label.
            f"<h3>{esc(position)}. The disagreement: {nature} {chip}</h3>"
            + _table(("Side", "Source", "What it says"), rows)
            + f"<p><strong>{esc(taken)}</strong></p>"
        )
    return (
        "<p>Two things we read said different things. Each one below is a place "
        "where a word from you settles it. The table lists them all; the detail "
        "under it quotes both sides.</p>"
        + _table(("#", "Status", "What kind of disagreement", "Files involved"), index_rows)
        + "".join(blocks)
    )


def _group_d(run: RunPaths):
    """What we could not tell. No provenance line: a gap cites nothing in any of
    the three recordings measured (0 of 18, 0 of 19, 0 of 15), so a provenance
    line here would be blank on every real run."""
    found = target_brief.open_questions(run)
    if isinstance(found, Marker):
        return found
    if not found:
        return (
            '<p class="absent">We did not record any open question. On a real '
            "target that is more likely to mean we did not notice one than that "
            "none exists.</p>"
        )
    items = []
    for q in found:
        # The question leads and our label for it trails, which is the reverse of
        # the draft. Measured over the 49 questions in the three recordings:
        # `unknown` is a self-contained sentence in all 49, while `subject` is a
        # bare slug in 19 of 19 on run-20260825-094033 (one of them,
        # `outbox-approval-invariant`, four times over), an `ent-… / inv-…` id pair
        # in 10 of 12 on run-20260816-172810, and an id-prefixed phrase in all 18
        # on run-20260826-090456. Bolding that as the lead of a question put a
        # rubrica identifier in the recipient's eye ahead of the question itself.
        # The label is kept rather than dropped, and named as ours, because it is
        # what they would quote back at us.
        ref = f' <span class="ident">(our reference: {esc(q.subject)})</span>' if q.subject else ""
        # No run has yet produced a gap with no `unknown`, so this is the branch
        # for an artifact that was written outside the schema rather than one
        # observed: state the absence, never leave a bullet holding only our id.
        asked = esc(q.unknown) or "We did not record what it was that we could not tell."
        items.append(f"<li>{asked}{ref}</li>")
    return (
        "<p>These are things we could not work out from what we read. They are "
        "questions, not criticisms.</p>"
        f"<ul>{''.join(items)}</ul>"
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
    blocks = []
    for op in found:
        params = (
            "<dd>Takes: " + esc(", ".join(op.params)) + "</dd>"
            if op.params
            else "<dd>Takes no parameters.</dd>"
        )
        outcomes = "".join(
            # A description can be `""` -- Task 5's handoff -- and `label:` with
            # nothing after it reads as prose that got truncated. The label is
            # still a fact about the target, so it stays and the absence is stated.
            f"<dd><em>{esc(o.label)}</em>"
            + (f": {esc(o.description)}" if o.description else " — we did not record what happens")
            + "</dd>"
            for o in op.outcomes
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
        called = f"<dd>Called as: {esc(handle)}</dd>" if handle and handle != title else ""
        heading = esc(title) if title else "One operation whose name we did not record"
        blocks.append(
            f"<dt>{heading}</dt>{called}{params}{outcomes}<dd>{_provenance(op.provenance)}</dd>"
        )
    return f"<dl>{''.join(blocks)}</dl>"


def _data_types(run: RunPaths):
    """What data it holds."""
    found = target_brief.data_types(run)
    if isinstance(found, Marker):
        return found
    if not found:
        return '<p class="absent">We did not identify the kinds of data it holds.</p>'
    blocks = []
    for kind in found:
        rows = [f"<dt>{esc(kind.name)}</dt>"]
        if kind.collection:
            # Measured `tickets` and `comments` on the toy. This is the one
            # `DataType` field that is the owner's own name rather than ours, so
            # it is the one a reader can confirm or correct outright -- and it is
            # the string that tells them which store we mean when their system has
            # two things called a Ticket.
            rows.append(f'<dd>Held as: <span class="ident">{esc(kind.collection)}</span></dd>')
        if kind.fields:
            # The type is parenthesised only when there is one. Measured, an empty
            # `type` rendered `ticket_id ()`, where the sibling outcome path states
            # its absence -- and a bare pair of brackets reads as a rendering fault
            # rather than as something we did not record.
            fields = ", ".join(
                f"{esc(f.name)} ({esc(f.type)})" if f.type.strip() else esc(f.name)
                for f in kind.fields
            )
            rows.append(f"<dd>Fields: {fields}</dd>")
        for relation in kind.relations:
            rows.append(f"<dd>Related to: {esc(relation)}</dd>")
        for rule in kind.rules:
            rows.append(f"<dd>Rule we believe holds: {esc(rule)}</dd>")
        rows.append(f"<dd>{_provenance(kind.provenance)}</dd>")
        blocks.append("".join(rows))
    return f"<dl>{''.join(blocks)}</dl>"


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
    blocks = []
    for persona in found:
        goals = "".join(f"<dd>{esc(goal)}</dd>" for goal in persona.goals) or (
            "<dd>We did not record what they are trying to do.</dd>"
        )
        blocks.append(
            f"<dt>{esc(persona.name)}</dt>{goals}<dd>{_provenance(persona.provenance)}</dd>"
        )
    return f"<dl>{''.join(blocks)}</dl>"


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
    """How to reply. This is what stands in place of the sign-off block the design
    dropped: the document asks for corrections in prose and offers no place to
    record an approval, because whether a ratification is worth collecting is a
    question these conversations have not answered yet.

    At the foot of the page, where the closing of an emailed document belongs --
    which is why it says "the description above" and not "below": `render` puts
    this last, and the brief's draft described a layout it did not build.
    """
    return (
        '<div class="reply"><h2>How to reply</h2>'
        "<p>Reply in whatever form suits you — prose in an email is ideal. The three "
        "things we asked for at the top are ranked: a source we should have read is "
        "worth more to us than a misread field, and a disagreement you settle is "
        "worth more than a detail you confirm. You do not need to work through the "
        "full description above to be useful to us.</p>"
        # Not "we are not asking you to approve anything", which is what the brief
        # wrote here: the brief's own
        # `test_page_names_the_target_and_asks_the_question` forbids the word
        # `approve` anywhere on the page, and the two shipped contradicting each
        # other. The test wins, because the word is the strongest signal that the
        # dropped sign-off block has come back -- and the sentence keeps its whole
        # meaning without it.
        "<p>Nothing here needs to be agreed to. We are asking whether it is "
        "true.</p></div>"
    )


def render(run: RunPaths) -> str:
    """The whole page, as one string."""
    head = target_brief.headline(run)
    known = isinstance(head, target_brief.Headline)
    # `head.name` can be `""` on a description that was read but names nothing, so
    # the test is the name and not the type. No fallback to `run.root.name`, which
    # the brief's draft used: measured, that is `run-20260827-115248`, which is
    # rubrica's identifier for the work rather than anything the recipient has seen
    # -- and a page whose `<h1>` is that has handed them the wrong subject.
    name = head.name.strip() if known else ""
    # `.strip()` on all three: the schema's `minLength: 1` admits `" "`, and
    # measured, a whitespace-only `interface` rendered `Reached over  .`, a
    # whitespace-only `notes` an empty `<p> </p>`, and a whitespace-only `name` an
    # `<h1>` holding one space where the no-name branch says what the page is about.
    # Stripping what is displayed is not rewriting it.
    interface = head.interface.strip() if known else ""
    notes = head.notes.strip() if known else ""
    # The subject of every sentence about the target, so one branch decides it
    # rather than each sentence guessing.
    subject = f"<strong>{esc(name)}</strong>" if name else "your system"
    # True for exactly the five sections that read the description, which is the
    # only case `_marker`'s terse form is correct for.
    terse = isinstance(head, Marker)
    # Built once, so the legend below can ask whether the label is on the page
    # rather than recomputing the operations to find out.
    operations = _operations(run)
    # Every body built before the page is assembled, because the legend's trigger is
    # a property of all of them and the legend must be readable above the lines it
    # glosses. Tier 2's three are built here for that reason alone -- they were
    # interpolated in place before, which is what put the gloss below the tier-1 ask
    # carrying most of what it explains.
    could_not_tell = _group_d(run)
    data_types = _data_types(run)
    personas = _personas(run)
    legend = _LEGEND if _needs_legend(could_not_tell, operations, data_types, personas) else ""
    body = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{esc(name)} — does this describe your system?</title>"
        if name
        else "<title>Does this describe your system?</title>",
        f"<style>{_CSS}</style></head><body>",
        f"<h1>{esc(name)}</h1>" if name else "<h1>The system we are describing</h1>",
        f'<p class="meta">Reached over {esc(interface)}.</p>' if interface else "",
        f'<p class="lede">This is what we currently believe about {subject}, '
        "written from your own documents. "
        "<strong>Does this accurately describe your system?</strong> Where it does "
        "not, we would rather hear it now than build on it.</p>",
        _description_banner(head),
        _sources_banner(run),
        f"<p>{esc(notes)}</p>" if notes else "",
        "<h2>What we most need from you</h2>",
        # The draft left this heading with nothing under it, and on all three
        # recordings it rendered as a bare rule above the next heading -- the one
        # place on the page that read as a section that had failed to fill in.
        # Its counterpart below ("What we believe, in full") always had its lead
        # sentence, so this is the sentence that was missing rather than a new
        # tier. It also states the ranking that the reply block refers back to.
        "<p>Three things, in the order they help us most: a source we should have "
        "read, a place our sources disagree, and something we could not work "
        "out.</p>",
        _section("What we read", _group_a(run)),
        _section("Where our sources disagree", _group_bc(run), terse),
        _section("What we could not tell", could_not_tell, terse, lead=legend),
        "<h2>What we believe, in full</h2>",
        "<p>Everything below is the detail behind the asks above. Skim it or skip "
        "it — the sections above are where a correction helps us most.</p>",
        _collapsed("What it can do", operations, terse),
        _collapsed("What data it holds", data_types, terse),
        _collapsed("Who uses it", personas, terse),
        _reply(),
        "</body></html>",
    ]
    return "\n".join(part for part in body if part)
