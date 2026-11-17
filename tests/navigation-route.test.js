/* Node-only routing regression tests, not browser/visual acceptance. */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('app.js','utf8');
const start=source.indexOf('  var lastDetailRoute =');
const end=source.indexOf('  // ---- 导航事件绑定',start);
function fixture(hash='#/detail/180103.SZ/asset/a01'){
 const calls=[],entries=[hash];let index=0;
 const location={hash};const active={pano:'heatmap',research:'detail'};
 const allowed={pano:['heatmap','news','proj-ndrc'],research:['detail','review']};
 const history={pushState(_s,_t,h){entries.splice(++index);entries.push(h);location.hash=h;}};
 const document={querySelector(q){let m=q.match(/^#(pano|research)Sub button\.on$/);if(m)return {dataset:{v:active[m[1]]}};
 m=q.match(/^#(pano|research)Sub button\[data-v="([\w-]+)"\]$/);if(m&&allowed[m[1]].includes(m[2]))return {dataset:{v:m[2]}};
 if(q==='#subbar button[data-scroll="advRisk"]')return {parentElement:{querySelectorAll(){return [];}}};return null;},getElementById(id){return {id};}};
 const ctx={location,history,document,window:{ReitsWorkspace:{selectAdviceForTarget(t){calls.push(['section',t.id]);}}},showPage(pg){calls.push(['page',pg]);},switchView(v){calls.push(['view',v]);},openReitDetail(code,update){calls.push(['detail',code,update,location.hash]);},setActiveNav(){}};
 vm.createContext(ctx);vm.runInContext(source.slice(start,end),ctx);
 return {ctx,calls,entries,location,active,go(delta){index+=delta;location.hash=entries[index];ctx.restoreNavigationRoute();}};
}
test('detail to overview writes an overview route, deduplicates touch/click, and refresh restores it',()=>{
 const f=fixture();const btn={dataset:{pg:'pano'}};f.ctx.syncNavigationRoute(btn);f.ctx.syncNavigationRoute(btn);
 assert.equal(f.location.hash,'#/page/pano/heatmap');assert.equal(f.entries.length,2);
 f.ctx.restoreNavigationRoute();assert.deepEqual(f.calls,[['page','pano'],['view','heatmap']]);
});
test('back restores the exact asset route, forward restores overview without growing history',()=>{
 const f=fixture();f.ctx.syncNavigationRoute({dataset:{pg:'pano'}});f.go(-1);
 assert.deepEqual(f.calls.pop(),['detail','180103.SZ',false,'#/detail/180103.SZ/asset/a01']);
 f.go(1);assert.deepEqual(f.calls,[['page','pano'],['view','heatmap']]);assert.equal(f.entries.length,2);
});
test('fund entry uses push history rather than replacing the previous page',()=>{
 const f=fixture('#/page/pano/heatmap');f.ctx.writeRoute('#/detail/180203.SZ');f.go(-1);
 assert.equal(f.location.hash,'#/page/pano/heatmap');assert.deepEqual(f.calls,[['page','pano'],['view','heatmap']]);
 assert.equal((source.match(/writeRoute\("#\/detail\/" \+ code\)/g)||[]).length,2);
});
test('all top-level destinations and research/advice sections restore their own routes',()=>{
 for(const pg of ['pano','research','advice','ops','inst']){
  const f=fixture();if(pg==='research')f.ctx.syncNavigationRoute({dataset:{pg:'pano'}});f.ctx.syncNavigationRoute({dataset:{pg:'research'}});assert.equal(f.location.hash,'#/detail/180103.SZ/asset/a01');
 f.active.research='review';f.ctx.syncNavigationRoute({dataset:{pg}});f.ctx.restoreNavigationRoute();assert.equal(f.calls[0][1],pg);
 }
 const f=fixture();f.ctx.syncNavigationRoute({dataset:{pg:'advice',scroll:'advRisk'}});f.ctx.restoreNavigationRoute();assert.deepEqual(f.calls,[['page','advice'],['section','advRisk']]);
});
test('root restores overview, invalid routes and existing research anchors remain untouched',()=>{
 for(const hash of ['','#']){const f=fixture(hash);f.ctx.restoreNavigationRoute();assert.deepEqual(f.calls,[['page','pano'],['view','heatmap']]);}
 for(const hash of ['#advRisk','#/page/pano/not-a-view','#/page/unknown']){const f=fixture(hash);f.ctx.restoreNavigationRoute();assert.equal(f.calls.length,0);}
});
test('research tab keeps an existing fund/asset detail URL instead of discarding it',()=>{
 const f=fixture();f.ctx.syncNavigationRoute({dataset:{pg:'research'}});assert.equal(f.entries.length,1);
 f.ctx.syncNavigationRoute({dataset:{pg:'pano'}});f.ctx.syncNavigationRoute({dataset:{pg:'research'}});assert.equal(f.location.hash,'#/detail/180103.SZ/asset/a01');
 f.active.research='review';f.ctx.syncNavigationRoute({dataset:{v:'review'}});assert.equal(f.location.hash,'#/page/research/review');
});
test('a delayed data load cannot reopen detail after the user has navigated away',()=>{
 const a=source.indexOf('  function openReitDetail(code, updateHash)');const b=source.indexOf('  function openReitDetailInner(',a);
 let ready,opened=0;const location={hash:'#/detail/180103.SZ'};
 const ctx={location,withResearchData(fn){ready=fn;},openReitDetailInner(){opened++;}};vm.createContext(ctx);vm.runInContext(source.slice(a,b),ctx);
 ctx.openReitDetail('180103.SZ',false);location.hash='#/page/pano/heatmap';ready();assert.equal(opened,0);
 ctx.openReitDetail('180203.SZ');ready();assert.equal(opened,1);
 assert.match(source,/if \(location.hash !== renderingHash\) return;/);
});
test('router listens to back/forward and hash links; both navigation event paths share synchronization',()=>{
 assert.match(source,/addEventListener\("popstate", restoreNavigationRoute\)/);assert.match(source,/addEventListener\("hashchange", restoreNavigationRoute\)/);
 const binding=source.slice(source.indexOf('  function bindNavButton('),source.indexOf('  // 绑定所有导航按钮'));
 assert.equal((binding.match(/syncNavigationRoute\(btn\)/g)||[]).length,3);assert.match(binding,/btn.addEventListener\("touchend"/);
 assert.match(fs.readFileSync('index.html','utf8'),/app.js\?v=20261117-navigation/);
});
