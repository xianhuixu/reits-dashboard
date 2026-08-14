#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""data.js/data.json 数据质量闸门：校验通过退出码 0，异常退出码 1。
供 scripts/auto_update.sh 在提交推送前调用，防止坏数据上线。"""
import json, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

try:
    with open('data.json', encoding='utf-8') as f:
        d = json.load(f)
except Exception as e:
    print(f"[check] data.json 读取失败: {e}")
    sys.exit(1)

reits = d.get('reits') or []
count = d.get('count') or 0
updated = d.get('updated')
lastTradeDate = d.get('lastTradeDate')
problems = []

if len(reits) < 80:
    problems.append(f"reits 数量过少 ({len(reits)} < 80)")
if count != len(reits):
    problems.append(f"count({count}) 与 reits 数量({len(reits)}) 不一致")
if not updated or not lastTradeDate:
    problems.append("updated/lastTradeDate 缺失")
bad_close = sum(1 for r in reits if r.get('close') is None or r.get('close') <= 0)
if bad_close > 3:
    problems.append(f"{bad_close} 只个券 close 无效")
bad_amt = sum(1 for r in reits if (r.get('amount') or 0) <= 0)
if bad_amt > 10:
    problems.append(f"{bad_amt} 只个券 amount 异常")

if problems:
    print(f"[check] 校验失败: {'; '.join(problems)}")
    sys.exit(1)

print(f"[check] 通过：{len(reits)} 只 · 截至 {lastTradeDate} · 更新 {updated}")
print(f"[check] 抽查 {reits[0]['code']} {reits[0]['name']}: close={reits[0].get('close')}, pct={reits[0].get('pct')}, amount={reits[0].get('amount')}")
