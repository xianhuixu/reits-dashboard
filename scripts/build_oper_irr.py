#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""经营权披露 IRR 利差（2025 年末口径）→ data_panel_l1l7.json.operatingDisclosedIrr

团队共识（固收 PM + 宏观 + 设计，2026-10）：
  主口径 = 基金披露 IRR − 期限匹配国债（中债 2/5/10/30Y 关键期限线性插值，端点水平外推）
  曲线固定用 2025-12-31（与披露 IRR 同日），禁止混用 9-29 曲线
  期限优先 WAL；无 WAL 时用 remaining_years_to_cf_end，并标注 tenorSource
  自算 IRR（EV 口径）只进悬浮提示，注明「对账偏高，中位约 280bp」
  无披露 → 「暂无披露」；口径不统一 → 不做业态均值 / 横向排名
  本块不回写时钟、不改结论横幅（经营权维持「标配」）

数据源（入库 oper_irr_cache/）：
  irr_summary.csv / prices_2025ye.json（固收 PM 交付）
  cgb_curve_20251231.json（东财 RPTA_WEB_TREASURYYIELD，可 --refresh-curve）

用法：
  python3 scripts/build_oper_irr.py                # 用缓存曲线重算并写面板
  python3 scripts/build_oper_irr.py --refresh-curve  # 拉 2025-12-31 曲线后重算
  python3 scripts/build_oper_irr.py --no-write       # 只打印，不写文件
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import cgb_curve  # noqa: E402

CACHE = ROOT / "oper_irr_cache"
CSV_PATH = CACHE / "irr_summary.csv"
PRICES_YE_PATH = CACHE / "prices_2025ye.json"
CURVE_PATH = CACHE / "cgb_curve_20251231.json"
PANEL_JSON = ROOT / "data_panel_l1l7.json"
PANEL_JS = ROOT / "data_panel.js"

CURVE_DATE = "2025-12-31"
CURVE_FIELDS = {2: "EMM00588704", 5: "EMM00166462", 10: "EMM00166466", 30: "EMM00166469"}
CURVE_SOURCE = (
    "东方财富数据中心 RPTA_WEB_TREASURYYIELD · 中债国债收益率 "
    "2Y(EMM00588704)/5Y(EMM00166462)/10Y(EMM00166466)/30Y(EMM00166469)"
)
SELF_IRR_NOTE = "对账偏高，中位约 280bp"
EXTREME_BP = -400  # 如 180402，只看自身变化，不做排名
LABEL = "2025 年末口径"
FORMULA = "基金披露 IRR − 期限匹配国债（WAL 优先，否则剩余年限；中债 2/5/10/30Y 关键期限线性插值）"


def _f(v):
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.lower() in ("nan", "none", "null"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fetch_curve_20251231() -> dict:
    url = (
        "https://datacenter.eastmoney.com/api/data/get?type=RPTA_WEB_TREASURYYIELD"
        f"&sty=ALL&st=SOLAR_DATE&sr=-1&p=1&ps=5"
        f"&filter=(SOLAR_DATE%3D%27{CURVE_DATE}%27)&source=WEB"
    )
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    rows = ((payload.get("result") or {}).get("data")) or []
    if not rows:
        raise RuntimeError(f"empty CGB curve for {CURVE_DATE}: {payload.get('message')}")
    row = rows[0]
    points = []
    for tenor, field in sorted(CURVE_FIELDS.items()):
        v = row.get(field)
        if v is None:
            raise RuntimeError(f"missing {field} on {CURVE_DATE}")
        points.append([tenor, round(float(v), 4)])
    out = {
        "asOf": CURVE_DATE,
        "points": points,
        "source": CURVE_SOURCE,
        "origin": "live",
        "fetchedAt": datetime.now().strftime("%Y-%m-%d"),
    }
    CACHE.mkdir(parents=True, exist_ok=True)
    CURVE_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def load_curve() -> dict:
    if not CURVE_PATH.exists():
        raise SystemExit(f"missing {CURVE_PATH}; run with --refresh-curve")
    return json.loads(CURVE_PATH.read_text(encoding="utf-8"))


def load_rows() -> list[dict]:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_prices_ye() -> dict:
    return json.loads(PRICES_YE_PATH.read_text(encoding="utf-8"))


def price_change_pct(price, price_ye) -> float | None:
    if price is None or price_ye is None or price_ye == 0:
        return None
    return round((price - price_ye) / price_ye * 100, 2)


def build_items(rows: list[dict], prices_ye: dict, curve: dict) -> tuple[list[dict], list[dict]]:
    points = curve["points"]
    disclosed, pending = [], []
    for r in rows:
        code = r["code"]
        name = r.get("name") or code
        sector = r.get("sector") or ""
        disc = _f(r.get("irr_disclosed_2025YE_pct"))
        price = _f(r.get("price"))
        price_ye = _f(r.get("price_2025ye"))
        if price_ye is None and isinstance(prices_ye.get(code), dict):
            price_ye = _f(prices_ye[code].get("price"))
        px_chg = price_change_pct(price, price_ye)
        self_irr = _f(r.get("IRR_pct"))
        gap = _f(r.get("gap_vs_disclosed_bp"))
        conf = (r.get("confidence") or "").strip() or None
        flag = (r.get("flag") or "").strip()
        review = ("待复核" in flag) or (code.startswith("508096") and "待复核" in (r.get("notes") or ""))
        wal = _f(r.get("WAL"))
        rem = _f(r.get("remaining_years_to_cf_end"))
        mac = _f(r.get("mac_duration"))
        base = {
            "code": code,
            "name": name,
            "sector": sector,
            "price": price,
            "priceAsOf": (r.get("price_date") or "").strip() or None,
            "price2025ye": price_ye,
            "priceChangePct": px_chg,
            "selfIrrPct": self_irr,
            "gapVsDisclosedBp": gap,
            "confidence": conf,
            "flag": flag or None,
            "reviewPending": bool(review),
            "wal": wal,
            "remainingYears": rem,
            "macDuration": mac,
        }
        if disc is None:
            pending.append({**base, "reason": "暂无披露"})
            continue
        if wal is not None and wal > 0:
            tenor, tenor_src = wal, "WAL"
        elif rem is not None and rem > 0:
            tenor, tenor_src = rem, "remaining_years"
        else:
            pending.append({**base, "irrDisclosedPct": disc, "reason": "缺期限（无 WAL / 剩余年限）"})
            continue
        tm = cgb_curve.term_matched_spread(disc, tenor, points)
        if not tm:
            pending.append({**base, "irrDisclosedPct": disc, "reason": "曲线插值失败"})
            continue
        spread_bp = round(tm["spread"] * 100, 1)
        disclosed.append({
            **base,
            "irrDisclosedPct": disc,
            "matchedYieldPct": tm["matchedYield"],
            "tenorYears": tm["years"],
            "tenorSource": tenor_src,
            "extrapolated": tm["extrapolated"],
            "spreadPct": tm["spread"],
            "spreadBp": spread_bp,
            "extreme": spread_bp <= EXTREME_BP,
            "selfIrrNote": SELF_IRR_NOTE if self_irr is not None else None,
        })
    disclosed.sort(key=lambda x: (x["sector"], x["code"]))
    pending.sort(key=lambda x: (x["sector"], x["code"]))
    return disclosed, pending


def sector_rows(disclosed: list[dict]) -> list[dict]:
    """仅计数，不做均值（口径不统一）。"""
    by: dict[str, list] = {}
    for r in disclosed:
        by.setdefault(r["sector"], []).append(r)
    out = []
    for sector in sorted(by):
        rows = by[sector]
        chgs = [r["priceChangePct"] for r in rows if r.get("priceChangePct") is not None]
        out.append({
            "sector": sector,
            "nDisclosed": len(rows),
            "priceChangeMedianPct": round(statistics.median(chgs), 2) if chgs else None,
            "aggregate": None,
            "aggregateNote": "口径不统一，暂不汇总",
        })
    return out


def build_block(disclosed, pending, curve, status, lag_reason, now) -> dict:
    chgs = [r["priceChangePct"] for r in disclosed if r.get("priceChangePct") is not None]
    hw = [r["priceChangePct"] for r in disclosed if r["sector"] == "高速公路" and r.get("priceChangePct") is not None]
    extremes = [r for r in disclosed if r.get("extreme")]
    gaps = [r["gapVsDisclosedBp"] for r in disclosed if r.get("gapVsDisclosedBp") is not None]
    return {
        "status": status,
        "label": LABEL,
        "formula": FORMULA,
        "asOf": CURVE_DATE,
        "priceAsOf": next((r.get("priceAsOf") for r in disclosed if r.get("priceAsOf")), None),
        "curve": {
            "asOf": curve.get("asOf"),
            "points": curve.get("points"),
            "source": curve.get("source"),
            "origin": curve.get("origin"),
        },
        "coverage": {
            "universe": len(disclosed) + len(pending),
            "disclosed": len(disclosed),
            "pending": len(pending),
            "withWal": sum(1 for r in disclosed if r.get("tenorSource") == "WAL"),
            "withRemainingYears": sum(1 for r in disclosed if r.get("tenorSource") == "remaining_years"),
        },
        "items": disclosed,
        "pending": pending,
        "sectors": sector_rows(disclosed),
        "summary": {
            "priceChangeMedianPct": round(statistics.median(chgs), 2) if chgs else None,
            "highwayPriceChangeMedianPct": round(statistics.median(hw), 2) if hw else None,
            "gapVsDisclosedMedianBp": round(statistics.median(gaps), 1) if gaps else None,
            "selfIrrNote": SELF_IRR_NOTE,
            "noSectorAverage": True,
            "noSpreadSort": True,
            "feedsBanner": False,
            "extremeNote": (
                "利差极端个券（如披露 IRR 为负）只看自身变化，不做横向排名；"
                + ("当前：" + "、".join(f"{e['code']} {e['spreadBp']}bp" for e in extremes) if extremes else "无")
            ),
        },
        "lagReason": lag_reason,
        "updated": now,
        "source": (
            "固收 PM irr_summary.csv（基金披露 IRR / WAL）· "
            f"中债曲线 {CURVE_DATE}（东财 RPTA_WEB_TREASURYYIELD）· "
            "年末以来价格变动 = 现价 / 2025-12-31 收盘 − 1"
        ),
        "badge": LABEL,
        "chartNote": (
            "主点 = 基金披露 IRR − 期限匹配国债；自算 IRR 仅悬浮提示"
            f"（{SELF_IRR_NOTE}）；暂无披露见下方空心点；"
            "利差列不可排序；业态不汇总。"
        ),
    }


def apply_to_panel(panel: dict, block: dict) -> dict:
    panel["operatingDisclosedIrr"] = block
    panel["updated"] = block.get("updated") or panel.get("updated")
    # 期限匹配 live 时序仍 pending；披露截面独立，不把 operatingSpreadTermMatched 标 ok
    tm = panel.get("operatingSpreadTermMatched") or {}
    tm["disclosedCrossSection"] = {
        "status": block["status"],
        "label": block["label"],
        "asOf": block["asOf"],
        "n": block["coverage"]["disclosed"],
        "note": "截面披露口径已接入；市值加权 live IRR 时序仍待接入",
    }
    panel["operatingSpreadTermMatched"] = tm
    sm = panel.setdefault("seedMeta", {})
    sm["operatingDisclosedLive"] = block["status"] == "ok"
    sm["operatingDisclosedSource"] = "scripts/build_oper_irr.py（2025 年末披露口径）"
    sm["operatingSpreadFormula"] = "IRR - term-matched CGB (disclosed YE2025 cross-section; series still seed IRR-10Y)"
    note_bits = [
        "产权序列（propertyYieldSeries / propertySpread）为真实数据",
        "经营权披露 IRR 截面（operatingDisclosedIrr）为 2025 年末口径真实数据",
        "经营权 IRR 月度时序（operatingIrrSeries）、bond10ySeries 月度锚点、sectorSnapshot 仍为 SEED",
    ]
    sm["note"] = "；".join(note_bits)
    panel["note"] = (
        "产权序列为 scripts/build_spread.py 真实数据；"
        "经营权披露 IRR 截面为 scripts/build_oper_irr.py（2025 年末口径）；"
        "经营权 IRR 月度时序 / sectorSnapshot 等仍为 PPT SEED。"
        "经营权利差主口径 = 基金披露 IRR − 期限匹配国债；不回写结论横幅。"
    )
    return panel


def write_panel(panel: dict) -> None:
    PANEL_JSON.write_text(json.dumps(panel, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    PANEL_JS.write_text(
        "window.REITS_DATA_PANEL = " + json.dumps(panel, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )


def run(refresh_curve: bool = False, write: bool = True) -> dict:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        curve = fetch_curve_20251231() if refresh_curve else load_curve()
        status, lag = "ok", None
    except Exception as exc:  # noqa: BLE001
        if not CURVE_PATH.exists():
            raise
        curve = load_curve()
        status, lag = "lagged", f"曲线刷新失败，沿用缓存 {CURVE_PATH.name}（{exc}）"
    rows = load_rows()
    prices_ye = load_prices_ye()
    disclosed, pending = build_items(rows, prices_ye, curve)
    if not disclosed:
        status, lag = "lagged", "无可用披露 IRR 行"
    block = build_block(disclosed, pending, curve, status, lag, now)
    panel = json.loads(PANEL_JSON.read_text(encoding="utf-8"))
    apply_to_panel(panel, block)
    if write:
        write_panel(panel)
    cov = block["coverage"]
    print(
        f"[oper_irr] {status} label={block['label']} curve={curve.get('asOf')} "
        f"disclosed={cov['disclosed']} pending={cov['pending']} "
        f"pxMed={block['summary']['priceChangeMedianPct']}% "
        f"hwMed={block['summary']['highwayPriceChangeMedianPct']}% "
        f"feedsBanner={block['summary']['feedsBanner']}"
    )
    return panel


if __name__ == "__main__":
    run(refresh_curve="--refresh-curve" in sys.argv, write="--no-write" not in sys.argv)
