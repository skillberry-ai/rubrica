"""The user-facing documents still name what the code owns.

Not a test of any behaviour -- a test of the documentation, in the shape of
test_refusal_fixtures.py. Every predicate asserts on a set the code already
exports (`cli.subcommand_names`, `paths.STAGES`, `skills.expected_skill_names`,
`validate.STAGE_ARTIFACTS`), never on a phrase. That is deliberate: a phrase pin
breaks on an innocuous reformat, which has already happened once in this
repository's skill tests, so pinning prose would trade one staleness problem for
a noisier one.

Why this module exists, measured rather than supposed: four hand-maintained
counts were stale simultaneously -- twelve subcommands against seventeen, 1126
tests against 1677, eight skills against nine, three human gates against four --
and CLAUDE.md's own reconciliation of the test count, roughly 800 words updated
commit by commit, was still wrong by 299.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rubrica import paths, skills

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"

PIPELINE = DOCS / "concepts" / "pipeline.md"
CLI_REF = DOCS / "reference" / "cli.md"
ARTIFACTS_REF = DOCS / "reference" / "artifacts.md"


def _user_facing() -> list[Path]:
    """Every document a reader with no build context is expected to read.

    docs/superpowers/ is excluded on purpose. It is recorded history: its counts
    are correct records of what was true on their own date, so a predicate that
    bans a count must not fire on them.
    """
    fixed = [REPO_ROOT / "README.md", REPO_ROOT / "CONTRIBUTING.md", REPO_ROOT / "CLAUDE.md"]
    under_docs = [
        path
        for path in sorted(DOCS.rglob("*.md"))
        if "superpowers" not in path.relative_to(DOCS).parts
    ]
    return [path for path in fixed if path.is_file()] + under_docs


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_the_pipeline_document_names_every_stage_in_contract_order():
    """paths.STAGES is the ordering and the on-disk numbering, so a document
    that lists the stages out of order is describing a different pipeline.

    Order, not just presence: every stage name is an ordinary English word
    (`emit`, `score`, `propose`), so presence alone is nearly satisfiable by
    accident in any prose about a pipeline. Position is not.
    """
    text = _read(PIPELINE)
    positions = []
    for stage in paths.STAGES:
        token = f"`{stage}`"
        assert token in text, f"pipeline.md never names the {stage} stage as {token}"
        positions.append(text.index(token))
    assert positions == sorted(positions), (
        "pipeline.md first names the stages in an order other than paths.STAGES: "
        f"{list(zip(paths.STAGES, positions, strict=True))}"
    )


@pytest.mark.parametrize("skill", sorted(skills.expected_skill_names()))
def test_every_skill_is_named_in_the_pipeline_document(skill):
    """skills.expected_skill_names() derives from STAGES minus the code-only
    stages, plus the orchestrator -- so this cannot drift from the code even if
    someone adds a stage and forgets the skill directory."""
    assert skill in _read(PIPELINE), f"pipeline.md never names {skill}"
