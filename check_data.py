import json, os
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
with open('data.json') as f:
    d = json.load(f)
print(f"updated: {d.get('updated')}")
print(f"lastTradeDate: {d.get('lastTradeDate')}")
print(f"count: {d.get('count')}")
# 抽查2只
reits = d.get('reits', [])
for r in reits[:2]:
    print(f"抽查 {r['code']} {r['name']}: close={r.get('close')}, pct={r.get('pct')}")
print('校验完成')
