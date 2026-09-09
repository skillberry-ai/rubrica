# Releasing

Releases are cut with `scripts/release.sh` on `main`. A release tag is strictly
`vX.Y.Z`; a pre-release such as `v0.3.0-rc1` is not a release and is never treated
as the previous one. That definition lives once in `scripts/lib/release-tag.sh`.

## Cut a release

```sh
make release VERSION=0.2.0        # or: ./scripts/release.sh 0.2.0
```

This runs on `main` only, with a clean worktree and in sync with `origin/main`.
It bumps `version` in `pyproject.toml`, re-locks `uv.lock` (which pins the
project's own version, so it would otherwise go stale — `uv` must be on `PATH`),
prepends a `CHANGELOG.md` section built from Conventional Commit subjects since
the previous tag, commits `chore(release): v0.2.0`, creates a signed annotated
tag, pushes, and creates the GitHub Release.

The re-lock is not a nicety. CI runs `uv sync --locked`, so a bump that left the
lockfile behind would have the release break the build it had just tagged. The
check for `uv` happens in preflight, before anything in the worktree is touched.

Preview without writing anything:

```sh
./scripts/release.sh --dry-run 0.2.0
```

If a run pushes the tag and then fails, re-run the same command — it detects the
pushed tag and resumes at the GitHub Release step. See
[Recovering from a partial run](#recovering-from-a-partial-run).

The release page is created on `$RELEASE_GH_REPO`, which defaults to
`github.com/skillberry-ai/rubrica`. Override it if you are releasing a fork.
`RELEASE_SKIP_GH=1` skips the page entirely, and `RELEASE_REMOTE` selects the
push remote (default `origin`).

`CHANGELOG.md` ships with a Keep a Changelog header and nothing below it:
`scripts/release.sh` prepends every section, so the file grows only at release
time. What lands in a section is the Conventional Commit subject as written, so
write the subject you would want to read there.

## PyPI

Cutting a release does not publish the package — publishing the *release* does.
`.github/workflows/publish.yml` triggers on `release: published`, builds an sdist
and a wheel, and uploads them to PyPI with a Trusted Publisher: no API token is
stored anywhere, and PEP 740 attestations are generated automatically.

This means the workflow is **inert until a trusted publisher is registered on
PyPI** for this repository, the workflow filename `publish.yml`, and the `pypi`
environment. Until then a release cuts a tag and a release page and publishes
nothing, which fails visibly in the Actions tab rather than silently.

To build the distributions locally without involving CI: `uv build`.

## Recovering from a partial run

`scripts/release.sh` does four things that can fail separately. Each state has
exactly one move:

| State | What happened | What to do |
|---|---|---|
| Worktree unchanged, nothing tagged | The commit or the tag failed — most often signing. The script restores the worktree to what preflight found, so nothing is half-applied. | Fix signing, re-run the same command. Do **not** commit leftovers by hand: a version bump with no tag makes that version number permanently unreleasable. |
| Commit and tag exist locally, nothing on the remote | The push failed. It pushes `main` and the tag `--atomic`, so this is the only push-failure state — the tag is never published without its release commit. | Fix the cause and re-run `scripts/release.sh <same version>`. It detects the release commit and its tag at `HEAD` and resumes at the push. Do **not** `git pull` — that puts a merge commit on top of the release commit. |
| Tag pushed, no GitHub Release | `gh release create` failed. | Re-run the same command; it resumes at the GitHub Release step. |
| Everything published | — | Nothing; publishing the release is what fires `publish.yml`. |
| `tag vX.Y.Z already exists locally`, and you know a run got part-way | `HEAD` moved after the tag was made (an amend, or a commit on top), so the tag no longer sits on a release commit and resuming declines to fire. | If the tag was never pushed, drop it and start over: `git tag -d vX.Y.Z`, then re-run. If it was already pushed, leave it alone and cut the next version instead — a published tag is a fixed point. |

Resuming is deliberately narrow: both resume paths fire only for a tag this
script created, on a `chore(release): vX.Y.Z` commit at `HEAD` whose
`pyproject.toml` already holds that version. A tag made or pushed by hand is
rejected with `tag vX.Y.Z already exists locally`, since there would be no bump
and no changelog section to publish.

## Tests

The release scripts are covered by `tests/unit/test_release.py` and
`tests/unit/test_release_notes.py`, which build throwaway git repositories as
fixtures — each with its own signing key, since the script signs unconditionally.
They touch no network remote and call no `gh`, so they run in `make test` like
everything else.
