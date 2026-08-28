"""Task 18: gate-brief, the human surface at all four human gates.

`_triaged` builds a run with a hand-written triage record exercising every
rendering gate 0 must show. `_full_run` builds a run reachable through score
with a world-model gap and a triage record's open deficiency, so gate 1's
pairing (spec section 10) has both halves to render.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from rubrica import brief, cli, refs, survey
from rubrica.artifacts import read_json, write_json
from rubrica.paths import RunPaths, list_json
from rubrica.utilisation import claim_utilisation
from rubrica.validate import validate_artifact
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
    run = build_toy_run(tmp_path / "runs", upto="score-seal")

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
    run = build_toy_run(tmp_path / "runs", upto="score-seal")
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
    # `triage-seal`, not any `rb-triage*` name: the record this command is waiting
    # for is the sealed one, and a bare "rb-triage" substring would now be
    # satisfied by any member of the family being named for any reason.
    assert "triage-seal" in text, "and it must say what to do next"
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
    assert "triage-seal" not in text


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

    One shape per guard, and no count of them here -- the enumeration is the
    list, and a number beside a list that grows is the first thing to go stale: a
    truthy non-list collection (`_mapping`/`_dicts`), a bare string where a dict
    belongs (`_dicts`), a `claims` value that is not a list (`_as_list`), a
    `claims` list holding unhashable members (the isinstance in the `covered` set
    comprehension), a non-string `resolution` that would otherwise be a dict key
    (the isinstance in the tally), and a part that is not JSON at all
    (`_quietly`). Asserted through cli.main, because the exit code is the
    promise, not the return value.
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
                # A real list holding unhashable elements. `_as_list` guards the
                # container and nothing guarded the members, so these two reached
                # a *set* comprehension: measured `TypeError: unhashable type:
                # 'dict'` and `... 'list'` at exit 1 with a fabricated
                # `[internal]` finding, on a readable run.
                {"id": "sub-c", "label": "c", "claims": [{"id": "clm-notes-001"}, ["clm-x"]]},
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


def test_gate_one_reports_read_coverage_per_pass(tmp_path):
    """Per pass, not per input -- the aggregate above it is what hid issue #6.

    Measured on run-20260823-112746: `claim-utilisation` read 33.6% overall while
    per-kind citation ran 110 of 135 for the pass that had read every claims file
    and 2 of 38 for the pass that had read three of twenty-three. A per-artifact
    number cannot say which pass did the citing, so the brief printed the average
    of a diligent pass and a skimming one.

    Every figure asserted here is summed back out of the partials on disk, keyed
    by the name the schema gives it, so a rendering that read the wrong key, lost
    a pass or mis-summed a column goes red while a reflow of the prose does not.
    `refs.PASS_OWN_KINDS` is iterated rather than re-typed for the same reason
    `brief` imports it: a second copy of which pass owns which kind is a copy of
    a judgment, and this test would then be able to agree with a stale one.
    """
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")

    text = brief.gate_brief(run, 1)
    section = _section(text, "Read coverage, per pass")

    for attribute, own_kinds in refs.PASS_OWN_KINDS:
        path = getattr(run, attribute)
        rows = read_json(path)["inputs_seen"]
        cited = sum(row["cited"] for row in rows)
        total = sum(row["own_kind_total"] for row in rows)
        assert f"{path.name}: {cited}/{total} claims of {', '.join(own_kinds)} cited" in section

    # The toy's one drop, and the note that says it was a decision: that is the
    # line a human is at gate 1 to rule on. Read off disk rather than named here,
    # so the fixture is the oracle for which row it is.
    dropped = [row for row in read_json(run.outcomes_part)["inputs_seen"] if row["dropped"]]
    assert len(dropped) == 1, f"the toy is expected to carry exactly one drop, got {dropped}"
    row = _row(section, dropped[0]["artifact_id"])
    assert f"{dropped[0]['cited']}/{dropped[0]['own_kind_total']} cited" in row
    assert f"{dropped[0]['dropped']} dropped" in row
    assert dropped[0]["note"] in row, "a drop is only readable beside the note it required"
    # And it is the *only* row printed under any pass. The toy carries a 0/0/0 row
    # for every artifact holding none of a pass's kinds -- honest in the artifact,
    # and it would bury this line in the brief.
    assert [line for line in section.splitlines() if line.startswith("    ")] == [row]


def test_gate_one_read_coverage_names_a_pass_that_wrote_no_accounting(tmp_path):
    """A pass missing from this block is the anomaly a reader is here to notice, so
    it has to be printed rather than skipped.

    The loop used to `continue` on a partial with no readable `inputs_seen`, and
    the "nothing to report" line only fires when *every* pass is absent -- so
    three passes rendering and one omitted rendered as a complete brief with no
    signal at all. Both branches are exercised, because they are the two states a
    reader acts on differently: a partial that was never written is a run that
    stopped, and one that is there carrying nothing readable is a defect
    `rubrica validate --stage X` will name.
    """
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    surviving = read_json(run.capabilities_part)["inputs_seen"]

    # Deleted: the partial is not there at all.
    run.goals_part.unlink()
    # Present and readable, but with nothing this block can sum.
    run.entities_part.write_text("{}", encoding="utf-8")

    section = _section(brief.gate_brief(run, 1), "Read coverage, per pass")

    assert f"{run.goals_part.name}: no accounting (not written yet)" in section
    assert f"{run.entities_part.name}: no accounting (present," in section
    # The control: the two passes that *did* write an accounting still render
    # their rate, so this is naming the omissions rather than replacing the block.
    cited = sum(row["cited"] for row in surviving)
    total = sum(row["own_kind_total"] for row in surviving)
    assert f"{run.capabilities_part.name}: {cited}/{total} claims of capability cited" in section
    assert "nothing to report" not in section, (
        "the all-four-absent line must not fire while two passes rendered"
    )


def test_gate_one_read_coverage_is_quiet_before_the_partials_exist(tmp_path):
    """gate-brief is a report, not a gate: it exits 0 on a readable run, so a run
    stopped before any reconcile pass has written its partial must render a line
    saying there is nothing to report rather than raise or print a blank block."""
    run = build_toy_run(tmp_path / "runs", upto="extract")

    section = _section(brief.gate_brief(run, 1), "Read coverage, per pass")

    assert "nothing to report" in section


def test_gate_one_read_coverage_does_not_raise_on_a_hand_edited_accounting(tmp_path):
    """A human at gate 1 hand-editing a partial before re-reading the brief is
    supported, so every shape that edit produces has to render rather than raise
    -- the same ruling `test_gate_one_does_not_raise_on_hand_edited_reconcile_partials`
    pins for the sweep, and the same fabricated `[internal]` finding at exit 1 is
    the failure. One shape per guard: a whole `inputs_seen` that is not a list
    (`_dicts`), a row that is not a dict (`_dicts`), a count that is a string and
    one that is null (`_count`, because `sum` raises rather than skipping), a
    partial that is a directory where a file belongs (`_quietly`), and a row with
    no `dropped` key at all.

    Asserted through cli.main, because the exit code is the promise.
    """
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    part = read_json(run.capabilities_part)
    part["inputs_seen"] = [
        {"artifact_id": "api-json", "own_kind_total": "5", "cited": None, "dropped": 5},
        {"artifact_id": "notes-md", "own_kind_total": 1, "cited": 1},
        "not-a-dict-at-all",
    ]
    write_json(run.capabilities_part, part)
    part = read_json(run.entities_part)
    part["inputs_seen"] = "not-a-list"
    write_json(run.entities_part, part)
    run.outcomes_part.unlink()
    run.outcomes_part.mkdir()

    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "1"]) == 0
    section = _section(brief.gate_brief(run, 1), "Read coverage, per pass")
    # The one pass whose accounting is intact still renders its own line: a guard
    # that dropped the whole block on one bad row would take the readable passes
    # down with the edited one.
    goals = read_json(run.goals_part)["inputs_seen"]
    assert f"{run.goals_part.name}: {sum(row['cited'] for row in goals)}/" in section
    # Both halves of the raw-vs-summed decision, which is otherwise only argued in a
    # comment. The api-json row states `"own_kind_total": "5"` and `"cited": null`
    # and prints them **verbatim**, because a reader who came here because a total
    # looked wrong needs what the file says; the pass total above it counts only the
    # row it can add, so it reads 1/1 from notes-md alone.
    assert "api-json: None/5 cited, 5 dropped" in _row(section, "api-json")
    assert "(no note)" in _row(section, "api-json"), "a drop with no note says so"
    assert f"{run.capabilities_part.name}: 1/1 claims of capability cited" in section


@pytest.mark.parametrize(
    "member",
    [
        # Readable JSON every one of them, and all four are what a hand-edit at
        # gate 1 produces from a list of claim ids.
        {"a": 1},
        ["clm-api-001"],
        None,
        7,
    ],
)
def test_gate_one_and_utilisation_survive_a_non_string_claim_member(tmp_path, member):
    """Measured before the fix, on a readable run whose world model carried
    `"claims": [{"a": 1}]` on a gap: `utilisation._cited_claim_ids` raised
    `TypeError: unhashable type: 'dict'` out of `set.update`, and cli.py turned
    that into exit 1 with one fabricated `[internal]` finding -- for
    `claim-utilisation` and for `gate-brief --gate 1`, which reads it. Both are
    reports, and CLAUDE.md's ruling for a report is that it always exits 0 on a
    readable run, so this is a contract violation rather than a strictness
    question.

    The mangle walks the document the way `refs._claim_refs_in` walks it rather
    than naming the citation sites: issue #6 added three of them, and a site list
    here would leave the next one unguarded and this test still green.
    """
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    world = read_json(run.world_model)
    # A gap, because the golden world has none and `gaps[].claims` is the newest
    # of the seven sites.
    world["gaps"] = [
        {
            "id": "gap-hand-edited",
            "subject": "billing",
            "unknown": "whether a refund can exceed the original charge",
            "why_it_matters": "the boundary case a suite would exercise",
            "blocks": ["propose"],
            "claims": ["clm-notes-001"],
        }
    ]
    _mangle_every_claims_array(world, member)
    for contradiction in world["contradictions"]:
        # Both sides: check_world_model resolves each as a claim reference and
        # `_cited_claim_ids` counts each, so leaving one intact would leave the
        # input it names cited and the last assertion below unearned.
        contradiction["claim_a"] = member
        contradiction["claim_b"] = member
    write_json(run.world_model, world)

    assert claim_utilisation(run)["artifacts"], "the report still reports every input"
    assert cli.main(["claim-utilisation", "--run", str(run.root)]) == 0
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "1"]) == 0
    # Nothing resolves any more, and the report says so rather than guessing: a
    # non-string member is not a claim id, and counting it as one would be the
    # same fabrication the exit code would have been.
    assert all(entry["cited"] == 0 for entry in claim_utilisation(run)["artifacts"])


def _mangle_every_claims_array(node, member) -> None:
    """Replace every `claims` array anywhere in `node` with `[member]`."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "claims":
                node[key] = [member]
            else:
                _mangle_every_claims_array(value, member)
    elif isinstance(node, list):
        for item in node:
            _mangle_every_claims_array(item, member)


def _replace_container(world: dict, site: str, shape) -> None:
    """Put `shape` where `site` names one of the containers `_cited_claim_ids` walks.

    A site rather than a walk, unlike `_mangle_every_claims_array` above: the
    member axis is one shape repeated at every `claims` array, while a container
    is a *different* key at each level, and naming them is what makes a missed
    level a red test rather than a silent pass.
    """
    if "[]." in site:
        parent, child = site.split("[].")
        for element in world[parent]:
            element[child] = shape
    else:
        world[site] = shape


@pytest.mark.parametrize(
    "shape",
    [
        # Not a list at all -- a bare string is the one that does not fail loudly,
        # since iterating it yields characters that then reach `.get`.
        "nope",
        7,
        {"id": "clm-api-001"},
        # A list whose elements are not the objects the walk expects.
        ["nope"],
        [None],
    ],
)
@pytest.mark.parametrize(
    "site",
    [
        "capabilities",
        "entities",
        "actors",
        "goals",
        "gaps",
        "contradictions",
        "capabilities[].outcome_classes",
        "entities[].invariants",
    ],
)
def test_gate_one_and_utilisation_survive_a_malformed_citation_container(tmp_path, site, shape):
    """The container axis of the same defect the member axis above pins.

    Measured before the fix, on readable runs: every one of these exits **1** from
    both `claim-utilisation` and `gate-brief --gate 1` with
    `AttributeError: 'str' object has no attribute 'get'` out of
    `utilisation._cited_claim_ids`, and one fabricated `[internal]` finding on
    stdout. `capabilities = "nope"` is the pre-existing walk; `gaps = "nope"`,
    `outcome_classes = "nope"` and `invariants = "nope"` are walks issue #6 added,
    so half of these are crashes through a path this branch created.

    Both commands are reports, and CLAUDE.md's ruling for a report is that it
    always exits clean on a readable run -- there is no findings channel through
    which a report could say "this document is malformed", which is exactly why
    guarding here is not the same question as `check_input_dispositions`, where a
    raise degrades to an `internal` finding at exit 1.
    """
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    world = read_json(run.world_model)
    # A gap first, because the golden world has none and `gaps` is one of the
    # containers under test.
    world["gaps"] = [
        {
            "id": "gap-hand-edited",
            "subject": "billing",
            "unknown": "whether a refund can exceed the original charge",
            "why_it_matters": "the boundary case a suite would exercise",
            "blocks": ["propose"],
            "claims": ["clm-notes-001"],
        }
    ]
    _replace_container(world, site, shape)
    write_json(run.world_model, world)

    assert cli.main(["claim-utilisation", "--run", str(run.root)]) == 0
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "1"]) == 0
    report = claim_utilisation(run)["artifacts"]
    assert report, "the report still lists every input"
    # And the citations the *other* containers hold still count. Each case breaks
    # exactly one container, so this is the assertion that separates "skipped the
    # container it could not walk" from "skipped the world model entirely" -- a
    # guard returning `[]` for everything satisfies every line above it, since they
    # all read 01-claims/, and would render every input as zero-cited. That is a
    # different false statement from the crash it replaced, not a fix.
    assert any(entry["cited"] for entry in report), f"only the bad container is skipped: {report}"


def test_an_unreadable_claims_directory_is_exit_2_from_both_reports(tmp_path):
    """The shape that must **not** be guarded into an exit 0, pinned as a test
    rather than only argued in a docstring.

    The other readable-run shapes in this file assert exit **0** -- issue #6 closed
    them by widening the world-model containers `utilisation._cited_claim_ids`
    walks. The report contract violation still open is a hand-edited `01-claims/`
    document, which takes both reports to exit 1 on a readable run; its shapes are
    parked in `docs/design/limitations.md` and exercised as `summary.Malformed`
    markers by
    `tests/unit/test_summary.py::test_utilisation_is_a_marker_rather_than_raising_on_a_readable_run`,
    not here. An unreadable `01-claims/` is a different kind: `paths.list_json`
    raises `UsageError`, `cli.py` maps it to **exit 2** alongside OSError, and the
    exit-code contract's ruling for a filesystem problem *is* 2 -- the harness
    pointed at something broken, not a stage defect.

    Guarding it inside `utilisation.py` the way the world-model walk was guarded
    would turn this into an exit 0 reporting empty utilisation over claims nobody
    could read, which is the one reading a human at gate 1 must never be handed. So
    this test exists to go red if someone reads
    `test_utilisation_is_a_marker_rather_than_raising_on_a_readable_run` as an
    invitation to close its fourth param. Sibling of
    `test_gate_zero_reports_an_unreadable_dispositions_directory_as_a_broken_run`,
    whose docstring already claimed this behaviour for `01-claims/` without pinning
    it.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    run.claims_dir.chmod(0o000)
    try:
        assert cli.main(["claim-utilisation", "--run", str(run.root)]) == 2
        assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "1"]) == 2
    finally:
        run.claims_dir.chmod(0o755)


# --------------------------------------------------------------------------
# Task 15: gate 0's three new sections -- the slice table, the
# predicted-vs-observed surface divergence (spec section 4.1), and the summary
# of every group split across more than one slice (spec section 5.2).
# --------------------------------------------------------------------------

# The module's own constants, not a second spelling of them: these three
# headers are what every assertion below scopes to, and a test that re-typed
# them would keep passing against a stale spelling by unscoping itself to the
# whole document -- which is the vacuity the scoping exists to prevent.
SLICES_HEADER = brief.SLICES_HEADER
DIVERGENCE_HEADER = brief.DIVERGENCE_HEADER
SPLIT_HEADER = brief.SPLIT_HEADER


def _staged_and_sealed_run(tmp_path) -> RunPaths:
    """A run carried through the whole triage family to its sealed record, with
    the golden world partitioned into more than one slice.

    `slice_cap=4096` is not decoration. At `slices.DEFAULT_SLICE_BYTES` the
    three-row toy catalogue is a single slice (4102 row-bytes against 65536),
    which is the right default for a real corpus but leaves both the slice
    table and the split-group summary exercising the degenerate case -- one
    row, no group spanning anything. 4096 is the smallest round cap above the
    largest single row (api-json, 2381) and partitions the three candidates
    across s01/s02 with `provenance.other_slices` populated in both
    directions, which is the state
    `test_gate_zero_names_a_group_split_across_slices` asserts it reaches
    before it asserts anything about the rendering.
    """
    return build_toy_run(tmp_path / "runs", upto="triage-seal", slice_cap=4096)


def _section(text: str, header: str) -> str:
    """The body of one named block of the brief, header line included.

    Scoped rather than `in text` for the reason CLAUDE.md gives: a bare
    substring over the whole document is satisfiable by any other section, and
    for these three sections it is satisfiable by the *header line* -- the
    brief opens with `GATE 0 -- <run root>`, and pytest numbers its own tmp
    directories, so `"99" in text` would start passing on the hundredth
    `pytest-NN` of a session no matter what the brief rendered.
    """
    # A blank header would make the `in text` below trivially true and the
    # slice that follows meaningless, so the anchor is checked before it is used.
    assert header.strip(), "a section anchor must be a real header"
    assert header in text, f"the brief has no {header!r} section"
    lines = text.split(header, 1)[1].splitlines()
    body = lines[:1]
    for line in lines[1:]:
        # A non-indented, non-empty line is the next section's header. Every
        # line a section owns is either indented or blank.
        if line and not line.startswith(" "):
            break
        body.append(line)
    return "\n".join(body)


def _row(section: str, prefix: str) -> str:
    """The one line of `section` that starts with `prefix`.

    Per-row rather than per-section, because a section-wide substring check for
    a small integer is satisfiable by the section's own furniture: measured, a
    rendering that dropped the candidate count entirely still passed
    `str(len(candidate_ids)) in table`, since the counts here are 1 and 2 and
    the slice ids are `s01` and `s02`.
    """
    rows = [line for line in section.splitlines() if line.strip().startswith(prefix)]
    assert len(rows) == 1, f"expected exactly one row starting {prefix!r}, got {rows}"
    return rows[0]


def _has_number(row: str, value) -> bool:
    """Whether `row` states `value` as a number, not as digits inside a word.

    The `2` in `s02` and the `1` in `418` are not statements of a count, and an
    assertion that accepts them is measuring the presence of an id or a byte
    figure rather than the thing it names.
    """
    return re.search(rf"(?<!\w){re.escape(str(value))}(?!\w)", row) is not None


def test_gate_zero_reports_the_slice_table(tmp_path):
    """Spec section 11: how many slices, and how many candidates and bytes each.

    Every id, count and byte figure is read back out of 00-slices.json rather
    than written here, so the assertion cannot drift from the slicer.
    """
    run = _staged_and_sealed_run(tmp_path)
    entries = read_json(run.slices)["slices"]
    assert len(entries) > 1, "fixture is a single slice; the slice table is degenerate"

    table = _section(brief.gate_brief(run, 0), SLICES_HEADER)
    for entry in entries:
        assert entry["id"] in table
        # The two figures the spec bullet names, not just the id, and each read
        # off that slice's own row: a rendering that listed ids alone would
        # satisfy an id-only check while omitting the whole reason a human reads
        # this table.
        row = _row(table, f"{entry['id']}:")
        assert _has_number(row, len(entry["candidate_ids"])), row
        assert _has_number(row, entry["bytes"]), row


def test_gate_zero_reports_the_surface_divergence(tmp_path):
    """`predicted_surface_count` reaches the human who can act on it.

    Mutated to a value the fixture cannot produce by accident, and asserted
    inside the divergence section rather than anywhere in the document.
    """
    run = _staged_and_sealed_run(tmp_path)
    doc = read_json(run.objective)
    doc["predicted_surface_count"] = 99
    write_json(run.objective, doc)

    divergence = _section(brief.gate_brief(run, 0), DIVERGENCE_HEADER)
    assert re.search(r"predicted[^\n]*(?<!\w)99(?!\w)", divergence), divergence


def test_gate_zero_counts_the_surfaces_the_parts_actually_observed(tmp_path):
    """The other half of the divergence, which a `predicted_surface_count`
    passthrough would satisfy without computing anything.

    A fourth predicted surface whose evidence names a candidate no part
    admitted must come up unconfirmed -- so observed stays at the three the
    fan-out ruled on, and the shortfall is named rather than left as a
    number the reader has to derive.
    """
    run = _staged_and_sealed_run(tmp_path)
    doc = read_json(run.objective)
    doc["objective_review"]["surfaces"].append(
        {
            "name": "admin console",
            "evidence": ["console-md"],
            "weight": {"candidates": 1, "bytes": 1},
        }
    )
    doc["predicted_surface_count"] = 4
    write_json(run.objective, doc)

    divergence = _section(brief.gate_brief(run, 0), DIVERGENCE_HEADER)
    assert "admin console" in divergence
    # Three of the four predicted surfaces have an admitted candidate in a
    # part, so the observed total is 3 against a predicted 4.
    assert re.search(r"predicted[^\n]*: 4", divergence)
    assert re.search(r"observed[^\n]*: 3", divergence)


def test_gate_zero_reports_a_surface_a_slice_observed_but_the_map_never_predicted(tmp_path):
    """The surplus direction of section 4.1's divergence.

    `observed_surfaces[]` is by definition what a member saw that the corpus
    map did not name, so a rendering that only counted predicted surfaces would
    report "3 observed" here and lose the one fact the field exists to carry.
    """
    run = _staged_and_sealed_run(tmp_path)
    slice_id = run.slice_ids_with_parts()[0]
    part = read_json(run.disposition_part(slice_id))
    part["observed_surfaces"] = [
        {
            "name": "retry semantics",
            "evidence": [part["dispositions"][0]["candidate_id"]],
            "weight": {"candidates": 1, "bytes": 1},
        }
    ]
    write_json(run.disposition_part(slice_id), part)

    divergence = _section(brief.gate_brief(run, 0), DIVERGENCE_HEADER)
    assert "retry semantics" in divergence
    assert re.search(r"observed[^\n]*: 4", divergence)


def test_gate_zero_names_a_group_split_across_slices(tmp_path):
    """Spec section 5.2's provenance summary: gate 0 is the only place a human
    can act on the near-duplicate residue a split group leaves behind."""
    run = _staged_and_sealed_run(tmp_path)
    text = brief.gate_brief(run, 0)
    split = [
        p for s in read_json(run.slices)["slices"] for p in s["provenance"] if p["other_slices"]
    ]
    # Reachability first, behaviour second, and no branch between them. The
    # brief's `if split:` form is the fixture-cannot-reach weakness shape
    # CLAUDE.md names: it passes silently the day the fixture stops splitting.
    assert split, "fixture no longer splits a group across slices; this test is checking nothing"

    summary = _section(text, SPLIT_HEADER)
    assert split[0]["group"] in summary
    # And how many slices hold it, which is the fact the bullet asks for --
    # read off that group's own row, and as a number rather than as digits the
    # row's own slice-id list would supply anyway (`s02` carries a `2`).
    holders = set(split[0]["other_slices"])
    for entry in read_json(run.slices)["slices"]:
        for provenance in entry["provenance"]:
            if provenance["group"] == split[0]["group"] and provenance["other_slices"]:
                holders.add(entry["id"])
    row = _row(summary, f"{split[0]['group']}:")
    assert _has_number(row, len(holders)), row


def test_gate_zero_still_works_before_the_family_has_run(tmp_path):
    """A surveyed run has a catalogue and nothing else. The three new sections
    read three artifacts that do not exist yet, and none of them may crash the
    report that tells a human triage has not landed."""
    run = survey.survey(
        corpus_roots=[CORPUS],
        runs_dir=tmp_path / "runs",
        target_name="ticketq",
        target_interface="mcp",
        objective="breadth",
        max_rounds=2,
        max_scenarios=128,
    )
    text = brief.gate_brief(run, 0)
    assert text
    assert "triage-seal" in text
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "0"]) == 0


def test_gate_zero_states_which_staged_artifacts_it_could_not_read(tmp_path):
    """A sealed record whose staged parts have been cleared away -- the shape a
    run archived down to its record has. The record still renders in full, and
    each new section says what is missing rather than pretending it read a
    prediction, a slice plan or a fan-out that is not there."""
    run = _staged_and_sealed_run(tmp_path)
    run.slices.unlink()
    run.objective.unlink()
    for slice_id in run.slice_ids_with_parts():
        run.disposition_part(slice_id).unlink()

    text = brief.gate_brief(run, 0)
    # The record's own content is untouched, so the sections that were always
    # here still render.
    assert "Objective verdict" in text
    for header in (SLICES_HEADER, DIVERGENCE_HEADER, SPLIT_HEADER):
        assert header in text, f"{header!r} must state its absence, not vanish"
    assert "00-slices.json" in _section(text, SLICES_HEADER)
    assert "00-objective.json" in _section(text, DIVERGENCE_HEADER)
    # And the split-group section must not answer a question it cannot answer.
    # "(none -- every group the slicer found fits inside one slice)" reads as a
    # finding about the corpus; with no slice plan on disk it would be an
    # announcement of absence made because the input was not there, which is the
    # defect class `paths.list_dir`'s docstring exists to record.
    split = _section(text, SPLIT_HEADER)
    assert "fits inside one slice" not in split, split
    assert "00-slices.json" in split
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "0"]) == 0


@pytest.mark.parametrize(
    ("break_it", "label"),
    [
        (lambda path: path.write_text("{not json", encoding="utf-8"), "malformed"),
        (lambda path: path.chmod(0o000), "unreadable"),
    ],
)
def test_gate_zero_does_not_claim_no_group_was_split_when_it_cannot_tell(tmp_path, break_it, label):
    """The other two ways the slice plan goes unread, alongside the absent case
    above. A run whose 00-slices.json is malformed or unreadable is the run most
    likely to have a split nobody noticed, so this is the worst possible place
    to render "(none)"."""
    run = _staged_and_sealed_run(tmp_path)
    # Reachability: the fixture really does have a split to lose, so a passing
    # assertion below is about the rendering rather than about a plan that never
    # split anything.
    assert "fits inside one slice" not in _section(brief.gate_brief(run, 0), SPLIT_HEADER)
    break_it(run.slices)
    try:
        split = _section(brief.gate_brief(run, 0), SPLIT_HEADER)
        assert "fits inside one slice" not in split, split
        assert "00-slices.json" in split
        assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "0"]) == 0
    finally:
        run.slices.chmod(0o644)


@pytest.mark.parametrize("artifact", ["slices", "objective", "part"])
def test_gate_zero_does_not_raise_on_a_malformed_staged_artifact(tmp_path, artifact):
    """Each of the three new reads gets its own case.

    One malformed document per parametrize rather than all three at once: with
    all three broken, a section that crashed would be masked by whichever
    raised first, and the case would prove only that *something* was tolerated.
    """
    run = _staged_and_sealed_run(tmp_path)
    target = {
        "slices": run.slices,
        "objective": run.objective,
        "part": run.disposition_part(run.slice_ids_with_parts()[0]),
    }[artifact]
    target.write_text("{not json at all", encoding="utf-8")

    text = brief.gate_brief(run, 0)
    assert "Objective verdict" in text
    for header in (SLICES_HEADER, DIVERGENCE_HEADER, SPLIT_HEADER):
        assert header in text
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "0"]) == 0


@pytest.mark.parametrize("artifact", ["slices", "objective", "part"])
@pytest.mark.parametrize("mode", [0o000, 0o444])
def test_gate_zero_does_not_raise_on_an_unreadable_staged_artifact(tmp_path, artifact, mode):
    """`chmod 000` is the read this report must survive; `chmod 0444` is the
    control that proves the 000 case is measuring permission rather than the
    existence of the file, since a read-only artifact reads perfectly well and
    must render its content in full."""
    run = _staged_and_sealed_run(tmp_path)
    target = {
        "slices": run.slices,
        "objective": run.objective,
        "part": run.disposition_part(run.slice_ids_with_parts()[0]),
    }[artifact]
    target.chmod(mode)
    try:
        text = brief.gate_brief(run, 0)
        assert "Objective verdict" in text
        for header in (SLICES_HEADER, DIVERGENCE_HEADER, SPLIT_HEADER):
            assert header in text
        if mode == 0o444:
            # Readable, so the content must actually be there -- otherwise the
            # 000 case above would pass on a rendering that never reads at all.
            assert read_json(run.slices)["slices"][0]["id"] in _section(text, SLICES_HEADER)
        assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "0"]) == 0
    finally:
        target.chmod(0o644)


def test_gate_zero_reports_an_unreadable_dispositions_directory_as_a_broken_run(tmp_path):
    """An unreadable *directory* is not the same failure as an unreadable file,
    and this module's docstring already draws that line: a run directory that
    cannot be read at all is the harness pointed at something broken, which is
    exit 2. `paths.list_dir` exists to make that raise instead of silently
    yielding nothing, and `claim_utilisation` over `01-claims/` and gate 3 over
    `05-verdicts/` both already behave this way. Pinned here so the behaviour
    is a measured decision rather than an accident of which helper was reached.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = _staged_and_sealed_run(tmp_path)
    run.dispositions_dir.chmod(0o000)
    try:
        assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "0"]) == 2
    finally:
        run.dispositions_dir.chmod(0o755)


# --- Gate 1: the capabilities the denominator excludes ------------------------
#
# Issue 17 narrowed `denominator.capability_cells` to the cells a scenario can
# actually be driven through, and this listing is the last report of an excluded
# capability a human can still act on -- not the only one. `seal_score` writes an
# `unreachable` hole per undrivable cell (rounds.py:1343-1361, seal_score's
# `undrivable`/`injected` block) and `emit` names one capability per instance
# (emit.py:101-108, `to_contract`'s `unbound` closure),
# but the first is read at gate 2 and the second at stage 06, by which point the
# loop has already spent its rounds against the narrowed denominator. The spec's
# paired `check-refs` finding was removed in 11a6c25 because `check-refs` runs
# before gate 1, its exit 1 means "a repairable
# stage defect, spend the one repair attempt", and an unbound capability is not
# repairable by re-dispatch -- so the finding would have halted a correct run before
# the gate it was meant to be read at: derived from rb-orchestrate's A3 and A4,
# never observed, since no orchestrated run was dispatched against an unbound world
# model to watch the halt. `gate-brief` is a report, not a gate, which is why every
# test below also pins exit 0.


def _unbound_capabilities() -> list[dict]:
    """Two capabilities with no `binding` at all, for the listing to report.

    No `binding` key rather than an empty one, because that is what
    `rb-reconcile-capabilities` section 5 tells the pass to write rather than
    guess a tool name -- so this is the shape the listing exists to report, not a
    mangling of a well-formed one.

    Two rather than one, and deliberately unlike each other: one cell against
    two, one citing input against two. A single-capability fixture cannot tell a
    rendering that reads each capability's own cells and evidence from one that
    prints a constant, and singular/plural is exactly the detail a rendering gets
    wrong on the row nobody built a fixture for.
    """
    return [
        {
            "id": "cap-keycloak",
            "operation": "Integrate with Keycloak",
            "params": [],
            "outcome_classes": [
                {
                    "id": "oc-keycloak-ok",
                    "kind": "success",
                    "description": "the caller is authenticated against Keycloak",
                    "claims": ["clm-pyproject-001"],
                }
            ],
            "claims": ["clm-pyproject-001"],
            "confidence": "low",
        },
        {
            "id": "cap-a2a-cancel",
            "operation": "agent.task.cancel",
            "params": [{"name": "task_id", "type": "string", "required": True}],
            "outcome_classes": [
                {
                    "id": "oc-cancelled",
                    "kind": "success",
                    "description": "the task reaches a terminal cancelled state",
                    "claims": ["clm-api-005"],
                },
                {
                    "id": "oc-cancel-unsupported",
                    "kind": "error",
                    "description": "the handler raises, and the caller sees a JSON-RPC error",
                    "claims": ["clm-notes-004"],
                },
            ],
            "claims": ["clm-api-001", "clm-notes-001"],
            "confidence": "low",
        },
    ]


def _with_pyproject_claims(run: RunPaths) -> None:
    """One extra input asserting the claim `cap-keycloak` rests on.

    A new input rather than one of the toy's three, because the citing input is the
    one clue about *why* a binding is absent that this listing does not take on
    trust: the `operation` beside it is prose a reconcile pass wrote, while the
    input is resolved from `01-claims/` at read time. On run-20260827-070444, 10 of
    the 19 excluded capabilities cite `pyproject-toml` and 4 of those cite nothing
    else -- and all 4 are dependency declarations read as target behaviour rather
    than surfaces the target has, `cap-keycloak` among them, which is why it is this
    fixture's row. A fixture whose unbound capability cited the same input as the
    bound ones could not tell a rendering that resolves each claim to its input from
    one that prints a constant.
    """
    write_json(
        run.claims("pyproject-toml"),
        {
            "schema_version": "0.1",
            "artifact_id": "pyproject-toml",
            "claims": [
                {
                    "id": "clm-pyproject-001",
                    "kind": "capability",
                    "statement": "the project depends on python-keycloak",
                    "evidence": [{"artifact_id": "pyproject-toml", "locator": "dependencies[3]"}],
                    "confidence": "low",
                    "derivation": "inferred",
                }
            ],
        },
    )
    # The fixture is a document this pipeline could produce, or it teaches the
    # listing to read a shape that never arrives.
    assert validate_artifact(run.claims("pyproject-toml"), "claims") == []


def _unbound_run(tmp_path) -> RunPaths:
    """The toy world plus two capabilities that declare no `binding.tool`."""
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    _with_pyproject_claims(run)
    world = read_json(run.world_model)
    world["capabilities"].extend(_unbound_capabilities())
    # Honest rather than stale: `reconcile-seal` writes `len(drivable_cells)`, so
    # leaving the toy's own figure here would make the fixture carry the
    # pre-narrowing arithmetic this whole branch exists to remove.
    world["denominator"]["capability_cells"] = len(refs.drivable_cells(world))
    write_json(run.world_model, world)
    assert validate_artifact(run.world_model, "world-model") == []
    return run


def _wholly_unbound_run(tmp_path) -> RunPaths:
    """A schema-valid world model in which *nothing* is drivable.

    Not a hypothetical, and measured on this fixture rather than reasoned. It keeps
    the toy's two goals, and goal holes are closable with no binding anywhere: run
    `propose-batches --round 1` against it and it writes `02-batches/round-1.json`
    and the loop continues, proposing against goals with no capability surface
    underneath. Drop the goals (`goals: []`, `denominator.goals: 0`, still
    schema-valid) and the same run prints "no closable holes: there is no propose
    round to dispatch" and exits 0 -- the loop's normal terminal state, reached from
    an entirely undrivable world model.

    Gate 1 precedes propose, which is what makes the listing worth reading here
    rather than later: in the halting case nothing downstream is ever written, so no
    coverage document carries the `unreachable` holes and `emit` never runs. That is
    a claim about that case, not about every run -- with goals present, gate 2's
    coverage document does report the same cells.
    """
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    _with_pyproject_claims(run)
    world = read_json(run.world_model)
    for capability in world["capabilities"]:
        capability.pop("binding", None)
    world["capabilities"].extend(_unbound_capabilities())
    world["denominator"]["capability_cells"] = len(refs.drivable_cells(world))
    write_json(run.world_model, world)
    assert validate_artifact(run.world_model, "world-model") == []
    assert world["denominator"]["capability_cells"] == 0, "the fixture must be wholly undrivable"
    return run


def test_gate_one_lists_the_capabilities_excluded_from_the_denominator(tmp_path):
    """Code cannot classify WHY a binding is absent -- that is semantic, and layer
    2 never mechanises semantics. So the brief lists what it can read and lets a
    human group them: counted off this rendering on run-20260827-070444, 10 of the
    19 excluded capabilities cite pyproject-toml and 4 of those cite nothing else,
    which is legible from the listing and is the actual cause of the magnitude.
    """
    run = _unbound_run(tmp_path)
    section = _section(brief.gate_brief(run, 1), brief.EXCLUDED_HEADER)

    one_cell = _row(section, "cap-keycloak")
    assert _has_number(one_cell, 1)
    assert "1 cell" in one_cell and "cells" not in one_cell, "singular for one cell"
    assert "pyproject-toml" in one_cell
    # The discriminating half: a rendering that printed every input, or a
    # constant, would satisfy the line above. cap-keycloak rests on one claim from
    # one input, and the toy's three inputs must not appear beside it.
    assert "api-json" not in one_cell and "notes-md" not in one_cell
    assert "Integrate with Keycloak" in section

    two_cells = _row(section, "cap-a2a-cancel")
    assert "2 cells" in two_cells
    assert "api-json" in two_cells and "notes-md" in two_cells
    assert "pyproject-toml" not in two_cells
    assert "agent.task.cancel" in section


def test_gate_one_states_both_numbers_when_capabilities_are_excluded(tmp_path):
    """Both numbers, always -- the argument the reconcile sweep's line already
    makes. The counts are read back out of the fixture rather than asserted as
    literals alone, so a rendering that printed the wrong one of the two fails
    here: 4 capabilities, 2 of them bound, 4 of the 7 cells drivable."""
    run = _unbound_run(tmp_path)
    world = read_json(run.world_model)
    section = _section(brief.gate_brief(run, 1), brief.EXCLUDED_HEADER)

    capability_line = _row(section, "2 of 4 capabilities")
    assert _has_number(capability_line, len(world["capabilities"]) - 2), "drivable capabilities"
    assert _has_number(capability_line, len(world["capabilities"])), "declared capabilities"

    cell_line = _row(section, "4 of 7 capability")
    assert _has_number(cell_line, len(refs.drivable_cells(world))), "drivable cells"
    assert _has_number(cell_line, 7), "declared cells"


def test_gate_one_says_so_when_every_capability_is_drivable(tmp_path):
    """A brief that printed the section only when non-empty would render "every
    capability is drivable" as silence, and that is a strong claim a reader should
    see stated. `_full_run` is the toy world: 2 capabilities, both bound."""
    run = _full_run(tmp_path)
    section = _section(brief.gate_brief(run, 1), brief.EXCLUDED_HEADER)

    assert "all 2 capabilities are drivable" in section
    # No listing and no remedy when there is nothing to act on -- the section is a
    # statement here, not an empty table with advice under it.
    assert "binding.fixed_args" not in section


def test_gate_one_makes_a_wholly_undrivable_world_model_impossible_to_miss(tmp_path):
    """With no binding anywhere and nothing else left to close, `propose-batches`
    prints the same "no closable holes" a genuinely converged round prints. A reader
    at gate 1 is the last one who can tell those apart, so the rendering must not
    let the distinction sit inside a table of counts.

    The condition is stated rather than the halt asserted, and `_wholly_unbound_run`
    records why: this fixture's own goals keep the loop going, so a rendering that
    promised the halt would be wrong on the fixture it is measured against."""
    run = _wholly_unbound_run(tmp_path)
    section = _section(brief.gate_brief(run, 1), brief.EXCLUDED_HEADER)

    # Located by the fence rather than by each line's opening words: a prefix pin on
    # prose is the mirror failure CLAUDE.md names, where a meaning-preserving
    # reword goes red for no reason. The fence is the rendering decision under
    # test, so it is what the assertion holds.
    banner = [line for line in section.splitlines() if line.strip().startswith("***")]
    # `>= 2` rather than `== 3`: how many lines the warning takes is the same
    # editorial choice the comment below already concedes, and a four-line split
    # (better at 80 columns) or a two-line merge under 100 would go red for no
    # requirement's sake. The alarm has to lead and the rest has to follow it, which
    # is what two lines is the floor for; the per-line fence and width assertions
    # below carry the rest of the requirement.
    assert len(banner) >= 2, f"expected the alarm and at least one line under it, got {banner}"

    loud, *follow = banner
    # The one phrase that IS pinned, deliberately: the requirement is words a reader
    # cannot mistake for a normal result, and shouted absolutes are the whole
    # instrument. Both numbers are on this line too.
    assert "NOTHING IS DRIVABLE" in loud
    assert _has_number(loud, 0) and _has_number(loud, 4)

    # The mistaking this exists to prevent, named in the rendering itself. Asserted
    # over the follow-on lines together, so how the sentence is split between them
    # stays an editorial choice. Both phrases are pinned verbatim on purpose, and
    # neither is incidental wording: "no closable holes" is the literal string
    # propose-batches prints (cli.py:606), which is the message the reader will
    # actually be handed, and "NOT a converged run" is the reading it must not be
    # given. Rewording either would change what this line does.
    rest = " ".join(follow)
    assert "no closable holes" in rest
    assert "NOT a converged run" in rest

    # A banner that wraps is not a banner. Measured at 215 characters on the first
    # draft: at 80 and at 120 columns the closing fence landed mid-paragraph and
    # everything after the first visual line read as prose, which is exactly the
    # loudness this branch exists for. Each fenced line has to fit a normal terminal
    # on its own, so both ends of the fence stay visible.
    for line in banner:
        assert line.rstrip().endswith("***"), line
        assert len(line) <= 100, f"{len(line)} characters wraps in a normal terminal: {line}"

    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "1"]) == 0


def test_gate_one_names_the_remedy_without_promising_a_re_dispatch(tmp_path):
    """The removed check-refs finding was criticised for stating the exclusion
    with no action, and emit.py's late report is the one that names it. A reader
    at gate 1 is the only person who can still act, and the one action that does
    NOT work has to be named too: rb-reconcile-capabilities section 5 tells the
    pass to leave `binding` off rather than guess a tool name, so spending a
    repair attempt on it changes nothing."""
    section = _section(brief.gate_brief(_unbound_run(tmp_path), 1), brief.EXCLUDED_HEADER)

    remedy = _row(section, "Acting on this")
    assert "binding.tool" in remedy and "binding.fixed_args" in remedy
    assert "01-world-model.json" in remedy

    # Co-occurrence on the one line that owns the rule, not presence anywhere in
    # the section: a section that promised a repair would still carry both
    # "re-dispatch" and "not" somewhere in it.
    no_repair = _row(section, "Re-dispatching")
    assert "will not" in no_repair


def test_gate_one_does_not_assert_a_cause_for_a_missing_binding(tmp_path):
    """Absence of `binding.tool` has three causes on the one run this was measured
    against -- a dependency declaration that is not target behaviour, a real
    surface on another interface, and real agent-level behaviour `binding`'s tool
    shape cannot express -- and telling them apart is semantic. A rendering that
    named one of them would be asserting a classification code cannot make."""
    section = _section(brief.gate_brief(_unbound_run(tmp_path), 1), brief.EXCLUDED_HEADER)

    for asserted_cause in ("dependency", "another interface", "agent-level", "not real"):
        assert asserted_cause not in section.lower()


def test_gate_one_excluded_listing_survives_a_malformed_claims_file(tmp_path):
    """`gate_brief` never raises on a readable run's content -- this module's
    docstring, and the ruling `_quietly` already carries. The capability is still
    reported when the file that would name its input cannot be read; only the
    input is unknown."""
    run = _unbound_run(tmp_path)
    run.claims("pyproject-toml").write_text("{not json", encoding="utf-8")

    section = _section(brief.gate_brief(run, 1), brief.EXCLUDED_HEADER)

    one_cell = _row(section, "cap-keycloak")
    assert "pyproject-toml" not in one_cell, "the file that would have named it is unreadable"
    assert "?" in one_cell
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "1"]) == 0


def test_gate_one_excluded_listing_costs_one_malformed_claims_file_only_its_own(tmp_path):
    """Per file rather than per directory: one unreadable member must cost its own
    claims and not the whole listing. A single guard around the walk would turn
    every capability's input list into `?` instead."""
    run = _unbound_run(tmp_path)
    run.claims("api-json").write_text("{not json", encoding="utf-8")

    section = _section(brief.gate_brief(run, 1), brief.EXCLUDED_HEADER)

    assert "pyproject-toml" in _row(section, "cap-keycloak")
    assert "notes-md" in _row(section, "cap-a2a-cancel")
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "1"]) == 0


@pytest.mark.parametrize(
    ("capabilities", "stated"),
    [
        # Every shape a hand-edit at this gate produces that reaches refs._cells'
        # and refs.drivable_cells' unguarded indexing. Measured before the guard:
        # a truthy non-list raises `AttributeError: 'str' object has no attribute
        # 'get'` out of both, a capability with no `id` raises `KeyError: 'id'`
        # out of _cells, and a non-list `outcome_classes` raises `TypeError:
        # string indices must be integers` out of _cells.
        #
        # `stated` is what the section must say for that shape, and it is the half
        # that makes this more than a not-raises test: the three outcomes are
        # "nothing readable to report", "present but uncountable", and "countable
        # even though malformed", and a rendering that dropped the uncountable line
        # entirely would pass a bare not-raises assertion on all six.
        ("nope", "declares no readable capability"),
        (
            [{"operation": "no id at all", "outcome_classes": [{"id": "oc-x"}]}],
            "could not be counted",
        ),
        (
            [{"id": "cap-x", "operation": "bad classes", "outcome_classes": "x"}],
            "could not be counted",
        ),
        (
            [{"id": "cap-x", "operation": "null binding", "binding": None, "outcome_classes": []}],
            "0 of 0 capability x outcome-class cells count",
        ),
        (["not a capability object at all"], "declares no readable capability"),
        (
            [{"id": ["not", "a", "string"], "operation": "unhashable id", "outcome_classes": []}],
            "0 of 0 capability x outcome-class cells count",
        ),
    ],
)
def test_gate_one_excluded_listing_does_not_raise_on_a_malformed_world_model(
    tmp_path, capabilities, stated
):
    """A report that reports "this document is malformed" by crashing is the least
    useful reading of a document -- `_dicts`' ruling, and the exit-code contract's
    for a report. `rubrica validate --stage reconcile-seal` is what names the
    defect; this must state what it could not count and exit 0."""
    run = build_toy_run(tmp_path / "runs", upto="reconcile-seal")
    world = read_json(run.world_model)
    world["capabilities"] = capabilities
    write_json(run.world_model, world)

    text = brief.gate_brief(run, 1)  # must not raise

    assert stated in _section(text, brief.EXCLUDED_HEADER)
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "1"]) == 0


def test_gate_one_excluded_listing_is_quiet_before_the_world_model_exists(tmp_path):
    """Gate 1 is read on runs that stopped short of the seal, and the section must
    say it has nothing to report rather than claim every capability is drivable --
    which is what the "all N" branch renders if it is reached with N of 0."""
    run = build_toy_run(tmp_path / "runs", upto="extract")

    section = _section(brief.gate_brief(run, 1), brief.EXCLUDED_HEADER)

    assert "nothing to report" in section
    assert "drivable" not in section
    assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "1"]) == 0


def test_gate_one_excluded_listing_separates_an_empty_world_model_from_an_absent_one(tmp_path):
    """`capabilities: []` is schema-valid -- world-model-0.1.json sets no minItems
    on it -- and a reader acts differently on "no world model yet" than on "a
    sealed world model that declares nothing". Neither may render as "all 0
    capabilities are drivable", which is the branch an empty list otherwise falls
    into and is a claim about a surface that does not exist."""
    absent = build_toy_run(tmp_path / "runs-absent", upto="extract")
    empty = build_toy_run(tmp_path / "runs-empty", upto="reconcile-seal")
    world = read_json(empty.world_model)
    world["capabilities"] = []
    world["denominator"]["capability_cells"] = 0
    write_json(empty.world_model, world)
    assert validate_artifact(empty.world_model, "world-model") == []

    absent_section = _section(brief.gate_brief(absent, 1), brief.EXCLUDED_HEADER)
    empty_section = _section(brief.gate_brief(empty, 1), brief.EXCLUDED_HEADER)

    assert "nothing to report" in absent_section
    assert "nothing to report" in empty_section
    assert "drivable" not in absent_section and "drivable" not in empty_section
    assert absent_section != empty_section, "a sealed world model is a different state"
    assert cli.main(["gate-brief", "--run", str(empty.root), "--gate", "1"]) == 0


def test_gate_one_excluded_listing_survives_an_unreadable_claims_file(tmp_path):
    """Unreadable is not the same failure as malformed, and only this one reaches
    `read_json` as an OSError rather than a JSON error. The module's docstring
    draws the line at the *directory*: an unreadable `01-claims/` is the harness
    pointed at something broken and still exits 2
    (`test_an_unreadable_claims_directory_is_exit_2_from_both_reports`), while one
    unreadable member is content this report states rather than raises on."""
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = _unbound_run(tmp_path)
    target = run.claims("pyproject-toml")
    target.chmod(0o000)
    try:
        section = _section(brief.gate_brief(run, 1), brief.EXCLUDED_HEADER)

        one_cell = _row(section, "cap-keycloak")
        assert "pyproject-toml" not in one_cell
        assert "?" in one_cell
        # The other members are still read, so the listing degrades by one row's
        # input list rather than wholesale.
        assert "notes-md" in _row(section, "cap-a2a-cancel")
        assert cli.main(["gate-brief", "--run", str(run.root), "--gate", "1"]) == 0
    finally:
        target.chmod(0o644)
