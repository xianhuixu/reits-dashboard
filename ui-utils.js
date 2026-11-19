(function (root) {
  "use strict";

  function formatPercentile(value) {
    return Number.isFinite(value) ? value.toFixed(1) + "%" : "—";
  }

  function escHtml(value) {
    return String(value == null ? "" : value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function averagePercentile(values) {
    if (!Array.isArray(values)) return null;

    var validValues = values.filter(function (value) {
      return Number.isFinite(value);
    });

    if (!validValues.length) return null;

    return validValues.reduce(function (sum, value) {
      return sum + value;
    }, 0) / validValues.length;
  }

  var _assetPromises = {};
  function loadStylesheet(href) {
    if (typeof document === "undefined") return Promise.resolve();
    var key = "css:" + href;
    if (_assetPromises[key]) return _assetPromises[key];
    var existing = document.querySelector('link[rel="stylesheet"][href="' + href + '"]');
    if (existing) return (_assetPromises[key] = Promise.resolve());
    _assetPromises[key] = new Promise(function (resolve, reject) {
      var link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = href;
      link.onload = function () { resolve(); };
      link.onerror = function () { delete _assetPromises[key]; reject(new Error("stylesheet " + href)); };
      document.head.appendChild(link);
    });
    return _assetPromises[key];
  }
  function loadScript(src) {
    if (typeof document === "undefined") return Promise.resolve();
    var key = "js:" + src;
    if (_assetPromises[key]) return _assetPromises[key];
    var existing = document.querySelector('script[src="' + src + '"]');
    if (existing) return (_assetPromises[key] = Promise.resolve());
    _assetPromises[key] = new Promise(function (resolve, reject) {
      var el = document.createElement("script");
      el.src = src;
      el.async = false;
      el.onload = function () { resolve(); };
      el.onerror = function () { delete _assetPromises[key]; reject(new Error("script " + src)); };
      document.body.appendChild(el);
    });
    return _assetPromises[key];
  }

  var api = {
    averagePercentile: averagePercentile,
    escHtml: escHtml,
    formatPercentile: formatPercentile,
    loadStylesheet: loadStylesheet,
    loadScript: loadScript
  };

  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }

  if (root) {
    root.averagePercentile = averagePercentile;
    root.escHtml = escHtml;
    root.formatPercentile = formatPercentile;
    root.loadStylesheet = loadStylesheet;
    root.loadScript = loadScript;
  }
})(typeof window === "undefined" ? null : window);
