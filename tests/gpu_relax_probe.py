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
lib.aru_gpu_relax_setup.argtypes=[C.c_void_p,C.c_int,i,i,d];lib.aru_gpu_relax_setup.restype=C.c_int
lib.aru_gpu_relax.argtypes=[C.c_void_p,d,C.c_int,d,i,C.c_int,C.c_double,C.c_int];lib.aru_gpu_relax.restype=C.c_int
lib.aru_relax.argtypes=[C.c_void_p,d,C.c_int,i,i,d,C.c_int,C.c_double,i,C.c_int];lib.aru_relax.restype=C.c_int
cpu=lib.aru_surface_create(vertices,len(vertices)//3,triangles,len(triangles)//3)
gpu=lib.aru_gpu_create(vertices,len(vertices)//3,triangles,len(triangles)//3,str(root/'cpp/gpu_projector.hlsl'))
assert cpu and gpu,lib.aru_gpu_error()
offsets=array(C.c_int,a['adjacencyOffsets']);neighbors=array(C.c_int,a['adjacencyIndices']);weights=array(C.c_double,a['guideWeights'])
report={'scope':'CPU parallel relax vs GPU relax including transfers; cached topology; excludes Maya/display and stencils','count':count,'cpu_threads':16,'cpu_sleeping_team':True,'input':'interpolated recorded curve relax controls'}
try:
    assert lib.aru_gpu_relax_setup(gpu,count,offsets,neighbors,weights),lib.aru_gpu_error()
    cases=[]
    for iterations in (0,1,5):
        cs=(C.c_int*count)(*([-1]*count));gs=(C.c_int*count)(*([-1]*count))
        ct=[];gt=[];errors=[]
        for repeat in range(8):
            controls=[v+(data['relaxed_positions'][j]-v)*(repeat/7.0) for j,v in enumerate(a['positions'])]
            moved=(C.c_double*(count*3))()
            assert lib.aru_stencil(array(C.c_double,controls),array(C.c_int,a['stencilOffsets']),array(C.c_int,a['stencilIndices']),array(C.c_double,a['stencilWeights']),count,moved)
            cp=array(C.c_double,moved);gp=array(C.c_double,moved);output=(C.c_double*(count*3))()
            start=time.perf_counter();assert lib.aru_relax(cpu,cp,count,offsets,neighbors,weights,iterations,0.35,cs,1);ct.append((time.perf_counter()-start)*1000)
            start=time.perf_counter();assert lib.aru_gpu_relax(gpu,gp,count,output,gs,iterations,0.35,1),lib.aru_gpu_error();gt.append((time.perf_counter()-start)*1000)
            error=max(abs(x-y) for x,y in zip(cp,output));errors.append(error)
            assert all(math.isfinite(v) for v in output)
            assert error<1.e-10,(iterations,repeat,error)
        cases.append(dict(iterations=iterations,cpu_ms=statistics.median(ct[1:]),gpu_ms=statistics.median(gt[1:]),max_error=max(errors),cpu_samples=ct,gpu_samples=gt))
    report['cases']=cases
finally:
    lib.aru_gpu_destroy(gpu);lib.aru_surface_destroy(cpu)
    (root/'tests/gpu_relax_probe.json').write_text(json.dumps(report,indent=2))
print(report)
