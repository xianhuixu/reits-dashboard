#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""产权类公募 REITs 分派率利差（真实数据版）→ data_panel_l1l7.json.propertySpread / propertyYieldSeries

口径移植自固收投资经理交付的 /workspace/reits_equity_spread/build_spread.py（README 规则逐条保留），
只把取数换成纯 urllib（CI 只装 pandas，没有 akshare）：
  价格 : 新浪 CN_MarketData.getKLineData（不复权日收盘；与 akshare fund_etf_hist_sina 同源）
  分派 : 东方财富 F10 分红送配详情 fundf10.eastmoney.com/fhsp_{code}.html（= akshare fund_open_fund_info_em 同页）
  份额 : 东方财富 F10 规模变动 FundArchivesDatas.aspx?type=gmbd 季末期末总份额（亿份）
  10Y  : macro_series.json.cgb10y（update_cycle_data.py 已每日刷新的中债 10Y；与时钟同一序列）
原始数据缓存在 spread_cache/（prices.csv / dists.csv / units.csv，入库）。

规则（README）：
- 分派事件：除息日相距 ≤45 天合并为一个事件；首个事件视为 stub；≥2 个事件才纳入
- 上市 <365 天：年化 = 第2..k 个事件现金和 × 365 / (ex_k − ex_1)，间隔需 ≥80 天
- 其余 TTM = 除息日在 (t−365, t] 的分派之和；窗口内事件跨度 ≥330 天则剔除最早一个
- 聚合：市值加权（价格×季末份额）与截面中位数；利差 = 收益率 − 10Y（bp）
- 分位：pct_expanding = 2022-01-01 以来；pct_rolling3y = 过去 3 年窗口（2025-01-01 起才给值）；
  pct_since_n10 = 截面 ≥10 只之后的历史（稳健性）
本仓库新增：
- 停牌/本次未取到最新价的个券：最后收盘价向后沿用到全市场最新交易日（只填尾部，历史不变）
- 分派同比：每只产权 REIT 的 TTM 分派 vs 一年前 TTM 分派（两端均有值，即上市满一年），截面中位数，±2% 容差
- 租金 vs 利率：10Y 一年均值变化（与 TTM 同窗口）为利率顺风，TTM 分派率 × 分派同比中位数为分派拖累
- 状态：本次 --refresh 价格与分派取数覆盖率均 ≥90% → ok；否则沿用缓存、status=lagged（前端「滞后 · 数据截至 MM-DD」）

用法：
  python3 scripts/build_spread.py --refresh     # 取数 + 计算 + 写 data_panel_l1l7.json / data_panel.js
  python3 scripts/build_spread.py               # 仅用缓存重算（status=lagged）
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "spread_cache"
PANEL_JSON = ROOT / "data_panel_l1l7.json"
PANEL_JS = ROOT / "data_panel.js"
UNIVERSE_JSON = ROOT / "universe.json"
MACRO_JSON = ROOT / "macro_series.json"

PCT_START = pd.Timestamp("2022-01-01")
YOY_TOL_PCT = 2.0
COVERAGE_OK = 0.9
TRAP_PCTILE = 80.0
SHORT_HISTORY_DAYS = 365
GATE_LOOKBACK = 60          # 交易日
FETCH_BUDGET_S = 420        # 整轮取数时间上限（海外 CI 不可达时尽快放弃）
SOURCE = ("新浪 CN_MarketData 日收盘（不复权）· 东方财富 F10 分红送配详情 / 规模变动（季末份额）· "
          "中债 10Y（macro_series.json，东财 RPTA_WEB_TREASURYYIELD）")
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://fundf10.eastmoney.com/"}


# ---------------------------------------------------------------- 取数（纯 urllib）
def _get(url: str, timeout: int = 12, headers: dict | None = None) -> str:
    req = urllib.request.Request(url, headers=headers or UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def fetch_prices(code: str, n: int = 60) -> pd.DataFrame:
    sym = ("sh" if code.endswith(".SH") else "sz") + code[:6]
    url = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
           f"?symbol={sym}&scale=240&ma=no&datalen={n}")
    rows = json.loads(_get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"}) or "null") or []
    out = [(r["day"][:10], float(r["close"])) for r in rows if r.get("day") and float(r.get("close") or 0) > 0]
    if not out:
        raise ValueError("empty kline")
    return pd.DataFrame(out, columns=["date", "close"])


def parse_dists_html(html: str) -> pd.DataFrame:
    m = re.search(r"<table class='w782 comm cfxq'>(.*?)</table>", html, re.S)
    if not m:
        raise ValueError("分红送配表缺失")
    out = []
    for tr in re.findall(r"<tr>(.*?)</tr>", m.group(1), re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(cells) < 4:
            continue  # 表头或「暂无分红信息」
        mm = re.search(r"每(\d+)份派现金([\d.]+)元", cells[3])
        if mm and re.match(r"\d{4}-\d{2}-\d{2}", cells[2]):
            out.append((cells[2][:10], float(mm.group(2)) / float(mm.group(1))))
    return pd.DataFrame(out, columns=["ex", "cash"])


def fetch_dists(code: str) -> pd.DataFrame:
    return parse_dists_html(_get(f"https://fundf10.eastmoney.com/fhsp_{code[:6]}.html"))


def parse_units_html(t: str) -> pd.DataFrame:
    rec = []
    for d, rest in re.findall(r"<tr><td>(\d{4}-\d{2}-\d{2})</td>(.*?)</tr>", t):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", rest)
        v = pd.to_numeric(cells[2] if len(cells) > 2 else None, errors="coerce")
        if pd.notna(v):
            rec.append((d, float(v)))
    return pd.DataFrame(rec, columns=["date", "units_yi"])


def fetch_units(code: str) -> pd.DataFrame:
    if "gmbd_apidata" not in (t := _get(f"https://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=gmbd&mode=0&code={code[:6]}&rt=0.5")):
        raise ValueError("规模变动接口返回异常")
    return parse_units_html(t)


# ---------------------------------------------------------------- 缓存
COLS = {"prices": ["code", "date", "close"], "dists": ["code", "ex", "cash"], "units": ["code", "date", "units_yi"]}

def load_cache(cache_dir: Path = CACHE) -> dict:
    def rd(kind):
        p = cache_dir / f"{kind}.csv"
        return pd.read_csv(p, dtype={"code": str}) if p.exists() else pd.DataFrame(columns=COLS[kind])
    return {k: rd(k) for k in COLS}


def save_cache(c: dict, cache_dir: Path = CACHE) -> None:
    cache_dir.mkdir(exist_ok=True)
    c["prices"].sort_values(["code", "date"]).to_csv(cache_dir / "prices.csv", index=False)
    c["dists"].sort_values(["code", "ex"]).to_csv(cache_dir / "dists.csv", index=False)
    c["units"].sort_values(["code", "date"]).to_csv(cache_dir / "units.csv", index=False)


def refresh_cache(c: dict, codes: list[str], fetchers: dict | None = None, budget_s: float = FETCH_BUDGET_S) -> dict:
    """逐只增量取数并并入缓存；任何失败沿用缓存。返回取数诊断（覆盖率决定 ok / lagged）。"""
    f = {"prices": fetch_prices, "dists": fetch_dists, "units": fetch_units, **(fetchers or {})}
    t0 = time.time()
    diag = {k: {"ok": 0, "failed": []} for k in ("prices", "dists", "units")}
    dead = set()   # 连续 5 只全失败的源视为本轮不可达（海外 CI），不再浪费时间
    streak = {k: 0 for k in diag}
    for code in codes:
        for kind in ("prices", "dists", "units"):
            if kind in dead or time.time() - t0 > budget_s:
                diag[kind]["failed"].append(code)
                continue
            old = c[kind][c[kind]["code"] == code]
            try:
                if kind == "prices":
                    new = f["prices"](code, 60 if len(old) > 200 else 1023)
                elif kind == "dists":
                    new = f["dists"](code)
                    if new.empty and len(old):
                        raise ValueError("分派表返回空，缓存非空")
                else:
                    new = f["units"](code)
                    if new.empty:
                        raise ValueError("份额表为空")
                new = new.assign(code=code)
                if kind == "prices":   # 增量：同日以新数据为准
                    merged = pd.concat([old[~old["date"].isin(new["date"])], new])
                else:                  # 分派 / 份额：整表替换
                    merged = new
                c[kind] = pd.concat([c[kind][c[kind]["code"] != code], merged[COLS[kind]]], ignore_index=True)
                diag[kind]["ok"] += 1
                streak[kind] = 0
            except Exception as e:  # noqa: BLE001
                diag[kind]["failed"].append(code)
                streak[kind] += 1
                if streak[kind] >= 5 and diag[kind]["ok"] == 0:
                    print(f"[spread] {kind} 源连续 5 只失败，本轮放弃（{e!r}）")
                    dead.add(kind)
            time.sleep(0.05)
    diag["elapsedS"] = round(time.time() - t0, 1)
    return diag


# ---------------------------------------------------------------- 计算（PM 口径）
def cluster_ids(ex: np.ndarray, gap: int = 45) -> np.ndarray:
    ids, cur, last = [], -1, None
    for e in ex:
        if last is None or (e - last) / np.timedelta64(1, "D") > gap:
            cur += 1
        ids.append(cur)
        last = e
    return np.array(ids, dtype=int)


def reit_series(px: pd.Series, dv: pd.DataFrame, listing: pd.Timestamp) -> pd.DataFrame:
    idx = px.index
    ttm = pd.Series(np.nan, idx)
    method = pd.Series("", idx, dtype=object)
    if dv.empty:
        return pd.DataFrame({"ttm_dist": ttm, "method": "no_dist"})
    ex = dv["ex"].values.astype("datetime64[ns]")
    cash = dv["cash"].values.astype(float)
    cid = cluster_ids(ex)
    nev = cid.max() + 1
    evx = np.array([ex[cid == i].min() for i in range(nev)])
    for t in idx:
        tt = np.datetime64(t)
        paid = ex <= tt
        evc = np.array([cash[(cid == i) & paid].sum() for i in range(nev)])
        k = int((evx <= tt).sum())
        if k == 0:
            method[t] = "pre_first_dist"
            continue
        span = (evx[k - 1] - evx[0]) / np.timedelta64(1, "D")
        age = (t - listing).days
        if k == 1:
            method[t] = "no_full_period"
        elif age < 365 and span < 365:
            if span >= 80:
                ttm[t] = evc[1:k].sum() * 365.0 / span
                method[t] = "annualized_young"
            else:
                method[t] = "young_span<80d"
        else:
            inw = np.where(evx[:k] > np.datetime64(t - pd.Timedelta(days=365)))[0]
            while len(inw) > 1 and (evx[inw[-1]] - evx[inw[0]]) / np.timedelta64(1, "D") >= 330:
                inw = inw[1:]
            ttm[t] = evc[inw].sum()
            method[t] = "ttm"
    return pd.DataFrame({"ttm_dist": ttm, "method": method})


def pct_rank(vals: np.ndarray, x: float) -> float:
    vals = vals[~np.isnan(vals)]
    return float("nan") if len(vals) == 0 or np.isnan(x) else float((vals <= x).mean() * 100)


def y10_series(macro: dict) -> pd.Series:
    s = (macro.get("cgb10y") or {}).get("series") or []
    return pd.Series([r["value"] for r in s], index=pd.to_datetime([r["date"] for r in s]), dtype=float).sort_index()


def per_reit_frame(uni: list[dict], cache: dict) -> tuple[pd.DataFrame, list[dict]]:
    """逐只日度 TTM 分派 / 市值。尾部缺价沿用最后收盘价到全市场最新交易日。"""
    prices, dists, units = cache["prices"], cache["dists"], cache["units"]
    last_all = pd.to_datetime(prices["date"]).max() if len(prices) else None
    frames, issues = [], []
    for u in uni:
        code = u["code"]
        p = prices[prices["code"] == code]
        if p.empty:
            issues.append({"code": code, "name": u["name"], "reason": "无价格数据"})
            continue
        px = pd.Series(p["close"].astype(float).values, index=pd.to_datetime(p["date"])).sort_index()
        px = px[px > 0]
        px = px[~px.index.duplicated(keep="last")]
        if last_all is not None and px.index[-1] < last_all:   # 尾部沿用（停牌 / 本次未取到）
            tail = pd.bdate_range(px.index[-1] + pd.Timedelta(days=1), last_all)
            tail = tail.intersection(pd.to_datetime(prices["date"]).unique())
            px = pd.concat([px, pd.Series(px.iloc[-1], index=tail)])
        d = dists[dists["code"] == code]
        dv = pd.DataFrame({"ex": pd.to_datetime(d["ex"]), "cash": d["cash"].astype(float)}).sort_values("ex").reset_index(drop=True)
        un_df = units[units["code"] == code]
        un = pd.Series(un_df["units_yi"].astype(float).values * 1e8, index=pd.to_datetime(un_df["date"])).sort_index()
        un = un[~un.index.duplicated(keep="last")]
        if dv.empty:
            issues.append({"code": code, "name": u["name"], "reason": "尚无分派记录"})
        if un.empty:
            issues.append({"code": code, "name": u["name"], "reason": "缺季末份额（不计入市值加权）"})
        s = reit_series(px, dv, px.index.min())
        s["close"] = px
        if not un.empty:
            s["units"] = un.reindex(un.index.union(px.index)).ffill().reindex(px.index).fillna(un.iloc[0])
        else:
            s["units"] = np.nan
        s["mcap"] = s["close"] * s["units"]
        s["ttm_yield"] = s["ttm_dist"] / s["close"] * 100
        s["code"], s["name"], s["sector"] = code, u["name"], u["sector"]
        frames.append(s.reset_index(names="date"))
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), issues


def _agg(g: pd.DataFrame) -> pd.Series:
    g = g[g["ttm_yield"].notna()]
    w = g[g["mcap"].notna()]
    return pd.Series({"n": len(g), "n_mcap": len(w),
                      "mcap": np.average(w["ttm_yield"], weights=w["mcap"]) if len(w) else np.nan,
                      "median": g["ttm_yield"].median() if len(g) else np.nan})


def aggregate(P: pd.DataFrame, y10: pd.Series) -> pd.DataFrame:
    V = P[P["ttm_yield"].notna()]
    A = V.groupby("date")[["ttm_yield", "mcap"]].apply(_agg)
    dates = pd.DatetimeIndex(sorted(A.index))
    y = y10.reindex(y10.index.union(dates)).ffill().reindex(dates)
    D = pd.DataFrame(index=dates)
    D["n_reits"], D["n_mcap"] = A["n"], A["n_mcap"]
    D["yield_mcap"], D["yield_median"], D["y10"] = A["mcap"], A["median"], y
    D["spread_mcap_bp"] = (D["yield_mcap"] - D["y10"]) * 100
    D["spread_median_bp"] = (D["yield_median"] - D["y10"]) * 100
    D = D[D["n_reits"].fillna(0) > 0]
    for col, tag in (("spread_mcap_bp", "mcap"), ("spread_median_bp", "median")):
        s = D[col]
        vals, idx = s.values, s.index
        pe, pr = [], []
        for i, t in enumerate(idx):
            if t < PCT_START:
                pe.append(np.nan); pr.append(np.nan); continue
            pe.append(pct_rank(vals[(idx >= PCT_START) & (idx <= t)], vals[i]))
            ws = t - pd.DateOffset(years=3)
            pr.append(pct_rank(vals[(idx > ws) & (idx <= t)], vals[i]) if ws >= PCT_START - pd.Timedelta(days=1) else np.nan)
        D[f"pct_expanding_{tag}"], D[f"pct_rolling3y_{tag}"] = pe, pr
        n10 = D.index[D["n_reits"] >= 10]
        start10 = n10[0] if len(n10) else None
        D[f"pct_since_n10_{tag}"] = [pct_rank(vals[(idx >= start10) & (idx <= t)], vals[i]) if start10 is not None and t >= start10 else np.nan
                                     for i, t in enumerate(idx)]
    return D


def sector_aggregate(P: pd.DataFrame, y10: pd.Series) -> pd.DataFrame:
    V = P[P["ttm_yield"].notna()]
    S = V.groupby(["date", "sector"])[["ttm_yield", "mcap"]].apply(_agg).reset_index()
    y = y10.reindex(y10.index.union(pd.DatetimeIndex(S["date"].unique()))).ffill()
    S["y10"] = S["date"].map(y)
    S["spread_mcap_bp"] = (S["mcap"] - S["y10"]) * 100
    S["spread_median_bp"] = (S["median"] - S["y10"]) * 100
    S["pct_expanding_mcap"] = np.nan
    for _, g in S.groupby("sector"):
        g = g.sort_values("date")
        vals, dts = g["spread_mcap_bp"].values, g["date"].values
        out = [pct_rank(vals[(dts >= np.datetime64(PCT_START)) & (dts <= dts[i])], vals[i]) if dts[i] >= np.datetime64(PCT_START) else np.nan
               for i in range(len(g))]
        S.loc[g.index, "pct_expanding_mcap"] = out
    return S


def yoy_state(median_pct: float | None, tol: float = YOY_TOL_PCT) -> str | None:
    if median_pct is None or not np.isfinite(median_pct):
        return None
    return "增长" if median_pct > tol else "下滑" if median_pct < -tol else "企稳"


def dist_yoy(P: pd.DataFrame, asof: pd.Timestamp) -> dict:
    """每只 TTM 分派 vs 一年前 TTM 分派（两端均有值），截面中位数 ±2% 容差。"""
    t0 = asof - pd.Timedelta(days=365)
    rows = []
    for code, g in P.groupby("code"):
        g = g.sort_values("date")
        a, b = g[g["date"] <= asof], g[g["date"] <= t0]
        if a.empty or b.empty:
            continue
        da, db = a["ttm_dist"].iloc[-1], b["ttm_dist"].iloc[-1]
        if pd.isna(da) or pd.isna(db) or db <= 0:
            continue
        rows.append({"code": code, "name": a["name"].iloc[-1], "sector": a["sector"].iloc[-1],
                     "ttmNow": round(float(da), 5), "ttmYearAgo": round(float(db), 5), "yoyPct": round((da / db - 1) * 100, 2)})
    if not rows:
        return {"n": 0, "medianPct": None, "state": None, "bySector": [], "perReit": []}
    R = pd.DataFrame(rows)
    med = float(R["yoyPct"].median())
    by = []
    for sec, g in R.groupby("sector"):
        m = float(g["yoyPct"].median())
        by.append({"sector": sec, "n": int(len(g)), "medianPct": round(m, 1), "nDown": int((g["yoyPct"] < -YOY_TOL_PCT).sum()),
                   "state": yoy_state(m)})
    return {"asOf": asof.strftime("%Y-%m-%d"), "yearAgo": t0.strftime("%Y-%m-%d"), "n": int(len(R)), "medianPct": round(med, 2),
            "nDown": int((R["yoyPct"] < -YOY_TOL_PCT).sum()), "nUp": int((R["yoyPct"] > YOY_TOL_PCT).sum()),
            "tolerancePct": YOY_TOL_PCT, "state": yoy_state(med),
            "method": "TTM 对 TTM（每只 t 与 t−365 天的 TTM 分派；两端均有值 = 分派记录满一年）· 截面中位数（市值加权会被新发大盘首年分派带偏）· ±2% 容差",
            "bySector": sorted(by, key=lambda r: r["medianPct"]), "perReit": sorted(rows, key=lambda r: r["yoyPct"])}


def rent_vs_rate(y10: pd.Series, asof: pd.Timestamp, ttm_yield_mcap: float, yoy_median_pct: float | None) -> dict:
    """利率顺风（10Y 一年均值变化，与 TTM 同窗口；点对点作次要）vs 分派拖累（TTM 分派率 × 分派同比中位数）。"""
    y = y10[y10.index <= asof].dropna()
    t1, t2 = asof - pd.Timedelta(days=365), asof - pd.Timedelta(days=730)
    cur, prev = y[y.index > t1], y[(y.index > t2) & (y.index <= t1)]
    if cur.empty or prev.empty or yoy_median_pct is None:
        return {"status": "pending", "note": "10Y 或分派同比不足一年"}
    avg_now, avg_prev = float(cur.mean()), float(prev.mean())
    ya = y[y.index <= t1]
    p2p = (float(y.iloc[-1]) - float(ya.iloc[-1])) * 100 if len(ya) else None
    tail = -(avg_now - avg_prev) * 100                 # 10Y 下行 = 正顺风（bp）
    drag = ttm_yield_mcap * yoy_median_pct / 100 * 100  # 分派率(%) × 同比(%) → bp
    net = tail + drag
    if abs(net) < 2:
        dom, txt = "balanced", "利率顺风与分派拖累大致相抵"
    elif net < 0:
        dom, txt = "distribution", "分派拖累占优：租金（分派）回落快过利率下行"
    else:
        dom, txt = "rate", "利率顺风占优：利率下行快过分派回落"
    return {"status": "ok", "asOf": asof.strftime("%Y-%m-%d"),
            "y10Avg1y": round(avg_now, 3), "y10AvgPrev1y": round(avg_prev, 3), "rateTailwindBp": round(tail, 1),
            "y10Now": round(float(y.iloc[-1]), 3), "y10YearAgo": round(float(ya.iloc[-1]), 3) if len(ya) else None,
            "pointToPointBp": round(p2p, 1) if p2p is not None else None,
            "ttmYieldMcap": round(ttm_yield_mcap, 2), "distYoYMedianPct": round(yoy_median_pct, 2),
            "distDragBp": round(drag, 1), "netBp": round(net, 1), "dominant": dom, "text": txt,
            "method": "利率顺风 = −(近 1 年 10Y 日均 − 前 1 年日均)，与 TTM 分派同窗口；点对点（t vs t−365）仅作次要参考。"
                      "分派拖累 = 市值加权 TTM 分派率 × 分派同比中位数。"}


def weekly_rows(D: pd.DataFrame) -> list[dict]:
    """L2 图用周频（每周最后一个交易日 + 最新一日）。pctile = 滚动 3 年分位（默认），pctileFull = 2022 年以来分位。"""
    wk = D.groupby(D.index.to_period("W-FRI")).tail(1)
    if wk.index[-1] != D.index[-1]:
        wk = pd.concat([wk, D.tail(1)])
    out = []
    for t, r in wk.iterrows():
        def f(v, nd):
            return None if pd.isna(v) else round(float(v), nd)
        out.append({"date": t.strftime("%Y-%m-%d"), "ttmYield": f(r["yield_mcap"], 3), "y10": f(r["y10"], 3),
                    "spread": f(r["spread_mcap_bp"] / 100, 4), "pctile": f(r["pct_rolling3y_mcap"] / 100, 4),
                    "pctileFull": f(r["pct_expanding_mcap"] / 100, 4), "n": int(r["n_reits"])})
    return out


def sector_rows(S: pd.DataFrame, asof: pd.Timestamp, yoy: dict) -> list[dict]:
    by = {r["sector"]: r for r in yoy.get("bySector") or []}
    out = []
    for sec, g in S.groupby("sector"):
        g = g.sort_values("date")
        last = g[g["date"] <= asof].iloc[-1]
        days = int((last["date"] - g["date"].iloc[0]).days)
        y = by.get(sec)
        pct = None if pd.isna(last["pct_expanding_mcap"]) else round(float(last["pct_expanding_mcap"]), 1)
        trap = bool(pct is not None and pct >= TRAP_PCTILE and y and y["state"] == "下滑")
        out.append({"sector": sec, "nReits": int(last["n"]), "yieldMcap": round(float(last["mcap"]), 3),
                    "spreadBp": round(float(last["spread_mcap_bp"]), 1), "spreadMedianBp": round(float(last["spread_median_bp"]), 1),
                    "pctFull": pct, "historyDays": days, "since": g["date"].iloc[0].strftime("%Y-%m-%d"),
                    "shortHistory": days < SHORT_HISTORY_DAYS,
                    "distYoYPct": y["medianPct"] if y else None, "distYoYN": y["n"] if y else 0,
                    "distNDown": y["nDown"] if y else 0, "distState": y["state"] if y else None, "valueTrap": trap})
    return sorted(out, key=lambda r: -r["spreadBp"])


def compute(uni: list[dict], cache: dict, macro: dict) -> dict:
    P, issues = per_reit_frame(uni, cache)
    y10 = y10_series(macro)
    D = aggregate(P, y10)
    S = sector_aggregate(P, y10)
    asof = D.index[-1]
    last = D.iloc[-1]
    yoy = dist_yoy(P, asof)
    rvr = rent_vs_rate(y10, asof, float(last["yield_mcap"]), yoy.get("medianPct"))
    g0 = D.iloc[-1 - GATE_LOOKBACK] if len(D) > GATE_LOOKBACK else None
    gate = None
    if g0 is not None and pd.notna(g0["pct_rolling3y_mcap"]) and pd.notna(last["pct_rolling3y_mcap"]):
        gate = {"pctileChangePP": round(float(last["pct_rolling3y_mcap"] - g0["pct_rolling3y_mcap"]), 1),
                "from": g0.name.strftime("%Y-%m-%d"), "to": asof.strftime("%Y-%m-%d"), "basis": "滚动 3 年分位（市值加权），60 个交易日"}
    def r(v, nd=1):
        return None if pd.isna(v) else round(float(v), nd)
    return {
        "asOf": asof.strftime("%Y-%m-%d"),
        "coverage": {"included": int(last["n_reits"]), "mcapWeighted": int(last["n_mcap"]), "universe": len(uni),
                     "excluded": [i for i in issues if i["reason"] != "缺季末份额（不计入市值加权）"] or [],
                     "issues": issues},
        "latest": {"ttmYieldMcap": r(last["yield_mcap"], 3), "ttmYieldMedian": r(last["yield_median"], 3), "y10": r(last["y10"], 3),
                   "spreadBp": r(last["spread_mcap_bp"]), "spreadMedianBp": r(last["spread_median_bp"]),
                   "pctRolling3y": r(last["pct_rolling3y_mcap"]), "pctFull": r(last["pct_expanding_mcap"]),
                   "pctSinceN10": r(last["pct_since_n10_mcap"]), "pctRolling3yMedian": r(last["pct_rolling3y_median"]),
                   "pctFullMedian": r(last["pct_expanding_median"]), "defaultPct": "pctRolling3y"},
        "gate60d": gate,
        "distYoY": yoy,
        "rentVsRate": rvr,
        "sectors": sector_rows(S, asof, yoy),
        "series": weekly_rows(D),
        "_daily": D,
    }


def build_block(res: dict, status: str, diag: dict | None, lag_reason: str | None, now: str) -> dict:
    blk = {k: v for k, v in res.items() if k not in ("series", "_daily")}
    blk.update({
        "status": status, "updated": now, "source": SOURCE,
        "label": "产权利差 = 市值加权 TTM 分派率 − 中债 10Y",
        "pctNote": "默认显示滚动 3 年分位；2022 年以来全样本分位见悬浮提示（2022—2023H1 截面仅 2–6 只，早期噪音大）",
        "method": "口径见 scripts/build_spread.py（移植固收 PM 交付规则：≤45 天合并分派事件、首期 stub、上市<365 天年化、TTM 防重复）",
        "fetch": diag or {"refresh": False},
    })
    if status != "ok":
        blk["lagReason"] = lag_reason or "本次未刷新，沿用缓存"
    return blk


def fetch_status(diag: dict | None, n: int) -> tuple[str, str | None]:
    if not diag:
        return "lagged", "未执行 --refresh，沿用缓存"
    pc = diag["prices"]["ok"] / max(n, 1)
    dc = diag["dists"]["ok"] / max(n, 1)
    if pc >= COVERAGE_OK and dc >= COVERAGE_OK:
        return "ok", None
    return "lagged", f"新浪/东财取数覆盖不足（价格 {diag['prices']['ok']}/{n}，分派 {diag['dists']['ok']}/{n}），沿用缓存"


def apply_to_panel(panel: dict, res: dict, block: dict) -> dict:
    panel["propertySpread"] = block
    panel["propertyYieldSeries"] = res["series"]
    sm = panel.setdefault("seedMeta", {})
    sm["propertyLive"] = True
    sm["propertySource"] = "live（scripts/build_spread.py）"
    sm["note"] = (
        "产权序列（propertyYieldSeries / propertySpread）为真实数据；"
        + ("经营权披露 IRR 截面（operatingDisclosedIrr）为 2025 年末口径真实数据；" if panel.get("operatingDisclosedIrr") else "")
        + "经营权 IRR 月度时序、bond10ySeries 月度锚点、sectorSnapshot 仍为 SEED"
    )
    return panel


def mark_lagged(panel: dict, reason: str) -> dict:
    """整轮计算失败：保留上一次结果，状态降为 lagged（绝不标 live）。"""
    blk = panel.get("propertySpread")
    if blk:
        blk["status"] = "lagged"
        blk["lagReason"] = reason
    return panel


def write_panel(panel: dict) -> None:
    PANEL_JSON.write_text(json.dumps(panel, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    PANEL_JS.write_text("window.REITS_DATA_PANEL = " + json.dumps(panel, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")


def run(refresh: bool = False, write: bool = True, fetchers: dict | None = None) -> dict:
    uni = [u for u in json.loads(UNIVERSE_JSON.read_text(encoding="utf-8")) if u.get("right") == "产权"]
    panel = json.loads(PANEL_JSON.read_text(encoding="utf-8"))
    macro = json.loads(MACRO_JSON.read_text(encoding="utf-8"))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cache = load_cache()
    diag = None
    if refresh:
        diag = refresh_cache(cache, [u["code"] for u in uni], fetchers)
        save_cache(cache)
    status, reason = fetch_status(diag, len(uni))
    res = compute(uni, cache, macro)
    block = build_block(res, status, diag, reason, now)
    apply_to_panel(panel, res, block)
    if write:
        write_panel(panel)
    L = block["latest"]
    print(f"[spread] {status} asOf={block['asOf']} n={block['coverage']['included']}/{block['coverage']['universe']} "
          f"TTM={L['ttmYieldMcap']}% 10Y={L['y10']}% spread={L['spreadBp']}bp pct3y={L['pctRolling3y']} full={L['pctFull']} "
          f"distYoY={block['distYoY'].get('medianPct')}%({block['distYoY'].get('n')}) {block['rentVsRate'].get('dominant')}")
    return panel


if __name__ == "__main__":
    run(refresh="--refresh" in sys.argv, write="--no-write" not in sys.argv)
