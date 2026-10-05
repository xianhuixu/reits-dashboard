# 经营权披露 IRR 利差（2025 年末口径）

`scripts/build_oper_irr.py` 写入 `data_panel_l1l7.json.operatingDisclosedIrr`。

- **主口径**：基金披露 IRR − 期限匹配国债（WAL 优先，否则剩余年限；`cgb_curve.interp_yield`）。
- **曲线**：固定 **2025-12-31** 中债 2/5/10/30Y（与披露 IRR 同日）；禁止混用现价日曲线。
- **自算 IRR**：仅悬浮提示，注明「对账偏高，中位约 280bp」。
- **暂无披露**：图下灰色空心点（同置信度中形态）。
- **展示约束**：利差列不可排序；业态不汇总（「口径不统一，暂不汇总」）；极端利差（如 180402）只看自身。
- **横幅**：`feedsBanner=false`，不回写结论横幅；经营权维持「标配」。
- **状态**：曲线/披露表可用 → `ok`；刷新失败沿用缓存 → `lagged`（角标「滞后 · 数据截至 MM-DD」）。

数据缓存：`oper_irr_cache/irr_summary.csv`、`prices_2025ye.json`、`cgb_curve_20251231.json`。
