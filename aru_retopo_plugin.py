"""Persistent Maya DG generator. All compute-time mutations are on output data."""
import json
import math
import time
import maya.api.OpenMaya as om
from Aru_RetopoTool.core import Plan
from Aru_RetopoTool.native import Surface, stencil


def maya_useNewAPI(): pass


class RetopoNode(om.MPxNode):
    TYPE_NAME = 'aruRetopoMesh'
    TYPE_ID = om.MTypeId(0x00131AD0)  # local development ID; reserve before distribution

    def __init__(self):
        super().__init__()
        self.surface = self.plan = None
        self.surface_key = self.plan_key = None
        self.seeds = None

    @staticmethod
    def creator(): return RetopoNode()

    @staticmethod
    def initialize():
        cls = RetopoNode
        def typed(name, short, kind, output=False):
            fn = om.MFnTypedAttribute()
            attr = fn.create(name, short, kind)
            fn.writable = not output; fn.storable = not output
            cls.addAttribute(attr); setattr(cls, name, attr)
            return attr
        def number(name, short, kind, default, minimum=None, maximum=None):
            fn = om.MFnNumericAttribute(); attr = fn.create(name, short, kind, default)
            if minimum is not None: fn.setMin(minimum)
            if maximum is not None: fn.setMax(maximum)
            fn.keyable = True
            cls.addAttribute(attr); setattr(cls, name, attr)
            return attr
        inputs = [typed('guideData', 'gd', om.MFnData.kString),
                  typed('selectedPatches', 'sps', om.MFnData.kString),
                  typed('referenceMesh', 'rm', om.MFnData.kMesh)]
        fn = om.MFnMatrixAttribute(); cls.guideMatrix = fn.create('guideMatrix', 'gm')
        cls.addAttribute(cls.guideMatrix); inputs.append(cls.guideMatrix)
        inputs += [number('subdivisions', 'sd', om.MFnNumericData.kInt, 2, 1, 6),
                   number('relaxIterations', 'ri', om.MFnNumericData.kInt, 3, 0, 30),
                   number('relaxStrength', 'rs', om.MFnNumericData.kDouble, .35, 0., 1.),
                   number('guideWeight', 'gw', om.MFnNumericData.kDouble, 1., 0., 1.),
                   number('projectionGuard', 'pg', om.MFnNumericData.kBoolean, True),
                   number('rebuildSerial', 'rb', om.MFnNumericData.kInt, 0)]
        outputs = [typed('outMesh', 'om', om.MFnData.kMesh, True),
                   typed('status', 'st', om.MFnData.kString, True)]
        for a in inputs:
            for b in outputs: cls.attributeAffects(a, b)

    def schedulingType(self): return om.MPxNode.kSerial

    def compute(self, plug, data):
        cls = RetopoNode
        if plug.attribute() not in (cls.outMesh, cls.status): return om.kUnknownParameter
        started = time.perf_counter()
        mesh_data = om.MFnMeshData().create()
        try:
            raw = data.inputValue(cls.guideData).asString()
            if not raw: raise ValueError('カーブネットを指定してください。')
            net = json.loads(raw)
            matrix = data.inputValue(cls.guideMatrix).asMatrix()
            points = []
            for p in net['positions']:
                q = om.MPoint(*p) * matrix
                points.append((q.x, q.y, q.z))
            if not all(math.isfinite(x) for p in points for x in p): raise ValueError('Non-finite guide positions')
            splines = tuple(tuple(s) for s in net['splines'])
            mesh = data.inputValue(cls.referenceMesh).asMeshTransformed()
            if mesh.isNull(): raise ValueError('参照メッシュを指定してください。')
            fn = om.MFnMesh(mesh)
            ref_points = tuple((p.x, p.y, p.z) for p in fn.getPoints())
            _, tri = fn.getTriangles()
            triangles = tuple(tri)
            if not all(math.isfinite(x) for p in ref_points for x in p): raise ValueError('Non-finite reference positions')
            surface_key = (ref_points, triangles)
            if surface_key != self.surface_key:
                surface = Surface(ref_points, triangles)
                if self.surface_key is None or triangles != self.surface_key[1]: self.seeds = None
                if self.surface: self.surface.close()
                self.surface, self.surface_key = surface, surface_key
            serial = data.inputValue(cls.rebuildSerial).asInt()
            # MPlug also supports the dynamic attribute on a hot-updated node.
            dep = om.MFnDependencyNode(self.thisMObject())
            selected = json.loads(dep.findPlug('selectedPatches', False).asString() or '[]')
            key = (splines, data.inputValue(cls.subdivisions).asInt(), serial, tuple(sorted(selected)))
            if key != self.plan_key:
                eps = sorted({v for sp in splines for v in (sp[0], sp[3])})
                _, _, normals = self.surface.project([points[v] for v in eps], guard=False)
                lookup = {points[v]: n for v, n in zip(eps, normals)}
                self.plan = Plan(points, splines, lambda p: lookup[tuple(p)], key[1], selected=set(selected))
                self.plan_key, self.seeds = key, None
            if not self.plan.count:
                data.outputValue(cls.outMesh).setMObject(mesh_data)
                data.outputValue(cls.status).setString('0 パッチ確定：面張りツールでホバー → 中クリック')
                data.outputValue(cls.outMesh).setClean(); data.outputValue(cls.status).setClean()
                return
            generated = self.plan.evaluate(points, splines, stencil)
            generated, self.seeds = self.surface.relax(
                generated, self.plan,
                data.inputValue(cls.relaxIterations).asInt(),
                data.inputValue(cls.relaxStrength).asDouble(),
                data.inputValue(cls.guideWeight).asDouble(), self.seeds,
                data.inputValue(cls.projectionGuard).asBool())
            om.MFnMesh().create([om.MPoint(*p) for p in generated], [4]*len(self.plan.faces),
                               [v for f in self.plan.faces for v in f], parent=mesh_data)
            status = '{} 領域 / {:,} quads / {:,} 頂点 / {:.1f} ms / C++'.format(
                self.plan.region_count, len(self.plan.faces), len(generated), (time.perf_counter()-started)*1000)
        except Exception as exc:
            # Invalid edited guides must clear the preview instead of displaying a stale mesh.
            self.plan_key = None
            self.seeds = None
            status = 'ERROR: {}'.format(exc)
        data.outputValue(cls.outMesh).setMObject(mesh_data)
        data.outputValue(cls.status).setString(status)
        data.outputValue(cls.outMesh).setClean()
        data.outputValue(cls.status).setClean()


def initializePlugin(obj):
    om.MFnPlugin(obj, 'Aru', '0.1.0', 'Any').registerNode(
        RetopoNode.TYPE_NAME, RetopoNode.TYPE_ID, RetopoNode.creator, RetopoNode.initialize)


def uninitializePlugin(obj):
    om.MFnPlugin(obj).deregisterNode(RetopoNode.TYPE_ID)
