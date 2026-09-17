"""Deterministic shared-edge honeycomb near the requested 500-patch scale."""
import math,time,json
from Aru_RetopoTool.tests.test_core import network
from Aru_RetopoTool.core import Plan,unit
from Aru_RetopoTool.native import stencil,Surface


def fixture(columns=25,rows=20,radius=3.):
    locations=[];index={};edges=set()
    for row in range(rows):
        for col in range(columns):
            cx=1.5*col;cz=math.sqrt(3)*(row+.5*(col%2));vertices=[]
            for k in range(6):
                x=round(cx+math.cos(k*math.pi/3),7);z=round(cz+math.sin(k*math.pi/3),7)
                key=(x,z)
                if key not in index:index[key]=len(locations);locations.append(key)
                vertices.append(index[key])
            for a,b in zip(vertices,vertices[1:]+vertices[:1]):edges.add(tuple(sorted((a,b))))
    mx=(min(x for x,z in locations)+max(x for x,z in locations))/2
    mz=(min(z for x,z in locations)+max(z for x,z in locations))/2
    scale=radius*.8/max(math.hypot(x-mx,z-mz) for x,z in locations)
    positions=[]
    for x,z in locations:
        x=(x-mx)*scale;z=(z-mz)*scale;positions.append((x,math.sqrt(radius*radius-x*x-z*z),z))
    return network(positions,sorted(edges))


def run():
    from maya import cmds
    import maya.api.OpenMaya as om
    p,s=fixture();start=time.perf_counter();plan=Plan(p,s,unit,3);topology=(time.perf_counter()-start)*1000
    mesh=cmds.polySphere(r=3,sx=64,sy=32)[0]
    sel=om.MSelectionList();sel.add(mesh);path=sel.getDagPath(0);path.extendToShape();fn=om.MFnMesh(path)
    _,tri=fn.getTriangles();surface=Surface([tuple(v)[:3] for v in fn.getPoints()],list(tri));seeds=None;times=[]
    try:
        for i in range(6):
            moved=list(p);v=p[0];moved[0]=(v[0]+i*.0001,v[1],v[2])
            start=time.perf_counter();generated=plan.evaluate(moved,s,stencil);evaluated=time.perf_counter()
            generated,seeds=surface.relax(generated,plan,5,seeds=seeds);end=time.perf_counter()
            times.append({'evaluate_ms':(evaluated-start)*1000,'relax_ms':(end-evaluated)*1000})
        from Aru_RetopoTool.tests.display import prepare_probe
        parent=cmds.createNode('transform',name='denseRetopoBenchmark')
        selection=om.MSelectionList();selection.add(parent)
        start=time.perf_counter()
        result_mesh=om.MFnMesh().create(om.MPointArray(generated),[4]*len(plan.faces),[v for f in plan.faces for v in f],parent=selection.getDependNode(0))
        upload_ms=(time.perf_counter()-start)*1000
        try:draw_ms=prepare_probe(parent,detailed=True)
        finally:cmds.delete(parent)
        return {'patches':plan.region_count,'quads':len(plan.faces),'vertices':plan.count,'guides':len(s),'topology_ms':topology,'samples':times,'mesh_create_ms':upload_ms,'draw_cold_prepare_ms':draw_ms}
    finally:surface.close();cmds.delete(mesh)


if __name__=='__main__':
    import os,sys,traceback
    import maya.standalone
    maya.standalone.initialize(name='python')
    status=0
    try:
        from maya import cmds
        import maya.api.OpenMaya as om
        from Aru_RetopoTool.tests.projection_cache import run as check_cache
        mesh=cmds.polySphere(r=3,sx=32,sy=16)[0]
        selection=om.MSelectionList();selection.add(mesh)
        path=selection.getDagPath(0);path.extendToShape();fn=om.MFnMesh(path)
        _,tri=fn.getTriangles()
        check_cache([tuple(p)[:3] for p in fn.getPoints()],list(tri))
        cmds.delete(mesh)
        report=run();print(json.dumps(report))
        if len(sys.argv)>1:
            with open(sys.argv[1],'w') as out:json.dump(report,out,indent=2)
    except Exception:
        traceback.print_exc();status=1
    finally:maya.standalone.uninitialize()
    sys.stdout.flush();sys.stderr.flush();os._exit(status)
