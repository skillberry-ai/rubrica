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

import re
from pathlib import Path

import pytest

from rubrica import paths, skills, validate
from rubrica.cli import subcommand_names

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


# Every subcommand gets its own section, headed `rubrica <name>`. Parsed rather
# than substring-matched because most subcommand names are ordinary words that
# appear in prose anyway -- `validate`, `decide`, `emit`, `smoke` -- so a bare
# `in text` check would pass on a document that merely mentions them.
_CLI_SECTION = re.compile(r"^#{2,4}\s+`?rubrica\s+([a-z-]+)`?", re.MULTILINE)


def _documented_subcommands() -> set[str]:
    return set(_CLI_SECTION.findall(_read(CLI_REF)))


@pytest.mark.parametrize("name", sorted(subcommand_names()))
def test_every_subcommand_has_its_own_section(name):
    assert name in _documented_subcommands(), (
        f"docs/reference/cli.md has no `rubrica {name}` section"
    )


def test_no_section_documents_a_subcommand_that_does_not_exist():
    """The other direction: a section for a command that was renamed or removed
    is a worse defect than a missing one, because it reads as current."""
    stale = _documented_subcommands() - set(subcommand_names())
    assert not stale, f"cli.md documents commands cli.SUBCOMMANDS does not define: {sorted(stale)}"


def _artifact_kinds() -> set[str]:
    return {kind for kinds in validate.STAGE_ARTIFACTS.values() for kind in kinds}


@pytest.mark.parametrize("kind", sorted(_artifact_kinds()))
def test_every_artifact_kind_is_documented(kind):
    """Backtick-delimited on purpose: a bare `expected in text` check is
    satisfied by the string `suite-expected`, so two distinct artifact kinds
    would collapse into one and the missing one would never be noticed."""
    assert f"`{kind}`" in _read(ARTIFACTS_REF), (
        f"docs/reference/artifacts.md never names the {kind} artifact as `{kind}`"
    )
