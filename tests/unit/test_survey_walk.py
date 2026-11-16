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


def test_a_shared_seen_dict_dedupes_across_two_separate_calls(tmp_path):
    """The fix for the per-root loop's own dedup gap, one level down from
    survey.survey: two *separate* walk_corpus calls, sharing one `seen` dict
    passed in by the caller, must dedupe against each other exactly as if
    they were one call over both roots. This is what lets survey() call
    walk_corpus once per root (for root_index) without losing cross-root
    duplicate detection.
    """
    root0 = tmp_path / "root0"
    root0.mkdir()
    root1 = tmp_path / "root1"
    root1.mkdir()
    (root0 / "a.md").write_text("same bytes\n", encoding="utf-8")
    (root1 / "b.md").write_text("same bytes\n", encoding="utf-8")

    seen: dict[str, object] = {}
    kept0, excluded0 = survey.walk_corpus([root0], seen=seen)
    kept1, excluded1 = survey.walk_corpus([root1], seen=seen)

    # The earlier call's file survives; the later call's byte-identical file
    # is the one dropped, and it is dropped exactly once.
    assert kept0 == [root0 / "a.md"]
    assert kept1 == []
    assert excluded0 == []
    assert _reasons(excluded1)["b.md"] == "duplicate"


# The two commonest top-level .gitignore shapes after a bare name -- `/x` tied
# to the root and `x/` naming a folder -- once excluded nothing: `/.env` kept
# its slash and matched no path, and `secrets/` became `secrets` and matched
# only a *file* of that name. A bug scout's corpus with exactly those two
# lines catalogued a `.env` holding a secret and `secrets/key.txt`.


def _ignoring(tmp_path, ignore: str, files: list[str]):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / ".gitignore").write_text(ignore, encoding="utf-8")
    for i, rel in enumerate(files):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        # Distinct bytes per file, so no keep is a `duplicate` drop instead.
        path.write_text(f"file {i}: {rel}\n", encoding="utf-8")
    kept, excluded = survey.walk_corpus([root])
    return {p.relative_to(root).as_posix() for p in kept}, _reasons(excluded)


def test_an_anchored_pattern_drops_only_the_root_file(tmp_path):
    kept, reasons = _ignoring(tmp_path, "/.env\n", [".env", "sub/.env"])
    assert reasons[".env"] == "gitignored"
    assert "sub/.env" in kept
    assert "sub/.env" not in reasons


def test_an_anchored_wildcard_does_not_cross_a_folder(tmp_path):
    """fnmatch's `*` matches `/`, so a whole-path match would drop `sub/a.env`."""
    kept, reasons = _ignoring(tmp_path, "/*.env\n", ["a.env", "sub/a.env"])
    assert reasons["a.env"] == "gitignored"
    assert "sub/a.env" in kept


def test_a_folder_pattern_drops_every_file_under_that_folder_at_any_depth(tmp_path):
    kept, reasons = _ignoring(
        tmp_path, "secrets/\n", ["secrets/key.txt", "a/secrets/k.txt", "secrets.md"]
    )
    assert reasons["secrets/key.txt"] == "gitignored"
    assert reasons["a/secrets/k.txt"] == "gitignored"
    # A *file* whose name merely starts the same is not under the folder.
    assert "secrets.md" in kept


def test_a_folder_pattern_does_not_drop_a_file_of_that_name(tmp_path):
    """`x/` names a folder; git keeps a plain file called `x`, and so do we."""
    kept, reasons = _ignoring(tmp_path, "secrets/\n", ["secrets", "docs/secrets"])
    assert {"secrets", "docs/secrets"} <= kept


def test_an_anchored_folder_pattern_drops_only_the_root_folder(tmp_path):
    """The task's `/build/` example, renamed: `build` is a vendored folder name,
    so it is dropped as `vendored` at any depth before .gitignore is consulted,
    and the anchoring could not be observed through it."""
    kept, reasons = _ignoring(
        tmp_path, "/generated/\n", ["generated/x", "generated/deep/y", "src/generated/x"]
    )
    assert reasons["generated/x"] == "gitignored"
    assert reasons["generated/deep/y"] == "gitignored"
    assert "src/generated/x" in kept


def test_a_folder_pattern_with_an_inner_slash_is_anchored(tmp_path):
    kept, reasons = _ignoring(tmp_path, "out/gen/\n", ["out/gen/a.py", "pkg/out/gen/b.py"])
    assert reasons["out/gen/a.py"] == "gitignored"
    assert "pkg/out/gen/b.py" in kept


@pytest.mark.parametrize("line", ["/\n", "//\n", "  /  \n"])
def test_a_line_of_only_slashes_ignores_nothing(tmp_path, line):
    """An empty pattern must not turn into one that matches the whole corpus."""
    kept, reasons = _ignoring(tmp_path, line, ["a.md", "sub/b.md"])
    assert {"a.md", "sub/b.md"} <= kept
    assert "gitignored" not in reasons.values()


def test_plain_patterns_still_match_by_path_or_bare_name(tmp_path):
    kept, reasons = _ignoring(
        tmp_path, ".env\n*.log\n", [".env", "sub/.env", "x.log", "deep/y.log", "keep.md"]
    )
    for rel in (".env", "sub/.env", "x.log", "deep/y.log"):
        assert reasons[rel] == "gitignored"
    assert "keep.md" in kept


# The first cut of the shapes above compared any pattern with a `/` one folder
# level per segment, so `**` became a single `*` and `**/.env` stopped dropping
# a nested `a/b/.env`; and a line naming a folder without a trailing slash --
# `secrets`, `/creds` -- excluded nothing inside it, where git ignores the
# whole folder (`git check-ignore -v secrets/key.txt` -> `.gitignore:1:secrets`).


def test_a_leading_double_star_matches_at_any_depth(tmp_path):
    kept, reasons = _ignoring(tmp_path, "**/.env\n", [".env", "a/.env", "a/b/.env", "a/b/k.md"])
    for rel in (".env", "a/.env", "a/b/.env"):
        assert reasons[rel] == "gitignored"
    assert "a/b/k.md" in kept


def test_a_trailing_double_star_drops_everything_inside_at_any_depth(tmp_path):
    kept, reasons = _ignoring(
        tmp_path, "logs/**\n", ["logs/top.txt", "logs/x/y/z.txt", "src/logs/a.txt"]
    )
    assert reasons["logs/top.txt"] == "gitignored"
    assert reasons["logs/x/y/z.txt"] == "gitignored"
    # As in git: `logs/**` names what is inside `logs`, not a file called it,
    # and the inner `/` anchors it to the root.
    assert "src/logs/a.txt" in kept
    assert not survey._gitignored("logs", ["logs/**"])


def test_an_inner_double_star_matches_zero_or_more_folders(tmp_path):
    kept, reasons = _ignoring(tmp_path, "a/**/b\n", ["a/b/f", "a/x/y/b/f", "a/x/y/c/f", "z/a/b/f"])
    assert reasons["a/b/f"] == "gitignored"
    assert reasons["a/x/y/b/f"] == "gitignored"
    assert {"a/x/y/c/f", "z/a/b/f"} <= kept


def test_a_plain_name_drops_a_folder_of_that_name_at_any_depth(tmp_path):
    kept, reasons = _ignoring(
        tmp_path, "secrets\n", ["secrets/key.txt", "a/secrets/k.txt", "secretsx/k.txt"]
    )
    assert reasons["secrets/key.txt"] == "gitignored"
    assert reasons["a/secrets/k.txt"] == "gitignored"
    assert "secretsx/k.txt" in kept


def test_an_anchored_name_drops_only_the_root_folder_of_that_name(tmp_path):
    kept, reasons = _ignoring(tmp_path, "/creds\n", ["creds/t.txt", "sub/creds/t.txt"])
    assert reasons["creds/t.txt"] == "gitignored"
    assert "sub/creds/t.txt" in kept
    assert "sub/creds/t.txt" not in reasons


def test_a_plain_wildcard_does_not_cross_a_folder(tmp_path):
    """fnmatch's `*` matches `/`: over the whole path `a*b` would drop `a/x/b`."""
    kept, reasons = _ignoring(tmp_path, "a*b\n", ["axb", "a/x/b"])
    assert reasons["axb"] == "gitignored"
    assert "a/x/b" in kept


def test_many_double_stars_on_a_deep_path_stay_fast():
    """A hostile .gitignore line must not make matching blow up with depth."""
    import time

    pattern = "/".join(["**"] * 30) + "/nomatch"
    path = "/".join(f"d{i}" for i in range(60)) + "/f"
    started = time.monotonic()
    assert not survey._gitignored(path, [pattern])
    assert time.monotonic() - started < 2.0
