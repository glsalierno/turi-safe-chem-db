"""
CLI entry point for auto_p2oasys.

Usage:
    python -m packages.auto_p2oasys --cas 67-64-1 [--fast] [--sds file.pdf] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Run auto_p2oasys CLI."""
    parser = argparse.ArgumentParser(
        prog="python -m packages.auto_p2oasys",
        description="Automatic P2OASys hazard scoring with expert-first routing.",
    )
    parser.add_argument(
        "--cas",
        type=str,
        help="CAS registry number (e.g., 67-64-1)",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Force fast pipeline even if expert score exists",
    )
    parser.add_argument(
        "--sds",
        type=Path,
        help="Path to SDS PDF file",
    )
    parser.add_argument(
        "--json",
        type=Path,
        dest="json_output",
        help="Write JSON result to file",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress source report output",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version and exit",
    )

    args = parser.parse_args(argv)

    if args.version:
        from . import __version__

        print(f"auto_p2oasys {__version__}")
        return 0

    if not args.cas and not args.sds:
        parser.error("Either --cas or --sds must be provided")

    from . import auto_p2oasys

    result = auto_p2oasys(
        cas=args.cas,
        sds_pdf=args.sds,
        force_fast=args.fast,
    )

    if not args.quiet:
        print(result.source_report.print_summary())
        print()

    print(result.print_summary())

    if args.json_output:
        with open(args.json_output, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, default=str)
        print(f"\nJSON written to: {args.json_output}")

    if result.error:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
