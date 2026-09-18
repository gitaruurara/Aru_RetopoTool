"""Native sparse-state ownership, transactional failure and ordered arithmetic."""
import sys,unittest,random,ctypes as C
from pathlib import Path
from array import array
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from Aru_RetopoTool.stencil_compiler import Composer,view

class Tests(unittest.TestCase):
 def test_ordered_multistage_composition_and_owned_results(self):
  rng=random.Random(523)
  with Composer([3,1,7,0]) as compiler:
   points=[{i:1.} for i in (3,1,7,0)]
   for stage in range(5):
    offsets=array('i',[0]);ids=array('i');weights=array('d');expected=[]
    for i in range(19):
     row={}
     for _ in range(7):
      source=rng.randrange(len(points));factor=rng.uniform(-.7,.8)
      ids.append(source);weights.append(factor)
      for key,value in points[source].items():row[key]=row.get(key,0.)+value*factor
     expected.append(row);offsets.append(len(ids))
    compiler.step(offsets,ids,weights,list(range(19)))
    override={2:{5:.2,1:.8},11:{7:1.}}
    compiler.set(override)
    for i,row in override.items():expected[i]=row
    off,columns,values=compiler.packed()
    rows=[dict(zip(columns[off[i]:off[i+1]],values[off[i]:off[i+1]])) for i in range(19)]
    self.assertEqual(rows,[{k:v for k,v in p.items() if abs(v)>1e-16} for p in expected])
    points=expected
   retained=compiler.packed();snapshot=tuple(tuple(a) for a in retained)
   compiler.set({0:{99:1.}})
   self.assertEqual(tuple(tuple(a) for a in retained),snapshot)
  self.assertEqual(tuple(tuple(a) for a in retained),snapshot)

 def test_failure_preserves_state_and_copy_checks_capacity(self):
  with Composer([0,1]) as compiler:
   baseline=compiler.packed()
   for offsets,ids,weights,requests in (
    ([0,2],[0],[1.],[0]),([0,1],[2],[1.],[0]),
    ([0,1],[0],[float('nan')],[0]),([0,1,2],[0,1],[1.,1.],[0,0])):
    with self.assertRaises(RuntimeError):compiler.step(array('i',offsets),array('i',ids),array('d',weights),requests)
    self.assertEqual(compiler.packed(),baseline)
   for rows in ({2:{0:1.}},{0:{0:float('inf')}}):
    with self.assertRaises(RuntimeError):compiler.set(rows)
    self.assertEqual(compiler.packed(),baseline)
   result=compiler.lib.aru_stencil_compiler_pack(compiler.handle)
   try:
    off=(C.c_int*3)(-9,-9,-9);ids=(C.c_int*2)(-9,-9);weights=(C.c_double*2)(-9,-9)
    self.assertEqual(compiler.lib.aru_stencil_result_copy(result,off,2,ids,weights,2),0)
    self.assertEqual(list(off),[-9]*3)
    self.assertEqual(compiler.lib.aru_stencil_result_copy(result,off,3,ids,weights,1),0)
    self.assertEqual(list(ids),[-9]*2)
   finally:compiler.lib.aru_stencil_result_destroy(result)
  self.assertIsNone(compiler.handle)
  with self.assertRaises(RuntimeError):compiler.packed()

if __name__=='__main__':unittest.main(verbosity=2)
