#!/usr/bin/env python3
"""Read-only, deterministic per-fund research export; no signal/valuation writes."""
import argparse
import hashlib
import json
import math
import sqlite3
from pathlib import Path

TABLES = "reit_info asset daily_quote distribution share_event ops_metric valuation forecast extension_offer issue_pricing financials reit_originator reit_fee reit_operator reit_project_company reit_originator_info reit_asset_ifind reit_offering_ifind appraisal_assumption revenue_breakdown ops_indicator_raw project_perf distcalc_item cost_breakdown project_fin project_bs fund_fee expansion_status holder_structure top_holders customer_conc concession_end".split()
DEFERRED = {"market_valuation": "缺少估值方法、单位和来源，不接入估值信号", "macro_series": "宏观模块独立", "price_risk": "行情风险模块独立", "price_move": "行情异动模块独立"}

def period_kind(period):
    s = str(period or '')[4:]
    return '单季报告期' if s in ('Q1','Q2','Q3','Q4') else '半年报告期' if s == 'H1' else '年度报告期' if s == 'A' else '未识别期间'

def scope(row, ownership, table):
    aid = row.get('asset_id')
    if aid == 'ALL': return '基金'
    if aid: return '项目' if ownership.get(aid) == row.get('code') else '归属待核'
    if table == 'financials' and row.get('level') == '基金层面': return '基金'
    return '归属待核'

def conflicts(financials, events):
    result=[]
    for r in financials:
        if r.get('scope') != '基金' or r.get('metric') not in ('actual_distribution','dps_actual') or r.get('value') != 0: continue
        # income_period is the only declared income attribution; payment year is never substituted.
        period=r['period']; year=period[:4]
        exact=[e for e in events if e.get('income_period') == period and ((e.get('dps_pretax') or 0)>0 or (e.get('total_amount') or 0)>0)]
        annual=[e for e in events if period.endswith('A') and str(e.get('income_period') or '').startswith(year) and ((e.get('dps_pretax') or 0)>0 or (e.get('total_amount') or 0)>0)]
        # Also flag potential date-basis disagreements, explicitly NOT a fiscal-period match.
        dated=[e for e in events if any(str(e.get(k) or '').startswith(year) for k in ('record_date','ex_date','pay_date')) and ((e.get('dps_pretax') or 0)>0 or (e.get('total_amount') or 0)>0)] if period.endswith('A') else []
        if exact or annual or dated:
            r['qualityFlags']=['财务分派字段为0，但存在非零分红事件；不可解读为零分红']
            result.append(dict(period=period,metric=r['metric'],caliber=r.get('caliber'),originalValue=0,basis='收益期间对应' if exact or annual else '仅日期同年，财年归属待核',eventCount=len(exact or annual or dated)))
    return result

def export(db, out):
    db=Path(db);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    schema={}
    all_data={}
    for item in c.execute("select name from sqlite_master where type='table' order by name").fetchall():
        t=item[0]
        rs=[{k:(None if isinstance(v,float) and not math.isfinite(v) else v) for k,v in dict(r).items()} for r in c.execute('select * from "'+t+'"')]
        fields=[r[1] for r in c.execute('pragma table_info("'+t+'")')]
        schema[t]=dict(rows=len(rs),fields={f:dict(nonNull=sum(r[f] is not None for r in rs),nonEmpty=sum(r[f] not in (None,'') for r in rs),zero=sum(r[f]==0 for r in rs)) for f in fields},exported=t in TABLES,reason=DEFERRED.get(t,''))
        if t in TABLES: all_data[t]=rs
    ownership={r['asset_id']:r['code'] for r in all_data['asset']}
    mismatches=0
    for t in ('ops_metric','financials','ops_indicator_raw','revenue_breakdown'):
        for r in all_data[t]:
            if 'scope' in r: r['original_scope']=r['scope']
            r['scope']=scope(r,ownership,t)
            if t=='ops_metric': mismatches += (r.get('level')=='基金层面') != (r['scope']=='基金')
    funds=[];total_flags=0
    for info in sorted(all_data['reit_info'],key=lambda r:r['code']):
        code=info['code']
        tables={t:sorted([r for r in rs if r.get('code')==code],key=lambda r:json.dumps(r,ensure_ascii=False,sort_keys=True)) for t,rs in all_data.items()}
        flags=conflicts(tables['financials'],tables['distribution']);total_flags+=len(flags)
        periods=sorted({r['period'] for t in ('financials','ops_metric') for r in tables[t] if r.get('period')})
        coverage={t:len(rs) for t,rs in tables.items()}
        payload=dict(schemaVersion=1,code=code,info=info,tables=tables,coverage=coverage,quality=dict(distributionConflicts=flags,unassignedFinancials=sum(r['scope']=='归属待核' for r in tables['financials']),sourceReportLinks=0,notes=['原始库无逐期公告URL及页码，无法提供逐期原文跳转；交易所链接仅为项目入口','未注明单位的源表仅展示原值，不与标准化金额相加','原值趋势不是同店或已核验可比序列；未计算同比、IRR、LTV及预测达成率']))
        write(out/(code+'.json'),payload)
        funds.append(dict(code=code,name=info['short_name'],periods=periods,coverage=coverage,distributionConflicts=len(flags)))
    audit=dict(schemaVersion=1,sourceSha256=hashlib.sha256(db.read_bytes()).hexdigest(),source='用户提供的爬取SQLite（只读）',feedsSignals=False,tables=schema,funds=funds,summary=dict(funds=len(funds),assets=len(all_data['asset']),ops=len(all_data['ops_metric']),financials=len(all_data['financials']),distributionEvents=len(all_data['distribution']),scopeLabelMismatches=mismatches,distributionConflictFields=total_flags),gaps=['leverage_ratio无可验证定义或公式，保留源单位且定义待核','收入/成本原表缺单位及分项不重叠依据，不生成构成图','源库无逐期报告URL/页码','forecast无单位字段，不与实际金额作数值对照','appraisal_assumption无日期/资产口径，单列假设不算达成率','部分financials项目公司记录无asset_id，不归入基金或任意项目','退出日期为空代表退出信息待核，不代表未退出'])
    write(out/'manifest.json',audit);c.close();return audit

def write(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'),sort_keys=True,allow_nan=False)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('database',type=Path);p.add_argument('--output',type=Path,default=Path('research/fund-archives'));a=p.parse_args();print(json.dumps(export(a.database,a.output)['summary'],ensure_ascii=False))
