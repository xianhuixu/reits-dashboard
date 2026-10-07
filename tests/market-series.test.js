const test = require('node:test');
const assert = require('node:assert/strict');
const source = require('../data_research.json');
const compact = require('../market-series.json');

test('首页轻量市场序列与研究数据完全一致，不改变数值或观察日期', () => {
  assert.deepEqual(compact.dates, source.series.dates);
  assert.deepEqual(compact.market, source.series.market);
  assert.equal(compact.asOf, compact.dates.at(-1));
  assert.equal(compact.source, 'data_research.json');
});
