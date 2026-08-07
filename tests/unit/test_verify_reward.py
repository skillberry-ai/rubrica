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


# -- the refuse path: every field compute_reward reads ----------------------
#
# The invariant: once _contract_problems returns [], compute_reward can neither
# raise nor score a field it did not read. Each case below broke one half of it.
# `transcript` is the run the reviewer used to demonstrate the inflation -- the
# agent called the wrong tool and answered "I could not determine which job
# failed", which a healthy contract scores 0.0.
WRONG_ANSWER_TRANSCRIPT = "\n".join(
    [
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "other_tool", "input": {"action": "nope"}}
                    ]
                },
            }
        ),
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": "I could not determine which job failed",
            }
        ),
    ]
)

CRASHED_TRANSCRIPT = json.dumps(
    {"type": "result", "subtype": "error", "is_error": True, "result": "Job 90420 failed."}
)


def _refuses(tmp_path, contract, transcript="", *, expect_in_error=None):
    """Run main() and assert it refused with a payload rather than scoring."""
    expected, logs, out = _write_run(tmp_path, contract, transcript)
    code = main(["--expected", str(expected), "--agent-logs", str(logs), "--out", str(out)])
    assert code == 2, "a bypassed authoring gate must refuse, not score"
    assert not (out / "reward.txt").exists(), "the platform must see a missing reward"
    error = json.loads((out / "reward-detail.json").read_text())["error"]
    if expect_in_error is not None:
        assert expect_in_error in error, error
    return error


def test_a_healthy_contract_scores_the_wrong_answer_run_zero(tmp_path):
    """The baseline the cases below are measured against."""
    expected, logs, out = _write_run(tmp_path, _contract(), WRONG_ANSWER_TRANSCRIPT)
    assert main(["--expected", str(expected), "--agent-logs", str(logs), "--out", str(out)]) == 0
    assert (out / "reward.txt").read_text() == "0.0"


def test_main_refuses_a_contract_with_no_assertions(tmp_path):
    """score_assertions([]) == 1.0 is an honest vacuous truth and a catastrophe here.

    A contract whose assertions were dropped scored 0.8 for the run above --
    a total failure turned into a high score, which is the one thing this
    file's docstring says must not happen.
    """
    contract = _contract()
    del contract["assertions"]
    _refuses(tmp_path, contract, WRONG_ANSWER_TRANSCRIPT, expect_in_error="assertions")


def test_main_refuses_a_contract_whose_assertions_are_empty(tmp_path):
    _refuses(
        tmp_path,
        _contract(assertions=[]),
        WRONG_ANSWER_TRANSCRIPT,
        expect_in_error="non-empty list",
    )


def test_main_refuses_a_contract_with_no_trajectory(tmp_path):
    """score_trajectory with no operations returns 1.0, for the same reason.

    The expected message is the type check specifically, not just the substring
    "trajectory": with the type check dropped, the match check catches an absent
    trajectory anyway, so a looser assertion would pass over the mutation.
    """
    contract = _contract()
    del contract["trajectory"]
    _refuses(
        tmp_path,
        contract,
        WRONG_ANSWER_TRANSCRIPT,
        expect_in_error="trajectory must be an object",
    )


@pytest.mark.parametrize("trajectory", ["subset", 3, ["find_jobs"]])
def test_main_refuses_a_trajectory_that_is_not_an_object(tmp_path, trajectory):
    """The input the type check exists for: truthy, so `or {}` cannot save it.

    A non-dict trajectory reached `.get("operations")` and raised AttributeError
    -- exit 1 with a traceback where the refuse path is exit 2 with a payload.
    """
    _refuses(
        tmp_path,
        _contract(trajectory=trajectory),
        expect_in_error="trajectory must be an object",
    )


def test_main_refuses_a_trajectory_with_no_operations_list(tmp_path):
    _refuses(
        tmp_path,
        _contract(trajectory={"match": "subset"}),
        WRONG_ANSWER_TRANSCRIPT,
        expect_in_error="trajectory.operations must be a list",
    )


def test_main_refuses_an_absent_trajectory_match(tmp_path):
    """Absent must refuse exactly as an explicit null already did.

    Falling through to "subset" meant a contract that declared no match mode at
    all scored under the loosest one, while `match: null` refused -- same field,
    same file, opposite behaviour.
    """
    contract = _contract(trajectory={"operations": [_op(action="find_jobs")]})
    _refuses(tmp_path, contract, expect_in_error="unknown trajectory.match None")


@pytest.mark.parametrize("status", ["weird", "OK", None, 1])
def test_main_refuses_an_unrecognized_completion_status(tmp_path, status):
    """A one-character typo in a two-value enum must not disable the crash gate.

    `completion.get("status", "ok") == "ok"` fails for "OK" just as it fails for
    "weird", so the gate never applied and a crashed agent scored 0.4 where a
    healthy contract scores 0.0.
    """
    contract = _contract(completion={"status": status, "nonempty_answer": True})
    _refuses(tmp_path, contract, CRASHED_TRANSCRIPT, expect_in_error="completion.status")


def test_a_healthy_contract_gates_a_crashed_run_to_zero(tmp_path):
    """The baseline for the status cases above."""
    expected, logs, out = _write_run(tmp_path, _contract(), CRASHED_TRANSCRIPT)
    assert main(["--expected", str(expected), "--agent-logs", str(logs), "--out", str(out)]) == 0
    assert (out / "reward.txt").read_text() == "0.0"
    assert json.loads((out / "reward-detail.json").read_text())["gate"] == 0.0


@pytest.mark.parametrize("nonempty", [0, None, "", "no"])
def test_main_refuses_a_non_boolean_nonempty_answer(tmp_path, nonempty):
    """A falsy non-boolean silently disables the empty-answer gate."""
    contract = _contract(completion={"status": "ok", "nonempty_answer": nonempty})
    _refuses(tmp_path, contract, expect_in_error="completion.nonempty_answer")


def test_main_refuses_a_non_dict_completion(tmp_path):
    _refuses(tmp_path, _contract(completion="ok"), expect_in_error="completion must be an object")


@pytest.mark.parametrize(
    "weights",
    [5, "heavy", [0.8, 0.2], {"assertions": "abc", "trajectory": 0.2}, {"assertions": None}],
)
def test_main_refuses_a_malformed_weights_instead_of_crashing_over_it(tmp_path, weights):
    """The old guard made the weights check a no-op for exactly its bad input.

    `if isinstance(weights, dict)` skipped a non-dict entirely and compute_reward
    then raised AttributeError; a string or None weight raised out of
    _contract_problems itself. Each exited 1 with a traceback and no payload,
    where the specified refuse path is exit 2 with an `error`.
    """
    _refuses(tmp_path, _contract(weights=weights), expect_in_error="weights")


def test_main_refuses_a_contract_that_is_not_an_object(tmp_path):
    _refuses(tmp_path, [1, 2, 3], expect_in_error="must be a JSON object")


@pytest.mark.parametrize("bad", [["a0"], [None], [1]])
def test_main_refuses_an_assertion_that_is_not_an_object(tmp_path, bad):
    _refuses(tmp_path, _contract(assertions=bad), expect_in_error="must be an object")


def test_main_refuses_a_trajectory_operation_that_is_not_an_object(tmp_path):
    contract = _contract(trajectory={"match": "subset", "operations": ["query_aap2"]})
    _refuses(tmp_path, contract, expect_in_error="operations[0] must be an object")


# -- the fields inside an assertion and an operation ------------------------
#
# The gate typed `assertions[i]` and `operations[i]` as objects and then never
# typed the fields it scores them against, so eight contracts cleared it and
# raised out of compute_reward -- exit 1 with a traceback, no reward.txt and no
# reward-detail.json, which is the failure mode the weights fix closed one field
# over. Each case below is one of those eight.


def _answer_assertion(kind, value):
    return {"id": "a0", "kind": kind, "value": value, "rationale": "the job id"}


_NO_ARGS = object()


def _tool_assertion(kind, args=_NO_ARGS, tool="query_aap2"):
    """A tool assertion; `args` left at its default omits the key entirely."""
    assertion = {"id": "a0", "kind": kind, "value": "at least once", "rationale": "the lookup"}
    assertion["tool"] = tool
    if args is not _NO_ARGS:
        assertion["args"] = args
    return assertion


@pytest.mark.parametrize("kind", ["answer_contains", "answer_excludes", "value_equals"])
@pytest.mark.parametrize("value", [5, ["x"], {"a": 1}, None])
def test_main_refuses_an_assertion_value_that_is_not_a_string(tmp_path, kind, value):
    """`value.lower()` raised AttributeError for every one of these."""
    contract = _contract(assertions=[_answer_assertion(kind, value)])
    _refuses(
        tmp_path,
        contract,
        WRONG_ANSWER_TRANSCRIPT,
        expect_in_error=f"assertions[0].value must be a string for kind {kind!r}",
    )


@pytest.mark.parametrize("kind", ["tool_called", "tool_not_called"])
@pytest.mark.parametrize("args", [5, ["a"], "action=find_jobs", None])
def test_main_refuses_a_tool_assertion_whose_args_are_not_an_object(tmp_path, kind, args):
    """`args.items()` raised AttributeError for the truthy non-dicts."""
    contract = _contract(assertions=[_tool_assertion(kind, args)])
    _refuses(
        tmp_path,
        contract,
        WRONG_ANSWER_TRANSCRIPT,
        expect_in_error=f"assertions[0].args must be an object for kind {kind!r}",
    )


@pytest.mark.parametrize("kind", ["tool_called", "tool_not_called"])
def test_main_refuses_a_tool_assertion_with_no_args_at_all(tmp_path, kind):
    """Not a crash but a silently looser match than the contract declared.

    call_matches reads `spec.get("args") or {}`, so an assertion with no args is
    satisfied by *any* call to the named tool. The schema requires the key, so a
    contract missing it is a bypassed authoring gate like the rest.
    """
    contract = _contract(assertions=[_tool_assertion(kind)])
    _refuses(
        tmp_path,
        contract,
        WRONG_ANSWER_TRANSCRIPT,
        expect_in_error=f"assertions[0].args must be an object for kind {kind!r}, got None",
    )


@pytest.mark.parametrize("args", [5, ["a"], "action=find_jobs", None])
def test_main_refuses_a_trajectory_operation_whose_args_are_not_an_object(tmp_path, args):
    contract = _contract(
        trajectory={"match": "subset", "operations": [{"tool": "query_aap2", "args": args}]}
    )
    _refuses(
        tmp_path,
        contract,
        WRONG_ANSWER_TRANSCRIPT,
        expect_in_error="trajectory.operations[0].args must be an object",
    )


def test_main_refuses_a_trajectory_operation_with_no_args_at_all(tmp_path):
    contract = _contract(trajectory={"match": "subset", "operations": [{"tool": "query_aap2"}]})
    _refuses(
        tmp_path,
        contract,
        WRONG_ANSWER_TRANSCRIPT,
        expect_in_error="trajectory.operations[0].args must be an object, got None",
    )


def test_a_well_typed_tool_assertion_still_scores(tmp_path):
    """The other half: the new checks must not refuse a healthy tool contract.

    Without this, deleting the kind split and refusing every assertion would
    look just as green as the fix.
    """
    contract = _contract(
        assertions=[_tool_assertion("tool_called", {"action": "find_jobs"})],
        trajectory={"match": "subset", "operations": [_op(action="find_jobs")]},
    )
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
    expected, logs, out = _write_run(tmp_path, contract, transcript)
    assert main(["--expected", str(expected), "--agent-logs", str(logs), "--out", str(out)]) == 0
    assert (out / "reward.txt").read_text() == "1.0"


def test_a_tool_assertion_with_an_unscored_non_string_value_still_scores(tmp_path):
    """The gate types the fields a kind is *scored against*, and only those.

    _assertion_satisfied never reads `value` for a tool kind, so typing it there
    would refuse a contract over a field that cannot affect the reward -- the same
    over-reach as typing `rationale` or `target`. This pins the kind split: widen
    the value check past _ANSWER_KINDS and this test refuses instead of scoring.
    """
    assertion = _tool_assertion("tool_not_called", {"action": "delete_job"})
    assertion["value"] = 5
    contract = _contract(assertions=[assertion])
    expected, logs, out = _write_run(tmp_path, contract, WRONG_ANSWER_TRANSCRIPT)
    assert main(["--expected", str(expected), "--agent-logs", str(logs), "--out", str(out)]) == 0
    assert (out / "reward.txt").read_text() == "0.8", "the exclusion holds; the trajectory does not"


@pytest.mark.parametrize(
    "literal",
    [
        '{"assertions": NaN, "trajectory": NaN}',
        '{"assertions": Infinity, "trajectory": -Infinity}',
        '{"assertions": Infinity, "trajectory": 0.2}',
    ],
)
def test_main_refuses_non_finite_weights(tmp_path, literal):
    """json.loads accepts these bare tokens, and NaN clears the sum check.

    `abs(nan - 1.0) > 1e-9` is False, so a NaN pair passed the one check that
    exists to keep the reward inside [0, 1] and then scored every run as
    `reward: nan`. The literals are parsed rather than built with float() so the
    test exercises the same path the container does: a JSON file on disk.
    """
    contract = _contract(weights=json.loads(literal))
    _refuses(
        tmp_path,
        contract,
        WRONG_ANSWER_TRANSCRIPT,
        expect_in_error="must be a finite number",
    )


def test_a_refusal_reports_every_problem_not_just_the_first(tmp_path):
    """The container gets one shot; a partial diagnosis wastes it."""
    contract = _contract(assertions=[], weights=5)
    contract["trajectory"] = {"operations": []}
    error = _refuses(tmp_path, contract)
    assert "assertions" in error
    assert "trajectory.match" in error
    assert "weights" in error


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
