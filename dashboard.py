"""
CPR Multi-Timeframe Swing Scanner — Streamlit dashboard.

Auto-fetches Yahoo Finance OHLCV, runs the scanner, and refreshes on a timer.
No broker API required.

Run:
    streamlit run dashboard.py
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from dashboard_utils import parse_symbols, results_frame
from data import load_universe
from scanner import run_scanner
from universe import PRESET_LABELS, list_presets, load_preset, refresh_all_universes

try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:  # pragma: no cover
    st_autorefresh = None

st.set_page_config(
    page_title="CPR Swing Scanner",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(ttl=600, show_spinner=False)
def _cached_scan(symbols: tuple[str, ...], period: str) -> dict[str, Any]:
    universe, index_df, warnings = load_universe(list(symbols), period=period)
    if not universe:
        return {
            "scanner_mode": "n/a",
            "index_cpr_narrow": False,
            "results": [],
            "errors": [{"symbol": "*", "error": w} for w in warnings]
            or [{"symbol": "*", "error": "No symbols downloaded"}],
            "scanned": 0,
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "symbol_count": 0,
        }
    report = run_scanner(universe, index_daily_df=index_df, min_score=0.0)
    report["fetched_at"] = datetime.now().isoformat(timespec="seconds")
    report["symbol_count"] = len(universe)
    # Merge download warnings into errors tab
    existing = report.get("errors") or []
    report["errors"] = existing + [{"symbol": "*", "error": w} for w in warnings]
    return report


def main() -> None:
    st.title("CPR Multi-Timeframe Swing Scanner")
    st.caption("Auto Yahoo Finance data · weekly CPR bias · daily CPR entry timing")

    presets = list_presets()
    preset_options = {label: key for key, label, _ in presets}

    with st.sidebar:
        st.header("Universe")
        preset_keys = [key for key, _, _ in presets]
        default_idx = preset_keys.index("nse_fno") if "nse_fno" in preset_keys else 0
        preset_label = st.selectbox(
            "Scan universe",
            options=list(preset_options.keys()),
            index=default_idx,
            help="NSE F&O is recommended. Nifty 500 is slower on free Yahoo Finance.",
        )
        preset_key = preset_options[preset_label]
        preset_symbols = load_preset(preset_key)
        st.caption(f"{len(preset_symbols)} symbols in preset")

        custom_mode = st.toggle("Custom symbol list", value=False)
        if custom_mode:
            symbols_text = st.text_area(
                "NSE symbols (comma or newline)",
                value=", ".join(preset_symbols[:10]),
                height=140,
                help="Plain NSE tickers — .NS is added automatically",
            )
            symbols = parse_symbols(symbols_text)
        else:
            symbols = preset_symbols
            st.text_area(
                "Preset symbols (read-only preview)",
                value=", ".join(symbols[:40]) + (" ..." if len(symbols) > 40 else ""),
                height=100,
                disabled=True,
            )

        if st.button("Refresh lists from NSE", width="stretch"):
            try:
                counts = refresh_all_universes()
                st.success(f"Updated: {counts}")
                st.cache_data.clear()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Refresh failed (using bundled lists): {exc}")

        st.header("Scan settings")
        period = st.selectbox("History period", ["1y", "2y", "5y", "max"], index=1)
        min_score = st.slider("Minimum score", 0, 100, 50, 5)
        direction = st.selectbox("Direction filter", ["ALL", "BUY", "SELL", "NONE"], index=0)

        st.header("Automation")
        auto_refresh = st.toggle("Auto-refresh", value=False)
        refresh_mins = st.slider("Refresh every (minutes)", 1, 60, 15)
        run_now = st.button("Run scan now", type="primary", width="stretch")
        clear_cache = st.button("Clear data cache", width="stretch")

        if clear_cache:
            _cached_scan.clear()
            st.success("Cache cleared")

        if len(symbols) >= 100:
            st.info(
                f"Large universe ({len(symbols)}). First run may take several minutes "
                "on free Yahoo Finance."
            )

    if not symbols:
        st.warning("Add at least one NSE symbol in the sidebar.")
        return

    if auto_refresh:
        if st_autorefresh is not None:
            st_autorefresh(interval=refresh_mins * 60 * 1000, key="cpr_auto_refresh")
        else:
            st.markdown(
                f"<meta http-equiv='refresh' content='{refresh_mins * 60}'>",
                unsafe_allow_html=True,
            )

    if run_now:
        _cached_scan.clear()

    with st.spinner(
        f"Fetching {len(symbols)} symbols ({PRESET_LABELS.get(preset_key, preset_key)}) "
        f"+ Nifty and scanning…"
    ):
        report = _cached_scan(tuple(symbols), period)

    mode = report.get("scanner_mode", "n/a")
    narrow = report.get("index_cpr_narrow", False)
    fetched_at = report.get("fetched_at", "")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Scanner mode", str(mode))
    c2.metric("Index CPR narrow", "Yes" if narrow else "No")
    c3.metric("Symbols scanned", report.get("symbol_count", report.get("scanned", 0)))
    c4.metric("Last update", fetched_at)

    if mode == "high_priority":
        st.success(
            "Market regime: high_priority — index weekly CPR is narrow; favor breakout setups."
        )
    elif mode == "normal":
        st.warning(
            "Market regime: normal — still scan, but treat new entries more cautiously."
        )

    df = results_frame(report.get("results", []), min_score=min_score, direction=direction)

    tabs = st.tabs(["Watchlist", "High conviction", "All rows", "Errors"])

    with tabs[0]:
        watch = df[df["classification"].isin(["watchlist", "high_conviction"])]
        st.dataframe(watch, width="stretch", hide_index=True)
        st.download_button(
            "Download watchlist CSV",
            watch.to_csv(index=False).encode("utf-8"),
            file_name="cpr_watchlist.csv",
            mime="text/csv",
            disabled=watch.empty,
        )

    with tabs[1]:
        high = df[df["classification"] == "high_conviction"]
        st.dataframe(high, width="stretch", hide_index=True)

    with tabs[2]:
        st.dataframe(df, width="stretch", hide_index=True)
        st.download_button(
            "Download full CSV",
            df.to_csv(index=False).encode("utf-8"),
            file_name="cpr_scan_results.csv",
            mime="text/csv",
            disabled=df.empty,
        )

    with tabs[3]:
        errors = report.get("errors") or []
        if errors:
            st.dataframe(pd.DataFrame(errors), width="stretch", hide_index=True)
        else:
            st.write("No download/scan errors.")

    with st.expander("How automation works"):
        st.markdown(
            """
            1. Choose a universe: **Sample**, **Nifty 50**, **NSE F&O (full)**, or **Nifty 500**.
            2. Dashboard pulls daily OHLCV from **Yahoo Finance** in batches (free).
            3. Runs the CPR scanner and ranks results.
            4. Cache lasts ~10 minutes. Use **Run scan now** to force a refresh.
            5. **NSE F&O** is the intended universe for this strategy (SELL needs F&O).
            """
        )


if __name__ == "__main__":
    main()
