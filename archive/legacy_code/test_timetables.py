import unittest
from normalize_schedules import minutes
from timetable_router import route
class Timetables(unittest.TestCase):
    def test_fractional_seconds(self):self.assertAlmostEqual(minutes('1899-12-31T08:10:30.500000'),490+30.5/60)
    def test_missed_departure(self):
        g={'a':[(480,490,'b','1','t',{})]};self.assertIsNone(route(g,'a','b',481))
    def test_transfer_buffer(self):
        g={'a':[(480,490,'b','1','t',{})],'b':[(491,500,'c','2','u',{}),(493,505,'c','2','v',{})]}
        self.assertEqual(route(g,'a','c',480)[-1]['arrival'],505)
if __name__=='__main__':unittest.main()
