import hashlib
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fund_export', ROOT/'scripts/export_fund_archives.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ArchiveExportTest(unittest.TestCase):
    def test_period_and_dividend_conflicts(self):
        self.assertNotEqual(m.period_kind('2026Q2'), m.period_kind('2026H1'))
        rows=[dict(scope='基金',period='2025A',metric='dps_actual',value=0,caliber='本期')]
        flags=m.conflicts(rows,[dict(income_period='2025Q3',dps_pretax=.2,pay_date='2026-01-03')])
        self.assertEqual(flags[0]['originalValue'],0)
        self.assertEqual(flags[0]['basis'],'收益期间对应')
        self.assertEqual(rows[0]['value'],0)
        self.assertTrue(rows[0]['qualityFlags'])
        potential=m.conflicts([dict(scope='基金',period='2025A',metric='dps_actual',value=0)], [dict(income_period='2024',dps_pretax=.2,pay_date='2025-01-03')])
        self.assertIn('财年归属待核',potential[0]['basis'])

    def test_readonly_repeatable_export_and_scope(self):
        manifest=json.loads((ROOT/'research/fund-archives/manifest.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); db=p/'source.db'; c=sqlite3.connect(db)
            for t in m.TABLES:
                fields=list(manifest['tables'][t]['fields'])
                c.execute('CREATE TABLE "'+t+'" ('+','.join('"'+f+'"' for f in fields)+')')
            def insert(t,r):
                c.execute('insert into "'+t+'" ('+','.join('"'+k+'"' for k in r)+') values ('+','.join('?' for _ in r)+')',list(r.values()))
            insert('reit_info',dict(code='508008.SH',short_name='测试'))
            insert('asset',dict(code='508008.SH',asset_id='508008.SH-A01',asset_name='测试项目'))
            insert('ops_metric',dict(code='508008.SH',asset_id='508008.SH-A01',period='2026Q3',metric='traffic_total',value=0,unit='车次',level='基金层面'))
            insert('ops_metric',dict(code='508008.SH',asset_id='WRONG',period='2026Q3',metric='traffic_volume',value=999))
            insert('financials',dict(code='508008.SH',asset_id='',period='2026Q3',metric='revenue',value=None,level='项目公司层面'))
            insert('financials',dict(code='508008.SH',asset_id='',period='2025A',metric='actual_distribution',value=0,level='基金层面'))
            insert('distribution',dict(code='508008.SH',income_period='2025Q3',dps_pretax=.2,total_amount=100,pay_date='2026-01-03'))
            c.commit(); c.close(); before=hashlib.sha256(db.read_bytes()).hexdigest()
            audit=m.export(db,p/'one');m.export(db,p/'two')
            self.assertEqual(before,hashlib.sha256(db.read_bytes()).hexdigest())
            self.assertEqual((p/'one/508008.SH.json').read_bytes(),(p/'two/508008.SH.json').read_bytes())
            self.assertEqual((p/'one/manifest.json').read_bytes(),(p/'two/manifest.json').read_bytes())
            d=json.loads((p/'one/508008.SH.json').read_text());ops=d['tables']['ops_metric']
            self.assertEqual(next(r for r in ops if r['value']==0)['scope'],'项目')
            self.assertEqual(next(r for r in ops if r['value']==999)['scope'],'归属待核')
            self.assertEqual(d['quality']['unassignedFinancials'],1)
            self.assertEqual(audit['summary']['scopeLabelMismatches'],1)
            self.assertEqual(len(d['quality']['distributionConflicts']),1)

if __name__=='__main__': unittest.main()
