"""The golden fixture, run through every layer with no model involved.

Section 9's "one golden end-to-end fixture ... run in CI". Deliberately *not*
folded into test_refs_states.py: that file's contract is one cumulative table
over the minimal builders, where each state is reachable by one more builder
call and the thing under test is check_all's silence. This file is the other
shape -- one complete run, checked at every layer, from real input files.

Every expected number here was measured against the real code, not predicted.
"""

from __future__ import annotations

import json

import pytest

from rubrica.emit import emit_run
from rubrica.refs import check_all
from rubrica.smoke import ORACLE_FLOOR, WEAK_BASELINE_CEILING, smoke_run
from rubrica.validate import validate_stage
from tests.toy import ARTIFACT_IDS, SIDS, build_toy_run, toy_roster

# Stages with a real artifact to gate at the point the fixture reaches. emit and
# smoke are checked after they run, further down.
AUTHORED_STAGES = (
    "intake",
    "extract",
    "reconcile",
    "propose",
    "score",
    "instantiate",
    "challenge",
)


@pytest.fixture
def toy_run(tmp_path):
    return build_toy_run(tmp_path / "runs")


def test_intake_registered_the_three_inputs_with_digests_it_computed(toy_run):
    """Real intake, so the digest and stored_as chain is produced rather than
    asserted. A hand-written digest could only ever satisfy a check that was
    not looking -- refs.check_inputs re-hashes these bytes.
    """
    manifest = json.loads(toy_run.manifest.read_text(encoding="utf-8"))
    assert [e["artifact_id"] for e in manifest["inputs"]] == list(ARTIFACT_IDS)
    assert [e["stored_as"] for e in manifest["inputs"]] == [
        "api-json.json",
        "notes-md.md",
        "trace-json.json",
    ]
    assert [e["kind"] for e in manifest["inputs"]] == ["mcp_tool_schema", "design_doc", "trace"]
    for entry in manifest["inputs"]:
        assert toy_run.input_file(entry["stored_as"]).is_file()


@pytest.mark.parametrize("stage", AUTHORED_STAGES)
def test_layer_1_is_clean_for_every_authored_stage(toy_run, stage):
    assert validate_stage(toy_run, stage) == []


def test_layer_2_is_clean_over_the_whole_run(toy_run):
    """Including the reachability gate over four seeds, both machine invariant
    forms, the discriminating_fact comparison, and the coverage/hole
    reconciliation in both directions.
    """
    assert check_all(toy_run) == []


def test_emit_produces_one_complete_package_per_scenario(toy_run):
    """tests/verify.py and tests/test.sh are checked for byte-identity across
    every package in this run, not just file presence. The design forbids a
    per-task generated verifier -- every package must run the identical
    scorer -- and `emit_run`'s copy call takes no per-scenario argument, so
    there is no code path by which two packages in the same run could
    legitimately differ here. test_emit_packages.py's `test_the_verifier_
    and_entrypoint_are_copied_verbatim` already pins one package against
    suite_template_dir(); this is the multi-package half of that claim, which
    a single-scenario fixture cannot exercise.
    """
    from rubrica.emit import suite_template_dir

    emitted, findings = emit_run(toy_run)
    assert (emitted, findings) == (sorted(SIDS), [])
    assert validate_stage(toy_run, "emit") == []
    assert check_all(toy_run) == []
    for sid in SIDS:
        for name in (
            "task.toml",
            "instruction.md",
            "seed.json",
            "golden.json",
            "provenance.md",
            "tests/expected.json",
            "tests/verify.py",
            "tests/test.sh",
        ):
            assert (toy_run.task_dir(sid) / name).is_file(), f"{sid}/{name}"
        for name in ("verify.py", "test.sh"):
            assert (toy_run.task_dir(sid) / "tests" / name).read_bytes() == (
                suite_template_dir() / name
            ).read_bytes(), f"{sid}'s {name} diverges from the shared template"


def test_the_emitted_contract_never_carries_a_kind_outside_the_vocabulary(toy_run):
    """The closed vocabulary, checked on the artifact that reaches the scorer.
    A kind the verifier does not implement scores as failed, silently, and the
    schema does not catch it because the *shape* is fine.
    """
    from rubrica.suite.verify import ASSERTION_KINDS

    emit_run(toy_run)
    for sid in SIDS:
        contract = json.loads(
            (toy_run.task_dir(sid) / "tests" / "expected.json").read_text(encoding="utf-8")
        )
        for assertion in contract["assertions"]:
            assert assertion["kind"] in ASSERTION_KINDS


def test_smoke_scores_the_suite_with_a_non_degenerate_spread(toy_run, tmp_path):
    """Success criterion #1: the suite executes and yields a spread.

    The three means below were measured, not predicted. The oracle at 1.0 is the
    test of the test suite -- if it drops, the labels or the verifier are broken,
    not the agent.
    """
    emit_run(toy_run)
    report, findings = smoke_run(toy_run, toy_roster(tmp_path))
    assert findings == []
    means = report["summary"]["mean_reward_by_role"]
    assert means == {"weak_baseline": 0.2, "under_test": 0.766667, "oracle": 1.0}
    assert report["verdict"] == "healthy"
    assert report["summary"]["unscoreable"] == 0
    assert report["summary"]["oracle_failures"] == 0
    assert validate_stage(toy_run, "smoke") == []
    assert check_all(toy_run) == []


def test_the_spread_clears_both_thresholds_it_is_measured_against(toy_run, tmp_path):
    """States *why* the verdict is healthy, against the constants rather than
    the literals. If a threshold moves, this fails with the reason attached
    instead of the previous test failing on a number nobody can interpret.

    The brief's draft of this test ended with
    `weak < under_test < oracle or (under_test <= oracle)` -- a tautology,
    since the second clause is true whenever the first is false (oracle is
    always >= under_test in this fixture) and also whenever it's true. That
    `or` makes the assertion unable to fail, which is worse than no test at
    all: it reads as coverage of the ordering while checking nothing beyond
    what the two threshold comparisons above it already check. Replaced with
    the strict ordering the fixture actually satisfies.
    """
    emit_run(toy_run)
    report, _ = smoke_run(toy_run, toy_roster(tmp_path))
    means = report["summary"]["mean_reward_by_role"]
    assert means["weak_baseline"] <= WEAK_BASELINE_CEILING
    assert means["oracle"] >= ORACLE_FLOOR
    assert means["weak_baseline"] < means["under_test"] <= means["oracle"]


def test_each_package_carries_its_own_scenarios_everything(toy_run):
    """Each emitted package was compiled entirely from *its own* scenario:
    its own oracle, its own seed, its own metadata, its own question.

    Necessary because no reward number can establish it: all three roles score
    identically on the two absence-shaped tasks (0.4 / 1.0 / 1.0), so a
    mislabeling between them moves nothing. And layer 2 only catches part of
    it -- refs.check_instances compares expected.json's scenario_id against its
    directory, so a *directory* swap is reported, but swapping which oracle,
    seed, or scenario metadata attaches to which id, with the capability
    wiring left correctly matched, passes check_all and every reward
    assertion in this file. scn-empty and scn-missing both ground their
    answer_excludes assertion at seed_pointer "/collections/tickets/2",
    which resolves to nothing in either seed (each has exactly two tickets)
    -- so a seed swap between the two changes no finding and no reward
    either. A metadata swap is the sharpest of the three: instruction.md is
    the question the agent is actually asked, so a swap there means one
    package poses the other's question while carrying its own seed and its
    own oracle -- not a bookkeeping error, an unfair task, and check_all
    stays silent through it too. Verified by performing all three swaps.

    Every side derives from toy_expected(sid)/toy_seed(sid)/toy_scenarios()
    rather than a hardcoded literal, so the check keeps working when the
    fixture's wording, seed, or scenario metadata changes -- and so that
    under a swap the fixture still returns the right content while the
    package holds the wrong one, which is what makes the assertion fire.

    Not pinned here: tests/verify.py and tests/test.sh. Both are copied from
    suite_template_dir() with no scenario-specific argument in the call that
    writes them, so there is no per-scenario value for a swap to attach to
    the wrong id -- see test_emit_produces_one_complete_package_per_scenario
    for the across-packages byte-identity check that property still
    deserves.
    """
    import tomllib

    from rubrica.emit import bindings, call_spec
    from tests.toy import toy_expected, toy_scenarios, toy_seed, toy_world_model

    scenarios_by_id = {s["id"]: s for s in toy_scenarios()["scenarios"]}
    bound = bindings(toy_world_model())

    emit_run(toy_run)
    for sid in SIDS:
        scenario = scenarios_by_id[sid]
        oracle = toy_expected(sid)

        contract = json.loads(
            (toy_run.task_dir(sid) / "tests" / "expected.json").read_text(encoding="utf-8")
        )
        assert contract["scenario_id"] == sid
        emitted = {(a.get("target"), a["value"]) for a in contract["assertions"]}
        expected = {(a.get("target"), a["value"]) for a in oracle["assertions"]}
        assert emitted == expected, f"{sid}'s package carries another scenario's assertions"

        golden = json.loads((toy_run.task_dir(sid) / "golden.json").read_text(encoding="utf-8"))
        assert golden["answer"] == oracle["answer_reference"]
        expected_calls = [
            call_spec(bound[op["capability_id"]], op.get("args", {}))
            for op in oracle["trajectory"]["operations"]
        ]
        assert golden["tool_calls"] == expected_calls, (
            f"{sid}'s package's golden calls belong to another scenario's trajectory"
        )

        seed = json.loads((toy_run.task_dir(sid) / "seed.json").read_text(encoding="utf-8"))
        assert seed == toy_seed(sid), f"{sid}'s package ships another scenario's seed"

        instruction = (toy_run.task_dir(sid) / "instruction.md").read_text(encoding="utf-8")
        assert instruction.strip() == scenario["user_intent"].strip(), (
            f"{sid}'s package asks another scenario's question"
        )

        with (toy_run.task_dir(sid) / "task.toml").open("rb") as handle:
            task_toml = tomllib.load(handle)
        assert task_toml["task"]["description"] == scenario["title"]
        assert task_toml["metadata"]["goal_id"] == scenario["goal_id"]
        assert task_toml["metadata"]["actor_id"] == scenario["actor_id"]
        assert task_toml["metadata"]["hop_depth"] == scenario["hop_depth"]


def test_the_weak_baseline_scores_only_on_the_absence_shaped_tasks(toy_run, tmp_path):
    """Pins the finding this fixture surfaced, so it cannot regress silently.

    verify.score_assertions scores an exclusion satisfied by absence as a point,
    by design -- so a refusing agent collects every answer_excludes assertion
    for free. The two absence-shaped scenarios are therefore partly passable by
    saying nothing, and what keeps them honest is the tool_called assertion each
    also carries. That is why rb-instantiate's invariants require one.

    Without this test, an edit that dropped the tool_called assertion from an
    absence scenario would raise the weak baseline toward its ceiling and only
    the aggregate mean would move -- a number no reader can attribute.
    """
    emit_run(toy_run)
    report, _ = smoke_run(toy_run, toy_roster(tmp_path))
    by_task = {
        task["scenario_id"]: {r["role"]: r["reward"] for r in task["results"]}
        for task in report["tasks"]
    }
    assert by_task["scn-open"]["weak_baseline"] == 0.0
    assert by_task["scn-blocked"]["weak_baseline"] == 0.0
    assert by_task["scn-empty"]["weak_baseline"] == 0.4
    assert by_task["scn-missing"]["weak_baseline"] == 0.4


def test_every_absence_shaped_scenario_carries_an_assertion_a_refusal_fails(toy_run):
    """The fixture-level statement of the invariant rb-instantiate must enforce.

    A scenario whose assertions are *all* exclusions is substantially passable
    by an agent that answers nothing, which removes exactly the signal the weak
    baseline exists to provide.
    """
    from rubrica.suite.verify import DATA_KINDS, TRAJECTORY_KINDS
    from tests.toy import toy_expected

    for sid in SIDS:
        assertions = toy_expected(sid)["assertions"]
        exclusions = [a for a in assertions if a["kind"] == "answer_excludes"]
        if not exclusions:
            continue
        refusal_proof = [
            a
            for a in assertions
            if a["kind"] in TRAJECTORY_KINDS
            or (a["kind"] in DATA_KINDS and a["kind"] != "answer_excludes")
        ]
        assert refusal_proof, f"{sid} is passable by a refusal"


def test_the_verifier_that_scores_is_the_copied_one_under_a_bare_import_surface(toy_run, tmp_path):
    """smoke runs the package's own verify.py under `python -S` with a scrubbed
    environment, so the stdlib-only constraint is enforced by execution rather
    than declared. Pinned here because the golden run is the only place all four
    packages are scored at once.
    """
    emit_run(toy_run)
    smoke_run(toy_run, toy_roster(tmp_path))
    for sid in SIDS:
        verifier_out = toy_run.smoke_dir("oracle", sid) / "verifier"
        assert (verifier_out / "reward.txt").is_file(), sid
        assert float((verifier_out / "reward.txt").read_text()) == 1.0
