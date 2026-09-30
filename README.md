# 公募REITs 全量投研面板

## 配置研究与布局更新（2026-09-14）

配置页按“配置总览 → 分权估值 → 现金流质量 → 板块筛选 → 风险与压力测试 → 研究依据”组织。正文直接包含在 HTML 中；`allocation-tools.js` 只读行情，并提供板块筛选与独立假设情景计算。`research-layout.css` 统一导航、卡片和响应式表格布局，沿用三种主题。

新版以[完整研究备忘录](research/allocation-research-2026-09-14.md)为依据，区分披露事实、研究判断与假设。原 `advice.json` / `advice.js` 和 `docs/school-framework.md` 保留为历史资料，当前配置页不再消费其评级、仓位倾向及未经逐项核验的卖方指标。行情更新不会自动刷新研究观点。

压力测试采用独立示例参数，不读写原始财务模型；产权采用零增长永续近似，经营权采用有限期等额年末现金流。正式投资定价仍须逐券建模。`npm test` 包含独立现金流现值核验、无效参数和缺失行情样本检查。

## 数据状态标注与语义色（2026-09-30）

- **数据状态角标**：`data-status.js`（`window.ReitsDataStatus`）把各 JSON 已有的 `status` / `asOf` / `seedMeta` / `stale` 字段统一映射为 live / 示例数据 / 待接入 / 缓存 · as-of X。非 live 模块在右上角显示角标并灰化（虚线边框、图表去饱和）。当前覆盖：L2 分权利差（seed）、Beta 面板、REITs 投资时钟与升息快于租金闸门的产权利差分位腿、招投标（stale / degraded）、中证 REITs 指数（stale）、赛道运营数据与分派监测（fundamentals 为空）、压力测试（纯假设，HTML 以 `data-ds-status="seed"` 声明）。新模块只需调用 `ReitsDataStatus.apply(el, state)`。
- **语义色**：红 / 绿（`--up` / `--down`）只表示价格涨跌（红涨绿跌）。配置倾向用 `--alloc-ow`（超配，深蓝）/ `--alloc-n`（标配，灰）/ `--alloc-uw`（低配，琥珀）；研判正负沿用同一蓝 / 琥珀轴（`--tilt-pos` / `--tilt-neg`）；预警 `--warn`（橙）、风险 / 红线 `--risk`（紫）；冲突 / 复核 / 参考标记用 `--flag-conflict` / `--flag-watch` / `--flag-ref`。三套主题各自定义。
- **资产重估判断**：完整版（理论回溯、排他性预测、四项条件↔因子映射）只在「周期分析」页；「策略信号」页保留摘要与跳转链接。
- Cloudflare 镜像：`deploy_cf.sh` 已加入 `data-status.js`；`.github/workflows/*` 的 `cp` 清单也需加入 `data-status.js`（本次 token 无 workflow 权限，未改；缺失时页面降级为不显示角标，其余功能不受影响）。

以下为既有数据管线与运行说明。

覆盖全部上市公募 REITs 的二级市场投研 Dashboard：全景热力图、策略分类研究（防御/周期/成长）、大类资产相关性、板块轮动、个券全表、配置建议。

- 数据源：同花顺 iFinD（行情与指数）
- 每个交易日收盘后自动更新（本地定时任务抓取并推送 data.js）
- 框架：中金 REITs 研究 + 《公募REITs投资策略分享-2026》顺周期动态配置框架

> 行情数据为第三方数据源口径，仅供研究参考，不构成投资建议。

## 本地运行与测试

```bash
npm run dev
npm test
```

页面保持原生 HTML、CSS 与 JavaScript 的静态架构，可直接由 GitHub Pages 部署。桌面端采用多栏信息布局；移动端将宽表限制在各自模块内横向滚动，并保留主模块的阅读位置，避免整页横向溢出。

自动化测试覆盖历史分位格式、移动端布局契约、配置建议层级、动画时长上限、键盘焦点样式、SVG 图表标题及主模块滚动位置恢复。


## 配置建议（分权破局重估学派）

「配置建议与风险」页由 `advice.json`（及镜像 `advice.js` → `window.REITS_ADVICE`）驱动，融合中金五维破局闸门与中信建投结构主线，并与 `data.json` 实时聚合产权/经营权量价。刷新表面：更新 `advice.json` 后同步生成 `advice.js`（`window.REITS_ADVICE = …`），提交即可随 GitHub Pages 生效。Cloudflare 镜像部署见 `deploy_cf.sh` / `daily-update.yml`，必须包含 `advice.json`（漏拷时 `advice.json` 会 200 回退成首页 HTML，配置页表现为空白）。页面始终展示研究日与行情日双时间戳。

> 学派框架与 advice 节点仅供投研信息展示，**不构成投资建议**。



## 二级投研数据面板（L1–L7）

研究分析 → 策略分类页展示 **L2 产权/经营权双利差时序**（TTM−10Y / IRR−10Y），数据文件 `data_panel_l1l7.json`。口径与学派框架对齐：经营权强制 IRR，统一 `avgYield` 不作产权锚。详见 [docs/data-panel-l1l7.md](docs/data-panel-l1l7.md)。

## 部署

`main` 分支根目录为 GitHub Pages 发布源。推送后由 `pages-build-deployment` 工作流自动发布至：

https://xianhuixu.github.io/reits-dashboard/

## 数据更新与自动更新

### 数据文件清单

| 文件 | 内容 | 更新方式 | 频率 |
|---|---|---|---|
| `data.js` / `data.json` | 行情、指标、六因子信号、相关性、事件流、回测 | `fetch_data_em.py`（腾讯直连，主）/ `fetch_data_server_v2.py`（hist_cache 兜底）/ `fetch_data.py`（iFinD 插件，备用） | 每交易日收盘后 |
| `news.js` / `news.json` | 信息流（东财新闻/搜狗微信/招标网） | `fetch_news.py` | 每交易日 |
| `corp_actions.js` / `corp_actions.json` | 公告（分红/扩募/解禁等） | `fetch_news.py` | 每交易日 |
| `projects.js` / `projects.json` | 发改委推荐/上交所受理/深交所受理项目 | `fetch_projects.py` | 每交易日 |
| `advice.js` / `advice.json` | 分权破局重估学派配置建议（闸门/仓位/分权/板块） | 人工维护（研究周更） | 周/事件驱动 |
| `data_panel_l1l7.json` / `data_panel.js` | L1–L7 二级投研数据面板（L2 分权利差序列等） | 当前为 PPT seed；live 见 `build_data_panel.py` | seed → 日后日/周频 |
| `universe.json` | 上市个券清单 | 手动（新 REIT 上市时） | 不定期 |
| `fundamentals.json` | 分派达成率等基本面 | 手动 | 季度 |
| `cycle_judgment.json` | 周期判定 + 10Y 国债 （`rateClock` 增长×利率时钟、`rateRentGate` 闸门由 `update_cycle_data.py` 自动计算） | 手动 + 自动 | 月度 / 每日 |
| `macro_series.json` | 真实 10Y 国债日序列 + 制造业 PMI 月序列缓存（东财数据中心） | `update_cycle_data.py` 自动 | 每日 |
| `overseas_clock_du2021.json` | 美国 REITs 投资时钟先验（杜丽虹 2021，年化总回报；替代已删除的 `overseas_static.json` 占位矩阵） | 手动（静态文献数据） | 不定期 |
| `holidays.txt` | 节假日表（跳过非交易日） | 手动 | 每年初 |
| `hist_cache/`（gitignore） | 全历史日线增量缓存 | 抓取脚本自动维护，自带单位自愈 | 随行情更新 |

### 自动更新（服务器 cron）

`scripts/auto_update.sh` 已实现全流程自动化。脚本自适配 `SCRIPT_DIR`/`WORK_DIR`，不再硬编码 `/root/.openclaw/workspace`，可在任意部署路径运行。

每个交易日 15:30 后（收盘数据完整）由 cron 调度：

```cron
30 15 * * 1-5 <仓库路径>/scripts/auto_update.sh >> <仓库路径>/scripts/auto_update.log 2>&1
```

脚本流程（6 步骤）：交易日/节假日判断 → `git pull` → 行情数据（`fetch_data_em.py` 直连腾讯，失败自动回退 `fetch_data_server_v2.py` 缓存版）→ **数据质量闸门 `check_data.py`**（个券数/收盘价/成交额校验，不通过立即 `exit 1` 放弃推送保护线上）→ 信息流 → 项目申报 → `git commit & push` → GitHub Pages 自动部署。

`full_update.sh` 是同等的全量版本（行情 → 周期判断 → 信息流 → 质量闸门 → 推送），适合手动一次性补跑。

### 首次克隆后初始化

`data.json` / `data_research.json` / `data_research.js` 等数据文件已 gitignore，首次克隆后仓库不含实际数据，请本地先运行一次生成：

```bash
python3 fetch_data_em.py   # 直连腾讯生成 data.js/data.json（约 1-2 分钟）
python3 fetch_news.py      # 抓取新闻与公告
python3 verify_data.py     # 校验产物文件
```

随后 `npm run dev` 即可在 http://127.0.0.1:7100 访问。

### 已弃用脚本

- `fetch_data_fast.py` / `fetch_data_patched.py` — iFinD 旧版本迭代残留，已停止使用并加入 `.gitignore`
- `fetch_data_server.py` — 服务器版未完工(mock 模式),请改用 `fetch_data_server_v2.py` (基于 hist_cache 兜底)

`fetch_data_em.py` 的 `fetch_history` 自带**成交量单位自愈**（腾讯"手"与 iFinD"份"混用会自动归一）；若服务器 hist_cache 从未修复过，可先跑一次：

```bash
python3 scripts/repair_volume_units.py
```

本机（Mac）更新：`python3 fetch_data_em.py`（需 pandas，直连腾讯 + 增量缓存 + 自愈），提交推送即上线。

### ECharts 定制构建（减小首屏体积）

`lib/echarts.min.js` 为定制构建（595KB vs 官方全量 1MB），仅包含站点用到的图表/组件。修改入口后重建：

```bash
cd /tmp && mkdir -p echarts-build && cd echarts-build && npm init -y
npm i echarts@5.6.0 esbuild
cp <仓库>/scripts/echarts-custom-entry.js entry.js
npx esbuild entry.js --bundle --minify --format=iife --outfile=lib/echarts.min.js
```

### 机构投研工作台改版（2026-09-15）

本轮依据 UI UX Pro Max 的 Data-Dense Dashboard 设计方向重构全站。主导航迁移至侧栏，分析任务使用顶部页签；市场总览增加真实等权价格序列、板块比较与成交活跃资产，配置研究按专题展示。手机端使用抽屉导航，并支持键盘关闭、焦点约束与宽表格局部滚动。

- `workspace.css`：统一工作台、主题及响应式布局。
- `workspace.js`：导航、历史走势、只读 CSV 导出与行情组件。历史走势使用 `data_research.json.series.market`，所选区间起点归一为 100，与中证 REITs 全收益指数分别标注。
- `design-system/reits-workspace/MASTER.md`：设计检索、适配判断与组件约束。
- `docs/review-20260915/`：检查记录和桌面、移动端截图。

行情数据文件、采集脚本与财务模型未修改；已核验的配置研究正文及来源保留。验证：`npm test`。


### 招投标独立定时更新

`招投标独立更新` 工作流每天北京时间 **09:20、18:20** 运行，覆盖周末，GitHub 调度可能延迟；可在 Actions 手动运行。与行情任务解耦，不必等待行情、微信或项目列表采集完成。

- 主源：用户指定的 https://ctbpsp.com/#/bulletinList?keyWords=reits ，正常浏览器读取公开可见列表，遇到访问验证、登录限制或模糊遮罩时记录失败。
- 官方备用：中国招标投标公共服务平台 HTTPS 公告搜索列表；按实际总记录数翻页，不能使用页面旧版硬编码的 15 条/页假设，也不能遇到旧公告即停止。
- 补充：深圳环水集团官网采购首页的最新公告；仅作局部补充，不代表全国或完整历史覆盖。
- 输出：`tenders.json`；展示最近 90 天有效公告。以完整标题与公告日期去重，不截取标题前缀；抓取失败保留历史并记录来源状态，不刷新失败来源的最近成功时间。
- 网站的“新闻与公告 → 招投标”显示主源状态、各来源核查时间、最新公告日期。源站无新公告不等于抓取失败；核查超过 30 小时会提示检查任务。
- 全部来源失败时先尝试发布失败状态，再令工作流失败；GITHUB_TOKEN 推送后显式请求 GitHub Pages 构建，并同步 Cloudflare 镜像。

本地验证：`pip install -r requirements-tenders.txt`；`python -m playwright install chromium`；`python -m unittest discover -s tests -p 'test_tenders.py'`。采集试运行可用 `python fetch_tenders.py --output /tmp/tenders-check.json`，不覆盖现有文件。


### 本机定时补充（已配置）

由于GitHub托管运行器访问全国性公告源返回405，当前Mac已配置用户级LaunchAgent `com.lion.reits-tenders`，每日北京时间09:50、18:50及用户登录后补跑。Mac需开机联网；休眠期间的日历任务通常在唤醒后补跑，关机不能按原时点执行。

运行目录：`~/Library/Application Support/REITsTenderUpdater/`；日志：该目录下`updater.log`；配置：`~/Library/LaunchAgents/com.lion.reits-tenders.plist`。运行器代码见`scripts/update_tenders_local.py`。本机只通过GitHub内容API更新`tenders.json`，不更新行情、财务模型或本地仓库。更新期间有并发提交时，重读SHA并合并公告后重试。

本机用户令牌推送自动触发GitHub Pages及招投标镜像发布；`tenders.json`变更不触发行情采集。运行器采用安装时的固定代码副本，后续升级需同步专用目录中的脚本。
