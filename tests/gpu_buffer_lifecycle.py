"""Disposable persistent GPU locator lifecycle checks (no viewport timing)."""
import os, json, tempfile, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
os.environ['MAYA_SKIP_USERSETUP_PY']='1'
if __name__ == '__main__':
    import maya.standalone
    maya.standalone.initialize(name='python')
from maya import cmds
from Aru_RetopoTool import guides, maya_api as api, preview_locator, patch_context, core
from Aru_RetopoTool.tests.test_core import polygon
from Aru_RetopoTool.tests.mesh_assertions import face_count


def run():
    cmds.undoInfo(state=True)
    reference=cmds.polyPlane(w=10,h=10)[0]
    guide=guides.create(reference)
    points,splines=polygon(4,height=1)
    cmds.setAttr(guide+'.netData',json.dumps(dict(positions=points,splines=splines)),type='string')
    output,node=api.create(guide,reference)
    locator=preview_locator.shape(node)
    uid=cmds.ls(locator,uuid=True)[0]
    keys=core.regions(points,splines,lambda p:(0,1,0))
    patch_context.confirm(node,core.patch_key(keys[0]))
    assert face_count(output)==16
    for _ in range(5):
        assert preview_locator.ensure(node)==locator
        assert cmds.ls(locator,uuid=True)[0]==uid
        assert len(cmds.ls(type=preview_locator.TYPE))==1
        assert not cmds.listRelatives(output,shapes=True,type='mesh')
    cmds.createNode('transform',name='lifecycleMarker')
    cmds.undo();assert cmds.ls(locator,uuid=True)[0]==uid
    cmds.redo();assert cmds.ls(locator,uuid=True)[0]==uid
    baked=api.bake(node)
    assert face_count(baked)==16
    assert len(cmds.ls(type='mesh'))==2
    cmds.undo();assert not cmds.objExists(baked)
    cmds.redo();assert face_count(baked)==16
    assert cmds.ls(locator,uuid=True)[0]==uid
    with tempfile.TemporaryDirectory() as directory:
        filename=str(Path(directory)/'locator.ma')
        cmds.file(rename=filename);cmds.file(save=True,type='mayaAscii',force=True)
        assert Path(filename).read_text(encoding='utf-8').count('createNode aruRetopoBufferPreview')==1
        cmds.file(new=True,force=True)
        assert not cmds.ls(type=preview_locator.TYPE)
        cmds.file(filename,open=True,force=True)
        assert preview_locator.shape(node)==locator
        assert cmds.ls(locator,uuid=True)[0]==uid
        assert face_count(output)==16
        assert not cmds.listRelatives(output,shapes=True,type='mesh')
        assert len(cmds.ls(type=preview_locator.TYPE))==1
    print('PASS persistent locator: reuse, Undo/Redo, bake, save, reopen, new')


if __name__=='__main__':
    result=0
    try:run()
    except Exception:
        import traceback
        traceback.print_exc();result=1
    finally:
        cmds.file(new=True,force=True)
        maya.standalone.uninitialize()
    sys.stdout.flush();sys.stderr.flush();os._exit(result)
