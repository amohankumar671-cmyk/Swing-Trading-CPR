# CPR Multi-Timeframe Swing Scanner

Python module that scores NSE F&O swing setups from **weekly CPR compression + breakout**, with daily CPR used only for entry timing.

All scanner modules live in the repo root.

## Install

```bash
pip install -r requirements.txt
pip install -e .
```

## Quick start

```python
from config import ScannerConfig
from evaluate import evaluate_stock
from scanner import run_scanner, market_regime

# daily_df / weekly_df: DataFrames with columns open, high, low, close, volume
# (DatetimeIndex preferred; weekly can be omitted and will be resampled)

signal = evaluate_stock(
    daily_df=stock_daily,
    weekly_df=None,                 # optional — resampled from daily
    index_daily_df=nifty_daily,
    index_weekly_df=None,
    direction=None,                 # None = score both BUY and SELL
    symbol="RELIANCE",
    stock_is_fno_eligible=True,
    config=ScannerConfig(),         # tunable percentiles / weights
)

# Full universe
report = run_scanner(
    universe=[
        {"symbol": "RELIANCE", "daily_df": reliance_daily, "stock_is_fno_eligible": True},
        # ...
    ],
    index_daily_df=nifty_daily,
)
print(report["scanner_mode"])  # high_priority | normal
print(report["results"][0])
```

Synthetic demo:

```bash
python run_synthetic_scan.py
```

## Layout

| File | Role |
|------|------|
| `cpr.py` | CPR calc, narrow percentile classification, weekly resample |
| `indicators.py` | EMA, RSI, ADX, volume ratio, relative strength |
| `signals.py` | BUY/SELL conditions + composite score |
| `entry_status.py` | Weekly vs daily conflict resolution |
| `risk.py` | Stop / target / trail / invalidation |
| `evaluate.py` | `evaluate_stock()` output schema |
| `scanner.py` | Market regime + universe loop |
| `config.py` | Tunable thresholds |

## Logic summary

| Layer | Role |
|--------|------|
| Weekly CPR | Bias / breakout trigger (narrow CPR + close beyond TC/BC) |
| Daily CPR | Entry timing only (`daily_bias` → `entry_status`) |
| Score 0–100 | Ranked watchlist instead of binary-only filters |
| Index weekly CPR | Market regime pre-filter (`high_priority` when index CPR is narrow) |

### Output schema (per stock)

```json
{
  "symbol": "string",
  "direction": "BUY | SELL | NONE",
  "score": 0,
  "classification": "high_conviction | watchlist | no_signal",
  "entry_status": "confirmed | pending_confirmation | downgrade_watchlist | warning_tighten_stop | n/a",
  "weekly_cpr_width_pct": 0.0,
  "weekly_cpr_percentile": 0.0,
  "stop_loss": 0.0,
  "target_1": 0.0,
  "volume_ratio": 0.0,
  "adx14": 0.0,
  "relative_strength": 0.0,
  "rsi14": 0.0,
  "daily_bias": "bullish | bearish | inside"
}
```

SELL signals are only generated when `stock_is_fno_eligible=True`.

## Config knobs

`ScannerConfig` exposes lookback (20–26 weeks), narrow percentiles (10 / 25), ADX/RSI/volume thresholds, and score weights so you can backtest and tune.

## Tests

```bash
pytest -q
```
