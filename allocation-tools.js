/* 配置研究辅助工具：只读行情；情景参数独立于任何原始财务模型。 */
(function (root) {
  "use strict";
  /** @param {number} rate @param {number} years @returns {number} */
  function annuity(rate, years) {
    return Math.abs(rate) < 1e-10 ? years : (1 - Math.pow(1 + rate, -years)) / rate;
  }
  /** 等额年末现金流的估值敏感性，仅用于示例，不代表任一个券。
   * @param {{kind:string,rate:number,shock:number,cash:number,years:number}} p
   * @returns {number}
   */
  function stress(p) {
    if (![p.rate, p.shock, p.cash, p.years].every(Number.isFinite) ||
      p.rate <= 0 || p.rate + p.shock <= 0 || p.cash < -1 || p.years < 1 ||
      !Number.isInteger(p.years) || !["property", "concession"].includes(p.kind)) {
      throw new RangeError("请检查贴现率、剩余年限和现金流假设。");
    }
    var ratio = p.kind === "property" ? p.rate / (p.rate + p.shock) :
      annuity(p.rate + p.shock, p.years) / annuity(p.rate, p.years);
    return (1 + p.cash) * ratio - 1;
  }
  /** @param {Array<{right?:string,ret20?:number}>} rows @param {string} right
   * @returns {{count:number,valid:number,ret20:number|null}} */
  function summarize(rows, right) {
    var group = rows.filter(function (r) { return r.right === right; });
    var values = group.map(function (r) { return r.ret20; }).filter(Number.isFinite);
    return { count: group.length, valid: values.length,
      ret20: values.length ? values.reduce(function (a, b) { return a + b; }, 0) / values.length : null };
  }
  /** 象限区间是否命中（Q4 滞胀子态只在 subState=滞胀 时命中 Q4-stagflation）。 */
  function inZone(zone, quadrant, sub) {
    if (!zone || !zone.length || !quadrant) return false;
    return zone.indexOf(quadrant) >= 0 || (quadrant === "Q4" && sub === "滞胀" && zone.indexOf("Q4-stagflation") >= 0);
  }
  function zoneLabel(zone) {
    return zone && zone.length ? zone.map(function (z) { return z === "Q4-stagflation" ? "Q4·滞胀" : z; }).join(" / ") : "未给出";
  }
  /** advice.clockSectorPrior × sectorViews × 当前 rateClock → 表格行（纯函数，便于测试）。
   * 过渡期（利率走平或增长趋势附近，2026-09-30 校准口径）不判定象限：按最近象限推演，命中时 status=reference（软提示「参考」），不产生 conflict/watch。
   * @param {any} advice @param {any} clock @returns {Array<any>} */
  function clockPriorRows(advice, clock) {
    var views = {};
    ((advice && advice.sectorViews) || []).forEach(function (v) { views[v.sector] = v; });
    var live = clock && clock.status === "ok";
    var trans = !!(live && clock.state === "transitional" && clock.leanQuadrant);
    var definite = !!(live && !trans && clock.quadrant);
    var q = definite ? clock.quadrant : trans ? clock.leanQuadrant : null;
    var sub = definite ? clock.subState : trans ? clock.leanSubState : null;
    return ((advice && advice.clockSectorPrior) || []).map(function (p) {
      var action = (views[p.sector] || {}).action || "—";
      var over = /超配/.test(action) && !/低配/.test(action);
      var under = /低配|观望|谨慎/.test(action);
      var inDanger = inZone(p.danger, q, sub), inBest = inZone(p.best, q, sub);
      var hit = over && inDanger ? "conflict" : under && inBest ? "watch" : null;
      var status = hit ? (trans ? "reference" : hit) : p.conflictFlag ? "static" : "ok";
      return { sector: p.sector, action: action, usAnalog: p.usAnalog, best: zoneLabel(p.best), danger: zoneLabel(p.danger),
        confidence: p.analogConfidence, inDanger: inDanger, inBest: inBest, status: status, reference: trans,
        softOf: trans ? hit : null, flag: p.conflictFlag || "", evidence: p.chinaEvidence || "" };
    });
  }
  /** 配置倾向文本 → 语义色类（超配=深蓝 / 偏超配=蓝描边 / 标配=灰 / 低配=琥珀）；红绿只留给价格涨跌。
   * @param {string} action @returns {"alloc-ow"|"alloc-ow-lite"|"alloc-n"|"alloc-uw"} */
  function allocClass(action) {
    var a = String(action || "");
    if (/低配|减配|回避|谨慎|观望/.test(a)) return "alloc-uw";
    if (/超配/.test(a)) return /标配|偏超配/.test(a) ? "alloc-ow-lite" : "alloc-ow";
    return "alloc-n";
  }
  function escText(v) { return String(v == null ? "" : v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  /** 时钟摘要行（配置页状态行与周期页共用口径）：「增长高于趋势（临界）· 利率下行」+ 信号切换/临界标签 + 口径说明。
   * @param {any} clock @returns {string} HTML */
  function clockHeadline(clock) {
    if (!clock || clock.status !== "ok" || !clock.summary) return "";
    var sw = clock.signalSwitch && clock.signalSwitch.active ? clock.signalSwitch : null;
    var crit = !!((clock.growth && clock.growth.critical) || (clock.rateDistance && clock.rateDistance.critical));
    return '<span class="clock-state-line"><b>' + escText(clock.summary) + "</b>" +
      (sw ? '<span class="rc-tag rc-tag-warn">信号切换</span>' : "") + (crit ? '<span class="rc-tag rc-tag-warn">临界</span>' : "") + "</span>" +
      (sw ? '<br><span class="rc-switch-note" style="display:inline">' + escText(sw.note) + "</span>" : "");
  }

  // ---------------- 配置页重排（设计师线框 2026-09-30）：纯函数，node 下可测 ----------------
  var ALLOC_LABEL = { "alloc-ow": "超配", "alloc-ow-lite": "偏超配", "alloc-n": "标配", "alloc-uw": "低配" };
  /** 配置倾向文本 → {cls, label}（超配 / 偏超配 / 标配 / 低配，沿用 #15 蓝阶色板 + ↑↗→↓）。 */
  function allocLabel(action) {
    var c = allocClass(action);
    return { cls: c, label: ALLOC_LABEL[c] };
  }
  /** advice.rating 去掉括注：「结构性偏多（引用…）」→「结构性偏多」。 */
  function ratingShort(advice) {
    var r = String((advice && advice.rating) || "").replace(/[（(].*$/, "").trim();
    return r || null;
  }
  /** 学派立场：{rating, property, operating, text}，text 形如「结构性偏多：产权超配 · 经营权标配」。advice 缺失 → null。 */
  function schoolStance(advice) {
    if (!advice) return null;
    var rv = advice.rightsViews || {};
    var p = rv["产权"] ? allocLabel(rv["产权"].view) : null;
    var o = rv["经营权"] ? allocLabel(rv["经营权"].view) : null;
    var rating = ratingShort(advice);
    var parts = [];
    if (p) parts.push("产权" + p.label);
    if (o) parts.push("经营权" + o.label);
    var text = (rating || "") + (rating && parts.length ? "：" : "") + parts.join(" · ");
    return { rating: rating, property: p, operating: o, text: text || null,
      school: (advice.school && advice.school.name) || null, asOfResearch: advice.asOfResearch || null };
  }
  /** 板块 → 权属（按行情样本中该板块多数个券的 right 字段）。 */
  function sectorRights(reits) {
    var cnt = {};
    (reits || []).forEach(function (r) {
      if (!r || !r.sector || !r.right) return;
      var c = cnt[r.sector] || (cnt[r.sector] = {});
      c[r.right] = (c[r.right] || 0) + 1;
    });
    var out = {};
    Object.keys(cnt).forEach(function (s) {
      out[s] = Object.keys(cnt[s]).sort(function (a, b) { return cnt[s][b] - cnt[s][a]; })[0];
    });
    return out;
  }
  var RANK = { "alloc-uw": 0, "alloc-n": 1, "alloc-ow-lite": 2, "alloc-ow": 3 };
  /** 与上期比较：只有 advice.previous 真实存在时才给出 ↑ / ↓ / —；否则 null（不伪造）。 */
  function changeOf(cur, prevAction) {
    if (prevAction == null) return null;
    var a = RANK[allocClass(cur)], b = RANK[allocClass(prevAction)];
    return a > b ? "↑" : a < b ? "↓" : "—";
  }
  /** 推荐表行：产权类 → 其下业态，经营权类 → 其下业态；有上期数据才带 prev / change。 */
  function recommendationRows(advice, rightsBySector) {
    if (!advice) return { rows: [], hasPrev: false };
    var prev = advice.previous || null;
    var prevRights = (prev && prev.rightsViews) || {};
    var prevSectors = {};
    ((prev && prev.sectorViews) || []).forEach(function (v) { prevSectors[v.sector] = v.action; });
    var hasPrev = !!(prev && (prev.sectorViews || prev.rightsViews));
    var rows = [];
    var groups = { "产权": [], "经营权": [], "其他": [] };
    (advice.sectorViews || []).forEach(function (v) {
      var r = (rightsBySector || {})[v.sector];
      (groups[r] || groups["其他"]).push(v);
    });
    ["产权", "经营权"].forEach(function (right) {
      var rv = (advice.rightsViews || {})[right];
      if (rv) {
        var pa = prevRights[right] ? prevRights[right].view : null;
        rows.push({ kind: "right", name: right + "类", action: rv.view, alloc: allocLabel(rv.view), reason: rv.view,
          prev: hasPrev && pa ? allocLabel(pa) : null, change: hasPrev ? changeOf(rv.view, pa) : null });
      }
      groups[right].forEach(function (v) {
        var pv = prevSectors[v.sector];
        rows.push({ kind: "sector", right: right, name: v.sector, action: v.action, alloc: allocLabel(v.action),
          confidence: v.confidence || null, reason: v.reason || "", ruling: v.schoolRuling || null,
          prev: hasPrev && pv ? allocLabel(pv) : null, change: hasPrev ? changeOf(v.action, pv) : null });
      });
    });
    groups["其他"].forEach(function (v) {
      rows.push({ kind: "sector", right: null, name: v.sector, action: v.action, alloc: allocLabel(v.action), confidence: v.confidence || null,
        reason: v.reason || "", ruling: v.schoolRuling || null, prev: null, change: null });
    });
    return { rows: rows, hasPrev: hasPrev };
  }
  function clamp01(x) { return Math.max(0, Math.min(1, x)); }
  function sgn(v, d) { return v == null || !isFinite(v) ? "—" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d == null ? 1 : d); }
  /** 风险红线：触发条件 + 当前值 + 距离（bp / pp）+ 进度（0–1，越大越接近）；缺数据的腿标 pending（前端显示「待接入」）。 */
  function redlines(cycle, advice) {
    var rc = (cycle && cycle.rateClock) || null, gate = (cycle && cycle.rateRentGate) || null, tsf = (cycle && cycle.tsfImpulse) || null;
    var spec = (advice && advice.rateRentGate) || {};
    var out = [];
    // 1. 利率轴转向上行（时钟利率轴，动态死区 + 5 日确认）
    if (rc && rc.status === "ok" && rc.d10y60bp != null) {
      var T = rc.thresholdBp, d = rc.d10y60bp;
      var allUp = rc.rateDistance && rc.rateDistance.all ? rc.rateDistance.all.up : null;
      var dist = rc.rateDir === "up" ? 0 : Math.max(0, allUp != null ? allUp : T - d);
      out.push({ id: "rate_up", title: "利率轴转向上行",
        trigger: "10Y 60 日变化 > +" + T + "bp（max(5bp, 0.7σ)），连续 5 个交易日确认",
        current: "当前 " + sgn(d) + "bp（" + (rc.rateDir === "down" ? "下行" : rc.rateDir === "up" ? "上行" : "走平") + "）",
        distance: rc.rateDir === "up" ? "已触发" : "距触发 " + dist.toFixed(1) + "bp",
        progress: clamp01((d + 2 * T) / (3 * T)), status: rc.rateDir === "up" ? "triggered" : dist <= 0.2 * T ? "near" : "far", pending: [] });
    } else {
      out.push({ id: "rate_up", title: "利率轴转向上行", trigger: "10Y 60 日变化 > +max(5bp, 0.7σ)，连续 5 日确认",
        current: "待接入", distance: null, progress: null, status: "pending", pending: ["10Y 真实序列"] });
    }
    // 2. 利率快过租金闸门（rateRentGate）
    var rl = gate && gate.rateLeg, sl = gate && gate.spreadLeg;
    var need = 25;
    var rateOk = rl && rl.status === "ok" && rl.d10y60bp != null;
    var pend = [];
    if (!sl || sl.status !== "ok") pend.push("产权利差分位腿（租金端）待接入");
    if (!rateOk) pend.push("利率腿待接入");
    out.push({ id: "rate_rent", title: spec.label || "利率快过租金闸门",
      trigger: spec.rule || (gate && gate.rule) || "Δ10Y(60交易日) ≥ +25bp 且 产权利差分位 60 日下降 ≥ 20pp",
      current: rateOk ? "利率腿 " + sgn(rl.d10y60bp) + "bp / 60 日" : "利率腿 待接入",
      distance: gate && gate.status === "triggered" ? "已触发" : rateOk ? "利率腿距触发 " + Math.max(0, need - rl.d10y60bp).toFixed(1) + "bp" : null,
      progress: rateOk ? clamp01(rl.d10y60bp / need) : null,
      status: gate && gate.status === "triggered" ? "triggered" : rateOk ? (need - rl.d10y60bp <= 5 ? "near" : "far") : "pending", pending: pend });
    // 3. 信用扩张：社融脉冲由负转正（领先 5–7 个月，约半年后类债资产承压）
    if (tsf && tsf.status === "ok" && tsf.value != null) {
      var v = tsf.value;
      out.push({ id: "tsf_turn", title: "信用扩张压制类债资产",
        trigger: "社融脉冲由负转正（领先 REITs 约 5–7 个月，只看方向）",
        current: "当前 " + sgn(v, 2) + "%（截至 " + (tsf.asOf || "—") + "）",
        distance: v > 0 ? "已为正值" : "距转正 " + Math.abs(v).toFixed(2) + "pp",
        progress: clamp01((v + 3) / 3), status: v > 0 ? "triggered" : Math.abs(v) <= 0.5 ? "near" : "far",
        pending: tsf.monthsBehind > 2 ? ["数据源滞后 " + tsf.monthsBehind + " 个月"] : [] });
    } else {
      out.push({ id: "tsf_turn", title: "信用扩张压制类债资产", trigger: "社融脉冲由负转正", current: "待接入",
        distance: null, progress: null, status: "pending", pending: ["社融 / 名义 GDP 序列"] });
    }
    // 4. 分派不达预期（逐券达成率未接入本页 → 待接入，不伪造）
    out.push({ id: "distribution", title: "分派不达预期",
      trigger: "个券分派达成率 < 95% 触发减持警戒；连续两期 < 90% 系统性减持",
      current: "待接入", distance: null, progress: null, status: "pending", pending: ["逐券分派达成率（季度披露）未接入本页"] });
    return out;
  }
  var API = { stress: stress, summarize: summarize, clockPriorRows: clockPriorRows, inZone: inZone, allocClass: allocClass, clockHeadline: clockHeadline,
    allocLabel: allocLabel, ratingShort: ratingShort, schoolStance: schoolStance, sectorRights: sectorRights, recommendationRows: recommendationRows, redlines: redlines };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  if (!root.document) return;
  root.ReitsAllocation = API;
  var doc = root.document;
  // 按实际导航高度设置章节偏移，适配窄屏换行与字体缩放。
  function updateAnchorOffset() {
    var header = doc.getElementById("topbar");
    doc.documentElement.style.setProperty("--sticky-offset", (header.getBoundingClientRect().height + doc.getElementById("subbar").getBoundingClientRect().height + 20) + "px");
  }
  updateAnchorOffset();
  if (root.ResizeObserver) new ResizeObserver(updateAnchorOffset).observe(doc.getElementById("topbar"));
  /** @param {string} id @returns {HTMLInputElement} */
  function input(id) { return /** @type {HTMLInputElement} */ (doc.getElementById(id)); }
  function updateStress() {
    var output = doc.getElementById("stressResult");
    try {
      var kind = input("stressKind").value;
      input("stressYears").disabled = kind === "property";
      var value = stress({ kind: kind, rate: Number(input("stressRate").value) / 100,
        shock: Number(input("stressShock").value) / 10000,
        cash: Number(input("stressCash").value) / 100, years: Number(input("stressYears").value) });
      if (!["stressRate", "stressShock", "stressCash", "stressYears"].every(function (id) { return input(id).value !== "" && input(id).checkValidity(); })) {
        throw new RangeError("请填写允许范围内的情景参数。");
      }
      output.textContent = (value > 0 ? "+" : "") + (value * 100).toFixed(2) + "%";
      output.className = "scenario-value " + (value < 0 ? "down" : value > 0 ? "up" : "flat");
      doc.getElementById("stressMethod").textContent = kind === "property" ?
        "简化产权模型：V = C / r；永续、零增长、无杠杆。实际产权估值仍需核查土地剩余年限、资本开支与退出价值。" :
        "简化经营权模型：V = Σ C / (1+r)ᵗ；等额年末现金流、到期残值为零、无杠杆。实际项目应逐期建模。";
    } catch (error) {
      output.textContent = error instanceof Error ? error.message : "情景计算失败，请检查参数。";
      output.className = "scenario-error";
    }
  }
  var form = doc.getElementById("stressForm");
  if (form) { form.addEventListener("input", updateStress); form.addEventListener("change", updateStress); form.addEventListener("submit", function (e) { e.preventDefault(); }); updateStress(); }
  var filter = doc.getElementById("sectorResearchFilter");
  function filterSectors() {
    var value = /** @type {HTMLSelectElement} */ (filter).value;
    doc.querySelectorAll("#advicePerf tbody tr").forEach(function (row) {
      row.hidden = value !== "all" && row.getAttribute("data-role") !== value;
    });
  }
  if (filter) { filter.addEventListener("input", filterSectors); filter.addEventListener("change", filterSectors); }
  // 时钟先验（advice.json 直读，不依赖研究数据包；当前象限取自核心 data.json 的 cycle.rateClock）
  function esc(v) { return String(v == null ? "" : v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
  function fetchAdvice() {
    var urls = ["advice.json", "https://xianhuixu.github.io/reits-dashboard/advice.json"];
    function at(i) {
      if (i >= urls.length) return Promise.reject(new Error("advice.json 不可用"));
      return fetch(urls[i]).then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.text();
      }).then(function (t) {
        t = (t || "").replace(/^\uFEFF/, "").trim();
        if (!t || t.charAt(0) === "<") throw new Error("HTML fallback");
        return JSON.parse(t);
      }).catch(function () { return at(i + 1); });
    }
    return at(0);
  }
  function renderClockPrior(advice, cycle) {
    var state = doc.getElementById("clockPriorState"), table = doc.getElementById("clockPriorTable"), gateEl = doc.getElementById("clockPriorGate");
    if (!state || !table) return;
    var clock = cycle && cycle.rateClock;
    var rows = clockPriorRows(advice, clock);
    if (root.ReitsDataStatus) root.ReitsDataStatus.apply(doc.getElementById("clockPriorPanel"), root.ReitsDataStatus.fromRateClock(clock));
    if (!rows.length) { state.textContent = "advice.json 暂无 clockSectorPrior。"; return; }
    var live = clock && clock.status === "ok";
    var trans = live && clock.state === "transitional";
    var gr = (clock && clock.growth) || {};
    var gNote = gr.critical ? "；增长<b>临界</b>（z3 " + esc(gr.z3) + "σ，" + esc((gr.distance || {}).label || "") + "）" : "";
    var headline = clockHeadline(clock);
    var distTxt = clock && clock.rateDistance ? "；" + esc(clock.rateDistance.label) : "";
    function pr(v) { return v == null ? "—" : v + "%"; }
    state.innerHTML = (headline ? headline + "<br>" : "") + (trans ?
      "当前状态：<b>" + esc(clock.stateLabel || "过渡期") + "</b> · 最近象限 " + esc((clock.leanQuadrant || "—") + " " + (clock.leanQuadrantName || clock.leanSubState || "")) +
        "（参考，Δ10Y " + esc((clock.d10y60bp > 0 ? "+" : "") + clock.d10y60bp) + "bp/60日" + distTxt + "；asOf " + esc(clock.asOf) + "，置信度 " + esc(clock.confidence || "低") + "）" + gNote +
        " · 美国先验（最近象限，仅参考）" + pr(clock.leanUsPriorAnnualReturn) + " · 过渡期不判硬冲突，命中项标「参考」" :
      live && clock.quadrant ?
      "当前象限：<b>" + esc(clock.quadrant + " " + (clock.subState || clock.quadrantName || "")) + "</b>（asOf " + esc(clock.asOf) + "，置信度 " + esc(clock.confidence || "—") + distTxt + "）" + gNote +
        " · 美国先验本象限整体年化总回报 " + pr(clock.usPriorAnnualReturn) + " · 橙色标记 = 学派超配但落在美国先验雷区" :
      "当前象限未判定（" + esc((clock && (clock.statusNote || clock.status)) || "行情核心数据未含 rateClock") + "），下表仅展示静态先验。");
    var LBL = { conflict: "冲突", watch: "复核", reference: "参考", "static": "待实证", ok: "—" };
    table.innerHTML = '<table class="matrix research-table"><thead><tr><th scope="col">中国板块</th><th scope="col">学派观点</th><th scope="col">美国类比（假设）</th><th scope="col">最佳象限</th><th scope="col">雷区</th><th scope="col">类比置信</th><th scope="col">冲突</th></tr></thead><tbody>' +
      rows.map(function (r) {
        var hl = r.status === "conflict" ? ' class="clock-conflict"' : r.status === "reference" ? ' class="clock-reference"' : "";
        var flagCls = { conflict: "flag-conflict", watch: "flag-watch", reference: "flag-reference" }[r.status];
        var mark = r.reference ? (r.inDanger ? " ◌最近象限雷区（参考）" : "") + (r.inBest ? " ☆最近象限最佳（参考）" : "") :
          (r.inDanger ? " ⚠️当前处雷区" : "") + (r.inBest ? " ★当前处最佳" : "");
        return "<tr" + hl + "><td><strong>" + esc(r.sector) + "</strong></td><td>" + (r.action === "—" ? "—" : '<span class="alloc-chip ' + allocClass(r.action) + '">' + esc(r.action) + "</span>") + "</td><td>" + esc(r.usAnalog) + '<span class="cell-note">' + esc(r.evidence) + "</span></td><td>" + esc(r.best) + "</td><td>" + esc(r.danger) + esc(mark) +
          "</td><td>" + esc(r.confidence) + "</td><td>" + (flagCls ? '<span class="flag-chip ' + flagCls + '">' + esc(LBL[r.status]) + "</span>" : "<b>" + esc(LBL[r.status]) + "</b>") + (r.flag ? '<span class="cell-note">' + esc(r.flag) + "</span>" : "") + "</td></tr>";
      }).join("") + "</tbody></table>";
    var spec = advice.rateRentGate || {}, g = cycle && cycle.rateRentGate;
    if (gateEl) {
      var st = g ? ({ triggered: "已触发", not_triggered: "未触发", "pending data": "待数据" }[g.status] || g.status) : "待数据";
      var legs = g ? "（利率腿：" + (g.rateLeg && g.rateLeg.status === "ok" ? (g.rateLeg.d10y60bp > 0 ? "+" : "") + g.rateLeg.d10y60bp + "bp/60日" + (g.rateLeg.met ? " 满足" : " 未满足") : "待数据") +
        "；产权利差分位腿：" + (g.spreadLeg && g.spreadLeg.status === "ok" ? g.spreadLeg.pctileChangePP + "pp" : "pending data") + "）" : "";
      var DS = root.ReitsDataStatus;
      var legBadge = DS ? DS.badgeHtml(g ? DS.fromGateLeg(g.spreadLeg, g.asOf) : DS.make(DS.PENDING, { note: "闸门未计算" }), true) : "";
      var eff = spec.effectsIfTriggered || {};
      gateEl.innerHTML = "<b>" + esc(spec.label || "升息快于租金闸门") + "</b>：" + esc(spec.rule || "") + " → 当前 <b>" + esc(st) + "</b>" + esc(legs) + legBadge +
        (g && g.status === "triggered" ? " · <b class=\"tone-risk\">已叠加：风险「" + esc(eff.risk) + "」升级为「" + esc(eff.escalateTo) + "」，估值闸门降为「" + esc(eff.downgradeTo) + "」</b>" :
          " · 触发后：风险「" + esc(eff.risk) + "」→「" + esc(eff.escalateTo) + "」，估值闸门 →「" + esc(eff.downgradeTo) + "」") + "。" + esc(spec.dataStatus || "");
    }
  }

  // ---------------- 配置页 ① 建议 / ② 理由 / ③ 红线（advice.json 直读 + data.json 核心行情；不依赖研究数据包） ----------------
  function svgEl(w, h, body, label) {
    return '<svg viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="none" role="presentation"><title>' + esc(label || "") + "</title>" + body + "</svg>";
  }
  function miniClockSvg(rc) {
    if (!rc || rc.status !== "ok") return '<p class="chart-placeholder">时钟未判定（待真实 10Y / PMI）</p>';
    var W = 240, H = 128, T = rc.thresholdBp || 5;
    var hist = (rc.history || []).slice(-12);
    var xs = hist.map(function (h) { return Math.abs(h.d10y60bp || 0); }).concat([Math.abs(rc.d10y60bp || 0), T * 2]);
    var xr = Math.max.apply(null, xs) * 1.15, yr = 1.5;
    function X(d) { return W / 2 + d / xr * (W / 2 - 6); }
    function Y(z) { return H / 2 - Math.max(-yr, Math.min(yr, z)) / yr * (H / 2 - 6); }
    var b = '<rect x="0" y="0" width="' + W + '" height="' + H + '" fill="none" stroke="var(--line2)"/>' +
      '<rect x="' + X(-T) + '" y="0" width="' + (X(T) - X(-T)) + '" height="' + H + '" fill="var(--tx3)" opacity=".08"/>' +
      '<rect x="0" y="' + Y(0.5) + '" width="' + W + '" height="' + (Y(-0.5) - Y(0.5)) + '" fill="var(--tx3)" opacity=".06"/>' +
      '<line x1="' + W / 2 + '" y1="0" x2="' + W / 2 + '" y2="' + H + '" stroke="var(--line2)"/><line x1="0" y1="' + H / 2 + '" x2="' + W + '" y2="' + H / 2 + '" stroke="var(--line2)"/>' +
      '<text x="4" y="12">Q2 复苏/泡沫</text><text x="' + (W - 4) + '" y="12" text-anchor="end">Q1 繁荣</text>' +
      '<text x="4" y="' + (H - 4) + '">Q3 衰退</text><text x="' + (W - 4) + '" y="' + (H - 4) + '" text-anchor="end">Q4 滞胀/复苏</text>';
    var pts = hist.filter(function (h) { return h.d10y60bp != null && h.z3 != null; }).map(function (h) { return X(h.d10y60bp).toFixed(1) + "," + Y(h.z3).toFixed(1); });
    if (pts.length > 1) b += '<polyline points="' + pts.join(" ") + '" fill="none" stroke="var(--tilt-neu)" stroke-width="1" stroke-dasharray="3 2"/>';
    var z3 = (rc.growth || {}).z3;
    if (z3 != null) b += '<circle cx="' + X(rc.d10y60bp).toFixed(1) + '" cy="' + Y(z3).toFixed(1) + '" r="5" fill="var(--tilt-pos)" stroke="var(--panel)" stroke-width="1.5"/>';
    return svgEl(W, H, b, "横轴 Δ10Y(60日)，纵轴 PMI 偏离 z3；虚线 = 近 12 个月轨迹，实心点 = 当前");
  }
  function lineSvg(seriesList, W, H) {
    var all = [];
    seriesList.forEach(function (s) { s.values.forEach(function (v) { if (v != null && isFinite(v)) all.push(v); }); });
    if (!all.length) return "";
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all), span = (hi - lo) || 1;
    var b = '<line x1="0" y1="' + (H - 1) + '" x2="' + W + '" y2="' + (H - 1) + '" stroke="var(--line2)"/>';
    seriesList.forEach(function (s) {
      var n = s.values.length;
      var pts = s.values.map(function (v, i) { return (i / Math.max(1, n - 1) * (W - 70)).toFixed(1) + "," + (H - 6 - (v - lo) / span * (H - 16)).toFixed(1); });
      var last = pts[pts.length - 1].split(",");
      b += '<polyline points="' + pts.join(" ") + '" fill="none" stroke="' + s.color + '" stroke-width="1.6"' + (s.dash ? ' stroke-dasharray="4 3"' : "") + "/>" +
        '<circle cx="' + last[0] + '" cy="' + last[1] + '" r="2.5" fill="' + s.color + '"/><text x="' + (+last[0] + 6) + '" y="' + (+last[1] + 3) + '">' + esc(s.label) + "</text>";
    });
    return svgEl(W, H, b, seriesList.map(function (s) { return s.label; }).join(" / "));
  }
  function betaSvg(bySector) {
    var rows = (bySector || []).filter(function (r) { return r.betaEq != null && r.betaBond != null; });
    if (!rows.length) return '<p class="chart-placeholder">Beta 待接入</p>';
    var W = 240, H = 128;
    var xs = rows.map(function (r) { return r.betaBond; }), ys = rows.map(function (r) { return r.betaEq; });
    var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs), y0 = Math.min.apply(null, ys), y1 = Math.max.apply(null, ys);
    function X(v) { return 10 + (v - x0) / ((x1 - x0) || 1) * (W - 60); }
    function Y(v) { return H - 12 - (v - y0) / ((y1 - y0) || 1) * (H - 26); }
    var col = { "偏股": "var(--tilt-pos)", "偏债": "var(--tilt-neg)", "中性": "var(--tilt-neu)" };
    var b = '<text x="' + (W - 2) + '" y="' + (H - 2) + '" text-anchor="end">债 Beta →</text><text x="2" y="9">↑ 股 Beta</text>';
    rows.forEach(function (r) {
      var cx = X(r.betaBond), cy = Y(r.betaEq), c = col[r.cls] || "var(--tx3)";
      b += (r.cls === "偏股" ? '<path d="M' + cx + " " + (cy - 5) + "l4.5 8h-9z" + '" fill="' + c + '"/>' : r.cls === "偏债" ? '<rect x="' + (cx - 3.5) + '" y="' + (cy - 3.5) + '" width="7" height="7" fill="' + c + '"/>' : '<circle cx="' + cx + '" cy="' + cy + '" r="3.5" fill="' + c + '"/>') +
        '<text x="' + (cx + 6) + '" y="' + (cy + 3) + '">' + esc(r.sector.slice(0, 4)) + "</text>";
    });
    return svgEl(W, H, b, "各业态周频股 Beta（纵）与债 Beta（横）；▲ 偏股 · ■ 偏债 · ● 中性");
  }
  function pct0(v) { return v == null ? "—" : Math.round(v * 100) + "%"; }
  function renderAdviceOverview(advice, data, panel) {
    var head = doc.getElementById("adviceHeadline");
    if (!head) return;
    var DS = root.ReitsDataStatus;
    var cycle = (data && data.cycle) || null, rc = cycle && cycle.rateClock;
    if (!advice) {
      head.textContent = "配置结论暂不可用（advice.json 加载失败）";
      doc.getElementById("advHeroSub").textContent = "研究正文（下方展开证据与各深度模块）不受影响。";
      doc.querySelector("#advRecTable tbody").innerHTML = '<tr><td colspan="3" class="note">advice.json 加载失败</td></tr>';
    } else {
      var st = schoolStance(advice);
      head.textContent = st.text || "—";
      var rec = recommendationRows(advice, sectorRights((data && data.reits) || []));
      doc.getElementById("advHeroSub").innerHTML = esc(st.school || "学派") + " · 研究日 " + esc(advice.asOfResearch || "—") + " · 行情日 " + esc((data && data.lastTradeDate) || advice.asOfMarket || "—") +
        (rec.hasPrev ? " · 对比上期 " + esc((advice.previous && advice.previous.asOf) || "") : ' · <span class="note">上期数据未接入：不显示「变化」列</span>');
      var th = '<tr><th scope="col">大类 / 业态</th><th scope="col">本期</th>' + (rec.hasPrev ? '<th scope="col">上期</th><th scope="col">变化</th>' : "") + '<th scope="col">一句话理由</th></tr>';
      doc.querySelector("#advRecTable thead").innerHTML = th;
      function chip(a) { return a ? '<span class="alloc-chip ' + a.cls + '">' + esc(a.label) + "</span>" : "—"; }
      doc.querySelector("#advRecTable tbody").innerHTML = rec.rows.map(function (r) {
        var orig = r.kind === "sector" && r.action && r.action !== r.alloc.label ? '<span class="adv-conf">' + esc(r.action) + "</span>" : "";
        var conf = r.confidence ? '<span class="adv-conf">置信 ' + esc(r.confidence) + "</span>" : "";
        return '<tr class="' + (r.kind === "right" ? "adv-right" : "adv-sector") + '"><td>' + esc(r.name) + "</td><td>" + chip(r.alloc) + orig + "</td>" +
          (rec.hasPrev ? "<td>" + chip(r.prev) + '</td><td class="num">' + esc(r.change || "—") + "</td>" : "") +
          '<td class="adv-reason-cell">' + esc(r.ruling ? r.reason + "；" + r.ruling : r.reason) + conf + "</td></tr>";
      }).join("");
      doc.getElementById("advRecNote").textContent = "学派一句话：" + (advice.headline || "—") + "（" + (advice.disclaimer ? "仅供研究展示，不构成投资建议" : "") + "）";
      // 红线
      var cards = redlines(cycle, advice);
      doc.getElementById("advRiskCards").innerHTML = cards.map(function (c) {
        var cls = c.status === "pending" ? " is-pending" : c.status === "near" || c.status === "triggered" ? " is-near" : "";
        var bar = c.progress == null ? "" : '<div class="ov-bar" aria-hidden="true"><i style="width:' + Math.round(c.progress * 100) + '%"></i></div>';
        var badge = c.status === "pending" && DS ? DS.badgeHtml(DS.make(DS.PENDING, { note: c.pending.join("；") }), true) : "";
        return '<article class="adv-risk' + cls + '"><h3>' + esc(c.title) + badge + '</h3><p class="ov-note">触发：' + esc(c.trigger) + "</p>" + bar +
          '<p class="adv-risk-dist">' + esc(c.current) + (c.distance ? " · <b>" + esc(c.distance) + "</b>" : "") + "</p>" +
          (c.pending.length ? '<p class="adv-risk-pending">' + c.pending.map(function (x) { return esc(/待接入|滞后/.test(x) ? x : x + " 待接入"); }).join("；") + "</p>" : "") + "</article>";
      }).join("");
      var LV = { "高": "risk-hi", "中": "risk-mid", "低": "risk-lo" };
      doc.getElementById("advRiskList").innerHTML = (advice.risks || []).map(function (r) {
        return '<li><span class="risk-lv ' + (LV[r.level] || "risk-lo") + '">' + esc(r.level) + "</span> <b>" + esc(r.title) + "</b>" + esc(r.detail) + "</li>";
      }).join("");
    }
    // ② 理由：时钟读数
    doc.getElementById("advMiniClock").innerHTML = miniClockSvg(rc);
    if (rc && rc.status === "ok") {
      var g = rc.growth || {}, cf = g.confirm || {};
      doc.getElementById("advReadClock").innerHTML = "<b>" + esc(rc.summary || "") + "</b>（" + esc((rc.quadrant ? rc.quadrant + " " : "") + (rc.quadrantName || "")) + "）<br>" +
        esc((rc.rateDistance || {}).label || "") + (cf.need ? "；" + esc((cf.title || "确认") + " " + cf.count + "/" + cf.need) : "");
    } else doc.getElementById("advReadClock").textContent = "时钟未判定，宏观背景层暂缺。";
    // 双利差（data_panel_l1l7 为 SEED → 示例数据角标）
    var P = panel || null, sEl = doc.getElementById("advMiniSpread");
    if (P && (P.propertyYieldSeries || []).length) {
      var ps = P.propertyYieldSeries.slice(-36), os = (P.operatingIrrSeries || []).slice(-36);
      sEl.innerHTML = lineSvg([{ label: "产权", values: ps.map(function (r) { return r.spread; }), color: "var(--tilt-pos)" },
        { label: "经营权", values: os.map(function (r) { return r.spread; }), color: "var(--tilt-neg)", dash: true }], 240, 128);
      var lp = ps[ps.length - 1], lo2 = os[os.length - 1];
      var term = P.operatingSpreadTermMatched && P.operatingSpreadTermMatched.status !== "ok" ? "；经营权期限匹配口径待接入" : "";
      doc.getElementById("advReadSpread").textContent = "产权利差 " + lp.spread.toFixed(2) + "%（历史 " + pct0(lp.pctile) + " 分位）" +
        (lo2 ? " · 经营权 " + lo2.spread.toFixed(2) + "%（" + pct0(lo2.pctile) + " 分位）" : "") + term;
    } else { sEl.innerHTML = '<p class="chart-placeholder">利差序列待接入</p>'; doc.getElementById("advReadSpread").textContent = "data_panel_l1l7.json 未加载。"; }
    if (DS) DS.apply(doc.getElementById("advReasonSpread"), DS.fromPanel(P));
    // 股 / 债 Beta：配置页不主动拉研究数据包（契约：配置页只直读 advice.json + 核心行情）。
    // 若用户已访问过研究页（研究包已合并进 REITS_DATA），进入视口时直接复用；否则给出跳转入口。
    var bEl = doc.getElementById("advReasonBeta");
    function loadBeta() {
      var B = root.REITS_DATA && root.REITS_DATA.correlation && root.REITS_DATA.correlation.betas;
      if (!B) {
        doc.getElementById("advMiniBeta").innerHTML = '<p class="chart-placeholder">Beta 图在研究页计算<br><button type="button" class="ov-link" data-ov-view="strategy" data-ov-anchor="betaScatter">查看 Beta 散点 →</button></p>';
        doc.getElementById("advReadBeta").textContent = "周频 Beta（对沪深300 / 10Y 国债）见研究分析 · 策略分类；访问过研究页后此处自动显示小图。";
        return false;
      }
      if (DS) DS.apply(bEl, DS.fromBetas(B));
      if (B.status !== "ok") { doc.getElementById("advMiniBeta").innerHTML = '<p class="chart-placeholder">Beta 待接入</p>'; doc.getElementById("advReadBeta").textContent = "周频 Beta 尚未计算。"; return true; }
      doc.getElementById("advMiniBeta").innerHTML = betaSvg(B.bySector);
      var by = { "偏债": [], "偏股": [] };
      B.bySector.forEach(function (r) { if (by[r.cls]) by[r.cls].push(r.sector); });
      doc.getElementById("advReadBeta").textContent = "偏债：" + (by["偏债"].join("、") || "—") + " · 偏股：" + (by["偏股"].join("、") || "—") + "（截面相对排序，截至 " + (B.asOf || "—") + "）";
      return true;
    }
    if (bEl && !bEl.dataset.bound) {
      bEl.dataset.bound = "1";
      if (root.IntersectionObserver) {
        // 每次进入视口都复查一次（研究包可能在此期间被研究页加载）
        var io = new root.IntersectionObserver(function (ents) {
          if (ents.some(function (e) { return e.isIntersecting; }) && loadBeta()) io.disconnect();
        }, { rootMargin: "120px" });
        io.observe(bEl);
      } else loadBeta();
    }
  }
  if (doc.getElementById("adviceHeadline")) {
    var advP = root.__ADVICE_READY || fetchAdvice().catch(function () { return null; });
    var dataP = root.__DATA_READY ? root.__DATA_READY.then(function () { return root.REITS_DATA || null; }, function () { return null; }) : Promise.resolve(null);
    var panelP = root.__PANEL_READY ? root.__PANEL_READY.then(function () { return root.REITS_DATA_PANEL || null; }, function () { return null; }) : Promise.resolve(null);
    Promise.all([advP, dataP, panelP]).then(function (res) { renderAdviceOverview(res[0], res[1], res[2]); })
      .catch(function (e) { if (root.console) root.console.error("[advice overview]", e && e.message); });
  }
  if (doc.getElementById("clockPriorPanel") && root.fetch) {
    var cyclePromise = root.__DATA_READY ? root.__DATA_READY.then(function () { return (root.REITS_DATA || {}).cycle || null; }, function () { return null; }) : Promise.resolve(null);
    (root.__ADVICE_READY ? root.__ADVICE_READY.then(function (a) { if (!a) throw new Error("advice.json 不可用"); return a; }) : fetchAdvice()).then(function (advice) {
      return cyclePromise.then(function (cycle) { renderClockPrior(advice, cycle); });
    }).catch(function (e) {
      var st = doc.getElementById("clockPriorState");
      if (st) st.textContent = "时钟先验暂不可用（advice.json 加载失败），板块研究正文不受影响。";
      if (root.console) root.console.warn("[clockPrior]", e && e.message);
    });
  }
  root.__DATA_READY.then(function () {
    var data = root.REITS_DATA || {};
    var rows = Array.isArray(data.reits) ? data.reits : [];
    doc.getElementById("allocationMarketDate").textContent = data.lastTradeDate || "未提供";
    doc.getElementById("allocationCoverage").textContent = rows.length + " 只";
    ["产权", "经营权"].forEach(function (right, i) {
      var s = summarize(rows, right);
      doc.getElementById("rightsSnapshot" + i).textContent = s.count + " 只 · 20日价格涨跌等权均值 " +
        (s.ret20 === null ? "暂无" : (s.ret20 > 0 ? "+" : "") + s.ret20.toFixed(2) + "%") +
        " · 有效样本 " + s.valid + "/" + s.count;
    });
    var date = data.lastTradeDate;
    var age = /^\d{4}-\d{2}-\d{2}$/.test(date || "") ? (Date.now() - Date.parse(date + "T15:00:00+08:00")) / 86400000 : Infinity;
    doc.getElementById("allocationFreshness").textContent = age > 7 ?
      "行情日期超过7个自然日或缺失，请核对更新状态；以下研究不构成实时评级。" :
      "行情按交易日更新；研究结论需结合最新公告复核。价格表现不等同于估值或含分红回报。";
  }).catch(function () {
    doc.getElementById("allocationFreshness").textContent = "行情暂不可用，研究正文仍可阅读；当前市场判断待数据恢复后复核。";
    // 核心行情加载失败时，独立开放静态研究，避免正文被默认页面隐藏。
    doc.querySelectorAll(".page").forEach(function (page) { page.hidden = page.id !== "pg-advice"; });
    doc.getElementById("topbar").dataset.cur = "advice";
    doc.getElementById("subbar").dataset.cur = "advice";
    doc.querySelectorAll("#tbNav button").forEach(function (button) {
      var active = button.getAttribute("data-pg") === "advice";
      button.classList.toggle("on", active);
      if (active) button.setAttribute("aria-current", "page"); else button.removeAttribute("aria-current");
      button.disabled = !active;
    });
    doc.querySelectorAll("#adviceSub button").forEach(function (button) {
      button.addEventListener("click", function () {
        var section = doc.getElementById(button.getAttribute("data-scroll"));
        if (section && root.ReitsWorkspace) root.ReitsWorkspace.selectAdviceForTarget(section);
        if (section) section.scrollIntoView();
        doc.querySelectorAll("#adviceSub button").forEach(function (other) {
          other.classList.toggle("on", other === button);
          if (other === button) other.setAttribute("aria-current", "page"); else other.removeAttribute("aria-current");
        });
      });
    });
  });
})(typeof window === "undefined" ? globalThis : window);
