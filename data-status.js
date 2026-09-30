/* 全站数据状态标注：把 JSON 里既有的 status / as-of / seed 字段统一映射为
 *   live（实时，不加标）· seed（示例数据）· pending（待接入）· cached（缓存 · as-of X）
 * 纯函数可在 node 下测试；浏览器端挂在 window.ReitsDataStatus。只读数据，不改数据。 */
(function (root) {
  "use strict";
  var LIVE = "live", SEED = "seed", PENDING = "pending", CACHED = "cached";
  var LABEL = { seed: "示例数据", pending: "待接入", cached: "缓存" };
  var STATUS_MAP = {
    ok: LIVE, live: LIVE, fresh: LIVE, triggered: LIVE, not_triggered: LIVE,
    seed: SEED, placeholder: SEED, sample: SEED, demo: SEED, example: SEED,
    pending: PENDING, "pending data": PENDING, pending_data: PENDING, unavailable: PENDING, missing: PENDING,
    "待计算": PENDING, "待数据": PENDING, "待接入": PENDING, na: PENDING, "n/a": PENDING, none: PENDING,
    cached: CACHED, cache: CACHED, stale: CACHED, degraded: CACHED, failed: CACHED, fallback: CACHED
  };
  /** 规范化 as-of：ISO 时间取日期部分，空值返回 null。 */
  function normAsOf(v) {
    if (v == null || v === "") return null;
    var s = String(v).trim();
    var m = /^(\d{4}-\d{2}-\d{2})/.exec(s);
    return m ? m[1] : s;
  }
  /** @param {string} status @param {{asOf?:any,note?:string,source?:string}} [extra] */
  function make(status, extra) {
    extra = extra || {};
    return { status: status, asOf: normAsOf(extra.asOf), note: extra.note || "", source: extra.source || "", display: extra.display || "" };
  }
  /** 任意 status 字符串 → 四态之一；未知状态视为 pending（宁可标注，不冒充 live）。 */
  function fromStatus(status, asOf, note) {
    if (status == null || status === "") return make(PENDING, { asOf: asOf, note: note || "状态缺失" });
    var key = String(status).trim().toLowerCase();
    var st = Object.prototype.hasOwnProperty.call(STATUS_MAP, key) ? STATUS_MAP[key] : PENDING;
    return make(st, { asOf: asOf, note: note });
  }
  /** data_panel_l1l7.json：seedMeta.liveFetch === false 或 source 含 seed → 示例数据。 */
  function fromPanel(P) {
    if (!P) return make(PENDING, { note: "data_panel_l1l7.json 未加载" });
    var seedFlag = (P.seedMeta && P.seedMeta.liveFetch === false) || /\bseed\b/i.test(String(P.source || "")) || /SEED ONLY/i.test(String(P.note || ""));
    if (seedFlag) return make(SEED, { asOf: P.asOfTrade, note: "PPT seed 插值序列，非 live", source: P.source });
    if (P.status) return fromStatus(P.status, P.asOfTrade);
    return make(LIVE, { asOf: P.asOfTrade });
  }
  /** correlation.betas：status !== ok → 待接入。 */
  function fromBetas(B) {
    if (!B) return make(PENDING, { note: "研究数据包尚无 correlation.betas" });
    return B.status === "ok" ? make(LIVE, { asOf: B.asOf }) : fromStatus(B.status || "pending", B.asOf, B.reason);
  }
  /** cycle.rateClock：status 非 ok → 待接入；任一序列 seriesOrigin=cache → 缓存。 */
  function fromRateClock(RC) {
    if (!RC) return make(PENDING, { note: "cycle_judgment.json 尚无 rateClock" });
    if (RC.status !== "ok") return fromStatus(RC.status, RC.asOf, RC.statusNote);
    var o = RC.seriesOrigin || {};
    var cached = Object.keys(o).some(function (k) { return o[k] === "cache"; });
    return cached ? make(CACHED, { asOf: RC.asOf, note: "本次取数失败，沿用缓存序列" }) : make(LIVE, { asOf: RC.asOf });
  }
  /** cycle.rateRentGate 的产权利差分位腿（spreadLeg）：pending data → 待接入。 */
  function fromGateLeg(leg, asOf) {
    if (!leg) return make(PENDING, { asOf: asOf, note: "闸门腿未计算" });
    return leg.status === "ok" ? make(LIVE, { asOf: leg.to || asOf }) : fromStatus(leg.status, asOf, leg.note);
  }
  /** cycle.tsfImpulse（社融脉冲）：pending → 待接入；取数走缓存或源滞后 >2 个月 → 「缓存 · 数据截至 X月」。 */
  function fromTsfImpulse(T) {
    if (!T || T.status !== "ok") return make(PENDING, { note: (T && T.reason) || "社融 / 名义 GDP 真实序列未接入" });
    var o = T.seriesOrigin || {};
    var cached = Object.keys(o).some(function (k) { return o[k] === "cache"; });
    var disp = "数据截至 " + (T.asOf ? parseInt(String(T.asOf).slice(5, 7), 10) + "月" : "—");
    if (cached || (T.monthsBehind != null && T.monthsBehind > 2)) {
      return make(CACHED, { asOf: T.asOf, display: disp, note: cached ? "本次取数失败，沿用缓存序列" : (T.staleNote || "数据源更新滞后") });
    }
    return make(LIVE, { asOf: T.asOf });
  }
  /** 中证 REITs 指数：stale=true → 缓存（as-of 取数据自带日期，缺失时仅显示「缓存」）。 */
  function fromMarketIndex(mi) {
    if (!mi || mi.close == null) return make(PENDING, { note: "指数行情待接入" });
    if (mi.stale) return make(CACHED, { asOf: mi.asOf || mi.date || mi.tradeDate, note: mi.staleNote || "实时获取失败，显示最近一次成功数据" });
    return make(LIVE, { asOf: mi.asOf || mi.date });
  }
  /** tenders.json：status 非 ok 或核查超过 maxAgeHours → 缓存 · as-of 最新公告日。 */
  function fromTenders(T, nowMs, maxAgeHours) {
    if (!T) return make(PENDING, { note: "招投标数据未加载" });
    var limit = (maxAgeHours == null ? 30 : maxAgeHours) * 3600000;
    var age = (nowMs == null ? Date.now() : nowMs) - Date.parse(T.checkedAt);
    var asOf = T.latestBulletinDate || T.lastSuccessAt || T.checkedAt;
    if (T.status !== "ok") return make(CACHED, { asOf: asOf, note: "主源未完整取得（" + (T.status || "未知") + "）" });
    if (!Number.isFinite(age) || age > limit) return make(CACHED, { asOf: asOf, note: "核查超过 " + (limit / 3600000) + " 小时" });
    return make(LIVE, { asOf: asOf });
  }
  /** fundamentals：无条目或全部数值为空 → 待接入。 */
  function fromFundamentals(list) {
    var rows = Array.isArray(list) ? list : [];
    var has = rows.some(function (f) {
      if (!f) return false;
      if (f.achieveRate != null || f.distYield != null) return true;
      var m = f.metrics || {};
      return Object.keys(m).some(function (k) { return m[k] != null; });
    });
    return has ? make(LIVE) : make(PENDING, { note: "fundamentals.json 运营数据待季度维护" });
  }
  function isLive(s) { return !s || s.status === LIVE; }
  /** 角标文字：示例数据 / 待接入 / 缓存 · as-of X；live 返回空串。 */
  function label(s) {
    if (isLive(s)) return "";
    if (s.status === CACHED) return LABEL.cached + (s.display ? " · " + s.display : s.asOf ? " · as-of " + s.asOf : "");
    return LABEL[s.status] || LABEL.pending;
  }
  function title(s) {
    if (isLive(s)) return "";
    var parts = [label(s)];
    if (s.status !== CACHED && s.asOf) parts.push("as-of " + s.asOf);
    if (s.note) parts.push(s.note);
    return parts.join(" · ");
  }
  function esc(v) { return String(v == null ? "" : v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
  /** 行内角标 HTML（用于表格/段落内）；live 返回空串。 */
  function badgeHtml(s, inline) {
    if (isLive(s)) return "";
    return '<span class="ds-badge ds-' + s.status + (inline ? " ds-inline" : "") + '" title="' + esc(title(s)) + '">' + esc(label(s)) + "</span>";
  }
  /** 汇总多个状态：任一非 live 即取最「弱」者（pending > seed > cached）。 */
  function worst(list) {
    var rank = { live: 0, cached: 1, seed: 2, pending: 3 };
    return (list || []).filter(Boolean).reduce(function (acc, s) { return rank[s.status] > rank[acc.status] ? s : acc; }, make(LIVE));
  }
  var api = { LIVE: LIVE, SEED: SEED, PENDING: PENDING, CACHED: CACHED, make: make, fromStatus: fromStatus, fromPanel: fromPanel,
    fromBetas: fromBetas, fromRateClock: fromRateClock, fromGateLeg: fromGateLeg, fromMarketIndex: fromMarketIndex,
    fromTenders: fromTenders, fromTsfImpulse: fromTsfImpulse, fromFundamentals: fromFundamentals, label: label, title: title, badgeHtml: badgeHtml,
    isLive: isLive, worst: worst, normAsOf: normAsOf };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (!root.document) return;
  /** 模块角标：在卡片右上角放置/更新/移除 .ds-badge，并以 data-ds 驱动灰化样式。 */
  api.apply = function (el, s) {
    if (typeof el === "string") el = root.document.getElementById(el);
    if (!el) return;
    var old = el.querySelector(":scope > .ds-badge.ds-corner");
    if (isLive(s)) {
      el.removeAttribute("data-ds");
      if (old) old.remove();
      return;
    }
    el.setAttribute("data-ds", s.status);
    var b = old || root.document.createElement("span");
    b.className = "ds-badge ds-corner ds-" + s.status;
    b.textContent = label(s);
    b.title = title(s);
    b.setAttribute("role", "note");
    if (!old) el.insertBefore(b, el.firstChild);
  };
  /** HTML 里以 data-ds-status / data-ds-asof 声明的静态模块（如纯假设示例）。 */
  api.applyDeclared = function (scope) {
    (scope || root.document).querySelectorAll("[data-ds-status]").forEach(function (el) {
      api.apply(el, fromStatus(el.getAttribute("data-ds-status"), el.getAttribute("data-ds-asof"), el.getAttribute("data-ds-note")));
    });
  };
  root.ReitsDataStatus = api;
  if (root.document.readyState === "loading") root.document.addEventListener("DOMContentLoaded", function () { api.applyDeclared(); });
  else api.applyDeclared();
})(typeof window === "undefined" ? globalThis : window);
