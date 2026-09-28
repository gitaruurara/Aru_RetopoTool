"""Interactive regressions; run only in the disposable diagnostic Maya."""
import json, os, traceback
from pathlib import Path
from maya import cmds
from Aru_RetopoTool import guides, patch_context, gpu_preview
ROOT = Path(__file__).parent

def run():
    assert os.getpid() == 51456
    report = {}
    try:
        guides.edit('aruRetopoGenerator1')
        tool = patch_context._active
        try:
            tool.rebuild()
            report['candidates'] = len(tool.candidates)
        except Exception:
            report['rebuild_error'] = traceback.format_exc()
        cmds.setToolTo('selectSuperContext')
        tool.tick()
        from Aru_RetopoTool.editor.curvenet import curve_net_menu
        curve_net_menu._enter_curvenet_context()
        report['resumed'] = bool(patch_context._active and patch_context._active.timer.isActive())
        report['generators'] = cmds.ls(type='aruRetopoMesh')
        report['previews'] = cmds.ls(type='aruRetopoBufferPreview')
    except Exception:
        report['error'] = traceback.format_exc()
    (ROOT/'gui_regressions_v9.json').write_text(json.dumps(report, indent=2))


def cameras():
    assert os.getpid() == 51456
    import math
    from Aru_RetopoTool.tests.gui_cylinder_occlusion import capture
    from Aru_RetopoTool import viewport_session
    viewport_session.refresh(); viewport_session.ensure_display()
    for label, position, focal in [('close',(3.5,1.,4.5),35.),('angle',(0.1,1.,6),35.),('far',(96,64,128),280.)]:
        cmds.setAttr('perspShape.orthographic',False)
        cmds.setAttr('perspShape.focalLength',focal)
        cmds.setAttr('persp.translate',*position,type='double3')
        constraint=cmds.aimConstraint('occlusionCylinder','persp',aimVector=(0,0,-1),upVector=(0,1,0),worldUpType='vector',worldUpVector=(0,1,0))
        cmds.delete(constraint)
        capture('regression_v9_'+label+'.png')


def reload_fixed():
    assert os.getpid() == 51456
    import importlib, __main__
    from Aru_RetopoTool import viewport_session, maya_api, ui
    from Aru_RetopoTool.editor.curvenet import curve_net_context, curve_net_menu
    cmds.setToolTo('selectSuperContext')
    if patch_context._active: patch_context._active.stop()
    viewport_session.stop()
    for module in (maya_api,patch_context,guides,curve_net_context,gpu_preview,ui): importlib.reload(module)
    __main__.__retopoGuideCtx__ = None
    viewport_session.start('modelPanel4')
    run()
    cameras()


def exercise():
    assert os.getpid() == 51456
    import importlib
    from unittest.mock import patch
    from types import SimpleNamespace
    import maya.api.OpenMaya as om
    import maya.api.OpenMayaUI as omui
    from Aru_RetopoTool import maya_api as api, ui, viewport_session
    from Aru_RetopoTool.editor.curvenet import curve_net_menu
    report={}
    try:
        generator='aruRetopoGenerator1'
        guide='aruRetopoGuideShape1'
        reference='occlusionCylinder'
        original=set(patch_context.selected(generator))
        from Aru_RetopoTool import preview_locator
        from Aru_RetopoTool.tests.mesh_assertions import face_count
        locator=preview_locator.shape(generator)
        locator_uuid=cmds.ls(locator,uuid=True)[0]
        output=cmds.listRelatives(locator,parent=True,fullPath=True)[0]
        mesh_count=len(cmds.ls(type='mesh'))
        count=face_count(output)
        cmds.setAttr('persp.translate',12,8,16,type='double3')
        cmds.setAttr('perspShape.focalLength',35.)
        constraint=cmds.aimConstraint(reference,'persp',aimVector=(0,0,-1),upVector=(0,1,0),worldUpType='vector',worldUpVector=(0,1,0))
        cmds.delete(constraint)
        for cycle in range(8):
            guides.edit(generator)
            tool=patch_context._active
            assert tool and tool.timer.isActive()
            cmds.setToolTo('selectSuperContext')
            assert patch_context._active is None
            curve_net_menu._enter_curvenet_context()
            tool=patch_context._active
            assert tool and tool.timer.isActive()
            tool.rebuild()
            view=omui.M3dView.active3dView()
            widget=patch_context.qt.wrapInstance(int(view.widget()),patch_context.qt.QWidget)
            target=None
            for key,_,_,triangles in tool.candidates:
                if not triangles:continue
                point=om.MPoint(*[sum(p[k] for p in triangles[:3])/3 for k in range(3)])
                x,y,visible=view.worldToView(point)
                if visible and 0<x<view.portWidth() and 0<y<view.portHeight():
                    tool.hover(x,y,view)
                    if tool.key:
                        ratio=view.portWidth()/widget.width()
                        target=widget.mapToGlobal(patch_context.qt.QPoint(round(x/ratio),round(widget.height()-y/ratio-1)))
                        break
            assert target is not None
            qt=patch_context.qt
            for remove in (True,False):
                event=SimpleNamespace(type=lambda:qt.QEvent.MouseButtonPress,
                    button=lambda:qt.Qt.MiddleButton,
                    modifiers=lambda:qt.Qt.ShiftModifier if remove else qt.Qt.NoModifier)
                with patch.object(qt.QCursor,'pos',return_value=target):
                    assert tool.eventFilter(widget,event), 'patch click not consumed'
                release=SimpleNamespace(type=lambda:qt.QEvent.MouseButtonRelease,button=lambda:qt.Qt.MiddleButton)
                assert tool.eventFilter(widget,release)
                faces=face_count(output)
                assert faces<count if remove else faces==count,(remove,faces,count)
            assert patch_context.selected(generator)==original
            cmds.undo();viewport_session.ensure_display()
            assert face_count(output)<count
            cmds.redo();viewport_session.ensure_display()
            assert face_count(output)==count
            viewport_session.refresh();viewport_session.ensure_display()
            assert cmds.ls(locator,uuid=True)[0]==locator_uuid
            assert len(cmds.ls(type='mesh'))==mesh_count
            assert not cmds.listRelatives(output,shapes=True,type='mesh')
            assert len(cmds.ls(type='aruRetopoMesh'))==1
            assert len(cmds.ls(type='aruRetopoBufferPreview'))==1
            cmds.select(guide)
            window=ui.RetopoWindow()
            assert window.node==generator
            window.node=None
            window.create()
            assert window.node==generator
            window.close();window.deleteLater()
        report['cycles']=8
        report['faces']=face_count(output)
        report['generators']=cmds.ls(type='aruRetopoMesh')
        report['previews']=cmds.ls(type='aruRetopoBufferPreview')
        report['fill_remove_undo']=True
    except Exception:report['error']=traceback.format_exc()
    (ROOT/'gui_exercise_v9.json').write_text(json.dumps(report,indent=2))


def locator_fixture():
    assert os.getpid()==51456
    import importlib, __main__
    from Aru_RetopoTool import viewport_session, maya_api, native_backend, preview_locator, ui
    from Aru_RetopoTool.editor.curvenet import curve_net_context
    cmds.setToolTo('selectSuperContext')
    if patch_context._active:patch_context._active.stop()
    viewport_session.stop()
    for module in (native_backend,preview_locator,maya_api,patch_context,guides,curve_net_context,gpu_preview,viewport_session,ui):importlib.reload(module)
    __main__.__retopoGuideCtx__=None
    from Aru_RetopoTool.tests import gui_depth_v8
    gui_depth_v8.fixture()
    exercise()
    cameras()


def saved_locator():
    assert os.getpid()==51456
    import importlib
    from Aru_RetopoTool import viewport_session, preview_locator, native_backend, maya_api
    from Aru_RetopoTool.tests import interactive_locator
    report={}
    try:
        cmds.setToolTo('selectSuperContext')
        viewport_session.stop()
        for module in (native_backend,maya_api,gpu_preview,viewport_session,interactive_locator):importlib.reload(module)
        locator=preview_locator.shape('aruRetopoGenerator1')
        uid=cmds.ls(locator,uuid=True)[0]
        path=str(ROOT/'locator_interactive_saved.ma')
        cmds.file(rename=path);cmds.file(save=True,type='mayaAscii',force=True)
        cmds.file(new=True,force=True);cmds.file(path,open=True,force=True)
        assert cmds.ls(locator,uuid=True)[0]==uid
        assert len(cmds.ls(type='mesh'))==1
        viewport_session.start('modelPanel4')
        report=interactive_locator.run('aruRetopoGenerator1',cycles=3)
        from Aru_RetopoTool.tests.gui_cylinder_occlusion import capture
        cmds.setAttr('perspShape.orthographic',True)
        cmds.setAttr('perspShape.orthographicWidth',4.)
        capture('locator_ortho_close.png')
        cmds.setAttr('perspShape.orthographic',False)
        cameras()
        report['save_reopen_uuid']=uid
    except Exception:report['error']=traceback.format_exc()
    (ROOT/'locator_interactive_final.json').write_text(json.dumps(report,indent=2))
