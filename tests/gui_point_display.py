"""Isolate point-drag native evaluation and optional GPU display paths."""
import json,time,traceback
from pathlib import Path
from unittest.mock import patch
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import gpu_preview
from Aru_RetopoTool.editor.curvenet import gpu_guides,curve_net_edit as edit
from Aru_RetopoTool.tests import gui_point_drag


def run(filtered_base=False):
    root=Path(__file__).resolve().parents[1];report={}
    selection=om.MSelectionList();selection.add('aruRetopoNative1')
    dep=om.MFnDependencyNode(selection.getDependNode(0))
    plug=dep.findPlug('outPositions',False)
    mesh_plug=dep.findPlug('outMesh',False)
    old_refresh=edit._dirty_shape_view
    for controls,direct in ((False,False),(True,False),(True,True)):
        saved=[];display=None;stages=[]
        old_controls=gpu_guides.GPU_CONTROLS;old_objects=gpu_preview._override.foreground.objects
        old_base=gpu_preview._override.operations[0]
        def measured():
            start=time.perf_counter();plug.asMObject();evaluated=time.perf_counter()
            if not direct:mesh_plug.asMObject()
            meshed=time.perf_counter()
            old_refresh();finished=time.perf_counter()
            stages.append({'evaluate_ms':(evaluated-start)*1000,'mesh_ms':(meshed-evaluated)*1000,'draw_ms':(finished-meshed)*1000})
        key='controls'+str(int(controls))+'_direct'+str(int(direct))
        try:
            gpu_guides.GPU_CONTROLS=controls;gpu_preview._set_world_guides(True)
            if direct:
                if 'aruRetopoBufferPreview' not in cmds.allNodeTypes():
                    cmds.loadPlugin(str(root/'bin'/cmds.about(version=True)/'aru_retopo_buffer_preview_v2.mll'),quiet=True)
                display=cmds.createNode('aruRetopoBufferPreview',name='retopoPointBufferDiagnosticShape')
                for src,dst in [('outPositions','positions'),('faceCounts','faceCounts'),('faceIndices','faceIndices')]:cmds.connectAttr('aruRetopoNative1.'+src,display+'.'+dst)
                for mesh in cmds.listConnections('aruRetopoNative1.outMesh',s=False,d=True,type='mesh') or []:
                    saved.append((mesh,cmds.getAttr(mesh+'.visibility')));cmds.setAttr(mesh+'.visibility',False)
                objects=om.MSelectionList();objects.add(display);gpu_preview._override.foreground.objects=objects
            if filtered_base:
                import maya.api.OpenMayaRender as render
                class BaseSubset(render.MSceneRender):
                    def __init__(self,objects):
                        super().__init__('aruRetopoPointBaseSubsetDiagnostic')
                        self.objects=objects
                        self.clearOperation().setOverridesColors(False)
                    def objectSetOverride(self):return self.objects
                excluded=set()
                for group in (gpu_preview._override.foreground.objects,gpu_preview._override.guides.objects):
                    for index in range(group.length()):excluded.add(group.getDagPath(index).fullPathName())
                objects=om.MSelectionList()
                for shape in cmds.ls(dag=True,shapes=True,long=True) or []:
                    if shape not in excluded:objects.add(shape)
                gpu_preview._override.operations[0]=BaseSubset(objects)
            cmds.refresh(force=True)
            with patch.object(edit,'_dirty_shape_view',measured):gui_point_drag.run(numeric=True)
            report[key]=json.loads((root/'tests/gui_point_drag.json').read_text())
            report[key]['display_stages']=stages
        except BaseException:report[key]={'error':traceback.format_exc()}
        finally:
            gpu_guides.GPU_CONTROLS=old_controls
            gpu_preview._override.foreground.objects=old_objects
            gpu_preview._override.operations[0]=old_base
            for mesh,value in saved:
                if cmds.objExists(mesh):cmds.setAttr(mesh+'.visibility',value)
            if display and cmds.objExists(display):cmds.delete(cmds.listRelatives(display,parent=True)[0])
            gpu_preview._set_world_guides(True);cmds.refresh(force=True)
    output=Path(__file__).with_name('gui_point_display_filtered.json') if filtered_base else Path(__file__).with_suffix('.json')
    output.write_text(json.dumps(report,indent=2))
