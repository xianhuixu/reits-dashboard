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

  var api = {
    averagePercentile: averagePercentile,
    escHtml: escHtml,
    formatPercentile: formatPercentile
  };

  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }

  if (root) {
    root.averagePercentile = averagePercentile;
    root.escHtml = escHtml;
    root.formatPercentile = formatPercentile;
  }
})(typeof window === "undefined" ? null : window);
