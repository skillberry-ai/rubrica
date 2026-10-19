"""`rubrica rule` and the gate-1 rulings it records, applied by code.

Built on the toy run sealed through `reconcile-seal`: two bound capabilities on
one tool (`query_tickets`), one service, one contradiction resolved
`preferred_a`, no gaps. Each test adds only the partial content its ruling
needs, re-seals, and asserts on what the seal made of it, so a difference is
attributable to the ruling alone.
"""

from __future__ import annotations

import json
import os

import pytest

from rubrica import cli, interfaces, reconcile, refs, rulings, validate
from rubrica.artifacts import read_json, write_json
from rubrica.errors import UsageError
from tests.toy import build_toy_run

CONTRADICTION = "con-missing-semantics"


@pytest.fixture
def run(tmp_path):
    return build_toy_run(tmp_path / "runs", upto="reconcile-seal")


def _seal(run):
    path, findings = reconcile.seal(run)
    assert findings == [], findings
    return read_json(path)


def _partials(run) -> dict[str, bytes]:
    paths = [
        run.capabilities_part,
        run.outcomes_part,
        run.entities_part,
        run.goals_part,
        run.gaps_part,
        run.services_part,
        *sorted(run.contradictions_dir.iterdir()),
    ]
    return {p.name: p.read_bytes() for p in paths}


def _add_gap(run, blocks=("instantiate",)):
    part = read_json(run.gaps_part)
    part["gaps"] = [
        {
            "id": "gap-order",
            "subject": "cap-get-ticket",
            "unknown": "the order comments come back in",
            "why_it_matters": "a scenario asserting order would be labelled against nothing",
            "blocks": list(blocks),
            "claims": ["clm-api-006"],
        }
    ]
    write_json(run.gaps_part, part)


def _unbind(run, cap="cap-get-ticket"):
    part = read_json(run.capabilities_part)
    for capability in part["capabilities"]:
        if capability["id"] == cap:
            capability.pop("binding")
    write_json(run.capabilities_part, part)


def _second_service(run):
    part = read_json(run.services_part)
    tool = dict(part["services"][0]["tools"][0], name="query_comments")
    part["services"].append(
        {
            "id": "svc-comments",
            "statement": "The comments backend",
            "tools": [tool],
            "signals": [{"kind": "no_outward_evidence_found", "locator": "api-json"}],
        }
    )
    write_json(run.services_part, part)


# -- contradictions ----------------------------------------------------------


def test_a_contradiction_ruling_reaches_the_sealed_world_model(run):
    before = _partials(run)
    rulings.rule(
        run,
        kind="contradictions",
        entry={"id": CONTRADICTION, "resolution": "preferred_b"},
        reason="the trace is what the target does",
    )
    world = _seal(run)
    assert world["contradictions"][0]["resolution"] == "preferred_b"
    assert _partials(run) == before
    ruling = read_json(run.rulings)["contradictions"][0]
    assert (ruling["replaces"], ruling["resolution"]) == ("preferred_a", "preferred_b")
    assert validate.validate_artifact(run.rulings, "rulings") == []
    assert refs.check_all(run) == []


def test_clearing_a_ruling_restores_the_passes_value(run):
    original = _seal(run)
    rulings.rule(
        run,
        kind="contradictions",
        entry={"id": CONTRADICTION, "resolution": "unresolved"},
        reason="r",
    )
    rulings.clear(run, kind="contradictions", ref=CONTRADICTION, reason="undo")
    assert "contradictions" not in read_json(run.rulings)
    assert _seal(run)["contradictions"] == original["contradictions"]


def test_resealing_with_rulings_is_byte_identical(run):
    rulings.rule(
        run,
        kind="contradictions",
        entry={"id": CONTRADICTION, "resolution": "unresolved"},
        reason="r",
    )
    _seal(run)
    first = run.world_model.read_bytes()
    _seal(run)
    assert run.world_model.read_bytes() == first


def test_editing_the_rulings_after_the_seal_is_a_stale_partial(run):
    rulings.rule(
        run,
        kind="contradictions",
        entry={"id": CONTRADICTION, "resolution": "unresolved"},
        reason="r",
    )
    _seal(run)
    document = read_json(run.rulings)
    document["contradictions"][0]["resolution"] = "both_possible"
    write_json(run.rulings, document)
    stale = [f for f in refs.check_partials(run) if f.artifact == run.rulings]
    assert stale, refs.check_partials(run)


# -- gaps ---------------------------------------------------------------------


def test_a_gap_can_be_accepted_without_breaking_the_world_models_schema(run):
    _add_gap(run)
    rulings.rule(
        run,
        kind="gaps",
        entry={"id": "gap-order", "ruling": "accept"},
        reason="order is not tested",
    )
    world = _seal(run)
    assert world["gaps"][0]["blocks"] == ["instantiate"]
    assert rulings.accepted_gaps(rulings.load(run)) == {"gap-order"}
    assert rulings.blocking_gaps(world["gaps"], rulings.load(run)) == []
    assert refs.check_all(run) == []


def test_a_gaps_blocks_can_be_replaced(run):
    _add_gap(run)
    rulings.rule(
        run,
        kind="gaps",
        entry={"id": "gap-order", "ruling": "blocks", "blocks": ["emit"]},
        reason="only emitting needs it",
    )
    assert _seal(run)["gaps"][0]["blocks"] == ["emit"]
    assert read_json(run.rulings)["gaps"][0]["replaces"] == ["instantiate"]


# -- capabilities ----------------------------------------------------------------


def test_binding_an_unbound_capability_raises_the_denominator(run):
    _unbind(run)
    unbound = _seal(run)["denominator"]["capability_cells"]
    rulings.rule(
        run,
        kind="capabilities",
        entry={
            "id": "cap-get-ticket",
            "ruling": "bind",
            "binding": {"tool": "query_tickets", "fixed_args": {"action": "get_ticket"}},
        },
        reason="it is query_tickets with action=get_ticket",
    )
    world = _seal(run)
    cap = next(c for c in world["capabilities"] if c["id"] == "cap-get-ticket")
    assert cap["binding"] == {"tool": "query_tickets", "fixed_args": {"action": "get_ticket"}}
    assert world["denominator"]["capability_cells"] > unbound
    assert refs.check_all(run) == []


def test_accepting_an_unbound_capability_changes_nothing_in_the_world_model(run):
    _unbind(run)
    before = _seal(run)
    rulings.rule(
        run,
        kind="capabilities",
        entry={"id": "cap-get-ticket", "ruling": "accept_unbound"},
        reason="r",
    )
    after = _seal(run)
    assert after["capabilities"] == before["capabilities"]
    assert after["denominator"] == before["denominator"]


# -- services ---------------------------------------------------------------------


def test_moving_a_tool_regroups_the_services_and_the_interfaces(run):
    _second_service(run)
    rulings.rule(
        run,
        kind="services",
        entry={"op": "move_tool", "tool": "query_comments", "to": "svc-tickets"},
        reason="one backend serves both",
    )
    world = _seal(run)
    assert [s["id"] for s in world["services"]] == ["svc-tickets"]
    assert [t["name"] for t in world["services"][0]["tools"]] == ["query_tickets", "query_comments"]
    written, findings = interfaces.synthesise(run)
    assert findings == []
    assert sorted(p.name for p in run.interfaces_dir.iterdir()) == ["svc-tickets.json"]
    assert len(read_json(run.services_part)["services"]) == 2


def test_merge_and_split_are_inverse_regroupings():
    run = None
    services = [
        {
            "id": "a",
            "statement": "A",
            "tools": [{"name": "x"}, {"name": "y"}],
            "signals": [{"kind": "k"}],
        },
        {"id": "b", "statement": "B", "tools": [{"name": "z"}], "signals": [{"kind": "k2"}]},
    ]
    split = {
        "services": [
            {"op": "split", "service": "a", "tools": ["y"], "new_id": "c", "statement": "C"}
        ]
    }
    out, problems = rulings.effective_services(run, services, split)
    assert problems == []
    assert {s["id"]: [t["name"] for t in s["tools"]] for s in out} == {
        "a": ["x"],
        "b": ["z"],
        "c": ["y"],
    }
    merge = {"services": [{"op": "merge", "service": "b", "into": "a"}]}
    out, problems = rulings.effective_services(run, services, merge)
    assert problems == []
    assert {s["id"]: [t["name"] for t in s["tools"]] for s in out} == {"a": ["x", "y", "z"]}
    assert services[0]["tools"] == [{"name": "x"}, {"name": "y"}], "the pass's list is not mutated"


# -- refusals --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "entry", "message"),
    [
        ("contradictions", {"id": "con-nope", "resolution": "unresolved"}, "no contradiction part"),
        ("contradictions", {"id": CONTRADICTION, "resolution": "preferred_a"}, "already resolved"),
        ("gaps", {"id": "gap-nope", "ruling": "accept"}, "records no gap"),
        ("capabilities", {"id": "cap-nope", "ruling": "accept_unbound"}, "records no capability"),
        ("capabilities", {"id": "cap-get-ticket", "ruling": "accept_unbound"}, "already bound"),
        (
            "capabilities",
            {
                "id": "cap-get-ticket",
                "ruling": "bind",
                "binding": {"tool": "nope", "fixed_args": {}},
            },
            "no service declares tool",
        ),
        ("services", {"op": "move_tool", "tool": "query_tickets", "to": "svc-nope"}, "cannot move"),
        (
            "services",
            {"op": "merge", "service": "svc-tickets", "into": "svc-tickets"},
            "cannot merge",
        ),
    ],
)
def test_a_ruling_that_names_nothing_real_is_refused_and_writes_nothing(run, kind, entry, message):
    with pytest.raises(UsageError, match=message):
        rulings.rule(run, kind=kind, entry=entry, reason="r")
    assert not run.rulings.exists()
    assert not run.decisions.exists() or "ruling at gate 1" not in run.decisions.read_text()


def test_binding_to_an_undeclared_tool_is_refused(run):
    _unbind(run)
    with pytest.raises(UsageError, match="no service declares tool 'nope'"):
        rulings.rule(
            run,
            kind="capabilities",
            entry={
                "id": "cap-get-ticket",
                "ruling": "bind",
                "binding": {"tool": "nope", "fixed_args": {}},
            },
            reason="r",
        )


def test_a_second_ruling_on_one_target_is_refused(run):
    rulings.rule(
        run,
        kind="contradictions",
        entry={"id": CONTRADICTION, "resolution": "unresolved"},
        reason="r",
    )
    with pytest.raises(UsageError, match="already has a ruling"):
        rulings.rule(
            run,
            kind="contradictions",
            entry={"id": CONTRADICTION, "resolution": "both_possible"},
            reason="r",
        )


def test_rulings_are_refused_once_propose_has_read_the_world_model(run):
    run.batches_dir.mkdir()
    with pytest.raises(UsageError, match="gate 1 is past"):
        rulings.rule(
            run,
            kind="contradictions",
            entry={"id": CONTRADICTION, "resolution": "unresolved"},
            reason="r",
        )


def test_a_ruling_the_partials_no_longer_support_is_a_seal_finding_against_the_rulings(run):
    write_json(
        run.rulings,
        {
            "schema_version": "0.1",
            "contradictions": [
                {
                    "id": "con-gone",
                    "resolution": "unresolved",
                    "replaces": "preferred_a",
                    "reason": "r",
                    "recorded_at": "t",
                }
            ],
        },
    )
    path, findings = reconcile.seal(run)
    assert path is None
    assert [(f.artifact, f.layer) for f in findings] == [(run.rulings, "rulings")]
    assert [(f.artifact, f.layer) for f in refs.check_rulings(run)] == [(run.rulings, "rulings")]


def test_a_malformed_rulings_file_is_a_usage_error_for_the_seal_and_the_command(run):
    run.rulings.write_text('{"schema_version": "0.1", "gaps": "nope"}', encoding="utf-8")
    with pytest.raises(UsageError, match="unusable rulings"):
        reconcile.seal(run)
    with pytest.raises(UsageError, match="unusable rulings"):
        rulings.rule(
            run,
            kind="contradictions",
            entry={"id": CONTRADICTION, "resolution": "unresolved"},
            reason="r",
        )


# -- the CLI ---------------------------------------------------------------------------


def _cli(run, *args):
    return cli.main(["rule", "--run", str(run.root), *args])


def test_the_cli_records_a_ruling_and_names_the_next_steps(run, capsys):
    code = _cli(
        run, "--contradiction", CONTRADICTION, "--resolution", "unresolved", "--reason", "r"
    )
    out = capsys.readouterr()
    assert code == 0
    assert out.out.strip() == f"contradiction {CONTRADICTION}: preferred_a -> unresolved"
    assert "reconcile-capabilities" in out.err and "reconcile-seal" in out.err
    line = run.decisions.read_text(encoding="utf-8").splitlines()[-1]
    assert f"ruling at gate 1: contradiction {CONTRADICTION}" in line
    assert not line.split(" ", 2)[2].startswith(("gate", "human gate"))


@pytest.mark.parametrize(
    "args",
    [
        ["--gap", "gap-order", "--reason", "r"],
        ["--gap", "gap-order", "--accept", "--blocks", "emit", "--reason", "r"],
        ["--capability", "cap-get-ticket", "--reason", "r"],
        ["--contradiction", CONTRADICTION, "--reason", "r"],
        ["--move-tool", "query_tickets", "--reason", "r"],
        ["--service-op", "0", "--reason", "r"],
        [
            "--capability",
            "cap-get-ticket",
            "--bind-tool",
            "query_tickets",
            "--fixed-args",
            "[]",
            "--reason",
            "r",
        ],
    ],
)
def test_incomplete_or_contradictory_cli_requests_exit_two_with_empty_stdout(run, capsys, args):
    _add_gap(run)
    code = _cli(run, *args)
    out = capsys.readouterr()
    assert code == 2
    assert out.out == ""
    assert out.err.startswith("error: ")


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads through chmod 000")
def test_an_unreadable_rulings_file_is_exit_two_naming_it(run, capsys):
    write_json(run.rulings, {"schema_version": "0.1"})
    run.rulings.chmod(0o000)
    try:
        code = _cli(
            run, "--contradiction", CONTRADICTION, "--resolution", "unresolved", "--reason", "r"
        )
        seal_code = cli.main(["reconcile-seal", "--run", str(run.root)])
    finally:
        run.rulings.chmod(0o644)
    out = capsys.readouterr()
    assert (code, seal_code) == (2, 2)
    assert out.out == ""
    assert run.rulings.name in out.err


def test_a_bad_schema_dir_is_exit_two(run, capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("RUBRICA_SCHEMA_DIR", str(tmp_path / "nowhere"))
    code = _cli(
        run, "--contradiction", CONTRADICTION, "--resolution", "unresolved", "--reason", "r"
    )
    assert code == 2
    assert capsys.readouterr().out == ""


def test_the_rulings_schema_rejects_an_unknown_field(run):
    write_json(run.rulings, {"schema_version": "0.1", "extra": 1})
    assert validate.validate_artifact(run.rulings, "rulings")
    json.loads(run.rulings.read_text())
