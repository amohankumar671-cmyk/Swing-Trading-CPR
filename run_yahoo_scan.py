"""Scan a free NSE sample universe using Yahoo Finance OHLCV (no broker API)."""

from __future__ import annotations

import argparse
import json

from data import DEFAULT_FNO_SYMBOLS, load_universe
from scanner import run_scanner


def main() -> None:
    parser = argparse.ArgumentParser(description="CPR swing scanner via Yahoo Finance")
    parser.add_argument(
        "--symbols",
        nargs="*",
        default=DEFAULT_FNO_SYMBOLS[:5],
        help="NSE symbols without .NS (default: small sample)",
    )
    parser.add_argument("--period", default="2y", help="Yahoo history period (default 2y)")
    parser.add_argument("--min-score", type=float, default=50.0, help="Min score to print")
    parser.add_argument("--json", action="store_true", help="Print full JSON report")
    args = parser.parse_args()

    print(f"Downloading {len(args.symbols)} symbols + Nifty from Yahoo Finance...")
    universe, index_df = load_universe(args.symbols, period=args.period)
    if not universe:
        raise SystemExit("No symbols downloaded. Check network / symbol names.")

    report = run_scanner(universe, index_daily_df=index_df, min_score=0.0)

    print(f"scanner_mode: {report['scanner_mode']}")
    print(f"index_cpr_narrow: {report['index_cpr_narrow']}")
    print(f"scanned: {report['scanned']}")
    print("-" * 72)
    print(f"{'SYMBOL':<12} {'DIR':<6} {'SCORE':>6} {'CLASS':<16} {'ENTRY':<22} {'RS':>7}")
    print("-" * 72)

    shown = 0
    for row in report["results"]:
        if row["score"] < args.min_score:
            continue
        print(
            f"{row['symbol']:<12} {row['direction']:<6} {row['score']:>6.1f} "
            f"{row['classification']:<16} {str(row['entry_status']):<22} "
            f"{(row['relative_strength'] or 0):>7.2f}"
        )
        shown += 1

    if shown == 0:
        print("(no rows above min-score; try --min-score 0)")

    if args.json:
        # Drop heavy frames; results are already plain dicts
        print(json.dumps({"scanner_mode": report["scanner_mode"], "results": report["results"]}, indent=2))


if __name__ == "__main__":
    main()
