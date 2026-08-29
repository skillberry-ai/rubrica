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

from rubrica import brief, paths, skills, validate
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


@pytest.mark.parametrize("doc", sorted((REPO_ROOT / "src").rglob("*.md")), ids=_doc_id)
def test_no_shipped_markdown_cites_recorded_history(doc):
    """The same rule, over the prose that ships inside the package.

    _user_facing() covers README/CONTRIBUTING/CLAUDE and docs/, and stops there --
    which is exactly why rb-reconcile/SUPERSEDED.md kept pointing at a dated design
    record long after that record's "no implementation yet" heading went false. A
    SKILL.md is read by a dispatched model and an exercise.md by a reviewer, so a
    stale pointer in either is read the same way a stale pointer in docs/ is. No
    file under src/ may cite the tree; there is no index here to exempt.
    """
    assert _HISTORY_TREE not in _read(doc), (
        f"{_doc_id(doc)} cites recorded history; point at current documentation instead"
    )


# The README's own drawing. Same discipline as the detailed page above -- a
# content table in a script, the committed output compared against a fresh
# render -- because a README picture is the one drawing a reader sees before they
# have any way to tell it is out of date. It differs from that page in one respect
# only: it groups the stages into phases rather than giving each its own row, so
# the predicate below asserts on the partition rather than on a row per stage.
README_RENDERER = REPO_ROOT / "scripts" / "render-readme-diagram.py"


def _readme_renderer() -> ModuleType:
    spec = importlib.util.spec_from_file_location("render_readme_diagram", README_RENDERER)
    assert spec is not None and spec.loader is not None, f"cannot load {README_RENDERER}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_readme_diagram_covers_every_stage_in_contract_order():
    """A partition, so this is stronger than the presence check a grouped drawing
    might seem to allow: concatenating the phases has to reproduce paths.STAGES
    exactly. Measured red on a stage deleted from its phase, on a renumbered gate,
    and on a hand-edited SVG.

    What it does not catch, also measured: moving `reconcile` from the second phase
    to the front of the third leaves the concatenation identical and passes. Which
    phase a stage belongs to is an editorial judgment about altitude, not a fact
    the code owns -- the same reason check-refs resolves a claim reference without
    ruling on whether the claim supports it. Reading the drawing is what catches
    that; this predicate catches the drift a reader would not notice.
    """
    covered = [stage for phase in _readme_renderer().PHASES for stage in phase["stages"]]
    assert covered == list(paths.STAGES), (
        "the README diagram's PHASES table does not partition paths.STAGES in order: "
        f"{covered} != {list(paths.STAGES)}"
    )


def test_every_readme_phase_line_accounts_for_exactly_one_stage_and_no_line_for_none():
    """The fold's guard, asserted in both directions.

    A phase may collapse a family of stages into one drawn line, so the partition
    test above -- which reads the unfolded `stages` lists -- can no longer see what
    the drawing actually sets. Two failures are possible and neither is visible in
    the SVG to anyone who does not already know the pipeline:

    - a stage in `stages` that no drawn line accounts for, which is a stage
      silently dropped from the drawing;
    - a drawn line that accounts for no stage, which is a fold prefix matching
      nothing -- a label standing for a family that is not there.

    Measured red both ways before being kept, one probe per half:

    - `folds=["deploy-"]` on the `compile` phase, a prefix matching none of its
      stages, failed the second half -- *the 'compile' phase draws a 'deploy*' line
      that accounts for no stage at all*;
    - moving `fold_lines`' append inside its `if label not in at` branch, so a fold
      keeps only the first stage it matches, failed the first -- *the 'select'
      phase draws lines accounting for ['survey', 'triage-slices'], not for its
      stages [...]*. The partition test above **passed** under that same mutation,
      which is the reason this predicate exists: it reads `stages`, and the drawing
      no longer does.

    Green on the committed table, and green with `folds` deleted from every phase
    (measured: the legend entry and its whole row fall away with it, and the canvas
    returns to its one-row height).

    The first half was `accounted == list(spec["stages"])` until
    `synthesise-interfaces` landed, and that spelling asserted one thing more than
    the property above: that every folded family occupies an *unbroken* run of its
    phase's stages. The pipeline falsified it. `synthesise-interfaces` sits between
    `reconcile-services` and `reconcile-seal` -- it reads the part the first writes,
    so the slot is a dependency, not a preference -- and it is not a `reconcile-`
    pass, so the `understand` phase's fold now spans a stage that draws its own
    line. List equality then failed on a table that is correct, which is a
    predicate wrong about the pipeline rather than a pipeline wrong about the
    predicate.

    So the two halves are spelled as what they always meant -- a multiset equality
    and a no-empty-line check -- plus the ordering claim the drawing does make,
    which list equality had been carrying implicitly: each line's own stages are in
    pipeline order, and the lines are ordered by where each begins. Four mutations
    measured red against this spelling, the two above and two that exist because
    ordering is now asserted directly rather than as a side effect:

    - `fold_lines`' append moved inside its `if label not in at` branch → *the
      'select' phase draws lines accounting for ['survey', 'triage-slices'], not
      for its stages [...]*;
    - `folds=["deploy-"]` on the `compile` phase → *draws a 'deploy*' line that
      accounts for no stage at all*;
    - `return list(reversed(lines))` → *the 'select' phase draws its lines
      ['triage*', 'survey'] in an order other than the pipeline's*;
    - the fold's `append` changed to `insert(0, stage)` → *the 'select' phase's
      'triage*' line draws ['triage-seal', ..., 'triage-slices'] out of pipeline
      order*.
    """
    renderer = _readme_renderer()
    for spec in renderer.PHASES:
        stages = list(spec["stages"])
        lines = renderer.fold_lines(spec)
        accounted = [stage for _, stages_of in lines for stage in stages_of]
        assert sorted(accounted) == sorted(stages), (
            f"the {spec['verb']!r} phase draws lines accounting for {accounted}, "
            f"not for its stages {stages}"
        )
        # Order, in the two senses the drawing claims: within a line, and between
        # lines. `stages.index` is safe because the multiset check above has already
        # established that every drawn stage is one of this phase's.
        for label, stages_of in lines:
            positions = [stages.index(stage) for stage in stages_of]
            assert positions == sorted(positions), (
                f"the {spec['verb']!r} phase's {label!r} line draws {stages_of} out of "
                f"pipeline order against its stages {stages}"
            )
        starts = [stages.index(stages_of[0]) for _, stages_of in lines if stages_of]
        assert starts == sorted(starts), (
            f"the {spec['verb']!r} phase draws its lines {[label for label, _ in lines]} in "
            f"an order other than the pipeline's against its stages {stages}"
        )
        for label, stages in lines:
            assert stages, (
                f"the {spec['verb']!r} phase draws a {label!r} line that accounts for no "
                "stage at all: a fold prefix matching nothing hides whatever it was "
                "meant to stand for"
            )


def test_the_readme_diagram_marks_every_human_gate():
    """brief.GATES is the code-side source of truth -- `rubrica gate-brief` refuses
    any number outside it -- so the drawing's gates stay derived rather than typed.
    Gate 0 is why this exists: it was added after the other three, and every
    hand-maintained count of them went stale in the same commit.
    """
    marked = tuple(
        phase["gate"] for phase in _readme_renderer().PHASES if phase["gate"] is not None
    )
    assert marked == brief.GATES, (
        f"the README diagram marks gates {marked}; brief.GATES is {brief.GATES}"
    )


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_committed_readme_diagram_matches_a_fresh_render(theme):
    """Both themes, because the pair is what the README's <picture> element
    references and a reader only ever sees one of them -- so a stale dark file is
    invisible to anyone browsing in light mode, including the author who forgot
    to re-render."""
    renderer = _readme_renderer()
    path = renderer.OUTPUTS[theme]
    assert path.is_file(), f"{_doc_id(path)} is missing; run {_doc_id(README_RENDERER)}"
    assert _read(path) == renderer.svg(theme), (
        f"{_doc_id(path)} is stale or hand-edited; re-run {_doc_id(README_RENDERER)}"
    )


def test_the_readme_diagram_fold_legend_appears_only_when_something_folds():
    """A legend explaining a convention the drawing does not use is worse than no
    legend. caption_rows() is what drops the fold entry and its whole row, so the
    check is against the rendered SVG rather than against that helper: a legend
    kept by a bug in phase() would still be wrong.

    Ported from the footnote guard staged-reconcile wrote for its own fold, which
    explained the star in a footnote line rather than a legend row. The mechanism
    changed in the merge; the property it held did not.
    """
    renderer = _readme_renderer()
    words = "one line standing for the stages it collapses"
    folds = bool(renderer.fold_marks())
    for theme in renderer.OUTPUTS:
        assert (words in renderer.svg(theme)) is folds, (
            f"the fold legend must appear exactly when something folds "
            f"(folds={folds}, marks={renderer.fold_marks()})"
        )


def test_fold_lines_folds_a_synthetic_family_this_test_owns():
    """A fold-triggering input this test owns, rather than the real PHASES.

    The real table is held by the two tests above and by the byte-compare, which
    would otherwise ratify whatever the renderer emitted at the moment the SVGs
    were committed. This spec cannot move when PHASES is re-partitioned, so a
    change to the phase table and a regression in the fold logic stay
    distinguishable.

    The expected lists are spelled out by hand rather than computed from the
    prefix or from any partition of the input spec: recomputing the fold here
    would be the same logic checking itself and could not catch a regression in
    that logic (the holds-identically shape).
    """
    renderer = _readme_renderer()
    spec = dict(
        stages=["intake", "reconcile-subjects", "reconcile-merge", "reconcile-seal", "propose"],
        folds=["reconcile-"],
    )
    assert renderer.fold_lines(spec) == [
        ("intake", ["intake"]),
        ("reconcile*", ["reconcile-subjects", "reconcile-merge", "reconcile-seal"]),
        ("propose", ["propose"]),
    ], (
        "three reconcile-* stages should collapse to one line, in the position "
        "the family occupied, with the unfolded stages either side kept in order"
    )

    # Edge case sharing the same root cause: a phase where every stage folds.
    assert renderer.fold_lines(
        dict(stages=["reconcile-subjects", "reconcile-merge"], folds=["reconcile-"])
    ) == [("reconcile*", ["reconcile-subjects", "reconcile-merge"])]

    # Two families in one phase, which the superseded single-prefix fold could not
    # express at all -- and the reason this mechanism is the one that survived.
    assert renderer.fold_lines(
        dict(stages=["triage-rule", "intake", "reconcile-gaps"], folds=["triage-", "reconcile-"])
    ) == [("triage*", ["triage-rule"]), ("intake", ["intake"]), ("reconcile*", ["reconcile-gaps"])]


def test_the_readme_references_both_diagram_themes():
    """The guard above keeps the files honest; this one keeps them reachable. A
    <picture> that lost its dark <source> still renders, which is exactly why the
    omission would go unnoticed on a light-themed page.
    """
    text = _read(REPO_ROOT / "README.md")
    renderer = _readme_renderer()
    for theme, path in renderer.OUTPUTS.items():
        rel = path.relative_to(REPO_ROOT).as_posix()
        assert rel in text, f"README.md never references the {theme} diagram, {rel}"
    dark = renderer.OUTPUTS["dark"].relative_to(REPO_ROOT).as_posix()
    source = text[text.index("<picture>") : text.index("</picture>")]
    assert "prefers-color-scheme: dark" in source and dark in source, (
        "README.md's <picture> does not offer the dark diagram under a "
        "prefers-color-scheme media query"
    )


def test_the_validate_stage_list_offers_exactly_the_contract_stages():
    """`validate --stage` takes one of paths.STAGES, so the document that lists
    the accepted values is either that list or wrong.

    Untested until now, and it drifted the way an untested list does: the
    staged-triage branch deleted the `triage` stage and added four, and this
    list kept offering the deleted one while naming only one of the four. A
    reader following it got exit 2 from a stage that no longer exists, and no
    hint that four stages they could validate were missing. Both halves are
    asserted -- every contract stage present, and nothing present that is not a
    contract stage -- because a list can drift in either direction and only the
    second half catches a deletion.
    """
    text = _read(CLI_REF)
    section = text[text.index("### `rubrica validate`") :]
    section = section[: section.index("\n### ")]
    offered = set(re.findall(r"`([a-z][a-z-]*)`", section))
    # The prose around the list names the flags and the layer too; only names
    # that are stages or look like them are the list's business.
    stage_shaped = {name for name in offered if name in set(paths.STAGES) or "triage" in name}
    assert stage_shaped == set(paths.STAGES), (
        "cli.md's validate --stage list disagrees with paths.STAGES: "
        f"missing {sorted(set(paths.STAGES) - stage_shaped)}, "
        f"offers non-stages {sorted(stage_shaped - set(paths.STAGES))}"
    )
