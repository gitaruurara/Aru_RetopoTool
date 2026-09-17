"""Explicit patch painting. Hover is draw-only; clicks persist boundary IDs."""
import json
from maya import cmds
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
from . import qt
from . import core, maya_api as api
from .native import Surface, stencil

NAME = 'aruRetopoPatchContext'
_active = None
preview = {}  # overlay full path -> world-space triangle vertices


def selected(node):
    return set(json.loads(cmds.getAttr(node+'.selectedPatches') or '[]'))


def confirm(node, key, remove=False):
    keys = selected(node)
    if remove: keys.discard(key)
    else: keys.add(key)
    with api.undo_chunk('Aru Retopo: remove patch' if remove else 'Aru Retopo: fill patch'):
        cmds.setAttr(node+'.selectedPatches', json.dumps(sorted(keys)), type='string')
        cmds.setAttr(node+'.rebuildSerial', cmds.getAttr(node+'.rebuildSerial')+1)


class PatchTool(qt.QObject):
    def __init__(self, node, context=NAME):
        super().__init__(qt.getMayaMainWindow())
        self.node = node
        self.context = context
        self.key = None
        self.cache = None
        self.candidates = []
        self.surface = None
        self.timer = qt.QTimer(self)
        self.timer.setInterval(70)
        self.timer.timeout.connect(self.tick)
        qt.QApplication.instance().installEventFilter(self)
        self.timer.start()

    def stop(self):
        self.timer.stop()
        qt.QApplication.instance().removeEventFilter(self)
        preview.clear()
        if self.surface: self.surface.close(); self.surface = None
        cmds.refresh(force=True)
        self.deleteLater()

    def rebuild(self):
        dep = om.MFnDependencyNode(_object(self.node))
        raw = cmds.getAttr(self.node+'.guideData')
        matrix = om.MMatrix(cmds.getAttr(self.node+'.guideMatrix'))
        ref = dep.findPlug('referenceMesh', False).asMObject()
        # Connected worldMesh supplies world-space geometry via data handle.
        ref = dep.findPlug('referenceMesh', False).asMDataHandle().asMeshTransformed()
        fn = om.MFnMesh(ref)
        refs = tuple((p.x,p.y,p.z) for p in fn.getPoints())
        _, triangles = fn.getTriangles()
        cache = (raw, tuple(matrix), refs, tuple(triangles))
        if cache == self.cache: return
        net = json.loads(raw)
        points = []
        for p in net['positions']:
            q = om.MPoint(*p)*matrix; points.append((q.x,q.y,q.z))
        splines = net['splines']
        if self.surface: self.surface.close()
        self.surface = Surface(refs, tuple(triangles))
        normals = self.surface.project(points, guard=False)[2]
        lookup = {p:n for p,n in zip(points,normals)}
        normal = lambda p: lookup[tuple(p)]
        self.candidates = []
        try: loops = core.regions(points, splines, normal)
        except ValueError: loops = []
        for loop in loops:
            key = core.patch_key(loop)
            plan = core.Plan(points, splines, normal, 3, selected={key})
            verts, _ = self.surface.relax(plan.evaluate(points,splines,stencil),plan,iterations=2,guard=False)
            mesh_data = om.MFnMeshData().create()
            obj = om.MFnMesh().create([om.MPoint(*p) for p in verts], [4]*len(plan.faces),
                                    [v for f in plan.faces for v in f], parent=mesh_data)
            mesh_fn = om.MFnMesh(obj)
            _, tri = mesh_fn.getTriangles()
            self.candidates.append((key, mesh_data, mesh_fn, [verts[i] for i in tri]))
        self.cache = cache

    def hover(self, x, y, view):
        self.rebuild()
        origin, direction = om.MPoint(), om.MVector()
        view.viewToWorld(x,y,origin,direction)
        hits = []
        # Require a reference hit, then choose the patch at that surface depth.
        dep = om.MFnDependencyNode(_object(self.node))
        ref = om.MFnMesh(dep.findPlug('referenceMesh',False).asMDataHandle().asMeshTransformed())
        surface_hit = ref.closestIntersection(om.MFloatPoint(origin), om.MFloatVector(direction),om.MSpace.kObject,1e10,False)
        if surface_hit:
            for key, data, fn, triangles in self.candidates:
                hit = fn.closestIntersection(om.MFloatPoint(origin),om.MFloatVector(direction),om.MSpace.kObject,1e10,False)
                if hit:
                    distance = abs(hit[1]-surface_hit[1])
                    if distance < max(.02, abs(surface_hit[1])*.015): hits.append((distance,key,triangles))
        self.key = min(hits, key=lambda h:h[0])[1] if hits else None
        preview.clear()
        if hits:
            triangles = min(hits, key=lambda h:h[0])[2]
            for overlay in cmds.listConnections(self.node+'.outMesh',s=False,d=True,shapes=True,type='aruRetopoOverlay') or []:
                preview[(cmds.ls(overlay,long=True) or [overlay])[0]] = triangles
        cmds.refresh(force=True)

    def tick(self, force=False):
        try:
            if cmds.currentCtx()!=self.context or not cmds.objExists(self.node):
                self.stop(); return
            if not force and qt.QApplication.mouseButtons()!=qt.Qt.NoButton:
                return
            view = omui.M3dView.active3dView()
            widget = qt.wrapInstance(int(view.widget()), qt.QWidget)
            point = widget.mapFromGlobal(qt.QCursor.pos())
            if widget.rect().contains(point):
                ratio = view.portWidth()/max(1,widget.width())
                self.hover(int(point.x()*ratio),int((widget.height()-point.y()-1)*ratio),view)
            elif preview:
                preview.clear(); self.key=None; cmds.refresh(force=True)
        except Exception as exc:
            self.key=None; preview.clear()
            self.timer.stop()
            cmds.warning('[Aru Retopo patch] '+str(exc))

    def eventFilter(self, obj, event):
        if cmds.currentCtx()!=getattr(self,'context',NAME): return False
        if event.type()==qt.QEvent.MouseButtonRelease and getattr(self,'_patch_press',False):
            if event.button()==qt.Qt.MiddleButton:
                self._patch_press=False
                return True
        if event.type()==qt.QEvent.MouseMove and getattr(self,'_patch_press',False): return True
        if event.type()==qt.QEvent.MouseButtonPress and event.button()==qt.Qt.MiddleButton:
            if event.modifiers() & qt.Qt.AltModifier: return False
            self.tick(force=True)
            if getattr(self,'context',NAME) != NAME and self.near_control_point(): return False
            if self.key:
                confirm(self.node,self.key,bool(event.modifiers() & qt.Qt.ShiftModifier))
                self._patch_press=True
                return True
        return False

    def near_control_point(self):
        """MMB on an EP/handle belongs to curve editing, not patch filling."""
        view=omui.M3dView.active3dView()
        widget=qt.wrapInstance(int(view.widget()),qt.QWidget)
        mouse=widget.mapFromGlobal(qt.QCursor.pos())
        ratio=view.portWidth()/max(1,widget.width())
        x,y=mouse.x()*ratio,(widget.height()-mouse.y()-1)*ratio
        from .editor.curvenet.curve_net_edit import _world_to_screen
        net=json.loads(cmds.getAttr(self.node+'.guideData'))
        matrix=om.MMatrix(cmds.getAttr(self.node+'.guideMatrix'))
        for p in net['positions']:
            q=om.MPoint(*p)*matrix
            point=_world_to_screen([q.x,q.y,q.z])
            if point and (point[0]-x)**2+(point[1]-y)**2 < (14*ratio)**2: return True
        return False


def _object(node):
    sel=om.MSelectionList();sel.add(node);return sel.getDependNode(0)


def start(node, context=NAME):
    global _active
    if _active:
        try: _active.stop()
        except RuntimeError: pass
    api.set_foreground(node,True)
    if not cmds.draggerContext(NAME,exists=True):
        cmds.draggerContext(NAME,cursor='crossHair',undoMode='step')
    cmds.setToolTo(context)
    _active=PatchTool(node,context)
    return _active
