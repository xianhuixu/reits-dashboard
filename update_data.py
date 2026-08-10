#!/usr/bin/env python3
"""更新 REITs Dashboard 数据 - 从腾讯接口获取实时数据并更新 data.js/data.json"""
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
DATA_JS = ROOT / "data.js"
DATA_JSON = ROOT / "data.json"
UNIVERSE = ROOT / "universe.json"
HOLIDAYS = ROOT / "holidays.txt"
CYCLE_JSON = ROOT / "cycle_judgment.json"

# 腾讯股票接口（支持批量查询，每次最多60只）
TENCENT_API = "http://qt.gtimg.cn/q={}"


def is_trading_day():
    """判断今天是否为交易日（非周末、非节假日）"""
    today = date.today()
    
    # 周末不是交易日
    if today.weekday() >= 5:  # 5=周六, 6=周日
        return False
    
    # 读取节假日配置
    if HOLIDAYS.exists():
        today_str = today.isoformat()
        content = HOLIDAYS.read_text(encoding='utf-8')
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith(today_str):
                return False
    
    return True


def fetch_tencent(codes):
    """从腾讯接口获取股票实时数据"""
    # 转换代码格式: 508056.SH -> sh508056, 180301.SZ -> sz180301
    tencent_codes = []
    for c in codes:
        if c.endswith('.SH'):
            tencent_codes.append('sh' + c.replace('.SH', ''))
        elif c.endswith('.SZ'):
            tencent_codes.append('sz' + c.replace('.SZ', ''))
    
    results = {}
    batch_size = 60
    for i in range(0, len(tencent_codes), batch_size):
        batch = tencent_codes[i:i+batch_size]
        url = TENCENT_API.format(','.join(batch))
        try:
            resp = requests.get(url, timeout=30)
            resp.encoding = 'gbk'
            text = resp.text
            
            # 解析返回数据
            for line in text.strip().split(';'):
                line = line.strip()
                if not line or not line.startswith('v_'):
                    continue
                # 提取代码和数据
                match = re.match(r'v_(sh|sz)(\d+)="(.+)";?', line)
                if not match:
                    continue
                market, code_num, data_str = match.groups()
                origin_code = f"{code_num}.{'SH' if market == 'sh' else 'SZ'}"
                
                # 解析字段（腾讯接口字段顺序）- 使用安全解析
                parts = data_str.split('~')
                
                # 基础字段（位置相对固定）
                name = parts[1] if len(parts) > 1 else ''
                price = None
                prev_close = None
                open_price = None
                volume = 0
                amount = 0
                high = None
                low = None
                
                # 尝试安全解析数字字段
                def safe_float(s):
                    try:
                        # 处理复合字段如 "2.251/25690/5785391"
                        s = str(s).split('/')[0]
                        return float(s) if s else None
                    except:
                        return None
                
                def safe_int(s):
                    try:
                        s = str(s).split('/')[0]
                        return int(s) if s else 0
                    except:
                        return 0
                
                if len(parts) > 3:
                    price = safe_float(parts[3])
                if len(parts) > 4:
                    prev_close = safe_float(parts[4])
                if len(parts) > 5:
                    open_price = safe_float(parts[5])
                if len(parts) > 6:
                    volume = safe_int(parts[6]) * 100  # 手->股
                
                # 成交额解析（腾讯接口字段位置修正）
                # parts[35] 格式: 当前价/成交量(手)/成交额(元) 的复合字段
                # parts[37] 是成交额(万元, 取整)
                # parts[57] 是成交额(万元, 精确)
                amount = 0
                if len(parts) > 35:
                    # 优先从复合字段解析: "2.271/21561/4882298"
                    composite = str(parts[35])
                    if '/' in composite:
                        sub = composite.split('/')
                        if len(sub) >= 3:
                            amount = safe_float(sub[2])  # 元
                if not amount and len(parts) > 37:
                    amount = safe_float(parts[37])
                    if amount:
                        amount = amount * 10000  # 万->元
                if not amount and len(parts) > 57:
                    amount = safe_float(parts[57])
                    if amount:
                        amount = amount * 10000  # 万->元
                if len(parts) > 33:
                    high = safe_float(parts[33])
                if len(parts) > 34:
                    low = safe_float(parts[34])
                
                results[origin_code] = {
                    'name': name,
                    'price': price,
                    'prev_close': prev_close,
                    'open': open_price,
                    'volume': volume,
                    'amount': amount,
                    'high': high,
                    'low': low,
                }
        except Exception as e:
            print(f"[warn] 批次 {i}-{i+batch_size} 获取失败: {e}")
    
    return results


def parse_data_js():
    """解析 data.js 中的数据"""
    content = DATA_JS.read_text(encoding='utf-8')
    start = content.find('window.REITS_DATA = ')
    if start < 0:
        raise ValueError("无法在 data.js 中找到 window.REITS_DATA")
    start += len('window.REITS_DATA = ')
    
    # 找到对应的结束位置
    brace_count = 0
    in_string = False
    escape = False
    json_start = start
    
    for i, ch in enumerate(content[start:], start):
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if not in_string:
            if ch == '{':
                brace_count += 1
            elif ch == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_str = content[json_start:i+1]
                    return json.loads(json_str)
    
    raise ValueError("无法解析 data.js 中的 JSON")


def update_reits_data(data, tencent_data):
    """更新 REITs 数据"""
    today_str = date.today().isoformat()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    reits = data.get('reits', [])
    updated_count = 0
    
    for r in reits:
        code = r['code']
        if code not in tencent_data:
            continue
        
        td = tencent_data[code]
        if td['price'] is None:
            continue
        
        # 获取历史数据
        hist_dates = r.get('histDates', [])
        hist_close = r.get('histClose', [])
        
        if not hist_dates:
            continue
        
        last_date = hist_dates[-1]
        
        # 判断是否需要更新
        if last_date == today_str:
            # 更新今天的收盘价
            hist_close[-1] = round(td['price'], 3)
        else:
            # 追加新的一天
            hist_dates.append(today_str)
            hist_close.append(round(td['price'], 3))
        
        # 更新当前价格和涨跌幅
        prev_close = td['prev_close']
        if prev_close and prev_close > 0:
            r['close'] = round(td['price'], 3)
            r['pct'] = round((td['price'] / prev_close - 1) * 100, 2)
        
        # 更新成交量和成交额
        if td['volume'] > 0:
            r['volume'] = td['volume']
            r['amount'] = round(td['amount'], 0)
        
        # 更新 spark（最近60天）
        spark_len = 60
        r['spark'] = [round(float(x), 3) for x in hist_close[-spark_len:]]
        
        updated_count += 1
    
    # 更新时间戳
    data['updated'] = now_str
    data['lastTradeDate'] = today_str
    
    # 更新周期判断数据
    if CYCLE_JSON.exists():
        try:
            cycle_data = json.loads(CYCLE_JSON.read_text(encoding='utf-8'))
            data['cycle'] = cycle_data
            print(f"[info] 已更新周期判断数据 (bond10y={cycle_data.get('bond10y')}, updated={cycle_data.get('updated')})")
        except Exception as e:
            print(f"[warn] 周期判断数据更新失败: {e}")
    
    print(f"[info] 已更新 {updated_count}/{len(reits)} 只 REITs")
    return data


def save_data(data):
    """保存 data.js 和 data.json"""
    # 保存 data.json
    DATA_JSON.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f"[info] 已保存 {DATA_JSON}")
    
    # 保存 data.js
    js_content = "window.REITS_DATA = " + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ";\n"
    DATA_JS.write_text(js_content, encoding='utf-8')
    print(f"[info] 已保存 {DATA_JS}")


def git_commit_push():
    """自动提交到 GitHub"""
    today_str = date.today().isoformat()
    try:
        # 检查是否有变更
        result = subprocess.run(
            ['git', 'diff', '--quiet'],
            cwd=ROOT,
            capture_output=True
        )
        if result.returncode == 0:
            print("[info] 无变更，跳过提交")
            return True
        
        # 添加、提交、推送
        subprocess.run(['git', 'add', 'data.js', 'data.json'], cwd=ROOT, check=True)
        subprocess.run(
            ['git', 'commit', '-m', f'数据更新: {today_str} - 自动更新REITs数据'],
            cwd=ROOT, check=True
        )
        subprocess.run(['git', 'push', 'origin', 'main'], cwd=ROOT, check=True)
        print(f"[info] 已推送到 GitHub")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[error] Git 操作失败: {e}")
        return False


def main():
    # 检查是否为交易日
    if not is_trading_day():
        print("[info] 今天不是交易日，跳过更新")
        sys.exit(0)
    
    print("=" * 50)
    print(f"REITs Dashboard 数据更新 - {date.today()}")
    print("=" * 50)
    
    # 1. 读取 universe.json
    universe = json.loads(UNIVERSE.read_text(encoding='utf-8'))
    codes = [u['code'] for u in universe]
    print(f"[info] 共 {len(codes)} 只 REITs")
    
    # 2. 从腾讯接口获取实时数据
    print("[info] 正在从腾讯接口获取实时数据...")
    tencent_data = fetch_tencent(codes)
    print(f"[info] 成功获取 {len(tencent_data)} 只 REITs 数据")
    
    # 3. 解析现有 data.js
    print("[info] 正在解析现有数据...")
    data = parse_data_js()
    print(f"[info] 当前数据最后更新: {data.get('updated', 'N/A')}")
    print(f"[info] 当前最后交易日: {data.get('lastTradeDate', 'N/A')}")
    
    # 4. 更新数据
    print("[info] 正在更新数据...")
    data = update_reits_data(data, tencent_data)
    
    # 5. 保存
    save_data(data)
    
    # 6. 自动提交到 GitHub
    print("[info] 正在推送到 GitHub...")
    git_commit_push()
    
    print("=" * 50)
    print("更新完成!")
    print("=" * 50)


if __name__ == '__main__':
    main()
