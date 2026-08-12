# CPR Multi-Timeframe Swing Scanner

Python module that scores NSE F&O swing setups from **weekly CPR compression + breakout**, with daily CPR used only for entry timing.

All scanner modules live in the repo root.

## Install

```bash
pip install -r requirements.txt
```

Dependencies: **pandas**, **numpy**, **yfinance** (free Yahoo Finance data). Optional: **pytest**.

Use **Python 3.12** (recommended on Windows). Avoid Python 3.14 for now.

## Free data (Yahoo Finance — no broker / no payment)

OHLCV is loaded with `yfinance`. NSE stocks use `.NS` (handled for you). Nifty is `^NSEI`.

```bash
# activate your venv first on Windows:  .venv\Scripts\activate
pip install -r requirements.txt
python run_yahoo_scan.py
```

Scan specific symbols:

```bash
python run_yahoo_scan.py --symbols RELIANCE TCS INFY SBIN --min-score 0
```

### Quick start (your own DataFrames)

```python
from config import ScannerConfig
from evaluate import evaluate_stock
from scanner import run_scanner, market_regime
from data import fetch_ohlcv, fetch_index_ohlcv

stock_daily = fetch_ohlcv("RELIANCE", period="2y")
nifty_daily = fetch_index_ohlcv(period="2y")

signal = evaluate_stock(
    daily_df=stock_daily,
    weekly_df=None,                 # optional — resampled from daily
    index_daily_df=nifty_daily,
    index_weekly_df=None,
    direction=None,                 # None = score both BUY and SELL
    symbol="RELIANCE",
    stock_is_fno_eligible=True,
    config=ScannerConfig(),
)
print(signal)
```

Synthetic demo (no internet):

```bash
python run_synthetic_scan.py
```

Yahoo is free and fine for building/testing. It is **not** an official exchange feed — later you can swap `data.py` for a broker API without changing the scanner logic.
## Layout

| File | Role |
|------|------|
| `data.py` | Free Yahoo Finance OHLCV loader (`yfinance`) |
| `cpr.py` | CPR calc, narrow percentile classification, weekly resample |
| `indicators.py` | EMA, RSI, ADX, volume ratio, relative strength |
| `signals.py` | BUY/SELL conditions + composite score |
| `entry_status.py` | Weekly vs daily conflict resolution |
| `risk.py` | Stop / target / trail / invalidation |
| `evaluate.py` | `evaluate_stock()` output schema |
| `scanner.py` | Market regime + universe loop |
| `config.py` | Tunable thresholds |
| `run_yahoo_scan.py` | End-to-end scan using Yahoo data |
| `run_synthetic_scan.py` | Offline demo with fake OHLCV |

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
