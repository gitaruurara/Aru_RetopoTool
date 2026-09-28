import os,sys,traceback
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import numpy as np
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit
from Aru_RetopoTool.tests import visibility_candidate as candidate
restore=candidate.install()
status=1
try:
    sphere=cmds.polySphere(r=3,sx=64,sy=32,ch=False)[0]
    other=cmds.polySphere(r=2,sx=32,sy=24,ch=False)[0]
    cmds.setAttr(other+'.translateZ',4)
    mesh=cmds.polyUnite(sphere,other,ch=False)[0]
    queries=np.random.default_rng(42).normal(size=(600,3))
    queries=queries/np.linalg.norm(queries,axis=1)[:,None]*3
    views=[((0,0,12),(0,0,-1),False),((10,4,8),(-1,0,-1),False),((0,0,12),(0,0,-1),True)]
    for stage in range(3):
        if stage==1:cmds.xform(mesh+'.vtx[0:80]',relative=True,translation=(.3,.2,-.5))
        if stage==2:cmds.setAttr(mesh+'.rotateY',37)
        for view in views:
            scalar=edit.make_visibility_test(mesh,view_info=view,use_acceleration=False)
            accelerated=edit.make_visibility_test(mesh,view_info=view)
            expected=[scalar(p) for p in queries]
            assert any(expected) and not all(expected)
            assert expected==[accelerated(p) for p in queries]
            assert expected==accelerated.many(queries.tolist())
            assert accelerated.many([])==[]
    assert candidate.native_calls>=9,candidate.native_calls
    print('VISIBILITY NATIVE PARITY / OCCLUSION / ORTHO / DEFORM / TRANSFORM PASSED',cmds.about(version=True))
    status=0
except BaseException:traceback.print_exc()
finally:
    restore()
    edit._invalidate_mesh_accel();cmds.file(new=True,force=True)
    maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
