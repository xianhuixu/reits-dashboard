"""离线重建美国 REITs 长期序列（usLong）。

从 hist_cache/*.csv 读取 iFinD 缓存的美股收盘价，
生成三类合成指数 + 代表标的个体归一化序列与统计指标，
写回 us_long_static.json，并同步更新 data.json / data.js。

用法：python3 scripts/build_us_long.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
HIST_DIR = ROOT / "hist_cache"

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

US_RECESSIONS = [
    ["1980-01-01", "1980-07-01"], ["1981-07-01", "1982-11-01"],
    ["1990-07-01", "1991-03-01"], ["2001-03-01", "2001-11-01"],
    ["2007-12-01", "2009-06-01"], ["2020-02-01", "2020-04-01"],
]

CATS = ("防御型", "周期型", "扩张型")


def series_stats(s):
    """s: 已归一化（起点=100）的 pd.Series，返回长期统计。"""
    s = s.dropna()
    if len(s) < 60:
        return None
    years = (s.index[-1] - s.index[0]).days / 365.25
    cagr = ((s.iloc[-1] / s.iloc[0]) ** (1 / years) - 1) * 100 if years > 0 else None

    def maxdd(a, b):
        w = s[(s.index >= a) & (s.index <= b)]
        return round(float((w / w.cummax() - 1).min() * 100), 1) if len(w) > 5 else None

    s10 = s[s.index >= s.index[-1] - pd.Timedelta(days=3652)]
    y10 = (s10.index[-1] - s10.index[0]).days / 365.25
    cagr10 = ((s10.iloc[-1] / s10.iloc[0]) ** (1 / y10) - 1) * 100 if len(s10) > 60 and y10 > 0 else None
    return {
        "start": s.index[0].strftime("%Y-%m-%d"),
        "cagr": round(cagr, 1) if cagr is not None else None,
        "dd0809": maxdd("2007-12-01", "2009-06-30"),
        "dd2020": maxdd("2020-02-01", "2020-04-30"),
        "cagr10": round(cagr10, 1) if cagr10 is not None else None,
    }


def main():
    us_series = {}
    for oc, meta in OVERSEAS.items():
        if meta["market"] != "美国":
            continue
        cache = HIST_DIR / (oc.replace(".", "_") + ".csv")
        if not cache.exists():
            print(f"[usLong] {oc} 无缓存，跳过")
            continue
        hdf = pd.read_csv(cache, dtype={"time": str})
        hdf["time"] = pd.to_datetime(hdf["time"])
        s = hdf.set_index("time")["close"].dropna().sort_index()
        if len(s) >= 120:
            us_series[oc] = s
    if not us_series:
        raise SystemExit("[usLong] 无可用美股缓存")

    udf_raw = pd.DataFrame(us_series).sort_index()
    udf = udf_raw.ffill()
    # 长缺口（>45 天无真实行情）不前向填充，置 NaN 让前端断线呈现
    for c in udf.columns:
        obs_idx = udf_raw[c].dropna().index
        pos = obs_idx.searchsorted(udf.index, side="right") - 1
        stale = pd.Series(False, index=udf.index)
        valid = pos >= 0
        if valid.any():
            last_dates = obs_idx[pos[valid]]
            stale.loc[valid] = (udf.index[valid] - last_dates) > pd.Timedelta(days=45)
        udf.loc[stale, c] = float("nan")

    weekly = udf.iloc[::5]
    if len(udf) and weekly.index[-1] != udf.index[-1]:
        weekly = pd.concat([weekly, udf.iloc[[-1]]])

    # 归一化（各自首个有效观测 = 100）
    norm = weekly.copy()
    for c in norm.columns:
        v = norm[c].dropna()
        if len(v):
            norm[c] = norm[c] / v.iloc[0] * 100.0

    cats = {}
    for cat in CATS:
        cols = [oc for oc, m in OVERSEAS.items() if m.get("cat") == cat and oc in norm.columns]
        if cols:
            cats[cat] = norm[cols].mean(axis=1, skipna=True)

    us_long = {
        "dates": [d.strftime("%Y-%m-%d") for d in weekly.index],
        "cats": {c: [round(float(v), 2) if pd.notna(v) else None for v in idx] for c, idx in cats.items()},
        "recessions": US_RECESSIONS,
        "stats": {c: series_stats(idx) for c, idx in cats.items() if series_stats(idx)},
        "members": {oc: {"name": m["name"], "type": m["type"], "cat": m["cat"]}
                    for oc, m in OVERSEAS.items() if oc in us_series},
        "memberSeries": {oc: [round(float(v), 2) if pd.notna(v) else None for v in norm[oc]]
                         for oc in norm.columns},
        "memberStats": {oc: series_stats(norm[oc]) for oc in norm.columns if series_stats(norm[oc])},
    }

    (ROOT / "us_long_static.json").write_text(
        json.dumps(us_long, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"[usLong] dates={len(us_long['dates'])} {us_long['dates'][0]}..{us_long['dates'][-1]} "
          f"members={len(us_long['memberSeries'])}")

    # 同步 data.json / data.js
    data_path = ROOT / "data.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    data["usLong"] = us_long
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    js = "window.REITS_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (ROOT / "data.js").write_text(js, encoding="utf-8")
    print(f"[usLong] data.json / data.js 已同步（{len(js) / 1e6:.1f}MB）")


if __name__ == "__main__":
    main()
