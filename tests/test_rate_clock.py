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
        self.assertIsNone(rc.growth_state(pmi([50, 51])))

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
