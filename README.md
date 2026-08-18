# 公募REITs 全量投研面板

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
| `universe.json` | 上市个券清单 | 手动（新 REIT 上市时） | 不定期 |
| `fundamentals.json` | 分派达成率等基本面 | 手动 | 季度 |
| `cycle_judgment.json` | 周期判定 + 10Y 国债 | 手动 | 月度 |
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
