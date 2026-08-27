"""The one fact every directory-writing prompt stage needs and no skill carried.

Several prompt stages write their artifact *into a directory*, and not one of
those directories is created by code: `grep -rn mkdir src/rubrica/` creates
`run.root`, `inputs_dir` and `slices_dir` and stops. Every other one comes into
being as a side effect of a dispatched member's `Write`, which creates parents.
`validate.py` states it plainly for one of them -- "a directory that does not
exist until the first member has written to it" -- and that sentence sits in a
module no member reads.

**Why the table below filters on `paths.STAGES` rather than listing rows
outright.** The two staged families are developed on sibling branches off `main`,
neither of which has the other's skills: `staged-triage` carries
`rb-triage-rule` and the monolithic `rb-reconcile`, `staged-reconcile` carries
`rb-reconcile-contradict` and the monolithic `rb-triage`. A hard-coded table
would be a different file on each branch and would conflict on every merge
into an integration branch. Filtering on `paths.STAGES` -- which *is* the
branch's pipeline -- makes one file correct everywhere, and the filter is not a
silent cap: a row whose stage this branch runs but whose skill is missing fails
the table test rather than being skipped.

MEASURED 2026-08-23, on the reservation-service run in issue #5: an
`rb-triage-rule` member dispatched into a run whose `00-dispositions/` did not
exist spent roughly seven turns and one `dangerouslyDisableSandbox` escalation
attempt trying to `mkdir` it before naming `Write` as the way round. `mkdir` is
not on the dispatch's Bash allowlist (`scripts/dispatch-stage.sh` allows
`rubrica *` and nothing else), so under `claude -p` the command lands on an
approval prompt that cannot be answered.

Two predicates, because the claim has a behavioural half and a prose half and
each is worthless alone:

`test_..._is_absent_until_its_writer_runs` pins the premise. No fixture reached
it before this module: `tests/toy.py` stages every part with
`artifacts.write_json`, whose `path.parent.mkdir` creates the directory, and
`_UPTO_STAGES` has no checkpoint between `extract` and `reconcile-gaps` -- so
"subjects written, `01-contradictions/` absent", the state
`rb-reconcile-contradict` is actually dispatched into, had to be built by hand
below. This is the *fixture-cannot-reach* shape, not a missing assertion.

`test_..._is_declared_write_created_in_its_skill` pins the prose. If somebody
later decides the mkdir belongs in code after all -- the alternative issue #5
proposed, whose cost is measured in `docs/design/limitations.md` -- the first
predicate fails and the prose has to go with it. That is the point: the two
must agree, and neither may drift alone.
"""

from __future__ import annotations

import re

import pytest

from rubrica import skills
from rubrica.artifacts import write_json
from rubrica.paths import STAGES, RunPaths
from tests import toy

# stage -> (skill directory, RunPaths attribute, the checkpoint that runs
# immediately before the stage that writes into it).
#
# Editorial, and it has to be: which directories code creates is not
# introspectable, so this table is read off `grep -rn mkdir src/rubrica/` by a
# person. What the tests below make non-editorial is that every row still holds
# -- an mkdir added anywhere fails the first predicate.
#
# `reconcile-contradict` carries no `upto` because `_UPTO_STAGES` has no
# checkpoint there; its precondition is built by hand in the fixture below.
_CANDIDATES: tuple[tuple[str, str, str, str | None], ...] = (
    ("triage-rule", "rb-triage-rule", "dispositions_dir", "triage-objective"),
    ("reconcile-contradict", "rb-reconcile-contradict", "contradictions_dir", None),
    ("extract", "rb-extract", "claims_dir", "intake"),
    # The loop's two rows moved with the propose/score split. A propose member
    # writes 02-scenarios/round-N/<batch>.json, so `02-scenarios/` is now
    # Write-created by whichever member of the round writes first; score writes
    # 03-score/round-N.json, so `03-score/` is its own. `03-coverage/` left this
    # table in the same change: rounds.seal_score composes it in code, and
    # artifacts.write_json mkdirs the parent, so no prompt needs the rule for it.
    ("propose", "rb-propose", "scenario_parts_dir", "reconcile-seal"),
    ("score", "rb-score", "score_parts_dir", "propose-seal"),
    ("instantiate", "rb-instantiate", "instances_dir", "score"),
    ("challenge", "rb-challenge", "verdicts_dir", "instantiate"),
)

# Only the stages this branch's pipeline actually runs; see the module docstring.
_ROWS = tuple(row for row in _CANDIDATES if row[0] in STAGES)


def _norm(text: str) -> str:
    """Whitespace-normalised and lowercased, so a reflow does not break a pin --
    the same helper the two family modules define, for the same reason (399dba5:
    two phrase pins broke on an innocuous reformat)."""
    return re.sub(r"\s+", " ", text.lower())


def test_the_row_table_names_real_stages_and_real_run_paths_attributes():
    """The table is editorial; that its entries exist is not. A stage renamed in
    `paths.STAGES` or a `RunPaths` attribute renamed leaves a row pointing at
    nothing, and every predicate below would then pass vacuously against a skill
    it never located.

    This is also what keeps the `paths.STAGES` filter from becoming a silent cap.
    A row is allowed to drop out only because this branch does not run that stage;
    a row this branch *does* run whose skill directory has been renamed or removed
    fails here rather than quietly reducing the parametrisation to nothing."""
    assert _ROWS, "every candidate row was filtered out; the table matches no stage here"
    for stage, skill_dir, attr, upto in _ROWS:
        assert stage in STAGES, f"{stage!r} is not a stage"
        assert hasattr(RunPaths("/nonexistent"), attr), f"RunPaths has no {attr!r}"
        assert (skills.skills_dir() / skill_dir / "SKILL.md").is_file(), (
            f"{stage} is in paths.STAGES but {skill_dir}/SKILL.md is missing; the filter "
            "drops rows for absent stages, never for absent skills"
        )
        if upto is not None:
            assert upto in STAGES, f"{upto!r} is not a stage"


@pytest.mark.parametrize(("stage", "skill_dir", "attr", "upto"), _ROWS)
def test_every_write_created_output_directory_is_absent_until_its_writer_runs(
    tmp_path, stage, skill_dir, attr, upto
):
    """The premise the prose rests on, measured rather than assumed: at the
    checkpoint immediately before its writer, the directory is not there.

    An mkdir added to code -- issue #5's other candidate fix -- turns this red,
    which is the coupling this module exists for."""
    if upto is None:
        # reconcile-contradict: extract's claims written, reconcile-subjects'
        # cover written, its own fan-out not started. No checkpoint stops here.
        run = toy.build_toy_run(tmp_path, upto="extract")
        write_json(run.subjects, toy.split_world_model()["subjects"])
    else:
        run = toy.build_toy_run(tmp_path, upto=upto)
    directory = getattr(run, attr)
    assert not directory.exists(), (
        f"{directory.name} exists before {stage} runs; if that is now deliberate, "
        f"{skill_dir}'s Output section must stop saying its Write creates it"
    )


@pytest.mark.parametrize(("stage", "skill_dir", "attr", "upto"), _ROWS)
def test_every_write_created_output_directory_is_declared_write_created_in_its_skill(
    stage, skill_dir, attr, upto
):
    """The rule has to be one statement: the command not to reach for, the
    directory it would have created, and the tool that creates it instead, all in
    the **same paragraph** of the section that owns them.

    `mkdir` locates the paragraph. It appears in no `SKILL.md` in the repository
    before this change, so it finds the new rule and nothing else. Neither it nor
    the directory name can be paraphrased away -- one is a command name, the other
    a path -- and `Write` cannot either, being the name of the tool that does the
    job instead.

    **Two requirements were measured out of this predicate rather than reasoned
    out, and the second is why it scopes to a paragraph and not a window.**

    It also asserted `creat`, on the argument that the prose must say the
    directory is *created* rather than only that `mkdir` is forbidden. Rewording
    all six paragraphs meaning-preservingly -- "your `Write` brings it into being,
    parents included" -- turned all six red against skills carrying the rule
    perfectly well. That was a phrase pin wearing a semantic requirement's
    clothes, and the deletion probe alone had passed it.

    It then scoped `write` to a +/-500-character window around `mkdir`, sized from
    a measured farthest distance of 231 to clear this repo's 2x floor. A probe
    that cut the rule down to a bare prohibition -- `mkdir` and the directory
    named, no route to the output at all -- **passed**, because
    `rb-reconcile-contradict`'s next paragraph opens "Write the part even when you
    found nothing" and sits inside 500 characters. The window was wide enough to
    borrow its evidence from prose that was already there, which is the
    substring-of-message weakness with extra steps. A paragraph cannot borrow, so
    there is no radius here to get wrong.

    The cost, stated because it is a real constraint on a later editor rather than
    an accident: splitting the rule across two paragraphs -- prohibition in one,
    the `Write` route in the next -- turns this red against prose that means the
    right thing. Keep it as one paragraph. The failure message says so.
    """
    skill = skills.load(skills.skills_dir() / skill_dir / "SKILL.md")
    dirname = getattr(RunPaths("/nonexistent"), attr).name.lower()
    paragraphs = [_norm(p) for p in skills.section_body(skill, "2. Output").split("\n\n")]
    owning = [p for p in paragraphs if "mkdir" in p]
    assert len(owning) == 1, (
        f"{skill_dir}'s Output section has {len(owning)} paragraphs naming mkdir, not 1; "
        "the rule is one statement and belongs in one paragraph"
    )
    rule = owning[0]
    assert dirname in rule, f"{skill_dir} does not tie the mkdir rule to {dirname}"
    assert "write" in rule, (
        f"{skill_dir} forbids mkdir without naming Write as the route to "
        f"{dirname} -- keep both halves in the one paragraph"
    )
