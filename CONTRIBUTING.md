# Contributing to Rubrica

Thanks for looking at Rubrica. This file covers the mechanics of contributing:
how to set up a dev environment, what CI checks, and the conventions every
commit is expected to follow. For what the project *is*, start with
`README.md`; for how the pipeline is put together, start with
`docs/concepts/pipeline.md`.

## Setup

Python 3.13+, [`uv`](https://docs.astral.sh/uv/).

```sh
make setup
```

This runs `uv sync --python 3.13 --extra dev`, which creates the venv and
installs the package and its dev dependencies **from the committed
`uv.lock`** — so you get the same pins CI does. `README.md`'s commands assume
that venv is on `PATH`; if it is not, prefix each command with `uv run`
instead (e.g. `uv run rubrica --help`).

**If you change a dependency, re-lock in the same commit.** Run `uv lock`
(or `uv lock --upgrade` to refresh within the constraints `pyproject.toml`
allows) and commit the resulting `uv.lock`. CI installs with `uv sync
--extra dev --locked`, which fails outright if the lockfile is out of date
with `pyproject.toml` rather than quietly re-resolving — so a forgotten
re-lock is a red gate, not a silent divergence between your machine and CI.

## The gates, and the rest of what CI runs

The project's gates are these, in this order:

1. **Lint and format** — `ruff check .` and `ruff format --check .`, making no
   changes.
2. **Tests** — the pytest suite.
3. **Skill contracts** — `rubrica check-skills`, validating every skill's
   `## Contract` block against the code that owns those names (stages, artifact
   kinds, subcommands).

**The gates are not all of CI, and this file will not tell you how much more
there is** — that number has gone stale here before. `.github/workflows/ci.yml`
carries the gates in its `check` job and a `dco` job beside them, which fails a
PR whose commits lack a `Signed-off-by` trailer; further workflows in
`.github/workflows/` run code scanning and dependency review on the same events.
Read that directory for the current set.

A red gate is not mergeable. Run all three locally before opening a PR — these
`make` targets are the same three checks, in the same order:

```sh
make check && make test && uv run rubrica check-skills
```

**`make` is not CI's entry point, though.** `.github/workflows/ci.yml` invokes
each check directly, as `uv run --extra dev <tool>`, rather than through a
target: every step repeats `--extra dev` so it is self-sufficient if the job is
reordered or a step is run on its own. The two are equivalent today, and nothing
enforces that they stay equivalent — so if you add a check to a `make` target,
add the matching step to `ci.yml` in the same commit, or it will simply not run
in CI while this file claims it does.

## `make live` is not one of them

`make live` dispatches a model against the `live`-marked tests, gated by
`RUBRICA_LIVE` and the `live` pytest marker. Running it against the
recordings already committed in the repo is free — that's what the three
gates exercise indirectly, since they never touch `live` tests at all.
*Producing* a new recording costs money, because it means an actual model
call. For that reason `make live` and `RUBRICA_LIVE` never run in CI, and a
PR should never need them to pass.

## Releasing

Releases are cut from `main` with one command:

```sh
make release VERSION=0.2.0
```

Everything that command does, what it refuses to do, and what to do when a run
fails part-way is in [`docs/releasing.md`](docs/releasing.md) — read it before
cutting one rather than working from this summary.

## Commits

Every commit must be both DCO signed-off and cryptographically signed:

```sh
git commit -S -s -m "..."
```

- `-s` (lowercase) adds the `Signed-off-by` trailer — the Developer
  Certificate of Origin. PRs without it fail CI checks.
- `-S` (uppercase) adds the cryptographic signature, so the commit shows as
  **Verified** on GitHub.

Both flags, every time. If signing fails (missing key, `gpg` error), stop
and report it — do not fall back to an unsigned commit and do not disable
signing to work around it.

To retroactively sign off and sign an existing branch:

```sh
git rebase --exec 'git commit --amend --no-edit -S -s' main
```

## AI attribution

If an AI assistant helped write a commit, credit it with a trailer of its
own, never as a co-author:

```
Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>
```

Never use `Co-Authored-By` or `Made-with` for this. GitHub parses those
trailers as co-authorship and inflates contributor stats for an assistant
that isn't a contributor in that sense.

## Comment density

This codebase's comment density is high and deliberate. A comment here
explains *why* a choice was made — usually citing a measurement, a prior
failure, or a constraint the artifact contract imposes — not what the next line
literally does. Match that when you add code; do not strip comments you
find inconvenient to keep updated.

## Adding or changing a test predicate

A new or edited assertion is only a guard once it has been watched fail.
Before committing one:

1. Delete or blank the thing it claims to check.
2. Confirm the predicate goes red.
3. Reword that same thing in a meaning-preserving way (different phrasing,
   same fact).
4. Confirm the predicate stays green.

A predicate nobody has watched fail in step 2 is not yet a guard — it may be
satisfied by unrelated content (a heading, a frontmatter line, anything
containing the substring it checks for) and never actually exercise the rule
it claims to enforce. For predicates over prompt text, do this against a
scratch copy under `RUBRICA_SKILLS_DIR` (pointed at a `/tmp` directory)
rather than editing the real skill files.

## Adding a stage or a skill

Four things own these names, and nothing else does:

- `paths.STAGES` — the stage ordering and the on-disk directory numbering.
- `validate.STAGE_ARTIFACTS` — which artifact kinds each stage's gate
  validates.
- `cli.SUBCOMMANDS` — the subcommand names the CLI recognizes.
- Every `SKILL.md`'s `## Contract` block, held to the three above by `rubrica
  check-skills`.

If you add or rename a stage, a skill, or a subcommand, `tests/unit/test_docs_accuracy.py`
will fail until the new name also appears in `docs/reference/cli.md`,
`docs/concepts/pipeline.md`, or `docs/reference/artifacts.md` as appropriate.
That failure is the guard doing its job, not a bug in the test — update the
docs rather than the assertion.

## Where documentation lives

[`docs/README.md`](docs/README.md) is the map of what is current and what is
not. Read it before you go looking for something, and before you add a new
document.

One rule from it is worth restating here because it is easy to get backwards:
the dated build records that live alongside the current docs are recorded
history, not documentation. Do not cite them as describing current behavior,
and do not edit anything inside them — a record of what happened during a
past build is falsified, not corrected, by editing it after the fact.

## License

Rubrica is licensed under the [Apache License 2.0](LICENSE). By contributing,
you agree that your contributions are licensed under the same terms, and you
certify compliance with the Developer Certificate of Origin via the `-s`
sign-off on every commit (see "Commits" above).
