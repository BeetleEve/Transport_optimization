import unittest
from transit import shortest, edge
class JourneyTests(unittest.TestCase):
    def test_direction_and_transfer_cost(self):
        g={};edge(g,'a','r1',5,'board');edge(g,'r1','b',2,'ride');edge(g,'b','r2',5,'board');edge(g,'r2','c',3,'ride')
        d,p=shortest(g,'a');self.assertEqual(d['c'],15);self.assertNotIn('a',shortest(g,'c')[0])
    def test_walking_can_beat_bus(self):
        g={};edge(g,'a','b',4,'walk');edge(g,'a','r',8,'board');edge(g,'r','b',1,'ride')
        d,p=shortest(g,'a');self.assertEqual(d['b'],4);self.assertEqual(p['b'][1],'walk')
    def test_added_route_cannot_worsen(self):
        g={};edge(g,'a','b',20,'walk');before=shortest(g,'a')[0]['b'];edge(g,'a','b',10,'ride');self.assertLessEqual(shortest(g,'a')[0]['b'],before)
if __name__=='__main__': unittest.main()
