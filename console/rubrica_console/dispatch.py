"""How the console calls `scripts/dispatch-stage.sh`, and how it reads one back.

The script is called exactly as a human calls it -- stage, run directory, an
optional slice id -- with the environment variables it documents. The console
adds nothing to the prompt: the only re-dispatch additions are the ones the
script itself reads from files (`RUBRICA_FINDINGS_FILE`, `RUBRICA_RESEED`,
`RUBRICA_REJECT`), so the "verbatim machine text, never paraphrased" rule in
CLAUDE.md is the script's to keep, and it already keeps it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import rubrica
from rubrica_console.credentials import SCRUBBED

# The script uses `mapfile`, which macOS's /bin/bash 3.2 lacks; measured on this
# project's own Macs it dies with "could not resolve the write scope" before
# dispatching. A Homebrew bash is tried first for that reason.
_BASH_CANDIDATES = ("/opt/homebrew/bin/bash", "/usr/local/bin/bash", "bash")

_COST_LINE = re.compile(r"^cost\s+\$([0-9.]+) over (\d+) turns")


def repo_root() -> Path:
    """The checkout this package was imported from (`src/rubrica` -> repo)."""
    return Path(rubrica.__file__).resolve().parents[2]


def default_script() -> Path:
    return repo_root() / "scripts" / "dispatch-stage.sh"


def find_bash() -> str | None:
    """The first bash whose major version is at least 4, or None."""
    for candidate in _BASH_CANDIDATES:
        path = candidate if os.path.isabs(candidate) else shutil.which(candidate)
        if not path or not os.access(path, os.X_OK):
            continue
        try:
            out = subprocess.run(
                [path, "-c", "echo ${BASH_VERSINFO[0]}"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            continue
        if out.isdigit() and int(out) >= 4:
            return path
    return None


@dataclass
class Progress:
    turns: int = 0
    last: str = ""
    cost: float | None = None
    finished: bool = False
    # The model call's own error, when the transcript ends in one ("Failed to
    # authenticate. API Error: 401 ..."), so the page can show why instead of an
    # exit code.
    error: str = ""


def read_progress(log: Path) -> Progress:
    """What a dispatch log says so far.

    The script tees Claude Code's stream-json to stdout, then prints a closing
    summary whose `cost` line is the authoritative spend. Before that line
    exists, the stream gives the turn count and the last tool the model used,
    which is what "is it still doing something" needs.
    """
    progress = Progress()
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return progress
    for line in text.splitlines():
        match = _COST_LINE.match(line)
        if match:
            progress.cost = float(match.group(1))
            progress.turns = int(match.group(2))
            progress.finished = True
            continue
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "assistant":
            progress.turns += 1
            content = (event.get("message") or {}).get("content") or []
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    target = block.get("input") or {}
                    hint = target.get("file_path") or target.get("command") or ""
                    progress.last = f"{block.get('name', 'tool')} {str(hint)[:120]}".strip()
        elif event.get("type") == "result":
            cost = event.get("total_cost_usd")
            if progress.cost is None and isinstance(cost, (int, float)):
                progress.cost = float(cost)
            if event.get("is_error"):
                progress.error = str(event.get("result") or event.get("subtype") or "error")[:500]
    return progress


def env_for(
    *,
    credentials: dict[str, str],
    lab: Path,
    model: str,
    effort: str,
    budget: str | None = None,
    findings_file: Path | None = None,
    reseed: bool = False,
    reject: list[str] | None = None,
) -> dict[str, str]:
    # Model access comes from the console's own credentials and nowhere else: an
    # inherited ANTHROPIC_* from the shell the server was started in would decide,
    # silently, which account a dispatch bills and whether it can authenticate.
    env = {k: v for k, v in os.environ.items() if k not in SCRUBBED}
    env.update(credentials)
    env["RUBRICA_LAB"] = str(lab)
    env["RUBRICA_MODEL"] = model
    env["RUBRICA_EFFORT"] = effort
    # Cleared, then set only when asked for: an inherited value from the shell the
    # server was started in would quietly change a dispatch the UI did not ask for.
    for key in ("RUBRICA_BUDGET", "RUBRICA_FINDINGS_FILE", "RUBRICA_RESEED", "RUBRICA_REJECT"):
        env.pop(key, None)
    if budget:
        env["RUBRICA_BUDGET"] = budget
    if findings_file is not None:
        env["RUBRICA_FINDINGS_FILE"] = str(findings_file)
    if reseed:
        env["RUBRICA_RESEED"] = "1"
    if reject:
        env["RUBRICA_REJECT"] = " ".join(reject)
    return env
