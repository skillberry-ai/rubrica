"""Tests for scripts/check-dco.sh.

The script is shell, so it is driven as a subprocess against throwaway git
repositories rather than imported. That is the idiom test_dispatch_harness.py
already uses for scripts/dispatch-stage.sh, and it is deliberate: the harness
this was transplanted from keeps its script tests in shell behind a separate
`make test-scripts` target, which here would be a fourth gate on a project whose
documentation names exactly three. A gate nobody is obliged to run stops running
silently.

Commits are made with `-c commit.gpgsign=false` so the suite never depends on a
developer's signing key or an unlocked agent -- the script checks the DCO
trailer, which is `-s`, and has nothing to say about `-S`.
"""

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-dco.sh"

AUTHOR = "Test Author"
EMAIL = "test.author@example.com"


def _git(repo: Path, *args: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=kw.pop("check", True),
        **kw,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo with one signed-off commit on `main`."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.name", AUTHOR)
    _git(r, "config", "user.email", EMAIL)
    (r / "README.md").write_text("base\n")
    _git(r, "add", "README.md")
    _git(r, "commit", "-q", "-m", f"chore: base\n\nSigned-off-by: {AUTHOR} <{EMAIL}>")
    return r


def _commit(repo: Path, subject: str, *, signoff: str | None = None, author: str | None = None):
    """Add a commit. `signoff` is the full trailer value, or None for none."""
    path = repo / f"f{subject.replace(' ', '_').replace(':', '')}.txt"
    path.write_text(subject)
    _git(repo, "add", str(path.name))
    msg = subject if signoff is None else f"{subject}\n\nSigned-off-by: {signoff}"
    args = ["commit", "-q", "-m", msg]
    if author:
        args += [f"--author={author}"]
    _git(repo, *args)


def _check(repo: Path, base: str = "main", head: str = "HEAD"):
    return subprocess.run([str(SCRIPT), base, head], cwd=repo, capture_output=True, text=True)


def test_a_signed_off_commit_passes(repo):
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "feat: one", signoff=f"{AUTHOR} <{EMAIL}>")
    result = _check(repo)
    assert result.returncode == 0, result.stderr


def test_a_commit_with_no_trailer_fails_and_names_it(repo):
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "feat: unsigned", signoff=None)
    result = _check(repo)
    assert result.returncode == 1
    assert "no Signed-off-by trailer" in result.stderr
    assert "feat: unsigned" in result.stderr


def test_a_trailer_naming_someone_else_fails(repo):
    """A sign-off naming a non-author certifies nothing about the author."""
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "feat: mismatched", signoff="Someone Else <someone@example.com>")
    result = _check(repo)
    assert result.returncode == 1
    assert "does not match the author" in result.stderr


def test_the_match_ignores_case_and_surrounding_whitespace(repo):
    """Contributors are not failed over capitalisation."""
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "feat: casing", signoff=f"  {AUTHOR.upper()}   <{EMAIL.upper()}>")
    result = _check(repo)
    assert result.returncode == 0, result.stderr


def test_a_merge_commit_is_exempt(repo):
    """A merge commit contributes no authored patch, so it certifies nothing."""
    _git(repo, "checkout", "-q", "-b", "side")
    _commit(repo, "feat: on side", signoff=f"{AUTHOR} <{EMAIL}>")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "feat: on feature", signoff=f"{AUTHOR} <{EMAIL}>")
    _git(repo, "merge", "--no-ff", "-q", "--no-gpg-sign", "-m", "Merge side", "side")
    result = _check(repo)
    assert result.returncode == 0, result.stderr


def test_a_bot_commit_is_exempt_and_reported_as_such(repo):
    """A bot cannot make the certification the DCO describes."""
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(
        repo,
        "chore(deps): bump",
        signoff=None,
        author="dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
    )
    result = _check(repo)
    assert result.returncode == 0, result.stderr
    assert "exempt" in result.stdout


def test_commits_already_on_the_base_branch_are_not_checked(repo):
    """Merge-base scoping: an advanced base must not drag its commits in."""
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, "feat: mine", signoff=f"{AUTHOR} <{EMAIL}>")
    _git(repo, "checkout", "-q", "main")
    _commit(repo, "feat: theirs unsigned", signoff=None)
    _git(repo, "checkout", "-q", "feature")
    result = _check(repo)
    assert result.returncode == 0, (
        "an unsigned commit on the advanced base branch was wrongly attributed "
        f"to this branch: {result.stderr}"
    )


def test_wrong_argument_count_is_a_usage_error(repo):
    result = subprocess.run([str(SCRIPT), "main"], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 2
    assert "Usage:" in result.stderr


def test_an_unresolvable_base_ref_is_reported_not_ignored(repo):
    result = _check(repo, base="no/such/ref")
    assert result.returncode == 1
    assert "cannot resolve base ref" in result.stderr
    assert "fetch-depth" in result.stderr
