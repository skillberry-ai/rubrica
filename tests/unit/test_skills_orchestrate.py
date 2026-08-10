"""tg-orchestrate's contract, and the control-flow rules it must state.

The orchestrator is the one skill whose defects are silent in a *successful*
run: an orchestrator that passes extra context into a dispatch, or retries three
times, or treats an exit 2 as repairable, produces artifacts that all validate.
So these checks are about the rules being present in the prompt, and the live
exercise is a whole-pipeline run.
"""

from __future__ import annotations

from testgen.cli import subcommand_names
from testgen.paths import STAGES
from testgen.skills import CODE_ONLY_STAGES, ORCHESTRATOR, SECTIONS, load, skills_dir

SKILL = skills_dir() / ORCHESTRATOR / "SKILL.md"


def test_it_declares_no_stage_because_it_dispatches_them():
    contract = load(SKILL).contract
    assert "stage" not in contract
    assert "schemas" not in contract


def test_it_writes_the_decisions_log():
    assert load(SKILL).contract["writes"] == ["decisions"]


def test_it_has_the_five_sections():
    assert all(section in load(SKILL).headings for section in SECTIONS)


def test_it_invokes_every_subcommand_the_loop_needs():
    """Not every subcommand -- compare-gold, diff-runs and sample-for-review are
    measurement tools the orchestrator does not run. But every one it does
    declare must be real, which check_contract already enforces; this pins the
    ones the loop cannot work without.
    """
    invokes = set(load(SKILL).contract["invokes"])
    required = {
        "check-skills",
        "validate",
        "check-refs",
        "record-stage",
        "decide",
        "dedupe-candidates",
        "emit",
        "smoke",
    }
    assert required <= invokes, f"missing: {sorted(required - invokes)}"
    assert invokes <= set(subcommand_names())


def test_it_names_every_stage_it_dispatches():
    """Derived from STAGES, so adding a stage fails here until the loop mentions
    it. The two code-only stages are named as well: intake mints the run and
    smoke scores it, and an orchestrator that does not know they exist skips them.
    """
    body = load(SKILL).body
    for stage in STAGES:
        if stage in CODE_ONLY_STAGES:
            assert stage in body, f"the loop never mentions the code stage {stage!r}"
        else:
            assert f"tg-{stage}" in body, f"the loop never dispatches tg-{stage}"


def test_it_states_all_three_exit_codes_and_what_each_means():
    """The branch. An orchestrator that treats 2 as repairable spends its one
    repair attempt on a misconfigured harness and then halts anyway, with the
    real cause buried.
    """
    body = load(SKILL).body
    for code in ("0", "1", "2"):
        assert code in body
    lowered = body.lower()
    assert "exit" in lowered
    assert "misconfigur" in lowered, "exit 2's meaning must be stated"


def test_it_states_the_repair_is_bounded_to_one_attempt():
    body = load(SKILL).body.lower()
    assert "once" in body or "one repair" in body
    assert "halt" in body


def test_it_states_the_three_things_a_dispatch_receives():
    """The contract. An orchestrator that threads context through has removed
    the isolation the fan-out design was chosen for, and every artifact still
    validates.
    """
    body = load(SKILL).body.lower()
    assert "run directory" in body
    assert "stage name" in body or "its stage" in body
    assert "skill" in body


def test_it_names_the_three_human_gates_and_the_no_gate_flag():
    body = load(SKILL).body
    assert "--no-gate" in body
    lowered = body.lower()
    assert lowered.count("gate") >= 4, "three gates and the flag must each be described"


def test_it_states_that_a_rejection_does_not_loop_back_to_propose():
    """Deferred on purpose: looping after instantiation makes run cost unbounded.
    An orchestrator that loops instead of reporting an honest hole turns a
    bounded run into an open-ended one.
    """
    body = load(SKILL).body.lower()
    assert "reject" in body
    assert "hole" in body


def test_it_records_each_stage_and_each_decision():
    body = load(SKILL).body
    assert "record-stage" in body
    assert "skill_sha256" in body or "skill hash" in body.lower()
    assert "decide" in body
