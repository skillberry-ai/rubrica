"""The console's HTTP surface: what reaches a dispatch, and what never can.

Driven over real HTTP on an OS-chosen port, because the properties that matter
-- the token, the Host check, what a path resolves to -- live in the request
handling, not in a function a unit test could call around it.
"""

from __future__ import annotations

import http.client
import json
import threading
from contextlib import contextmanager
from html import escape

import pytest
from rubrica_console import server as console_server
from rubrica_console.cli import main
from rubrica_console.jobs import Console

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


def test_gate_approval_over_http_records_the_note(console, run):
    with _serving(console) as port:
        status, _, body = _req(
            port, "POST", f"/api/runs/{run.root.name}/gates/3/approve", {"note": "verdicts read"}
        )
    assert status == 200, body
    assert "human gate 3 (console): verdicts read" in run.decisions.read_text()


def test_a_refused_action_is_a_409_with_the_reason(console, run):
    with _serving(console) as port:
        # Feedback with no text says nothing, so it is refused; approval is not.
        status, _, body = _req(port, "POST", f"/api/runs/{run.root.name}/gates/3/feedback", {})
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


def test_the_gates_with_a_structured_brief_carry_its_data(console, run):
    with _serving(console) as port:
        replies = {
            gate: json.loads(_req(port, "GET", f"/api/runs/{run.root.name}/gate/{gate}")[2])
            for gate in brief.GATES
        }
    for gate in brief.GATES:
        if gate in brief.GATE_DATA_GATES:
            assert replies[gate]["data"] == brief.gate_data(run, gate)
        else:
            assert "data" not in replies[gate]


def test_gate_0_changes_over_http_overrule_and_reseal(tmp_path):
    staged = build_toy_run(tmp_path / "staged", upto="triage-seal")
    console = Console(staged.root.parent, tmp_path / "lab", dispatch_script=tmp_path / "none.sh")
    change = {
        "candidate": "notes-md",
        "action": "decline",
        "reason_code": "superseded",
        "reason": "the api file says it all",
    }
    with _serving(console) as port:
        status, _, body = _req(
            port, "POST", f"/api/runs/{staged.root.name}/gates/0/changes", {"changes": [change]}
        )
        data = json.loads(_req(port, "GET", f"/api/runs/{staged.root.name}/gate/0")[2])["data"]
    assert status == 200, body
    assert json.loads(body)["status"] == "succeeded"
    notes = next(f for f in data["files"] if f["candidate_id"] == "notes-md")
    assert (notes["decision"], notes["triage_decision"], notes["authority"]) == (
        "decline",
        "admit",
        "human",
    )


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
