"""Command-line interface. All inputs and outputs stay on the local filesystem."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from . import __version__
from .core import DEFAULT_START, ORDERS, create_scenario, load_events, verify_scenario, write_scenario


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build deterministic, local webhook delivery fixtures.")
    parser.add_argument("--version", action="version", version=f"hookfixture {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Write a new fixture directory from a JSON event array")
    build.add_argument("input", help="JSON array containing type and data for each logical event")
    build.add_argument("--out", required=True, help="New output directory; its parent must exist")
    build.add_argument("--copies", type=int, default=1, help="Total deliveries per logical event (1–100)")
    build.add_argument("--order", choices=ORDERS, default="original")
    build.add_argument("--seed", type=int, default=0, help="Seed for reproducible shuffling")
    build.add_argument("--start", default=DEFAULT_START, help="Timezone-aware start for generated timestamps")
    verify = commands.add_parser("verify", help="Validate a manifest and all referenced fixtures")
    verify.add_argument("manifest")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            scenario = create_scenario(load_events(args.input), copies=args.copies, order=args.order, seed=args.seed, start=args.start)
            manifest = write_scenario(scenario, args.out)
            summary = verify_scenario(manifest)
            result = {"manifest": str(manifest), **asdict(summary)}
        else:
            result = {"valid": True, **asdict(verify_scenario(args.manifest))}
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        print(f"hookfixture: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
