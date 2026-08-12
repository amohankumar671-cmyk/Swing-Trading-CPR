"""CPR Multi-Timeframe Swing Scanner for NSE F&O stocks."""

from cpr_scanner.config import ScannerConfig
from cpr_scanner.evaluate import evaluate_stock
from cpr_scanner.scanner import run_scanner, market_regime

__all__ = [
    "ScannerConfig",
    "evaluate_stock",
    "run_scanner",
    "market_regime",
]

__version__ = "0.1.0"
