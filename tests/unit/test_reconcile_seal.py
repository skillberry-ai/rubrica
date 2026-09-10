"""The seal, and the one property that makes the split safe.

The round trip is the whole point: if seal(split(w)) != w, then staging reconcile
changed what the pipeline produces, and every fixture and recording downstream of
01-world-model.json is describing a world the new passes cannot rebuild.
"""

from __future__ import annotations

import os

import pytest

from rubrica import cli, reconcile, refs, validate
from rubrica.artifacts import read_json, sha256_of, write_json
from tests.toy import build_toy_run, split_world_model, toy_world_model


def _write_parts(run, parts: dict) -> None:
    write_json(run.capabilities_part, parts["capabilities"])
    write_json(run.outcomes_part, parts["outcomes"])
    write_json(run.entities_part, parts["entities"])
    write_json(run.goals_part, parts["goals"])
    write_json(run.gaps_part, parts["gaps"])
    write_json(run.subjects, parts["subjects"])
    for subject_id, part in parts["contradictions"].items():
        write_json(run.contradiction_part(subject_id), part)


def test_the_seal_rebuilds_the_golden_world_model_exactly(tmp_path):
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())

    path, findings = reconcile.seal(run)

    assert findings == []
    assert path == run.world_model
    assert read_json(run.world_model) == toy_world_model()


def _sealed(tmp_path):
    """A run carried to a clean seal, which is the state every digest test starts from."""
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    path, findings = reconcile.seal(run)
    assert findings == [], findings
    assert path == run.world_model
    return run


def test_the_seal_records_a_digest_for_every_partial_it_assembled(tmp_path):
    """The hole this closes: `01-world-model.json` recorded no digest of the partials
    it was assembled from, so a partial edited *after* the seal was undetectable by
    anything a human reads at gate 1. Measured on two domains -- rewriting
    `01-capabilities.json` after the seal left `validate --stage reconcile-seal`,
    `check-refs` and `gate-brief --gate 1` byte-identical to the clean run.

    Recorded in `manifest.json` rather than in the sealed document, and that is the
    ruling rather than an implementation detail. The manifest is already this
    project's home for digests -- `inputs[].sha256`, re-hashed by
    `refs.check_inputs` -- and `01-world-model.json` keeps its path, schema and byte
    shape, which is a property `CLAUDE.md` freezes deliberately so nothing below the
    seal can tell it was assembled pass by pass.
    """
    run = _sealed(tmp_path)
    recorded = {entry["path"]: entry for entry in read_json(run.manifest)["partials"]}
    # Derived from the fixture rather than listed: the toy world's contradiction parts
    # are one per subject and a literal roster here would be a second spelling of
    # split_world_model()'s own. What is asserted is the *rule* -- the five singleton
    # parts plus every contradiction part, and nothing else.
    expected = {
        "01-capabilities.json",
        "01-outcomes.json",
        "01-entities.json",
        "01-goals.json",
        "01-gaps.json",
    } | {f"01-contradictions/{p.name}" for p in run.contradictions_dir.iterdir()}
    assert set(recorded) == expected, sorted(set(recorded) ^ expected)
    # `01-subjects.json` is absent on purpose, and asserted so rather than left to the
    # set comparison: the seal never reads it -- it is the cover the contradict fan-out
    # slices, and no key of the world model comes from it -- so recording a digest for
    # it would claim an assembly read a file it did not.
    assert "01-subjects.json" not in recorded
    assert run.subjects.is_file(), "the fixture must actually have a subjects cover"


def test_the_recorded_digest_is_the_partial_s_actual_content(tmp_path):
    """A digest of something else is worse than none: it would clear a check while
    describing a file nobody wrote."""
    run = _sealed(tmp_path)
    for entry in read_json(run.manifest)["partials"]:
        path = run.root / entry["path"]
        assert entry["sha256"] == sha256_of(path), entry["path"]
        assert entry["bytes"] == path.stat().st_size, entry["path"]


def test_a_partial_edited_after_the_seal_is_a_finding_naming_it(tmp_path):
    """The reported defect, end to end. Everything at gate 1 was byte-identical
    before this; now the edit has one place that reports it, and the finding names
    the partial rather than the world model -- which is correct because the world
    model faithfully describes the partials as they were when it was sealed.
    """
    run = _sealed(tmp_path)
    assert refs.check_partials(run) == []

    capabilities = read_json(run.capabilities_part)
    capabilities["capabilities"][0]["description"] = "rewritten after the seal"
    write_json(run.capabilities_part, capabilities)

    findings = refs.check_partials(run)
    assert len(findings) == 1, findings
    assert findings[0].artifact == run.capabilities_part
    # The message has to carry both hashes and the remedy, not merely say something
    # is wrong: a `1` sends the orchestrator to repair a stage, so a reader who
    # cannot tell "edited since the seal" from "the seal is broken" spends the run's
    # one repair attempt on the wrong thing.
    message = findings[0].message
    assert sha256_of(run.capabilities_part) in message
    assert "reconcile-seal" in message


def test_the_edit_is_reported_through_check_all_and_not_only_its_own_checker(tmp_path):
    """A checker nothing calls closes nothing. `check-refs` is what a human runs at
    gate 1, so the hole is only closed if the finding arrives there."""
    run = _sealed(tmp_path)
    before = refs.check_all(run)

    capabilities = read_json(run.capabilities_part)
    capabilities["capabilities"][0]["description"] = "rewritten after the seal"
    write_json(run.capabilities_part, capabilities)

    after = refs.check_all(run)
    added = [f for f in after if f not in before]
    assert [f.artifact for f in added] == [run.capabilities_part], added


def test_a_partial_deleted_after_the_seal_is_a_finding_naming_it(tmp_path):
    """An absent partial is the same class as a changed one -- the sealed world model
    describes something that is no longer there -- and it must not surface as a
    traceback or as a finding against the world model."""
    run = _sealed(tmp_path)
    run.gaps_part.unlink()
    findings = refs.check_partials(run)
    assert [f.artifact for f in findings] == [run.gaps_part], findings


def test_a_manifest_with_no_partials_block_reports_nothing(tmp_path):
    """A run sealed before this existed has no record to check against, and inventing
    a finding for one would be the fabricated-finding failure `CLAUDE.md` records:
    `check-refs` over an unreadable 01-claims/ once reported four invented `no such
    claim` findings against a correct world model. The committed live recordings are
    exactly this case -- world models sealed by the superseded single-dispatch stage,
    with no manifest at all.
    """
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    manifest = read_json(run.manifest)
    assert "partials" not in manifest
    assert refs.check_partials(run) == []


def test_two_runs_sealed_from_identical_partials_record_identical_digests(tmp_path):
    """The seal's byte-identity property must survive gaining a record. It does
    because every field is content-derived: the digest and the byte count come from
    the file, and the path is run-relative rather than absolute.
    """
    first = _sealed(tmp_path / "a")
    second = _sealed(tmp_path / "b")
    assert read_json(first.manifest)["partials"] == read_json(second.manifest)["partials"]
    assert first.world_model.read_bytes() == second.world_model.read_bytes()


def test_re_sealing_after_a_legitimate_correction_updates_the_record(tmp_path):
    """The workflow this gate actually invites. `CLAUDE.md` says a human at gate 1
    corrects a grouping by hand, so an edit below the seal is encouraged rather than
    tamper-only -- what was missing was any signal that the seal has to be re-run.
    Re-running it must clear the finding, or the check would punish the correct
    workflow instead of the incorrect one.
    """
    run = _sealed(tmp_path)
    capabilities = read_json(run.capabilities_part)
    capabilities["capabilities"][0]["description"] = "corrected by a human at gate 1"
    write_json(run.capabilities_part, capabilities)
    assert refs.check_partials(run)

    path, findings = reconcile.seal(run)
    assert findings == []
    assert path == run.world_model
    assert refs.check_partials(run) == []


def test_an_unreadable_partial_is_a_finding_naming_it_and_not_a_traceback(tmp_path):
    """`CLAUDE.md`'s rule for touching refs.py: test the unreadable-input paths, not
    just the happy path. A stage defect must never surface as exit 2, and a `1` must
    name the right artifact -- `check-refs` over an unreadable `01-claims/` once
    reported four fabricated `no such claim` findings against a correct world model.
    """
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    run = _sealed(tmp_path)
    run.capabilities_part.chmod(0o000)
    try:
        findings = refs.check_partials(run)
    finally:
        run.capabilities_part.chmod(0o644)
    assert [f.artifact for f in findings] == [run.capabilities_part], findings
    assert "cannot read" in findings[0].message


@pytest.mark.parametrize(
    "bad_path",
    ["../escaped.json", "/etc/passwd", "01-contradictions/../../escaped.json"],
    ids=["relative-traversal", "absolute", "nested-traversal"],
)
def test_a_recorded_path_outside_the_run_is_a_finding_against_the_manifest(tmp_path, bad_path):
    """The one class where the finding names the manifest rather than the partial:
    there is no partial to name, and the recorded path is what is wrong. Refused by
    resolving rather than by scanning for `..`, so a spelling nobody anticipated
    cannot slip past a substring test -- and never read, since a stage output that
    points outside the run must arrive as a repairable finding rather than as a read
    of somebody else's file.
    """
    run = _sealed(tmp_path)
    manifest = read_json(run.manifest)
    manifest["partials"] = [{"path": bad_path, "sha256": "0" * 64, "bytes": 1}]
    write_json(run.manifest, manifest)
    findings = refs.check_partials(run)
    assert [f.artifact for f in findings] == [run.manifest], findings
    assert "inside the run directory" in findings[0].message


def test_a_stale_seal_reaches_the_orchestrator_as_exit_one_with_findings_on_stdout(
    tmp_path, capsys
):
    """The contract the orchestrator branches on. A stage defect is exit 1 with one
    finding per line on stdout -- never exit 2, which says retrying cannot help, and
    never exit 1 with empty stdout, which is what an exception escaping the handler
    produces.
    """
    run = _sealed(tmp_path)
    capabilities = read_json(run.capabilities_part)
    capabilities["capabilities"][0]["description"] = "rewritten after the seal"
    write_json(run.capabilities_part, capabilities)

    code = cli.main(["check-refs", "--run", str(run.root)])
    captured = capsys.readouterr()
    assert code == 1, captured.out + captured.err
    assert captured.out.strip(), "a 1 must never have empty stdout"
    assert "01-capabilities.json" in captured.out


def test_the_manifest_still_passes_layer_one_with_the_partials_block(tmp_path):
    """The block is a schema addition, so the document that carries it has to clear
    its own schema -- and the manifest is code output, which makes a layer-1 finding
    against it unrepairable by any re-dispatch."""
    run = _sealed(tmp_path)
    assert validate.validate_artifact(run.manifest, "manifest") == []


def test_the_sealed_world_model_passes_layer_one(tmp_path):
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    reconcile.seal(run)
    assert validate.validate_artifact(run.world_model, "world-model") == []


def test_the_seal_folds_the_services_part_into_the_world_model(tmp_path):
    """The one optional partial, and the one the seal folds whole.

    Read outside `_SINGLETON_PARTS` because every entry there is required and an
    absent one is a finding -- right for the five partials the world model cannot
    be assembled without, wrong for this one, which the test below is about.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")

    path, findings = reconcile.seal(run)

    assert findings == []
    assert path == run.world_model
    model = read_json(run.world_model)
    assert [service["id"] for service in model["services"]] == ["svc-tickets"]
    # Folded verbatim, not re-derived: the grouping is the pass's judgment and it is
    # what a human ratifies at gate 1, so a seal that rebuilt the records would be
    # handing them the seal's judgment instead.
    assert model["services"] == read_json(run.services_part)["services"]


def test_a_run_with_no_services_part_omits_the_key_rather_than_writing_an_empty_list(tmp_path):
    """Omitted, not `[]`, and the difference is what keeps the two committed live
    recordings valid: they predate the key, and a required or always-written one
    would invalidate the only behavioural evidence the refusal conditions have --
    obliging a paid re-record for a change that does not touch what they record.

    It is also the honest shape. `[]` asserts a pass looked and found no tools,
    which is a different claim about the target from "no pass ran".
    """
    run = build_toy_run(tmp_path, upto="reconcile-gaps")
    assert not run.services_part.exists()

    path, findings = reconcile.seal(run)

    assert findings == []
    assert path == run.world_model
    assert "services" not in read_json(run.world_model)


@pytest.mark.parametrize("broken", ["null", '["nope"]', '{"schema_version": "0.1"}'])
def test_a_malformed_services_part_is_a_finding_naming_that_artifact(tmp_path, broken):
    """Optional does not mean unchecked: a part that exists comes through the same
    door as the rest.

    `null` is the shape that motivated that door -- it is legitimate JSON, so
    `read_json` returns None for it and `document is not None` meant two things at
    once. Measured on `01-gaps.json`: the payload-key check was skipped and the
    assembly raised `KeyError`, which cli.py's catch-all reported against the run
    root. A list is the other half, and reaches `document["services"]` instead.
    Both must name `01-services.json`, which is where a repair starts.
    """
    run = build_toy_run(tmp_path, upto="synthesise-interfaces")
    run.services_part.write_text(broken, encoding="utf-8")

    path, findings = reconcile.seal(run)

    assert path is None
    assert [f.artifact for f in findings] == [run.services_part], findings
    assert not run.world_model.is_file(), "the seal must not write a partial world model"


def test_the_denominator_is_computed_not_copied(tmp_path):
    """The arithmetic is the seal's job. A partial cannot assert it, and nothing
    in the partials carries a number for the seal to trust."""
    run = build_toy_run(tmp_path, upto="extract")
    parts = split_world_model()
    _write_parts(run, parts)
    reconcile.seal(run)

    world = read_json(run.world_model)
    expected_cells = sum(len(o["outcome_classes"]) for o in parts["outcomes"]["outcomes"])
    assert world["denominator"] == {
        "version": 1,
        "capability_cells": expected_cells,
        "goals": len(parts["goals"]["goals"]),
    }


def test_the_denominator_agrees_with_the_recomputation_that_checks_it(tmp_path):
    """refs.check_world_model recomputes capability_cells, which makes the field an
    identity rather than an independent claim: whatever the seal writes has to be
    what the check derives, or check-refs reports a finding against a world model
    the seal itself just produced.

    Asserted through check_world_model rather than by recomputing the count here,
    so the two sides are not both this test's own arithmetic."""
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    reconcile.seal(run)

    assert [f for f in refs.check_world_model(run) if f.pointer.startswith("/denominator")] == []


def test_the_denominator_counts_distinct_cells_not_a_sum_of_counts(tmp_path):
    """The case where set semantics and a sum diverge, which the toy world model
    cannot reach on its own: refs.drivable_cells is a *set* of (capability, outcome
    class) pairs, so a repeated outcome-class id inside one capability is one cell,
    not two. A seal that summed per-capability lengths would write 5 here against
    the 4 distinct cells, and check_world_model -- which recomputes the field
    through that same function, which is what makes it an identity -- would
    immediately contradict it.

    The repeat is schema-legal -- the world-model schema puts no uniqueItems on
    outcome_classes, and check_world_model's duplicate-id scan covers the four
    top-level groups, not the classes nested inside a capability -- so nothing
    else in the pipeline stands between a repeated cell and this count."""
    run = build_toy_run(tmp_path, upto="extract")
    parts = split_world_model()
    first = parts["outcomes"]["outcomes"][0]
    # Copied before mutating: split_world_model's entities/actors/goals/gaps are
    # references into the world dict it was handed, and its outcome_classes lists
    # come straight off the golden capabilities. Appending in place would edit
    # toy_world_model()'s own structures for anything sharing them.
    repeated = [*first["outcome_classes"], dict(first["outcome_classes"][0])]
    parts["outcomes"]["outcomes"] = [
        {"capability_id": first["capability_id"], "outcome_classes": repeated},
        *parts["outcomes"]["outcomes"][1:],
    ]
    _write_parts(run, parts)

    reconcile.seal(run)

    world = read_json(run.world_model)
    naive_sum = sum(len(o["outcome_classes"]) for o in parts["outcomes"]["outcomes"])
    # Filtered on the binding so the expected value is narrow like the field it
    # checks. Measured: every capability in split_world_model() is bound, so the
    # filter yields the same 4 the unfiltered comprehension did -- this is a
    # hardening, not a change of what the test means today. Unfiltered, the first
    # unbound capability added to the toy fixture would turn this into a confusing
    # failure in a test that is not about binding at all.
    distinct = len(
        {
            (c["id"], oc["id"])
            for c in world["capabilities"]
            if (c.get("binding") or {}).get("tool")
            for oc in c["outcome_classes"]
        }
    )
    assert naive_sum != distinct, "the fixture must reach the case where the two differ"
    assert world["denominator"]["capability_cells"] == distinct
    assert [f for f in refs.check_world_model(run) if f.pointer.startswith("/denominator")] == []


# The two capability shapes the drivable-denominator tests below are built from,
# as functions rather than module constants so a test that mutates one cannot
# reach the next test's copy. Claim ids are the toy run's real ones
# (tests/toy.py::split_world_model): an unresolvable id would make
# check_world_model report a claim finding, and the identity test would then be
# measuring that instead of the denominator.
def _bound_capability() -> dict:
    return {
        "id": "cap-bound",
        "operation": "search",
        "params": [],
        "binding": {"tool": "search_restaurants", "fixed_args": {}},
        "claims": ["clm-api-001"],
        "confidence": "high",
    }


# The shape 19 of 24 capabilities had on the measured run: a real claim, no tool
# anyone could name from it. rb-reconcile-capabilities' refusal conditions
# require exactly this rather than a guessed tool.
def _unbound_capability() -> dict:
    return {
        "id": "cap-unbound",
        "operation": "integrate with Keycloak",
        "params": [],
        "claims": ["clm-api-001"],
        "confidence": "medium",
    }


def _bound_outcomes() -> dict:
    return {
        "capability_id": "cap-bound",
        "outcome_classes": [
            {"id": "oc-ok", "kind": "success", "description": "d", "claims": ["clm-api-005"]},
            {"id": "oc-empty", "kind": "empty", "description": "d", "claims": ["clm-api-005"]},
        ],
    }


def _unbound_outcomes() -> dict:
    return {
        "capability_id": "cap-unbound",
        "outcome_classes": [
            {
                "id": "oc-ok",
                "kind": "underspecified",
                "description": "d",
                "claims": ["clm-api-005"],
            },
        ],
    }


def _run_ready_to_seal_with(tmp_path, *, capabilities: list[dict], outcomes: list[dict]):
    """A toy run at extract with only the capabilities and outcomes parts swapped.

    Built off split_world_model rather than hand-authored so the entities, actors,
    goals, gaps, contradictions and the subject cover stay the golden ones. Those
    cite real claims, and the cover has to stay total -- otherwise
    check_world_model and check_subjects report findings of their own and the
    identity assertion below would be measuring one of those instead of the
    denominator. The other payload keys of the two swapped parts (`schema_version`,
    `inputs_seen`) are preserved for the same reason: the part is still the part.
    """
    run = build_toy_run(tmp_path, upto="extract")
    parts = split_world_model()
    parts["capabilities"] = {**parts["capabilities"], "capabilities": capabilities}
    parts["outcomes"] = {**parts["outcomes"], "outcomes": outcomes}
    _write_parts(run, parts)
    return run


def test_the_sealed_denominator_counts_only_drivable_cells(tmp_path):
    """The undrivable denominator (docs/design/findings.md). The denominator is
    frozen at the seal by design, so a wrong one is not corrected later -- it is
    scored against for the rest of the run and recorded in every coverage
    document.

    Measured on run-20260827-070444: 24 capabilities, 5 bound, denominator 56
    against 19 drivable cells, and `rubrica check-refs` exited 0 on it.
    """
    run = _run_ready_to_seal_with(
        tmp_path,
        capabilities=[_bound_capability(), _unbound_capability()],
        outcomes=[_bound_outcomes(), _unbound_outcomes()],
    )

    path, findings = reconcile.seal(run)

    assert findings == []
    world = read_json(path)
    # Two drivable cells, not the three the world model declares. Both numbers are
    # read off the sealed artifact rather than through refs, so the test is not
    # asserting the implementation against itself.
    declared = {(c["id"], oc["id"]) for c in world["capabilities"] for oc in c["outcome_classes"]}
    assert len(declared) == 3, "the fixture must declare a cell the suite cannot drive"
    assert world["denominator"]["capability_cells"] == 2
    # The unbound capability is still IN the world model. It is not a lie, and
    # some such capabilities are real surfaces worth recording -- it just stops
    # setting the target coverage is scored against.
    assert {c["id"] for c in world["capabilities"]} == {"cap-bound", "cap-unbound"}
    # version is a per-run amendment counter, not an arithmetic generation, so
    # narrowing the arithmetic must not move it.
    assert world["denominator"]["version"] == 1
    # Layer 1 still passes: narrowing a count changes no shape.
    assert validate.validate_artifact(run.world_model, "world-model") == []


def test_check_world_model_agrees_with_the_narrowed_seal(tmp_path):
    """The seal writes this field and check_world_model recomputes it, which makes
    it an identity. Both spellings had to change in one commit or every sealed
    world model reports a finding against itself -- the hazard the undrivable
    denominator's own suggested patch named and then reintroduced one layer down.
    """
    run = _run_ready_to_seal_with(
        tmp_path,
        capabilities=[_bound_capability(), _unbound_capability()],
        outcomes=[_bound_outcomes(), _unbound_outcomes()],
    )
    path, findings = reconcile.seal(run)
    assert findings == []
    assert path == run.world_model
    # Scoped to the denominator rather than asserting no findings at all, because
    # `check_world_model` is a checker of many clauses and only one of them is
    # this test's subject: that the seal's arithmetic and the check's
    # recomputation of `denominator.capability_cells` agree. A bare `== []` would
    # couple a binding test to every other clause in that function -- an actor
    # ref, a collection name, a contradiction's claim_a -- so an unrelated
    # addition there would fail here with a message about bindings.
    #
    # Do not restore the earlier reason given for this scoping, that a later task
    # on this branch makes check_world_model report every unbound capability:
    # that task was ae1b74e and 11a6c25 reverted it. The scoping is right; that
    # justification described behaviour the tree does not have.
    assert [f for f in refs.check_world_model(run) if "/denominator/" in f.pointer] == []


def test_the_drivable_denominator_counts_distinct_cells_not_a_sum(tmp_path):
    """The narrowed arithmetic has to stay a *set* over distinct pairs, exactly as
    the wide one was: a bound capability whose outcomes record repeats an
    outcome-class id is one cell, not two.

    Nothing else in the pipeline stands between that repeat and this count.
    world-model-0.1.json puts no uniqueItems on outcome_classes, and reconcile.seal
    refuses a duplicate *capability* record in the outcomes part but nothing at all
    for a repeated outcome-class id inside one record -- so the guard
    docs/design/limitations.md records has to live here, in the consumer that
    writes len(...) into the frozen field. Measured red against a seal spelled
    `sum(len(c["outcome_classes"]) for c in capabilities if the binding names a
    tool)`: it writes 2 where the check recomputes 1.

    The two descriptions differ, so a whole-object uniqueItems would not have
    caught this either -- the repeat is in the id alone.
    """
    repeated_outcomes = {
        "capability_id": "cap-bound",
        "outcome_classes": [
            {"id": "oc-ok", "kind": "success", "description": "first", "claims": ["clm-api-005"]},
            {"id": "oc-ok", "kind": "empty", "description": "second", "claims": ["clm-api-005"]},
        ],
    }
    run = _run_ready_to_seal_with(
        tmp_path,
        capabilities=[_bound_capability()],
        outcomes=[repeated_outcomes],
    )

    path, findings = reconcile.seal(run)

    assert findings == []
    world = read_json(path)
    # What the naive sum would have written, stated as the fixture property rather
    # than recomputed through refs: one bound capability, two outcome-class entries.
    assert len(repeated_outcomes["outcome_classes"]) == 2, (
        "the fixture must reach the case where a sum and a set differ"
    )
    assert world["denominator"]["capability_cells"] == 1
    assert [f for f in refs.check_world_model(run) if "/denominator/" in f.pointer] == []


def test_the_denominator_version_can_be_bumped_for_an_amendment(tmp_path):
    """An amendment costs an explicit orchestrator decision and a version bump.
    The seal takes the bumped number rather than inventing or incrementing one,
    so the record of why it moved stays in decisions.md."""
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    reconcile.seal(run, denominator_version=2)
    assert read_json(run.world_model)["denominator"]["version"] == 2


def test_the_target_comes_from_the_manifest(tmp_path):
    """No pass restates it. Today reconcile writes `target` itself and nothing
    checks it against the manifest, so this removes an unchecked restatement."""
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    reconcile.seal(run)
    assert read_json(run.world_model)["target"] == read_json(run.manifest)["target"]


@pytest.mark.parametrize(
    "attribute",
    ["capabilities_part", "outcomes_part", "entities_part", "goals_part", "gaps_part"],
)
def test_a_missing_partial_is_a_finding_and_writes_nothing(tmp_path, attribute):
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    getattr(run, attribute).unlink()

    path, findings = reconcile.seal(run)

    assert path is None
    assert findings, f"a missing {attribute} must be reported"
    assert not run.world_model.is_file(), "the seal must not write a partial world model"
    assert all(f.message for f in findings), "a finding with an empty message is an empty exit-1"
    # Absence, specifically -- not the payload-less case below. Measured: with the
    # read error swallowed into an empty dict, the payload-key check catches the
    # same file and names it, so exit code and artifact alone no longer tell the two
    # apart, and they are different repairs (mint the file vs. fix the pass that
    # wrote an empty one). The phrase is artifacts.read_json's own, already pinned
    # by tests/unit/test_validate.py for the same reason.
    assert any("missing artifact" in f.message for f in findings)


def test_several_missing_partials_name_the_earliest_pass_first(tmp_path):
    """Pass order, not filesystem order: the first finding names the pass a repair
    should start from, the same property _readable_targets holds for layer 2."""
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    run.gaps_part.unlink()
    run.outcomes_part.unlink()

    _, findings = reconcile.seal(run)

    assert [f.artifact for f in findings] == [run.outcomes_part, run.gaps_part]


@pytest.mark.parametrize(
    "attribute",
    ["capabilities_part", "outcomes_part", "entities_part", "goals_part", "gaps_part"],
)
# Four shapes, and only two code paths -- the grid is not one shape per branch.
# `{}` is the missing-key branch. The other three are all the non-object branch,
# because `isinstance([], dict)` is False just as `isinstance(5, dict)` is, and
# each is here for a measured reason rather than for symmetry: `5` is what makes
# the isinstance guard load-bearing (without it, `"gaps" not in 5` raises
# TypeError, so removing the guard turns the scalar params red and leaves the
# array params green); `null` is the shape that reproduced this whole class a
# second time after the first fix, because read_json returns None for it and None
# was also _read_part's read-failure sentinel; `[]` is the control that pins the
# guard as shape-general rather than scalar-only -- it answers `key not in
# document` correctly, so it would still be reported if the guard were narrowed to
# scalars, and a grid without it could not tell a general guard from a narrow one.
@pytest.mark.parametrize(
    "payload",
    ["{}", "[]", "5", "null"],
    ids=["object-without-the-key", "array", "scalar", "null"],
)
def test_a_partial_with_no_payload_key_is_a_finding_naming_that_partial(
    tmp_path, capsys, attribute, payload
):
    """Present, valid JSON, and nothing to assemble from.

    Measured before the fix: `01-gaps.json` rewritten to `{}` reached the assembly
    and raised KeyError there, which cli.py's catch-all turned into an exit-1
    `[internal]` finding against the *run root*. Exit code right, stdout non-empty,
    and the third rule of the exit-code contract broken -- the one this repo learned
    when check-refs fabricated four `no such claim` findings against a correct world
    model. `[]`, `5` and `null` are the same defect three shapes over: none carries a
    payload key, and `"gaps" not in 5` raises TypeError rather than answering the
    question -- the shape refs._as_list exists for, one layer up.

    `null` reproduced the class a second time after the first fix, which is why it
    is measured here rather than argued about: read_json legitimately *returns* None
    for a `null` document, and None was also _read_part's read-failure sentinel, so
    the payload-key check was skipped and the assembly raised `KeyError:
    'gaps_part'` -- reported against the run root, naming a RunPaths attribute
    rather than any artifact.
    """
    from rubrica.cli import main

    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    target = getattr(run, attribute)
    target.write_text(payload, encoding="utf-8")

    path, findings = reconcile.seal(run)

    assert path is None
    # A set, because 01-goals.json declares two payload keys and `{}` is missing
    # both: one finding per absent key, every one of them naming this partial.
    assert findings
    assert {f.artifact for f in findings} == {target}, "every finding must name this partial"
    assert all(f.message for f in findings)
    assert not run.world_model.is_file()

    assert main(["reconcile-seal", "--run", str(run.root)]) == 1
    out = capsys.readouterr().out
    assert target.name in out
    assert "[internal]" not in out, "a named partial, not the catch-all against the run root"
    # The shape is named in JSON's vocabulary, not Python's: this finding is read
    # next to the file it names, where `null` and `[...]` are what a repairer sees.
    # `{}` is the missing-key branch and says nothing about shape, hence the guard.
    if payload != "{}":
        assert {"[]": "array", "5": "number", "null": "null"}[payload] in out


@pytest.mark.parametrize("payload", ["{}", "null"], ids=["object-without-the-key", "null"])
def test_a_payload_less_contradiction_part_is_a_finding_naming_that_part(tmp_path, payload):
    """A contradiction part comes through the same door as the singletons, because
    the same shapes reached `part.get(...)` and raised AttributeError there against
    the run root. The empty *array* is a real record -- it says a fan-out member
    swept its subject and found no disagreement -- but an absent key is not that
    record, and the two must not become one spelling."""
    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    part = run.contradiction_part("sub-cap-get-ticket")
    assert part.is_file(), "the fixture must actually place a part at this path"
    part.write_text(payload, encoding="utf-8")

    path, findings = reconcile.seal(run)

    assert path is None
    assert {f.artifact for f in findings} == {part}
    assert all(f.message for f in findings)
    assert not run.world_model.is_file()


def test_an_empty_contradiction_part_is_not_a_finding(tmp_path):
    """The other direction, and the one that keeps the check above honest: a part
    whose `contradictions` array is empty is the record that a member swept its
    subject, so it seals clean and contributes nothing."""
    run = build_toy_run(tmp_path, upto="extract")
    parts = split_world_model()
    for subject_id in parts["contradictions"]:
        parts["contradictions"][subject_id] = {
            "schema_version": "0.1",
            "subject_id": subject_id,
            "contradictions": [],
        }
    _write_parts(run, parts)

    path, findings = reconcile.seal(run)

    assert findings == []
    assert path == run.world_model
    assert read_json(run.world_model)["contradictions"] == []


@pytest.mark.parametrize(
    "payload", ["{}", "[]", "5", "null"], ids=["object-without-target", "array", "scalar", "null"]
)
def test_a_manifest_with_no_target_is_a_finding_naming_the_manifest(tmp_path, capsys, payload):
    """The manifest comes through the same door as the partials because it shares
    the same failure: `target` is the one key the seal reads out of it, and a
    manifest that is `null` or carries no `target` reached `manifest["target"]` and
    raised there, against the run root."""
    from rubrica.cli import main

    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    run.manifest.write_text(payload, encoding="utf-8")

    path, findings = reconcile.seal(run)

    assert path is None
    assert {f.artifact for f in findings} == {run.manifest}
    assert all(f.message for f in findings)
    assert not run.world_model.is_file()

    assert main(["reconcile-seal", "--run", str(run.root)]) == 1
    out = capsys.readouterr().out
    assert "manifest.json" in out
    assert "[internal]" not in out


def test_a_duplicate_outcomes_record_is_a_finding_not_a_silent_drop(tmp_path):
    """Two records for one capability are schema-legal and nothing downstream would
    notice the loss: a dict comprehension keeps the last, and check_world_model
    recomputes capability_cells from the assembled model, so the denominator agrees
    with the reduced cell set and the world model reads as coherent at gate 1.

    Same reasoning as the undeclared-capability branch, so this asserts the same two
    properties: a finding naming the capability, and nothing written."""
    run = build_toy_run(tmp_path, upto="extract")
    parts = split_world_model()
    first = parts["outcomes"]["outcomes"][0]
    # A *different* set of classes under the same capability_id, so a silent
    # keep-the-last would visibly change the assembled cells rather than being a
    # no-op the assertion could not distinguish from correct behaviour.
    parts["outcomes"]["outcomes"] = [
        first,
        {
            "capability_id": first["capability_id"],
            "outcome_classes": [{"id": "oc-second", "kind": "error", "description": "a second"}],
        },
        *parts["outcomes"]["outcomes"][1:],
    ]
    _write_parts(run, parts)

    path, findings = reconcile.seal(run)

    assert path is None
    assert any(
        first["capability_id"] in f.message and "more than one" in f.message for f in findings
    )
    assert not run.world_model.is_file(), "the refusal must precede the single write"


def test_a_capability_with_no_outcome_record_is_a_finding(tmp_path):
    run = build_toy_run(tmp_path, upto="extract")
    parts = split_world_model()
    parts["outcomes"]["outcomes"] = parts["outcomes"]["outcomes"][:1]
    _write_parts(run, parts)

    path, findings = reconcile.seal(run)

    assert path is None
    assert any("no outcome classes" in f.message for f in findings)
    assert not run.world_model.is_file()


def test_an_outcome_record_for_an_unknown_capability_is_a_finding(tmp_path):
    run = build_toy_run(tmp_path, upto="extract")
    parts = split_world_model()
    parts["outcomes"]["outcomes"].append(
        {
            "capability_id": "cap-invented",
            "outcome_classes": [{"id": "oc-x", "kind": "success", "description": "invented"}],
        }
    )
    _write_parts(run, parts)

    path, findings = reconcile.seal(run)

    assert path is None
    assert any("cap-invented" in f.message for f in findings)


def test_the_cli_exits_clean_and_prints_the_world_model_path(tmp_path, capsys):
    from rubrica.cli import main

    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())

    assert main(["reconcile-seal", "--run", str(run.root)]) == 0
    assert capsys.readouterr().out.strip() == str(run.world_model)


def test_the_cli_exits_one_with_findings_on_stdout(tmp_path, capsys):
    """The exit-code contract: a stage defect is 1, one finding per line, on
    stdout -- never 2, and never an empty stdout."""
    from rubrica.cli import main

    run = build_toy_run(tmp_path, upto="extract")
    parts = split_world_model()
    _write_parts(run, parts)
    run.gaps_part.unlink()

    assert main(["reconcile-seal", "--run", str(run.root)]) == 1
    out = capsys.readouterr().out
    assert out.strip(), "exit 1 with empty stdout is the failure this forbids"
    # And it names the missing partial. Measured: with the finding swallowed
    # instead of reported, the KeyError that follows is still caught and still
    # exits 1 with a line on stdout -- but that line is `[internal]` against the
    # run root, so exit code and non-empty stdout alone cannot tell the seal
    # reporting a missing partial from the catch-all rescuing an exception.
    assert "01-gaps.json" in out


def test_a_missing_run_directory_is_a_usage_error(tmp_path, capsys):
    from rubrica.cli import main

    assert main(["reconcile-seal", "--run", str(tmp_path / "nope")]) == 2


@pytest.mark.parametrize("mode", [0o000, 0o444])
def test_an_unreadable_contradictions_directory_is_exit_2_not_a_finding(tmp_path, capsys, mode):
    """The other side of the split this task has to get right: a *missing* partial
    is a repairable stage defect (1), while a run directory the harness cannot read
    is a misconfiguration (2) and repeating the pass cannot help.

    Both modes, because they are different code paths: at 0o000 the listing itself
    fails, at 0o444 the listing succeeds and stat'ing a child fails. The shape
    matters here because `Path.glob` swallows EACCES -- an unreadable 01-claims/
    once made check-refs report four `no such claim` findings against a correct
    world model, and a glob here would have the seal silently assemble a world
    model with no contradictions at all."""
    if os.geteuid() == 0:
        pytest.skip("chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)")
    from rubrica.cli import main

    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    run.contradictions_dir.chmod(mode)
    try:
        code = main(["reconcile-seal", "--run", str(run.root)])
    finally:
        run.contradictions_dir.chmod(0o755)
    captured = capsys.readouterr()
    assert code == 2, captured.out
    assert captured.out.strip() == "", "a filesystem problem must not print a finding line"
    assert captured.err.startswith("error: ")
    assert not run.world_model.is_file()


def test_a_malformed_partial_is_a_finding_naming_that_partial(tmp_path, capsys):
    """Not exit 2, and not a finding against some other artifact. This repo has
    reported four fabricated `no such claim` findings against a correct world
    model because an unreadable input was blamed on the wrong file."""
    from rubrica.cli import main

    run = build_toy_run(tmp_path, upto="extract")
    _write_parts(run, split_world_model())
    run.entities_part.write_text("{not json", encoding="utf-8")

    code = main(["reconcile-seal", "--run", str(run.root)])
    out = capsys.readouterr().out
    assert code == 1
    assert "01-entities.json" in out
