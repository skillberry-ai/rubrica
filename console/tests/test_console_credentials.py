"""The console's own model credentials: stored privately, never shown back."""

from __future__ import annotations

import json
import os
import stat

import pytest
from rubrica_console import credentials
from rubrica_console.credentials import CredentialError, Credentials, Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "cfg" / "console-credentials.json")


def test_saved_credentials_are_readable_only_by_their_owner(store):
    store.save(Credentials(secret="s3cret-token-abcd"))
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(store.path.parent.stat().st_mode) == 0o700
    assert store.insecure() is False
    store.path.chmod(0o644)
    assert store.insecure() is True


def test_the_view_never_carries_a_secret_or_a_header_value(store):
    store.save(
        Credentials(
            base_url="https://gw", secret="s3cret-token-abcd", headers={"x-gw": "header-value-wxyz"}
        )
    )
    view = json.dumps(store.load().view())
    assert "s3cret" not in view and "header-value" not in view
    assert "abcd" in view and "wxyz" in view  # the last four, so a human can tell keys apart


def test_a_blank_secret_or_header_value_keeps_the_stored_one(store):
    store.save(Credentials(secret="first-secret-1111", headers={"x-gw": "keep-me-2222"}))
    store.update(
        {"base_url": "https://new", "secret": "", "headers": [{"name": "x-gw", "value": ""}]}
    )
    creds = store.load()
    assert creds.secret == "first-secret-1111"
    assert creds.headers == {"x-gw": "keep-me-2222"}
    assert creds.base_url == "https://new"


@pytest.mark.parametrize(
    "body",
    [
        {"base_url": "ftp://nope", "secret": "x"},
        {"auth_kind": "password", "secret": "x"},
        {"secret": "has space"},
        {"secret": "ok", "headers": [{"name": "bad name", "value": "v"}]},
        {"secret": "ok", "headers": [{"name": "x-new", "value": ""}]},
    ],
)
def test_bad_input_is_refused(store, body):
    with pytest.raises(CredentialError):
        store.update(body)


def test_env_carries_exactly_the_console_credentials():
    env = Credentials(
        base_url="https://gw", auth_kind="api_key", secret="k", headers={"a": "1", "b": "2"}
    ).env()
    assert env == {
        "ANTHROPIC_BASE_URL": "https://gw",
        "ANTHROPIC_API_KEY": "k",
        "ANTHROPIC_CUSTOM_HEADERS": "a: 1\nb: 2",
    }


def test_import_copies_claude_codes_settings_including_custom_headers(store, tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "env": {
                    "ANTHROPIC_BASE_URL": "https://gw/anthropic",
                    "ANTHROPIC_AUTH_TOKEN": "tok-9999",
                    "ANTHROPIC_CUSTOM_HEADERS": "x-context-guru-token: cg_abc\nx-other: 2",
                }
            }
        )
    )
    creds = store.import_claude_settings(settings)
    assert creds.base_url == "https://gw/anthropic"
    assert creds.auth_kind == "auth_token" and creds.secret == "tok-9999"
    assert creds.headers == {"x-context-guru-token": "cg_abc", "x-other": "2"}
    assert store.load().headers == creds.headers


def test_import_refuses_settings_with_no_secret(store, tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"env": {"ANTHROPIC_BASE_URL": "https://gw"}}))
    with pytest.raises(CredentialError):
        store.import_claude_settings(settings)


def test_the_connection_test_uses_only_the_console_credentials(tmp_path, monkeypatch):
    """It calls `claude -p` exactly as a dispatch would; a fake records what it got."""
    fake = tmp_path / "claude"
    log = tmp_path / "seen.json"
    fake.write_text(
        "#!/usr/bin/env python3\nimport json, os, sys\n"
        f"open({str(log)!r}, 'w').write(json.dumps({{k: os.environ.get(k) for k in "
        "['ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_CUSTOM_HEADERS', 'CLAUDE_CONFIG_DIR']} | "
        "{'argv': sys.argv[1:]}))\n"
        "print(json.dumps({'type': 'result', 'is_error': False, 'result': 'OK', "
        "'total_cost_usd': 0.0001}))\n"
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "shell-token")
    result = credentials.test(Credentials(secret="console-token", headers={"x": "1"}), "m-1")
    assert result["ok"] is True and "OK" in result["message"]
    seen = json.loads(log.read_text())
    assert seen["ANTHROPIC_AUTH_TOKEN"] == "console-token"
    assert seen["ANTHROPIC_CUSTOM_HEADERS"] == "x: 1"
    assert seen["CLAUDE_CONFIG_DIR"] and "--model" in seen["argv"] and "m-1" in seen["argv"]


def test_a_failed_connection_test_says_why(tmp_path, monkeypatch):
    fake = tmp_path / "claude"
    fake.write_text(
        "#!/usr/bin/env python3\nimport json\n"
        "print(json.dumps({'type': 'result', 'is_error': True, "
        "'result': 'Failed to authenticate. API Error: 401'}))\n"
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    result = credentials.test(Credentials(secret="x"), "m")
    assert result["ok"] is False and "401" in result["message"]
