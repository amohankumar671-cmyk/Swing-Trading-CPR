"""Configurable thresholds for the CPR swing scanner."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScannerConfig:
    """Tunable parameters — treat lookback/percentiles as starting points to backtest."""

    # Narrow CPR lookback (weekly CPR Width % history)
    cpr_lookback_min: int = 20
    cpr_lookback_max: int = 26
    extremely_narrow_percentile: float = 10.0
    narrow_percentile: float = 25.0

    # Indicators
    rsi_period: int = 14
    adx_period: int = 14
    adx_threshold: float = 20.0
    volume_avg_weeks: int = 10
    rs_lookback_days: int = 20
    ema_periods: tuple[int, ...] = field(default_factory=lambda: (20, 50, 200))

    # Signal thresholds
    rsi_buy_max: float = 68.0
    rsi_sell_min: float = 32.0
    volume_ratio_min: float = 1.0

    # Composite score weights
    weight_core_trigger: float = 40.0
    weight_volume: float = 20.0
    weight_adx: float = 15.0
    weight_rs: float = 15.0
    weight_rsi: float = 10.0

    # Score classification
    high_conviction_min: float = 80.0
    watchlist_min: float = 50.0

    # Entry status / conflict resolution
    pending_confirmation_max_days: int = 3
    downgrade_opposite_days: int = 3

    # Risk
    swing_lookback_weeks: int = 20
    invalidation_weeks: int = 2
    time_stop_weeks: int = 3

    @property
    def cpr_lookback(self) -> int:
        """Default lookback uses the upper end of the 20–26 week range."""
        return self.cpr_lookback_max
