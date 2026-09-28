"""Compare retained native projection seeds with legacy list conversion."""
import json,time,statistics
from maya import cmds
import maya.api.OpenMaya as om
from Aru_RetopoTool.tests.dense_performance import fixture
from Aru_RetopoTool.core import Plan,unit
from Aru_RetopoTool.native import Surface,stencil


def run():
    p,s=fixture();plan=Plan(p,s,unit,3)
    node=cmds.polySphere(r=3,sx=64,sy=32)[0]
    selection=om.MSelectionList();selection.add(node);path=selection.getDagPath(0);path.extendToShape()
    fn=om.MFnMesh(path);_,tri=fn.getTriangles()
    surfaces=[Surface([(v.x,v.y,v.z) for v in fn.getPoints()],list(tri)) for _ in range(2)]
    seeds=[None,None];samples=[[],[]]
    try:
        for i in range(20):
            moved=list(p);v=p[0];moved[0]=(v[0]+i*.0001,v[1],v[2])
            generated=plan.evaluate(moved,s,stencil);outputs=[]
            for k in (i%2,1-i%2):
                t=time.perf_counter()
                output,seeds[k]=surfaces[k].relax(generated,plan,5,seeds=seeds[k],native_seeds=bool(k))
                if i>=4:samples[k].append((time.perf_counter()-t)*1000)
                outputs.append(output)
            assert outputs[0]==outputs[1]
            assert list(seeds[0])==list(seeds[1])
        return dict(patches=plan.region_count,vertices=plan.count,list_ms=samples[0],native_ms=samples[1],median_list=statistics.median(samples[0]),median_native=statistics.median(samples[1]))
    finally:
        for surface in surfaces:surface.close()
        cmds.delete(node)

if __name__=='__main__':
    import sys,os,traceback,maya.standalone
    maya.standalone.initialize(name='python');status=0
    try:
        report=run()
        with open(sys.argv[1],'w') as f:json.dump(report,f,indent=2)
        print(json.dumps({k:v for k,v in report.items() if not isinstance(v,list)}))
    except Exception:traceback.print_exc();status=1
    finally:maya.standalone.uninitialize()
    sys.stdout.flush();sys.stderr.flush();os._exit(status)
