/* Node-only DOM contracts. No browser, geometry or visual acceptance claims. */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../page-agent-loader.js'),'utf8');
function sourceFunction(name,next){return source.slice(source.indexOf('  function '+name+'('),source.indexOf(next,source.indexOf('  function '+name+'('))).trim();}
class Classes{
 constructor(){this.set=new Set();}add(x){this.set.add(x);}remove(x){this.set.delete(x);}contains(x){return this.set.has(x);}toggle(x,on){if(on===undefined)on=!this.set.has(x);on?this.add(x):this.remove(x);return on;}
}
class Node{
 constructor(tag='div'){this.tagName=tag;this.children=[];this.parentNode=null;this.classList=new Classes();this.hidden=false;this.attributes={};this.listeners={};}
 get firstChild(){return this.children[0]||null;}
 appendChild(n){return this.insertBefore(n,null);}
 insertBefore(n,before){n.remove();const i=before?this.children.indexOf(before):this.children.length;this.children.splice(i,0,n);n.parentNode=this;return n;}
 remove(){if(this.parentNode){const a=this.parentNode.children;a.splice(a.indexOf(this),1);this.parentNode=null;}}
 setAttribute(k,v){this.attributes[k]=v;}
 addEventListener(k,fn){this.listeners[k]=fn;}
 querySelector(selector){const id=selector.slice(1);for(const c of this.children){if(c.id===id)return c;const found=c.querySelector(selector);if(found)return found;}return null;}
}
function fixture({mobile=true,pageHidden=false,detailHidden=false,archive=true}={}){
 const root=new Node('html'),body=new Node('body'),head=new Node('head');root.appendChild(head);root.appendChild(body);
 const document={documentElement:root,body,head,createElement:tag=>new Node(tag),getElementById:id=>root.querySelector('#'+id)};
 const make=(id,parent)=>{const n=new Node();n.id=id;parent.appendChild(n);return n;};
 const page=make('pg-research',body),view=make('v-detail',page),host=make('detailPanel',view);page.hidden=pageHidden;view.hidden=detailHidden;
 if(archive)make('fundArchive',host);
 const wrap=make('rdAiWrap',body),gear=make('rdAiGear',wrap),button=make('rdAiLauncher',wrap),panel=make('page-agent-runtime_agent-panel',body),card=make('rdAiCard',body);card.hidden=true;
 const events={},media={matches:mobile,addEventListener(k,fn){events.media=fn;}};const watched=[];let observerCallback;
 const window={matchMedia:q=>{assert.equal(q,'(max-width:640px)');return media;},addEventListener(k,fn){events[k]=fn;}};
 class MutationObserver{constructor(fn){observerCallback=fn;}observe(el,options){watched.push({el,options});}}
 const ctx={document,window,MutationObserver};
 const install=vm.runInNewContext('('+sourceFunction('installArchiveDock','  function buildCard(')+')',ctx);
 const controller=install(wrap);
 const inject=vm.runInNewContext('('+sourceFunction('injectStyles','  var gearBtn =')+')',ctx);inject();
 return {root,document,body,page,view,host,wrap,gear,button,panel,card,media,events,watched,controller,make,ctx,mutate:()=>observerCallback(),css:document.getElementById('rdAiStyles').textContent};
}

test('mobile fund and asset details get an in-flow toolbar before the archive, including delayed loader start',()=>{
 for(const route of ['#/detail/180103.SZ','#/detail/180103.SZ/asset/180103.SZ-A02']){
  const f=fixture();f.ctx.window.location={hash:route};f.controller.sync();
  const dock=f.document.getElementById('rdAiArchiveDock');assert.equal(dock.parentNode,f.host);assert.equal(f.host.firstChild,dock);assert.equal(f.wrap.parentNode,dock);assert.equal(dock.attributes['aria-label'],'档案辅助工具');assert.ok(f.wrap.classList.contains('rd-ai-archive-docked'));assert.ok(f.root.classList.contains('rd-ai-archive-mobile'));
  assert.match(f.css,/html\.rd-ai-archive-mobile #rdAiWrap\.rd-ai-archive-docked\{position:static;inset:auto/);
 }
});
test('leaving detail or resizing to desktop restores the original live launcher and listeners',()=>{
 const f=fixture(),button=f.button,gear=f.gear;const click=()=>{};button.addEventListener('click',click);
 f.media.matches=false;f.events.media();assert.equal(f.wrap.parentNode,f.body);assert.ok(!f.root.classList.contains('rd-ai-archive-mobile'));assert.equal(f.document.getElementById('rdAiArchiveDock'),null);
 f.media.matches=true;f.events.media();assert.notEqual(f.wrap.parentNode,f.body);
 f.page.hidden=true;f.mutate();assert.equal(f.wrap.parentNode,f.body);f.page.hidden=false;f.view.hidden=true;f.mutate();assert.equal(f.wrap.parentNode,f.body);
 f.view.hidden=false;f.view.classList.add('hidden');f.mutate();assert.equal(f.wrap.parentNode,f.body);f.view.classList.remove('hidden');f.mutate();assert.notEqual(f.wrap.parentNode,f.body);
 assert.equal(f.document.getElementById('rdAiLauncher'),button);assert.equal(f.document.getElementById('rdAiGear'),gear);assert.equal(button.listeners.click,click);
 assert.match(f.css,/#rdAiWrap\{position:fixed/);assert.match(f.css,/top:72px/);assert.match(f.css,/@media \(max-width:640px\)\{#rdAiWrap\{top:auto;bottom:max\(16px/);
});
test('fund-to-asset host replacement reattaches the same controls without duplicated docks',()=>{
 const f=fixture(),wrap=f.wrap;while(f.host.firstChild)f.host.firstChild.remove();f.make('fundArchive',f.host);f.mutate();
 assert.equal(f.document.getElementById('rdAiWrap'),wrap);assert.equal(wrap.parentNode,f.document.getElementById('rdAiArchiveDock'));assert.equal(f.host.children.filter(n=>n.id==='rdAiArchiveDock').length,1);
 f.controller.sync();f.controller.sync();assert.equal(f.host.children.filter(n=>n.id==='rdAiArchiveDock').length,1);
});
test('AI open/close class and settings card keep their original controls outside the agent panel',()=>{
 const f=fixture();const setOpen=vm.runInNewContext('('+sourceFunction('setPanelOpenClass','  function watchAgentPanel(')+')',f.ctx);
 setOpen(true);assert.ok(f.root.classList.contains('rd-ai-panel-open'));f.controller.sync();assert.ok(f.root.classList.contains('rd-ai-panel-open'));assert.equal(f.panel.parentNode,f.body);assert.notEqual(f.wrap.parentNode,f.panel);
 assert.match(f.css,/html\.rd-ai-archive-mobile\.rd-ai-panel-open #rdAiArchiveDock\{display:none\}/);assert.match(f.css,/html\.rd-ai-panel-open #rdAiLauncher,html\.rd-ai-panel-open #rdAiGear\{display:none!important/);
 setOpen(false);assert.ok(!f.root.classList.contains('rd-ai-panel-open'));assert.equal(f.wrap.children.length,2);
 const settings=sourceFunction('showCard','  function updateResetVisibility(');const ctx={...f.ctx,$:id=>f.document.getElementById(id),prefillForm(){},updateResetVisibility(){}};
 vm.runInNewContext(settings+';showCard();',ctx);assert.equal(f.card.hidden,false);vm.runInNewContext(settings+';hideCard();',ctx);assert.equal(f.card.hidden,true);assert.equal(f.card.parentNode,f.body);
 assert.match(source,/if \(card.hidden\) showCard\(\); else hideCard\(\)/);
});
test('archive-only dock and settings respect phone safe areas without clipping horizontal raw tables',()=>{
 const f=fixture();assert.match(f.css,/html\.rd-ai-archive-mobile #rdAiArchiveDock\{[^}]*min-height:56px;[^}]*safe-area-inset-right[^}]*safe-area-inset-left/);
 assert.match(f.css,/html\.rd-ai-archive-mobile #detailPanel\{padding-bottom:calc\(16px \+ env\(safe-area-inset-bottom/);
 assert.match(f.css,/html\.rd-ai-archive-mobile #rdAiCard\{[^}]*safe-area-inset-top[^}]*safe-area-inset-left[^}]*safe-area-inset-right[^}]*100dvh[^}]*safe-area-inset-bottom/);
 const css=fs.readFileSync(path.join(__dirname,'../research/fund-archive.css'),'utf8');assert.match(css,/\.fa-scroll\{overflow:auto/);assert.ok(!f.css.includes('.fa-scroll'));assert.ok(!/rd-ai-archive-mobile[^}]*overflow:hidden/.test(f.css));
 assert.ok(f.watched.some(w=>w.el===f.host&&w.options.childList===true&&!w.options.subtree));assert.ok(f.watched.some(w=>w.el===f.page&&w.options.attributeFilter.includes('hidden')));
});
test('other pages and detail views without an archive are not docked; idle loader cache is bumped',()=>{
 for(const options of [{mobile:false},{pageHidden:true},{detailHidden:true},{archive:false}]){const f=fixture(options);assert.equal(f.wrap.parentNode,f.body);assert.ok(!f.root.classList.contains('rd-ai-archive-mobile'));}
 const html=fs.readFileSync(path.join(__dirname,'../index.html'),'utf8');assert.match(html,/page-agent-loader\.js\?v=20261117-archive-dock/);assert.match(source,/installArchiveDock\(\$\('rdAiWrap'\)\)/);
});
