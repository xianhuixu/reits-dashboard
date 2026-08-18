#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚠️ DEPRECATED — 此脚本已不再使用，请改用 fetch_data_server_v2.py。

公募REITs 全量投研面板数据抓取脚本 - 服务器版本 (方案B)
数据源：stock_finance_data (同花顺) via OpenClaw 工具 / akshare / yfinance

本脚本默认 DATA_SOURCE="mock" 直接返回 None，仅作为占位实现。
实际服务器端数据生成见 fetch_data_server_v2.py(基于 hist_cache 离线生成)。
保留此文件仅供历史参考，预计在下一个大版本移除。
"""
覆盖：universe.json 全部上市公募 REITs + 大类资产基准 + 海外 REITs 代表标的
能力：上市以来全历史日线、MACD/RSI/分位/流动性指标、六因子信号打分、
     信号事件流与历史回测、海外 REITs 走势
输出：data.js（window.REITS_DATA）与 data.json

NOTE: 当前服务器环境对东方财富/同花顺直接访问受限，
      行情数据建议仍由本地 Mac (iFinD) 维护，服务器端仅作备份/兜底。
      信息流更新（fetch_news.py）可在服务器正常运行。
"""
import json
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
HIST_START = "2021-06-21"          # 首批 REITs 上市日
HIST_DIR = ROOT / "hist_cache"     # 逐代码全历史增量缓存
SPARK_POINTS = 60
CORR_WINDOW = 130                  # 相关性口径：近 130 交易日
FETCH_PAUSE = 1.5                  # 取数间隔，避免限频

# 大类资产相关性基准
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
OVERSEAS = {
    "PLD.N": {"name": "Prologis", "market": "美国", "type": "工业物流", "cat": "周期型"},
    "O.N": {"name": "Realty Income", "market": "美国", "type": "零售/净租赁", "cat": "防御型"},
    "AMT.N": {"name": "American Tower", "market": "美国", "type": "通信铁塔", "cat": "扩张型"},
    "EQIX.O": {"name": "Equinix", "market": "美国", "type": "数据中心", "cat": "扩张型"},
    "AVB.N": {"name": "AvalonBay", "market": "美国", "type": "住宅", "cat": "防御型"},
    "WELL.N": {"name": "Welltower", "market": "美国", "type": "医疗", "cat": "防御型"},
    "SPG.N": {"name": "Simon Property", "market": "美国", "type": "购物中心", "cat": "周期型"},
    "0823.HK": {"name": "领展房产基金", "market": "中国香港", "type": "综合", "cat": "防御型"},
}
US_HIST_START = "1990-01-01"
US_RECESSIONS = [
    ["1980-01-01", "1980-07-01"], ["1981-07-01", "1982-11-01"],
    ["1990-07-01", "1991-03-01"], ["2001-03-01", "2001-11-01"],
    ["2007-12-01", "2009-06-01"], ["2020-02-01", "2020-04-01"],
]

# ============================================================
# 数据获取层 - 可插拔设计，当前服务器环境建议用 "mock" 或 "local" 模式
# ============================================================

DATA_SOURCE = "mock"  # "ifind" | "akshare" | "yfinance" | "mock"


def fetch_history(code, end, start0=None):
    """
    获取单代码历史日线数据。
    当前服务器环境受限，默认返回 None（由调用方处理）。
    TODO: 未来可接入 stock_finance_data API（需 OpenClaw agent 代理调用）
    """
    if DATA_SOURCE == "mock":
        print(f"[fetch_data_server] {code} mock mode - skipping (请使用本地 Mac iFinD 更新)", flush=True)
        return None
    # TODO: 实现 akshare / yfinance / stock_finance_data 适配器
    return None


# ============================================================
# 指标计算层 - 与 fetch_data.py 完全一致
# ============================================================

def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, pd.NA)
    return 100 - 100 / (1 + rs)


def indicators(s_close, s_amt):
    out = {}
    n = len(s_close)
    last = float(s_close.iloc[-1])
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
    r = rsi(s_close)
    out["rsi14"] = round(float(r.iloc[-1]), 1) if pd.notna(r.iloc[-1]) else None
    out["pctRank"] = round(float((s_close < last).mean() * 100), 1)
    if n >= 250:
        ma250 = float(s_close.rolling(250).mean().iloc[-1])
        out["devMA250"] = round((last / ma250 - 1) * 100, 2)
    else:
        out["devMA250"] = None
    if len(s_amt) >= 60:
        amt20 = float(s_amt.tail(20).mean())
        amt60 = float(s_amt.tail(60).mean())
        out["amt20"] = round(amt20, 0)
        out["amtRatio"] = round(amt20 / amt60, 2) if amt60 else None
    else:
        out["amt20"] = round(float(s_amt.mean()), 0) if len(s_amt) else None
        out["amtRatio"] = None
    out["sinceIPO"] = round((last / float(s_close.iloc[0]) - 1) * 100, 2) if n > 1 else None
    if n > 20:
        out["volAnn"] = round(float(s_close.pct_change().dropna().std() * (244 ** 0.5) * 100), 1)
    else:
        out["volAnn"] = None
    return out


def detect_events(code, name, s_close, s_amt, days=120):
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


def score_signals(reits, fund, corr_ret, bench_ret, bond10y):
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
    print("[fetch_data_server] 服务器版本启动 - 当前为 mock 模式", flush=True)
    print("[fetch_data_server] 注意：当前服务器环境无法直接获取行情数据，", flush=True)
    print("[fetch_data_server]       请继续使用本地 Mac + iFinD 更新 data.js", flush=True)
    print("[fetch_data_server]       服务器端仅负责 fetch_news.py（信息流）更新", flush=True)
    # TODO: 未来接入真正的数据获取适配器后，实现完整的 data.js 生成逻辑
    # 当前保留框架以便未来扩展，完整实现参考 fetch_data.py


if __name__ == "__main__":
    main()
