// Layout/source contracts, not browser pixel acceptance.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const html=fs.readFileSync('index.html','utf8'),js=fs.readFileSync('research/track-analysis.js','utf8'),css=fs.readFileSync('research/track-analysis.css','utf8');
const section=html.slice(html.indexOf('id="v-track"'),html.indexOf('</section>',html.indexOf('id="v-track"')));
test('track uses top tabs and a mobile select, not a new left navigation or total-chart metric switch',()=>{
 assert.match(section,/id="trackSectorSwitch" role="tablist"/);assert.match(section,/<select id="trackSectorSelect"/);
 assert.doesNotMatch(section,/<aside|trackMetricSwitch|trackMedianChart|trackDispersionChart/);
 assert.match(css,/@media\(max-width:640px\)\{[\s\S]*\.track-sector-tabs\{display:none\}/);
 assert.match(css,/\.track-sector-select-wrap\{display:block\}/);
});
test('one sector uses full-width overview, independent core metrics, history and clickable fund details in that order',()=>{
 const ordered=['trackOverviewCard','trackCompareCard','trackTrendCard','trackFundsCard'].map(id=>section.indexOf('id="'+id+'"'));
 assert.ok(ordered.every((pos,i)=>pos>=0&&(i===0||pos>ordered[i-1])));
 assert.match(section,/id="trackMetricPanels"/);assert.match(section,/id="trackFundList"/);
 assert.match(js,/metrics\.map\(function \(m\)/);assert.match(js,/trackCompare-/);assert.match(js,/trackTrend-/);
 assert.match(js,/track-rank-list/);assert.match(js,/DENSE_LIMIT = 8/);assert.match(js,/!isMobile\(\)/);
 assert.match(js,/track-fund-list/);assert.match(js,/href="#\/detail\//);
 assert.doesNotMatch(section,/trackValProperty|trackValOperating/);
});
test('topbar receives mobile AI settings slot; track reading area has no launcher dock placeholder',()=>{
 const top=html.slice(html.indexOf('id="topbar"'),html.indexOf('</nav>',html.indexOf('id="topbar"')));
 assert.match(top,/id="rdAiTopSlot"/);assert.doesNotMatch(section,/trackAiTools|rdAiArchiveDock/);
 assert.match(html,/app\.js\?v=20261119-layout/);
});
