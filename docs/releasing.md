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

## The changelog

`CHANGELOG.md` is `# Changelog` and nothing else, and **that is a constraint
rather than an omission.** `scripts/release.sh` inserts each new section
immediately under the header and re-emits everything else below it, so any prose
added to that file lands *under* the newest release section and sinks one section
further with every release after it. No position in the file stays above the
sections, which is why the format is explained here instead of there. The file
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
follows [Semantic Versioning](https://semver.org/) — currently `0.x`, so anything
may change.

What lands in a section is the Conventional Commit subject as written, with one
exception: `scripts/lib/release-notes.sh` strips internal tracker citations out of
every subject, and out of any `BREAKING CHANGE:` footer prose, before it becomes a
bullet. So write the subject you would want to read there — and write it without a
tracker pointer, because one will be removed rather than rendered.

The exception is not a style preference. `CHANGELOG.md` is inside the citation
guard in `tests/unit/test_docs_accuracy.py` on purpose — a stale count in a
changelog section is a record, but a bare `#N` there is a live link to an
unrelated issue in the public repository — and commit subjects are immutable, so
the generator is the only place that can hold the property. Cutting v0.1.0 is what
measured this: nine citations reached the file from subjects written before the
tree's citations were rewritten, and the guard failed on `main`.

Deletion can leave a bullet reading clipped, which is the accepted cost. A
clipped bullet is a cosmetic defect; a pointer that resolves to the wrong issue is
a factual one.

**There are no `compare` links.** Keep a Changelog pairs each version with a link
to GitHub's compare view; `scripts/release.sh` generates none, neither an
`[Unreleased]` one nor a per-version one. A seeded `[Unreleased]:` link
definition is not a substitute and used to be in this repository: no `[Unreleased]`
text referenced it, so it rendered as nothing, its `compare/main...HEAD` target
compared `main` to itself, and it sank below the sections like any other line.
Delivering them means teaching the script to mint one per release, which is a
change to a script this repository transplanted rather than wrote, and it has not
been made.

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

## Exit codes: one divergence from the project's contract

Rubrica's exit-code contract reserves `2` for a usage error or an unreadable,
misconfigured run and `1` for findings. `scripts/release.sh` does not follow it,
and the divergence is recorded here rather than fixed. Its `usage()` exits `2`,
but every other failure routes through `die()`, which exits `1` — including four
states the contract assigns to `2`: `not inside a git repository`, `gh is not
installed or not on PATH`, `uv.lock exists but uv is not on PATH`, and `must be
on main to cut a release`. Each is a misconfigured environment, and each reports
`1`.

It stays that way because the script is a transplant kept in step with the
sibling repository it came from, and because nothing branches on its exit code
the way the orchestrator branches on a stage's — the contract exists so a `1` can
be retried and a `2` cannot, and there is no retry loop here. So do not read a
`1` from `release.sh` as "findings"; read the message.

## Tests

The release scripts are covered by `tests/unit/test_release.py` and
`tests/unit/test_release_notes.py`, which build throwaway git repositories as
fixtures — each with its own signing key, since the script signs unconditionally.
They touch no network remote and call no `gh`, so they run in `make test` like
everything else.
