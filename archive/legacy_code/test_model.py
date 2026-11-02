import unittest
from main import distance, optimize
class Distances(unittest.TestCase):
    def test_same_location(self):
        self.assertEqual(distance({'lat':69,'lon':88},{'lat':69,'lon':88}),0)
    def test_meridian_degree(self):
        self.assertAlmostEqual(distance({'lat':0,'lon':0},{'lat':1,'lon':0}),111194.9266,places=3)
    def test_symmetry(self):
        a={'lat':69.3,'lon':88.2};b={'lat':69.4,'lon':88.1}
        self.assertAlmostEqual(distance(a,b),distance(b,a))
class Optimizer(unittest.TestCase):
    def test_overlap_not_double_counted(self):
        routes={'a':{'cover':{1,2,3}},'b':{'cover':{1,2,3}},'c':{'cover':{4,5}}}
        self.assertEqual(optimize(routes,2),('a','c'))
    def test_invalid_budget(self):
        with self.assertRaises(ValueError): optimize({'a':{'cover':set()}},0)
if __name__=='__main__': unittest.main()

