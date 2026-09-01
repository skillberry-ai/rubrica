#!/usr/bin/env bash
#
# Every path a dispatched stage actually touched, pulled out of the stream-json
# transcript scripts/dispatch-stage.sh writes.
#
# This exists because the isolation rule is enforceable on artifacts inside a run
# and unenforceable on everything else a subagent can reach: a fan-out member
# that read a sibling's slice produces a byte-identical artifact to one that did
# not. No schema, no check-refs and no digest can catch it. The only instrument
# is a transcript audit, and both isolation violations observed in this project
# surfaced because a subagent volunteered them in a report nobody obliged it to
# write -- which is not an instrument, it is luck.
#
# Read the "file tools" list against the stage's Contract `reads`. A path outside
# it is graded Important, not Minor.
#
# Usage: scripts/audit-reads.sh <transcript.jsonl>
set -euo pipefail

T=${1:-}
[ -n "$T" ] || { echo "usage: $0 <transcript.jsonl>" >&2; exit 2; }
[ -f "$T" ] || { echo "no such transcript: $T" >&2; exit 2; }
command -v jq >/dev/null || { echo "jq is required and not on PATH" >&2; exit 2; }

# The toolset the dispatch was actually given, printed first because the two
# sections below are only as wide as it is.
#
# MEASURED 2026-09-01 at Claude Code 2.1.252, across a live sandbox, a broken one
# and no sandbox block: the init event's array carried **no Glob and no Grep**. Both
# are also absent from the parent session's toolset in this environment, so it looks
# like a property of the build rather than of the dispatch settings -- cause not
# established.
#
# Two of the six arms in the file-tools filter below therefore cannot match here.
# They are kept rather than deleted, because a build that restores those tools would
# otherwise get a silent blind spot in the only isolation instrument this project
# has. Printing the array is what makes the difference legible: with no Glob in it,
# no Glob lines below is arithmetic, not evidence of restraint.
echo "== toolset the dispatch was given =="
jq -r 'select(.type=="system") | (.tools // []) | join(", ")' "$T" | head -1

echo
echo "== file tools =="
jq -r 'select(.type=="assistant")
       | .message.content[]? | select(.type=="tool_use")
       | select(.name|test("^(Read|Glob|Grep|Edit|Write|NotebookEdit)$"))
       | "\(.name)\t\(.input.file_path // .input.path // .input.pattern // "-")"' "$T" \
  | sort -u

echo
echo "== bash commands =="
# Bash is the hole the file-tool list does not cover: a python -c that opens a
# file leaves no Read event, so these lines have to be read, not skimmed.
jq -r 'select(.type=="assistant")
       | .message.content[]? | select(.type=="tool_use") | select(.name=="Bash")
       | .input.command' "$T" | sort -u

echo
echo "== denials and tool errors =="
jq -r 'select(.type=="user")
       | .message.content[]? | select(.type=="tool_result")
       | select((.is_error==true) or ((.content|tostring)|test("permission|denied|not allowed";"i")))
       | (.content|tostring)' "$T" | cut -c1-200 | sort -u

echo
echo "== result =="
jq -r 'select(.type=="result")
       | "subtype=\(.subtype) turns=\(.num_turns) cost_usd=\(.total_cost_usd)"' "$T"
