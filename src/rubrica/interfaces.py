"""One service's OpenAPI document, derived from the tool contract it must preserve.

Code rather than a prompt, on `emit`'s argument: the document is a pure function
of the tool contract, so two runs with identical groupings must produce
byte-identical documents. Otherwise a difference in an emitted lab can no longer
be attributed to a stage, which is the property the whole measurement rests on.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

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


def claims_shape_problem(payload: object) -> str | None:
    """Why a parsed 01-claims/ member cannot be indexed, or None when it can.

    One home for the rule, shared by refs.check_parse and synthesise below. It
    lives here rather than in refs because refs already imports this module, so
    the other direction would be a cycle.

    A claims file is the one artifact whose *shape* refs checks as well as its
    parse, because every claim-resolving checker reads the claims index, and a
    member that parses to the wrong shape leaves that index short.
    Measured before this existed: `[]` in place of the toy's api-json.json made
    check-refs exit 1 with 28 `no such claim` findings against a correct world
    model and its partials, none naming the broken file -- and `{}` raised a
    KeyError out of _claim_index, an `[internal]` finding with no artifact.
    Reporting it in refs rides check_all's short-circuit, so the knock-on findings
    are held back exactly as they are for a truncated claims file.

    Only the keys the index reads unguarded are held to (`claims` a list, each
    member an object with a string `id`); anything finer is layer 1's.
    """
    if not isinstance(payload, dict):
        return f"claims file is not a JSON object (top level is {type(payload).__name__})"
    claims = payload.get("claims")
    if not isinstance(claims, list):
        return "claims file has no `claims` array"
    for i, claim in enumerate(claims):
        if not isinstance(claim, dict) or not isinstance(claim.get("id"), str):
            return f"claims[{i}] is not an object with a string `id`"
    return None


class _Claim(NamedTuple):
    """Where one claim was read from, and its payload when that payload is usable.

    A claim index rather than the payload index this used to be, because the two
    ways a `schema_claim` can fail are repairs for two different stages. An id no
    claim in `01-claims/` carries is `01-services.json`'s own defect and the
    finding names that file. A claim that *exists* and carries no payload usable
    as a schema is `rb-extract`'s defect, in the claims file this tuple names --
    the services part may be citing the only claim there is, byte-for-byte
    correctly. A payload index cannot tell those apart, and reported both against
    the services part: a 1 naming the wrong artifact, which sent the run's one
    repair attempt at a pass that would write the same thing again.

    `pointer` is into the claims file, not into the services part, and it is
    recorded here rather than recomputed because the index is the only place that
    knows which element of which file the id resolved to.
    """

    artifact: Path
    pointer: str
    payload: dict | None


def _document(service: dict, claims: dict[str, _Claim]) -> dict:
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
    sort_keys, so the order these dicts are built in -- `paths` among them, which
    is a dict and not a sequence -- is normalised away. List order is what
    byte-identity actually rests on, and this function builds exactly one list:
    `x-rubrica.tools`, in the order the pass wrote `service["tools"]`.
    """
    paths: dict[str, dict] = {}
    for tool in service["tools"]:
        name = tool["name"]
        paths[f"/{name}"] = {
            "post": {
                "operationId": name,
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {"schema": claims[tool["schema_claim"]].payload}
                    },
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
    refs.check_interfaces reports as a missing document for a service whose only
    problem is that a *sibling* was malformed, which is a 1 naming the wrong
    artifact. So every service is checked before any file is written.

    An unwritable 01-interfaces/ is NOT caught here. It raises OSError, which
    cli.py maps to exit 2 -- correct, because no re-dispatch of any prompt fixes a
    directory permission, and a 1 there would spend the run's single repair
    attempt rewriting a prompt whose output was never the problem.

    The findings name two different artifacts, and which one is not cosmetic: the
    services part for a defect in the grouping, and a claims file for a
    `schema_claim` resolving to a claim `rb-extract` left with no usable payload.
    See `_Claim` for why the second is not the part's defect.
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

    # Claim id -> where it was read and what payload it carries, over every claims
    # file. Built once: a run with forty inputs and four services would otherwise
    # re-read every claims file per service.
    #
    # An unreadable or non-dict claims file contributes nothing to the index, so a
    # `schema_claim` into it comes back as an id no claim carries -- the finding
    # against that file is already in `findings` and it is the one a repair acts
    # on. The index never blames a file it could not read. A dict whose `claims`
    # is missing, not a list, or holds a member with no string `id` is held to
    # claims_shape_problem instead, and while one is present the unresolved
    # `schema_claim` findings against the part are dropped (see below).
    claims: dict[str, _Claim] = {}
    misshapen = False
    for path in list_json(run.claims_dir):
        try:
            document = read_json(path)
        except ArtifactError as exc:
            findings.append(Finding(path, LAYER, "", f"cannot read: {exc}"))
            continue
        if not isinstance(document, dict):
            findings.append(Finding(path, LAYER, "", "claims file is not a JSON object"))
            continue
        # The rule refs holds a claims file to, so the two commands agree on which
        # file is broken. Measured before this: `{}` and `{"claims": "x"}` left the
        # index short and came back as one `no claim in 01-claims/ has id` against
        # a correct 01-services.json, naming no claims file at all, and
        # `{"claims": 7}` raised TypeError -- an `[internal]` 1 with no artifact.
        # Either way the orchestrator would spend its one repair on
        # reconcile-services, whose output was never the problem.
        problem = claims_shape_problem(document)
        if problem is not None:
            findings.append(Finding(path, LAYER, "", problem))
            misshapen = True
            continue
        for index, claim in enumerate(document["claims"]):
            payload = claim.get("payload")
            claims[claim["id"]] = _Claim(
                path,
                f"/claims/{index}/payload",
                payload if isinstance(payload, dict) else None,
            )

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
            claim = claims.get(schema_claim) if isinstance(schema_claim, str) else None
            # Two defects, two artifacts. Which file a 1 names is the whole point
            # of the split: an id nothing carries is this part's defect, while a
            # claim with no usable payload is the claims file's, and naming the
            # part for the second sent the repair at a pass whose output was
            # correct -- rb-reconcile-services is instructed to name the claim
            # anyway in exactly that case, so it would write the same thing again.
            if claim is None:
                findings.append(
                    Finding(
                        run.services_part,
                        LAYER,
                        f"{tool_pointer}/schema_claim",
                        f"no claim in 01-claims/ has id {schema_claim!r}",
                    )
                )
                ok = False
            elif claim.payload is None:
                findings.append(
                    Finding(
                        claim.artifact,
                        LAYER,
                        claim.pointer,
                        "no payload usable as a request-body schema, and "
                        f"{run.services_part.name} names this claim at "
                        f"{tool_pointer}/schema_claim",
                    )
                )
                ok = False
        if ok:
            planned.append((run.interface(service_id), _document(service, claims)))

    if misshapen:
        # A claims file that parses but cannot be indexed may be exactly where a
        # cited id lives, so an unresolved `schema_claim` is not yet evidence
        # against the services part. Held back, as check_all's short-circuit holds
        # back refs' knock-on findings, so the only file a repair is pointed at is
        # the claims file. Everything else against the part still prints: those
        # defects do not depend on the index.
        findings = [
            f
            for f in findings
            if not (f.artifact == run.services_part and f.pointer.endswith("/schema_claim"))
        ]

    if findings:
        return [], findings

    run.interfaces_dir.mkdir(parents=True, exist_ok=True)
    written = {path for path, _ in planned}
    # Synthesis owns this directory. A service renamed at gate 1 and re-synthesised
    # would otherwise leave its old document behind, and refs.check_interfaces
    # reports a document no service asked for -- so without this the rename would
    # leave a 1 standing against a run that is now correct.
    for stale in list_json(run.interfaces_dir):
        if stale not in written:
            stale.unlink()
    for path, document in planned:
        write_json(path, document)
    return sorted(written), []
