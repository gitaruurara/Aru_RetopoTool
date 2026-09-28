import os,sys,json,time,statistics,hashlib,struct,traceback
from pathlib import Path
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import maya.api.OpenMaya as om
root=Path(__file__).resolve().parents[1]
version=os.environ.get('ARU_TEST_BUFFER_VERSION','v3');status=1
try:
    data=json.loads((root/'tests/native_relax_input.json').read_text())
    local_cvs=int(os.environ.get('ARU_TEST_LOCAL_CVS','0'))
    if local_cvs:
        limited=list(data['arrays']['positions']);changed=0
        for index in range(0,len(limited),3):
            if limited[index:index+3]!=data['relaxed_positions'][index:index+3]:
                limited[index:index+3]=data['relaxed_positions'][index:index+3]
                changed+=1
                if changed>=local_cvs:break
        data['relaxed_positions']=limited
    suffix=('_local'+str(local_cvs)) if local_cvs else ''

    cmds.loadPlugin(str(root/'bin'/cmds.about(version=True)/('aru_retopo_mesh_buffer_'+version+'.mll')),quiet=True)
    node=cmds.createNode('aruRetopoMeshBuffer');sel=om.MSelectionList();sel.add(node);dep=om.MFnDependencyNode(sel.getDependNode(0))
    integers={'faceCounts','faceIndices','stencilOffsets','stencilIndices','adjacencyOffsets','adjacencyIndices'}
    for name,values in data['arrays'].items():
        fn=om.MFnIntArrayData() if name in integers else om.MFnDoubleArrayData()
        dep.findPlug(name,False).setMObject(fn.create(values))
    for name,value in data['settings'].items():cmds.setAttr(node+'.'+name,value)
    cmds.setAttr(node+'.guideMatrix',*data['matrix'],type='matrix')
    storage=om.MFnMeshData().create();tri=data['reference_indices']
    om.MFnMesh().create(om.MPointArray(data['reference_points']),[3]*(len(tri)//3),tri,parent=storage)
    dep.findPlug('referenceMesh',False).setMObject(storage)
    source=dep.findPlug('positions',False);output=dep.findPlug('outPositions',False)
    poses=[om.MFnDoubleArrayData().create(data['arrays']['positions']),om.MFnDoubleArrayData().create(data['relaxed_positions'])]
    cache_stats=None
    if os.environ.get('ARU_TEST_CACHE_STATS'):
        import ctypes as C
        lib=C.CDLL(str(root/'bin'/cmds.about(version=True)/('aru_retopo_mesh_buffer_'+version+'.mll')))
        lib.aru_cache_stats.argtypes=[C.POINTER(C.c_ulonglong)]
        lib.aru_cache_stats.restype=None
        cache_stats=(C.c_ulonglong*4)()
    rows=[];hashes={}
    for i in range(24):
        if i in (2,4,6,8):
            points=[list(p) for p in data['reference_points']]
            triangles=list(data['reference_indices'])
            if i==2:
                for p in points:p[2]+=.015*p[0]
            if i==6:
                for j in range(0,len(triangles),3):triangles[j+1],triangles[j+2]=triangles[j+2],triangles[j+1]
            storage=om.MFnMeshData().create()
            om.MFnMesh().create(om.MPointArray(points),[3]*(len(triangles)//3),triangles,parent=storage)
            dep.findPlug('referenceMesh',False).setMObject(storage)
        if i in (10,14):
            weights=list(data['arrays']['guideWeights'])
            if i==10:weights=[v*.5 for v in weights]
            dep.findPlug('guideWeights',False).setMObject(om.MFnDoubleArrayData().create(weights))
        if i in (12,14):
            adjacency=list(data['arrays']['adjacencyIndices'])
            if i==12:
                offsets=data['arrays']['adjacencyOffsets']
                for j in range(len(offsets)-1):adjacency[offsets[j]:offsets[j+1]]=reversed(adjacency[offsets[j]:offsets[j+1]])
            dep.findPlug('adjacencyIndices',False).setMObject(om.MFnIntArrayData().create(adjacency))
        if i==16:
            cmds.setAttr(node+'.relaxIterations',3);cmds.setAttr(node+'.projectionGuard',False)
        if i==18:cmds.setAttr(node+'.projectToReference',False)
        if i==20:
            for key,value in data['settings'].items():cmds.setAttr(node+'.'+key,value)
        if i==22:
            cmds.setAttr(node+'.guideMatrix',1,0,0,0,0,1,0,0,0,0,1,0,.02,0,0,1,type='matrix')
        source.setMObject(poses[i%2]);start=time.perf_counter();obj=output.asMObject();elapsed=(time.perf_counter()-start)*1000
        values=list(om.MFnDoubleArrayData(obj).array());assert values
        hashes[str(i%2)]=hashlib.sha256(struct.pack('='+str(len(values))+'d',*values)).hexdigest()
        row={'output_hash':hashes[str(i%2)],'frame':i,'ms':elapsed,'native_ms':cmds.getAttr(node+'.computeMilliseconds')}
        if cache_stats is not None:
            lib.aru_cache_stats(cache_stats);row['cache_cold_query_seed_hit']=list(cache_stats)
        if os.environ.get('ARU_TEST_IDLE_CPU'):
            cpu=time.process_time();wall=time.perf_counter();time.sleep(.025)
            row['idle_wall_ms']=(time.perf_counter()-wall)*1000
            row['idle_cpu_ms']=(time.process_time()-cpu)*1000
        rows.append(row)
    report={'version':version,'maya':cmds.about(version=True),'local_cvs':local_cvs,'scope':'native coordinate evaluation only; original/relaxed controls, optionally limited to local_cvs changed control vertices; no brush/write/render','vertices':len(values)//3,'faces':len(data['arrays']['faceCounts']),'samples':rows,'median_ms':statistics.median(r['ms'] for r in rows[2:]),'hashes':hashes}
    if version=='gpu':
        import ctypes as C
        lib=C.CDLL(str(root/'bin'/cmds.about(version=True)/'aru_retopo_mesh_buffer_gpu.mll'))
        lib.aru_gpu_backend_stats.argtypes=[C.POINTER(C.c_ulonglong)]
        stats=(C.c_ulonglong*3)();lib.aru_gpu_backend_stats(stats)
        report['gpu_backend_counts']=list(stats)
        if os.environ.get('ARU_TEST_EXPECT_GPU_FAILURE'):
            assert stats[0]==0 and stats[1]>0,list(stats)
        else:
            assert stats[0]>=12 and stats[1]==0,list(stats)
        original_gpu_dll=os.environ.pop('ARU_RETOPO_GPU_DLL',None)
        source.setMObject(poses[0]);output.asMObject()
        source.setMObject(poses[1]);cpu_values=list(om.MFnDoubleArrayData(output.asMObject()).array())
        error=max(abs(x-y) for x,y in zip(values,cpu_values))
        assert error<1.e-10,error
        report['cpu_max_error']=error
        if original_gpu_dll:os.environ['ARU_RETOPO_GPU_DLL']=original_gpu_dll
    (root/'tests'/('projection_certificates_node_state_'+version+'_'+cmds.about(version=True)+suffix+'.json')).write_text(json.dumps(report,indent=2))
    print('CERTIFICATE NODE STATE PASSED',version,report['median_ms'],report['vertices']);status=0
except BaseException:traceback.print_exc()
finally:
    cmds.file(new=True,force=True);maya.standalone.uninitialize();sys.stdout.flush();sys.stderr.flush();os._exit(status)
