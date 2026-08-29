"""One service's OpenAPI document, derived from the tool contract it must preserve.

Code rather than a prompt, on `emit`'s argument: the document is a pure function
of the tool contract, so two runs with identical groupings must produce
byte-identical documents. Otherwise a difference in an emitted lab can no longer
be attributed to a stage, which is the property the whole measurement rests on.
"""

from __future__ import annotations

import re
from pathlib import Path

from rubrica.artifacts import ArtifactError, read_json, write_json
from rubrica.findings import Finding
from rubrica.paths import RunPaths, is_safe_segment, list_json

# The predicate a tool name must satisfy for the harness to return it unchanged,
# which is what "the agent's tool contract is preserved" reduces to.
#
# NOT the harness's character class. simulation_harness.openapi.parser's
# sanitize_operation_id replaces every character outside [a-zA-Z0-9_-] with `_`,
# caps the result at 64, *and* strips leading and trailing `_` and `-` -- twice,
# once before the cap and once after. So `_query_tickets` matches the character
# class and is still rewritten to `query_tickets`: the agent would call a name the
# simulator does not serve, and nothing downstream would say so. Hence the
# anchored first and last character.
#
# Restated here rather than imported, because Rubrica takes no dependency on
# simulation-harness -- whether the harness accepts a document is the harness's
# test, not ours. The cost is that the two can drift, and the mirror of this
# constant in interface-0.1.json is held equal to it by
# tests/unit/test_interfaces.py.
TOOL_NAME_PATTERN = r"\A[a-zA-Z0-9](?:[a-zA-Z0-9_-]{0,62}[a-zA-Z0-9])?\Z"
TOOL_NAME = re.compile(TOOL_NAME_PATTERN)

# This module's Finding.layer. Distinct from "refs" for the reason "reconcile" and
# "rounds" are: refs checks a run someone may still be building, while this names
# the reason one command produced no output.
LAYER = "interfaces"


def _document(service: dict, payloads: dict[str, dict]) -> dict:
    """One service's OpenAPI document.

    The carrier convention is fixed rather than derived: method `post`, path
    `/<tool name>`, `operationId` the tool name. Only `operationId` is
    contractually significant -- it is what the harness turns into the MCP tool
    name -- so path and method carry no information and are chosen to be stable.
    Deriving them from the tool name would give a reader a marginally prettier
    document and this project a second thing to keep byte-stable.

    No `responses`. The harness's inline_schema_evidence exists for tool-style
    specs that declare no components.schemas and feeds request bodies as entity
    evidence, so a request-only document is its intended input. Inferring
    responses needs observed tool results, which is the step above this one.

    Key order here is *not* load-bearing: artifacts.canonical_bytes writes with
    sort_keys, so the order these dicts are built in is normalised away. List
    order is what byte-identity actually rests on, and both lists below are
    `service["tools"]` in the order the pass wrote it.
    """
    paths: dict[str, dict] = {}
    for tool in service["tools"]:
        name = tool["name"]
        paths[f"/{name}"] = {
            "post": {
                "operationId": name,
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": payloads[tool["schema_claim"]]}},
                },
            }
        }
    return {
        "openapi": "3.1.0",
        "info": {"title": service["id"], "version": "0.1.0"},
        "paths": paths,
        # Provenance travels in the document rather than beside it, because the
        # document is what a human at gate 1 reads and what a later step hands the
        # harness. `x-` keeps it a legal OpenAPI extension.
        "x-rubrica": {
            "service_id": service["id"],
            "tools": [dict(tool) for tool in service["tools"]],
        },
    }


def synthesise(run: RunPaths) -> tuple[list[Path], list[Finding]]:
    """Write one OpenAPI document per service, or report why none can be written.

    All-or-nothing, and deliberately: a partial directory is a state
    a layer-2 check over 01-interfaces/ would report as a missing document for a
    service whose only
    problem is that a *sibling* was malformed, which is a 1 naming the wrong
    artifact. So every service is checked before any file is written.

    An unwritable 01-interfaces/ is NOT caught here. It raises OSError, which
    cli.py maps to exit 2 -- correct, because no re-dispatch of any prompt fixes a
    directory permission, and a 1 there would spend the run's single repair
    attempt rewriting a prompt whose output was never the problem.
    """
    findings: list[Finding] = []

    try:
        part = read_json(run.services_part)
    except (ArtifactError, FileNotFoundError) as exc:
        # FileNotFoundError as well as ArtifactError: an absent part is the
        # ordinary shape of "reconcile-services has not run or failed", and it is
        # repairable by re-dispatching that pass -- so a finding, not an exception.
        return [], [Finding(run.services_part, LAYER, "", f"cannot read: {exc}")]

    if not isinstance(part, dict):
        # isinstance rather than a None check, for the reason reconcile.seal's
        # _UNREADABLE sentinel exists: `null` is legitimate JSON, and a document
        # that parses to a list reached `.get` and raised AttributeError.
        return [], [Finding(run.services_part, LAYER, "", "services part is not a JSON object")]

    services = part.get("services")
    if not isinstance(services, list):
        return [], [Finding(run.services_part, LAYER, "/services", "not an array")]

    # Claim id -> payload, over every claims file. Built once: a run with forty
    # inputs and four services would otherwise re-read every claims file per
    # service.
    payloads: dict[str, dict] = {}
    for path in list_json(run.claims_dir):
        try:
            document = read_json(path)
        except ArtifactError as exc:
            findings.append(Finding(path, LAYER, "", f"cannot read: {exc}"))
            continue
        if not isinstance(document, dict):
            findings.append(Finding(path, LAYER, "", "claims file is not a JSON object"))
            continue
        for claim in document.get("claims", []):
            if isinstance(claim, dict) and isinstance(claim.get("id"), str):
                payload = claim.get("payload")
                if isinstance(payload, dict):
                    payloads[claim["id"]] = payload

    planned: list[tuple[Path, dict]] = []
    for index, service in enumerate(services):
        pointer = f"/services/{index}"
        if not isinstance(service, dict):
            findings.append(Finding(run.services_part, LAYER, pointer, "not an object"))
            continue
        service_id = service.get("id")
        if not isinstance(service_id, str) or not is_safe_segment(service_id):
            # is_safe_segment, not safe_segment: see this module's tests. A bad id
            # in a stage's own output is repairable and owes a finding, whereas
            # safe_segment raises UnsafeSegment, which cli.py maps to exit 2.
            findings.append(
                Finding(
                    run.services_part,
                    LAYER,
                    f"{pointer}/id",
                    f"not usable as a filename: {service_id!r}",
                )
            )
            continue
        tools = service.get("tools")
        # Two defects, two messages. `not isinstance(tools, list) or not tools` in
        # one branch reported `{"a": 1}` as *empty*, which tells a repair prompt
        # something untrue about its own output -- the wrong-artifact rule's
        # sibling, one level down: a 1 has to name the right defect as well as the
        # right file.
        if not isinstance(tools, list):
            findings.append(Finding(run.services_part, LAYER, f"{pointer}/tools", "not an array"))
            continue
        if not tools:
            findings.append(Finding(run.services_part, LAYER, f"{pointer}/tools", "empty"))
            continue

        ok = True
        for j, tool in enumerate(tools):
            tool_pointer = f"{pointer}/tools/{j}"
            if not isinstance(tool, dict):
                findings.append(Finding(run.services_part, LAYER, tool_pointer, "not an object"))
                ok = False
                continue
            name = tool.get("name")
            if not isinstance(name, str) or not TOOL_NAME.match(name):
                findings.append(
                    Finding(
                        run.services_part,
                        LAYER,
                        f"{tool_pointer}/name",
                        f"would not survive the harness's sanitisation unchanged: {name!r}",
                    )
                )
                ok = False
                continue
            schema_claim = tool.get("schema_claim")
            if not isinstance(schema_claim, str) or schema_claim not in payloads:
                findings.append(
                    Finding(
                        run.services_part,
                        LAYER,
                        f"{tool_pointer}/schema_claim",
                        f"no claim in 01-claims/ carries a payload for {schema_claim!r}",
                    )
                )
                ok = False
        if ok:
            planned.append((run.interface(service_id), _document(service, payloads)))

    if findings:
        return [], findings

    run.interfaces_dir.mkdir(parents=True, exist_ok=True)
    written = {path for path, _ in planned}
    # Synthesis owns this directory. A service renamed at gate 1 and re-synthesised
    # would otherwise leave its old document behind, and a layer-2 check over this
    # directory would report an extra file against a run that is now correct. No
    # such check exists yet -- the removal is what keeps the directory honest for
    # the one that will, and for a human reading it at gate 1 today.
    for stale in list_json(run.interfaces_dir):
        if stale not in written:
            stale.unlink()
    for path, document in planned:
        write_json(path, document)
    return sorted(written), []
