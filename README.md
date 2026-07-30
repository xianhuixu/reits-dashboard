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
