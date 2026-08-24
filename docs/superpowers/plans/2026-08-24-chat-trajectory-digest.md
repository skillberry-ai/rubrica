# Chat-Trajectory Digest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give a chat-message trajectory a behavioural digest, so 200 tau2 trajectory files stop reaching triage as skeleton-only rows.

**Architecture:** One shape predicate (`digest.is_message_list`) becomes the single home for "this payload is a conversation". `digest_for_payload`'s trace branch splits into two producers — the existing dict one, unchanged, and a new message-list one — with the `heuristics_fired` tail assembled once. `intake.classify` gains one more route to `"trace"`. Nothing else changes: no new artifact kind, no schema change, no widening of the four extractor key tuples, and `survey.classify_payload` is deliberately left alone.

**Tech Stack:** Python 3.13, `uv`, pytest, ruff (`line-length = 100`, `select = ["E","F","I","UP","B","SIM"]`).

**Spec:** `docs/superpowers/specs/2026-08-24-chat-trajectory-digest-design.md`

## Global Constraints

- **Every commit signed and DCO'd: `git commit -S -s`.** Both flags. If signing fails, stop and report it; never fall back to unsigned.
- Attribution trailer is `Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>`. **Never** `Co-Authored-By` or `Made-with`.
- The three gates are `make test`, `make check`, and `uv run rubrica check-skills` exiting 0.
- Comment density here is high and deliberate: comments explain *why*, usually citing a measurement. Match it; do not strip existing comments.
- **Do not touch** `_REQUEST_KEYS`, `_STATUS_KEYS`, `_COUNT_KEYS`, `_NAME_KEYS`, the `kind` enum in `src/rubrica/schema/catalogue-0.1.json`, `survey.classify_payload`, `survey.explode`, `EXPLODE_MIN_ELEMENTS`, or `EXPLODE_MIN_COMMON_KEYS`. Each has been proposed and is wrong; spec §2 and §3 say why.
- **Do not edit anything under `docs/superpowers/`.** It is recorded history. Only `docs/README.md` may cite that tree.
- Per CLAUDE.md, measure every new text-level predicate in **both** directions before committing it: blank the prose it checks (in a `/tmp` copy under `RUBRICA_SKILLS_DIR`) and confirm red, then reword it meaning-preservingly and confirm green.
- Never write a test count into any document.

**Corpus paths used by Task 4 and Task 7** (present on this machine, not in the repo):
- `/home/bnayahu/work/kaegis/tau2-bench/src/tau2`
- `/home/bnayahu/work/kaegis/tau2-bench/data/tau2/trajectories`

---

### Task 1: The shape predicate

**Files:**
- Modify: `src/rubrica/digest.py` (add `is_message_list` after `_lookup_scopes`, around line 100)
- Test: `tests/unit/test_digest.py`

**Interfaces:**
- Consumes: `_SKELETON_MAX_CHILDREN` (`digest.py:55`), already this module's breadth budget.
- Produces: `digest.is_message_list(payload: Any) -> bool` — public, imported by `intake.py` in Task 3 and used by `digest_for_payload` in Task 2.

**One refinement on spec §4, applied here with the reason:** the spec says "every element carries `role`"; this requires that `role` be a **`str`**. Two reasons — a non-string role makes the distinct-role set unhashable and would raise, and a role is a string in every shape this targets. Measured on tau2: all 5,182 roles are strings.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_digest.py`:

```python
def test_a_chat_trajectory_is_recognised_as_a_message_list():
    """The shape tau2-bench's 200 trajectories actually have.

    Measured there: every file's key intersection is exactly {'role'}, because
    895 of 5,182 messages are {role, tool_calls} and carry no `content`. So no
    key-set rule reaches them -- a string `role` on every element is the only
    invariant they have, and that is what this predicate keys on.
    """
    payload = [
        {"role": "system", "content": "You are an airline agent."},
        {"role": "user", "content": "I need to change my flight."},
        {"role": "assistant", "tool_calls": [{"function": {"name": "get_reservation_details"}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": '{"reservation_id": "EHGLP3"}'},
    ]
    assert digest.is_message_list(payload) is True


def test_a_list_of_dicts_without_role_is_not_a_message_list():
    """The predicate's discriminating clause. Without it, any homogeneous list
    of objects would be digested as a conversation, and `element_counts` would
    report role tallies for records that have no roles."""
    assert digest.is_message_list([{"a": 1, "b": 2}, {"a": 3, "b": 4}]) is False


def test_a_single_message_is_not_a_conversation():
    """Two, not one: a one-element list carrying `role` is a shape common in
    configuration, and digesting it as a dialogue reports a conversation that
    does not exist."""
    assert digest.is_message_list([{"role": "user", "content": "hi"}]) is False


def test_a_message_list_needs_content_or_tool_calls_somewhere():
    """Role tags alone are not behaviour. A list of bare {role: ...} records
    carries nothing `request_text` or `names` could ever read, so it is not
    what this path exists for."""
    assert digest.is_message_list([{"role": "user"}, {"role": "assistant"}]) is False


def test_a_non_string_role_is_not_a_message_list():
    """Guards the distinct-role set below from an unhashable value, and states
    the shape rule: a role is a string."""
    assert digest.is_message_list([{"role": {"n": 1}, "content": "x"}] * 2) is False


def test_a_payload_with_more_distinct_roles_than_the_breadth_cap_is_not_a_conversation():
    """The cap sits in the predicate rather than in a truncation flag, so
    `element_counts` is bounded by construction. Measured on tau2: 4 roles."""
    many = [{"role": f"r{i}", "content": "x"} for i in range(digest._SKELETON_MAX_CHILDREN + 1)]
    assert digest.is_message_list(many) is False


def test_a_list_of_scalars_is_not_a_message_list():
    """The same payload `test_a_non_dict_trace_payload_falls_back_to_the_generic_skeleton`
    pins: it must keep reaching the skeleton, which requires failing here."""
    assert digest.is_message_list(["not", "a", "dict"]) is False
    assert digest.is_message_list({"role": "user"}) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_digest.py -k message_list -v`
Expected: FAIL, `AttributeError: module 'rubrica.digest' has no attribute 'is_message_list'`

- [ ] **Step 3: Implement the predicate**

Insert into `src/rubrica/digest.py`, immediately after `_lookup_scopes` (before `_first_scalar`):

```python
def is_message_list(payload: Any) -> bool:
    """Whether this payload is a conversation: a list of role-tagged messages.

    One home for the shape rule, because `intake.classify` and
    `digest_for_payload` must agree on it: a file classified `trace` for being a
    message list and then digested by the dict producer would fall through to a
    skeleton, which is exactly the defect issue #4 reported.

    Measured on tau2-bench's 200 chat trajectories, which is what this exists
    for: every file's key intersection is exactly {'role'} -- 895 of 5,182
    messages are {role, tool_calls} and carry no `content` -- so no key-set rule
    reaches them, and `EXPLODE_MIN_COMMON_KEYS` relaxed to 2 admits 0 of the
    200. A string `role` on every element is the only invariant they have.

    Two elements, not one: a one-element list carrying `role` is a shape common
    in configuration, and digesting it as a dialogue reports a conversation that
    does not exist. The distinct-role cap bounds `element_counts` by
    construction rather than by a truncation flag -- `_SKELETON_MAX_CHILDREN` is
    already this module's breadth budget, and a payload with more distinct roles
    than that is not a dialogue. Measured on tau2: 4 roles.

    Precision, measured: 200 of 200 tau2 trajectories, 0 of the 15 JSON fixtures
    under tests/fixtures/, 0 of the tau2-bench/src/tau2 tree.
    """
    if not isinstance(payload, list) or len(payload) < 2:
        return False
    # A *string* role, not merely a present one: the distinct-role set below
    # would raise on an unhashable value, and a role is a string in every shape
    # this targets.
    if not all(
        isinstance(message, dict) and isinstance(message.get("role"), str)
        for message in payload
    ):
        return False
    if not any("content" in message or "tool_calls" in message for message in payload):
        return False
    return len({message["role"] for message in payload}) <= _SKELETON_MAX_CHILDREN
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_digest.py -k message_list -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Verify the predicate against the real corpus in both directions**

Run:

```bash
uv run python - <<'EOF'
import json, glob
from rubrica.digest import is_message_list
traj = sorted(glob.glob('/home/bnayahu/work/kaegis/tau2-bench/data/tau2/trajectories/**/*.json', recursive=True))
src = sorted(glob.glob('/home/bnayahu/work/kaegis/tau2-bench/src/tau2/**/*.json', recursive=True))
fix = sorted(glob.glob('tests/fixtures/**/*.json', recursive=True))
def hits(paths):
    n = 0
    for p in paths:
        try:
            n += bool(is_message_list(json.load(open(p))))
        except Exception:
            pass
    return n, len(paths)
print("trajectories:", hits(traj))   # expect (200, 200)
print("tau2 src:    ", hits(src))    # expect (0, N)
print("fixtures:    ", hits(fix))    # expect (0, 15)
EOF
```

Expected: `(200, 200)`, `(0, ...)`, `(0, 15)`. If the trajectory count is not 200, stop — the predicate does not match the shape the design was measured on.

- [ ] **Step 6: Run the gates and commit**

```bash
make test && make check
git add src/rubrica/digest.py tests/unit/test_digest.py
git commit -S -s -m "feat: Add the message-list shape rule, one home for two callers

A conversation is a list of role-tagged messages, and both intake.classify and
digest_for_payload need the same answer: a file classified \`trace\` for being a
message list and then digested by the dict producer falls through to a skeleton,
which is the defect issue #4 reported.

Keyed on a string \`role\` on every element because that is the only invariant
tau2-bench's 200 trajectories have -- every file's key intersection is exactly
{'role'}, since 895 of 5,182 messages are {role, tool_calls} and carry no
\`content\`. Measured precision: 200 of 200 trajectories, 0 of the 15 JSON
fixtures, 0 of tau2-bench/src/tau2.

The distinct-role cap reuses _SKELETON_MAX_CHILDREN rather than adding a number
nobody has calibrated, and it sits in the predicate rather than in a truncation
flag so element_counts is bounded by construction.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 2: The message-list digest producer

**Files:**
- Modify: `src/rubrica/digest.py:292-334` (`digest_for_payload`'s trace branch)
- Test: `tests/unit/test_digest.py`

**Interfaces:**
- Consumes: `is_message_list` (Task 1); existing `_collect_names`, `_has_error_key`, `_SKELETON_DEPTH`, `TRACE_HEURISTICS`, `_first_scalar`, `_lookup_scopes`, `_has_error_marker`.
- Produces: `_trace_digest_from_dict(payload: dict, *, body_chars: int) -> tuple[dict, list[str]]` and `_trace_digest_from_messages(payload: list, *, body_chars: int) -> tuple[dict, list[str]]`. Both return `(result, fired)`; neither sets `heuristics_fired` — `digest_for_payload` assembles it once so `TRACE_HEURISTICS` ordering keeps a single spelling.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_digest.py`:

```python
# One trajectory, shaped exactly like tau2-bench's: a system policy stating the
# instant in prose, a user request, an assistant tool call, and a tool result.
_TRAJECTORY = [
    {"role": "system", "content": "# Airline Agent Policy\n\nThe current time is 2024-05-15 15:00:00 EST."},
    {"role": "user", "content": "I want to cancel reservation EHGLP3."},
    {
        "role": "assistant",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_reservation_details", "arguments": "{}"},
            }
        ],
    },
    {"role": "tool", "tool_call_id": "call_1", "content": '{"reservation_id": "EHGLP3"}'},
    {"role": "assistant", "tool_calls": [{"function": {"name": "cancel_reservation"}}]},
]


def test_a_chat_trajectory_digests_to_the_facts_a_triage_decision_needs():
    """Issue #4: 200 such files reached triage as skeleton-only rows carrying no
    tool names, no request text and no counts. Measured across that corpus, these
    three fields yield 14 distinct tool names and 68 distinct toolset signatures
    over 200 files -- the discrimination a near-duplicate ruling reads."""
    result = digest.digest_for_payload(_TRAJECTORY, "trace", body_chars=2000)
    assert result["element_counts"] == {
        "messages": 5,
        "role_system": 1,
        "role_user": 1,
        "role_assistant": 2,
        "role_tool": 1,
    }
    assert result["names"] == ["cancel_reservation", "get_reservation_details"]
    assert result["heuristics_fired"] == ["element_counts", "request_text", "names"]


def test_request_text_comes_from_the_user_turn_not_the_system_prompt():
    """The system prompt is corpus-wide boilerplate: measured on tau2, 118
    distinct first-user-message prefixes against 1 distinct system prefix. A
    fallback to the first message of any role would return the same bytes for
    nearly every candidate and destroy the discrimination this field exists for.
    """
    result = digest.digest_for_payload(_TRAJECTORY, "trace", body_chars=2000)
    assert result["request_text"] == "I want to cancel reservation EHGLP3."
    assert "Airline Agent Policy" not in result["request_text"]


def test_a_trajectory_with_no_user_turn_fires_no_request_text():
    """Honesty over coverage: the field is absent and `heuristics_fired` says so,
    which is what lets triage decline `digest_insufficient` and name what it
    needed."""
    result = digest.digest_for_payload(
        [
            {"role": "system", "content": "policy"},
            {"role": "assistant", "content": "done"},
        ],
        "trace",
        body_chars=2000,
    )
    assert "request_text" not in result
    assert "request_text" not in result["heuristics_fired"]


def test_names_reaches_a_tool_call_function_name():
    """The one field that discriminates on this corpus. `_collect_names` already
    reaches `tool_calls[].function.name` within its depth budget, so this asserts
    reuse rather than a second extractor."""
    result = digest.digest_for_payload(_TRAJECTORY, "trace", body_chars=2000)
    assert "get_reservation_details" in result["names"]


def test_a_chat_trajectory_fires_neither_status_nor_error_markers():
    """Measured on tau2: no key in _STATUS_KEYS appears in any of the 5,182
    messages, and the structural `_has_error_key` fires on 0 of the 200 files.
    Both absences are facts about the digest that `heuristics_fired` records --
    a value-substring rule that fired on 12 of 200 was rejected as the very
    inspection this module narrowed out."""
    result = digest.digest_for_payload(_TRAJECTORY, "trace", body_chars=2000)
    assert "status" not in result
    assert "error_markers" not in result
    assert "status" not in result["heuristics_fired"]
    assert "error_markers" not in result["heuristics_fired"]


def test_a_message_list_trace_digest_carries_no_skeleton_key():
    """Same rule as the dict producer: a trace digest has no skeleton, so it must
    not grow a truncation flag about one."""
    result = digest.digest_for_payload(_TRAJECTORY, "trace", body_chars=2000)
    assert "skeleton" not in result
    assert "skeleton_nodes_truncated" not in result


def test_request_text_is_truncated_to_body_chars():
    """The same budget the dict producer honours, for the same reason: a digest
    that ignores it is how one candidate's row exceeds a slice."""
    payload = [
        {"role": "system", "content": "policy"},
        {"role": "user", "content": "x" * 500},
    ]
    result = digest.digest_for_payload(payload, "trace", body_chars=40)
    assert len(result["request_text"]) == 40


def test_a_message_list_classified_other_still_digests_to_a_skeleton():
    """The producer is reached on `kind == "trace"` only. A message list that some
    other path classified `other` keeps the skeleton it had, so this change cannot
    alter a candidate the classifier did not move."""
    result = digest.digest_for_payload(_TRAJECTORY, "other", body_chars=2000)
    assert "skeleton" in result
    assert "heuristics_fired" not in result
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_digest.py -k "trajectory or request_text or message_list_trace" -v`
Expected: FAIL — `KeyError: 'element_counts'`, because the message list currently reaches the skeleton branch.

- [ ] **Step 3: Split the trace branch into two producers**

In `src/rubrica/digest.py`, replace the trace branch of `digest_for_payload` (currently lines 295-334, from `if kind == "trace" and isinstance(payload, dict):` through `return result`) with two module-level functions placed immediately *before* `digest_for_payload`, plus a new dispatch inside it.

First, move the existing body verbatim into a producer — the only edits are the signature, the removal of the final two lines, and the added `return`:

```python
def _trace_digest_from_dict(payload: dict, *, body_chars: int) -> tuple[dict, list[str]]:
    """The trace facts a dict-shaped capture carries. Unchanged behaviour; split
    out only so the message-list producer beside it can share
    `digest_for_payload`'s single assembly of `heuristics_fired`."""
    fired: list[str] = []
    result: dict[str, Any] = {}

    status = _first_scalar(payload, _STATUS_KEYS)
    if status is not None:
        result["status"] = status
        fired.append("status")

    # Same envelope widening as _first_scalar, and first scope wins for the
    # same reason: MLflow's span list is `data.spans`, not `spans`.
    counts: dict[str, int] = {}
    for scope in _lookup_scopes(payload):
        for key in _COUNT_KEYS:
            if key not in counts and isinstance(scope.get(key), list):
                counts[key] = len(scope[key])
    if counts:
        result["element_counts"] = counts
        fired.append("element_counts")

    request = _first_scalar(payload, _REQUEST_KEYS)
    if isinstance(request, str) and request.strip():
        # Kept raw and truncated rather than parsed: those captures
        # store request_preview as a *truncated* JSON string, so json.loads
        # fails on it while the question text sits in the first 80 chars.
        result["request_text"] = request[:body_chars]
        fired.append("request_text")

    names: set[str] = set()
    _collect_names(payload, _SKELETON_DEPTH, names)
    if names:
        result["names"] = sorted(names)
        fired.append("names")

    if _has_error_marker(payload, status, _SKELETON_DEPTH):
        result["error_markers"] = True
        fired.append("error_markers")

    return result, fired


def _trace_digest_from_messages(payload: list, *, body_chars: int) -> tuple[dict, list[str]]:
    """The trace facts a conversation carries, for the shape `is_message_list`
    admits.

    Reads `content` directly rather than through `_REQUEST_KEYS`: widening that
    tuple would change every existing dict-shaped trace digest and oblige
    re-recording the committed fixtures, for a key only this shape uses.

    Two heuristics never fire here, and both absences are measured rather than
    assumed. `status`: no key in `_STATUS_KEYS` appears in any of tau2's 5,182
    messages, because a chat trajectory has no terminal status field.
    `error_markers`: the structural `_has_error_key` fires on 0 of those 200
    files. A rule matching a tool result whose `content` begins with an error
    sentinel would have fired on 12 of 200 -- rejected, because that is the value
    inspection `_has_error_marker` was deliberately narrowed to exclude, and
    `heuristics_fired` reporting nothing found is the honest record.
    """
    fired: list[str] = []
    result: dict[str, Any] = {}

    # Always fires: a conversation always has messages. The role tally rides
    # along because it is the cheapest statement of an episode's shape -- how
    # many turns, how many tool results -- and the predicate's distinct-role cap
    # is what bounds it.
    counts: dict[str, int] = {"messages": len(payload)}
    for message in payload:
        key = f"role_{message['role']}"
        counts[key] = counts.get(key, 0) + 1
    result["element_counts"] = counts
    fired.append("element_counts")

    # The first *user* turn, with no fallback to the first message of any role:
    # the system prompt is corpus-wide boilerplate, measured at 118 distinct
    # user prefixes against 1 distinct system prefix across tau2's 200 files, so
    # a fallback would return the same bytes for nearly every candidate.
    for message in payload:
        content = message.get("content")
        if message["role"] == "user" and isinstance(content, str) and content.strip():
            result["request_text"] = content[:body_chars]
            fired.append("request_text")
            break

    # Per message rather than over the list, so the depth budget is spent inside
    # a message: that is what reaches `tool_calls[].function.name`, which is the
    # field carrying 14 distinct tool names and 68 toolset signatures here.
    names: set[str] = set()
    for message in payload:
        _collect_names(message, _SKELETON_DEPTH, names)
    if names:
        result["names"] = sorted(names)
        fired.append("names")

    if any(_has_error_key(message, _SKELETON_DEPTH) for message in payload):
        result["error_markers"] = True
        fired.append("error_markers")

    return result, fired
```

Then replace the branch inside `digest_for_payload` with:

```python
    if kind == "trace":
        produced: tuple[dict, list[str]] | None = None
        if isinstance(payload, dict):
            produced = _trace_digest_from_dict(payload, body_chars=body_chars)
        elif is_message_list(payload):
            produced = _trace_digest_from_messages(payload, body_chars=body_chars)
        if produced is not None:
            result, fired = produced
            result["heuristics_fired"] = [h for h in TRACE_HEURISTICS if h in fired]
            return result
        # Neither shape: fall through to the skeleton. survey.explode can hand a
        # trace-kind element that is not a dict, and a list of scalars is not a
        # conversation -- both are one candidate with a structural digest.
```

- [ ] **Step 4: Run the whole digest module to verify the new tests pass and none regressed**

Run: `uv run pytest tests/unit/test_digest.py -v`
Expected: PASS. In particular these three must still pass untouched — if any needs editing, the split is wrong:
- `test_a_non_dict_trace_payload_falls_back_to_the_generic_skeleton`
- `test_a_trace_digest_reaches_every_parsec_selection`
- `test_every_named_heuristic_is_reachable`

- [ ] **Step 5: Prove existing dict-shaped trace digests are byte-identical**

Run:

```bash
uv run python - <<'EOF'
import json, glob
from rubrica import digest
from rubrica.artifacts import canonical_bytes
for p in sorted(glob.glob('tests/fixtures/**/*.json', recursive=True)):
    payload = json.load(open(p))
    for kind in ("trace", "other"):
        print(kind, p, len(canonical_bytes(digest.digest_for_payload(payload, kind, body_chars=2000))))
EOF
```

Expected: run this once before Step 3 (stash the change) and once after; the two outputs must be identical. Any difference means a key tuple or the dict producer was altered.

- [ ] **Step 6: Run the gates and commit**

```bash
make test && make check
git add src/rubrica/digest.py tests/unit/test_digest.py
git commit -S -s -m "feat: Digest a chat trajectory's behaviour instead of its shape

digest_for_payload's trace branch guarded on isinstance(payload, dict), so a
message list could never reach it however it was classified -- the one-line
cause of issue #4's 200 skeleton-only rows. The branch now dispatches to one of
two producers and assembles heuristics_fired once, so TRACE_HEURISTICS keeps a
single spelling.

The message-list producer fires element_counts, request_text and names, and
measurably not status or error_markers: no key in _STATUS_KEYS appears in any of
tau2's 5,182 messages, and the structural _has_error_key fires on 0 of the 200
files. A rule matching a tool result whose content begins with an error sentinel
would have fired on 12 of 200 -- rejected as the value inspection
_has_error_marker was narrowed to exclude.

request_text reads \`content\` directly rather than through _REQUEST_KEYS, so
every existing dict-shaped trace digest stays byte-identical and no committed
fixture needs re-recording. It takes the first user turn with no fallback to the
first message of any role: measured 118 distinct user prefixes against 1 system
prefix, so a fallback would return the same bytes for nearly every candidate.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 3: Classification

**Files:**
- Modify: `src/rubrica/intake.py:75-101` (`classify`) and its import block (line 21-26)
- Test: `tests/unit/test_intake.py`

**Interfaces:**
- Consumes: `digest.is_message_list` (Task 1). `digest.py` imports only stdlib, so importing it from `intake.py` creates no cycle.
- Produces: no new names. `classify` gains one route to the existing `"trace"` return.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_intake.py`:

```python
def test_classify_recognises_a_chat_trajectory_as_a_trace(tmp_path):
    """Issue #4: a list of {role, content} messages carries neither `spans` nor
    `trace_id`, so it classified `other` and got a skeleton digest. It is a
    capture of what the target did, which is what `trace` means."""
    payload = [
        {"role": "system", "content": "You are an airline agent."},
        {"role": "user", "content": "Cancel EHGLP3."},
        {"role": "assistant", "tool_calls": [{"function": {"name": "cancel_reservation"}}]},
    ]
    assert classify(_write(tmp_path, "37_1_abc.json", payload)) == "trace"


def test_classify_leaves_a_list_of_non_message_records_alone(tmp_path):
    """The widening is scoped to conversations. A homogeneous list of records
    without roles is not one, and calling it a trace would hand the trace
    producer a payload with no field it can read."""
    payload = [{"id": 1, "value": "a"}, {"id": 2, "value": "b"}, {"id": 3, "value": "c"}]
    assert classify(_write(tmp_path, "records.json", payload)) == "other"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_intake.py -k "chat_trajectory or non_message_records" -v`
Expected: FAIL on the first — `assert 'other' == 'trace'`. The second passes already; it is the guard that the widening stays scoped.

- [ ] **Step 3: Add the classification route**

Add to `src/rubrica/intake.py`'s import block, in alphabetical position among the `rubrica` imports:

```python
from rubrica.digest import is_message_list
```

Then, in `classify`, replace lines 94-101 with:

```python
    if (
        isinstance(payload, list)
        and payload
        and isinstance(payload[0], dict)
        and ("spans" in payload[0] or "trace_id" in payload[0])
    ):
        return "trace"
    # A conversation is a capture of what the target did, which is what `trace`
    # means -- and issue #4 measured the cost of it classifying `other`: 200 tau2
    # trajectory files reached triage as skeleton-only rows. Widening the
    # existing kind rather than adding one, because no code branches on
    # `kind == "trace"` outside this function and survey.classify_payload.
    if is_message_list(payload):
        return "trace"
    return "other"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_intake.py -v`
Expected: PASS, including the existing `test_classify_recognises_a_trace_by_content`.

- [ ] **Step 5: Run the gates and commit**

```bash
make test && make check && uv run rubrica check-skills
git add src/rubrica/intake.py tests/unit/test_intake.py
git commit -S -s -m "feat: Classify a chat trajectory as the trace it is

A list of role-tagged messages carries neither \`spans\` nor \`trace_id\`, so it
classified \`other\` -- and issue #4 measured what that cost: 200 tau2 trajectory
files reached triage as skeleton-only rows.

Widening the existing kind rather than adding one. No code branches on
\`kind == \"trace\"\` outside classify and survey.classify_payload, so a new kind
would touch the enum, both schemas, artifacts.md and slices._signature in
exchange for a distinction no consumer acts on -- while widening \`trace\` leaves
heuristics_fired, the field rb-triage-rule calls the one that matters most,
carried by the kind that already carries it.

survey.classify_payload is deliberately untouched: its only caller passes
elements from explode, and _homogeneous requires every element to be a dict, so
it is never handed a list and a branch there would be unreachable.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 4: Confirm or falsify the design on the real corpus

**Files:** none modified. This task is the measurement spec §10 says confirms the design.

**Interfaces:**
- Consumes: Tasks 1-3 complete.
- Produces: the numbers quoted in Task 6's `limitations.md` edit. If they disagree with the spec, **stop and report** rather than adjusting the documentation to match.

- [ ] **Step 1: Survey the corpus at defaults**

```bash
rm -rf /tmp/probe4
uv run rubrica survey \
  --corpus /home/bnayahu/work/kaegis/tau2-bench/src/tau2 \
  --corpus /home/bnayahu/work/kaegis/tau2-bench/data/tau2/trajectories \
  --runs-dir /tmp/probe4 --target-name tau2 --target-interface python \
  --objective breadth
RUN=$(ls -d /tmp/probe4/run-* | head -1); echo "$RUN"
uv run rubrica validate --run "$RUN" --stage survey; echo "validate exit: $?"
```

Expected: survey succeeds, `validate` exits 0.

- [ ] **Step 2: Assert every number the design claims**

```bash
uv run python - "$RUN" <<'EOF'
import collections, json, sys
from pathlib import Path
from rubrica import slices as S
from rubrica.artifacts import canonical_bytes

cat = json.load(open(Path(sys.argv[1]) / "00-catalogue.json"))
cands = cat["candidates"]
kinds = collections.Counter(c["kind"] for c in cands)
traj = [c for c in cands if c["kind"] == "trace"]
fired = collections.Counter(tuple(c["digest"].get("heuristics_fired", [])) for c in traj)
sigs = {tuple(c["digest"].get("names", [])) for c in traj}
plan = S.plan_slices(cands)

assert len(cands) == 443, f"candidates {len(cands)} != 443"
assert kinds == {"source_code": 224, "trace": 200, "design_doc": 19}, kinds
assert len(traj) == 200, len(traj)
assert list(fired) == [("element_counts", "request_text", "names")], fired
assert len(canonical_bytes(cat)) < 1_048_576, "over the byte cap"
assert not S.oversized_rows(cands), "a row exceeds one slice"
# Every candidate lands in exactly one slice: the partition must stay total and
# disjoint, which is the property the slicer's own tests pin and the one a new
# candidate kind could break.
placed = [cid for sl in plan for cid in sl.candidate_ids]
assert sorted(placed) == sorted(c["candidate_id"] for c in cands), "partition is not total"
assert len(placed) == len(set(placed)), "partition is not disjoint"

print("candidates:", len(cands))
print("kinds:", dict(kinds))
print("catalogue bytes:", len(canonical_bytes(cat)))
print("heuristics_fired across the 200:", dict(fired))
print("distinct name signatures:", len(sigs))
print("slices:", len(plan))
EOF
```

Expected: no assertion fires; catalogue ~466KB (was 444KB), distinct name signatures **68**, slices ~7.

- [ ] **Step 3: Record the measured numbers**

Write the four numbers down for Task 6: candidate count, catalogue bytes, distinct name signatures, slice count. Task 6's prose quotes them; do not quote the spec's figures if these differ.

- [ ] **Step 4: No commit**

Nothing changed on disk. If any assertion in Step 2 fired, stop here and report which — the design is falsified on that point and Tasks 5-8 should not proceed until it is settled.

---

### Task 5: Widen rb-extract's capture-instant rule

**Files:**
- Modify: `src/rubrica/skills/rb-extract/SKILL.md:159-169` (section 3, the `**A state observation needs its instant.**` paragraph)
- Test: `tests/unit/test_skills_extract.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: nothing importable. Two existing predicates (`test_skills_extract.py:181` and `:210`) pin six phrases inside section 3 and must stay green.

**Why:** classifying these files `trace` activates this rule, and measured on tau2 **0 of 200 trajectories carry any time-shaped key**. The instant exists as prose in the opening message (`"The current time is 2024-05-15 15:00:00 EST."` at `/0/content`), so the rule's letter is satisfiable while its worked example points somewhere the artifact has nothing.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_skills_extract.py`:

```python
def test_the_method_allows_a_prose_instant_where_no_field_carries_one():
    """Measured on tau2-bench's 200 chat trajectories: zero carry any
    time-shaped key, while the instant is stated in the opening message's prose
    ("The current time is 2024-05-15 15:00:00 EST."). Without this clause the
    rule's worked example points at a field the artifact does not have, and a
    member reading it literally records no instant at all.

    Scoped to section 3 with section_body for the reason the two predicates above
    are: skills.load() sets body to the whole file text, so a bare substring
    check would also be satisfied by the frontmatter or the Contract block.
    """
    method = " ".join(section_body(load(SKILL), "3. Method").lower().split())
    assert "in prose rather than in a field" in method
    assert "cite the locator of that message" in method
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/test_skills_extract.py -k prose_instant -v`
Expected: FAIL — `assert 'in prose rather than in a field' in method`

- [ ] **Step 3: Widen the prose, additively**

In `src/rubrica/skills/rb-extract/SKILL.md`, inside the `**A state observation needs its instant.**` paragraph, insert one sentence after `...with the value in \`quote\`.` and before `It rides as evidence because...`:

```
Where the capture states the instant in prose rather than in a field -- a chat
trajectory whose opening message says "The current time is ...", with no
timestamped field anywhere in the file -- cite the locator of that message with
the sentence in `quote`. The rule is the same and only the locator moves.
```

Change nothing else in the paragraph. All six pinned phrases — `observed state`, `capture instant`, `request_time`, `declared contract`, `only stage that reads this artifact`, `no later stage can recover` — must survive verbatim.

- [ ] **Step 4: Run the three predicates together**

Run: `uv run pytest tests/unit/test_skills_extract.py -v`
Expected: PASS, including `test_the_method_ties_a_state_observation_to_its_capture_instant` and `test_the_method_says_why_only_extract_can_carry_the_instant`.

- [ ] **Step 5: Measure the new predicate in both directions**

Per CLAUDE.md, a predicate nobody has watched fail is not yet a guard.

```bash
# Direction 1 -- blank the prose it checks; the predicate must go RED.
rm -rf /tmp/skills-probe && cp -r src/rubrica/skills /tmp/skills-probe
python3 - <<'EOF'
from pathlib import Path
p = Path("/tmp/skills-probe/rb-extract/SKILL.md")
t = p.read_text()
start = t.index("Where the capture states the instant in prose")
end = t.index("The rule is the same and only the locator moves.") + len(
    "The rule is the same and only the locator moves."
)
p.write_text(t[:start] + t[end:])
EOF
RUBRICA_SKILLS_DIR=/tmp/skills-probe uv run pytest tests/unit/test_skills_extract.py -k prose_instant -q
echo "expected: FAILED (exit non-zero)"

# Direction 2 -- reword meaning-preservingly; the predicate must stay GREEN.
rm -rf /tmp/skills-probe2 && cp -r src/rubrica/skills /tmp/skills-probe2
python3 - <<'EOF'
from pathlib import Path
p = Path("/tmp/skills-probe2/rb-extract/SKILL.md")
t = p.read_text()
p.write_text(t.replace(
    "The rule is the same and only the locator moves.",
    "Nothing else about the rule changes; the locator is the only part that moves.",
))
EOF
RUBRICA_SKILLS_DIR=/tmp/skills-probe2 uv run pytest tests/unit/test_skills_extract.py -k prose_instant -q
echo "expected: passed (exit 0)"
```

Expected: direction 1 FAILS, direction 2 PASSES. If direction 1 passes, the predicate is vacuous — rewrite it before committing.

- [ ] **Step 6: Run the gates and commit**

```bash
make test && make check && uv run rubrica check-skills
git add src/rubrica/skills/rb-extract/SKILL.md tests/unit/test_skills_extract.py
git commit -S -s -m "fix: Let extract cite a capture instant stated in prose

Classifying chat trajectories as traces activates section 3's \"a state
observation needs its instant\" rule, and measured on tau2-bench's 200
trajectories, zero carry any time-shaped key. The instant is there -- the
opening message says \"The current time is 2024-05-15 15:00:00 EST.\" -- so the
rule's letter was satisfiable while its worked example pointed at a field the
artifact does not have, which is how a member reading it literally records no
instant at all.

Additive: all six phrases the two predicates in test_skills_extract.py pin
inside section 3 survive verbatim, and a new predicate covers the added clause,
measured in both directions.

This change obliges re-recording rb-extract's exercise.md -- a reviewable diff
rather than silent drift -- which is the next commit.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 6: Correct the limitations this design falsifies

**Files:**
- Modify: `docs/design/limitations.md:1073-1082` (inside "Signature clustering is conditional, and specific to traces") and add one new entry after it, before `### The catalogue digest is the single point of failure for triage` at line 1084.

**Interfaces:**
- Consumes: the four measured numbers from Task 4 Step 3.
- Produces: nothing importable.

**Constraint:** this file is shipped documentation, so it **must not cite `docs/superpowers/`** — `tests/unit/test_docs_accuracy.py::test_no_shipped_markdown_cites_recorded_history` fails if it does. State the measurements; do not reference the spec.

- [ ] **Step 1: Replace the falsified paragraph**

Replace lines 1073-1082 (from `On a corpus whose container elements classify as \`other\`...` through `...would become one that cannot be surveyed.`) with:

```markdown
On a corpus whose container elements classify as `other` rather than `trace`, the
mitigation does not apply at all — such elements cluster on skeleton shape
alone.

Issue #4 was read as an instance of that, and the reading was wrong twice over.
Measured on the 200 tau2 chat trajectories it reports: their skeleton digests are
**39 distinct**, largest identical group 18, differing only by message count —
not identical, as this entry previously said. The conclusion survives on firmer
ground: clustering keys on `heuristics_fired` and `names`, and a skeleton digest
carries neither, so clustering is inapplicable however many distinct skeletons
exist.

The second correction is the ordering. The projection that made #4 look
downstream of this design — roughly 5,425 candidates and ~2.9MB, past both of
`survey`'s caps — holds only if chat trajectories *explode* into one candidate
per message. They should not: a trajectory is one episode, in which message 7 is
unreadable without 1 through 6, which is the same shape the OpenAPI ruling keeps
whole. Measured for the file-level digest instead: 443 candidates unchanged,
466KB against a 444KB baseline, 7 slices. Nothing approaches a cap, so there is
no ordering dependency in either direction.

What does not change is which grouping key those candidates get. They are corpus
candidates, not container elements, and `slices._signature` clusters only an
oversized container's elements — so signature clustering still does not reach
them, and they are grouped by `(root_index, dirname)` exactly as before.
```

- [ ] **Step 2: Add the new entry**

Insert immediately before line 1084's `### The catalogue digest is the single point of failure for triage`:

```markdown
### A chat trajectory cannot say whether it succeeded

`rb-triage-rule` §3 step 2 rules that "a failing trace is almost never a
near-duplicate of a successful one", and near-duplicate ruling is the dominant
task on a corpus of 200 trajectories carrying 68 distinct toolset signatures.
The fact that decides it is not in the file.

Measured on `tau2-bench`. The 200 trajectory files under
`data/tau2/trajectories` are a projection of the `simulations` records inside
`data/tau2/results/final/*.json`, and the projection dropped everything that
scores the episode: each simulation record carries `reward_info` — **`reward` is
1.0 for 100 records and 0.0 for the other 100** — plus `start_time`, `end_time`,
`duration`, `task_id` and `trial`, and the trajectory keeps only `messages`.

So the digest's silence here is honest rather than thin: `status` cannot fire
because no key in `_STATUS_KEYS` appears in any of the 5,182 messages, and
`error_markers` fires on 0 of the 200 because the structural error-key check
finds nothing. The only signal that would separate the 12 failing episodes is a
tool result whose `content` begins with an error sentinel, and reading it is the
value inspection `_has_error_marker` was deliberately narrowed to exclude.

The authoritative artifact is reachable in principle and not admitted in
practice, for a third independent reason: `results/final/*.json` is
`{info, simulations, tasks, timestamp}`, so `explode` refuses it — the top-level
dict's values are not all dicts, and a container whose records sit under one key
is invisible to explosion. Its existing skeleton digest is unusually good (43
nodes, untruncated, showing `/simulations` as `array[200]` carrying
`reward_info`, `messages` and `start_time`), so a triage member could rule on it
and request a projection. Exploding it is not affordable today regardless: the
per-record canonical size is **mean 38,723 bytes, max 111,626**, against a
65,536-byte slice cap, so `survey`'s row check would exit 2.

Parked, not fixed. Ruling: near-duplicate ruling over a chat-trajectory corpus
is unsound in a way no digest change repairs, and the fix — teaching `explode`
the records-under-a-key envelope — must wait for the row-bytes and
catalogue-bytes problem it creates.
```

- [ ] **Step 3: Verify the docs guards**

Run: `uv run pytest tests/unit/test_docs_accuracy.py -v`
Expected: PASS. If `test_no_shipped_markdown_cites_recorded_history` fails, a `superpowers` reference crept into the prose — remove it.

- [ ] **Step 4: Confirm every number matches Task 4**

Re-read the two blocks against Task 4 Step 3's recorded numbers. Any figure that differs must be corrected to the measurement, never the reverse.

- [ ] **Step 5: Run the gates and commit**

```bash
make test && make check
git add docs/design/limitations.md
git commit -S -s -m "docs: Correct two claims about #4 and record what the fix does not reach

The clustering entry said this corpus's skeletons are identical; measured, they
are 39 distinct with a largest group of 18, differing only by message count. The
conclusion holds on firmer ground -- clustering keys on heuristics_fired and
names, and a skeleton carries neither.

It also said #4 was downstream of the staged-triage design, on a projection of
5,425 candidates and ~2.9MB. That holds only under per-message explosion, which
a trajectory should not get: it is one episode, and message 7 is unreadable
without 1 through 6. Measured for the file-level digest: 443 candidates
unchanged, 466KB against a 444KB baseline, 7 slices.

New entry for what this fix cannot reach. The trajectory files are a projection
of the simulations records in results/final, and the projection dropped
reward_info -- reward is 1.0 for 100 and 0.0 for 100. rb-triage-rule rules that a
failing trace is almost never a near-duplicate of a successful one, so
near-duplicate ruling over this corpus is unsound in a way no digest change
repairs.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 7: Re-record rb-extract's exercise

**Files:**
- Modify: `src/rubrica/skills/rb-extract/exercise.md`

**Interfaces:**
- Consumes: Task 5 committed.
- Produces: nothing importable.

**Why:** changing a skill obliges re-recording its exercise, and that re-record is a reviewable diff rather than silent drift. **This task dispatches a model and costs money.** It is the only task here that does.

- [ ] **Step 1: Read the existing record and the by-hand guide**

Run: `cat src/rubrica/skills/rb-extract/exercise.md` and `cat docs/guides/running-a-stage-by-hand.md`

Note the format the existing record uses; the new one must match it.

- [ ] **Step 2: Build a run to the point extract can be dispatched**

Follow `docs/guides/running-a-stage-by-hand.md`. Use `tests/toy.py`'s `build_toy_run(runs_dir, upto=...)` if it reaches `intake` — check `_UPTO_STAGES` first rather than adding a checkpoint; nearly every request for a new one turned out to already exist.

- [ ] **Step 3: Dispatch extract once, against one input**

Per the guide. Cap parallelism at 1 here — the gateway degrades on concurrent streaming generation, and one dispatch is what an exercise records anyway.

- [ ] **Step 4: Write what happened, not what should have**

Rules for this file, both from CLAUDE.md:
- It states what **happened**. A reasoned number presented as an observed one corrupts the evidence; one such misattribution shipped and had to be retracted.
- Results belong in this file, not only in a ledger elsewhere.

Record specifically whether the dispatch cited an instant, and from where — a field or a message's prose. That is the behaviour Task 5's clause exists to change, and it is the only evidence this plan can produce about it.

- [ ] **Step 5: Run the gates and commit**

```bash
make test && make check && uv run rubrica check-skills
git add src/rubrica/skills/rb-extract/exercise.md
git commit -S -s -m "docs: Re-record rb-extract's exercise after the prose-instant clause

Changing a skill obliges re-recording, and this is that diff. States what the
dispatch did, including whether it cited an instant and from where.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

### Task 8: Answer issue #4

**Files:** none. `gh` only.

**Interfaces:**
- Consumes: Task 4's measurements; Tasks 1-6 committed.

- [ ] **Step 1: Post the comment**

```bash
gh issue comment 4 --body "$(cat <<'EOF'
Analysed and fixed, with three corrections to this report — all measured against
`tau2-bench/data/tau2/trajectories` at survey defaults.

**Both proposed levers fail.**

- `EXPLODE_MIN_COMMON_KEYS = 2` explodes **0 of 200 files**. 895 of 5,182
  messages are `{role, tool_calls}` and carry no `content`, so the per-file key
  intersection is `{role}` — one key — in all 200. Only a threshold of 1 admits
  them, and 1 is not a homogeneity test.
- Classifying the message *elements* `trace` leaves **4,267 of 5,182 (82%)**
  firing zero heuristics, mean digest 39 bytes — thinner than the skeleton it
  replaces. Chat messages hold their text under `content`, which appears in none
  of `_REQUEST_KEYS`, `_STATUS_KEYS`, `_COUNT_KEYS` or `_NAME_KEYS`.

**The unit was the defect, not the threshold.** A trajectory is one episode, in
which message 7 is unreadable without 1 through 6 — `explode`'s documented
*non*-exploding case, the same ruling that keeps an OpenAPI document whole. The
file failing to explode is `explode` working. The actual cause is one line:
`digest_for_payload`'s trace branch guards on `isinstance(payload, dict)`, so a
message list could never reach it however it was classified.

**Fixed at file level**, which also retires the "in series with #3" argument —
that rested entirely on explosion:

| | candidates | catalogue | slices |
|---|---|---|---|
| before | 443 | 444KB | 7 |
| after | 443 | 466KB | 7 |
| explosion | 5,425 (11× cap) | ~2.9MB (2.8× cap) | ~45 |

Each of the 200 now fires `[element_counts, request_text, names]`, yielding 14
distinct tool names and **68 distinct toolset signatures**.

**Two smaller corrections.** The 200 digests were not "mutually
indistinguishable": 39 distinct, largest identical group 18, differing only by
message count. And `limitations.md` repeated it as "every skeleton is identical";
both are corrected.

**One thing the fix does not reach, now recorded in `limitations.md`.** These
files cannot say whether they succeeded. They are a projection of the
`simulations` records in `data/tau2/results/final/*.json`, and the projection
dropped `reward_info` — `reward` is 1.0 for 100 records and 0.0 for the other
100 — along with `start_time` and `task_id`. Since `rb-triage-rule` rules that
"a failing trace is almost never a near-duplicate of a successful one",
near-duplicate ruling over this corpus is unsound in a way no digest change
repairs. The authoritative artifact is also invisible for an independent reason:
`{info, simulations, tasks, timestamp}` never explodes, because the top-level
dict's values are not all dicts. Exploding it is unaffordable today regardless —
per-record mean 38,723 bytes, max 111,626, against a 65,536-byte slice cap.
EOF
)"
```

- [ ] **Step 2: Close the issue if the maintainer agrees**

Do not close it unilaterally — the recorded limitation means part of what #4
describes is parked rather than solved. Ask.

---

## Self-Review

**Spec coverage:**

| spec section | task |
|---|---|
| §4 the shape rule | Task 1 |
| §5.1 producer split, §5.2 fields | Task 2 |
| §5.3 classification | Task 3 |
| §5.4 the guard that must stay green | Task 2 Step 4 |
| §6 rb-extract's capture instant | Task 5 |
| §7 tests | Tasks 1-3, 5 (each task's own steps) |
| §8 limitations owed | Task 6 |
| §9 order of work | Task order 1-8 |
| §10 verification | Task 4, plus each task's gates |
| §2 "does not change" list | Global Constraints |
| §3 rejected alternatives | Global Constraints (the do-not-touch list) |

No spec section is unimplemented.

**Placeholder scan:** none. Every code step carries the actual code; every test step carries the actual test; both `/tmp` probe scripts are written out.

**Type consistency:** `is_message_list(payload: Any) -> bool` is defined in Task 1 and consumed under that exact name in Tasks 2 and 3. `_trace_digest_from_dict` and `_trace_digest_from_messages` both return `tuple[dict, list[str]]` and are called only from `digest_for_payload`. `_SKELETON_MAX_CHILDREN`, `_SKELETON_DEPTH`, `_collect_names`, `_has_error_key`, `_has_error_marker`, `_first_scalar`, `_lookup_scopes` and `TRACE_HEURISTICS` are all existing names, spelled as they appear in `digest.py`.

**One deviation from the spec, flagged deliberately:** Task 1 requires `role` to be a `str`, where spec §4 says only that every element carries `role`. Reason in the task. It is a tightening, not a widening — nothing the spec admits is excluded except a payload whose role is unhashable, which would have raised.
