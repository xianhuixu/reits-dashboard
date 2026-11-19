#!/usr/bin/env python3
"""Split bulky research snapshots for on-demand loading.

Does not change field definitions or coerce values. The full
research/operating-data.json and research/fund-archives/{code}.json
snapshots remain the source of truth (and the downloadable archive).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Fund-archive UI packs. Tables may appear in more than one pack (share_event).
ARCHIVE_PACKS = {
    "shell": (
        "ops_metric",
        "financials",
        "asset",
        "issue_pricing",
        "reit_offering_ifind",
        "reit_originator",
        "reit_fee",
        "concession_end",
    ),
    "quotes": ("daily_quote",),
    "finance": ("distribution", "forecast", "appraisal_assumption", "valuation"),
    "assets": (
        "extension_offer",
        "share_event",
        "reit_asset_ifind",
        "reit_operator",
        "reit_project_company",
        "reit_originator_info",
    ),
    "holders": ("holder_structure", "top_holders", "share_event"),
    "originals": (
        "ops_indicator_raw",
        "project_perf",
        "revenue_breakdown",
        "cost_breakdown",
        "distcalc_item",
        "project_fin",
        "project_bs",
        "fund_fee",
        "expansion_status",
        "customer_conc",
    ),
}


def dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False) + "\n")


def split_operating_data(src: Path | None = None, dest_dir: Path | None = None) -> dict:
    src = Path(src or ROOT / "research/operating-data.json")
    dest_dir = Path(dest_dir or ROOT / "research")
    data = json.loads(src.read_text())
    points = data.get("points") or []
    index = {k: v for k, v in data.items() if k != "points"}
    index["pointCount"] = len(points)
    index["periodPacks"] = {p: "operating-data/periods/" + p + ".json" for p in data.get("periods") or []}
    dump(dest_dir / "operating-data-index.json", index)

    by_period = {}
    by_fund = {}
    for p in points:
        by_period.setdefault(p["period"], []).append(p)
        by_fund.setdefault(p["code"], []).append(p)

    period_dir = dest_dir / "operating-data" / "periods"
    fund_dir = dest_dir / "operating-data" / "funds"
    if period_dir.exists():
        for old in period_dir.glob("*.json"):
            old.unlink()
    if fund_dir.exists():
        for old in fund_dir.glob("*.json"):
            old.unlink()

    for period, rows in by_period.items():
        dump(period_dir / (period + ".json"), {"period": period, "schemaVersion": data.get("schemaVersion", 1), "points": rows})
    for code, rows in by_fund.items():
        dump(fund_dir / (code + ".json"), {"code": code, "schemaVersion": data.get("schemaVersion", 1), "points": rows})

    return {
        "periods": len(by_period),
        "funds": len(by_fund),
        "points": len(points),
        "index": str(dest_dir / "operating-data-index.json"),
    }


def split_one_archive(payload: dict, dest_dir: Path) -> Path:
    code = payload["code"]
    tables = payload.get("tables") or {}
    index = {
        "schemaVersion": payload.get("schemaVersion", 1),
        "code": code,
        "info": payload.get("info"),
        "coverage": payload.get("coverage"),
        "quality": payload.get("quality"),
        "packs": sorted(ARCHIVE_PACKS),
    }
    out = dest_dir / code
    if out.exists():
        for old in out.glob("*.json"):
            old.unlink()
    dump(out / "index.json", index)
    for name, keys in ARCHIVE_PACKS.items():
        pack = {k: tables.get(k, []) for k in keys}
        dump(out / (name + ".json"), pack)
    return out


def split_fund_archives(src_dir: Path | None = None) -> dict:
    src_dir = Path(src_dir or ROOT / "research/fund-archives")
    files = sorted(p for p in src_dir.glob("*.json") if p.name != "manifest.json")
    for path in files:
        split_one_archive(json.loads(path.read_text()), src_dir)
    return {"funds": len(files), "dir": str(src_dir)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--operating", action="store_true")
    p.add_argument("--archives", action="store_true")
    args = p.parse_args()
    run_all = not args.operating and not args.archives
    if args.operating or run_all:
        print("operating", json.dumps(split_operating_data(), ensure_ascii=False))
    if args.archives or run_all:
        print("archives", json.dumps(split_fund_archives(), ensure_ascii=False))


if __name__ == "__main__":
    main()
