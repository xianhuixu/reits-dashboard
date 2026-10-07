/* 工作区交互：只读展示现有行情，不改变数据文件或财务模型。 */
(function (root) {
  'use strict';
  function normalizedSeries(series, days) {
    if (!series || !Array.isArray(series.dates) || !Array.isArray(series.market)) return [];
    var rows = series.dates.map(function (date, i) { return {date:date, value:series.market[i]}; })
      .slice(-days).filter(function (r) { return typeof r.date === 'string' && Number.isFinite(r.value) && r.value > 0; });
    var base = rows.length ? rows[0].value : 1;
    return rows.map(function (r) { return {date:r.date, value:r.value / base * 100}; });
  }

  // ---------------- 市场总览首屏派生（设计师线框 2026-09-30）：纯函数，node 下可测 ----------------
  var GROWTH_TXT = { "1": "增长高于趋势", "-1": "增长低于趋势", "0": "增长趋势附近" };
  var RATE_TXT = { up: "利率上行", down: "利率下行", flat: "利率走平" };
  var RATE_ARROW = { up: "↑", down: "↓", flat: "→" };
  var CLOCK_CELLS = [["Q2", "复苏"], ["Q1", "繁荣"], ["Q3", "衰退"], ["Q4", "滞胀"]];
  function num(v) { return typeof v === "number" && isFinite(v); }
  /** 带 Unicode 负号的有符号数：−7.4 / +0.12 */
  function sgnNum(v, d) { return !num(v) ? "—" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d == null ? 1 : d); }
  function noSignNum(v, d) { return !num(v) ? "—" : (v < 0 ? "−" : "") + Math.abs(v).toFixed(d == null ? 1 : d); }
  /** 「2026-09-30 11:50:33」→「09-30 11:50」 */
  function shortStamp(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/.exec(String(s || ""));
    return m ? m[2] + "-" + m[3] + (m[4] ? " " + m[4] + ":" + m[5] : "") : "—";
  }
  function fmtAmount(v) { return !num(v) ? "—" : v >= 1e8 ? (v / 1e8).toFixed(2) + " 亿" : v >= 1e4 ? Math.round(v / 1e4) + " 万" : String(Math.round(v)); }
  /** 结论横幅（时钟部分）：增长 / 利率文字、临界、信号切换。置信度不进横幅（放在时钟卡的灰色小标签）。 */
  function clockBanner(rc) {
    if (!rc || rc.status !== "ok") return { ok: false, growth: null, rate: null, critical: false, switchTag: false, switchNote: "", text: "增长 × 利率时钟未判定" };
    var g = rc.growth || {};
    var growth = GROWTH_TXT[String(g.state)] || "增长未判定";
    var rate = RATE_TXT[rc.rateDir] || "利率未判定";
    var gCrit = !!g.critical, rCrit = !!(rc.rateDistance && rc.rateDistance.critical);
    var sw = rc.signalSwitch && rc.signalSwitch.active ? rc.signalSwitch : null;
    return { ok: true, growth: growth, rate: rate, critical: gCrit || rCrit, criticalAxis: gCrit ? "growth" : rCrit ? "rate" : null,
      state: rc.state || null, quadrant: rc.quadrant || null, leanQuadrant: rc.leanQuadrant || null,
      switchTag: !!sw, switchNote: sw ? sw.note || "" : "", switchCause: sw ? sw.cause || null : null,
      text: growth + (gCrit ? "（临界）" : "") + " · " + rate + (rCrit ? "（临界）" : "") };
  }
  /** 时钟卡：大字 = 利率方向，迷你四象限，距切换线，增长轴 2 个月确认进度（圆点），置信度小标签。 */
  function clockCard(rc) {
    var b = clockBanner(rc);
    if (!b.ok) return { ok: false, big: "未判定", note: "10Y / PMI 真实序列未就绪" };
    var g = rc.growth || {}, dist = g.distance || {}, cf = g.confirm || null;
    var cells = CLOCK_CELLS.map(function (c) {
      return { q: c[0], label: c[1], on: rc.quadrant === c[0], lean: !rc.quadrant && rc.leanQuadrant === c[0] };
    });
    return { ok: true, big: b.rate, arrow: RATE_ARROW[rc.rateDir] || "", cells: cells,
      rateLine: "10Y 60日 " + sgnNum(rc.d10y60bp) + "bp，阈值 " + noSignNum(rc.thresholdBp) + "bp" + (rc.thresholdFloored ? "（下限）" : ""),
      rateHead: "10Y 60日 " + sgnNum(rc.d10y60bp) + "bp", rateThr: "阈值 " + noSignNum(rc.thresholdBp) + "bp" + (rc.thresholdFloored ? "（下限）" : ""),
      growthLine: "增长 z3 = " + noSignNum(g.z3, 2) + "σ（" + (GROWTH_TXT[String(g.state)] || "—").replace("增长", "") + "）",
      growthDist: num(dist.sigma) ? "距退出线 " + noSignNum(Math.max(0, dist.sigma), 2) + "σ" : "", critical: !!g.critical,
      confirm: cf ? { title: cf.title || "确认", count: cf.count || 0, need: cf.need || 2, label: cf.label || "" } : null,
      confidence: rc.confidence || null, quadrantName: rc.quadrant ? rc.quadrant + " " + (rc.quadrantName || "") : (rc.stateLabel || "") };
  }
  /** 产权利差分位卡：默认滚动 3 年分位；全样本分位放 title；propertySpread 真实序列优先。 */
  function spreadCard(panel) {
    var ps = panel && panel.propertySpread, L = ps && ps.latest, s = panel && panel.propertyYieldSeries;
    if (L && num(L.pctRolling3y)) {
      var series = s || [], last = series.length ? series[series.length - 1] : null, prev = series.length > 3 ? series[series.length - 4] : null;
      var pct = Math.round(L.pctRolling3y), full = num(L.pctFull) ? Math.round(L.pctFull) : null;
      var delta = last && prev && num(last.pctile) && num(prev.pctile) ? Math.round((last.pctile - prev.pctile) * 100) : null;
      return { ok: true, pctile: pct, pctileFull: full, spread: num(L.spreadBp) ? L.spreadBp / 100 : (last && last.spread),
        asOf: (ps && ps.asOf) || (last && last.date) || null, delta: delta,
        arrow: delta == null ? "" : delta > 0 ? "↑" : delta < 0 ? "↓" : "→",
        tip: "滚动 3 年分位 " + pct + "%" + (full != null ? " · 2022 年以来全样本 " + full + "%（早期截面仅 2–6 只，噪音大）" : "") +
          (num(L.ttmYieldMcap) ? " · TTM " + L.ttmYieldMcap + "% − 10Y " + L.y10 + "% = " + L.spreadBp + "bp" : "") };
    }
    if (!s || !s.length || !num(s[s.length - 1].pctile)) return { ok: false };
    var last2 = s[s.length - 1], prev2 = s.length > 3 ? s[s.length - 4] : null;
    var pct2 = Math.round(last2.pctile * 100);
    var delta2 = prev2 && num(prev2.pctile) ? Math.round((last2.pctile - prev2.pctile) * 100) : null;
    return { ok: true, pctile: pct2, pctileFull: last2.pctileFull != null ? Math.round(last2.pctileFull * 100) : null,
      spread: last2.spread, asOf: last2.date || panel.asOfTrade || null, delta: delta2,
      arrow: delta2 == null ? "" : delta2 > 0 ? "↑" : delta2 < 0 ? "↓" : "→", tip: "" };
  }
  /** 市场今日卡：指数日涨跌（缺失时用等权）、成交额、涨跌家数。 */
  function marketCard(data) {
    var rows = (data && data.reits) || [];
    var pcts = rows.map(function (r) { return r.pct; }).filter(num);
    var up = pcts.filter(function (v) { return v > 0; }).length, down = pcts.filter(function (v) { return v < 0; }).length;
    var eq = pcts.length ? pcts.reduce(function (a, b) { return a + b; }, 0) / pcts.length : null;
    var amt = rows.reduce(function (a, r) { return a + (num(r.amount) ? r.amount : 0); }, 0);
    var mi = (data && data.marketIndex) || null;
    var useIdx = !!(mi && num(mi.pct));
    return { ok: pcts.length > 0 || useIdx, pct: useIdx ? mi.pct : eq, source: useIdx ? "index" : "equal",
      name: useIdx ? mi.name || "中证REITs" : "全市场等权", code: useIdx ? String(mi.code || "").replace(/\.CSI$/, "") : "",
      close: mi && num(mi.close) ? mi.close : null, equalPct: eq, amount: amt, up: up, down: down, flat: pcts.length - up - down, count: rows.length };
  }
  /** 社融脉冲卡：数值、方向箭头、由正转负/由负转正的解读、数据截至。 */
  function tsfCard(t) {
    if (!t || t.status !== "ok" || !num(t.value)) return { ok: false };
    var flip = t.lastFlip && t.lastFlip.direction;
    var read = flip === "正转负" ? "由正转负 → 提示约半年后 REITs 环境改善" : flip === "负转正" ? "由负转正 → 提示约半年后 REITs 环境承压" : "只看方向，不并入增长轴";
    return { ok: true, value: t.value, prev: num(t.prev) ? t.prev : null, arrow: num(t.prev) ? (t.value > t.prev ? "↑" : t.value < t.prev ? "↓" : "→") : "",
      read: read, asOf: t.asOf || null, monthsBehind: t.monthsBehind == null ? null : t.monthsBehind };
  }
  /** 今日要点（≤3 条）：信号切换 / 时钟提示 → 领涨领跌 → 宽度与重估。返回 {text, parts} 供安全渲染。 */
  function todayPoints(data) {
    var out = [], rc = data && data.cycle && data.cycle.rateClock;
    var sw = rc && rc.signalSwitch && rc.signalSwitch.active ? rc.signalSwitch : null;
    if (sw) out.push({ kind: "switch", text: "投资时钟读数切换：" + (sw.from || "—") + " → " + (sw.to || "—") + "。" + (sw.note || "") });
    else if (rc && (rc.conflictFlags || []).length) out.push({ kind: "flag", text: "时钟提示（" + rc.conflictFlags[0].sector + "）：" + String(rc.conflictFlags[0].text || "").slice(0, 70) });
    var rows = ((data && data.reits) || []).filter(function (r) { return num(r.pct); });
    if (rows.length) {
      var hi = rows.reduce(function (a, r) { return r.pct > a.pct ? r : a; }), lo = rows.reduce(function (a, r) { return r.pct < a.pct ? r : a; });
      out.push({ kind: "movers", hi: { name: hi.name, code: hi.code, pct: hi.pct }, lo: { name: lo.name, code: lo.code, pct: lo.pct },
        text: "领涨 " + hi.name + " " + sgnNum(hi.pct, 2) + "% · 领跌 " + lo.name + " " + sgnNum(lo.pct, 2) + "%" });
      var m = marketCard(data), rv = (data && data.revaluation) || {};
      out.push({ kind: "breadth", text: "市场宽度 " + Math.round(m.up / rows.length * 100) + "% 上涨（" + m.up + " / " + m.down + "）" +
        (rv.stage ? " · 资产重估：" + rv.stage + "（" + (rv.score != null ? rv.score : "—") + "/4 项成立）" : "") });
    }
    return out.slice(0, 3);
  }

  // ---------------- 首页 / 配置页结论横幅（2026-09-30 团队反馈）----------------
  // 结论 = 时钟利率方向 → 学派立场 / stanceOverride（advice.json）。增长侧状态不进横幅（「临界」只在时钟卡上）。
  // 产权利差分位第二条依据：仅当 propertySpread.status === live 且 分派同比中位数 > −2% 时显示；
  // 否则在原位置留灰字说明原因（数据滞后 / 分派同比下滑）。种子 / 待接入模块不参与推导。
  var DSX = root.ReitsDataStatus || (typeof require === 'function' ? (function () { try { return require('./data-status.js'); } catch (e) { return null; } })() : null);
  function usable(s) { return !!s && (s.status === 'live' || s.status === 'cached'); }
  function monthLabel(asOf) { var m = /^\d{4}-(\d{2})/.exec(String(asOf || '')); return m ? Number(m[1]) + ' 月' : null; }
  /**
   * @param {object} data   data.json（cycle.rateClock / cycle.tsfImpulse / cycle.rateRentGate）
   * @param {string|null} stance  学派立场文字（schoolStance(advice).text）；只来自 advice.json
   * @param {object} [panel] data_panel_l1l7.json —— propertySpread 决定第二条依据是否显示
   * @param {object} [advice] advice.json —— stanceOverrideRationale 作降档解释
   */
  function bannerModel(data, stance, panel, advice) {
    var cy = (data && data.cycle) || {}, rc = cy.rateClock, tsf = cy.tsfImpulse, gate = cy.rateRentGate;
    var used = [], excluded = [];
    var rcS = DSX && DSX.fromRateClock ? DSX.fromRateClock(rc) : { status: rc && rc.status === 'ok' ? 'live' : 'pending' };
    var rate = null;
    if (rc && rc.status === 'ok' && usable(rcS) && RATE_TXT[rc.rateDir]) { rate = RATE_TXT[rc.rateDir]; used.push('rateClock.rate'); }
    else excluded.push('rateClock');
    var spreadBasis = null, spreadSkip = null;
    var ps = panel && panel.propertySpread, pS = DSX && DSX.fromPropertySpread ? DSX.fromPropertySpread(panel) : (ps ? { status: ps.status === 'ok' ? 'live' : 'lagged' } : { status: 'seed' });
    if (panel !== undefined) {
      if (ps && (ps.status === 'ok' || ps.status === 'lagged')) {
        var yoy = (ps.distYoY || {}).medianPct, pct = (ps.latest || {}).pctRolling3y, live = pS.status === 'live';
        var yoyOk = num(yoy) && yoy > -2;
        if (live && yoyOk && num(pct)) { spreadBasis = '产权利差分位 ' + Math.round(pct) + '%（滚动3年）'; used.push('propertySpread'); }
        else {
          var why = !live ? '数据滞后' : '分派同比下滑';
          if (!live && num(yoy) && yoy <= -2) why = '数据滞后 / 分派同比下滑';
          spreadSkip = '利差分位暂不参与（' + why + '）';
          excluded.push('propertySpread:' + (live ? 'distYoY' : pS.status));
        }
      } else {
        excluded.push('propertySpread:' + (pS ? pS.status : 'pending'));
        spreadSkip = '利差分位暂不参与（待接入真实序列）';
      }
    }
    var aux = null;
    var tS = DSX && DSX.fromTsfImpulse ? DSX.fromTsfImpulse(tsf) : { status: tsf && tsf.status === 'ok' ? 'live' : 'pending' };
    if (tsf && tsf.status === 'ok' && usable(tS) && num(tsf.value) && tsf.value < 0) {
      var turned = tsf.lastFlip && tsf.lastFlip.direction === '正转负';
      var mo = monthLabel(tsf.asOf);
      aux = '辅助：社融脉冲' + (turned ? '转负' : '为负') + '（低置信' + (mo ? '，数据截至 ' + mo : '') + '）';
      used.push('tsfImpulse');
    } else excluded.push('tsfImpulse');
    var basis = rate ? '依据：时钟·' + rate + (spreadBasis ? ' · ' + spreadBasis : '') : '依据：配置页学派立场';
    // 降档说明：stanceOverride 生效时，用租金 vs 利率对照解释为什么不是「产权超配」
    var overrideNote = null;
    if (advice && advice.stanceOverride) {
      var rl = (gate && gate.rentLeg) || (ps && ps.rentVsRate) || null;
      if (rl && rl.status && rl.status !== 'pending' && num(rl.rateTailwindBp) && num(rl.distDragBp)) {
        overrideNote = '降档理由：利率顺风 ' + sgnNum(rl.rateTailwindBp, 1) + 'bp（一年均值） vs 分派拖累 ' + sgnNum(rl.distDragBp, 1) + 'bp（' + (rl.text || '') + '）';
      } else if (advice.stanceOverrideRationale) overrideNote = '降档理由：' + String(advice.stanceOverrideRationale).slice(0, 80);
    }
    var conclusion = (rate || '时钟未判定') + ' → ' + (stance || '配置结论见配置页');
    return { rate: rate, stance: stance || null, conclusion: conclusion, basis: basis, spreadBasis: spreadBasis,
      spreadSkip: spreadSkip, overrideNote: overrideNote, aux: aux, used: used, excluded: excluded };
  }
  var HOME = {bannerModel:bannerModel, normalizedSeries:normalizedSeries, clockBanner:clockBanner, clockCard:clockCard, spreadCard:spreadCard, marketCard:marketCard, tsfCard:tsfCard, todayPoints:todayPoints, shortStamp:shortStamp, sgnNum:sgnNum, fmtAmount:fmtAmount};
  if (typeof module !== 'undefined' && module.exports) module.exports = HOME;
  if (!root.document) return;
  var doc = root.document, activeAdvice = 'advOverview', chart, series, days = 60;
  var $ = function (id) { return doc.getElementById(id); };
  var signed = function (v) { return (v > 0 ? '+' : '') + v.toFixed(2) + '%'; };
  function selectAdviceForTarget(target) {
    var panel = target && target.closest('#v-advice > article.card');
    if (!panel) panel = $(activeAdvice);
    if (!panel) return;
    activeAdvice = panel.id;
    doc.querySelectorAll('#v-advice > article.card').forEach(function (p) { p.hidden = p !== panel; });
    doc.querySelectorAll('#adviceSub button').forEach(function (b) {
      var active = b.dataset.scroll === panel.id;
      b.classList.toggle('on', active);
      if (active) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
  }
  function drawer(open) {
    doc.body.classList.toggle('sidebar-open', open);
    $('sidebarScrim').hidden = !open;
    $('sidebarToggle').setAttribute('aria-expanded', String(open));
    $('workspace').inert = open;
    $('sidebar').inert = !open && root.innerWidth < 768;
    if (open) $('tbNav').querySelector('button.on').focus();
  }
  var labels = {
    pano:['市场总览','从全市场表现，到每一项底层资产。'],
    research:['研究分析','价格、周期与资产基本面的多维观察。'],
    advice:['配置与风险','面向专业投资者的估值、现金流与风险监测框架。'],
    inst:['机构间市场','机构间REITs项目与市场动态。']
  };
  function pageChanged(pg) {
    var label = labels[pg] || labels.pano;
    $('workspaceTitle').textContent = $('workspaceLocation').textContent = label[0];
    $('workspaceSubtitle').textContent = label[1];
    $('exportMarket').hidden = pg !== 'pano';
    doc.querySelector('.heading-sketch').hidden = pg !== 'pano';
    selectAdviceForTarget($(activeAdvice));
    var wasOpen = doc.body.classList.contains('sidebar-open');
    drawer(false);
    if (wasOpen) $('workspaceMain').focus({preventScroll:true});
    if (chart) requestAnimationFrame(function () { chart.resize(); });
  }
  root.ReitsWorkspace = {selectAdviceForTarget:selectAdviceForTarget,pageChanged:pageChanged};
  function renderTrend() {
    var rows = normalizedSeries(series, days), el = $('workspaceTrend');
    if (!rows.length) { el.textContent = '历史序列暂不可用，请稍后刷新。'; return; }
    if (!el.clientWidth) return;
    // 首页单序列图使用原生 SVG；复杂研究图表继续按需使用 ECharts。
    if (!chart) chart = {resize:renderTrend};
    var last = rows[rows.length - 1];
    $('workspaceTrendValue').textContent = last.value.toFixed(2);
    $('workspaceTrendChange').textContent = signed(last.value - 100);
    $('workspaceTrendChange').className = last.value > 100 ? 'up' : last.value < 100 ? 'down' : 'flat';
    $('workspaceTrendPeriod').textContent = rows[0].date + ' — ' + last.date;
    var summary='全市场等权价格指数，区间首日100，区间变化'+signed(last.value-100)+'。左右键查看日期。';
    el.setAttribute('aria-label',summary); el.setAttribute('role','group'); el.tabIndex=0;
    var w=Math.max(280,el.clientWidth), h=Math.max(160,el.clientHeight), left=35, right=w-12, top=12, bottom=h-28;
    var values=rows.map(function(r){return r.value;}), min=Math.min.apply(null,values), max=Math.max.apply(null,values), pad=Math.max((max-min)*.1,.2);
    var low=min-pad, high=max+pad, x=function(i){return left+i/Math.max(1,rows.length-1)*(right-left);}, y=function(v){return bottom-(v-low)/(high-low)*(bottom-top);};
    var points=rows.map(function(r,i){return x(i).toFixed(2)+','+y(r.value).toFixed(2);});
    var grid='';
    for(var t=0;t<4;t++){var v=low+(high-low)*t/3, gy=y(v);grid+='<line class="trend-grid" x1="'+left+'" x2="'+right+'" y1="'+gy+'" y2="'+gy+'"/><text class="trend-axis" x="'+(left-8)+'" y="'+(gy+3)+'" text-anchor="end">'+v.toFixed(high-low<4?1:0)+'</text>';}
    [0,Math.floor((rows.length-1)/2),rows.length-1].forEach(function(i){grid+='<text class="trend-axis" x="'+x(i)+'" y="'+(h-7)+'" text-anchor="'+(i===0?'start':i===rows.length-1?'end':'middle')+'">'+esc(rows[i].date.slice(5))+'</text>';});
    el.innerHTML='<svg class="trend-svg" viewBox="0 0 '+w+' '+h+'" aria-hidden="true"><defs><linearGradient id="marketTrendFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--accent)" stop-opacity=".13"/><stop offset="1" stop-color="var(--accent)" stop-opacity=".01"/></linearGradient></defs>'+grid+'<path fill="url(#marketTrendFill)" d="M'+left+','+bottom+' L'+points.join(' L')+' L'+right+','+bottom+'Z"/><polyline class="trend-line" points="'+points.join(' ')+'"/><circle class="trend-endpoint" cx="'+x(rows.length-1)+'" cy="'+y(last.value)+'" r="3"/><g class="trend-cursor" visibility="hidden"><line x1="0" x2="0" y1="'+top+'" y2="'+bottom+'"/><circle r="4"/></g></svg><div class="trend-tooltip" hidden><b></b><span></span></div>';
    var svg=el.querySelector('svg'), cursor=el.querySelector('.trend-cursor'), tip=el.querySelector('.trend-tooltip'), index=rows.length-1;
    function inspect(i,keyboard){index=Math.max(0,Math.min(rows.length-1,i));var point=rows[index],px=x(index),py=y(point.value);cursor.setAttribute('visibility','visible');var line=cursor.querySelector('line');line.setAttribute('x1',px);line.setAttribute('x2',px);var dot=cursor.querySelector('circle');dot.setAttribute('cx',px);dot.setAttribute('cy',py);tip.hidden=false;tip.style.left=Math.min(w-142,Math.max(8,px-65))+'px';tip.style.top='0px';tip.querySelector('b').textContent=point.date;tip.querySelector('span').textContent='等权指数 '+point.value.toFixed(2);if(keyboard)el.setAttribute('aria-label',summary+' '+point.date+'，'+point.value.toFixed(2));}
    el.onpointermove=function(e){var box=svg.getBoundingClientRect(),px=(e.clientX-box.left)*w/box.width;inspect(Math.round((px-left)/(right-left)*(rows.length-1)),false);};
    el.onpointerleave=function(){cursor.setAttribute('visibility','hidden');tip.hidden=true;};
    el.onkeydown=function(e){var next=e.key==='ArrowLeft'?index-1:e.key==='ArrowRight'?index+1:e.key==='Home'?0:e.key==='End'?rows.length-1:null;if(next!==null){e.preventDefault();inspect(next,true);}};
    el.onblur=function(){cursor.setAttribute('visibility','hidden');tip.hidden=true;el.setAttribute('aria-label',summary);};
    $('workspaceTrendTable').querySelector('tbody').replaceChildren();
    rows.forEach(function(r){var tr=doc.createElement('tr'); [r.date,r.value.toFixed(2)].forEach(function(v){var td=doc.createElement('td');td.textContent=v;tr.append(td);});$('workspaceTrendTable').querySelector('tbody').append(tr);});
  }

  // ---------------- 市场总览首屏渲染 ----------------
  function esc(v) { return String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function pctSpan(v, d) { if (!num(v)) return '—'; var c = v > 0 ? 'up' : v < 0 ? 'down' : 'flat'; return '<span class="' + c + '">' + sgnNum(v, d == null ? 2 : d) + '%</span>'; }
  function dsApply(el, s) { if (root.ReitsDataStatus && root.ReitsDataStatus.apply) root.ReitsDataStatus.apply(el, s); }
  function cardShell(el, title, attrs, inner, state) {
    el.classList.remove('is-loading', 'is-empty', 'is-error', 'is-content-in');
    if (state === 'empty') el.classList.add('is-empty');
    else if (state === 'error') el.classList.add('is-error');
    el.removeAttribute('aria-busy');
    el.innerHTML = '<h3>' + esc(title) + '</h3><span class="ov-go" aria-hidden="true">详情 →</span>' + inner;
    Object.keys(attrs).forEach(function (k) { el.setAttribute(k, attrs[k]); });
    el.setAttribute('role', 'link'); el.tabIndex = 0;
    // 可见数据本身构成链接名称，避免短标签遮蔽完整状态。
    el.removeAttribute('aria-label');
    // design-r3: 150–200ms fade when real content replaces skeleton
    if (typeof el.offsetWidth === 'number') void el.offsetWidth;
    el.classList.add('is-content-in');
  }
  function cardSkeletonHtml(title) {
    return '<h3>' + esc(title) + '</h3>' +
      '<div class="ov-skel-block ov-skel-kpi" aria-hidden="true">&nbsp;</div>' +
      '<div class="ov-skel-block ov-skel-line" aria-hidden="true">&nbsp;</div>' +
      '<div class="ov-skel-block ov-skel-line short" aria-hidden="true">&nbsp;</div>';
  }
  function renderBanner(data, stance, panel, advice) {
    var rc = data.cycle && data.cycle.rateClock, b = clockBanner(rc), h = $('ovHeadline');
    if (!h) return;
    // 结论只含利率方向 → 学派立场 / stanceOverride；增长侧（含「临界」）不进横幅
    var m = bannerModel(data, stance || null, panel || null, advice || null);
    var headlineHtml = '<span class="ov-rate-label">' + esc(m.rate || '时钟未判定') + '</span><span class="ov-arrow" aria-hidden="true">→</span><span class="ov-stance">' +
      (stance ? esc(stance) : '<span class="ov-skel">配置结论读取中</span>') + '</span>';
    if (h.innerHTML !== headlineHtml) h.innerHTML = headlineHtml;
    var basisHtml = '<span class="ov-basis-main">' + esc(m.basis) + '</span>' +
      (m.spreadSkip ? '<small class="ov-basis-skip">' + esc(m.spreadSkip) + '</small>' : '') +
      (m.overrideNote ? '<small class="ov-basis-note">' + esc(m.overrideNote) + '</small>' : '') +
      (m.aux ? '<small class="ov-basis-aux">' + esc(m.aux) + '</small>' : '');
    ['ovBasis', 'advBasis'].forEach(function (id) { var el = $(id); if (el) { el.innerHTML = basisHtml; el.hidden = false; } });
    if ($('ovBasisSummary')) $('ovBasisSummary').innerHTML = esc(m.basis) + (m.spreadSkip ? '<small>' + esc(m.spreadSkip) + '</small>' : '');
    if ($('ovMethodLabel')) $('ovMethodLabel').textContent = m.overrideNote ? '判断依据与口径 · 含降档说明' : '判断依据与口径';
    $('ovUpdated').textContent = '数据更新于 ' + shortStamp(data.updated || data.lastTradeDate);
    if (b.switchTag) {
      $('ovSwitchTag').innerHTML = '<span class="ov-tag-switch" title="时钟读数较上一交易日发生切换">信号切换</span>';
      var note = $('ovSwitchNote');
      note.innerHTML = esc(b.switchNote || '时钟读数较上一交易日切换') + ' <button type="button" class="ov-link" data-ov-view="cycle" data-ov-anchor="rateClockRow">口径说明 →</button>';
      note.hidden = false;
      note.classList.remove('ov-switch-note-plain');
    } else {
      // 无切换时保留同一位置放口径入口，首屏高度不随信号变化（CLS≈0）
      var n2 = $('ovSwitchNote');
      n2.innerHTML = '时钟每日按 10Y 国债 60 日变化与 PMI 偏离趋势自动判定 <button type="button" class="ov-link" data-ov-view="cycle" data-ov-anchor="rateClockRow">口径说明 →</button>';
      n2.classList.add('ov-switch-note-plain'); n2.hidden = false;
    }
  }
  function renderHome(data, panel, stance, advice) {
    var rc = data.cycle && data.cycle.rateClock, DS = root.ReitsDataStatus;
    var rows = data.reits || [];
    var sectors = {}; rows.forEach(function (r) { if (r.sector) sectors[r.sector] = 1; });
    $('ovUniverse').textContent = '全市场 ' + rows.length + ' 只 · ' + Object.keys(sectors).length + ' 个业态';
    var rv = data.revaluation;
    if (rv && rv.stage) $('ovReval').innerHTML = '<button type="button" class="ov-link ov-link-sub" data-ov-view="cycle" data-ov-anchor="revalFull">资产重估：' + esc(rv.stage) + ' · ' + esc(rv.score) + '/4 →</button>';
    renderBanner(data, stance || null, panel || null, advice || null);
    // 1 · 投资时钟
    var c = clockCard(rc), el = $('ovCardClock');
    if (el) {
      var inner;
      var cardState = null;
      if (!c.ok) { cardState = 'empty'; inner = '<div class="ov-state-empty"><div class="ov-big ov-big-text">' + esc(c.big) + '</div><p class="ov-note">' + esc(c.note) + '</p></div>'; }
      else {
        inner = '<div class="ov-mini-clock" aria-hidden="true">' + c.cells.map(function (x) { return '<span class="' + (x.on ? 'on' : x.lean ? 'lean' : '') + '">' + x.label + '</span>'; }).join('') + '</div>' +
          '<div class="ov-big ov-big-text">' + esc(c.big) + ' <span class="ov-dir" aria-hidden="true">' + esc(c.arrow) + '</span></div>' +
          '<p class="ov-note"><span class="ov-nw">' + esc(c.rateHead) + '，</span><span class="ov-nw">' + esc(c.rateThr) + '</span></p>' +
          '<p class="ov-note"><span class="ov-nw">' + esc(c.growthLine) + '</span>' + (c.growthDist ? ' <span class="ov-nw' + (c.critical ? ' ov-crit' : '') + '">' + esc(c.growthDist) + '</span>' : '') +
          (c.critical ? ' <span class="rc-tag rc-tag-warn ov-tag-sm" title="增长 z3 距退出线不足 0.05σ">临界</span>' : '') + '</p>';
        if (c.confirm) {
          var dots = ''; for (var i = 0; i < c.confirm.need; i++) dots += '<i class="' + (i < c.confirm.count ? 'on' : '') + '"></i>';
          inner += '<div class="ov-confirm"><span class="ov-dots" aria-hidden="true">' + dots + '</span><b>' + esc(c.confirm.title) + ' ' + c.confirm.count + '/' + c.confirm.need + '</b><small>' + esc(c.confirm.label) + '</small></div>';
        }
        inner += '<div class="ov-foot">' + (c.confidence ? '<span class="ov-pill ov-pill-grey">置信度 ' + esc(c.confidence) + '</span>' : '') + '<span>' + esc(c.quadrantName) + '</span></div>';
      }
      cardShell(el, '投资时钟', { 'data-ov-view': 'cycle', 'data-ov-anchor': 'rateClockRow' }, inner, cardState);
      if (DS && DS.fromRateClock) dsApply(el, DS.fromRateClock(rc));
    }
    // 2 · 产权利差分位
    var sp = spreadCard(panel); el = $('ovCardSpread');
    if (el) {
      var spInner, spState = null;
      if (!sp.ok) {
        spState = 'empty';
        spInner = '<div class="ov-state-empty"><div class="ov-big">—</div><p class="ov-note">利差序列待接入</p></div>';
      } else {
        spInner = '<div class="ov-big">' + sp.pctile + '%<small>分位</small>' + (sp.arrow ? '<span class="ov-dir" aria-hidden="true">' + sp.arrow + '</span>' : '') + '</div>' +
          '<p class="ov-note">利差 ' + (num(sp.spread) ? sp.spread.toFixed(2) + '%' : '—') + (sp.delta != null ? ' · 较 3 个月前 ' + sgnNum(sp.delta, 0) + 'pp' : '') +
          (sp.pctileFull != null ? ' · 全样本 ' + sp.pctileFull + '%' : '') + '</p>' +
          '<div class="ov-bar" role="img" aria-label="滚动 3 年分位 ' + sp.pctile + '%"><i style="width:' + sp.pctile + '%"></i></div>' +
          '<p class="ov-note ov-note-gap">默认滚动 3 年分位；越高 = 相对债券越便宜</p><div class="ov-foot"><span>截至 ' + esc(sp.asOf || '—') + '</span></div>';
      }
      cardShell(el, '产权利差分位', { 'data-ov-view': 'strategy', 'data-ov-anchor': 'panelL2Spreads', 'title': sp.tip || '' }, spInner, spState);
      if (DS && DS.fromPropertySpread) dsApply(el, DS.fromPropertySpread(panel));
    }
    // 3 · 市场今日
    var m = marketCard(data); el = $('ovCardMarket');
    if (el) {
      cardShell(el, '最近交易日', { 'data-ov-view': 'sector', 'data-ov-anchor': 'v-sector' },
        '<div class="ov-big">' + pctSpan(m.pct) + '</div>' +
        '<p class="ov-note">' + esc(m.name) + (m.code ? ' ' + esc(m.code) : '') + (m.close != null ? ' · ' + m.close.toFixed(2) : '') + '</p>' +
        '<p class="ov-note">成交额 <b>' + fmtAmount(m.amount) + '</b></p>' +
        '<p class="ov-note">上涨 <b class="up no-arrow">' + m.up + '</b> · 下跌 <b class="down no-arrow">' + m.down + '</b> · 平 ' + m.flat + '</p>' +
        '<div class="ov-foot"><span>' + (m.source === 'index' ? '等权 ' + pctSpan(m.equalPct) : '指数缺失，按等权计') + '</span></div>');
      if (DS && DS.fromMarketIndex) dsApply(el, DS.fromMarketIndex(data.marketIndex, data.lastTradeDate));
    }
    // 4 · 社融脉冲
    var tsf = data.cycle && data.cycle.tsfImpulse, t = tsfCard(tsf); el = $('ovCardTsf');
    if (el) {
      var tInner, tState = null;
      if (!t.ok) {
        tState = 'empty';
        tInner = '<div class="ov-state-empty"><div class="ov-big">—</div><p class="ov-note">社融序列待接入</p></div>';
      } else {
        tInner = '<div class="ov-big">' + noSignNum(t.value, 2) + '%' + (t.arrow ? '<span class="ov-dir" aria-hidden="true">' + t.arrow + '</span>' : '') + '</div>' +
          '<p class="ov-note">上期 ' + (t.prev != null ? noSignNum(t.prev, 2) + '%' : '—') + '</p>' +
          '<p class="ov-note"><b>' + esc(t.read) + '</b></p>' +
          '<div class="ov-foot"><span class="ov-pill">领先 5–7 个月</span><span>数据截至 ' + esc(t.asOf || '—') + (t.monthsBehind ? '（滞后 ' + t.monthsBehind + ' 个月）' : '') + '</span></div>';
      }
      cardShell(el, '社融脉冲 · 领先预警', { 'data-ov-view': 'cycle', 'data-ov-anchor': 'tsfImpulseCard' }, tInner, tState);
      if (DS && DS.fromTsfImpulse) dsApply(el, DS.fromTsfImpulse(tsf));
    }
    // 今日要点
    var ul = $('ovPoints');
    if (ul) {
      ul.innerHTML = todayPoints(data).map(function (p) {
        if (p.kind === 'movers') return '<li>领涨 <b>' + esc(p.hi.name) + '</b> ' + pctSpan(p.hi.pct) + ' · 领跌 <b>' + esc(p.lo.name) + '</b> ' + pctSpan(p.lo.pct) + '</li>';
        return '<li>' + (p.kind === 'switch' ? '<b>信号切换</b> · ' : '') + esc(p.kind === 'switch' ? p.text.replace(/^投资时钟读数切换：/, '时钟读数 ') : p.text) + '</li>';
      }).join('') || '<li>暂无要点</li>';
    }
  }
  function goView(view, anchor) {
    var btn = doc.querySelector('#subbar [data-v="' + view + '"]');
    if (btn) btn.click();
    if (!anchor) return;
    var tries = 0;
    (function seek() {
      var a = $(anchor);
      if (a && a.offsetParent !== null) {
        // 研究页图表/数据异步渲染会改变上方高度：短时间内复位几次，用户一旦滚动即停止
        var userMoved = false, stop = function () { userMoved = true; };
        root.addEventListener('wheel', stop, { once: true, passive: true }); root.addEventListener('touchstart', stop, { once: true, passive: true });
        [0, 250, 600, 1200, 2000].forEach(function (ms) { setTimeout(function () { if (!userMoved) a.scrollIntoView({ block: 'start' }); }, ms); });
        return;
      }
      if (++tries < 40) setTimeout(seek, 75);
    })();
  }
  function bindHomeNav() {
    doc.addEventListener('click', function (e) {
      var t = e.target.closest('[data-ov-view],[data-ov-page]');
      if (!t) return;
      if (t.dataset.ovPage) { var nav = doc.querySelector('#tbNav [data-pg="' + t.dataset.ovPage + '"]'); if (nav) nav.click(); root.scrollTo({ top: 0, behavior: 'auto' }); return; }
      e.preventDefault(); goView(t.dataset.ovView, t.dataset.ovAnchor);
    });
    doc.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      var t = e.target.closest && e.target.closest('.ov-card[role="link"]');
      if (!t || t !== e.target) return;
      e.preventDefault(); t.click();
    });
  }
  var sectorKey = 'pct';
  function renderSectors(rows) {
    var groups = {}; rows.forEach(function (r) { var v = r[sectorKey]; if (num(v)) { (groups[r.sector] = groups[r.sector] || []).push(v); } });
    var sectors = Object.keys(groups).map(function (k) { return { name: k, value: groups[k].reduce(function (a, b) { return a + b; }, 0) / groups[k].length }; }).sort(function (a, b) { return b.value - a.value; });
    var max = Math.max.apply(null, sectors.map(function (r) { return Math.abs(r.value); }).concat([.01]));
    $('workspaceSectors').replaceChildren();
    sectors.forEach(function (r) {
      var b = doc.createElement('button'); b.className = 'sector-line';
      var label = doc.createElement('span'); label.className = 'sector-label'; label.textContent = r.name;
      var track = doc.createElement('span'); track.className = 'sector-track';
      var bar = doc.createElement('i'); bar.style.width = Math.abs(r.value) / max * 100 + '%'; bar.style.background = 'var(--' + (r.value >= 0 ? 'up' : 'down') + ')'; track.append(bar);
      var value = doc.createElement('span'); value.className = 'sector-value ' + (r.value > 0 ? 'up' : r.value < 0 ? 'down' : 'flat'); value.textContent = sgnNum(r.value, 2) + '%';
      b.append(label, track, value);
      b.title = r.name + ' ' + (sectorKey === 'pct' ? '最近交易日' : '近 1 月') + ' ' + value.textContent;
      b.addEventListener('click', function () { var chip = Array.from(doc.querySelectorAll('#hmSectorChips button')).find(function (x) { return x.dataset.s === r.name; }); if (chip) chip.click(); $('heatmapCard').scrollIntoView({ block: 'start' }); });
      $('workspaceSectors').append(b);
    });
  }
  function loadTrendLazily() {
    var el = $('workspaceTrend'), started = false;
    function start() {
      if (started) return; started = true;
      function history(url){return fetch(url).then(function(r){if(!r.ok)throw new Error('历史数据加载失败');return r.json();});}
      history('market-series.json').then(function(data){if(data.asOf!==(root.REITS_DATA||{}).lastTradeDate)throw new Error('轻量序列时点不匹配');return data;})
        .catch(function(){return history('data_research.json').then(function(data){return data.series;});})
        .then(function(data){series=data;renderTrend();})
        .catch(function (error) { el.textContent = '历史序列暂不可用，请刷新重试。'; console.warn(error.message); });
    }
    if (!root.IntersectionObserver) return start();
    var io = new IntersectionObserver(function (en) { if (en.some(function (x) { return x.isIntersecting; })) { io.disconnect(); start(); } }, { rootMargin: '200px' });
    io.observe(el);
  }
  function init() {
    bindHomeNav();
    selectAdviceForTarget($(activeAdvice)); drawer(false);
    // 示意图只切换解释，不读取或改写财务模型。
    var explanations = {
      cash: ['经营收益：先核查收入与经营成本的同口径变化，再判断利润是否有现金支持。','实际回款：核对应收账龄、收缴和预收款，区分本期经营与跨期收付。','可分配现金：逐项核对披露调整表，关注维护开支、债务服务与现金预留。','每份分派：核对实际分派金额和对应份额，区分期间差异与扩募影响。'],
      risk: ['资产运营：观察量价、收缴与维护支出的变化，识别其对未来可分派现金的影响。','估值传导：分别检验现金流预测和折现率的变化，结合剩余期限与合同残值评估价值。','组合约束：穿透共同风险来源，并用成交容量、参与率和持仓核算退出天数。']
    };
    ['cash','risk'].forEach(function(kind){
      doc.querySelectorAll('[data-'+kind+'-step]').forEach(function(button){button.addEventListener('click',function(){
        doc.querySelectorAll('[data-'+kind+'-step]').forEach(function(b){b.classList.toggle('on',b===button);b.setAttribute('aria-pressed',String(b===button));});
        $(kind+'Explanation').textContent=explanations[kind][Number(button.getAttribute('data-'+kind+'-step'))];
      });});
    });
    doc.querySelectorAll('[data-right-scene]').forEach(function(button){button.addEventListener('click',function(){
      var property=button.dataset.rightScene==='property';
      doc.querySelectorAll('[data-right-scene]').forEach(function(b){b.classList.toggle('on',b===button);b.setAttribute('aria-pressed',String(b===button));});
      $('terminalLabel').textContent=property?'期末价值':'合同到期';
      $('terminalValue').textContent=property?'需评估':'核查残值';
      $('rightsExplanation').textContent=property?'产权类：以可持续分派与资产价值交叉核验，仍须考虑土地剩余年限、资本开支和退出假设。':'经营权类：分派可能包含本金的经济回收；按剩余期限求解IRR，期末回收价值须有合同依据。';
    });});
    if (root.IntersectionObserver) {
      var reveal=new IntersectionObserver(function(entries){entries.forEach(function(entry){if(entry.isIntersecting){entry.target.classList.add('is-revealed');reveal.unobserve(entry.target);}});},{threshold:.15});
      doc.querySelectorAll('.visual-reveal,.research-sketch').forEach(function(el){reveal.observe(el);});
    }

    $('sidebarToggle').addEventListener('click',function(){drawer(true);});
    $('tbNav').addEventListener('click',function(e){if(e.target.closest('button[data-pg]'))drawer(false);});
    $('sidebarScrim').addEventListener('click',function(){drawer(false);$('sidebarToggle').focus();});
    doc.addEventListener('keydown',function(e){
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {e.preventDefault();drawer(false);$('gSearch').focus();}
      if (!doc.body.classList.contains('sidebar-open')) return;
      if(e.key==='Escape'){drawer(false);$('sidebarToggle').focus();}
      if(e.key==='Tab') {var items=Array.from($('sidebar').querySelectorAll('a,button')).filter(function(x){return !x.disabled;});var i=items.indexOf(doc.activeElement);if(e.shiftKey&&i<=0){e.preventDefault();items[items.length-1].focus();}else if(!e.shiftKey&&i===items.length-1){e.preventDefault();items[0].focus();}}
    });
    doc.querySelectorAll('[data-advice-target]').forEach(function(b){b.addEventListener('click',function(){doc.querySelector('#tbNav [data-pg="advice"]').click();selectAdviceForTarget($(b.dataset.adviceTarget));window.scrollTo({top:0,behavior:'auto'});});});
    doc.querySelectorAll('[data-jump-view]').forEach(function(b){b.addEventListener('click',function(){var target=doc.querySelector('#subbar [data-v="'+b.dataset.jumpView+'"]');if(target)target.click();});});
    $('workspaceRange').addEventListener('click',function(e){var b=e.target.closest('[data-days]');if(!b)return;days=Number(b.dataset.days);this.querySelectorAll('button').forEach(function(x){x.classList.toggle('on',x===b);x.setAttribute('aria-pressed',String(x===b));});renderTrend();});
    new MutationObserver(function(){if(series)renderTrend();}).observe(doc.documentElement,{attributes:true,attributeFilter:['data-theme']});
    root.addEventListener('resize',function(){if(chart)chart.resize();if(root.innerWidth>=768)drawer(false);else if(!doc.body.classList.contains('sidebar-open'))$('sidebar').inert=true;});
    if(root.ResizeObserver)new ResizeObserver(function(){if(chart&&$('workspaceTrend').clientWidth)chart.resize();}).observe($('workspaceTrend'));
    root.__DATA_READY.then(function(){
      var data=root.REITS_DATA, rows=data.reits||[];
      $('workspaceDate').textContent=data.lastTradeDate||'日期未提供';
      Array.from($('kpis').children).slice(4).forEach(function(el){$('marketContext').append(el);});
      renderSectors(rows);
      $('sectorRange').addEventListener('click',function(e){var b=e.target.closest('[data-k]');if(!b)return;sectorKey=b.dataset.k;this.querySelectorAll('button').forEach(function(x){x.classList.toggle('on',x===b);x.setAttribute('aria-pressed',String(x===b));});renderSectors(rows);});
      rows.filter(function(r){return Number.isFinite(r.amount);}).sort(function(a,b){return b.amount-a.amount;}).slice(0,5).forEach(function(r){var b=doc.createElement('button');b.className='active-asset';var name=doc.createElement('span');name.textContent=r.name;var pct=doc.createElement('span');pct.textContent=Number.isFinite(r.pct)?signed(r.pct):'—';var code=doc.createElement('small');code.textContent=r.code;var amount=doc.createElement('span');amount.textContent=(r.amount/1e4).toFixed(0)+' 万元';b.append(name,pct,code,amount);b.addEventListener('click',function(){root.location.hash='/detail/'+r.code;});$('workspaceActive').append(b);});
      $('exportMarket').addEventListener('click',function(){var csv=[['代码','名称','板块','收盘价','当日涨跌幅(%)','成交额(元)']].concat(rows.map(function(r){return [r.code,r.name,r.sector,r.close,r.pct,r.amount];})).map(function(row){return row.map(function(v){return '"'+String(v==null?'':v).replace(/"/g,'""')+'"';}).join(',');}).join('\r\n');var url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'}));var a=doc.createElement('a');a.href=url;a.download='REITs行情-'+data.lastTradeDate+'.csv';a.click();setTimeout(function(){URL.revokeObjectURL(url);},1000);});
      loadTrendLazily();
    }).catch(function(){pageChanged('advice');$('workspaceDate').textContent='行情暂不可用';});
  }

  // 首屏结论：脚本执行时 DOM 已解析（defer），数据 + 面板 + advice 就绪即一次性渲染（横幅只渲染一次，避免文字增长造成 CLS）
  (function earlyHome() {
    if (!root.__DATA_READY) return;
    var soft = function (p) { return p ? p.then(function (x) { return x; }, function () { return null; }) : Promise.resolve(null); };
    var advice = soft(root.__ADVICE_READY);
    var advTimed = Promise.race([advice, new Promise(function (r) { setTimeout(function () { r(null); }, 2500); })]);
    function stanceOf(adv) { var api = root.ReitsAllocation; var st = adv && api && api.schoolStance ? api.schoolStance(adv) : null; return st && st.text || null; }
    root.__DATA_READY.then(function () {
      return Promise.all([soft(root.__PANEL_READY), advTimed]);
    }).then(function (res) {
      var data = root.REITS_DATA; if (!data || !$('ovHero')) return;
      var panel = root.REITS_DATA_PANEL || null, adv = res[1];
      renderHome(data, panel, stanceOf(adv) || (adv ? '配置结论见配置页' : null), adv || null);
      if (!adv) advice.then(function (a) { renderBanner(data, stanceOf(a) || '配置结论见配置页', panel, a); });
    }).catch(function (e) { if (root.console) console.warn('首屏渲染失败', e); });
  })();
  doc.addEventListener('DOMContentLoaded',init);
})(typeof window==='undefined'?globalThis:window);
