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
  assert.ok(["ok", "lagged"].includes(P.propertySpread.status));
  const sp = H.spreadCard(P);
  assert.ok(sp.ok && sp.pctile >= 90 && sp.pctile <= 100);
  assert.ok(sp.pctileFull >= sp.pctile - 5);
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

test("advice: stanceOverride, recommendation rows and red lines", () => {
  const adv = JSON.parse(read("advice.json"));
  const D = JSON.parse(read("data.json"));
  const st = A.schoolStance(adv);
  assert.equal(st.override, "产权标配·偏多观察");
  assert.equal(st.text, "产权标配·偏多观察");
  assert.equal(st.property.label, "标配");
  assert.equal(st.property.cls, "alloc-n");
  const rec = A.recommendationRows(adv, A.sectorRights(D.reits));
  const prop = rec.rows.find((r) => r.kind === "right" && r.name === "产权类");
  assert.equal(prop.alloc.label, "标配");
  assert.equal(prop.alloc.cls, "alloc-n");
  assert.equal(rec.hasPrev, !!adv.previous);
  assert.ok(rec.rows.some((r) => r.kind === "sector"));
  if (!rec.hasPrev) rec.rows.forEach((r) => assert.equal(r.change, null));
  const rl = A.redlines(D.cycle, adv);
  assert.deepEqual(rl.map((r) => r.id), ["rate_up", "rate_rent", "tsf_turn", "distribution"]);
  assert.equal(rl[3].status, "pending");
  assert.match(rl[1].current, /分位腿|顺风/);
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

// ---------------- 2026-09-30 团队反馈：结论横幅依据行 ----------------
const STANCE = "产权标配·偏多观察";
const liveData = () => JSON.parse(read("data.json"));
const liveAdvice = () => JSON.parse(read("advice.json"));
const livePanel = () => JSON.parse(read("data_panel_l1l7.json"));

test("banner conclusion is rate → stanceOverride; spread basis hidden while distributions decline", () => {
  const adv = liveAdvice(), panel = livePanel();
  const m = H.bannerModel(liveData(), STANCE, panel, adv);
  assert.equal(m.conclusion, "利率下行 → " + STANCE);
  assert.equal(m.basis, "依据：时钟·利率下行"); // 分派同比下滑 → 第二条依据不进 basis
  assert.match(m.spreadSkip, /利差分位暂不参与/);
  assert.match(m.spreadSkip, /分派同比下滑|数据滞后/);
  assert.match(m.overrideNote || "", /降档理由|顺风|拖累/);
  assert.equal(m.aux, "辅助：社融脉冲转负（低置信，数据截至 4 月）");
  assert.doesNotMatch([m.conclusion, m.basis, m.aux].join("|"), /增长|临界|趋势|PMI|z3/);
  // 分派企稳 + live → 第二条依据出现
  const ok = JSON.parse(JSON.stringify(panel));
  ok.propertySpread.status = "ok";
  ok.propertySpread.distYoY.medianPct = 1.0;
  ok.propertySpread.distYoY.state = "企稳";
  const m2 = H.bannerModel(liveData(), STANCE, ok, adv);
  assert.match(m2.basis, /产权利差分位 \d+%（滚动3年）/);
  assert.equal(m2.spreadSkip, null);
  assert.ok(m2.used.includes("propertySpread"));
});

test("growth state never changes the banner", () => {
  const base = H.bannerModel(liveData(), STANCE);
  for (const g of [{ state: -1, z3: -0.9, critical: false }, { state: 0, z3: 0.1, critical: true }, { state: 1, z3: 2, critical: false }]) {
    const d = liveData();
    Object.assign(d.cycle.rateClock.growth, g);
    const m = H.bannerModel(d, STANCE);
    assert.deepEqual([m.conclusion, m.basis, m.aux], [base.conclusion, base.basis, base.aux]);
  }
});

test("seed / pending modules are excluded from banner derivation", () => {
  const d = liveData();
  const base = H.bannerModel(d, STANCE);
  // 产权利差分位（SEED / 无 propertySpread）无论分位高低都不进第二条依据
  for (const pctile of [0.01, 0.5, 0.99]) {
    const seedPanel = { source: "seed", seedMeta: { liveFetch: false }, propertyYieldSeries: [{ pctile, spread: 1 }] };
    const m = H.bannerModel(d, STANCE, seedPanel);
    assert.deepEqual([m.conclusion, m.basis, m.aux], [base.conclusion, base.basis, base.aux]);
    assert.ok(m.excluded.some((e) => /propertySpread/.test(e)));
    assert.ok(!m.used.includes("propertySpread"));
  }
  // 社融脉冲 pending → 不给辅助依据
  const d2 = liveData(); d2.cycle.tsfImpulse = { status: "pending" };
  assert.equal(H.bannerModel(d2, STANCE).aux, null);
  // 时钟为种子 / 待接入 → 不给利率结论
  const d3 = liveData(); d3.cycle.rateClock.status = "seed";
  const m3 = H.bannerModel(d3, STANCE);
  assert.equal(m3.rate, null);
  assert.ok(m3.excluded.includes("rateClock"));
  assert.equal(m3.basis, "依据：配置页学派立场");
});

test("tsf aux line: only when negative; 转负 only after a positive→negative flip", () => {
  const withTsf = (t) => { const d = liveData(); d.cycle.tsfImpulse = Object.assign({ status: "ok", asOf: "2026-04", monthsBehind: 5 }, t); return H.bannerModel(d, STANCE).aux; };
  assert.equal(withTsf({ value: 0.5, lastFlip: { direction: "负转正" } }), null);
  assert.equal(withTsf({ value: -0.3, lastFlip: null }), "辅助：社融脉冲为负（低置信，数据截至 4 月）");
  assert.match(withTsf({ value: -0.3, lastFlip: { direction: "正转负" } }), /转负/);
});

test("banner / advice rationale containers and clock card no-wrap fragments", () => {
  const html = read("index.html");
  assert.match(html, /id="ovBasis"/);
  assert.match(html, /id="advBasis"/);
  const c = H.clockCard(JSON.parse(read("data.json")).cycle.rateClock);
  assert.equal(c.rateThr, "阈值 5.0bp（下限）");
  assert.match(read("workspace.js"), /ov-nw/);
});

test("head: scripts deferred; latin web font is self-hosted with font-display; no @font-face in styles/workspace", () => {
  const html = read("index.html");
  (html.match(/<script src="[^"]+"[^>]*>/g) || []).forEach((s) => assert.match(s, /\bdefer\b/, s));
  assert.doesNotMatch(read("styles.css") + read("workspace.css"), /@font-face/, "keep @font-face out of styles/workspace");
  const fonts = read("fonts.css");
  assert.match(fonts, /@font-face/);
  assert.match(fonts, /font-display:\s*swap/);
  assert.match(fonts, /IBM Plex Sans/);
  assert.match(html, /fonts\.css/);
  assert.match(html, /preload[^>]+ibm-plex-sans-latin-wght-normal\.woff2/);
  assert.match(read("workspace.css"), /--fs-1:\s*12px/);
  assert.match(read("workspace.css"), /--font-data:\s*var\(--font-latin\)/);
  // design-r3: critical path CSS for banner + 4 cards is inlined for LCP
  assert.match(html, /id="critical-css"/);
  const crit = html.match(/<style id="critical-css">([\s\S]*?)<\/style>/);
  assert.ok(crit, "critical-css style block present");
  assert.match(crit[1], /\.ov-headline/);
  assert.match(crit[1], /\.ov-cards/);
  assert.match(crit[1], /\.ov-hero/);
});

test("design-r1: panel subheads and L2 stamps use type-scale classes (no inline font-size)", () => {
  const html = read("index.html");
  assert.doesNotMatch(html, /style="[^"]*font-size/);
  assert.match(html, /class="panel-subhead"/);
  assert.match(html, /经营权 · 基金披露 IRR/);
  assert.match(html, /class="panel-l2-stamp"/);
  assert.match(read("workspace.css"), /@keyframes ov-rise/);
  assert.match(read("workspace.css"), /prefers-reduced-motion:reduce[^}]*\.ov-hero/s);
});

test("design-r2: home + strategy L2 have zero inline font-size; eye accent stays research-blue", () => {
  const html = read("index.html");
  const home = html.match(/id="v-heatmap"[\s\S]*?(?=<section class="view")/)[0];
  const strat = html.match(/id="v-strategy"[\s\S]*?(?=<section class="view")/)[0];
  assert.doesNotMatch(home, /font-size\s*:/);
  assert.doesNotMatch(strat, /font-size\s*:/);
  assert.match(home, /ov-skel-block/);
  assert.match(home, /hm-skel/);
  assert.match(home, /ovHeadline/);
  assert.match(home, /产权标配·偏多观察/);
  const wc = read("workspace.css");
  const eye = wc.match(/\[data-theme="eye"\]\s*\{[^}]+\}/)[0];
  assert.match(eye, /--accent:#2f5fc9|--accent:\s*#2f5fc9/);
  assert.doesNotMatch(eye, /--accent:#32664e/);
  assert.match(wc, /--brand:#3159ce/);
  assert.match(read("page-agent-loader.js"), /rd-ai-panel-open #rdAiLauncher/);
  assert.match(read("page-agent-loader.js"), /visibility:hidden/);
  assert.match(read("page-agent-loader.js"), /\[data-theme="eye"\] #rdAiLauncher/);
  // strategy card / heatmap crumbs no longer use inline font-size
  const app = read("app.js");
  assert.match(app, /strat-today/);
  assert.match(app, /hm-crumb-now/);
  assert.doesNotMatch(app, /strat-card[\s\S]{0,200}style="font-size:12px/);
});

test("design-r3: chart/scroll utilities replace height inline; skeleton fades in; idle non-FP scripts", () => {
  const html = read("index.html");
  const wc = read("workspace.css");
  const app = read("app.js");
  const ws = read("workspace.js");
  assert.match(wc, /\.chart-h-sm\s*\{\s*height:\s*300px/);
  assert.match(wc, /\.chart-h-md\s*\{\s*height:\s*380px/);
  assert.match(wc, /\.chart-h-lg\s*\{\s*height:\s*400px/);
  assert.match(wc, /\.scroll-panel\s*\{/);
  assert.match(html, /class="chart-h-sm"/);
  assert.match(html, /class="chart-h-md"/);
  assert.match(html, /class="chart-h-lg"/);
  assert.match(html, /scroll-panel scroll-panel-/);
  assert.doesNotMatch(html, /style="[^"]*(?:max-)?height\s*:/);
  assert.doesNotMatch(html, /style="/);
  assert.match(wc, /@keyframes ov-content-in/);
  assert.match(wc, /is-content-in/);
  assert.match(ws, /is-content-in/);
  assert.match(app, /is-content-in/);
  assert.match(html, /requestIdleCallback/);
  assert.match(html, /page-agent-loader\.js/);
  assert.match(html, /geography\/map\.js/);
  assert.doesNotMatch(html, /<script src="tender-feed\.js[^"]*" defer/);
  assert.doesNotMatch(html, /<script src="geography\/map\.js[^"]*" defer/);
  assert.match(app, /runEntryMotion/);
  const panel = JSON.parse(read("data_panel_l1l7.json"));
  assert.ok(panel.operatingDisclosedIrr);
  assert.equal(panel.operatingDisclosedIrr.status, "ok");
  assert.ok((panel.operatingDisclosedIrr.items || []).length >= 20);
  assert.match(read("docs/deferred/banner-prerender-workflow.md"), /design-r3 \(PR #24\)/);
});

