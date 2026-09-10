"""Whether a digest carries what a decision needs.

Every assertion here is anchored to a decision the parsec run actually made by
hand, because "is this digest good enough" is otherwise unanswerable. If a
selection made on 2026-08-13 is not reachable from these fields, the digest is
wrong -- not the test.
"""

from __future__ import annotations

import json
from pathlib import Path

from rubrica import digest, slices
from rubrica.intake import classify

# One number above any cap under test, so a cap change cannot silently make these
# generators stop exceeding it.
_OVER = 400


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
    # Python has a parser, so neither fallback marker may appear. Without
    # these, a regression routing `.py` into the prose branch would leave
    # every test below green.
    assert "unsupported_language" not in result
    assert "parse_failed" not in result


def test_a_javascript_file_digests_as_prose_rather_than_a_parse_failure(tmp_path):
    """`_source_digest` parses with Python's `ast`, so it can only read `.py`.

    Measured on the parsec corpus (run-20260826-090456): 135 of 135 `.py`
    candidates parsed and 0 of 5 `.js` did, a split that falls exactly on the
    language boundary rather than on anything the bytes contain. The seven
    suffixes without a parser therefore take the prose route, which a triage
    pass can rule on, instead of a bare flag it cannot.
    """
    path = tmp_path / "app.js"
    path.write_text(
        "// Render the choice list.\n"
        "import { describe } from 'vitest';\n"
        "export function renderChoice(opts) {\n"
        "  return opts.map(o => o.label);\n"
        "}\n"
        "export class Exporter { toCSV(rows) { return rows.join(','); } }\n",
        encoding="utf-8",
    )
    # Through the real path: the file is still classified as source code, because
    # it is source code. Only the digester's route changes.
    assert classify(path) == "source_code"
    result = digest.digest_for_path(path, classify(path), body_chars=2000)

    assert result["unsupported_language"] == ".js"
    # The whole point: valid JavaScript is not a parse failure, and a digest that
    # said so put a digester bug into a gate-0 brief as a corpus gap.
    assert "parse_failed" not in result
    assert result["lines"] == 6
    assert "renderChoice" in result["body_head"]
    assert result["digest_truncated"] is False


def test_the_unsupported_route_turns_on_the_language_not_on_the_characters(tmp_path):
    """Four of the five parsec `.js` failures named a unicode character, which
    makes the defect look like an encoding problem. It is not: pure-ASCII,
    idiomatic JavaScript fails `ast.parse` identically. This pins the em-dash as
    a red herring, so a later fix aimed at the characters cannot look sufficient.
    """
    path = tmp_path / "pure.js"
    path.write_text("export function f(a) { return a.map(x => x + 1); }\n", encoding="utf-8")
    result = digest.digest_for_path(path, "source_code", body_chars=2000)
    assert result["unsupported_language"] == ".js"
    assert "parse_failed" not in result


def test_a_python_file_that_genuinely_does_not_parse_still_says_parse_failed(tmp_path):
    """`parse_failed` keeps its name and narrows to what it says. It is the one
    reading a caller cannot get any other way -- a `.py` file whose bytes the
    parser rejects -- and it must stay distinguishable from a language this
    digester has no parser for at all.
    """
    path = tmp_path / "broken.py"
    path.write_text("def f(\n", encoding="utf-8")
    result = digest.digest_for_path(path, "source_code", body_chars=2000)
    assert result["parse_failed"] is True
    # The two markers are mutually exclusive by construction: this is a Python
    # file and Python has a parser, so nothing here is unsupported.
    assert "unsupported_language" not in result


def _generated_module(
    path: Path,
    *,
    defs: int = 0,
    assigns: int = 0,
    classes: int = 0,
    imports: int = 0,
    name_chars: int = 8,
) -> Path:
    """A Python module of exactly the requested top-level shape.

    Generated rather than fixtured because the point is a count no real file in
    this tree reaches: the largest real module here has 269 top-level defs, and
    the rows the issue measured are at 500 and 2,000.
    """
    pad = "x" * max(0, name_chars - 6)
    lines = [f"import mod_{i}_{pad}" for i in range(imports)]
    lines += [f"A_{i}_{pad} = {i}" for i in range(assigns)]
    lines += [f"def f_{i}_{pad}():\n    pass" for i in range(defs)]
    lines += [f"class C_{i}_{pad}:\n    pass" for i in range(classes)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_a_source_digest_caps_every_one_of_its_four_name_lists(tmp_path):
    """`_source_digest` bounded nothing: `defs`, `classes`, `assignments` and
    `imports` were each emitted in full, so one candidate's digest grew linearly
    with its top-level name count. Every other producer in this module has a bound
    and a visible flag for hitting it -- `_MAX_NAMES`, `_MAX_ROLE_CHARS`,
    `_SKELETON_MAX_NODES`, `keys_truncated`, `digest_truncated`. This one had
    neither.
    """
    path = _generated_module(
        tmp_path / "wide.py",
        defs=_OVER,
        assigns=_OVER,
        classes=_OVER,
        imports=_OVER,
    )
    result = digest.digest_for_path(path, "source_code", body_chars=2000)
    for field in ("defs", "classes", "assignments", "imports"):
        assert len(result[field]) == digest._MAX_SOURCE_NAMES, field


def test_a_capped_source_digest_stays_far_inside_one_slice(tmp_path):
    """The consequence the caps exist to prevent, asserted on the quantity survey
    actually refuses on. Measured before them: 2,000 defs plus 2,000 assignments
    digested to 199,852 bytes, three times over the 65,536-byte slice cap, and a
    slice holding one candidate is already minimal so no slicer could rescue the
    row. 500 + 500 produced 49,352 bytes -- 75% of one slice in a single row.
    """
    path = _generated_module(tmp_path / "huge.py", defs=2000, assigns=2000)
    result = digest.digest_for_path(path, "source_code", body_chars=2000)
    assert len(json.dumps(result).encode("utf-8")) < slices.DEFAULT_SLICE_BYTES // 2


def test_a_source_name_is_bounded_in_characters_as_well_as_in_entries(tmp_path):
    """An entry cap without a character bound is the defect this module already
    carried on `names`, and `ast` will parse an identifier of any width -- so caps
    alone would leave the byte hole open in a sibling producer. Reuses
    `_MAX_NAME_CHARS` rather than inventing a second number: the longest real
    top-level name in this tree is 92 characters, so 128 truncates none of the
    3,456 measured.
    """
    path = _generated_module(tmp_path / "verbose.py", defs=2, name_chars=40_000)
    result = digest.digest_for_path(path, "source_code", body_chars=2000)
    assert all(len(name) <= digest._MAX_NAME_CHARS for name in result["defs"])


def test_a_truncated_source_digest_says_so(tmp_path):
    """Same convention as every sibling flag: a truncation a prompt can see is a
    fact about the candidate, one it cannot see is a lie about it."""
    path = _generated_module(tmp_path / "wide.py", defs=_OVER)
    result = digest.digest_for_path(path, "source_code", body_chars=2000)
    assert result["source_names_truncated"] is True


def test_an_untruncated_source_digest_says_so_rather_than_omitting_the_flag(tmp_path):
    """Unconditional, for the reason `keys_truncated` is: a flag a reader only sees
    when it is true cannot be told apart from a digest written before the flag
    existed. The median module in this tree has 14 top-level names in its widest
    list, so False is what nearly every real candidate reports."""
    path = _generated_module(tmp_path / "ordinary.py", defs=3, assigns=2, imports=1)
    result = digest.digest_for_path(path, "source_code", body_chars=2000)
    assert result["source_names_truncated"] is False


def test_a_source_list_exactly_at_the_cap_is_not_reported_truncated(tmp_path):
    """The flag is set where the budget actually refuses a name, never re-derived
    from `len(...) >= CAP`. `_skeleton`'s `truncated[0]` records the measurement
    that forced this: the length comparison false-positives on a walk whose
    natural size lands exactly on the cap, where nothing was cut off.
    """
    at_cap = _generated_module(tmp_path / "at.py", defs=digest._MAX_SOURCE_NAMES)
    past_cap = _generated_module(tmp_path / "past.py", defs=digest._MAX_SOURCE_NAMES + 1)
    at = digest.digest_for_path(at_cap, "source_code", body_chars=2000)
    past = digest.digest_for_path(past_cap, "source_code", body_chars=2000)
    assert at["source_names_truncated"] is False
    assert past["source_names_truncated"] is True


def test_a_parse_failure_grows_no_truncation_flag(tmp_path):
    """`{"parse_failed": True}` is the whole digest for bytes that are not Python,
    so it must not grow a flag about names nothing collected -- the rule that keeps
    `role_keys_truncated` off a dict-shaped trace."""
    path = tmp_path / "broken.py"
    path.write_text("def (:\n", encoding="utf-8")
    result = digest.digest_for_path(path, "source_code", body_chars=2000)
    assert result["parse_failed"] is True
    assert "source_names_truncated" not in result


def test_an_unsupported_source_file_carries_no_heading_outline(tmp_path):
    """`_prose_digest`'s `headings` means markdown headings, and is deliberately
    complete rather than truncated. A `#`-commented language would therefore put
    every comment line in the candidate row, unbounded in comment count:
    measured, 500 Ruby comment lines produce 500 headings and 21,890 bytes,
    against the 65,536-byte one-slice cap that makes `survey` exit 2 on an
    oversized row. Six of the seven unsupported suffixes use `//` and would
    collect an empty list, so the field earns nothing either way.
    """
    path = tmp_path / "reservation.rb"
    path.write_text(
        "\n".join([f"# comment line {i}" for i in range(500)] + ["class Reservation", "end"]),
        encoding="utf-8",
    )
    result = digest.digest_for_path(path, "source_code", body_chars=2000)
    assert result["unsupported_language"] == ".rb"
    assert "headings" not in result
    # The row cannot grow with comment count: what remains is the bounded set.
    assert set(result) == {"lines", "body_head", "digest_truncated", "unsupported_language"}


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
    """A reachable route, though not the one this docstring used to name.

    `survey.explode` cannot hand over a non-dict trace element: `_homogeneous`
    refuses any element list holding a non-dict, and `classify_payload` has no
    branch outside `isinstance(payload, dict)` so it could not call one "trace"
    anyway. `intake.classify` is the route -- its list branch decides on
    `payload[0]` alone, so `[{"trace_id": "t1", "spans": []}, "scalar", 3]`
    classifies `trace`, `explode` declines it as heterogeneous, and the whole list
    reaches the digest.

    digest_for_payload's trace branch dispatches on shape -- a dict to one
    producer, a message list to another -- and a payload that is neither falls
    through here, so this must not raise and must not silently produce an empty
    result."""
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
    """The cap sits in the predicate, which bounds how many keys `element_counts`
    can have -- 33 -- and nothing about how wide one is. Their width is bounded
    separately by `_MAX_ROLE_CHARS`; see the truncation tests below. Measured on
    tau2: 4 roles."""
    many = [{"role": f"r{i}", "content": "x"} for i in range(digest._SKELETON_MAX_CHILDREN + 1)]
    assert digest.is_message_list(many) is False


def test_a_payload_at_exactly_the_breadth_cap_is_still_a_conversation():
    """The cap is `<=`, and the negative above sits one role past it -- a count
    that fails `< cap` and `<= cap` alike, so it cannot see an off-by-one edit.
    Only a payload landing exactly on the boundary can."""
    exactly = [{"role": f"r{i}", "content": "x"} for i in range(digest._SKELETON_MAX_CHILDREN)]
    assert digest.is_message_list(exactly) is True


def test_a_list_of_scalars_is_not_a_message_list():
    """The same payload `test_a_non_dict_trace_payload_falls_back_to_the_generic_skeleton`
    pins: it must keep reaching the skeleton, which requires failing here."""
    assert digest.is_message_list(["not", "a", "dict"]) is False
    assert digest.is_message_list({"role": "user"}) is False
    # `None` is the central case, not an exotic one: `intake.classify` calls this
    # with `_json_or_none(path)`, which returns None for every non-JSON file a
    # corpus walk keeps -- a Makefile, a CSV, a .env. Without the
    # `isinstance(payload, list)` clause, `len(None)` raises TypeError inside
    # `survey`, whose cli.py dispatch block catches only (UsageError,
    # ArtifactError, OSError) and sits ahead of main()'s catch-all -- measured
    # end-to-end with the clause removed, it escapes main() as a traceback: exit 1
    # with empty stdout, the one shape the exit-code contract forbids.
    #
    # Measured, three scopes, because the clause was earlier read as unpinned and
    # that is true of only the narrowest one. Delete it and this module alone still
    # passed every test it had; the wider unit suite failed 280, including
    # test_survey.py::test_classify_returns_a_kind_for_a_pathologically_nested_file,
    # which reaches this predicate down the same `_json_or_none` -> None route. So
    # the clause was pinned, heavily but only as a side effect of tests about
    # something else -- and a shape rule that no assertion beside it states is one
    # a reader will re-triage as unreachable. This line is that assertion, and with
    # it deleted this is the only test in the module that goes red.
    assert digest.is_message_list(None) is False


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
    """The chat-trajectory skeletons (docs/design/findings.md): 200 such files
    reached triage as skeleton-only rows carrying no tool names, no request text
    and no counts. Measured across that corpus, these three fields yield 14
    distinct tool names and 68 distinct toolset signatures over 200 files -- the
    discrimination a near-duplicate ruling reads."""
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


def test_request_text_comes_from_the_first_user_turn_not_a_later_one():
    """First, not merely some: a design clause whose violation is silent. Drop
    the loop's `break` and the field carries the *last* user turn instead, with
    no key appearing or disappearing to say so. `_TRAJECTORY` has one user turn,
    so it cannot tell the two apart -- this payload has two."""
    payload = [
        {"role": "system", "content": "policy"},
        {"role": "user", "content": "I want to cancel reservation EHGLP3."},
        {"role": "assistant", "content": "Cancelled."},
        {"role": "user", "content": "Now change my seat."},
    ]
    result = digest.digest_for_payload(payload, "trace", body_chars=2000)
    assert result["request_text"] == "I want to cancel reservation EHGLP3."


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
    """Both absent from this digest, for reasons that are different in kind.

    `status` is not implemented on this path at all -- the message-list producer
    makes no `_first_scalar` call and no `_STATUS_KEYS` lookup. The tau2
    measurement (no key in `_STATUS_KEYS` in any of the 5,182 messages) is why
    implementing it was unnecessary, not why it stays quiet: a trajectory that did
    carry a status key would not fire it either.

    `error_markers` is implemented, by the producer's `_has_error_key` clause, and
    fires -- see the test below, which is the one that pins it. It found nothing
    here and on 0 of tau2's 200 files, which is a fact about the corpus. A
    value-substring rule that fired on 12 of 200 was rejected as the very
    inspection this module narrowed out.

    So this asserts one absent implementation and one implementation that found
    nothing, and `heuristics_fired` records both as the same kind of silence.
    """
    result = digest.digest_for_payload(_TRAJECTORY, "trace", body_chars=2000)
    assert "status" not in result
    assert "error_markers" not in result
    assert "status" not in result["heuristics_fired"]
    assert "error_markers" not in result["heuristics_fired"]


def test_error_markers_fires_on_a_message_carrying_an_error_shaped_key():
    """The message-list producer's own `_has_error_key` clause. Every other
    assertion about it on this path is an *absence*, and tau2's 200 files fire it
    0 times. Measured: delete the clause and this is the only test in tests/unit
    that goes red -- the reachability test above covers the dict producer only."""
    payload = [
        {"role": "user", "content": "cancel reservation EHGLP3"},
        {"role": "tool", "tool_call_id": "call_1", "error": "boom"},
    ]
    result = digest.digest_for_payload(payload, "trace", body_chars=2000)
    assert result["error_markers"] is True
    assert "error_markers" in result["heuristics_fired"]


def test_a_field_saying_no_error_occurred_does_not_fire_error_markers():
    """The emptiness guard omitted `False`, so `error: False` -- a field whose
    whole content is "nothing went wrong" -- asserted failure.

    Measured on each of the four metadata-rich airline result files under
    tau2-bench's `data/tau2/results/final`, whose messages carry a top-level
    `error: False`: `_has_error_key` fired on 200 of 200 episodes in all four,
    including every episode that scored `reward == 1.0`. The count of those is
    deliberately not stated -- it varies by file (100, 112, 101 and 118 of 200),
    and the finding is that success and failure became indistinguishable, not how
    many of each a given file holds. `heuristics_fired` then reported
    `error_markers` as a found fact about every successful episode, which defeats
    `rb-triage-rule` reading a failing trace as almost never a near-duplicate of
    a successful one.

    The three cases are one guard, not three: `in` compares by equality and
    `0 == False`, so the single `False` entry covers the zero count too, and
    `None` was already handled. The truthy value is asserted alongside them
    because a guard that swallowed it would be the mirror defect -- silence
    where a real error key exists -- and the test above pins only the string
    form through the producer.
    """
    assert digest._has_error_key({"error": False}, digest._SKELETON_DEPTH) is False
    assert digest._has_error_key({"error": 0}, digest._SKELETON_DEPTH) is False
    assert digest._has_error_key({"error": None}, digest._SKELETON_DEPTH) is False
    assert digest._has_error_key({"error": True}, digest._SKELETON_DEPTH) is True

    # Through the producer, on the shape this became newly reachable for: an
    # episode whose every message states it did not fail.
    payload = [
        {"role": "user", "content": "cancel reservation EHGLP3", "error": False},
        {"role": "assistant", "content": "Cancelled.", "error": False},
    ]
    result = digest.digest_for_payload(payload, "trace", body_chars=2000)
    assert "error_markers" not in result
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


def test_a_long_role_is_truncated_so_element_counts_stays_byte_bounded():
    """The distinct-role cap bounds the *number* of `element_counts` keys, not
    their bytes, and the key is built by interpolating the role verbatim.

    Measured on this exact payload before `_MAX_ROLE_CHARS` existed: 96,514 bytes
    as a trace digest against 248 as the skeleton the same payload got before the
    trace branch dispatched on shape -- so one row cleared
    `slices.DEFAULT_SLICE_BYTES` (65,536) and `survey`'s oversized-row check would
    exit 2 for the whole corpus. 32 distinct roles is exactly the predicate's cap,
    so this payload is one it admits rather than a shape it rules out.
    """
    payload = [{"role": "x" * 3000 + str(i), "content": "hi"} for i in range(32)]
    assert digest.is_message_list(payload) is True
    result = digest.digest_for_payload(payload, "trace", body_chars=2000)
    assert len(json.dumps(result)) < 65536
    # Every key still spells a role, just a bounded prefix of one.
    for key in result["element_counts"]:
        if key != "messages":
            assert len(key) <= len("role_") + digest._MAX_ROLE_CHARS


def test_a_truncated_role_is_reported_rather_than_silently_merged():
    """Truncation is where two distinct roles can collide into one key and merge
    their tallies -- a digest that lies about the candidate, not one that is
    merely narrow. Same convention as `keys_truncated` and
    `skeleton_nodes_truncated`: the fact is recorded where it happens.

    Both roles here differ only past the cap, so the merge is visible in the
    counts as well as in the flag.
    """
    role_a = "a" * digest._MAX_ROLE_CHARS + "-planner"
    role_b = "a" * digest._MAX_ROLE_CHARS + "-critic"
    payload = [{"role": role_a, "content": "x"}, {"role": role_b, "content": "y"}]
    result = digest.digest_for_payload(payload, "trace", body_chars=2000)
    assert result["role_keys_truncated"] is True
    merged = f"role_{'a' * digest._MAX_ROLE_CHARS}"
    assert result["element_counts"][merged] == 2


def test_an_untruncated_role_says_so_rather_than_omitting_the_flag():
    """Unconditional, for the reason `keys_truncated` is: a flag a reader only
    sees when it is true cannot be told apart from a digest written before the
    flag existed. tau2's longest role is `assistant` at 9 characters, so False is
    what every real trajectory reports."""
    result = digest.digest_for_payload(_TRAJECTORY, "trace", body_chars=2000)
    assert result["role_keys_truncated"] is False


def test_a_role_exactly_at_the_cap_is_not_reported_truncated():
    """The comparison is `>`, and a role landing exactly on the cap loses no
    characters -- so reporting it truncated would be the false positive
    `skeleton_nodes_truncated` was rewritten to avoid. A negative one character
    past the cap cannot see an off-by-one edit; this can."""
    at_cap = "r" * digest._MAX_ROLE_CHARS
    past_cap = "r" * (digest._MAX_ROLE_CHARS + 1)
    at = digest.digest_for_payload(
        [{"role": at_cap, "content": "x"}, {"role": "user", "content": "y"}],
        "trace",
        body_chars=2000,
    )
    past = digest.digest_for_payload(
        [{"role": past_cap, "content": "x"}, {"role": "user", "content": "y"}],
        "trace",
        body_chars=2000,
    )
    assert at["role_keys_truncated"] is False
    assert past["role_keys_truncated"] is True


def test_a_dict_shaped_trace_digest_grows_no_role_flag():
    """The flag is the message-list producer's own. A dict-shaped capture has no
    role keys, so it must not grow a truncation flag about ones it cannot have --
    the same rule that keeps `skeleton_nodes_truncated` off a trace digest."""
    result = digest.digest_for_payload({"trace_id": "t", "spans": []}, "trace", body_chars=2000)
    assert "role_keys_truncated" not in result


def test_a_long_name_is_bounded_in_characters_and_not_only_in_entries():
    """`_MAX_NAMES` caps the list at 64 *entries* and bounded nothing about their
    width, so one verbose name made the row larger than the slice that has to
    hold it. Measured before this bound, end-to-end: a two-message conversation
    whose `name` values are 40,000 characters each surveyed to `1 candidate
    row(s) exceed one slice of 65536 bytes: chat-json at 80549 bytes` -- exit 2,
    refusing the whole corpus, where the same file digested as a skeleton is 433
    bytes.
    """
    payload = [
        {"role": "user", "content": "x", "name": "t" * 40_000},
        {"role": "assistant", "content": "y", "name": "u" * 40_000},
    ]
    result = digest.digest_for_payload(payload, "trace", body_chars=2000)
    assert result["names"]
    assert all(len(name) <= digest._MAX_NAME_CHARS for name in result["names"])


def test_a_bounded_name_keeps_the_whole_row_inside_one_slice():
    """The bound exists for the row, not for the field, so this asserts the thing
    survey actually refuses on rather than only the field it refuses because of.
    `_MAX_NAMES` * `_MAX_NAME_CHARS` is the field's worst case; both together are
    what keep it a fraction of a slice.
    """
    payload = [
        {"role": "user", "content": "x", "name": f"tool_{i}_" + "z" * 40_000} for i in range(80)
    ]
    result = digest.digest_for_payload(payload, "trace", body_chars=2000)
    assert len(json.dumps(result).encode("utf-8")) < slices.DEFAULT_SLICE_BYTES


def test_a_truncated_name_is_reported_rather_than_silently_dropped():
    """Truncation is where two distinct names can collapse into one entry -- `names`
    is collected into a set, so the sorted list loses one. That is a digest that
    lies about the candidate rather than one that is merely narrow, which is the
    same argument `role_keys_truncated` carries, and the collision is a
    possibility of truncating into a set rather than a certainty: two names that
    differ within the cap keep both entries.
    """
    a = "t" * digest._MAX_NAME_CHARS + "-planner"
    b = "t" * digest._MAX_NAME_CHARS + "-critic"
    result = digest.digest_for_payload(
        [{"role": "user", "content": "x", "name": a}, {"role": "user", "content": "y", "name": b}],
        "trace",
        body_chars=2000,
    )
    assert result["names_truncated"] is True
    assert result["names"] == ["t" * digest._MAX_NAME_CHARS]


def test_an_untruncated_name_says_so_rather_than_omitting_the_flag():
    """Unconditional beside the field it describes, for the reason
    `role_keys_truncated` is: a flag a reader only sees when it is true cannot be
    told apart from a digest written before the flag existed. The longest name in
    any corpus on this pod is `query_tickets.find_tickets` at 26 characters, so
    False is what every real candidate reports.
    """
    result = digest.digest_for_payload(_TRAJECTORY, "trace", body_chars=2000)
    assert result["names_truncated"] is False


def test_a_name_exactly_at_the_cap_is_not_reported_truncated():
    """The comparison is `>`, and a name landing exactly on the cap loses no
    characters -- so reporting it truncated would be the false positive
    `skeleton_nodes_truncated` was rewritten to avoid. A negative one character
    past the cap cannot see an off-by-one edit; this can."""
    at_cap = "n" * digest._MAX_NAME_CHARS
    past_cap = "n" * (digest._MAX_NAME_CHARS + 1)
    # Two messages, because `is_message_list` refuses a one-element list: a single
    # role-tagged element is a shape common in configuration, and this producer is
    # only reached for a conversation.
    at = digest.digest_for_payload(
        [{"role": "user", "content": "x", "name": at_cap}, {"role": "assistant", "content": "y"}],
        "trace",
        body_chars=2000,
    )
    past = digest.digest_for_payload(
        [{"role": "user", "content": "x", "name": past_cap}, {"role": "assistant", "content": "y"}],
        "trace",
        body_chars=2000,
    )
    assert at["names_truncated"] is False
    assert past["names_truncated"] is True


def test_both_trace_producers_bound_the_names_they_collect():
    """`_collect_names` is shared: the dict-shaped producer calls it once on the
    payload and the message-list producer calls it per message. The defect was in
    the shared collector, so a fix that reached only the message-list route would
    leave the dict-shaped capture -- which has always been exposed -- unbounded.
    """
    long_name = "w" * 40_000
    from_dict = digest.digest_for_payload(
        {"trace_id": "t", "spans": [{"name": long_name}]}, "trace", body_chars=2000
    )
    from_messages = digest.digest_for_payload(
        [
            {"role": "user", "content": "x", "name": long_name},
            {"role": "assistant", "content": "y"},
        ],
        "trace",
        body_chars=2000,
    )
    for result in (from_dict, from_messages):
        assert result["names"] == ["w" * digest._MAX_NAME_CHARS]
        assert result["names_truncated"] is True


def test_a_digest_with_no_names_grows_no_names_flag():
    """The flag is a sibling of the field, not of the digest. `names` is emitted
    only when something was collected, so a candidate carrying none must not grow
    a truncation flag about names it does not have -- the same rule that keeps
    `role_keys_truncated` off a dict-shaped trace."""
    result = digest.digest_for_payload({"trace_id": "t", "spans": []}, "trace", body_chars=2000)
    assert "names" not in result
    assert "names_truncated" not in result


def test_a_message_list_classified_other_still_digests_to_a_skeleton():
    """The producer is reached on `kind == "trace"` only. A message list that some
    other path classified `other` keeps the skeleton it had, so this change cannot
    alter a candidate the classifier did not move."""
    result = digest.digest_for_payload(_TRAJECTORY, "other", body_chars=2000)
    assert "skeleton" in result
    assert "heuristics_fired" not in result
