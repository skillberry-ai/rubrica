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
    ORCHESTRATOR,
    SECTIONS,
    SKILL_FILENAME,
    Skill,
    discover,
    expected_skill_names,
    load,
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
    """
    path = write_skill(tmp_path, "tg-extract")
    assert skill_sha256(path) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_editing_only_the_prose_changes_the_hash(tmp_path):
    """The half of the statement above that a digest-equality assertion cannot
    make on its own: hashing only the contract block would satisfy that test.
    """
    path = write_skill(tmp_path, "tg-extract")
    before = skill_sha256(path)
    path.write_text(
        path.read_text(encoding="utf-8").replace("Body text.", "Different body text."),
        encoding="utf-8",
    )
    assert skill_sha256(path) != before


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
