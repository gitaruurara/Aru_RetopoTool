"""Typed guide output versus JSON, including dirty updates and legacy meshes."""
import json
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import maya_api as api
from Aru_RetopoTool.core import regions,patch_key
from Aru_RetopoTool.tests.test_core import polygon

def plug(node,attr):
    selection=om.MSelectionList();selection.add(node)
    return om.MFnDependencyNode(selection.getDependNode(0)).findPlug(attr,False)
def check(guide):
    # Read typed first, then JSON; neither output is allowed to mark the other clean.
    obj=plug(guide,'outPositions').asMObject()
    typed=list(om.MFnDoubleArrayData(obj).array())
    raw=cmds.getAttr(guide+'.outNetData')
    expected=[v for p in json.loads(raw)['positions'] for v in p] if raw else []
    assert typed==expected
    return typed

def run():
    owned=[]
    guide=cmds.createNode('retopoGuideNode');owned.append(cmds.listRelatives(guide,parent=True)[0])
    p,s=polygon(5,height=1);raw=json.dumps(dict(positions=p,splines=s))
    try:
        cmds.setAttr(guide+'.netData',raw,type='string');base=check(guide)
        ref=cmds.polyPlane(w=10,h=10,sx=8,sy=8)[0];owned.append(ref)
        modern,new=api.create(guide,ref,subdivisions=2);owned.extend([modern,new])
        legacy,old=api.create(guide,ref,subdivisions=2);owned.extend([legacy,old])
        cmds.disconnectAttr(guide+'.netData',old+'.guideRestData')
        cmds.disconnectAttr(guide+'.outPositions',old+'.guidePositions')
        cmds.setAttr(old+'.guideRestData','',type='string')
        keys=json.dumps([patch_key(r) for r in regions(p,s,lambda p:(0,1,0))])
        for node in (new,old):cmds.setAttr(node+'.selectedPatches',keys,type='string')
        for i in range(5):
            cmds.setAttr(guide+'.controlPoints[0]',.03*i,0,.01*i,type='double3')
            check(guide)
            a=om.MFnMesh(plug(new,'outMesh').asMObject()).getPoints()
            b=om.MFnMesh(plug(old,'outMesh').asMObject()).getPoints()
            assert list(map(tuple,a))==list(map(tuple,b))
        assert check(guide)!=base
        current=check(guide)
        preview=[v+.123 for v in current]
        cmds.setAttr(guide+'.editPreviewPositions',preview,type='doubleArray')
        assert check(guide)==preview
        assert cmds.getAttr(guide+'.netData')==raw
        a=om.MFnMesh(plug(new,'outMesh').asMObject()).getPoints()
        b=om.MFnMesh(plug(old,'outMesh').asMObject()).getPoints()
        assert list(map(tuple,a))==list(map(tuple,b))
        cmds.undo();assert check(guide)==current
        cmds.redo();assert check(guide)==preview
        cmds.setAttr(guide+'.editPreviewPositions',[],type='doubleArray')
        assert check(guide)==current
        # A stale preview from different topology must never truncate output.
        cmds.setAttr(guide+'.editPreviewPositions',[1.,2.,3.],type='doubleArray')
        assert check(guide)==current
        cmds.setAttr(guide+'.editPreviewPositions',[],type='doubleArray')
        print('PASS numeric preview output, legacy mesh parity, clear, Undo/Redo, stale length')
        # Deformer input, sculpt envelope and explicit pose dirty propagation.
        meshdata=om.MFnMeshData().create()
        deformed=om.MPointArray([(x,y+.4,z+.1) for x,y,z in p])
        om.MFnMesh().create(deformed,[3],[0,1,2],parent=meshdata)
        plug(guide,'inSurface').setMObject(meshdata)
        for falloff in (0.,.2,.8):
            cmds.setAttr(guide+'.sculptFalloff',falloff);check(guide)
            cmds.setAttr(guide+'.sculptPose[0].sculptPoseX',falloff);check(guide)
            cmds.setAttr(guide+'.poseFalloff',.4+falloff);check(guide)
        # Surface bind takes precedence over deformer input.
        shape=api.shape(ref,'mesh')
        cmds.connectAttr(shape+'.worldMesh[0]',guide+'.driverMesh')
        binding=dict(cv_idx=0,tri_verts=[0,1,9],bary=[.2,.3,.5],rest_offset=[0,0,0],
                     rest_normal=[0,1,0],rest_tangent=[1,0,0],rest_binormal=[0,0,1])
        cmds.setAttr(guide+'.surfaceBindData',json.dumps({'bindings':[binding]}),type='string')
        previous=check(guide)
        cmds.move(0,.5,0,ref+'.vtx[0]',relative=True);assert check(guide)!=previous
        cmds.setAttr(guide+'.netData','',type='string');assert check(guide)==[]
        cmds.setAttr(guide+'.netData',raw,type='string');assert check(guide)
        print('PASS typed positions match JSON: CP, legacy mesh, deformer/sculpt, surface bind, empty/restore')
    finally:
        for node in reversed(owned):
            if cmds.objExists(node):cmds.delete(node)
