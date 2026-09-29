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

    def test_dead_band_rules_reject_forced_quadrant(self):
        import validate_rate_clock as v
        rc = self._rc()
        bad = copy.deepcopy(rc)
        bad.update(state="definite", quadrant="Q3", d10y60bp=-5.9, conflictFlags=[])
        errs = []
        v.check_dead_band(bad, errs)
        self.assertTrue(any("死区内却判定了象限" in e for e in errs), errs)

    def test_transitional_rejects_hard_flags_and_quadrant(self):
        import validate_rate_clock as v
        bad = copy.deepcopy(self._rc())
        bad.update(state="transitional", stateLabel="利率走平·过渡期", rateDir="flat", confidence="低",
                   quadrant="Q3", usPriorAnnualReturn=None, d10y60bp=-5.9,
                   conflictFlags=[{"level": "conflict", "text": "x"}])
        errs = []
        v.check_dead_band(bad, errs)
        self.assertTrue(any("过渡期不得给出象限" in e for e in errs), errs)
        self.assertTrue(any("只允许「参考」" in e for e in errs), errs)

    def test_growth_boundary_must_match_pmi3m(self):
        import validate_rate_clock as v
        bad = copy.deepcopy(self._rc())
        bad["growth"] = dict(bad["growth"], pmi3m=49.77, boundary=False)
        errs = []
        v.check_dead_band(bad, errs)
        self.assertTrue(any("boundary" in e for e in errs), errs)


class UpdateCycleOfflineTests(unittest.TestCase):
    def setUp(self):
        self.advice = json.loads((ROOT / "advice.json").read_text(encoding="utf-8"))
        self.panel = json.loads((ROOT / "data_panel_l1l7.json").read_text(encoding="utf-8"))

    def test_fetch_failure_uses_cache_and_marks_origin(self):
        ucd_cache = ucd.MACRO_JSON
        try:
            ucd.MACRO_JSON = ROOT / "tests" / "fixtures" / "__missing_macro__.json"
            m = ucd.refresh_macro_series("2026-09-29", fetch_y10=lambda: [], fetch_pmi=lambda: [])
        finally:
            ucd.MACRO_JSON = ucd_cache
        self.assertEqual(m["cgb10y"]["origin"], "unavailable")
        self.assertEqual(m["cgb10y"]["series"], [])
        cycle = ucd.apply_rate_clock({"rateClock": None}, m, self.advice, self.panel, "2026-09-29")
        self.assertEqual(cycle["rateClock"]["status"], "unavailable")
        self.assertIsNone(cycle["rateClock"]["quadrant"])
        self.assertEqual(cycle["rateRentGate"]["status"], "pending data")

    def test_cached_macro_series_reproduces_committed_clock(self):
        macro = json.loads((ROOT / "macro_series.json").read_text(encoding="utf-8"))
        committed = json.loads((ROOT / "cycle_judgment.json").read_text(encoding="utf-8"))["rateClock"]
        cycle = ucd.apply_rate_clock({"rateClock": None}, copy.deepcopy(macro), self.advice, self.panel, committed.get("computedAt"))
        rc = cycle["rateClock"]
        self.assertEqual(rc["quadrant"], committed["quadrant"])
        self.assertEqual(rc["state"], committed["state"])
        self.assertEqual(rc.get("leanQuadrant"), committed.get("leanQuadrant"))
        self.assertEqual([h["state"] for h in rc["history"]], [h["state"] for h in committed["history"]])
        self.assertEqual(rc["d10y60bp"], committed["d10y60bp"])
        self.assertEqual(rc["asOf"], macro["cgb10y"]["asOf"])
        self.assertEqual(cycle["rateRentGate"]["spreadLeg"]["status"], "pending data")  # SEED 面板不得当真实


if __name__ == "__main__":
    unittest.main()
