"""What survey does with a symlinked file inside, or named as, a corpus seed.

rglob does not descend into a symlinked folder, but `is_file()` follows a
symlinked *file*, so before this a link in the corpus pointing at a secret
elsewhere on the machine was read, hashed and catalogued as evidence. The rule
these tests hold: a link whose target is outside its root is never opened and
is recorded in `excluded`; a link to a file inside the root is kept; a named
file that is itself a link is catalogued as its target.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from rubrica import refs, survey, validate
from rubrica.artifacts import read_json

NOW = datetime(2026, 11, 16, 9, 0, 0, tzinfo=UTC)
SECRET = "SECRET-TOKEN-must-not-be-catalogued"

pytestmark = pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlinks here")


def _reasons(excluded):
    return {entry["path"]: entry["reason"] for entry in excluded}


def _layout(tmp_path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "id_rsa").write_text(f"{SECRET}\n", encoding="utf-8")
    root = tmp_path / "corpus"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "spec.md").write_text("# Spec\n\nThe tools.\n", encoding="utf-8")
    return root, outside


def test_a_link_to_a_file_outside_the_root_is_declined_not_read(tmp_path):
    root, outside = _layout(tmp_path)
    (root / "docs" / "key.md").symlink_to(outside / "id_rsa")
    kept, excluded = survey.walk_corpus([root])
    assert [p.relative_to(root).as_posix() for p in kept] == ["docs/spec.md"]
    assert _reasons(excluded)["docs/key.md"] == "symlink_outside_root"


def test_a_relative_dotdot_link_out_of_the_root_is_declined(tmp_path):
    root, _ = _layout(tmp_path)
    (root / "up.md").symlink_to(os.path.join("..", "elsewhere", "id_rsa"))
    _, excluded = survey.walk_corpus([root])
    assert _reasons(excluded)["up.md"] == "symlink_outside_root"


def test_a_link_into_a_sibling_root_is_still_outside_its_own(tmp_path):
    root, outside = _layout(tmp_path)
    (root / "key.md").symlink_to(outside / "id_rsa")
    _, excluded = survey.walk_corpus([root, outside])
    assert _reasons(excluded)["key.md"] == "symlink_outside_root"


def test_a_link_to_a_file_inside_the_root_is_kept(tmp_path):
    root, _ = _layout(tmp_path)
    (root / "readme.md").write_text("# Readme\n", encoding="utf-8")
    (root / "docs" / "alias.md").symlink_to(root / "readme.md")
    # Byte-identical to readme.md, so the later path is a duplicate; that is
    # the ordinary rule, and it shows the link was read rather than declined.
    kept, excluded = survey.walk_corpus([root])
    paths = sorted(p.relative_to(root).as_posix() for p in kept)
    assert "symlink_outside_root" not in _reasons(excluded).values()
    assert paths == ["docs/alias.md", "docs/spec.md"]
    assert _reasons(excluded)["readme.md"] == "duplicate"


def test_a_link_inside_the_root_into_its_vcs_folder_is_vcs_metadata(tmp_path):
    root, _ = _layout(tmp_path)
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text(f"[remote]\n{SECRET}\n", encoding="utf-8")
    (root / "notes.md").symlink_to(root / ".git" / "config")
    kept, excluded = survey.walk_corpus([root])
    assert root / "notes.md" not in kept
    assert _reasons(excluded)["notes.md"] == "vcs_metadata"


def test_the_root_itself_reached_through_a_link_keeps_inside_links(tmp_path):
    root, _ = _layout(tmp_path)
    (root / "alias.md").symlink_to(root / "docs" / "spec.md")
    linked_root = tmp_path / "linked"
    linked_root.symlink_to(root, target_is_directory=True)
    _, excluded = survey.walk_corpus([linked_root])
    assert "symlink_outside_root" not in _reasons(excluded).values()


def test_the_secret_never_reaches_the_catalogue(tmp_path):
    root, outside = _layout(tmp_path)
    (root / "docs" / "key.md").symlink_to(outside / "id_rsa")
    run = survey.survey(
        corpus_roots=[root],
        runs_dir=tmp_path / "runs",
        target_name="toy",
        target_interface="mcp",
        objective="breadth",
        max_rounds=2,
        max_scenarios=128,
        now=NOW,
    )
    text = run.catalogue.read_text(encoding="utf-8")
    assert SECRET not in text
    catalogue = read_json(run.catalogue)
    assert _reasons(catalogue["excluded"])["docs/key.md"] == "symlink_outside_root"
    assert validate.validate_stage(run, "survey") == []
    assert refs.check_catalogue(run) == []


def test_a_named_seed_that_is_a_link_is_catalogued_as_its_target(tmp_path):
    root, outside = _layout(tmp_path)
    (outside / "real.md").write_text("# Real\n\nTarget prose.\n", encoding="utf-8")
    (root / "named.md").symlink_to(outside / "real.md")
    run = survey.survey(
        corpus_roots=[root / "named.md"],
        runs_dir=tmp_path / "runs",
        target_name="toy",
        target_interface="mcp",
        objective="breadth",
        max_rounds=2,
        max_scenarios=128,
        now=NOW,
    )
    catalogue = read_json(run.catalogue)
    roots = catalogue["request"]["corpus_roots"]
    corpus = [c for c in catalogue["candidates"] if c["origin"] == "corpus"]
    assert [(roots[c["root_index"]], c["path"]) for c in corpus] == [
        (str(outside.resolve()), "real.md")
    ]
    assert validate.validate_stage(run, "survey") == []


# The lockfile, `--exclude` and `.gitignore` checks once looked only at the
# link's own name, so a link was a way to smuggle a declined file's contents
# into the catalogue under an innocent name. Each test below also surveys for
# real and reads the catalogue text, so "excluded" means "never read into it".


def _survey(tmp_path, root, **kwargs):
    return survey.survey(
        corpus_roots=[root],
        runs_dir=tmp_path / "runs",
        target_name="toy",
        target_interface="mcp",
        objective="breadth",
        max_rounds=2,
        max_scenarios=128,
        now=NOW,
        **kwargs,
    )


def _catalogued_paths(run):
    return {c["path"] for c in read_json(run.catalogue)["candidates"] if c["origin"] == "corpus"}


def test_a_link_to_a_gitignored_file_is_gitignored(tmp_path):
    root, _ = _layout(tmp_path)
    (root / ".gitignore").write_text(".env\n", encoding="utf-8")
    (root / ".env").write_text(f"API_KEY={SECRET}\n", encoding="utf-8")
    (root / "notes.md").symlink_to(root / ".env")
    kept, excluded = survey.walk_corpus([root])
    assert root / "notes.md" not in kept
    assert _reasons(excluded)["notes.md"] == "gitignored"
    assert _reasons(excluded)[".env"] == "gitignored"
    run = _survey(tmp_path, root)
    assert SECRET not in run.catalogue.read_text(encoding="utf-8")
    assert "notes.md" not in _catalogued_paths(run)


def test_a_link_to_an_operator_excluded_file_is_operator_excluded(tmp_path):
    root, _ = _layout(tmp_path)
    (root / "real.md").write_text(f"# Real\n\n{SECRET}\n", encoding="utf-8")
    (root / "alias.txt").symlink_to(root / "real.md")
    kept, excluded = survey.walk_corpus([root], operator_globs=["real.md"])
    assert root / "alias.txt" not in kept
    assert _reasons(excluded)["alias.txt"] == "operator_excluded"
    assert _reasons(excluded)["real.md"] == "operator_excluded"


def test_a_link_to_a_lockfile_is_a_lockfile(tmp_path):
    root, _ = _layout(tmp_path)
    (root / "package-lock.json").write_text(f'{{"token": "{SECRET}"}}\n', encoding="utf-8")
    (root / "deps.json").symlink_to(root / "package-lock.json")
    kept, excluded = survey.walk_corpus([root])
    assert root / "deps.json" not in kept
    assert _reasons(excluded)["deps.json"] == "lockfile"
    run = _survey(tmp_path, root)
    assert SECRET not in run.catalogue.read_text(encoding="utf-8")
    assert "deps.json" not in _catalogued_paths(run)


def test_a_link_to_an_ordinary_file_survives_the_name_checks(tmp_path):
    root, _ = _layout(tmp_path)
    (root / ".gitignore").write_text(".env\n", encoding="utf-8")
    # The target sorts after the link, so the link is the path that claims
    # the bytes and the target is the `duplicate` -- the link is kept.
    (root / "zz-real.md").write_text("# Real\n", encoding="utf-8")
    (root / "guide.md").symlink_to(root / "zz-real.md")
    kept, excluded = survey.walk_corpus([root], operator_globs=["*.lock"])
    assert root / "guide.md" in kept
    assert "guide.md" not in _reasons(excluded)


# A link whose target is missing, or one that points back at itself, makes
# is_file() return False with no error on 3.13, so before this such a link was
# in neither `kept` nor `excluded` -- left out, against the rule that
# `excluded` records every path the survey chose not to catalogue.
def test_a_dangling_link_is_recorded_as_outside_the_root(tmp_path):
    root, _ = _layout(tmp_path)
    (root / "docs" / "gone.md").symlink_to(tmp_path / "nowhere" / "gone.md")
    kept, excluded = survey.walk_corpus([root])
    assert [p.relative_to(root).as_posix() for p in kept] == ["docs/spec.md"]
    assert _reasons(excluded) == {"docs/gone.md": "symlink_outside_root"}


def test_a_self_looping_link_is_recorded_as_outside_the_root(tmp_path):
    root, _ = _layout(tmp_path)
    (root / "docs" / "loop.md").symlink_to("loop.md")
    kept, excluded = survey.walk_corpus([root])
    assert [p.relative_to(root).as_posix() for p in kept] == ["docs/spec.md"]
    assert _reasons(excluded) == {"docs/loop.md": "symlink_outside_root"}


def test_a_link_to_a_folder_is_still_neither_entered_nor_recorded(tmp_path):
    # Today's behaviour, kept on purpose: a symlinked folder is not descended
    # into and is not recorded, whether its target is inside the root or not.
    root, outside = _layout(tmp_path)
    (root / "inner").symlink_to(root / "docs", target_is_directory=True)
    (root / "outer").symlink_to(outside, target_is_directory=True)
    kept, excluded = survey.walk_corpus([root])
    assert [p.relative_to(root).as_posix() for p in kept] == ["docs/spec.md"]
    assert excluded == []
