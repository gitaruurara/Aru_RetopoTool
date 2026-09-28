"""Run from evalDeferred so each measured edit can be undone immediately."""
import json,time,statistics,traceback
from pathlib import Path
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import native_backend,gpu_preview
from Aru_RetopoTool.editor.curvenet import curve_net_relax,curve_net_edit

def run():
    root=Path(__file__).resolve().parents[1]
    report={'scope':'Actual brush plus relax/write/synchronous refresh; separate undo-restored steps, not mouse gesture series','samples_ms':{}}
    guide='aruRetopoGuideShape1';native=native_backend.backend('aruRetopoGenerator1')
    before=cmds.getAttr(guide+'.outNetData')
    meshes=cmds.listConnections(native+'.outMesh',s=False,d=True,type='mesh') or []
    saved=[(m,cmds.getAttr(m+'.visibility')) for m in meshes]
    old_objects=gpu_preview._override.foreground.objects
    preview=None;pending=False
    original_refresh=curve_net_edit._dirty_shape_view
    selection=om.MSelectionList();selection.add(native)
    coordinate_plug=om.MFnDependencyNode(selection.getDependNode(0)).findPlug('outPositions',False)
    stage_rows=[]
    def measured_refresh():
        start=time.perf_counter();coordinate_plug.asMObject();evaluated=time.perf_counter()
        native_times=cmds.getAttr(native+'.computeMilliseconds')
        redraw_start=time.perf_counter();original_refresh();finished=time.perf_counter()
        stage_rows.append({'evaluate_ms':(evaluated-start)*1000,'redraw_ms':(finished-redraw_start)*1000,'native_ms':native_times})

    try:
        cmds.loadPlugin(str(root/'bin'/cmds.about(version=True)/'aru_retopo_buffer_preview_v2.mll'),quiet=True)
        preview=cmds.createNode('aruRetopoBufferPreview',name='retopoRelaxBufferDiagnosticShape')
        for src,dst in [('outPositions','positions'),('faceCounts','faceCounts'),('faceIndices','faceIndices')]:
            cmds.connectAttr(native+'.'+src,preview+'.'+dst)
        objects=om.MSelectionList();objects.add(preview)
        cmds.setAttr(preview+'.visibility',False)
        report['stages']={}
        curve_net_edit._dirty_shape_view=measured_refresh
        for mode in ('mesh','buffer'):
            if mode=='buffer':
                cmds.setAttr(preview+'.visibility',True)
                gpu_preview._override.foreground.objects=objects
                for m,_ in saved:cmds.setAttr(m+'.visibility',False)
            cmds.refresh(force=True)
            rows=[];stage_rows.clear()
            for i in range(5):
                cmds.undoInfo(openChunk=True,chunkName='Retopo buffer relax sample')
                try:
                    pending=True
                    start=time.perf_counter()
                    affected=curve_net_relax.brush_relax(guide,1546,1145)
                    rows.append((time.perf_counter()-start)*1000)
                finally:cmds.undoInfo(closeChunk=True)
                cmds.undo();pending=False
                assert cmds.getAttr(guide+'.outNetData')==before,'Sample undo failed'
                cmds.refresh(currentView=True)
            report['samples_ms'][mode]=rows
            report['stages'][mode]=list(stage_rows)
            report['affected']=len(affected)
        report['median_ms']={k:statistics.median(v[1:]) for k,v in report['samples_ms'].items()}
    except BaseException:report['error']=traceback.format_exc()
    finally:
        curve_net_edit._dirty_shape_view=original_refresh
        if pending:cmds.undo()
        gpu_preview._override.foreground.objects=old_objects
        for m,v in saved:cmds.setAttr(m+'.visibility',v)
        if preview and cmds.objExists(preview):cmds.delete(cmds.listRelatives(preview,parent=True)[0])
        cmds.refresh(force=True)
        report['restored']=cmds.getAttr(guide+'.outNetData')==before
        (root/'tests'/'gui_buffer_relax_stages.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
