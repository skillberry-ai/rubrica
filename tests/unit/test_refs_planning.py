import json

import pytest

from rubrica.artifacts import write_json
from rubrica.errors import UsageError
from rubrica.paths import RunPaths
from rubrica.refs import (
    _cells,
    cell_ref,
    check_all,
    check_coverage,
    check_scenarios,
    check_world_model,
    drivable_cells,
    goal_ref,
    parse_hole_ref,
)
from tests.builders import minimal_claims, minimal_coverage, minimal_scenarios, minimal_world_model


def _run(tmp_path, *, claims=True, world=True, scenarios=False, coverage=False):
    run = RunPaths(tmp_path)
    if claims:
        write_json(run.claims("aap2-api"), minimal_claims())
    if world:
        write_json(run.world_model, minimal_world_model())
    if scenarios:
        write_json(run.scenarios, minimal_scenarios())
    if coverage:
        write_json(run.coverage_latest, minimal_coverage())
    return run


def _scored_run(tmp_path, *, coverage):
    """A run holding a world model, scenarios, and the given coverage payload."""
    run = RunPaths(tmp_path)
    write_json(run.world_model, minimal_world_model())
    write_json(run.scenarios, minimal_scenarios())
    write_json(run.coverage_latest, coverage)
    return run


def _coverage_run_with(tmp_path, *, capabilities, matrix_cells, holes):
    """A run holding just the two documents check_coverage's matrix clause reads.

    `_run` and `_scored_run` above both take minimal_world_model whole, and these
    fixtures need a world model with a bound and an unbound capability in it, which
    is the distinction the matrix clause turns on.

    `goals=[]` and an empty goal matrix, so the goal half contributes nothing and
    a finding these tests see came from the capability half. No scenarios file is
    written: check_coverage defaults to an empty scenario list, and no row here is
    marked covered, so nothing needs a live scenario to credit.

    `minimal_world_model`'s `denominator` is left at its default rather than
    recomputed against `capabilities`. check_coverage never reads
    `denominator.capability_cells` -- it compares only
    `coverage.denominator_version` against `world.denominator.version` -- and a
    check_coverage test must not depend on check_world_model's arithmetic.
    """
    run = RunPaths(tmp_path)
    write_json(run.world_model, minimal_world_model(capabilities=capabilities, goals=[]))
    covered = sum(1 for c in matrix_cells if c["covered"])
    write_json(
        run.coverage_latest,
        minimal_coverage(
            capability_matrix={
                "cells": matrix_cells,
                "covered": covered,
                "total": len(matrix_cells),
                "pct": (covered / len(matrix_cells)) if matrix_cells else 0.0,
            },
            goal_matrix={"rows": [], "covered": 0, "total": 0, "pct": 0.0},
            holes=holes,
        ),
    )
    return run


def _bound(cap_id, *outcome_ids):
    return {
        "id": cap_id,
        "binding": {"tool": "t", "fixed_args": {}},
        "outcome_classes": [{"id": oc} for oc in outcome_ids],
    }


def _unbound(cap_id, *outcome_ids):
    """A capability with no `binding` at all -- undrivable, and so outside the
    denominator, but still declared, so its cells stay in the wide `_cells` set."""
    return {"id": cap_id, "outcome_classes": [{"id": oc} for oc in outcome_ids]}


def _row(cap_id, oc_id):
    return {
        "capability_id": cap_id,
        "outcome_class_id": oc_id,
        "scenario_ids": [],
        "covered": False,
    }


def _hole(ref, reason, justification):
    return {"ref": ref, "reason": reason, "justification": justification}


def _matrix_findings(findings):
    """Only the two matrix-completeness messages, by pointer.

    Scoped rather than substring-filtered so the hole reconciliation's own
    findings -- which fire on some of these fixtures for legitimate reasons --
    cannot satisfy or mask an assertion about this clause.
    """
    return [f.message for f in findings if f.pointer == "/capability_matrix/cells"]


# -- hole refs ----------------------------------------------------------
def test_cell_and_goal_refs_round_trip():
    assert parse_hole_ref(cell_ref("cap-a", "oc-b")) == ("cell", ("cap-a", "oc-b"))
    assert parse_hole_ref(goal_ref("goal-x")) == ("goal", ("goal-x",))


def test_cell_ref_has_the_documented_string_form():
    assert cell_ref("cap-a", "oc-b") == "cell:cap-a/oc-b"
    assert goal_ref("goal-x") == "goal:goal-x"


@pytest.mark.parametrize("bad", ["cap-a", "cell:cap-a", "goal:", "cell:a/b/c", ""])
def test_malformed_hole_refs_raise(bad):
    with pytest.raises(ValueError):
        parse_hole_ref(bad)


# -- world model --------------------------------------------------------
def test_a_consistent_world_model_has_no_findings(tmp_path):
    assert check_world_model(_run(tmp_path)) == []


def test_a_claim_reference_with_no_matching_claim_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["capabilities"][0]["claims"] = ["clm-999"]
    write_json(run.world_model, world)
    findings = check_world_model(run)
    assert any("clm-999" in f.message for f in findings)
    assert all(f.layer == "refs" for f in findings)


def test_a_goal_pointing_at_an_unknown_actor_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["goals"][0]["actor_id"] = "act-ghost"
    write_json(run.world_model, world)
    assert any("act-ghost" in f.message for f in check_world_model(run))


def test_a_relation_pointing_at_an_unknown_entity_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["entities"][0]["relations"] = [
        {"name": "events", "target_entity_id": "ent-ghost", "cardinality": "many"}
    ]
    write_json(run.world_model, world)
    assert any("ent-ghost" in f.message for f in check_world_model(run))


def test_a_contradiction_citing_an_unknown_claim_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["contradictions"] = [
        {
            "id": "con-1",
            "claim_a": "clm-001",
            "claim_b": "clm-ghost",
            "nature": "return shape",
            "resolution": "unresolved",
            "rationale": "cannot tell which source is current",
        }
    ]
    write_json(run.world_model, world)
    assert any("clm-ghost" in f.message for f in check_world_model(run))


def test_an_invariant_over_an_undeclared_collection_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["entities"][0]["invariants"] = [
        {
            "id": "inv-1",
            "statement": "s",
            "machine": {"form": "unique", "collection": "widgets", "field": "x"},
        }
    ]
    write_json(run.world_model, world)
    assert any("widgets" in f.message for f in check_world_model(run))


def test_a_miscounted_capability_cell_denominator_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["denominator"]["capability_cells"] = 5
    write_json(run.world_model, world)
    findings = check_world_model(run)
    assert any("capability_cells" in f.message and "5" in f.message for f in findings)


def test_a_miscounted_goal_denominator_is_reported(tmp_path):
    run = _run(tmp_path)
    world = minimal_world_model()
    world["denominator"]["goals"] = 4
    write_json(run.world_model, world)
    assert any("goals" in f.message for f in check_world_model(run))


def test_duplicate_capability_ids_are_reported(tmp_path):
    """capability_cells stays 2: _cells is a set of (capability_id,
    outcome_class_id) pairs, so duplicating a capability wholesale adds no new
    cell. Bumping the denominator to 4 would provoke a second, unrelated
    finding rather than silence one, so this asserts on the exact list."""
    run = _run(tmp_path)
    world = minimal_world_model()
    world["capabilities"].append(dict(world["capabilities"][0]))
    write_json(run.world_model, world)
    findings = check_world_model(run)
    assert [(f.pointer, f.message) for f in findings] == [
        ("/capabilities", "duplicate id 'cap-find-jobs'")
    ]


# -- unbound capabilities, reported at gate 1 ---------------------------
def _binding_run_with(tmp_path, capabilities, *, goals=None):
    """A run holding the two documents check_world_model's binding clause reads.

    Local rather than a call into `test_rounds.py`'s `_world_run_with`: test
    modules here do not import each other's builders, and the two build different
    worlds anyway.

    The `denominator` is recomputed from `capabilities` and `goals`, unlike
    `_coverage_run_with` above which deliberately leaves it stale.
    check_world_model *is* the function that recomputes the denominator, so a
    stale field would add two findings of its own to every assertion below and the
    binding clause would be asserted about through a filter rather than directly.

    `minimal_claims` is written because `minimal_world_model`'s entities, actors
    and goals cite `clm-001`: without it every one of those citations becomes a
    `no such claim` finding, which is the fabricated-finding shape CLAUDE.md warns
    about rather than anything this section is testing.
    """
    run = RunPaths(tmp_path)
    write_json(run.claims("aap2-api"), minimal_claims())
    goals = [] if goals is None else goals
    write_json(
        run.world_model,
        minimal_world_model(
            capabilities=capabilities,
            goals=goals,
            denominator={
                "version": 1,
                "capability_cells": len(drivable_cells({"capabilities": capabilities})),
                "goals": len(goals),
            },
        ),
    )
    return run


def _binding_findings(findings):
    """Only the findings the unbound-capability clause raised.

    Scoped on that clause's own first phrase rather than on the bare word
    `binding`, which the denominator finding one block above could pick up if its
    wording ever changes, and no narrower than that, so a reworded justification
    does not break the filter.
    """
    return [f for f in findings if "declares no binding.tool" in f.message]


def test_check_world_model_reports_a_capability_with_no_tool_binding(tmp_path):
    """The earliest signal before this existed was emit.py:105, at stage 06 --
    after propose, score, instantiate and challenge have all run against the
    narrowed denominator, and after gates 1, 2 and 3. Its remediation ("add
    binding.tool and binding.fixed_args in the world model") asks a human to
    hand-edit a frozen, sealed artifact.

    An unbound capability is a bounded-coverage decision, and this repository's
    "no silent caps" discipline says it is reported where it is made.
    """
    run = _binding_run_with(
        tmp_path,
        [_bound("cap-bound", "oc-ok"), _unbound("cap-unbound", "oc-ok", "oc-empty")],
    )

    unbound = _binding_findings(check_world_model(run))

    assert len(unbound) == 1
    assert "cap-unbound" in unbound[0].message
    # The cell count, because that is the number a reader at gate 1 is deciding
    # about -- two cells excluded, not one capability.
    assert "2 outcome-class cells" in unbound[0].message
    # Pointed at the capability, not at the denominator: the denominator is
    # correct, and /capabilities/1 is the element a human would edit.
    assert unbound[0].pointer == "/capabilities/1"


def test_check_world_model_says_nothing_about_a_fully_bound_world_model(tmp_path):
    """The negative direction. Every fixture in the tree is fully bound, so a
    finding here would fire on all of them."""
    run = _binding_run_with(tmp_path, [_bound("cap-bound", "oc-ok")])

    assert check_world_model(run) == []


def test_check_world_model_reports_every_capability_when_none_is_bound(tmp_path):
    """Zero drivable cells is the case that most needs the finding, not the case
    that can be left to the mixed one.

    With every capability unbound and `goals: []`, `rounds.closable_holes` yields
    an empty round-1 worklist, so `propose-batches` exits 0 printing "no closable
    holes" -- the loop's *normal* terminal state, reached from a world model that
    is schema-valid and entirely undrivable. Gate 1 precedes propose, so this
    finding is the only thing standing between that world model and a human who
    reads a converged run as a covered one.

    Measured both directions against the clause it guards. Gating the loop on
    `drivable_cells(world)` being non-empty -- the shape a clause derived from the
    denominator would take -- leaves the mixed test above passing and fails only
    here, with `assert [] == ['/capabilities/0', '/capabilities/1']`. Deleting the
    loop fails both.
    """
    run = _binding_run_with(
        tmp_path,
        [_unbound("cap-a", "oc-ok"), _unbound("cap-b", "oc-ok", "oc-empty")],
    )

    findings = check_world_model(run)
    reported = [(f.pointer, f.message) for f in _binding_findings(findings)]

    assert [pointer for pointer, _ in reported] == ["/capabilities/0", "/capabilities/1"]
    # Counted per capability and not summed, because /capabilities/<index> is what a
    # human edits and "3 cells excluded" names nothing they can open.
    assert "its 1 outcome-class cells" in reported[0][1]
    assert "its 2 outcome-class cells" in reported[1][1]
    # And nothing else fires: the denominator this fixture declares is 0, which is
    # the true drivable count, so the run is internally consistent and merely
    # useless. That is why this is a finding and not a refusal.
    assert len(findings) == 2


def test_an_unreadable_claims_directory_is_a_usage_error_not_an_unbound_report(tmp_path):
    """CLAUDE.md requires the unreadable-input paths whenever refs.py is touched,
    and the rule exists because check-refs over an unreadable 01-claims/ once
    reported four fabricated `no such claim` findings against a correct world
    model.

    Measured: check_world_model raises UsageError here, and that is the designed
    answer rather than a defect this clause introduced. `_claim_ids` reads the
    directory through `paths.list_json`, which raises deliberately (paths.py:131-137)
    because an unreadable run directory is "the harness pointed at something it
    cannot read, which is exit 2" -- not a repairable stage defect at exit 1. The
    same raise happens on a fully bound world model, so the new clause is never
    reached and cannot be what turns a filesystem problem into a finding.

    Asserted rather than deleted, because the tempting version of this test -- the
    one asserting the unbound finding still lands beside an unreadable claims
    directory -- would only pass if `_claim_ids` went back to swallowing EACCES,
    which is the exact regression paths.py exists to prevent. So the guard runs in
    the other direction: no partial finding list escapes, and nothing invents a
    claim defect.
    """
    run = _binding_run_with(tmp_path, [_unbound("cap-unbound", "oc-ok", "oc-empty")])
    run.claims_dir.chmod(0o000)
    try:
        with pytest.raises(UsageError, match="cannot read run directory"):
            check_world_model(run)
    finally:
        run.claims_dir.chmod(0o755)  # restored in a finally, or the tmp_path teardown fails


def test_a_world_model_read_through_a_mode_0444_file_still_reports_the_unbound_capability(
    tmp_path,
):
    """The other unreadable-input shape CLAUDE.md names: readable but not
    writable. No checker writes, so this must be indistinguishable from the
    ordinary case -- and it is the shape a human hand-editing a sealed artifact at
    gate 1 would leave behind."""
    run = _binding_run_with(tmp_path, [_unbound("cap-unbound", "oc-ok", "oc-empty")])
    run.world_model.chmod(0o444)
    try:
        findings = check_world_model(run)
    finally:
        run.world_model.chmod(0o644)  # restored in a finally, or the tmp_path teardown fails

    assert _binding_findings(findings)
    assert not any("no such claim" in f.message for f in findings)


def test_check_all_over_a_write_protected_run_still_reports_the_unbound_capability(tmp_path):
    """The exit-code contract's second invariant: a `1` must never have empty
    stdout. An exception escaping the handler produces exactly that, and the
    finding is what puts a line on stdout in the first place."""
    run = _binding_run_with(tmp_path, [_unbound("cap-unbound", "oc-ok", "oc-empty")])
    run.root.chmod(0o555)
    try:
        findings = check_all(run)
    finally:
        run.root.chmod(0o755)  # restored in a finally, or the tmp_path teardown fails

    assert _binding_findings(findings), "a readable-but-unwritable run must report, not raise"


def _with_a_gap(world):
    """`world` plus one gap, so /gaps/{i}/claims/{k} is reachable.

    minimal_world_model seals `"gaps": []`, as does the golden toy fixture --
    deliberately, since neither world has anything missing from it. Parametrising
    only the two sites a gap-less fixture can reach is the *fixture-cannot-reach*
    weakness this repo has measured, so the gap is injected here instead of being
    given to a fixture that would then teach a skill the wrong world.
    """
    world["gaps"] = [
        {
            "id": "gap-1",
            "subject": "error semantics",
            "unknown": "what happens on an unknown controller",
            "why_it_matters": "cannot build not_found scenarios",
            "blocks": ["propose"],
            "claims": ["clm-001"],
        }
    ]
    return world


def _at_outcome_class(world):
    world["capabilities"][0]["outcome_classes"][0]["claims"] = ["clm-does-not-exist"]


def _at_invariant(world):
    world["entities"][0]["invariants"] = [
        {
            "id": "inv-1",
            "statement": "job_id is unique",
            "machine": {"form": "unique", "collection": "jobs", "field": "job_id"},
            "claims": ["clm-does-not-exist"],
        }
    ]


def _at_gap(world):
    # The caller has already run _with_a_gap, so the gap is there to mutate.
    world["gaps"][0]["claims"] = ["clm-does-not-exist"]


@pytest.mark.parametrize(
    ("site", "fabricate"),
    [
        ("/capabilities/0/outcome_classes/0/claims/0", _at_outcome_class),
        ("/entities/0/invariants/0/claims/0", _at_invariant),
        ("/gaps/0/claims/0", _at_gap),
    ],
    ids=["outcome-class", "invariant", "gap"],
)
def test_a_fabricated_claim_id_on_a_child_element_is_reported(tmp_path, site, fabricate):
    """The mirror of the parent-element check, at the three sites issue #6 added.

    Without this, a pass could satisfy the new `claims` requirement with an id it
    invented, and layer 2 -- whose whole job is that every reference resolves --
    would not look. One-directional as everywhere else in this module: that the
    id exists, never that the claim supports the element.
    """
    run = _run(tmp_path)
    world = _with_a_gap(minimal_world_model())
    fabricate(world)
    write_json(run.world_model, world)
    findings = check_world_model(run)
    assert any("clm-does-not-exist" in f.message for f in findings)
    assert any(f.pointer == site for f in findings), (
        f"reported, but not at {site}: {[f.pointer for f in findings]}"
    )


def test_a_resolvable_claim_id_on_every_child_element_is_clean(tmp_path):
    """The green direction, and what stops the three above passing vacuously.

    Each of them asserts a finding appears. A world model that was already
    reported for some unrelated reason would satisfy that without the new sites
    ever being walked, so the unmutated shape has to be known clean first.
    """
    run = _run(tmp_path)
    world = _with_a_gap(minimal_world_model())
    world["entities"][0]["invariants"] = [
        {
            "id": "inv-1",
            "statement": "job_id is unique",
            "machine": {"form": "unique", "collection": "jobs", "field": "job_id"},
            "claims": ["clm-001"],
        }
    ]
    write_json(run.world_model, world)
    assert check_world_model(run) == []


@pytest.mark.parametrize(
    "over",
    [
        {"gaps": None},
        {"gaps": "not-a-list"},
        {"gaps": [None]},
        {"gaps": [{"id": "gap-1", "claims": "not-a-list"}]},
        {"gaps": [{"id": "gap-1", "claims": [{}]}]},
        {"gaps": [{"id": "gap-1"}]},
    ],
    ids=[
        "null",
        "not-a-list",
        "list-of-non-dicts",
        "claims-not-a-list",
        "claims-holding-a-non-string",
        "no-claims-key",
    ],
)
def test_a_malformed_gaps_array_is_a_finding_or_nothing_never_a_crash(tmp_path, over):
    """`gaps` was iterated by no checker in this module until issue #6.

    So these shapes were all clean here, and a loop added without guards makes
    them raise instead. Exit **1**, not 2: `cli.py`'s named handler maps only
    (OSError, UsageError, ArtifactError, UnknownStage) to 2, and `except Exception`
    takes an AttributeError to exit 1 with a generic `internal` finding. So it is
    the *specificity* half of the exit-code rule that these break, never the
    exit-code half -- a repairable stage defect reported against nothing in
    particular, which is the wording `refs.check_world_model`'s own guard block
    carries for the same shapes. Measured before `_as_list` and the `isinstance`
    guards went in: `{"gaps": null}` and `{"gaps": "x"}` both raised
    AttributeError out of `check_world_model`, `claims: "nope"` reported one
    `no such claim` finding per character, and `claims: [{}]` raised `TypeError:
    unhashable type: 'dict'` from the membership test.

    None of these documents is schema-valid. The point is that layer 2 must not be
    the thing that discovers that by crashing, and must not invent a finding
    against a shape it cannot read.
    """
    run = _run(tmp_path)
    world = minimal_world_model()
    world.update(over)
    write_json(run.world_model, world)
    findings = check_world_model(run)
    assert isinstance(findings, list)
    assert not any("/gaps/" in f.pointer for f in findings), (
        f"a finding was fabricated against an unreadable gaps array: {findings}"
    )


def _non_string_claim_at_outcome_class(world):
    world["capabilities"][0]["outcome_classes"][0]["claims"] = [{"a": 1}]


def _non_string_claim_at_invariant(world):
    world["entities"][0]["invariants"] = [
        {
            "id": "inv-1",
            "statement": "job_id is unique",
            "machine": {"form": "unique", "collection": "jobs", "field": "job_id"},
            "claims": [{"a": 1}],
        }
    ]


def _non_string_claim_at_gap(world):
    _with_a_gap(world)["gaps"][0]["claims"] = [{"a": 1}]


@pytest.mark.parametrize(
    ("prefix", "mutate"),
    [
        ("/capabilities/0/outcome_classes/0/claims/", _non_string_claim_at_outcome_class),
        ("/entities/0/invariants/0/claims/", _non_string_claim_at_invariant),
        ("/gaps/0/claims/", _non_string_claim_at_gap),
    ],
    ids=["outcome-class", "invariant", "gap"],
)
def test_a_non_string_claim_entry_on_a_child_element_is_skipped_not_raised(
    tmp_path, prefix, mutate
):
    """A dict where a claim id belongs, at each of issue #6's three sites.

    Measured before the `isinstance(claim_id, str)` guards: every one of the three
    raised `TypeError: unhashable type: 'dict'` from `claim_id not in
    known_claims`. `cli.py`'s catch-all converts that to exit 1 with a generic
    `internal` finding rather than exit 2 -- so it is not an exit-code violation,
    but every other real finding in the world model is suppressed and replaced by a
    message naming no artifact, which is the half of the rule that says a `1` must
    name the *right* one.

    Skipped rather than reported, deliberately: `claim_refs` items `$ref`
    `#/$defs/id`, a patterned string, so layer 1 already rejects this document, and
    a property a deterministic gate enforces belongs to that gate. The denominator
    assertion is the control -- it proves the checker ran to completion and its
    later findings survived, rather than the whole thing being swallowed.
    """
    run = _run(tmp_path)
    world = minimal_world_model()
    world["denominator"]["goals"] = 99
    mutate(world)
    write_json(run.world_model, world)

    findings = check_world_model(run)
    assert not any(f.pointer.startswith(prefix) for f in findings), (
        f"a non-string claim entry was reported at {prefix}: {findings}"
    )
    assert any(f.pointer == "/denominator/goals" for f in findings), (
        "the checker aborted: a finding it reaches after the claim loops is missing"
    )


def test_a_pointer_past_a_skipped_claim_entry_is_the_document_index(tmp_path):
    """The reason the skip is a `continue` and not a filtered generator.

    A layer-2 pointer has to address the position the entry actually occupies on
    disk: `/gaps/0/claims/2` must mean the third element of that array, or a human
    following it opens the file and lands on a different one. Filtering before
    `enumerate` would renumber the survivors and report this finding at
    `/gaps/0/claims/0`, which addresses a dict.
    """
    run = _run(tmp_path)
    world = _with_a_gap(minimal_world_model())
    # Two unreadable entries ahead of the fabricated id, so a renumbering is
    # visible as a two-place shift rather than being masked by an off-by-nothing.
    world["gaps"][0]["claims"] = [{}, 7, "clm-does-not-exist"]
    write_json(run.world_model, world)

    findings = check_world_model(run)
    assert [(f.pointer, f.message) for f in findings] == [
        ("/gaps/0/claims/2", "no such claim: clm-does-not-exist")
    ]


# -- scenarios ----------------------------------------------------------
def test_consistent_scenarios_have_no_findings(tmp_path):
    assert check_scenarios(_run(tmp_path, scenarios=True)) == []


def test_a_capability_ref_to_an_unknown_capability_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    payload = minimal_scenarios()
    payload["scenarios"][0]["capability_refs"] = [
        {"capability_id": "cap-ghost", "outcome_class_id": "oc-success"}
    ]
    write_json(run.scenarios, payload)
    assert any("cap-ghost" in f.message for f in check_scenarios(run))


def test_a_capability_ref_to_a_wrong_outcome_class_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    payload = minimal_scenarios()
    payload["scenarios"][0]["capability_refs"] = [
        {"capability_id": "cap-find-jobs", "outcome_class_id": "oc-ghost"}
    ]
    write_json(run.scenarios, payload)
    assert any("oc-ghost" in f.message for f in check_scenarios(run))


def test_a_scenario_with_an_unknown_goal_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    payload = minimal_scenarios()
    payload["scenarios"][0]["goal_id"] = "goal-ghost"
    write_json(run.scenarios, payload)
    assert any("goal-ghost" in f.message for f in check_scenarios(run))


def test_a_duplicate_pointing_at_no_such_scenario_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    payload = minimal_scenarios()
    payload["scenarios"][0]["status"] = "duplicate"
    payload["scenarios"][0]["duplicate_of"] = "scn-ghost"
    write_json(run.scenarios, payload)
    assert any("scn-ghost" in f.message for f in check_scenarios(run))


def test_a_hole_ref_naming_no_real_cell_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    payload = minimal_scenarios()
    payload["scenarios"][0]["provenance"]["hole_refs"] = ["cell:cap-ghost/oc-success"]
    write_json(run.scenarios, payload)
    assert any("cap-ghost" in f.message for f in check_scenarios(run))


def test_a_stale_denominator_version_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    write_json(run.scenarios, minimal_scenarios(denominator_version=2))
    assert any("denominator_version" in f.message for f in check_scenarios(run))


def test_duplicate_scenario_ids_are_reported(tmp_path):
    run = _run(tmp_path, scenarios=True)
    payload = minimal_scenarios()
    payload["scenarios"].append(dict(payload["scenarios"][0]))
    write_json(run.scenarios, payload)
    assert any("duplicate" in f.message for f in check_scenarios(run))


# -- coverage -----------------------------------------------------------
def test_consistent_coverage_has_no_findings(tmp_path):
    assert check_coverage(_run(tmp_path, scenarios=True, coverage=True)) == []


def test_a_coverage_matrix_missing_a_real_cell_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["capability_matrix"]["cells"] = payload["capability_matrix"]["cells"][:1]
    payload["capability_matrix"]["total"] = 1
    payload["capability_matrix"]["pct"] = 1.0
    write_json(run.coverage_latest, payload)
    assert any("oc-empty" in f.message for f in check_coverage(run))


def test_a_coverage_matrix_inventing_a_cell_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["capability_matrix"]["cells"].append(
        {
            "capability_id": "cap-ghost",
            "outcome_class_id": "oc-success",
            "scenario_ids": [],
            "covered": False,
        }
    )
    # Both total and pct must follow the added row, or the arithmetic check
    # fires too and the test would pass on the wrong finding.
    payload["capability_matrix"]["total"] = 3
    payload["capability_matrix"]["pct"] = 1 / 3
    write_json(run.coverage_latest, payload)
    findings = check_coverage(run)
    # The invented cell isn't a real cell, so no hole can name it either -- it
    # is also uncovered and unjustified, which is a second, legitimate finding
    # now that holes are related to the matrices.
    assert [f.message for f in findings] == [
        "matrix invents cell cell:cap-ghost/oc-success",
        "cell:cap-ghost/oc-success is uncovered but no hole justifies it",
    ]


def test_check_coverage_accepts_a_matrix_of_drivable_cells_with_holes_on_the_rest(tmp_path):
    """The fabricated-finding guard for issue 17's narrowing.

    check_coverage compared matrix rows against the WIDE cell set, so a matrix
    that correctly enumerates only drivable cells reported one 'matrix omits
    cell' finding per undrivable cell -- 37 of them on run-20260827-070444,
    against a document that was right. That is the class CLAUDE.md's rule about a
    `1` naming the right artifact exists over.

    The undrivable cell is still carried, as an `unreachable` hole, so nothing
    disappears from the report. Its ref has to RESOLVE, which is why _cells stays
    wide: narrow that resolution and this test goes red on 'hole names no real
    cell'.
    """
    run = _coverage_run_with(
        tmp_path,
        capabilities=[_bound("cap-bound", "oc-ok"), _unbound("cap-unbound", "oc-ok")],
        # Drivable cells only -- what rounds.capability_matrix produces once the
        # narrowing this guard precedes lands.
        matrix_cells=[_row("cap-bound", "oc-ok")],
        holes=[
            _hole("cell:cap-bound/oc-ok", "not_yet_attempted", "no scenario proposed yet"),
            _hole("cell:cap-unbound/oc-ok", "unreachable", "capability declares no binding.tool"),
        ],
    )

    findings = check_coverage(run)

    assert [f.message for f in findings] == []


def test_check_coverage_still_reports_a_matrix_that_omits_a_drivable_cell(tmp_path):
    """The other direction, so the narrowed comparison is not narrowed into
    vacuity: dropping a DRIVABLE cell from the matrix is still a finding. Without
    this, a matrix holding only the cells some scenario happened to claim would
    report 100% of a denominator it shrank to fit -- the failure
    rounds.capability_matrix' docstring ranks first.
    """
    run = _coverage_run_with(
        tmp_path,
        capabilities=[_bound("cap-bound", "oc-ok", "oc-empty")],
        matrix_cells=[_row("cap-bound", "oc-ok")],
        holes=[_hole("cell:cap-bound/oc-ok", "not_yet_attempted", "no scenario yet")],
    )

    findings = check_coverage(run)

    assert _matrix_findings(findings) == ["matrix omits cell cell:cap-bound/oc-empty"]


def test_check_coverage_reports_a_matrix_row_on_an_undrivable_cell(tmp_path):
    """The invented-cell direction, which this narrowing TIGHTENS.

    Against the wide set a row on an undrivable cell resolved and passed. It is a
    finding now: that cell sits outside the scored surface, so it belongs in the
    holes rather than in the matrix, and a row there puts an undrivable cell back
    into the denominator every percentage is measured against.

    Its own message, not 'matrix invents cell': the cell IS declared, and a human
    at gate 2 told the matrix invented something they can find in
    01-world-model.json reads that as the checker being wrong.
    """
    run = _coverage_run_with(
        tmp_path,
        capabilities=[_bound("cap-bound", "oc-ok"), _unbound("cap-unbound", "oc-ok")],
        matrix_cells=[_row("cap-bound", "oc-ok"), _row("cap-unbound", "oc-ok")],
        holes=[
            _hole("cell:cap-bound/oc-ok", "not_yet_attempted", "no scenario yet"),
            _hole("cell:cap-unbound/oc-ok", "unreachable", "capability declares no binding.tool"),
        ],
    )

    findings = check_coverage(run)

    assert _matrix_findings(findings) == [
        "matrix scores undrivable cell cell:cap-unbound/oc-ok; it belongs in the holes"
    ]


def test_check_coverage_separates_an_undrivable_row_from_an_invented_one(tmp_path):
    """The partition itself, in one document, because `seen - drivable` holds both
    kinds and only the wide `_cells` set tells them apart. A single message for the
    pair would make the two indistinguishable in a gate-2 report, where one is a
    row that should have been a hole and the other is a row naming nothing.
    """
    run = _coverage_run_with(
        tmp_path,
        capabilities=[_bound("cap-bound", "oc-ok"), _unbound("cap-unbound", "oc-ok")],
        matrix_cells=[
            _row("cap-bound", "oc-ok"),
            _row("cap-unbound", "oc-ok"),
            # No capability declares this pair at all.
            _row("cap-ghost", "oc-nope"),
        ],
        holes=[
            _hole("cell:cap-bound/oc-ok", "not_yet_attempted", "no scenario yet"),
            _hole("cell:cap-unbound/oc-ok", "unreachable", "capability declares no binding.tool"),
        ],
    )

    findings = check_coverage(run)

    # Sorted by pair, so the ghost precedes the unbound capability.
    assert _matrix_findings(findings) == [
        "matrix invents cell cell:cap-ghost/oc-nope",
        "matrix scores undrivable cell cell:cap-unbound/oc-ok; it belongs in the holes",
    ]


def test_inconsistent_covered_arithmetic_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["capability_matrix"]["covered"] = 2
    write_json(run.coverage_latest, payload)
    assert any("covered" in f.message for f in check_coverage(run))


def test_a_pct_that_disagrees_with_the_counts_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["capability_matrix"]["pct"] = 0.9
    write_json(run.coverage_latest, payload)
    assert any("pct" in f.message for f in check_coverage(run))


def test_a_cell_citing_an_unknown_scenario_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["capability_matrix"]["cells"][0]["scenario_ids"] = ["scn-ghost"]
    write_json(run.coverage_latest, payload)
    assert any("scn-ghost" in f.message for f in check_coverage(run))


def test_a_cell_marked_covered_with_no_scenarios_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["capability_matrix"]["cells"][1]["covered"] = True
    payload["capability_matrix"]["covered"] = 2
    payload["capability_matrix"]["pct"] = 1.0
    write_json(run.coverage_latest, payload)
    assert any("no scenarios" in f.message for f in check_coverage(run))


def test_a_blocked_by_gap_hole_naming_no_real_gap_is_reported(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    payload = minimal_coverage()
    payload["holes"][0]["reason"] = "blocked_by_gap"
    payload["holes"][0]["gap_id"] = "gap-ghost"
    write_json(run.coverage_latest, payload)
    assert any("gap-ghost" in f.message for f in check_coverage(run))


def test_an_uncovered_cell_with_no_hole_is_reported(tmp_path):
    """Without this, a report can claim zero holes while cells sit uncovered."""
    coverage = minimal_coverage(holes=[])
    run = _scored_run(tmp_path, coverage=coverage)
    messages = " || ".join(f.message for f in check_coverage(run))
    assert "cell:cap-find-jobs/oc-empty is uncovered but no hole justifies it" in messages
    assert "goal:goal-triage is uncovered but no hole justifies it" in messages


def test_a_hole_naming_a_covered_row_is_reported(tmp_path):
    coverage = minimal_coverage()
    coverage["holes"].append(
        {
            "ref": "cell:cap-find-jobs/oc-success",
            "reason": "not_yet_attempted",
            "justification": "claims a hole in a cell the same report marks covered",
        }
    )
    run = _scored_run(tmp_path, coverage=coverage)
    messages = " || ".join(f.message for f in check_coverage(run))
    assert "cell:cap-find-jobs/oc-success" in messages
    assert "the matrix marks covered" in messages


def test_hop_depths_expected_must_match_the_world_model(tmp_path):
    coverage = minimal_coverage()
    coverage["goal_matrix"]["rows"][0]["hop_depths_expected"] = [1]
    run = _scored_run(tmp_path, coverage=coverage)
    findings = [f for f in check_coverage(run) if "hop_depths_expected" in f.pointer]
    assert len(findings) == 1
    assert "[1, 2]" in findings[0].message


def test_hop_depths_present_must_be_derived_from_the_listed_scenarios(tmp_path):
    coverage = minimal_coverage()
    coverage["goal_matrix"]["rows"][0]["hop_depths_present"] = [1, 2]
    run = _scored_run(tmp_path, coverage=coverage)
    findings = [f for f in check_coverage(run) if "hop_depths_present" in f.pointer]
    assert len(findings) == 1
    assert "scn-001" in findings[0].message or "[2]" in findings[0].message


def test_a_goal_row_marked_covered_without_scenarios_is_reported(tmp_path):
    coverage = minimal_coverage()
    row = coverage["goal_matrix"]["rows"][0]
    row["scenario_ids"] = []
    row["hop_depths_present"] = []
    row["covered"] = True
    coverage["goal_matrix"]["covered"] = 1
    coverage["goal_matrix"]["pct"] = 1.0
    run = _scored_run(tmp_path, coverage=coverage)
    findings = [f for f in check_coverage(run) if f.pointer.endswith("/covered")]
    assert len(findings) == 1
    assert "lists no scenarios" in findings[0].message


def test_a_goal_row_covered_at_only_some_expected_hop_depths_is_not_covered(tmp_path):
    """The builder payload is exactly this case: expected [1, 2], present [2]."""
    coverage = minimal_coverage()
    row = coverage["goal_matrix"]["rows"][0]
    row["covered"] = True
    coverage["goal_matrix"]["covered"] = 1
    coverage["goal_matrix"]["pct"] = 1.0
    run = _scored_run(tmp_path, coverage=coverage)
    messages = " || ".join(f.message for f in check_coverage(run))
    assert "hop depth" in messages


# -- coverage credited to a scenario that no longer counts ------------------
#
# check_coverage checked that a cited scenario_id *existed* and never that it was
# still live, so a cell could stay covered by a scenario challenge rejected or
# dedupe folded away, with check-refs and validate --stage score both green.


def _two_scenarios(dead_status, **dead_extra):
    """scn-001 (hop 2) with the given status, plus a live scn-002 (hop 1)."""
    doc = minimal_scenarios()
    first = doc["scenarios"][0]
    first["status"] = dead_status
    first.update(dead_extra)
    second = json.loads(json.dumps(first))
    second["id"] = "scn-002"
    second["hop_depth"] = 1
    second["status"] = "active"
    second.pop("rejected_reason", None)
    second.pop("duplicate_of", None)
    doc["scenarios"].append(second)
    return doc


def _run_with(tmp_path, scenarios, coverage):
    run = RunPaths(tmp_path)
    write_json(run.world_model, minimal_world_model())
    write_json(run.scenarios, scenarios)
    write_json(run.coverage_latest, coverage)
    return run


@pytest.mark.parametrize(
    "status, extra",
    [
        ("rejected", {"rejected_reason": "ambiguous"}),
        ("duplicate", {"duplicate_of": "scn-002"}),
    ],
)
def test_a_covered_cell_credited_only_to_a_dead_scenario_is_reported(tmp_path, status, extra):
    """A rejection reopens the cell; a dedupe fold moves the credit elsewhere.

    Both are handled by the same rule because OPEN_STATUSES is the same "still
    counts" set the max_scenarios cap uses: a duplicate is never instantiated and
    never emitted, so no test ships for the cell it claimed.
    """
    run = _run_with(tmp_path, _two_scenarios(status, **extra), minimal_coverage())
    findings = [f for f in check_coverage(run) if f.pointer == "/capability_matrix/cells/0"]
    assert len(findings) == 1
    assert "scn-001" in findings[0].message
    assert "recompute coverage" in findings[0].message, "the finding must say what to do"


def test_a_covered_goal_row_credited_only_to_a_rejected_scenario_is_reported(tmp_path):
    """The goal matrix gets the same rule as the capability matrix.

    Both feed _check_matrix_arithmetic and the hole reconciliation, so checking
    only the cells would leave the goal denominator confidently wrong in exactly
    the state the capability denominator reports.
    """
    scenarios = _two_scenarios("rejected", rejected_reason="ambiguous")
    scenarios["scenarios"][1]["status"] = "rejected"
    scenarios["scenarios"][1]["rejected_reason"] = "ambiguous"

    coverage = minimal_coverage()
    row = coverage["goal_matrix"]["rows"][0]
    row["scenario_ids"] = ["scn-001", "scn-002"]
    row["hop_depths_present"] = [1, 2]
    row["covered"] = True
    coverage["goal_matrix"]["covered"] = 1
    coverage["goal_matrix"]["pct"] = 1.0
    # The goal is covered now, so its honest-hole entry has to go with it.
    coverage["holes"] = [h for h in coverage["holes"] if h["ref"] != goal_ref("goal-triage")]

    run = _run_with(tmp_path, scenarios, coverage)
    findings = [f for f in check_coverage(run) if f.pointer == "/goal_matrix/rows/0"]
    assert len(findings) == 1
    assert "scn-001, scn-002" in findings[0].message
    assert "recompute coverage" in findings[0].message


def test_a_covered_row_credited_to_both_a_live_and_a_dead_scenario_is_clean(tmp_path):
    """The narrowness of the rule: one live scenario still exercises the cell.

    Firing on *any* dead credit would make check-refs dirty for the whole run
    after a single rejection in a well-covered cell, which is the phantom-repair
    failure the states table exists to prevent.
    """
    scenarios = _two_scenarios("rejected", rejected_reason="ambiguous")
    coverage = minimal_coverage()
    coverage["capability_matrix"]["cells"][0]["scenario_ids"] = ["scn-001", "scn-002"]
    run = _run_with(tmp_path, scenarios, coverage)
    assert check_coverage(run) == []


def test_the_builder_coverage_payload_is_clean(tmp_path):
    """Guards the builders: every later state test depends on this staying true."""
    run = _scored_run(tmp_path, coverage=minimal_coverage())
    assert check_coverage(run) == []


# -- drivable cells -----------------------------------------------------
def test_drivable_cells_keeps_only_cells_whose_capability_names_a_tool():
    """The scoring set, as distinct from refs._cells' resolver set.

    Measured on run-20260827-070444: 24 capabilities, 5 bound, 37 of 56 cells on
    capabilities emit.bindings drops. Both spellings are needed at once -- a hole
    ref on an undrivable cell still has to RESOLVE (refs._cells) while the
    denominator must not COUNT it (this function), which is why narrowing _cells
    in place would fabricate findings against correct artifacts.
    """
    world = {
        "capabilities": [
            {
                "id": "cap-bound",
                "binding": {"tool": "query_tickets", "fixed_args": {}},
                "outcome_classes": [{"id": "oc-ok"}, {"id": "oc-empty"}],
            },
            # Key absent -- the shape 19 of 24 capabilities had on the measured run.
            {"id": "cap-absent", "outcome_classes": [{"id": "oc-ok"}]},
            # Explicit null. Not schema-legal (binding is an object), but a
            # hand-edit at gate 1 produces it and `.get("binding", {}).get` raises
            # AttributeError on it rather than reading as unbound.
            {"id": "cap-null", "binding": None, "outcome_classes": [{"id": "oc-ok"}]},
            # Present but no tool: also undrivable, because emit.call_spec reads
            # binding["tool"] and nothing else identifies the call.
            {
                "id": "cap-no-tool",
                "binding": {"fixed_args": {}},
                "outcome_classes": [{"id": "oc-ok"}],
            },
        ]
    }
    assert drivable_cells(world) == {("cap-bound", "oc-ok"), ("cap-bound", "oc-empty")}
    # The resolver stays wide over the same input: five cells, not two.
    assert len(_cells(world)) == 5


def test_drivable_cells_counts_distinct_pairs_rather_than_summing():
    """limitations.md:1330 -- a sum of per-capability outcome-class counts agrees
    with the set only until an id repeats, at which point the sum is the wrong
    number. A repeated outcome-class id is schema-legal.
    """
    world = {
        "capabilities": [
            {
                "id": "cap-a",
                "binding": {"tool": "t", "fixed_args": {}},
                "outcome_classes": [{"id": "oc-ok"}, {"id": "oc-ok"}],
            }
        ]
    }
    assert drivable_cells(world) == {("cap-a", "oc-ok")}
    assert len(drivable_cells(world)) == 1  # a sum would say 2


def test_drivable_cells_tolerates_a_world_model_missing_its_collections():
    """check_all has no ordering guarantee that layer 1 rejected a malformed
    document first, which is the argument refs._as_list already carries.
    """
    assert drivable_cells({}) == set()
    assert drivable_cells({"capabilities": []}) == set()
    assert (
        drivable_cells({"capabilities": [{"id": "c", "binding": {"tool": "t", "fixed_args": {}}}]})
        == set()
    )


# -- check_all ----------------------------------------------------------
def test_check_all_tolerates_a_run_that_has_only_reached_reconcile(tmp_path):
    assert check_all(_run(tmp_path)) == []


def test_check_all_tolerates_an_empty_run_directory(tmp_path):
    assert check_all(RunPaths(tmp_path)) == []


def test_check_all_aggregates_findings_from_every_present_artifact(tmp_path):
    run = _run(tmp_path, scenarios=True, coverage=True)
    world = minimal_world_model()
    world["denominator"]["goals"] = 9
    write_json(run.world_model, world)
    payload = minimal_scenarios()
    payload["scenarios"][0]["goal_id"] = "goal-ghost"
    write_json(run.scenarios, payload)
    messages = " ".join(f.message for f in check_all(run))
    assert "goals" in messages
    assert "goal-ghost" in messages
