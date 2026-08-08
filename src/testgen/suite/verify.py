#!/usr/bin/env python3
"""Generic verifier for a testgen-emitted task (contract "testgen/v1").

Stdlib-only: this runs inside the task container, a bare ubi9 image with no
third-party packages and no network. It must never import testgen.

This file is the SOLE implementation of testgen's scoring semantics, and it is
hand-written rather than generated per task on purpose. A generated verifier is
untrustworthy code sitting directly in the scoring path -- the one place a bug
silently inflates every score. Keeping it fixed is also what forces the
assertion vocabulary closed: no skill can invent a kind, because adding one is a
human edit to this file.

emit copies this file verbatim into every package. The tracked original at
src/testgen/suite/verify.py is what the tests exercise, so the tested file and
the executed file cannot differ.
"""

import argparse
import json
import math
import sys
from pathlib import Path

CONTRACT = "testgen/v1"

# The answer carries the discriminating fact, so it carries most of the weight.
# A trajectory is largely obvious once the task is understood, and weighting it
# heavily would let a well-shaped-but-wrong run out-score a correct one.
DEFAULT_WEIGHTS = {"assertions": 0.8, "trajectory": 0.2}


def parse_transcript(text):
    """Read a stream-json transcript into (calls, answer, ok, notes).

    Each call is (tool_name, args). Malformed lines are skipped so a truncated
    transcript still scores rather than crashing -- a crash would be reported as
    a broken agent when the truth is a broken log.

    `notes` is what keeps those concessions honest. A skipped line or a coerced
    field changes the score, so it is carried out to reward-detail.json rather
    than applied silently. Distinct notes are recorded once each, so a wholly
    corrupt log cannot flood the detail file.

    A `result` that is not a string scores as **no answer**, deliberately not as
    `str(value)`: str({"text": "90420"}) contains "90420", so coercion would
    satisfy an answer_contains assertion against a dict the agent never uttered.
    compute_reward's docstring rules that out -- tolerance at the scoring seam is
    score inflation. No answer means the nonempty_answer gate fires, which is the
    honest reading of a log this verifier cannot understand.
    """
    calls, answer, ok = [], "", False
    notes, skipped = [], 0

    def note(message):
        if message not in notes:
            notes.append(message)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith(("{", "[")):
            # Not shaped like JSON at all -- ordinary log noise, not counted:
            # a corrupt event is recorded below, but noise between events is not.
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            skipped += 1
            continue
        if not isinstance(event, dict):
            skipped += 1
            continue
        if event.get("type") == "assistant":
            message = event.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    args = block.get("input")
                    calls.append((block.get("name", ""), args if isinstance(args, dict) else {}))
        elif event.get("type") == "result":
            # Last result event wins: exactly one is written per run, but a
            # partial transcript plus a terminal error event can yield two.
            value = event.get("result", "")
            if value is None:
                value = ""
            elif not isinstance(value, str):
                note(
                    f"a result event carried a {type(value).__name__} rather than a string; "
                    "scored as no answer"
                )
                value = ""
            answer = value
            ok = event.get("subtype") == "success" and not event.get("is_error", False)
    if skipped:
        notes.append(f"skipped {skipped} line(s) that were not parseable JSON objects")
    return calls, answer, ok, notes


def _as_number(value):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def values_equal(want, got):
    """Compare two JSON scalars as tool arguments.

    Numbers compare numerically and a numeric string equals a number: an agent
    that serialises job_id as "90420" still chose the right job, so penalising
    it would measure serialisation style rather than tool use. Booleans are
    never equal to numbers, because failed_only=true and failed_only=1 are
    different intents.
    """
    if isinstance(want, bool) or isinstance(got, bool):
        return isinstance(want, bool) and isinstance(got, bool) and want == got
    want_number, got_number = _as_number(want), _as_number(got)
    if want_number is not None and got_number is not None:
        return want_number == got_number
    return want == got


def call_matches(spec, call):
    """Subset match: tool names must be equal and every listed arg must agree.

    Arguments the spec omits are ignored, so an incidental max_results or
    controller does not break an otherwise correct call.
    """
    name, args = call
    if spec.get("tool", "") != name:
        return False
    for key, want in (spec.get("args") or {}).items():
        if key not in args or not values_equal(want, args[key]):
            return False
    return True


def _contains(answer, value):
    """Whether `value` occurs in `answer`, case-insensitively.

    An empty value never counts as found: an empty answer_contains would be
    vacuously satisfied by anything, and that is exactly the silent score
    inflation this file exists to prevent.
    """
    if not value:
        return False
    return value.lower() in answer.lower()


def _delimited(answer, value):
    """Whether `value` occurs in `answer` not flanked by an alphanumeric.

    This is what separates value_equals from answer_contains: an answer of
    "job 13 failed" must not satisfy an asserted count of "3".
    """
    haystack, needle = answer.lower(), value.lower()
    if not needle:
        return False
    start = 0
    while True:
        index = haystack.find(needle, start)
        if index < 0:
            return False
        before = haystack[index - 1] if index > 0 else ""
        after_index = index + len(needle)
        after = haystack[after_index] if after_index < len(haystack) else ""
        if not before.isalnum() and not after.isalnum():
            return True
        start = index + 1


# The closed assertion vocabulary, split by the field each kind scores against:
# an answer kind reads `value`, a tool kind reads `tool` and `args`. Stated once
# here because _contract_problems types those fields per kind, and a second copy
# of the vocabulary is how the gate and the scorer drift apart.
_ANSWER_KINDS = ("answer_contains", "answer_excludes", "value_equals")
_TOOL_KINDS = ("tool_called", "tool_not_called")


def _assertion_satisfied(answer, calls, assertion):
    """-> True, False, or None when the kind is not in the closed vocabulary."""
    kind = assertion.get("kind")
    value = assertion.get("value", "")
    if kind == "answer_contains":
        return _contains(answer, value)
    if kind == "answer_excludes":
        # An empty value is malformed, not a real exclusion: an assertion that
        # excludes nothing must fail rather than score, the same way an
        # unrecognised kind does -- not_contains("") would otherwise be
        # vacuously True and hand out a point for asserting nothing.
        if not value:
            return False
        return not _contains(answer, value)
    if kind == "value_equals":
        return _delimited(answer, value)
    if kind in _TOOL_KINDS:
        hit = any(call_matches(assertion, call) for call in calls)
        return hit if kind == "tool_called" else not hit
    return None


def score_assertions(answer, calls, assertions):
    """-> (score, detail) over one denominator of every assertion.

    An exclusion satisfied by absence scores a point rather than avoiding a
    penalty. That makes a fabrication trap a positively-scored item, and lets a
    pure-absence scenario consist entirely of exclusions and still score.

    An unrecognised kind counts as failed, never as satisfied: the vocabulary is
    closed, so one can only arrive here through a bypassed authoring gate, and
    awarding a point would hide that.
    """
    satisfied_ids, failed, unknown = [], [], []
    for assertion in assertions:
        result = _assertion_satisfied(answer, calls, assertion)
        if result is None:
            entry = dict(assertion)
            entry["error"] = f"unknown assertion kind {assertion.get('kind')!r}"
            unknown.append(entry)
            failed.append(entry)
        elif result:
            satisfied_ids.append(assertion.get("id"))
        else:
            failed.append(dict(assertion))

    total = len(assertions)
    detail = {
        "total": total,
        "satisfied": satisfied_ids,
        "failed": failed,
        "unknown_kinds": unknown,
    }
    if total == 0:
        return 1.0, detail
    return (total - len(failed)) / total, detail


def _match_unordered(operations, calls):
    """-> the set of expected-operation indices satisfied, greedily.

    Each actual call is consumed by at most one expected operation. Without
    that, a single call would satisfy a two-operation trajectory and hop depth
    -- the whole difficulty signal -- would stop being measured.
    """
    used, matched = set(), set()
    for i, operation in enumerate(operations):
        for j, call in enumerate(calls):
            if j in used or not call_matches(operation, call):
                continue
            used.add(j)
            matched.add(i)
            break
    return matched


def score_trajectory(calls, trajectory):
    """-> (score, detail) for one of the three declared match modes.

    The "subset" fallback below is unreachable from main(): _contract_problems
    requires trajectory.match to be present and one of the three modes, so a
    contract that reaches here through the entrypoint has already declared one.
    It stays because this is a pure function called directly by its own tests,
    and because falling back is the right behaviour for a caller that has
    already been told the contract is well-formed.
    """
    operations = trajectory.get("operations") or []
    match = trajectory.get("match", "subset")

    if match == "exact-sequence":
        pairwise = len(operations) == len(calls) and all(
            call_matches(operation, call) for operation, call in zip(operations, calls, strict=True)
        )
        matched = set(range(len(operations))) if pairwise else set()
        score = 1.0 if pairwise else 0.0
    else:
        matched = _match_unordered(operations, calls)
        complete = len(matched) == len(operations)
        if match == "exact-set":
            score = 1.0 if complete and len(calls) == len(operations) else 0.0
        else:
            score = 1.0 if not operations else len(matched) / len(operations)

    detail = {
        "match": match,
        "actual": [{"tool": name, "args": args} for name, args in calls],
        "unmatched": [op for i, op in enumerate(operations) if i not in matched],
        # Calls that matched nothing are extra even under a partial match:
        # len(calls) - len(operations) undercounts whenever some calls matched
        # and others didn't, e.g. two calls against two operations where only
        # one call matches -- that's one extra call, not zero.
        "extra_calls": max(0, len(calls) - len(matched)),
    }
    return score, detail


def compute_reward(contract, calls, answer, ok):
    """-> (reward, detail).

    `reward` holds only scalars. Everything a human needs to understand the
    number goes in `detail`, written alongside as reward-detail.json: a bare
    0.625 with no way to see which check failed costs real debugging time.

    The completion gate multiplies rather than contributes. A run that crashed
    or answered nothing has not earned partial credit for calling the right
    tools, but the components stay visible in `reward` so the gate is
    distinguishable from a genuinely wrong answer.

    Two of the defaults this function falls back to are reachable through
    main(), and both are safe by construction rather than by tolerance: an
    absent or null `completion` scores as {"status": "ok", "nonempty_answer":
    true}, the *strictest* setting of both gates, and absent weights fall back
    to DEFAULT_WEIGHTS, this file's own constant rather than anything a contract
    could have got wrong. The other two -- the empty assertion list and the
    empty trajectory -- are unreachable and must stay so: _contract_problems
    refuses a contract that omits or mistypes either, because both score a full
    mark for a component nobody declared. Read none of the four as tolerance at
    the scoring seam. Tolerance there is score inflation.
    """
    completion = contract.get("completion") or {}
    gate = 1.0
    if completion.get("status", "ok") == "ok" and not ok:
        gate = 0.0
    if completion.get("nonempty_answer", True) and not answer.strip():
        gate = 0.0

    assertion_score, assertion_detail = score_assertions(
        answer, calls, contract.get("assertions") or []
    )
    trajectory_score, trajectory_detail = score_trajectory(calls, contract.get("trajectory") or {})

    weights = contract.get("weights") or {}
    weight_assertions = float(weights.get("assertions", DEFAULT_WEIGHTS["assertions"]))
    weight_trajectory = float(weights.get("trajectory", DEFAULT_WEIGHTS["trajectory"]))
    combined = weight_assertions * assertion_score + weight_trajectory * trajectory_score

    reward = {
        "reward": round(gate * combined, 6),
        "completion": gate,
        "assertions": round(assertion_score, 6),
        "trajectory": round(trajectory_score, 6),
    }
    detail = {
        "scenario_id": contract.get("scenario_id"),
        "gate": gate,
        "weights": {"assertions": weight_assertions, "trajectory": weight_trajectory},
        "assertions": assertion_detail,
        "trajectory": trajectory_detail,
    }
    return reward, detail


_VALID_MATCH_MODES = ("subset", "exact-set", "exact-sequence")
_VALID_COMPLETION_STATUSES = ("ok", "error")


def _is_number(value):
    """Whether `value` is a real, finite number.

    Booleans are not: True is not a weight. Neither are NaN and +/-Infinity,
    which json.loads accepts as bare tokens: NaN clears the sum check below --
    `abs(nan - 1.0) > 1e-9` is False -- and then scores every run `reward: nan`,
    a reward outside [0, 1], which is the one thing that check exists to prevent.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _contract_problems(contract):
    """-> a list of contract-shape problems, empty if the contract is well-formed.

    **The invariant, with its one stated limit: once this returns [], no
    *contract* field can make compute_reward raise, and no component it scores
    comes from a contract field this gate left untyped. The single thing outside
    it is the transcript, which is not a contract field at all -- recorded at the
    end of this docstring rather than assumed away.** Every field compute_reward
    reads off the contract is type-checked here, and every closed vocabulary it
    compares against is checked for membership. Both halves matter, and each was
    violated:

    - A field compute_reward *scored without reading* inflated the reward. A
      contract with no `assertions` scored 1.0 for assertions, because
      score_assertions([]) == 1.0 is an honest vacuous truth for a pure
      function and a catastrophe at this seam: a run that called the wrong tool
      and answered "I could not determine which job failed" scored 0.8 instead
      of 0.0. Same for a contract with no `trajectory`. So `assertions` must be
      a non-empty list and `trajectory.operations` must be a list -- the
      vacuous-truth functions are left alone, because they are right about
      their own inputs.
    - A field it *could not read* crashed it. A non-dict `weights` slipped
      through the old `if isinstance(weights, dict)` guard -- which made the
      weights check a no-op for exactly the input it guarded against -- and
      compute_reward then raised AttributeError. A traceback exits 1 with no
      payload, where the specified refuse path is exit 2 with an `error`. The
      same hole sat one field over, and outlasted the weights fix: this loop
      checked that each `assertions[i]` and each `trajectory.operations[i]` *was
      an object* and never typed the fields inside it, so `value: 5` reached
      `value.lower()` and `args: ["a"]` reached `args.items()`. Eight such
      contracts cleared this gate and exited 1 with a traceback, no reward.txt
      and no reward-detail.json. Hence the per-kind `value` and `args` checks:
      the fields a kind is scored against are typed for that kind, which also
      refuses an absent `args` on a tool assertion or an operation -- absent args
      match any call to the named tool, a looser match than the contract
      declared, and the schema requires the key.
    - A field it read as a *default* inflated the reward again, one field further
      over. `tool` cannot raise, because it is only ever compared for equality
      against a call name; on an operation and on a `tool_called` a missing or
      mistyped one also fails closed, scoring 0 for the item. On a
      `tool_not_called` it did not: `call_matches` compares
      `spec.get("tool", "")`, no call is ever named "", so an exclusion naming no
      tool matched nothing and was therefore *satisfied* -- a free point for
      asserting nothing, measured at assertions=1.0 on a run that called the
      wrong tool. That is the same vacuous truth _assertion_satisfied already
      refuses for an empty `answer_excludes` value. So `tool` must be a non-empty
      string for both _TOOL_KINDS, and for every operation too: the schema
      requires it there as well, and leaving one of the pair untyped is how the
      two drift apart.

    Closed vocabularies fail closed here, uniformly. An unrecognised assertion
    kind already failed closed inside score_assertions (counted as failed).
    These did not:

    - `trajectory.match`, absent, fell through to "subset", the most lenient
      mode -- so a contract that declared no mode at all scored under the
      loosest one, while an explicit `null` correctly refused. Same field, same
      file, opposite behaviour. The key is now required.
    - `completion.status`, unrecognised, silently disabled the crash gate: the
      test was `status == "ok"`, so "OK" or "weird" or null made the equality
      fail and a crashed agent scored as a completed one. A one-character typo
      in a two-value enum must not do that.
    - Weights that don't sum to 1.0 produce a reward outside [0, 1] that looks
      like a normal, if unusually high, score. NaN reaches the same place through
      the sum check itself -- see _is_number.

    All of these are bypassed-authoring-gate problems, not agent problems, so
    main() refuses on them exactly like a CONTRACT mismatch. Scoring them would
    invert that conclusion, which is the one thing this file's docstring says
    must not happen.

    The one limit named at the top, so that this gate's silence is not read as a
    guarantee it does not give:

    - The transcript. compute_reward's other three arguments come from
      parse_transcript, not from the contract, and a `result` event carrying a
      non-string `result` is a broken log rather than a bypassed authoring gate.
      Choosing between dropping such an answer and str()-ing it is a scoring
      decision, not a shape check, so it is ruled on in parse_transcript's own
      docstring, not here.
    """
    problems = []

    if not isinstance(contract, dict):
        return [f"contract must be a JSON object, got {type(contract).__name__}"]

    declared = contract.get("contract")
    if declared != CONTRACT:
        problems.append(f"expected contract {CONTRACT!r}, got {declared!r}")

    completion = contract.get("completion")
    if completion is not None and not isinstance(completion, dict):
        problems.append(f"completion must be an object, got {completion!r}")
    elif isinstance(completion, dict):
        status = completion.get("status")
        if status not in _VALID_COMPLETION_STATUSES:
            problems.append(
                f"unknown completion.status {status!r}, expected one of "
                f"{_VALID_COMPLETION_STATUSES}"
            )
        nonempty = completion.get("nonempty_answer", True)
        if not isinstance(nonempty, bool):
            problems.append(
                f"completion.nonempty_answer must be a boolean, got {nonempty!r}; a falsy "
                "non-boolean silently disables the empty-answer gate"
            )

    assertions = contract.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        problems.append(
            f"assertions must be a non-empty list, got {assertions!r}; an empty or absent list "
            "scores a full mark for asserting nothing"
        )
    else:
        for i, assertion in enumerate(assertions):
            if not isinstance(assertion, dict):
                problems.append(f"assertions[{i}] must be an object, got {assertion!r}")
                continue
            kind = assertion.get("kind")
            value = assertion.get("value", "")
            args = assertion.get("args")
            tool = assertion.get("tool")
            if kind in _ANSWER_KINDS and not isinstance(value, str):
                problems.append(
                    f"assertions[{i}].value must be a string for kind {kind!r}, got {value!r}"
                )
            if kind in _TOOL_KINDS and not isinstance(args, dict):
                problems.append(
                    f"assertions[{i}].args must be an object for kind {kind!r}, got {args!r}"
                )
            if kind in _TOOL_KINDS and not (isinstance(tool, str) and tool):
                problems.append(
                    f"assertions[{i}].tool must be a non-empty string for kind {kind!r}, got "
                    f"{tool!r}"
                )

    trajectory = contract.get("trajectory")
    if not isinstance(trajectory, dict):
        problems.append(
            f"trajectory must be an object, got {trajectory!r}; an absent trajectory scores a "
            "full mark for a trajectory nobody declared"
        )
    else:
        match = trajectory.get("match")
        if match not in _VALID_MATCH_MODES:
            problems.append(
                f"unknown trajectory.match {match!r}, expected one of {_VALID_MATCH_MODES}"
            )
        operations = trajectory.get("operations")
        if not isinstance(operations, list):
            problems.append(
                f"trajectory.operations must be a list, got {operations!r}; an absent list "
                "scores a full mark for a trajectory nobody declared"
            )
        else:
            for i, operation in enumerate(operations):
                if not isinstance(operation, dict):
                    problems.append(
                        f"trajectory.operations[{i}] must be an object, got {operation!r}"
                    )
                    continue
                op_tool, op_args = operation.get("tool"), operation.get("args")
                if not isinstance(op_args, dict):
                    problems.append(
                        f"trajectory.operations[{i}].args must be an object, got {op_args!r}"
                    )
                if not (isinstance(op_tool, str) and op_tool):
                    problems.append(
                        f"trajectory.operations[{i}].tool must be a non-empty string, got "
                        f"{op_tool!r}"
                    )

    weights = contract.get("weights")
    if weights is not None and not isinstance(weights, dict):
        problems.append(f"weights must be an object, got {weights!r}")
    else:
        # A missing weights object is not a problem: compute_reward falls back
        # to DEFAULT_WEIGHTS, which is this file's own constant rather than
        # anything the contract could have got wrong.
        weights = weights or {}
        pairs = [
            ("assertions", weights.get("assertions", DEFAULT_WEIGHTS["assertions"])),
            ("trajectory", weights.get("trajectory", DEFAULT_WEIGHTS["trajectory"])),
        ]
        # Type-checked before float() rather than inside a try: float("abc")
        # raises ValueError and float(None) raises TypeError, and either one
        # escaping this function is a traceback in place of the refuse payload.
        bad = [(name, value) for name, value in pairs if not _is_number(value)]
        for name, value in bad:
            problems.append(f"weights.{name} must be a finite number, got {value!r}")
        if not bad:
            total = float(pairs[0][1]) + float(pairs[1][1])
            if abs(total - 1.0) > 1e-9:
                problems.append(
                    f"weights must sum to 1.0, got assertions={pairs[0][1]!r} + "
                    f"trajectory={pairs[1][1]!r} = {total!r}"
                )

    return problems


def read_contract(path):
    """-> (contract, problems). A file that could not be read is itself a problem.

    main() used to call json.loads directly, so a truncated expected.json raised
    out of the verifier before _contract_problems ran: the refusal path that
    exists to keep an authoring failure from being scored as a zero never
    engaged, and the platform saw a crashed verifier rather than a stated
    refusal. A gate cannot defend a file it did not manage to parse.
    """
    try:
        text = Path(path).read_text()
    except OSError as exc:
        return None, [f"contract at {path} could not be read: {exc}"]
    try:
        contract = json.loads(text)
    except ValueError as exc:
        return None, [f"contract at {path} is not parseable JSON: {exc}"]
    if not isinstance(contract, dict):
        return None, [
            f"contract at {path} is a {type(contract).__name__}, not an object; every field "
            "this verifier reads would be absent"
        ]
    return contract, []


def _read_logs(agent_logs):
    """Concatenate every transcript file in the agent log directory.

    Globs *.jsonl and *.txt, so --out must not point at --agent-logs: a second
    run would otherwise read its own reward.txt back as transcript input.
    """
    parts = []
    for pattern in ("*.jsonl", "*.txt"):
        for path in sorted(Path(agent_logs).glob(pattern)):
            parts.append(path.read_text(errors="replace"))
    return "\n".join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", default="/tests/expected.json")
    parser.add_argument("--agent-logs", default="/logs/agent")
    parser.add_argument("--out", default="/logs/verifier")
    args = parser.parse_args(argv)

    # out is created before the contract is read: a refusal has to be able to
    # write reward-detail.json, and an absent contract is one of the refusals.
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    contract, problems = read_contract(args.expected)
    if not problems:
        problems = _contract_problems(contract)
    if problems:
        # Refuse rather than write a misleading 0 -- or, for a weights
        # problem, an inflated reward that looks like a normal score. A
        # contract this verifier cannot read is a bypassed authoring gate, not
        # a bad agent run, and scoring it would invert that conclusion. No
        # reward.txt is written, so the platform sees a missing reward
        # instead of a real one.
        message = "; ".join(problems)
        (out / "reward-detail.json").write_text(json.dumps({"error": message}, indent=2))
        print(f"verify.py: {message}", file=sys.stderr)
        return 2

    calls, answer, ok, notes = parse_transcript(_read_logs(args.agent_logs))
    reward, detail = compute_reward(contract, calls, answer, ok)
    if notes:
        detail["transcript_notes"] = notes

    (out / "reward.json").write_text(json.dumps(reward, indent=2, sort_keys=True))
    (out / "reward.txt").write_text(str(reward["reward"]))
    (out / "reward-detail.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True, default=str)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
