"""Opt-in live preview diagnostic. Requires v2 solver in an existing test fixture."""
import json,time,statistics
from pathlib import Path
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import native_backend,gpu_preview

def run(node='aruRetopoGenerator1',guide='aruRetopoGuideShape1',split_stages=False):
    native=native_backend.backend(node)
    if not native or not cmds.attributeQuery('outPositions',node=native,exists=True):
        raise RuntimeError('Fresh Maya with native v2 fixture required')
    root=Path(__file__).resolve().parents[1]
    cmds.loadPlugin(str(root/'bin'/cmds.about(version=True)/'aru_retopo_buffer_preview_v2.mll'),quiet=True)
    meshes=cmds.listConnections(native+'.outMesh',s=False,d=True,type='mesh') or []
    saved=[(m,cmds.getAttr(m+'.visibility')) for m in meshes]
    old_objects=gpu_preview._override.foreground.objects
    old_cp=cmds.getAttr(guide+'.controlPoints[0]')[0]
    old_xray=cmds.getAttr(guide+'.xray')
    preview=None
    from Aru_RetopoTool.editor.curvenet import gpu_guides
    report={'pid':__import__('os').getpid(),'gpu_controls':gpu_guides.GPU_CONTROLS,'scope':'Full guide CP dirty -> solver -> direct GPU preview -> forced refresh; synthetic edits, no mouse context','samples_ms':{}}
    try:
        preview=cmds.createNode('aruRetopoBufferPreview',name='retopoLiveBufferDiagnosticShape')
        for src,dst in [('outPositions','positions'),('faceCounts','faceCounts'),('faceIndices','faceIndices')]:
            cmds.connectAttr(native+'.'+src,preview+'.'+dst)
        objects=om.MSelectionList();objects.add(preview)
        gpu_preview._override.foreground.objects=objects
        for m,_ in saved:cmds.setAttr(m+'.visibility',False)
        cmds.setAttr(guide+'.xray',True)
        coordinate_plug=None
        if split_stages:
            selection=om.MSelectionList();selection.add(native)
            coordinate_plug=om.MFnDependencyNode(selection.getDependNode(0)).findPlug('outPositions',False)
            report['stages_ms']=[]
        for mode in ('idle','deform'):
            samples=[]
            for i in range(35):
                start=time.perf_counter()
                if mode=='deform':cmds.setAttr(guide+'.controlPoints[0]',old_cp[0]+i*.0001,old_cp[1],old_cp[2],type='double3')
                assigned=time.perf_counter()
                if split_stages and mode=='deform':
                    data=coordinate_plug.asMObject()
                evaluated=time.perf_counter()
                cmds.refresh(force=True)
                refreshed=time.perf_counter()
                if split_stages and mode=='deform' and i>=5:
                    report['stages_ms'].append({'assign':(assigned-start)*1000,'evaluate':(evaluated-assigned)*1000,'refresh':(refreshed-evaluated)*1000})
                if i>=5:samples.append((time.perf_counter()-start)*1000)
            report['samples_ms'][mode]=samples
        report['median_ms']={k:statistics.median(v) for k,v in report['samples_ms'].items()}
        report['max_ms']={k:max(v) for k,v in report['samples_ms'].items()}
        suffix='gpu_controls' if gpu_guides.GPU_CONTROLS else 'ui_controls'
        if split_stages:
            suffix+='_stages'
            report['stage_medians_ms']={k:statistics.median(row[k] for row in report['stages_ms']) for k in ('assign','evaluate','refresh')}
        (root/'tests'/('gui_buffer_live_'+suffix+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
        return report
    finally:
        gpu_preview._override.foreground.objects=old_objects
        for m,v in saved:cmds.setAttr(m+'.visibility',v)
        cmds.setAttr(guide+'.controlPoints[0]',*old_cp,type='double3')
        cmds.setAttr(guide+'.xray',old_xray)
        if preview and cmds.objExists(preview):cmds.delete(cmds.listRelatives(preview,parent=True)[0])
        cmds.refresh(force=True)
