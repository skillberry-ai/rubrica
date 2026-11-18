"""What survey drops, and whether it says so.

Spec §2's third constraint -- declining must stay visible -- applies to the
mechanical excluder, not only to the skill. A file that vanishes from a
catalogue with no reason recorded is indistinguishable from one that was never
there, which is the confusion that made four parsec gaps unreadable.
"""

from __future__ import annotations

import json
import os

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


_AS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0


@pytest.mark.skipif(_AS_ROOT, reason="chmod 000 does not stop root from listing a folder")
def test_an_unreadable_subfolder_is_recorded_and_its_siblings_kept(tmp_path):
    """rglob skipped a folder it could not list without a word, so every file
    inside was in neither list -- measured as ([a.md], []) on this exact tree.
    The folder cannot name its files, so the folder itself is what is recorded.
    """
    root = tmp_path / "corpus"
    locked = root / "locked"
    locked.mkdir(parents=True)
    (root / "a.md").write_text("# A\n", encoding="utf-8")
    (root / "z.md").write_text("# Z\n", encoding="utf-8")
    (locked / "spec.md").write_text("# Spec\n", encoding="utf-8")
    locked.chmod(0o000)
    try:
        kept, excluded = survey.walk_corpus([root])
    finally:
        locked.chmod(0o755)
    assert kept == [root / "a.md", root / "z.md"]
    assert _reasons(excluded) == {"locked": "unreadable"}


@pytest.mark.skipif(_AS_ROOT, reason="chmod 000 does not stop root from listing a folder")
def test_an_unreadable_folder_two_levels_down_is_recorded_too(tmp_path):
    root = tmp_path / "corpus"
    locked = root / "docs" / "inner" / "locked"
    locked.mkdir(parents=True)
    (root / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (root / "docs" / "inner" / "note.md").write_text("# Note\n", encoding="utf-8")
    (locked / "spec.md").write_text("# Spec\n", encoding="utf-8")
    locked.chmod(0o000)
    try:
        kept, excluded = survey.walk_corpus([root])
    finally:
        locked.chmod(0o755)
    assert kept == [root / "docs" / "guide.md", root / "docs" / "inner" / "note.md"]
    assert _reasons(excluded) == {"docs/inner/locked": "unreadable"}


def _walk_with_half_locked(root, half, **kwargs):
    half.chmod(0o644)
    try:
        return survey.walk_corpus([root], **kwargs)
    finally:
        half.chmod(0o755)


@pytest.mark.skipif(_AS_ROOT, reason="chmod 644 does not stop root from entering a folder")
def test_a_listable_but_unenterable_subfolder_is_recorded_and_its_siblings_kept(tmp_path):
    """A `chmod 644` folder can be listed, so the walk's on_error never fired,
    but is_file() on its entries raised PermissionError and the whole survey
    aborted as "cannot read corpus root" -- measured on `c/half/spec.md`.
    """
    root = tmp_path / "corpus"
    half = root / "half"
    (half / "deeper").mkdir(parents=True)
    (root / "a.md").write_text("# A\n", encoding="utf-8")
    (half / "spec.md").write_text("# Spec\n", encoding="utf-8")
    (half / "deeper" / "more.md").write_text("# More\n", encoding="utf-8")
    kept, excluded = _walk_with_half_locked(root, half)
    assert kept == [root / "a.md"]
    assert _reasons(excluded) == {"half": "unreadable"}


@pytest.mark.skipif(_AS_ROOT, reason="chmod 644 does not stop root from entering a folder")
def test_a_listable_but_unenterable_gitignored_folder_keeps_the_gitignored_reason(tmp_path):
    root = tmp_path / "corpus"
    half = root / "secret"
    half.mkdir(parents=True)
    (root / ".gitignore").write_text("secret/\n", encoding="utf-8")
    (root / "a.md").write_text("# A\n", encoding="utf-8")
    (half / "k.md").write_text("# K\n", encoding="utf-8")
    kept, excluded = _walk_with_half_locked(root, half)
    assert root / "a.md" in kept
    assert _reasons(excluded)["secret"] == "gitignored"  # pragma: allowlist secret


@pytest.mark.skipif(_AS_ROOT, reason="chmod 644 does not stop root from entering a folder")
def test_a_listable_but_unenterable_root_still_raises(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "a.md").write_text("# A\n", encoding="utf-8")
    root.chmod(0o644)
    try:
        with pytest.raises(UsageError, match="cannot read corpus root"):
            survey.walk_corpus([root])
    finally:
        root.chmod(0o755)


def _locked_outside_target(tmp_path):
    """A file outside the corpus inside a `chmod 000` folder, so stat-ing it
    through a symlink raises PermissionError while the link itself lstats fine."""
    outside = tmp_path / "outside" / "locked"
    outside.mkdir(parents=True)
    (outside / "secret").write_text("hunter2\n", encoding="utf-8")
    return outside, outside / "secret"


@pytest.mark.skipif(_AS_ROOT, reason="chmod 000 does not stop root from reading a target")
def test_a_symlink_to_an_unreadable_target_is_a_symlink_decline_not_a_locked_folder(tmp_path):
    """is_file() follows a link, so a link into a locked place raised for the
    link alone and its whole folder was recorded `unreadable` -- measured on
    this tree as kept [docs/a.md], excluded {docs: unreadable}, with
    docs/sub/b.md in neither list and the link never recorded at all.
    """
    root = tmp_path / "corpus"
    (root / "docs" / "sub").mkdir(parents=True)
    (root / "docs" / "a.md").write_text("# A\n", encoding="utf-8")
    (root / "docs" / "sub" / "b.md").write_text("# B\n", encoding="utf-8")
    locked, secret = _locked_outside_target(tmp_path)
    (root / "docs" / "link.md").symlink_to(secret)
    locked.chmod(0o000)
    try:
        kept, excluded = survey.walk_corpus([root])
    finally:
        locked.chmod(0o755)
    assert kept == [root / "docs" / "a.md", root / "docs" / "sub" / "b.md"]
    assert _reasons(excluded) == {"docs/link.md": "symlink_outside_root"}


@pytest.mark.skipif(_AS_ROOT, reason="chmod 000 does not stop root from reading a target")
def test_a_symlink_to_an_unreadable_target_in_the_root_does_not_abort_the_survey(tmp_path):
    """The same link directly in the root escaped as "cannot read corpus root"."""
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "a.md").write_text("# A\n", encoding="utf-8")
    locked, secret = _locked_outside_target(tmp_path)
    (root / "link.md").symlink_to(secret)
    locked.chmod(0o000)
    try:
        kept, excluded = survey.walk_corpus([root])
    finally:
        locked.chmod(0o755)
    assert kept == [root / "a.md"]
    assert _reasons(excluded) == {"link.md": "symlink_outside_root"}


def _walk_with_locked(root, locked, **kwargs):
    locked.chmod(0o000)
    try:
        return survey.walk_corpus([root], **kwargs)
    finally:
        locked.chmod(0o755)


@pytest.mark.skipif(_AS_ROOT, reason="chmod 000 does not stop root from listing a folder")
def test_a_locked_gitignored_folder_keeps_the_gitignored_reason(tmp_path):
    """Readable, `secret/k.md` is `gitignored`; locked, the folder used to read
    `unreadable`, so a mode bit changed what the tally meant. The folder-only
    pattern `secret/` must match the folder's own path.
    """
    root = tmp_path / "corpus"
    locked = root / "secret"
    locked.mkdir(parents=True)
    (root / ".gitignore").write_text("secret/\n", encoding="utf-8")
    (root / "a.md").write_text("# A\n", encoding="utf-8")
    (locked / "k.md").write_text("# K\n", encoding="utf-8")
    _, readable = survey.walk_corpus([root])
    assert _reasons(readable)["secret/k.md"] == "gitignored"
    _, excluded = _walk_with_locked(root, locked)
    assert _reasons(excluded)["secret"] == "gitignored"  # pragma: allowlist secret


@pytest.mark.skipif(_AS_ROOT, reason="chmod 000 does not stop root from listing a folder")
def test_a_locked_folder_under_an_operator_glob_keeps_the_operator_reason(tmp_path):
    root = tmp_path / "corpus"
    locked = root / "private"
    locked.mkdir(parents=True)
    (root / "a.md").write_text("# A\n", encoding="utf-8")
    (locked / "k.md").write_text("# K\n", encoding="utf-8")
    _, readable = survey.walk_corpus([root], operator_globs=["private/*"])
    assert _reasons(readable) == {"private/k.md": "operator_excluded"}
    _, excluded = _walk_with_locked(root, locked, operator_globs=["private/*"])
    assert _reasons(excluded) == {"private": "operator_excluded"}


@pytest.mark.skipif(_AS_ROOT, reason="chmod 000 does not stop root from listing a folder")
def test_a_locked_folder_under_a_double_star_glob_keeps_the_operator_reason(tmp_path):
    root = tmp_path / "corpus"
    locked = root / "skip"
    locked.mkdir(parents=True)
    (root / "a.md").write_text("# A\n", encoding="utf-8")
    (locked / "k.md").write_text("# K\n", encoding="utf-8")
    _, readable = survey.walk_corpus([root], operator_globs=["skip/**"])
    assert _reasons(readable) == {"skip/k.md": "operator_excluded"}
    _, excluded = _walk_with_locked(root, locked, operator_globs=["skip/**"])
    assert _reasons(excluded) == {"skip": "operator_excluded"}


@pytest.mark.skipif(_AS_ROOT, reason="chmod 000 does not stop root from listing a folder")
def test_a_plain_locked_folder_is_still_unreadable(tmp_path):
    root = tmp_path / "corpus"
    locked = root / "locked"
    locked.mkdir(parents=True)
    (root / "a.md").write_text("# A\n", encoding="utf-8")
    (locked / "k.md").write_text("# K\n", encoding="utf-8")
    _, excluded = _walk_with_locked(root, locked)
    assert _reasons(excluded) == {"locked": "unreadable"}


@pytest.mark.skipif(_AS_ROOT, reason="chmod 000 does not stop root from listing a folder")
def test_a_locked_folder_a_glob_may_not_fully_cover_stays_unreadable(tmp_path):
    """`private/*.md` cannot be shown to cover every file in a folder nobody
    can list, and an unrelated ignore line must not reach it either.
    """
    root = tmp_path / "corpus"
    locked = root / "private"
    locked.mkdir(parents=True)
    (root / ".gitignore").write_text("other/\n", encoding="utf-8")
    (locked / "k.md").write_text("# K\n", encoding="utf-8")
    _, excluded = _walk_with_locked(root, locked, operator_globs=["private/*.md"])
    assert _reasons(excluded) == {"private": "unreadable"}


@pytest.mark.skipif(_AS_ROOT, reason="chmod 000 does not stop root from listing a folder")
@pytest.mark.parametrize("line", ["data/*", "data/**", "data/**/*"])
def test_a_locked_folder_under_a_trailing_star_ignore_line_keeps_the_gitignored_reason(
    tmp_path, line
):
    """`data/*`, `data/**` and `data/**/*` match only the files inside
    `data`, never the folder's own path, so a locked `data` used to read
    `unreadable` while a readable one gave every file `gitignored` -- measured
    on this tree.
    """
    root = tmp_path / "corpus"
    locked = root / "data"
    locked.mkdir(parents=True)
    (root / ".gitignore").write_text(f"{line}\n", encoding="utf-8")
    (root / "a.md").write_text("# A\n", encoding="utf-8")
    (locked / "k.md").write_text("# K\n", encoding="utf-8")
    _, readable = survey.walk_corpus([root])
    assert _reasons(readable) == {"data/k.md": "gitignored"}
    _, excluded = _walk_with_locked(root, locked)
    assert _reasons(excluded) == {"data": "gitignored"}


@pytest.mark.skipif(_AS_ROOT, reason="chmod 000 does not stop root from listing a folder")
@pytest.mark.parametrize("line", ["data/*.md", "data/*/"])
def test_a_locked_folder_an_ignore_line_may_not_fully_cover_stays_unreadable(tmp_path, line):
    """`data/*.md` covers only some files, and `data/*/` skips the files
    directly inside `data`, so neither may claim a folder nobody can list.
    """
    root = tmp_path / "corpus"
    locked = root / "data"
    locked.mkdir(parents=True)
    (root / ".gitignore").write_text(f"{line}\n", encoding="utf-8")
    (locked / "k.md").write_text("# K\n", encoding="utf-8")
    _, excluded = _walk_with_locked(root, locked)
    assert _reasons(excluded) == {"data": "unreadable"}


def test_a_trailing_star_line_reaches_a_folder_only_in_folder_mode():
    """The folder-mode rule must not leak into file checks: a file called
    `logs` is not matched by `logs/**`, `logs/*` or `logs/**/*`.
    """
    assert survey._gitignored("logs", ["logs/**"], folder=True)
    assert survey._gitignored("logs", ["logs/*"], folder=True)
    assert survey._gitignored("logs", ["logs/**/*"], folder=True)
    assert not survey._gitignored("logs", ["logs/**/*"])
    assert survey._gitignored("logs/k.md", ["logs/**/*"])
    assert not survey._gitignored("logs", ["logs/*/*"], folder=True)
    assert survey._gitignored("a/logs", ["logs/**"], folder=True) is False
    assert not survey._gitignored("logs", ["logs/*"])
    assert not survey._gitignored("logs", ["logs/**", "!logs/**"], folder=True)


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


# `!` lines were once skipped while the broad line they narrow still applied,
# so the common "ignore everything, keep a few" file dropped exactly what git
# keeps: a bug scout's corpus with the five lines below came out empty, every
# file `gitignored`, where `git check-ignore` keeps three of the four.


def test_an_ignore_everything_keep_a_few_file_keeps_what_git_keeps(tmp_path):
    ignore = "*\n!*/\n!*.py\n!*.md\n!.gitignore\n"
    kept, reasons = _ignoring(tmp_path, ignore, ["docs/api.md", "src/app.py", "build.log"])
    assert {".gitignore", "docs/api.md", "src/app.py"} <= kept
    assert reasons["build.log"] == "gitignored"


def test_a_negated_file_inside_an_ignored_folder_glob_is_kept(tmp_path):
    kept, reasons = _ignoring(tmp_path, "docs/*\n!docs/api.md\n", ["docs/api.md", "docs/other.md"])
    assert "docs/api.md" in kept
    assert reasons["docs/other.md"] == "gitignored"


def test_a_later_plain_line_overrides_an_earlier_negation(tmp_path):
    """Last match wins: `!x` before `x` re-includes nothing."""
    kept, reasons = _ignoring(tmp_path, "!x\nx\n", ["x", "y"])
    assert reasons["x"] == "gitignored"
    assert "y" in kept


# A .gitignore saved with a UTF-8 byte-order mark (Windows Notepad, some
# editors) once kept the mark on its first pattern, `﻿.env`, which matched
# nothing: a bug scout's corpus catalogued `.env` while `git status --ignored`
# showed it ignored. Git drops one leading mark, and so must we.


def test_a_byte_order_mark_does_not_hide_the_first_gitignore_line(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / ".gitignore").write_bytes(b"\xef\xbb\xbf.env\nsecrets/\n")
    (root / ".env").write_text("TOKEN=placeholder\n", encoding="utf-8")
    (root / "secrets").mkdir()
    (root / "secrets" / "key.txt").write_text("k\n", encoding="utf-8")
    (root / "README.md").write_text("# Target\n", encoding="utf-8")
    assert survey._gitignore_patterns(root) == [".env", "secrets/"]
    kept, excluded = survey.walk_corpus([root])
    reasons = _reasons(excluded)
    assert reasons[".env"] == "gitignored"
    assert reasons["secrets/key.txt"] == "gitignored"
    assert "README.md" in {p.relative_to(root).as_posix() for p in kept}


def test_a_gitignore_without_a_byte_order_mark_reads_the_same(tmp_path):
    kept, reasons = _ignoring(tmp_path, ".env\nsecrets/\n", [".env", "secrets/k.txt", "a.md"])
    assert reasons[".env"] == "gitignored"
    assert reasons["secrets/k.txt"] == "gitignored"
    assert "a.md" in kept


def test_only_one_leading_byte_order_mark_is_dropped(tmp_path):
    """Git strips one mark at the start of the file, not one inside a line."""
    root = tmp_path / "corpus"
    root.mkdir()
    (root / ".gitignore").write_bytes(b"\xef\xbb\xbf.env\n\xef\xbb\xbfx\n")
    assert survey._gitignore_patterns(root) == [".env", "﻿x"]


def _walk_or_fail(roots, fifo, **kwargs):
    """walk_corpus in a thread with a join timeout, so a hang fails the test.

    A blocked open() on a FIFO would otherwise hang the whole suite. On a
    timeout the FIFO gets a writer, which unblocks the stuck read so the daemon
    thread can finish, and the test fails naming the hang.
    """
    import threading

    result: dict = {}

    def walk() -> None:
        # Kept rather than lost in the thread, so a refusal reaches the test.
        try:
            result["value"] = survey.walk_corpus(roots, **kwargs)
        except Exception as exc:
            result["error"] = exc

    worker = threading.Thread(target=walk, daemon=True)
    worker.start()
    worker.join(timeout=10)
    if worker.is_alive():
        fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
        os.close(fd)
        pytest.fail(f"walk_corpus hung opening the FIFO {fifo}")
    if "error" in result:
        raise result["error"]
    return result["value"]


# A FIFO at the root's .gitignore was read before any file was walked, and
# read_text() blocked until a writer appeared: `c/a.md` plus
# `mkfifo c/.gitignore` hung walk_corpus forever. It then counted as no
# patterns, which surveyed under rules nobody could read; it is now refused,
# still without ever opening the FIFO.
@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no mkfifo here")
def test_a_fifo_gitignore_is_refused_and_does_not_hang(tmp_path):
    root = tmp_path / "c"
    root.mkdir()
    (root / "a.md").write_text("# A\n", encoding="utf-8")
    os.mkfifo(root / ".gitignore")
    with pytest.raises(UsageError, match=r"\.gitignore is not a regular file"):
        _walk_or_fail([root], root / ".gitignore")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no mkfifo here")
def test_a_gitignore_linked_to_a_fifo_is_refused_and_does_not_hang(tmp_path):
    root = tmp_path / "c"
    root.mkdir()
    (root / "a.md").write_text("# A\n", encoding="utf-8")
    os.mkfifo(tmp_path / "pipe")
    (root / ".gitignore").symlink_to(tmp_path / "pipe")
    with pytest.raises(UsageError, match=r"\.gitignore is not a regular file"):
        _walk_or_fail([root], tmp_path / "pipe")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no mkfifo here")
def test_survey_over_a_fifo_gitignore_exits_2_without_hanging(tmp_path, capsys):
    import threading

    root = tmp_path / "c"
    root.mkdir()
    (root / "a.md").write_text("# A\n", encoding="utf-8")
    os.mkfifo(root / ".gitignore")
    runs = tmp_path / "runs"
    result: dict = {}
    worker = threading.Thread(
        target=lambda: result.setdefault("code", _survey_cli(root, runs)), daemon=True
    )
    worker.start()
    worker.join(timeout=10)
    if worker.is_alive():
        os.close(os.open(root / ".gitignore", os.O_WRONLY | os.O_NONBLOCK))
        pytest.fail("survey hung opening the FIFO .gitignore")
    assert result["code"] == 2
    assert ".gitignore" in capsys.readouterr().err
    assert not runs.exists() or list(runs.iterdir()) == []


def _survey_cli(root, runs):
    from rubrica import cli

    return cli.main(
        [
            "survey",
            "--corpus",
            str(root),
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


# One byte that is not UTF-8 anywhere in the .gitignore -- here a Latin-1 `é`
# in a comment -- made the strict decode fail, and the failure counted as no
# patterns: a bug scout's corpus catalogued `.env` and its key while
# `git check-ignore` ignored it. Git reads the file as bytes; so do we now.
def test_a_latin_1_comment_does_not_drop_the_other_gitignore_lines(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / ".gitignore").write_bytes(b"# caf\xe9 notes\n.env\n")
    (root / ".env").write_text("API_KEY=placeholder\n", encoding="utf-8")
    (root / "README.md").write_text("# Target\n", encoding="utf-8")
    assert ".env" in survey._gitignore_patterns(root)
    kept, excluded = survey.walk_corpus([root])
    assert _reasons(excluded)[".env"] == "gitignored"
    assert "README.md" in {p.relative_to(root).as_posix() for p in kept}


def test_a_bad_byte_inside_a_pattern_line_spares_the_lines_around_it(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / ".gitignore").write_bytes(b".env\nbad\xff.txt\nsecrets/\n")
    patterns = survey._gitignore_patterns(root)
    assert patterns[0] == ".env"
    assert patterns[-1] == "secrets/"


def test_a_missing_gitignore_is_still_no_patterns(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    assert survey._gitignore_patterns(root) == []


@pytest.mark.skipif(_AS_ROOT, reason="chmod 000 does not stop root from reading a file")
def test_an_unreadable_gitignore_is_refused_and_mints_no_run(tmp_path, capsys):
    """A `chmod 000 .gitignore` once counted as no patterns, so every file git
    ignores -- a `.env` included -- was catalogued with its contents. Unknown
    ignore rules are now a usage error, raised before the run folder exists."""
    root = tmp_path / "corpus"
    root.mkdir()
    ignore = root / ".gitignore"
    ignore.write_text(".env\n", encoding="utf-8")
    (root / ".env").write_text("API_KEY=placeholder\n", encoding="utf-8")
    (root / "README.md").write_text("# Target\n", encoding="utf-8")
    runs = tmp_path / "runs"
    ignore.chmod(0o000)
    try:
        with pytest.raises(UsageError, match=r"cannot read the corpus root's \.gitignore"):
            survey.walk_corpus([root])
        assert _survey_cli(root, runs) == 2
        assert str(ignore) in capsys.readouterr().err
        assert not runs.exists() or list(runs.iterdir()) == []
    finally:
        ignore.chmod(0o644)


# The `only` path (files named one by one) goes through the same check: a FIFO
# handed in directly is declined as unreadable, never opened.
@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no mkfifo here")
def test_a_fifo_passed_as_a_named_file_is_declined_without_opening_it(tmp_path):
    root = tmp_path / "c"
    root.mkdir()
    (root / "a.md").write_text("# A\n", encoding="utf-8")
    os.mkfifo(root / "pipe")
    kept, excluded = _walk_or_fail([root], root / "pipe", only=[root / "a.md", root / "pipe"])
    assert [p.relative_to(root).as_posix() for p in kept] == ["a.md"]
    assert _reasons(excluded) == {"pipe": "unreadable"}
