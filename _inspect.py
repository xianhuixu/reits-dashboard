import json, os
os.chdir("/Users/lion/Desktop/Vibe Coding/reits-dashboard")
with open("data.json", "r", encoding="utf-8") as f:
    data = json.load(f)
print("Top-level keys:", list(data.keys()))
for k, v in data.items():
    print(f"  {k}: type={type(v).__name__}, len={len(v) if hasattr(v, '__len__') else 'N/A'}")
