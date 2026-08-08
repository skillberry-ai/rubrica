"""Parsing one SKILL.md, and the failures that are exit 2 rather than findings.

A malformed SKILL.md is a human-authored file: no stage produces it, so no
repair prompt fixes it. That is the same ruling --agents and --gold carry, and
it is why the assertions below expect UsageError rather than a Finding.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from testgen.errors import UsageError
from testgen.paths import STAGES
from testgen.skills import (
    CODE_ONLY_STAGES,
    CONTRACT_HEADING,
    ORCHESTRATOR,
    SECTIONS,
    SKILL_FILENAME,
    Skill,
    discover,
    expected_skill_names,
    load,
    section_body,
    skill_sha256,
    skills_dir,
)

CONTRACT = """\
```toml
stage = "extract"
reads = ["manifest", "input_file"]
writes = ["claims"]
schemas = ["claims"]
invokes = ["validate"]
```
"""


def write_skill(root, name, contract=CONTRACT, headings=SECTIONS, extra=""):
    """A minimal well-formed SKILL.md, with knobs for the negative cases."""
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        f"name: {name}",
        "description: A skill, for testing.",
        "---",
        "",
        f"# {name}",
        "",
        "Purpose paragraph.",
        "",
        "## Contract",
        "",
        contract,
    ]
    for heading in headings:
        lines += ["", f"## {heading}", "", "Body text."]
    if extra:
        lines += ["", extra]
    path = directory / SKILL_FILENAME
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_load_returns_the_contract_and_the_headings_in_order(tmp_path):
    path = write_skill(tmp_path, "tg-extract")
    skill = load(path)
    assert isinstance(skill, Skill)
    assert skill.name == "tg-extract"
    assert skill.path == path
    assert skill.contract == {
        "stage": "extract",
        "reads": ["manifest", "input_file"],
        "writes": ["claims"],
        "schemas": ["claims"],
        "invokes": ["validate"],
    }
    # "Contract" first, then the five sections, in document order. The tuple
    # order is load-bearing: tg-challenge's ordering test reads it.
    assert skill.headings == ("Contract", *SECTIONS)


def test_the_headings_tuple_preserves_document_order_not_sorted_order(tmp_path):
    """Pins order specifically, because ("Contract", *SECTIONS) happens to be
    close to sorted order and a set() would satisfy the test above.
    """
    reversed_sections = tuple(reversed(SECTIONS))
    path = write_skill(tmp_path, "tg-extract", headings=reversed_sections)
    assert load(path).headings == ("Contract", *reversed_sections)


def test_skill_sha256_is_the_digest_of_the_whole_file(tmp_path):
    """The manifest's reproducibility hook hashes the skill that was used --
    prose included, because a changed Method section changes the run.

    Asserted as exact equality against an independently computed
    hashlib.sha256(path.read_bytes()) rather than, say, inequality before and
    after editing the prose: any implementation that satisfies an equality
    against the whole file's bytes must by construction change output
    whenever those bytes change, so a change-detection test on top of this
    one would be subsumed -- there is no mutation that passes this assertion
    and fails a "does editing the prose change the hash" one.
    """
    path = write_skill(tmp_path, "tg-extract")
    assert skill_sha256(path) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_discover_finds_every_skill_directory_sorted(tmp_path):
    write_skill(tmp_path, "tg-reconcile")
    write_skill(tmp_path, "tg-extract")
    (tmp_path / "not-a-skill").mkdir()
    assert [s.name for s in discover(tmp_path)] == ["tg-extract", "tg-reconcile"]


def test_a_directory_without_a_skill_file_is_not_discovered(tmp_path):
    """A stray directory is skipped, not an error: check-skills reports the
    *missing* skill by name (Task 2), which is a better message than a parse
    failure on a directory nobody claimed was a skill.
    """
    write_skill(tmp_path, "tg-extract")
    (tmp_path / "tg-propose").mkdir()
    assert [s.name for s in discover(tmp_path)] == ["tg-extract"]


def test_discover_on_a_missing_directory_is_a_usage_error(tmp_path):
    with pytest.raises(UsageError):
        discover(tmp_path / "nope")


def test_a_missing_skill_file_is_a_usage_error(tmp_path):
    with pytest.raises(UsageError):
        load(tmp_path / "tg-extract" / SKILL_FILENAME)


def test_invalid_utf8_bytes_are_a_usage_error(tmp_path):
    """A mis-encoded SKILL.md is refused, not a crash.

    UnicodeDecodeError is a ValueError, not an OSError, so an `except OSError`
    around read_text lets it propagate. cli.py's outer catch deliberately
    excludes ValueError -- that is the class of error a repair prompt could
    plausibly fix -- so an unhandled UnicodeDecodeError would surface as exit
    1 with an [internal] finding blaming the run directory, telling the
    orchestrator to spend its one bounded repair attempt re-running a stage
    when the actual problem is a mis-encoded prompt file that no stage wrote.
    """
    directory = tmp_path / "tg-extract"
    directory.mkdir()
    path = directory / SKILL_FILENAME
    path.write_bytes(b"\xff\xfe# tg-extract\n")
    with pytest.raises(UsageError):
        load(path)


def test_a_skill_with_no_contract_block_is_a_usage_error(tmp_path):
    path = write_skill(tmp_path, "tg-extract", contract="Just prose, no block.")
    with pytest.raises(UsageError):
        load(path)


def test_a_contract_block_that_is_not_toml_is_a_usage_error(tmp_path):
    path = write_skill(tmp_path, "tg-extract", contract="```toml\nstage = [unclosed\n```\n")
    with pytest.raises(UsageError):
        load(path)


def test_a_non_toml_fenced_block_is_not_mistaken_for_the_contract(tmp_path):
    """The block is found by its `toml` info string, not by being first. A
    SKILL.md whose Method section opens with a ```json example must still parse.
    """
    path = write_skill(
        tmp_path,
        "tg-extract",
        contract='```json\n{"stage": "wrong"}\n```\n\n' + CONTRACT,
    )
    assert load(path).contract["stage"] == "extract"


def test_two_toml_blocks_in_the_contract_section_is_a_usage_error(tmp_path):
    """Exactly one ```toml``` fence is required in the Contract section --
    not the first, not the last. A "deprecated example" or before/after
    block sitting alongside the real one is ambiguous, and this project
    refuses an ambiguous human-authored file rather than resolving it in the
    reader's favour by guessing which block was meant.
    """
    decoy = '```toml\nstage = "wrong"\n```\n\n'
    path = write_skill(tmp_path, "tg-extract", contract=decoy + CONTRACT)
    with pytest.raises(UsageError) as excinfo:
        load(path)
    assert "2 ```toml blocks" in str(excinfo.value)


def test_expected_skill_names_are_derived_from_STAGES(tmp_path):
    """Derived, never enumerated: adding a stage must demand a skill without
    anyone remembering to edit a list. Deleting the derivation and writing the
    eight names out passes an equality test against a literal -- so the
    assertion is against STAGES itself.
    """
    names = expected_skill_names()
    assert names[-1] == ORCHESTRATOR
    assert set(names[:-1]) == {f"tg-{s}" for s in STAGES if s not in CODE_ONLY_STAGES}
    assert "tg-intake" not in names and "tg-smoke" not in names


def test_skills_dir_resolves_beside_the_module_and_honours_the_override(tmp_path, monkeypatch):
    """Where an *installed* copy looks for its skills.

    This is the assertion that pins item 1 of the plan's Spec reconciliation:
    the skills are package data beside the module, not a repo-root directory
    that ships in no wheel. It reads like a restatement of the implementation
    and is kept anyway, because the thing being pinned is a packaging decision
    that no other test can fail on.
    """
    from testgen import skills as skills_module

    assert skills_dir() == Path(skills_module.__file__).resolve().parent / "skills"
    monkeypatch.setenv("TESTGEN_SKILLS_DIR", str(tmp_path))
    assert skills_dir() == tmp_path


def test_a_fenced_block_inside_a_section_does_not_inflate_headings(tmp_path):
    """A `## ` line inside a fenced code block is not a heading.

    A Method section that shows a markdown snippet -- entirely plausible
    prose for a skill that must itself describe SKILL.md structure -- must
    not silently inflate and reorder the `headings` tuple that Task 12's
    ordering checks depend on.
    """
    directory = tmp_path / "tg-extract"
    directory.mkdir()
    text = "\n".join(
        [
            "---",
            "name: tg-extract",
            "description: A skill, for testing.",
            "---",
            "",
            "# tg-extract",
            "",
            "## Contract",
            "",
            CONTRACT,
            "## 3. Method",
            "",
            "Example output a downstream reader might paste back:",
            "",
            "```markdown",
            "## Not a real heading",
            "```",
            "",
            "## 4. Invariants",
            "",
            "Body text.",
            "",
        ]
    )
    path = directory / SKILL_FILENAME
    path.write_text(text, encoding="utf-8")
    skill = load(path)
    assert skill.headings == ("Contract", "3. Method", "4. Invariants")
    assert "Not a real heading" not in skill.headings


def test_an_impostor_toml_fence_before_contract_is_ignored(tmp_path):
    """A valid-TOML fence in the prose before `## Contract`, declaring a
    different stage with a plausible value for every key, must not be
    mistaken for the contract -- only a fence inside the `## Contract`
    section counts. This is the silent case: the impostor is not invalid
    TOML (exit 2) and not obviously wrong (an ordinary Task 2 finding), so
    nothing downstream would notice unless the search is scoped to the
    section.
    """
    directory = tmp_path / "tg-extract"
    directory.mkdir()
    text = "\n".join(
        [
            "---",
            "name: tg-extract",
            "description: A skill, for testing.",
            "---",
            "",
            "# tg-extract",
            "",
            "Purpose paragraph with an example that gives plausible values",
            "for every key a real contract would need:",
            "",
            "```toml",
            'stage = "reconcile"',
            'reads = ["manifest"]',
            'writes = ["reconciled"]',
            'schemas = ["reconciled"]',
            'invokes = ["validate"]',
            "```",
            "",
            "## Contract",
            "",
            CONTRACT,
        ]
    )
    path = directory / SKILL_FILENAME
    path.write_text(text, encoding="utf-8")
    assert load(path).contract["stage"] == "extract"


def test_no_contract_heading_at_all_is_a_usage_error_naming_the_file(tmp_path):
    """A stray toml fence elsewhere in the file does not stand in for a
    missing `## Contract` heading -- that is a malformed file, the same class
    as a missing block, and the error names the file so a human can find it.
    """
    directory = tmp_path / "tg-extract"
    directory.mkdir()
    text = "\n".join(
        [
            "---",
            "name: tg-extract",
            "description: A skill, for testing.",
            "---",
            "",
            "# tg-extract",
            "",
            "## 3. Method",
            "",
            "```toml",
            'stage = "extract"',
            "```",
            "",
        ]
    )
    path = directory / SKILL_FILENAME
    path.write_text(text, encoding="utf-8")
    with pytest.raises(UsageError) as excinfo:
        load(path)
    assert str(path) in str(excinfo.value)
    assert CONTRACT_HEADING in str(excinfo.value)


def test_section_body_at_eof_returns_the_last_sections_text_not_empty(tmp_path):
    """Section 5 is last in every real skill. An implementation of
    `section_body` that required a following `## ` heading would read every
    refusal section as empty, and Task 2's emptiness check would then fire on
    every correct skill.
    """
    path = write_skill(tmp_path, "tg-extract")
    skill = load(path)
    body = section_body(skill, SECTIONS[-1])
    assert body.strip() != ""
    assert "Body text." in body
