"""What survey drops, and whether it says so.

Spec §2's third constraint -- declining must stay visible -- applies to the
mechanical excluder, not only to the skill. A file that vanishes from a
catalogue with no reason recorded is indistinguishable from one that was never
there, which is the confusion that made four parsec gaps unreadable.
"""

from __future__ import annotations

import json

import pytest

from rubrica import survey
from rubrica.errors import UsageError


def _corpus(tmp_path):
    root = tmp_path / "corpus"
    (root / "src").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "node_modules" / "left-pad").mkdir(parents=True)
    (root / "README.md").write_text("# Target\n\nProse.\n", encoding="utf-8")
    (root / "src" / "tools.py").write_text("TOOLS = {}\n", encoding="utf-8")
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (root / "node_modules" / "left-pad" / "index.js").write_text("x\n", encoding="utf-8")
    (root / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3}), encoding="utf-8")
    (root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")
    (root / ".gitignore").write_text("secrets.txt\n", encoding="utf-8")
    (root / "secrets.txt").write_text("hunter2\n", encoding="utf-8")
    (root / "copy-of-readme.md").write_text("# Target\n\nProse.\n", encoding="utf-8")
    return root


def _reasons(excluded):
    return {entry["path"]: entry["reason"] for entry in excluded}


def test_every_exclusion_class_fires_and_names_itself(tmp_path):
    root = _corpus(tmp_path)
    kept, excluded = survey.walk_corpus([root])
    reasons = _reasons(excluded)
    assert reasons[".git/HEAD"] == "vcs_metadata"
    assert reasons["node_modules/left-pad/index.js"] == "vendored"
    assert reasons["package-lock.json"] == "lockfile"
    assert reasons["logo.png"] == "binary"
    assert reasons["secrets.txt"] == "gitignored"
    # Byte-identical to README.md, which sorts first, so the copy is the dupe.
    assert reasons["copy-of-readme.md"] == "duplicate"


def test_what_survives_is_only_the_real_evidence(tmp_path):
    root = _corpus(tmp_path)
    kept, _ = survey.walk_corpus([root])
    assert [p.relative_to(root).as_posix() for p in kept] == [
        ".gitignore",
        "README.md",
        "src/tools.py",
    ]


def test_operator_globs_are_recorded_not_silent(tmp_path):
    """An --exclude the operator passed is still a decline, and still visible."""
    root = _corpus(tmp_path)
    _, excluded = survey.walk_corpus([root], operator_globs=["src/*.py"])
    assert _reasons(excluded)["src/tools.py"] == "operator_excluded"


def test_no_file_is_excluded_for_being_large(tmp_path):
    """Spec §2: shape was the binding constraint, never size.

    A 3MB source file is the shape tool_definitions.py had, and it was the
    parsec run's most cited input.
    """
    root = tmp_path / "corpus"
    root.mkdir()
    big = root / "tool_definitions.py"
    big.write_text("TOOLS = [\n" + '    {"name": "t"},\n' * 60000 + "]\n", encoding="utf-8")
    kept, excluded = survey.walk_corpus([root])
    assert kept == [big]
    assert excluded == []


def test_an_unreadable_root_raises_rather_than_reporting_an_empty_corpus(tmp_path):
    """The narrow case this module's own comment already named but did not yet
    hold: `Path.rglob` swallows a PermissionError raised while listing the
    *root* itself, so an EACCES root used to return `kept=[]` silently instead
    of raising -- reporting an unreadable corpus as an empty one, exactly the
    hazard `list_dir`'s docstring documents for `Path.glob`. Task 7's own
    `test_an_unreadable_corpus_root_is_exit_two_material` exercises this
    through `survey.survey`; this is the same defect pinned directly against
    `walk_corpus`, one level down.
    """
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "fine.md").write_text("# Fine\n", encoding="utf-8")
    root.chmod(0o000)
    try:
        with pytest.raises(UsageError, match="cannot read corpus root"):
            survey.walk_corpus([root])
    finally:
        root.chmod(0o755)


def test_an_unreadable_file_is_recorded_rather_than_raised(tmp_path):
    """A corpus is a user tree; one bad mode must not abort the inventory.

    This is the narrow case: the *file* is unreadable, which is a candidate
    problem. An unreadable corpus *root* is a misconfigured harness and is
    UsageError -- see test_survey_cli.py.
    """
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "fine.md").write_text("# Fine\n", encoding="utf-8")
    bad = root / "locked.md"
    bad.write_text("# Locked\n", encoding="utf-8")
    bad.chmod(0o000)
    try:
        kept, excluded = survey.walk_corpus([root])
        assert kept == [root / "fine.md"]
        assert _reasons(excluded)["locked.md"] == "unreadable"
    finally:
        bad.chmod(0o644)
