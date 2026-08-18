#!/bin/bash
# REITs Dashboard 自动更新脚本
# 每个交易日下午运行：拉取最新代码、更新行情与信息流、数据校验、提交推送
# 路径自适配：不再依赖固定 /root/.openclaw/workspace

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$(dirname "$SCRIPT_DIR")"
cd "$WORK_DIR"

LOG_FILE="$SCRIPT_DIR/auto_update.log"
HOLIDAYS_FILE="$WORK_DIR/holidays.txt"

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

# 0. 交易日判断
dow=$(date +%u)
if [ "$dow" -gt 5 ]; then
    log "周末，跳过更新"
    exit 0
fi

today=$(date +%Y-%m-%d)
if [ -f "$HOLIDAYS_FILE" ]; then
    holiday=$(grep "^${today}=" "$HOLIDAYS_FILE" | cut -d= -f2)
    if [ -n "$holiday" ]; then
        log "节假日（${holiday}），跳过更新"
        exit 0
    fi
fi

# 1. 拉取最新代码
log "[1/6] Pulling latest code from GitHub..."
if ! git pull origin main >> "$LOG_FILE" 2>&1; then
    log "ERROR: Git pull failed"
    exit 1
fi

# 2. 行情数据（主路径腾讯直连，兜底 hist_cache）
log "[2/6] Updating market data (tencent direct, cache fallback)..."
if timeout 600 python3 fetch_data_em.py >> "$LOG_FILE" 2>&1; then
    log "Market data updated via fetch_data_em.py (tencent direct)"
else
    exit_code=$?
    log "WARNING: fetch_data_em.py exited with code ${exit_code}, falling back to cache-based server_v2"
    if timeout 120 python3 fetch_data_server_v2.py >> "$LOG_FILE" 2>&1; then
        log "Market data processed from hist_cache (server_v2)"
    else
        log "ERROR: both market data scripts failed"
    fi
fi

# 3. 数据质量闸门：data.js 校验不通过则不推送（保护线上数据）
log "[3/6] Validating data quality..."
if python3 check_data.py >> "$LOG_FILE" 2>&1; then
    log "Data quality check passed"
else
    log "ERROR: Data quality check FAILED - skipping push to protect live site"
    exit 1
fi

# 4. 信息流（东方财富新闻 + 搜狗微信 + 招标投标平台）
log "[4/6] Updating news feed..."
if timeout 300 python3 fetch_news.py >> "$LOG_FILE" 2>&1; then
    log "News update completed successfully"
else
    exit_code=$?
    log "WARNING: News update exited with code ${exit_code} (may be timeout or error)"
fi

# 5. 项目申报与推荐动态（发改委 / 上交所 / 深交所）
log "[5/6] Updating project filing dynamics..."
if timeout 180 python3 fetch_projects.py >> "$LOG_FILE" 2>&1; then
    log "Project dynamics update completed successfully"
else
    exit_code=$?
    log "WARNING: fetch_projects.py exited with code ${exit_code} (may be timeout or error)"
fi

# 6. 提交并推送到 GitHub（自动触发 GitHub Pages 部署）
log "[6/6] Checking for changes & pushing..."
if git diff --quiet && git diff --cached --quiet; then
    log "No changes to commit, nothing to do"
    exit 0
fi

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
