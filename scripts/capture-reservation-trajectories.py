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

# These two paths point into a checkout of the target this fixture was captured
# against. They are environment-overridable rather than hard-coded because the
# fixture README used to instruct re-runners to edit this source file by hand,
# which is a worse contract than a variable: editing source to run a script makes
# the edit indistinguishable from a change to the script. The defaults are the
# paths the 2026-08-12 capture actually used, kept verbatim so that record stays
# reproducible for whoever still has that checkout. Measured 2026-09-09: that
# directory is still present on the capture machine and both defaults still
# resolve there, but it is no longer a git checkout (`git rev-parse HEAD` reports
# "not a git repository"), so the commit sha the fixture README's capture
# conditions record can no longer be verified against it. Anyone re-running this
# anywhere else must set both.
TOOL_DIR = Path(
    os.environ.get(
        "RUBRICA_ROSSOCTL_TOOL_DIR",
        "/home/bnayahu/work/rossoctl/examples/mcp/reservation_tool",
    )
)
AGENT_SRC = Path(
    os.environ.get(
        "RUBRICA_ROSSOCTL_AGENT_SRC",
        "/home/bnayahu/work/rossoctl/examples/a2a/reservation_service/src",
    )
)
MODEL = "Azure/gpt-4.1"


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
    doc = {"tools": [json.loads(t.to_mcp_tool().model_dump_json(exclude_none=True)) for t in tools]}
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


# p01-p10 are the original list: five happy paths, five aimed at the output
# questions the control run could not answer. Prompts 7 and 8 name an
# obviously-invalid id explicitly, because a model told only "a restaurant that
# does not exist" will search first and never drive the error path. p11 onwards
# were added later, each closing a gap a pipeline run recorded -- see the block
# above them.
#
# {restaurant_id} and {reservation_id} are filled from an OBSERVED span output,
# never authored -- see substitute() below.
PROMPTS: list[tuple[str, str]] = [
    ("p01-search", "Find Italian restaurants in Boston"),
    (
        "p02-search-then-check",
        "Find Italian restaurants in Boston, then check availability at the first "
        "one for 4 people on 2025-03-15 at 7:00 PM",
    ),
    (
        "p03-place",
        "Book a table at restaurant {restaurant_id} for 2025-03-15T19:00:00, party "
        "of 4. Name: Jane Smith, Phone: +1-555-987-6543, Email: jane@example.com",
    ),
    ("p04-list", "List all reservations for jane@example.com"),
    ("p05-cancel", "Cancel reservation {reservation_id} because plans changed"),
    ("p06-search-empty", "Find Ethiopian restaurants in Fargo"),
    (
        "p07-check-unknown",
        "Check availability at restaurant rest_999 for 2 people on 2025-03-15 at 8:00 PM",
    ),
    (
        "p08-place-unknown",
        "Book a table at restaurant rest_999 for 2025-03-15T20:00:00, party of 2. "
        "Name: Test User, Phone: +1-555-000-0000, Email: test@example.com",
    ),
    ("p09-list-empty", "List all reservations for nobody@example.com"),
    ("p10-cancel-unknown", "Cancel reservation reservation_deadbeef1234 because it does not exist"),
    # p11 onwards were added on 2026-08-16 to close gaps a full pipeline run
    # recorded against the p01-p10 capture. Each one exists because
    # 01-world-model.json named an input that would close a specific gap, and
    # every one of those asks was for a trace. They are appended rather than
    # interleaved so p01-p10 keep the ids and the order the committed
    # trajectories.json was captured under.
    #
    # p11 is the one that unblocked the run. p05-cancel cancels jane's
    # reservation and nothing in the original ten ever listed afterwards, so
    # whether cancelling deletes the record or flags it was unknowable from the
    # capture -- and every place-then-cancel-then-list scenario had two possible
    # gold answers. Listing the same guest after p05 settles it by observation.
    # It reads {reservation_id} indirectly: p05 must have run for this to mean
    # anything, and p05 skips itself if place_reservation was never observed.
    ("p11-list-after-cancel", "List all reservations for jane@example.com"),
    (
        "p12-check-over-capacity",
        "Check availability at restaurant {restaurant_id} for 30 people on 2025-03-15 at 7:00 PM",
    ),
    ("p13-list-by-phone", "List all reservations for +1-555-987-6543"),
    (
        "p14-check-bad-datetime",
        "Check availability at restaurant {restaurant_id} for 4 people on the 45th of "
        "Foguary at 25:00",
    ),
    ("p15-search-bad-price-tier", "Find restaurants in Boston with price tier 9"),
    (
        "p16-place-over-capacity",
        "Book a table at restaurant {restaurant_id} for 2025-03-15T19:00:00, party of 40. "
        "Name: Overflow Test, Phone: +1-555-000-0002, Email: overflow@example.com",
    ),
    (
        "p17-search-city-catalogue",
        "List every restaurant you know about in Boston, with cuisine and price tier for each",
    ),
]


def _content_text(content) -> str:
    """A ToolMessage's content as text, whichever shape LangChain used.

    Measured on the first live capture: content arrives either as a plain str or
    as a list of content blocks. Dropping the list shape lost a real
    observation -- search_restaurants had returned rest_001, the id-extraction
    heuristic never saw it, and two dependent prompts cascaded to
    `skipped-unobserved`. Joining the text blocks is what makes an observation
    the harness already captured readable.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content)


def tool_outputs(result: dict) -> list[tuple[str, str]]:
    """(tool_name, raw content) for every ToolMessage in a graph result.

    Matched on class name rather than isinstance to avoid importing
    langchain_core.messages at module scope, which would make the tools-list
    subcommand require the agent's dependency set for no reason.
    """
    out = []
    for m in result.get("messages", []):
        if type(m).__name__ == "ToolMessage":
            out.append((getattr(m, "name", ""), _content_text(m.content)))
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
                summary["prompts"].append({"id": pid, "status": "error", "detail": str(exc)[:300]})
                continue

            calls = tool_outputs(result)
            for name, content in calls:
                try:
                    payload = json.loads(content)
                # TypeError alongside JSONDecodeError: content is text by the time it
                # reaches here (_content_text normalises the list-of-blocks shape), but
                # json.loads still raises TypeError rather than JSONDecodeError for a
                # small set of non-str/bytes inputs, so both are caught defensively. This
                # is a guard for genuinely non-JSON content, not the list-content case --
                # that observation is no longer discarded here.
                except (json.JSONDecodeError, TypeError):
                    continue
                if name == "search_restaurants" and isinstance(payload, list) and payload:
                    observed.setdefault("restaurant_id", payload[0].get("id", ""))
                if name == "place_reservation" and isinstance(payload, dict) and payload.get("id"):
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
        proc = start_server()
        try:
            summary = capture_trajectories(Path(args.out))
        finally:
            proc.terminate()
            proc.wait(timeout=10)
        print(json.dumps(summary, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
