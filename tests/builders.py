"""Minimal schema-valid artifact payloads, for mutation in tests.

Each builder returns the smallest payload its schema accepts. Tests override
one key to construct a negative case, which keeps each test's intent visible
instead of buried in fifty lines of valid boilerplate.
"""

from __future__ import annotations

from typing import Any


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
            }
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
                "sha256": "a" * 64,
                "kind": "mcp_tool_schema",
                "bytes": 4096,
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
