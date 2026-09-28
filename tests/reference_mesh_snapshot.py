"""Dirty-input snapshot parity for deformation, topology, connections and Undo."""
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import maya_api as api
from Aru_RetopoTool.maya_data import ReferenceMeshSnapshot,plug_handle
from Aru_RetopoTool.tests.curve_edit_features import fixture

def run():
    mesh,guide,node,_,_=fixture()
    plug=om.MFnDependencyNode(om.MSelectionList().add(node).getDependNode(0)).findPlug('referenceMesh',False)
    cache=ReferenceMeshSnapshot(plug)
    def expected():
        with plug_handle(plug) as handle:
            fn=om.MFnMesh(handle.asMeshTransformed());_,tri=fn.getTriangles()
            return tuple((p.x,p.y,p.z) for p in fn.getPoints()),tuple(tri)
    def check():
        actual=cache.read();assert actual==expected()
        # Allow a conservative second read if evaluation itself dirtied input.
        stable=cache.read();assert cache.read() is stable
        return stable
    try:
        original=check()
        for delta in (.1,.2,-.3):
            with api.undo_chunk('snapshot vertex'):
                cmds.move(0,delta,0,mesh+'.vtx[0]',relative=True)
            assert check()!=original
            cmds.undo();assert check()==original
            cmds.redo();check();cmds.undo();check()
        cmds.setAttr(mesh+'.translateX',2.);assert check()!=original
        cmds.setAttr(mesh+'.translateX',0.);assert check()==original
        history=cmds.ls(cmds.listHistory(mesh),type='polyPlane')[0]
        cmds.setAttr(history+'.subdivisionsWidth',5);assert len(check()[0])!=len(original[0])
        other=cmds.polySphere(r=2,sx=8,sy=4)[0]
        shape=cmds.listRelatives(other,shapes=True,fullPath=True)[0]
        with api.undo_chunk('snapshot reconnect'):
            cmds.connectAttr(shape+'.worldMesh[0]',node+'.referenceMesh',force=True)
        swapped=check();cmds.undo();assert check()!=swapped
        cmds.redo();assert check()==swapped
        assert cache.callback is not None
    finally:cache.close()
    assert cache.callback is None and cache.cached is None
    print('PASS reference snapshot dirty propagation, repeated deformations, transform, topology, reconnect, Undo/Redo and cleanup')
