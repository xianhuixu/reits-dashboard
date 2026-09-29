# 增长 × 利率 REITs 投资时钟 · 股/债 Beta · 升息快于租金闸门

> 落地日期：2026-09-29（UTC+8）· 分支 `feat/rate-clock-beta`
> 文献：杜丽虹《用数据解读你不知道的REITs（六）REITs的投资时钟》，证券市场周刊，2021-12-22，<https://baijiahao.baidu.com/s?id=1719823577102902700>
> **范围提醒**：原文只研究**美国**权益型 REITs（1994 年以来月度收益；Beta 截至 2021-06、过去 5 年），没有涉及中国公募 REITs。本仓库只把它当作**方法论 + 海外先验**。

## 1. 海外先验（P0-1）· `overseas_clock_du2021.json`

| 象限 | 美国定义 | 年化总回报 |
|---|---|---|
| Q1 繁荣 | 实际 GDP ≥2% + 升息 | 4.9% |
| Q2 复苏/泡沫 | ≥2% + 降息 | **23.9%（最佳）** |
| Q3 衰退 | <2% + 降息 | **3.5%（最差）** |
| Q4 滞胀/复苏 | <2% + 升息 | 15.1%（滞胀 −10.7% / 复苏 26.1%） |

- 口径是**年化总回报**，不是超额收益；旧 `overseas_static.json`（placeholder=true 的占位矩阵）已删除，前端与抓取脚本不再引用。
- 分业态只收录原文**文字**给出的区间（>15% / 10–15% / <10% / 负 / 样本不足）以及原文明确说出的最佳期 / 雷区；原文没说的写 `null`（例如多元化）。
- **未获取**：表1（各业态股/债 Beta 表）与图1–3（气泡图）为图片，box 访问图床超时；方法细节（加权方式、子指数、GDP 插值）原文未说明。
- 进入前端：`fetch_data_em.py` / `fetch_data.py` 读入 → `data_research.json.overseasClock` → 周期分析页「海外先验」卡。

## 2. 增长 × 利率时钟（P0-2）· `cycle_judgment.json.rateClock`

由 `update_cycle_data.py`（CI 每日第一步）调用 `rate_clock.py` 自动计算：

| 轴 | 中国化口径 | 数据源（真实） |
|---|---|---|
| 利率 | 10Y 国债收益率 **60 个交易日**变化；**±10bp 死区** | 东财数据中心 `RPTA_WEB_TREASURYYIELD` · `EMM00166466`（中债 10Y） |
| 增长 | 制造业 PMI **近 3 月均值 vs 50**（替代美国「实际 GDP 2%」）；趋势 = 近 3 月均值 − 前 3 月均值（±0.1 死区），用于 Q4 滞胀/复苏拆分 | 东财数据中心 `RPT_ECONOMY_PMI`（国家统计局） |

- 死区内：`rateDir="flat"`，象限按变化**符号**给出「倾向象限」，`confidence="低"`。没有用长期滞回，因为在慢速单边下行时，滞回会把一年前的升息方向一直带到今天，误导性更大。
- `history`：逐月末重算（只用当月末已公布的数据），保留最近 24–36 个月，供 SVG 轨迹与 `rotation`（顺时针 = 繁荣→滞胀→衰退→复苏；逆时针 = 利率先行）使用。
- `conflictFlags`：当前象限 × `advice.clockSectorPrior` × `advice.sectorViews`：
  - `conflict`：学派超配（含「标配偏超配」），但该板块美国类比在当前象限属于雷区；
  - `watch`：学派低配或观望，但当前象限是其美国类比的最佳期；
  - `background`：Q3 或 Q4·滞胀 这类高风险象限 vs 学派月度立场（按 resolutionRules，只作背景）。
- 真实序列缓存在 `macro_series.json`。取数失败时沿用缓存并标注 `seriesOrigin=cache`；缓存也没有时 `status="unavailable"`、象限为空，**不插值、不沿用手工值**。
- **注意**：`data_panel_l1l7.json.bond10ySeries` 是 PPT 锚点 **SEED 插值**，不是真实数据，本模块不使用。

**2026-09-29 首次判定**：10Y 1.679%（2026-09-28），60 日 −5.9bp（落在死区内，倾向降息）；PMI 3 月均 49.77（6–8 月 50.3 / 49.2 / 49.8），趋势下行 → **Q3 衰退（低置信度）**。月末轨迹为 Q2（2026-05/06）→ Q3，属于逆时针旋转（利率先行）。美国先验中本象限整体年化 3.5%，住宅按揭、独栋出租领先；办公、社区商业、购物中心、酒店、商业按揭为雷区。自动冲突：**消费「标配偏超配」vs 购物中心 / 社区商业 Q3 雷区**。

## 3. 股/债 Beta（P1-3）· `data_research.json.correlation.betas`

`beta_calc.py`（由 `fetch_data_em.py` 与 `fetch_data.py` 调用，数据源沿用各自行情源：腾讯 K 线 / iFinD）：

- 周频（W-FRI）收益；对 **000300.SH 沪深300** 求股 Beta，对 **000012.SH 上证国债** 求债 Beta；另把周收益对周 Δ10Y（bp，取自 `macro_series.json`）回归，结果 ×10，得到 `sens10y`，即「10Y 每上行 10bp 对应的周收益 %」。
- 主窗口 **104 周**（腾讯接口单次 500 根日线，CI 无持久 hist_cache，实际约 100 周，以 `weeksAvailable` 为准；少于 40 周置空），另算板块 **52 周滚动** Beta，用来观察 Beta 漂移。
- 分类：中国 REITs 与股指相关性很低、Beta ≪1，所以**不用**美国的「Beta>1 = 偏股」。改为截面相对排序：`score = z(股Beta) − z(债Beta)`，前 1/3 为偏股，后 1/3 为偏债，中间为中性。
- 与人工策略标签交叉：防御型应偏债，周期型 / 扩张型应偏股；落在相反一端的记 `disagree` 并列表。
- 前端：策略分类页「股/债 Beta 定位」卡，包括散点（债 Beta × 股 Beta，菱形 = 不一致）、52 周滚动折线、板块表和不一致清单。资产相关性页的相关散点保留，并在该卡加了链接。
- **当前状态：pending**。box 无法访问腾讯 K 线（WAF 拦截），本 PR 没有生成任何 Beta 数值；`scripts/sync_static_embeds.py` 只写入 `status=pending`。合并后，CI 下一次运行 `fetch_data_em.py` 会用真实行情计算。单元测试使用合成夹具（`tests/test_beta_calc.py`），夹具只用于测试，不作为数据。

## 4. 中国 9 业态时钟先验（P1-4）· `advice.json.clockSectorPrior`

**映射由本仪表盘提出，不是原文观点**，待学派复核。「配置与风险 → 板块筛选」表下方新增「时钟先验」面板（`allocation-tools.js` 直读 `advice.json`，当前象限取自核心 `data.json.cycle.rateClock`，不依赖 `data_research.json`），冲突行标黄。

| 中国板块 | 美国类比 | 最佳 | 雷区 | 置信 |
|---|---|---|---|---|
| 仓储物流 | 工业/物流 | Q2 | Q4·滞胀 | 高 |
| 数据中心 | 数据中心 | Q2 | Q4 | 中高 |
| 消费 | 购物中心 / 社区商业 | Q4 / Q2 | **Q3** | 中（`conflictFlag`） |
| 产业园 | 办公 | Q2 | Q3 / Q4 | 中 |
| 保租房 | 出租公寓（政策托底） | Q2 | Q4·滞胀 | 中低 |
| 高速 / 能源 / 市政环保 | 基建（经营权） | Q2 | Q4 | 低 |
| 商业不动产 | 多元化 / 办公 / 酒店 | 未给出 | Q3 | 低 |

## 5. 升息快于租金闸门（P1-5）· `cycle_judgment.json.rateRentGate`

- 规则：**Δ10Y(60 交易日) ≥ +25bp 且 产权利差分位 60 日下降 ≥ 20pp** → 风险 `rate_equity_divert` 升为「高」，估值闸门 `valuation` 降为 `partial`（前端叠加显示，不自动改写 `advice.json`）。
- 利率腿用真实 10Y；产权利差分位腿目前只有 `data_panel_l1l7.json` 的 SEED（`seedMeta.liveFetch=false`），所以标为 **pending data**。
- 条件是 AND：利率腿用真实数据明确未满足时，整体为 `not_triggered`，`dataStatus` 为 `partial`；利率腿满足但分位腿仍是 pending 时，整体为 `pending data`。
- 当前：Δ10Y −5.9bp，未满足 → `not_triggered`（partial）。

## 6. 校验与测试

- `python3 validate_rate_clock.py`：逐项核对原文数字，要求口径为年化总回报、业态无点值、占位矩阵已移除、rateClock / rateRentGate 枚举合法、clockSectorPrior 覆盖 9 个板块且声明为假设、advice.js 与 advice.json 同步、betas 为 pending 时不得含数值。
- `python3 -m unittest discover -s tests -p 'test_*.py'`；`npm test`。
- 手工刷新嵌入：`python3 update_cycle_data.py && python3 scripts/sync_static_embeds.py`。

## 7. 已知局限

1. PMI 只是 GDP 的月度替代；阈值 50 与美国「GDP 2%」没有经过校准。2021–2026 年中国利率几乎单边下行，升息象限样本很少，中国本土分象限回测（P2-6）尚未做。
2. 死区内的倾向判断置信度低，前端已标注。
3. Beta 窗口受腾讯接口 500 根日线限制（约 100 周）；新上市个券不足 40 周时置空。
4. 美国先验数值的方法细节不明（见 §1）；中美业态映射是假设。
