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
    check_schema(panel)
    if args.check:
        return
    # Live fetch placeholder — keep seed; only refresh JS mirror
    # TODO: iFinD/Wind pull when credentials & codes confirmed
    write_js(panel)


if __name__ == "__main__":
    main()
