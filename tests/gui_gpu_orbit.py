"""Scripted camera orbit stability check; not a physical mouse test."""
import json,time,statistics
from pathlib import Path
from unittest.mock import patch
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import gpu_preview
from Aru_RetopoTool.gpu_buffer_preview import BufferPreview
from Aru_RetopoTool.editor.curvenet import gpu_guides


def run():
    camera=cmds.modelPanel('modelPanel4',q=True,camera=True)
    if cmds.nodeType(camera)=='camera':camera=cmds.listRelatives(camera,parent=True,fullPath=True)[0]
    before=cmds.xform(camera,q=True,ws=True,matrix=True)
    selection=om.MSelectionList();selection.add(camera)
    camera_fn=om.MFnTransform(selection.getDagPath(0))
    local_before=camera_fn.transformation()
    source=cmds.getAttr('aruRetopoGuideShape1.outNetData')
    controls=gpu_guides.GPU_CONTROLS;session=None;rows=[];calls=[]
    old_positions=gpu_guides.positions
    def sample(owner):
        calls.append(1)
        return old_positions(owner)
    try:
        session=BufferPreview(gpu_preview._override.foreground)
        assert session.shapes
        gpu_guides.GPU_CONTROLS=True;gpu_preview._set_world_guides(True);cmds.refresh(force=True)
        with patch.object(gpu_guides,'positions',sample):
            for i in range(60):
                start=time.perf_counter()
                cmds.orbit(camera,horizontalAngle=1.,verticalAngle=.1)
                cmds.refresh(force=True)
                rows.append((time.perf_counter()-start)*1000)
        changed=cmds.xform(camera,q=True,ws=True,matrix=True)!=before
        camera_fn.setTransformation(local_before)
        session.close()
        assert changed
        assert all(abs(a-b)<1e-10 for a,b in zip(before,cmds.xform(camera,q=True,ws=True,matrix=True)))
        assert cmds.getAttr('aruRetopoGuideShape1.outNetData')==source
        assert session.closed and not cmds.ls(type='aruRetopoBufferPreview')
        Path(__file__).with_suffix('.json').write_text(json.dumps(dict(frames=len(rows),median_ms=statistics.median(rows[1:]),max_ms=max(rows),geometry_resamples=len(calls),camera_restored=True,guide_restored=True,session_closed=True),indent=2))
    finally:
        try:
            camera_fn.setTransformation(local_before)
        finally:
            if session:session.close()
            gpu_guides.GPU_CONTROLS=controls;gpu_preview._set_world_guides(True);cmds.refresh(force=True)
