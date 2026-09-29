const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { clockPriorRows, inZone } = require("../allocation-tools.js");

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

test("committed rateClock: transitional ⇒ no quadrant, flat, low confidence, only reference flags", () => {
  const rc = JSON.parse(read("cycle_judgment.json")).rateClock;
  if (rc.status !== "ok") return;
  assert.ok(["definite", "transitional", "undetermined"].includes(rc.state));
  if (rc.state === "transitional") {
    assert.equal(rc.quadrant, null);
    assert.equal(rc.rateDir, "flat");
    assert.equal(rc.confidence, "低");
    assert.equal(rc.stateLabel, "利率走平·过渡期");
    assert.ok(Math.abs(rc.d10y60bp) < 10);
    assert.ok((rc.conflictFlags || []).every((f) => f.level === "reference"));
  }
  const app = read("app.js");
  assert.match(app, /reference: "参考"/);
  assert.match(app, /rc-trans/);
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
