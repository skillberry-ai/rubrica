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
                "outcome_classes": [
                    {"id": "oc-success", "kind": "success", "description": "jobs returned"},
                    {"id": "oc-empty", "kind": "empty", "description": "no jobs match"},
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
        "stages": {
            "reconcile": {"model": "claude-opus-5", "effort": "high", "skill_sha256": "b" * 64}
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
