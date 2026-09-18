"""Diagnostic Maya only: scripted pointer input through real editing handlers."""
import json, os, traceback, importlib, sys
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
from maya import cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
ROOT=Path(__file__).parent


def run(expected_pid):
    assert os.getpid()==expected_pid, "Use only a disposable diagnostic Maya"
    report={}
    from Aru_RetopoTool import guides,patch_context,viewport_session,qt,brush_context
    from Aru_RetopoTool.editor.curvenet import curve_net_context as context,curve_net_edit as edit,curve_net_symmetry as sym,brush,soft_move,symmetry_constraints
    from Aru_RetopoTool import maya_api as api
    import __main__
    try:
        cmds.setToolTo('selectSuperContext')
        if patch_context._active:patch_context._active.stop()
        viewport_session.stop()
        for mod in (brush,soft_move,symmetry_constraints,edit,context,brush_context,patch_context):importlib.reload(mod)
        __main__.__retopoGuideCtx__=None
        cmds.file(new=True,force=True)
        if cmds.pluginInfo('aru_retopo_draw_plugin',q=True,loaded=True):
            cmds.unloadPlugin('aru_retopo_draw_plugin')
        sym.set_axis('');sym.set_space('world')
        mesh=cmds.polyPlane(w=12,h=12,sx=12,sy=12,name='brushReference')[0]
        from Aru_RetopoTool.tests.test_core import network
        from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
        pts,splines=network([(-2,0,0),(0,0,0),(2,0,0),(-2,0,2),(0,0,2),(2,0,2)],[(0,1),(1,2),(3,4),(4,5),(0,3),(1,4),(2,5)])
        guide=guides.create(mesh)
        edit.RetopoGuideAccessor(guide).write(RetopoGuideData.from_dict(dict(positions=pts,splines=splines)))
        output,node=api.create(guide,mesh)
        from Aru_RetopoTool import core
        keys=[core.patch_key(loop) for loop in core.regions(pts,splines,lambda p:(0,1,0))]
        cmds.setAttr(node+'.selectedPatches',json.dumps(keys),type='string')
        cmds.setAttr('persp.translate',0,10,8,type='double3')
        cmds.setAttr('perspShape.focalLength',35)
        aim=cmds.aimConstraint(mesh,'persp',aimVector=(0,0,-1),upVector=(0,1,0));cmds.delete(aim)
        viewport_session.start('modelPanel4');guides.edit(node);cmds.refresh(force=True)
        tool=patch_context._active;tool.timer.stop()
        ctx=__main__.__retopoGuideCtx__
        view=omui.M3dView.active3dView();widget=qt.wrapInstance(int(view.widget()),qt.QWidget)
        x,y,_=view.worldToView(om.MPoint(0,0,0))
        scale=view.portWidth()/widget.width()
        pos=widget.mapToGlobal(qt.QPoint(round(x/scale),round(widget.height()-y/scale-1)))
        raw=cmds.getAttr(guide+'.netData');filled=cmds.getAttr(node+'.selectedPatches')
        brush.set_radius(220)
        def key(kind,k,mods=qt.Qt.NoModifier):return qt.QKeyEvent(kind,k,mods)
        def mouse(kind,button=qt.Qt.MiddleButton,mods=qt.Qt.NoModifier):
            return qt.QMouseEvent(kind,qt.QPointF(10,10),button,button,mods)
        cmds.setFocus('modelPanel4')
        with patch.object(qt.QCursor,'pos',return_value=pos):
            assert tool.brush.viewport_focus(),'Real Maya panel focus rejected'
            assert tool.eventFilter(widget,key(qt.QEvent.KeyPress,qt.Qt.Key_B))
            assert tool.eventFilter(widget,mouse(qt.QEvent.MouseButtonPress))
            with patch.object(qt.QCursor,'pos',return_value=pos+qt.QPoint(60,0)):
                assert tool.eventFilter(widget,mouse(qt.QEvent.MouseMove))
            assert brush.radius()>250
            assert tool.eventFilter(widget,mouse(qt.QEvent.MouseButtonRelease))
            assert tool.eventFilter(widget,key(qt.QEvent.KeyRelease,qt.Qt.Key_B,qt.Qt.ControlModifier))
            assert not tool.brush.b and not tool.brush.consume_release
            assert not tool.eventFilter(widget,key(qt.QEvent.KeyPress,qt.Qt.Key_B,qt.Qt.AltModifier))
            # Escape restores the radius while consuming the rest of the stroke.
            before=brush.radius()
            assert tool.eventFilter(widget,key(qt.QEvent.KeyPress,qt.Qt.Key_B))
            assert tool.eventFilter(widget,mouse(qt.QEvent.MouseButtonPress))
            with patch.object(qt.QCursor,'pos',return_value=pos+qt.QPoint(50,0)):
                assert tool.eventFilter(widget,mouse(qt.QEvent.MouseMove))
            assert tool.eventFilter(widget,key(qt.QEvent.KeyPress,qt.Qt.Key_Escape))
            assert brush.radius()==before
            assert tool.eventFilter(widget,mouse(qt.QEvent.MouseButtonRelease))
            assert tool.eventFilter(widget,key(qt.QEvent.KeyRelease,qt.Qt.Key_B))
        assert cmds.getAttr(guide+'.netData')==raw and cmds.getAttr(node+'.selectedPatches')==filled
        with patch.object(qt.QCursor,'pos',return_value=pos):
            assert tool.eventFilter(widget,key(qt.QEvent.KeyPress,qt.Qt.Key_B))
            tool.brush.event(qt.QEvent(qt.QEvent.ApplicationDeactivate))
            assert not tool.brush.b and not tool.brush.consume_release
        with patch.object(tool.brush,'viewport_focus',return_value=False):
            assert not tool.brush.event(key(qt.QEvent.KeyPress,qt.Qt.Key_B))
        report['resize_no_geometry_changes']=True
        cmds.optionVar(iv=(brush.SOFT,1));brush.set_radius(400)
        point=[x,y,0]
        with patch.object(cmds,'draggerContext',side_effect=lambda *a,**k:2 if k.get('button') else point),patch.object(cmds,'getModifiers',return_value=0):
            ctx.press()
            move=context._state_get(ctx._s,'soft_move')
            assert move is not None,'MMB press did not start soft EP movement'
            assert len(move.weights)>1,move.weights
            point[0]+=35;point[1]+=15
            ctx._drag_impl()
            assert cmds.getAttr(guide+'.netData')==raw,'numeric preview should not write data during drag'
            assert cmds.getAttr(guide+'.editPreviewPositions')
            ctx.release()
        final=edit.RetopoGuideAccessor(guide).read()
        assert len(final.splines)==len(splines) and len(final.positions)==len(pts)
        changed=[i for i in final.endpoint_indices() if sum((final.positions[i][k]-pts[i][k])**2 for k in range(3))>1e-8]
        assert len(changed)>1,changed
        assert all(abs(final.positions[i][1])<1e-6 for i in final.endpoint_indices())
        assert cmds.getAttr(node+'.selectedPatches')==filled
        committed=cmds.getAttr(guide+'.netData')
        cmds.undo();assert cmds.getAttr(guide+'.netData')==raw
        cmds.redo();assert cmds.getAttr(guide+'.netData')==committed
        report['soft_real_press_drag_release']={'weights':move.weights,'moved':changed,'undo_redo':True}
        # Cancel uses the same event path, and release must not commit afterward.
        ep=final.positions[1];cx,cy,_=view.worldToView(om.MPoint(*ep));point[:]=[cx,cy,0]
        with patch.object(cmds,'draggerContext',side_effect=lambda *a,**k:2 if k.get('button') else point),patch.object(cmds,'getModifiers',return_value=0):
            ctx.press();point[0]+=10;ctx._drag_impl()
            assert tool.eventFilter(widget,key(qt.QEvent.KeyPress,qt.Qt.Key_Escape))
            ctx.release()
        assert cmds.getAttr(guide+'.netData')==committed
        report['escape_cancel']=True
        with patch.object(qt.QCursor,'pos',return_value=pos):
            tool.brush.last=None;tool.brush.update()
            assert brush_context.display,'no brush draw payload'
            cmds.refresh(force=True)
            image=om.MImage();view.readColorBuffer(image,True);image.writeToFile(str(ROOT/'brush_preview.png'),'png')
        report['brush_payload']=len(brush_context.display)
        cmds.optionVar(iv=(brush.SOFT,0))
        from Aru_RetopoTool.tests.interactive_locator import run as lifecycle
        report['tool_switches']=lifecycle(node,cycles=2)
        # Keep the test scene ready for trying the new interaction.
        guides.edit(node);cmds.optionVar(iv=(brush.SOFT,1))
        from Aru_RetopoTool import ui
        importlib.reload(ui)
        window=ui.RetopoWindow()
        assert window.parent() is not None
        assert window.soft_move.isChecked() and window.connect_radius.value()==round(brush.snap_radius())
        window.close();window.deleteLater()
        report['passed']=True
    except Exception:report['error']=traceback.format_exc()
    (ROOT/'interactive_brush_report.json').write_text(json.dumps(report,indent=2))
