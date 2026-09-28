/* 原始权益人注册地索引：行情只读，城市级示意坐标，地域统计按基金代码去重。 */
(function (root) {
  'use strict';
  function selectLocations(registry, funds, filters) {
    var byCode = new Map(funds.map(function (f) { return [f.code, f]; }));
    var query = (filters.query || '').trim().toLowerCase();
    return registry.locations.filter(function (r) {
      var f = byCode.get(r.code), city = registry.cities[r.city];
      return f && city && (!filters.sectors || filters.sectors.includes(f.sector)) &&
        (!filters.province || city.province === filters.province) &&
        (!query || [f.name, f.code, r.organization, r.role, r.city, city.province].join(' ').toLowerCase().includes(query));
    }).map(function (r) { return Object.assign({}, r, {fund:byCode.get(r.code)}); });
  }
  function groupLocations(rows, registry, key) {
    var groups = new Map();
    rows.forEach(function (r) {
      var name = key === 'province' ? registry.cities[r.city].province : r.city;
      if (!groups.has(name)) groups.set(name, {name:name, codes:new Set(), rows:[]});
      var g = groups.get(name); g.codes.add(r.code); g.rows.push(r);
    });
    return Array.from(groups.values()).map(function (g) { return {name:g.name, count:g.codes.size, rows:g.rows}; })
      .sort(function (a, b) { return b.count-a.count || a.name.localeCompare(b.name, 'zh-CN'); });
  }
  function sectorCounts(rows) {
    var counts=new Map();
    rows.forEach(function(r){ if(!counts.has(r.fund.sector))counts.set(r.fund.sector,new Set());counts.get(r.fund.sector).add(r.code); });
    return Array.from(counts,function(entry){return {sector:entry[0],count:entry[1].size};});
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {selectLocations:selectLocations, groupLocations:groupLocations, sectorCounts:sectorCounts};
  if (!root.document) return;
  var doc=root.document, host=doc.getElementById('assetGeography');
  if (!host) return;
  var registry, funds, rows=[], selected='', mode='city', geo, zoom=1, activeSectors=new Set(), sectors=[];
  var $=function (id) { return doc.getElementById(id); };
  var esc=function (s) { return String(s).replace(/[&<>"']/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); };
  var viewports={1:[0,0,720,490],2:[340,140,330,320],3:[450,267,105,100],4:[435,370,80,65]};
  var svgNS='http://www.w3.org/2000/svg';
  var palette=['#3159ce','#0b8c85','#be683b','#9163a8','#bd8e21','#597d50','#ae556d','#5f79a2','#756759','#394988'];
  function sectorColor(sector){return palette[Math.max(0,sectors.indexOf(sector))%palette.length];}
  function svgEl(tag, attrs, parent) {
    var e=doc.createElementNS(svgNS,tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k,attrs[k]); });
    if (parent) parent.appendChild(e); return e;
  }
  function xy(p) { return [(p[0]-73)*10.5+20,(54-p[1])*12.6+12]; }
  function geometryPath(feature) {
    var polygons=feature.geometry.type==='Polygon' ? [feature.geometry.coordinates] : feature.geometry.coordinates;
    return polygons.map(function (polygon) { return polygon.map(function (ring) {
      return ring.map(function (p,i) { var v=xy(p); return (i?'L':'M')+v[0].toFixed(2)+','+v[1].toFixed(2); }).join('')+'Z';
    }).join(''); }).join('');
  }
  function buildMap() {
    var svg=$('geoSvg'); svg.replaceChildren();
    var defs=svgEl('defs',{},svg), clip=svgEl('clipPath',{id:'geoMainClip'},defs);
    svgEl('rect',{x:0,y:0,width:720,height:480},clip);
    var base=svgEl('g',{'clip-path':'url(#geoMainClip)'},svg);
    var paths=svgEl('g',{id:'geoLand'},base);
    geo.features.forEach(function (f) { svgEl('path',{d:geometryPath(f),class:'geo-province','fill-rule':'evenodd'},paths); });
    svgEl('g',{id:'geoMarkers'},svg);
    // 南海诸岛附图保留底图原始几何；主图与附图采用相同投影。
    var inset=svgEl('svg',{x:32,y:330,width:96,height:126,viewBox:'335 420 205 250',class:'geo-inset','aria-hidden':'true'},svg);
    svgEl('rect',{x:335,y:420,width:205,height:250,class:'geo-inset-bg'},inset);
    geo.features.forEach(function (f) { svgEl('path',{d:geometryPath(f),class:'geo-province'},inset); });
    var label=svgEl('text',{x:80,y:474,'text-anchor':'middle',class:'geo-inset-label'},svg);label.textContent='南海诸岛';
  }
  function setZoom(value) {
    zoom=value;
    $('geoSvg').setAttribute('viewBox',viewports[zoom].join(' '));
    $('geoZoom').value=String(zoom);
    renderMarkers();
  }

  function chooseCity(city) {
    selected=selected===city?'':city;
    renderMarkers(); renderProjects(); renderRank();
  }
  function renderMarkers() {
    if (!geo) return;
    var focusLabel=doc.activeElement && doc.activeElement.closest('.geo-marker') ? doc.activeElement.getAttribute('aria-label') : null;
    var parent=$('geoMarkers'); parent.replaceChildren();
    var viewport=viewports[zoom], markerScale=Math.max(viewport[2]/720,viewport[3]/490);
    var cities=groupLocations(rows,registry,'city');
    // 标签避让：密集城市用编号圆点和旁边的城市排名查阅。
    var labels=['北京市','上海市','深圳市','重庆市','成都市'];
    cities.slice().reverse().forEach(function (g) {
      var p=xy(registry.cities[g.name].coordinates), r=5+Math.sqrt(g.count)*3;
      var button=svgEl('g',{transform:'translate('+p.join(',')+') scale('+markerScale+')',tabindex:0,role:'button','aria-label':g.name+'，'+g.count+'只基金，查看项目','aria-pressed':String(selected===g.name),class:'geo-marker'+(selected===g.name?' is-selected':'')},parent);
      svgEl('circle',{r:r+5,class:'geo-halo'},button);
      var mix=sectorCounts(g.rows).sort(function(a,b){return sectors.indexOf(a.sector)-sectors.indexOf(b.sector);});
      var circumference=2*Math.PI*r, total=mix.reduce(function(n,s){return n+s.count;},0), offset=0;
      mix.forEach(function(s){var length=circumference*s.count/total;svgEl('circle',{r:r,fill:'none',stroke:sectorColor(s.sector),'stroke-width':r*2,'stroke-dasharray':length+' '+circumference,'stroke-dashoffset':-offset,transform:'rotate(-90)'},button);offset+=length;});
      svgEl('circle',{r:r*.62,class:'geo-dot'},button);
      var n=svgEl('text',{'text-anchor':'middle',dy:3.5,class:'geo-number'},button);n.textContent=g.count;
      if(zoom>1 || labels.includes(g.name)) {
        var offset=g.name==='北京市'?-18:20;
        var t=svgEl('text',{'text-anchor':'middle',y:offset,class:'geo-city-label'},button);
        t.textContent=g.name.replace(/市$|藏族自治州$/g,'');
      }
      if(focusLabel===button.getAttribute('aria-label'))button.focus({preventScroll:true});
      var title=svgEl('title',{},button);title.textContent=g.name+' · '+g.count+'只基金 · '+mix.map(function(s){return s.sector+s.count+'只';}).join(' / ');
      button.addEventListener('click',function () { chooseCity(g.name); });
      button.addEventListener('keydown',function (e) { if(e.key==='Enter'||e.key===' ') {e.preventDefault();chooseCity(g.name);} });
    });
  }
  function renderRank() {
    var groups=groupLocations(rows,registry,mode), max=groups.length?groups[0].count:1;
    $('geoRank').innerHTML=groups.map(function (g,i) {
      return '<button class="geo-rank-row '+(selected===g.name?'is-selected':'')+'" data-place="'+esc(g.name)+'" aria-label="'+esc(g.name)+'，'+g.count+'只基金"><span class="geo-rank-num">'+String(i+1).padStart(2,'0')+'</span><span class="geo-rank-name">'+esc(g.name.replace(/市$|省$/g,''))+'</span><span class="geo-rank-track"><i style="width:'+g.count/max*100+'%"></i></span><b>'+g.count+'</b></button>';
    }).join('') || '<p class="geo-empty">没有符合筛选条件的已收录地点。</p>';
    $('geoRank').querySelectorAll('button').forEach(function (button) { button.addEventListener('click',function () {
      if(mode==='city') chooseCity(button.dataset.place);
      else { $('geoProvince').value=button.dataset.place; update(); }
    }); });
  }
  function renderProjects() {
    var visible=rows.filter(function (r) { return !selected || selected===r.city; });
    $('geoSelection').textContent=selected || '全部已收录地点';
    $('geoResultCount').textContent=new Set(visible.map(function(r){return r.code;})).size+' 只基金 · '+visible.length+' 条主体记录';
    $('geoClearCity').hidden=!selected;
    $('geoProjects').innerHTML=visible.map(function (r) {
      var s=registry.sources[r.source], c=registry.cities[r.city];
      return '<article class="geo-project"><div class="geo-project-top"><span><i class="geo-sector-dot" style="background:'+sectorColor(r.fund.sector)+'"></i>'+esc(r.city)+' · '+esc(r.fund.sector)+'</span><small>'+esc(r.code)+'</small></div><a class="geo-fund" href="#/detail/'+encodeURIComponent(r.code)+'">'+esc(r.fund.name)+' ↗</a><p><b>'+esc(r.role)+'</b> · '+esc(r.organization)+'</p><div class="geo-project-source"><a href="'+esc(s.url)+'" target="_blank" rel="noopener noreferrer">'+esc(s.document||'招募说明书')+' ↗</a><span>注册地 · '+esc(c.province)+'</span></div></article>';
    }).join('') || '<p class="geo-empty">未找到项目。可清除筛选，或查看待补充清单。</p>';
  }
  function update() {
    selected='';
    rows=selectLocations(registry,funds,{sectors:Array.from(activeSectors),province:$('geoProvince').value,query:$('geoSearch').value});
    var covered=new Set(rows.map(function (r) { return r.code; }));
    $('geoStats').innerHTML='<span><b>'+covered.size+'</b>只基金</span><span><b>'+new Set(rows.map(function(r){return r.city;})).size+'</b>个城市 / 州</span><span><b>'+groupLocations(rows,registry,'province').length+'</b>个省级地区</span>';
    $('geoStatus').textContent='筛选结果：'+covered.size+'只基金，'+rows.length+'条原始权益人注册地记录。';
    renderMarkers();renderRank();renderProjects();
  }
  function init() {
    sectors=Array.from(new Set(funds.map(function(f){return f.sector;}))).sort();
    activeSectors=new Set(sectors);
    var provinces=Array.from(new Set(Object.values(registry.cities).map(function(c){return c.province;}))).sort(function(a,b){return a.localeCompare(b,'zh-CN');});
    function renderLegend(){ $('geoSectorLegend').innerHTML=sectors.map(function(s){return '<button type="button" class="geo-sector-filter'+(activeSectors.has(s)?' on':'')+'" data-sector="'+esc(s)+'" aria-pressed="'+activeSectors.has(s)+'"><i style="background:'+sectorColor(s)+'"></i>'+esc(s)+'</button>';}).join(''); $('geoSectorLegend').querySelectorAll('button').forEach(function(b){b.addEventListener('click',function(){var s=b.dataset.sector;if(activeSectors.has(s))activeSectors.delete(s);else activeSectors.add(s);renderLegend();update();});});}
    renderLegend();
    provinces.forEach(function(s){$('geoProvince').add(new Option(s,s));});
    var covered=new Set(registry.locations.map(function(r){return r.code;}));
    var missing=funds.filter(function(f){return !covered.has(f.code);});
    $('geoCoverage').textContent='已定位 '+covered.size+' / '+funds.length+' 只基金 · 注册地口径';
    $('geoMissingLabel').textContent='口径与境外注册主体（'+missing.length+'只未设内地点位）';
    var offshoreLink=function(r){return '<a href="'+esc(registry.sources[r.source].url)+'" target="_blank" rel="noopener noreferrer">'+esc(r.organization)+' <small>'+esc(r.code)+'</small></a>';};
    var unverified=missing.filter(function(f){return !registry.offshore.some(function(r){return r.code===f.code;});});
    $('geoMissing').innerHTML='<p>未设内地点位：'+registry.offshore.filter(function(r){return !covered.has(r.code);}).map(offshoreLink).join('')+'</p><p>同基金另有境内点位：'+registry.offshore.filter(function(r){return covered.has(r.code);}).map(offshoreLink).join('')+'</p>'+(unverified.length?'<p>注册地待核验：'+unverified.map(function(f){return '<a href="#/detail/'+encodeURIComponent(f.code)+'">'+esc(f.name)+' <small>'+esc(f.code)+'</small></a>';}).join('')+'</p>':'');
    $('geoChecked').textContent=registry.checkedAt;
    $('geoProvince').addEventListener('change',update);
    $('geoSearch').addEventListener('input',update);
    $('geoReset').addEventListener('click',function(){activeSectors=new Set(sectors);renderLegend();$('geoProvince').value='';$('geoSearch').value='';setZoom(1);update();});
    $('geoClearCity').addEventListener('click',function(){selected='';renderMarkers();renderRank();renderProjects();});
    $('geoZoom').addEventListener('change',function(){setZoom(Number(this.value));});
    $('geoRankMode').querySelectorAll('button').forEach(function(b){b.addEventListener('click',function(){mode=b.dataset.mode; $('geoRankMode').querySelectorAll('button').forEach(function(x){x.classList.toggle('on',x===b);x.setAttribute('aria-pressed',String(x===b));});renderRank();});});
    // 全站样本结构单独计数，不能以地理收录子集替代市场全量。
    var counts=sectors.map(function(s){return {name:s,count:funds.filter(function(f){return f.sector===s;}).length};}).sort(function(a,b){return b.count-a.count;});
    $('geoSectorChart').innerHTML=counts.map(function(s,i){return '<div class="geo-sector-line"><span>'+esc(s.name)+'</span><div><i style="width:'+s.count/counts[0].count*100+'%;--sector-tone:'+['#3159ce','#3d7a9d','#54877b','#8775a7'][i%4]+'"></i></div><b>'+s.count+'</b><small>'+Math.round(s.count/funds.length*100)+'%</small></div>';}).join('');
    $('geoUniverseCount').textContent=funds.length+'只 · 站内行情样本';
    update();
  }
  function loadJson(url) { return fetch(url,{signal:AbortSignal.timeout(15000)}).then(function(r){if(!r.ok)throw new Error(url+': '+r.status);return r.json();}); }
  Promise.all([root.__DATA_READY || Promise.resolve(),loadJson('geography/sponsors.json?v=20260928-3')]).then(function(results){
    registry=results[1]; funds=(root.REITS_DATA||{}).reits;
    if(!Array.isArray(funds)||!funds.length) throw new Error('行情样本未加载');
    init();
    return loadJson('geography/china-provinces.json?v=1').then(function(data){geo=data;buildMap();renderMarkers();$('geoMapLoading').hidden=true;});
  }).catch(function(error){
    console.error('原始权益人地图加载失败',error);
    $('geoMapLoading').hidden=false;
    $('geoMapLoading').textContent='地图加载失败，请刷新重试。已载入的城市排名和项目清单仍可使用。';
    $('geoStatus').textContent='地图未完整加载。';
  });
})(typeof window!=='undefined'?window:globalThis);
