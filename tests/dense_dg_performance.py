"""Measure real guide-to-mesh DG evaluation in a disposable Maya process."""
import os,sys,json,time,cProfile,pstats,io,statistics
os.environ['MAYA_SKIP_USERSETUP_PY']='1'
import maya.standalone
maya.standalone.initialize(name='python')
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool import maya_api as api
from Aru_RetopoTool.core import regions,patch_key,unit
from Aru_RetopoTool.tests.dense_performance import fixture

def run():
    root=os.path.dirname(os.path.dirname(__file__))
    cmds.loadPlugin(os.path.join(root,'editor/curvenet/aru_retopo_guide_plugin.py'))
    p,s=fixture();guide=cmds.createNode('retopoGuideNode')
    cmds.setAttr(guide+'.netData',json.dumps(dict(positions=p,splines=s)),type='string')
    reference=cmds.polySphere(r=3,sx=64,sy=32)[0]
    mesh,node=api.create(guide,reference,subdivisions=3)
    keys=[patch_key(r) for r in regions(p,s,unit)]
    cmds.setAttr(node+'.selectedPatches',json.dumps(keys),type='string')
    cmds.setAttr(node+'.relaxIterations',5)
    native='--native' in sys.argv
    if native:
        from Aru_RetopoTool.native_backend import enable
        enable(node)
    output_node=api.output_plug(node).rsplit('.',1)[0]
    selection=om.MSelectionList();selection.add(output_node)
    coordinates_only='--positions' in sys.argv
    dep=om.MFnDependencyNode(selection.getDependNode(0))
    plug=dep.findPlug('outPositions' if coordinates_only else 'outMesh',False)
    timings=[];stages=[]
    for i in range(20):
        t=time.perf_counter();cmds.setAttr(guide+'.controlPoints[0]',i*.0001,0,0,type='double3')
        obj=plug.asMObject()
        if coordinates_only:
            vertices=len(om.MFnDoubleArrayData(obj).array())//3
            faces=len(om.MFnIntArrayData(dep.findPlug('faceCounts',False).asMObject()).array())
        else:
            fn=om.MFnMesh(obj);vertices=fn.numVertices;faces=fn.numPolygons
        if i>=4:
            timings.append((time.perf_counter()-t)*1000)
            if native:stages.append(cmds.getAttr(output_node+'.computeMilliseconds'))
    profile=cProfile.Profile();profile.enable()
    for i in range(5):
        cmds.setAttr(guide+'.controlPoints[0]',i*.0002,0,0,type='double3');plug.asMObject()
    profile.disable();out=io.StringIO();pstats.Stats(profile,stream=out).sort_stats('cumtime').print_stats(28)
    report=dict(backend=('native_positions' if coordinates_only else 'native') if native else 'legacy',patches=len(keys),faces=faces,vertices=vertices,median_ms=statistics.median(timings),samples_ms=timings,stages_ms=stages,profile=out.getvalue())
    print(json.dumps({k:v for k,v in report.items() if k not in ('profile','samples_ms')}))
    return report
status=0
try:
    report=run()
    with open(sys.argv[1],'w') as f:json.dump(report,f,indent=2)
except Exception:
    import traceback;traceback.print_exc();status=1
finally:
    cmds.file(new=True,force=True)
    for plugin in ('aru_retopo_draw_plugin','aru_retopo_mesh_buffer_v2','aru_retopo_plan_plugin','aru_retopo_plugin','aru_retopo_guide_plugin'):
        if cmds.pluginInfo(plugin,q=True,loaded=True):cmds.unloadPlugin(plugin,force=True)
    maya.standalone.uninitialize()
sys.stdout.flush();sys.stderr.flush();os._exit(status)
