"""The dispatch harness's deny lists, exercised through the script itself.

`scripts/dispatch-stage.sh` grants the dispatched stage `Read(<run>/**)`, which is
right for artifacts and wrong for `decisions.md` -- the orchestrator's log, which in
a measured run holds the pre-registered predictions for the very stage being
dispatched. On 2026-08-13 a `propose` dispatch ran `ls -la` in a run directory with
P7-P9 sitting in that file; it was one Read from its own answer key, and what
stopped it was an unrelated premature kill.

The deny list is bounded from the other side too, which cost a wrong commit to
learn: four skills' contracts oblige them to invoke `check-refs`, that subprocess
runs inside the member's sandbox, and a denied artifact is therefore invisible to
the *checker*. Denying one makes a stage's own gate fabricate findings about what it
cannot see.

The second half covers the re-seed append -- the one channel by which an
adversary's `alternative_answers` and `notes` reach a re-dispatched
`rb-instantiate`, which cannot read `05-verdicts/` itself.

These tests drive the real script with `RUBRICA_PRINT_SETTINGS=1`, which writes
both settings files plus the composed prompt and exits before dispatching.
Asserting against the emitted JSON and prompt rather than against the script's
source matters: a source grep passes on a rule that is present and unreachable --
the substring-of-message weakness the design spec's section 6 names -- and these
rules' whole difficulty is that they have to survive two settings scopes with
opposite precedence rules.

Measured in every direction before committing:

- deleting `$RUN/decisions.md` from RUN_DENY turns exactly three red and leaves
  the other parametrizations green
- denying a world model the stage must read turns the over-subtraction test red
- appending the *whole* verdict instead of two fields turns the over-inclusion
  test red; appending only `notes` turns the verbatim and empty-list tests red
- moving the sandbox `+ $rundeny` concatenation outside its parenthesis makes jq
  fail the run outright rather than emitting a list quietly missing the entries
- restoring either of the two denies that were wrong -- `07-report.json`, or
  `05-verdicts` for `instantiate` -- turns
  `test_nothing_check_refs_reads_is_ever_denied` red. The `05-verdicts` half only
  goes red against a *populated* run, which is why that test builds a toy run
  through `challenge` rather than using a bare directory.
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


def _bwrap_dir(tmp_path, *, works):
    """A stub `bwrap` for PATH: one that engages, or one that fails as the pod did.

    The script probes `bwrap` before writing the sandbox block, so every test
    asserting that block's contents would otherwise depend on the developer's own
    bubblewrap working -- and the machine that motivated the probe is exactly the
    one where it does not. MEASURED 2026-09-01 on a pod with an empty capability
    bounding set: `bwrap --unshare-all --dev-bind / / --proc /proc true` exits 1
    with the message below, while the same command without `--proc` exits 0, which
    is how the fault stayed hidden.
    """
    bin_dir = tmp_path / ("bwrap-ok" if works else "bwrap-broken")
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "bwrap"
    body = "#!/usr/bin/env bash\nexit 0\n"
    if not works:
        # Faithful to the pod rather than failing unconditionally: it fails only
        # when asked to mount `proc`, and succeeds without `--proc`. That asymmetry
        # IS the fault, and a stub ignoring its arguments let the probe drop
        # `--proc` with every test still green -- measured, and why this loop exists.
        body = (
            "#!/usr/bin/env bash\n"
            'for a in "$@"; do\n'
            '  if [ "$a" = "--proc" ]; then\n'
            '    echo "bwrap: Can\'t mount proc on /newroot/proc: Operation not permitted" >&2\n'
            "    exit 1\n"
            "  fi\n"
            "done\n"
            "exit 0\n"
        )
    stub.write_text(body, encoding="utf-8")
    stub.chmod(0o755)
    return bin_dir


def _path_with(*dirs):
    """PATH with each directory prepended, in the order given."""
    return os.pathsep.join([*(str(d) for d in dirs), os.environ["PATH"]])


def _dispatch(tmp_path, *args, run=None, **env):
    """Run the harness in print-settings mode. Returns the CompletedProcess.

    The run directory only has to exist -- the script resolves and grants it
    without reading any artifact, and nothing is dispatched in this mode.

    A working stub `bwrap` is the default, so the sandbox block gets written on any
    machine; a caller passing its own PATH overrides that.
    """
    if run is None:
        run = tmp_path / "run"
        run.mkdir(exist_ok=True)
    env.setdefault("PATH", _path_with(_bwrap_dir(tmp_path, works=True)))
    return subprocess.run(
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "RUBRICA_LAB": str(tmp_path / "lab"),
            "RUBRICA_PRINT_SETTINGS": "1",
            **env,
        },
    )


def _paths(proc):
    """The three paths print-settings mode emits, in its fixed order."""
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    perms, sandbox, prompt = proc.stdout.split()
    return json.loads(Path(perms).read_text()), json.loads(Path(sandbox).read_text()), prompt


@pytest.fixture
def settings(tmp_path):
    """(permissions JSON, sandbox JSON, resolved run dir) for a propose dispatch."""
    run = tmp_path / "run"
    run.mkdir()
    perms, sandbox, _ = _paths(_dispatch(tmp_path, "propose", str(run), run=run))
    return perms, sandbox, run.resolve()


# Derived, not guessed: the union of every skill's Contract `reads` is claims_dir,
# coverage_latest, expected, input_file, manifest, scenarios, seed, verdict and
# world_model. Neither of these is in it, and both are *about* the stages rather
# than merely outside their scope -- an orchestrator log and the human review
# surface.
#
# The list is short for a second reason, which cost a wrong commit to learn: a path
# check-refs reads must never be denied. See
# test_nothing_check_refs_reads_is_ever_denied below, which derives that from
# refs.py rather than from this comment.
OUT_OF_CONTRACT = ("decisions.md", "measurement")


@pytest.mark.parametrize("leaf", OUT_OF_CONTRACT)
def test_the_permissions_scope_denies_each_run_local_answer_key(settings, leaf):
    perms, _, run = settings
    assert f"Read(/{run}/{leaf})" in perms["permissions"]["deny"]


@pytest.mark.parametrize("leaf", OUT_OF_CONTRACT)
def test_the_sandbox_scope_denies_each_run_local_answer_key(settings, leaf):
    """The second scope exists because the first one only covers the file tools.

    A `python -c "open(...)"` leaves no Read event for permissions.deny to match,
    which is why the same intent is expressed twice. This asserts the rule is
    *emitted*, never that the OS honours it -- the script's own comment records
    that layer engaging at Claude Code 2.1.231 and not engaging at 2.1.227, so a
    test asserting enforcement would encode one machine's version.
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


def test_write_is_scoped_to_the_run_and_not_granted_bare(settings):
    """A bare "Write" lets a dispatch write anywhere, and one did.

    MEASURED on 2026-08-14: with `Write` unscoped, the `rb-emit` dispatch wrote
    `check_prune_scratch.py` into the *repository root*, ran it, and removed it.
    The content was a read-only analysis script, but the same grant reaches
    `src/rubrica/*.py` and every sibling `SKILL.md` -- the one class of write that
    would corrupt what this project measures. The sandbox scope's
    `allowWrite: [$run]` did not stop it, so this rule is the enforcement.

    Asserting the absence of the bare string as well as the presence of the scoped
    one: granting both would leave the hole open while looking fixed.

    The scope is now the stage's own `writes` contract rather than the run
    directory, which closes the second half of the same hole. `Write(/$RUN/**)`
    stopped a dispatch escaping the run and permitted anything inside it -- and one
    dispatch used that too, putting a `compute_weights.py` helper in the run root
    (issue #15). Both the blanket grant and the bare one are asserted absent, since
    either would make the derived list decorative.
    """
    perms, _, run = settings
    allow = perms["permissions"]["allow"]
    assert "Write" not in allow
    assert f"Write(/{run}/**)" not in allow, "the run-wide grant is the hole #15 reports"
    assert f"Edit(/{run}/**)" not in allow
    # `propose` writes one scenario part. The fixture's run has no batch plan on
    # disk, so the resolver falls back to the artifact's own directory -- which is
    # the documented behaviour and still refuses everything else in the run.
    assert f"Write(/{run}/02-scenarios/**)" in allow
    assert f"Edit(/{run}/02-scenarios/**)" in allow


def test_no_write_grant_reaches_a_scratch_file_at_the_run_root(settings):
    """The measured defect in #15, stated as the property that refuses it.

    `rb-triage-objective`'s contract is `writes = ["objective"]`, and the dispatch
    documented in #12 also wrote `compute_weights.py` into the run directory. A
    scratch script there is not an artifact, is cleaned up by nothing, is covered by
    no schema, and `check-refs` exits 0 with it present -- `summary.orphaned_temp_files`
    keeps `p.name` where `".tmp." in p.name`, so it is a shape that mechanism does not
    cover.

    Asserted as "no grant matches" rather than "this one grant is absent", because
    the hole was a grant that matched *everything* in the run: a test naming one
    forbidden path would pass against a rule that still permitted the rest.
    """
    perms, _, run = settings
    grants = [g for g in perms["permissions"]["allow"] if g.startswith(("Write(", "Edit("))]
    assert grants, "the stage must be able to write something"
    stray = f"/{run}/compute_weights.py"
    for grant in grants:
        pattern = grant[grant.index("(") + 1 : -1]
        prefix = pattern[: -len("**")] if pattern.endswith("**") else pattern
        assert not stray.startswith(prefix) or pattern == stray, (
            f"{grant} would permit a scratch script at the run root"
        )


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


# --- triage --------------------------------------------------------------------
#
# triage-objective is a barrier pass (no slice id) reading only
# 00-slices.json, so unlike `settings` above these two dispatch it directly
# rather than through the `propose`-shaped fixture. It stands in for the family
# here because a later `rubrica check-refs` reads a file this pass does not,
# which is the asymmetry the second test needs.


def test_the_triage_dispatch_denies_the_decisions_log(tmp_path):
    """Every stage's dispatch denies decisions.md: a propose dispatch was
    measured one Read from the run's answer key on 2026-08-13."""
    run = tmp_path / "run"
    run.mkdir()
    perms, _, _ = _paths(_dispatch(tmp_path, "triage-objective", str(run), run=run))
    assert any("decisions.md" in rule for rule in perms["permissions"]["deny"])


def test_dispatch_hands_a_rule_member_its_slice_id():
    """triage-rule is a fan-out stage like extract and instantiate/challenge,
    so its dispatch case must hand the member its own slice id -- the shard
    filename `slice_shard` resolves against -- the same way extract hands an
    artifact_id and instantiate/challenge hand a scenario_id."""
    script = SCRIPT.read_text()
    assert "triage-rule)" in script
    assert "Your slice_id" in script


def test_dispatch_hands_a_propose_member_its_batch_id(tmp_path):
    """propose is a fan-out over the round's batch partition, so its dispatch
    case must hand the member its own batch_id -- the key it resolves against
    `02-batches/round-N.json` to find its own hole_refs.

    Asserted against the *composed prompt*, not against the script's source.
    A `"propose)" in script` grep passes on a rule that is present and
    unreachable, which is the weakness the script's own print-settings comment
    names; reading the prompt file proves the arm is reached. Whitespace is
    split rather than pinned, because the arms are column-aligned and a
    realignment is not a behaviour change.
    """
    run = tmp_path / "run"
    run.mkdir()
    _, _, prompt = _paths(_dispatch(tmp_path, "propose", str(run), "b01", run=run))
    lines = [ln for ln in Path(prompt).read_text().splitlines() if "batch_id" in ln]
    assert lines, "the composed prompt carries no batch_id line"
    assert lines[0].split() == ["Your", "batch_id:", "b01"]


def test_the_triage_dispatch_does_not_deny_a_path_check_refs_reads(tmp_path):
    """The mirror of the rule that cost two wrong denies: 2f93726 measured that
    denying a path check-refs reads makes a stage's own gate fabricate findings.
    triage-objective no longer reads the catalogue itself -- `catalogue_facts`
    on the plan is what it reads instead -- and its own gate cannot either,
    since its contract is `invokes = ["validate"]`. What a deny would break is
    a *later* `rubrica check-refs`: check_catalogue and check_slices both read
    the file, and RUN_DENY is one global list rather than a per-stage one, so a
    path denied here is denied to every dispatch whose gate does run it."""
    run = tmp_path / "run"
    run.mkdir()
    perms, sandbox, _ = _paths(_dispatch(tmp_path, "triage-objective", str(run), run=run))
    denied = set(perms["permissions"]["deny"]) | {
        f"Read(/{p})" for p in sandbox["sandbox"]["filesystem"]["denyRead"]
    }
    assert not any("00-catalogue.json" in rule for rule in denied)


# --- the re-seed append -------------------------------------------------------
#
# rb-orchestrate step 227 and rb-instantiate section 1 agree on the payload and it
# is two fields: the verdict's `alternative_answers` and its `notes`. The parent
# spec calls a paraphrased notice "the orchestrator's conclusion wearing a
# finding's clothes", so what these tests hold is not that the script declines to
# paraphrase -- it is that a copy is the only thing it can produce.

VERDICT = {
    "schema_version": "0.1",
    "scenario_id": "scn-001",
    "uniquely_determined": False,
    "derivable_without_guessing": True,
    "minimum_tool_calls_found": 1,
    "verdict": "re-seed",
    "alternative_answers": [
        {"answer": "CANARY-ALT-ANSWER", "world_consistent_reason": "CANARY-REASON"}
    ],
    "flags": ["CANARY-FLAG"],
    "notes": "CANARY-NOTES",
}


def _run_with_verdict(tmp_path, verdict=None, sid="scn-001"):
    run = tmp_path / "run"
    (run / "05-verdicts").mkdir(parents=True, exist_ok=True)
    (run / "05-verdicts" / f"{sid}.json").write_text(json.dumps(verdict or VERDICT))
    return run


def test_a_reseed_dispatch_carries_the_two_verdict_fields_verbatim(tmp_path):
    run = _run_with_verdict(tmp_path)
    _, _, prompt_file = _paths(
        _dispatch(tmp_path, "instantiate", str(run), "scn-001", run=run, RUBRICA_RESEED="1")
    )
    prompt = Path(prompt_file).read_text()
    assert "CANARY-ALT-ANSWER" in prompt
    assert "CANARY-REASON" in prompt
    assert "CANARY-NOTES" in prompt


def test_a_reseed_dispatch_carries_nothing_but_those_two_fields(tmp_path):
    """The over-inclusion direction, which a `cat the verdict` implementation fails.

    `verdict` and `minimum_tool_calls_found` are the adversary's *conclusions*;
    handing them over invites the member to defer rather than re-judge, which
    rb-instantiate's section 1 rules out in as many words.
    """
    run = _run_with_verdict(tmp_path)
    _, _, prompt_file = _paths(
        _dispatch(tmp_path, "instantiate", str(run), "scn-001", run=run, RUBRICA_RESEED="1")
    )
    prompt = Path(prompt_file).read_text()
    assert "CANARY-FLAG" not in prompt
    assert "minimum_tool_calls_found" not in prompt
    assert "uniquely_determined" not in prompt


def test_an_empty_alternatives_list_is_passed_through_rather_than_dropped(tmp_path):
    """Empty is a *shape*, not a missing value.

    rb-instantiate section 1: an empty `alternative_answers` with populated notes
    is the other defect class -- an undeclared call, or a disputed oracle -- and the
    notes are then the entire reason. A script that omitted the empty field would
    hide which of the two shapes arrived.
    """
    run = _run_with_verdict(tmp_path, {**VERDICT, "alternative_answers": []})
    _, _, prompt_file = _paths(
        _dispatch(tmp_path, "instantiate", str(run), "scn-001", run=run, RUBRICA_RESEED="1")
    )
    assert '"alternative_answers": []' in Path(prompt_file).read_text()


def test_no_reseed_flag_means_no_appended_block(tmp_path):
    run = _run_with_verdict(tmp_path)
    _, _, prompt_file = _paths(_dispatch(tmp_path, "instantiate", str(run), "scn-001", run=run))
    prompt = Path(prompt_file).read_text()
    assert "CANARY-NOTES" not in prompt
    assert "re-seed" not in prompt


@pytest.mark.parametrize(
    "verdict_value, sid, stage, expected_in_stderr",
    [
        ("accept", "scn-001", "instantiate", "not 're-seed'"),
        ("reject", "scn-001", "instantiate", "not 're-seed'"),
    ],
)
def test_a_reseed_notice_for_a_non_reseed_verdict_is_a_usage_error(
    tmp_path, verdict_value, sid, stage, expected_in_stderr
):
    """Inventing an objection is the same defect as paraphrasing one."""
    run = _run_with_verdict(tmp_path, {**VERDICT, "verdict": verdict_value}, sid=sid)
    proc = _dispatch(tmp_path, stage, str(run), sid, run=run, RUBRICA_RESEED="1")
    assert proc.returncode == 2
    assert expected_in_stderr in proc.stderr


def test_a_reseed_notice_to_a_stage_that_takes_none_is_a_usage_error(tmp_path):
    run = _run_with_verdict(tmp_path)
    proc = _dispatch(tmp_path, "reconcile-subjects", str(run), run=run, RUBRICA_RESEED="1")
    assert proc.returncode == 2
    assert "only to instantiate" in proc.stderr


def test_a_reseed_notice_with_no_verdict_file_is_a_usage_error(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    proc = _dispatch(tmp_path, "instantiate", str(run), "scn-001", run=run, RUBRICA_RESEED="1")
    assert proc.returncode == 2
    assert "no verdict to re-seed from" in proc.stderr


# --- the rejection notice -----------------------------------------------------
#
# rb-score's Inputs section calls this "a whole kind of dispatch rather than an
# edge case": score may be re-dispatched after rb-challenge has judged, to record
# a rejection and recompute against it. Its `reads` still exclude `05-verdicts/`,
# so the quoted fields are the only way a rejection reaches it.
#
# The payload is three fields -- `uniquely_determined`, `derivable_without_guessing`
# and `notes`. What must stay out is `rejected_reason`: rb-score says the enum is
# its own and a notice that had already chosen from it "would be the
# conclusion-passing the orchestrator's own rules forbid". `verdict` and `flags`
# stay out for the reason they stay out of the re-seed block.
#
# Measured on 2026-08-14, when this mode was added mid-run: widening the jq
# projection to the whole verdict turns the over-inclusion test red; narrowing it
# to `{notes}` turns the verbatim test red; dropping the accept guard turns
# test_a_rejection_notice_for_an_accepted_verdict_is_a_usage_error red while
# leaving the rest green.

REJECT_VERDICT = {
    "schema_version": "0.1",
    "scenario_id": "scn-042",
    "uniquely_determined": False,
    "derivable_without_guessing": False,
    "minimum_tool_calls_found": 2,
    "verdict": "reject",
    "alternative_answers": [
        {"answer": "CANARY-REJECT-ALT", "world_consistent_reason": "CANARY-REJECT-REASON"}
    ],
    "flags": ["CANARY-REJECT-FLAG"],
    "notes": "CANARY-REJECT-NOTES",
}


def test_a_rejection_notice_carries_the_three_verdict_fields_verbatim(tmp_path):
    run = _run_with_verdict(tmp_path, REJECT_VERDICT, sid="scn-042")
    _, _, prompt_file = _paths(
        _dispatch(tmp_path, "score", str(run), run=run, RUBRICA_REJECT="scn-042")
    )
    prompt = Path(prompt_file).read_text()
    assert "CANARY-REJECT-NOTES" in prompt
    assert '"uniquely_determined": false' in prompt
    assert '"derivable_without_guessing": false' in prompt
    assert "scn-042" in prompt


def test_a_rejection_notice_never_carries_the_reason_or_the_conclusions(tmp_path):
    """The over-inclusion direction, and `rejected_reason` is the load-bearing one.

    A notice that named the reason would pick from an enum rb-score says is its
    own. The adversary's `flags` and `alternative_answers` are its conclusions and
    belong no more here than in the re-seed block.
    """
    run = _run_with_verdict(tmp_path, REJECT_VERDICT, sid="scn-042")
    _, _, prompt_file = _paths(
        _dispatch(tmp_path, "score", str(run), run=run, RUBRICA_REJECT="scn-042")
    )
    prompt = Path(prompt_file).read_text()
    assert "rejected_reason" not in prompt
    assert "CANARY-REJECT-FLAG" not in prompt
    assert "CANARY-REJECT-ALT" not in prompt
    assert "minimum_tool_calls_found" not in prompt


def test_a_rejection_notice_covers_every_id_it_is_given(tmp_path):
    run = _run_with_verdict(tmp_path, REJECT_VERDICT, sid="scn-042")
    second = {**REJECT_VERDICT, "scenario_id": "scn-043", "notes": "CANARY-SECOND-NOTES"}
    (run / "05-verdicts" / "scn-043.json").write_text(json.dumps(second))
    _, _, prompt_file = _paths(
        _dispatch(tmp_path, "score", str(run), run=run, RUBRICA_REJECT="scn-042 scn-043")
    )
    prompt = Path(prompt_file).read_text()
    assert "CANARY-REJECT-NOTES" in prompt
    assert "CANARY-SECOND-NOTES" in prompt


def test_a_rejection_notice_to_a_stage_that_takes_none_is_a_usage_error(tmp_path):
    run = _run_with_verdict(tmp_path, REJECT_VERDICT, sid="scn-042")
    proc = _dispatch(tmp_path, "propose", str(run), run=run, RUBRICA_REJECT="scn-042")
    assert proc.returncode == 2
    assert "only to score" in proc.stderr


def test_a_rejection_notice_for_an_accepted_verdict_is_a_usage_error(tmp_path):
    """Inventing a rejection is the same defect as inventing an objection."""
    run = _run_with_verdict(tmp_path, {**REJECT_VERDICT, "verdict": "accept"}, sid="scn-042")
    proc = _dispatch(tmp_path, "score", str(run), run=run, RUBRICA_REJECT="scn-042")
    assert proc.returncode == 2
    assert "would invent one" in proc.stderr


def test_a_rejection_notice_with_no_verdict_file_is_a_usage_error(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    proc = _dispatch(tmp_path, "score", str(run), run=run, RUBRICA_REJECT="scn-042")
    assert proc.returncode == 2
    assert "no verdict to build a rejection notice from" in proc.stderr


def test_a_second_reseed_carried_as_a_rejection_announces_the_escalation(tmp_path):
    """rb-orchestrate maps a second re-seed to a rejection, so the id is accepted.

    It is announced on stderr rather than carried silently because the escalation
    is the orchestrator's ruling and not something the verdict file says. Measured
    on this run: the announcement is also what let a misapplication of that rule
    be caught afterwards, when the escalated scenario had never actually received
    a second re-seed verdict.
    """
    run = _run_with_verdict(tmp_path, {**REJECT_VERDICT, "verdict": "re-seed"}, sid="scn-042")
    proc = _dispatch(tmp_path, "score", str(run), run=run, RUBRICA_REJECT="scn-042")
    assert proc.returncode == 0
    assert "re-seed" in proc.stderr and "treat as a rejection" in proc.stderr


# --- the repair append --------------------------------------------------------
#
# The first of the two appends the design sanctions, and the one this script did
# not implement until a `check-refs` finding needed routing back to rb-challenge.
# It takes a file rather than a string so the appended text is a gate's own bytes.


def test_a_repair_dispatch_carries_the_gate_findings_verbatim(tmp_path):
    findings = tmp_path / "findings.txt"
    findings.write_text(
        "[refs] runs/r/05-verdicts/scn-042.json#/minimum_tool_calls_found: CANARY-GATE-FINDING\n"
    )
    run = _run_with_verdict(tmp_path, REJECT_VERDICT, sid="scn-042")
    _, _, prompt_file = _paths(
        _dispatch(
            tmp_path,
            "challenge",
            str(run),
            "scn-042",
            run=run,
            RUBRICA_FINDINGS_FILE=str(findings),
        )
    )
    assert "CANARY-GATE-FINDING" in Path(prompt_file).read_text()


def test_an_empty_findings_file_is_a_usage_error(tmp_path):
    """A repair dispatch carrying nothing is indistinguishable from a first one.

    Measured on the parsec run: a plain challenge re-dispatch found a complete
    verdict already in its one `writes` slot and correctly declined to re-judge,
    so the repair was a silent no-op. Exit 2 rather than a quiet no-append.
    """
    empty = tmp_path / "empty.txt"
    empty.write_text("")
    run = _run_with_verdict(tmp_path, REJECT_VERDICT, sid="scn-042")
    proc = _dispatch(
        tmp_path, "challenge", str(run), "scn-042", run=run, RUBRICA_FINDINGS_FILE=str(empty)
    )
    assert proc.returncode == 2
    assert "empty or missing" in proc.stderr


def test_no_findings_file_means_no_repair_block(tmp_path):
    run = _run_with_verdict(tmp_path, REJECT_VERDICT, sid="scn-042")
    _, _, prompt_file = _paths(_dispatch(tmp_path, "challenge", str(run), "scn-042", run=run))
    assert "A gate reported findings" not in Path(prompt_file).read_text()


def test_nothing_check_refs_reads_is_ever_denied(tmp_path):
    """The guard that would have caught two wrong denies, derived from refs.py.

    Four skills' contracts oblige them to invoke `check-refs`, and that subprocess
    runs inside the member's sandbox. So denying an artifact hides it from the
    *checker* as well, and bubblewrap masks a denied path to a character device --
    neither absent nor readable.

    MEASURED on 2026-08-13: with `$RUN/05-verdicts` denied to `instantiate`, the
    scn-005 re-seed's own `check-refs` reported ten fabricated "instance scn-XXX has
    no verdict" findings while the identical command outside the sandbox exited 0.
    That is the `1`-naming-the-wrong-artifact failure this repository already
    records for an unreadable `01-claims/`. `07-report.json` was the same mistake
    unbitten: `refs.py` reads it at :115 and :1279, and no run had reached smoke.

    Asserting against `refs._readable_targets` rather than a hand-list means a
    future check-refs that starts reading `decisions.md` fails this test instead of
    silently fabricating findings in a live dispatch.

    **It has to run against a populated run, and the first version did not.**
    `_readable_targets` enumerates instances and verdicts with `list_json`, so on an
    empty directory those contribute nothing and a `05-verdicts` deny sails through
    — measured: restoring that exact deny left this test green. That is the
    fixture-cannot-reach weakness, so the fixture is now a full toy run carrying
    real verdict files.
    """
    from rubrica.paths import RunPaths
    from rubrica.refs import _readable_targets
    from tests.toy import build_toy_run

    # upto=None builds through challenge, so 05-verdicts/ and 04-instances/ are
    # populated and reachable by _readable_targets.
    run_paths = build_toy_run(tmp_path / "runs")
    run = run_paths.root
    perms, sandbox, _ = _paths(_dispatch(tmp_path, "instantiate", str(run), "scn-001", run=run))
    resolved = run.resolve()

    denied_run_paths = {
        Path(p) for p in sandbox["sandbox"]["filesystem"]["denyRead"] if str(resolved) in p
    }
    # permissions.deny carries the same intent in "Read(/abs)" form
    denied_run_paths |= {
        Path(r[len("Read(/") : -1])
        for r in perms["permissions"]["deny"]
        if r.startswith("Read(/") and str(resolved) in r and not r.endswith("/**)")
    }

    read_by_check_refs = {p.resolve() for p in _readable_targets(RunPaths(resolved))}
    for denied in denied_run_paths:
        for target in read_by_check_refs:
            assert denied != target and denied not in target.parents, (
                f"{denied} is denied but check-refs reads {target}; a stage that invokes "
                "check-refs will get fabricated findings about what it cannot see"
            )


# --- the output-token cap, and the transcript that must not be overwritten -----
#
# Both halves come out of one failure. On 2026-08-25 `propose` round 2 died with
# "Claude's response exceeded the 32000 output token maximum" after 3.57 USD and
# 31 minutes, having written nothing; and because transcripts are named by stage
# rather than by attempt, round 2's transcript landed on round 1's path and the
# only per-attempt record of that failure went with it.
#
# The cap half is not about headroom -- the batch partition is what bounds the
# write. It is about a declared dependency: the number was Claude Code's own
# default, so the value a run ran under was not recoverable from this repository
# afterwards.
#
# These tests drive the script rather than grepping it, on the source-grep rule
# this module's docstring sets out. The cap tests put a stub `claude` first on PATH
# and read the environment the harness actually spawned it with; the transcript
# tests use the script's own naming, through RUBRICA_PRINT_TRANSCRIPT and through
# two real invocations of the stub.
#
# Measured in both directions before committing, each mutation made in place in
# the script and reverted after:
#
#   export line deleted            declares red (sees UNSET); overridable green,
#                                  for the reason its own docstring records
#   export made unconditional      overridable red (sees the constant, not 4242)
#   collision block deleted        both re-dispatch tests red; unsuffixed green
#   collision made unconditional   unsuffixed red; both re-dispatch tests green
#   print block moved above the    the naming test red -- it is the mode
#     collision block              reporting a path the dispatch would not use
#   export moved below the         declares red: the line reads exactly as it
#     `| tee` pipeline             should, and governs nothing. This is the form
#                                  the real regression takes, and the source-grep
#                                  assertion this test replaced stays green
#                                  through it
#   export moved below `cd "$RUN"`, green, and correctly so -- it still governs the
#     but still above `claude`     dispatch, so the test is not position-sensitive
#                                  for its own sake
#   either comment reworded        all green
#
# A mutation that only broke the syntax cannot be mistaken for a test that saw the
# change: every helper here asserts the script exited 0 and reports its stderr, so
# a bash parse error fails on that assertion instead. The one mutation that moved
# whole blocks around was additionally checked with `bash -n` before running.

STUB_CLAUDE = """#!/usr/bin/env bash
# Stand-in for the model dispatch. Records the environment and the argv the
# harness spawned it with, prints stream-json lines so `tee` has bytes to write,
# and exits 0 without a model.
printf '%s\\n' "${CLAUDE_CODE_MAX_OUTPUT_TOKENS-UNSET}" >> "$STUB_ENV_RECORD"
# NUL-separated and truncating rather than appending: the prompt is one argv
# entry containing newlines, so a line-per-arg record cannot be split back, and
# the retry test invokes the stub twice with only the last call under assertion.
printf '%s\\0' "$@" > "$STUB_ARGV_RECORD"
echo "{\\"stub_attempt\\": \\"${STUB_ATTEMPT:-1}\\"}"
# The closing summary reads the cost out of the transcript, so the stub has to
# emit the line a real `--output-format stream-json` dispatch ends with. Two ways
# to withhold it, because they fail the summary differently: STUB_NO_RESULT=1
# leaves a parseable transcript with no totals in it, STUB_TRUNCATED=1 leaves one
# jq cannot parse at all.
if [ "${STUB_TRUNCATED:-0}" = "1" ]; then
  # A dispatch killed mid-stream: the last line is half an object. jq cannot
  # parse the file at all, which is a different failure from a missing field.
  printf '%s' "{\\"type\\": \\"result\\", \\"total_cost_"
elif [ "${STUB_NO_RESULT:-0}" != "1" ]; then
  printf '{"type": "result", "total_cost_usd": %s, "num_turns": %s}\\n' \\
    "${STUB_COST:-1.25}" "${STUB_TURNS:-7}"
fi
"""


def _dispatch_with_stub_claude(tmp_path, *args, run=None, expect_exit=0, **env):
    """Run the harness for real against a stub `claude`, and return (proc, record).

    The stub sits first on PATH, so it is what `command -v claude` finds and what
    the dispatch line executes -- the script only prepends its own `.venv/bin`,
    which carries no `claude`. `record` is the file the stub appended its view of
    CLAUDE_CODE_MAX_OUTPUT_TOKENS to, one line per invocation; `_stub_argv` reads
    the sibling file holding the last invocation's argv.
    """
    bin_dir = tmp_path / "stub-bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "claude"
    stub.write_text(STUB_CLAUDE, encoding="utf-8")
    stub.chmod(0o755)
    record = tmp_path / "stub-env.txt"
    if run is None:
        run = tmp_path / "run"
        run.mkdir(exist_ok=True)
    base = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_MAX_OUTPUT_TOKENS"}
    proc = subprocess.run(
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env={
            **base,
            "PATH": _path_with(bin_dir, _bwrap_dir(tmp_path, works=True)),
            "RUBRICA_LAB": str(tmp_path / "lab"),
            "STUB_ENV_RECORD": str(record),
            "STUB_ARGV_RECORD": str(tmp_path / "stub-argv.bin"),
            **env,
        },
    )
    assert proc.returncode == expect_exit, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    return proc, record


def _stub_argv(tmp_path):
    """The argv of the last stub invocation, as a list of strings.

    Read from the NUL-separated record rather than reconstructed from the
    script's source: the mutation that matters here is a flag reaching the
    spawned process, and a source grep cannot tell a built-but-unpassed array
    from a passed one.
    """
    raw = (tmp_path / "stub-argv.bin").read_bytes()
    return [arg.decode("utf-8") for arg in raw.split(b"\0")[:-1]]


def test_the_dispatch_declares_the_output_token_cap(tmp_path):
    """The spawned process must see a concrete cap the caller did not have to set.

    The round loop's viability depended on a default belonging to another tool:
    unset in the environment and absent from this repository, so the value a run
    actually ran under was not recoverable afterwards. MEASURED on Claude Code
    2.1.247 with the variable unset, that default is not even one number: 32000
    for the id `aws/claude-sonnet-4-6` and 64000 for `claude-sonnet-5`, which is
    what `--model sonnet` resolved to. 32000 is exactly what killed propose round
    2, so which ceiling a run got was decided outside this repository.

    The assertion is on the *shape* of the value, not its digits: which number the
    script pins is a decision recorded in the script's own comment, and pinning it
    here as well would make a deliberate change a test failure rather than a
    review.
    """
    run = tmp_path / "run"
    run.mkdir()
    _, record = _dispatch_with_stub_claude(tmp_path, "propose", str(run), run=run)
    seen = record.read_text(encoding="utf-8").split()
    assert seen, "the stub dispatch recorded nothing; it was not executed"
    assert seen[0] != "UNSET", "the dispatch left the output-token cap to Claude Code's default"
    assert seen[0].isdigit() and int(seen[0]) > 0


def test_the_output_token_cap_is_overridable_from_the_environment(tmp_path):
    """Same shape as RUBRICA_MODEL and RUBRICA_EFFORT: a default in the script,
    overridable per dispatch, so a probe does not need the file edited.

    RUBRICA_BUDGET used to be named here as a third example and is not one any
    more -- it has no default, because a dollar ceiling nobody asked for is a
    barrier rather than a record. See the budget tests at the end of this module.

    The mutation this one catches is an unconditional `export VAR=<n>`, which
    would silently discard the value a probe passed in -- and the ceiling is
    precisely the thing this task had to probe. MEASURED green with the export
    line deleted altogether, since the caller's own value then reaches the
    dispatch untouched; that direction is what the test above holds.
    """
    run = tmp_path / "run"
    run.mkdir()
    _, record = _dispatch_with_stub_claude(
        tmp_path, "propose", str(run), run=run, CLAUDE_CODE_MAX_OUTPUT_TOKENS="4242"
    )
    assert record.read_text(encoding="utf-8").split() == ["4242"]


def _transcript_path_for(lab, stage="propose", slice_id=""):
    """The transcript path the script itself would choose, via its print mode.

    Shelling out rather than restating the naming rule, for the reason this
    module's docstring gives.
    """
    run = Path(lab).parent / "run"
    run.mkdir(parents=True, exist_ok=True)
    args = [str(SCRIPT), stage, str(run)] + ([slice_id] if slice_id else [])
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        env={**os.environ, "RUBRICA_LAB": str(lab), "RUBRICA_PRINT_TRANSCRIPT": "1"},
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    printed = proc.stdout.split()
    assert len(printed) == 1, f"print-transcript mode printed {printed!r}"
    return Path(printed[0])


def test_a_re_dispatch_does_not_overwrite_the_earlier_transcript(tmp_path):
    # MEASURED consequence, not a hypothetical: transcripts are named by stage,
    # so propose round 2 overwrote round 1's and destroyed the only per-attempt
    # evidence for the failure that motivated this whole change.
    lab = tmp_path / "lab"
    (lab / "transcripts").mkdir(parents=True)
    existing = lab / "transcripts" / "propose.jsonl"
    existing.write_text("round one\n", encoding="utf-8")
    # Drive the script's own naming logic rather than reimplementing it here.
    chosen = _transcript_path_for(lab, stage="propose", slice_id="")
    assert chosen != existing
    assert existing.read_text(encoding="utf-8") == "round one\n"


def test_a_first_dispatch_still_gets_the_unsuffixed_transcript_name(tmp_path):
    """The over-correction direction: suffixing unconditionally would rename every
    first attempt, and the slice id has to stay in the name either way -- the
    fan-out members' transcripts are told apart by nothing else."""
    lab = tmp_path / "lab"
    (lab / "transcripts").mkdir(parents=True)
    assert _transcript_path_for(lab, stage="propose") == lab / "transcripts" / "propose.jsonl"
    assert _transcript_path_for(lab, stage="extract", slice_id="api-json") == (
        lab / "transcripts" / "extract-api-json.jsonl"
    )


def test_a_re_dispatch_leaves_the_earlier_transcripts_bytes_intact(tmp_path):
    """The end-to-end half: two real invocations, both writing a transcript.

    The naming test above cannot see a `tee` that truncates, because print mode
    writes nothing. This one runs the dispatch line twice against the stub and
    reads both files afterwards, which is the form the real regression took.
    """
    run = tmp_path / "run"
    run.mkdir()
    first, _ = _dispatch_with_stub_claude(tmp_path, "propose", str(run), run=run, STUB_ATTEMPT="1")
    second, _ = _dispatch_with_stub_claude(tmp_path, "propose", str(run), run=run, STUB_ATTEMPT="2")
    # Which file each attempt wrote comes from the script's own closing summary,
    # so this test does not restate the naming rule either.
    paths = [_reported_transcript(proc) for proc in (first, second)]
    assert paths[0] != paths[1]
    assert '"stub_attempt": "1"' in paths[0].read_text(encoding="utf-8")
    assert '"stub_attempt": "2"' in paths[1].read_text(encoding="utf-8")
    assert len(list((tmp_path / "lab" / "transcripts").iterdir())) == 2


def _reported_transcript(proc):
    """The transcript path out of the script's closing summary ("transcript  <p>")."""
    for line in proc.stdout.splitlines():
        if line.startswith("transcript"):
            return Path(line.split(maxsplit=1)[1].strip())
    raise AssertionError(f"no transcript line in {proc.stdout!r}")


# ---------------------------------------------------------------------------
# The dollar ceiling: opt-in, and the cost reported either way.
#
# `--max-budget-usd` carried a default of 2 until this change, and a ceiling is
# not a neutral guard -- it kills the dispatch where it stands. MEASURED twice on
# real runs: `src/rubrica/summary.py`'s `orphaned_temp_files` docstring records a
# ceiling killing a reconcile pass mid-write, leaving a
# `02-scenarios.json.tmp.*` a human had to remove by hand, and the
# reconcile-subjects dispatch in issue #18 spent its whole ceiling before writing
# anything. Neither failure is legible from the run afterwards: a killed dispatch
# and a refusing one both leave no artifact.
#
# So the default is now no ceiling, and the cost is reported on every dispatch
# instead. That is strictly more information than a silent default ever gave --
# a run under a ceiling of 2 never said so anywhere either.
# ---------------------------------------------------------------------------


def test_no_dollar_ceiling_is_imposed_unless_the_caller_asks_for_one(tmp_path):
    """The default direction: the flag must be absent from argv, not merely large.

    Passing a very high number instead would satisfy any assertion about the
    dispatch surviving, and would still cap a run at whatever number this file
    happened to pick. The absence is the property.
    """
    run = tmp_path / "run"
    run.mkdir()
    _dispatch_with_stub_claude(tmp_path, "propose", str(run), run=run)
    assert "--max-budget-usd" not in _stub_argv(tmp_path)


def test_a_requested_dollar_ceiling_reaches_the_dispatch(tmp_path):
    """The opt-in direction, asserted on the pairing rather than on presence.

    A flag present with the wrong value -- the old default, say -- would pass a
    membership check on the flag name alone, so this pins the value that follows
    it.
    """
    run = tmp_path / "run"
    run.mkdir()
    _dispatch_with_stub_claude(tmp_path, "propose", str(run), run=run, RUBRICA_BUDGET="7.5")
    argv = _stub_argv(tmp_path)
    assert "--max-budget-usd" in argv
    assert argv[argv.index("--max-budget-usd") + 1] == "7.5"


def test_an_empty_budget_variable_asks_for_no_ceiling(tmp_path):
    """`RUBRICA_BUDGET=` must mean unset, matching how RUBRICA_LIVE reads.

    The mutation this catches is `${RUBRICA_BUDGET+x}` or a bare `-z` test
    inverted: either would pass an empty string to `--max-budget-usd`, which
    Claude Code rejects as a usage error. A caller clearing the variable to drop
    a ceiling would then get a dispatch that never starts.
    """
    run = tmp_path / "run"
    run.mkdir()
    _dispatch_with_stub_claude(tmp_path, "propose", str(run), run=run, RUBRICA_BUDGET="")
    assert "--max-budget-usd" not in _stub_argv(tmp_path)


def _summary_field(proc, label):
    """The closing summary's value for a `<label>  <value>` line."""
    for line in proc.stdout.splitlines():
        if line.startswith(label):
            return line[len(label) :].strip()
    raise AssertionError(f"no {label!r} line in {proc.stdout!r}")


def test_the_closing_summary_reports_what_the_dispatch_cost(tmp_path):
    """Removing the ceiling only holds if the number it hid becomes visible.

    Both figures are asserted because either alone is misleading: a cost with no
    turn count cannot be compared against another dispatch of the same stage, and
    issue #18's evidence was exactly the pair (38 turns, $3.72, no artifact).
    """
    run = tmp_path / "run"
    run.mkdir()
    proc, _ = _dispatch_with_stub_claude(
        tmp_path, "propose", str(run), run=run, STUB_COST="3.716", STUB_TURNS="38"
    )
    reported = _summary_field(proc, "cost")
    assert "3.716" in reported
    assert "38" in reported


def test_the_closing_summary_names_which_ceiling_was_in_force(tmp_path):
    """A cost figure is only readable next to the ceiling it ran under.

    Asserted in both directions in one test because the two strings have to
    differ: a summary printing the same text whether or not a ceiling was set
    would satisfy either assertion alone.
    """
    run = tmp_path / "run"
    run.mkdir()
    without, _ = _dispatch_with_stub_claude(tmp_path, "propose", str(run), run=run)
    with_ceiling, _ = _dispatch_with_stub_claude(
        tmp_path, "propose", str(run), run=run, RUBRICA_BUDGET="10"
    )
    assert "10" in _summary_field(with_ceiling, "cost")
    assert "10" not in _summary_field(without, "cost")


def test_a_dispatch_that_reported_no_cost_says_so_rather_than_printing_null(tmp_path):
    """A transcript with no result line is a killed dispatch, not a crash here.

    Two predicates, because the field being absent has two wrong renderings and
    only one right one. Dropping jq's `// ""` defaults makes the summary read
    `cost $null over null turns`, which is a number-shaped answer to a question
    with no answer -- the class this project calls a reasoned figure presented as
    an observed one. Reporting nothing at all is the other.

    MEASURED both directions: deleting either default turns the `null` assertion
    red; deleting the whole cost line turns the other one red.
    """
    run = tmp_path / "run"
    run.mkdir()
    proc, _ = _dispatch_with_stub_claude(tmp_path, "propose", str(run), run=run, STUB_NO_RESULT="1")
    assert proc.returncode == 0
    reported = _summary_field(proc, "cost")
    assert reported, "the summary dropped the cost line entirely"
    assert "null" not in reported


def test_a_transcript_truncated_mid_stream_does_not_take_the_exit_code_with_it(tmp_path):
    """The guard that matters most, because it is the exit-code contract's.

    `set -euo pipefail` is on and the summary's `jq` runs in a command
    substitution, so an unparseable transcript without `|| true` makes the script
    exit non-zero *after* a dispatch that may well have written a good artifact.
    The orchestrator branches on that code, and this failure would arrive as a `2`
    -- a stage defect surfacing as an unreadable run, which the contract forbids
    outright.

    A missing field cannot reach this: jq parses that file fine. It takes a
    half-written final line, which is exactly what a killed dispatch leaves, and
    is why the stub can emit one.

    MEASURED: dropping `|| true` turns this red with the script exiting 5.
    """
    run = tmp_path / "run"
    run.mkdir()
    proc, _ = _dispatch_with_stub_claude(tmp_path, "propose", str(run), run=run, STUB_TRUNCATED="1")
    assert proc.returncode == 0
    assert _summary_field(proc, "cost")


# ---------------------------------------------------------------------------
# The sandbox probe.
#
# MEASURED 2026-09-01, three dispatches replicating this script's flags at Claude
# Code 2.1.252: a stage can enumerate `01-claims/` with the sandbox live AND with
# no sandbox block at all -- `ls` and `find` are auto-approved as read-only in both
# -- and can enumerate it in neither when a sandbox is configured that `bwrap`
# cannot engage, because every Bash command then dies at the bwrap layer, the
# stage's own `rubrica validate` and `check-refs` included.
#
# That third state is what cost issue #18 38 turns and $3.72 for no artifact. It is
# also invisible: `failIfUnavailable` makes the sandbox loud about not engaging, but
# the dispatch proceeds anyway and exits 0. So the script probes first and drops the
# block rather than handing a stage a shell where nothing runs.
#
# The probe is the `--proc` form on purpose. The same command without `--proc`
# succeeds on the pod that motivated this, so a smoke test omitting it reports a
# working sandbox where there is none.
# ---------------------------------------------------------------------------


def test_a_working_probe_leaves_the_sandbox_block_in_place(tmp_path):
    """The non-degraded machine must be unaffected, block and failure mode intact.

    `failIfUnavailable` is asserted alongside `enabled` because a probe that
    replaced the block with a quieter one would satisfy a check on `enabled` alone
    while removing the signal that layer is not engaging.
    """
    run = tmp_path / "run"
    run.mkdir()
    _, sandbox, _ = _paths(_dispatch(tmp_path, "propose", str(run), run=run))
    assert sandbox["sandbox"]["enabled"] is True
    assert sandbox["sandbox"]["failIfUnavailable"] is True


def test_a_failed_probe_drops_the_block_instead_of_dispatching_into_a_dead_shell(tmp_path):
    """The degraded machine: an empty user scope, which is what `NO_SANDBOX` writes.

    Asserted as the absence of the key rather than `enabled: false`, because a
    `sandbox` block present in this scope is the thing that was measured to stop
    the *other* scope's deny rules from being enforced.
    """
    run = tmp_path / "run"
    run.mkdir()
    proc = _dispatch(
        tmp_path,
        "propose",
        str(run),
        run=run,
        PATH=_path_with(_bwrap_dir(tmp_path, works=False)),
    )
    _, sandbox, _ = _paths(proc)
    assert sandbox == {}


def test_the_probe_asks_bwrap_to_mount_proc_which_is_what_discriminates(tmp_path):
    """The fault is invisible to the probe form that omits `--proc`.

    Issue #18 records it: on the pod, `bwrap --unshare-all --dev-bind / / true` exits
    0 while the same command with `--proc /proc` exits 1, so a smoke test without it
    reports a working sandbox where there is none. The stub carries that asymmetry,
    so a probe dropping `--proc` sees success, leaves the block in place, and fails
    here.

    MEASURED: dropping `--proc` from the probe was green against a stub that failed
    unconditionally. That is why the stub imitates the pod instead, and why this test
    is separate from the fallback tests it would otherwise duplicate.
    """
    run = tmp_path / "run"
    run.mkdir()
    _, sandbox, _ = _paths(
        _dispatch(
            tmp_path,
            "propose",
            str(run),
            run=run,
            PATH=_path_with(_bwrap_dir(tmp_path, works=False)),
        )
    )
    assert sandbox == {}, "the probe did not ask bwrap for --proc"


def test_the_fallback_says_which_of_the_two_reasons_dropped_the_sandbox(tmp_path):
    """A dropped sandbox is a changed measurement, so it may not be silent.

    Both reasons in one test because they have to be distinguishable: a banner
    printing the same words for a deliberate override and for a broken machine
    would tell a reader nothing they could act on, and would satisfy either
    assertion alone.
    """
    run = tmp_path / "run"
    run.mkdir()
    broken = _dispatch(
        tmp_path, "propose", str(run), run=run, PATH=_path_with(_bwrap_dir(tmp_path, works=False))
    )
    asked = _dispatch(tmp_path, "propose", str(run), run=run, RUBRICA_NO_SANDBOX="1")
    assert "bwrap" in broken.stderr
    assert "RUBRICA_NO_SANDBOX" in asked.stderr
    assert "bwrap" not in asked.stderr


def test_the_probes_own_output_is_kept_where_it_can_be_read_afterwards(tmp_path):
    """stderr scrolls away; the reason a recording lost its sandbox must not.

    The file is asserted to hold the probe's actual message rather than merely to
    exist, because an empty file written unconditionally would pass the weaker
    check and leave the diagnosis nowhere.
    """
    run = tmp_path / "run"
    run.mkdir()
    _dispatch(
        tmp_path, "propose", str(run), run=run, PATH=_path_with(_bwrap_dir(tmp_path, works=False))
    )
    logs = sorted((tmp_path / "lab").glob("sandbox-probe-*"))
    assert logs, f"no probe log under {tmp_path / 'lab'}"
    assert "Operation not permitted" in logs[0].read_text(encoding="utf-8")


def test_requiring_the_sandbox_turns_a_failed_probe_into_a_refusal(tmp_path):
    """For a measured run, losing the isolation layer beats running without knowing.

    Exit 2 rather than 1: the exit-code contract reserves 1 for a repairable stage
    defect worth one retry, and no retry fixes a machine whose kernel will not give
    the sandbox its capabilities.

    The second assertion is the one that matters -- refusing after spending a
    dispatch would defeat the point.
    """
    run = tmp_path / "run"
    run.mkdir()
    proc, _ = _dispatch_with_stub_claude(
        tmp_path,
        "propose",
        str(run),
        run=run,
        expect_exit=2,
        RUBRICA_REQUIRE_SANDBOX="1",
        PATH=_path_with(
            tmp_path / "stub-bin", _bwrap_dir(tmp_path, works=False), tmp_path / "bwrap-ok"
        ),
    )
    assert "bwrap" in proc.stderr
    assert not (tmp_path / "stub-argv.bin").exists(), "it dispatched before refusing"


def test_the_closing_summary_records_which_sandbox_the_dispatch_ran_under(tmp_path):
    """Which configuration produced a recording is not reconstructable afterwards.

    Both directions, because a summary naming the sandbox only when it is present
    reads identically to one that never mentions it -- and the degraded case is the
    one a reader needs told.

    The count assertion is here because its absence let a real defect through: the
    line was first composed as `${VAR:+off -- $VAR}${VAR:-on}`, and `${VAR:-on}`
    expands to VAR when VAR is set, so the reason printed twice. A test checking
    only that "off" appeared was green on it, and reading the output caught it.
    """
    run = tmp_path / "run"
    run.mkdir()
    on, _ = _dispatch_with_stub_claude(tmp_path, "propose", str(run), run=run)
    off, _ = _dispatch_with_stub_claude(
        tmp_path,
        "propose",
        str(run),
        run=run,
        PATH=_path_with(
            tmp_path / "stub-bin", _bwrap_dir(tmp_path, works=False), tmp_path / "bwrap-ok"
        ),
    )
    assert _summary_field(on, "sandbox") == "on"
    reported = _summary_field(off, "sandbox")
    assert reported.startswith("off -- ")
    assert reported.count("cannot engage") == 1, f"the reason is repeated: {reported!r}"
