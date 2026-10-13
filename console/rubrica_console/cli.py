"""`rubrica-console`: open the browser console over a folder of runs.

The console lives outside the `rubrica` package on purpose: the core is the
pipeline -- schemas, checks, seals, emit -- and the console is an operator's tool
built on top of it. It drives the pipeline only through the `rubrica` CLI and
`scripts/dispatch-stage.sh`, as subprocesses, so nothing in the core imports it or
knows it exists, and removing this folder removes the console and nothing else.

Exit codes follow the core CLI's contract as far as they apply: `0` when the server
is interrupted, `2` for a runs folder or run that does not exist, a port that cannot
be bound, or a bad argument. There is no `1`: the console checks nothing itself, and
the work it starts reports through its own subprocesses' exit codes, in the page.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from rubrica.paths import RunPaths
from rubrica.validate import manifest_stage_efforts
from rubrica_console import credentials, jobs, server

CLEAN, USAGE = 0, 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rubrica-console",
        description="Open the browser console: start runs, run stages, hold gates, read reports.",
    )
    # One of the two: a folder of runs, or one run (whose parent becomes that folder).
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--runs-dir", default=None)
    where.add_argument("--run", default=None)
    # Loopback by default: the console can start model dispatches, which spend
    # money, and every run holds the target's corpus copies in 00-inputs/.
    # --host 0.0.0.0 is a choice an operator should have to type.
    parser.add_argument("--host", default=server.DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=server.DEFAULT_PORT)
    parser.add_argument(
        "--root", default=None, help="where the file picker may browse (default: home)"
    )
    parser.add_argument(
        "--lab",
        default=None,
        help="the console's own job records and logs, outside every run "
        "(default: $RUBRICA_LAB, else <runs-dir>/../lab)",
    )
    # Three is rb-orchestrate's measured cap for the shared gateway (B3, B6.2).
    parser.add_argument("--max-parallel", type=int, default=3)
    parser.add_argument("--model", default=None, help="default model (default: $RUBRICA_MODEL)")
    parser.add_argument("--effort", default="medium", choices=manifest_stage_efforts())
    # A flag rather than an environment variable, so the env overrides CLAUDE.md
    # lists stay the whole set the package reads. Tests point it at a fake.
    parser.add_argument("--dispatch-script", default=None)
    # The console's own model credentials, set from its Settings page. A file
    # rather than the environment: a dispatch must not depend on which shell the
    # server happened to be started from.
    parser.add_argument(
        "--credentials",
        default=None,
        help="the console's model credentials file "
        "(default: ~/.config/rubrica/console-credentials.json)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        # argparse exits 0 for --help and 2 for a usage error; keep both, and
        # always return an int rather than letting SystemExit escape a caller.
        return CLEAN if exc.code == 0 else USAGE
    try:
        if args.run:
            opened = Path(args.run).resolve()
            if not opened.is_dir():
                raise FileNotFoundError(f"run directory does not exist: {opened}")
            RunPaths(opened)
            runs_dir = opened.parent
        else:
            opened = None
            runs_dir = Path(args.runs_dir).resolve()
            if not runs_dir.is_dir():
                raise FileNotFoundError(f"runs directory does not exist: {runs_dir}")
        if args.max_parallel < 1:
            raise ValueError("--max-parallel must be at least 1")
        lab = Path(args.lab or os.environ.get("RUBRICA_LAB") or runs_dir.parent / "lab")
        console = jobs.Console(
            runs_dir,
            lab,
            dispatch_script=Path(args.dispatch_script) if args.dispatch_script else None,
            max_parallel=args.max_parallel,
            model=args.model or os.environ.get("RUBRICA_MODEL") or "sonnet",
            effort=args.effort,
            credentials=credentials.Store(Path(args.credentials) if args.credentials else None),
        )
        httpd = server.make_server(
            console,
            args.host,
            args.port,
            root=Path(args.root).expanduser() if args.root else None,
        )
    except (OSError, ValueError) as exc:
        # A folder that is not there, a port already taken, a bad number: the
        # operator's to fix, and nothing a retry could change.
        print(f"error: {exc}", file=sys.stderr)
        return USAGE
    url = server.url_of(httpd)
    if opened is not None:
        url += f"#/run/{opened.name}"
    # The URL on stdout, flushed, so a wrapper script can read it before the
    # server blocks.
    print(url, flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        console.shutdown()
        httpd.server_close()
    return CLEAN


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
