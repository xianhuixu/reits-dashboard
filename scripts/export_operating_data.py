#!/usr/bin/env python3
"""One-off, read-only export. No valuation, forecast, raw yoy or signal mutations."""
import argparse, sqlite3, json, hashlib, math
from pathlib import Path
from datetime import datetime

def export(db):
    c=sqlite3.connect(db.resolve().as_uri()+'?mode=ro', uri=True)
    c.row_factory=sqlite3.Row
    def rows(q):
        return [{k:(v if not isinstance(v,float) or math.isfinite(v) else None) for k,v in dict(r).items()} for r in c.execute(q)]
    funds=rows('select code,short_name,sector_l1,sector_l2,status,list_date from reit_info order by code')
    assets=rows('select code,asset_id,asset_name,include_type,include_date,exit_date from asset')
    ownership={a['asset_id']:a['code'] for a in assets}
    points=[]; rejected=0; corrected=0
    for r in rows('select * from ops_metric'):
        scope='基金' if r['asset_id']=='ALL' else '项目'
        if scope=='项目' and ownership.get(r['asset_id'])!=r['code']:
            rejected+=1; continue
        expected='基金层面' if scope=='基金' else '项目'
        corrected+=(r['level']=='基金层面')!=(scope=='基金')
        r.update(scope=scope,sourceTable='ops_metric')
        points.append(r)
    allowed="'revenue','ebitda','distributable_cash'"
    for r in rows(f"select * from financials where metric in ({allowed}) and level='基金层面' and (asset_id='' or asset_id='ALL' or asset_id is null)"):
        r.update(scope='基金',sourceTable='financials',originalAssetId=r['asset_id'],asset_id='ALL'); points.append(r)
    periods=sorted({r['period'] for r in points},key=lambda s:(int(s[:4]),{'Q1':1,'Q2':2,'H1':2.5,'Q3':3,'Q4':4,'A':4.5}.get(s[4:],0)),reverse=True)
    for r in points:
        r['tax_flag']=r.get('tax_flag') or '未说明'
    return dict(schemaVersion=1,importedAt=datetime.now().astimezone().isoformat(timespec='seconds'),timezone='Asia/Shanghai',source=dict(label='用户提供的爬取数据库',sha256=hashlib.sha256(db.read_bytes()).hexdigest(),review='待原公告复核',feedsSignals=False),latestPeriod=periods[0],periods=periods,funds=funds,assets=assets,points=points,quality=dict(rejectedOrphanPoints=rejected,scopeLabelMismatches=corrected,sameStoreVerified=False,notes=['基金/项目归属按asset_id核验，保留原始level','同比未完成资产范围、期间完整性与税口径复核，不自动计算','行情、估值、IRR、预测和原始同比字段均未接入']))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('database',type=Path);p.add_argument('--output',type=Path,default=Path('research/operating-data.json'));args=p.parse_args()
    d=export(args.database);args.output.write_text(json.dumps(d,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n');print('funds',len(d['funds']),'points',len(d['points']),'period',d['latestPeriod'],'bytes',args.output.stat().st_size,'quality',d['quality'])
