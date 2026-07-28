import json, os
os.chdir("/Users/lion/Desktop/Vibe Coding/reits-dashboard")
data = json.load(open("data.json", "r", encoding="utf-8"))
reits = data.get("reits", [])
avg_pct = sum(r["pct"] for r in reits) / len(reits)
print(f"全市场等权涨跌幅: {avg_pct:.2f}%")
