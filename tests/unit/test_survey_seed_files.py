"""`survey --corpus` naming a single file, not only a folder.

A human seeding a run points at the files that matter, some of them loose. The
rule these tests hold: a named file is catalogued as named -- whatever the walk
would have dropped it for by *where* it sits -- and every file still has to be
something a candidate can be, with a decline recorded when it is not.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rubrica import intake, survey, validate
from rubrica.artifacts import read_json
from rubrica.errors import UsageError

NOW = datetime(2026, 11, 10, 9, 0, 0, tzinfo=UTC)


def _survey(tmp_path, seeds, **over):
    kwargs = dict(
        corpus_roots=seeds,
        runs_dir=tmp_path / "runs",
        target_name="toy",
        target_interface="mcp",
        objective="breadth",
        max_rounds=2,
        max_scenarios=128,
        now=NOW,
    )
    kwargs.update(over)
    return survey.survey(**kwargs)


def _tree(tmp_path):
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "docs" / "spec.md").write_text("# Spec\n\nThe tools.\n", encoding="utf-8")
    (root / "docs" / "notes.md").write_text("# Notes\n\nMore prose.\n", encoding="utf-8")
    (root / "docs" / "unwanted.md").write_text("# Unwanted\n", encoding="utf-8")
    (root / "src" / "tools.py").write_text("TOOLS = {}\n", encoding="utf-8")
    return root


def _paths(catalogue):
    roots = catalogue["request"]["corpus_roots"]
    return sorted(
        f"{roots[c['root_index']]}/{c['path']}"
        for c in catalogue["candidates"]
        if c["origin"] == "corpus"
    )


def test_a_named_file_is_the_only_candidate_from_its_folder(tmp_path):
    root = _tree(tmp_path)
    run = _survey(tmp_path, [root / "docs" / "spec.md"])
    catalogue = read_json(run.catalogue)
    assert validate.validate_stage(run, "survey") == []
    assert _paths(catalogue) == [f"{root / 'docs'}/spec.md"]
    assert catalogue["request"]["corpus_roots"] == [str(root / "docs")]
    assert catalogue["request"]["seed_files"] == [str(root / "docs" / "spec.md")]


def test_two_named_siblings_share_one_root(tmp_path):
    root = _tree(tmp_path)
    run = _survey(tmp_path, [root / "docs" / "spec.md", root / "docs" / "notes.md"])
    catalogue = read_json(run.catalogue)
    assert catalogue["request"]["corpus_roots"] == [str(root / "docs")]
    assert {c["root_index"] for c in catalogue["candidates"]} == {0}
    assert sorted(c["path"] for c in catalogue["candidates"]) == ["notes.md", "spec.md"]


def test_a_file_and_a_folder_in_one_survey(tmp_path):
    root = _tree(tmp_path)
    run = _survey(tmp_path, [root / "src", root / "docs" / "spec.md"])
    catalogue = read_json(run.catalogue)
    assert catalogue["request"]["corpus_roots"] == [str(root / "src"), str(root / "docs")]
    assert _paths(catalogue) == sorted([f"{root / 'src'}/tools.py", f"{root / 'docs'}/spec.md"])


def test_a_named_file_also_inside_a_named_folder_is_one_candidate(tmp_path):
    root = _tree(tmp_path)
    run = _survey(tmp_path, [root / "docs", root / "docs" / "spec.md"])
    catalogue = read_json(run.catalogue)
    assert sum(c["path"] == "spec.md" for c in catalogue["candidates"]) == 1
    assert {"path": "spec.md", "reason": "duplicate"} in catalogue["excluded"]


def test_a_named_file_skips_the_filters_on_where_it_sits(tmp_path):
    """The human pointed at it: neither --exclude nor .gitignore takes it away."""
    root = _tree(tmp_path)
    (root / "docs" / ".gitignore").write_text("spec.md\n", encoding="utf-8")
    run = _survey(tmp_path, [root / "docs" / "spec.md"], operator_globs=["*.md"])
    catalogue = read_json(run.catalogue)
    assert [c["path"] for c in catalogue["candidates"]] == ["spec.md"]
    assert catalogue["excluded"] == []


def test_a_named_file_that_cannot_be_a_candidate_is_declined_visibly(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "spec.md").write_text("# Spec\n", encoding="utf-8")
    (root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    run = _survey(tmp_path, [root / "spec.md", root / "logo.png", root / "uv.lock"])
    catalogue = read_json(run.catalogue)
    assert [c["path"] for c in catalogue["candidates"]] == ["spec.md"]
    reasons = {e["path"]: e["reason"] for e in catalogue["excluded"]}
    assert reasons == {"logo.png": "binary", "uv.lock": "lockfile"}


def test_a_missing_path_is_a_usage_error_and_mints_no_run(tmp_path):
    with pytest.raises(UsageError, match="neither a file nor a directory"):
        _survey(tmp_path, [tmp_path / "nope.md"])
    assert not (tmp_path / "runs").exists()


def test_an_unreadable_named_file_is_a_usage_error_naming_it(tmp_path):
    """Inside a walked folder an unreadable file is one declined candidate; a file
    the human named and the harness cannot open is the harness misconfigured."""
    root = _tree(tmp_path)
    locked = root / "docs" / "spec.md"
    locked.chmod(0o000)
    try:
        with pytest.raises(UsageError, match="cannot read corpus file: .*spec.md"):
            _survey(tmp_path, [locked])
    finally:
        locked.chmod(0o644)
    assert not (tmp_path / "runs").exists()


def test_intake_admits_a_named_file_from_its_own_folder(tmp_path):
    """The reader that joins roots[root_index] / path needs no change."""
    root = _tree(tmp_path)
    run = _survey(tmp_path, [root / "src", root / "docs" / "spec.md"])
    catalogue = read_json(run.catalogue)
    spec = next(c for c in catalogue["candidates"] if c["path"] == "spec.md")
    source_root = catalogue["request"]["corpus_roots"][spec["root_index"]]
    run.inputs_dir.mkdir(parents=True)
    entry = intake.materialise(
        run, candidate=spec, source_root=source_root, artifact_id=spec["candidate_id"]
    )
    stored = (run.inputs_dir / entry["stored_as"]).read_bytes()
    assert stored == (root / "docs" / "spec.md").read_bytes()


def test_relative_seeds_are_recorded_absolute_and_intake_runs_from_elsewhere(tmp_path, monkeypatch):
    """A relative folder and a bare file name, surveyed from one folder, admitted
    from another. Before the fix the bare name's root was recorded as `.`, which
    intake joined onto its own cwd -- here a folder holding a decoy of the same
    name, so the wrong bytes would have been admitted rather than an error."""
    root = _tree(tmp_path)
    monkeypatch.chdir(root / "docs")
    run = _survey(tmp_path, [Path("../src"), Path("spec.md")])
    catalogue = read_json(run.catalogue)
    request = catalogue["request"]
    assert all(Path(r).is_absolute() for r in request["corpus_roots"])
    assert request["seed_files"]
    assert all(Path(s).is_absolute() for s in request["seed_files"])

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "spec.md").write_text("# Decoy\n", encoding="utf-8")
    monkeypatch.chdir(elsewhere)
    run.inputs_dir.mkdir(parents=True)
    for name, source in (
        ("spec.md", root / "docs" / "spec.md"),
        ("tools.py", root / "src" / "tools.py"),
    ):
        cand = next(c for c in catalogue["candidates"] if c["path"] == name)
        entry = intake.materialise(
            run,
            candidate=cand,
            source_root=request["corpus_roots"][cand["root_index"]],
            artifact_id=cand["candidate_id"],
        )
        assert (run.inputs_dir / entry["stored_as"]).read_bytes() == source.read_bytes()


def test_the_cli_takes_a_file_for_corpus(tmp_path, capsys):
    from rubrica import cli

    root = _tree(tmp_path)
    code = cli.main(
        [
            "survey",
            "--corpus",
            str(root / "docs" / "spec.md"),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--target-name",
            "toy",
            "--target-interface",
            "mcp",
            "--objective",
            "breadth",
        ]
    )
    assert code == 0
    run_dir = Path(capsys.readouterr().out.strip())
    catalogue = json.loads((run_dir / "00-catalogue.json").read_text(encoding="utf-8"))
    assert [c["path"] for c in catalogue["candidates"]] == ["spec.md"]


def _repo_with_vcs(tmp_path, name=".git"):
    root = _tree(tmp_path)
    vcs = root / name
    (vcs / "hooks").mkdir(parents=True)
    (vcs / "config").write_text('[remote "origin"]\n\turl = x\n', encoding="utf-8")
    (vcs / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    return root, vcs


@pytest.mark.parametrize("name", [".git", ".hg", ".svn", ".GIT", ".Hg"])
def test_a_vcs_folder_seed_is_a_usage_error_and_mints_no_run(tmp_path, name):
    """`--corpus repo/.git` catalogued `config` and `HEAD` as evidence: the walk
    filters only the parts *below* a root, so the root itself slipped past."""
    _, vcs = _repo_with_vcs(tmp_path, name)
    with pytest.raises(UsageError, match="version-control folder"):
        _survey(tmp_path, [vcs])
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("name", [".git", ".GIT"])
def test_a_named_file_inside_a_vcs_folder_is_a_usage_error(tmp_path, name):
    """A named file skips the walk's where-it-sits filters, so the seed check
    is the only thing between `.git/config` and the catalogue."""
    _, vcs = _repo_with_vcs(tmp_path, name)
    with pytest.raises(UsageError, match="version-control folder"):
        _survey(tmp_path, [vcs / "config"])
    with pytest.raises(UsageError, match="version-control folder"):
        _survey(tmp_path, [vcs / "hooks"])
    assert not (tmp_path / "runs").exists()


def test_a_symlink_into_a_vcs_folder_is_refused(tmp_path):
    """The spelled path names no VCS folder; the resolved one does."""
    _, vcs = _repo_with_vcs(tmp_path)
    link = tmp_path / "innocent"
    link.symlink_to(vcs, target_is_directory=True)
    with pytest.raises(UsageError, match="version-control folder"):
        _survey(tmp_path, [link])
    with pytest.raises(UsageError, match="version-control folder"):
        _survey(tmp_path, [link / "config"])


def test_a_folder_holding_a_vcs_folder_is_still_walked(tmp_path):
    """Only a seed that *is* or sits inside one is refused; a repo root is the
    ordinary case, and its VCS folder is dropped as `vcs_metadata`."""
    root, _ = _repo_with_vcs(tmp_path)
    run = _survey(tmp_path, [root])
    catalogue = read_json(run.catalogue)
    assert not any(".git" in c["path"] for c in catalogue["candidates"])
    reasons = {e["path"]: e["reason"] for e in catalogue["excluded"]}
    assert reasons[".git/config"] == "vcs_metadata"


def test_the_walk_drops_a_vcs_folder_whatever_its_case(tmp_path):
    """`.GIT` is the `.git` folder on a case-insensitive volume; an exact-case
    match let its contents into the catalogue."""
    root, _ = _repo_with_vcs(tmp_path, ".GIT")
    run = _survey(tmp_path, [root])
    catalogue = read_json(run.catalogue)
    assert not any(c["path"].startswith(".GIT/") for c in catalogue["candidates"])
    reasons = {e["path"]: e["reason"] for e in catalogue["excluded"]}
    assert reasons[".GIT/config"] == "vcs_metadata"
    assert reasons[".GIT/HEAD"] == "vcs_metadata"


def test_the_cli_exits_2_on_a_vcs_folder_seed(tmp_path, capsys):
    from rubrica import cli

    _, vcs = _repo_with_vcs(tmp_path)
    code = cli.main(
        [
            "survey",
            "--corpus",
            str(vcs),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--target-name",
            "toy",
            "--target-interface",
            "mcp",
            "--objective",
            "breadth",
        ]
    )
    assert code == 2
    assert capsys.readouterr().out == ""
    assert not (tmp_path / "runs").exists()


def _cli_survey(corpus, runs):
    from rubrica import cli

    return cli.main(
        [
            "survey",
            "--corpus",
            corpus,
            "--runs-dir",
            str(runs),
            "--target-name",
            "toy",
            "--target-interface",
            "mcp",
            "--objective",
            "breadth",
        ]
    )


# Path("") is Path("."), so a blank --corpus (an unset $CORPUS in a caller's
# script) used to catalogue whatever folder the caller ran from and exit 0.
# The cwd here is a real tree, so the old behaviour would mint a run.
@pytest.mark.parametrize("blank", ["", "  ", "\t"])
def test_a_blank_corpus_is_a_usage_error_and_mints_no_run(tmp_path, capsys, monkeypatch, blank):
    root = _tree(tmp_path)
    monkeypatch.chdir(root)
    runs = tmp_path / "runs"
    assert _cli_survey(blank, runs) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--corpus" in captured.err
    assert not runs.exists()


def test_a_blank_corpus_beside_a_real_one_is_still_refused(tmp_path, capsys, monkeypatch):
    from rubrica import cli

    root = _tree(tmp_path)
    monkeypatch.chdir(root)
    runs = tmp_path / "runs"
    code = cli.main(
        [
            "survey",
            "--corpus",
            str(root),
            "--corpus",
            "",
            "--runs-dir",
            str(runs),
            "--target-name",
            "toy",
            "--target-interface",
            "mcp",
            "--objective",
            "breadth",
        ]
    )
    assert code == 2
    assert capsys.readouterr().out == ""
    assert not runs.exists()


def test_a_dot_corpus_still_walks_the_current_folder(tmp_path, capsys, monkeypatch):
    root = _tree(tmp_path)
    monkeypatch.chdir(root)
    assert _cli_survey(".", tmp_path / "runs") == 0
    run_dir = Path(capsys.readouterr().out.strip())
    catalogue = json.loads((run_dir / "00-catalogue.json").read_text(encoding="utf-8"))
    assert catalogue["candidates"]


# Path("") is Path("."), so a blank --runs-dir (an unset $RUNS in a caller's
# script) used to mint `run-<ts>/` in whatever folder the caller ran from and
# exit 0 -- often the corpus itself, where a later survey catalogues the run.
@pytest.mark.parametrize("blank", ["", "  "])
def test_a_blank_runs_dir_on_survey_is_a_usage_error_and_mints_no_run(
    tmp_path, capsys, monkeypatch, blank
):
    root = _tree(tmp_path)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    assert _cli_survey(str(root), blank) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--runs-dir" in captured.err
    assert list(cwd.iterdir()) == []


@pytest.mark.parametrize("blank", ["", "  "])
def test_a_blank_runs_dir_on_intake_is_a_usage_error_and_mints_no_run(
    tmp_path, capsys, monkeypatch, blank
):
    from rubrica import cli

    spec = tmp_path / "spec.md"
    spec.write_text("# Spec\n\nThe tools.\n", encoding="utf-8")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    code = cli.main(
        [
            "intake",
            "--input",
            str(spec),
            "--runs-dir",
            blank,
            "--target-name",
            "toy",
            "--target-interface",
            "mcp",
        ]
    )
    assert code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--runs-dir" in captured.err
    assert list(cwd.iterdir()) == []


# The same Path("") hazard one flag over: a blank --run made the current folder
# the run, and run-summary and target-brief wrote their pages into it.
@pytest.mark.parametrize("command", ["run-summary", "target-brief"])
@pytest.mark.parametrize("blank", ["", "  "])
def test_a_blank_run_is_a_usage_error_and_writes_nothing(
    tmp_path, capsys, monkeypatch, command, blank
):
    from rubrica import cli

    monkeypatch.chdir(tmp_path)
    assert cli.main([command, "--run", blank]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--run" in captured.err
    assert list(tmp_path.iterdir()) == []
