"""Tests for universe presets."""

from universe import PRESET_LABELS, fno_symbol_set, list_presets, load_preset


def test_load_sample_preset():
    symbols = load_preset("sample")
    assert "RELIANCE" in symbols
    assert len(symbols) == 10


def test_load_fno_preset():
    symbols = load_preset("nse_fno")
    assert len(symbols) >= 150
    assert "RELIANCE" in symbols
    assert "TCS" in symbols


def test_load_nifty_presets():
    n50 = load_preset("nifty50")
    n500 = load_preset("nifty500")
    assert len(n50) >= 45
    assert len(n500) >= 450
    assert set(n50).issubset(set(n500)) or len(set(n50) & set(n500)) > 40


def test_list_presets_and_fno_set():
    rows = list_presets()
    assert {r[0] for r in rows} == set(PRESET_LABELS)
    fno = fno_symbol_set()
    assert "INFY" in fno
