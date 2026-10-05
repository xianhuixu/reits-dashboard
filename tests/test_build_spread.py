# -*- coding: utf-8 -*-
"""产权分派率利差：与固收 PM 9-29 参考数字对照 + 分派同比 / 租金-利率口径。"""
from __future__ import annotations
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_spread as bs  # noqa: E402


class BuildSpreadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        uni = [u for u in json.loads((ROOT / "universe.json").read_text(encoding="utf-8")) if u.get("right") == "产权"]
        macro = json.loads((ROOT / "macro_series.json").read_text(encoding="utf-8"))
        cls.res = bs.compute(uni, bs.load_cache(), macro)
        cls.panel = json.loads((ROOT / "data_panel_l1l7.json").read_text(encoding="utf-8"))

    def test_pm_20260929_reference_within_tolerance(self):
        """PM 交付 9-29：53/58、TTM 4.83%、10Y 1.667%、利差 316bp、滚动3年≈95%、全样本≈96.6%。
        当前缓存可能滚到 9-30；允许一日漂移，但数量级与分派同比必须对齐。"""
        L = self.res["latest"]
        self.assertGreaterEqual(self.res["coverage"]["included"], 50)
        self.assertAlmostEqual(L["ttmYieldMcap"], 4.83, delta=0.05)
        self.assertAlmostEqual(L["spreadBp"], 316, delta=5)
        self.assertAlmostEqual(L["pctRolling3y"], 94.9, delta=2)
        self.assertAlmostEqual(L["pctFull"], 96.6, delta=2)
        self.assertGreaterEqual(L["pctFull"], L["pctRolling3y"] - 5)

    def test_dist_yoy_matches_pm(self):
        y = self.res["distYoY"]
        self.assertEqual(y["n"], 33)
        self.assertAlmostEqual(y["medianPct"], -4.16, delta=0.05)
        self.assertEqual(y["nDown"], 17)
        self.assertEqual(y["state"], "下滑")
        by = {r["sector"]: r for r in y["bySector"]}
        self.assertAlmostEqual(by["产业园"]["medianPct"], -12.8, delta=0.2)
        self.assertEqual(by["产业园"]["nDown"], 9)
        self.assertEqual(by["产业园"]["n"], 14)
        self.assertAlmostEqual(by["仓储物流"]["medianPct"], -8.1, delta=0.2)
        self.assertEqual(by["仓储物流"]["nDown"], 4)
        self.assertAlmostEqual(by["保租房"]["medianPct"], -5.0, delta=0.2)
        self.assertAlmostEqual(by["消费"]["medianPct"], 6.1, delta=0.2)

    def test_rent_vs_rate_distribution_dominates(self):
        r = self.res["rentVsRate"]
        self.assertEqual(r["status"], "ok")
        self.assertAlmostEqual(r["y10Avg1y"], 1.777, delta=0.01)
        self.assertAlmostEqual(r["y10AvgPrev1y"], 1.788, delta=0.01)
        self.assertAlmostEqual(r["rateTailwindBp"], 1.0, delta=1.5)
        self.assertAlmostEqual(r["distDragBp"], -20.0, delta=1.5)
        self.assertAlmostEqual(r["pointToPointBp"], -22.0, delta=5)
        self.assertEqual(r["dominant"], "distribution")

    def test_value_trap_and_short_history_flags(self):
        by = {r["sector"]: r for r in self.res["sectors"]}
        self.assertTrue(by["产业园"]["valueTrap"])
        self.assertTrue(by["仓储物流"]["valueTrap"])
        self.assertFalse(by["消费"]["valueTrap"])
        self.assertTrue(by["数据中心"]["shortHistory"])

    def test_panel_block_written(self):
        ps = self.panel["propertySpread"]
        self.assertIn(ps["status"], ("ok", "lagged"))
        self.assertEqual(ps["asOf"], self.res["asOf"])
        self.assertEqual(self.panel["propertyYieldSeries"][-1]["date"], ps["asOf"])

    def test_fetch_failure_marks_lagged_never_live(self):
        st, reason = bs.fetch_status({"prices": {"ok": 0, "failed": ["x"]}, "dists": {"ok": 0, "failed": ["x"]}, "units": {"ok": 0, "failed": []}}, 58)
        self.assertEqual(st, "lagged")
        self.assertIsNotNone(reason)
        st2, _ = bs.fetch_status({"prices": {"ok": 55, "failed": []}, "dists": {"ok": 55, "failed": []}, "units": {"ok": 50, "failed": []}}, 58)
        self.assertEqual(st2, "ok")


if __name__ == "__main__":
    unittest.main()
