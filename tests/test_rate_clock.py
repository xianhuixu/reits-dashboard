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


def monthly_pmi_wave(n=120, start_year=2016):
    """合成 PMI：50 附近正弦 + 小扰动（仅测试夹具，不作为数据）。"""
    import math
    return pmi([round(50 + 1.2 * math.sin(i / 7.0) + 0.3 * math.sin(i / 2.3), 2) for i in range(n)], start_year, 1)


class RateAxisTests(unittest.TestCase):
    def test_thresholds_floor_and_sigma(self):
        self.assertEqual(rc.rate_thresholds(6.9), (5.0, 2.5))          # 0.7×6.9=4.83 → 触底 5bp，退出 2.5bp
        t, e = rc.rate_thresholds(17.2)
        self.assertAlmostEqual(t, 12.04)
        self.assertAlmostEqual(e, 6.02)
        self.assertEqual(rc.rate_thresholds(None), (None, None))

    def test_raw_state_hysteresis(self):
        T, E = 10.0, 5.0
        self.assertEqual(rc.rate_raw_state(0, 9.9, T, E), 0)         # 未过进入线
        self.assertEqual(rc.rate_raw_state(0, 10.1, T, E), 1)
        self.assertEqual(rc.rate_raw_state(0, -10.1, T, E), -1)
        self.assertEqual(rc.rate_raw_state(1, 6.0, T, E), 1)         # 上行中仍在退出线之上 → 保持
        self.assertEqual(rc.rate_raw_state(1, 4.9, T, E), 0)         # 跌破退出线 → 走平
        self.assertEqual(rc.rate_raw_state(-1, -5.1, T, E), -1)
        self.assertEqual(rc.rate_raw_state(-1, -4.9, T, E), 0)
        self.assertEqual(rc.rate_raw_state(-1, 10.5, T, E), 1)       # 直接反向越过进入线

    def test_step_requires_five_consecutive_days(self):
        T, E = 5.0, 2.5
        cur, cnt = 0, 0
        for day in range(4):
            cur, cnt, raw = rc.rate_step(cur, cnt, -7.0, T, E)
            self.assertEqual((cur, raw, cnt), (0, -1, day + 1))
        cur, cnt, raw = rc.rate_step(cur, cnt, -7.0, T, E)
        self.assertEqual((cur, cnt), (-1, 0))                        # 第 5 日切换
        # 中断一天则计数清零
        cur, cnt = 0, 0
        for d in (-7, -7, -7, -4, -7, -7, -7, -7):
            cur, cnt, _ = rc.rate_step(cur, cnt, d, T, E)
        self.assertEqual((cur, cnt), (0, 4))

    def test_path_uses_rolling_sigma_and_confirms(self):
        # 400 个交易日横盘微波动 → 之后快速下行：应在越线后第 5 个交易日切到下行
        import math
        vals = [2.0 + 0.0005 * math.sin(i / 3) for i in range(400)] + [2.0 - 0.002 * i for i in range(1, 80)]
        path = rc.rate_state_path(daily(vals))
        self.assertEqual(path[0]["idx"], rc.RATE_LOOKBACK + rc.RATE_SIGMA_WINDOW - 1)
        self.assertTrue(all(p["thr"] >= rc.RATE_FLOOR_BP for p in path))
        first_raw = next(i for i, p in enumerate(path) if p["raw"] == -1)
        first_state = next(i for i, p in enumerate(path) if p["state"] == -1)
        self.assertEqual(first_state - first_raw, rc.RATE_PERSIST - 1)
        self.assertTrue(all(p["state"] == 0 for p in path[:first_raw]))

    def test_distance_labels(self):
        d = rc.rate_distance(-1, -7.4, 5.0, 2.5)
        self.assertEqual((d["target"], d["bp"]), ("flat", 4.9))
        self.assertIn("距退出下行", d["label"])
        self.assertFalse(d["critical"])
        f = rc.rate_distance(0, 4.2, 5.0, 2.5)
        self.assertEqual((f["target"], f["bp"]), ("up", 0.8))
        self.assertIn("距上行切换还差 0.8bp", f["label"])
        self.assertTrue(f["critical"])                                  # ≤ 0.2×5bp
        p = rc.rate_distance(0, -6.0, 5.0, 2.5, pending=2, raw=-1)
        self.assertIn("确认中 2/5", p["label"])


class GrowthAxisTests(unittest.TestCase):
    def test_growth_step_hysteresis(self):
        self.assertEqual(rc.growth_step(0, 0.49), 0)
        self.assertEqual(rc.growth_step(0, 0.5), 1)
        self.assertEqual(rc.growth_step(1, 0.26), 1)                 # 0.26 仍高于退出线 0.25
        self.assertEqual(rc.growth_step(1, 0.24), 0)
        self.assertEqual(rc.growth_step(-1, -0.3), -1)
        self.assertEqual(rc.growth_step(-1, -0.2), 0)
        self.assertEqual(rc.growth_step(-1, 0.6), 1)                 # 直接跳到高于趋势

    def test_pmi_zscore_matches_hand_calc(self):
        import statistics as st
        rows = monthly_pmi_wave(40)
        gp = rc.growth_path(rows, trend_win=6, z_win=10)
        vals = [r["value"] for r in rows]
        dev = {i: vals[i] - st.mean(vals[i - 5:i + 1]) for i in range(5, len(vals))}
        i = len(vals) - 1
        z = lambda k: (dev[k] - st.mean([dev[j] for j in range(k - 9, k + 1)])) / st.stdev([dev[j] for j in range(k - 9, k + 1)])
        self.assertAlmostEqual(gp[-1]["dev"], dev[i], places=9)
        self.assertAlmostEqual(gp[-1]["z"], z(i), places=9)
        self.assertAlmostEqual(gp[-1]["z3"], (z(i) + z(i - 1) + z(i - 2)) / 3, places=9)
        self.assertEqual(gp[0]["month"], rows[5 + 9 + 2]["month"])   # 首个 z3 需 36/60 类窗口 + 3 个月

    def test_growth_block_critical_and_labels(self):
        b = rc.growth_block({"month": "2026-09", "pmi": 50.1, "dev": 0.42, "z": 0.72, "z3": 0.26, "state": 1,
                             "trend": "下行", "trendDelta": -0.08})
        self.assertTrue(b["critical"])
        self.assertEqual(b["levelLabel"], "高于趋势（临界）")
        self.assertEqual(b["distance"]["sigma"], 0.01)
        self.assertNotIn("boundary", b)
        self.assertEqual(rc.summary_text("down", b), "增长高于趋势（临界）· 利率下行")
        n = rc.growth_block({"month": "2026-09", "pmi": 50, "dev": 0, "z": 0, "z3": 0.1, "state": 0, "trend": None, "trendDelta": None})
        self.assertEqual(n["distance"]["target"], "above")
        self.assertIn("距趋势上方还差 0.40σ", n["distance"]["label"])


    def test_growth_two_month_confirmation(self):
        # 一个月越线不切换，连续两个月才切换；中途回落清零
        st, cand, cnt = 0, None, 0
        seq = []
        for z3 in (0.55, 0.3, 0.6, 0.93, 0.26, 0.2, 0.3, 0.2, 0.1):
            st, raw, cand, cnt = rc.growth_confirm_step(st, cand, cnt, z3)
            seq.append((st, cnt))
        self.assertEqual(seq, [(0, 1), (0, 0), (0, 1), (1, 0), (1, 0), (1, 1), (1, 0), (1, 1), (0, 0)])

    def test_growth_confirm_progress_and_earliest_month(self):
        b = rc.growth_block({"month": "2026-09", "pmi": 50.1, "dev": 0.42, "z": 0.72, "z3": 0.26, "state": 1,
                             "raw": 1, "pending": 0, "trend": "下行", "trendDelta": -0.08})
        c = b["confirm"]
        self.assertEqual((c["count"], c["need"], c["earliestMonth"]), (0, 2, "2026-11"))
        self.assertEqual(c["label"], "需连续 2 个月低于 0.25σ，最早 11 月数据可能改变读数")
        self.assertTrue(b["hysteresisBacktested"])
        c1 = rc.growth_confirm(1, 1, "2026-10")
        self.assertEqual((c1["count"], c1["earliestMonth"]), (1, "2026-11"))
        self.assertEqual(rc.growth_confirm(0, 0, "2026-12")["earliestMonth"], "2027-02")

    def test_growth_backtest_stats(self):
        gp = [{"month": f"2016-{m:02d}", "state": s} for m, s in
              zip(range(1, 13), [0, 0, 0, 1, 1, 1, 1, 1, 0, 0, -1, -1])]
        bt = rc.growth_backtest(gp)
        self.assertEqual(bt["switches"], 3)
        self.assertEqual(bt["switchesPerYear"], 3.0)
        self.assertEqual(bt["whipsawsUnder2m"], 0)
        self.assertEqual(bt["neutralPct"], 42)
        self.assertEqual(bt["currentEntryMonth"], "2016-11")

    def test_method_no_longer_says_not_backtested(self):
        m = rc._method_block()
        self.assertNotIn("尚未回测", m["growth"])
        self.assertIn("连续 2 个月", m["growth"])
        self.assertEqual(m["backtestGrowth"]["switchesPerYear"], 0.9)
        self.assertEqual(m["backtestGrowth"]["medianStateMonths"], 6)

class TsfImpulseTests(unittest.TestCase):
    def test_gdp_quarterly_and_ttm(self):
        cum = [{"month": m, "cum": v} for m, v in
               [("2025-03", 100), ("2025-06", 210), ("2025-09", 330), ("2025-12", 460), ("2026-03", 110)]]
        q = rc.gdp_quarterly(cum)
        self.assertEqual(q, {"2025-03": 100, "2025-06": 110, "2025-09": 120, "2025-12": 130, "2026-03": 110})
        self.assertEqual(rc.gdp_ttm(cum), {"2025-12": 460, "2026-03": 470})

    def test_impulse_formula(self):
        # 前 12 个月每月 10，后 12 个月每月 20 → 12 个月和之差 = 120；GDP TTM = 460（2025-12）
        tsf = [{"month": rc._month_add("2024-01", i), "value": 10 if i < 12 else 20} for i in range(24)]
        cum = [{"month": m, "cum": v} for m, v in [("2025-03", 100), ("2025-06", 210), ("2025-09", 330), ("2025-12", 460)]]
        ser = rc.tsf_impulse_series(tsf, cum)
        self.assertEqual(len(ser), 1)
        self.assertEqual(ser[0]["month"], "2025-12")
        self.assertAlmostEqual(ser[0]["value"], 120 / 460 * 100)
        blk = rc.compute_tsf_impulse(tsf, cum, "2026-09-30")
        self.assertEqual((blk["status"], blk["asOf"], blk["monthsBehind"]), ("ok", "2025-12", 9))
        self.assertIn("数据截至 12月", blk["asOfLabel"])

    def test_impulse_pending_never_fabricates(self):
        blk = rc.compute_tsf_impulse([], [], "2026-09-30")
        self.assertEqual((blk["status"], blk["label"], blk["value"]), ("pending", "待接入", None))
        self.assertNotIn("series", blk)


class RateClockTests(unittest.TestCase):
    def _long_daily(self, tail):
        import math
        base = [2.0 + 0.0005 * math.sin(i / 3) for i in range(400)]
        return daily(base + tail)

    def test_definite_q2_and_signal_switch_from_methodology(self):
        falling = self._long_daily([2.0 - 0.002 * i for i in range(1, 80)])
        strong = pmi([50.0] * 100 + [51.5, 52.0, 52.5, 52.8], 2017, 1)  # 连续 2 个月 z3 ≥ 0.5 才确认
        old = {"status": "ok", "state": "transitional", "stateLabel": "利率走平·过渡期", "quadrant": None, "leanQuadrant": "Q3"}
        c = rc.compute_rate_clock(falling, strong, old_block=old, today="2026-09-30")
        self.assertEqual((c["state"], c["quadrant"], c["rateDir"], c["growth"]["state"]), ("definite", "Q2", "down", 1))
        self.assertEqual(c["signalSwitch"]["cause"], "methodology")
        self.assertIn("口径更新", c["signalSwitch"]["note"])
        self.assertTrue(c["signalSwitch"]["active"])
        # 次日同一读数：沿用切换记录；两周后标签失效
        c2 = rc.compute_rate_clock(falling, strong, old_block=c, today="2026-10-20")
        self.assertEqual(c2["signalSwitch"]["date"], "2026-09-30")
        self.assertFalse(c2["signalSwitch"]["active"])

    def test_growth_neutral_is_transitional_with_lean(self):
        falling = self._long_daily([2.0 - 0.002 * i for i in range(1, 80)])
        flat_pmi = pmi([50.0 + (0.1 if i % 2 else -0.1) for i in range(103)], 2017, 1)
        c = rc.compute_rate_clock(falling, flat_pmi, today="2026-09-30")
        self.assertEqual(c["growth"]["state"], 0)
        self.assertEqual(c["state"], "transitional")
        self.assertEqual(c["stateLabel"], rc.GROWTH_NEUTRAL_LABEL)
        self.assertIsNone(c["quadrant"])
        self.assertEqual(c["confidence"], "低")

    def test_rate_flat_is_transitional(self):
        flat = self._long_daily([2.0] * 80)
        strong = pmi([50.0] * 100 + [51.5, 52.0, 52.5, 52.8], 2017, 1)  # 连续 2 个月 z3 ≥ 0.5 才确认
        c = rc.compute_rate_clock(flat, strong)
        self.assertEqual((c["state"], c["rateDir"], c["stateLabel"]), ("transitional", "flat", rc.TRANSITIONAL_LABEL))
        self.assertEqual(c["history"][-1]["state"], "transitional")
        self.assertTrue(all("thresholdBp" in h for h in c["history"]))

    def test_classify_point(self):
        self.assertEqual(rc.classify_point(-1, -7, 1, 0.3)["quadrant"], "Q2")
        self.assertEqual(rc.classify_point(1, 8, -1, -0.6, "下行")["subState"], "滞胀")
        t = rc.classify_point(0, -3, -1, -0.7)
        self.assertEqual((t["state"], t["leanQuadrant"]), ("transitional", "Q3"))
        self.assertEqual(rc.classify_point(0, -3, 0, 0.1)["stateLabel"], rc.BOTH_NEUTRAL_LABEL)
        self.assertEqual(rc.classify_point(None, None, 1, 0.6)["state"], "undetermined")
        self.assertEqual(rc.classify_point(-1, -7, 1, 0.26, critical=True)["confidence"], "中低")

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
        trans = {"status": "ok", "state": "transitional", "stateLabel": "利率走平·过渡期", "quadrant": None, "leanQuadrant": "Q3",
                 "leanSubState": "衰退", "leanQuadrantName": "衰退", "leanUsPriorAnnualReturn": 3.5, "d10y60bp": -1.9,
                 "growth": {"critical": True}}
        soft = rc.conflict_flags(trans, advice)
        self.assertTrue(soft)
        self.assertEqual({f["level"] for f in soft}, {"reference"})
        self.assertTrue(all(f["text"].startswith("参考·利率走平·过渡期") for f in soft))
        self.assertIn("消费", [f["sector"] for f in soft])
        self.assertTrue(any("增长处临界" in f["text"] for f in soft))

    def test_q2_flags_park_watch_consumer_clear(self):
        advice = {"sectorViews": [{"sector": "消费", "action": "标配偏超配"}, {"sector": "产业园", "action": "观望/弱低配"}],
                  "clockSectorPrior": [{"sector": "消费", "usAnalog": "购物中心", "best": ["Q4", "Q2"], "danger": ["Q3"]},
                                       {"sector": "产业园", "usAnalog": "办公", "best": ["Q2"], "danger": ["Q3", "Q4"]}]}
        clock = {"status": "ok", "quadrant": "Q2", "quadrantName": "复苏/泡沫", "subState": "复苏/泡沫", "growth": {"critical": True}}
        flags = rc.conflict_flags(clock, advice)
        self.assertEqual([(f["sector"], f["level"]) for f in flags], [("产业园", "watch")])
        self.assertIn("临界", flags[0]["text"])

    def test_unavailable_never_fabricates(self):
        old = {"history": [{"month": "2024-01", "quadrant": "Q2"}], "asOf": "2024-01-31"}
        c = rc.compute_rate_clock([], [], old_block=old)
        self.assertEqual(c["status"], "unavailable")
        self.assertIsNone(c["quadrant"])
        self.assertEqual(c["history"], old["history"])

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
