"""Pure helpers shared by the Streamlit dashboard (safe to import in tests)."""

from __future__ import annotations

from typing import Any

import pandas as pd

DISPLAY_COLS = [
    "symbol",
    "direction",
    "score",
    "classification",
    "entry_status",
    "weekly_cpr_classification",
    "weekly_cpr_percentile",
    "volume_ratio",
    "adx14",
    "relative_strength",
    "rsi14",
    "daily_bias",
    "stop_loss",
    "target_1",
]


def parse_symbols(text: str) -> list[str]:
    parts = [p.strip().upper() for p in text.replace("\n", ",").split(",")]
    return [p for p in parts if p]


def results_frame(
    results: list[dict[str, Any]],
    min_score: float,
    direction: str,
) -> pd.DataFrame:
    if not results:
        return pd.DataFrame(columns=DISPLAY_COLS)
    df = pd.DataFrame(results)
    for col in DISPLAY_COLS:
        if col not in df.columns:
            df[col] = None
    df = df[DISPLAY_COLS]
    df = df[df["score"] >= min_score]
    if direction != "ALL":
        df = df[df["direction"] == direction]
    return df.sort_values("score", ascending=False).reset_index(drop=True)
