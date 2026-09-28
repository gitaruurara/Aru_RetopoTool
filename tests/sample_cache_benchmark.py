"""Compare boundary memoization with the immediately preceding implementation."""
import json, statistics, sys, time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root.parent))
from Aru_RetopoTool.core import Plan
from Aru_RetopoTool.tests.test_core import network
old={}
exec((root/'tests/core_before_sample_cache.py.txt').read_text(encoding='utf-8'),old)
nx,ny=20,25
points=[(x,0,z) for z in range(ny+1) for x in range(nx+1)]
edges=[]
for z in range(ny+1):
    for x in range(nx+1):
        i=z*(nx+1)+x
        if x<nx:edges.append((i,i+1))
        if z<ny:edges.append((i,i+nx+1))
p,s=network(points,edges)
plans=[cls(p,s,lambda _:(0,1,0),3) for cls in (old['Plan'],Plan)]
timings=[[],[]]
expected=plans[0].compile_stencil(s)
for repeat in range(7):
    for index in ((0,1) if repeat%2==0 else (1,0)):
        start=time.perf_counter()
        actual=plans[index].compile_stencil(s)
        timings[index].append((time.perf_counter()-start)*1000)
        assert actual==expected
result=dict(patches=plans[1].region_count,exact=True,before_ms=statistics.median(timings[0]),after_ms=statistics.median(timings[1]),scope='synthetic grid stencil compilation only')
(root/'tests/sample_cache_benchmark.json').write_text(json.dumps(result,indent=2))
print(result)
