/* 招投标专用数据与新闻合并；核查时间和公告日期分开展示。 */
(function(root){
  'use strict';
  function merge(news, tenders) {
    var seen=new Map();
    (news||[]).concat(tenders||[]).forEach(function(row){
      var key=String(row.date)+'|'+String(row.title).replace(/\s+/g,'').toLowerCase();
      seen.set(key,row);
    });
    return Array.from(seen.values()).sort(function(a,b){return String(b.date).localeCompare(String(a.date));});
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={merge:merge};
  if(!root.document)return;
  // 数据状态角标（data-status.js）：status 非 ok 或核查超 30 小时 → 「缓存 · as-of 最新公告日」
  function markCard(host,state){var card=host&&host.closest('.card');if(card&&state&&root.ReitsDataStatus)root.ReitsDataStatus.apply(card,state);}
  function show(payload) {
    var host=document.getElementById('tenderStatus');
    host.replaceChildren();
    var line=document.createElement('p');
    line.textContent='招投标：'+(payload.status==='ok'?'主源已核查':payload.status==='degraded'?'主源未完整取得，部分来源可用':'本轮抓取失败，保留历史公告')+' · 最新公告 '+(payload.latestBulletinDate||'暂无')+' · 核查 '+String(payload.checkedAt||'未提供').replace('T',' ').slice(0,16)+'（北京时间）';
    host.append(line);
    var details=document.createElement('details'),summary=document.createElement('summary');
    summary.textContent='查看数据来源与更新状态';details.append(summary);
    var schedule=document.createElement('p');schedule.textContent=payload.schedule+'；展示最近90天公告。';details.append(schedule);
    (payload.sources||[]).forEach(function(source){var p=document.createElement('p');p.textContent=source.name+'：'+({ok:'核查成功',partial:'部分取得',failed:'未成功'}[source.status]||'待核查')+'，本轮 '+source.count+' 条；最近成功 '+(source.lastSuccessAt?source.lastSuccessAt.replace('T',' ').slice(0,16):'暂无')+'。'+(source.scope||'');details.append(p);});
    var age=Date.now()-Date.parse(payload.checkedAt);
    if(!Number.isFinite(age)||age>30*3600000){var warning=document.createElement('p');warning.textContent='招投标核查已超过30小时或时间缺失，请检查定时任务。';warning.className='tender-warning';host.prepend(warning);}
    markCard(host,root.ReitsDataStatus&&root.ReitsDataStatus.fromTenders(payload));
    var a=document.createElement('a');a.href='https://ctbpsp.com/#/bulletinList?keyWords=reits';a.target='_blank';a.rel='noopener';a.textContent='打开指定主源搜索页';details.append(a);host.append(details);
  }
  root.ReitsTenders={load:async function(news){
    var controller=new AbortController(),timer=setTimeout(function(){controller.abort();},12000);
    try{
      var response=await fetch('tenders.json',{cache:'no-cache',signal:controller.signal});
      if(!response.ok)throw new Error('招投标数据未加载');
      var data=await response.json();
      if(!Array.isArray(data.items)||!Array.isArray(data.sources))throw new Error('招投标数据格式异常');
      show(data);
      return Object.assign({},news,{items:merge(news.items,data.items),tags:Array.from(new Set((news.tags||['全部']).concat(['招投标'])))});
    }catch(error){var host=document.getElementById('tenderStatus');host.textContent='招投标专用数据暂不可用，当前显示新闻中的历史线索；请稍后刷新。';markCard(host,root.ReitsDataStatus&&root.ReitsDataStatus.make('cached',{note:'招投标专用数据未加载，显示新闻中的历史线索'}));return news;}
    finally{clearTimeout(timer);}
  }};
})(typeof window==='undefined'?globalThis:window);
