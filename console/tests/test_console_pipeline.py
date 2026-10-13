"""The console's step model: what a run's files on disk say is done and next.

Read-only and pure, so it is tested directly over toy-run checkpoints rather than
through the server.
"""

from __future__ import annotations

import json
import os

import pytest
from rubrica_console import pipeline
from rubrica_console.pipeline import DONE, FAILED, READY, WAITING, Ledger

from tests.toy import build_toy_run

# The step a run stopped after each checkpoint should offer next. The toy run's
# own checkpoints, so a stage added to the walk without a checkpoint here is the
# thing the parametrisation below makes visible.
_NEXT = {
    "triage-slices": "triage-objective",
    "triage-objective": "triage-rule",
    "triage-rule": "triage-audit",
    "triage-audit": "triage-seal",
    "triage-seal": "gate-0",
    "intake": "extract",
    "extract": "reconcile-subjects",
    "reconcile-gaps": "reconcile-services",
    "reconcile-services": "synthesise-interfaces",
    "synthesise-interfaces": "reconcile-seal",
    "reconcile-seal": "gate-1",
    "propose": "round-1/propose-seal",
    "propose-seal": "round-1/score",
    "score": "round-1/propose-seal-2",
    "score-seal": "gate-2",
    "instantiate": "challenge",
    "challenge": "gate-3",
}


@pytest.mark.parametrize("upto", sorted(_NEXT))
def test_each_checkpoint_offers_the_next_step_of_the_walk(tmp_path, upto):
    run = build_toy_run(tmp_path, upto=upto)
    steps = pipeline.steps(run)
    nxt = pipeline.next_step(steps)
    assert nxt is not None and nxt.id == _NEXT[upto]
    assert nxt.status == READY
    # Everything after the next step that is not done is waiting, never ready.
    after = steps[steps.index(nxt) + 1 :]
    assert all(s.status in (DONE, WAITING) for s in after)


def test_a_complete_run_waits_only_on_gate_3_then_emit(tmp_path):
    run = build_toy_run(tmp_path)
    steps = pipeline.steps(run)
    assert pipeline.next_step(steps).id == "gate-3"


def test_the_survey_path_has_triage_steps_and_the_intake_path_does_not(tmp_path):
    survey = build_toy_run(tmp_path / "a", upto="triage-seal")
    intake = build_toy_run(tmp_path / "b", upto="intake")
    assert pipeline.find(pipeline.steps(survey), "triage-rule") is not None
    assert pipeline.find(pipeline.steps(intake), "triage-rule") is None


def test_every_step_carries_a_one_line_summary(tmp_path):
    # Both paths, so the triage steps and the late steps are all reached; a step
    # added to the walk without a line in SUMMARIES fails here, not in the UI.
    seen = pipeline.steps(build_toy_run(tmp_path / "a", upto="triage-seal"))
    seen += pipeline.steps(build_toy_run(tmp_path / "b"))
    missing = sorted({s.id for s in seen if not s.summary})
    assert not missing
    assert all("\n" not in s.summary for s in seen)
    # And no line is left over for a step the walk no longer has.
    keys = {s.id.rsplit("/", 1)[-1] for s in seen}
    assert set(pipeline.SUMMARIES) <= keys


def test_fan_out_members_come_from_the_run_files(tmp_path):
    run = build_toy_run(tmp_path, upto="intake")
    extract = pipeline.find(pipeline.steps(run), "extract")
    inputs = [i["artifact_id"] for i in json.loads(run.manifest.read_text())["inputs"]]
    assert sorted(extract.members_todo) == sorted(inputs)
    assert extract.recipe[0] == {"op": "fanout", "stage": "extract", "ids": extract.members_todo}
    # check-refs comes after the fan-out, once, never per member.
    assert [op["op"] for op in extract.recipe] == ["fanout", "validate", "check-refs", "record"]


def test_a_free_text_gate_line_counts_and_a_mid_sentence_mention_does_not(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    run.decisions.write_text(
        "- 2026-10-07T19:15:47Z round loop note: Gate 1 passed without review\n",
        encoding="utf-8",
    )
    assert pipeline.find(pipeline.steps(run), "gate-1").status == READY
    with run.decisions.open("a", encoding="utf-8") as fh:
        fh.write("- 2026-10-07T16:29:53Z Gate 1: user approved the world model\n")
    assert pipeline.find(pipeline.steps(run), "gate-1").status == DONE


def test_a_gate_is_inferred_passed_when_a_later_stage_ran(tmp_path):
    run = build_toy_run(tmp_path, upto="propose")
    gate = pipeline.find(pipeline.steps(run), "gate-1")
    assert gate.status == DONE
    assert "later stage" in gate.reason


def test_blocking_gaps_are_named_on_gate_1(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    world = json.loads(run.world_model.read_text())
    world.setdefault("gaps", []).append({"id": "gap-x", "blocks": ["instantiate"]})
    run.world_model.write_text(json.dumps(world), encoding="utf-8")
    gate = pipeline.find(pipeline.steps(run), "gate-1")
    assert any("gap-x" in n and "instantiate" in n for n in gate.notes)


def test_a_re_score_makes_both_later_seals_stale(tmp_path):
    """B9's reject path: a rewritten score part means both seals must run again."""
    run = build_toy_run(tmp_path, upto="score-seal")
    later = max(os.stat(p).st_mtime_ns for p in run.root.rglob("*.json")) + 10**9
    os.utime(run.score_part(1), ns=(later, later))
    steps = pipeline.steps(run)
    assert pipeline.find(steps, "round-1/propose-seal-2").status == READY
    assert pipeline.find(steps, "round-1/score-seal").status == WAITING


def test_no_closable_holes_ends_the_loop(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-seal")
    run.decisions.write_text(
        "- 2026-10-12T00:00:00Z human gate 1 (console): ok\n"
        "- 2026-10-12T00:00:01Z round 1: no closable holes; the loop ends (console)\n",
        encoding="utf-8",
    )
    steps = pipeline.steps(run)
    assert pipeline.find(steps, "round-1/propose") is None
    assert pipeline.next_step(steps).id == "gate-2"


def test_a_human_can_stop_the_loop_after_a_round(tmp_path):
    run = build_toy_run(tmp_path, upto="score-seal")
    doc = json.loads(run.coverage_round(1).read_text())
    doc["verdict"] = "continue"
    run.coverage_round(1).write_text(json.dumps(doc), encoding="utf-8")
    # A `continue` under the round cap opens round 2 ...
    manifest = json.loads(run.manifest.read_text())
    manifest["limits"]["max_rounds"] = 3
    run.manifest.write_text(json.dumps(manifest), encoding="utf-8")
    assert pipeline.find(pipeline.steps(run), "round-2/propose-batches") is not None
    # ... and a recorded ruling closes it.
    with run.decisions.open("a", encoding="utf-8") as fh:
        fh.write("- 2026-10-12T00:00:00Z round loop stopped after round 1 (console): enough\n")
    steps = pipeline.steps(run)
    assert pipeline.find(steps, "round-2/propose-batches") is None
    assert pipeline.next_step(steps).id == "gate-2"


def test_the_ledger_overrides_disk_both_ways(tmp_path):
    run = build_toy_run(tmp_path, upto="intake")
    accepted = pipeline.steps(run, Ledger(accepted={"extract"}))
    assert pipeline.find(accepted, "extract").status == DONE
    assert pipeline.next_step(accepted).id == "reconcile-subjects"
    run2 = build_toy_run(tmp_path / "b", upto="extract")
    failed = pipeline.steps(run2, Ledger(failed={"extract"}))
    assert pipeline.find(failed, "extract").status == FAILED
    assert pipeline.next_step(failed).id == "extract"


def test_a_malformed_artifact_reads_as_not_done_rather_than_raising(tmp_path):
    run = build_toy_run(tmp_path, upto="extract")
    run.subjects.write_text("not json", encoding="utf-8")
    steps = pipeline.steps(run)
    contradict = pipeline.find(steps, "reconcile-contradict")
    assert contradict.members_todo == [] and contradict.status != DONE


def test_followup_counts_re_seeds_once_and_rejects(tmp_path):
    run = build_toy_run(tmp_path)
    a, b = run.scenario_ids_with_instances()[:2]
    for sid in (a, b):
        doc = json.loads(run.verdict(sid).read_text())
        doc["verdict"] = "re-seed"
        run.verdict(sid).write_text(json.dumps(doc), encoding="utf-8")
    step = pipeline.find(pipeline.steps(run, Ledger(reseeded={a})), "followup")
    op = step.recipe[0]
    # b gets its one re-seed; a already had it, so its second re-seed is a reject.
    assert op["reseed"] == [b]
    assert op["reject"] == [a]
