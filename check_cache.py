import json, glob, os, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
universe = json.load(open(os.path.join(ROOT, 'universe.json')))
codes = [u['code'] for u in universe]
print(f'universe: {len(codes)} 只')
fetched = set()
for f in glob.glob(os.path.join(ROOT, 'hist_cache/*.csv')):
    c = os.path.basename(f).replace('.csv','').replace('_SH','.SH').replace('_SZ','.SZ').replace('_N','.N').replace('_O','.O')
    fetched.add(c)
print(f'缓存文件: {len(fetched)} 个')
missing = [c for c in codes if c not in fetched]
print(f'缺失缓存: {len(missing)} 只')
for c in missing:
    print(f'  {c}')
print('完成')
