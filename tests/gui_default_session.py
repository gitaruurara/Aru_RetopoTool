"""Default interactive display survives Undo/Redo/save without Undo pollution."""
import json,tempfile
from pathlib import Path
from maya import cmds
from Aru_RetopoTool import viewport_session,gpu_preview
from Aru_RetopoTool.editor.curvenet import gpu_guides

def run():
    node='aruRetopoGuideShape1';before=cmds.getAttr(node+'.outNetData')
    original_scene=cmds.file(q=True,sn=True);report={}
    marker=None
    try:
        viewport_session.start('modelPanel4')
        assert viewport_session.active() and gpu_guides.GPU_CONTROLS
        assert gpu_preview._buffer_session.shapes
        cmds.undoInfo(openChunk=True,chunkName='Viewport session Undo probe')
        try:marker=cmds.createNode('transform',name='aruViewportSessionUndoProbe')
        finally:cmds.undoInfo(closeChunk=True)
        cmds.undo();assert not cmds.objExists(marker)
        viewport_session.ensure_display();assert gpu_preview._buffer_session.shapes
        cmds.redo();assert cmds.objExists(marker)
        viewport_session.ensure_display();assert gpu_preview._buffer_session.shapes
        cmds.undo();assert not cmds.objExists(marker)
        viewport_session.ensure_display();assert gpu_preview._buffer_session.shapes
        report['undo_redo']=True
        with tempfile.TemporaryDirectory(prefix='aruViewportSession_') as folder:
            target=str(Path(folder)/'session.ma')
            cmds.file(rename=target)
            try:
                cmds.file(save=True,type='mayaAscii',force=True)
                assert b'createNode aruRetopoBufferPreview' not in Path(target).read_bytes()
            finally:cmds.file(rename=original_scene)
            viewport_session.ensure_display();assert gpu_preview._buffer_session.shapes
        report['save_resume']=True
        assert cmds.getAttr(node+'.outNetData')==before
        report['guide_unchanged']=True
        viewport_session.stop()
        assert not cmds.ls(type='aruRetopoBufferPreview')
        assert cmds.getAttr('aruRetopoMesh1Shape.visibility')
        report['stop_cleanup']=True
        viewport_session.start('modelPanel4')
        cmds.refresh(force=True)
        report['active_for_user']=viewport_session.active()
    except BaseException:
        import traceback
        report['error']=traceback.format_exc()
        viewport_session.stop()
    finally:
        Path(__file__).with_suffix('.json').write_text(json.dumps(report,indent=2))
