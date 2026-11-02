#!/usr/bin/env python3
"""重建派生文件并校验一致性（market-series.json、首页 banner 预渲染）。

用途：
1) git post-merge hook 调用——合并/拉取远端每日更新后自动重建；
2) deploy_cf.sh 部署前自检——发现派生文件过期则自动重建。

--check 模式：仅校验不修改，不一致时退出码 1（供 CI / 部署前拦截）。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKET_SERIES = ROOT / "market-series.json"
RESEARCH = ROOT / "data_research.json"


def market_series_stale() -> bool:
    """market-series.json 与 data_research.json 是否脱节。"""
    if not MARKET_SERIES.exists():
        return True
    compact = json.loads(MARKET_SERIES.read_text(encoding="utf-8"))
    source = json.loads(RESEARCH.read_text(encoding="utf-8"))
    series = source.get("series") or {}
    return compact.get("dates") != series.get("dates") or compact.get("market") != series.get("market")


def rebuild() -> None:
    """按 daily-update.yml 的顺序重建派生文件。"""
    for step in (["python3", "scripts/build_market_series.py"],
                 ["python3", "scripts/prerender_banner.py"]):
        subprocess.run(step, cwd=ROOT, check=True)


def main() -> int:
    check_only = "--check" in sys.argv
    if not market_series_stale():
        print("[ok] 派生文件与源数据一致", flush=True)
        return 0
    if check_only:
        print("[stale] market-series.json 与 data_research.json 不一致，"
              "请运行 python3 scripts/rebuild_derived.py", flush=True)
        return 1
    print("[rebuild] 派生文件过期，正在重建……", flush=True)
    rebuild()
    if market_series_stale():
        print("[error] 重建后仍不一致", flush=True)
        return 1
    print("[done] 派生文件已重建（market-series.json + banner 预渲染）", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
