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
