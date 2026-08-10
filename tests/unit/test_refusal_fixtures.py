"""The negative fixtures still contain the defects they were built around.

Not a test of any skill -- a test of the fixtures. A contradiction fixture that
lost its contradiction in an edit would let the live refusal test pass forever
for the wrong reason, and nothing would report it. That is the
fixture-cannot-reach shape, and this file is what closes it.
"""

from __future__ import annotations

import json

from testgen.intake import classify
from tests.toy import CONTRADICTION_DIR, GAP_DIR


def test_the_contradiction_fixture_has_three_readable_inputs():
    # Filtered to files: once Task 14's controller step commits
    # recorded/01-world-model.json beside these three, iterdir() also yields
    # that directory, and both the name assertion and classify() (which
    # expects a file) would break on it. The recording is the fixture's
    # output, not one of its inputs, so it is deliberately not part of this
    # listing.
    paths = [p for p in CONTRADICTION_DIR.iterdir() if p.is_file()]
    names = sorted(p.name for p in paths)
    assert names == ["api.json", "notes.md", "trace.json"]
    for path in paths:
        assert classify(path) in {"mcp_tool_schema", "design_doc", "trace"}


def test_the_notes_and_the_trace_disagree_about_the_unknown_id_case():
    """The defect the fixture exists to carry. Asserted on the artifacts, so an
    edit that reconciles them by accident fails here rather than silently
    turning the live test into a tautology.

    Strengthened from a bare `assert "error" in notes`: measured against
    tests/fixtures/toy/notes.md, the golden fixture -- deliberately *not* the
    unresolvable one -- which also contains "error" (in its own "Error
    behaviour" section) and would satisfy that predicate. A predicate
    satisfiable by the fixture it was built to differ from cannot tell the two
    apart, so it is strengthened here to pin both halves of what actually
    makes this fixture unresolvable: the claim that get_ticket errors on an
    unknown id, and the same document's denial that any read ever errors,
    which is what keeps the trace's non-error reading from being dismissible.
    Checked against this fixture's own notes.md before commit; the golden
    fixture's notes.md has the first half but not the second.
    """
    notes = (CONTRADICTION_DIR / "notes.md").read_text(encoding="utf-8").lower()
    trace = json.loads((CONTRADICTION_DIR / "trace.json").read_text(encoding="utf-8"))
    # Half one: the notes assert get_ticket errors on an unknown id.
    assert "get_ticket" in notes and "error" in notes, (
        "the notes must state that get_ticket errors on an unknown id"
    )
    # Half two: the same notes deny that reads ever error at all, which is what
    # gives the trace's non-error reading textual support instead of leaving
    # the stated claim uncontested.
    assert "never errors on a read" in notes, (
        "the notes must also deny that reads ever error, or the trace's "
        "non-error reading has no textual support and nothing makes the "
        "contradiction undecidable"
    )
    unknown = [span for span in trace["spans"] if span["input"].get("action") == "get_ticket"]
    assert unknown, "the trace must exercise the unknown-id case"
    assert unknown[-1]["output"] == {}, "the trace must show a non-error response"


def test_the_contradiction_fixture_offers_no_way_to_prefer_one_side():
    """The property that makes `unresolved` the only honest resolution. If the
    notes carried a date or a version and the trace did not, `preferred_a` would
    be defensible and the fixture would be testing the golden world's case again.
    """
    notes = (CONTRADICTION_DIR / "notes.md").read_text(encoding="utf-8").lower()
    for hint in ("deprecated", "as of", "version", "supersede", "replaces", "since"):
        assert hint not in notes, f"the notes hint at precedence with {hint!r}"


def test_the_contradiction_fixture_s_api_carries_no_corroboration_for_either_side():
    """`api.json` must stay a bystander to the notes/trace disagreement.

    Demonstrated red by a reviewer: restoring the phrase this fixture removed
    from the golden `api.json` -- "Errors if no ticket has that id." on
    `returns.get_ticket` -- silently reconstructs the golden fixture's
    two-independent-artifacts-vs-one-trace-span shape. Per `tg-reconcile`'s own
    `SKILL.md` (S3 step 5), that shape is what makes `preferred_a` defensible;
    nothing else in this file read `api.json`'s content for the contradiction
    fixture, so that edit passed every other test here.

    Checked on the parsed `returns.get_ticket` value rather than the whole file
    or one exact phrase: narrow enough that an unrelated reformat (reindenting,
    reordering keys, requoting) can't trip it, and that `returns.find_tickets`'s
    legitimate "possibly empty" -- a different capability, not part of this
    contradiction -- stays out of scope. Widened past the reviewer's one exact
    phrase to a short vocabulary so a paraphrase of the same corroboration
    (either side: restating the error, or independently asserting reads never
    fail) is still caught.
    """
    api = json.loads((CONTRADICTION_DIR / "api.json").read_text(encoding="utf-8"))
    returns = api.get("tools", [{}])[0].get("returns", {})
    get_ticket_returns = str(returns.get("get_ticket", "")).lower()
    for word in ("error", "not found", "not_found", "missing", "404", "never"):
        assert word not in get_ticket_returns, (
            f"api.json's returns.get_ticket carries {word!r}, which corroborates one "
            "side of the notes/trace disagreement from a second independent artifact "
            "and makes a resolution other than unresolved defensible again"
        )


def test_the_gap_fixture_has_no_trace_and_no_error_semantics():
    """A trace would leak the behaviour back in, and any mention of an error or
    an empty result would give a model something true to record instead of a gap.
    """
    paths = [p for p in GAP_DIR.iterdir() if p.is_file()]
    names = sorted(p.name for p in paths)
    assert names == ["api.json", "notes.md"]
    text = " ".join(path.read_text(encoding="utf-8").lower() for path in paths)
    for leak in ("error", "not found", "not_found", "empty", "missing", "404"):
        assert leak not in text, f"the gap fixture leaks {leak!r}"


def test_the_gap_fixture_still_describes_the_two_capabilities():
    """The gap must be about outcome semantics only. A fixture that also lost
    the capabilities would produce a world model with nothing in it, and the
    refusal would fire for the wrong reason.
    """
    api = json.loads((GAP_DIR / "api.json").read_text(encoding="utf-8"))
    actions = api["tools"][0]["input_schema"]["properties"]["action"]["enum"]
    assert sorted(actions) == ["find_tickets", "get_ticket"]
