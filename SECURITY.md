# Security Policy

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Use GitHub's private vulnerability reporting instead:

1. Go to the [Security tab](https://github.com/skillberry-ai/rubrica/security)
   of this repository.
2. Click **Report a vulnerability**.

This opens a private advisory visible only to you and the maintainers. If you
cannot use that form, open a regular issue containing only a request for a
private contact channel — no vulnerability details.

Please include, as far as you can determine it:

- the affected component and version (or commit SHA),
- the impact and the trust boundary crossed,
- steps to reproduce, ideally the `rubrica` invocation and the smallest corpus or
  run directory that triggers it,
- any configuration required to trigger it (`RUBRICA_*` environment variables, a
  hand-edited artifact, a `scripts/dispatch-stage.sh` dispatch).

We aim to acknowledge a report within 5 working days and to keep you updated as
we investigate. Please give us a reasonable opportunity to ship a fix before
disclosing publicly.

## Supported versions

This project is pre-1.0 and moves fast. Only the latest released version
receives security fixes; there are no long-term support branches.

| Version | Supported |
|---|---|
| latest release | ✅ |
| older releases | ❌ |

## Scope: the dispatch harness

Rubrica is a command-line tool, not a service, so most of its surface is the file
system of whoever runs it. One part is worth naming explicitly.

`scripts/dispatch-stage.sh` dispatches a model to run a pipeline stage, and it
passes that model credentials by two paths. Exported `ANTHROPIC_*` variables are
used as-is; when neither `ANTHROPIC_AUTH_TOKEN` nor `ANTHROPIC_API_KEY` is
exported, the script reads `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` and
`ANTHROPIC_API_KEY` out of `~/.claude/settings.json` and exports those instead.
So an empty environment is **not** evidence that no credential reaches the
dispatched model — the settings file is the other source, and it is read at
launch rather than copied, specifically so a token does not come to rest in the
scratch directory the dispatch runs in.

The same script grants the model `Write` access derived from the dispatched
stage's own `writes` contract. Both of the wider scopings that preceded it were
observed being used to drop a scratch file the pipeline had no use for, and the
two are not equally harmless:

- the **bare `Write` grant** put one in the repository root. That grant was not
  confined to scratch files: it reached `src/rubrica/*.py` and any sibling
  `SKILL.md`, so a dispatched stage could have edited the code or the prompt its
  own output was about to be judged against.
- the **run-directory scoping** that replaced it put one inside the run root,
  where nothing read it and nothing reacted to it.

Both are recorded in `docs/design/limitations.md`, and both are now pinned by
tests. `Read` access is still the whole run directory.

**CodeQL does not analyse shell.** `dispatch-stage.sh` is a substantial shell
program, so a clean CodeQL run on this repository is not evidence about it. If you
are deciding what a green scanning badge covers here, it covers the Python.

Genuinely in scope, and worth reporting:

- leakage of `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_API_KEY` or any other credential
  into a dispatch transcript, a run artifact, or a generated suite,
- a dispatched stage writing outside the scope its `writes` contract resolves to,
  or reading outside the deny list that holds it to its own skill directory,
- a corpus file, an artifact, or a hand-edited manifest achieving code execution
  in a `rubrica` subcommand,
- an emitted suite executing artifact content that was meant to be data,
- vulnerabilities in our dependency pinning or release/publish pipeline.

Out of scope: a dispatched model producing an inaccurate world model, a weak
scenario, or a verdict you disagree with. That is a correctness issue — please
open a normal issue for it.
