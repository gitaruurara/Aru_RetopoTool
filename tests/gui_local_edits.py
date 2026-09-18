"""Run only in a disposable, explicitly identified interactive Maya."""
import os,json,traceback,importlib,sys
from pathlib import Path
from unittest.mock import patch
from maya import cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
ROOT=Path(__file__).parent


def run(expected_pid):
    assert os.getpid()==expected_pid
    report={};messages=[]
    callback=om.MCommandMessage.addCommandOutputCallback(lambda message,kind,*a:messages.append(str(message)))
    try:
        from Aru_RetopoTool import patch_context,viewport_session,core,native,ui,native_backend
        cmds.setToolTo('selectSuperContext')
        if patch_context._active:patch_context._active.stop()
        viewport_session.stop();cmds.file(new=True,force=True)
        for name in ('aru_retopo_draw_plugin','aru_retopo_plan_plugin','aru_retopo_plugin'):
            if cmds.pluginInfo(name,q=True,loaded=True):cmds.unloadPlugin(name)
        for module in (native,core,native_backend):importlib.reload(module)
        from Aru_RetopoTool import local_fields,density,local_edit_runtime,local_edit_context,brush_context
        for module in (local_fields,density,local_edit_runtime,local_edit_context,brush_context,patch_context,ui):importlib.reload(module)
        from Aru_RetopoTool import guides,maya_api as api,qt
        from Aru_RetopoTool.editor.curvenet import curve_net_edit as edit,brush,curve_net_symmetry as sym
        from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData
        from Aru_RetopoTool.tests.test_core import network
        from Aru_RetopoTool.tests.mesh_assertions import mesh_fn
        sym.set_axis('');cmds.optionVar(iv=(local_edit_context.MODE,0))
        mesh=cmds.polyPlane(w=12,h=12,sx=12,sy=12,name='localEditReference')[0]
        p,s=network([(-2,0,-1),(0,0,-1),(2,0,-1),(-2,0,2),(0,0,2),(2,0,2)],[(0,1),(1,2),(3,4),(4,5),(0,3),(1,4),(2,5)])
        guide=guides.create(mesh);edit.RetopoGuideAccessor(guide).write(RetopoGuideData.from_dict(dict(positions=p,splines=s)))
        output,node=api.create(guide,mesh,subdivisions=3)
        plan=core.Plan(p,s,lambda p:(0,1,0),3);cmds.setAttr(node+'.selectedPatches',json.dumps(plan.region_keys),type='string')
        cmds.setAttr('persp.translate',0,10,8,type='double3');cmds.setAttr('perspShape.focalLength',35)
        aim=cmds.aimConstraint(mesh,'persp',aimVector=(0,0,-1),upVector=(0,1,0));cmds.delete(aim)
        viewport_session.start('modelPanel4');guides.edit(node);cmds.refresh(force=True)
        tool=patch_context._active;tool.timer.stop();view=omui.M3dView.active3dView();widget=qt.wrapInstance(int(view.widget()),qt.QWidget)
        def screen(point):
            x,y,_=view.worldToView(om.MPoint(*point));ratio=view.portWidth()/widget.width()
            return x,y,widget.mapToGlobal(qt.QPoint(round(x/ratio),round(widget.height()-y/ratio-1)))
        def event(kind,button,mods=qt.Qt.NoModifier):return qt.QMouseEvent(kind,qt.QPointF(10,10),button,button,mods)
        def capture(name):
            cmds.refresh(force=True);img=om.MImage();view.readColorBuffer(img,True);img.writeToFile(str(ROOT/name),'png')
        # Paint actual application event path, including native output and Undo.
        x,y,pos=screen((-1,0,.5));brush.set_radius(180)
        cmds.optionVar(iv=(local_edit_context.MODE,1));cmds.optionVar(fv=(local_edit_context.TARGET,1.))
        original=cmds.getAttr(node+'.influenceField') or ''
        with patch.object(qt.QCursor,'pos',return_value=pos):
            assert tool.eventFilter(widget,event(qt.QEvent.MouseButtonPress,qt.Qt.LeftButton))
            assert tool.local.stroke is not None
            with patch.object(qt.QCursor,'pos',return_value=pos+qt.QPoint(30,0)):
                assert tool.eventFilter(widget,event(qt.QEvent.MouseMove,qt.Qt.LeftButton))
            assert cmds.getAttr(node+'.influenceField')!=original
            tool.brush.update();capture('influence_paint_preview.png')
            assert tool.eventFilter(widget,event(qt.QEvent.MouseButtonRelease,qt.Qt.LeftButton))
        field=cmds.getAttr(node+'.influenceField');assert field and json.loads(field)
        cmds.undo();assert (cmds.getAttr(node+'.influenceField') or '')==original
        cmds.redo();assert cmds.getAttr(node+'.influenceField')==field
        report['paint_undo']=True
        cmds.optionVar(iv=(local_edit_context.MODE,0));cmds.optionVar(iv=(brush.SOFT,0))
        # Choose a point on an interior generated loop, away from guide boundaries.
        x,y,pos=screen((-1,0,.4));before=mesh_fn(output).numPolygons
        with patch.object(qt.QCursor,'pos',return_value=pos),patch.object(qt.QApplication,'keyboardModifiers',return_value=qt.Qt.ControlModifier):
            tool.tick(force=True)
            assert tool.key and tool.local.seed is not None,(tool.key,tool.local.reason)
            capture('density_hover.png')
            assert tool.eventFilter(widget,event(qt.QEvent.MouseButtonPress,qt.Qt.MiddleButton,qt.Qt.ControlModifier))
            assert tool.local.stroke is not None
            with patch.object(qt.QCursor,'pos',return_value=pos-qt.QPoint(35,0)):
                assert tool.eventFilter(widget,event(qt.QEvent.MouseMove,qt.Qt.MiddleButton,qt.Qt.ControlModifier))
            stroke=tool.local.stroke
            report['density_debug']={'type':str(type(stroke)),'count':getattr(stroke,'count',None),'candidates':len(getattr(stroke,'candidates',[])),'pending':getattr(stroke,'pending',None)}
            during=mesh_fn(output).numPolygons;assert during<before,(before,during)
            capture('density_drag_preview.png')
            assert tool.eventFilter(widget,event(qt.QEvent.MouseButtonRelease,qt.Qt.MiddleButton,qt.Qt.ControlModifier))
        cmds.undo();assert mesh_fn(output).numPolygons==before
        cmds.redo();assert mesh_fn(output).numPolygons==during
        report['density_undo']={'before':before,'after':during}
        # Mirrored paint and reduction use the same real event dispatch.
        cmds.setAttr(node+'.loopReductions','[]',type='string');cmds.setAttr(node+'.influenceField','{}',type='string')
        sym.set_axis('x');cmds.optionVar(iv=(local_edit_context.MODE,1))
        with patch.object(qt.QCursor,'pos',return_value=pos):
            assert tool.eventFilter(widget,event(qt.QEvent.MouseButtonPress,qt.Qt.LeftButton))
            assert tool.eventFilter(widget,event(qt.QEvent.MouseButtonRelease,qt.Qt.LeftButton))
        assert len(json.loads(cmds.getAttr(node+'.influenceField')))==2
        report['symmetric_paint']=True
        cmds.optionVar(iv=(local_edit_context.MODE,0))
        with patch.object(qt.QCursor,'pos',return_value=pos),patch.object(qt.QApplication,'keyboardModifiers',return_value=qt.Qt.ControlModifier):
            tool.tick(force=True)
            assert tool.eventFilter(widget,event(qt.QEvent.MouseButtonPress,qt.Qt.MiddleButton,qt.Qt.ControlModifier))
            with patch.object(qt.QCursor,'pos',return_value=pos-qt.QPoint(35,0)):
                assert tool.eventFilter(widget,event(qt.QEvent.MouseMove,qt.Qt.MiddleButton,qt.Qt.ControlModifier))
            assert tool.eventFilter(widget,event(qt.QEvent.MouseButtonRelease,qt.Qt.MiddleButton,qt.Qt.ControlModifier))
        assert mesh_fn(output).numPolygons==before-16
        report['symmetric_density']=True
        saved=cmds.getAttr(node+'.loopReductions')
        with patch.object(qt.QCursor,'pos',return_value=pos),patch.object(qt.QApplication,'keyboardModifiers',return_value=qt.Qt.ControlModifier):
            tool.tick(force=True)
            assert tool.eventFilter(widget,event(qt.QEvent.MouseButtonPress,qt.Qt.MiddleButton,qt.Qt.ControlModifier))
            with patch.object(qt.QCursor,'pos',return_value=pos-qt.QPoint(35,0)):
                assert tool.eventFilter(widget,event(qt.QEvent.MouseMove,qt.Qt.MiddleButton,qt.Qt.ControlModifier))
            assert tool.eventFilter(widget,qt.QKeyEvent(qt.QEvent.KeyPress,qt.Qt.Key_Escape,qt.Qt.NoModifier))
            assert tool.eventFilter(widget,event(qt.QEvent.MouseButtonRelease,qt.Qt.MiddleButton,qt.Qt.ControlModifier))
        assert cmds.getAttr(node+'.loopReductions')==saved
        report['density_cancel']=True
        # The restoration menu action must find loops initiated in the other patch too.
        tool.local.menu_key=tool.key;tool.local.menu_action('restore')
        assert mesh_fn(output).numPolygons==before
        cmds.undo();assert mesh_fn(output).numPolygons==before-16
        report['restore_menu_undo']=True
        # Rightward drag restores the selected direction, in one Undo.
        with patch.object(qt.QCursor,'pos',return_value=pos),patch.object(qt.QApplication,'keyboardModifiers',return_value=qt.Qt.ControlModifier):
            tool.tick(force=True)
            assert tool.eventFilter(widget,event(qt.QEvent.MouseButtonPress,qt.Qt.MiddleButton,qt.Qt.ControlModifier))
            with patch.object(qt.QCursor,'pos',return_value=pos+qt.QPoint(35,0)):
                assert tool.eventFilter(widget,event(qt.QEvent.MouseMove,qt.Qt.MiddleButton,qt.Qt.ControlModifier))
            assert tool.eventFilter(widget,event(qt.QEvent.MouseButtonRelease,qt.Qt.MiddleButton,qt.Qt.ControlModifier))
        assert mesh_fn(output).numPolygons==before
        cmds.undo();assert mesh_fn(output).numPolygons==before-16
        report['right_drag_restore']=True
        painted=cmds.getAttr(node+'.influenceField')
        tool.local.menu_action('reset_paint')
        assert json.loads(cmds.getAttr(node+'.influenceField'))=={}
        cmds.undo();assert cmds.getAttr(node+'.influenceField')==painted
        report['paint_reset_undo']=True
        cmds.optionVar(iv=(local_edit_context.MODE,1))
        with patch.object(qt.QCursor,'pos',return_value=pos):
            tool.eventFilter(widget,event(qt.QEvent.MouseButtonPress,qt.Qt.LeftButton))
            tool.eventFilter(widget,qt.QKeyEvent(qt.QEvent.KeyPress,qt.Qt.Key_Escape,qt.Qt.NoModifier))
            tool.eventFilter(widget,event(qt.QEvent.MouseButtonRelease,qt.Qt.LeftButton))
        assert cmds.getAttr(node+'.influenceField')==painted
        report['paint_cancel']=True
        cmds.optionVar(iv=(local_edit_context.MODE,0))
        # Right-click opens the local menu; thinning is undoable.
        sym.set_axis('');cmds.setAttr(node+'.loopReductions','[]',type='string')
        with patch.object(qt.QCursor,'pos',return_value=pos):
            tool.tick(force=True)
            assert tool.eventFilter(widget,event(qt.QEvent.MouseButtonPress,qt.Qt.RightButton))
        assert tool.local.menu and len(tool.local.menu.actions())==4
        tool.local.menu.hide();tool.timer.stop()
        tool.local.menu_action('alternate')
        assert mesh_fn(output).numPolygons<before
        cmds.undo();assert mesh_fn(output).numPolygons==before
        report['right_menu_thinning']=True
        # Reductions can be set on an unconfirmed preview without filling it.
        key=tool.key
        patch_context.confirm(node,key,remove=True)
        with patch.object(qt.QCursor,'pos',return_value=pos),patch.object(qt.QApplication,'keyboardModifiers',return_value=qt.Qt.ControlModifier):
            tool.tick(force=True)
            assert tool.local.seed is not None
            tool.eventFilter(widget,event(qt.QEvent.MouseButtonPress,qt.Qt.MiddleButton,qt.Qt.ControlModifier))
            with patch.object(qt.QCursor,'pos',return_value=pos-qt.QPoint(35,0)):
                tool.eventFilter(widget,event(qt.QEvent.MouseMove,qt.Qt.MiddleButton,qt.Qt.ControlModifier))
            tool.eventFilter(widget,event(qt.QEvent.MouseButtonRelease,qt.Qt.MiddleButton,qt.Qt.ControlModifier))
        assert key not in patch_context.selected(node)
        patch_context.confirm(node,key)
        assert mesh_fn(output).numPolygons==before-8
        report['unfilled_density_then_confirm']=True
        # Ctrl-MMB directly on the outer guide still starts extrusion.
        bx,by,bpos=screen((-2,0,.5))
        with patch.object(qt.QCursor,'pos',return_value=bpos),patch.object(qt.QApplication,'keyboardModifiers',return_value=qt.Qt.ControlModifier):
            tool.tick(force=True)
            tool.eventFilter(widget,event(qt.QEvent.MouseButtonPress,qt.Qt.MiddleButton,qt.Qt.ControlModifier))
            assert tool.local.stroke is None and tool.gesture is not None
            tool.eventFilter(widget,qt.QKeyEvent(qt.QEvent.KeyPress,qt.Qt.Key_Escape,qt.Qt.NoModifier))
            tool.eventFilter(widget,event(qt.QEvent.MouseButtonRelease,qt.Qt.MiddleButton,qt.Qt.ControlModifier))
        report['boundary_extrusion_priority']=True
        window=ui.RetopoWindow();assert window.parent() is not None
        # Real Qt menu/checkbox dispatch, not just direct menu_action calls.
        def click_control(control,point=None):
            point=point or control.rect().center()
            global_point=control.mapToGlobal(point)
            for kind,buttons in ((qt.QEvent.MouseButtonPress,qt.Qt.LeftButton),(qt.QEvent.MouseButtonRelease,qt.Qt.NoButton)):
                event=qt.QMouseEvent(kind,qt.QPointF(point),qt.QPointF(global_point),qt.Qt.LeftButton,buttons,qt.Qt.NoModifier)
                qt.QApplication.sendEvent(control,event)
        def escape_control(control):
            for kind in (qt.QEvent.KeyPress,qt.QEvent.KeyRelease):
                qt.QApplication.sendEvent(control,qt.QKeyEvent(kind,qt.Qt.Key_Escape,qt.Qt.NoModifier))
        window.node=node;window.guide.setText(guide)
        local_edit_context.set_painting(True)
        assert window.paint_influence.isChecked()
        saved_fields=cmds.getAttr(node+'.influenceField')
        with patch.object(qt.QCursor,'pos',return_value=pos):
            tool.tick(force=True)
            qt.QApplication.sendEvent(widget,event(qt.QEvent.MouseButtonPress,qt.Qt.RightButton))
            menu=tool.local.menu;assert menu is not None and menu.isVisible()
            # Popup input must never create another menu or paint beneath it.
            assert not tool.eventFilter(menu,event(qt.QEvent.MouseButtonPress,qt.Qt.RightButton))
            assert not tool.eventFilter(menu,event(qt.QEvent.MouseButtonPress,qt.Qt.LeftButton))
            assert tool.local.menu is menu and tool.local.stroke is None
            exit_action=menu.actions()[-1];assert exit_action.text()=='追従ペイントを終了'
            click_control(menu,menu.actionGeometry(exit_action).center())
        assert not local_edit_context.painting() and not window.paint_influence.isChecked()
        assert tool.local.menu is None and not any(w.objectName()=='AruRetopoLocalEditMenu' and w.isVisible() for w in qt.QApplication.topLevelWidgets())
        assert cmds.getAttr(node+'.influenceField')==saved_fields
        report['real_menu_exit_no_paint']=True
        # UI checkbox above viewport remains clickable; Escape also exits idle paint.
        local_edit_context.set_painting(True)
        with patch.object(qt.QCursor,'pos',return_value=pos):
            assert not tool.eventFilter(window.paint_influence,event(qt.QEvent.MouseButtonPress,qt.Qt.LeftButton))
            click_control(window.paint_influence)
        assert not local_edit_context.painting()
        local_edit_context.set_painting(True)
        qt.QApplication.sendEvent(widget,qt.QKeyEvent(qt.QEvent.KeyPress,qt.Qt.Key_Escape,qt.Qt.NoModifier))
        assert not local_edit_context.painting() and not window.paint_influence.isChecked()
        assert not local_edit_context.preview
        report['checkbox_and_escape_exit']=True
        # Repeated popup dismissals leave no visible menus; tool exit closes its menu.
        for i in range(3):
            with patch.object(qt.QCursor,'pos',return_value=pos):
                tool.tick(force=True)
                qt.QApplication.sendEvent(widget,event(qt.QEvent.MouseButtonPress,qt.Qt.RightButton))
            menu=tool.local.menu;assert menu is not None
            visible=[w for w in qt.QApplication.topLevelWidgets() if w.objectName()=='AruRetopoLocalEditMenu' and w.isVisible()]
            assert visible==[menu],len(visible)
            escape_control(menu)
            assert tool.local.menu is None and not any(w.objectName()=='AruRetopoLocalEditMenu' and w.isVisible() for w in qt.QApplication.topLevelWidgets())
        with patch.object(qt.QCursor,'pos',return_value=pos):
            tool.tick(force=True)
            qt.QApplication.sendEvent(widget,event(qt.QEvent.MouseButtonPress,qt.Qt.RightButton))
        menu=tool.local.menu;tool.local.close()
        assert tool.local.menu is None and not any(w.objectName()=='AruRetopoLocalEditMenu' and w.isVisible() for w in qt.QApplication.topLevelWidgets())
        report['popup_lifetime']=True
        window.close();window.deleteLater()
        tool.timer.start();report['passed']=True
    except Exception:report['error']=traceback.format_exc()
    om.MMessage.removeCallback(callback);report['messages']=messages[-15:]
    (ROOT/'gui_local_edits_report.json').write_text(json.dumps(report,indent=2))
