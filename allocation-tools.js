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
   * @param {any} advice @param {any} clock @returns {Array<any>} */
  function clockPriorRows(advice, clock) {
    var views = {};
    ((advice && advice.sectorViews) || []).forEach(function (v) { views[v.sector] = v; });
    var ok = clock && clock.status === "ok" && clock.quadrant;
    var q = ok ? clock.quadrant : null, sub = ok ? clock.subState : null;
    return ((advice && advice.clockSectorPrior) || []).map(function (p) {
      var action = (views[p.sector] || {}).action || "—";
      var over = /超配/.test(action) && !/低配/.test(action);
      var under = /低配|观望|谨慎/.test(action);
      var inDanger = inZone(p.danger, q, sub), inBest = inZone(p.best, q, sub);
      var status = over && inDanger ? "conflict" : under && inBest ? "watch" : p.conflictFlag ? "static" : "ok";
      return { sector: p.sector, action: action, usAnalog: p.usAnalog, best: zoneLabel(p.best), danger: zoneLabel(p.danger),
        confidence: p.analogConfidence, inDanger: inDanger, inBest: inBest, status: status,
        flag: p.conflictFlag || "", evidence: p.chinaEvidence || "" };
    });
  }
  if (typeof module !== "undefined" && module.exports) module.exports = { stress: stress, summarize: summarize, clockPriorRows: clockPriorRows, inZone: inZone };
  if (!root.document) return;
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
    if (!rows.length) { state.textContent = "advice.json 暂无 clockSectorPrior。"; return; }
    var ok = clock && clock.status === "ok" && clock.quadrant;
    state.innerHTML = ok ?
      "当前象限：<b>" + esc(clock.quadrant + " " + (clock.subState || clock.quadrantName || "")) + "</b>（asOf " + esc(clock.asOf) + "，置信度 " + esc(clock.confidence || "—") +
        (clock.deadBand ? "，10Y 60日变化在 ±10bp 死区内，按符号倾向判定" : "") + "）· 美国先验本象限整体年化总回报 " +
        (clock.usPriorAnnualReturn == null ? "—" : clock.usPriorAnnualReturn + "%") + " · 标黄 = 学派超配但落在美国先验雷区" :
      "当前象限未判定（" + esc((clock && (clock.statusNote || clock.status)) || "行情核心数据未含 rateClock") + "），下表仅展示静态先验。";
    var LBL = { conflict: "冲突", watch: "复核", "static": "待实证", ok: "—" };
    table.innerHTML = '<table class="matrix research-table"><thead><tr><th scope="col">中国板块</th><th scope="col">学派观点</th><th scope="col">美国类比（假设）</th><th scope="col">最佳象限</th><th scope="col">雷区</th><th scope="col">类比置信</th><th scope="col">冲突</th></tr></thead><tbody>' +
      rows.map(function (r) {
        var hl = r.status === "conflict" ? ' class="clock-conflict" style="background:rgba(212,160,23,.16)"' : "";
        var mark = (r.inDanger ? " ⚠️当前处雷区" : "") + (r.inBest ? " ★当前处最佳" : "");
        return "<tr" + hl + "><td><strong>" + esc(r.sector) + "</strong></td><td>" + esc(r.action) + "</td><td>" + esc(r.usAnalog) + '<span class="cell-note">' + esc(r.evidence) + "</span></td><td>" + esc(r.best) + "</td><td>" + esc(r.danger) + esc(mark) +
          "</td><td>" + esc(r.confidence) + "</td><td><b>" + esc(LBL[r.status]) + "</b>" + (r.flag ? '<span class="cell-note">' + esc(r.flag) + "</span>" : "") + "</td></tr>";
      }).join("") + "</tbody></table>";
    var spec = advice.rateRentGate || {}, g = cycle && cycle.rateRentGate;
    if (gateEl) {
      var st = g ? ({ triggered: "已触发", not_triggered: "未触发", "pending data": "待数据" }[g.status] || g.status) : "待数据";
      var legs = g ? "（利率腿：" + (g.rateLeg && g.rateLeg.status === "ok" ? (g.rateLeg.d10y60bp > 0 ? "+" : "") + g.rateLeg.d10y60bp + "bp/60日" + (g.rateLeg.met ? " 满足" : " 未满足") : "待数据") +
        "；产权利差分位腿：" + (g.spreadLeg && g.spreadLeg.status === "ok" ? g.spreadLeg.pctileChangePP + "pp" : "pending data") + "）" : "";
      var eff = spec.effectsIfTriggered || {};
      gateEl.innerHTML = "<b>" + esc(spec.label || "升息快于租金闸门") + "</b>：" + esc(spec.rule || "") + " → 当前 <b>" + esc(st) + "</b>" + esc(legs) +
        (g && g.status === "triggered" ? " · <b style=\"color:var(--up)\">已叠加：风险「" + esc(eff.risk) + "」升级为「" + esc(eff.escalateTo) + "」，估值闸门降为「" + esc(eff.downgradeTo) + "」</b>" :
          " · 触发后：风险「" + esc(eff.risk) + "」→「" + esc(eff.escalateTo) + "」，估值闸门 →「" + esc(eff.downgradeTo) + "」") + "。" + esc(spec.dataStatus || "");
    }
  }
  if (doc.getElementById("clockPriorPanel") && root.fetch) {
    var cyclePromise = root.__DATA_READY ? root.__DATA_READY.then(function () { return (root.REITS_DATA || {}).cycle || null; }, function () { return null; }) : Promise.resolve(null);
    fetchAdvice().then(function (advice) {
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
