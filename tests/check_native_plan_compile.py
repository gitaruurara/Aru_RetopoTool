import sys,ctypes,unittest,random,time,statistics,json
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
from Aru_RetopoTool import native,core
lib=ctypes.CDLL(str(ROOT/'bin/plan_compile_candidate/aru_retopo_core_v6.dll'))
with patch.object(native.C,'CDLL',return_value=lib):native.library()
from Aru_RetopoTool.tests import test_core,core_compiled_candidate as candidate
cases=[(str(n),*test_core.polygon(n)) for n in (3,4,5,8)]
cases.append(('mixed',*test_core.network([(0,0,0),(0,0,1),(1,0,1),(1,0,0),(2,0,.5)],[(0,1),(1,2),(2,3),(3,0),(3,4),(4,2)])))
maximum=0
for name,p,s in cases:
 for level in (1,2,3,4):
  a=core.Plan(p,s,lambda _:(0,1,0),level);b=candidate.Plan(p,s,lambda _:(0,1,0),level)
  ao,ai,aw=a.compile_stencil(s);bo,bi,bw=b.compile_stencil(s)
  assert ao==bo and ai==bi,(name,level)
  error=max(abs(x-y) for x,y in zip(aw,bw));maximum=max(maximum,error)
  assert error<1e-12,(name,level,error)
print('20 parity cases passed; maximum coefficient error',maximum)
with patch.object(test_core,'Plan',candidate.Plan):
 result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(test_core))
 assert result.wasSuccessful()
net=json.loads((ROOT/'tests/gui_point_drag_final_numeric.json').read_text())
p,s=net['positions'],net['splines'];report={}
outputs={}
for name,cls in (('before',core.Plan),('after',candidate.Plan)):
 timings=[]
 for i in range(5):
  start=time.perf_counter();a=cls(p,s,lambda p:p,3);built=time.perf_counter();data=a.compile_stencil(s);end=time.perf_counter()
  if i:timings.append({'plan':(built-start)*1000,'compile':(end-built)*1000,'total':(end-start)*1000})
 outputs[name]=data
 report[name]={'regions':a.region_count,'faces':len(a.faces),'timings':timings,'median':{k:statistics.median(r[k] for r in timings) for k in timings[0]}}
a,b=outputs.values();assert a[0]==b[0] and a[1]==b[1]
report['max_coefficient_error']=max(abs(x-y) for x,y in zip(a[2],b[2]));assert report['max_coefficient_error']<1e-12
(ROOT/'tests/native_plan_compile_comparison.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v['median'] for k,v in report.items() if isinstance(v,dict)},indent=2))
