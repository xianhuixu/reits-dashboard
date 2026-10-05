# -*- coding: utf-8 -*-
"""经营权披露 IRR（2025 年末口径）。"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import build_oper_irr as bo  # noqa: E402
import cgb_curve as cc  # noqa: E402


class BuildOperIrrTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.curve = bo.load_curve()
        cls.panel = json.loads((ROOT / "data_panel_l1l7.json").read_text(encoding="utf-8"))
        cls.block = cls.panel["operatingDisclosedIrr"]

    def test_curve_is_ye2025_not_sep29(self):
        self.assertEqual(self.curve["asOf"], "2025-12-31")
        pts = {t: y for t, y in self.curve["points"]}
        self.assertAlmostEqual(pts[10], 1.8473, places=3)
        self.assertNotEqual(self.curve["asOf"], "2026-09-29")

    def test_primary_uses_disclosed_not_self_calc(self):
        for r in self.block["items"]:
            self.assertIsNotNone(r["irrDisclosedPct"])
            self.assertIn("spreadBp", r)
            # self-calc may exist but must not be the spread basis
            if r.get("selfIrrPct") is not None:
                self.assertEqual(r.get("selfIrrNote"), "对账偏高，中位约 280bp")

    def test_coverage_and_pending(self):
        cov = self.block["coverage"]
        self.assertEqual(cov["universe"], 30)
        self.assertEqual(cov["disclosed"] + cov["pending"], 30)
        self.assertGreaterEqual(cov["disclosed"], 21)
        self.assertGreaterEqual(cov["withWal"], 21)
        self.assertEqual(len(self.block["pending"]), cov["pending"])
        for r in self.block["pending"]:
            self.assertEqual(r.get("reason"), "暂无披露")

    def test_term_match_uses_cgb_curve_helper(self):
        sample = next(r for r in self.block["items"] if r["code"] == "180201.SZ")
        tm = cc.term_matched_spread(sample["irrDisclosedPct"], sample["tenorYears"], self.curve["points"])
        self.assertAlmostEqual(sample["matchedYieldPct"], tm["matchedYield"], places=4)
        self.assertAlmostEqual(sample["spreadBp"], round(tm["spread"] * 100, 1), places=1)

    def test_price_change_and_highway(self):
        s = self.block["summary"]
        self.assertIsNotNone(s["priceChangeMedianPct"])
        self.assertLess(s["priceChangeMedianPct"], 0)
        self.assertAlmostEqual(s["priceChangeMedianPct"], -8.45, delta=2.0)
        self.assertLess(s["highwayPriceChangeMedianPct"], -5)

    def test_no_banner_feed_no_sector_mean(self):
        s = self.block["summary"]
        self.assertFalse(s["feedsBanner"])
        self.assertTrue(s["noSectorAverage"])
        self.assertTrue(s["noSpreadSort"])
        for sec in self.block["sectors"]:
            self.assertIsNone(sec["aggregate"])
            self.assertIn("口径不统一", sec["aggregateNote"])

    def test_extreme_180402(self):
        row = next(r for r in self.block["items"] if r["code"] == "180402.SZ")
        self.assertTrue(row["extreme"])
        self.assertLess(row["spreadBp"], -400)

    def test_panel_schema_and_seed_meta(self):
        self.assertEqual(self.block["label"], "2025 年末口径")
        self.assertIn("operatingDisclosedIrr", self.panel)
        self.assertTrue(self.panel["seedMeta"].get("operatingDisclosedLive"))
        self.assertIn("披露 IRR", self.panel["note"])
        # 月度时序仍在，但横幅/时钟不读本块
        self.assertTrue(self.panel.get("operatingIrrSeries"))


if __name__ == "__main__":
    unittest.main()
