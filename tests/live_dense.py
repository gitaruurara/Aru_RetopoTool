"""Restored temporary-scene benchmark; call explicitly in interactive Maya."""
import json,time,statistics
import os
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import guides,maya_api,gpu_preview
from Aru_RetopoTool.tests.dense_performance import fixture
from Aru_RetopoTool.core import Plan,unit


def run(panel='modelPanel4',samples=12):
    checkpoint_path=os.path.join(os.path.dirname(__file__),'live_dense_checkpoint.json')
    started=time.perf_counter()
    def checkpoint(stage):
        with open(checkpoint_path,'w') as stream:json.dump({'stage':stage,'elapsed_s':time.perf_counter()-started},stream)
    checkpoint('starting')
    selected=cmds.ls(selection=True,long=True) or []
    undo=cmds.undoInfo(query=True,state=True)
    modified=cmds.file(query=True,modified=True)
    namespace=cmds.namespaceInfo(currentNamespace=True)
    camera=cmds.modelEditor(panel,query=True,camera=True)
    sel=om.MSelectionList();sel.add(camera);path=sel.getDagPath(0)
    if path.node().hasFn(om.MFn.kCamera):path.pop()
    camera_fn=om.MFnTransform(path);camera_matrix=camera_fn.transformation()
    test_ns=None;report={}
    cmds.undoInfo(stateWithoutFlush=False)
    try:
        test_ns=cmds.namespace(add='aruRetopoPerfTest')
        cmds.namespace(set=test_ns)
        reference=cmds.polySphere(r=3,sx=64,sy=32,constructionHistory=False)[0]
        cmds.setAttr(reference+'.translateX',1000.)
        p,s=fixture();plan=Plan(p,s,unit,3)
        guide=guides.create(reference)
        checkpoint('guide topology assignment')
        cmds.setAttr(guide+'.netData',json.dumps({'positions':[(x+1000,y,z) for x,y,z in p],'splines':s}),type='string')
        checkpoint('generator creation')
        output,node=maya_api.create(guide,reference,subdivisions=3,iterations=5)
        checkpoint('patch selection')
        cmds.setAttr(node+'.selectedPatches',json.dumps(plan.region_keys),type='string')
        status=cmds.getAttr(node+'.status');assert not status.startswith('ERROR:'),status
        report['status']=status
        report['quads']=cmds.polyEvaluate(output,face=True)
        cmds.select(reference);cmds.viewFit(camera)
        cmds.select(clear=True)
        checkpoint('GPU enable')
        gpu_preview.enable(panel)
        sel=om.MSelectionList();sel.add(guide)
        plug=om.MFnDependencyNode(sel.getDependNode(0)).findPlug('controlPoints',False).elementByLogicalIndex(0).child(0)
        original=plug.asDouble()
        for mode in ('idle','deform'):
            checkpoint(mode)
            times=[]
            for i in range(samples):
                start=time.perf_counter()
                if mode=='deform':plug.setDouble(original+.0001*(i+1))
                cmds.refresh(force=True)
                times.append((time.perf_counter()-start)*1000)
            report[mode+'_ms']=times;report[mode+'_median']=statistics.median(times[3:])
        report['last_status']=cmds.getAttr(node+'.status')
        return report
    finally:
        checkpoint('restore')
        gpu_preview.disable()
        cmds.namespace(set=namespace)
        if test_ns and cmds.namespace(exists=test_ns):cmds.namespace(removeNamespace=test_ns,deleteNamespaceContent=True)
        camera_fn.setTransformation(camera_matrix)
        cmds.select([s for s in selected if cmds.objExists(s)],replace=True) if selected else cmds.select(clear=True)
        cmds.undoInfo(stateWithoutFlush=undo)
        cmds.file(modified=modified)
        cmds.refresh(force=True)
        checkpoint('finished')
