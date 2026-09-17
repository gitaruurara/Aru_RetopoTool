"""Foreground wires with backface and self-occlusion filtering."""
import maya.api.OpenMaya as om
import maya.api.OpenMayaUI as omui
import maya.api.OpenMayaRender as omr


def maya_useNewAPI(): pass


class Overlay(omui.MPxLocatorNode):
    NAME = 'aruRetopoOverlay'
    ID = om.MTypeId(0x00131AD1)
    CLASSIFICATION = 'drawdb/geometry/aruRetopoOverlay'
    REGISTRANT = 'AruRetopoOverlayDraw'

    @staticmethod
    def creator(): return Overlay()

    @staticmethod
    def initialize():
        typed = om.MFnTypedAttribute()
        Overlay.mesh = typed.create('inputMesh', 'rtm', om.MFnData.kMesh)
        typed.storable = False
        Overlay.addAttribute(Overlay.mesh)
        numeric = om.MFnNumericAttribute()
        Overlay.enabled = numeric.create('enabled', 'rte', om.MFnNumericData.kBoolean, True)
        Overlay.addAttribute(Overlay.enabled)


class DrawData(om.MUserData):
    def __init__(self):
        super().__init__(False)
        self.lines = om.MPointArray()
        self.topology = None
        self.edges = []
        self.preview = om.MPointArray()
        self.guide_preview = om.MPointArray()
        self.preview_points = om.MPointArray()
        self.selected_points = om.MPointArray()


class Draw(omr.MPxDrawOverride):
    def __init__(self, obj):
        super().__init__(obj, None, True)
        self._draw_data={}

    @staticmethod
    def creator(obj): return Draw(obj)

    def supportedDrawAPIs(self): return omr.MRenderer.kAllDevices
    def hasUIDrawables(self): return True
    def isBounded(self, objPath, cameraPath): return False

    def prepareForDraw(self, objPath, cameraPath, frameContext, oldData):
        key=cameraPath.fullPathName()
        if key not in self._draw_data:self._draw_data[key]=DrawData()
        data=self._draw_data[key]
        from Aru_RetopoTool.drag_extrude import selected_points, selected_lines
        data.selected_lines = om.MPointArray([om.MPoint(*p) for p in selected_lines.get(objPath.fullPathName(), [])])
        data.selected_points = om.MPointArray([om.MPoint(*p) for p in selected_points.get(objPath.fullPathName(), [])])
        from Aru_RetopoTool.patch_context import preview
        from Aru_RetopoTool.construction import preview_lines, preview_points
        data.preview_points = om.MPointArray([om.MPoint(*p) for p in preview_points.get(objPath.fullPathName(), [])])
        data.guide_preview = om.MPointArray([om.MPoint(*p) for p in preview_lines.get(objPath.fullPathName(), [])])
        data.preview = om.MPointArray([om.MPoint(*p) for p in preview.get(objPath.fullPathName(), [])])
        node = om.MFnDependencyNode(objPath.node())
        if not node.findPlug('enabled', False).asBool():
            data.lines=om.MPointArray();data.view_key=None;return data
        mesh = node.findPlug('inputMesh', False).asMObject()
        if mesh.isNull():
            data.lines=om.MPointArray();data.view_key=None;return data
        fn = om.MFnMesh(mesh)
        points = fn.getPoints()
        counts, indices = fn.getVertices()
        topology = (tuple(counts), tuple(indices))
        if topology != data.topology:
            edges, offset = {}, 0
            for fi, count in enumerate(counts):
                face = list(indices[offset:offset+count]); offset += count
                for a, b in zip(face, face[1:]+face[:1]):
                    edges.setdefault(tuple(sorted((a, b))), []).append(fi)
            data.edges = sorted(edges.items())
            data.topology = topology
        camera = om.MFnCamera(cameraPath)
        orthographic = camera.isOrtho()
        inverse = objPath.inclusiveMatrixInverse()
        eye = camera.eyePoint(om.MSpace.kWorld) * inverse
        direction = camera.viewDirection(om.MSpace.kWorld) * inverse
        direction.normalize()
        geometry_key=(topology,tuple((p.x,p.y,p.z) for p in points))
        view_key=(geometry_key,tuple(eye),tuple(direction),orthographic)
        if view_key==getattr(data,'view_key',None):return data
        if geometry_key!=getattr(data,'geometry_key',None):
            from Aru_RetopoTool.display_native import Wire
            if fn.numPolygons:
                _,triangles=fn.getTriangles()
                normals=[tuple(fn.getPolygonNormal(i)) for i in range(fn.numPolygons)]
                if (getattr(data,'wire',None) and data.wire.triangles==tuple(triangles)
                        and getattr(data,'geometry_key',None)[0]==topology):
                    data.wire.update(geometry_key[1],normals)
                else:
                    if getattr(data,'wire',None):data.wire.close()
                    data.wire=Wire(geometry_key[1],tuple(triangles),data.edges,normals)
            elif getattr(data,'wire',None):data.wire.close();data.wire=None
            data.geometry_key=geometry_key
        data.lines=om.MPointArray(data.wire.visible(tuple(eye)[:3],tuple(direction),orthographic,compact=True)) if getattr(data,'wire',None) else om.MPointArray()
        data.view_key=view_key
        return data

    def addUIDrawables(self, objPath, manager, frameContext, data):
        if not data or (not len(data.lines) and not len(data.preview) and not len(data.guide_preview) and not len(data.selected_points) and not len(data.selected_lines)): return
        manager.beginDrawable(omr.MUIDrawManager.kNonSelectable)
        manager.beginDrawInXray()
        if len(data.preview):
            manager.setColor(om.MColor((1.0, .65, .15, .35)))
            manager.mesh(omr.MUIDrawManager.kTriangles, data.preview)
        manager.setColor(om.MColor((0.025, 0.075, 0.10, 1.0)))
        manager.setLineWidth(1.75)
        manager.lineList(data.lines, False)
        if len(data.guide_preview):
            manager.setColor(om.MColor((1.,.75,.1,1.)))
            manager.setLineWidth(3.)
            manager.lineList(data.guide_preview,False)
            manager.setPointSize(8.)
            for point in data.preview_points:manager.point(point)
        if len(data.selected_lines):
            manager.setColor(om.MColor((.3,1.,.2,1.)))
            manager.setLineWidth(4.)
            manager.lineList(data.selected_lines,False)
        if len(data.selected_points):
            manager.setColor(om.MColor((.02,.12,.03,1.)))
            manager.setPointSize(13.)
            for point in data.selected_points: manager.point(point)
            manager.setColor(om.MColor((.3,1.,.2,1.)))
            manager.setPointSize(9.)
            for point in data.selected_points: manager.point(point)
        manager.endDrawInXray()
        manager.endDrawable()


def initializePlugin(obj):
    plugin = om.MFnPlugin(obj, 'Aru', '0.1.0', 'Any')
    plugin.registerNode(Overlay.NAME, Overlay.ID, Overlay.creator, Overlay.initialize,
                        om.MPxNode.kLocatorNode, Overlay.CLASSIFICATION)
    try:
        omr.MDrawRegistry.registerDrawOverrideCreator(Overlay.CLASSIFICATION, Overlay.REGISTRANT, Draw.creator)
    except Exception:
        plugin.deregisterNode(Overlay.ID)
        raise


def uninitializePlugin(obj):
    omr.MDrawRegistry.deregisterDrawOverrideCreator(Overlay.CLASSIFICATION, Overlay.REGISTRANT)
    om.MFnPlugin(obj).deregisterNode(Overlay.ID)
