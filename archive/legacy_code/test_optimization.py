import unittest,json
from pathlib import Path
from optimize_timetable import evaluate,load_patterns
from normalize_schedules import minutes
class ScheduleOptimization(unittest.TestCase):
    def test_wait_and_shift(self):
        p={'a':{'route':'1','departures':[]},'b':{'route':'2','departures':[(100,'b'),(120,'c')]}}
        req=[('a','b',(96,'a',{},'A1'))]
        before,_=evaluate(p,req,5);after,_=evaluate(p,req,5,'2',2)
        self.assertEqual(before['sum_wait'],24);self.assertEqual(after['sum_wait'],6)
    def test_source_cells(self):
        root=Path(__file__).resolve().parent
        books=json.loads((root/'data/schedules/extracted.json').read_text(encoding='utf-8'))
        cells={(b['file'],s['name'],c['cell']):c['value'] for b in books for s in b['sheets'] for row in s['rows'] for c in row}
        trips,patterns=load_patterns('weekday','АДЦ')
        for p in patterns.values():
            for kind in ('arrivals','departures'):
                for value,trip,src,cell in p[kind]:
                    original=minutes(cells[src['file'],src['sheet'],cell]);self.assertIsNotNone(original);self.assertAlmostEqual(value%1440,original,places=5)
    def test_reproducible_selected_candidate(self):
        import csv
        root=Path(__file__).resolve().parent
        d=json.loads((root/'output/optimization_summary.json').read_text(encoding='utf-8'))
        with (root/'output/optimization_candidates.csv').open(encoding='utf-8-sig') as f: rows=list(csv.DictReader(f))
        selected=(d['after']['missed'],d['after']['sum_wait'],abs(d['shift_min']))
        self.assertTrue(all(selected<=(int(r['missed']),float(r['sum_wait']),abs(int(r['shift_min']))) for r in rows))
if __name__=='__main__':unittest.main()
