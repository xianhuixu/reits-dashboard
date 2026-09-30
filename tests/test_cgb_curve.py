"""中债曲线插值 / 经营权期限匹配利差（纯函数）。"""
import unittest

import cgb_curve as cc

PTS = [[2, 1.259], [5, 1.3948], [10, 1.667], [30, 2.0735]]


class CurveTests(unittest.TestCase):
    def test_exact_tenors(self):
        for t, y in PTS:
            self.assertEqual(cc.interp_yield(PTS, t), (y, False))

    def test_linear_between_points(self):
        y, ext = cc.interp_yield(PTS, 7)
        self.assertAlmostEqual(y, 1.3948 + (1.667 - 1.3948) * 2 / 5)
        self.assertFalse(ext)
        self.assertAlmostEqual(cc.interp_yield(PTS, 20)[0], 1.667 + (2.0735 - 1.667) * 0.5)

    def test_flat_extrapolation_flagged(self):
        self.assertEqual(cc.interp_yield(PTS, 1), (1.259, True))
        self.assertEqual(cc.interp_yield(PTS, 40), (2.0735, True))

    def test_unsorted_and_missing(self):
        self.assertAlmostEqual(cc.interp_yield(list(reversed(PTS)), 7)[0], cc.interp_yield(PTS, 7)[0])
        self.assertEqual(cc.interp_yield([], 7), (None, False))
        self.assertEqual(cc.interp_yield(PTS, 0), (None, False))

    def test_term_matched_spread_never_falls_back_to_10y(self):
        r = cc.term_matched_spread(5.31, 20, PTS)
        self.assertAlmostEqual(r["spread"], round(5.31 - 1.87025, 4))
        self.assertEqual(r["years"], 20)
        self.assertIsNone(cc.term_matched_spread(5.31, None, PTS))
        self.assertIsNone(cc.term_matched_spread(None, 20, PTS))
        self.assertIsNone(cc.term_matched_spread(5.31, 20, []))

    def test_weighted_term(self):
        self.assertEqual(cc.weighted_term([{"mcap": 100, "years": 10}, {"mcap": 300, "years": 20}]), 17.5)
        self.assertIsNone(cc.weighted_term([{"mcap": 100, "years": None}]))


if __name__ == "__main__":
    unittest.main()
