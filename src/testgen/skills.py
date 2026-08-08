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
from testgen.findings import Finding
from testgen.paths import STAGES, RunPaths

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
    except (OSError, UnicodeDecodeError) as exc:
        # UnicodeDecodeError is a ValueError, not an OSError, so it needs its
        # own arm here: cli.py's outer catch deliberately excludes ValueError
        # (that is the class of error a repair prompt could plausibly fix),
        # and a mis-encoded prompt file is not one of those -- it is exactly
        # the human-authored, unrepairable case UsageError exists for.
        raise UsageError(f"unreadable skill file: {path} ({exc})") from exc

    headings = tuple(title for title, _ in _headings_with_lines(text.splitlines()))

    contract_section = _section_text(text, CONTRACT_HEADING, path)
    # Exactly one fence, not "the first" or "the last": a second toml block
    # in a section whose entire purpose is to hold one -- a deprecated or
    # before/after example, say -- is ambiguous, and an ambiguous
    # human-authored file is refused rather than resolved in the reader's
    # favour by a guess.
    matches = list(_TOML_BLOCK.finditer(contract_section))
    if len(matches) != 1:
        raise UsageError(
            f"{path} has {len(matches)} ```toml blocks in its ## {CONTRACT_HEADING} "
            "section; exactly one is required"
        )
    try:
        contract = tomllib.loads(matches[0].group("body"))
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


def _is_subsequence(needles: tuple[str, ...], haystack: tuple[str, ...]) -> bool:
    """Whether every item of `needles` occurs in `haystack`, in the same
    relative order, with other items allowed in between.

    Deliberately weaker than "is a prefix" or "equals": a skill may add its
    own `##` headings (a worked example, a glossary) between or after the five
    required ones, and only their relative order is part of the contract.
    """
    iterator = iter(haystack)
    return all(any(item == needle for item in iterator) for needle in needles)


def check_contract(skill: Skill) -> list[Finding]:
    """One skill's declaration against the code that owns each name.

    Findings, never raises: every problem here names a line a human can edit,
    which is exit 1's contract. An unreadable file is load()'s UsageError and
    exit 2, because there is nothing to name.
    """
    # Imported here rather than at module scope: cli imports skills for the
    # check-skills subcommand, so a top-level import of cli from skills would
    # be circular. Same pattern refs.check_report uses for smoke.
    from testgen.cli import subcommand_names
    from testgen.validate import ARTIFACT_SCHEMAS, STAGE_ARTIFACTS

    out: list[Finding] = []

    def report(pointer: str, message: str) -> None:
        out.append(Finding(skill.path, "skill", pointer, message))

    stage = skill.contract.get("stage")
    # A wrong-typed stage is checked before every branch below that assumes
    # `stage` is a string or None: `stage not in STAGES` would already catch
    # a non-string value (no int or list is ever a member of a tuple of
    # stage names), but folding that into "unknown stage" makes the message
    # say "which is not one of: ..." for a TOML author who wrote `stage =
    # ["extract"]` by accident -- a shape mistake, not a spelling one. One
    # named check, and the elif chain below never runs on a bad type, so this
    # never cascades into a second, confusing finding for the same key.
    if stage is not None and not isinstance(stage, str):
        report(
            "/stage",
            f"declares stage {stage!r}, which must be a string, not {type(stage).__name__}",
        )
    elif skill.name == ORCHESTRATOR:
        if stage is not None:
            report(
                "/stage",
                f"{ORCHESTRATOR} is not a stage: it dispatches them, so it must not "
                "declare a stage",
            )
    elif stage not in STAGES:
        report("/stage", f"declares stage {stage!r}, which is not one of: {', '.join(STAGES)}")
    elif skill.name != f"tg-{stage}":
        report(
            "/stage",
            f"lives in {skill.name}/ but declares stage {stage!r}; the orchestrator "
            f"dispatches it as {skill.name} and validates it as {stage!r}",
        )

    for key in ("reads", "writes"):
        value = skill.contract.get(key, [])
        if not isinstance(value, list):
            # Checked directly against the contract, not skill.declared(key):
            # declared() is deliberately tolerant (returns [] for a bad
            # shape) so load() itself never raises on this, but that same
            # tolerance means the per-element loop below would silently
            # iterate zero times and report nothing -- the worst failure
            # shape this module has, since a real author who forgets the
            # brackets around a single name (`reads = "manifest"`) gets no
            # finding at all. `continue` skips the loop so a bad shape
            # produces one finding about the shape, not zero.
            report(
                f"/{key}",
                f"declares {key} = {value!r}, which must be a list, not {type(value).__name__}",
            )
            continue
        for i, name in enumerate(value):
            if not isinstance(name, str) or not hasattr(RunPaths, name) or name.startswith("_"):
                # name.startswith("_") is folded into the same finding as "not
                # an attribute at all": a skill declares artifacts through
                # RunPaths's public layout API, and a private helper (e.g.
                # _instance_dir_names) is an implementation detail, not part
                # of the contract, even though hasattr() would otherwise
                # accept it.
                report(
                    f"/{key}/{i}",
                    f"names {name!r}, which is not a RunPaths attribute; declare artifacts "
                    "by their RunPaths name, never as a literal path",
                )

    if skill.name != ORCHESTRATOR and stage in STAGES:
        schemas_value = skill.contract.get("schemas", [])
        if not isinstance(schemas_value, list):
            # Same shape-before-content ordering as reads/writes above: if
            # schemas itself is the wrong type, the omission/invention checks
            # below would compare a set built from set("a string") -- its
            # characters, not its declared kind -- and produce a confusing
            # second finding that contradicts this one. Reporting the shape
            # and stopping keeps it to one finding.
            report(
                "/schemas",
                f"declares schemas = {schemas_value!r}, which must be a list, not "
                f"{type(schemas_value).__name__}",
            )
        else:
            # Same shape-before-content ordering one level in: a well-typed
            # list can still hold ill-typed elements (`schemas = [{kind =
            # "claims"}]` or `schemas = [["claims"]]` -- an array of tables is
            # a natural TOML idiom someone reaches for meaning more
            # structure). set(schemas_value) would raise TypeError on the
            # dict (unhashable) or silently accept the list (hashable only
            # by identity, so it can never equal a string in `required` and
            # would just look like a phantom invented kind) -- either way
            # not a finding a human can act on. Checking every element's
            # type before the set() call, and skipping the omission/
            # invention comparison entirely when one fails, keeps this to
            # one finding per bad element instead of a crash or a confusing
            # mix of a shape complaint and a wrong content complaint.
            bad = [(i, kind) for i, kind in enumerate(schemas_value) if not isinstance(kind, str)]
            if bad:
                for i, kind in bad:
                    report(
                        "/schemas",
                        f"declares artifact kind {kind!r} at index {i}, which must be a "
                        f"string, not {type(kind).__name__}",
                    )
            else:
                declared = set(schemas_value)
                required = set(STAGE_ARTIFACTS[stage])
                for kind in sorted(declared - required):
                    if kind not in ARTIFACT_SCHEMAS:
                        report("/schemas", f"declares artifact kind {kind!r}, which has no schema")
                    else:
                        report(
                            "/schemas",
                            f"declares artifact kind {kind!r}, which stage {stage!r} is not "
                            "gated on",
                        )
                omitted = sorted(required - declared)
                if omitted:
                    report(
                        "/schemas",
                        f"omits artifact kind(s) {', '.join(repr(k) for k in omitted)}, which "
                        f"stage {stage!r} is gated on",
                    )

    known = subcommand_names()
    invokes_value = skill.contract.get("invokes", [])
    if not isinstance(invokes_value, list):
        report(
            "/invokes",
            f"declares invokes = {invokes_value!r}, which must be a list, not "
            f"{type(invokes_value).__name__}",
        )
    else:
        for i, name in enumerate(invokes_value):
            if name not in known:
                report(
                    f"/invokes/{i}",
                    f"invokes {name!r}, which is not a testgen subcommand; the subcommands "
                    f"are: {', '.join(known)}",
                )

    for heading in SECTIONS:
        if heading not in skill.headings:
            report("", f"has no '## {heading}' section")
    if not _is_subsequence(tuple(h for h in SECTIONS if h in skill.headings), skill.headings):
        report("", f"sections are out of order; the required order is: {', '.join(SECTIONS)}")

    refusals = SECTIONS[-1]
    # section_body is Task 1's, fence-aware and EOF-aware. Do not re-implement
    # the slice here: section 5 is last in every real skill, so a second
    # implementation that required a following heading would read every
    # refusal section as empty and this check would fire on every correct
    # skill.
    if refusals in skill.headings and not section_body(skill, refusals).strip():
        report(
            "",
            f"'## {refusals}' is empty; a skill with no stated refusal conditions "
            "confabulates under under-specification rather than recording a gap",
        )
    return out


def check_all(root: Path | str | None = None) -> list[Finding]:
    """Every skill's contract, plus the roster check no single skill can make.

    Deliberately does not build on discover(): discover() calls load() on
    every SKILL.md it finds, unconditionally, so an unrecognised directory
    with a broken SKILL.md (a scratch copy, a typo'd name) would raise before
    this function got to say what is actually wrong with it -- that it is not
    one of the skills this pipeline dispatches. So a directory's name is
    checked against expected_skill_names() *before* it is loaded: a name this
    build does not recognise is reported without parsing its contents, and
    only a directory this build does recognise as one of its own skills is
    handed to load(), whose UsageError is left to propagate for that name --
    an official skill's SKILL.md that cannot even be parsed is human-authored
    and unrepairable by re-prompting, the same exit-2 class as a malformed
    --agents roster, and folding it into the finding list here would
    silently downgrade it to a repairable exit-1 defect.
    """
    root = Path(root) if root is not None else skills_dir()
    if not root.is_dir():
        raise UsageError(f"skills directory does not exist: {root}")

    expected = set(expected_skill_names())
    found_names: set[str] = set()
    out: list[Finding] = []

    for child in sorted(root.iterdir()):
        skill_path = child / SKILL_FILENAME
        if not skill_path.is_file():
            continue
        name = child.name
        if name not in expected:
            out.append(
                Finding(
                    skill_path,
                    "skill",
                    "",
                    f"{name} is not a skill this pipeline dispatches; the skills are: "
                    f"{', '.join(sorted(expected))}",
                )
            )
            continue
        found_names.add(name)
        out.extend(check_contract(load(skill_path)))

    for name in sorted(expected - found_names):
        out.append(Finding(root, "skill", "", f"no skill named {name}, which paths.STAGES demands"))
    return out
