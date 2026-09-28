import os,sys,json,traceback
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import guides
from Aru_RetopoTool.editor.curvenet.relax_preview import RelaxPreview
from Aru_RetopoTool.tests import relax_owned_snapshot_candidate as candidate
status=1;restore=None
try:
    ref=cmds.polySphere(ch=False)[0];node=guides.create(ref)
    data={'positions':[[0,0,1],[.3,0,1],[.7,0,1],[1,0,1]],'splines':[[0,1,2,3]]}
    cmds.setAttr(node+'.netData',json.dumps(data),type='string')
    stats,restore=candidate.install()
    stroke=RelaxPreview(node)
    first,matrix=stroke._edit_world();stroke.write(first)
    def equal():
        expected,expected_matrix=stroke.world()
        actual,matrix=stroke._edit_world()
        assert actual.to_dict()==expected.to_dict()
        assert matrix==expected_matrix
        return actual
    assert equal() is stroke.pending
    assert stats['reused']==1
    # Returned public snapshots remain owned copies.
    public,_=stroke.world();public.positions[0][0]+=1
    assert public.positions!=stroke.pending.positions
    # External numeric writes must revoke the cache, even with equal sizes.
    values=[x for p in first.positions for x in p];values[0]+=.125
    cmds.setAttr(node+'.editPreviewPositions',values,type='doubleArray')
    assert not stroke._owned_preview_valid
    assert equal().positions[0][0]==values[0]
    # Restore our publication, then check nonidentity coordinate transforms.
    stroke.write(stroke.pending)
    parent=cmds.listRelatives(node,parent=True)[0]
    cmds.setAttr(parent+'.translateX',2)
    equal()
    cmds.setAttr(parent+'.translateX',0)
    assert equal() is stroke.pending
    # Connected preview input always follows upstream numeric data.
    source=cmds.createNode('network');cmds.addAttr(source,longName='positions',dataType='doubleArray')
    values[1]+=.2;cmds.setAttr(source+'.positions',values,type='doubleArray')
    cmds.connectAttr(source+'.positions',node+'.editPreviewPositions',force=True)
    assert not stroke._owned_preview_valid
    equal()
    values[2]+=.3;cmds.setAttr(source+'.positions',values,type='doubleArray');equal()
    cmds.disconnectAttr(source+'.positions',node+'.editPreviewPositions')
    stroke.cancel();assert stroke._owned_preview_callback is None
    assert not cmds.getAttr(node+'.editPreviewPositions')
    # A deleted node must still release the callback.
    stroke=RelaxPreview(node);stroke.write(stroke.world()[0]);cmds.delete(node)
    stroke.cancel();assert stroke._owned_preview_callback is None
    print('OWNED SNAPSHOT REUSE / EXTERNAL WRITE / TRANSFORM / CONNECTION / COPY / CANCEL / DELETE PASSED',stats)
    status=0
except BaseException:traceback.print_exc()
finally:
    if restore:restore()
    cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
