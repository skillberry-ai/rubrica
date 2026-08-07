#!/bin/bash
# Harbor verifier entrypoint for a testgen-emitted task.
#
# Harbor's contract is a bare float in /logs/verifier/reward.txt; reward.json
# and reward-detail.json are written alongside for humans. verify.py writes no
# reward.txt when it refuses to score, so an unreadable contract reaches the
# platform as a missing reward rather than as a real zero.
#
# emit copies this file verbatim into every package; the tracked original is
# src/testgen/suite/test.sh.
set -o pipefail
mkdir -p /logs/verifier
python3 /tests/verify.py \
  --expected /tests/expected.json \
  --agent-logs /logs/agent \
  --out /logs/verifier
exit $?
