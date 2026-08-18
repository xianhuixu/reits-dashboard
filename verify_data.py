#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""data.js / news.js / corp_actions.js 文件级校验（读取真实产物，不输出硬编码假数据）。

修复记录:
- 修复前用 datetime(2026, 7, 30) 硬编码 today，导致任何时间运行都"通过"
- 修复假打印 "✓ [done] 87/87 只" 等无意义文案
- 不会运行 fetch_data.py / fetch_news.py，只是读取其已落盘的产物
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)


def load_js_payload(path, prefix):
    """从 window.<NAME> = {...} 风格的 .js 文件里提取 JSON 部分。"""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    i = raw.find(prefix)
    if i < 0:
        raise ValueError(f"{path} 缺少 {prefix!r}")
    s = raw[i + len(prefix):].strip()
    if s.endswith(";"):
        s = s[:-1]
    s = s.strip()
    return json.loads(s)


def check_data_js():
    d = load_js_payload("data.js", "window.REITS_DATA = ")
    reits = d.get("reits") or []
    problems = []
    if len(reits) < 80:
        problems.append(f"reits 数量过少 {len(reits)} (<80)")
    close_bad = sum(1 for r in reits if not r.get("close") or r["close"] <= 0)
    if close_bad > 3:
        problems.append(f"{close_bad} 只 close 无效")
    if not d.get("updated") or not d.get("lastTradeDate"):
        problems.append("updated / lastTradeDate 缺失")
    return d, problems


def check_news_js():
    n = load_js_payload("news.js", "window.REITS_NEWS = ")
    items = n.get("items") or []
    problems = []
    today = datetime.now().date()
    cutoff = today - timedelta(days=30)
    out = [i for i in items if datetime.strptime(i["date"], "%Y-%m-%d").date() < cutoff]
    if out:
        problems.append(f"{len(out)} 条新闻超出 30 天范围")
    return n, problems


def check_corp_actions_js():
    c = load_js_payload("corp_actions.js", "window.REITS_ACTIONS = ")
    items = c.get("items") or []
    return c, []  # 公告列表允许为空


def main():
    print("=" * 50)
    print("【数据校验报告】", datetime.now().isoformat(timespec="seconds"))
    print("=" * 50)

    summary = []
    overall_ok = True

    # 1. data.js
    try:
        d, p = check_data_js()
        verdict = "✓" if not p else "✗"
        summary.append((verdict, "data.js", f"{len(d.get('reits', []))} 只 · 截至 {d.get('lastTradeDate')} · 更新 {d.get('updated')}", p))
        if p:
            overall_ok = False
    except Exception as e:
        summary.append(("✗", "data.js", f"读取失败: {e}", [str(e)]))
        overall_ok = False

    # 2. news.js
    try:
        n, p = check_news_js()
        items = n.get("items", [])
        verdict = "✓" if not p else "✗"
        summary.append((verdict, "news.js", f"{len(items)} 条", p))
        if p:
            overall_ok = False
    except Exception as e:
        summary.append(("✗", "news.js", f"读取失败: {e}", [str(e)]))
        overall_ok = False

    # 3. corp_actions.js
    try:
        c, p = check_corp_actions_js()
        summary.append(("✓" if not p else "✗", "corp_actions.js", f"{len(c.get('items', []))} 条", p))
    except Exception as e:
        summary.append(("✗", "corp_actions.js", f"读取失败: {e}", [str(e)]))
        overall_ok = False

    # 4. 抽查
    try:
        d = load_js_payload("data.js", "window.REITS_DATA = ")
        reits = d.get("reits", [])
        if reits:
            head = reits[0]
            tail = reits[-1]
            print(f"\n[抽查] 首只 {head['code']} {head['name']}: close={head.get('close')}, pct={head.get('pct')}%")
            print(f"[抽查] 末只 {tail['code']} {tail['name']}: close={tail.get('close')}, pct={tail.get('pct')}%")
    except Exception:
        pass

    # 输出汇总
    print()
    for verdict, name, info, problems in summary:
        print(f"[{verdict}] {name}: {info}")
        for prob in problems:
            print(f"        - {prob}")

    print()
    if overall_ok:
        print("【校验结论】全部通过 ✓")
        sys.exit(0)
    else:
        print("【校验结论】存在问题 ✗,请检查")
        sys.exit(1)


if __name__ == "__main__":
    main()
