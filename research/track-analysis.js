/* Isolated 赛道透视 renderer. Does not mutate REITS_DATA, advice or signals. */
(function (root) {
  "use strict";
  var DATA = null;
  var loading = false;
  var metricId = "occupancy_rate";
  var sectorId = "产业园";
  var SECTOR_ORDER = ["产业园", "消费", "商业不动产", "仓储物流", "保租房", "高速公路", "能源", "数据中心", "市政环保", "供热"];
  var charts = {};

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function fmt(v, digits) {
    if (v == null || typeof v !== "number" || !isFinite(v)) return "本期无匹配口径数据";
    return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: digits == null ? 2 : digits, minimumFractionDigits: 0 }).format(v);
  }
  function cssVal(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "";
  }
  function theme() {
    return {
      tx: cssVal("--tx") || "#e8edf4",
      tx2: cssVal("--tx2") || "#b4c0d0",
      tx3: cssVal("--tx3") || "#8a93a0",
      accent: cssVal("--accent") || "#3b82f6",
      grid: cssVal("--grid") || "#243044",
      def: cssVal("--def") || "#60a5fa",
      cyc: cssVal("--cyc") || "#f59e0b",
      gro: cssVal("--gro") || "#34d399",
      warn: cssVal("--warn") || "#f59e0b",
      risk: cssVal("--risk") || "#e11d48"
    };
  }
  function dispose() {
    Object.keys(charts).forEach(function (id) {
      try { if (charts[id] && !charts[id].isDisposed()) charts[id].dispose(); } catch (e) {}
    });
    charts = {};
  }
  var pendingCharts = {};
  var retryTimer = null;

  function visible() {
    return $("v-track") && !$("v-track").hidden && $("pg-research") && !$("pg-research").hidden;
  }
  function retryCharts() {
    if (retryTimer || !visible()) return;
    retryTimer = setTimeout(function () {
      retryTimer = null;
      if (!visible()) return;
      Object.keys(pendingCharts).forEach(function (id) { setChart(id, pendingCharts[id]); });
    }, 100);
  }
  function setChart(id, option) {
    var el = $(id);
    if (!el || !root.echarts) return;
    if (el.hidden) { delete pendingCharts[id]; return; }
    pendingCharts[id] = option;
    if (!visible() || el.offsetWidth === 0 || el.offsetHeight === 0) { retryCharts(); return; }
    var inst = charts[id];
    // An earlier failed setOption must not poison later mounts (ECharts internal scheduler).
    try {
      if (!inst || inst.isDisposed() || root.echarts.getInstanceByDom(el) !== inst) {
        inst = root.echarts.getInstanceByDom(el) || root.echarts.init(el, null, { renderer: "canvas" });
        charts[id] = inst;
      }
      inst.setOption(option, true);
      inst.resize();
      inst.off("click");
      inst.on("click", function (p) { if (p.data && p.data.fund && p.data.fund.code) root.location.hash = "#/detail/" + p.data.fund.code; });
      delete pendingCharts[id];
      return inst;
    } catch (e) {
      try { if (inst) inst.dispose(); } catch (_) {}
      delete charts[id];
      console.error("[track-chart:" + id + "]", e);
      return null;
    }
  }
  function loadPack() {
    if (DATA) return Promise.resolve(DATA);
    if (loading) return loading;
    loading = fetch("research/track-analysis.json").then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (j) {
      if (!j || j.schemaVersion !== 1) throw new Error("赛道聚合版本不兼容");
      DATA = j;
      loading = false;
      return j;
    }).catch(function (e) {
      loading = false;
      throw e;
    });
    return loading;
  }
  function metricSpec() {
    return (DATA.metrics || []).find(function (m) { return m.id === metricId; }) || DATA.metrics[0];
  }
  function metricApplies(metric, sector) {
    var pack = DATA.latest[metric.id] || {};
    return (pack.sectors || []).some(function (s) { return s.sector === sector; }) ||
      (pack.excludedListing || []).some(function (f) { return f.sector === sector; });
  }
  function sectorNames() {
    var names = [];
    DATA.metrics.forEach(function (m) {
      var pack = DATA.latest[m.id];
      (pack.sectors || []).concat(pack.excludedListing || []).forEach(function (s) {
        if (names.indexOf(s.sector) < 0) names.push(s.sector);
      });
    });
    return names.sort(function (a, b) {
      var ai = SECTOR_ORDER.indexOf(a), bi = SECTOR_ORDER.indexOf(b);
      return (ai < 0 ? 100 : ai) - (bi < 0 ? 100 : bi) || a.localeCompare(b);
    });
  }
  function selectSector(id) {
    if (!DATA || sectorNames().indexOf(id) < 0) return;
    sectorId = id;
    var current = metricSpec();
    if (!metricApplies(current, sectorId)) metricId = DATA.metrics.find(function (m) { return metricApplies(m, sectorId); }).id;
    render();
  }
  function renderSwitch() {
    var sectorHost = $("trackSectorSwitch");
    if (sectorHost) {
      sectorHost.innerHTML = sectorNames().map(function (name) {
        return '<button type="button" data-sector="' + esc(name) + '" aria-pressed="' + (name === sectorId) + '"' +
          (name === sectorId ? ' class="on"' : '') + '>' + esc(name) + '</button>';
      }).join('');
      sectorHost.onclick = function (e) {
        var b = e.target.closest && e.target.closest('button[data-sector]');
        if (b) selectSector(b.dataset.sector);
      };
    }
    var host = $("trackMetricSwitch");
    if (!host || !DATA) return;
    host.innerHTML = DATA.metrics.filter(function (m) { return metricApplies(m, sectorId); }).map(function (m) {
      var sector = (DATA.latest[m.id].sectors || []).find(function (s) { return s.sector === sectorId; });
      var n = sector ? sector.n : 0;
      return '<button type="button" data-metric="' + esc(m.id) + '"' +
        (m.id === metricId ? ' class="on" aria-pressed="true"' : ' aria-pressed="false"') +
        '>' + esc(m.label) + ' · ' + n + '</button>';
    }).join("");
    host.onclick = function (e) {
      var b = e.target && e.target.closest && e.target.closest("button[data-metric]");
      if (!b) return;
      metricId = b.dataset.metric;
      render();
    };
  }
  function baseAxis(th) {
    return {
      axisLabel: { color: th.tx3, fontSize: 11 },
      axisLine: { lineStyle: { color: th.grid } },
      splitLine: { lineStyle: { color: th.grid } }
    };
  }
  function renderQuality() {
    var spec = metricSpec();
    var pack = DATA.latest[spec.id] || { sectors: [] };
    var sectors = (pack.sectors || []).filter(function (s) { return s.sector === sectorId; });
    var th = theme();
    var meta = $("trackQualityMeta");
    if (meta) {
      meta.textContent = sectorId + " · 报告期 " + (pack.period || DATA.latestPeriod) +
        " · 口径 " + spec.caliber + " · 单位 " + spec.unit_label +
        " · 税标记 " + spec.tax_flag +
        " · " + (spec.weighting_note || "") +
        " · 来源：经营数据快照（chinareits 入库） · 每次仅展示当前赛道，切换指标不叠加异质单位";
    }
    var stats = $("trackStats");
    if (stats) stats.innerHTML = sectors.map(function (s) {
      return '<div><small>匹配口径 / 期末上市适用基金</small><strong>' + s.n + ' / ' + s.universe + '</strong></div>' +
        '<div><small>本期无匹配口径数据</small><strong>' + s.undisclosed + ' 只</strong></div>' +
        '<div><small>' + (s.n === 1 ? '单基金原值' : '中位数') + '（' + esc(spec.unit_label) + '）</small><strong>' + (s.pointOnly ? '不汇总' : fmt(s.medianDisplay)) + '</strong></div>' +
        '<div><small>最低 — 最高（' + esc(spec.unit_label) + '）</small><strong>' + (s.pointOnly ? '不排名' : (fmt(displayMin(s)) + ' — ' + fmt(displayMax(s)))) + '</strong></div>';
    }).join('');
    var aggregated = sectors.filter(function (s) { return !s.pointOnly && s.n > 1; });
    $("trackMedianChart").hidden = aggregated.length === 0;
    var summary = $("trackSampleNote");
    if (summary) summary.textContent = sectors.some(function (s) { return s.pointOnly; }) ? "能源子业态待核：仅列基金点，不计算全能源中位数、极值排名或趋势。" :
      sectors.some(function (s) { return s.n === 1; }) ? "仅 1 只匹配基金，只列单基金原值，不硬造分布。" :
      sectors.some(function (s) { return s.n === 0; }) ? "本期无匹配口径数据；不画空分布，不作 0。" : "当前赛道内基金等权分布，可点击散点进入档案；极值不等于经营优劣。";
    $("trackDispersionChart").hidden = !sectors.some(function (s) { return s.n; });
    var names = sectors.map(function (s) { return s.sector; }).reverse();
    var medianNames = aggregated.map(function (s) { return s.sector; }).reverse();
    var medians = aggregated.map(function (s) { return s.medianDisplay; }).reverse();
    var ns = aggregated.map(function (s) { return s.n; }).reverse();
    setChart("trackMedianChart", {
      color: [th.accent],
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 72, right: 56, top: 16, bottom: 28 },
      xAxis: Object.assign({ type: "value", name: spec.unit_label, nameTextStyle: { color: th.tx3 } }, baseAxis(th)),
      yAxis: Object.assign({ type: "category", data: medianNames }, baseAxis(th), { splitLine: { show: false } }),
      series: [{
        type: "bar", name: "中位数（基金等权）", data: medians, barMaxWidth: 18,
        label: { show: true, position: "right", color: th.tx2, fontSize: 10,
          formatter: function (p) { return fmt(p.value) + " · n=" + ns[p.dataIndex]; } }
      }]
    });
    var scatter = [];
    sectors.forEach(function (s) {
      (s.funds || []).forEach(function (f) {
        scatter.push({ value: [f.display, s.sector], fund: f });
      });
    });
    var inst = setChart("trackDispersionChart", {
      title: spec.id === "occupancy_rate" ? { text: "基金等权、非面积加权", left: 72, top: 0, textStyle: { color: th.tx3, fontSize: 11, fontWeight: 400 } } : undefined,
      color: [th.accent],
      tooltip: {
        trigger: "item",
        formatter: function (p) {
          var f = p.data && p.data.fund;
          if (!f) return "";
          return esc(f.name) + "<br/>" + esc(f.code) + " · " + esc(f.sector) +
            "<br/>" + esc(spec.label) + " " + fmt(f.display) + " " + esc(spec.unit_label) +
            (f.expansionInPeriod ? "<br/>本期窗口内有扩募纳入" : "") +
            "<br/>点击打开基金档案";
        }
      },
      grid: { left: 72, right: 24, top: spec.id === "occupancy_rate" ? 28 : 16, bottom: 36 },
      xAxis: Object.assign({ type: "value", name: spec.unit_label, nameTextStyle: { color: th.tx3 } }, baseAxis(th)),
      yAxis: Object.assign({ type: "category", data: names }, baseAxis(th), { splitLine: { show: false } }),
      series: [{
        type: "scatter", symbolSize: 11,
        data: scatter,
        name: spec.label
      }]
    });
    if (inst) {
      inst.off("click");
      inst.on("click", function (p) {
        var f = p.data && p.data.fund;
        if (f && f.code) root.location.hash = "#/detail/" + f.code;
      });
    }
    var fundTable = $("trackFundTable");
    if (fundTable) {
      var funds = sectors.reduce(function (all, s) { return all.concat(s.funds || []); }, []);
      fundTable.innerHTML = '<details><summary>查看当前赛道基金原值（' + funds.length + ' 只）</summary><div class="table-scroll"><table class="matrix"><thead><tr><th>基金</th><th>' + esc(spec.label) + '（' + esc(spec.unit_label) + '）</th><th>扩募提示</th></tr></thead><tbody>' +
        funds.map(function (f) { return '<tr><td><a href="#/detail/' + esc(f.code) + '">' + esc(f.name) + ' · ' + esc(f.code) + '</a></td><td>' + fmt(f.display) + '</td><td>' + (f.expansionInPeriod ? '本期含扩募，非同店' : '资产范围待核') + '</td></tr>'; }).join('') + '</tbody></table></div></details>';
    }
    var table = $("trackQualityTable");
    if (table) {
      table.innerHTML = '<table class="matrix"><thead><tr><th class="l">赛道</th><th>披露</th><th>本期无匹配口径数据</th><th>中位数 / 单基金原值</th><th>最低</th><th>最高</th></tr></thead><tbody>' +
        sectors.map(function (s) {
          return "<tr><td class='l'>" + esc(s.sector) + "</td>" +
            '<td class="num">' + s.n + " / " + s.universe + "</td>" +
            '<td class="num">' + (s.undisclosed ? s.undisclosed : "0") + "</td>" +
            '<td class="num">' + (s.pointOnly ? "不汇总" : fmt(s.medianDisplay)) + "</td>" +
            '<td class="num">' + (s.pointOnly ? "不排名" : fmt(displayMin(s))) + "</td>" +
            '<td class="num">' + (s.pointOnly ? "不排名" : fmt(displayMax(s))) + "</td></tr>";
        }).join("") + "</tbody></table>";
    }
    var und = $("trackUndisclosed");
    if (und) {
      var bits = sectors.map(function (s) {
        return s.sector + " " + s.n + "/" + s.universe + "；本期无匹配口径数据 " + s.undisclosed + " 只" + (s.undisclosedCodes.length ? "（" + s.undisclosedCodes.join("、") + "）" : "");
      });
      var exclusions = (pack.excludedListing || []).filter(function (f) { return f.sector === sectorId; }).map(function (f) {
        return f.code + " " + f.reason + (f.listDate ? "（" + f.listDate + "）" : "");
      });
      und.textContent = "覆盖分母：截至 " + pack.periodEnd + " 已上市且适用指标的基金（经营库 list_date 核对，不以行情库存在与否判断）。" +
        bits.join(" · ") + "。另列，不计缺数、不进入上市基金分布/趋势：" + (exclusions.join("；") || "无") +
        (sectors.some(function (s) { return s.pointOnly; }) ? "。能源子业态待核，仅列基金点位，不计算全能源中位数/趋势/排名；绝对量不表示经营优劣。" : "");
    }
  }
  function displayMin(s) {
    if (!s.funds || !s.funds.length) return null;
    return Math.min.apply(null, s.funds.map(function (f) { return f.display; }));
  }
  function displayMax(s) {
    if (!s.funds || !s.funds.length) return null;
    return Math.max.apply(null, s.funds.map(function (f) { return f.display; }));
  }
  function renderTrend() {
    var spec = metricSpec();
    var original = DATA.trend[spec.id] || { sectors: [] };
    var pack = { sectors: original.sectors.filter(function (s) { return s.sector === sectorId; }) };
    var th = theme();
    var colors = [th.accent, th.cyc, th.gro, th.def, th.warn, "#a78bfa", "#fb7185"];
    var periods = [];
    (pack.sectors || []).forEach(function (s) {
      (s.points || []).forEach(function (p) {
        if (periods.indexOf(p.period) < 0) periods.push(p.period);
      });
    });
    periods.sort();
    var coverageTable = $("trackTrendTable");
    if (coverageTable) coverageTable.innerHTML = '<table class="matrix"><caption>各期覆盖数 n（基金只数）</caption><thead><tr><th>赛道</th>' +
      periods.map(function (p) { return '<th>' + esc(p) + '</th>'; }).join('') + '</tr></thead><tbody>' +
      (pack.sectors || []).map(function (sector) {
        var map = {}; sector.points.forEach(function (p) { map[p.period] = p.n; });
        return '<tr><td>' + esc(sector.sector) + '</td>' + periods.map(function (p) { return '<td>' + (map[p] || '无匹配数据') + '</td>'; }).join('') + '</tr>';
      }).join('') + '</tbody></table>';

    var series = (pack.sectors || []).map(function (s, i) {
      var map = {};
      (s.points || []).forEach(function (p) { map[p.period] = p; });
      return {
        name: s.sector,
        type: "line",
        showSymbol: true,
        symbolSize: 8,
        data: periods.map(function (period) {
          var p = map[period];
          if (!p) return null;
          return { value: p.medianDisplay, n: p.n, period: period };
        }),
        lineStyle: { width: 2 },
        itemStyle: { color: colors[i % colors.length] },
        label: {
          show: !root.matchMedia || !root.matchMedia("(max-width:640px)").matches, fontSize: 9, color: th.tx3,
          formatter: function (p) { return p.data && p.data.n != null ? "n=" + p.data.n : ""; }
        }
      };
    });
    $("trackTrendChart").hidden = series.length === 0;
    var trendNote = $("trackTrendNote");
    if (trendNote) trendNote.textContent = series.length ? sectorId + " · " + spec.label + "（每期样本可能变动）" : sectorId + " · 当前指标无可展示的季度趋势；能源不汇总，单期/无样本不连线。";
    setChart("trackTrendChart", {
      color: colors,
      legend: { top: 0, type: "scroll", textStyle: { color: th.tx2, fontSize: 11 } },
      tooltip: {
        trigger: "axis",
        formatter: function (items) {
          if (!items || !items.length) return "";
          var lines = [items[0].axisValue + "（变动样本中位数，不代表经营改善或恶化）"];
          items.forEach(function (it) {
            if (it.data == null || it.data.value == null) return;
            lines.push(it.marker + it.seriesName + "：" + fmt(it.data.value) + " " + spec.unit_label + " · 覆盖 " + it.data.n + " 只");
          });
          return lines.join("<br>");
        }
      },
      grid: { left: 48, right: 16, top: 36, bottom: 28 },
      xAxis: Object.assign({ type: "category", data: periods }, baseAxis(th)),
      yAxis: Object.assign({ type: "value", scale: true, name: spec.unit_label, nameTextStyle: { color: th.tx3 } }, baseAxis(th)),
      series: series
    });
  }
  function latestPair(sectorPack) {
    var pairs = (sectorPack && sectorPack.fixedPairs) || [];
    return pairs.length ? pairs[pairs.length - 1] : null;
  }
  function renderFixed() {
    var spec = metricSpec();
    var original = DATA.trend[spec.id] || { sectors: [] };
    var pack = { sectors: original.sectors.filter(function (s) { return s.sector === sectorId; }) };
    var th = theme();
    var rows = (pack.sectors || []).map(function (s) {
      return { sector: s.sector, pair: latestPair(s) };
    }).filter(function (r) { return r.pair && r.pair.n; });
    $("trackFixedChart").hidden = rows.length === 0;
    var fixedNote = $("trackFixedNote");
    if (fixedNote) fixedNote.textContent = rows.length ? sectorId + " · 固定同口径样本，仅固定名单、指标、单位、期间与税标记，资产范围待核。" : sectorId + " · 当前指标无固定同口径样本变化；能源不汇总。";
    var names = rows.map(function (r) { return r.sector; });
    setChart("trackFixedChart", {
      color: [th.gro, th.risk, th.tx3],
      legend: { top: 0, textStyle: { color: th.tx2, fontSize: 11 } },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 72, right: 16, top: 36, bottom: 28 },
      xAxis: Object.assign({ type: "value", name: "只", max: "dataMax", nameTextStyle: { color: th.tx3 } }, baseAxis(th)),
      yAxis: Object.assign({ type: "category", data: names.slice().reverse() }, baseAxis(th), { splitLine: { show: false } }),
      series: [
        { name: "报告值上升", type: "bar", stack: "g", barMaxWidth: 16, data: rows.map(function (r) { return r.pair.nUp; }).reverse() },
        { name: "报告值下降", type: "bar", stack: "g", barMaxWidth: 16, data: rows.map(function (r) { return r.pair.nDown; }).reverse() },
        { name: "持平", type: "bar", stack: "g", barMaxWidth: 16, data: rows.map(function (r) { return r.pair.nFlat; }).reverse() }
      ]
    });
    var table = $("trackFixedTable");
    if (table) {
      table.innerHTML = '<table class="matrix"><thead><tr><th class="l">赛道</th><th>比较期</th><th>固定同口径样本</th><th>上升</th><th>下降</th><th>持平</th><th>上升占比</th><th>剔除扩募</th></tr></thead><tbody>' +
        rows.map(function (r) {
          var p = r.pair;
          return "<tr><td class='l'>" + esc(r.sector) + "</td><td>" + esc(p.from) + " → " + esc(p.to) + "</td>" +
            '<td class="num">' + p.n + "</td>" +
            '<td class="num">' + p.nUp + "</td>" +
            '<td class="num">' + p.nDown + "</td>" +
            '<td class="num">' + p.nFlat + "</td>" +
            '<td class="num">' + (p.upShare == null ? "本期无匹配口径数据" : (p.upShare * 100).toFixed(1) + "%") + "</td>" +
            '<td class="num">' + p.excludedExpansion + "</td></tr>";
        }).join("") + "</tbody></table>";
    }
  }
  function withECharts(cb) {
    var load = root.__loadECharts;
    if (root.echarts) { cb(); return; }
    if (load) load().then(function () { cb(); }).catch(function (e) { console.error("[track] echarts", e && e.message); });
    else cb();
  }
  function render() {
    if (!DATA || !$("v-track") || $("v-track").hidden) return;
    renderSwitch();
    withECharts(function () {
      renderQuality();
      renderTrend();
      renderFixed();
    });
  }
  function mount() {
    if (!$("v-track")) return Promise.resolve();
    return loadPack().then(function () {
      return new Promise(function (resolve) {
        root.requestAnimationFrame(function () { root.requestAnimationFrame(function () {
          try { render(); retryCharts(); } catch (e) { console.error("[track-render]", e); }
          resolve();
        }); });
      });
    }, function (e) {
      var meta = $("trackQualityMeta");
      if (meta) meta.textContent = "经营聚合加载失败：" + (e && e.message || e);
    });
  }
  function resize() {
    if (!visible()) return;
    retryCharts();
    Object.keys(charts).forEach(function (id) {
      try { if (charts[id] && !charts[id].isDisposed()) charts[id].resize(); } catch (e) {}
    });
  }
  if (root.addEventListener) root.addEventListener("resize", resize);
  if (root.MutationObserver && typeof document !== "undefined" && document.documentElement) {
    new MutationObserver(function () { render(); }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  }
  var api = { mount: mount, render: render, load: loadPack, format: fmt, sector: function () { return sectorId; }, setSector: selectSector, metric: function () { return metricId; }, setMetric: function (id) { var m = DATA && DATA.metrics.find(function (m) { return m.id === id; }); if (m && metricApplies(m, sectorId)) { metricId = id; render(); } } };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.ReitsTrackAnalysis = api;
  if (root.ResizeObserver && typeof document !== "undefined" && $("v-track")) {
    new root.ResizeObserver(function () { resize(); }).observe($("v-track"));
  }
})(typeof window === "undefined" ? globalThis : window);
