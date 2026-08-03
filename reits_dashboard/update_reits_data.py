#!/usr/bin/env python3
"""
REITs Dashboard 数据更新脚本
接入同花顺(stock_finance_data)数据库，自动获取REITs实时行情与历史数据

用法:
    python3 update_reits_data.py           # 更新所有REITs数据
    python3 update_reits_data.py --price   # 仅更新价格数据
    python3 update_reits_data.py --tech    # 更新技术指标
"""

import json
import os
import sys
import subprocess
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# 配置
DATA_DIR = Path(__file__).parent
OUTPUT_DIR = DATA_DIR / "data"
OUTPUT_DIR.mkdir(exist_ok=True)

REITS_LIST_FILE = DATA_DIR / "reits_list.json"
DASHBOARD_DATA_FILE = OUTPUT_DIR / "dashboard_data.json"
HISTORY_DATA_FILE = OUTPUT_DIR / "history_data.csv"


def load_reits_list():
    """加载REITs列表"""
    with open(REITS_LIST_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    all_reits = []
    for reit in data.get('reits', []):
        all_reits.append(reit)
    for reit in data.get('reits_sz', []):
        all_reits.append(reit)
    
    return all_reits


def get_stock_info(tickers):
    """获取股票基本信息"""
    if not tickers:
        return {}
    
    ticker_str = ','.join(tickers)
    output_file = OUTPUT_DIR / "stock_info.csv"
    
    try:
        # 使用 kimi_datasource_call 工具获取数据
        # 这里我们通过调用同花顺API
        from kimi_datasource_call import get_stock_info as ths_get_info
        result = ths_get_info(ticker=ticker_str, file_path=str(output_file))
        
        if output_file.exists():
            df = pd.read_csv(output_file)
            return df.to_dict('records')
    except Exception as e:
        print(f"获取股票信息失败: {e}")
    
    return {}


def get_realtime_price_batch(tickers):
    """批量获取实时价格（每次最多3个）"""
    all_data = []
    
    # 分批处理，每批3个
    for i in range(0, len(tickers), 3):
        batch = tickers[i:i+3]
        ticker_str = ','.join(batch)
        output_file = OUTPUT_DIR / f"realtime_{i}.csv"
        
        try:
            # 调用同花顺API获取实时价格
            import subprocess
            result = subprocess.run([
                'python3', '-c', f'''
from kimi_datasource_call import get_stock_realtime_price
get_stock_realtime_price(
    ticker="{ticker_str}",
    type="realtime_price",
    file_path="{output_file}"
)
'''
            ], capture_output=True, text=True, timeout=30)
            
            if output_file.exists():
                df = pd.read_csv(output_file)
                all_data.append(df)
                
        except Exception as e:
            print(f"获取实时价格失败 ({ticker_str}): {e}")
    
    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return pd.DataFrame()


def get_history_price(tickers, days=30):
    """获取历史价格数据"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    all_data = []
    
    for i in range(0, len(tickers), 3):
        batch = tickers[i:i+3]
        ticker_str = ','.join(batch)
        output_file = OUTPUT_DIR / f"history_{i}.csv"
        
        try:
            import subprocess
            result = subprocess.run([
                'python3', '-c', f'''
from kimi_datasource_call import get_stock_price
get_stock_price(
    ticker="{ticker_str}",
    start_date="{start_date.strftime('%Y-%m-%d')}",
    end_date="{end_date.strftime('%Y-%m-%d')}",
    interval="D",
    adjust="forward",
    file_path="{output_file}"
)
'''
            ], capture_output=True, text=True, timeout=60)
            
            if output_file.exists():
                df = pd.read_csv(output_file)
                all_data.append(df)
                
        except Exception as e:
            print(f"获取历史价格失败 ({ticker_str}): {e}")
    
    if all_data:
        return pd.concat(all_data, ignore_index=True)
    return pd.DataFrame()


def calculate_metrics(history_df):
    """计算关键指标"""
    if history_df.empty:
        return {}
    
    metrics = {}
    
    # 按股票代码分组计算
    for ticker in history_df['thscode'].unique():
        df = history_df[history_df['thscode'] == ticker].sort_values('time')
        
        if len(df) < 2:
            continue
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 日涨跌幅
        daily_change = (latest['close'] - prev['close']) / prev['close'] * 100 if prev['close'] != 0 else 0
        
        # 30日涨跌幅
        if len(df) >= 30:
            month_ago = df.iloc[-30]
            monthly_change = (latest['close'] - month_ago['close']) / month_ago['close'] * 100
        else:
            monthly_change = 0
        
        # 成交量均值
        avg_volume = df['volume'].mean()
        
        # 波动率（标准差）
        volatility = df['close'].pct_change().std() * 100
        
        metrics[ticker] = {
            'latest_price': round(latest['close'], 4),
            'daily_change_pct': round(daily_change, 2),
            'monthly_change_pct': round(monthly_change, 2),
            'latest_volume': int(latest['volume']),
            'avg_volume': int(avg_volume),
            'volatility': round(volatility, 2),
            'high_30d': round(df['high'].max(), 4),
            'low_30d': round(df['low'].min(), 4),
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    
    return metrics


def generate_dashboard_data(reits_list, metrics):
    """生成Dashboard数据"""
    dashboard_data = {
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_count': len(reits_list),
        'categories': {}
    }
    
    # 按分类统计
    for reit in reits_list:
        category = reit['category']
        if category not in dashboard_data['categories']:
            dashboard_data['categories'][category] = []
        
        ticker = reit['code']
        reit_data = {
            'code': ticker,
            'name': reit['name'],
            'category': category,
            'list_date': reit['list_date']
        }
        
        # 合并指标数据
        if ticker in metrics:
            reit_data.update(metrics[ticker])
        
        dashboard_data['categories'][category].append(reit_data)
    
    # 保存数据
    with open(DASHBOARD_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(dashboard_data, f, ensure_ascii=False, indent=2)
    
    return dashboard_data


def print_summary(dashboard_data):
    """打印数据摘要"""
    print("\n" + "="*80)
    print(f"REITs Dashboard 数据更新完成 - {dashboard_data['update_time']}")
    print("="*80)
    print(f"总计: {dashboard_data['total_count']} 只REITs")
    print(f"分类: {', '.join(dashboard_data['categories'].keys())}")
    print("\n各板块概况:")
    print("-"*80)
    
    for category, items in dashboard_data['categories'].items():
        print(f"\n【{category}】({len(items)}只)")
        for item in items[:5]:  # 只显示前5只
            price = item.get('latest_price', 'N/A')
            change = item.get('daily_change_pct', 'N/A')
            if change != 'N/A':
                change_str = f"+{change}%" if change >= 0 else f"{change}%"
            else:
                change_str = "N/A"
            print(f"  {item['code']} {item['name']}: ¥{price} ({change_str})")
        
        if len(items) > 5:
            print(f"  ... 共{len(items)}只")
    
    print("\n" + "="*80)
    print(f"数据文件已保存至: {DASHBOARD_DATA_FILE}")
    print("="*80 + "\n")


def main():
    """主函数"""
    print("REITs Dashboard 数据更新启动...")
    
    # 加载REITs列表
    reits_list = load_reits_list()
    print(f"加载了 {len(reits_list)} 只REITs")
    
    # 获取所有ticker
    tickers = [reit['code'] for reit in reits_list]
    
    # 获取历史数据（最近30天）
    print("正在获取历史价格数据...")
    history_df = get_history_price(tickers, days=30)
    
    if not history_df.empty:
        # 保存历史数据
        history_df.to_csv(HISTORY_DATA_FILE, index=False)
        print(f"历史数据已保存: {HISTORY_DATA_FILE}")
        
        # 计算指标
        print("正在计算关键指标...")
        metrics = calculate_metrics(history_df)
        
        # 生成Dashboard数据
        print("正在生成Dashboard数据...")
        dashboard_data = generate_dashboard_data(reits_list, metrics)
        
        # 打印摘要
        print_summary(dashboard_data)
    else:
        print("警告: 未能获取历史数据，请检查网络连接或API配置")
        # 生成空数据
        dashboard_data = generate_dashboard_data(reits_list, {})
        print_summary(dashboard_data)


if __name__ == '__main__':
    main()
