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

from pathlib import Path
from typing import Any

from testgen.artifacts import write_json
from testgen.intake import intake
from testgen.paths import RunPaths

TOY_DIR = Path(__file__).resolve().parent / "fixtures" / "toy"

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
                    {"name": "queue", "type": "string", "required": True},
                    {"name": "status", "type": "string", "required": False},
                ],
                "outcome_classes": [
                    {
                        "id": "oc-found",
                        "kind": "success",
                        "description": "one or more tickets match the filters",
                    },
                    {
                        "id": "oc-none",
                        "kind": "empty",
                        "description": "no ticket matches the filters",
                    },
                ],
                "claims": ["clm-api-001", "clm-api-005", "clm-trace-001"],
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
                    },
                    {
                        "id": "oc-missing",
                        "kind": "not_found",
                        "description": "no ticket has that id, which is an error",
                    },
                ],
                "claims": ["clm-api-002", "clm-notes-004"],
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
                    },
                    {
                        "id": "inv-ticket-id-unique",
                        "statement": "ticket_id is unique across every queue",
                        "machine": {
                            "form": "unique",
                            "collection": "tickets",
                            "field": "ticket_id",
                        },
                    },
                ],
                "claims": ["clm-api-003", "clm-notes-005", "clm-notes-006"],
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
                "claims": ["clm-notes-002"],
            },
            {
                "id": "goal-explain",
                "actor_id": "act-support",
                "statement": "Explain why a ticket is stuck",
                "expected_hop_depths": [2],
                "claims": ["clm-notes-003"],
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
                    "the notes describe the current contract and the trace is one captured "
                    "call that predates it, so oc-missing is modelled as an error; recorded "
                    "rather than dropped because a scenario built on the trace's behaviour "
                    "would be labelled against a world the target no longer has"
                ),
            }
        ],
        "gaps": [],
        "denominator": {"version": 1, "capability_cells": 4, "goals": 2},
    }
    payload.update(over)
    return payload


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


def _scenarios_before_score() -> dict[str, Any]:
    """02-scenarios.json as tg-propose would have left it: every scenario
    `proposed`, none marked `duplicate_of` yet.

    Used only by build_toy_run(upto="propose"). A run handed to the score stage
    with every scenario already `active` -- and the near-duplicate already
    folded -- cannot show whether score promoted anything or ruled on the
    duplicate; this is what makes that state reachable as its own fixture
    rather than only as toy_scenarios()'s post-score result.
    """
    scenarios = []
    for scenario in _SCENARIOS:
        scenario = dict(scenario)
        scenario["status"] = "proposed"
        scenario.pop("duplicate_of", None)
        scenarios.append(scenario)
    return {
        "schema_version": "0.1",
        "denominator_version": 1,
        "scenarios": scenarios,
    }


def toy_coverage(**over: Any) -> dict[str, Any]:
    """Full coverage of four cells and two goals, so holes is empty.

    A hole here would have to name a covered row, which refs.check_coverage
    reports in both directions -- so "fully covered" and "no holes" are one
    statement, not two.
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
                    "scenario_ids": ["scn-open", "scn-blocked"],
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
                    "scenario_ids": ["scn-open", "scn-empty", "scn-missing"],
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


# **The `answer_excludes` grounding rule.** `refs._check_reachability` requires
# an `answer_excludes` pointer to resolve to *nothing*: the seed must not
# contain what the assertion says it lacks. So an exclusion can never name a
# value that is present -- excluding a distractor that exists is not
# expressible this way, and is expressed instead by `value_equals`, which
# requires the answer to carry the right token. The exclusions below therefore
# ground in the *absence of a further record*, which is exactly the
# log-does-not-say shape section 4 says this field exists for. Each
# `rationale` says so in words, because a reviewer reading the packet has to be
# able to tell a deliberate absence from a broken pointer.
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
# silently accepted and ignored.
_UPTO_STAGES: tuple[str, ...] = (
    "intake",
    "extract",
    "reconcile",
    "propose",
    "score",
    "instantiate",
    "challenge",
)
_UPTO_INDEX: dict[str, int] = {name: i for i, name in enumerate(_UPTO_STAGES)}


def build_toy_run(runs_dir: Path, *, upto: str | None = None, **intake_kwargs: Any) -> RunPaths:
    """Mint a run with real intake, then write every hand-authored artifact
    up to and including the named stage.

    intake is real rather than simulated so the manifest's sha256, stored_as and
    the 00-inputs/ copies are produced by the code that produces them in a real
    run -- refs.check_inputs re-hashes those bytes, and a hand-written digest
    would only ever satisfy a check that was not looking.

    `upto` stops the run after one named stage, so a later task can hand a
    skill a run populated up to but not past the stage under test: handing
    tg-reconcile a run that already contains 01-world-model.json tests
    nothing. `upto=None` (the default) writes everything this fixture knows how
    to write, through challenge.

    `upto="propose"` is the one stage whose content differs from the
    steady-state artifact rather than just stopping early: it writes every
    scenario `proposed` with no `duplicate_of`, via _scenarios_before_score(),
    because a fixture handed to the score stage with the duplicate already
    folded could never show whether score did the folding or found nothing to
    do.

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
    if stop < _UPTO_INDEX["reconcile"]:
        return run

    write_json(run.world_model, toy_world_model())
    if stop < _UPTO_INDEX["propose"]:
        return run
    if stop == _UPTO_INDEX["propose"]:
        write_json(run.scenarios, _scenarios_before_score())
        return run

    write_json(run.scenarios, toy_scenarios())
    if stop < _UPTO_INDEX["score"]:
        return run

    write_json(run.coverage_round(1), toy_coverage())
    write_json(run.coverage_latest, toy_coverage())
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
