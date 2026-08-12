"""Minimal example: evaluate one synthetic stock and print the signal JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cpr_scanner import ScannerConfig, evaluate_stock, run_scanner
from tests.conftest import make_compressed_then_breakout, make_ohlcv


def main() -> None:
    stock = make_compressed_then_breakout(seed=7)
    index = make_ohlcv(n=len(stock), seed=99, trend=0.0005)
    index.index = stock.index

    signal = evaluate_stock(
        daily_df=stock,
        weekly_df=None,
        index_daily_df=index,
        symbol="SYNTH",
        stock_is_fno_eligible=True,
        config=ScannerConfig(),
    )
    print(json.dumps(signal, indent=2, default=str))

    report = run_scanner(
        [{"symbol": "SYNTH", "daily_df": stock, "stock_is_fno_eligible": True}],
        index_daily_df=index,
    )
    print("scanner_mode:", report["scanner_mode"])
    print("top score:", report["results"][0]["score"] if report["results"] else None)


if __name__ == "__main__":
    main()
