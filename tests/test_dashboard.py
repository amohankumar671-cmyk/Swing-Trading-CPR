"""Unit helpers used by the dashboard."""

from dashboard_utils import parse_symbols, results_frame


def test_parse_symbols():
    assert parse_symbols("reliance, tcs\ninfy") == ["RELIANCE", "TCS", "INFY"]
    assert parse_symbols("  ") == []


def test_results_frame_filters():
    rows = [
        {
            "symbol": "A",
            "direction": "BUY",
            "score": 80,
            "classification": "high_conviction",
            "entry_status": "confirmed",
        },
        {
            "symbol": "B",
            "direction": "SELL",
            "score": 40,
            "classification": "no_signal",
            "entry_status": "n/a",
        },
    ]
    df = results_frame(rows, min_score=50, direction="BUY")
    assert list(df["symbol"]) == ["A"]
    assert df.iloc[0]["score"] == 80
