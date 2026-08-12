"""Tests for Yahoo Finance helpers (no network required for unit checks)."""

from __future__ import annotations

import pandas as pd

from data import _flatten_ohlcv, to_yahoo_symbol


def test_to_yahoo_symbol():
    assert to_yahoo_symbol("reliance") == "RELIANCE.NS"
    assert to_yahoo_symbol("RELIANCE.NS") == "RELIANCE.NS"
    assert to_yahoo_symbol("^NSEI") == "^NSEI"


def test_flatten_multiindex_ohlcv():
    idx = pd.bdate_range("2024-01-02", periods=3)
    cols = pd.MultiIndex.from_product(
        [["Close", "High", "Low", "Open", "Volume"], ["RELIANCE.NS"]],
        names=["Price", "Ticker"],
    )
    raw = pd.DataFrame(
        [
            [100, 101, 99, 100, 1000],
            [102, 103, 101, 101, 1100],
            [101, 102, 100, 102, 1200],
        ],
        index=idx,
        columns=cols,
    )
    out = _flatten_ohlcv(raw, "RELIANCE.NS")
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert len(out) == 3
    assert out.iloc[-1]["close"] == 101
