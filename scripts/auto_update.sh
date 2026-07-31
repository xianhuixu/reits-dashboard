#!/bin/bash
set -e
cd /root/.openclaw/workspace

LOG_FILE="/root/.openclaw/workspace/scripts/auto_update.log"

echo "=== REITs Dashboard Auto Update ===" | tee -a "$LOG_FILE"
echo "Start: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"

# 1. 判断是否为交易日（排除周末）
dow=$(date +%u)
if [ "$dow" -gt 5 ]; then
    echo "周末，跳过更新" | tee -a "$LOG_FILE"
    exit 0
fi

# 2. 拉取最新代码（包含本地更新的 data.js）
echo "[1/4] Pulling latest code..." | tee -a "$LOG_FILE"
if ! git pull origin main 2>&1 | tee -a "$LOG_FILE"; then
    echo "Git pull failed, aborting" | tee -a "$LOG_FILE"
    exit 1
fi

# 3. 更新信息流
echo "[2/4] Updating news feed..." | tee -a "$LOG_FILE"
if timeout 300 python3 fetch_news.py 2>&1 | tee -a "$LOG_FILE"; then
    echo "News update completed" | tee -a "$LOG_FILE"
else
    echo "News update completed or timed out (exit code: $?)" | tee -a "$LOG_FILE"
fi

# 4. 检查是否有变更
echo "[3/4] Checking for changes..." | tee -a "$LOG_FILE"
if git diff --quiet && git diff --cached --quiet; then
    echo "No changes to commit" | tee -a "$LOG_FILE"
    exit 0
fi

# 5. 提交并推送
echo "[4/4] Committing and pushing..." | tee -a "$LOG_FILE"
git add -A
git commit -m "auto: update REITs news feed $(date '+%Y-%m-%d %H:%M')" | tee -a "$LOG_FILE"
if git push origin main 2>&1 | tee -a "$LOG_FILE"; then
    echo "Push successful" | tee -a "$LOG_FILE"
else
    echo "Push failed" | tee -a "$LOG_FILE"
    exit 1
fi

echo "Done: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
echo "---" | tee -a "$LOG_FILE"
