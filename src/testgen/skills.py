"""Reading the skill files, and hashing the one a stage was run with.

The pipeline's producers are prompts, so the drift hazard is different in kind
from the one the schemas close: a SKILL.md can name an artifact path that does
not exist, a stage that was renamed, or a CLI subcommand spelled with an
underscore, and nothing downstream notices until a model has already been paid
to follow it. This module gives that text one machine-readable declaration --
the `## Contract` block -- and check_contract, arriving in this same module in
Task 2, is what holds it to the code that owns each name.

**A malformed SKILL.md is exit 2, not a finding.** It is human-authored, like
--agents and --gold: no stage produces it, so no repair prompt fixes it. A
contract that *parses* but declares something wrong is the opposite -- an
ordinary finding, because it names exactly what to edit.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from testgen.artifacts import sha256_of
from testgen.errors import UsageError
from testgen.paths import STAGES

SKILL_FILENAME = "SKILL.md"

# Stages implemented entirely in code. intake mints run ids and timestamps,
# which the design spec forbids a skill from inventing; smoke executes the
# suite. Every other stage in STAGES has a skill, and expected_skill_names
# derives the list rather than restating it -- so adding a stage demands a
# skill without anyone remembering to edit a constant.
CODE_ONLY_STAGES: frozenset[str] = frozenset({"intake", "smoke"})

# Not a stage: it dispatches them. It has no `stage` key and no `schemas`.
ORCHESTRATOR = "tg-orchestrate"

# The uniform five-section skill shape (design spec section 5), in order.
# Section 5 is the one that matters most: skills default to helpfulness, and
# confabulation under under-specification is the characteristic failure of a
# prompt pipeline.
SECTIONS: tuple[str, ...] = (
    "1. Inputs",
    "2. Output",
    "3. Method",
    "4. Invariants",
    "5. Refusal conditions",
)

# The machine-readable declaration every skill carries in addition to its
# five prose sections above. Deliberately not a member of SECTIONS: it is not
# one of the numbered, human-facing sections -- it is where load() and
# check_contract look for the ```toml block.
CONTRACT_HEADING = "Contract"

_HEADING = re.compile(r"^##[ \t]+(?P<title>.+?)[ \t]*$")
_TOML_BLOCK = re.compile(r"^```toml[ \t]*\n(?P<body>.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)


def _headings_with_lines(lines: list[str]) -> list[tuple[str, int]]:
    """(title, line_index) for every `## ` heading outside a fenced code block.

    A regex that tracks fence state across an entire file is unreadable, so
    this walks the file once instead: toggle a flag on every fence-delimiter
    line (a line whose stripped form starts with ``` ```) and only look for a
    heading while that flag is unset. Without this, a Method section that
    shows a markdown snippet containing "## " would inflate and reorder the
    `headings` tuple that Task 12's ordering checks depend on.
    """
    found = []
    in_fence = False
    for index, line in enumerate(lines):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING.match(line)
        if match:
            found.append((match.group("title"), index))
    return found


def _section_text(text: str, heading: str, path: Path) -> str:
    """Body of one `## heading` section: the lines after it, up to the next
    `## ` heading (fence-aware, the same rule `headings` uses) or EOF.

    Raises UsageError naming `path` if `heading` is not present at all -- a
    missing section is a malformed file, the same class as a missing
    contract block.
    """
    lines = text.splitlines()
    headings = _headings_with_lines(lines)
    for position, (title, line_index) in enumerate(headings):
        if title != heading:
            continue
        start = line_index + 1
        end = headings[position + 1][1] if position + 1 < len(headings) else len(lines)
        return "\n".join(lines[start:end])
    raise UsageError(f"{path} has no '## {heading}' heading")


@dataclass(frozen=True)
class Skill:
    """One parsed SKILL.md: its declaration, its structure, and its text."""

    name: str
    path: Path
    contract: dict[str, Any]
    headings: tuple[str, ...]
    body: str

    def declared(self, key: str) -> list[str]:
        """A list-valued contract key, or [] if absent.

        Tolerant on purpose: an absent key is check_contract's finding to
        report by name, and raising here would turn it into exit 2.
        """
        value = self.contract.get(key, [])
        return value if isinstance(value, list) else []


def section_body(skill: Skill, heading: str) -> str:
    """Text under one `## heading` in `skill.body`, fence-aware like `headings`.

    One implementation shared by three callers: load() uses it to find the
    Contract section (rather than the first ```toml``` fence anywhere in the
    file), check_contract's refusal-section emptiness check (Task 2) uses it
    on "5. Refusal conditions", and the ordering check on the Method section
    (Task 12) uses it too -- one place to get the fence-and-EOF handling
    right instead of three.
    """
    return _section_text(skill.body, heading, skill.path)


def skills_dir() -> Path:
    """Directory holding the skill files.

    Package data beside this module rather than at the repository root, so an
    installed (non-editable) copy can find its own skills -- the same reason
    the schemas moved. Overridable via TESTGEN_SKILLS_DIR so a candidate skill
    set can be checked without reinstalling.
    """
    override = os.environ.get("TESTGEN_SKILLS_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "skills"


def expected_skill_names() -> tuple[str, ...]:
    """Every skill this build must ship, derived from STAGES."""
    return tuple(f"tg-{stage}" for stage in STAGES if stage not in CODE_ONLY_STAGES) + (
        ORCHESTRATOR,
    )


def skill_sha256(path: Path | str) -> str:
    """Digest of a whole SKILL.md, for manifest.stages[].skill_sha256.

    The whole file, prose included: a changed Method section changes what the
    run did, so a hash over the contract block alone would call two different
    runs comparable.
    """
    return sha256_of(path)


def load(path: Path | str) -> Skill:
    """Parse one SKILL.md, raising UsageError on anything unreadable.

    The contract block is looked for within the `## Contract` section only,
    not the first ```toml``` fence anywhere in the file: under the mandated
    section order the real contract comes first, so the only way a fence
    elsewhere could be mistaken for it is a toml-fenced example placed in the
    prose *before* `## Contract` -- and if that impostor happens to be valid
    TOML with plausible values for every key, "first fence in the file" would
    silently pick it over the real one.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UsageError(f"unreadable skill file: {path} ({exc})") from exc

    headings = tuple(title for title, _ in _headings_with_lines(text.splitlines()))

    contract_section = _section_text(text, CONTRACT_HEADING, path)
    match = _TOML_BLOCK.search(contract_section)
    if match is None:
        raise UsageError(
            f"{path} has no ```toml contract block in its ## {CONTRACT_HEADING} section"
        )
    try:
        contract = tomllib.loads(match.group("body"))
    except tomllib.TOMLDecodeError as exc:
        raise UsageError(f"{path} has a contract block that is not valid TOML: {exc}") from exc

    return Skill(name=path.parent.name, path=path, contract=contract, headings=headings, body=text)


def discover(root: Path | str | None = None) -> list[Skill]:
    """Every skill under `root` (default skills_dir()), sorted by name.

    A subdirectory with no SKILL.md is skipped rather than reported: the
    missing skill is named by check_contract, which knows which names are
    required, and "tg-propose has no SKILL.md" is a better message than a
    parse failure on a directory nobody claimed was a skill.
    """
    root = Path(root) if root is not None else skills_dir()
    if not root.is_dir():
        raise UsageError(f"skills directory does not exist: {root}")
    return [
        load(child / SKILL_FILENAME)
        for child in sorted(root.iterdir())
        if (child / SKILL_FILENAME).is_file()
    ]
