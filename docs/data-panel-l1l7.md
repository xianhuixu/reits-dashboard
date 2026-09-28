# 二级投研数据面板 L1–L7

对齐 PPT《REITs二级投研数据面板》（刘伟 / Shu WU，修改 2026-09-24）与 `docs/school-framework.md` **分权属估值**纪律。

## 本仓库落地

| 文件 | 作用 |
|---|---|
| `data_panel_l1l7.json` | 面板序列与截面（schema 见 fusion `ppt_seed_l1l7.json` → `schemaProposal`） |
| `data_panel.js` | `window.REITS_DATA_PANEL` 镜像，便于直链 / 兼容 |
| `build_data_panel.py` | 校验 schema、同步 JS；**live 拉取尚未接入** |

前端：`index.html` 并行 `fetch("data_panel_l1l7.json")` → `REITS_DATA_PANEL`；研究分析 → **策略分类** 页展示 **L2 双利差**（产权 TTM−10Y、经营权 **IRR−10Y**）。市场复盘上的 avgYield−10Y 标尺已降级为「粗览 · 非产权锚」。

## 口径（强制）

- **产权利差** = 市值加权 TTM 现金分派率 − 10Y  
- **经营权利差** = 市值加权中债 **IRR** − 10Y（**不是** TTM；PPT slide11 笔误已在实现中纠正）  
- 每个图保留 `asOfTrade` / `source` / seed 标记  

## Seed vs Live

当前 JSON 为 **PPT 快照锚点插值 SEED**（`seedMeta.liveFetch=false`，`asOfTrade≈2026-09-24`）。行情主链路 `data.json` 已更新至更新交易日时，**勿把 seed 当作当日定价**。后续用 iFinD / Wind / 中债登填入同 schema 后去掉 seed 标记即可；在 fetch 就绪前 **不要** 把本文件挂进会失败的每日流水线。

## 层级路线（展示优先）

1. **B1 / 本 PR**：L2 双时序  
2. L1 三资产归一 · L3 板块利差 · L4 市值收益 · L5 近月指数 · L6 流动性 · L7 周轮动  

详细 gap 与字段表见工作区 fusion 手稿（未强制合入）：`integration-brief.md` / `gap-analysis.md`。短草稿亦可参考 `research/l1l7-panel-draft.md`。

## Cloudflare 拷贝

`deploy_cf.sh` 需包含 `data_panel_l1l7.json`（及可选 `data_panel.js`）。GitHub Actions `daily-update.yml` 的 CF 步骤若无 workflow 写权限，请人工补一行 copy，否则 CF 镜像缺面板 JSON、GitHub Pages 仍可读（根目录静态文件）。
> **Blocker for CI CF mirror**: this PR could not update `.github/workflows/daily-update.yml` (GitHub token lacks `workflow` scope). After merge, manually add `data_panel_l1l7.json` to the CF `cp` line in that workflow (same as `deploy_cf.sh`). GitHub Pages serves repo root files and does not need the workflow edit.

