#!/usr/bin/env python3
"""
公募REITs 全量投研面板数据抓取脚本（服务器版）
数据源：腾讯 K 线接口（替代 iFinD）
覆盖：universe.json 全部上市公募REITs + 大类资产基准
能力：上市以来全历史日线、MACD/RSI/分位/流动性指标、
     六因子信号打分、信号事件流与历史回测
输出：data.js（window.REITS_DATA）与 data.json
"""
import json
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA_JS = ROOT / "data.js"
DATA_JSON = ROOT / "data.json"
UNIVERSE = ROOT / "universe.json"
HIST_DIR = ROOT / "hist_cache"      # 逐代码全历史增量缓存
HIST_START = "2021-06-21"
SPARK_POINTS = 250                # 个券详情走势窗口（近250交易日）
CORR_WINDOW = 130                   # 相关性口径：近 130 交易日
FETCH_PAUSE = 0.3                   # 取数间隔

# 腾讯接口代码映射
def tencent_code(c):
    """508001.SH → sh508001, 399324.SZ → sz399324"""
    if c.endswith(".SH"):
        return "sh" + c[:-3]
    if c.endswith(".SZ"):
        return "sz" + c[:-3]
    if c.endswith(".CSI"):
        # 尝试上海
        return "sh" + c[:-4]
    return c

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
# 官方中证REITs收益指数（用于首页 KPI 首卡）
MARKET_INDEX_CODE = "932047.CSI"

# NBER 美国经济衰退区间
US_RECESSIONS = [
    ["1980-01-01", "1980-07-01"], ["1981-07-01", "1982-11-01"],
    ["1990-07-01", "1991-03-01"], ["2001-03-01", "2001-11-01"],
    ["2007-12-01", "2009-06-01"], ["2020-02-01", "2020-04-01"],
]


# ---------------- 腾讯 K 线取数 ----------------
def tencent_kline(code, limit=500):
    """从腾讯接口获取日K线。返回 DataFrame(time,open,high,low,close,volume) 或 None。"""
    tc = tencent_code(code)
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={tc},day,,,{limit},na"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            klines = data.get("data", {}).get(tc, {}).get("day", [])
            if not klines:
                return None
            rows = []
            for k in klines:
                # 格式: [日期, 开盘, 收盘, 最高, 最低, 成交量]
                # 腾讯成交量单位 = 手（1手=100份），×100 归一为"份"，
                # 与 hist_cache 中 iFinD 口径（volume=份）保持一致
                rows.append({
                    "time": k[0],
                    "thscode": code,
                    "open": float(k[1]),
                    "close": float(k[2]),
                    "high": float(k[3]),
                    "low": float(k[4]),
                    "volume": float(k[5]) * 100,
                })
            return pd.DataFrame(rows)
    except Exception as e:
        print(f"[tencent] {code} 失败: {e}", flush=True)
        return None


def fetch_history(code, end, start0=None):
    """逐代码全历史，hist_cache 增量更新。"""
    HIST_DIR.mkdir(exist_ok=True)
    cache = HIST_DIR / (code.replace(".", "_") + ".csv")
    old = None
    start = start0 or HIST_START
    if cache.exists():
        try:
            old = pd.read_csv(cache, dtype={"time": str})
            if len(old) and "time" in old.columns:
                start = (pd.to_datetime(old["time"]).max() + timedelta(days=1)).date().isoformat()
        except Exception:
            old = None

    df = tencent_kline(code, limit=500)
    if df is None:
        if old is not None and len(old):
            return old
        return None

    # 合并旧数据
    if old is not None:
        # 自愈：以本次腾讯取数（volume 已归一为"份"）为参照，修复旧缓存中的单位异常行：
        #  - ratio < 0.5  → 旧行是"手"口径（历史遗留）→ ×100 归一为"份"
        #  - ratio > 50   → 旧行曾被误乘 ×100 → ÷100 还原
        try:
            old["volume"] = pd.to_numeric(old["volume"], errors="coerce")
            tx_ref = df[["time", "volume"]].rename(columns={"volume": "v_tx"})
            m = old.merge(tx_ref, on="time", how="left")
            ratio = m["volume"] / m["v_tx"]
            valid = m["v_tx"].notna() & (m["v_tx"] > 0)
            lo = valid & (ratio < 0.5)
            hi = valid & (ratio > 50)
            if lo.any():
                old.loc[lo, "volume"] = old.loc[lo, "volume"] * 100
                print(f"[heal] {code} 修复 {int(lo.sum())} 行 手→份", flush=True)
            if hi.any():
                old.loc[hi, "volume"] = old.loc[hi, "volume"] / 100
                print(f"[heal] {code} 还原 {int(hi.sum())} 行 误乘×100", flush=True)
        except Exception:
            pass
        df = pd.concat([old, df], ignore_index=True)
    df = df.drop_duplicates(subset=["thscode", "time"]).sort_values("time")
    df.to_csv(cache, index=False)
    return df


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
    if len(s_close) >= 15 and pd.notna(r.iloc[-1]):
        out["rsi14"] = round(float(r.iloc[-1]), 1)
    else:
        out["rsi14"] = None
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
    # 上市以来累计涨跌与年化波动率
    out["sinceIPO"] = round((last / float(s_close.iloc[0]) - 1) * 100, 2) if n > 1 else None
    if n > 20:
        out["volAnn"] = round(float(s_close.pct_change().dropna().std() * (244 ** 0.5) * 100), 1)
    else:
        out["volAnn"] = None
    return out


# ---------------- 六因子信号打分 ----------------
def score_signals(reits, fund, corr_ret, bench_ret, bond10y):
    """六因子打分（-2 ~ +2）：流动性/情绪/资金/业绩/利差/股债联动。"""
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


# ---------------- 信号检测与回测 ----------------
def detect_events(code, name, s_close, s_amt):
    """检测六类信号事件。"""
    events = []
    n = len(s_close)
    if n < 60:
        return events
    close = s_close.values
    amt = s_amt.values
    dates = s_close.index.strftime("%Y-%m-%d").tolist()

    def sig(i):
        c, a = close[:i+1], amt[:i+1]
        out = {"i": i}
        # 1 突破20日高
        if i >= 20 and c[i] == max(c[i-20:i+1]):
            out["break20"] = True
        # 2 放量
        if i >= 20 and a[i] > a[i-20:i].mean() * 1.5:
            out["volumeSpike"] = True
        # 3 价稳量缩（近10日振幅<3%且成交额<20日均值80%）
        if i >= 10:
            rng = (max(c[i-10:i+1]) - min(c[i-10:i+1])) / c[i] * 100 if c[i] else 0
            if rng < 3 and a[i] < a[i-10:i].mean() * 0.8:
                out["quiet"] = True
        # 4 RSI超卖反弹
        if i >= 14:
            dc = pd.Series(c)
            r = rsi(dc, 14)
            if r.iloc[i-1] < 30 and r.iloc[i] >= 30:
                out["rsiBounce"] = True
        # 5 金叉
        if i >= 26:
            dc = pd.Series(c)
            dif = ema(dc, 12) - ema(dc, 26)
            dea = ema(dif, 9)
            if len(dif) > i and len(dea) > i and i > 0:
                if float(dif.iloc[i-1]) <= float(dea.iloc[i-1]) and float(dif.iloc[i]) > float(dea.iloc[i]):
                    out["goldenCross"] = True
        # 6 跌幅>3%
        if i > 0 and (c[i] / c[i-1] - 1) * 100 < -3:
            out["drop3"] = True
        return out

    for i in range(60, n):
        s = sig(i)
        if len(s) > 1:
            events.append({"code": code, "name": name, "date": dates[i], **s})
    return events


BT_TYPE_MAP = [("goldenCross", "MACD金叉"), ("deathCross", "MACD死叉"),
               ("rsiOver", "RSI超买"), ("rsiBounce", "RSI超卖"),
               ("volumeSpike", "成交异动"), ("break20", "突破250日线"),
               ("quiet", "价稳量缩"), ("drop3", "单日大跌")]


def backtest_events(events, close_map):
    """回测聚合：按信号类型输出 5/20 日均值与胜率（直接给前端小体积聚合结果，不再输出逐样本明细）。"""
    agg = {}
    for e in events:
        c = close_map.get(e["code"])
        if c is None:
            continue
        try:
            idx = c.index.get_loc(e["date"])
        except KeyError:
            continue
        types = [t for f, t in BT_TYPE_MAP if e.get(f)] or ["信号"]
        for t in types:
            b = agg.setdefault(t, {"r5": [], "r20": []})
            if idx + 5 < len(c):
                b["r5"].append(float(c.iloc[idx + 5] / c.iloc[idx] - 1))
            if idx + 20 < len(c):
                b["r20"].append(float(c.iloc[idx + 20] / c.iloc[idx] - 1))

    def stat(x):
        if not x:
            return None
        return {"n": len(x), "avg": round(sum(x) / len(x) * 100, 2),
                "win": round(sum(1 for v in x if v > 0) / len(x) * 100, 1)}

    return {t: {"d5": stat(b["r5"]), "d20": stat(b["r20"])} for t, b in agg.items()}


# ---------------- 主流程 ----------------
def main():
    universe = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    codes = [u["code"] for u in universe]
    end = date.today().isoformat()

    # ---------- 1. REITs 全历史 ----------
    frames, fetched = [], set()
    for i, c in enumerate(codes):
        df = fetch_history(c, end)
        if df is not None and "thscode" in df.columns and len(df):
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
    # volume 已归一为"份"（腾讯取数×100 / iFinD 原样），×收盘价 = 估算成交额（元）
    amt = close * vol
    dates = [d.strftime("%Y-%m-%d") for d in close.index]

    # ---------- 2. 基准指数全历史 ----------
    bench_frames = []
    for bc in BENCHMARKS:
        bdf = fetch_history(bc, end)
        if bdf is not None and "thscode" in bdf.columns and len(bdf):
            bench_frames.append(bdf)
        time.sleep(FETCH_PAUSE)
    bclose = None
    if bench_frames:
        bdf = pd.concat(bench_frames, ignore_index=True)
        bdf["time"] = pd.to_datetime(bdf["time"])
        bclose = bdf.pivot_table(index="time", columns="thscode", values="close").sort_index()

    # ---------- 2b. 官方中证REITs指数 ----------
    market_index = None
    # 尝试东方财富（服务器可能不通，失败则置空）
    try:
        mi_df = tencent_kline(MARKET_INDEX_CODE, limit=100)
        if mi_df is not None and len(mi_df) >= 2:
            mi_close = mi_df.sort_values("time")["close"]
            last, prev = mi_close.iloc[-1], mi_close.iloc[-2]
            market_index = {
                "code": MARKET_INDEX_CODE,
                "name": "中证REITs收益指数",
                "close": round(float(last), 2),
                "pct": round(float((last / prev - 1) * 100), 2),
            }
    except Exception:
        pass

    # 尝试从东方财富获取中证REITs指数
    try:
        import ssl
        ctx = ssl._create_unverified_context()
        em_url = "https://push2.eastmoney.com/api/qt/stock/get?secid=2.932047&fields=f43,f44,f45,f46,f47,f48,f57,f58,f60,f169,f170"
        req = urllib.request.Request(em_url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            em_data = json.loads(resp.read().decode("utf-8"))
            em_d = em_data.get("data", {})
            if em_d.get("f57"):
                last = em_d.get("f43", 0) / 100.0
                prev = em_d.get("f60", 0) / 100.0
                if last and prev:
                    market_index = {
                        "code": MARKET_INDEX_CODE,
                        "name": em_d.get("f58", "中证REITs收益指数"),
                        "close": round(last, 2),
                        "pct": round((last / prev - 1) * 100, 2) if prev else 0,
                    }
                    print(f"[marketIndex] 东方财富获取成功: {market_index}", flush=True)
    except Exception as e:
        print(f"[marketIndex] 东方财富获取失败: {e}", flush=True)

    if market_index is None:
        print(f"[marketIndex] {MARKET_INDEX_CODE} 无数据，置空", flush=True)

    # ---------- 3. 单只指标与信号 ----------
    reits = []
    close_map = {}
    for u in universe:
        c = u["code"]
        if c not in close.columns:
            continue
        s_close = close[c].dropna()
        s_amt = amt[c].reindex(s_close.index).fillna(0)
        if len(s_close) < 2:
            continue
        close_map[c] = s_close

        last = float(s_close.iloc[-1])
        prev = float(s_close.iloc[-2])
        pct = (last / prev - 1) * 100 if prev else 0

        # 5/20/60日收益率
        ret5 = ret20 = ret60 = None
        if len(s_close) >= 6:
            ret5 = round((last / float(s_close.iloc[-6]) - 1) * 100, 2)
        if len(s_close) >= 21:
            ret20 = round((last / float(s_close.iloc[-21]) - 1) * 100, 2)
        if len(s_close) >= 61:
            ret60 = round((last / float(s_close.iloc[-61]) - 1) * 100, 2)

        # 指标
        ind = indicators(s_close, s_amt)

        # sparkline（近60日）
        spark = [round(float(v), 3) for v in s_close.tail(SPARK_POINTS).tolist()]
        hist_dates = [d.strftime("%Y-%m-%d") for d in s_close.tail(SPARK_POINTS).index]

        reits.append({
            **u,
            "close": round(last, 3),
            "pct": round(pct, 2),
            "volume": int(s_amt.iloc[-1] / last) if last else 0,  # 估算成交量（份）
            "amount": round(float(s_amt.iloc[-1]), 2),
            "ret5": ret5,
            "ret20": ret20,
            "ret60": ret60,
            **ind,
            "histDates": hist_dates,
            "histClose": spark,  # 与 spark 同步，供 update_data.py 增量更新
            "listDays": int(len(s_close)),
            "signals": {},
        })

    print(f"[reits] 计算完成 {len(reits)}/{len(universe)}", flush=True)

    # ---------- 3b. 六因子信号打分（跨截面，需全量 reits） ----------
    fund = {}
    try:
        fund_raw = json.loads((ROOT / "fundamentals.json").read_text(encoding="utf-8"))
        if isinstance(fund_raw, dict):
            fund = {f["code"]: f for f in fund_raw.get("items", [])}
    except Exception:
        pass
    bond10y = None
    try:
        cycle_raw = json.loads((ROOT / "cycle_judgment.json").read_text(encoding="utf-8"))
        bond10y = cycle_raw.get("bond10y")
    except Exception:
        pass
    cret_w = close.pct_change()
    bret_w = bclose.pct_change() if bclose is not None else None
    reits = score_signals(reits, fund, cret_w, bret_w, bond10y)

    # ---------- 4. 板块与策略分类 ----------
    sectors = sorted({u["sector"] for u in universe})
    strategies = ["防御型", "周期型", "扩张型"]

    # ---------- 5. 大类资产相关性（板块×基准矩阵 + 股性债性散点 + 板块对照） ----------
    corr_payload = None
    try:
        cret_w = close.tail(CORR_WINDOW).pct_change()
        bret_w = bclose.tail(CORR_WINDOW).pct_change() if bclose is not None else None
        if bret_w is None:
            raise RuntimeError("无基准数据")
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
    except Exception as e:
        print(f"[corr] 计算失败: {e}", flush=True)


    # ---------- 5b. 个券相似度（个券×个券收益率相关性 Top5，供详情页"相似个券"） ----------
    reit_peers = None
    try:
        cret_w = close.tail(CORR_WINDOW).pct_change()
        cols = [c for c in codes if c in cret_w.columns]
        cm = cret_w[cols].corr(min_periods=20)
        reit_peers = {}
        for c in cols:
            row = cm[c].drop(index=c).dropna()
            if not len(row):
                continue
            top = row.reindex(row.abs().sort_values(ascending=False).index).head(5)
            reit_peers[c] = {"peers": [{"code": k, "r": round(float(v), 2)} for k, v in top.items()]}
        print(f"[reitPeers] 计算完成 {len(reit_peers)} 只", flush=True)
    except Exception as e:
        print(f"[reitPeers] 计算失败: {e}", flush=True)

    # ---------- 6. 策略信号汇总 ----------
    strat_signals = {}
    for st in strategies:
        members = [r for r in reits if r["strategy"] == st]
        if members:
            avg_total = sum(r["signals"]["total"] for r in members) / len(members)
            strat_signals[st] = {"avg": round(avg_total, 1),
                                 "label": "偏强" if avg_total / 6 >= 1 else "偏弱" if avg_total / 6 <= -1 else "中性"}

    # ---------- 6.5 资产重估状态 ----------
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
        stage = {4: "重估进行中", 3: "重估初期", 2: "重估酝酿", 1: "重估暂停", 0: "重估缺席"}.get(score, "重估缺席")
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
        s_amt = amt[c].reindex(close_map[c].index).fillna(0)
        all_events.extend(detect_events(c, u["name"], close_map[c], s_amt))
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
                out.append(None)
                continue
            m = (close_w[cols].loc[dt] / base * 100.0).mean()
            out.append(round(float(m), 2) if pd.notna(m) else None)
        return out

    wdates = [d.strftime("%Y-%m-%d") for d in close_w.index]

    # ---------- 9. 周期判断 ----------
    cycle = None
    try:
        cycle = json.loads((ROOT / "cycle_judgment.json").read_text(encoding="utf-8"))
    except Exception:
        pass

    # ---------- 10. 基本面 ----------
    fund_raw = None
    try:
        fund_raw = json.loads((ROOT / "fundamentals.json").read_text(encoding="utf-8"))
    except Exception:
        pass

    # ---------- 10b. 海外静态数据（美国长期走势 / 周期耦合矩阵） ----------
    us_long = None
    try:
        us_long = json.loads((ROOT / "us_long_static.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    overseas_static = None
    try:
        overseas_static = json.loads((ROOT / "overseas_static.json").read_text(encoding="utf-8"))
    except Exception:
        pass

    # 读取已有 data.json 中的 marketIndex（避免覆盖）
    old_market_index = None
    try:
        old_data = json.loads(DATA_JSON.read_text(encoding="utf-8"))
        old_market_index = old_data.get("marketIndex")
    except Exception:
        pass

    payload = {
        "updated": pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d %H:%M:%S"),
        "lastTradeDate": dates[-1] if dates else None,
        "count": len(reits),
        "sectors": sectors,
        "strategies": strategies,
        "reits": reits,
        "marketIndex": market_index or old_market_index,
        "correlation": corr_payload,
        "reitPeers": reit_peers,
        "stratSignals": strat_signals,
        "revaluation": revaluation,
        "events": recent_events,
        "backtest": backtest,
        "cycle": cycle or None,
        "fundamentals": fund_raw.get("items", []) if isinstance(fund_raw, dict) else [],
        "usLong": us_long,
        "overseasStatic": overseas_static,
        "series": {
            "dates": wdates,
            "market": eq_index(codes),
            "bySector": {sec: eq_index([u["code"] for u in universe if u["sector"] == sec]) for sec in sectors},
            "byStrategy": {st: eq_index([u["code"] for u in universe if u["strategy"] == st]) for st in strategies},
            "byRight": {r: eq_index([u["code"] for u in universe if u["right"] == r]) for r in ("产权", "经营权")},
        },
    }

    # 拆分首屏核心数据与研究数据（前端按需加载，提升首屏速度）
    CORE_KEYS = ["updated", "lastTradeDate", "count", "sectors", "strategies", "reits",
                 "marketIndex", "cycle", "revaluation", "stratSignals"]
    core = {k: payload[k] for k in CORE_KEYS if k in payload}
    rest = {k: v for k, v in payload.items() if k not in CORE_KEYS}
    js = "window.REITS_DATA = " + json.dumps(core, ensure_ascii=False) + ";\n"
    DATA_JS.write_text(js, encoding="utf-8")
    DATA_JSON.write_text(json.dumps(core, ensure_ascii=False, indent=1), encoding="utf-8")
    jsr = "window.REITS_DATA_R = " + json.dumps(rest, ensure_ascii=False) + ";\n"
    (ROOT / "data_research.js").write_text(jsr, encoding="utf-8")
    (ROOT / "data_research.json").write_text(json.dumps(rest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[done] {len(reits)} 只，截至 {last_date}，"
          f"data.js {len(js) / 1e6:.1f}MB + research {len(jsr) / 1e6:.1f}MB", flush=True)
    missing = [u["name"] for u in universe if u["code"] not in fetched]
    print(f"[done] {len(reits)}/{len(universe)} 只，截至 {payload['lastTradeDate']}，"
          f"data.js {len(js) / 1e6:.1f}MB", flush=True)
    if missing:
        print("[miss] " + "、".join(missing))
    sync_inst_reits()


def sync_inst_reits():
    """机构间REITs（不动产ABS）快照与主站数据同步更新。
    调用 inst_reits_update.py（源自 tingdall/reits-dashboard，抓取沪深交易所项目），
    成功则刷新前端加载的 inst_reits.js；失败沿用旧快照，不影响主流程。"""
    import shutil
    import subprocess
    import sys
    script = ROOT / "inst_reits_update.py"
    snapshot = ROOT / "reits_snapshot.js"
    target = ROOT / "inst_reits.js"
    try:
        r = subprocess.run([sys.executable, str(script)], cwd=str(ROOT),
                           timeout=300, capture_output=True, text=True)
        if r.returncode == 0 and snapshot.exists():
            shutil.copyfile(snapshot, target)
            print("[done] 机构间REITs快照已同步 → inst_reits.js", flush=True)
        else:
            print(f"[warn] 机构间REITs抓取返回非零，沿用旧快照：{r.stderr.strip()[:200]}", flush=True)
    except Exception as e:
        print(f"[warn] 机构间REITs同步失败（沿用旧快照）：{e}", flush=True)


if __name__ == "__main__":
    main()
