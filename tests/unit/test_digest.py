"""Whether a digest carries what a decision needs.

Every assertion here is anchored to a decision the parsec run actually made by
hand, because "is this digest good enough" is otherwise unanswerable. If a
selection made on 2026-08-13 is not reachable from these fields, the digest is
wrong -- not the test.
"""

from __future__ import annotations

import json

from rubrica import digest


def test_prose_carries_the_full_heading_outline(tmp_path):
    """The parsec prose documents were admitted on title and structure.

    The outline is complete rather than truncated: it is the cheapest possible
    statement of what a document covers, and truncating it is how a triage
    misses the one section that mattered.
    """
    path = tmp_path / "architecture.md"
    path.write_text(
        "# Parsec\n\nIntro.\n\n## Routing\n\ntext\n\n### Fast path\n\nmore\n\n## Streaming\n\nx\n",
        encoding="utf-8",
    )
    result = digest.digest_for_path(path, "design_doc", body_chars=20)
    assert result["headings"] == ["# Parsec", "## Routing", "### Fast path", "## Streaming"]
    assert result["lines"] == 15
    assert len(result["body_head"]) <= 20
    assert result["digest_truncated"] is True


def test_source_carries_top_level_assignments_not_only_defs(tmp_path):
    """Spec §8: triage can only name TOOL_DEFINITIONS as a projection's
    extraction point if the digest lists top-level assignments. Without this
    field the projection brief cannot say where to start."""
    path = tmp_path / "tool_definitions.py"
    path.write_text(
        "import json\nfrom typing import Any\n\n"
        "TOOL_DEFINITIONS = [{'name': 'query_aap2'}]\n"
        "DELEGATION_TOOLS = []\n\n"
        "def build(x: Any) -> dict:\n    return {}\n\n"
        "class Registry:\n    pass\n",
        encoding="utf-8",
    )
    result = digest.digest_for_path(path, "source_code", body_chars=2000)
    assert result["assignments"] == ["DELEGATION_TOOLS", "TOOL_DEFINITIONS"]
    assert result["defs"] == ["build"]
    assert result["classes"] == ["Registry"]
    assert result["imports"] == ["json", "typing"]


def test_a_json_document_carries_a_structural_skeleton(tmp_path):
    path = tmp_path / "tools.json"
    path.write_text(
        json.dumps({"tools": [{"name": "a", "input_schema": {"type": "object"}}]}),
        encoding="utf-8",
    )
    result = digest.digest_for_path(path, "mcp_tool_schema", body_chars=2000)
    assert result["skeleton"]["/tools"] == {"type": "array", "length": 1}
    assert result["skeleton"]["/tools/0/name"] == {"type": "string"}


def test_a_trace_digest_reaches_every_parsec_selection():
    """The four facts the 2026-08-13 selection actually turned on:

    t7 kept for being the only ERROR with three spans; t3 identified as an
    icinga/aap2 crossover from its question text; depth judged from span count;
    tool coverage judged from span names.
    """
    element = {
        "trace_id": "tr-eef9",
        "status": "TraceStatus.ERROR",
        "execution_time_ms": 11776,
        "request_preview": '{"question": "How many sandbox accounts do we have in each region?"',
        "response_preview": '{"response": "I will query...", "routing_method": "llm"}',
        "spans": [
            {
                "name": "parsec:orchestrator",
                "span_type": "AGENT",
                "events": [{"name": "exception"}],
            },
            {"name": "query_aws_account_db", "span_type": "TOOL", "events": []},
            {"name": "db_list_tables", "span_type": "TOOL", "events": []},
        ],
    }
    result = digest.digest_for_payload(element, "trace", body_chars=2000)
    assert result["status"] == "TraceStatus.ERROR"
    assert result["element_counts"]["spans"] == 3
    assert "sandbox accounts" in result["request_text"]
    assert result["names"] == ["db_list_tables", "parsec:orchestrator", "query_aws_account_db"]
    assert result["error_markers"] is True
    assert "status" in result["heuristics_fired"]
    assert "names" in result["heuristics_fired"]


def test_an_mlflow_enveloped_trace_reaches_the_same_facts():
    """The same four facts, from a capture that wraps them in `info`/`data`.

    MEASURED on the reservation-service corpus: all 27 MLflow trace elements
    fired `names` alone, because it was the only heuristic that recursed.
    `status` wanted a top-level `state` and MLflow puts it at `info.state`;
    `request_text` wanted `request_preview` and MLflow puts it at
    `info.request_preview`; `element_counts` wanted `spans` and MLflow puts it
    at `data.spans`. Three of five were structurally unable to fire, and
    rb-triage reported that nothing in the catalogue attested a failure -- for a
    corpus in which nine traces carry an error payload or an empty result.

    The parsec capture above is flat, which is why the top-level-only lookup was
    right for the corpus it was measured against and wrong for this one.
    """
    element = {
        "trace_id": "tr-59ef",
        "info": {
            "trace_id": "tr-59ef",
            "state": "OK",
            "request_preview": '{"messages": [{"content": "Check availability at rest_999"}]}',
            "execution_duration_ms": 4210,
        },
        "data": {
            "spans": [
                {"name": "LangGraph"},
                {"name": "check_availability"},
            ]
        },
    }
    result = digest.digest_for_payload(element, "trace", body_chars=2000)
    assert result["status"] == "OK"
    assert result["element_counts"]["spans"] == 2
    assert "rest_999" in result["request_text"]
    assert result["names"] == ["LangGraph", "check_availability"]
    for heuristic in ("status", "element_counts", "request_text", "names"):
        assert heuristic in result["heuristics_fired"], heuristic


def test_a_top_level_field_outranks_the_envelope():
    """Scope order is precedence, not a merge. A capture that states its own
    status at the top level keeps that value even when an envelope disagrees --
    otherwise adding envelope support would silently change what every flat
    capture already digests to."""
    element = {
        "status": "TraceStatus.ERROR",
        "spans": [{"name": "a"}],
        "info": {"state": "OK", "request_preview": "ignored"},
        "data": {"spans": [{"name": "b"}, {"name": "c"}]},
    }
    result = digest.digest_for_payload(element, "trace", body_chars=2000)
    assert result["status"] == "TraceStatus.ERROR"
    assert result["element_counts"]["spans"] == 1


def test_the_envelope_widening_does_not_reach_into_spans():
    """One level into named envelope keys, never a tree walk.

    This is the constraint `_has_error_marker` was narrowed to satisfy: a
    span-level `status` reads "error" on internal or recovered steps, and
    treating one as the trace's own status is how the earlier version came to
    fire on 62 successful elements out of 130. A trace whose only `status` sits
    inside `data.spans[*]` must therefore report no status at all.
    """
    element = {"data": {"spans": [{"name": "db_query", "status": "error"}]}}
    result = digest.digest_for_payload(element, "trace", body_chars=2000)
    assert "status" not in result
    assert "status" not in result["heuristics_fired"]
    assert "error_markers" not in result["heuristics_fired"]
    # The span list itself is still counted -- that is one level, not a walk.
    assert result["element_counts"]["spans"] == 1


def test_a_heuristic_that_does_not_fire_is_absent_from_heuristics_fired():
    """This is the whole mitigation for §5.3.

    A digest that silently lacked a field would make triage guess. Recording
    which heuristics fired is what lets it decline digest_insufficient and name
    what it needed -- so this assertion is the load-bearing one in the file.
    """
    result = digest.digest_for_payload({"a": 1, "b": 2, "c": 3}, "trace", body_chars=2000)
    assert "status" not in result["heuristics_fired"]
    assert "names" not in result["heuristics_fired"]
    assert result["heuristics_fired"] == []


def test_every_named_heuristic_is_reachable():
    """A heuristic nobody can trigger is dead prose in the skill that cites it."""
    element = {
        "status": "OK",
        "spans": [{"name": "a"}, {"name": "b"}],
        "question": "why",
        "error": "boom",
    }
    result = digest.digest_for_payload(element, "trace", body_chars=2000)
    assert set(result["heuristics_fired"]) == set(digest.TRACE_HEURISTICS)


def test_an_undecodable_file_digests_to_a_recorded_failure(tmp_path):
    """Not a raise: survey already recorded readable files only, so reaching
    here means the bytes are not text -- and a digest that reports that is what
    lets triage decline rather than the run abort."""
    path = tmp_path / "notes.md"
    path.write_bytes(b"\xff\xfe\x00bad")
    result = digest.digest_for_path(path, "design_doc", body_chars=2000)
    assert result["undecodable"] is True


def test_a_pathologically_nested_json_document_does_not_raise(tmp_path):
    """survey.py's own module docstring states its rule as 'no size-based
    exclusion,' so nothing upstream screens a file for shape before it reaches
    here. CPython's json decoder raises RecursionError, not JSONDecodeError,
    for a deeply nested document -- measured directly: json.loads on a
    10,000-deep [[[...]]] raises RecursionError under this interpreter's
    default recursion limit. A stage defect surfacing as an uncaught
    exception is exactly what this module's own contract (never raise) rules
    out."""
    path = tmp_path / "deep.json"
    depth = 10_000
    path.write_text("[" * depth + "]" * depth, encoding="utf-8")
    result = digest.digest_for_path(path, "mcp_tool_schema", body_chars=2000)
    assert "undecodable" not in result
    # Fell back to the prose digest, same as any other file this module has
    # no reader for -- not a crash, and not a fabricated "skeleton".
    assert "headings" in result


def test_error_markers_does_not_fire_on_ordinary_error_vocabulary():
    """Narrowed after being measured too noisy to trust: a blanket scan of
    every string value for "error"/"exception" fired on 63 of the real
    130-element parsec capture's elements, 62 of them at TraceStatus.OK.
    Parsec is an ops assistant, so a correct answer routinely discusses
    "error rate" and "error logs" as ordinary domain vocabulary, and a
    recovered step's own status attribute can read "error" without the trace
    having failed. Neither should raise this flag -- only the trace's own
    status/state/outcome value, or a literal error-shaped key, should."""
    element = {
        "status": "TraceStatus.OK",
        "response_preview": '{"response": "The error rate held steady; no errors were logged."}',
        "spans": [{"name": "db_query", "status": "error"}],
    }
    result = digest.digest_for_payload(element, "trace", body_chars=2000)
    assert "error_markers" not in result
    assert "error_markers" not in result["heuristics_fired"]


def test_error_markers_still_fires_on_a_structural_error_key_without_error_status():
    """The narrowed heuristic keeps a second, independent path: a literal
    error-shaped key (_ERROR_KEYS) fires even when the trace's own status
    says nothing about failure -- e.g. a caught-and-logged exception in a
    trace whose top-level status was never updated to reflect it."""
    element = {"status": "OK", "steps": [{"traceback": "boom"}]}
    result = digest.digest_for_payload(element, "trace", body_chars=2000)
    assert result["error_markers"] is True


def test_a_wide_object_skeleton_does_not_scale_with_key_count_past_the_cap():
    """_SKELETON_MAX_CHILDREN is the fix that actually brought the real
    corpus under its context budget: one 1191-key pricing dict
    (ec2_pricing.json) produced a 783KB digest by itself before this cap
    existed, because the skeleton recursed into every key even though its
    displayed `keys` list was already capped at 32. None of the original
    seven tests exercised a dict wider than the cap, so this fix could be
    silently reverted with nothing turning red. A 40-key and a 1000-key dict
    must cost the digest the same."""
    small = {f"k{i:04d}": i for i in range(40)}
    huge = {f"k{i:04d}": i for i in range(1000)}
    small_result = digest.digest_for_payload({"d": small}, "other", body_chars=2000)
    huge_result = digest.digest_for_payload({"d": huge}, "other", body_chars=2000)
    small_size = len(json.dumps(small_result))
    huge_size = len(json.dumps(huge_result))
    # Both are past the 32-key cap, so the only difference between them
    # should be the digit width of `key_count` (40 vs 1000) -- not per-key
    # growth. A generous bound: nowhere near the ~24,000 extra bytes 960
    # uncapped extra keys would cost.
    assert huge_size - small_size < 50


def test_a_wide_object_skeleton_reports_its_true_key_count_and_truncation():
    """The array branch reports the true `length` even though it only
    expands element 0; the object branch's `keys` list, capped silently,
    was the one truncation point in the module with no visible marker -- the
    exact shape that produced the ec2_pricing.json overrun above. A digest
    that hides its own truncation is what turns this module's blindness into
    a silent bad selection instead of a `digest_insufficient` decline."""
    narrow = {f"k{i:03d}": i for i in range(5)}
    wide = {f"k{i:03d}": i for i in range(40)}
    narrow_skeleton = digest.digest_for_payload({"d": narrow}, "other", body_chars=2000)[
        "skeleton"
    ]["/d"]
    wide_skeleton = digest.digest_for_payload({"d": wide}, "other", body_chars=2000)["skeleton"][
        "/d"
    ]
    assert narrow_skeleton["key_count"] == 5
    assert narrow_skeleton["keys_truncated"] is False
    assert wide_skeleton["key_count"] == 40
    assert wide_skeleton["keys_truncated"] is True
    assert len(wide_skeleton["keys"]) == 32


def test_a_non_dict_trace_payload_falls_back_to_the_generic_skeleton():
    """survey.explode can hand a trace-kind element that is not itself a dict
    (a heterogeneous or scalar element); digest_for_payload's trace branch
    guards on isinstance(payload, dict), so this must not raise and must not
    silently produce an empty result."""
    result = digest.digest_for_payload(["not", "a", "dict"], "trace", body_chars=2000)
    assert result["skeleton"]["/"] == {"type": "array", "length": 3}


def test_skeleton_stops_at_the_node_cap_and_says_so():
    # A wide, deep payload: 32 keys at each of three levels is 32^3 pointers
    # if nothing bounds the total, which is the shape that produced a 39KB
    # candidate row on the real corpus.
    leaf = {f"k{i}": 1 for i in range(32)}
    mid = {f"m{i}": dict(leaf) for i in range(32)}
    payload = {f"t{i}": dict(mid) for i in range(32)}
    result = digest.digest_for_payload(payload, "other", body_chars=2000)
    assert len(result["skeleton"]) <= 128
    assert result["skeleton_nodes_truncated"] is True


def test_a_small_skeleton_is_not_marked_truncated():
    result = digest.digest_for_payload({"a": {"b": 1}}, "other", body_chars=2000)
    assert result["skeleton_nodes_truncated"] is False
    assert result["skeleton"]  # and it still has content


def test_the_clamp_does_not_touch_a_sixty_nine_node_skeleton():
    # tau2's results.json digests measure 69 nodes; the cap must not bind on
    # them, or a real trajectory capture loses shape to a fix aimed at a
    # pricing table.
    payload = {f"k{i}": {"a": 1, "b": 2} for i in range(23)}
    result = digest.digest_for_payload(payload, "other", body_chars=2000)
    assert result["skeleton_nodes_truncated"] is False
    assert len(result["skeleton"]) == 69


def test_trace_digests_carry_no_skeleton_key_at_all():
    # The clamp is a skeleton concern. A trace digest has no skeleton, so it
    # must not grow a truncation flag about one.
    result = digest.digest_for_payload({"trace_id": "t", "spans": []}, "trace", body_chars=2000)
    assert "skeleton" not in result
    assert "skeleton_nodes_truncated" not in result


def test_a_skeleton_landing_exactly_on_the_node_cap_is_not_truncated():
    # A payload whose natural, uncapped skeleton has exactly 128 nodes: 8
    # top-level keys, each holding 15 leaves, is 8 + 8*15 == 128. Nothing about
    # this walk is ever refused by the budget guard -- the count only reaches
    # 128 on the very last write -- so comparing the final length to the cap
    # (as an earlier version of this flag did) falsely reports truncation here.
    # This is the exact boundary a length-based proxy cannot distinguish from a
    # walk that was actually cut off.
    payload = {f"t{i}": {f"k{j}": 1 for j in range(15)} for i in range(8)}
    result = digest.digest_for_payload(payload, "other", body_chars=2000)
    assert len(result["skeleton"]) == 128
    assert result["skeleton_nodes_truncated"] is False


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


# One trajectory, shaped exactly like tau2-bench's: a system policy stating the
# instant in prose, a user request, an assistant tool call, and a tool result.
_TRAJECTORY = [
    {
        "role": "system",
        "content": "# Airline Agent Policy\n\nThe current time is 2024-05-15 15:00:00 EST.",
    },
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
