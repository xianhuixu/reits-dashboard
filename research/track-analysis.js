/* Isolated 赛道透视 renderer. Does not mutate REITS_DATA, advice or signals. */
(function (root) {
  "use strict";
  var DATA = null;
  var loading = false;
  var sectorId = "产业园";
  var periodId = null;
  var SECTOR_ORDER = ["产业园", "消费", "商业不动产", "仓储物流", "保租房", "高速公路", "能源", "数据中心", "市政环保", "供热"];
  var SECTOR_SLUGS = {
    "产业园": "chanyeyuan",
    "消费": "xiaofei",
    "商业不动产": "shangye",
    "仓储物流": "cangchu",
    "保租房": "baozufang",
    "高速公路": "gaosu",
    "能源": "nengyuan",
    "数据中心": "shuju",
    "市政环保": "huanbao",
    "供热": "gongre"
  };
  var SLUG_TO_SECTOR = {};
  Object.keys(SECTOR_SLUGS).forEach(function (name) { SLUG_TO_SECTOR[SECTOR_SLUGS[name]] = name; });
  var DENSE_LIMIT = 8;
  var charts = {};
  var pendingCharts = {};
  var retryTimer = null;
  var writingHash = false;
  var renderedMobile = null;

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
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
      gro: cssVal("--gro") || "#34d399",
      risk: cssVal("--risk") || "#e11d48"
    };
  }
  function isMobile() {
    return !!(root.matchMedia && root.matchMedia("(max-width:640px)").matches);
  }
  function visible() {
    return $("v-track") && !$("v-track").hidden && $("pg-research") && !$("pg-research").hidden;
  }
  function clearCharts(prefix) {
    Object.keys(charts).forEach(function (id) {
      if (prefix && id.indexOf(prefix) !== 0) return;
      try { if (charts[id] && !charts[id].isDisposed()) charts[id].dispose(); } catch (e) {}
      delete charts[id];
      delete pendingCharts[id];
    });
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
    try {
      if (!inst || inst.isDisposed() || root.echarts.getInstanceByDom(el) !== inst) {
        inst = root.echarts.getInstanceByDom(el) || root.echarts.init(el, null, { renderer: "canvas" });
        charts[id] = inst;
      }
      inst.setOption(option, true);
      inst.resize();
      inst.off("click");
      inst.on("click", function (p) {
        if (p.data && p.data.fund && p.data.fund.code) root.location.hash = "#/detail/" + p.data.fund.code;
      });
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
  function metricApplies(metric, sector) {
    var pack = DATA.latest[metric.id] || {};
    return (pack.sectors || []).some(function (s) { return s.sector === sector; }) ||
      (pack.excludedListing || []).some(function (f) { return f.sector === sector; });
  }
  function applicableMetrics(sector) {
    return (DATA.metrics || []).filter(function (m) { return metricApplies(m, sector); });
  }
  function sectorRow(metric, sector) {
    var pack = (DATA.latest[metric.id] || {});
    return (pack.sectors || []).find(function (s) { return s.sector === sector; }) || {
      sector: sector, n: 0, universe: 0, undisclosed: 0, undisclosedCodes: [], funds: [],
      median: null, medianDisplay: null, min: null, max: null, pointOnly: false
    };
  }
  function sectorNames() {
    var names = [];
    DATA.metrics.forEach(function (m) {
      var pack = DATA.latest[m.id] || {};
      (pack.sectors || []).concat(pack.excludedListing || []).forEach(function (s) {
        if (names.indexOf(s.sector) < 0) names.push(s.sector);
      });
    });
    return names.sort(function (a, b) {
      var ai = SECTOR_ORDER.indexOf(a), bi = SECTOR_ORDER.indexOf(b);
      return (ai < 0 ? 100 : ai) - (bi < 0 ? 100 : bi) || a.localeCompare(b);
    });
  }
  function toSlug(name) { return SECTOR_SLUGS[name] || "chanyeyuan"; }
  function fromSlug(slug) {
    if (!slug) return null;
    var raw = slug;
    try { raw = decodeURIComponent(slug); } catch (e) {}
    if (Object.prototype.hasOwnProperty.call(SLUG_TO_SECTOR, raw)) return SLUG_TO_SECTOR[raw];
    if (sectorNames().indexOf(raw) >= 0) return raw;
    return null;
  }
  function parseHashSector() {
    var hash = (root.location && root.location.hash) || "";
    var m = hash.match(/^#\/page\/research\/track(?:\/([^/?#]+))?/);
    return fromSlug(m && m[1]);
  }
  function trackHash(name) { return "#/page/research/track/" + toSlug(name); }
  function writeSectorHash(name, replace) {
    var hash = trackHash(name);
    if (!root.location || root.location.hash === hash) return;
    writingHash = true;
    try {
      if (replace && root.history && root.history.replaceState) root.history.replaceState(null, "", hash);
      else if (root.history && root.history.pushState) root.history.pushState(null, "", hash);
      else root.location.hash = hash;
      if (root.location.hash !== hash) root.location.hash = hash;
    } finally {
      writingHash = false;
    }
  }
  function selectSector(id, opts) {
    opts = opts || {};
    if (!DATA) return;
    if (sectorNames().indexOf(id) < 0) return;
    var changed = sectorId !== id;
    sectorId = id;
    if (!opts.fromRoute && (changed || opts.forceHash)) writeSectorHash(id, !!opts.replace);
    if (opts.skipRender && !changed) return;
    render();
  }
  function applyRoute(slug, opts) {
    opts = opts || {};
    if (!DATA) {
      var requestedHash = root.location.hash;
      return loadPack().then(function () { if (root.location.hash === requestedHash) applyRoute(slug, opts); });
    }
    if (!/^#\/page\/research\/track(?:\/|$)/.test(root.location.hash || "")) return;
    var name = fromSlug(slug) || parseHashSector() || sectorNames()[0] || "产业园";
    selectSector(name, { fromRoute: true });
    if ((root.location.hash || "") !== trackHash(sectorId)) writeSectorHash(sectorId, true);
  }
  function displayMin(s) {
    if (!s.funds || !s.funds.length) return null;
    return Math.min.apply(null, s.funds.map(function (f) { return f.display; }));
  }
  function displayMax(s) {
    if (!s.funds || !s.funds.length) return null;
    return Math.max.apply(null, s.funds.map(function (f) { return f.display; }));
  }
  function useScatter(row) {
    return !isMobile() && !row.pointOnly && row.n >= 2 && row.n <= DENSE_LIMIT;
  }
  function renderSwitch() {
    var names = sectorNames();
    var tabs = $("trackSectorSwitch");
    if (tabs) {
      tabs.innerHTML = names.map(function (name) {
        return '<button type="button" role="tab" data-sector="' + esc(name) + '" aria-selected="' + (name === sectorId) + '"' +
          (name === sectorId ? ' class="on"' : "") + ">" + esc(name) + "</button>";
      }).join("");
      tabs.onclick = function (e) {
        var b = e.target && e.target.closest && e.target.closest("button[data-sector]");
        if (b) selectSector(b.dataset.sector);
      };
      tabs.onkeydown = function (e) {
        if (["ArrowLeft", "ArrowRight", "Home", "End"].indexOf(e.key) < 0) return;
        e.preventDefault();
        var at = names.indexOf(sectorId);
        var next = e.key === "Home" ? 0 : e.key === "End" ? names.length - 1 : (at + (e.key === "ArrowRight" ? 1 : -1) + names.length) % names.length;
        selectSector(names[next]);
        var active = tabs.querySelector && tabs.querySelector('button[data-sector="' + names[next] + '"]');
        if (active && active.focus) active.focus();
      };
    }
    var sel = $("trackSectorSelect");
    if (sel) {
      sel.innerHTML = names.map(function (name) {
        return '<option value="' + esc(name) + '"' + (name === sectorId ? " selected" : "") + ">" + esc(name) + "</option>";
      }).join("");
      sel.onchange = function () { selectSector(sel.value); };
    }
  }
  function renderOverview() {
    var metrics = applicableMetrics(sectorId);
    var period = periodId || DATA.latestPeriod;
    var periodEnd = (DATA.latest[metrics[0] ? metrics[0].id : "occupancy_rate"] || {}).periodEnd;
    var meta = $("trackQualityMeta");
    if (meta) {
      meta.textContent = sectorId + " · 报告期 " + period +
        (periodEnd ? "（截至 " + periodEnd + "）" : "") +
        " · 来源：经营数据快照（chinareits 入库） · 切换业态时保留当前报告期";
    }
    var stats = $("trackStats");
    if (stats) {
      stats.innerHTML = metrics.map(function (m) {
        var s = sectorRow(m, sectorId);
        var mid = s.pointOnly ? "不汇总" : !s.universe ? "本期无上市样本" : (s.n === 1 ? "单基金原值 " + fmt(s.medianDisplay) : fmt(s.medianDisplay));
        var range = s.pointOnly || !s.n ? "不排名" : fmt(displayMin(s)) + " — " + fmt(displayMax(s));
        return '<article class="track-stat-metric"><h3>' + esc(m.label) + '（' + esc(m.unit_label) + '）</h3>' +
          '<div class="track-stat-grid">' +
          "<div><small>匹配口径 / 期末上市适用基金</small><strong>" + s.n + " / " + s.universe + "</strong></div>" +
          "<div><small>本期无匹配口径数据</small><strong>" + s.undisclosed + " 只</strong></div>" +
          "<div><small>" + (s.n === 1 ? "单基金原值" : "中位数") + "</small><strong>" + mid + "</strong></div>" +
          "<div><small>最低 — 最高</small><strong>" + range + "</strong></div></div></article>";
      }).join("") || "<p class='track-meta'>当前业态暂无适用核心指标。</p>";
    }
    var und = $("trackUndisclosed");
    if (und) {
      var bits = [];
      metrics.forEach(function (m) {
        var s = sectorRow(m, sectorId);
        if (s.undisclosed) bits.push(m.label + "本期无匹配口径数据 " + s.undisclosed + " 只" + (s.undisclosedCodes && s.undisclosedCodes.length ? "（" + s.undisclosedCodes.join("、") + "）" : ""));
      });
      var seen = {};
      var exclusions = [];
      metrics.forEach(function (m) {
        ((DATA.latest[m.id] || {}).excludedListing || []).forEach(function (f) {
          if (f.sector !== sectorId || seen[f.code]) return;
          seen[f.code] = 1;
          exclusions.push(f.code + " " + f.reason + (f.listDate ? "（" + f.listDate + "）" : ""));
        });
      });
      und.textContent = (bits.length ? bits.join(" · ") + "。" : metrics.every(function (m) { return !sectorRow(m, sectorId).universe; }) ? "本期暂无已上市适用基金。" : "本期已上市适用基金中，已计入匹配口径样本。") +
        "另列，不计缺数、不进入上市基金分布/趋势：" + (exclusions.join("；") || "无") +
        (metrics.some(function (m) { return sectorRow(m, sectorId).pointOnly; }) ? "。能源子业态待核，仅列基金点位，不计算全能源中位数、趋势或排名。" : "");
    }
  }
  function rankList(row, spec) {
    var funds = (row.funds || []).slice().sort(function (a, b) {
      if (row.pointOnly) return a.code.localeCompare(b.code);
      return b.display - a.display || a.code.localeCompare(b.code);
    });
    if (!funds.length) return "<p class='track-meta'>" + (row.universe ? "本期无匹配口径数据，不画空分布。" : "截至报告期末暂无已上市适用基金；另列基金不计缺数。") + "</p>";
    var title = row.pointOnly || funds.length === 1 ? "基金点位" : "可点排名";
    return '<ol class="track-rank-list" aria-label="' + esc(spec.label + title) + '">' + funds.map(function (f, i) {
      return '<li><a href="#/detail/' + esc(f.code) + '"><span class="rank">' + (row.pointOnly || funds.length === 1 ? "·" : (i + 1)) + "</span>" +
        "<span class='name'>" + esc(f.name) + "</span><span class='code'>" + esc(f.code) + "</span>" +
        "<span class='val'>" + fmt(f.display) + " " + esc(spec.unit_label) + "</span><span class='scope'>" + (f.expansionInPeriod ? "本期含扩募，非同店" : "资产范围待核") + "</span></a></li>";
    }).join("") + "</ol>";
  }
  function renderCompare() {
    var host = $("trackMetricPanels");
    if (!host) return;
    clearCharts("trackCompare-");
    var metrics = applicableMetrics(sectorId);
    host.innerHTML = metrics.map(function (m) {
      var s = sectorRow(m, sectorId);
      var scatter = useScatter(s);
      var note = s.pointOnly ? "能源子业态待核：仅列基金点，不计算全能源中位数或排名。" :
        s.n === 0 ? (s.universe ? "本期无匹配口径数据，不硬造分布。" : "本期暂无已上市适用基金，不绘制分布。") :
        s.n === 1 ? "仅 1 只匹配基金，只列单基金原值，不硬造分布。" :
        scatter ? "基金等权散点，点击进入档案。" : "样本较多或窄屏，改用按报告值排序的可点列表；顺序不代表经营优劣，避免标签重叠。";
      return '<section class="track-metric-panel" data-metric="' + esc(m.id) + '"><h3>' + esc(m.label) + "</h3>" +
        '<p class="track-meta">口径 ' + esc(m.caliber) + " · 单位 " + esc(m.unit_label) + " · 税标记 " + esc(m.tax_flag) +
        " · " + esc(m.weighting_note || "基金等权") + " · 覆盖 " + s.n + "/" + s.universe + " · " + note + "</p>" +
        (scatter ? '<div id="trackCompare-' + esc(m.id) + '" class="track-chart"></div>' : "") +
        (scatter ? "" : rankList(s, m)) + "</section>";
    }).join("") || "<p class='track-meta'>当前业态暂无适用核心指标。</p>";
    var th = theme();
    metrics.forEach(function (m) {
      var s = sectorRow(m, sectorId);
      if (!useScatter(s)) return;
      setChart("trackCompare-" + m.id, {
        title: { text: m.id === "occupancy_rate" ? "基金等权、非面积加权" : "", left: 8, top: 0, textStyle: { color: th.tx3, fontSize: 11, fontWeight: 400 } },
        color: [th.accent],
        tooltip: {
          trigger: "item",
          formatter: function (p) {
            var f = p.data && p.data.fund;
            if (!f) return "";
            return esc(f.name) + "<br/>" + esc(f.code) + "<br/>" + esc(m.label) + " " + fmt(f.display) + " " + esc(m.unit_label) + (f.expansionInPeriod ? "<br/>本期含扩募，非同店" : "<br/>资产范围待核");
          }
        },
        grid: { left: 28, right: 16, top: 28, bottom: 36 },
        xAxis: { type: "value", name: m.unit_label, nameTextStyle: { color: th.tx3 }, axisLabel: { color: th.tx3 }, splitLine: { lineStyle: { color: th.grid } } },
        yAxis: { type: "category", data: [s.sector], axisLabel: { show: false }, splitLine: { show: false } },
        series: [{ type: "scatter", symbolSize: 11, data: (s.funds || []).map(function (f) { return { value: [f.display, s.sector], fund: f }; }) }]
      });
    });
  }
  function renderTrend() {
    var host = $("trackTrendPanels");
    if (!host) return;
    clearCharts("trackTrend-");
    clearCharts("trackFixed-");
    var metrics = applicableMetrics(sectorId);
    var hideN = isMobile();
    host.innerHTML = metrics.map(function (m) {
      var trend = ((DATA.trend[m.id] || {}).sectors || []).find(function (s) { return s.sector === sectorId; });
      var row = sectorRow(m, sectorId);
      var pairs = (trend && trend.fixedPairs) || [];
      var latest = pairs.length ? pairs[pairs.length - 1] : null;
      var canTrend = trend && trend.points && trend.points.length && !row.pointOnly;
      var canFixed = latest && latest.n && !row.pointOnly;
      var note = row.pointOnly ? "能源不汇总：不画全能源中位数趋势，也不做固定同口径样本排名。" :
        canTrend ? sectorId + " · " + m.label + "（每期样本可能变动）" : sectorId + " · 当前指标无可展示的季度趋势。";
      return '<section class="track-metric-panel" data-metric="' + esc(m.id) + '"><h3>' + esc(m.label) + "趋势</h3>" +
        '<p class="track-meta">' + esc(note) + "</p>" +
        (canTrend ? '<div id="trackTrend-' + esc(m.id) + '" class="track-chart-wide"></div>' : "") +
        (canTrend ? '<details><summary>各期覆盖数 n</summary><div class="table-scroll"><table class="matrix"><thead><tr>' +
          (trend.points.map(function (p) { return "<th>" + esc(p.period) + "</th>"; }).join("")) +
          "</tr></thead><tbody><tr>" + trend.points.map(function (p) { return "<td>" + p.n + "</td>"; }).join("") +
          "</tr></tbody></table></div></details>" : "") +
        (canFixed ? '<p class="track-meta">固定同口径样本 ' + esc(latest.from) + " → " + esc(latest.to) +
          "：样本 " + latest.n + "，上升 " + latest.nUp + "，下降 " + latest.nDown + "，持平 " + latest.nFlat +
          "，上升占比 " + (latest.upShare == null ? "本期无匹配口径数据" : (latest.upShare * 100).toFixed(1) + "%") +
          "，剔除扩募 " + latest.excludedExpansion + "。资产范围待核，不是同店改善。</p>" +
          '<div id="trackFixed-' + esc(m.id) + '" class="track-chart"></div>' :
          (row.pointOnly ? "" : '<p class="track-meta">当前指标无固定同口径样本变化。</p>')) +
        "</section>";
    }).join("") || "<p class='track-meta'>当前业态暂无趋势。</p>";
    var th = theme();
    metrics.forEach(function (m) {
      var trend = ((DATA.trend[m.id] || {}).sectors || []).find(function (s) { return s.sector === sectorId; });
      var row = sectorRow(m, sectorId);
      if (trend && trend.points && trend.points.length && !row.pointOnly) {
        setChart("trackTrend-" + m.id, {
          color: [th.accent],
          tooltip: {
            trigger: "axis",
            formatter: function (items) {
              if (!items || !items.length || items[0].data == null) return "";
              var d = items[0].data;
              return d.period + "（变动样本中位数，不代表经营改善或恶化）<br/>" + m.label + " " + fmt(d.value) + " " + m.unit_label + " · 覆盖 " + d.n + " 只";
            }
          },
          grid: { left: 48, right: 16, top: 16, bottom: 28 },
          xAxis: { type: "category", data: trend.points.map(function (p) { return p.period; }), axisLabel: { color: th.tx3 } },
          yAxis: { type: "value", scale: true, name: m.unit_label, nameTextStyle: { color: th.tx3 }, axisLabel: { color: th.tx3 }, splitLine: { lineStyle: { color: th.grid } } },
          series: [{
            name: sectorId,
            type: "line",
            showSymbol: true,
            symbolSize: 8,
            data: trend.points.map(function (p) { return { value: p.medianDisplay, n: p.n, period: p.period }; }),
            label: { show: !hideN, fontSize: 9, color: th.tx3, formatter: function (p) { return p.data && p.data.n != null ? "n=" + p.data.n : ""; } }
          }]
        });
      }
      var latest = trend && trend.fixedPairs && trend.fixedPairs.length ? trend.fixedPairs[trend.fixedPairs.length - 1] : null;
      if (latest && latest.n && !row.pointOnly) {
        setChart("trackFixed-" + m.id, {
          color: [th.gro, th.risk, th.tx3],
          tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
          grid: { left: 88, right: 16, top: 8, bottom: 24 },
          xAxis: { type: "value", name: "只", nameTextStyle: { color: th.tx3 }, axisLabel: { color: th.tx3 } },
          yAxis: { type: "category", data: ["报告值上升", "报告值下降", "持平"].reverse(), axisLabel: { color: th.tx3 }, splitLine: { show: false } },
          series: [{
            type: "bar", barMaxWidth: 16,
            data: [
              { value: latest.nFlat, itemStyle: { color: th.tx3 } },
              { value: latest.nDown, itemStyle: { color: th.risk } },
              { value: latest.nUp, itemStyle: { color: th.gro } }
            ]
          }]
        });
      }
    });
  }
  function renderFunds() {
    var host = $("trackFundList");
    if (!host) return;
    var metrics = applicableMetrics(sectorId);
    var byCode = {};
    metrics.forEach(function (m) {
      var s = sectorRow(m, sectorId);
      (s.funds || []).forEach(function (f) {
        if (!byCode[f.code]) byCode[f.code] = { code: f.code, name: f.name, values: [] };
        if (byCode[f.code].name === f.code) byCode[f.code].name = f.name;
        byCode[f.code].values.push(m.label + " " + fmt(f.display) + " " + m.unit_label);
        byCode[f.code].expansion = byCode[f.code].expansion || f.expansionInPeriod;
      });
      (s.undisclosedCodes || []).forEach(function (code) {
        if (!byCode[code]) byCode[code] = { code: code, name: code, values: [] };
        byCode[code].values.push(m.label + " 本期无匹配口径数据");
      });
    });
    var funds = Object.keys(byCode).sort().map(function (c) { return byCode[c]; });
    if (!funds.length) {
      host.innerHTML = "<p class='track-meta'>当前赛道本期没有可展示的已上市匹配口径基金。未上市或期后上市基金见上方另列说明，不进入明细。</p>";
      return;
    }
    host.innerHTML = '<ul class="track-fund-list" aria-label="当前赛道基金明细">' + funds.map(function (f) {
      return '<li><a href="#/detail/' + esc(f.code) + '"><span class="name">' + esc(f.name) + "</span>" +
        '<span class="code">' + esc(f.code) + "</span>" +
        '<span class="vals">' + esc(f.values.join(" · ")) + "</span><span class='scope'>" + (f.expansion ? "本期含扩募，非同店" : "资产范围待核") + "</span></a></li>";
    }).join("") + "</ul>";
  }
  function baseReady() { return DATA && $("v-track") && !$("v-track").hidden; }
  function withECharts(cb) {
    var load = root.__loadECharts;
    if (root.echarts) { cb(); return; }
    if (load) load().then(function () { cb(); }).catch(function (e) { console.error("[track] echarts", e && e.message); });
    else cb();
  }
  function render() {
    if (!baseReady()) return;
    renderedMobile = isMobile();
    renderSwitch();
    renderOverview();
    renderFunds();
    withECharts(function () {
      renderCompare();
      renderTrend();
      retryCharts();
    });
  }
  function mount() {
    if (!$("v-track")) return Promise.resolve();
    return loadPack().then(function () {
      if (!visible() || !/^#\/page\/research\/track(?:\/|$)/.test(root.location.hash || "")) return;
      periodId = periodId || DATA.latestPeriod;
      var fromHash = parseHashSector();
      if (fromHash) sectorId = fromHash;
      else if (sectorNames().indexOf(sectorId) < 0) sectorId = sectorNames()[0] || "产业园";
      if ((root.location.hash || "") !== trackHash(sectorId)) writeSectorHash(sectorId, true);
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
    if (DATA && renderedMobile !== isMobile()) { render(); return; }
    retryCharts();
    Object.keys(charts).forEach(function (id) {
      try { if (charts[id] && !charts[id].isDisposed()) charts[id].resize(); } catch (e) {}
    });
  }
  if (root.addEventListener) root.addEventListener("resize", resize);
  if (root.MutationObserver && typeof document !== "undefined" && document.documentElement) {
    new MutationObserver(function () { if (visible()) render(); }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  }
  var api = {
    mount: mount,
    render: render,
    load: loadPack,
    format: fmt,
    slugs: SECTOR_SLUGS,
    period: function () { return periodId; },
    sector: function () { return sectorId; },
    setSector: function (id) { selectSector(id); },
    applyRoute: applyRoute,
    parseHashSector: parseHashSector,
    currentRoute: function () { return trackHash(sectorId); },
    writingHash: function () { return writingHash; }
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.ReitsTrackAnalysis = api;
  if (root.ResizeObserver && typeof document !== "undefined" && $("v-track")) {
    new root.ResizeObserver(function () { resize(); }).observe($("v-track"));
  }
})(typeof window === "undefined" ? globalThis : window);
