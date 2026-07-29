#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公募REITs 全量投研面板数据抓取脚本 v3（demo-1）
数据源：同花顺 iFinD（ifind 插件 ifind_tool.py）
覆盖：universe.json 全部上市公募 REITs（79 只）+ 大类资产基准 + 海外 REITs 代表标的
能力：上市以来全历史日线（增量缓存）、MACD/RSI/分位/流动性指标、
     六因子信号打分、信号事件流与历史回测、海外 REITs 走势
输出：data.js（window.REITS_DATA）与 data.json
手动维护文件（脚本只读不写）：fundamentals.json（季度）、cycle_judgment.json（月度）
"""
import json
import subprocess
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
IFIND_SCRIPT = Path(
    "/Users/lion/Library/Application Support/kimi-desktop/daimon-share/daimon/"
    "runtime/kimi-code/home/plugins/managed/ifind/scripts/ifind_tool.py"
)
HIST_START = "2021-06-21"          # 首批 REITs 上市日
HIST_DIR = ROOT / "hist_cache"     # 逐代码全历史增量缓存
SPARK_POINTS = 60
CORR_WINDOW = 130                  # 相关性口径：近 130 交易日
FETCH_PAUSE = 0.6                  # 取数间隔，避免限频

# 大类资产相关性基准（均已验证 iFinD 可取）
BENCHMARKS = {
    "399324.SZ": {"name": "深证红利", "group": "红利股", "note": "中证红利无数据，以深证红利替代"},
    "000012.SH": {"name": "上证国债", "group": "无风险利率", "note": "无风险利率/债性代理"},
    "000300.SH": {"name": "沪深300", "group": "权益", "note": "权益基准"},
    "399393.SZ": {"name": "国证地产", "group": "A股板块", "note": "对应：保租房"},
    "399995.SZ": {"name": "基建工程", "group": "A股板块", "note": "对应：产业园/市政环保"},
    "399808.SZ": {"name": "中证新能", "group": "A股板块", "note": "对应：能源"},
    "399437.SZ": {"name": "国证运输", "group": "A股板块", "note": "对应：高速公路"},
    "399353.SZ": {"name": "国证物流", "group": "A股板块", "note": "对应：仓储物流"},
    "399935.SZ": {"name": "中证信息", "group": "A股板块", "note": "对应：数据中心"},
    "000932.SH": {"name": "中证消费", "group": "A股板块", "note": "对应：消费"},
}
SECTOR_PEER = {
    "保租房": "399393.SZ", "产业园": "399995.SZ", "市政环保": "399995.SZ",
    "能源": "399808.SZ", "高速公路": "399437.SZ", "仓储物流": "399353.SZ",
    "数据中心": "399935.SZ", "消费": "000932.SH",
}
# 海外 REITs 代表标的（已验证 iFinD 美股 .N/.O 可取；取不到自动跳过）
OVERSEAS = {
    "PLD.N": {"name": "Prologis", "market": "美国", "type": "工业物流"},
    "O.N": {"name": "Realty Income", "market": "美国", "type": "零售/净租赁"},
    "AMT.N": {"name": "American Tower", "market": "美国", "type": "基础设施"},
    "EQIX.O": {"name": "Equinix", "market": "美国", "type": "数据中心"},
    "AVB.N": {"name": "AvalonBay", "market": "美国", "type": "住宅"},
    "WELL.N": {"name": "Welltower", "market": "美国", "type": "医疗"},
    "SPG.N": {"name": "Simon Property", "market": "美国", "type": "购物中心"},
    "0823.HK": {"name": "领展房产基金", "market": "中国香港", "type": "综合"},
}


# ---------------- iFinD 基础取数 ----------------
def ifind_price(codes, start, end, retries=2):
    """拉取日行情，失败退避重试。返回 DataFrame 或 None。"""
    for attempt in range(retries + 1):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            fp = f.name
        params = {"ticker": ",".join(codes), "start_date": start, "end_date": end,
                  "file_path": fp, "interval": "D", "adjust": "none"}
        try:
            subprocess.run([sys.executable, str(IFIND_SCRIPT), "call",
                            "--api-name", "ifind_get_price",
                            "--params-json", json.dumps(params)],
                           capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            time.sleep(4 * (attempt + 1))
            continue
        p = Path(fp)
        if p.exists() and p.stat().st_size > 10:
            try:
                return pd.read_csv(fp)
            except Exception:
                return None
        time.sleep(4 * (attempt + 1))
    return None


def fetch_history(code, end):
    """逐代码全历史，hist_cache 增量更新；iFinD 单次查询有约 2-3 年区间上限，分段抓取。"""
    HIST_DIR.mkdir(exist_ok=True)
    cache = HIST_DIR / (code.replace(".", "_") + ".csv")
    old = None
    start = HIST_START
    if cache.exists():
        try:
            old = pd.read_csv(cache, dtype={"time": str})
            if len(old) and "time" in old.columns:
                start = (pd.to_datetime(old["time"]).max() + timedelta(days=1)).date().isoformat()
        except Exception:
            old = None
    if start <= end:
        parts = []
        seg = date.fromisoformat(start)
        e = date.fromisoformat(end)
        while seg <= e:                          # 700 天一段，规避区间上限
            seg_end = min(seg + timedelta(days=700), e)
            d = ifind_price([code], seg.isoformat(), seg_end.isoformat(), retries=1)
            if d is not None and "thscode" in d.columns and len(d):
                parts.append(d)
            time.sleep(0.6)
            seg = seg_end + timedelta(days=1)
        if parts:
            new = pd.concat(parts, ignore_index=True)
            df = pd.concat([old, new], ignore_index=True) if old is not None else new
            df["time"] = df["time"].astype(str).apply(
                lambda t: f"{t[:4]}-{t[4:6]}-{t[6:]}" if len(t.strip()) == 8 and t.strip().isdigit() else t.strip()
            )
            df = df.drop_duplicates(subset=["thscode", "time"]).sort_values("time")
            df.to_csv(cache, index=False)
            return df
        if old is not None and len(old):        # 增量失败时用缓存兜底
            return old
        return None
    return old


# ---------------- 指标计算 ----------------
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, pd.NA)
    return 100 - 100 / (1 + rs)


def indicators(s_close, s_amt):
    """s_close/s_amt：单只 REITs 收盘价/成交额序列（索引为日期）。返回指标 dict。"""
    out = {}
    n = len(s_close)
    last = float(s_close.iloc[-1])
    # MACD
    dif = ema(s_close, 12) - ema(s_close, 26)
    dea = ema(dif, 9)
    hist = (dif - dea) * 2
    cross = None
    if n >= 2:
        d0, d1 = float((dif - dea).iloc[-2]), float((dif - dea).iloc[-1])
        if d0 <= 0 < d1:
            cross = "golden"
        elif d0 >= 0 > d1:
            cross = "death"
    out["macd"] = {"dif": round(float(dif.iloc[-1]), 4), "dea": round(float(dea.iloc[-1]), 4),
                   "hist": round(float(hist.iloc[-1]), 4), "cross": cross}
    # RSI14
    r = rsi(s_close)
    out["rsi14"] = round(float(r.iloc[-1]), 1) if pd.notna(r.iloc[-1]) else None
    # 历史分位与 250 日线乖离
    out["pctRank"] = round(float((s_close < last).mean() * 100), 1)
    if n >= 250:
        ma250 = float(s_close.rolling(250).mean().iloc[-1])
        out["devMA250"] = round((last / ma250 - 1) * 100, 2)
    else:
        out["devMA250"] = None
    # 流动性
    if len(s_amt) >= 60:
        amt20 = float(s_amt.tail(20).mean())
        amt60 = float(s_amt.tail(60).mean())
        out["amt20"] = round(amt20, 0)
        out["amtRatio"] = round(amt20 / amt60, 2) if amt60 else None
    else:
        out["amt20"] = round(float(s_amt.mean()), 0) if len(s_amt) else None
        out["amtRatio"] = None
    # 累计与波动
    out["sinceIPO"] = round((last / float(s_close.iloc[0]) - 1) * 100, 2) if n > 1 else None
    if n > 20:
        out["volAnn"] = round(float(s_close.pct_change().dropna().std() * (244 ** 0.5) * 100), 1)
    else:
        out["volAnn"] = None
    return out


# ---------------- 信号事件 ----------------
def detect_events(code, name, s_close, s_amt, days=120):
    """检测 MACD 交叉 / RSI 超买超卖 / 成交异动 / 突破250日线。返回全部事件（含历史，供回测）。"""
    events = []
    n = len(s_close)
    if n < 40:
        return events
    dif = ema(s_close, 12) - ema(s_close, 26)
    dea = ema(dif, 9)
    diff = dif - dea
    r = rsi(s_close)
    amt60 = s_amt.rolling(60).mean()
    ma250 = s_close.rolling(250).mean()
    dates = s_close.index
    for i in range(1, n):
        dt = dates[i].strftime("%Y-%m-%d")
        if diff.iloc[i - 1] <= 0 < diff.iloc[i]:
            events.append({"code": code, "name": name, "date": dt, "type": "MACD金叉", "i": i})
        elif diff.iloc[i - 1] >= 0 > diff.iloc[i]:
            events.append({"code": code, "name": name, "date": dt, "type": "MACD死叉", "i": i})
        rv = r.iloc[i]
        if pd.notna(rv) and pd.notna(r.iloc[i - 1]):
            if r.iloc[i - 1] <= 70 < rv:
                events.append({"code": code, "name": name, "date": dt, "type": "RSI超买",
                               "value": round(float(rv), 1), "i": i})
            elif r.iloc[i - 1] >= 30 > rv:
                events.append({"code": code, "name": name, "date": dt, "type": "RSI超卖",
                               "value": round(float(rv), 1), "i": i})
        a6 = amt60.iloc[i]
        if pd.notna(a6) and a6 > 0 and s_amt.iloc[i] > 2 * a6:
            events.append({"code": code, "name": name, "date": dt, "type": "成交异动",
                           "value": round(float(s_amt.iloc[i] / a6), 1), "i": i})
        m2 = ma250.iloc[i]
        if pd.notna(m2) and pd.notna(ma250.iloc[i - 1]):
            if s_close.iloc[i - 1] <= ma250.iloc[i - 1] and s_close.iloc[i] > m2:
                events.append({"code": code, "name": name, "date": dt, "type": "突破250日线", "i": i})
    return events


def backtest_events(all_events, close_map):
    """每类事件：出现后 5/20 交易日的平均收益与胜率。close_map: code -> close Series。"""
    bt = {}
    for etype in ["MACD金叉", "MACD死叉", "RSI超买", "RSI超卖", "成交异动", "突破250日线"]:
        rets5, rets20 = [], []
        for e in all_events:
            if e["type"] != etype or e["code"] not in close_map:
                continue
            s = close_map[e["code"]]
            i = e["i"]
            if i + 5 < len(s):
                rets5.append(float(s.iloc[i + 5] / s.iloc[i] - 1))
            if i + 20 < len(s):
                rets20.append(float(s.iloc[i + 20] / s.iloc[i] - 1))
        def stat(x):
            if not x:
                return None
            return {"n": len(x), "avg": round(sum(x) / len(x) * 100, 2),
                    "win": round(sum(1 for v in x if v > 0) / len(x) * 100, 1)}
        bt[etype] = {"d5": stat(rets5), "d20": stat(rets20)}
    return bt


# ---------------- 六因子信号 ----------------
def score_signals(reits, fund, corr_ret, bench_ret, bond10y):
    """六因子打分（-2 ~ +2）。corr_ret: REITs 日收益 DataFrame（近窗口）；bench_ret: 基准收益。"""
    # 流动性：amt20 全市场分位
    amt_list = sorted([r["amt20"] for r in reits if r.get("amt20")])
    def liq_score(a):
        if a is None or not amt_list:
            return 0
        p = sum(1 for x in amt_list if x < a) / len(amt_list)
        return 2 if p >= 0.8 else 1 if p >= 0.6 else 0 if p >= 0.4 else -1 if p >= 0.2 else -2

    def rsi_score(v):
        if v is None:
            return 0
        return 1 if v >= 70 else 2 if v >= 55 else 0 if v >= 45 else -1 if v >= 30 else -2

    def flow_score(v):
        if v is None:
            return 0
        return 2 if v >= 1.5 else 1 if v >= 1.1 else 0 if v >= 0.9 else -1 if v >= 0.7 else -2

    def perf_score(code):
        f = fund.get(code) if fund else None
        if not f or f.get("achieveRate") is None:
            return 0
        a = f["achieveRate"]
        return 2 if a >= 95 else 1 if a >= 90 else -1 if a >= 85 else -2

    def spread_score(code):
        f = fund.get(code) if fund else None
        if not f or f.get("distYield") is None or bond10y is None:
            return 0
        sp = f["distYield"] - bond10y
        return 2 if sp >= 4.5 else 1 if sp >= 3.5 else 0 if sp >= 2.5 else -1 if sp >= 1.5 else -2

    # 股债联动：个券近窗口与沪深300相关性 − 与国债相关性
    def sb_score(code):
        if corr_ret is None or code not in corr_ret.columns:
            return 0
        if "000300.SH" not in bench_ret.columns or "000012.SH" not in bench_ret.columns:
            return 0
        j = pd.concat([corr_ret[code], bench_ret["000300.SH"], bench_ret["000012.SH"]], axis=1).dropna()
        if len(j) < 20:
            return 0
        diff = float(j.iloc[:, 0].corr(j.iloc[:, 1]) - j.iloc[:, 0].corr(j.iloc[:, 2]))
        return 2 if diff >= 0.5 else 1 if diff >= 0.25 else 0 if diff >= -0.25 else -1 if diff >= -0.5 else -2

    for r in reits:
        f = {"liquidity": liq_score(r.get("amt20")), "sentiment": rsi_score(r.get("rsi14")),
             "moneyflow": flow_score(r.get("amtRatio")), "performance": perf_score(r["code"]),
             "spread": spread_score(r["code"]), "stockbond": sb_score(r["code"])}
        total = sum(f.values())
        avg = total / 6.0
        r["signals"] = {**f, "total": total,
                        "label": "偏强" if avg >= 1 else "偏弱" if avg <= -1 else "中性"}
    return reits


def load_json(name):
    p = ROOT / name
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def main():
    universe = json.loads((ROOT / "universe.json").read_text(encoding="utf-8"))
    codes = [u["code"] for u in universe]
    end = date.today().isoformat()

    # ---------- 1. REITs 全历史 ----------
    frames, fetched = [], set()
    for i, c in enumerate(codes):
        df = fetch_history(c, end)
        if df is not None and "thscode" in df.columns:
            frames.append(df)
            fetched.add(c)
        time.sleep(FETCH_PAUSE)
        if (i + 1) % 10 == 0 or i + 1 == len(codes):
            print(f"[reits {i + 1}/{len(codes)}] 已获取 {len(fetched)}", flush=True)
    if not frames:
        raise SystemExit("取数全部失败，未更新数据")
    df = pd.concat(frames, ignore_index=True)
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time")
    close = df.pivot_table(index="time", columns="thscode", values="close").sort_index()
    vol = df.pivot_table(index="time", columns="thscode", values="volume").sort_index()
    amt = close * vol                                # 估算成交额
    dates = [d.strftime("%Y-%m-%d") for d in close.index]

    # ---------- 2. 基准指数全历史 ----------
    bench_frames = []
    for bc in BENCHMARKS:
        bdf = fetch_history(bc, end)
        if bdf is not None and "thscode" in bdf.columns:
            bench_frames.append(bdf)
        time.sleep(FETCH_PAUSE)
    bclose = None
    if bench_frames:
        bdf = pd.concat(bench_frames, ignore_index=True)
        bdf["time"] = pd.to_datetime(bdf["time"])
        bclose = bdf.pivot_table(index="time", columns="thscode", values="close").sort_index()

    # ---------- 3. 海外 REITs（取不到自动跳过） ----------
    overseas = []
    for oc, meta in OVERSEAS.items():
        odf = fetch_history(oc, end)
        time.sleep(FETCH_PAUSE)
        if odf is None or "thscode" not in odf.columns or not len(odf):
            print(f"[overseas] {oc} 无数据，跳过", flush=True)
            continue
        odf["time"] = pd.to_datetime(odf["time"])
        os_ = odf.set_index("time")["close"].dropna().sort_index()
        if len(os_) < 30:
            continue
        tail = os_.tail(250)
        overseas.append({
            "code": oc, **meta,
            "dates": [d.strftime("%Y-%m-%d") for d in tail.index],
            "norm": [round(float(v / tail.iloc[0] * 100), 2) for v in tail],
            "ret1y": round(float((os_.iloc[-1] / os_.iloc[-245] - 1) * 100), 2) if len(os_) > 245 else None,
            "sinceStart": round(float((os_.iloc[-1] / os_.iloc[0] - 1) * 100), 2),
        })
        print(f"[overseas] {oc} ok", flush=True)

    # ---------- 4. 个券指标 ----------
    fund_raw = load_json("fundamentals.json") or {}
    fund = {f["code"]: f for f in fund_raw.get("items", [])} if isinstance(fund_raw, dict) else {}
    cycle = load_json("cycle_judgment.json") or {}
    bond10y = cycle.get("bond10y")

    reits = []
    close_map = {}
    for u in universe:
        c = u["code"]
        if c not in close.columns:
            continue
        s = close[c].dropna()
        if len(s) < 2:
            continue
        a = amt[c].reindex(s.index).fillna(0)
        close_map[c] = s
        last, prev = s.iloc[-1], s.iloc[-2]

        def ret(n):
            return round(float((last / s.iloc[-n - 1] - 1) * 100), 2) if len(s) > n else None

        ind = indicators(s, a)
        last_vol = float(vol[c].dropna().iloc[-1]) if c in vol.columns and len(vol[c].dropna()) else None
        reits.append({
            "code": c, "name": u["name"], "sector": u["sector"],
            "right": u["right"], "strategy": u["strategy"],
            "close": round(float(last), 3),
            "pct": round(float((last / prev - 1) * 100), 2),
            "ret5": ret(5), "ret20": ret(20), "ret60": ret(60),
            "volume": int(last_vol) if last_vol else None,
            "amount": round(float(last * last_vol), 0) if last_vol else None,
            "spark": [round(float(x), 3) for x in s.tail(SPARK_POINTS)],
            "histDates": [d.strftime("%Y-%m-%d") for d in s.index],
            "histClose": [round(float(x), 3) for x in s],
            **ind,
        })

    sectors = sorted({u["sector"] for u in universe})
    strategies = ["防御型", "周期型", "成长型"]

    # ---------- 5. 相关性（近 130 交易日口径） ----------
    corr_payload = None
    cret_w, bret_w = None, None
    if bclose is not None:
        bret = bclose.pct_change()
        cret = close.pct_change()
        cret_w, bret_w = cret.tail(CORR_WINDOW), bret.tail(CORR_WINDOW)
        groups = {"全市场": codes}
        for st in strategies:
            groups[st] = [u["code"] for u in universe if u["strategy"] == st]
        for sec in sectors:
            groups[sec] = [u["code"] for u in universe if u["sector"] == sec]

        def port_ret(code_list):
            cols = [c for c in code_list if c in cret_w.columns]
            return cret_w[cols].mean(axis=1) if cols else pd.Series(dtype=float)

        def pearson(a, b):
            j = pd.concat([a, b], axis=1).dropna()
            if len(j) < 20:
                return None
            return round(float(j.iloc[:, 0].corr(j.iloc[:, 1])), 2)

        bcodes = [c for c in BENCHMARKS if c in bret_w.columns]
        benchmarks_meta = [{"code": c, **BENCHMARKS[c]} for c in bcodes]
        matrix = {}
        for gname, gcodes in groups.items():
            pr = port_ret(gcodes)
            matrix[gname] = {bc: pearson(pr, bret_w[bc]) for bc in bcodes}
        scatter = []
        if "000012.SH" in bret_w.columns and "000300.SH" in bret_w.columns:
            for sec in sectors:
                pr = port_ret(groups[sec])
                scatter.append({"sector": sec, "bond": pearson(pr, bret_w["000012.SH"]),
                                "equity": pearson(pr, bret_w["000300.SH"])})
        peers = []
        for sec, bc in SECTOR_PEER.items():
            if bc not in bret_w.columns:
                continue
            pr = port_ret(groups.get(sec, []))
            bser = bclose[bc].dropna().tail(CORR_WINDOW)
            peers.append({
                "sector": sec, "peerCode": bc, "peerName": BENCHMARKS[bc]["name"],
                "corr": pearson(pr, bret_w[bc]),
                "reitRet": round(float((pr.dropna().add(1).prod() - 1) * 100), 2) if len(pr.dropna()) else None,
                "peerRet": round(float((bser.iloc[-1] / bser.iloc[0] - 1) * 100), 2) if len(bser) > 1 else None,
            })
        corr_payload = {"benchmarks": benchmarks_meta, "matrix": matrix,
                        "scatter": scatter, "peers": peers}
        print(f"[corr] 基准 {len(benchmarks_meta)} 个", flush=True)

    # ---------- 6. 六因子信号 ----------
    reits = score_signals(reits, fund, cret_w, bret_w if bclose is not None else None, bond10y)
    strat_signals = {}
    for st in strategies:
        members = [r for r in reits if r["strategy"] == st]
        if members:
            avg_total = sum(r["signals"]["total"] for r in members) / len(members)
            strat_signals[st] = {"avg": round(avg_total, 1),
                                 "label": "偏强" if avg_total / 6 >= 1 else "偏弱" if avg_total / 6 <= -1 else "中性"}

    # ---------- 6.5 资产重估状态（高善文"资产重估理论"框架） ----------
    # 理论：实体经济回报下降 + 流动性过剩 → 资金溢出追逐资产 → 类债资产系统性重估
    # 排他性可验证预测：① 利率下行（国债指数上涨）② 成交额中枢抬升（60日均 > 250日均）
    # ③ 市场宽度扩张（20日上涨家数占比 >50%）④ 估值分位抬升（全市场历史分位均值 >50%）
    revaluation = None
    try:
        rv_items = []
        score = 0
        if bclose is not None and "000012.SH" in bclose.columns:
            bs = bclose["000012.SH"].dropna()
            if len(bs) > 60:
                b60 = round(float((bs.iloc[-1] / bs.iloc[-61] - 1) * 100), 2)
                ok = b60 > 0
                score += ok
                rv_items.append({"name": "利率下行趋势", "value": f"国债指数60日 {b60:+.2f}%",
                                 "ok": bool(ok), "desc": "无风险利率下行是重估的核心驱动力"})
        mkt_amt = amt[[c for c in amt.columns]].mean(axis=1)
        if len(mkt_amt) >= 250:
            a60, a250 = float(mkt_amt.tail(60).mean()), float(mkt_amt.tail(250).mean())
            ratio = a60 / a250 if a250 else 0
            ok = ratio > 1
            score += ok
            rv_items.append({"name": "资金中枢抬升", "value": f"60/250日成交额比 {ratio:.2f}",
                             "ok": bool(ok), "desc": "流动性过剩溢出至 REITs 市场的直接证据"})
        cret20 = close.pct_change().tail(20)
        breadth = float((cret20 > 0).mean(axis=1).mean() * 100)
        ok = breadth > 50
        score += ok
        rv_items.append({"name": "市场宽度扩张", "value": f"20日上涨占比 {breadth:.0f}%",
                         "ok": bool(ok), "desc": "重估应从防御型扩散至全市场"})
        ranks = [r["pctRank"] for r in reits if r.get("pctRank") is not None]
        if ranks:
            avg_rank = sum(ranks) / len(ranks)
            ok = avg_rank > 50
            score += ok
            rv_items.append({"name": "估值分位抬升", "value": f"全市场历史分位均值 {avg_rank:.0f}%",
                             "ok": bool(ok), "desc": "价格系统性站上历史中枢是重估的结果验证"})
        stage = {4: "重估进行中", 3: "重估初期", 2: "重估酝酿", 1: "重估暂停", 0: "重估缺席"}[score]
        revaluation = {"score": score, "stage": stage, "items": rv_items}
        print(f"[reval] {stage} ({score}/4)", flush=True)
    except Exception as e:
        print(f"[reval] 计算失败: {e}", flush=True)

    # ---------- 7. 信号事件与回测 ----------
    all_events = []
    for u in universe:
        c = u["code"]
        if c not in close_map:
            continue
        a = amt[c].reindex(close_map[c].index).fillna(0)
        all_events.extend(detect_events(c, u["name"], close_map[c], a))
    cutoff = (date.today() - timedelta(days=120)).isoformat()
    recent_events = sorted([{k: v for k, v in e.items() if k != "i"} for e in all_events if e["date"] >= cutoff],
                           key=lambda x: x["date"], reverse=True)[:200]
    backtest = backtest_events(all_events, close_map)
    print(f"[events] 近120日 {len(recent_events)} 条，回测 {len(backtest)} 类", flush=True)

    # ---------- 8. 组合指数序列（近 250 日） ----------
    close_w = close.tail(250)

    def eq_index(code_list):
        cols = [c for c in code_list if c in close_w.columns]
        sub = close_w[cols].dropna(how="all")
        if sub.empty:
            return []
        base = close_w[cols].loc[sub.index[0]]
        out = []
        for dt in close_w.index:
            if dt < sub.index[0]:
                out.append(None)  # 板块尚无成员上市的日期以前端空值补齐，保证与全局日期轴对齐
                continue
            m = (close_w[cols].loc[dt] / base * 100.0).mean()
            out.append(round(float(m), 2) if pd.notna(m) else None)
        return out

    wdates = [d.strftime("%Y-%m-%d") for d in close_w.index]
    payload = {
        "updated": pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d %H:%M:%S"),
        "lastTradeDate": dates[-1] if dates else None,
        "count": len(reits),
        "sectors": sectors,
        "strategies": strategies,
        "reits": reits,
        "correlation": corr_payload,
        "overseas": overseas,
        "stratSignals": strat_signals,
        "revaluation": revaluation,
        "events": recent_events,
        "backtest": backtest,
        "cycle": cycle or None,
        "fundamentals": fund_raw.get("items", []) if isinstance(fund_raw, dict) else [],
        "overseasStatic": load_json("overseas_static.json"),
        "series": {
            "dates": wdates,
            "market": eq_index(codes),
            "bySector": {sec: eq_index([u["code"] for u in universe if u["sector"] == sec]) for sec in sectors},
            "byStrategy": {st: eq_index([u["code"] for u in universe if u["strategy"] == st]) for st in strategies},
            "byRight": {r: eq_index([u["code"] for u in universe if u["right"] == r]) for r in ("产权", "经营权")},
        },
    }

    js = "window.REITS_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n"
    (ROOT / "data.js").write_text(js, encoding="utf-8")
    (ROOT / "data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    missing = [u["name"] for u in universe if u["code"] not in fetched]
    print(f"[done] {len(reits)}/{len(universe)} 只，截至 {payload['lastTradeDate']}，"
          f"data.js {len(js) / 1e6:.1f}MB", flush=True)
    if missing:
        print("[miss] " + "、".join(missing))


if __name__ == "__main__":
    main()
