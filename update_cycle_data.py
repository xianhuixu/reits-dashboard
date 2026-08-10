#!/usr/bin/env python3
"""
自动更新周期判断宏观数据
- 10年期国债收益率（从 akshare 新浪财经接口获取）
- PMI、CPI 等月度数据（保留手动维护）
"""
import json
import sys
from datetime import date
from pathlib import Path

import akshare as ak

ROOT = Path(__file__).resolve().parent
CYCLE_JSON = ROOT / "cycle_judgment.json"


def fetch_bond10y():
    """从新浪财经获取10年期国债收益率"""
    try:
        df = ak.bond_gb_zh_sina(symbol="中国10年期国债")
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            close = float(latest["close"])
            date_str = str(latest["date"])
            print(f"[info] 新浪债券数据: {date_str} 收盘 {close}%")
            return round(close, 2), date_str
    except Exception as e:
        print(f"[warn] akshare 获取国债收益率失败: {e}")
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
