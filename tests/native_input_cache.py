"""Reference invalidation for native cached inputs, using Python output oracle."""
import os,json,traceback,sys
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import maya.api.OpenMaya as om
from pathlib import Path
from Aru_RetopoTool import maya_api as api,native_backend as backend
from Aru_RetopoTool.tests.test_core import polygon
from Aru_RetopoTool.tests.typed_positions import plug
from Aru_RetopoTool.core import regions,patch_key
root=Path(__file__).resolve().parents[1];status=1
try:
    cmds.loadPlugin(str(root/'bin'/cmds.about(version=True)/'aru_retopo_mesh_buffer_inputcache.mll'))
    cmds.loadPlugin(str(root/'editor/curvenet/aru_retopo_guide_plugin.py'))
    guide=cmds.createNode('retopoGuideNode');p,s=polygon(5,height=1)
    cmds.setAttr(guide+'.netData',json.dumps(dict(positions=p,splines=s)),type='string')
    reference=cmds.polyPlane(w=12,h=12,sx=4,sy=4)[0]
    mesh,node=api.create(guide,reference,subdivisions=2)
    cmds.setAttr(node+'.selectedPatches',json.dumps([patch_key(r) for r in regions(p,s,lambda p:(0,1,0))]),type='string')
    native=backend.enable(node)
    def read(owner):return list(map(tuple,om.MFnMesh(plug(owner,'outMesh').asMObject()).getPoints()))
    def compare():
        a,b=read(native),read(node);assert a==b
        return a
    for mode in ('off','serial','parallel'):
        cmds.evaluationManager(mode=mode)
        for frame,height in ((1,0.),(2,.5),(3,-.3)):
            cmds.setKeyframe(reference,attribute='translateY',time=frame,value=height)
        for frame in (1,2,3,2,1):
            cmds.currentTime(frame);a=compare()
            assert max(abs(q[1]-cmds.getAttr(reference+'.translateY')) for q in a)<1.e-6
            cmds.setAttr(guide+'.controlPoints[0].xValue',frame*.01);compare()
        before=compare();cmds.move(0,.15,0,reference+'.vtx[*]',relative=True)
        assert compare()!=before;cmds.undo();assert compare()==before
    source=cmds.connectionInfo(native+'.referenceMesh',sourceFromDestination=True)
    cmds.disconnectAttr(source,native+'.referenceMesh')
    plug(native,'referenceMesh').setMObject(om.MFnMeshData().create())
    plug(native,'outPositions').asMObject();assert cmds.getAttr(native+'.status').startswith('ERROR:')
    cmds.connectAttr(source,native+'.referenceMesh');compare()
    for level in (1,3,2):
        cmds.setAttr(node+'.subdivisions',level);compare()
    print('PASS native input cache: reference animation, deform/Undo, invalid data recovery, subdivisions, DG/serial/parallel')
    status=0
except BaseException:traceback.print_exc()
finally:
    cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
