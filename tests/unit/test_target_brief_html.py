"""The page `target-brief` sends to the target's owners.

Every expected value here was read off a real `build_toy_run(upto="reconcile-seal")`
rather than reasoned about: the toy target is `{"interface": "mcp", "name":
"ticketq"}` with no `notes`, three input groups all with an empty `directory`, two
capabilities that share the handle `query_tickets`, two entities, one actor, one
contradiction resolved `preferred_a`, and no gaps.

Three tests here are the page's premise rather than coverage --
`test_page_never_shows_a_rubrica_identifier`,
`test_the_pages_own_prose_never_names_a_stage_a_gate_or_an_artifact` and
`test_selected_prose_carrying_one_of_our_ids_reaches_the_page_unrewritten`.

The first two hold of this module's *own chrome*, on a corpus whose prose carries no
identifier of ours -- which is what the toy is, measured: `open_questions` is `[]` and
no `clm-`-shaped string reaches the page. They are not a property of a real page. The
controller measured run-20260825-094033's page at about forty distinct `clm-...` ids
and 119 occurrences of `claim`, every one of them inside prose a stage wrote, which
this feature ships verbatim because rewriting it is the one thing the document must
not do. The third test pins that sanctioned exception, so the two above cannot be
read as a promise the page does not make.

A failure in the first two is prose to reword, never an assertion to relax: a
recipient asked "does this describe your system?" who is instead reading about
`01-world-model.json` has been handed the wrong question.
"""

from __future__ import annotations

import json
import os
import re
import shutil

import pytest

from rubrica import target_brief_html
from tests.toy import build_toy_run


def test_page_is_self_contained_and_carries_no_script(tmp_path):
    page = target_brief_html.render(build_toy_run(tmp_path, upto="reconcile-seal"))
    assert page.startswith("<!doctype html>")
    assert page.rstrip().endswith("</html>")
    # Ruling 1: emailed out of the project, so it must read with scripts off.
    assert "<script" not in page.lower()
    # Self-contained: no network, no external asset.
    assert "http://" not in page and "https://" not in page
    assert "<style>" in page


def test_page_names_the_target_and_asks_the_question(tmp_path):
    page = target_brief_html.render(build_toy_run(tmp_path, upto="reconcile-seal"))
    assert "ticketq" in page
    assert "does this accurately describe your system?" in page.lower()
    # The dropped sign-off block must not come back by accident.
    for word in ("sign off", "sign-off", "signature", "approve", "ratif"):
        assert word not in page.lower()


def test_page_leads_with_the_asks_and_puts_the_description_beneath(tmp_path):
    page = target_brief_html.render(build_toy_run(tmp_path, upto="reconcile-seal"))
    # Tier 1 before tier 2: the ask-list is the point, the full description is
    # the appendix that supports it.
    assert page.index("Where our sources disagree") < page.index("What we believe")
    # Tier 2 is collapsed; tier 1 is not.
    body = page[page.index("What we believe") :]
    assert "<details>" in body
    assert "<details>" not in page[: page.index("What we believe")]


def test_page_renders_every_group_and_every_tier_two_section(tmp_path):
    page = target_brief_html.render(build_toy_run(tmp_path, upto="reconcile-seal"))
    for heading in (
        "What we read",
        "Where our sources disagree",
        "What we could not tell",
        "What we believe",
        "What it can do",
        "What data it holds",
        "Who uses it",
    ):
        assert heading in page


def test_page_prints_each_collapsed_heading_exactly_once(tmp_path):
    """Ruling 36. A `<summary>` naming the section plus an `<h2>` naming it again
    inside the same `<details>` prints every tier-2 heading twice to a reader. The
    disclosure control *is* the heading here, so the `<h2>` goes."""
    page = target_brief_html.render(build_toy_run(tmp_path, upto="reconcile-seal"))
    for heading in ("What it can do", "What data it holds", "Who uses it"):
        assert page.count(heading) == 1, heading
        assert f"<h2>{heading}</h2>" not in page, heading
        # The positive control the absence above needs: the heading is still on
        # the page, carried by the control that opens the section.
        assert f"<summary>{heading}</summary>" in page, heading
    # And the tier-1 headings, which are not collapsed, still are `<h2>`s -- so
    # the assertion above is about where a heading lives, not about h2 vanishing.
    assert "<h2>What we read</h2>" in page


def test_page_renders_the_toy_contradiction_with_both_files_named(tmp_path):
    page = target_brief_html.render(build_toy_run(tmp_path, upto="reconcile-seal"))
    # The claim ids dissolve into the files that state them: an owner reads two
    # of their own documents disagreeing, never `clm-notes-004`.
    assert "notes.md" in page and "trace.json" in page
    assert "clm-notes-004" not in page and "clm-trace-002" not in page
    # Each side quotes itself: the locator the owner can jump to, and the line
    # their own document carries. This is what `_side_html` is for -- the naive
    # `esc(dispute.side_a)` puts a dataclass repr here and fails the line above.
    assert "#error-behaviour" in page
    assert "not an empty result" in page
    # `resolution` is `preferred_a`, so the page names the file it went with.
    assert "We went with" in page
    # A locator is labelled rather than dropped into bare parentheses: side_b's is
    # the raw JSON pointer `#/spans/1/output`, and Task 3 measured `#/126` shapes
    # on a real run. Both sides asserted, because side_b carries no quote and so
    # takes `_side_html`'s path-plus-locator branch.
    assert "(at #error-behaviour)" in page
    assert "(at #/spans/1/output)" in page


def test_page_distinguishes_two_operations_that_share_a_handle(tmp_path):
    """Both toy capabilities carry `binding.tool == "query_tickets"`, so heading
    each entry on the handle prints the same word twice and the reader cannot tell
    which operation is which. The `operation` string is what distinguishes them."""
    page = target_brief_html.render(build_toy_run(tmp_path, upto="reconcile-seal"))
    assert "query_tickets.find_tickets" in page
    assert "query_tickets.get_ticket" in page


def test_page_names_the_handle_under_both_toy_operations(tmp_path):
    """Ruling 34. Measured on the toy: `handle` is `query_tickets` and `sentence`
    is `query_tickets.find_tickets`, so the two differ and the conditional is True
    for both capabilities -- the brief's comment claiming it never fires was wrong.
    The handle is kept because it is the name the owner's own tooling uses."""
    page = target_brief_html.render(build_toy_run(tmp_path, upto="reconcile-seal"))
    assert page.count("Called as: query_tickets<") == 2
    run = build_toy_run(tmp_path / "same", upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    # The positive control for the conditional: an operation whose sentence is
    # already the handle says it once, not twice.
    world_model["capabilities"][0]["operation"] = "query_tickets"
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    assert page.count("Called as: query_tickets<") == 1


def test_page_names_the_collection_each_data_type_lives_in(tmp_path):
    """Ruling 37. `collection` is the one `DataType` field that is the owner's own
    word rather than ours -- measured `tickets` and `comments` on the toy -- and the
    brief's `_data_types` never read it."""
    page = target_brief_html.render(build_toy_run(tmp_path, upto="reconcile-seal"))
    assert "tickets</span>" in page and "comments</span>" in page
    run = build_toy_run(tmp_path / "bare", upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    del world_model["entities"][0]["collection"]
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    # Absent, so no empty row -- and the positive control is the sibling entity,
    # which still names its own collection on the same page.
    assert "tickets</span>" not in page
    assert "comments</span>" in page


def test_page_omits_the_directory_clause_when_there_is_no_directory(tmp_path):
    """Ruling 33. Every toy group has `directory == ""` -- the three inputs share
    their whole directory, so nothing survives the prefix strip -- and an
    unconditional clause prints `... under : notes.md` with an empty span."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    assert " under <span" not in page
    # The positive control: the group whose clause was suppressed is still listed.
    assert "notes.md" in page
    manifest = json.loads(run.manifest.read_text())
    for record in manifest["inputs"]:
        name = record["source_path"].rsplit("/", 1)[-1]
        record["source_path"] = f"/corpus/docs/{name}" if name == "notes.md" else f"/corpus/{name}"
    run.manifest.write_text(json.dumps(manifest))
    page = target_brief_html.render(run)
    # `/corpus` is the shared prefix, so `docs` is what is left of one group's path.
    assert ' under <span class="file">docs</span>' in page


def test_page_relabels_every_input_kind_rather_than_shipping_the_token(tmp_path):
    """No machine kind token reaches the page -- scoped, because a blanket version
    of this cannot be written honestly.

    `trace` is a substring of the target's own `trace.json` and `other` is a
    substring of this page's own "The other side", so asserting either token absent
    fails on a correct page. For those two the guard is the same-test positive
    control this repo requires -- their *label* is on the page -- which is **weaker
    than absence**: a page carrying both the label and the raw token would pass.
    The other five are guarded by absence, `openapi` as a bare word because it is a
    substring of nothing here but could become one in a label.

    Each of the seven is written into the manifest in turn so that no assertion is
    vacuous for want of that kind in the toy corpus: only `design_doc`,
    `mcp_tool_schema` and `trace` occur in it.
    """
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    manifest = json.loads(run.manifest.read_text())
    labels = {
        "openapi": "HTTP API description",
        "mcp_tool_schema": "MCP tool definitions",
        "entity_schema": "Data model definitions",
        "trace": "Recorded interactions",
        "design_doc": "Written documentation",
        "source_code": "Source code",
        "other": "Other material",
    }
    for kind, label in labels.items():
        manifest["inputs"][0]["kind"] = kind
        run.manifest.write_text(json.dumps(manifest))
        page = target_brief_html.render(run)
        assert label in page, kind
        if kind == "openapi":
            assert not re.search(r"\bopenapi\b", page, re.IGNORECASE), kind
        elif kind not in ("trace", "other"):
            assert kind not in page, kind


def test_page_ships_an_off_schema_kind_raw_rather_than_inventing_a_label(tmp_path):
    """`.get(kind, kind)`, for `_OUTCOME_LABELS`' reason: a label we do not have is
    no reason to drop or rename a fact about the target."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    manifest = json.loads(run.manifest.read_text())
    manifest["inputs"][0]["kind"] = "grimoire"
    run.manifest.write_text(json.dumps(manifest))
    page = target_brief_html.render(run)
    assert "grimoire" in page
    # The positive control: the kinds we do have labels for are still relabelled on
    # the same page, so the line above is the fallback and not the table breaking.
    assert "Recorded interactions" in page


def test_page_states_an_unnamed_input_file_rather_than_an_empty_row(tmp_path):
    """Task 3 measured one group with a blank filename row on a real run.
    `inputs_read` keeps such a record on purpose -- `len(files) + slices` is its
    arithmetic against the run's own record of what it read -- so the renderer has
    to say what it is rather than print an empty monospace span."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    manifest = json.loads(run.manifest.read_text())
    manifest["inputs"].append({"artifact_id": "", "source_path": "", "kind": "design_doc"})
    # A whitespace-only path is the same defect one `.strip()` further out, and it is
    # schema-conforming where the empty one is not: measured pre-fix, this record
    # rendered `<span class="file"> </span>` in this listing -- the stray punctuation
    # `_files_html`'s docstring says it exists to prevent.
    manifest["inputs"].append({"artifact_id": "sp", "source_path": " ", "kind": "design_doc"})
    run.manifest.write_text(json.dumps(manifest))
    page = target_brief_html.render(run)
    assert "2 more we could not name" in page
    assert '<span class="file"></span>' not in page
    assert '<span class="file"> </span>' not in page
    # The positive control: the named file in the very same group still renders.
    assert "notes.md" in page


def test_page_labels_an_outcome_that_carries_no_description(tmp_path):
    """`Outcome.description` can be `""` -- Task 5's handoff -- and the label alone
    followed by a colon reads as prose that got truncated."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["capabilities"][0]["outcome_classes"][0]["description"] = ""
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    assert "we did not record what happens" in page
    # The colon sits outside the emphasis, so the brief's drafted `<em>label:</em>`
    # shape would print `On success:</em>`. The string this line carried before the
    # review -- `On success:</em></dd>` -- matched neither rendering: the drafted one
    # put a space and the description after `</em>`, so it asserted nothing.
    assert "On success:</em>" not in page
    # The positive control: the sibling outcome, whose description is intact,
    # still renders as label plus description.
    assert "no ticket matches the filters" in page


def test_page_says_an_undecided_disagreement_is_undecided(tmp_path):
    """Ruling 26 resolved: no B/C partition. `taken` is `""` for `unresolved`, and
    silence after two contradicting sides reads as a decision the reader missed."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    # The positive control, on the golden world: a resolved dispute names its file.
    assert "We went with notes.md." in page
    assert "We have not decided between them." not in page
    world_model = json.loads(run.world_model.read_text())
    world_model["contradictions"][0]["resolution"] = "unresolved"
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    assert "We have not decided between them." in page
    assert "We went with notes.md." not in page


def test_page_labels_the_nature_of_a_disagreement_rather_than_leading_with_it(tmp_path):
    """Task 4's handoff: `nature` is sometimes a machine token (`count_mismatch`,
    `incompatible_precondition` were seen on real runs) rather than a sentence. It
    is carried verbatim either way -- this document never rewrites prose -- so the
    label is what stops a token reading as a sentence we wrote."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    assert "The disagreement: the operator notes state" in page
    world_model = json.loads(run.world_model.read_text())
    world_model["contradictions"][0]["nature"] = "count_mismatch"
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    assert "The disagreement: count_mismatch" in page


def test_page_states_a_marker_instead_of_dropping_the_section(tmp_path):
    """A partial run must produce a page that says what it has not got to, in the
    owner's words -- not a page missing a section, which is indistinguishable from
    a renderer that forgot one."""
    run = build_toy_run(tmp_path, upto="extract")
    page = target_brief_html.render(run)
    assert "What we believe" in page
    assert "not got far enough" in page
    # An operator's artifact name is not something an owner can act on.
    assert "01-world-model.json" not in page


def test_page_states_the_partial_run_once_and_still_shows_every_section(tmp_path):
    """Five world-model-backed sections carry the identical marker when one file is
    unreadable, and five panels tell the owner five times that one thing is
    missing. One banner says it; each section keeps its heading and a short line
    pointing at the banner, so nothing silently disappears."""
    run = build_toy_run(tmp_path, upto="extract")
    page = target_brief_html.render(run)
    assert page.count("not got far enough") == 1
    assert page.count("see the note at the top of this page") == 5
    for heading in (
        "Where our sources disagree",
        "What we could not tell",
        "What it can do",
        "What data it holds",
        "Who uses it",
    ):
        assert heading in page
    # The positive control the count above needs: the one section that is not
    # world-model-backed is not a marker at all on this run, so the five is five
    # sections rather than every section on the page.
    assert "notes.md" in page


def test_page_states_an_unreadable_input_record_in_full_rather_than_pointing_up(
    tmp_path,
):
    """The terse "see the note at the top" line is only correct for a section whose
    marker is the one the banner states. `What we read` reads the run's own record
    of what it read, not the description, so its marker is a second fact and says
    the whole thing in place."""
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    run.manifest.chmod(0o000)
    try:
        page = target_brief_html.render(run)
    finally:
        run.manifest.chmod(0o644)
    assert "could not read it back" in page
    assert "see the note at the top of this page" not in page
    # The positive control: the description is intact and rendered, so the marker
    # above is one section's and not the whole page's.
    assert "query_tickets.get_ticket" in page


def test_page_banners_an_unreadable_claims_directory_once(tmp_path):
    """Task 1 returns a marker rather than an empty index, so the page must say
    the citations are missing rather than render as a confident description with
    no sources."""
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    run.claims_dir.chmod(0o000)
    try:
        page = target_brief_html.render(run)
    finally:
        run.claims_dir.chmod(0o755)
    assert page.count('class="banner"') == 1
    assert "could not read" in page.lower()
    # It still describes the target: the banner qualifies the page, not the read.
    assert "ticketq" in page and "What it can do" in page


def test_page_carries_the_legend_only_when_a_phrasing_it_glosses_appears(tmp_path):
    """Both triggers, and the golden toy as the control for both: its page carries
    neither our `Not addressed` label nor the idiom a stage writes, so the legend is
    off, and each mutation below turns it on by itself.

    The idiom is the trigger that matters. Measured on run-20260826-090456: 110
    occurrences of `No claim`, against a label the same page never uses -- so a
    legend glossing only the label was a legend for the phrasing the recipient meets
    least."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    assert 'class="legend"' not in target_brief_html.render(run)
    world_model = json.loads(run.world_model.read_text())
    world_model["capabilities"][0]["outcome_classes"][0]["kind"] = "underspecified"
    run.world_model.write_text(json.dumps(world_model))
    assert 'class="legend"' in target_brief_html.render(run)
    # The label reverted, so the second trigger is measured on its own rather than on
    # a page the first has already turned the legend on for.
    world_model["capabilities"][0]["outcome_classes"][0]["kind"] = "success"
    world_model["gaps"] = [
        {
            "id": "gap-reopen",
            "subject": "reopen-timer",
            "unknown": "No claim directly addresses whether a reopen resets the timer.",
            "blocks": [],
        }
    ]
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    assert 'class="legend"' in page
    # And the third spelling, which the same substring has to fire: the stages write
    # this idiom at least three ways and a legend that fires on one of them is a
    # legend absent from most pages that need it.
    world_model["gaps"][0]["unknown"] = (
        "Whether a reopen resets the timer: no claim explicitly states this."
    )
    run.world_model.write_text(json.dumps(world_model))
    assert 'class="legend"' in target_brief_html.render(run)


def test_the_legend_glosses_both_phrasings_and_leads_the_section_carrying_them(tmp_path):
    """Spec 2 mandates a gloss of the idiom, and the words are pinned literally here
    rather than through `target_brief_html._LEGEND`: the ban test's exemption is that
    constant, whatever it says, so a reword that quietly stopped glossing one of the
    two phrasings would pass every other test in this module. This is the pin that
    reddens instead."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["gaps"] = [
        {
            "id": "gap-reopen",
            "subject": "reopen-timer",
            "unknown": "No claim directly addresses whether a reopen resets the timer.",
            "blocks": [],
        }
    ]
    world_model["capabilities"][0]["outcome_classes"][0]["kind"] = "underspecified"
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    # Both phrasings glossed, and the word the legend exists to explain is in it: a
    # legend that avoided `claim` would be explaining a word it never names.
    assert "no claim addresses something" in page
    assert "directly addresses it, or explicitly states it" in page
    assert "a “claim” is one statement we recorded while reading them" in page
    assert "An outcome labelled “Not addressed” says the same thing." in page
    assert "Neither means the behaviour is missing from your system." in page
    # Above the lines it glosses, and inside the ask that carries most of them.
    assert page.index("What we could not tell") < page.index('class="legend"')
    assert page.index('class="legend"') < page.index("No claim directly addresses")
    assert page.index('class="legend"') < page.index("What we believe, in full")


def test_page_escapes_owner_controlled_prose(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["target"]["notes"] = '<script>alert("x")</script>'
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    assert "<script" not in page.lower()
    assert "&lt;script&gt;" in page


def test_page_renders_a_lone_surrogate_rather_than_failing_to_write(tmp_path):
    """`summary.esc` is the one place that decides this, and it is why this module
    escapes everything through it -- a `UnicodeEncodeError` from `write_text` is a
    ValueError that escaped every handler but the catch-all once."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["target"]["notes"] = "bad \udcff byte"
    run.world_model.write_text(json.dumps(world_model))
    out = tmp_path / "brief.html"
    out.write_text(target_brief_html.render(run), encoding="utf-8")  # must not raise
    assert "bad" in out.read_text(encoding="utf-8")


def test_page_never_shows_a_rubrica_identifier(tmp_path):
    """No id shape in anything this module puts on the page itself.

    Scoped to the toy deliberately, and the scope is the finding the review made
    against this docstring: `open_questions` is `[]` on the golden build, so the one
    place the renderer *chooses* to print an id of ours -- `(our reference: ...)`,
    where `subject` is an `ent-... / inv-...` pair in 10 of 12 gaps on
    run-20260816-172810 -- is not reached from here at all. It is reached, and
    asserted, in
    `test_selected_prose_carrying_one_of_our_ids_reaches_the_page_unrewritten`.
    What this test holds is that no builder leaks one into a page built from prose
    that has none."""
    page = target_brief_html.render(build_toy_run(tmp_path, upto="reconcile-seal"))
    leaked = re.findall(r"\b(?:clm|cap|ent|act|goal|gap|con|oc|art)-[a-z0-9-]+", page)
    assert leaked == [], leaked


def test_page_drops_the_target_name_rather_than_showing_the_run_directory(tmp_path):
    """`run.root.name` is `run-20260827-115248` -- measured on a toy build -- which
    is rubrica's own identifier for the work and not a name the owner has ever
    seen. A page whose `<h1>` is that has handed the recipient the wrong subject."""
    run = build_toy_run(tmp_path, upto="extract")
    page = target_brief_html.render(run)
    assert run.root.name not in page
    assert "The system we are describing" in page
    # The positive control: the run's name is on the page when the description
    # gives us one, so the line above is the fallback and not the name vanishing.
    full = build_toy_run(tmp_path / "full", upto="reconcile-seal")
    assert "<h1>ticketq</h1>" in target_brief_html.render(full)


def test_the_pages_own_prose_never_names_a_stage_a_gate_or_an_artifact(tmp_path):
    """The renderer's own chrome, measured on a corpus whose prose carries none of
    these words: no heading, label or sentence this module writes names a stage, a
    gate, an artifact or rubrica itself.

    Not a property of a real page, and the name says so. `claim` occurs 119 times on
    run-20260825-094033's page, all of it inside prose a stage wrote and this feature
    ships verbatim -- see the module docstring, and
    `test_selected_prose_carrying_one_of_our_ids_reaches_the_page_unrewritten` for the
    sanctioned exception pinned rather than assumed. What this test can hold, and
    does, is that the words are not ours.

    One exemption, and it is exactly one string wide. `_LEGEND` glosses the idiom
    *"no claim addresses X"* for a recipient who would otherwise read it as a
    statement about their system, so it cannot avoid the word `claim` -- a legend that
    did would be explaining a word it never names. Dropping `claim` from the list
    below instead would exempt every future piece of chrome along with it, so the
    legend is subtracted from the page by its own constant: whatever `_LEGEND` says is
    exempt, and nothing else is. That the legend still says the right thing is
    `test_the_legend_glosses_both_phrasings_and_leads_the_section_carrying_them`'s job,
    with the words pinned literally there so a reword reddens rather than silently
    widening this hole.

    The page is rendered with the legend *on*, by relabelling one outcome rather than
    by writing prose that carries a banned word: a page the legend is absent from
    would run this loop without ever meeting the string it exempts, and the exemption
    would be the decoration this project calls fixture-cannot-reach."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["capabilities"][0]["outcome_classes"][0]["kind"] = "underspecified"
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run).lower()
    assert target_brief_html._LEGEND.lower() in page
    page = page.replace(target_brief_html._LEGEND.lower(), "")
    assert 'class="legend"' not in page
    for word in (
        "reconcile",
        "extract",
        "triage",
        "world model",
        "claim",
        "artifact",
        "gate",
        "manifest",
        "rubrica",
        "scenario",
    ):
        assert word not in page, word


def test_page_relabels_the_kinds_and_flags_the_dispute_in_a_multi_source_line(tmp_path):
    """`_provenance`'s two-source branch is unreachable on the golden toy -- every
    element there rests on one file, so `single_source` is True for all of them and
    neither the kind list nor the disputed flag is ever rendered. Both are reached
    here by giving one operation a claim from each of two files, one of which the
    toy's contradiction names."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    # The positive control, on the golden world: the one-source line is what is
    # rendered instead, so the absences below are the branch and not the line.
    assert "From <span" in page
    assert "From 2 sources" not in page
    assert "our sources disagree about this" not in page
    world_model = json.loads(run.world_model.read_text())
    world_model["capabilities"][0]["claims"] = ["clm-api-001", "clm-notes-004"]
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    assert "From 2 sources (Written documentation, MCP tool definitions):" in page
    assert "design_doc" not in page and "mcp_tool_schema" not in page
    # `clm-notes-004` is one side of the toy's contradiction, so the element now
    # rests on a disputed claim and says so.
    assert "our sources disagree about this" in page


def test_page_says_it_could_not_resolve_a_side_rather_than_dropping_it(tmp_path):
    """Ruling 7: an unreadable record of where we read things must never render as
    a positive statement that no evidence exists. With no sources resolvable both
    sides of the toy's disagreement say so, and the banner above says why."""
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    # The positive control: with the record readable, both sides name their file.
    assert "we could not resolve which file states it" not in page
    assert "One side is stated in:" in page
    run.claims_dir.chmod(0o000)
    try:
        page = target_brief_html.render(run)
    finally:
        run.claims_dir.chmod(0o755)
    assert page.count("we could not resolve which file states it") == 2
    assert "One side is stated in:" not in page


def test_page_says_a_side_is_stated_in_a_file_it_could_not_name(tmp_path):
    """A whitespace-only `source_path` rendered a blank `<span class="file">` beside
    a quote from it -- measured on a hand-edited manifest, and reachable only there
    because `SourceRef.path` falls back to the artifact id. The phrase is
    `_files_html`'s, which already counts the files it could not name one section
    above, so nothing new is invented for it.

    Every assertion is scoped to the disagreement section. The same hand-edited path
    also reaches a tier-2 provenance line through `Provenance.files`, which this
    round does not cover -- a page-wide assertion here would pin that as intended.
    """

    def disagreement(page):
        start = page.index("Where our sources disagree")
        return page[start : page.index("What we could not tell", start)]

    run = build_toy_run(tmp_path, upto="reconcile-seal")
    section = disagreement(target_brief_html.render(run))
    # The positive control: with the path readable the side names the file and the
    # phrase below is nowhere on the page.
    assert '<span class="file">notes.md</span>' in section
    assert "a file we could not name" not in section
    manifest = json.loads(run.manifest.read_text())
    for record in manifest["inputs"]:
        if record["artifact_id"] == "notes-md":
            record["source_path"] = "   "
    run.manifest.write_text(json.dumps(manifest))
    section = disagreement(target_brief_html.render(run))
    assert "a file we could not name (at #error-behaviour)" in section
    # No blank in either place the section had one: the side line, and the sentence
    # under it that read `We went with  .`.
    assert not re.search(r'<span class="file">\s*</span>', section)
    assert not re.search(r"We went with\s+\.", section)
    # The quote is still shown, so the side is stated rather than dropped for want
    # of a filename.
    assert "an id no ticket has is an **error**" in section


def test_page_states_each_empty_belief_rather_than_rendering_an_empty_list(tmp_path):
    """Five `not found` branches no golden run reaches, because the toy world has
    inputs, capabilities, entities, an actor and one contradiction. Each is a
    sentence rather than an empty `<dl>`: a section with nothing in it reads as a
    render that broke.

    The contradiction branch is the one a real run reaches most often -- most runs
    record none -- and it is the most delicate paragraph on the page, since "nothing
    contradicted anything" is what a reader will hear as "your documents agree".
    Under branch coverage it was the one sentence here no test rendered."""
    empty = (
        "We have no record of what we read.",
        "We did not identify anything it can be asked to do.",
        "We did not identify the kinds of data it holds.",
        "We did not identify who uses it.",
        "Nothing we read contradicted anything else we read.",
    )
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    # The positive control for all four: the golden page carries the content, so
    # none of the four sentences below is on it.
    for sentence in empty:
        assert sentence not in page, sentence
    manifest = json.loads(run.manifest.read_text())
    manifest["inputs"] = []
    run.manifest.write_text(json.dumps(manifest))
    world_model = json.loads(run.world_model.read_text())
    world_model["capabilities"] = []
    world_model["entities"] = []
    world_model["actors"] = []
    world_model["goals"] = []
    world_model["contradictions"] = []
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    for sentence in empty:
        assert sentence in page, sentence


def test_page_states_a_user_with_no_goal_and_an_operation_with_no_parameter(tmp_path):
    """Two more branches the golden toy cannot reach: its one actor has two goals
    and both its operations take parameters."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    # The positive controls: the golden page renders the goals and the parameters,
    # so neither sentence below is on it.
    assert "We did not record what they are trying to do." not in page
    assert "Takes no parameters." not in page
    assert "Explain why a ticket is stuck" in page
    assert "ticket_id (integer, required)" in page
    world_model = json.loads(run.world_model.read_text())
    world_model["goals"] = []
    del world_model["capabilities"][1]["params"]
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    assert "We did not record what they are trying to do." in page
    assert "Takes no parameters." in page


def test_page_renders_an_open_question_as_a_question(tmp_path):
    """`open_questions` returns `[]` on the golden toy -- measured -- so the branch
    that renders one is unreached without a gap written in."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    # The positive control: the empty case is what the golden page says instead.
    assert "We did not record any open question." in page
    world_model = json.loads(run.world_model.read_text())
    world_model["gaps"] = [
        {
            "id": "gap-retention",
            "subject": "How long a closed ticket is kept",
            "unknown": "Nothing we read says when a closed ticket is removed.",
            "blocks": ["propose"],
            "why_it_matters": "internal prose the page must not show",
        }
    ]
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    assert "How long a closed ticket is kept" in page
    assert "Nothing we read says when a closed ticket is removed." in page
    assert "We did not record any open question." not in page
    # The question leads, our label for it trails and is named as ours. Measured on
    # run-20260825-094033, every one of the 19 subjects is a slug like
    # `outbox-approval-invariant`, so the draft's bolded-subject lead put a rubrica
    # id where the question belongs.
    assert page.index("Nothing we read says when a closed ticket is removed.") < page.index(
        "(our reference: How long a closed ticket is kept)"
    )
    assert "<strong>How long a closed ticket is kept</strong>" not in page
    # `why_it_matters` is rubrica talking about itself and `blocks` is a list of
    # stage names; `OpenQuestion` carries neither, and this is where that shows.
    assert "internal prose the page must not show" not in page
    assert "propose" not in page


def test_page_counts_the_pieces_a_sliced_input_was_read_as(tmp_path):
    """`slices` is 0 for every toy group -- measured -- so both halves of "we read
    199 files as 269 pieces" are unreachable without a sliced input written in. The
    arithmetic matters on a real run: Task 3 measured 71 of parsec's inputs as 71
    `#/NN` slices of one capture, and listing them as 71 files would misstate it."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    # The positive controls: with nothing sliced, the page states one count only.
    assert "3 files of yours." in page
    assert "separate pieces" not in page
    assert "pieces)" not in page
    manifest = json.loads(run.manifest.read_text())
    sliced = dict(next(r for r in manifest["inputs"] if r["kind"] == "trace"))
    sliced["source_path"] = sliced["source_path"] + "#/spans/0"
    sliced["artifact_id"] = sliced["artifact_id"] + "-0"
    manifest["inputs"].append(sliced)
    run.manifest.write_text(json.dumps(manifest))
    page = target_brief_html.render(run)
    # Still three files -- the fragment is cut before grouping -- read as four.
    assert "3 files of yours, read as 4 separate pieces." in page
    assert "(read as 2 pieces)" in page


def test_page_states_a_gap_that_records_no_question(tmp_path):
    """No run has produced a gap with an empty `unknown` -- 0 of the 49 questions in
    the three recordings -- so the branch that states that absence is only reachable
    from an artifact written outside the schema."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["gaps"] = [
        {"id": "gap-1", "subject": "retention-policy", "unknown": "", "blocks": []},
        {
            "id": "gap-2",
            "subject": "escalation-path",
            "unknown": "Nothing we read says who a stuck ticket goes to.",
            "blocks": [],
        },
    ]
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    assert "We did not record what it was that we could not tell." in page
    assert "(our reference: retention-policy)" in page
    # The positive control: the neighbouring gap of the same shape still renders its
    # question, so this is a statement about one empty field and not a broken section.
    assert "Nothing we read says who a stuck ticket goes to." in page
    assert "(our reference: escalation-path)" in page


def test_each_tier_heading_is_followed_by_prose(tmp_path):
    """Both tier headings introduce sections rather than carrying content of their
    own, so each needs its own lead sentence. Rendered on all three recordings, the
    draft's `What we most need from you` sat directly above the next `<h2>` -- the
    one place on the page that read as a section that had failed to fill in."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    for heading in ("What we most need from you", "What we believe, in full"):
        tag = f"<h2>{heading}</h2>"
        assert tag in page
        after = page[page.index(tag) + len(tag) :].lstrip()
        # Structural rather than a phrase pin: what must hold is that prose follows,
        # not which words it uses.
        assert after.startswith("<p"), heading


def test_page_labels_a_slice_of_a_file_rather_than_juxtaposing_the_fragment(tmp_path):
    """Task 4's handoff. Every toy `source_path` is a whole file, so the fragment a
    sliced input carries -- measured as `trajectories2.json#/10` on
    run-20260816-172810 -- only reaches a side line once one is written in."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    manifest = json.loads(run.manifest.read_text())
    trace = next(r for r in manifest["inputs"] if r["kind"] == "trace")
    trace["source_path"] = trace["source_path"] + "#/spans/1"
    run.manifest.write_text(json.dumps(manifest))
    page = target_brief_html.render(run)
    # The file is the owner's, the index into it is ours, and the locator sits in
    # the same clause because both answer "where inside your material".
    assert "(piece #/spans/1, at #/spans/1/output)" in page
    assert "trace.json#/spans/1</span> (at" not in page
    # The positive control: the sibling side of the same disagreement is not a
    # slice, so it carries a locator and no piece -- the label is about a fragment
    # in the path, not about every source line on the page.
    assert "notes.md</span> (at #error-behaviour)" in page
    # And a path that is *nothing but* a fragment keeps it as the only name there
    # is, rather than being labelled a piece of an empty file. `intake` cannot
    # write this shape (`intake.py:333` builds the fragment from a `Path`, which
    # never stringifies empty), so a hand-edited manifest is the only way in --
    # which is also why `_common_prefix` carries a filter for it.
    trace["source_path"] = "#/spans/1"
    run.manifest.write_text(json.dumps(manifest))
    page = target_brief_html.render(run)
    assert '<span class="file">#/spans/1</span> (at #/spans/1/output)' in page
    assert "piece" not in page
    # The positive control again, on the same page: the unsliced sibling is
    # untouched by the fragment-only branch.
    assert "notes.md</span> (at #error-behaviour)" in page


def test_page_keeps_a_hash_in_the_owners_own_filename_whole(tmp_path):
    """A `#` in a filename is not the slicer's fragment.

    `intake.py:333` writes a sliced input's `source_path` as
    `<container>#<json_pointer>`, and a JSON pointer always begins `/`, so a `#`
    followed by anything else belongs to the name the owner gave the file. Nothing
    forbids one there.

    Measured on the pre-fix renderer, with the toy's trace input renamed
    `notes#2.md`: the disagreement's side line read `<span class="file">notes</span>
    (piece #2.md, at #/spans/1/output)` and the `What we read` listing said `notes`.
    Two fabrications in the two sections whose whole ask is "did we read the right
    files" -- a file of that name we never read, and a piece of it that does not
    exist."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    manifest = json.loads(run.manifest.read_text())
    trace = next(r for r in manifest["inputs"] if r["kind"] == "trace")
    original = trace["source_path"]
    trace["source_path"] = original.replace("trace.json", "notes#2.md")
    run.manifest.write_text(json.dumps(manifest))
    page = target_brief_html.render(run)
    # Both places the name reaches: the listing of what we read, and the side of the
    # disagreement the trace states. Two, so neither can be the one that passes.
    assert page.count('<span class="file">notes#2.md</span>') == 2
    assert "piece #2.md" not in page
    assert '<span class="file">notes</span>' not in page
    # The positive control, in the same test: a real slicer fragment on the same path
    # is still labelled a piece and still collapses to one file, so the clause tells
    # the two shapes apart rather than switching the labelling off.
    trace["source_path"] = original + "#/spans/1"
    run.manifest.write_text(json.dumps(manifest))
    page = target_brief_html.render(run)
    assert "(piece #/spans/1, at #/spans/1/output)" in page
    assert '<span class="file">trace.json</span>' in page


def test_page_states_that_it_could_not_place_a_belief_rather_than_leaving_it_blank(
    tmp_path,
):
    """`Provenance.files` empty renders a sentence, not nothing.

    Reached with `01-claims/` *removed* rather than unreadable, which is the case
    that has no banner over it: `paths.list_dir` returns `[]` for a missing directory,
    so `source_index` returns `{}` and `_sources_banner` stays silent. Measured
    pre-fix on exactly this run: five `<dd></dd>` rows and no banner anywhere, so a
    reader met five beliefs about their system with the space where our evidence goes
    left empty -- which reads as us having none.

    Saying it is safe in both directions because `world-model-0.1.json`'s
    `$defs/claim_refs` is `minItems: 1`: an element that conforms cites at least one
    claim, so an empty `files` can only mean we failed to resolve them."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    # The positive control, on the golden run: the same rows carry a file, so the
    # sentence below is one this page states only when it cannot name one.
    assert 'From <span class="file">api.json</span>' in page
    assert "could not work out which of your files" not in page
    shutil.rmtree(run.claims_dir)
    page = target_brief_html.render(run)
    assert page.count("We could not work out which of your files this came from.") == 5
    assert "<dd></dd>" not in page
    # The condition the run is in: no banner fired, which is why the sentence has to
    # stand on its own rather than point up at one.
    assert 'class="banner"' not in page


def test_page_says_it_has_not_got_far_enough_when_the_record_of_what_it_read_is_absent(
    tmp_path,
):
    """The Absent, non-terse marker -- Ruling 3's sentence, quoted in the module
    docstring, and reachable only through `_group_a` on a run whose `manifest.json`
    is absent while the description is readable.

    The review measured it dead under the whole suite: a `raise` in its place, 88
    passed. The test that looked like its guard asserts `"not got far enough" in
    page` on an `upto="extract"` run, where that phrase comes from
    `_description_banner`'s different sentence -- substring-of-message, and the reason
    this test unlinks the manifest on a *sealed* run instead."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    run.manifest.unlink()
    page = target_brief_html.render(run)
    assert "We have not got far enough to describe this yet." in page
    # Absent and Malformed are two facts. Neither the Malformed sentence nor the
    # terse form of either is on this page, so the sentence above is this marker's
    # and not any other's.
    assert "could not read it back" not in page
    assert "see the note at the top of this page" not in page
    # The positive control: the description is intact and rendered, so one section
    # says what it has not got to while the rest of the page describes the target.
    assert "query_tickets.get_ticket" in page


def test_page_banners_an_unreadable_description_and_marks_each_section_malformed(
    tmp_path,
):
    """The whole Malformed world-model path: `_description_banner`'s Malformed branch
    and `_marker`'s terse Malformed branch, both measured dead by the review (a
    `raise` in either, 35 passed).

    Its sibling at `test_page_states_the_partial_run_once_and_still_shows_every_
    section` is the Absent half of the same shape, and the two prose sets share no
    sentence -- which is the global rule that Absent and Malformed are two facts, as
    a pair of tests rather than as a comment."""
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    run.world_model.chmod(0o000)
    try:
        page = target_brief_html.render(run)
    finally:
        run.world_model.chmod(0o644)
    assert "could not read it back, so the sections below are empty" in page
    assert "a fault at our end and not a statement about your system" in page
    assert page.count("Nothing to show here — ") == 5
    # Not the Absent prose: "yet" is the whole difference between the two terse
    # markers, and the banner's own sentence differs from the Absent banner's.
    assert "Nothing to show here yet" not in page
    assert "not got far enough" not in page
    # The positive control: `What we read` reads the manifest, which is readable, so
    # the five above are five sections and not the whole page.
    assert "notes.md" in page


def test_selected_prose_carrying_one_of_our_ids_reaches_the_page_unrewritten(tmp_path):
    """The sanctioned exception to the two tests above, pinned rather than assumed.

    Two shapes, one test. An id inside prose a stage wrote ships verbatim, because
    "selected and relabelled, never rewritten" is this feature's constraint and a
    filter narrow enough to be safe would drop genuine questions. And `subject` --
    an `ent-... / inv-...` pair in 10 of 12 gaps on run-20260816-172810 -- reaches the
    page inside `(our reference: ...)`, which is ours by choice: 47 of 49 subjects
    across the three recordings are the only stable handle a commenting owner can
    quote back at us, and the label names it as ours rather than passing it off as
    the target's vocabulary."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    # The control the pair above never had: on a build whose gaps are empty, neither
    # shape is on the page at all, so what follows is the gap arriving and not the
    # renderer printing ids of its own accord.
    assert "our reference" not in page
    assert "clm-" not in page
    world_model = json.loads(run.world_model.read_text())
    world_model["gaps"] = [
        {
            "id": "gap-close",
            "subject": "ent-ticket / inv-close-once",
            "unknown": "Nothing we read says whether clm-notes-004 still holds after a reopen.",
            "blocks": [],
        }
    ]
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    assert "Nothing we read says whether clm-notes-004 still holds after a reopen." in page
    assert "(our reference: ent-ticket / inv-close-once)" in page


def test_page_heads_an_operation_on_its_handle_when_the_operation_string_is_blank(
    tmp_path,
):
    """`capability.operation` is `minLength: 1`, which admits `" "`: schema-conforming,
    truthy, and enough to shadow a handle the run did read. Measured pre-fix, the
    entry headed itself `<dt> </dt><dd>Called as: query_tickets</dd>` -- a blank name
    where every other empty field in this module is a stated absence.

    `target_brief._rules` stripped for this exact hole one module over, which is the
    precedent rather than a new rule."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    # The positive control: with a real `operation`, that string heads the entry.
    assert "<dt>query_tickets.find_tickets</dt>" in page
    world_model = json.loads(run.world_model.read_text())
    world_model["capabilities"][0]["operation"] = " "
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    assert "<dt> </dt>" not in page
    assert "<dt>query_tickets</dt>" in page
    # And the sibling operation, untouched, still heads itself on its own string --
    # so the fallback is one entry's and not the whole list collapsing onto handles.
    assert "<dt>query_tickets.get_ticket</dt>" in page


def test_page_states_an_operation_it_could_not_name_rather_than_heading_it_blank(tmp_path):
    """The blank-`operation` case above still had a `binding.tool` to fall back to.
    With the binding gone as well, `operations` falls the handle back to the same
    `" "`, and both fields are whitespace at once.

    Measured pre-fix, that entry shipped `<dt></dt><dd>Called as:  </dd>` -- an
    unheaded entry followed by a blank name, on a page whose reader has nobody to ask
    what the entry was. The heading states the absence instead, and what the
    operation does is still rendered beneath it."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world_model = json.loads(run.world_model.read_text())
    world_model["capabilities"][0]["operation"] = " "
    world_model["capabilities"][0].pop("binding", None)
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    assert "<dt></dt>" not in page
    assert "<dt> </dt>" not in page
    # `Called as:` with nothing after it is the second blank, and it goes because the
    # handle it would print is the same unnameable string as the title.
    assert not re.search(r"Called as:\s*</dd>", page)
    assert "One operation whose name we did not record" in page
    # The entry is still an entry: the parameters the run did read are under the
    # stated absence, so the fact survives the missing name.
    assert "<dt>One operation whose name we did not record</dt><dd>Takes:" in page
    # The positive control, on the golden world: neither the stated absence nor a
    # blank heading is on a page whose operations both have names.
    clean = target_brief_html.render(build_toy_run(tmp_path / "clean", upto="reconcile-seal"))
    assert "One operation whose name we did not record" not in clean
    assert "<dt>query_tickets.find_tickets</dt>" in clean


def test_page_drops_a_headline_field_that_holds_only_whitespace(tmp_path):
    """Three `minLength: 1` strings that admit `" "`. Measured pre-fix, with all
    three set to one space: `<h1> </h1>`, `<p class="meta">Reached over  .</p>` and an
    empty `<p> </p>` -- three visible blanks at the top of the page, where the
    no-name branch exists to say what the page is about instead."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    # The positive controls: the golden headline renders all of what it has.
    assert "<h1>ticketq</h1>" in page
    assert '<p class="meta">Reached over mcp.</p>' in page
    world_model = json.loads(run.world_model.read_text())
    world_model["target"]["name"] = " "
    world_model["target"]["interface"] = " "
    world_model["target"]["notes"] = " "
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    assert "<h1> </h1>" not in page
    assert "Reached over" not in page
    assert "<p> </p>" not in page
    # The fallback the stripped name falls back to, so the `<h1>` is not simply gone.
    assert "<h1>The system we are describing</h1>" in page


def test_page_states_a_field_whose_type_we_did_not_record(tmp_path):
    """`Field.type` can be `""` on a world model that fails layer 1, which is a model
    this feature exists to render rather than to reject. Measured pre-fix:
    `Fields: ticket_id (), queue (string), ...` -- a bare pair of brackets, which
    reads as a rendering fault rather than as something we did not record, where the
    sibling outcome path states its absence in words."""
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    page = target_brief_html.render(run)
    # The positive control: with a type, the type is parenthesised after the name.
    assert "Fields: ticket_id (integer)," in page
    world_model = json.loads(run.world_model.read_text())
    world_model["entities"][0]["fields"][0]["type"] = ""
    run.world_model.write_text(json.dumps(world_model))
    page = target_brief_html.render(run)
    assert "ticket_id ()" not in page
    # The name still ships, and its typed siblings in the same list are untouched --
    # so the brackets go and nothing else does.
    assert "Fields: ticket_id, queue (string)," in page
