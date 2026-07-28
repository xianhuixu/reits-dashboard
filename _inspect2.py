import json, os
os.chdir("/Users/lion/Desktop/Vibe Coding/reits-dashboard")
data = json.load(open("data.json", "r", encoding="utf-8"))
reits = data.get("reits", [])
print("Total REITs:", len(reits))
if reits:
    print("First REIT keys:", list(reits[0].keys()))
    print("Sample REIT:", json.dumps(reits[0], ensure_ascii=False, indent=2))
