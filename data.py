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

from universe import SAMPLE_SYMBOLS, fno_symbol_set

NIFTY50 = "^NSEI"

# Back-compat alias used by older scripts/docs
DEFAULT_FNO_SYMBOLS: list[str] = list(SAMPLE_SYMBOLS)


def to_yahoo_symbol(symbol: str, exchange: str = "NS") -> str:
    """Convert plain NSE ticker to Yahoo symbol. Pass-through for ^INDEX and already-suffixed."""
    s = symbol.strip().upper()
    if s.startswith("^") or "." in s:
        return s
    return f"{s}.{exchange}"


def _normalize_single_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip().lower() for c in out.columns]
    out = out.rename(columns={"adj close": "close", "adj_close": "close"})
    needed = ["open", "high", "low", "close", "volume"]
    missing = [c for c in needed if c not in out.columns]
    if missing:
        raise ValueError(f"Yahoo data missing columns {missing}")
    out = out[needed].dropna(subset=["open", "high", "low", "close"])
    out.index = pd.to_datetime(out.index)
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_localize(None)
    return out.sort_index()


def _flatten_ohlcv(df: pd.DataFrame, yahoo_symbol: str) -> pd.DataFrame:
    """Normalize yfinance single/multi-ticker download to open/high/low/close/volume."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        level0 = out.columns.get_level_values(0)
        level1 = out.columns.get_level_values(1)
        if yahoo_symbol in set(level1):
            out = out.xs(yahoo_symbol, axis=1, level=1)
        elif len(set(level1)) == 1:
            out = out.droplevel(1, axis=1)
        else:
            try:
                out = out.xs(yahoo_symbol, axis=1, level=-1)
            except KeyError:
                out.columns = level0

    return _normalize_single_ohlcv(out)


def fetch_ohlcv(
    symbol: str,
    *,
    period: str = "2y",
    interval: str = "1d",
    exchange: str = "NS",
) -> pd.DataFrame:
    """Download daily (or other) OHLCV from Yahoo Finance for one symbol."""
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


def fetch_many_ohlcv(
    symbols: Iterable[str],
    *,
    period: str = "2y",
    interval: str = "1d",
    batch_size: int = 40,
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """
    Batch-download OHLCV for many NSE symbols (faster than one-by-one).

    Returns (symbol -> daily_df, error_messages).
    """
    plain = []
    seen: set[str] = set()
    for s in symbols:
        p = to_yahoo_symbol(s).replace(".NS", "").replace("^", "")
        # Keep index symbols out of equity batch
        if s.strip().startswith("^"):
            continue
        if p and p not in seen:
            seen.add(p)
            plain.append(p)

    frames: dict[str, pd.DataFrame] = {}
    errors: list[str] = []

    for i in range(0, len(plain), batch_size):
        chunk = plain[i : i + batch_size]
        yahoos = [to_yahoo_symbol(s) for s in chunk]
        try:
            raw = yf.download(
                yahoos,
                period=period,
                interval=interval,
                auto_adjust=True,
                progress=False,
                threads=True,
                group_by="ticker",
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"batch {chunk[0]}..{chunk[-1]}: {exc}")
            # Fallback to singles for this chunk
            for s in chunk:
                try:
                    frames[s] = fetch_ohlcv(s, period=period, interval=interval)
                except Exception as e2:  # noqa: BLE001
                    errors.append(f"{s}: {e2}")
            continue

        if raw is None or raw.empty:
            for s in chunk:
                errors.append(f"{s}: empty download")
            continue

        # Single ticker still returns flat columns
        if len(chunk) == 1:
            s = chunk[0]
            try:
                frames[s] = _flatten_ohlcv(raw, to_yahoo_symbol(s))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{s}: {exc}")
            continue

        # Multi-ticker: columns are (ticker, price) or sometimes (price, ticker)
        if isinstance(raw.columns, pd.MultiIndex):
            level0 = set(map(str, raw.columns.get_level_values(0)))
            for s, yahoo in zip(chunk, yahoos):
                try:
                    if yahoo in level0:
                        sub = raw[yahoo]
                    elif s in level0:
                        sub = raw[s]
                    else:
                        # try level 1
                        sub = raw.xs(yahoo, axis=1, level=-1, drop_level=True)
                    frames[s] = _normalize_single_ohlcv(sub)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{s}: {exc}")
        else:
            errors.append("unexpected Yahoo multi-ticker layout")

    return frames, errors


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
    min_bars: int = 100,
    fno_only_sell: bool | None = None,
) -> tuple[list[dict], pd.DataFrame, list[str]]:
    """
    Fetch stock + index frames ready for run_scanner().

    Returns (universe_items, index_daily_df, warnings).
    `stock_is_fno_eligible` is True only for symbols in the bundled F&O list
    (unless fno_only_sell is overridden).
    """
    index_df = fetch_index_ohlcv(index_symbol, period=period)
    frames, errors = fetch_many_ohlcv(symbols, period=period)
    fno = fno_symbol_set()
    items: list[dict] = []
    warnings = list(errors)

    for sym, daily in frames.items():
        if daily is None or daily.empty or len(daily) < min_bars:
            warnings.append(
                f"{sym}: insufficient history ({0 if daily is None else len(daily)} rows)"
            )
            continue
        if fno_only_sell is None:
            eligible = sym in fno
        else:
            eligible = bool(fno_only_sell)
        items.append(
            {
                "symbol": sym,
                "daily_df": daily,
                "stock_is_fno_eligible": eligible,
            }
        )

    if warnings:
        print("Data warnings:")
        for e in warnings[:30]:
            print(f"  - {e}")
        if len(warnings) > 30:
            print(f"  ... and {len(warnings) - 30} more")

    return items, index_df, warnings
