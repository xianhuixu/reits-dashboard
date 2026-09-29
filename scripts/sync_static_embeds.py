#!/usr/bin/env python3
"""把手工/静态 JSON 同步进已生成的前端数据包，而不重新抓行情。

- cycle_judgment.json → data.json / data.js 的 cycle（含 rateClock / rateRentGate）
- overseas_clock_du2021.json → data_research.json 的 overseasClock（并移除旧 overseasStatic 占位）
- data_research.json.correlation.betas 缺失时写入 status=pending（等待 fetch_data*.py 用真实行情计算）

用法：python3 scripts/sync_static_embeds.py   （在仓库根目录；每日 CI 中 fetch_data_em.py 会重新生成这些字段）
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    cycle = json.loads((ROOT / "cycle_judgment.json").read_text(encoding="utf-8"))
    core = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
    core["cycle"] = cycle
    (ROOT / "data.json").write_text(json.dumps(core, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "data.js").write_text("window.REITS_DATA = " + json.dumps(core, ensure_ascii=False) + ";\n", encoding="utf-8")

    rp = ROOT / "data_research.json"
    rest = json.loads(rp.read_text(encoding="utf-8"))
    rest.pop("overseasStatic", None)
    rest["overseasClock"] = json.loads((ROOT / "overseas_clock_du2021.json").read_text(encoding="utf-8"))
    corr = rest.get("correlation")
    if isinstance(corr, dict) and "betas" not in corr:
        corr["betas"] = {"status": "pending", "bySector": [], "byReit": [], "rolling": None,
                         "reason": "待 fetch_data_em.py / fetch_data.py 以真实周频行情（000300.SH / 000012.SH / REITs）计算；"
                                   "静态同步脚本不生成任何 Beta 数值"}
    rp.write_text(json.dumps(rest, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[sync] data.json/data.js cycle, data_research.json overseasClock/betas 已同步")


if __name__ == "__main__":
    main()
