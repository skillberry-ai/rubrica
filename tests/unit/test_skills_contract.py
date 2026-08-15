"""Every contract declaration, against the code that owns the name.

The checks here are the only mechanical grip this project has on a prompt. A
schema gates an artifact a stage wrote; nothing gates the text that told the
stage what to write, so a SKILL.md naming `world-model` (the schema kind) where
it means `world_model` (the RunPaths attribute) would be discovered by a model
at run time, after the dispatch was paid for.

Each test below mutates one key of an otherwise-valid contract, which is the
deletion-mutation dual: the fixture is valid, so a finding can only come from
the mutated key.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from rubrica.cli import subcommand_names
from rubrica.errors import UsageError
from rubrica.paths import STAGES, RunPaths
from rubrica.skills import (
    CODE_ONLY_STAGES,
    ORCHESTRATOR,
    SECTIONS,
    SKILL_FILENAME,
    check_all,
    check_contract,
    discover,
    expected_skill_names,
    load,
)
from rubrica.validate import ARTIFACT_SCHEMAS, STAGE_ARTIFACTS

CONTRACTS: dict[str, dict[str, object]] = {
    "rb-extract": {
        "stage": "extract",
        "reads": ["manifest", "input_file"],
        "writes": ["claims"],
        "schemas": ["claims"],
        "invokes": ["validate"],
    },
    ORCHESTRATOR: {
        "reads": ["manifest"],
        "writes": ["decisions"],
        "invokes": ["validate", "check-refs"],
    },
}


def _toml(contract: dict[str, object]) -> str:
    lines = []
    for key, value in contract.items():
        if isinstance(value, str):
            lines.append(f'{key} = "{value}"')
        else:
            inner = ", ".join(f'"{v}"' for v in value)
            lines.append(f"{key} = [{inner}]")
    return "```toml\n" + "\n".join(lines) + "\n```\n"


def write_skill(
    root: Path, name: str, contract=None, headings=SECTIONS, refusals="Refuse."
) -> Path:
    """A valid SKILL.md for `name`, with knobs for each negative case."""
    contract = CONTRACTS[name] if contract is None else contract
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        f"name: {name}",
        "description: d.",
        "---",
        "",
        f"# {name}",
        "",
        "Purpose.",
        "",
        "## Contract",
        "",
        _toml(contract),
    ]
    for heading in headings:
        body = refusals if heading == SECTIONS[-1] else "Body."
        lines += ["", f"## {heading}", "", body]
    path = directory / SKILL_FILENAME
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_skill_with_raw_contract(root: Path, name: str, toml_body: str) -> Path:
    """Like write_skill, but for contracts _toml() cannot render: it only
    knows how to serialize a bare string or a flat list of strings, so an
    array-of-tables or a nested array (the two shapes that reach set()
    un-stringified) has to be written out as literal TOML text instead.
    """
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        f"name: {name}",
        "description: d.",
        "---",
        "",
        f"# {name}",
        "",
        "Purpose.",
        "",
        "## Contract",
        "",
        "```toml",
        toml_body,
        "```",
    ]
    for heading in SECTIONS:
        body = "Refuse." if heading == SECTIONS[-1] else "Body."
        lines += ["", f"## {heading}", "", body]
    path = directory / SKILL_FILENAME
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def messages(findings) -> str:
    return " | ".join(f.message for f in findings)


def test_a_valid_contract_produces_no_findings(tmp_path):
    """The baseline every mutation below is measured against."""
    assert check_contract(load(write_skill(tmp_path, "rb-extract"))) == []


def test_the_orchestrator_contract_is_valid_without_a_stage(tmp_path):
    assert check_contract(load(write_skill(tmp_path, ORCHESTRATOR))) == []


def test_an_unknown_stage_is_reported(tmp_path):
    """rb-bogus/ declaring stage="bogus": the directory name agrees with the
    stage (f"rb-{stage}" == "rb-bogus"), so the stage-mismatch arm cannot fire
    as a substitute the way it does for stage="extraction" in a rb-extract/
    directory (that fixture's mismatch arm also names "extraction" in its
    message, so a pointer-and-substring check alone cannot tell which arm
    produced the finding). Asserting the count is what makes a disabled
    unknown-stage check visible: with it disabled, the elif chain falls
    through to the mismatch arm, which does not fire here (the names agree),
    so the count drops from 1 to 0 rather than staying at 1 via a different
    message.
    """
    contract = dict(CONTRACTS["rb-extract"], stage="bogus")
    findings = check_contract(load(write_skill(tmp_path, "rb-bogus", contract)))
    assert len(findings) == 1
    assert [f.pointer for f in findings] == ["/stage"]
    assert "bogus" in messages(findings)


def test_a_stage_that_disagrees_with_the_directory_name_is_reported(tmp_path):
    """A SKILL.md in rb-propose/ declaring stage="score" would be dispatched for
    propose and validated as score -- the two halves of one run disagreeing about
    which stage just ran. "score" is a real member of STAGES, so the
    unknown-stage arm cannot be the one that fires here -- only the mismatch arm
    can, which is the fixture this test needs to isolate that arm from the one
    above.
    """
    contract = dict(CONTRACTS["rb-extract"], stage="score", schemas=["coverage"])
    findings = check_contract(load(write_skill(tmp_path, "rb-extract", contract)))
    assert len(findings) == 1
    assert "/stage" in [f.pointer for f in findings]
    assert "rb-extract" in messages(findings) and "score" in messages(findings)


def test_the_orchestrator_may_not_declare_a_stage(tmp_path):
    contract = dict(CONTRACTS[ORCHESTRATOR], stage="reconcile")
    findings = check_contract(load(write_skill(tmp_path, ORCHESTRATOR, contract)))
    assert [f.pointer for f in findings] == ["/stage"]


@pytest.mark.parametrize("declared", [["claims"], "claims", []])
def test_the_orchestrator_may_not_declare_schemas(tmp_path, declared):
    """The mirror of the stage finding above, and it did not exist.

    `if skill.name != ORCHESTRATOR and stage in STAGES:` wrapped the whole
    schemas block, so rb-orchestrate declaring `schemas = ["claims"]` -- or the
    non-list `schemas = "claims"` -- exited 0 with no finding, while the same file
    declaring a `stage` was correctly reported. The `schemas` key belongs to a
    stage's layer-1 gate; the orchestrator has no stage, so any value here is
    meaningless, including the empty list. Three values because the old guard
    skipped on the key's *owner*, not on its shape: no value of it could fire.
    """
    contract = dict(CONTRACTS[ORCHESTRATOR], schemas=declared)
    findings = check_contract(load(write_skill(tmp_path, ORCHESTRATOR, contract)))
    assert [f.pointer for f in findings] == ["/schemas"]
    assert "must not declare schemas" in messages(findings)


def test_a_stage_skill_still_gets_the_schemas_block_it_always_had(tmp_path):
    """The other half of the split: the stage path is unchanged.

    Restructuring the guard from one compound condition into two branches must
    not cost the stage skills their omission and invention checks, which is the
    only reason the compound condition looked safe to write in the first place.
    """
    contract = dict(CONTRACTS["rb-extract"], schemas=["coverage"])
    findings = check_contract(load(write_skill(tmp_path, "rb-extract", contract)))
    messages_seen = messages(findings)
    assert [f.pointer for f in findings] == ["/schemas", "/schemas"]
    assert "is not gated on" in messages_seen and "omits artifact kind" in messages_seen


def test_a_non_string_stage_is_reported(tmp_path):
    """`stage = ["extract"]` is a shape mistake (brackets typed where a bare
    string was meant), not a spelling one -- a distinct finding from "unknown
    stage" so the message says "must be a string" rather than the misleading
    "which is not one of: ...".
    """
    contract = dict(CONTRACTS["rb-extract"], stage=["extract"])
    findings = check_contract(load(write_skill(tmp_path, "rb-extract", contract)))
    assert len(findings) == 1
    assert [f.pointer for f in findings] == ["/stage"]
    assert "must be a string" in messages(findings)


@pytest.mark.parametrize("key", ["reads", "writes"])
def test_a_path_that_is_not_a_RunPaths_attribute_is_reported(tmp_path, key):
    """The schema kind is `world-model`; the RunPaths attribute is `world_model`.
    A skill that declares the former names nothing the code can resolve.
    """
    contract = dict(CONTRACTS["rb-extract"])
    contract[key] = ["world-model"]
    findings = check_contract(load(write_skill(tmp_path, "rb-extract", contract)))
    assert [f.pointer for f in findings] == [f"/{key}/0"]
    assert "world-model" in messages(findings)


@pytest.mark.parametrize("key", ["reads", "writes"])
def test_a_private_RunPaths_attribute_is_reported(tmp_path, key):
    """`_instance_dir_names` is a real RunPaths attribute -- hasattr() alone
    would accept it -- but it is a private helper, not part of the layout API
    a skill declares artifacts through.
    """
    contract = dict(CONTRACTS["rb-extract"])
    contract[key] = ["_instance_dir_names"]
    findings = check_contract(load(write_skill(tmp_path, "rb-extract", contract)))
    assert [f.pointer for f in findings] == [f"/{key}/0"]
    assert "_instance_dir_names" in messages(findings)


@pytest.mark.parametrize("key", ["reads", "writes"])
def test_every_declared_name_is_checked_not_only_the_first(tmp_path, key):
    """Otherwise a loop that returns on its first finding would pass the test
    above while leaving every later entry unchecked.
    """
    contract = dict(CONTRACTS["rb-extract"])
    contract[key] = ["manifest", "world-model", "nope"]
    findings = check_contract(load(write_skill(tmp_path, "rb-extract", contract)))
    assert [f.pointer for f in findings] == [f"/{key}/1", f"/{key}/2"]


@pytest.mark.parametrize("key", ["reads", "writes"])
def test_a_non_list_reads_or_writes_is_reported_once_not_as_a_cascade(tmp_path, key):
    """`reads = "manifest"` (bare string, brackets forgotten) is the worst
    failure shape this module could have if left unchecked: Skill.declared()
    tolerates it into [], and a loop over [] reports nothing at all, silence
    from the one component whose job is catching declaration mistakes. This
    must be exactly one finding, naming the key -- not zero, and not a
    finding per character of the string (which iterating "manifest" directly
    would produce).
    """
    contract = dict(CONTRACTS["rb-extract"])
    contract[key] = "manifest"
    findings = check_contract(load(write_skill(tmp_path, "rb-extract", contract)))
    assert [f.pointer for f in findings] == [f"/{key}"]
    assert "manifest" in messages(findings) and "list" in messages(findings)


def test_an_omitted_artifact_kind_is_reported(tmp_path):
    """instantiate is gated on both seed and expected. A skill that names only
    the seed is the drift a subset check would wave through -- and an oracle
    nobody wrote is a scenario that emits no test.
    """
    contract = {
        "stage": "instantiate",
        "reads": ["world_model", "scenarios"],
        "writes": ["seed", "expected", "rationale"],
        "schemas": ["seed"],
        "invokes": ["validate"],
    }
    findings = check_contract(load(write_skill(tmp_path, "rb-instantiate", contract)))
    assert [f.pointer for f in findings] == ["/schemas"]
    assert "expected" in messages(findings)


def test_an_invented_artifact_kind_is_reported(tmp_path):
    contract = dict(CONTRACTS["rb-extract"], schemas=["claims", "report"])
    findings = check_contract(load(write_skill(tmp_path, "rb-extract", contract)))
    assert [f.pointer for f in findings] == ["/schemas"]
    assert "report" in messages(findings)


def test_an_omission_and_an_invention_are_reported_separately(tmp_path):
    """Two messages, not one: "omits X" and "declares Y" tell the editor which
    direction is wrong, and a single symmetric-difference message does not.
    """
    contract = dict(CONTRACTS["rb-extract"], schemas=["report"])
    findings = check_contract(load(write_skill(tmp_path, "rb-extract", contract)))
    assert len(findings) == 2
    assert {"claims", "report"} <= set(messages(findings).replace("'", " ").split())


def test_a_non_list_schemas_is_reported_once_not_alongside_the_omission_check(tmp_path):
    """`schemas = "claims"` must not also trip the omission check: set("claims")
    is its characters, not its declared kind, and a set built from that would
    say "omits ... 'a', 'c', 'i', 'l', 'm', 's'" alongside the shape finding --
    two messages that contradict each other about what is wrong. This must be
    exactly one finding.
    """
    contract = dict(CONTRACTS["rb-extract"], schemas="claims")
    findings = check_contract(load(write_skill(tmp_path, "rb-extract", contract)))
    assert [f.pointer for f in findings] == ["/schemas"]
    assert "claims" in messages(findings) and "list" in messages(findings)


def test_a_schemas_array_of_tables_is_reported_not_a_crash(tmp_path):
    """`schemas = [{kind = "claims"}]` is a plausible reach for more structure
    -- an array of tables is a natural TOML idiom -- but a dict is unhashable,
    so set(schemas_value) raises TypeError before the fix. This must surface
    as a finding naming the dict and its type, not a Python exception.
    """
    toml_body = (
        'stage = "extract"\n'
        'reads = ["manifest", "input_file"]\n'
        'writes = ["claims"]\n'
        'schemas = [{kind = "claims"}]\n'
        'invokes = ["validate"]'
    )
    findings = check_contract(
        load(write_skill_with_raw_contract(tmp_path, "rb-extract", toml_body))
    )
    assert [f.pointer for f in findings] == ["/schemas"]
    assert "claims" in messages(findings) and "dict" in messages(findings)


def test_a_schemas_nested_array_is_reported_not_a_crash(tmp_path):
    """`schemas = [["claims"]]` is a second, differently-shaped ill-typed
    element: a list is unhashable too, so set(schemas_value) raises the same
    TypeError as the array-of-tables case above, by a different route (a
    nested array rather than a table). Both must be caught by the same
    per-element type check, not just the one shape that happened to be
    named first.
    """
    toml_body = (
        'stage = "extract"\n'
        'reads = ["manifest", "input_file"]\n'
        'writes = ["claims"]\n'
        'schemas = [["claims"]]\n'
        'invokes = ["validate"]'
    )
    findings = check_contract(
        load(write_skill_with_raw_contract(tmp_path, "rb-extract", toml_body))
    )
    assert [f.pointer for f in findings] == ["/schemas"]
    assert "must be a string" in messages(findings)


def test_an_unknown_subcommand_is_reported(tmp_path):
    """`check_refs` with an underscore is the plausible typo: it is how the
    Python function is spelled and it is not what argparse accepts.
    """
    contract = dict(CONTRACTS["rb-extract"], invokes=["validate", "check_refs"])
    findings = check_contract(load(write_skill(tmp_path, "rb-extract", contract)))
    assert [f.pointer for f in findings] == ["/invokes/1"]
    assert "check_refs" in messages(findings)


def test_every_real_subcommand_is_accepted(tmp_path):
    """Pins the check against the CLI rather than a hand-kept list: if a
    subcommand is added and subcommand_names() does not see it, this fails.
    """
    contract = dict(CONTRACTS["rb-extract"], invokes=list(subcommand_names()))
    assert check_contract(load(write_skill(tmp_path, "rb-extract", contract))) == []


def test_a_non_list_invokes_is_reported(tmp_path):
    """`invokes = "validate"` (bare string) must be reported by shape, not
    silently treated as declaring nothing.
    """
    contract = dict(CONTRACTS["rb-extract"], invokes="validate")
    findings = check_contract(load(write_skill(tmp_path, "rb-extract", contract)))
    assert [f.pointer for f in findings] == ["/invokes"]
    assert "validate" in messages(findings) and "list" in messages(findings)


def test_a_missing_section_is_reported(tmp_path):
    without_refusals = SECTIONS[:-1]
    findings = check_contract(load(write_skill(tmp_path, "rb-extract", headings=without_refusals)))
    assert SECTIONS[-1] in messages(findings)


def test_sections_out_of_order_are_reported(tmp_path):
    """Method before Inputs reads as a skill that acts before it reads."""
    scrambled = (SECTIONS[2], SECTIONS[0], SECTIONS[1], SECTIONS[3], SECTIONS[4])
    findings = check_contract(load(write_skill(tmp_path, "rb-extract", headings=scrambled)))
    assert findings, "an out-of-order section list must be reported"


def test_extra_headings_between_the_sections_are_allowed(tmp_path):
    """A subsequence, not an equality: a skill may add its own headings."""
    with_extras = (
        SECTIONS[0],
        SECTIONS[1],
        "Worked example",
        SECTIONS[2],
        SECTIONS[3],
        SECTIONS[4],
    )
    assert check_contract(load(write_skill(tmp_path, "rb-extract", headings=with_extras))) == []


def test_an_empty_refusal_section_is_reported(tmp_path):
    """Section 5 is the most important prompt-level decision in the system. A
    heading with nothing under it is how that decision silently is not made.
    """
    findings = check_contract(load(write_skill(tmp_path, "rb-extract", refusals="")))
    assert findings, "an empty refusal-conditions section must be reported"
    assert SECTIONS[-1] in messages(findings)


def test_a_refusal_section_at_end_of_file_is_read_correctly(tmp_path):
    """The section-body slice must handle EOF, not only the next `## ` heading.
    Section 5 is last in every real skill, so an implementation that looks for a
    following heading would find every refusal section empty -- and the test
    above would pass for the wrong reason.
    """
    assert check_contract(load(write_skill(tmp_path, "rb-extract"))) == []
    path = write_skill(tmp_path, "rb-extract")
    assert path.read_text(encoding="utf-8").rstrip().endswith("Refuse.")


def test_check_all_reports_a_skill_STAGES_demands_but_the_directory_lacks(tmp_path):
    write_skill(tmp_path, "rb-extract")
    findings = check_all(tmp_path)
    missing = messages(findings)
    for name in expected_skill_names():
        if name != "rb-extract":
            assert name in missing, f"{name} must be reported missing"


def test_check_all_reports_a_directory_that_is_not_a_known_skill(tmp_path):
    for name in expected_skill_names():
        contract = CONTRACTS.get(name)
        if contract is None:
            continue
        write_skill(tmp_path, name)
    write_skill(tmp_path, "rb-extract")
    (tmp_path / "rb-extractt" / "SKILL.md").parent.mkdir()
    (tmp_path / "rb-extractt" / "SKILL.md").write_text("stray\n", encoding="utf-8")
    assert "rb-extractt" in messages(check_all(tmp_path))


@pytest.mark.skipif(
    os.geteuid() == 0, reason="chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)"
)
def test_discover_on_an_unreadable_skills_directory_is_a_usage_error(tmp_path):
    """root.is_dir() is true -- the directory exists -- but chmod(0o000) denies
    the read+execute permission root.iterdir() needs to list it, so it raises a
    bare PermissionError (an OSError), not the empty list a missing-or-empty
    directory would give and not the UsageError the sibling check two lines up
    already raises for a directory that does not exist at all. Left unwrapped,
    this would reach cli.py's generic except Exception and become exit 1 with a
    fabricated [internal] finding advising a stage repair for a filesystem
    permission problem that has nothing to do with any run.
    """
    root = tmp_path / "skills"
    root.mkdir()
    write_skill(root, "rb-extract")
    root.chmod(0o000)
    try:
        with pytest.raises(UsageError) as excinfo:
            discover(root)
    finally:
        root.chmod(0o755)  # restore so tmp_path's own cleanup can remove it
    assert str(root) in str(excinfo.value)


@pytest.mark.skipif(
    os.geteuid() == 0, reason="chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)"
)
def test_check_all_on_an_unreadable_skills_directory_is_a_usage_error(tmp_path):
    """The same permission-denied root as discover() above, through check_all()
    instead: both functions share the walk (and now the mapping) in
    skills._skill_dirs, so this pins that the sharing did not leave check_all()
    with a stale, unwrapped iterdir() call of its own.
    """
    root = tmp_path / "skills"
    root.mkdir()
    write_skill(root, "rb-extract")
    root.chmod(0o000)
    try:
        with pytest.raises(UsageError) as excinfo:
            check_all(root)
    finally:
        root.chmod(0o755)
    assert str(root) in str(excinfo.value)


@pytest.mark.skipif(
    os.geteuid() == 0, reason="chmod-based deny is bypassed under CAP_DAC_OVERRIDE (root)"
)
def test_discover_on_a_skill_directory_that_denies_stat_is_a_usage_error(tmp_path):
    """The narrower case: the *root* is readable, but a *child* skill directory
    is not, so root.iterdir() itself succeeds and the failure is in
    `(child / SKILL_FILENAME).is_file()` needing to stat inside a directory it
    cannot enter. Confirmed by direct experiment, not assumed from the docs,
    that Path.is_file() does not swallow this the way it swallows a missing
    path: it only ignores ENOENT/ENOTDIR/EBADF/ELOOP internally, and
    permission-denied is none of those, so it raises here exactly as
    root.iterdir() does above, into the same except OSError in _skill_dirs.
    """
    root = tmp_path / "skills"
    root.mkdir()
    child = write_skill(root, "rb-extract").parent
    child.chmod(0o000)
    try:
        with pytest.raises(UsageError) as excinfo:
            discover(root)
    finally:
        child.chmod(0o755)
    assert str(root) in str(excinfo.value)


def test_the_RunPaths_names_the_real_skills_use_all_exist():
    """Guards the check itself against the attribute API moving under it.

    If paths.RunPaths ever renames `coverage_latest`, this fails here rather
    than in the middle of a dispatched score stage.
    """
    for name in (
        "manifest",
        "input_file",
        "claims",
        "world_model",
        "scenarios",
        "coverage_round",
        "coverage_latest",
        "seed",
        "expected",
        "rationale",
        "verdict",
        "task_dir",
        "report",
        "decisions",
    ):
        assert hasattr(RunPaths, name), name


def test_every_stage_in_STAGES_has_a_schema_entry():
    """The precondition check 4 rests on. STAGE_ARTIFACTS must be total over
    STAGES, or `STAGE_ARTIFACTS[stage]` raises KeyError inside check_contract
    and a repairable declaration becomes an exit-2 traceback.
    """
    for stage in STAGES:
        assert stage in STAGE_ARTIFACTS
        for kind in STAGE_ARTIFACTS[stage]:
            assert kind in ARTIFACT_SCHEMAS


def test_survey_is_code_only_but_triage_is_not():
    """survey mints run ids and timestamps, exactly like intake -- the design
    spec forbids a skill from inventing either, so survey has no SKILL.md and
    must never grow one. triage is not in this set: unlike survey, it carries
    judgment (which candidates matter for the target and objective), so it is
    a real skill stage and rb-triage arrives in a later task.
    """
    assert "survey" in CODE_ONLY_STAGES
    assert "triage" not in CODE_ONLY_STAGES
