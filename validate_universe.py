#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量验证候选 REITs 代码：能取到近期行情 → 拉官方简称 → 输出 universe_validated2.json"""
import json, subprocess, sys, tempfile
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
IFIND = "/Users/lion/Library/Application Support/kimi-desktop/daimon-share/daimon/runtime/kimi-code/home/plugins/managed/ifind/scripts/ifind_tool.py"

def call(api, params, retries=2):
    import time
    for attempt in range(retries + 1):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            fp = f.name
        params["file_path"] = fp
        subprocess.run([sys.executable, IFIND, "call", "--api-name", api,
                        "--params-json", json.dumps(params)],
                       capture_output=True, text=True, timeout=180)
        p = Path(fp)
        if p.exists() and p.stat().st_size > 10:
            try:
                return pd.read_csv(fp)
            except Exception:
                return None
        time.sleep(5 * (attempt + 1))  # 限频退避
    return None

codes = [l.strip() for l in (ROOT / (sys.argv[3] if len(sys.argv) > 3 else "candidates.txt")).read_text().splitlines()
         if l.strip() and not l.startswith("#")]
# 支持分片运行：python3 validate_universe.py 0 30
if len(sys.argv) >= 3:
    codes = codes[int(sys.argv[1]):int(sys.argv[2])]

valid = []
for i in range(0, len(codes), 3):
    batch = codes[i:i+3]
    df = call("ifind_get_price", {"ticker": ",".join(batch),
              "start_date": "2026-07-20", "end_date": "2026-07-27",
              "interval": "D", "adjust": "none"})
    got = set(df["thscode"].unique()) if df is not None and "thscode" in df.columns else set()
    missing = [c for c in batch if c not in got]
    # 批量查询会被无效代码整体拖空 → 对缺失代码逐一单查
    frames = []
    for c in missing:
        d1 = call("ifind_get_price", {"ticker": c,
                  "start_date": "2026-07-20", "end_date": "2026-07-27",
                  "interval": "D", "adjust": "none"}, retries=1)
        if d1 is not None and "thscode" in d1.columns and len(d1):
            got.add(c)
    for c in batch:
        ok = c in got
        if ok:
            valid.append(c)
        print(("OK  " if ok else "MISS") + " " + c, flush=True)

print(f"\nvalid: {len(valid)}/{len(codes)}")

names = {}
for i in range(0, len(valid), 3):
    batch = valid[i:i+3]
    df = call("ifind_get_stock_info", {"ticker": ",".join(batch)})
    if df is not None and "thscode" in df.columns:
        for _, row in df.iterrows():
            names[row["thscode"]] = str(row.get("ths_stock_short_name_stock", "")).strip()
    print("named:", ", ".join(f"{c}={names.get(c,'?')}" for c in batch), flush=True)

out = [{"code": c, "name": names.get(c, "")} for c in valid]
(ROOT / "universe_validated2.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("written universe_validated2.json:", len(out))
