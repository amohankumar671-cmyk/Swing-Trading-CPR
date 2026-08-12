"""Free market-data helpers using Yahoo Finance (yfinance).

No broker API or paid subscription required. Suitable for research / scanner
prototyping. Not for live order routing.

NSE equity symbols use the `.NS` suffix (e.g. RELIANCE.NS).
Nifty 50 index: ^NSEI
"""

from __future__ import annotations

from typing import Iterable

import pandas as pd

try:
    import yfinance as yf
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "yfinance is required for Yahoo Finance data. Install with: pip install yfinance"
    ) from exc


NIFTY50 = "^NSEI"

# Small free starter universe (NSE F&O names). Expand as needed.
DEFAULT_FNO_SYMBOLS: list[str] = [
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "ITC",
    "BHARTIARTL",
    "LT",
    "KOTAKBANK",
]


def to_yahoo_symbol(symbol: str, exchange: str = "NS") -> str:
    """Convert plain NSE ticker to Yahoo symbol. Pass-through for ^INDEX and already-suffixed."""
    s = symbol.strip().upper()
    if s.startswith("^") or "." in s:
        return s
    return f"{s}.{exchange}"


def _flatten_ohlcv(df: pd.DataFrame, yahoo_symbol: str) -> pd.DataFrame:
    """Normalize yfinance single/multi-ticker download to open/high/low/close/volume."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        # Prefer columns for this ticker when present
        level0 = out.columns.get_level_values(0)
        level1 = out.columns.get_level_values(1)
        if yahoo_symbol in set(level1):
            out = out.xs(yahoo_symbol, axis=1, level=1)
        elif len(set(level1)) == 1:
            out = out.droplevel(1, axis=1)
        else:
            # yfinance sometimes orders as (Price, Ticker)
            try:
                out = out.xs(yahoo_symbol, axis=1, level=-1)
            except KeyError:
                out.columns = level0

    out.columns = [str(c).strip().lower() for c in out.columns]
    rename = {
        "adj close": "close",
        "adj_close": "close",
    }
    out = out.rename(columns=rename)

    needed = ["open", "high", "low", "close", "volume"]
    missing = [c for c in needed if c not in out.columns]
    if missing:
        raise ValueError(f"Yahoo data missing columns {missing} for {yahoo_symbol}")

    out = out[needed].dropna(subset=["open", "high", "low", "close"])
    out.index = pd.to_datetime(out.index)
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_localize(None)
    out = out.sort_index()
    return out


def fetch_ohlcv(
    symbol: str,
    *,
    period: str = "2y",
    interval: str = "1d",
    exchange: str = "NS",
) -> pd.DataFrame:
    """
    Download daily (or other) OHLCV from Yahoo Finance.

    Parameters
    ----------
    symbol : plain ticker ("RELIANCE") or Yahoo form ("RELIANCE.NS", "^NSEI")
    period : e.g. "1y", "2y", "5y", "max"
    interval : e.g. "1d" (daily). Weekly bars are resampled inside the scanner.
    """
    yahoo = to_yahoo_symbol(symbol, exchange=exchange)
    raw = yf.download(
        yahoo,
        period=period,
        interval=interval,
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    return _flatten_ohlcv(raw, yahoo)


def fetch_index_ohlcv(
    symbol: str = NIFTY50,
    *,
    period: str = "2y",
    interval: str = "1d",
) -> pd.DataFrame:
    """Download benchmark index OHLCV (default Nifty 50)."""
    return fetch_ohlcv(symbol, period=period, interval=interval, exchange="NS")


def load_universe(
    symbols: Iterable[str],
    *,
    period: str = "2y",
    index_symbol: str = NIFTY50,
) -> tuple[list[dict], pd.DataFrame]:
    """
    Fetch stock + index frames ready for run_scanner().

    Returns (universe_items, index_daily_df).
    Skips symbols that fail to download.
    """
    index_df = fetch_index_ohlcv(index_symbol, period=period)
    items: list[dict] = []
    errors: list[str] = []
    for sym in symbols:
        try:
            daily = fetch_ohlcv(sym, period=period)
            if daily.empty or len(daily) < 100:
                errors.append(f"{sym}: insufficient history ({len(daily)} rows)")
                continue
            items.append(
                {
                    "symbol": to_yahoo_symbol(sym).replace(".NS", ""),
                    "daily_df": daily,
                    "stock_is_fno_eligible": True,
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{sym}: {exc}")
    if errors:
        print("Data warnings:")
        for e in errors:
            print(f"  - {e}")
    return items, index_df
