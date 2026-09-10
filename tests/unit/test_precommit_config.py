"""The pre-commit hooks agree with the versions this project actually pins.

The one predicate with teeth is the ruff rev. The recorded failure it guards
against is in the sibling project, at
https://github.com/skillberry-ai/simulation-harness/issues/15: its hook pinned
ruff 0.6.9 while the project ran a later ruff, so `ruff-format` rewrote files that
`ruff format --check` then rejected, and the two fought over every commit that
touched an affected file. The harness prevents a recurrence with a comment beside
the rev. A comment is not a guard -- this module is.

`uv.lock` is the authority rather than `pyproject.toml`, and the distinction is
the whole point: the dev extra declares a *range* (`ruff>=0.8,<0.17`), so there is
no single version there to compare against. The lock is what `make setup` and CI
both install, so it is what the hook has to match.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / ".pre-commit-config.yaml"
LOCK = REPO_ROOT / "uv.lock"
BASELINE = REPO_ROOT / ".secrets.baseline"


def _config() -> dict:
    assert CONFIG.is_file(), f"{CONFIG.name} is missing"
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def _repo_entry(url_fragment: str) -> dict:
    """The one `repos:` entry whose url contains `url_fragment`."""
    matches = [r for r in _config()["repos"] if url_fragment in r["repo"]]
    assert len(matches) == 1, f"expected exactly one {url_fragment} hook, found {len(matches)}"
    return matches[0]


def _locked_version(package: str) -> str:
    """The version `uv.lock` pins for `package`.

    Parsed with tomllib rather than by regex over the file: `uv.lock` holds one
    `[[package]]` table per dependency and a regex for `version` after a `name`
    match would read the wrong table the moment the field order changes.
    """
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    versions = [p["version"] for p in lock["package"] if p["name"] == package]
    assert len(versions) == 1, f"expected one {package} in uv.lock, found {len(versions)}"
    return versions[0]


def test_the_ruff_hook_rev_equals_the_locked_ruff():
    """A mismatch is the sibling project's recorded failure: the hook reformats
    the file, then the gate rejects what the hook wrote."""
    rev = _repo_entry("ruff-pre-commit")["rev"]
    assert rev == f"v{_locked_version('ruff')}", (
        f"ruff-pre-commit rev {rev} != locked ruff v{_locked_version('ruff')}. "
        "The hook would reformat files `ruff format --check` then rejects; bump both together."
    )


def test_the_large_file_hook_admits_the_committed_fixtures():
    """`check-added-large-files` defaults to 500kB and this tree commits more than
    twice that in captured trajectories, so the default would block a re-capture
    of a fixture the suite depends on. Asserted against the real files rather than
    a remembered number, so growing a fixture past the limit fails here."""
    hook = next(
        h for h in _repo_entry("pre-commit-hooks")["hooks"] if h["id"] == "check-added-large-files"
    )
    limit = int(next(a for a in hook["args"] if a.startswith("--maxkb")).split("=")[1])
    tracked = [p for p in (REPO_ROOT / "tests" / "fixtures").rglob("*") if p.is_file()]
    biggest = max(tracked, key=lambda p: p.stat().st_size)
    biggest_kb = biggest.stat().st_size // 1024
    assert limit > biggest_kb, (
        f"--maxkb={limit} is below {biggest.name} at {biggest_kb}kB; a re-capture would be blocked"
    )


def test_shellcheck_covers_every_tracked_shell_script():
    """The `files` pattern is a promise about coverage, so it is checked against
    the tree rather than trusted. `scripts/lib/` is the case that motivates it: a
    pattern of `^scripts/[^/]*\\.sh$` would silently skip both release libraries."""
    pattern = re.compile(_repo_entry("shellcheck-py")["hooks"][0]["files"])
    scripts = sorted(
        p.relative_to(REPO_ROOT).as_posix() for p in (REPO_ROOT / "scripts").rglob("*.sh")
    )
    assert scripts, "no shell scripts found; the tree moved"
    unmatched = [s for s in scripts if not pattern.search(s)]
    assert not unmatched, f"shellcheck's files pattern misses: {unmatched}"


@pytest.mark.parametrize(
    "hook_id",
    ["end-of-file-fixer", "trailing-whitespace", "check-yaml", "check-merge-conflict"],
)
def test_the_harness_hygiene_hooks_are_present(hook_id: str):
    """Adopted from `simulation-harness` unchanged; named individually so dropping
    one is a failure rather than a silent narrowing of the config."""
    ids = [h["id"] for h in _repo_entry("pre-commit-hooks")["hooks"]]
    assert hook_id in ids, f"{hook_id} missing from the pre-commit-hooks entry"


def test_detect_secrets_points_at_the_committed_baseline():
    hook = _repo_entry("detect-secrets")["hooks"][0]
    assert "--baseline" in hook["args"] and ".secrets.baseline" in hook["args"]
    assert BASELINE.is_file(), ".secrets.baseline is missing, so the hook has no baseline to read"


# The two hooks that *rewrite* files, and the paths they must never rewrite. This
# is the one adaptation `simulation-harness`'s config could not have needed: that
# repo has no recorded-history tree under a do-not-edit rule.
#
# Measured, not supposed. Adopting the harness config unmodified and running
# `pre-commit run --all-files` edited four files: three plans under
# docs/superpowers/ (trailing whitespace inside shell snippets, and missing final
# newlines) and tests/fixtures/corpus-toy/generated.txt, which is deliberately
# stored with no trailing newline because it is corpus input whose bytes a digest
# is taken over. Both classes are records: CLAUDE.md and docs/README.md say a
# record of what happened is falsified, not corrected, by a later edit.
_MUTATING_HOOKS = ("end-of-file-fixer", "trailing-whitespace")
_PROTECTED = ("docs/superpowers/plans/some-plan.md", "tests/fixtures/corpus-toy/generated.txt")


@pytest.mark.parametrize("hook_id", _MUTATING_HOOKS)
@pytest.mark.parametrize("path", _PROTECTED)
def test_the_rewriting_hooks_cannot_touch_records(hook_id: str, path: str):
    """A file-rewriting hook must not reach recorded history or a fixture."""
    hook = next(h for h in _repo_entry("pre-commit-hooks")["hooks"] if h["id"] == hook_id)
    exclude = hook.get("exclude")
    assert exclude, f"{hook_id} has no exclude, so it would rewrite {path}"
    assert re.search(exclude, path), f"{hook_id}'s exclude does not cover {path}"


def test_detect_secrets_still_scans_the_records_it_must_not_rewrite():
    """The exclusion above is about *rewriting*, and must not become a blanket one.

    detect-secrets reads without writing, and the fixtures are exactly where a
    captured credential would land, so scoping it away from them would remove the
    coverage that matters most. Asserted because the tempting fix for the finding
    above -- one top-level `exclude:` for the whole config -- would do that
    silently.
    """
    hook = _repo_entry("detect-secrets")["hooks"][0]
    assert "exclude" not in hook, "detect-secrets must keep scanning fixtures"
    assert "exclude" not in _config(), (
        "a top-level exclude would also stop detect-secrets scanning the fixtures"
    )
