"""Compare a two-column solver with SVD, including projected curve fits."""
import os,sys,json,time,statistics,traceback,inspect,copy
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
    from Aru_RetopoTool.tests import junction_compact_candidate
    rng=np.random.default_rng(2941);records=[]
    folder=Path(__file__).resolve().parents[1]/'bin'/cmds.about(version=True)
    old_lib=mp._load_library(folder/'aru_retopo_maya_projector_endpoints.dll')
    new_lib=mp._load_library(folder/'aru_retopo_maya_junction_compact.dll')
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
        results=[];times={}
        for name,lib in [('python',old_lib),('native',new_lib)]:
            mp.clear();mp._LIB=lib
            restore=junction_compact_candidate.install() if name=="native" else None
            solver=relax._fit_junction_lengths
            current=copy.deepcopy(cn);durations=[]
            for i in range(8):
                start=time.perf_counter();solver(current,set(range(count)),directions,fn);durations.append((time.perf_counter()-start)*1000)
            results.append(np.asarray(current.positions));times[name]=statistics.median(durations[1:])
            if restore:restore()
        fit_error=float(np.max(np.abs(results[0]-results[1])))
        assert fit_error<1e-7,fit_error
        records.append(dict(mesh=kind,count=count,transformed=transformed,max_error=fit_error,times=times))
        mp.clear();cmds.delete(mesh)
    (Path(__file__).parent/('junction_compact_'+cmds.about(version=True)+'.json')).write_text(json.dumps(records,indent=2))
    print(json.dumps(records),flush=True);status=0
except BaseException:traceback.print_exc()
finally:
    mp.clear();cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
