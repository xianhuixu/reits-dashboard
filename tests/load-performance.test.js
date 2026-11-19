const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.join(__dirname, "..");
const read = (f) => fs.readFileSync(path.join(root, f), "utf8");
const html = read("index.html");
const headers = read("_headers");
const app = read("app.js");

function stylesheetLinks(file) {
  return html.match(new RegExp(`<link[^>]+href="${file}[^"]*"[^>]*>`, "g")) || [];
}

test("data.json preload is discovered before the early fetch and matches credentials omit", () => {
  const preload = html.match(/<link rel="preload" href="data\.json" as="fetch" crossorigin>/);
  assert.ok(preload, "data.json preload link");
  const preloadAt = html.indexOf(preload[0]);
  const fetchAt = html.indexOf('window.__DATA_READY = fetch("data.json"');
  const corsAt = html.indexOf('fetch("data.json", {mode: "cors", credentials: "omit"}');
  const fontAt = html.indexOf('ibm-plex-sans-latin-wght-normal.woff2');
  assert.ok(fetchAt > 0 && corsAt > 0, "__DATA_READY fetch");
  assert.ok(preloadAt < fetchAt, "preload must precede __DATA_READY fetch");
  assert.ok(preloadAt < fontAt, "data.json preload stays early in head");
  assert.equal((html.match(/<link rel="preload" href="data\.json"/g) || []).length, 1);
});

test("lazy CSS/JS for operating data, fund archive and allocation tools are not on the critical path", () => {
  assert.doesNotMatch(html, /<link[^>]+href="research\/operating-data\.css/);
  assert.doesNotMatch(html, /<link[^>]+href="research\/fund-archive\.css/);
  assert.doesNotMatch(html, /<script[^>]+src="research\/operating-data\.js/);
  assert.doesNotMatch(html, /<script[^>]+src="research\/fund-archive\.js/);
  assert.doesNotMatch(html, /<script[^>]+src="allocation-tools\.js/);
  assert.match(html, /<script src="ui-utils\.js\?v=20261119-perf" defer>/);
  assert.match(html, /<script src="workspace\.js\?v=20261119-perf" defer>/);
  assert.match(html, /<script src="app\.js\?v=20261119-layout" defer>/);
  assert.match(html, /<link rel="stylesheet" href="fonts\.css/);
  assert.match(html, /<link rel="stylesheet" href="styles\.css/);
  assert.match(html, /<link rel="stylesheet" href="workspace\.css/);
  assert.match(app, /ensureViewModule\("ops"\)/);
  assert.match(app, /ensureViewModule\("archive"\)/);
  assert.match(app, /ensureViewModule\("alloc"\)/);
  assert.doesNotMatch(html, /<link[^>]+href="research\/track-analysis\.css/);
  assert.doesNotMatch(html, /<script[^>]+src="research\/track-analysis\.js/);
  assert.doesNotMatch(html, /track-analysis\.json/);
  assert.match(app, /ensureViewModule\("track"\)/);
  assert.match(app, /VIEW_ASSETS[\s\S]*track:\s*\{[\s\S]*track-analysis\.js\?v=20261119-layout/);
});

test("research-layout.css and geography/map.css appear once each plus a noscript fallback", () => {
  const layout = stylesheetLinks("research-layout\\.css");
  const map = stylesheetLinks("geography\\/map\\.css");
  assert.equal(layout.length, 2, layout.join("\n"));
  assert.equal(map.length, 2, map.join("\n"));
  assert.match(layout[0], /media="print"/);
  assert.match(map[0], /media="print"/);
  assert.match(html, /<noscript><link rel="stylesheet" href="research-layout\.css/);
  assert.match(html, /<noscript><link rel="stylesheet" href="geography\/map\.css/);
});

test("a fund detail deep link loads the fund-archive module before render", () => {
  assert.match(app, /function restoreNavigationRoute\(/);
  assert.match(app, /#\\\/\?detail\\\/\(\[0-9A-Z.\]\+\)/);
  const start = app.indexOf("  function openReitDetail(code, updateHash)");
  const end = app.indexOf("  function openReitDetailInner(", start);
  assert.ok(start >= 0 && end > start);
  const slice = app.slice(start, end);
  assert.match(slice, /ensureViewModule\("archive"\)/);
  assert.match(slice, /if \(window\.ReitsFundArchive\) go\(\);/);
  assert.match(slice, /if \(location.hash === requestedHash\) openReitDetailInner/);
});

test("_headers caches fonts and versioned CSS/JS, but revalidates JSON immediately", () => {
  assert.match(headers, /\/fonts\/\*/);
  assert.match(headers, /max-age=31536000,\s*immutable/);
  assert.match(headers, /\/\*\.css/);
  assert.match(headers, /\/\*\.js/);
  assert.match(headers, /\/research\/\*\.css/);
  assert.match(headers, /\/research\/\*\.js/);
  assert.match(headers, /max-age=604800,\s*immutable/);
  const jsonRule = headers.lastIndexOf("/*.json");
  const jsRule = headers.indexOf("/*.js");
  const cssRule = headers.indexOf("/*.css");
  assert.ok(jsonRule > jsRule && jsonRule > cssRule, "JSON revalidation must override broader JS/CSS rules");
  const jsonBlocks = [
    "/*.json",
    "/research/*.json",
    "/research/operating-data/*",
    "/research/fund-archives/*"
  ].map((path) => {
    const start = headers.indexOf(path + "\n");
    assert.ok(start >= 0, path);
    return headers.slice(start, start + 120);
  });
  jsonBlocks.forEach((block) => {
    assert.match(block, /Cache-Control:\s*public, max-age=0, must-revalidate/);
    assert.doesNotMatch(block, /max-age=60/);
  });
  assert.match(headers, /\/index\.html\n\s*Cache-Control:\s*public, max-age=0, must-revalidate/);
  assert.match(headers, /(?:^|\n)\/\n\s*Cache-Control:\s*public, max-age=0, must-revalidate/);
  assert.match(headers, /GitHub Pages 不读取本文件/);
});

test("operating-data period packs preserve raw points and are not the 2.5MB monolith", () => {
  const full = JSON.parse(read("research/operating-data.json"));
  const index = JSON.parse(read("research/operating-data-index.json"));
  assert.equal(index.schemaVersion, full.schemaVersion);
  assert.equal(index.latestPeriod, full.latestPeriod);
  assert.deepEqual(index.periods, full.periods);
  assert.deepEqual(index.funds, full.funds);
  assert.deepEqual(index.assets, full.assets);
  assert.deepEqual(index.quality, full.quality);
  assert.ok(!("points" in index));
  assert.equal(index.pointCount, full.points.length);
  const periodFile = path.join(root, "research/operating-data/periods", full.latestPeriod + ".json");
  const pack = JSON.parse(fs.readFileSync(periodFile, "utf8"));
  const expected = full.points.filter((p) => p.period === full.latestPeriod);
  assert.deepEqual(pack.points, expected);
  pack.points.forEach((p) => {
    assert.ok(p.value === null || Number.isFinite(p.value));
    assert.ok("unit" in p && "tax_flag" in p && "caliber" in p && "period" in p);
  });
  const latestSize = fs.statSync(periodFile).size;
  const fullSize = fs.statSync(path.join(root, "research/operating-data.json")).size;
  assert.ok(latestSize < fullSize / 5, `latest period ${latestSize} vs full ${fullSize}`);
  const missing = full.points.filter((p) => p.value == null || Number.isNaN(p.value));
  const packMissing = pack.points.filter((p) => p.value == null || Number.isNaN(p.value));
  assert.equal(packMissing.length, missing.filter((p) => p.period === full.latestPeriod).length);
});

test("fund archives stay lazy: slim index plus sections, complete snapshot only for download", () => {
  const code = "180103.SZ";
  const full = JSON.parse(read("research/fund-archives/" + code + ".json"));
  const index = JSON.parse(read("research/fund-archives/" + code + "/index.json"));
  const shell = JSON.parse(read("research/fund-archives/" + code + "/shell.json"));
  const quotes = JSON.parse(read("research/fund-archives/" + code + "/quotes.json"));
  assert.equal(index.code, code);
  assert.deepEqual(index.info, full.info);
  assert.deepEqual(index.coverage, full.coverage);
  assert.deepEqual(index.quality, full.quality);
  assert.deepEqual(shell.ops_metric, full.tables.ops_metric);
  assert.deepEqual(shell.financials, full.tables.financials);
  assert.deepEqual(quotes.daily_quote, full.tables.daily_quote);
  const indexSize = fs.statSync(path.join(root, "research/fund-archives", code, "index.json")).size;
  const shellSize = fs.statSync(path.join(root, "research/fund-archives", code, "shell.json")).size;
  const fullSize = fs.statSync(path.join(root, "research/fund-archives", code + ".json")).size;
  assert.ok(indexSize + shellSize < fullSize * 0.6, `index+shell ${indexSize + shellSize} vs full ${fullSize}`);
  assert.match(read("research/fund-archive.js"), /fund-archives\/'?\s*\+?\s*esc\(d\.code\)\s*\+?\s*'\.json/);
  const dirs = fs.readdirSync(path.join(root, "research/fund-archives")).filter((n) => n.endsWith(".json") && n !== "manifest.json");
  assert.equal(dirs.length, 103);
  dirs.forEach((name) => {
    const codeName = name.replace(/\.json$/, "");
    assert.ok(fs.existsSync(path.join(root, "research/fund-archives", codeName, "index.json")), codeName);
  });
  assert.doesNotMatch(html, /fund-archives\/\d{6}\.(SH|SZ)\.json/);
});

test("homepage banner stance does not require allocation-tools.js", () => {
  const A = require("../allocation-tools.js");
  const advice = JSON.parse(read("advice.json"));
  const expected = A.schoolStance(advice).text;
  const ws = read("workspace.js");
  const start = ws.indexOf("function bannerStance(adv)");
  const end = ws.indexOf("function stanceOf(adv)", start);
  assert.ok(start >= 0 && end > start);
  const ctx = { root: {}, console };
  vm.createContext(ctx);
  vm.runInContext(
    "var root = { ReitsAllocation: null };\n" +
      ws.slice(ws.indexOf("var ALLOC_LABEL"), ws.indexOf("function stanceOf(adv)")) +
      "\nthis.result = bannerStance(this.advice);",
    Object.assign(ctx, { advice })
  );
  // Evaluate in a fresh context more explicitly
  const ctx2 = { advice, result: null };
  vm.createContext(ctx2);
  const script =
    `var root = {};\n` +
    ws.slice(ws.indexOf("var ALLOC_LABEL"), ws.indexOf("function stanceOf(adv)")) +
    `\nresult = bannerStance(advice);`;
  vm.runInContext(script, ctx2);
  assert.equal(ctx2.result, expected);
});
