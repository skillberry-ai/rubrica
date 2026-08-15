"""Layer 2 over the triage record: reference resolution, nothing semantic.

Spec §6.1 and §10. Every disposition must resolve to a real candidate and vice
versa, and the two decline codes whose whole purpose is to make a loss visible
(`digest_insufficient`, `needs_projection`) must actually be pointed at by
something -- a deficiency or a projection -- or the loss they record is
invisible. The one finding §11 asks for that *is* semantic (matching a
world-model gap's prose to a decline's prose) is deliberately absent here; it
becomes a human-read report in a later task.
"""

from __future__ import annotations

from rubrica import refs
from rubrica.artifacts import write_json
from rubrica.paths import RunPaths


def _run_with(tmp_path, mutate, decline_code="out_of_scope"):
    """A run with a two-candidate catalogue and a matching, clean triage record.

    cap-json is a container (admissible: False) that was exploded into
    elements elsewhere; readme-md is an ordinary admissible candidate.
    cap-json is declined with `decline_code`, and the baseline always carries
    one deficiency and one projection that reference each other, so a test
    that wipes one side of that reference is the only source of a finding.
    """
    run = RunPaths(tmp_path / "run-20260814-213000")
    run.root.mkdir(parents=True)
    catalogue = {
        "schema_version": "0.1",
        "run_id": "run-20260814-213000",
        "created_utc": "2026-08-14T21:30:00Z",
        "request": {
            "target": {"name": "t", "interface": "i"},
            "objective": "breadth",
            "corpus_roots": ["/tmp/c"],
            "limits": {"max_rounds": 2, "max_scenarios": 128},
        },
        "policy": {
            "exclusion_reasons": ["binary"],
            "explode_min_elements": 3,
            "explode_min_common_keys": 3,
            "digest_body_chars": 2000,
            "max_candidates": 500,
        },
        "candidates": [
            {
                "candidate_id": "cap-json",
                "origin": "corpus",
                "path": "cap.json",
                "bytes": 10,
                "sha256": "a" * 64,
                "kind": "trace",
                "admissible": False,
                "digest": {},
            },
            {
                "candidate_id": "readme-md",
                "origin": "corpus",
                "path": "README.md",
                "bytes": 20,
                "sha256": "b" * 64,
                "kind": "design_doc",
                "admissible": True,
                "digest": {},
            },
        ],
        "excluded": [],
    }
    write_json(run.catalogue, catalogue)

    triage = {
        "schema_version": "0.1",
        "run_id": "run-20260814-213000",
        "objective_review": {
            "declared_objective": "breadth",
            "supported": True,
            "surfaces": [
                {
                    "name": "docs",
                    "evidence": ["readme-md"],
                    "weight": {"candidates": 1, "bytes": 20},
                }
            ],
        },
        "dispositions": [
            {
                "candidate_id": "cap-json",
                "disposition": "decline",
                "reason_code": decline_code,
                "reason": "a container, not evidence on its own",
                "authority": "triage",
            },
            {
                "candidate_id": "readme-md",
                "disposition": "admit",
                "reason": "the only description of the target's purpose",
                "authority": "triage",
            },
        ],
        "deficiencies": [
            {
                "deficiency_id": "def-1",
                "subject": "cap-json",
                "statement": "the digest alone did not show enough to admit it",
            }
        ],
        "projections": [
            {
                "projection_id": "proj-1",
                "closes": ["def-1"],
                "sources": [{"candidate_id": "cap-json", "digest_note": "digest was partial"}],
                "wanted": {
                    "kind": "trace",
                    "statement": "a fuller trace than the digest could show",
                    "why": "needed to ground an assertion",
                },
                "method": {"confidence": "medium", "steps": ["re-read cap-json in full"]},
                "acceptance": {"classifies_as": "trace", "prose": "shows the full call and result"},
                "boundary": "does not cover other candidates",
            }
        ],
    }
    mutate(triage, catalogue)
    write_json(run.triage, triage)
    return run


def test_a_clean_record_has_no_findings(tmp_path):
    assert refs.check_triage(_run_with(tmp_path, lambda t, c: None)) == []


def test_a_candidate_with_no_disposition_is_a_finding(tmp_path):
    """The coverage requirement is the whole mechanism.

    Without it, 'declined' and 'never considered' are the same absence -- which
    is exactly the confusion that left four parsec gaps indistinguishable from
    gaps nothing could close.
    """

    def mutate(triage, catalogue):
        triage["dispositions"] = [
            d for d in triage["dispositions"] if d["candidate_id"] != "readme-md"
        ]

    findings = refs.check_triage(_run_with(tmp_path, mutate))
    assert findings and "readme-md" in str(findings[0])


def test_a_disposition_for_an_unknown_candidate_is_a_finding(tmp_path):
    """Triage cannot invent a candidate; a candidate it wishes existed is a
    deficiency."""

    def mutate(triage, catalogue):
        triage["dispositions"].append(
            {
                "candidate_id": "invented",
                "disposition": "admit",
                "reason": "x",
                "authority": "triage",
            }
        )

    findings = refs.check_triage(_run_with(tmp_path, mutate))
    assert findings and "invented" in str(findings[0])


def test_two_dispositions_for_one_candidate_is_a_finding(tmp_path):
    def mutate(triage, catalogue):
        triage["dispositions"].append(dict(triage["dispositions"][0]))

    assert refs.check_triage(_run_with(tmp_path, mutate)) != []


def test_a_decline_without_a_reason_code_is_a_finding(tmp_path):
    """Required on declines and forbidden on admits: a conditional constraint,
    so it lives here rather than in an if/then the schema expresses badly."""

    def mutate(triage, catalogue):
        for d in triage["dispositions"]:
            if d["disposition"] == "decline":
                d.pop("reason_code", None)

    assert refs.check_triage(_run_with(tmp_path, mutate)) != []


def test_an_admit_carrying_a_decline_reason_code_is_a_finding(tmp_path):
    def mutate(triage, catalogue):
        for d in triage["dispositions"]:
            if d["disposition"] == "admit":
                d["reason_code"] = "off_objective"

    assert refs.check_triage(_run_with(tmp_path, mutate)) != []


def test_a_digest_insufficient_decline_unreferenced_by_a_deficiency_is_a_finding(tmp_path):
    """Spec §6.1: the two codes whose purpose is to make a loss visible would
    otherwise be the quietest way to lose something. A decline nothing points at
    reads exactly like a decline that was fine."""

    def mutate(triage, catalogue):
        triage["deficiencies"] = []

    findings = refs.check_triage(_run_with(tmp_path, mutate, decline_code="digest_insufficient"))
    assert findings and "digest_insufficient" in str(findings[0])


def test_a_needs_projection_decline_unreferenced_by_a_projection_is_a_finding(tmp_path):
    def mutate(triage, catalogue):
        triage["projections"] = []

    assert refs.check_triage(_run_with(tmp_path, mutate, decline_code="needs_projection")) != []


def test_a_projection_closing_an_unknown_deficiency_is_a_finding(tmp_path):
    def mutate(triage, catalogue):
        triage["projections"][0]["closes"] = ["def-nope"]

    findings = refs.check_triage(_run_with(tmp_path, mutate))
    assert findings and "def-nope" in str(findings[0])


def test_a_projection_source_that_is_not_a_candidate_is_a_finding(tmp_path):
    def mutate(triage, catalogue):
        triage["projections"][0]["sources"][0]["candidate_id"] = "ghost"

    assert refs.check_triage(_run_with(tmp_path, mutate)) != []


def test_an_admitted_inadmissible_candidate_is_a_finding(tmp_path):
    """A container is in the catalogue so a reader can see where elements came
    from. Admitting it hands one stage every record at once."""

    def mutate(triage, catalogue):
        for d in triage["dispositions"]:
            if d["candidate_id"] == "cap-json":
                d["disposition"] = "admit"
                d.pop("reason_code", None)

    findings = refs.check_triage(_run_with(tmp_path, mutate))
    assert findings and "admissible" in str(findings[0])


def test_zero_admits_is_a_finding_naming_the_triage_record(tmp_path):
    """An empty admitted set is a scoping failure, not a triage result -- and it
    is exit 1 against 00-triage.json, repairable by re-dispatching, never exit 2."""

    def mutate(triage, catalogue):
        for d in triage["dispositions"]:
            d["disposition"] = "decline"
            d["reason_code"] = "off_objective"

    findings = refs.check_triage(_run_with(tmp_path, mutate))
    assert findings and "00-triage.json" in str(findings[0].artifact)


def test_an_absent_triage_record_is_not_a_finding(tmp_path):
    """Spec §7.1 again: a run built through intake --input never had one."""
    run = RunPaths(tmp_path / "run-20260814-213000")
    run.root.mkdir(parents=True)
    assert refs.check_triage(run) == []


def test_check_triage_never_raises_on_a_malformed_document(tmp_path):
    """check_all runs on whatever is on disk, ahead of validate --stage triage
    rejecting the same document.

    A hashable-keyed lookup on candidate_id, deficiency_id or projection_id
    would raise TypeError the moment one of those holds a list or a dict
    instead of the string the schema requires -- turning a repairable stage
    defect into exit 2, the one thing the exit-code contract forbids. None of
    these shapes is schema-valid; the point is that layer 2 must not be the
    thing that discovers that by crashing.
    """
    run = RunPaths(tmp_path / "run-20260814-213000")
    run.root.mkdir(parents=True)
    write_json(run.catalogue, {"candidates": "not-a-list"})
    write_json(
        run.triage,
        {
            "dispositions": [
                {"candidate_id": ["nope"], "disposition": "admit"},
                "not-a-dict",
            ],
            "deficiencies": [{"deficiency_id": {"x": 1}}],
            "projections": [{"projection_id": ["nope"], "closes": 5, "sources": "not-a-list"}],
        },
    )
    assert isinstance(refs.check_triage(run), list)
