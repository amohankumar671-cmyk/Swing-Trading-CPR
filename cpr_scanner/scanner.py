"""Full-universe scanner loop over NSE F&O stocks."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Literal

import pandas as pd

from cpr_scanner.config import ScannerConfig
from cpr_scanner.cpr import add_cpr, classify_cpr_width, is_narrow_classification, resample_daily_to_weekly
from cpr_scanner.evaluate import evaluate_stock

Direction = Literal["BUY", "SELL"]

# Optional default F&O universe stub — replace with live NSE F&O list in production
DEFAULT_FNO_SYMBOLS: list[str] = []


def market_regime(
    index_daily_df: pd.DataFrame,
    index_weekly_df: pd.DataFrame | None = None,
    config: ScannerConfig | None = None,
) -> dict[str, Any]:
    """
    Market regime pre-filter from benchmark weekly CPR.

    if index_cpr_narrow:
        scanner_mode = "high_priority"  # broad compression
    else:
        scanner_mode = "normal"
    """
    cfg = config or ScannerConfig()
    weekly = index_weekly_df if index_weekly_df is not None and len(index_weekly_df) else None
    if weekly is None:
        weekly = resample_daily_to_weekly(index_daily_df)
    weekly = add_cpr(weekly)
    class_df = classify_cpr_width(weekly["cpr_width_pct"], cfg)
    latest = class_df.iloc[-1]
    classification = latest["cpr_classification"]
    index_cpr_narrow = is_narrow_classification(classification)
    return {
        "index_cpr_narrow": index_cpr_narrow,
        "index_cpr_classification": classification,
        "index_cpr_percentile": float(latest["cpr_percentile"])
        if pd.notna(latest["cpr_percentile"])
        else None,
        "index_cpr_width_pct": float(latest["cpr_width_pct"])
        if pd.notna(latest["cpr_width_pct"])
        else None,
        "scanner_mode": "high_priority" if index_cpr_narrow else "normal",
    }


def run_scanner(
    universe: Iterable[dict[str, Any]] | Iterable[str],
    *,
    index_daily_df: pd.DataFrame,
    index_weekly_df: pd.DataFrame | None = None,
    load_stock: Callable[[str], tuple[pd.DataFrame, pd.DataFrame | None]] | None = None,
    direction: Direction | None = None,
    config: ScannerConfig | None = None,
    min_score: float = 0.0,
) -> dict[str, Any]:
    """
    Loop evaluate_stock over the F&O universe.

    `universe` items may be:
      - symbol strings (requires load_stock callback), or
      - dicts with keys: symbol, daily_df, weekly_df?, stock_is_fno_eligible?

    Returns
    -------
    {
      "scanner_mode": "high_priority" | "normal",
      "index_cpr_narrow": bool,
      "results": [ ... ranked SignalOutput ... ],
    }
    """
    cfg = config or ScannerConfig()
    regime = market_regime(index_daily_df, index_weekly_df, cfg)

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for item in universe:
        try:
            if isinstance(item, str):
                if load_stock is None:
                    raise ValueError("load_stock callback required when universe is symbol strings")
                symbol = item
                daily_df, weekly_df = load_stock(symbol)
                fno = True
            else:
                symbol = item["symbol"]
                daily_df = item["daily_df"]
                weekly_df = item.get("weekly_df")
                fno = bool(item.get("stock_is_fno_eligible", True))

            signal = evaluate_stock(
                daily_df=daily_df,
                weekly_df=weekly_df,
                index_daily_df=index_daily_df,
                index_weekly_df=index_weekly_df,
                direction=direction,
                symbol=symbol,
                stock_is_fno_eligible=fno,
                config=cfg,
            )
            if signal["score"] >= min_score:
                results.append(signal)
        except Exception as exc:  # noqa: BLE001 — collect per-symbol failures
            sym = item if isinstance(item, str) else item.get("symbol", "?")
            errors.append({"symbol": str(sym), "error": str(exc)})

    results.sort(key=lambda r: r.get("score", 0), reverse=True)

    return {
        "scanner_mode": regime["scanner_mode"],
        "index_cpr_narrow": regime["index_cpr_narrow"],
        "index_cpr_classification": regime["index_cpr_classification"],
        "index_cpr_percentile": regime["index_cpr_percentile"],
        "results": results,
        "errors": errors,
        "scanned": len(results) + len(errors),
    }
