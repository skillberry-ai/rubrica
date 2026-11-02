"""The reconcile passes that run after the two a phase skips, told about the skip.

rb-orchestrate does not dispatch `reconcile-subjects` or `reconcile-contradict`
when `manifest.json` carries a `phase` block, so `01-subjects.json` and
`01-contradictions/` never exist in a phased run. Every pass still to run named
one or both under `reads` and carried an unconditional "an input this contract
names is absent -- refuse" condition. Measured on a real phased run
(run-20261005-113420, reservation-service corpus): three dispatches of
`rb-reconcile-capabilities`, three refusals, each citing that condition, and no
phased run could reach gate 1. The code side -- the seal and `check-refs` --
already tolerated the absence; no prompt did, and no test looked.

The skill set is derived from the contracts rather than listed, so a pass added
later that reads either input is held to the same rule without anyone
remembering to add it here.
"""

from __future__ import annotations

import re
from pathlib import Path

from rubrica.paths import RunPaths
from rubrica.skills import Skill, discover, section_body

INPUTS = "1. Inputs"
REFUSALS = "5. Refusal conditions"

# The two passes a phase skips. They read their own inputs, never each other's
# output under a phase, because under a phase neither is dispatched at all.
SKIPPED_STAGES = {"reconcile-subjects", "reconcile-contradict"}
SKIPPED_READS = ("subjects", "contradictions_dir")

# On-disk names from RunPaths, not typed here, so a rename of either artifact
# fails this module rather than leaving it pinning a name nothing writes.
_RUN = RunPaths(Path("/run"))
FILE_NAMES = {read: getattr(_RUN, read).name for read in SKIPPED_READS}


def _paragraphs(text: str) -> list[str]:
    """Blank-line-separated blocks, whitespace-normalised and lowercased.

    A §5 condition is one bullet and a §1 rule is one paragraph, and both are
    separated by blank lines in every skill -- so this is the co-occurrence
    scope, narrow enough that "phase" in one condition and the file name in
    another cannot satisfy a predicate together.
    """
    return [re.sub(r"\s+", " ", block).lower() for block in re.split(r"\n\s*\n", text)]


def _readers() -> list[tuple[Skill, list[str]]]:
    out = []
    for skill in discover():
        if skill.contract.get("stage") in SKIPPED_STAGES:
            continue
        absent = [read for read in SKIPPED_READS if read in skill.declared("reads")]
        if absent:
            out.append((skill, absent))
    return out


def test_the_reader_set_is_the_six_passes_after_the_skip():
    """Fixture-cannot-reach guard: if discovery found nothing, every test below
    would pass vacuously over an empty loop."""
    names = {skill.name for skill, _ in _readers()}
    assert names == {
        "rb-reconcile-capabilities",
        "rb-reconcile-outcomes",
        "rb-reconcile-entities",
        "rb-reconcile-goals",
        "rb-reconcile-gaps",
        "rb-reconcile-services",
    }


def _trigger(condition: str) -> str:
    """A condition's bold lead -- the trigger a model matches against -- or ''."""
    match = re.match(r"- \*\*(.*?)\*\*", condition)
    return match.group(1) if match else ""


def test_each_reader_has_a_phase_condition_naming_what_is_absent():
    """One §5 condition's trigger names the phase, the manifest that declares it,
    and every skipped file this pass reads. Without it the absent-input condition
    is the only one that matches, and it says refuse.

    Scoped to the trigger, not the bullet: measured, the gaps bullet names
    `01-subjects.json` again in its body, so a whole-bullet check stayed green
    with the file cut from the trigger -- where a model would no longer read the
    exception as covering it."""
    for skill, absent in _readers():
        triggers = [_trigger(c) for c in _paragraphs(section_body(skill, REFUSALS))]
        names = [FILE_NAMES[read] for read in absent]
        matching = [
            t
            for t in triggers
            if "phase" in t and "manifest.json" in t and all(n in t for n in names)
        ]
        assert matching, f"{skill.name}: no refusal condition carves {names} out under a phase"


def test_each_readers_phase_condition_comes_before_the_absent_input_one():
    """A model reads §5 top to bottom and acts on the first condition that matches;
    the measured run's three refusals each stopped at the absent-input condition.
    So the exception has to be met first.

    Order rather than a pointer inside the absent-input condition, because that
    condition is held byte-identical across the whole reconcile family
    (`test_skills_reconcile_family`), and two of its members are the passes a
    phase skips -- where a pointer to a phase exception would be false."""
    for skill, _ in _readers():
        triggers = [_trigger(c) for c in _paragraphs(section_body(skill, REFUSALS))]
        absent_input = [i for i, t in enumerate(triggers) if "absent from the run directory" in t]
        phase = [i for i, t in enumerate(triggers) if "phase" in t and "manifest.json" in t]
        assert absent_input, f"{skill.name}: the absent-input condition is gone"
        assert phase, f"{skill.name}: no phase condition"
        assert max(phase) < min(absent_input), (
            f"{skill.name}: the phase condition comes after the absent-input condition"
        )


def test_each_reader_keeps_the_contradiction_constraint_under_a_phase():
    """No sweep ran, which is not the same as the claims agreeing. §1 makes an
    unruled disagreement the pass can see count as one recorded `unresolved`, so
    the pass does not settle it in a place with no rationale field -- the
    observability loss this project counts as a regression."""
    for skill, _ in _readers():
        paragraphs = _paragraphs(section_body(skill, INPUTS))
        assert any("phase" in p and "unresolved" in p for p in paragraphs), (
            f"{skill.name}: §1 does not say how a disagreement is treated under a phase"
        )


def test_gaps_records_an_unruled_disagreement_under_a_phase():
    """Under a phase nobody else records a disagreement at all, so the gaps pass
    is told to make each one it sees visible at gate 1 as a gap."""
    (gaps,) = [skill for skill, _ in _readers() if skill.name == "rb-reconcile-gaps"]
    paragraphs = _paragraphs(section_body(gaps, INPUTS))
    assert any("phase" in p and "unresolved" in p and "as a gap" in p for p in paragraphs)
