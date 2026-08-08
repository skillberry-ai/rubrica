"""record-stage and decide: the manifest's stage map and the run's notebook.

Both were declared by the design spec and implemented by nobody. The manifest
one matters most: stability.comparability gates diff-runs' headline verdict on
the stage map matching, so with the map empty two unrelated runs compare as
comparable -- a check that passes because the data is absent.
"""

from __future__ import annotations

import re

from testgen.artifacts import read_json, write_json
from testgen.cli import main
from testgen.paths import RunPaths
from testgen.skills import skill_sha256
from testgen.stability import comparability, stage_config
from testgen.validate import manifest_stage_efforts, validate_artifact
from tests.builders import minimal_manifest


def _run(tmp_path, stages=None):
    run = RunPaths(tmp_path / "run-20260808-120000")
    manifest = minimal_manifest()
    manifest["stages"] = {} if stages is None else stages
    write_json(run.manifest, manifest)
    return run


def _skill(tmp_path, text="# tg-extract\n"):
    path = tmp_path / "SKILL.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_record_stage_writes_model_effort_and_the_skill_digest(tmp_path):
    run = _run(tmp_path)
    skill = _skill(tmp_path)
    assert (
        main(
            [
                "record-stage",
                "--run",
                str(run.root),
                "--stage",
                "extract",
                "--model",
                "claude-sonnet-5",
                "--effort",
                "high",
                "--skill",
                str(skill),
            ]
        )
        == 0
    )
    assert read_json(run.manifest)["stages"] == {
        "extract": {
            "model": "claude-sonnet-5",
            "effort": "high",
            "skill_sha256": skill_sha256(skill),
        }
    }


def test_the_recorded_digest_is_of_the_file_that_was_passed(tmp_path):
    """Not a caller-supplied string, and not a fixed placeholder. Editing the
    skill and re-recording must change the digest, or the hook records nothing
    that could ever make two runs incomparable.
    """
    run = _run(tmp_path)
    skill = _skill(tmp_path)
    argv = [
        "record-stage",
        "--run",
        str(run.root),
        "--stage",
        "extract",
        "--model",
        "m",
        "--effort",
        "high",
        "--skill",
        str(skill),
    ]
    assert main(argv) == 0
    before = read_json(run.manifest)["stages"]["extract"]["skill_sha256"]
    skill.write_text("# tg-extract\n\nA changed Method section.\n", encoding="utf-8")
    assert main(argv) == 0
    assert read_json(run.manifest)["stages"]["extract"]["skill_sha256"] != before


def test_record_stage_merges_rather_than_replacing_the_map(tmp_path):
    """A stage re-dispatched after a repair must not erase its siblings."""
    run = _run(
        tmp_path, stages={"reconcile": {"model": "m", "effort": "high", "skill_sha256": "b" * 64}}
    )
    assert (
        main(
            [
                "record-stage",
                "--run",
                str(run.root),
                "--stage",
                "extract",
                "--model",
                "m",
                "--effort",
                "low",
                "--skill",
                str(_skill(tmp_path)),
            ]
        )
        == 0
    )
    assert set(read_json(run.manifest)["stages"]) == {"reconcile", "extract"}


def test_recording_the_same_stage_twice_overwrites_only_that_entry(tmp_path):
    run = _run(
        tmp_path,
        stages={"reconcile": {"model": "keep-me", "effort": "high", "skill_sha256": "b" * 64}},
    )
    skill = _skill(tmp_path)
    for effort in ("low", "max"):
        assert (
            main(
                [
                    "record-stage",
                    "--run",
                    str(run.root),
                    "--stage",
                    "reconcile",
                    "--model",
                    "changed",
                    "--effort",
                    effort,
                    "--skill",
                    str(skill),
                ]
            )
            == 0
        )
    stages = read_json(run.manifest)["stages"]
    assert stages["reconcile"] == {
        "model": "changed",
        "effort": "max",
        "skill_sha256": skill_sha256(skill),
    }


def test_the_manifest_still_validates_after_recording(tmp_path):
    """The map is schema-gated, so a writer that got the shape wrong would be
    caught by `validate --stage intake` -- but only if someone ran it. This is
    that someone.
    """
    run = _run(tmp_path)
    assert (
        main(
            [
                "record-stage",
                "--run",
                str(run.root),
                "--stage",
                "emit",
                "--model",
                "claude-sonnet-5",
                "--effort",
                "medium",
                "--skill",
                str(_skill(tmp_path)),
            ]
        )
        == 0
    )
    assert validate_artifact(run.manifest, "manifest") == []


def test_recording_does_not_reformat_the_rest_of_the_manifest(tmp_path):
    """Byte stability is the reproducibility premise: diff-runs must not report
    formatting as variance. A hand-rolled json.dump would rewrite every line.
    """
    run = _run(tmp_path)
    before = run.manifest.read_text(encoding="utf-8")
    assert (
        main(
            [
                "record-stage",
                "--run",
                str(run.root),
                "--stage",
                "extract",
                "--model",
                "m",
                "--effort",
                "high",
                "--skill",
                str(_skill(tmp_path)),
            ]
        )
        == 0
    )
    after = run.manifest.read_text(encoding="utf-8")
    # Every line of the original survives except the one-line empty stages map.
    unchanged = [line for line in before.splitlines() if line.strip() != '"stages": {},']
    for line in unchanged:
        assert line in after.splitlines(), line


def test_two_runs_recording_different_skills_are_not_comparable(tmp_path):
    """The check that was passing on absent data. Before this task both runs
    had `stages: {}`, so comparability found nothing to disagree about.
    """
    a, b = _run(tmp_path / "a"), _run(tmp_path / "b")
    for run, text in ((a, "# v1\n"), (b, "# v2\n")):
        skill = run.root / "SKILL.md"
        skill.write_text(text, encoding="utf-8")
        assert (
            main(
                [
                    "record-stage",
                    "--run",
                    str(run.root),
                    "--stage",
                    "extract",
                    "--model",
                    "m",
                    "--effort",
                    "high",
                    "--skill",
                    str(skill),
                ]
            )
            == 0
        )
    assert stage_config(a) != stage_config(b)
    # comparability returns the reasons list directly (empty means comparable),
    # not an (ok, reasons) pair -- the brief's draft of this test unpacked it as
    # a 2-tuple, which raises ValueError against the real signature below.
    reasons = comparability(a, b)
    assert reasons
    assert any("skill_sha256" in reason for reason in reasons)


def test_an_unknown_stage_is_exit_2(tmp_path, capsys):
    run = _run(tmp_path)
    assert (
        main(
            [
                "record-stage",
                "--run",
                str(run.root),
                "--stage",
                "extraction",
                "--model",
                "m",
                "--effort",
                "high",
                "--skill",
                str(_skill(tmp_path)),
            ]
        )
        == 2
    )


def test_a_missing_skill_file_is_exit_2(tmp_path, capsys):
    run = _run(tmp_path)
    assert (
        main(
            [
                "record-stage",
                "--run",
                str(run.root),
                "--stage",
                "extract",
                "--model",
                "m",
                "--effort",
                "high",
                "--skill",
                str(tmp_path / "nope.md"),
            ]
        )
        == 2
    )
    assert capsys.readouterr().err.startswith("error: ")


def test_an_unknown_effort_is_exit_2(tmp_path):
    """argparse's choices come from the schema, so this cannot drift from it."""
    run = _run(tmp_path)
    assert (
        main(
            [
                "record-stage",
                "--run",
                str(run.root),
                "--stage",
                "extract",
                "--model",
                "m",
                "--effort",
                "extreme",
                "--skill",
                str(_skill(tmp_path)),
            ]
        )
        == 2
    )


def test_the_effort_choices_are_read_from_the_schema():
    """Not a second copy of the enum. If the schema gains an effort level, the
    CLI accepts it with no code change -- and if someone adds one to the CLI
    only, the manifest fails layer 1 and this test fails first.
    """
    assert manifest_stage_efforts() == ("low", "medium", "high", "xhigh", "max")


def test_decide_appends_a_timestamped_line(tmp_path):
    run = _run(tmp_path)
    assert (
        main(
            ["decide", "--run", str(run.root), "--note", "round 1: continue, 2 of 4 cells covered"]
        )
        == 0
    )
    text = run.decisions.read_text(encoding="utf-8")
    assert re.fullmatch(
        r"- \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z round 1: continue, 2 of 4 cells covered\n",
        text,
    ), text


def test_decide_appends_rather_than_rewriting(tmp_path):
    """The notebook is append-only: it is the record of what the orchestrator
    decided, and a rewrite would erase the reason a run went the way it did.
    """
    run = _run(tmp_path)
    for note in ("round 1: continue", "round 2: converged"):
        assert main(["decide", "--run", str(run.root), "--note", note]) == 0
    lines = run.decisions.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0].endswith("round 1: continue")
    assert lines[1].endswith("round 2: converged")


def test_decide_on_a_missing_run_directory_is_exit_2(tmp_path):
    assert main(["decide", "--run", str(tmp_path / "nope"), "--note", "x"]) == 2


def test_decide_refuses_an_empty_note(tmp_path, capsys):
    """A blank entry in the notebook is worse than no entry: it records that a
    decision was made and not what it was.
    """
    run = _run(tmp_path)
    assert main(["decide", "--run", str(run.root), "--note", "   "]) == 2
    assert capsys.readouterr().err.startswith("error: ")
    assert not run.decisions.exists()


# -- one scope narrower: the same mistake at a finer grain -----------------


def test_a_stages_map_that_is_not_an_object_is_exit_2_not_exit_1(tmp_path, capsys):
    """A corrupt manifest.stages (a list, say) is a harness pointed at
    something it cannot act on, not a repairable stage defect. Without the
    isinstance guard in record_stage, `dict(raw_stages or {})` either raises a
    bare TypeError -- uncaught by record-stage's own (UsageError, OSError)
    handler, so it falls through to cli.py's catch-all and becomes exit 1 with
    a manufactured "internal" finding instead of exit 2 -- or, for an empty
    list, silently discards the corruption and writes on top of it.
    """
    run = _run(tmp_path, stages=["not", "a", "mapping"])
    assert (
        main(
            [
                "record-stage",
                "--run",
                str(run.root),
                "--stage",
                "extract",
                "--model",
                "m",
                "--effort",
                "high",
                "--skill",
                str(_skill(tmp_path)),
            ]
        )
        == 2
    )
    assert capsys.readouterr().err.startswith("error: ")
    # Untouched: a usage error must not have written a repaired-looking
    # manifest over the corrupt one.
    assert read_json(run.manifest)["stages"] == ["not", "a", "mapping"]


def test_recording_over_a_malformed_sibling_entry_leaves_it_untouched(tmp_path):
    """record_stage merges by replacing the *entry* for its own stage, not by
    reading into an existing one -- so a sibling entry that is itself
    malformed (not an object) must not stop a different stage's recording,
    and must survive unchanged rather than being "fixed" or dropped.
    """
    run = _run(tmp_path, stages={"reconcile": "not-an-object"})
    assert (
        main(
            [
                "record-stage",
                "--run",
                str(run.root),
                "--stage",
                "extract",
                "--model",
                "m",
                "--effort",
                "high",
                "--skill",
                str(_skill(tmp_path)),
            ]
        )
        == 0
    )
    stages = read_json(run.manifest)["stages"]
    assert stages["reconcile"] == "not-an-object"
    assert stages["extract"]["model"] == "m"


def test_decide_refuses_a_note_with_an_embedded_newline(tmp_path, capsys):
    """decisions.md is one entry per physical line (test_decide_appends_a_
    timestamped_line's re.fullmatch and this module's own tests both parse it
    that way). append_decision only strips a *trailing* newline
    (test_append_decision_creates_then_appends in test_artifacts.py), so an
    embedded one would split the entry across two lines, the second of which
    has no leading "- <timestamp>" -- corrupting the append-only format for
    every reader downstream, not just this one entry.
    """
    run = _run(tmp_path)
    assert (
        main(
            [
                "decide",
                "--run",
                str(run.root),
                "--note",
                "round 1: continue\nsecretly something else",
            ]
        )
        == 2
    )
    assert capsys.readouterr().err.startswith("error: ")
    assert not run.decisions.exists()
