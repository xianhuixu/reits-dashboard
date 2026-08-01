#!/bin/bash
# REITs Dashboard 自动更新脚本
# 每个交易日下午运行：拉取最新代码、更新信息流、提交推送

set -e
cd /root/.openclaw/workspace

LOG_FILE="/root/.openclaw/workspace/scripts/auto_update.log"
HOLIDAYS_FILE="/root/.openclaw/workspace/holidays.txt"

green() { echo -e "\033[32m$1\033[0m"; }
red() { echo -e "\033[31m$1\033[0m"; }
yellow() { echo -e "\033[33m$1\033[0m"; }

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# 日志轮转：超过 5MB 时截断
rotate_log() {
    if [ -f "$LOG_FILE" ] && [ "$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)" -gt 5242880 ]; then
        tail -n 1000 "$LOG_FILE" > "${LOG_FILE}.tmp"
        mv "${LOG_FILE}.tmp" "$LOG_FILE"
        log "日志已轮转（保留最后1000行）"
    fi
}

rotate_log

log "=== REITs Dashboard Auto Update Started ==="

# 1. 判断是否为交易日（排除周末）
dow=$(date +%u)
if [ "$dow" -gt 5 ]; then
    log "周末，跳过更新"
    exit 0
fi

# 2. 判断是否为节假日
today=$(date +%Y-%m-%d)
if [ -f "$HOLIDAYS_FILE" ]; then
    holiday=$(grep "^${today}=" "$HOLIDAYS_FILE" | cut -d= -f2)
    if [ -n "$holiday" ]; then
        log "节假日（${holiday}），跳过更新"
        exit 0
    fi
fi

# 3. 拉取最新代码（包含本地 Mac 更新的 data.js）
log "[1/4] Pulling latest code from GitHub..."
if ! git pull origin main >> "$LOG_FILE" 2>&1; then
    log "ERROR: Git pull failed"
    exit 1
fi

# 5. 更新行情数据（基于本地 hist_cache 数据生成 data.js）
log "[3/4] Updating market data from local cache..."
if timeout 120 python3 fetch_data_server_v2.py >> "$LOG_FILE" 2>&1; then
    log "Market data processed successfully"
else
    exit_code=$?
    log "WARNING: fetch_data_server_v2.py exited with code ${exit_code}"
fi

# 6. 更新信息流（东方财富新闻 + 搜狗微信 + 招标投标平台）
log "[4/4] Updating news feed..."
if timeout 300 python3 fetch_news.py >> "$LOG_FILE" 2>&1; then
    log "News update completed successfully"
else
    exit_code=$?
    log "WARNING: News update exited with code ${exit_code} (may be timeout or error)"
fi

# 7. 检查是否有变更需要提交
log "[5/4] Checking for changes..."
if git diff --quiet && git diff --cached --quiet; then
    log "No changes to commit, nothing to do"
    exit 0
fi

# 7. 提交并推送到 GitHub（自动触发 GitHub Pages 部署）
log "[5/4] Committing and pushing..."
git add -A
git commit -m "auto: update REITs dashboard $(date '+%Y-%m-%d %H:%M')" >> "$LOG_FILE" 2>&1
if git push origin main >> "$LOG_FILE" 2>&1; then
    log "SUCCESS: Push completed - GitHub Pages will auto-deploy shortly"
    log "Site: https://xianhuixu.github.io/reits-dashboard"
else
    log "ERROR: Git push failed"
    exit 1
fi

log "=== Auto Update Finished ==="
echo "" >> "$LOG_FILE"
