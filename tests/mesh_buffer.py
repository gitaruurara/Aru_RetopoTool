"""Isolated C++ mesh transfer parity and timing; not enabled in artist scenes."""
import os,sys,json,time,statistics,struct,ctypes
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool.tests.dense_performance import fixture
from Aru_RetopoTool.core import Plan,unit
from Aru_RetopoTool.native import stencil,packed,unpack
from Aru_RetopoTool.tests.typed_positions import plug

def run():
    root=os.path.dirname(os.path.dirname(__file__))
    cmds.loadPlugin(os.path.join(root,'bin',cmds.about(version=True),'aru_retopo_mesh_buffer_v2.mll'))
    p,s=fixture();plan=Plan(p,s,unit,3);points=list(plan.evaluate(p,s,stencil));values=packed(points)
    node=cmds.createNode('aruRetopoMeshBuffer')
    counts=[4]*len(plan.faces);indices=[v for f in plan.faces for v in f]
    plug(node,'faceCounts').setMObject(om.MFnIntArrayData().create(counts))
    plug(node,'faceIndices').setMObject(om.MFnIntArrayData().create(indices))
    storage=om.MFnMeshData().create();template=om.MFnMesh().create(om.MPointArray(points),counts,indices,parent=storage)
    previous=[];times=[[],[]]
    try:
        for i in range(20):
            values[0]=points[0][0]+i*.00001
            outputs=[]
            for k in (i%2,1-i%2):
                start=time.perf_counter()
                if k==0:
                    coords=om.MPointArray(unpack(values));data=om.MFnMeshData().create()
                    fn=om.MFnMesh();fn.copy(template,data);fn.setPoints(coords)
                else:
                    plug(node,'positions').setMObject(om.MFnDoubleArrayData().create(om.MDoubleArray(values)))
                    data=plug(node,'outMesh').asMObject();fn=om.MFnMesh(data)
                elapsed=(time.perf_counter()-start)*1000
                if i>=4:times[k].append(elapsed)
                actual=fn.getPoints();assert len(actual)==len(points)
                assert abs(actual[0].x-values[0])<1e-6
                assert all(max(abs(a-b) for a,b in zip(tuple(v)[:3],values[3*j:3*j+3]))<1e-6 for j,v in enumerate(actual))
                outputs.append(list(map(tuple,actual)))
                if i==0:previous.append((data,tuple(actual[0])))
            assert outputs[0]==outputs[1]
            for data,first in previous:assert tuple(om.MFnMesh(data).getPoint(0))==first
        # Same vertex count with different topology must rebuild the template.
        changed=list(indices);changed[:4]=reversed(changed[:4])
        plug(node,'faceIndices').setMObject(om.MFnIntArrayData().create(changed))
        assert list(om.MFnMesh(plug(node,'outMesh').asMObject()).getPolygonVertices(0))==changed[:4]
        for data,first in previous:assert tuple(om.MFnMesh(data).getPoint(0))==first
        plug(node,'faceIndices').setMObject(om.MFnIntArrayData().create(indices))
        # Invalid counts/indices/coordinates produce empty output, never stale geometry.
        for invalid in ([0.,1.], [float('nan')]*len(values)):
            plug(node,'positions').setMObject(om.MFnDoubleArrayData().create(invalid))
            empty=plug(node,'outMesh').asMObject()
            assert empty.hasFn(om.MFn.kMeshData)
            try: size=om.MFnMesh(empty).numVertices
            except RuntimeError: size=0  # valid empty MFnMeshData has no mesh object
            assert size==0
        plug(node,'positions').setMObject(om.MFnDoubleArrayData().create(om.MDoubleArray(values)))
        assert om.MFnMesh(plug(node,'outMesh').asMObject()).numVertices==len(points)
        result={'vertices':len(points),'quads':len(plan.faces),'python_transfer_ms':statistics.median(times[0]),'native_transfer_ms':statistics.median(times[1]),'samples_ms':times}
        print('PASS native mesh transfer parity, previous outputs preserved, invalid/recovery', {k:v for k,v in result.items() if k!='samples_ms'})
        return result
    finally:cmds.delete(node)
if __name__=='__main__':
    import maya.standalone,traceback
    maya.standalone.initialize(name='python');status=0
    try:
        report=run()
        with open(sys.argv[1],'w') as f:json.dump(report,f,indent=2)
    except Exception:traceback.print_exc();status=1
    finally:maya.standalone.uninitialize()
    sys.stdout.flush();sys.stderr.flush();os._exit(status)
