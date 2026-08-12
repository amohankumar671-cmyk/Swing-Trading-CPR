"""Tests for indicators, scoring, entry status, and evaluate_stock."""

from __future__ import annotations

import pandas as pd

from cpr_scanner.config import ScannerConfig
from cpr_scanner.entry_status import resolve_entry_status_full
from cpr_scanner.evaluate import evaluate_stock
from cpr_scanner.indicators import adx, relative_strength, rsi, volume_ratio
from cpr_scanner.scanner import market_regime, run_scanner
from cpr_scanner.signals import classify_score, composite_score, evaluate_binary_signal
from tests.conftest import make_compressed_then_breakout, make_ohlcv


def test_rsi_bounds():
    s = make_ohlcv(n=100)["close"]
    r = rsi(s, 14)
    valid = r.dropna()
    assert valid.min() >= 0
    assert valid.max() <= 100


def test_adx_rising_flag():
    df = make_ohlcv(n=120, trend=0.005, vol_scale=0.005)
    a = adx(df, 14)
    assert "adx" in a.columns
    assert "adx_rising" in a.columns
    assert a["adx"].dropna().iloc[-1] > 0


def test_volume_ratio():
    vol = pd.Series([100.0] * 10 + [200.0])
    vr = volume_ratio(vol, 10)
    assert abs(vr.iloc[-1] - 200.0 / ((100 * 9 + 200) / 10)) < 1e-9


def test_relative_strength_positive_when_stock_outperforms():
    idx = pd.bdate_range("2024-01-01", periods=40)
    stock = pd.Series(range(100, 140), index=idx, dtype=float)
    index = pd.Series([100.0] * 40, index=idx)
    rs = relative_strength(stock, index, 20)
    assert rs > 0


def test_composite_score_core_trigger():
    score, klass = composite_score(
        direction="BUY",
        weekly_cpr_classification="narrow",
        weekly_close=110,
        weekly_cpr_tc=100,
        weekly_cpr_bc=98,
        volume_ratio=1.5,
        adx14=25,
        adx_rising=True,
        relative_strength=2.0,
        rsi14=55,
    )
    assert score == 100
    assert klass == "high_conviction"


def test_composite_score_partial_volume():
    score, _ = composite_score(
        direction="BUY",
        weekly_cpr_classification="narrow",
        weekly_close=110,
        weekly_cpr_tc=100,
        weekly_cpr_bc=98,
        volume_ratio=0.5,
        adx14=10,
        adx_rising=False,
        relative_strength=-1,
        rsi14=80,
    )
    # core 40 + half volume 10 = 50
    assert score == 50
    assert classify_score(score) == "watchlist"


def test_sell_requires_fno():
    kwargs = dict(
        weekly_cpr_classification="extremely_narrow",
        weekly_close=90,
        weekly_cpr_tc=100,
        weekly_cpr_bc=98,
        volume_ratio=1.2,
        adx14=22,
        adx_rising=True,
        relative_strength=-3.0,
        rsi14=40,
    )
    assert evaluate_binary_signal(direction="SELL", stock_is_fno_eligible=False, **kwargs) is False
    assert evaluate_binary_signal(direction="SELL", stock_is_fno_eligible=True, **kwargs) is True


def test_entry_status_confirmed_when_aligned():
    daily = make_ohlcv(n=80, trend=0.01)
    weekly = daily.resample("W-FRI").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()
    status = resolve_entry_status_full(
        weekly_signal_direction="BUY",
        daily_bias="bullish",
        daily_df=daily,
        weekly_df=weekly,
        weekly_signal_true=True,
    )
    assert status == "confirmed"


def test_entry_status_pending_when_inside():
    daily = make_ohlcv(n=80)
    weekly = daily.resample("W-FRI").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()
    status = resolve_entry_status_full(
        weekly_signal_direction="BUY",
        daily_bias="inside",
        daily_df=daily,
        weekly_df=weekly,
        weekly_signal_true=True,
        config=ScannerConfig(pending_confirmation_max_days=10),
    )
    assert status in ("pending_confirmation", "downgrade_watchlist")


def test_evaluate_stock_schema():
    stock = make_compressed_then_breakout()
    index = make_ohlcv(n=len(stock), seed=99, trend=0.0005)
    index.index = stock.index
    out = evaluate_stock(
        daily_df=stock,
        weekly_df=None,
        index_daily_df=index,
        symbol="TEST",
        stock_is_fno_eligible=True,
    )
    required = {
        "symbol",
        "direction",
        "score",
        "classification",
        "entry_status",
        "weekly_cpr_width_pct",
        "weekly_cpr_percentile",
        "stop_loss",
        "target_1",
        "volume_ratio",
        "adx14",
        "relative_strength",
        "rsi14",
        "daily_bias",
    }
    assert required.issubset(out.keys())
    assert out["symbol"] == "TEST"
    assert out["direction"] in ("BUY", "SELL", "NONE")
    assert 0 <= out["score"] <= 100
    assert out["classification"] in ("high_conviction", "watchlist", "no_signal")
    assert out["daily_bias"] in ("bullish", "bearish", "inside")


def test_evaluate_stock_direction_buy_only():
    stock = make_ohlcv(n=260)
    index = make_ohlcv(n=260, seed=1)
    index.index = stock.index
    out = evaluate_stock(
        stock, None, index, direction="BUY", symbol="ABC", stock_is_fno_eligible=True
    )
    assert out["direction"] in ("BUY", "NONE")


def test_market_regime_and_scanner():
    index = make_ohlcv(n=300, seed=3)
    stock_a = make_compressed_then_breakout(seed=7)
    stock_b = make_ohlcv(n=len(stock_a), seed=11)
    stock_a = stock_a.iloc[-len(index) :] if len(stock_a) > len(index) else stock_a
    # Align lengths
    n = min(len(index), len(stock_a), len(stock_b))
    index = index.iloc[-n:]
    stock_a = stock_a.iloc[-n:]
    stock_b = stock_b.iloc[-n:]
    stock_a.index = index.index
    stock_b.index = index.index

    regime = market_regime(index)
    assert regime["scanner_mode"] in ("high_priority", "normal")
    assert "index_cpr_narrow" in regime

    report = run_scanner(
        [
            {"symbol": "AAA", "daily_df": stock_a, "stock_is_fno_eligible": True},
            {"symbol": "BBB", "daily_df": stock_b, "stock_is_fno_eligible": True},
        ],
        index_daily_df=index,
    )
    assert report["scanned"] == 2
    assert isinstance(report["results"], list)
    assert len(report["results"]) == 2
    # ranked descending
    scores = [r["score"] for r in report["results"]]
    assert scores == sorted(scores, reverse=True)
