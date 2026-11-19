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
function fixture({zero=false,mobile=false,hash='#/page/research/track/chanyeyuan',deferred=false}={}){
 const media={matches:mobile};const errors=[],timers=[],events={},entries=[hash];let index=0,currentHash=hash,resolveFetch;
 const location={};Object.defineProperty(location,'hash',{get:()=>currentHash,set:h=>{if(h!==currentHash){entries.splice(++index);entries.push(h);currentHash=h;}}});
 const window={Deno:{},addEventListener:(k,fn)=>events[k]=fn,matchMedia:()=>media,location,
  history:{pushState(_s,_t,h){location.hash=h;},replaceState(_s,_t,h){currentHash=h;entries[index]=h;}}};
 const sandbox={window,console:{error:(...a)=>errors.push(a),warn:(...a)=>errors.push(a),log(){}},setTimeout:(fn,ms)=>{timers.push({fn,ms});return timers.length;},clearTimeout(){}};
 vm.createContext(sandbox);
 vm.runInContext(fs.readFileSync('lib/echarts-custom.min.js','utf8'),sandbox);
 window.echarts.setPlatformAPI({createCanvas:canvas});window.requestAnimationFrame=fn=>fn();
 const elements={};
 function host(){
  let html='',created=[];const n={hidden:false,textContent:'',value:''};
  Object.defineProperty(n,'innerHTML',{get:()=>html,set:v=>{
   created.forEach(id=>delete elements[id]);created=[];html=v;
   for(const tag of v.matchAll(/<[^>]+\bid="([^"]+)"[^>]*>/g)){
    const id=tag[1];elements[id]=/class="track-chart/.test(tag[0])?canvas():host();
    if(zero&&elements[id].getContext)elements[id].offsetHeight=0;
    created.push(id);
   }
  }});return n;
 }
 ['v-track','pg-research','trackSectorSelect','trackSectorSwitch','trackQualityMeta','trackStats','trackUndisclosed','trackMetricPanels','trackTrendPanels','trackFundList'].forEach(id=>elements[id]=host());
 sandbox.document={getElementById:id=>elements[id],documentElement:{},defaultView:{getComputedStyle:()=>({width:'800px',height:'320px',paddingLeft:0,paddingRight:0,paddingTop:0,paddingBottom:0})}};
 sandbox.getComputedStyle=()=>({getPropertyValue:()=>''});
 const response={ok:true,json:async()=>pack};sandbox.fetch=()=>deferred?new Promise(r=>resolveFetch=()=>r(response)):Promise.resolve(response);
 vm.runInContext(fs.readFileSync('research/track-analysis.js','utf8'),sandbox);
 const instances=()=>Object.values(elements).filter(e=>e.getContext).map(e=>window.echarts.getInstanceByDom(e)).filter(Boolean);
 return {window,elements,errors,timers,events,entries,instances,setMobile(v){media.matches=v;events.resize();},resolve:()=>resolveFetch(),dispose:()=>instances().forEach(i=>i.dispose()),async go(delta){index+=delta;currentHash=entries[index];elements['v-track'].hidden=!currentHash.includes('/page/research/track');if(!elements['v-track'].hidden)await window.ReitsTrackAnalysis.applyRoute(currentHash.split('/').pop(),{fromRoute:true});}};
}
test('current sector renders all applicable metrics independently and keeps chart scheduler healthy on archive return',async()=>{
 const f=fixture({hash:'#/page/research/track/shangye'});try{
  await f.window.ReitsTrackAnalysis.mount();
  assert.equal(f.window.ReitsTrackAnalysis.sector(),'商业不动产');
  for(const metric of ['occupancy_rate','wale']){
   const chart=f.window.echarts.getInstanceByDom(f.elements['trackCompare-'+metric]);
   assert.equal(chart.getOption().series[0].type,'scatter');
   assert.ok(chart.getOption().series[0].data.every(p=>p.fund.sector==='商业不动产'));

  }
  assert.match(f.elements.trackMetricPanels.innerHTML,/出租率/);assert.match(f.elements.trackMetricPanels.innerHTML,/剩余租约期限/);
  f.setMobile(true);assert.doesNotMatch(f.elements.trackMetricPanels.innerHTML,/id="trackCompare-/);f.setMobile(false);
  f.window.ReitsTrackAnalysis.setSector('消费');
  const fixed=f.window.echarts.getInstanceByDom(f.elements['trackFixed-occupancy_rate']);
  assert.equal(fixed.getViewOfSeriesModel(fixed.getModel().getSeriesByIndex(0)).type,'bar');
  f.window.ReitsTrackAnalysis.setSector('商业不动产');
  const scatter=f.window.echarts.getInstanceByDom(f.elements['trackCompare-occupancy_rate']);
  const point=scatter.getOption().series[0].data[0];scatter.trigger('click',{data:point});
  assert.equal(f.window.location.hash,'#/detail/'+point.fund.code);
  f.elements['v-track'].hidden=true;f.instances().forEach(i=>i.dispose());
  await f.go(-1);await f.window.ReitsTrackAnalysis.mount();
  assert.equal(f.window.ReitsTrackAnalysis.sector(),'商业不动产');
  assert.match(f.elements.trackQualityMeta.textContent,/商业不动产 · 报告期 2026Q3/);
  assert.deepEqual(f.errors,[]);
 }finally{f.dispose();}
});
test('mobile uses clickable lists rather than scatter, zero-size history charts retry and n is available without labels',async()=>{
 const f=fixture({zero:true,mobile:true});try{
  await f.window.ReitsTrackAnalysis.mount();assert.equal(f.instances().length,0);
  assert.ok(f.timers.some(t=>t.ms===100));
  Object.values(f.elements).filter(e=>e.getContext).forEach(e=>e.offsetHeight=320);
  f.timers.find(t=>t.ms===100).fn();
  assert.ok(f.instances().length>0);
  assert.doesNotMatch(f.elements.trackMetricPanels.innerHTML,/id="trackCompare-/);
  assert.match(f.elements.trackMetricPanels.innerHTML,/track-rank-list/);
  assert.match(f.elements.trackFundList.innerHTML,/#\/detail\//);
  assert.doesNotMatch(f.elements.trackFundList.innerHTML,/<table/);
  const trend=f.window.echarts.getInstanceByDom(f.elements['trackTrend-occupancy_rate']).getOption();
  assert.equal(trend.series[0].label.show,false);
  assert.match(f.elements.trackTrendPanels.innerHTML,/各期覆盖数 n/);
  f.elements.trackSectorSelect.value="消费";f.elements.trackSectorSelect.onchange();
  assert.equal(f.window.location.hash,"#/page/research/track/xiaofei");
  assert.equal(f.window.ReitsTrackAnalysis.period(),"2026Q3");
  assert.deepEqual(f.errors,[]);
 }finally{f.dispose();}
});
test('sector changes create history, back/forward and refresh restore sector while report period is preserved',async()=>{
 const f=fixture();try{
  await f.window.ReitsTrackAnalysis.mount();const period=f.window.ReitsTrackAnalysis.period();
  f.window.ReitsTrackAnalysis.setSector('消费');assert.equal(f.window.location.hash,'#/page/research/track/xiaofei');
  f.window.ReitsTrackAnalysis.setSector('仓储物流');assert.equal(f.window.location.hash,'#/page/research/track/cangchu');
  assert.equal(f.window.ReitsTrackAnalysis.period(),period);
  await f.go(-1);assert.equal(f.window.ReitsTrackAnalysis.sector(),'消费');
  await f.go(1);assert.equal(f.window.ReitsTrackAnalysis.sector(),'仓储物流');
  assert.ok(f.entries.length===3);assert.deepEqual(f.errors,[]);
  const refresh=fixture({hash:f.window.location.hash});try{await refresh.window.ReitsTrackAnalysis.mount();assert.equal(refresh.window.ReitsTrackAnalysis.sector(),'仓储物流');assert.equal(refresh.entries.length,1);}finally{refresh.dispose();}
 }finally{f.dispose();}
});
test('only selected-sector core metrics appear; energy remains code-ordered individual points with no ranking or aggregate history',async()=>{
 const f=fixture();try{
  await f.window.ReitsTrackAnalysis.mount();
  assert.match(f.elements.trackMetricPanels.innerHTML,/track-rank-list/,'dense industrial points use list');
  f.window.ReitsTrackAnalysis.setSector('高速公路');
  assert.match(f.elements.trackMetricPanels.innerHTML,/日均车流/);assert.doesNotMatch(f.elements.trackMetricPanels.innerHTML,/出租率|发电量/);
  f.window.ReitsTrackAnalysis.setSector('能源');
  assert.match(f.elements.trackMetricPanels.innerHTML,/发电量/);assert.match(f.elements.trackMetricPanels.innerHTML,/利用小时/);
  assert.doesNotMatch(f.elements.trackMetricPanels.innerHTML,/可点排名|id="trackCompare-/);
  assert.doesNotMatch(f.elements.trackTrendPanels.innerHTML,/id="trackTrend-|id="trackFixed-/);
  assert.match(f.elements.trackUndisclosed.textContent,/不计算全能源中位数/);
  assert.deepEqual(f.errors,[]);
 }finally{f.dispose();}
});
test('late data completion cannot replace a detail route with a sector route',async()=>{
 const f=fixture({deferred:true});try{
  const mounted=f.window.ReitsTrackAnalysis.mount();f.window.location.hash='#/detail/180103.SZ';f.elements['v-track'].hidden=true;f.resolve();await mounted;
  assert.equal(f.window.location.hash,'#/detail/180103.SZ');assert.equal(f.instances().length,0);
 }finally{f.dispose();}
});
