import sys,ctypes,importlib.util,json,random,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
from Aru_RetopoTool import subdivision
lib=ctypes.CDLL(str(ROOT/'bin/subdivision_ready/aru_retopo_core_v5.dll'));subdivision.library=lambda:lib
from Aru_RetopoTool.core import Plan
from Aru_RetopoTool.tests import test_core
spec=importlib.util.spec_from_file_location('ref',ROOT/'tests/plan_full_reference.py');ref=importlib.util.module_from_spec(spec);spec.loader.exec_module(ref);ref.__package__='Aru_RetopoTool'
cases=[(str(n),*test_core.polygon(n)) for n in (3,4,5,8)]
cases.append(('mixed',*test_core.network([(0,0,0),(0,0,1),(1,0,1),(1,0,0),(2,0,.5)],[(0,1),(1,2),(2,3),(3,0),(3,4),(4,2)])))
rows=[]
for name,p,s in cases:
 for level in (1,2,3,4):
  a=ref.Plan(p,s,lambda _:(0,1,0),level);b=Plan(p,s,lambda _:(0,1,0),level)
  assert a.faces==b.faces and a.guide_vertices==b.guide_vertices and a.adj_ids==b.adj_ids and a.adj_offsets==b.adj_offsets
  rng=random.Random(34);moved=[tuple(x+rng.uniform(-.2,.2) for x in pt) for pt in p]
  error=max(abs(x-y) for u,v in zip(a.evaluate(moved,s),b.evaluate(moved,s)) for x,y in zip(u,v))
  ao,ai,aw=a.compile_stencil(s);bo,bi,bw=b.compile_stencil(s)
  assert ao==bo and ai==bi
  coeff=max(abs(x-y) for x,y in zip(aw,bw))
  assert max(error,coeff)<1e-12,(name,level,error,coeff)
  rows.append(dict(case=name,level=level,error=error,coefficient_error=coeff))
(ROOT/'tests/subdivision_plan_parity.json').write_text(json.dumps(rows,indent=2));print('20 native/reference cases passed')
result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(test_core))
assert result.wasSuccessful()
