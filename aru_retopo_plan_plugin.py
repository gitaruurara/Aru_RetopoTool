"""Cached topology provider for the opt-in native retopo backend."""
import json,math
import maya.api.OpenMaya as om
from Aru_RetopoTool.core import Plan
from Aru_RetopoTool.native import Surface
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData

def maya_useNewAPI():pass
class RetopoPlan(om.MPxNode):
    ID=om.MTypeId(0x00131AD6)
    ARRAYS={'stencilOffsets':om.MFnData.kIntArray,'stencilIndices':om.MFnData.kIntArray,
            'stencilWeights':om.MFnData.kDoubleArray,'faceCounts':om.MFnData.kIntArray,
            'faceIndices':om.MFnData.kIntArray,'adjacencyOffsets':om.MFnData.kIntArray,
            'adjacencyIndices':om.MFnData.kIntArray,'guideWeights':om.MFnData.kDoubleArray}
    def __init__(self):super().__init__();self.key=None;self.payload=None
    @staticmethod
    def creator():return RetopoPlan()
    @staticmethod
    def initialize():
        cls=RetopoPlan
        def typed(name,kind,output=False):
            fn=om.MFnTypedAttribute();a=fn.create(name,name,kind)
            fn.writable=not output;fn.storable=not output;cls.addAttribute(a);setattr(cls,name,a);return a
        inputs=[typed('guideData',om.MFnData.kString),typed('referenceMesh',om.MFnData.kMesh),typed('selectedPatches',om.MFnData.kString)]
        # Evaluated positions are read when topology actually changes; CP edits
        # must not dirty an unchanged topology/stencil (same contract as Plan.key).
        typed('guidePositions',om.MFnData.kDoubleArray)
        fn=om.MFnMatrixAttribute();cls.guideMatrix=fn.create('guideMatrix','gm');cls.addAttribute(cls.guideMatrix);inputs.append(cls.guideMatrix)
        for name,kind,default in (('subdivisions',om.MFnNumericData.kInt,2),('rebuildSerial',om.MFnNumericData.kInt,0),('guideWeight',om.MFnNumericData.kDouble,1.)):
            fn=om.MFnNumericAttribute();a=fn.create(name,name,kind,default);cls.addAttribute(a);setattr(cls,name,a);inputs.append(a)
        outputs=[typed(name,kind,True) for name,kind in cls.ARRAYS.items()]+[typed('status',om.MFnData.kString,True)]
        for a in inputs:
            for b in outputs:cls.attributeAffects(a,b)
    def schedulingType(self):return om.MPxNode.kSerial
    def compute(self,plug,data):
        cls=RetopoPlan
        if plug.attribute() not in [getattr(cls,n) for n in list(cls.ARRAYS)+['status']]:return None
        try:
            raw=data.inputValue(cls.guideData).asString()
            # Reuse a parsed guide only when another evaluator already owns it.
            # A miss keeps the lightweight JSON path; never build editor wrappers
            # merely to evaluate the native plan.
            cached=RetopoGuideData._PARSE_CACHE.get(raw)
            if cached is None:
                net=json.loads(raw)
                splines=tuple(map(tuple,net['splines']))
                base_points=net['positions']
            else:
                splines=tuple(cached.splines)
                base_points=cached.positions
            selected=set(json.loads(data.inputValue(cls.selectedPatches).asString() or '[]'))
            key=(splines,data.inputValue(cls.subdivisions).asInt(),data.inputValue(cls.rebuildSerial).asInt(),tuple(sorted(selected)))
            weight=data.inputValue(cls.guideWeight).asDouble()
            if not math.isfinite(weight) or not 0<=weight<=1:raise ValueError('Invalid guide weight')
            if self.key!=key:
                points=base_points;obj=data.inputValue(cls.guidePositions).data()
                if not obj.isNull():
                    values=list(om.MFnDoubleArrayData(obj).array())
                    if len(values)!=len(points)*3:raise ValueError('Guide position count mismatch')
                    points=list(zip(values[::3],values[1::3],values[2::3]))
                matrix=data.inputValue(cls.guideMatrix).asMatrix()
                points=[tuple(om.MPoint(*p)*matrix)[:3] for p in points]
                if not all(math.isfinite(v) for p in points for v in p):raise ValueError('Invalid guide positions')
                handle=data.inputValue(cls.referenceMesh);mesh=handle.asMesh()
                if mesh.isNull() or not mesh.hasFn(om.MFn.kMesh):raise ValueError('Missing reference mesh')
                fn=om.MFnMesh(handle.asMeshTransformed());_,tri=fn.getTriangles()
                surface=Surface([tuple(v)[:3] for v in fn.getPoints()],list(tri))
                try:
                    eps=sorted({v for sp in splines for v in (sp[0],sp[3])})
                    _,_,normals=surface.project([points[i] for i in eps],guard=False)
                    lookup={points[i]:n for i,n in zip(eps,normals)}
                    plan=Plan(points,splines,lambda p:lookup[tuple(p)],key[1],selected=selected)
                finally:surface.close()
                offsets,ids,weights=plan.compile_stencil(splines)
                values=dict(stencilOffsets=offsets,stencilIndices=ids,stencilWeights=weights,
                            faceCounts=[4]*len(plan.faces),faceIndices=[v for f in plan.faces for v in f],
                            adjacencyOffsets=plan.adj_offsets,adjacencyIndices=plan.adj_ids)
                self.payload={name:(om.MFnIntArrayData().create(value) if cls.ARRAYS[name]==om.MFnData.kIntArray else om.MFnDoubleArrayData().create(value)) for name,value in values.items()}
                self.plan=plan;self.key=key;self.weight=None
            if self.weight!=weight:
                self.payload['guideWeights']=om.MFnDoubleArrayData().create([weight if i in self.plan.guide_vertices else 0. for i in range(self.plan.count)])
                self.weight=weight
            message='{} 領域 / {:,} quads / {:,} 頂点 / Native'.format(self.plan.region_count,len(self.plan.faces),self.plan.count)
        except Exception as exc:
            self.key=None
            self.payload={name:(om.MFnIntArrayData().create([]) if kind==om.MFnData.kIntArray else om.MFnDoubleArrayData().create([])) for name,kind in cls.ARRAYS.items()}
            message='ERROR: '+str(exc)
        for name,obj in self.payload.items():
            handle=data.outputValue(getattr(cls,name));handle.setMObject(obj);handle.setClean()
        handle=data.outputValue(cls.status);handle.setString(message);handle.setClean()

def initializePlugin(obj):om.MFnPlugin(obj,'Aru','0.1.0','Any').registerNode('aruRetopoPlan',RetopoPlan.ID,RetopoPlan.creator,RetopoPlan.initialize)
def uninitializePlugin(obj):om.MFnPlugin(obj).deregisterNode(RetopoPlan.ID)
