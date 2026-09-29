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
        self.assertEqual(rc["d10y60bp"], committed["d10y60bp"])
        self.assertEqual(rc["asOf"], macro["cgb10y"]["asOf"])
        self.assertEqual(cycle["rateRentGate"]["spreadLeg"]["status"], "pending data")  # SEED 面板不得当真实


if __name__ == "__main__":
    unittest.main()
