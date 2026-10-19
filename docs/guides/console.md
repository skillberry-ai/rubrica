# The browser console

`rubrica-console` opens a local web page from which you can start a run, run each
stage, watch dispatches as they happen, hold the human gates, and read every
report. It does what the shell helpers around `scripts/dispatch-stage.sh` do, with
the state of the run on screen instead of in your head.

```bash
uv run rubrica-console --runs-dir runs          # every run in runs/
uv run rubrica-console --run runs/run-20261007-143204   # open one run
# prints http://127.0.0.1:8765/ — open it in a browser; Ctrl+C stops it
```

Its code is in [`console/`](../../console/README.md) at the repository root, apart
from the `rubrica` package: it drives the pipeline only through the `rubrica` CLI and
`scripts/dispatch-stage.sh`, and nothing in `src/` imports it.

Prompt stages need a checkout of this repository (the console calls
`scripts/dispatch-stage.sh`), `claude` and `jq` on `PATH`, bash 4 or newer — on
macOS, `brew install bash` — and **the console's own model credentials**, set on
its Settings page. Without them the page says so, and code steps and gates still
work.

## Model access

The console does not use the credentials of the shell it was started from, or
Claude Code's own settings. Open **Settings** and give it its own: a base URL
(blank for the default Anthropic API), an auth token or an API key, and any extra
headers your gateway needs — `x-context-guru-token`, for instance. **Copy from
Claude Code settings** fills them in from `~/.claude/settings.json` on the server,
without the values passing through the page. **Test connection** makes one tiny
real call through the same path a dispatch takes (about $0.002).

They are kept in `~/.config/rubrica/console-credentials.json` (or `--credentials`),
readable only by you. The page never gets a secret back — only whether it is set
and its last four characters — and the file picker will not show or accept that
file. Every dispatch gets exactly these credentials: any `ANTHROPIC_*` variable in
the console's own environment is removed first.

This is why: a dispatch used to borrow whatever the starting shell had, and
`dispatch-stage.sh` copies a token and a base URL from Claude Code's settings but
not a gateway's extra header. Started from a plain terminal, every dispatch of a
real run was refused with a 401.

## What you see

**Runs.** Every run under `--runs-dir`, how far it has got, what is next, and what
the console has spent on it.

**New run.** Either *survey a corpus* — the run goes through triage and stops at
gate 0 — or *hand-pick input files*, which skips triage and gate 0 the way
`rubrica intake --input` does. Creating a run calls no model.

Both use the same picker: a checkbox on every file and folder, a path box, a filter
for the folder you are in, *select all here* / *clear here*, and a summary of what
is in and out with a live file count. Checking a folder takes everything inside it;
open it and uncheck anything to leave that out. A half-filled box is a folder that
is partly in. The selection is kept as you move between folders.

What a selection becomes depends on the mode, because the two commands take
different things:

- **Hand-pick:** every file the selection covers, folders expanded, minus what you
  unchecked, becomes one `--input`. Hidden files and folders (`.git`, `.venv`) are
  skipped and symlinks are not followed.
- **Survey:** each checked folder is a `--corpus` root, and each thing you unchecked
  inside one becomes an `--exclude` pattern, shown on the form before the run is
  created. `survey` only takes folders, so a file cannot be checked on its own, and
  it cannot take something back in from inside a folder you left out; the picker
  greys both out and says why. An exclusion applies under *every* corpus folder,
  and one with no folder in it (a file at the top of a root) also leaves out every
  file with that name below it — the form says so when either applies.

**A run.** On the left, every step of the pipeline in order, grouped by phase:
triage, world model, each round, suite. Each step is one of:

| Status | Meaning |
|---|---|
| done | its output is on disk (and its checks passed, or you accepted them) |
| ready | the next thing to do — or, for a gate, waiting for you |
| running | a job is running it now |
| failed | a check reported findings you have not repaired or accepted |
| waiting | an earlier step is not done |

Status comes from the run's files, not from the console's memory, so a run you
drove by hand, or with `rb-orchestrate`, shows up correctly too. A fan-out step
shows how many members are done; running it only dispatches the missing ones, so
it is always safe to run again after a crash.

On the right, the selected step: what it does, the exact commands a click runs,
its members, and every job that has run it — each dispatch's turns, cost and last
action, and each command's log.

## Running things

- **Run** runs one step. Anything that calls a model asks first, saying how many
  dispatches it will start and, once the run has some history, what they have cost
  on average.
- **Run to next gate** runs steps in order and stops at the next human gate, at any
  check that reports findings, at a step that exits 2, or at anything that needs you
  (smoke needs an agents roster file). A round's later steps are only known once the
  round before them finishes, so the confirmation is a lower bound across the round
  loop.
- **Model, effort and cap** in the top bar are passed to each dispatch as
  `RUBRICA_MODEL`, `RUBRICA_EFFORT` and `RUBRICA_BUDGET`, and recorded with
  `record-stage`. They are remembered per browser.
- At most `--max-parallel` dispatches (default 3) run at once, across every run the
  console drives. Three is the cap `rb-orchestrate` uses for the shared gateway.
- **Cancel** stops a job's running dispatches. Its finished members stay on disk.
- **A fan-out stops itself** when its first three dispatches all fail without
  spending anything — that is a failure to reach the model (credentials, gateway,
  model id), and every other member would fail the same way. The step shows the
  model call's own error. A dispatch that spent money and then failed does not count.

## Running the same inputs again

Each run keeps what it was made from — the mode, every folder and file you picked,
what you unchecked, the target, the limits — beside its console records. **New run
from these inputs**, on a run's page, opens the New run form already filled in;
change anything, then create. For a run the console did not create, the form is
filled from the run itself (a survey run's corpus folders and exclusion patterns,
or a hand-picked run's input files), and the page says so. The New run form also
keeps a draft in your browser, so leaving the page does not lose a selection.

## Deleting a run

**Delete run**, on a run's page, removes the run's folder and the console's own
records for it under `console/<run name>/`. It cannot be undone, so you type the
run's name to confirm, and it is refused while a job is still running on the run
(cancel it first). Dispatch transcripts in the lab directory are shared between
runs and are left alone.

## When the connection drops

A dispatch that does not finish — the network dropped, the laptop slept, the
process was stopped — is an **interruption**, not a failure. The step stops
there, before its checks, so nothing is reported as a stage defect and no repair
is spent. The page says **Interrupted — nothing is lost**, and **Resume** runs
again only the dispatches that did not finish: every member that finished is
kept and not paid for twice. A member that died after writing part of its file
is redone too, because the console remembers which dispatches did not finish
rather than trusting that a file on disk is complete. If a repair is the thing
interrupted, the repair is given back. **Run to next gate** resumes the same way.
If the console itself stopped, its jobs show as interrupted when it starts again,
and the step resumes from what is on disk.

## When a check fails

A check that exits 1 marks the step **failed** and keeps its findings. Then:

- **Repair (one attempt)** re-dispatches the step with the findings attached,
  word for word, through `RUBRICA_FINDINGS_FILE`. For a fan-out, each member gets
  only the finding lines that name it. If the repair fails too, the step halts, as
  `rb-orchestrate` would.
- **Accept these findings and continue** records your reason in `decisions.md` and
  treats those exact lines as accepted from then on. A later check that prints the
  same line no longer fails; a new line still does.
- **Run again** is there when you have fixed something by hand. For a fan-out it
  dispatches only the members with no finished output.

A code step (a seal, for instance) offers no repair: its findings name an
artifact an earlier stage wrote, which is where the fix belongs.

A check that exits 2 halts the job with no repair, because re-dispatching cannot
fix a harness or filesystem problem.

## Gates

**Gate 0** has its own page, drawn from `gate-brief --gate 0 --format json`:

- A summary strip: whether the objective is supported, how many files are
  admitted and their size, the declines, the open gaps, and your rulings.
- **Needs you**: one card for each thing that needs a human — a declined file
  (declines that share a reason fold into one card when there are more than
  three), a gap whose suggested fix was not supplied (with the
  `adopt-projection` command to supply it), the largest admits, an unsupported
  objective, a predicted surface nothing confirmed, a folder split across slices.
  A file's card has **Admit / Decline**; a change asks for your reason, and a
  decline for its reason code. Every card has a 💬 comment box.
- **All files**, closed by default: every file by folder, a checkbox each
  (checked means the run reads it) and one per folder, with triage's reason and
  yours on expand.
- **Save changes** records each change with `rubrica overrule`, re-runs
  `triage-seal`, `validate` and `check-refs`, and leaves the gate open.
  **Approve with N changes** does the same and then approves. Your rulings in
  force are listed with **Undo**. Triage's own decisions stay on disk beside
  yours, and once gate 0 is approved the page is read-only.

The other gates show their `gate-brief` split into sections, one card each. A long section
shows its first lines and can be filtered, and lines of the form `name: 12/40 ...`
get a bar. Each section has a **Comment** button. Your comments and an overall
note are kept as a draft in your browser until you send them, and are joined into
one line of `decisions.md`. Earlier notes on the gate are listed under the brief.

**Record feedback, don't approve yet** writes
`console: feedback on gate N, not approved: <your review>` and leaves the gate
open. No model step reads `decisions.md`, so feedback reaches the record and the
next person, not a stage: to change what a stage produced, edit its file or re-run
the step, then approve. **Approve** records
`human gate N (console): <your review>` with `rubrica decide`; at gate 0 it first runs
`rubrica intake --run`, which admits what triage chose. A blocking gap is listed on
gate 1, and approving gate 1 is your ruling that the run may go on. From gates 1
to 3 you can also **waive** a finding (`rubrica waive`) or **change a limit**
(`rubrica set-limit`). After a round's coverage is sealed you can **stop the round
loop** there.

A gate counts as passed when `decisions.md` has a line starting `human gate N` or
`Gate N:` (the form hand-written decisions have used), or when a later stage has
already run.

## Where things are kept

The console writes into a run only through `rubrica` commands and
`dispatch-stage.sh`. Its own job records, logs, findings files and the small
ledger of what it has done (which scenarios it re-seeded, which findings you
accepted) live under `--lab` (default `$RUBRICA_LAB`, else `<runs-dir>/../lab`) in
`console/<run name>/`. Dispatch transcripts go where `dispatch-stage.sh` puts them,
in the same lab directory. Restarting the console marks jobs that were running as
*interrupted*; the files on disk say what finished.

Losing the lab directory loses one fact the run's files do not hold: which
scenarios already had their one re-seed. The next follow-up would re-seed them
again.

## Safety

The console starts model dispatches, so being on your own machine is not enough
protection on its own: any page open in your browser can send requests to
`127.0.0.1`. So:

- It listens on `127.0.0.1` only, unless you pass `--host`.
- Every action needs a secret token that only the console's own page knows.
- Requests whose `Host` or `Origin` names some other site are refused, which stops
  a hostile domain from pointing itself at your machine.
- The file picker stays under `--root` (default: your home directory), and run
  files are served only from inside the run. An HTML file inside a run is shown as
  text, never run as a page.

## Options and exit codes

`--runs-dir DIR` or `--run RUN` (one is required; `--run` opens that run and uses its
parent as the runs folder). Optional: `--host` (default `127.0.0.1`), `--port`
(default `8765`; `0` lets the system pick), `--root` (where the file picker may
browse; default your home directory), `--lab` (the console's own records; default
`$RUBRICA_LAB`, else `<runs-dir>/../lab`), `--max-parallel` (default `3`),
`--model` (default `$RUBRICA_MODEL`, else `sonnet`), `--effort` (default `medium`),
`--dispatch-script` (default this checkout's `scripts/dispatch-stage.sh`),
`--credentials` (default `~/.config/rubrica/console-credentials.json`).

It exits `0` when interrupted and `2` for a runs folder or run that does not exist,
a port that cannot be bound, or a bad argument. It never exits `1`: the work it
starts reports through its own subprocesses' exit codes, shown in the page. A
report that fails on one page — `gate-brief` over an unreadable `01-claims/`, which
is exit 2 on the command line — becomes an error on that page, and the console keeps
answering for every other one.

## How this relates to `rb-orchestrate`

The console follows `rb-orchestrate`'s walk in code: the same order, the same
checks after each stage, one repair, the three-dispatch cap, re-seed once, rejects
through `rb-score`. It does not use or change the skill. So a run driven from the
console is not evidence about whether `rb-orchestrate` works —
[`limitations.md`](../design/limitations.md) records this.
