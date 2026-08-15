# Contributing to Rubrica

Thanks for looking at Rubrica. This file covers the mechanics of contributing:
how to set up a dev environment, what CI checks, and the conventions every
commit is expected to follow. For what the project *is*, start with
`README.md`; for how the pipeline is put together, start with
`docs/pipeline-overview.md`.

## Setup

Python 3.13+, [`uv`](https://docs.astral.sh/uv/).

```sh
make setup
```

This creates a venv (`uv venv --python 3.13`) and installs the package with
its dev dependencies (`uv pip install -e '.[dev]'`). `README.md`'s commands
assume that venv is on `PATH`; if it is not, prefix each command with `uv
run` instead (e.g. `uv run rubrica --help`).

## The gates CI runs

CI runs exactly three checks, in this order:

1. `make check` — `ruff check` and `ruff format --check`, making no changes.
2. `make test` — the pytest suite (`uv run pytest -q`).
3. `uv run rubrica check-skills` — validates every skill's `## Contract`
   block against the code that owns those names (stages, artifact kinds,
   subcommands).

A red gate is not mergeable. Run all three locally before opening a PR:

```sh
make check && make test && uv run rubrica check-skills
```

## `make live` is not one of them

`make live` dispatches a model against the `live`-marked tests, gated by
`RUBRICA_LIVE` and the `live` pytest marker. Running it against the
recordings already committed in the repo is free — that's what CI's three
gates exercise indirectly, since they never touch `live` tests at all.
*Producing* a new recording costs money, because it means an actual model
call. For that reason `make live` and `RUBRICA_LIVE` never run in CI, and a
PR should never need them to pass.

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
failure, or a constraint from the design spec — not what the next line
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
