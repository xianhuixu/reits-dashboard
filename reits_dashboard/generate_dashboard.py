#!/usr/bin/env python3
"""
REITs Dashboard 数据处理器
处理同花顺数据并生成可视化Dashboard
"""

import json
import os
import glob
import pandas as pd
from datetime import datetime
from pathlib import Path

DATA_DIR = Path("/root/.openclaw/workspace/reits_dashboard/data")
OUTPUT_DIR = Path("/root/.openclaw/workspace/reits_dashboard")

# REITs 名称映射
REITS_INFO = {
    "508000.SH": {"name": "华安张江光大REIT", "category": "产业园区"},
    "508001.SH": {"name": "浙商沪杭甬REIT", "category": "高速公路"},
    "508006.SH": {"name": "富国首创水务REIT", "category": "环保"},
    "508008.SH": {"name": "国金中国铁建REIT", "category": "高速公路"},
    "508009.SH": {"name": "平安广州广河REIT", "category": "高速公路"},
    "508018.SH": {"name": "华夏中国交建REIT", "category": "高速公路"},
    "508019.SH": {"name": "中金湖北科投光谷REIT", "category": "产业园区"},
    "508021.SH": {"name": "国泰海通临港创新REIT", "category": "产业园区"},
    "508027.SH": {"name": "东吴苏州工业园区REIT", "category": "产业园区"},
    "508028.SH": {"name": "中金普洛斯REIT", "category": "仓储物流"},
    "508056.SH": {"name": "中金厦门安居REIT", "category": "保障性租赁住房"},
    "508066.SH": {"name": "华泰江苏交控REIT", "category": "高速公路"},
    "508068.SH": {"name": "华夏北京保障房REIT", "category": "保障性租赁住房"},
    "508077.SH": {"name": "华夏基金华润有巢REIT", "category": "保障性租赁住房"},
    "508096.SH": {"name": "嘉实京东仓储REIT", "category": "仓储物流"},
    "508098.SH": {"name": "嘉实中国电建清洁能源REIT", "category": "能源"},
    "508099.SH": {"name": "建信中关村REIT", "category": "产业园区"},
    "508033.SH": {"name": "易方达深高速REIT", "category": "高速公路"},
    "180101.SZ": {"name": "博时蛇口产园REIT", "category": "产业园区"},
    "180201.SZ": {"name": "中航首钢绿能REIT", "category": "环保"},
    "180301.SZ": {"name": "红土深圳安居REIT", "category": "保障性租赁住房"},
    "180401.SZ": {"name": "鹏华深圳能源REIT", "category": "能源"},
    "180501.SZ": {"name": "华夏和达高科REIT", "category": "产业园区"},
    "180601.SZ": {"name": "国金中国铁建REIT", "category": "高速公路"},
    "180701.SZ": {"name": "银华绍兴原水水利REIT", "category": "水利"},
    "180801.SZ": {"name": "华夏合肥高新REIT", "category": "产业园区"},
    "180901.SZ": {"name": "平安宁波交投REIT", "category": "高速公路"},
}


def load_all_data():
    """加载所有CSV数据文件"""
    all_dfs = []
    csv_files = sorted(DATA_DIR.glob("reits_batch*.csv"))
    
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            all_dfs.append(df)
        except Exception as e:
            print(f"读取文件失败 {csv_file}: {e}")
    
    if all_dfs:
        return pd.concat(all_dfs, ignore_index=True)
    return pd.DataFrame()


def calculate_metrics(df):
    """计算每只REIT的关键指标"""
    metrics = []
    
    for ticker in df['thscode'].unique():
        ticker_df = df[df['thscode'] == ticker].sort_values('time')
        
        if len(ticker_df) < 2:
            continue
        
        latest = ticker_df.iloc[-1]
        prev = ticker_df.iloc[-2]
        
        # 日涨跌幅
        daily_change = ((latest['close'] - prev['close']) / prev['close'] * 100) if prev['close'] != 0 else 0
        
        # 周涨跌幅（近5个交易日）
        if len(ticker_df) >= 5:
            week_ago = ticker_df.iloc[-5]
            weekly_change = ((latest['close'] - week_ago['close']) / week_ago['close'] * 100)
        else:
            weekly_change = 0
        
        # 月涨跌幅
        if len(ticker_df) >= 20:
            month_ago = ticker_df.iloc[-20]
            monthly_change = ((latest['close'] - month_ago['close']) / month_ago['close'] * 100)
        else:
            first = ticker_df.iloc[0]
            monthly_change = ((latest['close'] - first['close']) / first['close'] * 100)
        
        # 振幅
        amplitude = ((latest['high'] - latest['low']) / latest['low'] * 100) if latest['low'] != 0 else 0
        
        # 成交量均值
        avg_volume = ticker_df['volume'].mean()
        
        # 30日最高/最低
        high_30d = ticker_df['high'].max()
        low_30d = ticker_df['low'].min()
        
        info = REITS_INFO.get(ticker, {"name": ticker, "category": "未知"})
        
        metrics.append({
            'ticker': ticker,
            'name': info['name'],
            'category': info['category'],
            'latest_price': round(latest['close'], 3),
            'daily_change_pct': round(daily_change, 2),
            'weekly_change_pct': round(weekly_change, 2),
            'monthly_change_pct': round(monthly_change, 2),
            'amplitude': round(amplitude, 2),
            'volume': int(latest['volume']),
            'avg_volume': int(avg_volume),
            'high_30d': round(high_30d, 3),
            'low_30d': round(low_30d, 3),
            'date': latest['time']
        })
    
    return pd.DataFrame(metrics)


def generate_dashboard_html(metrics_df):
    """生成HTML Dashboard"""
    
    if metrics_df.empty:
        return "<h1>暂无数据</h1>"
    
    # 按日涨跌幅排序
    top_gainers = metrics_df.nlargest(5, 'daily_change_pct')
    top_losers = metrics_df.nsmallest(5, 'daily_change_pct')
    
    # 按板块分类统计
    category_stats = metrics_df.groupby('category').agg({
        'daily_change_pct': 'mean',
        'monthly_change_pct': 'mean',
        'volume': 'sum'
    }).round(2)
    
    # 生成表格行
    def make_table_rows(df, limit=None):
        rows = []
        data = df.head(limit) if limit else df
        for _, row in data.iterrows():
            change_class = 'positive' if row['daily_change_pct'] >= 0 else 'negative'
            weekly_class = 'positive' if row['weekly_change_pct'] >= 0 else 'negative'
            monthly_class = 'positive' if row['monthly_change_pct'] >= 0 else 'negative'
            
            rows.append(f"""
            <tr>
                <td><strong>{row['ticker']}</strong></td>
                <td>{row['name']}</td>
                <td><span class="badge">{row['category']}</span></td>
                <td class="price">¥{row['latest_price']}</td>
                <td class="{change_class}">{row['daily_change_pct']:+.2f}%</td>
                <td class="{weekly_class}">{row['weekly_change_pct']:+.2f}%</td>
                <td class="{monthly_class}">{row['monthly_change_pct']:+.2f}%</td>
                <td>{row['volume']:,}</td>
                <td>¥{row['low_30d']} - ¥{row['high_30d']}</td>
            </tr>
            """)
        return '\n'.join(rows)
    
    # 生成分类统计行
    def make_category_rows():
        rows = []
        for category, stats in category_stats.iterrows():
            change_class = 'positive' if stats['daily_change_pct'] >= 0 else 'negative'
            rows.append(f"""
            <tr>
                <td><strong>{category}</strong></td>
                <td class="{change_class}">{stats['daily_change_pct']:+.2f}%</td>
                <td class="{change_class}">{stats['monthly_change_pct']:+.2f}%</td>
                <td>{stats['volume']:,.0f}</td>
            </tr>
            """)
        return '\n'.join(rows)
    
    update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    total_count = len(metrics_df)
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>REITs Dashboard - 中国公募REITs行情监控</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        .header {{
            text-align: center;
            color: white;
            padding: 30px 0;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }}
        
        .header .subtitle {{
            font-size: 1.1em;
            opacity: 0.9;
        }}
        
        .header .update-time {{
            font-size: 0.9em;
            opacity: 0.7;
            margin-top: 10px;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        
        .stat-card {{
            background: white;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s;
        }}
        
        .stat-card:hover {{
            transform: translateY(-5px);
        }}
        
        .stat-card .number {{
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
        }}
        
        .stat-card .label {{
            color: #666;
            font-size: 0.9em;
            margin-top: 5px;
        }}
        
        .card {{
            background: white;
            border-radius: 12px;
            padding: 25px;
            margin: 20px 0;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}
        
        .card h2 {{
            font-size: 1.3em;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #f0f0f0;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .card h2 .icon {{
            font-size: 1.2em;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9em;
        }}
        
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        
        th {{
            font-weight: 600;
            color: #555;
            background: #f8f9fa;
        }}
        
        tr:hover {{
            background: #f8f9fa;
        }}
        
        .positive {{
            color: #e74c3c;
            font-weight: 600;
        }}
        
        .negative {{
            color: #27ae60;
            font-weight: 600;
        }}
        
        .price {{
            font-weight: 600;
            color: #333;
        }}
        
        .badge {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 0.8em;
            background: #e3f2fd;
            color: #1976d2;
        }}
        
        .top-section {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin: 20px 0;
        }}
        
        @media (max-width: 768px) {{
            .top-section {{
                grid-template-columns: 1fr;
            }}
            .header h1 {{
                font-size: 1.8em;
            }}
        }}
        
        .footer {{
            text-align: center;
            color: white;
            padding: 20px;
            opacity: 0.7;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏢 REITs Dashboard</h1>
            <div class="subtitle">中国公募REITs行情监控面板</div>
            <div class="update-time">数据更新时间: {update_time} | 数据源: 同花顺</div>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="number">{total_count}</div>
                <div class="label">监控REITs数量</div>
            </div>
            <div class="stat-card">
                <div class="number">{len(metrics_df[metrics_df['daily_change_pct'] > 0])}</div>
                <div class="label">上涨数量</div>
            </div>
            <div class="stat-card">
                <div class="number">{len(metrics_df[metrics_df['daily_change_pct'] < 0])}</div>
                <div class="label">下跌数量</div>
            </div>
            <div class="stat-card">
                <div class="number">{metrics_df['daily_change_pct'].mean():+.2f}%</div>
                <div class="label">平均涨跌幅</div>
            </div>
        </div>
        
        <div class="top-section">
            <div class="card">
                <h2><span class="icon">📈</span> 涨幅榜 TOP 5</h2>
                <table>
                    <thead>
                        <tr>
                            <th>代码</th>
                            <th>名称</th>
                            <th>价格</th>
                            <th>日涨跌</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join([f'<tr><td><strong>{row["ticker"]}</strong></td><td>{row["name"]}</td><td class="price">¥{row["latest_price"]}</td><td class="positive">{row["daily_change_pct"]:+.2f}%</td></tr>' for _, row in top_gainers.iterrows()])}
                    </tbody>
                </table>
            </div>
            
            <div class="card">
                <h2><span class="icon">📉</span> 跌幅榜 TOP 5</h2>
                <table>
                    <thead>
                        <tr>
                            <th>代码</th>
                            <th>名称</th>
                            <th>价格</th>
                            <th>日涨跌</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join([f'<tr><td><strong>{row["ticker"]}</strong></td><td>{row["name"]}</td><td class="price">¥{row["latest_price"]}</td><td class="negative">{row["daily_change_pct"]:+.2f}%</td></tr>' for _, row in top_losers.iterrows()])}
                    </tbody>
                </table>
            </div>
        </div>
        
        <div class="card">
            <h2><span class="icon">🏭</span> 板块表现</h2>
            <table>
                <thead>
                    <tr>
                        <th>板块</th>
                        <th>日均涨跌</th>
                        <th>月均涨跌</th>
                        <th>总成交量</th>
                    </tr>
                </thead>
                <tbody>
                    {make_category_rows()}
                </tbody>
            </table>
        </div>
        
        <div class="card">
            <h2><span class="icon">📊</span> 全部REITs行情</h2>
            <table>
                <thead>
                    <tr>
                        <th>代码</th>
                        <th>名称</th>
                        <th>板块</th>
                        <th>最新价</th>
                        <th>日涨跌</th>
                        <th>周涨跌</th>
                        <th>月涨跌</th>
                        <th>成交量</th>
                        <th>30日区间</th>
                    </tr>
                </thead>
                <tbody>
                    {make_table_rows(metrics_df.sort_values('daily_change_pct', ascending=False))}
                </tbody>
            </table>
        </div>
    </div>
    
    <div class="footer">
        <p>REITs Dashboard | 数据仅供参考，不构成投资建议</p>
    </div>
</body>
</html>"""
    
    return html


def main():
    print("正在处理REITs数据...")
    
    # 加载数据
    df = load_all_data()
    
    if df.empty:
        print("错误: 未找到数据文件")
        return
    
    print(f"已加载 {len(df)} 条数据记录")
    
    # 计算指标
    metrics_df = calculate_metrics(df)
    
    if metrics_df.empty:
        print("错误: 无法计算指标")
        return
    
    print(f"已计算 {len(metrics_df)} 只REITs指标")
    
    # 保存指标数据
    metrics_df.to_csv(OUTPUT_DIR / "metrics.csv", index=False, encoding='utf-8-sig')
    print("指标数据已保存")
    
    # 生成Dashboard
    html = generate_dashboard_html(metrics_df)
    
    # 保存HTML
    dashboard_path = OUTPUT_DIR / "dashboard.html"
    with open(dashboard_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"Dashboard已生成: {dashboard_path}")
    
    # 打印摘要
    print("\n" + "="*60)
    print("REITs Dashboard 数据摘要")
    print("="*60)
    print(f"总数量: {len(metrics_df)}")
    print(f"上涨: {len(metrics_df[metrics_df['daily_change_pct'] > 0])} 只")
    print(f"下跌: {len(metrics_df[metrics_df['daily_change_pct'] < 0])} 只")
    print(f"平均涨跌幅: {metrics_df['daily_change_pct'].mean():+.2f}%")
    print("\n涨幅前三:")
    for _, row in metrics_df.nlargest(3, 'daily_change_pct').iterrows():
        print(f"  {row['ticker']} {row['name']}: +{row['daily_change_pct']:.2f}%")
    print("\n跌幅前三:")
    for _, row in metrics_df.nsmallest(3, 'daily_change_pct').iterrows():
        print(f"  {row['ticker']} {row['name']}: {row['daily_change_pct']:.2f}%")
    print("="*60)


if __name__ == '__main__':
    main()
