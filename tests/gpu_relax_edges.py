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

# Sharp cube, disconnected second cube, and a degenerate triangle stress guards.
verts=[(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
faces=[0,2,1,0,3,2,4,5,6,4,6,7,0,1,5,0,5,4,1,2,6,1,6,5,2,3,7,2,7,6,3,0,4,3,4,7]
verts+= [(x+4,y,z) for x,y,z in verts]
faces += [v+8 for v in faces]
faces += [0,0,1]
vertices=array(C.c_double,[x for v in verts for x in v]);triangles=array(C.c_int,faces)
cpu=lib.aru_surface_create(vertices,len(verts),triangles,len(faces)//3)
gpu=lib.aru_gpu_create(vertices,len(verts),triangles,len(faces)//3,str(root/'cpp/gpu_projector.hlsl'))
assert cpu and gpu,lib.aru_gpu_error()
report={'scope':'sharp surfaces, disconnected components, degenerate triangle, cached repeated edits and settings changes','cases':[]}
try:
    for n in (128,2048,64):
        offsets=array(C.c_int,[2*j for j in range(n+1)])
        neighbors=array(C.c_int,[k for j in range(n) for k in ((j-1)%n,(j+1)%n)])
        weights=array(C.c_double,[1.0 if j%7==0 else 0.2 if j%3==0 else 0.0 for j in range(n)])
        assert lib.aru_gpu_relax_setup(gpu,n,offsets,neighbors,weights),lib.aru_gpu_error()
        cs=(C.c_int*n)(*([-1]*n));gs=(C.c_int*n)(*([-1]*n))
        for step,(iterations,strength,guard) in enumerate([(5,.35,1),(5,.35,1),(5,.8,1),(1,.8,1),(0,.35,1),(5,.35,0),(5,.35,1)]):
            values=[value for j in range(n) for value in (3*math.sin(j*.1)+2,1.2*math.cos(j*.07),1.2*math.sin(j*.17)+step*.002)]
            cp=array(C.c_double,values);gp=array(C.c_double,values);out=(C.c_double*(n*3))()
            assert lib.aru_relax(cpu,cp,n,offsets,neighbors,weights,iterations,strength,cs,guard)
            assert lib.aru_gpu_relax(gpu,gp,n,out,gs,iterations,strength,guard),lib.aru_gpu_error()
            error=max(abs(x-y) for x,y in zip(cp,out));assert error<1.e-10,(n,step,error)
            assert all(math.isfinite(x) for x in out)
            report['cases'].append(dict(count=n,step=step,error=error))
finally:
    lib.aru_gpu_destroy(gpu);lib.aru_surface_destroy(cpu)
    (root/'tests/gpu_relax_edges.json').write_text(json.dumps(report,indent=2))
print('PASS',len(report['cases']),'cases; max error',max(c['error'] for c in report['cases']))
