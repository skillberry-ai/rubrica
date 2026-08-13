#!/usr/bin/env bash
#
# Dispatch one stage into a Claude Code instance that shares nothing with the
# developer's own setup.
#
# docs/running-a-stage-by-hand.md is the runbook this automates; §7 there covers
# why an isolated instance is worth the trouble and what is and is not enforced.
# The short version: this project's falsifiable claim is that the *prompt*
# carries the judgment across artifact handoffs. A dispatch that also carries a
# global CLAUDE.md, whatever plugins and hooks the developer runs, and this
# repository's own CLAUDE.md and design spec is not measuring the skill -- it is
# measuring the skill plus a briefing, and the briefing is the answer key.
#
# Usage:
#   scripts/dispatch-stage.sh <stage> <run-dir> [slice-id]
#
#   scripts/dispatch-stage.sh extract   "$RUN" api-json
#   scripts/dispatch-stage.sh reconcile "$RUN"
#
# Environment:
#   RUBRICA_LAB          scratch dir for settings and transcripts
#                        (default ${TMPDIR:-/tmp}/rubrica-lab)
#   RUBRICA_MODEL        model for the dispatch (default sonnet)
#   RUBRICA_EFFORT       effort for the dispatch (default medium)
#   RUBRICA_BUDGET       hard dollar ceiling for the dispatch (default 2)
#   RUBRICA_NO_SANDBOX   set to 1 to omit the sandbox block entirely
#   RUBRICA_RESEED       set to 1 to carry a re-seed verdict's alternative_answers
#                        and notes into an instantiate re-dispatch, verbatim
#   RUBRICA_PRINT_SETTINGS  set to 1 to write the settings files and the prompt,
#                        print their three paths, and dispatch nothing
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
LAB=${RUBRICA_LAB:-${TMPDIR:-/tmp}/rubrica-lab}

for tool in claude jq; do
  command -v "$tool" >/dev/null || { echo "$tool is required and not on PATH" >&2; exit 2; }
done

STAGE=${1:-}
RUN_ARG=${2:-}
SLICE=${3:-}
if [ -z "$STAGE" ] || [ -z "$RUN_ARG" ]; then
  echo "usage: $0 <stage> <run-dir> [slice-id]" >&2
  exit 2
fi
RUN=$(cd "$RUN_ARG" 2>/dev/null && pwd) || { echo "no such run directory: $RUN_ARG" >&2; exit 2; }

SKILL_DIR="$REPO/src/rubrica/skills/rb-$STAGE"
SKILL="$SKILL_DIR/SKILL.md"
if [ ! -f "$SKILL" ]; then
  echo "no skill for stage '$STAGE'. Stages with a skill:" >&2
  for d in "$REPO"/src/rubrica/skills/rb-*; do
    name=$(basename "$d")
    [ "$name" = "rb-orchestrate" ] && continue   # the eighth skill is not a stage
    echo "  ${name#rb-}" >&2
  done
  exit 2
fi

# The slice id is an address, not context: a fan-out member cannot find its own
# work without it. Give it its own id and nothing about any sibling.
SLICE_LINE=""
if [ -n "$SLICE" ]; then
  case "$STAGE" in
    extract)               SLICE_LINE="Your artifact_id:  $SLICE" ;;
    instantiate|challenge) SLICE_LINE="Your scenario_id:  $SLICE" ;;
    *) echo "$STAGE is a single dispatch over everything; it takes no slice id" >&2; exit 2 ;;
  esac
fi

mkdir -p "$LAB/transcripts"
export CLAUDE_CONFIG_DIR="$LAB/cc-config"
mkdir -p "$CLAUDE_CONFIG_DIR"

# Auth. An isolated CLAUDE_CONFIG_DIR means the developer's OAuth session is not
# in scope, so the dispatch needs credentials from the environment. If they are
# already exported, they are used as-is; otherwise they are read out of the real
# user settings at launch rather than copied into a second file, so a token does
# not end up sitting in the scratch dir.
USER_SETTINGS="$HOME/.claude/settings.json"
if [ -z "${ANTHROPIC_AUTH_TOKEN:-}" ] && [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -f "$USER_SETTINGS" ]; then
  for var in ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_API_KEY; do
    val=$(jq -r --arg v "$var" '.env[$v] // empty' "$USER_SETTINGS")
    [ -n "$val" ] && export "$var=$val"
  done
fi
if [ -z "${ANTHROPIC_AUTH_TOKEN:-}" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "warning: no ANTHROPIC_AUTH_TOKEN or ANTHROPIC_API_KEY in the environment" >&2
  echo "         or in $USER_SETTINGS -- the dispatch will probably fail to authenticate." >&2
fi

# Every skill's Invariants section tells the stage to run bare `rubrica ...`, and
# README.md says commands assume the venv is on PATH. Put it there. Measured
# without this: the stage reaches for `uv run rubrica`, which wants a writable uv
# cache it does not have, and spends its whole budget thrashing on that instead
# of on the artifact.
[ -x "$REPO/.venv/bin/rubrica" ] || {
  echo "warning: $REPO/.venv/bin/rubrica not found -- run 'make setup' first," >&2
  echo "         or the stage cannot run its own gate." >&2
}
export PATH="$REPO/.venv/bin:$PATH"

# ---------------------------------------------------------------------------
# Two enforcement layers, deliberately in two different settings scopes.
#
# MEASURED, both directions, on Claude Code 2.1.227: a `sandbox` block in the
# file passed to --settings silently stops that same file's permissions.deny
# Read rules from being enforced -- no warning, the reads just succeed. The same
# deny list with the sandbox key deleted blocks; with it added back, it does not.
# So sandbox goes in the isolated user scope and permissions go in --settings.
#
# What each layer covers:
#   permissions.deny Read(...)   the Read/Grep/Glob tools, and the file commands
#                                Claude Code parses out of a Bash line
#   sandbox.filesystem.denyRead  OS-level, via bubblewrap, so a Python script
#                                that opens the file itself is stopped too
#
# The sandbox layer has been measured twice, with opposite results, and both
# observations are kept because neither explains the other:
#
#   2.1.227, directory entry ($REPO/docs): did NOT engage, even with bubblewrap
#     0.9.0 and socat installed and `bwrap --unshare-all` working standalone -- a
#     `python -c "open(...)"` read a denyRead path successfully.
#   2.1.231, file entry ($RUN/decisions.md): DID engage -- the same
#     `python3 -c "open(...)"` got PermissionError [Errno 13], while a control
#     read of $RUN/01-world-model.json in the same dispatch returned its
#     contents, so it was that path being denied and not Bash file access
#     failing wholesale.
#
# Version, or file-versus-directory: unknown which accounts for it. Do not rely
# on this layer on a machine where you have not checked it yourself.
# failIfUnavailable is set so a silent fall-through becomes loud rather than
# being mistaken for enforcement. Set RUBRICA_NO_SANDBOX=1 to drop the block if
# it gets in the way, and read the read audit rather than trusting either layer.
# ---------------------------------------------------------------------------

# Three paths inside the run are the run's own answer key. Granting the whole run
# directory is right for artifacts and wrong for these, because no skill's
# Contract lists any of them under `reads`:
#
#   decisions.md    the orchestrator's log -- gate rulings, and in a measured
#                   run the pre-registered predictions for the very stage being
#                   dispatched. Observed on 2026-08-13: a propose dispatch ran
#                   `ls -la` in the run directory with P7-P9 sitting in that
#                   file, one Read away from the answer to its own exercise. It
#                   was killed before it got there, which is luck, not a control.
#   measurement/    recall.json/.md and review/sample.json/packet.md -- the
#                   human review surface, which is scored *against* the stages.
#
# Derived, not guessed: the union of every skill's `reads` is claims_dir,
# coverage_latest, expected, input_file, manifest, scenarios, seed, verdict and
# world_model. Neither of these two is in it -- and, per the block below, neither
# is read by check-refs, which is the constraint that actually bounds this list.
RUN_DENY=("$RUN/decisions.md" "$RUN/measurement")

# ---------------------------------------------------------------------------
# What may NOT go in that list, MEASURED on 2026-08-13 and costing a wrong commit:
# any path `rubrica check-refs` reads.
#
# Four skills' contracts oblige them to invoke check-refs (reconcile, instantiate,
# score, emit). That subprocess runs inside the same sandbox as the member, so a
# denied artifact is invisible to the *checker* too -- and bubblewrap masks a
# denied path to a character device, which is not absent and not readable.
#
# The first version of this block also denied $RUN/05-verdicts to instantiate,
# because rb-instantiate's SKILL.md says outright that 05-verdicts/ is not in its
# `reads` and a notice arriving any other way makes the re-dispatch a no-op. The
# intent was right and the mechanism was wrong: the scn-005 re-seed's own
# check-refs then reported ten fabricated "instance scn-XXX has no verdict"
# findings, while the identical command outside the sandbox exited 0. That is
# exactly the failure this repository already records for an unreadable
# 01-claims/ -- a `1` naming the wrong artifact.
#
# $RUN/07-report.json came out for the same reason without waiting to be bitten:
# check-refs reads it (refs.py:115 and :1279). It survived only because no run had
# reached smoke yet.
#
# So the rule is not "deny what the stage may not read" -- that is unenforceable
# here, because the stage's own gate must read the whole run. It is "deny only
# what check-refs never looks at", which is why decisions.md and measurement/
# stay: refs.py never references either. tests/unit/test_dispatch_harness.py
# derives this from refs._readable_targets rather than trusting this comment.
# ---------------------------------------------------------------------------

if [ "${RUBRICA_NO_SANDBOX:-0}" = "1" ]; then
  echo '{}' > "$CLAUDE_CONFIG_DIR/settings.json"
else
  jq -n --arg repo "$REPO" --arg run "$RUN" --arg skilldir "$SKILL_DIR" \
    --argjson rundeny "$(printf '%s\n' "${RUN_DENY[@]}" | jq -R . | jq -s .)" \
    '{sandbox: {
        enabled: true,
        autoAllowBashIfSandboxed: true,
        failIfUnavailable: true,
        filesystem: {
          allowRead: [$repo, $run, $skilldir],
          denyRead: ([$repo + "/docs", $repo + "/tests", $repo + "/src/rubrica/skills"] + $rundeny),
          allowWrite: [$run]
        },
        network: { allowedDomains: [] }
      }}' > "$CLAUDE_CONFIG_DIR/settings.json"
fi

# The answer key: the design spec under docs/, the golden fixture under tests/
# that a skill is supposed to imitate, this repository's own CLAUDE.md and
# README.md, and every sibling skill.
#
# permissions.deny beats permissions.allow unconditionally, so the skills root
# cannot be denied wholesale and this stage's own directory re-allowed inside it
# -- the siblings get enumerated one at a time. sandbox.filesystem uses the
# opposite rule (more specific path wins), which is why the two lists above and
# below are built differently from the same intent.
DENY=("$REPO/docs" "$REPO/tests" "$REPO/CLAUDE.md" "$REPO/README.md" "${RUN_DENY[@]}")
for d in "$REPO"/src/rubrica/skills/rb-*; do
  [ "$d" = "$SKILL_DIR" ] || DENY+=("$d")
done

# A "//abs" rule is "/" prepended to a path that already starts with "/".
SETTINGS_FILE="$LAB/settings-$STAGE${SLICE:+-$SLICE}.json"
jq -n --arg repo "$REPO" --arg run "$RUN" --arg skilldir "$SKILL_DIR" \
  --argjson deny "$(printf '%s\n' "${DENY[@]}" \
      | jq -R '"Read(/" + . + ")", "Read(/" + . + "/**)"' | jq -s .)" \
  '{permissions: {
      deny: $deny,
      allow: ["Read(/" + $skilldir + "/**)", "Read(/" + $run + "/**)",
              "Edit(/" + $run + "/**)", "Write",
              "Bash(rubrica *)", "Bash(" + $repo + "/.venv/bin/rubrica *)"]
    }}' > "$SETTINGS_FILE"

# ---------------------------------------------------------------------------
# The re-seed append -- one of exactly two things an orchestrator may add to a
# re-dispatch, and the reason this mechanism exists at all rather than a human
# retyping the objection.
#
# rb-orchestrate's step 227 and rb-instantiate's section 1 agree on the payload,
# and it is two fields, not four: the verdict's `alternative_answers` and its
# `notes`. Nothing else -- not `uniquely_determined`, not the verdict string.
#
# Built with jq straight from the verdict file, so a paraphrase is not something
# this script declines to write, it is something it cannot express. That is the
# whole design constraint: the parent spec calls a paraphrased finding "the
# orchestrator's conclusion wearing a finding's clothes", and the only structural
# defence is to make the text a copy rather than a rendering.
#
# `alternative_answers` arriving empty is meaningful rather than missing:
# rb-instantiate's section 1 says an empty list plus populated `notes` is the
# other defect shape -- a call the scenario never declared, or a disputed oracle --
# and the notes are then the entire reason. So the field is passed through as-is,
# empty or not, and this script never decides which shape it is.
# ---------------------------------------------------------------------------
RESEED_BLOCK=""
if [ "${RUBRICA_RESEED:-0}" = "1" ]; then
  if [ "$STAGE" != "instantiate" ]; then
    echo "RUBRICA_RESEED applies only to instantiate; $STAGE takes no re-seed notice" >&2
    exit 2
  fi
  if [ -z "$SLICE" ]; then
    echo "RUBRICA_RESEED needs the scenario_id whose verdict is being carried" >&2
    exit 2
  fi
  VERDICT="$RUN/05-verdicts/$SLICE.json"
  if [ ! -f "$VERDICT" ]; then
    echo "no verdict to re-seed from: $VERDICT" >&2
    exit 2
  fi
  # A re-seed notice for a verdict that is not a re-seed would be the orchestrator
  # inventing an objection, which is the same defect as paraphrasing one.
  actual=$(jq -r '.verdict' "$VERDICT")
  if [ "$actual" != "re-seed" ]; then
    echo "$SLICE's verdict is '$actual', not 're-seed'; nothing to carry" >&2
    exit 2
  fi
  RESEED_BLOCK=$(jq '{alternative_answers, notes}' "$VERDICT")
fi

# The dispatch prompt, verbatim from docs/running-a-stage-by-hand.md §2. Nothing
# else may be added to it: not a summary of what an earlier stage concluded, not
# an excerpt of the world model, and not a correction for something a skill got
# wrong. A skill defect belongs in the skill.
PROMPT="You are the $STAGE stage of the rubrica pipeline.

Run directory: $RUN
Your skill:    $SKILL
$SLICE_LINE

Read your skill and follow it exactly. Read only the artifacts your skill's
Contract block lists under \`reads\`. Write only what it lists under \`writes\`.
Do not read this pipeline's other stages, other scenarios, or any file the
contract does not name.

When you are done, report only: the paths you wrote, and any refusal
condition you hit."

# The appended block names its own provenance and quotes; it does not interpret.
# rb-instantiate already knows what a re-seed notice obliges it to do, so the
# framing stops at naming which file the JSON came out of.
if [ -n "$RESEED_BLOCK" ]; then
  PROMPT="$PROMPT

rb-challenge judged this scenario \`re-seed\`. Its verdict's
\`alternative_answers\` and \`notes\`, quoted verbatim from $VERDICT:

$RESEED_BLOCK"
fi

# Written out every run, not only in print-settings mode: the prompt is the one
# input to a dispatch that the transcript does not let you reconstruct exactly,
# and a re-seed run is precisely when you want to prove what was appended.
PROMPT_FILE="$LAB/prompt-$STAGE${SLICE:+-$SLICE}.txt"
printf '%s\n' "$PROMPT" > "$PROMPT_FILE"

# Stop here with both settings files and the prompt written, and nothing
# dispatched. This exists so the deny lists and the re-seed append are testable:
# every other way of checking them either costs a model dispatch or greps this
# file's source, and a test that greps the source passes when the rule is present
# and unreachable. Prints three paths in a fixed order -- permissions file,
# sandbox file, prompt file.
if [ "${RUBRICA_PRINT_SETTINGS:-0}" = "1" ]; then
  echo "$SETTINGS_FILE"
  echo "$CLAUDE_CONFIG_DIR/settings.json"
  echo "$PROMPT_FILE"
  exit 0
fi

TRANSCRIPT="$LAB/transcripts/$STAGE${SLICE:+-$SLICE}.jsonl"

# cwd is the run directory, not the repository. manifest.inputs[].source_path is
# a repo-relative path, so a run-dir cwd means it cannot resolve back to the
# original fixture file even by accident.
cd "$RUN"
claude -p "$PROMPT" \
  --safe-mode \
  --settings "$SETTINGS_FILE" \
  --strict-mcp-config \
  --disable-slash-commands \
  --add-dir "$SKILL_DIR" \
  --add-dir "$REPO" \
  --output-format stream-json --verbose \
  --model "${RUBRICA_MODEL:-sonnet}" \
  --effort "${RUBRICA_EFFORT:-medium}" \
  --max-budget-usd "${RUBRICA_BUDGET:-2}" \
  < /dev/null | tee "$TRANSCRIPT"

cat <<EOF

transcript  $TRANSCRIPT
gates       rubrica validate --stage $STAGE --run "$RUN"
            rubrica check-refs --run "$RUN"
read audit  $REPO/scripts/audit-reads.sh "$TRANSCRIPT"

The read audit is not optional housekeeping. A fan-out member that read a
sibling's slice produces a byte-identical artifact to one that did not, so no
schema, no check-refs and no digest can see the difference -- the transcript is
the only instrument there is.
EOF
