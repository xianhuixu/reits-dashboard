#!/usr/bin/env python3
"""更新 REITs Dashboard 数据 - 从腾讯接口获取实时数据并更新 data.js/data.json"""
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
DATA_JS = ROOT / "data.js"
DATA_JSON = ROOT / "data.json"
UNIVERSE = ROOT / "universe.json"

# 腾讯股票接口（支持批量查询，每次最多60只）
TENCENT_API = "http://qt.gtimg.cn/q={}"

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
                
                # 成交额和最高最低位置可能有变化，尝试从后面找
                if len(parts) > 33:
                    amount = safe_float(parts[33])
                    if amount:
                        amount = amount * 10000  # 万->元
                if len(parts) > 34:
                    high = safe_float(parts[34])
                if len(parts) > 35:
                    low = safe_float(parts[35])
                
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
    
    # 找到对应的结束位置（最后一个分号前的JSON）
    # data.js 格式: window.REITS_DATA = {...};
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
        # 如果最后一天已经是今天，更新价格
        # 否则追加新一天
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
    
    print(f"[info] 已更新 {updated_count}/{len(reits)} 只 REITs")
    return data


def save_data(data):
    """保存 data.js 和 data.json"""
    # 保存 data.json
    DATA_JSON.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f"[info] 已保存 {DATA_JSON}")
    
    # 保存 data.js (带 window.REITS_DATA 前缀)
    js_content = "window.REITS_DATA = " + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ";\n"
    DATA_JS.write_text(js_content, encoding='utf-8')
    print(f"[info] 已保存 {DATA_JS}")


def main():
    print("=" * 50)
    print("REITs Dashboard 数据更新")
    print("=" * 50)
    
    # 1. 读取 universe.json 获取代码列表
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
    
    print("=" * 50)
    print("更新完成!")
    print("=" * 50)


if __name__ == '__main__':
    main()
