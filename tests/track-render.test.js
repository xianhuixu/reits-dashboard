// CPU-only integration with the actual generated ECharts bundle, not a chart API stub.
// Canvas drawing is a no-op; this verifies series registration/scheduler and lifecycle,
// not browser geometry, pixel layout or design acceptance.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const pack=JSON.parse(fs.readFileSync('research/track-analysis.json','utf8'));
function canvas(){
 const attrs={};
 const ctx=new Proxy({measureText:t=>({width:String(t).length*7}),createLinearGradient:()=>({addColorStop(){}}),createRadialGradient:()=>({addColorStop(){}}),getLineDash:()=>[]},{get(t,k){return k in t?t[k]:()=>{};}});
 return {nodeName:'CANVAS',style:{},width:800,height:320,offsetWidth:800,offsetHeight:320,getContext:()=>ctx,setAttribute:(k,v)=>attrs[k]=v,getAttribute:k=>attrs[k]};
}
function fixture({zero=false,mobile=false}={}){
 const errors=[],timers=[],events={};
 const window={Deno:{},addEventListener:(k,fn)=>events[k]=fn,matchMedia:()=>({matches:mobile}),location:{hash:'#/page/research/track'}};
 const sandbox={window,console:{error:(...a)=>errors.push(a),warn:(...a)=>errors.push(a),log(){}},setTimeout:(fn,ms)=>{timers.push({fn,ms});return timers.length;},clearTimeout(){}};
 vm.createContext(sandbox);
 vm.runInContext(fs.readFileSync('lib/echarts-custom.min.js','utf8'),sandbox);
 window.echarts.setPlatformAPI({createCanvas:canvas});
 window.requestAnimationFrame=fn=>fn();
 const ids=['trackMedianChart','trackDispersionChart','trackTrendChart','trackFixedChart'];
 const elements={};ids.forEach(id=>{elements[id]=canvas();if(zero)elements[id].offsetHeight=0;});
 ['v-track','pg-research','trackQualityMeta','trackMetricSwitch','trackSectorSwitch','trackSampleNote','trackStats','trackTrendNote','trackFixedNote','trackFundTable','trackQualityTable','trackUndisclosed','trackFixedTable','trackTrendTable'].forEach(id=>elements[id]={hidden:false,innerHTML:'',textContent:''});
 sandbox.document={getElementById:id=>elements[id],documentElement:{},defaultView:{getComputedStyle:()=>({width:'800px',height:'320px',paddingLeft:0,paddingRight:0,paddingTop:0,paddingBottom:0})}};
 sandbox.getComputedStyle=()=>({getPropertyValue:()=>''});
 sandbox.fetch=async()=>({ok:true,json:async()=>pack});
 vm.runInContext(fs.readFileSync('research/track-analysis.js','utf8'),sandbox);
 const instances=()=>ids.map(id=>window.echarts.getInstanceByDom(elements[id])).filter(Boolean);
 return {window,elements,ids,errors,timers,events,instances,dispose:()=>instances().forEach(i=>i.dispose())};
}
test('real bundle registers bar; initial render and fund-archive return retain all four operating charts',async()=>{
 const f=fixture();try{
  await f.window.ReitsTrackAnalysis.mount();
  assert.equal(f.instances().length,4, f.errors.map(a=>a.map(e=>e.stack||String(e)).join(" ")).join("\n"));
  const median=f.window.echarts.getInstanceByDom(f.elements.trackMedianChart);
  assert.equal(median.getViewOfSeriesModel(median.getModel().getSeriesByIndex(0)).type,'bar');
  const fixed=f.window.echarts.getInstanceByDom(f.elements.trackFixedChart);
  assert.equal(fixed.getOption().series[0].type,'bar');
  f.window.ReitsTrackAnalysis.setSector('消费');
  const scatter=f.window.echarts.getInstanceByDom(f.elements.trackDispersionChart);
  const first=scatter.getOption().series[0].data[0];
  scatter.trigger('click',{data:first});
  assert.equal(f.window.location.hash,'#/detail/'+first.fund.code);
  f.elements['v-track'].hidden=true;f.window.ReitsTrackAnalysis.render();
  // Fund archive may dispose chart objects. The cached track instances must be recreated.
  f.instances().forEach(i=>i.dispose());
  f.elements['v-track'].hidden=false;
  await f.window.ReitsTrackAnalysis.mount();await f.window.ReitsTrackAnalysis.mount();
  assert.equal(f.instances().length,4, f.errors.map(a=>a.map(e=>e.stack||String(e)).join(" ")).join("\n"));
  assert.match(f.elements.trackQualityMeta.textContent,/消费 · 报告期 2026Q3/);
  assert.equal(f.window.ReitsTrackAnalysis.sector(),'消费');
  assert.doesNotMatch(f.elements.trackQualityMeta.textContent,/getProgressNote|暂不可用|失败/);
  assert.deepEqual(f.errors,[]);
 }finally{f.dispose();}
});
test('zero-size mount retries after layout is ready, and mobile hides overlapping n labels but retains coverage table',async()=>{
 const f=fixture({zero:true,mobile:true});try{
  await f.window.ReitsTrackAnalysis.mount();assert.equal(f.instances().length,0);
  assert.ok(f.timers.some(t=>t.ms===100),'zero-size rendering schedules a retry');
  f.ids.forEach(id=>f.elements[id].offsetHeight=320);
  f.timers.find(t=>t.ms===100).fn();
  assert.equal(f.instances().length,4, f.errors.map(a=>a.map(e=>e.stack||String(e)).join(" ")).join("\n"));
  const trend=f.window.echarts.getInstanceByDom(f.elements.trackTrendChart).getOption();
  assert.equal(trend.series[0].label.show,false);
  assert.match(f.elements.trackTrendTable.innerHTML,/2026Q3/);
  assert.match(f.elements.trackTrendTable.innerHTML,/各期覆盖数 n/);
  assert.match(f.elements.trackQualityTable.innerHTML,/本期无匹配口径数据/);
  f.window.ReitsTrackAnalysis.setSector('消费');
  assert.match(f.elements.trackUndisclosed.textContent,/508607.SH 期后上市（2026-11-04）/);
  assert.deepEqual(f.errors,[]);
 }finally{f.dispose();}
});
test('energy selector shows individual points only and no full-energy median, trend or fixed-sample ranking',async()=>{
 const f=fixture();try{
  await f.window.ReitsTrackAnalysis.mount();f.window.ReitsTrackAnalysis.setSector('能源');f.window.ReitsTrackAnalysis.setMetric('power_generation');
  const option=id=>f.window.echarts.getInstanceByDom(f.elements[id]).getOption();
  assert.ok(!option('trackMedianChart').yAxis[0].data.includes('能源'));
  assert.ok(option('trackDispersionChart').series[0].data.some(p=>p.fund.sector==='能源'));
  assert.equal(f.elements.trackTrendChart.hidden,true);
  assert.equal(f.elements.trackFixedChart.hidden,true);
  assert.match(f.elements.trackUndisclosed.textContent,/不计算全能源中位数/);
  assert.deepEqual(f.errors,[]);
 }finally{f.dispose();}
});

test('sector chips scope current scatter, trend, fixed sample and detail to one sector and only expose applicable metrics', async()=>{
 const f=fixture();try{
  await f.window.ReitsTrackAnalysis.mount();
  for(const sector of ['产业园','消费','商业不动产','仓储物流','保租房','高速公路']){
   f.window.ReitsTrackAnalysis.setSector(sector);
   assert.equal(f.window.ReitsTrackAnalysis.sector(),sector);
   const instance=id=>f.window.echarts.getInstanceByDom(f.elements[id]);
   const dots=instance('trackDispersionChart').getOption().series[0].data;
   assert.ok(dots.length>0);assert.ok(dots.every(p=>p.fund.sector===sector));
   const trends=instance('trackTrendChart').getOption().series;
   assert.ok(trends.every(s=>s.name===sector));
   assert.match(f.elements.trackFundTable.innerHTML,/查看当前赛道基金原值/);
  }
  assert.equal(f.window.ReitsTrackAnalysis.metric(),'traffic_volume');
  assert.doesNotMatch(f.elements.trackMetricSwitch.innerHTML,/出租率|发电量/);
  f.window.ReitsTrackAnalysis.setMetric('occupancy_rate');
  assert.equal(f.window.ReitsTrackAnalysis.metric(),'traffic_volume','inapplicable metrics cannot be selected');
  assert.deepEqual(f.errors,[]);
 }finally{f.dispose();}
});
