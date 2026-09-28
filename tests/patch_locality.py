"""Exact old/new Plan parity and dense construction timing."""
import json,math,time,statistics,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root.parent))
from Aru_RetopoTool.core import Plan,regions,patch_key
from Aru_RetopoTool.tests.test_core import network,polygon
old={};exec((root/'tests/core_before_patch_locality.py.txt').read_text(encoding='utf-8'),old)
def grid(nx,ny):
    pts=[(x,0,z) for z in range(ny+1) for x in range(nx+1)]
    edges=[]
    for z in range(ny+1):
        for x in range(nx+1):
            i=z*(nx+1)+x
            if x<nx:edges.append((i,i+1))
            if z<ny:edges.append((i,i+nx+1))
    return network(pts,edges)
cases=[]
for n in (3,4,5,6):
    p,s=polygon(n)
    for level in (1,2,3,4):cases.append((p,s,level,None))
for nx,ny in ((2,3),(10,10),(20,25)):
    p,s=grid(nx,ny);keys=[patch_key(r) for r in regions(p,s,lambda _:(0,1,0))]
    for selection in (None,set(keys[::2])):cases.append((p,s,3,selection))
p,s=network([(0,0,0),(1,0,0),(1,0,1),(0,0,1),(-1,0,1),(-1.5,0,.5),(-1,0,0)],[(0,1),(1,2),(2,3),(3,0),(3,4),(4,5),(5,6),(6,0)])
for level in (1,2,3,4):cases.append((p,s,level,None))
results=[]
for p,s,level,selected in cases:
    timings=[];plans=[]
    for cls in (old['Plan'],Plan):
        start=time.perf_counter();plan=cls(p,s,lambda _:(0,1,0),level,selected=selected);timings.append((time.perf_counter()-start)*1000);plans.append(plan)
    assert plans[0].__dict__==plans[1].__dict__
    compiled=[];compile_ms=[]
    for plan in plans:
        start=time.perf_counter();compiled.append(plan.compile_stencil(s));compile_ms.append((time.perf_counter()-start)*1000)
    assert compiled[0]==compiled[1]
    results.append(dict(regions=plans[1].region_count,level=level,old_ms=timings[0],new_ms=timings[1],old_compile_ms=compile_ms[0],new_compile_ms=compile_ms[1]))
(root/'tests/patch_locality.json').write_text(json.dumps(results,indent=2))
print('PASS exact Plan metadata and compiled stencils:',len(results),'cases')
print(results[-2:])
