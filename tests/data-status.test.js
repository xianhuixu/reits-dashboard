const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const DS = require("../data-status");
const { allocClass } = require("../allocation-tools");

const root = path.join(__dirname, "..");
const read = (f) => fs.readFileSync(path.join(root, f), "utf8");

test("status strings map to live / seed / pending / cached / lagged", () => {
  assert.equal(DS.fromStatus("ok").status, "live");
  assert.equal(DS.fromStatus("pending data").status, "pending");
  assert.equal(DS.fromStatus("unavailable").status, "pending");
  assert.equal(DS.fromStatus("待计算").status, "pending");
  assert.equal(DS.fromStatus("stale").status, "cached");
  assert.equal(DS.fromStatus("degraded").status, "cached");
  assert.equal(DS.fromStatus("seed").status, "seed");
  assert.equal(DS.fromStatus("lagged").status, "lagged");
  assert.equal(DS.fromStatus("滞后").status, "lagged");
  assert.equal(DS.fromStatus("weird-new-state").status, "pending");
  assert.equal(DS.fromStatus(null).status, "pending");
});

test("labels: 示例数据 / 待接入 / 缓存 · as-of X / 滞后 · 数据截至 MM-DD; live has no badge", () => {
  assert.equal(DS.label(DS.make("seed", { asOf: "2026-09-24" })), "示例数据");
  assert.equal(DS.label(DS.make("pending")), "待接入");
  assert.equal(DS.label(DS.make("cached", { asOf: "2026-09-29T09:47:32+08:00" })), "缓存 · as-of 2026-09-29");
  assert.equal(DS.label(DS.make("cached")), "缓存");
  assert.equal(DS.label(DS.lagged("2026-09-29")), "滞后 · 数据截至 09-29");
  assert.equal(DS.label(DS.make("live")), "");
  assert.equal(DS.badgeHtml(DS.make("live")), "");
  const html = DS.badgeHtml(DS.make("seed", { asOf: "2026-09-24", note: 'a<b>"c' }), true);
  assert.match(html, /class="ds-badge ds-seed ds-inline"/);
  assert.match(html, />示例数据</);
  assert.match(html, /as-of 2026-09-24/);
  assert.doesNotMatch(html, /<b>/);
});

test("propertySpread live → fromPropertySpread live; lagged never looks live; whole panel still seed for 经营权", () => {
  const panel = JSON.parse(read("data_panel_l1l7.json"));
  assert.equal(panel.propertySpread.status, "ok");
  assert.equal(DS.fromPropertySpread(panel).status, "live");
  assert.equal(DS.fromPropertySpread(panel).asOf, panel.propertySpread.asOf);
  const lag = JSON.parse(JSON.stringify(panel));
  lag.propertySpread.status = "lagged";
  lag.propertySpread.lagReason = "新浪取数失败";
  const L = DS.fromPropertySpread(lag);
  assert.equal(L.status, "lagged");
  assert.equal(DS.label(L), "滞后 · 数据截至 " + panel.propertySpread.asOf.slice(5));
  assert.equal(DS.fromPanel(panel).status, "seed"); // 经营权仍 SEED，整面板仍 seed
  assert.equal(DS.fromPanel(null).status, "pending");
  assert.equal(DS.fromPanel({ asOfTrade: "2026-10-01", source: "chinabond live", seedMeta: { liveFetch: true } }).status, "live");
});

test("rateRentGate spread leg live/lagged → matching badge; pending → 待接入", () => {
  const gate = JSON.parse(read("data.json")).cycle.rateRentGate;
  assert.equal(DS.fromGateLeg({ status: "pending data" }, "2026-09-29").status, "pending");
  assert.equal(DS.fromGateLeg({ status: "ok", to: "2026-09-29" }).status, "live");
  assert.equal(DS.fromGateLeg({ status: "lagged", to: "2026-09-29" }).status, "lagged");
  assert.equal(DS.fromGateLeg(undefined).status, "pending");
  assert.equal(gate.spreadLeg.status, "ok");
  assert.equal(DS.fromGateLeg(gate.spreadLeg, gate.asOf).status, "live");
  assert.ok(gate.rentLeg && gate.rentLeg.dominant === "distribution");
});

test("beta panel pending when not computed; rate clock cached when series from cache", () => {
  assert.equal(DS.fromBetas(null).status, "pending");
  assert.equal(DS.fromBetas({ status: "pending", reason: "x" }).status, "pending");
  assert.equal(DS.fromBetas({ status: "ok", asOf: "2026-09-26" }).status, "live");
  assert.equal(DS.fromRateClock({ status: "unavailable" }).status, "pending");
  assert.equal(DS.fromRateClock({ status: "ok", asOf: "2026-09-29", seriesOrigin: { y10: "live", pmi: "live" } }).status, "live");
  const c = DS.fromRateClock({ status: "ok", asOf: "2026-09-29", seriesOrigin: { y10: "cache", pmi: "live" } });
  assert.equal(c.status, "cached");
  assert.equal(DS.label(c), "缓存 · as-of 2026-09-29");
});

test("tenders stale or degraded → 缓存 · as-of 最新公告日", () => {
  const now = Date.parse("2026-09-30T12:00:00+08:00");
  const base = { status: "ok", checkedAt: "2026-09-30T09:47:32+08:00", latestBulletinDate: "2026-09-29" };
  assert.equal(DS.fromTenders(base, now).status, "live");
  const stale = DS.fromTenders(Object.assign({}, base, { checkedAt: "2026-09-28T09:47:32+08:00" }), now);
  assert.equal(DS.label(stale), "缓存 · as-of 2026-09-29");
  assert.equal(DS.fromTenders(Object.assign({}, base, { status: "degraded" }), now).status, "cached");
  assert.equal(DS.fromTenders(Object.assign({}, base, { checkedAt: "bad" }), now).status, "cached");
});

test("market index stale, fundamentals empty, worst-of aggregation", () => {
  assert.equal(DS.fromMarketIndex({ close: 948.47, stale: true }).status, "cached");
  assert.equal(DS.fromMarketIndex({ close: 948.47, stale: false }).status, "live");
  assert.equal(DS.fromMarketIndex(null).status, "pending");
  assert.equal(DS.fromFundamentals([{ achieveRate: null, distYield: null, metrics: { 出租率: null } }]).status, "pending");
  assert.equal(DS.fromFundamentals([{ achieveRate: 101.2 }]).status, "live");
  assert.equal(DS.fromFundamentals([]).status, "pending");
  assert.equal(DS.worst([DS.make("live"), DS.make("cached"), DS.make("seed")]).status, "seed");
  assert.equal(DS.worst([]).status, "live");
});

test("allocation palette classes are independent of price red/green", () => {
  assert.equal(allocClass("超配"), "alloc-ow");
  assert.equal(allocClass("长期超配"), "alloc-ow");
  assert.equal(allocClass("标配偏超配"), "alloc-ow-lite");
  assert.equal(allocClass("标配"), "alloc-n");
  assert.equal(allocClass("左侧分批布局"), "alloc-n");
  assert.equal(allocClass("观望/弱低配"), "alloc-uw");
  assert.equal(allocClass("战略弱低配"), "alloc-uw");
  const css = read("styles.css");
  ["--alloc-ow", "--alloc-n", "--alloc-uw", "--warn", "--risk", "--flag-conflict", "--flag-ref"].forEach((v) => {
    assert.equal((css.match(new RegExp(v + ":", "g")) || []).length >= 3, true, v + " defined for light / eye / dark");
  });
  assert.doesNotMatch(css, /\.alloc-[a-z-]+ \{[^}]*var\(--(up|down)\)/);
});

test("non-price modules no longer use --up / --down", () => {
  const alloc = read("allocation-tools.js");
  assert.doesNotMatch(alloc, /var\(--(up|down)\)/);
  const app = read("app.js");
  assert.doesNotMatch(app, /"#10b981"|"#ef4444"/, "category / quadrant palettes avoid green / red");
  assert.doesNotMatch(app, /var stageColor = RV\.score >= 3 \? "var\(--up\)"/);
  assert.match(app, /flagColor = \{ conflict: "var\(--flag-conflict\)"/);
});

test("pages load the status helper before app.js and dedupe 资产重估判断", () => {
  const html = read("index.html");
  const iDs = html.indexOf('src="data-status.js'), iApp = html.indexOf('src="app.js');
  assert.ok(iDs > 0 && iDs < iApp, "data-status.js before app.js");
  const full = html.match(/资产重估判断（/g) || [];
  assert.equal(full.length, 1, "full 资产重估判断 appears once (cycle page)");
  const cycle = html.slice(html.indexOf('id="v-cycle"'), html.indexOf('id="v-track"'));
  assert.match(cycle, /id="revalPanel"/);
  const signal = html.slice(html.indexOf('id="v-signal"'));
  assert.match(signal, /id="revalSignalSummary"/);
  assert.match(signal, /data-jump-view="cycle"/);
  assert.doesNotMatch(html, /id="revalSignalMap"/);
  assert.match(read("deploy_cf.sh"), /data-status\.js/);
});

// ---- 色盲友好色板（Machado 2009 severity 1.0，与 Chrome Emulation.setEmulatedVisionDeficiency 同矩阵） ----
const CVD = {
  normal: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
  protanopia: [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
  deuteranopia: [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.01182, 0.04294, 0.968881]],
  tritanopia: [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.3039]],
};
const lin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const hexRgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
function labOf(h, m) {
  const l = hexRgb(h).map(lin);
  const s = m.map((r) => Math.min(1, Math.max(0, r[0] * l[0] + r[1] * l[1] + r[2] * l[2])));
  const X = (0.4124 * s[0] + 0.3576 * s[1] + 0.1805 * s[2]) / 0.95047, Y = 0.2126 * s[0] + 0.7152 * s[1] + 0.0722 * s[2], Z = (0.0193 * s[0] + 0.1192 * s[1] + 0.9505 * s[2]) / 1.08883;
  const f = (t) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  return [116 * f(Y) - 16, 500 * (f(X) - f(Y)), 200 * (f(Y) - f(Z))];
}
const dE76 = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
function themeVars(css, selector) {
  const i = css.lastIndexOf(selector + " {\n  /*") >= 0 ? css.lastIndexOf(selector + " {\n  /*") : css.lastIndexOf(selector + " {\n  --alloc-ow");
  const block = css.slice(i, css.indexOf("}", i));
  const out = {};
  block.replace(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g, (_, k, v) => { out[k] = v; });
  return out;
}

test("allocation ramp is one cool hue, warm colours only for warn / risk, risk distinct under CVD", () => {
  const css = read("styles.css");
  const up = { ":root": "#c13f4a", '[data-theme="eye"]': "#b83445", '[data-theme="dark"]': "#ff929b" };
  for (const sel of [":root", '[data-theme="eye"]', '[data-theme="dark"]']) {
    const v = themeVars(css, sel);
    ["alloc-ow", "alloc-n", "alloc-uw", "warn", "risk"].forEach((k) => assert.ok(v[k], sel + " " + k));
    for (const k of ["alloc-ow", "alloc-n", "alloc-uw"]) {
      const [L, a, b] = labOf(v[k], CVD.normal);
      const hue = (Math.atan2(b, a) * 180 / Math.PI + 360) % 360;
      assert.ok(hue > 230 && hue < 300, `${sel} ${k} should be cool blue (hue ${hue.toFixed(0)})`);
      assert.ok(L >= 0);
    }
    for (const [name, m] of Object.entries(CVD)) {
      const d = (x, y) => dE76(labOf(x, m), labOf(y, m));
      assert.ok(d(v["alloc-uw"], v.warn) > 30, `${sel} ${name}: 低配 vs 预警`);
      assert.ok(d(v["alloc-ow"], v.risk) > 10, `${sel} ${name}: 超配 vs 风险`);
      assert.ok(d(v.risk, up[sel]) > 10, `${sel} ${name}: 风险 vs 上涨红`);
    }
  }
  assert.match(css, /\.alloc-ow::before[^{]*\{ content: "↑"/);
  assert.match(css, /\.alloc-n::before \{ content: "→"/);
  assert.match(css, /\.alloc-uw::before[^{]*\{ content: "↓"/);
  assert.match(css, /\.tone-risk::before \{ content: "⚠ "/);
});
