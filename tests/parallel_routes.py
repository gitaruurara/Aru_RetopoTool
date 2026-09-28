"""Exact v4/v7 route parity and isolated timing; does not measure viewport FPS."""
import os, sys, traceback, ctypes as C, time, statistics, json
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import numpy as np
from Aru_RetopoTool.editor.curvenet import maya_projector as mp, curve_net_edit as edit
status=1
try:
    configured=mp.library()
    serial=C.CDLL(str(Path(configured._name).with_name("aru_retopo_maya_projector_v4.dll")))
    for name in ("aru_maya_projector_create","aru_maya_projector_destroy","aru_maya_fit_routes","aru_maya_projector_points"):
        getattr(serial,name).argtypes=getattr(configured,name).argtypes
        getattr(serial,name).restype=getattr(configured,name).restype
    parallel=C.CDLL(str(Path(serial._name).with_name('aru_retopo_maya_projector_v7.dll')))
    for name in ('aru_maya_projector_create','aru_maya_projector_destroy','aru_maya_fit_routes','aru_maya_projector_points'):
        getattr(parallel,name).argtypes=getattr(serial,name).argtypes
        getattr(parallel,name).restype=getattr(serial,name).restype
    mesh=cmds.polySphere(sx=64,sy=32,ch=False)[0]
    rng=np.random.default_rng(381)
    controls=rng.normal(size=(256,4,3));controls/=np.linalg.norm(controls,axis=2,keepdims=True)
    controls[0,3]=controls[0,0] # Degenerate route must preserve handles.
    records=[]
    for transformed in (False,True):
        if transformed:
            cmds.setAttr(mesh+'.translate',1.2,-.3,.7,type='double3')
            cmds.setAttr(mesh+'.scale',-1.3,.7,1.8,type='double3')
        fn,_=edit._get_mesh_fn(mesh)
        outputs=[]
        for lib in (serial,parallel):
            mp.clear();mp._LIB=lib
            modes=[]
            projector=mp.Projector(fn.fullPathName())
            try:
                for count in (0,1,511,512,5000):
                    queries=np.resize(controls[:,0,:],(count,3))
                    modes.append(projector.points(queries,as_array=True))
                bad=np.zeros((512,3));bad[-1,0]=float('nan')
                try:projector.points(bad)
                except RuntimeError:pass
                else:raise AssertionError('Non-finite projection was accepted')
            finally:projector.close()
            for draft in (True,False):
                for count in (1,15,16,256):
                    data=controls[:count].tolist()
                    result=mp.fit_routes(fn,data,draft)
                    durations=[]
                    for repeat in range(9):
                        t=time.perf_counter(); actual=mp.fit_routes(fn,data,draft)
                        durations.append((time.perf_counter()-t)*1000)
                        assert np.array_equal(actual,result)
                    modes.append(result)
                    records.append(dict(version=Path(lib._name).stem,transformed=transformed,draft=draft,count=count,median_ms=statistics.median(durations)))
            outputs.append(modes)
        for old,new in zip(*outputs):assert np.array_equal(old,new),'Parallel route changed result'
    report=dict(maya=cmds.about(version=True),exact_parity=True,records=records)
    Path(__file__).with_name('parallel_routes_'+cmds.about(version=True)+'.json').write_text(json.dumps(report,indent=2))
    print('PARALLEL ROUTES EXACT PARITY PASSED',cmds.about(version=True))
    for row in records:
        if row['count']==256:print(row)
    status=0
except BaseException:traceback.print_exc()
finally:
    mp.clear();edit._invalidate_mesh_accel();cmds.file(new=True,force=True)
    maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
