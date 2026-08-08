"""The agent roster boundary: loading, substitution, and the preflight.

Everything about smoke that does not touch a subprocess. A malformed roster is a
usage error rather than a finding, which is the one place in the project where a
schema failure does not become exit 1: a person wrote this file, so there is no
stage to send a repair prompt to.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from testgen.errors import UsageError
from testgen.smoke import REQUIRED_ROLES, ROLES, AgentSpec, load_agents, preflight, substitute
from tests.builders import minimal_agents


def _roster(tmp_path, payload=None):
    path = tmp_path / "agents.json"
    path.write_text(json.dumps(payload if payload is not None else minimal_agents()), "utf-8")
    return path


# -- load_agents --------------------------------------------------------------


def test_a_valid_roster_loads_all_three_roles(tmp_path):
    specs = load_agents(_roster(tmp_path))
    assert [s.role for s in specs] == list(ROLES)
    assert specs[0].command == ("true",)
    assert specs[0].notes == "no tools"


def test_the_agent_timeout_defaults_to_the_one_the_package_declares(tmp_path):
    """emit writes AGENT_TIMEOUT_SEC into task.toml for Harbor.

    Using a different default here would mean a package that times out locally
    does not time out on the platform, or the reverse -- the same suite scoring
    two ways depending on who ran it.
    """
    from testgen.emit import AGENT_TIMEOUT_SEC

    assert load_agents(_roster(tmp_path))[0].timeout_sec == AGENT_TIMEOUT_SEC


def test_an_explicit_timeout_wins(tmp_path):
    payload = minimal_agents()
    payload["agents"][0]["timeout_sec"] = 12.5
    assert load_agents(_roster(tmp_path, payload))[0].timeout_sec == 12.5


def test_an_absent_roster_is_a_usage_error(tmp_path):
    with pytest.raises(UsageError, match="unusable agent roster"):
        load_agents(tmp_path / "nope.json")


def test_a_roster_that_fails_the_schema_is_a_usage_error(tmp_path):
    payload = minimal_agents()
    payload["agents"][0]["role"] = "sidekick"
    with pytest.raises(UsageError, match="sidekick"):
        load_agents(_roster(tmp_path, payload))


def test_a_roster_with_an_empty_executable_is_a_usage_error(tmp_path):
    payload = minimal_agents()
    payload["agents"][0]["command"] = ["", "--flag"]
    with pytest.raises(UsageError):
        load_agents(_roster(tmp_path, payload))


def test_a_duplicated_role_is_a_usage_error(tmp_path):
    """Two under_test agents make mean_reward_by_role ambiguous.

    The schema cannot express it: uniqueItems compares whole objects, and two
    entries differing only by model are distinct objects.
    """
    payload = minimal_agents()
    payload["agents"].append({"role": "under_test", "model": "other", "command": ["true"]})
    with pytest.raises(UsageError, match="under_test"):
        load_agents(_roster(tmp_path, payload))


def test_a_roster_missing_a_required_role_still_loads(tmp_path):
    """Deliberately not a usage error.

    Dropping the oracle is a cost decision a person is allowed to make, and the
    run still produces real data. smoke reports it as a finding and refuses to
    call the result healthy -- exit 1 with the data, not exit 2 with nothing.
    """
    payload = minimal_agents()
    payload["agents"] = [a for a in payload["agents"] if a["role"] != "oracle"]
    specs = load_agents(_roster(tmp_path, payload))
    assert "oracle" not in {s.role for s in specs}
    assert "oracle" in REQUIRED_ROLES


# -- substitute ---------------------------------------------------------------


def test_every_placeholder_is_filled():
    argv = substitute(
        ("run", "--task", "{task_dir}", "--logs", "{logs_dir}", "--id", "{scenario_id}"),
        task_dir=Path("/runs/r/06-suite/scn-001"),
        logs_dir=Path("/runs/r/measurement/smoke/oracle/scn-001/agent"),
        scenario_id="scn-001",
    )
    assert argv == (
        "run",
        "--task",
        "/runs/r/06-suite/scn-001",
        "--logs",
        "/runs/r/measurement/smoke/oracle/scn-001/agent",
        "--id",
        "scn-001",
    )


def test_a_literal_brace_survives():
    """str.replace, not str.format.

    A JSON snippet passed as a flag value is an ordinary thing to put in an argv,
    and str.format raises KeyError or ValueError on it. A roster that works from a
    shell must not break because one argument held a brace.
    """
    argv = substitute(
        ("run", '--extra={"temperature": 0}', "{scenario_id}"),
        task_dir=Path("/t"),
        logs_dir=Path("/l"),
        scenario_id="scn-001",
    )
    assert argv == ("run", '--extra={"temperature": 0}', "scn-001")


def test_an_unknown_placeholder_is_left_alone():
    """It may mean something to the command itself; guessing would corrupt it."""
    assert substitute(
        ("run", "{model}"), task_dir=Path("/t"), logs_dir=Path("/l"), scenario_id="s"
    ) == ("run", "{model}")


def test_a_placeholder_appearing_twice_is_filled_twice():
    assert substitute(
        ("{scenario_id}", "{scenario_id}-out"),
        task_dir=Path("/t"),
        logs_dir=Path("/l"),
        scenario_id="s",
    ) == ("s", "s-out")


# -- preflight ----------------------------------------------------------------


def test_preflight_resolves_the_executable_to_an_absolute_path():
    """run_agent sets cwd to the task directory.

    A relative command that resolved from the repository root would not exist by
    the time it ran, so the resolved path is substituted back into command[0].
    """
    spec = AgentSpec(role="under_test", model="m", command=("true", "--x"))
    resolved = preflight((spec,))[0]
    assert Path(resolved.command[0]).is_absolute()
    assert Path(resolved.command[0]).resolve() == Path(shutil.which("true")).resolve()
    assert resolved.command[1:] == ("--x",)


def test_preflight_refuses_a_command_that_cannot_run():
    """Before anything runs, not on task 5 of 8.

    Discovering the typo mid-run wastes every agent invocation before it and
    leaves a half-populated report on disk.
    """
    spec = AgentSpec(role="oracle", model="m", command=("definitely-not-a-real-binary-xyz",))
    with pytest.raises(UsageError, match="not runnable"):
        preflight((spec,))


def test_preflight_refuses_a_placeholder_in_the_executable_and_says_why():
    """The documented restriction, stated where an operator will hit it.

    `substitute` fills placeholders in every argv element, but it runs per (role,
    task) inside the agent loop -- long after the roster has to be accepted or
    refused. So the executable must resolve as written, and the message has to say
    so: letting `{task_dir}/run-agent` through would move the failure into
    subprocess.run, where a FileNotFoundError becomes an exit-1 stage finding
    about a run whose artifacts are fine. agents-0.1.json's `command` description
    states the same restriction.
    """
    spec = AgentSpec(role="under_test", model="m", command=("{task_dir}/run-agent", "--x"))
    with pytest.raises(UsageError, match="before .task_dir.") as excinfo:
        preflight((spec,))
    assert "only in the arguments after it" in str(excinfo.value)


def test_the_schema_states_the_same_restriction_preflight_enforces():
    """One rule, and the roster author reads the schema, not preflight's docstring."""
    from testgen.artifacts import read_json
    from testgen.validate import schema_dir

    description = read_json(schema_dir() / "agents-0.1.json")["properties"]["agents"]["items"][
        "properties"
    ]["command"]["description"]
    assert "runnable as written" in description
    assert "only in the arguments after the executable" in description


def test_preflight_names_the_role_that_is_broken():
    specs = (
        AgentSpec(role="weak_baseline", model="m", command=("true",)),
        AgentSpec(role="oracle", model="m", command=("nope-xyz",)),
    )
    with pytest.raises(UsageError, match="oracle"):
        preflight(specs)
