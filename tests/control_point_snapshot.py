"""Sparse, connected, locked and undoable control-point snapshots."""
import maya.api.OpenMaya as om
from maya import cmds
from Aru_RetopoTool.maya_data import double3_array_values
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit
from Aru_RetopoTool import maya_api as api
from Aru_RetopoTool.tests.curve_edit_features import fixture

def run():
    node=cmds.createNode('network')
    cmds.addAttr(node,longName='vectors',attributeType='double3',multi=True)
    for name in ('vx','vy','vz'):cmds.addAttr(node,longName=name,attributeType='double',parent='vectors')
    plug=om.MFnDependencyNode(om.MSelectionList().add(node).getDependNode(0)).findPlug('vectors',False)
    assert double3_array_values(plug)=={}
    cmds.setAttr(node+'.vectors[2]',.1,.2,.3,type='double3')
    cmds.setAttr(node+'.vectors[17]',-.1,-.2,-.3,type='double3')
    driver=cmds.createNode('addDoubleLinear');cmds.connectAttr(driver+'.output',node+'.vectors[17].vy')
    for value in (.7,-.6,1.2):
        cmds.setAttr(driver+'.input1',value)
        values=double3_array_values(plug)
        assert set(values)=={2,17}
        assert tuple(values[17])==(-.1,value,-.3),values
        assert cmds.getAttr(node+'.vectors',multiIndices=True)==[2,17]
    cmds.delete(driver,node)
    mesh,guide,owner,_,_=fixture()
    cmds.setAttr(guide+'.controlPoints[2]',.2,.3,.4,type='double3')
    cmds.setAttr(guide+'.controlPoints[5]',-.2,-.3,-.4,type='double3')
    cmds.setAttr(guide+'.controlPoints[5].xValue',lock=True)
    with api.undo_chunk('snapshot reset'):edit._reset_control_points(guide,6)
    assert cmds.getAttr(guide+'.controlPoints[2]')[0]==(0.,0.,0.)
    assert cmds.getAttr(guide+'.controlPoints[5].xValue')==-.2
    cmds.undo();assert cmds.getAttr(guide+'.controlPoints[2]')[0]==(.2,.3,.4)
    cmds.redo();assert cmds.getAttr(guide+'.controlPoints[2]')[0]==(0.,0.,0.)
    print('PASS empty/sparse double3 snapshot, fresh connected values, locked reset and Undo/Redo')
