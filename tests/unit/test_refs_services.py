"""The layer-2 checks over 01-services.json and 01-interfaces/.

Each test mutates a real toy run rather than building a synthetic document, so the
negative case is reachable from a state the pipeline can actually produce. A check
whose failure no fixture can reach is not yet a guard.

Every predicate is measured in both directions here, not only in the report: the
mutation that must make it red, and beside it a meaning-preserving change -- a
reordered `services` array, a renamed service re-synthesised, a payload reformatted
without changing its parsed value -- that must leave it green. The whitespace case
is the one to watch: if it goes red, the comparison is over bytes rather than
decoded values and is wrong.
"""

from __future__ import annotations

import json

from rubrica.interfaces import synthesise
from rubrica.refs import check_all, check_interfaces, check_services
from tests.toy import build_toy_run


def _services(run):
    return json.loads(run.services_part.read_text(encoding="utf-8"))


def _rewrite(run, part):
    run.services_part.write_text(json.dumps(part), encoding="utf-8")


def _claims(run, artifact_id="api-json"):
    path = run.claims(artifact_id)
    return path, json.loads(path.read_text(encoding="utf-8"))


def _rewrite_claims(run, path, document, **dump):
    path.write_text(json.dumps(document, **dump), encoding="utf-8")


def _claim(document, claim_id):
    return next(c for c in document["claims"] if c["id"] == claim_id)


def _two_services(run):
    """A two-service, two-tool run, synthesised by the real code.

    The toy corpus declares one tool, so the array-order and multi-document paths
    are unreachable from it as built: reordering a one-element list is not a
    reorder, and one document cannot show a sibling being matched to the right
    service. The second tool claim cites the same region of the same input as the
    first, which is legitimate -- two claims may name one locator -- and keeps the
    payload check comparable for both.

    This leaves `01-services.json`'s own `inputs_seen` accounting one claim short,
    which is check_input_dispositions' finding and not these two checkers'. The
    tests below call check_services and check_interfaces directly, so that
    disagreement is out of frame rather than tolerated.
    """
    path, document = _claims(run)
    second = json.loads(json.dumps(_claim(document, "clm-api-010")))
    second["id"] = "clm-api-011"
    second["statement"] = "The target declares a second tool for closing tickets"
    document["claims"].append(second)
    _rewrite_claims(run, path, document)

    part = _services(run)
    billing = json.loads(json.dumps(part["services"][0]))
    billing["id"] = "svc-billing"
    billing["tools"] = [
        {"name": "close_ticket", "claims": ["clm-api-011"], "schema_claim": "clm-api-011"}
    ]
    part["services"].append(billing)
    _rewrite(run, part)
    _, findings = synthesise(run)
    assert findings == [], findings
    return part


def test_a_clean_run_reports_nothing(tmp_path):
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    assert check_services(run) == []
    assert check_interfaces(run) == []


def test_neither_checker_speaks_before_the_documents_exist(tmp_path):
    """The state between the two stages: the part written, nothing synthesised.

    check_interfaces must be silent here. Reporting "no document" for every
    service on a run whose only property is that the next stage has not run yet
    would make reconcile-services' own check-refs gate exit 1, and the
    orchestrator would spend its single repair attempt re-dispatching a pass that
    cannot fix it. This is the guard check_verdicts and check_contradiction_parts
    each have for the same reason.
    """
    run = build_toy_run(tmp_path, upto="reconcile-services")
    assert not run.interfaces_dir.exists()
    assert check_interfaces(run) == []
    assert check_services(run) == [], "the part alone is already checkable, and is clean"


def test_a_claim_id_that_resolves_to_nothing_is_reported(tmp_path):
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    part = _services(run)
    part["services"][0]["tools"][0]["claims"] = ["clm-nope"]
    part["services"][0]["tools"][0]["schema_claim"] = "clm-nope"
    _rewrite(run, part)
    findings = check_services(run)
    assert findings
    assert all(f.artifact == run.services_part for f in findings)
    assert any("clm-nope" in f.message for f in findings)


def test_a_claim_of_the_wrong_kind_is_reported(tmp_path):
    """Resolution is not enough: a `capability` claim resolves and carries no
    input schema, so a tool citing one would synthesise a request body out of
    nothing.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    part = _services(run)
    part["services"][0]["tools"][0]["claims"] = ["clm-api-001"]
    part["services"][0]["tools"][0]["schema_claim"] = "clm-api-001"
    _rewrite(run, part)
    assert any("clm-api-001" in f.message for f in check_services(run))


def test_a_wrong_kind_schema_claim_synthesis_accepts_is_still_reported(tmp_path):
    """The gap only this check closes.

    interfaces.synthesise indexes payloads from claims of *every* kind, so a
    `schema_claim` naming a non-tool claim that happens to carry a payload becomes
    a request body with no complaint from the producer. Nothing else in the
    pipeline says so.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    path, document = _claims(run)
    _claim(document, "clm-api-001")["payload"] = {"type": "string"}
    _rewrite_claims(run, path, document)
    part = _services(run)
    part["services"][0]["tools"][0]["claims"] = ["clm-api-001"]
    part["services"][0]["tools"][0]["schema_claim"] = "clm-api-001"
    _rewrite(run, part)

    _, synthesis_findings = synthesise(run)
    assert synthesis_findings == [], "the producer accepts it, which is why this check exists"
    assert any(
        "clm-api-001" in f.message and "capability" in f.message for f in check_services(run)
    )


def test_a_schema_claim_from_outside_its_own_tool_is_reported(tmp_path):
    """`schema_claim` names the winner among the tool's *own* claims. One naming a
    claim the tool does not cite is a request body with no recorded evidence that
    it belongs to this tool at all.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    part = _services(run)
    part["services"][0]["tools"][0]["schema_claim"] = "clm-notes-001"
    _rewrite(run, part)
    findings = check_services(run)
    assert any("clm-notes-001" in f.message for f in findings)
    assert all(f.artifact == run.services_part for f in findings)


def test_a_tool_claim_in_no_service_is_reported(tmp_path):
    """The partition, from the orphan side. A tool nobody can simulate is a hole in
    the description, and the pass's own accounting is what should have recorded it.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    part = _services(run)
    part["services"] = []
    _rewrite(run, part)
    assert any("clm-api-010" in f.message for f in check_services(run))


def test_a_tool_claim_in_two_services_is_reported(tmp_path):
    """The partition, from the duplicate side: two simulators serving one tool
    name, which is a database the agent sees two conflicting views of.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    part = _services(run)
    part["services"].append(json.loads(json.dumps(part["services"][0])))
    part["services"][1]["id"] = "svc-tickets-again"
    _rewrite(run, part)
    assert any("clm-api-010" in f.message for f in check_services(run))


def test_one_tool_cited_twice_inside_one_service_is_not_a_duplicate(tmp_path):
    """The other direction of the partition, and the reason it counts services
    rather than citations: two tools of one service sharing a schema claim are one
    simulator with one database, which is not the hazard this reports.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    part = _services(run)
    tool = part["services"][0]["tools"][0]
    part["services"][0]["tools"].append({**tool, "name": "query_tickets_readonly"})
    _rewrite(run, part)
    assert check_services(run) == []


def test_a_payload_edited_away_from_its_input_is_reported(tmp_path):
    """The check that makes a prompt's byte-for-byte transcription falsifiable.

    Structural identity between a payload and the document region its locator
    names -- not whether the claim *supports* anything, which is semantic and the
    hole layer 2 is forbidden to paper over.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    path, document = _claims(run)
    del _claim(document, "clm-api-010")["payload"]["properties"]["ticket_id"]
    _rewrite_claims(run, path, document)
    findings = check_services(run)
    assert any("clm-api-010" in f.message for f in findings)
    assert any(f.artifact == path for f in findings)


def test_a_payload_reformatted_without_changing_its_value_stays_clean(tmp_path):
    """The mirror of the test above, and the one that pins *what* is compared.

    Re-indented, re-ordered keys, non-default separators: every byte of the
    payload changes and its decoded value does not. A comparison over bytes would
    go red here, and would be reporting a formatting choice as a fidelity defect.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    path, document = _claims(run)
    payload = _claim(document, "clm-api-010")["payload"]
    _claim(document, "clm-api-010")["payload"] = {
        key: payload[key] for key in reversed(list(payload))
    }
    _rewrite_claims(run, path, document, indent=4, sort_keys=False, separators=(" ,", " : "))
    assert path.read_text(encoding="utf-8") != run.claims("notes-md").read_text(encoding="utf-8")
    assert check_services(run) == []


def test_a_locator_that_resolves_to_nothing_is_reported(tmp_path):
    """A pointer naming a region the input does not have. Reported rather than
    passed over, because silence here would let a fabricated payload through
    behind a fabricated locator -- which is the whole property this check exists
    to make observable.

    Asserted on the pointer as well as the message, and measurably not for
    tidiness: with this clause disabled the comparison below still fires -- UNSET
    is not equal to any payload -- and its message quotes the same locator, so a
    substring assertion alone stayed green over a checker that had lost this
    branch entirely.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    path, document = _claims(run)
    _claim(document, "clm-api-010")["evidence"][0]["locator"] = "#/tools/7/input_schema"
    _rewrite_claims(run, path, document)
    findings = check_services(run)
    assert any(
        f.artifact == path
        and f.pointer.endswith("/evidence/0/locator")
        and "#/tools/7/input_schema" in f.message
        for f in findings
    ), findings


def test_a_heading_anchor_locator_is_not_compared(tmp_path):
    """Locators come in two shapes in this project, and only one is comparable.

    `#/tools/0/input_schema` is a JSON pointer; `#operator-notes` is a markdown
    heading anchor. resolve_pointer *raises* on the second, so an unguarded
    comparison would leave an exception escaping as one `[internal]` finding
    naming the run root. A structural non-comparison is not evidence of a defect,
    so this says nothing -- demonstrated by mutating the payload as well, which
    the pointer locator above reports and this one does not.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    path, document = _claims(run)
    claim = _claim(document, "clm-api-010")
    claim["evidence"][0] = {"artifact_id": "notes-md", "locator": "#operator-notes"}
    del claim["payload"]["properties"]["ticket_id"]
    _rewrite_claims(run, path, document)
    assert check_services(run) == []


def test_a_non_json_input_is_not_compared(tmp_path):
    """The same silence for the other half of the pair: a pointer is only
    resolvable against a document that parses. notes.md is registered input bytes
    that are not JSON at all, and an unreadable or unparseable input is
    check_inputs' and check_readable's finding, never this one's.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    path, document = _claims(run)
    claim = _claim(document, "clm-api-010")
    claim["evidence"][0] = {"artifact_id": "notes-md", "locator": "#/tools/0/input_schema"}
    del claim["payload"]["properties"]["ticket_id"]
    _rewrite_claims(run, path, document)
    assert check_services(run) == []


def test_a_missing_document_and_an_extra_one_are_both_reported(tmp_path):
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    run.interface("svc-tickets").unlink()
    assert any("svc-tickets" in f.message for f in check_interfaces(run))

    run = build_toy_run(tmp_path / "second", upto="synthesise-interfaces")
    extra = run.interfaces_dir / "svc-nobody.json"
    extra.write_text("{}", encoding="utf-8")
    findings = check_interfaces(run)
    assert any(f.artifact == extra for f in findings)


def test_an_unreadable_document_is_not_reported_as_a_missing_one(tmp_path):
    """The wrong-artifact rule at the one place these two checkers could break it.

    A truncated document is present, so reporting "no document" against
    01-services.json would send the repair at the grouping when the file that
    will not parse is the one check_readable already names.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    run.interface("svc-tickets").write_text("{ not json", encoding="utf-8")
    assert check_interfaces(run) == []


def test_an_operation_id_that_no_longer_matches_its_tool_name_is_reported(tmp_path):
    """Contract preservation, made mechanical. This is the check the rest of the
    lab design rests on: the substitution is invisible to the agent's reasoning
    only if the name it calls is the name the simulator serves.

    The needle is delimited. `"query_ticket" in message` is a substring of
    `query_tickets` and was satisfied by either half of the difference, so it
    stayed green over a checker that had lost one of the two directions --
    measured, by disabling each in turn.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    path = run.interface("svc-tickets")
    document = json.loads(path.read_text(encoding="utf-8"))
    document["paths"]["/query_tickets"]["post"]["operationId"] = "query_ticket"
    path.write_text(json.dumps(document), encoding="utf-8")
    findings = check_interfaces(run)
    assert any("'query_ticket'" in f.message for f in findings), findings
    assert all(f.artifact == path for f in findings)


def test_the_difference_is_named_in_both_directions(tmp_path):
    """A rename is two defects, not one: a tool with no operation and an operation
    with no tool. A human reading one half would rename the wrong side back.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    path = run.interface("svc-tickets")
    document = json.loads(path.read_text(encoding="utf-8"))
    document["paths"]["/query_tickets"]["post"]["operationId"] = "query_ticket"
    path.write_text(json.dumps(document), encoding="utf-8")
    messages = " ".join(f.message for f in check_interfaces(run))
    assert "query_ticket'" in messages, messages
    assert "query_tickets'" in messages, messages


def test_an_operation_moved_to_another_method_still_counts(tmp_path):
    """The walk, rather than the fixed /paths/<name>/post this project writes.

    A document hand-corrected at gate 1 reaches check-refs without passing through
    synthesis again, and reading only `post` would report a moved operation as
    missing -- a finding naming a defect that is not the one there.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    path = run.interface("svc-tickets")
    document = json.loads(path.read_text(encoding="utf-8"))
    document["paths"]["/query_tickets"] = {"put": document["paths"]["/query_tickets"]["post"]}
    path.write_text(json.dumps(document), encoding="utf-8")
    assert check_interfaces(run) == []


def test_a_tool_name_that_would_not_survive_sanitisation_is_reported(tmp_path):
    """Reported here as well as refused in synthesise(), and not redundantly: a
    document hand-corrected at gate 1 reaches check-refs without passing through
    synthesis again.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    part = _services(run)
    part["services"][0]["tools"][0]["name"] = "query_tickets_"
    _rewrite(run, part)
    assert any("query_tickets_" in f.message for f in check_services(run))


def test_an_unreadable_claims_file_does_not_fabricate_findings(tmp_path):
    """The rule learned the hard way in this repo: check-refs over an unreadable
    01-claims/ once reported four fabricated `no such claim` findings against a
    correct world model. An unreadable input is check_readable's finding; these two
    checkers must name it or say nothing, never blame the services part for it.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    (run.claims_dir / "api-json.json").write_text("{ not json", encoding="utf-8")
    findings = check_services(run)
    assert all(f.artifact != run.services_part for f in findings), (
        f"blamed the services part for an unreadable claims file: {findings}"
    )
    assert findings == [], findings


def test_a_claims_file_carrying_no_claims_key_is_treated_as_absent(tmp_path):
    """The third shape, which is neither unreadable nor a non-object: valid JSON,
    a dict, and no `claims` key. check_readable cannot see it and _claim_index
    raises KeyError on it, and *measured before the guard*, this checker reported
    `no claim in 01-claims/ has id clm-api-010` against a services part that had
    not changed -- the fabricated-finding class, from a shape the readable check
    passes.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    (run.claims_dir / "api-json.json").write_text('{"schema_version": "0.1"}', encoding="utf-8")
    assert check_services(run) == []


def test_a_reordered_services_array_changes_nothing(tmp_path):
    """Meaning-preserving, for the partition and the document matching alike.

    Array order in the part is what byte-identity of the *documents* rests on, and
    is not something either checker may have an opinion about: a human who moved
    two services at gate 1 has changed nothing about the grouping.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    part = _two_services(run)
    assert check_services(run) == []
    assert check_interfaces(run) == []

    part["services"].reverse()
    _rewrite(run, part)
    assert check_services(run) == []
    assert check_interfaces(run) == []


def test_check_all_reaches_both_checkers(tmp_path):
    """A checker nobody registered is a checker nobody runs, and `check-refs` is
    the only caller the orchestrator has.

    One mutation reaches both: a tool renamed in the part and not re-synthesised
    fails the sanitisation clause against 01-services.json *and* leaves the
    document serving a name the part no longer declares.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    assert check_all(run) == [], "the baseline this state is measured against"
    part = _services(run)
    part["services"][0]["tools"][0]["name"] = "query_tickets_"
    _rewrite(run, part)
    artifacts = {f.artifact for f in check_all(run)}
    assert run.services_part in artifacts, artifacts
    assert run.interface("svc-tickets") in artifacts, artifacts


def test_a_renamed_service_re_synthesised_stays_clean(tmp_path):
    """The rename gate 1 exists to allow, through the real synthesis. Nothing may
    hold the run to the old name: the document's path is derived from the id, and
    synthesis owns the directory, so the stale document is gone.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    part = _services(run)
    part["services"][0]["id"] = "svc-support"
    _rewrite(run, part)
    written, findings = synthesise(run)
    assert findings == [], findings
    assert written == [run.interface("svc-support")]
    assert check_services(run) == []
    assert check_interfaces(run) == []
