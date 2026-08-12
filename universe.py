"""NSE universe presets for one-click scanning.

Bundled lists (offline-friendly):
  - sample   : small starter set
  - nifty50  : Nifty 50 constituents
  - nse_fno  : NSE F&O underlyings (~200) — recommended default for this scanner
  - nifty500 : Nifty 500 constituents

Lists live under universes/*.txt and can be refreshed from NSE when online.
"""

from __future__ import annotations

import csv
import io
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UNIVERSE_DIR = ROOT / "universes"

SAMPLE_SYMBOLS: list[str] = [
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "ITC",
    "BHARTIARTL",
    "LT",
    "KOTAKBANK",
]

PRESET_FILES = {
    "sample": None,  # uses SAMPLE_SYMBOLS
    "nifty50": "nifty50.txt",
    "nse_fno": "nse_fno.txt",
    "nifty500": "nifty500.txt",
}

PRESET_LABELS = {
    "sample": "Sample (10)",
    "nifty50": "Nifty 50",
    "nse_fno": "NSE F&O (full)",
    "nifty500": "Nifty 500",
}


def _read_symbol_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    symbols: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip().upper()
        if s and not s.startswith("#"):
            symbols.append(s)
    # Preserve order, drop dupes
    seen: set[str] = set()
    out: list[str] = []
    for s in symbols:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def load_preset(name: str) -> list[str]:
    """Load a bundled universe preset by key."""
    key = name.strip().lower()
    if key not in PRESET_FILES:
        raise ValueError(f"Unknown preset {name!r}. Choose from {list(PRESET_FILES)}")
    if key == "sample":
        return list(SAMPLE_SYMBOLS)
    filename = PRESET_FILES[key]
    assert filename is not None
    symbols = _read_symbol_file(UNIVERSE_DIR / filename)
    if not symbols:
        raise FileNotFoundError(f"Universe file missing or empty: {UNIVERSE_DIR / filename}")
    return symbols


def fno_symbol_set() -> set[str]:
    """Symbols currently treated as F&O-eligible (for SELL gating)."""
    try:
        return set(load_preset("nse_fno"))
    except Exception:
        return set(SAMPLE_SYMBOLS)


def list_presets() -> list[tuple[str, str, int]]:
    """Return (key, label, count) for UI."""
    rows: list[tuple[str, str, int]] = []
    for key, label in PRESET_LABELS.items():
        try:
            n = len(load_preset(key))
        except Exception:
            n = 0
        rows.append((key, f"{label} — {n} symbols", n))
    return rows


def _http_get(url: str, timeout: int = 30) -> bytes:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CPRScanner/0.1)",
        "Accept": "*/*",
        "Referer": "https://www.nseindia.com/",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def refresh_nifty_lists() -> dict[str, int]:
    """Download Nifty 50 / 500 constituent CSVs from NSE archives into universes/."""
    UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    mapping = {
        "nifty50": "https://archives.nseindia.com/content/indices/ind_nifty50list.csv",
        "nifty500": "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
    }
    counts: dict[str, int] = {}
    for key, url in mapping.items():
        raw = _http_get(url).decode("utf-8", errors="ignore")
        rows = list(csv.DictReader(io.StringIO(raw)))
        symbols = [r["Symbol"].strip().upper() for r in rows if r.get("Symbol")]
        path = UNIVERSE_DIR / f"{key}.txt"
        path.write_text("\n".join(symbols) + "\n", encoding="utf-8")
        counts[key] = len(symbols)
    return counts


def refresh_fno_list() -> int:
    """Download NSE F&O equity underlyings into universes/nse_fno.txt."""
    UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    raw = _http_get("https://www.nseindia.com/api/underlying-information?index=equities")
    payload = json.loads(raw.decode("utf-8"))
    items = payload.get("data", {}).get("UnderlyingList", [])
    symbols = sorted({str(x.get("symbol", "")).strip().upper() for x in items if x.get("symbol")})
    path = UNIVERSE_DIR / "nse_fno.txt"
    path.write_text("\n".join(symbols) + "\n", encoding="utf-8")
    return len(symbols)


def refresh_all_universes() -> dict[str, int]:
    """Refresh bundled universe files from NSE (when reachable)."""
    counts = refresh_nifty_lists()
    counts["nse_fno"] = refresh_fno_list()
    counts["sample"] = len(SAMPLE_SYMBOLS)
    return counts
