# 产权利差（真实序列）

`scripts/build_spread.py` 每日由 `update_cycle_data.py` 调用（`--refresh`）。

- **默认分位**：滚动 3 年（`pct_rolling3y`）；全样本（2022 以来）仅悬浮提示。
- **状态**：取数覆盖 ≥90% → `ok`；否则沿用 `spread_cache/`、`status=lagged`，角标「滞后 · 数据截至 MM-DD」（绝不标 live）。
- **分派同比**：TTM 对 TTM，截面中位数，±2% 容差 → 下滑 / 企稳 / 增长。
- **横幅第二条依据**：仅 `status=ok` 且分派同比中位数 > −2% 时显示「产权利差分位 X%（滚动3年）」；否则灰字说明原因。
- **stanceOverride**：`advice.json` 可配置（当前「产权标配·偏多观察」）；横幅与配置表产权行以此为准。
- **经营权披露 IRR**：见 `docs/operating-disclosed-irr.md`（`operatingDisclosedIrr`，2025 年末口径）；月度时序仍为 SEED。
