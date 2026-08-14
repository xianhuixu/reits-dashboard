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

# 5. 更新行情数据
# 主路径：fetch_data_em.py 直连腾讯行情（增量更新 hist_cache + 单位自愈 + 生成 data.js/data.json）
# 兜底：fetch_data_server_v2.py 基于现有 hist_cache 生成（腾讯直连失败时使用）
log "[3/4] Updating market data (tencent direct, cache fallback)..."
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

# 5b. 数据质量闸门：data.js 校验不通过则不推送（保护线上数据）
log "[3b/4] Validating data quality..."
if python3 check_data.py >> "$LOG_FILE" 2>&1; then
    log "Data quality check passed"
else
    log "ERROR: Data quality check FAILED - skipping push to protect live site"
    exit 1
fi

# 6. 更新信息流（东方财富新闻 + 搜狗微信 + 招标投标平台）
log "[4/4] Updating news feed..."
if timeout 300 python3 fetch_news.py >> "$LOG_FILE" 2>&1; then
    log "News update completed successfully"
else
    exit_code=$?
    log "WARNING: News update exited with code ${exit_code} (may be timeout or error)"
fi

# 6. 更新项目申报与推荐动态（发改委 / 上交所 / 深交所）
log "[5/5] Updating project filing dynamics..."
if timeout 180 python3 fetch_projects.py >> "$LOG_FILE" 2>&1; then
    log "Project dynamics update completed successfully"
else
    exit_code=$?
    log "WARNING: fetch_projects.py exited with code ${exit_code} (may be timeout or error)"
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
