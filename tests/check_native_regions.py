import sys,ctypes,json,time,statistics,random,unittest,math
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parent))
from Aru_RetopoTool import native,core
from Aru_RetopoTool.tests import test_core,regions_candidate as candidate
lib=ctypes.CDLL(str(ROOT/'bin/regions_candidate/aru_retopo_core_v7.dll'))
with patch.object(native.C,'CDLL',return_value=lib):native.library()
old=core.regions;rng=random.Random(735)
cases=[]
for n in range(3,16):
 for trial in range(12):
  p,s=test_core.polygon(n)
  p=[tuple(x+rng.uniform(-.05,.05) for x in xyz) for xyz in p]
  cases.append((p,s,lambda p:(0,1,0)))
# Shared cells, dangling branches and multi-segment sides.
for w in (2,3,5,10):
 p=[(x,0,z) for z in range(w) for x in range(w)]
 edges=[(z*w+x,z*w+x+1) for z in range(w) for x in range(w-1)]+[(z*w+x,(z+1)*w+x) for z in range(w-1) for x in range(w)]
 p,s=test_core.network(p,edges);cases.append((p,s,lambda p:(0,1,0)))
net=json.loads((ROOT/'tests/gui_point_drag_final_numeric.json').read_text());cases.append((net['positions'],net['splines'],lambda p:p))
for i,(p,s,normal) in enumerate(cases):
 a=old(p,s,normal);b=candidate.regions(p,s,normal);assert a==b,('case',i,a[:1],b[:1])
print(len(cases),'exact region parity cases passed')
with patch.object(core,'regions',candidate.regions):
 result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(test_core));assert result.wasSuccessful()
p,s,normal=cases[-1];report={}
for name,fn in (('before',old),('after',candidate.regions)):
 times=[]
 for i in range(12):
  t=time.perf_counter();fn(p,s,normal);times.append((time.perf_counter()-t)*1000)
 report[name]={'median':statistics.median(times[1:]),'samples':times}
(ROOT/'tests/regions_comparison.json').write_text(json.dumps(report,indent=2));print({k:v['median'] for k,v in report.items()})
