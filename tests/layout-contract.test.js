const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");

test("mobile layout does not hide page-level horizontal overflow", () => {
  assert.doesNotMatch(html, /html, body\s*\{\s*overflow-x:\s*clip/);
});

test("layout containers can shrink within the mobile viewport", () => {
  assert.match(html, /\.page, \.view, \.card\s*\{\s*min-width:\s*0;/);
});

test("wide financial matrices use local scrolling containers", () => {
  ["matrix", "osMatrix", "usCoupleStats", "corrMatrix", "peerBars", "advicePerf", "fundTable", "backtestTable"].forEach((id) => {
    assert.match(html, new RegExp(`class="table-scroll" id="${id}"`));
  });
  assert.match(html, /\.table-scroll\s*\{[^}]*overflow-x:\s*auto/s);
  assert.match(html, /\.table-scroll\s*>\s*table\s*\{[^}]*min-width:\s*680px/s);
});

test("mobile secondary navigation exposes scrollable tabs", () => {
  assert.match(html, /#subbar \.sub\s*\{[^}]*overflow-x:\s*auto/s);
  assert.match(html, /#subbar \.sub\s*\{[^}]*scroll-snap-type:\s*x proximity/s);
});

test("allocation conclusions precede long-term mapping detail", () => {
  const adviceStart = html.indexOf('id="advCycle"');
  const adviceEnd = html.indexOf('id="advTactic"');
  const adviceSection = html.slice(adviceStart, adviceEnd);
  assert.ok(adviceSection.indexOf('id="adviceList"') < adviceSection.indexOf('id="adviceMapping"'));
  assert.match(html, /id="adviceList" class="advice-summary"/);
});

test("entry motion is bounded and keyboard focus remains visible", () => {
  assert.match(html, /Math\.min\(i \* 50, 250\)/);
  assert.match(html, /:focus-visible/);
});

test("generated charts expose accessible SVG titles", () => {
  assert.match(html, /function svgTitle\(/);
  assert.match(html, /<title>/);
});

test("primary navigation preserves page scroll positions", () => {
  assert.match(html, /var pageScroll = \{ pano: 0, research: 0, advice: 0, inst: 0 \}/);
  assert.match(html, /pageScroll\[currentPage\] = window\.(?:pageYOffset \|\| window\.)?scrollY/);
  assert.match(html, /behavior: "auto"/);
});

test("primary and secondary navigation share one sticky shell", () => {
  assert.match(html, /<nav id="topbar"[^>]*>[\s\S]*<div id="subbar"[\s\S]*<\/nav>\s*<div class="data-meta" id="meta">/);
  assert.match(html, /#topbar\s*\{[^}]*position:\s*sticky/s);
  assert.doesNotMatch(html, /#subbar\s*\{[^}]*position:\s*sticky/s);
  assert.doesNotMatch(html, /#subbar\s*\{[^}]*(?:^|;)\s*top:\s*\d+px/ms);
});

test("secondary navigation labels do not use numeric prefixes", () => {
  const adviceStart = html.indexOf('id="adviceSub"');
  const adviceSub = html.slice(adviceStart, html.indexOf("</div>", adviceStart));
  assert.doesNotMatch(adviceSub, /[①②③④]/);
  assert.match(adviceSub, />大类策略配置建议</);
  assert.match(adviceSub, />风险提示</);
});

test("navigation state and anchor offsets are accessible and header-aware", () => {
  assert.match(html, /aria-current/);
  assert.match(html, /function setActiveNav\(/);
  assert.match(html, /setAttribute\("aria-current", "page"\)/);
  assert.match(html, /btn\.parentElement\.querySelectorAll\("button"\)/);
  assert.match(html, /scroll-margin-top:\s*var\(--sticky-offset\)/);
  assert.doesNotMatch(html, /window\.scrollY - 132/);
  assert.doesNotMatch(html, /document\.querySelectorAll\("#subbar \.sub button\.on"\)/);
});
