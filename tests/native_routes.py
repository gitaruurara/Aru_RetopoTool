import os,sys,traceback
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import numpy as np
from Aru_RetopoTool.editor.curvenet import curve_net_context as context,curve_net_edit as edit,maya_projector
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
status=1
try:
    mesh=cmds.polySphere(sx=20,sy=16,ch=False)[0]
    rng=np.random.default_rng(118);worst=0.;cases=0
    for transformed in (False,True):
        if transformed:
            cmds.setAttr(mesh+'.translate',1.2,-.3,.7,type='double3');cmds.setAttr(mesh+'.rotateY',32)
            cmds.setAttr(mesh+'.scale',-1.3,.7,1.8,type='double3')
        fn,dag=edit._get_mesh_fn(mesh)
        controls=[]
        for i in range(12):
            p=rng.normal(size=3);p/=np.linalg.norm(p)
            q=rng.normal(size=3);q/=np.linalg.norm(q)
            controls.append([p.tolist(),(p+(q-p)/3+rng.normal(size=3)*.15).tolist(),(q+(p-q)/3+rng.normal(size=3)*.15).tolist(),q.tolist()])
        for draft in (True,False):
            actual=maya_projector.fit_routes(fn,controls,draft)
            assert actual is not None,'Native route function must be exercised'
            for points,result in zip(controls,actual):
                cn=RetopoGuideData.from_dict({'positions':points,'splines':[[0,1,2,3]]})
                context._fit_spline_handles_to_mesh(cn,0,mesh,iters=context._FIT_DRAFT_ITERS if draft else context._FIT_ITERS,n_samples=context._FIT_DRAFT_SAMPLES if draft else context._FIT_SAMPLES)
                error=float(np.max(np.abs(np.array(cn.positions[1:3])-np.array(result))))
                worst=max(worst,error);assert error<1e-9,(transformed,draft,error);cases+=1
    print('NATIVE ROUTES / DRAFT / REFINED / TRANSFORM PARITY PASSED',cmds.about(version=True),'cases',cases,'max error',worst)
    status=0
except BaseException:traceback.print_exc()
finally:
    maya_projector.clear();edit._invalidate_mesh_accel();cmds.file(new=True,force=True)
    maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
