#!/bin/bash
# REITs Dashboard 全量数据更新脚本
# 集成: 行情 → 周期判断 → 信息流 → 质量闸门 → 推送
# 路径自适配：不再依赖固定 /root/.openclaw/workspace

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$SCRIPT_DIR/full_update_$(date +%Y%m%d_%H%M%S).log"

cd "$WORK_DIR"

echo "=== REITs Dashboard 全量数据更新 ==="
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "工作目录: $WORK_DIR"
echo "日志: $LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1

# 1. 行情数据
echo ""
echo "[1/5] 更新行情数据 (fetch_data_em.py)..."
if python3 fetch_data_em.py; then
    echo "[ok] 行情数据更新成功"
else
    echo "[warn] fetch_data_em.py 失败，尝试兜底 fetch_data_server_v2.py..."
    if ! python3 fetch_data_server_v2.py; then
        echo "[error] 兜底方案也失败"
        exit 1
    fi
    echo "[ok] 行情数据由 hist_cache 兜底生成"
fi

# 2. 周期判断数据
echo ""
echo "[2/5] 更新周期判断数据 (update_cycle_data.py)..."
if python3 update_cycle_data.py; then
    echo "[ok] 周期判断数据更新成功"
else
    echo "[warn] 周期判断数据更新失败，继续执行后续步骤"
fi

# 3. 信息流（公告 + 新闻）
echo ""
echo "[3/5] 更新信息流 (fetch_news.py)..."
if python3 fetch_news.py; then
    echo "[ok] 信息流更新成功"
else
    echo "[warn] 信息流更新失败"
fi

# 4. 数据质量闸门（保护线上）
echo ""
echo "[4/5] 数据质量校验 (check_data.py)..."
if python3 check_data.py; then
    echo "[ok] 数据校验通过"
else
    echo "[error] 数据校验未通过 —— 放弃推送，保护线上数据"
    exit 1
fi

# 5. 提交推送
echo ""
echo "[5/5] 提交并推送..."
git add -A
git commit -m "auto: update REITs dashboard $(date '+%Y-%m-%d %H:%M')" || echo "无变更需要提交"
if git push origin main; then
    echo "[ok] 推送成功"
else
    echo "[error] 推送失败"
    exit 1
fi

echo ""
echo "=== 更新完成 ==="
echo "结束时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "日志: $LOG_FILE"
