"""Trajectory scoring, the reward computation, and the verifier entrypoint."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from testgen.suite.verify import CONTRACT, compute_reward, main, score_trajectory


def _calls(*pairs):
    return list(pairs)


def _op(tool="query_aap2", **args):
    return {"tool": tool, "args": args}


# -- score_trajectory -------------------------------------------------------


def test_subset_scores_the_matched_fraction():
    calls = _calls(("query_aap2", {"action": "find_jobs"}))
    trajectory = {
        "match": "subset",
        "operations": [_op(action="find_jobs"), _op(action="get_job_log")],
    }
    score, detail = score_trajectory(calls, trajectory)
    assert score == 0.5
    assert detail["unmatched"] == [_op(action="get_job_log")]


def test_subset_ignores_extra_calls():
    calls = _calls(("query_aap2", {"action": "find_jobs"}), ("query_aap2", {"action": "whatever"}))
    score, _ = score_trajectory(calls, {"match": "subset", "operations": [_op(action="find_jobs")]})
    assert score == 1.0


def test_subset_does_not_let_one_call_satisfy_two_operations():
    """Otherwise a single call scores a two-hop trajectory, erasing hop depth."""
    calls = _calls(("query_aap2", {"action": "find_jobs"}))
    trajectory = {
        "match": "subset",
        "operations": [_op(action="find_jobs"), _op(action="find_jobs")],
    }
    score, _ = score_trajectory(calls, trajectory)
    assert score == 0.5


def test_subset_is_order_independent():
    calls = _calls(
        ("query_aap2", {"action": "get_job_log"}), ("query_aap2", {"action": "find_jobs"})
    )
    trajectory = {
        "match": "subset",
        "operations": [_op(action="find_jobs"), _op(action="get_job_log")],
    }
    score, _ = score_trajectory(calls, trajectory)
    assert score == 1.0


def test_exact_set_rejects_an_extra_call():
    calls = _calls(("query_aap2", {"action": "find_jobs"}), ("query_aap2", {"action": "extra"}))
    score, _ = score_trajectory(
        calls, {"match": "exact-set", "operations": [_op(action="find_jobs")]}
    )
    assert score == 0.0


def test_exact_set_accepts_the_same_calls_in_any_order():
    calls = _calls(
        ("query_aap2", {"action": "get_job_log"}), ("query_aap2", {"action": "find_jobs"})
    )
    trajectory = {
        "match": "exact-set",
        "operations": [_op(action="find_jobs"), _op(action="get_job_log")],
    }
    score, _ = score_trajectory(calls, trajectory)
    assert score == 1.0


def test_exact_sequence_rejects_the_wrong_order():
    calls = _calls(
        ("query_aap2", {"action": "get_job_log"}), ("query_aap2", {"action": "find_jobs"})
    )
    trajectory = {
        "match": "exact-sequence",
        "operations": [_op(action="find_jobs"), _op(action="get_job_log")],
    }
    score, _ = score_trajectory(calls, trajectory)
    assert score == 0.0


def test_exact_sequence_accepts_the_right_order():
    calls = _calls(
        ("query_aap2", {"action": "find_jobs"}), ("query_aap2", {"action": "get_job_log"})
    )
    trajectory = {
        "match": "exact-sequence",
        "operations": [_op(action="find_jobs"), _op(action="get_job_log")],
    }
    score, _ = score_trajectory(calls, trajectory)
    assert score == 1.0


def test_no_expected_operations_scores_one():
    score, _ = score_trajectory([], {"match": "subset", "operations": []})
    assert score == 1.0


def test_extra_calls_counts_calls_that_matched_nothing():
    """len(calls) - len(operations) undercounts: a call that matched nothing
    is extra even when the total call count doesn't exceed the operation
    count."""
    calls = _calls(("query_aap2", {"action": "find_jobs"}), ("query_aap2", {"action": "find_jobs"}))
    trajectory = {
        "match": "subset",
        "operations": [_op(action="find_jobs"), _op(action="get_job_log")],
    }
    score, detail = score_trajectory(calls, trajectory)
    assert score == 0.5
    assert detail["extra_calls"] == 1


# -- compute_reward ---------------------------------------------------------


def _contract(**over):
    payload = {
        "contract": CONTRACT,
        "scenario_id": "scn-001",
        "completion": {"status": "ok", "nonempty_answer": True},
        "assertions": [
            {"id": "a0", "kind": "answer_contains", "value": "90420", "rationale": "the job id"}
        ],
        "trajectory": {"match": "subset", "operations": [_op(action="find_jobs")]},
        "weights": {"assertions": 0.8, "trajectory": 0.2},
    }
    payload.update(over)
    return payload


def test_a_fully_correct_run_scores_one():
    calls = _calls(("query_aap2", {"action": "find_jobs"}))
    reward, _ = compute_reward(_contract(), calls, "Job 90420 failed.", True)
    assert reward["reward"] == 1.0
    assert reward["completion"] == 1.0


def test_the_weights_are_applied():
    """Answer right, trajectory absent -> the assertions weight alone."""
    reward, _ = compute_reward(_contract(), [], "Job 90420 failed.", True)
    assert reward["reward"] == pytest.approx(0.8)


def test_a_failed_completion_gates_the_reward_to_zero():
    calls = _calls(("query_aap2", {"action": "find_jobs"}))
    reward, detail = compute_reward(_contract(), calls, "Job 90420 failed.", False)
    assert reward["reward"] == 0.0
    assert detail["gate"] == 0.0
    assert reward["assertions"] == 1.0, "the components stay visible under the gate"


def test_an_empty_answer_gates_the_reward_to_zero():
    reward, _ = compute_reward(_contract(), [], "   ", True)
    assert reward["reward"] == 0.0


def test_an_expected_error_completion_is_not_gated_by_a_failed_run():
    contract = _contract(completion={"status": "error", "nonempty_answer": False})
    reward, _ = compute_reward(contract, [], "", False)
    assert reward["completion"] == 1.0


def test_missing_weights_fall_back_to_the_documented_defaults():
    contract = _contract()
    del contract["weights"]
    reward, detail = compute_reward(contract, [], "Job 90420 failed.", True)
    assert detail["weights"] == {"assertions": 0.8, "trajectory": 0.2}
    assert reward["reward"] == pytest.approx(0.8)


# -- main -------------------------------------------------------------------


def _write_run(tmp_path, contract, transcript):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "expected.json").write_text(json.dumps(contract))
    logs = tmp_path / "logs" / "agent"
    logs.mkdir(parents=True)
    (logs / "transcript.jsonl").write_text(transcript)
    return tmp_path / "tests" / "expected.json", logs, tmp_path / "out"


def test_main_writes_the_three_reward_files(tmp_path):
    transcript = "\n".join(
        [
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "query_aap2",
                                "input": {"action": "find_jobs"},
                            }
                        ]
                    },
                }
            ),
            json.dumps(
                {"type": "result", "subtype": "success", "is_error": False, "result": "Job 90420."}
            ),
        ]
    )
    expected, logs, out = _write_run(tmp_path, _contract(), transcript)
    code = main(["--expected", str(expected), "--agent-logs", str(logs), "--out", str(out)])
    assert code == 0
    assert json.loads((out / "reward.json").read_text())["reward"] == 1.0
    assert (out / "reward.txt").read_text() == "1.0"
    assert "weights" in json.loads((out / "reward-detail.json").read_text())


def test_main_refuses_an_unreadable_contract_rather_than_scoring_zero(tmp_path):
    """A zero would report a bypassed authoring gate as a bad agent run."""
    expected, logs, out = _write_run(tmp_path, _contract(contract="bench/v2"), "")
    code = main(["--expected", str(expected), "--agent-logs", str(logs), "--out", str(out)])
    assert code == 2
    assert not (out / "reward.txt").exists()
    assert "bench/v2" in json.loads((out / "reward-detail.json").read_text())["error"]


def test_main_refuses_an_unrecognized_trajectory_match_mode(tmp_path):
    """A one-character typo must not silently fall through to subset, the most
    lenient mode -- that's the exact asymmetry an unknown assertion kind
    (which fails closed) does not have."""
    contract = _contract(trajectory={"match": "exact_set", "operations": [_op(action="find_jobs")]})
    expected, logs, out = _write_run(tmp_path, contract, "")
    code = main(["--expected", str(expected), "--agent-logs", str(logs), "--out", str(out)])
    assert code == 2
    assert not (out / "reward.txt").exists()
    assert "exact_set" in json.loads((out / "reward-detail.json").read_text())["error"]


def test_main_refuses_weights_that_do_not_sum_to_one(tmp_path):
    """A weights bug must not silently produce a reward outside [0, 1] that
    looks like a normal, if unusually high, score."""
    contract = _contract(weights={"assertions": 0.9, "trajectory": 0.9})
    expected, logs, out = _write_run(tmp_path, contract, "")
    code = main(["--expected", str(expected), "--agent-logs", str(logs), "--out", str(out)])
    assert code == 2
    assert not (out / "reward.txt").exists()
    error = json.loads((out / "reward-detail.json").read_text())["error"]
    assert "weights" in error
    assert "1.8" in error


def test_main_reads_both_jsonl_and_txt_logs(tmp_path):
    expected, logs, out = _write_run(tmp_path, _contract(), "")
    (logs / "extra.txt").write_text(
        json.dumps(
            {"type": "result", "subtype": "success", "is_error": False, "result": "Job 90420."}
        )
    )
    assert main(["--expected", str(expected), "--agent-logs", str(logs), "--out", str(out)]) == 0
    assert json.loads((out / "reward.json").read_text())["assertions"] == 1.0


# -- the container constraint ----------------------------------------------


def test_verify_py_never_imports_testgen():
    """It executes in a bare ubi9 container where the package does not exist."""
    source = Path("src/testgen/suite/verify.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders = [
        node
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Import)
            and any(alias.name.startswith("testgen") for alias in node.names)
        )
        or (isinstance(node, ast.ImportFrom) and (node.module or "").startswith("testgen"))
    ]
    assert offenders == []


def test_test_sh_invokes_the_verifier_and_propagates_its_exit_code():
    script = Path("src/testgen/suite/test.sh").read_text(encoding="utf-8")
    assert "/tests/verify.py" in script
    assert "/logs/verifier" in script
    assert "exit $?" in script
