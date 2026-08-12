"""Synthetic OHLCV helpers for unit tests."""

from __future__ import annotations

import numpy as np
import pandas as pd


def make_ohlcv(
    n: int = 300,
    start: str = "2023-01-02",
    freq: str = "B",
    start_price: float = 100.0,
    seed: int = 42,
    trend: float = 0.001,
    vol_scale: float = 0.01,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start=start, periods=n)
    rets = trend + vol_scale * rng.standard_normal(n)
    close = start_price * np.cumprod(1 + rets)
    open_ = np.roll(close, 1)
    open_[0] = start_price
    high = np.maximum(open_, close) * (1 + 0.002 * rng.random(n))
    low = np.minimum(open_, close) * (1 - 0.002 * rng.random(n))
    volume = rng.integers(100_000, 500_000, size=n).astype(float)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def make_compressed_then_breakout(
    n: int = 400,
    seed: int = 7,
) -> pd.DataFrame:
    """
    Build daily data that yields many narrow weekly CPRs, then a bullish breakout
    with rising volume/ADX-friendly trend.
    """
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2022-01-03", periods=n)
    prices = []
    price = 100.0
    for i in range(n):
        # Long compression, then breakout in last ~30 sessions
        if i < n - 40:
            shock = 0.0015 * rng.standard_normal()
        else:
            shock = 0.012 + 0.004 * rng.standard_normal()
        price *= 1 + shock
        prices.append(price)
    close = np.array(prices)
    open_ = np.roll(close, 1)
    open_[0] = 100.0
    # Tight ranges during compression
    range_frac = np.where(np.arange(n) < n - 40, 0.004, 0.02)
    high = np.maximum(open_, close) * (1 + range_frac * rng.random(n))
    low = np.minimum(open_, close) * (1 - range_frac * rng.random(n))
    base_vol = 200_000.0
    volume = np.where(
        np.arange(n) < n - 40,
        base_vol * (0.8 + 0.4 * rng.random(n)),
        base_vol * (1.5 + 1.0 * rng.random(n)),
    )
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )
