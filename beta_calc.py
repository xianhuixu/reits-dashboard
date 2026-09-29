#!/usr/bin/env python3
"""股/债 Beta 与 Δ10Y 敏感度（杜丽虹 2021「偏股型 / 偏债型」方法的中国化）。

- 周频（W-FRI 收盘）简单收益率；主窗口 104 周（数据不足时用可得周数，n<MIN_OBS 置空），滚动 52 周。
- betaEq  = Cov(r, r_沪深300)/Var(r_沪深300)；betaBond = Cov(r, r_上证国债)/Var(r_上证国债)。
- sens10y = 周收益(%) 对 周 Δ10Y(bp) 回归斜率 × 10 → 「10Y 每上行 10bp 的周收益 %」（负值=利率敏感/偏债）。
- 分类：中国 REITs 与股指相关性很低，Beta 普遍 ≪1，**不用 Beta>1 切分**；
  改用截面相对排序：score = z(betaEq) − z(betaBond)，前 1/3 偏股、后 1/3 偏债、中间中性。
- 与人工策略标签对照：防御型 期望偏债；周期型/扩张型 期望偏股；落在相反一端 → disagree。
纯计算、无网络；输入缺失时返回 status=pending，前端显示待计算，绝不填假数。
"""
from __future__ import annotations

import pandas as pd

WINDOW_WEEKS = 104
ROLL_WEEKS = 52
MIN_OBS = 40
EQ_CODE = "000300.SH"
BOND_CODE = "000012.SH"
EXPECTED_CLASS = {"防御型": "偏债", "周期型": "偏股", "扩张型": "偏股"}


def pending(reason: str) -> dict:
    return {"status": "pending", "reason": reason, "bySector": [], "byReit": [], "rolling": None}


def weekly_close(df):
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    return df.sort_index().resample("W-FRI").last()


def weekly_returns(df):
    return weekly_close(df).pct_change(fill_method=None)


def ols_beta(y, x, min_obs: int = MIN_OBS):
    j = pd.concat([y, x], axis=1).dropna()
    if len(j) < min_obs:
        return None, int(len(j))
    xv = j.iloc[:, 1]
    var = float(xv.var())
    if not var or var != var:
        return None, int(len(j))
    return float(j.iloc[:, 0].cov(xv)) / var, int(len(j))


def _r(v, n=3):
    return None if v is None else round(float(v), n)


def _zscores(vals: dict) -> dict:
    s = pd.Series({k: v for k, v in vals.items() if v is not None}, dtype=float)
    if len(s) < 3 or not s.std():
        return {}
    return ((s - s.mean()) / s.std()).to_dict()


def classify(by_code: dict) -> dict:
    """by_code: {code: {betaEq, betaBond}} → {code: (score, cls)}；截面三分位。"""
    ze = _zscores({k: v.get("betaEq") for k, v in by_code.items()})
    zb = _zscores({k: v.get("betaBond") for k, v in by_code.items()})
    scores = {k: ze[k] - zb[k] for k in by_code if k in ze and k in zb}
    if len(scores) < 3:
        return {}
    ranked = sorted(scores, key=lambda k: scores[k])
    n = len(ranked)
    out = {}
    for i, k in enumerate(ranked):
        cls = "偏债" if i < n / 3 else ("偏股" if i >= n - n / 3 else "中性")
        out[k] = (round(scores[k], 3), cls)
    return out


def compute_betas(reit_close, bench_close, universe, y10=None, window: int = WINDOW_WEEKS,
                  roll: int = ROLL_WEEKS, min_obs: int = MIN_OBS, eq: str = EQ_CODE, bond: str = BOND_CODE,
                  y10_source: str | None = None) -> dict:
    """reit_close / bench_close：日频收盘 DataFrame（DatetimeIndex × 代码）；y10：日频 10Y(%) Series 或 None。"""
    if bench_close is None or eq not in bench_close.columns or bond not in bench_close.columns:
        return pending(f"缺少基准 {eq}/{bond} 日线")
    if reit_close is None or reit_close.empty:
        return pending("缺少 REITs 日线")
    rw = weekly_returns(reit_close)
    bw = weekly_returns(bench_close[[eq, bond]])
    idx = rw.index.intersection(bw.index)
    rw, bw = rw.loc[idx], bw.loc[idx]
    dy = None
    if y10 is not None and len(y10):
        ys = pd.Series(y10).astype(float)
        ys.index = pd.to_datetime(ys.index)
        dy = (ys.sort_index().resample("W-FRI").last().diff() * 100).reindex(idx)  # bp
    rw_win, bw_win = rw.tail(window), bw.tail(window)
    dy_win = dy.tail(window) if dy is not None else None

    def one(series):
        be, n = ols_beta(series, bw_win[eq], min_obs)
        bb, _ = ols_beta(series, bw_win[bond], min_obs)
        s10 = None
        if dy_win is not None:
            s, _ = ols_beta(series * 100, dy_win, min_obs)
            s10 = None if s is None else s * 10
        return be, bb, s10, n

    meta = {u["code"]: u for u in universe}
    by_code = {}
    for c in rw_win.columns:
        if c not in meta:
            continue
        be, bb, s10, n = one(rw_win[c])
        by_code[c] = {"betaEq": be, "betaBond": bb, "sens10y": s10, "n": n}
    if not any(v["betaEq"] is not None for v in by_code.values()):
        return pending(f"周频样本不足（每只 < {min_obs} 周）")
    cls = classify(by_code)
    by_reit = []
    for c, v in by_code.items():
        u = meta[c]
        sc, cl = cls.get(c, (None, None))
        exp = EXPECTED_CLASS.get(u.get("strategy"))
        disagree = bool(cl and exp and cl != "中性" and cl != exp)
        by_reit.append({"code": c, "name": u.get("name"), "sector": u.get("sector"), "strategy": u.get("strategy"),
                        "betaEq": _r(v["betaEq"]), "betaBond": _r(v["betaBond"]), "sens10y": _r(v["sens10y"]),
                        "n": v["n"], "score": sc, "cls": cl, "expected": exp, "disagree": disagree})
    by_reit.sort(key=lambda x: (x["sector"] or "", x["code"]))

    sectors = sorted({u["sector"] for u in universe})
    sec_ret = {}
    by_sector = []
    for sec in sectors:
        cols = [u["code"] for u in universe if u["sector"] == sec and u["code"] in rw.columns]
        if not cols:
            continue
        sr = rw[cols].mean(axis=1, skipna=True)
        sr[rw[cols].notna().sum(axis=1) == 0] = float("nan")
        sec_ret[sec] = sr
        be, bb, s10, n = one(sr.tail(window))
        by_sector.append({"sector": sec, "members": len(cols), "betaEq": _r(be), "betaBond": _r(bb),
                          "sens10y": _r(s10), "n": n})
    sc_cls = classify({s["sector"]: s for s in by_sector})
    for s in by_sector:
        s["score"], s["cls"] = sc_cls.get(s["sector"], (None, None))
    ranked_eq = sorted([s for s in by_sector if s["betaEq"] is not None], key=lambda s: -s["betaEq"])
    for i, s in enumerate(ranked_eq):
        s["rankEq"] = i + 1

    # 52 周滚动（板块）
    roll_dates, roll_out = [], {sec: {"betaEq": [], "betaBond": []} for sec in sec_ret}
    min_roll = max(min(roll, min_obs), int(roll * 0.8))
    for end in range(roll, len(idx) + 1):
        roll_dates.append(idx[end - 1].strftime("%Y-%m-%d"))
        be_w, bb_w = bw[eq].iloc[end - roll:end], bw[bond].iloc[end - roll:end]
        for sec, sr in sec_ret.items():
            seg = sr.iloc[end - roll:end]
            be, _ = ols_beta(seg, be_w, min_roll)
            bb, _ = ols_beta(seg, bb_w, min_roll)
            roll_out[sec]["betaEq"].append(_r(be))
            roll_out[sec]["betaBond"].append(_r(bb))
    rolling = {"window": roll, "dates": roll_dates[-window:],
               "bySector": {k: {kk: vv[-window:] for kk, vv in v.items()} for k, v in roll_out.items()}} if roll_dates else None

    n_weeks = int(rw_win.dropna(how="all").shape[0])
    return {
        "status": "ok",
        "asOf": idx[-1].strftime("%Y-%m-%d") if len(idx) else None,
        "window": window, "weeksAvailable": n_weeks, "rollWindow": roll, "minObs": min_obs,
        "frequency": "weekly (W-FRI close)",
        "benchmarks": {"equity": f"{eq} 沪深300", "bond": f"{bond} 上证国债指数",
                       "rate": y10_source or ("10Y 国债收益率（macro_series.json）" if dy is not None else None)},
        "sens10yUnit": "10Y 每上行 10bp 的周收益 %" if dy is not None else None,
        "sens10yStatus": "ok" if dy is not None else "pending（10Y 日序列不可用）",
        "classRule": "截面相对排序：score=z(betaEq)−z(betaBond)，前1/3 偏股 / 后1/3 偏债 / 中间中性（中国 REITs 股性低，不用 Beta>1 绝对阈值）",
        "expectedByStrategy": EXPECTED_CLASS,
        "bySector": by_sector,
        "byReit": by_reit,
        "disagreements": [r["code"] for r in by_reit if r["disagree"]],
        "rolling": rolling,
    }


def y10_series_from_macro(macro: dict | None):
    """macro_series.json → pd.Series(日期→%)；无数据返回 None。"""
    rows = ((macro or {}).get("cgb10y") or {}).get("series") or []
    if not rows:
        return None
    return pd.Series({r["date"]: float(r["value"]) for r in rows if r.get("value") is not None})


def compute_betas_safe(reit_close, bench_close, universe, root=None) -> dict:
    """fetch_data*.py 调用入口：读取 macro_series.json 的真实 10Y；任何异常 → pending（不中断主流程）。"""
    import json
    from pathlib import Path
    try:
        macro = None
        p = Path(root or Path(__file__).resolve().parent) / "macro_series.json"
        if p.exists():
            macro = json.loads(p.read_text(encoding="utf-8"))
        y10 = y10_series_from_macro(macro)
        src = ((macro or {}).get("cgb10y") or {}).get("source")
        out = compute_betas(reit_close, bench_close, universe, y10=y10, y10_source=src)
        print(f"[beta] {out.get('status')} 周数 {out.get('weeksAvailable')} 不一致 {len(out.get('disagreements') or [])} 只"
              + (f" 原因 {out.get('reason')}" if out.get("status") != "ok" else ""), flush=True)
        return out
    except Exception as e:  # noqa: BLE001
        print(f"[beta] 计算失败: {e}", flush=True)
        return pending(f"计算失败: {e}")
