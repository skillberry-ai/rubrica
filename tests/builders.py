"""Minimal schema-valid artifact payloads, for mutation in tests.

Each builder returns the smallest payload its schema accepts. Tests override
one key to construct a negative case, which keeps each test's intent visible
instead of buried in fifty lines of valid boilerplate.
"""

from __future__ import annotations

import hashlib
from typing import Any

# The registered input copy that minimal_manifest describes. The manifest's
# sha256 is the real digest of these bytes, so any state builder that writes
# them satisfies refs.check_inputs by construction rather than by tolerance --
# the previous "a" * 64 placeholder could only ever have passed a check that
# was not looking.
MINIMAL_INPUT_NAME = "aap2-api.json"
MINIMAL_INPUT_BYTES = b'{"tools": [{"name": "query_aap2"}]}\n'


def minimal_claims(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "artifact_id": "aap2-api",
        "claims": [
            {
                "id": "clm-001",
                "kind": "capability",
                "statement": "query_aap2 supports action=find_jobs",
                "evidence": [{"artifact_id": "aap2-api", "locator": "api.json#/tools/0"}],
                "confidence": "high",
                "derivation": "stated",
            }
        ],
    }
    payload.update(over)
    return payload


def minimal_world_model(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "target": {"name": "aap2", "interface": "mcp"},
        "capabilities": [
            {
                "id": "cap-find-jobs",
                "operation": "query_aap2.find_jobs",
                "binding": {"tool": "query_aap2", "fixed_args": {"action": "find_jobs"}},
                "params": [{"name": "controller", "type": "string", "required": True}],
                # Every outcome class carries `claims`, which $defs/outcome_class has
                # required since issue #6. One id, the same the capability cites: this
                # payload is the smallest thing the schema accepts, and clm-001 is the
                # only claim minimal_claims declares.
                "outcome_classes": [
                    {
                        "id": "oc-success",
                        "kind": "success",
                        "description": "jobs returned",
                        "claims": ["clm-001"],
                    },
                    {
                        "id": "oc-empty",
                        "kind": "empty",
                        "description": "no jobs match",
                        "claims": ["clm-001"],
                    },
                ],
                "claims": ["clm-001"],
                "confidence": "high",
            }
        ],
        "entities": [
            {
                "id": "ent-job",
                "name": "Job",
                "collection": "jobs",
                "fields": [
                    {"name": "job_id", "type": "integer"},
                    {"name": "status", "type": "string"},
                    {"name": "controller", "type": "string"},
                ],
                "claims": ["clm-001"],
            }
        ],
        "actors": [{"id": "act-sre", "name": "SRE", "claims": ["clm-001"]}],
        "goals": [
            {
                "id": "goal-triage",
                "actor_id": "act-sre",
                "statement": "Find out why a job failed",
                "expected_hop_depths": [1, 2],
                "claims": ["clm-001"],
            }
        ],
        "contradictions": [],
        "gaps": [],
        "denominator": {"version": 1, "capability_cells": 2, "goals": 1},
    }
    payload.update(over)
    return payload


def minimal_scenarios(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "denominator_version": 1,
        "scenarios": [
            {
                "id": "scn-001",
                "round": 1,
                "goal_id": "goal-triage",
                "actor_id": "act-sre",
                "title": "Find the failing job on prod0",
                "user_intent": "A job failed on prod0. Which one, and why?",
                "hop_depth": 2,
                "capability_refs": [
                    {"capability_id": "cap-find-jobs", "outcome_class_id": "oc-success"}
                ],
                "discriminating_fact": "exactly one prod0 job failed inside the window",
                "status": "active",
                "provenance": {
                    "hole_refs": ["cell:cap-find-jobs/oc-success"],
                    "claim_ids": ["clm-001"],
                    "round": 1,
                },
            }
        ],
    }
    payload.update(over)
    return payload


def minimal_coverage(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "round": 1,
        "denominator_version": 1,
        "capability_matrix": {
            "cells": [
                {
                    "capability_id": "cap-find-jobs",
                    "outcome_class_id": "oc-success",
                    "scenario_ids": ["scn-001"],
                    "covered": True,
                },
                {
                    "capability_id": "cap-find-jobs",
                    "outcome_class_id": "oc-empty",
                    "scenario_ids": [],
                    "covered": False,
                },
            ],
            "covered": 1,
            "total": 2,
            "pct": 0.5,
        },
        "goal_matrix": {
            "rows": [
                {
                    "goal_id": "goal-triage",
                    "scenario_ids": ["scn-001"],
                    "hop_depths_present": [2],
                    "hop_depths_expected": [1, 2],
                    "covered": False,
                }
            ],
            "covered": 0,
            "total": 1,
            "pct": 0.0,
        },
        "holes": [
            {
                "ref": "cell:cap-find-jobs/oc-empty",
                "reason": "not_yet_attempted",
                "justification": "no scenario has exercised the empty-result path yet",
            },
            {
                "ref": "goal:goal-triage",
                "reason": "not_yet_attempted",
                "justification": "only the 2-hop path is covered; hop depth 1 has no scenario",
            },
        ],
        "progress": {"new_cells_this_round": 1, "rounds_without_progress": 0},
        "verdict": "continue",
    }
    payload.update(over)
    return payload


def minimal_manifest(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "run_id": "run-20260806-120000",
        "created_utc": "2026-08-06T12:00:00Z",
        "target": {"name": "aap2", "interface": "mcp"},
        "inputs": [
            {
                "artifact_id": "aap2-api",
                "source_path": "harness-skills/parsec-aap2/api.json",
                "stored_as": MINIMAL_INPUT_NAME,
                "sha256": hashlib.sha256(MINIMAL_INPUT_BYTES).hexdigest(),
                "kind": "mcp_tool_schema",
                "bytes": len(MINIMAL_INPUT_BYTES),
            }
        ],
        # A real member of paths.STAGES, and a prompt one: manifest.stages records
        # the model, effort and skill digest of a *dispatched* stage, so keying
        # this on a code stage would describe an entry no run can produce. It was
        # keyed on "reconcile" until that stage became a family, which is the drift
        # the schema's propertyNames enum exists to catch.
        "stages": {
            "reconcile-subjects": {
                "model": "claude-opus-5",
                "effort": "high",
                "skill_sha256": "b" * 64,
            }
        },
        "limits": {"max_rounds": 2, "max_scenarios": 8},
    }
    payload.update(over)
    return payload


def minimal_seed(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "collections": {
            "jobs": [
                {"job_id": 90420, "status": "failed", "controller": "prod0"},
                {"job_id": 90421, "status": "successful", "controller": "prod0"},
            ]
        },
    }
    payload.update(over)
    return payload


def minimal_expected(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "scenario_id": "scn-001",
        "discriminating_fact": "exactly one prod0 job failed inside the window",
        "answer_reference": "Job 90420 failed on prod0.",
        "assertions": [
            {
                "kind": "answer_contains",
                "target": "answer",
                "value": "90420",
                "rationale": "the failing job id must appear in the answer",
                "grounded_in": {"seed_pointer": "/collections/jobs/0/job_id"},
            },
            {
                "kind": "tool_called",
                "target": "query_aap2.find_jobs",
                "value": "at least once",
                "rationale": "the agent must query rather than guess",
                "capability_id": "cap-find-jobs",
            },
        ],
        "trajectory": {
            "match": "subset",
            "operations": [{"capability_id": "cap-find-jobs", "args": {"controller": "prod0"}}],
        },
        "completion": {"status": "ok", "nonempty_answer": True},
    }
    payload.update(over)
    return payload


def minimal_suite_expected(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract": "rubrica/v1",
        "scenario_id": "scn-001",
        "completion": {"status": "ok", "nonempty_answer": True},
        "assertions": [
            {
                "id": "a0",
                "kind": "answer_contains",
                "target": "answer",
                "value": "90420",
                "rationale": "the failing job id must appear in the answer",
            },
            {
                "id": "a1",
                "kind": "tool_called",
                "target": "query_aap2.find_jobs",
                "value": "at least once",
                "rationale": "the agent must query rather than guess",
                "tool": "query_aap2",
                "args": {"action": "find_jobs"},
            },
        ],
        "trajectory": {
            "match": "subset",
            "operations": [
                {"tool": "query_aap2", "args": {"action": "find_jobs", "controller": "prod0"}}
            ],
        },
        "weights": {"assertions": 0.8, "trajectory": 0.2},
    }
    payload.update(over)
    return payload


def minimal_report(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "run_id": "run-20260806-120000",
        "agents": [
            {"role": "weak_baseline", "model": "claude-haiku-4-5-20251001", "notes": "no tools"},
            {"role": "under_test", "model": "claude-sonnet-5"},
            {"role": "oracle", "model": "claude-sonnet-5", "notes": "handed golden.json"},
        ],
        "tasks": [
            {
                "scenario_id": "scn-001",
                "results": [
                    {
                        "role": "weak_baseline",
                        "scored": True,
                        "reward": 0.0,
                        "completion": 1.0,
                        "assertions": 0.0,
                        "trajectory": 0.0,
                    },
                    {
                        "role": "under_test",
                        "scored": True,
                        "reward": 0.8,
                        "completion": 1.0,
                        "assertions": 1.0,
                        "trajectory": 0.0,
                    },
                    {
                        "role": "oracle",
                        "scored": True,
                        # 0.85, not 1.0: above ORACLE_FLOOR (0.80, so the verdict stays
                        # healthy) but below PASS_THRESHOLD (0.999, so oracle_failures
                        # counts it at the default threshold). That gap is what makes
                        # refs.test_the_recomputation_uses_the_producers_own_functions
                        # meaningful -- weak_baseline's 0.0 can never cross a positive
                        # PASS_THRESHOLD, so oracle_failures is the only summary number
                        # here that a lowered PASS_THRESHOLD can actually move.
                        "reward": 0.85,
                        "completion": 1.0,
                        "assertions": 1.0,
                        "trajectory": 1.0,
                    },
                ],
                "all_pass": False,
                "all_fail": False,
            }
        ],
        "summary": {
            "mean_reward_by_role": {"weak_baseline": 0.0, "under_test": 0.8, "oracle": 0.85},
            "all_pass_tasks": 0,
            "all_fail_tasks": 0,
            "oracle_failures": 1,
            "unscoreable": 0,
        },
        "verdict": "healthy",
    }
    payload.update(over)
    return payload


def minimal_agents(**over: Any) -> dict[str, Any]:
    # weak_baseline first (several tests key off index 0 of both the raw
    # payload and the loaded, ROLES-sorted result), but oracle ahead of
    # under_test -- so the overall order still differs from ROLES and
    # load_agents' sort-into-ROLES-order is actually exercised rather than
    # passing trivially because the roster already arrived in that order.
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "agents": [
            {
                "role": "weak_baseline",
                "model": "claude-haiku-4-5-20251001",
                "command": ["true"],
                "notes": "no tools",
            },
            {
                "role": "oracle",
                "model": "claude-sonnet-5",
                "command": ["true"],
                "notes": "handed golden.json",
            },
            {"role": "under_test", "model": "claude-sonnet-5", "command": ["true"]},
        ],
    }
    payload.update(over)
    return payload


def minimal_triage(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "run_id": "run-20260806-120000",
        "objective_review": {
            "declared_objective": "breadth",
            "supported": True,
            "surfaces": [
                {
                    "name": "api schema",
                    "evidence": ["aap2-api"],
                    "weight": {"candidates": 1, "bytes": 37},
                }
            ],
        },
        "dispositions": [
            {
                "candidate_id": "aap2-api",
                "disposition": "admit",
                "reason": "the only surface describing the tool",
                "authority": "triage",
            }
        ],
        "deficiencies": [],
        "projections": [],
    }
    payload.update(over)
    return payload


def minimal_gold(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "target": "aap2",
        "tasks": [
            {
                "id": "bench-001",
                "goal_id": "goal-triage",
                "hop_depth": 2,
                "capability_refs": [
                    {"capability_id": "cap-find-jobs", "outcome_class_id": "oc-success"}
                ],
                "notes": "the hand-authored triage task scn-001 should match",
            }
        ],
    }
    payload.update(over)
    return payload


def minimal_verdict(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "scenario_id": "scn-001",
        "uniquely_determined": True,
        "derivable_without_guessing": True,
        "minimum_tool_calls_found": 2,
        "verdict": "accept",
        "notes": "answered independently from the seed and matched the oracle",
    }
    payload.update(over)
    return payload


def minimal_catalogue(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "run_id": "run-20260806-120000",
        "created_utc": "2026-08-06T12:00:00Z",
        "request": {
            "target": {"name": "aap2", "interface": "mcp"},
            "objective": "breadth",
            "corpus_roots": ["/tmp/aap2"],
            "limits": {"max_rounds": 2, "max_scenarios": 8},
        },
        "policy": {
            "exclusion_reasons": ["binary"],
            "explode_min_elements": 3,
            "explode_min_common_keys": 3,
            "digest_body_chars": 2000,
            "max_candidates": 500,
            "max_catalogue_bytes": 1_048_576,
        },
        "candidates": [],
        "excluded": [],
    }
    payload.update(over)
    return payload


# The reconcile partials. Each is *sliced out of* minimal_world_model rather
# than restated, for the same reason the partial schemas $ref the world model's
# $defs: reconcile-seal has to assemble these seven files into exactly that
# document, so a builder that drifted from it would let a test pass against a
# world model the seal could never produce.
def minimal_subjects(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "subjects": [
            {
                "id": "sub-jobs",
                "label": "jobs and their query surface",
                # Total over minimal_claims by construction, which is what
                # refs.check_subjects will demand of a real cover.
                "claims": [claim["id"] for claim in minimal_claims()["claims"]],
            }
        ],
    }
    payload.update(over)
    return payload


def minimal_contradictions_part(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "subject_id": minimal_subjects()["subjects"][0]["id"],
        # Empty, like minimal_world_model's contradictions: a member that swept
        # its subject and found no disagreement is the ordinary case, and the
        # schema has no minItems precisely so it can say so.
        "contradictions": minimal_world_model()["contradictions"],
    }
    payload.update(over)
    return payload


def _minimal_inputs_seen(own_kinds: tuple[str, ...]) -> list[dict[str, Any]]:
    """The accounting row for minimal_claims' single artifact, nothing dropped.

    Required on the four partials whose pass owns a claim kind since issue #6,
    where read coverage of 01-claims/ varied 3/23 to 23/23 across byte-identical
    dispatches. The count is *counted* against minimal_claims rather than passed
    in as a literal, so it stays honest if that payload's one claim ever changes
    kind or gains a sibling: today its only claim is of kind `capability`, so
    capabilities-part reads 1/1/0 and the other three 0/0/0. `note` is absent
    because nothing is dropped, which is the half of the schema's if/then that
    keeps a 0/0/0 row cheap enough for the totality rule to be worth having.

    `own_kinds` takes the same shape as one entry of refs.PASS_OWN_KINDS -- what
    the pass writing this partial is accountable for -- because that is what
    refs.check_input_dispositions recomputes the row against.
    """
    own_kind_total = sum(1 for claim in minimal_claims()["claims"] if claim["kind"] in own_kinds)
    return [
        {
            "artifact_id": minimal_claims()["artifact_id"],
            "own_kind_total": own_kind_total,
            "cited": own_kind_total,
            "dropped": 0,
        }
    ]


def minimal_capabilities_part(**over: Any) -> dict[str, Any]:
    capability = minimal_world_model()["capabilities"][0]
    # The one subtraction that defines this artifact: outcome classes are the
    # next pass's output, so capability_core forbids them here.
    del capability["outcome_classes"]
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "capabilities": [capability],
        "inputs_seen": _minimal_inputs_seen(("capability",)),
    }
    payload.update(over)
    return payload


def minimal_outcomes_part(**over: Any) -> dict[str, Any]:
    capability = minimal_world_model()["capabilities"][0]
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "outcomes": [
            {
                "capability_id": capability["id"],
                "outcome_classes": capability["outcome_classes"],
            }
        ],
        "inputs_seen": _minimal_inputs_seen(("outcome_class",)),
    }
    payload.update(over)
    return payload


def minimal_entities_part(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "entities": minimal_world_model()["entities"],
        "inputs_seen": _minimal_inputs_seen(("entity", "invariant")),
    }
    payload.update(over)
    return payload


def minimal_goals_part(**over: Any) -> dict[str, Any]:
    world = minimal_world_model()
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "actors": world["actors"],
        "goals": world["goals"],
        "inputs_seen": _minimal_inputs_seen(("actor", "goal")),
    }
    payload.update(over)
    return payload


def minimal_gaps_part(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "gaps": minimal_world_model()["gaps"],
    }
    payload.update(over)
    return payload


# The tool-interface kinds. Stated here rather than sliced out of
# minimal_world_model the way the other partials are, because the world model's
# `services` key is optional and no seal assembles this part into it yet -- a
# slice would assert an assembly that does not exist. The direction of reuse
# instead runs the other way, from the part to the document: minimal_interface
# derives its title, path, operationId and provenance block from this service,
# so the carrier convention is *shown* being derived rather than restated in a
# second literal that could disagree with the first.
def minimal_services_part(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "services": [
            {
                "id": "svc-aap2",
                "statement": "the aap2 backend the one declared tool addresses",
                # `sole_service_in_run` and not a shared-anything reason: one
                # tool has nothing to share, which is why the enum carries it.
                "grouping_evidence": ["sole_service_in_run"],
                "tools": [
                    {
                        "name": "query_aap2",
                        # The only claim minimal_claims declares. It is of kind
                        # `capability`, not `tool`, which is why the accounting
                        # row below reads 0/0/0 -- layer 1 asks that the ids
                        # resolve to the id pattern, never that the claim they
                        # name is of any particular kind.
                        "claims": ["clm-001"],
                        "schema_claim": "clm-001",
                    }
                ],
                # Absence of evidence, never a `contained` verdict: nothing in
                # minimal_claims says this tool reaches outside the process, and
                # nothing says it does not.
                "signals": [{"kind": "no_outward_evidence_found", "locator": "aap2-api"}],
            }
        ],
        "inputs_seen": _minimal_inputs_seen(("tool",)),
    }
    payload.update(over)
    return payload


def minimal_interface(**over: Any) -> dict[str, Any]:
    service = minimal_services_part()["services"][0]
    tool = service["tools"][0]
    payload: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": service["id"], "version": "0.1.0"},
        "paths": {
            f"/{tool['name']}": {
                "post": {
                    "operationId": tool["name"],
                    # No `responses`. The harness's inline_schema_evidence exists
                    # for tool-style specs that declare no components.schemas and
                    # feeds request bodies as entity evidence, so a request-only
                    # document is its intended input rather than a degraded one.
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    },
                }
            }
        },
        "x-rubrica": {"service_id": service["id"], "tools": [tool]},
    }
    payload.update(over)
    return payload


# The triage split's part kinds. Each is *sliced out of* minimal_triage rather
# than restated, for the same reason the part schemas $ref triage-0.1.json's
# $defs: triage-seal has to assemble these into exactly that record, so a
# builder that drifted from it would let a test pass against a triage record
# the seal could never produce.
def minimal_slices(**over: Any) -> dict[str, Any]:
    candidate_id = minimal_triage()["dispositions"][0]["candidate_id"]
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "run_id": minimal_triage()["run_id"],
        "cap_bytes": 1_048_576,
        # `request` and `policy` are reused from minimal_catalogue rather than
        # restated, for the same reason the parts are sliced out of the whole:
        # catalogue_facts copies both verbatim, so a builder that drifted from
        # minimal_catalogue would let a test pass against a pair the writer
        # could never have produced.
        "catalogue_facts": {
            "request": minimal_catalogue()["request"],
            "policy": minimal_catalogue()["policy"],
            "excluded": {
                "total": 0,
                "by_reason": {},
                "entries": [],
                "entries_truncated": False,
            },
            # 19, deliberately not the slice's own `bytes: 37` below. The two
            # are different metrics -- this one is the candidate's source file
            # size, that one is row_bytes' serialized size -- and never
            # conflating them is the whole subject of candidate_bytes_index'
            # docstring. A builder where they read as the same number would
            # teach the opposite.
            "candidate_bytes": {candidate_id: 19},
        },
        "slices": [
            {
                "id": "s01",
                "label": "everything",
                "groups": ["root"],
                "bytes": 37,
                "candidate_ids": [candidate_id],
                "provenance": [
                    {
                        "group": "root",
                        "in_this_slice": 1,
                        "in_group_total": 1,
                        "other_slices": [],
                    }
                ],
            }
        ],
    }
    payload.update(over)
    return payload


def minimal_objective(**over: Any) -> dict[str, Any]:
    triage = minimal_triage()
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "run_id": triage["run_id"],
        "objective_review": triage["objective_review"],
        "predicted_surface_count": len(triage["objective_review"]["surfaces"]),
    }
    payload.update(over)
    return payload


def minimal_dispositions_part(**over: Any) -> dict[str, Any]:
    triage = minimal_triage()
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "run_id": triage["run_id"],
        "slice_id": minimal_slices()["slices"][0]["id"],
        "dispositions": triage["dispositions"],
        "observed_surfaces": [],
        "deficiency_notes": [],
    }
    payload.update(over)
    return payload


def minimal_audit(**over: Any) -> dict[str, Any]:
    triage = minimal_triage()
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "run_id": triage["run_id"],
        # Empty, like minimal_triage's own: a run that swept every slice and
        # found nothing worth projecting is the ordinary case, and both
        # schemas leave these array-less of a minItems for exactly that reason.
        "deficiencies": triage["deficiencies"],
        "projections": triage["projections"],
    }
    payload.update(over)
    return payload


def minimal_adoptions(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "run_id": minimal_triage()["run_id"],
        # Empty: no human has necessarily adopted anything, and triage-seal
        # folds this file in unconditionally rather than treating an empty
        # list as a defect.
        "adoptions": [],
    }
    payload.update(over)
    return payload


def minimal_batches(**over: Any) -> dict[str, Any]:
    # The hole this batch owns is taken from minimal_coverage's own uncovered
    # cell, so the projection is over a hole the coverage report actually
    # reports rather than an invented ref that happens to match the pattern.
    hole = minimal_coverage()["holes"][0]["ref"]
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "round": 1,
        "cap_bytes": 28000,
        "bytes_per_scenario": 1600,
        # One batch, not zero: batches-0.1.json puts minItems: 1 here because
        # propose-batches writes no document at all when no hole is closable.
        "batches": [{"id": "b01", "hole_refs": [hole], "projected_bytes": 1600}],
    }
    payload.update(over)
    return payload


def minimal_scenarios_part(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "round": 1,
        "batch_id": minimal_batches()["batches"][0]["id"],
        # One scenario, sliced out of minimal_scenarios, so the part carries
        # exactly the shape scenarios-0.1.json#/$defs/scenario accepts -- which
        # is also what proves the cross-file $ref resolves at all.
        "scenarios": minimal_scenarios()["scenarios"],
    }
    payload.update(over)
    return payload


def minimal_score_part(**over: Any) -> dict[str, Any]:
    coverage = minimal_coverage()
    payload: dict[str, Any] = {
        "schema_version": "0.1",
        "round": coverage["round"],
        # The status change this round made, and nothing computable: no
        # matrices, no scenario re-emit.
        "rulings": [{"scenario_id": minimal_scenarios()["scenarios"][0]["id"], "status": "active"}],
        # Sliced out of minimal_coverage, for the same reason
        # minimal_scenarios_part slices its scenario: the holes are the same
        # $defs/hole the sealed coverage report carries.
        "holes": coverage["holes"],
        "verdict": coverage["verdict"],
    }
    payload.update(over)
    return payload
