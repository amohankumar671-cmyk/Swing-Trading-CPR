"""Supporting technical indicators for the CPR swing scanner."""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import ScannerConfig
from cpr import _normalize_columns


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.astype(float).ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI."""
    delta = series.astype(float).diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    out = out.where(avg_loss != 0, 100.0)
    out = out.where(avg_gain != 0, 0.0)
    return out


def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Average Directional Index (Wilder).

    Returns columns: adx, plus_di, minus_di, adx_rising.
    """
    out = _normalize_columns(df)
    high = out["high"].astype(float)
    low = out["low"].astype(float)
    close = out["close"].astype(float)

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)

    alpha = 1.0 / period
    atr = tr.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    plus_di = (
        100.0
        * pd.Series(plus_dm, index=out.index)
        .ewm(alpha=alpha, min_periods=period, adjust=False)
        .mean()
        / atr
    )
    minus_di = (
        100.0
        * pd.Series(minus_dm, index=out.index)
        .ewm(alpha=alpha, min_periods=period, adjust=False)
        .mean()
        / atr
    )

    dx = (100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx_val = dx.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    adx_rising = adx_val > adx_val.shift(1)

    return pd.DataFrame(
        {
            "adx": adx_val,
            "plus_di": plus_di,
            "minus_di": minus_di,
            "adx_rising": adx_rising,
        },
        index=out.index,
    )


def volume_ratio(volume: pd.Series, weeks: int = 10) -> pd.Series:
    """current_week_volume / volume_avg_Nw."""
    vol = volume.astype(float)
    avg = vol.rolling(window=weeks, min_periods=max(1, weeks // 2)).mean()
    return vol / avg.replace(0, np.nan)


def relative_strength(
    stock_close: pd.Series,
    index_close: pd.Series,
    lookback_days: int = 20,
) -> float:
    """
    Stock % return over last N trading days minus index % return over same period.
    """
    stock = stock_close.astype(float).dropna()
    index = index_close.astype(float).dropna()
    # Align on common dates when both are DatetimeIndex
    if isinstance(stock.index, pd.DatetimeIndex) and isinstance(index.index, pd.DatetimeIndex):
        common = stock.index.intersection(index.index)
        stock = stock.loc[common]
        index = index.loc[common]

    if len(stock) < lookback_days + 1 or len(index) < lookback_days + 1:
        return float("nan")

    s0, s1 = float(stock.iloc[-(lookback_days + 1)]), float(stock.iloc[-1])
    i0, i1 = float(index.iloc[-(lookback_days + 1)]), float(index.iloc[-1])
    if s0 == 0 or i0 == 0:
        return float("nan")
    stock_ret = (s1 / s0 - 1.0) * 100.0
    index_ret = (i1 / i0 - 1.0) * 100.0
    return stock_ret - index_ret


def add_daily_emas(daily_df: pd.DataFrame, config: ScannerConfig | None = None) -> pd.DataFrame:
    cfg = config or ScannerConfig()
    out = _normalize_columns(daily_df)
    for period in cfg.ema_periods:
        out[f"ema{period}"] = ema(out["close"], period)
    return out


def add_weekly_indicators(
    weekly_df: pd.DataFrame,
    config: ScannerConfig | None = None,
) -> pd.DataFrame:
    cfg = config or ScannerConfig()
    out = _normalize_columns(weekly_df)
    out["rsi14"] = rsi(out["close"], cfg.rsi_period)
    adx_df = adx(out, cfg.adx_period)
    out = out.join(adx_df)
    if "volume" in out.columns:
        out["volume_avg_10w"] = (
            out["volume"].astype(float).rolling(cfg.volume_avg_weeks, min_periods=1).mean()
        )
        out["volume_ratio"] = volume_ratio(out["volume"], cfg.volume_avg_weeks)
    else:
        out["volume_avg_10w"] = np.nan
        out["volume_ratio"] = np.nan
    return out
