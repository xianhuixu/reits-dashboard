const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert/strict");
const A = require("../allocation-tools.js");
const { stress, summarize } = A;

test("cash-only shocks pass through both valuation models", () => {
  for (const kind of ["property", "concession"]) {
    assert.ok(Math.abs(stress({kind, rate: .05, shock: 0, cash: -.1, years: 15}) + .1) < 1e-12);
    assert.equal(stress({kind, rate: .05, shock: 0, cash: 0, years: 15}), 0);
  }
});
test("combined perpetual shock matches independently calculated value ratio", () => {
  const change = stress({kind: "property", rate: .05, shock: .005, cash: -.05, years: 15});
  assert.ok(Math.abs(change - ((95 / .055) / (100 / .05) - 1)) < 1e-12);
});
test("finite cash flow result matches explicit annual discounted cash flows", () => {
  let base = 0, shocked = 0;
  for (let t = 1; t <= 15; t++) { base += 100 / 1.05 ** t; shocked += 95 / 1.055 ** t; }
  const change = stress({kind: "concession", rate: .05, shock: .005, cash: -.05, years: 15});
  assert.ok(Math.abs(change - (shocked / base - 1)) < 1e-12);
});
test("invalid assumptions cannot produce a plausible valuation", () => {
  const base = {kind: "property", rate: .05, shock: .005, cash: -.05, years: 15};
  for (const invalid of [{rate: 0}, {shock: -.05}, {cash: -1.1}, {years: 1.5}, {rate: NaN}, {kind: "unknown"}]) {
    assert.throws(() => stress({...base, ...invalid}), RangeError);
  }
  assert.equal(stress({...base, cash: -1}), -1);
});
test("market summary excludes missing returns and does not mutate source rows", () => {
  const rows = Object.freeze([Object.freeze({right: "产权", ret20: 2}),
    Object.freeze({right: "产权", ret20: null}), Object.freeze({right: "产权", ret20: NaN}),
    Object.freeze({right: "经营权", ret20: -4})]);
  assert.deepEqual(summarize(rows, "产权"), {count: 3, valid: 1, ret20: 2});
  assert.deepEqual(summarize(rows, "经营权"), {count: 1, valid: 1, ret20: -4});
  assert.deepEqual(summarize([], "产权"), {count: 0, valid: 0, ret20: null});
});

const panel = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "data_panel_l1l7.json"), "utf8"));

test("operating disclosed table disables spread sort and hides sector average", () => {
  const rows = A.operatingDisclosedRows(panel);
  assert.ok(rows.length >= 21);
  const html = A.operatingDisclosedTableHtml(rows, panel.operatingDisclosedIrr.summary);
  assert.match(html, /data-no-sort="1"/);
  assert.match(html, /口径不统一，暂不汇总/);
  assert.match(html, /年末以来价格/);
  const strip = A.operatingPendingStripHtml(A.operatingPendingRows(panel));
  assert.match(strip, /暂无披露/);
  assert.match(strip, /oper-irr-dot/);
});
