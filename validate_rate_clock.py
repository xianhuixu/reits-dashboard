#!/usr/bin/env python3
"""校验 P0/P1「投资时钟 + Beta」相关产出（schema + 数据诚信约束）。

用法：python3 validate_rate_clock.py   （退出码 0 = 通过；供 tests/test_validate_rate_clock.py 与本地/CI 手动调用）
检查：
- overseas_clock_du2021.json：原文数字逐项核对、口径=年化总回报、业态只用区间色带（无点值）、来源 URL
- 旧占位矩阵 overseas_static.json 已移除且不再被前端/脚本引用
- cycle_judgment.json：rateClock / rateRentGate / tsfImpulse 结构与状态枚举；ok 时必须带真实来源与 asOf；
  利率轴动态阈值（进入线 = max(5bp, 0.7σ)、退出线 = 进入线/2）与滞回一致性、增长 z3 滞回一致性、
  确定象限 ⇔ 两轴均有方向；旧 PMI 49.5–50.5 边界规则已移除；社融脉冲 pending 时不得含数值
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


STATES = {"definite", "transitional", "undetermined"}
FLAG_LEVELS = {"conflict", "watch", "background", "reference"}
RATE_FLOOR_BP, RATE_K, EXIT_RATIO = 5.0, 0.7, 0.5
G_ENTER, G_EXIT = 0.5, 0.25
TOL = 0.051  # 存档值保留 1 位小数（bp）/ 2 位小数（σ）的容差


def _growth_rules(z3, gs, where, errs):
    """月度增长滞回：z3 ≥ +0.5 ⇒ 高于趋势(1)；≤ −0.5 ⇒ 低于趋势(−1)；|z3| < 0.25 ⇒ 趋势附近(0)。"""
    if z3 is None or gs is None:
        return
    if gs not in (1, 0, -1):
        errs.append(f"{where}: growthState 非法 {gs}")
    elif z3 >= G_ENTER + 0.005 and gs != 1:
        errs.append(f"{where}: z3 {z3} ≥ +0.5 却不是「高于趋势」")
    elif z3 <= -G_ENTER - 0.005 and gs != -1:
        errs.append(f"{where}: z3 {z3} ≤ −0.5 却不是「低于趋势」")
    elif abs(z3) < G_EXIT - 0.005 and gs != 0:
        errs.append(f"{where}: z3 {z3} 在 ±0.25 以内却未退回「趋势附近」")


def _rate_rules(d, t, e, rdir, pending, where, errs):
    """利率滞回（无待确认时）：上行 ⇒ d ≥ −… 不低于退出线；下行 ⇒ d ≤ −E；走平 ⇒ |d| ≤ T；退出线 = 进入线/2，进入线 ≥ 5bp。"""
    if t is None or d is None:
        return
    if t < RATE_FLOOR_BP - 1e-9:
        errs.append(f"{where}: 进入线 {t}bp 低于 5bp 下限")
    if e is not None and abs(e - t * EXIT_RATIO) > TOL:
        errs.append(f"{where}: 退出线 {e}bp ≠ 进入线/2（{t}bp）")
    if pending:
        return
    if rdir == "up" and d < e - TOL:
        errs.append(f"{where}: 上行状态但 Δ10Y {d}bp 已低于退出线 +{e}bp 且无待确认")
    if rdir == "down" and d > -e + TOL:
        errs.append(f"{where}: 下行状态但 Δ10Y {d}bp 已高于退出线 −{e}bp 且无待确认")
    if rdir == "flat" and abs(d) > t + TOL:
        errs.append(f"{where}: 走平状态但 |Δ10Y| {abs(d)}bp 超出进入线 {t}bp 且无待确认")


def _state_rules(obj, gs, where, errs):
    """单个时点：确定象限 ⇔ 利率有方向 且 增长高于/低于趋势；过渡期无象限、置信度低。"""
    st, q, rdir = obj.get("state"), obj.get("quadrant"), obj.get("rateDir")
    if st not in STATES:
        errs.append(f"{where}: state 非法 {st}")
        return
    if st == "transitional":
        if q is not None:
            errs.append(f"{where}: 过渡期不得给出象限（quadrant={q}）")
        if rdir in ("up", "down") and gs in (1, -1):
            errs.append(f"{where}: 两轴均有方向却标为过渡期")
        if obj.get("confidence") not in (None, "低"):
            errs.append(f"{where}: 过渡期置信度必须为 低")
        if "过渡期" not in (obj.get("stateLabel") or ""):
            errs.append(f"{where}: 过渡期 stateLabel 须含「过渡期」")
        if obj.get("leanQuadrant") not in ("Q1", "Q2", "Q3", "Q4", None):
            errs.append(f"{where}: leanQuadrant 非法")
    elif st == "definite":
        if q not in ("Q1", "Q2", "Q3", "Q4"):
            errs.append(f"{where}: 确定状态必须给出象限")
        if rdir not in ("up", "down") or gs not in (1, -1):
            errs.append(f"{where}: 利率走平或增长趋势附近却判定了象限 {q}")
        want = {("up", 1): "Q1", ("down", 1): "Q2", ("down", -1): "Q3", ("up", -1): "Q4"}.get((rdir, gs))
        if want and q != want:
            errs.append(f"{where}: 象限 {q} 与两轴方向不符（应为 {want}）")
    elif q is not None:
        errs.append(f"{where}: undetermined 不得给出象限")


def check_dead_band(rc, errs):
    g = rc.get("growth") or {}
    gs = g.get("state")
    _state_rules(rc, gs, "rateClock", errs)
    _rate_rules(rc.get("d10y60bp"), rc.get("thresholdBp"), rc.get("exitBp"), rc.get("rateDir"), rc.get("ratePending"), "rateClock", errs)
    _growth_rules(g.get("z3"), gs, "rateClock.growth", errs)
    sig = rc.get("sigma60bp")
    if sig is not None and rc.get("thresholdBp") is not None and abs(rc["thresholdBp"] - max(RATE_FLOOR_BP, RATE_K * sig)) > 0.1:
        errs.append(f"rateClock: 进入线 {rc['thresholdBp']}bp ≠ max(5, 0.7×σ {sig}bp)")
    if "boundary" in g or "pmi3m" in g or "49.5" in json.dumps(rc.get("method") or {}, ensure_ascii=False):
        errs.append("rateClock: 旧「PMI 49.5–50.5 边界」规则应已移除")
    if g.get("critical") and "临界" not in (rc.get("summary") or ""):
        errs.append("rateClock: 增长临界但 summary 未标「临界」")
    st = rc.get("state")
    if st == "transitional":
        if rc.get("usPriorAnnualReturn") is not None:
            errs.append("rateClock: 过渡期 usPriorAnnualReturn 应为空（最近象限先验放 leanUsPriorAnnualReturn）")
        hard = [f for f in rc.get("conflictFlags") or [] if f.get("level") != "reference"]
        if hard:
            errs.append(f"rateClock: 过渡期只允许「参考」级提示，发现 {[f.get('level') for f in hard]}")
    elif st == "definite":
        if any(f.get("level") == "reference" for f in rc.get("conflictFlags") or []):
            errs.append("rateClock: 确定象限不应出现 reference 级提示")
    sw = rc.get("signalSwitch")
    if sw is not None:
        if sw.get("cause") not in ("methodology", "market") or not sw.get("note") or not sw.get("date"):
            errs.append("rateClock.signalSwitch 缺 cause/note/date")
        if sw.get("cause") == "methodology" and "口径" not in sw.get("note", ""):
            errs.append("rateClock.signalSwitch 口径切换须注明「来自口径更新」")
    for h in rc.get("history") or []:
        w = f"rateClock.history[{h.get('month')}]"
        _state_rules(h, h.get("growthState"), w, errs)
        _rate_rules(h.get("d10y60bp"), h.get("thresholdBp"), h.get("exitBp"), h.get("rateDir"), h.get("ratePending"), w, errs)
        _growth_rules(h.get("z3"), h.get("growthState"), w, errs)


def check_tsf(cy, errs):
    t = cy.get("tsfImpulse")
    if not t:
        errs.append("cycle_judgment: 缺少 tsfImpulse（运行 update_cycle_data.py）")
        return
    if t.get("status") == "pending":
        if t.get("value") is not None or t.get("series"):
            errs.append("tsfImpulse pending 时不得含数值（前端显示「待接入」）")
        if t.get("label") != "待接入":
            errs.append("tsfImpulse pending 时 label 应为「待接入」")
    elif t.get("status") == "ok":
        for k in ("asOf", "asOfLabel", "value", "series", "sources", "interpretation", "formula"):
            if t.get(k) in (None, "", []):
                errs.append(f"tsfImpulse.{k} 缺失")
        if "数据截至" not in (t.get("asOfLabel") or ""):
            errs.append("tsfImpulse.asOfLabel 须写「数据截至 X月」")
        if (t.get("series") or [[None]])[-1][0] != t.get("asOf"):
            errs.append("tsfImpulse.series 末点与 asOf 不一致")
        if "−0.45" not in (t.get("interpretation") or "") or "方向" not in (t.get("interpretation") or ""):
            errs.append("tsfImpulse.interpretation 须注明相关系数约 −0.45 且只看方向")
    else:
        errs.append(f"tsfImpulse.status 非法 {t.get('status')}")


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
        for k in ("thresholdBp", "exitBp", "sigma60bp", "summary", "rateDistance", "methodVersion"):
            if rc.get(k) in (None, ""):
                errs.append(f"rateClock.{k} 缺失")
        check_dead_band(rc, errs)
    check_tsf(cy, errs)
    for f in rc.get("conflictFlags") or []:
        if f.get("level") not in FLAG_LEVELS or not f.get("text"):
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
