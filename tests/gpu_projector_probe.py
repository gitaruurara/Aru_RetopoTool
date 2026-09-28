"""Standalone GPU/CPU BVH projection parity and transfer-inclusive timing."""
import ctypes as C,json,time,statistics,math
from pathlib import Path
root=Path(__file__).resolve().parents[1]
lib=C.CDLL(str(root/'bin/gpu-experimental/aru_retopo_gpu_projector.dll'))
d=C.POINTER(C.c_double);i=C.POINTER(C.c_int)
lib.aru_gpu_create.argtypes=[d,C.c_int,i,C.c_int,C.c_wchar_p];lib.aru_gpu_create.restype=C.c_void_p
lib.aru_gpu_destroy.argtypes=[C.c_void_p];lib.aru_gpu_destroy.restype=None
lib.aru_gpu_project.argtypes=[C.c_void_p,d,C.c_int,d,i,C.c_int];lib.aru_gpu_project.restype=C.c_int
lib.aru_gpu_error.restype=C.c_char_p
lib.aru_surface_create.argtypes=[d,C.c_int,i,C.c_int];lib.aru_surface_create.restype=C.c_void_p
lib.aru_surface_destroy.argtypes=[C.c_void_p];lib.aru_surface_destroy.restype=None
lib.aru_project.argtypes=[C.c_void_p,d,C.c_int,d,i,d,C.c_int];lib.aru_project.restype=C.c_int
lib.aru_stencil.argtypes=[d,i,i,d,C.c_int,d];lib.aru_stencil.restype=C.c_int
array=lambda kind,values:(kind*len(values))(*values)
data=json.loads((root/'tests/native_relax_input.json').read_text());a=data['arrays']
vertices=array(C.c_double,[v for p in data['reference_points'] for v in p]);triangles=array(C.c_int,data['reference_indices'])
count=len(a['stencilOffsets'])-1;queries=(C.c_double*(count*3))()
assert lib.aru_stencil(array(C.c_double,a['positions']),array(C.c_int,a['stencilOffsets']),array(C.c_int,a['stencilIndices']),array(C.c_double,a['stencilWeights']),count,queries)
cpu=lib.aru_surface_create(vertices,len(vertices)//3,triangles,len(triangles)//3)
gpu=None;report={'queries':count,'triangles':len(triangles)//3,'scope':'nearest-point projection only, GPU includes host upload and readback; CPU comparator is serial aru_project, not the parallel full Maya solver'}
try:
    gpu=lib.aru_gpu_create(vertices,len(vertices)//3,triangles,len(triangles)//3,str(root/'cpp/gpu_projector.hlsl'))
    if not gpu:raise RuntimeError(lib.aru_gpu_error().decode())
    cases=[]
    for n in (256,count):
        reference=(C.c_double*(n*3))();actual=(C.c_double*(n*3))()
        cs=(C.c_int*n)(*([-1]*n));gs=(C.c_int*n)(*([-1]*n))
        ct=[];gt=[]
        for repeat in range(5):
            start=time.perf_counter();assert lib.aru_project(cpu,queries,n,reference,cs,None,1);ct.append((time.perf_counter()-start)*1000)
            start=time.perf_counter();ok=lib.aru_gpu_project(gpu,queries,n,actual,gs,1);gt.append((time.perf_counter()-start)*1000)
            if not ok:raise RuntimeError(lib.aru_gpu_error().decode())
            error=max(abs(x-y) for x,y in zip(reference,actual));assert all(math.isfinite(v) for v in actual)
            assert error<1.e-10,(repeat,n,error)
        cases.append(dict(count=n,max_error=error,seed_mismatches=sum(x!=y for x,y in zip(cs,gs)),cpu_serial_ms=statistics.median(ct[1:]),gpu_transfer_inclusive_ms=statistics.median(gt[1:])))
    report['cases']=cases
    # Independently evolving positions/seeds exercise the normal guard across edits.
    n=count
    cq=array(C.c_double,list(queries));gq=array(C.c_double,list(queries))
    co=(C.c_double*(n*3))();go=(C.c_double*(n*3))()
    cs=(C.c_int*n)(*([-1]*n));gs=(C.c_int*n)(*([-1]*n))
    steps=[]
    for step in range(12):
        for j in range(n*3):
            delta=0.004*math.sin(step*0.7+(j%97)*0.13)
            cq[j]+=delta;gq[j]+=delta
        assert lib.aru_project(cpu,cq,n,co,cs,None,1)
        start=time.perf_counter()
        assert lib.aru_gpu_project(gpu,gq,n,go,gs,1),lib.aru_gpu_error()
        elapsed=(time.perf_counter()-start)*1000
        error=max(abs(x-y) for x,y in zip(co,go))
        assert all(math.isfinite(v) for v in go)
        assert error<1.e-10,(step,error)
        steps.append(dict(step=step,max_error=error,seed_mismatches=sum(x!=y for x,y in zip(cs,gs)),gpu_ms=elapsed))
        cq,gq=array(C.c_double,list(co)),array(C.c_double,list(go))
    report['continuous_projection']=steps
finally:
    if gpu:lib.aru_gpu_destroy(gpu)
    if cpu:lib.aru_surface_destroy(cpu)
    (root/'tests/gpu_projector_probe.json').write_text(json.dumps(report,indent=2))
print(report)
