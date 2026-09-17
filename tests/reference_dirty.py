"""Reference-cache invalidation across DG/EM, animation, edits and connections."""
import json
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import maya_api as api
from Aru_RetopoTool.core import regions,patch_key
from Aru_RetopoTool.tests.test_core import polygon
from Aru_RetopoTool.tests.typed_positions import plug

def run():
    owned=[];mode=cmds.evaluationManager(q=True,mode=True)[0];time=cmds.currentTime(q=True)
    guide=cmds.createNode('retopoGuideNode');owned.append(cmds.listRelatives(guide,parent=True)[0])
    p,s=polygon(5,height=1);cmds.setAttr(guide+'.netData',json.dumps(dict(positions=p,splines=s)),type='string')
    ref=cmds.polyPlane(w=12,h=12,sx=4,sy=4)[0];owned.append(ref)
    keys=json.dumps([patch_key(r) for r in regions(p,s,lambda p:(0,1,0))])
    try:
        nodes=[]
        for _ in range(2):
            mesh,node=api.create(guide,ref,subdivisions=2);owned.extend([mesh,node]);nodes.append(node)
            cmds.setAttr(node+'.selectedPatches',keys,type='string')
        selection=om.MSelectionList();selection.add(nodes[1]);oracle=om.MFnDependencyNode(selection.getDependNode(0)).userNode()
        def compare():
            oracle._reference_dirty=True
            cmds.dgdirty(nodes[1]+'.referenceMesh')
            points=[]
            for node in nodes:
                fn=om.MFnMesh(plug(node,'outMesh').asMObject());points.append(list(map(tuple,fn.getPoints())))
                assert not cmds.getAttr(node+'.status').startswith('ERROR:')
            assert points[0]==points[1]
            return points[0]
        for evaluation in ('off','serial','parallel'):
            cmds.evaluationManager(mode=evaluation)
            for frame,height in ((1,0.),(2,.5),(3,-.3)):
                cmds.setKeyframe(ref,attribute='translateY',time=frame,value=height)
            previous=None
            for frame in (1,2,3,2,1):
                cmds.currentTime(frame);a=compare()
                assert max(abs(p[1]-cmds.getAttr(ref+'.translateY')) for p in a)<1e-6
                if previous is not None:assert a!=previous
                previous=a
                cmds.setAttr(guide+'.controlPoints[0].xValue',frame*.01);compare()
            before=compare()
            cmds.move(0,.15,0,ref+'.vtx[*]',relative=True);assert compare()!=before
            cmds.undo();assert compare()==before
        source=api.shape(ref,'mesh')+'.worldMesh[0]'
        cmds.disconnectAttr(source,nodes[0]+'.referenceMesh')
        # Maya retains the last mesh value after disconnection.
        compare()
        plug(nodes[0],'referenceMesh').setMObject(om.MFnMeshData().create())
        plug(nodes[0],'outMesh').asMObject()
        assert cmds.getAttr(nodes[0]+'.status').startswith('ERROR:')
        cmds.connectAttr(source,nodes[0]+'.referenceMesh');compare()
        print('PASS reference cache: DG/serial/parallel, animated transforms, CP edits, vertex edit/Undo, disconnect/reconnect')
    finally:
        cmds.evaluationManager(mode=mode);cmds.currentTime(time)
        for node in reversed(owned):
            if cmds.objExists(node):cmds.delete(node)
