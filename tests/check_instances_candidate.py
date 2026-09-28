import sys,ctypes,unittest,importlib.util,random
from unittest.mock import patch
from pathlib import Path
root=Path.cwd();sys.path.insert(0,str(root.parent))
from Aru_RetopoTool import native
lib=ctypes.CDLL(str(root/'bin/instances_candidate/aru_retopo_core_v6.dll'))
with patch.object(native.C,'CDLL',return_value=lib):native.library()
from Aru_RetopoTool.tests import test_core,test_stencil_compiler,test_subdivision
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(m) for m in (test_core,test_stencil_compiler,test_subdivision))
result=unittest.TextTestRunner(verbosity=1).run(suite);assert result.wasSuccessful()
from Aru_RetopoTool.core import Plan
spec=importlib.util.spec_from_file_location('ref',root/'tests/plan_full_reference.py');ref=importlib.util.module_from_spec(spec);spec.loader.exec_module(ref);ref.__package__='Aru_RetopoTool'
cases=[(str(n),*test_core.polygon(n)) for n in (3,4,5,8)]
cases.append(('mixed',*test_core.network([(0,0,0),(0,0,1),(1,0,1),(1,0,0),(2,0,.5)],[(0,1),(1,2),(2,3),(3,0),(3,4),(4,2)])))
for name,p,s in cases:
 for level in (1,2,3,4):
  a=ref.Plan(p,s,lambda _:(0,1,0),level);b=Plan(p,s,lambda _:(0,1,0),level)
  ao,ai,aw=a.compile_stencil(s);bo,bi,bw=b.compile_stencil(s)
  assert ao==bo and ai==bi
  assert max(abs(x-y) for x,y in zip(aw,bw))<1e-12
print('20 coefficient parity cases passed')
