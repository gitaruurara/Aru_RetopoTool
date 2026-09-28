"""Large continuous-stroke comparison; numeric update only, no viewport."""
import os,sys,json,time,statistics,traceback
import inspect
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool.editor.curvenet import curve_net_relax as relax
from Aru_RetopoTool.editor.curvenet.relax_preview import RelaxPreview
import numpy as np
root=Path(__file__).resolve().parents[1];status=1;restore=None
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
    from Aru_RetopoTool.editor.curvenet import maya_projector as mp
    folder=root/'bin'/cmds.about(version=True)
    libraries={'separate':mp._load_library(folder/'aru_retopo_maya_projector_bound.dll'),
               'bound':mp._load_library(folder/'aru_retopo_maya_projector_directions.dll')}
    from Aru_RetopoTool.tests import junction_directions_candidate as candidate
    report['trials']=[]
    for mode in ('separate','bound')*3:
        if restore:restore();restore=None
        if mode=='bound':restore=candidate.install()
        mp.clear();mp._LIB=libraries[mode]
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
        report['trials'].append({'mode':mode,**report['modes'][mode]})
        cmds.undo()
        assert cmds.getAttr(node+'.outNetData')==before
        assert not cmds.getAttr(node+'.editPreviewPositions')
        mesh.asMObject()
    a,b=(json.loads(outputs[k][0]) for k in ('separate','bound'))
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
    assert np.allclose(outputs['separate'][1],outputs['bound'][1],rtol=0,atol=1e-8)
    report['max_guide_error']=float(np.max(np.abs(np.asarray(ap)-np.asarray(bp))))
    report['max_mesh_error']=float(np.max(np.abs(np.asarray(outputs['separate'][1])-np.asarray(outputs['bound'][1]))))
    report['within_tolerance']=True;report['restored']=True
    (root/'tests'/('junction_directions_stroke_'+cmds.about(version=True)+'.json')).write_text(json.dumps(report,indent=2))
    print('CONTINUOUS RELAX PASSED', {k:(v['median_ms'],v['release_ms']) for k,v in report['modes'].items()});status=0
except BaseException:traceback.print_exc()
finally:
    if restore:restore()
    mp.clear()
    relax.edit._dirty_shape_view=refresh
    cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
