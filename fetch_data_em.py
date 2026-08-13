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
SPARK_POINTS = 60
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
                rows.append({
                    "time": k[0],
                    "thscode": code,
                    "open": float(k[1]),
                    "close": float(k[2]),
                    "high": float(k[3]),
                    "low": float(k[4]),
                    "volume": float(k[5]),
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
        out["volAnn"] = round(amt20 / amt60 - 1, 3) if amt60 else None
    else:
        out["volAnn"] = None
    return out


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


def backtest_events(events, close_map):
    """简单回测：信号后5日收益率。"""
    results = []
    for e in events:
        c = close_map.get(e["code"])
        if c is None:
            continue
        try:
            idx = c.index.get_loc(e["date"])
        except KeyError:
            continue
        if idx + 5 >= len(c):
            continue
        ret = (c.iloc[idx + 5] / c.iloc[idx] - 1) * 100
        results.append({"event": e, "ret5": round(float(ret), 2)})
    return results


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
    amt = close * vol                                # 估算成交额
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

        # 上市至今收益率
        since_ipo = None
        if "ipoPrice" in u and u["ipoPrice"]:
            since_ipo = round((last / u["ipoPrice"] - 1) * 100, 2)

        # 20日/60日收益率
        ret20 = ret60 = None
        if len(s_close) >= 21:
            ret20 = round((last / float(s_close.iloc[-21]) - 1) * 100, 2)
        if len(s_close) >= 61:
            ret60 = round((last / float(s_close.iloc[-61]) - 1) * 100, 2)

        # 指标
        ind = indicators(s_close, s_amt)

        # sparkline（近60日）
        spark = [round(float(v), 3) for v in s_close.tail(SPARK_POINTS).tolist()]
        hist_dates = [d.strftime("%Y-%m-%d") for d in s_close.tail(SPARK_POINTS).index]

        # 六因子信号
        sig_score = 0
        signals = {
            "momentum": " bullish" if ret20 and ret20 > 2 else " bearish" if ret20 and ret20 < -2 else "neutral",
            "liquidity": "high" if ind.get("volAnn") and ind["volAnn"] > 0.2 else "low",
            "volatility": "high" if ind.get("rsi14") and (ind["rsi14"] > 70 or ind["rsi14"] < 30) else "normal",
            "valuation": "cheap" if ind.get("pctRank") and ind["pctRank"] < 30 else "expensive" if ind.get("pctRank") and ind["pctRank"] > 70 else "fair",
            "trend": "up" if ind.get("macd") and ind["macd"]["hist"] > 0 else "down",
            "total": 0
        }
        # 简单打分
        if ret20 and ret20 > 2:
            sig_score += 1
        if ind.get("volAnn") and ind["volAnn"] > 0.2:
            sig_score += 1
        if ind.get("rsi14") and ind["rsi14"] < 30:
            sig_score += 1
        if ind.get("pctRank") and ind["pctRank"] < 30:
            sig_score += 1
        if ind.get("macd") and ind["macd"]["hist"] > 0:
            sig_score += 1
        signals["total"] = sig_score

        reits.append({
            **u,
            "close": round(last, 3),
            "pct": round(pct, 2),
            "volume": int(s_amt.iloc[-1] / last) if last else 0,  # 估算成交量
            "amount": round(float(s_amt.iloc[-1]), 2),
            "ret20": ret20,
            "ret60": ret60,
            "sinceIPO": since_ipo,
            **ind,
            "spark": spark,
            "histDates": hist_dates,
            "histClose": spark,  # 与 spark 同步，供 update_data.py 增量更新
            "signals": signals,
        })

    print(f"[reits] 计算完成 {len(reits)}/{len(universe)}", flush=True)

    # ---------- 4. 板块与策略分类 ----------
    sectors = sorted({u["sector"] for u in universe})
    strategies = ["防御型", "周期型", "扩张型"]

    # ---------- 5. 相关性 ----------
    corr_payload = {}
    try:
        recent_close = close.tail(CORR_WINDOW)
        corr = recent_close.pct_change().corr()
        for c in codes:
            if c not in corr.columns:
                continue
            peers = []
            for pc in codes:
                if pc != c and pc in corr.columns:
                    v = corr.loc[c, pc]
                    if pd.notna(v):
                        peers.append({"code": pc, "r": round(float(v), 2)})
            peers.sort(key=lambda x: abs(x["r"]), reverse=True)
            # 板块基准
            sec = next((u["sector"] for u in universe if u["code"] == c), None)
            bench = SECTOR_PEER.get(sec)
            bench_r = None
            if bench and bench in corr.columns:
                bench_r = round(float(corr.loc[c, bench]), 2)
            corr_payload[c] = {"peers": peers[:5], "sectorPeer": bench_r}
    except Exception as e:
        print(f"[corr] 计算失败: {e}", flush=True)

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
        "stratSignals": strat_signals,
        "revaluation": revaluation,
        "events": recent_events,
        "backtest": backtest,
        "cycle": cycle or None,
        "fundamentals": fund_raw.get("items", []) if isinstance(fund_raw, dict) else [],
        "series": {
            "dates": wdates,
            "market": eq_index(codes),
            "bySector": {sec: eq_index([u["code"] for u in universe if u["sector"] == sec]) for sec in sectors},
            "byStrategy": {st: eq_index([u["code"] for u in universe if u["strategy"] == st]) for st in strategies},
            "byRight": {r: eq_index([u["code"] for u in universe if u["right"] == r]) for r in ("产权", "经营权")},
        },
    }

    js = "window.REITS_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n"
    DATA_JS.write_text(js, encoding="utf-8")
    DATA_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    missing = [u["name"] for u in universe if u["code"] not in fetched]
    print(f"[done] {len(reits)}/{len(universe)} 只，截至 {payload['lastTradeDate']}，"
          f"data.js {len(js) / 1e6:.1f}MB", flush=True)
    if missing:
        print("[miss] " + "、".join(missing))


if __name__ == "__main__":
    main()
