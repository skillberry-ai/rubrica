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
import sys
from pathlib import Path

CONTRACT = "testgen/v1"

# The answer carries the discriminating fact, so it carries most of the weight.
# A trajectory is largely obvious once the task is understood, and weighting it
# heavily would let a well-shaped-but-wrong run out-score a correct one.
DEFAULT_WEIGHTS = {"assertions": 0.8, "trajectory": 0.2}


def parse_transcript(text):
    """Read a stream-json transcript into (calls, answer, ok).

    Each call is (tool_name, args). Malformed lines are skipped so a truncated
    transcript still scores rather than crashing -- a crash would be reported as
    a broken agent when the truth is a broken log.
    """
    calls, answer, ok = [], "", False
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    args = block.get("input")
                    calls.append((block.get("name", ""), args if isinstance(args, dict) else {}))
        elif event.get("type") == "result":
            # Last result event wins: exactly one is written per run, but a
            # partial transcript plus a terminal error event can yield two.
            answer = event.get("result", "") or ""
            ok = event.get("subtype") == "success" and not event.get("is_error", False)
    return calls, answer, ok


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
    if kind in ("tool_called", "tool_not_called"):
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
    """-> (score, detail) for one of the three declared match modes."""
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
        "extra_calls": max(0, len(calls) - len(operations)),
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

    contract = json.loads(Path(args.expected).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    declared = contract.get("contract")
    if declared != CONTRACT:
        # Refuse rather than write a misleading 0. A contract this verifier
        # cannot read is a bypassed authoring gate, not a bad agent run, and
        # reporting it as 0 would invert that conclusion. No reward.txt is
        # written, so the platform sees a missing reward instead of a real one.
        message = f"expected contract {CONTRACT!r}, got {declared!r}"
        (out / "reward-detail.json").write_text(json.dumps({"error": message}, indent=2))
        print(f"verify.py: {message}", file=sys.stderr)
        return 2

    calls, answer, ok = parse_transcript(_read_logs(args.agent_logs))
    reward, detail = compute_reward(contract, calls, answer, ok)

    (out / "reward.json").write_text(json.dumps(reward, indent=2, sort_keys=True))
    (out / "reward.txt").write_text(str(reward["reward"]))
    (out / "reward-detail.json").write_text(
        json.dumps(detail, indent=2, sort_keys=True, default=str)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
