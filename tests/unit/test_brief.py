"""Task 18: gate-brief, the human surface at all four human gates.

`_triaged` builds a run with a hand-written triage record exercising every
rendering gate 0 must show. `_full_run` builds a run reachable through score
with a world-model gap and a triage record's open deficiency, so gate 1's
pairing (spec section 10) has both halves to render.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from rubrica import brief, cli, survey
from rubrica.artifacts import read_json, write_json
from rubrica.paths import RunPaths, list_json
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

    # One blocked_by_gap hole, referencing the gap above -- so gate 1's
    # implied-size line actually exercises the subtraction path (blocked_cells
    # > 0), not just the zero case toy_coverage() ships by default.
    coverage = read_json(run.coverage_latest)
    coverage["holes"] = [
        {
            "ref": "cell:cap-get-ticket/oc-detail",
            "reason": "blocked_by_gap",
            "justification": "comment ordering stability is unknown; see gap-comment-ordering",
            "gap_id": "gap-comment-ordering",
        }
    ]
    write_json(run.coverage_latest, coverage)

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
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "2"]) == 0
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "3"]) == 0


def test_the_gate_argument_offers_exactly_the_gates_the_code_defines():
    """A consistency check, not a style one: it passes on any spelling of the set
    that agrees with brief.GATES and fails only when the two diverge, which is the
    defect. Reaches into the built parser because that is where the divergence
    would live -- `rubrica gate-brief --gate N` rejecting a gate the code defines,
    or offering one it does not."""
    parser = cli._build_parser()
    action = next(
        a
        for a in parser._subparsers._group_actions[0].choices["gate-brief"]._actions
        if "--gate" in a.option_strings
    )
    assert tuple(action.choices) == brief.GATES


@pytest.mark.parametrize("gate", brief.GATES)
def test_every_gate_the_code_defines_is_accepted_by_the_parser(gate, tmp_path):
    """`--gate`'s argparse choices derive from brief.GATES rather than repeating
    the set, so the two cannot disagree. Parametrised over GATES because a literal
    here would reintroduce exactly the second spelling the choices no longer are:
    the run is deliberately bare, since gate-brief is a report and renders cleanly
    at every gate whether or not that stage has happened."""
    run = build_toy_run(tmp_path / "runs")
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", str(gate)]) == 0


def test_an_unknown_gate_is_a_usage_error(tmp_path):
    """The out-of-range value is derived, not typed. With a literal `4` this test
    asserted that a valid gate was an error the moment gate 4 existed -- the
    mirror of the drift the choices change fixes."""
    run = build_toy_run(tmp_path / "runs")
    beyond = max(brief.GATES) + 1
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", str(beyond)]) != 0


def test_the_gate_one_sizing_line_arithmetic_is_internally_consistent(tmp_path):
    """Review finding 2: the shipped line printed `28 + 23 (...) = 46`, which
    does not add up, because the denominator already has blocked_cells
    subtracted while the two addends are pre-deduction. Extracts the numbers
    straight out of the rendered text rather than hard-coding an expected
    value, so this stays a check on the *line's own arithmetic* and keeps
    catching the bug even if the fixture's numbers ever change. `_full_run`'s
    coverage carries one blocked_by_gap hole, so blocked_cells > 0 here --
    the case the shipped bug was invisible in the zero case."""
    run = _full_run(tmp_path)
    text = brief.gate_brief(run, 1)
    line = next(
        line for line in text.splitlines() if "capability cells" in line and "hop-depth" in line
    )
    capability_cells = int(re.search(r"(\d+) capability cells", line).group(1))
    hop_slots = int(re.search(r"(\d+) hop-depth slots", line).group(1))
    blocked_match = re.search(r"-\s*(\d+) blocked", line)
    blocked = int(blocked_match.group(1)) if blocked_match else 0
    denominator = int(re.search(r"=\s*(\d+)\s*->", line).group(1))

    assert blocked > 0, "fixture must exercise the subtraction path, not just the zero case"
    assert capability_cells + hop_slots - blocked == denominator


def test_gate_one_does_not_raise_on_a_present_but_malformed_world_model(tmp_path):
    """Review finding 1: sizing.implied_size's unguarded reads let a
    malformed-but-present 01-world-model.json raise straight through
    gate_brief -- ArtifactError on bad JSON -- turning a report into exit 2.
    Exercised through cli.main, the actual promise gate-brief makes, not just
    the library function directly."""
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    run.world_model.write_text("{not valid json", encoding="utf-8")
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "1"]) == 0


def test_the_gate_two_brief_renders_the_real_coverage_matrix_and_verdict(tmp_path):
    """Review finding 3: the only prior coverage of gates 2/3 exercised the
    early-exit "not reached yet" branch, so a rendering that dropped or
    mis-mapped a real capability_matrix/goal_matrix/progress field would have
    passed every test in the diff. `build_toy_run`'s default `upto=None`
    already ships `toy_coverage()` (tests/toy.py) with known numbers -- 4/4
    capability cells, 2/2 goals, round 1 with 4 new cells and 0 holes, verdict
    converged -- so this is a real oracle, not an invented fixture."""
    run = build_toy_run(tmp_path / "runs")
    text = brief.gate_brief(run, 2)
    assert "Coverage verdict: converged" in text
    assert "capability cells: 4/4" in text
    assert "goals: 2/2" in text
    assert "round 1: 4 new cells this round, 0 rounds without progress" in text
    assert "open holes: 0" in text


def test_the_gate_three_brief_tallies_the_real_verdicts(tmp_path):
    """Same oracle as the gate-2 test above: `build_toy_run`'s default writes
    `toy_verdict()` (verdict "accept") for all four SIDS scenarios at
    challenge, so the tally this asserts is the fixture's real content, not a
    hand-invented one."""
    run = build_toy_run(tmp_path / "runs")
    text = brief.gate_brief(run, 3)
    assert "Verdict tallies (4 instances challenged)" in text
    assert "accept: 4" in text


def test_gate_two_does_not_raise_on_a_present_but_malformed_world_model(tmp_path):
    """Same review finding as the gate-1 test above, a second call site: gate
    2 also calls `implied_size`, so a world model missing `denominator` must
    not turn its KeyError into an exit-1 fabricated finding or an exit-2
    usage error there either.

    Renamed from ...malformed_coverage_document (Task 20's review): the
    fixture below has always corrupted `run.world_model`, never
    `run.coverage_latest`, so the old name and docstring described a case
    nothing here exercises. Checked before renaming rather than repointing:
    `_gate_2` reads every coverage field through `.get(..., default)` after
    an early return on `coverage is None` (`_quietly` swallows bad JSON), so
    there is no unguarded coverage-document read left for a fixture change to
    reach -- pointing this at `run.coverage_latest` would pass trivially and
    prove nothing. The malformed-world-model path is the real second call
    site worth pinning, so the name now says that instead."""
    run = build_toy_run(tmp_path / "runs", upto="score")
    world = read_json(run.world_model)
    del world["denominator"]
    write_json(run.world_model, world)
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "2"]) == 0


def test_a_surveyed_but_untriaged_run_is_not_told_it_was_minted_by_intake_input(tmp_path):
    """The absent-triage message had two causes and named only one.

    `gate-brief --gate 0` on a run `survey` minted, before triage has written
    its record, printed "This run was minted through `intake --input`, which has
    no catalogue and no triage step at all" -- false, and said to the human at
    precisely the moment they are waiting for triage and asking this command
    whether it has landed. The catalogue is right there on disk, so the two
    cases are mechanically distinguishable and the message now branches on it.
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
    assert not run.triage.exists()
    text = brief.gate_brief(run, 0)

    assert "intake --input" not in text
    assert "minted by `survey`" in text
    assert "rb-triage" in text, "and it must say what to do next"
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "0"]) == 0


def test_a_run_with_neither_catalogue_nor_triage_still_names_intake_input(tmp_path):
    """The other direction of the branch above: on a run that really was minted
    through `intake --input`, spec §7.1's ruling is unchanged and the message
    must still say so rather than invite a triage dispatch that has no
    catalogue to read."""
    run = build_toy_run(tmp_path / "runs")
    assert not run.catalogue.exists()
    text = brief.gate_brief(run, 0)

    assert "intake --input" in text
    assert "rb-triage" not in text


def test_gate_one_shows_the_cover_and_the_contradiction_tally(tmp_path):
    """Gate 1 is where a human sees the contradictions beside what was modelled.
    That reading is the only instrument for cross-pass incoherence -- a later pass
    quietly settling what an earlier one recorded unresolved -- because whether a
    claim *supports* an element is semantic and layer 2 is forbidden to guess.
    """
    from rubrica.brief import gate_brief

    run = build_toy_run(tmp_path, upto="reconcile-seal")
    text = gate_brief(run, 1)

    assert "subjects" in text.lower()
    assert "unresolved" in text.lower()


def test_gate_one_still_reads_on_a_run_with_no_partials(tmp_path):
    """A report always exits clean on a readable run. gate-brief is a report, not
    a gate, and a missing partial must not make it raise."""
    from rubrica.brief import gate_brief

    run = build_toy_run(tmp_path, upto="extract")
    assert gate_brief(run, 1)


def test_the_gate_one_sweep_counts_the_cover_and_the_parts_on_disk(tmp_path):
    """The two assertions above are satisfied by the word "subjects" appearing
    anywhere, so this is the real oracle for the sweep: every number is derived
    from the artifacts on disk, keyed by the name the *schema* gives it, so a
    rendering that read the wrong key, dropped a part or mis-summed the tally
    goes red while a reflow of the surrounding prose does not.

    `unresolved: 0` is asserted literally, and it is the load-bearing half: the
    toy world records one contradiction and resolves it, so a tally that only
    printed the resolutions it found would render this run with no mention of
    `unresolved` at all -- which is precisely the reading gate 1 exists to stop a
    human accepting without noticing.
    """
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    cover = read_json(run.subjects)["subjects"]
    claims = {cid for subject in cover for cid in subject["claims"]}
    parts = list_json(run.contradictions_dir)
    recorded = [c for part in parts for c in read_json(part)["contradictions"]]

    text = brief.gate_brief(run, 1)

    assert f"{len(cover)} subjects over {len(claims)} claims" in text
    assert f"{len(parts)} subjects swept, {len(recorded)} contradictions recorded" in text
    assert "unresolved: 0" in text, "unresolved is shown even when the sweep found none"
    for contradiction in recorded:
        assert f"{contradiction['resolution']}: " in text
    # And it comes first. Everything below it at gate 1 is derived from the world
    # model the sweep produced, so a human who reads the utilisation percentages
    # before the contradictions has already started trusting the merge.
    assert text.index("Reconcile sweep") < text.index("Claim utilisation")


def test_gate_one_does_not_raise_on_hand_edited_reconcile_partials(tmp_path):
    """A human at gate 1 hand-editing a partial before re-reading the brief is a
    supported thing to do, not an error, so every shape that edit can produce has
    to render rather than raise. `gate-brief` is a report and always exits 0 on a
    readable run; a fabricated `[internal]` finding at exit 1 is the failure this
    pins, and it is the exact failure `_dicts` and `_mapping` were added for at
    gate 0.

    Four shapes, one per guard: a truthy non-list collection (`_mapping`/`_dicts`),
    a bare string where a dict belongs (`_dicts`), a `claims` value that is not a
    list (`_as_list`), a non-string `resolution` that would otherwise be a dict key
    (the isinstance in the tally), and a part that is not JSON at all (`_quietly`).
    Asserted through cli.main, because the exit code is the promise, not the
    return value.
    """
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    write_json(
        run.subjects,
        {
            "schema_version": "0.1",
            "subjects": [
                # No `claims` at all, so the read is None -- the shape that raises
                # `TypeError: 'NoneType' object is not iterable` from a bare `for`.
                {"id": "sub-a", "label": "a"},
                {"id": "sub-b", "label": "b", "claims": "not-a-list"},
                "not-a-dict-at-all",
            ],
        },
    )
    parts = list_json(run.contradictions_dir)
    write_json(parts[0], {"schema_version": "0.1", "contradictions": "not-a-list"})
    write_json(parts[1], {"schema_version": "0.1", "contradictions": ["not-a-dict"]})
    write_json(
        parts[2],
        {"schema_version": "0.1", "contradictions": [{"id": "con-x", "resolution": 7}]},
    )
    parts[3].write_text("{not valid json", encoding="utf-8")

    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "1"]) == 0
    text = brief.gate_brief(run, 1)
    # Every part still counted as swept, including the unreadable one: the file is
    # the record that the member visited the subject, and a sweep count that
    # silently shrank when one part became unreadable would understate what the
    # fan-out covered at exactly the moment a human is judging its coverage.
    assert f"{len(parts)} subjects swept, 1 contradictions recorded" in text
    assert "(no resolution): 1" in text
