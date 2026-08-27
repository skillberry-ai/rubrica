"""The golden toy world: two capabilities, four cells, four scenarios.

Section 9 asks for "one golden end-to-end fixture: a two-capability toy world
small enough to review by hand, run in CI". This is it, and it is deliberately
*not* a consolidation of tests/builders.py. Those payloads are minimal so that
one changed key is the whole test -- mutation fodder. This world is the opposite
artifact: complete enough that a person reading it can judge whether the
pipeline's output would be fair, and built from real files through real intake
so the digest and stored_as chain is exercised rather than hand-written to
agree. Keep both.

The world it describes: `ticketq`, two support queues, one read-only tool with
two actions. Every seed below carries near-misses on purpose -- a ticket that
is open in the wrong queue, a ticket with a confusingly similar summary --
because a world with exactly one candidate row is passable by any agent that
calls the API once, which is how an all-pass suite happens.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from rubrica import rounds
from rubrica.artifacts import read_json, sha256_of, write_json
from rubrica.intake import classify, intake
from rubrica.paths import RunPaths
from rubrica.seal import seal
from rubrica.slices import write_slices
from rubrica.survey import survey

TOY_DIR = Path(__file__).resolve().parent / "fixtures" / "toy"
CONTRADICTION_DIR = Path(__file__).resolve().parent / "fixtures" / "toy-contradiction"
GAP_DIR = Path(__file__).resolve().parent / "fixtures" / "toy-gap"

# The trajectory run's captured fixture (design spec 2026-08-12). Not a toy
# world and not built by build_toy_run -- it is committed live capture, so it
# sits beside the other fixture dirs for path resolution only.
TRAJECTORIES_DIR = Path(__file__).resolve().parent / "fixtures" / "reservation-trajectories"

# In the order intake registers them, which fixes the artifact ids below.
INPUT_FILES: tuple[Path, ...] = (
    TOY_DIR / "api.json",
    TOY_DIR / "notes.md",
    TOY_DIR / "trace.json",
)

# What intake.slug makes of each filename. Asserted in test_toy_end_to_end
# against the manifest intake actually wrote, rather than trusted here.
ARTIFACT_IDS: tuple[str, ...] = ("api-json", "notes-md", "trace-json")

# The scenarios with an instance directory. Deliberately narrower than
# ALL_SCENARIO_IDS below, which also holds the folded scn-open-dup: a duplicate
# is never instantiated, so iterating this set is what keeps seeds and oracles
# off it.
SIDS: tuple[str, ...] = ("scn-open", "scn-empty", "scn-blocked", "scn-missing")


def _claim(cid, kind, statement, artifact_id, locator, confidence, derivation, quote=None):
    evidence: dict[str, Any] = {"artifact_id": artifact_id, "locator": locator}
    if quote is not None:
        evidence["quote"] = quote
    return {
        "id": cid,
        "kind": kind,
        "statement": statement,
        "evidence": [evidence],
        "confidence": confidence,
        "derivation": derivation,
    }


_CLAIMS: dict[str, list[dict[str, Any]]] = {
    "api-json": [
        _claim(
            "clm-api-001",
            "capability",
            "query_tickets supports action=find_tickets",
            "api-json",
            "#/tools/0/input_schema/properties/action/enum/0",
            "high",
            "stated",
        ),
        _claim(
            "clm-api-002",
            "capability",
            "query_tickets supports action=get_ticket",
            "api-json",
            "#/tools/0/input_schema/properties/action/enum/1",
            "high",
            "stated",
        ),
        _claim(
            "clm-api-003",
            "entity",
            "A ticket carries ticket_id, queue, status, summary and comment_count",
            "api-json",
            "#/entities/Ticket/fields",
            "high",
            "stated",
        ),
        _claim(
            "clm-api-004",
            "entity",
            "A comment carries comment_id, ticket_id, position and body",
            "api-json",
            "#/entities/Comment/fields",
            "high",
            "stated",
        ),
        _claim(
            "clm-api-005",
            "outcome_class",
            "find_tickets returns a possibly-empty list of matching tickets",
            "api-json",
            "#/tools/0/returns/find_tickets",
            "high",
            "stated",
        ),
        _claim(
            "clm-api-006",
            "outcome_class",
            "get_ticket returns the ticket together with its comments, ordered by position",
            "api-json",
            "#/tools/0/returns/get_ticket",
            "high",
            "stated",
        ),
        _claim(
            "clm-api-007",
            "capability",
            "find_tickets takes an optional queue filter",
            "api-json",
            "#/tools/0/input_schema/properties/queue",
            "high",
            "stated",
            quote='"required": ["action"]',
        ),
        _claim(
            "clm-api-008",
            "capability",
            "find_tickets takes an optional status filter",
            "api-json",
            "#/tools/0/input_schema/properties/status",
            "high",
            "stated",
            quote='"required": ["action"]',
        ),
        _claim(
            "clm-api-009",
            "capability",
            "get_ticket needs a ticket_id to identify which ticket to fetch",
            "api-json",
            "#/tools/0/input_schema/properties/ticket_id",
            "medium",
            "inferred",
        ),
    ],
    "notes-md": [
        _claim(
            "clm-notes-001",
            "actor",
            "Support engineers triage the two queues",
            "notes-md",
            "#operator-notes",
            "medium",
            "inferred",
        ),
        _claim(
            "clm-notes-002",
            "goal",
            "An engineer locates the ticket that needs action, or establishes it does not exist",
            "notes-md",
            "#what-engineers-actually-ask",
            "medium",
            "inferred",
        ),
        _claim(
            "clm-notes-003",
            "goal",
            "An engineer explains why a ticket is stuck",
            "notes-md",
            "#what-engineers-actually-ask",
            "medium",
            "inferred",
        ),
        _claim(
            "clm-notes-004",
            "outcome_class",
            "get_ticket with an id no ticket has is an error, not an empty result",
            "notes-md",
            "#error-behaviour",
            "high",
            "stated",
            quote="`get_ticket` with an id no ticket has is an **error**, not an empty result.",
        ),
        _claim(
            "clm-notes-005",
            "invariant",
            "comment_count equals the number of comment records on the ticket",
            "notes-md",
            "#invariants-the-store-maintains",
            "high",
            "stated",
        ),
        _claim(
            "clm-notes-006",
            "invariant",
            "ticket_id is unique across every queue",
            "notes-md",
            "#invariants-the-store-maintains",
            "high",
            "stated",
        ),
        _claim(
            "clm-notes-007",
            "goal",
            "locating the ticket that needs action takes one lookup",
            "notes-md",
            "#what-engineers-actually-ask",
            "high",
            "stated",
            quote='"Which ticket in this queue still needs me?" — one lookup.',
        ),
        _claim(
            "clm-notes-008",
            "goal",
            "explaining why a ticket is stuck takes finding the ticket, then reading its comments",
            "notes-md",
            "#what-engineers-actually-ask",
            "high",
            "stated",
            quote="find the ticket, then read its comments, which is where the blocker is named.",
        ),
    ],
    "trace-json": [
        _claim(
            "clm-trace-001",
            "outcome_class",
            "find_tickets returned an empty list for a queue with no matching tickets",
            "trace-json",
            "#/spans/0/output",
            "high",
            "reverse_engineered",
        ),
        _claim(
            "clm-trace-002",
            "outcome_class",
            "get_ticket on an unknown id returned an empty object rather than an error",
            "trace-json",
            "#/spans/1/output",
            "medium",
            "reverse_engineered",
        ),
    ],
}


def toy_claims(artifact_id: str, **over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "artifact_id": artifact_id,
        "claims": [dict(claim) for claim in _CLAIMS[artifact_id]],
    }
    payload.update(over)
    return payload


def toy_world_model(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "target": {"name": "ticketq", "interface": "mcp"},
        "capabilities": [
            {
                "id": "cap-find-tickets",
                "operation": "query_tickets.find_tickets",
                "binding": {"tool": "query_tickets", "fixed_args": {"action": "find_tickets"}},
                "params": [
                    {"name": "queue", "type": "string", "required": False},
                    {"name": "status", "type": "string", "required": False},
                ],
                "outcome_classes": [
                    {
                        "id": "oc-found",
                        "kind": "success",
                        "description": "one or more tickets match the filters",
                        # clm-api-005: "find_tickets returns a possibly-empty list of
                        # matching tickets". The one claim covers both outcome classes,
                        # and citing it twice is correct rather than sloppy -- an outcome
                        # class's claims are the evidence for *that outcome*, not a
                        # partition of the claim set.
                        "claims": ["clm-api-005"],
                    },
                    {
                        "id": "oc-none",
                        "kind": "empty",
                        "description": "no ticket matches the filters",
                        # clm-trace-001 is the observed empty return; clm-api-005 is the
                        # stated "possibly-empty".
                        "claims": ["clm-api-005", "clm-trace-001"],
                    },
                ],
                # The capability's own claims are the capability-kind ones only, now that
                # the outcome_class-kind evidence sits on the outcome class it is about
                # (issue #6). Before that, $defs/outcome_class had no `claims` array at
                # all and was additionalProperties: false, so this list was the only
                # place the evidence for an outcome could go.
                "claims": ["clm-api-001", "clm-api-007", "clm-api-008"],
                "confidence": "high",
            },
            {
                "id": "cap-get-ticket",
                "operation": "query_tickets.get_ticket",
                "binding": {"tool": "query_tickets", "fixed_args": {"action": "get_ticket"}},
                "params": [{"name": "ticket_id", "type": "integer", "required": True}],
                "outcome_classes": [
                    {
                        "id": "oc-detail",
                        "kind": "success",
                        "description": "the ticket and its comments, ordered by position",
                        "claims": ["clm-api-006"],
                    },
                    {
                        "id": "oc-missing",
                        "kind": "not_found",
                        "description": "no ticket has that id, which is an error",
                        # clm-notes-004, the *preferred_a* side of con-missing-semantics.
                        # Its losing side, clm-trace-002, is deliberately not cited here:
                        # the contradiction records it, and citing the side the resolution
                        # rejected would model a disagreement as settled the other way.
                        "claims": ["clm-notes-004"],
                    },
                ],
                "claims": ["clm-api-002", "clm-api-009"],
                "confidence": "high",
            },
        ],
        "entities": [
            {
                "id": "ent-ticket",
                "name": "Ticket",
                "collection": "tickets",
                "fields": [
                    {"name": "ticket_id", "type": "integer"},
                    {"name": "queue", "type": "string"},
                    {"name": "status", "type": "string"},
                    {"name": "summary", "type": "string"},
                    {"name": "comment_count", "type": "integer"},
                ],
                "relations": [
                    {"name": "comments", "target_entity_id": "ent-comment", "cardinality": "many"}
                ],
                "invariants": [
                    {
                        "id": "inv-comment-count",
                        "statement": "comment_count is the number of comments on the ticket",
                        "machine": {
                            "form": "count",
                            "collection": "tickets",
                            "field": "comment_count",
                            "of": "comments",
                            "local_key": "ticket_id",
                            "foreign_key": "ticket_id",
                        },
                        # clm-notes-005: "comment_count equals the number of comment
                        # records on the ticket".
                        "claims": ["clm-notes-005"],
                    },
                    {
                        "id": "inv-ticket-id-unique",
                        "statement": "ticket_id is unique across every queue",
                        "machine": {
                            "form": "unique",
                            "collection": "tickets",
                            "field": "ticket_id",
                        },
                        # clm-notes-006, whose statement is this invariant verbatim.
                        "claims": ["clm-notes-006"],
                    },
                ],
                # Entity-kind only, for the same reason the capabilities above shed their
                # outcome_class-kind claims: the invariant-kind evidence now sits on the
                # invariant it states.
                "claims": ["clm-api-003"],
            },
            {
                "id": "ent-comment",
                "name": "Comment",
                "collection": "comments",
                "fields": [
                    {"name": "comment_id", "type": "integer"},
                    {"name": "ticket_id", "type": "integer"},
                    {"name": "position", "type": "integer"},
                    {"name": "body", "type": "string"},
                ],
                "claims": ["clm-api-004"],
            },
        ],
        "actors": [{"id": "act-support", "name": "Support engineer", "claims": ["clm-notes-001"]}],
        "goals": [
            {
                "id": "goal-locate",
                "actor_id": "act-support",
                "statement": (
                    "Locate the ticket that needs action, or establish that it does not exist"
                ),
                "expected_hop_depths": [1],
                "claims": ["clm-notes-002", "clm-notes-007"],
            },
            {
                "id": "goal-explain",
                "actor_id": "act-support",
                "statement": "Explain why a ticket is stuck",
                "expected_hop_depths": [2],
                "claims": ["clm-notes-003", "clm-notes-008"],
            },
        ],
        "contradictions": [
            {
                "id": "con-missing-semantics",
                "claim_a": "clm-notes-004",
                "claim_b": "clm-trace-002",
                "nature": (
                    "the operator notes state that get_ticket on an unknown id is an error; "
                    "the captured trace shows an empty object returned instead"
                ),
                "resolution": "preferred_a",
                "rationale": (
                    "clm-notes-004 is stated at high confidence directly from the operator "
                    "notes; clm-trace-002 is only reverse_engineered at medium confidence from "
                    "one captured call, which shows what the target did once but not what it is "
                    "contracted to do. The stated, higher-confidence claim wins, so oc-missing "
                    "is modelled as an error; recorded rather than dropped because a scenario "
                    "built on the trace's behaviour would be labelled against a claim the "
                    "evidence does not actually support"
                ),
            }
        ],
        "gaps": [],
        "denominator": {"version": 1, "capability_cells": 4, "goals": 2},
    }
    payload.update(over)
    return payload


# Which claim kinds each pass is accountable for. The six kinds in
# claims-0.1.json partition onto the four passes that own one, which is what
# makes an own-kind count a per-pass number rather than an aggregate: measured on
# run-20260823-112746, per-kind citation was capability 110/135 while goal was
# 2/38, and the run's single aggregate figure of 33.6% is the average that hid
# it. reconcile-gaps owns no kind, and reconcile-subjects and
# reconcile-contradict need no accounting -- refs.check_subjects already makes
# the cover total.
OWN_KINDS: dict[str, tuple[str, ...]] = {
    "capabilities": ("capability",),
    "entities": ("entity", "invariant"),
    "outcomes": ("outcome_class",),
    "goals": ("actor", "goal"),
}


def _claim_refs_in(node: Any) -> set[str]:
    """Every id in every `claims` array anywhere in a partial.

    A walk rather than a per-part list of paths: the four partials nest their
    citations differently -- an entity carries them on itself and on each
    invariant, the outcomes part two levels down inside an `outcomes` record --
    and a path list would need revising by whoever nests a new element. Mirrors
    refs._claim_refs_in, and both exist because the fixture must compute what
    the checker recomputes; if they ever disagree, the fixture is what proves
    the checker wrong rather than the other way round.
    """
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "claims":
                found.update(v for v in value if isinstance(v, str))
            else:
                found.update(_claim_refs_in(value))
    elif isinstance(node, list):
        for item in node:
            found.update(_claim_refs_in(item))
    return found


def _inputs_seen(part: dict[str, Any], own_kinds: tuple[str, ...]) -> list[dict[str, Any]]:
    """One row per artifact in the toy corpus, computed from the part itself.

    Total over every artifact, including those holding none of this pass's kinds
    -- a 0/0/0 row is the honest record for those, and totality is what the
    checker requires: a missing row leaves a pass that never opened a claims file
    indistinguishable from one that opened it and cited nothing.
    """
    cited_ids = _claim_refs_in(part)
    rows: list[dict[str, Any]] = []
    for artifact_id in ARTIFACT_IDS:
        own = [c for c in toy_claims(artifact_id)["claims"] if c["kind"] in own_kinds]
        cited = sum(1 for claim in own if claim["id"] in cited_ids)
        row: dict[str, Any] = {
            "artifact_id": artifact_id,
            "own_kind_total": len(own),
            "cited": cited,
            "dropped": len(own) - cited,
        }
        if row["dropped"]:
            # The toy's one drop today, and it is the worked example the spec
            # wants on the record: clm-trace-002 is the losing side of
            # con-missing-semantics, resolved `preferred_a`. It is cited by the
            # contradiction and by no partial, so the outcomes pass's row for
            # trace-json reads 2/1/1 -- which is exactly the case a reader at
            # gate 1 should be able to tell apart from a file nobody opened.
            #
            # The note itself says none of that. This branch stamps one sentence
            # on *any* non-zero drop, so a fixture edit that dropped a claim for
            # an unrelated reason would put a false statement into the model
            # answer every skill imitates -- schema-valid, and silent. The prose
            # is therefore true of every drop by construction: a dropped claim is
            # by definition one this partial does not cite. Which drop it is, and
            # why, belongs in the comment above rather than in the artifact.
            row["note"] = (
                "read and deliberately not modelled in this partial; nothing this pass "
                "wrote rests on it"
            )
        rows.append(row)
    return rows


def split_world_model(
    world: dict[str, Any] | None = None,
    *,
    claim_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """The golden world model, cut into the partials the reconcile passes write.

    Derived rather than hand-authored beside toy_world_model: tests/fixtures/toy/
    is the model answer a skill imitates, and a second copy of that answer in
    partial form would be a second thing to keep correct -- the drift this module
    already avoids by building every checkpoint from one source. Deriving is also
    what makes the seal's round trip a *property* (seal(split(w)) == w) rather
    than a worked example: a hand-authored pair could satisfy it while both
    drifted together.

    `claim_ids` defaults to every claim the toy run actually contains, because the
    cover has to be total -- refs.check_subjects reports any claim it omits, and a
    fixture that could not pass its own gate would be untestable against it.

    The subject assignment is deliberately mechanical (one subject per capability,
    one per entity, one for the actors and goals, one catch-all): it stands in for
    a judgment a prompt makes, and a fixture that guessed cleverly here would be
    claiming more than it can know.
    """
    world = toy_world_model() if world is None else world
    if claim_ids is None:
        claim_ids = [
            claim["id"]
            for artifact_id in ARTIFACT_IDS
            for claim in toy_claims(artifact_id)["claims"]
        ]
    remaining = list(dict.fromkeys(claim_ids))

    subjects: list[dict[str, Any]] = []

    def take(subject_id: str, label: str, cited: list[str]) -> None:
        """Record one subject, and strike its claims off the catch-all's list.

        Struck rather than left, so a claim cited by two elements lands in both
        subjects (the cover is a cover) while the catch-all holds only what no
        element cites at all.
        """
        if not cited:
            return
        # Deduplicated, order preserved. One claim can reach `cited` twice now that
        # a capability's subject also covers what its outcome classes cite -- the
        # golden world's clm-api-005 is on both of cap-find-tickets' outcome classes,
        # deliberately, since an outcome class's claims are the evidence for *that*
        # outcome rather than a partition. Repeating the id in a cover would say
        # nothing a reader could act on.
        subjects.append({"id": subject_id, "label": label, "claims": list(dict.fromkeys(cited))})
        for claim_id in cited:
            if claim_id in remaining:
                remaining.remove(claim_id)

    # A capability's subject covers what its outcome classes cite, and an entity's
    # what its invariants cite. Since issue #6 those are the elements that hold the
    # outcome_class- and invariant-kind evidence, and a cover built from the parent
    # array alone would strand it: measured with the child arrays ignored, all six
    # moved ids fell through to sub-uncited, and con-missing-semantics
    # -- whose claim_a is oc-missing's clm-notes-004 -- followed them there, out of
    # the subject that names the capability the disagreement is about.
    for capability in world["capabilities"]:
        take(
            f"sub-{capability['id']}",
            capability["operation"],
            [
                *capability["claims"],
                *(
                    claim_id
                    for outcome_class in capability["outcome_classes"]
                    for claim_id in outcome_class["claims"]
                ),
            ],
        )
    for entity in world["entities"]:
        take(
            f"sub-{entity['id']}",
            entity["name"],
            [
                *entity["claims"],
                *(
                    claim_id
                    for invariant in entity.get("invariants", [])
                    for claim_id in invariant["claims"]
                ),
            ],
        )
    take(
        "sub-actors-and-goals",
        "who uses the target, and what for",
        [cid for item in (*world["actors"], *world["goals"]) for cid in item["claims"]],
    )
    take("sub-uncited", "claims no element of the world model cites", remaining)

    # Every subject gets a part, empty or not: the file is the record that the
    # fan-out member visited that subject, which is what
    # refs.check_contradiction_parts checks and what the single-turn stage could
    # never show. A contradiction lands under the first subject holding its
    # claim_a, so the assignment is a function of the cover rather than a second
    # judgment.
    #
    # Both sides then join that subject, and that is the load-bearing half.
    # rb-reconcile-contradict's invariant 3 is that both sides of a recorded
    # contradiction are claims the member's *own* subject names -- a claim
    # outside that subject is a sibling member's to sweep, so a contradiction
    # spanning two subjects is not this member's to record. Measured before
    # this: sub-cap-get-ticket held clm-notes-004 but not clm-trace-002, and
    # carried con-missing-semantics anyway. Since tests/fixtures/toy/ is the
    # model answer a skill imitates, that
    # taught the member reaching across subjects was fine, and it left the fixture
    # unable to demonstrate the whole point of the split -- that a cross-artifact
    # contradiction is findable *within* one subject. Over-assigning is legal
    # (a cover may put one claim in several subjects) and is exactly what
    # rb-reconcile-subjects instructs when a claim bears on more than one subject.
    #
    # Ownership is resolved against a snapshot taken before any of this widening,
    # so which subject owns a contradiction stays a function of the cover the
    # passes above built rather than of the order this loop happens to run in.
    by_subject: dict[str, list[dict[str, Any]]] = {s["id"]: [] for s in subjects}
    by_id = {s["id"]: s for s in subjects}
    as_covered = {s["id"]: list(s["claims"]) for s in subjects}
    for contradiction in world["contradictions"]:
        owner = next(
            (s["id"] for s in subjects if contradiction["claim_a"] in as_covered[s["id"]]),
            subjects[-1]["id"],
        )
        by_subject[owner].append(contradiction)
        for side in ("claim_a", "claim_b"):
            claim_id = contradiction[side]
            if claim_id not in by_id[owner]["claims"]:
                by_id[owner]["claims"].append(claim_id)

    # Built before the rows, because _inputs_seen reads the finished part: the
    # count of cited claims is a property of what the pass wrote, so declaring
    # rows beside the elements would make them a second assertion to keep
    # correct rather than a measurement of the first.
    partials: dict[str, Any] = {
        "capabilities": {
            "schema_version": "0.1",
            "capabilities": [
                {k: v for k, v in capability.items() if k != "outcome_classes"}
                for capability in world["capabilities"]
            ],
        },
        "outcomes": {
            "schema_version": "0.1",
            "outcomes": [
                {"capability_id": c["id"], "outcome_classes": c["outcome_classes"]}
                for c in world["capabilities"]
            ],
        },
        "entities": {"schema_version": "0.1", "entities": world["entities"]},
        "goals": {
            "schema_version": "0.1",
            "actors": world["actors"],
            "goals": world["goals"],
        },
    }
    for key, own_kinds in OWN_KINDS.items():
        partials[key]["inputs_seen"] = _inputs_seen(partials[key], own_kinds)

    # gaps gets no inputs_seen: rb-reconcile-gaps owns no claim kind, and a gap
    # asserts what no input contains, so no output shape can force its read
    # coverage. The hole that leaves is real, and deliberate rather than missed.
    return {
        "subjects": {"schema_version": "0.1", "subjects": subjects},
        "contradictions": {
            subject_id: {
                "schema_version": "0.1",
                "subject_id": subject_id,
                "contradictions": found,
            }
            for subject_id, found in by_subject.items()
        },
        **partials,
        "gaps": {"schema_version": "0.1", "gaps": world["gaps"]},
    }


_SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "scn-open",
        "round": 1,
        "goal_id": "goal-locate",
        "actor_id": "act-support",
        "title": "Find the open billing ticket",
        "user_intent": "Which ticket in the billing queue is still open?",
        "hop_depth": 1,
        "capability_refs": [{"capability_id": "cap-find-tickets", "outcome_class_id": "oc-found"}],
        "discriminating_fact": "exactly one billing ticket has status open",
        "status": "active",
        "provenance": {
            "hole_refs": ["cell:cap-find-tickets/oc-found"],
            "claim_ids": ["clm-api-001", "clm-api-005"],
            "round": 1,
        },
    },
    {
        "id": "scn-empty",
        "round": 1,
        "goal_id": "goal-locate",
        "actor_id": "act-support",
        "title": "Report that the shipping queue is quiet",
        "user_intent": "Is anything blocked in the shipping queue right now?",
        "hop_depth": 1,
        "capability_refs": [{"capability_id": "cap-find-tickets", "outcome_class_id": "oc-none"}],
        "discriminating_fact": "no shipping ticket has status blocked",
        "status": "active",
        "provenance": {
            "hole_refs": ["cell:cap-find-tickets/oc-none"],
            "claim_ids": ["clm-trace-001"],
            "round": 1,
        },
    },
    {
        "id": "scn-blocked",
        "round": 1,
        "goal_id": "goal-explain",
        "actor_id": "act-support",
        "title": "Explain what the blocked billing ticket is waiting on",
        "user_intent": "One billing ticket is blocked. Which one, and what is it waiting on?",
        "hop_depth": 2,
        "capability_refs": [
            {"capability_id": "cap-find-tickets", "outcome_class_id": "oc-found"},
            {"capability_id": "cap-get-ticket", "outcome_class_id": "oc-detail"},
        ],
        "discriminating_fact": (
            "exactly one billing ticket is blocked, and only its last comment names the blocker"
        ),
        "status": "active",
        "provenance": {
            "hole_refs": ["cell:cap-get-ticket/oc-detail", "goal:goal-explain"],
            "claim_ids": ["clm-api-002", "clm-api-004"],
            "round": 1,
        },
    },
    {
        "id": "scn-missing",
        "round": 1,
        "goal_id": "goal-locate",
        "actor_id": "act-support",
        "title": "Establish that a ticket does not exist",
        "user_intent": "What is the status of ticket 4109?",
        "hop_depth": 1,
        "capability_refs": [{"capability_id": "cap-get-ticket", "outcome_class_id": "oc-missing"}],
        "discriminating_fact": "no ticket with id 4109 exists in either queue",
        "status": "active",
        "provenance": {
            "hole_refs": ["cell:cap-get-ticket/oc-missing"],
            "claim_ids": ["clm-notes-004"],
            "round": 1,
        },
    },
    # Folded into scn-open by the score stage: same goal, the same single cell,
    # and the same discriminating fact behind different wording. Present because
    # dedupe.candidate_pairs returns nothing at all on a scenario set whose
    # cells are disjoint -- without this pair the toy world could not exercise a
    # dedupe judgment, and the deterministic half of stage 3 would be untested
    # against any real input. It is never instantiated and never emitted, which
    # is what `duplicate` means.
    {
        "id": "scn-open-dup",
        "round": 1,
        "goal_id": "goal-locate",
        "actor_id": "act-support",
        "title": "Which billing ticket still needs attention",
        "user_intent": "Is there a billing ticket nobody has closed yet?",
        "hop_depth": 1,
        "capability_refs": [{"capability_id": "cap-find-tickets", "outcome_class_id": "oc-found"}],
        "discriminating_fact": "exactly one billing ticket has status open",
        "status": "duplicate",
        "duplicate_of": "scn-open",
        "provenance": {
            "hole_refs": ["cell:cap-find-tickets/oc-found"],
            "claim_ids": ["clm-api-001"],
            "round": 1,
        },
    },
]

# Every scenario in 02-scenarios.json, including the folded one. SIDS above is
# the narrower set -- the scenarios with an instance directory -- and the two
# must not be conflated: iterating ALL_SCENARIO_IDS to build seeds would
# instantiate a duplicate, which refs.check_instances reports.
ALL_SCENARIO_IDS: tuple[str, ...] = tuple(s["id"] for s in _SCENARIOS)


def toy_scenarios(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "denominator_version": 1,
        "scenarios": [dict(s) for s in _SCENARIOS],
    }
    payload.update(over)
    return payload


# The one batch this world's round 1 partitions into, and it is a derived fact
# rather than a choice: the golden world declares four cells and two goals, so
# rounds.closable_holes returns six refs on a run with no coverage document, and
# rounds.partition packs 28000 // 1600 = 17 refs per batch against the default
# budget. Named here because the part filename is this id and every scenario in
# the part has to target a hole this batch owns. Nothing trusts this comment:
# build_toy_run asserts write_batches returned round 1's plan, and
# test_upto_propose_writes_the_batch_plan_and_the_part_and_seals_nothing asserts
# scenario_part_batch_ids(1) is exactly this id -- so a partition that grew to two
# batches fails there rather than leaving a stale constant behind.
TOY_BATCH_ID = "b01"


def _proposed_scenarios() -> list[dict[str, Any]]:
    """Every scenario as its propose member wrote it: `proposed`, never folded.

    A fold and a promotion are rb-score's rulings, which arrive in
    03-score/round-1.json and are applied by rounds.seal_scenarios -- so a part
    carrying either would be a fixture teaching a propose member to do the next
    stage's job. `status: "proposed"` with no `duplicate_of` is the only shape
    rb-propose's own Output section allows.
    """
    scenarios = []
    for scenario in _SCENARIOS:
        scenario = dict(scenario)
        scenario["status"] = "proposed"
        scenario.pop("duplicate_of", None)
        scenarios.append(scenario)
    return scenarios


def toy_scenario_part(**over: Any) -> dict[str, Any]:
    """Round 1's single propose part: every scenario, all in one batch.

    One part rather than several, and the reason is the golden world rather than
    convenience: `scn-open` and `scn-open-dup` both target
    `cell:cap-find-tickets/oc-found`, and refs.check_scenario_parts reports a
    scenario whose `provenance.hole_refs` name a hole the round assigned to a
    *sibling* batch. Splitting these two across two members would therefore make
    the golden fixture carry a finding -- and the pair exists precisely so
    dedupe.candidate_pairs has something to judge, so it cannot be split either.

    The order is `_SCENARIOS`' order, and it is load-bearing:
    rounds.collect_scenarios preserves a part's own order, so this is what fixes
    the byte order of the sealed 02-scenarios.json.
    """
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "round": 1,
        "batch_id": TOY_BATCH_ID,
        "scenarios": _proposed_scenarios(),
    }
    payload.update(over)
    return payload


def toy_score_part(**over: Any) -> dict[str, Any]:
    """Round 1's score part: the rulings, no holes, and the verdict.

    Everything rb-score decides and nothing it can compute. The matrices that
    used to sit in this fixture are rounds.seal_score's arithmetic now, which is
    why `toy_coverage()` below is still the golden coverage document but no
    longer anything this builder writes: the seal composes it, and
    test_toy_fixture holds the two to each other.

    `holes` is empty because every row of this world's denominator is covered --
    the same single statement toy_coverage()'s docstring makes, and seal_score
    refuses a part whose holes and computed matrices disagree in either
    direction, so a hole added here without a matching uncovered row would be
    caught rather than sealed.
    """
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "round": 1,
        "rulings": [
            # Promotions first, in _SCENARIOS order, then the fold: a ruling only
            # exists to CHANGE a status, so every scenario named here is one the
            # sealed document must not carry as `proposed`.
            {"scenario_id": "scn-open", "status": "active"},
            {"scenario_id": "scn-empty", "status": "active"},
            {"scenario_id": "scn-blocked", "status": "active"},
            {"scenario_id": "scn-missing", "status": "active"},
            {
                "scenario_id": "scn-open-dup",
                "status": "duplicate",
                "duplicate_of": "scn-open",
            },
        ],
        "holes": [],
        "verdict": "converged",
    }
    payload.update(over)
    return payload


def toy_coverage(**over: Any) -> dict[str, Any]:
    """Full coverage of four cells and two goals, so holes is empty.

    A hole here would have to name a covered row, which refs.check_coverage
    reports in both directions -- so "fully covered" and "no holes" are one
    statement, not two.

    No longer written by build_toy_run: rounds.seal_score composes the coverage
    document from toy_score_part() now, and this stays as the answer key that
    composition is held to (test_toy_fixture compares the two byte for byte).
    Two entries below were corrected when the seal took over, and both are the
    fixture moving toward rb-score's own Method rather than away from it:

      * `cell:cap-find-tickets/oc-found` now lists scn-open-dup among its
        `scenario_ids`. Method step 4 says a cell lists every scenario *claiming*
        it and marks `covered` from whether any of them is live -- so a folded
        claimant belongs in the list, and omitting it taught the opposite of the
        asymmetry the step exists to state.
      * every id list is sorted. Method step 4 does not ask for an order, so the
        seal fixes one: two runs with identical parts must produce byte-identical
        output, and check_coverage compares these as sets either way.
    """
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "round": 1,
        "denominator_version": 1,
        "capability_matrix": {
            "cells": [
                {
                    "capability_id": "cap-find-tickets",
                    "outcome_class_id": "oc-found",
                    "scenario_ids": ["scn-blocked", "scn-open", "scn-open-dup"],
                    "covered": True,
                },
                {
                    "capability_id": "cap-find-tickets",
                    "outcome_class_id": "oc-none",
                    "scenario_ids": ["scn-empty"],
                    "covered": True,
                },
                {
                    "capability_id": "cap-get-ticket",
                    "outcome_class_id": "oc-detail",
                    "scenario_ids": ["scn-blocked"],
                    "covered": True,
                },
                {
                    "capability_id": "cap-get-ticket",
                    "outcome_class_id": "oc-missing",
                    "scenario_ids": ["scn-missing"],
                    "covered": True,
                },
            ],
            "covered": 4,
            "total": 4,
            "pct": 1.0,
        },
        "goal_matrix": {
            "rows": [
                {
                    "goal_id": "goal-locate",
                    "scenario_ids": ["scn-empty", "scn-missing", "scn-open"],
                    "hop_depths_present": [1],
                    "hop_depths_expected": [1],
                    "covered": True,
                },
                {
                    "goal_id": "goal-explain",
                    "scenario_ids": ["scn-blocked"],
                    "hop_depths_present": [2],
                    "hop_depths_expected": [2],
                    "covered": True,
                },
            ],
            "covered": 2,
            "total": 2,
            "pct": 1.0,
        },
        "holes": [],
        "progress": {"new_cells_this_round": 4, "rounds_without_progress": 0},
        "verdict": "converged",
    }
    payload.update(over)
    return payload


# One open billing ticket. Distractors: a closed billing ticket, and an
# open ticket in the wrong queue -- so "the open one" is not answerable by
# reading back the only row.
_SEEDS: dict[str, dict[str, Any]] = {
    "scn-open": {
        "tickets": [
            {
                "ticket_id": 4101,
                "queue": "billing",
                "status": "closed",
                "summary": "Duplicate invoice raised twice",
                "comment_count": 0,
            },
            {
                "ticket_id": 4102,
                "queue": "billing",
                "status": "open",
                "summary": "Invoice export fails for EU accounts",
                "comment_count": 1,
            },
            {
                "ticket_id": 4103,
                "queue": "shipping",
                "status": "open",
                "summary": "Label printer offline in DC2",
                "comment_count": 0,
            },
        ],
        "comments": [
            {
                "comment_id": 1,
                "ticket_id": 4102,
                "position": 1,
                "body": "Reproduced on staging with an EU billing address.",
            },
        ],
    },
    # Nothing blocked in shipping. Distractors: a *billing* ticket that is
    # blocked, and a shipping ticket that is open -- both near-misses on one
    # filter each, so an agent that drops either filter answers wrongly.
    "scn-empty": {
        "tickets": [
            {
                "ticket_id": 4102,
                "queue": "billing",
                "status": "blocked",
                "summary": "Invoice export fails for EU accounts",
                "comment_count": 1,
            },
            {
                "ticket_id": 4103,
                "queue": "shipping",
                "status": "open",
                "summary": "Label printer offline in DC2",
                "comment_count": 0,
            },
        ],
        "comments": [
            {
                "comment_id": 1,
                "ticket_id": 4102,
                "position": 1,
                "body": "Waiting on the payments team.",
            },
        ],
    },
    # One blocked billing ticket whose blocker is named only in its *last*
    # comment. Distractors: a billing ticket with a near-identical summary that
    # is not blocked, and a blocked ticket in the wrong queue.
    "scn-blocked": {
        "tickets": [
            {
                "ticket_id": 4102,
                "queue": "billing",
                "status": "blocked",
                "summary": "Invoice export fails for EU accounts",
                "comment_count": 2,
            },
            {
                "ticket_id": 4103,
                "queue": "billing",
                "status": "open",
                "summary": "Invoice export slow for EU accounts",
                "comment_count": 0,
            },
            {
                "ticket_id": 4104,
                "queue": "shipping",
                "status": "blocked",
                "summary": "Label printer offline in DC2",
                "comment_count": 1,
            },
        ],
        "comments": [
            {
                "comment_id": 1,
                "ticket_id": 4102,
                "position": 1,
                "body": "Reproduced on staging with an EU billing address.",
            },
            {
                "comment_id": 2,
                "ticket_id": 4102,
                "position": 2,
                "body": "Blocked on PAY-77 until the payments team ships the fix.",
            },
            {
                "comment_id": 3,
                "ticket_id": 4104,
                "position": 1,
                "body": "Replacement printer ordered.",
            },
        ],
    },
    # No ticket 4109 anywhere. Distractors: two tickets whose ids bracket it,
    # so an agent that fabricates rather than reports absence has something
    # plausible to fabricate from.
    "scn-missing": {
        "tickets": [
            {
                "ticket_id": 4102,
                "queue": "billing",
                "status": "open",
                "summary": "Invoice export fails for EU accounts",
                "comment_count": 0,
            },
            {
                "ticket_id": 4110,
                "queue": "billing",
                "status": "closed",
                "summary": "Invoice export fixed for EU accounts",
                "comment_count": 0,
            },
        ],
        "comments": [],
    },
}


def toy_seed(scenario_id: str, **over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "collections": {
            name: [dict(record) for record in records]
            for name, records in _SEEDS[scenario_id].items()
        },
    }
    payload.update(over)
    return payload


# **The `answer_excludes` grounding rule, as the gate actually states it.**
# `refs._check_reachability` requires an `answer_excludes` *pointer* to resolve
# to nothing or to something empty. That is a rule about the pointer, and only
# about the pointer. The excluded *string* may perfectly well appear elsewhere in
# the same seed -- and in an absence-shaped scenario it usually must, because
# every plausible near-miss is in the seed by construction, which is the only
# reason the test discriminates at all. Both exclusions below are exactly that
# shape: each names a summary that another ticket in its own seed carries, while
# its pointer addresses a record index the seed does not fill. Layer 2 is
# correctly silent on both, because both pointers resolve to nothing.
#
# So the exclusions ground in the *absence of a further record*, which is exactly
# the log-does-not-say shape section 4 says this field exists for, and each
# `rationale` says so in words, because a reviewer reading the packet has to be
# able to tell a deliberate absence from a broken pointer.
#
# **A known defect in these two model answers, recorded here rather than fixed.**
# Because the excluded string is present in the seed, an agent that answers
# correctly *and more informatively* trips the exclusion: "nothing in shipping is
# blocked; the one shipping ticket, 'Label printer offline in DC2', is open" is a
# better answer than the reference and scores 0.5 instead of 1.0. Nothing
# mechanical catches that -- the pointer resolves to nothing, so the reachability
# gate is satisfied -- which makes it a judgment the author owes, and
# `rb-instantiate`'s Method says so in those terms. Re-deriving these labels
# belongs with a deliberate re-record rather than an edit here: the reward each
# exclusion feeds is pinned in three separate places, so changing the value alone
# would move numbers other tests assert.
_ORACLES: dict[str, dict[str, Any]] = {
    "scn-open": {
        "answer_reference": "Ticket 4102 is the one open billing ticket.",
        "assertions": [
            {
                "kind": "value_equals",
                "target": "answer",
                "value": "4102",
                "rationale": "the open billing ticket's id, as a standalone token: an answer "
                "naming 41020 or 14102 has not identified this ticket",
                "grounded_in": {"seed_pointer": "/collections/tickets/1/ticket_id"},
            },
            {
                "kind": "tool_called",
                "target": "query_tickets.find_tickets",
                "value": "at least once",
                "rationale": "the queue must be queried rather than guessed at",
                "capability_id": "cap-find-tickets",
            },
        ],
        "trajectory": {
            "match": "subset",
            "operations": [{"capability_id": "cap-find-tickets", "args": {"queue": "billing"}}],
        },
    },
    "scn-empty": {
        "answer_reference": "Nothing in the shipping queue is blocked.",
        "assertions": [
            {
                "kind": "answer_excludes",
                "target": "answer",
                "value": "Label printer offline in DC2",
                "rationale": "the shipping queue holds exactly one ticket and it is open, so "
                "there is no blocked shipping ticket to describe; the pointer "
                "resolves to nothing because the seed has no second shipping "
                "record, and naming this ticket's summary is fabrication",
                "grounded_in": {"seed_pointer": "/collections/tickets/2"},
            },
            {
                "kind": "tool_called",
                "target": "query_tickets.find_tickets",
                "value": "at least once",
                "rationale": "an empty result must be established by querying, not assumed",
                "capability_id": "cap-find-tickets",
            },
        ],
        "trajectory": {
            "match": "subset",
            "operations": [
                {
                    "capability_id": "cap-find-tickets",
                    "args": {"queue": "shipping", "status": "blocked"},
                }
            ],
        },
    },
    "scn-blocked": {
        "answer_reference": "Ticket 4102 is blocked on PAY-77.",
        "assertions": [
            {
                "kind": "value_equals",
                "target": "answer",
                "value": "4102",
                "rationale": "the blocked ticket's id, and not 4103's, which differs only in "
                "its summary wording",
                "grounded_in": {"seed_pointer": "/collections/tickets/0/ticket_id"},
            },
            {
                "kind": "answer_contains",
                "target": "answer",
                "value": "PAY-77",
                "rationale": "the blocker is named only in the ticket's last comment, so an "
                "answer carrying it proves the comments were read",
                "grounded_in": {"seed_pointer": "/collections/comments/1/body"},
            },
            {
                "kind": "tool_called",
                "target": "query_tickets.get_ticket",
                "value": "at least once",
                "rationale": "the blocker is not in the find_tickets result, so the detail "
                "call is the second hop this scenario claims",
                "capability_id": "cap-get-ticket",
            },
        ],
        "trajectory": {
            "match": "subset",
            "operations": [
                {
                    "capability_id": "cap-find-tickets",
                    "args": {"queue": "billing", "status": "blocked"},
                },
                {"capability_id": "cap-get-ticket", "args": {"ticket_id": 4102}},
            ],
        },
    },
    "scn-missing": {
        "answer_reference": "There is no ticket 4109.",
        "assertions": [
            {
                "kind": "answer_excludes",
                "target": "answer",
                "value": "Invoice export fails for EU accounts",
                "rationale": "the seed holds two tickets, 4102 and 4110, and neither is 4109; "
                "the pointer resolves to nothing because there is no third "
                "record, so attributing a neighbouring ticket's summary to 4109 "
                "is the fabrication this test exists to catch",
                "grounded_in": {"seed_pointer": "/collections/tickets/2"},
            },
            {
                "kind": "tool_called",
                "target": "query_tickets.get_ticket",
                "value": "at least once",
                "rationale": "absence must be established by looking, not by assuming",
                "capability_id": "cap-get-ticket",
            },
        ],
        "trajectory": {
            "match": "subset",
            "operations": [{"capability_id": "cap-get-ticket", "args": {"ticket_id": 4109}}],
        },
    },
}

_RATIONALES: dict[str, str] = {
    "scn-open": "Distractors: 4101 is billing but closed; 4103 is open but in shipping. "
    "An agent must apply both filters.",
    "scn-empty": "Distractors: 4102 is blocked but in billing; 4103 is in shipping but "
    "open. Dropping either filter yields a non-empty answer.",
    "scn-blocked": "Distractors: 4103's summary differs from 4102's by one word and it is "
    "not blocked; 4104 is blocked but in shipping. The blocker is in the "
    "second comment only, so an agent that reads the first stops short.",
    "scn-missing": "Distractors: 4102 and 4110 bracket the requested 4109, and 4110's "
    "summary reads as a resolution of 4102's, so a fabricated answer has "
    "plausible material to draw on.",
}


def toy_expected(scenario_id: str, **over: Any) -> dict[str, Any]:
    """The oracle, with the scenario's discriminating_fact copied verbatim.

    Verbatim because refs.check_instances compares the two strings: a paraphrase
    is indistinguishable from substituting an easier fact, which is the exact
    move the field exists to prevent.
    """
    scenario = next(s for s in _SCENARIOS if s["id"] == scenario_id)
    oracle = _ORACLES[scenario_id]
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "scenario_id": scenario_id,
        "discriminating_fact": scenario["discriminating_fact"],
        "answer_reference": oracle["answer_reference"],
        "assertions": [dict(a) for a in oracle["assertions"]],
        "trajectory": dict(oracle["trajectory"]),
        "completion": {"status": "ok", "nonempty_answer": True},
    }
    payload.update(over)
    return payload


def toy_rationale(scenario_id: str) -> str:
    """The reviewer-facing note section 6 step 6 requires.

    Its whole job is to let a reviewer judge fairness without reverse-
    engineering the seed, so it names the distractors and why each is a
    near-miss.
    """
    scenario = next(s for s in _SCENARIOS if s["id"] == scenario_id)
    return (
        f"# {scenario['title']}\n\n"
        f"**Discriminating fact:** {scenario['discriminating_fact']}\n\n"
        f"**Distractor set.** {_RATIONALES[scenario_id]}\n"
    )


def toy_verdict(scenario_id: str, **over: Any) -> dict[str, Any]:
    """An accepting adversary whose call count matches the claimed hop depth.

    Matching rather than lower: refs.check_verdicts requires the
    difficulty_overstated flag when the adversary beats the claim, and a golden
    fixture that needed the flag would be asserting a defect is tolerated
    rather than that a clean run is clean.
    """
    scenario = next(s for s in _SCENARIOS if s["id"] == scenario_id)
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "scenario_id": scenario_id,
        "uniquely_determined": True,
        "derivable_without_guessing": True,
        "minimum_tool_calls_found": scenario["hop_depth"],
        "verdict": "accept",
        "notes": (
            "answered independently from the seed and matched the oracle; the distractors "
            "rule out every second reading I could construct"
        ),
    }
    payload.update(over)
    return payload


# Named checkpoints build_toy_run's `upto` accepts, in pipeline order. Not
# paths.STAGES verbatim: this fixture writes nothing for "emit" or "smoke" (no
# suite package, no report), so those two are deliberately absent rather than
# silently accepted and ignored. "survey" is absent for a related reason: a
# stop right after survey() would add no hand-authored content of this
# fixture's own, so the checkpoint would be a pure alias for the one-line
# survey.survey() call the tests that want a bare catalogue already make --
# and a checkpoint indistinguishable from an earlier one is the very thing
# this tuple's exclusions exist to prevent. A name outside the tuple raises;
# it is never silently accepted.
#
# The five "triage-*" names ARE here, and each writes something the one before
# it does not: the slice plan and its shards, 00-objective.json, one
# 00-dispositions/ part per slice, 00-audit.json, and the sealed
# 00-triage.json. They are also the only checkpoints that do not go through
# intake at all -- the family runs ahead of it, so a triage run is minted by
# survey over TOY_DIR and stops before the manifest exists (see
# _build_toy_triage_run). build_toy_catalogue_and_triage() below remains the
# separate, explicit helper for the other shape: an already-intaken run that a
# test needs a catalogue and a sealed triage record laid over.
_TRIAGE_UPTO_STAGES: tuple[str, ...] = (
    "triage-slices",
    "triage-objective",
    "triage-rule",
    "triage-audit",
    "triage-seal",
)
_UPTO_STAGES: tuple[str, ...] = (
    *_TRIAGE_UPTO_STAGES,
    "intake",
    "extract",
    # Two checkpoints for the reconcile family rather than eight: "reconcile-gaps"
    # is every partial written with no world model yet -- the state the seal and
    # the layer-2 part checkers are tested against -- and "reconcile-seal" is the
    # assembled world model every later stage reads. The intermediate states
    # between passes have no consumer, and a checkpoint nobody stops at is a
    # helper this module already has too many requests for.
    "reconcile-gaps",
    "reconcile-seal",
    # Four checkpoints across the loop rather than five: "propose" is every part
    # written with nothing sealed -- the state check_scenario_parts and the
    # part schemas are tested against -- and "propose-seal" is the assembled
    # scenario list score reads. "score" is the judgments with no report yet,
    # and "score-seal" is the coverage document every later stage and gate 2
    # read. "propose-batches" gets no checkpoint: nothing stops there, and a
    # checkpoint nobody stops at is a helper this module already has too many
    # requests for.
    "propose",
    "propose-seal",
    "score",
    "score-seal",
    "instantiate",
    "challenge",
)
_UPTO_INDEX: dict[str, int] = {name: i for i, name in enumerate(_UPTO_STAGES)}


def build_toy_run(
    runs_dir: Path,
    *,
    upto: str | None = None,
    slice_cap: int | None = None,
    **intake_kwargs: Any,
) -> RunPaths:
    """Mint a run with real intake, then write every hand-authored artifact
    up to and including the named stage.

    intake is real rather than simulated so the manifest's sha256, stored_as and
    the 00-inputs/ copies are produced by the code that produces them in a real
    run -- refs.check_inputs re-hashes those bytes, and a hand-written digest
    would only ever satisfy a check that was not looking.

    A `upto` naming one of the staged-triage passes is minted by survey rather
    than intake and returns before intake ever runs -- see
    _build_toy_triage_run, which this delegates to. `slice_cap` is that
    branch's only extra knob, and it is a named parameter rather than another
    **intake_kwargs entry precisely because it must never reach intake(), which
    takes no such argument. Passing it with a post-intake checkpoint raises:
    there is no catalogue to partition on that path, and a cap silently
    ignored would leave a caller believing their run was sliced.

    `upto` stops the run after one named stage, so a later task can hand a
    skill a run populated up to but not past the stage under test: handing
    rb-propose a run that does not yet contain 01-world-model.json tests
    nothing, and handing a reconcile pass one that already does tests nothing
    either. `upto=None` (the default) writes everything this fixture knows how
    to write, through challenge.

    The loop's four checkpoints differ from each other in what is SEALED rather
    than in what was authored: `upto="propose"` leaves round 1's batch plan and
    its one propose part on disk with no 02-scenarios.json at all,
    `upto="propose-seal"` adds the assembled scenario list with every scenario
    still `proposed`, `upto="score"` adds the rulings with no coverage document,
    and `upto="score-seal"` folds those rulings and composes the report. Both
    sealed documents come from rounds.seal_scenarios and rounds.seal_score, never
    from a literal here -- a fixture that hand-wrote one could disagree with the
    seal, and this fixture is the model answer a skill imitates.

    An `upto` outside _UPTO_STAGES raises rather than silently building
    everything or silently building nothing: a typoed stage name silently
    accepted either way would hand a later task's test a run one stage off
    from what it asked for, with nothing to say so.
    """
    if upto is not None and upto not in _UPTO_INDEX:
        raise ValueError(
            f"unknown stage {upto!r} for build_toy_run(upto=...); expected one of "
            f"{_UPTO_STAGES} or None for everything"
        )
    if slice_cap is not None and upto not in _TRIAGE_UPTO_STAGES:
        raise ValueError(
            f"slice_cap is only meaningful for the staged-triage checkpoints "
            f"{_TRIAGE_UPTO_STAGES}, not for upto={upto!r}: a run minted through intake "
            "--input has no catalogue to partition"
        )
    if upto in _TRIAGE_UPTO_STAGES:
        return _build_toy_triage_run(runs_dir, upto=upto, slice_cap=slice_cap, **intake_kwargs)
    stop = _UPTO_INDEX[upto] if upto is not None else _UPTO_INDEX["challenge"]

    run = intake(
        inputs=list(INPUT_FILES),
        runs_dir=Path(runs_dir),
        target_name="ticketq",
        target_interface="mcp",
        max_rounds=intake_kwargs.pop("max_rounds", 2),
        max_scenarios=intake_kwargs.pop("max_scenarios", 8),
        **intake_kwargs,
    )
    if stop < _UPTO_INDEX["extract"]:
        return run

    for artifact_id in ARTIFACT_IDS:
        write_json(run.claims(artifact_id), toy_claims(artifact_id))
    if stop < _UPTO_INDEX["reconcile-gaps"]:
        return run

    parts = split_world_model()
    write_json(run.subjects, parts["subjects"])
    for subject_id, part in parts["contradictions"].items():
        write_json(run.contradiction_part(subject_id), part)
    write_json(run.capabilities_part, parts["capabilities"])
    write_json(run.outcomes_part, parts["outcomes"])
    write_json(run.entities_part, parts["entities"])
    write_json(run.goals_part, parts["goals"])
    write_json(run.gaps_part, parts["gaps"])
    if stop < _UPTO_INDEX["reconcile-seal"]:
        return run

    # Sealed by the real seal, not by writing toy_world_model() here. Same reason
    # intake is real in this builder: the artifact every later stage reads is
    # produced by the code that produces it in a real run, so a defect in the
    # join or the denominator cannot hide behind a hand-written answer.
    from rubrica.reconcile import seal

    sealed, findings = seal(run)
    assert not findings, f"the toy partials must seal cleanly: {findings}"
    assert sealed == run.world_model
    if stop < _UPTO_INDEX["propose"]:
        return run

    # propose-batches is code and has no checkpoint of its own, so its plan comes
    # from the real write_batches rather than from a literal here. That is not
    # tidiness: refs.check_scenario_parts resolves every scenario's
    # provenance.hole_refs against this round's batch roster, so a hand-written
    # plan could disagree with the partition the code would actually have
    # produced and the golden fixture would carry a finding for it.
    plan = rounds.write_batches(run, round_n=1)
    assert plan == run.batches(1), f"the toy world must partition into one round-1 plan: {plan}"
    write_json(run.scenario_part(1, TOY_BATCH_ID), toy_scenario_part())
    if stop < _UPTO_INDEX["propose-seal"]:
        return run

    # Sealed by the real seal for the reason intake and rubrica.reconcile.seal
    # are real above: 02-scenarios.json is code output, and a fixture that
    # hand-wrote it could disagree with the seal every later stage's copy came
    # from. seal_scenarios is a pure function of the parts and the rulings, so
    # calling it here and again below is the same call the orchestrator makes
    # twice per round -- once so score has a document to read, once so
    # instantiate sees the statuses.
    sealed, findings = rounds.seal_scenarios(run)
    assert not findings, f"the toy propose part must seal cleanly: {findings}"
    assert sealed == run.scenarios
    if stop < _UPTO_INDEX["score"]:
        return run

    write_json(run.score_part(1), toy_score_part())
    if stop < _UPTO_INDEX["score-seal"]:
        return run

    # The second seal of the round, and the order matters: the rulings have to be
    # folded into 02-scenarios.json before seal_score computes the matrices, or
    # scn-open-dup would still be `proposed` and would credit
    # cell:cap-find-tickets/oc-found as a live scenario nothing will ever ship.
    sealed, findings = rounds.seal_scenarios(run)
    assert not findings, f"the toy score rulings must fold cleanly: {findings}"
    assert sealed == run.scenarios
    coverage, findings = rounds.seal_score(run, round_n=1)
    assert not findings, f"the toy score part must seal cleanly: {findings}"
    assert coverage == run.coverage_round(1)
    if stop < _UPTO_INDEX["instantiate"]:
        return run

    for sid in SIDS:
        write_json(run.seed(sid), toy_seed(sid))
        write_json(run.expected(sid), toy_expected(sid))
        run.rationale(sid).write_text(toy_rationale(sid), encoding="utf-8")
    if stop < _UPTO_INDEX["challenge"]:
        return run

    for sid in SIDS:
        write_json(run.verdict(sid), toy_verdict(sid))
    return run


def _build_toy_triage_run(
    runs_dir: Path, *, upto: str, slice_cap: int | None = None, **survey_kwargs: Any
) -> RunPaths:
    """The staged-triage half of build_toy_run: survey the golden world, then
    write each pass's part up to and including `upto`.

    survey rather than intake, and no intake at all: the family runs *ahead* of
    intake in paths.STAGES, gate 0 stands between the sealed record and the
    manifest, and a fixture that minted a manifest here would be a run one gate
    past where its checkpoint claims to stop.

    Everything structural is written by the code that writes it in a real run
    -- survey walks TOY_DIR, write_slices partitions the catalogue survey
    wrote, seal assembles 00-triage.json from the staged parts. The only
    hand-authored content is the *judgment* each prompt pass supplies: which
    surfaces the objective names, and how each candidate is ruled. A
    hand-written plan or a hand-written sealed record would only ever satisfy a
    check that was not looking.
    """
    stop = _UPTO_INDEX[upto]
    run = survey(
        corpus_roots=[TOY_DIR],
        runs_dir=Path(runs_dir),
        target_name="ticketq",
        target_interface="mcp",
        objective="breadth",
        max_rounds=survey_kwargs.pop("max_rounds", 2),
        max_scenarios=survey_kwargs.pop("max_scenarios", 8),
        **survey_kwargs,
    )
    # The cap is omitted rather than defaulted when no override was asked for:
    # slices.DEFAULT_SLICE_BYTES is the one home for that number, and restating
    # it here would give the fixture a second copy to drift from. At that
    # default the whole toy catalogue is a single slice (4102 row-bytes against
    # 65536), which is why slice_cap exists -- 4096 is the smallest round cap
    # above the largest single row (api-json, 2381) and partitions the three
    # candidates in two.
    if slice_cap is None:
        write_slices(run)
    else:
        write_slices(run, cap=slice_cap)
    if stop < _UPTO_INDEX["triage-objective"]:
        return run

    _write_toy_objective(run)
    if stop < _UPTO_INDEX["triage-rule"]:
        return run

    _write_toy_disposition_parts(run)
    if stop < _UPTO_INDEX["triage-audit"]:
        return run

    _write_toy_audit(run)
    if stop < _UPTO_INDEX["triage-seal"]:
        return run

    _seal_toy_triage(run)
    return run


# One surface name per catalogue `kind`, for the objective pass's map-level
# reading. Prose rather than the raw kind string because gate 0's brief renders
# these for a human to read; the .get fallback keeps a catalogue that grows a
# fourth kind valid -- surface.name only has to be non-empty -- rather than
# raising inside a fixture builder.
_SURFACE_NAMES: dict[str, str] = {
    "mcp_tool_schema": "tool schema",
    "design_doc": "operator notes",
    "trace": "captured trajectory",
}


def _toy_surfaces(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One surface per candidate kind, both weights computed from the catalogue.

    refs.check_objective recomputes weight.candidates from the surface's own
    distinct evidence ids and weight.bytes by summing each evidence
    candidate's catalogue `bytes` field, so a literal weight here would be a
    second copy of the catalogue's arithmetic waiting to disagree with it --
    which is how the pre-split helper carried `"bytes": 1` unnoticed, back
    when nothing recomputed it. `bytes` is each source file's own size, never
    slices.row_bytes' serialized-row size: the skeleton clamp makes a row size
    saturate, so it stops discriminating exactly where a weight must.
    """
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        by_kind.setdefault(candidate["kind"], []).append(candidate)
    return [
        {
            "name": _SURFACE_NAMES.get(kind, kind),
            "evidence": [candidate["candidate_id"] for candidate in members],
            "weight": {
                "candidates": len(members),
                "bytes": sum(candidate["bytes"] for candidate in members),
            },
        }
        for kind, members in sorted(by_kind.items())
    ]


def _write_toy_objective(run: RunPaths) -> None:
    """00-objective.json: rb-triage-objective's ruling over the toy catalogue.

    predicted_surface_count equals the number of surfaces named, which is the
    non-divergent case rb-triage-audit's own comparison expects here: it counts
    every predicted surface with an admitted candidate anywhere in the parts
    plus every distinct observed_surfaces entry, and in this fixture every
    candidate is admitted and no part observes anything the objective missed.
    """
    catalogue = read_json(run.catalogue)
    surfaces = _toy_surfaces(catalogue["candidates"])
    write_json(
        run.objective,
        {
            "schema_version": "0.1",
            "run_id": catalogue["run_id"],
            "predicted_surface_count": len(surfaces),
            "objective_review": {
                "declared_objective": "breadth",
                "supported": True,
                "surfaces": surfaces,
            },
        },
    )


def _write_toy_disposition_parts(run: RunPaths) -> None:
    """One 00-dispositions/<slice_id>.json per slice the plan declares.

    Membership is read from 00-slices.json rather than from ARTIFACT_IDS, so
    the parts follow whatever partition the cap in force actually produced: one
    part at the default cap, two at slice_cap=4096. That is what makes
    refs.check_disposition_parts' "every slice has a part" clause a real check
    on the multi-slice fixture rather than a tautology over a single member.

    Every candidate is admitted, matching what build_toy_catalogue_and_triage
    has always produced: the golden world's three files are exactly the three
    inputs every downstream toy fixture expects the manifest to carry, so a
    decline here would put the triage record and that manifest at odds.

    observed_surfaces is [] by rb-triage-rule's own rule -- a member reports
    only the surfaces 00-objective.json did not already name, and the objective
    above names one per kind, which is all of them.
    """
    plan = read_json(run.slices)
    for entry in plan["slices"]:
        write_json(
            run.disposition_part(entry["id"]),
            {
                "schema_version": "0.1",
                "run_id": plan["run_id"],
                "slice_id": entry["id"],
                "dispositions": [
                    {
                        "candidate_id": candidate_id,
                        "disposition": "admit",
                        "reason": f"{candidate_id} is part of the golden toy world",
                        # The member's own ranking within its own slice. The
                        # seal renumbers admits across every part, so this
                        # exercises its member-priority sort rather than
                        # dictating the sealed order.
                        "priority": position,
                        "authority": "triage",
                    }
                    for position, candidate_id in enumerate(entry["candidate_ids"], start=1)
                ],
                "observed_surfaces": [],
                "deficiency_notes": [],
            },
        )


def _write_toy_audit(run: RunPaths) -> None:
    """00-audit.json: both arrays empty, which is a claim rather than a gap.

    audit-0.1.json's own description makes that point -- a run with no
    deficiencies has swept every slice and found nothing worth projecting,
    rather than skipped the check. The toy world admits everything, so there is
    no digest_insufficient or needs_projection decline for a deficiency or a
    projection to answer, and seal.seal's item 5 has nothing to refuse.
    """
    write_json(
        run.audit,
        {
            "schema_version": "0.1",
            "run_id": read_json(run.slices)["run_id"],
            "deficiencies": [],
            "projections": [],
        },
    )


def _seal_toy_triage(run: RunPaths) -> None:
    """00-triage.json, assembled by seal.seal from the staged parts.

    Raises on a finding rather than returning quietly: seal writes nothing when
    it reports anything, so a silent return would hand a caller a "sealed"
    checkpoint with no 00-triage.json in it, and the failure would surface
    later against whichever artifact read it next instead of here.
    """
    _, findings = seal(run)
    if findings:
        raise AssertionError(
            "the toy fixture's staged triage parts do not seal: "
            + "; ".join(f.message for f in findings)
        )


def build_toy_catalogue_and_triage(run: RunPaths) -> None:
    """Write 00-catalogue.json and 00-triage.json for the toy world's three
    inputs, admitting all of them under their real ARTIFACT_IDS.

    Deliberately separate from build_toy_run, and does not call or reroute
    its intake() call: a run that has been through real intake --input (as
    every existing toy run has) has no catalogue and no triage record, and
    spec §7.1 rules that this is not a finding -- so build_toy_run must keep
    minting exactly the way it always has. This helper exists only for a test
    that needs a catalogue and a triage record to check *against* the same
    manifest, and admits every candidate under its real ARTIFACT_IDS so that
    a manifest written by real intake() lines up with it exactly, with no
    collision suffix in play.

    The catalogue below stays hand-written for exactly that reason -- the
    candidate ids have to be ARTIFACT_IDS, not whatever a survey of some other
    directory would slug -- but 00-triage.json no longer is. It is written by
    seal.seal over the same staged parts a real run seals, laid down here by
    the same four writers _build_toy_triage_run uses, so the record this helper
    produces is one the real code assembles rather than a literal that merely
    resembles one.
    """
    candidates = [
        {
            "candidate_id": artifact_id,
            "origin": "corpus",
            "path": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256_of(path),
            "kind": classify(path),
            "admissible": True,
            "digest": {},
        }
        for artifact_id, path in zip(ARTIFACT_IDS, INPUT_FILES, strict=True)
    ]
    write_json(
        run.catalogue,
        {
            "schema_version": "0.1",
            "run_id": run.root.name,
            "created_utc": "2026-08-14T21:30:00Z",
            "request": {
                "target": {"name": "ticketq", "interface": "mcp"},
                "objective": "breadth",
                "corpus_roots": [str(TOY_DIR)],
                "limits": {"max_rounds": 2, "max_scenarios": 8},
            },
            "policy": {
                "exclusion_reasons": ["binary"],
                "explode_min_elements": 3,
                "explode_min_common_keys": 3,
                "digest_body_chars": 2000,
                "max_candidates": 500,
                "max_catalogue_bytes": 5_000_000,
            },
            "candidates": candidates,
            "excluded": [],
        },
    )
    # The staged parts, then the seal -- the same sequence a real run takes
    # from triage-slices to triage-seal, over the catalogue just written. No
    # cap override: this helper's catalogue is one slice at any cap the toy
    # world can produce, and a caller who needs the fan-out partitioned asks
    # build_toy_run for it with slice_cap instead.
    write_slices(run)
    _write_toy_objective(run)
    _write_toy_disposition_parts(run)
    _write_toy_audit(run)
    _seal_toy_triage(run)


# Scripted agents for the golden smoke run. Real subprocesses printing real
# JSONL, never mocks: the properties that matter are all about the other end of
# the pipe, and smoke's contract with an agent is a transcript on stdout.
#
# The oracle reads golden.json, which is what the design spec means by "an
# oracle agent handed the reference answer". It is a test of the test suite: if
# it does not pass nearly everything, the labels or the verifier are broken.
ORACLE_SCRIPT = """\
import json, pathlib
golden = json.loads(pathlib.Path("golden.json").read_text())
for call in golden["tool_calls"]:
    print(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": call["tool"], "input": call["args"]}]}}))
print(json.dumps({"type": "result", "subtype": "success", "result": golden["answer"]}))
"""

# No tools, no answer. Scores 0 on the two positive-assertion tasks and 0.4 on
# the two absence-shaped ones, because an exclusion satisfied by absence scores
# a point by design -- which is exactly why each absence task also carries a
# tool_called assertion this agent fails.
WEAK_SCRIPT = """\
import json
print(json.dumps({"type": "result", "subtype": "success",
                  "result": "I do not have enough information to say."}))
"""

# Makes every call and then paraphrases without the tokens the oracle asserts:
# full trajectory credit, partial assertion credit. A middling agent rather
# than a broken one, which is the spread that matters.
UNDER_TEST_SCRIPT = """\
import json, pathlib
golden = json.loads(pathlib.Path("golden.json").read_text())
for call in golden["tool_calls"]:
    print(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": call["tool"], "input": call["args"]}]}}))
print(json.dumps({"type": "result", "subtype": "success",
                  "result": "I looked at the queue and found the relevant ticket."}))
"""

_SCRIPTS = {
    "weak_baseline": WEAK_SCRIPT,
    "under_test": UNDER_TEST_SCRIPT,
    "oracle": ORACLE_SCRIPT,
}


def toy_roster(tmp_path: Path) -> tuple[Any, ...]:
    """AgentSpecs for the three roles, backed by scripts written under tmp_path.

    sys.executable rather than a shebang: the interpreter running the tests is
    the one that must run the scripts, and a shebang would depend on the
    executable bit and on `python` resolving to 3.13 on PATH.
    """
    from rubrica.smoke import AgentSpec

    specs = []
    for role, body in _SCRIPTS.items():
        script = Path(tmp_path) / f"{role}.py"
        script.write_text(body, encoding="utf-8")
        specs.append(
            AgentSpec(
                role=role,
                model=f"scripted-{role}",
                command=(sys.executable, str(script)),
                timeout_sec=60.0,
            )
        )
    return tuple(specs)
