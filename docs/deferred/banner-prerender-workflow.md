# Banner HTML pre-render (deferred — needs workflow scope)

## Why
Mobile LCP target ≤ 2.5s. The conclusion banner (`#ovHero` / `#ovHeadline`) is the LCP candidate.
A committed static snapshot (design-r1) already paints the last-known conclusion without waiting for `advice.json`.
Build-time inject on every data refresh would keep that snapshot fresh without a manual edit.

## What Jason needs to wire (token lacks `workflow` scope)

1. Add a step after `advice.json` / `data.json` refresh in `.github/workflows/daily-update.yml` (and any mirror deploy workflow):

```bash
python3 scripts/prerender_banner.py
```

2. Commit the updated `index.html` fragment (or the generated snippet if you prefer include-at-build).

## Script
`scripts/prerender_banner.py` reads live JSON through the same `workspace.js` / `allocation-tools.js`
pure functions (`bannerModel` / `schoolStance`) and replaces `#ovHeadline` / `#ovBasis`.

## Until then
design-r1 ships a manually refreshed snapshot matching 2026-10-05 live stance:
`利率下行 → 产权标配·偏多观察` / `依据：时钟·利率下行`.
`workspace.js` still overwrites on load when data is ready.


## design-r3 (PR #24) — still blocked on workflow scope

Round 3 shipped everything else for mobile LCP (critical CSS inline for banner+4 cards,
deferred research-layout/map CSS, idle-loaded tender/map/page-agent, heatmap still behind
IntersectionObserver). Live mobile LCP was ~3.0s after r2; the remaining ~0.5s to hit
**≤ 2.5s** needs this workflow step so every daily update refreshes the static `#ovHeadline`
snapshot. Please merge the step above into `.github/workflows/daily-update.yml` (and any
mirror deploy workflow). Token used by the bot still has **no workflow scope**.
