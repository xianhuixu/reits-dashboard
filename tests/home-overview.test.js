// 市场总览 / 配置页重排（设计师线框 2026-09-30）：首屏派生纯函数 + 形状区分样式契约
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const H = require("../workspace.js");
const A = require("../allocation-tools.js");
const read = (f) => fs.readFileSync(path.join(__dirname, "..", f), "utf8");

const baseRc = () => ({
  status: "ok", state: "definite", quadrant: "Q2", quadrantName: "复苏/泡沫", rateDir: "down", d10y60bp: -7.4, thresholdBp: 5, thresholdFloored: true,
  confidence: "中低", rateDistance: { critical: false },
  growth: { state: 1, z3: 0.26, critical: true, distance: { sigma: 0.01 }, confirm: { title: "退回中性确认", count: 0, need: 2, label: "需连续 2 个月低于 0.25σ，最早 11 月数据可能改变读数" } },
  signalSwitch: { active: true, cause: "methodology", note: "口径更新", from: "过渡期", to: "Q2" },
});

test("banner keeps confidence out and marks the critical axis", () => {
  const b = H.clockBanner(baseRc());
  assert.equal(b.growth, "增长高于趋势");
  assert.equal(b.rate, "利率下行");
  assert.equal(b.criticalAxis, "growth");
  assert.equal(b.switchTag, true);
  assert.doesNotMatch(JSON.stringify(b), /置信度|中低/);
  assert.equal(H.clockBanner({ status: "pending" }).ok, false);
});

test("clock card shows 2-dot confirmation, grey confidence and threshold line", () => {
  const c = H.clockCard(baseRc());
  assert.equal(c.big, "利率下行");
  assert.equal(c.rateLine, "10Y 60日 −7.4bp，阈值 5.0bp（下限）");
  assert.equal(c.growthDist, "距退出线 0.01σ");
  assert.deepEqual([c.confirm.count, c.confirm.need], [0, 2]);
  assert.equal(c.confirm.title, "退回中性确认");
  assert.match(c.confirm.label, /最早 11 月/);
  assert.equal(c.confidence, "中低");
  assert.equal(c.cells.filter((x) => x.on).map((x) => x.q).join(), "Q2");
});

test("live data: banner, cards and points derive from the committed data files", () => {
  const D = JSON.parse(read("data.json"));
  const P = JSON.parse(read("data_panel_l1l7.json"));
  const rc = D.cycle.rateClock;
  assert.equal(rc.growth.confirm.need, 2);
  const sp = H.spreadCard(P);
  assert.ok(sp.ok && sp.pctile >= 0 && sp.pctile <= 100);
  const m = H.marketCard(D);
  assert.equal(m.up + m.down + m.flat, D.reits.filter((r) => Number.isFinite(r.pct)).length);
  const t = H.tsfCard(D.cycle.tsfImpulse);
  if (D.cycle.tsfImpulse.status === "ok") assert.ok(t.ok && t.asOf);
  const pts = H.todayPoints(D);
  assert.ok(pts.length >= 1 && pts.length <= 3);
});

test("market card falls back to equal weight when the index is missing", () => {
  const m = H.marketCard({ reits: [{ pct: 1, amount: 1e8 }, { pct: -0.5, amount: 5e7 }, { pct: 0 }] });
  assert.equal(m.source, "equal");
  assert.equal(m.pct, 0.5 / 3);
  assert.deepEqual([m.up, m.down, m.flat], [1, 1, 1]);
  assert.equal(H.fmtAmount(m.amount), "1.50 亿");
});

test("tsf card reads a positive-to-negative flip as a lead signal", () => {
  const t = H.tsfCard({ status: "ok", value: -0.81, prev: 0.43, asOf: "2026-04", lastFlip: { direction: "正转负" } });
  assert.equal(t.arrow, "↓");
  assert.match(t.read, /由正转负/);
  assert.equal(H.tsfCard({ status: "pending" }).ok, false);
});

test("spread card compares with three observations earlier", () => {
  const s = H.spreadCard({ propertyYieldSeries: [{ pctile: 0.9 }, { pctile: 0.95 }, { pctile: 0.96 }, { pctile: 0.97, spread: 3, date: "2026-09-15" }] });
  assert.equal(s.pctile, 97);
  assert.equal(s.delta, 7);
  assert.equal(s.arrow, "↑");
});

test("stamps and signed numbers use the dashboard formats", () => {
  assert.equal(H.shortStamp("2026-09-30 11:50:33"), "09-30 11:50");
  assert.equal(H.sgnNum(-7.4), "−7.4");
  assert.equal(H.sgnNum(0.12, 2), "+0.12");
});

test("advice: stance, recommendation rows and red lines", () => {
  const adv = JSON.parse(read("advice.json"));
  const D = JSON.parse(read("data.json"));
  const st = A.schoolStance(adv);
  assert.match(st.text, /产权.+ · 经营权/);
  const rec = A.recommendationRows(adv, A.sectorRights(D.reits));
  assert.equal(rec.hasPrev, !!adv.previous);
  assert.ok(rec.rows.some((r) => r.kind === "right") && rec.rows.some((r) => r.kind === "sector"));
  if (!rec.hasPrev) rec.rows.forEach((r) => assert.equal(r.change, null));
  const rl = A.redlines(D.cycle, adv);
  assert.deepEqual(rl.map((r) => r.id), ["rate_up", "rate_rent", "tsf_turn", "distribution"]);
  assert.equal(rl[3].status, "pending");
  rl.filter((r) => r.progress != null).forEach((r) => assert.ok(r.progress >= 0 && r.progress <= 1));
});

test("home first screen is chart-free and ECharts loads lazily", () => {
  const html = read("index.html");
  const hero = html.slice(html.indexOf('id="v-heatmap"'), html.indexOf('id="ovEvidence"'));
  assert.match(hero, /id="ovHero"/);
  ["ovCardClock", "ovCardSpread", "ovCardMarket", "ovCardTsf"].forEach((id) => assert.match(hero, new RegExp(`id="${id}"`)));
  assert.doesNotMatch(hero, /treemap|echarts|<canvas/);
  assert.doesNotMatch(html, /<script[^>]+echarts-custom\.min\.js/);
  assert.match(html, /__loadECharts/);
  assert.equal((html.match(/id="adviceSub"/g) || []).length, 1, "adviceSub id must stay unique");
  assert.match(read("app.js"), /withECharts\(renderTreemap\)/);
});

test("shape-based colour: prices carry ▲▼ without fills, warnings are outlined with ⚠", () => {
  const css = read("styles.css");
  assert.match(css, /\.up::before \{ content: "▲/);
  assert.match(css, /\.down::before \{ content: "▼/);
  assert.match(css, /\.rc-tag-warn \{[^}]*background: transparent;[^}]*border: 1px solid/);
  assert.match(css, /\.rc-tag-warn::before \{ content: "⚠/);
  // 价格涨跌不再用底色块
  assert.doesNotMatch(css, /\.(up-b|down-b)\s*\{[^}]*background:\s*var\(--(up|down)/);
  assert.doesNotMatch(css, /^=======$/m, "no merge-conflict markers");
  const ws = read("workspace.css");
  assert.match(ws, /\.ov-dots i\.on/);
  assert.doesNotMatch(read("workspace.js"), /style\.color = 'var\(--' \+ \(last\.value/);
});
