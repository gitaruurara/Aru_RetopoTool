import os,sys,ctypes as C,traceback,json
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
import numpy as np
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import native
D=C.POINTER(C.c_double);I=C.POINTER(C.c_int)
status=1
try:
    old=native.library();new=C.CDLL(str(Path(__file__).resolve().parents[1]/'bin/projection_trial/aru_retopo_core_v4.dll'))
    for name in ('aru_surface_create','aru_surface_destroy','aru_project','aru_relax'):
        getattr(new,name).argtypes=getattr(old,name).argtypes;getattr(new,name).restype=getattr(old,name).restype
    meshes=[cmds.polySphere(r=3,sx=32,sy=24,ch=False)[0],cmds.polyCube(ch=False)[0],cmds.polyTorus(ch=False)[0]]
    cases=0
    for mesh in meshes:
        sel=om.MSelectionList();sel.add(mesh);dag=sel.getDagPath(0);dag.extendToShape();fn=om.MFnMesh(dag)
        vertices=np.array([tuple(p)[:3] for p in fn.getPoints()],dtype=np.float64)
        ids=np.array(fn.getTriangles()[1],dtype=np.int32)
        # Duplicate and degenerate triangles exercise distance ties and fallback.
        ids=np.concatenate((ids,ids[:3],np.array([0,0,0],dtype=np.int32)))
        handles=[lib.aru_surface_create(vertices.ctypes.data_as(D),len(vertices),ids.ctypes.data_as(I),len(ids)//3) for lib in (old,new)]
        assert all(handles)
        n=1024;rng=np.random.default_rng(55);q=rng.normal(size=(n,3))*3
        seeds=[np.full(n,-1,dtype=np.int32) for _ in handles]
        offsets=np.arange(0,2*n+1,2,dtype=np.int32)
        neighbors=np.array([j for i in range(n) for j in ((i-1)%n,(i+1)%n)],dtype=np.int32)
        weights=np.zeros(n,dtype=np.float64);weights[::5]=1
        try:
            for iteration in range(6):
                results=[]
                for lib,handle,seed in zip((old,new),handles,seeds):
                    out=np.empty_like(q);normals=np.empty_like(q)
                    assert lib.aru_project(handle,q.ctypes.data_as(D),n,out.ctypes.data_as(D),seed.ctypes.data_as(I),normals.ctypes.data_as(D),iteration%2)
                    results.append((out.copy(),seed.copy(),normals.copy()))
                assert all(np.array_equal(a,b) for a,b in zip(*results)),('project',mesh,iteration)
                results=[]
                for lib,handle,seed in zip((old,new),handles,seeds):
                    out=q.copy()
                    assert lib.aru_relax(handle,out.ctypes.data_as(D),n,offsets.ctypes.data_as(I),neighbors.ctypes.data_as(I),weights.ctypes.data_as(D),3,.35,seed.ctypes.data_as(I),iteration%2)
                    results.append((out.copy(),seed.copy()))
                assert all(np.array_equal(a,b) for a,b in zip(*results)),('relax',mesh,iteration)
                q=q+rng.normal(size=q.shape)*.001;cases+=1
        finally:
            for lib,handle in zip((old,new),handles):lib.aru_surface_destroy(handle)
    print('BVH BOUNDS EXACT PROJECT/NORMAL/SEED/PARALLEL RELAX PARITY PASSED',cmds.about(version=True),'cases',cases)
    status=0
except BaseException:traceback.print_exc()
finally:
    cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
