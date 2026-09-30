const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { clockPriorRows, inZone, clockHeadline } = require("../allocation-tools.js");

const root = path.join(__dirname, "..");
const read = (f) => fs.readFileSync(path.join(root, f), "utf8");
const advice = JSON.parse(read("advice.json"));

test("clock prior flags 消费 overweight in Q3 as conflict", () => {
  const rows = clockPriorRows(advice, { status: "ok", quadrant: "Q3", subState: "衰退" });
  assert.equal(rows.length, 9);
  const consumer = rows.find((r) => r.sector === "消费");
  assert.equal(consumer.status, "conflict");
  assert.equal(consumer.inDanger, true);
  const park = rows.find((r) => r.sector === "产业园");
  assert.notEqual(park.status, "conflict"); // 观望/弱低配 落在雷区不算冲突
});

test("clock prior without a live quadrant never claims a conflict", () => {
  const rows = clockPriorRows(advice, { status: "unavailable" });
  assert.ok(rows.every((r) => r.status !== "conflict" && !r.inDanger && !r.inBest));
  assert.equal(rows.find((r) => r.sector === "消费").status, "static");
});

test("transitional state (rate flat) downgrades hits to soft reference, never conflict", () => {
  const clock = { status: "ok", state: "transitional", stateLabel: "利率走平·过渡期", quadrant: null,
    leanQuadrant: "Q3", leanSubState: "衰退", rateDir: "flat", confidence: "低" };
  const rows = clockPriorRows(advice, clock);
  assert.ok(rows.every((r) => r.status !== "conflict" && r.status !== "watch"));
  const consumer = rows.find((r) => r.sector === "消费");
  assert.equal(consumer.status, "reference");
  assert.equal(consumer.softOf, "conflict");
  assert.equal(consumer.inDanger, true);
  assert.equal(consumer.reference, true);
});

test("transitional without lean quadrant behaves like undetermined", () => {
  const rows = clockPriorRows(advice, { status: "ok", state: "transitional", quadrant: null, leanQuadrant: null });
  assert.ok(rows.every((r) => !r.inDanger && !r.inBest && r.status !== "reference"));
});

test("committed rateClock follows calibrated rules (dynamic dead band + growth z3 hysteresis)", () => {
  const cy = JSON.parse(read("cycle_judgment.json"));
  const rc = cy.rateClock;
  if (rc.status !== "ok") return;
  assert.ok(["definite", "transitional", "undetermined"].includes(rc.state));
  assert.equal(rc.methodVersion, "2026-09-30");
  assert.ok(rc.thresholdBp >= 5);
  assert.ok(Math.abs(rc.exitBp - rc.thresholdBp / 2) < 0.051);
  assert.ok(!("boundary" in (rc.growth || {})), "旧 49.5–50.5 边界规则已移除");
  if (rc.state === "transitional") {
    assert.equal(rc.quadrant, null);
    assert.equal(rc.confidence, "低");
    assert.match(rc.stateLabel, /过渡期/);
    assert.ok((rc.conflictFlags || []).every((f) => f.level === "reference"));
  } else if (rc.state === "definite") {
    assert.ok(["up", "down"].includes(rc.rateDir));
    assert.ok([1, -1].includes(rc.growth.state));
  }
  assert.match(rc.summary, /增长.+· 利率/);
  if (rc.growth.critical) assert.match(rc.summary, /临界/);
  assert.match(rc.rateDistance.label, /距/);
  const app = read("app.js");
  assert.match(app, /reference: "参考"/);
  assert.match(app, /rc-trans/);
  assert.match(app, /信号切换/);
  assert.match(app, /rateClockGrowthDist/);
});

test("clockHeadline renders summary, 信号切换 tag, 临界 tag and methodology note", () => {
  const clock = { status: "ok", summary: "增长高于趋势（临界）· 利率下行", growth: { critical: true },
    rateDistance: { critical: false }, signalSwitch: { active: true, cause: "methodology", note: "9-30 起改用新口径，这次切换来自口径更新，不代表市场突变" } };
  const h = clockHeadline(clock);
  assert.match(h, /增长高于趋势（临界）· 利率下行/);
  assert.match(h, /信号切换/);
  assert.match(h, /rc-tag-warn">临界/);
  assert.match(h, /口径更新，不代表市场突变/);
  assert.equal(clockHeadline({ status: "unavailable" }), "");
  assert.doesNotMatch(clockHeadline(Object.assign({}, clock, { signalSwitch: { active: false, note: "x" } })), /信号切换/);
});

test("Q2 definite: 产业园 watch, 消费 no conflict (current calibrated reading)", () => {
  const rows = clockPriorRows(advice, { status: "ok", state: "definite", quadrant: "Q2", subState: "复苏/泡沫" });
  assert.equal(rows.find((r) => r.sector === "产业园").status, "watch");
  assert.notEqual(rows.find((r) => r.sector === "消费").status, "conflict");
});

test("data-status helper labels TSF impulse card: 缓存 · 数据截至 4月 / 待接入", () => {
  const DS = require("../data-status.js");
  const stale = DS.fromTsfImpulse({ status: "ok", asOf: "2026-04", monthsBehind: 5, seriesOrigin: { tsf: "live", gdp: "live" } });
  assert.equal(DS.label(stale), "缓存 · 数据截至 4月");
  const cached = DS.fromTsfImpulse({ status: "ok", asOf: "2026-08", monthsBehind: 1, seriesOrigin: { tsf: "cache" } });
  assert.equal(cached.status, "cached");
  assert.equal(DS.label(DS.fromTsfImpulse({ status: "ok", asOf: "2026-08", monthsBehind: 1, seriesOrigin: {} })), "");
  assert.equal(DS.label(DS.fromTsfImpulse({ status: "pending", label: "待接入" })), "待接入");
  assert.equal(DS.label(DS.make(DS.CACHED, { asOf: "2026-09-01" })), "缓存 · as-of 2026-09-01");
});

test("TSF impulse card: ok carries 数据截至 as-of, pending carries no numbers", () => {
  const t = JSON.parse(read("cycle_judgment.json")).tsfImpulse;
  assert.ok(t, "tsfImpulse present");
  if (t.status === "ok") {
    assert.match(t.asOfLabel, /数据截至 \d+月/);
    assert.equal(t.series[t.series.length - 1][0], t.asOf);
    assert.equal(typeof t.value, "number");
  } else {
    assert.equal(t.status, "pending");
    assert.equal(t.label, "待接入");
    assert.equal(t.value, null);
  }
  const html = read("index.html"), app = read("app.js");
  ["tsfImpulseCard", "tsfImpulseDetail", "tsfImpulseSpark"].forEach((id) => assert.match(html, new RegExp(`id="${id}"`)));
  assert.match(app, /IntersectionObserver/);
  assert.match(app, /待接入/);
});

test("Q4 stagflation zone only matches stagflation sub-state", () => {
  assert.equal(inZone(["Q4-stagflation"], "Q4", "滞胀"), true);
  assert.equal(inZone(["Q4-stagflation"], "Q4", "复苏"), false);
  assert.equal(inZone(["Q3"], null, null), false);
});

test("overseas matrix uses article clock (年化总回报), placeholder removed", () => {
  const html = read("index.html"), app = read("app.js");
  assert.ok(!fs.existsSync(path.join(root, "overseas_static.json")));
  assert.doesNotMatch(app, /overseasStatic/);
  assert.match(html, /美国 REITs 投资时钟（年化总回报 %）/);
  assert.doesNotMatch(html, /历史平均年化超额收益/);
  assert.match(app, /D\.overseasClock/);
  const oc = JSON.parse(read("overseas_clock_du2021.json"));
  const q = Object.fromEntries(oc.quadrants.map((x) => [x.id, x.annualTotalReturn]));
  assert.deepEqual(q, { Q1: 4.9, Q2: 23.9, Q3: 3.5, Q4: 15.1 });
  assert.deepEqual(oc.quadrants[3].split.map((s) => s.annualTotalReturn), [-10.7, 26.1]);
  // 旧占位矩阵的数字（如 14.5 / 16.8 / 18.2）不应再作为数据出现
  const rd = read("data_research.json");
  assert.doesNotMatch(rd, /"placeholder": true/);
});

test("UI mounts rate clock, beta panel and clock prior containers", () => {
  const html = read("index.html");
  ["rateClockChart", "rateClockDetail", "betaScatter", "betaRolling", "betaSectorTable", "betaDisagree", "clockPriorTable", "clockPriorGate", "osClockSectors"].forEach((id) => {
    assert.match(html, new RegExp(`id="${id}"`), id);
  });
  // 配置页只直读 advice.json，不依赖 data_research.json
  const alloc = read("allocation-tools.js");
  assert.match(alloc, /"advice\.json"/);
  assert.doesNotMatch(alloc, /data_research/);
});

test("beta panel shows honest pending state when betas are not computed", () => {
  const app = read("app.js");
  assert.match(app, /B\.status !== "ok"/);
  assert.match(app, /不展示任何示例数值/);
  const rd = JSON.parse(read("data_research.json"));
  const b = rd.correlation && rd.correlation.betas;
  assert.ok(b, "correlation.betas present");
  if (b.status === "pending") {
    assert.equal(b.byReit.length, 0);
    assert.equal(b.bySector.length, 0);
  } else {
    assert.equal(b.status, "ok");
  }
});

test("cycle rateClock carries source and as-of when status ok", () => {
  const cy = JSON.parse(read("cycle_judgment.json"));
  const rc = cy.rateClock;
  assert.ok(["ok", "unavailable"].includes(rc.status));
  if (rc.status === "ok") {
    assert.match(rc.sources.y10, /EMM00166466/);
    assert.match(rc.asOf, /^\d{4}-\d{2}-\d{2}$/);
    assert.ok(Array.isArray(rc.history) && rc.history.length > 0);
  }
  assert.ok(["triggered", "not_triggered", "pending data"].includes(cy.rateRentGate.status));
});
