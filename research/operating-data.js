/* Read-only operating data. Kept separate from REITS_DATA / advice / spread. */
(function(root){
'use strict';
var NAMES={occupancy_rate:'出租率',avg_rent:'平均租金',rent_collection_rate:'收缴率',wale:'剩余租约期限',traffic_volume:'日均车流',traffic_total:'车流量',toll_revenue:'通行费收入',power_generation:'发电量',on_grid_power:'上网电量',settled_power:'结算电量',avg_tariff:'平均电价',revenue:'营业收入',ebitda:'EBITDA',distributable_cash:'可供分配金额',rack_utilization:'上架率',hosting_price:'托管单价',it_load:'IT负载',footfall_yoy:'客流同比（原始值）',sales_yoy:'销售额同比（原始值）',treatment_volume:'处理量',water_supply:'供水量',tenant_count:'租户数量',top5_tenant_share:'前五租户占比',top10_tenant_share:'前十租户占比',leasable_area:'可出租面积',leased_area:'已出租面积',heat_sales:'售热量',heating_area:'供热面积',utilization_hours:'利用小时',rack_capacity:'机柜容量',rack_installed:'已安装容量'};
function numeric(x){return typeof x==='number'&&Number.isFinite(x);}
function format(p){if(!p||!numeric(p.value))return '尚未披露';var isPct=p.unit==='小数'||p.unit==='%',v=p.value*(p.unit==='小数'?100:1),opts=isPct||!Number.isInteger(v)?{minimumFractionDigits:2,maximumFractionDigits:2}:{maximumFractionDigits:0};return new Intl.NumberFormat('zh-CN',opts).format(v);}
function unit(p){return p.unit==='小数'?'%':p.unit||'未说明';}
function caliberLabel(p){if(p.sourceTable==='financials'&&p.caliber==='本期'){return p.caliber+(/^\d{4}Q[1-4]$/.test(p.period)?'（单季）':/H1$/.test(p.period)?'（上半年）':/A$/.test(p.period)?'（年报期间）':'');}return p.caliber;}
function scopeReason(p){return '原标签：'+p.level+'；按资产ID确认为'+p.scope+'层。';}
function periodBounds(period){var m=/^(\d{4})(Q[1-4]|H1|A)$/.exec(period||'');if(!m)return null;var year=+m[1],ends={Q1:'03-31',Q2:'06-30',H1:'06-30',Q3:'09-30',Q4:'12-31',A:'12-31'},starts={Q1:'01-01',Q2:'04-01',H1:'01-01',Q3:'07-01',Q4:'10-01',A:'01-01'};return {start:(year-1)+'-'+starts[m[2]],end:year+'-'+ends[m[2]]};}
function compare(p,assets){var b=p&&periodBounds(p.period),expanded=b&&(assets||[]).some(function(a){return a.code===p.code&&a.include_type==='扩募'&&/^\d{4}-\d{2}-\d{2}$/.test(a.include_date||'')&&a.include_date>=b.start&&a.include_date<=b.end;});
 if(expanded)return {label:'含扩募，非同店',reason:'较上年同期资产范围可能变化，不展示同店同比。未完成两期项目范围复核，不自动计算同比。'};
 var metric=p&&p.metric,tax=p&&p.tax_flag;
 if(metric==='footfall_yoy'||metric==='sales_yoy')return {label:'不可比',reason:'该字段已是原始同比，未按同口径复核，不作为已核验同比列。'};
 if(metric==='avg_rent'||metric==='hosting_price')return {label:'不可比',reason:'租金类同比须同单位、同平均或期末口径，且含税口径对齐。税标记为“未说明”或未对齐时不计算同比。'+(tax==='未说明'?' 含税口径未说明。':'')};
 return {label:'待核资产范围',reason:'可能已有上年同期同口径记录，但两期项目是否持续在池尚未复核，不自动计算同比。税口径“不适用”不作为出租率、车流、电量等不可比的依据。'};}
function select(d,s){return d.points.filter(function(p){var f=s.funds.get(p.code);return f&&(!s.sector||f.sector_l1===s.sector)&&p.period===s.period&&p.metric===s.metric&&(!s.caliber||p.caliber===s.caliber)&&p.scope==='基金';});}
var CORE={'交通':'traffic_volume','能源':'power_generation','水务环保':'revenue','供热':'heating_area','数据中心':'rack_utilization'};
var UNIVERSAL=['revenue','ebitda','distributable_cash'];
var METRIC_SECTORS={occupancy_rate:['消费','产业园','仓储物流','保障性租赁住房'],avg_rent:['消费','产业园','仓储物流','保障性租赁住房'],wale:['消费','产业园','仓储物流','保障性租赁住房'],rent_collection_rate:['消费','产业园','仓储物流','保障性租赁住房','数据中心','供热'],leasable_area:['消费','产业园','仓储物流','保障性租赁住房'],leased_area:['消费','产业园','仓储物流','保障性租赁住房'],tenant_count:['消费','产业园','仓储物流','保障性租赁住房'],top5_tenant_share:['消费','产业园','仓储物流','保障性租赁住房'],top10_tenant_share:['消费','产业园','仓储物流','保障性租赁住房'],traffic_volume:['交通'],traffic_total:['交通'],toll_revenue:['交通'],power_generation:['能源','水务环保'],on_grid_power:['能源'],settled_power:['能源','水务环保'],avg_tariff:['能源'],utilization_hours:['能源','水务环保'],fuel_price:['能源'],fuel_volume:['能源'],treatment_volume:['水务环保'],water_supply:['水务环保'],heat_sales:['供热'],heating_area:['供热'],rack_utilization:['数据中心'],hosting_price:['数据中心'],it_load:['数据中心'],rack_capacity:['数据中心'],rack_installed:['数据中心'],footfall_yoy:['消费'],sales_yoy:['消费']};
function coreMetric(sector){return CORE[sector]||'occupancy_rate';}
function coreChoices(sector){return [coreMetric(sector)].concat({交通:['traffic_total']}[sector]||[]);}
function preferredCaliber(metric){if(metric==='avg_rent'||metric==='traffic_volume'||metric==='avg_tariff'||metric==='hosting_price')return '期间平均';if(metric==='revenue'||metric==='ebitda'||metric==='distributable_cash')return '本期';if(metric==='toll_revenue'||metric==='power_generation'||metric==='treatment_volume'||metric==='heat_sales')return '期间';return '期末';}
function metricApplies(metric,sector){if(UNIVERSAL.indexOf(metric)>=0)return true;var sectors=METRIC_SECTORS[metric];return !sectors||sectors.indexOf(sector)>=0;}
function vacancyLabel(f,metric,p){if(p&&numeric(p.value))return '';if(p&&!numeric(p.value))return '尚未披露';if(!metricApplies(metric,f.sector_l1))return '该指标不适用';return '尚未披露';}
function isCoreMetric(metric){return !metric||metric==='__core__';}
function activeMetric(s,f){return isCoreMetric(s.metric)?coreMetric(f.sector_l1):s.metric;}
function pointFor(d,f,period,metric,caliber,loose){var all=d.points.filter(function(p){return p.code===f.code&&p.period===period&&p.metric===metric&&p.scope==='基金';});if(!loose&&caliber)return all.filter(function(p){return p.caliber===caliber;})[0]||null;var pref=caliber||preferredCaliber(metric);return all.filter(function(p){return p.caliber===pref&&numeric(p.value);})[0]||all.filter(function(p){return numeric(p.value);})[0]||all[0]||null;}
function rowView(d,s,f){if(isCoreMetric(s.metric)){var choices=coreChoices(f.sector_l1),i,p;for(i=0;i<choices.length;i++){p=pointFor(d,f,s.period,choices[i],null,true);if(p&&numeric(p.value))return {metric:choices[i],point:p,vacancy:''};}return {metric:choices[0],point:null,vacancy:vacancyLabel(f,choices[0],null)};}var metric=s.metric,loose=s.caliber==='__auto__',p=pointFor(d,f,s.period,metric,loose?null:s.caliber,loose);return {metric:metric,point:p,vacancy:vacancyLabel(f,metric,p)};}
function paginate(items,requested,size){size=Number.isInteger(size)&&size>0?size:20;var pages=Math.max(1,Math.ceil(items.length/size));var page=Math.min(pages,Math.max(1,Number.isInteger(requested)?requested:1));return {items:items.slice((page-1)*size,page*size),page:page,pages:pages,total:items.length,start:items.length?(page-1)*size+1:0,end:Math.min(page*size,items.length)};}
var api={paginate:paginate,format:format,unit:unit,caliberLabel:caliberLabel,compare:compare,periodBounds:periodBounds,select:select,coreMetric:coreMetric,preferredCaliber:preferredCaliber,metricApplies:metricApplies,vacancyLabel:vacancyLabel,activeMetric:activeMetric,pointFor:pointFor,coreChoices:coreChoices,rowView:rowView,names:NAMES};
if(typeof module==='object'&&module.exports)module.exports=api;
if(!root.document)return;
var doc=root.document,$=function(id){return doc.getElementById(id);},data=null,loading=false,pageNumber=1,activeDetail=null;
function el(tag,text,cls){var n=doc.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;}
function options(node,values,current){node.replaceChildren();values.forEach(function(x){var o=el('option',x.label);o.value=x.value;node.appendChild(o);});if(values.some(function(x){return x.value===current;}))node.value=current;}
function state(){return {funds:new Map(data.funds.map(function(f){return [f.code,f];})),period:$('opsPeriod').value,sector:$('opsSector').value,metric:$('opsMetric').value,caliber:$('opsCaliber').value};}
function pool(){var s=state();return data.points.filter(function(p){var f=s.funds.get(p.code);return f&&(!s.sector||f.sector_l1===s.sector)&&p.period===s.period&&p.scope==='基金';});}
function controls(kind){if(kind==='sector'||kind==='period'||kind==='init'){
 var ms=Array.from(new Set(pool().map(function(p){return p.metric;}))).sort();var old=$('opsMetric').value;var sector=$('opsSector').value;
 var preferred=sector?coreMetric(sector):'__core__';
 var opts=ms.map(function(m){return {value:m,label:NAMES[m]||m};});
 if(!sector)opts.unshift({value:'__core__',label:'按业态核心指标'});
 options($('opsMetric'),opts,kind==='sector'||kind==='init'?preferred:old||preferred);
 }
 var metric=$('opsMetric').value;
 if(isCoreMetric(metric)){options($('opsCaliber'),[{value:'__auto__',label:'按指标默认口径'}],'__auto__');$('opsCaliber').disabled=true;}
 else {$('opsCaliber').disabled=false;var ps=pool().filter(function(p){return p.metric===metric;});var cs=Array.from(new Set(ps.map(function(p){return p.caliber;}))).sort();
 options($('opsCaliber'),cs.map(function(c){return {value:c,label:c};}),kind==='metric'||kind==='init'?preferredCaliber(metric):$('opsCaliber').value);}
 render();
}
function cell(row,text,cls){var n=el('td',text);if(cls)n.className=cls;row.appendChild(n);return n;}
function closeDetail(){if(!activeDetail)return;var previous=activeDetail;activeDetail=null;previous.row.remove();previous.buttons.forEach(function(b){b.setAttribute('aria-expanded','false');});}
function detail(f,s,row,buttons,trigger){if(activeDetail&&activeDetail.anchor===row){closeDetail();return;}closeDetail();var view=rowView(data,s,f),metric=view.metric,caliber=view.point?view.point.caliber:preferredCaliber(metric);var box=el('div',null,'ops-detail');box.appendChild(el('h3',f.short_name+' · '+s.period+' · '+(NAMES[metric]||metric)));
 var project=data.points.filter(function(p){return p.code===f.code&&p.period===s.period&&p.scope==='项目'&&p.metric===metric;});
 var history=data.points.filter(function(p){return p.code===f.code&&p.metric===metric&&p.scope==='基金'&&p.caliber===caliber;}).sort(function(a,b){return data.periods.indexOf(a.period)-data.periods.indexOf(b.period);});
 var btn=el('button','关闭明细','secondary-button');btn.type='button';btn.onclick=function(){closeDetail();trigger.focus();};box.appendChild(btn);
 function section(title,rs,projectMode){box.appendChild(el('h4',title));if(!rs.length){box.appendChild(el('p',view.vacancy==='该指标不适用'?'该指标不适用于该业态。':'该指标尚未披露'+(projectMode?'项目':'基金')+'层数据。','note'));return;}
 var wrap=el('div',null,'ops-scroll');wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label',title);var t=el('table',null,'matrix');var tr=el('tr');var thead=el('thead');['报告期／资产','数值','单位','统计口径','含税口径'].forEach(function(x){tr.appendChild(el('th',x));});thead.appendChild(tr);t.appendChild(thead);var body=el('tbody');rs.forEach(function(p){var r=el('tr');var a=data.assets.find(function(a){return a.asset_id===p.asset_id;});cell(r,projectMode?(a?a.asset_name:p.asset_id):p.period);cell(r,format(p),'ops-num');cell(r,unit(p));cell(r,caliberLabel(p));cell(r,p.tax_flag);r.title=scopeReason(p);body.appendChild(r);});t.appendChild(body);wrap.appendChild(t);box.appendChild(wrap);}
 box.appendChild(el('p','历史原值不连线、不补缺期；扩募与税口径变化可能影响可比性。','note'));
 section('历史原值 · '+(NAMES[metric]||metric),history,false);section('项目明细 · 不与基金合计相加',project,true);
 var list=el('details');list.appendChild(el('summary','资产范围与扩募记录'));data.assets.filter(function(a){return a.code===f.code;}).forEach(function(a){list.appendChild(el('p',a.asset_name+' · '+a.include_type+' · 纳入日期 '+(a.include_date||'未核实')+' · 退出信息待核实','note'));});box.appendChild(list);
 var expanded=el('tr',null,'ops-expanded-row'),holder=cell(expanded,null);holder.colSpan=7;box.classList.add('ops-inline-detail');box.tabIndex=-1;box.id=buttons[0].getAttribute('aria-controls');box.setAttribute('role','region');box.setAttribute('aria-label',f.short_name+'历史及项目明细');holder.appendChild(box);row.after(expanded);activeDetail={row:expanded,anchor:row,buttons:buttons};buttons.forEach(function(b){b.setAttribute('aria-expanded','true');});row.closest('.ops-scroll').scrollLeft=0;box.focus({preventScroll:true});
}
function render(keepPage){if(keepPage!==true)pageNumber=1;closeDetail();var s=state(),query=$('opsSearch').value.trim().toLowerCase();var fs=data.funds.filter(function(f){return (!s.sector||f.sector_l1===s.sector)&&(!query||(f.short_name+f.code).toLowerCase().includes(query));});
 var views=fs.map(function(f){return rowView(data,s,f);});
 var valued=views.filter(function(v){return v.point&&numeric(v.point.value);}).length;
 var missing=views.filter(function(v){return v.vacancy==='尚未披露';}).length;
 var inapplicable=views.filter(function(v){return v.vacancy==='该指标不适用';}).length;
 var any=new Set(data.points.filter(function(p){return p.period===s.period&&s.funds.has(p.code)&&(!s.sector||s.funds.get(p.code).sector_l1===s.sector);}).map(function(p){return p.code;}));
 $('opsCoverage').textContent=s.period+' · '+(s.sector||'全部业态')+'：该期经营／财务有记录 '+any.size+' 只；当前指标有值 '+valued+' 只，尚未披露 '+missing+' 只'+(inapplicable?'，该指标不适用 '+inapplicable+' 只':'')+'。未用上一期补齐。';
 var cards=$('opsCards');cards.replaceChildren();[['本期有记录',any.size+' 只'],['当前指标有值',valued+' 只'],[inapplicable?'该指标不适用':'尚未披露',(inapplicable||missing)+' 只']].forEach(function(x){var a=el('article',null,'ops-card');a.appendChild(el('p',x[0]));a.appendChild(el('strong',x[1]));cards.appendChild(a);});
 var page=paginate(fs,pageNumber,20);pageNumber=page.page;
 var body=$('opsBody');body.replaceChildren();page.items.forEach(function(f,index){var view=rowView(data,s,f),p=view.point,vacant=view.vacancy,display=vacant||format(p);var r=el('tr',null,'ops-data-row');var name=cell(r,null);var archiveLink=el('a',f.short_name,'fa-name-link');archiveLink.href='#/detail/'+encodeURIComponent(f.code);archiveLink.title='打开完整基金研究档案';name.appendChild(archiveLink);name.appendChild(el('small',f.code+' · '+f.sector_l2+' · '+(NAMES[view.metric]||view.metric)));var compact=el('span',display+(p&&!vacant?' '+unit(p):''),'ops-mobile-value');compact.setAttribute('aria-hidden','true');name.appendChild(compact);var valueCell=cell(r,display,vacant?'ops-vacant ops-num':'ops-num');cell(r,p&&!vacant?unit(p):'—');cell(r,p&&!vacant?caliberLabel(p):'—');cell(r,p&&!vacant?p.tax_flag:'—');var reason=el('details');var cmp=(!vacant&&p)?compare(p,data.assets):{label:vacant||'尚未披露',reason:vacant==='该指标不适用'?'当前指标与该业态不匹配，不代表没有经营数据。请改用该业态核心指标，或切到对应业态查看。':'本期该口径无基金层记录；项目层数据可查看明细。'};reason.appendChild(el('summary',cmp.label));reason.appendChild(el('p',cmp.reason,'note'));cell(r,null).appendChild(reason);
 var b=el('button','查看明细','secondary-button'),mobile=el('button','展开明细','secondary-button ops-mobile-open'),buttons=[b,mobile],detailId='ops-detail-'+f.code+'-'+index;buttons.forEach(function(button){button.type='button';button.setAttribute('aria-expanded','false');button.setAttribute('aria-controls',detailId);button.onclick=function(){detail(f,s,r,buttons,button);};});name.appendChild(mobile);cell(r,null).appendChild(b);body.appendChild(r);});
 if(!fs.length){var r=el('tr');var c=cell(r,'没有匹配基金，请调整筛选。');c.colSpan=7;body.appendChild(r);}
 $('opsCount').textContent='匹配 '+fs.length+' 只基金，本页显示第 '+page.start+'–'+page.end+' 只（每页 20 只；含尚未披露、指标不适用与未上市项目，不作为覆盖率分母）';
 $('opsPageStatus').textContent='第 '+page.page+' / '+page.pages+' 页';$('opsPrev').disabled=page.page<=1;$('opsNext').disabled=page.page>=page.pages;

}
function load(){if(data||loading)return;loading=true;$('opsLoad').textContent='正在读取经营数据快照…';fetch('research/operating-data.json').then(function(r){if(!r.ok)throw new Error('HTTP '+r.status);return r.json();}).then(function(d){if(d.schemaVersion!==1)throw new Error('数据版本不兼容');data=d;$('opsLoad').textContent='导入日期 '+d.importedAt.slice(0,10)+'（北京时间） · 经营报告期独立于行情日 · 来源：用户爬取库';options($('opsPeriod'),d.periods.map(function(x){return {value:x,label:x};}),d.latestPeriod);options($('opsSector'),[{value:'',label:'全部业态'}].concat(Array.from(new Set(d.funds.map(function(f){return f.sector_l1;}))).sort().map(function(x){return {value:x,label:x};})));controls('init');$('opsFilters').disabled=false;}).catch(function(e){loading=false;$('opsLoad').textContent='经营数据暂不可用：'+e.message+'。';$('opsRetry').hidden=false;});}
var page=$('pg-ops');if(!page)return;
$('opsPrev').onclick=function(){pageNumber--;render(true);};$('opsNext').onclick=function(){pageNumber++;render(true);};
$('opsRetry').onclick=function(){this.hidden=true;load();};['Sector','Period','Metric'].forEach(function(k){$('ops'+k).onchange=function(){controls(k.toLowerCase());};});$('opsCaliber').onchange=render;$('opsSearch').oninput=function(){if(data)render();};
new MutationObserver(function(){if(!page.hidden)load();}).observe(page,{attributes:true,attributeFilter:['hidden']});if(!page.hidden)load();
})(typeof window==='undefined'?globalThis:window);
