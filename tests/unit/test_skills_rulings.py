"""The six passes that model a contradiction honour a human's gate-1 ruling on it.

A ruling in 01-rulings.json changes the world model only once these passes are
re-run and model the human's resolution, so each must (a) declare the file in its
contract and (b) say, in the section that owns its inputs, that a ruled
resolution supersedes the part's. Scoped to `## 1. Inputs` with
`section_body`, never the whole file: the contract block and the frontmatter
would satisfy a naive substring check on their own.

Measured both ways when written: blanking the paragraph in a /tmp copy under
RUBRICA_SKILLS_DIR turns every case red, and a meaning-preserving reword of it
("takes the place of" for "in place of", the paragraph reflowed) stays green.
"""

from __future__ import annotations

import re

import pytest

from rubrica.rulings import CONTRADICTION_READERS
from rubrica.skills import load, section_body, skills_dir

INPUTS = "1. Inputs"


def _paragraphs(text: str) -> list[str]:
    return [" ".join(p.split()) for p in re.split(r"\n\s*\n", text)]


@pytest.mark.parametrize("stage", CONTRADICTION_READERS)
def test_each_contradiction_reader_declares_the_rulings_file(stage):
    skill = load(skills_dir() / f"rb-{stage}" / "SKILL.md")
    assert "rulings" in skill.contract["reads"]
    assert "rulings" not in skill.contract["writes"]


@pytest.mark.parametrize("stage", CONTRADICTION_READERS)
def test_each_contradiction_reader_models_the_human_resolution(stage):
    inputs = section_body(load(skills_dir() / f"rb-{stage}" / "SKILL.md"), INPUTS)
    ruled = [p for p in _paragraphs(inputs) if "01-rulings.json" in p]
    assert ruled, f"rb-{stage}'s Inputs never names 01-rulings.json"
    paragraph = ruled[0].lower()
    # Co-occurrence in one paragraph: the human's resolution replaces the part's,
    # and that is what the pass models.
    assert "resolution" in paragraph
    assert re.search(r"in place of|supersede|takes? the place of|instead of", paragraph)
    assert re.search(r"\bmodel", paragraph)
    # Absent is the normal case and must not read as an error.
    assert "absent" in paragraph
