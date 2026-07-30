const test = require("node:test");
const assert = require("node:assert/strict");

const { averagePercentile, formatPercentile } = require("../ui-utils.js");

test("formatPercentile formats values already expressed on a 0-100 scale", () => {
  assert.equal(formatPercentile(44.88), "44.9%");
  assert.equal(formatPercentile(15.93), "15.9%");
});

test("formatPercentile formats an average percentile without rescaling it", () => {
  assert.equal(formatPercentile(averagePercentile([10, 20, 30])), "20.0%");
});

test("formatPercentile renders null and non-finite values as a dash", () => {
  assert.equal(formatPercentile(null), "—");
  assert.equal(formatPercentile(Number.NaN), "—");
  assert.equal(formatPercentile(Number.POSITIVE_INFINITY), "—");
  assert.equal(formatPercentile(Number.NEGATIVE_INFINITY), "—");
});

test("averagePercentile safely ignores null and non-finite values", () => {
  assert.equal(
    averagePercentile([10, null, Number.NaN, 20, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]),
    15
  );
  assert.equal(averagePercentile([null, Number.NaN, Number.POSITIVE_INFINITY]), null);
});
