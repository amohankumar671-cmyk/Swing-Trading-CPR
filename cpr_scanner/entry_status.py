"""Weekly vs daily conflict resolution (timeframe hierarchy)."""

from __future__ import annotations

from typing import Literal

import pandas as pd

from cpr_scanner.config import ScannerConfig
from cpr_scanner.cpr import add_cpr, daily_cpr_bias

EntryStatus = Literal[
    "confirmed",
    "pending_confirmation",
    "downgrade_watchlist",
    "warning_tighten_stop",
    "n/a",
]


def _bias_aligned(weekly_direction: str, daily_bias: str) -> bool:
    if weekly_direction == "BUY":
        return daily_bias == "bullish"
    if weekly_direction == "SELL":
        return daily_bias == "bearish"
    return False


def _bias_opposite(weekly_direction: str, daily_bias: str) -> bool:
    if weekly_direction == "BUY":
        return daily_bias == "bearish"
    if weekly_direction == "SELL":
        return daily_bias == "bullish"
    return False


def _bias_neutral_or_opposite(weekly_direction: str, daily_bias: str) -> bool:
    return daily_bias == "inside" or _bias_opposite(weekly_direction, daily_bias)


def daily_bias_series(daily_df: pd.DataFrame) -> pd.Series:
    """Compute daily_bias for each row using prior-day CPR."""
    d = add_cpr(daily_df)
    return d.apply(
        lambda r: daily_cpr_bias(r["close"], r["cpr_tc"], r["cpr_bc"]),
        axis=1,
    )


def weeks_since_cpr_breakout(
    weekly_df: pd.DataFrame,
    direction: str,
) -> int | None:
    """
    How many completed weekly bars ago the close first broke CPR in `direction`.

    Returns 0 if the latest week just broke out, None if no recent breakout found
    within a short lookback.
    """
    w = add_cpr(weekly_df) if "cpr_tc" not in weekly_df.columns else weekly_df
    look = min(8, len(w))
    if look == 0:
        return None

    for i in range(1, look + 1):
        row = w.iloc[-i]
        close, tc, bc = row["close"], row["cpr_tc"], row["cpr_bc"]
        if pd.isna(tc) or pd.isna(bc):
            continue
        broke = close > tc if direction == "BUY" else close < bc
        if not broke:
            # First non-breakout looking backward => breakout age is i-1 weeks
            # (if i==1, current week is not broken)
            return None if i == 1 else i - 1
    # Entire lookback still broken — treat as aged breakout
    return look


def trading_days_since_weekly_trigger(
    daily_df: pd.DataFrame,
    weekly_df: pd.DataFrame,
    direction: str,
) -> int:
    """
    Approximate trading days since the weekly CPR breakout week started/closed.

    Uses the latest weekly bar's index date vs the latest daily bar.
    """
    if weekly_df.empty or daily_df.empty:
        return 0
    weekly_end = weekly_df.index[-1]
    daily_end = daily_df.index[-1]
    if not isinstance(weekly_end, pd.Timestamp):
        weekly_end = pd.Timestamp(weekly_end)
    if not isinstance(daily_end, pd.Timestamp):
        daily_end = pd.Timestamp(daily_end)

    # Count daily bars strictly after the prior week's end (start of breakout week)
    # Prefer bars on/after the breakout week label.
    mask = daily_df.index >= weekly_end - pd.Timedelta(days=6)
    recent = daily_df.loc[mask]
    return max(0, len(recent) - 1) if len(recent) else 0


def resolve_entry_status(
    *,
    weekly_signal_direction: str,
    daily_bias: str,
    daily_df: pd.DataFrame,
    weekly_signal_true: bool,
    config: ScannerConfig | None = None,
) -> EntryStatus:
    """
    Weekly sets bias; daily sets entry timing only.

    Apply after a weekly buy_signal or sell_signal is True:

    - aligned daily_bias -> confirmed
    - just triggered (1–3 trading days) AND daily neutral/opposite -> pending_confirmation
    - daily opposite for > 3 trading days -> downgrade_watchlist
    - was aligned earlier then flipped opposite -> warning_tighten_stop
    """
    cfg = config or ScannerConfig()

    if not weekly_signal_true or weekly_signal_direction not in ("BUY", "SELL"):
        return "n/a"

    if _bias_aligned(weekly_signal_direction, daily_bias):
        return "confirmed"

    biases = daily_bias_series(daily_df).dropna()
    if biases.empty:
        return "pending_confirmation"

    # Count consecutive opposite days from the end
    opposite_streak = 0
    for b in reversed(list(biases)):
        if _bias_opposite(weekly_signal_direction, b):
            opposite_streak += 1
        else:
            break

    # Was aligned earlier in recent window?
    recent = list(biases.iloc[-max(cfg.downgrade_opposite_days + 5, 10) :])
    had_alignment = any(_bias_aligned(weekly_signal_direction, b) for b in recent)
    flipped_to_opposite = had_alignment and _bias_opposite(weekly_signal_direction, daily_bias)

    if flipped_to_opposite and opposite_streak >= 1:
        # Deterioration after prior confirmation
        if opposite_streak <= cfg.downgrade_opposite_days or had_alignment:
            # Prefer warning when we previously had alignment
            if had_alignment and opposite_streak >= 1:
                return "warning_tighten_stop"

    if opposite_streak > cfg.downgrade_opposite_days:
        return "downgrade_watchlist"

    if _bias_neutral_or_opposite(weekly_signal_direction, daily_bias):
        if opposite_streak <= cfg.pending_confirmation_max_days or days_since <= cfg.pending_confirmation_max_days:
            return "pending_confirmation"
        return "downgrade_watchlist"

    return "pending_confirmation"


def resolve_entry_status_full(
    *,
    weekly_signal_direction: str,
    daily_bias: str,
    daily_df: pd.DataFrame,
    weekly_df: pd.DataFrame,
    weekly_signal_true: bool,
    config: ScannerConfig | None = None,
) -> EntryStatus:
    """Full conflict resolution with weekly trigger timing."""
    cfg = config or ScannerConfig()

    if not weekly_signal_true or weekly_signal_direction not in ("BUY", "SELL"):
        return "n/a"

    if _bias_aligned(weekly_signal_direction, daily_bias):
        return "confirmed"

    biases = daily_bias_series(daily_df)
    recent_biases = list(biases.iloc[-15:]) if len(biases) else []

    opposite_streak = 0
    for b in reversed(recent_biases):
        if _bias_opposite(weekly_signal_direction, b):
            opposite_streak += 1
        else:
            break

    had_alignment = any(_bias_aligned(weekly_signal_direction, b) for b in recent_biases[:-1])
    currently_opposite = _bias_opposite(weekly_signal_direction, daily_bias)

    if had_alignment and currently_opposite:
        return "warning_tighten_stop"

    days_since = trading_days_since_weekly_trigger(daily_df, weekly_df, weekly_signal_direction)

    if currently_opposite and opposite_streak > cfg.downgrade_opposite_days:
        return "downgrade_watchlist"

    if _bias_neutral_or_opposite(weekly_signal_direction, daily_bias):
        if days_since <= cfg.pending_confirmation_max_days or opposite_streak <= cfg.pending_confirmation_max_days:
            return "pending_confirmation"
        return "downgrade_watchlist"

    return "pending_confirmation"
