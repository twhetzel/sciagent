#!/usr/bin/env python3
"""Run golden-query dataset discovery evaluation (developer harness)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))


def _require_project_dependencies() -> None:
    try:
        import dotenv  # noqa: F401
    except ModuleNotFoundError:
        print(
            "Missing project dependencies. Use the project virtualenv:\n"
            "  cd server && uv run python scripts/run_golden_queries.py\n"
            "Or from the repo root:\n"
            "  ./scripts/run_golden_queries.sh",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


_require_project_dependencies()

from evaluation.golden_queries import (  # noqa: E402
    DEFAULT_GOLDEN_MAX_RESULTS,
    DEFAULT_QUERY_PAUSE_SEC,
    GOLDEN_QUERIES,
    evaluate_all_golden_queries,
    evaluate_golden_query,
    format_report_text,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run golden-query dataset discovery evaluation against enabled sources.",
    )
    parser.add_argument(
        "--query",
        action="append",
        dest="queries",
        help="Run a single query instead of the default golden set (repeatable).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON reports instead of human-readable summaries.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=None,
        help=(
            "Override repository max-results limit for this run "
            f"(default: {DEFAULT_GOLDEN_MAX_RESULTS} for evaluation, not GEO_MAX_RESULTS)."
        ),
    )
    parser.add_argument(
        "--pause-between-queries",
        type=float,
        default=DEFAULT_QUERY_PAUSE_SEC,
        help="Seconds to wait between queries to reduce NCBI rate limiting (default: 2).",
    )
    args = parser.parse_args()

    queries = tuple(args.queries) if args.queries else GOLDEN_QUERIES
    reports = evaluate_all_golden_queries(
        queries,
        max_results=args.max_results,
        pause_between_queries_sec=args.pause_between_queries,
    )

    if args.json:
        print(json.dumps(reports, indent=2, sort_keys=True))
    else:
        for index, report in enumerate(reports):
            if index:
                print("\n" + ("-" * 72) + "\n")
            print(format_report_text(report))

    failed = [
        report
        for report in reports
        if report.get("error")
        or not report.get("context_export_ok", False)
        or not report.get("assay_ranking_ok", True)
    ]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
