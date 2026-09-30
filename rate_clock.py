#!/usr/bin/env python3
"""「增长 × 利率方向」REITs 投资时钟（杜丽虹 2021 框架的中国化实现）+ 社融脉冲 + 升息/租金闸门。

纯 Python（无第三方依赖），供 update_cycle_data.py 调用，也便于单元测试。
口径 2026-09-30 校准版（METHOD_VERSION，见 docs/rate-clock.md）：

利率轴（固收 PM 回测：中债 10Y 日频 2015-01 ~ 2026-09-29，13 个 ≥30bp 拐点）
- 信号 d = 10Y 60 个交易日变化（bp）；σ = d 的滚动 250 交易日（≈1 年）样本标准差。
- 进入线 T = max(5bp, 0.7σ)；退出线 E = T / 2（T 触底 5bp 时 E = 2.5bp）。
- 滞回：d > T → 上行；d < −T → 下行；上行中 d < E / 下行中 d > −E → 回到走平。
- 新状态须连续 5 个交易日成立才切换（期间计数，不满足即清零）。不加 60 日均线条件（回测无增益）。
- 预期统计：约 4.8 次切换/年、状态中位持续 50 个交易日、<10 日的“来回切换”占 6%、拐点识别中位滞后约 60 日；
  滞后主要来自 60 日窗口本身（20–40 日窗口更快，但未采用）。

增长轴（宏观分析师口径；滞回阈值尚未回测）
- g = 制造业 PMI − 其近 36 个月均值（含当月）；z = g 在 60 个月滚动窗口内标准化（减均值 / 样本标准差）。
- 象限用 z 的 3 个月均值 z3：z3 ≥ +0.5 进入「高于趋势」，≤ −0.5 进入「低于趋势」；已在高于/低于趋势时，
  z3 回到 ±0.25 以内（高于趋势时 z3 < 0.25 / 低于趋势时 z3 > −0.25）才退回「趋势附近」。
- 东财 RPT_ECONOMY_PMI 无新订单分项 → 使用 PMI 总指数（已在 method 中标注）。已移除旧的「49.5–50.5 边界」规则。

象限：两轴都有方向才判「确定象限」；任一轴处于走平/趋势附近 → 过渡期（只给最近象限作参考）。
社融脉冲：单独卡片（不并入增长轴）= (近12个月社融增量和 − 上年同期12个月和) / 近4个季度名义 GDP，%。
仅作宏观背景层：不改变 advice.sectorViews（学派 resolutionRules）。
所有数据均来自真实接口；取数失败时返回 status=unavailable / 待接入，绝不插值/编造。
"""
from __future__ import annotations

import json
import math
import urllib.request
from typing import Iterable

METHOD_VERSION = "2026-09-30"
METHOD_SWITCH_NOTE = "9-30 起改用新口径，这次切换来自口径更新，不代表市场突变"
SIGNAL_TAG_DAYS = 14         # 「信号切换」标签保留的自然日

# 利率轴
RATE_LOOKBACK = 60           # 交易日
RATE_SIGMA_WINDOW = 250      # 交易日（≈1 年）
RATE_K_ENTER = 0.7
RATE_FLOOR_BP = 5.0
RATE_EXIT_RATIO = 0.5        # 退出线 = 进入线 / 2
RATE_PERSIST = 5             # 连续交易日确认
RATE_CRITICAL_RATIO = 0.2    # 距最近切换线 ≤ 0.2×进入线 记为「临界」
RATE_SERIES_START = "2015-01-01"
BACKTEST_PM = {"period": "2015-01 ~ 2026-09-29（首个可用 σ 起 2016-03-31）", "turningPoints": 13, "switchesPerYear": 4.8,
               "medianStateDays": 50, "whipsawPct": 6, "medianLagDays": 60,
               "note": "滞后主要来自 60 日窗口（20–40 日窗口更快，未采用）；加 60 日均线条件无增益"}

# 增长轴
PMI_TREND_WINDOW = 36        # 月
PMI_Z_WINDOW = 60            # 月
GROWTH_ENTER = 0.5
GROWTH_EXIT = 0.25
GROWTH_CRITICAL = 0.05       # 距切换线 ≤ 0.05σ 记为「临界」
GROWTH_TREND_DEAD_BAND = 0.05
PMI_FETCH_MONTHS = 240

TRANSITIONAL_LABEL = "利率走平·过渡期"
GROWTH_NEUTRAL_LABEL = "增长趋势附近·过渡期"
BOTH_NEUTRAL_LABEL = "利率走平·增长趋势附近·过渡期"
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
RATE_DIR_TXT = {"up": "利率上行", "down": "利率下行", "flat": "利率走平"}
GROWTH_TXT = {1: "增长高于趋势", -1: "增长低于趋势", 0: "增长趋势附近"}

CGB10Y_SOURCE = "东方财富数据中心 RPTA_WEB_TREASURYYIELD · EMM00166466 中国国债收益率10年（中债口径）"
CGB_CURVE_SOURCE = "东方财富数据中心 RPTA_WEB_TREASURYYIELD · 中债国债收益率 2Y(EMM00588704)/5Y(EMM00166462)/10Y(EMM00166466)/30Y(EMM00166469)"
PMI_SOURCE = "东方财富数据中心 RPT_ECONOMY_PMI · 制造业 PMI 总指数（国家统计局；该接口无新订单分项）"
TSF_SOURCE = "商务部数据中心 data.mofcom.gov.cn 社会融资规模增量（月度，亿元；akshare macro_china_shrzgm 同源）"
GDP_SOURCE = "东方财富数据中心 RPT_ECONOMY_GDP · 国内生产总值累计值（国家统计局，亿元；季度差分为单季）"
CURVE_FIELDS = {2: "EMM00588704", 5: "EMM00166462", 10: "EMM00166466", 30: "EMM00166469"}
_UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}


# ---------------- 取数（真实接口） ----------------
def _get_json(url: str, timeout: int = 20, data: bytes | None = None, headers: dict | None = None):
    req = urllib.request.Request(url, headers=headers or _UA, data=data, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _treasury_pages(pages: int, sty: str):
    for p in range(1, pages + 1):
        url = ("https://datacenter.eastmoney.com/api/data/get?type=RPTA_WEB_TREASURYYIELD"
               f"&sty={sty}&st=SOLAR_DATE&sr=-1&p={p}&ps=500&source=WEB")
        try:
            data = (_get_json(url).get("result") or {}).get("data") or []
        except Exception as e:  # noqa: BLE001
            print(f"[rate_clock] 国债收益率第{p}页获取失败: {e}")
            return
        yield data
        if len(data) < 500:
            return


def fetch_cgb10y_history(pages: int = 14, start: str = RATE_SERIES_START) -> list[dict]:
    """10Y 国债收益率日序列 [{date, value}] 升序（自 start 起）；失败返回 []。"""
    rows: list[dict] = []
    for data in _treasury_pages(pages, "SOLAR_DATE,EMM00166466"):
        for r in data:
            v = r.get("EMM00166466")
            if v is None:
                continue
            rows.append({"date": str(r.get("SOLAR_DATE", ""))[:10], "value": round(float(v), 4)})
        if rows and min(r["date"] for r in rows) < start:
            break
    return [r for r in normalize_series(rows) if r["date"] >= start]


def fetch_cgb_curve_latest() -> dict | None:
    """最新一个 2/5/10/30Y 全部有值的中债国债曲线关键期限点；失败返回 None。"""
    for data in _treasury_pages(1, "SOLAR_DATE," + ",".join(CURVE_FIELDS.values())):
        for r in data:
            vals = {k: r.get(f) for k, f in CURVE_FIELDS.items()}
            if all(v is not None for v in vals.values()):
                return {"asOf": str(r.get("SOLAR_DATE", ""))[:10],
                        "points": [[k, round(float(vals[k]), 4)] for k in sorted(vals)]}
    return None


def fetch_pmi_history(n: int = PMI_FETCH_MONTHS) -> list[dict]:
    """制造业 PMI 月序列 [{month:'YYYY-MM', value}] 升序；失败返回 []。"""
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_ECONOMY_PMI"
           f"&columns=REPORT_DATE,MAKE_INDEX&sortColumns=REPORT_DATE&sortTypes=-1&pageSize={n}"
           "&pageNumber=1&source=WEB&client=WEB")
    try:
        data = (_get_json(url).get("result") or {}).get("data") or []
    except Exception as e:  # noqa: BLE001
        print(f"[rate_clock] PMI 获取失败: {e}")
        return []
    out = {}
    for r in data:
        v = r.get("MAKE_INDEX")
        if v is not None:
            out[str(r.get("REPORT_DATE", ""))[:7]] = float(v)
    return [{"month": m, "value": out[m]} for m in sorted(out)]


def fetch_tsf_history() -> list[dict]:
    """社融规模增量月序列 [{month, value(亿元)}] 升序；失败返回 []。"""
    try:
        data = _get_json("https://data.mofcom.gov.cn/datamofcom/front/gnmy/shrzgmQuery", data=b"",
                         headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.mofcom.gov.cn/gnmy/shrzgm.shtml"})
    except Exception as e:  # noqa: BLE001
        print(f"[rate_clock] 社融增量获取失败: {e}")
        return []
    out = {}
    for r in data or []:
        d, v = str(r.get("date") or ""), r.get("tiosfs")
        if len(d) == 6 and v is not None:
            out[f"{d[:4]}-{d[4:]}"] = float(v)
    return [{"month": m, "value": out[m]} for m in sorted(out)]


def fetch_gdp_cum_history() -> list[dict]:
    """名义 GDP 年内累计值 [{month:'YYYY-03|06|09|12', cum(亿元)}] 升序；失败返回 []。"""
    url = ("https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_ECONOMY_GDP"
           "&columns=REPORT_DATE,DOMESTICL_PRODUCT_BASE&sortColumns=REPORT_DATE&sortTypes=-1&pageSize=120"
           "&pageNumber=1&source=WEB&client=WEB")
    try:
        data = (_get_json(url).get("result") or {}).get("data") or []
    except Exception as e:  # noqa: BLE001
        print(f"[rate_clock] GDP 获取失败: {e}")
        return []
    out = {}
    for r in data:
        v = r.get("DOMESTICL_PRODUCT_BASE")
        if v is not None:
            out[str(r.get("REPORT_DATE", ""))[:7]] = float(v)
    return [{"month": m, "cum": out[m]} for m in sorted(out)]


def normalize_series(rows: Iterable[dict]) -> list[dict]:
    seen = {}
    for r in rows:
        if r.get("date") and r.get("value") is not None:
            seen[r["date"]] = float(r["value"])
    return [{"date": d, "value": seen[d]} for d in sorted(seen)]


# ---------------- 统计小工具 ----------------
def _mean(xs):
    return sum(xs) / len(xs)


def _std(xs):
    """样本标准差（ddof=1，与 pandas 默认一致）。"""
    n = len(xs)
    if n < 2:
        return None
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def _sign(v):
    return 1 if v is not None and v > 0 else -1 if v is not None and v < 0 else 0


# ---------------- 利率轴：动态死区 + 滞回 + 5 日确认 ----------------
def rate_change_bp(series: list[dict], lookback: int = RATE_LOOKBACK, end_idx: int | None = None):
    """series 升序；返回 (变化bp, 起点日期, 终点日期) 或 (None, None, None)。"""
    if end_idx is None:
        end_idx = len(series) - 1
    start_idx = end_idx - lookback
    if end_idx < 0 or start_idx < 0:
        return None, None, None
    a, b = series[start_idx], series[end_idx]
    return round((b["value"] - a["value"]) * 100, 1), a["date"], b["date"]


def rate_thresholds(sigma_bp, k: float = RATE_K_ENTER, floor: float = RATE_FLOOR_BP, exit_ratio: float = RATE_EXIT_RATIO):
    """进入线 T = max(floor, k·σ)，退出线 E = T·exit_ratio。σ 缺失返回 (None, None)。"""
    if sigma_bp is None:
        return None, None
    t = max(floor, k * sigma_bp)
    return t, t * exit_ratio


def rate_raw_state(cur: int, d: float, t: float, e: float) -> int:
    """当日原始信号（未确认）：上行 1 / 走平 0 / 下行 −1。"""
    raw = cur
    if cur == 1 and d < e:
        raw = 0
    if cur == -1 and d > -e:
        raw = 0
    if d > t:
        raw = 1
    if d < -t:
        raw = -1
    return raw


def rate_step(cur: int, cnt: int, d: float, t: float, e: float, persist: int = RATE_PERSIST):
    """滞回状态机一步：返回 (新状态, 待确认计数, 原始信号)。原始信号≠当前状态连续 persist 日才切换。"""
    raw = rate_raw_state(cur, d, t, e)
    if raw != cur:
        cnt += 1
        if cnt >= persist:
            return raw, 0, raw
        return cur, cnt, raw
    return cur, 0, raw


def rate_state_path(series: list[dict], lookback: int = RATE_LOOKBACK, window: int = RATE_SIGMA_WINDOW,
                    persist: int = RATE_PERSIST) -> list[dict]:
    """逐交易日重放利率轴状态（只用当日可得数据）。从首个 σ 可用日起，初始状态为走平。"""
    vals = [r["value"] * 100 for r in series]
    n = len(vals)
    d60 = [vals[i] - vals[i - lookback] if i >= lookback else None for i in range(n)]
    out: list[dict] = []
    cur, cnt = 0, 0
    for i in range(lookback + window - 1, n):
        sig = _std(d60[i - window + 1:i + 1])  # 滚动 σ：窗口 [i-window+1, i] 内的 d60（均非空）
        t, e = rate_thresholds(sig)
        cur, cnt, raw = rate_step(cur, cnt, d60[i], t, e, persist)
        out.append({"date": series[i]["date"], "idx": i, "d60": d60[i], "sigma": sig, "thr": t, "exit": e,
                    "raw": raw, "state": cur, "pending": cnt})
    return out


DIR_OF = {1: "up", -1: "down", 0: "flat"}


def rate_distance(state: int, d: float, t: float, e: float, pending: int = 0, raw: int | None = None) -> dict:
    """距切换线的距离（bp，正数 = 还需移动的幅度）。critical：距最近切换线 ≤ 0.2×进入线。"""
    if state == -1:
        cands = [("flat", -e - d, f"距退出下行（转走平）还差 {{x}}bp（60日变化需回升至 > −{e:.1f}bp）"),
                 ("up", t - d, "距上行切换还差 {x}bp")]
    elif state == 1:
        cands = [("flat", d - e, f"距退出上行（转走平）还差 {{x}}bp（60日变化需回落至 < +{e:.1f}bp）"),
                 ("down", d + t, "距下行切换还差 {x}bp")]
    else:
        cands = [("up", t - d, "距上行切换还差 {x}bp"), ("down", d + t, "距下行切换还差 {x}bp")]
    target, dist, tpl = min(cands, key=lambda c: c[1])
    dist_r = round(dist, 1)
    if pending and raw is not None and raw != state:
        label = f"已越线，新状态「{RATE_DIR_TXT[DIR_OF[raw]]}」确认中 {pending}/{RATE_PERSIST} 日"
    else:
        label = tpl.replace("{x}", f"{max(dist_r, 0):.1f}")
    return {"target": target, "bp": dist_r, "label": label,
            "critical": bool(dist <= RATE_CRITICAL_RATIO * t) or bool(pending),
            "marginPct": round(max(0.0, min(1.0, dist / t)) * 100),
            "all": {c[0]: round(c[1], 1) for c in cands}}


# ---------------- 增长轴：PMI 偏离趋势 z 分数 + 滞回 ----------------
def growth_step(cur: int, z3: float, enter: float = GROWTH_ENTER, exit_: float = GROWTH_EXIT) -> int:
    """月度滞回：≥+0.5 进入高于趋势，≤−0.5 进入低于趋势；已在其中时回到 ±0.25 以内才退回趋势附近。"""
    if z3 >= enter:
        return 1
    if z3 <= -enter:
        return -1
    if cur == 1 and z3 < exit_:
        return 0
    if cur == -1 and z3 > -exit_:
        return 0
    return cur


def growth_path(pmi: list[dict], trend_win: int = PMI_TREND_WINDOW, z_win: int = PMI_Z_WINDOW) -> list[dict]:
    """逐月：dev = PMI − 近36月均值（含当月）；z = dev 在 60 月窗口内标准化；z3 = z 的 3 月均值；state 滞回。"""
    vals = [r["value"] for r in pmi]
    n = len(vals)
    dev = [vals[i] - _mean(vals[i - trend_win + 1:i + 1]) if i >= trend_win - 1 else None for i in range(n)]
    z: list = [None] * n
    for i in range(n):
        w = dev[i - z_win + 1:i + 1] if i >= z_win - 1 else []
        if len(w) == z_win and all(x is not None for x in w):
            sd = _std(w)
            z[i] = (dev[i] - _mean(w)) / sd if sd else None
    out, cur, prev_z3 = [], 0, None
    for i in range(n):
        if i < 2 or any(z[k] is None for k in (i, i - 1, i - 2)):
            continue
        z3 = (z[i] + z[i - 1] + z[i - 2]) / 3
        cur = growth_step(cur, z3)
        td = None if prev_z3 is None else z3 - prev_z3
        trend = None if td is None else ("上行" if td > GROWTH_TREND_DEAD_BAND else "下行" if td < -GROWTH_TREND_DEAD_BAND else "持平")
        out.append({"month": pmi[i]["month"], "pmi": vals[i], "dev": dev[i], "z": z[i], "z3": z3,
                    "state": cur, "trend": trend, "trendDelta": td})
        prev_z3 = z3
    return out


def growth_distance(state: int, z3: float) -> dict:
    if state == 1:
        cands = [("neutral", z3 - GROWTH_EXIT, "距趋势附近（退出高于趋势）还差 {x}σ")]
    elif state == -1:
        cands = [("neutral", -GROWTH_EXIT - z3, "距趋势附近（退出低于趋势）还差 {x}σ")]
    else:
        cands = [("above", GROWTH_ENTER - z3, "距趋势上方还差 {x}σ"), ("below", z3 + GROWTH_ENTER, "距趋势下方还差 {x}σ")]
    target, dist, tpl = min(cands, key=lambda c: c[1])
    return {"target": target, "sigma": round(dist, 2), "label": tpl.replace("{x}", f"{max(dist, 0):.2f}"),
            "critical": bool(dist <= GROWTH_CRITICAL + 1e-9),
            "marginPct": round(max(0.0, min(1.0, dist / (GROWTH_ENTER - GROWTH_EXIT))) * 100)}


def growth_block(gp_row: dict) -> dict:
    st = gp_row["state"]
    dist = growth_distance(st, gp_row["z3"])
    label = GROWTH_TXT[st].replace("增长", "")
    return {
        "pmiLatest": gp_row["pmi"], "pmiMonth": gp_row["month"],
        "dev": round(gp_row["dev"], 2), "z": round(gp_row["z"], 2), "z3": round(gp_row["z3"], 2),
        "state": st, "level": "强" if st == 1 else "弱" if st == -1 else None,
        "levelLabel": label + ("（临界）" if dist["critical"] else ""),
        "critical": dist["critical"], "distance": dist,
        "trend": gp_row["trend"], "trendDelta": None if gp_row["trendDelta"] is None else round(gp_row["trendDelta"], 2),
        "basis": "PMI 总指数（东财接口无新订单分项）", "hysteresisBacktested": False,
    }


# ---------------- 象限 ----------------
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


def classify_point(rate_state: int | None, d60, g_state: int | None, z3, trend=None, critical: bool = False) -> dict:
    """definite（两轴均有方向）/ transitional（任一轴走平或趋势附近，给最近象限参考）/ undetermined（数据不足）。"""
    rdir = DIR_OF.get(rate_state) if rate_state is not None else None
    r_lean = rdir if rdir in ("up", "down") else DIR_OF.get(_sign(d60)) if _sign(d60) else None
    g_lean = g_state if g_state else _sign(z3)
    level = {1: "强", -1: "弱"}.get(g_state)
    lean_level = {1: "强", -1: "弱"}.get(g_lean)
    if rdir is None or g_state is None:
        return {"state": "undetermined", "stateLabel": "未判定", "quadrant": None, "subState": None,
                "leanQuadrant": None, "leanSubState": None, "rateDir": rdir, "rateLean": r_lean, "confidence": None}
    if rdir in ("up", "down") and level:
        q = quadrant_of(level, rdir)
        return {"state": "definite", "stateLabel": QUADRANT_META[q]["name"], "quadrant": q,
                "subState": sub_state(q, trend), "leanQuadrant": None, "leanSubState": None,
                "rateDir": rdir, "rateLean": r_lean, "confidence": "中低" if critical else "中"}
    label = BOTH_NEUTRAL_LABEL if (rdir == "flat" and not level) else TRANSITIONAL_LABEL if rdir == "flat" else GROWTH_NEUTRAL_LABEL
    lq = quadrant_of(lean_level, r_lean)
    return {"state": "transitional", "stateLabel": label, "quadrant": None, "subState": None,
            "leanQuadrant": lq, "leanSubState": sub_state(lq, trend) if lq else None,
            "rateDir": rdir, "rateLean": r_lean, "confidence": "低"}


def summary_text(rate_dir: str | None, g: dict | None) -> str:
    gt = (GROWTH_TXT.get(g["state"]) + ("（临界）" if g.get("critical") else "")) if g else "增长未判定"
    return f"{gt}{'' if gt.endswith('）') else ' '}· {RATE_DIR_TXT.get(rate_dir, '利率未判定')}"


def _growth_at(gp: list[dict], month: str):
    row = None
    for r in gp:
        if r["month"] <= month:
            row = r
        else:
            break
    return row


def build_history(rp: list[dict], gp: list[dict], series: list[dict], months: int = HISTORY_MONTHS) -> list[dict]:
    """逐月末重算象限轨迹（只用当月末可得的数据：利率轴取月末交易日状态，增长轴取 ≤ 当月的最新 PMI）。"""
    by_month: dict[str, dict] = {}
    for r in rp:
        by_month[r["date"][:7]] = r
    hist = []
    for m in sorted(by_month)[-months:]:
        r = by_month[m]
        g = _growth_at(gp, m)
        gs = g["state"] if g else None
        crit = bool(g and growth_distance(gs, g["z3"])["critical"])
        c = classify_point(r["state"], r["d60"], gs, g["z3"] if g else None, g["trend"] if g else None, crit)
        hist.append({
            "month": m, "asOf": r["date"], "y10": series[r["idx"]]["value"], "d10y60bp": round(r["d60"], 1),
            "thresholdBp": round(r["thr"], 1), "exitBp": round(r["exit"], 1), "ratePending": r["pending"],
            "rateDir": c["rateDir"], "rateLean": c["rateLean"],
            "z3": round(g["z3"], 2) if g else None, "growthState": gs, "growthMonth": g["month"] if g else None,
            "growthTrend": g["trend"] if g else None,
            "state": c["state"], "stateLabel": c["stateLabel"], "confidence": c["confidence"],
            "quadrant": c["quadrant"], "subState": c["subState"],
            "leanQuadrant": c["leanQuadrant"], "leanSubState": c["leanSubState"],
        })
    return hist


def rate_backtest(rp: list[dict], series: list[dict], reversal_bp: float = 30.0) -> dict:
    """复核 PM 回测口径：切换次数/年（按 250 交易日/年）、状态持续中位数、<10 日状态占比、≥30bp 拐点识别滞后中位数。"""
    if not rp:
        return {}
    states = [r["state"] for r in rp]
    n = len(states)
    switches = sum(1 for i in range(1, n) if states[i] != states[i - 1])
    runs, k = [], 1
    for i in range(1, n):
        if states[i] == states[i - 1]:
            k += 1
        else:
            runs.append(k)
            k = 1
    runs.append(k)
    runs_sorted = sorted(runs)
    med = runs_sorted[len(runs_sorted) // 2] if len(runs_sorted) % 2 else (runs_sorted[len(runs_sorted) // 2 - 1] + runs_sorted[len(runs_sorted) // 2]) / 2
    # zigzag 拐点（与 dz_backtest.py 一致：自 σ 可用日起，丢弃第一个点）
    start = rp[0]["idx"]
    ys = [(series[i]["date"], series[i]["value"] * 100) for i in range(start, len(series))]
    pts, hi, lo = [], ys[0][1], ys[0][1]
    hii = loi = ys[0][0]
    dirn = 0
    for t, v in ys:
        if v > hi:
            hi, hii = v, t
        if v < lo:
            lo, loi = v, t
        if dirn >= 0 and v <= hi - reversal_bp:
            pts.append((hii, "top"))
            dirn, lo, loi = -1, v, t
        elif dirn <= 0 and v >= lo + reversal_bp:
            pts.append((loi, "bottom"))
            dirn, hi, hii = 1, v, t
    pts = pts[1:]
    dates = [r["date"] for r in rp]
    lags = []
    for t, kind in pts:
        want = -1 if kind == "top" else 1
        i0 = next((i for i, d in enumerate(dates) if d >= t), None)
        if i0 is None:
            continue
        hit = next((i for i in range(i0, n) if states[i] == want), None)
        if hit is not None:
            lags.append(hit - i0)
    lags.sort()
    lag_med = (lags[len(lags) // 2] if len(lags) % 2 else (lags[len(lags) // 2 - 1] + lags[len(lags) // 2]) / 2) if lags else None
    return {"from": rp[0]["date"], "to": rp[-1]["date"], "tradingDays": n,
            "switchesPerYear": round(switches / (n / 250), 1), "switches": switches,
            "medianStateDays": med, "whipsawPct": round(sum(1 for x in runs if x < 10) / len(runs) * 100),
            "medianLagDays": lag_med, "turningPoints": len(lags)}


def _reading_label(block: dict | None) -> str | None:
    if not block or block.get("status") != "ok":
        return None
    if block.get("quadrant"):
        return f"{block['quadrant']} {block.get('quadrantName') or ''}".strip()
    lq = block.get("leanQuadrant")
    return f"{block.get('stateLabel') or '过渡期'}（最近 {lq or '—'}，参考）"


def _days_between(a: str | None, b: str | None):
    from datetime import date as _d
    try:
        return (_d.fromisoformat(b[:10]) - _d.fromisoformat(a[:10])).days
    except Exception:  # noqa: BLE001
        return None


def signal_switch(old_block: dict | None, new_block: dict, today: str | None) -> dict | None:
    """读数变化 → 记「信号切换」；旧块口径版本不同 → cause=methodology（附口径说明）。标签保留 14 个自然日。"""
    old_lbl, new_lbl = _reading_label(old_block), _reading_label(new_block)
    prev = (old_block or {}).get("signalSwitch")
    if old_lbl and new_lbl and old_lbl != new_lbl:
        method = (old_block or {}).get("methodVersion") != METHOD_VERSION
        sw = {"date": today or new_block.get("asOf"), "asOf": new_block.get("asOf"), "from": old_lbl, "to": new_lbl,
              "cause": "methodology" if method else "market",
              "note": METHOD_SWITCH_NOTE if method else "按既定规则切换（口径未变）"}
    elif prev and old_lbl == new_lbl:
        sw = dict(prev)
    else:
        return None
    age = _days_between(sw.get("date"), today or new_block.get("asOf"))
    sw["active"] = age is not None and 0 <= age <= SIGNAL_TAG_DAYS
    return sw


def merge_history(old: list[dict] | None, new: list[dict], months: int = HISTORY_MONTHS) -> list[dict]:
    """新算结果覆盖同月；旧口径条目（无 thresholdBp）不再保留，避免新旧口径混排。"""
    by = {h["month"]: h for h in (old or []) if h.get("month") and "thresholdBp" in h}
    for h in new:
        by[h["month"]] = h
    return [by[k] for k in sorted(by)][-months:]


def _method_block() -> dict:
    return {
        "version": METHOD_VERSION,
        "rate": (f"10Y 国债 {RATE_LOOKBACK} 交易日变化 d；σ = d 的滚动 {RATE_SIGMA_WINDOW} 交易日标准差；进入线 T = max({RATE_FLOOR_BP:.0f}bp, "
                 f"{RATE_K_ENTER}σ)，退出线 = T/2；新状态连续 {RATE_PERSIST} 个交易日成立才切换；无 60 日均线条件"),
        "growth": (f"制造业 PMI 总指数 − 近 {PMI_TREND_WINDOW} 月均值 → {PMI_Z_WINDOW} 月滚动标准化 z → 3 月均值 z3；"
                   f"z3 ≥ +{GROWTH_ENTER} 进入高于趋势 / ≤ −{GROWTH_ENTER} 进入低于趋势，回到 ±{GROWTH_EXIT} 以内退回趋势附近（滞回阈值尚未回测）"),
        "quadrant": "两轴均有方向 → 确定象限；任一轴走平/趋势附近 → 过渡期（最近象限仅作参考）",
        "backtestPM": BACKTEST_PM,
        "growthReference": "宏观分析师参考：2026-09 PMI 50.1，偏离 +0.42，z 0.72（月度序列 growth_axis.csv 逐月核对一致）",
        "usPriorSource": "overseas_clock_du2021.json（美国 1994 年以来，年化总回报）",
    }


def compute_rate_clock(series: list[dict], pmi: list[dict], old_block: dict | None = None,
                       today: str | None = None) -> dict:
    base = {
        "_comment": "增长×利率 REITs 投资时钟（杜丽虹 2021 框架中国化，2026-09-30 校准口径）；仅作宏观背景，不改变 advice.sectorViews；见 docs/rate-clock.md",
        "methodVersion": METHOD_VERSION,
        "method": _method_block(),
        "sources": {"y10": CGB10Y_SOURCE, "pmi": PMI_SOURCE},
        "computedAt": today,
    }
    old_hist = (old_block or {}).get("history") or []
    rp = rate_state_path(series) if len(series) > RATE_LOOKBACK + RATE_SIGMA_WINDOW else []
    gp = growth_path(pmi)
    if not rp or not gp:
        base.update({
            "status": "unavailable",
            "statusNote": (f"10Y（需 >{RATE_LOOKBACK + RATE_SIGMA_WINDOW} 个交易日）或 PMI（需 ≥{PMI_TREND_WINDOW + PMI_Z_WINDOW + 1} 个月）"
                           "真实序列取数失败/不足，象限未判定（不插值、不沿用手工值）"),
            "quadrant": None, "history": old_hist,
            "asOf": (old_block or {}).get("asOf"),
        })
        return base
    cur = rp[-1]
    g = growth_block(gp[-1])
    rdist = rate_distance(cur["state"], cur["d60"], cur["thr"], cur["exit"], cur["pending"], cur["raw"])
    crit = rdist["critical"] or g["critical"]
    c = classify_point(cur["state"], cur["d60"], g["state"], gp[-1]["z3"], g["trend"], crit)
    q, sub = c["quadrant"], c["subState"]
    hist = merge_history(old_hist, build_history(rp, gp, series))
    chg, d0, d1 = rate_change_bp(series)

    def prior_of(qq, ss):
        if not qq:
            return None
        return Q4_SPLIT_PRIOR[ss] if qq == "Q4" and ss in Q4_SPLIT_PRIOR else QUADRANT_META[qq]["usPrior"]

    notes = [f"10Y 60日变化 {cur['d60']:+.1f}bp，进入线 ±{cur['thr']:.1f}bp（σ {cur['sigma']:.1f}bp×{RATE_K_ENTER}，下限 {RATE_FLOOR_BP:.0f}bp）、"
             f"退出线 ±{cur['exit']:.1f}bp → {RATE_DIR_TXT[DIR_OF[cur['state']]]}；{rdist['label']}"]
    notes.append(f"PMI 偏离 z3 {gp[-1]['z3']:+.2f}σ → {GROWTH_TXT[g['state']]}；{g['distance']['label']}"
                 + ("（临界）" if g["critical"] else ""))
    if c["state"] == "transitional":
        notes.append(f"不判定象限，最近象限 {c['leanQuadrant'] or '—'} 仅作参考")
    base.update({
        "status": "ok",
        "asOf": d1,
        "y10": series[-1]["value"], "y10Start": series[-1 - RATE_LOOKBACK]["value"], "y10StartDate": d0,
        "d10y60bp": round(cur["d60"], 1), "sigma60bp": round(cur["sigma"], 1),
        "thresholdBp": round(cur["thr"], 1), "exitBp": round(cur["exit"], 1),
        "thresholdFloored": cur["thr"] <= RATE_FLOOR_BP + 1e-9,
        "rateDir": c["rateDir"], "rateLean": c["rateLean"], "rawRateDir": DIR_OF[cur["raw"]],
        "ratePending": cur["pending"], "rateDistance": rdist,
        "state": c["state"], "stateLabel": c["stateLabel"],
        "summary": summary_text(c["rateDir"], g),
        "confidence": c["confidence"],
        "confidenceNote": "；".join(notes),
        "growth": g,
        "quadrant": q, "quadrantName": QUADRANT_META[q]["name"] if q else c["stateLabel"],
        "subState": sub, "usPriorAnnualReturn": prior_of(q, sub),
        "leanQuadrant": c["leanQuadrant"], "leanSubState": c["leanSubState"],
        "leanQuadrantName": QUADRANT_META[c["leanQuadrant"]]["name"] if c["leanQuadrant"] else None,
        "leanUsPriorAnnualReturn": prior_of(c["leanQuadrant"], c["leanSubState"]),
        "leanNote": "仅作参考：过渡期按两轴偏向推得的最近象限，不参与硬冲突判定" if c["state"] == "transitional" else None,
        "backtest": rate_backtest(rp, series),
        "rotation": rotation_of(hist),
        "history": hist,
    })
    base["signalSwitch"] = signal_switch(old_block, base, today)
    return base


# ---------------- 社融脉冲（单独预警卡，不并入增长轴） ----------------
def _month_add(m: str, k: int) -> str:
    y, mm = int(m[:4]), int(m[5:7]) - 1 + k
    return f"{y + mm // 12:04d}-{mm % 12 + 1:02d}"


def gdp_quarterly(cum_rows: list[dict]) -> dict:
    """年内累计 → 单季（Q1 = 累计；其余 = 本季累计 − 上季累计，要求上季存在）。"""
    cum = {r["month"]: r["cum"] for r in cum_rows}
    out = {}
    for m, v in cum.items():
        if m[5:7] == "03":
            out[m] = v
        else:
            p = _month_add(m, -3)
            if p in cum and p[:4] == m[:4]:
                out[m] = v - cum[p]
    return out


def gdp_ttm(cum_rows: list[dict]) -> dict:
    """季末月 → 近 4 个季度名义 GDP 之和（需连续 4 个季度）。"""
    q = gdp_quarterly(cum_rows)
    out = {}
    for m in q:
        ks = [_month_add(m, -3 * i) for i in range(4)]
        if all(k in q for k in ks):
            out[m] = sum(q[k] for k in ks)
    return out


def tsf_impulse_series(tsf: list[dict], gdp_cum: list[dict]) -> list[dict]:
    """impulse(t) = (Σ社融增量[t-11..t] − Σ[t-23..t-12]) / 近4季名义GDP(≤t 的最新季末) × 100。"""
    v = {r["month"]: r["value"] for r in tsf}
    ttm = gdp_ttm(gdp_cum)
    qs = sorted(ttm)
    out = []
    for m in sorted(v):
        ks = [_month_add(m, -i) for i in range(24)]
        if not all(k in v for k in ks):
            continue
        qm = next((x for x in reversed(qs) if x <= m), None)
        if qm is None:
            continue
        now = sum(v[k] for k in ks[:12])
        prev = sum(v[k] for k in ks[12:])
        out.append({"month": m, "value": (now - prev) / ttm[qm] * 100, "gdpQuarter": qm})
    return out


TSF_INTERPRETATION = ("与 REITs 5–7 个月后的 3 个月收益负相关（相关系数约 −0.45，样本 2021-10 起约 55–60 个月，只看方向）；"
                      "脉冲由正转负，往往提示约 6 个月后 REITs 环境更好。单独预警，不并入增长轴。")


def compute_tsf_impulse(tsf: list[dict], gdp_cum: list[dict], today: str | None = None, origin: dict | None = None) -> dict:
    base = {"_comment": "社融脉冲领先预警（单独卡片，不并入增长轴）；见 docs/rate-clock.md §2.4",
            "formula": "(近12个月社融增量之和 − 上年同期12个月之和) / 近4个季度名义GDP × 100%",
            "interpretation": TSF_INTERPRETATION,
            "sources": {"tsf": TSF_SOURCE, "gdp": GDP_SOURCE}, "seriesOrigin": origin or {}, "computedAt": today}
    ser = tsf_impulse_series(tsf, gdp_cum)
    if not ser:
        base.update({"status": "pending", "label": "待接入", "asOf": None, "value": None,
                     "reason": "社融增量或名义 GDP 真实序列不可用/不足 24 个月，不展示任何数值"})
        return base
    last = ser[-1]
    y, m = last["month"].split("-")
    flip = None
    for i in range(len(ser) - 1, 0, -1):
        a, b = _sign(ser[i - 1]["value"]), _sign(ser[i]["value"])
        if a and b and a != b:
            flip = {"month": ser[i]["month"], "direction": "正转负" if b < 0 else "负转正"}
            break
    lag = None
    if today:
        lag = (int(today[:4]) - int(y)) * 12 + int(today[5:7]) - int(m)
    base.update({
        "status": "ok", "label": None, "asOf": last["month"], "asOfLabel": f"数据截至 {int(m)}月（{y}-{m}）",
        "value": round(last["value"], 2), "gdpQuarter": last["gdpQuarter"],
        "prev": round(ser[-2]["value"], 2) if len(ser) > 1 else None,
        "change3m": round(last["value"] - ser[-4]["value"], 2) if len(ser) > 3 else None,
        "lastFlip": flip, "monthsBehind": lag,
        "staleNote": f"社融源最新只到 {y}-{m}，较当前滞后 {lag} 个月" if lag and lag > 2 else None,
        "series": [[r["month"], round(r["value"], 2)] for r in ser[-36:]],
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
        tag = f"参考·{clock.get('stateLabel') or TRANSITIONAL_LABEL}（最近象限 {q} {clock.get('leanQuadrantName') or ''}，Δ10Y {clock.get('d10y60bp')}bp）"
    else:
        return []
    gnote = "；增长处临界（距切换线 ≤0.05σ）" if (clock.get("growth") or {}).get("critical") else ""
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
