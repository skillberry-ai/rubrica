# Reservation-Service Trajectory Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run rubrica against the `reservation_service` agent under a realistic
evidence boundary — tool source withheld, `/tools/list` plus captured
trajectories standing in for it — and check six pre-registered predictions.

**Architecture:** A capture harness drives the target's LangGraph graph directly
(skipping A2A) against a locally-run MCP server, with MLflow autologging real
traces. The captured `tools-list.json` and `trajectories.json` are committed as a
fixture with a provenance README and a guard test, then staged into `rubrica
intake` alongside the agent source and the two READMEs. Six `rb-extract`
dispatches fan out over the six inputs, `rb-reconcile` barriers, and the world
model is read against the predictions.

**Tech Stack:** Python 3.13 + `uv`; rubrica CLI; `fastmcp`, `langgraph`,
`langchain-openai`, `langchain-mcp-adapters`, `mlflow` 3.15.1 in a throwaway
venv; `Azure/gpt-4.1` via a litellm proxy; `scripts/dispatch-stage.sh`.

**Spec:** [`docs/superpowers/specs/2026-08-12-reservation-service-trajectory-run-design.md`](../specs/2026-08-12-reservation-service-trajectory-run-design.md)

## Global Constraints

- **Every commit signed and DCO'd: `git commit -S -s`.** Both flags. If signing
  fails, stop and report — never fall back to unsigned.
- Attribution trailer is `Assisted-By: Claude (Anthropic AI)
  <noreply@anthropic.com>`. Never `Co-Authored-By` or `Made-with`.
- ruff: `line-length = 100`, `select = ["E","F","I","UP","B","SIM"]`. `docs/` is
  excluded; **`tests/` is not**, so `capture_harness.py` must pass `make check`.
- `make check` clean and `uv run rubrica check-skills` exit 0 at every commit.
- Test baseline before this plan: **1129 passed, 4 skipped** (measured
  2026-08-12). Task 3 adds tests and must re-measure and update CLAUDE.md.
- Comment density is high and deliberate: comments explain *why*, citing a
  measurement. Match it.
- No change to rubrica source, schemas, or skills. If the run exposes a skill
  defect, that is a separate change (spec §12).
- Never register `providers/mock.py`, `schemas.py`, `providers/base.py`, or
  `reservation_tool.py` as an input (spec §4, §12).
- Rossoctl source pinned at `dbbc5e0f46cc92c8f642e44d1124965394cf36e5`, working
  tree clean at capture time.
- MLflow 3.15.1 facts, all measured: field is `info.trace_id` (not
  `request_id`); the filesystem backend is in maintenance mode so a
  `sqlite:///` tracking URI is required; trace logging is async so
  `get_trace(tid, flush=True)` is required.

---

## File Structure

**Created:**

| Path | Responsibility |
|---|---|
| `tests/fixtures/reservation-trajectories/capture_harness.py` | Produces both artifacts. Provenance, never run by CI. |
| `tests/fixtures/reservation-trajectories/tools-list.json` | Captured `/tools/list`, 5 tools. |
| `tests/fixtures/reservation-trajectories/trajectories.json` | Captured traces, JSON array. |
| `tests/fixtures/reservation-trajectories/README.md` | Capture conditions, prompt list, substitution rules. |
| `tests/unit/test_trajectory_fixtures.py` | Guard: the fixture still carries what the experiment depends on. |

**Modified:**

| Path | Change |
|---|---|
| `tests/toy.py:29-31` | Add `TRAJECTORIES_DIR`, following the existing `*_DIR` pattern. |
| `CLAUDE.md` | Re-measured test baseline. |

**Working directory (not committed):** `/tmp/rubrica-lab/capture/` holds the
venv and `mlflow.db`. `/tmp/rubrica-lab/inputs-trajectory-run/` holds the staged
inputs.

`capture_harness.py` is named so pytest does not collect it (collection matches
`test_*.py` / `*_test.py`). It is still linted, hence the ruff constraint.

---

## Task 1: Capture `/tools/list`

**Files:**
- Create: `tests/fixtures/reservation-trajectories/capture_harness.py`
- Create (output): `tests/fixtures/reservation-trajectories/tools-list.json`

**Interfaces:**
- Consumes: nothing.
- Produces: `capture_tools_list(out_path: Path) -> int` returning the tool count;
  a `main()` with argparse subcommands `tools-list` and `trajectories`. Task 2
  extends the same file and relies on both names.

- [ ] **Step 1: Create the working directory**

```bash
mkdir -p /tmp/rubrica-lab/capture
cd /home/bnayahu/work/rossoctl/examples && git rev-parse HEAD && git status --short
```

Expected: `dbbc5e0f46cc92c8f642e44d1124965394cf36e5` and empty status. If the SHA
differs, stop — the spec pins this and a different tree means different
artifacts.

- [ ] **Step 2: Write the harness skeleton and the tools-list subcommand**

Create `tests/fixtures/reservation-trajectories/capture_harness.py`:

```python
"""Capture `/tools/list` and agent trajectories for the trajectory run.

Provenance, not a test. pytest never collects this (the name does not match
`test_*.py`) and CI never runs it: it needs `fastmcp`, `langgraph`,
`langchain-openai`, `langchain-mcp-adapters` and `mlflow`, none of which are
rubrica dependencies, plus a reachable litellm proxy. It lives beside the
artifacts it produced so a reader can see exactly how they were made -- the
design spec's section 10 reasoning, that a re-capture draws fresh LLM spans and
a fresh confirmation_code sequence, so without this file nobody could later
distinguish a pipeline change from a capture change.

Run it from a throwaway venv; the fixture README carries the exact command.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

# The tool server and the LangChain client spell this env var's value
# differently, and both spellings are correct for their own side: FastMCP wants
# "streamable-http", langchain-mcp-adapters wants "streamable_http". This is the
# contradiction the control run's rb-reconcile found and resolved as
# `both_possible` -- it was right, and it is also a real deployment hazard,
# because a deployment setting one MCP_TRANSPORT for both processes breaks one
# of them. The harness therefore sets them per-process and never globally.
SERVER_TRANSPORT = "streamable-http"
CLIENT_TRANSPORT = "streamable_http"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8765

TOOL_DIR = Path("/home/bnayahu/work/rossoctl/examples/mcp/reservation_tool")
AGENT_SRC = Path("/home/bnayahu/work/rossoctl/examples/a2a/reservation_service/src")


def capture_tools_list(out_path: Path) -> int:
    """Write the MCP-protocol `/tools/list` document, and return the tool count.

    Read in-process via `list_tools()` rather than over HTTP. The design spec
    permits this: `list_tools()` reads the registered tool definitions and never
    touches MockProvider, so it cannot perturb the `_reservation_counter`
    ordering the trajectory capture depends on. `to_mcp_tool()` is what makes
    the result the wire shape rather than FastMCP's internal object -- measured:
    `FunctionTool` has no `inputSchema` attribute, only `parameters`, so
    serialising the object directly would produce a document no MCP client
    would ever see.
    """
    import asyncio

    sys.path.insert(0, str(TOOL_DIR))
    import reservation_tool as rt

    async def _list():
        return await rt.mcp.list_tools()

    tools = asyncio.run(_list())
    doc = {
        "tools": [
            json.loads(t.to_mcp_tool().model_dump_json(exclude_none=True)) for t in tools
        ]
    }
    out_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return len(doc["tools"])


def _port_open(host: str, port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def start_server() -> subprocess.Popen:
    """Launch the MCP server and block until its port accepts connections.

    Readiness is polled rather than slept on: a fixed sleep either wastes time
    or races, and a race here shows up as an empty trajectory rather than an
    error, which is the worst failure mode for an artifact nobody re-reads.
    """
    env = {
        **os.environ,
        "MCP_TRANSPORT": SERVER_TRANSPORT,
        "HOST": SERVER_HOST,
        "PORT": str(SERVER_PORT),
    }
    proc = subprocess.Popen(
        [sys.executable, "-c", "import reservation_tool; reservation_tool.run_server()"],
        cwd=str(TOOL_DIR),
        env=env,
    )
    for _ in range(120):
        if _port_open(SERVER_HOST, SERVER_PORT):
            return proc
        if proc.poll() is not None:
            raise RuntimeError(f"MCP server exited early with code {proc.returncode}")
        time.sleep(0.25)
    proc.terminate()
    raise RuntimeError(f"MCP server did not open {SERVER_HOST}:{SERVER_PORT} within 30s")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_tools = sub.add_parser("tools-list")
    p_tools.add_argument("--out", required=True)
    p_traj = sub.add_parser("trajectories")
    p_traj.add_argument("--out", required=True)

    args = parser.parse_args()
    if args.command == "tools-list":
        n = capture_tools_list(Path(args.out))
        print(f"wrote {args.out} with {n} tools")
        return 0
    if args.command == "trajectories":
        raise SystemExit("trajectories: implemented in Task 2")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run the tools-list capture**

```bash
cd /tmp/rubrica-lab/capture
FIX=/home/bnayahu/work/kaegis/rubrica/tests/fixtures/reservation-trajectories
mkdir -p "$FIX"
uv run --with fastmcp --with pydantic python "$FIX/capture_harness.py" \
  tools-list --out "$FIX/tools-list.json"
```

Expected: `wrote .../tools-list.json with 5 tools`

- [ ] **Step 4: Verify the artifact matches the spec's premise**

```bash
FIX=/home/bnayahu/work/kaegis/rubrica/tests/fixtures/reservation-trajectories
python3 -c "
import json
d=json.load(open('$FIX/tools-list.json'))
names=sorted(t['name'] for t in d['tools'])
print('tools:', names)
assert names == ['cancel_reservation','check_availability','list_reservations',
                 'place_reservation','search_restaurants'], names
for t in d['tools']:
    props = t['inputSchema']['properties']
    assert props, t['name']
    os_ = t.get('outputSchema') or {}
    assert os_.get('properties',{}).get('result',{}).get('type') == 'string', t['name']
print('inputs specified, all five outputSchemas opaque -- spec section 3 premise holds')
"
```

Expected: the five names, then the premise line. **If any `outputSchema` is not
the opaque `{result: string}` wrapper, stop and report** — the experiment's
central premise (§3) has changed and the spec needs revising before capture.

- [ ] **Step 5: Lint and commit**

```bash
cd /home/bnayahu/work/kaegis/rubrica
make check
git add tests/fixtures/reservation-trajectories/
git commit -S -s -m "feat: Capture the reservation tool's /tools/list document

Measured and asserted at capture time: all five outputSchemas are the opaque
{result: string} wrapper, so /tools/list specifies how to call each tool and
says nothing about what comes back. That asymmetry is the premise the
trajectory run rests on, so the capture step checks it rather than assuming it.

Read in-process via list_tools() + to_mcp_tool(). Serialising FunctionTool
directly would not give the wire shape -- it has no inputSchema attribute,
only parameters.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 2: Capture the trajectories

**Files:**
- Modify: `tests/fixtures/reservation-trajectories/capture_harness.py`
- Create (output): `tests/fixtures/reservation-trajectories/trajectories.json`

**Interfaces:**
- Consumes: `start_server()`, `SERVER_*`/`CLIENT_TRANSPORT`, `AGENT_SRC` from Task 1.
- Produces: `trajectories.json` as a JSON array of MLflow trace dicts, each with
  an added top-level `trace_id`. Task 3's guard test and Task 4's intake depend
  on that mirror.

- [ ] **Step 1: Add the prompt list and the trajectory capture**

Replace the `trajectories` branch stub and add above `main()`:

```python
# Ten prompts. Five happy paths, five aimed at the output questions the control
# run could not answer. Prompts 7 and 8 name an obviously-invalid id explicitly,
# because a model told only "a restaurant that does not exist" will search first
# and never drive the error path.
#
# {restaurant_id} and {reservation_id} are filled from an OBSERVED span output,
# never authored -- see substitute() below.
PROMPTS: list[tuple[str, str]] = [
    ("p01-search", "Find Italian restaurants in Boston"),
    ("p02-search-then-check",
     "Find Italian restaurants in Boston, then check availability at the first "
     "one for 4 people on 2025-03-15 at 7:00 PM"),
    ("p03-place",
     "Book a table at restaurant {restaurant_id} for 2025-03-15T19:00:00, party "
     "of 4. Name: Jane Smith, Phone: +1-555-987-6543, Email: jane@example.com"),
    ("p04-list", "List all reservations for jane@example.com"),
    ("p05-cancel",
     "Cancel reservation {reservation_id} because plans changed"),
    ("p06-search-empty", "Find Ethiopian restaurants in Fargo"),
    ("p07-check-unknown",
     "Check availability at restaurant rest_999 for 2 people on 2025-03-15 at "
     "8:00 PM"),
    ("p08-place-unknown",
     "Book a table at restaurant rest_999 for 2025-03-15T20:00:00, party of 2. "
     "Name: Test User, Phone: +1-555-000-0000, Email: test@example.com"),
    ("p09-list-empty", "List all reservations for nobody@example.com"),
    ("p10-cancel-unknown",
     "Cancel reservation reservation_deadbeef1234 because it does not exist"),
]


def tool_outputs(result: dict) -> list[tuple[str, str]]:
    """(tool_name, raw content) for every ToolMessage in a graph result.

    Matched on class name rather than isinstance to avoid importing
    langchain_core.messages at module scope, which would make the tools-list
    subcommand require the agent's dependency set for no reason.
    """
    out = []
    for m in result.get("messages", []):
        if type(m).__name__ == "ToolMessage":
            out.append((getattr(m, "name", ""), m.content))
    return out


def substitute(text: str, observed: dict[str, str]) -> str | None:
    """Fill {restaurant_id}/{reservation_id} from observed spans, or refuse.

    Returns None when a needed value was never observed. That is deliberate: the
    alternative is inventing an id, which would make this harness the oracle for
    the very system the experiment withholds. A skipped prompt is recorded as a
    skip; it is never replaced by a plausible-looking guess.
    """
    needed = [k for k in ("restaurant_id", "reservation_id") if "{" + k + "}" in text]
    for key in needed:
        if not observed.get(key):
            return None
    return text.format(**{k: observed[k] for k in needed})
```

- [ ] **Step 2: Add the capture driver**

```python
def capture_trajectories(out_path: Path) -> dict:
    """Drive the ten prompts through the real graph, returning a run summary.

    Drives `graph.ainvoke` directly instead of the A2A HTTP layer. graph.py is
    cleanly separable -- get_mcpclient() and get_graph() are module-level and
    agent.py only wraps them -- so this is a genuine full agent turn (LLM
    planning, tool calls, final answer) with no server to stand up.
    """
    import asyncio

    import mlflow
    from langchain_core.messages import HumanMessage

    # Measured on MLflow 3.15.1: the filesystem tracking backend is in
    # maintenance mode and makes get_trace() return None with only a warning, so
    # a sqlite URI is mandatory rather than tidy.
    db = Path("/tmp/rubrica-lab/capture/mlflow.db").resolve()
    db.parent.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(f"sqlite:///{db}")
    mlflow.set_experiment("reservation-service-trajectories")
    mlflow.langchain.autolog()

    os.environ["MCP_URL"] = f"http://{SERVER_HOST}:{SERVER_PORT}/mcp"
    os.environ["MCP_TRANSPORT"] = CLIENT_TRANSPORT
    os.environ["LLM_API_BASE"] = os.environ["OPENAI_API_BASE"].rstrip("/") + "/v1"
    os.environ["LLM_API_KEY"] = os.environ["OPENAI_API_KEY"]
    os.environ["LLM_MODEL"] = MODEL

    sys.path.insert(0, str(AGENT_SRC))
    from reservation_service.graph import get_graph, get_mcpclient

    traces: list[dict] = []
    summary = {"model": MODEL, "prompts": []}
    observed: dict[str, str] = {}

    async def _run():
        graph = await get_graph(get_mcpclient())
        for pid, template in PROMPTS:
            text = substitute(template, observed)
            if text is None:
                summary["prompts"].append({"id": pid, "status": "skipped-unobserved"})
                continue
            try:
                result = await graph.ainvoke({"messages": [HumanMessage(content=text)]})
            except Exception as exc:  # a failed turn is data, not a crash
                summary["prompts"].append(
                    {"id": pid, "status": "error", "detail": str(exc)[:300]}
                )
                continue

            calls = tool_outputs(result)
            for name, content in calls:
                try:
                    payload = json.loads(content)
                except json.JSONDecodeError:
                    continue
                if name == "search_restaurants" and isinstance(payload, list) and payload:
                    observed.setdefault("restaurant_id", payload[0].get("id", ""))
                if name == "place_reservation" and isinstance(payload, dict):
                    if payload.get("id"):
                        observed.setdefault("reservation_id", payload["id"])

            tid = mlflow.get_last_active_trace_id()
            # flush=True is mandatory: trace logging is async, and without it
            # get_trace returns None for a trace written moments earlier.
            trace = mlflow.get_trace(tid, flush=True) if tid else None
            if trace is None:
                summary["prompts"].append({"id": pid, "status": "no-trace", "text": text})
                continue
            d = trace.to_dict()
            # Additive mirror. classify() inspects payload[0] for `spans` or
            # `trace_id`; a raw MLflow trace has neither at that level (they are
            # info.trace_id and data.spans), so without this the array
            # classifies as `other`. MLflow 3 renamed request_id -> trace_id.
            d["trace_id"] = d["info"]["trace_id"]
            traces.append(d)
            summary["prompts"].append(
                {
                    "id": pid,
                    "status": "captured",
                    "text": text,
                    "tools_called": [n for n, _ in calls],
                }
            )

    asyncio.run(_run())
    out_path.write_text(json.dumps(traces, indent=2) + "\n", encoding="utf-8")
    summary["traces_written"] = len(traces)
    return summary
```

Add near the transport constants:

```python
MODEL = "Azure/gpt-4.1"
```

And replace the `trajectories` branch in `main()`:

```python
    if args.command == "trajectories":
        proc = start_server()
        try:
            summary = capture_trajectories(Path(args.out))
        finally:
            proc.terminate()
            proc.wait(timeout=10)
        print(json.dumps(summary, indent=2))
        return 0
```

- [ ] **Step 3: Run the capture, once**

```bash
cd /tmp/rubrica-lab/capture
FIX=/home/bnayahu/work/kaegis/rubrica/tests/fixtures/reservation-trajectories
uv run --with fastmcp --with pydantic --with pydantic-settings --with mlflow \
       --with langgraph --with langchain-core --with langchain-openai \
       --with langchain-mcp-adapters --with mcp \
  python "$FIX/capture_harness.py" trajectories --out "$FIX/trajectories.json" \
  | tee /tmp/rubrica-lab/capture/summary.json
```

Expected: a summary listing ten prompt entries and `traces_written`.

**Single pass. Do not re-run to get better traces.** Spec §6: re-rolling until a
trace comes out the desired shape is selection bias and reinstates the harness
author as the oracle. If a prompt shows `status: error`, `no-trace`, or
`skipped-unobserved`, record it and move on — a path never driven means the
corresponding gap stays open, which is a result.

- [ ] **Step 4: Verify what was captured, without judging it**

```bash
FIX=/home/bnayahu/work/kaegis/rubrica/tests/fixtures/reservation-trajectories
python3 -c "
import json
t=json.load(open('$FIX/trajectories.json'))
print('traces:', len(t))
for x in t:
    assert 'trace_id' in x, 'mirror missing'
    assert x['data']['spans'], 'empty spans'
errs=[x for x in t if '\"error\"' in json.dumps(x)]
print('traces containing an error response:', len(errs))
print('reservation_ prefix seen:', 'reservation_' in json.dumps(t))
print('res_12345 seen (should be False):', 'res_12345' in json.dumps(t))
"
```

Record the numbers. `traces` may be fewer than ten if prompts were skipped —
that is reportable, not fixable.

- [ ] **Step 5: Lint and commit**

```bash
cd /home/bnayahu/work/kaegis/rubrica
make check
git add tests/fixtures/reservation-trajectories/
git commit -S -s -m "feat: Capture reservation-service agent trajectories

Ten prompts through the real LangGraph graph against a local MCP server, with
Azure/gpt-4.1 behind a litellm proxy and mlflow.langchain.autolog(). Single
pass, every outcome recorded including skips -- re-rolling until a trace looks
right would make the harness the oracle for the system the run withholds.

The harness sets MCP_TRANSPORT differently per process: streamable-http for
FastMCP, streamable_http for langchain-mcp-adapters. That is the contradiction
the control run resolved as both_possible, confirmed as a real deployment
hazard -- one env var, two incompatible spellings.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 3: Fixture README, guard test, baseline

**Files:**
- Create: `tests/fixtures/reservation-trajectories/README.md`
- Create: `tests/unit/test_trajectory_fixtures.py`
- Modify: `tests/toy.py` (add `TRAJECTORIES_DIR` beside the existing `*_DIR`)
- Modify: `CLAUDE.md` (re-measured baseline)

**Interfaces:**
- Consumes: both captured artifacts from Tasks 1–2.
- Produces: `tests.toy.TRAJECTORIES_DIR: Path`.

- [ ] **Step 1: Write the failing guard test**

Create `tests/unit/test_trajectory_fixtures.py`:

```python
"""The trajectory fixture still carries what the experiment depends on.

Not a test of any skill -- a test of the fixture, in the shape of
test_refusal_fixtures.py. Two things would silently invalidate the trajectory
run if they drifted: the top-level `trace_id` mirror (without it `classify`
returns `other` and the extract member loses its kind hint), and the opaque
`outputSchema` (the run's whole premise is that /tools/list says nothing about
outputs). Neither shows up as a failure anywhere else.

Assertions are on structure and on `classify`'s verdict, never on captured
prose, so a legitimate re-capture with different LLM wording stays green.
"""

from __future__ import annotations

import json

import pytest

from rubrica.intake import classify
from tests.toy import TRAJECTORIES_DIR

TOOLS_LIST = TRAJECTORIES_DIR / "tools-list.json"
TRAJECTORIES = TRAJECTORIES_DIR / "trajectories.json"

FIVE_TOOLS = frozenset(
    {
        "search_restaurants",
        "check_availability",
        "place_reservation",
        "cancel_reservation",
        "list_reservations",
    }
)


@pytest.fixture(scope="module")
def tools_doc() -> dict:
    return json.loads(TOOLS_LIST.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def traces() -> list:
    return json.loads(TRAJECTORIES.read_text(encoding="utf-8"))


def test_tools_list_has_the_five_capabilities(tools_doc):
    assert {t["name"] for t in tools_doc["tools"]} == FIVE_TOOLS


def test_every_tool_specifies_its_inputs(tools_doc):
    for tool in tools_doc["tools"]:
        assert tool["inputSchema"]["properties"], tool["name"]


def test_no_tool_specifies_its_outputs(tools_doc):
    """The premise of the run: outputs are opaque, so trajectories are the only
    source of output knowledge. If this goes red the spec needs revising, not
    the assertion."""
    for tool in tools_doc["tools"]:
        result = tool.get("outputSchema", {}).get("properties", {}).get("result", {})
        assert result.get("type") == "string", tool["name"]


def test_tools_list_classifies_as_an_mcp_tool_schema():
    assert classify(TOOLS_LIST) == "mcp_tool_schema"


def test_every_trace_carries_the_top_level_trace_id_mirror(traces):
    for trace in traces:
        assert trace["trace_id"] == trace["info"]["trace_id"]


def test_every_trace_has_at_least_one_span(traces):
    for trace in traces:
        assert trace["data"]["spans"]


def test_trajectories_classify_as_a_trace():
    """Guards the mirror's purpose rather than its presence: without the
    top-level trace_id this returns `other`."""
    assert classify(TRAJECTORIES) == "trace"


def test_at_least_one_trace_observed_an_error_response(traces):
    """Four of the control run's five gaps are error-path questions. A fixture
    with no observed error cannot close any of them."""
    assert any("error" in json.dumps(trace) for trace in traces)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd /home/bnayahu/work/kaegis/rubrica
uv run pytest tests/unit/test_trajectory_fixtures.py -q
```

Expected: collection error — `ImportError: cannot import name 'TRAJECTORIES_DIR' from 'tests.toy'`.

- [ ] **Step 3: Add the constant**

In `tests/toy.py`, after line 31 (`GAP_DIR = ...`):

```python
# The trajectory run's captured fixture (design spec 2026-08-12). Not a toy
# world and not built by build_toy_run -- it is committed live capture, so it
# sits beside the other fixture dirs for path resolution only.
TRAJECTORIES_DIR = Path(__file__).resolve().parent / "fixtures" / "reservation-trajectories"
```

- [ ] **Step 4: Run it to verify it passes**

```bash
uv run pytest tests/unit/test_trajectory_fixtures.py -q
```

Expected: 8 passed.

- [ ] **Step 5: Write the provenance README**

Create `tests/fixtures/reservation-trajectories/README.md`. Fill every
bracketed value from Task 2's recorded summary — no brackets may remain.

```markdown
# reservation-service trajectory capture

Committed live capture for the trajectory run
(`docs/superpowers/specs/2026-08-12-reservation-service-trajectory-run-design.md`).

Re-capturing draws fresh LLM spans and a fresh `confirmation_code` sequence, so
without this record nobody could later distinguish a pipeline change from a
capture change. Changing the harness obliges re-recording, and that re-record is
a reviewable diff.

## Capture conditions

| | |
|---|---|
| Date | 2026-08-12 |
| Model | `Azure/gpt-4.1` via litellm proxy (`OPENAI_API_BASE`) |
| MLflow | 3.15.1, `sqlite:///` backend, `autolog()` for LangChain |
| Target | `rossoctl/examples` at `dbbc5e0f46cc92c8f642e44d1124965394cf36e5`, clean |
| MCP server | in-process build, `streamable-http` on `127.0.0.1:8765` |
| Agent | `graph.ainvoke` driven directly; A2A layer not used |
| Traces written | [N from summary] |

`MCP_TRANSPORT` is set per-process and never globally: `streamable-http` for
FastMCP, `streamable_http` for langchain-mcp-adapters. One env var, two
incompatible spellings — the hazard the control run flagged as a contradiction.

## Prompt list, verbatim

[Paste the ten (id, text) pairs from PROMPTS.]

`{restaurant_id}` and `{reservation_id}` are filled from an **observed** span
output — the first `search_restaurants` result's `id` and the
`place_reservation` result's `id`. When a needed value was never observed the
prompt is **skipped**, never filled with a plausible guess.

## Outcome per prompt

[Paste the summary's `prompts` array: id, status, tools_called.]

## Single-pass rule

Captured in one pass. No prompt was re-run to obtain a better trace. A prompt
that failed to drive its intended path is recorded as such, and the gap it was
aimed at stays open.
```

- [ ] **Step 6: Re-measure the baseline and update CLAUDE.md**

```bash
make test 2>&1 | tail -2
```

Record the actual counts. In `CLAUDE.md`, replace the `Baseline:` line's numbers
with the measured ones and note the addition, following the existing line's own
convention of naming what changed.

- [ ] **Step 7: Verify and commit**

```bash
make check && uv run rubrica check-skills && echo "check-skills=0"
git add tests/ CLAUDE.md
git commit -S -s -m "test: Guard the trajectory fixture and record its provenance

Two properties would silently invalidate the run if they drifted, and neither
surfaces as a failure anywhere else: the top-level trace_id mirror (without it
classify returns other and the extract member loses its kind hint) and the
opaque outputSchema (the run's premise is that /tools/list says nothing about
outputs). Both are now asserted, along with classify's verdict on each file --
guarding the mirror's purpose rather than merely its presence.

Assertions are structural, so a legitimate re-capture with different LLM
wording stays green.

Assisted-By: Claude (Anthropic AI) <noreply@anthropic.com>"
```

---

## Task 4: Stage the inputs and mint the run

**Files:**
- Create: `/tmp/rubrica-lab/inputs-trajectory-run/` (six staged inputs)
- Create: `/tmp/rubrica-lab/provenance-trajectory-run.md`

**Interfaces:**
- Consumes: both captured artifacts.
- Produces: a run directory path written to `/tmp/rubrica-lab/CURRENT_RUN_TRAJ`,
  used by Tasks 5–6.

- [ ] **Step 1: Stage the six inputs**

```bash
set -e
SRC=/home/bnayahu/work/rossoctl/examples
FIX=/home/bnayahu/work/kaegis/rubrica/tests/fixtures/reservation-trajectories
ST=/tmp/rubrica-lab/inputs-trajectory-run
rm -rf "$ST"; mkdir -p "$ST"

cp "$SRC/a2a/reservation_service/src/reservation_service/graph.py" "$ST/agent-graph.py"
cp "$SRC/a2a/reservation_service/src/reservation_service/agent.py" "$ST/agent-server.py"
cp "$SRC/a2a/reservation_service/README.md"  "$ST/agent-notes.md"
cp "$SRC/mcp/reservation_tool/README.md"     "$ST/mcp-tool-notes.md"
cp "$FIX/tools-list.json"                    "$ST/tools-list.json"
cp "$FIX/trajectories.json"                  "$ST/trajectories.json"
ls -l "$ST"
```

Staging, not direct paths: `source_path` is reachable from a dispatched stage
and the rossoctl tree is in neither `dispatch-stage.sh`'s `permissions.deny` nor
its sandbox `allowRead`, so a stage following it could walk to
`providers/mock.py`. Renaming also avoids both READMEs slugging to
`readme-md` / `readme-md-2`.

- [ ] **Step 2: Confirm the withheld files are absent**

```bash
ST=/tmp/rubrica-lab/inputs-trajectory-run
for bad in reservation_tool.py schemas.py mock.py base.py; do
  if grep -rql "$bad" "$ST" 2>/dev/null; then echo "MENTIONS $bad (ok if only prose)"; fi
  test ! -e "$ST/$bad" || { echo "FAIL: $bad staged"; exit 1; }
done
echo "no withheld file staged"
```

- [ ] **Step 3: Verify classification before spending money**

```bash
cd /home/bnayahu/work/kaegis/rubrica
.venv/bin/python -c "
from pathlib import Path
from rubrica.intake import classify, slug
exp={'agent-graph.py':'source_code','agent-server.py':'source_code',
     'agent-notes.md':'design_doc','mcp-tool-notes.md':'design_doc',
     'tools-list.json':'mcp_tool_schema','trajectories.json':'trace'}
for p in sorted(Path('/tmp/rubrica-lab/inputs-trajectory-run').iterdir()):
    got=classify(p); ok='OK ' if got==exp[p.name] else 'BAD'
    print(f'{ok} {p.name:20} id={slug(p.name):22} kind={got}')
    assert got==exp[p.name], (p.name, got, exp[p.name])
print('all six classify as intended')
"
```

Expected: six `OK` lines. A `BAD` on `trajectories.json` means the top-level
`trace_id` mirror is missing — fix Task 2 before proceeding.

- [ ] **Step 4: Write the provenance note, outside the staging dir**

Create `/tmp/rubrica-lab/provenance-trajectory-run.md` mapping each staged name
to its original path, plus the rossoctl SHA. Outside the staging directory
because it names the wider source tree, which a stage should not be able to walk
into.

- [ ] **Step 5: Mint the run**

```bash
cd /home/bnayahu/work/kaegis/rubrica
RUN=$(.venv/bin/rubrica intake --runs-dir runs \
  --target-name reservation-service --target-interface a2a \
  --max-rounds 2 --max-scenarios 6 \
  $(for f in /tmp/rubrica-lab/inputs-trajectory-run/*; do printf -- '--input %s ' "$f"; done))
RUN=$(cd "$RUN" && pwd); echo "$RUN" > /tmp/rubrica-lab/CURRENT_RUN_TRAJ
echo "RUN=$RUN"
.venv/bin/rubrica validate --run "$RUN" --stage intake; echo "validate=$?"
.venv/bin/rubrica check-refs --run "$RUN"; echo "check-refs=$?"
jq '{run_id,target,limits,inputs:[.inputs[]|{artifact_id,kind,bytes}]}' "$RUN/manifest.json"
```

Expected: both gates `0`, six inputs with the kinds from Step 3.

`--max-scenarios 6` matches the control, so `denominator.capability_cells` is
compared against the same cap.

- [ ] **Step 6: Record the run id in the plan**

No commit — `runs/` is gitignored. Note the run id in your task report so
Task 6's `diff-runs` can name it.

---

## Task 5: The six-slice extract fan-out

**Files:** none created; writes `01-claims/*.json` inside the run.

**Interfaces:**
- Consumes: `/tmp/rubrica-lab/CURRENT_RUN_TRAJ`.
- Produces: six claims files, one per `artifact_id`.

- [ ] **Step 1: Dispatch all six, each with its own lab**

```bash
cd /home/bnayahu/work/kaegis/rubrica
RUN=$(cat /tmp/rubrica-lab/CURRENT_RUN_TRAJ)
for s in agent-graph-py agent-server-py agent-notes-md mcp-tool-notes-md \
         tools-list-json trajectories-json; do
  RUBRICA_LAB=/tmp/rubrica-lab/t-$s \
    ./scripts/dispatch-stage.sh extract "$RUN" "$s" \
    > /tmp/rubrica-lab/log-t-$s.txt 2>&1 &
done
wait
```

A separate `RUBRICA_LAB` per slice is required, not tidiness: the script writes
`$CLAUDE_CONFIG_DIR/settings.json` on every invocation, and six processes
truncating-then-writing one shared path race. Contents are identical, but the
window between truncate and write is real. Per-slice labs also mean the six
share strictly less than six sequential runs would.

Confirm the slice ids against `jq -r '.inputs[].artifact_id' "$RUN/manifest.json"`
before running; `slug()` derives them and a mismatch exits 2.

- [ ] **Step 2: Gates**

```bash
RUN=$(cat /tmp/rubrica-lab/CURRENT_RUN_TRAJ)
.venv/bin/rubrica validate --run "$RUN" --stage extract; echo "validate=$?"
.venv/bin/rubrica check-refs --run "$RUN"; echo "check-refs=$?"
ls -l "$RUN/01-claims/"
```

Expected: both `0`, six files. A `1` is a repairable stage defect worth one
retry; a `2` means retrying cannot help.

- [ ] **Step 3: Read audits — the only instrument for the isolation rule**

```bash
for s in agent-graph-py agent-server-py agent-notes-md mcp-tool-notes-md \
         tools-list-json trajectories-json; do
  echo "##### $s"
  ./scripts/audit-reads.sh /tmp/rubrica-lab/t-$s/transcripts/extract-$s.jsonl
done
```

`rb-extract`'s contract is `reads = ["manifest", "input_file"]`. Each member
should show only `manifest.json`, its own `00-inputs/` file, and its own
`SKILL.md`. **Any other `00-inputs/*` file is an Important isolation finding**,
not a nit — a member that read a sibling writes a byte-identical artifact to one
that did not, so nothing on disk shows it.

Also grep each transcript for `tests/`, `docs/`, `CLAUDE.md`, `fixtures` — the
answer-key surface — and for `providers/` and `mock.py`, which for this run are
the withheld implementation.

- [ ] **Step 4: Record the stage and tally**

```bash
RUN=$(cat /tmp/rubrica-lab/CURRENT_RUN_TRAJ)
.venv/bin/rubrica record-stage --run "$RUN" --stage extract \
  --model claude-sonnet-5 --effort medium \
  --skill src/rubrica/skills/rb-extract/SKILL.md
for f in "$RUN"/01-claims/*.json; do
  echo "$(basename "$f"): $(jq -r '.claims|length' "$f") claims  \
$(jq -r '.claims|group_by(.kind)|map("\(.[0].kind):\(length)")|join(" ")' "$f")"
done
```

One manifest entry covers the stage, not one per slice. Confirm the model id
from a transcript (`jq -r 'select(.type=="assistant")|.message.model'`) rather
than assuming.

- [ ] **Step 5: Report, no commit**

Report per-slice cost, claim counts, kind tallies, and every audit line. Pay
attention to whether `trajectories-json` produced `entity` claims with field
sets — that is prediction P6, and the one most likely to fail.

---

## Task 6: Reconcile, gate 1, and the prediction checks

**Files:** none created; writes `01-world-model.json` inside the run.

**Interfaces:**
- Consumes: six claims files.
- Produces: the world model, plus a written verdict on P1–P6.

- [ ] **Step 1: Dispatch reconcile — a barrier, no slice id**

```bash
cd /home/bnayahu/work/kaegis/rubrica
RUN=$(cat /tmp/rubrica-lab/CURRENT_RUN_TRAJ)
RUBRICA_LAB=/tmp/rubrica-lab/t-reconcile \
  ./scripts/dispatch-stage.sh reconcile "$RUN" \
  > /tmp/rubrica-lab/log-t-reconcile.txt 2>&1
```

Budget above the control's $1.49: this barriers over six claims files, not five.

- [ ] **Step 2: Gates and audit**

```bash
RUN=$(cat /tmp/rubrica-lab/CURRENT_RUN_TRAJ)
.venv/bin/rubrica validate --run "$RUN" --stage reconcile; echo "validate=$?"
.venv/bin/rubrica check-refs --run "$RUN"; echo "check-refs=$?"
./scripts/audit-reads.sh /tmp/rubrica-lab/t-reconcile/transcripts/reconcile.jsonl
.venv/bin/rubrica record-stage --run "$RUN" --stage reconcile \
  --model claude-sonnet-5 --effort medium \
  --skill src/rubrica/skills/rb-reconcile/SKILL.md
```

`reads = ["manifest", "claims_dir"]`. The control's reconcile also read
`src/rubrica/schema/world-model-0.1.json` and ran `find /`; note whether that
recurs. Reading the schema is arguably inside `schemas = ["world-model"]` and
outside `reads`, which `reads`'s vocabulary (`RunPaths` attribute names) cannot
express — report it as a contract-vocabulary observation, not a violation.

- [ ] **Step 3: Shape, and the six predictions**

```bash
RUN=$(cat /tmp/rubrica-lab/CURRENT_RUN_TRAJ)
W="$RUN/01-world-model.json"
jq '{target,denominator,capabilities:(.capabilities|length),
     entities:(.entities|length),actors:(.actors|length),goals:(.goals|length),
     contradictions:(.contradictions|length),gaps:(.gaps|length)}' "$W"
echo "--- P3/P4: what did it conclude about ids and refunds? ---"
grep -o "res_12345\|reservation_[a-f0-9]\{6,\}\|reservation_abc123" "$W" | sort | uniq -c
jq -r '.. | .statement? // empty | select(test("refund";"i"))' "$W"
echo "--- P5: capability params ---"
jq -r '.capabilities[] | "\(.name // .id): \([.params[]?.name] | join(", "))"' "$W"
echo "--- P6: entity fields ---"
jq -r '.entities[] | "\(.name): \([.fields[].name] | join(", "))"' "$W"
echo "--- gaps ---"
jq -r '.gaps[] | "- \(.id): \(.subject) [blocks \(.blocks|join(","))]"' "$W"
echo "--- contradictions ---"
jq -r '.contradictions[] | "- \(.id): \(.resolution) -- \(.nature)"' "$W"
```

- [ ] **Step 4: Score the predictions in writing**

For each, record **met / not met / partial** with the evidence:

| | Prediction |
|---|---|
| P1 | Four of the control's five gaps closed. |
| P2 | `gap-check-availability-empty` did **not** close. |
| P3 | `reservation_id` characterised as `reservation_<hex>`; the README vs `tools-list` disagreement surfaced as a contradiction. |
| P4 | `refund_policy` from the observed string, not `schemas.py`'s default. |
| P5 | Five capabilities with correct required/optional params, from `tools-list.json`. |
| P6 | At least one entity reconstructed with fields derived from observed spans. |

A missed prediction is a result. Do not adjust the prediction to match the
outcome, and do not register `providers/mock.py` to close a surviving gap —
spec §12: it would improve the suite and destroy the measurement.

- [ ] **Step 5: Diff against the control**

```bash
cd /home/bnayahu/work/kaegis/rubrica
.venv/bin/rubrica diff-runs --a runs/run-20260812-074017 \
  --b "$(cat /tmp/rubrica-lab/CURRENT_RUN_TRAJ)" | jq .
```

Expect `comparable: false` with reasons — the input sets differ by construction.
`diff-runs` reports the stage diffs anyway, by design. Compare
`1b_capabilities` and `denominator.capability_cells` against the control's
five and **16**.

- [ ] **Step 6: Hold gate 1 and report**

Human gate 1. Report the shape table, the P1–P6 scoring, the `diff-runs` output,
every read-audit line, and total measured cost. Then stop and ask before
`propose` — gates 1, 2 and 3 are human by design and this is the first.

---

## Self-Review

**Spec coverage.** §1 → Tasks 4–6. §2 control framing → Task 6 Step 5. §3
boundary premise → Task 1 Step 4 plus the guard test. §4 inputs and staging →
Task 4 Steps 1–5. §5 harness → Tasks 1–2. §6 prompts and single-pass → Task 2
Steps 1, 3. §7 mirror and the three MLflow behaviours → Task 2 Step 2, guarded
in Task 3. §8 predictions → Task 6 Step 4. §9 `diff-runs` → Task 6 Step 5. §10
provenance → Task 3 Steps 5, 7. §11 failure modes → Task 2 Step 3's
single-pass rule and the per-process transport constants. §12 not-in-scope →
Global Constraints and Task 6 Step 4. No gap.

**Placeholders.** The only bracketed values are in Task 3 Step 5's README
template, where the step says explicitly to fill them from Task 2's recorded
summary and that no brackets may remain. Everything else is literal.

**Type consistency.** `capture_tools_list(out_path: Path) -> int` and
`capture_trajectories(out_path: Path) -> dict` are defined in Tasks 1–2 and
called only from `main()`. `start_server() -> subprocess.Popen`,
`tool_outputs(result: dict) -> list[tuple[str, str]]`, and
`substitute(text: str, observed: dict[str, str]) -> str | None` are each defined
once and used with those signatures. `TRAJECTORIES_DIR` is added in Task 3
Step 3 and imported in Step 1's test under that exact name. Constants
`SERVER_TRANSPORT`, `CLIENT_TRANSPORT`, `SERVER_HOST`, `SERVER_PORT`, `MODEL`,
`TOOL_DIR`, `AGENT_SRC`, `PROMPTS` are defined in Tasks 1–2 and referenced
consistently.
