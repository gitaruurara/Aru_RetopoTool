"""B+MMB brush resizing and draw-only influence feedback in the combined tool."""
import math
from maya import cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
from . import qt, maya_api as api
from .editor.curvenet import brush

display={}


class Interaction:
    def __init__(self,tool):
        self.tool=tool;self.b=False;self.resizing=None;self.consume_release=False;self.last=None

    def close(self):
        self.b=False;self.resizing=None;self.consume_release=False;self.last=None
        display.clear()

    def mouse(self):
        view=omui.M3dView.active3dView()
        widget=qt.wrapInstance(int(view.widget()),qt.QWidget)
        point=widget.mapFromGlobal(qt.QCursor.pos())
        if not widget.rect().contains(point):return None
        scale=view.portWidth()/max(1,widget.width())
        return view,point.x()*scale,(widget.height()-point.y()-1)*scale

    def context(self):
        import __main__
        return getattr(__main__,'__retopoGuideCtx__',None)

    def viewport_focus(self):
        mouse=self.mouse()
        if not mouse:return False
        widget=qt.wrapInstance(int(mouse[0].widget()),qt.QWidget)
        focus=qt.QApplication.focusWidget()
        if isinstance(focus,(qt.QLineEdit,qt.QTextEdit,qt.QPlainTextEdit,qt.QAbstractSpinBox)):
            return False
        # Maya focuses a sibling layout widget, not necessarily the GL widget.
        if focus is None or focus==widget or widget.isAncestorOf(focus):return True
        panels=set(cmds.getPanel(type='modelPanel') or [])
        panel=widget.parentWidget()
        while panel:
            if panel.objectName() in panels and (panel==focus or panel.isAncestorOf(focus)):
                return True
            panel=panel.parentWidget()
        return False

    def event(self,event):
        kind=event.type()
        if kind==qt.QEvent.ApplicationDeactivate:
            self.close();return False
        if kind in (qt.QEvent.ShortcutOverride,qt.QEvent.KeyPress,qt.QEvent.KeyRelease):
            if event.key()==qt.Qt.Key_B:
                releasing=kind==qt.QEvent.KeyRelease and self.b
                if not releasing and (not self.viewport_focus() or
                        event.modifiers() & (qt.Qt.AltModifier|qt.Qt.ControlModifier) or
                        qt.QApplication.mouseButtons()!=qt.Qt.NoButton):return False
                if kind==qt.QEvent.ShortcutOverride:
                    event.accept();return True
                if event.isAutoRepeat():return True
                self.b=kind==qt.QEvent.KeyPress
                if not self.b:self.resizing=None
                self.update();return True
            if kind==qt.QEvent.KeyPress and event.key()==qt.Qt.Key_Escape and self.resizing:
                brush.set_radius(self.resizing[2]);self.resizing=None
                self.update();return True
            if kind==qt.QEvent.KeyPress and event.key()==qt.Qt.Key_Escape:
                ctx=self.context()
                if ctx and getattr(ctx,'_point_preview',None) is not None:
                    ctx._cancel_relax();self.last=None;self.update();return True
        if (kind==qt.QEvent.MouseButtonPress and event.button()==qt.Qt.MiddleButton and self.b
                and not event.modifiers() & (qt.Qt.AltModifier|qt.Qt.ControlModifier)):
            mouse=self.mouse()
            if mouse:
                self.resizing=(mouse[1],mouse[2],brush.radius())
                self.consume_release=True
                self.update();return True
        if kind==qt.QEvent.MouseButtonRelease and event.button()==qt.Qt.MiddleButton and self.consume_release:
            self.resizing=None;self.consume_release=False;self.update();return True
        if kind==qt.QEvent.MouseMove:
            if self.resizing:
                mouse=self.mouse()
                if mouse:brush.set_radius(self.resizing[2]+mouse[1]-self.resizing[0])
                self.update();return True
            if self.consume_release:return True
        return False

    def update(self):
        from .editor.curvenet import curve_net_relax as relax,curve_net_edit as edit
        show=self.b or brush.soft() or bool(qt.QApplication.keyboardModifiers() & qt.Qt.ShiftModifier)
        mouse=self.mouse() if show else None
        if mouse is None:
            self.last=None
            if display:display.clear();cmds.refresh(force=True)
            return
        view,x,y=mouse
        signature=(x,y,brush.radius(),brush.soft(),self.b,self.tool._revision,
                   tuple(view.modelViewMatrix()),tuple(view.projectionMatrix()))
        if signature==self.last:return
        self.last=signature
        guide=(cmds.listConnections(self.tool.node+'.guideData',s=True,d=False,shapes=True) or [None])[0]
        if not guide:return
        world=relax._world_data(guide)
        from .editor.curvenet import curve_net_context as context
        ctx=self.context()
        move=context._state_get(ctx._s,'soft_move') if ctx else None
        if move is not None:
            weights=dict(move.weights)
            weights.update({pair:weights[v] for v,pair in move.pairs.items()})
        else:weights=relax.brush_weights(guide,x,y,brush.radius(),_world=world)
        overlays=cmds.listConnections(api.output_plug(self.tool.node),s=False,d=True,shapes=True,type='aruRetopoOverlay') or []
        radius=brush.radius()
        circle=[]
        for i in range(64):
            for j in (i,i+1):
                angle=2*math.pi*j/64
                circle.append((x+radius*math.cos(angle),y+radius*math.sin(angle),0))
        display.clear()
        for overlay in overlays:
            path=(cmds.ls(overlay,long=True) or [overlay])[0]
            display[path]=(view.getCamera().fullPathName(),circle,[(view.worldToView(om.MPoint(*world[0].positions[v]))[:2],w) for v,w in weights.items()],(x,y,radius))
        cmds.refresh(force=True)


def draw(manager,data):
    camera,circle,points,center=data
    manager.setColor(om.MColor((1.,.8,.15,1.)))
    manager.setLineWidth(1.5)
    manager.lineList(om.MPointArray(circle),True)
    # Screen rings remain legible around controls drawn in the later GPU pass.
    for p,w in points:
        manager.setColor(om.MColor((1.,.25+.65*(1-w),.1,1.)))
        ring=[]
        for i in range(16):
            for j in (i,i+1):
                a=2*math.pi*j/16
                ring.append((p[0]+8*math.cos(a),p[1]+8*math.sin(a),0))
        manager.lineList(om.MPointArray(ring),True)
    manager.setColor(om.MColor((1.,.9,.4,1.)))
    manager.text2d(om.MPoint(center[0]+center[2]+8,center[1],0),'{} px'.format(round(center[2])))
