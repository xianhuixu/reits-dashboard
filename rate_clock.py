#!/usr/bin/env python3
"""「增长 × 利率方向」REITs 投资时钟（杜丽虹 2021 框架的中国化实现）+ 升息/租金闸门。

纯 Python（无第三方依赖），供 update_cycle_data.py 调用，也便于单元测试。

口径（中国化，见 docs/rate-clock.md）：
- 利率轴：10Y 国债收益率 60 个交易日变化，±10bp 死区。死区内 rateDir='flat'，
  **不强制判定象限**：state='transitional'，显示「利率走平·过渡期」，quadrant=None；
  另给出按变化符号的 leanQuadrant（最近象限）与 bp 变化，仅作参考，confidence='低'。
  （不做长期滞回：慢速单边下行时滞回会把一年前的升息方向延续到今天，误导性更大。）
- 增长边界：PMI 3 月均值落在 [49.5, 50.5] 时 growth.boundary=True、标注「边界」，
  象限仍按 50 判定但置信度下调并注明（仅利率轴决定是否进入过渡期）。
- 冲突标记：只有确定象限才产生硬冲突（conflict/watch/background）；过渡期按 leanQuadrant
  产生 level='reference' 的「参考」提示。
- 增长轴：制造业 PMI 近 3 个月均值 vs 50（替代美国「实际 GDP 同比 2%」）；
  趋势 = 近 3 月均值 − 前 3 月均值（±0.1 死区），用于 Q4 滞胀/复苏拆分。
- 象限：Q1 增长强+升息（繁荣）· Q2 增长强+降息（复苏/泡沫）· Q3 增长弱+降息（衰退）· Q4 增长弱+升息（滞胀/复苏）。
仅作宏观背景层：不改变 advice.sectorViews（学派 resolutionRules）。
所有数据均来自真实接口；取数失败时返回 status=unavailable，绝不插值/编造。
"""
from __future__ import annotations

import json
import urllib.request
from typing import Iterable

RATE_LOOKBACK = 60          # 交易日
RATE_DEAD_BAND_BP = 10.0
PMI_THRESHOLD = 50.0
PMI_TREND_DEAD_BAND = 0.1
PMI_BOUNDARY_BAND = 0.5      # 49.5–50.5 视为增长边界
TRANSITIONAL_LABEL = "利率走平·过渡期"
HISTORY_MONTHS = 24

# 门槛：升息快于租金（P1-5）
GATE_RATE_UP_BP = 25.0
GATE_SPREAD_PCTILE_DROP_PP = 20.0

QUADRANT_META = {
    "Q1": {"name": "繁荣", "growth": "强", "rate": "升息", "usPrior": 4.9},
    "Q2": {"name": "复苏/泡沫", "growth": "强", "rate": "降息", "usPrior": 23.9},
    "Q3": {"name": "衰退", "growth": "弱", "rate": "降息", "usPrior": 3.5},
    "Q4": {"name": "滞胀/复苏", "growth": "弱", "rate": "升息", "usPrior": 15.1},
}
Q4_SPLIT_PRIOR = {"滞胀": -10.7, "复苏": 26.1}
CLOCKWISE_NEXT = {"Q1": "Q4", "Q4": "Q3", "Q3": "Q2", "Q2": "Q1"}
COUNTER_NEXT = {v: k for k, v in CLOCKWISE_NEXT.items()}

CGB10Y_SOURCE = "东方财富数据中心 RPTA_WEB_TREASURYYIELD · EMM00166466 中国国债收益率10年（中债口径）"
PMI_SOURCE = "东方财富数据中心 RPT_ECONOMY_PMI · 制造业 PMI（国家统计局）"
_UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}


# ---------------- 取数（真实接口） ----------------
def _get_json(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_cgb10y_history(pages: int = 2) -> list[dict]:
    """10Y 国债收益率日序列 [{date, value}] 升序；失败返回 []。每页 500 个自然日行（含仅美债行）。"""
    rows: list[dict] = []
    for p in range(1, pages + 1):
        url = ("https://datacenter.eastmoney.com/api/data/get?type=RPTA_WEB_TREASURYYIELD"
               f"&sty=SOLAR_DATE,EMM00166466&st=SOLAR_DATE&sr=-1&p={p}&ps=500&source=WEB")
        try:
            data = (_get_json(url).get("result") or {}).get("data") or []
        except Exception as e:  # noqa: BLE001
            print(f"[rate_clock] 10Y 第{p}页获取失败: {e}")
            break
        for r in data:
            v = r.get("EMM00166466")
            if v is None:
                continue
            rows.append({"date": str(r.get("SOLAR_DATE", ""))[:10], "value": round(float(v), 4)})
        if len(data) < 500:
            break
    return normalize_series(rows)


def fetch_pmi_history(n: int = 36) -> list[dict]:
    """制造业 PMI 月序列 [{month:'YYYY-MM', value}] 升序；失败返回 []。"""
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_ECONOMY_PMI"
           f"&columns=REPORT_DATE,MAKE_INDEX&sortColumns=REPORT_DATE&sortTypes=-1&pageSize={n}"
           "&pageNumber=1&source=WEB&client=WEB")
    try:
        data = (_get_json(url).get("result") or {}).get("data") or []
    except Exception as e:  # noqa: BLE001
        print(f"[rate_clock] PMI 获取失败: {e}")
        return []
    out = []
    for r in data:
        v = r.get("MAKE_INDEX")
        if v is None:
            continue
        out.append({"month": str(r.get("REPORT_DATE", ""))[:7], "value": float(v)})
    out.sort(key=lambda x: x["month"])
    return out


def normalize_series(rows: Iterable[dict]) -> list[dict]:
    seen = {}
    for r in rows:
        if r.get("date") and r.get("value") is not None:
            seen[r["date"]] = float(r["value"])
    return [{"date": d, "value": seen[d]} for d in sorted(seen)]


# ---------------- 判定逻辑（纯函数） ----------------
def rate_change_bp(series: list[dict], lookback: int = RATE_LOOKBACK, end_idx: int | None = None):
    """series 升序；返回 (变化bp, 起点日期, 终点日期) 或 (None, None, None)。"""
    if end_idx is None:
        end_idx = len(series) - 1
    start_idx = end_idx - lookback
    if end_idx < 0 or start_idx < 0:
        return None, None, None
    a, b = series[start_idx], series[end_idx]
    return round((b["value"] - a["value"]) * 100, 1), a["date"], b["date"]


def rate_direction(change_bp, dead_band: float = RATE_DEAD_BAND_BP):
    """返回 (dir, inDeadBand, lean)。dir ∈ {'up','down','flat', None}；lean 为变化符号方向。"""
    if change_bp is None:
        return None, False, None
    lean = "up" if change_bp > 0 else "down" if change_bp < 0 else None
    if change_bp >= dead_band:
        return "up", False, lean
    if change_bp <= -dead_band:
        return "down", False, lean
    return "flat", True, lean


def growth_state(pmi: list[dict], upto_month: str | None = None):
    """PMI 近3月均值 vs 50 + 趋势。返回 dict 或 None（不足 3 个月）。"""
    rows = [r for r in pmi if upto_month is None or r["month"] <= upto_month]
    if len(rows) < 3:
        return None
    last3 = [r["value"] for r in rows[-3:]]
    avg3 = sum(last3) / 3
    prev = [r["value"] for r in rows[-6:-3]]
    trend_val = round(avg3 - sum(prev) / len(prev), 2) if len(prev) == 3 else None
    if trend_val is None:
        trend = None
    elif trend_val > PMI_TREND_DEAD_BAND:
        trend = "上行"
    elif trend_val < -PMI_TREND_DEAD_BAND:
        trend = "下行"
    else:
        trend = "持平"
    boundary = abs(avg3 - PMI_THRESHOLD) <= PMI_BOUNDARY_BAND + 1e-9
    return {
        "pmiLatest": rows[-1]["value"], "pmiMonth": rows[-1]["month"],
        "pmi3m": round(avg3, 2), "level": "强" if avg3 >= PMI_THRESHOLD else "弱",
        "boundary": boundary, "levelLabel": "边界" if boundary else ("强" if avg3 >= PMI_THRESHOLD else "弱"),
        "boundaryNote": (f"PMI 3月均值 {avg3:.2f} 处于 {PMI_THRESHOLD - PMI_BOUNDARY_BAND:.1f}–{PMI_THRESHOLD + PMI_BOUNDARY_BAND:.1f} 边界带，"
                         f"强/弱归属不稳定（按 50 暂归「{'强' if avg3 >= PMI_THRESHOLD else '弱'}」）") if boundary else None,
        "trend": trend, "trendDelta": trend_val,
    }


def quadrant_of(growth_level: str | None, rate_dir: str | None):
    if growth_level not in ("强", "弱") or rate_dir not in ("up", "down"):
        return None
    if growth_level == "强":
        return "Q1" if rate_dir == "up" else "Q2"
    return "Q4" if rate_dir == "up" else "Q3"


def sub_state(quadrant: str | None, growth_trend: str | None):
    if quadrant == "Q4":
        if growth_trend == "上行":
            return "复苏"
        if growth_trend == "下行":
            return "滞胀"
        return "待定"
    return QUADRANT_META[quadrant]["name"] if quadrant else None


def rotation_of(history: list[dict]):
    """只用确定象限（过渡期月份跳过）判断最近一次切换的旋转方向。"""
    seq, months = [], []
    for h in history:
        q = h.get("quadrant")
        if q and (not seq or seq[-1] != q):
            seq.append(q)
            months.append(h.get("month"))
    last_def = next((h.get("month") for h in reversed(history) if h.get("quadrant")), None)
    trans_since = sum(1 for h in history if last_def and h.get("month", "") > last_def and h.get("state") == "transitional")
    base = {"basis": "仅确定象限（过渡期月份不计）", "lastDefiniteMonth": last_def, "transitionalMonthsSince": trans_since}
    if len(seq) < 2:
        return dict(base, direction="未切换", **{"from": None, "to": seq[-1] if seq else None, "switchMonth": None})
    a, b = seq[-2], seq[-1]
    if CLOCKWISE_NEXT[a] == b:
        d = "顺时针"
    elif COUNTER_NEXT[a] == b:
        d = "逆时针（利率先行）"
    else:
        d = "跳跃"
    return dict(base, direction=d, **{"from": a, "to": b, "switchMonth": months[-1]})


def classify_point(chg, g) -> dict:
    """单个时点的象限状态：definite（确定象限）/ transitional（利率走平）/ undetermined（数据不足）。"""
    rdir, band, lean = rate_direction(chg)
    level = g["level"] if g else None
    trend = g["trend"] if g else None
    gb = bool(g and g.get("boundary"))
    if rdir in ("up", "down") and level:
        q = quadrant_of(level, rdir)
        return {"state": "definite", "stateLabel": QUADRANT_META[q]["name"], "quadrant": q,
                "subState": sub_state(q, trend), "leanQuadrant": None, "leanSubState": None,
                "rateDir": rdir, "rateLean": lean, "deadBand": False,
                "confidence": "中低" if gb else "中"}
    if rdir == "flat" and level:
        lq = quadrant_of(level, lean)
        return {"state": "transitional", "stateLabel": TRANSITIONAL_LABEL, "quadrant": None, "subState": None,
                "leanQuadrant": lq, "leanSubState": sub_state(lq, trend) if lq else None,
                "rateDir": "flat", "rateLean": lean, "deadBand": True, "confidence": "低"}
    return {"state": "undetermined", "stateLabel": "未判定", "quadrant": None, "subState": None,
            "leanQuadrant": None, "leanSubState": None, "rateDir": rdir, "rateLean": lean,
            "deadBand": band, "confidence": None}


def month_end_indices(series: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for i, r in enumerate(series):
        out[r["date"][:7]] = i
    return out


def build_history(series: list[dict], pmi: list[dict], months: int = HISTORY_MONTHS) -> list[dict]:
    """逐月末重算象限轨迹（只用当月末可得的数据）。"""
    idx = month_end_indices(series)
    keys = sorted(idx)[-(months + 1):]
    # 当月若未到月末（最后一个月），仍保留：以最新交易日为点
    hist: list[dict] = []
    for m in keys:
        i = idx[m]
        chg, _, d_end = rate_change_bp(series, end_idx=i)
        if chg is None:
            continue
        g = growth_state(pmi, upto_month=m)
        c = classify_point(chg, g)
        hist.append({
            "month": m, "asOf": d_end, "y10": series[i]["value"], "d10y60bp": chg,
            "state": c["state"], "stateLabel": c["stateLabel"],
            "rateDir": c["rateDir"], "rateLean": c["rateLean"], "deadBand": c["deadBand"], "confidence": c["confidence"],
            "pmi3m": g["pmi3m"] if g else None, "growth": g["level"] if g else None,
            "growthBoundary": bool(g and g.get("boundary")),
            "growthTrend": g["trend"] if g else None,
            "quadrant": c["quadrant"], "subState": c["subState"],
            "leanQuadrant": c["leanQuadrant"], "leanSubState": c["leanSubState"],
        })
    return hist[-months:]


def merge_history(old: list[dict] | None, new: list[dict], months: int = 36) -> list[dict]:
    """新算结果覆盖同月；保留新序列覆盖不到的更早月份（真实历史计算结果）。"""
    by = {h["month"]: h for h in (old or []) if h.get("month")}
    for h in new:
        by[h["month"]] = h
    return [by[k] for k in sorted(by)][-months:]


def compute_rate_clock(series: list[dict], pmi: list[dict], old_block: dict | None = None,
                       today: str | None = None) -> dict:
    base = {
        "_comment": "增长×利率 REITs 投资时钟（杜丽虹 2021 框架中国化）；仅作宏观背景，不改变 advice.sectorViews；见 docs/rate-clock.md",
        "method": {
            "rate": f"10Y 国债 {RATE_LOOKBACK} 交易日变化，±{RATE_DEAD_BAND_BP:.0f}bp 死区；死区内不判象限，记「{TRANSITIONAL_LABEL}」，最近象限仅作参考",
            "growth": f"制造业 PMI 近3月均值 vs 50（{PMI_THRESHOLD - PMI_BOUNDARY_BAND:.1f}–{PMI_THRESHOLD + PMI_BOUNDARY_BAND:.1f} 标「边界」）；趋势=近3月均值−前3月均值（±0.1 死区）",
            "usPriorSource": "overseas_clock_du2021.json（美国 1994 年以来，年化总回报）",
        },
        "sources": {"y10": CGB10Y_SOURCE, "pmi": PMI_SOURCE},
        "computedAt": today,
    }
    old_hist = (old_block or {}).get("history") or []
    if len(series) <= RATE_LOOKBACK or len(pmi) < 3:
        base.update({
            "status": "unavailable",
            "statusNote": "10Y 或 PMI 真实序列取数失败/不足，象限未判定（不插值、不沿用手工值）",
            "quadrant": None, "history": old_hist,
            "asOf": (old_block or {}).get("asOf"),
        })
        return base
    hist = build_history(series, pmi)
    chg, d0, d1 = rate_change_bp(series)
    g = growth_state(pmi)
    c = classify_point(chg, g)
    q, sub = c["quadrant"], c["subState"]
    merged = merge_history(old_hist, hist)

    def prior_of(qq, ss):
        if not qq:
            return None
        return Q4_SPLIT_PRIOR[ss] if qq == "Q4" and ss in Q4_SPLIT_PRIOR else QUADRANT_META[qq]["usPrior"]

    notes = []
    if c["state"] == "transitional":
        notes.append(f"10Y 60日变化 {chg:+.1f}bp 在 ±{RATE_DEAD_BAND_BP:.0f}bp 死区内 → 利率走平·过渡期，不判定象限；"
                     f"最近象限 {c['leanQuadrant'] or '—'} 仅作参考")
    elif c["state"] == "definite":
        notes.append(f"10Y 60日变化 {chg:+.1f}bp 超出死区")
    if g and g.get("boundary"):
        notes.append(g["boundaryNote"])
    base.update({
        "status": "ok",
        "asOf": d1,
        "y10": series[-1]["value"], "y10Start": series[-1 - RATE_LOOKBACK]["value"], "y10StartDate": d0,
        "d10y60bp": chg, "rateDir": c["rateDir"], "rateLean": c["rateLean"], "deadBand": c["deadBand"],
        "state": c["state"], "stateLabel": c["stateLabel"],
        "confidence": c["confidence"],
        "confidenceNote": "；".join(notes),
        "growth": g,
        "quadrant": q, "quadrantName": QUADRANT_META[q]["name"] if q else c["stateLabel"],
        "subState": sub, "usPriorAnnualReturn": prior_of(q, sub),
        "leanQuadrant": c["leanQuadrant"], "leanSubState": c["leanSubState"],
        "leanQuadrantName": QUADRANT_META[c["leanQuadrant"]]["name"] if c["leanQuadrant"] else None,
        "leanUsPriorAnnualReturn": prior_of(c["leanQuadrant"], c["leanSubState"]),
        "leanNote": "仅作参考：死区内按 10Y 变化符号推得的最近象限，不参与硬冲突判定" if c["state"] == "transitional" else None,
        "rotation": rotation_of(merged),
        "history": merged,
    })
    return base


# ---------------- 冲突标记 ----------------
def _is_overweight(action: str | None) -> bool:
    return bool(action) and "超配" in action and "低配" not in action


def _is_underweight(action: str | None) -> bool:
    return bool(action) and any(k in action for k in ("低配", "观望", "谨慎"))


def _in_zone(zone: list | None, quadrant: str, sub: str | None) -> bool:
    if not zone or not quadrant:
        return False
    if quadrant in zone:
        return True
    return quadrant == "Q4" and sub == "滞胀" and "Q4-stagflation" in zone


def conflict_flags(clock: dict, advice: dict | None) -> list[dict]:
    """确定象限 vs 学派板块观点：超配板块落在美国先验雷区 → conflict；低配板块处最佳象限 → watch；
    高风险象限 → background。过渡期（利率走平）只按 leanQuadrant 产生 level='reference' 的「参考」提示。"""
    if not clock or clock.get("status") != "ok" or not advice:
        return []
    definite = bool(clock.get("quadrant"))
    if definite:
        q, sub = clock["quadrant"], clock.get("subState")
        tag = f"rateClock={q}（{clock.get('quadrantName')}）"
    elif clock.get("state") == "transitional" and clock.get("leanQuadrant"):
        q, sub = clock["leanQuadrant"], clock.get("leanSubState")
        tag = f"参考·{TRANSITIONAL_LABEL}（最近象限 {q} {clock.get('leanQuadrantName') or ''}，Δ10Y {clock.get('d10y60bp')}bp）"
    else:
        return []
    gnote = "；增长处边界带" if (clock.get("growth") or {}).get("boundary") else ""
    views = {v.get("sector"): v for v in advice.get("sectorViews") or []}
    flags = []
    for p in advice.get("clockSectorPrior") or []:
        v = views.get(p.get("sector")) or {}
        act = v.get("action")
        if _is_overweight(act) and _in_zone(p.get("danger"), q, sub):
            flags.append({
                "sector": p["sector"], "level": "conflict" if definite else "reference", "action": act,
                "text": f"{tag} × {p['sector']}「{act}」 vs 美国先验雷区（{p.get('usAnalog')}）" +
                        ("→ 需给出中国实证理由或降级" if definite else "→ 非确定象限，仅提示跟踪") + gnote,
            })
        elif _is_underweight(act) and _in_zone(p.get("best"), q, sub):
            flags.append({
                "sector": p["sector"], "level": "watch" if definite else "reference", "action": act,
                "text": f"{tag} 为 {p['sector']} 美国先验最佳象限（{p.get('usAnalog')}），学派「{act}」" +
                        ("→ 复核是否错过修复" if definite else "→ 非确定象限，仅提示跟踪") + gnote,
            })
    if q == "Q3" or (q == "Q4" and sub == "滞胀"):
        mon = ((advice.get("horizons") or {}).get("monthly") or {}).get("stance")
        pr = clock.get("usPriorAnnualReturn") if definite else clock.get("leanUsPriorAnnualReturn")
        flags.append({
            "sector": "全市场", "level": "background" if definite else "reference",
            "text": f"{tag}{'·' + sub if sub else ''}：美国先验整体年化 {pr}%（高风险象限）vs 学派月度「{mon}」→ 按 resolutionRules 仅作宏观背景，不单独改仓位",
        })
    return flags


# ---------------- P1-5 升息快于租金闸门 ----------------
def spread_pctile_change(rows: list[dict], lookback_days: int = 60):
    """rows: [{date, pctile(0-1)}] 升序。返回 (变化pp, 起点日期, 终点日期)；按自然日≥lookback*1.45 近似 60 交易日。"""
    from datetime import date as _d
    rows = [r for r in rows if r.get("date") and r.get("pctile") is not None]
    if len(rows) < 2:
        return None, None, None
    end = rows[-1]
    end_d = _d.fromisoformat(end["date"][:10])
    span = int(lookback_days * 1.45)
    start = None
    for r in reversed(rows[:-1]):
        if (end_d - _d.fromisoformat(r["date"][:10])).days >= span:
            start = r
            break
    if start is None:
        return None, None, None
    return round((end["pctile"] - start["pctile"]) * 100, 1), start["date"], end["date"]


def rate_rent_gate(series: list[dict], panel: dict | None) -> dict:
    """10Y 60日升 ≥25bp 且 产权利差分位 60日降 ≥20pp → 升级利率风险、估值闸门降级。

    产权利差分位目前只有 data_panel_l1l7.json 的 SEED 插值（seedMeta.liveFetch=false），
    该腿记为 pending data；利率腿用真实 10Y。利率腿明确未满足时，整体为 not_triggered（AND 条件）。
    """
    out = {
        "rule": f"Δ10Y({RATE_LOOKBACK}交易日) ≥ +{GATE_RATE_UP_BP:.0f}bp 且 产权利差分位 {RATE_LOOKBACK}日下降 ≥ {GATE_SPREAD_PCTILE_DROP_PP:.0f}pp",
        "effectsIfTriggered": {"risk": "rate_equity_divert", "escalateTo": "高", "gate": "valuation", "downgradeTo": "partial"},
    }
    chg, d0, d1 = rate_change_bp(series)
    if chg is None:
        rate_leg = {"status": "pending data", "note": "10Y 真实序列不可用"}
    else:
        rate_leg = {"status": "ok", "d10y60bp": chg, "from": d0, "to": d1, "met": chg >= GATE_RATE_UP_BP,
                    "source": CGB10Y_SOURCE}
    live = bool(panel and (panel.get("seedMeta") or {}).get("liveFetch") is True)
    if not live:
        spread_leg = {"status": "pending data",
                      "note": "产权利差分位仅有 data_panel_l1l7.json SEED 插值（非真实），待中债/中证 live 序列接入"}
    else:
        pc, s0, s1 = spread_pctile_change(panel.get("propertyYieldSeries") or [])
        if pc is None:
            spread_leg = {"status": "pending data", "note": "产权利差分位序列不足 60 日"}
        else:
            spread_leg = {"status": "ok", "pctileChangePP": pc, "from": s0, "to": s1,
                          "met": pc <= -GATE_SPREAD_PCTILE_DROP_PP}
    if rate_leg["status"] == "ok" and not rate_leg["met"]:
        status = "not_triggered"
    elif rate_leg["status"] == "ok" and spread_leg["status"] == "ok":
        status = "triggered" if spread_leg["met"] else "not_triggered"
    else:
        status = "pending data"
    data_status = "complete" if (rate_leg["status"] == "ok" and spread_leg["status"] == "ok") else "partial"
    out.update({"status": status, "dataStatus": data_status, "rateLeg": rate_leg, "spreadLeg": spread_leg,
                "asOf": rate_leg.get("to")})
    return out
