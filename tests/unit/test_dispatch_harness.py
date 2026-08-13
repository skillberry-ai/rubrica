"""The dispatch harness's deny lists, exercised through the script itself.

`scripts/dispatch-stage.sh` grants the dispatched stage `Read(<run>/**)`, which is
right for artifacts and wrong for the three run-local paths no skill's Contract
lists under `reads`. One of them, `decisions.md`, is the orchestrator's log --
and in a measured run it holds the pre-registered predictions for the very stage
being dispatched. On 2026-08-13 a `propose` dispatch ran `ls -la` in a run
directory with P7-P9 sitting in that file; it was one Read from its own answer
key, and what stopped it was an unrelated premature kill.

These tests drive the real script with `RUBRICA_PRINT_SETTINGS=1`, which writes
both settings files and exits before dispatching. Asserting against the emitted
JSON rather than against the script's source matters: a source grep passes on a
rule that is present and unreachable -- the substring-of-message weakness the
design spec's section 6 names -- and this rule's whole difficulty is that it has
to survive two settings scopes with opposite precedence rules.

Measured both directions before committing: deleting `$RUN/decisions.md` from the
script's RUN_DENY array turns all four assertions below red, and moving the
sandbox `+ $rundeny` concatenation without the parenthesis makes jq fail the run
outright rather than emitting a list quietly missing the entries.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "dispatch-stage.sh"

# The script hard-requires both on PATH and exits 2 without them, so a machine
# lacking either would fail these tests for a reason that is not the deny list.
missing = [tool for tool in ("claude", "jq") if shutil.which(tool) is None]
pytestmark = pytest.mark.skipif(
    bool(missing), reason=f"dispatch-stage.sh requires {', '.join(missing)} on PATH"
)


@pytest.fixture
def settings(tmp_path):
    """Run the harness in print-settings mode; return (permissions, sandbox) JSON.

    The run directory only has to exist -- the script resolves and grants it
    without reading any artifact, and nothing is dispatched in this mode.
    """
    run = tmp_path / "run"
    run.mkdir()
    proc = subprocess.run(
        [str(SCRIPT), "propose", str(run)],
        capture_output=True,
        text=True,
        env={**os.environ, "RUBRICA_LAB": str(tmp_path / "lab"), "RUBRICA_PRINT_SETTINGS": "1"},
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    perms_path, sandbox_path = proc.stdout.split()
    return (
        json.loads(Path(perms_path).read_text()),
        json.loads(Path(sandbox_path).read_text()),
        run.resolve(),
    )


# Derived, not guessed: the union of every skill's Contract `reads` is claims_dir,
# coverage_latest, expected, input_file, manifest, scenarios, seed, verdict and
# world_model. These three are what a run holds that no stage may name, and all
# three are *about* the stages rather than merely outside their scope -- an
# orchestrator log, a smoke report, and the human review surface.
OUT_OF_CONTRACT = ("decisions.md", "07-report.json", "measurement")


@pytest.mark.parametrize("leaf", OUT_OF_CONTRACT)
def test_the_permissions_scope_denies_each_run_local_answer_key(settings, leaf):
    perms, _, run = settings
    assert f"Read(/{run}/{leaf})" in perms["permissions"]["deny"]


@pytest.mark.parametrize("leaf", OUT_OF_CONTRACT)
def test_the_sandbox_scope_denies_each_run_local_answer_key(settings, leaf):
    """The second scope exists because the first one only covers the file tools.

    A `python -c "open(...)"` leaves no Read event for permissions.deny to match,
    which is why the same intent is expressed twice. The sandbox layer was
    measured non-functional on the machine this was built on, so this asserts the
    rule is *emitted*, never that the OS honours it.
    """
    _, sandbox, run = settings
    assert f"{run}/{leaf}" in sandbox["sandbox"]["filesystem"]["denyRead"]


def test_the_deny_of_a_run_path_outranks_the_blanket_run_read_grant(settings):
    """Both rules are present at once, and the narrow one has to win.

    permissions.deny beats permissions.allow unconditionally in Claude Code, so
    these two coexisting is the mechanism rather than a contradiction. Pinning it
    here because deleting the allow grant would also make the deny tests above
    pass, while breaking every stage's ability to read its own artifacts.
    """
    perms, _, run = settings
    assert f"Read(/{run}/**)" in perms["permissions"]["allow"]
    assert f"Read(/{run}/decisions.md)" in perms["permissions"]["deny"]


def test_the_run_artifacts_a_stage_must_read_are_not_denied(settings):
    """The over-subtraction direction, which an over-broad deny list would fail.

    A rule denying the run wholesale, or `01-*`, would satisfy every assertion
    above and leave `rb-propose` unable to read the world model it is dispatched
    to work from.
    """
    perms, sandbox, run = settings
    denied = set(perms["permissions"]["deny"]) | {
        f"Read(/{p})" for p in sandbox["sandbox"]["filesystem"]["denyRead"]
    }
    for artifact in ("manifest.json", "01-world-model.json", "02-scenarios.json", "01-claims"):
        assert f"Read(/{run}/{artifact})" not in denied
