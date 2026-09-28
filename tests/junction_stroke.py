"""Large continuous-stroke comparison; numeric update only, no viewport."""
import os,sys,json,time,statistics,traceback
import numpy as np
import inspect
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool.editor.curvenet import curve_net_relax as relax
from Aru_RetopoTool.editor.curvenet.relax_preview import RelaxPreview
root=Path(__file__).resolve().parents[1];status=1
refresh=relax.edit._dirty_shape_view
try:
    for plugin in ('editor/curvenet/aru_retopo_guide_plugin.py','aru_retopo_plugin.py','aru_retopo_plan_plugin.py','aru_retopo_draw_plugin.py','bin/'+cmds.about(version=True)+'/aru_retopo_mesh_buffer_numeric.mll'):
        cmds.loadPlugin(str(root/plugin),quiet=True)
    cmds.file('D:/Dropbox/App/.codex/recovery/retopo-20260917/maya-numeric-isolated-20260918.ma',open=True,force=True,prompt=False)
    node='aruRetopoGuideShape1';native='aruRetopoNative1'
    before=cmds.getAttr(node+'.outNetData')
    weights={int(k):v for k,v in json.loads((root/'tests/relax_benchmark_weights.json').read_text()).items()}
    assert len(weights)==200
    selection=om.MSelectionList();selection.add(native)
    mesh=om.MFnDependencyNode(selection.getDependNode(0)).findPlug('outMesh',False)
    relax.edit._dirty_shape_view=lambda:None
    report={'scope':'8 consecutive 200 EP dabs with native outMesh, fixed weights; no brush or viewport','modes':{}}
    outputs={}
    from Aru_RetopoTool.tests.junction_inverse_candidate import _junction_length_inverse
    original_fit=relax._fit_junction_lengths
    scope=dict(relax.__dict__,_junction_length_inverse=_junction_length_inverse)
    source=inspect.getsource(original_fit).replace('np.linalg.pinv(rows,rcond=np.finfo(float).eps*rows.shape[1])','_junction_length_inverse(rows)')
    exec(source,scope)
    candidate_fit=scope['_fit_junction_lengths']
    order=('analytic','svd') if os.environ.get('ARU_JUNCTION_REVERSE') else ('svd','analytic')
    for mode in order*3:
        relax._fit_junction_lengths=original_fit if mode=='svd' else candidate_fit
        cmds.undoInfo(openChunk=True,chunkName='Continuous '+mode)
        stroke=RelaxPreview(node)
        try:
            rows=[]
            for i in range(8):
                start=time.perf_counter()
                if stroke:stroke.apply(weights)
                else:relax.relax(node,weights)
                calc=(time.perf_counter()-start)*1000
                mesh.asMObject()
                rows.append(dict(calc_write_ms=calc,total_ms=(time.perf_counter()-start)*1000))
            start=time.perf_counter()
            if stroke:stroke.commit()
            else:relax.relax(node,{ep:1. for ep in weights},draft=False,smooth=False)
            mesh.asMObject()
            finish=(time.perf_counter()-start)*1000
            outputs[mode]=(cmds.getAttr(node+'.netData'),list(map(tuple,om.MFnMesh(mesh.asMObject()).getPoints())))
            report['modes'][mode]={'samples':rows,'median_ms':statistics.median(row['total_ms'] for row in rows[1:]),'release_ms':finish}
        finally:
            if stroke and not stroke.closed:stroke.cancel()
            cmds.undoInfo(closeChunk=True)
        cmds.undo()
        assert cmds.getAttr(node+'.outNetData')==before
        assert not cmds.getAttr(node+'.editPreviewPositions')
        mesh.asMObject()
    a,b=(json.loads(outputs[k][0]) for k in ('svd','analytic'))
    ap=a.pop('positions');bp=b.pop('positions')
    assert np.allclose(ap,bp,rtol=0,atol=1e-9)
    def close_metadata(left,right):
        if isinstance(left,dict):
            assert left.keys()==right.keys()
            for key in left:close_metadata(left[key],right[key])
        elif isinstance(left,list):
            assert len(left)==len(right)
            for x,y in zip(left,right):close_metadata(x,y)
        elif isinstance(left,float):assert abs(left-right)<1e-9,(left,right)
        else:assert left==right,(left,right)
    close_metadata(a,b)
    assert np.allclose(outputs['svd'][1],outputs['analytic'][1],rtol=0,atol=1e-8)
    report['max_guide_error']=float(np.max(np.abs(np.asarray(ap)-np.asarray(bp))))
    report['max_mesh_error']=float(np.max(np.abs(np.asarray(outputs['svd'][1])-np.asarray(outputs['analytic'][1]))))
    report['within_tolerance']=True;report['restored']=True
    (root/'tests'/('junction_stroke_2027_reverse.json' if os.environ.get('ARU_JUNCTION_REVERSE') else 'junction_stroke_2027.json')).write_text(json.dumps(report,indent=2))
    print('CONTINUOUS RELAX PASSED', {k:(v['median_ms'],v['release_ms']) for k,v in report['modes'].items()});status=0
except BaseException:traceback.print_exc()
finally:
    relax.edit._dirty_shape_view=refresh
    cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
