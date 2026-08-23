"""The exit-code contract over *present but malformed* ingestion artifacts.

This file exists because the shape it guards recurred four times on one branch,
and two earlier fix rounds patched individual sites without sweeping the class.
Every case below is one mutation of a readable run's 00-catalogue.json or
00-triage.json -- the two documents gate 0 explicitly invites a human to
hand-edit, so "malformed" here is not a hypothetical corruption but the
expected outcome of an ordinary hand-edit -- driven through `cli.main` and
checked against the contract rather than against a message:

    0  clean
    1  findings, one per line ON STDOUT, never empty
    2  usage error, or an unreadable/misconfigured run

The two invariants that were breached, both stated in cli.py's own docstring:
**a 1 must never have empty stdout** (an exception escaping main() produces
exactly that) and **a stage defect must never surface as 2** (the orchestrator
halts instead of spending its one repair attempt). A third, from
claim-utilisation's ruling and restated at cli.py's gate-brief arm: **a report
command always exits 0 on a readable run**, so an orchestrator reading its exit
code cannot mistake data for a defect.

Deliberately asserting the contract and not the wording. A per-mutation
expected message would pin prose that is free to improve, and would not have
caught any of the eleven real failures -- every one of them was an exception
type nobody had enumerated, which is exactly what a contract-shaped assertion
catches and a message-shaped one does not. The named findings' *specific*
behaviour (which artifact a finding points at, whether a run stays retryable)
is asserted in each module's own test file.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rubrica import cli, survey
from rubrica.artifacts import read_json, write_json
from tests.unit.test_admit import _triage_record

CORPUS = Path(__file__).parent.parent / "fixtures" / "corpus-toy"
NOW = datetime(2026, 8, 14, 21, 30, 0, tzinfo=UTC)


def _retarget(catalogue: dict, root_index) -> None:
    """One candidate's root_index, which indexes request.corpus_roots."""
    for candidate in catalogue["candidates"]:
        if candidate.get("candidate_id") == "readme-md":
            candidate["root_index"] = root_index


def _repriority(triage: dict, value) -> None:
    """One admit gets `value` as its priority and its siblings an integer one.

    Mixing the two is the point: a *uniformly* string priority sorts fine, so a
    mutation that set them all would have measured green against the pre-fix
    code and proved nothing.
    """
    for index, disposition in enumerate(triage["dispositions"]):
        if disposition["disposition"] == "admit":
            disposition["priority"] = value if index == 0 else 1


def _renull_one_admit(triage: dict) -> None:
    """One admit's candidate_id becomes null, its siblings keeping theirs --
    mixed for _repriority's reason: the sort key has to compare the two."""
    for disposition in triage["dispositions"]:
        if disposition["disposition"] == "admit":
            disposition["candidate_id"] = None
            break


# Every mutation is `(label, mutate_catalogue, mutate_triage)`, applied to a
# real surveyed-and-triaged run. A `None` mutator leaves that document as
# survey (or the fixture) wrote it. Each was measured against the pre-fix code;
# ESCAPED marks the ones that took an exception straight out of main().
MUTATIONS: tuple[tuple[str, object, object], ...] = (
    # C1: the whole reason this file exists. Deleting request.target from a
    # surveyed catalogue -- the hand-edit gate 0 authorises -- ESCAPED with
    # KeyError, and left the run permanently unusable afterwards.
    ("catalogue has no request.target", lambda c: c["request"].pop("target"), None),
    ("catalogue has no request.limits", lambda c: c["request"].pop("limits"), None),
    ("catalogue has no created_utc", lambda c: c.pop("created_utc"), None),
    ("catalogue request is a string", lambda c: c.update(request="nope"), None),
    ("catalogue target is a string", lambda c: c["request"].update(target="nope"), None),
    ("catalogue target.name is blank", lambda c: c["request"]["target"].update(name="   "), None),
    ("catalogue max_rounds is zero", lambda c: c["request"]["limits"].update(max_rounds=0), None),
    (
        "catalogue max_scenarios is a string",
        lambda c: c["request"]["limits"].update(max_scenarios="8"),
        None,
    ),
    ("catalogue created_utc is not a stamp", lambda c: c.update(created_utc="yesterday"), None),
    # ESCAPED with TypeError rather than ValueError: strptime raises TypeError
    # when handed a number, which a `except ValueError` guard would have missed.
    ("catalogue created_utc is a number", lambda c: c.update(created_utc=17), None),
    # Sweep: root_index indexes request.corpus_roots with no length check.
    # ESCAPED (IndexError; TypeError for the string form).
    ("catalogue root_index is out of range", lambda c: _retarget(c, 5), None),
    ("catalogue root_index is a string", lambda c: _retarget(c, "0"), None),
    # Sweep: the admits sort key was not a total order. Both ESCAPED (TypeError).
    ("triage priority is a string on one admit", None, lambda t: _repriority(t, "high")),
    ("triage candidate_id is null on one admit", None, _renull_one_admit),
    # I7 and its siblings: element-level `.get` with no isinstance guard.
    ("triage deficiencies carries a string", None, lambda t: t.update(deficiencies=["oops"])),
    ("triage projections carries a string", None, lambda t: t.update(projections=["oops"])),
    # Distinct from the entry above, and the distinction is the whole point: a
    # list *carrying* a string lands at exit 2 by the legitimate "no such
    # projection" path, while a `projections` that is not a list at all is a
    # malformed record -- and that reached the same exit 2, surfacing a stage
    # defect as a misconfigured harness, which makes the orchestrator halt
    # instead of spending its one repair attempt. Sweep fix 6's headline case,
    # unguarded until this line existed.
    ("triage projections is a string", None, lambda t: t.update(projections="nope")),
    ("triage dispositions is a string", None, lambda t: t.update(dispositions="nope")),
    ("triage objective_review is a string", None, lambda t: t.update(objective_review="nope")),
    (
        "triage recommended_objective is a string",
        None,
        lambda t: t["objective_review"].update(recommended_objective="depth"),
    ),
    ("triage sources is a string", None, lambda t: t["projections"][0].update(sources="nope")),
    ("triage closes carries a list", None, lambda t: t["projections"][0].update(closes=[["x"]])),
    (
        "triage acceptance has no classifies_as",
        None,
        lambda t: t["projections"][0].update(acceptance={"prose": "p"}),
    ),
    (
        "triage must_contain carries a number",
        None,
        lambda t: t["projections"][0]["acceptance"].update(must_contain=[17]),
    ),
    (
        "triage pointers_required carries a number",
        None,
        lambda t: t["projections"][0]["acceptance"].update(pointers_required=[17]),
    ),
    ("catalogue candidates is a string", lambda c: c.update(candidates="nope"), None),
    ("catalogue candidates carries a string", lambda c: c.update(candidates=["oops"]), None),
    (
        "catalogue candidate_id is a list",
        lambda c: c["candidates"].append({"candidate_id": ["a"], "origin": "corpus"}),
        None,
    ),
    ("catalogue policy is a string", lambda c: c.update(policy="nope"), None),
    (
        "catalogue digest_body_chars is a bool",
        lambda c: c["policy"].update(digest_body_chars=True),
        None,
    ),
)


def _run(tmp_path, label):
    """A real surveyed run with a real triage record, then one mutation."""
    run = survey.survey(
        corpus_roots=[CORPUS],
        runs_dir=tmp_path / "runs",
        target_name="ticketq",
        target_interface="mcp",
        objective="breadth",
        max_rounds=2,
        max_scenarios=128,
        now=NOW,
    )
    triage = _triage_record(run.root.name, drop_a_disposition=False, decline_everything=False)
    # A projection, so `adopt-projection` has something to name. Its acceptance
    # contract is satisfied by the file _projection_source writes, so on an
    # unmutated run the command reaches its write path rather than stopping at
    # a structural finding.
    triage["deficiencies"] = [
        {
            "deficiency_id": "def-1",
            "subject": "the tool result shape",
            "statement": "no admitted candidate records what a call returns",
        }
    ]
    triage["projections"] = [
        {
            "projection_id": "prj-1",
            "wanted": {"statement": "one tool schema carrying result shapes"},
            "closes": ["def-1"],
            "sources": [{"candidate_id": "readme-md"}],
            "method": {"confidence": "high"},
            "acceptance": {"classifies_as": "mcp_tool_schema", "prose": "shapes are named"},
        }
    ]

    catalogue_mutator, triage_mutator = next(
        (c, t) for candidate_label, c, t in MUTATIONS if candidate_label == label
    )
    if triage_mutator is not None:
        triage_mutator(triage)
    write_json(run.triage, triage)

    if catalogue_mutator is not None:
        catalogue = read_json(run.catalogue)
        catalogue_mutator(catalogue)
        write_json(run.catalogue, catalogue)
    return run


def _projection_source(tmp_path) -> Path:
    source = tmp_path / "manufactured.json"
    source.write_text(json.dumps({"tools": [{"name": "list_tickets"}]}), encoding="utf-8")
    return source


LABELS = [label for label, _, _ in MUTATIONS]


@pytest.mark.parametrize("label", LABELS)
def test_intake_run_never_escapes_main_on_a_malformed_artifact(tmp_path, label, capsys):
    """Exit 1 with lines on stdout, or exit 2 -- never a traceback out of main().

    Exit 2 is accepted for *some* mutations here on purpose: a triage record
    whose only admit names a null candidate_id can legitimately reach the
    "nothing was admitted" path, and the run-level failures cli.py maps to 2
    are not what this asserts. What it asserts is that main() returns an int
    and that a 1 is never silent.
    """
    run = _run(tmp_path, label)
    code = cli.main(["intake", "--run", str(run.root)])
    captured = capsys.readouterr()
    assert code in (0, 1, 2), f"{label}: main() returned {code!r}"
    if code == 1:
        assert captured.out.strip(), f"{label}: exit 1 with empty stdout"


@pytest.mark.parametrize("label", LABELS)
@pytest.mark.parametrize("gate", [0, 1, 2, 3])
def test_gate_brief_always_exits_clean_on_a_malformed_artifact(tmp_path, label, gate, capsys):
    """A report is never a gate: claim-utilisation's ruling, restated at
    cli.py's gate-brief arm and broken by seven of these mutations, each of
    which turned this command into a fabricated `[internal]` finding at exit 1.
    """
    run = _run(tmp_path, label)
    code = cli.main(["gate-brief", "--run", str(run.root), "--gate", str(gate)])
    captured = capsys.readouterr()
    assert code == 0, f"{label}, gate {gate}: gate-brief exited {code}"
    assert captured.out.strip(), f"{label}, gate {gate}: rendered nothing"


@pytest.mark.parametrize("label", LABELS)
def test_adopt_projection_never_escapes_main_on_a_malformed_artifact(tmp_path, label, capsys):
    run = _run(tmp_path, label)
    code = cli.main(
        [
            "adopt-projection",
            "--run",
            str(run.root),
            "--projection",
            "prj-1",
            "--file",
            str(_projection_source(tmp_path)),
        ]
    )
    captured = capsys.readouterr()
    assert code in (0, 1, 2), f"{label}: main() returned {code!r}"
    if code == 1:
        assert captured.out.strip(), f"{label}: exit 1 with empty stdout"


@pytest.mark.parametrize("label", LABELS)
def test_check_refs_never_escapes_main_on_a_malformed_artifact(tmp_path, label, capsys):
    run = _run(tmp_path, label)
    code = cli.main(["check-refs", "--run", str(run.root)])
    captured = capsys.readouterr()
    assert code in (0, 1, 2), f"{label}: main() returned {code!r}"
    if code == 1:
        assert captured.out.strip(), f"{label}: exit 1 with empty stdout"


@pytest.mark.parametrize("label", LABELS)
def test_validate_survey_and_triage_never_escape_main(tmp_path, label, capsys):
    """Layer 1 is the layer that is *supposed* to name every mutation above, so
    it is also the one that must not fall over reaching them."""
    run = _run(tmp_path, label)
    # "triage-seal", not "triage": the record's kind is still `triage`, but the
    # stage that writes 00-triage.json is the family's seal. Naming the retired
    # stage here would make every iteration an exit-2 usage error, which is in
    # the accepted set and so would pass while reaching none of layer 1.
    for stage in ("survey", "triage-seal"):
        code = cli.main(["validate", "--run", str(run.root), "--stage", stage])
        captured = capsys.readouterr()
        assert code in (0, 1, 2), f"{label}/{stage}: main() returned {code!r}"
        if code == 1:
            assert captured.out.strip(), f"{label}/{stage}: exit 1 with empty stdout"
