#!/usr/bin/env bash
#
# Dispatch one stage into a Claude Code instance that shares nothing with the
# developer's own setup.
#
# docs/guides/running-a-stage-by-hand.md is the runbook this automates; §7 there covers
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
#   scripts/dispatch-stage.sh reconcile-contradict "$RUN" sub-cap-get-ticket
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
#   RUBRICA_REJECT       space-separated scenario ids whose rejection is being
#                        carried into a score re-dispatch, verbatim
#   RUBRICA_FINDINGS_FILE  path to a file holding a gate's stdout, appended to a
#                        repair re-dispatch verbatim. Takes a FILE, never a
#                        string, so the text is a gate's bytes and not the
#                        orchestrator's retyping of them.
#   RUBRICA_PRINT_SETTINGS  set to 1 to write the settings files and the prompt,
#                        print their three paths, and dispatch nothing
#   RUBRICA_PRINT_TRANSCRIPT  set to 1 to print the transcript path this dispatch
#                        would write, and dispatch nothing
#   CLAUDE_CODE_MAX_OUTPUT_TOKENS  output-token ceiling for the dispatch. Claude
#                        Code's own variable, not this project's; pinned below to
#                        a default so a run's ceiling is on the record, and
#                        overridable here so a probe needs no file edit.
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
    [ "$name" = "rb-orchestrate" ] && continue   # it dispatches stages; it is not one
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
    reconcile-contradict)  SLICE_LINE="Your subject_id:   $SLICE" ;;
    instantiate|challenge) SLICE_LINE="Your scenario_id:  $SLICE" ;;
    triage-rule)           SLICE_LINE="Your slice_id:     $SLICE" ;;
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

# The output-token ceiling, declared here rather than inherited from whatever the
# spawned tool happens to default to. MEASURED on Claude Code 2.1.247 by pointing
# ANTHROPIC_BASE_URL at a local recorder that logs the request body and answers
# 400, so nothing was generated and the sweep cost nothing:
#
#   var unset, --model sonnet (logged as claude-sonnet-5)   max_tokens 64000
#   var unset, --model aws/claude-sonnet-4-6                max_tokens 32000
#   var unset, --model aws/claude-opus-5                    max_tokens 64000
#   var 8000 / 32000 / 64000 / 100000                       sent verbatim
#   var 999999                                              clamped to 128000
#
# Two things follow. The 32000 that killed propose round 2 on
# run-20260825-094033 was this default for the model that dispatch resolved to --
# not a model limit and not anything this project set; and the default is not one
# number, it moves with the model id, so which ceiling a run got was decided
# outside the repository. That is the reason for pinning, rather than headroom:
# the batch partition is what bounds the write.
#
# 64000 is the value this version already chooses for the alias RUBRICA_MODEL
# defaults to, so pinning it changes no observed behaviour there, while stopping a
# resolution like the sonnet-4-6 one above from halving the ceiling silently. This
# line was confirmed to be what reaches the wire, not just the environment: with
# the default temporarily set to a distinctive value and the variable unset in the
# caller, that value is what the recorder logged.
#
# A live request through the configured gateway carrying max_tokens=64000 was
# accepted -- HTTP 200, 4 output tokens -- but for `aws/claude-sonnet-4-6`, one of
# the ids that gateway grants, because `claude-sonnet-5` itself came back 403
# team-not-allowed on the same account.
#
# NOT established, and both need a generation that actually approaches the value:
# whether a response near 64000 completes, and what the endpoint enforces beyond
# accepting the field. The 128000 above is the client's clamp, not the API's.
export CLAUDE_CODE_MAX_OUTPUT_TOKENS="${CLAUDE_CODE_MAX_OUTPUT_TOKENS:-64000}"

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
# Derived, not guessed: the union of every skill's `reads` is capabilities_part,
# claims_dir, contradictions_dir, coverage_latest, entities_part,
# expected, goals_part, input_file, manifest, outcomes_part, scenarios, seed,
# subjects, verdict and world_model. Neither of these two is in it -- and, per
# the block below, neither is read by check-refs, which is the constraint that
# actually bounds this list. Re-derive rather than trust this line:
#   uv run python -c "from rubrica.skills import discover; print(sorted(
#     {n for s in discover() for n in s.contract.get('reads', [])}))"
RUN_DENY=("$RUN/decisions.md" "$RUN/measurement")

# ---------------------------------------------------------------------------
# What may NOT go in that list, MEASURED on 2026-08-13 and costing a wrong commit:
# any path `rubrica check-refs` reads.
#
# Most skills' contracts oblige them to invoke check-refs -- every reconcile pass,
# instantiate, score and emit. That subprocess runs inside the same sandbox as the member, so a
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

# WebSearch is denied for a reason unrelated to the answer key, and it is not a
# read path: MEASURED 2026-08-20, a tool named exactly `WebSearch` in the request
# makes LiteLLM 1.85.5's websearch_interception rewrite stream=True to
# stream=False, so the whole response is generated before any byte is sent and
# envoy's ~300s idle timeout kills the turn with zero bytes at 301.0s. Reconcile
# never completed until this was removed. No stage uses WebSearch. Denying it
# here strips it from the request's tools array (25 -> 24, verified on the wire),
# which is what defeats the name match -- a permission-only block would still
# advertise the tool and still be intercepted.
WS_DENY=("WebSearch")
for d in "$REPO"/src/rubrica/skills/rb-*; do
  [ "$d" = "$SKILL_DIR" ] || DENY+=("$d")
done

# `Write` is scoped to the run, and was a bare "Write" until 2026-08-14. MEASURED
# on the parsec run: the `rb-emit` dispatch wrote /home/.../rubrica/check_prune.py
# into the *repository root*, ran it, and deleted it. Harmless in content -- a
# read-only analysis script it used to check its own pruning -- but the capability
# is not: the same grant would let a dispatch edit src/rubrica/*.py or a sibling
# SKILL.md, which is the one thing that would corrupt what this project measures,
# and `record-stage`'s digest would only reveal a skill change after the run.
# `Edit` was already scoped; `Write` was the hole. Note also that the sandbox
# scope's allowWrite: [$run] did NOT stop it, which is a third data point for the
# "do not rely on this layer" comment above.
#
# A "//abs" rule is "/" prepended to a path that already starts with "/".
SETTINGS_FILE="$LAB/settings-$STAGE${SLICE:+-$SLICE}.json"
jq -n --arg repo "$REPO" --arg run "$RUN" --arg skilldir "$SKILL_DIR" \
  --argjson deny "$( { printf '%s\n' "${DENY[@]}" \
      | jq -R '"Read(/" + . + ")", "Read(/" + . + "/**)"'; \
      printf '%s\n' "${WS_DENY[@]}" | jq -R .; } | jq -s .)" \
  '{permissions: {
      deny: $deny,
      allow: ["Read(/" + $skilldir + "/**)", "Read(/" + $run + "/**)",
              "Edit(/" + $run + "/**)", "Write(/" + $run + "/**)",
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

# ---------------------------------------------------------------------------
# The rejection notice -- the third sanctioned append, and the one CLAUDE.md's
# "exactly two things" summary omits. rb-score's Inputs section names it as "a
# whole kind of dispatch rather than an edge case": score may be re-dispatched
# after rb-challenge has judged, to record a rejection and recompute against it.
#
# The payload is fixed at three fields per rejected scenario -- uniquely_determined,
# derivable_without_guessing, and notes -- quoted from the verdict file. score's
# `reads` still excludes 05-verdicts/, so this text is the only way a rejection
# reaches it.
#
# What must NOT go in: `rejected_reason`. The enum is score's to choose from the
# quoted evidence, and rb-score says a notice that had already picked from it
# "would be the conclusion-passing the orchestrator's own rules forbid". So this
# block carries no reason, and `verdict` and `flags` stay out for the same reason
# they stay out of the re-seed block -- they are the adversary's conclusions.
#
# A second re-seed is accepted here because rb-orchestrate's table maps it to a
# rejection ("Verdict re-seed, second time | Treat as a rejection"). The
# escalation is announced on stderr rather than made silently, because it is the
# orchestrator's ruling and not something the verdict file says.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# The repair append -- the first of the two the design sanctions, and the one
# this script never implemented until a gate finding needed routing back.
#
# It takes a FILE rather than a string on purpose. A string parameter invites the
# orchestrator to type what it believes the gate said; a file makes the append a
# copy of the gate's own stdout. Same defence as the re-seed block: a paraphrase
# is not declined here, it is inexpressible.
#
# An empty or missing file is exit 2 rather than a silent no-append, because a
# repair dispatch that arrives carrying nothing is indistinguishable from a first
# dispatch -- which is exactly the no-op that cost this run a wasted challenge.
# ---------------------------------------------------------------------------
FINDINGS_BLOCK=""
if [ -n "${RUBRICA_FINDINGS_FILE:-}" ]; then
  if [ ! -s "$RUBRICA_FINDINGS_FILE" ]; then
    echo "RUBRICA_FINDINGS_FILE is empty or missing: $RUBRICA_FINDINGS_FILE" >&2
    echo "       A repair dispatch must carry the findings that provoked it." >&2
    exit 2
  fi
  FINDINGS_BLOCK=$(cat "$RUBRICA_FINDINGS_FILE")
fi

REJECT_BLOCK=""
if [ -n "${RUBRICA_REJECT:-}" ]; then
  if [ "$STAGE" != "score" ]; then
    echo "RUBRICA_REJECT applies only to score; $STAGE takes no rejection notice" >&2
    exit 2
  fi
  for sid in $RUBRICA_REJECT; do
    V="$RUN/05-verdicts/$sid.json"
    if [ ! -f "$V" ]; then
      echo "no verdict to build a rejection notice from: $V" >&2
      exit 2
    fi
    actual=$(jq -r '.verdict' "$V")
    case "$actual" in
      reject) ;;
      re-seed)
        echo "note: $sid's verdict is 're-seed'; carrying it as a rejection per" >&2
        echo "      rb-orchestrate section 3 (re-seed, second time -> treat as a rejection)." >&2
        ;;
      *)
        echo "$sid's verdict is '$actual'; a rejection notice for it would invent one" >&2
        exit 2
        ;;
    esac
    REJECT_BLOCK="$REJECT_BLOCK
$sid, quoted verbatim from $V:

$(jq '{uniquely_determined, derivable_without_guessing, notes}' "$V")
"
  done
fi

# The dispatch prompt, verbatim from docs/guides/running-a-stage-by-hand.md §2. Nothing
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

if [ -n "$FINDINGS_BLOCK" ]; then
  PROMPT="$PROMPT

A gate reported findings against the artifact you wrote. Its stdout, verbatim:

$FINDINGS_BLOCK

Repair only what these findings name."
fi

if [ -n "$REJECT_BLOCK" ]; then
  PROMPT="$PROMPT

rb-challenge rejected the following scenarios of this round. For each, its
verdict's \`uniquely_determined\`, \`derivable_without_guessing\` and \`notes\`:
$REJECT_BLOCK"
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
# Never overwrite a prior attempt. MEASURED cost of the previous behaviour:
# propose round 2's transcript overwrote round 1's on run-20260825-094033,
# destroying the only per-attempt record of the failure that motivated the
# bounded-batch change -- and for propose the round is exactly what a reader needs
# to tell two attempts apart. The script does not know the round and does not need
# to: "do not destroy the prior attempt" is the whole requirement. The first
# attempt keeps the unsuffixed name, because that is the path the closing summary
# prints and audit-reads.sh is pointed at.
if [ -e "$TRANSCRIPT" ]; then
  n=2
  while [ -e "$LAB/transcripts/$STAGE${SLICE:+-$SLICE}-$n.jsonl" ]; do
    n=$((n + 1))
  done
  TRANSCRIPT="$LAB/transcripts/$STAGE${SLICE:+-$SLICE}-$n.jsonl"
fi

# Stop here with the transcript path chosen and nothing dispatched, for the reason
# the print-settings block above exists: the alternative ways to check this naming
# either cost a model dispatch or grep this file's source, and a test that greps
# the source passes when the rule is present and unreachable. Prints one line.
if [ "${RUBRICA_PRINT_TRANSCRIPT:-0}" = "1" ]; then
  echo "$TRANSCRIPT"
  exit 0
fi

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
