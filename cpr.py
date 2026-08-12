"""Central Pivot Range (CPR) calculations for daily and weekly bars."""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import ScannerConfig


REQUIRED_OHLC = ("open", "high", "low", "close")


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase column names and ensure required OHLC columns exist."""
    out = df.copy()
    out.columns = [str(c).strip().lower() for c in out.columns]
    missing = [c for c in REQUIRED_OHLC if c not in out.columns]
    if missing:
        raise ValueError(f"DataFrame missing required columns: {missing}")
    return out


def compute_cpr_row(high: float, low: float, close: float) -> dict[str, float]:
    """
    CPR from a single prior period's OHLC.

    Pivot (P)      = (High + Low + Close) / 3
    Bottom CPR (BC) = (High + Low) / 2
    Top CPR (TC)    = (P - BC) + P
    CPR Width       = TC - BC
    CPR Width %     = (CPR Width / Close) * 100
    """
    p = (high + low + close) / 3.0
    bc = (high + low) / 2.0
    tc = (p - bc) + p
    width = tc - bc
    width_pct = (width / close) * 100.0 if close else np.nan
    return {
        "pivot": float(p),
        "bc": float(bc),
        "tc": float(tc),
        "width": float(width),
        "width_pct": float(width_pct),
    }


def add_cpr(df: pd.DataFrame) -> pd.DataFrame:
    """
    Attach CPR columns computed from the *prior* completed bar.

    The current row trades relative to CPR from the previous period's OHLC.
    """
    out = _normalize_columns(df)
    prior_high = out["high"].shift(1)
    prior_low = out["low"].shift(1)
    prior_close = out["close"].shift(1)

    p = (prior_high + prior_low + prior_close) / 3.0
    bc = (prior_high + prior_low) / 2.0
    tc = (p - bc) + p
    width = tc - bc
    width_pct = (width / prior_close) * 100.0

    out["cpr_pivot"] = p
    out["cpr_bc"] = bc
    out["cpr_tc"] = tc
    out["cpr_width"] = width
    out["cpr_width_pct"] = width_pct
    return out


def classify_cpr_width(
    width_pct_series: pd.Series,
    config: ScannerConfig | None = None,
) -> pd.DataFrame:
    """
    Relative narrow-CPR classification via rolling percentile rank.

    percentile_rank = percentile of current week's CPR Width % within last 20–26 weeks
    <= 10  -> extremely_narrow
    <= 25  -> narrow
    else   -> normal
    """
    cfg = config or ScannerConfig()
    lookback = cfg.cpr_lookback
    s = width_pct_series.astype(float)

    def _percentile_rank(window: np.ndarray) -> float:
        # window includes current value as last element
        if np.any(np.isnan(window)):
            return np.nan
        current = window[-1]
        # Percentile rank: fraction of lookback values strictly less than current,
        # plus half the ties — classic percentile rank in [0, 100].
        hist = window  # full window including current
        less = np.sum(hist < current)
        equal = np.sum(hist == current)
        return float((less + 0.5 * equal) / len(hist) * 100.0)

    percentile = s.rolling(window=lookback, min_periods=cfg.cpr_lookback_min).apply(
        _percentile_rank, raw=True
    )

    classification = pd.Series(index=s.index, dtype=object)
    classification = np.where(
        percentile.isna(),
        None,
        np.where(
            percentile <= cfg.extremely_narrow_percentile,
            "extremely_narrow",
            np.where(percentile <= cfg.narrow_percentile, "narrow", "normal"),
        ),
    )

    return pd.DataFrame(
        {
            "cpr_width_pct": s,
            "cpr_percentile": percentile,
            "cpr_classification": classification,
        },
        index=s.index,
    )


def is_narrow_classification(classification: str | None) -> bool:
    return classification in ("narrow", "extremely_narrow")


def daily_cpr_bias(close: float, tc: float, bc: float) -> str:
    """daily_bias = bullish if close > TC else bearish if close < BC else inside."""
    if pd.isna(close) or pd.isna(tc) or pd.isna(bc):
        return "inside"
    if close > tc:
        return "bullish"
    if close < bc:
        return "bearish"
    return "inside"


def resample_daily_to_weekly(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Resample daily OHLCV to weekly bars (week ending Friday by default)."""
    out = _normalize_columns(daily_df)
    if not isinstance(out.index, pd.DatetimeIndex):
        if "date" in out.columns:
            out = out.set_index(pd.to_datetime(out["date"]))
        else:
            raise ValueError("Daily DataFrame needs a DatetimeIndex or a 'date' column")
    out = out.sort_index()

    agg: dict[str, str] = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }
    if "volume" in out.columns:
        agg["volume"] = "sum"

    weekly = out.resample("W-FRI").agg(agg).dropna(subset=["open", "high", "low", "close"])
    return weekly
