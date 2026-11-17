const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const O=require('../research/operating-data.js'),D=require('../research/operating-data.json');
test('operating snapshot source and audited scope coverage',()=>{
 assert.equal(D.funds.length,103);assert.equal(D.latestPeriod,'2026Q3');assert.equal(D.source.feedsSignals,false);assert.match(D.source.sha256,/^[a-f0-9]{64}$/);assert.equal(D.quality.scopeLabelMismatches,552);
 assert.equal(D.points.filter(x=>x.sourceTable==='ops_metric').length,4651);
 assert.equal(new Set(D.points.filter(x=>x.period==='2026Q3').map(x=>x.code)).size,91);
 const ownership=new Map(D.assets.map(a=>[a.asset_id,a.code]));
 D.points.forEach(p=>{assert.ok(p.value===null||Number.isFinite(p.value));if(p.scope==='基金')assert.equal(p.asset_id,'ALL');else assert.equal(ownership.get(p.asset_id),p.code);});
});
test('only standard ops and whitelisted fund financials enter page',()=>{
 const fins=D.points.filter(x=>x.sourceTable==='financials');assert.equal(fins.length,5903);
 fins.forEach(p=>{assert.equal(p.level,'基金层面');assert.ok(['revenue','ebitda','distributable_cash'].includes(p.metric));});
 assert.ok(!('market_valuation' in D));assert.ok(!('forecast' in D));assert.ok(!('daily_quote' in D));
});
test('zero is a reported value, null and numeric strings are never coerced',()=>{
 assert.equal(O.format({value:0,unit:'万元'}),'0');assert.equal(O.format({value:null}),'未披露');assert.equal(O.format({value:'0.9'}),'未披露');assert.equal(O.format({value:.8874,unit:'小数'}),'88.74');assert.equal(O.unit({unit:'小数'}),'%');assert.equal(O.format({value:5.79,unit:'%'}),'5.79');
});
test('slice never silently carries forward or combines fund and project',()=>{
 const funds=new Map(D.funds.map(f=>[f.code,f]));const ps=O.select(D,{funds,period:'2026Q3',sector:'产业园',metric:'occupancy_rate',caliber:'期末'});assert.ok(ps.length>0);ps.forEach(p=>{assert.equal(p.period,'2026Q3');assert.equal(p.scope,'基金');assert.equal(p.caliber,'期末');assert.equal(funds.get(p.code).sector_l1,'产业园');});
 assert.deepEqual(O.select(D,{funds,period:'2099Q3',metric:'revenue'}),[]);
});
test('comparison never invents verified same-store / unknown tax is not comparable',()=>{
 assert.equal(O.compare({period:'2026Q3',tax_flag:'未说明'}).label,'不可比');
 assert.equal(O.compare({code:'x',period:'2026Q3'},[{code:'x',include_type:'扩募',include_date:'2025-08-29'}]).label,'含扩募，非同店');
 assert.equal(O.compare({code:'x',period:'2026Q3'},[{code:'x',include_type:'扩募',include_date:'nan'}]).label,'不可比');
 assert.equal(O.compare({metric:'footfall_yoy',period:'2026Q3',tax_flag:'不适用'}).label,'不可比');
 assert.equal(O.periodBounds('nan'),null);assert.equal(O.periodBounds('2026H1').end,'2026-06-30');
});
test('new tab is accessible, lazy and mirrored through existing recursive asset copy',()=>{
 const html=fs.readFileSync('index.html','utf8'),js=fs.readFileSync('research/operating-data.js','utf8'),css=fs.readFileSync('research/operating-data.css','utf8');
 assert.match(html,/data-pg="ops"/);assert.match(html,/id="pg-ops" hidden/);assert.match(html,/aria-live="polite"/);assert.match(js,/MutationObserver/);assert.match(js,/fetch\('research\/operating-data.json'\)/);assert.doesNotMatch(js,/innerHTML|REITS_DATA\s*=|REITS_ADVICE\s*=/);
 assert.match(css,/overflow:auto/);assert.match(css,/max-width:767px/);assert.match(css,/grid-template-columns:1fr/);
 for(const p of ['deploy_cf.sh','.github/workflows/daily-update.yml','.github/workflows/tenders-mirror.yml'])assert.match(fs.readFileSync(p,'utf8'),/cp -r .*research/);
});

test('financial period labels distinguish quarters from semiannual reports',()=>{assert.equal(O.caliberLabel({sourceTable:'financials',caliber:'本期',period:'2026Q3'}),'本期（单季）');assert.equal(O.caliberLabel({sourceTable:'financials',caliber:'本期',period:'2026H1'}),'本期（上半年）');assert.equal(O.caliberLabel({sourceTable:'ops_metric',caliber:'期间累计',period:'2026Q3'}),'期间累计');});
