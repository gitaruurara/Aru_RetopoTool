"""Compaction draws only after CP restoration and trimming, with one Undo."""
from unittest.mock import patch
from maya import cmds
from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData


def run():
    cn=RetopoGuideData.from_dict({'positions':[[0,0,0],[1,0,0],[2,0,0],[3,0,0],[9,0,0]],'splines':[(0,1,2,3)]})
    guide=cmds.createNode('retopoGuideNode')
    cmds.setAttr(guide+'.netData',cn.to_json(),type='string')
    cmds.setAttr(guide+'.controlPoints[3]',.2,.3,0,type='double3')
    cmds.setAttr(guide+'.controlPoints[4]',.1,0,0,type='double3')
    before=cmds.getAttr(guide+'.netData');draws=[]
    def drawn():
        draws.append((len(RetopoGuideData.from_json(cmds.getAttr(guide+'.netData')).positions),
                      cmds.getAttr(guide+'.controlPoints[3]')[0],
                      cmds.getAttr(guide+'.controlPoints',multiIndices=True)))
    cmds.undoInfo(openChunk=True,chunkName='Retopo compact redraw test')
    try:
        with patch.object(edit,'_dirty_shape_view',side_effect=drawn):
            count,remap=edit.prune_orphan_cvs_and_write(guide,cn)
        assert count==1 and remap=={0:0,1:1,2:2,3:3}
        assert len(draws)==1 and draws[0][0]==4
        assert draws[0][1]==(.2,.3,0.)
        assert all(i<4 for i in draws[0][2])
    finally:cmds.undoInfo(closeChunk=True)
    cmds.undo()
    assert cmds.getAttr(guide+'.netData')==before
    assert cmds.getAttr(guide+'.controlPoints[4]')[0]==(.1,0.,0.)
    cmds.delete(cmds.listRelatives(guide,parent=True)[0])
    print('PASS compact commit renders once after CP restore/trim and preserves Undo')
