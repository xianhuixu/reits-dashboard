"""rateClock / rateRentGate 纯函数回归（合成夹具，不联网）。"""
import unittest
from datetime import date, timedelta

import rate_clock as rc


def daily(values, start=date(2024, 1, 1)):
    out, d = [], start
    for v in values:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        out.append({"date": d.isoformat(), "value": v})
        d += timedelta(days=1)
    return out


def pmi(vals, start_year=2023, start_month=1):
    out = []
    y, m = start_year, start_month
    for v in vals:
        out.append({"month": f"{y}-{m:02d}", "value": v})
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


class RateClockTests(unittest.TestCase):
    def test_direction_dead_band(self):
        self.assertEqual(rc.rate_direction(12)[0], "up")
        self.assertEqual(rc.rate_direction(-10)[0], "down")
        d, band, lean = rc.rate_direction(-5.9)
        self.assertEqual((d, band, lean), ("flat", True, "down"))
        self.assertEqual(rc.rate_direction(0)[2], None)
        self.assertEqual(rc.rate_direction(None), (None, False, None))

    def test_growth_state_uses_3m_avg_and_trend(self):
        g = rc.growth_state(pmi([50.3, 50.0, 50.3, 50.3, 49.2, 49.8]))
        self.assertEqual(g["pmi3m"], 49.77)
        self.assertEqual(g["level"], "弱")
        self.assertEqual(g["trend"], "下行")
        self.assertTrue(g["boundary"])                     # 49.77 ∈ [49.5, 50.5]
        self.assertEqual(g["levelLabel"], "边界")
        self.assertIn("边界", g["boundaryNote"])
        self.assertIsNone(rc.growth_state(pmi([50, 51])))

    def test_growth_boundary_band_edges(self):
        self.assertTrue(rc.growth_state(pmi([49.5] * 6))["boundary"])
        self.assertTrue(rc.growth_state(pmi([50.5] * 6))["boundary"])
        self.assertFalse(rc.growth_state(pmi([49.4] * 6))["boundary"])
        self.assertFalse(rc.growth_state(pmi([50.6] * 6))["boundary"])
        self.assertEqual(rc.growth_state(pmi([49.4] * 6))["levelLabel"], "弱")

    def test_dead_band_is_transitional_not_forced_quadrant(self):
        flat_down = daily([1.80 - i * 0.001 for i in range(200)])  # 60 日 −6bp
        weak = pmi([50.5] * 18 + [49.6, 49.5, 49.3, 49.2, 49.1, 49.0])  # 3M 49.1，非边界
        c = rc.compute_rate_clock(flat_down, weak, today="2024-12-31")
        self.assertEqual(c["state"], "transitional")
        self.assertEqual(c["stateLabel"], "利率走平·过渡期")
        self.assertIsNone(c["quadrant"])
        self.assertIsNone(c["usPriorAnnualReturn"])
        self.assertEqual(c["rateDir"], "flat")
        self.assertEqual(c["confidence"], "低")
        self.assertEqual((c["leanQuadrant"], c["leanUsPriorAnnualReturn"]), ("Q3", 3.5))
        self.assertAlmostEqual(c["d10y60bp"], -6.0, places=1)
        flat_up = daily([1.60 + i * 0.001 for i in range(200)])
        self.assertEqual(rc.compute_rate_clock(flat_up, weak)["leanQuadrant"], "Q4")
        self.assertEqual(rc.compute_rate_clock(daily([1.7] * 200), weak)["leanQuadrant"], None)

    def test_history_marks_transitional_months_distinctly(self):
        # 前段快速下行（确定 Q3），后段横盘（过渡期）
        vals = [2.2 - i * 0.004 for i in range(150)] + [1.604 - i * 0.0005 for i in range(150)]
        weak = pmi([49.0] * 24)
        c = rc.compute_rate_clock(daily(vals), weak)
        states = {h["state"] for h in c["history"]}
        self.assertEqual(states, {"definite", "transitional"})
        for h in c["history"]:
            if h["state"] == "transitional":
                self.assertIsNone(h["quadrant"])
                self.assertEqual(h["stateLabel"], "利率走平·过渡期")
                self.assertTrue(abs(h["d10y60bp"]) < 10)
            else:
                self.assertEqual(h["quadrant"], "Q3")
        rot = c["rotation"]
        self.assertEqual(rot["lastDefiniteMonth"], max(h["month"] for h in c["history"] if h["state"] == "definite"))
        self.assertGreater(rot["transitionalMonthsSince"], 0)

    def test_growth_boundary_lowers_confidence_but_keeps_definite_quadrant(self):
        falling = daily([2.0 - i * 0.004 for i in range(200)])
        c = rc.compute_rate_clock(falling, pmi([50.0] * 18 + [49.9, 49.8, 49.8, 49.7, 49.7, 49.6]))
        self.assertEqual((c["state"], c["quadrant"]), ("definite", "Q3"))
        self.assertTrue(c["growth"]["boundary"])
        self.assertEqual(c["confidence"], "中低")
        self.assertIn("边界", c["confidenceNote"])

    def test_quadrants_and_q4_split(self):
        self.assertEqual(rc.quadrant_of("强", "up"), "Q1")
        self.assertEqual(rc.quadrant_of("强", "down"), "Q2")
        self.assertEqual(rc.quadrant_of("弱", "down"), "Q3")
        self.assertEqual(rc.quadrant_of("弱", "up"), "Q4")
        self.assertIsNone(rc.quadrant_of("弱", "flat"))
        self.assertEqual(rc.sub_state("Q4", "下行"), "滞胀")
        self.assertEqual(rc.sub_state("Q4", "上行"), "复苏")

    def test_rotation(self):
        h = [{"quadrant": q} for q in ("Q1", "Q1", "Q4")]
        self.assertEqual(rc.rotation_of(h)["direction"], "顺时针")
        h = [{"quadrant": q} for q in ("Q1", "Q2")]
        self.assertTrue(rc.rotation_of(h)["direction"].startswith("逆时针"))
        self.assertEqual(rc.rotation_of([{"quadrant": "Q3"}])["direction"], "未切换")
        h = [{"month": "2025-01", "quadrant": "Q3", "state": "definite"}, {"month": "2025-02", "quadrant": None, "state": "transitional"},
             {"month": "2025-03", "quadrant": "Q4", "state": "definite"}, {"month": "2025-04", "quadrant": None, "state": "transitional"}]
        r = rc.rotation_of(h)
        self.assertEqual((r["from"], r["to"], r["switchMonth"], r["lastDefiniteMonth"], r["transitionalMonthsSince"]), ("Q3", "Q4", "2025-03", "2025-03", 1))

    def test_compute_rate_clock_q3_and_q4_stagflation_prior(self):
        falling = daily([2.0 - i * 0.004 for i in range(200)])  # −0.4bp/日 → 60 日 −24bp
        weak_down = pmi([50.5] * 18 + [50.2, 50.0, 49.9, 49.6, 49.4, 49.3])
        c = rc.compute_rate_clock(falling, weak_down, today="2024-12-31")
        self.assertEqual(c["status"], "ok")
        self.assertEqual(c["rateDir"], "down")
        self.assertEqual(c["quadrant"], "Q3")
        self.assertEqual(c["usPriorAnnualReturn"], 3.5)
        self.assertEqual(c["confidence"], "中")
        self.assertTrue(c["history"])
        rising = daily([1.6 + i * 0.004 for i in range(200)])
        c2 = rc.compute_rate_clock(rising, weak_down)
        self.assertEqual((c2["quadrant"], c2["subState"], c2["usPriorAnnualReturn"]), ("Q4", "滞胀", -10.7))

    def test_unavailable_never_fabricates(self):
        old = {"history": [{"month": "2024-01", "quadrant": "Q2"}], "asOf": "2024-01-31"}
        c = rc.compute_rate_clock([], [], old_block=old)
        self.assertEqual(c["status"], "unavailable")
        self.assertIsNone(c["quadrant"])
        self.assertEqual(c["history"], old["history"])

    def test_conflict_flags_consumer_q3(self):
        advice = {
            "sectorViews": [{"sector": "消费", "action": "标配偏超配"}, {"sector": "产业园", "action": "观望/弱低配"},
                            {"sector": "仓储物流", "action": "观望/弱低配"}],
            "clockSectorPrior": [
                {"sector": "消费", "usAnalog": "购物中心", "best": ["Q4", "Q2"], "danger": ["Q3"]},
                {"sector": "产业园", "usAnalog": "办公", "best": ["Q2"], "danger": ["Q3", "Q4"]},
                {"sector": "仓储物流", "usAnalog": "工业", "best": ["Q3"], "danger": ["Q4-stagflation"]},
            ],
            "horizons": {"monthly": {"stance": "底部区域配置"}},
        }
        clock = {"status": "ok", "quadrant": "Q3", "quadrantName": "衰退", "subState": "衰退", "usPriorAnnualReturn": 3.5}
        flags = rc.conflict_flags(clock, advice)
        conflicts = [f for f in flags if f["level"] == "conflict"]
        self.assertEqual([f["sector"] for f in conflicts], ["消费"])
        self.assertTrue(any(f["level"] == "watch" and f["sector"] == "仓储物流" for f in flags))
        self.assertTrue(any(f["level"] == "background" for f in flags))
        self.assertEqual(rc.conflict_flags({"status": "unavailable"}, advice), [])
        # 过渡期：按最近象限推演，但只出「参考」软提示，不出硬冲突
        trans = {"status": "ok", "state": "transitional", "quadrant": None, "leanQuadrant": "Q3", "leanSubState": "衰退",
                 "leanQuadrantName": "衰退", "leanUsPriorAnnualReturn": 3.5, "d10y60bp": -5.9, "growth": {"boundary": True}}
        soft = rc.conflict_flags(trans, advice)
        self.assertTrue(soft)
        self.assertEqual({f["level"] for f in soft}, {"reference"})
        self.assertTrue(all(f["text"].startswith("参考·利率走平·过渡期") for f in soft))
        self.assertIn("消费", [f["sector"] for f in soft])
        self.assertTrue(any("增长处边界带" in f["text"] for f in soft))

    def test_stagflation_zone_matches_only_q4_stagflation(self):
        self.assertTrue(rc._in_zone(["Q4-stagflation"], "Q4", "滞胀"))
        self.assertFalse(rc._in_zone(["Q4-stagflation"], "Q4", "复苏"))


class RateRentGateTests(unittest.TestCase):
    def test_rate_leg_not_met_is_not_triggered_even_if_spread_pending(self):
        g = rc.rate_rent_gate(daily([1.7] * 100), {"seedMeta": {"liveFetch": False}})
        self.assertEqual(g["status"], "not_triggered")
        self.assertEqual(g["spreadLeg"]["status"], "pending data")
        self.assertEqual(g["dataStatus"], "partial")

    def test_rate_leg_met_but_seed_spread_is_pending(self):
        g = rc.rate_rent_gate(daily([1.6 + i * 0.006 for i in range(100)]), {"seedMeta": {"liveFetch": False}})
        self.assertTrue(g["rateLeg"]["met"])
        self.assertEqual(g["status"], "pending data")

    def test_triggered_with_live_spread(self):
        rows = [{"date": (date(2024, 1, 1) + timedelta(days=i)).isoformat(), "pctile": 0.9 - i * 0.003} for i in range(120)]
        panel = {"seedMeta": {"liveFetch": True}, "propertyYieldSeries": rows}
        g = rc.rate_rent_gate(daily([1.6 + i * 0.006 for i in range(100)]), panel)
        self.assertEqual(g["status"], "triggered")
        self.assertEqual(g["effectsIfTriggered"]["gate"], "valuation")

    def test_missing_series_pending(self):
        self.assertEqual(rc.rate_rent_gate([], None)["status"], "pending data")


if __name__ == "__main__":
    unittest.main()
