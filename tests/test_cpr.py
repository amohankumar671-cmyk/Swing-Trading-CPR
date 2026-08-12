"""Tests for CPR calculation and narrow classification."""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import ScannerConfig
from cpr import (
    add_cpr,
    classify_cpr_width,
    compute_cpr_row,
    daily_cpr_bias,
    is_narrow_classification,
    resample_daily_to_weekly,
)
from tests.conftest import make_ohlcv


def test_compute_cpr_row_formula():
    high, low, close = 110.0, 100.0, 108.0
    cpr = compute_cpr_row(high, low, close)
    p = (110 + 100 + 108) / 3
    bc = (110 + 100) / 2
    tc = (p - bc) + p
    assert abs(cpr["pivot"] - p) < 1e-9
    assert abs(cpr["bc"] - bc) < 1e-9
    assert abs(cpr["tc"] - tc) < 1e-9
    assert abs(cpr["width"] - (tc - bc)) < 1e-9
    assert abs(cpr["width_pct"] - ((tc - bc) / close) * 100) < 1e-9


def test_add_cpr_uses_prior_bar():
    df = pd.DataFrame(
        {
            "open": [10, 11, 12],
            "high": [12, 13, 14],
            "low": [9, 10, 11],
            "close": [11, 12, 13],
            "volume": [1, 1, 1],
        },
        index=pd.bdate_range("2024-01-01", periods=3),
    )
    out = add_cpr(df)
    assert np.isnan(out.iloc[0]["cpr_pivot"])
    expected = compute_cpr_row(12, 9, 11)
    assert abs(out.iloc[1]["cpr_tc"] - expected["tc"]) < 1e-9
    assert abs(out.iloc[1]["cpr_bc"] - expected["bc"]) < 1e-9


def test_daily_cpr_bias():
    assert daily_cpr_bias(110, 105, 100) == "bullish"
    assert daily_cpr_bias(95, 105, 100) == "bearish"
    assert daily_cpr_bias(102, 105, 100) == "inside"


def test_classify_narrow_percentile():
    # Build a series where the last value is among the lowest
    widths = pd.Series([5.0] * 20 + [0.5])
    cfg = ScannerConfig(cpr_lookback_min=20, cpr_lookback_max=21)
    out = classify_cpr_width(widths, cfg)
    assert out.iloc[-1]["cpr_classification"] == "extremely_narrow"
    assert is_narrow_classification(out.iloc[-1]["cpr_classification"])


def test_resample_weekly():
    daily = make_ohlcv(n=60)
    weekly = resample_daily_to_weekly(daily)
    assert len(weekly) >= 8
    assert set(["open", "high", "low", "close", "volume"]).issubset(weekly.columns)
