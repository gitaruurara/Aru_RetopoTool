"""Final-position snapshot parity with legacy plug reads and live drivers."""
from unittest.mock import patch
from types import SimpleNamespace
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
import maya.OpenMaya as om1
from maya import cmds
from Aru_RetopoTool.editor.curvenet import curve_net_node as node
from Aru_RetopoTool.tests.curve_edit_features import fixture


def legacy_values(plug):
    return {plug.elementByPhysicalIndex(i).logicalIndex(): tuple(
        plug.elementByPhysicalIndex(i).child(k).asDouble() for k in range(3))
        for i in range(plug.evaluateNumElements())}


def run():
    _, guide, _, positions, splines = fixture()
    selection = om1.MSelectionList(); selection.add(guide)
    obj = om1.MObject(); selection.getDependNode(0, obj)
    shape = SimpleNamespace(thisMObject=lambda:obj,
        _getNetData=lambda:RetopoGuideData.from_json(cmds.getAttr(guide+'.netData')))
    shape._computeFinalPositions = lambda:node.RetopoGuideNode._computeFinalPositions(shape)
    driver = cmds.createNode('addDoubleLinear')
    cmds.connectAttr(driver+'.output', guide+'.controlPoints[0].xValue')
    handle = splines[0][1]
    cmds.setAttr(guide+'.controlPoints[%d]' % handle, .2, -.1, .3, type='double3')
    cmds.setAttr(guide+'.controlPoints[999]', 3, 4, 5, type='double3')
    for value in (0., .5, -.8, 1.4):
        cmds.setAttr(driver+'.input1',value)
        actual = shape._computeFinalPositions()
        with patch.object(node, 'double3_array_values', legacy_values):
            expected = shape._computeFinalPositions()
        assert actual == expected, (actual, expected)
        assert actual[0][0] == positions[0][0]+value
        cmds.undo()
        actual = shape._computeFinalPositions()
        with patch.object(node, 'double3_array_values', legacy_values):
            assert actual == shape._computeFinalPositions()
        cmds.redo()
    print('PASS final positions: sparse/out-of-range CP, connected EP, manual handle, Undo/Redo')
