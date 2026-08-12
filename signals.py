"""Buy/sell signal conditions and composite scoring."""

from __future__ import annotations

from typing import Any, Literal

from config import ScannerConfig
from cpr import is_narrow_classification


Direction = Literal["BUY", "SELL"]


def evaluate_binary_signal(
    *,
    direction: Direction,
    weekly_cpr_classification: str | None,
    weekly_close: float,
    weekly_cpr_tc: float,
    weekly_cpr_bc: float,
    volume_ratio: float,
    adx14: float,
    adx_rising: bool,
    relative_strength: float,
    rsi14: float,
    stock_is_fno_eligible: bool,
    config: ScannerConfig | None = None,
) -> bool:
    """Strict pass/fail BUY or SELL conditions from the build spec."""
    cfg = config or ScannerConfig()

    if not is_narrow_classification(weekly_cpr_classification):
        return False
    if not (volume_ratio > cfg.volume_ratio_min):
        return False
    if not (adx14 > cfg.adx_threshold and adx_rising):
        return False

    if direction == "BUY":
        return (
            weekly_close > weekly_cpr_tc
            and relative_strength > 0
            and rsi14 < cfg.rsi_buy_max
        )

    # SELL — F&O only
    if not stock_is_fno_eligible:
        return False
    return (
        weekly_close < weekly_cpr_bc
        and relative_strength < 0
        and rsi14 > cfg.rsi_sell_min
    )


def composite_score(
    *,
    direction: Direction,
    weekly_cpr_classification: str | None,
    weekly_close: float,
    weekly_cpr_tc: float,
    weekly_cpr_bc: float,
    volume_ratio: float,
    adx14: float,
    adx_rising: bool,
    relative_strength: float,
    rsi14: float,
    config: ScannerConfig | None = None,
) -> tuple[float, str]:
    """
    Weighted 0–100 score (identical weights for BUY/SELL; direction flips comparisons).

    score += 40 if (narrow_cpr AND weekly_close_breaks_cpr) else 0
    score += 20 if volume_ratio > 1.0 else (volume_ratio / 1.0) * 20
    score += 15 if (adx14 > 20 and adx_rising) else 0
    score += 15 if relative_strength aligned with direction else 0
    score += 10 if rsi_not_extended else 0
    """
    cfg = config or ScannerConfig()
    score = 0.0

    narrow = is_narrow_classification(weekly_cpr_classification)
    if direction == "BUY":
        breaks_cpr = weekly_close > weekly_cpr_tc
        rs_aligned = relative_strength > 0
        rsi_ok = rsi14 < cfg.rsi_buy_max
    else:
        breaks_cpr = weekly_close < weekly_cpr_bc
        rs_aligned = relative_strength < 0
        rsi_ok = rsi14 > cfg.rsi_sell_min

    if narrow and breaks_cpr:
        score += cfg.weight_core_trigger

    # Partial credit on volume
    if volume_ratio > cfg.volume_ratio_min:
        score += cfg.weight_volume
    elif volume_ratio > 0 and not (volume_ratio != volume_ratio):  # not NaN
        score += (volume_ratio / cfg.volume_ratio_min) * cfg.weight_volume

    if adx14 > cfg.adx_threshold and adx_rising:
        score += cfg.weight_adx

    if rs_aligned:
        score += cfg.weight_rs

    if rsi_ok:
        score += cfg.weight_rsi

    score = float(min(100.0, max(0.0, score)))
    classification = classify_score(score, cfg)
    return score, classification


def classify_score(score: float, config: ScannerConfig | None = None) -> str:
    cfg = config or ScannerConfig()
    if score >= cfg.high_conviction_min:
        return "high_conviction"
    if score >= cfg.watchlist_min:
        return "watchlist"
    return "no_signal"


def resolve_signal_direction(
    buy_score: float,
    sell_score: float,
    buy_signal: bool,
    sell_signal: bool,
) -> str:
    """Pick BUY / SELL / NONE from binary signals and scores."""
    if buy_signal and not sell_signal:
        return "BUY"
    if sell_signal and not buy_signal:
        return "SELL"
    if buy_signal and sell_signal:
        return "BUY" if buy_score >= sell_score else "SELL"
    # Soft ranking: still surface the stronger side if watchlist-worthy
    if buy_score >= sell_score and buy_score >= 50:
        return "BUY"
    if sell_score > buy_score and sell_score >= 50:
        return "SELL"
    return "NONE"


def signal_snapshot(metrics: dict[str, Any], direction: Direction, config: ScannerConfig) -> dict[str, Any]:
    """Helper used by evaluate_stock for one direction."""
    binary = evaluate_binary_signal(
        direction=direction,
        weekly_cpr_classification=metrics["weekly_cpr_classification"],
        weekly_close=metrics["weekly_close"],
        weekly_cpr_tc=metrics["weekly_cpr_tc"],
        weekly_cpr_bc=metrics["weekly_cpr_bc"],
        volume_ratio=metrics["volume_ratio"],
        adx14=metrics["adx14"],
        adx_rising=metrics["adx_rising"],
        relative_strength=metrics["relative_strength"],
        rsi14=metrics["rsi14"],
        stock_is_fno_eligible=metrics["stock_is_fno_eligible"],
        config=config,
    )
    score, classification = composite_score(
        direction=direction,
        weekly_cpr_classification=metrics["weekly_cpr_classification"],
        weekly_close=metrics["weekly_close"],
        weekly_cpr_tc=metrics["weekly_cpr_tc"],
        weekly_cpr_bc=metrics["weekly_cpr_bc"],
        volume_ratio=metrics["volume_ratio"],
        adx14=metrics["adx14"],
        adx_rising=metrics["adx_rising"],
        relative_strength=metrics["relative_strength"],
        rsi14=metrics["rsi14"],
        config=config,
    )
    return {"binary": binary, "score": score, "classification": classification}
