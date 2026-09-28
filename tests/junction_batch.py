"""Batched junction fitting vs sequential reference on sparse/dense weights."""
import os,sys,traceback,copy
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import numpy as np
from Aru_RetopoTool.editor.curvenet import curve_net_relax as relax,curve_net_edit as edit,maya_projector
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
from Aru_RetopoTool.tests.dense_performance import fixture
status=1
try:
    mesh=cmds.polySphere(r=3,sx=32,sy=24,ch=False)[0]
    fn,dag=edit._get_mesh_fn(mesh)
    positions,splines=fixture()
    base=RetopoGuideData.from_dict({'positions':positions,'splines':splines})
    eps=sorted(base.endpoint_indices());worst=0.;cases=0
    batch=relax._fit_junction_lengths
    for stride in (1,7,31):
        weights={ep:(i%7+1)/7 for i,ep in enumerate(eps[::stride])}
        for manual in (False,True):
            a=copy.deepcopy(base);b=copy.deepcopy(base)
            if manual:
                handles={h for sp in splines[::11] for h in sp[1:3]}
                a.manual_handles=set(handles);b.manual_handles=set(handles)
            relax._fit_junction_lengths=relax._fit_junction_lengths_scalar
            relax._smooth_junctions(a,weights,fn,dag,amount=.6,respect_manual=manual)
            relax._fit_junction_lengths=batch
            relax._smooth_junctions(b,weights,fn,dag,amount=.6,respect_manual=manual)
            error=float(np.max(np.abs(np.array(a.positions)-np.array(b.positions))))
            worst=max(worst,error);assert error<1e-10,error;cases+=1
    from Aru_RetopoTool.tests import junction_norm_reference as reference
    reference._fit_junction_lengths=batch
    for stride in (1,7,31):
        weights={ep:(i%7+1)/7 for i,ep in enumerate(eps[::stride])}
        for manual in (False,True):
            a=RetopoGuideData.from_dict(base.to_dict(),lazy_objects=True)
            b=RetopoGuideData.from_dict(base.to_dict(),lazy_objects=True)
            if manual:
                handles={h for sp in splines[::11] for h in sp[1:3]}
                a.manual_handles=set(handles);b.manual_handles=set(handles)
            reference._smooth_junctions(a,weights,fn,dag,amount=.6,respect_manual=manual)
            relax._smooth_junctions(b,weights,fn,dag,amount=.6,respect_manual=manual)
            assert a.to_dict()==b.to_dict(),'Specialized vector norm changed junction output'
    # Degenerate routes, shared controls, self loops and unpaired branches
    # exercise the batched direction masks and last-write ordering.
    unusual = {
        'positions': [[0,3,0], [.2,3,0], [.5,3,0], [1,3,0],
                      [0,3,.5], [-1,3,0], [-.5,3,0]],
        'splines': [(0,1,2,3), (0,1,6,5), (0,4,4,0), (0,0,3,3)],
    }
    for amount in (0., .6, 1.2):
        for manual in (False, True):
            a=RetopoGuideData.from_dict(unusual,lazy_objects=True)
            b=RetopoGuideData.from_dict(unusual,lazy_objects=True)
            if manual:
                a.manual_handles={4};b.manual_handles={4}
            weights={0:1.,3:.2,5:0.}
            reference._smooth_junctions(a,weights,fn,dag,amount=amount,respect_manual=manual)
            relax._smooth_junctions(b,weights,fn,dag,amount=amount,respect_manual=manual)
            assert a.to_dict()==b.to_dict(), 'Batched directions changed unusual topology'
    print('SPECIALIZED VECTOR NORM / EXACT JUNCTION OUTPUT PASSED')
    print('BATCH JUNCTION PARITY PASSED',cmds.about(version=True),'cases',cases,'max error',worst)
    status=0
except BaseException:traceback.print_exc()
finally:
    maya_projector.clear();edit._invalidate_mesh_accel();cmds.file(new=True,force=True)
    maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
