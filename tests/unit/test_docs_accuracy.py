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

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

from rubrica import paths, skills, validate
from rubrica.cli import subcommand_names

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"

PIPELINE = DOCS / "concepts" / "pipeline.md"
CLI_REF = DOCS / "reference" / "cli.md"
ARTIFACTS_REF = DOCS / "reference" / "artifacts.md"

# The drawn counterpart to pipeline.md, and the script that renders it. Loaded
# by path rather than imported: scripts/ is a directory of tools, not a package,
# which is how test_trajectory_fixtures.py already reaches its capture harness.
DIAGRAM = DOCS / "concepts" / "pipeline-diagram.html"
RENDERER = REPO_ROOT / "scripts" / "render-pipeline-diagram.py"


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


# Policy predicates. Unlike the four above, these do not check that a document
# names something the code owns -- they enforce a decision about what a document
# may contain. All were motivated by measurement, recorded here because a future
# author will feel them as friction and deserves the reason: four hand-maintained
# counts were stale simultaneously, and the ~800-word parenthetical in CLAUDE.md
# that existed purely to keep the test count honest was itself wrong by 299.

_TEST_COUNT = re.compile(r"\b\d{3,4}\s+(?:tests?|passed)\b")

_NUMBER = (
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)"
)
# Only sets that grow. `## Two check layers` stays: there are exactly two by
# architecture, and a third would be a design change rather than an increment.
#
# `gates?` means the *human* gates, which are the set that grew -- three (after
# reconcile, score and challenge) until triage added gate 0. It cannot tell that
# sense from the closed one: `## The three gates you must pass`, over the three
# checks CI runs, matches too, and that is semantically the `Two check layers`
# case rather than a defect. Rewording the heading is the right response to such
# a hit -- CONTRIBUTING.md's own section is titled `## The gates CI runs` for
# exactly this reason -- because narrowing the token would cost the predicate the
# case it exists for. Judge a hit before obeying it.
_GROWING = r"(?:stages?|skills?|subcommands?|gates?)"
# `[ \t]` rather than `\s`, twice, and `[^\n]*` rather than `.*`: with `\s+` the
# pattern spans the newline at the end of a heading and consumes words from the
# line below it. Measured on the pre-rewrite README, where `# 1, the coverage
# matrices at 2, the verdict tallies at 3` matched because `3` -> newline ->
# `rubrica ` -> `gate` satisfied NUMBER -> space -> word -> GROWING.
_COUNTED_HEADING = re.compile(
    rf"^#+[ \t]+[^\n]*\b{_NUMBER}[ \t]+(?:\w+[ \t]+)?{_GROWING}\b",
    re.IGNORECASE | re.MULTILINE,
)


def _without_fences(text: str) -> str:
    """Markdown text with fenced blocks blanked out.

    A shell comment inside a ```bash block starts with `#` and is not a
    heading. Measured: `# runs all three gates in order` inside a fence
    matched the heading pattern before this was added.
    """
    out, fence = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        out.append("" if fence else line)
    return "\n".join(out)


def _doc_id(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


# The bare token, not `docs/superpowers`. docs/README.md links the tree
# relatively, as `superpowers/`, because `docs/superpowers/` from inside docs/
# would be a broken link -- so a predicate keyed on the qualified path computes
# "nothing cites history" and then fails its own allowlist assertion on a
# correct tree. Measured: docs/README.md carries `superpowers` four times, on two
# lines (each is a link whose text and target both spell it), and
# `docs/superpowers` zero times.
_HISTORY_TREE = "superpowers"


@pytest.mark.parametrize("doc", _user_facing(), ids=_doc_id)
def test_no_user_facing_document_carries_a_hand_typed_test_count(doc):
    """The count grows with every capability, so a number typed into prose is
    wrong shortly after it is written. `make test` reports the real one."""
    hits = _TEST_COUNT.findall(_read(doc))
    assert not hits, f"{_doc_id(doc)} states a test count ({hits}); run make test instead"


@pytest.mark.parametrize("doc", _user_facing(), ids=_doc_id)
def test_no_heading_counts_something_that_grows(doc):
    hits = _COUNTED_HEADING.findall(_without_fences(_read(doc)))
    assert not hits, (
        f"{_doc_id(doc)} has a heading counting stages/skills/subcommands/gates: {hits}"
    )


def _renderer() -> ModuleType:
    spec = importlib.util.spec_from_file_location("render_pipeline_diagram", RENDERER)
    assert spec is not None and spec.loader is not None, f"cannot load {RENDERER}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_diagram_draws_every_stage_in_contract_order():
    """The drawing carries the same stage list as pipeline.md, so it can go stale
    the same way -- and a drawing does it silently, because nobody re-reads an
    image looking for a missing row. ROWS is the renderer's whole content model,
    so asserting on it is asserting on the drawing.
    """
    rows = _renderer().ROWS
    drawn = [row["name"] for row in rows if row["kind"] == "stage"]
    assert drawn == list(paths.STAGES), (
        "the pipeline diagram's ROWS table does not draw paths.STAGES in order: "
        f"{drawn} != {list(paths.STAGES)}"
    )


def test_the_committed_diagram_matches_a_fresh_render():
    """The page is committed so a reader needs no build step; this is what keeps
    that copy honest. Fires on either mistake: a hand-edit to the HTML, or a
    change to the renderer that was never re-rendered.

    The renderer is pure string building over ROWS -- no clock, no filesystem
    reads -- so a mismatch is always one of those two and never flake.
    """
    assert DIAGRAM.is_file(), f"{_doc_id(DIAGRAM)} is missing; run {_doc_id(RENDERER)}"
    assert _read(DIAGRAM) == _renderer().page(), (
        f"{_doc_id(DIAGRAM)} is stale or hand-edited; re-run {_doc_id(RENDERER)}"
    )


def test_claude_md_does_not_cite_recorded_history():
    """The instruction every agent in this repository follows must point at
    current documentation. It used to point into a dated build record."""
    assert _HISTORY_TREE not in _read(REPO_ROOT / "CLAUDE.md")


def test_only_the_docs_index_cites_recorded_history():
    citing = [_doc_id(doc) for doc in _user_facing() if _HISTORY_TREE in _read(doc)]
    assert citing == ["docs/README.md"], (
        "docs/README.md is the one user-facing file that may link recorded history; "
        f"these do: {citing}"
    )
