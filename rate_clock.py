#!/usr/bin/env python3
"""「增长 × 利率方向」REITs 投资时钟（杜丽虹 2021 框架的中国化实现）+ 升息/租金闸门。

纯 Python（无第三方依赖），供 update_cycle_data.py 调用，也便于单元测试。

口径（中国化，见 docs/rate-clock.md）：
- 利率轴：10Y 国债收益率 60 个交易日变化，±10bp 死区。死区内 rateDir='flat'，
  象限按变化符号（rateLean）给出「倾向象限」并标 confidence='低'；变化恰为 0 时不判定。
  （不做长期滞回：慢速单边下行时滞回会把一年前的升息方向延续到今天，误导性更大。）
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


def effective_dir(rdir, lean):
    return rdir if rdir in ("up", "down") else lean


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
    return {
        "pmiLatest": rows[-1]["value"], "pmiMonth": rows[-1]["month"],
        "pmi3m": round(avg3, 2), "level": "强" if avg3 >= PMI_THRESHOLD else "弱",
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
    seq = []
    for h in history:
        q = h.get("quadrant")
        if q and (not seq or seq[-1] != q):
            seq.append(q)
    if len(seq) < 2:
        return {"direction": "未切换", "from": None, "to": seq[-1] if seq else None}
    a, b = seq[-2], seq[-1]
    if CLOCKWISE_NEXT[a] == b:
        d = "顺时针"
    elif COUNTER_NEXT[a] == b:
        d = "逆时针（利率先行）"
    else:
        d = "跳跃"
    return {"direction": d, "from": a, "to": b}


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
        rdir, band, lean = rate_direction(chg)
        g = growth_state(pmi, upto_month=m)
        q = quadrant_of(g["level"] if g else None, effective_dir(rdir, lean))
        hist.append({
            "month": m, "asOf": d_end, "y10": series[i]["value"], "d10y60bp": chg,
            "rateDir": rdir, "rateLean": lean, "deadBand": band, "confidence": "低" if band else "中",
            "pmi3m": g["pmi3m"] if g else None, "growth": g["level"] if g else None,
            "growthTrend": g["trend"] if g else None,
            "quadrant": q, "subState": sub_state(q, g["trend"] if g else None),
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
            "rate": f"10Y 国债 {RATE_LOOKBACK} 交易日变化，±{RATE_DEAD_BAND_BP:.0f}bp 死区（死区内按符号给倾向象限，置信度低）",
            "growth": "制造业 PMI 近3月均值 vs 50；趋势=近3月均值−前3月均值（±0.1 死区）",
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
    rdir, band, lean = rate_direction(chg)
    g = growth_state(pmi)
    q = quadrant_of(g["level"], effective_dir(rdir, lean))
    sub = sub_state(q, g["trend"])
    merged = merge_history(old_hist, hist)
    prior = QUADRANT_META[q]["usPrior"] if q else None
    if q == "Q4" and sub in Q4_SPLIT_PRIOR:
        prior = Q4_SPLIT_PRIOR[sub]
    base.update({
        "status": "ok",
        "asOf": d1,
        "y10": series[-1]["value"], "y10Start": series[-1 - RATE_LOOKBACK]["value"], "y10StartDate": d0,
        "d10y60bp": chg, "rateDir": rdir, "rateLean": lean, "deadBand": band,
        "confidence": "低" if band else "中",
        "confidenceNote": ("10Y 60日变化在 ±10bp 死区内，象限按变化符号给出倾向判断" if band
                           else "10Y 60日变化超出死区"),
        "growth": g,
        "quadrant": q, "quadrantName": QUADRANT_META[q]["name"] if q else "利率横盘（未判定）",
        "subState": sub, "usPriorAnnualReturn": prior,
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
    """当前象限 vs 学派板块观点：超配板块落在美国先验雷区 → 冲突；低配板块处于最佳象限 → 提示。"""
    if not clock or clock.get("status") != "ok" or not clock.get("quadrant") or not advice:
        return []
    q, sub = clock["quadrant"], clock.get("subState")
    views = {v.get("sector"): v for v in advice.get("sectorViews") or []}
    flags = []
    for p in advice.get("clockSectorPrior") or []:
        v = views.get(p.get("sector")) or {}
        act = v.get("action")
        if _is_overweight(act) and _in_zone(p.get("danger"), q, sub):
            flags.append({
                "sector": p["sector"], "level": "conflict", "action": act,
                "text": f"rateClock={q}（{clock.get('quadrantName')}）× {p['sector']}「{act}」 vs 美国先验雷区（{p.get('usAnalog')}）→ 需给出中国实证理由或降级",
            })
        elif _is_underweight(act) and _in_zone(p.get("best"), q, sub):
            flags.append({
                "sector": p["sector"], "level": "watch", "action": act,
                "text": f"rateClock={q} 为 {p['sector']} 美国先验最佳象限（{p.get('usAnalog')}），学派「{act}」→ 复核是否错过修复",
            })
    if q == "Q3" or (q == "Q4" and sub == "滞胀"):
        mon = ((advice.get("horizons") or {}).get("monthly") or {}).get("stance")
        flags.append({
            "sector": "全市场", "level": "background",
            "text": f"rateClock={q}{'·' + sub if sub else ''}：美国先验整体年化 {clock.get('usPriorAnnualReturn')}%（高风险象限）vs 学派月度「{mon}」→ 按 resolutionRules 仅作宏观背景，强化偏债/逆周期结构，不单独改仓位",
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
