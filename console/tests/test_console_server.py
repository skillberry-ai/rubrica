"""The console's HTTP surface: what reaches a dispatch, and what never can.

Driven over real HTTP on an OS-chosen port, because the properties that matter
-- the token, the Host check, what a path resolves to -- live in the request
handling, not in a function a unit test could call around it.
"""

from __future__ import annotations

import http.client
import json
import socket
import threading
from contextlib import contextmanager
from html import escape
from pathlib import Path

import pytest
from rubrica_console import server as console_server
from rubrica_console.cli import main
from rubrica_console.jobs import Console, Entry, Job, Member

from rubrica import brief, summary
from tests.toy import build_toy_run

TOKEN = "test-token-123"


@contextmanager
def _serving(console: Console, root=None):
    server = console_server.make_server(console, "127.0.0.1", 0, root=root, token=TOKEN)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def _req(port, method, path, body=None, *, token=TOKEN, host=None, origin=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    headers = {"Host": host or f"127.0.0.1:{port}"}
    if token is not None:
        headers["X-Rubrica-Token"] = token
    if origin is not None:
        headers["Origin"] = origin
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    try:
        conn.request(method, path, body=data, headers=headers)
        res = conn.getresponse()
        return res.status, res.getheader("Content-Type") or "", res.read()
    finally:
        conn.close()


@pytest.fixture
def run(tmp_path):
    return build_toy_run(tmp_path / "runs")


@pytest.fixture
def console(tmp_path, run):
    return Console(run.root.parent, tmp_path / "lab", dispatch_script=tmp_path / "none.sh")


# -- the page and the API ------------------------------------------------------


def test_the_ui_page_carries_the_token_and_its_assets_are_served(console):
    with _serving(console) as port:
        status, _, body = _req(port, "GET", "/", token=None)
        js = _req(port, "GET", "/static/app.js", token=None)
        css = _req(port, "GET", "/static/app.css", token=None)
    assert status == 200
    assert f'content="{TOKEN}"' in body.decode()
    assert js[0] == 200 and js[1].startswith("text/javascript")
    assert css[0] == 200


def test_state_lists_the_runs(console, run):
    with _serving(console) as port:
        status, _, body = _req(port, "GET", "/api/state", token=None)
    data = json.loads(body)
    assert status == 200
    assert run.root.name in [r["name"] for r in data["runs"]]
    assert data["prompt_ready"] is False
    assert "repository checkout" in data["prompt_reason"]


def test_run_detail_carries_steps_and_the_next_one(console, run):
    with _serving(console) as port:
        status, _, body = _req(port, "GET", f"/api/runs/{run.root.name}", token=None)
    data = json.loads(body)
    assert status == 200
    assert data["next"] == "gate-3"
    assert any(s["id"] == "round-1/score-seal" for s in data["steps"])


def test_a_step_id_with_a_slash_reaches_the_api_as_one_segment(console, run):
    with _serving(console) as port:
        status, _, body = _req(
            port,
            "POST",
            f"/api/runs/{run.root.name}/steps/round-1%2Fscore-seal/accept",
            {"note": "x"},
        )
    # It resolved the step (and refused: it is done with nothing open), rather
    # than reporting "no such API path".
    assert status == 409
    assert b"no open findings" in body


def _raw_post(port, content_length: str) -> bytes:
    """POST with a hand-written Content-Length, over a bare socket.

    `http.client` computes the header itself, so it cannot send a bad one. The
    short timeout makes a server that waits on the body fail the test (as
    `TimeoutError`) instead of stalling the suite.
    """
    with socket.create_connection(("127.0.0.1", port), timeout=3) as sock:
        sock.sendall(
            (
                "POST /api/runs/x/delete HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{port}\r\n"
                f"X-Rubrica-Token: {TOKEN}\r\n"
                f"Content-Length: {content_length}\r\n"
                "\r\n"
            ).encode()
        )
        # No body follows, and the socket stays open: a server that reads
        # "until the client closes" would block here.
        reply = b""
        while b"\r\n\r\n" not in reply:
            chunk = sock.recv(4096)
            if not chunk:
                break
            reply += chunk
    return reply


@pytest.mark.parametrize("bad", ["abc", "-5", "+5", "1_0", "\u0665"])
def test_a_bad_content_length_is_refused_promptly(console, bad):
    with _serving(console) as port:
        reply = _raw_post(port, bad)
    status_line = reply.split(b"\r\n", 1)[0]
    # A 409 from ConsoleError, like an oversized body -- not a 500, not a hang.
    assert status_line.startswith(b"HTTP/1.0 409") or status_line.startswith(b"HTTP/1.1 409"), reply


def test_a_valid_content_length_still_reads_the_body(console, run):
    # The guard must not refuse what `http.client` sends for an ordinary request.
    with _serving(console) as port:
        status, _, body = _req(port, "POST", f"/api/runs/{run.root.name}/delete", {"confirm": "no"})
    assert status == 409
    assert b"Content-Length" not in body


def test_gate_approval_over_http_records_the_note(console, run):
    with _serving(console) as port:
        status, _, body = _req(
            port, "POST", f"/api/runs/{run.root.name}/gates/3/approve", {"note": "verdicts read"}
        )
    assert status == 200, body
    assert "human gate 3 (console): verdicts read" in run.decisions.read_text()


def test_a_refused_action_is_a_409_with_the_reason(console, run):
    with _serving(console) as port:
        status, _, body = _req(port, "POST", f"/api/runs/{run.root.name}/gates/3/approve", {})
    assert status == 409
    assert b"note is required" in body


def test_gate_feedback_is_recorded_and_leaves_the_gate_open(console, run):
    name = run.root.name
    with _serving(console) as port:
        status, _, body = _req(
            port,
            "POST",
            f"/api/runs/{name}/gates/3/feedback",
            {"note": 'on "Verdict tallies": check s-002'},
        )
        assert status == 200, body
        _, _, brief_body = _req(port, "GET", f"/api/runs/{name}/gate/3")
    assert "feedback on gate 3, not approved" in run.decisions.read_text()
    # Still the next thing to do: feedback is not an approval.
    gate = next(s for s in console.steps(name) if s.id == "gate-3")
    assert gate.status == "ready"
    history = json.loads(brief_body)["history"]
    assert any("check s-002" in line for line in history)


def test_delete_needs_the_name_typed_back(console, run):
    path = f"/api/runs/{run.root.name}/delete"
    with _serving(console) as port:
        refused = _req(port, "POST", path, {"confirm": "nope"})
        assert run.root.is_dir()
        done = _req(port, "POST", path, {"confirm": run.root.name})
    assert refused[0] == 409
    assert done[0] == 200 and not run.root.exists()


# -- what stands between a web page and a dispatch -----------------------------


@pytest.mark.parametrize("token", [None, "", "wrong"])
def test_every_post_needs_the_token(console, run, token):
    with _serving(console) as port:
        status, _, _ = _req(
            port, "POST", f"/api/runs/{run.root.name}/decide", {"note": "x"}, token=token
        )
    assert status == 403
    assert "x" not in (run.decisions.read_text() if run.decisions.exists() else "")


@pytest.mark.parametrize("host", ["evil.example:8765", "attacker.test", ""])
def test_a_foreign_host_header_is_refused_even_for_reads(console, host):
    """DNS rebinding: a hostile name pointed at 127.0.0.1 must not be served."""
    with _serving(console) as port:
        status, _, body = _req(port, "GET", "/", host=host or "x", token=None)
        api = _req(port, "GET", "/api/state", host=host or "x", token=None)
    assert status == 403 and TOKEN.encode() not in body
    assert api[0] == 403


def test_localhost_by_name_is_allowed(console):
    with _serving(console) as port:
        status, _, _ = _req(port, "GET", "/api/state", host=f"localhost:{port}", token=None)
    assert status == 200


def test_a_foreign_origin_is_refused(console, run):
    with _serving(console) as port:
        status, _, _ = _req(
            port,
            "POST",
            f"/api/runs/{run.root.name}/decide",
            {"note": "x"},
            origin="http://evil.example",
        )
    assert status == 403


# -- the file picker -----------------------------------------------------------


def test_the_picker_lists_folders_under_its_root(console, tmp_path):
    (tmp_path / "corpus").mkdir()
    (tmp_path / "corpus" / "a.md").write_text("x")
    with _serving(console, root=tmp_path) as port:
        status, _, body = _req(port, "GET", f"/api/fs?path={tmp_path / 'corpus'}", token=None)
    data = json.loads(body)
    assert status == 200
    assert [e["name"] for e in data["entries"]] == ["a.md"]


def test_the_picker_shows_dot_entries_only_when_asked(console, tmp_path):
    (tmp_path / "corpus" / ".config").mkdir(parents=True)
    # VCS metadata stays out of both listings: a ticked `.git` would be walked by
    # survey as a root, cataloguing git config (which can carry a token in a URL).
    (tmp_path / "corpus" / ".git").mkdir()
    (tmp_path / "corpus" / ".git" / "config").write_text("x")
    (tmp_path / "corpus" / ".env.example").write_text("x")
    (tmp_path / "corpus" / "a.md").write_text("x")
    url = f"/api/fs?path={tmp_path / 'corpus'}"
    with _serving(console, root=tmp_path) as port:
        _, _, plain = _req(port, "GET", url, token=None)
        _, _, shown = _req(port, "GET", url + "&hidden=1", token=None)
    assert [e["name"] for e in json.loads(plain)["entries"]] == ["a.md"]
    assert [e["name"] for e in json.loads(shown)["entries"]] == [".config", ".env.example", "a.md"]


def test_the_picker_hides_vcs_folders_whatever_their_case(console, tmp_path):
    # On a case-insensitive volume (the macOS default) `.GIT` is the `.git` folder,
    # so an exact-name check let it into the hidden listing.
    (tmp_path / "corpus" / ".GIT").mkdir(parents=True)
    (tmp_path / "corpus" / ".GIT" / "config").write_text("x")
    (tmp_path / "corpus" / "a.md").write_text("x")
    url = f"/api/fs?path={tmp_path / 'corpus'}"
    with _serving(console, root=tmp_path) as port:
        _, _, plain = _req(port, "GET", url, token=None)
        _, _, shown = _req(port, "GET", url + "&hidden=1", token=None)
    assert [e["name"] for e in json.loads(plain)["entries"]] == ["a.md"]
    assert [e["name"] for e in json.loads(shown)["entries"]] == ["a.md"]


@pytest.mark.parametrize("escape_path", ["/etc", "{root}/../..", "{root}/link"])
def test_the_picker_never_leaves_its_root(console, tmp_path, escape_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "link").symlink_to("/etc")
    path = escape_path.format(root=root)
    with _serving(console, root=root) as port:
        status, _, body = _req(port, "GET", f"/api/fs?path={path}", token=None)
    assert status == 409
    assert b"limited to" in body


# -- report pages and run files ------------------------------------------------


def test_the_run_summary_is_served_with_navigation(console, run):
    with _serving(console) as port:
        status, _, body = _req(port, "GET", f"/runs/{run.root.name}/", token=None)
    page = body.decode()
    assert status == 200
    assert f"<h1>{run.root.name}</h1>" in page
    assert 'id="rubrica-console-nav"' in page
    # The report page never carries the token; only the console page does.
    assert TOKEN not in page


def test_decorate_adds_the_nav_and_removes_nothing(run):
    written = summary.run_summary(run)
    nav = console_server._report_nav(run.root.name, "/")
    assert console_server.decorate(written, nav).replace(nav, "", 1) == written


@pytest.mark.parametrize("gate", brief.GATES)
def test_each_gate_page_carries_gate_brief_text(console, run, gate):
    with _serving(console) as port:
        status, _, body = _req(port, "GET", f"/runs/{run.root.name}/gate/{gate}", token=None)
        api = _req(port, "GET", f"/api/runs/{run.root.name}/gate/{gate}", token=None)
    text = brief.gate_brief(run, gate)
    assert status == 200
    assert escape(text.splitlines()[0]) in body.decode()
    assert json.loads(api[2])["text"] == text


def test_a_run_file_is_served_as_is(console, run):
    with _serving(console) as port:
        status, content_type, body = _req(
            port, "GET", f"/runs/{run.root.name}/manifest.json", token=None
        )
    assert status == 200 and content_type.startswith("application/json")
    assert body == run.manifest.read_bytes()


def test_an_html_file_in_a_run_is_served_as_text_never_as_a_page(console, run):
    (run.root / "evil.html").write_text("<script>steal()</script>")
    with _serving(console) as port:
        status, content_type, _ = _req(port, "GET", f"/runs/{run.root.name}/evil.html", token=None)
    assert status == 200 and content_type.startswith("text/plain")


def _get_headers(port, path):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    try:
        conn.request("GET", path, headers={"Host": f"127.0.0.1:{port}"})
        res = conn.getresponse()
        return res.status, {k.lower(): v for k, v in res.getheaders()}, res.read()
    finally:
        conn.close()


# Every type a browser can run script in, plus one it has never heard of. The SVG
# under 00-inputs/ is the real path: intake copies a corpus SVG there and the run
# summary links it.
_SCRIPT = '<svg xmlns="http://www.w3.org/2000/svg"><script>steal()</script></svg>'


@pytest.mark.parametrize(
    "rel",
    [
        "evil.html",
        "evil.svg",
        "evil.xhtml",
        "evil.xht",
        "evil.xml",
        "evil.weirdext",
        "00-inputs/evil.svg",
    ],
)
def test_a_run_file_that_could_run_script_is_served_as_inert_text(console, run, rel):
    target = run.root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_SCRIPT)
    with _serving(console) as port:
        status, headers, body = _get_headers(port, f"/runs/{run.root.name}/{rel}")
    assert status == 200
    assert headers["content-type"] == "text/plain; charset=utf-8"
    assert headers["content-security-policy"] == "sandbox"
    assert headers["x-content-type-options"] == "nosniff"
    assert body == _SCRIPT.encode()


def test_a_binary_run_file_of_unknown_type_is_served_as_bytes(console, run):
    (run.root / "blob.bin").write_bytes(b"\xff\xfe\x00<script>")
    with _serving(console) as port:
        status, headers, _ = _get_headers(port, f"/runs/{run.root.name}/blob.bin")
    assert status == 200 and headers["content-type"] == "application/octet-stream"
    assert headers["content-security-policy"] == "sandbox"


def test_a_json_run_file_still_reads_back_as_json(console, run):
    (run.root / "data.json").write_text('{"a": 1}')
    with _serving(console) as port:
        status, headers, body = _get_headers(port, f"/runs/{run.root.name}/data.json")
    assert status == 200
    assert headers["content-type"] == "application/json; charset=utf-8"
    assert headers["content-security-policy"] == "sandbox"
    assert headers["x-content-type-options"] == "nosniff"
    assert json.loads(body) == {"a": 1}


# Thirty levels, because pytest's temp directory sits deep under /private/var:
# four `..` stayed inside it and the old viewer's test once passed with the guard
# deleted.
_UP = "../" * 30
_UP_ENCODED = "%2e%2e/" * 30


@pytest.mark.parametrize("rest", [f"{_UP}etc/passwd", f"{_UP_ENCODED}etc/passwd", "nope.json"])
def test_nothing_outside_the_run_is_reachable(console, run, rest):
    with _serving(console) as port:
        status, _, body = _req(port, "GET", f"/runs/{run.root.name}/{rest}", token=None)
    assert status == 404
    assert b"root:" not in body


def test_a_symlink_out_of_the_run_is_not_followed(console, run, tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("do not serve")
    (run.root / "link.txt").symlink_to(outside)
    with _serving(console) as port:
        status, _, body = _req(port, "GET", f"/runs/{run.root.name}/link.txt", token=None)
    assert status == 404 and b"do not serve" not in body


# -- folder links from the run summary -----------------------------------------
# run-summary links `04-instances/<id>/` and `06-suite/<id>/`; the console answers
# a folder with a listing it builds, rather than the 404 those links used to get.


def test_the_summary_links_folders_that_the_console_answers_with_a_listing(console, run):
    page = summary.run_summary(run)
    sid = next(p.name for p in run.instances_dir.iterdir() if p.is_dir())
    assert f'href="04-instances/{sid}/"' in page
    inside = sorted(p.name for p in (run.instances_dir / sid).iterdir())
    with _serving(console) as port:
        status, headers, body = _get_headers(port, f"/runs/{run.root.name}/04-instances/{sid}/")
    assert status == 200
    assert headers["content-type"] == "text/html; charset=utf-8"
    assert headers["content-security-policy"] == "sandbox"
    assert headers["x-content-type-options"] == "nosniff"
    text = body.decode()
    for name in inside:
        assert f'href="/runs/{run.root.name}/04-instances/{sid}/{name}' in text


def test_a_suite_folder_lists_and_its_files_are_served_inert(console, run):
    # The toy run stops before emit, so the suite folder is written here.
    sid = next(p.name for p in run.instances_dir.iterdir() if p.is_dir())
    folder = run.suite_dir / sid
    folder.mkdir(parents=True)
    (folder / "evil.html").write_text("<script>steal()</script>")
    with _serving(console) as port:
        status, _, body = _get_headers(port, f"/runs/{run.root.name}/06-suite/{sid}")
        file_status, headers, file_body = _get_headers(
            port, f"/runs/{run.root.name}/06-suite/{sid}/evil.html"
        )
    assert status == 200
    assert f'href="/runs/{run.root.name}/06-suite/{sid}/evil.html"' in body.decode()
    assert file_status == 200
    assert headers["content-type"] == "text/plain; charset=utf-8"
    assert headers["content-security-policy"] == "sandbox"
    assert file_body == b"<script>steal()</script>"


def test_a_folder_listing_escapes_names(console, run):
    folder = run.root / "odd"
    folder.mkdir()
    (folder / "<img src=x onerror=steal()>.txt").write_text("x")
    with _serving(console) as port:
        status, _, body = _get_headers(port, f"/runs/{run.root.name}/odd/")
    assert status == 200
    assert b"<img" not in body
    assert b"&lt;img src=x onerror=steal()&gt;.txt" in body


def test_a_folder_listing_leaves_off_a_symlink_out_of_the_run(console, run, tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("do not serve")
    folder = run.root / "odd"
    folder.mkdir()
    (folder / "door.txt").symlink_to(outside)
    (folder / "kept.txt").write_text("fine")
    with _serving(console) as port:
        _, _, listing = _get_headers(port, f"/runs/{run.root.name}/odd/")
        status, _, body = _req(port, "GET", f"/runs/{run.root.name}/odd/door.txt", token=None)
    assert b"kept.txt" in listing and b"door.txt" not in listing
    assert status == 404 and b"do not serve" not in body


def test_a_folder_outside_the_run_is_not_listed(console, run, tmp_path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "secret.txt").write_text("do not list")
    (run.root / "dirlink").symlink_to(outside)
    with _serving(console) as port:
        linked = _req(port, "GET", f"/runs/{run.root.name}/dirlink/", token=None)
        climbed = _req(port, "GET", f"/runs/{run.root.name}/{_UP}tmp/", token=None)
        climbed_enc = _req(port, "GET", f"/runs/{run.root.name}/{_UP_ENCODED}", token=None)
    for status, _, body in (linked, climbed, climbed_enc):
        assert status == 404
        assert b"secret.txt" not in body


def test_an_unknown_run_is_refused(console):
    with _serving(console) as port:
        status, _, _ = _req(port, "GET", "/api/runs/..%2F..%2Fetc", token=None)
    assert status == 409


# -- the rubrica-console command -----------------------------------------------------------------


def test_a_missing_runs_dir_is_exit_2(tmp_path, capsys):
    assert main(["--runs-dir", str(tmp_path / "nope"), "--port", "0"]) == 2
    captured = capsys.readouterr()
    assert captured.out.strip() == "" and captured.err.startswith("error: ")


def test_the_console_needs_a_run_or_a_runs_dir(capsys):
    assert main([]) == 2


def test_a_port_in_use_is_exit_2(console, run, tmp_path, capsys):
    with _serving(console) as port:
        code = main(["--run", str(run.root), "--port", str(port), "--lab", str(tmp_path / "lab2")])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out.strip() == "" and captured.err.startswith("error: ")


# -- what a picker selection expands to --------------------------------------------


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "pick"
    (root / "src" / "tests").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "README.md").write_text("r")
    (root / "src" / "a.py").write_text("aa")
    (root / "src" / "b.py").write_text("bbb")
    (root / "src" / "tests" / "t.py").write_text("t")
    (root / ".git" / "config").write_text("x")
    (root / "src" / ".hidden.py").write_text("h")
    return root


def _expand(port, include, exclude=(), token=TOKEN):
    status, _, body = _req(
        port,
        "POST",
        "/api/fs/expand",
        {"include": list(include), "exclude": list(exclude)},
        token=token,
    )
    return status, json.loads(body)


def test_a_folder_expands_to_its_files_minus_what_was_unchecked(console, tree):
    with _serving(console, root=tree) as port:
        status, data = _expand(
            port, [str(tree)], [str(tree / "src" / "tests"), str(tree / "src" / "b.py")]
        )
    assert status == 200
    names = sorted(p.rsplit("/", 1)[1] for p in data["files"])
    # Dot-directories and dot-files are skipped; the unchecked folder and file are out.
    assert names == ["README.md", "a.py"]
    assert data["total"] == 2 and data["bytes"] == 3 and data["truncated"] is False


def test_expansion_with_hidden_walks_dot_entries_but_never_vcs_metadata(console, tree):
    (tree / ".github").mkdir()
    (tree / ".github" / "ci.yml").write_text("c")
    with _serving(console, root=tree) as port:
        status, _, body = _req(
            port, "POST", "/api/fs/expand", {"include": [str(tree)], "hidden": True}, token=TOKEN
        )
    names = sorted(p.rsplit("/", 1)[1] for p in json.loads(body)["files"])
    assert status == 200
    # `.git/config` stays out: survey drops VCS metadata whatever the picker shows.
    assert names == [".hidden.py", "README.md", "a.py", "b.py", "ci.yml", "t.py"]


def test_expansion_skips_vcs_folders_whatever_their_case(console, tmp_path):
    root = tmp_path / "pick"
    (root / ".GIT").mkdir(parents=True)
    (root / ".GIT" / "config").write_text("x")
    (root / "README.md").write_text("r")
    with _serving(console, root=root) as port:
        for hidden in (False, True):
            status, _, body = _req(
                port,
                "POST",
                "/api/fs/expand",
                {"include": [str(root)], "hidden": hidden},
                token=TOKEN,
            )
            data = json.loads(body)
            assert status == 200
            assert [p.rsplit("/", 1)[1] for p in data["files"]] == ["README.md"]
            assert data["total"] == 1


def test_files_and_folders_can_be_mixed_and_overlaps_count_once(console, tree):
    with _serving(console, root=tree) as port:
        _, data = _expand(
            port, [str(tree / "src"), str(tree / "src" / "a.py"), str(tree / "README.md")]
        )
    assert data["total"] == 4  # a, b, tests/t, README -- a.py counted once


def test_expansion_never_leaves_the_root(console, tree, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("s")
    (tree / "link").symlink_to(outside)
    with _serving(console, root=tree) as port:
        status, data = _expand(port, [str(outside)])
        assert status == 409 and "limited to" in data["error"]
        # A symlinked folder inside the root is not followed out of it.
        _, data = _expand(port, [str(tree)])
    assert not any("secret" in p for p in data["files"])


def test_expansion_refuses_a_sibling_whose_name_starts_like_the_root(console, tree):
    """The prefix check carries the separator: `<root>-evil` is not under `<root>`."""
    sibling = tree.parent / (tree.name + "-evil")
    sibling.mkdir()
    (sibling / "x.txt").write_text("x")
    with _serving(console, root=tree) as port:
        status, data = _expand(port, [str(sibling)])
    assert status == 409 and "limited to" in data["error"]


def test_expansion_refuses_a_dot_dot_escape_and_a_symlink_pointing_out(console, tree, tmp_path):
    outside = tmp_path / "out2"
    outside.mkdir()
    (outside / "secret.txt").write_text("s")
    (tree / "door").symlink_to(outside)
    with _serving(console, root=tree) as port:
        status, data = _expand(port, [str(tree / "src" / ".." / ".." / "out2")])
        assert status == 409 and "limited to" in data["error"]
        # Named through a link inside the root, the target is still outside it.
        status, data = _expand(port, [str(tree / "door")])
    assert status == 409 and "limited to" in data["error"]


def test_expansion_needs_the_token(console, tree):
    with _serving(console, root=tree) as port:
        status, _ = _expand(port, [str(tree)], token="wrong")
    assert status == 403


def test_vendored_folders_are_skipped_like_survey_skips_them(console, tree):
    (tree / "node_modules" / "pkg").mkdir(parents=True)
    (tree / "node_modules" / "pkg" / "index.js").write_text("x")
    with _serving(console, root=tree) as port:
        _, data = _expand(port, [str(tree)])
    assert not any("node_modules" in p for p in data["files"])


def test_a_count_that_runs_out_says_it_is_partial(console, tree, monkeypatch):
    monkeypatch.setattr(console_server, "_EXPAND_WALK_CAP", 0)
    with _serving(console, root=tree) as port:
        _, data = _expand(port, [str(tree)])
    assert data["partial"] is True


class _DeadSocket:
    """A connection the browser already closed: every write raises."""

    def __init__(self, exc):
        self.exc = exc

    def write(self, _data):
        raise self.exc

    def flush(self):
        raise self.exc


@pytest.mark.parametrize(
    "exc", [BrokenPipeError(32, "Broken pipe"), ConnectionResetError(54, "reset")]
)
def test_a_reply_to_a_client_that_hung_up_is_dropped_quietly(exc):
    """Measured: each dropped request printed two tracebacks -- the write raised, and
    the catch-all then sent a 500 down the same dead socket. The browser hangs up
    routinely (a closed picker, a newer count), so the reply is simply abandoned.

    Tested on the handler rather than over a socket: a hard client close on macOS was
    measured *not* to make the server's write fail, so a socket-level version of this
    test passed with the fix removed."""
    handler = console_server.Handler.__new__(console_server.Handler)
    handler.wfile = _DeadSocket(exc)
    handler.request_version = "HTTP/1.1"
    handler.requestline = "POST /api/fs/expand HTTP/1.1"
    handler.command = "POST"
    handler.close_connection = False
    handler._send(200, b"{}", "application/json")  # must not raise
    assert handler.close_connection is True


def test_the_server_prints_nothing_for_a_dropped_connection_and_everything_else(console, capsys):
    srv = console_server.make_server(console, "127.0.0.1", 0, token=TOKEN)
    try:
        try:
            raise BrokenPipeError(32, "Broken pipe")
        except BrokenPipeError:
            srv.handle_error(None, ("127.0.0.1", 1))
        assert "Traceback" not in capsys.readouterr().err
        try:
            raise KeyError("a real bug")
        except KeyError:
            srv.handle_error(None, ("127.0.0.1", 1))
        assert "a real bug" in capsys.readouterr().err
    finally:
        srv.server_close()


# -- credentials over HTTP -------------------------------------------------------------


@pytest.fixture
def cred_console(tmp_path, run):
    from rubrica_console import credentials

    store = credentials.Store(tmp_path / "home" / "console-credentials.json")
    return Console(
        run.root.parent, tmp_path / "lab", dispatch_script=tmp_path / "none.sh", credentials=store
    )


def test_credentials_go_in_and_never_come_back_out(cred_console):
    with _serving(cred_console) as port:
        status, _, body = _req(
            port,
            "POST",
            "/api/credentials",
            {
                "base_url": "https://gw",
                "secret": "super-secret-value-9876",
                "headers": [{"name": "x-gw", "value": "header-secret-5432"}],
            },
        )
        assert status == 200, body
        _, _, got = _req(port, "GET", "/api/credentials", token=None)
    for text in (body, got):
        assert b"super-secret" not in text and b"header-secret" not in text
    view = json.loads(got)
    assert view["configured"] is True and view["secret_hint"].endswith("9876")


def test_setting_credentials_needs_the_token(cred_console):
    with _serving(cred_console) as port:
        status, _, _ = _req(port, "POST", "/api/credentials", {"secret": "x"}, token="wrong")
    assert status == 403
    assert not cred_console.credentials.path.exists()


def test_the_picker_does_not_list_the_credentials_file(cred_console, tmp_path):
    from rubrica_console import credentials

    cred_console.credentials.save(credentials.Credentials(secret="x"))
    home = cred_console.credentials.path.parent
    (home / "notes.txt").write_text("n")
    with _serving(cred_console, root=tmp_path) as port:
        _, _, body = _req(port, "GET", f"/api/fs?path={home}", token=None)
        _, data = _expand(port, [str(home)])
    assert [e["name"] for e in json.loads(body)["entries"]] == ["notes.txt"]
    assert not any("console-credentials" in p for p in data["files"])


# -- the job log ---------------------------------------------------------------


@pytest.fixture
def log_job(console, run, tmp_path):
    """A finished job with one entry log and one member log, put straight into
    the console's table: the endpoint under test only reads it, and dispatching
    a real job would need a model."""
    entry_log = tmp_path / "entry.log"
    entry_log.write_bytes(b"0123456789")
    member_log = tmp_path / "member.log"
    member_log.write_bytes(b"member says hi")
    job = Job(
        id="job-log-1",
        run=run.root.name,
        step="extract",
        title="extract",
        kind="stage",
        entries=[Entry(label="first", log=str(entry_log))],
        members={"m1": Member(id="m1", log=str(member_log))},
    )
    console._jobs[job.id] = job
    return job


def _log(port, query=""):
    status, _, body = _req(port, "GET", f"/api/jobs/job-log-1/log{query}", token=None)
    return status, json.loads(body)


def test_the_job_log_reads_the_last_entry_and_follows_on_from_next(console, log_job):
    with _serving(console) as port:
        status, first = _log(port)
        Path(log_job.entries[0].log).write_bytes(b"0123456789abc")
        _, follow = _log(port, f"?offset={first['next']}")
    assert status == 200
    assert first == {"text": "0123456789", "next": 10}
    assert follow == {"text": "abc", "next": 13}


def test_the_job_log_reads_a_member_log_by_id(console, log_job):
    with _serving(console) as port:
        status, data = _log(port, "?member=m1")
    assert status == 200
    assert data["text"] == "member says hi"


def test_an_entry_out_of_range_is_a_409(console, log_job):
    with _serving(console) as port:
        status, data = _log(port, "?entry=5")
    assert status == 409
    assert data["error"] == "no such entry in this job"


def test_an_unknown_member_is_a_409(console, log_job):
    with _serving(console) as port:
        status, data = _log(port, "?member=nobody")
    assert status == 409
    assert data["error"] == "no such member in this job"


@pytest.mark.parametrize("value", ["abc", "undefined", "NaN", "1.5"])
def test_a_non_numeric_entry_is_a_409_naming_it_not_a_500(console, log_job, value):
    with _serving(console) as port:
        status, data = _log(port, f"?entry={value}")
    assert status == 409
    assert data["error"] == "entry must be a whole number"


@pytest.mark.parametrize("value", ["abc", "undefined", "NaN", "1.5"])
def test_a_non_numeric_offset_is_a_409_naming_it_not_a_500(console, log_job, value):
    with _serving(console) as port:
        status, data = _log(port, f"?offset={value}")
    assert status == 409
    assert data["error"] == "offset must be a whole number"


def test_a_missing_log_file_reads_as_empty_text(console, log_job):
    Path(log_job.entries[0].log).unlink()
    with _serving(console) as port:
        status, data = _log(port)
    assert status == 200
    assert data == {"text": "", "next": 0}


@pytest.mark.parametrize("offset", ["999", "-3"])
def test_an_offset_outside_the_file_reads_the_tail_chunk(console, log_job, monkeypatch, offset):
    # A small chunk so "the tail" is distinguishable from "the whole file".
    monkeypatch.setattr(console_server, "_LOG_CHUNK", 4)
    with _serving(console) as port:
        status, data = _log(port, f"?offset={offset}")
    assert status == 200
    assert data == {"text": "6789", "next": 10}


# "—" is three bytes (e2 80 94); this project's output is full of it, and a chunk
# edge or a half-written log can fall inside it.
_DASH = "—".encode()


def test_a_character_spanning_the_chunk_edge_reads_back_whole_in_two_polls(
    console, log_job, monkeypatch
):
    monkeypatch.setattr(console_server, "_LOG_CHUNK", 4)
    text = "ab—c"
    Path(log_job.entries[0].log).write_bytes(text.encode())
    with _serving(console) as port:
        _, first = _log(port, "?offset=0")
        _, second = _log(port, f"?offset={first['next']}")
    assert first == {"text": "ab", "next": 2}
    assert second == {"text": "—c", "next": 6}
    assert first["text"] + second["text"] == text


def test_a_log_ending_mid_character_holds_it_back_until_the_rest_is_written(console, log_job):
    log = Path(log_job.entries[0].log)
    log.write_bytes(b"done " + _DASH[:2])
    with _serving(console) as port:
        _, partial = _log(port, "?offset=0")
        log.write_bytes(b"done " + _DASH + b" ok")
        _, rest = _log(port, f"?offset={partial['next']}")
    assert partial == {"text": "done ", "next": 5}
    assert rest == {"text": "— ok", "next": len(b"done ") + 3 + 3}


def test_a_chunk_smaller_than_one_character_still_makes_progress(console, log_job, monkeypatch):
    monkeypatch.setattr(console_server, "_LOG_CHUNK", 2)
    Path(log_job.entries[0].log).write_bytes(_DASH + b"x")
    with _serving(console) as port:
        _, data = _log(port, "?offset=0")
    assert data == {"text": "—", "next": 3}


@pytest.mark.parametrize("chunk", [3, 4, 5])
def test_the_tail_jump_never_starts_mid_character(console, log_job, monkeypatch, chunk):
    # With "a—b" (5 bytes) a 3-byte tail would start inside the dash; a 4-byte
    # one starts on its lead byte, and the whole file needs no jump at all.
    monkeypatch.setattr(console_server, "_LOG_CHUNK", chunk)
    Path(log_job.entries[0].log).write_bytes(b"a" + _DASH + b"b")
    with _serving(console) as port:
        _, data = _log(port)
    assert "\ufffd" not in data["text"]
    assert data["next"] == 5
    assert data["text"] == {3: "b", 4: "—b", 5: "a—b"}[chunk]


def test_a_genuinely_invalid_byte_still_decodes_as_a_replacement(console, log_job):
    Path(log_job.entries[0].log).write_bytes(b"a\xffb")
    with _serving(console) as port:
        _, data = _log(port, "?offset=0")
    assert data == {"text": "a\ufffdb", "next": 3}


# -- the budget a dispatch is capped at ----------------------------------------


@pytest.fixture
def bare_console(tmp_path):
    (tmp_path / "runs").mkdir()
    return Console(tmp_path / "runs", tmp_path / "lab", dispatch_script=tmp_path / "none.sh")


# "nan", "inf" and "1e999" passed the old `float(budget) <= 0` check and reached
# `claude --max-budget-usd` as a ceiling that caps nothing.
@pytest.mark.parametrize(
    "budget", ["nan", "NaN", "inf", "-inf", "1e999", "0", "-1", "abc", True, [5], {"usd": 5}]
)
def test_a_budget_that_is_not_a_finite_positive_number_is_refused(bare_console, budget):
    with pytest.raises(console_server.ConsoleError, match="a budget is a positive number"):
        console_server._opts(bare_console, {"budget": budget})


@pytest.mark.parametrize(
    ("budget", "forwarded"), [("5", "5"), ("0.5", "0.5"), (5, "5"), (" 5 ", "5"), (2.5, "2.5")]
)
def test_a_good_budget_is_forwarded_as_a_clean_number(bare_console, budget, forwarded):
    assert console_server._opts(bare_console, {"budget": budget}).budget == forwarded


@pytest.mark.parametrize("body", [{}, {"budget": ""}, {"budget": None}])
def test_no_budget_means_none_is_forwarded(bare_console, body):
    assert console_server._opts(bare_console, body).budget is None


def test_a_bad_budget_over_http_is_a_409_and_starts_nothing(console, run):
    with _serving(console) as port:
        status, _, data = _req(
            port, "POST", f"/api/runs/{run.root.name}/run-to-gate", {"budget": "inf"}
        )
    assert status == 409
    assert b"a budget is a positive number of dollars" in data


# -- set-limit over HTTP ---------------------------------------------------------


@pytest.mark.parametrize(
    "limits",
    [
        {"max_scenarios": "abc"},
        {"max_scenarios": "3.5"},
        {"max_scenarios": 2.9},
        {"max_scenarios": True},
        {"max_scenarios": 0},
        {"max_scenarios": -3},
        {"max_scenarios": [4]},
        {"max_scenarios": 1e400},  # JSON's Infinity once escaped as OverflowError
    ],
    ids=repr,
)
def test_set_limit_with_a_bad_value_is_a_409_naming_the_limit(console, run, limits):
    before = run.manifest.read_bytes()
    with _serving(console) as port:
        status, _, body = _req(
            port, "POST", f"/api/runs/{run.root.name}/set-limit", {"limits": limits, "reason": "r"}
        )
    assert status == 409, body
    assert b"max_scenarios must be a whole number" in body
    assert run.manifest.read_bytes() == before


@pytest.mark.parametrize("limits", [["max_scenarios", 4], "max_scenarios=4", 4], ids=repr)
def test_set_limit_with_limits_that_are_not_an_object_is_a_409(console, run, limits):
    with _serving(console) as port:
        status, _, body = _req(
            port, "POST", f"/api/runs/{run.root.name}/set-limit", {"limits": limits, "reason": "r"}
        )
    assert status == 409, body
    assert b"limits must be an object" in body


@pytest.mark.parametrize("value", ["4", 4], ids=repr)
def test_set_limit_over_http_reaches_rubrica_as_digits(console, run, monkeypatch, value):
    seen: list[list[str]] = []

    def human(name, title, commands):
        seen.extend(commands)
        return Job(id="j", run=name, step="human", title=title, kind="gate", status="succeeded")

    monkeypatch.setattr(console, "_human", human)
    with _serving(console) as port:
        status, _, body = _req(
            port,
            "POST",
            f"/api/runs/{run.root.name}/set-limit",
            {"limits": {"max_scenarios": value}, "reason": "raise it"},
        )
    assert status == 200, body
    [args] = seen
    assert args[0] == "set-limit"
    assert args[args.index("--max-scenarios") + 1] == "4"
