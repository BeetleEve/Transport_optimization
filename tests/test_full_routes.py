import unittest
from app.full_routes import orient
class FullRoutes(unittest.TestCase):
    def test_loop_preserved(self):
        n={i:{'lat':69+i*.001,'lon':88} for i in [1,2,3]}
        parts,gaps=orient([([1,2,3,2,1],'forward')],n)
        self.assertEqual(parts,[[1,2,3,2,1]]);self.assertFalse(gaps)
    def test_gap_not_connected(self):
        n={i:{'lat':69+i*.001,'lon':88} for i in [1,2,3,4]}
        parts,gaps=orient([([1,2],'forward'),([3,4],'forward')],n)
        self.assertEqual(len(parts),2);self.assertEqual(len(gaps),1)
    def test_connected_orientation(self):
        n={i:{'lat':69+i*.001,'lon':88} for i in [1,2,3]}
        parts,gaps=orient([([1,2],'forward'),([3,2],'')],n)
        self.assertEqual(parts,[[1,2,3]]);self.assertFalse(gaps)
if __name__=='__main__':unittest.main()
