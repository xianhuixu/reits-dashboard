# Unified Sticky Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Combine the brand area, primary navigation, and page-specific secondary tabs into one compact sticky navigation shell with clear flat hierarchy on desktop and mobile.

**Architecture:** Retain the existing static HTML/CSS/JavaScript architecture. Restructure the existing `#topbar` and `#subbar` markup inside `index.html`, add source-level regression contracts, and update the existing navigation state functions without changing any data pipeline or financial values.

**Tech Stack:** HTML, CSS, vanilla JavaScript, Node.js built-in test runner, GitHub Pages.

---

### Task 1: Lock the unified navigation structure with regression tests

**Files:**
- Modify: `tests/layout-contract.test.js`
- Test: `tests/layout-contract.test.js`

- [ ] **Step 1: Add failing structural and label assertions**

Append tests that isolate the navigation source and require a single sticky shell, nested secondary navigation, data metadata outside the shell, and unnumbered secondary labels:

```javascript
test("primary and secondary navigation share one sticky shell", () => {
  assert.match(html, /<nav id="topbar">[\s\S]*<div id="subbar"[\s\S]*<\/nav>\s*<div class="data-meta" id="meta">/);
  assert.match(html, /#topbar\s*\{[^}]*position:\s*sticky/s);
  assert.doesNotMatch(html, /#subbar\s*\{[^}]*position:\s*sticky/s);
  assert.doesNotMatch(html, /#subbar\s*\{[^}]*top:\s*\d+px/s);
});

test("secondary navigation labels do not use numeric prefixes", () => {
  const adviceSub = html.slice(html.indexOf('id="adviceSub"'), html.indexOf('</div>', html.indexOf('id="adviceSub"')));
  assert.doesNotMatch(adviceSub, /[①②③④]/);
  assert.match(adviceSub, />大类策略配置建议</);
  assert.match(adviceSub, />风险提示</);
});

test("navigation state and anchor offsets are accessible and header-aware", () => {
  assert.match(html, /aria-current/);
  assert.match(html, /scroll-margin-top:\s*var\(--sticky-offset\)/);
  assert.doesNotMatch(html, /window\.scrollY - 132/);
});
```

- [ ] **Step 2: Run the tests and verify the intended failures**

Run:

```bash
node --test tests/layout-contract.test.js
```

Expected: the three new tests fail because `#subbar` is outside `#topbar`, uses its own sticky offset, advice labels include circled numbers, and anchor scrolling uses a hard-coded `132px` offset.

- [ ] **Step 3: Commit the failing regression contract**

```bash
git add tests/layout-contract.test.js
git commit -m "test: define unified navigation contracts"
```

### Task 2: Restructure and style the unified sticky shell

**Files:**
- Modify: `index.html:265-387`
- Test: `tests/layout-contract.test.js`

- [ ] **Step 1: Nest the secondary navigation and move metadata out of the sticky shell**

Restructure the existing markup to this ownership model while retaining the existing IDs used by JavaScript:

```html
<nav id="topbar">
  <div class="topbar-main">
    <div class="tb-brand"><img src="icons/lion-v2-crop.png" alt="Lion"><span>REITs 投研工作台</span></div>
    <div id="tbNav">
      <button data-pg="pano" class="on" aria-current="page">市场全景</button>
      <button data-pg="research">多维研究分析</button>
      <button data-pg="advice">配置建议与风险</button>
      <span class="ink"></span>
    </div>
    <div class="tb-search">
      <input id="gSearch" placeholder="搜索个券名称 / 代码" autocomplete="off">
      <div class="tb-drop" id="gSearchDrop" hidden></div>
    </div>
    <span class="theme-sw" id="themeSw">
      <button data-t="light" title="白天">☀️ 白天</button>
      <button data-t="eye" title="护眼">🌿 护眼</button>
      <button data-t="dark" title="夜晚">🌙 夜晚</button>
    </span>
  </div>
  <div id="subbar" data-cur="pano">
    <div class="sub" id="panoSub">
      <button data-pg="pano" data-scroll="v-heatmap" class="on" aria-current="page">行情总览与热力图</button>
      <button data-pg="pano" data-scroll="newsCard">重点事件信息流</button>
    </div>
    <div class="sub" id="researchSub">
      <button data-v="strategy" class="on" aria-current="page">策略分类研究</button>
      <button data-v="cycle">周期耦合分析</button>
      <button data-v="track">赛道透视</button>
      <button data-v="corr">大类资产相关性</button>
      <button data-v="detail">个券透视</button>
      <button data-v="sector">板块轮动</button>
      <button data-v="signal">策略信号</button>
    </div>
    <div class="sub" id="adviceSub">
      <button data-pg="advice" data-scroll="advCycle">大类策略配置建议</button>
      <button data-pg="advice" data-scroll="advTactic">短期交易战术</button>
      <button data-pg="advice" data-scroll="advPerf">中长期配置建议</button>
      <button data-pg="advice" data-scroll="advRisk">风险提示</button>
    </div>
  </div>
</nav>
<div class="data-meta" id="meta">数据加载中…</div>
```

Change the advice buttons to these exact labels:

```html
<button data-pg="advice" data-scroll="advCycle">大类策略配置建议</button>
<button data-pg="advice" data-scroll="advTactic">短期交易战术</button>
<button data-pg="advice" data-scroll="advPerf">中长期配置建议</button>
<button data-pg="advice" data-scroll="advRisk">风险提示</button>
```

- [ ] **Step 2: Replace the current topbar/subbar CSS with desktop flat-navigation styles**

Implement the shared shell with explicit row ownership:

```css
:root { --sticky-offset: 118px; }
#topbar { position: sticky; top: 8px; z-index: 40; display: block; overflow: visible;
  background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
  box-shadow: var(--shadow); margin-bottom: 8px; }
.topbar-main { min-height: 64px; display: flex; align-items: center; gap: 18px; padding: 0 16px; }
#topbar .tb-brand { min-width: 226px; padding-right: 18px; border-right: 1px solid var(--line); }
#topbar .tb-brand img { width: 46px; height: 46px; border-radius: 8px; }
#tbNav { position: relative; align-self: stretch; display: flex; gap: 2px; }
#tbNav button { position: relative; border-radius: 0; padding: 0 15px; }
#tbNav .ink { bottom: 0; height: 3px; }
#subbar { min-height: 42px; display: flex; align-items: center; overflow: hidden;
  padding: 0 16px 0 260px; border-top: 1px solid var(--line); background: var(--panel2); }
#subbar .sub { width: 100%; margin-left: 0; gap: 4px; }
#subbar .sub button { background: transparent; border-radius: 6px; box-shadow: none;
  padding: 6px 11px; color: var(--tx2); transition: color .18s, background .18s; }
#subbar .sub button.on { background: rgba(59,130,246,.10); color: var(--accent); font-weight: 650; }
.data-meta { min-height: 24px; padding: 2px 2px 0; color: var(--tx3); font-size: 11.5px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
[data-theme="dark"] #subbar .sub button.on { background: rgba(91,147,255,.15); }
```

Use existing theme variables so light, eye, and dark themes retain their current palettes.

- [ ] **Step 3: Add the compact mobile three-row layout**

Replace the current mobile top offsets and large logo styles:

```css
@media (max-width: 860px) {
  :root { --sticky-offset: 150px; }
  #topbar { top: 4px; }
  .topbar-main { min-height: 92px; display: grid; grid-template-columns: 1fr auto;
    grid-template-areas: "brand search" "primary theme"; gap: 4px 8px; padding: 6px 10px; }
  #topbar .tb-brand { grid-area: brand; min-width: 0; border-right: 0; padding-right: 0; }
  #topbar .tb-brand img { width: 36px; height: 36px; }
  #topbar .tb-brand span { font-size: 12.5px; }
  .tb-search { grid-area: search; }
  .tb-search input { width: 132px; }
  #tbNav { grid-area: primary; min-width: 0; overflow-x: auto; }
  #tbNav button { min-height: 36px; padding: 0 9px; font-size: 12.5px; }
  #topbar .theme-sw { grid-area: theme; }
  #subbar { min-height: 40px; padding: 0 10px; }
  #subbar .sub { overflow-x: auto; }
  .data-meta { display: none; }
}
```

- [ ] **Step 4: Run the navigation and full test suites**

Run:

```bash
node --test tests/layout-contract.test.js
npm test
```

Expected: all navigation contracts and the complete suite pass.

- [ ] **Step 5: Commit the structural and visual implementation**

```bash
git add index.html tests/layout-contract.test.js
git commit -m "feat: unify sticky dashboard navigation"
```

### Task 3: Synchronize navigation state and anchor behavior

**Files:**
- Modify: `index.html:1437-1502`
- Test: `tests/layout-contract.test.js`

- [ ] **Step 1: Extend the failing accessibility/state test**

Require scoped activation and removal of the global secondary-state reset:

```javascript
assert.match(html, /function setActiveNav\(/);
assert.match(html, /setAttribute\("aria-current", "page"\)/);
assert.match(html, /b\.parentElement\.querySelectorAll\("button"\)/);
assert.doesNotMatch(html, /document\.querySelectorAll\("#subbar \.sub button\.on"\)/);
```

- [ ] **Step 2: Run the targeted test and verify failure**

Run:

```bash
node --test tests/layout-contract.test.js
```

Expected: FAIL because navigation state currently toggles classes directly and clears active secondary tabs across all primary pages.

- [ ] **Step 3: Implement one state helper for primary and secondary navigation**

Add this helper before `switchView` and use it in `switchView`, `showPage`, and the secondary click handler:

```javascript
function setActiveNav(buttons, activeButton) {
  buttons.forEach(function (button) {
    var isActive = button === activeButton;
    button.classList.toggle("on", isActive);
    if (isActive) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
}
```

Use the helper in each navigation path:

```javascript
function switchView(v) {
  document.querySelectorAll(".view").forEach(function (x) { x.hidden = x.id !== "v-" + v; });
  var active = document.querySelector('#researchSub button[data-v="' + v + '"]');
  setActiveNav(document.querySelectorAll("#researchSub button"), active);
  stagger($("v-" + v));
}

function showPage(pg, keepScroll) {
  var btn = document.querySelector('#tbNav > button[data-pg="' + pg + '"]');
  if (!btn) return;
  var switching = pg !== currentPage;
  if (switching) {
    pageScroll[currentPage] = window.scrollY;
    currentPage = pg;
  }
  $("subbar").dataset.cur = pg;
  setActiveNav(document.querySelectorAll("#tbNav > button"), btn);
  var ink = document.querySelector("#tbNav .ink");
  ink.style.left = btn.offsetLeft + "px";
  ink.style.width = btn.offsetWidth + "px";
  $("topbar").classList.toggle("adv", pg === "advice");
  document.querySelectorAll(".page").forEach(function (p) { p.hidden = p.id !== "pg-" + pg; });
  if (switching) restorePageScroll(pg);
}

$("subbar").addEventListener("click", function (e) {
  var b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.scroll) {
    showPage(b.dataset.pg, true);
    setActiveNav(b.parentElement.querySelectorAll("button"), b);
    var t = document.getElementById(b.dataset.scroll);
    if (t) t.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  if (b.dataset.v) {
    showPage("research");
    switchView(b.dataset.v);
  }
});

$("tbNav").addEventListener("click", function (e) {
  var b = e.target.closest("button");
  if (!b || !b.dataset.pg) return;
  showPage(b.dataset.pg);
});
```

- [ ] **Step 4: Replace the hard-coded anchor offset with CSS scroll margins**

Add:

```css
#v-heatmap, #newsCard, #advCycle, #advTactic, #advPerf, #advRisk, #detailPanel {
  scroll-margin-top: var(--sticky-offset);
}
```

Replace the anchor scroll calculation with:

```javascript
if (t) t.scrollIntoView({ behavior: "smooth", block: "start" });
```

- [ ] **Step 5: Run the full automated checks**

Run:

```bash
npm test
node --check server.js
python3 -m py_compile fetch_data.py fetch_news.py
git diff --check
```

Expected: 0 failed tests and all syntax/diff checks exit 0.

- [ ] **Step 6: Commit the state and anchor improvements**

```bash
git add index.html tests/layout-contract.test.js
git commit -m "fix: synchronize navigation state and anchors"
```

### Task 4: Rendered desktop and mobile verification

**Files:**
- Verify: `index.html`
- Verify: `tests/layout-contract.test.js`

- [ ] **Step 1: Start the existing static development server**

Run:

```bash
npm run dev -- --port 7102 --host 127.0.0.1
```

Expected: the server reports `http://127.0.0.1:7102/`.

- [ ] **Step 2: Verify desktop 1280×720 in Browser**

Exercise this flow:

```text
app load -> scroll at least 800px -> confirm unified sticky shell remains visible
-> switch all three primary modules -> switch one research secondary tab
-> confirm primary underline, secondary flat active fill, search, and theme controls remain usable
```

Record: page title, visible page/view IDs, `body.scrollWidth`, topbar bounding rectangle before/after scroll, secondary active label, console warnings/errors, and a screenshot.

Expected: `body.scrollWidth === 1280`, topbar remains at its sticky top position, and no relevant console warnings/errors are present.

- [ ] **Step 3: Verify mobile 390×844 in Browser**

Exercise this flow:

```text
app load -> inspect the three compact navigation rows -> scroll at least 800px
-> horizontally scroll the research secondary tabs -> switch cycle analysis
-> switch advice and use the unnumbered Risk tab
```

Record: `body.scrollWidth`, topbar height, primary/secondary scroll widths, visible active states, console warnings/errors, and screenshots for the home and research states.

Expected: `body.scrollWidth === 390`, the sticky shell remains operable, the secondary row scrolls locally, and no text or controls overlap.

- [ ] **Step 4: Verify retained workflows**

Test theme switching, exact-code global asset search, individual detail rendering, and remembered primary-page scroll positions.

Expected: each workflow updates the intended visible state without console errors.

### Task 5: Reconcile remote state, deploy, and verify production

**Files:**
- Deploy: `index.html`
- Deploy: `tests/layout-contract.test.js`
- Deploy: `docs/superpowers/specs/2026-07-30-unified-sticky-navigation-design.md`
- Deploy: `docs/superpowers/plans/2026-07-30-unified-sticky-navigation.md`

- [ ] **Step 1: Read the current remote main SHA and compare concurrent changes**

Run:

```bash
gh api repos/xianhuixu/reits-dashboard/git/ref/heads/main --jq .object.sha
```

If standard `git push origin main` remains unavailable, use the GitHub Git Data API with `force=false`, taking the current remote commit as the parent and its tree as the base. Abort before updating the ref if any concurrent remote change overlaps `index.html`, the navigation tests, or the design/plan documents.

- [ ] **Step 2: Update remote main without modifying financial data**

Deploy only the planned navigation, test, design, and plan files. Do not upload local copies of `data.js`, `data.json`, `news.js`, `news.json`, `corp_actions.js`, or `corp_actions.json`.

Expected: the remote update is a fast-forward from the latest remote commit and `main` resolves to the new commit SHA.

- [ ] **Step 3: Wait for GitHub Pages**

Run:

```bash
gh run list --repo xianhuixu/reits-dashboard --workflow pages-build-deployment --limit 5
```

Expected: the workflow for the new head SHA completes with `success`.

- [ ] **Step 4: Verify the production URL at desktop and mobile widths**

Open:

```text
https://xianhuixu.github.io/reits-dashboard/
```

Repeat the desktop/mobile sticky-navigation, module switching, no-overflow, theme, search, and console checks against production. Confirm the loaded advice secondary labels contain no numeric prefixes.

- [ ] **Step 5: Report final evidence**

Report the final remote commit SHA, Pages workflow ID/status, production URL, automated test count, desktop/mobile viewport checks, screenshots, and any remaining local Git transport limitation.
