const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const root = path.join(__dirname, "..");
const panelPath = path.join(root, "data_panel_l1l7.json");

const REQUIRED = [
  "updated",
  "asOfTrade",
  "bond10ySeries",
  "propertyYieldSeries",
  "operatingIrrSeries",
  "benchmarksNormalized",
  "marketLiquidity",
  "sectorSnapshot",
  "csiReitsMonth",
];

test("data_panel_l1l7.json has schema keys and non-empty L2 series", () => {
  const panel = JSON.parse(fs.readFileSync(panelPath, "utf8"));
  REQUIRED.forEach((k) => assert.ok(k in panel, "missing " + k));
  assert.ok(panel.bond10ySeries.length > 0);
  assert.ok(panel.propertyYieldSeries.length > 0);
  assert.ok(panel.operatingIrrSeries.length > 0);
  assert.equal(panel.sectorSnapshot.length, 9);
  assert.ok(Array.isArray(panel.marketLiquidity));
  assert.ok(Array.isArray(panel.csiReitsMonth));
  assert.ok(panel.benchmarksNormalized && Array.isArray(panel.benchmarksNormalized.dates));
});

test("operating spread is IRR-based (not TTM) in docs and last row", () => {
  const panel = JSON.parse(fs.readFileSync(panelPath, "utf8"));
  const blob = JSON.stringify(panel.seedMeta || {}) + (panel.note || "");
  assert.match(blob, /IRR/i);
  assert.match(panel.seedMeta.operatingSpreadFormula || "", /IRR/i);
  assert.match(panel.seedMeta.operatingSpreadFormula || "", /term-matched|bond10y/i);
  assert.doesNotMatch(panel.seedMeta.operatingSpreadFormula || "", /\bTTM\b/);
  const last = panel.operatingIrrSeries[panel.operatingIrrSeries.length - 1];
  assert.equal(typeof last.irr, "number");
  assert.equal(typeof last.spread, "number");
  const lastP = panel.propertyYieldSeries[panel.propertyYieldSeries.length - 1];
  assert.equal(typeof lastP.ttmYield, "number");
});

test("operating spread target = IRR − term-matched CGB (pending until remaining term is live)", () => {
  const panel = JSON.parse(fs.readFileSync(panelPath, "utf8"));
  const tm = panel.operatingSpreadTermMatched;
  assert.ok(tm, "operatingSpreadTermMatched present");
  assert.ok(["pending", "ok"].includes(tm.status));
  assert.match(tm.formula, /剩余期限/);
  assert.match(tm.formula, /插值/);
  assert.match(tm.propertyFormula, /TTM.*10Y/);
  if (tm.status === "pending") assert.ok(!("spread" in tm) && !("series" in tm));
  (tm.curve.points || []).forEach((p) => assert.equal(p.length, 2));
  const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
  assert.match(html, /IRR − 期限匹配国债/);
  assert.match(html, /id="panelL2TermStatus"/);
});

test("operatingDisclosedIrr is YE2025 disclosed primary and does not feed banner", () => {
  const panel = JSON.parse(fs.readFileSync(panelPath, "utf8"));
  const od = panel.operatingDisclosedIrr;
  assert.ok(od, "operatingDisclosedIrr present");
  assert.equal(od.status, "ok");
  assert.equal(od.label, "2025 年末口径");
  assert.equal(od.curve.asOf, "2025-12-31");
  assert.equal(od.summary.feedsBanner, false);
  assert.equal(od.coverage.disclosed + od.coverage.pending, 30);
  assert.ok(od.items.every((r) => r.irrDisclosedPct != null && r.spreadBp != null));
  assert.ok(od.items.some((r) => r.code === "180201.SZ" && r.sector === "高速公路"));
  const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
  assert.match(html, /id="operIrrTableHost"/);
  assert.match(html, /id="operIrrPendingStrip"/);
  assert.match(html, /2025 年末口径/);
  const app = fs.readFileSync(path.join(root, "app.js"), "utf8");
  assert.match(app, /paintOperatingDisclosed/);
  assert.match(app, /fromOperatingDisclosedIrr/);
});

test("propertySpread is live (rolling 3y pctile) and feeds L2 property series", () => {
  const panel = JSON.parse(fs.readFileSync(panelPath, "utf8"));
  const ps = panel.propertySpread;
  assert.ok(ps, "propertySpread present");
  assert.ok(["ok", "lagged"].includes(ps.status));
  assert.ok(ps.latest.pctRolling3y >= 90);
  assert.ok(ps.latest.pctFull >= ps.latest.pctRolling3y - 5);
  assert.equal(ps.distYoY.tolerancePct, 2);
  assert.ok(ps.sectors.some((r) => r.valueTrap && r.sector === "产业园"));
  assert.ok(ps.sectors.some((r) => r.shortHistory && r.sector === "数据中心"));
  assert.equal(panel.propertyYieldSeries[panel.propertyYieldSeries.length - 1].date, ps.asOf);
  assert.ok(panel.propertyYieldSeries.length > 100);
});

test("build_data_panel.py --check exits 0", () => {
  const r = spawnSync("python3", ["build_data_panel.py", "--check"], { cwd: root, encoding: "utf-8" });
  assert.equal(r.status, 0, r.stderr || r.stdout);
});

test("UI mounts L2 chart containers and demotes avgYield gauge copy", () => {
  const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
  const app = fs.readFileSync(path.join(root, "app.js"), "utf8");
  assert.match(html, /id="chartL2Property"/);
  assert.match(html, /id="chartL2Operating"/);
  assert.match(html, /id="operIrrTableHost"/);
  assert.match(html, /data_panel_l1l7\.json/);
  assert.match(html, /非产权锚/);
  assert.match(app, /renderL2SpreadCharts/);
  assert.match(app, /chartL2Property/);
  assert.match(app, /非产权锚/);
});

test("L2 renderer does not throw on seed panel (node smoke)", () => {
  const panel = JSON.parse(fs.readFileSync(panelPath, "utf8"));
  // Minimal shape check mimicking dualSpreadOption inputs
  function smoke(rows, yieldKey) {
    assert.ok(rows.every((r) => r.date && typeof r[yieldKey] === "number" && typeof r.spread === "number"));
  }
  smoke(panel.propertyYieldSeries, "ttmYield");
  smoke(panel.operatingIrrSeries, "irr");
  assert.ok(panel.bond10ySeries.every((r) => r.date && typeof r.ytm === "number"));
});
