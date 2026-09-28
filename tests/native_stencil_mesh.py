"""Guide controls -> native stencil -> mesh, compared to current Python path."""
import os,json,sys,time,statistics
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool.tests.dense_performance import fixture
from Aru_RetopoTool.tests.test_core import polygon
from Aru_RetopoTool.tests.typed_positions import plug
from Aru_RetopoTool.core import Plan,unit
from Aru_RetopoTool.native import stencil,packed,unpack,Surface

def run(project=False):
    root=os.path.dirname(os.path.dirname(__file__))
    cmds.loadPlugin(os.path.join(root,'bin',cmds.about(version=True),'aru_retopo_mesh_buffer_v2.mll'))
    for source in ((fixture(),) if project else (polygon(4),polygon(5),fixture())):
        p,s=source;plan=Plan(p,s,unit if len(s)>10 else lambda p:(0,1,0),3);node=cmds.createNode('aruRetopoMeshBuffer')
        counts=[4]*len(plan.faces);ids=[v for f in plan.faces for v in f]
        offsets,controls,weights=plan.compile_stencil(s)
        for name,data in (('faceCounts',counts),('faceIndices',ids),('stencilOffsets',offsets),('stencilIndices',controls)):
            plug(node,name).setMObject(om.MFnIntArrayData().create(data))
        plug(node,'stencilWeights').setMObject(om.MFnDoubleArrayData().create(weights))
        initial=unpack(plan.evaluate(p,s,stencil).values)
        storage=om.MFnMeshData().create();template=om.MFnMesh().create(om.MPointArray(initial),counts,ids,parent=storage)
        times=[[],[]];retained=None;surface=None;reference=None;seeds=None
        if project:
            reference=cmds.polySphere(r=3,sx=64,sy=32)[0]
            reference_shape=cmds.listRelatives(reference,shapes=True,fullPath=True)[0]
            cmds.connectAttr(reference_shape+'.worldMesh[0]',node+'.referenceMesh')
            cmds.setAttr(node+'.projectToReference',True);cmds.setAttr(node+'.relaxIterations',5)
            for name,array in (('adjacencyOffsets',plan.adj_offsets),('adjacencyIndices',plan.adj_ids)):
                plug(node,name).setMObject(om.MFnIntArrayData().create(array))
            plug(node,'guideWeights').setMObject(om.MFnDoubleArrayData().create([1. if i in plan.guide_vertices else 0. for i in range(plan.count)]))
            selection=om.MSelectionList();selection.add(reference_shape);fn=om.MFnMesh(selection.getDagPath(0))
            _,triangles=fn.getTriangles();surface=Surface([tuple(p)[:3] for p in fn.getPoints()],list(triangles))
        try:
            for i in range(16):
                moved=list(p);v=p[0];moved[0]=(v[0]+i*.0001,v[1],v[2])
                outputs=[]
                for k in (i%2,1-i%2):
                    start=time.perf_counter()
                    if k==0:
                        generated=plan.evaluate(moved,s,stencil)
                        if project:
                            coordinates,seeds=surface.relax(generated,plan,5,seeds=seeds,native_seeds=True)
                        else:coordinates=unpack(generated.values)
                        points=om.MPointArray(coordinates);data=om.MFnMeshData().create()
                        fn=om.MFnMesh();fn.copy(template,data);fn.setPoints(points)
                    else:
                        plug(node,'positions').setMObject(om.MFnDoubleArrayData().create(om.MDoubleArray(packed(moved))))
                        data=plug(node,'outMesh').asMObject();fn=om.MFnMesh(data)
                    if i>=4:times[k].append((time.perf_counter()-start)*1000)
                    outputs.append(list(map(tuple,fn.getPoints())))
                    if i==0 and k==1:retained=(data,outputs[-1])
                assert outputs[0]==outputs[1]
                assert list(om.MFnDoubleArrayData(plug(node,"positions").asMObject()).array())==[x for point in moved for x in point]
                assert list(map(tuple,om.MFnMesh(retained[0]).getPoints()))==retained[1]
            if project:
                # Changed reference geometry, guide matrix and solver settings.
                cmds.setAttr(reference+'.translateY',.2)
                selection=om.MSelectionList();selection.add(reference_shape)
                reference_fn=om.MFnMesh(selection.getDagPath(0));_,triangles=reference_fn.getTriangles()
                # Use the existing DG generator's transformed mesh extraction.
                # DAG getPoints(kWorld) keeps doubles; asMeshTransformed stores
                # transformed mesh coordinates at Maya's mesh precision.
                from Aru_RetopoTool import maya_api as api
                api.load_plugin();reader=cmds.createNode('aruRetopoMesh')
                try:
                    cmds.setAttr(reader+'.guideData',json.dumps({'positions':[], 'splines':[]}),type='string')
                    cmds.connectAttr(reference_shape+'.worldMesh[0]',reader+'.referenceMesh')
                    cmds.getAttr(reader+'.status')
                    selection=om.MSelectionList();selection.add(reader)
                    user=om.MFnDependencyNode(selection.getDependNode(0)).userNode()
                    reference_points,reference_triangles=user.surface_key
                    surface.close();surface=Surface(reference_points,reference_triangles)
                finally:cmds.delete(reader)
                matrix=om.MMatrix((1.1,0,0,0, 0,.95,0,0, 0,0,1,0, .1,.2,-.1,1))
                plug(node,'guideMatrix').setMObject(om.MFnMatrixData().create(matrix))
                transformed=[tuple(om.MPoint(*v)*matrix)[:3] for v in moved]
                for steps,amount,anchor_weight,safe in ((0,.35,1.,True),(5,.7,.25,False),(3,0.,1.,True)):
                    cmds.setAttr(node+'.relaxIterations',steps);cmds.setAttr(node+'.relaxStrength',amount)
                    cmds.setAttr(node+'.projectionGuard',safe)
                    plug(node,'guideWeights').setMObject(om.MFnDoubleArrayData().create([anchor_weight if i in plan.guide_vertices else 0. for i in range(plan.count)]))
                    expected,seeds=surface.relax(plan.evaluate(transformed,s,stencil),plan,steps,amount,anchor_weight,seeds=seeds,guard=safe,native_seeds=True)
                    reference_data=om.MFnMeshData().create();reference_mesh=om.MFnMesh()
                    reference_mesh.copy(template,reference_data);reference_mesh.setPoints(om.MPointArray(expected))
                    actual=om.MFnMesh(plug(node,'outMesh').asMObject()).getPoints()
                    wanted=reference_mesh.getPoints()
                    difference=max((a-b).length() for a,b in zip(actual,wanted))
                    assert list(map(tuple,actual))==list(map(tuple,wanted)),(steps,amount,anchor_weight,safe,difference,tuple(actual[0]),tuple(wanted[0]))
                print('PASS native reference/guide transform and solver-setting changes')
            if not project:
                # Same-sized coefficient replacement must invalidate the cache.
                altered=list(weights);altered[0]+=0.125
                plug(node,'stencilWeights').setMObject(om.MFnDoubleArrayData().create(altered))
                revised=om.MFnMesh(plug(node,'outMesh').asMObject()).getPoints()
                expected=stencil(moved,offsets,controls,altered)
                comparison_data=om.MFnMeshData().create();comparison=om.MFnMesh()
                comparison.copy(template,comparison_data);comparison.setPoints(om.MPointArray(expected))
                assert list(map(tuple,revised))==list(map(tuple,comparison.getPoints()))
                plug(node,'stencilWeights').setMObject(om.MFnDoubleArrayData().create(weights))
            if project:
                for name,bad_value,valid_value,kind in (
                    ('adjacencyOffsets',[0],plan.adj_offsets,'int'),
                    ('adjacencyIndices',[-1]*len(plan.adj_ids),plan.adj_ids,'int'),
                    ('guideWeights',[float('nan')]*plan.count,[1. if i in plan.guide_vertices else 0. for i in range(plan.count)],'double')):
                    factory=om.MFnIntArrayData if kind=='int' else om.MFnDoubleArrayData
                    plug(node,name).setMObject(factory().create(bad_value))
                    assert cmds.getAttr(node+'.status').startswith('ERROR:')
                    plug(node,name).setMObject(factory().create(valid_value))
                    assert om.MFnMesh(plug(node,'outMesh').asMObject()).numVertices==plan.count
            # Malformed CSR must not read outside source or weight storage.
            plug(node,'stencilOffsets').setMObject(om.MFnIntArrayData().create([0,len(controls)+1]))
            bad=plug(node,'outMesh').asMObject()
            try: size=om.MFnMesh(bad).numVertices
            except RuntimeError:size=0
            assert size==0
            plug(node,'stencilOffsets').setMObject(om.MFnIntArrayData().create(offsets))
            assert om.MFnMesh(plug(node,'outMesh').asMObject()).numVertices==plan.count
            result={'projection':project,'patches':plan.region_count,'controls':len(p),'vertices':plan.count,'python_ms':statistics.median(times[0]),'native_ms':statistics.median(times[1]),'samples_ms':times}
            print('PASS guide stencil + mesh parity / immutable outputs / invalid CSR recovery',{k:v for k,v in result.items() if k!='samples_ms'})
        finally:
            cmds.delete(node)
            if surface:surface.close()
            if reference:cmds.delete(reference)
    return result
if __name__=='__main__':
    import maya.standalone,traceback
    maya.standalone.initialize(name='python');status=0
    try:
        result=run(project="--project" in sys.argv)
        with open(sys.argv[1],'w') as f:json.dump(result,f,indent=2)
    except Exception:traceback.print_exc();status=1
    finally:maya.standalone.uninitialize()
    sys.stdout.flush();sys.stderr.flush();os._exit(status)
