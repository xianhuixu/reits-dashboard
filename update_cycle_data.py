#!/usr/bin/env python3
"""
自动更新周期判断宏观数据
- 10年期国债收益率（东方财富数据中心「中美国债收益率」接口，纯 urllib，无第三方依赖）
- PMI、CPI 等月度数据（保留手动维护）
"""
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CYCLE_JSON = ROOT / "cycle_judgment.json"

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
