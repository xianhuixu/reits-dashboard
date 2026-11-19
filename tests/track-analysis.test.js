const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const read = (f) => fs.readFileSync(path.join(root, f), "utf8");
const html = read("index.html");
const app = read("app.js");
const js = read("research/track-analysis.js");
const css = read("research/track-analysis.css");
const pack = JSON.parse(read("research/track-analysis.json"));
const Track = require("../research/track-analysis.js");

test("track pack is fund-scope only and keeps 和达 fund occupancy isolated from projects", () => {
  assert.equal(pack.schemaVersion, 1);
  assert.equal(pack.latestPeriod, "2026Q3");
  assert.equal(pack.selfCheck.hedaFundOccupancy, 0.7551);
  assert.deepEqual(pack.selfCheck.hedaProjectOccupancies, [0.6378, 0.9107, 0.9207]);
  const occ = pack.latest.occupancy_rate;
  assert.equal(occ.period, "2026Q3");
  assert.equal(occ.caliber, "期末");
  assert.equal(occ.unit, "小数");
  assert.equal(occ.tax_flag, "不适用");
  const heda = occ.sectors.flatMap((s) => s.funds).find((f) => f.code === "180103.SZ");
  assert.ok(heda, "和达 should appear in fund-level occupancy");
  assert.equal(heda.value, 0.7551);
  assert.equal(heda.display, 75.51);
  assert.notEqual(heda.value, 0.9207);
  assert.notEqual(heda.display, 92.07);
  for (const metric of pack.metrics) {
    for (const s of pack.latest[metric.id].sectors) {
      for (const f of s.funds) {
        assert.equal(typeof f.value, "number");
        assert.ok(Number.isFinite(f.value));
        assert.notEqual(f.value, null);
      }
      assert.equal(s.n + s.undisclosed, s.universe);
      assert.equal(s.undisclosedCodes.length, s.undisclosed);
      if (s.n === 0 || s.pointOnly) {
        assert.equal(s.median, null);
        assert.equal(s.medianDisplay, null);
      } else {
        assert.equal(typeof s.median, "number");
        assert.ok(!s.undisclosedCodes.some((c) => s.funds.some((f) => f.code === c)));
      }
    }
  }
});

test("nulls stay 本期无匹配口径数据 and zeros are not invented in the formatter", () => {
  assert.equal(Track.format(null), "本期无匹配口径数据");
  assert.equal(Track.format(undefined), "本期无匹配口径数据");
  assert.equal(Track.format(NaN), "本期无匹配口径数据");
  assert.equal(Track.format(0), "0");
  assert.equal(Track.format(75.51), "75.51");
  assert.match(js, /if \(v == null \|\| typeof v !== "number" \|\| !isFinite\(v\)\) return "本期无匹配口径数据"/);
  assert.doesNotMatch(js, /value \|\| 0/);
});

test("changing-sample medians carry per-period coverage and are not written as 改善 or 恶化", () => {
  const notes = pack.sourceNotes.join("\n");
  assert.match(notes, /变动样本中位数/);
  assert.match(notes, /不把中位数升降写成改善\/恶化/);
  assert.match(notes, /基金等权、非面积加权/);
  assert.match(notes, /出租率中位数环比不是同店改善/);
  assert.match(notes, /不绘制同比/);
  assert.match(html, /连线可能只是样本更换，不代表经营改善或恶化/);
  assert.match(js, /不代表经营改善或恶化/);
  assert.match(html, /不是同店改善/);
  assert.match(html, /基金等权、非面积加权/);
  assert.match(js, /变动样本中位数，不代表经营改善或恶化/);
  assert.match(js, /spec\.weighting_note/);
  assert.match(html, /基金等权、非面积加权/);
  const occ = pack.metrics.find((m) => m.id === "occupancy_rate");
  assert.equal(occ.weighting_note, "基金等权、非面积加权");
  const xiaofei = pack.trend.occupancy_rate.sectors.find((s) => s.sector === "消费");
  const q2 = xiaofei.points.find((p) => p.period === "2026Q2");
  const q3 = xiaofei.points.find((p) => p.period === "2026Q3");
  assert.equal(q2.n, 12);
  assert.equal(q3.n, 13);
  assert.equal(q3.codes.length, 13);
  for (const s of pack.trend.occupancy_rate.sectors) {
    for (const p of s.points) {
      assert.ok(p.n >= 1);
      assert.equal(p.codes.length, p.n);
    }
  }
  assert.equal(pack.trend.occupancy_rate.sampleNote.includes("不代表经营改善或恶化"), true);
  assert.ok(!("yoy" in pack));
  assert.ok(!pack.metrics.some((m) => /yoy|同比/i.test(m.id + m.label)));
});

test("fixed same-caliber sample reports rise share separately and excludes in-window 扩募", () => {
  const xiaofei = pack.trend.occupancy_rate.sectors.find((s) => s.sector === "消费");
  const pair = xiaofei.fixedPairs.find((p) => p.from === "2026Q2" && p.to === "2026Q3");
  assert.equal(pair.n, 12);
  assert.equal(pair.nUp, 7);
  assert.equal(pair.nDown, 4);
  assert.equal(pair.nFlat, 1);
  assert.equal(pair.nUp + pair.nDown + pair.nFlat, pair.n);
  assert.equal(pair.excludedExpansion, 0);
  assert.ok(Math.abs(pair.upShare - 7 / 12) < 1e-12);
  assert.match(pair.note, /不是同店改善/);
  assert.match(js, /报告值上升/);
  assert.match(html, /固定同口径样本变化/);
  assert.doesNotMatch(html, /减持红线/);
  assert.doesNotMatch(app, /\["减持红线"/);
  assert.doesNotMatch(app, /连续两期 <90% 系统性减持/);
  assert.match(html, /框架红线不自动下达减持指令/);
});

test("track analysis assets are lazy-loaded only when 赛道透视 opens", () => {
  assert.doesNotMatch(html, /<link[^>]+href="research\/track-analysis\.css/);
  assert.doesNotMatch(html, /<script[^>]+src="research\/track-analysis\.js/);
  assert.doesNotMatch(html, /track-analysis\.json/);
  assert.match(app, /track:\s*\{ css: "research\/track-analysis\.css\?v=20261119-trackfix", js: "research\/track-analysis\.js\?v=20261119-trackfix" \}/);
  const switchStart = app.indexOf("  function switchView(v)");
  const switchEnd = app.indexOf("  function showPage(", switchStart);
  const slice = app.slice(switchStart, switchEnd);
  assert.match(slice, /v === "track"/);
  assert.match(slice, /ensureViewModule\("track"\)/);
  assert.match(slice, /ReitsTrackAnalysis\.mount/);
  assert.doesNotMatch(app, /LAZY\.research\.push\(function \(\) \{\s*var TRACKS/);
  assert.doesNotMatch(js, /REITS_DATA\s*=/);
  assert.doesNotMatch(js, /REITS_ADVICE\s*=/);
  assert.match(js, /fetch\("research\/track-analysis\.json"\)/);
  assert.match(html, /id="v-track"/);
  assert.match(html, /id="trackMedianChart"/);
  assert.match(html, /id="trackTrendChart"/);
  assert.match(css, /max-width:767px/);
  assert.match(html, /<script src="app\.js\?v=20261119-trackfix" defer>/);
});

test("user-requested removal is limited to the two track valuation cards", () => {
  assert.doesNotMatch(html, /id="trackVal(?:Property|Operating)/);
  assert.doesNotMatch(js, /renderValuation|renderPropertyValuation|renderOperatingValuation|__PANEL_READY|REITS_DATA_PANEL/);
  assert.doesNotMatch(js, /propertySpread|operatingDisclosedIrr/);
  // Other pages keep the existing valuation source and functionality.
  const panel = JSON.parse(read("data_panel_l1l7.json"));
  assert.ok(panel.propertySpread && panel.operatingDisclosedIrr);
  assert.match(read("allocation-tools.js"), /operatingDisclosedIrr/);
});
