"""Exercise owned GPU display on the existing dense GUI scene."""
import json
from pathlib import Path
from maya import cmds
from Aru_RetopoTool import gpu_preview
from Aru_RetopoTool.gpu_buffer_preview import BufferPreview
from Aru_RetopoTool.editor.curvenet import gpu_guides
from Aru_RetopoTool.tests import gui_point_drag


def run():
    original_controls=gpu_guides.GPU_CONTROLS
    session=None
    try:
        session=BufferPreview(gpu_preview._override.foreground)
        assert session.shapes
        gpu_guides.GPU_CONTROLS=True
        gpu_preview._set_world_guides(True)
        cmds.refresh(force=True)
        gui_point_drag.run(numeric=True)
        report=json.loads(Path(gui_point_drag.__file__).with_suffix('.json').read_text())
        # The benchmark ends with a real Undo, which must close the GPU session.
        assert session.closed and not session.callbacks
        assert not cmds.ls(type='aruRetopoBufferPreview')
        assert cmds.getAttr('aruRetopoMesh1.visibility')
        report['session_closed_on_undo']=True
        Path(__file__).with_suffix('.json').write_text(json.dumps(report,indent=2))
    finally:
        if session:session.close()
        gpu_guides.GPU_CONTROLS=original_controls
        gpu_preview._set_world_guides(True)
        cmds.refresh(force=True)
