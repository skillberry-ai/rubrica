"""The tool-name survival predicate, and the synthesis it guards."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from rubrica.cli import main
from rubrica.interfaces import LAYER, TOOL_NAME, TOOL_NAME_PATTERN, synthesise
from rubrica.paths import list_json
from rubrica.validate import validate_artifact
from tests.toy import build_toy_run, toy_claims

_SCHEMA_DIR = Path(__file__).parents[2] / "src/rubrica/schema"


def test_the_predicate_admits_a_name_the_harness_returns_unchanged():
    assert TOOL_NAME.match("query_tickets")
    assert TOOL_NAME.match("a")
    assert TOOL_NAME.match("a" * 64)
    assert TOOL_NAME.match("get-ticket_2")


def test_the_predicate_rejects_a_leading_separator_the_character_class_admits():
    """The case the character class alone waves through, and the reason this
    predicate is not `^[a-zA-Z0-9_-]{1,64}$`.

    sanitize_operation_id replaces out-of-class characters with `_`, caps at 64,
    *and* strips leading and trailing `_` and `-` -- twice, before and after the
    cap. So `_query_tickets` matches the character class and is still rewritten to
    `query_tickets`, which is a silently broken tool contract: the agent calls a
    name the simulator does not serve. This is the regression test for that.
    """
    assert not TOOL_NAME.match("_query_tickets")
    assert not TOOL_NAME.match("query_tickets_")
    assert not TOOL_NAME.match("-query")
    assert not TOOL_NAME.match("query-")
    assert not TOOL_NAME.match("_")


def test_the_predicate_rejects_an_out_of_class_character_and_an_over_long_name():
    assert not TOOL_NAME.match("query/tickets")
    assert not TOOL_NAME.match("query tickets")
    assert not TOOL_NAME.match("a" * 65)


def test_the_schema_pattern_and_the_python_constant_are_the_same_predicate():
    """Two homes for one rule, and a test instead of an import.

    A JSON Schema cannot import a Python constant, so the pattern is stated twice
    -- once in interface-0.1.json, once in interfaces.py. That is a genuine
    duplication, and this is what stops it becoming a drift: change one and this
    goes red naming both.
    """
    schema = json.loads((_SCHEMA_DIR / "interface-0.1.json").read_text(encoding="utf-8"))
    pattern = schema["$defs"]["operation"]["properties"]["operationId"]["pattern"]
    assert pattern == TOOL_NAME_PATTERN, (
        f"interface-0.1.json pins {pattern!r} and interfaces.py pins "
        f"{TOOL_NAME_PATTERN!r}; they must be the same predicate"
    )
    # Compiled as well as compared: a pattern that is equal but not valid Python
    # regex would pass the comparison and fail at first use.
    assert re.compile(pattern).match("query_tickets")


# -- synthesis: the deterministic stage --------------------------------------


def test_the_toy_run_synthesises_one_document_per_service(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-services")
    written, findings = synthesise(run)
    assert findings == []
    assert written == [run.interface("svc-tickets")]
    doc = json.loads(written[0].read_text(encoding="utf-8"))
    assert doc["openapi"] == "3.1.0"
    assert list(doc["paths"]) == ["/query_tickets"]
    operation = doc["paths"]["/query_tickets"]["post"]
    assert operation["operationId"] == "query_tickets"
    # The contract, preserved: the request body is the claim's payload, not a
    # schema derived from it. Compared against the claim rather than a literal, so
    # a fixture edit changes both sides at once.
    payload = next(c for c in toy_claims("api-json")["claims"] if c["id"] == "clm-api-010")[
        "payload"
    ]
    assert operation["requestBody"]["content"]["application/json"]["schema"] == payload
    assert doc["x-rubrica"]["service_id"] == "svc-tickets"
    assert validate_artifact(written[0], "interface") == []


def test_two_runs_produce_byte_identical_documents(tmp_path):
    """The reason this stage is code. If synthesis varied, a difference in an
    emitted lab could no longer be attributed to a stage -- the property the whole
    measurement rests on.

    Byte equality, not structural. Key order is *not* what this pins:
    artifacts.canonical_bytes sorts keys, so the order `_document` builds them in
    is normalised away on write. What it pins is everything canonicalisation does
    not decide for us -- the separators and indentation write_json chooses, and the
    order of every *list* in the document, which sort_keys does not touch: `paths`
    iterates the service's tools and `x-rubrica.tools` copies that same array, so a
    synthesis that visited tools in a set's order would fail here.
    """
    a = build_toy_run(tmp_path / "a", upto="reconcile-services")
    b = build_toy_run(tmp_path / "b", upto="reconcile-services")
    synthesise(a)
    synthesise(b)
    assert a.interface("svc-tickets").read_bytes() == b.interface("svc-tickets").read_bytes()


def test_the_request_body_is_the_named_schema_claim_not_the_first_one(tmp_path):
    """The disagreement ruling, made mechanical.

    `schema_claim` exists for exactly one situation: two inputs declare one tool
    and give different input schemas. The pass records the disagreement in prose
    and *names* the claim whose payload wins, because a rule for picking a winner
    would bury a judgment in code. This is the half a test can check -- that
    synthesis honours the name.

    Rigged so both plausible wrong implementations fail: the losing claim is first
    in the tool's `claims` array *and* lives in the claims file that sorts first
    (`api-json.json` before `trace-json.json`), so neither first-listed nor
    first-read produces the asserted payload.
    """
    run = build_toy_run(tmp_path, upto="reconcile-services")
    disagreeing = {
        "type": "object",
        "required": ["action", "queue"],
        "properties": {"action": {"type": "string"}, "queue": {"type": "string"}},
    }
    trace = json.loads(run.claims("trace-json").read_text(encoding="utf-8"))
    trace["claims"].append(
        {
            "id": "clm-trace-tool",
            "kind": "tool",
            "statement": "The trace shows query_tickets taking an action and a required queue",
            "evidence": [{"artifact_id": "trace-json", "locator": "#/steps/0/arguments"}],
            "confidence": "medium",
            "derivation": "stated",
            "payload": disagreeing,
        }
    )
    run.claims("trace-json").write_text(json.dumps(trace), encoding="utf-8")

    part = json.loads(run.services_part.read_text(encoding="utf-8"))
    tool = part["services"][0]["tools"][0]
    tool["claims"] = ["clm-api-010", "clm-trace-tool"]
    tool["schema_claim"] = "clm-trace-tool"
    tool["schema_disagreement"] = (
        "api.json makes queue optional; the trace shows it always sent. The trace "
        "is the observed call, so its schema is the one synthesised."
    )
    run.services_part.write_text(json.dumps(part), encoding="utf-8")

    written, findings = synthesise(run)
    assert findings == []
    doc = json.loads(written[0].read_text(encoding="utf-8"))
    schema = doc["paths"]["/query_tickets"]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]
    assert schema == disagreeing
    losing = next(c for c in toy_claims("api-json")["claims"] if c["id"] == "clm-api-010")
    assert schema != losing["payload"], "the first-listed claim's payload must not win"


def test_a_run_whose_target_declares_no_tools_writes_nothing_and_exits_clean(tmp_path, capsys):
    """`services: []` is an honest part, so an empty derivation is exit 0.

    `rb-reconcile-services`' refusal conditions instruct the pass to write an empty
    list rather than invent a service for a target whose corpus declares no tool,
    and this is the other half of that ruling: nothing to derive is not a failure to
    derive. Exit code *and* stdout, because the printed-path count is the signal
    `rb-orchestrate` branches on -- it must not run
    `validate --stage synthesise-interfaces` here, whose "produced no interface
    artifact" finding would accuse a correct run
    (test_the_interface_gate_over_a_run_with_no_services_names_the_run_root pins what
    that costs).

    The part is validated in the test rather than assumed legal: if
    `services-part-0.1.json` ever grew a `minItems`, the pass could no longer obey
    its own refusal condition and this whole case would be unreachable.
    """
    run = build_toy_run(tmp_path, upto="reconcile-services")
    part = json.loads(run.services_part.read_text(encoding="utf-8"))
    part["services"] = []
    for row in part["inputs_seen"]:
        row.update(own_kind_total=0, cited=0, dropped=0)
    run.services_part.write_text(json.dumps(part), encoding="utf-8")
    assert validate_artifact(run.services_part, "services-part") == []

    code = main(["synthesise-interfaces", "--run", str(run.root)])
    captured = capsys.readouterr()
    assert (code, captured.out, captured.err) == (0, "", "")
    assert list_json(run.interfaces_dir) == []


def test_a_missing_services_part_is_a_repairable_finding(tmp_path):
    """Exit 1, not 2: re-dispatching reconcile-services repairs it, which is
    exactly what a 1 promises the orchestrator.
    """
    run = build_toy_run(tmp_path, upto="reconcile-gaps")
    assert not run.services_part.exists()
    written, findings = synthesise(run)
    assert written == []
    assert len(findings) == 1
    assert findings[0].artifact == run.services_part
    assert findings[0].layer == "interfaces"


def test_a_non_dict_services_part_names_that_part_and_nothing_else(tmp_path):
    """`["nope"]` rather than a truncation: a document that parses to a non-object
    reached `.get` and raised AttributeError in four measured places in this repo,
    each time surfacing as a fabricated `[internal]` finding against the run root
    -- a 1 naming the wrong artifact.
    """
    run = build_toy_run(tmp_path, upto="reconcile-services")
    run.services_part.write_text('["nope"]', encoding="utf-8")
    written, findings = synthesise(run)
    assert written == []
    assert [f.artifact for f in findings] == [run.services_part]
    assert {f.layer for f in findings} == {LAYER}


def test_a_services_key_that_is_not_an_array_names_that_key(tmp_path):
    """An object where an array belongs: the shape that reaches `enumerate` and
    iterates a dict's *keys*, so every later check would run against a string.
    """
    run = build_toy_run(tmp_path, upto="reconcile-services")
    part = json.loads(run.services_part.read_text(encoding="utf-8"))
    part["services"] = {"svc-tickets": {}}
    run.services_part.write_text(json.dumps(part), encoding="utf-8")
    written, findings = synthesise(run)
    assert written == []
    assert [(f.artifact, f.pointer) for f in findings] == [(run.services_part, "/services")]
    assert {f.layer for f in findings} == {LAYER}


def _rewrite_services(run, mutate):
    """Apply `mutate` to the parsed services part and write it back.

    A helper rather than four more copies of parse/mutate/dump: the four cases
    below differ only in the one value they break, and the repeated boilerplate is
    what made three of these branches easy to leave untested in the first place.
    """
    part = json.loads(run.services_part.read_text(encoding="utf-8"))
    mutate(part)
    run.services_part.write_text(json.dumps(part), encoding="utf-8")
    return part


def test_a_claims_file_that_is_not_an_object_names_that_file(tmp_path):
    """`["nope"]` in a claims file, not in the services part.

    The same shape as the services-part case, in the other loop, and it was
    untested: a document that parses to a list reached `.get("claims", [])` and
    raised AttributeError in four measured places in this repo. A claims file is
    `extract`'s output, so the finding names the file and re-dispatching that one
    input's extractor is the repair.
    """
    run = build_toy_run(tmp_path, upto="reconcile-services")
    run.claims("api-json").write_text('["nope"]', encoding="utf-8")
    written, findings = synthesise(run)
    assert written == []
    assert (findings[0].artifact, findings[0].message) == (
        run.claims("api-json"),
        "claims file is not a JSON object",
    )
    assert {f.layer for f in findings} == {LAYER}


def test_a_service_that_is_not_an_object_names_its_index(tmp_path):
    """A string where a service belongs, so the pointer is the only thing that can
    say which element is wrong -- there is no id to quote.
    """
    run = build_toy_run(tmp_path, upto="reconcile-services")
    _rewrite_services(run, lambda part: part["services"].insert(0, "nope"))
    written, findings = synthesise(run)
    assert written == []
    assert [(f.artifact, f.pointer, f.message) for f in findings] == [
        (run.services_part, "/services/0", "not an object")
    ]
    assert {f.layer for f in findings} == {LAYER}


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"query_tickets": {}}, "not an array"),
        ([], "empty"),
    ],
    ids=["mapping", "empty-list"],
)
def test_a_tools_value_that_is_wrong_and_one_that_is_empty_get_different_messages(
    tmp_path, value, message
):
    """Two defects, two messages, and they used to be one.

    `not isinstance(tools, list) or not tools` reported `{"query_tickets": {}}` as
    *empty*, so a repair prompt handed that finding would have been told something
    untrue about its own output. Parametrized rather than split, because what is
    being asserted is precisely that the two inputs do not produce the same line.
    """
    run = build_toy_run(tmp_path, upto="reconcile-services")
    _rewrite_services(run, lambda part: part["services"][0].__setitem__("tools", value))
    written, findings = synthesise(run)
    assert written == []
    assert [(f.artifact, f.pointer, f.message) for f in findings] == [
        (run.services_part, "/services/0/tools", message)
    ]
    assert {f.layer for f in findings} == {LAYER}


def test_a_tool_that_is_not_an_object_names_its_index_within_the_service(tmp_path):
    """The tool-level twin of the service-level case: the pointer carries both
    indices, because a service with several tools gives a repair nothing else to go
    on -- `name` is exactly what is missing.
    """
    run = build_toy_run(tmp_path, upto="reconcile-services")
    _rewrite_services(run, lambda part: part["services"][0]["tools"].insert(0, "nope"))
    written, findings = synthesise(run)
    assert written == []
    assert (run.services_part, "/services/0/tools/0", "not an object") in [
        (f.artifact, f.pointer, f.message) for f in findings
    ]
    assert {f.layer for f in findings} == {LAYER}


def test_an_unsafe_service_id_is_a_finding_and_never_a_path(tmp_path):
    """is_safe_segment rather than safe_segment: a bad id in a stage's own output
    is repairable, and joining through safe_segment would raise UnsafeSegment,
    which cli.py maps to exit 2 -- unrepairable by construction.
    """
    run = build_toy_run(tmp_path, upto="reconcile-services")
    part = json.loads(run.services_part.read_text(encoding="utf-8"))
    part["services"][0]["id"] = "../../etc/passwd"
    run.services_part.write_text(json.dumps(part), encoding="utf-8")
    written, findings = synthesise(run)
    assert written == []
    assert findings and all(f.artifact == run.services_part for f in findings)
    assert {f.layer for f in findings} == {LAYER}
    assert not (run.root.parent.parent / "etc").exists()


def test_a_tool_name_that_would_not_survive_sanitisation_is_a_finding(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-services")
    part = json.loads(run.services_part.read_text(encoding="utf-8"))
    part["services"][0]["tools"][0]["name"] = "_query_tickets"
    run.services_part.write_text(json.dumps(part), encoding="utf-8")
    written, findings = synthesise(run)
    assert written == []
    assert any("_query_tickets" in f.message for f in findings)
    assert {f.layer for f in findings} == {LAYER}


def test_a_schema_claim_resolving_to_nothing_is_a_finding(tmp_path):
    run = build_toy_run(tmp_path, upto="reconcile-services")
    part = json.loads(run.services_part.read_text(encoding="utf-8"))
    part["services"][0]["tools"][0]["schema_claim"] = "clm-does-not-exist"
    run.services_part.write_text(json.dumps(part), encoding="utf-8")
    written, findings = synthesise(run)
    assert written == []
    assert any("clm-does-not-exist" in f.message for f in findings)
    assert {f.layer for f in findings} == {LAYER}


def test_a_malformed_claims_file_is_a_finding_against_that_file(tmp_path):
    """A 1 naming the right artifact. A claims file is `extract`'s output, so a
    malformed one is repairable by re-dispatching that one input's extractor --
    and the finding has to name the file, not the services part that cited it.
    """
    run = build_toy_run(tmp_path, upto="reconcile-services")
    run.claims("api-json").write_text("{ not json", encoding="utf-8")
    written, findings = synthesise(run)
    assert written == []
    assert run.claims("api-json") in [f.artifact for f in findings]
    assert {f.layer for f in findings} == {LAYER}


def test_an_unreadable_claims_file_raises_rather_than_becoming_a_finding(tmp_path):
    """chmod 000 on one claims file is a 2, and the malformed case above is the 1.

    The line is *content versus filesystem*, not which stage could rewrite the
    file, and cli.py's shared handler draws it in those words: a stage defect is
    malformed content -- ArtifactError, KeyError, UnsafeSegment -- while an OSError
    is the filesystem refusing, which no repair prompt can fix. So `read_json`'s
    PermissionError travels out of here untouched and becomes exit 2.

    Pinned because the tempting reading is the other one: `write_json` replaces
    atomically, so re-dispatching that input's extractor *would* in fact overwrite
    a mode-000 claims file, which makes "repairable" look like the deciding
    question. Following it here would make synthesis the only reader in the repo
    that answers differently from the others over the very same file -- `validate
    --stage extract` and `check-refs` both exit 2 on it -- and one command
    disagreeing with its neighbours about one file's exit code is worse than
    either answer.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path, upto="reconcile-services")
    target = run.claims("api-json")
    target.chmod(0o000)
    try:
        with pytest.raises(OSError) as caught:
            synthesise(run)
    finally:
        target.chmod(0o644)
    # Named, not just raised: cli.py prints `error: {exc}` on stderr, so the path
    # has to be in the exception or the operator is told only that something was
    # unreadable.
    assert str(target) in str(caught.value)


@pytest.mark.parametrize("populated", [False, True])
@pytest.mark.parametrize("mode", [0o000, 0o444])
def test_an_unwritable_interfaces_directory_is_exit_2_with_no_finding(
    tmp_path, capsys, mode, populated
):
    """The other half of the split, at the exit code rather than at the return value.

    Four cases because they raise in three different places, and a branch that
    turned any one of them into a `1` would spend the run's one repair attempt
    re-dispatching a prompt whose output was never the problem: at 0o000 the listing
    itself fails, at 0o444 over a directory that already holds a document the listing
    succeeds and `is_file()` on the child fails, and at 0o444 over an empty one both
    succeed and `write_json`'s mkstemp is what refuses. `write_json` mkdirs the
    parent, so reasoning about which call raises is not optional here.

    Asserted through `cli.main` rather than against `synthesise`: what must not
    happen is a finding line on stdout, and only the CLI can show that.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = build_toy_run(tmp_path, upto="reconcile-services")
    if populated:
        assert synthesise(run) == ([run.interface("svc-tickets")], [])
    else:
        run.interfaces_dir.mkdir(parents=True)
    run.interfaces_dir.chmod(mode)
    try:
        code = main(["synthesise-interfaces", "--run", str(run.root)])
    finally:
        run.interfaces_dir.chmod(0o755)
    captured = capsys.readouterr()
    assert code == 2, captured.out
    assert captured.out.strip() == "", "a filesystem problem must not print a finding line"
    assert captured.err.startswith("error: ")


def test_a_stale_document_from_a_previous_run_is_removed(tmp_path):
    """Synthesis owns the directory. A service renamed at gate 1 and re-synthesised
    would otherwise leave the old document behind, and refs.check_interfaces
    reports a document no service asked for -- a 1 against a run that is now
    correct. What this pins is the half of that pair the writer owns: the directory
    never carries a document no service asked for. The checker's half is measured
    in tests/unit/test_refs_services.py, over a rename through this same code.
    """
    run = build_toy_run(tmp_path, upto="reconcile-services")
    stale = run.interface("svc-gone")
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("{}", encoding="utf-8")
    written, findings = synthesise(run)
    assert findings == []
    assert not stale.exists()
    assert written == [run.interface("svc-tickets")]
