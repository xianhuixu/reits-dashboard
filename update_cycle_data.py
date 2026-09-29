#!/usr/bin/env python3
"""
自动更新周期判断宏观数据
- 10年期国债收益率（东方财富数据中心「中美国债收益率」接口，纯 urllib，无第三方依赖）
- 增长×利率 REITs 投资时钟 rateClock（10Y 60日变化 × 制造业 PMI 3月均值/趋势，见 rate_clock.py / docs/rate-clock.md）
- 升息快于租金闸门 rateRentGate（利率腿真实；产权利差分位腿待 live 数据）
- PMI、CPI 等 pm/cycles/clock 文字判定仍保留手动维护
真实序列缓存在 macro_series.json（供 fetch_data*.py 计算 Δ10Y 敏感度）；取数失败时沿用缓存并标注 asOf，绝不插值。
"""
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

import rate_clock as rc

ROOT = Path(__file__).resolve().parent
CYCLE_JSON = ROOT / "cycle_judgment.json"
MACRO_JSON = ROOT / "macro_series.json"
ADVICE_JSON = ROOT / "advice.json"
PANEL_JSON = ROOT / "data_panel_l1l7.json"

# 东财字段：EMM00166466 = 中国国债收益率10年
URL = ("https://datacenter.eastmoney.com/api/data/get?type=RPTA_WEB_TREASURYYIELD"
       "&sty=ALL&st=SOLAR_DATE&sr=-1&p=1&ps=5&source=WEB")


def fetch_bond10y():
    """从东方财富数据中心获取最新10年期国债收益率"""
    try:
        req = urllib.request.Request(URL, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://data.eastmoney.com/",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            rows = json.loads(resp.read().decode("utf-8")).get("result", {}).get("data") or []
        for row in rows:  # 倒序返回，取第一条非空的
            v = row.get("EMM00166466")
            if v is not None:
                date_str = str(row.get("SOLAR_DATE", ""))[:10]
                print(f"[info] 东财国债数据: {date_str} 10Y收盘 {v}%")
                return round(float(v), 2), date_str
    except Exception as e:
        print(f"[warn] 东财获取国债收益率失败: {e}")
    return None, None


def _load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def refresh_macro_series(today_str, fetch_y10=rc.fetch_cgb10y_history, fetch_pmi=rc.fetch_pmi_history):
    """拉取真实 10Y 日序列与 PMI 月序列；失败则沿用 macro_series.json 缓存（标注 origin=cache）。"""
    cache = _load(MACRO_JSON) or {}
    y10 = fetch_y10()
    pmi = fetch_pmi()
    out = {
        "_comment": "真实宏观序列缓存（update_cycle_data.py 自动写入；不得手工编辑/插值）。供 rateClock、rateRentGate 与 Beta 的 Δ10Y 敏感度使用",
        "updated": today_str,
    }
    old_y = (cache.get("cgb10y") or {})
    old_p = (cache.get("pmi") or {})
    if len(y10) > rc.RATE_LOOKBACK:
        out["cgb10y"] = {"source": rc.CGB10Y_SOURCE, "origin": "live", "asOf": y10[-1]["date"],
                         "fetchedAt": today_str, "unit": "%", "series": y10}
    elif old_y.get("series"):
        out["cgb10y"] = dict(old_y, origin="cache")
        print(f"[warn] 10Y 日序列取数失败，沿用缓存 asOf={old_y.get('asOf')}")
    else:
        out["cgb10y"] = {"source": rc.CGB10Y_SOURCE, "origin": "unavailable", "asOf": None, "series": []}
    if len(pmi) >= 3:
        out["pmi"] = {"source": rc.PMI_SOURCE, "origin": "live", "asOf": pmi[-1]["month"],
                      "fetchedAt": today_str, "series": pmi}
    elif old_p.get("series"):
        out["pmi"] = dict(old_p, origin="cache")
        print(f"[warn] PMI 取数失败，沿用缓存 asOf={old_p.get('asOf')}")
    else:
        out["pmi"] = {"source": rc.PMI_SOURCE, "origin": "unavailable", "asOf": None, "series": []}
    return out


def apply_rate_clock(cycle, macro, advice, panel, today_str):
    y10 = (macro.get("cgb10y") or {}).get("series") or []
    pmi = (macro.get("pmi") or {}).get("series") or []
    block = rc.compute_rate_clock(y10, pmi, old_block=cycle.get("rateClock"), today=today_str)
    block["seriesOrigin"] = {"y10": (macro.get("cgb10y") or {}).get("origin"),
                             "pmi": (macro.get("pmi") or {}).get("origin")}
    block["conflictFlags"] = rc.conflict_flags(block, advice)
    cycle["rateClock"] = block
    cycle["rateRentGate"] = rc.rate_rent_gate(y10, panel)
    return cycle


def update_cycle_data():
    if not CYCLE_JSON.exists():
        print(f"[error] {CYCLE_JSON} 不存在")
        return False

    cycle = json.loads(CYCLE_JSON.read_text(encoding="utf-8"))
    updated = False
    today_str = date.today().strftime("%Y-%m-%d")

    # 更新国债收益率
    bond10y, bond_date = fetch_bond10y()
    if bond10y is not None:
        old_bond = cycle.get("bond10y")
        cycle["bond10y"] = bond10y
        print(f"[info] bond10y: {old_bond}% -> {bond10y}% (数据日期: {bond_date})")
        updated = True

    # 增长×利率时钟 + 升息/租金闸门（宏观背景层）
    try:
        macro = refresh_macro_series(today_str)
        if (macro.get("cgb10y") or {}).get("series"):
            MACRO_JSON.write_text(json.dumps(macro, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        apply_rate_clock(cycle, macro, _load(ADVICE_JSON), _load(PANEL_JSON), today_str)
        rcb = cycle["rateClock"]
        print(f"[info] rateClock: {rcb.get('status')} {rcb.get('state')} {rcb.get('quadrant') or ('lean ' + str(rcb.get('leanQuadrant')))} {rcb.get('quadrantName')} "
              f"Δ10Y60={rcb.get('d10y60bp')}bp PMI3m={(rcb.get('growth') or {}).get('pmi3m')} "
              f"冲突 {len(rcb.get('conflictFlags') or [])} 条；rateRentGate={cycle['rateRentGate']['status']}")
        updated = True
    except Exception as e:
        print(f"[warn] rateClock 计算失败（保留旧值）: {e}")

    # 更新日期
    if updated:
        cycle["updated"] = today_str
        CYCLE_JSON.write_text(
            json.dumps(cycle, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8"
        )
        print(f"[info] 已更新 {CYCLE_JSON}")
    else:
        print("[info] 没有自动获取的数据需要更新（PMI/CPI仍需手动维护）")

    return updated


if __name__ == "__main__":
    try:
        update_cycle_data()
    except Exception as e:
        print(f"[error] 更新周期数据失败: {e}")
        sys.exit(1)
