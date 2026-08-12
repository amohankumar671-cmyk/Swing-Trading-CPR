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
from data import DEFAULT_FNO_SYMBOLS, load_universe
from scanner import run_scanner

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


@st.cache_data(ttl=300, show_spinner=False)
def _cached_scan(symbols: tuple[str, ...], period: str) -> dict[str, Any]:
    universe, index_df = load_universe(list(symbols), period=period)
    if not universe:
        return {
            "scanner_mode": "n/a",
            "index_cpr_narrow": False,
            "results": [],
            "errors": [{"symbol": "*", "error": "No symbols downloaded"}],
            "scanned": 0,
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "symbol_count": 0,
        }
    report = run_scanner(universe, index_daily_df=index_df, min_score=0.0)
    report["fetched_at"] = datetime.now().isoformat(timespec="seconds")
    report["symbol_count"] = len(universe)
    return report


def main() -> None:
    st.title("CPR Multi-Timeframe Swing Scanner")
    st.caption("Auto Yahoo Finance data · weekly CPR bias · daily CPR entry timing")

    with st.sidebar:
        st.header("Scan settings")
        default_text = ", ".join(DEFAULT_FNO_SYMBOLS)
        symbols_text = st.text_area(
            "NSE symbols (comma or newline)",
            value=default_text,
            height=140,
            help="Plain NSE tickers — .NS is added automatically",
        )
        period = st.selectbox("History period", ["1y", "2y", "5y", "max"], index=1)
        min_score = st.slider("Minimum score", 0, 100, 50, 5)
        direction = st.selectbox("Direction filter", ["ALL", "BUY", "SELL", "NONE"], index=0)

        st.header("Automation")
        auto_refresh = st.toggle("Auto-refresh", value=True)
        refresh_mins = st.slider("Refresh every (minutes)", 1, 60, 15)
        run_now = st.button("Run scan now", type="primary", use_container_width=True)
        clear_cache = st.button("Clear data cache", use_container_width=True)

        if clear_cache:
            _cached_scan.clear()
            st.success("Cache cleared")

    symbols = parse_symbols(symbols_text)
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
            st.info(
                f"Auto-refresh every {refresh_mins} min "
                "(install streamlit-autorefresh for smoother updates)."
            )

    if run_now:
        _cached_scan.clear()

    with st.spinner(f"Fetching {len(symbols)} symbols + Nifty and scanning…"):
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
        st.dataframe(watch, use_container_width=True, hide_index=True)
        st.download_button(
            "Download watchlist CSV",
            watch.to_csv(index=False).encode("utf-8"),
            file_name="cpr_watchlist.csv",
            mime="text/csv",
            disabled=watch.empty,
        )

    with tabs[1]:
        high = df[df["classification"] == "high_conviction"]
        st.dataframe(high, use_container_width=True, hide_index=True)

    with tabs[2]:
        st.dataframe(df, use_container_width=True, hide_index=True)
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
            st.dataframe(pd.DataFrame(errors), use_container_width=True, hide_index=True)
        else:
            st.write("No download/scan errors.")

    with st.expander("How automation works"):
        st.markdown(
            """
            1. Dashboard pulls daily OHLCV from **Yahoo Finance** (free).
            2. Runs `evaluate_stock` / `run_scanner` on your symbol list.
            3. Caches results for 5 minutes to avoid hammering Yahoo.
            4. With **Auto-refresh** on, the page reloads on your chosen interval and rescans.
            """
        )


if __name__ == "__main__":
    main()
