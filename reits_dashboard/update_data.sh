#!/bin/bash
# REITs Dashboard 数据更新脚本
# 批量获取同花顺数据并生成Dashboard

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$SCRIPT_DIR/data"
mkdir -p "$DATA_DIR"

echo "=========================================="
echo "REITs Dashboard 数据更新"
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# REITs 代码列表 (上海)
REITS_SH=(
    "508000.SH"
    "508001.SH"
    "508006.SH"
    "508008.SH"
    "508009.SH"
    "508018.SH"
    "508019.SH"
    "508021.SH"
    "508027.SH"
    "508028.SH"
    "508056.SH"
    "508066.SH"
    "508068.SH"
    "508077.SH"
    "508096.SH"
    "508098.SH"
    "508099.SH"
    "508033.SH"
)

# REITs 代码列表 (深圳)
REITS_SZ=(
    "180101.SZ"
    "180201.SZ"
    "180301.SZ"
    "180401.SZ"
    "180501.SZ"
    "180601.SZ"
    "180701.SZ"
    "180801.SZ"
    "180901.SZ"
)

# 合并所有代码
ALL_REITS=(${REITS_SH[@]} ${REITS_SZ[@]})

echo ""
echo "正在获取 ${#ALL_REITS[@]} 只REITs的历史数据..."
echo ""

# 获取历史数据（最近30天）
END_DATE=$(date +%Y-%m-%d)
START_DATE=$(date -d "30 days ago" +%Y-%m-%d)

# 分批获取，每批3个
BATCH_SIZE=3
TOTAL=${#ALL_REITS[@]}

for ((i=0; i<TOTAL; i+=BATCH_SIZE)); do
    BATCH=()
    for ((j=0; j<BATCH_SIZE && i+j<TOTAL; j++)); do
        BATCH+=("${ALL_REITS[i+j]}")
    done
    
    TICKER_STR=$(IFS=,; echo "${BATCH[*]}")
    OUTPUT_FILE="$DATA_DIR/history_$(printf "%03d" $i).csv"
    
    echo "[$((i+1))/$TOTAL] 获取: $TICKER_STR"
    
    # 这里需要通过 OpenClaw 工具调用
    # 实际使用时，可以在 OpenClaw 会话中运行此脚本
    # 或使用 API 调用
    
    sleep 1  # 避免请求过于频繁
done

echo ""
echo "数据获取完成，输出目录: $DATA_DIR"
echo "=========================================="
