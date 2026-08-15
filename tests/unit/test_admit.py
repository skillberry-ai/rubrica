"""intake --run: admitting the triage record's admits into 00-inputs/.

survey.survey over tests/fixtures/corpus-toy/ produces eleven candidates
(gitignore, readme-md, api-json, capture-json plus its four exploded
elements, notes-md, locked-md, tool-defs-py -- see test_survey_fixture.py for
the same corpus). Every test here hand-writes a triage record admitting the
prose file and two of the four trace elements and declining the rest, since
check_triage requires one disposition per candidate.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rubrica import cli, intake, refs, survey, validate
from rubrica.artifacts import read_json, write_json
from rubrica.errors import UsageError
from rubrica.paths import RunPaths

FIXTURE = Path(__file__).parent.parent / "fixtures" / "corpus-toy"
NOW = datetime(2026, 8, 14, 21, 30, 0, tzinfo=UTC)

# Every candidate_id survey.survey produces over corpus-toy that is not one of
# the three admitted below (readme-md, capture-json-0, capture-json-1).
_DECLINED = (
    "gitignore",
    "api-json",
    "capture-json",
    "capture-json-2",
    "capture-json-3",
    "notes-md",
    "locked-md",
    "tool-defs-py",
)
_ADMITTED = ("readme-md", "capture-json-0", "capture-json-1")


def _surveyed(tmp_path) -> RunPaths:
    return survey.survey(
        corpus_roots=[FIXTURE],
        runs_dir=tmp_path / "runs",
        target_name="ticketq",
        target_interface="mcp",
        objective="breadth",
        max_rounds=2,
        max_scenarios=128,
        now=NOW,
    )


def _triage_record(run_id: str, *, drop_a_disposition: bool, decline_everything: bool) -> dict:
    admitted = () if decline_everything else _ADMITTED
    dispositions = []
    for cid in admitted:
        dispositions.append(
            {
                "candidate_id": cid,
                "disposition": "admit",
                "reason": "carries evidence of the target's shape",
                "authority": "triage",
            }
        )
    for cid in (*_DECLINED, *(_ADMITTED if decline_everything else ())):
        dispositions.append(
            {
                "candidate_id": cid,
                "disposition": "decline",
                "reason_code": "no_evidence_value",
                "reason": "adds nothing the admitted set does not already carry",
                "authority": "triage",
            }
        )
    if drop_a_disposition:
        dispositions = [d for d in dispositions if d["candidate_id"] != "tool-defs-py"]
    return {
        "schema_version": "0.1",
        "run_id": run_id,
        "objective_review": {
            "declared_objective": "breadth",
            "supported": True,
            "surfaces": [
                {
                    "name": "the admitted set",
                    "evidence": ["readme-md"],
                    "weight": {"candidates": len(admitted), "bytes": 1},
                }
            ],
        },
        "dispositions": dispositions,
        "deficiencies": [],
        "projections": [],
    }


def _surveyed_and_triaged(
    tmp_path, *, drop_a_disposition: bool = False, decline_everything: bool = False
) -> RunPaths:
    run = _surveyed(tmp_path)
    write_json(
        run.triage,
        _triage_record(
            run.root.name,
            drop_a_disposition=drop_a_disposition,
            decline_everything=decline_everything,
        ),
    )
    return run


def test_admitting_writes_inputs_and_a_valid_manifest(tmp_path):
    run = _surveyed_and_triaged(tmp_path)
    assert intake.admit_from_triage(run) == []
    manifest = read_json(run.manifest)
    assert {e["artifact_id"] for e in manifest["inputs"]} == set(_ADMITTED)
    assert validate.validate_stage(run, "intake") == []
    assert refs.check_all(run) == []


def test_the_manifest_takes_its_parameters_from_the_catalogue(tmp_path):
    """Not from argv. One file the human edits at gate 0, one file intake reads."""
    run = _surveyed_and_triaged(tmp_path)
    intake.admit_from_triage(run)
    manifest = read_json(run.manifest)
    catalogue = read_json(run.catalogue)
    assert manifest["target"] == catalogue["request"]["target"]
    assert manifest["limits"] == catalogue["request"]["limits"]
    assert manifest["created_utc"] == catalogue["created_utc"]


def test_a_declined_candidate_is_not_admitted(tmp_path):
    run = _surveyed_and_triaged(tmp_path)
    intake.admit_from_triage(run)
    stored = {p.name for p in run.inputs_dir.iterdir()}
    assert not any("logo" in name or "lock" in name for name in stored)


def test_an_inconsistent_triage_record_is_findings_and_writes_nothing(tmp_path):
    """Exit 1, repairable by re-dispatching triage -- never exit 2. A stage defect
    surfacing as 2 makes the orchestrator halt instead of spending its one repair.
    """
    run = _surveyed_and_triaged(tmp_path, drop_a_disposition=True)
    findings = intake.admit_from_triage(run)
    assert findings
    assert all("00-triage.json" in str(f.artifact) for f in findings)
    assert not run.manifest.exists()
    assert not run.inputs_dir.exists()


def test_zero_admits_is_findings_rather_than_an_empty_manifest(tmp_path):
    """inputs.minItems is 1, so writing the manifest anyway would surface a
    scoping failure as a schema error against an artifact no prompt wrote."""
    run = _surveyed_and_triaged(tmp_path, decline_everything=True)
    findings = intake.admit_from_triage(run)
    assert findings and not run.manifest.exists()


def test_admitting_twice_refuses_rather_than_rewriting(tmp_path):
    """A re-run gets a new run id so old artifacts stay diffable -- the rule
    intake() already holds for its run directory."""
    run = _surveyed_and_triaged(tmp_path)
    intake.admit_from_triage(run)
    with pytest.raises(FileExistsError):
        intake.admit_from_triage(run)


def test_an_admit_naming_a_candidate_the_catalogue_does_not_carry_is_a_finding(tmp_path):
    """check_triage's own "no such candidate" check (refs.py) is gated behind
    `if candidates`, so it is silent whenever the catalogue's own candidates
    list is empty -- exactly what a degenerate catalogue looks like. Without
    its own check, admit_from_triage would hit `candidates[d["candidate_id"]]`
    directly and raise KeyError: an uncaught exception here is exit 1 with
    empty stdout, indistinguishable from a crashed harness rather than a
    repairable stage defect. Must come back as a finding against
    00-triage.json instead, and write nothing.
    """
    run = _surveyed(tmp_path)
    catalogue = read_json(run.catalogue)
    catalogue["candidates"] = []
    write_json(run.catalogue, catalogue)
    write_json(
        run.triage,
        _triage_record(run.root.name, drop_a_disposition=False, decline_everything=False),
    )

    assert refs.check_triage(run) == [], "the setup itself must not be caught by layer 2 first"

    findings = intake.admit_from_triage(run)
    assert findings
    assert all("00-triage.json" in str(f.artifact) for f in findings)
    assert any("readme-md" in f.message for f in findings)
    assert not run.manifest.exists()
    assert not run.inputs_dir.exists()


def test_a_missing_triage_record_is_a_usage_error(tmp_path):
    """Stages run out of order is a misconfigured harness, which is exit 2."""
    run = _surveyed(tmp_path)
    with pytest.raises(UsageError, match="00-triage.json"):
        intake.admit_from_triage(run)


def test_run_and_input_are_mutually_exclusive():
    parser = cli._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["intake", "--run", "r", "--input", "x"])


def test_run_mode_rejects_the_parameters_the_catalogue_already_carries(capsys):
    """Refused in the CLI rather than resolved by precedence: minting from an
    ambiguous parameter set is the shape that produced findings against an
    unfixable artifact. argparse cannot express "illegal only alongside --run"
    directly, so this is checked in cli.main after parsing -- but it is a
    usage error like any other on this path, caught in the same try/except as
    the admit_from_triage call rather than left to escape cli.main(): an
    escaping UsageError would print nothing to stdout and exit 1, indistinguishable
    from a stage defect. exit 2 with a message on stderr, not SystemExit or an
    uncaught exception.
    """
    code = cli.main(["intake", "--run", "r", "--target-name", "t"])
    assert code == 2
    assert "target-name" in capsys.readouterr().err


def test_intake_run_via_the_cli_prints_the_run_and_exits_clean(tmp_path, capsys):
    run = _surveyed_and_triaged(tmp_path)
    code = cli.main(["intake", "--run", str(run.root)])
    assert code == 0
    assert capsys.readouterr().out.strip() == str(run.root)


def test_intake_run_via_the_cli_reports_findings_at_exit_one(tmp_path, capsys):
    run = _surveyed_and_triaged(tmp_path, drop_a_disposition=True)
    code = cli.main(["intake", "--run", str(run.root)])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out.strip()
    assert not run.manifest.exists()


def test_a_catalogue_missing_corpus_roots_is_a_finding_not_a_traceback(tmp_path):
    """catalogue["request"]["corpus_roots"] used to be a bare index -- on an
    unvalidated catalogue (hand-edited, or written by a future producer that
    gets it wrong) that raises KeyError, and cli.py's adopt-projection/intake
    dispatch blocks catch only (UsageError, ArtifactError, OSError), so the
    KeyError would escape main() as a traceback: an empty-stdout exit,
    exactly what the exit-code contract's "a 1 must never have empty stdout"
    rule forbids. A malformed catalogue is a repairable stage defect, and
    this function already returns findings for one shape of that (see the
    unknown-admitted-candidate test elsewhere in this file), so a missing
    corpus_roots becomes one too, rather than raising.
    """
    run = _surveyed_and_triaged(tmp_path)
    catalogue = read_json(run.catalogue)
    del catalogue["request"]["corpus_roots"]
    write_json(run.catalogue, catalogue)

    findings = intake.admit_from_triage(run)

    assert len(findings) == 1
    assert findings[0].artifact == run.catalogue
    assert "corpus_roots" in findings[0].message
    assert not run.inputs_dir.exists()
    assert not run.manifest.exists()


def test_a_catalogue_missing_its_target_is_a_finding_and_leaves_the_run_retryable(tmp_path, capsys):
    """The Critical of this branch's whole-branch review, in one test.

    `catalogue["request"]["target"]["name"]`, `["limits"]["max_rounds"]` and
    `datetime.strptime(catalogue["created_utc"], ...)` were bare indexes running
    *after* the 00-inputs/ materialise loop and *outside* the try whose except
    cleans it up. Deleting `request.target` -- exactly the hand-edit gate 0
    authorises on 00-catalogue.json -- breached the contract three ways in one
    command:

        KeyError: 'target'   -> escaped cli.main(), exit 1, empty stdout
        00-inputs/ left fully populated with no manifest
        every retry -> "error: [Errno 17] File exists: .../00-inputs", exit 2

    That third one is what made it Critical rather than Important: repairing the
    catalogue could not recover the run, so a survey plus a triage dispatch were
    both wasted. The retry succeeding at exit 0 is the assertion that matters
    most here; the finding and the absent 00-inputs/ are how it gets there.
    """
    run = _surveyed_and_triaged(tmp_path)
    catalogue = read_json(run.catalogue)
    del catalogue["request"]["target"]
    write_json(run.catalogue, catalogue)

    assert cli.main(["intake", "--run", str(run.root)]) == 1
    printed = capsys.readouterr().out
    assert printed.strip(), "exit 1 with empty stdout is the shape this closed"
    assert "00-catalogue.json" in printed, "the finding must name the artifact carrying the defect"
    assert "/request/target" in printed, "and point at the key that is missing"
    # Nothing left behind: the check runs before the mkdir, so the failed
    # admission is not merely cleaned up, it never created anything.
    assert not run.inputs_dir.exists()
    assert not run.manifest.exists()

    catalogue["request"]["target"] = {"name": "ticketq", "interface": "mcp"}
    write_json(run.catalogue, catalogue)
    assert cli.main(["intake", "--run", str(run.root)]) == 0
    assert {e["artifact_id"] for e in read_json(run.manifest)["inputs"]} == set(_ADMITTED)


@pytest.mark.parametrize(
    ("pointer", "mutate"),
    [
        ("/request/target", lambda c: c["request"].pop("target")),
        ("/request/target/name", lambda c: c["request"]["target"].update(name="   ")),
        ("/request/target/interface", lambda c: c["request"]["target"].pop("interface")),
        ("/request/limits", lambda c: c["request"].pop("limits")),
        ("/request/limits/max_rounds", lambda c: c["request"]["limits"].update(max_rounds=0)),
        (
            "/request/limits/max_scenarios",
            lambda c: c["request"]["limits"].update(max_scenarios="8"),
        ),
        ("/created_utc", lambda c: c.pop("created_utc")),
        ("/created_utc", lambda c: c.update(created_utc=17)),
    ],
)
def test_no_catalogue_defect_ever_yields_a_manifest_layer_one_rejects(tmp_path, pointer, mutate):
    """Every one of register()'s five arguments, checked at its own pointer.

    Two failure shapes hide behind these eight mutations and only the first was
    ever reported. The absent-key ones raised out of main(); the *out-of-range*
    ones (`max_rounds: 0`, `max_scenarios: "8"`, a blank target name) did not
    raise at all -- they wrote a manifest at exit 0 that `validate --stage
    intake` then rejected, which is the same misdirection intake()'s own
    argument checks exist to prevent: a finding against manifest.json, an
    artifact no skill wrote and no repair prompt can fix.

    So the assertion is the *property* rather than either shape: whatever is
    wrong with the catalogue, this command either writes a manifest layer 1
    accepts or writes nothing and says why.
    """
    run = _surveyed_and_triaged(tmp_path)
    catalogue = read_json(run.catalogue)
    mutate(catalogue)
    write_json(run.catalogue, catalogue)

    findings = intake.admit_from_triage(run)

    assert findings, f"{pointer}: a malformed catalogue must be reported, not written through"
    assert all(f.artifact == run.catalogue for f in findings)
    assert any(f.pointer == pointer for f in findings), (
        f"expected a finding at {pointer}, got {[f.pointer for f in findings]}"
    )
    assert not run.manifest.exists()
    assert not run.inputs_dir.exists()


@pytest.mark.parametrize("root_index", [5, -1, "0", True, None])
def test_an_admitted_candidates_root_index_is_checked_against_the_roots_it_indexes(
    tmp_path, root_index
):
    """`roots[candidate.get("root_index", 0)]` had no length check.

    `_container_path` already guarded its own copy of this lookup, with the
    reasoning that resolving against the catalogue's own record of a root is
    what keeps a wrong-file read from being silent -- and a *corpus* candidate's
    root_index had no guard at all. A hand-edited `5` against one corpus root
    raised IndexError straight out of main() (a string one, TypeError); `True`
    is here because `isinstance(True, int)` is True in Python and `roots[True]`
    silently reads the second root rather than raising, which is the wrong file
    with no error anywhere.
    """
    run = _surveyed_and_triaged(tmp_path)
    catalogue = read_json(run.catalogue)
    for candidate in catalogue["candidates"]:
        if candidate.get("candidate_id") == "readme-md":
            candidate["root_index"] = root_index
    write_json(run.catalogue, catalogue)

    findings = intake.admit_from_triage(run)

    assert findings
    assert all(f.artifact == run.catalogue for f in findings)
    assert any("root_index" in f.message for f in findings)
    assert not run.inputs_dir.exists()
    assert not run.manifest.exists()


def test_the_admit_order_survives_a_priority_the_schema_would_have_rejected(tmp_path):
    """The sort key had to become a total order over unvalidated JSON.

    `(d.get("priority", 1 << 30), d.get("candidate_id"))` raised
    `TypeError: '<' not supported between instances of 'int' and 'str'` on a
    triage record mixing a string priority with an integer one, out of main()
    at exit 1 with empty stdout -- and admit_from_triage's own comments say
    twice that it does not assume layer 1 has already run. The three callers of
    intake.admit_sort_key (this one, refs.check_admitted_inputs, and
    brief._gate_0) must also agree on the *order*, not merely each not raise,
    because _unique_artifact_id's collision suffixes are derived from it.
    """
    run = _surveyed_and_triaged(tmp_path)
    triage = read_json(run.triage)
    for index, disposition in enumerate(triage["dispositions"]):
        if disposition["disposition"] == "admit":
            disposition["priority"] = "high" if index == 0 else 1
    write_json(run.triage, triage)

    assert intake.admit_from_triage(run) == []
    assert {e["artifact_id"] for e in read_json(run.manifest)["inputs"]} == set(_ADMITTED)
    # check_admitted_inputs replays the same sort to recover which artifact_id
    # each candidate became, so a second spelling of the key would report every
    # admission as both missing and unadmitted.
    assert refs.check_admitted_inputs(run) == []


def test_a_string_priority_sorts_as_if_absent_rather_than_reordering_the_admits(tmp_path):
    """The other direction of the guard above: coercion must not silently
    reorder admits whose priorities are fine. A disposition with no usable
    priority sorts last, which is where one that declares none already sorted.
    """
    ordered = sorted(
        [
            {"candidate_id": "b", "priority": 2},
            {"candidate_id": "a", "priority": "high"},
            {"candidate_id": "c", "priority": 1},
            {"candidate_id": "d"},
        ],
        key=intake.admit_sort_key,
    )
    assert [d["candidate_id"] for d in ordered] == ["c", "b", "a", "d"]


def test_admission_is_retryable_once_a_disappeared_source_file_returns(tmp_path):
    """A source file can vanish between survey and intake -- deleted, moved,
    whatever -- and materialise raises OSError partway through the admit loop,
    having already copied readme-md's alphabetical predecessors
    (capture-json-0, capture-json-1) into 00-inputs/ first. Before the fix,
    that left 00-inputs/ half-populated with no manifest, and every retry hit
    FileExistsError on run.inputs_dir.mkdir forever -- permanently stuck. The
    run must come back to its pre-admission state instead, so this same call
    can simply be made again once the file is restored. That second call
    succeeding is the point of this test, not the directory-is-gone cleanup
    on its own.
    """
    # A copy, not FIXTURE itself: this test deletes one of the corpus files,
    # and tests/fixtures/corpus-toy/ is a checked-in fixture other tests in
    # this module (and test_survey_fixture.py) read from the same session.
    corpus = tmp_path / "corpus-copy"
    shutil.copytree(FIXTURE, corpus)
    run = survey.survey(
        corpus_roots=[corpus],
        runs_dir=tmp_path / "runs",
        target_name="ticketq",
        target_interface="mcp",
        objective="breadth",
        max_rounds=2,
        max_scenarios=128,
        now=NOW,
    )
    write_json(
        run.triage,
        _triage_record(run.root.name, drop_a_disposition=False, decline_everything=False),
    )

    readme = corpus / "README.md"
    original = readme.read_bytes()
    readme.unlink()

    with pytest.raises(OSError):
        intake.admit_from_triage(run)
    assert not run.inputs_dir.exists()
    assert not run.manifest.exists()

    readme.write_bytes(original)
    assert intake.admit_from_triage(run) == []
    manifest = read_json(run.manifest)
    assert {e["artifact_id"] for e in manifest["inputs"]} == set(_ADMITTED)
