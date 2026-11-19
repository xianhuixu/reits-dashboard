#!/usr/bin/env python3
"""Aggregate fund-level operating snapshots for the 赛道透视 view.

Read-only: never mutates operating-data, advice, or signal files.
Only fund-scope (asset_id ALL) points enter the pack. Project-level
values are never used as a fund substitute. Heterogeneous units and
mixed calibers/tax flags are kept in separate series. Missing values
are omitted, never coerced to 0. Quarterly trends use a changing
sample; each point carries its coverage count. Adjacent-period rise
counts use a fixed fund sample and are not labeled as same-store.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]

SECTOR_ALIAS = {
    "交通": "高速公路",
    "保障性租赁住房": "保租房",
    "水务环保": "市政环保",
}

# Preferred single series per metric. Other calibers/tax flags are not mixed in.
METRICS = [
    dict(id="occupancy_rate", label="出租率", unit_label="%", source_unit="小数", caliber="期末", tax_flag="不适用", scale=100,
         weighting_note="基金等权、非面积加权",
         note="仅基金层面期末出租率；不用项目点位替代基金值。中位数变化不是同店改善。"),
    dict(id="rent_collection_rate", label="收缴率", unit_label="%", source_unit="小数", caliber="期间", tax_flag="不适用", scale=100,
         weighting_note="基金等权",
         note="只纳入「期间」口径；期末收缴率不并入。"),
    dict(id="wale", label="剩余租约期限", unit_label="年", source_unit="年", caliber="期末", tax_flag="不适用", scale=1,
         weighting_note="基金等权",
         note="期末 WALE，单位为年。"),
    dict(id="traffic_volume", label="日均车流", unit_label="车次/日", source_unit="车次/日", caliber="期间平均", tax_flag="不适用", scale=1,
         weighting_note="基金等权",
         note="仅高速公路/交通；不与出租率等异质指标同轴。"),
    dict(id="power_generation", label="发电量", unit_label="万kWh", source_unit="万kWh", caliber="期间", tax_flag="不适用", scale=1,
         weighting_note="基金等权",
         note="仅能源等适用业态的期间发电量，绝对量受装机规模影响，不宜直接当作效率。"),
    dict(id="utilization_hours", label="利用小时", unit_label="小时", source_unit="小时", caliber="期间", tax_flag="不适用", scale=1,
         weighting_note="基金等权",
         note="期间利用小时，用于补充观察发电效率。"),
    dict(id="rack_utilization", label="上架率", unit_label="%", source_unit="小数", caliber="期末", tax_flag="不适用", scale=100,
         weighting_note="基金等权",
         note="数据中心上架率；样本可能很少。"),
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def display_sector(ops_sector: str, market_sector: str | None) -> str:
    if market_sector:
        return market_sector
    return SECTOR_ALIAS.get(ops_sector, ops_sector)


def period_kind(period: str) -> str:
    s = str(period or "")[4:]
    if s in ("Q1", "Q2", "Q3", "Q4"):
        return "quarter"
    if s == "H1":
        return "semi"
    if s == "A":
        return "annual"
    return "other"


def quarter_start_end(period: str) -> tuple[date, date] | None:
    if period_kind(period) != "quarter":
        return None
    year = int(period[:4])
    q = period[4:]
    starts = {"Q1": (1, 1), "Q2": (4, 1), "Q3": (7, 1), "Q4": (10, 1)}
    ends = {"Q1": (3, 31), "Q2": (6, 30), "Q3": (9, 30), "Q4": (12, 31)}
    s, e = starts[q], ends[q]
    return date(year, s[0], s[1]), date(year, e[0], e[1])


def parse_iso(d: str | None) -> date | None:
    if not d or not isinstance(d, str) or len(d) < 10:
        return None
    try:
        return date.fromisoformat(d[:10])
    except ValueError:
        return None


def fund_has_expansion(assets: list[dict], code: str, start: date, end: date) -> bool:
    for a in assets:
        if a.get("code") != code or a.get("include_type") != "扩募":
            continue
        inc = parse_iso(a.get("include_date"))
        if inc and start <= inc <= end:
            return True
    return False


def select_points(points: list[dict], metric: dict, period: str) -> list[dict]:
    out = []
    for p in points:
        if p.get("period") != period:
            continue
        if p.get("metric") != metric["id"]:
            continue
        if p.get("scope") != "基金" or p.get("asset_id") != "ALL":
            continue
        if p.get("caliber") != metric["caliber"]:
            continue
        if (p.get("unit") or "") != metric["source_unit"]:
            continue
        if (p.get("tax_flag") or "未说明") != metric["tax_flag"]:
            continue
        if p.get("value") is None or not isinstance(p.get("value"), (int, float)):
            continue
        if isinstance(p.get("value"), float) and p["value"] != p["value"]:
            continue
        out.append(p)
    return out


def display_value(raw, scale: float):
    if raw is None:
        return None
    return raw * scale if scale != 1 else raw


def build(root: Path | None = None) -> dict:
    root = Path(root or ROOT)
    ops_path = root / "research" / "operating-data.json"
    data_path = root / "data.json"
    ops = json.loads(ops_path.read_text(encoding="utf-8"))
    market = json.loads(data_path.read_text(encoding="utf-8"))
    market_by_code = {r["code"]: r for r in market.get("reits") or []}
    assets = ops.get("assets") or []
    funds = ops.get("funds") or []
    points = ops.get("points") or []
    latest = ops.get("latestPeriod")
    quarters = [p for p in (ops.get("periods") or []) if period_kind(p) == "quarter"]

    def meta_for(code: str, ops_fund: dict) -> dict:
        m = market_by_code.get(code)
        sector = display_sector(ops_fund.get("sector_l1"), m["sector"] if m else None)
        return {
            "code": code,
            "name": (m and m.get("name")) or ops_fund.get("short_name") or code,
            "sector": sector,
            "opsSector": ops_fund.get("sector_l1"),
            "right": (m and m.get("right")) or None,
            "listed": bool(m),
        }

    fund_meta = {f["code"]: meta_for(f["code"], f) for f in funds}
    sector_universe = {}
    for meta in fund_meta.values():
        sector_universe.setdefault(meta["sector"], []).append(meta["code"])

    metrics_out = []
    latest_out = {}
    trend_out = {}

    for metric in METRICS:
        mid = metric["id"]
        metrics_out.append({k: metric[k] for k in metric})
        # latest snapshot
        latest_rows = select_points(points, metric, latest)
        by_sector: dict[str, list] = {}
        for p in latest_rows:
            meta = fund_meta[p["code"]]
            item = dict(meta)
            item.update(value=p["value"], display=display_value(p["value"], metric["scale"]))
            bounds = quarter_start_end(latest)
            item["expansionInPeriod"] = bool(bounds and fund_has_expansion(assets, p["code"], *bounds))
            by_sector.setdefault(meta["sector"], []).append(item)
        sectors_latest = []
        for sector, items in sorted(by_sector.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            vals = [i["value"] for i in items]
            universe = sector_universe.get(sector) or []
            disclosed = {i["code"] for i in items}
            undisclosed = [c for c in universe if c not in disclosed]
            sectors_latest.append({
                "sector": sector,
                "n": len(items),
                "universe": len(universe),
                "undisclosed": len(undisclosed),
                "undisclosedCodes": undisclosed,
                "median": median(vals) if vals else None,
                "medianDisplay": display_value(median(vals), metric["scale"]) if vals else None,
                "min": min(vals) if vals else None,
                "max": max(vals) if vals else None,
                "expansionInPeriod": sum(1 for i in items if i["expansionInPeriod"]),
                "funds": sorted(items, key=lambda i: (i["value"], i["code"])),
            })
        latest_out[mid] = {
            "period": latest,
            "periodKind": period_kind(latest),
            "caliber": metric["caliber"],
            "unit": metric["source_unit"],
            "tax_flag": metric["tax_flag"],
            "sectors": sectors_latest,
        }

        # quarterly changing-sample trend + fixed-sample pairs
        trend_sectors: dict[str, dict] = {}
        # collect per period
        period_map: dict[str, dict[str, list]] = {}
        for period in quarters:
            rows = select_points(points, metric, period)
            for p in rows:
                sec = fund_meta[p["code"]]["sector"]
                period_map.setdefault(period, {}).setdefault(sec, []).append(p)

        all_sectors = sorted({sec for mp in period_map.values() for sec in mp})
        for sector in all_sectors:
            pts = []
            for period in reversed(quarters):  # chronological
                rows = period_map.get(period, {}).get(sector) or []
                if not rows:
                    continue
                vals = [p["value"] for p in rows]
                pts.append({
                    "period": period,
                    "n": len(rows),
                    "median": median(vals),
                    "medianDisplay": display_value(median(vals), metric["scale"]),
                    "codes": [p["code"] for p in rows],
                })
            # adjacent quarter pairs (chronological)
            fixed = []
            for a, b in zip(pts, pts[1:]):
                # only if periods are true neighbors in the quarter list
                try:
                    ia = quarters[::-1].index(a["period"])
                    ib = quarters[::-1].index(b["period"])
                except ValueError:
                    continue
                if ib != ia + 1:
                    # still OK if we skipped empty periods in pts — then they are not adjacent in time
                    chrono = list(reversed(quarters))
                    if chrono.index(b["period"]) != chrono.index(a["period"]) + 1:
                        # there were empty quarters in between; still compare these two disclosed periods?
                        # Analyst asked for coverage on changing sample; for fixed sample, adjacent disclosed quarters is OK if we label the from/to.
                        pass
                set_a, set_b = set(a["codes"]), set(b["codes"])
                common = sorted(set_a & set_b)
                start, _ = quarter_start_end(a["period"]) or (None, None)
                _, end = quarter_start_end(b["period"]) or (None, None)
                excluded = []
                if start and end:
                    kept = []
                    for code in common:
                        if fund_has_expansion(assets, code, start, end):
                            excluded.append(code)
                        else:
                            kept.append(code)
                    common = kept
                val_a = {p["code"]: p["value"] for p in period_map[a["period"]][sector]}
                val_b = {p["code"]: p["value"] for p in period_map[b["period"]][sector]}
                n_up = n_down = n_flat = 0
                for code in common:
                    dv = val_b[code] - val_a[code]
                    if dv > 0:
                        n_up += 1
                    elif dv < 0:
                        n_down += 1
                    else:
                        n_flat += 1
                n = len(common)
                fixed.append({
                    "from": a["period"],
                    "to": b["period"],
                    "n": n,
                    "nUp": n_up,
                    "nDown": n_down,
                    "nFlat": n_flat,
                    "upShare": (n_up / n) if n else None,
                    "downShare": (n_down / n) if n else None,
                    "excludedExpansion": len(excluded),
                    "note": "固定基金样本的报告值升降家数，未核验资产范围，不是同店改善。",
                })
            trend_sectors[sector] = {"sector": sector, "points": pts, "fixedPairs": fixed}
        trend_out[mid] = {
            "caliber": metric["caliber"],
            "unit": metric["source_unit"],
            "tax_flag": metric["tax_flag"],
            "sampleNote": "各期变动样本中位数，点旁为当期覆盖只数；连线可能只反映样本更换，不代表经营改善或恶化。",
            "sectors": [trend_sectors[s] for s in all_sectors],
        }

    heda = [p for p in points if p.get("code") == "180103.SZ" and p.get("metric") == "occupancy_rate" and p.get("period") == latest]
    return {
        "schemaVersion": 1,
        "generatedFrom": {
            "operatingData": "research/operating-data.json",
            "operatingImportedAt": ops.get("importedAt"),
            "operatingSha256": sha256_file(ops_path),
            "marketData": "data.json",
            "marketUpdated": market.get("updated"),
            "dataSha256": sha256_file(data_path),
        },
        "timezone": "Asia/Shanghai",
        "latestPeriod": latest,
        "periodsQuarterly": quarters,
        "sourceNotes": [
            "经营点位来自用户提供的爬取库快照（chinareits 经营数据入库），只读聚合。",
            "仅基金层面（scope=基金且 asset_id=ALL）；项目点位不替代基金值。",
            "同一序列只保留单一报告期粒度、统计口径、单位与税标记；缺失为尚未披露，不作 0。",
            "出租率分布为基金等权、非面积加权；出租率中位数环比不是同店改善。",
            "季度趋势为变动样本中位数，必须阅读每期覆盖数；不把中位数升降写成改善/恶化。",
            "项目范围未复核，不绘制同比。产权与经营权估值由前端分图读取已有面板，不在此包硬混。",
        ],
        "sectorAliases": SECTOR_ALIAS,
        "metrics": metrics_out,
        "latest": latest_out,
        "trend": trend_out,
        "selfCheck": {
            "hedaFundOccupancy": next((p["value"] for p in heda if p.get("scope") == "基金" and p.get("asset_id") == "ALL"), None),
            "hedaProjectOccupancies": sorted({p["value"] for p in heda if p.get("scope") == "项目"}),
        },
    }


def write(payload: dict, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    out = args.output or (args.root / "research" / "track-analysis.json")
    payload = build(args.root)
    write(payload, out)
    heda = payload["selfCheck"]
    print("period", payload["latestPeriod"], "bytes", out.stat().st_size,
          "hedaFund", heda["hedaFundOccupancy"], "hedaProjects", heda["hedaProjectOccupancies"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
