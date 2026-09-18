"""Run on a disposable scene with a visible, filled retopo patch.

Exercises actual hover/raycast and event handlers with scripted pointer positions;
this is not a physical mouse latency test. No new scene is opened by this test.
"""
from maya import cmds
from Aru_RetopoTool import guides, patch_context

def run(generator, cycles=8):
    assert not cmds.about(batch=True), "Run in a disposable interactive Maya scene"
    from unittest.mock import patch
    from types import SimpleNamespace
    import maya.api.OpenMaya as om
    import maya.api.OpenMayaUI as omui
    from Aru_RetopoTool import maya_api as api, ui, viewport_session
    from Aru_RetopoTool.editor.curvenet import curve_net_menu
    report={}
    guide=cmds.listConnections(generator+'.guideData',s=True,d=False,shapes=True)[0]
    original=set(patch_context.selected(generator))
    from Aru_RetopoTool import preview_locator
    from Aru_RetopoTool.tests.mesh_assertions import face_count
    locator=preview_locator.shape(generator)
    locator_uuid=cmds.ls(locator,uuid=True)[0]
    output=cmds.listRelatives(locator,parent=True,fullPath=True)[0]
    mesh_count=len(cmds.ls(type='mesh'))
    preview_count=len(cmds.ls(type='aruRetopoBufferPreview'))
    count=face_count(output)
    for cycle in range(cycles):
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
        assert cmds.objExists(generator)
        assert len(cmds.ls(type='aruRetopoBufferPreview'))==preview_count
        cmds.select(guide)
        window=ui.RetopoWindow()
        assert window.node==generator
        window.node=None
        window.create()
        assert window.node==generator
        window.close();window.deleteLater()
    report['cycles']=cycles
    report['faces']=face_count(output)
    report['generators']=cmds.ls(type='aruRetopoMesh')
    report['previews']=cmds.ls(type='aruRetopoBufferPreview')
    report['fill_remove_undo']=True
    return report
