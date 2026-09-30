"""仓库产出校验 + update_cycle_data 离线（mock 取数）回归。"""
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

import update_cycle_data as ucd

ROOT = Path(__file__).resolve().parent.parent


class ValidatorTests(unittest.TestCase):
    def test_repo_outputs_pass_validator(self):
        r = subprocess.run([sys.executable, "validate_rate_clock.py"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def _rc(self):
        return json.loads((ROOT / "cycle_judgment.json").read_text(encoding="utf-8"))["rateClock"]

    def test_definite_requires_both_axes_directional(self):
        import validate_rate_clock as v
        bad = copy.deepcopy(self._rc())
        bad.update(state="definite", quadrant="Q3", rateDir="flat", d10y60bp=-1.0, ratePending=0, conflictFlags=[])
        errs = []
        v.check_dead_band(bad, errs)
        self.assertTrue(any("利率走平或增长趋势附近却判定了象限" in e for e in errs), errs)

    def test_rate_hysteresis_and_threshold_consistency(self):
        import validate_rate_clock as v
        bad = copy.deepcopy(self._rc())
        bad.update(rateDir="down", d10y60bp=-1.0, thresholdBp=5.0, exitBp=2.5, ratePending=0)
        errs = []
        v.check_dead_band(bad, errs)
        self.assertTrue(any("已高于退出线" in e for e in errs), errs)
        bad2 = copy.deepcopy(self._rc())
        bad2.update(thresholdBp=4.0, exitBp=2.0)
        errs = []
        v.check_dead_band(bad2, errs)
        self.assertTrue(any("低于 5bp 下限" in e for e in errs), errs)

    def test_transitional_rejects_hard_flags_and_quadrant(self):
        import validate_rate_clock as v
        bad = copy.deepcopy(self._rc())
        bad.update(state="transitional", stateLabel="利率走平·过渡期", rateDir="flat", confidence="低",
                   quadrant="Q3", usPriorAnnualReturn=None, d10y60bp=-1.9, ratePending=0,
                   conflictFlags=[{"level": "conflict", "text": "x"}])
        errs = []
        v.check_dead_band(bad, errs)
        self.assertTrue(any("过渡期不得给出象限" in e for e in errs), errs)
        self.assertTrue(any("只允许「参考」" in e for e in errs), errs)

    def test_growth_state_must_match_z3_and_old_boundary_removed(self):
        import validate_rate_clock as v
        bad = copy.deepcopy(self._rc())
        bad["growth"] = dict(bad["growth"], z3=0.1, state=1, boundary=True)
        errs = []
        v.check_dead_band(bad, errs)
        self.assertTrue(any("±0.25 以内却未退回" in e for e in errs), errs)
        self.assertTrue(any("49.5–50.5" in e for e in errs), errs)

    def test_tsf_pending_must_not_carry_numbers(self):
        import validate_rate_clock as v
        errs = []
        v.check_tsf({"tsfImpulse": {"status": "pending", "label": "待接入", "value": -0.8}}, errs)
        self.assertTrue(any("不得含数值" in e for e in errs), errs)


class UpdateCycleOfflineTests(unittest.TestCase):
    def setUp(self):
        self.advice = json.loads((ROOT / "advice.json").read_text(encoding="utf-8"))
        self.panel = json.loads((ROOT / "data_panel_l1l7.json").read_text(encoding="utf-8"))

    def test_fetch_failure_uses_cache_and_marks_origin(self):
        ucd_cache = ucd.MACRO_JSON
        try:
            ucd.MACRO_JSON = ROOT / "tests" / "fixtures" / "__missing_macro__.json"
            m = ucd.refresh_macro_series("2026-09-29", fetch_y10=lambda: [], fetch_pmi=lambda: [], fetch_tsf=lambda: [],
                                         fetch_gdp=lambda: [], fetch_curve=lambda: None)
        finally:
            ucd.MACRO_JSON = ucd_cache
        self.assertEqual(m["cgb10y"]["origin"], "unavailable")
        self.assertEqual(m["cgb10y"]["series"], [])
        cycle = ucd.apply_rate_clock({"rateClock": None}, m, self.advice, self.panel, "2026-09-29")
        self.assertEqual(cycle["rateClock"]["status"], "unavailable")
        self.assertIsNone(cycle["rateClock"]["quadrant"])
        self.assertEqual(cycle["rateRentGate"]["status"], "pending data")
        self.assertEqual((cycle["tsfImpulse"]["status"], cycle["tsfImpulse"]["label"]), ("pending", "待接入"))
        self.assertIsNone(cycle["tsfImpulse"]["value"])

    def test_cached_macro_series_reproduces_committed_clock(self):
        macro = json.loads((ROOT / "macro_series.json").read_text(encoding="utf-8"))
        committed_cycle = json.loads((ROOT / "cycle_judgment.json").read_text(encoding="utf-8"))
        committed = committed_cycle["rateClock"]
        cycle = ucd.apply_rate_clock({"rateClock": None}, copy.deepcopy(macro), self.advice, self.panel, committed.get("computedAt"))
        rc = cycle["rateClock"]
        self.assertEqual(rc["quadrant"], committed["quadrant"])
        self.assertEqual(rc["state"], committed["state"])
        self.assertEqual(rc.get("leanQuadrant"), committed.get("leanQuadrant"))
        self.assertEqual([h["state"] for h in rc["history"]], [h["state"] for h in committed["history"]])
        self.assertEqual(rc["d10y60bp"], committed["d10y60bp"])
        self.assertEqual((rc["thresholdBp"], rc["exitBp"], rc["rateDir"]), (committed["thresholdBp"], committed["exitBp"], committed["rateDir"]))
        self.assertEqual(rc["growth"]["z3"], committed["growth"]["z3"])
        self.assertEqual(cycle["tsfImpulse"]["value"], committed_cycle["tsfImpulse"]["value"])
        self.assertEqual(rc["asOf"], macro["cgb10y"]["asOf"])
        self.assertEqual(cycle["rateRentGate"]["spreadLeg"]["status"], "pending data")  # SEED 面板不得当真实


if __name__ == "__main__":
    unittest.main()
