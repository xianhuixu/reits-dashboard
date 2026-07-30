(function (root) {
  "use strict";

  function formatPercentile(value) {
    return Number.isFinite(value) ? value.toFixed(1) + "%" : "—";
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
    formatPercentile: formatPercentile
  };

  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }

  if (root) {
    root.averagePercentile = averagePercentile;
    root.formatPercentile = formatPercentile;
  }
})(typeof window === "undefined" ? null : window);
