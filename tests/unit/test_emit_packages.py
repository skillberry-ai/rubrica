"""Writing an accepted instance out as a Harbor task package."""

from __future__ import annotations

import json
import tomllib

from rubrica.artifacts import write_json
from rubrica.emit import emit_run, suite_template_dir
from rubrica.paths import RunPaths
from tests.builders import (
    minimal_expected,
    minimal_manifest,
    minimal_scenarios,
    minimal_seed,
    minimal_verdict,
    minimal_world_model,
)

SID = "scn-001"


def _run(tmp_path, *, verdict=..., scenarios=None, world=None, expected=None) -> RunPaths:
    """A run populated through challenge, ready for emit."""
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    write_json(run.manifest, minimal_manifest())
    write_json(run.world_model, world if world is not None else minimal_world_model())
    write_json(run.scenarios, scenarios if scenarios is not None else minimal_scenarios())
    write_json(run.seed(SID), minimal_seed())
    write_json(run.expected(SID), expected if expected is not None else minimal_expected())
    if verdict is not ...:
        if verdict is not None:
            write_json(run.verdict(SID), verdict)
    else:
        write_json(run.verdict(SID), minimal_verdict())
    return run


def test_an_accepted_instance_produces_all_eight_files(tmp_path):
    run = _run(tmp_path)
    emitted, findings = emit_run(run)
    assert findings == []
    assert emitted == [SID]
    task = run.task_dir(SID)
    for name in ("task.toml", "instruction.md", "seed.json", "golden.json", "provenance.md"):
        assert (task / name).is_file(), name
    for name in ("expected.json", "verify.py", "test.sh"):
        assert (task / "tests" / name).is_file(), name


def test_the_task_toml_is_parseable_and_names_the_target(tmp_path):
    run = _run(tmp_path)
    emit_run(run)
    payload = tomllib.loads((run.task_dir(SID) / "task.toml").read_text())
    assert payload["schema_version"] == "1.3"
    assert payload["task"]["name"].endswith(SID)
    assert payload["metadata"]["agent_type"] == "aap2"
    assert payload["environment"]["mcp_servers"][0]["url"] == "${BACKEND_MCP_URL}"
    assert payload["verifier"]["timeout_sec"] > 0
    assert payload["agent"]["timeout_sec"] > 0


def test_the_instruction_is_the_scenarios_user_intent(tmp_path):
    run = _run(tmp_path)
    emit_run(run)
    text = (run.task_dir(SID) / "instruction.md").read_text()
    assert text.strip() == minimal_scenarios()["scenarios"][0]["user_intent"]


def test_the_seed_is_copied_verbatim(tmp_path):
    run = _run(tmp_path)
    emit_run(run)
    assert (run.task_dir(SID) / "seed.json").read_text() == run.seed(SID).read_text()


def test_the_suite_directory_env_override_wins(monkeypatch, tmp_path):
    """RUBRICA_SUITE_DIR must actually redirect suite_template_dir(), the same
    way test_validate.py pins RUBRICA_SCHEMA_DIR against schema_dir() and
    test_skills_parse.py pins RUBRICA_SKILLS_DIR against skills_dir().

    Before this test, mutating the env-var literal in emit.py had zero test
    references catching it: the final Rubrica-rename review flagged that a
    misspelling of RUBRICA_SUITE_DIR during the rename would have left all
    1126 tests passing. CLAUDE.md discloses the gap rather than hiding it,
    but the fix is to close it, not just to disclose it.
    """
    monkeypatch.setenv("RUBRICA_SUITE_DIR", str(tmp_path))
    assert suite_template_dir() == tmp_path


def test_the_verifier_and_entrypoint_are_copied_verbatim(tmp_path):
    """The tested file and the executed file must not differ."""
    run = _run(tmp_path)
    emit_run(run)
    for name in ("verify.py", "test.sh"):
        assert (run.task_dir(SID) / "tests" / name).read_bytes() == (
            suite_template_dir() / name
        ).read_bytes()
    # shutil.copyfile does not preserve permission bits: without an explicit
    # chmod, the copy would land at the umask default and Harbor could never
    # execute the container's verifier entrypoint.
    mode = (run.task_dir(SID) / "tests" / "test.sh").stat().st_mode
    assert mode & 0o111, "test.sh must keep its executable bit"


def test_the_golden_holds_the_reference_answer_and_the_expected_calls(tmp_path):
    run = _run(tmp_path)
    emit_run(run)
    golden = json.loads((run.task_dir(SID) / "golden.json").read_text())
    assert golden["answer"] == minimal_expected()["answer_reference"]
    assert golden["tool_calls"] == [
        {"tool": "query_aap2", "args": {"action": "find_jobs", "controller": "prod0"}}
    ]


def test_the_provenance_records_the_discriminating_fact_and_the_adversarys_finding(tmp_path):
    run = _run(tmp_path)
    emit_run(run)
    text = (run.task_dir(SID) / "provenance.md").read_text()
    assert "exactly one prod0 job failed inside the window" in text
    assert "cell:cap-find-jobs/oc-success" in text
    assert "minimum_tool_calls_found" in text


def test_the_emitted_contract_validates_against_verify_pys_expectations(tmp_path):
    from rubrica.suite.verify import CONTRACT, compute_reward

    run = _run(tmp_path)
    emit_run(run)
    contract = json.loads((run.task_dir(SID) / "tests" / "expected.json").read_text())
    assert contract["contract"] == CONTRACT
    reward, _ = compute_reward(
        contract,
        [("query_aap2", {"action": "find_jobs", "controller": "prod0"})],
        "Job 90420.",
        True,
    )
    assert reward["reward"] == 1.0


def test_a_rejected_scenario_is_skipped_without_a_finding(tmp_path):
    """The coverage report already accounts for the cell it lost."""
    scenarios = minimal_scenarios()
    scenarios["scenarios"][0]["status"] = "rejected"
    scenarios["scenarios"][0]["rejected_reason"] = "ambiguous"
    run = _run(tmp_path, scenarios=scenarios, verdict=minimal_verdict(verdict="reject"))
    emitted, findings = emit_run(run)
    assert emitted == []
    assert findings == []
    assert not run.task_dir(SID).exists()


def test_an_active_scenario_with_a_reject_verdict_is_skipped_without_a_finding(tmp_path):
    """Status and verdict come from different stages and can legitimately disagree.

    The brief's own reject-path test sets status to "rejected" too, so it never
    exercises this line on its own: it is filtered out earlier by the status
    guard. This scenario stays active so the verdict check is what does the work.
    """
    run = _run(tmp_path, verdict=minimal_verdict(verdict="reject"))
    emitted, findings = emit_run(run)
    assert emitted == []
    assert findings == []
    assert not run.task_dir(SID).exists()


def test_an_instance_with_no_verdict_is_a_finding(tmp_path):
    """emit runs once, after challenge, so here the absence is real."""
    run = _run(tmp_path, verdict=None)
    emitted, findings = emit_run(run)
    assert emitted == []
    assert len(findings) == 1
    assert "has no verdict" in findings[0].message


def test_a_re_seed_verdict_is_a_finding(tmp_path):
    run = _run(tmp_path, verdict=minimal_verdict(verdict="re-seed"))
    emitted, findings = emit_run(run)
    assert emitted == []
    assert any("re-seed" in f.message for f in findings)


def test_a_partially_instantiated_instance_is_a_finding_not_a_crash(tmp_path):
    """instantiate can die mid-instance, leaving a directory with no seed/expected.

    Before this test existed, mutating the guard away turned this into an
    unhandled AttributeError from inside to_contract instead of a finding --
    exactly the "stage defect surfaces as a crash" failure mode the exit-code
    contract exists to prevent.
    """
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    write_json(run.manifest, minimal_manifest())
    write_json(run.world_model, minimal_world_model())
    write_json(run.scenarios, minimal_scenarios())
    run.instance_dir(SID).mkdir(parents=True, exist_ok=True)
    write_json(run.verdict(SID), minimal_verdict())

    emitted, findings = emit_run(run)

    assert emitted == []
    assert len(findings) == 1
    assert "is missing seed.json, expected.json" in findings[0].message
    assert not run.task_dir(SID).exists()


def test_a_present_but_truncated_expected_is_reported_as_unparseable_not_missing(tmp_path):
    """The repair for a truncated file is not the repair for an absent one.

    Reporting a truncated expected.json as "missing" sends the repair prompt to
    author the oracle again from scratch, discarding labels a human may already
    have read, instead of fixing the one thing that is wrong.
    """
    run = _run(tmp_path)
    run.expected(SID).write_text('{"schema_version": "0.1", "scenario_i', encoding="utf-8")

    emitted, findings = emit_run(run)

    assert emitted == []
    assert len(findings) == 1
    assert "has unparseable JSON in expected.json" in findings[0].message
    assert "missing" not in findings[0].message


def test_one_file_absent_and_the_other_unparseable_are_reported_separately(tmp_path):
    run = _run(tmp_path)
    run.seed(SID).unlink()
    run.expected(SID).write_text("{", encoding="utf-8")

    _, findings = emit_run(run)

    assert len(findings) == 1
    assert "is missing seed.json" in findings[0].message
    assert "has unparseable JSON in expected.json" in findings[0].message


def test_an_unbound_capability_becomes_a_finding_and_writes_no_package(tmp_path):
    world = minimal_world_model()
    del world["capabilities"][0]["binding"]
    run = _run(tmp_path, world=world)
    emitted, findings = emit_run(run)
    assert emitted == []
    assert findings
    assert all(f.layer == "emit" for f in findings)
    assert not run.task_dir(SID).exists(), "a package must not be half-written"


def test_a_missing_world_model_is_a_finding_not_a_crash(tmp_path):
    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    emitted, findings = emit_run(run)
    assert emitted == []
    assert len(findings) == 1


def test_a_missing_scenario_list_is_a_finding_not_an_empty_suite(tmp_path):
    """02-scenarios.json and 01-world-model.json are equally required inputs.

    Degrading to {"scenarios": []} exited 0 having written nothing, which told
    the orchestrator an empty suite was a successful emit.
    """
    run = _run(tmp_path)
    run.scenarios.unlink()
    emitted, findings = emit_run(run)
    assert emitted == []
    assert len(findings) == 1
    assert "02-scenarios.json" in findings[0].message


# -- pruning ---------------------------------------------------------------
def test_a_package_is_pruned_when_its_scenario_is_later_rejected(tmp_path):
    """06-suite/ must be a function of the current run state and nothing else.

    A complete, well-formed package for a scenario the adversary threw out as
    ambiguous would otherwise stay under 06-suite/, ship to Harbor, and be
    scored as a test somebody accepted. Nobody did.
    """
    run = _run(tmp_path)
    assert emit_run(run) == ([SID], [])
    assert run.task_dir(SID).is_dir()

    scenarios = minimal_scenarios()
    scenarios["scenarios"][0]["status"] = "rejected"
    scenarios["scenarios"][0]["rejected_reason"] = "ambiguous"
    write_json(run.scenarios, scenarios)

    emitted, findings = emit_run(run)

    assert emitted == []
    assert findings == []
    assert not run.task_dir(SID).exists(), "a rejected scenario's package must not ship"


def test_a_package_is_pruned_when_its_verdict_flips_to_re_seed(tmp_path):
    run = _run(tmp_path)
    assert emit_run(run) == ([SID], [])
    write_json(run.verdict(SID), minimal_verdict(verdict="re-seed"))

    emitted, findings = emit_run(run)

    assert emitted == []
    assert any("re-seed" in f.message for f in findings)
    assert not run.task_dir(SID).exists()


def test_a_package_is_pruned_when_its_scenario_disappears_from_the_list(tmp_path):
    run = _run(tmp_path)
    assert emit_run(run) == ([SID], [])
    write_json(run.scenarios, minimal_scenarios(scenarios=[]))

    emitted, _ = emit_run(run)

    assert emitted == []
    assert not run.task_dir(SID).exists()


def test_pruning_leaves_a_package_the_current_run_still_emits(tmp_path):
    """The guard against a prune that deletes the suite it just wrote."""
    run = _run(tmp_path)
    emit_run(run)
    emitted, findings = emit_run(run)
    assert (emitted, findings) == ([SID], [])
    assert (run.task_dir(SID) / "tests" / "expected.json").is_file()


def test_a_missing_input_does_not_prune_the_whole_suite(tmp_path):
    """A mistyped run directory must not destroy work in response to a typo.

    emit_run's early returns report a missing *input*, where the emitted set is
    empty for want of information rather than because nothing qualifies.
    """
    run = _run(tmp_path)
    assert emit_run(run) == ([SID], [])
    run.world_model.unlink()

    emitted, findings = emit_run(run)

    assert emitted == []
    assert len(findings) == 1
    assert run.task_dir(SID).is_dir(), "a missing world model must not delete the suite"


def test_re_emitting_replaces_a_stale_package(tmp_path):
    run = _run(tmp_path)
    emit_run(run)
    stale = run.task_dir(SID) / "stale.txt"
    stale.write_text("left over from an earlier emit")
    emit_run(run)
    assert not stale.exists()


def test_a_single_unbound_capability_does_not_cost_the_whole_suite(tmp_path):
    """A finding for one instance must not prevent a sibling from emitting."""
    world = minimal_world_model()
    world["capabilities"].append(
        {
            "id": "cap-unbound",
            "operation": "query_aap2.other",
            "params": [],
            "outcome_classes": [
                {"id": "oc-other", "kind": "success", "description": "the other outcome"}
            ],
            "claims": ["clm-001"],
            "confidence": "high",
        }
    )
    world["denominator"]["capability_cells"] = 3

    scenarios = minimal_scenarios()
    scenarios["scenarios"].append(
        {
            "id": "scn-000",
            "round": 1,
            "goal_id": "goal-triage",
            "actor_id": "act-sre",
            "title": "Exercise the unbound capability",
            "user_intent": "Trigger the other outcome.",
            "hop_depth": 1,
            "capability_refs": [{"capability_id": "cap-unbound", "outcome_class_id": "oc-other"}],
            "discriminating_fact": "the unbound capability never gets a binding",
            "status": "active",
            "provenance": {"hole_refs": [], "claim_ids": ["clm-001"], "round": 1},
        }
    )

    run = RunPaths(tmp_path)
    run.root.mkdir(parents=True, exist_ok=True)
    write_json(run.manifest, minimal_manifest())
    write_json(run.world_model, world)
    write_json(run.scenarios, scenarios)

    write_json(run.seed(SID), minimal_seed())
    write_json(run.expected(SID), minimal_expected())
    write_json(run.verdict(SID), minimal_verdict())

    write_json(run.seed("scn-000"), minimal_seed())
    write_json(
        run.expected("scn-000"),
        minimal_expected(
            scenario_id="scn-000",
            assertions=[
                {
                    "kind": "tool_called",
                    "target": "query_aap2.other",
                    "value": "at least once",
                    "rationale": "exercises the unbound capability",
                    "capability_id": "cap-unbound",
                }
            ],
            trajectory={
                "match": "subset",
                "operations": [{"capability_id": "cap-unbound", "args": {}}],
            },
        ),
    )
    write_json(run.verdict("scn-000"), minimal_verdict(scenario_id="scn-000"))

    emitted, findings = emit_run(run)

    assert emitted == [SID]
    assert run.task_dir(SID).is_dir()
    assert not run.task_dir("scn-000").exists()
    assert any("cap-unbound" in f.message for f in findings)


# -- the emit -> layer-1 seam ----------------------------------------------
def test_a_real_emitted_contract_passes_the_layer_1_gate_emit_is_judged_by(tmp_path):
    """The seam nothing tested: what emit writes against the schema that gates it.

    Every other suite-expected test validates tests/builders.py's hand-written
    transcription of the contract, not the file emit_run actually produces. If
    the two drift, `validate --stage emit` fails on every package -- and because
    emit is deterministic, the orchestrator's one repair attempt reproduces the
    failure byte-for-byte and hard-stops.
    """
    from rubrica.validate import validate_artifact

    run = _run(tmp_path)
    assert emit_run(run) == ([SID], [])
    contract = run.task_dir(SID) / "tests" / "expected.json"
    assert validate_artifact(contract, "suite-expected") == []


def test_the_suite_expected_schema_pins_the_weights_verify_py_actually_uses():
    """One fact, three encodings; this couples two of them.

    verify.DEFAULT_WEIGHTS is the constant emit.py imports. The schema pins the
    same two numbers again with `const`, and nothing in the code connects them,
    so re-tuning the weights in verify.py would silently make every package emit
    produces fail emit's own layer-1 gate. Both sources are read here at test
    time rather than transcribed, so the assertion cannot go stale.
    """
    import json as _json

    from rubrica.suite.verify import DEFAULT_WEIGHTS
    from rubrica.validate import ARTIFACT_SCHEMAS, schema_dir

    schema = _json.loads(
        (schema_dir() / ARTIFACT_SCHEMAS["suite-expected"]).read_text(encoding="utf-8")
    )
    pinned = schema["properties"]["weights"]["properties"]
    assert {name: spec["const"] for name, spec in pinned.items()} == DEFAULT_WEIGHTS


def test_emit_is_byte_stable_across_runs(tmp_path):
    """Two emits of one run directory must produce identical bytes."""
    run = _run(tmp_path)
    emit_run(run)
    first = {
        p.relative_to(run.suite_dir): p.read_bytes()
        for p in sorted(run.suite_dir.rglob("*"))
        if p.is_file()
    }
    emit_run(run)
    second = {
        p.relative_to(run.suite_dir): p.read_bytes()
        for p in sorted(run.suite_dir.rglob("*"))
        if p.is_file()
    }
    assert first == second
