const test = require('node:test');
const assert = require('node:assert/strict');
const {selectLocations, groupLocations, sectorCounts} = require('../geography/map.js');
const registry = require('../geography/sponsors.json');
const funds = require('../universe.json');

test('主体注册地有交易所披露来源、合法城市坐标与唯一主体记录', () => {
  const keys = new Set();
  // primary = 交易所官网披露文件；secondary = 披露文件的指定转载平台（仅境外主体补点使用）
  const PRIMARY = /^https:\/\/(www\.sse\.com\.cn|disc\.static\.szse\.cn)\//;
  const SECONDARY = /^https?:\/\/(pdf\.dfcfw\.com|fund\.eastmoney\.com|cfi\.net\.cn|static\.cninfo\.com\.cn)\//;
  for (const r of registry.locations) {
    assert.ok(funds.some(f => f.code === r.code), r.code);
    const source = registry.sources[r.source], city = registry.cities[r.city];
    assert.ok(source && source.basis && source.checkedAt, r.code);
    if (source.kind === 'secondary') assert.match(source.url, SECONDARY, r.code);
    else assert.match(source.url, PRIMARY, r.code);
    assert.match(r.organization,/公司|合伙/);
    assert.match(r.role,/原始权益人|发起人|运营管理机构/);
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
  assert.deepEqual(rows.filter(r=>r.code.startsWith('180503')).map(r=>r.city),['北京市']);
  // 普洛斯：原始权益人香港注册，补点为境内运营管理机构（上海），不是原始权益人点位
  const glp=rows.filter(r=>r.code.startsWith('508056'));
  assert.deepEqual(glp.map(r=>r.city),['上海市']);
  assert.ok(glp.every(r=>/运营管理机构/.test(r.role)));
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

test('境外主体的原始权益人不虚构内地点位，仅以境内运营管理机构补点', () => {
  assert.deepEqual(selectLocations(registry,[],{}),[]);
  const offshore=new Set(registry.offshore.map(o=>o.code));
  for(const code of ['508056.SH','508060.SH','508078.SH','508088.SH','180306.SZ']){
    assert.ok(offshore.has(code),code+' 原始权益人境外说明需保留');
    const rows=registry.locations.filter(r=>r.code===code);
    assert.ok(rows.length>0,code+' 应有境内运营管理机构补点');
    // 这 5 只无境内原始权益人，点位只能是运营管理机构角色
    assert.ok(rows.every(r=>/运营管理机构/.test(r.role)),code+' 不得虚构原始权益人内地点位');
  }
  assert.equal(registry.unverified.length,0);
});
