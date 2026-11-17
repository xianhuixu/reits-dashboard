const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
const A=require('../research/fund-archive.js');
const base=path.join(__dirname,'../research/fund-archives');
const read=code=>JSON.parse(fs.readFileSync(path.join(base,code+'.json'),'utf8'));
const manifest=read('manifest');

test('archive export is deterministic, read-only and flags dividend conflicts (Python fixtures)',()=>{
 const out=execFileSync('python3',['-m','unittest','discover','-s','tests','-p','test_fund_archives.py'],{cwd:path.join(__dirname,'..'),encoding:'utf8'});assert.equal(typeof out,'string');
});
test('full source audit and all fund shards agree; no project/fund mixing',()=>{
 assert.equal(manifest.summary.funds,103);assert.equal(manifest.summary.financials,20507);assert.equal(manifest.summary.ops,4651);assert.equal(manifest.summary.distributionEvents,544);assert.equal(manifest.summary.scopeLabelMismatches,552);assert.equal(manifest.feedsSignals,false);assert.equal(manifest.tables.market_valuation.exported,false);assert.ok(manifest.tables.market_valuation.fields.valuation_yield);
 const totals={};for(const fund of manifest.funds){const d=read(fund.code);assert.equal(d.code,fund.code);assert.ok(!Object.hasOwn(d.tables,'market_valuation'));assert.ok(!JSON.stringify(d.tables).includes('\"valuation_yield\"'));const own=new Set(d.tables.asset.map(a=>a.asset_id));for(const [t,rs] of Object.entries(d.tables)){assert.equal(rs.length,d.coverage[t]);assert.equal(rs.length,fund.coverage[t]);totals[t]=(totals[t]||0)+rs.length;for(const r of rs)assert.equal(r.code,fund.code);}
 for(const t of ['ops_metric','financials']){for(const r of A.normalized(d,t)){assert.equal(r.scope,'基金');if(t==='ops_metric')assert.equal(r.asset_id,'ALL');}
 for(const r of d.tables[t].filter(r=>r.scope==='项目'))assert.ok(own.has(r.asset_id));}
 }
 for(const [t,n] of Object.entries(totals))assert.equal(n,manifest.tables[t].rows,t);
 assert.ok(manifest.summary.distributionConflictFields>0);
});
test('period, caliber, scope, source, tax and unit cannot form a mixed series',()=>{
 const r={metric:'revenue',asset_id:'ALL',source:'financials',period:'2026Q2',unit:'万元',caliber:'本期',tax_flag:'未说明',value:1};
 const rows=[r,{...r,period:'2026H1'},{...r,period:'2026A'},{...r,unit:'元'},{...r,caliber:'年初至今'},{...r,tax_flag:'含税'},{...r,asset_id:'A01'},{...r,source:'ops_metric'}];assert.equal(A.groupSeries(rows).length,8);
 assert.equal(A.periodLabel(r),'本期单季');assert.equal(A.periodLabel({...r,period:'2026H1'}),'上半年累计');assert.equal(A.periodLabel({...r,period:'2026A'}),'全年');
 assert.deepEqual(A.periodsBetween([{period:'2025Q3'},{period:'2026Q1'}]),['2025Q3','2025Q4','2026Q1']);
});
test('zero, missing, negative and quality flagged values remain distinct',()=>{
 assert.equal(A.visibleValue({value:0}),'0');assert.equal(A.visibleValue({value:null}),'未披露');assert.equal(A.visibleValue({value:-5}),'-5');assert.match(A.visibleValue({value:0,qualityFlags:['冲突']}),/待核.*0/);
 const rs=[{period:'2025Q1',value:1},{period:'2025Q3',value:3}];const chart=A.plot(rs,'period','value',A.periodsBetween(rs),true);assert.equal((chart.match(/polyline/g)||[]).length,4);assert.ok(!A.plot(rs,'period','value',null,false).includes('polyline'));
});
test('508008 preserves only period traffic and 180203 keeps traffic vs toll separate',()=>{
 const d=read('508008.SH'),rs=A.normalized(d,'ops_metric').filter(r=>r.period==='2026Q3');assert.equal(rs.find(r=>r.metric==='traffic_total').value,2086000);assert.ok(!rs.some(r=>r.metric==='traffic_volume'));assert.match(A.summaryCards(d),/期间车次/);assert.ok(!A.summaryCards(d).includes('日均车流'));
 const highway=read('180203.SZ'),p=A.normalized(highway,'ops_metric').filter(r=>r.period==='2026Q3');assert.equal(p.find(r=>r.metric==='traffic_volume').value,19692);assert.equal(p.find(r=>r.metric==='toll_revenue').value,13551.5);assert.match(A.summaryCards(read('508006.SH')),/营业收入/);
});
test('two priority sectors render real data; forecasts stay unit-unknown, not IRR; leverage definition stays unverified',()=>{
 for(const code of ['180103.SZ','180203.SZ']){const d=read(code),before=JSON.stringify(d);assert.match(A.operating(d),/<svg/);assert.match(A.finances(d),/季度利润与分配/);assert.match(A.finances(d),/逐笔分红/);assert.match(A.originals(d),/可供分配金额计算过程/);assert.match(A.holders(d),/主要持有人/);const a=d.tables.asset[0];assert.match(A.assetContent(d,a),/返回.*基金档案/);assert.match(A.assetContent(d,a),/当前期基金及兄弟资产对照/);assert.equal(JSON.stringify(d),before);}
 const d=read('180103.SZ');for(const k of Object.keys(d.tables))d.tables[k]=[];
 d.tables.forecast=[{code:d.code,year:2027,metric:'distributable_cash',value:12345,scenario:'首发',start_month:1,end_month:12}];
 const before=JSON.stringify(d),forecastOnly=A.finances(d);assert.match(forecastOnly,/无单位字段/);assert.match(forecastOnly,/>12345<\/td>/);assert.doesNotMatch(forecastOnly,/<svg|IRR|达成率[^。]*[0-9]/);assert.equal(JSON.stringify(d),before);
 d.tables.forecast=[];d.tables.financials=[{code:d.code,scope:'基金',asset_id:'ALL',metric:'leverage_ratio',period:'2025A',caliber:'期末',unit:'倍',value:1.75,tax_flag:'不适用'}];
 const leverage=A.finances(d);assert.match(leverage,/原始杠杆字段，定义待核/);assert.match(leverage,/1.75/);assert.match(leverage,/倍（源表单位，定义待核）/);assert.doesNotMatch(leverage,/权益乘数|LTV|贷款价值比|抵押率/);assert.equal(d.tables.financials[0].value,1.75);assert.equal(d.tables.financials[0].unit,'倍');
});
test('zero financial distributions are flagged, never plotted as zero event payments',()=>{
 let count=0;for(const fund of manifest.funds){const d=read(fund.code);for(const r of d.tables.financials.filter(r=>r.qualityFlags)){assert.equal(r.value,0);assert.match(A.visibleValue(r),/待核/);count++;}}
 assert.equal(count,manifest.summary.distributionConflictFields);const d=read('180103.SZ');const actual=A.normalized(d,'financials').filter(r=>['actual_distribution','dps_actual'].includes(r.metric));assert.ok(actual.length>0);const html=A.finances(d);assert.match(html,/财务报表分派金额（非事件）/);assert.match(html,/除息日/);assert.match(html,/登记日/);assert.match(html,/支付日/);assert.match(html,/无单位字段/);
});
test('detail and asset routes validate, lazy cache reads once and never writes signals',async()=>{
 assert.deepEqual(A.parseRoute('#/detail/180103.SZ/asset/180103.SZ-A02'),{code:'180103.SZ',asset:'180103.SZ-A02'});assert.equal(A.parseRoute('#/detail/../../etc'),null);assert.equal(A.parseRoute('#/detail/180103.SZ/asset/%FF'),null);assert.equal(A.parseRoute('#/detail/180103.SZ/asset/x/other'),null);
 let calls=0;const payload={schemaVersion:1,code:'999999.SH',tables:{}};const fetcher=async url=>{calls++;assert.equal(url,'research/fund-archives/999999.SH.json');return {ok:true,json:async()=>payload};};const one=A.load('999999.SH',fetcher),two=A.load('999999.SH',fetcher);assert.equal(one,two);assert.equal(await one,payload);assert.equal(calls,1);
 const js=fs.readFileSync(path.join(__dirname,'../research/fund-archive.js'),'utf8');assert.ok(!/REITS_DATA\s*[.=]|localStorage|POST|PUT|PATCH/.test(js));const app=fs.readFileSync(path.join(__dirname,'../app.js'),'utf8');assert.match(app,/ReitsFundArchive.mount\(archiveHost, r.code\)/);assert.match(app,/fa-legacy/);const ops=fs.readFileSync(path.join(__dirname,'../research/operating-data.js'),'utf8');assert.match(ops,/archiveLink.href='#\/detail\//);
});
test('responsive archive has local table scroll, nonsticky mobile identity and keyboard controls',()=>{
 const css=fs.readFileSync(path.join(__dirname,'../research/fund-archive.css'),'utf8');assert.match(css,/@media\(max-width:760px\)/);assert.match(css,/\.fa-identity\{position:static/);assert.match(css,/\.fa-scroll\{overflow:auto/);assert.match(css,/scroll-margin-top/);assert.match(css,/focus-visible/);const js=fs.readFileSync(path.join(__dirname,'../research/fund-archive.js'),'utf8');assert.match(js,/aria-pressed/);assert.match(js,/target.isConnected/);assert.match(js,/重试载入/);
});
// Small DOM contract fixture (not a browser and not a visual acceptance test).
class Region {
 constructor(){this.dataset={};this.isConnected=true;this.buttons=[];this.html='';}
 set innerHTML(html){this.html=html;if(html.includes('class="fa-body"'))this.body=new Region();if(html.includes('id="fa-content"')){this.content=new Region();this.buttons=[...html.matchAll(/data-fa-tab="([^"]+)"/g)].map(m=>({dataset:{faTab:m[1]},setAttribute(k,v){this[k]=v;}}));}}
 get innerHTML(){return this.html;}
 querySelector(s){if(s==='.fa-body')return this.body;if(s==='#fa-content')return this.content;return null;}
 querySelectorAll(s){return s==='[data-fa-tab]'?this.buttons:[];}
}
test('mount opens real fund panels and asset route, without preloading other funds',async()=>{
 const oldFetch=global.fetch,oldLocation=global.location;let calls=0;
 try{global.fetch=async url=>{calls++;return {ok:true,json:async()=>read(path.basename(url,'.json'))};};global.location={hash:'#/detail/180103.SZ'};const host=new Region();await A.mount(host,'180103.SZ');assert.match(host.innerHTML,/单只基金研究档案/);assert.match(host.body.content.innerHTML,/<svg/);const nav=host.body.buttons;assert.equal(nav.length,5);nav.find(b=>b.dataset.faTab==='finance').onclick();assert.match(host.body.content.innerHTML,/逐笔分红/);nav.find(b=>b.dataset.faTab==='assets').onclick();assert.match(host.body.content.innerHTML,/#\/detail\/180103.SZ\/asset\//);assert.equal(calls,1);
 global.location.hash='#/detail/180103.SZ/asset/180103.SZ-A02';const project=new Region();await A.mount(project,'180103.SZ');assert.match(project.body.innerHTML,/当前资产报告期/);assert.match(project.body.innerHTML,/返回.*基金档案/);assert.equal(calls,1);
 global.location.hash='#/detail/180103.SZ/asset/180203.SZ-A01';const wrong=new Region();await A.mount(wrong,'180103.SZ');assert.match(wrong.body.innerHTML,/资产ID不属于该基金/);
 }finally{global.fetch=oldFetch;global.location=oldLocation;}
});

test('composition with missing unit or overlap evidence produces no graph and retains every original value',()=>{
 const d=read('180103.SZ');
 for(const f of [d,read('180203.SZ')]){const html=A.composition(f);assert.doesNotMatch(html,/<svg|<rect|<polyline/);assert.match(html,/未生成构成图/);assert.match(html,/分项不重叠/);}
 d.tables.revenue_breakdown=[{company:'同主体',period:'2026Q3',item:'收入合计',value:1.234567891234567},{company:'同主体',period:'2026Q3',item:'收入子项',value:0.00000000123456789}];
 d.tables.cost_breakdown=[{company:'同主体',period:'2026Q3',item:'费用',unit:'万元',value:17.25}];
 const before=JSON.stringify(d),html=A.composition(d);assert.doesNotMatch(html,/<svg|<rect/);assert.ok(html.includes(String(d.tables.revenue_breakdown[0].value)));assert.ok(html.includes(String(d.tables.revenue_breakdown[1].value)));assert.match(html,/17.25/);assert.match(html,/收入合计/);assert.match(html,/收入子项/);assert.equal(JSON.stringify(d),before);
});
test('main-view precision is metric-aware while original tables retain full numeric precision',()=>{
 assert.equal(A.displayNumber(1234.56789,{metric:'revenue',unit:'万元'}),'1,234.57');
 assert.equal(A.displayNumber(97.12345,{metric:'occupancy_rate',unit:'%'}),'97.12');
 assert.equal(A.displayNumber(2.7182818,{metric:'close',unit:'元'}),'2.718');
 assert.equal(A.displayNumber(.0274,{metric:'dps_pretax',unit:'元/份'}),'0.0274');
 assert.equal(A.displayNumber(.2,{metric:'dps_distributable',unit:'元/份'}),'0.2000');
 assert.equal(A.displayNumber(2086000,{metric:'traffic_total',unit:'车次'}),'2,086,000');
 assert.equal(A.displayNumber(19692.125,{metric:'traffic_volume',unit:'车次/日'}),'19,692.13');
 assert.notEqual(A.displayNumber(.000000001,{metric:'revenue',unit:'万元'}),'0.00');
 assert.notEqual(A.displayNumber(.00000000000001,{metric:'dps_pretax',unit:'元/份'}),'0.0000');
 const value=1.234567891234567,raw=A.table([{period:'2026Q3',value}],['period','value'],'完整精度');assert.ok(raw.includes('>'+String(value)+'</td>'));assert.equal(A.rawValue(value),String(value));
});
test('original tables use one semantic sticky row header and never pin every body cell',()=>{
 const html=A.table([{period:'2026Q3',value:1.12345678912345,unit:'万元'}],['period','value','unit'],'原表');
 assert.match(html,/<th scope="row" class="fa-row-key">2026Q3<\/th>/);assert.equal((html.match(/scope="row"/g)||[]).length,1);assert.equal((html.match(/<td/g)||[]).length,2);assert.ok(!/<td[^>]*fa-row-key/.test(html));
 const css=fs.readFileSync(path.join(__dirname,'../research/fund-archive.css'),'utf8');assert.match(css,/\.fa-scroll tbody \.fa-row-key\{position:sticky;left:0/);assert.ok(!css.includes('.fa-scroll tbody th{position:sticky'));assert.match(css,/\.fa-scroll thead \.fa-row-key\{left:0;z-index:3/);assert.match(css,/font-weight:400;white-space:normal;overflow-wrap:anywhere/);assert.match(css,/max-width:150px/);
 const d=read('180103.SZ'),matrix=A.financialMatrix(A.normalized(d,'financials'));assert.match(matrix,/scope="row" class="fa-row-key"/);
});
