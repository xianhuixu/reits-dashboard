#!/usr/bin/env python3
"""
自动更新周期判断宏观数据
- 10年期国债收益率（东方财富数据中心「中美国债收益率」接口，纯 urllib，无第三方依赖）
- 增长×利率 REITs 投资时钟 rateClock（10Y 60日变化动态死区+滞回 × PMI 偏离趋势 z 分数，见 rate_clock.py / docs/rate-clock.md）
- 社融脉冲领先预警 tsfImpulse（商务部数据中心社融增量 + 东财名义 GDP）
- 产权利差真实序列 data_panel_l1l7.json.propertySpread（scripts/build_spread.py --refresh；新浪/东财抓取失败 → 沿用缓存、status=lagged）
- 升息快于租金闸门 rateRentGate（利率腿真实 10Y；产权利差分位腿 = propertySpread 滚动 3 年分位 60 日变化；租金端 rentLeg）
- PMI、CPI 等 pm/cycles/clock 文字判定仍保留手动维护
真实序列缓存在 macro_series.json（供 fetch_data*.py 计算 Δ10Y 敏感度）；取数失败时沿用缓存并标注 asOf，绝不插值。
"""
import json
import re
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


def _pick(name, fresh, old, ok, meta):
    """fresh 满足 ok → live；否则沿用缓存（origin=cache）；都没有 → unavailable。绝不插值。"""
    if ok(fresh):
        return dict(meta, origin="live", series=fresh)
    if (old or {}).get("series"):
        print(f"[warn] {name} 取数失败/不足，沿用缓存 asOf={old.get('asOf')}")
        return dict(old, origin="cache")
    return dict(meta, origin="unavailable", asOf=None, series=[])


def refresh_macro_series(today_str, fetch_y10=rc.fetch_cgb10y_history, fetch_pmi=rc.fetch_pmi_history,
                         fetch_tsf=rc.fetch_tsf_history, fetch_gdp=rc.fetch_gdp_cum_history,
                         fetch_curve=rc.fetch_cgb_curve_latest):
    """拉取真实 10Y 日序列 / PMI / 社融增量 / 名义 GDP 累计值 / 中债曲线关键期限；失败则沿用缓存（origin=cache）。"""
    cache = _load(MACRO_JSON) or {}
    y10, pmi, tsf, gdp = fetch_y10(), fetch_pmi(), fetch_tsf(), fetch_gdp()
    try:
        curve = fetch_curve()
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 中债曲线获取失败: {e}")
        curve = None
    out = {
        "_comment": "真实宏观序列缓存（update_cycle_data.py 自动写入；不得手工编辑/插值）。供 rateClock、社融脉冲、rateRentGate、Beta 的 Δ10Y 敏感度与经营权期限匹配利差使用",
        "updated": today_str,
    }
    out["cgb10y"] = _pick("10Y 日序列", y10, cache.get("cgb10y"),
                          lambda s: len(s) > rc.RATE_LOOKBACK + rc.RATE_SIGMA_WINDOW,
                          {"source": rc.CGB10Y_SOURCE, "asOf": y10[-1]["date"] if y10 else None, "fetchedAt": today_str,
                           "unit": "%", "start": rc.RATE_SERIES_START})
    out["pmi"] = _pick("PMI", pmi, cache.get("pmi"), lambda s: len(s) > rc.PMI_TREND_WINDOW + rc.PMI_Z_WINDOW + 2,
                       {"source": rc.PMI_SOURCE, "asOf": pmi[-1]["month"] if pmi else None, "fetchedAt": today_str})
    out["tsf"] = _pick("社融增量", tsf, cache.get("tsf"), lambda s: len(s) >= 24,
                       {"source": rc.TSF_SOURCE, "asOf": tsf[-1]["month"] if tsf else None, "fetchedAt": today_str, "unit": "亿元"})
    out["gdp"] = _pick("名义 GDP", gdp, cache.get("gdp"), lambda s: len(s) >= 8,
                       {"source": rc.GDP_SOURCE, "asOf": gdp[-1]["month"] if gdp else None, "fetchedAt": today_str,
                        "unit": "亿元（年内累计）"})
    old_c = cache.get("cgbCurve") or {}
    if curve and curve.get("points"):
        out["cgbCurve"] = {"source": rc.CGB_CURVE_SOURCE, "origin": "live", "fetchedAt": today_str, "unit": "%", **curve}
    elif old_c.get("points"):
        out["cgbCurve"] = dict(old_c, origin="cache")
    else:
        out["cgbCurve"] = {"source": rc.CGB_CURVE_SOURCE, "origin": "unavailable", "asOf": None, "points": []}
    return out


def dump_macro(macro) -> str:
    """缩进 1，但序列每行一条（控制体积与 diff 噪声）。"""
    txt = json.dumps(macro, ensure_ascii=False, indent=1)
    return re.sub(r"\{\n\s+(\"(?:date|month)\": [^\n]+),\n\s+(\"(?:value|cum)\": [^\n]+)\n\s+\}",
                  r"{\1, \2}", txt) + "\n"


def refresh_property_spread(refresh=True):
    """产权利差（scripts/build_spread.py）：需在 macro_series.json 写入之后、闸门计算之前运行。
    任何异常 → 保留上一次 propertySpread 并降为 lagged（绝不标 live）。返回最新面板。"""
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_spread as bs
    try:
        return bs.run(refresh=refresh, write=True)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 产权利差计算失败，沿用上一次结果并标 lagged: {e!r}")
        panel = _load(PANEL_JSON)
        if panel and panel.get("propertySpread"):
            bs.mark_lagged(panel, f"计算失败（{type(e).__name__}），沿用上一次成功数据")
            bs.write_panel(panel)
        return panel


def apply_rate_clock(cycle, macro, advice, panel, today_str):
    y10 = (macro.get("cgb10y") or {}).get("series") or []
    pmi = (macro.get("pmi") or {}).get("series") or []
    block = rc.compute_rate_clock(y10, pmi, old_block=cycle.get("rateClock"), today=today_str)
    block["seriesOrigin"] = {"y10": (macro.get("cgb10y") or {}).get("origin"),
                             "pmi": (macro.get("pmi") or {}).get("origin")}
    block["conflictFlags"] = rc.conflict_flags(block, advice)
    cycle["rateClock"] = block
    cycle["tsfImpulse"] = rc.compute_tsf_impulse(
        (macro.get("tsf") or {}).get("series") or [], (macro.get("gdp") or {}).get("series") or [], today_str,
        origin={"tsf": (macro.get("tsf") or {}).get("origin"), "gdp": (macro.get("gdp") or {}).get("origin")})
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
            MACRO_JSON.write_text(dump_macro(macro), encoding="utf-8")
        panel = refresh_property_spread(refresh=True) or _load(PANEL_JSON)
        apply_rate_clock(cycle, macro, _load(ADVICE_JSON), panel, today_str)
        rcb = cycle["rateClock"]
        print(f"[info] rateClock: {rcb.get('status')} {rcb.get('state')} {rcb.get('quadrant') or ('lean ' + str(rcb.get('leanQuadrant')))} {rcb.get('quadrantName')} "
              f"Δ10Y60={rcb.get('d10y60bp')}bp 阈值±{rcb.get('thresholdBp')}bp z3={(rcb.get('growth') or {}).get('z3')} "
              f"社融脉冲={cycle['tsfImpulse'].get('value')}%@{cycle['tsfImpulse'].get('asOf')} "
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
