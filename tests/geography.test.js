const test = require('node:test');
const assert = require('node:assert/strict');
const {selectLocations, groupLocations} = require('../geography/map.js');
const registry = require('../geography/locations.json');
const funds = require('../universe.json');

test('地理条目可追溯，城市级坐标有效，基金与城市关联唯一', () => {
  const keys = new Set();
  for (const r of registry.locations) {
    assert.ok(funds.some(f => f.code === r.code), r.code);
    const source = registry.sources[r.source], city = registry.cities[r.city];
    assert.ok(source && /^https:\/\//.test(source.url) && source.basis && source.checkedAt);
    assert.ok(city && city.province && city.precision === 'city');
    const [lon,lat] = city.coordinates;
    assert.ok(Number.isFinite(lon) && lon >= 73 && lon <= 135);
    assert.ok(Number.isFinite(lat) && lat >= 18 && lat <= 54);
    assert.ok(!keys.has(r.code+'|'+r.city)); keys.add(r.code+'|'+r.city);
  }
});

test('跨城市基金在省级统计只计一次，省份合计不可当作基金总数', () => {
  const rows = selectLocations(registry, funds, {query:'508056'});
  assert.equal(rows.length, 7);
  const cities = groupLocations(rows,registry,'city');
  const provinces = groupLocations(rows,registry,'province');
  assert.equal(cities.length,7);
  assert.equal(provinces.find(p => p.name === '广东省').count,1);
  assert.equal(provinces.find(p => p.name === '广东省').rows.length,3);
});

test('组合筛选搜索底层所在地，不把深国际的深圳品牌当作资产地点', () => {
  const original = JSON.stringify(registry);
  const rows = selectLocations(registry, funds, {query:'180302',sector:'仓储物流'});
  assert.deepEqual(rows.map(r=>r.city).sort(), ['杭州市','黔南布依族苗族自治州'].sort());
  assert.equal(selectLocations(registry,funds,{query:'180302',province:'广东省'}).length,0);
  assert.equal(selectLocations(registry,funds,{query:'不存在的项目'}).length,0);
  assert.equal(JSON.stringify(registry),original);
});

test('索引未收录的基金不填入默认坐标，行情不存在的代码不展示', () => {
  assert.deepEqual(selectLocations(registry,[],{}),[]);
  const missing = funds.filter(f=>!registry.locations.some(r=>r.code===f.code));
  assert.ok(missing.length>0);
  assert.equal(selectLocations(registry,funds,{query:missing[0].code}).length,0);
});
