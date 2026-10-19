"""The console's HTTP server: a JSON API, the single-page UI, and the report pages.

It binds to 127.0.0.1 by default, and that matters more now than when this was a
viewer: the server can start model dispatches, which spend money, and the run
directories hold copies of the target's corpus in `00-inputs/`.

Two checks stand between a web page and a dispatch, because being on loopback is
not enough on its own -- any page open in the same browser can send requests to
127.0.0.1:

- **A per-process token on every POST**, in the `X-Rubrica-Token` header. The
  token is written into the UI page this server serves; another site's script can
  send a request here but cannot read that page, so it cannot learn the token.
- **The `Host` header must name this server** (`127.0.0.1:<port>`,
  `localhost:<port>`) when bound to loopback, on every request. That closes DNS
  rebinding, where a hostile domain re-points itself at 127.0.0.1 so the browser
  treats this server as same-origin with it. An `Origin` header, when present,
  must match too.

Nothing here writes a run artifact: every action is a `jobs.Console` call, which
runs the `rubrica` CLI or `scripts/dispatch-stage.sh` as a subprocess.
"""

from __future__ import annotations

import json
import mimetypes
import os
import secrets
import sys
import time
import traceback
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from rubrica import brief, summary, survey, target_brief, validate, waivers
from rubrica.paths import RunPaths
from rubrica_console import credentials, pipeline
from rubrica_console.jobs import Console, ConsoleError, Options

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
TOKEN_HEADER = "X-Rubrica-Token"
_MAX_BODY = 1 << 20
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}
# A client that went away mid-request. Not ConnectionError as a whole: a refused
# outbound connection is a different thing and should still be reported.
_GONE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)
# How much of a log one poll returns. A dispatch log is a stream-json transcript
# and can run to megabytes; the UI asks for the tail and then follows it.
_LOG_CHUNK = 256 * 1024
# The most file paths one expansion returns. Each hand-picked file is one extract
# dispatch, so a selection past this is a corpus, and survey is the mode for it.
_EXPAND_CAP = 5000
# How long and how far one count may walk before it answers "at least N".
_EXPAND_SECONDS = 3.0
_EXPAND_WALK_CAP = 50_000


def _static(name: str) -> bytes:
    return resources.files("rubrica_console").joinpath("static", name).read_bytes()


def _report_nav(name: str, current: str) -> str:
    base = f"/runs/{escape(name)}"
    links = [("/#/run/" + escape(name), "← Console"), (f"{base}/", "Run summary")]
    links += [(f"{base}/gate/{g}", f"Gate {g}") for g in brief.GATES]
    links += [(f"{base}/target-brief.html", "Target brief")]
    items = " ".join(
        f'<a href="{href}"{" aria-current=page" if href == current else ""}>{escape(label)}</a>'
        for href, label in links
    )
    return (
        '<nav id="rubrica-console-nav" style="position:sticky;top:0;z-index:10;display:flex;'
        "flex-wrap:wrap;gap:12px;align-items:center;padding:8px 16px;margin:-8px -8px 16px;"
        "background:Canvas;color:CanvasText;border-bottom:1px solid GrayText;"
        f'font:14px system-ui,sans-serif"><strong>{escape(name)}</strong> {items}</nav>'
        "<style>#rubrica-console-nav a{color:LinkText}"
        "#rubrica-console-nav a[aria-current]{font-weight:700;text-decoration:none}</style>"
    )


def decorate(page: str, nav: str) -> str:
    """`page` with a navigation bar added after `<body>`; nothing else changes.

    Inserted around the renderer's markup rather than threaded into it, so
    `run-summary` and `target-brief` write byte-for-byte the pages they always
    have, and this view cannot drift from them.
    """
    if "<body>" in page:
        return page.replace("<body>", "<body>" + nav, 1)
    return nav + page


def _text_page(title: str, body: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>{escape(title)}</title></head>"
        '<body style="font:15px system-ui,sans-serif;margin:8px 24px">'
        f"<h1>{escape(title)}</h1>{body}</body></html>"
    )


def _gate_page(run: RunPaths, gate: int) -> str:
    text = brief.gate_brief(run, gate)
    return _text_page(
        f"{run.root.name} — gate {gate}",
        f'<pre style="white-space:pre-wrap;font:13px ui-monospace,monospace">{escape(text)}</pre>',
    )


def _opts(console: Console, body: dict) -> Options:
    effort = body.get("effort") or console.defaults.effort
    if effort not in validate.manifest_stage_efforts():
        raise ConsoleError(f"effort must be one of {validate.manifest_stage_efforts()}")
    budget = body.get("budget")
    if budget not in (None, ""):
        try:
            if float(budget) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ConsoleError("a budget is a positive number of dollars") from None
        budget = str(budget)
    else:
        budget = None
    model = (body.get("model") or console.defaults.model).strip()
    if not model or any(c.isspace() for c in model):
        raise ConsoleError("a model id has no spaces")
    return Options(model=model, effort=effort, budget=budget, agents=body.get("agents") or None)


class Handler(BaseHTTPRequestHandler):
    console: Console
    token: str
    root: Path  # the file picker's root
    bound_host: str

    server_version = "rubrica-console"

    def log_message(self, format, *args):
        # Quiet: the UI polls every two seconds per open tab, and one line per
        # poll would drown the URL line an operator needs. Errors still reach
        # stderr through the traceback in _dispatch.
        return

    # -- plumbing ------------------------------------------------------------

    def _send(self, status: HTTPStatus, body: bytes, content_type: str, head: bool = False):
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            if not head:
                self.wfile.write(body)
        except _GONE:
            # The browser stopped waiting -- a closed picker, a page left, a newer
            # count superseding this one. Normal, not an error: there is nobody to
            # answer, so stop. Measured before this catch: the write raised
            # BrokenPipeError, _handle's catch-all then tried to send a 500 down the
            # same dead socket, and each dropped request printed two tracebacks.
            self.close_connection = True

    def _json(self, status: HTTPStatus, data, head: bool = False):
        body = json.dumps(data, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", head)

    def _html(self, status: HTTPStatus, page: str, head: bool = False):
        self._send(status, page.encode("utf-8"), "text/html; charset=utf-8", head)

    def _host_ok(self) -> bool:
        if self.bound_host not in _LOOPBACK:
            # Bound to a real interface on purpose (--host): the operator chose to
            # be reachable by name, so the token is the check that remains.
            return True
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        host = self.headers.get("Host", "")
        if host not in allowed:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin in {f"http://{h}" for h in allowed}

    def _segments(self) -> list[str]:
        # Split before unquoting, so a step id carrying an encoded "/" (round-1/propose)
        # stays one segment.
        raw = urlsplit(self.path).path
        return [unquote(s) for s in raw.split("/") if s]

    def _query(self) -> dict[str, str]:
        return {k: v[-1] for k, v in parse_qs(urlsplit(self.path).query).items()}

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > _MAX_BODY:
            raise ConsoleError("request body too large")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            raise ConsoleError("the request body is not JSON") from None
        if not isinstance(data, dict):
            raise ConsoleError("the request body must be a JSON object")
        return data

    # -- verbs ---------------------------------------------------------------

    def do_HEAD(self):
        self._handle("GET", head=True)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def _handle(self, method: str, head: bool = False):
        if not self._host_ok():
            return self._json(HTTPStatus.FORBIDDEN, {"error": "unexpected Host or Origin"}, head)
        if method == "POST" and not secrets.compare_digest(
            self.headers.get(TOKEN_HEADER, ""), self.token
        ):
            return self._json(HTTPStatus.FORBIDDEN, {"error": "missing or wrong console token"})
        try:
            if method == "GET":
                return self._get(head)
            return self._post()
        except _GONE:
            # Raised while reading the request body, before any reply: same case.
            self.close_connection = True
            return None
        except ConsoleError as exc:
            return self._json(HTTPStatus.CONFLICT, {"error": str(exc)}, head)
        except Exception as exc:
            traceback.print_exc()
            return self._json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"{type(exc).__name__}: {exc}"},
                head,
            )

    # -- GET -----------------------------------------------------------------

    def _get(self, head: bool):
        seg = self._segments()
        if not seg or seg == ["index.html"]:
            page = _static("index.html").decode("utf-8").replace("__RUBRICA_TOKEN__", self.token)
            return self._html(HTTPStatus.OK, page, head)
        if seg[0] == "static" and len(seg) == 2 and seg[1] in ("app.js", "app.css"):
            kind = "text/javascript" if seg[1].endswith(".js") else "text/css"
            return self._send(HTTPStatus.OK, _static(seg[1]), f"{kind}; charset=utf-8", head)
        if seg[0] == "api":
            return self._json(HTTPStatus.OK, self._api_get(seg[1:]), head)
        if seg[0] == "runs" and len(seg) >= 2:
            return self._report(seg[1], seg[2:], head)
        return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"}, head)

    def _api_get(self, seg: list[str]):
        c = self.console
        if seg == ["state"]:
            return {
                "runs_dir": str(c.runs_dir),
                "lab": str(c.lab),
                "root": str(self.root),
                "runs": [self._run_row(n) for n in c.list_runs()],
                "defaults": {"model": c.defaults.model, "effort": c.defaults.effort},
                "efforts": list(validate.manifest_stage_efforts()),
                "max_parallel": c.max_parallel,
                "prompt_ready": c.prompt_ready(),
                "prompt_reason": "" if c.prompt_ready() else c.prompt_unavailable_reason(),
                "waivable_checks": list(waivers.WAIVABLE_CHECKS),
                "remedies": list(waivers.remedy_choices()),
            }
        if len(seg) == 2 and seg[0] == "runs":
            return self._run_detail(seg[1])
        if seg == ["credentials"]:
            return self._credentials_view()
        if len(seg) == 3 and seg[0] == "runs" and seg[2] == "spec":
            return c.run_spec(seg[1])
        if len(seg) == 3 and seg[0] == "runs" and seg[2] == "preview":
            return {"steps": [s.as_dict() for s in c.preview_to_gate(seg[1])]}
        if len(seg) == 4 and seg[0] == "runs" and seg[2] == "gate":
            gate = self._gate_number(seg[3])
            run = c.run_paths(seg[1])
            reply = {"text": brief.gate_brief(run, gate), "history": c.gate_history(seg[1], gate)}
            # The structured brief, where one is built: what the page draws its
            # cards and checkboxes from. Gates without one keep the text sections.
            if gate in brief.GATE_DATA_GATES:
                reply["data"] = brief.gate_data(run, gate)
            return reply
        if len(seg) == 2 and seg[0] == "jobs":
            return c.job(seg[1]).as_dict()
        if len(seg) == 3 and seg[0] == "jobs" and seg[2] == "log":
            return self._log(seg[1])
        if seg == ["fs"]:
            return self._fs(self._query().get("path") or str(self.root))
        raise ConsoleError("no such API path")

    def _credentials_view(self) -> dict:
        store = self.console.credentials
        try:
            view = store.load().view()
            view["error"] = ""
        except credentials.CredentialError as exc:
            view = credentials.Credentials().view()
            view["error"] = str(exc)
        view["path"] = str(store.path)
        view["insecure"] = store.insecure()
        return view

    def _run_row(self, name: str) -> dict:
        try:
            steps = self.console.steps(name)
        except Exception as exc:  # one broken run must not hide the others
            return {"name": name, "error": f"{type(exc).__name__}: {exc}"}
        nxt = pipeline.next_step(steps)
        active = self.console.active_job(name)
        # What the run is about, for a card a human can recognise; a run whose
        # inputs cannot be read back still lists, just without a target.
        try:
            spec = self.console.run_spec(name)
        except Exception:
            spec = {}
        phases: dict[str, list[int]] = {}
        for s in steps:
            done_total = phases.setdefault(s.phase, [0, 0])
            done_total[0] += s.status == pipeline.DONE
            done_total[1] += 1
        return {
            "name": name,
            "target": spec.get("target_name") or "",
            "interface": spec.get("target_interface") or "",
            "mode": spec.get("mode") or "",
            "phases": [{"phase": k, "done": v[0], "total": v[1]} for k, v in phases.items()],
            "failed": any(s.status == pipeline.FAILED for s in steps),
            "done": sum(s.status == pipeline.DONE for s in steps),
            "total": len(steps),
            "next": nxt.title if nxt else "complete",
            "next_kind": nxt.kind if nxt else None,
            "running": active.title if active else None,
            "cost": self.console.run_cost(name),
        }

    def _run_detail(self, name: str) -> dict:
        c = self.console
        steps = c.steps(name)
        active = c.active_job(name)
        jobs = c.jobs(name)
        row = self._run_row(name)
        return {
            "name": name,
            "target": row.get("target", ""),
            "interface": row.get("interface", ""),
            "mode": row.get("mode", ""),
            "phases": row.get("phases", []),
            "root": str(c.run_paths(name).root),
            "steps": [s.as_dict() for s in steps],
            "next": (pipeline.next_step(steps) or pipeline.Step("", "", "")).id or None,
            "active": active.as_dict() if active else None,
            "jobs": [j.as_dict() for j in jobs[:40]],
            "cost": c.run_cost(name),
            "ledger": c.ledger_view(name),
        }

    def _gate_number(self, raw: str) -> int:
        if not raw.isdigit() or int(raw) not in brief.GATES:
            raise ConsoleError(f"gates are {brief.GATES}")
        return int(raw)

    def _log(self, job_id: str) -> dict:
        job = self.console.job(job_id)
        q = self._query()
        if "member" in q:
            member = job.members.get(q["member"])
            if member is None:
                raise ConsoleError("no such member in this job")
            path = Path(member.log)
        else:
            index = int(q.get("entry", -1))
            if not job.entries or not -len(job.entries) <= index < len(job.entries):
                raise ConsoleError("no such entry in this job")
            path = Path(job.entries[index].log)
        try:
            data = path.read_bytes()
        except OSError:
            data = b""
        offset = int(q.get("offset", -1))
        if offset < 0 or offset > len(data):
            offset = max(0, len(data) - _LOG_CHUNK)
        chunk = data[offset : offset + _LOG_CHUNK]
        return {"text": chunk.decode("utf-8", errors="replace"), "next": offset + len(chunk)}

    def _fs(self, raw: str) -> dict:
        root = self.root.resolve()
        target = Path(raw).expanduser().resolve()
        if not target.is_relative_to(root):
            raise ConsoleError(f"the picker is limited to {root}")
        secret = self.console.credentials.path.expanduser().resolve()
        if not target.is_dir():
            raise ConsoleError(f"not a folder: {target}")
        entries = []
        try:
            children = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError as exc:
            raise ConsoleError(f"cannot list {target}: {exc}") from exc
        for child in children:
            if child.name.startswith(".") or child.resolve() == secret:
                continue
            try:
                is_dir = child.is_dir()
                # Not resolved: a symlink out of the root is listed by its own path,
                # and following it is refused on the next listing by the check above.
                entries.append(
                    {
                        "name": child.name,
                        "path": str(child),
                        "dir": is_dir,
                        "size": None if is_dir else child.stat().st_size,
                    }
                )
            except OSError:
                continue
        parent = str(target.parent) if target != root else None
        return {"path": str(target), "parent": parent, "entries": entries[:2000]}

    def _expand(self, body: dict) -> dict:
        """What a picker selection amounts to: included paths minus excluded ones.

        Folders expand to every file under them, without following symlinks and
        skipping dot-directories (`.git`, `.venv`) and the vendored folders survey
        skips (`node_modules`, `dist`, ...), and nothing outside the picker's root
        is ever read. A walk that runs out of time or files answers with
        `partial: true`, and the page never uses a partial list as inputs.
        Hand-pick mode uses the file list as intake's inputs; survey mode only
        shows the count, since `survey` walks the roots
        itself and also drops VCS, vendored, lock and gitignored files.
        """
        root = self.root.resolve()
        # The separator is part of the prefix, so `/home/al` does not admit `/home/alex`.
        root_prefix = str(root).rstrip(os.sep) + os.sep

        def inside(raw) -> Path:
            # Resolved as a string and checked before any Path is built, and the
            # resolved path is what is returned: checking `Path(raw).resolve()` but
            # returning the unresolved `Path(raw)` left what was checked and what was
            # walked as two different values, and CodeQL's py/path-injection flagged
            # it (it recognises a realpath-then-prefix guard, not `is_relative_to`).
            if not isinstance(raw, str) or not raw:
                raise ConsoleError("a selected path must be a non-empty string")
            resolved = os.path.realpath(os.path.expanduser(raw))
            # One `startswith` on the separator-terminated form, rather than
            # `== root or startswith(root + sep)`: it admits the root itself, refuses
            # a sibling like `<root>-evil`, and is the single-call guard shape CodeQL
            # treats as a sanitizer -- the two-condition form was still flagged.
            if not (resolved.rstrip(os.sep) + os.sep).startswith(root_prefix):
                raise ConsoleError(f"the picker is limited to {root}")
            return Path(resolved)

        secret = self.console.credentials.path.expanduser().resolve()
        include = [inside(p) for p in body.get("include") or []]
        exclude = {inside(p).resolve() for p in body.get("exclude") or []}

        def excluded(path: Path) -> bool:
            resolved = path.resolve()
            return any(resolved == e or resolved.is_relative_to(e) for e in exclude)

        files: list[str] = []
        seen: set[Path] = set()
        total_bytes = 0
        cap = _EXPAND_CAP
        # Bounded in time and in files walked, because a selection can be a home
        # directory: measured, checking one sent this walk through ~/Library for
        # minutes while the page piled up newer requests behind it. A partial count
        # says so; it never pretends to be the total.
        deadline = time.monotonic() + _EXPAND_SECONDS
        partial = False
        for start in include:
            if partial:
                break
            if excluded(start):
                continue
            if start.is_file():
                candidates = [start]
            elif start.is_dir():
                candidates = []
                for dirpath, dirnames, filenames in os.walk(start, followlinks=False):
                    if time.monotonic() > deadline or len(candidates) > _EXPAND_WALK_CAP:
                        partial = True
                        break
                    here = Path(dirpath)
                    # The folders survey itself never reads, so the count matches it.
                    dirnames[:] = sorted(
                        d
                        for d in dirnames
                        if not d.startswith(".")
                        and d not in survey._VENDOR_DIRS
                        and not excluded(here / d)
                    )
                    candidates += [here / f for f in sorted(filenames) if not f.startswith(".")]
            else:
                continue
            for path in candidates:
                # Checked here too: measured, resolving and stat-ing each file is the
                # slow half, and a check only between folders let a 3-second limit
                # run to 13 seconds over a home directory.
                if time.monotonic() > deadline:
                    partial = True
                    break
                resolved = path.resolve()
                # The console's own credentials are never an input to anything.
                if resolved == secret:
                    continue
                if resolved in seen or excluded(path) or not resolved.is_relative_to(root):
                    continue
                if not path.is_file():
                    continue
                seen.add(resolved)
                try:
                    total_bytes += path.stat().st_size
                except OSError:
                    continue
                if len(files) < cap:
                    files.append(str(path))
        return {
            "files": files,
            "total": len(seen),
            "bytes": total_bytes,
            "truncated": len(seen) > len(files),
            # True when the walk stopped early: `total` is then "at least".
            "partial": partial,
        }

    # -- report pages --------------------------------------------------------

    def _report(self, name: str, rest: list[str], head: bool):
        run = self.console.run_paths(name)
        base = f"/runs/{name}"
        try:
            if not rest:
                page = decorate(summary.run_summary(run), _report_nav(name, f"{base}/"))
                return self._html(HTTPStatus.OK, page, head)
            if rest == ["target-brief.html"]:
                page = decorate(
                    target_brief.page(run), _report_nav(name, f"{base}/target-brief.html")
                )
                return self._html(HTTPStatus.OK, page, head)
            if len(rest) == 2 and rest[0] == "gate":
                gate = self._gate_number(rest[1])
                nav = _report_nav(name, f"{base}/gate/{gate}")
                return self._html(HTTPStatus.OK, decorate(_gate_page(run, gate), nav), head)
        except ConsoleError:
            raise
        except Exception as exc:
            traceback.print_exc()
            page = _text_page(
                "Could not render this report",
                "<p>The command-line equivalent would fail too. "
                f"<code>{escape(type(exc).__name__)}: {escape(str(exc))}</code></p>",
            )
            return self._html(HTTPStatus.INTERNAL_SERVER_ERROR, page, head)
        return self._file(run, rest, head)

    def _file(self, run: RunPaths, rest: list[str], head: bool):
        """A file under the run directory, so run-summary's relative links resolve.

        Resolved and then checked to be inside the run, so neither `..` nor a
        symlink pointing out of the run can reach the rest of the filesystem.
        """
        root = run.root.resolve()
        target = root.joinpath(*rest).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            return self._json(HTTPStatus.NOT_FOUND, {"error": "no such file in this run"}, head)
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type == "application/json":
            content_type += "; charset=utf-8"
        # Served as data, never as a page from this origin: an HTML file in a corpus
        # copy must not run script with access to the console's token.
        if content_type.startswith("text/html"):
            content_type = "text/plain; charset=utf-8"
        return self._send(HTTPStatus.OK, target.read_bytes(), content_type, head)

    def _credentials_post(self, action: list[str], body: dict):
        store = self.console.credentials
        try:
            if action == []:
                store.update(body)
            elif action == ["import"]:
                store.import_claude_settings()
            elif action == ["clear"]:
                store.clear()
            elif action == ["test"]:
                model = (body.get("model") or self.console.defaults.model).strip()
                result = credentials.test(store.load(), model)
                return self._json(HTTPStatus.OK, result)
            else:
                raise ConsoleError("no such API path")
        except credentials.CredentialError as exc:
            raise ConsoleError(str(exc)) from exc
        return self._json(HTTPStatus.OK, self._credentials_view())

    # -- POST ----------------------------------------------------------------

    def _post(self):
        c = self.console
        seg = self._segments()
        body = self._body()
        if seg == ["api", "fs", "expand"]:
            # A POST only because a selection can be longer than a URL; it reads,
            # never writes.
            return self._json(HTTPStatus.OK, self._expand(body))
        if seg[:2] == ["api", "credentials"]:
            return self._credentials_post(seg[2:], body)
        if seg == ["api", "runs"]:
            name, _, output = c.create_run(body)
            return self._json(HTTPStatus.OK, {"name": name, "output": output})
        if len(seg) == 4 and seg[:2] == ["api", "jobs"] and seg[3] == "cancel":
            return self._json(HTTPStatus.OK, c.cancel(seg[2]).as_dict())
        if len(seg) < 4 or seg[:2] != ["api", "runs"]:
            raise ConsoleError("no such API path")
        name, action = seg[2], seg[3:]
        if action == ["delete"]:
            c.delete_run(name, body.get("confirm", ""))
            return self._json(HTTPStatus.OK, {"deleted": name})
        if len(action) == 3 and action[0] == "steps" and action[2] in ("run", "repair"):
            job = c.run_step(name, action[1], _opts(c, body), repair=action[2] == "repair")
        elif len(action) == 3 and action[0] == "steps" and action[2] == "accept":
            job = c.accept(name, action[1], body.get("note", ""))
        elif action == ["run-to-gate"]:
            job = c.run_to_gate(name, _opts(c, body))
        elif len(action) == 3 and action[0] == "gates" and action[2] == "approve":
            job = c.approve_gate(name, self._gate_number(action[1]), body.get("note", ""))
        elif action == ["gates", "1", "changes"]:
            job = c.gate1_changes(
                name,
                body.get("changes") or [],
                body.get("note", ""),
                approve=bool(body.get("approve")),
            )
        elif action == ["gates", "1", "rerun"]:
            job = c.rerun_for_rulings(name, _opts(c, body))
        elif action == ["gates", "0", "changes"]:
            job = c.gate0_changes(
                name,
                body.get("changes") or [],
                body.get("note", ""),
                approve=bool(body.get("approve")),
            )
        elif len(action) == 3 and action[0] == "gates" and action[2] == "feedback":
            job = c.gate_feedback(name, self._gate_number(action[1]), body.get("note", ""))
        elif action == ["stop-rounds"]:
            job = c.stop_rounds(name, body.get("note", ""))
        elif action == ["decide"]:
            job = c.decide(name, body.get("note", ""))
        elif action == ["waive"]:
            job = c.waive(
                name,
                body.get("check", ""),
                body.get("subject", ""),
                body.get("remedy", ""),
                body.get("reason", ""),
            )
        elif action == ["set-limit"]:
            limits = {k: v for k, v in (body.get("limits") or {}).items() if v not in (None, "")}
            job = c.set_limit(name, limits, body.get("reason", ""))
        else:
            raise ConsoleError("no such API path")
        return self._json(HTTPStatus.OK, job.as_dict())


def make_server(
    console: Console,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    root: Path | None = None,
    token: str | None = None,
) -> ThreadingHTTPServer:
    """A server bound and ready, not yet serving. Port 0 lets the OS pick one."""
    handler = type(
        "ConsoleHandler",
        (Handler,),
        {
            "console": console,
            "token": token or secrets.token_urlsafe(24),
            "root": (root or Path.home()).resolve(),
            "bound_host": host,
        },
    )
    server = _Server((host, port), handler)
    server.daemon_threads = True
    return server


class _Server(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        # The stdlib prints a traceback for any exception that escapes a handler.
        # A dropped connection is not one worth printing (see Handler._send); every
        # other exception still is, because that is a bug in this module.
        exc = sys.exc_info()[1]
        if isinstance(exc, _GONE):
            return
        super().handle_error(request, client_address)


def url_of(server: ThreadingHTTPServer) -> str:
    host, port = server.server_address[:2]
    return f"http://{host}:{port}/"
