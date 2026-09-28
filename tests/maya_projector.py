"""Exact bulk/intersector parity and dirty-cache lifetime checks in mayapy."""
import os,sys,traceback
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import numpy as np
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit,maya_projector

def check(mesh):
    fn,dag=edit._get_mesh_fn(mesh)
    queries=np.random.default_rng(73).normal(size=(600,3))*4
    expected=np.array([edit._closest_point_pos_only(fn,p) for p in queries])
    actual=np.array(maya_projector.points(fn,queries))
    assert np.array_equal(expected,actual),float(np.max(np.abs(expected-actual)))
    buffer=maya_projector.points_array(fn,queries)
    assert buffer.dtype==np.float64 and buffer.flags.c_contiguous
    assert np.array_equal(buffer,expected)
    buffer[0]=999
    assert np.array_equal(maya_projector.points_array(fn,queries),expected),'Returned array aliases cached output'
    assert maya_projector.points_array(fn,[]).shape==(0,3)
    assert maya_projector._CACHE,'Test must exercise native path, not fallback'
    hits=maya_projector.surface_hits(fn,queries)
    for query,(position,normal,face,bary) in zip(queries,hits):
        expected_position,expected_face,expected_bary=edit._closest_point_on_mesh(fn,dag,query)
        assert position==expected_position and face==expected_face
        assert normal==edit._get_normal_at_point(fn,query)
        assert [row[0] for row in bary]==[row[0] for row in expected_bary]
        assert max(abs(a[1]-b[1]) for a,b in zip(bary,expected_bary))<1e-12
    assert maya_projector.surface_hits(fn,[])==[]


status=1
try:
    mesh=cmds.polySphere(sx=16,sy=12,ch=False,name='bulkProjectionTest')[0]
    check(mesh)
    cmds.setAttr(mesh+'.translate',1.2,-.3,2.1,type='double3')
    cmds.setAttr(mesh+'.rotate',12,37,-9,type='double3')
    cmds.setAttr(mesh+'.scale',-1.5,.8,2.3,type='double3')
    check(mesh)
    cmds.xform(mesh+'.vtx[5]',translation=(.5,.7,.1),relative=True)
    check(mesh)
    cmds.delete(mesh)
    replacement=cmds.polyCube(ch=False,name='bulkProjectionTest')[0]
    check(replacement)
    maya_projector.clear();edit._invalidate_mesh_accel()
    print('BULK MAYA PROJECTOR PARITY / TRANSFORM / DEFORM / DELETE-RECREATE PASSED',cmds.about(version=True))
    status=0
except BaseException:traceback.print_exc()
finally:
    maya_projector.clear();edit._invalidate_mesh_accel()
    cmds.file(new=True,force=True)
    maya.standalone.uninitialize()
    sys.stdout.flush();sys.stderr.flush()
    os._exit(status)
