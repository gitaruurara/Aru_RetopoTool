"""Internal serialized geometry remains writable/undoable without an AE field."""
from maya import cmds
from Aru_RetopoTool.tests.curve_edit_features import fixture
from Aru_RetopoTool import maya_api as api
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit

def run():
    _,guide,_,_,_=fixture()
    assert cmds.attributeQuery('netData',node=guide,hidden=True)
    assert not cmds.attributeQuery('curveColor',node=guide,hidden=True)
    assert not cmds.attributeQuery('meshName',node=guide,hidden=True)
    before=cmds.getAttr(guide+'.netData')
    accessor=edit.RetopoGuideAccessor(guide);cn=accessor.read();cn.positions[0][0]+=.1
    with api.undo_chunk('hidden serialized guide edit'):accessor.write(cn)
    after=cmds.getAttr(guide+'.netData');assert before!=after
    cmds.undo();assert cmds.getAttr(guide+'.netData')==before
    cmds.redo();assert cmds.getAttr(guide+'.netData')==after
    assert cmds.getAttr(guide+'.outNetData')
    print('PASS hidden serialized data remains editable, evaluable and Undo/Redo-safe')
