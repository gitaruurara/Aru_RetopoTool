"""Compare a two-column solver with SVD, including projected curve fits."""
import os,sys,json,time,statistics,traceback,inspect,copy
from unittest.mock import patch
from contextlib import nullcontext
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import numpy as np
from Aru_RetopoTool.editor.curvenet import curve_net_relax as relax,curve_net_edit as edit
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData

from Aru_RetopoTool.editor.curvenet import maya_projector as mp
status=1
try:
    rng=np.random.default_rng(2941);records=[]
    folder=Path(__file__).resolve().parents[1]/'bin'/cmds.about(version=True)
    new_lib=mp._load_library(folder/'aru_retopo_maya_projector_compact.dll')
    for kind,count,transformed in [('sphere',1,False),('sphere',15,False),('sphere',16,False),('sphere',500,False),('sphere',500,True),('cube',500,True)]:
        mesh=(cmds.polySphere(sx=64,sy=32,ch=False) if kind=='sphere' else cmds.polyCube(ch=False))[0]
        if transformed:
            cmds.setAttr(mesh+'.scale',-1.3,.8,1.7,type='double3')
            cmds.setAttr(mesh+'.rotate',13,23,-7,type='double3')
        fn,_=edit._get_mesh_fn(mesh)
        cn=RetopoGuideData();directions={}
        for i in range(count):
            a=rng.normal(size=3);a/=np.linalg.norm(a)
            b=a+rng.normal(size=3)*.15;b/=np.linalg.norm(b)
            start=len(cn.positions)
            for point in (a,a+(b-a)/3,b-(b-a)/3,b):cn.add_cv(point.tolist())
            cn.add_spline(start,start+1,start+2,start+3)
            directions[start+1]=(b-a)/max(np.linalg.norm(b-a),1e-12)
            directions[start+2]=-directions[start+1]
            if i%4==0:directions[start+2]=directions[start+1].copy()
            elif i%4==1:directions[start+1]=np.zeros(3);directions[start+2]=np.zeros(3)
            elif i%4==2:
                other=rng.normal(size=3);directions[start+2]=other/np.linalg.norm(other)

        results=[];times={}
        for name,lib in [('python',new_lib),('native',new_lib)]:
            mp.clear();mp._LIB=lib
            solver=relax._fit_junction_lengths
            current=copy.deepcopy(cn);durations=[]
            for i in range(8):
                start=time.perf_counter()
                with patch.object(mp,'junction_compact',return_value=None) if name=='python' else nullcontext():
                    solver(current,set(range(count)),directions,fn)
                durations.append((time.perf_counter()-start)*1000)
            results.append(np.asarray(current.positions));times[name]=statistics.median(durations[1:])
        fit_error=float(np.max(np.abs(results[0]-results[1])))
        assert fit_error<1e-7,fit_error
        records.append(dict(mesh=kind,count=count,transformed=transformed,max_error=fit_error,times=times))
        mp.clear();cmds.delete(mesh)
    mesh=cmds.polySphere(ch=False)[0];fn,_=edit._get_mesh_fn(mesh)
    mp.clear();mp._LIB=new_lib
    controls=np.asarray([[[0,1,0],[.1,1,0],[.2,1,0],[.3,1,0]]],dtype=float)
    ds=np.asarray([[[1,0,0],[-1,0,0]]],dtype=float);lengths=np.ones((1,2))*.1;chords=np.array([.3])
    args=[controls,ds,lengths,chords]
    saved=mp.junction_compact(fn,*args);owned=saved.copy()
    mp.junction_compact(fn,controls+.1,ds,lengths,chords);assert np.array_equal(saved,owned)
    assert mp.junction_compact(fn,controls,ds*2,lengths,chords) is None
    for index in range(4):
        bad=list(args);bad[index]=args[index].copy();bad[index].flat[0]=float('nan')
        try:mp.junction_compact(fn,*bad)
        except RuntimeError:pass
        else:raise AssertionError('Nonfinite compact input accepted')
        bad=list(args);bad[index]=np.empty(0)
        try:mp.junction_compact(fn,*bad)
        except (ValueError,RuntimeError):pass
        else:raise AssertionError('Invalid compact size accepted')
    assert mp.junction_compact(fn,np.empty((0,4,3)),np.empty((0,2,3)),np.empty((0,2)),np.empty(0)).shape==(0,2)
    from unittest.mock import patch
    with patch.object(edit,'_accel_for',return_value=None):
        try:mp.junction_compact(fn,*args)
        except RuntimeError as exc:assert 'reference mesh' in str(exc)
        else:raise AssertionError('Missing reference accepted')
    # Exercise the numerical SVD path using the same required native library.
    cmds.loadPlugin(str(folder.parents[1]/'editor/curvenet/aru_retopo_guide_plugin.py'),quiet=True);cmds.undoInfo(state=True)
    from Aru_RetopoTool.tests import surface_relax
    with patch.object(mp,'junction_compact',return_value=None) as observed:
        surface_relax.run();assert observed.call_count
    import ctypes as C
    mp.clear();mp._LIB=new_lib
    victim=cmds.polySphere(ch=False)[0];victim_fn,_=edit._get_mesh_fn(victim)
    owner=mp.Projector(victim_fn.fullPathName())
    try:
        ts=np.linspace(.05,.95,15);us=1-ts;c0=3*us*us*ts;c1=3*us*ts*ts
        coefficient=np.stack((c0,c1,us**3+c0,ts**3+c1),axis=1)
        buffers=[np.ascontiguousarray(x) for x in args+[coefficient]]
        ptr=C.POINTER(C.c_double);output=np.empty((1,2));raw=new_lib.aru_maya_junction_compact_v1
        call=[owner.handle]+[x.ctypes.data_as(ptr) for x in buffers]
        assert raw(*call,2147483647,output.ctypes.data_as(ptr))==0
        cmds.delete(victim)
        assert raw(*call,1,output.ctypes.data_as(ptr))==0
    finally:owner.close()
    print('PASS compact rejects oversized count and deleted reference owner',flush=True)
    print('PASS compact ownership, malformed input, normalized-direction guard, empty and SVD fallback',flush=True)
    (Path(__file__).parent/('junction_compact_release_'+cmds.about(version=True)+'.json')).write_text(json.dumps(records,indent=2))
    print(json.dumps(records),flush=True);status=0
except BaseException:traceback.print_exc()
finally:
    mp.clear();cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
