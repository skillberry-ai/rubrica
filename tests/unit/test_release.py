"""Tests for scripts/release.sh.

Builds a fixture repository with a local bare origin, copies the release scripts
into it, and drives release.sh there. Never touches a network remote and never
calls gh -- RELEASE_SKIP_GH=1 covers the release-page step.

release.sh passes -S and -s unconditionally, which forces signing regardless of
commit.gpgsign. The fixture gets its own throwaway SSH signing key so the suite
never depends on a developer's real key or on an unlocked ssh-agent.

Ported from the sibling project's shell suite for the reason recorded in
tests/unit/test_release_notes.py: a separate shell-test target would be a fourth
gate on a project whose documentation names exactly three.
"""

import itertools
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# The fixture cannot exist without a signing key, and every case drives a script
# that signs. Skipping the module is the honest outcome where ssh-keygen is
# absent; weakening the signing assertions would not be.
pytestmark = pytest.mark.skipif(
    shutil.which("ssh-keygen") is None,
    reason="ssh-keygen is needed to mint the fixture's throwaway signing key",
)

PYPROJECT = """\
[project]
name = "fixture"
version = "0.1.0"
requires-python = ">=3.13"
"""

# Eight lines below the header, not one, and the length is the point. The real
# CHANGELOG.md used to carry three paragraphs and a link definition here, and the
# insertion below re-emits every one of them *under* the newest release section --
# a one-line preamble made that displacement look like a rounding error instead of
# the whole shape of the file. Sections and a link definition too, so a positional
# assertion has something to be wrong about.
CHANGELOG_PREAMBLE = """Notable changes to the fixture, newest first. The format follows
Keep a Changelog, and this project follows Semantic Versioning --
currently `0.x`, so anything may change.

Sections below are generated at release time from Conventional Commit
subjects since the previous release tag.

[Unreleased]: https://example.invalid/compare/main...HEAD
"""
CHANGELOG = f"# Changelog\n\n{CHANGELOG_PREAMBLE}"

# The first line of the preamble, used wherever a case needs to say where the
# preamble ended up relative to the new section.
CHANGELOG_PREAMBLE_FIRST_LINE = CHANGELOG_PREAMBLE.splitlines()[0]

# The fixture sets every git setting release.sh depends on in the repository's own
# config, so the developer's global and system config must not reach it. This is
# not tidiness: a global `commit.gpgsign = true` would sign the release commit even
# if release.sh dropped its -S, and the signing case would then pass vacuously.
# Measured both ways -- see the comment on commit.gpgsign in the fixture.
_GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}

# The system directories only. Used to hide uv from the script without hiding bash,
# git, sed and awk with it -- an empty PATH would fail at the `/usr/bin/env bash`
# shebang and the case would measure nothing.
_SYSTEM_PATH = "/usr/bin:/bin"


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=check,
        env={**os.environ, **_GIT_ENV},
    )


def _origin(repo: Path) -> Path:
    """The bare repository the fixture pushes to."""
    return repo.parent / "origin.git"


def _tmpdir(repo: Path) -> Path:
    """Where release.sh's own tempfiles land, so a leak is observable."""
    return repo.parent / "tmp"


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    """A repo with pyproject.toml, CHANGELOG.md, the release scripts, and a bare origin."""
    key = tmp_path / "signing_key"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "release-test", "-f", str(key)],
        check=True,
        capture_output=True,
    )

    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", "-b", "main", str(origin)],
        check=True,
        capture_output=True,
        env={**os.environ, **_GIT_ENV},
    )
    (tmp_path / "tmp").mkdir()

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "Test Author")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "gpg.format", "ssh")
    _git(repo, "config", "user.signingkey", str(key) + ".pub")
    # Deliberately false, and load-bearing. release.sh passes -S and -s itself, so
    # leaving these on would sign the release commit and tag even with the script's
    # flags removed -- which is exactly the mutation the signing case has to catch.
    # Measured: with commit.gpgsign true and -S deleted from release.sh, that case
    # stays green; with it false, it goes red.
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "tag.gpgsign", "false")

    (repo / "pyproject.toml").write_text(PYPROJECT)
    (repo / "CHANGELOG.md").write_text(CHANGELOG)
    # Only the release scripts, not all of scripts/: the rest of the tree is
    # irrelevant here and copying it drags __pycache__ into the fixture's history.
    (repo / "scripts").mkdir()
    shutil.copytree(REPO_ROOT / "scripts" / "lib", repo / "scripts" / "lib")
    shutil.copy2(REPO_ROOT / "scripts" / "release.sh", repo / "scripts" / "release.sh")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "chore: base")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "-u", "origin", "main")
    return repo


def _release(repo: Path, *args: str, **env: str) -> subprocess.CompletedProcess:
    e = {
        **os.environ,
        **_GIT_ENV,
        "RELEASE_SKIP_GH": "1",
        # The fixture has no dependencies to resolve, so the re-lock stays hermetic.
        "UV_OFFLINE": "1",
        # Redirected so the tempfile case can see what the script left behind.
        "TMPDIR": str(_tmpdir(repo)),
        **env,
    }
    return subprocess.run(
        [str(repo / "scripts" / "release.sh"), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        env=e,
    )


def _both(result: subprocess.CompletedProcess) -> str:
    """stdout and stderr together, for asserting that a phrase appears on neither."""
    return result.stdout + result.stderr


# A process-wide counter rather than a count of the files in the worktree, which is
# the defect the sibling suite's port already had to fix: a worktree-derived name
# repeats after a `git reset --hard` rollback, and the second commit then re-writes
# the first one's file instead of adding a new one.
_FILE_SEQ = itertools.count()


def _commit(repo: Path, subject: str) -> None:
    """Commit and push.

    Pushing is not incidental. release.sh's preflight rejects a local main that
    differs from the remote, so a fixture commit left unpushed makes every case
    below die in preflight rather than exercise what it names.
    """
    (repo / f"f{next(_FILE_SEQ)}.txt").write_text(subject)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", subject)
    _git(repo, "push", "-q", "origin", "main")


def _version(repo: Path) -> str:
    for line in (repo / "pyproject.toml").read_text().splitlines():
        if line.startswith("version = "):
            return line.split('"')[1]
    raise AssertionError("no version in pyproject.toml")


# --- dry run ----------------------------------------------------------------


def test_dry_run_reports_and_changes_nothing(fixture_repo):
    _commit(fixture_repo, "feat(api): add an endpoint")
    before = _git(fixture_repo, "rev-parse", "HEAD").stdout
    result = _release(fixture_repo, "--dry-run", "0.2.0")
    assert result.returncode == 0, result.stderr
    # The plan and the generated notes, not just the exit code: a dry run that
    # printed nothing would satisfy returncode == 0 on its own.
    assert "v0.2.0" in result.stdout
    assert "0.1.0 -> 0.2.0" in result.stdout
    assert "- **api:** add an endpoint" in result.stdout
    assert "dry run" in result.stdout
    assert _version(fixture_repo) == "0.1.0"
    assert _git(fixture_repo, "rev-parse", "HEAD").stdout == before
    assert _git(fixture_repo, "tag", "-l").stdout.strip() == ""
    assert _git(fixture_repo, "status", "--porcelain", "-uno").stdout == ""


# --- preflight rejections ---------------------------------------------------


def test_a_dirty_worktree_is_rejected(fixture_repo):
    (fixture_repo / "pyproject.toml").write_text(PYPROJECT + "# scratch\n")
    result = _release(fixture_repo, "0.2.0")
    assert result.returncode != 0
    assert "uncommitted changes" in result.stderr


def test_a_non_main_branch_is_rejected(fixture_repo):
    _git(fixture_repo, "checkout", "-q", "-b", "feature")
    result = _release(fixture_repo, "0.2.0")
    assert result.returncode != 0
    assert "must be on main" in result.stderr


def test_a_bare_double_dash_with_no_version_is_rejected(fixture_repo):
    """`--` used to leave VERSION empty: usage printed here, but an empty version
    went through to the release step. The script has no `--` case on purpose, so it
    falls through to the unknown-option arm. The empty version is the failure that
    mattered, so assert on it directly as well as on the message.
    """
    result = _release(fixture_repo, "--")
    assert result.returncode != 0
    assert "unknown option: --" in result.stderr
    assert _version(fixture_repo) == "0.1.0", "an empty version reached the bump"
    assert _git(fixture_repo, "tag", "-l").stdout.strip() == ""


# --- first release ----------------------------------------------------------


def test_the_first_release_may_equal_the_current_version(fixture_repo):
    _commit(fixture_repo, "feat: something")
    result = _release(fixture_repo, "0.1.0")
    assert result.returncode == 0, result.stderr
    assert _git(fixture_repo, "tag", "-l").stdout.strip() == "v0.1.0"
    assert _git(fixture_repo, "log", "-1", "--format=%s").stdout.strip() == (
        "chore(release): v0.1.0"
    )
    # The tag and the release commit must reach the remote, or nothing was released.
    assert _git(_origin(fixture_repo), "tag", "-l").stdout.strip() == "v0.1.0"
    assert (
        _git(_origin(fixture_repo), "rev-parse", "main").stdout
        == _git(fixture_repo, "rev-parse", "HEAD").stdout
    )


@pytest.mark.parametrize(
    "starting_changelog",
    ["# Changelog\n", CHANGELOG],
    ids=["header-only", "header-and-prose"],
)
def test_the_changelog_gains_a_section_and_keeps_one_trailing_newline(
    fixture_repo, starting_changelog
):
    """Both starting shapes, because the trailing-newline normalisation is only
    observable in one of them.

    The generated section deliberately ends in a blank line so consecutive releases
    stay separated. Where the file already carries prose below the header, that prose
    ends the assembled file and hides the blank line; where the header is the whole
    file, the new section *is* the tail and the stray blank line is visible. Measured:
    with the normalisation replaced by a plain copy of CHANGELOG.md.new, the
    header-only parameter goes red and the other stays green -- which is why the
    single-shape version of this case could not see the mutation at all.
    """
    (fixture_repo / "CHANGELOG.md").write_text(starting_changelog)
    _git(fixture_repo, "add", "-A")
    # --allow-empty: one of the two shapes is what the fixture already wrote.
    _git(fixture_repo, "commit", "-q", "--allow-empty", "-m", "docs: set the changelog shape")
    _git(fixture_repo, "push", "-q", "origin", "main")
    _commit(fixture_repo, "feat(scope): a feature")
    assert _release(fixture_repo, "0.1.0").returncode == 0
    text = (fixture_repo / "CHANGELOG.md").read_text()
    assert text.startswith("# Changelog\n")
    assert text.count("# Changelog\n") == 1, "the header was duplicated"
    assert "## v0.1.0" in text
    assert "- **scope:** a feature" in text
    assert text == text.rstrip("\n") + "\n", "exactly one trailing newline"

    # *Where* the section lands, not merely that it is present. The insertion
    # point is immediately under the header, which is what makes a header-only
    # seed the only shape that stays coherent across releases.
    assert text.startswith("# Changelog\n\n## v0.1.0"), (
        "the section is not directly under the header"
    )
    if starting_changelog is CHANGELOG:
        # And the consequence, asserted rather than described: prose that was
        # under the header is now under the *section*. This is why the
        # repository's own CHANGELOG.md carries none -- see the case below.
        assert text.index("## v0.1.0") < text.index(CHANGELOG_PREAMBLE_FIRST_LINE), (
            "the preamble did not sink below the new section"
        )


def test_the_release_commit_and_tag_are_both_signed(fixture_repo):
    """`cat-file -t` reports "tag" for signed and unsigned annotated tags alike,
    so it cannot catch a dropped -S. Look at the objects themselves.

    The fixture sets commit.gpgsign and tag.gpgsign false for this case's sake: with
    either true, git would sign anyway and the case could not see the flag go.
    """
    _commit(fixture_repo, "feat: something")
    assert _release(fixture_repo, "0.1.0").returncode == 0
    commit = _git(fixture_repo, "cat-file", "commit", "HEAD").stdout
    assert "gpgsig" in commit, "release commit is not signed (-S dropped?)"
    assert "Signed-off-by: " in commit, "release commit lacks DCO sign-off (-s dropped?)"
    tag = _git(fixture_repo, "cat-file", "tag", "v0.1.0").stdout
    assert "BEGIN SSH SIGNATURE" in tag, "release tag is not signed"


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is needed to build the fixture lockfile")
def test_uv_lock_is_refreshed_with_the_bump_when_present(fixture_repo):
    """uv.lock pins the project's own version, so a bump that skipped the re-lock
    would leave the lockfile stale -- and CI runs `uv sync --locked`, so the release
    would break the build it had just tagged.
    """
    subprocess.run(
        ["uv", "lock", "-q"],
        cwd=fixture_repo,
        check=True,
        capture_output=True,
        env={**os.environ, "UV_OFFLINE": "1"},
    )
    _git(fixture_repo, "add", "-A")
    _git(fixture_repo, "commit", "-q", "-m", "build: add a lockfile")
    _git(fixture_repo, "push", "-q", "origin", "main")
    lock = fixture_repo / "uv.lock"
    assert 'version = "0.1.0"' in lock.read_text(), "fixture lockfile does not pin its own version"

    result = _release(fixture_repo, "0.2.0")
    assert result.returncode == 0, result.stderr
    assert _version(fixture_repo) == "0.2.0"
    # The point of the case: a stale lock is what breaks `uv sync --locked`, so
    # assert the lockfile's own recorded version moved -- not just pyproject's.
    assert 'version = "0.2.0"' in lock.read_text(), (
        "uv.lock still records the old version; the re-lock step did not run"
    )
    assert "uv.lock" in _git(fixture_repo, "show", "--stat", "--format=", "HEAD").stdout, (
        "uv.lock was re-locked but not committed with the release"
    )
    assert _git(fixture_repo, "status", "--porcelain", "-uno").stdout == "", (
        "the release left an unstaged lockfile change behind"
    )


@pytest.mark.skipif(
    shutil.which("uv", path=_SYSTEM_PATH) is not None,
    reason=f"uv is reachable on {_SYSTEM_PATH}, so it cannot be hidden from the script",
)
def test_the_preflight_rejects_a_missing_uv_before_touching_the_worktree(fixture_repo):
    """A missing uv is a fix-your-PATH problem, so it must be caught in preflight
    rather than half-way through -- after the bump but before the commit is exactly
    where it would poison a version number.

    PATH is narrowed to the system directories rather than emptied: the script's
    shebang is `/usr/bin/env bash`, so an empty PATH fails at exec and the case
    would measure nothing. uv is normally installed under the user's home, so it
    disappears while git, sed and awk stay reachable.
    """
    (fixture_repo / "uv.lock").write_text("version = 1\n")
    _git(fixture_repo, "add", "-A")
    _git(fixture_repo, "commit", "-q", "-m", "build: add a lockfile")
    _git(fixture_repo, "push", "-q", "origin", "main")
    result = _release(fixture_repo, "0.2.0", PATH=_SYSTEM_PATH)
    assert result.returncode != 0
    assert "uv is not on PATH" in result.stderr
    assert _version(fixture_repo) == "0.1.0", "the worktree was mutated before the uv check"
    assert _git(fixture_repo, "tag", "-l").stdout.strip() == ""


# --- second release ---------------------------------------------------------


def test_an_equal_version_is_rejected_once_a_release_tag_exists(fixture_repo):
    _commit(fixture_repo, "feat: one")
    assert _release(fixture_repo, "0.1.0").returncode == 0
    _commit(fixture_repo, "feat: two")
    result = _release(fixture_repo, "0.1.0")
    assert result.returncode != 0
    assert "already exists locally" in result.stderr
    lower = _release(fixture_repo, "0.0.9")
    assert lower.returncode != 0
    assert "must be greater than the current version" in lower.stderr


def test_a_pre_release_tag_is_not_treated_as_the_previous_release(fixture_repo):
    """The notes range must stay anchored at the last real release."""
    _commit(fixture_repo, "feat: one")
    assert _release(fixture_repo, "0.1.0").returncode == 0
    _git(fixture_repo, "tag", "v0.2.0-rc1")
    _commit(fixture_repo, "feat: after the rc")
    result = _release(fixture_repo, "--dry-run", "0.2.0")
    assert result.returncode == 0, result.stderr
    assert "Commit range : v0.1.0..HEAD" in result.stdout


def test_no_conventional_commits_still_produces_a_valid_section(fixture_repo):
    _commit(fixture_repo, "feat: one")
    assert _release(fixture_repo, "0.1.0").returncode == 0
    result = _release(fixture_repo, "0.2.0")
    assert result.returncode == 0, result.stderr
    text = (fixture_repo / "CHANGELOG.md").read_text()
    assert "No changes recorded." in text
    assert "\n\n## v0.1.0" in text, "a blank line must separate the new section"
    assert text.count("# Changelog\n") == 1, "the header was duplicated"
    assert text == text.rstrip("\n") + "\n", "exactly one trailing newline"


# --- rollback and resume ----------------------------------------------------


def test_a_failed_commit_restores_the_worktree(fixture_repo):
    """Signing is mandatory, so point signingkey at a file that does not exist.
    Nothing may be left half-applied: a version bump with no tag makes that
    version permanently unreleasable."""
    _commit(fixture_repo, "feat: something")
    head = _git(fixture_repo, "rev-parse", "HEAD").stdout
    _git(fixture_repo, "config", "user.signingkey", str(fixture_repo / "nope.pub"))
    result = _release(fixture_repo, "0.2.0")
    assert result.returncode != 0
    assert _version(fixture_repo) == "0.1.0", "pyproject.toml was left bumped"
    assert (fixture_repo / "CHANGELOG.md").read_text() == CHANGELOG
    assert _git(fixture_repo, "tag", "-l").stdout.strip() == ""
    assert _git(fixture_repo, "rev-parse", "HEAD").stdout == head
    assert _git(fixture_repo, "status", "--porcelain", "-uno").stdout == ""


def test_a_tag_this_script_did_not_create_does_not_trigger_a_resume(fixture_repo):
    """There would be no bump and no changelog section to publish."""
    _commit(fixture_repo, "feat: something")
    _git(fixture_repo, "tag", "-a", "-m", "by hand", "v0.2.0")
    result = _release(fixture_repo, "0.2.0")
    assert result.returncode != 0
    assert "already exists locally" in result.stderr
    assert "Resuming" not in _both(result)
    assert _version(fixture_repo) == "0.1.0"
    assert _git(_origin(fixture_repo), "tag", "-l").stdout.strip() == ""


def test_a_failed_push_is_resumable(fixture_repo):
    """A rejecting pre-receive hook on the bare origin gives the real-world state:
    the signed commit and tag exist locally, nothing reached the remote. Remove the
    hook and re-run the same command; it must resume at the push rather than start
    over.

    A hook rather than a broken remote URL, which is what the brief proposed: the
    script fetches the remote before anything else, so an unreachable URL fails in
    the fetch and the release commit this case needs is never made.
    """
    _commit(fixture_repo, "feat: something")
    hook = _origin(fixture_repo) / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'rejected by the test hook' >&2\nexit 1\n")
    hook.chmod(0o755)

    first = _release(fixture_repo, "0.2.0")
    assert first.returncode != 0
    assert _git(fixture_repo, "log", "-1", "--format=%s").stdout.strip() == (
        "chore(release): v0.2.0"
    ), "the release commit should exist locally after a failed push"
    assert _git(fixture_repo, "tag", "-l", "v0.2.0").stdout.strip() == "v0.2.0"
    assert _git(_origin(fixture_repo), "tag", "-l", "v0.2.0").stdout.strip() == ""

    hook.unlink()
    second = _release(fixture_repo, "0.2.0")
    assert second.returncode == 0, second.stderr
    assert "Resuming at the push" in second.stderr
    assert _git(_origin(fixture_repo), "tag", "-l", "v0.2.0").stdout.strip() == "v0.2.0"
    assert (
        _git(_origin(fixture_repo), "rev-parse", "main").stdout
        == _git(fixture_repo, "rev-parse", "HEAD").stdout
    )
    assert _git(fixture_repo, "tag", "-l").stdout.split() == ["v0.2.0"], "the tag was re-made"


def test_an_already_published_tag_resumes_at_the_release_step(fixture_repo):
    """The third row of docs/releasing.md's recovery table: the tag is published and
    the GitHub Release is not, so a re-run must resume there and commit nothing.

    Exercises the remote-tag resolution too -- the arm keys on the commit the
    *remote* tag points at, read from the ls-remote output rather than the local tag.
    """
    _commit(fixture_repo, "feat: something")
    assert _release(fixture_repo, "0.2.0").returncode == 0
    head = _git(fixture_repo, "rev-parse", "HEAD").stdout
    again = _release(fixture_repo, "0.2.0")
    assert again.returncode == 0, again.stderr
    assert "Resuming at the GitHub release step" in again.stderr
    assert "nothing will be committed or pushed" in again.stderr
    assert _git(fixture_repo, "rev-parse", "HEAD").stdout == head
    assert _git(fixture_repo, "tag", "-l").stdout.split() == ["v0.2.0"]


def test_a_hand_pushed_tag_at_head_does_not_resume_at_the_release_step(fixture_repo):
    """The resume-at-GitHub-release arm needs the same gate as the resume-at-push one,
    and needs it tested separately.

    A hand-pushed vX.Y.Z sitting at HEAD used to resume straight to "Done." with
    nothing released -- no version bump, no changelog section, a release page
    announcing a tag nobody cut. The case above it cannot reach this arm: it leaves
    the hand-made tag unpushed, so `git ls-remote` comes back empty and the arm is
    unreachable whatever its condition says. This one pushes the tag, which is what
    puts the arm in play.
    """
    _commit(fixture_repo, "feat: something")
    _git(fixture_repo, "tag", "-a", "-m", "hand-made tag", "v0.2.0")
    _git(fixture_repo, "push", "-q", "origin", "v0.2.0")
    result = _release(fixture_repo, "0.2.0")
    assert result.returncode != 0
    assert "already exists locally" in result.stderr
    assert "Resuming" not in _both(result), "a hand-pushed tag resumed and released nothing"
    assert "Done." not in result.stdout
    assert _version(fixture_repo) == "0.1.0"
    assert "## v0.2.0" not in (fixture_repo / "CHANGELOG.md").read_text()


def test_the_push_is_atomic_so_main_and_the_tag_land_together_or_not_at_all(fixture_repo):
    """An `update` hook rejecting only refs/heads/main is the shape that matters.

    Non-atomically that state left the tag published with no release commit on main
    -- and the next run then saw the pushed tag, resumed at the GitHub release step
    and reported success with the remote still behind. Atomic routes the same failure
    to the resume-at-push arm instead, which is why the second half of this case
    asserts that a re-run publishes both refs rather than just finishing quietly.
    """
    _commit(fixture_repo, "feat: something")
    origin = _origin(fixture_repo)
    main_before = _git(origin, "rev-parse", "main").stdout
    hook = origin / "hooks" / "update"
    hook.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        "    refs/heads/main) echo 'main rejected by the test hook' >&2; exit 1 ;;\n"
        "esac\n"
        "exit 0\n"
    )
    hook.chmod(0o755)

    first = _release(fixture_repo, "0.2.0")
    assert first.returncode != 0
    assert _git(origin, "tag", "-l", "v0.2.0").stdout.strip() == "", (
        "the tag was published without its release commit; the push was not atomic"
    )
    assert _git(origin, "rev-parse", "main").stdout == main_before

    hook.unlink()
    second = _release(fixture_repo, "0.2.0")
    assert second.returncode == 0, second.stderr
    assert "Resuming at the push" in second.stderr
    assert _git(origin, "tag", "-l", "v0.2.0").stdout.strip() == "v0.2.0"
    assert _git(origin, "rev-parse", "main").stdout == (
        _git(fixture_repo, "rev-parse", "HEAD").stdout
    ), "the resumed run left the remote behind"


def test_a_hand_written_changelog_preamble_survives(fixture_repo):
    """A first line that is not `# Changelog` used to be discarded unconditionally by
    `tail -n +2`, which silently threw away whatever a human had written there.

    The script now drops that line only when it is the header it is about to re-emit.
    Neither parameter of the trailing-newline case can see this: both start with
    `# Changelog`, so the conditional and the unconditional drop behave identically.
    """
    _commit(fixture_repo, "feat: one")
    assert _release(fixture_repo, "0.1.0").returncode == 0
    text = (fixture_repo / "CHANGELOG.md").read_text()
    assert text.startswith("# Changelog\n")
    (fixture_repo / "CHANGELOG.md").write_text(
        "Hand-written preamble line\n" + text[len("# Changelog\n") :]
    )
    _git(fixture_repo, "add", "-A")
    _git(fixture_repo, "commit", "-q", "-m", "docs: add a changelog preamble")
    _git(fixture_repo, "push", "-q", "origin", "main")

    result = _release(fixture_repo, "0.2.0")
    assert result.returncode == 0, result.stderr
    text = (fixture_repo / "CHANGELOG.md").read_text()
    assert "Hand-written preamble line" in text, "the hand-written first line was discarded"
    assert text.startswith("# Changelog\n"), "the header was not re-emitted"
    assert text.count("# Changelog\n") == 1, "the header was duplicated"
    assert "## v0.1.0" in text, "the previous release section was lost"
    assert text == text.rstrip("\n") + "\n", "exactly one trailing newline"
    # Survives, but not where its author put it, and "survives" on its own reads
    # as "is preserved" -- which is the claim this case used to leave a reader
    # with and is not true. Measured: the line sinks past exactly the one new
    # section, so it ends up between v0.2.0 and the v0.1.0 it was written above.
    # One place lower per release, which is the whole argument for seeding the
    # repository's own CHANGELOG.md with the header alone.
    assert (
        text.index("# Changelog")
        < text.index("## v0.2.0")
        < text.index("Hand-written preamble line")
        < text.index("## v0.1.0")
    ), f"the preamble did not sink past exactly the new section:\n{text}"


def test_the_repositorys_own_changelog_is_seeded_with_the_header_and_nothing_else():
    """The seed shape the insertion above requires, asserted on the real file.

    Not a style rule. `release.sh` re-emits everything below line 1 *after* the
    new section, so prose seeded here would appear under the newest release and
    move down at every release after that. The file this repository shipped
    before this case existed carried three paragraphs and an `[Unreleased]:` link
    definition; simulating the first release put all of it below the v0.1.0
    section, left "Sections below are generated at release time" pointing at
    nothing, and left the link definition dangling -- no `[Unreleased]` text
    referenced it, so it rendered as nothing at all.

    The explanation of the format lives in docs/releasing.md, which is a file the
    insertion cannot move.
    """
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert text == "# Changelog\n", (
        f"CHANGELOG.md must be the header alone until release.sh writes a section; found {text!r}"
    )


def test_tempfiles_are_cleaned_up(fixture_repo):
    """TMPDIR is redirected at the fixture, so the tempfiles the script owns are
    observable rather than lost among everything else in /tmp."""
    _commit(fixture_repo, "feat: something")
    assert _release(fixture_repo, "0.1.0").returncode == 0
    tmp = _tmpdir(fixture_repo)
    leftovers = sorted(p.name for p in tmp.iterdir() if p.name.startswith("release-"))
    assert leftovers == [], leftovers
    scratch = sorted(p.name for p in fixture_repo.iterdir() if p.name.endswith(".new"))
    assert scratch == [], scratch
