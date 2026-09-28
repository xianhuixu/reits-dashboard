const test = require('node:test');
const assert = require('node:assert/strict');
const {selectLocations, groupLocations, sectorCounts} = require('../geography/map.js');
const registry = require('../geography/sponsors.json');
const funds = require('../universe.json');

test('主体注册地有交易所披露来源、合法城市坐标与唯一主体记录', () => {
  const keys = new Set();
  for (const r of registry.locations) {
    assert.ok(funds.some(f => f.code === r.code), r.code);
    const source = registry.sources[r.source], city = registry.cities[r.city];
    assert.ok(source && /^https:\/\/(www\.sse\.com\.cn|disc\.static\.szse\.cn)\//.test(source.url) && source.basis && source.checkedAt);
    assert.match(r.organization,/公司|合伙/);
    assert.match(r.role,/原始权益人|发起人/);
    assert.ok(city && city.province && city.precision === 'city');
    const [lon,lat] = city.coordinates;
    assert.ok(Number.isFinite(lon) && lon >= 73 && lon <= 135);
    assert.ok(Number.isFinite(lat) && lat >= 18 && lat <= 54);
    const key=r.code+'|'+r.organization+'|'+r.city;
    assert.ok(!keys.has(key)); keys.add(key);
  }
});

test('按原始权益人注册地定位，不沿用底层资产所在地', () => {
  const rows=selectLocations(registry,funds,{});
  assert.deepEqual(rows.filter(r=>r.code.startsWith('180203')).map(r=>r.city),['天津市']);
  assert.deepEqual(rows.filter(r=>r.code.startsWith('508017')).map(r=>r.city),['上海市']);
  assert.deepEqual(rows.filter(r=>r.code.startsWith('180302')).map(r=>r.city),['深圳市']);
  assert.ok(!rows.some(r=>r.code.startsWith('508056')));
});

test('多主体、多城市按基金代码去重，资产类别支持多选', () => {
  const rows=selectLocations(registry,funds,{});
  assert.deepEqual(new Set(rows.filter(r=>r.code.startsWith('180303')).map(r=>r.city)),new Set(['嘉兴市','南京市','天津市']));
  assert.equal(groupLocations(rows,registry,'city').find(g=>g.name==='深圳市').count,
    new Set(rows.filter(r=>r.city==='深圳市').map(r=>r.code)).size);
  assert.equal(sectorCounts(rows).reduce((n,s)=>n+s.count,0),new Set(rows.map(r=>r.code)).size);
  assert.ok(selectLocations(registry,funds,{sectors:['仓储物流']}).every(r=>r.fund.sector==='仓储物流'));
  assert.deepEqual(selectLocations(registry,funds,{sectors:[]}),[]);
  assert.equal(selectLocations(registry,funds,{query:'招商局公路',province:'天津市'}).length,1);
});

test('境外及待核验主体没有默认内地点位', () => {
  assert.deepEqual(selectLocations(registry,[],{}),[]);
  const marked=new Set(registry.locations.map(r=>r.code));
  for(const code of ['508056.SH','508060.SH','508078.SH','508088.SH','180503.SZ','180306.SZ']) assert.ok(!marked.has(code),code);
});
