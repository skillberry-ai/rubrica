# `target-brief` Tables, Theme and Colour Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn every populated section of `target-brief.html` from bullet lists
into tables, give the page a light/dark theme, and colour it using only fields
the run recorded.

**Architecture:** One renderer changes, `src/rubrica/target_brief_html.py`.
Task 1 lands the theme and three markup primitives (`_table`, `_row`, `_chip`);
Tasks 2 through 5 convert one section family each on top of them; Task 6 adds
the ranked-asks table and the page-level guards. `src/rubrica/target_brief.py`
is not touched — it already computes every field the new markup needs, and the
compute/render split is what keeps a section from disagreeing with the numbers
beside it.

**Tech Stack:** Python 3.13, `uv`, pytest, ruff. No JavaScript and no webfonts in
the output, ever — the page is emailed and read behind proxies with scripts off.

**Spec:** [`docs/superpowers/specs/2026-08-28-target-brief-tables-and-theme-design.md`](../specs/2026-08-28-target-brief-tables-and-theme-design.md)

## Global Constraints

Every task's requirements implicitly include all of these.

- **Commits are signed and DCO'd: `git commit -S -s`.** Both flags. If signing
  fails, stop and report it; never fall back to unsigned.
- Attribution trailer is `Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>`.
  Never `Co-Authored-By`.
- ruff: `line-length = 100`, `select = ["E","F","I","UP","B","SIM"]`. Run
  `make check` before every commit.
- **No JavaScript in the rendered page. No webfonts.** Not one line, not one
  `@import`.
- **Everything user-controlled goes through `summary.esc`** — including numbers,
  dict keys and any string read from an artifact.
- **This module's own prose names no stage, no gate, no artifact, and not
  rubrica.** Prose *selected* from the run ships verbatim, ids and all. Two
  tests enforce this and must stay green.
- **Selected prose is relabelled, never rewritten.** Markup may change around a
  sentence; the sentence may not change.
- **A section whose body is a `Marker` keeps its heading and renders the marker
  sentence** — never a table, never nothing.
- Comment density in this file is high and deliberate: comments explain *why*,
  usually citing a measurement. Match it. Do not strip existing comments when
  moving code.
- The test command throughout is
  `uv run pytest tests/unit/test_target_brief_html.py -q`.
- Full gates are `make test`, `make check`, and `uv run rubrica check-skills`.

### Existing assertions that pin markup you are changing

These are measured rulings, not incidental strings. Preserve the markup they
name, or — where a task says so explicitly — update the assertion and keep the
ruling.

| Test file line | Pinned string | Consequence |
|---|---|---|
| 182 | `' under <span class="file">docs</span>'` (leading space) | `_group_a`'s `where` clause keeps its exact construction, including the leading space. |
| 253, 254, 641 | `<span class="file"></span>` and `<span class="file"> </span>` must **not** appear | Never emit an empty or blank `.file` span. |
| 630, 872, 894 | `<span class="file">notes.md</span>`, `…trace.json…`, `'From <span class="file">api.json</span>'` | `.file` spans carry no extra classes, and `_provenance`'s single-source sentence keeps the words `From <file>`. |
| 832 | `'<span class="file">#/spans/1</span> (at #/spans/1/output)'` | `_side_html`'s "file (at locator)" form survives verbatim. |
| 862, 864 | `page.count('<span class="file">notes#2.md</span>') == 2`, and `<span class="file">notes</span>` **not** in page | **Task 3 changes this count.** Update the number to what the new markup produces; keep the `not in` assertion, which is the actual ruling. |
| 578, 587 | `"our sources disagree about this"` absent / present | The disputed marking keeps that exact phrase as its word. |
| 1059 | `'<p class="meta">Reached over mcp.</p>'` | The meta line is untouched by every task. |

---

## File Structure

| File | Responsibility |
|---|---|
| `src/rubrica/target_brief_html.py` (modify) | The only source file. Theme in `_CSS`; primitives `_table`/`_row`/`_chip`; one builder per section, each converted in place. |
| `tests/unit/test_target_brief_html.py` (modify) | 46 existing test functions. Four assert `<dt>`/`<dd>`/`<dl>` and are rewritten in Task 5; the rest keep passing unchanged. New tests are appended per task. |
| `CLAUDE.md`, `docs/reference/cli.md` (check, modify only if needed) | Task 6 verifies the `target-brief` paragraphs still read true. |

---

## Task 1: The theme and the markup primitives

**Files:**
- Modify: `src/rubrica/target_brief_html.py` — replace `_CSS` (lines 56-94); add
  `_table`, `_row`, `_chip`, `_KIND_SLUG`, `_STATUS_CHIP` after `_kind`.
- Test: `tests/unit/test_target_brief_html.py`

**Interfaces:**
- Consumes: `summary.esc`, the existing `_kind`, `_KIND_LABELS`.
- Produces, for Tasks 2-6:
  - `_table(headers: tuple[str, ...], rows: list[str], klass: str = "") -> str`
    — a scroll wrapper plus `<table>` with a `<thead>` row of `<th>`. Escapes
    headers. Returns `""` when `rows` is empty, so no caller can emit an empty
    table.
  - `_row(*cells: str) -> str` — one `<tr>` of `<td>`. Cells arrive **already
    escaped or already markup**; `_row` does not escape.
  - `_chip(variant: str, word: str) -> str` — `<span class="{variant}">{word}</span>`,
    word escaped. One class, not two, so an existing assertion on a bare class
    string cannot be broken by a shared prefix.
  - `_kind_chip(kind: str) -> str` — the kind chip, word from `_kind`.
  - `_STATUS_CHIP: dict[str, tuple[str, str]]` — `resolution` → (variant, word).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_target_brief_html.py`:

```python
def test_every_colour_token_is_defined_in_both_palettes():
    """A token defined only in `:root` renders as nothing in dark mode, and the
    author working in light mode cannot see it. Both directions matter, so this
    reads the tokens actually *used* and checks each palette defines every one."""
    css = target_brief_html._CSS
    used = set(re.findall(r"var\((--[a-z0-9-]+)\)", css))
    assert used, "no custom properties in use -- this test would be vacuous"
    light, _, rest = css.partition("prefers-color-scheme: dark")
    assert rest, "no dark block in the stylesheet"
    for token in sorted(used):
        assert f"{token}:" in light, f"{token} is used but not defined for light"
        assert f"{token}:" in rest, f"{token} is used but not defined for dark"


def test_table_helper_emits_a_header_row_and_nothing_for_no_rows():
    assert target_brief_html._table(("A", "B"), []) == ""
    html = target_brief_html._table(("A", "B"), [target_brief_html._row("1", "2")])
    assert "<th>A</th>" in html and "<th>B</th>" in html
    assert "<td>1</td><td>2</td>" in html


def test_table_helper_escapes_its_headers():
    html = target_brief_html._table(("<x>",), [target_brief_html._row("c")])
    assert "<th>&lt;x&gt;</th>" in html


def test_a_chip_always_carries_its_word():
    """Colour is never the only carrier: the page is emailed, printed and
    forwarded into clients that strip CSS."""
    chip = target_brief_html._chip("undecided", "Undecided")
    assert ">Undecided<" in chip
    assert 'class="undecided"' in chip


def test_a_chip_escapes_its_word():
    assert "&lt;b&gt;" in target_brief_html._chip("both", "<b>")


def test_every_status_chip_names_a_variant_and_a_word():
    for resolution, (variant, word) in target_brief_html._STATUS_CHIP.items():
        assert variant and word, resolution
        assert word == word.strip()


def test_the_page_carries_no_stylesheet_link_and_no_font_import():
    """No webfont: the page is opened behind a corporate proxy, offline, in a
    mail client's browser view. A downloaded face is one more thing that fails
    to arrive."""
    css = target_brief_html._CSS
    assert "@import" not in css
    assert "font-face" not in css
    assert "http" not in css
```

`re` is already imported at the top of this test module (it is used at line 641).

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_target_brief_html.py -q -k "colour_token or table_helper or chip or stylesheet_link"`
Expected: FAIL — `AttributeError: module 'rubrica.target_brief_html' has no attribute '_table'`, and the token test failing on `no dark block in the stylesheet`.

- [ ] **Step 3: Replace `_CSS`**

Replace the whole `_CSS` string (and keep the comment above it, amended as
shown — the old comment argues a prose-only measure that is no longer the whole
truth):

```python
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
```

- [ ] **Step 4: Add the primitives**

Insert after `_kind` (which currently ends around line 170):

```python
# `kind` -> the CSS class carrying that kind's hue. Seven, matching `_KIND_LABELS`,
# and an off-schema kind falls to `kind-other` while `_kind` still ships its own
# token as the word: an unknown kind gets a neutral colour and its real name, never
# a colour we invented a meaning for.
#
# These are unordered categories, so the hues are seven distinct families and not a
# light-to-dark ramp. A ramp would say one kind outranks another, which is a claim
# the run does not make.
# Amended during implementation, and the reason is measured rather than aesthetic: a
# slug spelled `kind-openapi` puts that enum token in the `<style>` block, and
# `test_page_relabels_every_input_kind_rather_than_shipping_the_token` asserts
# `\bopenapi\b` is absent from the whole page -- `-` is a word boundary, so the class
# matches. `kind-http` is not the way out either: it fails this task's own no-webfont
# check, which cannot tell a class from a URL.
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
```

- [ ] **Step 5: Run the new tests**

Run: `uv run pytest tests/unit/test_target_brief_html.py -q -k "colour_token or table_helper or chip or stylesheet_link"`
Expected: PASS, 7 tests.

- [ ] **Step 6: Run the whole module's suite**

Run: `uv run pytest tests/unit/test_target_brief_html.py -q`
Expected: PASS. Nothing has changed the markup yet, so all 46 existing tests
still hold. If any fail, it is the stylesheet: check that no class the suite
asserts on lost its rule.

- [ ] **Step 7: Measure the token test in both directions**

Delete the `--attn-line` line from the dark block in a scratch copy, run the
token test, confirm it goes red naming `--attn-line`; restore it and confirm
green. A predicate nobody has watched fail is not yet a guard.

- [ ] **Step 8: Check and commit**

```bash
make check
git add src/rubrica/target_brief_html.py tests/unit/test_target_brief_html.py
git commit -S -s -F - <<'MSG'
feat: Give target-brief a two-palette theme and its table primitives

The stylesheet becomes custom properties defined once per palette, with explicit
--bg and --fg rather than leaning on `color-scheme: light dark`: once a chip has a
background, the UA default is no longer a surface the contrast was checked against.
A test reads the tokens actually used and fails if either palette is missing one,
because a token defined only in :root renders as nothing in dark mode and the author
working in light mode cannot see it.

Three primitives the section builders land on next. `_table` returns "" for no rows
so no caller can ship a header row with nothing under it -- a table with headings and
no body reads as a render that broke, which is what this module's five "absent"
sentences exist to avoid. `_row` deliberately does not escape, because every cell is
either markup we built or a string already through esc. `_chip` has no branch that
omits its word: the page is emailed, printed and forwarded into clients that strip
CSS, so a chip whose meaning lives in its background loses its meaning in transit.

Chips carry one class rather than a shared `chip` class plus a variant. The suite
asserts on bare class="x" strings and a shared prefix would break every one of them.

Kind hues are seven unordered families, not a ramp: a ramp would say one kind of
source outranks another, which is a claim the run does not make.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
```

---

## Task 2: "What we read" becomes a table

**Files:**
- Modify: `src/rubrica/target_brief_html.py` — `_group_a`, the `items` loop and
  the returned markup.
- Test: `tests/unit/test_target_brief_html.py`

**Interfaces:**
- Consumes: `_table`, `_row`, `_kind_chip` from Task 1.
- Produces: nothing new. `_group_a`'s signature and return type are unchanged —
  it still returns `str` or a `Marker`.

- [ ] **Step 1: Write the failing tests**

```python
def test_what_we_read_is_a_table_with_a_kind_column(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    # Split on the heading, not the bare phrase: "What we read" first occurs at page
    # offset 2635 inside `_CSS`'s `.file, .ident` comment, against the heading at 6809,
    # so a bare-phrase split returns a slice of the stylesheet.
    section = page.split("<h2>What we read</h2>")[1].split("<h2>")[0]
    assert "<table>" in section or '<table class' in section
    assert "<th>What kind</th>" in section
    assert "<th>Where</th>" in section
    assert "<th>The files</th>" in section
    # The kind chip, coloured and carrying its own word.
    assert 'class="kind-doc"' in section
    assert ">Written documentation<" in section


def test_what_we_read_keeps_its_count_sentence_above_the_table(tmp_path):
    """The sentence is what gives a reader the size before they wade in, and
    `_group_a`'s ruling is that the listing stays uncapped because the file the
    owner would have named is the one behind an "and 24 more"."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    section = page.split("<h2>What we read</h2>")[1].split("<h2>")[0]
    assert section.index("We built this description by reading") < section.index("<table")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_target_brief_html.py -q -k "what_we_read"`
Expected: FAIL — `assert "<table>" in section`, because the section is a `<ul>`.

- [ ] **Step 3: Convert `_group_a`**

Replace the `items` loop and the return statement. Keep the whole docstring and
both existing comments verbatim — they carry the uncapped ruling and the
empty-directory measurement.

```python
    rows = []
    for group in groups:
        # Conditional: every toy group has `directory == ""` -- the three inputs
        # share their whole directory, so nothing survives the prefix strip -- and
        # unconditionally this printed `... under : notes.md` with an empty span.
        #
        # The leading space is load-bearing: the suite pins
        # `' under <span class="file">docs</span>'` with it, and inside a `<td>` it
        # is invisible.
        where = (
            f' under <span class="file">{esc(group.directory)}</span>'
            if group.directory
            else "—"  # The stated absence. The bullet form hid it by having no clause.
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
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_target_brief_html.py -q`
Expected: PASS, including `test_page_omits_the_directory_clause_when_there_is_no_directory`
(line 166), `test_page_relabels_every_input_kind_rather_than_shipping_the_token`
(185), `test_page_ships_an_off_schema_kind_raw_rather_than_inventing_a_label`
(223), `test_page_states_an_unnamed_input_file_rather_than_an_empty_row` (237)
and `test_page_counts_the_pieces_a_sliced_input_was_read_as` (742) — all five
read this section and none of them asserts `<li>`.

- [ ] **Step 5: Check the off-schema kind still gets a neutral chip**

Run: `uv run pytest tests/unit/test_target_brief_html.py -q -k off_schema -v`
Expected: PASS. That test writes a kind outside the enum and asserts the token
ships raw. Confirm by eye that it lands in `kind-other` and not in a hue that
implies we recognised it.

- [ ] **Step 6: Check and commit**

```bash
make check
git add src/rubrica/target_brief_html.py tests/unit/test_target_brief_html.py
git commit -S -s -F - <<'MSG'
feat: Render "What we read" as a table with a kind chip

Three columns -- what kind, where, the files -- replacing a bullet per group. The
count sentence stays above the table, because it is what gives a reader the size
before they wade into an uncapped listing, and the listing stays uncapped for the
reason it always was: the file the owner would have named is the one behind an
"and 24 more".

The pieces count stays inside the Where cell rather than becoming a column. A column
would print a number for every group, and the existing ruling is that two counts
appear only when they differ -- "199 files, read as 269 pieces" is a fact, "3 files,
read as 3 pieces" is arithmetic nobody asked for.

The leading space in the ` under <file>` clause is kept deliberately: the suite pins
it, and inside a table cell it is invisible.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
```

---

## Task 3: The disagreements become an index table plus per-dispute tables

This is the section the change exists for: 41 disputes over 123 bullets today,
with nothing to scan.

**Files:**
- Modify: `src/rubrica/target_brief_html.py` — `_side_html` and `_group_bc`.
- Modify: `tests/unit/test_target_brief_html.py` — line 862's occurrence count.
- Test: `tests/unit/test_target_brief_html.py`

**Interfaces:**
- Consumes: `_table`, `_row`, `_chip`, `_STATUS_CHIP` from Task 1.
- Produces:
  - `_status_chip(resolution: str) -> str` — the chip for one `resolution`,
    falling back to the undecided chip for any value outside `_STATUS_CHIP`.
  - `_side_rows(refs, label: str) -> list[str]` replaces `_side_html`: it
    returns rows for the per-dispute table instead of a `<p>` plus `<ul>`.

- [ ] **Step 1: Write the failing tests**

```python
def test_disagreements_lead_with_an_index_table_of_every_dispute(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    section = page.split("Where our sources disagree")[1].split("What we could not tell")[0]
    assert "<th>#</th>" in section
    assert "<th>Status</th>" in section
    assert "<th>What kind of disagreement</th>" in section
    assert "<th>Files involved</th>" in section
    # The toy world records exactly one contradiction, so the index has one row
    # and its number is 1 -- positional, never the recorded id.
    assert '<span class="num">1</span>' in section


def test_the_index_never_prints_a_recorded_dispute_id(tmp_path):
    """`Dispute.id` is the run's own string. The existing no-identifier test covers
    the page as a whole; this one covers the column that would most naturally have
    been filled with it."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    recorded = world_model["contradictions"][0]["id"]
    page = target_brief_html.render(run)
    assert recorded not in page


def test_each_dispute_shows_its_two_sides_as_a_table_of_source_and_quote(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    section = page.split("Where our sources disagree")[1].split("What we could not tell")[0]
    assert "<th>Side</th>" in section
    assert "<th>Source</th>" in section
    assert "<th>What it says</th>" in section
    assert "<td>One side</td>" in section
    assert "<td>The other side</td>" in section


def test_an_undecided_dispute_carries_the_amber_chip_and_says_so(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["contradictions"][0]["resolution"] = "unresolved"
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    assert 'class="undecided"' in page
    assert ">Undecided<" in page
    assert "We have not decided between them." in page


def test_a_settled_dispute_carries_the_settled_chip_and_names_the_file(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["contradictions"][0]["resolution"] = "preferred_a"
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    assert 'class="settled"' in page
    assert ">Side chosen<" in page
    assert "We went with " in page


def test_an_off_enum_resolution_reads_as_undecided_and_asserts_no_decision(tmp_path):
    """`_taken` returns "" for anything outside the three values it knows, so the
    chip must agree with it without either consulting the other. A colour that said
    "settled" over a sentence that said "we have not decided" would be the page
    asserting a decision nobody made."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["contradictions"][0]["resolution"] = "something_new"
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    assert 'class="undecided"' in page
    assert "We have not decided between them." in page
    assert 'class="settled"' not in page
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_target_brief_html.py -q -k "disagreements or index_never or two_sides or undecided_dispute or settled_dispute or off_enum"`
Expected: FAIL — no `<th>#</th>`, no chips.

- [ ] **Step 3: Add `_status_chip` and replace `_side_html` with `_side_rows`**

Insert `_status_chip` above `_side_rows`:

```python
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
```

Now replace `_side_html` wholesale with `_side_rows`. **Keep every comment in the
body verbatim** — they carry the `#/126` slice measurement, the
`_file_and_piece` ruling and the missing-quote count:

```python
def _side_rows(refs, label: str) -> list[str]:
    """One side of a disagreement, as rows of a source-and-quote table.

    Was `_side_html`, which returned a `<p>` plus a `<ul>`. The rows carry the same
    three facts and let the reader compare the two sides down a column, which is the
    comparison the section is asking them to make and the one a pair of nested
    bullet lists made hardest.

    `Dispute.side_a` is a `tuple[SourceRef, ...]`, not a sentence. Rendering it
    through `esc()` directly would print the dataclass repr and put
    `claim_id='clm-notes-004'` on a page whose entire premise is that no rubrica
    identifier appears on it.

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
        # second reading of the same path here.
        base, piece = target_brief._file_and_piece(ref.path)
        # A path with nothing nameable in it rendered as a blank
        # `<span class="file">` -- measured on a hand-edited world model, reachable
        # only there because `SourceRef.path` falls back to the artifact id. The
        # phrase is `_files_html`'s, which already counts the files it could not
        # name in the section above.
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
```

- [ ] **Step 4: Rewrite `_group_bc`**

```python
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
            target_brief._file_and_piece(ref.path)[0]
            for ref in (*dispute.side_a, *dispute.side_b)
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
        index_rows.append(
            _row(f'<span class="num">{position}</span>', chip, nature, involved)
        )
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
```

- [ ] **Step 5: Fix the pinned occurrence count at line 862**

`test_page_keeps_a_hash_in_the_owners_own_filename_whole` asserts
`page.count('<span class="file">notes#2.md</span>') == 2`. The index table now
names the same file again, so the count rises. Run the test, read the actual
number, and set it to that — then confirm the assertion that carries the real
ruling, `'<span class="file">notes</span>' not in page`, is still there and still
passes. Add one line to that test's docstring recording why the number changed.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/unit/test_target_brief_html.py -q`
Expected: PASS. Watch these in particular:
`test_page_renders_the_toy_contradiction_with_both_files_named` (102),
`test_page_says_an_undecided_disagreement_is_undecided` (278),
`test_page_labels_the_nature_of_a_disagreement_rather_than_leading_with_it` (294),
`test_page_says_it_could_not_resolve_a_side_rather_than_dropping_it` (590),
`test_page_says_a_side_is_stated_in_a_file_it_could_not_name` (610),
`test_page_labels_a_slice_of_a_file_rather_than_juxtaposing_the_fragment` (806).

Two of those carry assertions worth naming, both already accounted for above:

- **294** pins the exact strings `"The disagreement: the operator notes state"`
  and `"The disagreement: count_mismatch"`. The `<h3>` in Step 4 carries that
  label, which is why it is there. Do not delete this test: it records that a
  bare `count_mismatch` token reads as a sentence we wrote badly rather than as
  a category we were handed.
- **806** asserts `"piece" not in page` — **page-wide, not section-scoped**. It
  holds because no group in that fixture has slices, so Task 2's conditional
  `"(read as N pieces)"` never renders there. Any new prose anywhere on the page
  containing the substring `piece` breaks it. If it goes red, the fix is your
  new wording, not the assertion.

- [ ] **Step 7: Check and commit**

```bash
make check
git add src/rubrica/target_brief_html.py tests/unit/test_target_brief_html.py
git commit -S -s -F - <<'MSG'
feat: Give the disagreements an index table and tabulate both sides

41 disputes over 123 bullets on run-20260826-090456, with nothing to scan and no
way to see which are still open. The index table answers that first -- number,
status chip, what kind of disagreement, files involved -- and the detail stays whole
beneath it, because the two verbatim quotes are what let an owner settle a dispute
and shortening them takes away the thing they are being asked to rule on.

Each side becomes rows of a Side / Source / What it says table, so the reader
compares the two down a column. That is the comparison this section asks for and
the one nested bullet lists made hardest. The label repeats down a multi-ref side
rather than spanning it: a rowspan over a side that resolved to no refs is a branch
whose edge case is invisible until an owner meets it, and that empty case is real.

An off-enum resolution reads as undecided, agreeing with _taken -- which returns ""
for any value it does not know -- by both defaulting to "we did not decide" rather
than by consulting each other. A chip claiming a decision above a sentence denying
one would be the page asserting a judgment nobody made.

Numbering is positional. Dispute.id is the run's own string and never reaches the
page, which a new test pins directly at the column that would most naturally have
carried it.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
```

---

## Task 4: "What we could not tell" becomes a table

**Files:**
- Modify: `src/rubrica/target_brief_html.py` — `_group_d`.
- Test: `tests/unit/test_target_brief_html.py`

**Interfaces:**
- Consumes: `_table`, `_row` from Task 1.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

```python
def test_what_we_could_not_tell_is_a_numbered_table_of_questions(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    section = page.split("What we could not tell")[1].split("What we believe, in full")[0]
    assert "<th>#</th>" in section
    assert "<th>The question</th>" in section
    assert "<th>Our reference</th>" in section
    assert '<span class="num">1</span>' in section
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_target_brief_html.py -q -k could_not_tell`
Expected: FAIL — no `<th>` in the section.

- [ ] **Step 3: Convert `_group_d`**

Keep the docstring and the whole measured comment about question-before-label:

```python
    rows = []
    for position, q in enumerate(found, start=1):
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
        #
        # It is now a column, which is the same ruling expressed in a grid: the
        # question is the wide first column and our reference is the narrow last
        # one, so the eye reaches the question before the slug on every row.
        # The words "our reference:" and the parentheses stay in the cell, not just
        # in the column heading. `test_page_renders_an_open_question_as_a_question`
        # and `test_page_states_a_gap_that_records_no_question` both pin the exact
        # string `(our reference: X)`, and what they are pinning is that the label is
        # named as *ours* -- a column heading a reader skims past does not carry that.
        ref = (
            f'<span class="ident">(our reference: {esc(q.subject)})</span>'
            if q.subject
            else "—"
        )
        # No run has yet produced a gap with no `unknown`, so this is the branch
        # for an artifact that was written outside the schema rather than one
        # observed: state the absence, never leave a row holding only our id.
        asked = esc(q.unknown) or "We did not record what it was that we could not tell."
        rows.append(_row(f'<span class="num">{position}</span>', asked, ref))
    return (
        "<p>These are things we could not work out from what we read. They are "
        "questions, not criticisms.</p>"
        + _table(("#", "The question", "Our reference"), rows)
    )
```

The reference cell keeps the words `our reference:` and its parentheses.
`test_page_renders_an_open_question_as_a_question` (line 706) and
`test_page_states_a_gap_that_records_no_question` (765) both pin the exact string
`(our reference: X)`, and the ruling they record is that the label is named as
*ours* — which a column heading a reader skims past does not do. An em dash
stands in when there is no subject, so the column never has a silently empty
cell.

Test 706 also asserts, page-wide, that `"propose"` does not appear: `blocks` is a
list of stage names and `why_it_matters` is us talking about ourselves, and
`OpenQuestion` carries neither. Nothing you add in this task may contain that
substring.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_target_brief_html.py -q`
Expected: PASS.

- [ ] **Step 5: Check and commit**

```bash
make check
git add src/rubrica/target_brief_html.py tests/unit/test_target_brief_html.py
git commit -S -s -F - <<'MSG'
feat: Render the open questions as a numbered table

Question in the wide first column, our own reference in the narrow last one. That
is the existing ruling expressed as a grid rather than a change to it: the label
trails because `subject` is a bare slug or an id-prefixed phrase on every run
measured, and leading with it put an identifier in the recipient's eye ahead of the
question. The eye still reaches the question first on every row.

An em dash stands in where a question carries no subject, so the column never has a
silently empty cell.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
```

---

## Task 5: The three collapsed sections become tables, with provenance chips

**Files:**
- Modify: `src/rubrica/target_brief_html.py` — `_provenance`, `_operations`,
  `_data_types`, `_personas`.
- Modify: `tests/unit/test_target_brief_html.py` — the four tests that assert
  `<dl>`/`<dt>`/`<dd>`, at lines 648, 875, 994 and 1019.
- Test: `tests/unit/test_target_brief_html.py`

**Interfaces:**
- Consumes: `_table`, `_row`, `_chip` from Task 1.
- Produces:
  - `_where(prov) -> str` — the "Where we read it" cell: the chips this element
    earns, followed by `_provenance(prov)`'s existing sentence.

**The four tests you are rewriting encode measured rulings. Keep every ruling and
change only the markup it is asserted against.** They are:

| Line | Test | Ruling it records |
|---|---|---|
| 648 | `…states_each_empty_belief_rather_than_rendering_an_empty_list` | Five empty branches are sentences, not empty containers. The docstring's `<dl>` reference becomes "an empty table". |
| 875 | `…states_that_it_could_not_place_a_belief_rather_than_leaving_it_blank` | An element whose files did not resolve says so; five blank `<dd></dd>` rows shipped once. Assert the sentence in the new cell. |
| 994 | `…heads_an_operation_on_its_handle_when_the_operation_string_is_blank` | A whitespace-only `operation` must not head an entry with a blank; the handle takes over. |
| 1019 | `…states_an_operation_it_could_not_name_rather_than_heading_it_blank` | When neither name is nameable, the heading states the absence and the other columns still say what the operation does. |

- [ ] **Step 1: Write the failing tests**

```python
def test_the_three_detail_sections_are_tables(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    assert "<th>Operation</th>" in page
    assert "<th>Called as</th>" in page
    assert "<th>Takes</th>" in page
    assert "<th>What can come back</th>" in page
    assert "<th>Where we read it</th>" in page
    assert "<th>What it is</th>" in page
    assert "<th>Held as</th>" in page
    assert "<th>Fields</th>" in page
    assert "<th>Who</th>" in page
    assert "<th>What they are trying to do</th>" in page


def test_an_element_resting_on_one_source_says_so_in_a_chip(tmp_path):
    """Measured on run-20260826-090456 through the helpers that render it: 28 of 30
    entities and 4 of 39 operations rest on a single source. It varies, which is
    why it earns a chip -- a badge that never varies implies a distinction was
    checked."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    # Every element in the golden toy world rests on one file.
    assert 'class="one-source"' in page
    assert ">One source only<" in page


def test_a_disputed_element_keeps_its_phrase_and_gains_the_chip(tmp_path):
    """The phrase is pinned by
    `test_page_relabels_the_kinds_and_flags_the_dispute_in_a_multi_source_line`,
    so the chip carries it verbatim rather than replacing it with a shorter word."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["capabilities"][0]["claims"] = ["clm-api-001", "clm-notes-004"]
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    assert 'class="disputed"' in page
    assert "our sources disagree about this" in page
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_target_brief_html.py -q -k "three_detail or one_source or disputed_element"`
Expected: FAIL — no `<th>Operation</th>`, no `class="one-source"`.

- [ ] **Step 3: Add `_where` and trim `_provenance`**

`_provenance` keeps its whole docstring and its whole empty-files comment. Change
only its last two statements — the disputed clause moves into `_where` as a chip
so the fact is stated once:

```python
    files = ", ".join(f'<span class="file">{esc(f)}</span>' for f in prov.files)
    if prov.single_source:
        text = f"From {files}"
    else:
        kinds = ", ".join(esc(_kind(k)) for k in prov.kinds)
        text = f"From {len(prov.files)} sources ({kinds}): {files}"
    return f'<span class="src">{text}.</span>'


def _where(prov) -> str:
    """The "Where we read it" cell: the chips this element earns, then the sentence.

    Two chips, both recorded and both measured to vary on run-20260826-090456
    through these same helpers -- single-source is 28 of 30 entities and 4 of 39
    operations, disputed is 4 of 30 and 6 of 39. That is the whole test for whether
    something may be coloured here: `Provenance`'s docstring records that
    `derivation` and `confidence` were built as badges and dropped because both come
    out identical on every row, and that a badge which never varies "implies a
    distinction was checked".

    The disputed chip carries the full phrase `our sources disagree about this`
    rather than a shorter word, because the suite pins that phrase and it is the
    clause `_provenance` used to append. Stating it once, as a chip, is the same fact
    in the place a reader scans for it.
    """
    chips = []
    if prov.files and prov.single_source:
        chips.append(_chip("one-source", "One source only"))
    if prov.disputed:
        chips.append(_chip("disputed", "our sources disagree about this"))
    return "".join(chips) + _provenance(prov)
```

`prov.files and prov.single_source`: with no files at all, `_provenance` already
says it could not work out where the element came from, and a "One source only"
chip above that sentence would contradict it.

- [ ] **Step 4: Convert `_operations`**

Keep every comment in the existing body. In particular, the comment block above
`handle = op.handle.strip()` runs from the line beginning
`# \`sentence\` (the \`operation\` string) heads the entry, not \`handle\`.` down to the
line ending `# can still recognise the operation by.` — roughly 30 lines. It is the
measurement behind the three assignments under it (the shared-handle finding, the
whitespace-only `operation` hole, and the both-blank case), and it moves across
unchanged. The code below shows those three assignments without it only so the diff
is readable; do not drop it.

```python
    rows = []
    for op in found:
        params = esc(", ".join(op.params)) if op.params else "Takes no parameters."
        outcomes = "".join(
            # A description can be `""` -- Task 5's handoff -- and `label:` with
            # nothing after it reads as prose that got truncated. The label is
            # still a fact about the target, so it stays and the absence is stated.
            f'<div class="oc"><em>{esc(o.label)}</em>'
            + (f": {esc(o.description)}" if o.description else " — we did not record what happens")
            + "</div>"
            for o in op.outcomes
        ) or "We did not record what can come back."
        handle = op.handle.strip()
        title = op.sentence.strip() or handle
        # The bare handle, with the label carried by the column heading rather than
        # repeated down 39 rows. `test_page_names_the_handle_under_both_toy_operations`
        # pins `"Called as: query_tickets<"` twice; Step 6 updates it to count
        # `"<td>query_tickets</td>"` instead, which is the same ruling -- the handle is
        # shown when it differs from the title and once when it does not -- against
        # the new markup.
        called = esc(handle) if handle and handle != title else "—"
        heading = esc(title) if title else "One operation whose name we did not record"
        rows.append(_row(f"<strong>{heading}</strong>", called, params, outcomes, _where(op.provenance)))
    return _table(
        ("Operation", "Called as", "Takes", "What can come back", "Where we read it"), rows
    )
```

Add `.oc { margin: .1rem 0; }` to `_CSS` beside the chip rules.

- [ ] **Step 5: Convert `_data_types` and `_personas`**

```python
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
        extra = [f'<div class="oc">Related to: {esc(r)}</div>' for r in kind.relations]
        extra += [f'<div class="oc">Rule we believe holds: {esc(r)}</div>' for r in kind.rules]
        rows.append(_row(f"<strong>{esc(kind.name)}</strong>", held, fields,
                         "".join(extra) or "—", _where(kind.provenance)))
    return _table(
        ("What it is", "Held as", "Fields", "Rules and relations", "Where we read it"), rows
    )
```

`_personas`, keeping its whole docstring:

```python
    rows = []
    for persona in found:
        goals = "".join(f'<div class="oc">{esc(goal)}</div>' for goal in persona.goals) or (
            "We did not record what they are trying to do."
        )
        rows.append(_row(f"<strong>{esc(persona.name)}</strong>", goals, _where(persona.provenance)))
    return _table(("Who", "What they are trying to do", "Where we read it"), rows)
```

- [ ] **Step 6: Rewrite the four markup-pinned tests**

Run them first and read each failure:

Run: `uv run pytest tests/unit/test_target_brief_html.py -q -k "empty_belief or could_not_place or heads_an_operation or could_not_name"`

For each, change only the markup the assertion names and keep the ruling:
- 648: **no assertion changes.** Its `<dl>` is in the docstring only; every
  assertion is one of the five sentences, which is the ruling and is untouched.
  Reword the docstring's "an empty `<dl>`" to "an empty table".
- 875: assert the sentence `We could not work out which of your files this came from.`
  is present and that no `<td></td>` is. An empty cell is the new shape of the
  blank `<dd></dd>` that shipped once.
- 994 and 1019: assert on the cell contents — `<strong>query_tickets</strong>`
  and `<strong>One operation whose name we did not record</strong>` — and assert
  `"<td></td>" not in page` and `"<strong> </strong>" not in page`, which is the
  blank-heading hole in its new spelling.

- [ ] **Step 7: Run the whole suite**

Run: `uv run pytest tests/unit/test_target_brief_html.py -q`
Expected: PASS. `test_page_distinguishes_two_operations_that_share_a_handle`
(123), `test_page_names_the_handle_under_both_toy_operations` (132),
`test_page_names_the_collection_each_data_type_lives_in` (149),
`test_page_labels_an_outcome_that_carries_no_description` (259),
`test_page_states_a_user_with_no_goal_and_an_operation_with_no_parameter` (686)
and `test_page_states_a_field_whose_type_we_did_not_record` (1073) all read these
three sections.

**Test 132 will fail, and Step 6 is where you fix it.** It pins
`page.count("Called as: query_tickets<") == 2`, then `== 1` for the positive
control. Replace both with `page.count("<td>query_tickets</td>")`, same numbers.
That preserves the ruling exactly — the handle appears twice when it differs from
both titles, once when one operation's title has become the handle itself — while
dropping a label the column heading now carries.

- [ ] **Step 8: Check and commit**

```bash
make check
git add src/rubrica/target_brief_html.py tests/unit/test_target_brief_html.py
git commit -S -s -F - <<'MSG'
feat: Tabulate the description and chip what an element rests on

The three collapsed sections become tables, which is where 71 dt/dd pairs on
run-20260826-090456 were least readable: an operation's parameters, outcomes and
sources are four facts about one thing, and a definition list stacks them instead of
lining them up against the next operation's.

Two chips, and the test for whether anything may be coloured here is the one
Provenance's docstring already set: it records that derivation and confidence were
built as badges and dropped because both come out identical on every row, and that a
badge which never varies "implies a distinction was checked". These two vary,
measured through the helpers that render them -- single-source is 28 of 30 entities
and 4 of 39 operations, disputed is 4 of 30 and 6 of 39.

The disputed clause moves out of _provenance's sentence and into a chip carrying the
identical phrase, so the fact is stated once in the place a reader scans for it. No
one-source chip when there are no files at all: _provenance already says it could not
work out where the element came from, and a chip above that sentence would contradict
it.

Four tests that pinned dl/dt/dd markup are rewritten against the new shape, ruling
for ruling: an empty branch is still a sentence and not an empty container, an
unplaceable element still says so, and a blank operation name is still stated rather
than heading a row with nothing in it.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
```

---

## Task 6: The ranked asks table, the page-level guards, and the gates

**Files:**
- Modify: `src/rubrica/target_brief_html.py` — the asks paragraph in `render`.
- Test: `tests/unit/test_target_brief_html.py`
- Check, and modify only if they no longer read true: `CLAUDE.md`,
  `docs/reference/cli.md`.

**Interfaces:**
- Consumes: `_table`, `_row` from Task 1.
- Produces: the finished page.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_asks_are_a_ranked_table_of_three(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    section = page.split("What we most need from you")[1].split("<h2>")[0]
    assert "<th>Rank</th>" in section
    assert "<th>What we need</th>" in section
    assert "<th>Where it is</th>" in section
    # `_reply()` refers back to "the three things we asked for at the top are
    # ranked", so the table must have exactly three rows for that to stay true.
    assert section.count("<tr>") == 4  # one header row plus three


def test_a_populated_page_carries_no_bullet_list(tmp_path):
    """The regression guard for the whole change. Measured against a run that
    reaches every section, because a fixture that reaches only some would let a
    bullet survive in the sections it never renders."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    # The positive control: the page is populated, so there is something to have
    # rendered as a bullet in the first place.
    assert "<table" in page
    assert "<li>" not in page
    assert "<ul>" not in page
    assert "<dl>" not in page
    assert "<dt>" not in page


def test_no_severity_vocabulary_reaches_the_page(tmp_path):
    """Colour on this page encodes recorded status and kind. It never encodes a
    severity we assigned, and the words that would announce one are the cheapest
    thing to check for. `blocks` is the field that would most naturally have become
    a severity axis, and its values are stage names."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run).lower()
    for word in ("severity", "critical", "high priority", "p1", "blocker", "urgent"):
        assert word not in page, word


def test_a_marker_section_keeps_its_heading_and_renders_no_table(tmp_path):
    """A section that cannot be read keeps its heading and says so. `_table` returns
    "" for no rows, so the failure this guards is a header row standing over nothing
    -- which reads as a render that broke rather than as a fact we do not have."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    run.world_model.unlink()
    page = target_brief_html.render(run)
    for heading in (
        "Where our sources disagree",
        "What we could not tell",
        "What it can do",
        "What data it holds",
        "Who uses it",
    ):
        assert heading in page
    # The five world-model sections are gone, so the only tables left are the asks
    # and what we read -- never an empty grid where a section used to be.
    assert "<th>Status</th>" not in page
    assert "<th>Operation</th>" not in page
    assert 'class="banner"' in page


def test_every_table_on_the_page_has_a_header_row(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    assert page.count("<table") == page.count("<thead>")
    assert page.count("<table") >= 6
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_target_brief_html.py -q -k "ranked_table or no_bullet or severity or header_row or marker_section"`
Expected: FAIL — `<th>Rank</th>` missing, and `"<li>" not in page` failing until
every earlier task has landed.

- [ ] **Step 3: Replace the asks paragraph in `render`**

Replace the single `<p>Three things, in the order they help us most: …</p>` and
keep the comment above it, extended:

```python
        "<h2>What we most need from you</h2>",
        # The draft left this heading with nothing under it, and on all three
        # recordings it rendered as a bare rule above the next heading -- the one
        # place on the page that read as a section that had failed to fill in.
        # Its counterpart below ("What we believe, in full") always had its lead
        # sentence, so this is the sentence that was missing rather than a new
        # tier. It also states the ranking that the reply block refers back to.
        #
        # Now a table, because the ranking *is* tabular: three asks, in order, each
        # pointing at the section that answers it. The sentence stated an order the
        # reader then had to hold; the table shows it. Three rows exactly -- `_reply`
        # says "the three things we asked for at the top are ranked", and
        # `CLAUDE.md` and `docs/reference/cli.md` both say three ranked asks lead.
        _table(
            ("Rank", "What we need", "Where it is"),
            [
                _row("1", "A source we should have read", "What we read"),
                _row("2", "A place our sources disagree", "Where our sources disagree"),
                _row("3", "Something we could not work out", "What we could not tell"),
            ],
        ),
```

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest tests/unit/test_target_brief_html.py -q`
Expected: PASS, every test.

- [ ] **Step 5: Measure the no-bullets guard in both directions**

In a scratch copy of the module under `RUBRICA_SKILLS_DIR`-style isolation (or
simply edit, test, revert), change one `_table(...)` call back to a `<ul>` and
confirm `test_a_populated_page_carries_no_bullet_list` goes red naming it. Revert
and confirm green. Do the same for one chip: drop its word and confirm
`test_a_chip_always_carries_its_word` fails.

- [ ] **Step 6: Run the full gates**

```bash
make test
make check
uv run rubrica check-skills; echo "check-skills exit: $?"
uv run pytest tests/unit/test_docs_accuracy.py -q
```
Expected: all green, `check-skills exit: 0`.

- [ ] **Step 7: Check the two documents still read true**

```bash
grep -n -A8 'target-brief` is a report too' CLAUDE.md
sed -n '515,570p' docs/reference/cli.md
```

Both say "Three ranked asks lead". That is still true — the asks are three rows
in the same order. Both describe the page's two load-bearing properties, which
are unchanged. **If either describes the layout as a list, update that clause and
nothing else.** Do not add a sentence about tables to `CLAUDE.md` unless the
existing prose is now wrong: this file is already long, and a layout detail is not
one of the two properties it exists to record.

- [ ] **Step 8: Commit**

```bash
make check
git add src/rubrica/target_brief_html.py tests/unit/test_target_brief_html.py
git commit -S -s -F - <<'MSG'
feat: Rank the three asks in a table and guard the page against bullets

The asks were a sentence stating an order the reader then had to hold. The ranking
is tabular -- three asks, in order, each naming the section that answers it -- so it
is a table now. Exactly three rows, because _reply refers back to "the three things
we asked for at the top" and both CLAUDE.md and cli.md say three ranked asks lead.

Three page-level guards land with it. No bullet list survives on a populated page,
measured against a run that reaches every section, since a fixture reaching only some
would let a bullet live on in the ones it never renders. Every table has a header
row. And no severity vocabulary reaches the page: colour here encodes recorded status
and kind, never a severity we assigned, and gaps[].blocks -- the field that would
most naturally have become that axis -- holds stage names this page may never carry.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
MSG
```

---

## Final verification (run by the orchestrator, not a task)

```bash
make test
make check
uv run rubrica check-skills; echo "check-skills exit: $?"
uv run rubrica target-brief --run /home/bnayahu/work/kaegis/rubrica/runs/run-20260826-090456
```

Then open the page and read it. Check by eye, in both colour schemes:

- Every section is a table with a header row, and nothing is a bullet.
- The 41-row disagreement index scans, and the 15 amber chips are findable.
- No chip is colour-only — each carries its word.
- Nothing on the page names a stage, a gate, an artifact or rubrica.
- The page is still one file with no script and no webfont.
