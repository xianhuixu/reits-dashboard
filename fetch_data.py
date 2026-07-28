#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公募REITs 全量投研面板数据抓取脚本 v2
数据源：同花顺 iFinD（ifind 插件 ifind_tool.py）
覆盖：universe.json 中全部经 iFinD 验证的上市公募 REITs（79 只）
输出：data.js（window.REITS_DATA）与 data.json
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
LOOKBACK_DAYS = 200
SPARK_POINTS = 60
BATCH_PAUSE = 1.2          # 批次间隔，避免限频

# 大类资产相关性基准（均已验证 iFinD 可取）
# 注：中证红利 000922 iFinD 无数据，以深证红利 399324.SZ 替代
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
# REITs 板块 → A股对应板块指数
SECTOR_PEER = {
    "保租房": "399393.SZ", "产业园": "399995.SZ", "市政环保": "399995.SZ",
    "能源": "399808.SZ", "高速公路": "399437.SZ", "仓储物流": "399353.SZ",
    "数据中心": "399935.SZ", "消费": "000932.SH",
}


def ifind_price(codes, start, end, retries=2):
    """拉取日行情（≤3只/批），失败退避重试。返回 DataFrame 或 None。"""
    for attempt in range(retries + 1):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            fp = f.name
        params = {"ticker": ",".join(codes), "start_date": start, "end_date": end,
                  "file_path": fp, "interval": "D", "adjust": "none"}
        subprocess.run([sys.executable, str(IFIND_SCRIPT), "call",
                        "--api-name", "ifind_get_price",
                        "--params-json", json.dumps(params)],
                       capture_output=True, text=True, timeout=180)
        p = Path(fp)
        if p.exists() and p.stat().st_size > 10:
            try:
                return pd.read_csv(fp)
            except Exception:
                return None
        time.sleep(4 * (attempt + 1))
    return None


def main():
    universe = json.loads((ROOT / "universe.json").read_text(encoding="utf-8"))
    codes = [u["code"] for u in universe]
    end = date.today()
    start = (end - timedelta(days=LOOKBACK_DAYS)).isoformat()

    frames = []
    fetched = set()
    cache_dir = ROOT / "raw_cache"
    cache_dir.mkdir(exist_ok=True)
    tag = date.today().strftime("%Y%m%d")
    for i in range(0, len(codes), 3):
        batch = codes[i:i + 3]
        cache = cache_dir / f"{tag}_{i}.csv"
        if cache.exists():                      # 断点续跑：今日已抓批次直接复用
            df = pd.read_csv(cache)
        else:
            df = ifind_price(batch, start, end.isoformat())
            # 批量查询会被无效/缺数据代码整体拖空，对缺失者逐一单查
            got = set(df["thscode"].unique()) if df is not None and "thscode" in df.columns else set()
            add = []
            for c in [c for c in batch if c not in got]:
                d1 = ifind_price([c], start, end.isoformat(), retries=1)
                if d1 is not None and "thscode" in d1.columns and len(d1):
                    add.append(d1)
            if add:
                df = pd.concat([df] + add, ignore_index=True) if df is not None else pd.concat(add, ignore_index=True)
            if df is not None and len(df):
                df.to_csv(cache, index=False)
            time.sleep(BATCH_PAUSE)
        if df is not None and "thscode" in df.columns:
            frames.append(df)
            fetched.update(df["thscode"].unique())
        print(f"[{min(i+3, len(codes))}/{len(codes)}] 已获取 {len(fetched)} 只", flush=True)

    if not frames:
        raise SystemExit("取数全部失败，未更新数据")
    df = pd.concat(frames, ignore_index=True)
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time")

    close = df.pivot_table(index="time", columns="thscode", values="close")
    vol = df.pivot_table(index="time", columns="thscode", values="volume")
    dates = [d.strftime("%Y-%m-%d") for d in close.index]

    def eq_index(code_list):
        sub = close[[c for c in code_list if c in close.columns]].dropna(how="all")
        if sub.empty:
            return []
        norm = sub / sub.iloc[0] * 100.0
        return [round(v, 2) if pd.notna(v) else None for v in norm.mean(axis=1)]

    reits = []
    for u in universe:
        c = u["code"]
        if c not in close.columns:
            continue
        s = close[c].dropna()
        if len(s) < 2:
            continue
        last, prev = s.iloc[-1], s.iloc[-2]

        def ret(n):
            return round((last / s.iloc[-n - 1] - 1) * 100, 2) if len(s) > n else None

        v = vol[c].dropna() if c in vol.columns else pd.Series(dtype=float)
        last_vol = float(v.iloc[-1]) if len(v) else None
        reits.append({
            "code": c, "name": u["name"], "sector": u["sector"],
            "right": u["right"], "strategy": u["strategy"],
            "close": round(float(last), 3),
            "pct": round(float((last / prev - 1) * 100), 2),
            "ret5": ret(5), "ret20": ret(20), "ret60": ret(60),
            "volume": int(last_vol) if last_vol else None,
            "amount": round(last * last_vol, 0) if last_vol else None,  # 估算成交额（元）
            "spark": [round(float(x), 3) for x in s.tail(SPARK_POINTS)],
        })

    sectors = sorted({u["sector"] for u in universe})
    strategies = ["防御型", "周期型", "成长型"]

    # ---------- 基准指数抓取与相关性计算 ----------
    bench_frames = []
    bcodes = list(BENCHMARKS.keys())
    for i in range(0, len(bcodes), 3):
        batch = bcodes[i:i + 3]
        bdf = ifind_price(batch, start, end.isoformat())
        got = set(bdf["thscode"].unique()) if bdf is not None and "thscode" in bdf.columns else set()
        for c in [c for c in batch if c not in got]:
            d1 = ifind_price([c], start, end.isoformat(), retries=1)
            if d1 is not None and "thscode" in d1.columns and len(d1):
                bdf = pd.concat([bdf, d1], ignore_index=True) if bdf is not None else d1
        if bdf is not None and "thscode" in bdf.columns:
            bench_frames.append(bdf)
        time.sleep(BATCH_PAUSE)
        print(f"[bench {min(i+3, len(bcodes))}/{len(bcodes)}]", flush=True)

    corr_payload = None
    if bench_frames:
        bdf = pd.concat(bench_frames, ignore_index=True)
        bdf["time"] = pd.to_datetime(bdf["time"])
        bclose = bdf.pivot_table(index="time", columns="thscode", values="close").sort_index()
        bret = bclose.pct_change()

        # 组合日收益率（等权）：全市场 / 策略 / 板块
        cret = close.pct_change()
        groups = {"全市场": codes}
        for st in strategies:
            groups[st] = [u["code"] for u in universe if u["strategy"] == st]
        for sec in sectors:
            groups[sec] = [u["code"] for u in universe if u["sector"] == sec]

        def port_ret(code_list):
            cols = [c for c in code_list if c in cret.columns]
            return cret[cols].mean(axis=1) if cols else pd.Series(dtype=float)

        def pearson(a, b):
            j = pd.concat([a, b], axis=1).dropna()
            if len(j) < 20:
                return None
            return round(float(j.iloc[:, 0].corr(j.iloc[:, 1])), 2)

        benchmarks_meta = [{"code": c, **BENCHMARKS[c]} for c in bcodes if c in bret.columns]
        matrix = {}
        for gname, gcodes in groups.items():
            pr = port_ret(gcodes)
            matrix[gname] = {bc: pearson(pr, bret[bc]) for bc in bret.columns}

        # 股性-债性散点：各板块 X=与国债相关性，Y=与沪深300相关性
        scatter = []
        if "000012.SH" in bret.columns and "000300.SH" in bret.columns:
            for sec in sectors:
                pr = port_ret(groups[sec])
                scatter.append({
                    "sector": sec,
                    "bond": pearson(pr, bret["000012.SH"]),
                    "equity": pearson(pr, bret["000300.SH"]),
                })

        # REITs 板块 vs A股对应板块：相关系数 + 期间涨跌幅对比
        peers = []
        for sec, bc in SECTOR_PEER.items():
            if bc not in bret.columns:
                continue
            pr = port_ret(groups.get(sec, []))
            bser = bclose[bc].dropna()
            peers.append({
                "sector": sec, "peerCode": bc, "peerName": BENCHMARKS[bc]["name"],
                "corr": pearson(pr, bret[bc]),
                "reitRet": round(float((port_ret(groups.get(sec, [])).dropna().add(1).prod() - 1) * 100), 2) if len(pr.dropna()) else None,
                "peerRet": round(float((bser.iloc[-1] / bser.iloc[0] - 1) * 100), 2) if len(bser) > 1 else None,
            })

        corr_payload = {
            "benchmarks": benchmarks_meta,
            "matrix": matrix,          # matrix[组合][基准code] = 相关系数
            "scatter": scatter,
            "peers": peers,
        }
        print(f"[corr] 基准 {len(benchmarks_meta)} 个，矩阵 {len(matrix)} 行", flush=True)

    payload = {
        "updated": pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d %H:%M:%S"),
        "lastTradeDate": dates[-1] if dates else None,
        "count": len(reits),
        "sectors": sectors,
        "strategies": strategies,
        "reits": reits,
        "correlation": corr_payload,
        "series": {
            "dates": dates,
            "market": eq_index(codes),
            "bySector": {sec: eq_index([u["code"] for u in universe if u["sector"] == sec])
                         for sec in sectors},
            "byStrategy": {st: eq_index([u["code"] for u in universe if u["strategy"] == st])
                           for st in strategies},
            "byRight": {r: eq_index([u["code"] for u in universe if u["right"] == r])
                        for r in ("产权", "经营权")},
        },
    }

    js = "window.REITS_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n"
    (ROOT / "data.js").write_text(js, encoding="utf-8")
    (ROOT / "data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    missing = [u["name"] for u in universe if u["code"] not in fetched]
    print(f"[done] {len(reits)}/{len(universe)} 只，截至 {payload['lastTradeDate']}")
    if missing:
        print("[miss] " + "、".join(missing))


if __name__ == "__main__":
    main()
