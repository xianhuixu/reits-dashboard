#!/usr/bin/env python3
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_track_analysis import (  # noqa: E402
    display_value,
    fund_has_expansion,
    period_kind,
    quarter_start_end,
    select_points,
    listing_status,
    applicable,
    display_sector,
    build,
)

OCC = {
    "id": "occupancy_rate",
    "caliber": "期末",
    "source_unit": "小数",
    "tax_flag": "不适用",
    "scale": 100,
}


class SelectAndCaliber(unittest.TestCase):
    def test_fund_points_only_and_null_not_zero(self):
        points = [
            {"code": "A", "asset_id": "ALL", "scope": "基金", "period": "2026Q3", "metric": "occupancy_rate", "caliber": "期末", "unit": "小数", "tax_flag": "不适用", "value": 0.7551},
            {"code": "A", "asset_id": "A02", "scope": "项目", "period": "2026Q3", "metric": "occupancy_rate", "caliber": "期末", "unit": "小数", "tax_flag": "不适用", "value": 0.9207},
            {"code": "B", "asset_id": "ALL", "scope": "基金", "period": "2026Q3", "metric": "occupancy_rate", "caliber": "期末", "unit": "小数", "tax_flag": "不适用", "value": None},
            {"code": "C", "asset_id": "ALL", "scope": "基金", "period": "2026Q3", "metric": "occupancy_rate", "caliber": "期间", "unit": "小数", "tax_flag": "不适用", "value": 0.99},
            {"code": "D", "asset_id": "ALL", "scope": "基金", "period": "2026Q3", "metric": "occupancy_rate", "caliber": "期末", "unit": "%", "tax_flag": "不适用", "value": 88},
            {"code": "E", "asset_id": "ALL", "scope": "基金", "period": "2026Q2", "metric": "occupancy_rate", "caliber": "期末", "unit": "小数", "tax_flag": "不适用", "value": 0.8},
            {"code": "F", "asset_id": "ALL", "scope": "基金", "period": "2026Q3", "metric": "occupancy_rate", "caliber": "期末", "unit": "小数", "tax_flag": "含税", "value": 0.7},
            {"code": "G", "asset_id": "ALL", "scope": "基金", "period": "2026Q3", "metric": "occupancy_rate", "caliber": "期末", "unit": "小数", "tax_flag": "不适用", "value": 0},
        ]
        got = select_points(points, OCC, "2026Q3")
        self.assertEqual([p["code"] for p in got], ["A", "G"])
        self.assertEqual(got[0]["value"], 0.7551)
        self.assertEqual(got[1]["value"], 0)
        self.assertIsNone(display_value(None, 100))
        self.assertEqual(display_value(0.7551, 100), 75.51)
        self.assertEqual(display_value(0, 100), 0)

    def test_expansion_window_is_from_start_to_end(self):
        assets = [
            {"code": "X", "include_type": "扩募", "include_date": "2026-07-15"},
            {"code": "Y", "include_type": "首发", "include_date": "2026-07-15"},
            {"code": "Z", "include_type": "扩募", "include_date": "2026-01-01"},
        ]
        start, _ = quarter_start_end("2026Q2")
        _, end = quarter_start_end("2026Q3")
        self.assertEqual((start, end), (date(2026, 4, 1), date(2026, 9, 30)))
        self.assertTrue(fund_has_expansion(assets, "X", start, end))
        self.assertFalse(fund_has_expansion(assets, "Y", start, end))
        self.assertFalse(fund_has_expansion(assets, "Z", start, end))
        self.assertEqual(period_kind("2026Q3"), "quarter")
        self.assertEqual(period_kind("2026H1"), "semi")

    def test_listing_cutoff_does_not_use_market_membership(self):
        self.assertEqual(listing_status({"list_date": "2026-09-30"}, "2026Q3"), "期末已上市")
        self.assertEqual(listing_status({"list_date": "2026-10-01"}, "2026Q3"), "期后上市")
        self.assertEqual(listing_status({"list_date": None, "status": "已获批未上市"}, "2026Q3"), "未上市")
        self.assertEqual(listing_status({"list_date": None, "status": "存续"}, "2026Q3"), "上市日待核")
        self.assertTrue(applicable({"sector_l1": "消费"}, OCC))
        self.assertFalse(applicable({"sector_l1": "能源"}, OCC))
        self.assertEqual(display_sector("供热", "市政环保"), "供热")


class GeneratedPack(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = json.loads((ROOT / "research" / "track-analysis.json").read_text(encoding="utf-8"))
        cls.fresh = build(ROOT)

    def test_reproducible_and_self_check(self):
        self.assertEqual(self.pack["schemaVersion"], self.fresh["schemaVersion"])
        self.assertEqual(self.pack["latestPeriod"], "2026Q3")
        self.assertEqual(self.pack["selfCheck"], self.fresh["selfCheck"])
        self.assertEqual(self.fresh["selfCheck"]["hedaFundOccupancy"], 0.7551)
        self.assertEqual(self.fresh["selfCheck"]["hedaProjectOccupancies"], [0.6378, 0.9107, 0.9207])
        self.assertNotIn("yoy", self.fresh)
        notes = "\n".join(self.fresh["sourceNotes"])
        self.assertIn("不把中位数升降写成改善/恶化", notes)
        self.assertIn("基金等权、非面积加权", notes)
        self.assertIn("不绘制同比", notes)

    def test_consumption_changing_vs_fixed_sample(self):
        trend = self.fresh["trend"]["occupancy_rate"]
        xf = next(s for s in trend["sectors"] if s["sector"] == "消费")
        q2 = next(p for p in xf["points"] if p["period"] == "2026Q2")
        q3 = next(p for p in xf["points"] if p["period"] == "2026Q3")
        self.assertEqual(q2["n"], 12)
        self.assertEqual(q3["n"], 13)
        pair = next(p for p in xf["fixedPairs"] if p["from"] == "2026Q2" and p["to"] == "2026Q3")
        self.assertEqual((pair["n"], pair["nUp"], pair["nDown"], pair["nFlat"], pair["excludedExpansion"]), (12, 7, 4, 1, 0))
        self.assertIn("不是同店改善", pair["note"])
        self.assertIn("不代表经营改善或恶化", trend["sampleNote"])

    def test_period_end_denominator_excludes_unlisted_and_post_period_listings(self):
        ops = json.loads((ROOT / "research" / "operating-data.json").read_text())
        by_code = {f["code"]: f for f in ops["funds"]}
        occ = self.fresh["latest"]["occupancy_rate"]
        exclusions = {f["code"]: f["reason"] for f in occ["excludedListing"]}
        for code in ["181002.SZ", "508605.SH", "508606.SH", "508610.SH"]:
            self.assertEqual(exclusions[code], "未上市")
            self.assertIsNone(by_code[code]["list_date"])
        for code in ["508607.SH", "508609.SH"]:
            self.assertEqual(exclusions[code], "期后上市")
        market_codes = {r["code"] for r in json.loads((ROOT / "data.json").read_text())["reits"]}
        self.assertNotIn("181001.SZ", market_codes)
        self.assertNotIn("508607.SH", market_codes)
        self.assertEqual(by_code["181001.SZ"]["list_date"], "2026-09-03")
        self.assertEqual(by_code["508607.SH"]["list_date"], "2026-11-04")
        self.assertEqual(by_code["508609.SH"]["list_date"], "2026-10-30")
        rows = {s["sector"]: s for s in occ["sectors"]}
        self.assertEqual((rows["消费"]["n"], rows["消费"]["universe"], rows["消费"]["undisclosed"]), (13, 13, 0))
        self.assertEqual((rows["商业不动产"]["n"], rows["商业不动产"]["universe"]), (4, 4))
        self.assertIn("181001.SZ", [f["code"] for f in rows["消费"]["funds"]])
        self.assertEqual(sum(s["n"] for s in occ["sectors"] if s["sector"] in ["消费", "商业不动产"]), 17)
        for metric in self.fresh["metrics"]:
            pack = self.fresh["latest"][metric["id"]]
            for sector in pack["sectors"]:
                expected = [f for f in ops["funds"] if applicable(f, metric)
                            and listing_status(f, "2026Q3") == "期末已上市"
                            and display_sector(f["sector_l1"], next((r["sector"] for r in json.loads((ROOT / "data.json").read_text())["reits"] if r["code"] == f["code"]), None)) == sector["sector"]]
                self.assertEqual(sector["universe"], len(expected))
                self.assertEqual(sector["n"] + sector["undisclosed"], sector["universe"])
                self.assertTrue(set(sector["undisclosedCodes"]).isdisjoint(exclusions))
            for sector in self.fresh["trend"][metric["id"]]["sectors"]:
                self.assertNotEqual(sector["sector"], "能源")
                for point in sector["points"]:
                    for code in point["codes"]:
                        self.assertEqual(listing_status(by_code[code], point["period"]), "期末已上市")
            for sector in pack["sectors"]:
                if sector["sector"] == "能源":
                    self.assertTrue(sector["pointOnly"])
                    self.assertIsNone(sector["median"])
                    self.assertIsNone(sector["medianDisplay"])
                    self.assertIsNone(sector["min"])
                    self.assertIsNone(sector["max"])
                    self.assertEqual([f["code"] for f in sector["funds"]], sorted(f["code"] for f in sector["funds"]))


if __name__ == "__main__":
    unittest.main()
