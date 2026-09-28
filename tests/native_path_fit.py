"""Compare native and original curve fitter, including fixed handles."""
import os,sys,traceback,copy
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import numpy as np
from Aru_RetopoTool.editor.curvenet import curve_net_context as context,curve_net_edit as edit,maya_projector,path_fit
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
status=1
try:
    mesh=cmds.polySphere(sx=20,sy=16,ch=False)[0]
    rng=np.random.default_rng(932);worst=0.;cases=0
    for i in range(12):
        p=rng.normal(size=3);p/=np.linalg.norm(p)
        q=rng.normal(size=3);q/=np.linalg.norm(q)
        h=p+(q-p)/3+rng.normal(size=3)*.2
        j=q+(p-q)/3+rng.normal(size=3)*.2
        original=RetopoGuideData.from_dict({'positions':[p.tolist(),h.tolist(),j.tolist(),q.tolist()],'splines':[[0,1,2,3]]})
        for fixed in (None,1,2):
            a=copy.deepcopy(original);b=copy.deepcopy(original)
            path_fit.ENABLED=False
            ea=context._fit_spline_handles_to_mesh(a,0,mesh,iters=8,n_samples=11,fixed=fixed)
            path_fit.ENABLED=True
            eb=context._fit_spline_handles_to_mesh(b,0,mesh,iters=8,n_samples=11,fixed=fixed)
            assert path_fit._LIB is not None,'Native DLL was not exercised'
            error=float(np.max(np.abs(np.array(a.positions)-np.array(b.positions))))
            worst=max(worst,error);assert error<1e-9,(i,fixed,error)
            assert abs(ea-eb)<1e-9,(ea,eb)
            assert a.splines==b.splines
            cases+=1
    print('NATIVE PATH FIT PARITY PASSED',cmds.about(version=True),'cases',cases,'max error',worst)
    status=0
except BaseException:traceback.print_exc()
finally:
    path_fit.ENABLED=True;maya_projector.clear();edit._invalidate_mesh_accel()
    cmds.file(new=True,force=True);maya.standalone.uninitialize()
    sys.stdout.flush();sys.stderr.flush();os._exit(status)
