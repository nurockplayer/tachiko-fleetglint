"""Command-line entry point. Each subcommand's work lives in its own module (docs/architecture.md §8)."""
import argparse
import importlib
import sys

from fleetglint import RECORD_FORMAT_VERSION, __version__

# subcommand -> module whose run(args) -> int implements it; a module serving several
# subcommands (ingest: ingest, status, source, rebuild) dispatches on args.command
COMMANDS = {
    "serve": "fleetglint.server",
    "ingest": "fleetglint.ingest",
    "check": "fleetglint.schema",
    "emit": "fleetglint.emit",
    "status": "fleetglint.ingest",
    "source": "fleetglint.ingest",
    "rebuild": "fleetglint.ingest",
}


def build_parser():
    parser = argparse.ArgumentParser(prog="fleetglint", description="Local, read-only board for multi-agent workflows.")
    parser.add_argument("--config", help="config file (default $XDG_CONFIG_HOME/fleetglint/config.toml)")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p = sub.add_parser("serve", help="run the ingest thread and the HTTP server on 127.0.0.1")
    p.add_argument("--port", type=int)
    p.add_argument("--open", action="store_true", help="open the board in the default browser")

    p = sub.add_parser("ingest", help="run the ingest loop without the server")
    p.add_argument("--once", action="store_true", help="one pass, then exit")

    p = sub.add_parser("check", help="validate NDJSON files (or stdin)")
    p.add_argument("files", nargs="*")

    p = sub.add_parser("emit", help="validate one full record from stdin and append it")
    p.add_argument("--source-id")
    p.add_argument("--root", help="sources root (default: the first configured root)")

    sub.add_parser("status", help="sources, quarantine counts, database path")

    p = sub.add_parser("source", help="source maintenance")
    source_sub = p.add_subparsers(dest="source_command", metavar="ACTION", required=True)
    r = source_sub.add_parser("reset", help="acknowledge a discontinuity and rebuild that source")
    r.add_argument("source_id")

    sub.add_parser("rebuild", help="delete and rebuild the database from retained segments and adapters")
    sub.add_parser("version", help="print versions and paths")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    if args.command == "version":
        print(f"fleetglint {__version__} (record format v{RECORD_FORMAT_VERSION})")
        return 0
    module = importlib.import_module(COMMANDS[args.command])
    handler = getattr(module, "run", None)
    if handler is None:
        print(f"fleetglint {args.command}: not implemented yet", file=sys.stderr)
        return 3
    return handler(args)
