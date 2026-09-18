"""Analytical Catmull-Clark masks, owned output arrays, and rejected topology."""
import sys,unittest,gc
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from Aru_RetopoTool.subdivision import plan

class Tests(unittest.TestCase):
    def test_boundary_quad_masks_and_numbering(self):
        steps,buffers=plan(4,[(0,1,2,3)],[(0,1),(1,2),(2,3),(0,3)],1)
        offsets,ids,weights=steps[0]
        rows=[dict(zip(ids[offsets[i]:offsets[i+1]],weights[offsets[i]:offsets[i+1]])) for i in range(9)]
        self.assertEqual(rows[0],{0:.75,1:.125,3:.125})
        self.assertEqual(rows[4],{0:.5,1:.5})
        self.assertEqual(rows[8],{0:.25,1:.25,2:.25,3:.25})
        self.assertEqual(list(buffers[0]),[0,4,8,5,1,6,8,4,2,7,8,6,3,5,8,7])
        self.assertEqual(len(buffers[1]),10)
        self.assertEqual(list(buffers[7]),[0])

    def test_owned_arrays_survive_later_builds(self):
        steps,buffers=plan(4,[(0,1,2,3)],[(0,1),(1,2),(2,3),(0,3)],3)
        before=([tuple(tuple(a) for a in row) for row in steps],[tuple(a) for a in buffers])
        for _ in range(4):plan(3,[(0,1,2)],[(0,1),(1,2),(0,2)],2)
        gc.collect()
        self.assertEqual(before,([tuple(tuple(a) for a in row) for row in steps],[tuple(a) for a in buffers]))

    def test_empty_and_invalid_topology(self):
        steps,buffers=plan(0,[],[],2)
        self.assertEqual(list(buffers[0]),[])
        self.assertEqual(list(buffers[1]),[0])
        for count,faces,guides,levels in (
            (3,[(0,1,4)],[],1),(3,[(0,1,-1)],[],1),
            (3,[(0,0,2)],[],1),(3,[(0,1,2)],[(0,4)],1),
            (3,[(0,1,2)],[],0),(3,[(0,1,2)],[],7),
        ):
            with self.assertRaises(ValueError):plan(count,faces,guides,levels)

if __name__=='__main__':unittest.main(verbosity=2)
