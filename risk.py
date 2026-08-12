"""Risk management levels attached to every signal output."""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd

from config import ScannerConfig

Direction = Literal["BUY", "SELL"]


def prior_swing_high(weekly_df: pd.DataFrame, lookback: int = 20) -> float:
    """Next visible weekly resistance / prior swing high (excluding current week)."""
    highs = weekly_df["high"].astype(float)
    if len(highs) < 2:
        return float(highs.iloc[-1]) if len(highs) else float("nan")
    window = highs.iloc[-(lookback + 1) : -1]
    return float(window.max()) if len(window) else float(highs.iloc[-2])


def prior_swing_low(weekly_df: pd.DataFrame, lookback: int = 20) -> float:
    """Next visible weekly support / prior swing low (excluding current week)."""
    lows = weekly_df["low"].astype(float)
    if len(lows) < 2:
        return float(lows.iloc[-1]) if len(lows) else float("nan")
    window = lows.iloc[-(lookback + 1) : -1]
    return float(window.min()) if len(window) else float(lows.iloc[-2])


def build_risk_plan(
    *,
    direction: Direction,
    weekly_cpr_bc: float,
    weekly_cpr_tc: float,
    current_week_low: float,
    current_week_high: float,
    daily_cpr_bc: float,
    daily_cpr_tc: float,
    ema20: float | None,
    weekly_df: pd.DataFrame,
    config: ScannerConfig | None = None,
) -> dict[str, Any]:
    """
    BUY:
      stop_loss = min(weekly_CPR_bottom, current_week_low)
      target_1  = next visible weekly resistance / prior swing high
      trail     = daily_CPR_bottom or rising EMA20 once trend established
      invalidation / time_stop notes

    SELL: mirror.
    """
    cfg = config or ScannerConfig()

    if direction == "BUY":
        stop_loss = float(min(weekly_cpr_bc, current_week_low))
        target_1 = prior_swing_high(weekly_df, cfg.swing_lookback_weeks)
        # Prefer higher of structure targets if swing high is below price context
        trail = f"daily_CPR_bottom ({daily_cpr_bc:.2f})"
        if ema20 is not None and not (isinstance(ema20, float) and np.isnan(ema20)):
            trail += f" or rising EMA20 ({float(ema20):.2f}) once trend established"
        invalidation = (
            f"weekly_close back inside or below weekly CPR within "
            f"{cfg.invalidation_weeks} weeks -> exit"
        )
        time_stop = (
            f"no follow-through within {cfg.time_stop_weeks} weeks of breakout -> exit"
        )
    else:
        stop_loss = float(max(weekly_cpr_tc, current_week_high))
        target_1 = prior_swing_low(weekly_df, cfg.swing_lookback_weeks)
        trail = f"daily_CPR_top ({daily_cpr_tc:.2f})"
        if ema20 is not None and not (isinstance(ema20, float) and np.isnan(ema20)):
            trail += f" or falling EMA20 ({float(ema20):.2f}) once trend established"
        invalidation = (
            f"weekly_close back inside or above weekly CPR within "
            f"{cfg.invalidation_weeks} weeks -> exit"
        )
        time_stop = (
            f"no follow-through within {cfg.time_stop_weeks} weeks of breakdown -> exit"
        )

    return {
        "stop_loss": stop_loss,
        "target_1": float(target_1),
        "trail": trail,
        "invalidation": invalidation,
        "time_stop": time_stop,
    }
