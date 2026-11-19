/* Isolated 赛道透视 renderer. Does not mutate REITS_DATA, advice or signals. */
(function (root) {
  "use strict";
  var DATA = null;
  var loading = false;
  var metricId = "occupancy_rate";
  var charts = {};
  var mounted = false;

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function fmt(v, digits) {
    if (v == null || typeof v !== "number" || !isFinite(v)) return "尚未披露";
    return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: digits == null ? 2 : digits, minimumFractionDigits: 0 }).format(v);
  }
  function pct(v) {
    if (v == null || !isFinite(v)) return "尚未披露";
    return (v * 100).toFixed(1) + "%";
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
  function setChart(id, option) {
    var el = $(id);
    if (!el || !root.echarts) return;
    if (el.offsetWidth === 0 || el.offsetHeight === 0) return;
    if (!charts[id] || charts[id].isDisposed()) charts[id] = root.echarts.init(el, null, { renderer: "canvas" });
    charts[id].setOption(option, true);
    charts[id].resize();
    return charts[id];
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
  function renderSwitch() {
    var host = $("trackMetricSwitch");
    if (!host || !DATA) return;
    host.innerHTML = DATA.metrics.map(function (m) {
      var n = ((DATA.latest[m.id] || {}).sectors || []).reduce(function (a, s) { return a + s.n; }, 0);
      var disabled = n === 0;
      return '<button type="button" role="tab" data-metric="' + esc(m.id) + '"' +
        (m.id === metricId ? ' class="on" aria-selected="true"' : ' aria-selected="false"') +
        (disabled ? " disabled" : "") + ">" + esc(m.label) + (n ? " · " + n : "") + "</button>";
    }).join("");
    host.onclick = function (e) {
      var b = e.target && e.target.closest && e.target.closest("button[data-metric]");
      if (!b || b.disabled) return;
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
    var sectors = pack.sectors || [];
    var th = theme();
    var meta = $("trackQualityMeta");
    if (meta) {
      meta.textContent = "报告期 " + (pack.period || DATA.latestPeriod) +
        " · 口径 " + spec.caliber + " · 单位 " + spec.unit_label +
        " · 税标记 " + spec.tax_flag +
        " · " + (spec.weighting_note || "") +
        " · 来源：经营数据快照（chinareits 入库）";
    }
    var names = sectors.map(function (s) { return s.sector; }).reverse();
    var medians = sectors.map(function (s) { return s.medianDisplay; }).reverse();
    var ns = sectors.map(function (s) { return s.n; }).reverse();
    setChart("trackMedianChart", {
      color: [th.accent],
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 72, right: 56, top: 16, bottom: 28 },
      xAxis: Object.assign({ type: "value", name: spec.unit_label, nameTextStyle: { color: th.tx3 } }, baseAxis(th)),
      yAxis: Object.assign({ type: "category", data: names }, baseAxis(th), { splitLine: { show: false } }),
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
      title: spec.id === "occupancy_rate" ? { text: "基金等权、非面积加权；点位为基金层面，不是项目替代", left: 72, top: 0, textStyle: { color: th.tx3, fontSize: 11, fontWeight: 400 } } : undefined,
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
    var table = $("trackQualityTable");
    if (table) {
      table.innerHTML = '<table class="matrix"><thead><tr><th class="l">赛道</th><th>披露</th><th>尚未披露</th><th>中位数</th><th>最低</th><th>最高</th></tr></thead><tbody>' +
        sectors.map(function (s) {
          return "<tr><td class='l'>" + esc(s.sector) + "</td>" +
            '<td class="num">' + s.n + " / " + s.universe + "</td>" +
            '<td class="num">' + (s.undisclosed ? s.undisclosed : "0") + "</td>" +
            '<td class="num">' + fmt(s.medianDisplay) + "</td>" +
            '<td class="num">' + fmt(displayMin(s)) + "</td>" +
            '<td class="num">' + fmt(displayMax(s)) + "</td></tr>";
        }).join("") + "</tbody></table>";
    }
    var und = $("trackUndisclosed");
    if (und) {
      var bits = sectors.filter(function (s) { return s.undisclosed; }).map(function (s) {
        return s.sector + " " + s.undisclosed + " 只尚未披露";
      });
      und.textContent = bits.length ? bits.join(" · ") + "。未披露不计入中位数，也不作 0。" : "本期适用赛道中，已披露样本均已计入中位数。";
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
    var pack = DATA.trend[spec.id] || { sectors: [] };
    var th = theme();
    var colors = [th.accent, th.cyc, th.gro, th.def, th.warn, "#a78bfa", "#fb7185"];
    var periods = [];
    (pack.sectors || []).forEach(function (s) {
      (s.points || []).forEach(function (p) {
        if (periods.indexOf(p.period) < 0) periods.push(p.period);
      });
    });
    periods.sort();
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
          show: true, fontSize: 9, color: th.tx3,
          formatter: function (p) { return p.data && p.data.n != null ? "n=" + p.data.n : ""; }
        }
      };
    });
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
    var pack = DATA.trend[spec.id] || { sectors: [] };
    var th = theme();
    var rows = (pack.sectors || []).map(function (s) {
      return { sector: s.sector, pair: latestPair(s) };
    }).filter(function (r) { return r.pair && r.pair.n; });
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
      table.innerHTML = '<table class="matrix"><thead><tr><th class="l">赛道</th><th>比较期</th><th>固定样本</th><th>上升</th><th>下降</th><th>持平</th><th>上升占比</th><th>剔除扩募</th></tr></thead><tbody>' +
        rows.map(function (r) {
          var p = r.pair;
          return "<tr><td class='l'>" + esc(r.sector) + "</td><td>" + esc(p.from) + " → " + esc(p.to) + "</td>" +
            '<td class="num">' + p.n + "</td>" +
            '<td class="num">' + p.nUp + "</td>" +
            '<td class="num">' + p.nDown + "</td>" +
            '<td class="num">' + p.nFlat + "</td>" +
            '<td class="num">' + (p.upShare == null ? "尚未披露" : (p.upShare * 100).toFixed(1) + "%") + "</td>" +
            '<td class="num">' + p.excludedExpansion + "</td></tr>";
        }).join("") + "</tbody></table>";
    }
  }
  function renderPropertyValuation(panel) {
    var meta = $("trackValPropertyMeta");
    var ps = panel && panel.propertySpread;
    if (!ps) {
      if (meta) meta.textContent = "产权利差面板尚未加载。";
      return;
    }
    if (meta) {
      meta.textContent = "asOf " + (ps.asOf || "—") + " · 状态 " + (ps.status || "—") +
        (ps.lagReason ? " · " + ps.lagReason : "") +
        " · 覆盖 " + ((ps.coverage && ps.coverage.included) || "—") + "/" + ((ps.coverage && ps.coverage.universe) || "—") +
        " · 10Y " + (ps.latest && ps.latest.y10 != null ? ps.latest.y10 + "%" : "尚未披露") +
        " · 市值加权 TTM " + (ps.latest && ps.latest.ttmYieldMcap != null ? ps.latest.ttmYieldMcap + "%" : "尚未披露");
    }
    var th = theme();
    var sectors = ps.sectors || [];
    var names = sectors.map(function (s) { return s.sector; }).reverse();
    setChart("trackValPropertyChart", {
      color: [th.accent, th.cyc],
      legend: { top: 0, textStyle: { color: th.tx2, fontSize: 11 } },
      tooltip: { trigger: "axis" },
      grid: { left: 80, right: 48, top: 36, bottom: 28 },
      xAxis: [
        Object.assign({ type: "value", name: "TTM%", nameTextStyle: { color: th.tx3 } }, baseAxis(th)),
        Object.assign({ type: "value", name: "利差BP", nameTextStyle: { color: th.tx3 } }, baseAxis(th), { splitLine: { show: false } })
      ],
      yAxis: Object.assign({ type: "category", data: names }, baseAxis(th), { splitLine: { show: false } }),
      series: [
        { name: "市值加权 TTM 分派率", type: "bar", data: sectors.map(function (s) { return s.yieldMcap; }).reverse(), barMaxWidth: 14 },
        { name: "利差 BP", type: "scatter", xAxisIndex: 1, data: sectors.map(function (s) { return s.spreadBp; }).reverse(), symbolSize: 10 }
      ]
    });
    var per = (ps.distYoY && ps.distYoY.perReit) || [];
    var occ = ((DATA.latest.occupancy_rate || {}).sectors || []).reduce(function (a, s) {
      (s.funds || []).forEach(function (f) { a[f.code] = f; });
      return a;
    }, {});
    var pts = [];
    per.forEach(function (r) {
      var f = occ[r.code];
      if (!f || r.ttmNow == null) return;
      pts.push({ value: [r.ttmNow * 100, f.display], fund: f, ttm: r.ttmNow * 100, yoy: r.yoyPct, sector: r.sector });
    });
    setChart("trackValPropertyScatter", {
      color: [th.accent],
      tooltip: {
        trigger: "item",
        formatter: function (p) {
          var d = p.data;
          if (!d || !d.fund) return "";
          return esc(d.fund.name) + "<br/>出租率 " + fmt(d.fund.display) + "%（基金等权点位，非面积加权）<br/>TTM 分派率 " + fmt(d.ttm) + "%" +
            (d.yoy == null ? "" : "<br/>分派同比 " + fmt(d.yoy) + "%") +
            "<br/>仅分派同比样本，不是全市场截面";
        }
      },
      grid: { left: 48, right: 16, top: 28, bottom: 40 },
      xAxis: Object.assign({ type: "value", name: "TTM 分派率 %", scale: true, nameTextStyle: { color: th.tx3 } }, baseAxis(th)),
      yAxis: Object.assign({ type: "value", name: "出租率 %", scale: true, nameTextStyle: { color: th.tx3 } }, baseAxis(th)),
      title: { text: "出租率 vs TTM 分派（交叉样本 " + pts.length + " 只，不是全样本）", left: 0, top: 0, textStyle: { color: th.tx2, fontSize: 11, fontWeight: 400 } },
      series: [{ type: "scatter", symbolSize: 10, data: pts }]
    });
  }
  function renderOperatingValuation(panel) {
    var meta = $("trackValOperatingMeta");
    var od = panel && panel.operatingDisclosedIrr;
    if (!od) {
      if (meta) meta.textContent = "经营权披露 IRR 面板尚未加载。";
      return;
    }
    if (meta) {
      meta.textContent = (od.label || "") + " · asOf " + (od.asOf || "—") +
        " · 披露 " + ((od.coverage && od.coverage.disclosed) || 0) + "/" + ((od.coverage && od.coverage.universe) || 0) +
        " · 业态不汇总 · " + (od.formula || "");
    }
    var th = theme();
    var items = od.items || [];
    var pending = od.pending || [];
    var sectors = [];
    items.forEach(function (it) { if (sectors.indexOf(it.sector) < 0) sectors.push(it.sector); });
    pending.forEach(function (it) { if (sectors.indexOf(it.sector) < 0) sectors.push(it.sector); });
    var data = items.map(function (it) {
      return { value: [it.spreadBp, it.sector], item: it };
    });
    setChart("trackValOperatingChart", {
      color: [th.cyc],
      tooltip: {
        trigger: "item",
        formatter: function (p) {
          var it = p.data && p.data.item;
          if (!it) return "";
          return esc(it.name) + "<br/>披露 IRR " + (it.irrDisclosedPct == null ? "尚未披露" : it.irrDisclosedPct + "%") +
            "<br/>期限匹配国债 " + (it.matchedYieldPct == null ? "尚未披露" : fmt(it.matchedYieldPct) + "%") +
            "<br/>利差 " + (it.spreadBp == null ? "尚未披露" : fmt(it.spreadBp) + " BP");
        }
      },
      grid: { left: 80, right: 24, top: 16, bottom: 36 },
      xAxis: Object.assign({ type: "value", name: "利差 BP", nameTextStyle: { color: th.tx3 } }, baseAxis(th)),
      yAxis: Object.assign({ type: "category", data: sectors }, baseAxis(th), { splitLine: { show: false } }),
      series: [{ type: "scatter", symbolSize: 11, data: data }]
    });
    var table = $("trackValOperatingTable");
    if (table) {
      table.innerHTML = '<table class="matrix"><thead><tr><th class="l">基金</th><th class="l">赛道</th><th>披露 IRR</th><th>匹配国债</th><th>利差 BP</th></tr></thead><tbody>' +
        items.map(function (it) {
          return "<tr><td class='l'><a class='track-fund-link' href='#/detail/" + esc(it.code) + "'>" + esc(it.name) + "</a></td>" +
            "<td class='l'>" + esc(it.sector) + "</td>" +
            '<td class="num">' + (it.irrDisclosedPct == null ? "尚未披露" : it.irrDisclosedPct + "%") + "</td>" +
            '<td class="num">' + (it.matchedYieldPct == null ? "尚未披露" : fmt(it.matchedYieldPct) + "%") + "</td>" +
            '<td class="num">' + (it.spreadBp == null ? "尚未披露" : fmt(it.spreadBp)) + "</td></tr>";
        }).join("") +
        pending.map(function (it) {
          return "<tr><td class='l'><a class='track-fund-link' href='#/detail/" + esc(it.code) + "'>" + esc(it.name) + "</a></td>" +
            "<td class='l'>" + esc(it.sector) + "</td>" +
            '<td class="num" colspan="3">尚未披露' + (it.reason ? " · " + esc(it.reason) : "") + "</td></tr>";
        }).join("") + "</tbody></table>";
    }
  }
  function renderValuation() {
    var panel = root.REITS_DATA_PANEL;
    function go(p) { renderPropertyValuation(p); renderOperatingValuation(p); }
    if (panel) { go(panel); return; }
    if (root.__PANEL_READY) {
      root.__PANEL_READY.then(function () { go(root.REITS_DATA_PANEL); }).catch(function () { go(null); });
    } else go(null);
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
      renderValuation();
    });
  }
  function mount() {
    var page = $("v-track");
    if (!page) return Promise.resolve();
    mounted = true;
    return loadPack().then(function () { render(); }).catch(function (e) {
      var meta = $("trackQualityMeta");
      if (meta) meta.textContent = "经营聚合暂不可用：" + (e && e.message || e);
    });
  }
  function resize() {
    Object.keys(charts).forEach(function (id) {
      try { if (charts[id] && !charts[id].isDisposed()) charts[id].resize(); } catch (e) {}
    });
  }
  if (root.addEventListener) root.addEventListener("resize", resize);
  if (root.MutationObserver && typeof document !== "undefined" && document.documentElement) {
    new MutationObserver(function () { render(); }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  }
  var api = { mount: mount, render: render, load: loadPack, format: fmt, metric: function () { return metricId; }, setMetric: function (id) { metricId = id; render(); } };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.ReitsTrackAnalysis = api;
})(typeof window === "undefined" ? globalThis : window);
