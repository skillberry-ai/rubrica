"""Every YAML file under `.github/` parses, and every action it uses names a ref.

The gap this closes was measured rather than supposed. Nine tracked files live
under `.github/` -- four workflows, `dependabot.yml`, three issue templates and
the pull-request template -- and before this module not one of them was read by
anything in the repository. ruff does not parse YAML, `make test` never looked at
the directory, and GitHub Actions has never executed on the machine this branch
was written on. A workflow with a tab in its indentation, or a `steps:` list that
YAML folds into a string, would have reached the public repository unexamined,
and the first reader of the defect would have been a contributor's red PR.

Two predicates, and the second is the one with teeth. Parsing catches a
malformed file. An `uses:` with no `@ref` -- `uses: actions/checkout` -- parses
perfectly and resolves to whatever that action's default branch holds on the day
the job runs, which is a supply-chain hazard rather than a syntax error.

**Deliberately inside `make test`.** This project names three gates, and a fourth
would be a change to that contract rather than an addition to it; a pytest module
needs no new target.

One YAML subtlety worth knowing before reading a failure here: PyYAML implements
YAML 1.1, where the bare key `on:` is the boolean `True`. So a parsed workflow's
trigger block is keyed `True`, not `"on"`, and a predicate written against the
string would compute "no workflow has a trigger" and pass its own assertion. No
predicate below is keyed on `on`, and one that is added must handle both.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DOT_GITHUB = REPO_ROOT / ".github"


def _yaml_files() -> list[Path]:
    """Every YAML file under `.github/`, both spellings of the suffix.

    `.yaml` as well as `.yml` although the tree carries only `.yml` today: the
    point of a gate is the file nobody has added yet, and a `.yaml` sibling that
    fell outside the glob would be silently unscanned rather than reported.
    """
    return sorted(
        path
        for suffix in ("*.yml", "*.yaml")
        for path in DOT_GITHUB.rglob(suffix)
        if path.is_file()
    )


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _uses_values(node: object) -> list[str]:
    """Every `uses:` value anywhere in a parsed document.

    Recursive over the parsed structure rather than a grep over the text, because
    the parse is what proves the key is a mapping key and not a word inside a
    `run:` script. A `uses` whose value is not a string is returned as its repr
    so the ref predicate reports it instead of skipping it.
    """
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "uses":
                found.append(value if isinstance(value, str) else repr(value))
            else:
                found.extend(_uses_values(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_uses_values(item))
    return found


# owner/repo, optionally with a subpath, then @ and a ref that is a tag, a branch
# or a full sha -- `github/codeql-action/init@v4` and
# `pypa/gh-action-pypi-publish@release/v1` are both in the tree and both match.
# A leading `./` is a local action living in this repository, pinned by the commit
# the workflow runs at, so it needs no ref of its own.
_PINNED_USES = re.compile(r"^[\w.-]+/[\w./-]+@[\w./+-]+$")
_LOCAL_USES = re.compile(r"^\./[\w./-]+$")


def test_the_scan_set_is_not_empty():
    """Guards the two parametrized cases below against *fixture-cannot-reach*.

    Both are parametrized over `_yaml_files()`, so a moved or renamed directory
    would collect zero cases and report a green suite over an unread tree. This
    case is the one that notices.
    """
    files = _yaml_files()
    assert files, f"no YAML found under {_rel(DOT_GITHUB)}; the glob or the tree moved"
    # The four workflows are the files whose breakage a contributor feels first,
    # so name the directory rather than only the count.
    assert any(path.parent.name == "workflows" for path in files), (
        "no workflow files found; .github/workflows/ moved or emptied"
    )


@pytest.mark.parametrize("path", _yaml_files(), ids=_rel)
def test_every_yaml_file_under_dot_github_parses(path: Path):
    try:
        yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        pytest.fail(f"{_rel(path)} is not valid YAML: {exc}")


@pytest.mark.parametrize("path", _yaml_files(), ids=_rel)
def test_every_action_reference_names_a_ref(path: Path):
    """`uses: actions/checkout` parses and is still wrong.

    Unpinned, the step runs whatever that action's default branch holds on the
    day the job runs, so the workflow's behaviour changes with no commit here.
    """
    unpinned = [
        value
        for value in _uses_values(yaml.safe_load(path.read_text(encoding="utf-8")))
        if not (_PINNED_USES.match(value) or _LOCAL_USES.match(value))
    ]
    assert not unpinned, f"{_rel(path)} uses an action with no ref: {unpinned}"


# A ref is *floating* when it cannot pin a release: a bare major tag (`v7`) or a
# branch (`release/v1`) both move under the workflow as new versions ship, which is
# the point of using them. A full semver tag or a 40-character sha does not.
_EXACT_REF = re.compile(r"^v?\d+\.\d+\.\d+$|^[0-9a-f]{40}$")


def _floating_action_repos() -> set[str]:
    """The `owner/repo` of every workflow action pinned by a floating ref.

    Subpaths are dropped, because Dependabot's `dependency-name` addresses the
    repository: `github/codeql-action/init@v4` and `.../analyze@v4` are one entry,
    not two.
    """
    repos: set[str] = set()
    for path in _yaml_files():
        if path.parent.name != "workflows":
            continue
        for value in _uses_values(yaml.safe_load(path.read_text(encoding="utf-8"))):
            if _LOCAL_USES.match(value) or "@" not in value:
                continue
            target, _, ref = value.partition("@")
            if _EXACT_REF.match(ref):
                continue
            repos.add("/".join(target.split("/")[:2]))
    return repos


def _actions_ignore_names() -> set[str]:
    """`dependency-name`s ignored in dependabot.yml's github-actions block."""
    config = yaml.safe_load((DOT_GITHUB / "dependabot.yml").read_text(encoding="utf-8"))
    return {
        entry["dependency-name"]
        for update in config["updates"]
        if update.get("package-ecosystem") == "github-actions"
        for entry in update.get("ignore", [])
        if "dependency-name" in entry
    }


def test_the_floating_ref_scan_finds_the_actions_the_tree_actually_uses():
    """Guards the case below against *fixture-cannot-reach* the same way
    test_the_scan_set_is_not_empty does: an empty left-hand side makes a subset
    assertion vacuously true, so a broken parse would read as full coverage."""
    repos = _floating_action_repos()
    assert repos, "no floating-ref actions found; the workflow scan or the tree moved"
    assert "github/codeql-action" in repos, (
        f"codeql-action is pinned by floating major tag in the tree but not found: {repos}"
    )


def test_every_floating_ref_action_is_ignored_for_minor_and_patch():
    """The ignore block's stated policy has to cover every action it describes.

    Its comment gives the reason in general terms -- we float the major tag, so a
    minor/patch PR *narrows* the ref and adds churn -- and that reason applies to
    every action referenced that way, not to whichever one was listed first. An
    action pinned `@v7` and absent from the block gets exactly the narrowing PR the
    comment says the block prevents, on the first weekly run, and nothing in the
    repository would have reported it.
    """
    missing = sorted(_floating_action_repos() - _actions_ignore_names())
    assert not missing, (
        "these actions float their major ref but are not ignored for minor/patch "
        f"in .github/dependabot.yml: {missing}"
    )
