# 修复 hist_cache 中腾讯"手"单位行 → ×100 归一为"份"（与 iFinD 口径一致）
# 用法：在含 hist_cache/ 的仓库根目录执行
#   python3 scripts/repair_volume_units.py
# 原理：以腾讯日K成交量（手）为参照，缓存行 volume 与腾讯手数之比 <5 的判定为"手"口径，×100 归一
# 注意：需可访问 web.ifzq.gtimg.cn；美股/港股代码结构不同会跳过（其 volume 不参与成交额计算）

import json, time, ssl, urllib.request, glob, os
import pandas as pd

ctx = ssl._create_unverified_context()
ROOT = os.getcwd()

def tencent_code(code):
    m = {"SH": "sh", "SZ": "sz"}
    if "." in code:
        return m.get(code.split(".")[1], "") + code.split(".")[0]
    return code

def tencent_vol(code, n=25):
    tc = tencent_code(code)
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={tc},day,,,{n},na"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        d = json.loads(urllib.request.urlopen(req, timeout=20, context=ctx).read().decode("utf-8"))
        ks = d.get("data", {}).get(tc, {}).get("day") or d.get("data", {}).get(tc, {}).get("qfqday") or []
        return pd.DataFrame(ks, columns=["time", "open", "close", "high", "low", "volume"])[["time", "volume"]]
    except Exception as e:
        print(f"  [tx-fail] {code}: {e}")
        return None

fixed_files, fixed_rows = 0, 0
for f in sorted(glob.glob(os.path.join(ROOT, "hist_cache", "*.csv"))):
    code = os.path.basename(f).replace("_", ".").replace(".csv", "")
    if "HK" in code:  # 港股缓存不参与修复（volume 结构不同）
        continue
    d = pd.read_csv(f, dtype={"time": str})
    if "volume" not in d.columns or len(d) < 5:
        continue
    tx = tencent_vol(code)
    if tx is None or not len(tx):
        continue
    m = d.merge(tx, on="time", how="left", suffixes=("", "_tx"))
    m["volume"] = pd.to_numeric(m["volume"], errors="coerce")
    m["volume_tx"] = pd.to_numeric(m["volume_tx"], errors="coerce")
    mask = m["volume_tx"].notna() & (m["volume_tx"] > 0)
    ratio = (m.loc[mask, "volume"] / m.loc[mask, "volume_tx"])
    hand_rows = mask & (ratio < 5)  # cache ≈ 腾讯手数 → 单位是"手"
    n = int(hand_rows.sum())
    if n:
        m.loc[hand_rows, "volume"] = m.loc[hand_rows, "volume"] * 100
        m = m.drop(columns=["volume_tx"])
        m.to_csv(f, index=False)
        fixed_files += 1
        fixed_rows += n
        print(f"  fixed {os.path.basename(f)}: {n} 行 ×100")
    time.sleep(0.3)
print(f"\n[repair done] {fixed_files} files, {fixed_rows} rows")
