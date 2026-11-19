"""Regression: missing equity/bond benchmarks must not crash daily scoring."""
import pandas as pd

from fetch_data_em import score_signals


def test_score_signals_accepts_missing_bench_ret():
    idx = pd.date_range("2026-01-01", periods=30, freq="B")
    corr_ret = pd.DataFrame({"508000.SH": 0.001}, index=idx)
    reits = [{"code": "508000.SH", "amt20": None, "rsi14": None, "amtRatio": None}]
    out = score_signals(reits, fund=None, corr_ret=corr_ret, bench_ret=None, bond10y=None)
    assert out[0]["signals"]["stockbond"] == 0
    assert out[0]["signals"]["label"] == "中性"
