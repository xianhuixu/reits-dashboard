#!/bin/bash
# REITs Dashboard 复核重试脚本
# 每个交易日 20:00 运行：检查当天是否已完成数据更新，如未更新则自动重试
# 路径自适配：不再依赖固定 /root/.openclaw/workspace

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$SCRIPT_DIR/auto_update.log"
HOLIDAYS_FILE="$WORK_DIR/holidays.txt"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [VERIFY] $1" | tee -a "$LOG_FILE"
}

# 0. 交易日判断
dow=$(date +%u)
if [ "$dow" -gt 5 ]; then
    log "周末，跳过复核"
    exit 0
fi

today=$(date +%Y-%m-%d)
if [ -f "$HOLIDAYS_FILE" ]; then
    holiday=$(grep "^${today}=" "$HOLIDAYS_FILE" | cut -d= -f2)
    if [ -n "$holiday" ]; then
        log "节假日（${holiday}），跳过复核"
        exit 0
    fi
fi

log "=== REITs Dashboard 复核检查 Started ==="

# 1. 检查今天是否已有数据更新提交
cd "$WORK_DIR"
today_commits=$(git log --oneline --since="${today} 00:00" --until="${today} 23:59" --grep="数据更新:" | wc -l)

if [ "$today_commits" -gt 0 ]; then
    log "✅ 今天已找到 ${today_commits} 次数据更新提交，无需重试"
    latest_commit=$(git log --oneline --since="${today} 00:00" --until="${today} 23:59" --grep="数据更新:" | head -1)
    log "   最新: ${latest_commit}"
    log "=== 复核通过 ==="
    exit 0
fi

# 2. 检查 data.js 最后修改时间是否在今天
data_js_date=$(stat -c %y "$WORK_DIR/data.js" 2>/dev/null | cut -d' ' -f1)
if [ "$data_js_date" = "$today" ]; then
    log "✅ data.js 今天已更新 (${data_js_date})，无需重试"
    log "=== 复核通过 ==="
    exit 0
fi

log "⚠️ 今天尚未找到数据更新提交，开始自动重试..."
log "   data.js 最后修改: ${data_js_date:-unknown}"

# 3. 运行自动更新
if bash "$SCRIPT_DIR/auto_update.sh" >> "$LOG_FILE" 2>&1; then
    log "✅ 重试成功"
else
    log "❌ 重试失败，请手动检查"
    exit 1
fi

log "=== 复核重试完成 ==="
