"""Cached topology provider for the opt-in native retopo backend."""
import json,math
import maya.api.OpenMaya as om
from Aru_RetopoTool.core import Plan, selected_regions
from Aru_RetopoTool.native import Surface
from Aru_RetopoTool.editor.curvenet.curve_net_data import RetopoGuideData

def maya_useNewAPI():pass
class RetopoPlan(om.MPxNode):
    ID=om.MTypeId(0x00131AD6)
    ARRAYS={'stencilOffsets':om.MFnData.kIntArray,'stencilIndices':om.MFnData.kIntArray,
            'stencilWeights':om.MFnData.kDoubleArray,'faceCounts':om.MFnData.kIntArray,
            'faceIndices':om.MFnData.kIntArray,'adjacencyOffsets':om.MFnData.kIntArray,
            'adjacencyIndices':om.MFnData.kIntArray,'guideWeights':om.MFnData.kDoubleArray}
    def __init__(self):
        super().__init__();self.key=None;self.payload=None
        self._surface=None;self._surface_dirty=True;self.layout_key=None
    def setDependentsDirty(self,plug,affected):
        if plug.attribute()==self.referenceMesh:
            self._surface_dirty=True
            self.key=None
            self.layout_key=None
    @staticmethod
    def creator():return RetopoPlan()
    @staticmethod
    def initialize():
        cls=RetopoPlan
        def typed(name,kind,output=False):
            fn=om.MFnTypedAttribute();a=fn.create(name,name,kind)
            fn.writable=not output;fn.storable=not output;cls.addAttribute(a);setattr(cls,name,a);return a
        inputs=[typed('guideData',om.MFnData.kString),typed('referenceMesh',om.MFnData.kMesh),typed('selectedPatches',om.MFnData.kString),typed('influenceField',om.MFnData.kString),typed('loopReductions',om.MFnData.kString)]
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
            reductions=data.inputValue(cls.loopReductions).asString() or '[]'
            field=data.inputValue(cls.influenceField).asString() or '{}'
            key=(splines,data.inputValue(cls.subdivisions).asInt(),data.inputValue(cls.rebuildSerial).asInt(),tuple(sorted(selected)),reductions)
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
                if self._surface is None or self._surface_dirty:
                    fn=om.MFnMesh(handle.asMeshTransformed());_,tri=fn.getTriangles()
                    surface=Surface([tuple(v)[:3] for v in fn.getPoints()],list(tri))
                    if self._surface is not None:self._surface.close()
                    self._surface=surface;self._surface_dirty=False
                surface=self._surface
                eps=sorted({v for sp in splines for v in (sp[0],sp[3])})
                _,_,normals=surface.project([points[i] for i in eps],guard=False)
                lookup={points[i]:n for i,n in zip(eps,normals)}
                normal=lambda p:lookup[tuple(p)]
                loops=selected_regions(points,splines,normal,selected)
                used=sorted({si for loop in loops for side in loop for si,_ in side})
                layout=(tuple(tuple(tuple(side) for side in loop) for loop in loops),
                        tuple((i,splines[i]) for i in used),key[1],key[2],reductions)
                # Region discovery still runs: an inserted internal edge or a
                # changed logical corner must invalidate the plan. Unselected
                # guide additions can retain identical compiled mesh buffers.
                if self.layout_key!=layout:
                    plan=Plan(points,splines,normal,key[1],selected=selected,region_loops=loops)
                    from Aru_RetopoTool.density import apply
                    plan=apply(plan,json.loads(reductions))
                    offsets,ids,weights=plan.compile_stencil(splines)
                    values=dict(stencilOffsets=offsets,stencilIndices=ids,stencilWeights=weights,
                                faceCounts=[4]*len(plan.faces),faceIndices=[v for f in plan.faces for v in f],
                                adjacencyOffsets=plan.adj_offsets,adjacencyIndices=plan.adj_ids)
                    self.payload={name:(om.MFnIntArrayData().create(value) if cls.ARRAYS[name]==om.MFnData.kIntArray else om.MFnDoubleArrayData().create(value)) for name,value in values.items()}
                    self.plan=plan;self.layout_key=layout;self.weight=None
                self.key=key
            if self.weight!=(weight,field):
                from Aru_RetopoTool.local_fields import weights as field_weights, decoded
                self.payload['guideWeights']=om.MFnDoubleArrayData().create(field_weights(self.plan,decoded(field),weight))
                self.weight=(weight,field)
            message='{} 領域 / {:,} quads / {:,} 頂点 / Native'.format(self.plan.region_count,len(self.plan.faces),self.plan.count)
            if getattr(self.plan,'rejected',None):message+=' / {} 削減保留'.format(len(self.plan.rejected))
        except Exception as exc:
            self.key=None;self.layout_key=None
            self.payload={name:(om.MFnIntArrayData().create([]) if kind==om.MFnData.kIntArray else om.MFnDoubleArrayData().create([])) for name,kind in cls.ARRAYS.items()}
            message='ERROR: '+str(exc)
        for name,obj in self.payload.items():
            handle=data.outputValue(getattr(cls,name));handle.setMObject(obj);handle.setClean()
        handle=data.outputValue(cls.status);handle.setString(message);handle.setClean()

def initializePlugin(obj):om.MFnPlugin(obj,'Aru','0.1.0','Any').registerNode('aruRetopoPlan',RetopoPlan.ID,RetopoPlan.creator,RetopoPlan.initialize)
def uninitializePlugin(obj):om.MFnPlugin(obj).deregisterNode(RetopoPlan.ID)
