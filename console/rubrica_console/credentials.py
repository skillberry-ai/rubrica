"""The console's own model credentials: where dispatches get their access from.

A dispatch used to borrow whatever the shell that started the console happened
to have. `scripts/dispatch-stage.sh` copies `ANTHROPIC_BASE_URL`,
`ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_API_KEY` out of `~/.claude/settings.json`
when none is exported, and nothing else -- so a gateway that also needs a header
(`ANTHROPIC_CUSTOM_HEADERS`) worked from a Claude Code shell, which exports it, and
answered 401 to every dispatch from a plain terminal. Measured on a real run: 102
extract dispatches failed that way, three minutes of retries each, before anyone
saw why.

So the console holds its own: a base URL, one secret (an auth token or an API key),
and any extra headers, in one file readable only by its owner. Every dispatch gets
exactly these and none of the shell's -- `jobs.py` scrubs inherited `ANTHROPIC_*`
variables first -- and `dispatch-stage.sh`, finding a token already exported, uses
it as-is without reading the user's settings.

The secret never leaves the server: the API returns only whether it is set and its
last four characters, nothing logs it, and the file picker refuses this file.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import stat

# bandit B404 -- subprocess is how the credential test reaches the gateway: it runs
# `claude -p` exactly as a dispatch does, so there is no import-free way to test.
import subprocess  # nosec B404
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

AUTH_TOKEN, API_KEY = "auth_token", "api_key"
_ENV_FOR_KIND = {AUTH_TOKEN: "ANTHROPIC_AUTH_TOKEN", API_KEY: "ANTHROPIC_API_KEY"}

# Every variable through which a dispatch could pick up model access the console
# did not give it. Scrubbed before the console's own are set.
SCRUBBED = (
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_CUSTOM_HEADERS",
    "CLAUDE_CODE_OAUTH_TOKEN",
)


def default_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "rubrica" / "console-credentials.json"


class CredentialError(Exception):
    """A credentials request the console refuses; shown to the human."""


def _hint(secret: str) -> str:
    return f"…{secret[-4:]}" if len(secret) >= 8 else "set"


@dataclass
class Credentials:
    base_url: str = ""
    auth_kind: str = AUTH_TOKEN
    secret: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def configured(self) -> bool:
        return bool(self.secret)

    def env(self) -> dict[str, str]:
        """The environment a dispatch gets for model access, and nothing else."""
        out: dict[str, str] = {}
        if self.base_url:
            out["ANTHROPIC_BASE_URL"] = self.base_url
        if self.secret:
            out[_ENV_FOR_KIND[self.auth_kind]] = self.secret
        if self.headers:
            # Claude Code reads this as newline-separated "Name: value" lines.
            out["ANTHROPIC_CUSTOM_HEADERS"] = "\n".join(
                f"{k}: {v}" for k, v in self.headers.items()
            )
        return out

    def view(self) -> dict:
        """What the browser may see: never a secret, never a header value."""
        return {
            "configured": self.configured,
            "base_url": self.base_url,
            "auth_kind": self.auth_kind,
            "secret_hint": _hint(self.secret) if self.secret else "",
            "headers": [{"name": k, "hint": _hint(v)} for k, v in self.headers.items()],
        }


class Store:
    def __init__(self, path: Path | None = None):
        self.path = (path or default_path()).expanduser()

    def load(self) -> Credentials:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return Credentials()
        except (OSError, ValueError) as exc:
            raise CredentialError(f"cannot read {self.path}: {exc}") from exc
        if not isinstance(data, dict):
            raise CredentialError(f"{self.path} is not a JSON object")
        headers = data.get("headers") or {}
        return Credentials(
            base_url=str(data.get("base_url") or ""),
            auth_kind=data.get("auth_kind")
            if data.get("auth_kind") in _ENV_FOR_KIND
            else AUTH_TOKEN,
            secret=str(data.get("secret") or ""),
            headers={str(k): str(v) for k, v in headers.items()}
            if isinstance(headers, dict)
            else {},
        )

    def insecure(self) -> bool:
        """True when someone other than the owner can read the file."""
        try:
            return bool(self.path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO))
        except OSError:
            return False

    def save(self, creds: Credentials) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            self.path.parent.chmod(0o700)
        payload = json.dumps(
            {
                "base_url": creds.base_url,
                "auth_kind": creds.auth_kind,
                "secret": creds.secret,
                "headers": creds.headers,
            },
            indent=2,
        )
        # Created 0600 from the start, never chmod-ed after a moment of being
        # world-readable, then swapped in whole.
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".creds-")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, self.path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    def update(self, body: dict) -> Credentials:
        """Apply a form: blank secret or header value means "keep what is stored"."""
        current = self.load()
        base_url = str(body.get("base_url", current.base_url) or "").strip()
        if base_url and not base_url.startswith(("https://", "http://")):
            raise CredentialError("the base URL must start with https:// or http://")
        kind = body.get("auth_kind", current.auth_kind)
        if kind not in _ENV_FOR_KIND:
            raise CredentialError("auth_kind must be auth_token or api_key")
        secret = str(body.get("secret") or "").strip() or current.secret
        if any(c.isspace() for c in secret):
            raise CredentialError("a secret has no spaces or line breaks")
        rows = body.get("headers")
        if rows is None:
            # Not in the form at all: keep the stored headers as they are.
            headers = dict(current.headers)
        else:
            headers = {}
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name") or "").strip()
                if not name:
                    continue
                if ":" in name or any(c.isspace() for c in name):
                    raise CredentialError(f"not a header name: {name!r}")
                # A blank value keeps the stored one, so the page never needs it.
                value = str(row.get("value") or "").strip() or current.headers.get(name, "")
                if not value:
                    raise CredentialError(f"header {name} has no value")
                if "\n" in value or "\r" in value:
                    raise CredentialError(f"header {name}'s value has a line break")
                headers[name] = value
        creds = Credentials(base_url=base_url, auth_kind=kind, secret=secret, headers=headers)
        self.save(creds)
        return creds

    def clear(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()

    def import_claude_settings(self, settings: Path | None = None) -> Credentials:
        """Copy model access out of Claude Code's own settings, server-side.

        The values never travel through the browser: the page asks for an import,
        and this reads ~/.claude/settings.json's `env` block directly.
        """
        settings = settings or Path.home() / ".claude" / "settings.json"
        try:
            env = json.loads(settings.read_text(encoding="utf-8")).get("env") or {}
        except (OSError, ValueError, AttributeError) as exc:
            raise CredentialError(f"cannot read {settings}: {exc}") from exc
        token, key = env.get("ANTHROPIC_AUTH_TOKEN"), env.get("ANTHROPIC_API_KEY")
        if not token and not key:
            raise CredentialError(f"{settings} has no ANTHROPIC_AUTH_TOKEN or ANTHROPIC_API_KEY")
        headers = {}
        for line in str(env.get("ANTHROPIC_CUSTOM_HEADERS") or "").splitlines():
            name, sep, value = line.partition(":")
            if sep and name.strip() and value.strip():
                headers[name.strip()] = value.strip()
        creds = Credentials(
            base_url=str(env.get("ANTHROPIC_BASE_URL") or ""),
            auth_kind=AUTH_TOKEN if token else API_KEY,
            secret=str(token or key),
            headers=headers,
        )
        self.save(creds)
        return creds


def test(creds: Credentials, model: str, *, timeout: float = 120.0) -> dict:
    """One tiny real call through the path every dispatch takes.

    `claude -p` with the console's credentials and an empty, throwaway config
    directory -- the same isolation `dispatch-stage.sh` uses -- so a pass here
    means the gateway, the secret, the headers and the model id all work for a
    dispatch, not merely for some other client.
    """
    if not creds.configured:
        return {"ok": False, "message": "no credentials are set"}
    claude = shutil.which("claude")
    if not claude:
        return {"ok": False, "message": "claude is not on PATH, so no stage can be dispatched"}
    env = {k: v for k, v in os.environ.items() if k not in SCRUBBED}
    env.update(creds.env())
    with tempfile.TemporaryDirectory(prefix="rubrica-cred-test-") as config:
        env["CLAUDE_CONFIG_DIR"] = config
        try:
            # bandit B603 -- argv is a list, never a shell string, so nothing here is
            # word-split or glob-expanded. `claude` is shutil.which's absolute path, and
            # the model id travels as one argument however it is spelled.
            proc = subprocess.run(  # nosec B603
                [
                    claude,
                    "-p",
                    "Reply with the single word OK.",
                    "--model",
                    model,
                    # No tools and a one-line system prompt: the call still takes
                    # the gateway, the secret, the headers and the model id a
                    # dispatch takes, without Claude Code's built-in prompt and tool
                    # list. Measured: with them, this test cost $0.13 the first time.
                    "--system-prompt",
                    "You are a connectivity check.",
                    "--tools",
                    "",
                    "--output-format",
                    "json",
                    "--strict-mcp-config",
                    "--disable-slash-commands",
                    "--max-turns",
                    "1",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=config,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "message": f"no answer within {int(timeout)}s"}
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        tail = (proc.stderr or proc.stdout).strip()[-400:]
        return {"ok": False, "message": f"claude exited {proc.returncode}: {tail}"}
    if result.get("is_error"):
        return {"ok": False, "message": str(result.get("result") or "the call failed")[:600]}
    return {
        "ok": True,
        "message": f"{model} answered: {str(result.get('result') or '').strip()[:80]}",
        "cost": result.get("total_cost_usd"),
    }
