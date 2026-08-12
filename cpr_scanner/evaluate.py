"""Core evaluate_stock() API returning the per-stock scan schema."""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd

from cpr_scanner.config import ScannerConfig
from cpr_scanner.cpr import (
    add_cpr,
    classify_cpr_width,
    daily_cpr_bias,
    resample_daily_to_weekly,
)
from cpr_scanner.entry_status import resolve_entry_status_full
from cpr_scanner.indicators import (
    add_daily_emas,
    add_weekly_indicators,
    relative_strength,
)
from cpr_scanner.risk import build_risk_plan
from cpr_scanner.signals import (
    composite_score,
    evaluate_binary_signal,
    resolve_signal_direction,
)

Direction = Literal["BUY", "SELL"]


def _ensure_weekly(daily_df: pd.DataFrame, weekly_df: pd.DataFrame | None) -> pd.DataFrame:
    if weekly_df is not None and len(weekly_df) > 0:
        return weekly_df.copy()
    return resample_daily_to_weekly(daily_df)


def _prepare_frames(
    daily_df: pd.DataFrame,
    weekly_df: pd.DataFrame | None,
    config: ScannerConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = add_daily_emas(add_cpr(daily_df), config)
    weekly = _ensure_weekly(daily_df, weekly_df)
    weekly = add_cpr(weekly)
    weekly = add_weekly_indicators(weekly, config)

    class_df = classify_cpr_width(weekly["cpr_width_pct"], config)
    weekly = weekly.join(class_df[["cpr_percentile", "cpr_classification"]], how="left")
    return daily, weekly


def _safe_float(value: Any, default: float = float("nan")) -> float:
    try:
        v = float(value)
        if np.isnan(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def evaluate_stock(
    daily_df: pd.DataFrame,
    weekly_df: pd.DataFrame | None,
    index_daily_df: pd.DataFrame,
    index_weekly_df: pd.DataFrame | None = None,
    direction: Direction | None = None,
    *,
    symbol: str = "",
    stock_is_fno_eligible: bool = True,
    config: ScannerConfig | None = None,
) -> dict[str, Any]:
    """
    Evaluate one stock against the CPR multi-timeframe swing rules.

    Parameters
    ----------
    daily_df, weekly_df :
        OHLCV for the stock. Weekly may be omitted (resampled from daily).
    index_daily_df, index_weekly_df :
        Benchmark (Nifty / sector) for relative strength and regime.
    direction :
        If "BUY" or "SELL", score/signal only that side. If None, evaluate both
        and pick the stronger side.
    symbol :
        Ticker for the output schema.
    stock_is_fno_eligible :
        SELL signals require True (F&O shorting).
    config :
        Optional ScannerConfig overrides.

    Returns
    -------
    dict matching the build-spec output schema (plus risk extras).
    """
    cfg = config or ScannerConfig()

    if daily_df is None or len(daily_df) == 0:
        raise ValueError("daily_df is required and must be non-empty")
    if index_daily_df is None or len(index_daily_df) == 0:
        raise ValueError("index_daily_df is required and must be non-empty")

    daily, weekly = _prepare_frames(daily_df, weekly_df, cfg)
    index_daily = add_cpr(index_daily_df)
    index_weekly = _ensure_weekly(index_daily_df, index_weekly_df)
    index_weekly = add_cpr(index_weekly)
    index_class = classify_cpr_width(index_weekly["cpr_width_pct"], cfg)
    index_weekly = index_weekly.join(
        index_class[["cpr_percentile", "cpr_classification"]], how="left"
    )

    w = weekly.iloc[-1]
    d = daily.iloc[-1]

    weekly_close = _safe_float(w["close"])
    weekly_cpr_tc = _safe_float(w["cpr_tc"])
    weekly_cpr_bc = _safe_float(w["cpr_bc"])
    weekly_cpr_width_pct = _safe_float(w["cpr_width_pct"])
    weekly_cpr_percentile = _safe_float(w["cpr_percentile"])
    weekly_cpr_classification = w.get("cpr_classification")
    if isinstance(weekly_cpr_classification, float) and np.isnan(weekly_cpr_classification):
        weekly_cpr_classification = None

    volume_ratio = _safe_float(w.get("volume_ratio"), 0.0)
    adx14 = _safe_float(w.get("adx"), 0.0)
    adx_rising = bool(w.get("adx_rising")) if not pd.isna(w.get("adx_rising")) else False
    rsi14 = _safe_float(w.get("rsi14"), 50.0)

    rs = relative_strength(
        daily["close"],
        index_daily["close"] if "close" in index_daily.columns else add_cpr(index_daily_df)["close"],
        cfg.rs_lookback_days,
    )
    rs = _safe_float(rs, 0.0)

    daily_bias = daily_cpr_bias(
        _safe_float(d["close"]),
        _safe_float(d["cpr_tc"]),
        _safe_float(d["cpr_bc"]),
    )

    metrics = {
        "weekly_cpr_classification": weekly_cpr_classification,
        "weekly_close": weekly_close,
        "weekly_cpr_tc": weekly_cpr_tc,
        "weekly_cpr_bc": weekly_cpr_bc,
        "volume_ratio": volume_ratio,
        "adx14": adx14,
        "adx_rising": adx_rising,
        "relative_strength": rs,
        "rsi14": rsi14,
        "stock_is_fno_eligible": stock_is_fno_eligible,
    }

    directions: list[Direction]
    if direction in ("BUY", "SELL"):
        directions = [direction]  # type: ignore[list-item]
    else:
        directions = ["BUY", "SELL"]

    score_keys = {
        "weekly_cpr_classification",
        "weekly_close",
        "weekly_cpr_tc",
        "weekly_cpr_bc",
        "volume_ratio",
        "adx14",
        "adx_rising",
        "relative_strength",
        "rsi14",
    }
    score_metrics = {k: metrics[k] for k in score_keys}

    results: dict[str, dict[str, Any]] = {}
    for direc in directions:
        binary = evaluate_binary_signal(direction=direc, config=cfg, **metrics)
        score, classification = composite_score(direction=direc, config=cfg, **score_metrics)
        results[direc] = {
            "binary": binary,
            "score": score,
            "classification": classification,
        }

    if len(directions) == 1:
        side = directions[0]
        if results[side]["binary"] or results[side]["classification"] != "no_signal":
            chosen = side
        else:
            chosen = "NONE"
    else:
        chosen = resolve_signal_direction(
            buy_score=results["BUY"]["score"],
            sell_score=results["SELL"]["score"],
            buy_signal=results["BUY"]["binary"],
            sell_signal=results["SELL"]["binary"],
        )

    if chosen == "NONE":
        # Prefer the higher score side for reporting metrics, but direction NONE
        buy_s = results.get("BUY", {}).get("score", 0.0)
        sell_s = results.get("SELL", {}).get("score", 0.0)
        report_side: Direction = "BUY" if buy_s >= sell_s else "SELL"
        score = results[report_side]["score"]
        classification = results[report_side]["classification"]
        weekly_signal_true = False
        risk_direction: Direction = report_side
    else:
        score = results[chosen]["score"]
        classification = results[chosen]["classification"]
        weekly_signal_true = bool(results[chosen]["binary"])
        risk_direction = chosen  # type: ignore[assignment]

    entry_status = resolve_entry_status_full(
        weekly_signal_direction=chosen if chosen != "NONE" else risk_direction,
        daily_bias=daily_bias,
        daily_df=daily,
        weekly_df=weekly,
        weekly_signal_true=weekly_signal_true and chosen != "NONE",
        config=cfg,
    )
    if chosen == "NONE":
        entry_status = "n/a"

    ema20 = _safe_float(d.get("ema20")) if "ema20" in daily.columns else float("nan")
    risk = build_risk_plan(
        direction=risk_direction,
        weekly_cpr_bc=weekly_cpr_bc,
        weekly_cpr_tc=weekly_cpr_tc,
        current_week_low=_safe_float(w["low"]),
        current_week_high=_safe_float(w["high"]),
        daily_cpr_bc=_safe_float(d["cpr_bc"]),
        daily_cpr_tc=_safe_float(d["cpr_tc"]),
        ema20=ema20,
        weekly_df=weekly,
        config=cfg,
    )

    index_cpr_class = index_weekly.iloc[-1].get("cpr_classification")
    index_cpr_narrow = index_cpr_class in ("narrow", "extremely_narrow")

    output: dict[str, Any] = {
        "symbol": symbol,
        "direction": chosen,
        "score": round(float(score), 2),
        "classification": classification,
        "entry_status": entry_status,
        "weekly_cpr_width_pct": round(weekly_cpr_width_pct, 4)
        if not np.isnan(weekly_cpr_width_pct)
        else None,
        "weekly_cpr_percentile": round(weekly_cpr_percentile, 2)
        if not np.isnan(weekly_cpr_percentile)
        else None,
        "weekly_cpr_classification": weekly_cpr_classification,
        "stop_loss": round(risk["stop_loss"], 2)
        if not np.isnan(risk["stop_loss"])
        else None,
        "target_1": round(risk["target_1"], 2) if not np.isnan(risk["target_1"]) else None,
        "volume_ratio": round(volume_ratio, 3) if not np.isnan(volume_ratio) else None,
        "adx14": round(adx14, 2) if not np.isnan(adx14) else None,
        "relative_strength": round(rs, 3) if not np.isnan(rs) else None,
        "rsi14": round(rsi14, 2) if not np.isnan(rsi14) else None,
        "daily_bias": daily_bias,
        # Extras useful for scanning / risk (beyond minimal schema)
        "trail": risk["trail"],
        "invalidation": risk["invalidation"],
        "time_stop": risk["time_stop"],
        "index_cpr_narrow": bool(index_cpr_narrow),
        "stock_is_fno_eligible": stock_is_fno_eligible,
    }
    return output
