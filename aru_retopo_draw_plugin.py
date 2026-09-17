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

    @staticmethod
    def creator(obj): return Draw(obj)

    def supportedDrawAPIs(self): return omr.MRenderer.kAllDevices
    def hasUIDrawables(self): return True
    def isBounded(self, objPath, cameraPath): return False

    def prepareForDraw(self, objPath, cameraPath, frameContext, oldData):
        data = oldData if isinstance(oldData, DrawData) else DrawData()
        data.lines = om.MPointArray()
        from Aru_RetopoTool.drag_extrude import selected_points
        data.selected_points = om.MPointArray([om.MPoint(*p) for p in selected_points.get(objPath.fullPathName(), [])])
        from Aru_RetopoTool.patch_context import preview
        from Aru_RetopoTool.construction import preview_lines, preview_points
        data.preview_points = om.MPointArray([om.MPoint(*p) for p in preview_points.get(objPath.fullPathName(), [])])
        data.guide_preview = om.MPointArray([om.MPoint(*p) for p in preview_lines.get(objPath.fullPathName(), [])])
        data.preview = om.MPointArray([om.MPoint(*p) for p in preview.get(objPath.fullPathName(), [])])
        node = om.MFnDependencyNode(objPath.node())
        if not node.findPlug('enabled', False).asBool(): return data
        mesh = node.findPlug('inputMesh', False).asMObject()
        if mesh.isNull(): return data
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
        inverse = objPath.inclusiveMatrixInverse()
        eye = camera.eyePoint(om.MSpace.kWorld) * inverse
        direction = camera.viewDirection(om.MSpace.kWorld) * inverse
        direction.normalize()
        normals = [fn.getPolygonNormal(i) for i in range(fn.numPolygons)]
        accel = fn.autoUniformGridParams()
        # Test short edge sections, so a partially occluded edge isn't removed
        # wholesale. Shaded output supplies the surface; this draws wires only.
        lines = []
        for (a, b), faces in data.edges:
            for step in range(4):
                p0 = points[a] + (points[b]-points[a])*(step/4.)
                p1 = points[a] + (points[b]-points[a])*((step+1)/4.)
                mid = p0+(p1-p0)*.5
                to_eye = -direction if camera.isOrtho else eye-mid
                if not any(normals[fi]*to_eye > 0 for fi in faces): continue
                distance = to_eye.length()
                if distance < 1e-10: continue
                ray = to_eye.normal()
                eps = max((points[a]-points[b]).length()*1e-4, 1e-6)
                origin = mid+ray*eps
                hit = fn.closestIntersection(om.MFloatPoint(origin), om.MFloatVector(ray),
                    om.MSpace.kObject, 1e10 if camera.isOrtho else max(distance-eps, eps),
                    False, accelParams=accel, tolerance=1e-7)
                if hit is None: lines.extend((p0, p1))
        data.lines = om.MPointArray(lines)
        return data

    def addUIDrawables(self, objPath, manager, frameContext, data):
        if not data or (not len(data.lines) and not len(data.preview) and not len(data.guide_preview) and not len(data.selected_points)): return
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
