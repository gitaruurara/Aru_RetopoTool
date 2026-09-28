"""Compare a two-column solver with SVD, including projected curve fits."""
import os,sys,json,time,statistics,traceback,inspect,copy
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import numpy as np
from Aru_RetopoTool.editor.curvenet import curve_net_relax as relax,curve_net_edit as edit
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData

from Aru_RetopoTool.tests.junction_inverse_candidate import _junction_length_inverse as analytic

status=1
try:
    rng=np.random.default_rng(2941)
    t=np.linspace(.05,.95,15);u=1-t;c0=3*u*u*t;c1=3*u*t*t
    ds=rng.normal(size=(10000,2,3));ds/=np.linalg.norm(ds,axis=2)[:,:,None]
    ds[:100,1]=ds[:100,0];ds[100:200,1]=-ds[100:200,0]
    columns=np.stack((c0[None,:,None]*ds[:,0,None,:],c1[None,:,None]*ds[:,1,None,:]),axis=-1)
    rows=np.concatenate((columns.reshape(-1,45,2),np.broadcast_to(np.eye(2)*.1,(len(ds),2,2))),axis=1)
    reference=lambda a:np.linalg.pinv(a,rcond=np.finfo(float).eps*a.shape[1])
    error=float(np.max(np.abs(reference(rows)-analytic(rows))))
    assert error<1e-12,error
    timings={}
    for count in (16,200,500,10000):
        timings[count]={}
        for name,fn in [('svd',reference),('analytic',analytic)]:
            durations=[]
            for _ in range(20):
                start=time.perf_counter();fn(rows[:count]);durations.append((time.perf_counter()-start)*1000)
            timings[count][name]=statistics.median(durations)
    source=inspect.getsource(relax._fit_junction_lengths)
    source=source.replace('np.linalg.pinv(rows,rcond=np.finfo(float).eps*rows.shape[1])','analytic(rows)')
    scope=dict(relax.__dict__,analytic=analytic);exec(source,scope)
    baseline=relax._fit_junction_lengths;candidate=scope['_fit_junction_lengths'];records=[]
    for kind in ('sphere','cube'):
        mesh=(cmds.polySphere(sx=64,sy=32,ch=False) if kind=='sphere' else cmds.polyCube(ch=False))[0]
        fn,_=edit._get_mesh_fn(mesh)
        cn=RetopoGuideData();directions={}
        for i in range(500):
            a=rng.normal(size=3);a/=np.linalg.norm(a)
            b=a+rng.normal(size=3)*.15;b/=np.linalg.norm(b)
            start=len(cn.positions)
            for point in (a,a+(b-a)/3,b-(b-a)/3,b):cn.add_cv(point.tolist())
            cn.add_spline(start,start+1,start+2,start+3)
            directions[start+1]=(b-a)/max(np.linalg.norm(b-a),1e-12)
            directions[start+2]=-directions[start+1]
        results=[];times={}
        for name,solver in [('svd',baseline),('analytic',candidate)]:
            current=copy.deepcopy(cn);durations=[]
            for i in range(8):
                start=time.perf_counter();solver(current,set(range(500)),directions,fn);durations.append((time.perf_counter()-start)*1000)
            results.append(np.asarray(current.positions));times[name]=statistics.median(durations[1:])
        fit_error=float(np.max(np.abs(results[0]-results[1])))
        assert fit_error<1e-9,fit_error
        records.append(dict(mesh=kind,max_error=fit_error,times=times))
        cmds.delete(mesh)
    report=dict(inverse_max_error=error,inverse_ms=timings,projected_fit=records)
    (Path(__file__).parent/('junction_inverse_'+cmds.about(version=True)+'.json')).write_text(json.dumps(report,indent=2))
    print(json.dumps(report));status=0
except BaseException:traceback.print_exc()
finally:
    cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
