"""Task 18: gate-brief, the human surface at all four human gates.

`_triaged` builds a run with a hand-written triage record exercising every
rendering gate 0 must show. `_full_run` builds a run reachable through score
with a world-model gap and a triage record's open deficiency, so gate 1's
pairing (spec section 10) has both halves to render.
"""

from __future__ import annotations

from pathlib import Path

from rubrica import brief, cli, survey
from rubrica.artifacts import read_json, write_json
from rubrica.paths import RunPaths
from tests.toy import build_toy_catalogue_and_triage, build_toy_run

CORPUS = Path(__file__).parent.parent / "fixtures" / "corpus-toy"


def _triaged(tmp_path) -> RunPaths:
    """A surveyed run with a hand-written triage record: three admits by
    priority, declines across six reason codes (including one
    `needs_projection` referenced by a projection and one `digest_insufficient`
    backed only by a non-empty `deficiencies[]`, per refs.check_triage's
    strong/weak split), and one open deficiency with the projection that would
    close it.
    """
    run = survey.survey(
        corpus_roots=[CORPUS],
        runs_dir=tmp_path / "runs",
        target_name="ticketq",
        target_interface="mcp",
        objective="breadth",
        max_rounds=2,
        max_scenarios=128,
    )
    write_json(
        run.triage,
        {
            "schema_version": "0.1",
            "run_id": run.root.name,
            "objective_review": {
                "declared_objective": "breadth",
                "supported": True,
                "surfaces": [
                    {
                        "name": "ticketq",
                        "evidence": ["readme-md", "capture-json-0", "capture-json-1"],
                        "weight": {"candidates": 3, "bytes": 1},
                    }
                ],
            },
            "dispositions": [
                {
                    "candidate_id": "readme-md",
                    "disposition": "admit",
                    "priority": 1,
                    "reason": "names the target and its two queues",
                    "authority": "triage",
                },
                {
                    "candidate_id": "capture-json-0",
                    "disposition": "admit",
                    "priority": 2,
                    "reason": "one captured trajectory shape",
                    "authority": "triage",
                },
                {
                    "candidate_id": "capture-json-1",
                    "disposition": "admit",
                    "priority": 3,
                    "reason": "a second, distinct trajectory shape",
                    "authority": "triage",
                },
                {
                    "candidate_id": "gitignore",
                    "disposition": "decline",
                    "reason_code": "off_objective",
                    "reason": "vcs housekeeping, not evidence about the target",
                    "authority": "triage",
                },
                {
                    "candidate_id": "api-json",
                    "disposition": "decline",
                    "reason_code": "off_objective",
                    "reason": "describes a different surface than this run's objective",
                    "authority": "triage",
                },
                {
                    "candidate_id": "capture-json",
                    "disposition": "decline",
                    "reason_code": "out_of_scope",
                    "reason": "the container; its elements are the real candidates",
                    "authority": "triage",
                },
                {
                    "candidate_id": "capture-json-2",
                    "disposition": "decline",
                    "reason_code": "near_duplicate",
                    "reason": "same shape as capture-json-0",
                    "authority": "triage",
                },
                {
                    "candidate_id": "capture-json-3",
                    "disposition": "decline",
                    "reason_code": "superseded",
                    "reason": "same shape as capture-json-1, less complete",
                    "authority": "triage",
                },
                {
                    "candidate_id": "notes-md",
                    "disposition": "decline",
                    "reason_code": "no_evidence_value",
                    "reason": "carries no statement about the target",
                    "authority": "triage",
                },
                {
                    "candidate_id": "locked-md",
                    "disposition": "decline",
                    "reason_code": "digest_insufficient",
                    "reason": "the digest could not establish what this file describes",
                    "authority": "triage",
                },
                {
                    "candidate_id": "tool-defs-py",
                    "disposition": "decline",
                    "reason_code": "needs_projection",
                    "reason": "valuable but unusable as raw source; see prj-tools",
                    "authority": "triage",
                },
            ],
            "deficiencies": [
                {
                    "deficiency_id": "def-shapes",
                    "subject": "tool result shapes",
                    "statement": "no admitted candidate declares the result shape of the "
                    "tools the captured trajectories call",
                }
            ],
            "projections": [
                {
                    "projection_id": "prj-tools",
                    "closes": ["def-shapes"],
                    "sources": [
                        {
                            "candidate_id": "tool-defs-py",
                            "digest_note": "top-level tool schema literals",
                        }
                    ],
                    "wanted": {
                        "kind": "mcp_tool_schema",
                        "statement": "one JSON document holding each tool's result shape",
                        "why": "every capability binds to a tool, and a scenario cannot be "
                        "seeded without the result shape",
                    },
                    "method": {
                        "confidence": "high",
                        "steps": ["import the module rather than parsing it"],
                    },
                    "acceptance": {
                        "classifies_as": "mcp_tool_schema",
                        "prose": "one document with a /tools pointer",
                    },
                    "boundary": "does not invent a result shape no tool call in the "
                    "admitted traces exercises",
                }
            ],
        },
    )
    return run


def _full_run(tmp_path) -> RunPaths:
    """A run reachable through score, patched with one world-model gap and
    one open triage deficiency -- gate 1's actual state, so the pairing spec
    section 10 rules a human's call has both halves to look at.
    """
    run = build_toy_run(tmp_path / "runs", upto="score")

    world = read_json(run.world_model)
    world["gaps"] = [
        {
            "id": "gap-comment-ordering",
            "subject": "comment ordering",
            "unknown": "whether `position` is stable across edits",
            "why_it_matters": "get_ticket's outcome_class claims comments are ordered by "
            "position, and nothing admitted says whether that ordering can change",
            "blocks": ["score"],
        }
    ]
    write_json(run.world_model, world)

    build_toy_catalogue_and_triage(run)
    triage = read_json(run.triage)
    triage["deficiencies"] = [
        {
            "deficiency_id": "def-comment-stability",
            "subject": "comment ordering stability",
            "statement": "no admitted input says whether position values can change after "
            "a comment is added",
        }
    ]
    write_json(run.triage, triage)

    return run


def test_the_gate_zero_brief_leads_with_the_objective_verdict(tmp_path):
    """A reader who stops after ten lines must have seen the thing most likely to
    make them overturn the selection."""
    text = brief.gate_brief(_triaged(tmp_path), 0)
    head = "\n".join(text.splitlines()[:10]).lower()
    assert "objective" in head
    assert "supported" in head


def test_the_gate_zero_brief_lists_declines_grouped_by_reason_code(tmp_path):
    text = brief.gate_brief(_triaged(tmp_path), 0)
    assert "off_objective" in text
    assert "needs_projection" in text


def test_the_gate_zero_brief_shows_every_open_deficiency_and_its_projection(tmp_path):
    """The block that would have predicted six parsec refusals is useless if the
    brief buries it."""
    text = brief.gate_brief(_triaged(tmp_path), 0)
    assert "def-shapes" in text and "prj-tools" in text


def test_the_gate_zero_brief_would_not_pass_with_an_empty_declines_block(tmp_path):
    """Guards against a rendering that satisfies the substring checks above by
    accident while silently omitting the whole declines section -- the header
    must actually enumerate every decline, not just mention the word."""
    text = brief.gate_brief(_triaged(tmp_path), 0)
    declines_section = text.split("Declines, by reason code")[1]
    for reason_code in (
        "off_objective",
        "out_of_scope",
        "near_duplicate",
        "superseded",
        "no_evidence_value",
        "digest_insufficient",
        "needs_projection",
    ):
        assert reason_code in declines_section
    # And every declined candidate_id is named somewhere under that header.
    for candidate_id in (
        "gitignore",
        "api-json",
        "capture-json",
        "capture-json-2",
        "capture-json-3",
        "notes-md",
        "locked-md",
        "tool-defs-py",
    ):
        assert candidate_id in declines_section


def test_the_gate_one_brief_puts_gaps_and_declined_deficiencies_side_by_side(tmp_path):
    """Spec §10: this pairing is semantic, so it is a human's call and this
    rendering is the whole instrument for making it."""
    text = brief.gate_brief(_full_run(tmp_path), 1)
    assert "gap-" in text
    assert "deficien" in text.lower()
    assert "utilisation" in text.lower()
    assert "implied" in text.lower()


def test_the_gate_one_brief_names_the_gap_and_the_deficiency_by_id(tmp_path):
    """A rendering that only says "1 gap" and "1 deficiency" would pass looser
    checks; gate 1's whole point is pairing specific prose, so both ids must
    appear, not just their counts."""
    text = brief.gate_brief(_full_run(tmp_path), 1)
    assert "gap-comment-ordering" in text
    assert "def-comment-stability" in text


def test_a_brief_for_a_run_with_no_triage_record_says_so_and_exits_clean(tmp_path):
    """Spec §7.1 held consistently by the report as well as by the check."""
    text = brief.gate_brief(build_toy_run(tmp_path), 0)
    assert "no triage" in text.lower()


def test_gate_brief_is_a_report_and_never_a_gate(tmp_path):
    """Same ruling as claim-utilisation: it always exits clean on a readable run."""
    assert cli.main(["gate-brief", "--run", str(_triaged(tmp_path).root), "--gate", "0"]) == 0


def test_gate_brief_covers_gates_two_and_three_without_raising(tmp_path):
    """Gates 2 and 3 render what already exists (the coverage verdict, the
    verdict tallies) -- exercised here on a run that has reached neither stage,
    which must still render cleanly rather than raise."""
    run = build_toy_run(tmp_path / "runs", upto="reconcile")
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "2"]) == 0
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "3"]) == 0


def test_an_unknown_gate_is_a_usage_error(tmp_path):
    run = build_toy_run(tmp_path / "runs")
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "4"]) != 0
