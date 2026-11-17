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
 assert.equal(O.format({value:0,unit:'万元'}),'0');assert.equal(O.format({value:null}),'尚未披露');assert.equal(O.format({value:'0.9'}),'尚未披露');assert.equal(O.format({value:.8874,unit:'小数'}),'88.74');assert.equal(O.unit({unit:'小数'}),'%');assert.equal(O.format({value:5.79,unit:'%'}),'5.79');assert.equal(O.format({value:0.92,unit:'小数'}),'92.00');assert.equal(O.format({value:13551.5,unit:'万元'}),'13,551.50');assert.equal(O.format({value:19692,unit:'车次/日'}),'19,692');
});
test('slice never silently carries forward or combines fund and project',()=>{
 const funds=new Map(D.funds.map(f=>[f.code,f]));const ps=O.select(D,{funds,period:'2026Q3',sector:'产业园',metric:'occupancy_rate',caliber:'期末'});assert.ok(ps.length>0);ps.forEach(p=>{assert.equal(p.period,'2026Q3');assert.equal(p.scope,'基金');assert.equal(p.caliber,'期末');assert.equal(funds.get(p.code).sector_l1,'产业园');});
 assert.deepEqual(O.select(D,{funds,period:'2099Q3',metric:'revenue'}),[]);
});
test('comparison never invents verified same-store / unknown tax is not comparable',()=>{
 assert.equal(O.compare({period:'2026Q3',metric:'occupancy_rate',tax_flag:'不适用'}).label,'待核资产范围');
 assert.equal(O.compare({period:'2026Q3',metric:'traffic_volume',tax_flag:'不适用'}).label,'待核资产范围');
 assert.equal(O.compare({period:'2026Q3',metric:'avg_rent',tax_flag:'未说明'}).label,'不可比');
 assert.equal(O.compare({code:'x',period:'2026Q3',metric:'occupancy_rate'},[{code:'x',include_type:'扩募',include_date:'2025-08-29'}]).label,'含扩募，非同店');
 assert.equal(O.compare({code:'x',period:'2026Q3',metric:'occupancy_rate'},[{code:'x',include_type:'扩募',include_date:'nan'}]).label,'待核资产范围');
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

test('fund pagination uses 20 unique funds, clamps pages and preserves source',()=>{
 const funds=Array.from({length:103},(_,i)=>({code:String(i)}));
 const first=O.paginate(funds,1),last=O.paginate(funds,6),beyond=O.paginate(funds,100);
 assert.equal(first.items.length,20);assert.equal(first.pages,6);assert.equal(first.start,1);assert.equal(first.end,20);
 assert.equal(last.items.length,3);assert.equal(last.start,101);assert.equal(last.end,103);assert.equal(beyond.page,6);
 assert.equal(O.paginate(funds,-1).page,1);assert.equal(O.paginate([],9).start,0);assert.equal(O.paginate([],9).end,0);
 assert.equal(O.paginate(funds.slice(0,2),6).page,1);assert.equal(funds.length,103);
 assert.deepEqual(Array.from({length:6},(_,i)=>O.paginate(funds,i+1).items).flat(),funds);
});
test('reading contracts keep pagination outside scroll and details under selected row',()=>{
 const html=fs.readFileSync('index.html','utf8'),js=fs.readFileSync('research/operating-data.js','utf8'),css=fs.readFileSync('research/operating-data.css','utf8');
 assert.match(html,/id="opsPrev"/);assert.match(html,/id="opsNext"/);assert.match(html,/id="opsPageStatus" role="status"/);assert.doesNotMatch(html,/id="opsDetail"/);
 assert.match(js,/paginate\(fs,pageNumber,20\)/);assert.match(js,/if\(keepPage!==true\)pageNumber=1/);assert.match(js,/row\.after\(expanded\)/);assert.match(js,/aria-expanded/);assert.match(js,/trigger\.focus\(\)/);assert.match(js,/scrollLeft=0/);assert.doesNotMatch(js,/\$\('opsDetail'\)/);
 assert.match(css,/position:sticky;left:0/);assert.match(css,/position:sticky;top:0/);assert.match(css,/text-align:right/);assert.match(js,/ops-num/);assert.match(css,/ops-mobile-value/);assert.match(css,/ops-mobile-open/);
 assert.doesNotMatch(css,/100vw/);assert.match(css,/container-type:inline-size/);assert.match(css,/100cqw/);assert.match(css,/.ops-expanded-row>td{[^}]*max-width:0/);
});

test('all-sector default uses core metrics and distinguishes inapplicable from undisclosed',()=>{
 const funds=new Map(D.funds.map(f=>[f.code,f]));
 const highway=D.funds.find(f=>f.code==='180201.SZ');
 const park=D.funds.find(f=>f.code==='180103.SZ');
 const cainiao=D.funds.find(f=>f.code==='180307.SZ');
 const unlisted=D.funds.find(f=>f.code==='180107.SZ');
 assert.equal(O.coreMetric('交通'),'traffic_volume');
 assert.equal(O.coreMetric('能源'),'power_generation');
 assert.equal(O.coreMetric('产业园'),'occupancy_rate');
 assert.equal(O.metricApplies('occupancy_rate','交通'),false);
 assert.equal(O.metricApplies('occupancy_rate','产业园'),true);
 assert.equal(O.vacancyLabel(highway,'occupancy_rate',null),'该指标不适用');
 assert.equal(O.vacancyLabel(cainiao,'occupancy_rate',null),'尚未披露');
 assert.equal(O.vacancyLabel(unlisted,'occupancy_rate',null),'尚未披露');
 const core={funds,period:'2026Q3',sector:'',metric:'__core__',caliber:'__auto__'};
 const hv=O.rowView(D,core,highway),pv=O.rowView(D,core,park);
 assert.equal(hv.metric,'traffic_volume');assert.equal(hv.point.value,157800);assert.equal(hv.vacancy,'');
 assert.equal(O.unit(hv.point),'车次/日');
 assert.equal(pv.metric,'occupancy_rate');assert.ok(pv.point&&Number.isFinite(pv.point.value));
 const occ={funds,period:'2026Q3',sector:'',metric:'occupancy_rate',caliber:'期末'};
 assert.equal(O.rowView(D,occ,highway).vacancy,'该指标不适用');
 assert.equal(O.compare({metric:'footfall_yoy',period:'2026Q3',tax_flag:'不适用'}).label,'不可比');
});

test('highway core metric falls back to period traffic without converting into daily average',()=>{
 const funds=new Map(D.funds.map(f=>[f.code,f]));
 const core={funds,period:'2026Q3',sector:'',metric:'__core__',caliber:'__auto__'};
 const tie=D.funds.find(f=>f.code==='508008.SH');
 const zhao=D.funds.find(f=>f.code==='180203.SZ');
 const tv=O.rowView(D,core,tie), zv=O.rowView(D,core,zhao);
 assert.equal(tv.metric,'traffic_total');assert.equal(tv.point.value,2086000);assert.equal(tv.point.unit,'车次');assert.equal(tv.vacancy,'');
 assert.notEqual(tv.metric,'traffic_volume');
 assert.equal(zv.metric,'traffic_volume');assert.equal(zv.point.value,19692);assert.equal(zv.point.unit,'车次/日');
});
