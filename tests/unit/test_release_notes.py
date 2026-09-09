"""Tests for scripts/lib/release-tag.sh and scripts/lib/release-notes.sh.

Both are sourced-only bash, so each case runs a `bash -c 'source ...; ...'`
snippet against a throwaway git repository. No network, no `gh`.

Ported from the harness's shell suite rather than transplanted as shell: see the
Phase 3 note in the implementation plan. The short version is that a separate
`make test-scripts` target would be a fourth gate on a project whose
documentation names exactly three.
"""

import itertools
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
NOTES_LIB = REPO_ROOT / "scripts" / "lib" / "release-notes.sh"
TAG_LIB = REPO_ROOT / "scripts" / "lib" / "release-tag.sh"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _bash(repo: Path, lib: Path, snippet: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", f"source {lib}\n{textwrap.dedent(snippet)}"],
        cwd=repo,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.name", "Test Author")
    _git(r, "config", "user.email", "test@example.com")
    return r


# A process-wide counter rather than a count of the files in the worktree: the
# merge case commits on two branches, and a worktree-derived name repeats across
# them -- both sides write f1.txt -- which git reports as an add/add conflict and
# the merge then fails instead of exercising --no-merges.
_FILE_SEQ = itertools.count()


def _commit(repo: Path, subject: str, body: str = "") -> None:
    (repo / f"f{next(_FILE_SEQ)}.txt").write_text(subject)
    _git(repo, "add", "-A")
    msg = subject if not body else f"{subject}\n\n{body}"
    _git(repo, "commit", "-q", "-m", msg)


# --- release-tag.sh ---------------------------------------------------------


@pytest.mark.parametrize(
    "tag,expected",
    [
        ("v1.2.3", 0),
        ("refs/tags/v1.2.3", 0),
        ("v0.3.0-rc1", 1),  # a pre-release is not a release
        ("v1.2", 1),
        ("1.2.3", 1),
        ("v1.2.3.4", 1),
    ],
)
def test_release_tag_is_accepts_only_exact_release_tags(repo, tag, expected):
    result = _bash(repo, TAG_LIB, f'release_tag_is "{tag}"')
    assert result.returncode == expected


def test_release_tag_latest_picks_the_highest_and_ignores_pre_releases(repo):
    _commit(repo, "chore: base")
    for tag in ("v0.1.0", "v0.9.0", "v0.10.0", "v0.11.0-rc1"):
        _git(repo, "tag", tag)
    result = _bash(repo, TAG_LIB, "release_tag_latest")
    # sort -V, so v0.10.0 outranks v0.9.0 -- a lexical sort would get this wrong.
    assert result.stdout.strip() == "v0.10.0"


def test_release_tag_latest_is_empty_and_succeeds_with_no_tags(repo):
    _commit(repo, "chore: base")
    result = _bash(repo, TAG_LIB, 'set -e; latest=$(release_tag_latest); echo "[$latest]"')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


# --- release-notes.sh -------------------------------------------------------


def test_notes_group_by_type_in_declared_order(repo):
    _commit(repo, "chore: base")
    _commit(repo, "fix(digest): bound a name")
    _commit(repo, "feat(brief): add a block")
    _commit(repo, "docs: explain the gate")
    out = _bash(repo, NOTES_LIB, 'generate_release_notes "HEAD~3..HEAD"').stdout
    assert out.index("### Features") < out.index("### Fixes") < out.index("### Documentation")
    assert "- **brief:** add a block" in out
    assert "- **digest:** bound a name" in out
    assert "- explain the gate" in out


def test_an_empty_range_produces_nothing(repo):
    """The only notes case whose assertion is purely negative, so the only one
    that needs the exit code checked as well.

    A bash failure -- a renamed function, an unsourceable library, a typo in the
    snippet -- also produces empty stdout, so `out.strip() == ""` alone is
    satisfied by the function not existing. Measured: renaming
    `generate_release_notes` in the library left this case green without the
    returncode assertion and reddens it with one. Every other case in this
    module asserts some substring is *present* in stdout, which no failure mode
    can satisfy, so none of them needs the same guard.
    """
    _commit(repo, "chore: base")
    result = _bash(repo, NOTES_LIB, 'generate_release_notes "HEAD..HEAD"')
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_a_range_starting_at_a_tag_excludes_the_tagged_commit(repo):
    _commit(repo, "feat: before the tag")
    _git(repo, "tag", "v0.1.0")
    _commit(repo, "feat: after the tag")
    out = _bash(repo, NOTES_LIB, 'generate_release_notes "v0.1.0..HEAD"').stdout
    assert "after the tag" in out
    assert "before the tag" not in out


def test_a_merge_commits_own_subject_is_excluded_but_its_content_is_not(repo):
    """--no-merges. This repository's history is merge-based, so this case is the
    one that decides whether generated notes are usable here at all."""
    _commit(repo, "chore: base")
    _git(repo, "checkout", "-q", "-b", "side")
    _commit(repo, "feat(side): brought in by the merge")
    _git(repo, "checkout", "-q", "main")
    _commit(repo, "fix(main): on the trunk")
    _git(repo, "merge", "--no-ff", "-q", "--no-gpg-sign", "-m", "Merge the side branch", "side")
    # HEAD~2 is the base commit: the first-parent chain is base -> fix(main) ->
    # the merge, so HEAD~3 does not exist in this topology. Assert the merge
    # commit really is inside the range before asserting it is absent from the
    # notes -- otherwise the case below would pass on a range that never held it.
    in_range = _git(repo, "log", "--format=%s", "HEAD~2..HEAD")
    assert "Merge the side branch" in in_range
    out = _bash(repo, NOTES_LIB, 'generate_release_notes "HEAD~2..HEAD"').stdout
    assert "brought in by the merge" in out
    assert "on the trunk" in out
    assert "Merge the side branch" not in out


def test_unparseable_subjects_fall_under_other(repo):
    _commit(repo, "chore: base")
    _commit(repo, "just some words")
    out = _bash(repo, NOTES_LIB, 'generate_release_notes "HEAD~1..HEAD"').stdout
    assert "### Other" in out
    assert "- just some words" in out


def test_a_bang_in_the_subject_declares_a_breaking_change(repo):
    _commit(repo, "chore: base")
    _commit(repo, "feat(api)!: rename the flag")
    out = _bash(repo, NOTES_LIB, 'generate_release_notes "HEAD~1..HEAD"').stdout
    assert out.index("### Breaking changes") < out.index("### Features")
    assert "- **api:** rename the flag" in out
    # Breaking commits still appear under their own type: the section adds
    # emphasis without removing anything.
    assert out.count("rename the flag") == 2


def test_a_breaking_change_footer_wins_over_the_subject(repo):
    """The footer says what the reader must *do*; the subject only says what
    changed. Both spellings of the token are accepted."""
    _commit(repo, "chore: base")
    _commit(
        repo,
        "feat(cli): change the default",
        body="BREAKING CHANGE: pass --explicit to keep the\nold behaviour.",
    )
    out = _bash(repo, NOTES_LIB, 'generate_release_notes "HEAD~1..HEAD"').stdout
    assert "### Breaking changes" in out
    # Folded onto one line, and the footer's prose is used, not the subject's.
    assert "- **cli:** pass --explicit to keep the old behaviour." in out


def test_trailers_below_the_footer_do_not_leak_into_the_notes(repo):
    """Collection stops at the first blank line, so Signed-off-by and
    Co-Authored-By never reach a bullet."""
    _commit(repo, "chore: base")
    _commit(
        repo,
        "feat(cli): change the default",
        body="BREAKING CHANGE: pass --explicit.\n\nSigned-off-by: Test Author <test@example.com>",
    )
    out = _bash(repo, NOTES_LIB, 'generate_release_notes "HEAD~1..HEAD"').stdout
    assert "Signed-off-by" not in out
    assert "- **cli:** pass --explicit." in out
