#!/bin/bash
# 全量数据更新脚本
set -e
cd /root/.openclaw/workspace

LOG_FILE="/root/.openclaw/workspace/scripts/full_update_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== REITs Dashboard 全量数据更新 ==="
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"

# 1. 更新行情数据
echo "[1/5] 更新行情数据 (fetch_data_em.py)..."
if python3 fetch_data_em.py; then
    echo "✓ 行情数据更新成功"
else
    echo "✗ fetch_data_em.py 失败，尝试兜底方案 fetch_data_server_v2.py..."
    python3 fetch_data_server_v2.py || echo "⚠ 兜底方案也失败"
fi

# 2. 更新周期判断数据
echo "[2/5] 更新周期判断数据 (update_cycle_data.py)..."
if python3 update_cycle_data.py; then
    echo "✓ 周期判断数据更新成功"
else
    echo "⚠ 周期判断数据更新失败，继续执行后续步骤"
fi

# 3. 更新信息流
echo "[3/5] 更新信息流 (fetch_news.py)..."
if python3 fetch_news.py; then
    echo "✓ 信息流更新成功"
else
    echo "⚠ 信息流更新失败"
fi

# 4. 数据质量校验
echo "[4/4] 数据质量校验 (check_data.py)..."
if python3 check_data.py; then
    echo "✓ 数据校验通过"
else
    echo "⚠ 数据校验未通过，请检查日志"
fi

# 5. 提交推送
echo "[5/5] 提交并推送..."
git add -A
git commit -m "auto: update REITs dashboard $(date '+%Y-%m-%d %H:%M')" || echo "无变更需要提交"
git push origin main && echo "✓ 推送成功" || echo "✗ 推送失败"

echo ""
echo "=== 更新完成 ==="
echo "结束时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "日志: $LOG_FILE"
