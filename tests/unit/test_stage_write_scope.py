"""`scripts/stage-write-scope.py`: a stage's write grant, from its own contract.

The script exists because `dispatch-stage.sh` granted `Write(/$RUN/**)`, so a
stage could write anything inside the run -- and one did, putting a
`compute_weights.py` helper in the run root: the unfiltered stray write
(docs/design/findings.md). The ruling was that a stage's `writes` is the whole
truth about what appears in `$RUN` and that the sandbox scope enforces it, so what
these tests hold is that the resolution is right for every stage the harness
dispatches, and that it never widens back to the run.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from rubrica.paths import STAGES
from rubrica.skills import SKILL_PREFIX, load, skills_dir
from tests.toy import build_toy_run

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "stage-write-scope.py"

# Every stage dispatch-stage.sh can dispatch: those with a skill file. Derived
# rather than listed, so a stage added later is covered without anyone editing a
# roster -- the same reasoning skills.expected_skill_names() rests on.
DISPATCHABLE = tuple(
    stage for stage in STAGES if (skills_dir() / f"{SKILL_PREFIX}{stage}" / "SKILL.md").is_file()
)


def _scope(run_dir, stage, slice_id=None) -> subprocess.CompletedProcess:
    argv = [sys.executable, str(SCRIPT), str(run_dir), stage]
    if slice_id is not None:
        argv.append(slice_id)
    return subprocess.run(argv, capture_output=True, text=True)


def test_the_dispatchable_roster_is_not_empty():
    """A guard on the derivation: an empty roster would make every parametrized
    test below vacuously green."""
    assert len(DISPATCHABLE) >= 8, DISPATCHABLE


@pytest.mark.parametrize("stage", DISPATCHABLE)
def test_every_dispatchable_stage_resolves_to_at_least_one_path(tmp_path, stage):
    """A stage that resolved to nothing would be granted nothing and could not write
    its artifact, so the dispatch would fail mid-turn rather than cleanly. The
    harness refuses an empty scope for that reason; this is the other half of it."""
    result = _scope(tmp_path, stage, "probe-id")
    assert result.returncode == 0, result.stderr
    assert result.stdout.split(), f"{stage} resolved to no writable path"


@pytest.mark.parametrize("stage", DISPATCHABLE)
def test_no_stage_is_granted_the_run_directory_itself(tmp_path, stage):
    """The regression that matters. A resolution collapsing to the run root would
    reinstate `Write(/$RUN/**)` while looking derived -- and one draft did exactly
    that: `score_part(1)` is `<dir>/round-1.json`, so walking up two levels from it
    reached the run root. The script now refuses rather than widening, and this is
    what would catch a future artifact whose depth differs again.
    """
    result = _scope(tmp_path, stage, "probe-id")
    assert result.returncode == 0, result.stderr
    for line in result.stdout.split():
        assert line not in (f"{tmp_path}/**", f"{tmp_path}", f"{tmp_path}/"), (
            f"{stage} was granted the whole run directory"
        )
        assert Path(line.removesuffix("/**")) != tmp_path


@pytest.mark.parametrize("stage", DISPATCHABLE)
def test_every_resolved_path_is_inside_the_run(tmp_path, stage):
    result = _scope(tmp_path, stage, "probe-id")
    for line in result.stdout.split():
        assert line.startswith(f"{tmp_path}/"), line


@pytest.mark.parametrize("stage", DISPATCHABLE)
def test_the_resolution_covers_exactly_the_contract_s_writes(tmp_path, stage):
    """The resolution is of the contract, so its size follows the contract's.

    Not a path-by-path comparison, which would restate RunPaths in the test: what is
    asserted is that every declared write contributes, and that nothing else does.
    `rb-instantiate` declares three and resolves to three; a stage declaring one
    cannot resolve to two.
    """
    writes = load(skills_dir() / f"{SKILL_PREFIX}{stage}" / "SKILL.md").contract["writes"]
    result = _scope(tmp_path, stage, "probe-id")
    assert len(result.stdout.split()) == len(set(writes)), (
        f"{stage} declares {writes} and resolved to {result.stdout.split()}"
    )


def test_a_fanout_member_is_scoped_to_its_own_slice(tmp_path):
    """The fan-out isolation rule, enforced by the grant rather than only stated in
    prose: a member gets its own slice's path and no sibling's."""
    result = _scope(tmp_path, "extract", "art-1")
    assert result.stdout.split() == [f"{tmp_path}/01-claims/art-1.json"]
    assert "art-2" not in result.stdout


def test_a_round_parameterised_stage_pins_the_round_when_a_plan_exists(tmp_path):
    """`score` writes `03-score/round-N.json` and the harness is given no round, so
    the round comes from the latest batch plan on disk -- which `propose-batches`
    always writes before either `propose` or `score` is dispatched for the round."""
    run = build_toy_run(tmp_path, upto="propose")
    assert run.batches_rounds() == [1]
    assert _scope(run.root, "score").stdout.split() == [f"{run.root}/03-score/round-1.json"]
    assert _scope(run.root, "propose", "b01").stdout.split() == [
        f"{run.root}/02-scenarios/round-1/b01.json"
    ]


def test_a_round_parameterised_stage_falls_back_to_the_artifact_directory(tmp_path):
    """With no plan on disk the round cannot be pinned, and the fallback is the
    artifact's own tree rather than an error. A grant that is too tight breaks the
    dispatch it was meant to protect, and a denied write surfaces mid-turn as a model
    working around it rather than as a clean failure -- while the directory grant
    still refuses everything else in the run, which is what the ruling asked for.
    """
    assert _scope(tmp_path, "score").stdout.split() == [f"{tmp_path}/03-score/**"]
    assert _scope(tmp_path, "propose", "b01").stdout.split() == [f"{tmp_path}/02-scenarios/**"]


def test_a_missing_slice_id_falls_back_to_the_directory_rather_than_guessing(tmp_path):
    """An operator running the harness by hand, or a barrier pass with no id. Which
    file inside the directory the dispatch will write is not knowable here, so the
    directory is the honest grant."""
    assert _scope(tmp_path, "extract").stdout.split() == [f"{tmp_path}/01-claims/**"]


def test_a_code_stage_is_a_usage_error_and_not_an_empty_scope(tmp_path):
    """`intake` has no skill, so asking about it is a caller bug. Exit 2 rather than
    an empty scope, which the harness would otherwise read as a stage allowed to
    write nothing -- and which would then fail as a denied write mid-dispatch."""
    result = _scope(tmp_path, "intake")
    assert result.returncode == 2
    assert result.stdout.strip() == ""
    assert "no skill for stage" in result.stderr


def test_the_output_is_sorted_and_free_of_duplicates(tmp_path):
    """The grant list ends up in a settings file the harness writes per dispatch, and
    two runs of the same stage must produce the same file."""
    first = _scope(tmp_path, "instantiate", "scn-1").stdout
    second = _scope(tmp_path, "instantiate", "scn-1").stdout
    lines = first.split()
    assert first == second
    assert lines == sorted(lines)
    assert len(lines) == len(set(lines))
