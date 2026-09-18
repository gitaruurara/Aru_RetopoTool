"""Directed walks, orientation invalidation and owned native region results."""
import sys,unittest,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from Aru_RetopoTool.core import regions
from Aru_RetopoTool.tests.test_core import network,polygon

class Tests(unittest.TestCase):
    def test_shared_edge_direction_and_stable_order(self):
        points=[(0,0,0),(0,0,1),(1,0,1),(1,0,0),(2,0,0),(2,0,1)]
        p,s=network(points,[(0,1),(1,2),(2,3),(3,0),(3,4),(4,5),(5,2)])
        self.assertEqual(regions(p,s,lambda p:(0,1,0)),[
            [((0,1),),((1,1),),((2,1),),((3,1),)],
            [((2,-1),),((6,-1),),((5,-1),),((4,-1),)]])

    def test_normals_are_read_again_and_results_are_independent(self):
        p,s=polygon(4)
        forward=regions(p,s,lambda p:(0,1,0))
        saved=repr(forward)
        reverse=regions(p,s,lambda p:(0,-1,0))
        self.assertNotEqual(forward,reverse)
        self.assertEqual(repr(forward),saved)
        reverse[0].clear()
        self.assertEqual(regions(p,s,lambda p:(0,1,0)),forward)

    def test_rejects_invalid_geometry_and_empty_network(self):
        p,s=polygon(4)
        for points,curves,normal in (
            ([],[],lambda p:(0,1,0)),
            (p,[(0,1,2)],lambda p:(0,1,0)),
            (p,[(0,1,2,len(p))],lambda p:(0,1,0)),
            (p,[(0,1,2,0)],lambda p:(0,1,0)),
            (p,s,lambda p:(0,math.nan,0)),
            (p,s,lambda p:(0,1)),
            ([(math.inf,0,0)]+p[1:],s,lambda p:(0,1,0)),
        ):
            with self.assertRaises(ValueError):regions(points,curves,normal)
        self.assertTrue(regions(p,s,lambda p:(0,1,0)))

if __name__=='__main__':unittest.main(verbosity=2)
