import json, os
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

# 校验 news.json
with open('news.json') as f:
    news = json.load(f)
items = news.get('items', [])
print(f'[news.json] items: {len(items)}')
if items:
    dates = [i['date'] for i in items]
    print(f'[news.json] date range: {min(dates)} to {max(dates)}')

# 校验 corp_actions.json
with open('corp_actions.json') as f:
    ca = json.load(f)
items2 = ca.get('items', [])
print(f'[corp_actions.json] items: {len(items2)}')
if items2:
    dates2 = [i['date'] for i in items2]
    print(f'[corp_actions.json] date range: {min(dates2)} to {max(dates2)}')

print('校验完成')
