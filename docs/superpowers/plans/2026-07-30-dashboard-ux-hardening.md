# REITs Dashboard UX Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the deployed REITs dashboard's mobile usability, data-format reliability, information hierarchy, motion efficiency, and chart accessibility without changing its financial analysis framework.

**Architecture:** Retain the existing static GitHub Pages architecture and Python data pipeline. Extract deterministic UI formatting into a browser-and-Node compatible utility module, add Node built-in tests, and make scoped HTML/CSS/JavaScript improvements inside the existing single-page shell.

**Tech Stack:** HTML, CSS, vanilla JavaScript, Node.js built-in test runner, Python syntax checks, GitHub Pages.

---

### Task 1: Add regression tests for percentile formatting

**Files:**
- Create: `tests/ui-utils.test.js`
- Create: `ui-utils.js`
- Modify: `package.json`
- Modify: `index.html`

- [ ] **Step 1: Write the failing test**

```javascript
const test = require("node:test");
const assert = require("node:assert/strict");
const { formatPercentile, averagePercentile } = require("../ui-utils.js");

test("formats percentile values already expressed on a 0-100 scale", () => {
  assert.equal(formatPercentile(44.88), "44.9%");
  assert.equal(formatPercentile(15.93), "15.9%");
});

test("averages percentile values without multiplying them by 100", () => {
  assert.equal(formatPercentile(averagePercentile([10, 20, 30])), "20.0%");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/ui-utils.test.js`

Expected: FAIL because `ui-utils.js` does not exist.

- [ ] **Step 3: Implement the formatting module and use it in the dashboard**

```javascript
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.REITS_UI = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function formatPercentile(value) {
    return value == null || !Number.isFinite(value) ? "—" : value.toFixed(1) + "%";
  }
  function averagePercentile(values) {
    const valid = values.filter(Number.isFinite);
    return valid.length ? valid.reduce((sum, value) => sum + value, 0) / valid.length : null;
  }
  return { formatPercentile, averagePercentile };
});
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tests/ui-utils.test.js`

Expected: PASS with 2 tests.

### Task 2: Add responsive layout contracts

**Files:**
- Create: `tests/layout-contract.test.js`
- Modify: `index.html`

- [ ] **Step 1: Write failing source-level layout tests**

```javascript
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const html = fs.readFileSync(path.join(__dirname, "..", "index.html"), "utf8");

test("mobile pages do not clip body overflow", () => {
  assert.doesNotMatch(html, /html, body\s*\{\s*overflow-x:\s*clip/);
});

test("wide matrices use local horizontal scrolling", () => {
  assert.match(html, /class="table-scroll" id="matrix"/);
  assert.match(html, /\.table-scroll\s*\{[^}]*overflow-x:\s*auto/s);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/layout-contract.test.js`

Expected: FAIL on the existing body clipping rule and missing table-scroll class.

- [ ] **Step 3: Add bounded overflow containers and mobile rules**

```css
.page, .view, .card { min-width: 0; }
.table-scroll { width: 100%; overflow-x: auto; overscroll-behavior-inline: contain; }
@media (max-width: 860px) {
  html, body { max-width: 100%; }
  .table-scroll > table { min-width: 680px; }
}
```

- [ ] **Step 4: Run the layout tests**

Run: `node --test tests/layout-contract.test.js`

Expected: PASS.

### Task 3: Clarify hierarchy and motion

**Files:**
- Modify: `index.html`
- Modify: `tests/layout-contract.test.js`

- [ ] **Step 1: Add failing assertions for conclusion-first advice and bounded animation delay**

```javascript
assert.match(html, /id="adviceList"[\s\S]*id="adviceMapping"/);
assert.match(html, /Math\.min\(i \* 50, 250\)/);
```

- [ ] **Step 2: Run tests and confirm the intended failures**

Run: `node --test tests/layout-contract.test.js`

Expected: FAIL because the long-term mapping precedes the allocation conclusion and stagger delays are unbounded.

- [ ] **Step 3: Reorder the advice summary and constrain animation**

Move `#adviceList` immediately after the cycle-position paragraph, add the `advice-summary` grid class, reduce page/card transition durations, and cap card stagger delay:

```css
.advice-summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.page:not([hidden]) { animation: fade .22s var(--ease); }
.page:not([hidden]) .card, .page:not([hidden]) .kpi { animation-duration: .32s; }
@media (max-width: 860px) { .advice-summary { grid-template-columns: 1fr; } }
```

```javascript
function stagger(scope) {
  if (!scope) return;
  scope.querySelectorAll(".card").forEach(function (card, index) {
    card.style.setProperty("--d", Math.min(index * 50, 250) + "ms");
  });
}
```

- [ ] **Step 4: Preserve page scroll positions and smooth only explicit anchor navigation**

Store scroll positions per primary page in `showPage`; restore them without long animated travel. Use smooth scrolling for advice anchors and selected-security detail navigation:

```javascript
var currentPage = "pano";
var pageScroll = { pano: 0, research: 0, advice: 0 };

function restorePageScroll(page) {
  requestAnimationFrame(function () {
    window.scrollTo({ top: pageScroll[page] || 0, behavior: "auto" });
  });
}
```

- [ ] **Step 5: Run tests**

Run: `npm test`

Expected: PASS.

### Task 4: Improve chart semantics and navigation cues

**Files:**
- Modify: `index.html`
- Modify: `tests/layout-contract.test.js`

- [ ] **Step 1: Add failing assertions**

Require chart SVG output to include `<title>`, require the secondary navigation to use scroll snapping, and require visible focus styling for buttons:

```javascript
assert.match(html, /<title>/);
assert.match(html, /scroll-snap-type:\s*x proximity/);
assert.match(html, /:focus-visible/);
```

- [ ] **Step 2: Run tests and verify failure**

Run: `npm test`

Expected: FAIL because generated charts currently omit accessible titles.

- [ ] **Step 3: Add chart titles, focus states, and mobile overflow cues**

Add titles to line, radar, correlation, cycle, and allocation SVGs; add `:focus-visible` styles; add scroll snapping and an edge fade to the mobile secondary navigation:

```css
button:focus-visible, input:focus-visible, select:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
#subbar .sub { scroll-snap-type: x proximity; scrollbar-width: none; }
#subbar .sub button { scroll-snap-align: start; }
```

```javascript
function svgTitle(title) {
  return "<title>" + title + "</title>";
}
```

- [ ] **Step 4: Run tests**

Run: `npm test`

Expected: PASS.

### Task 5: Verify, commit, deploy, and validate production

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run static verification**

Run: `npm test && node --check server.js && python3 -m py_compile fetch_data.py fetch_news.py`

Expected: all commands exit 0.

- [ ] **Step 2: Run local rendered QA**

Start the repository server, verify desktop 1280x720 and mobile 390x844, exercise all three primary modules and at least one research submodule, confirm no body overflow or relevant console errors, and inspect screenshots against the current production baseline.

- [ ] **Step 3: Update documentation**

Document `npm test`, responsive behavior, and retained static deployment architecture in `README.md`.

- [ ] **Step 4: Commit and push**

Run: `git add index.html ui-utils.js tests package.json README.md docs/superpowers/plans/2026-07-30-dashboard-ux-hardening.md && git commit -m "Improve dashboard usability and data clarity" && git push origin main`

Expected: push succeeds to `main`.

- [ ] **Step 5: Verify GitHub Pages**

Wait for the `pages-build-deployment` workflow to complete, then verify the production URL, updated commit, desktop/mobile rendering, target interactions, and absence of relevant console errors.
