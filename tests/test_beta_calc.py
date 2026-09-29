"""Beta 计算回归：合成夹具（非真实行情），验证估计、相对分类、不一致标记与 pending 状态。"""
import unittest

import numpy as np
import pandas as pd

import beta_calc as bc


def fixture(weeks=130, seed=7):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2023-01-02", periods=weeks * 5)
    eq = rng.normal(0, 0.012, len(days))
    bond = rng.normal(0, 0.0015, len(days))
    dy = -bond * 400 + rng.normal(0, 0.2, len(days))  # bp/日，与国债指数反向
    noise = lambda s: rng.normal(0, s, len(days))  # noqa: E731
    rets = {
        "A.SH": 0.6 * eq + noise(0.004),              # 偏股
        "B.SH": 0.5 * eq + noise(0.004),              # 偏股
        "C.SH": 0.05 * eq + 2.0 * bond + noise(0.002),  # 偏债
        "D.SH": 0.02 * eq + 2.5 * bond + noise(0.002),  # 偏债
        "E.SH": 0.25 * eq + 1.0 * bond + noise(0.003),
        "F.SH": 0.3 * eq + 0.8 * bond + noise(0.003),
    }
    close = pd.DataFrame({k: 100 * np.cumprod(1 + v) for k, v in rets.items()}, index=days)
    bench = pd.DataFrame({"000300.SH": 4000 * np.cumprod(1 + eq), "000012.SH": 200 * np.cumprod(1 + bond)}, index=days)
    y10 = pd.Series(2.0 + np.cumsum(dy) / 100, index=days)
    uni = [
        {"code": "A.SH", "name": "A", "sector": "产业园", "strategy": "周期型"},
        {"code": "B.SH", "name": "B", "sector": "产业园", "strategy": "防御型"},   # 人工防御 vs 量化偏股 → 不一致
        {"code": "C.SH", "name": "C", "sector": "保租房", "strategy": "防御型"},
        {"code": "D.SH", "name": "D", "sector": "保租房", "strategy": "周期型"},   # 人工周期 vs 量化偏债 → 不一致
        {"code": "E.SH", "name": "E", "sector": "能源", "strategy": "防御型"},
        {"code": "F.SH", "name": "F", "sector": "能源", "strategy": "周期型"},
    ]
    return close, bench, y10, uni


class BetaTests(unittest.TestCase):
    def test_ols_beta_recovers_slope(self):
        x = pd.Series(np.linspace(-1, 1, 60))
        b, n = bc.ols_beta(0.7 * x + 0.1, x)
        self.assertAlmostEqual(b, 0.7, places=6)
        self.assertEqual(n, 60)
        self.assertEqual(bc.ols_beta(x.head(10), x.head(10))[0], None)

    def test_compute_betas_classes_and_disagreements(self):
        close, bench, y10, uni = fixture()
        out = bc.compute_betas(close, bench, uni, y10=y10)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["window"], 104)
        self.assertLessEqual(out["weeksAvailable"], 104)
        r = {x["code"]: x for x in out["byReit"]}
        self.assertGreater(r["A.SH"]["betaEq"], 0.4)
        self.assertGreater(r["C.SH"]["betaBond"], 1.0)
        self.assertEqual(r["A.SH"]["cls"], "偏股")
        self.assertEqual(r["D.SH"]["cls"], "偏债")
        self.assertIn("B.SH", out["disagreements"])
        self.assertIn("D.SH", out["disagreements"])
        self.assertNotIn("A.SH", out["disagreements"])
        # 偏债券对 10Y 上行更敏感（负值更大）
        self.assertLess(r["D.SH"]["sens10y"], r["A.SH"]["sens10y"])
        self.assertEqual({s["sector"] for s in out["bySector"]}, {"产业园", "保租房", "能源"})
        self.assertTrue(out["rolling"]["dates"])
        self.assertEqual(len(out["rolling"]["dates"]), len(out["rolling"]["bySector"]["保租房"]["betaEq"]))

    def test_relative_ranking_not_absolute_cutoff(self):
        close, bench, y10, uni = fixture()
        out = bc.compute_betas(close, bench, uni, y10=y10)
        self.assertTrue(all((x["betaEq"] or 0) < 1 for x in out["byReit"]))
        self.assertTrue(any(x["cls"] == "偏股" for x in out["byReit"]))  # 全部 <1 仍有偏股

    def test_pending_states(self):
        close, bench, y10, uni = fixture()
        self.assertEqual(bc.compute_betas(close, None, uni)["status"], "pending")
        self.assertEqual(bc.compute_betas(close, bench[["000300.SH"]], uni)["status"], "pending")
        self.assertEqual(bc.compute_betas(close.tail(50), bench.tail(50), uni)["status"], "pending")
        out = bc.compute_betas(close, bench, uni, y10=None)
        self.assertEqual(out["status"], "ok")
        self.assertTrue(all(x["sens10y"] is None for x in out["byReit"]))
        self.assertTrue(out["sens10yStatus"].startswith("pending"))

    def test_y10_from_macro(self):
        self.assertIsNone(bc.y10_series_from_macro({}))
        s = bc.y10_series_from_macro({"cgb10y": {"series": [{"date": "2026-01-02", "value": 1.8}]}})
        self.assertEqual(float(s.iloc[0]), 1.8)


if __name__ == "__main__":
    unittest.main()
