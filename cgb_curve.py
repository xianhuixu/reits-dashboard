#!/usr/bin/env python3
"""中债国债收益率曲线：按剩余期限插值 + 经营权期限匹配利差（纯函数，无第三方依赖）。

经营权利差口径（2026-09-30 团队校准）：IRR − 与剩余期限匹配的国债收益率（中债曲线关键期限线性插值），
替代旧的 IRR − 10Y。产权利差不变：TTM 分派率 − 10Y。
曲线关键期限取自东财 RPTA_WEB_TREASURYYIELD（2Y/5Y/10Y/30Y，中债口径，update_cycle_data.py 写入 macro_series.json.cgbCurve）。
短于最短期限 / 长于最长期限时按端点水平外推（不做斜率外推），并在结果里标注 extrapolated。
"""
from __future__ import annotations


def interp_yield(points, years: float):
    """points: [[期限年, 收益率%], ...]（任意顺序，≥1 个点）；返回 (收益率%, 是否外推)。数据不足返回 (None, False)。"""
    pts = sorted((float(t), float(y)) for t, y in (points or []) if t is not None and y is not None)
    if not pts or years is None or years <= 0:
        return None, False
    if years <= pts[0][0]:
        return pts[0][1], years < pts[0][0]
    if years >= pts[-1][0]:
        return pts[-1][1], years > pts[-1][0]
    for (t0, y0), (t1, y1) in zip(pts, pts[1:]):
        if t0 <= years <= t1:
            return y0 + (y1 - y0) * (years - t0) / (t1 - t0), False
    return None, False


def term_matched_spread(irr_pct, remaining_years, points):
    """经营权期限匹配利差（%）= IRR − 插值国债收益率；任一输入缺失返回 None（不回退到 10Y）。"""
    if irr_pct is None or remaining_years is None:
        return None
    y, ext = interp_yield(points, remaining_years)
    if y is None:
        return None
    return {"spread": round(irr_pct - y, 4), "matchedYield": round(y, 4), "years": remaining_years, "extrapolated": ext}


def weighted_term(rows):
    """市值加权剩余期限：rows=[{mcap, years}]；缺字段的行剔除，无有效行返回 None。"""
    ok = [(r["mcap"], r["years"]) for r in rows or [] if r.get("mcap") and r.get("years") is not None]
    tot = sum(m for m, _ in ok)
    return round(sum(m * y for m, y in ok) / tot, 2) if tot else None
