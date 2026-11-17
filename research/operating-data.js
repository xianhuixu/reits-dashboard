/* Read-only operating data. Kept separate from REITS_DATA / advice / spread. */
(function(root){
'use strict';
var NAMES={occupancy_rate:'出租率',avg_rent:'平均租金',rent_collection_rate:'收缴率',wale:'剩余租约期限',traffic_volume:'日均车流',traffic_total:'车流量',toll_revenue:'通行费收入',power_generation:'发电量',on_grid_power:'上网电量',settled_power:'结算电量',avg_tariff:'平均电价',revenue:'营业收入',ebitda:'EBITDA',distributable_cash:'可供分配金额',rack_utilization:'上架率',hosting_price:'托管单价',it_load:'IT负载',footfall_yoy:'客流同比（原始值）',sales_yoy:'销售额同比（原始值）',treatment_volume:'处理量',water_supply:'供水量',tenant_count:'租户数量',top5_tenant_share:'前五租户占比',top10_tenant_share:'前十租户占比',leasable_area:'可出租面积',leased_area:'已出租面积',heat_sales:'售热量',heating_area:'供热面积',utilization_hours:'利用小时',rack_capacity:'机柜容量',rack_installed:'已安装容量'};
function numeric(x){return typeof x==='number'&&Number.isFinite(x);}
function format(p){if(!p||!numeric(p.value))return '未披露';return new Intl.NumberFormat('zh-CN',{maximumFractionDigits:2}).format(p.value*(p.unit==='小数'?100:1));}
function unit(p){return p.unit==='小数'?'%':p.unit||'未说明';}
function caliberLabel(p){if(p.sourceTable==='financials'&&p.caliber==='本期'){return p.caliber+(/^\d{4}Q[1-4]$/.test(p.period)?'（单季）':/H1$/.test(p.period)?'（上半年）':/A$/.test(p.period)?'（年报期间）':'');}return p.caliber;}
function scopeReason(p){return '原标签：'+p.level+'；按资产ID确认为'+p.scope+'层。';}
function periodBounds(period){var m=/^(\d{4})(Q[1-4]|H1|A)$/.exec(period||'');if(!m)return null;var year=+m[1],ends={Q1:'03-31',Q2:'06-30',H1:'06-30',Q3:'09-30',Q4:'12-31',A:'12-31'},starts={Q1:'01-01',Q2:'04-01',H1:'01-01',Q3:'07-01',Q4:'10-01',A:'01-01'};return {start:(year-1)+'-'+starts[m[2]],end:year+'-'+ends[m[2]]};}
function compare(p,assets){var b=p&&periodBounds(p.period),expanded=b&&(assets||[]).some(function(a){return a.code===p.code&&a.include_type==='扩募'&&/^\d{4}-\d{2}-\d{2}$/.test(a.include_date||'')&&a.include_date>=b.start&&a.include_date<=b.end;});return {label:expanded?'含扩募，非同店':'不可比',reason:(expanded?'较上年同期资产范围可能变化，不展示同店同比。 ':'')+'未完成两期资产范围、报告期间完整性及含税口径复核，不自动计算同比。'+(!p||p.tax_flag==='未说明'?' 含税口径未说明。':'')};}
function select(d,s){return d.points.filter(function(p){var f=s.funds.get(p.code);return f&&(!s.sector||f.sector_l1===s.sector)&&p.period===s.period&&p.metric===s.metric&&(!s.caliber||p.caliber===s.caliber)&&p.scope==='基金';});}
function paginate(items,requested,size){size=Number.isInteger(size)&&size>0?size:20;var pages=Math.max(1,Math.ceil(items.length/size));var page=Math.min(pages,Math.max(1,Number.isInteger(requested)?requested:1));return {items:items.slice((page-1)*size,page*size),page:page,pages:pages,total:items.length,start:items.length?(page-1)*size+1:0,end:Math.min(page*size,items.length)};}
var api={paginate:paginate,format:format,unit:unit,caliberLabel:caliberLabel,compare:compare,periodBounds:periodBounds,select:select,names:NAMES};
if(typeof module==='object'&&module.exports)module.exports=api;
if(!root.document)return;
var doc=root.document,$=function(id){return doc.getElementById(id);},data=null,loading=false,pageNumber=1,activeDetail=null;
function el(tag,text,cls){var n=doc.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;}
function options(node,values,current){node.replaceChildren();values.forEach(function(x){var o=el('option',x.label);o.value=x.value;node.appendChild(o);});if(values.some(function(x){return x.value===current;}))node.value=current;}
function state(){return {funds:new Map(data.funds.map(function(f){return [f.code,f];})),period:$('opsPeriod').value,sector:$('opsSector').value,metric:$('opsMetric').value,caliber:$('opsCaliber').value};}
function pool(){var s=state();return data.points.filter(function(p){var f=s.funds.get(p.code);return f&&(!s.sector||f.sector_l1===s.sector)&&p.period===s.period&&p.scope==='基金';});}
function controls(kind){if(kind==='sector'||kind==='period'||kind==='init'){
 var ms=Array.from(new Set(pool().map(function(p){return p.metric;}))).sort();var old=$('opsMetric').value;
 var preferred={'交通':'traffic_volume','能源':'power_generation','水务环保':'revenue','供热':'heat_sales','数据中心':'rack_utilization'}[$('opsSector').value]||'occupancy_rate';
 options($('opsMetric'),ms.map(function(m){return {value:m,label:NAMES[m]||m};}),kind==='sector'?preferred:old||preferred);
 }
 var ps=pool().filter(function(p){return p.metric===$('opsMetric').value;});var cs=Array.from(new Set(ps.map(function(p){return p.caliber;}))).sort();
 var preferredCaliber=$('opsMetric').value==='avg_rent'?'期间平均':(['revenue','ebitda','distributable_cash'].includes($('opsMetric').value)?'本期':'期末');
 options($('opsCaliber'),cs.map(function(c){return {value:c,label:c};}),kind==='metric'||kind==='init'?preferredCaliber:$('opsCaliber').value);render();
}
function cell(row,text){var n=el('td',text);row.appendChild(n);return n;}
function closeDetail(){if(!activeDetail)return;var previous=activeDetail;activeDetail=null;previous.row.remove();previous.buttons.forEach(function(b){b.setAttribute('aria-expanded','false');});}
function detail(f,s,row,buttons,trigger){if(activeDetail&&activeDetail.anchor===row){closeDetail();return;}closeDetail();var box=el('div',null,'ops-detail');box.appendChild(el('h3',f.short_name+' · '+s.period));
 var project=data.points.filter(function(p){return p.code===f.code&&p.period===s.period&&p.scope==='项目'&&p.metric===s.metric;});
 var history=data.points.filter(function(p){return p.code===f.code&&p.metric===s.metric&&p.scope==='基金'&&p.caliber===s.caliber;}).sort(function(a,b){return data.periods.indexOf(a.period)-data.periods.indexOf(b.period);});
 var btn=el('button','关闭明细','secondary-button');btn.type='button';btn.onclick=function(){closeDetail();trigger.focus();};box.appendChild(btn);
 function section(title,rs,projectMode){box.appendChild(el('h4',title));if(!rs.length){box.appendChild(el('p','该指标未披露'+(projectMode?'项目':'基金')+'层数据。','note'));return;}
 var wrap=el('div',null,'ops-scroll');wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label',title);var t=el('table',null,'matrix');var tr=el('tr');var thead=el('thead');['报告期／资产','数值','单位','统计口径','含税口径'].forEach(function(x){tr.appendChild(el('th',x));});thead.appendChild(tr);t.appendChild(thead);var body=el('tbody');rs.forEach(function(p){var r=el('tr');var a=data.assets.find(function(a){return a.asset_id===p.asset_id;});cell(r,projectMode?(a?a.asset_name:p.asset_id):p.period);cell(r,format(p));cell(r,unit(p));cell(r,caliberLabel(p));cell(r,p.tax_flag);r.title=scopeReason(p);body.appendChild(r);});t.appendChild(body);wrap.appendChild(t);box.appendChild(wrap);}
 box.appendChild(el('p','历史原值不连线、不补缺期；扩募与税口径变化可能影响可比性。','note'));
 section('历史原值 · '+(NAMES[s.metric]||s.metric),history,false);section('项目明细 · 不与基金合计相加',project,true);
 var list=el('details');list.appendChild(el('summary','资产范围与扩募记录'));data.assets.filter(function(a){return a.code===f.code;}).forEach(function(a){list.appendChild(el('p',a.asset_name+' · '+a.include_type+' · 纳入日期 '+(a.include_date||'未核实')+' · 退出信息待核实','note'));});box.appendChild(list);
 var expanded=el('tr',null,'ops-expanded-row'),holder=cell(expanded,null);holder.colSpan=7;box.classList.add('ops-inline-detail');box.tabIndex=-1;box.id=buttons[0].getAttribute('aria-controls');box.setAttribute('role','region');box.setAttribute('aria-label',f.short_name+'历史及项目明细');holder.appendChild(box);row.after(expanded);activeDetail={row:expanded,anchor:row,buttons:buttons};buttons.forEach(function(b){b.setAttribute('aria-expanded','true');});row.closest('.ops-scroll').scrollLeft=0;box.focus({preventScroll:true});
}
function render(keepPage){if(keepPage!==true)pageNumber=1;closeDetail();var s=state(),ps=select(data,s),query=$('opsSearch').value.trim().toLowerCase();var fs=data.funds.filter(function(f){return (!s.sector||f.sector_l1===s.sector)&&(!query||(f.short_name+f.code).toLowerCase().includes(query));});
 var coverage=new Set(ps.filter(function(p){return numeric(p.value);}).map(function(p){return p.code;}));var any=new Set(data.points.filter(function(p){return p.period===s.period&&s.funds.has(p.code)&&(!s.sector||s.funds.get(p.code).sector_l1===s.sector);}).map(function(p){return p.code;}));
 $('opsCoverage').textContent=s.period+' · '+(s.sector||'全部业态')+'：该期经营／财务有记录 '+any.size+' 只；当前指标基金层有值 '+coverage.size+' 只。未用上一期补齐。';
 var cards=$('opsCards');cards.replaceChildren();[['本期有记录',any.size+' 只'],['当前指标有值',coverage.size+' 只'],['统计口径',s.caliber||'无记录']].forEach(function(x){var a=el('article',null,'ops-card');a.appendChild(el('p',x[0]));a.appendChild(el('strong',x[1]));cards.appendChild(a);});
 var page=paginate(fs,pageNumber,20);pageNumber=page.page;
 var body=$('opsBody');body.replaceChildren();page.items.forEach(function(f,index){var rs=ps.filter(function(p){return p.code===f.code;});if(!rs.length)rs=[null];rs.forEach(function(p,pointIndex){var r=el('tr',null,'ops-data-row');var name=cell(r,null);name.appendChild(el('b',f.short_name));name.appendChild(el('small',f.code+' · '+f.sector_l2));var compact=el('span',format(p)+(p?' '+unit(p):''),'ops-mobile-value');compact.setAttribute('aria-hidden','true');name.appendChild(compact);cell(r,format(p));cell(r,p?unit(p):'—');cell(r,p?caliberLabel(p):'—');cell(r,p?p.tax_flag:'—');var reason=el('details');reason.appendChild(el('summary',p?compare(p,data.assets).label:'未披露'));reason.appendChild(el('p',p?compare(p,data.assets).reason:'本期该口径无基金层记录；项目层数据可查看明细。','note'));cell(r,null).appendChild(reason);
 var b=el('button','查看明细','secondary-button'),mobile=el('button','展开明细','secondary-button ops-mobile-open'),buttons=[b,mobile],detailId='ops-detail-'+f.code+'-'+index+'-'+pointIndex;buttons.forEach(function(button){button.type='button';button.setAttribute('aria-expanded','false');button.setAttribute('aria-controls',detailId);button.onclick=function(){detail(f,s,r,buttons,button);};});name.appendChild(mobile);cell(r,null).appendChild(b);body.appendChild(r);});});
 if(!fs.length){var r=el('tr');var c=cell(r,'没有匹配基金，请调整筛选。');c.colSpan=7;body.appendChild(r);}
 $('opsCount').textContent='匹配 '+fs.length+' 只基金，本页显示第 '+page.start+'–'+page.end+' 只（每页 20 只；含未披露与未上市项目，不作为覆盖率分母）';
 $('opsPageStatus').textContent='第 '+page.page+' / '+page.pages+' 页';$('opsPrev').disabled=page.page<=1;$('opsNext').disabled=page.page>=page.pages;

}
function load(){if(data||loading)return;loading=true;$('opsLoad').textContent='正在读取经营数据快照…';fetch('research/operating-data.json').then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json();}).then(function(d){if(d.schemaVersion!==1)throw new Error('数据版本不兼容');data=d;$('opsLoad').textContent='导入日期 '+d.importedAt.slice(0,10)+'（北京时间） · 经营报告期独立于行情日 · 来源：用户爬取库';options($('opsPeriod'),d.periods.map(function(x){return {value:x,label:x};}),d.latestPeriod);options($('opsSector'),[{value:'',label:'全部业态'}].concat(Array.from(new Set(d.funds.map(function(f){return f.sector_l1;}))).sort().map(function(x){return {value:x,label:x};})));controls('init');$('opsFilters').disabled=false;}).catch(function(e){loading=false;$('opsLoad').textContent='经营数据暂不可用：'+e.message+'。';$('opsRetry').hidden=false;});}
var page=$('pg-ops');if(!page)return;
$('opsPrev').onclick=function(){pageNumber--;render(true);};$('opsNext').onclick=function(){pageNumber++;render(true);};
$('opsRetry').onclick=function(){this.hidden=true;load();};['Sector','Period','Metric'].forEach(function(k){$('ops'+k).onchange=function(){controls(k.toLowerCase());};});$('opsCaliber').onchange=render;$('opsSearch').oninput=function(){if(data)render();};
new MutationObserver(function(){if(!page.hidden)load();}).observe(page,{attributes:true,attributeFilter:['hidden']});if(!page.hidden)load();
})(typeof window==='undefined'?globalThis:window);
