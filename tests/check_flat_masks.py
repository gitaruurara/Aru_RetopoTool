import sys,ctypes,json,time,statistics,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
from Aru_RetopoTool import native,core
from Aru_RetopoTool.tests import test_core,test_stencil_compiler,test_subdivision
libs={}
for name,path in (('before','bin/aru_retopo_core_v7.dll'),('after','bin/flat_masks_candidate/aru_retopo_core_v7.dll')):
 lib=ctypes.CDLL(str(ROOT/path));native._lib=None
 with patch.object(native.C,'CDLL',return_value=lib):native.library()
 libs[name]=lib
net=json.loads((ROOT/'tests/gui_point_drag_final_numeric.json').read_text());p,s=net['positions'],net['splines']
report={'before':[],'after':[]};outputs={}
for i in range(7):
 for name,lib in libs.items():
  native._lib=lib;t=time.perf_counter();plan=core.Plan(p,s,lambda p:p,3);built=time.perf_counter();coeff=plan.compile_stencil(s);end=time.perf_counter()
  report[name].append({'plan_ms':(built-t)*1000,'total_ms':(end-t)*1000})
  outputs[name]=(plan.faces,plan.guide_vertices,plan.patches,[(tuple(o),tuple(v),tuple(w)) for o,v,w in plan.steps],coeff)
assert outputs['before']==outputs['after']
report['identical']=True;report['median']={name:{k:statistics.median(row[k] for row in report[name][1:]) for k in ('plan_ms','total_ms')} for name in libs}
(ROOT/'tests/flat_masks_comparison.json').write_text(json.dumps(report,indent=2));print(json.dumps(report['median'],indent=2))
native._lib=libs['after']
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(m) for m in (test_core,test_stencil_compiler,test_subdivision))
result=unittest.TextTestRunner(verbosity=1).run(suite);assert result.wasSuccessful()
