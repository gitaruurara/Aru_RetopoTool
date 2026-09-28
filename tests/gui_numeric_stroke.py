"""Deferred GUI comparison: real brush selection + numeric stroke + redraw."""
import json,time,statistics,traceback,hashlib,struct
from pathlib import Path
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool.editor.curvenet import curve_net_relax as relax,curve_net_edit as edit
from Aru_RetopoTool.editor.curvenet.relax_preview import RelaxPreview


def run(direct_buffer=False, gpu_controls=False, filtered_base=False, hide_guides=False, brush_start=(1546,1145), capture=None, instrument_stages=True):
    root=Path(__file__).resolve().parents[1]
    node='aruRetopoGuideShape1'
    before=cmds.getAttr(node+'.outNetData')
    report={'scope':'8 consecutive brush calls and synchronous GPU redraw; scripted screen path, not physical mouse events','modes':{},'brush_start':list(brush_start)}
    old_refresh=edit._dirty_shape_view
    selection=om.MSelectionList();selection.add('aruRetopoNative1')
    plug=om.MFnDependencyNode(selection.getDependNode(0)).findPlug('outPositions',False)
    timing_plug=om.MFnDependencyNode(selection.getDependNode(0)).findPlug('computeMilliseconds',False)
    stages=[]
    def measured_refresh():
        if not instrument_stages:return old_refresh()
        start=time.perf_counter();plug.asMObject();evaluated=time.perf_counter()
        native_stages=list(om.MFnDoubleArrayData(timing_plug.asMObject()).array())
        draw_start=time.perf_counter();thread_start=time.thread_time();process_start=time.process_time()
        old_refresh();finished=time.perf_counter()
        thread_ms=(time.thread_time()-thread_start)*1000;process_ms=(time.process_time()-process_start)*1000
        stages.append({'native_evaluate_ms':(evaluated-start)*1000,'redraw_ms':(finished-draw_start)*1000,'native_stages_ms':native_stages,'draw_thread_ms':thread_ms,'draw_process_ms':process_ms})
    outputs={};pending=False;stroke=None
    from Aru_RetopoTool import gpu_preview
    from Aru_RetopoTool.editor.curvenet import gpu_guides
    old_controls=gpu_guides.GPU_CONTROLS
    old_objects=gpu_preview._override.foreground.objects
    old_base=gpu_preview._override.operations[0]
    saved=[];display=None
    guide_visibility=None
    try:
        if hide_guides:
            guide_visibility=cmds.getAttr(node+'.visibility')
            cmds.setAttr(node+'.visibility',False)
        if gpu_controls:
            gpu_guides.GPU_CONTROLS=True
            gpu_preview._set_world_guides(True)
        if direct_buffer:
            if 'aruRetopoBufferPreview' not in cmds.allNodeTypes():
                cmds.loadPlugin(str(root/'bin'/cmds.about(version=True)/'aru_retopo_buffer_preview_v2.mll'),quiet=True)
            display=cmds.createNode('aruRetopoBufferPreview',name='retopoNumericBufferDiagnosticShape')
            for src,dst in [('outPositions','positions'),('faceCounts','faceCounts'),('faceIndices','faceIndices')]:
                cmds.connectAttr('aruRetopoNative1.'+src,display+'.'+dst)
            for m in cmds.listConnections('aruRetopoNative1.outMesh',s=False,d=True,type='mesh') or []:
                saved.append((m,cmds.getAttr(m+'.visibility')))
                cmds.setAttr(m+'.visibility',False)
            objects=om.MSelectionList();objects.add(display)
            gpu_preview._override.foreground.objects=objects
            cmds.refresh(force=True)
        if filtered_base:
            import maya.api.OpenMayaRender as render
            class BaseSubset(render.MSceneRender):
                def __init__(self,objects):
                    super().__init__('aruRetopoBaseSubsetDiagnostic')
                    self.objects=objects
                    self.clearOperation().setOverridesColors(False)
                def objectSetOverride(self):return self.objects
            excluded=set()
            for group in (gpu_preview._override.foreground.objects,gpu_preview._override.guides.objects):
                for index in range(group.length()):
                    excluded.add(group.getDagPath(index).fullPathName())
            objects=om.MSelectionList()
            for shape in cmds.ls(dag=True,shapes=True,long=True) or []:
                if shape not in excluded:objects.add(shape)
            gpu_preview._override.operations[0]=BaseSubset(objects)
            report['base_excluded']=sorted(excluded)
            cmds.refresh(force=True)
        edit._dirty_shape_view=measured_refresh
        for mode in ('ordinary','numeric'):
            cmds.undoInfo(openChunk=True,chunkName='Retopo GUI '+mode)
            pending=True
            stroke=RelaxPreview(node) if mode=='numeric' else None
            try:
                rows=[];affected=set()
                for i in range(8):
                    stages.clear();start=time.perf_counter()
                    if stroke:ids=stroke.brush(brush_start[0]+4*i,brush_start[1])
                    else:ids=relax.brush_relax(node,brush_start[0]+4*i,brush_start[1])
                    elapsed=(time.perf_counter()-start)*1000
                    assert ids, "No EP affected; invalid benchmark screen path"
                    affected.update(ids)
                    rows.append({'total_ms':elapsed,'affected':len(ids),'stages':list(stages)})
                start=time.perf_counter()
                if stroke:stroke.commit()
                else:relax.relax(node,{ep:1. for ep in affected},draft=False,smooth=False)
                release=(time.perf_counter()-start)*1000
                outputs[mode]=cmds.getAttr(node+'.netData')
                mesh_values=list(om.MFnDoubleArrayData(plug.asMObject()).array())
                if capture is not None:capture[mode]={'guide':outputs[mode],'mesh':list(mesh_values)}
                guide_hash=hashlib.sha256(outputs[mode].encode()).hexdigest()
                mesh_hash=hashlib.sha256(struct.pack('='+str(len(mesh_values))+'d',*mesh_values)).hexdigest()
                report['modes'][mode]={'samples':rows,'median_ms':statistics.median(r['total_ms'] for r in rows[1:]),'release_ms':release,'guide_hash':guide_hash,'mesh_hash':mesh_hash}
            finally:cmds.undoInfo(closeChunk=True)
            cmds.undo();pending=False
            assert cmds.getAttr(node+'.outNetData')==before
            assert not cmds.getAttr(node+'.editPreviewPositions')
            cmds.refresh(force=True)
        report['exact_final_data']=outputs['ordinary']==outputs['numeric']
        assert report['exact_final_data']
    except BaseException:report['error']=traceback.format_exc()
    finally:
        edit._dirty_shape_view=old_refresh
        if stroke and not stroke.closed:stroke.cancel()
        if pending:cmds.undo()
        if guide_visibility is not None and cmds.objExists(node):
            cmds.setAttr(node+'.visibility',guide_visibility)
        gpu_guides.GPU_CONTROLS=old_controls
        gpu_preview._set_world_guides(True)
        gpu_preview._override.foreground.objects=old_objects
        gpu_preview._override.operations[0]=old_base
        for m,value in saved:
            if cmds.objExists(m):cmds.setAttr(m+'.visibility',value)
        if display and cmds.objExists(display):cmds.delete(cmds.listRelatives(display,parent=True)[0])
        cmds.refresh(force=True)
        report['restored']=cmds.getAttr(node+'.outNetData')==before
        report['direct_buffer']=direct_buffer
        report['gpu_controls']=gpu_controls
        name='gui_numeric_stroke_direct.json' if direct_buffer else 'gui_numeric_stroke.json'
        if gpu_controls:name=name.replace('.json','_gpu_controls.json')
        if filtered_base:name=name.replace('.json','_filtered_base.json')
        if hide_guides:name=name.replace('.json','_no_guides.json')
        report['hide_guides']=hide_guides
        (root/'tests'/name).write_text(json.dumps(report,indent=2))
