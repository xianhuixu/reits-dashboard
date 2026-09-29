#!/usr/bin/env python3
"""校验 P0/P1「投资时钟 + Beta」相关产出（schema + 数据诚信约束）。

用法：python3 validate_rate_clock.py   （退出码 0 = 通过；供 tests/test_validate_rate_clock.py 与本地/CI 手动调用）
检查：
- overseas_clock_du2021.json：原文数字逐项核对、口径=年化总回报、业态只用区间色带（无点值）、来源 URL
- 旧占位矩阵 overseas_static.json 已移除且不再被前端/脚本引用
- cycle_judgment.json：rateClock / rateRentGate 结构与状态枚举；ok 时必须带真实来源与 asOf
- advice.json：clockSectorPrior 覆盖 9 个中国板块、声明「映射为本仪表盘假设」；advice.js 与 advice.json 同步
- data_research.json：overseasClock 已嵌入、correlation.betas 为 ok 或 pending（pending 时不得含 Beta 数值）
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QS = {"Q1", "Q2", "Q3", "Q4", "Q4-stagflation"}
BANDS = {">15%", "10-15%", ">10%", ">=10%", "<10%", "<0", "n/a"}
ARTICLE = {"Q1": 4.9, "Q2": 23.9, "Q3": 3.5, "Q4": 15.1, "Q4-stagflation": -10.7, "Q4-recovery": 26.1}
CN_SECTORS = {"保租房", "市政环保", "能源", "高速公路", "数据中心", "仓储物流", "产业园", "消费", "商业不动产"}


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def check_overseas(errs):
    oc = load("overseas_clock_du2021.json")
    src = oc.get("source") or {}
    if "1719823577102902700" not in (src.get("url") or ""):
        errs.append("overseas_clock: source.url 缺失")
    for k in ("author", "outlet", "date", "sample"):
        if not src.get(k):
            errs.append(f"overseas_clock: source.{k} 缺失")
    if "年化总回报" not in (oc.get("metric") or "") or "超额" in (oc.get("metric") or ""):
        errs.append("overseas_clock: metric 必须为年化总回报")
    got = {}
    for q in oc.get("quadrants") or []:
        got[q["id"]] = q.get("annualTotalReturn")
        for sp in q.get("split") or []:
            got[sp["id"]] = sp.get("annualTotalReturn")
    for k, v in ARTICLE.items():
        if got.get(k) != v:
            errs.append(f"overseas_clock: {k} 应为 {v}，实际 {got.get(k)}")
    for s in oc.get("bySector") or []:
        for z in ("best", "danger"):
            zone = s.get(z)
            if zone is not None and (not isinstance(zone, list) or not set(zone) <= QS):
                errs.append(f"overseas_clock: {s.get('type')} {z} 非法 {zone}")
        for col, b in (s.get("bands") or {}).items():
            if col not in QS or b not in BANDS:
                errs.append(f"overseas_clock: {s.get('type')} band {col}={b} 非法（只允许区间色带，不允许点值）")
        extra = {k for k, v in s.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
        if extra:
            errs.append(f"overseas_clock: {s.get('type')} 含数值点字段 {extra}")
    if (ROOT / "overseas_static.json").exists():
        errs.append("overseas_static.json 占位矩阵应已删除")
    for f in ("app.js", "fetch_data_em.py", "fetch_data.py"):
        if "overseas_static.json" in (ROOT / f).read_text(encoding="utf-8").replace("已删除的 overseas_static.json", "") or \
                "overseasStatic" in (ROOT / f).read_text(encoding="utf-8"):
            errs.append(f"{f} 仍引用 overseas_static / overseasStatic")


def check_cycle(errs):
    cy = load("cycle_judgment.json")
    rc = cy.get("rateClock")
    if not rc:
        errs.append("cycle_judgment: 缺少 rateClock（运行 update_cycle_data.py）")
        return
    if rc.get("status") not in ("ok", "unavailable"):
        errs.append(f"rateClock.status 非法 {rc.get('status')}")
    if rc.get("status") == "ok":
        if rc.get("quadrant") not in ("Q1", "Q2", "Q3", "Q4", None):
            errs.append("rateClock.quadrant 非法")
        for k in ("asOf", "d10y60bp", "growth", "sources", "history", "confidence"):
            if rc.get(k) in (None, "", []):
                errs.append(f"rateClock.{k} 缺失")
        if not all(h.get("month") and "quadrant" in h for h in rc.get("history") or []):
            errs.append("rateClock.history 条目缺 month/quadrant")
        if rc.get("rateDir") not in ("up", "down", "flat"):
            errs.append("rateClock.rateDir 非法")
    for f in rc.get("conflictFlags") or []:
        if f.get("level") not in ("conflict", "watch", "background") or not f.get("text"):
            errs.append(f"rateClock.conflictFlags 条目非法 {f}")
    g = cy.get("rateRentGate")
    if not g or g.get("status") not in ("triggered", "not_triggered", "pending data"):
        errs.append("rateRentGate 缺失或 status 非法")
    elif (g.get("spreadLeg") or {}).get("status") == "ok":
        panel = load("data_panel_l1l7.json")
        if (panel.get("seedMeta") or {}).get("liveFetch") is not True:
            errs.append("rateRentGate: 产权利差分位仍为 SEED，却被当作真实数据使用")


def check_advice(errs):
    adv = load("advice.json")
    pri = adv.get("clockSectorPrior") or []
    if {p.get("sector") for p in pri} != CN_SECTORS:
        errs.append(f"clockSectorPrior 板块集合不符: {sorted(p.get('sector') for p in pri)}")
    for p in pri:
        for k in ("usAnalog", "analogConfidence", "note"):
            if not p.get(k):
                errs.append(f"clockSectorPrior {p.get('sector')} 缺 {k}")
        if "假设" not in (p.get("note") or "") or "并非" not in (p.get("note") or ""):
            errs.append(f"clockSectorPrior {p.get('sector')} note 未声明映射为本仪表盘假设")
        for z in ("best", "danger"):
            if p.get(z) is not None and not set(p[z]) <= QS:
                errs.append(f"clockSectorPrior {p.get('sector')} {z} 非法")
    cons = next((p for p in pri if p.get("sector") == "消费"), {})
    if "Q3" not in (cons.get("danger") or []) or not cons.get("conflictFlag"):
        errs.append("clockSectorPrior 消费 应含 Q3 雷区与 conflictFlag")
    if not adv.get("rateRentGate", {}).get("rule"):
        errs.append("advice.rateRentGate.rule 缺失")
    js = (ROOT / "advice.js").read_text(encoding="utf-8")
    if js != "window.REITS_ADVICE = " + json.dumps(adv, ensure_ascii=False) + ";\n":
        errs.append("advice.js 与 advice.json 不同步")


def check_research(errs):
    rd = load("data_research.json")
    if "overseasStatic" in rd:
        errs.append("data_research.json 仍含 overseasStatic 占位")
    if not (rd.get("overseasClock") or {}).get("quadrants"):
        errs.append("data_research.json 缺 overseasClock")
    b = (rd.get("correlation") or {}).get("betas")
    if b is None:
        errs.append("data_research.json 缺 correlation.betas（ok 或 pending）")
        return
    if b.get("status") == "pending":
        if b.get("byReit") or b.get("bySector"):
            errs.append("betas pending 状态下不得含数值")
    elif b.get("status") == "ok":
        for k in ("asOf", "window", "rollWindow", "bySector", "byReit", "classRule"):
            if b.get(k) in (None, ""):
                errs.append(f"betas.{k} 缺失")
        for r in b.get("byReit") or []:
            if r.get("cls") not in ("偏股", "偏债", "中性", None):
                errs.append(f"betas {r.get('code')} cls 非法")
    else:
        errs.append(f"betas.status 非法 {b.get('status')}")


def main() -> int:
    errs: list[str] = []
    for fn in (check_overseas, check_cycle, check_advice, check_research):
        try:
            fn(errs)
        except Exception as e:  # noqa: BLE001
            errs.append(f"{fn.__name__} 异常: {e}")
    if errs:
        print("[validate_rate_clock] FAIL")
        for e in errs:
            print("  -", e)
        return 1
    print("[validate_rate_clock] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
