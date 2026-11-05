# Target brief: Report and Workbook — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `rubrica target-brief` into a single self-contained page with a Report tab that asks for nothing and a Workbook tab that collects answers, exportable as PDF and JSON.

**Architecture:** The reader/renderer split stays. New pure functions go into `target_brief.py`: topics, quick takes, workbook order, visible references, and capability groups. `target_brief_html.py` is restructured into two `<section>`s, plus one inline `<script>` that only toggles, records and exports, and builds no content. Everything the page shows is server-rendered, so the page still reads with scripts off.

**Tech Stack:** Python 3.13 stdlib (`html.parser` for the visible-text test helper), vanilla inline JS, pytest. Node (v24, on PATH) only for a syntax check of the inline script in one test, skipped when absent.

**Spec:** `docs/superpowers/specs/2026-11-05-target-brief-report-and-workbook-design.md`

## Global Constraints

- One file: inline `<style>` and exactly one inline `<script>` with no `src`; no `http://`/`https://` anywhere; no external asset.
- Byte-identical output for identical inputs. No wall-clock in rendered output; `generated` = `manifest.created_utc`.
- Text a reader sees never contains: a rubrica id shape (`clm|cap|ent|act|goal|gap|con|oc|art`-prefixed), the run directory name, or the words reconcile/extract/triage/world model/claim/artifact/gate/manifest/rubrica/scenario/subject. Exception: `_LEGEND`, and prose a stage wrote that ships verbatim. Ids may sit in attributes and the script.
- Prose a stage wrote is selected or trimmed, never rewritten. Sentences we compose are visibly ours.
- No severity vocabulary (`severity`, `critical`, `high priority`, `p1`, `blocker`, `urgent`).
- The Report section contains no answer control, no open-item count, no progress counter.
- left = `claim_a`, right = `claim_b`, always; columns never swap.
- Answer `choice` tokens: `left`, `right`, `both`, `neither`, `yes`, `no_other`, `only_left`, `only_right`, `dont_know`.
- Workbook quotas: undecided 5, confirm 3, questions 2, both_possible 0 (named constants).
- Quick-take thresholds: out-of-date ≥5 losses and ≥75% of settled; source-of-truth ≥5 wins and ≤1 loss; self-contradiction ≥3; busiest topics top 3.
- Every commit `git commit -S -s`, trailer `Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>` placed **before** the sign-off.
- Gates after every task: `make test`, `make check`, `uv run rubrica check-skills`.

## Review Focus

1. **A quote containing `</script>` or `<!--`**: it must not break the page. Covered because all data lives in escaped HTML; the script embeds only constants. Test in Task 4.
2. **Ids containing quotes or `&` placed into `data-` attributes**: `esc` with `quote=True` is used for every attribute. Test in Task 4.
3. **A run with no subjects file or no contradiction parts** (an older run): topic falls back to one group with a marker, and no item is dropped. Test in Task 1.
4. **`localStorage` throws** (sandboxed `file://`, private mode): the page still works. The JS wraps every storage call in try/catch; checked by the JS syntax test plus code review. No browser test.
5. **An off-enum `resolution`**: treated as undecided everywhere (chip, quota kind, badge none, controls). Test in Task 2.

---

### Task 1: Reader — topics, chosen side, headline, visible refs

**Files:**
- Modify: `src/rubrica/target_brief.py` (Dispute, `_taken` → `_chosen`, `disputes`, `OpenQuestion`, `open_questions`)
- Test: `tests/unit/test_target_brief.py`

**Interfaces:**
- Produces:
  - `Dispute` fields: `id, nature, resolution, chosen: str | None` (`"a"|"b"|None`), `side_a, side_b, topic_id: str, topic_label: str, headline: str, ref: str` (`"D<n>"`), `rationale: str`. `taken` is removed.
  - `def kind_of(resolution: str) -> str` returning `"undecided"|"confirm"|"both"`.
  - `OpenQuestion` gains `topic_id: str, topic_label: str, ref: str` (`"Q<n>"`).
  - `def topics(run) -> dict[str, str] | Marker`: subject id → trimmed label (cut at first `:` when present, then stripped; full label otherwise; empty → the id is **not** shown, use `"Other"`).
  - `def contradiction_topics(run) -> dict[str, str]`: contradiction id → subject id, from `run.contradictions_dir` part files (each part's `subject_id`); `{}` on any read failure.
  - `def side_files(refs) -> frozenset[str]`: owner-openable file names via `_file_and_piece(r.path)[0]`, empties dropped.
  - constant `NO_TOPIC = ""` for "Other".

- [ ] **Step 1: Write failing tests** in `tests/unit/test_target_brief.py`:
  - `test_chosen_marks_the_side_and_never_a_file`: `_chosen("preferred_a") == "a"`, `"preferred_b" == "b"`, `"both_possible" is None`, `"unresolved" is None`, `"something_new" is None`.
  - `test_kind_of_reads_an_off_enum_resolution_as_undecided`: `kind_of("x") == "undecided"`, `kind_of("preferred_b") == "confirm"`, `kind_of("both_possible") == "both"`.
  - `test_disputes_carry_their_topic_from_the_part_they_were_written_to`: toy `upto="reconcile-seal"` → the one dispute has `topic_id == "sub-cap-get-ticket"`, `topic_label == "query_tickets.get_ticket"`, `ref == "D1"`, `chosen == "a"`.
  - `test_topic_label_is_trimmed_at_its_first_colon_never_rewritten`: rewrite the subject label to `"Who the parties are: agent, reporter"` → `topic_label == "Who the parties are"`.
  - `test_disputes_fall_back_to_no_topic_when_the_subjects_cannot_be_read`: delete `run.subjects` → `topic_id == NO_TOPIC`, and the dispute is still returned.
  - `test_headline_is_a_short_first_sentence_without_our_ids`: nature `"Short thing. clm-x-001 says more."` → `headline == "Short thing."`; nature `"clm-x says. More."` → `""`; a first sentence of 201 chars → `""`; the toy nature (no period, 108 chars, no id) → the whole nature.
  - `test_open_question_topic_is_the_subject_holding_most_of_its_claims`: inject a gap `{"id":"gap.a","subject":"s","unknown":"u?","claims":["clm-api-001","clm-api-007","clm-notes-004"]}` into the world model → `topic_id == "sub-cap-find-tickets"` (2 of 3), `ref == "Q1"`; a gap with no claims → `NO_TOPIC`.
  - `test_refs_number_items_in_id_order_within_their_kind`: two contradictions `con-b`, `con-a` → refs `D1` for `con-a`, `D2` for `con-b`.
  - Delete `test_taken_names_the_file_rather_than_inferring_the_kind` and `test_taken_says_so_when_the_chosen_side_resolves_to_nothing`, and replace any other `taken` assertions in this file.

- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_target_brief.py`. Expected: the new tests fail (AttributeError or ImportError).

- [ ] **Step 3: Implement.** The headline sentence split is `re.split(r"(?<=[.?!])\s+(?=[A-Z`])", nature.strip(), maxsplit=1)[0]`. Reject the sentence when it is longer than 200 chars or matches `\b(?:clm|cap|ent|act|goal|gap|con|oc|art)-|\bclaim`. When the run carries a `question` string field on the contradiction record, `headline` prefers it (the spec's forward hook). `rationale` comes from the record verbatim via `_text`. Delete `_BOTH_POSSIBLE`; keep `_UNRESOLVED_SIDE` (the renderer uses it). Rewrite the `disputes()` docstring paragraph about ordering: id order stays the canonical order, and the Workbook order lives in `workbook_order`.

- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_target_brief.py`. Expected: PASS (the HTML tests may fail; they are Task 4's).

- [ ] **Step 5: Commit** `feat(target-brief): Read each disagreement's topic, chosen side and reference`

### Task 2: Reader — quick takes and workbook order

**Files:**
- Modify: `src/rubrica/target_brief.py`
- Test: `tests/unit/test_target_brief.py`

**Interfaces:**
- Consumes: Task 1's `Dispute`, `OpenQuestion`, `kind_of`, `side_files`.
- Produces:
  - `@dataclass(frozen=True) class Take: kind: str` (`"stale"|"trusted"|"self"|"topic"`), `subject: str` (file name or topic label), `topic_id: str`, `won: int, lost: int, settled: int, count: int, open: int, item_ids: tuple[str, ...]` (all items the take counts, id order), `examples: tuple[str, ...]` (≤3).
  - `def quick_takes(found: list[Dispute]) -> list[Take]`: order is stale (by losses desc, then name), trusted (wins desc), self (count desc), topic (top 3 by count desc, then label).
  - `def workbook_order(found: list[Dispute], questions: list[OpenQuestion], takes: list[Take]) -> list[str]`: the ids of the first `min(10, total)` items, in display order.
  - Constants: `STALE_MIN_LOSSES = 5`, `STALE_MIN_SHARE = 0.75`, `TRUSTED_MIN_WINS = 5`, `TRUSTED_MAX_LOSSES = 1`, `SELF_MIN = 3`, `TOPIC_TAKES = 3`, `WORKBOOK_QUOTAS = (("undecided", 5), ("confirm", 3), ("question", 2), ("both", 0))`, `WORKBOOK_SIZE = 10`, `EXAMPLES = 3`.

Algorithm notes, which the tests alone don't settle:
- Same-file: `side_files(a) == side_files(b)` and `len == 1`. Otherwise cross-file. For a settled cross-file pair, credit a win to every file in `winner − loser` and a loss to every file in `loser − winner`. `settled` = wins + losses for that file.
- Stale fires when `lost >= 5 and lost / settled >= 0.75`. Its examples are losses only. Trusted fires when `won >= 5 and lost <= 1`; its examples are wins.
- Examples, in every case: undecided first, then by id, take 3.
- Topic takes skip `NO_TOPIC` and any topic with count < 2. `open` = undecided count in the topic.
- Workbook: build each kind's list sorted by (touches-a-take desc, topic-size desc, id). A dispute touches a take when a take's file is in its side files or a take's `topic_id` equals its topic; a question touches one when its topic is a take's topic. Fill slots by quota, then redistribute unused slots in order undecided→confirm→question→both. Then interleave in round-robin order undecided, confirm, question, both, skipping exhausted kinds.

- [ ] **Step 1: Write failing tests.** Build `Dispute` objects directly with a helper `_d(id, files_a, files_b, resolution, topic="t")` whose sides are `SourceRef`s with `path` set to the file name:
  - `test_a_file_losing_five_of_six_looks_stale`: 5 lost and 1 won against `code.sh` (6 disputes) → one `Take(kind="stale", subject="doc.md", lost=5, settled=6)`; its `examples` are 3 of the losses.
  - `test_a_file_losing_four_of_six_does_not`, and `test_a_file_losing_four_of_four_does_not` (below the minimum of 5).
  - `test_a_file_winning_five_and_losing_one_looks_trusted`.
  - `test_a_file_contradicting_itself_three_times_is_a_take`, plus a same-file pair that is not counted toward stale/trusted.
  - `test_a_file_on_both_sides_is_credited_neither`: side a `{x, y}`, side b `{y}`, preferred_a → x won 1, y nothing.
  - `test_topic_takes_are_the_top_three_by_count`.
  - `test_workbook_fills_its_quotas_and_interleaves`: 6 undecided, 4 confirm, 3 questions → 10 ids, kinds in order `U C Q U C Q U C U U`.
  - `test_workbook_hands_unused_slots_on`: 2 undecided, 10 confirm, 0 questions → 2 U + 8 C = 10.
  - `test_workbook_takes_everything_when_there_is_less_than_ten`: 3 total → 3.
  - `test_workbook_prefers_items_touching_a_take`: of two undecided items, the one whose file is a stale take's file comes first even though its id sorts later.
  - No real-run test: the run lives outside the repo. Step 5 measures it by hand and records the numbers in the docstring.

- [ ] **Step 2: Run** them and watch them fail.
- [ ] **Step 3: Implement** `Take`, `quick_takes` and `workbook_order`.
- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_target_brief.py`. Expected: PASS.
- [ ] **Step 5: Measure on the real run** (out of tree, read-only): `uv run python -c "from rubrica.paths import RunPaths; from rubrica import target_brief as t; r=RunPaths('/home/bnayahu/work/dam/work/runs/run-20261103-172151'); d=t.disputes(r); print([(x.kind,x.subject,x.won,x.lost,x.count) for x in t.quick_takes(d)])"`. Expected: stale `docs/triage.md` 3/14, trusted `scripts/post-triage.src.sh` 6/1, self `agents/triage.md` 6, and the top topics. Put the printed numbers in the docstring.
- [ ] **Step 6: Commit** `feat(target-brief): Compute quick takes and the workbook's first ten`

### Task 3: Reader — capability groups

**Files:**
- Modify: `src/rubrica/target_brief.py`
- Test: `tests/unit/test_target_brief.py`

**Interfaces:**
- Produces: `def capability_group(op_id: str) -> str`: for `cap.<seg>.<rest>`, returns `<seg>`; otherwise `""` (the renderer shows `""` as "Other"). And `def grouped_operations(ops: list[Operation]) -> list[tuple[str, list[Operation]]]`, with groups in first-seen order and source order inside each group.

- [ ] **Step 1: Failing tests:** `capability_group("cap.tracker.add-label") == "tracker"`; `capability_group("cap-find-tickets") == ""`; `capability_group("cap..x") == ""`; `grouped_operations` keeps first-seen group order.
- [ ] **Step 2: Run, fail. Step 3: Implement. Step 4: Run, pass.**
- [ ] **Step 5: Commit** `feat(target-brief): Group capabilities by their id's middle segment`

### Task 4: Renderer — Report, Workbook, script, print; rewrite the HTML tests

The biggest task. It is one task because the HTML tests change together with the layout.

**Files:**
- Modify: `src/rubrica/target_brief_html.py` (module docstring, `_CSS`, `_group_bc` → split into `_dispute_card`, `_report_*` and `_workbook_*`, `render`, `_reply`)
- Test: `tests/unit/test_target_brief_html.py`, `tests/unit/test_cli.py` (only if the `<title>` changes; keep the title unchanged: `"<name> — does this describe your system?"`)

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: `render(run) -> str` (unchanged signature). Test helper in the test module: `def visible_text(page: str) -> str` (an `html.parser.HTMLParser` subclass that drops the contents of `<script>`/`<style>` and keeps data only, joined with spaces).

Page structure (exact headings, since tests pin them):
- `<nav class="tabs">` with two `<a href="#report">Report</a>` / `<a href="#workbook">Workbook</a>` links. It works as plain anchors with no JS; JS turns them into tabs.
- `<section id="report">`: `<h2>What it seems to do</h2>` (who uses it: `_personas` table collapsed under `<details><summary>Who uses it</summary>`; then one `<details>` per capability group with `<summary>` `"<Group> (N)"`, where an empty group renders as `Other`); `<h2>What looks off</h2>` (the quick-takes table, columns `What we noticed` / `Examples`, every example a read-only card; when there are no takes, `<p>No pattern stood out across your files.</p>`); `<h2>What we could not find</h2>` (questions grouped by topic, read-only, each row `ref`, `unknown`, `(our reference: subject)`); the invitation `<p class="invite">`; `<h2>Reference</h2>` with `<details><summary>What data it holds</summary>` and `<details><summary>What we read</summary>`.
- `<section id="workbook">`: `<h2>Your answers</h2>`, the lede with "Does this accurately describe your system?", the `<h3>Start here</h3>` block with the counter `<span id="wb-count">`, the buttons `<button type="button" id="wb-print">` / `id="wb-download"`, and the 10 cards; `<h2>Everything else</h2>` with `<details>` per topic for the remaining disputes (filter chips `data-filter="undecided|confirm|both"`), a `<details>` for the remaining questions, and a `<details><summary>Did we miss a source?</summary>` holding `_group_a` plus a free-text card `data-item="missed-source"`; the no-JS note `<p class="nojs">`; `_reply()`.
- A card: `<article class="card" data-item="{esc id}" data-ref="{ref}" data-kind="{kind}">`, `<h4>` = `{ref} · {headline or topic_label + " — " + files a vs files b}`, the sides table (columns `Source`, `What it says`, with column headers `Left` and `Right`; the chosen column gets `<span class="pick">our pick</span>`, and both_possible gives both columns `<span class="maybe">both may hold</span>`), `<details><summary>Our full reasoning</summary>` holding `nature` then `rationale`, then `<fieldset class="answer">` with radio inputs `name="{esc id}" value="{token}"` and `<textarea data-note>`. Fieldsets in the Report are never emitted.
- By-file view (my call, superseding the spec's toggle): "Everything else" is rendered once, grouped by topic, with a static index table above it (`File`, `Disagreements`, `References`) listing each file's refs. No toggle, and no card rendered twice.
- Script (`_JS` constant, one `<script>` block at the end of body): it reads `document.body.dataset.run`, `dataset.digest` and `dataset.generated` (attributes on `<body>`), restores and saves from `localStorage` key `"tb:" + digest`, wires radios and notes, updates `#wb-count` (answered among the first 10), toggles tabs via `location.hash`, filters chips, triggers `window.print()`, and downloads the JSON (spec shape plus `ref`) with `Blob` + `URL.createObjectURL` + `<a download="answers-<name>-<run>.json">`. Before print it adds `class="printing"`, which expands answered cards' `<details>`. It never uses `innerHTML`.
- Print CSS: both sections visible; `.tabs, button, .nojs, fieldset input:not(:checked) + label` hidden; each answered card prints its selected label and note; `details:not([open])` stays collapsed except under `.printing` for answered cards; unanswered "Everything else" groups hidden (`.printing details.untouched{display:none}`).

Remove: "What we most need from you" and its table, "What we believe, in full", the dispute index table, "We went with"/"We have not decided between them." sentences, `_STATUS_CHIP` words in the Report. Keep: `_LEGEND` (placed under "What we could not find" when needed), the banners, markers, `_where`, the chips.

- [ ] **Step 1: Rewrite tests first.** In `tests/unit/test_target_brief_html.py`:
  - Add `visible_text`. Re-point `test_page_never_shows_a_rubrica_identifier`, `test_the_pages_own_prose_never_names_a_stage_a_gate_or_an_artifact` (add `"subject"` to its word list) and `test_page_drops_the_target_name_rather_than_showing_the_run_directory` at `visible_text(page)`. Each docstring records the user's 2026-11-05 ruling and what loosened.
  - New `test_visible_text_helper_still_catches_a_planted_id`: render the toy, inject `<td>clm-x-001</td>` into the page string → the identifier regex over `visible_text` finds it; inject `data-item="clm-x-001"` → it doesn't.
  - Replace `test_page_is_self_contained_and_carries_no_script` with `test_page_is_self_contained_with_one_inline_script`: exactly one `<script>`, no `src=`, no `http://`/`https://`, has `<style>`.
  - New `test_inline_script_parses`: write `_JS` to a tmp file and run `node --check`; skip when `shutil.which("node")` is None.
  - New `test_page_reads_with_scripts_off`: strip `<script>…</script>`; every dispute ref (`D1`), the sides' quote text, and the headings `What it seems to do`, `What looks off`, `What we could not find`, `Your answers`, `Everything else` are present; the nav anchors are present.
  - New `test_the_report_asks_for_nothing`: slice `<section id="report">…</section>` → no `<fieldset`, no `<input`, no `<textarea`, no `wb-count`, and none of `"Undecided"`, `"need your"`, `"answered"` (case-insensitive) in its visible text. Positive control: the workbook slice has a `<fieldset`.
  - New `test_our_pick_badges_the_chosen_side_only`: on the toy (`preferred_a`), the card's Left column holds `class="pick"` and the Right does not; flip to `preferred_b` and it moves; set `unresolved` and no `class="pick"` remains; set `both_possible` and both columns hold `class="maybe"`.
  - New `test_a_same_file_pair_still_shows_which_reading_we_took`: rewrite the toy's contradiction so `claim_b` is `clm-notes-005` (also from notes.md) → the badge sits on exactly one column, and the page text contains no `We went with`.
  - New `test_the_workbook_starts_with_at_most_ten_cards_in_order`: inject 12 contradictions (6 unresolved, 6 preferred_a) plus 3 gaps into the toy world model, with matching `01-contradictions/` parts → the Start-here block's `data-item` sequence equals `target_brief.workbook_order(...)`, length 10.
  - New `test_every_card_carries_its_reference_and_its_id`: `data-item="con-missing-semantics"` and `data-ref="D1"` are present, and `D1` is visible.
  - New `test_a_quote_with_a_closing_script_tag_cannot_escape`: set a claim quote to `</script><script>alert(1)</script>` → `page.count("<script") == 1`.
  - New `test_an_id_with_quotes_is_escaped_in_its_attribute`: contradiction id `a"b&c` → `data-item="a&quot;b&amp;c"`.
  - New `test_the_quick_takes_section_says_when_nothing_stood_out` (the toy has 1 dispute).
  - New `test_page_is_byte_identical_across_two_renders`.
  - New `test_body_carries_the_export_metadata`: `data-run` = the run id, `data-generated` = the manifest `created_utc`; neither in `visible_text`.
  - Update or delete the tests pinning removed structure: `..._leads_with_the_asks_...`, `..._every_group_and_every_tier_two_section`, `..._each_collapsed_heading_exactly_once`, `..._toy_contradiction_with_both_files_named` (keep the file and locator asserts; drop `We went with`), `..._undecided_disagreement_is_undecided`, `..._labels_the_nature_...` (the nature now sits under "Our full reasoning"; keep a label), `..._partial_run_once_...`, `..._legend_...leads_the_section...`, `..._each_tier_heading_...`, `test_disagreements_lead_with_an_index_table...`, `test_the_index_never_prints...` (→ visible text), `test_each_dispute_shows_its_two_sides...`, `test_an_undecided_dispute_carries_the_amber_chip...`, `test_a_settled_dispute...names_the_file`, `test_an_off_enum_resolution...`, `test_the_asks_are_a_ranked_table_of_three` (delete), `test_a_populated_page_carries_no_bullet_list` (keep; takes are a table), `test_a_marker_section_keeps_its_heading...`, `test_page_names_the_target_and_asks_the_question` (keep the forbidden words). Each rewritten test keeps its original *intent*; when a test's premise was the removed structure, delete it and say so in the commit body.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_target_brief_html.py`. Expected: many failures.
- [ ] **Step 3: Implement** the renderer and update the module docstring: the "No JavaScript" paragraph is replaced by the user's ruling plus the no-JS fallback rule; the "own prose" paragraph is rescoped to visible text.
- [ ] **Step 4: Run** `make test`. Expected: PASS, `test_cli.py` included.
- [ ] **Step 5: Measure both ways**, as CLAUDE.md requires, for the three rescoped tests and the Report-asks-nothing test: temporarily add a visible `clm-` id in a Report cell → red; revert → green. Note it in the commit body.
- [ ] **Step 6: Render the real run and check it by eye**: `uv run rubrica target-brief --run /home/bnayahu/work/dam/work/runs/run-20261103-172151 -o /tmp/tb-new.html`. Then use headless Chrome to print a PDF and take screenshots of both tabs with JS on: `google-chrome --headless=new --screenshot=/tmp/tb.png --window-size=1280,2400 file:///tmp/tb-new.html`. Check that the file size and visible first screen are sane.
- [ ] **Step 7: Commit** `feat(target-brief): Split the page into a Report and a Workbook`

### Task 5: Docs and the limitation

**Files:**
- Modify: `docs/reference/cli.md` §`rubrica target-brief`, `CLAUDE.md` (the `target-brief` paragraph), `docs/design/limitations.md` (remove the "We went with X" entry), `docs/guides/invoking-rubrica.md:154` only if it is now wrong.

- [ ] **Step 1: Edit.** cli.md: describe the Report and the Workbook, the 10, the PDF/JSON export, inline script with a no-JS fallback, the visible-text scope of the vocabulary rule, and visible refs instead of `(our reference: …)` as the reply handle (that label still exists). Delete "There is no place on it to record an approval" and replace it with "it records per-item answers, never a ratification of the run". CLAUDE.md: same, compressed. Remove "Three ranked asks lead" and keep the rest of the paragraph's rulings.
- [ ] **Step 2: Run** `make test`, `make check`, `uv run rubrica check-skills`. Expected: all clean (`test_docs_accuracy.py` included).
- [ ] **Step 3: Commit** `docs(target-brief): Describe the Report and Workbook; retire the "We went with" limitation`

### Task 6: Whole-branch review

- [ ] Dispatch one fresh reviewer (`superpowers:requesting-code-review`) over `main..HEAD`, with the spec and plan paths. Fix the confirmed findings, re-run the three gates, and commit.
