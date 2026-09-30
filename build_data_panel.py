#!/usr/bin/env python3
"""Build / refresh data_panel_l1l7.json (+ data_panel.js).

Phase A stub: does NOT call Wind / iFinD / 中债登 yet.
- Default: leave existing seed JSON untouched (or rewrite wrapper JS from JSON).
- Future: pull bond10ySeries, property TTM (mcap-weighted), operating IRR (mcap-weighted),
  benchmarksNormalized, marketLiquidity, sectorSnapshot, csiReitsMonth and overwrite seed.

Usage:
  python3 build_data_panel.py            # sync data_panel.js from JSON
  python3 build_data_panel.py --check    # schema key presence check only

Do not wire into daily-update until live fetch is ready — seed is OK for first PR.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JSON_PATH = ROOT / "data_panel_l1l7.json"
JS_PATH = ROOT / "data_panel.js"
MACRO_PATH = ROOT / "macro_series.json"
TERM_KEY = "operatingSpreadTermMatched"
TERM_STATUSES = {"pending", "ok"}

REQUIRED_TOP = [
    "updated",
    "asOfTrade",
    "bond10ySeries",
    "propertyYieldSeries",
    "operatingIrrSeries",
    "benchmarksNormalized",
    "marketLiquidity",
    "sectorSnapshot",
    "csiReitsMonth",
]


def load_panel() -> dict:
    if not JSON_PATH.exists():
        raise SystemExit(f"missing {JSON_PATH}")
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


def write_js(panel: dict) -> None:
    js = "window.REITS_DATA_PANEL = " + json.dumps(panel, ensure_ascii=False, separators=(",", ":")) + ";\n"
    JS_PATH.write_text(js, encoding="utf-8")
    print(f"[data_panel] wrote {JS_PATH.name} ({len(js)} bytes)")


def term_matched_block(panel: dict, macro: dict | None) -> dict:
    """经营权期限匹配利差块：曲线来自 macro_series.json.cgbCurve（东财中债 2/5/10/30Y，live）；
    经营权 REITs 市值加权剩余期限 + live IRR 尚未接入 → status=pending，不生成任何利差数值、不回退 10Y。"""
    old = panel.get(TERM_KEY) or {}
    curve = (macro or {}).get("cgbCurve") or old.get("curve") or {}
    blk = {
        "status": "pending",
        "label": "待接入 · 期限匹配（当前图仍为 SEED IRR−10Y）",
        "formula": "经营权利差 = IRR − 与市值加权剩余期限匹配的中债国债收益率（2/5/10/30Y 关键期限线性插值，端点外水平外推）",
        "propertyFormula": "产权利差 = TTM 分派率 − 10Y（不变）",
        "pendingReason": "缺经营权 REITs 剩余期限（逐只，市值加权）与 live IRR；曲线已接入。数据齐备前不展示期限匹配利差数值",
        "interpolation": "cgb_curve.interp_yield / term_matched_spread（tests/test_cgb_curve.py）",
        "creditSpreadAAplus": "未接入：AA+ 信用利差无易得的免费日频源，本期跳过",
        "curve": {k: curve.get(k) for k in ("asOf", "points", "source", "origin") if curve.get(k) is not None},
    }
    if curve.get("points"):
        import cgb_curve
        blk["curvePreview"] = [{"years": t, "yield": round(cgb_curve.interp_yield(curve["points"], t)[0], 4)}
                               for t in (3, 7, 15, 20)]
    return blk


def check_term_block(panel: dict) -> None:
    blk = panel.get(TERM_KEY)
    if not blk:
        raise SystemExit(f"schema missing {TERM_KEY}（运行 python3 build_data_panel.py 生成）")
    if blk.get("status") not in TERM_STATUSES:
        raise SystemExit(f"{TERM_KEY}.status 非法 {blk.get('status')}")
    if "剩余期限" not in (blk.get("formula") or "") or "插值" not in (blk.get("formula") or ""):
        raise SystemExit(f"{TERM_KEY}.formula 必须说明按剩余期限插值")
    if "TTM" not in (blk.get("propertyFormula") or "") or "10Y" not in (blk.get("propertyFormula") or ""):
        raise SystemExit("产权利差口径必须保持 TTM − 10Y")
    if blk["status"] == "pending":
        if any(k in blk for k in ("spread", "series", "remainingYears")):
            raise SystemExit(f"{TERM_KEY} pending 时不得含利差数值")
    else:
        live = (panel.get("seedMeta") or {}).get("liveFetch") is True
        if not live or not blk.get("remainingYears") or not blk.get("series"):
            raise SystemExit(f"{TERM_KEY} ok 需 live IRR + remainingYears + series")
    pts = (blk.get("curve") or {}).get("points") or []
    if pts and not all(isinstance(p, list) and len(p) == 2 for p in pts):
        raise SystemExit(f"{TERM_KEY}.curve.points 格式应为 [[年, %], ...]")


def check_schema(panel: dict) -> None:
    missing = [k for k in REQUIRED_TOP if k not in panel]
    if missing:
        raise SystemExit(f"schema missing keys: {missing}")
    if not panel["propertyYieldSeries"] or not panel["operatingIrrSeries"]:
        raise SystemExit("L2 series empty")
    # Operating spread must be IRR-based (seedMeta / note)
    note = (panel.get("note") or "") + " " + json.dumps(panel.get("seedMeta") or {}, ensure_ascii=False)
    if "IRR" not in note and "irr" not in note:
        print("[warn] operating spread formula note should mention IRR−10Y", file=sys.stderr)
    last_p = panel["propertyYieldSeries"][-1]
    last_o = panel["operatingIrrSeries"][-1]
    if "ttmYield" not in last_p or "spread" not in last_p:
        raise SystemExit("propertyYieldSeries row missing ttmYield/spread")
    if "irr" not in last_o or "spread" not in last_o:
        raise SystemExit("operatingIrrSeries row missing irr/spread")
    check_term_block(panel)
    print(
        f"[data_panel] OK asOf={panel.get('asOfTrade')} "
        f"bond={len(panel['bond10ySeries'])} "
        f"prop={len(panel['propertyYieldSeries'])} "
        f"op={len(panel['operatingIrrSeries'])} "
        f"sectors={len(panel.get('sectorSnapshot') or [])}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="validate schema only")
    args = ap.parse_args()
    panel = load_panel()
    if args.check:
        check_schema(panel)
        return
    # Live fetch placeholder — keep seed; refresh term-matched block (curve from macro_series.json) + JS mirror
    # TODO: iFinD/Wind pull when credentials & codes confirmed
    macro = json.loads(MACRO_PATH.read_text(encoding="utf-8")) if MACRO_PATH.exists() else None
    panel[TERM_KEY] = term_matched_block(panel, macro)
    check_schema(panel)
    JSON_PATH.write_text(json.dumps(panel, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_js(panel)


if __name__ == "__main__":
    main()
