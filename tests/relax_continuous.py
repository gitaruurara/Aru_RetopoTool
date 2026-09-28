"""Large continuous-stroke comparison; numeric update only, no viewport."""
import os,sys,json,time,statistics,traceback
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
    for plugin in ('editor/curvenet/aru_retopo_guide_plugin.py','aru_retopo_plugin.py','aru_retopo_plan_plugin.py','aru_retopo_draw_plugin.py','bin/2027/aru_retopo_mesh_buffer_v4.mll'):
        cmds.loadPlugin(str(root/plugin),quiet=True)
    cmds.file('D:/Dropbox/App/.codex/recovery/retopo-20260917/maya-v4-restore-16732.ma',open=True,force=True,prompt=False)
    node='aruRetopoGuideShape1';native='aruRetopoNative1'
    before=cmds.getAttr(node+'.outNetData')
    weights={int(k):v for k,v in json.loads((root/'tests/relax_benchmark_weights.json').read_text()).items()}
    assert len(weights)==200
    selection=om.MSelectionList();selection.add(native)
    mesh=om.MFnDependencyNode(selection.getDependNode(0)).findPlug('outMesh',False)
    relax.edit._dirty_shape_view=lambda:None
    report={'scope':'8 consecutive 200 EP dabs with native outMesh, fixed weights; no brush or viewport','modes':{}}
    outputs={}
    for mode in ('ordinary','preview'):
        cmds.undoInfo(openChunk=True,chunkName='Continuous '+mode)
        stroke=RelaxPreview(node) if mode=='preview' else None
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
    assert outputs['ordinary']==outputs['preview'],'Continuous stroke output differs'
    report['exact_final_data_and_mesh']=True;report['restored']=True
    (root/'tests/relax_continuous_2027.json').write_text(json.dumps(report,indent=2))
    print('CONTINUOUS RELAX PASSED', {k:(v['median_ms'],v['release_ms']) for k,v in report['modes'].items()});status=0
except BaseException:traceback.print_exc()
finally:
    relax.edit._dirty_shape_view=refresh
    cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
