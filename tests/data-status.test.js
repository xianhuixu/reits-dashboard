const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const DS = require("../data-status");
const { allocClass } = require("../allocation-tools");

const root = path.join(__dirname, "..");
const read = (f) => fs.readFileSync(path.join(root, f), "utf8");

test("status strings map to live / seed / pending / cached", () => {
  assert.equal(DS.fromStatus("ok").status, "live");
  assert.equal(DS.fromStatus("pending data").status, "pending");
  assert.equal(DS.fromStatus("unavailable").status, "pending");
  assert.equal(DS.fromStatus("待计算").status, "pending");
  assert.equal(DS.fromStatus("stale").status, "cached");
  assert.equal(DS.fromStatus("degraded").status, "cached");
  assert.equal(DS.fromStatus("seed").status, "seed");
  // 未知或缺失状态不冒充 live
  assert.equal(DS.fromStatus("weird-new-state").status, "pending");
  assert.equal(DS.fromStatus(null).status, "pending");
});

test("labels: 示例数据 / 待接入 / 缓存 · as-of X; live has no badge", () => {
  assert.equal(DS.label(DS.make("seed", { asOf: "2026-09-24" })), "示例数据");
  assert.equal(DS.label(DS.make("pending")), "待接入");
  assert.equal(DS.label(DS.make("cached", { asOf: "2026-09-29T09:47:32+08:00" })), "缓存 · as-of 2026-09-29");
  assert.equal(DS.label(DS.make("cached")), "缓存");
  assert.equal(DS.label(DS.make("live")), "");
  assert.equal(DS.badgeHtml(DS.make("live")), "");
  const html = DS.badgeHtml(DS.make("seed", { asOf: "2026-09-24", note: 'a<b>"c' }), true);
  assert.match(html, /class="ds-badge ds-seed ds-inline"/);
  assert.match(html, />示例数据</);
  assert.match(html, /as-of 2026-09-24/);
  assert.doesNotMatch(html, /<b>/);
});

test("committed L2 panel is seed (as-of 2026-09-24); live panel is not badged", () => {
  const panel = JSON.parse(read("data_panel_l1l7.json"));
  const s = DS.fromPanel(panel);
  assert.equal(s.status, "seed");
  assert.equal(s.asOf, panel.asOfTrade);
  assert.equal(DS.fromPanel(null).status, "pending");
  assert.equal(DS.fromPanel({ asOfTrade: "2026-10-01", source: "chinabond live", seedMeta: { liveFetch: true } }).status, "live");
});

test("rateRentGate spread leg pending → 待接入; rate leg ok → live", () => {
  const gate = JSON.parse(read("data.json")).cycle.rateRentGate;
  assert.equal(DS.fromGateLeg({ status: "pending data" }, "2026-09-29").status, "pending");
  assert.equal(DS.fromGateLeg({ status: "ok", to: "2026-09-29" }).status, "live");
  assert.equal(DS.fromGateLeg(undefined).status, "pending");
  if (gate && gate.spreadLeg && gate.spreadLeg.status !== "ok") assert.equal(DS.fromGateLeg(gate.spreadLeg, gate.asOf).status, "pending");
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
